"""Frozen result models for the global-workspace stage (design section 10).

These are pure, self-validating result DTOs (like
:class:`~sylanne_alpha.v3core.dynamics.models.MultiscaleAdvance`): they check
their own shape/finiteness/bounds and are never persisted, so they are not part
of the sealed canonical registry.  A :class:`WorkspaceProposal` carries a stable
id, its legal action, a source index into the persistent source-refractory
vector, a clipped salience, a bounded confidence, and a 16-dimensional key.  A
:class:`WorkspaceBroadcast` carries the competition outcome: per-proposal
activation/inhibition, the 0/1/2 broadcast set with its mode, per-legal-action
support and bounded log-evidence, and the advanced source-refractory vector.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from ..canonical import assert_exact_type
from ..contracts import Action
from ..formula_v1 import PROPOSAL_SALIENCE_BOUNDS, WORKSPACE_CAPACITY

_SALIENCE_LO, _SALIENCE_HI = PROPOSAL_SALIENCE_BOUNDS
_KEY_DIM = 16

WORKSPACE_MODES = ("EMPTY", "SINGLE_LEGAL", "TOP1", "TOP2_AMBIGUOUS")


def _check_float(value: object, low: float, high: float, name: str) -> None:
    assert_exact_type(value, float, name)
    if not isfinite(value):
        raise ValueError(f"{name} must be finite")
    if not low <= value <= high:
        raise ValueError(f"{name} must lie in [{low}, {high}]")


@dataclass(frozen=True, slots=True)
class WorkspaceProposal:
    """One legal, present workspace proposal."""

    proposal_id: str
    action: Action
    source_index: int
    salience: float
    confidence: float
    key: tuple

    def __post_init__(self) -> None:
        assert_exact_type(self.proposal_id, str, "proposal_id")
        assert_exact_type(self.action, Action, "action")
        assert_exact_type(self.source_index, int, "source_index")
        if not 0 <= self.source_index < WORKSPACE_CAPACITY:
            raise ValueError("source_index must index the source-refractory vector")
        _check_float(self.salience, _SALIENCE_LO, _SALIENCE_HI, "salience")
        _check_float(self.confidence, 0.0, 1.0, "confidence")
        assert_exact_type(self.key, tuple, "key")
        if len(self.key) != _KEY_DIM:
            raise ValueError("key must have exactly 16 entries")
        for index, value in enumerate(self.key):
            assert_exact_type(value, float, f"key[{index}]")
            if not isfinite(value):
                raise ValueError("key entries must be finite")
        if not self.proposal_id:
            raise ValueError("proposal_id must not be empty")


@dataclass(frozen=True, slots=True)
class WorkspaceBroadcast:
    """The bounded, registration-order-invariant competition result."""

    proposals: tuple
    effective_salience: tuple
    activation: tuple
    inhibition: tuple
    broadcast_ids: tuple
    mode: str
    support: tuple
    log_evidence: tuple
    source_refractory_next: tuple

    def __post_init__(self) -> None:
        assert_exact_type(self.proposals, tuple, "proposals")
        count = len(self.proposals)
        for index, proposal in enumerate(self.proposals):
            assert_exact_type(proposal, WorkspaceProposal, f"proposals[{index}]")
        for name, values in (
            ("effective_salience", self.effective_salience),
            ("activation", self.activation),
            ("inhibition", self.inhibition),
        ):
            assert_exact_type(values, tuple, name)
            if len(values) != count:
                raise ValueError(f"{name} must align with the proposals")
            for value in values:
                assert_exact_type(value, float, name)
                if not isfinite(value):
                    raise ValueError(f"{name} must be finite")
        assert_exact_type(self.broadcast_ids, tuple, "broadcast_ids")
        if len(self.broadcast_ids) > 2:
            raise ValueError("at most two proposals may broadcast")
        for value in self.broadcast_ids:
            assert_exact_type(value, str, "broadcast_ids entry")
        assert_exact_type(self.mode, str, "mode")
        if self.mode not in WORKSPACE_MODES:
            raise ValueError("mode must be a declared workspace mode")
        for name, mapping in (("support", self.support), ("log_evidence", self.log_evidence)):
            assert_exact_type(mapping, tuple, name)
            for entry in mapping:
                assert_exact_type(entry, tuple, f"{name} entry")
                if len(entry) != 2:
                    raise ValueError(f"{name} entries must be (action_name, value)")
                assert_exact_type(entry[0], str, f"{name} action name")
                assert_exact_type(entry[1], float, f"{name} value")
                if not isfinite(entry[1]):
                    raise ValueError(f"{name} value must be finite")
        for _name, value in self.log_evidence:
            if not -2.0 <= value <= 2.0:
                raise ValueError("workspace log-evidence must lie in [-2,2]")
        assert_exact_type(self.source_refractory_next, tuple, "source_refractory_next")
        if len(self.source_refractory_next) != WORKSPACE_CAPACITY:
            raise ValueError("source_refractory_next must have one entry per source")
        for value in self.source_refractory_next:
            _check_float(value, 0.0, 1.0, "source_refractory_next entry")


__all__ = ["WORKSPACE_MODES", "WorkspaceBroadcast", "WorkspaceProposal"]
