"""Sylanne-Embodiment computation layer: Phase Transition Expression Trigger.

Expression is not a "decision to speak" but a phase transition --
internal pressure accumulates until a critical point, then erupts.
Like water boiling at 100°C: not gradual, but sudden.
"""
from __future__ import annotations

from typing import Any


class PhaseTransitionExpression:
    __slots__ = (
        "pressure", "threshold", "decay_rate",
        "silence_duration", "_last_expression_time", "_expression_count",
    )

    def __init__(self, initial_threshold: float = 0.6):
        self.pressure = 0.0
        self.threshold = initial_threshold
        self.decay_rate = 0.02  # Natural pressure dissipation
        self.silence_duration = 0.0
        self._last_expression_time = 0.0
        self._expression_count = 0

    def accumulate(self, drive: float, dt: float = 1.0):
        """Accumulate expression pressure from emotional drive."""
        self.pressure += drive * dt
        # Natural decay (pressure dissipates even without expression)
        self.pressure = max(0.0, self.pressure * (1.0 - self.decay_rate))
        self.silence_duration += dt

    def expression_intensity(self) -> float:
        """Continuous expression intensity: 0.0 (silent) to 1.0+ (urgent).

        - pressure < threshold * 0.5 → 0.0 (no expression)
        - pressure = threshold → 1.0 (normal expression)
        - pressure > threshold → >1.0 (urgent expression)
        """
        half_threshold = self.threshold * 0.5
        if self.pressure < half_threshold:
            return 0.0
        return (self.pressure - half_threshold) / max(0.01, self.threshold)

    def should_express(self) -> bool:
        """Phase transition check (compat): intensity above hint threshold."""
        return self.expression_intensity() > 0.3

    def express(self, now: float = 0.0) -> dict[str, Any]:
        """Trigger expression -- release pressure, return intensity and mode."""
        intensity = self.expression_intensity()
        urgency = min(1.0, self.silence_duration / 10.0)  # Longer silence → more urgent

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

        # After expressing, threshold rises slightly (harder to speak again immediately)
        self.threshold = min(0.9, self.threshold + 0.03)

        return {
            "intensity": round(intensity, 3),
            "urgency": round(urgency, 3),
            "mode": mode,
            "threshold_after": round(self.threshold, 3),
            "expression_count": self._expression_count,
        }

    def silence_lowers_threshold(self, dt: float = 1.0):
        """Prolonged silence makes it easier to speak (threshold drops)."""
        self.threshold = max(0.25, self.threshold - 0.008 * dt)

    def state(self) -> dict[str, Any]:
        """Current state for diagnostics."""
        return {
            "pressure": round(self.pressure, 4),
            "threshold": round(self.threshold, 4),
            "ratio": round(self.pressure / max(0.01, self.threshold), 3),
            "silence_duration": round(self.silence_duration, 1),
            "ready": self.should_express(),
        }

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
