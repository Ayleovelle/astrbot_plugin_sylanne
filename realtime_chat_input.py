from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


PUBLIC_REALTIME_INPUT_SCHEMA_VERSION = "astrbot.realtime_input_fragments.v1"

_WHITESPACE_RE = re.compile(r"\s+")
_CLOSING_PUNCTUATION_RE = re.compile(r"[。！？!?~～…]+$")
_QUESTION_PARTICLES = {"吗", "嘛", "么", "呢", "不", "吧"}
_CONTINUATION_PREFIXES = {
    "不是",
    "不对",
    "就是",
    "我是说",
    "刚刚",
    "那个",
    "这",
    "那",
}


@dataclass(frozen=True)
class RealtimeInputSettings:
    enabled: bool = True
    max_window_seconds: float = 3.2
    max_fragments: int = 6
    max_fragment_chars: int = 18
    injection_max_chars: int = 520


@dataclass(frozen=True)
class RealtimeInputFragment:
    text: str
    speaker_key: str
    observed_at: float
    kind: str


def observe_realtime_input_fragment(
    windows: dict[str, dict[str, Any]],
    *,
    session_key: str,
    speaker_key: str,
    text: str,
    now: float,
    settings: RealtimeInputSettings | None = None,
) -> dict[str, Any]:
    settings = settings or RealtimeInputSettings()
    session = str(session_key or "global")
    speaker = str(speaker_key or "unknown")
    normalized = normalize_input_fragment_text(text)
    if not settings.enabled or not normalized:
        windows.pop(session, None)
        return _empty_payload(session, speaker, reason="disabled_or_empty")

    if not _is_fragment_candidate(normalized, settings):
        windows.pop(session, None)
        return _empty_payload(session, speaker, reason="not_fragment_candidate")

    fragment = RealtimeInputFragment(
        text=normalized,
        speaker_key=speaker,
        observed_at=float(now),
        kind=classify_input_fragment(normalized),
    )
    previous = windows.get(session)
    if not _can_extend_window(previous, fragment, settings):
        windows[session] = _window_from_fragment(session, fragment)
        return _empty_payload(session, speaker, reason="window_started")

    fragments = list(previous.get("fragments") or [])
    fragments.append(fragment)
    fragments = fragments[-max(2, int(settings.max_fragments)) :]
    previous["fragments"] = fragments
    previous["updated_at"] = fragment.observed_at

    if not _should_emit_window(fragments, settings):
        return _empty_payload(session, speaker, reason="waiting_for_more_fragments")

    windows.pop(session, None)
    sequence = [item.text for item in fragments]
    merged = merge_input_fragments(sequence)
    return {
        "schema_version": PUBLIC_REALTIME_INPUT_SCHEMA_VERSION,
        "kind": "realtime_user_message_fragments",
        "should_inject": True,
        "session_key": session,
        "speaker_key": speaker,
        "fragment_count": len(sequence),
        "fragments": sequence,
        "display_sequence": " / ".join(sequence),
        "merged_intent": merged,
        "started_at": fragments[0].observed_at,
        "updated_at": fragments[-1].observed_at,
        "elapsed_seconds": round(max(0.0, fragments[-1].observed_at - fragments[0].observed_at), 6),
        "reason": "short_interval_fragment_turn",
    }


def build_realtime_input_fragment_injection(
    payload: dict[str, Any],
    *,
    max_chars: int = 520,
) -> str:
    if not payload.get("should_inject"):
        return ""
    lines = [
        "[sylanne_user_message_fragments]",
        "同一用户在很短时间内分多条发送；请把下面碎片当作同一轮用户意图，而不是逐条误读或只回应最后一条。",
        "fragment_count={count}; elapsed_seconds={elapsed}; schema={schema}".format(
            count=int(payload.get("fragment_count") or 0),
            elapsed=payload.get("elapsed_seconds", 0),
            schema=str(payload.get("schema_version") or PUBLIC_REALTIME_INPUT_SCHEMA_VERSION),
        ),
        "fragments={sequence}".format(
            sequence=str(payload.get("display_sequence") or ""),
        ),
        "merged_intent={merged}".format(
            merged=str(payload.get("merged_intent") or ""),
        ),
    ]
    text = "\n".join(lines).strip()
    limit = max(160, int(max_chars))
    if len(text) <= limit:
        return text
    return text[:limit].rstrip()


def normalize_input_fragment_text(text: str) -> str:
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    value = _WHITESPACE_RE.sub(" ", value)
    return value.strip()


def classify_input_fragment(text: str) -> str:
    value = normalize_input_fragment_text(text)
    if not value:
        return "empty"
    if all(not ch.isalnum() and not "\u4e00" <= ch <= "\u9fff" for ch in value):
        return "symbol_or_emoji"
    if len(value) <= 2:
        return "short_word"
    if _looks_like_closing_fragment(value):
        return "closing"
    if any(value.startswith(prefix) for prefix in _CONTINUATION_PREFIXES):
        return "continuation"
    return "short_text"


def merge_input_fragments(fragments: list[str]) -> str:
    cleaned = [normalize_input_fragment_text(item) for item in fragments]
    cleaned = [item for item in cleaned if item]
    return " ".join(cleaned).strip()


def _empty_payload(session_key: str, speaker_key: str, *, reason: str) -> dict[str, Any]:
    return {
        "schema_version": PUBLIC_REALTIME_INPUT_SCHEMA_VERSION,
        "kind": "realtime_user_message_fragments",
        "should_inject": False,
        "session_key": session_key,
        "speaker_key": speaker_key,
        "reason": reason,
    }


def _window_from_fragment(
    session_key: str,
    fragment: RealtimeInputFragment,
) -> dict[str, Any]:
    return {
        "schema_version": PUBLIC_REALTIME_INPUT_SCHEMA_VERSION,
        "kind": "realtime_user_message_fragment_window",
        "session_key": session_key,
        "speaker_key": fragment.speaker_key,
        "started_at": fragment.observed_at,
        "updated_at": fragment.observed_at,
        "fragments": [fragment],
    }


def _can_extend_window(
    previous: dict[str, Any] | None,
    fragment: RealtimeInputFragment,
    settings: RealtimeInputSettings,
) -> bool:
    if not previous:
        return False
    if str(previous.get("speaker_key") or "") != fragment.speaker_key:
        return False
    fragments = previous.get("fragments")
    if not isinstance(fragments, list) or not fragments:
        return False
    last = fragments[-1]
    last_time = float(getattr(last, "observed_at", previous.get("updated_at", 0.0)) or 0.0)
    if fragment.observed_at - last_time > max(0.4, float(settings.max_window_seconds)):
        return False
    return True


def _should_emit_window(
    fragments: list[RealtimeInputFragment],
    settings: RealtimeInputSettings,
) -> bool:
    if len(fragments) < 2:
        return False
    if len(fragments) >= max(2, int(settings.max_fragments)):
        return True
    if len(fragments) < 3:
        return False
    return _looks_like_closing_fragment(fragments[-1].text)


def _is_fragment_candidate(text: str, settings: RealtimeInputSettings) -> bool:
    value = normalize_input_fragment_text(text)
    if not value:
        return False
    if "\n" in value:
        return False
    max_chars = max(2, int(settings.max_fragment_chars))
    if len(value) <= max_chars:
        return True
    return any(value.startswith(prefix) for prefix in _CONTINUATION_PREFIXES) and len(value) <= max_chars + 8


def _looks_like_closing_fragment(text: str) -> bool:
    value = normalize_input_fragment_text(text)
    if not value:
        return False
    if _CLOSING_PUNCTUATION_RE.search(value):
        return True
    return value in _QUESTION_PARTICLES or value[-1] in _QUESTION_PARTICLES
