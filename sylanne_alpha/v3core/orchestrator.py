"""Deterministic core turn orchestration (design sections 6 / 14 / 16).

``orchestrate`` wires the six pure named stages
``encoder -> dynamics -> workspace -> inference -> expression -> trace``
into a single deterministic turn over immutable core DTOs.  (formula v2 deleted the
former ``snn`` stage together with the spiking subsystem; the trace still records
neutral spike/summary telemetry fields for schema stability.)  Before the named
stages it settles the previous eligible delayed-credit outcome (design 14.2 step
4); after them it freezes this turn's pending outcome, appends one bounded
``ExperienceRecord`` keyed by the *committed* revision (never the same-turn trace
digest), and produces a :class:`DecisionPlan`, a :class:`StateDelta`, a closed
:class:`EffectBundle`, and a :class:`CoreDecisionTrace`.

Quantize-on-persist (回溯红队 a16 MAJOR DoD): the float64 compute product is
encoded to the lossy float16 persistence bytes, decoded back, and the *decoded*
state is the sole canonical in-memory state advanced next turn — so a crash
reload can never fork the cognitive trajectory.  ``payload_digest`` hashes exactly
those quantized bytes.

Digest dependencies are one-way (payload -> trace -> journal): the trace may embed
``payload_digest`` but never its own or the journal digest.

Pure stdlib ``hashlib`` over immutable tuples: no astrbot/v2core/_engine, no
clocks, no filesystem, no callbacks, no randomness.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace

from .canonical import assert_exact_type, canonical_sha256
from .contracts import Action, CoreInvocation, TurnEnvelope, TurnSequence
from .effects.models import (
    DecisionPlan,
    EffectBundle,
    StateDelta,
    V3MetricEffect,
    V3StateEffect,
    V3TraceEffect,
)
from .expression.policy import ExpressionConstraints, expression_policy, next_style_ring
from .features import decision_state as compute_decision_state
from .formula_v1 import (
    AXIS_DIM,
    COMPUTE_PROFILES,
    EXPERIENCE_CAPACITY,
    FORMULA_DIGEST,
    LF_CENSOR_REASON_NON_ADJACENT,
    LF_ELIGIBLE_ORIGIN_CONTEXTS,
    SNN_NEURONS,
    SNN_SUMMARY_DIM,
)
from .dynamics.multiscale import advance_dynamics
from .inference.policy_scorer import score_policy
from .learning.label_free import settle_label_free
from .learning.outcomes import freeze_actual_prediction, settle_with
from .observation.encoder import encode_observation, project_outcome
from .observation.models import ObservationFacts
from .state.codec import (
    StateCodecError,
    StateSizeError,
    decode_state,
    encode_state,
)
from .state.models import (
    EXPERIENCE_FEATURE_DIM,
    ExperienceRecord,
    PendingOutcome,
    V3State,
)
from .state.transition import advance_autonomous_refractory
from .trace.canonical import (
    TRACE_HARD_CAP_BYTES,
    canonical_trace_bytes,
    compute_journal_digest,
    trace_digest_hex,
)
from .trace.models import TRACE_SCHEMA_VERSION, CoreDecisionTrace
from .workspace.competition import run_workspace


STAGE_ORDER = ("encoder", "dynamics", "workspace", "inference", "expression", "trace")

# Hard state ceiling mirrors the bridge ``limits.MAX_STATE_BYTES``; the pure core
# owns its own copy so it never imports the bridge.
STATE_HARD_CAP_BYTES = 64 * 1024

_ACTION_ORDER = (Action.SPEAK, Action.HOLD, Action.CLARIFY, Action.REACH)
_ACTION_TO_CODE = {action: index for index, action in enumerate(_ACTION_ORDER)}
_ACTION_CODE_NONE = 255
_S16_HI = 32767
_S16_LO = -32768


# --------------------------------------------------------------------------- #
# Result DTO (pure, self-validating, not registered)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class OrchestratorResult:
    """The deterministic artifacts of one orchestrated turn.

    On ``accepted`` the decision/state/effects/trace are all present.  On a
    rejected invocation (trace or state over the hard cap) none of the cognitive
    artifacts survive: only bounded runtime ``telemetry`` records the failure and
    neither state nor trace is committed (design section 16.2).
    """

    accepted: bool
    reject_reason: str
    decision_plan: object
    state_delta: object
    effects: object
    trace: object
    trace_bytes: bytes
    trace_digest: str
    payload_digest: str
    journal_digest: str
    telemetry: tuple

    def __post_init__(self) -> None:
        assert_exact_type(self.accepted, bool, "accepted")
        assert_exact_type(self.reject_reason, str, "reject_reason")
        assert_exact_type(self.trace_bytes, bytes, "trace_bytes")
        assert_exact_type(self.trace_digest, str, "trace_digest")
        assert_exact_type(self.payload_digest, str, "payload_digest")
        assert_exact_type(self.journal_digest, str, "journal_digest")
        assert_exact_type(self.telemetry, tuple, "telemetry")


# --------------------------------------------------------------------------- #
# Small pure helpers
# --------------------------------------------------------------------------- #


def _quantize_s16(value: float) -> int:
    clipped = 1.0 if value > 1.0 else -1.0 if value < -1.0 else value
    q = int(round(clipped * _S16_HI))
    return _S16_HI if q > _S16_HI else _S16_LO if q < _S16_LO else q


def _quantize_u8(value: float) -> int:
    clipped = 1.0 if value > 1.0 else 0.0 if value < 0.0 else value
    q = int(round(clipped * 255.0))
    return 255 if q > 255 else 0 if q < 0 else q


def _action_code(action: object) -> int:
    if action is None:
        return _ACTION_CODE_NONE
    return _ACTION_TO_CODE[action]


def _is_adjacent(previous: TurnSequence, current: TurnSequence) -> bool:
    return (
        previous.writer_epoch == current.writer_epoch
        and current.local_sequence == previous.local_sequence + 1
    )


def _decode_observation(envelope: TurnEnvelope) -> ObservationFacts:
    observation = envelope.observation
    if type(observation) is not tuple or len(observation) != 2:
        raise TypeError("envelope.observation must be (raw_values, previous_action)")
    raw_values, previous_action = observation
    if previous_action is not None and type(previous_action) is not Action:
        raise TypeError("previous_action must be an Action or None")
    return ObservationFacts(
        raw_values=raw_values,
        context=envelope.context,
        previous_action=previous_action,
    )


def _decode_projected(value: object) -> tuple:
    if value is None:
        return None, None
    if type(value) is not tuple or len(value) != 2:
        raise TypeError("projected_actual_outcome must be None or (actual_action, quality_score)")
    actual_action, quality_score = value
    if actual_action is not None and type(actual_action) is not Action:
        raise TypeError("actual_action must be an Action or None")
    if quality_score is not None and type(quality_score) is not float:
        raise TypeError("quality_score must be a float or None")
    return actual_action, quality_score


def _rejected(reason: str, telemetry: tuple) -> OrchestratorResult:
    return OrchestratorResult(
        accepted=False,
        reject_reason=reason,
        decision_plan=None,
        state_delta=None,
        effects=None,
        trace=None,
        trace_bytes=b"",
        trace_digest="",
        payload_digest="",
        journal_digest="",
        telemetry=telemetry,
    )


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


def orchestrate(invocation: object) -> OrchestratorResult:
    """Run one deterministic shadow turn over an immutable :class:`CoreInvocation`."""

    if type(invocation) is not CoreInvocation:
        raise TypeError("orchestrate requires a CoreInvocation")
    envelope = invocation.envelope
    base = invocation.base_state
    if type(base) is not V3State:
        raise TypeError("base_state must have exact type V3State")

    profile = envelope.compute_profile
    context = envelope.context
    expected = COMPUTE_PROFILES.get(profile.profile_id)
    if expected is None or (
        profile.snn_enabled,
        profile.ticks,
        profile.stdp_enabled,
        profile.reuse_last_summary,
    ) != tuple(expected):
        raise ValueError(
            f"compute profile {profile.profile_id!r} is inconsistent with the frozen manifest"
        )
    snn_enabled, ticks, stdp_enabled, reuse_last = expected
    actual_action, quality_score = _decode_projected(invocation.projected_actual_outcome)
    turn_revision = base.revision + 1

    # -- stage: encoder ------------------------------------------------------
    facts = _decode_observation(envelope)
    frame = encode_observation(facts)
    input_digest = canonical_sha256(frame)
    outcome_frame = project_outcome(frame)

    # -- pre-stage: settle the previous eligible delayed outcome (design 14.2/4).
    # Two DISJOINT settlement paths share one adjacency skeleton, one outcome frame,
    # and one atomic commit (spec §2.3): path A learns the per-action label model
    # (unchanged), path B learns the label-free reaction channel and never sees the
    # action.  Non-adjacent (or no pending) censors BOTH exactly like v1.
    settled_beliefs = base.action_beliefs
    settled_label_free = base.label_free
    settle_censored = True
    settle_reward = 0.0
    settle_r_preference = 0.0
    # Label-free trace telemetry (spec §4.3); neutral unless path B runs this turn.
    lf_r_react = 0.0
    lf_reaction_valid = False
    lf_censor_reason = LF_CENSOR_REASON_NON_ADJACENT
    lf_pref_offset_after = (
        base.label_free.pref_offset if base.label_free is not None else tuple(0.0 for _ in range(AXIS_DIM))
    )
    lf_marginal_mu = tuple(0.0 for _ in range(AXIS_DIM))
    pending = base.pending_outcome
    if pending is not None and _is_adjacent(pending.sequence, envelope.sequence):
        # Path A: label-gated settlement (design 8.3 / 11.2), semantics unchanged.
        # Only fires when turn t froze an actual-action prediction (labeled turn).
        if len(pending.predictive_mu_actual) == AXIS_DIM:
            settlement = settle_with(base, outcome_frame, quality_score)
            settled_beliefs = settlement.new_action_beliefs
            settle_censored = settlement.censored
            settle_reward = settlement.reward
            settle_r_preference = settlement.r_preference
        # Path B: label-free settlement (spec §2.3).  Runs on ANY adjacent turn --
        # action UNKNOWN turns settle here (the hole this closes), and L2/len are NOT
        # eligibility-gated (spec §3.3/§3.4).  The frozen t-turn eligibility gates
        # only the L1 preference credit, inside settle_label_free, which reports
        # NOT_ELIGIBLE when it withholds that credit.  Path B writes only label_free.
        lf = settle_label_free(
            base, frame, outcome_frame, context, invocation.reaction_facts, pending.label_free_eligible
        )
        settled_label_free = lf.new_label_free
        lf_r_react = lf.r_react
        lf_reaction_valid = lf.reaction_valid
        lf_censor_reason = lf.reason
        lf_pref_offset_after = lf.new_label_free.pref_offset
        lf_marginal_mu = lf.marginal_mu

    # -- SNN stage DELETED (formula v2) --------------------------------------
    # The reservoir was structurally silent (max membrane ~0.32 vs a 0.65 threshold
    # floor), so it never influenced the drive, and its only *live* consumer -- the
    # snn-novelty proposal -- is gone.  The compute-profile load-shedding flags
    # (snn_enabled/ticks/stdp_enabled/reuse_last) survive on the ComputeProfile but no
    # longer gate any reservoir, so every profile now advances the same continuous
    # trajectory.  ``last_snn_summary`` is permanently ``None`` (nothing produces a
    # summary), so REUSE_LAST_SNN_SUMMARY still degrades deterministically.  The trace
    # keeps neutral spike/summary telemetry fields for schema stability.
    degradation_reason = "NONE"
    if reuse_last and base.last_snn_summary is None:
        degradation_reason = "REUSE_WITHOUT_SUMMARY_FALLBACK"
    spike_counts = tuple(0 for _ in range(SNN_NEURONS))
    first_latencies = tuple(-1 for _ in range(SNN_NEURONS))
    trace_summary = tuple(0.0 for _ in range(SNN_SUMMARY_DIM))

    # -- stage: dynamics -----------------------------------------------------
    advance = advance_dynamics(base, frame, turn_revision)
    next_latent = advance.next_latent_axes
    drive = advance.drive
    dynamics_advanced = advance.advanced
    decision_state = compute_decision_state(next_latent)

    # -- stage: workspace ----------------------------------------------------
    # The 8-source workspace refractory is not part of the frozen v1 state schema,
    # so it starts neutral each turn (deterministic); persistence is a later revision.
    source_refractory = tuple(0.0 for _ in range(8))
    broadcast = run_workspace(decision_state, frame, context, source_refractory)

    # -- stage: inference ----------------------------------------------------
    # The settled label-free offset (path B) rides into scoring exactly like the
    # settled action beliefs (path A): this turn's EFE risk uses the preference the
    # reaction just nudged (spec §3.2).  label_free None keeps v1 scoring byte-exact.
    advanced_state = replace(
        base, latent_axes=next_latent, action_beliefs=settled_beliefs, label_free=settled_label_free
    )
    policy = score_policy(advanced_state, broadcast, context)
    selected = policy.selected_action

    rho_hold_after, rho_reach_after = advance_autonomous_refractory(
        context, selected, base.rho_hold, base.rho_reach
    )

    # -- stage: expression ---------------------------------------------------
    constraints = expression_policy(
        selected, decision_state, frame.values, base.style_ring, frame.valid_mask
    )
    new_style_ring = next_style_ring(base.style_ring, constraints.style_signature)

    # -- freeze this turn's pending outcome for settlement at t+1 ------------
    # Reaction eligibility is decided and frozen NOW, from turn t's own context
    # (spec §2.2): an IDLE turn has no interaction to react to, so t+1 must not
    # retro-decide.  The frozen c/V_C use the offset in force this turn so the label
    # path's reward stays "t-turn reward by t-turn preferences".
    label_free_eligible = context.value in LF_ELIGIBLE_ORIGIN_CONTEXTS
    settled_offset = settled_label_free.pref_offset if settled_label_free is not None else None
    if actual_action is not None:
        frozen = freeze_actual_prediction(
            settled_beliefs, decision_state, actual_action, settled_offset
        )
        new_pending = PendingOutcome(
            origin_turn_id=envelope.turn_id,
            sequence=envelope.sequence,
            action=selected,
            projected_actual_action=actual_action,
            c=frozen["c"],
            v_c=frozen["v_c"],
            reward_scale=1.0,
            preference_log_terms_before=frozen["preference_log_terms_before"],
            predictive_mu_actual=frozen["predictive_mu_actual"],
            predictive_v_actual=frozen["predictive_v_actual"],
            likelihood_r_actual=frozen["likelihood_r_actual"],
            label_free_eligible=label_free_eligible,
        )
    else:
        new_pending = PendingOutcome(
            origin_turn_id=envelope.turn_id,
            sequence=envelope.sequence,
            action=selected,
            projected_actual_action=None,
            label_free_eligible=label_free_eligible,
        )

    # -- append one bounded ExperienceRecord (committed revision key) --------
    reward_components = [0.0] * AXIS_DIM
    if not settle_censored:
        reward_components[0] = settle_reward
        reward_components[1] = settle_r_preference
    workspace_slots = [0.0] * 8
    for proposal, activation_value in zip(broadcast.proposals, broadcast.activation):
        workspace_slots[proposal.source_index] = activation_value
    record = ExperienceRecord(
        observation_digest=bytes.fromhex(input_digest)[:8],
        encoded_features=tuple(_quantize_s16(next_latent[i]) for i in range(EXPERIENCE_FEATURE_DIM)),
        workspace_broadcast=tuple(_quantize_s16(value) for value in workspace_slots),
        shadow_action_code=_action_code(selected),
        actual_action_code=_action_code(actual_action),
        next_observation=tuple(_quantize_u8(value) for value in frame.values),
        reward_components=tuple(_quantize_s16(value) for value in reward_components),
        trace_revision=turn_revision,
        trace_turn_digest=hashlib.sha256(envelope.turn_id.encode("utf-8")).digest()[:8],
    )
    # Append one entry and keep only the last 64 (bounded FIFO, design section 13).
    new_experiences = (base.experiences + (record,))[-EXPERIENCE_CAPACITY:]

    last_summary = base.last_snn_summary  # vestigial reuse slot: always None now

    # -- build the float64 compute product, then quantize on the persist edge -
    raw_next = V3State(
        session_ref=base.session_ref,
        schema_version=base.schema_version,
        source_digest=base.source_digest,
        state_generation_id=base.state_generation_id,
        revision=turn_revision,
        writer_epoch=envelope.sequence.writer_epoch,
        session_generation=base.session_generation,
        formula_version=base.formula_version,
        model_revision=base.model_revision,
        last_committed_turn_sequence=envelope.sequence,
        last_committed_turn_id=envelope.turn_id,
        latent_axes=next_latent,
        rho_hold=rho_hold_after,
        rho_reach=rho_reach_after,
        style_ring=new_style_ring,
        action_beliefs=settled_beliefs,
        last_snn_summary=last_summary,
        pending_outcome=new_pending,
        experiences=new_experiences,
        label_free=settled_label_free,
    )
    try:
        payload = encode_state(raw_next, max_bytes=STATE_HARD_CAP_BYTES)
        canonical_next = decode_state(payload)  # the sole canonical in-memory state
    except StateSizeError:
        return _rejected("STATE_OVERSIZE", (("v3_state_oversize", float(turn_revision)),))
    except StateCodecError:
        return _rejected("STATE_QUANTIZE_ERROR", (("v3_state_quantize_error", float(turn_revision)),))
    payload_digest = hashlib.sha256(payload).hexdigest()

    # -- stage: trace --------------------------------------------------------
    shadow_name = selected.value
    actual_name = actual_action.value if actual_action is not None else "UNKNOWN"
    if actual_action is None:
        disagreement = False
        disagreement_reason = "ACTUAL_UNKNOWN"
    elif selected == actual_action:
        disagreement = False
        disagreement_reason = "AGREE"
    else:
        disagreement = True
        disagreement_reason = "DISAGREE"

    weight_saturation = 0.0  # SNN deleted (formula v2): no plastic weights to saturate

    trace = CoreDecisionTrace(
        schema_version=TRACE_SCHEMA_VERSION,
        turn_id=envelope.turn_id,
        writer_epoch=envelope.sequence.writer_epoch,
        local_sequence=envelope.sequence.local_sequence,
        formula_version=profile.formula_version,
        formula_digest=FORMULA_DIGEST,
        model_revision=profile.model_version,
        state_generation_id=base.state_generation_id,
        source_digest=base.source_digest,
        base_revision=base.revision,
        next_revision=turn_revision,
        input_digest=input_digest,
        payload_digest=payload_digest,
        profile_id=profile.profile_id,
        profile_snn_enabled=profile.snn_enabled,
        profile_ticks=profile.ticks,
        profile_stdp_enabled=profile.stdp_enabled,
        profile_reuse_last_summary=profile.reuse_last_summary,
        math_backend=profile.math_backend,
        profile_digest=canonical_sha256(profile),
        seed=envelope.deterministic_seed,
        observation_values=frame.values,
        observation_valid_mask=frame.valid_mask,
        decision_state=decision_state,
        drive=drive,
        next_latent_axes=next_latent,
        dynamics_advanced=dynamics_advanced,
        snn_ran=False,
        snn_rolled_back=False,
        snn_summary_valid=False,
        weight_saturation=weight_saturation,
        spike_counts=spike_counts,
        first_latencies=first_latencies,
        snn_summary=trace_summary,
        workspace_mode=broadcast.mode,
        proposal_ids=tuple(proposal.proposal_id for proposal in broadcast.proposals),
        proposal_sources=tuple(proposal.source_index for proposal in broadcast.proposals),
        proposal_salience=tuple(proposal.salience for proposal in broadcast.proposals),
        proposal_confidence=tuple(proposal.confidence for proposal in broadcast.proposals),
        activation=broadcast.activation,
        inhibition=broadcast.inhibition,
        effective_salience=broadcast.effective_salience,
        broadcast_ids=broadcast.broadcast_ids,
        support=broadcast.support,
        log_evidence=broadcast.log_evidence,
        source_refractory_next=broadcast.source_refractory_next,
        candidate_actions=tuple(candidate.action.value for candidate in policy.candidates),
        candidate_mu=tuple(candidate.mu for candidate in policy.candidates),
        candidate_predictive_var=tuple(candidate.predictive_var for candidate in policy.candidates),
        candidate_prior_log=tuple(candidate.prior_log for candidate in policy.candidates),
        candidate_workspace_evidence=tuple(
            candidate.workspace_log_evidence for candidate in policy.candidates
        ),
        candidate_refractory=tuple(candidate.refractory_penalty for candidate in policy.candidates),
        candidate_risk=tuple(candidate.risk for candidate in policy.candidates),
        candidate_ambiguity=tuple(candidate.ambiguity for candidate in policy.candidates),
        candidate_information_gain=tuple(candidate.information_gain for candidate in policy.candidates),
        candidate_expected_free_energy=tuple(
            candidate.expected_free_energy for candidate in policy.candidates
        ),
        candidate_logit=tuple(candidate.logit for candidate in policy.candidates),
        candidate_posterior=tuple(candidate.posterior for candidate in policy.candidates),
        selected_action=shadow_name,
        policy_confidence=policy.confidence,
        rho_hold_before=base.rho_hold,
        rho_reach_before=base.rho_reach,
        rho_hold_after=rho_hold_after,
        rho_reach_after=rho_reach_after,
        length_bucket=constraints.length_bucket,
        pace=constraints.pace,
        directness=constraints.directness,
        warmth=constraints.warmth,
        hesitation=constraints.hesitation,
        style_signature=constraints.style_signature,
        shadow_action=shadow_name,
        actual_action=actual_name,
        disagreement=disagreement,
        disagreement_reason=disagreement_reason,
        degradation_reason=degradation_reason,
        r_react=lf_r_react,
        reaction_valid=lf_reaction_valid,
        lf_censor_reason=lf_censor_reason,
        pref_offset_after=lf_pref_offset_after,
        marginal_mu=lf_marginal_mu,
    )

    trace_bytes = canonical_trace_bytes(trace)
    if len(trace_bytes) > TRACE_HARD_CAP_BYTES:
        # Reject the whole invocation: commit neither state nor core trace.
        return _rejected("TRACE_OVERSIZE", (("v3_trace_oversize_bytes", float(len(trace_bytes))),))
    trace_digest = trace_digest_hex(trace_bytes)
    journal_digest = compute_journal_digest(
        payload_digest, len(payload), trace_digest, len(trace_bytes)
    )

    effects = EffectBundle(
        effects=(
            V3StateEffect(payload=payload),
            V3TraceEffect(payload=trace_bytes),
            V3MetricEffect(name="v3_shadow_turn", value=1.0),
            V3MetricEffect(name="v3_shadow_disagreement", value=1.0 if disagreement else 0.0),
        )
    )
    decision_plan = DecisionPlan(
        action=selected,
        confidence=policy.confidence,
        expression=constraints,
        reasons=(broadcast.mode, degradation_reason, disagreement_reason),
    )
    state_delta = StateDelta(
        next_state=canonical_next,
        payload_digest=payload_digest,
        base_revision=base.revision,
    )
    return OrchestratorResult(
        accepted=True,
        reject_reason="",
        decision_plan=decision_plan,
        state_delta=state_delta,
        effects=effects,
        trace=trace,
        trace_bytes=trace_bytes,
        trace_digest=trace_digest,
        payload_digest=payload_digest,
        journal_digest=journal_digest,
        telemetry=(
            ("v3_state_bytes", float(len(payload))),
            ("v3_trace_bytes", float(len(trace_bytes))),
        ),
    )


__all__ = [
    "OrchestratorResult",
    "STAGE_ORDER",
    "STATE_HARD_CAP_BYTES",
    "TRACE_HARD_CAP_BYTES",
    "ExpressionConstraints",
    "orchestrate",
]
