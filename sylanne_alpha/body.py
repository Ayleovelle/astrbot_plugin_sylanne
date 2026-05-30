"""身体状态模型模块。

定义 Sylanne-Embodiment 的完整身体状态数据结构，包含 8 个子系统：
- 脉搏 (Pulse): 心跳计数、节律稳定性、应激负荷
- 血流 (Bloodflow): 温暖感、循环活力、记忆流动
- 神经 (Nerve): 可塑性、敏感度、阈值漂移
- 肌肉 (Muscle): 准备度、疲劳、训练延伸
- 温度 (Temperature): 温暖、波动性、修复热
- 伤口 (Wound): 开放伤口、修复进度、疤痕、敏感度
- 免疫 (Immunity): 边界压力、主权、中断预算、冷却、暂停
- 死亡率 (Mortality): 负荷、耗竭、恢复债务

核心职责：
- 维护 29 维状态向量的读写
- 通过 apply() 方法接收事件并演化状态
- 管理记忆 traces（短期记忆池）
- 提供关系记忆和影子记忆的观测接口
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .attention import attention_delta
from .shadow_memory import (
    ShadowMemory,
)
from .vector import EVENT_AXES, STATE_AXES, linear_delta
from .vector import clamp as _clamp

SCHEMA_VERSION = "sylanne.alpha.body.v1"
RELATIONSHIP_MEMORY_SCHEMA_VERSION = "sylanne.alpha.relationship_memory.v1"


@dataclass(slots=True)
class AlphaPulseState:
    """脉搏子系统状态。

    模拟心跳节律，反映交互频率和应激水平。
    - beat: 累计心跳数（单调递增，代表交互历史长度）
    - rhythm: 节律稳定性 [0,1]，hurt 事件会降低
    - strain: 应激负荷 [0,1]，边界/伤害事件会升高
    - last_tick: 上次状态更新的时间戳
    """

    beat: float = 0.0
    rhythm: float = 0.5
    strain: float = 0.0
    last_tick: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "beat": round(self.beat, 6),
            "rhythm": round(self.rhythm, 6),
            "strain": round(self.strain, 6),
            "last_tick": round(self.last_tick, 6),
        }


@dataclass(slots=True)
class AlphaBloodflowState:
    """血流子系统状态。

    模拟情感温度和记忆循环。
    - warmth: 关系温暖感 [0,1]，safe 事件升高，hurt 降低
    - circulation: 循环活力 [0,1]，有文本交互时升高
    - memory_flow: 记忆流动强度 [0,1]，随 traces 数量和可塑性增长
    """

    warmth: float = 0.4
    circulation: float = 0.0
    memory_flow: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "warmth": round(self.warmth, 6),
            "circulation": round(self.circulation, 6),
            "memory_flow": round(self.memory_flow, 6),
        }


@dataclass(slots=True)
class AlphaNerveState:
    """神经子系统状态。

    模拟学习能力和感知阈值。
    - plasticity: 可塑性 [0,1]，交互越多越高，决定探索倾向
    - sensitivity: 敏感度 [0,1]，hurt 事件升高
    - repetition: 当前文本的重复次数（整数）
    - threshold_drift: 阈值漂移 [0,1]，重复刺激导致脱敏
    """

    plasticity: float = 0.0
    sensitivity: float = 0.0
    repetition: int = 0
    threshold_drift: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "plasticity": round(self.plasticity, 6),
            "sensitivity": round(self.sensitivity, 6),
            "repetition": self.repetition,
            "threshold_drift": round(self.threshold_drift, 6),
        }


@dataclass(slots=True)
class AlphaMuscleState:
    """肌肉子系统状态。

    模拟行动准备度和疲劳。
    - readiness: 行动准备度 [0,1]，有文本时升高，空闲时降低
    - fatigue: 疲劳度 [0,1]，高接触需求时累积
    - trained_reach: 训练延伸 [0,1]，重复交互逐渐增长
    """

    readiness: float = 0.2
    fatigue: float = 0.0
    trained_reach: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "readiness": round(self.readiness, 6),
            "fatigue": round(self.fatigue, 6),
            "trained_reach": round(self.trained_reach, 6),
        }


@dataclass(slots=True)
class AlphaTemperatureState:
    """温度子系统状态。

    模拟情感温度和修复热量。
    - warmth: 情感温暖 [0,1]，safe 升高，hurt 降低
    - volatility: 波动性 [0,1]，boundary 事件升高
    - repair_heat: 修复热 [0,1]，repair 事件升高
    """

    warmth: float = 0.45
    volatility: float = 0.0
    repair_heat: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "warmth": round(self.warmth, 6),
            "volatility": round(self.volatility, 6),
            "repair_heat": round(self.repair_heat, 6),
        }


@dataclass(slots=True)
class AlphaWoundState:
    """伤口子系统状态。

    模拟情感创伤和修复过程。
    - open: 开放伤口程度 [0,1]，hurt 事件大幅升高
    - scar: 疤痕累积 [0,1]，未修复的伤口缓慢转化为疤痕
    - sensitivity: 伤口敏感度 [0,1]，疤痕越多越敏感
    - repair: 修复进度 [0,1]，repair 事件升高
    """

    open: float = 0.0
    scar: float = 0.0
    sensitivity: float = 0.0
    repair: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "open": round(self.open, 6),
            "scar": round(self.scar, 6),
            "sensitivity": round(self.sensitivity, 6),
            "repair": round(self.repair, 6),
        }


@dataclass(slots=True)
class AlphaImmunityState:
    """免疫子系统状态。

    模拟边界防御和主权保护机制。
    - boundary_pressure: 边界压力 [0,1]，boundary/hurt 事件升高
    - sovereignty: 用户主权 [0,1]，低于 0.5 时阻止外向行动
    - interruption_budget: 中断预算 [0,1]，主动发言消耗预算
    - cooldown: 冷却计时器 [0,1]，主动发言后进入冷却
    - paused: 用户暂停标志，暂停时阻止所有外向行动
    """

    boundary_pressure: float = 0.0
    sovereignty: float = 1.0
    interruption_budget: float = 1.0
    cooldown: float = 0.0
    paused: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "boundary_pressure": round(self.boundary_pressure, 6),
            "sovereignty": round(self.sovereignty, 6),
            "interruption_budget": round(self.interruption_budget, 6),
            "cooldown": round(self.cooldown, 6),
            "paused": self.paused,
        }


@dataclass(slots=True)
class AlphaMortalityState:
    """死亡率子系统状态。

    模拟系统极限负荷，高耗竭时强制进入恢复模式。
    - load: 负荷 [0,1]，boundary/hurt 升高，safe 降低
    - exhaustion: 耗竭 [0,1]，超过 0.8 时 guard 阻止外向行动
    - recovery_debt: 恢复债务 [0,1]，idle 升高，repair 降低
    """

    load: float = 0.0
    exhaustion: float = 0.0
    recovery_debt: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "load": round(self.load, 6),
            "exhaustion": round(self.exhaustion, 6),
            "recovery_debt": round(self.recovery_debt, 6),
        }


@dataclass(slots=True)
class AlphaBodyState:
    """Sylanne-Embodiment 完整身体状态模型。

    聚合 8 个子系统 + 需求字典 + 记忆存储，构成 Sylanne 的「身体」。
    是 kernel 的核心数据载体，所有状态演化最终都反映在这里。

    与其他组件的关系：
    - AlphaKernel 持有一个 AlphaBodyState 实例，通过 tick() 驱动演化
    - vector.py 定义权重矩阵，body.apply() 调用 linear_delta 计算增量
    - codec.py 可将 state_vector() 编码为紧凑二进制
    - ShadowMemory 通过 observe_shadow_signal() 记录隐性信号
    """

    pulse: AlphaPulseState = field(default_factory=AlphaPulseState)
    bloodflow: AlphaBloodflowState = field(default_factory=AlphaBloodflowState)
    nerve: AlphaNerveState = field(default_factory=AlphaNerveState)
    muscle: AlphaMuscleState = field(default_factory=AlphaMuscleState)
    temperature: AlphaTemperatureState = field(default_factory=AlphaTemperatureState)
    wound: AlphaWoundState = field(default_factory=AlphaWoundState)
    immunity: AlphaImmunityState = field(default_factory=AlphaImmunityState)
    mortality: AlphaMortalityState = field(default_factory=AlphaMortalityState)
    needs: dict[str, float] = field(
        default_factory=lambda: {
            "need_contact": 0.0,
            "need_quiet": 0.0,
            "need_repair": 0.0,
            "need_expression": 0.0,
        }
    )
    memory: dict[str, Any] = field(default_factory=lambda: {"traces": []})

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AlphaBodyState":
        """从字典反序列化为 AlphaBodyState 实例。

        对每个子系统，只取 dataclass 声明的字段，忽略多余键。
        """
        body = cls()
        for name, state_type in (
            ("pulse", AlphaPulseState),
            ("bloodflow", AlphaBloodflowState),
            ("nerve", AlphaNerveState),
            ("muscle", AlphaMuscleState),
            ("temperature", AlphaTemperatureState),
            ("wound", AlphaWoundState),
            ("immunity", AlphaImmunityState),
            ("mortality", AlphaMortalityState),
        ):
            payload = data.get(name)
            if isinstance(payload, dict):
                setattr(
                    body,
                    name,
                    state_type(
                        **{
                            key: value
                            for key, value in payload.items()
                            if key in state_type.__dataclass_fields__
                        }
                    ),
                )
        if isinstance(data.get("needs"), dict):
            body.needs.update(
                {str(key): _clamp(float(value)) for key, value in data["needs"].items()}
            )
        if isinstance(data.get("memory"), dict):
            memory_data = data["memory"]
            traces = memory_data.get("traces", [])
            relationship = (
                memory_data.get("relationship")
                if isinstance(memory_data.get("relationship"), dict)
                else {}
            )
            shadow = (
                memory_data.get("shadow")
                if isinstance(memory_data.get("shadow"), dict)
                else {}
            )
            events = (
                shadow.get("events", [])
                if isinstance(shadow.get("events"), list)
                else []
            )
            body.memory = {
                "traces": [dict(item) for item in traces if isinstance(item, dict)][
                    -50:
                ],
                "relationship": dict(relationship),
                "shadow": {
                    "events": [dict(item) for item in events if isinstance(item, dict)][
                        -24:
                    ]
                },
            }
            memory_system = memory_data.get("_memory_system")
            if isinstance(memory_system, dict):
                body.memory["_memory_system"] = dict(memory_system)
        return body

    def state_vector(self) -> dict[str, float]:
        """将当前身体状态展平为 29 维状态向量字典。

        键为 STATE_AXES 中定义的轴名，值为对应的浮点数。
        用于 kernel 的决策计算和 codec 的二进制编码。
        """
        vector = {
            "pulse.beat": self.pulse.beat,
            "pulse.rhythm": self.pulse.rhythm,
            "pulse.strain": self.pulse.strain,
            "needs.need_contact": self.needs["need_contact"],
            "needs.need_quiet": self.needs["need_quiet"],
            "needs.need_repair": self.needs["need_repair"],
            "needs.need_expression": self.needs["need_expression"],
            "nerve.plasticity": self.nerve.plasticity,
            "nerve.sensitivity": self.nerve.sensitivity,
            "nerve.threshold_drift": self.nerve.threshold_drift,
            "bloodflow.circulation": self.bloodflow.circulation,
            "bloodflow.memory_flow": self.bloodflow.memory_flow,
            "bloodflow.warmth": self.bloodflow.warmth,
            "muscle.trained_reach": self.muscle.trained_reach,
            "muscle.fatigue": self.muscle.fatigue,
            "muscle.readiness": self.muscle.readiness,
            "temperature.warmth": self.temperature.warmth,
            "temperature.volatility": self.temperature.volatility,
            "temperature.repair_heat": self.temperature.repair_heat,
            "wound.open": self.wound.open,
            "wound.repair": self.wound.repair,
            "wound.scar": self.wound.scar,
            "wound.sensitivity": self.wound.sensitivity,
            "immunity.boundary_pressure": self.immunity.boundary_pressure,
            "immunity.cooldown": self.immunity.cooldown,
            "immunity.interruption_budget": self.immunity.interruption_budget,
            "mortality.load": self.mortality.load,
            "mortality.exhaustion": self.mortality.exhaustion,
            "mortality.recovery_debt": self.mortality.recovery_debt,
        }
        return {axis: round(float(vector[axis]), 6) for axis in STATE_AXES}

    def event_vector(
        self,
        *,
        text: str = "",
        flags: list[str] | None = None,
        confidence: float = 0.0,
        elapsed: float = 1.0,
        repetition: int = 0,
    ) -> dict[str, float]:
        """将一次交互事件编码为 9 维事件向量。

        Args:
            text: 用户输入文本
            flags: 事件标志列表（idle/safe/hurt/boundary/repair）
            confidence: 置信度 [0,1]
            elapsed: 距上次事件的时间间隔（秒，截断到 [1,12]）
            repetition: 该文本的历史重复次数

        Returns:
            9 维事件向量字典，键为 EVENT_AXES 中的轴名
        """
        flags = list(flags or [])
        clean_text = text.strip()
        vector = {
            "elapsed": max(1.0, min(12.0, float(elapsed))),
            "has_text": 1.0 if clean_text else 0.0,
            "confidence": _clamp(confidence),
            "idle": 1.0 if "idle" in flags and not clean_text else 0.0,
            "safe": 1.0 if "safe" in flags else 0.0,
            "hurt": 1.0 if "hurt" in flags else 0.0,
            "boundary": 1.0 if "boundary" in flags else 0.0,
            "repair": 1.0 if "repair" in flags else 0.0,
            "repetition": float(max(0, repetition)),
        }
        return {axis: vector[axis] for axis in EVENT_AXES}

    def vector_delta(self, event: dict[str, float]) -> dict[str, float]:
        """计算事件向量对状态向量的增量。

        组合线性权重矩阵投影 + 注意力机制的非线性修正。
        """
        delta = linear_delta(event)
        for axis, value in attention_delta(self.state_vector(), event).items():
            delta[axis] = delta.get(axis, 0.0) + value
        return delta

    def apply_vector_delta(self, delta: dict[str, float], *, now: float = 0.0) -> None:
        """将状态增量应用到身体各轴，所有值 clamp 到 [0,1]。

        Args:
            delta: 状态增量字典，键为 STATE_AXES 轴名
            now: 当前时间戳，用于更新 pulse.last_tick
        """
        self.pulse.beat = max(0.0, self.pulse.beat + delta.get("pulse.beat", 0.0))
        self.pulse.rhythm = _clamp(self.pulse.rhythm + delta.get("pulse.rhythm", 0.0))
        self.pulse.strain = _clamp(self.pulse.strain + delta.get("pulse.strain", 0.0))
        self.pulse.last_tick = now or self.pulse.last_tick + 1.0
        self.needs["need_contact"] = _clamp(
            self.needs["need_contact"] + delta.get("needs.need_contact", 0.0)
        )
        self.needs["need_quiet"] = _clamp(
            self.needs["need_quiet"] + delta.get("needs.need_quiet", 0.0)
        )
        self.needs["need_repair"] = _clamp(
            self.needs["need_repair"] + delta.get("needs.need_repair", 0.0)
        )
        self.needs["need_expression"] = _clamp(
            self.needs["need_expression"] + delta.get("needs.need_expression", 0.0)
        )
        self.nerve.plasticity = _clamp(
            self.nerve.plasticity + delta.get("nerve.plasticity", 0.0)
        )
        self.nerve.sensitivity = _clamp(
            self.nerve.sensitivity + delta.get("nerve.sensitivity", 0.0)
        )
        self.nerve.threshold_drift = _clamp(
            self.nerve.threshold_drift + delta.get("nerve.threshold_drift", 0.0)
        )
        self.bloodflow.circulation = _clamp(
            self.bloodflow.circulation + delta.get("bloodflow.circulation", 0.0)
        )
        self.bloodflow.memory_flow = _clamp(
            self.bloodflow.memory_flow + delta.get("bloodflow.memory_flow", 0.0)
        )
        self.bloodflow.warmth = _clamp(
            self.bloodflow.warmth + delta.get("bloodflow.warmth", 0.0)
        )
        self.muscle.trained_reach = _clamp(
            self.muscle.trained_reach + delta.get("muscle.trained_reach", 0.0)
        )
        self.muscle.fatigue = _clamp(
            self.muscle.fatigue + delta.get("muscle.fatigue", 0.0)
        )
        self.muscle.readiness = _clamp(
            self.muscle.readiness + delta.get("muscle.readiness", 0.0)
        )
        self.temperature.warmth = _clamp(
            self.temperature.warmth + delta.get("temperature.warmth", 0.0)
        )
        self.temperature.volatility = _clamp(
            self.temperature.volatility + delta.get("temperature.volatility", 0.0)
        )
        self.temperature.repair_heat = _clamp(
            self.temperature.repair_heat + delta.get("temperature.repair_heat", 0.0)
        )
        self.wound.open = _clamp(self.wound.open + delta.get("wound.open", 0.0))
        self.wound.repair = _clamp(self.wound.repair + delta.get("wound.repair", 0.0))
        self.wound.scar = _clamp(self.wound.scar + delta.get("wound.scar", 0.0))
        self.wound.sensitivity = _clamp(
            self.wound.sensitivity + delta.get("wound.sensitivity", 0.0)
        )
        self.immunity.boundary_pressure = _clamp(
            self.immunity.boundary_pressure
            + delta.get("immunity.boundary_pressure", 0.0)
        )
        self.immunity.sovereignty = _clamp(
            self.immunity.sovereignty + delta.get("immunity.sovereignty", 0.0)
        )
        self.immunity.cooldown = _clamp(
            self.immunity.cooldown + delta.get("immunity.cooldown", 0.0)
        )
        self.immunity.interruption_budget = _clamp(
            self.immunity.interruption_budget
            + delta.get("immunity.interruption_budget", 0.0)
        )
        self.mortality.load = _clamp(
            self.mortality.load + delta.get("mortality.load", 0.0)
        )
        self.mortality.exhaustion = _clamp(
            self.mortality.exhaustion + delta.get("mortality.exhaustion", 0.0)
        )
        self.mortality.recovery_debt = _clamp(
            self.mortality.recovery_debt + delta.get("mortality.recovery_debt", 0.0)
        )

    def simulate_vectors(self, events: list[dict[str, float]]) -> dict[str, float]:
        """在克隆体上模拟一系列事件，返回最终状态向量（不修改自身）。"""
        clone = AlphaBodyState.from_dict(self.to_dict())
        now = clone.pulse.last_tick
        for event in events:
            now += max(1.0, float(event.get("elapsed", 1.0)))
            clone.apply_vector_delta(clone.vector_delta(event), now=now)
        return clone.state_vector()

    def recall_memory(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        """基于关键词匹配从 traces 中召回相关记忆。

        评分规则：精确匹配 +1，词重叠 +1/词，权重加成。
        """
        terms = {part for part in query.strip().split() if part}
        scored = []
        for trace in self.memory.get("traces", []):
            text = str(trace.get("text") or "")
            overlap = sum(1 for term in terms if term in text)
            exact = 1 if query and query in text else 0
            score = exact + overlap + float(trace.get("weight") or 0.0)
            scored.append((score, trace))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [dict(trace) for _, trace in scored[: max(0, limit)]]

    # Legacy: superseded by MemorySystem
    def decay_memory(self, factor: float = 0.95) -> None:
        factor = _clamp(factor)
        for trace in self.memory.get("traces", []):
            trace["weight"] = round(
                _clamp(float(trace.get("weight") or 0.0) * factor), 6
            )

    # Legacy: superseded by MemorySystem
    def compress_memory(self, *, limit: int = 50) -> None:
        traces = [dict(trace) for trace in self.memory.get("traces", [])]
        traces.sort(key=lambda trace: float(trace.get("weight") or 0.0), reverse=True)
        self.memory["traces"] = traces[: max(0, limit)]

    def relationship_memory(self) -> dict[str, Any]:
        """返回关系记忆的结构化摘要。

        基于显式信号计数（偏好/边界/进展/修复）判断关系阶段：
        - low_signal: 信号不足，不参与 prompt
        - forming_continuity: 正在形成连续性
        - active_continuity: 活跃的关系连续性
        """
        relationship = self.memory.setdefault("relationship", {})
        signals = relationship.setdefault("signals", {})
        preference_count = int(signals.get("preference_count") or 0)
        boundary_count = int(signals.get("boundary_count") or 0)
        progress_count = int(signals.get("progress_count") or 0)
        repair_count = int(signals.get("repair_count") or 0)
        event_count = preference_count + boundary_count + progress_count + repair_count
        weight = _clamp(event_count / 12.0)
        phase = "low_signal"
        if weight >= 0.6:
            phase = "active_continuity"
        elif weight >= 0.25:
            phase = "forming_continuity"
        return {
            "schema_version": RELATIONSHIP_MEMORY_SCHEMA_VERSION,
            "kind": "relationship_memory",
            "internal_only": True,
            "read_only": True,
            "public_api_eligible": False,
            "prompt_eligible": event_count > 0,
            "signals": {
                "preference_count": preference_count,
                "boundary_count": boundary_count,
                "progress_count": progress_count,
                "repair_count": repair_count,
            },
            "continuity": {
                "event_count": event_count,
                "weight": round(weight, 6),
                "phase": phase,
            },
            "constraints": [
                "explicit_signal_counts_only",
                "no_raw_text",
                "session_local",
                "does_not_override_current_user_text",
            ],
        }

    def _observe_relationship_signal(self, *, flags: list[str], text: str) -> None:
        if not text:
            return
        relationship = self.memory.setdefault("relationship", {})
        signals = relationship.setdefault("signals", {})
        for name, markers in {
            "preference_count": {"preference", "style", "like"},
            "boundary_count": {"boundary", "pause"},
            "progress_count": {"progress", "followup", "project"},
            "repair_count": {"repair"},
        }.items():
            if any(marker in flags for marker in markers):
                signals[name] = int(signals.get(name) or 0) + 1

    def shadow_memory(self) -> dict[str, Any]:
        shadow = ShadowMemory.from_raw(self.memory.get("shadow"))
        return shadow.state()

    def observe_shadow_signal(
        self, *, text: str = "", flags: list[str] | None = None, kind: str = ""
    ) -> None:
        shadow = ShadowMemory.from_raw(self.memory.get("shadow"))
        shadow.observe_signal(text=text, flags=flags, kind=kind)
        self.memory["shadow"] = shadow.to_raw()

    def to_dict(self) -> dict[str, Any]:
        shadow = (
            self.memory.get("shadow")
            if isinstance(self.memory.get("shadow"), dict)
            else {}
        )
        memory_payload = {
            "traces": list(self.memory.get("traces", []))[-50:],
            "relationship": dict(self.memory.get("relationship") or {}),
            "shadow": {
                "events": [
                    dict(item)
                    for item in shadow.get("events", [])
                    if isinstance(item, dict)
                ][-24:]
            },
        }
        memory_system = self.memory.get("_memory_system")
        if isinstance(memory_system, dict):
            memory_payload["_memory_system"] = dict(memory_system)
        return {
            "pulse": self.pulse.to_dict(),
            "bloodflow": self.bloodflow.to_dict(),
            "nerve": self.nerve.to_dict(),
            "muscle": self.muscle.to_dict(),
            "temperature": self.temperature.to_dict(),
            "wound": self.wound.to_dict(),
            "immunity": self.immunity.to_dict(),
            "mortality": self.mortality.to_dict(),
            "needs": {key: round(value, 6) for key, value in self.needs.items()},
            "memory": memory_payload,
        }

    def apply(
        self,
        *,
        text: str = "",
        flags: list[str] | None = None,
        confidence: float = 0.0,
        now: float = 0.0,
    ) -> None:
        """接收一次交互事件，驱动身体状态完整演化。

        这是身体状态的主入口方法，执行以下步骤：
        1. 构建 9 维事件向量
        2. 计算并应用状态增量（线性投影 + 注意力修正）
        3. 执行非线性后处理（疲劳累积、伤口自愈、疤痕形成等）
        4. 处理免疫系统控制信号（pause/resume/reset）
        5. 更新记忆流动和 traces

        Args:
            text: 用户输入文本
            flags: 事件标志列表
            confidence: 置信度
            now: 当前时间戳
        """
        flags = list(flags or [])
        text = text.strip()
        elapsed = max(0.0, now - self.pulse.last_tick) if now else 1.0
        previous = [
            str(item.get("text") or "") for item in self.memory.get("traces", [])
        ]
        repetition = previous.count(text) + 1 if text else 0

        event = self.event_vector(
            text=text,
            flags=flags,
            confidence=confidence,
            elapsed=elapsed,
            repetition=repetition,
        )
        self.apply_vector_delta(self.vector_delta(event), now=now)
        self.nerve.repetition = repetition

        self.muscle.fatigue = _clamp(
            self.muscle.fatigue + (0.06 if self.needs["need_contact"] > 0.65 else 0.0)
        )
        self.muscle.readiness = _clamp(
            0.2
            + self.muscle.trained_reach
            + self.needs["need_expression"]
            - self.muscle.fatigue
        )
        self.wound.repair = _clamp(
            self.wound.repair
            + (0.02 if self.wound.open > 0.0 and "repair" not in flags else 0.0)
        )
        self.wound.scar = _clamp(
            self.wound.scar + max(0.0, self.wound.open - self.wound.repair) * 0.05
        )
        self.wound.sensitivity = _clamp(self.wound.sensitivity + self.wound.scar * 0.02)
        self.immunity.paused = (
            "pause" in flags or self.immunity.paused and "resume" not in flags
        )
        if "reset" in flags:
            self.immunity.interruption_budget = 1.0
            self.immunity.cooldown = 0.0
            self.immunity.paused = False
        target_flow = _clamp(
            len(self.memory.get("traces", [])) / 50.0 + self.nerve.plasticity * 0.2
        )
        self.bloodflow.memory_flow = _clamp(
            self.bloodflow.memory_flow * 0.9 + target_flow * 0.1
        )

        if text:
            self.memory.setdefault("traces", []).append(
                {
                    "id": f"trace-{len(self.memory.get('traces', [])) + 1}",
                    "text": text[:500],
                    "weight": round(_clamp(0.35 + repetition * 0.08), 6),
                    "temperature": self.temperature.to_dict()["warmth"],
                }
            )
            self.memory["traces"] = self.memory["traces"][-50:]
            self._observe_relationship_signal(flags=flags, text=text)
            self.observe_shadow_signal(text=text, flags=flags)


# ---------------------------------------------------------------------------
# Item 97: 能量管理模型
# ---------------------------------------------------------------------------


class EnergyPool:
    """Sylanne 的能量池：模拟认知负荷/情感消耗/恢复周期。"""

    def __init__(self, max_energy: float = 1.0):
        self._energy: float = max_energy
        self._max: float = max_energy
        self._last_tick: float = time.time()

    @property
    def energy(self) -> float:
        return self._energy

    @property
    def is_fatigued(self) -> bool:
        return self._energy < 0.3

    def consume(self, amount: float):
        """消耗能量（对话、情感处理、LLM 调用等）。"""
        self._energy = max(0.0, self._energy - amount)

    def recover(self, dt: float):
        """自然恢复。dt 为距上次 tick 的秒数。"""
        # 每小时恢复 0.2 能量
        recovery = dt / 3600 * 0.2
        self._energy = min(self._max, self._energy + recovery)

    def tick(self):
        """每轮对话调用。"""
        now = time.time()
        dt = now - self._last_tick
        self._last_tick = now
        self.recover(dt)

    def get_fatigue_hint(self) -> str | None:
        """疲劳时返回风格提示。"""
        if self._energy < 0.15:
            return "非常疲惫，回复极简短温和"
        elif self._energy < 0.3:
            return "有些疲惫，回复简短但保持温度"
        return None

    def to_dict(self) -> dict:
        return {"energy": self._energy, "last_tick": self._last_tick}

    @classmethod
    def from_dict(cls, data: dict) -> "EnergyPool":
        pool = cls()
        pool._energy = data.get("energy", 1.0)
        pool._last_tick = data.get("last_tick", time.time())
        return pool
