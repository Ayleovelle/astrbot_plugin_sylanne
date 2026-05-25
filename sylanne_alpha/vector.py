from __future__ import annotations

from collections.abc import Mapping


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp *value* between *lo* and *hi* (inclusive)."""
    return max(lo, min(hi, float(value)))


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

STATE_INDEX = {axis: index for index, axis in enumerate(STATE_AXES)}
EVENT_INDEX = {axis: index for index, axis in enumerate(EVENT_AXES)}

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
    event_values = tuple(float(event.get(axis, 0.0)) for axis in EVENT_AXES)
    delta_values = [0.0] * len(STATE_AXES)
    for state_index, terms in WEIGHT_TERMS:
        delta_values[state_index] = sum(
            event_values[event_index] * weight for event_index, weight in terms
        )
    return {axis: delta_values[index] for index, axis in enumerate(STATE_AXES)}
