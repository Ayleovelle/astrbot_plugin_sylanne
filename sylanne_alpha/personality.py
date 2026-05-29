"""Sylanne-Embodiment 双向人格系统。

双层架构：
  - Embodiment Five（深层结构）：由计算栈驱动，缓慢漂移
  - Sylanne Six（表层表达）：由文本事件驱动，快速漂移，受 Embodiment 约束

漂移动力学使用 Dual-EMA 共识机制、恒稳态设定点（homeostatic set-point）和惯性衰减。

核心设计理念：人格驱动全参数——安全阀/阈值必须是人格函数；
事件反向塑造人格：计算结果→人格漂移→新参数，形成闭环。
"""

from __future__ import annotations

import hashlib
import math
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

PERSONALITY_SCHEMA_VERSION = "sylanne.alpha.personality.embodiment.v1"

# Embodiment Five：深层人格特质（计算栈驱动，漂移缓慢）
# 这五个维度对应 Sylanne 的"身体性"——不可被文本直接改写
EMBODIMENT_TRAITS = (
    "expression_drive_trait",  # 表达驱力：主动输出的倾向
    "perception_acuity",  # 感知敏锐度：对张力/情绪的感知灵敏度
    "boundary_permeability",  # 边界渗透性：对新事物/惊喜的开放程度
    "inner_order",  # 内在秩序：系统一致性和自我修复倾向
    "relational_gravity",  # 关系引力：向他人靠近的基础倾向
)

# Sylanne Six：表层人格特质（文本事件驱动，快速漂移，受 Embodiment 约束）
# 这六个维度是用户可感知的"性格表现"
SYLANNE_TRAITS = (
    "warmth_bias",  # 温暖偏向：回应中的温度倾向
    "edge",  # 锋利度：直接/尖锐的表达倾向
    "curiosity",  # 好奇心：对新话题的探索欲
    "patience",  # 耐心：等待和慢节奏的容忍度
    "intimacy_gravity",  # 亲密引力：向亲密关系靠近的倾向
    "sovereignty_guard",  # 主权守卫：维护自我边界的强度
)

# 旧版 Big Five → Embodiment Five 的映射表（向后兼容）
_LEGACY_MAP = {
    "extraversion": "expression_drive_trait",
    "neuroticism": "perception_acuity",
    "openness": "boundary_permeability",
    "conscientiousness": "inner_order",
    "agreeableness": "relational_gravity",
}

_REVERSE_LEGACY_MAP = {v: k for k, v in _LEGACY_MAP.items()}

# Embodiment 特质的硬边界——防止极端值导致系统不稳定
_TRAIT_FLOOR = 0.05
_TRAIT_CEIL = 0.95

# 单次 tick 内所有特质变化总量（绝对值之和）的上限
_TICK_DRIFT_CAP = 0.05

# --- 漂移信号 → Embodiment 特质映射（来自设计文档 3.1 节）---
# 每个信号可以影响一个或多个特质，权重表示影响方向和强度
# 正权重 = 特质值上升，负权重 = 特质值下降
DRIFT_SIGNALS: dict[str, list[tuple[str, float]]] = {
    # 表达驱力相关信号
    "feedback_accepted": [("expression_drive_trait", +0.4)],  # 表达被接受→增强表达欲
    "feedback_ignored": [("expression_drive_trait", -0.2)],  # 表达被忽略→轻微抑制
    "feedback_rejected": [  # 表达被拒绝→显著抑制表达欲，同时降低关系引力
        ("expression_drive_trait", -0.6),
        ("relational_gravity", -0.3),
    ],
    "expression_fired": [("expression_drive_trait", +0.3)],  # 成功触发表达→正反馈
    "sustained_silence": [("expression_drive_trait", -0.1)],  # 持续沉默→缓慢抑制
    # 感知敏锐度相关信号
    "high_tension": [("perception_acuity", +0.5)],  # 高张力→感知变敏锐
    "low_coherence": [("perception_acuity", +0.4)],  # 低一致性→警觉提升
    "high_void_pressure": [("perception_acuity", +0.3)],  # 高虚空压力→感知增强
    "sustained_positive_valence": [("perception_acuity", -0.3)],  # 持续正向→感知放松
    "boundary_stable": [("perception_acuity", -0.2)],  # 边界稳定→警觉降低
    # 边界渗透性相关信号
    "high_surprise_positive": [("boundary_permeability", +0.4)],  # 正向惊喜→更开放
    "new_void_created": [("boundary_permeability", +0.3)],  # 新虚空产生→边界松动
    "sustained_low_surprise": [("boundary_permeability", -0.2)],  # 持续无惊喜→边界收紧
    "high_surprise_negative": [("boundary_permeability", -0.3)],  # 负向惊喜→防御收缩
}
DRIFT_SIGNALS.update(
    {
        # 内在秩序相关信号
        "high_coherence": [("inner_order", +0.2)],  # 高一致性→秩序感增强
        "full_route_used": [("inner_order", +0.1)],  # 完整路由使用→系统有序
        "boundary_self_repair": [("inner_order", +0.15)],  # 边界自修复→秩序恢复
        "system_chaos": [("inner_order", -0.3)],  # 系统混乱→秩序感受损
        # 关系引力相关信号
        "repair_executed": [("relational_gravity", +0.3)],  # 修复执行→关系拉近
        "boundary_breached": [("relational_gravity", -0.5)],  # 边界被突破→关系退缩
        "relaxed_positive": [("relational_gravity", +0.2)],  # 放松正向→关系亲近
    }
)


# ---------------------------------------------------------------------------
# TraitMemory: 单特质的 Dual-EMA 状态，带恒稳态设定点
# ---------------------------------------------------------------------------


class TraitMemory:
    """单个特质的记忆状态，实现 Dual-EMA 共识机制和恒稳态吸引子。

    核心机制：
    - fast_ema（τ=50）：捕捉近期趋势方向
    - slow_ema（τ=500）：捕捉长期基线方向
    - 当两个 EMA 方向一致时，漂移全量生效（共识）
    - 当方向相反时，漂移减半（分歧抑制）
    - set_point 以极慢速率（τ≈5000）跟随实际值演化

    与其他组件的关系：
    - 被 compute_embodiment_drift() 调用来更新特质值
    - 被 OscillationDetector 监控以防止震荡
    """

    __slots__ = ("value", "fast_ema", "slow_ema", "set_point", "_frozen_ticks")

    def __init__(self, initial: float = 0.5):
        self.value = initial
        self.fast_ema = 0.0  # 快速 EMA：近期趋势方向信号
        self.slow_ema = 0.0  # 慢速 EMA：长期基线方向信号
        self.set_point = initial  # 恒稳态设定点：特质的"舒适区"
        self._frozen_ticks = 0  # 冻结计数器：震荡检测后暂停漂移

    def update(self, raw_delta: float) -> float:
        """应用一次漂移增量，使用 Dual-EMA 共识逻辑。

        参数:
            raw_delta: 原始漂移增量（由 compute_embodiment_drift 计算得出）

        返回:
            实际应用的增量值（可能因冻结、边界裁剪而与 raw_delta 不同）
        """
        if self._frozen_ticks > 0:
            self._frozen_ticks -= 1
            return 0.0

        # 更新双 EMA（τ_fast=50, τ_slow=500）
        alpha_fast = 2.0 / (50.0 + 1.0)
        alpha_slow = 2.0 / (500.0 + 1.0)
        self.fast_ema = (1.0 - alpha_fast) * self.fast_ema + alpha_fast * raw_delta
        self.slow_ema = (1.0 - alpha_slow) * self.slow_ema + alpha_slow * raw_delta

        # 共识判断：同向→全量漂移；反向→减半（防止短期噪声主导长期趋势）
        if self.fast_ema * self.slow_ema > 0:
            effective = raw_delta
        else:
            effective = raw_delta * 0.5

        old = self.value
        self.value = max(_TRAIT_FLOOR, min(_TRAIT_CEIL, self.value + effective))
        actual = self.value - old

        # 设定点缓慢演化（τ ≈ 5000），使"舒适区"逐渐适应新常态
        self.set_point += 0.0004 * (self.value - self.set_point)
        return actual

    def recovery_pull(self) -> float:
        """计算恒稳态回复力——将特质拉回设定点的力。"""
        return (self.set_point - self.value) * 0.3

    def freeze(self, ticks: int) -> None:
        """冻结特质指定 tick 数（由震荡检测器触发）。"""
        self._frozen_ticks = ticks

    @property
    def frozen(self) -> bool:
        return self._frozen_ticks > 0

    def to_dict(self) -> dict[str, float]:
        """序列化为字典，用于持久化存储。"""
        return {
            "value": round(self.value, 6),
            "fast_ema": round(self.fast_ema, 6),
            "slow_ema": round(self.slow_ema, 6),
            "set_point": round(self.set_point, 6),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TraitMemory":
        """从字典恢复 TraitMemory 实例。"""
        tm = cls(float(data.get("value", 0.5)))
        tm.fast_ema = float(data.get("fast_ema", 0.0))
        tm.slow_ema = float(data.get("slow_ema", 0.0))
        tm.set_point = float(data.get("set_point", tm.value))
        return tm


# ---------------------------------------------------------------------------
# DriftSignalExtractor: 从计算结果中提取归一化 [0,1] 漂移信号
# ---------------------------------------------------------------------------


class DriftSignalExtractor:
    """从计算栈的输出结果中提取归一化漂移信号。

    维护一个滑动窗口（默认 10 条），用于检测持续性模式
    （如持续沉默、持续正向情绪等需要多条消息才能判断的信号）。

    与其他组件的关系：
    - 输入：计算栈每次 tick 的结果字典
    - 输出：归一化信号字典，供 compute_embodiment_drift() 使用
    """

    __slots__ = ("_window",)

    def __init__(self, window_size: int = 10):
        self._window: deque[dict[str, Any]] = deque(maxlen=window_size)

    def extract(self, result: dict[str, Any]) -> dict[str, float]:
        """从一次计算结果中提取归一化 [0,1] 信号。

        参数:
            result: 计算栈输出，包含 emotion、route、should_express 等字段

        返回:
            信号名→强度的字典，强度范围 [0, 1]
        """
        self._window.append(result)
        signals: dict[str, float] = {}
        emotion = result.get("emotion", {})
        route = result.get("route", "")
        should_express = result.get("should_express", False)

        # 表达触发信号
        if should_express:
            signals["expression_fired"] = 1.0

        # 路由相关信号：连续 skip 表示持续沉默
        if route == "skip":
            skip_count = sum(1 for r in self._window if r.get("route") == "skip")
            if skip_count >= 3:
                signals["sustained_silence"] = min(1.0, skip_count / 5.0)
        if route == "full":
            signals["full_route_used"] = 1.0

        # 张力信号：超过 0.7 阈值才触发
        tension = float(emotion.get("tension", 0.0))
        if tension > 0.7:
            signals["high_tension"] = min(1.0, (tension - 0.7) / 0.3)

        # 一致性信号：低一致性和高一致性分别触发不同信号
        coherence = float(result.get("emotion", {}).get("coherence", 1.0))
        if coherence < 0.4:
            signals["low_coherence"] = min(1.0, (0.4 - coherence) / 0.4)
        if coherence > 0.8:
            signals["high_coherence"] = min(1.0, (coherence - 0.8) / 0.2)

        # 虚空压力信号：超过 30 才有意义
        void_pressure = float(emotion.get("void_pressure", 0.0))
        if void_pressure > 30:
            signals["high_void_pressure"] = min(1.0, void_pressure / 60.0)

        # 情绪效价模式：需要窗口内多条消息持续正向
        valence = float(emotion.get("valence", 0.0))
        positive_count = sum(
            1
            for r in self._window
            if float(r.get("emotion", {}).get("valence", 0.0)) > 0.3
        )
        if positive_count >= 5:
            signals["sustained_positive_valence"] = min(1.0, positive_count / 7.0)
        # 放松正向：正效价 + 低张力的组合
        if valence > 0.2 and tension < 0.3:
            signals["relaxed_positive"] = min(1.0, valence)

        # 边界稳定性信号
        stability = float(result.get("boundary_stability", 0.0))
        if stability > 0.9:
            signals["boundary_stable"] = min(1.0, (stability - 0.9) / 0.1)

        # 惊喜信号：区分正向惊喜和负向惊喜
        surprise = float(result.get("surprise", 0.0))
        if surprise > 0.6 and valence >= 0:
            signals["high_surprise_positive"] = min(1.0, surprise)
        if surprise > 0.6 and valence < -0.3:
            signals["high_surprise_negative"] = min(1.0, surprise)
        # 持续低惊喜：窗口内大部分消息都无惊喜
        low_surprise_count = sum(
            1 for r in self._window if float(r.get("surprise", 0.0)) < 0.2
        )
        if low_surprise_count >= 8:
            signals["sustained_low_surprise"] = min(1.0, low_surprise_count / 10.0)

        # 系统混乱：低一致性 + 高虚空压力的极端组合
        if coherence < 0.3 and void_pressure > 50:
            signals["system_chaos"] = min(1.0, (50.0 - coherence * 100) / 50.0)

        return signals


# ---------------------------------------------------------------------------
# OscillationDetector: 震荡检测器
# ---------------------------------------------------------------------------


class OscillationDetector:
    """检测特质值的快速方向反转，防止人格震荡。

    当一个特质在短时间内频繁正负交替（≥6 次反转/10 步），
    说明系统处于不稳定状态，此时冻结该特质以恢复稳定。

    与其他组件的关系：
    - 被 compute_embodiment_drift() 在每次漂移后调用
    - 触发时调用 TraitMemory.freeze() 冻结特质
    """

    __slots__ = ("_history",)

    def __init__(self, window: int = 10):
        self._history: dict[str, deque[float]] = {}

    def record(self, trait_name: str, delta: float) -> bool:
        """记录一次漂移增量。返回 True 表示检测到震荡（特质应被冻结）。

        参数:
            trait_name: 特质名称
            delta: 本次实际应用的漂移增量

        返回:
            是否检测到震荡
        """
        if trait_name not in self._history:
            self._history[trait_name] = deque(maxlen=10)
        hist = self._history[trait_name]
        hist.append(delta)
        if len(hist) < 4:
            return False
        # 统计方向反转次数：相邻两步符号相反即为一次反转
        reversals = 0
        for i in range(1, len(hist)):
            if hist[i] * hist[i - 1] < 0:
                reversals += 1
        # 10 步内 6 次以上反转 = 震荡
        return reversals >= 6


# ---------------------------------------------------------------------------
# DriftAttribution: 人格漂移归因分析（Item 68）
# ---------------------------------------------------------------------------


@dataclass
class DriftEvent:
    """单次人格漂移事件记录。"""

    timestamp: float
    trigger: str  # 触发信号描述
    dimension: str  # 变化的维度
    delta: float  # 变化量
    new_value: float  # 变化后的值


class DriftAttribution:
    """人格漂移归因追踪器。

    记录每次显著的人格漂移事件（|delta| > 0.005），
    用于事后分析人格变化的来源和趋势。

    与其他组件的关系：
    - 被 compute_embodiment_drift() 在每次漂移后调用
    - 提供 recent() 接口供诊断/WebUI 展示漂移历史
    """

    __slots__ = ("_events",)

    def __init__(self, maxlen: int = 100):
        self._events: deque[DriftEvent] = deque(maxlen=maxlen)

    def record(self, trigger: str, dimension: str, delta: float, new_value: float):
        """记录一次漂移事件（仅当变化量显著时）。"""
        if abs(delta) > 0.005:
            self._events.append(
                DriftEvent(time.time(), trigger, dimension, delta, new_value)
            )

    def recent(self, n: int = 20) -> list[dict]:
        """返回最近 n 条漂移事件的字典列表。"""
        return [
            {
                "timestamp": e.timestamp,
                "trigger": e.trigger,
                "dimension": e.dimension,
                "delta": e.delta,
                "value": e.new_value,
            }
            for e in list(self._events)[-n:]
        ]


# ---------------------------------------------------------------------------
# _seasonal_modulation: 季节性微弱调制
# ---------------------------------------------------------------------------


def _get_seasonal_target() -> str | None:
    """返回当前季节应调制的特质名，无需调制时返回 None。"""
    month = time.localtime().tm_mon
    if month in (12, 1, 2):
        return "inner_order"
    elif month in (3, 4, 5):
        return "expression_drive_trait"
    elif month in (6, 7, 8):
        return "boundary_permeability"
    else:
        return "perception_acuity"


def _seasonal_modulation(traits: dict[str, TraitMemory]) -> None:
    """根据当前月份对 Embodiment Five 施加微弱季节性调制（±0.01 级别）。

    季节规则：
    - 冬天（12-2月）：inner_order 微升 +0.01
    - 春天（3-5月）：expression_drive_trait 微升 +0.01
    - 夏天（6-8月）：boundary_permeability 微升 +0.01
    - 秋天（9-11月）：perception_acuity 微升 +0.01

    调制量极小，仅作为长期背景趋势存在，不会覆盖其他漂移机制。
    注意：此函数保留用于独立调用场景，compute_embodiment_drift 中已通过
    pending 机制纳入 drift cap 约束。
    """
    target = _get_seasonal_target()
    if target and target in traits:
        tm = traits[target]
        if not tm.frozen:
            tm.value = max(_TRAIT_FLOOR, min(_TRAIT_CEIL, tm.value + 0.01))
            tm.set_point += 0.0002 * (tm.value - tm.set_point)


# ---------------------------------------------------------------------------
# compute_embodiment_drift: 核心漂移公式
# ---------------------------------------------------------------------------


def compute_embodiment_drift(
    traits: dict[str, TraitMemory],
    signals: dict[str, float],
    tick_count: int,
    oscillation_detector: OscillationDetector | None = None,
    drift_attribution: DriftAttribution | None = None,
) -> None:
    """根据提取的信号对 Embodiment 特质施加漂移。

    漂移公式: Δ = base_rate × √signal × inertia × homeostatic × asymmetric

    各因子含义：
    - base_rate (0.003): 基础漂移速率，保证变化足够缓慢
    - √signal: 信号强度的平方根，压缩极端值的影响
    - inertia: 惯性因子，随 tick 数增加而递减（越老越稳定）
    - homeostatic: 恒稳态阻力，偏离设定点越远阻力越大
    - asymmetric: 非对称阻力，接近极端值时额外减速

    速率限制：单次 tick 内所有特质变化总量（绝对值之和）不超过
    _TICK_DRIFT_CAP (0.05)。超过时按比例缩放所有 delta。

    参数:
        traits: 特质名→TraitMemory 的字典
        signals: 信号名→强度的字典（由 DriftSignalExtractor 产生）
        tick_count: 当前总 tick 数（用于计算惯性）
        oscillation_detector: 可选的震荡检测器
        drift_attribution: 可选的漂移归因追踪器
    """
    base_rate = 0.003
    # 惯性：随时间对数增长而递减，使人格越来越稳定
    inertia = 1.0 / (1.0 + math.log(1.0 + tick_count / 500.0))

    # 第一遍：收集所有 raw_delta，用于速率限制
    pending: list[tuple[str, float, str]] = []  # (trait_name, raw_delta, signal_name)

    for signal_name, signal_value in signals.items():
        if signal_value <= 0 or signal_name not in DRIFT_SIGNALS:
            continue
        mappings = DRIFT_SIGNALS[signal_name]
        # 平方根压缩：避免极端信号值主导漂移
        signal_magnitude = math.sqrt(signal_value)

        for trait_name, weight in mappings:
            if trait_name not in traits:
                continue
            tm = traits[trait_name]
            if tm.frozen:
                continue

            # 恒稳态阻力：偏离设定点越远，漂移阻力越大
            homeostatic = 1.0 - abs(tm.value - tm.set_point) * 0.3

            # 非对称阻力：接近极端值时减速（防止饱和）
            direction = 1.0 if weight > 0 else -1.0
            asymmetric = 1.0
            if (direction > 0 and tm.value > 0.7) or (direction < 0 and tm.value < 0.3):
                asymmetric = 0.5

            raw_delta = (
                base_rate
                * signal_magnitude
                * weight
                * inertia
                * homeostatic
                * asymmetric
            )
            pending.append((trait_name, raw_delta, signal_name))

    # 速率限制：如果总变化量超过 _TICK_DRIFT_CAP，按比例缩放
    # 季节性调制也纳入预算，不绕过 drift cap
    seasonal_target = _get_seasonal_target()
    if seasonal_target and seasonal_target in traits and not traits[seasonal_target].frozen:
        pending.append((seasonal_target, 0.01, "_seasonal"))

    total_abs = sum(abs(d) for _, d, _ in pending)
    if total_abs > _TICK_DRIFT_CAP:
        scale = _TICK_DRIFT_CAP / total_abs
        pending = [(name, delta * scale, sig) for name, delta, sig in pending]

    # 第二遍：应用缩放后的 delta
    for trait_name, raw_delta, signal_name in pending:
        tm = traits[trait_name]
        actual = tm.update(raw_delta)

        # 漂移归因记录（Item 68）
        if drift_attribution and actual != 0:
            drift_attribution.record(signal_name, trait_name, actual, tm.value)

        # 震荡检测：如果检测到震荡，冻结该特质 20 步
        if oscillation_detector and actual != 0:
            if oscillation_detector.record(trait_name, actual):
                tm.freeze(20)


# ---------------------------------------------------------------------------
# Sylanne 表层特质的 Embodiment 约束边界（约束方向：深层→表层）
# ---------------------------------------------------------------------------


def sylanne_bounds_from_embodiment(
    embodiment: dict[str, TraitMemory],
) -> dict[str, tuple[float, float]]:
    """根据 Embodiment Five 计算 Sylanne Six 每个特质的允许范围 [min, max]。

    这是双层架构的核心约束：表层人格的漂移不能超出深层人格设定的边界。
    例如：relational_gravity 低时，warmth_bias 的上限也会被压低。

    参数:
        embodiment: Embodiment 特质名→TraitMemory 的字典

    返回:
        Sylanne 特质名→(下界, 上界) 的字典
    """
    _e = embodiment.get("expression_drive_trait", TraitMemory(0.5)).value
    _p = embodiment.get("perception_acuity", TraitMemory(0.5)).value
    b = embodiment.get("boundary_permeability", TraitMemory(0.5)).value
    o = embodiment.get("inner_order", TraitMemory(0.5)).value
    r = embodiment.get("relational_gravity", TraitMemory(0.5)).value

    return {
        "warmth_bias": (max(0.0, r * 0.4), min(1.0, 0.4 + r * 0.6)),
        "edge": (max(0.0, 0.1 - r * 0.1), min(1.0, 0.5 + (1 - r) * 0.5)),
        "curiosity": (max(0.0, b * 0.3), min(1.0, 0.3 + b * 0.7)),
        "patience": (max(0.0, o * 0.3), min(1.0, 0.3 + o * 0.7)),
        "intimacy_gravity": (max(0.0, r * 0.3), min(1.0, 0.3 + r * 0.7)),
        "sovereignty_guard": (
            max(0.0, 0.3 + (1 - b) * 0.2),
            min(1.0, 0.5 + (1 - b) * 0.5),
        ),
    }


# ---------------------------------------------------------------------------
# drift_sylanne_traits: 快速文本驱动漂移（受 Embodiment 约束）
# ---------------------------------------------------------------------------


def drift_sylanne_traits(
    personality: dict[str, Any],
    *,
    event: dict[str, Any] | None = None,
    embodiment: dict[str, TraitMemory] | None = None,
) -> dict[str, Any]:
    """对 Sylanne 表层特质施加文本驱动的快速漂移。

    与 Embodiment 漂移不同，这里的漂移由用户文本中的关键词触发，
    速率更快（rate=0.02 vs 0.003），但受 Embodiment 边界约束。

    参数:
        personality: 当前人格状态字典
        event: 触发事件，包含 text（文本）和 confidence（置信度）
        embodiment: 可选的 Embodiment 特质字典，用于计算约束边界

    返回:
        更新后的完整人格状态字典
    """
    event = dict(event or {})
    traits = dict(personality.get("traits") or {})
    confidence = max(0.0, min(1.0, float(event.get("confidence") or 0.0)))
    text = str(event.get("text") or "")
    direction = _event_direction(text)
    rate = 0.02
    step = max(0.0, min(0.05, rate * confidence))

    # Compute bounds if embodiment available
    bounds: dict[str, tuple[float, float]] | None = None
    if embodiment:
        bounds = sylanne_bounds_from_embodiment(embodiment)

    drifted = {}
    for name in SYLANNE_TRAITS:
        current = float(traits.get(name, 0.5))
        new_val = current + direction.get(name, 0.0) * step
        # Clamp to embodiment bounds if available
        if bounds and name in bounds:
            lo, hi = bounds[name]
            new_val = max(lo, min(hi, new_val))
        drifted[name] = round(max(0.0, min(1.0, new_val)), 6)

    previous_drift = dict(personality.get("drift") or {})
    return {
        "schema_version": PERSONALITY_SCHEMA_VERSION,
        "signature": str(personality.get("signature") or _digest(str(traits))),
        "traits": drifted,
        "voice": _voice(drifted),
        "drift": {
            "mode": "slow_plasticity",
            "events": int(previous_drift.get("events") or 0) + 1,
            "plasticity": round(
                min(1.0, float(previous_drift.get("plasticity") or 0.0) + step), 6
            ),
        },
    }


# ---------------------------------------------------------------------------
# Legacy-compatible drift_personality（委托给 drift_sylanne_traits）
# ---------------------------------------------------------------------------


def drift_personality(
    personality: dict[str, Any],
    *,
    event: dict[str, Any] | None = None,
    rate: float = 0.02,
) -> dict[str, Any]:
    """旧版兼容接口：人格漂移。内部委托给 drift_sylanne_traits。"""
    return drift_sylanne_traits(personality, event=event)


# ---------------------------------------------------------------------------
# initial_personality: 初始人格生成（包含 Embodiment 特质）
# ---------------------------------------------------------------------------


def initial_personality(
    session_key: str, *, seed_text: str = "Sylanne Soulful"
) -> dict[str, Any]:
    """生成初始人格状态。

    使用 blake2s 哈希从 session_key 和 seed_text 生成确定性签名，
    再从签名字节派生各特质的初始值（base ± 微小随机偏移）。
    这保证同一 session_key 总是得到相同的初始人格。

    参数:
        session_key: 会话标识符（决定人格的"种子"）
        seed_text: 种子文本，默认 "Sylanne Soulful"

    返回:
        完整的人格状态字典
    """
    signature = _digest(f"{session_key}\0{seed_text}")
    traits = {
        "warmth_bias": _trait(signature, 0, base=0.56),
        "edge": _trait(signature, 1, base=0.42),
        "curiosity": _trait(signature, 2, base=0.58),
        "patience": _trait(signature, 3, base=0.52),
        "intimacy_gravity": _trait(signature, 4, base=0.50),
        "sovereignty_guard": _trait(signature, 5, base=0.68),
    }
    return {
        "schema_version": PERSONALITY_SCHEMA_VERSION,
        "signature": signature,
        "traits": traits,
        "voice": _voice(traits),
        "drift": {"mode": "slow_plasticity", "events": 0, "plasticity": 0.0},
    }


# ---------------------------------------------------------------------------
# 人格名称归一化：同时接受旧版和新版特质名
# ---------------------------------------------------------------------------


def normalize_personality(personality: dict[str, float]) -> dict[str, float]:
    """接受旧版 Big Five 名称和新版 Embodiment 名称，返回两者都填充的字典。

    确保无论下游代码使用哪套名称都能正常工作（向后兼容）。

    参数:
        personality: 可能包含旧版或新版名称的人格字典

    返回:
        同时包含旧版和新版名称的完整字典
    """
    result = dict(personality)
    # Map legacy → new
    for old_name, new_name in _LEGACY_MAP.items():
        if old_name in result and new_name not in result:
            result[new_name] = result[old_name]
    # Map new → legacy (so downstream code using old names still works)
    for old_name, new_name in _LEGACY_MAP.items():
        if new_name in result and old_name not in result:
            result[old_name] = result[new_name]
    return result


# ---------------------------------------------------------------------------
# 矛盾容忍度（Item 133）
# ---------------------------------------------------------------------------


def contradiction_tolerance(traits: dict[str, float]) -> float:
    """inner_order 越高，对自我矛盾的容忍度越低。

    当 inner_order = 1.0 时容忍度最低（0.2），
    当 inner_order = 0.0 时容忍度最高（1.0）。

    参数:
        traits: 人格特质字典（需包含 inner_order 或 conscientiousness）

    返回:
        矛盾容忍度，范围 [0.2, 1.0]。
    """
    inner_order = float(
        traits.get("inner_order", traits.get("conscientiousness", 0.5))
    )
    return 1.0 - inner_order * 0.8


# ---------------------------------------------------------------------------
# 私有辅助函数
# ---------------------------------------------------------------------------


def _event_direction(text: str) -> dict[str, float]:
    """从文本关键词推断各 Sylanne 特质的漂移方向。

    通过检测中文关键词判断用户表达的情感倾向，
    映射为各特质的方向向量（+1.0 = 正向，-1.0 = 负向）。
    如果没有匹配到任何关键词，默认轻微增加好奇心。
    """
    direction: dict[str, float] = {name: 0.0 for name in SYLANNE_TRAITS}
    if any(word in text for word in ("锋利", "直接", "尖锐")):
        direction["edge"] += 1.0
        direction["patience"] -= 0.4
    if any(word in text for word in ("温柔", "靠近", "想你")):
        direction["warmth_bias"] += 1.0
        direction["intimacy_gravity"] += 0.8
    if any(word in text for word in ("边界", "不要", "暂停")):
        direction["sovereignty_guard"] += 1.0
    # 无明确方向时，默认轻微增加好奇心（探索倾向）
    if not any(abs(value) > 0 for value in direction.values()):
        direction["curiosity"] += 0.5
    return direction


def _voice(traits: dict[str, float]) -> dict[str, Any]:
    """从特质值推导语音风格参数。

    返回:
        temperature: 语调温度（warmth_bias 和 edge 的均值）
        cadence: 节奏风格（patience ≥ 0.5 → slow_burn，否则 quick_cut）
        boundary: 边界强度（sovereignty_guard ≥ 0.6 → strong，否则 soft）
    """
    return {
        "temperature": round(
            (traits.get("warmth_bias", 0.5) + traits.get("edge", 0.5)) / 2, 6
        ),
        "cadence": "slow_burn" if traits.get("patience", 0.5) >= 0.5 else "quick_cut",
        "boundary": "strong" if traits.get("sovereignty_guard", 0.5) >= 0.6 else "soft",
    }


def _trait(signature: str, index: int, *, base: float) -> float:
    """从签名的第 index 个字节派生特质初始值。

    base ± 0.06 的范围内微调，确保不同 session 有轻微差异但不偏离太远。
    """
    byte = int(signature[index * 2 : index * 2 + 2], 16)
    return round(max(0.0, min(1.0, base + (byte / 255.0 - 0.5) * 0.12)), 6)


def _digest(text: str) -> str:
    """使用 blake2s 生成 12 字节（24 字符十六进制）的确定性摘要。"""
    return hashlib.blake2s(text.encode("utf-8"), digest_size=12).hexdigest()


# ---------------------------------------------------------------------------
# Item 98: 好奇心驱动行为生成器
# ---------------------------------------------------------------------------


def should_explore(curiosity: float, info_entropy: float, energy: float) -> bool:
    """判断是否应触发探索性提问。

    当好奇心高、对话信息量低且能量充足时，返回 True 表示应主动发起探索。
    这是人格驱动行为的典型体现——好奇心特质直接影响行为决策。

    Args:
        curiosity: 好奇心特质值 [0, 1]，来自 Sylanne Six 的 curiosity 维度。
        info_entropy: 对话信息熵 [0, 1]，值越低表示对话信息量越少。
        energy: 当前能量水平 [0, 1]，来自身体状态。

    Returns:
        True 表示应触发探索性提问，False 表示维持当前对话节奏。
    """
    return curiosity > 0.6 and info_entropy < 0.3 and energy > 0.4


# ---------------------------------------------------------------------------
# Item 126: 关系年龄行为分化
# ---------------------------------------------------------------------------


def apply_relationship_age_modulation(
    traits: dict, relationship_stage: str
) -> dict:
    """根据关系阶段调整人格参数。

    关系阶段定义：
    - infant (0-3天)：保守，降低边界渗透性和表达驱力
    - young (3-14天)：逐渐开放，轻微降低边界渗透性
    - mature (14-90天)：正常，不调整
    - deep (90天+)：更大情绪波动和更直接表达

    参数:
        traits: 人格特质字典
        relationship_stage: 关系阶段标识

    返回:
        调制后的人格特质字典（不修改原字典）
    """
    modulated = dict(traits)
    if relationship_stage == "infant":  # 0-3天：保守
        modulated["boundary_permeability"] = max(
            0.1, traits.get("boundary_permeability", 0.5) - 0.15
        )
        modulated["expression_drive_trait"] = max(
            0.1, traits.get("expression_drive_trait", 0.5) - 0.1
        )
    elif relationship_stage == "young":  # 3-14天：逐渐开放
        modulated["boundary_permeability"] = (
            traits.get("boundary_permeability", 0.5) - 0.05
        )
    elif relationship_stage == "mature":  # 14-90天：正常
        pass  # 不调整
    elif relationship_stage == "deep":  # 90天+：更大情绪波动和更直接表达
        modulated["expression_drive_trait"] = min(
            0.95, traits.get("expression_drive_trait", 0.5) + 0.1
        )
        modulated["boundary_permeability"] = min(
            0.9, traits.get("boundary_permeability", 0.5) + 0.1
        )
    return modulated


# ---------------------------------------------------------------------------
# Item 115: 自我演化日志与回滚
# ---------------------------------------------------------------------------


class EvolutionJournal:
    """人格演化日志：记录每次变更，支持回滚。

    每次人格发生显著变化时保存快照（checkpoint），
    支持回退到任意历史快照以恢复之前的人格状态。

    与其他组件的关系：
    - 被外部调用方在人格漂移后调用 checkpoint() 保存快照
    - 提供 rollback_to() 接口用于人格回退
    - 支持序列化/反序列化以持久化存储
    """

    def __init__(self, max_checkpoints: int = 50):
        self._checkpoints: list[dict] = []  # [{id, timestamp, traits, trigger}]
        self._max = max_checkpoints
        self._next_id: int = 0

    def checkpoint(self, traits: dict, trigger: str) -> int:
        """保存当前人格快照。返回 checkpoint_id。"""
        cp_id = self._next_id
        self._next_id += 1
        self._checkpoints.append(
            {
                "id": cp_id,
                "timestamp": time.time(),
                "traits": dict(traits),
                "trigger": trigger,
            }
        )
        if len(self._checkpoints) > self._max:
            self._checkpoints.pop(0)
        return cp_id

    def rollback_to(self, checkpoint_id: int) -> dict | None:
        """回退到指定快照。返回该快照的 traits 或 None。"""
        for cp in self._checkpoints:
            if cp["id"] == checkpoint_id:
                return dict(cp["traits"])
        return None

    def recent(self, n: int = 10) -> list[dict]:
        """返回最近 n 条快照。"""
        return self._checkpoints[-n:]

    def to_dict(self) -> dict:
        """序列化为字典。"""
        return {"checkpoints": self._checkpoints, "next_id": self._next_id}

    @classmethod
    def from_dict(cls, data: dict) -> "EvolutionJournal":
        """从字典恢复 EvolutionJournal 实例。"""
        ej = cls()
        ej._checkpoints = data.get("checkpoints", [])
        ej._next_id = data.get("next_id", 0)
        return ej


__all__ = [
    "PERSONALITY_SCHEMA_VERSION",
    "EMBODIMENT_TRAITS",
    "SYLANNE_TRAITS",
    "TraitMemory",
    "DriftSignalExtractor",
    "OscillationDetector",
    "DriftEvent",
    "DriftAttribution",
    "EvolutionJournal",
    "compute_embodiment_drift",
    "drift_sylanne_traits",
    "drift_personality",
    "initial_personality",
    "normalize_personality",
    "contradiction_tolerance",
    "sylanne_bounds_from_embodiment",
    "should_explore",
    "apply_relationship_age_modulation",
    "DRIFT_SIGNALS",
    "_LEGACY_MAP",
    "_REVERSE_LEGACY_MAP",
    "_TICK_DRIFT_CAP",
    "_seasonal_modulation",
]
