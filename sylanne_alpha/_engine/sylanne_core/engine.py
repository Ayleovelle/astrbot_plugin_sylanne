"""SylanneEngine — the public entry point for Sylanne-Core SDK.

Provides the async API for integrating affective computation into chatbots.
Designed as an AstrBot plugin dependency: downstream plugins call get_engine()
to obtain a pre-configured instance.

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
    ) -> None:
        self._data_dir = Path(data_dir)
        self._llm = llm
        self._embedding = embedding
        self._config = config or SylanneConfig()
        self._status: EngineStatus = "init"
        self._hosts: dict[str, SylanneHost] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._listeners: list[Callable[[str, Surface], Any]] = []

    @property
    def status(self) -> EngineStatus:
        return self._status

    async def start(self) -> None:
        """Initialize the engine. Must be called before process/tick."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._status = "running"

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
        for host in self._hosts.values():
            try:
                host.flush()
            except Exception:
                if self._status == "running":
                    self._status = "degraded"
        self._hosts.clear()
        self._locks.clear()
        self._status = "closed"

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

        Returns:
            Surface dict with keys: state, decision, guard, personality, memory, dynamics.
        """
        if self._status == "closed":
            await self.start()
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
        if self._status == "closed":
            await self.start()
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
        if self._status == "closed":
            await self.start()
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
            )
        return self._hosts[session_id]

    async def _assess(self, text: str) -> dict[str, Any] | None:
        if not text.strip():
            return None
        try:
            from .assessor import assess_text

            result = await assess_text(text, self._llm)
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
