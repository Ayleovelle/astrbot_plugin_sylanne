"""Process-local sharing registry for SylanneEngine.

Deduplicates engines by resolved data_dir so one persistence directory is owned
by exactly one engine per process (prevents lost-update on flush).

Engines are event-loop affine: a shared engine must be used from the loop it was
first acquired on. Cross-loop sharing raises RuntimeError.

The SylanneEngine import is deferred to function bodies to avoid a circular
import (engine.py imports nothing from here at module load). Keep it that way.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import os
import threading
import weakref
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

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
_REGISTRY: dict[str, _Entry | asyncio.Future[None]] = {}
_LOCK = threading.Lock()


def _make_key(data_dir: str | Path) -> str:
    """Canonical dedup key: resolved, case-folded absolute path.

    resolve(strict=False) tolerates a not-yet-existing directory (start() creates
    it later). normcase folds case and separators on Windows; no-op on POSIX.
    """
    return os.path.normcase(str(Path(data_dir).resolve()))


def _copy_config(cfg: SylanneConfig) -> SylanneConfig:
    """Return an independent copy so caller mutation cannot shift the baseline."""
    return dataclasses.replace(cfg)


async def get_shared_engine(
    data_dir: str | Path,
    llm: LLMFn | None,
    embedding: EmbeddingFn | None = None,
    config: SylanneConfig | None = None,
) -> SylanneEngine:
    """Return (and start) the process-shared engine for ``data_dir``.

    See SylanneEngine.shared for the public contract.
    """
    from .engine import SylanneEngine

    key = _make_key(data_dir)
    resolved_dir = Path(data_dir).resolve()
    cfg = _copy_config(config if config is not None else SylanneConfig())
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
                    raise ValueError(
                        f"llm is required to create a new shared engine for {key!r}"
                    )
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
                if slot.config != cfg:
                    raise SharedEngineConflictError(
                        f"Shared engine {key!r} already exists with a different SylanneConfig."
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
                    resolved_dir, llm, embedding=embedding, config=cfg, _shared=True
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
            init_future.set_result(None)
            return new_engine

        assert engine is not None
        if engine.status in ("init", "closed"):
            await engine.start()
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
        if not tombstone.done():
            tombstone.set_result(None)


def clear_shared_registry() -> None:
    """Drop all registry entries WITHOUT shutdown. TEST ISOLATION ONLY.

    DANGER: this does NOT call shutdown() and does NOT flush sessions — any
    in-memory state not yet persisted is lost, and live engines are orphaned
    (still running, just no longer findable via shared()). It exists so tests
    can reset process-global state cheaply between cases.

    Never call this in production. For real teardown use release_shared_engine()
    (or SylanneEngine.release_shared), which flushes and shuts down cleanly.

    Safe to call from sync code with no event loop.
    """
    with _LOCK:
        _REGISTRY.clear()


def is_shared(data_dir: str | Path) -> bool:
    """Return True if a live shared engine is registered for ``data_dir``.

    A slot mid-teardown (tombstone) counts as not-live: the engine is on its
    way out and the path will soon be free.
    """
    key = _make_key(data_dir)
    with _LOCK:
        return isinstance(_REGISTRY.get(key), _Entry)


def list_shared() -> list[dict[str, str]]:
    """Snapshot of the live shared engines in this process.

    Returns one dict per live entry with its resolved ``data_dir`` key and the
    engine's current ``status``. Slots mid-teardown (tombstones) are omitted.
    Intended for diagnostics — e.g. spotting redundant engines across plugins.
    """
    with _LOCK:
        snapshot = [(key, entry) for key, entry in _REGISTRY.items() if isinstance(entry, _Entry)]
    # Read engine.status outside the lock; it is a cheap attribute read.
    return [{"data_dir": key, "status": entry.engine.status} for key, entry in snapshot]


def warn_if_shared_exists(data_dir: str | Path) -> None:
    """Warn when a direct SylanneEngine(...) targets a data_dir already shared.

    Called from SylanneEngine.__init__ for direct construction only (shared()
    builds its instance through a path that bypasses this). The goal is to
    surface the "10 plugins, 10 engines on one data_dir" waste without blocking
    legitimate serial reuse (e.g. restart after shutdown).
    """
    key = _make_key(data_dir)
    with _LOCK:
        exists = isinstance(_REGISTRY.get(key), _Entry)
    if exists:
        logger.warning(
            "A shared SylanneEngine already exists for %r, but a new engine is being "
            "constructed directly for the same data_dir. Two engines on one directory "
            "duplicate computation and LLM calls and can overwrite each other's state on "
            "flush. Use SylanneEngine.shared(%r, ...) to reuse the existing instance.",
            key,
            str(data_dir),
        )
