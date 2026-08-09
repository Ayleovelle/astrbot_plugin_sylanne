"""SylanneEngine — the public entry point for Sylanne-Core SDK.

Provides the async API for integrating affective computation into chatbots.
Instantiate it directly with your own LLM callback.

Typical usage::

    from sylanne_core import SylanneEngine, SylanneConfig

    engine = SylanneEngine(data_dir="./data", llm=my_llm_fn)
    await engine.start()
    surface = await engine.process("session_1", "你好")
    print(surface["decision"]["action"])  # e.g. "express"
    await engine.shutdown()
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .compute import SylanneHost
    from .telemetry import DistillationSink

from .compute.utils import safe_filename
from .config import SylanneConfig
from .types import EngineStatus, HealthStatus, Surface

logger = logging.getLogger("sylanne_core")


@dataclass
class _Submission:
    """One in-flight-or-recently-completed ``submit()`` computation.

    Stored under one or two keys in ``engine._submissions`` — the text-hash
    key always, and the ``msg_id`` key too once a caller has supplied one —
    with BOTH keys pointing at the same instance, so a join through either
    index reaches the same task and eviction (via ``keys``) removes it once.
    """

    task: asyncio.Task[Surface]
    created: float
    text_hash: str
    msg_id: str | None
    ctx_fp: tuple[Any, ...]
    keys: tuple[Any, ...]
    done_at: float | None = None
    warned_text_divergence: bool = False
    warned_ctx_divergence: bool = False


class SylanneEngine:
    """Affective computation engine with session management and persistence.

    Each session maintains independent emotional state that evolves through
    a 7-layer computation pipeline on every process() call.

    Args:
        data_dir: Directory for session state persistence (created if missing).
        llm: Async function(system_prompt, user_prompt) -> str for semantic assessment.
        embedding: Optional async function(text) -> list[float] for memory retrieval.
        config: Engine configuration. Defaults to SylanneConfig().

    Example::

        async def my_llm(system: str, user: str) -> str:
            return await call_openai(system, user)

        engine = SylanneEngine(data_dir="./data", llm=my_llm)
        await engine.start()
        surface = await engine.process("user_123", "hello")
        # surface["decision"]["action"] in {"express", "listen", "hold", ...}
        await engine.shutdown()
    """

    def __init__(
        self,
        data_dir: str | Path,
        llm: Callable[[str, str], Awaitable[str]],
        embedding: Callable[[str], Awaitable[list[float]]] | None = None,
        config: SylanneConfig | None = None,
        *,
        assessor_llm: Callable[[str, str], Awaitable[str]] | None = None,
        _shared: bool = False,
    ) -> None:
        # _shared is set only by SylanneEngine.shared() when it builds the one
        # canonical instance for a data_dir. Direct construction (the default)
        # warns if that data_dir already has a live shared engine, to surface
        # the "many plugins, many redundant engines on one directory" waste.
        if not _shared:
            from ._sharing import warn_if_shared_exists

            warn_if_shared_exists(data_dir)
        self._data_dir = Path(data_dir)
        self._llm = llm
        self._embedding = embedding
        # Track whether config came from the file (vs passed in code) so start()
        # can drop a starter template only for the file-driven path.
        self._config_from_file = config is None
        # No config passed -> self-read it from the shared config file in data_dir
        # (one stable place users edit, independent of which copy owns the engine).
        # A missing/invalid file falls back to defaults. An ``assessor_model`` block
        # becomes a small dedicated assessor llm; without one, assessment falls back
        # to the main llm.
        if config is None:
            from ._config_store import load_config

            config, assessor_block = load_config(data_dir)
            if assessor_llm is None and assessor_block:
                from ._assessor_llm import build_from_config

                assessor_llm = build_from_config(assessor_block)
        self._config = config
        self._assessor_llm = assessor_llm
        self._shared = _shared
        self._status: EngineStatus = "init"
        self._hosts: dict[str, SylanneHost] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._listeners: list[Callable[[str, Surface], Any]] = []
        self._telemetry_sink: DistillationSink | None = self._build_telemetry_sink()
        # --- submit() dedup table (engine-instance, engine-loop-affine: no locks) ---
        self._submissions: dict[Any, _Submission] = {}
        # Bounded FIFO of recently-evicted keys, used only to classify a later miss
        # on the same key as "recomputed_after_window" vs a genuinely new key for
        # submit_stats(). Capped like the dedup table itself so long-running
        # processes never grow this without bound.
        self._recent_evicted: OrderedDict[Any, None] = OrderedDict()
        self._stat_computed = 0
        self._stat_joined = 0
        self._stat_recomputed_after_window = 0
        # Diagnostics-only identity registry; see ``participants()``. NEVER read
        # by any branch that affects behavior — see module docs / submit().
        self._participants: dict[str, dict[str, Any]] = {}
        self._process_nudge_logged = False
        # --- tick() absolute-minimum-interval coalescer state ---
        self._last_tick: dict[str, tuple[float, Surface]] = {}

    @property
    def status(self) -> EngineStatus:
        return self._status

    async def start(self) -> None:
        """Initialize the engine. Must be called before process/tick."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        if self._config_from_file:
            from ._config_store import write_default_config

            write_default_config(self._data_dir)
        self._status = "running"

    async def _ensure_started(self) -> None:
        """Start a not-yet-started engine; restart a closed DIRECT engine.

        A closed SHARED engine must NOT silently self-resurrect: it was released
        and removed from the registry, so reviving it here would let the next
        SylanneEngine.shared() build a SECOND engine on this data_dir and
        double-flush. Raise instead, telling the caller to re-acquire via shared().
        """
        if self._status == "closed":
            if self._shared:
                raise RuntimeError(
                    "This shared SylanneEngine was released (status='closed'). "
                    "Re-acquire it via SylanneEngine.shared(data_dir, ...); reusing a "
                    "released instance would duplicate the engine on this data_dir and "
                    "lose updates on flush."
                )
            await self.start()

    def on(self, listener: Callable[[str, Surface], Any]) -> None:
        """注册推送监听器。每次 process() 完成后，listener(session_id, surface) 会被调用。"""
        self._listeners.append(listener)

    def off(self, listener: Callable[[str, Surface], Any]) -> None:
        """移除推送监听器。"""
        self._listeners = [fn for fn in self._listeners if fn is not listener]

    def health(self) -> HealthStatus:
        """引擎健康检查，开发者用于判断计算模块是否正常。"""
        return {
            "status": self._status,
            "active_sessions": len(self._hosts),
            "data_dir_exists": self._data_dir.exists(),
            "llm_configured": self._llm is not None,
            "embedding_configured": self._embedding is not None,
        }

    async def shutdown(self) -> None:
        """Flush all sessions and release resources. Engine becomes 'closed'."""
        had_flush_error = False
        for session_id, host in self._hosts.items():
            try:
                host.flush()
            except Exception:
                had_flush_error = True
                logger.warning(
                    "flush failed for session %r during shutdown; its latest state may be lost",
                    session_id,
                    exc_info=True,
                )
        self._hosts.clear()
        self._locks.clear()
        self._cancel_and_clear_submissions()
        self._last_tick.clear()
        if self._telemetry_sink is not None:
            self._telemetry_sink.close()
        # Preserve a flush failure in the final status instead of masking it as a
        # clean 'closed'.
        self._status = "degraded" if had_flush_error else "closed"

    async def __aenter__(self) -> SylanneEngine:
        await self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.shutdown()

    async def process(
        self,
        session_id: str,
        text: str,
        *,
        confidence: float | None = None,
        flags: list[str] | None = None,
        now: float | None = None,
        values: dict[str, float] | None = None,
    ) -> Surface:
        """Process a user message and return the computed emotional surface.

        Args:
            session_id: Unique session identifier (e.g. user ID or chat ID).
            text: The user's message text.
            confidence: Pre-computed confidence score [0,1]. Overrides LLM assessment.
            flags: Semantic flags (e.g. ["safe"], ["hurt", "boundary"]).
            now: Unix timestamp. Defaults to current time.
            values: Additional numeric signals (e.g. {"group_heat": 0.7}).
                特殊键 ``"dialogue_quality"``（归一化 [0,1]）= 对上一轮回复的质量自评，
                驱动「越聊越校准」人格漂移：高分强化表达欲+拉近关系，低分收敛表达欲。
                滞后反馈——在评分对象的下一轮调用时传入。

        Returns:
            Surface dict with keys: state, decision, guard, personality, memory, dynamics.

        Note:
            On a ``shared()`` engine, prefer ``submit()`` — it dedups identical
            messages across co-resident plugins; ``process()`` always recomputes,
            so N plugins calling it on the same shared engine still pay N LLM
            calls. This stays public (some callers genuinely want raw, always-fresh
            processing), but a shared engine logs a one-time nudge below.
        """
        if self._shared and not self._process_nudge_logged:
            self._process_nudge_logged = True
            logger.info(
                "process() called directly on the shared engine for %s; if you want "
                "cross-plugin duplicate-message dedup, call submit() instead — process() "
                "always recomputes and never joins",
                self._data_dir,
            )
        await self._ensure_started()
        assessment = await self._assess(text) if self._config.assessor_enabled else None
        async with self._session_lock(session_id):
            host = self._get_or_create_host(session_id)
            event = {
                "text": text,
                "confidence": (
                    confidence
                    if confidence is not None
                    else (assessment or {}).get("confidence", 0.0)
                ),
                "flags": (flags if flags is not None else (assessment or {}).get("flags", [])),
                "now": now if now is not None else time.time(),
                "values": values or {},
            }
            result = host.on_request(event, assessment=assessment)
            surface = self._to_surface(session_id, host, result)
            await self._notify(session_id, surface)
            return surface

    async def submit(
        self,
        session_id: str,
        text: str,
        *,
        msg_id: str | None = None,
        confidence: float | None = None,
        flags: list[str] | None = None,
        now: float | None = None,
        values: dict[str, float] | None = None,
        dedup: bool = True,
        plugin: str | None = None,
    ) -> Surface:
        """Submit a message for idempotent, cross-plugin-dedup'd processing.

        The front door for a ``shared()`` engine. When several co-resident
        plugins each receive the SAME platform event and each call ``submit()``
        with the same ``session_id`` (and the same text, or better, the same
        ``msg_id``), only the FIRST call actually computes — the rest join that
        computation and all receive the identical :class:`Surface`. There is no
        election, no role, and no dependence on which plugin loaded first or
        how many plugins exist: correctness comes from "has this message been
        submitted before", not from anyone's identity.

        The guarantee is precise, not magical: it is 1x for submit() callers
        that use CONSISTENT keys — pass the platform's raw, unmodified message
        text, or (strongly recommended) a stable ``msg_id`` such as the
        platform's own message id. Mixing "sometimes msg_id, sometimes not" for
        the same logical message is absorbed by the dual index (see below) but
        is not what gives the tightest guarantee. Callers that bypass submit()
        (calling ``process()`` directly) are not covered — that is a deliberate
        escape hatch, not a hole in this contract.

        Args:
            session_id: Unique session identifier (e.g. user ID or chat ID).
            text: The user's message text. Pass the platform's raw text.
            msg_id: The platform's own message id, if available (e.g.
                ``event.message_obj.message_id``). Strongly recommended: it is
                the exact, un-guessable join key and immune to text-normalization
                differences between plugins.
            confidence: Pre-computed confidence score [0,1]. Overrides LLM assessment.
            flags: Semantic flags (e.g. ["safe"], ["hurt", "boundary"]).
            now: Unix timestamp. Defaults to current time.
            values: Additional numeric signals — see ``process()``.
            dedup: When False, this is exactly ``process()`` (no dedup table
                involvement at all) — the raw, always-recompute escape hatch.
            plugin: Optional caller identity string, purely for diagnostics (see
                ``participants()``/``submit_stats()``). Never affects dedup/join
                behavior — identity observes, idempotency guarantees.

        Returns:
            The Surface — either freshly computed (this call was first) or
            joined from another awaiter's in-flight/just-completed computation.

        Dedup mechanics (engine-instance table, engine-loop-affine — no locks):
            Each first-seen submission is indexed under its text-hash key
            always, and ALSO under its ``msg_id`` key when one was given. A
            later call with no ``msg_id`` may join on a hash hit. A later call
            WITH ``msg_id`` joins an existing hash-hit only if that entry
            recorded no ``msg_id`` of its own; if it recorded a DIFFERENT
            ``msg_id``, that is a genuine repeat (same text, distinct message)
            and triggers a fresh computation. A direct ``msg_id`` hit always
            joins — even if its recorded text differs (logged once as a
            warning; reusing a msg_id for different text is a dangerous
            pattern and the platform is trusted here, so the FIRST submission
            for that id wins). Divergent confidence/flags/values on a join is
            logged once at debug level; the first submitter's context wins.

            The real computation runs in a DETACHED task (created, not directly
            awaited) so that any one awaiter cancelling its own await can never
            cancel the shared computation for the others — every awaiter
            (including the first submitter) awaits ``asyncio.shield(task)``.

            Completed entries are pruned lazily on each ``submit()`` call: once
            older than ``config.submit_window_seconds``, or beyond
            ``config.submit_max_entries`` (oldest completed evicted first).
            IN-FLIGHT entries are never capped or evicted by either rule. A
            FAILED task evicts its own keys immediately — a poisoned entry
            does not get to "stick" for the rest of the window.
        """
        if not dedup:
            return await self.process(
                session_id, text, confidence=confidence, flags=flags, now=now, values=values
            )

        self._prune_submissions()

        text_hash = "h:" + hashlib.blake2b(text.encode()).hexdigest()[:32]
        key_hash = (session_id, text_hash)
        key_msg = (session_id, msg_id) if msg_id is not None else None
        ctx_fp = self._ctx_fingerprint(confidence, flags, values)

        entry: _Submission | None = None
        joined = False

        if key_msg is not None:
            entry = self._submissions.get(key_msg)
            if entry is not None:
                joined = True
                if entry.text_hash != text_hash and not entry.warned_text_divergence:
                    entry.warned_text_divergence = True
                    logger.warning(
                        "submit(): msg_id %r on session %r was already submitted with "
                        "DIFFERENT text — joining the first submission's result anyway "
                        "(msg_id is trusted as authoritative). Reusing a msg_id across "
                        "distinct message text is a dangerous pattern; make sure msg_id "
                        "is unique per logical message.",
                        msg_id,
                        session_id,
                    )
            else:
                hash_hit = self._submissions.get(key_hash)
                if hash_hit is not None and hash_hit.msg_id is None:
                    # Upgrade the hash-only entry so future msg_id lookups join directly.
                    hash_hit.msg_id = msg_id
                    hash_hit.keys = (*hash_hit.keys, key_msg)
                    self._submissions[key_msg] = hash_hit
                    entry = hash_hit
                    joined = True
                elif hash_hit is not None and hash_hit.msg_id != msg_id:
                    # A different msg_id already claims this text: a genuine repeat,
                    # not a duplicate delivery of the same message -> compute fresh.
                    entry = None
        else:
            hash_hit = self._submissions.get(key_hash)
            if hash_hit is not None:
                entry = hash_hit
                joined = True

        if joined and entry is not None:
            if entry.ctx_fp != ctx_fp and not entry.warned_ctx_divergence:
                entry.warned_ctx_divergence = True
                logger.debug(
                    "submit(): session %r joined a submission whose confidence/flags/"
                    "values differ from this call's; the first submitter's context wins.",
                    session_id,
                )
            self._stat_joined += 1
            self._note_submit_outcome(plugin, joined=True)
            return await asyncio.shield(entry.task)

        # Miss: this call is the one that computes.
        was_recently_evicted = key_hash in self._recent_evicted or (
            key_msg is not None and key_msg in self._recent_evicted
        )
        keys: tuple[Any, ...] = (key_hash,) if key_msg is None else (key_hash, key_msg)
        task: asyncio.Task[Surface] = asyncio.ensure_future(
            self.process(
                session_id, text, confidence=confidence, flags=flags, now=now, values=values
            )
        )
        new_entry = _Submission(
            task=task,
            created=time.time(),
            text_hash=text_hash,
            msg_id=msg_id,
            ctx_fp=ctx_fp,
            keys=keys,
        )
        for k in keys:
            self._submissions[k] = new_entry
            self._recent_evicted.pop(k, None)
        task.add_done_callback(self._on_submission_done)
        if was_recently_evicted:
            self._stat_recomputed_after_window += 1
        else:
            self._stat_computed += 1
        self._note_submit_outcome(plugin, joined=False)
        return await asyncio.shield(task)

    def submit_stats(self) -> dict[str, Any]:
        """Snapshot of submit() dedup counters since engine construction.

        Returns ``{"computed": int, "joined": int, "recomputed_after_window": int}``.
        ``recomputed_after_window`` is a best-effort heuristic bounded the same
        way the dedup table itself is (an LRU of recently-evicted keys) — a miss
        for a key evicted long enough ago to have aged out of that LRU is
        counted as ``computed`` instead. When any ``submit(..., plugin=...)``
        calls have been made, also includes ``"by_plugin"``: a
        ``{plugin: {"submits": int, "joins": int}}`` breakdown — diagnostics
        only, sourced from the same registry as ``participants()``.
        """
        stats: dict[str, Any] = {
            "computed": self._stat_computed,
            "joined": self._stat_joined,
            "recomputed_after_window": self._stat_recomputed_after_window,
        }
        if self._participants:
            stats["by_plugin"] = {
                name: {"submits": info["submits"], "joins": info["joins"]}
                for name, info in self._participants.items()
            }
        return stats

    def participants(self) -> list[dict[str, Any]]:
        """Snapshot of the participants registry, sorted by ``first_seen``.

        Populated only when callers pass ``plugin=`` to ``shared()``/``submit()``.
        This is diagnostics, never behavior: nothing in submit()'s dedup/join
        logic reads it, and no plugin is treated specially for having (or
        lacking) an entry here. Each item is
        ``{"plugin", "copy_id", "sdk_version", "first_seen", "submits", "joins"}``.
        """
        return [
            {"plugin": name, **info}
            for name, info in sorted(
                self._participants.items(), key=lambda item: item[1]["first_seen"]
            )
        ]

    def set_llm(
        self,
        llm: Callable[[str, str], Awaitable[str]],
        *,
        assessor_llm: Callable[[str, str], Awaitable[str]] | None = None,
    ) -> None:
        """Ops escape hatch: swap this engine's llm callback(s) at runtime.

        For replacing a dead builder's closure on a shared engine — e.g. the
        plugin that built the engine was hot-disabled/reloaded and its ``llm``
        callable now points at torn-down state (see the "driver death" note in
        SPEC) — without restarting the process. No auto-magic: nothing calls
        this for you; an operator or a health-check script decides when and
        whether to swap.

        Args:
            llm: Replaces the main llm callback used for ``process()``/``submit()``.
            assessor_llm: If given, also replaces the assessor llm. Omit to
                leave the current assessor (or main-llm fallback) untouched.
        """
        self._llm = llm
        if assessor_llm is not None:
            self._assessor_llm = assessor_llm
        logger.info("SylanneEngine llm swapped via set_llm() for %s", self._data_dir)

    async def tick(
        self,
        session_id: str,
        flags: list[str] | None = None,
        *,
        force: bool = False,
    ) -> Surface:
        """Advance session state without user input (background heartbeat).

        Enforces a per-session ABSOLUTE MINIMUM interval:
        ``config.tick_min_interval_seconds`` (default 45s). A call within that
        interval of the session's last real tick returns the cached Surface
        WITHOUT advancing state at all — no host mutation, no new snapshot.
        This is not a heartbeat scheduler and it does not own any timer of its
        own; it exists so that several co-resident plugins each running their
        own independent ~60s heartbeat loop against the same shared engine
        collapse to roughly one real tick per interval instead of N.

        ``force=True`` bypasses the coalescer and always advances state. This
        is a test/ops escape hatch, not a "heartbeat owner" role — nothing in
        this engine grants special status to a forcing caller, and racing the
        interval on purpose defeats the point of calling tick() at all.
        """
        await self._ensure_started()
        now_ts = time.time()
        if not force:
            cached = self._last_tick.get(session_id)
            if cached is not None and now_ts - cached[0] < self._config.tick_min_interval_seconds:
                return cached[1]
        async with self._session_lock(session_id):
            host = self._get_or_create_host(session_id)
            event = {
                "text": "",
                "confidence": 0.0,
                "flags": flags or ["idle"],
                "now": now_ts,
                "values": {},
            }
            result = host.on_request(event)
            surface = self._to_surface(session_id, host, result)
        self._last_tick[session_id] = (now_ts, surface)
        return surface

    async def state(self, session_id: str) -> Surface:
        """Get current session state without advancing the pipeline."""
        # Mirror process/tick/inject: a released SHARED engine must refuse to
        # rehydrate a host here too, else an observer reading state() on a
        # released engine would silently rebuild hosts from disk and bypass the
        # resurrection guard. _ensure_started is a no-op on a running engine.
        await self._ensure_started()
        async with self._session_lock(session_id):
            host = self._get_or_create_host(session_id)
            surface = host.diagnostics()
            return self._to_surface(session_id, host, surface)

    async def reset(self, session_id: str) -> None:
        """Reset session to fresh state. Deletes persisted data."""
        async with self._session_lock(session_id):
            if session_id in self._hosts:
                del self._hosts[session_id]
            safe_name = safe_filename(session_id)
            for suffix in (".alpha.json", ".json"):
                state_file = self._data_dir / f"{safe_name}{suffix}"
                if state_file.exists():
                    state_file.unlink()

    async def destroy(self, session_id: str) -> None:
        """Permanently remove session state and release its lock."""
        await self.reset(session_id)
        if session_id in self._locks:
            del self._locks[session_id]

    async def inject(
        self,
        session_id: str,
        source: str,
        influence_type: str,
        intensity: float,
        target_dimension: str = "",
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Inject external influence into a session's hot pool.

        Other plugins call this to affect the emotional state of a session.
        For example, a memory plugin detecting contradiction with a previously
        reflected topic can re-ignite that material in the hot pool.

        Args:
            session_id: Target session identifier.
            source: Plugin identifier (e.g. "memory_plugin", "dialogue_agent").
            influence_type: One of "contradiction", "reinforcement", "revelation",
                           "betrayal", "validation".
            intensity: Influence strength [0, 1].
            target_dimension: Target dimension or material type in the hot pool.
            payload: Optional metadata dict passed through to the influence.

        Raises:
            ValueError: If influence_type is not a recognized type.
        """
        from .compute.hot_pool import _VALID_INFLUENCE_TYPES

        if influence_type not in _VALID_INFLUENCE_TYPES:
            raise ValueError(
                f"Invalid influence_type {influence_type!r}. "
                f"Must be one of: {', '.join(sorted(_VALID_INFLUENCE_TYPES))}"
            )
        await self._ensure_started()
        async with self._session_lock(session_id):
            host = self._get_or_create_host(session_id)
            from .compute.hot_pool import Influence

            influence = Influence(
                source=source,
                type=influence_type,  # type: ignore[arg-type]
                intensity=max(0.0, min(1.0, intensity)),
                target_dimension=target_dimension,
                payload=payload or {},
            )
            host.kernel.hot_pool.receive_influence(influence)

    def exists(self, session_id: str) -> bool:
        """Check if a session exists without creating it."""
        return session_id in self._hosts

    # --- shared instance registry ---

    @classmethod
    async def shared(
        cls,
        data_dir: str | Path,
        llm: Callable[[str, str], Awaitable[str]],
        embedding: Callable[[str], Awaitable[list[float]]] | None = None,
        config: SylanneConfig | None = None,
        *,
        assessor_llm: Callable[[str, str], Awaitable[str]] | None = None,
        plugin: str | None = None,
    ) -> SylanneEngine:
        """Return (and start) the process-shared engine for ``data_dir``.

        One engine per resolved data_dir is maintained for the process lifetime,
        so independent call sites can share a single instance without passing
        the object around — and one persistence directory is never owned by two
        engines at once WITHIN THIS PROCESS (which would cause lost updates on
        flush). This guarantee is per-process only: there is no cross-process
        lock, so running two OS processes on one data_dir will double-flush and
        lose updates — use one process per data_dir.

        When ``config`` is omitted, the engine self-reads it from
        ``<data_dir>/sylanne.config.json`` (one stable place users edit), so every
        plugin can just call ``shared(data_dir)`` and share the same settings. An
        ``assessor_model`` block in that file routes assessment to a small
        dedicated model; otherwise assessment uses the main ``llm``.

        Later calls with the same data_dir return the existing instance. A
        conflicting ``config`` raises SharedEngineConflictError; a different
        ``llm``/``embedding`` object logs a warning but reuses the original.
        The returned engine is already started (status == "running").

        Every co-resident plugin gets the SAME full engine — there is no
        driver/observer split. Call ``submit()`` (not ``process()``) so
        duplicate deliveries of the same message across plugins dedup instead
        of each paying for their own LLM call.

        Args:
            plugin: Optional caller identity string, purely for diagnostics —
                recorded in ``engine.participants()`` (first attach logged at
                INFO). Never gates behavior: identity observes, submit()'s
                idempotency guarantees.

        Warning: the shared engine is event-loop affine. Do not drive it from a
        different event loop than the one used for the first shared() call. Do
        NOT use ``async with`` on a shared instance — the first context exit
        would shut it down for all holders. Use release_shared() for teardown.
        """
        from ._sharing import get_shared_engine

        engine = await get_shared_engine(
            data_dir, llm, embedding=embedding, config=config, assessor_llm=assessor_llm
        )
        if plugin is not None:
            engine._note_participant(plugin)
        return engine

    @classmethod
    def peek_shared(cls, data_dir: str | Path) -> SylanneEngine | None:
        """Return the live shared engine for ``data_dir`` if one exists, else None.

        Public wrapper over the attach-only registry lookup: this NEVER builds
        or starts an engine — use it (or ``wait_shared``) for a pure-listener
        plugin that has no ``llm`` of its own and must never become the copy
        that constructs the engine.
        """
        from ._sharing import peek_shared_engine

        return peek_shared_engine(data_dir)

    @classmethod
    async def wait_shared(
        cls,
        data_dir: str | Path,
        *,
        timeout: float | None = None,
        interval: float = 0.5,
    ) -> SylanneEngine | None:
        """Poll for a shared engine on ``data_dir`` until one appears or timeout.

        For a listen-only plugin (no ``llm`` of its own) that may load before
        whichever co-resident plugin will eventually build the engine. This is
        a plain polling loop, not a wake-on-publish channel — a parked-future
        wakeup protocol was considered and rejected: it can leak or drop
        wakeups across vendored copies under different module names, while a
        0.5s default poll is imperceptible for a chat heartbeat and needs no
        new synchronization primitives shared across copies.

        Returns the engine as soon as ``peek_shared`` sees one. Returns
        ``None`` (after logging once at INFO) if ``timeout`` elapses with no
        engine ever appearing — correct by construction: nobody has declared
        compute for this data_dir yet.

        Args:
            timeout: Max seconds to wait. ``None`` waits forever.
            interval: Seconds between polls. Default 0.5s.
        """
        loop = asyncio.get_running_loop()
        deadline = None if timeout is None else loop.time() + timeout
        while True:
            engine = cls.peek_shared(data_dir)
            if engine is not None:
                return engine
            if deadline is not None and loop.time() >= deadline:
                logger.info(
                    "wait_shared(%s) timed out after %.1fs with no shared engine ever "
                    "appearing on this data_dir",
                    data_dir,
                    timeout,
                )
                return None
            await asyncio.sleep(interval)

    @classmethod
    async def release_shared(cls, data_dir: str | Path) -> None:
        """Shut down and remove the shared engine for ``data_dir``.

        Flushes all sessions to disk and frees the registry slot. After this
        returns, a subsequent shared() call for the same path creates a new
        engine. Call only when no other holder is still using the instance;
        wire this into your application's shutdown path (there is no atexit
        auto-flush — see module docs).
        """
        from ._sharing import release_shared_engine

        await release_shared_engine(data_dir)

    @classmethod
    def clear_shared_registry(cls) -> None:
        """Drop all shared registry entries without shutdown. TEST ISOLATION ONLY.

        DANGER: does NOT flush sessions — unpersisted state is lost and live
        engines are orphaned. Never call this in production; use release_shared()
        for real teardown. Safe to call from sync fixtures (no event loop needed).
        """
        from ._sharing import clear_shared_registry

        clear_shared_registry()

    @classmethod
    def is_shared(cls, data_dir: str | Path) -> bool:
        """Return True if a live shared engine is registered for ``data_dir``."""
        from ._sharing import is_shared

        return is_shared(data_dir)

    @classmethod
    def list_shared(cls) -> list[dict[str, str]]:
        """Snapshot of live shared engines: ``[{"data_dir", "status"}, ...]``.

        Diagnostic helper for spotting redundant engines across plugins sharing
        one process. Slots mid-teardown are omitted.
        """
        from ._sharing import list_shared

        return list_shared()

    @classmethod
    def shared_data_dir(cls, explicit: str | Path | None = None) -> Path:
        """Resolve the canonical host-shared ``data_dir`` for co-deployed plugins.

        Returns ``explicit`` if given, else ``$SYLANNE_DATA_DIR``, else
        ``~/.sylanne/shared`` — resolved and absolute, not created. Route every
        plugin's ``shared()`` call through this so independent plugins converge
        on ONE engine instead of each defaulting to its own directory (which
        would never dedup).
        """
        from ._sharing import resolve_shared_data_dir

        return resolve_shared_data_dir(explicit)

    # --- internal ---

    async def _notify(self, session_id: str, surface: Surface) -> None:
        for listener in self._listeners:
            try:
                ret = listener(session_id, surface)
                if asyncio.iscoroutine(ret) or asyncio.isfuture(ret):
                    await ret
            except Exception:
                logger.warning("Listener error", exc_info=True)

    def _session_lock(self, session_id: str) -> asyncio.Lock:
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()
        return self._locks[session_id]

    def _get_or_create_host(self, session_id: str) -> SylanneHost:
        if session_id not in self._hosts:
            from .compute import SylanneHost

            self._hosts[session_id] = SylanneHost(
                root=self._data_dir,
                session_key=session_id,
                profile=self._config.profile(),
                telemetry_sink=self._telemetry_sink,
                pel_enabled=self._config.pel_core_enabled,
            )
        return self._hosts[session_id]

    def _ctx_fingerprint(
        self,
        confidence: float | None,
        flags: list[str] | None,
        values: dict[str, float] | None,
    ) -> tuple[Any, ...]:
        """Hashable fingerprint of a submit() call's context, for divergence checks."""
        return (
            confidence,
            tuple(sorted(flags)) if flags else (),
            tuple(sorted((values or {}).items())),
        )

    def _prune_submissions(self) -> None:
        """Lazily evict stale/overflow completed entries from the dedup table.

        Runs at the top of every ``submit()`` call. Completed entries older
        than ``submit_window_seconds`` are evicted; beyond that, completed
        entries in excess of ``submit_max_entries`` are evicted oldest-first.
        IN-FLIGHT entries (``done_at is None``) are never touched by either
        rule — only a finished computation ages out.
        """
        cutoff = time.time() - self._config.submit_window_seconds
        seen: set[int] = set()
        completed: list[_Submission] = []
        for entry in list(self._submissions.values()):
            if id(entry) in seen:
                continue
            seen.add(id(entry))
            if entry.done_at is None:
                continue
            if entry.done_at < cutoff:
                self._evict_submission(entry)
            else:
                completed.append(entry)
        overflow = len(completed) - self._config.submit_max_entries
        if overflow > 0:
            completed.sort(key=lambda e: e.done_at or 0.0)
            for entry in completed[:overflow]:
                self._evict_submission(entry)

    def _evict_submission(self, entry: _Submission) -> None:
        """Remove every key of ``entry`` from the live table into the recent-evicted LRU."""
        for key in entry.keys:
            if self._submissions.get(key) is entry:
                del self._submissions[key]
            self._recent_evicted[key] = None
            self._recent_evicted.move_to_end(key)
        while len(self._recent_evicted) > self._config.submit_max_entries:
            self._recent_evicted.popitem(last=False)

    def _on_submission_done(self, task: asyncio.Task[Surface]) -> None:
        """Done-callback: stamp done_at, evict a failed task's keys immediately.

        Always retrieves a failed task's exception here so it is never
        reported as "exception never retrieved" even in the (rare) case where
        every awaiter's own await got cancelled before reaching the result.
        """
        for entry in {id(e): e for e in self._submissions.values()}.values():
            if entry.task is task:
                entry.done_at = time.time()
                if not task.cancelled() and task.exception() is not None:
                    # Poison must not stick for the rest of the window.
                    for key in entry.keys:
                        if self._submissions.get(key) is entry:
                            del self._submissions[key]
                break

    def _cancel_and_clear_submissions(self) -> None:
        """Cancel every in-flight submit() task and drop the dedup tables.

        Used on shutdown() and on loop-rebind (see ``_sharing.get_shared_engine``)
        — tasks created on a now-dead event loop cannot be awaited further, and
        letting a rebound engine keep pointing at them would hang the next
        ``submit()`` that tries to join. Cheap and idempotent.
        """
        for entry in {id(e): e for e in self._submissions.values()}.values():
            if not entry.task.done():
                entry.task.cancel()
        self._submissions.clear()
        self._recent_evicted.clear()

    def _note_participant(self, plugin: str) -> dict[str, Any]:
        """Register (or fetch) ``plugin``'s participants-registry entry.

        Diagnostics only — see ``participants()``/HARD RULE in module docs.
        Logs once at INFO on first attach for a given plugin name.
        """
        info = self._participants.get(plugin)
        if info is not None:
            return info
        try:
            import importlib

            from ._sharing import _self_identity

            copy_id = _self_identity().get("copy_id")
        except Exception:
            copy_id = None
        try:
            sdk_version = getattr(
                importlib.import_module(__package__ or "sylanne_core"), "__version__", "0+unknown"
            )
        except Exception:
            sdk_version = "0+unknown"
        info = {
            "copy_id": copy_id,
            "sdk_version": sdk_version,
            "first_seen": time.time(),
            "submits": 0,
            "joins": 0,
        }
        self._participants[plugin] = info
        logger.info("plugin %s attached to shared engine on %s", plugin, self._data_dir)
        return info

    def _note_submit_outcome(self, plugin: str | None, *, joined: bool) -> None:
        """Increment ``plugin``'s submits/joins counter, if identity was given.

        Diagnostics only: this is the only place submit() touches the
        participants registry, and it never branches submit()'s own dedup/join
        decision on anything read from it.
        """
        if plugin is None:
            return
        info = self._note_participant(plugin)
        if joined:
            info["joins"] += 1
        else:
            info["submits"] += 1

    def _build_telemetry_sink(self) -> DistillationSink | None:
        """Construct the shared distillation sink if opted in, else None.

        One sink per engine (a single append file) shared across all sessions.
        When the flag is off this returns None and the per-tick path stays
        zero-cost. Never raises into construction — a misconfigured sink
        disables collection rather than breaking the engine.
        """
        cfg = self._config
        if not cfg.training_data_sink:
            return None
        import secrets

        from .telemetry import DistillationSink

        base = self._data_dir / "telemetry"
        fname = Path(cfg.training_data_path or "distill_corpus.jsonl").name
        salt = cfg.training_data_salt
        if not salt:
            salt = secrets.token_hex(8)
            logger.warning(
                "training_data_salt is empty; using a per-process random salt — "
                "cross-run session grouping will be unstable"
            )
        try:
            return DistillationSink(
                enabled=True,
                path=base / (fname or "distill_corpus.jsonl"),
                salt=salt,
                base_dir=base,
            )
        except (OSError, ValueError):
            logger.warning(
                "could not open distillation sink; data collection disabled",
                exc_info=True,
            )
            return None

    async def _assess(self, text: str) -> dict[str, Any] | None:
        if not text.strip():
            return None
        try:
            from .assessor import assess_text

            result = await assess_text(text, self._assessor_llm or self._llm)
            if result and result.pop("_degraded", False):
                if self._status == "running":
                    self._status = "degraded"
            return result
        except Exception:
            if self._status == "running":
                self._status = "degraded"
            return None

    def _to_surface(self, session_id: str, host: SylanneHost, raw: dict[str, Any]) -> Surface:
        from .adapter import to_surface

        return to_surface(session_id, host, raw, diagnostics=self._config.diagnostics)
