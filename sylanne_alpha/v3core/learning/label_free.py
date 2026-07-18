"""formula v2 label-free settlement: the two learners L1/L2 (spec §2/§3).

At ``t+1`` the immediately consecutive accepted turn settles turn ``t``'s pending
outcome twice, along two DISJOINT paths (spec §2.3 / §4.1):

* path A -- the existing label-gated :func:`settle_with` -- learns the per-action
  transition model, and requires an actual action label; and
* path B -- :func:`settle_label_free`, HERE -- learns the label-FREE reaction
  channel, and never sees which action was chosen.

This module is path B.  It is label-free: :func:`settle_label_free` is not given the
pending outcome and reads only ``pre_state.latent_axes`` and ``pre_state.label_free``
-- both action-independent -- so it never reaches ``pending.action`` /
``projected_actual_action`` / any shadow action.  The pre-state it receives DOES also
carry action-derived scalars (``rho_hold`` / ``rho_reach`` / the style ring), so the
guarantee is not purely a matter of the type signature; the §4.1 guarantee-2
property test pins output invariance to every one of those fields, which is what
makes the action truly invisible to this path.

Three things learn from the ``t+1`` reaction, each with its own gate:

* L1 -- ``PreferenceOffsetLearnerV1`` (spec §3.2): a bounded ``[-0.30, 0.30]``
  residual on the preference mean.  Updated only when the reaction is *valid*, as a
  convex combination toward the reaction-weighted ``(y' - base_c)`` target; a
  negative reaction decays the offset back toward the v1 prior anchor (target 0),
  never reversing it.  Convex combination + a learning rate ``< 1`` is contracting
  by construction, so the offset never diverges and never leaves its box.
* L2 -- ``MarginalOutcomePredictorV1`` (spec §3.3): an action-UNCONDITIONED
  diagonal-EKF world-model head that reuses :func:`ekf_transition_update` verbatim
  (its noise ``MARGINAL_V``/``MARGINAL_R`` equal ``ACTION_INITIAL_V``/``_R``, so the
  shared core is byte-identical).  Updated on any settled turn with >=1 valid
  outcome axis; it is DELIBERATELY not wired into the policy (learn but do not use).
* the user length baseline (spec §3.4): an EMA over ``u'[18]`` gated on an inbound
  context, a valid length bit, and ``same_sender != False`` -- a behavioural
  statistic, not a learner, so it is not gated on reaction validity.

The dynamics matrices ``P``/``W_*``/``U_*`` are never touched (they are protected by
the §9 Jacobian contraction proof).  Pure stdlib float math over immutable tuples:
no NumPy, no I/O, no clocks, no Action.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from ..canonical import assert_exact_type
from ..contracts import ReactionFacts, TurnContextClass
from ..features import decision_state
from ..formula_v1 import (
    AXIS_DIM,
    LEN_BASELINE_ETA,
    LEN_BASELINE_INIT,
    LF_CENSOR_REASON_NOT_ELIGIBLE,
    LF_REACTION_CONTEXTS,
    MARGINAL_INITIAL_B,
    MARGINAL_INITIAL_G,
    MARGINAL_SIGMA_INIT,
    PREF_ETA,
    PREF_OFFSET_BOUNDS,
)
from ..inference.policy_scorer import base_preference_c, generative_mu
from ..observation.models import ObservationFrame, OutcomeFrame
from ..state.models import (
    LABEL_FREE_MARGINAL_DIM,
    REACTION_COUNT_CAP,
    LabelFreeState,
    V3State,
)
from .outcomes import ekf_transition_update
from .reaction import reaction_signal

# The one channel L2/len read from ``u'`` beyond the reaction signal's own four.
_LENGTH_CHANNEL = 18
# Inbound contexts admit a reaction AND accumulate the length baseline (spec §3.4).
_REACTION_CONTEXTS = frozenset(TurnContextClass(name) for name in LF_REACTION_CONTEXTS)
_PREF_LO, _PREF_HI = PREF_OFFSET_BOUNDS


def _clip(value: float, low: float, high: float) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return value


def prior_label_free() -> LabelFreeState:
    """The all-prior :class:`LabelFreeState` a ``None`` ``label_free`` resolves to.

    ``pref_offset`` is zero (the v1 preference), the marginal head is the frozen
    ``MARGINAL_*`` prior (``g``/``b`` interleaved exactly like an ``ActionBeliefs``
    row), the length baseline is ``LEN_BASELINE_INIT``, and both counts are zero.
    ``None`` and this value are semantically identical -- a zero offset scores
    identically to formula v1 (see :func:`preferences`; equal under ``==``, modulo an
    IEEE signed zero on a state axis that is unreachable through the real dynamics) --
    so materializing it changes no decision.
    """

    return LabelFreeState(
        pref_offset=tuple(0.0 for _ in range(AXIS_DIM)),
        marginal_theta=tuple(
            MARGINAL_INITIAL_G if index % 2 == 0 else MARGINAL_INITIAL_B
            for index in range(LABEL_FREE_MARGINAL_DIM)
        ),
        marginal_sigma=tuple(
            MARGINAL_SIGMA_INIT[0] if index % 2 == 0 else MARGINAL_SIGMA_INIT[1]
            for index in range(LABEL_FREE_MARGINAL_DIM)
        ),
        marginal_count=0,
        len_baseline=LEN_BASELINE_INIT,
        reaction_count=0,
    )


def _deinterleave(theta: tuple) -> tuple:
    """Split an interleaved ``[g0,b0,g1,b1,...]`` 16-vector into ``(g[8], b[8])``."""

    return (
        tuple(theta[2 * axis] for axis in range(AXIS_DIM)),
        tuple(theta[2 * axis + 1] for axis in range(AXIS_DIM)),
    )


def _interleave(g: tuple, b: tuple) -> tuple:
    """Interleave ``g[8]``/``b[8]`` back into the packed ``[g0,b0,...]`` 16-vector."""

    row: list[float] = []
    for axis in range(AXIS_DIM):
        row.append(g[axis])
        row.append(b[axis])
    return tuple(row)


@dataclass(frozen=True, slots=True)
class LabelFreeSettlement:
    """Bounded result of one path-B settlement (spec §2.3).

    Carries the reaction verdict, the ``t+1`` marginal prediction BEFORE its update
    (for trace/eval), and the advanced :class:`LabelFreeState`.  ``new_label_free``
    is the state the caller commits atomically alongside path A's ``action_beliefs``;
    the two write disjoint fields, so a same-turn double settlement is one commit.
    """

    reaction_valid: bool
    reason: str
    r_react: float
    marginal_mu: tuple
    new_label_free: LabelFreeState

    def __post_init__(self) -> None:
        assert_exact_type(self.reaction_valid, bool, "reaction_valid")
        assert_exact_type(self.reason, str, "reason")
        assert_exact_type(self.r_react, float, "r_react")
        if not isfinite(self.r_react):
            raise ValueError("r_react must be finite")
        assert_exact_type(self.marginal_mu, tuple, "marginal_mu")
        if len(self.marginal_mu) != AXIS_DIM:
            raise ValueError("marginal_mu must have exactly AXIS_DIM entries")
        for index, value in enumerate(self.marginal_mu):
            assert_exact_type(value, float, f"marginal_mu[{index}]")
            if not isfinite(value):
                raise ValueError("marginal_mu must be finite")
        assert_exact_type(self.new_label_free, LabelFreeState, "new_label_free")


def _update_pref_offset(
    prior_offset: tuple, r_react: float, s_dec: tuple, outcome_frame: OutcomeFrame
) -> tuple:
    """L1 (spec §3.2): a bounded convex-combination update of the preference offset.

    For each *valid* outcome axis the target is ``clip(y' - base_c, -0.30, 0.30)``
    when ``r_react >= 0`` and ``0.0`` (decay to the prior anchor) when ``r_react <
    0``; the step is ``off' = (1 - eta)*off + eta*target`` with ``eta = PREF_ETA *
    |r_react| < 1``.  Invalid axes keep their offset.  The result is clamped to the
    *declared* box; because both endpoints already lie in the box the clamp is a
    no-op in exact arithmetic and only catches float rounding on a persisted (grid)
    input -- the offset is provably non-divergent and bounded.
    """

    base_c = base_preference_c(s_dec)
    eta = PREF_ETA * abs(r_react)
    new_offset = list(prior_offset)
    for axis in range(AXIS_DIM):
        if not outcome_frame.is_valid(axis):
            continue
        if r_react >= 0.0:
            target = _clip(outcome_frame.y[axis] - base_c[axis], _PREF_LO, _PREF_HI)
        else:
            target = 0.0
        updated = (1.0 - eta) * new_offset[axis] + eta * target
        new_offset[axis] = _clip(updated, _PREF_LO, _PREF_HI)
    return tuple(new_offset)


def settle_label_free(
    pre_state: object,
    frame: object,
    outcome_frame: object,
    context: object,
    reaction_facts: object,
    eligible: object,
) -> LabelFreeSettlement:
    """Settle turn ``t``'s label-free reaction at ``t+1`` (spec §2.3 / §3).

    The caller (orchestrator path B) has already established that a pending outcome
    exists and is adjacent.  This function is NOT given the pending outcome and reads
    only ``pre_state.latent_axes`` and ``pre_state.label_free`` -- both
    action-independent -- so it cannot observe the chosen action; the §7 property
    test pins that invariance (including against the action-derived refractory/style
    fields the pre-state also happens to carry).

    The three learners have DIFFERENT gates (spec §3.2/§3.3/§3.4), so ``eligible``
    (turn ``t``'s frozen reaction eligibility) gates ONLY the L1 preference credit:

    * L1 offset -- ``eligible AND reaction valid`` (an IDLE-origin turn has no
      interaction to prefer-credit);
    * L2 marginal EKF -- any adjacent turn with >=1 valid outcome axis, regardless of
      eligibility / reaction validity / action; and
    * length baseline -- inbound context + a valid length bit + ``same_sender !=
      False``, also regardless of eligibility.

    ``pre_state.label_free`` (``None`` -> :func:`prior_label_free`) supplies the
    priors; ``frame`` is ``u'`` (the ``t+1`` message), ``outcome_frame`` is ``y' =
    project_outcome(u')`` (the learning target), ``context`` is ``context'``, and
    ``reaction_facts`` freezes ``same_sender`` (``None`` = admitted noise).
    """

    if type(pre_state) is not V3State:
        raise TypeError("pre_state must have exact type V3State")
    if type(frame) is not ObservationFrame:
        raise TypeError("frame must have exact type ObservationFrame")
    if type(outcome_frame) is not OutcomeFrame:
        raise TypeError("outcome_frame must have exact type OutcomeFrame")
    assert_exact_type(context, TurnContextClass, "context")
    assert_exact_type(reaction_facts, (ReactionFacts, type(None)), "reaction_facts")
    assert_exact_type(eligible, bool, "eligible")

    prior = pre_state.label_free if pre_state.label_free is not None else prior_label_free()
    same_sender = reaction_facts.same_sender if reaction_facts is not None else None
    s_dec = decision_state(pre_state.latent_axes)

    # -- L1: preference offset -- eligibility- AND reaction-gated (spec §3.2) --
    # An ineligible origin turn still runs L2 / len below; only the preference credit
    # is withheld, reported as NOT_ELIGIBLE.
    if eligible:
        reaction = reaction_signal(
            frame, context, prior.len_baseline, prior.reaction_count, same_sender
        )
        reaction_valid = reaction.valid
        reason = reaction.reason
        r_react = reaction.r_react
        if reaction.valid:
            new_offset = _update_pref_offset(prior.pref_offset, reaction.r_react, s_dec, outcome_frame)
        else:
            new_offset = prior.pref_offset
    else:
        reaction_valid = False
        reason = LF_CENSOR_REASON_NOT_ELIGIBLE
        r_react = 0.0
        new_offset = prior.pref_offset

    # -- L2: marginal outcome EKF (adjacency + >=1 valid axis; not reaction/action) --
    g_m, b_m = _deinterleave(prior.marginal_theta)
    sigma_g_m, sigma_b_m = _deinterleave(prior.marginal_sigma)
    marginal_mu = generative_mu(g_m, b_m, s_dec)  # the prediction BEFORE the update
    g_m2, b_m2, sigma_g_m2, sigma_b_m2, marginal_count2 = ekf_transition_update(
        g_m, b_m, sigma_g_m, sigma_b_m, prior.marginal_count, s_dec, outcome_frame
    )
    new_marginal_theta = _interleave(g_m2, b_m2)
    new_marginal_sigma = _interleave(sigma_g_m2, sigma_b_m2)

    # -- length baseline (behavioural statistic; not reaction-gated, spec §3.4) --
    new_len_baseline = prior.len_baseline
    new_reaction_count = prior.reaction_count
    if (
        context in _REACTION_CONTEXTS
        and frame.is_valid(_LENGTH_CHANNEL)
        and same_sender is not False
    ):
        new_len_baseline = _clip(
            (1.0 - LEN_BASELINE_ETA) * prior.len_baseline
            + LEN_BASELINE_ETA * frame.values[_LENGTH_CHANNEL],
            0.0,
            1.0,
        )
        new_reaction_count = min(prior.reaction_count + 1, REACTION_COUNT_CAP)

    new_label_free = LabelFreeState(
        pref_offset=new_offset,
        marginal_theta=new_marginal_theta,
        marginal_sigma=new_marginal_sigma,
        marginal_count=marginal_count2,
        len_baseline=new_len_baseline,
        reaction_count=new_reaction_count,
    )
    return LabelFreeSettlement(
        reaction_valid=reaction_valid,
        reason=reason,
        r_react=r_react,
        marginal_mu=marginal_mu,
        new_label_free=new_label_free,
    )


__all__ = [
    "LabelFreeSettlement",
    "prior_label_free",
    "settle_label_free",
]
