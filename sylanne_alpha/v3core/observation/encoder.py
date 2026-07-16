"""Deterministic observation encoder and finite-action outcome projection.

Pure stdlib math over immutable core DTOs.  Section 7 fixes the 36-channel
normalization schema; section 11.1/11.2 fixes the eight-axis OutcomeFrame
projection.  Every path gates on the validity mask: an invalid channel emits no
evidence and its semantic-default value is inert downstream.
"""

from __future__ import annotations

from math import isfinite, log1p, tanh

from ..contracts import Action, TurnContextClass
from ..formula_v1 import AXIS_DIM, OBSERVATION_DIM, OUTCOME_PROJECTOR_REVISION, SEMANTIC_DEFAULTS
from .models import DERIVED_CHANNELS, ObservationFacts, ObservationFrame, OutcomeFrame


# --- section 7 normalization primitives -----------------------------------------


def _clip(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


def _signed(value: float) -> float:
    return 0.5 + 0.5 * _clip(value, -1.0, 1.0)


def _clip01(value: float) -> float:
    return _clip(value, 0.0, 1.0)


def _positive(value: float, k: float) -> float:
    return tanh(max(0.0, value) / k)


def _density(value: float) -> float:
    return tanh(max(0.0, value) / 2.0)


def _log_length(value: float) -> float:
    return tanh(log1p(max(0.0, value)) / 4.0)


def _valence(value: float) -> float:
    return 0.5 + 0.5 * tanh(value / 2.0)


def _engagement(value: float) -> float:
    return _clip(value / 1.3, 0.0, 1.0)


def _log_gap(value: float) -> float:
    return tanh(log1p(min(max(0.0, value), 86400.0)) / 8.0)


def _boolean(value: float) -> float:
    return 1.0 if value else 0.0


# Per-channel normalizer for every value-bearing channel (0-26, 30, 31).  The
# seven derived channels (27-29, 32-35) are computed from the authoritative enum
# and resolved action, not from raw facts.
_NORMALIZERS = {
    0: _signed,
    1: _clip01,
    2: _clip01,
    3: _clip01,
    4: _clip01,
    5: _clip01,
    6: _clip01,
    7: lambda value: _positive(value, 1.0),
    8: lambda value: _positive(value, 1.0),
    9: _clip01,
    10: lambda value: _positive(value, 1.0),
    11: _signed,
    12: _signed,
    13: _log_length,
    14: lambda value: _positive(value, 2.0),
    15: lambda value: _positive(value, 2.0),
    16: _clip01,
    17: lambda value: _positive(value, 1.0),
    18: _log_length,
    19: _density,
    20: _density,
    21: _density,
    22: _boolean,
    23: _density,
    24: _density,
    25: _valence,
    26: _engagement,
    30: _boolean,
    31: _log_gap,
}

_CONTEXT_BITS = {
    TurnContextClass.ADDRESSED: (1.0, 0.0, 0.0),
    TurnContextClass.AMBIENT: (0.0, 0.0, 0.0),
    TurnContextClass.IDLE: (0.0, 1.0, 0.0),
    TurnContextClass.PROACTIVE: (0.0, 0.0, 1.0),
}

_ACTION_CHANNEL = {
    Action.SPEAK: 32,
    Action.HOLD: 33,
    Action.CLARIFY: 34,
    Action.REACH: 35,
}


def encode_observation(facts: ObservationFacts) -> ObservationFrame:
    """Encode raw facts into the fixed 36-channel frame with a validity mask."""

    if type(facts) is not ObservationFacts:
        raise TypeError("facts must have exact type ObservationFacts")

    raw = facts.raw_values
    values = [0.0] * OBSERVATION_DIM
    valid_mask = 0

    for index in range(OBSERVATION_DIM):
        if index in DERIVED_CHANNELS:
            continue
        source = raw[index]
        if source is None:
            values[index] = SEMANTIC_DEFAULTS[index]
            continue
        normalized = _NORMALIZERS[index](source)
        if not isfinite(normalized):
            values[index] = SEMANTIC_DEFAULTS[index]
            continue
        values[index] = _clip01(normalized)
        valid_mask |= 1 << index

    addressed, idle, proactive = _CONTEXT_BITS[facts.context]
    values[27] = addressed
    values[28] = idle
    values[29] = proactive
    valid_mask |= (1 << 27) | (1 << 28) | (1 << 29)

    action = facts.previous_action
    if action is not None:
        hot = _ACTION_CHANNEL[action]
        for channel in (32, 33, 34, 35):
            values[channel] = 1.0 if channel == hot else 0.0
        valid_mask |= (1 << 32) | (1 << 33) | (1 << 34) | (1 << 35)
    else:
        for channel in (32, 33, 34, 35):
            values[channel] = 0.0

    return ObservationFrame(values=tuple(values), valid_mask=valid_mask)


# --- section 11.1 / 11.2 outcome projection -------------------------------------


def _mean(contributors: list[float]) -> float | None:
    if not contributors:
        return None
    return sum(contributors) / len(contributors)


def _max(contributors: list[float]) -> float | None:
    if not contributors:
        return None
    return max(contributors)


def project_outcome(observation: ObservationFrame) -> OutcomeFrame:
    """Project the next observation frame into the eight-axis OutcomeFrame.

    Each contributor inherits its source validity bit (the warm-minus-cold
    affiliation term requires both), invalid outcome dimensions are censored, and
    non-finite results clear their bit.
    """

    if type(observation) is not ObservationFrame:
        raise TypeError("observation must have exact type ObservationFrame")

    u = observation.values
    mask = observation.valid_mask

    def valid(index: int) -> bool:
        return bool((mask >> index) & 1)

    y = [0.0] * AXIS_DIM
    valid_mask = 0

    def emit(axis: int, result: float | None) -> None:
        nonlocal valid_mask
        if result is None or not isfinite(result):
            return
        y[axis] = _clip(result, -1.0, 1.0)
        valid_mask |= 1 << axis

    # 0 valence = valid_mean(2*u[25]-1, 2*u[0]-1)
    valence: list[float] = []
    if valid(25):
        valence.append(2.0 * u[25] - 1.0)
    if valid(0):
        valence.append(2.0 * u[0] - 1.0)
    emit(0, _mean(valence))

    # 1 arousal = 2*max_valid(u[21], u[23]) - 1
    arousal: list[float] = []
    if valid(21):
        arousal.append(u[21])
    if valid(23):
        arousal.append(u[23])
    arousal_max = _max(arousal)
    emit(1, None if arousal_max is None else 2.0 * arousal_max - 1.0)

    # 2 safety = 1 - 2*valid_mean(u[1], u[2], u[17])
    safety: list[float] = []
    if valid(1):
        safety.append(u[1])
    if valid(2):
        safety.append(u[2])
    if valid(17):
        safety.append(u[17])
    safety_mean = _mean(safety)
    emit(2, None if safety_mean is None else 1.0 - 2.0 * safety_mean)

    # 3 affiliation = valid_mean(2*u[0]-1, u[19]-u[20]); warm-minus-cold needs both bits.
    affiliation: list[float] = []
    if valid(0):
        affiliation.append(2.0 * u[0] - 1.0)
    if valid(19) and valid(20):
        affiliation.append(u[19] - u[20])
    emit(3, _mean(affiliation))

    # 4 uncertainty = 2*valid_mean(u[22], u[4], 1-u[6]) - 1
    uncertainty: list[float] = []
    if valid(22):
        uncertainty.append(u[22])
    if valid(4):
        uncertainty.append(u[4])
    if valid(6):
        uncertainty.append(1.0 - u[6])
    uncertainty_mean = _mean(uncertainty)
    emit(4, None if uncertainty_mean is None else 2.0 * uncertainty_mean - 1.0)

    # 5 novelty = 2*u[4]-1
    emit(5, (2.0 * u[4] - 1.0) if valid(4) else None)
    # 6 agency = 2*u[9]-1
    emit(6, (2.0 * u[9] - 1.0) if valid(9) else None)
    # 7 expression_pressure = 2*u[11]-1
    emit(7, (2.0 * u[11] - 1.0) if valid(11) else None)

    return OutcomeFrame(y=tuple(y), valid_mask=valid_mask, projector_revision=OUTCOME_PROJECTOR_REVISION)


__all__ = ["encode_observation", "project_outcome"]
