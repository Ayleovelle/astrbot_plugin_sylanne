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
import logging
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .compute import SylanneHost
    from .telemetry import DistillationSink

from .compute.utils import safe_filename
from .config import SylanneConfig
from .types import EngineStatus, HealthStatus, Surface

logger = logging.getLogger("sylanne_core")


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
        """
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

    async def tick(
        self,
        session_id: str,
        flags: list[str] | None = None,
    ) -> Surface:
        """Advance session state without user input (background heartbeat)."""
        await self._ensure_started()
        async with self._session_lock(session_id):
            host = self._get_or_create_host(session_id)
            event = {
                "text": "",
                "confidence": 0.0,
                "flags": flags or ["idle"],
                "now": time.time(),
                "values": {},
            }
            result = host.on_request(event)
            return self._to_surface(session_id, host, result)

    async def state(self, session_id: str) -> Surface:
        """Get current session state without advancing the pipeline."""
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

        Warning: the shared engine is event-loop affine. Do not drive it from a
        different event loop than the one used for the first shared() call. Do
        NOT use ``async with`` on a shared instance — the first context exit
        would shut it down for all holders. Use release_shared() for teardown.
        """
        from ._sharing import get_shared_engine

        return await get_shared_engine(
            data_dir, llm, embedding=embedding, config=config, assessor_llm=assessor_llm
        )

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
