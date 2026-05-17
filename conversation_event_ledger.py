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
