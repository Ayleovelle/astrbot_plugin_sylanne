"""向量工具函数模块。

定义 Sylanne 身体状态的向量空间基础设施：
- 状态轴 (STATE_AXES): 29 维身体状态向量，覆盖脉搏/需求/神经/血流/肌肉/温度/伤口/免疫/死亡率
- 事件轴 (EVENT_AXES): 9 维事件输入向量，描述一次交互的特征
- 权重矩阵 (WEIGHTS): 事件→状态的线性映射系数
- linear_delta: 核心状态演化函数，将事件向量通过权重矩阵投影为状态增量
"""

from __future__ import annotations

from collections.abc import Mapping


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """将数值限制在 [lo, hi] 区间内。

    Args:
        value: 待限制的浮点数
        lo: 下界（默认 0.0）
        hi: 上界（默认 1.0）

    Returns:
        限制后的浮点数
    """
    return max(lo, min(hi, float(value)))


# 身体状态向量的 29 个维度轴，按子系统分组：
# pulse(脉搏) → needs(需求) → nerve(神经) → bloodflow(血流)
# → muscle(肌肉) → temperature(温度) → wound(伤口) → immunity(免疫) → mortality(死亡率)
STATE_AXES = (
    "pulse.beat",
    "pulse.rhythm",
    "pulse.strain",
    "needs.need_contact",
    "needs.need_quiet",
    "needs.need_repair",
    "needs.need_expression",
    "nerve.plasticity",
    "nerve.sensitivity",
    "nerve.threshold_drift",
    "bloodflow.circulation",
    "bloodflow.memory_flow",
    "bloodflow.warmth",
    "muscle.trained_reach",
    "muscle.fatigue",
    "muscle.readiness",
    "temperature.warmth",
    "temperature.volatility",
    "temperature.repair_heat",
    "wound.open",
    "wound.repair",
    "wound.scar",
    "wound.sensitivity",
    "immunity.boundary_pressure",
    "immunity.cooldown",
    "immunity.interruption_budget",
    "mortality.load",
    "mortality.exhaustion",
    "mortality.recovery_debt",
)

# 事件输入向量的 9 个维度轴：
# elapsed(距上次事件的时间间隔) / has_text(是否有文本) / confidence(置信度)
# idle/safe/hurt/boundary/repair(事件标志位) / repetition(重复次数)
EVENT_AXES = (
    "elapsed",
    "has_text",
    "confidence",
    "idle",
    "safe",
    "hurt",
    "boundary",
    "repair",
    "repetition",
)

# 轴名→索引的快速查找表，用于 codec 二进制编码
STATE_INDEX = {axis: index for index, axis in enumerate(STATE_AXES)}
EVENT_INDEX = {axis: index for index, axis in enumerate(EVENT_AXES)}

# 权重矩阵：定义每个事件维度对每个状态维度的影响系数
# 例如 "needs.need_repair": {"hurt": 0.24, "repair": -0.05}
# 表示 hurt 事件使修复需求增加 0.24，repair 事件使其减少 0.05
WEIGHTS: dict[str, dict[str, float]] = {
    "pulse.beat": {"elapsed": 1.0},
    "pulse.rhythm": {"elapsed": 0.01, "hurt": -0.03},
    "pulse.strain": {"boundary": 0.08, "hurt": 0.08, "safe": -0.03},
    "needs.need_contact": {"idle": 0.2, "has_text": 0.03, "safe": -0.08},
    "needs.need_quiet": {"boundary": 0.08, "hurt": 0.04, "safe": -0.04},
    "needs.need_repair": {"hurt": 0.24, "repair": -0.05},
    "needs.need_expression": {"has_text": 0.12, "idle": 0.02},
    "nerve.plasticity": {"has_text": 0.05, "repetition": 0.05, "idle": 0.01},
    "nerve.sensitivity": {"hurt": 0.04, "has_text": 0.01, "safe": -0.02},
    "nerve.threshold_drift": {"repetition": 0.02, "safe": -0.01},
    "bloodflow.circulation": {"has_text": 0.08, "confidence": 0.05},
    "bloodflow.memory_flow": {"has_text": 0.04, "repetition": 0.02},
    "bloodflow.warmth": {"safe": 0.06, "hurt": -0.02},
    "muscle.trained_reach": {"has_text": 0.02, "repetition": 0.04},
    "muscle.fatigue": {"idle": 0.03, "safe": -0.04},
    "muscle.readiness": {"has_text": 0.08, "idle": -0.04},
    "temperature.warmth": {"safe": 0.05, "hurt": -0.05},
    "temperature.volatility": {"boundary": 0.08, "safe": -0.03},
    "temperature.repair_heat": {"repair": 0.1, "safe": -0.03},
    "wound.open": {"hurt": 0.22, "repair": -0.06},
    "wound.repair": {"repair": 0.15, "hurt": 0.02},
    "wound.scar": {"hurt": 0.02},
    "wound.sensitivity": {"hurt": 0.15},
    "immunity.boundary_pressure": {"boundary": 0.25, "hurt": 0.04, "safe": -0.04},
    "immunity.cooldown": {"idle": 0.08, "safe": -0.1},
    "immunity.interruption_budget": {"idle": -0.04, "safe": 0.03},
    "mortality.load": {"boundary": 0.03, "hurt": 0.02, "safe": -0.03},
    "mortality.exhaustion": {"idle": 0.02, "safe": -0.04},
    "mortality.recovery_debt": {"idle": 0.01, "repair": -0.03},
}


# 预编译的权重查找表：将 WEIGHTS 字典转为 (状态索引, ((事件索引, 权重), ...)) 元组
# 避免每次 linear_delta 调用时重复做字典查找，提升热路径性能
WEIGHT_TERMS: tuple[tuple[int, tuple[tuple[int, float], ...]], ...] = tuple(
    (
        STATE_INDEX[axis],
        tuple(
            (EVENT_INDEX[event_axis], weight) for event_axis, weight in weights.items()
        ),
    )
    for axis, weights in WEIGHTS.items()
)


def linear_delta(event: Mapping[str, float]) -> dict[str, float]:
    """通过权重矩阵将事件向量线性投影为状态增量。

    这是身体状态演化的核心函数：每次交互事件发生时，
    将 9 维事件向量乘以权重矩阵，得到 29 维状态增量向量。

    Args:
        event: 事件向量，键为 EVENT_AXES 中的轴名

    Returns:
        状态增量字典，键为 STATE_AXES 中的轴名，值为该轴的变化量
    """
    event_values = tuple(float(event.get(axis, 0.0)) for axis in EVENT_AXES)
    delta_values = [0.0] * len(STATE_AXES)
    for state_index, terms in WEIGHT_TERMS:
        # 对每个状态轴，累加所有相关事件维度的加权贡献
        delta_values[state_index] = sum(
            event_values[event_index] * weight for event_index, weight in terms
        )
    return {axis: delta_values[index] for index, axis in enumerate(STATE_AXES)}
