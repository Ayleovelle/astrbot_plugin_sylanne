"""Sylanne-Embodiment: Shadow Memory subsystem.

Extracted from body.py to reduce God Object complexity.
Tracks implicit conversational signals (interruptions, corrections,
followups, jokes, boundaries, repairs) and produces advisory state indices.
"""
from __future__ import annotations

from typing import Any

from .vector import clamp as _clamp


SHADOW_MEMORY_SCHEMA_VERSION = "sylanne.alpha.shadow_memory.v1"


class ShadowMemory:
    """Manages shadow signal observation and state computation."""

    __slots__ = ("_events",)

    def __init__(self, events: list[dict[str, Any]] | None = None) -> None:
        self._events: list[dict[str, Any]] = [dict(e) for e in (events or []) if isinstance(e, dict)][-24:]

    @property
    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    @events.setter
    def events(self, value: list[dict[str, Any]]) -> None:
        self._events = [dict(e) for e in value if isinstance(e, dict)][-24:]

    def observe_signal(self, *, text: str = "", flags: list[str] | None = None, kind: str = "") -> None:
        flags = list(flags or [])
        text = str(text or "").strip()
        signal_kind = kind or shadow_kind(text, flags)
        if not signal_kind:
            return
        self._events.append({"kind": signal_kind, "weight": round(shadow_weight(signal_kind), 6)})
        self._events = self._events[-24:]

    def state(self) -> dict[str, Any]:
        events = list(self._events)[-24:]
        counts = _count_events(events)
        pressure = _clamp((counts["interruption_count"] + counts["correction_count"] + counts["followup_count"] + counts["repair_count"]) / 8.0)
        boundary_need = _clamp((counts["boundary_count"] + counts["correction_count"]) / 6.0)
        return {
            "schema_version": SHADOW_MEMORY_SCHEMA_VERSION,
            "kind": "shadow_memory",
            "internal_only": True,
            "read_only": True,
            "public_api_eligible": False,
            "signals": counts,
            "state_index": {
                "repair_pressure": round(pressure, 6),
                "boundary_need": round(boundary_need, 6),
                "risk_impulse": round(max(pressure, boundary_need) * 0.5, 6),
            },
            "memory_gate": {
                "long_term_fact_count": 0,
                "common_ground_count": counts["joke_or_bit_count"],
                "correction_count": counts["correction_count"],
                "uncertain_count": max(0, len(events) - sum(counts.values())),
            },
            "summary": shadow_summary(counts),
            "constraints": ["advisory_only", "no_raw_text", "not_a_fact", "current_user_text_priority", "bounded_recent_events_only"],
        }

    def to_raw(self) -> dict[str, Any]:
        """Return raw dict for body.memory['shadow'] serialization."""
        return {"events": [dict(e) for e in self._events]}

    @classmethod
    def from_raw(cls, data: dict[str, Any] | None) -> "ShadowMemory":
        """Restore from body.memory['shadow'] dict."""
        if not isinstance(data, dict):
            return cls()
        events = data.get("events", [])
        if not isinstance(events, list):
            return cls()
        return cls(events=events)


def _count_events(events: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "interruption_count": 0,
        "correction_count": 0,
        "followup_count": 0,
        "joke_or_bit_count": 0,
        "boundary_count": 0,
        "repair_count": 0,
    }
    for event in events:
        kind = str(event.get("kind") or "")
        if kind == "interruption":
            counts["interruption_count"] += 1
        if kind == "correction":
            counts["correction_count"] += 1
        if kind == "followup":
            counts["followup_count"] += 1
        if kind == "joke_or_bit":
            counts["joke_or_bit_count"] += 1
        if kind == "boundary":
            counts["boundary_count"] += 1
        if kind == "repair":
            counts["repair_count"] += 1
    return counts


def shadow_kind(text: str, flags: list[str]) -> str:
    flag_set = set(flags)
    lowered = text.lower()
    if "interrupted" in flag_set or "unfinished_reply" in flag_set:
        return "interruption"
    if "followup" in flag_set or any(marker in text for marker in ("接着", "继续", "刚才", "没说完", "上面", "前面")):
        return "followup"
    if "correction" in flag_set or any(marker in text for marker in ("不是", "不对", "错了", "理解错", "你误会", "别当成")):
        return "correction"
    if "joke" in flag_set or any(marker in text for marker in ("谐音", "玩笑", "梗", "只是逗", "开玩笑")) or "joke" in lowered:
        return "joke_or_bit"
    if "boundary" in flag_set or any(marker in text for marker in ("别", "不要", "停", "边界")):
        return "boundary"
    if "repair" in flag_set or any(marker in text for marker in ("道歉", "修复", "补救")):
        return "repair"
    return ""


def shadow_weight(kind: str) -> float:
    return {"interruption": 0.8, "correction": 0.9, "followup": 0.7, "joke_or_bit": 0.45, "boundary": 0.75, "repair": 0.65}.get(kind, 0.35)


def shadow_summary(counts: dict[str, int]) -> str:
    if counts["correction_count"]:
        return "用户纠正过理解，旧记忆只能作背景。"
    if counts["interruption_count"] or counts["followup_count"]:
        return "存在未完成承接信号，下一轮应自然续接但不解释内部原因。"
    if counts["joke_or_bit_count"]:
        return "存在玩笑或共同语境信号，不能写成长期事实。"
    return "暂无明显 shadow 压力。"
