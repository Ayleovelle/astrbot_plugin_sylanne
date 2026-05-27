"""Sylanne-Embodiment 计算核心层：相变表达触发器（Phase Transition Expression Trigger）。

在 7 层计算栈中的位置：L7 表达层。
职责：表达不是一个"决定说话"的离散决策，而是一个相变过程——
内部压力持续积累，直到临界点突然爆发。如同水在 100°C 沸腾：不是渐进的，而是突变的。

核心机制：
  - pressure（压力）：由情感驱动力持续注入
  - threshold（阈值）：由人格和社交场调制，沉默会降低阈值（更容易说话）
  - 表达后阈值上升（不应期），防止连续输出
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .social_field import SocialSignals


class PhaseTransitionExpression:
    """相变表达触发器。

    模拟表达行为的物理相变模型：
      - pressure（压力）：由情感驱动力持续注入，自然衰减
      - threshold（阈值）：表达的临界点，受人格和社交场调制
      - 当 pressure > threshold * 0.5 时开始有表达倾向
      - 表达后阈值上升（不应期），沉默会逐渐降低阈值

    与其他组件的关系：
      - 被 ComputationSpine 在 L7 层调用
      - 接收 VoidScarEngine.expression_drive() 作为驱动力
      - 接收 SocialSignals 调制群聊中的有效阈值
      - should_express() 输出给 ComputationSpine 决定是否表达
    """

    __slots__ = (
        "pressure",
        "threshold",
        "decay_rate",
        "silence_duration",
        "_last_expression_time",
        "_expression_count",
        "_social_context",
        "_social_signals",
        "_silence_urgency_divisor",
        "_refractory",
        "_silence_drop_rate",
        "_min_threshold_floor",
    )

    def __init__(self, initial_threshold: float = 0.6):
        self.pressure = 0.0
        self.threshold = initial_threshold
        self.decay_rate = 0.02  # Natural pressure dissipation
        self.silence_duration = 0.0
        self._last_expression_time = 0.0
        self._expression_count = 0
        self._social_context: dict = {}
        self._social_signals: SocialSignals | None = None
        self._silence_urgency_divisor = 10.0
        self._refractory = 0.03
        self._silence_drop_rate = 0.008
        self._min_threshold_floor = 0.25

    def accumulate(self, drive: float, dt: float = 1.0):
        """积累表达压力。

        Args:
            drive: 情感驱动力（来自 VoidScarEngine.expression_drive()）
            dt: 时间步长
        """
        self.pressure += drive * dt
        # Natural decay (pressure dissipates even without expression)
        self.pressure = max(0.0, self.pressure * (1.0 - self.decay_rate))
        self.silence_duration += dt

    def set_social_params(self, params: dict) -> None:
        """设置人格派生的社交场参数（由 ComputationSpine.apply_personality 调用）。"""
        self._social_context = params

    def apply_social_signals(self, signals: SocialSignals | None) -> None:
        """应用社交信号（在 accumulate() 之前调用，影响有效阈值计算）。"""
        self._social_signals = signals

    def set_personality_params(
        self,
        decay_rate: float,
        silence_urgency_divisor: float,
        refractory: float,
        silence_drop_rate: float,
        min_threshold_floor: float,
    ):
        self.decay_rate = decay_rate
        self._silence_urgency_divisor = silence_urgency_divisor
        self._refractory = refractory
        self._silence_drop_rate = silence_drop_rate
        self._min_threshold_floor = min_threshold_floor

    def effective_threshold(self) -> float:
        """计算有效阈值（含社交场调制）。

        私聊：直接返回 self.threshold
        群聊：theta_eff = theta_base * (1 + mu) - sigma_call - sigma_sheaf - sigma_void
          - mu: 群聊基础提升（内向者更高）
          - sigma_call: 被 @/点名时大幅降低阈值
          - sigma_sheaf: 关系层析耦合降低阈值
          - sigma_void: 社交虚空压力降低阈值
        """
        if not self._social_signals or not self._social_signals.is_group:
            return self.threshold

        params = self._social_context
        mu = params.get("group_threshold_boost", 0.3)
        theta_group = self.threshold * (1.0 + mu)

        if self._social_signals.is_at_bot:
            return 0.0
        sigma_call = 0.6 * theta_group if self._social_signals.name_mentioned else 0.0

        sigma_sheaf = (
            self._social_signals.sheaf_coupling
            * params.get("sheaf_coupling", 0.3)
            * 0.3
        )

        sigma_void = (
            self._social_signals.social_void_pressure
            * params.get("void_coupling", 0.3)
            * 0.2
        )

        theta_eff = theta_group - sigma_call - sigma_sheaf - sigma_void
        return max(0.0, theta_eff)

    def expression_intensity(self) -> float:
        """连续表达强度：0.0（沉默）到 1.0+（紧急）。

        - pressure < threshold * 0.5 → 0.0（无表达倾向）
        - pressure = threshold → 1.0（正常表达）
        - pressure > threshold → >1.0（紧急表达）
        """
        threshold = self.effective_threshold()
        if threshold < 1e-6:
            return 1.0 if self.pressure > 0 else 0.0
        half_threshold = threshold * 0.5
        if self.pressure < half_threshold:
            return 0.0
        return (self.pressure - half_threshold) / threshold

    def should_express(self) -> bool:
        """相变检查：强度是否超过 hint 阈值（pressure > threshold * 0.5）。"""
        threshold = self.effective_threshold()
        half = threshold * 0.5
        return self.pressure > half

    def express(self, now: float = 0.0) -> dict[str, Any]:
        """触发表达——释放压力，返回强度和模式。

        表达后：
          - 压力归零
          - 沉默时长归零
          - 阈值上升（不应期，防止连续输出）
          - 群聊中不应期额外增加

        Returns:
            包含 intensity, urgency, mode, threshold_after, expression_count 的字典
        """
        intensity = self.expression_intensity()
        urgency = min(
            1.0, self.silence_duration / self._silence_urgency_divisor
        )  # Longer silence → more urgent

        # Determine expression mode from intensity
        if intensity < 0.5:
            mode = "hint"
        elif intensity < 1.0:
            mode = "normal"
        else:
            mode = "urgent"

        self.pressure = 0.0
        self.silence_duration = 0.0
        self._last_expression_time = now
        self._expression_count += 1

        # After expressing, threshold rises (harder to speak again immediately)
        refractory = self._refractory
        if self._social_signals and self._social_signals.is_group:
            refractory += self._social_context.get("refractory_boost", 0.03)
        self.threshold = min(0.9, self.threshold + refractory)

        return {
            "intensity": round(intensity, 3),
            "urgency": round(urgency, 3),
            "mode": mode,
            "threshold_after": round(self.threshold, 3),
            "expression_count": self._expression_count,
        }

    def silence_lowers_threshold(self, dt: float = 1.0):
        """持续沉默降低表达阈值（越久不说话，越容易开口）。"""
        self.threshold = max(
            self._min_threshold_floor, self.threshold - self._silence_drop_rate * dt
        )

    def _current_mode(self) -> str:
        """从当前强度推导表达模式：silent / hint / normal / urgent。"""
        intensity = self.expression_intensity()
        if intensity < 0.3:
            return "silent"
        elif intensity < 0.7:
            return "hint"
        elif intensity < 1.2:
            return "normal"
        return "urgent"

    def state(self) -> dict[str, Any]:
        """当前状态快照（用于诊断和 UI 展示）。"""
        eff_threshold = self.effective_threshold()
        is_group = bool(self._social_signals and self._social_signals.is_group)
        result = {
            "pressure": round(self.pressure, 4),
            "threshold": round(self.threshold, 4),
            "effective_threshold": round(eff_threshold, 4),
            "ratio": round(self.pressure / max(0.01, eff_threshold), 3),
            "silence_duration": round(self.silence_duration, 1),
            "ready": self.should_express(),
            "mode": self._current_mode(),
            "expression_count": self._expression_count,
            "is_group": is_group,
        }
        if is_group and self._social_signals:
            result["social_signals"] = {
                "name_mentioned": self._social_signals.name_mentioned,
                "is_at_bot": self._social_signals.is_at_bot,
                "topic_relevance": round(self._social_signals.topic_relevance, 3),
                "continuation": round(self._social_signals.continuation_strength, 3),
                "noise_level": round(self._social_signals.group_noise_level, 3),
                "void_pressure": round(self._social_signals.social_void_pressure, 3),
                "sheaf_coupling": round(self._social_signals.sheaf_coupling, 3),
            }
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "pressure": self.pressure,
            "threshold": self.threshold,
            "silence_duration": self.silence_duration,
            "expression_count": self._expression_count,
        }

    def from_dict(self, data: dict[str, Any]):
        self.pressure = float(data.get("pressure", 0.0))
        self.threshold = float(data.get("threshold", 0.6))
        self.silence_duration = float(data.get("silence_duration", 0.0))
        self._expression_count = int(data.get("expression_count", 0))
