"""Delayed-credit settlement of one PendingOutcome (design sections 8.3 / 11.2).

At ``t+1`` the immediately consecutive accepted :class:`OutcomeFrame` settles the
turn-``t`` :class:`PendingOutcome` exactly once, using only the frozen predictive
belief, likelihood, preference density, and (optionally) eligibility tensor that
turn ``t`` stored.  For each valid outcome dimension the exact diagonal posterior
gives a preference-log improvement; the mean improvement is the preference
reward, optionally blended with a structured quality score.  The per-action reward
baseline and the actual-action EKF transition update both consume the pre-update
baseline / beliefs and are returned together so the caller commits them atomically
with the rest of the turn.  (formula v2 deleted the reward-gated STDP weight update
that also lived here; the SNN it modulated no longer exists.)

If no outcome dimension is valid the credit is censored: no weight, baseline, or
belief change occurs.

Pure stdlib float math over immutable tuples: no NumPy, no I/O, no clocks.

Formula-v1 storage note: :class:`ActionBeliefs` persists ``theta=[g,b]`` and its
diagonal parameter covariance ``Sigma_theta``, the per-action baseline, and the
per-action count.  It has no field for a learned transition variance ``V_a`` or a
per-axis count, so in v1 ``V_a`` stays the immutable prior ``ACTION_INITIAL_V``
and the EKF ``eta`` uses the per-action count.  The EKF still computes the theta /
Sigma update that *is* storable; ``V_a`` learning is deferred to a later state
schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, log, pi, tanh

from ..contracts import Action
from ..formula_v1 import (
    ACTION_B_BOUNDS,
    ACTION_COUNT_CAP,
    ACTION_G_BOUNDS,
    ACTION_Q_THETA,
    ACTION_SIGMA_BOUNDS,
    AXIS_DIM,
    BASELINE_BOUNDS,
    BASELINE_DECAY,
    BASELINE_LEARN,
)
from ..inference.policy_scorer import (
    action_params,
    generative_mu,
    initial_action_beliefs,
    likelihood_variance,
    predictive_variance,
    preferences,
)
from ..observation.models import OutcomeFrame
from ..state.models import ActionBeliefs, PendingOutcome, V3State

_ACTION_ORDER = (Action.SPEAK, Action.HOLD, Action.CLARIFY, Action.REACH)
_ACTION_INDEX = {action: index for index, action in enumerate(_ACTION_ORDER)}
_G_LO, _G_HI = ACTION_G_BOUNDS
_B_LO, _B_HI = ACTION_B_BOUNDS
_SIGMA_LO, _SIGMA_HI = ACTION_SIGMA_BOUNDS
_BASE_LO, _BASE_HI = BASELINE_BOUNDS
_TWO_PI = 2.0 * pi


def update_baseline(baseline: float, reward: float) -> float:
    """Bounded per-action reward EMA ``clip(0.95*baseline + 0.05*reward, -1, 1)``.

    Formerly design 8.3's STDP reward baseline; the SNN is gone but the per-action
    baseline still lives on :class:`ActionBeliefs` and evolves every settlement.
    """

    if type(baseline) is not float or type(reward) is not float:
        raise TypeError("baseline and reward must be floats")
    return _clip(BASELINE_DECAY * baseline + BASELINE_LEARN * reward, _BASE_LO, _BASE_HI)


def _clip(value: float, low: float, high: float) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return value


# --------------------------------------------------------------------------- #
# Posterior and preference density (design 8.3 / 11.2)
# --------------------------------------------------------------------------- #


def posterior_dim(mu: float, v: float, y: float, r: float) -> tuple:
    """Exact per-dimension diagonal-Gaussian posterior ``(mean, var)``."""

    posterior_var = 1.0 / (1.0 / v + 1.0 / r)
    posterior_mean = posterior_var * (mu / v + y / r)
    return posterior_mean, posterior_var


def preference_expected_log_term(mean: float, var: float, c: float, v_c: float) -> float:
    """``E_{x~N(mean,var)}[log N(x;c,V_C)] = -0.5*(log(2*pi*V_C)+((mean-c)^2+var)/V_C)``."""

    return -0.5 * (log(_TWO_PI * v_c) + ((mean - c) ** 2 + var) / v_c)


def predictive_preference_terms(mu: tuple, v: tuple, c: tuple, v_c: tuple) -> tuple:
    """The frozen "before" preference terms using the predictive belief."""

    return tuple(preference_expected_log_term(mu[i], v[i], c[i], v_c[i]) for i in range(AXIS_DIM))


# --------------------------------------------------------------------------- #
# Freeze the actual-action prediction at turn t
# --------------------------------------------------------------------------- #


def freeze_actual_prediction(
    beliefs: object, decision_state: tuple, actual_action: object, offset: tuple | None = None
) -> dict:
    """Compute the arrays a :class:`PendingOutcome` freezes for later settlement.

    ``offset`` is the formula-v2 label-free L1 preference residual in force at turn
    ``t`` (spec §3.2): the frozen ``c``/``V_C`` therefore reflect the preference the
    label path's reward is measured against, keeping "t-turn reward uses t-turn
    preferences" exact.  ``offset is None`` is the v1 behaviour byte-for-byte.
    """

    if type(actual_action) is not Action:
        raise TypeError("actual_action must have exact type Action")
    g, b, _sigma_g, _sigma_b, _count = action_params(beliefs, actual_action)
    mu = generative_mu(g, b, decision_state)
    v = predictive_variance()
    r = likelihood_variance()
    c, v_c = preferences(decision_state, offset)
    before = predictive_preference_terms(mu, v, c, v_c)
    return {
        "predictive_mu_actual": mu,
        "predictive_v_actual": v,
        "likelihood_r_actual": r,
        "c": c,
        "v_c": v_c,
        "preference_log_terms_before": before,
    }


# --------------------------------------------------------------------------- #
# Reward (design 8.3)
# --------------------------------------------------------------------------- #


def _valid_quality(quality_score: object) -> bool:
    return type(quality_score) is float and isfinite(quality_score) and 0.0 <= quality_score <= 1.0


def settle_reward(pending: object, outcome_frame: object, quality_score: object) -> tuple:
    """Return ``(censored, r_preference, reward)`` for one settlement."""

    if type(pending) is not PendingOutcome:
        raise TypeError("pending must have exact type PendingOutcome")
    if type(outcome_frame) is not OutcomeFrame:
        raise TypeError("outcome_frame must have exact type OutcomeFrame")
    if not (
        len(pending.predictive_mu_actual) == AXIS_DIM
        and len(pending.predictive_v_actual) == AXIS_DIM
        and len(pending.likelihood_r_actual) == AXIS_DIM
        and len(pending.c) == AXIS_DIM
        and len(pending.v_c) == AXIS_DIM
        and len(pending.preference_log_terms_before) == AXIS_DIM
    ):
        raise ValueError("pending outcome is missing its frozen settlement arrays")

    diffs: list[float] = []
    for i in range(AXIS_DIM):
        if not outcome_frame.is_valid(i):
            continue
        post_mean, post_var = posterior_dim(
            pending.predictive_mu_actual[i],
            pending.predictive_v_actual[i],
            outcome_frame.y[i],
            pending.likelihood_r_actual[i],
        )
        post_term = preference_expected_log_term(post_mean, post_var, pending.c[i], pending.v_c[i])
        diffs.append(post_term - pending.preference_log_terms_before[i])

    if not diffs:
        return True, 0.0, 0.0

    r_preference = _clip((sum(diffs) / len(diffs)) / pending.reward_scale, -1.0, 1.0)
    if _valid_quality(quality_score):
        reward = _clip(0.70 * r_preference + 0.30 * (2.0 * quality_score - 1.0), -1.0, 1.0)
    else:
        reward = r_preference
    return False, r_preference, reward


# --------------------------------------------------------------------------- #
# Actual-action EKF transition update (design 11.2)
# --------------------------------------------------------------------------- #


def ekf_transition_update(
    g: tuple,
    b: tuple,
    sigma_g: tuple,
    sigma_b: tuple,
    count: int,
    s: tuple,
    outcome_frame: OutcomeFrame,
) -> tuple:
    """Return ``(g', b', sigma_g', sigma_b', count')`` for the actual action.

    Only valid outcome dimensions update; the per-action ``count`` advances once.
    The transition variance ``V_a`` is the immutable prior in v1 and is not
    learned here (no storage field), so it is not returned.
    """

    v = predictive_variance()
    r = likelihood_variance()
    new_g = list(g)
    new_b = list(b)
    new_sigma_g = list(sigma_g)
    new_sigma_b = list(sigma_b)
    any_update = False
    for i in range(AXIS_DIM):
        if not outcome_frame.is_valid(i):
            continue
        any_update = True
        mu = tanh(g[i] * s[i] + b[i])
        jacobian = 1.0 - mu * mu
        j_g = jacobian * s[i]
        j_b = jacobian
        error = outcome_frame.y[i] - mu
        denom = v[i] + r[i] + j_g * j_g * sigma_g[i] + j_b * j_b * sigma_b[i]
        k_g = sigma_g[i] * j_g / denom
        k_b = sigma_b[i] * j_b / denom
        new_g[i] = _clip(g[i] + k_g * error, _G_LO, _G_HI)
        new_b[i] = _clip(b[i] + k_b * error, _B_LO, _B_HI)
        new_sigma_g[i] = _clip((1.0 - k_g * j_g) * sigma_g[i] + ACTION_Q_THETA, _SIGMA_LO, _SIGMA_HI)
        new_sigma_b[i] = _clip((1.0 - k_b * j_b) * sigma_b[i] + ACTION_Q_THETA, _SIGMA_LO, _SIGMA_HI)
    new_count = min(count + 1, ACTION_COUNT_CAP) if any_update else count
    return tuple(new_g), tuple(new_b), tuple(new_sigma_g), tuple(new_sigma_b), new_count


def _rebuild_beliefs(beliefs: ActionBeliefs, action: Action, g, b, sigma_g, sigma_b, baseline, count) -> ActionBeliefs:
    index = _ACTION_INDEX[action]
    theta_row: list[float] = []
    sigma_row: list[float] = []
    for axis in range(AXIS_DIM):
        theta_row.append(g[axis])
        theta_row.append(b[axis])
        sigma_row.append(sigma_g[axis])
        sigma_row.append(sigma_b[axis])
    theta = tuple(tuple(theta_row) if i == index else beliefs.theta[i] for i in range(len(_ACTION_ORDER)))
    sigma = tuple(tuple(sigma_row) if i == index else beliefs.sigma[i] for i in range(len(_ACTION_ORDER)))
    baselines = tuple(baseline if i == index else beliefs.baselines[i] for i in range(len(_ACTION_ORDER)))
    counts = tuple(count if i == index else beliefs.counts[i] for i in range(len(_ACTION_ORDER)))
    return ActionBeliefs(theta=theta, sigma=sigma, baselines=baselines, counts=counts)


# --------------------------------------------------------------------------- #
# Composed settlement
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class SettlementResult:
    """Bounded, atomic settlement outcome for one pending turn.

    formula v2 deleted the reward-gated STDP weight update (the SNN is gone), so
    this no longer carries ``credit_gate``/``stdp_delta``/``clipped_mass``/
    ``new_plastic_weights``.  The per-action reward baseline and the actual-action
    EKF belief update survive.
    """

    censored: bool
    reward: float
    r_preference: float
    baseline_before: float
    baseline_after: float
    new_action_beliefs: ActionBeliefs


def settle_with(pre_state: object, outcome_frame: object, quality_score: object = None) -> SettlementResult:
    """Settle the pending outcome against an explicit accepted next OutcomeFrame."""

    if type(pre_state) is not V3State:
        raise TypeError("pre_state must have exact type V3State")
    if type(outcome_frame) is not OutcomeFrame:
        raise TypeError("outcome_frame must have exact type OutcomeFrame")
    pending = pre_state.pending_outcome
    if type(pending) is not PendingOutcome:
        raise ValueError("pre_state has no pending outcome to settle")

    beliefs = pre_state.action_beliefs or initial_action_beliefs()
    actual = pending.projected_actual_action

    censored, r_preference, reward = settle_reward(pending, outcome_frame, quality_score)
    if censored or actual is None:
        return SettlementResult(
            censored=True,
            reward=0.0,
            r_preference=0.0,
            baseline_before=0.0,
            baseline_after=0.0,
            new_action_beliefs=beliefs,
        )

    action_index = _ACTION_INDEX[actual]
    baseline_before = beliefs.baselines[action_index]
    baseline_after = update_baseline(baseline_before, reward)

    s = _decision_state(pre_state)
    g, b, sigma_g, sigma_b, count = action_params(beliefs, actual)
    g2, b2, sigma_g2, sigma_b2, count2 = ekf_transition_update(
        g, b, sigma_g, sigma_b, count, s, outcome_frame
    )
    new_beliefs = _rebuild_beliefs(beliefs, actual, g2, b2, sigma_g2, sigma_b2, baseline_after, count2)

    return SettlementResult(
        censored=False,
        reward=reward,
        r_preference=r_preference,
        baseline_before=baseline_before,
        baseline_after=baseline_after,
        new_action_beliefs=new_beliefs,
    )


def _decision_state(pre_state: V3State) -> tuple:
    from ..features import decision_state

    return decision_state(pre_state.latent_axes)


__all__ = [
    "SettlementResult",
    "ekf_transition_update",
    "freeze_actual_prediction",
    "posterior_dim",
    "predictive_preference_terms",
    "preference_expected_log_term",
    "settle_reward",
    "settle_with",
    "update_baseline",
]
