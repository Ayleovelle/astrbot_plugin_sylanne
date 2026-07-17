"""RED/GREEN tests for Task 9 delayed-credit settlement (design 8.3 / 11.2).

Settlement uses only the frozen predictive belief, likelihood, and preference
density a turn stored; it computes the exact diagonal posterior, the bounded
preference reward, the per-action baseline, and the actual-action-only EKF
transition update.  (formula v2 deleted the SNN and its reward-gated STDP delta.)
Every numeric value here is recomputed independently from the frozen formula-v1
constants.
"""

from __future__ import annotations

from math import isclose, log, pi, tanh

from sylanne_alpha.v3core import formula_v1 as formula
from sylanne_alpha.v3core.contracts import Action, SessionRef, TurnSequence
from sylanne_alpha.v3core.features import decision_state
from sylanne_alpha.v3core.inference import initial_action_beliefs
from sylanne_alpha.v3core.learning import (
    SettlementResult,
    ekf_transition_update,
    freeze_actual_prediction,
    posterior_dim,
    predictive_preference_terms,
    preference_expected_log_term,
    settle_reward,
    settle_with,
)
from sylanne_alpha.v3core.learning.outcomes import settle_with as _settle_with
from sylanne_alpha.v3core.observation.models import OutcomeFrame
from sylanne_alpha.v3core.state.models import (
    PendingOutcome,
    V3State,
)

AXIS_DIM = formula.AXIS_DIM
FULL_OUTCOME_MASK = (1 << AXIS_DIM) - 1
_V = formula.ACTION_INITIAL_V
_R = formula.ACTION_INITIAL_R
REV = formula.OUTCOME_PROJECTOR_REVISION


def _session() -> SessionRef:
    return SessionRef(key_id="k", session_digest=b"s" * 32, session_generation=1)


def _outcome(y: tuple, mask: int = FULL_OUTCOME_MASK) -> OutcomeFrame:
    return OutcomeFrame(y=y, valid_mask=mask, projector_revision=REV)


# --------------------------------------------------------------------------- #
# Posterior and preference density
# --------------------------------------------------------------------------- #


def test_posterior_dim_matches_exact_formula() -> None:
    mean, var = posterior_dim(0.3, _V, -0.4, _R)
    expected_var = 1.0 / (1.0 / _V + 1.0 / _R)
    expected_mean = expected_var * (0.3 / _V + -0.4 / _R)
    assert isclose(var, expected_var, abs_tol=1e-15)
    assert isclose(mean, expected_mean, abs_tol=1e-15)


def test_preference_expected_log_term_formula() -> None:
    term = preference_expected_log_term(0.2, 0.1, 0.6, 0.5)
    expected = -0.5 * (log(2 * pi * 0.5) + ((0.2 - 0.6) ** 2 + 0.1) / 0.5)
    assert isclose(term, expected, abs_tol=1e-15)


def test_freeze_before_terms_are_predictive_preference_terms() -> None:
    s = decision_state(tuple(0.1 for _ in range(24)))
    frozen = freeze_actual_prediction(initial_action_beliefs(), s, Action.SPEAK)
    expected = predictive_preference_terms(
        frozen["predictive_mu_actual"], frozen["predictive_v_actual"], frozen["c"], frozen["v_c"]
    )
    assert frozen["preference_log_terms_before"] == expected


# --------------------------------------------------------------------------- #
# Reward branches (design 8.3)
# --------------------------------------------------------------------------- #


def _pending(actual: Action, s: tuple, shadow: Action | None = None) -> PendingOutcome:
    frozen = freeze_actual_prediction(initial_action_beliefs(), s, actual)
    return PendingOutcome(
        origin_turn_id="t",
        sequence=TurnSequence(1, 1),
        action=shadow if shadow is not None else actual,
        projected_actual_action=actual,
        c=frozen["c"],
        v_c=frozen["v_c"],
        reward_scale=formula.ACTION_REWARD_SCALE,
        preference_log_terms_before=frozen["preference_log_terms_before"],
        predictive_mu_actual=frozen["predictive_mu_actual"],
        predictive_v_actual=frozen["predictive_v_actual"],
        likelihood_r_actual=frozen["likelihood_r_actual"],
    )


def _expected_r_preference(pending: PendingOutcome, outcome: OutcomeFrame) -> float:
    diffs = []
    for i in range(AXIS_DIM):
        if not outcome.is_valid(i):
            continue
        mean, var = posterior_dim(
            pending.predictive_mu_actual[i], pending.predictive_v_actual[i], outcome.y[i], pending.likelihood_r_actual[i]
        )
        post = preference_expected_log_term(mean, var, pending.c[i], pending.v_c[i])
        diffs.append(post - pending.preference_log_terms_before[i])
    value = (sum(diffs) / len(diffs)) / pending.reward_scale
    return max(-1.0, min(1.0, value))


def test_reward_censored_when_no_valid_outcome_dim() -> None:
    s = decision_state(tuple(0.1 for _ in range(24)))
    pending = _pending(Action.SPEAK, s)
    censored, r_pref, reward = settle_reward(pending, _outcome(tuple(0.0 for _ in range(8)), mask=0), None)
    assert censored is True and r_pref == 0.0 and reward == 0.0


def test_reward_uses_preference_only_when_quality_invalid() -> None:
    s = decision_state(tuple(0.2 for _ in range(24)))
    pending = _pending(Action.SPEAK, s)
    outcome = _outcome(tuple(0.3 for _ in range(8)))
    censored, r_pref, reward = settle_reward(pending, outcome, None)
    assert censored is False
    assert isclose(r_pref, _expected_r_preference(pending, outcome), abs_tol=1e-12)
    assert reward == r_pref


def test_reward_blends_quality_and_is_bounded() -> None:
    s = decision_state(tuple(0.2 for _ in range(24)))
    pending = _pending(Action.SPEAK, s)
    outcome = _outcome(tuple(0.3 for _ in range(8)))
    _c, r_pref, reward = settle_reward(pending, outcome, 0.9)
    expected = max(-1.0, min(1.0, 0.70 * r_pref + 0.30 * (2 * 0.9 - 1.0)))
    assert isclose(reward, expected, abs_tol=1e-12)
    assert -1.0 <= reward <= 1.0
    # Out-of-range / non-float quality is invalid and ignored.
    _c2, _r2, reward_invalid = settle_reward(pending, outcome, 1.5)
    assert reward_invalid == r_pref


# --------------------------------------------------------------------------- #
# EKF transition update (design 11.2)
# --------------------------------------------------------------------------- #


def test_ekf_box_projection_bounds_and_count() -> None:
    g = tuple(1.19 for _ in range(8))
    b = tuple(0.49 for _ in range(8))
    sigma = tuple(0.9 for _ in range(8))
    s = tuple(1.0 for _ in range(8))
    # Extreme positive error drives g and b up; the box must clamp them.
    outcome = _outcome(tuple(1.0 for _ in range(8)))
    g2, b2, sg2, sb2, count2 = ekf_transition_update(g, b, sigma, sigma, 0, s, outcome)
    for value in g2:
        assert formula.ACTION_G_BOUNDS[0] <= value <= formula.ACTION_G_BOUNDS[1]
    for value in b2:
        assert formula.ACTION_B_BOUNDS[0] <= value <= formula.ACTION_B_BOUNDS[1]
    for value in sg2 + sb2:
        assert formula.ACTION_SIGMA_BOUNDS[0] <= value <= formula.ACTION_SIGMA_BOUNDS[1]
    assert count2 == 1


def test_ekf_only_updates_valid_dimensions() -> None:
    g = tuple(0.85 for _ in range(8))
    b = tuple(0.0 for _ in range(8))
    sigma = tuple(0.1 for _ in range(8))
    s = tuple(0.5 for _ in range(8))
    outcome = _outcome(tuple(0.9 for _ in range(8)), mask=0b00000001)  # only axis 0 valid
    g2, b2, sg2, sb2, count2 = ekf_transition_update(g, b, sigma, sigma, 5, s, outcome)
    assert g2[0] != g[0]  # axis 0 updated
    for i in range(1, 8):
        assert g2[i] == g[i] and b2[i] == b[i] and sg2[i] == sigma[i]
    assert count2 == 6


def test_ekf_no_update_leaves_count_unchanged() -> None:
    g = tuple(0.85 for _ in range(8))
    b = tuple(0.0 for _ in range(8))
    sigma = tuple(0.1 for _ in range(8))
    _g, _b, _sg, _sb, count = ekf_transition_update(g, b, sigma, sigma, 3, tuple(0.0 for _ in range(8)), _outcome(tuple(0.0 for _ in range(8)), mask=0))
    assert count == 3


def test_transition_variance_is_immutable_v1_prior() -> None:
    """Design 11.2 formula-v1: ``V_a`` is an immutable prior, never learned online.

    Guards the code/design reconciliation for the reported EKF-variance defect.
    The actual-action EKF returns only ``(g, b, sigma_g, sigma_b, count)`` -- no
    learned variance slot -- and the predictive transition variance a fresh turn
    freezes stays exactly ``ACTION_INITIAL_V`` no matter how many outcomes settle.
    A reintroduced online-``V`` learner (the removed ``eta``/``V_ai'`` scaffolding)
    would either grow the EKF return arity or drift ``predictive_v_actual`` away
    from the prior, and this test would catch it.
    """
    from sylanne_alpha.v3core.inference import predictive_variance

    prior = tuple(_V for _ in range(AXIS_DIM))
    # The predictive variance is exactly the frozen formula-v1 prior.
    assert predictive_variance() == prior
    assert all(value == formula.ACTION_INITIAL_V for value in predictive_variance())

    # A large-innovation EKF step still returns a five-tuple with no V_a element.
    g = tuple(0.85 for _ in range(8))
    b = tuple(0.0 for _ in range(8))
    sigma = tuple(0.1 for _ in range(8))
    s = tuple(0.5 for _ in range(8))
    updated = ekf_transition_update(g, b, sigma, sigma, 0, s, _outcome(tuple(1.0 for _ in range(8))))
    assert len(updated) == 5  # (g, b, sigma_g, sigma_b, count) -- variance is not learned

    # Repeated settlements never adapt the transition variance away from the prior:
    # the prediction a later turn would freeze still carries the immutable V_a.
    st = decision_state(tuple(0.1 for _ in range(24)))
    beliefs = initial_action_beliefs()
    for _ in range(50):
        state = _state_with_pending(
            _pending(Action.SPEAK, st, shadow=Action.SPEAK),
        )
        result = settle_with(state, _outcome(tuple(0.9 for _ in range(8))))
        assert result.censored is False
        beliefs = result.new_action_beliefs
        frozen = freeze_actual_prediction(beliefs, st, Action.SPEAK)
        assert frozen["predictive_v_actual"] == prior
    assert predictive_variance() == prior


# --------------------------------------------------------------------------- #
# Composed settlement
# --------------------------------------------------------------------------- #


def _state_with_pending(pending: PendingOutcome) -> V3State:
    return V3State(
        session_ref=_session(),
        state_generation_id="gen",
        latent_axes=tuple(0.1 for _ in range(24)),
        action_beliefs=initial_action_beliefs(),
        pending_outcome=pending,
    )


def test_settlement_learns_actual_action_only() -> None:
    s = decision_state(tuple(0.1 for _ in range(24)))
    pending = _pending(Action.SPEAK, s, shadow=Action.HOLD)
    result = settle_with(_state_with_pending(pending), _outcome(tuple(0.3 for _ in range(8))))
    assert isinstance(result, SettlementResult)
    assert result.censored is False
    base = initial_action_beliefs()
    speak_index = 0
    hold_index = 1
    # Only the actual action (SPEAK, row 0) changed; HOLD row unchanged.
    assert result.new_action_beliefs.theta[speak_index] != base.theta[speak_index]
    assert result.new_action_beliefs.theta[hold_index] == base.theta[hold_index]
    assert result.new_action_beliefs.counts[speak_index] == 1


def test_settlement_updates_the_per_action_reward_baseline() -> None:
    s = decision_state(tuple(0.1 for _ in range(24)))
    pending = _pending(Action.HOLD, s, shadow=Action.HOLD)
    result = settle_with(_state_with_pending(pending), _outcome(tuple(0.9 for _ in range(8))))
    assert result.censored is False
    # Baseline moved from 0 toward the reward (per-action reward EMA survives).
    assert isclose(result.baseline_after, 0.95 * 0.0 + 0.05 * result.reward, abs_tol=1e-12)


def test_settlement_censored_without_valid_outcome() -> None:
    s = decision_state(tuple(0.1 for _ in range(24)))
    pending = _pending(Action.HOLD, s, shadow=Action.HOLD)
    result = settle_with(_state_with_pending(pending), _outcome(tuple(0.0 for _ in range(8)), mask=0))
    assert result.censored is True
    # No belief change on a censored settlement.
    assert result.new_action_beliefs.theta == initial_action_beliefs().theta


def test_public_settle_with_alias_is_same() -> None:
    assert settle_with is _settle_with
