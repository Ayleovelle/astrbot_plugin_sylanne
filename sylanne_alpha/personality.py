"""Sylanne-Embodiment Bidirectional Personality System.

Dual-layer architecture:
  - Embodiment Five (deep structure): computation-driven, slow drift
  - Sylanne Six (surface expression): text-driven, fast drift, bounded by Embodiment

Drift dynamics use Dual-EMA consensus, homeostatic set-point, and inertia.
"""

from __future__ import annotations

import hashlib
import math
from collections import deque
from typing import Any

PERSONALITY_SCHEMA_VERSION = "sylanne.alpha.personality.embodiment.v1"

EMBODIMENT_TRAITS = (
    "expression_drive_trait",
    "perception_acuity",
    "boundary_permeability",
    "inner_order",
    "relational_gravity",
)

SYLANNE_TRAITS = (
    "warmth_bias",
    "edge",
    "curiosity",
    "patience",
    "intimacy_gravity",
    "sovereignty_guard",
)

# Legacy Big Five → Embodiment Five mapping
_LEGACY_MAP = {
    "extraversion": "expression_drive_trait",
    "neuroticism": "perception_acuity",
    "openness": "boundary_permeability",
    "conscientiousness": "inner_order",
    "agreeableness": "relational_gravity",
}

_REVERSE_LEGACY_MAP = {v: k for k, v in _LEGACY_MAP.items()}

# Hard bounds for Embodiment traits
_TRAIT_FLOOR = 0.05
_TRAIT_CEIL = 0.95

# --- Drift signal → Embodiment trait mapping (from design doc 3.1) ---
DRIFT_SIGNALS: dict[str, list[tuple[str, float]]] = {
    "feedback_accepted": [("expression_drive_trait", +0.4)],
    "feedback_ignored": [("expression_drive_trait", -0.2)],
    "feedback_rejected": [
        ("expression_drive_trait", -0.6),
        ("relational_gravity", -0.3),
    ],
    "expression_fired": [("expression_drive_trait", +0.3)],
    "sustained_silence": [("expression_drive_trait", -0.1)],
    "high_tension": [("perception_acuity", +0.5)],
    "low_coherence": [("perception_acuity", +0.4)],
    "high_void_pressure": [("perception_acuity", +0.3)],
    "sustained_positive_valence": [("perception_acuity", -0.3)],
    "boundary_stable": [("perception_acuity", -0.2)],
    "high_surprise_positive": [("boundary_permeability", +0.4)],
    "new_void_created": [("boundary_permeability", +0.3)],
    "sustained_low_surprise": [("boundary_permeability", -0.2)],
    "high_surprise_negative": [("boundary_permeability", -0.3)],
}
DRIFT_SIGNALS.update(
    {
        "high_coherence": [("inner_order", +0.2)],
        "full_route_used": [("inner_order", +0.1)],
        "boundary_self_repair": [("inner_order", +0.15)],
        "system_chaos": [("inner_order", -0.3)],
        "repair_executed": [("relational_gravity", +0.3)],
        "boundary_breached": [("relational_gravity", -0.5)],
        "relaxed_positive": [("relational_gravity", +0.2)],
    }
)


# ---------------------------------------------------------------------------
# TraitMemory: per-trait Dual-EMA with homeostatic set-point
# ---------------------------------------------------------------------------


class TraitMemory:
    """Per-trait state with Dual-EMA consensus and homeostatic attractor."""

    __slots__ = ("value", "fast_ema", "slow_ema", "set_point", "_frozen_ticks")

    def __init__(self, initial: float = 0.5):
        self.value = initial
        self.fast_ema = 0.0  # recent trend (direction signal)
        self.slow_ema = 0.0  # long-term baseline (direction signal)
        self.set_point = initial
        self._frozen_ticks = 0

    def update(self, raw_delta: float) -> float:
        """Apply a drift delta with Dual-EMA consensus logic.

        Returns the actual delta applied.
        """
        if self._frozen_ticks > 0:
            self._frozen_ticks -= 1
            return 0.0

        # Update EMAs (τ_fast=50, τ_slow=500)
        alpha_fast = 2.0 / (50.0 + 1.0)
        alpha_slow = 2.0 / (500.0 + 1.0)
        self.fast_ema = (1.0 - alpha_fast) * self.fast_ema + alpha_fast * raw_delta
        self.slow_ema = (1.0 - alpha_slow) * self.slow_ema + alpha_slow * raw_delta

        # Consensus: same direction → full drift; opposite → 50% of slow
        if self.fast_ema * self.slow_ema > 0:
            effective = raw_delta
        else:
            effective = raw_delta * 0.5

        old = self.value
        self.value = max(_TRAIT_FLOOR, min(_TRAIT_CEIL, self.value + effective))
        actual = self.value - old

        # Set-point evolution (τ ≈ 5000)
        self.set_point += 0.0004 * (self.value - self.set_point)
        return actual

    def recovery_pull(self) -> float:
        """Homeostatic force toward set_point."""
        return (self.set_point - self.value) * 0.3

    def freeze(self, ticks: int) -> None:
        self._frozen_ticks = ticks

    @property
    def frozen(self) -> bool:
        return self._frozen_ticks > 0

    def to_dict(self) -> dict[str, float]:
        return {
            "value": round(self.value, 6),
            "fast_ema": round(self.fast_ema, 6),
            "slow_ema": round(self.slow_ema, 6),
            "set_point": round(self.set_point, 6),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TraitMemory":
        tm = cls(float(data.get("value", 0.5)))
        tm.fast_ema = float(data.get("fast_ema", 0.0))
        tm.slow_ema = float(data.get("slow_ema", 0.0))
        tm.set_point = float(data.get("set_point", tm.value))
        return tm


# ---------------------------------------------------------------------------
# DriftSignalExtractor: extracts normalized [0,1] signals from computation
# ---------------------------------------------------------------------------


class DriftSignalExtractor:
    """Extracts normalized drift signals from computation results."""

    __slots__ = ("_window",)

    def __init__(self, window_size: int = 10):
        self._window: deque[dict[str, Any]] = deque(maxlen=window_size)

    def extract(self, result: dict[str, Any]) -> dict[str, float]:
        """Extract normalized [0,1] signals from a computation result."""
        self._window.append(result)
        signals: dict[str, float] = {}
        emotion = result.get("emotion", {})
        route = result.get("route", "")
        should_express = result.get("should_express", False)

        # Expression fired
        if should_express:
            signals["expression_fired"] = 1.0

        # Route-based signals
        if route == "skip":
            skip_count = sum(1 for r in self._window if r.get("route") == "skip")
            if skip_count >= 3:
                signals["sustained_silence"] = min(1.0, skip_count / 5.0)
        if route == "full":
            signals["full_route_used"] = 1.0

        # Tension
        tension = float(emotion.get("tension", 0.0))
        if tension > 0.7:
            signals["high_tension"] = min(1.0, (tension - 0.7) / 0.3)

        # Coherence
        coherence = float(result.get("emotion", {}).get("coherence", 1.0))
        if coherence < 0.4:
            signals["low_coherence"] = min(1.0, (0.4 - coherence) / 0.4)
        if coherence > 0.8:
            signals["high_coherence"] = min(1.0, (coherence - 0.8) / 0.2)

        # Void pressure
        void_pressure = float(emotion.get("void_pressure", 0.0))
        if void_pressure > 30:
            signals["high_void_pressure"] = min(1.0, void_pressure / 60.0)

        # Valence patterns
        valence = float(emotion.get("valence", 0.0))
        positive_count = sum(
            1
            for r in self._window
            if float(r.get("emotion", {}).get("valence", 0.0)) > 0.3
        )
        if positive_count >= 5:
            signals["sustained_positive_valence"] = min(1.0, positive_count / 7.0)
        if valence > 0.2 and tension < 0.3:
            signals["relaxed_positive"] = min(1.0, valence)

        # Boundary stability
        stability = float(result.get("boundary_stability", 0.0))
        if stability > 0.9:
            signals["boundary_stable"] = min(1.0, (stability - 0.9) / 0.1)

        # Surprise
        surprise = float(result.get("surprise", 0.0))
        if surprise > 0.6 and valence >= 0:
            signals["high_surprise_positive"] = min(1.0, surprise)
        if surprise > 0.6 and valence < -0.3:
            signals["high_surprise_negative"] = min(1.0, surprise)
        low_surprise_count = sum(
            1 for r in self._window if float(r.get("surprise", 0.0)) < 0.2
        )
        if low_surprise_count >= 8:
            signals["sustained_low_surprise"] = min(1.0, low_surprise_count / 10.0)

        # System chaos
        if coherence < 0.3 and void_pressure > 50:
            signals["system_chaos"] = min(1.0, (50.0 - coherence * 100) / 50.0)

        return signals


# ---------------------------------------------------------------------------
# OscillationDetector
# ---------------------------------------------------------------------------


class OscillationDetector:
    """Detects rapid direction reversals and freezes traits."""

    __slots__ = ("_history",)

    def __init__(self, window: int = 10):
        self._history: dict[str, deque[float]] = {}

    def record(self, trait_name: str, delta: float) -> bool:
        """Record a delta. Returns True if oscillation detected (trait frozen)."""
        if trait_name not in self._history:
            self._history[trait_name] = deque(maxlen=10)
        hist = self._history[trait_name]
        hist.append(delta)
        if len(hist) < 4:
            return False
        # Count direction reversals
        reversals = 0
        for i in range(1, len(hist)):
            if hist[i] * hist[i - 1] < 0:
                reversals += 1
        return reversals >= 6


# ---------------------------------------------------------------------------
# compute_embodiment_drift: core drift formula
# ---------------------------------------------------------------------------


def compute_embodiment_drift(
    traits: dict[str, TraitMemory],
    signals: dict[str, float],
    tick_count: int,
    oscillation_detector: OscillationDetector | None = None,
) -> None:
    """Apply drift to Embodiment traits based on extracted signals.

    Formula: Δ = base_rate × sqrt(signal) × inertia × homeostatic × asymmetric
    """
    base_rate = 0.003
    inertia = 1.0 / (1.0 + math.log(1.0 + tick_count / 500.0))

    for signal_name, signal_value in signals.items():
        if signal_value <= 0 or signal_name not in DRIFT_SIGNALS:
            continue
        mappings = DRIFT_SIGNALS[signal_name]
        signal_magnitude = math.sqrt(signal_value)

        for trait_name, weight in mappings:
            if trait_name not in traits:
                continue
            tm = traits[trait_name]
            if tm.frozen:
                continue

            # Homeostatic resistance
            homeostatic = 1.0 - abs(tm.value - tm.set_point) * 0.3

            # Asymmetric resistance near extremes
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
            actual = tm.update(raw_delta)

            # Oscillation detection
            if oscillation_detector and actual != 0:
                if oscillation_detector.record(trait_name, actual):
                    tm.freeze(20)


# ---------------------------------------------------------------------------
# Sylanne bounds from Embodiment (constraint direction)
# ---------------------------------------------------------------------------


def sylanne_bounds_from_embodiment(
    embodiment: dict[str, TraitMemory],
) -> dict[str, tuple[float, float]]:
    """Compute [min, max] bounds for each Sylanne trait from Embodiment five."""
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
# drift_sylanne_traits: fast text-based drift with Embodiment bounds
# ---------------------------------------------------------------------------


def drift_sylanne_traits(
    personality: dict[str, Any],
    *,
    event: dict[str, Any] | None = None,
    embodiment: dict[str, TraitMemory] | None = None,
) -> dict[str, Any]:
    """Drift Sylanne traits (fast, text-based) with optional Embodiment bounds."""
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
# Legacy-compatible drift_personality (delegates to drift_sylanne_traits)
# ---------------------------------------------------------------------------


def drift_personality(
    personality: dict[str, Any],
    *,
    event: dict[str, Any] | None = None,
    rate: float = 0.02,
) -> dict[str, Any]:
    """Legacy-compatible personality drift. Delegates to drift_sylanne_traits."""
    return drift_sylanne_traits(personality, event=event)


# ---------------------------------------------------------------------------
# initial_personality (updated to include Embodiment traits)
# ---------------------------------------------------------------------------


def initial_personality(
    session_key: str, *, seed_text: str = "Sylanne Soulful"
) -> dict[str, Any]:
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
# Personality normalization: accept both legacy and new names
# ---------------------------------------------------------------------------


def normalize_personality(personality: dict[str, float]) -> dict[str, float]:
    """Accept both old Big Five names and new Embodiment names.

    Returns a dict with BOTH old and new names populated for backwards compat.
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
# Private helpers (preserved from original)
# ---------------------------------------------------------------------------


def _event_direction(text: str) -> dict[str, float]:
    direction: dict[str, float] = {name: 0.0 for name in SYLANNE_TRAITS}
    if any(word in text for word in ("锋利", "直接", "尖锐")):
        direction["edge"] += 1.0
        direction["patience"] -= 0.4
    if any(word in text for word in ("温柔", "靠近", "想你")):
        direction["warmth_bias"] += 1.0
        direction["intimacy_gravity"] += 0.8
    if any(word in text for word in ("边界", "不要", "暂停")):
        direction["sovereignty_guard"] += 1.0
    if not any(abs(value) > 0 for value in direction.values()):
        direction["curiosity"] += 0.5
    return direction


def _voice(traits: dict[str, float]) -> dict[str, Any]:
    return {
        "temperature": round(
            (traits.get("warmth_bias", 0.5) + traits.get("edge", 0.5)) / 2, 6
        ),
        "cadence": "slow_burn" if traits.get("patience", 0.5) >= 0.5 else "quick_cut",
        "boundary": "strong" if traits.get("sovereignty_guard", 0.5) >= 0.6 else "soft",
    }


def _trait(signature: str, index: int, *, base: float) -> float:
    byte = int(signature[index * 2 : index * 2 + 2], 16)
    return round(max(0.0, min(1.0, base + (byte / 255.0 - 0.5) * 0.12)), 6)


def _digest(text: str) -> str:
    return hashlib.blake2s(text.encode("utf-8"), digest_size=12).hexdigest()


__all__ = [
    "PERSONALITY_SCHEMA_VERSION",
    "EMBODIMENT_TRAITS",
    "SYLANNE_TRAITS",
    "TraitMemory",
    "DriftSignalExtractor",
    "OscillationDetector",
    "compute_embodiment_drift",
    "drift_sylanne_traits",
    "drift_personality",
    "initial_personality",
    "normalize_personality",
    "sylanne_bounds_from_embodiment",
    "DRIFT_SIGNALS",
    "_LEGACY_MAP",
    "_REVERSE_LEGACY_MAP",
]
