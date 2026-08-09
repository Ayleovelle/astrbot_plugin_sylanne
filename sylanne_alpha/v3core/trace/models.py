"""Frozen canonical decision trace model (design section 16.2).

:class:`CoreDecisionTrace` is a pure, self-validating result DTO (like
:class:`~sylanne_alpha.v3core.dynamics.models.MultiscaleAdvance`): it checks its
own shapes/finiteness/bounds and is *not* part of the sealed canonical registry,
because it is serialized by the dedicated byte codec in :mod:`.canonical`, never
by the generic canonical-JSON path.

It carries every value section 16.2 requires: turn/input/state/formula/model
revisions and digests; the complete ``ComputeProfile`` and its digest; the seed
and canonical decision-state (BodySnapshot PE) values; the deterministic, SNN,
and continuous-path features; per-neuron spike counts and first latencies plus
SNN degradation state; every workspace proposal/activation/inhibition/broadcast;
every candidate belief and EFE term; the v3 shadow action, v2 actual action, and
structured disagreement; and a deterministic degradation reason.  It may carry
the cognitive ``payload_digest`` but never its own ``trace_digest`` or the
``journal_digest`` — the digest dependency graph stays acyclic
(payload -> trace -> journal).

Required fixed-shape numeric values are stored as exact ``float`` tuples; the
canonical codec packs them as big-endian IEEE-754 doubles so byte-identical
replay reproduces them losslessly.  Digest/count summaries may accompany them but
never replace them.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from ..canonical import assert_exact_type
from ..formula_v1 import (
    AXIS_DIM,
    LF_TRACE_CENSOR_REASONS,
    OBSERVATION_DIM,
    SNN_NEURONS,
    SNN_SUMMARY_DIM,
    STATE_DIM,
)


# formula v2 label-free reaction learning (spec 2026-07-18 §4.3) added the five
# ``r_react`` / ``reaction_valid`` / ``lf_censor_reason`` / ``pref_offset_after`` /
# ``marginal_mu`` telemetry fields below, bumping the trace schema from 1 to 2.
# Slice D adds ``reaction_same_sender`` (spec §1.4): ``same_sender`` participates in
# state evolution (it censors the reaction and gates the length baseline), so it is a
# deterministic core input and MUST be recorded here for the trace to be a complete,
# byte-reproducible explanation of the settlement -- schema bumps 2 -> 3.  It is a
# three-valued boolean relation (True/False/None), carries no identity, and does not
# widen the privacy surface.
TRACE_SCHEMA_VERSION = 3
_LF_CENSOR_REASONS = frozenset(LF_TRACE_CENSOR_REASONS)

_WORKSPACE_MODES = ("EMPTY", "SINGLE_LEGAL", "TOP1", "TOP2_AMBIGUOUS")
_EXPRESSION_BUCKETS = ("NONE", "SHORT", "MEDIUM", "LONG")
_ACTION_NAMES = ("SPEAK", "HOLD", "CLARIFY", "REACH")
_ACTUAL_NAMES = _ACTION_NAMES + ("UNKNOWN",)


def _check_str(value: object, name: str) -> None:
    assert_exact_type(value, str, name)


def _check_bool(value: object, name: str) -> None:
    assert_exact_type(value, bool, name)


def _check_int(value: object, name: str) -> None:
    assert_exact_type(value, int, name)


def _check_finite(value: object, name: str) -> None:
    assert_exact_type(value, float, name)
    if not isfinite(value):
        raise ValueError(f"{name} must be finite")


def _check_float_vec(values: object, length: int, name: str) -> None:
    assert_exact_type(values, tuple, name)
    if len(values) != length:
        raise ValueError(f"{name} must have exactly {length} entries")
    for index, value in enumerate(values):
        _check_finite(value, f"{name}[{index}]")


def _check_int_vec(values: object, length: int, name: str) -> None:
    assert_exact_type(values, tuple, name)
    if len(values) != length:
        raise ValueError(f"{name} must have exactly {length} entries")
    for index, value in enumerate(values):
        _check_int(value, f"{name}[{index}]")


def _check_variable_float_vec(values: object, count: int, name: str) -> None:
    assert_exact_type(values, tuple, name)
    if len(values) != count:
        raise ValueError(f"{name} must align with the proposal/candidate count")
    for index, value in enumerate(values):
        _check_finite(value, f"{name}[{index}]")


@dataclass(frozen=True, slots=True)
class CoreDecisionTrace:
    """The complete deterministic explanation of one committed shadow turn."""

    # -- identity / revisions / digests --------------------------------------
    schema_version: int
    turn_id: str
    writer_epoch: int
    local_sequence: int
    formula_version: str
    formula_digest: str
    model_revision: str
    state_generation_id: str
    source_digest: str
    base_revision: int
    next_revision: int
    input_digest: str
    payload_digest: str
    # -- compute profile ------------------------------------------------------
    profile_id: str
    profile_snn_enabled: bool
    profile_ticks: int
    profile_stdp_enabled: bool
    profile_reuse_last_summary: bool
    math_backend: str
    profile_digest: str
    seed: bytes
    # -- deterministic / continuous path -------------------------------------
    observation_values: tuple
    observation_valid_mask: int
    decision_state: tuple
    drive: tuple
    next_latent_axes: tuple
    dynamics_advanced: bool
    # -- SNN path -------------------------------------------------------------
    snn_ran: bool
    snn_rolled_back: bool
    snn_summary_valid: bool
    weight_saturation: float
    spike_counts: tuple
    first_latencies: tuple
    snn_summary: tuple
    # -- workspace ------------------------------------------------------------
    workspace_mode: str
    proposal_ids: tuple
    proposal_sources: tuple
    proposal_salience: tuple
    proposal_confidence: tuple
    activation: tuple
    inhibition: tuple
    effective_salience: tuple
    broadcast_ids: tuple
    support: tuple
    log_evidence: tuple
    source_refractory_next: tuple
    # -- inference ------------------------------------------------------------
    candidate_actions: tuple
    candidate_mu: tuple
    candidate_predictive_var: tuple
    candidate_prior_log: tuple
    candidate_workspace_evidence: tuple
    candidate_refractory: tuple
    candidate_risk: tuple
    candidate_ambiguity: tuple
    candidate_information_gain: tuple
    candidate_expected_free_energy: tuple
    candidate_logit: tuple
    candidate_posterior: tuple
    selected_action: str
    policy_confidence: float
    # -- autonomous refractory -----------------------------------------------
    rho_hold_before: float
    rho_reach_before: float
    rho_hold_after: float
    rho_reach_after: float
    # -- expression -----------------------------------------------------------
    length_bucket: str
    pace: float
    directness: float
    warmth: float
    hesitation: bool
    style_signature: tuple
    # -- decision comparison / degradation -----------------------------------
    shadow_action: str
    actual_action: str
    disagreement: bool
    disagreement_reason: str
    degradation_reason: str
    # -- formula v2 label-free reaction learning (spec §4.3) -----------------
    # The label-free path-B verdict for this turn's settlement: the reaction scalar,
    # its validity, the settlement reason (a reaction reason when path B ran, else
    # NON_ADJACENT / NOT_ELIGIBLE), the L1 offset AFTER the update, and the L2
    # marginal prediction.  All neutral (0.0 / False / NON_ADJACENT / zeros) when
    # path B did not run this turn.
    r_react: float
    reaction_valid: bool
    lf_censor_reason: str
    pref_offset_after: tuple
    marginal_mu: tuple
    # The frozen ``same_sender`` relation consumed by this turn's path-B settlement
    # (spec §1.4): True/False/None.  ``None`` when path B did not run this turn or the
    # bridge could not decide.  Recorded so offline replay can reproduce the online
    # settlement bit-for-bit (a False same_sender censors the reaction).
    reaction_same_sender: bool | None

    def __post_init__(self) -> None:
        _check_int(self.schema_version, "schema_version")
        for name in (
            "turn_id",
            "formula_version",
            "formula_digest",
            "model_revision",
            "state_generation_id",
            "source_digest",
            "input_digest",
            "payload_digest",
            "profile_id",
            "math_backend",
            "profile_digest",
            "workspace_mode",
            "selected_action",
            "length_bucket",
            "shadow_action",
            "actual_action",
            "disagreement_reason",
            "degradation_reason",
        ):
            _check_str(getattr(self, name), name)
        for name in ("writer_epoch", "local_sequence", "base_revision", "next_revision", "observation_valid_mask", "profile_ticks"):
            _check_int(getattr(self, name), name)
        for name in (
            "profile_snn_enabled",
            "profile_stdp_enabled",
            "profile_reuse_last_summary",
            "dynamics_advanced",
            "snn_ran",
            "snn_rolled_back",
            "snn_summary_valid",
            "hesitation",
            "disagreement",
        ):
            _check_bool(getattr(self, name), name)
        assert_exact_type(self.seed, bytes, "seed")

        _check_float_vec(self.observation_values, OBSERVATION_DIM, "observation_values")
        _check_float_vec(self.decision_state, AXIS_DIM, "decision_state")
        _check_float_vec(self.drive, AXIS_DIM, "drive")
        _check_float_vec(self.next_latent_axes, STATE_DIM, "next_latent_axes")
        _check_int_vec(self.spike_counts, SNN_NEURONS, "spike_counts")
        _check_int_vec(self.first_latencies, SNN_NEURONS, "first_latencies")
        _check_float_vec(self.snn_summary, SNN_SUMMARY_DIM, "snn_summary")
        _check_float_vec(self.source_refractory_next, 8, "source_refractory_next")
        _check_finite(self.weight_saturation, "weight_saturation")

        proposal_count = len(self.proposal_ids)
        assert_exact_type(self.proposal_ids, tuple, "proposal_ids")
        for pid in self.proposal_ids:
            _check_str(pid, "proposal_ids entry")
        _check_int_vec(self.proposal_sources, proposal_count, "proposal_sources")
        _check_variable_float_vec(self.proposal_salience, proposal_count, "proposal_salience")
        _check_variable_float_vec(self.proposal_confidence, proposal_count, "proposal_confidence")
        _check_variable_float_vec(self.activation, proposal_count, "activation")
        _check_variable_float_vec(self.inhibition, proposal_count, "inhibition")
        _check_variable_float_vec(self.effective_salience, proposal_count, "effective_salience")
        assert_exact_type(self.broadcast_ids, tuple, "broadcast_ids")
        if len(self.broadcast_ids) > 2:
            raise ValueError("at most two proposals may broadcast")
        for bid in self.broadcast_ids:
            _check_str(bid, "broadcast_ids entry")
        self._check_named_pairs(self.support, "support")
        self._check_named_pairs(self.log_evidence, "log_evidence")

        candidate_count = len(self.candidate_actions)
        assert_exact_type(self.candidate_actions, tuple, "candidate_actions")
        for action in self.candidate_actions:
            _check_str(action, "candidate_actions entry")
        for name in (
            "candidate_prior_log",
            "candidate_workspace_evidence",
            "candidate_refractory",
            "candidate_risk",
            "candidate_ambiguity",
            "candidate_information_gain",
            "candidate_expected_free_energy",
            "candidate_logit",
            "candidate_posterior",
        ):
            _check_variable_float_vec(getattr(self, name), candidate_count, name)
        for name in ("candidate_mu", "candidate_predictive_var"):
            rows = getattr(self, name)
            assert_exact_type(rows, tuple, name)
            if len(rows) != candidate_count:
                raise ValueError(f"{name} must align with the candidate count")
            for row in rows:
                _check_float_vec(row, AXIS_DIM, f"{name} row")

        for name in (
            "policy_confidence",
            "rho_hold_before",
            "rho_reach_before",
            "rho_hold_after",
            "rho_reach_after",
            "pace",
            "directness",
            "warmth",
        ):
            _check_finite(getattr(self, name), name)
        _check_int_vec(self.style_signature, 4, "style_signature")

        if self.workspace_mode not in _WORKSPACE_MODES:
            raise ValueError("workspace_mode must be a declared workspace mode")
        if self.length_bucket not in _EXPRESSION_BUCKETS:
            raise ValueError("length_bucket must be a declared expression bucket")
        if self.selected_action not in _ACTION_NAMES:
            raise ValueError("selected_action must be a declared action")
        if self.shadow_action not in _ACTION_NAMES:
            raise ValueError("shadow_action must be a declared action")
        if self.actual_action not in _ACTUAL_NAMES:
            raise ValueError("actual_action must be a declared action or UNKNOWN")

        # formula v2 label-free fields.
        _check_finite(self.r_react, "r_react")
        if not -1.0 <= self.r_react <= 1.0:
            raise ValueError("r_react must lie in [-1,1]")
        _check_bool(self.reaction_valid, "reaction_valid")
        _check_str(self.lf_censor_reason, "lf_censor_reason")
        if self.lf_censor_reason not in _LF_CENSOR_REASONS:
            raise ValueError("lf_censor_reason must be a declared label-free reason")
        _check_float_vec(self.pref_offset_after, AXIS_DIM, "pref_offset_after")
        _check_float_vec(self.marginal_mu, AXIS_DIM, "marginal_mu")
        assert_exact_type(
            self.reaction_same_sender, (bool, type(None)), "reaction_same_sender"
        )

    @staticmethod
    def _check_named_pairs(mapping: object, name: str) -> None:
        assert_exact_type(mapping, tuple, name)
        for entry in mapping:
            assert_exact_type(entry, tuple, f"{name} entry")
            if len(entry) != 2:
                raise ValueError(f"{name} entries must be (name, value) pairs")
            _check_str(entry[0], f"{name} name")
            _check_finite(entry[1], f"{name} value")


__all__ = ["CoreDecisionTrace", "TRACE_SCHEMA_VERSION"]
