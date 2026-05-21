from __future__ import annotations

import hashlib
from typing import Any

DIALOGUE_SCHEMA_VERSION = "sylanne.alpha.dialogue.v1"

_TOPIC_SHIFT_MARKERS = ("换个话题", "另外", "对了", "服务器", "卡死", "报错", "bug")
_CONTINUATION_MARKERS = ("还有", "而且", "然后", "就是", "也", "继续")


def segment_dialogue(
    *,
    session_key: str,
    text: str = "",
    now: float = 0.0,
    previous: dict[str, Any] | None = None,
    flags: list[str] | None = None,
    reply_in_progress: bool = False,
) -> dict[str, Any]:
    flags = list(flags or [])
    normalized = " ".join(str(text or "").split())
    previous_id = str((previous or {}).get("segment_id") or "")
    relation = _relation(normalized, previous=previous, flags=flags)
    segment_id = previous_id if previous_id and relation == "continuation" else _segment_id(session_key, normalized, now)
    interruption = _interruption(relation, reply_in_progress=reply_in_progress)
    actions = ["cancel_realtime_dispatch"] if interruption["detected"] and reply_in_progress else []
    return {
        "schema_version": DIALOGUE_SCHEMA_VERSION,
        "session_key": session_key,
        "segment_id": segment_id,
        "relation": relation,
        "message_time": now,
        "features": {
            "chars": len(normalized),
            "short_fragment": len(normalized) <= 24,
            "topic_shift": relation == "topic_shift",
            "withdrawal": relation == "withdrawal",
        },
        "interruption": interruption,
        "actions": actions,
        "text_preview": normalized[:80],
    }


def _relation(text: str, *, previous: dict[str, Any] | None, flags: list[str]) -> str:
    if "withdrawal" in flags:
        return "withdrawal"
    if any(marker in text for marker in _TOPIC_SHIFT_MARKERS):
        return "topic_shift"
    if previous and (len(text) <= 24 or any(marker in text for marker in _CONTINUATION_MARKERS)):
        return "continuation"
    return "new_segment"


def _interruption(relation: str, *, reply_in_progress: bool) -> dict[str, Any]:
    if relation == "withdrawal":
        return {"detected": True, "reason": "message_withdrawal"}
    if reply_in_progress and relation == "topic_shift":
        return {"detected": True, "reason": "user_topic_shift_during_reply"}
    return {"detected": False, "reason": "none"}


def _segment_id(session_key: str, text: str, now: float) -> str:
    seed = f"{session_key}\0{text}\0{now:.3f}".encode("utf-8")
    return "seg-" + hashlib.blake2s(seed, digest_size=6).hexdigest()


__all__ = ["DIALOGUE_SCHEMA_VERSION", "segment_dialogue"]
