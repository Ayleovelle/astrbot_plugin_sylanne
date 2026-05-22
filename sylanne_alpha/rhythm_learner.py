"""Adaptive rhythm synchronization: deliberate mutual pacing adjustment.

Real relationships don't passively mirror — both sides deliberately adjust.
The higher-frequency side feels loss when ignored, deliberately slows down
(with tone degrading too), and pressure accumulates silently until eruption.

Key insight from user research:
- Synchronization is DELIBERATE, not unconscious
- The faster side slows down when ignored AND tone gets worse
- Frequency change accompanies tone change (coupled, not decoupled)
- Long-term frequency mismatch accumulates into void pressure
"""
from __future__ import annotations

import math
from collections import deque
from typing import Any

_MAX_SAMPLES = 60
_MIN_SAMPLES_FOR_PROFILE = 8
_DEFAULT_CHARS_PER_SECOND = 7.5
_DEFAULT_MAX_PART_CHARS = 48


class RhythmProfile:
    """Learned rhythm characteristics from a single user."""

    __slots__ = (
        "_msg_lengths", "_inter_msg_gaps", "_last_msg_time",
        "_chars_per_second", "_avg_part_chars", "_confidence",
    )

    def __init__(self):
        self._msg_lengths: deque[int] = deque(maxlen=_MAX_SAMPLES)
        self._inter_msg_gaps: deque[float] = deque(maxlen=_MAX_SAMPLES)
        self._last_msg_time: float = 0.0
        self._chars_per_second: float = _DEFAULT_CHARS_PER_SECOND
        self._avg_part_chars: float = _DEFAULT_MAX_PART_CHARS
        self._confidence: float = 0.0

    def observe(self, text: str, timestamp: float) -> None:
        """Record one user message."""
        length = len(text.strip())
        if length < 1:
            return
        self._msg_lengths.append(length)

        if self._last_msg_time > 0 and timestamp > self._last_msg_time:
            gap = timestamp - self._last_msg_time
            if 0.3 < gap < 120.0:
                self._inter_msg_gaps.append(gap)
        self._last_msg_time = timestamp

        self._recompute()

    def _recompute(self) -> None:
        n = len(self._msg_lengths)
        if n < _MIN_SAMPLES_FOR_PROFILE:
            self._confidence = 0.0
            return

        self._confidence = min(1.0, (n - _MIN_SAMPLES_FOR_PROFILE) / (_MAX_SAMPLES - _MIN_SAMPLES_FOR_PROFILE))

        sorted_lengths = sorted(self._msg_lengths)
        p50_idx = len(sorted_lengths) // 2
        self._avg_part_chars = float(sorted_lengths[p50_idx])

        if len(self._inter_msg_gaps) >= 3:
            sorted_gaps = sorted(self._inter_msg_gaps)
            median_gap = sorted_gaps[len(sorted_gaps) // 2]
            median_len = self._avg_part_chars
            if median_gap > 0.1:
                self._chars_per_second = max(2.0, min(20.0, median_len / median_gap))

    @property
    def confidence(self) -> float:
        return self._confidence

    @property
    def avg_part_chars(self) -> float:
        return self._avg_part_chars

    @property
    def chars_per_second(self) -> float:
        return self._chars_per_second

    def modulate(self, default_max_part: int, default_cps: float, blend: float) -> tuple[int, float]:
        """Return (max_part_chars, chars_per_second) blended toward user rhythm.

        blend: 0.0 = pure default, 1.0 = pure user rhythm.
        Actual blend is further scaled by confidence.
        """
        effective_blend = blend * self._confidence
        if effective_blend < 0.05:
            return default_max_part, default_cps

        learned_part = max(12, min(120, int(self._avg_part_chars)))
        learned_cps = self._chars_per_second

        blended_part = int(default_max_part * (1 - effective_blend) + learned_part * effective_blend)
        blended_cps = default_cps * (1 - effective_blend) + learned_cps * effective_blend

        return max(12, min(120, blended_part)), max(2.0, min(20.0, blended_cps))

    def to_dict(self) -> dict[str, Any]:
        return {
            "msg_lengths": list(self._msg_lengths),
            "inter_msg_gaps": list(self._inter_msg_gaps),
            "last_msg_time": self._last_msg_time,
            "chars_per_second": self._chars_per_second,
            "avg_part_chars": self._avg_part_chars,
            "confidence": self._confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RhythmProfile":
        p = cls()
        for v in data.get("msg_lengths", []):
            p._msg_lengths.append(int(v))
        for v in data.get("inter_msg_gaps", []):
            p._inter_msg_gaps.append(float(v))
        p._last_msg_time = float(data.get("last_msg_time", 0.0))
        p._chars_per_second = float(data.get("chars_per_second", _DEFAULT_CHARS_PER_SECOND))
        p._avg_part_chars = float(data.get("avg_part_chars", _DEFAULT_MAX_PART_CHARS))
        p._confidence = float(data.get("confidence", 0.0))
        return p


class RhythmLearner:
    """Per-session rhythm learner with intimacy gating."""

    __slots__ = ("_profiles", "_intimacy_threshold")

    def __init__(self, intimacy_threshold: float = 0.6):
        self._profiles: dict[str, RhythmProfile] = {}
        self._intimacy_threshold = intimacy_threshold

    def is_intimate(self, engine_observation: dict[str, float]) -> bool:
        """Determine if current relationship state qualifies as high-intimacy."""
        warmth = engine_observation.get("warmth", 0.0)
        coherence = engine_observation.get("coherence", 1.0)
        tension = engine_observation.get("tension", 0.0)
        combined = (warmth * 0.5 + coherence * 0.3 + (1.0 - tension) * 0.2)
        return combined >= self._intimacy_threshold

    def observe_user_message(self, session_key: str, text: str, timestamp: float,
                             engine_observation: dict[str, float]) -> None:
        """Observe a user message. Only learns if intimacy is high enough."""
        if not self.is_intimate(engine_observation):
            return
        if session_key not in self._profiles:
            self._profiles[session_key] = RhythmProfile()
        self._profiles[session_key].observe(text, timestamp)

    def get_rhythm_params(self, session_key: str, default_max_part: int = 48,
                          default_cps: float = 7.5, blend: float = 0.6,
                          expression_drive: float = 0.5,
                          recent_ignored_rate: float = 0.0) -> tuple[int, float]:
        """Get modulated segmentation params — deliberate synchronization.

        Unlike passive learning, this is a conscious decision:
        - High expression_drive → actively speed up toward user rhythm
        - High ignored_rate → deliberately slow down (pull back)
        - The blend is modulated by drive (wanting to sync) vs withdrawal (being ignored)
        """
        profile = self._profiles.get(session_key)
        if profile is None or profile.confidence < 0.1:
            return default_max_part, default_cps

        # Deliberate adjustment: drive pushes toward sync, ignored pulls back
        # When ignored a lot, bot deliberately reduces its own frequency
        drive_factor = min(1.0, expression_drive * 1.5)
        withdrawal_factor = min(0.8, recent_ignored_rate * 2.0)

        # Net sync intent: positive = want to sync, negative = pulling back
        sync_intent = drive_factor - withdrawal_factor
        effective_blend = max(0.0, blend * profile.confidence * max(0.1, sync_intent))

        if effective_blend < 0.05:
            # Pulling back: use slower-than-default rhythm
            slowdown = 1.0 + withdrawal_factor * 0.5
            return int(default_max_part * slowdown), default_cps / slowdown

        learned_part = max(12, min(120, int(profile.avg_part_chars)))
        learned_cps = profile.chars_per_second

        blended_part = int(default_max_part * (1 - effective_blend) + learned_part * effective_blend)
        blended_cps = default_cps * (1 - effective_blend) + learned_cps * effective_blend

        return max(12, min(120, blended_part)), max(2.0, min(20.0, blended_cps))

    def profile(self, session_key: str) -> RhythmProfile | None:
        return self._profiles.get(session_key)

    def to_dict(self) -> dict[str, Any]:
        return {k: v.to_dict() for k, v in self._profiles.items()}

    @classmethod
    def from_dict(cls, data: dict[str, Any], intimacy_threshold: float = 0.6) -> "RhythmLearner":
        learner = cls(intimacy_threshold=intimacy_threshold)
        for k, v in data.items():
            learner._profiles[k] = RhythmProfile.from_dict(v)
        return learner
