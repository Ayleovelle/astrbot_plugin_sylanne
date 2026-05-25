from __future__ import annotations

import re
from typing import Any

from .commands import command_surface, memory_surface, reset_surface

REALTIME_PLAN_SCHEMA_VERSION = "sylanne.alpha.realtime_plan.v1"
SIMULATION_SCHEMA_VERSION = "sylanne.alpha.compat.simulation.v1"


def emotion_values(host: Any) -> dict[str, float]:
    values = command_surface(host, "emotion")["values"]
    return {
        "warmth": float(values["warmth"]),
        "pulse": float(values["pulse"]),
        "expression": float(values["expression"]),
        "repair": float(values["repair"]),
    }


def build_memory_payload(host: Any, query: str = "", limit: int = 5) -> dict[str, Any]:
    payload = memory_surface(host, query=query, limit=limit)
    payload["prompt_fragment"] = _safe_prompt_fragment(host)
    return payload


def inject_context(host: Any, request: Any) -> Any:
    fragment = _safe_prompt_fragment(host)
    current = str(getattr(request, "prompt", "") or "")
    setattr(request, "prompt", f"{current}\n{fragment}".strip())
    return request


def _safe_prompt_fragment(host: Any) -> str:
    diagnostics = host.diagnostics()
    payload = diagnostics["host_payload"]
    relationship = (
        payload.get("relationship_memory", {})
        if isinstance(payload.get("relationship_memory"), dict)
        else {}
    )
    continuity = (
        relationship.get("continuity", {})
        if isinstance(relationship.get("continuity"), dict)
        else {}
    )
    personality = (
        payload.get("personality", {})
        if isinstance(payload.get("personality"), dict)
        else {}
    )
    voice = (
        personality.get("voice", {})
        if isinstance(personality.get("voice"), dict)
        else {}
    )
    return "\n".join(
        [
            "[retrieved_conversation_context]",
            f"（{_relationship_summary(str(continuity.get('phase', 'low_signal')), float(continuity.get('weight') or 0.0))}）",
            f"（{_voice_summary(str(voice.get('cadence', 'steady')), str(voice.get('boundary', 'clear')))}）",
        ]
    )


def _relationship_summary(phase: str, weight: float) -> str:
    if phase in {"stable", "warm", "established"} or weight >= 0.45:
        return "你们已经有一些连续互动，可以自然承接，但不要替用户下结论。"
    if phase not in {"", "none", "low_signal"} or weight >= 0.12:
        return "已有少量上下文线索，可以轻微参考，仍以眼前问题为准。"
    return "可用上下文很少，把这轮当作当前问题来处理。"


def _voice_summary(cadence: str, boundary: str) -> str:
    style = (
        "语速放慢一点，短句之间保留停顿感"
        if cadence in {"slow_burn", "slow", "gentle"}
        else "表达保持清楚，不要堆太多设定"
    )
    guard = "，边界感要清楚" if boundary in {"strong", "clear"} else ""
    return f"{style}{guard}。"


def simulate_update(
    host: Any,
    *,
    text: str = "",
    flags: list[str] | None = None,
    confidence: float = 0.5,
) -> dict[str, Any]:
    body = host.kernel.body
    event = body.event_vector(text=text, flags=list(flags or []), confidence=confidence)
    simulated = body.simulate_vectors([event])
    return {
        "schema_version": SIMULATION_SCHEMA_VERSION,
        "session_key": host.session_key,
        "event": event,
        "vector": simulated,
    }


def strip_draft_blocks(text: str) -> str:
    cleaned = str(text or "")
    for tag in ("draft_notes", "thinking", "think"):
        cleaned = re.sub(rf"(?is)<{tag}[^>]*>.*?</{tag}>", "", cleaned)
    lines = cleaned.replace("\r\n", "\n").split("\n")
    visible: list[str] = []
    hidden_tag: str | None = None
    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()
        opening = re.fullmatch(r"<([a-z_]+)[^>]*>", lower)
        closing = re.fullmatch(r"</([a-z_]+)>", lower)
        if opening and opening.group(1) in {"draft_notes", "thinking", "think"}:
            hidden_tag = opening.group(1)
            continue
        if closing and closing.group(1) == hidden_tag:
            hidden_tag = None
            continue
        if hidden_tag is None:
            visible.append(line)
    return "\n".join(visible).strip()


def realtime_plan(
    session_key: str,
    text: str,
    *,
    max_part_chars: int = 48,
    chars_per_second: float = 7.5,
) -> dict[str, Any]:
    raw = str(text or "")
    visible = strip_draft_blocks(raw)
    parts = _split_text(visible, max_part_chars=max_part_chars)
    return {
        "schema_version": REALTIME_PLAN_SCHEMA_VERSION,
        "kind": "realtime_chat_plan",
        "session_key": session_key,
        "enabled": True,
        "message_count": len(parts),
        "message_parts": _message_parts(parts, chars_per_second=chars_per_second),
        "source_text_chars": len(raw),
    }


def _message_parts(
    parts: list[str], *, chars_per_second: float = 7.5
) -> list[dict[str, Any]]:
    raw_delays = [
        _typing_delay(previous, chars_per_second=chars_per_second)
        for previous, _ in _previous_and_current(parts)
    ]
    budget = min(36.0, max(0.0, (len(parts) - 1) * 3.2))
    total = sum(raw_delays)
    scale = 1.0 if total <= budget or total <= 0 else budget / total
    return [
        {
            "index": index,
            "text": part,
            "delay_before_seconds": round(min(4.2, delay * scale), 3),
        }
        for index, (part, delay) in enumerate(zip(parts, raw_delays, strict=True))
    ]


def _previous_and_current(parts: list[str]) -> list[tuple[str, str]]:
    return [
        (parts[index - 1] if index > 0 else "", part)
        for index, part in enumerate(parts)
    ]


def _typing_delay(previous_text: str, *, chars_per_second: float = 7.5) -> float:
    if not previous_text:
        return 0.0
    visible_chars = sum(1 for char in str(previous_text) if not char.isspace())
    punctuation_pause = (
        0.75
        if str(previous_text).rstrip().endswith(("。", "！", "？", ".", "!", "?"))
        else 0.35
    )
    return round(
        min(4.2, max(0.8, visible_chars / chars_per_second + punctuation_pause)), 3
    )


def realtime_dispatch(session_key: str, text: str) -> dict[str, Any]:
    plan = realtime_plan(session_key, text)
    return {
        "kind": "realtime_chat_dispatch",
        "session_key": session_key,
        "sent": bool(plan["message_parts"]),
        "plan": plan,
    }


def proactive_decision(surface: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "proactive_decision",
        "schema_version": surface["schema_version"],
        "session_key": surface["session_key"],
        "action": surface["decision"]["action"],
        "allowed": surface["guard"]["allowed"],
        "reason": surface["host_payload"]["reason"],
        "host_payload": surface["host_payload"],
    }


def _split_text(text: str, *, max_part_chars: int) -> list[str]:
    if not text:
        return []
    fragments = [
        part.strip() for part in text.replace("\r\n", "\n").split("\n") if part.strip()
    ]
    if not fragments:
        fragments = [text.strip()]
    parts: list[str] = []
    for fragment in fragments:
        parts.extend(
            _merge_short_parts(
                _split_fragment(fragment, max_part_chars=max_part_chars),
                max_part_chars=max_part_chars,
            )
        )
    return parts


def _split_fragment(text: str, *, max_part_chars: int) -> list[str]:
    pieces: list[str] = []
    remaining = text.strip()
    while remaining:
        if len(remaining) <= max_part_chars:
            pieces.append(remaining)
            break
        split_at = _split_index(remaining, max_part_chars=max_part_chars)
        if _would_split_protected_ascii_token(remaining, split_at):
            pieces.append(remaining)
            break
        pieces.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    return pieces


def _merge_short_parts(parts: list[str], *, max_part_chars: int) -> list[str]:
    merged: list[str] = []
    for part in parts:
        if not part:
            continue
        if merged and _should_merge_with_previous(
            merged[-1], part, max_part_chars=max_part_chars
        ):
            merged[-1] = f"{merged[-1]}{part}"
        else:
            merged.append(part)
    return merged


def _should_merge_with_previous(
    previous: str, current: str, *, max_part_chars: int
) -> bool:
    if len(previous) + len(current) > max_part_chars:
        return False
    return _is_too_short_part(current) or len(previous) + len(current) <= max(
        14, max_part_chars // 2
    )


def _is_too_short_part(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    return len(stripped) <= 4 and all(not char.isspace() for char in stripped)


def _split_index(text: str, *, max_part_chars: int) -> int:
    window = text[:max_part_chars]
    semantic = _preferred_split_index(window, "。！？!?；;")
    if semantic is not None:
        return semantic
    soft = _preferred_split_index(window, "，、,：:")
    if soft is not None:
        return soft
    for index in range(len(window) - 1, max(0, max_part_chars // 2) - 1, -1):
        if window[index].isspace() and _safe_ascii_boundary(text, index):
            return index + 1
    for index in range(len(window) - 1, max(0, max_part_chars // 2) - 1, -1):
        if _safe_cjk_boundary(text, index):
            return index
    return max_part_chars


def _preferred_split_index(window: str, delimiters: str) -> int | None:
    for index in range(len(window) - 1, max(0, len(window) // 2) - 1, -1):
        if window[index] in delimiters:
            return index + 1
    return None


def _safe_ascii_boundary(text: str, index: int) -> bool:
    previous_char = text[index - 1] if index > 0 else ""
    next_char = text[index + 1] if index + 1 < len(text) else ""
    return not (_is_ascii_token_char(previous_char) and _is_ascii_token_char(next_char))


def _safe_cjk_boundary(text: str, index: int) -> bool:
    if index <= 0 or index >= len(text):
        return False
    previous_char = text[index - 1]
    next_char = text[index]
    if _is_ascii_token_char(previous_char) or _is_ascii_token_char(next_char):
        return False
    return not _ascii_token_crosses_boundary(text, index)


def _ascii_token_crosses_boundary(text: str, index: int) -> bool:
    if index <= 0 or index >= len(text):
        return False
    return _is_ascii_token_char(text[index - 1]) and _is_ascii_token_char(text[index])


def _is_ascii_token_char(char: str) -> bool:
    return bool(char) and (
        char.isascii() and (char.isalnum() or char in ":/_?&=.-#%+_")
    )


def _protected_ascii_prefix_length(text: str) -> int:
    index = 0
    while index < len(text) and _is_ascii_token_char(text[index]):
        index += 1
    return index


def _would_split_protected_ascii_token(text: str, split_at: int) -> bool:
    if split_at <= 0 or split_at >= len(text):
        return False
    return _is_ascii_token_char(text[split_at - 1]) and _is_ascii_token_char(
        text[split_at]
    )


__all__ = [
    "build_memory_payload",
    "command_surface",
    "emotion_values",
    "inject_context",
    "memory_surface",
    "proactive_decision",
    "realtime_dispatch",
    "realtime_plan",
    "reset_surface",
    "simulate_update",
    "strip_draft_blocks",
]
