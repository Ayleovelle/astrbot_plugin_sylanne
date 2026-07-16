"""RED/GREEN tests for Task 9 global workspace (design section 10).

``ProposalArbiterV1`` is pure ``v3core``: it turns the eight-dimensional decision
state, the normalized observation frame, an optional SNN summary, and the
authoritative context into at most eight legal proposals, runs four bounded
competition iterations, and emits a registration-order-invariant broadcast with
per-action support and bounded log-evidence.  It performs no I/O and imports
nothing the firewall forbids.
"""

from __future__ import annotations

from math import exp, isclose

import pytest

from sylanne_alpha.v3core import formula_v1 as formula
from sylanne_alpha.v3core.contracts import Action, TurnContextClass
from sylanne_alpha.v3core.observation.models import ObservationFrame
from sylanne_alpha.v3core.workspace import (
    WorkspaceBroadcast,
    WorkspaceProposal,
    build_proposals,
    run_workspace,
)
from sylanne_alpha.v3core.workspace.competition import (
    ProposalArbiterV1,
    arbitrate,
    proposal_salience,
)

AXIS_DIM = formula.AXIS_DIM
FULL_MASK = (1 << formula.OBSERVATION_DIM) - 1


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #


def _frame(values: tuple | None = None, valid_mask: int = FULL_MASK) -> ObservationFrame:
    if values is None:
        values = tuple(0.5 for _ in range(formula.OBSERVATION_DIM))
    return ObservationFrame(values=values, valid_mask=valid_mask)


def _center(value: float) -> float:
    return 2.0 * value - 1.0


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _clip01(value: float) -> float:
    return _clip(value, 0.0, 1.0)


def _expected_salience(index: int, s: tuple, frame: ObservationFrame, snn: tuple | None) -> float:
    v = frame.values
    if index == 0:
        raw = 1.2 * s[7] + 0.5 * s[1] + 0.3 * _center(v[11])
    elif index == 1:
        raw = 0.9 * abs(s[0]) + 0.7 * s[3] + 0.4 * s[2]
    elif index == 2:
        raw = 1.4 * s[4] + 0.4 * s[5]
    elif index == 3:
        raw = -1.3 * s[2] - 0.6 * s[6] + 0.5 * _center(v[17])
    elif index == 4:
        raw = 1.4 * _center(v[10]) - 0.4 * s[7]
    elif index == 5:
        raw = 1.1 * s[3] + 0.8 * s[7] + 0.3 * s[5]
    elif index == 6:
        raw = 1.2 * snn[10] + 0.6 * s[5]
    else:
        raw = 0.8 * _center(v[30]) + 0.6 * _center(v[26]) + 0.4 * s[3]
    return _clip(raw, -4.0, 4.0)


# --------------------------------------------------------------------------- #
# Proposal construction: salience/confidence/keys/required bits
# --------------------------------------------------------------------------- #


def test_salience_confidence_match_formula_and_bounds() -> None:
    s = (0.6, -0.3, 0.2, 0.7, 0.9, -0.4, 0.5, 0.8)
    snn = tuple(0.1 * i for i in range(formula.SNN_SUMMARY_DIM))
    frame = _frame()
    for index in range(formula.WORKSPACE_CAPACITY):
        salience, present = proposal_salience(index, s, frame, snn)
        assert present is True
        expected = _expected_salience(index, s, frame, snn)
        assert isclose(salience, expected, rel_tol=0, abs_tol=1e-12)
        assert -4.0 <= salience <= 4.0
        confidence = _clip01(0.5 + 0.25 * abs(salience))
        assert 0.0 <= confidence <= 1.0


def test_required_bits_gate_presence() -> None:
    s = tuple(0.0 for _ in range(AXIS_DIM))
    snn = tuple(0.0 for _ in range(formula.SNN_SUMMARY_DIM))
    # body-speak requires bit 11; clearing it makes the proposal absent.
    mask = FULL_MASK & ~(1 << 11)
    _, present = proposal_salience(0, s, _frame(valid_mask=mask), snn)
    assert present is False
    # affect-speak requires nothing observational -> always present.
    _, present = proposal_salience(1, s, _frame(valid_mask=0), snn)
    assert present is True
    # continuity-speak requires {26,30}: clearing either removes it.
    for bit in (26, 30):
        _, present = proposal_salience(7, s, _frame(valid_mask=FULL_MASK & ~(1 << bit)), snn)
        assert present is False


def test_snn_novelty_requires_valid_summary() -> None:
    s = tuple(0.0 for _ in range(AXIS_DIM))
    _, present = proposal_salience(6, s, _frame(), None)
    assert present is False
    _, present = proposal_salience(6, s, _frame(), tuple(0.0 for _ in range(formula.SNN_SUMMARY_DIM)))
    assert present is True


def test_proposal_keys_are_l2_normalized() -> None:
    s = (0.6, -0.3, 0.2, 0.7, 0.9, -0.4, 0.5, 0.8)
    snn = tuple(0.0 for _ in range(formula.SNN_SUMMARY_DIM))
    proposals = build_proposals(s, _frame(), snn, TurnContextClass.ADDRESSED)
    for proposal in proposals:
        assert len(proposal.key) == 16
        norm = sum(value * value for value in proposal.key) ** 0.5
        assert isclose(norm, 1.0, abs_tol=1e-12)


# --------------------------------------------------------------------------- #
# Context masking
# --------------------------------------------------------------------------- #


def test_context_masks_illegal_actions_before_competition() -> None:
    s = tuple(0.0 for _ in range(AXIS_DIM))
    snn = tuple(0.0 for _ in range(formula.SNN_SUMMARY_DIM))
    # IDLE only allows HOLD -> only boundary-hold / fatigue-hold survive.
    proposals = build_proposals(s, _frame(), snn, TurnContextClass.IDLE)
    assert {p.action for p in proposals} == {Action.HOLD}
    assert {p.proposal_id for p in proposals} == {"boundary-hold", "fatigue-hold"}
    # PROACTIVE allows HOLD, REACH.
    proposals = build_proposals(s, _frame(), snn, TurnContextClass.PROACTIVE)
    assert {p.action for p in proposals} <= {Action.HOLD, Action.REACH}


# --------------------------------------------------------------------------- #
# Competition: empty / single / top1 / top2, order invariance, inhibition
# --------------------------------------------------------------------------- #


def _zero_refractory() -> tuple:
    return tuple(0.0 for _ in range(formula.WORKSPACE_CAPACITY))


def test_empty_broadcast_when_no_legal_proposal() -> None:
    s = tuple(0.0 for _ in range(AXIS_DIM))
    # IDLE with both HOLD proposals gated off (17 and 10 invalid) -> empty.
    mask = FULL_MASK & ~(1 << 17) & ~(1 << 10)
    broadcast = run_workspace(s, _frame(valid_mask=mask), None, TurnContextClass.IDLE, _zero_refractory())
    assert broadcast.mode == "EMPTY"
    assert broadcast.broadcast_ids == ()
    for _, value in broadcast.log_evidence:
        assert value == 0.0


def test_single_legal_proposal_broadcasts_with_activation_one() -> None:
    s = tuple(0.0 for _ in range(AXIS_DIM))
    # IDLE, only fatigue-hold present (drop boundary-hold via bit 17).
    mask = FULL_MASK & ~(1 << 17)
    broadcast = run_workspace(s, _frame(valid_mask=mask), None, TurnContextClass.IDLE, _zero_refractory())
    assert broadcast.mode == "SINGLE_LEGAL"
    assert broadcast.broadcast_ids == ("fatigue-hold",)
    assert isclose(broadcast.activation[0], 1.0, abs_tol=1e-12)


def test_registration_order_invariance() -> None:
    s = (0.6, -0.3, 0.2, 0.7, 0.9, -0.4, 0.5, 0.8)
    snn = tuple(0.05 * i for i in range(formula.SNN_SUMMARY_DIM))
    frame = _frame()
    proposals = list(build_proposals(s, frame, snn, TurnContextClass.ADDRESSED))
    forward = arbitrate(tuple(proposals), TurnContextClass.ADDRESSED, _zero_refractory())
    backward = arbitrate(tuple(reversed(proposals)), TurnContextClass.ADDRESSED, _zero_refractory())
    assert forward.mode == backward.mode
    assert forward.broadcast_ids == backward.broadcast_ids
    assert dict(forward.log_evidence) == pytest.approx(dict(backward.log_evidence))


def test_exact_tie_breaks_by_lexicographic_proposal_id() -> None:
    # Two identical-action proposals with equal salience must rank by proposal_id.
    key_a = tuple([1.0] + [0.0] * 15)
    p_b = WorkspaceProposal(
        proposal_id="b-prop", action=Action.SPEAK, source_index=0, salience=2.0, confidence=1.0, key=key_a
    )
    p_a = WorkspaceProposal(
        proposal_id="a-prop", action=Action.SPEAK, source_index=1, salience=2.0, confidence=1.0, key=key_a
    )
    broadcast = arbitrate((p_b, p_a), TurnContextClass.ADDRESSED, _zero_refractory())
    # Ambiguous (identical) -> top-2, but the ranked winner order is lexicographic.
    assert broadcast.broadcast_ids[0] == "a-prop"


def test_source_refractory_update_formula_and_bounds() -> None:
    s = tuple(0.0 for _ in range(AXIS_DIM))
    mask = FULL_MASK & ~(1 << 17)  # only fatigue-hold (source index 4) present in IDLE
    refractory = tuple(0.5 for _ in range(formula.WORKSPACE_CAPACITY))
    broadcast = run_workspace(s, _frame(valid_mask=mask), None, TurnContextClass.IDLE, refractory)
    nxt = broadcast.source_refractory_next
    assert len(nxt) == formula.WORKSPACE_CAPACITY
    for index in range(formula.WORKSPACE_CAPACITY):
        broadcasted = "fatigue-hold" in broadcast.broadcast_ids and index == 4
        expected = _clip(0.72 * 0.5 + (0.45 if broadcasted else 0.0), 0.0, 1.0)
        assert isclose(nxt[index], expected, abs_tol=1e-12)
        assert 0.0 <= nxt[index] <= 1.0


def test_log_evidence_bounded_and_formula() -> None:
    s = (0.6, -0.3, 0.2, 0.7, 0.9, -0.4, 0.5, 0.8)
    snn = tuple(0.05 * i for i in range(formula.SNN_SUMMARY_DIM))
    broadcast = run_workspace(s, _frame(), snn, TurnContextClass.ADDRESSED, _zero_refractory())
    support = dict(broadcast.support)
    mean_support = sum(support.values()) / len(support)
    for action_name, evidence in broadcast.log_evidence:
        expected = _clip(2.0 * (support[action_name] - mean_support), -2.0, 2.0)
        assert isclose(evidence, expected, abs_tol=1e-12)
        assert -2.0 <= evidence <= 2.0


def test_activation_is_softmax_of_final_potentials() -> None:
    s = (0.6, -0.3, 0.2, 0.7, 0.9, -0.4, 0.5, 0.8)
    snn = tuple(0.05 * i for i in range(formula.SNN_SUMMARY_DIM))
    broadcast = run_workspace(s, _frame(), snn, TurnContextClass.ADDRESSED, _zero_refractory())
    # activation is a probability distribution over present proposals.
    assert isclose(sum(broadcast.activation), 1.0, abs_tol=1e-9)
    for value in broadcast.activation:
        assert 0.0 <= value <= 1.0


def test_arbiter_class_matches_function() -> None:
    s = (0.6, -0.3, 0.2, 0.7, 0.9, -0.4, 0.5, 0.8)
    snn = tuple(0.05 * i for i in range(formula.SNN_SUMMARY_DIM))
    frame = _frame()
    proposals = build_proposals(s, frame, snn, TurnContextClass.ADDRESSED)
    arbiter = ProposalArbiterV1()
    a = arbiter.arbitrate(proposals, TurnContextClass.ADDRESSED, _zero_refractory())
    b = arbitrate(proposals, TurnContextClass.ADDRESSED, _zero_refractory())
    assert a.broadcast_ids == b.broadcast_ids
    assert a.mode == b.mode
