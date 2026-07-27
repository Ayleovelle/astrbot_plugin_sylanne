"""Frozen result models for finite-action active inference (design section 11).

These are pure, self-validating result DTOs (like
:class:`~sylanne_alpha.v3core.dynamics.models.MultiscaleAdvance`): they are never
persisted, so they are not part of the sealed canonical registry.

``ReservoirFeaturesV1`` is the named reservoir feature output consumed by the
workspace/policy (design section 18 terminology gate withholds a scientific
alias until the ablation gates pass).  ``TransitionBelief`` is one action's
diagonal-Gaussian generative belief; ``ActionCandidate`` carries every traced EFE
term and the posterior for one legal action; ``PolicyScorerResult`` is the whole
turn's decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from ..canonical import assert_exact_type
from ..contracts import Action
from ..formula_v1 import AXIS_DIM, SNN_SUMMARY_DIM


def _check_axis_vector(values: object, name: str) -> None:
    assert_exact_type(values, tuple, name)
    if len(values) != AXIS_DIM:
        raise ValueError(f"{name} must have exactly {AXIS_DIM} entries")
    for index, value in enumerate(values):
        assert_exact_type(value, float, f"{name}[{index}]")
        if not isfinite(value):
            raise ValueError(f"{name}[{index}] must be finite")


def _check_finite(value: object, name: str) -> None:
    assert_exact_type(value, float, name)
    if not isfinite(value):
        raise ValueError(f"{name} must be finite")


@dataclass(frozen=True, slots=True)
class ReservoirFeaturesV1:
    """Named reservoir feature output: the 16-value summary and its validity."""

    summary: tuple
    valid: bool

    def __post_init__(self) -> None:
        assert_exact_type(self.summary, tuple, "summary")
        if len(self.summary) != SNN_SUMMARY_DIM:
            raise ValueError("summary must have exactly 16 entries")
        for index, value in enumerate(self.summary):
            assert_exact_type(value, float, f"summary[{index}]")
            if not isfinite(value):
                raise ValueError(f"summary[{index}] must be finite")
        assert_exact_type(self.valid, bool, "valid")


@dataclass(frozen=True, slots=True)
class TransitionBelief:
    """One action's diagonal-Gaussian predictive belief and likelihood variance."""

    action: Action
    mu: tuple
    predictive_var: tuple
    likelihood_var: tuple

    def __post_init__(self) -> None:
        assert_exact_type(self.action, Action, "action")
        _check_axis_vector(self.mu, "mu")
        _check_axis_vector(self.predictive_var, "predictive_var")
        _check_axis_vector(self.likelihood_var, "likelihood_var")


@dataclass(frozen=True, slots=True)
class ActionCandidate:
    """Everything traced for one legal action (design 16.2)."""

    action: Action
    mu: tuple
    predictive_var: tuple
    prior_log: float
    workspace_log_evidence: float
    refractory_penalty: float
    risk: float
    ambiguity: float
    information_gain: float
    expected_free_energy: float
    logit: float
    posterior: float

    def __post_init__(self) -> None:
        assert_exact_type(self.action, Action, "action")
        _check_axis_vector(self.mu, "mu")
        _check_axis_vector(self.predictive_var, "predictive_var")
        for name in (
            "prior_log",
            "workspace_log_evidence",
            "refractory_penalty",
            "risk",
            "ambiguity",
            "information_gain",
            "expected_free_energy",
            "logit",
            "posterior",
        ):
            _check_finite(getattr(self, name), name)
        if not 0.0 <= self.posterior <= 1.0:
            raise ValueError("posterior must be a probability in [0,1]")


@dataclass(frozen=True, slots=True)
class PolicyScorerResult:
    """The full policy decision for one turn."""

    decision_state: tuple
    candidates: tuple
    selected_action: Action
    confidence: float

    def __post_init__(self) -> None:
        _check_axis_vector(self.decision_state, "decision_state")
        assert_exact_type(self.candidates, tuple, "candidates")
        if not self.candidates:
            raise ValueError("a legal turn must have at least one candidate")
        for index, candidate in enumerate(self.candidates):
            assert_exact_type(candidate, ActionCandidate, f"candidates[{index}]")
        assert_exact_type(self.selected_action, Action, "selected_action")
        _check_finite(self.confidence, "confidence")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence (p1-p2) must lie in [0,1]")
        if self.selected_action not in {candidate.action for candidate in self.candidates}:
            raise ValueError("selected_action must be one of the legal candidates")


__all__ = [
    "ActionCandidate",
    "PolicyScorerResult",
    "ReservoirFeaturesV1",
    "TransitionBelief",
]
