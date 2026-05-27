"""Sylanne-Embodiment: 影子记忆子系统。

从 body.py 中提取，减少 God Object 复杂度。
追踪隐式对话信号（打断、纠正、续接、玩笑、边界、修复），
并产生建议性状态指标。

设计理念：
- 影子记忆不存储事实，只存储"对话动力学信号"
- 输出仅为建议性（advisory_only），不直接影响回复内容
- 用于帮助系统感知对话中的隐含压力和边界需求

与其他组件的关系：
- 被 body.py 的主循环调用 observe_signal()
- 输出的 state() 供计算栈参考（修复压力、边界需求等）
- 不直接写入长期记忆，只影响当前轮的决策参考
"""

from __future__ import annotations

from typing import Any

from .vector import clamp as _clamp

SHADOW_MEMORY_SCHEMA_VERSION = "sylanne.alpha.shadow_memory.v1"


class ShadowMemory:
    """管理影子信号的观察和状态计算。

    维护最近 24 条隐式信号事件，计算修复压力、边界需求等指标。
    这些指标是"建议性"的——告诉系统"可能需要注意什么"，
    但不强制改变行为。
    """

    __slots__ = ("_events",)

    def __init__(self, events: list[dict[str, Any]] | None = None) -> None:
        # 只保留最近 24 条事件，防止无限增长
        self._events: list[dict[str, Any]] = [
            dict(e) for e in (events or []) if isinstance(e, dict)
        ][-24:]

    @property
    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    @events.setter
    def events(self, value: list[dict[str, Any]]) -> None:
        self._events = [dict(e) for e in value if isinstance(e, dict)][-24:]

    def observe_signal(
        self, *, text: str = "", flags: list[str] | None = None, kind: str = ""
    ) -> None:
        """观察一个隐式信号并记录。

        参数:
            text: 用户消息文本（用于关键词检测信号类型）
            flags: 外部标记列表（如 "interrupted"、"correction" 等）
            kind: 直接指定信号类型（优先于自动检测）
        """
        flags = list(flags or [])
        text = str(text or "").strip()
        # 优先使用显式指定的 kind，否则从文本和 flags 自动推断
        signal_kind = kind or shadow_kind(text, flags)
        if not signal_kind:
            return
        self._events.append(
            {"kind": signal_kind, "weight": round(shadow_weight(signal_kind), 6)}
        )
        self._events = self._events[-24:]

    def state(self) -> dict[str, Any]:
        """计算当前影子记忆状态，返回完整的状态报告。

        返回字典包含：
        - signals: 各类信号的计数
        - state_index: 修复压力、边界需求、风险冲动
        - memory_gate: 记忆门控信息（哪些可以写入长期记忆）
        - summary: 人类可读的状态摘要
        - constraints: 使用约束列表
        """
        events = list(self._events)[-24:]
        counts = _count_events(events)
        # 修复压力：打断+纠正+续接+修复的累积，归一化到 [0,1]
        pressure = _clamp(
            (
                counts["interruption_count"]
                + counts["correction_count"]
                + counts["followup_count"]
                + counts["repair_count"]
            )
            / 8.0
        )
        # 边界需求：边界信号+纠正的累积
        boundary_need = _clamp(
            (counts["boundary_count"] + counts["correction_count"]) / 6.0
        )
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
            "constraints": [
                "advisory_only",
                "no_raw_text",
                "not_a_fact",
                "current_user_text_priority",
                "bounded_recent_events_only",
            ],
        }

    def to_raw(self) -> dict[str, Any]:
        """序列化为原始字典，用于 body.memory['shadow'] 持久化。"""
        return {"events": [dict(e) for e in self._events]}

    @classmethod
    def from_raw(cls, data: dict[str, Any] | None) -> "ShadowMemory":
        """从 body.memory['shadow'] 字典恢复实例。"""
        if not isinstance(data, dict):
            return cls()
        events = data.get("events", [])
        if not isinstance(events, list):
            return cls()
        return cls(events=events)


def _count_events(events: list[dict[str, Any]]) -> dict[str, int]:
    """统计各类信号的出现次数。"""
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
    """从文本和标记推断影子信号类型。

    检测优先级：打断 > 续接 > 纠正 > 玩笑 > 边界 > 修复。
    使用中文关键词匹配，覆盖常见的隐式对话信号表达。

    参数:
        text: 用户消息文本
        flags: 外部标记列表

    返回:
        信号类型字符串，无法识别时返回空字符串
    """
    flag_set = set(flags)
    lowered = text.lower()
    if "interrupted" in flag_set or "unfinished_reply" in flag_set:
        return "interruption"
    if "followup" in flag_set or any(
        marker in text for marker in ("接着", "继续", "刚才", "没说完", "上面", "前面")
    ):
        return "followup"
    if "correction" in flag_set or any(
        marker in text
        for marker in ("不是", "不对", "错了", "理解错", "你误会", "别当成")
    ):
        return "correction"
    if (
        "joke" in flag_set
        or any(marker in text for marker in ("谐音", "玩笑", "梗", "只是逗", "开玩笑"))
        or "joke" in lowered
    ):
        return "joke_or_bit"
    if "boundary" in flag_set or any(
        marker in text for marker in ("别", "不要", "停", "边界")
    ):
        return "boundary"
    if "repair" in flag_set or any(
        marker in text for marker in ("道歉", "修复", "补救")
    ):
        return "repair"
    return ""


def shadow_weight(kind: str) -> float:
    """返回各类信号的权重（影响力大小）。

    权重越高表示该信号对系统状态的影响越大。
    纠正(0.9)最重，因为它意味着系统理解出错。
    """
    return {
        "interruption": 0.8,
        "correction": 0.9,
        "followup": 0.7,
        "joke_or_bit": 0.45,
        "boundary": 0.75,
        "repair": 0.65,
    }.get(kind, 0.35)


def shadow_summary(counts: dict[str, int]) -> str:
    """根据信号计数生成人类可读的状态摘要。

    按优先级返回最重要的一条摘要信息。
    """
    if counts["correction_count"]:
        return "用户纠正过理解，旧记忆只能作背景。"
    if counts["interruption_count"] or counts["followup_count"]:
        return "存在未完成承接信号，下一轮应自然续接但不解释内部原因。"
    if counts["joke_or_bit_count"]:
        return "存在玩笑或共同语境信号，不能写成长期事实。"
    return "暂无明显 shadow 压力。"
