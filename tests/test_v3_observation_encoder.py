"""RED/GREEN tests for the pure v3 observation encoder and outcome projection."""

from __future__ import annotations

from math import isfinite, log1p, tanh

import pytest

from sylanne_alpha.v3core.canonical import canonical_json_bytes
from sylanne_alpha.v3core.contracts import Action, TurnContextClass
from sylanne_alpha.v3core.formula_v1 import (
    AXIS_DIM,
    OBSERVATION_DIM,
    OUTCOME_PROJECTOR_REVISION,
    SEMANTIC_DEFAULTS,
)
from sylanne_alpha.v3core.observation.encoder import encode_observation, project_outcome
from sylanne_alpha.v3core.observation.models import (
    DERIVED_CHANNELS,
    ObservationFacts,
    ObservationFrame,
    OutcomeFrame,
)


# --- independent reference implementation of the spec section 7 primitives ---


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


# Reference per-channel normalizer for every value-bearing channel.
_REFERENCE = {
    0: _signed,
    1: _clip01,
    2: _clip01,
    3: _clip01,
    4: _clip01,
    5: _clip01,
    6: _clip01,
    7: lambda x: _positive(x, 1.0),
    8: lambda x: _positive(x, 1.0),
    9: _clip01,
    10: lambda x: _positive(x, 1.0),
    11: _signed,
    12: _signed,
    13: _log_length,
    14: lambda x: _positive(x, 2.0),
    15: lambda x: _positive(x, 2.0),
    16: _clip01,
    17: lambda x: _positive(x, 1.0),
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

# Value-bearing raw inputs (all channels except the 7 derived ones).
_FULL_RAW = {
    0: 0.8,
    1: 0.2,
    2: 0.3,
    3: 0.5,
    4: 0.6,
    5: 0.4,
    6: 0.7,
    7: 1.0,
    8: 0.5,
    9: 0.9,
    10: 0.25,
    11: 0.4,
    12: -0.5,
    13: 7.0,
    14: 2.0,
    15: 1.0,
    16: 0.5,
    17: 0.1,
    18: 10.0,
    19: 2.0,
    20: 0.5,
    21: 0.35,
    22: 1.0,
    23: 0.15,
    24: 0.4,
    25: 0.65,
    26: 0.65,
    30: 1.0,
    31: 60.0,
}


def _raw_tuple(overrides: dict[int, float | None] | None = None) -> tuple[float | None, ...]:
    raw: list[float | None] = [None] * OBSERVATION_DIM
    for index, value in _FULL_RAW.items():
        raw[index] = value
    if overrides is not None:
        for index, value in overrides.items():
            raw[index] = value
    return tuple(raw)


def _facts(
    *,
    overrides: dict[int, float | None] | None = None,
    context: TurnContextClass = TurnContextClass.ADDRESSED,
    previous_action: Action | None = Action.SPEAK,
) -> ObservationFacts:
    return ObservationFacts(
        raw_values=_raw_tuple(overrides),
        context=context,
        previous_action=previous_action,
    )


def test_encoder_emits_exactly_36_finite_values_and_a_36_bit_mask() -> None:
    frame = encode_observation(_facts())
    assert type(frame) is ObservationFrame
    assert len(frame.values) == OBSERVATION_DIM == 36
    assert all(type(value) is float and isfinite(value) and 0.0 <= value <= 1.0 for value in frame.values)
    assert type(frame.valid_mask) is int
    # Every channel is provided/known in this fixture, so all 36 bits are valid.
    assert frame.valid_mask == (1 << 36) - 1


def test_every_table_normalization_is_applied_exactly() -> None:
    frame = encode_observation(_facts())
    for index, normalizer in _REFERENCE.items():
        assert frame.values[index] == pytest.approx(normalizer(_FULL_RAW[index])), index
    # A few load-bearing exact values from section 7.
    assert frame.values[0] == pytest.approx(0.9)  # signed(0.8)
    assert frame.values[12] == pytest.approx(0.25)  # signed(-0.5)
    assert frame.values[7] == pytest.approx(tanh(1.0))  # positive(1.0, 1)
    assert frame.values[14] == pytest.approx(tanh(1.0))  # positive(2.0, 2)
    assert frame.values[22] == 1.0  # boolean question
    assert frame.values[26] == pytest.approx(0.5)  # engagement 0.65 / 1.3


def test_missing_channel_uses_semantic_default_and_clears_the_valid_bit() -> None:
    frame = encode_observation(_facts(overrides={7: None, 25: None}))
    for index in (7, 25):
        assert not (frame.valid_mask >> index) & 1
        assert frame.values[index] == SEMANTIC_DEFAULTS[index]
    # Neighbouring valid channels are untouched.
    assert (frame.valid_mask >> 0) & 1
    assert frame.values[0] == pytest.approx(0.9)


@pytest.mark.parametrize(
    "context,expected_bits",
    [
        (TurnContextClass.ADDRESSED, (1.0, 0.0, 0.0)),
        (TurnContextClass.AMBIENT, (0.0, 0.0, 0.0)),
        (TurnContextClass.IDLE, (0.0, 1.0, 0.0)),
        (TurnContextClass.PROACTIVE, (0.0, 0.0, 1.0)),
    ],
)
def test_context_channels_are_mutually_exclusive_and_always_valid(
    context: TurnContextClass,
    expected_bits: tuple[float, float, float],
) -> None:
    frame = encode_observation(_facts(context=context))
    assert (frame.values[27], frame.values[28], frame.values[29]) == expected_bits
    # At most one context bit is hot: mutual exclusivity by construction.
    assert sum(expected_bits) <= 1.0
    for index in (27, 28, 29):
        assert (frame.valid_mask >> index) & 1


@pytest.mark.parametrize(
    "action,onehot",
    [
        (Action.SPEAK, (1.0, 0.0, 0.0, 0.0)),
        (Action.HOLD, (0.0, 1.0, 0.0, 0.0)),
        (Action.CLARIFY, (0.0, 0.0, 1.0, 0.0)),
        (Action.REACH, (0.0, 0.0, 0.0, 1.0)),
    ],
)
def test_known_previous_action_sets_one_hot_and_all_four_valid_bits(
    action: Action,
    onehot: tuple[float, float, float, float],
) -> None:
    frame = encode_observation(_facts(previous_action=action))
    assert tuple(frame.values[32:36]) == onehot
    for index in (32, 33, 34, 35):
        assert (frame.valid_mask >> index) & 1


def test_unknown_previous_action_clears_channels_32_to_35_values_and_bits() -> None:
    frame = encode_observation(_facts(previous_action=None))
    for index in (32, 33, 34, 35):
        assert frame.values[index] == 0.0
        assert not (frame.valid_mask >> index) & 1


def test_facts_reject_non_none_values_at_derived_channels() -> None:
    assert DERIVED_CHANNELS == frozenset({27, 28, 29, 32, 33, 34, 35})
    for index in sorted(DERIVED_CHANNELS):
        raw = list(_raw_tuple())
        raw[index] = 1.0
        with pytest.raises(ValueError):
            ObservationFacts(
                raw_values=tuple(raw),
                context=TurnContextClass.ADDRESSED,
                previous_action=None,
            )


def test_invalid_channel_value_is_inert_downstream_and_leaves_valid_data_identical() -> None:
    # Channel 25 (valence cue) invalid, channel 0 valid: valence should read only u[0].
    frame = encode_observation(_facts(overrides={25: None}))
    assert not (frame.valid_mask >> 25) & 1

    tampered_values = list(frame.values)
    tampered_values[25] = 0.9  # arbitrary in-range value at an invalid slot
    tampered = ObservationFrame(values=tuple(tampered_values), valid_mask=frame.valid_mask)

    # Downstream projection is byte-identical regardless of the invalid slot's value.
    assert canonical_json_bytes(project_outcome(frame)) == canonical_json_bytes(project_outcome(tampered))
    # Every valid value and every bit are unchanged.
    assert frame.valid_mask == tampered.valid_mask
    for index in range(OBSERVATION_DIM):
        if (frame.valid_mask >> index) & 1:
            assert frame.values[index] == tampered.values[index]


# --- outcome projection (section 11.1 / 11.2) ---


def _frame_from_values(values: dict[int, float], mask_indices: set[int]) -> ObservationFrame:
    full = [0.0] * OBSERVATION_DIM
    for index, value in values.items():
        full[index] = value
    mask = 0
    for index in mask_indices:
        mask |= 1 << index
    return ObservationFrame(values=tuple(full), valid_mask=mask)


def test_outcome_projection_matches_section_11_1_formulas_when_all_valid() -> None:
    values = {
        0: 0.8,
        1: 0.2,
        2: 0.3,
        4: 0.6,
        6: 0.7,
        9: 0.9,
        11: 0.4,
        17: 0.1,
        19: 0.5,
        20: 0.25,
        21: 0.35,
        22: 1.0,
        23: 0.15,
        25: 0.65,
    }
    frame = _frame_from_values(values, set(values))
    outcome = project_outcome(frame)
    assert type(outcome) is OutcomeFrame
    assert outcome.projector_revision == OUTCOME_PROJECTOR_REVISION
    assert outcome.valid_mask == (1 << AXIS_DIM) - 1

    expected = (
        ((2 * 0.65 - 1) + (2 * 0.8 - 1)) / 2,  # valence
        2 * max(0.35, 0.15) - 1,  # arousal
        1 - 2 * ((0.2 + 0.3 + 0.1) / 3),  # safety
        ((2 * 0.8 - 1) + (0.5 - 0.25)) / 2,  # affiliation
        2 * ((1.0 + 0.6 + (1 - 0.7)) / 3) - 1,  # uncertainty
        2 * 0.6 - 1,  # novelty
        2 * 0.9 - 1,  # agency
        2 * 0.4 - 1,  # expression_pressure
    )
    for index, value in enumerate(expected):
        assert outcome.y[index] == pytest.approx(value), index
        assert -1.0 <= outcome.y[index] <= 1.0


def test_outcome_valence_omits_invalid_contributor() -> None:
    # Only u[0] valid; valence = 2*u[0]-1 (u[25] contributor dropped).
    frame = _frame_from_values({0: 0.8, 25: 0.65}, {0})
    outcome = project_outcome(frame)
    assert (outcome.valid_mask >> 0) & 1
    assert outcome.y[0] == pytest.approx(2 * 0.8 - 1)


def test_outcome_affiliation_warm_minus_cold_requires_both_source_bits() -> None:
    # u[0] valid, u[19] valid but u[20] invalid -> warm-minus-cold contributor dropped.
    frame = _frame_from_values({0: 0.8, 19: 0.5, 20: 0.25}, {0, 19})
    outcome = project_outcome(frame)
    assert outcome.y[3] == pytest.approx(2 * 0.8 - 1)

    # Both warm/cold valid -> contributor participates.
    frame_both = _frame_from_values({0: 0.8, 19: 0.5, 20: 0.25}, {0, 19, 20})
    outcome_both = project_outcome(frame_both)
    assert outcome_both.y[3] == pytest.approx(((2 * 0.8 - 1) + (0.5 - 0.25)) / 2)


def test_outcome_dimension_is_censored_when_no_contributor_is_valid() -> None:
    # Nothing feeding novelty (u[4]) or agency (u[9]) is valid.
    frame = _frame_from_values({0: 0.8}, {0})
    outcome = project_outcome(frame)
    for index in (1, 2, 4, 5, 6, 7):
        assert not (outcome.valid_mask >> index) & 1
        assert outcome.y[index] == 0.0
    # valence/affiliation still valid via u[0].
    assert (outcome.valid_mask >> 0) & 1
    assert (outcome.valid_mask >> 3) & 1


def test_outcome_frame_is_finite_and_clipped_under_extreme_inputs() -> None:
    values = {index: 1.0 for index in range(OBSERVATION_DIM)}
    frame = _frame_from_values(values, set(range(OBSERVATION_DIM)))
    outcome = project_outcome(frame)
    assert all(type(value) is float and isfinite(value) and -1.0 <= value <= 1.0 for value in outcome.y)
