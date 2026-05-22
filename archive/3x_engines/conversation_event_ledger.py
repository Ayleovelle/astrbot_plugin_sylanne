from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import hashlib
from collections import deque


PUBLIC_RELATIONAL_TIME_LAYER_SCHEMA_VERSION = "astrbot.relational_time_layer.v1"


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


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: Any, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, _as_float(value, lower)))


def _event_epoch(event: LedgerEvent) -> float:
    payload = event.event_time if isinstance(event.event_time, dict) else {}
    epoch = payload.get("epoch")
    if epoch is None:
        epoch = payload.get("event_epoch")
    return _as_float(epoch, 0.0)


def _event_time_payload(event: LedgerEvent) -> dict[str, Any]:
    payload = event.event_time if isinstance(event.event_time, dict) else {}
    result: dict[str, Any] = {}
    epoch = _event_epoch(event)
    if epoch:
        result["epoch"] = epoch
    local_time = str(payload.get("local_time") or payload.get("event_local_time") or "").strip()
    timezone = str(payload.get("timezone") or payload.get("event_timezone") or "").strip()
    if local_time:
        result["local_time"] = _head_text(local_time, 80)
    if timezone:
        result["timezone"] = _head_text(timezone, 64)
    return result


def _interpretation_types(event: LedgerEvent) -> list[str]:
    types = []
    for item in event.interpretations:
        if not isinstance(item, dict):
            continue
        value = str(item.get("type") or item.get("kind") or "").strip()
        if value and value not in {"none", "relationship_candidate_summary"} and value not in types:
            types.append(value)
    if event.topic_state == "corrected" and "correction" not in types:
        types.append("correction")
    return types[:4]


def _candidate_type(self_interpretation: dict[str, Any]) -> str:
    if not isinstance(self_interpretation, dict):
        return ""
    candidate = self_interpretation.get("turning_point_candidate")
    if not isinstance(candidate, dict):
        return ""
    value = str(candidate.get("type") or "").strip()
    if value in {"", "none"}:
        return ""
    return value


def build_relational_time_layer(
    events,
    *,
    session_key: str | None = None,
    self_interpretation: dict[str, Any] | None = None,
    relationship_candidate_summary: dict[str, Any] | None = None,
    now: float | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    selected = [event for event in list(events or []) if isinstance(event, LedgerEvent)]
    if session_key is not None:
        selected = [event for event in selected if event.session_key == session_key]
    selected = selected[-max(1, int(limit)):]
    epochs = [_event_epoch(event) for event in selected if _event_epoch(event) > 0.0]
    start_epoch = min(epochs) if epochs else 0.0
    end_epoch = max(epochs) if epochs else _as_float(now, 0.0)
    duration = max(0.0, end_epoch - start_epoch) if start_epoch and end_epoch else 0.0
    turning_types: list[str] = []
    event_payloads = []
    for event in selected:
        event_types = _interpretation_types(event)
        for event_type in event_types:
            if event_type not in turning_types:
                turning_types.append(event_type)
        event_payloads.append(
            {
                "event_id": str(event.event_id or ""),
                "session_key": str(event.session_key or "global"),
                "role": str(event.role or ""),
                "topic_state": str(event.topic_state or ""),
                "delivery_status": str(event.delivery_status or ""),
                "event_time": _event_time_payload(event),
                "turning_point_types": event_types,
                "evidence": {
                    "message_length": len(str(event.raw_text or event.normalized_text or "")),
                    "has_media_summary": bool(event.media_summary),
                    "has_quote_summary": bool(event.quote_summary),
                },
            },
        )
    candidate_type = _candidate_type(self_interpretation or {})
    if candidate_type and candidate_type not in turning_types:
        turning_types.append(candidate_type)
    relationship_confidence = _clamp((relationship_candidate_summary or {}).get("confidence"))
    signal_count = len(turning_types) + sum(1 for event in selected if event.topic_state in {"corrected", "needs_followup"})
    weight = _clamp(0.18 * signal_count + 0.28 * relationship_confidence + min(duration / 7200.0, 1.0) * 0.18)
    phase = "low_signal"
    if weight >= 0.62:
        phase = "active_continuity"
    elif weight >= 0.32:
        phase = "forming_continuity"
    return {
        "schema_version": PUBLIC_RELATIONAL_TIME_LAYER_SCHEMA_VERSION,
        "kind": "relational_time_layer",
        "internal_only": True,
        "read_only": True,
        "public_api_eligible": False,
        "span": {
            "event_count": len(selected),
            "start_epoch": start_epoch,
            "end_epoch": end_epoch,
            "duration_seconds": round(duration, 6),
        },
        "continuity": {
            "phase": phase,
            "relationship_time_weight": round(weight, 6),
            "turning_point_types": turning_types[:8],
            "relationship_candidate_confidence": round(relationship_confidence, 6),
        },
        "events": event_payloads,
        "constraints": [
            "internal_research_signal_only",
            "bounded_recent_events_only",
            "not_a_relationship_fact",
            "does_not_override_current_user_text",
        ],
    }
