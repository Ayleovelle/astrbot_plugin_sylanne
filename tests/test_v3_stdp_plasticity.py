"""RED/GREEN tests for Task 8 reward-gated STDP settlement (design section 8.3).

Only excitatory-to-excitatory synapses are plastic.  Credit is gated by the
originating STDP profile and shadow/actual action equality; the one-shot weight
update runs a homeostatic pull toward ``W0`` and a deterministic incoming-budget
projection in canonical ``synapse_id`` order, so per-edge bounds, Dale signs, and
the incoming absolute-weight limit ``<= 1.2`` hold simultaneously after every
update.
"""

from __future__ import annotations

import pytest

from sylanne_alpha.v3core import formula_v1 as formula
from sylanne_alpha.v3core.contracts import Action
from sylanne_alpha.v3core.spiking import plasticity
from sylanne_alpha.v3core.state.models import PLASTIC_SYNAPSE_COUNT

PLASTIC = formula.PLASTIC_SYNAPSES
COUNT = len(PLASTIC)
W0 = formula.RECURRENT_EE_WEIGHT
LO, HI = formula.SNN_EXCITATORY_WEIGHT_BOUNDS


# --------------------------------------------------------------------------- #
# Independent references
# --------------------------------------------------------------------------- #


def _fixed_l1(post: int) -> float:
    return sum(
        abs(formula.recurrent_initial_weight(post, pre))
        for pre in formula.RECURRENT_TOPOLOGY[post]
        if not (post < formula.SNN_EXCITATORY and pre < formula.SNN_EXCITATORY)
    )


def _plastic_by_post() -> dict[int, list[int]]:
    grouped: dict[int, list[int]] = {}
    for index, (post, _pre) in enumerate(PLASTIC):
        grouped.setdefault(post, []).append(index)
    return grouped


# --------------------------------------------------------------------------- #
# Only excitatory-to-excitatory plasticity
# --------------------------------------------------------------------------- #


def test_plastic_synapses_are_all_excitatory_to_excitatory() -> None:
    assert COUNT == PLASTIC_SYNAPSE_COUNT == 473
    for post, pre in PLASTIC:
        assert 0 <= post < formula.SNN_EXCITATORY
        assert 0 <= pre < formula.SNN_EXCITATORY
        assert post != pre
        assert formula.recurrent_is_plastic(post, pre) is True
    # canonical order is post-major then recurrent-topology order
    assert list(PLASTIC) == [
        (post, pre)
        for post in range(formula.SNN_EXCITATORY)
        for pre in formula.RECURRENT_TOPOLOGY[post]
        if pre < formula.SNN_EXCITATORY
    ]


# --------------------------------------------------------------------------- #
# Credit gate: originating profile AND action equality
# --------------------------------------------------------------------------- #


def test_credit_gate_requires_profile_and_action_equality() -> None:
    assert plasticity.compute_credit_gate(True, Action.SPEAK, Action.SPEAK) is True
    assert plasticity.compute_credit_gate(True, Action.SPEAK, Action.HOLD) is False
    assert plasticity.compute_credit_gate(False, Action.SPEAK, Action.SPEAK) is False
    assert plasticity.compute_credit_gate(True, Action.SPEAK, None) is False
    assert plasticity.compute_credit_gate(True, None, None) is False


def test_stdp_delta_is_zero_unless_gated() -> None:
    assert plasticity.stdp_delta(0.8, 0.2, True) == pytest.approx(0.6)
    assert plasticity.stdp_delta(0.8, 0.2, False) == 0.0
    assert plasticity.stdp_delta(-0.5, 0.3, True) == pytest.approx(-0.8)


# --------------------------------------------------------------------------- #
# One-shot weight update mechanics
# --------------------------------------------------------------------------- #


def test_apply_stdp_moves_weights_in_credit_direction_and_is_pure() -> None:
    weights = tuple(W0 for _ in range(COUNT))
    eligibility = tuple(1.0 for _ in range(COUNT))
    new_weights, clipped = plasticity.apply_stdp(weights, eligibility, 1.0)
    assert len(new_weights) == COUNT
    # candidate = clip(W0 + 0.002*1*1 - 1e-5*(W0-W0)) = W0 + 0.002; well under budget -> unclipped
    assert new_weights[0] == pytest.approx(W0 + 0.002)
    assert clipped == pytest.approx(0.0, abs=1e-9)
    # deterministic / pure
    assert plasticity.apply_stdp(weights, eligibility, 1.0)[0] == new_weights


def test_homeostasis_pulls_toward_w0_when_delta_zero() -> None:
    above = tuple(0.20 for _ in range(COUNT))
    below = tuple(0.02 for _ in range(COUNT))
    high_new, _ = plasticity.apply_stdp(above, tuple(0.0 for _ in range(COUNT)), 0.0)
    low_new, _ = plasticity.apply_stdp(below, tuple(0.0 for _ in range(COUNT)), 0.0)
    assert high_new[0] == pytest.approx(0.20 - 1e-5 * (0.20 - W0))
    assert high_new[0] < 0.20
    assert low_new[0] == pytest.approx(0.02 - 1e-5 * (0.02 - W0))
    assert low_new[0] > 0.02


# --------------------------------------------------------------------------- #
# Canonical-order incoming-budget projection and simultaneous invariants
# --------------------------------------------------------------------------- #


def test_budget_projection_caps_incoming_l1_in_canonical_order() -> None:
    weights = tuple(HI for _ in range(COUNT))  # all at the per-edge ceiling
    eligibility = tuple(3.0 for _ in range(COUNT))
    new_weights, clipped = plasticity.apply_stdp(weights, eligibility, 1.0)

    by_post = _plastic_by_post()
    # find at least one post whose plastic demand exceeds its budget
    saturated_posts = [post for post, idx in by_post.items() if len(idx) * HI > 1.2 - _fixed_l1(post)]
    assert saturated_posts, "expected some saturated postsynaptic neuron"

    for post, indices in by_post.items():
        budget = 1.2 - _fixed_l1(post)
        assigned = [new_weights[i] for i in indices]
        # (1) incoming absolute weight limit holds simultaneously with fixed edges
        assert _fixed_l1(post) + sum(assigned) <= 1.2 + 1e-9
        # (2) each edge respects the Dale / per-edge bound
        for value in assigned:
            assert LO <= value <= HI
        # (3) canonical order: a nonzero assignment never follows a zeroed one
        zero_seen = False
        for value in assigned:
            if value == 0.0:
                zero_seen = True
            elif zero_seen:
                pytest.fail("later canonical synapse kept weight after an earlier one hit zero")
        # (4) exact greedy projection reference
        remaining = max(0.0, budget)
        expected = []
        for _ in indices:
            take = min(HI, remaining)  # candidate is HI for every edge here
            expected.append(take)
            remaining -= take
        assert assigned == pytest.approx(expected)
    assert clipped > 0.0  # some candidate mass was projected away


def test_all_updates_keep_bounds_and_l1_under_random_deltas() -> None:
    import random

    rng = random.Random(2718)
    by_post = _plastic_by_post()
    for _ in range(200):
        weights = tuple(rng.uniform(LO, HI) for _ in range(COUNT))
        eligibility = tuple(rng.uniform(-3.0, 3.0) for _ in range(COUNT))
        delta = rng.uniform(-2.0, 2.0)
        new_weights, clipped = plasticity.apply_stdp(weights, eligibility, delta)
        assert clipped >= -1e-9
        for value in new_weights:
            assert LO <= value <= HI
        for post, indices in by_post.items():
            assert _fixed_l1(post) + sum(new_weights[i] for i in indices) <= 1.2 + 1e-9


# --------------------------------------------------------------------------- #
# Baseline update
# --------------------------------------------------------------------------- #


def test_baseline_update_is_bounded_exponential_mean() -> None:
    assert plasticity.update_baseline(0.0, 1.0) == pytest.approx(0.05)
    assert plasticity.update_baseline(0.5, -1.0) == pytest.approx(0.95 * 0.5 + 0.05 * -1.0)
    # bounded to [-1, 1] under repeated extreme reward
    baseline = 0.0
    for _ in range(1000):
        baseline = plasticity.update_baseline(baseline, 1.0)
    assert -1.0 <= baseline <= 1.0


# --------------------------------------------------------------------------- #
# Settlement convenience: gate drives whether credit applies
# --------------------------------------------------------------------------- #


def test_settle_applies_credit_only_when_gated() -> None:
    weights = tuple(W0 for _ in range(COUNT))
    eligibility = tuple(1.0 for _ in range(COUNT))
    gated, _ = plasticity.settle_stdp(weights, eligibility, reward=1.0, baseline_before=0.0, credit_gate=True)
    ungated, _ = plasticity.settle_stdp(weights, eligibility, reward=1.0, baseline_before=0.0, credit_gate=False)
    assert gated[0] == pytest.approx(W0 + 0.002 * 1.0 * 1.0)  # reward-baseline = 1.0
    assert ungated[0] == pytest.approx(W0)  # delta 0 and W==W0 -> no homeostatic move
