"""Process-local sharing registry for SylanneEngine.

Deduplicates engines by resolved data_dir so one persistence directory is owned
by exactly one engine per process (prevents lost-update on flush). The guarantee
is PER PROCESS: there is no cross-process lock, so two OS processes pointed at one
data_dir each build an engine and double-flush — run one process per data_dir.

Engines are event-loop affine: a shared engine must be used from the loop it was
first acquired on. Cross-loop sharing raises RuntimeError.

The SylanneEngine import is deferred to function bodies to avoid a circular
import (engine.py imports nothing from here at module load). Keep it that way.
"""

from __future__ import annotations

import asyncio
import dataclasses
import importlib
import logging
import os
import sys
import weakref
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeGuard

from ._identity import resolve_identity
from ._rendezvous import get_cell
from .config import SylanneConfig

if TYPE_CHECKING:
    from .engine import SylanneEngine

logger = logging.getLogger("sylanne_core")

LLMFn = Callable[[str, str], Awaitable[str]]
EmbeddingFn = Callable[[str], Awaitable[list[float]]]


class SharedEngineConflictError(RuntimeError):
    """Raised when shared() is given a config that conflicts with the existing entry."""


@dataclass
class _Entry:
    """A live registry entry: the engine plus the parameters it was created with."""

    engine: SylanneEngine
    config: SylanneConfig  # frozen-equivalent copy, immune to caller mutation
    llm: LLMFn
    embedding: EmbeddingFn | None
    loop_ref: weakref.ref[asyncio.AbstractEventLoop]


# A slot holds either a live _Entry or, while shutdown is in flight, an
# asyncio.Future tombstone. Concurrent shared() that sees a tombstone awaits it
# (outside the lock) then retries the lookup.
#
# The registry and its lock live in a process-global rendezvous cell, not in this
# module: vendored copies under different module names then converge on ONE
# registry and dedup for real. These names alias the cell's objects, which are
# stable for the process lifetime (cleared in place, never rebound).
_cell = get_cell()
_REGISTRY: dict[str, _Entry | asyncio.Future[None]] = _cell.registry
_LOCK = _cell.lock


def _make_key(data_dir: str | Path) -> str:
    """Canonical dedup key: resolved, case-folded absolute path.

    resolve(strict=False) tolerates a not-yet-existing directory (start() creates
    it later). normcase folds case and separators on Windows; no-op on POSIX.
    """
    return os.path.normcase(str(Path(data_dir).resolve()))


def _is_live_entry(slot: object) -> TypeGuard[_Entry]:
    """A slot is a live engine entry iff it is present and not a tombstone Future.

    Duck-typed on purpose (NOT isinstance _Entry): vendored copies under different
    module names have distinct _Entry classes, so isinstance would misjudge a
    co-resident copy's entry as absent — making the diagnostics lie and, worse,
    letting clear_shared_registry orphan another copy's still-running engine.
    """
    return slot is not None and not isinstance(slot, asyncio.Future)


def _copy_config(cfg: SylanneConfig) -> SylanneConfig:
    """Return an independent copy so caller mutation cannot shift the baseline."""
    return dataclasses.replace(cfg)


_SELF_IDENTITY: dict[str, Any] | None = None


def _self_identity() -> dict[str, Any]:
    """Resolve (and cache) THIS copy's diagnostic identity. Best-effort.

    Lazy on purpose: ``__version__`` is defined in ``__init__`` AFTER this module
    is imported, so it is read at call time, not import time.
    """
    global _SELF_IDENTITY
    if _SELF_IDENTITY is None:
        pkg = __package__ or "sylanne_core"
        try:
            version = getattr(importlib.import_module(pkg), "__version__", "0+unknown")
        except Exception:
            version = "0+unknown"
        _SELF_IDENTITY = resolve_identity(Path(__file__).resolve().parent, version, pkg)
    return _SELF_IDENTITY


def _note_identity(key: str, *, built: bool) -> None:
    """Register this copy in the rendezvous cell; warn when a consuming copy's
    version differs from the version that built the engine.

    Best-effort and never raises — identity is diagnostics, not correctness. The
    cell mutations run OUTSIDE the dedup lock section of get_shared_engine, so the
    non-reentrant cell lock is never taken twice.
    """
    try:
        cell = get_cell()
        ident = _self_identity()
        copy_id = ident.get("copy_id")
        if not copy_id:
            return
        builder_version: str | None = None
        builder_short: str | None = None
        with cell.lock:
            cell.identities[copy_id] = ident
            if built:
                cell.builders[key] = copy_id
                return
            builder_id = cell.builders.get(key)
            if builder_id and builder_id != copy_id:
                # Read the builder's record INSIDE the lock; another thread may be
                # registering or clearing identities concurrently.
                builder = cell.identities.get(builder_id)
                if builder:
                    builder_version = builder.get("version")
                    builder_short = builder.get("short")
        if builder_version and builder_version != ident.get("version"):
            logger.warning(
                "sylanne_core version skew on %r: engine built by %s (v%s), but this "
                "copy %s (v%s) loaded a different version. Namespace the vendored copy "
                "or install sylanne_core once as a shared dependency.",
                key,
                builder_short,
                builder_version,
                ident.get("short"),
                ident.get("version"),
            )
    except Exception:
        return


_SCANNED_FOR_OLD_COPIES = False


def _scan_for_pre2_copies() -> None:
    """One-shot diagnostic: warn about any pre-2.0 sylanne_core copy already loaded.

    A pre-2.0 copy predates the rendezvous cell entirely: it cannot reach this
    process's shared registry no matter what, so it will always build its own
    engine on a data_dir another copy also shares — silently double-flushing
    the SAME files from two independent engines. There is nothing to converge
    (that copy structurally cannot participate), so this is log-only: name the
    module and its file path so the operator knows to migrate it.

    Runs once per process (guarded by ``_SCANNED_FOR_OLD_COPIES``), triggered
    from the first ``get_shared_engine`` call. Entirely best-effort: any
    failure here must never break sharing itself.
    """
    global _SCANNED_FOR_OLD_COPIES
    if _SCANNED_FOR_OLD_COPIES:
        return
    _SCANNED_FOR_OLD_COPIES = True
    try:
        this_pkg = __package__ or "sylanne_core"
        for name, mod in list(sys.modules.items()):
            if mod is None or name == this_pkg or not name.endswith("sylanne_core"):
                continue
            version = getattr(mod, "__version__", None)
            if not version:
                continue
            try:
                major = int(str(version).split(".", 1)[0])
            except (ValueError, IndexError):
                continue
            if major < 2:
                logger.warning(
                    "found a pre-2.0 sylanne_core copy already imported as %r (v%s, %s) — "
                    "that copy predates the rendezvous cell and cannot reach a shared "
                    "engine at all; it will build and flush its OWN engine on any data_dir "
                    "it is pointed at, silently double-flushing alongside newer copies. "
                    "Migrate it to >=3.0.",
                    name,
                    version,
                    getattr(mod, "__file__", "<unknown path>"),
                )
    except Exception:
        return


async def get_shared_engine(
    data_dir: str | Path,
    llm: LLMFn | None,
    embedding: EmbeddingFn | None = None,
    config: SylanneConfig | None = None,
    assessor_llm: LLMFn | None = None,
) -> SylanneEngine:
    """Return (and start) the process-shared engine for ``data_dir``.

    See SylanneEngine.shared for the public contract.
    """
    from .engine import SylanneEngine

    _scan_for_pre2_copies()

    key = _make_key(data_dir)
    resolved_dir = Path(data_dir).resolve()
    explicit_config = config is not None
    # When no config is passed, self-read it (and any assessor_model block) from
    # the shared config file in data_dir, so the conflict baseline and the engine
    # see the same user-controlled settings.
    if config is not None:
        cfg = _copy_config(config)
    else:
        from ._config_store import load_config, write_default_config

        loaded_cfg, assessor_block = load_config(data_dir)
        write_default_config(data_dir)  # drop a starter template on first use
        cfg = _copy_config(loaded_cfg)
        if assessor_llm is None and assessor_block:
            from ._assessor_llm import build_from_config

            assessor_llm = build_from_config(assessor_block)
    loop = asyncio.get_running_loop()

    while True:
        pending: asyncio.Future[None] | None = None  # tombstone or init future to await
        init_future: asyncio.Future[None] | None = None  # we own this; must resolve it
        engine: SylanneEngine | None = None

        with _LOCK:
            slot = _REGISTRY.get(key)
            if slot is None:
                # First acquire: llm is mandatory to build a new engine.
                if llm is None:
                    raise ValueError(f"llm is required to create a new shared engine for {key!r}")
                # Publish an init Future as a placeholder, then build+start OUTSIDE
                # the lock. Concurrent acquirers see the Future and await it rather
                # than racing into a second start(). Only on success do we swap in
                # the real _Entry. This closes the init race and avoids leaking a
                # half-started engine on cancellation.
                init_future = loop.create_future()
                _REGISTRY[key] = init_future
            elif isinstance(slot, asyncio.Future):
                # Init or shutdown in flight: await the Future, then retry.
                pending = slot
            else:
                # Existing live entry: check loop affinity, then conflicts.
                bound = slot.loop_ref()
                if bound is not None and not bound.is_closed() and bound is not loop:
                    raise RuntimeError(
                        f"Shared engine {key!r} is bound to a different event loop. "
                        f"SylanneEngine holds loop-affine asyncio primitives and cannot "
                        f"be shared across loops/threads. Use a separate data_dir per loop."
                    )
                if bound is None or bound.is_closed():
                    # Original loop was GC'd or closed; rebind to the current one.
                    # Per-session asyncio.Lock objects are bound to the old loop and
                    # would raise "attached to a different loop" if reused, so drop
                    # them — they are recreated lazily. Session state (_hosts) is not
                    # loop-bound and is preserved.
                    slot.loop_ref = weakref.ref(loop)
                    slot.engine._locks.clear()
                    # submit()'s dedup tasks are asyncio Tasks bound to the dead loop
                    # too — awaiting them on the new loop would hang forever. Cancel
                    # and drop them (same cleanup engine.shutdown() does) so the next
                    # submit() on the rebound engine recomputes instead of wedging.
                    if hasattr(slot.engine, "_cancel_and_clear_submissions"):
                        slot.engine._cancel_and_clear_submissions()
                    if hasattr(slot.engine, "_last_tick"):
                        slot.engine._last_tick.clear()
                # A pre-2.4 builder's engine has no submit() at all: dedup is simply
                # unavailable on this data_dir until every copy upgrades. Loud because
                # silent duplicate LLM cost is exactly the failure mode 3.0 exists to
                # kill everywhere else.
                if not hasattr(slot.engine, "submit"):
                    builder_id = _cell.builders.get(key)
                    builder_short = None
                    if builder_id:
                        builder_ident = _cell.identities.get(builder_id)
                        if builder_ident:
                            builder_short = builder_ident.get("short")
                    logger.warning(
                        "shared engine %r has no submit() — it was built by a pre-2.4 "
                        "sylanne_core copy%s. submit() dedup is UNAVAILABLE on this "
                        "data_dir until every co-resident copy is upgraded to >=3.0; "
                        "duplicate LLM cost across plugins is possible until then.",
                        key,
                        f" ({builder_short})" if builder_short else "",
                    )
                # Config compatibility, compared by VALUE over the INTERSECTION of
                # field names: two vendored copies have distinct SylanneConfig
                # classes (and a newer copy may have ADDED a defaulted field), so a
                # plain != would falsely conflict on class identity or an extra key.
                stored = dataclasses.asdict(slot.config)
                wanted = dataclasses.asdict(cfg)
                if any(stored[k] != wanted[k] for k in stored.keys() & wanted.keys()):
                    if explicit_config:
                        # A caller explicitly handed a conflicting config: hard error.
                        raise SharedEngineConflictError(
                            f"Shared engine {key!r} already exists with a different SylanneConfig."
                        )
                    # Self-read diff (the on-disk file was edited, or a cross-version
                    # copy): do NOT crash a bystander acquirer. Keep the running
                    # config and tell the operator a restart is needed to apply it.
                    logger.warning(
                        "shared engine %r: on-disk config differs from the running "
                        "engine; keeping the running config (restart to apply).",
                        key,
                    )
                if llm is not None and slot.llm is not llm:
                    logger.warning(
                        "shared engine %r reused with a different llm; keeping original", key
                    )
                if embedding is not None and slot.embedding is not embedding:
                    logger.warning(
                        "shared engine %r reused with a different embedding; keeping original",
                        key,
                    )
                engine = slot.engine

        if pending is not None:
            # Wait for the in-flight init/shutdown to finish, then retry the lookup.
            # Suppress errors: the owning task reports its own failure; we just retry.
            try:
                await pending
            except (Exception, asyncio.CancelledError):
                pass
            continue

        if init_future is not None:
            # We own the placeholder: build + start, then publish the real entry.
            # llm was verified non-None under the lock before init_future was set.
            assert llm is not None
            try:
                new_engine = SylanneEngine(
                    resolved_dir,
                    llm,
                    embedding=embedding,
                    config=cfg,
                    assessor_llm=assessor_llm,
                    _shared=True,
                )
                await new_engine.start()
            except BaseException:
                # Roll back the placeholder so the slot is free for a fresh attempt,
                # and wake any waiters (they will retry and rebuild). BaseException
                # covers CancelledError so a cancelled start() does not leak the slot.
                with _LOCK:
                    if _REGISTRY.get(key) is init_future:
                        del _REGISTRY[key]
                if not init_future.done():
                    init_future.set_result(None)
                raise
            with _LOCK:
                _REGISTRY[key] = _Entry(new_engine, cfg, llm, embedding, weakref.ref(loop))
            _note_identity(key, built=True)
            init_future.set_result(None)
            return new_engine

        assert engine is not None
        if engine.status in ("init", "closed"):
            await engine.start()
        _note_identity(key, built=False)
        return engine


async def release_shared_engine(data_dir: str | Path) -> None:
    """Shut down and remove the shared engine for ``data_dir``.

    Replaces the slot with a tombstone Future under the lock, awaits shutdown
    outside the lock, then frees the slot and resolves the tombstone so any
    waiters retry and build a fresh engine.

    Idempotent: if the engine is already gone, or another release is in flight,
    this returns immediately rather than awaiting that release. "Release the
    thing I asked to release" is satisfied either way, and not awaiting a
    foreign tombstone avoids reintroducing cross-loop coupling.
    """
    key = _make_key(data_dir)
    loop = asyncio.get_running_loop()

    with _LOCK:
        slot = _REGISTRY.get(key)
        if slot is None or isinstance(slot, asyncio.Future):
            # Nothing live to release (already gone, or a release is in flight).
            return
        # Loop affinity: shutdown() touches loop-bound primitives, so it must run
        # on the loop the engine was acquired on. Mirror the check in acquire.
        bound = slot.loop_ref()
        if bound is not None and not bound.is_closed() and bound is not loop:
            raise RuntimeError(
                f"Shared engine {key!r} is bound to a different event loop and cannot "
                f"be released from this one. Call release_shared() on the loop that "
                f"acquired it."
            )
        tombstone: asyncio.Future[None] = loop.create_future()
        _REGISTRY[key] = tombstone
        engine_to_close = slot.engine

    try:
        await engine_to_close.shutdown()
    finally:
        with _LOCK:
            if _REGISTRY.get(key) is tombstone:
                del _REGISTRY[key]
                # Drop the stale builder record too, so a released path leaves no
                # orphaned driver id behind (clear_shared_registry does the same).
                # _LOCK is the cell lock, so this is consistent with the del above.
                _cell.builders.pop(key, None)
        if not tombstone.done():
            tombstone.set_result(None)


def clear_shared_registry() -> None:
    """Drop THIS copy's registry entries WITHOUT shutdown. TEST ISOLATION ONLY.

    DANGER: this does NOT call shutdown() and does NOT flush sessions — any
    in-memory state not yet persisted is lost, and live engines are orphaned
    (still running, just no longer findable via shared()). It exists so tests
    can reset process-global state cheaply between cases.

    Scoped to entries THIS copy built (plus tombstones and builder-less slots),
    so a reset in one vendored copy never orphans an engine a co-resident copy is
    still using. In the common single-copy case this clears everything, as before.

    Never call this in production. For real teardown use release_shared_engine()
    (or SylanneEngine.release_shared), which flushes and shuts down cleanly.

    Safe to call from sync code with no event loop.
    """
    cell = get_cell()
    try:
        my_copy_id = _self_identity().get("copy_id")
    except Exception:
        my_copy_id = None
    with cell.lock:
        if my_copy_id is None:
            # Identity unavailable: clear everything (safe in the single-copy/test
            # case this method exists for).
            cell.registry.clear()
            cell.identities.clear()
            cell.builders.clear()
            return
        for slot_key in list(cell.registry):
            entry = cell.registry[slot_key]
            if not _is_live_entry(entry):
                # Tombstone (Future): transient, drop it.
                del cell.registry[slot_key]
                cell.builders.pop(slot_key, None)
            elif cell.builders.get(slot_key) == my_copy_id:
                # A live entry THIS copy built. A foreign copy's live entry (or one
                # with no recorded builder) is left alone so we never orphan it.
                del cell.registry[slot_key]
                cell.builders.pop(slot_key, None)
        cell.identities.pop(my_copy_id, None)


def is_shared(data_dir: str | Path) -> bool:
    """Return True if a live shared engine is registered for ``data_dir``.

    A slot mid-teardown (tombstone) counts as not-live: the engine is on its
    way out and the path will soon be free.
    """
    key = _make_key(data_dir)
    with _LOCK:
        return _is_live_entry(_REGISTRY.get(key))


def list_shared() -> list[dict[str, str]]:
    """Snapshot of the live shared engines in this process.

    Returns one dict per live entry with its resolved ``data_dir`` key and the
    engine's current ``status``. Slots mid-teardown (tombstones) are omitted.
    Intended for diagnostics — e.g. spotting redundant engines across plugins.
    """
    with _LOCK:
        snapshot = [(key, entry) for key, entry in _REGISTRY.items() if _is_live_entry(entry)]
    # Read engine.status outside the lock; it is a cheap attribute read.
    return [{"data_dir": key, "status": entry.engine.status} for key, entry in snapshot]


def resolve_shared_data_dir(explicit: str | Path | None = None) -> Path:
    """Resolve the canonical host-shared ``data_dir`` so co-deployed plugins converge.

    Sharing dedups by ``data_dir``: if each embedded-SDK plugin defaults to its own
    directory, they never collide and you get one engine per plugin — the exact
    waste the driver/observer model exists to avoid. Route every plugin through
    this and they land on ONE engine. Priority:

      1. ``explicit`` (if given) — the caller pins the directory.
      2. ``$SYLANNE_DATA_DIR`` — the host operator pins one directory for all plugins.
      3. ``~/.sylanne/shared`` — a stable per-user default.

    Returns a resolved absolute path. It is NOT created here — ``start()`` creates
    it on first use. The result feeds straight into ``shared``.
    """
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("SYLANNE_DATA_DIR")
    if env and env.strip():
        return Path(env.strip()).expanduser().resolve()
    try:
        home = Path.home()
    except (RuntimeError, OSError):
        # Home undeterminable (unusual container/service accounts): fall back to a
        # stable cwd-relative dir so the path is still deterministic for the run.
        home = Path.cwd()
    return (home / ".sylanne" / "shared").resolve()


def peek_shared_engine(data_dir: str | Path) -> SylanneEngine | None:
    """Return the live shared engine for ``data_dir``, or None. NEVER builds.

    Unlike ``get_shared_engine``, this never constructs or starts an engine — it
    is the attach-only primitive an observer uses to grab the driver's engine
    without becoming a driver itself. A slot mid-teardown counts as absent.
    """
    key = _make_key(data_dir)
    with _LOCK:
        slot = _REGISTRY.get(key)
        if _is_live_entry(slot):
            return slot.engine
    return None


def warn_if_shared_exists(data_dir: str | Path) -> None:
    """Warn when a direct SylanneEngine(...) targets a data_dir already shared.

    Called from SylanneEngine.__init__ for direct construction only (shared()
    builds its instance through a path that bypasses this). The goal is to
    surface the "10 plugins, 10 engines on one data_dir" waste without blocking
    legitimate serial reuse (e.g. restart after shutdown).
    """
    key = _make_key(data_dir)
    with _LOCK:
        exists = _is_live_entry(_REGISTRY.get(key))
    if exists:
        logger.warning(
            "A shared SylanneEngine already exists for %r, but a new engine is being "
            "constructed directly for the same data_dir. Two engines on one directory "
            "duplicate computation and LLM calls and can overwrite each other's state on "
            "flush. Use SylanneEngine.shared(%r, ...) to reuse the existing instance.",
            key,
            str(data_dir),
        )
