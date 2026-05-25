"""Session management logic extracted from main.py.

Provides SessionContext which encapsulates session key derivation,
per-session lock management, host lifecycle, and memory system hydration.
All methods delegate attribute access to the plugin instance via ``self._p``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

try:
    from astrbot.api import logger  # type: ignore
except ImportError:
    import logging as _logging

    logger = _logging.getLogger("astrbot_plugin_sylanne")  # type: ignore

from sylanne_alpha.host import SylanneAlphaHost
from sylanne_alpha.memory_system import ConversationBuffer, MemorySystem


class SessionContext:
    """Encapsulates session management for the Sylanne plugin."""

    def __init__(self, plugin: Any) -> None:
        self._p = plugin

    # ------------------------------------------------------------------
    # Session key derivation
    # ------------------------------------------------------------------

    def session_key(self, event: Any = None, session_key: str = "") -> str:
        if session_key:
            return session_key
        if event is not None:
            base = str(
                getattr(event, "session_id", "")
                or getattr(event, "unified_msg_origin", "")
                or "default"
            )
            # For group chats, include sender_id so each user gets an
            # independent host/kernel/computation spine.
            sender_id = str(
                getattr(event, "sender_id", "") or getattr(event, "user_id", "") or ""
            )
            if sender_id and base != "default":
                return f"{base}:{sender_id}"
            return base
        return "default"

    # ------------------------------------------------------------------
    # Per-session lock
    # ------------------------------------------------------------------

    def session_lock(self, session_key: str) -> asyncio.Lock:
        if session_key not in self._p._session_locks:
            self._p._session_locks[session_key] = asyncio.Lock()
        return self._p._session_locks[session_key]

    # ------------------------------------------------------------------
    # Safe session key (filesystem-safe)
    # ------------------------------------------------------------------

    def safe_session_key(self, session_key: str) -> str:
        cache = getattr(self._p, "_safe_session_key_cache", None)
        if cache is None:
            self._p._safe_session_key_cache = {}
            cache = self._p._safe_session_key_cache
        if session_key in cache:
            return cache[session_key]
        safe = session_key.replace("/", "_").replace("\\", "_")
        cache[session_key] = safe
        return safe

    # ------------------------------------------------------------------
    # Public session key resolution
    # ------------------------------------------------------------------

    def resolve_public_session_key(
        self, event: Any = None, *, request: Any = None, session_key: str = ""
    ) -> str:
        if session_key:
            return session_key
        if event is not None:
            if isinstance(event, str):
                return event
            umo = getattr(event, "unified_msg_origin", None)
            if umo:
                return str(umo)
        if request is not None:
            sid = getattr(request, "session_id", None)
            if sid:
                return str(sid)
        return "global"

    # ------------------------------------------------------------------
    # Memory system helpers
    # ------------------------------------------------------------------

    def memory_system_for_session(self, session_key: str) -> MemorySystem:
        if not session_key:
            session_key = "default"
        systems = getattr(self._p, "_memory_systems", None)
        if systems is None:
            self._p._memory_systems = {}
            systems = self._p._memory_systems
        if session_key not in systems:
            systems[session_key] = MemorySystem()
        return systems[session_key]

    def memory_system_has_content(self, memory_system: Any) -> bool:
        if memory_system is None:
            return False
        return bool(
            list(getattr(memory_system, "_l1", []) or [])
            or list(getattr(memory_system, "_l2", []) or [])
            or dict(getattr(memory_system, "_l3_nodes", {}) or {})
            or list(getattr(memory_system, "_l3_edges", []) or [])
        )

    def hydrate_memory_system_from_body_traces(
        self, session_key: str, memory_system: MemorySystem, traces: Any
    ) -> None:
        if self.memory_system_has_content(memory_system):
            return
        for trace in list(traces or [])[-50:]:
            if not isinstance(trace, dict):
                continue
            text = str(trace.get("text") or "").strip()
            if not text:
                continue
            try:
                temperature = float(
                    trace.get("temperature", trace.get("warmth", 0.5)) or 0.5
                )
            except (TypeError, ValueError):
                temperature = 0.5
            memory_system.write(
                text=text,
                embedding=trace.get("embedding"),
                temperature=max(0.0, min(1.0, temperature)),
            )
            if memory_system._l1:
                item = memory_system._l1[-1]
                try:
                    item.weight = max(
                        0.0, min(1.0, float(trace.get("weight", 1.0) or 1.0))
                    )
                except (TypeError, ValueError):
                    item.weight = 1.0
                try:
                    created_at = float(
                        trace.get("created_at", trace.get("updated_at", 0.0)) or 0.0
                    )
                    if created_at > 0:
                        item.created_at = created_at
                except (TypeError, ValueError):
                    pass

    # ------------------------------------------------------------------
    # Known WebUI sessions
    # ------------------------------------------------------------------

    def known_webui_sessions(self, requested: str = "") -> list[str]:
        sessions: list[str] = []

        def add(value: Any) -> None:
            text = str(value or "").strip()
            if text and text not in sessions:
                sessions.append(text)

        add(requested)
        for key in getattr(self._p, "_hosts", {}).keys():
            add(key)
        for key in getattr(self._p, "_memory_systems", {}).keys():
            add(key)
        cache = self._p._sylanne_memory_cache
        if isinstance(cache, dict):
            for key in cache.keys():
                add(key)
        for host in list(getattr(self._p, "_hosts", {}).values()):
            runtime = getattr(host, "runtime", None)
            export_all = getattr(runtime, "export_all", None)
            if not callable(export_all):
                continue
            try:
                exported = export_all()
            except Exception:
                continue
            persisted = (
                exported.get("sessions", {}) if isinstance(exported, dict) else {}
            )
            if isinstance(persisted, dict):
                for key in persisted.keys():
                    add(key)
        try:
            cfg = (
                self._p.config
                if hasattr(self._p, "_config")
                else getattr(self._p, "config", {}) or {}
            )
            root = Path(
                str(cfg.get("sylanne_alpha_root") or Path.home() / ".sylanne_alpha")
            )
            if root.exists():
                for path in root.glob("*.alpha.json"):
                    add(path.name[: -len(".alpha.json")])
        except Exception as e:
            logger.debug(f"Sylanne skip: {e}")
        if not sessions:
            add("default")
        return sessions

    # ------------------------------------------------------------------
    # Host management
    # ------------------------------------------------------------------

    def host(self, session_key: str) -> SylanneAlphaHost:
        if not session_key:
            session_key = "default"
        if not hasattr(self._p, "_hosts"):
            self._p._hosts = {}
        if session_key not in self._p._hosts:
            # LRU eviction: persist and remove oldest host if over limit
            if len(self._p._hosts) >= self._p._MAX_HOSTS:
                oldest_key = next(iter(self._p._hosts))
                old_host = self._p._hosts.pop(oldest_key)
                self._p._persist_kernel_sync(oldest_key, old_host)
            cfg = (
                self._p.config
                if hasattr(self._p, "_config")
                else getattr(self._p, "config", {}) or {}
            )
            root = cfg.get("sylanne_alpha_root") or str(Path.home() / ".sylanne_alpha")
            host = SylanneAlphaHost(root=root, session_key=session_key)
            # Share encoder across all hosts to save memory
            plugin_cls = type(self._p)
            if plugin_cls._shared_encoder is None:
                plugin_cls._shared_encoder = host.kernel.computation.encoder
            else:
                host.kernel.computation.replace_encoder(plugin_cls._shared_encoder)
            # Derive memory system params from personality
            personality = (
                host.kernel._personality()
                if hasattr(host.kernel, "_personality")
                else {}
            )
            memory_system = self.memory_system_for_session(session_key)
            if personality and isinstance(personality, dict):
                memory_system.derive_params(personality)
            # Restore memory system state if previously persisted
            mem_data = host.kernel.body.memory.get("_memory_system")
            if mem_data and isinstance(mem_data, dict):
                memory_system.from_dict(mem_data)
            if not self.memory_system_has_content(memory_system):
                self.hydrate_memory_system_from_body_traces(
                    session_key,
                    memory_system,
                    host.kernel.body.memory.get("traces", []),
                )
                if self.memory_system_has_content(memory_system):
                    host.kernel.body.memory["_memory_system"] = memory_system.to_dict()
                    self._p._persist_kernel_sync(session_key, host)
            self._p._hosts[session_key] = host
            # Restore conversation buffer (file fallback; KV kept in sync)
            if session_key not in self._p._conversation_buffers:
                buf_data = host.runtime.load_buffer(session_key)
                if buf_data and isinstance(buf_data, dict):
                    self._p._conversation_buffers[session_key] = (
                        ConversationBuffer.from_dict(buf_data)
                    )
        else:
            # Touch: move to end for LRU ordering
            host = self._p._hosts.pop(session_key)
            self._p._hosts[session_key] = host
        return self._p._hosts[session_key]
