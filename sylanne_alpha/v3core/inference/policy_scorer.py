"""Finite-action active inference: ``PolicyScorerV1`` (design section 11).

The scorer reads the eight-dimensional decision state, the per-action
linear-Gaussian beliefs, the workspace log-evidence, the autonomous refractory
state, and the context legal masks/priors, and computes for every legal action
the diagonal-Gaussian risk (KL to preferences), the ambiguity, the epistemic
information gain, the expected free energy, and the softmax policy posterior.
Only legal actions enter the softmax; exact ties use the fixed safety order.

Pure stdlib float math over immutable tuples: no NumPy, no I/O, no clocks, no
callbacks, no randomness.

In formula v1 the transition variance ``V_a`` is the immutable prior
``ACTION_INITIAL_V`` and the likelihood variance ``R_a`` is ``ACTION_INITIAL_R``;
the learned per-action parameter posterior ``Sigma_theta`` (with ``theta=[g,b]``)
is what persists in :class:`ActionBeliefs`.  ``ActionBeliefs`` has no field for a
learned ``V_a``, so ``V_a`` is not online-persisted in v1 (see the module note in
:mod:`sylanne_alpha.v3core.learning.outcomes`).
"""

from __future__ import annotations

from math import e, exp, log, pi, tanh

from ..contracts import Action, TurnContextClass
from ..formula_v1 import (
    ACTION_BIAS,
    ACTION_INITIAL_COVARIANCE,
    ACTION_INITIAL_G,
    ACTION_INITIAL_R,
    ACTION_INITIAL_V,
    AXIS_DIM,
    CONTEXT_ACTION_PRIORS,
    POLICY_GAMMA,
    POLICY_TEMPERATURE,
    POLICY_WORKSPACE_EVIDENCE_BOUNDS,
    PREFERENCE_C_CONSTANT,
    PREFERENCE_C_STATE_AXES,
    PREFERENCE_V_C,
)
from ..features import decision_state
from ..state.models import THETA_PARAMS, ActionBeliefs, V3State
from ..state.transition import autonomous_refractory_penalty
from .models import ActionCandidate, PolicyScorerResult

# ``ActionBeliefs`` rows are indexed in this order (matches the state codec).
_ACTION_ORDER = (Action.SPEAK, Action.HOLD, Action.CLARIFY, Action.REACH)
_ACTION_INDEX = {action: index for index, action in enumerate(_ACTION_ORDER)}
_ACTION_BIAS = {Action[name]: values for name, values in ACTION_BIAS}
_SIGMA_G_INIT, _SIGMA_B_INIT = ACTION_INITIAL_COVARIANCE
_EVIDENCE_LO, _EVIDENCE_HI = POLICY_WORKSPACE_EVIDENCE_BOUNDS
_TWO_PI_E = 2.0 * pi * e
# Fixed safety order for exact posterior ties (design 11.3): HOLD, CLARIFY, SPEAK, REACH.
_TIE_ORDER = (Action.HOLD, Action.CLARIFY, Action.SPEAK, Action.REACH)
_TIE_RANK = {action: rank for rank, action in enumerate(_TIE_ORDER)}


def _clip(value: float, low: float, high: float) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return value


# --------------------------------------------------------------------------- #
# Beliefs
# --------------------------------------------------------------------------- #


def initial_action_beliefs() -> ActionBeliefs:
    """Build the formula-v1 prior beliefs (g=0.85, b=ACTION_BIAS, Sigma=0.10)."""

    theta_rows = []
    sigma_rows = []
    for action in _ACTION_ORDER:
        bias = _ACTION_BIAS[action]
        theta_row: list[float] = []
        sigma_row: list[float] = []
        for axis in range(AXIS_DIM):
            theta_row.append(ACTION_INITIAL_G)
            theta_row.append(bias[axis])
            sigma_row.append(_SIGMA_G_INIT)
            sigma_row.append(_SIGMA_B_INIT)
        theta_rows.append(tuple(theta_row))
        sigma_rows.append(tuple(sigma_row))
    return ActionBeliefs(
        theta=tuple(theta_rows),
        sigma=tuple(sigma_rows),
        baselines=tuple(0.0 for _ in _ACTION_ORDER),
        counts=tuple(0 for _ in _ACTION_ORDER),
    )


def action_params(beliefs: object, action: Action) -> tuple:
    """Return ``(g[8], b[8], sigma_g[8], sigma_b[8], count)`` for one action.

    ``beliefs`` may be ``None`` (uninitialised session), in which case the frozen
    formula-v1 prior is used.
    """

    if type(action) is not Action:
        raise TypeError("action must have exact type Action")
    if beliefs is None:
        bias = _ACTION_BIAS[action]
        g = tuple(ACTION_INITIAL_G for _ in range(AXIS_DIM))
        b = tuple(bias[axis] for axis in range(AXIS_DIM))
        sigma_g = tuple(_SIGMA_G_INIT for _ in range(AXIS_DIM))
        sigma_b = tuple(_SIGMA_B_INIT for _ in range(AXIS_DIM))
        return g, b, sigma_g, sigma_b, 0
    if type(beliefs) is not ActionBeliefs:
        raise TypeError("beliefs must be an ActionBeliefs or None")
    index = _ACTION_INDEX[action]
    theta = beliefs.theta[index]
    sigma = beliefs.sigma[index]
    g = tuple(theta[THETA_PARAMS * axis] for axis in range(AXIS_DIM))
    b = tuple(theta[THETA_PARAMS * axis + 1] for axis in range(AXIS_DIM))
    sigma_g = tuple(sigma[THETA_PARAMS * axis] for axis in range(AXIS_DIM))
    sigma_b = tuple(sigma[THETA_PARAMS * axis + 1] for axis in range(AXIS_DIM))
    return g, b, sigma_g, sigma_b, beliefs.counts[index]


def generative_mu(g: tuple, b: tuple, s: tuple) -> tuple:
    """``mu_ai = tanh(g_ai * s_i + b_ai)`` (design 11.2)."""

    return tuple(tanh(g[i] * s[i] + b[i]) for i in range(AXIS_DIM))


def predictive_variance() -> tuple:
    """The immutable formula-v1 transition variance ``V_a`` (per axis)."""

    return tuple(ACTION_INITIAL_V for _ in range(AXIS_DIM))


def likelihood_variance() -> tuple:
    """The immutable formula-v1 likelihood variance ``R_a`` (per axis)."""

    return tuple(ACTION_INITIAL_R for _ in range(AXIS_DIM))


def base_preference_c(s: tuple) -> tuple:
    """The versioned base preference mean ``base_c(s)`` before any learned residual.

    ``base_c_i(s) = s_i`` on the two state-copying axes (``PREFERENCE_C_STATE_AXES``)
    and ``PREFERENCE_C_CONSTANT_i`` elsewhere (design 11.2 / spec §3.2).  The
    formula-v2 label-free L1 learner adds a bounded residual on top of this; the
    residual's target is measured relative to ``base_c`` so this stays the single
    source of the base mean.
    """

    return tuple(
        s[axis] if axis in PREFERENCE_C_STATE_AXES else PREFERENCE_C_CONSTANT[axis]
        for axis in range(AXIS_DIM)
    )


def preferences(s: tuple, offset: tuple | None = None) -> tuple:
    """Return the preference mean ``c`` and diagonal variance ``V_C`` (design 11.2).

    ``offset`` is the formula-v2 label-free L1 preference residual (spec §3.2):
    ``c_i = clip(base_c_i(s) + offset_i, -1, 1)``.  ``offset is None`` (no
    ``label_free`` state) is the v1 behaviour exactly -- the base mean is returned
    unclipped and byte-identical to formula v1, so a null/zero offset never drifts a
    single bit (the regression anchor).  ``V_C`` is the immutable prior either way.
    """

    base_c = base_preference_c(s)
    if offset is None:
        return base_c, PREFERENCE_V_C
    c = tuple(_clip(base_c[axis] + offset[axis], -1.0, 1.0) for axis in range(AXIS_DIM))
    return c, PREFERENCE_V_C


# --------------------------------------------------------------------------- #
# EFE terms (each sum normalized by its declared dimension count)
# --------------------------------------------------------------------------- #


def kl_risk(mu: tuple, v: tuple, c: tuple, v_c: tuple) -> float:
    """Diagonal-Gaussian ``KL(N(mu,V) || N(c,V_C))`` normalized by ``AXIS_DIM``."""

    total = 0.0
    for i in range(AXIS_DIM):
        total += log(v_c[i] / v[i]) + (v[i] + (mu[i] - c[i]) ** 2) / v_c[i] - 1.0
    return 0.5 * total / AXIS_DIM


def efe_ambiguity(r: tuple) -> float:
    """``0.5 * sum_i log(2*pi*e*R_i)`` normalized by ``AXIS_DIM``."""

    total = sum(log(_TWO_PI_E * r[i]) for i in range(AXIS_DIM))
    return 0.5 * total / AXIS_DIM


def information_gain(mu: tuple, s: tuple, sigma_g: tuple, sigma_b: tuple, v: tuple, r: tuple) -> float:
    """Epistemic gain ``0.5*sum_i log(1 + j^T Sigma j/(V+R))`` normalized by ``AXIS_DIM``.

    ``j_ai = (1-mu_ai^2) * [s_i, 1]`` and ``Sigma_theta_ai = diag(sigma_g, sigma_b)``,
    so ``j^T Sigma j = (1-mu^2)^2 * (s_i^2*sigma_g + sigma_b)``.
    """

    total = 0.0
    for i in range(AXIS_DIM):
        jacobian = 1.0 - mu[i] * mu[i]
        quad = (jacobian * jacobian) * (s[i] * s[i] * sigma_g[i] + sigma_b[i])
        total += log(1.0 + quad / (v[i] + r[i]))
    return 0.5 * total / AXIS_DIM


# --------------------------------------------------------------------------- #
# Policy
# --------------------------------------------------------------------------- #


def _legal_actions(context: TurnContextClass) -> tuple:
    names = CONTEXT_ACTION_PRIORS[context.value]
    legal = frozenset(Action[name] for name in names)
    return tuple(action for action in _ACTION_ORDER if action in legal)


def _softmax(logits: list[float]) -> list[float]:
    scaled = [value / POLICY_TEMPERATURE for value in logits]
    peak = max(scaled)
    exps = [exp(value - peak) for value in scaled]
    total = sum(exps)
    return [value / total for value in exps]


def score_policy(pre_state: object, broadcast: object, context: object) -> PolicyScorerResult:
    """Score every legal action and return the finite-action decision."""

    if type(pre_state) is not V3State:
        raise TypeError("pre_state must have exact type V3State")
    if type(context) is not TurnContextClass:
        raise TypeError("context must have exact type TurnContextClass")

    s = decision_state(pre_state.latent_axes)
    # formula v2: the label-free L1 preference residual (spec §3.2/§4.1) enters EFE
    # risk here.  ``label_free is None`` resolves to offset ``None`` = the v1
    # preference mean exactly, so a session that never settled a reaction scores
    # byte-identically to formula v1.
    label_free = pre_state.label_free
    offset = label_free.pref_offset if label_free is not None else None
    c, v_c = preferences(s, offset)
    v = predictive_variance()
    r = likelihood_variance()
    beliefs = pre_state.action_beliefs
    rho_hold = pre_state.rho_hold
    rho_reach = pre_state.rho_reach

    log_evidence = dict(getattr(broadcast, "log_evidence", ()))
    priors = CONTEXT_ACTION_PRIORS[context.value]
    legal = _legal_actions(context)

    partials = []
    logits: list[float] = []
    for action in legal:
        g, b, sigma_g, sigma_b, _count = action_params(beliefs, action)
        mu = generative_mu(g, b, s)
        risk = kl_risk(mu, v, c, v_c)
        ambiguity = efe_ambiguity(r)
        info_gain = information_gain(mu, s, sigma_g, sigma_b, v, r)
        efe = risk + ambiguity - info_gain
        prior_log = log(priors[action.value])
        workspace_evidence = _clip(
            float(log_evidence.get(action.value, 0.0)), _EVIDENCE_LO, _EVIDENCE_HI
        )
        refractory = autonomous_refractory_penalty(context, action, rho_hold, rho_reach)
        logit = prior_log + workspace_evidence - refractory - POLICY_GAMMA * efe
        logits.append(logit)
        partials.append(
            {
                "action": action,
                "mu": mu,
                "predictive_var": v,
                "prior_log": prior_log,
                "workspace_log_evidence": workspace_evidence,
                "refractory_penalty": refractory,
                "risk": risk,
                "ambiguity": ambiguity,
                "information_gain": info_gain,
                "expected_free_energy": efe,
                "logit": logit,
            }
        )

    posteriors = _softmax(logits)
    candidates = tuple(
        ActionCandidate(posterior=posteriors[index], **partials[index]) for index in range(len(legal))
    )

    # Selection: highest posterior, exact ties by the fixed safety order.
    def _selection_key(candidate: ActionCandidate) -> tuple:
        return (-candidate.posterior, _TIE_RANK[candidate.action])

    ranked = sorted(candidates, key=_selection_key)
    selected = ranked[0].action
    if len(ranked) >= 2:
        confidence = _clip(ranked[0].posterior - ranked[1].posterior, 0.0, 1.0)
    else:
        confidence = 1.0
    return PolicyScorerResult(
        decision_state=s,
        candidates=candidates,
        selected_action=selected,
        confidence=confidence,
    )


class PolicyScorerV1:
    """Named finite-action policy scorer (design section 18 terminology gate).

    The scientific ``ActiveInferencePolicy`` alias is withheld until likelihood
    calibration, Brier/ECE, action-coverage, and EFE ablation gates pass.
    """

    def score(self, pre_state: object, broadcast: object, context: object) -> PolicyScorerResult:
        return score_policy(pre_state, broadcast, context)


__all__ = [
    "PolicyScorerV1",
    "action_params",
    "base_preference_c",
    "efe_ambiguity",
    "generative_mu",
    "information_gain",
    "initial_action_beliefs",
    "kl_risk",
    "likelihood_variance",
    "predictive_variance",
    "preferences",
    "score_policy",
]
