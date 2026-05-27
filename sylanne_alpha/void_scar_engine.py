"""Sylanne-Embodiment 计算核心层：虚空-伤痕耦合引擎（Void-Scar Coupled Engine）。

在 7 层计算栈中的位置：L3 层的统一入口，替代了原始架构中的 SSM + TDA 层。
职责：将伤痕代数（不可逆状态动力学）与虚空微积分（一等缺席计算）通过双向耦合整合：
  Γ 耦合：虚空压力 → 伤痕创伤事件（压力积累到阈值时触发创伤）
  Φ 耦合：伤痕麻木 → 虚空检测灵敏度（麻木维度降低虚空检测阈值）

输出 8 维情感空间：warmth, arousal, valence, tension, curiosity,
repair_pressure, expression_drive, boundary_firmness。
"""

from __future__ import annotations

import math
from typing import Any, Callable

from .scar_algebra import ScarredState
from .void_calculus import VoidSpace


class SocialVoid:
    """群聊沉默虚空——当 agent 在活跃群聊中保持沉默时，压力持续积累。

    模拟"群里大家都在聊，我却没说话"的社交压力。
    与 VoidSpace 中的个人虚空不同，这是纯社交层面的压力源。
    """

    __slots__ = ("pressure", "silence_ticks", "group_activity", "topic_boundary")

    def __init__(self):
        self.pressure = 0.0
        self.silence_ticks = 0
        self.group_activity = 0.0
        self.topic_boundary = 0.5

    def tick(self, group_active: bool = True):
        if not group_active:
            self.pressure *= 0.95
            return
        self.silence_ticks += 1
        depth = self.group_activity
        beta = self.topic_boundary
        if depth > 0 and self.silence_ticks > 0:
            self.pressure += (
                depth * math.log(self.silence_ticks + 1) * (1.0 - beta) * 0.1
            )
        self.pressure = min(5.0, self.pressure)

    def reset(self):
        self.silence_ticks = 0
        self.pressure *= 0.3

    def to_dict(self) -> dict:
        return {
            "pressure": self.pressure,
            "silence_ticks": self.silence_ticks,
            "group_activity": self.group_activity,
            "topic_boundary": self.topic_boundary,
        }

    def from_dict(self, data: dict):
        self.pressure = float(data.get("pressure", 0.0))
        self.silence_ticks = int(data.get("silence_ticks", 0))
        self.group_activity = float(data.get("group_activity", 0.0))
        self.topic_boundary = float(data.get("topic_boundary", 0.5))


class VoidScarEngine:
    """虚空-伤痕耦合计算引擎。

    替代计算脊柱中原始的 SSM（L3）和 TDA（L4）层。
    通过双向耦合将两个独立的数学系统整合为统一的情感计算引擎：
      - Γ 耦合（虚空→伤痕）：虚空压力超过阈值时，向伤痕状态注入创伤事件
      - Φ 耦合（伤痕→虚空）：伤痕麻木的维度降低虚空检测阈值（更容易感知缺席）

    与其他组件的关系：
      - 被 ComputationSpine.process() 在 L3 层调用
      - 接收 L1 HDC 编码和 L2 惊讶度
      - 输出 8 维情感观测给 L5 HGT 和 L7 表达层
      - expression_drive() 输出给 L7 PhaseTransitionExpression
    """

    __slots__ = (
        "scar_state",
        "void_space",
        "social_void",
        "similarity_fn",
        "_coherence",
        "_last_event_vec",
        "_tick",
        "_void_pressure_coupling_rate",
        "_void_drive_weight",
        "_social_drive_weight",
        "_accepted_decay",
        "_ignored_deepening",
        "_personality_detection_floor",
    )

    def __init__(
        self,
        n_dims: int = 8,
        wound_threshold: float = 0.6,
        similarity_fn: Callable[[bytes, bytes], float] | None = None,
        max_voids: int = 50,
        pressure_threshold: float = 10.0,
    ):
        self.scar_state = ScarredState(n_dims=n_dims, wound_threshold=wound_threshold)
        self.similarity_fn = similarity_fn or _default_similarity
        self.void_space = VoidSpace(
            similarity_fn=self.similarity_fn,
            max_voids=max_voids,
            pressure_threshold=pressure_threshold,
        )
        self.social_void = SocialVoid()
        self._coherence = 1.0
        self._last_event_vec: bytes | None = None
        self._tick = 0
        self._void_pressure_coupling_rate = 0.3
        self._void_drive_weight = 0.5
        self._social_drive_weight = 0.3
        self._accepted_decay = 0.7
        self._ignored_deepening = 0.05
        self._personality_detection_floor: float = 0.1

    def process(
        self,
        event_vec: bytes,
        ssm_input: list[float],
        surprise: float,
        timestamp: float = 0.0,
    ) -> dict[str, Any]:
        """处理一个事件通过耦合的虚空-伤痕引擎。

        执行顺序：
          1. Φ 耦合：伤痕麻木 → 降低虚空检测阈值
          2. 虚空微积分步进
          3. Γ 耦合：虚空压力超阈值 → 向伤痕注入创伤
          4. 伤痕代数步进（主事件）
          5. 计算全局一致性

        Args:
            event_vec: HDC 编码的事件向量（用于虚空边界操作）
            ssm_input: 8 维输入向量（用于伤痕状态演化）
            surprise: 来自预测编码门控的惊讶度
            timestamp: 事件时间戳

        Returns:
            包含伤痕状态、虚空状态、耦合信息和一致性的综合结果
        """
        self._tick += 1

        # Compute similarity to previous event (for void detection)
        prev_sim = 0.0
        if self._last_event_vec is not None:
            prev_sim = self.similarity_fn(event_vec, self._last_event_vec)
        self._last_event_vec = event_vec

        # --- Coupling Φ: Scars → Void sensitivity ---
        # Numbed dimensions lower void detection threshold, but respect personality floor
        numbed_count = sum(
            1 for d in range(self.scar_state.n_dims) if self.scar_state.is_numbed(d)
        )
        if numbed_count > 0:
            # Phi coupling: numbed dims lower detection threshold, but respect floor
            personality_base = self.void_space._detection_threshold
            phi_floor = self._personality_detection_floor
            phi_adjusted = max(phi_floor, personality_base - numbed_count * 0.03)
            self.void_space._detection_threshold = phi_adjusted

        # --- Void Calculus step ---
        void_result = self.void_space.process(event_vec, surprise, prev_sim)

        # --- Coupling Γ: Void pressure → Scar wounding ---
        coupling_wounds: list[dict[str, Any]] = []
        for coupling in void_result["coupling_events"]:
            wound_event = [0.0] * self.scar_state.n_dims
            dim_hint = int(coupling.get("dim_hint", 0)) % self.scar_state.n_dims
            wound_event[dim_hint] = (
                coupling["pressure"] * self._void_pressure_coupling_rate
            )
            wound_result = self.scar_state.step(wound_event, timestamp, heal=False)
            coupling_wounds.append(wound_result)

        # --- Scar Algebra step (main event) ---
        scar_result = self.scar_state.step(ssm_input, timestamp)

        # --- Compute coherence (emergent resonance) ---
        self._coherence = self._compute_coherence()

        return {
            "scar": scar_result,
            "void": void_result,
            "coupling_wounds": coupling_wounds,
            "coherence": self._coherence,
            "observation": self.observe(),
        }

    # Canonical dimension names for the 8-dim emotion space
    _DIM_NAMES: tuple[str, ...] = (
        "warmth",
        "arousal",
        "valence",
        "tension",
        "curiosity",
        "repair_pressure",
        "expression_drive",
        "boundary_firmness",
    )

    def observe(self) -> dict[str, float]:
        """可观测输出：供下游层使用的命名情感维度。

        返回 8 个命名情感维度（warmth, arousal, valence, tension,
        curiosity, repair_pressure, expression_drive, boundary_firmness）
        加上 coherence, void_pressure, active_voids, ghost_count 等元信息。
        """
        raw = self.scar_state.observe()
        obs: dict[str, float] = {}
        # Map dim_N → named dimensions
        for i, name in enumerate(self._DIM_NAMES):
            obs[name] = raw.get(f"dim_{i}", 0.0)
        # Keep sensitivity values under named keys
        for i, name in enumerate(self._DIM_NAMES):
            obs[f"sensitivity_{name}"] = raw.get(f"sensitivity_{i}", 1.0)
        obs["total_scars"] = raw.get("total_scars", 0.0)
        obs["numbed_dimensions"] = raw.get("numbed_dimensions", 0.0)
        obs["coherence"] = self._coherence
        obs["void_pressure"] = self.void_space.total_pressure()
        obs["active_voids"] = float(len(self.void_space.voids))
        obs["ghost_count"] = float(len(self.void_space.ghosts))
        return obs

    def expression_drive(self) -> float:
        """计算综合表达驱动力（供 L7 相变表达层使用）。

        三个来源加权求和：
          - scar_drive: 伤痕基向量第 6 维（expression_drive 维度）的绝对值
          - void_drive: 虚空总压力归一化后乘以权重
          - social_drive: 社交虚空压力归一化后乘以权重
        """
        scar_drive = (
            abs(self.scar_state.base[6]) if len(self.scar_state.base) > 6 else 0.0
        )
        void_drive = min(1.0, self.void_space.total_pressure() / 50.0)
        social_drive = min(1.0, self.social_void.pressure / 3.0)
        return min(
            1.0,
            scar_drive
            + void_drive * self._void_drive_weight
            + social_drive * self._social_drive_weight,
        )

    def _compute_coherence(self) -> float:
        """计算全局一致性：虚空与伤痕的对齐程度。

        r → 1: 虚空和伤痕对齐（系统一致——痛的地方也在回避）
        r → 0: 压力积累在麻木区域（解离状态——回避的不是真正痛的地方）

        这是系统健康度的重要指标：低一致性暗示需要干预。
        """
        if not self.void_space.voids:
            return 1.0
        total_pressure = 0.0
        numbed_pressure = 0.0
        for v in self.void_space.voids:
            total_pressure += v.pressure
            dim_hint = len(v.boundary) % self.scar_state.n_dims
            if self.scar_state.modifier(dim_hint) < 0.5:
                numbed_pressure += v.pressure
        if total_pressure < 0.01:
            return 1.0
        return 1.0 - (numbed_pressure / total_pressure)

    def feedback(self, outcome: str, dt: float = 1.0) -> dict[str, float]:
        """注入表达结果作为反馈。

        'accepted' → 减少虚空压力，正向伤痕输入（温暖、修复）
        'ignored' → 增加虚空深度，负向伤痕输入（退缩）
        'rejected' → 创伤事件注入伤痕状态（伤害）
        """
        if outcome == "accepted":
            for v in self.void_space.voids:
                v.pressure *= self._accepted_decay
            feedback_vec = [0.3, 0.0, 0.2, -0.2, 0.1, -0.3, 0.0, 0.0]
        elif outcome == "ignored":
            for v in self.void_space.voids:
                v.depth = min(5.0, v.depth + self._ignored_deepening)
            feedback_vec = [0.0, -0.1, -0.1, 0.2, -0.1, 0.0, -0.3, 0.0]
        elif outcome == "rejected":
            feedback_vec = [-0.3, 0.1, -0.3, 0.3, -0.1, 0.4, -0.2, 0.3]
        else:
            feedback_vec = [0.0] * 8

        self.scar_state.step(feedback_vec, 0.0)
        return self.scar_state.observe()

    def to_dict(self) -> dict[str, Any]:
        return {
            "scar": self.scar_state.to_dict(),
            "void": self.void_space.to_dict(),
            "social_void": self.social_void.to_dict(),
            "coherence": self._coherence,
            "tick": self._tick,
        }

    def diagnostics(self) -> dict[str, Any]:
        return {
            "scar": self.scar_state.observe(),
            "void": self.void_space.diagnostics(),
            "coherence": self._coherence,
            "expression_drive": self.expression_drive(),
            "tick": self._tick,
        }

    def set_personality_params(
        self,
        coupling_rate: float,
        pressure_threshold: float,
        void_drive_weight: float,
        social_drive_weight: float,
        accepted_decay: float,
        ignored_deepening: float,
    ):
        self._void_pressure_coupling_rate = coupling_rate
        self.void_space._pressure_threshold = pressure_threshold
        self._void_drive_weight = void_drive_weight
        self._social_drive_weight = social_drive_weight
        self._accepted_decay = accepted_decay
        self._ignored_deepening = ignored_deepening


def _default_similarity(a: bytes, b: bytes) -> float:
    """默认相似度函数：基于 Hamming 距离的二进制向量相似度。"""
    if not a or not b:
        return 0.0
    min_len = min(len(a), len(b))
    xor_bits = sum((a[i] ^ b[i]).bit_count() for i in range(min_len))
    total_bits = min_len * 8
    return 1.0 - (xor_bits / total_bits) if total_bits > 0 else 0.0
