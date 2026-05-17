from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import hashlib
from collections import deque


@dataclass
class LedgerEvent:
    event_id: str
    session_key: str
    speaker_key: str = ""
    role: str = "user"
    raw_text: str = ""
    normalized_text: str = ""
    media_summary: str = ""
    quote_summary: str = ""
    event_time: dict[str, Any] = field(default_factory=dict)
    delivery_status: str = ""
    topic_state: str = "open"
    interpretations: list[dict[str, Any]] = field(default_factory=list)
    memory_gate: dict[str, Any] = field(default_factory=dict)


def stable_event_id(session_key: str, role: str, text: str, epoch: Any) -> str:
    payload = "\n".join([session_key, role, text, str(epoch)])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


class ConversationEventLedger:
    def __init__(self, max_events_per_session: int = 24) -> None:
        self.max_events_per_session = max_events_per_session
        self._events_by_session: dict[str, deque[LedgerEvent]] = {}

    def record(self, event: LedgerEvent) -> None:
        events = self._events_by_session.setdefault(
            event.session_key, deque(maxlen=self.max_events_per_session)
        )
        events.append(event)

    def recent(self, session_key: str, *, limit: int | None = None) -> list[LedgerEvent]:
        events = list(self._events_by_session.get(session_key, deque()))
        if limit is not None:
            return events[-limit:]
        return events

    def clear(self, session_key: str | None = None) -> None:
        if session_key is None:
            self._events_by_session.clear()
        else:
            self._events_by_session.pop(session_key, None)


def _head_text(text: str, limit: int = 160) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)] + "…"


def looks_like_user_correction(text: str) -> bool:
    markers = ("不是", "不对", "我没说", "我没讲", "没有说", "没有讲", "你理解错", "你误会")
    return any(marker in text for marker in markers) or "什么时候和你说" in text or "谁跟你说" in text


def looks_like_explicit_prior_reference(text: str) -> bool:
    markers = (
        "刚才你说",
        "刚刚你说",
        "你刚才说",
        "你刚刚说",
        "刚才那个",
        "刚才那句",
        "刚才那段",
        "上一句",
        "上一段",
        "上一轮",
        "再说一遍",
        "重复一遍",
        "接着说",
        "接上",
        "续上",
        "说完",
        "没说完",
        "那句话",
        "这句话",
        "那段话",
        "这段话",
        "刚才的话",
        "刚刚的话",
        "对他们说",
        "想对他们说",
        "same topic continues",
        "what did you say",
        "say that again",
        "repeat that",
    )
    return any(marker in text.lower() for marker in markers)


def audit_shadow_lifecycle(
    previous_assistant_text: str,
    current_user_text: str,
    delivery_status: str,
    has_interrupted_breakpoint: bool,
) -> dict[str, Any]:
    previous_excerpt = _head_text(previous_assistant_text)
    if has_interrupted_breakpoint or delivery_status == "interrupted":
        return {
            "topic_state": "needs_followup",
            "should_inject_shadow": True,
            "release_reason": "interrupted_reply_breakpoint",
            "previous_assistant_excerpt": previous_excerpt,
        }

    if looks_like_user_correction(current_user_text):
        return {
            "topic_state": "corrected",
            "should_inject_shadow": True,
            "release_reason": "user_correction_or_source_query",
            "previous_assistant_excerpt": previous_excerpt,
        }

    if looks_like_explicit_prior_reference(current_user_text):
        return {
            "topic_state": "needs_followup",
            "should_inject_shadow": True,
            "release_reason": "explicit_prior_reference",
            "previous_assistant_excerpt": previous_excerpt,
        }

    return {
        "topic_state": "completed",
        "should_inject_shadow": False,
        "release_reason": "delivered_topic_completed",
        "previous_assistant_excerpt": previous_excerpt,
    }


def build_ledger_summary(events, limit: int = 5) -> str:
    selected = list(events)[-limit:]
    lines = [
        "[sylanne_event_ledger_summary]",
        "audit-only bounded recent events ledger; does not override AstrBot native context.",
    ]
    for event in selected:
        parts = [f"{event.role}"]
        if event.delivery_status:
            parts.append(f"status={event.delivery_status}")
        if event.topic_state:
            parts.append(f"topic={event.topic_state}")
        lines.append("; ".join(parts))
        if event.raw_text:
            lines.append(event.raw_text)
    return "\n".join(lines)
