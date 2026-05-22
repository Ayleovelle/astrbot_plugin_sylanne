from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


PUBLIC_REALTIME_INPUT_SCHEMA_VERSION = "astrbot.realtime_input_fragments.v1"

_WHITESPACE_RE = re.compile(r"\s+")
_CLOSING_PUNCTUATION_RE = re.compile(r"[。！？!?~～…]+$")
_QUESTION_PARTICLES = {"吗", "嘛", "么", "呢", "不", "吧"}
_QUESTION_MARKERS = (
    "为什么",
    "为啥",
    "怎么",
    "怎样",
    "咋",
    "哪里",
    "哪儿",
    "哪",
    "谁",
    "什么",
    "几",
    "多少",
    "是否",
    "是不是",
    "有没有",
    "吗",
    "嘛",
    "么",
    "呢",
    "从哪",
    "看来的",
)
_COMPLETION_LIKELY_MARKERS = (
    "就是这样",
    "大概这样",
    "就这样",
    "说完了",
    "没了",
    "以上",
)
_HANGING_CLAUSE_MARKERS = (
    "是为了",
    "为了",
    "因为",
    "所以",
    "然后",
    "接着",
    "以及",
    "而且",
    "但是",
    "可是",
    "让你",
    "让你更",
    "更好地去",
)
_STANDALONE_SHORT_REPLIES = {
    "好",
    "好的",
    "嗯",
    "嗯嗯",
    "行",
    "可以",
    "ok",
    "OK",
    "谢谢",
    "谢了",
    "不用",
    "不了",
    "没事",
    "知道了",
    "明白",
    "明白了",
}
_CONTINUATION_PREFIXES = {
    "不是",
    "不对",
    "就是",
    "我是说",
    "我说的是",
    "我的意思是",
    "刚刚",
    "那个",
}
_SETUP_PREFIXES = {
    "你要",
    "我只是",
    "我就是",
    "我就",
    "我有点",
    "我觉得",
    "我想说",
    "我还",
    "其实",
    "等一下",
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

    if _looks_like_standalone_short_reply(normalized):
        windows.pop(session, None)
        return _empty_payload(session, speaker, reason="standalone_short_reply")

    fragment = RealtimeInputFragment(
        text=normalized,
        speaker_key=speaker,
        observed_at=float(now),
        kind=classify_input_fragment(normalized),
    )
    previous = windows.get(session)
    if _can_extend_window(previous, fragment, settings):
        if not _can_append_to_existing_window(normalized, settings):
            windows.pop(session, None)
            return _empty_payload(session, speaker, reason="not_fragment_candidate")
        fragments = list(previous.get("fragments") or [])
        fragments.append(fragment)
        fragments.sort(key=lambda item: float(getattr(item, "observed_at", 0.0) or 0.0))
        fragments = fragments[-max(2, int(settings.max_fragments)) :]
        previous["fragments"] = fragments
        previous["started_at"] = fragments[0].observed_at
        previous["updated_at"] = fragments[-1].observed_at

        if not _should_emit_window(fragments, settings):
            sequence = [item.text for item in fragments]
            return _empty_payload(
                session,
                speaker,
                reason="waiting_for_more_fragments",
                should_hold=True,
                fragments=sequence,
                merged_intent=merge_input_fragments(sequence),
            )

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

    if not _should_start_fragment_window(normalized, settings):
        windows.pop(session, None)
        return _empty_payload(session, speaker, reason="not_fragment_candidate")

    if not _can_extend_window(previous, fragment, settings):
        windows[session] = _window_from_fragment(session, fragment)
        return _empty_payload(
            session,
            speaker,
            reason="window_started",
            should_hold=True,
            fragments=[fragment.text],
            merged_intent=fragment.text,
        )

    return _empty_payload(session, speaker, reason="not_fragment_candidate")


def build_realtime_input_hold_injection(
    payload: dict[str, Any],
    *,
    max_chars: int = 360,
) -> str:
    if not payload.get("should_hold"):
        return ""
    lines = [
        "[sylanne_user_message_fragments_waiting]",
        "用户可能正在把一句话分多条发送；当前不要把这些碎片当作完整语义。",
        "reason={reason}; fragment_count={count}".format(
            reason=str(payload.get("reason") or ""),
            count=len(payload.get("fragments") or []),
        ),
        "fragments={sequence}".format(
            sequence=str(payload.get("display_sequence") or ""),
        ),
        "partial_intent={merged}".format(
            merged=str(payload.get("merged_intent") or ""),
        ),
    ]
    text = "\n".join(lines).strip()
    limit = max(120, int(max_chars))
    if len(text) <= limit:
        return text
    return text[:limit].rstrip()


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
        "如果当前 prompt 只包含最后一个碎片，请以 merged_intent 理解用户真正想说的话。",
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


def _empty_payload(
    session_key: str,
    speaker_key: str,
    *,
    reason: str,
    should_hold: bool = False,
    fragments: list[str] | None = None,
    merged_intent: str = "",
) -> dict[str, Any]:
    payload = {
        "schema_version": PUBLIC_REALTIME_INPUT_SCHEMA_VERSION,
        "kind": "realtime_user_message_fragments",
        "should_inject": False,
        "should_hold": bool(should_hold),
        "session_key": session_key,
        "speaker_key": speaker_key,
        "reason": reason,
    }
    if fragments:
        payload["fragments"] = fragments
        payload["display_sequence"] = " / ".join(fragments)
    if merged_intent:
        payload["merged_intent"] = merged_intent
    return payload


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
    semantic_wait_until = float(previous.get("semantic_wait_until") or 0.0)
    if semantic_wait_until > 0.0 and fragment.observed_at <= semantic_wait_until:
        return True
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
    if _has_hanging_tail(fragments[-1].text):
        return False
    if _has_hanging_tail(fragments[-2].text) and not _looks_like_clause_completion(
        fragments[-1].text,
    ):
        return False
    if _has_hanging_tail(fragments[-2].text) and _looks_like_clause_completion(
        fragments[-1].text,
    ):
        return True
    if _looks_like_closing_fragment(fragments[-1].text):
        return True
    merged = merge_input_fragments([item.text for item in fragments])
    if _looks_like_semantic_question(merged):
        return True
    return any(marker in merged for marker in _COMPLETION_LIKELY_MARKERS)


def _is_fragment_candidate(text: str, settings: RealtimeInputSettings) -> bool:
    value = normalize_input_fragment_text(text)
    if not value:
        return False
    if "\n" in value:
        return False
    return _should_start_fragment_window(value, settings) or _can_append_to_existing_window(
        value,
        settings,
    )


def _should_start_fragment_window(text: str, settings: RealtimeInputSettings) -> bool:
    value = normalize_input_fragment_text(text)
    if not value or "\n" in value or _looks_like_standalone_short_reply(value):
        return False
    compact = _compact_fragment_text(value)
    max_chars = max(2, int(settings.max_fragment_chars))
    if _looks_like_complete_correction(value):
        return False
    if len(compact) <= 4:
        return True
    if all(not ch.isalnum() and not "\u4e00" <= ch <= "\u9fff" for ch in value):
        return True
    if _CLOSING_PUNCTUATION_RE.search(value) and len(compact) <= 8:
        return True
    if any(value.startswith(prefix) for prefix in _CONTINUATION_PREFIXES):
        return len(value) <= max_chars + 8
    if any(value.startswith(prefix) for prefix in _SETUP_PREFIXES):
        return len(value) <= max_chars + 8
    if _has_hanging_tail(value):
        return len(value) <= max_chars + 10
    return False


def _can_append_to_existing_window(text: str, settings: RealtimeInputSettings) -> bool:
    value = normalize_input_fragment_text(text)
    if not value or "\n" in value:
        return False
    max_chars = max(2, int(settings.max_fragment_chars))
    if len(value) <= max_chars:
        return True
    if any(value.startswith(prefix) for prefix in _CONTINUATION_PREFIXES | _SETUP_PREFIXES):
        return len(value) <= max_chars + 8
    if _has_hanging_tail(value):
        return len(value) <= max_chars + 10
    return _looks_like_semantic_question(value) and len(value) <= max_chars + 8


def _looks_like_closing_fragment(text: str) -> bool:
    value = normalize_input_fragment_text(text)
    if not value:
        return False
    if _CLOSING_PUNCTUATION_RE.search(value):
        return True
    return value in _QUESTION_PARTICLES or value[-1] in _QUESTION_PARTICLES


def _looks_like_standalone_short_reply(text: str) -> bool:
    value = normalize_input_fragment_text(text)
    if not value:
        return False
    compact = _compact_fragment_text(value)
    if compact in _STANDALONE_SHORT_REPLIES:
        return True
    return compact.lower() in {item.lower() for item in _STANDALONE_SHORT_REPLIES}


def _looks_like_semantic_question(text: str) -> bool:
    value = normalize_input_fragment_text(text)
    if not value:
        return False
    if "?" in value or "？" in value:
        return True
    return any(marker in value for marker in _QUESTION_MARKERS)


def _looks_like_complete_correction(text: str) -> bool:
    value = normalize_input_fragment_text(text)
    if not any(value.startswith(prefix) for prefix in _CONTINUATION_PREFIXES):
        return False
    return ("，" in value or "," in value or "。" in value) and len(_compact_fragment_text(value)) > 5


def _has_hanging_tail(text: str) -> bool:
    value = normalize_input_fragment_text(text)
    compact = _compact_fragment_text(value)
    if not compact:
        return False
    if compact in {"是为了", "为了", "因为", "所以", "然后", "接着", "以及", "而且", "但是", "可是"}:
        return True
    return any(compact.endswith(marker) for marker in _HANGING_CLAUSE_MARKERS)


def _looks_like_clause_completion(text: str) -> bool:
    value = normalize_input_fragment_text(text)
    compact = _compact_fragment_text(value)
    if not compact:
        return False
    if _looks_like_closing_fragment(value):
        return True
    if compact.endswith(("呀", "啊", "哦", "呢", "嘛", "啦", "了", "吧")) and len(compact) >= 3:
        return True
    return len(compact) >= 5 and not _has_hanging_tail(value)


def _compact_fragment_text(text: str) -> str:
    return re.sub(r"[。！？!?~～…，,、\s]+", "", normalize_input_fragment_text(text))
