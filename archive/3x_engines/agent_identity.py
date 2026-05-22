from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ConversationIdentity:
    """Stable identity extracted from an AstrBot turn for agent-state routing."""

    conversation_id: str
    speaker_id: str | None = None
    speaker_name: str | None = None
    group_id: str | None = None
    platform_id: str | None = None

    @property
    def has_speaker(self) -> bool:
        return bool(self.speaker_id)

    @property
    def speaker_track_id(self) -> str | None:
        if not self.speaker_id:
            return None
        return f"{self.conversation_id}::speaker:{self.speaker_id}"


def conversation_identity_from_event(
    event: Any,
    request: Any | None = None,
) -> ConversationIdentity:
    conversation_id = _first_text(
        _safe_attr(event, "unified_msg_origin"),
        _safe_attr(request, "session_id"),
        "global",
    )
    return ConversationIdentity(
        conversation_id=conversation_id,
        speaker_id=_sender_id(event),
        speaker_name=_sender_name(event),
        group_id=_group_id(event),
        platform_id=_platform_id(event),
    )


def _sender_id(event: Any) -> str | None:
    return _first_text(
        _safe_call(event, "get_sender_id"),
        _safe_attr(event, "sender_id"),
        _safe_attr(event, "user_id"),
        _nested_attr(event, ("message_obj", "sender", "user_id")),
        _nested_attr(event, ("message_obj", "sender", "sender_id")),
        _nested_attr(event, ("sender", "user_id")),
        _nested_attr(event, ("sender", "sender_id")),
    )


def _sender_name(event: Any) -> str | None:
    return _first_text(
        _safe_call(event, "get_sender_name"),
        _safe_attr(event, "sender_name"),
        _safe_attr(event, "nickname"),
        _nested_attr(event, ("message_obj", "sender", "nickname")),
        _nested_attr(event, ("message_obj", "sender", "name")),
        _nested_attr(event, ("sender", "nickname")),
        _nested_attr(event, ("sender", "name")),
    )


def _group_id(event: Any) -> str | None:
    return _first_text(
        _safe_call(event, "get_group_id"),
        _safe_attr(event, "group_id"),
        _nested_attr(event, ("message_obj", "group_id")),
    )


def _platform_id(event: Any) -> str | None:
    return _first_text(
        _safe_call(event, "get_platform_id"),
        _safe_attr(event, "platform_id"),
        _nested_attr(event, ("message_obj", "platform_id")),
    )


def _safe_call(value: Any, method_name: str) -> Any:
    method = getattr(value, method_name, None)
    if not callable(method):
        return None
    try:
        return method()
    except Exception:
        return None


def _safe_attr(value: Any, attr_name: str) -> Any:
    if value is None:
        return None
    return getattr(value, attr_name, None)


def _nested_attr(value: Any, path: tuple[str, ...]) -> Any:
    current = value
    for item in path:
        current = _safe_attr(current, item)
        if current is None:
            return None
    return current


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None
