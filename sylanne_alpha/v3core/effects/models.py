"""Closed effect vocabulary emitted by the deterministic core.

The three ``V3*Effect`` records plus :class:`EffectBundle` are the closed,
canonical-registry-declared union the ``EffectCommitter`` journals.
:class:`DecisionPlan` and :class:`StateDelta` are the orchestrator's semantic
outputs (design section 6): a text-free finite decision and the complete
proposed next-state change.  They are pure, self-validating result DTOs (like
:class:`~sylanne_alpha.v3core.dynamics.models.MultiscaleAdvance`) and are *not*
registered — modules never persist them directly; only the closed
``EffectBundle`` (encoded state bytes + trace bytes + metric scalars) crosses the
persistence boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from ..canonical import assert_exact_type, assert_valid_dto
from ..contracts import Action
from ..expression.policy import ExpressionConstraints
from ..state.models import V3State


@dataclass(frozen=True, slots=True)
class V3StateEffect:
    payload: bytes

    def __post_init__(self) -> None:
        assert_exact_type(self.payload, bytes, "payload")
        assert_valid_dto(self)


@dataclass(frozen=True, slots=True)
class V3TraceEffect:
    payload: bytes

    def __post_init__(self) -> None:
        assert_exact_type(self.payload, bytes, "payload")
        assert_valid_dto(self)


@dataclass(frozen=True, slots=True)
class V3MetricEffect:
    name: str
    value: int | float

    def __post_init__(self) -> None:
        assert_exact_type(self.name, str, "name")
        assert_exact_type(self.value, (int, float), "value")
        assert_valid_dto(self)
        if not self.name:
            raise ValueError("metric name must not be empty")


Effect = V3StateEffect | V3TraceEffect | V3MetricEffect
EFFECT_TYPES = (V3StateEffect, V3TraceEffect, V3MetricEffect)


@dataclass(frozen=True, slots=True)
class EffectBundle:
    effects: tuple[Effect, ...]

    def __post_init__(self) -> None:
        if type(self.effects) is not tuple or not all(type(effect) in EFFECT_TYPES for effect in self.effects):
            raise TypeError("EffectBundle accepts only the closed v3 effect union")
        assert_valid_dto(self)


@dataclass(frozen=True, slots=True)
class DecisionPlan:
    """A finite, text-free decision (design section 6): never a host Reply."""

    action: Action
    confidence: float
    expression: ExpressionConstraints
    reasons: tuple

    def __post_init__(self) -> None:
        assert_exact_type(self.action, Action, "action")
        assert_exact_type(self.confidence, float, "confidence")
        if not isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be a probability in [0,1]")
        assert_exact_type(self.expression, ExpressionConstraints, "expression")
        if self.expression.action is not self.action:
            raise ValueError("expression constraints must match the decided action")
        assert_exact_type(self.reasons, tuple, "reasons")
        for index, reason in enumerate(self.reasons):
            assert_exact_type(reason, str, f"reasons[{index}]")


@dataclass(frozen=True, slots=True)
class StateDelta:
    """All proposed next-state changes (design section 6): modules never persist directly.

    ``next_state`` is the canonical *decoded* (float16-quantized) advancing state;
    ``payload_digest`` hashes the quantized persistence bytes; ``base_revision`` is
    the revision the delta advances from.
    """

    next_state: V3State
    payload_digest: str
    base_revision: int

    def __post_init__(self) -> None:
        assert_exact_type(self.next_state, V3State, "next_state")
        assert_exact_type(self.payload_digest, str, "payload_digest")
        if len(self.payload_digest) != 64:
            raise ValueError("payload_digest must be a 256-bit hex digest")
        assert_exact_type(self.base_revision, int, "base_revision")
        if self.base_revision < 0:
            raise ValueError("base_revision must be non-negative")
        if self.next_state.revision != self.base_revision + 1:
            raise ValueError("next_state.revision must advance base_revision by exactly one")
