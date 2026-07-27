"""Frozen observation and outcome frames for the deterministic v3 core.

These DTOs are pure containers.  They validate their own shape, finiteness, and
bounds without depending on the sealed canonical registry, mirroring the manual
validation style of the frozen v2 fact snapshots.  Semantic-default numbers only
keep the fixed-width tensor finite; they are never interpreted as evidence, so
every downstream consumer gates on ``valid_mask``.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from ..canonical import assert_exact_type
from ..contracts import Action, TurnContextClass
from ..formula_v1 import AXIS_DIM, OBSERVATION_DIM, OUTCOME_PROJECTOR_REVISION


# Context bits (27-29) are derived from the authoritative TurnContextClass and the
# previous-action bits (32-35) from the resolved actual action.  They are never
# supplied as raw facts, so ObservationFacts requires them to be absent.
CONTEXT_CHANNELS = (27, 28, 29)
PREVIOUS_ACTION_CHANNELS = (32, 33, 34, 35)
DERIVED_CHANNELS = frozenset(CONTEXT_CHANNELS + PREVIOUS_ACTION_CHANNELS)


@dataclass(frozen=True, slots=True)
class ObservationFacts:
    """Immutable core input: raw per-channel facts plus authoritative context."""

    raw_values: tuple
    context: TurnContextClass
    previous_action: Action | None = None

    def __post_init__(self) -> None:
        assert_exact_type(self.raw_values, tuple, "raw_values")
        if len(self.raw_values) != OBSERVATION_DIM:
            raise ValueError("raw_values must have exactly OBSERVATION_DIM entries")
        for index, value in enumerate(self.raw_values):
            if index in DERIVED_CHANNELS:
                if value is not None:
                    raise ValueError("derived observation channels must be None in facts")
                continue
            if value is None:
                continue
            assert_exact_type(value, float, f"raw_values[{index}]")
            if not isfinite(value):
                raise ValueError("raw observation values must be finite")
        assert_exact_type(self.context, TurnContextClass, "context")
        if self.previous_action is not None:
            assert_exact_type(self.previous_action, Action, "previous_action")


@dataclass(frozen=True, slots=True)
class ObservationFrame:
    """Fixed-width normalized observation with a 36-bit validity mask."""

    values: tuple
    valid_mask: int

    def __post_init__(self) -> None:
        assert_exact_type(self.values, tuple, "values")
        if len(self.values) != OBSERVATION_DIM:
            raise ValueError("values must have exactly OBSERVATION_DIM entries")
        for index, value in enumerate(self.values):
            assert_exact_type(value, float, f"values[{index}]")
            if not isfinite(value):
                raise ValueError("observation values must be finite")
            if not 0.0 <= value <= 1.0:
                raise ValueError("observation values must be normalized to [0,1]")
        assert_exact_type(self.valid_mask, int, "valid_mask")
        if not 0 <= self.valid_mask < (1 << OBSERVATION_DIM):
            raise ValueError("valid_mask must be a 36-bit mask")

    def is_valid(self, index: int) -> bool:
        if type(index) is not int or not 0 <= index < OBSERVATION_DIM:
            raise ValueError("index must be a valid observation channel")
        return bool((self.valid_mask >> index) & 1)


@dataclass(frozen=True, slots=True)
class OutcomeFrame:
    """Eight-axis normalized outcome projection with per-axis validity."""

    y: tuple
    valid_mask: int
    projector_revision: str

    def __post_init__(self) -> None:
        assert_exact_type(self.y, tuple, "y")
        if len(self.y) != AXIS_DIM:
            raise ValueError("y must have exactly AXIS_DIM entries")
        for index, value in enumerate(self.y):
            assert_exact_type(value, float, f"y[{index}]")
            if not isfinite(value):
                raise ValueError("outcome values must be finite")
            if not -1.0 <= value <= 1.0:
                raise ValueError("outcome values must be clipped to [-1,1]")
        assert_exact_type(self.valid_mask, int, "valid_mask")
        if not 0 <= self.valid_mask < (1 << AXIS_DIM):
            raise ValueError("valid_mask must be an 8-bit mask")
        assert_exact_type(self.projector_revision, str, "projector_revision")
        if self.projector_revision != OUTCOME_PROJECTOR_REVISION:
            raise ValueError("projector_revision must match the formula-v1 outcome revision")

    def is_valid(self, index: int) -> bool:
        if type(index) is not int or not 0 <= index < AXIS_DIM:
            raise ValueError("index must be a valid outcome axis")
        return bool((self.valid_mask >> index) & 1)


__all__ = [
    "CONTEXT_CHANNELS",
    "DERIVED_CHANNELS",
    "PREVIOUS_ACTION_CHANNELS",
    "ObservationFacts",
    "ObservationFrame",
    "OutcomeFrame",
]
