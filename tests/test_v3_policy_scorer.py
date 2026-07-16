"""RED/GREEN tests for Task 9 finite-action active inference (design section 11).

``PolicyScorerV1`` scores only legal actions, uses the closed-form diagonal KL
risk, the ambiguity term, and the epistemic information gain (denominator
``V+R``, each sum normalized by the axis count), adds the workspace log-evidence
and the bounded autonomous refractory penalty, and selects with the fixed safety
tie order.  Every numeric value here is recomputed independently from the frozen
formula-v1 constants.
"""

from __future__ import annotations

from math import e, exp, isclose, log, pi, tanh

from sylanne_alpha.v3core import formula_v1 as formula
from sylanne_alpha.v3core.contracts import Action, SessionRef, TurnContextClass
from sylanne_alpha.v3core.features import decision_state
from sylanne_alpha.v3core.inference import (
    PolicyScorerResult,
    PolicyScorerV1,
    efe_ambiguity,
    generative_mu,
    information_gain,
    initial_action_beliefs,
    kl_risk,
    preferences,
    score_policy,
)
from sylanne_alpha.v3core.state.models import V3State
from sylanne_alpha.v3core.state.transition import (
    advance_autonomous_refractory,
    autonomous_refractory_penalty,
    rho_decay,
)
from sylanne_alpha.v3core.workspace import run_workspace
from sylanne_alpha.v3core.observation.models import ObservationFrame

AXIS_DIM = formula.AXIS_DIM
FULL_MASK = (1 << formula.OBSERVATION_DIM) - 1
_V = formula.ACTION_INITIAL_V
_R = formula.ACTION_INITIAL_R
_SIG = formula.ACTION_INITIAL_COVARIANCE[0]
_ACTION_BIAS = {Action[name]: values for name, values in formula.ACTION_BIAS}


def _session() -> SessionRef:
    return SessionRef(key_id="k", session_digest=b"s" * 32, session_generation=1)


def _state(latent: tuple, rho_hold: float = 0.0, rho_reach: float = 0.0) -> V3State:
    return V3State(
        session_ref=_session(),
        state_generation_id="gen",
        latent_axes=latent,
        rho_hold=rho_hold,
        rho_reach=rho_reach,
    )


def _frame() -> ObservationFrame:
    return ObservationFrame(values=tuple(0.5 for _ in range(36)), valid_mask=FULL_MASK)


def _no_broadcast():
    class _B:
        log_evidence = ()

    return _B()


def _expected_efe(action: Action, s: tuple) -> tuple:
    g = tuple(formula.ACTION_INITIAL_G for _ in range(AXIS_DIM))
    b = _ACTION_BIAS[action]
    mu = tuple(tanh(g[i] * s[i] + b[i]) for i in range(AXIS_DIM))
    c, v_c = preferences(s)
    risk = 0.5 * sum(
        log(v_c[i] / _V) + (_V + (mu[i] - c[i]) ** 2) / v_c[i] - 1.0 for i in range(AXIS_DIM)
    ) / AXIS_DIM
    ambiguity = 0.5 * sum(log(2 * pi * e * _R) for _ in range(AXIS_DIM)) / AXIS_DIM
    info = 0.5 * sum(
        log(1.0 + ((1 - mu[i] ** 2) ** 2) * (s[i] ** 2 * _SIG + _SIG) / (_V + _R)) for i in range(AXIS_DIM)
    ) / AXIS_DIM
    return mu, risk, ambiguity, info, risk + ambiguity - info


# --------------------------------------------------------------------------- #
# Context / legality
# --------------------------------------------------------------------------- #


def test_only_legal_actions_are_scored() -> None:
    latent = tuple(0.1 for _ in range(24))
    for context, expected in (
        (TurnContextClass.ADDRESSED, {Action.SPEAK, Action.CLARIFY, Action.HOLD}),
        (TurnContextClass.AMBIENT, {Action.HOLD, Action.SPEAK}),
        (TurnContextClass.PROACTIVE, {Action.HOLD, Action.REACH}),
        (TurnContextClass.IDLE, {Action.HOLD}),
    ):
        result = score_policy(_state(latent), _no_broadcast(), context)
        assert {c.action for c in result.candidates} == expected
        assert isclose(sum(c.posterior for c in result.candidates), 1.0, abs_tol=1e-9)


# --------------------------------------------------------------------------- #
# EFE closed forms
# --------------------------------------------------------------------------- #


def test_efe_terms_match_closed_form() -> None:
    latent = tuple(0.05 * (i - 12) for i in range(24))
    s = decision_state(latent)
    result = score_policy(_state(latent), _no_broadcast(), TurnContextClass.ADDRESSED)
    for candidate in result.candidates:
        mu, risk, ambiguity, info, efe = _expected_efe(candidate.action, s)
        assert candidate.mu == mu
        assert isclose(candidate.risk, risk, abs_tol=1e-12)
        assert isclose(candidate.ambiguity, ambiguity, abs_tol=1e-12)
        assert isclose(candidate.information_gain, info, abs_tol=1e-12)
        assert isclose(candidate.expected_free_energy, efe, abs_tol=1e-12)


def test_component_helpers_normalize_by_dimension() -> None:
    s = decision_state(tuple(0.2 for _ in range(24)))
    c, v_c = preferences(s)
    mu = generative_mu(tuple(0.85 for _ in range(8)), _ACTION_BIAS[Action.SPEAK], s)
    v = tuple(_V for _ in range(8))
    r = tuple(_R for _ in range(8))
    manual_risk = 0.5 * sum(
        log(v_c[i] / v[i]) + (v[i] + (mu[i] - c[i]) ** 2) / v_c[i] - 1.0 for i in range(8)
    ) / 8
    assert isclose(kl_risk(mu, v, c, v_c), manual_risk, abs_tol=1e-12)
    assert isclose(efe_ambiguity(r), 0.5 * log(2 * pi * e * _R), abs_tol=1e-12)


def test_logit_includes_prior_evidence_and_refractory() -> None:
    latent = tuple(0.1 for _ in range(24))
    s = decision_state(latent)
    frame = _frame()
    broadcast = run_workspace(s, frame, None, TurnContextClass.PROACTIVE, tuple(0.0 for _ in range(8)))
    state = _state(latent, rho_hold=0.5, rho_reach=0.0)
    result = score_policy(state, broadcast, TurnContextClass.PROACTIVE)
    evidence = dict(broadcast.log_evidence)
    priors = formula.CONTEXT_ACTION_PRIORS["PROACTIVE"]
    for candidate in result.candidates:
        _mu, _risk, _amb, _info, efe = _expected_efe(candidate.action, s)
        penalty = autonomous_refractory_penalty(TurnContextClass.PROACTIVE, candidate.action, 0.5, 0.0)
        expected_logit = (
            log(priors[candidate.action.value])
            + max(-2.0, min(2.0, evidence.get(candidate.action.value, 0.0)))
            - penalty
            - efe
        )
        assert isclose(candidate.logit, expected_logit, abs_tol=1e-12)
    # HOLD is penalized in PROACTIVE with rho_hold>0; the penalty equals 2*0.8*0.5.
    assert isclose(
        autonomous_refractory_penalty(TurnContextClass.PROACTIVE, Action.HOLD, 0.5, 0.0), 0.8, abs_tol=1e-12
    )


def test_posterior_is_legal_only_softmax() -> None:
    latent = tuple(0.1 for _ in range(24))
    result = score_policy(_state(latent), _no_broadcast(), TurnContextClass.AMBIENT)
    logits = [c.logit for c in result.candidates]
    peak = max(logits)
    exps = [exp(v - peak) for v in logits]
    total = sum(exps)
    for candidate, raw in zip(result.candidates, exps):
        assert isclose(candidate.posterior, raw / total, abs_tol=1e-12)


def test_confidence_is_top_two_gap_and_ties_use_safety_order() -> None:
    # A perfectly symmetric AMBIENT state can tie HOLD and SPEAK; safety order
    # prefers HOLD.  Build a state where posteriors are (near) equal.
    latent = tuple(0.0 for _ in range(24))
    result = score_policy(_state(latent), _no_broadcast(), TurnContextClass.AMBIENT)
    posts = sorted((c.posterior for c in result.candidates), reverse=True)
    assert isclose(result.confidence, posts[0] - posts[1], abs_tol=1e-12)
    assert 0.0 <= result.confidence <= 1.0
    assert isinstance(result, PolicyScorerResult)


# --------------------------------------------------------------------------- #
# Autonomous refractory (rho) transition
# --------------------------------------------------------------------------- #


def test_rho_initialization_decay_penalty_increment_bounds() -> None:
    assert formula.RHO_HOLD_INITIAL == 0.0 and formula.RHO_REACH_INITIAL == 0.0
    assert isclose(rho_decay(0.5), 0.4, abs_tol=1e-12)
    # Penalty only for HOLD/REACH in PROACTIVE/IDLE.
    assert autonomous_refractory_penalty(TurnContextClass.ADDRESSED, Action.HOLD, 1.0, 1.0) == 0.0
    assert autonomous_refractory_penalty(TurnContextClass.PROACTIVE, Action.SPEAK, 1.0, 1.0) == 0.0
    assert isclose(
        autonomous_refractory_penalty(TurnContextClass.IDLE, Action.HOLD, 1.0, 0.0), 1.6, abs_tol=1e-12
    )
    # Post-selection increment only in penalty contexts for the selected action.
    hold, reach = advance_autonomous_refractory(TurnContextClass.PROACTIVE, Action.HOLD, 0.0, 0.0)
    assert isclose(hold, 0.35, abs_tol=1e-12) and reach == 0.0
    hold, reach = advance_autonomous_refractory(TurnContextClass.ADDRESSED, Action.HOLD, 1.0, 1.0)
    assert isclose(hold, 0.8, abs_tol=1e-12) and isclose(reach, 0.8, abs_tol=1e-12)
    # Bounds: repeated PROACTIVE HOLD saturates but never exceeds 1.
    rho_h, rho_r = 1.0, 1.0
    for _ in range(50):
        rho_h, rho_r = advance_autonomous_refractory(TurnContextClass.PROACTIVE, Action.HOLD, rho_h, rho_r)
    assert 0.0 <= rho_h <= 1.0 and 0.0 <= rho_r <= 1.0


def test_scorer_class_matches_function() -> None:
    latent = tuple(0.1 for _ in range(24))
    a = PolicyScorerV1().score(_state(latent), _no_broadcast(), TurnContextClass.ADDRESSED)
    b = score_policy(_state(latent), _no_broadcast(), TurnContextClass.ADDRESSED)
    assert a.selected_action == b.selected_action
    assert [c.logit for c in a.candidates] == [c.logit for c in b.candidates]
