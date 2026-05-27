"""Sylanne-Embodiment 计算核心层：自创生边界（Autopoietic Boundary）。

在 7 层计算栈中的位置：L6 边界层。
职责：将人格建模为一个自我维持的计算过程——不由外部参数定义，而是通过持续的
自修复循环来维持。小扰动被吸收（边界完整性微降），大冲击可能触发相变
（identity kernel 旋转重组）。

核心思想来自 Maturana & Varela 的自创生理论：系统通过自身的运作来维持自身的组织。
"""

from __future__ import annotations

import math
from typing import Any


class AutopoieticBoundary:
    """自创生边界：人格的自我维持计算过程。

    核心概念：
      - identity_kernel: 身份核心向量（自参照约束），定义"我是谁"
      - boundary_integrity: 边界完整性 [0, 1]，高 = 抗干扰能力强
      - internal_entropy: 内部熵 [0, 1]，高 = 系统混乱度大
      - repair_rate: 自修复速率，每 tick 恢复的完整性量

    扰动机制：
      - 外力投影到 identity_kernel 的正交补空间（平行分量被吸收）
      - 穿透量 = 正交分量大小 × (1 - 完整性)
      - 穿透超过阈值 → 相变（identity_kernel 旋转重组）
      - 穿透未超阈值 → 完整性微降 + 熵微升

    与其他组件的关系：
      - 被 ComputationSpine 在 L6 层调用
      - 接收 L3 情感状态转换为的力向量
      - stability() 输出给结果诊断
      - 相变事件影响 L7 表达驱动力
    """

    __slots__ = (
        "identity_dim",
        "identity_kernel",
        "boundary_integrity",
        "internal_entropy",
        "repair_rate",
        "_phase_transitions",
        "_last_penetration",
        "_phase_threshold",
        "_rotation_angle",
    )

    def __init__(self, identity_dim: int = 32, agreeableness: float = 0.5):
        self.identity_dim = identity_dim
        # Identity kernel: self-referential constraint vector
        self.identity_kernel = self._init_kernel(identity_dim)
        # Initial integrity derived from personality: agreeable = more permeable
        self.boundary_integrity = 1.0 - agreeableness * 0.08
        self.internal_entropy = 0.0
        self.repair_rate = 0.05
        self._phase_transitions: list[dict[str, Any]] = []
        self._last_penetration: float = 0.0
        self._phase_threshold = 0.7
        self._rotation_angle = 0.1

    def perturb(self, force: list[float]) -> dict[str, Any]:
        """外部扰动作用于边界。

        将力向量分解为平行于 identity_kernel 的分量（被吸收）和正交分量（可能穿透）。
        穿透量 = 正交分量范数 × (1 - boundary_integrity)。

        如果穿透超过相变阈值：触发 identity_kernel 旋转重组（系统适应性改变）。
        否则：边界完整性微降，内部熵微升。

        Args:
            force: 外力向量（32 维，由情感状态映射而来）

        Returns:
            包含穿透量、是否相变、边界完整性、内部熵的诊断字典
        """
        if len(force) < self.identity_dim:
            force = force + [0.0] * (self.identity_dim - len(force))
        force = force[: self.identity_dim]

        # Project force onto identity kernel's orthogonal complement
        dot = sum(f * k for f, k in zip(force, self.identity_kernel))
        orthogonal = [f - dot * k for f, k in zip(force, self.identity_kernel)]
        orth_norm = math.sqrt(sum(x * x for x in orthogonal) + 1e-12)

        # Penetration = orthogonal magnitude × (1 - integrity)
        penetration = orth_norm * (1.0 - self.boundary_integrity)
        self._last_penetration = penetration
        phase_transition = penetration > self._phase_threshold

        if phase_transition:
            self._reorganize(orthogonal, orth_norm)
            self.internal_entropy = min(1.0, self.internal_entropy + 0.3)
            self._phase_transitions.append(
                {
                    "penetration": penetration,
                    "entropy_after": self.internal_entropy,
                }
            )
            if len(self._phase_transitions) > 20:
                self._phase_transitions = self._phase_transitions[-20:]
        else:
            self.boundary_integrity = max(
                0.0, self.boundary_integrity - penetration * 0.1
            )
            self.internal_entropy = min(1.0, self.internal_entropy + penetration * 0.05)

        return {
            "penetration": round(penetration, 4),
            "phase_transition": phase_transition,
            "boundary_integrity": round(self.boundary_integrity, 4),
            "internal_entropy": round(self.internal_entropy, 4),
        }

    def self_repair(self):
        """自修复循环——每 tick 运行。

        当处于活跃压力下（最近有高穿透）时，只缓慢降低熵而不恢复完整性——
        伤口仍然开放，需要时间愈合。这防止了"被打一下立刻满血"的不真实行为。

        正常修复时，完整性有 0.3 的下限，防止正反馈崩溃
        （完整性越低 → 穿透越大 → 完整性更低 → 死循环）。
        """
        if self._last_penetration > 0.4:
            # Wound still open: slow healing, don't restore integrity yet
            self._last_penetration *= 0.8  # Gradually decay penetration memory
            self.internal_entropy = max(
                0.0, self.internal_entropy - self.repair_rate * 0.2
            )
            return
        # Normal repair — floor at 0.3 to prevent positive feedback collapse
        self.boundary_integrity = max(
            0.3, min(1.0, self.boundary_integrity + self.repair_rate)
        )
        self.internal_entropy = max(0.0, self.internal_entropy - self.repair_rate * 0.5)
        # Re-normalize identity kernel
        norm = math.sqrt(sum(x * x for x in self.identity_kernel) + 1e-12)
        self.identity_kernel = [x / norm for x in self.identity_kernel]

    def stability(self) -> float:
        """整体稳定性评分：高 = 抗变化能力强。公式：完整性 × (1 - 熵)。"""
        return self.boundary_integrity * (1.0 - self.internal_entropy)

    def phase_transition_count(self) -> int:
        return len(self._phase_transitions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "boundary_integrity": self.boundary_integrity,
            "internal_entropy": self.internal_entropy,
            "stability": self.stability(),
            "repair_rate": self.repair_rate,
            "phase_transitions": len(self._phase_transitions),
            "phase_transition_log": self._phase_transitions[-10:],
            "last_penetration": self._last_penetration,
            "identity_kernel": self.identity_kernel,
        }

    def from_dict(self, data: dict[str, Any]):
        self.boundary_integrity = float(data.get("boundary_integrity", 1.0))
        self.internal_entropy = float(data.get("internal_entropy", 0.0))
        self.repair_rate = float(data.get("repair_rate", 0.05))
        self._last_penetration = float(data.get("last_penetration", 0.0))
        if "phase_transition_log" in data and isinstance(
            data["phase_transition_log"], list
        ):
            self._phase_transitions = data["phase_transition_log"]
        if "identity_kernel" in data and isinstance(data["identity_kernel"], list):
            self.identity_kernel = [float(x) for x in data["identity_kernel"]]

    def _reorganize(self, force: list[float], force_norm: float):
        """自主重组：将 identity_kernel 向力的方向微旋转。

        这是相变的核心——系统在大冲击下不是崩溃，而是适应性地改变自身。
        旋转角度由 _rotation_angle 控制（人格开放性越高，旋转越大）。
        """
        angle = self._rotation_angle  # Max rotation per phase transition
        unit_force = [f / force_norm for f in force]
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        self.identity_kernel = [
            cos_a * k + sin_a * f for k, f in zip(self.identity_kernel, unit_force)
        ]
        # Re-normalize
        norm = math.sqrt(sum(x * x for x in self.identity_kernel) + 1e-12)
        self.identity_kernel = [x / norm for x in self.identity_kernel]

    @classmethod
    def create_shared_kernel(cls, dim: int) -> list[float]:
        """创建确定性身份核心向量（用于跨实例共享）。"""
        return cls._init_kernel(dim)

    def set_identity_kernel(self, kernel: list[float]) -> None:
        """替换身份核心向量为共享的版本。"""
        self.identity_kernel = list(kernel)

    def set_personality_params(
        self, repair_rate: float, phase_threshold: float, rotation_angle: float
    ):
        self.repair_rate = repair_rate
        self._phase_threshold = phase_threshold
        self._rotation_angle = rotation_angle

    @staticmethod
    def _init_kernel(dim: int) -> list[float]:
        """确定性初始化身份核心向量（使用素数种子的线性同余生成器）。"""
        kernel = []
        state = 7919  # prime seed
        for i in range(dim):
            state = (state * 48271) % 2147483647
            kernel.append((state / 2147483647) * 2.0 - 1.0)
        norm = math.sqrt(sum(x * x for x in kernel))
        return [x / norm for x in kernel]
