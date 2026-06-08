"""Sylanne-Embodiment 计算核心层：热池与人格坍缩（Hot Pool & Personality Collapse）。

在 7 层计算栈中的位置：跨层子系统，连接 L3（VoidScar）、L5（Body）、L6（Autopoiesis）。
职责：积累未解决的情感材料（热材料），当热池温度和压力超过临界阈值时，
触发级联放大（cascade），最终可能导致人格坍缩（personality collapse）——
一种不可逆的人格空间相变。

核心概念：
  - HotMaterial（热材料）：单个未解决的情感碎片，有热度、质量、年龄
  - HotPool（热池）：热材料的容器，具有温度/体积/压力热力学
  - CascadeState（级联状态）：放大级联的追踪器，控制灵敏度倍增
  - CollapseRecord（坍缩记录）：人格坍缩事件的不可变记录

与其他组件的关系：
  - 接收外部影响注入（来自 memory_plugin、dialogue_agent 等）
  - 通过 feed_body() 将热力学状态推入身体子系统
  - 通过 cascade 状态影响 ComputationSpine 的漂移速率
  - 坍缩时直接修改人格特质（绕过正常漂移上限）
"""

from __future__ import annotations

import itertools
import math
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from .vector import clamp as _clamp

# ---------------------------------------------------------------------------
# 类型定义
# ---------------------------------------------------------------------------

InfluenceType = Literal[
    "contradiction",  # 已反思材料被对立证据重新点燃
    "reinforcement",  # 现有材料被确认证据强化
    "revelation",  # 重新框架化现有材料的新信息
    "betrayal",  # 信任违背，将温材料转为热材料
    "validation",  # 外部认可，冷却材料
]

_VALID_INFLUENCE_TYPES: frozenset[str] = frozenset(
    ("contradiction", "reinforcement", "revelation", "betrayal", "validation")
)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

# _clamp is from vector.py — same signature (value, lo=0.0, hi=1.0).
# vector.py's version additionally handles NaN/Inf → lo, which is a strict superset.

# Monotonic counter for generating unique material IDs within the same process.
_material_id_counter = itertools.count()


def _safe_float(value: Any, default: float = 0.0) -> float:
    """安全转换为有限浮点数。"""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(f):
        return default
    return f


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Influence:
    """单个外部影响注入——来自其他插件的信号。

    Attributes:
        source: 插件标识符（如 "memory_plugin", "dialogue_agent"）
        type: 语义类别
        intensity: [0, 1] — 影响强度
        target_dimension: 目标身体轴或热池维度
        payload: 不透明元数据
        timestamp: 注入时间戳
    """

    source: str
    type: InfluenceType
    intensity: float
    target_dimension: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass(slots=True)
class HotMaterial:
    """单个未解决的情感材料——热池中的基本单元。

    生命周期：创建 → 加热/冷却 → 反思 → 消亡（或坍缩处理）。
    热度和质量共同决定材料对热池温度的贡献。

    Attributes:
        id: 唯一标识符（如 "wound_20240315_001"）
        origin_type: 创建来源类型
        heat: [0, 1] — 当前热强度
        mass: [0, 1] — 未处理内容量
        age_ticks: 自创建以来的 tick 数
        last_ignition: 上次重新点燃的时间戳
        reflection_count: 被反思（冷却）的次数
        peak_heat: 历史最高热度（用于伤痕计算）
        source_text_hash: 来源文本哈希（用于矛盾检测）
    """

    id: str
    origin_type: str
    heat: float = 0.0
    mass: float = 0.0
    age_ticks: int = 0
    last_ignition: float = 0.0
    reflection_count: int = 0
    peak_heat: float = 0.0
    source_text_hash: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "origin_type": self.origin_type,
            "heat": round(self.heat, 6),
            "mass": round(self.mass, 6),
            "age_ticks": self.age_ticks,
            "last_ignition": self.last_ignition,
            "reflection_count": self.reflection_count,
            "peak_heat": round(self.peak_heat, 6),
            "source_text_hash": self.source_text_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HotMaterial:
        return cls(
            id=data.get("id", "unknown"),
            origin_type=data.get("origin_type", "unknown"),
            heat=_safe_float(data.get("heat"), 0.0),
            mass=_safe_float(data.get("mass"), 0.0),
            age_ticks=int(data.get("age_ticks", 0)),
            last_ignition=_safe_float(data.get("last_ignition"), 0.0),
            reflection_count=int(data.get("reflection_count", 0)),
            peak_heat=_safe_float(data.get("peak_heat"), 0.0),
            source_text_hash=int(data.get("source_text_hash", 0)),
        )


@dataclass(slots=True)
class CascadeState:
    """级联放大状态追踪器。

    当热池的 temperature * pressure 超过 cascade_trigger 时，级联激活。
    级联期间所有传入信号被放大（sensitivity_multiplier），
    且人格漂移速率提升 10 倍。

    Attributes:
        active: 级联是否激活
        intensity: [0, 1] — 当前级联强度
        momentum: [0, 1] — 惯性，防止级联立即停止
        ticks_above_critical: 连续超过坍缩阈值的 tick 数
        sensitivity_multiplier: 传入信号的放大因子
        peak_intensity: 历史最高强度（诊断用）
    """

    active: bool = False
    intensity: float = 0.0
    momentum: float = 0.0
    ticks_above_critical: int = 0
    sensitivity_multiplier: float = 1.0
    peak_intensity: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "intensity": round(self.intensity, 6),
            "momentum": round(self.momentum, 6),
            "ticks_above_critical": self.ticks_above_critical,
            "sensitivity_multiplier": round(self.sensitivity_multiplier, 6),
            "peak_intensity": round(self.peak_intensity, 6),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CascadeState:
        return cls(
            active=bool(data.get("active", False)),
            intensity=_safe_float(data.get("intensity"), 0.0),
            momentum=_safe_float(data.get("momentum"), 0.0),
            ticks_above_critical=int(data.get("ticks_above_critical", 0)),
            sensitivity_multiplier=_safe_float(data.get("sensitivity_multiplier"), 1.0),
            peak_intensity=_safe_float(data.get("peak_intensity"), 0.0),
        )

    def reset(self) -> None:
        """重置级联状态（坍缩后调用）。"""
        self.active = False
        self.intensity = 0.0
        self.momentum = 0.0
        self.ticks_above_critical = 0
        self.sensitivity_multiplier = 1.0


@dataclass(slots=True)
class CollapseRecord:
    """人格坍缩事件的不可变记录。

    坍缩是人格空间中的相变——多个特质同时发生大幅度、不可逆的偏移。
    记录保存坍缩前后的完整人格快照，用于诊断和历史追踪。

    Attributes:
        timestamp: 坍缩发生时间
        trigger_temperature: 触发时的热池温度
        trigger_pressure: 触发时的热池压力
        cascade_duration_ticks: 级联持续的 tick 数
        pre_collapse_traits: 坍缩前的人格特质快照
        post_collapse_traits: 坍缩后的人格特质快照
        trait_deltas: 各特质的变化量
        recovery_ticks_remaining: 恢复期剩余 tick 数
        collapse_tick: 坍缩发生时的热池 tick 编号
    """

    timestamp: float
    trigger_temperature: float
    trigger_pressure: float
    cascade_duration_ticks: int
    pre_collapse_traits: dict[str, float]
    post_collapse_traits: dict[str, float]
    trait_deltas: dict[str, float]
    recovery_ticks_remaining: int
    collapse_tick: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "trigger_temperature": round(self.trigger_temperature, 6),
            "trigger_pressure": round(self.trigger_pressure, 6),
            "cascade_duration_ticks": self.cascade_duration_ticks,
            "pre_collapse_traits": {k: round(v, 6) for k, v in self.pre_collapse_traits.items()},
            "post_collapse_traits": {k: round(v, 6) for k, v in self.post_collapse_traits.items()},
            "trait_deltas": {k: round(v, 6) for k, v in self.trait_deltas.items()},
            "recovery_ticks_remaining": self.recovery_ticks_remaining,
            "collapse_tick": self.collapse_tick,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CollapseRecord:
        return cls(
            timestamp=_safe_float(data.get("timestamp"), 0.0),
            trigger_temperature=_safe_float(data.get("trigger_temperature"), 0.0),
            trigger_pressure=_safe_float(data.get("trigger_pressure"), 0.0),
            cascade_duration_ticks=int(data.get("cascade_duration_ticks", 0)),
            pre_collapse_traits=data.get("pre_collapse_traits", {}),
            post_collapse_traits=data.get("post_collapse_traits", {}),
            trait_deltas=data.get("trait_deltas", {}),
            recovery_ticks_remaining=int(data.get("recovery_ticks_remaining", 0)),
            collapse_tick=int(data.get("collapse_tick", 0)),
        )


# ---------------------------------------------------------------------------
# 热池引擎
# ---------------------------------------------------------------------------

_SCHEMA_VERSION = "sylanne.alpha.hot_pool.v1"

# 模式对应的最大材料数
_MODE_MAX_MATERIALS: dict[str, int] = {"lite": 8, "pro": 16, "max": 32}


class HotPool:
    """热池（Hot Pool）计算引擎。

    热池是未解决情感材料的容器。它具有三个宏观热力学量：
      - temperature（温度）：所有材料的质量加权平均热度
      - volume（体积）：总未处理质量
      - pressure（压力）：时间压缩的紧迫感

    当 temperature * pressure 超过 cascade_trigger 时，级联放大激活。
    级联持续超过 collapse_threshold 达到足够 tick 数后，触发人格坍缩。

    与 scar_algebra.py 和 void_calculus.py 风格一致：
    纯 Python、__slots__、详细文档字符串、数值精度。
    """

    __slots__ = (
        # 宏观热力学
        "_temperature",
        "_volume",
        "_pressure",
        # 材料存储
        "_materials",
        "_max_materials",
        # 级联子系统
        "_cascade",
        # 坍缩历史
        "_collapse_history",
        "_in_recovery",
        "_recovery_ticks_remaining",
        # 人格派生参数
        "_collapse_threshold",
        "_cascade_trigger",
        "_decay_rate",
        "_pressure_growth_rate",
        "_validation_effectiveness",
        "_neuroticism",
        # 内部计数器
        "_tick",
        # 维度数（模式感知）
        "_n_dims",
    )

    def __init__(self, n_dims: int = 16, mode: str = "pro"):
        """初始化热池。

        Args:
            n_dims: 材料容量维度（由 mode 决定，也可直接指定）。
            mode: 运行模式 ("lite", "pro", "max")，决定 max_materials。
        """
        self._n_dims: int = n_dims
        self._max_materials: int = _MODE_MAX_MATERIALS.get(mode, n_dims)

        # 宏观热力学量
        self._temperature: float = 0.0
        self._volume: float = 0.0
        self._pressure: float = 0.0

        # 材料存储
        self._materials: list[HotMaterial] = []

        # 级联子系统
        self._cascade: CascadeState = CascadeState()

        # 坍缩历史
        self._collapse_history: list[CollapseRecord] = []
        self._in_recovery: bool = False
        self._recovery_ticks_remaining: int = 0

        # 人格派生参数（默认值，由 apply_personality 覆盖）
        self._collapse_threshold: float = 0.75
        self._cascade_trigger: float = 0.6
        self._decay_rate: float = 0.02
        self._pressure_growth_rate: float = 0.01
        self._validation_effectiveness: float = 0.4
        self._neuroticism: float = 0.5

        # 内部计数器
        self._tick: int = 0

    # ------------------------------------------------------------------
    # 属性访问（只读）
    # ------------------------------------------------------------------

    @property
    def temperature(self) -> float:
        """当前热池温度 [0, 1]。"""
        return self._temperature

    @property
    def volume(self) -> float:
        """当前热池体积 [0, 1]。"""
        return self._volume

    @property
    def pressure(self) -> float:
        """当前热池压力 [0, 1]。"""
        return self._pressure

    @property
    def cascade(self) -> CascadeState:
        """级联状态引用。"""
        return self._cascade

    @property
    def in_recovery(self) -> bool:
        """是否处于坍缩后恢复期。"""
        return self._in_recovery

    @property
    def recovery_ticks_remaining(self) -> int:
        """恢复期剩余 tick 数。"""
        return self._recovery_ticks_remaining

    @property
    def materials(self) -> list[HotMaterial]:
        """当前材料列表（只读引用）。"""
        return self._materials

    @property
    def collapse_history(self) -> list[CollapseRecord]:
        """坍缩历史记录。"""
        return self._collapse_history

    # ------------------------------------------------------------------
    # 人格参数派生
    # ------------------------------------------------------------------

    def apply_personality(self, personality: dict[str, float]) -> None:
        """从人格特质派生热池内部阈值。

        映射关系：
          - 神经质 ↑ → cascade_trigger ↓, collapse_threshold ↓（更易触发）
          - 尽责性 ↑ → decay_rate ↑（更好的自我调节/冷却）
          - 开放性 ↑ → pressure_growth_rate ↓（更能容忍模糊性）
          - 宜人性 ↑ → validation_effectiveness ↑（认可更有效）

        Args:
            personality: 大五人格特质字典，值域 [0, 1]。
        """
        neuroticism = _safe_float(personality.get("neuroticism"), 0.5)
        conscientiousness = _safe_float(personality.get("conscientiousness"), 0.5)
        openness = _safe_float(personality.get("openness"), 0.5)
        agreeableness = _safe_float(personality.get("agreeableness"), 0.5)

        self._neuroticism = _clamp(neuroticism)

        # 神经质：降低级联触发和坍缩阈值
        # cascade_trigger 范围: [0.4, 0.8]
        self._cascade_trigger = 0.8 - neuroticism * 0.4
        # collapse_threshold 范围: [0.6, 0.9]
        self._collapse_threshold = 0.9 - neuroticism * 0.3

        # 尽责性：加速冷却（更好的自我调节）
        # decay_rate 范围: [0.01, 0.04]
        self._decay_rate = 0.01 + conscientiousness * 0.03

        # 开放性：减缓压力积累（更能容忍模糊性）
        # pressure_growth_rate 范围: [0.01, 0.02]
        self._pressure_growth_rate = 0.02 - openness * 0.01

        # 宜人性：认可更有效
        # validation_effectiveness 范围: [0.3, 0.5]
        self._validation_effectiveness = 0.3 + agreeableness * 0.2

    # ------------------------------------------------------------------
    # 影响接收
    # ------------------------------------------------------------------

    def receive_influence(
        self,
        influence: Influence,
        body: Any = None,
        personality: dict[str, float] | None = None,
    ) -> None:
        """处理一个传入的外部影响。

        根据影响类型执行不同的热注入逻辑：
          - contradiction: 重新点燃已有材料（乘性增强）
          - reinforcement: 温和加热 + 增加质量
          - revelation: 创建新材料或大幅加热已有材料
          - betrayal: 热尖峰——所有材料升温 + 创建高热新材料
          - validation: 冷却效应——降低所有材料热度

        有效强度受级联灵敏度倍增器放大。

        Args:
            influence: 已解析的 Influence 对象。
            body: 可选的身体状态引用（当前未使用，预留扩展）。
            personality: 可选的人格特质字典（用于动态调整）。
        """
        now = influence.timestamp if influence.timestamp > 0 else time.time()

        # 有效强度：受级联放大
        eff_intensity = _clamp(influence.intensity * self._cascade.sensitivity_multiplier)

        inf_type = influence.type if influence.type in _VALID_INFLUENCE_TYPES else "reinforcement"

        if inf_type == "contradiction":
            self._receive_contradiction(eff_intensity, influence.target_dimension, now)
        elif inf_type == "reinforcement":
            self._receive_reinforcement(eff_intensity, influence.target_dimension, now)
        elif inf_type == "revelation":
            self._receive_revelation(eff_intensity, influence.target_dimension, now)
        elif inf_type == "betrayal":
            self._receive_betrayal(eff_intensity, influence.target_dimension, now)
        elif inf_type == "validation":
            self._receive_validation(eff_intensity)

    def _receive_contradiction(self, eff_intensity: float, target_dim: str, now: float) -> None:
        """矛盾：重新点燃已有材料，反思计数归零。

        如果找到匹配的材料（按 target_dimension 或 origin_type），
        则乘性增强其热度。否则创建新材料。
        """
        heat_delta = eff_intensity * 0.8
        target = self._find_material_by_dimension(target_dim)
        if target is not None:
            # 矛盾超越原始：乘性增强，反思次数越多增强越大
            boost = 1.0 + target.reflection_count * 0.15
            target.heat = _clamp(target.heat + heat_delta * boost)
            target.peak_heat = max(target.peak_heat, target.heat)
            target.last_ignition = now
            target.reflection_count = 0  # 撤销之前的反思冷却
        else:
            self._add_material(
                HotMaterial(
                    id=f"contradiction_{time.time_ns()}_{next(_material_id_counter)}",
                    origin_type="contradiction",
                    heat=_clamp(heat_delta),
                    mass=_clamp(eff_intensity * 0.4),
                    peak_heat=heat_delta,
                    last_ignition=now,
                )
            )

    def _receive_reinforcement(self, eff_intensity: float, target_dim: str, now: float) -> None:
        """强化：温和加热 + 增加质量。"""
        heat_delta = eff_intensity * 0.5
        target = self._find_material_by_dimension(target_dim)
        if target is not None:
            target.heat = _clamp(target.heat + heat_delta)
            target.mass = _clamp(target.mass + eff_intensity * 0.3)
            target.peak_heat = max(target.peak_heat, target.heat)
        else:
            self._add_material(
                HotMaterial(
                    id=f"reinforcement_{time.time_ns()}_{next(_material_id_counter)}",
                    origin_type="reinforcement",
                    heat=_clamp(heat_delta),
                    mass=_clamp(eff_intensity * 0.3),
                    peak_heat=heat_delta,
                    last_ignition=now,
                )
            )

    def _receive_revelation(self, eff_intensity: float, target_dim: str, now: float) -> None:
        """启示：创建新材料或大幅加热已有材料。"""
        heat_delta = eff_intensity * 0.7
        mass_delta = eff_intensity * 0.5
        target = self._find_material_by_dimension(target_dim)
        if target is not None:
            target.heat = _clamp(target.heat + heat_delta)
            target.mass = _clamp(target.mass + mass_delta)
            target.peak_heat = max(target.peak_heat, target.heat)
            target.last_ignition = now
        else:
            self._add_material(
                HotMaterial(
                    id=f"revelation_{time.time_ns()}_{next(_material_id_counter)}",
                    origin_type="revelation",
                    heat=_clamp(heat_delta),
                    mass=_clamp(mass_delta),
                    peak_heat=heat_delta,
                    last_ignition=now,
                )
            )

    def _receive_betrayal(self, eff_intensity: float, target_dim: str, now: float) -> None:
        """背叛：热尖峰——所有现有材料升温 + 创建高热新材料。

        背叛将所有温材料转为热材料（全局热注入），
        同时创建一个高热度、高质量的新材料。
        """
        # 全局热注入：所有现有材料升温
        for mat in self._materials:
            mat.heat = _clamp(mat.heat + eff_intensity * 0.6)
            mat.peak_heat = max(mat.peak_heat, mat.heat)

        # 创建新的高热材料
        heat_delta = eff_intensity * 0.9
        mass_delta = eff_intensity * 0.7
        self._add_material(
            HotMaterial(
                id=f"betrayal_{time.time_ns()}_{next(_material_id_counter)}",
                origin_type="betrayal",
                heat=_clamp(heat_delta),
                mass=_clamp(mass_delta),
                peak_heat=heat_delta,
                last_ignition=now,
            )
        )

    def _receive_validation(self, eff_intensity: float) -> None:
        """认可：冷却效应——降低所有材料热度。

        冷却强度受宜人性调制的 validation_effectiveness 影响。
        """
        cooling_factor = eff_intensity * self._validation_effectiveness
        for mat in self._materials:
            mat.heat *= max(0.3, 1.0 - cooling_factor)

    # ------------------------------------------------------------------
    # 材料管理
    # ------------------------------------------------------------------

    def _find_material_by_dimension(self, target_dim: str) -> HotMaterial | None:
        """按目标维度查找匹配的材料。

        匹配逻辑：target_dimension 包含在材料的 origin_type 或 id 中，
        或者 origin_type 包含在 target_dimension 中。
        """
        if not target_dim:
            return None
        for mat in self._materials:
            if (
                target_dim in mat.id
                or target_dim in mat.origin_type
                or mat.origin_type in target_dim
            ):
                return mat
        return None

    def _add_material(self, material: HotMaterial) -> None:
        """添加材料到热池，遵守容量上限。

        当达到上限时，移除热度最低的材料为新材料腾出空间。
        """
        if len(self._materials) >= self._max_materials:
            # 淘汰热度最低的材料
            if self._materials:
                min_idx = 0
                min_heat = self._materials[0].heat
                for i in range(1, len(self._materials)):
                    if self._materials[i].heat < min_heat:
                        min_heat = self._materials[i].heat
                        min_idx = i
                self._materials.pop(min_idx)
        self._materials.append(material)

    # ------------------------------------------------------------------
    # 反思（外部冷却接口）
    # ------------------------------------------------------------------

    def reflect(self, material_id: str, cooling_factor: float = 0.3) -> bool:
        """标记材料为已反思（部分处理/冷却）。

        反思降低材料热度并增加反思计数。反思计数越高，
        未来的被动冷却越快（但矛盾重新点燃时会归零）。

        Args:
            material_id: 目标材料 ID。
            cooling_factor: 冷却强度 [0, 1]，默认 0.3。

        Returns:
            是否找到并处理了目标材料。
        """
        cooling_factor = _clamp(cooling_factor)
        for mat in self._materials:
            if mat.id == material_id:
                mat.heat = max(0.0, mat.heat * (1.0 - cooling_factor))
                mat.reflection_count += 1
                return True
        return False

    # ------------------------------------------------------------------
    # 核心 tick（每步热力学演化）
    # ------------------------------------------------------------------

    def tick(self, body: Any = None, spine: Any = None) -> CollapseRecord | None:
        """推进热池状态一个 tick。

        执行顺序：
          1. 被动冷却（指数衰减）
          2. 清除死亡材料
          3. 计算宏观热力学量
          4. 级联逻辑（激活/演化/终止）
          5. 推入身体状态
          6. 级联对漂移速率的影响
          7. 检查坍缩条件
          8. 恢复期倒计时

        Args:
            body: 身体状态对象（用于 feed_body）。
            spine: 计算脊柱对象（用于漂移速率调制）。

        Returns:
            如果触发坍缩，返回 CollapseRecord；否则返回 None。
        """
        self._tick += 1

        # --- Step 1: 被动冷却 ---
        for mat in self._materials:
            mat.age_ticks += 1
            # 基础衰减：指数冷却，反思次数加速冷却
            cooling = self._decay_rate * (1.0 + mat.reflection_count * 0.2)
            mat.heat = max(0.0, mat.heat - cooling)
            # 低热度时质量缓慢溶解
            if mat.heat < 0.1:
                mat.mass = max(0.0, mat.mass - 0.01)

        # --- Step 2: 清除死亡材料（热度=0 且 质量=0）---
        self._materials = [m for m in self._materials if m.heat > 0.001 or m.mass > 0.01]

        # --- Step 3: 计算宏观热力学量 ---
        if self._materials:
            total_mass = sum(m.mass for m in self._materials)
            self._volume = _clamp(total_mass)
            # 温度 = 质量加权平均热度
            if total_mass > 0.001:
                self._temperature = sum(m.heat * m.mass for m in self._materials) / total_mass
            else:
                self._temperature = 0.0
            # 压力随时间和体积增长（未解决材料积累紧迫感）
            self._pressure = _clamp(self._pressure + self._pressure_growth_rate * self._volume)
            # 低温时压力衰减
            if self._temperature < 0.2:
                self._pressure = max(0.0, self._pressure - 0.02)
        else:
            self._temperature *= 0.9
            self._volume = 0.0
            self._pressure = max(0.0, self._pressure - 0.03)

        # --- Step 4: 级联逻辑 ---
        cascade_score = self._temperature * self._pressure
        self._evolve_cascade(cascade_score)

        # --- Step 5: 推入身体状态 ---
        if body is not None:
            self.feed_body(body)

        # --- Step 6: 级联对漂移速率的影响 ---
        if spine is not None:
            self._modulate_drift_rate(spine)

        # --- Step 7: 检查坍缩条件 ---
        collapse_ticks_required = self._collapse_ticks_required()
        if self._cascade.ticks_above_critical >= collapse_ticks_required:
            return self._trigger_collapse()

        # --- Step 8: 恢复期倒计时 ---
        if self._in_recovery:
            self._recovery_ticks_remaining -= 1
            if self._recovery_ticks_remaining <= 0:
                self._in_recovery = False
                self._recovery_ticks_remaining = 0

        return None

    # ------------------------------------------------------------------
    # 级联演化
    # ------------------------------------------------------------------

    def _evolve_cascade(self, cascade_score: float) -> None:
        """演化级联状态。

        级联激活条件：cascade_score > cascade_trigger 且当前未激活。
        级联演化：灵敏度倍增器随强度增长（上限 3.0）。
        级联终止：cascade_score 降到 trigger 以下且动量耗尽。
        """
        c = self._cascade

        # 激活检查
        if cascade_score > self._cascade_trigger and not c.active:
            c.active = True
            c.intensity = cascade_score
            c.momentum = 0.5
            c.sensitivity_multiplier = 1.5

        if not c.active:
            return

        # 级联演化
        c.intensity = max(c.intensity, cascade_score)
        c.peak_intensity = max(c.peak_intensity, c.intensity)

        # 灵敏度放大：随持续级联增长，硬上限 3.0
        c.sensitivity_multiplier = _clamp(1.0 + c.intensity * 2.0, lo=1.0, hi=3.0)

        # 动量逻辑
        if cascade_score < self._cascade_trigger:
            # 低于触发阈值但动量维持级联
            c.momentum = max(0.0, c.momentum - 0.1)
            if c.momentum <= 0.0:
                # 级联终止
                c.active = False
                c.sensitivity_multiplier = 1.0
                c.ticks_above_critical = 0
        else:
            # 仍在触发阈值之上：动量增长
            c.momentum = min(1.0, c.momentum + 0.05)

        # 追踪超过坍缩阈值的连续 tick 数
        if c.active:
            if c.intensity > self._collapse_threshold:
                c.ticks_above_critical += 1
            else:
                c.ticks_above_critical = max(0, c.ticks_above_critical - 1)

    # ------------------------------------------------------------------
    # 坍缩逻辑
    # ------------------------------------------------------------------

    def _collapse_ticks_required(self) -> int:
        """人格影响的坍缩阈值（所需连续 tick 数）。

        神经质人格坍缩更快（所需 tick 数更少）。
        基础：15 ticks。范围：[5, 25]。
        """
        # 高神经质 = 更少的 tick 需求
        return max(5, int(25 - self._neuroticism * 20))

    def _trigger_collapse(self) -> CollapseRecord:
        """执行人格坍缩——人格空间中的相变。

        坍缩方向由热池中的主导材料类型决定：
          - 背叛主导：主权 ↑, 宜人性 ↓, 神经质 ↑
          - 矛盾主导：开放性 ↑, 尽责性 ↓
          - 伤口主导：退缩模式（外向性 ↓↓, 神经质 ↑↑）

        坍缩后：
          - 进入恢复期（人格流动性增加）
          - 级联重置
          - 材料部分排空（坍缩"处理"了部分材料）
        """
        # 统计主导材料类型（按 heat * mass 加权）
        type_weights: dict[str, float] = {}
        for mat in self._materials:
            w = mat.heat * mat.mass
            type_weights[mat.origin_type] = type_weights.get(mat.origin_type, 0.0) + w

        # 计算坍缩幅度（上限 0.4）
        collapse_magnitude = min(0.4, self._cascade.intensity * 0.5)

        # 根据主导类型确定特质偏移方向
        betrayal_weight = type_weights.get("betrayal", 0.0)
        contradiction_weight = type_weights.get("contradiction", 0.0)
        wound_weight = type_weights.get("wound", 0.0)

        if betrayal_weight > contradiction_weight and betrayal_weight > wound_weight:
            # 背叛主导坍缩：主权 ↑, 宜人性 ↓, 神经质 ↑
            trait_deltas = {
                "extraversion": -collapse_magnitude * 0.6,
                "agreeableness": -collapse_magnitude * 0.8,
                "neuroticism": +collapse_magnitude * 0.7,
                "openness": -collapse_magnitude * 0.4,
                "conscientiousness": +collapse_magnitude * 0.3,
            }
        elif contradiction_weight > wound_weight:
            # 矛盾主导坍缩：开放性 ↑, 尽责性 ↓
            trait_deltas = {
                "extraversion": -collapse_magnitude * 0.3,
                "agreeableness": -collapse_magnitude * 0.4,
                "neuroticism": +collapse_magnitude * 0.5,
                "openness": +collapse_magnitude * 0.6,
                "conscientiousness": -collapse_magnitude * 0.5,
            }
        else:
            # 伤口主导坍缩：退缩模式
            trait_deltas = {
                "extraversion": -collapse_magnitude * 0.8,
                "agreeableness": -collapse_magnitude * 0.3,
                "neuroticism": +collapse_magnitude * 0.9,
                "openness": -collapse_magnitude * 0.5,
                "conscientiousness": +collapse_magnitude * 0.2,
            }

        # 进入恢复期
        recovery_ticks = max(30, int(60 * self._cascade.intensity))
        self._in_recovery = True
        self._recovery_ticks_remaining = recovery_ticks

        # 保存级联持续时间（reset 会清零，必须在 reset 之前读取）
        cascade_duration = self._cascade.ticks_above_critical

        # 重置级联
        self._cascade.reset()

        # 排空热池（坍缩处理了部分材料）
        for mat in self._materials:
            mat.heat *= 0.3  # 残余热度
            mat.mass *= 0.5  # 一半材料被"处理"

        # 构建坍缩记录
        record = CollapseRecord(
            timestamp=time.time(),
            trigger_temperature=self._temperature,
            trigger_pressure=self._pressure,
            cascade_duration_ticks=cascade_duration,
            pre_collapse_traits={},  # 由调用方填充
            post_collapse_traits={},  # 由调用方填充
            trait_deltas=trait_deltas,
            recovery_ticks_remaining=recovery_ticks,
            collapse_tick=self._tick,
        )
        # 限制历史记录长度，防止长会话无限增长
        if len(self._collapse_history) >= 50:
            self._collapse_history = self._collapse_history[-49:]
        self._collapse_history.append(record)

        return record

    # ------------------------------------------------------------------
    # 身体集成
    # ------------------------------------------------------------------

    def feed_body(self, body: Any) -> None:
        """将热池热力学状态推入身体子系统。

        映射关系（增量式，不覆盖）：
          - temperature → body.temperature.volatility（波动性贡献）
          - pressure → body.immunity.boundary_pressure（边界压力贡献）
          - cascade.active → body.mortality.load + body.pulse.strain
          - in_recovery → body.immunity.sovereignty（脆弱性）

        Args:
            body: AlphaBodyState 实例。
        """
        # 温度 → 波动性
        if hasattr(body, "temperature") and hasattr(body.temperature, "volatility"):
            volatility_contribution = self._temperature * 0.3
            body.temperature.volatility = _clamp(
                body.temperature.volatility + volatility_contribution * 0.1
            )

        # 压力 → 边界压力
        if hasattr(body, "immunity") and hasattr(body.immunity, "boundary_pressure"):
            pressure_contribution = self._pressure * 0.2
            body.immunity.boundary_pressure = _clamp(
                body.immunity.boundary_pressure + pressure_contribution * 0.05
            )

        # 级联 → 死亡率负荷 + 应激
        if self._cascade.active:
            if hasattr(body, "mortality") and hasattr(body.mortality, "load"):
                body.mortality.load = _clamp(body.mortality.load + self._cascade.intensity * 0.1)
            if hasattr(body, "pulse") and hasattr(body.pulse, "strain"):
                body.pulse.strain = _clamp(body.pulse.strain + self._cascade.intensity * 0.05)

        # 恢复期 → 降低主权（脆弱性）
        if self._in_recovery:
            if hasattr(body, "immunity") and hasattr(body.immunity, "sovereignty"):
                recovery_factor = self._recovery_ticks_remaining / 60.0
                body.immunity.sovereignty = _clamp(
                    body.immunity.sovereignty - recovery_factor * 0.1
                )

    def body_deltas(self) -> dict[str, float]:
        """返回热池对身体各维度的增量贡献（不直接修改身体）。

        用于不持有身体引用时的集成场景。

        Returns:
            字典，键为 "subsystem.field" 格式，值为增量。
        """
        deltas: dict[str, float] = {}

        # 温度 → 波动性
        deltas["temperature.volatility"] = self._temperature * 0.3 * 0.1

        # 压力 → 边界压力
        deltas["immunity.boundary_pressure"] = self._pressure * 0.2 * 0.05

        # 级联贡献
        if self._cascade.active:
            deltas["mortality.load"] = self._cascade.intensity * 0.1
            deltas["pulse.strain"] = self._cascade.intensity * 0.05
        else:
            deltas["mortality.load"] = 0.0
            deltas["pulse.strain"] = 0.0

        # 恢复期贡献
        if self._in_recovery:
            recovery_factor = self._recovery_ticks_remaining / 60.0
            deltas["immunity.sovereignty"] = -(recovery_factor * 0.1)
        else:
            deltas["immunity.sovereignty"] = 0.0

        return deltas

    # ------------------------------------------------------------------
    # 漂移速率调制
    # ------------------------------------------------------------------

    def _modulate_drift_rate(self, spine: Any) -> None:
        """级联期间将漂移速率提升 10 倍。

        通过设置 spine._drift_min_interval 实现：
          - 级联激活：移除速率限制（interval = 0）
          - 级联终止：恢复正常速率限制（interval = 30）
        """
        if hasattr(spine, "_drift_min_interval"):
            if self._cascade.active:
                spine._drift_min_interval = 0.0
            else:
                spine._drift_min_interval = 30.0

    def drift_rate_multiplier(self) -> float:
        """返回当前漂移速率倍增器。

        级联激活时返回 10.0，恢复期返回 2.0，正常返回 1.0。
        用于不持有 spine 引用时的集成场景。
        """
        if self._cascade.active:
            return 10.0
        if self._in_recovery:
            return 2.0
        return 1.0

    def drift_cap_multiplier(self) -> float:
        """返回当前漂移上限倍增器。

        恢复期人格流动性增加，漂移上限翻倍。
        """
        if self._in_recovery:
            return 2.0
        return 1.0

    # ------------------------------------------------------------------
    # 伤口摄入（body → hot pool）
    # ------------------------------------------------------------------

    def ingest_wound(self, wound_open: float) -> None:
        """从身体伤口状态摄入材料到热池。

        当 body.wound.open > 0.3 时调用。如果热池中已有伤口材料，
        更新其热度和质量；否则创建新的伤口材料。

        Args:
            wound_open: body.wound.open 值 [0, 1]。
        """
        if wound_open <= 0.3:
            return

        existing_wound = None
        for mat in self._materials:
            if mat.origin_type == "wound":
                existing_wound = mat
                break

        if existing_wound is None:
            self._add_material(
                HotMaterial(
                    id=f"wound_{time.time_ns()}_{next(_material_id_counter)}",
                    origin_type="wound",
                    heat=_clamp(wound_open * 0.6),
                    mass=_clamp(wound_open * 0.4),
                    peak_heat=wound_open * 0.6,
                    last_ignition=time.time(),
                )
            )
        else:
            existing_wound.heat = max(existing_wound.heat, wound_open * 0.5)
            existing_wound.mass = _clamp(existing_wound.mass + 0.05)
            existing_wound.peak_heat = max(existing_wound.peak_heat, existing_wound.heat)

    # ------------------------------------------------------------------
    # L6 自创生集成钩子
    # ------------------------------------------------------------------

    def boundary_integrity_delta(self) -> float:
        """返回级联对边界完整性的削弱量。

        级联激活时，边界完整性降低（最多 -0.2）。
        用于 L6 Autopoiesis 层集成。

        Returns:
            负值表示削弱，0.0 表示无影响。
        """
        if self._cascade.active:
            return -(self._cascade.intensity * 0.2)
        return 0.0

    # ------------------------------------------------------------------
    # L7 相变集成钩子
    # ------------------------------------------------------------------

    def expression_pressure_boost(self) -> float:
        """返回坍缩后的表达压力增强。

        坍缩后 3 tick 内，系统必须表达（强制输出）。

        Returns:
            正值表示表达压力增强，0.0 表示无影响。
        """
        if not self._collapse_history:
            return 0.0
        latest = self._collapse_history[-1]
        # 坍缩后 3 tick 内强制表达
        ticks_since_collapse = self._tick - latest.collapse_tick
        if 0 <= ticks_since_collapse < 3:
            return 1.5  # 超过表达阈值的倍数
        return 0.0

    # ------------------------------------------------------------------
    # 级联信号放大钩子
    # ------------------------------------------------------------------

    def amplify_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """级联期间放大传入事件信号。

        放大逻辑：
          - confidence 乘以 sensitivity_multiplier
          - hurt 标志时注入 cascade_hurt_boost
          - boundary 标志时注入 cascade_boundary_boost

        Args:
            event: 事件字典（包含 confidence, flags, values 等）。

        Returns:
            修改后的事件字典（原地修改并返回）。
        """
        if not self._cascade.active:
            return event

        # 放大置信度
        if "confidence" in event:
            event["confidence"] = _clamp(
                float(event["confidence"]) * self._cascade.sensitivity_multiplier,
                lo=0.0,
                hi=1.0,
            )

        # 标志增强
        flags = event.get("flags", [])
        values = event.get("values", {})

        if "hurt" in flags:
            values["cascade_hurt_boost"] = self._cascade.intensity * 0.3
        if "boundary" in flags:
            values["cascade_boundary_boost"] = self._cascade.intensity * 0.2

        event["values"] = values
        return event

    # ------------------------------------------------------------------
    # 序列化 / 反序列化
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """序列化热池状态为字典。"""
        return {
            "schema_version": _SCHEMA_VERSION,
            "temperature": round(self._temperature, 6),
            "volume": round(self._volume, 6),
            "pressure": round(self._pressure, 6),
            "materials": [m.to_dict() for m in self._materials],
            "cascade": self._cascade.to_dict(),
            "collapse_history": [r.to_dict() for r in self._collapse_history],
            "in_recovery": self._in_recovery,
            "recovery_ticks_remaining": self._recovery_ticks_remaining,
            "tick": self._tick,
            "params": {
                "collapse_threshold": self._collapse_threshold,
                "cascade_trigger": self._cascade_trigger,
                "decay_rate": self._decay_rate,
                "pressure_growth_rate": self._pressure_growth_rate,
                "validation_effectiveness": self._validation_effectiveness,
                "neuroticism": self._neuroticism,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], n_dims: int = 16, mode: str = "pro") -> HotPool:
        """从字典反序列化热池状态。"""
        pool = cls(n_dims=n_dims, mode=mode)
        pool._temperature = _safe_float(data.get("temperature"), 0.0)
        pool._volume = _safe_float(data.get("volume"), 0.0)
        pool._pressure = _safe_float(data.get("pressure"), 0.0)
        pool._tick = int(data.get("tick", 0))
        pool._in_recovery = bool(data.get("in_recovery", False))
        pool._recovery_ticks_remaining = int(data.get("recovery_ticks_remaining", 0))

        materials_data = data.get("materials", [])
        pool._materials = [HotMaterial.from_dict(m) for m in materials_data]

        cascade_data = data.get("cascade")
        if cascade_data:
            pool._cascade = CascadeState.from_dict(cascade_data)

        history_data = data.get("collapse_history", [])
        pool._collapse_history = [CollapseRecord.from_dict(r) for r in history_data]

        params = data.get("params", {})
        if params:
            pool._collapse_threshold = _safe_float(params.get("collapse_threshold"), 0.75)
            pool._cascade_trigger = _safe_float(params.get("cascade_trigger"), 0.6)
            pool._decay_rate = _safe_float(params.get("decay_rate"), 0.02)
            pool._pressure_growth_rate = _safe_float(params.get("pressure_growth_rate"), 0.01)
            pool._validation_effectiveness = _safe_float(
                params.get("validation_effectiveness"), 0.4
            )
            pool._neuroticism = _safe_float(params.get("neuroticism"), 0.5)

        return pool

    def diagnostics(self) -> dict[str, Any]:
        """返回诊断信息（不含完整序列化，用于 surface 输出）。"""
        return {
            "temperature": round(self._temperature, 4),
            "volume": round(self._volume, 4),
            "pressure": round(self._pressure, 4),
            "material_count": len(self._materials),
            "cascade_active": self._cascade.active,
            "cascade_intensity": round(self._cascade.intensity, 4),
            "sensitivity_multiplier": round(self._cascade.sensitivity_multiplier, 4),
            "in_recovery": self._in_recovery,
            "collapse_count": len(self._collapse_history),
        }
