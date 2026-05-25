"""Proactive speech scheduling logic extracted from main.py.

All methods delegate attribute access to the plugin instance via ``self._p``.
"""

from __future__ import annotations

import asyncio
from typing import Any

try:
    from astrbot.api import logger  # type: ignore
except ImportError:
    import logging as _logging

    logger = _logging.getLogger("astrbot_plugin_sylanne")  # type: ignore


class ProactiveScheduler:
    """Encapsulates proactive speech scheduling for the Sylanne plugin."""

    def __init__(self, plugin: Any) -> None:
        self._p = plugin

    # ------------------------------------------------------------------
    # Policy & feedback
    # ------------------------------------------------------------------

    def derive_dispatch_policy(
        self, decision: Any = None, *, session_key: str = "", **kwargs: Any
    ) -> dict[str, Any]:
        cfg = self._p.config or {}
        cooldown = float(cfg.get("proactive_speech_dispatch_cooldown_seconds", 1800.0))
        feedback_pressure = 0.0
        audit = getattr(self._p, "_proactive_dispatch_audit", None) or {}
        history = audit.get(session_key)
        if history:
            cold_count = sum(
                1
                for entry in history
                if entry.get("feedback_status") in ("cold_reply", "unanswered")
            )
            feedback_pressure = min(1.0, cold_count * 0.3)
            cooldown = cooldown * (1.0 + feedback_pressure)
        return {
            "should_dispatch": bool(cfg.get("enable_proactive_speech_dispatch")),
            "reason": "policy",
            "cooldown_seconds": cooldown,
            "feedback_pressure": feedback_pressure,
        }

    def observe_dispatch_feedback(self, session_key: str = "", **kwargs: Any) -> None:
        pass

    def should_exit_after_idle(self, session_key: str = "", **kwargs: Any) -> bool:
        return True

    # ------------------------------------------------------------------
    # Dispatch building & blocking
    # ------------------------------------------------------------------

    def build_dispatch_request(
        self,
        decision: Any = None,
        *,
        event_or_session: Any = None,
        session_key: str = "",
        candidate_context: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        cfg = self._p.config or {}
        topic_judgement = {}
        if isinstance(decision, dict):
            topic_judgement = decision.get("topic_judgement", {})
        message_text = topic_judgement.get("draft_message", "")
        min_idle = float(cfg.get("proactive_speech_min_idle_seconds", 300.0))
        return {
            "requested": True,
            "session_key": session_key,
            "message_text": message_text,
            "quiet_gate": {"min_idle_seconds": min_idle},
            "realtime_chat_plan": {"message_count": 1},
        }

    def dispatch_blocked_reason(
        self,
        decision: Any = None,
        dispatch: Any = None,
        *,
        event_or_session: Any = None,
        dry_run: bool = False,
        force: bool = False,
        **kwargs: Any,
    ) -> str:
        if force:
            return ""
        cfg = self._p.config or {}
        if not cfg.get("enable_proactive_speech_dispatch"):
            return "dispatch_disabled"
        now = (
            self._p._observed_now()
            if callable(self._p._observed_now)
            else self._p._observed_now
        )
        candidates = self._p._proactive_candidate_sessions
        sk = ""
        if event_or_session is not None:
            sk = str(getattr(event_or_session, "unified_msg_origin", "") or "")
        candidate = candidates.get(sk, {})
        last_seen = candidate.get("last_seen_at", 0.0)
        min_idle = float(
            (dispatch or {}).get("quiet_gate", {}).get("min_idle_seconds", 300.0)
        )
        if last_seen and (now - last_seen) < min_idle:
            return "recent_user_activity_quiet_period"
        last_sent = (getattr(self._p, "_proactive_dispatch_last_sent", None) or {}).get(
            sk, 0.0
        )
        cooldown = float(cfg.get("proactive_speech_dispatch_cooldown_seconds", 1800.0))
        if last_sent and (now - last_sent) < cooldown:
            return "cooldown_active"
        return ""

    # ------------------------------------------------------------------
    # Scheduler state & loop
    # ------------------------------------------------------------------

    def ensure_state(self) -> None:
        if not hasattr(self._p, "_proactive_scheduler_task"):
            self._p._proactive_scheduler_task: asyncio.Task | None = None
        if not hasattr(self._p, "_proactive_candidate_sessions"):
            self._p._proactive_candidate_sessions: dict[str, Any] = {}
        if not hasattr(self._p, "_proactive_scheduler_locks"):
            self._p._proactive_scheduler_locks: dict[str, asyncio.Lock] = {}

    async def run_once(self) -> dict[str, Any]:
        self.ensure_state()
        candidates = dict(self._p._proactive_candidate_sessions)
        checked = 0
        dispatched = 0
        for sk, info in candidates.items():
            checked += 1
            dispatch_fn = getattr(self._p, "request_proactive_speech_dispatch", None)
            if dispatch_fn and callable(dispatch_fn):
                event = (
                    info.get("event")
                    or type("_E", (), {"unified_msg_origin": sk, "session_id": sk})()
                )
                result = await dispatch_fn(event, dry_run=False)
                if result.get("dispatched"):
                    dispatched += 1
        return {"checked": checked, "dispatched": dispatched}

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    async def get_speech_decision(
        self,
        event_or_session: Any = None,
        *,
        session_key: str = "",
        now: float = 0.0,
        candidate_context: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        from sylanne_alpha.compat import proactive_decision

        sk = (
            session_key
            or (
                str(getattr(event_or_session, "unified_msg_origin", ""))
                if event_or_session
                else ""
            )
            or "default"
        )
        host = self._p._host(sk)
        surface = host.diagnostics()
        return proactive_decision(surface)

    async def request_dispatch(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {}

    async def judge_topic(self, session_key: str = "", **kwargs: Any) -> dict[str, Any]:
        return {"topic": "", "confidence": 0.0, "should_speak": False}
