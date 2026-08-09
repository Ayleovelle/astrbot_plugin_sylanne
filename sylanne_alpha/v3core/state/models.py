"""Frozen v3 cognitive state models (Task 6 schema).

A :class:`V3State` carries the persistence envelope headers required by design
section 15.1 (schema/formula/model revisions, opaque state-generation id, writer
epoch, sequence fence) alongside the complete bounded cognitive payload: the
24-dimensional continuous latent axes, the per-action linear-Gaussian belief, the
autonomous refractory scalars, the style signature ring, a vestigial optional
reuse summary (``last_snn_summary``, always ``None`` since formula v2 deleted the
SNN), an optional settled :class:`PendingOutcome`, and a bounded 64-entry FIFO
:class:`ExperienceRecord` buffer.

Every numeric field is finite and bounded and every collection has a fixed or
capped length grounded in the frozen formula manifest, so a malformed value can
never form a state.  The canonical packed byte encoding of these models lives in
:mod:`.codec`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from struct import pack, unpack

from ..canonical import assert_exact_type, assert_valid_dto
from ..contracts import Action, SessionRef, TurnSequence
from ..formula_v1 import (
    ACTION_B_BOUNDS,
    ACTION_COUNT_CAP,
    ACTION_G_BOUNDS,
    ACTION_SIGMA_BOUNDS,
    AXIS_DIM,
    BASELINE_BOUNDS,
    EXPERIENCE_CAPACITY,
    FORMULA_VERSION,
    PREF_OFFSET_BOUNDS,
    SNN_SUMMARY_DIM,
    STATE_DIM,
    STYLE_SIGNATURE_RING_CAPACITY,
)


# --------------------------------------------------------------------------- #
# Fixed shapes derived from the frozen formula manifest
# --------------------------------------------------------------------------- #

# formula v2 label-free reaction learning (spec 2026-07-18) added the
# ``LabelFreeState`` sub-state, the optional ``V3State.label_free`` slot, and the
# ``PendingOutcome.label_free_eligible`` flag, bumping the schema from 1 to 2.
STATE_SCHEMA_VERSION = 2
LATENT_DIM = STATE_DIM  # 24 = 8 axes x 3 timescales
ACTION_COUNT = 4  # SPEAK, HOLD, CLARIFY, REACH
THETA_PARAMS = 2  # theta_ai = [g_ai, b_ai] per axis (design 11.3)
STYLE_RING_CAPACITY = STYLE_SIGNATURE_RING_CAPACITY  # 4
STYLE_SIGNATURE_FIELDS = 4  # (length, pace, directness/warmth, hesitation) buckets
WORKSPACE_BROADCAST_DIM = 8  # one salience per workspace proposal slot
EXPERIENCE_FEATURE_DIM = STATE_DIM  # quantized continuous/path feature vector
EXPERIENCE_REWARD_DIM = AXIS_DIM  # per-axis reward components

# formula v2 deleted the SNN sub-state (``SnnState``), so the reservoir scalar
# bounds (plastic weights / eligibility / threshold / trace / voltage) and the
# plastic-synapse count are gone.  Only the per-action reward baseline bound and
# the reuse-summary bound survive, feeding ``ActionBeliefs.baselines`` and the
# vestigial ``last_snn_summary`` slot respectively.


def _to_float16(value: float) -> float:
    """Round ``value`` onto the float16 grid exactly as :mod:`.codec` packs it (``>e``)."""

    try:
        return unpack(">e", pack(">e", value))[0]
    except OverflowError as exc:  # a bound outside float16 range can never be stored
        raise ValueError(f"{value!r} is not representable on the float16 storage grid") from exc


def quantization_safe_bounds(bounds: tuple[float, float]) -> tuple[float, float]:
    """Widen a declared bound to the float16 grid the codec actually persists on.

    Quantization *is* persistence (回溯红队 a16 MAJOR DoD).  Every bounded real in a
    :class:`V3State` round-trips through ``struct`` ``'>e'`` in :mod:`.codec`, so the
    value a reload validates is ``float16(x)``, never ``x``.  float16 rounding is
    round-half-even, and it can carry a boundary value *outside* its own declared
    interval: ``float16(0.65) = 0.64990234375 < 0.65`` and
    ``float16(0.35) = 0.35009765625 > 0.35``.

    Validating a decoded state against the *exact* declared interval therefore
    rejects states the clamp is required to produce.  That is the
    ``STATE_QUANTIZE_ERROR`` livelock: once homeostasis pins a threshold to its 0.65
    clamp floor, ``decode(encode(state))`` raises forever, ``orchestrate()`` rejects
    every turn, and the shadow permanently stops advancing state.

    The fix is one bound vocabulary for "bounded": the validation interval is the
    declared interval unioned with its float16 image -- widened *outward* to the
    nearest representable value on each side.  Because float16 rounding is monotone
    non-decreasing, ``low <= x <= high`` implies
    ``float16(low) <= float16(x) <= float16(high)``; taking the union with the
    declared interval means the result accepts both ``x`` and its stored image for
    every legal ``x``.  That is exactly the a16 DoD: ``decode(encode(x))`` holds for
    *any* state legally clamped to a bound.

    The declared bounds themselves are deliberately left alone.  They are the
    semantic contract the core clamps to and measures saturation against
    (``orchestrator._WEIGHT_HI``); widening them in place would silently retire that
    saturation gate.  Only the storage-validation interval moves.
    """

    low, high = bounds
    if low > high:
        raise ValueError(f"declared bounds {bounds!r} are inverted")
    return (min(low, _to_float16(low)), max(high, _to_float16(high)))


# Continuous payload bounds, each grounded in the code that actually clamps them:
#   latent_axes  -- design 9: 24 values in [-1,1]; ``dynamics.multiscale._clip_unit``.
#   baselines    -- per-action reward EMA clip(0.95*baseline + 0.05*reward, -1, 1)
#                   (``learning.outcomes.update_baseline``).
#   last_snn_summary -- vestigial reuse slot (formula v2 deleted the reservoir that
#                   produced it); still validated to [0,1] when present, always None now.
LATENT_AXIS_BOUNDS = (-1.0, 1.0)
SNN_SUMMARY_BOUNDS = (0.0, 1.0)

# Storage-validation intervals: the declared bounds above, widened onto the float16
# persistence grid.  Every DTO validates against these; nothing clamps to them.
# -1.0/0.0/1.0 are all exactly representable in float16, so those intervals come
# back unchanged.
LATENT_AXIS_STORED_BOUNDS = quantization_safe_bounds(LATENT_AXIS_BOUNDS)
BASELINE_STORED_BOUNDS = quantization_safe_bounds(BASELINE_BOUNDS)
SNN_SUMMARY_STORED_BOUNDS = quantization_safe_bounds(SNN_SUMMARY_BOUNDS)

# --------------------------------------------------------------------------- #
# formula v2 label-free learner state shapes and bounds (spec 2026-07-18 §3.1)
# --------------------------------------------------------------------------- #
#   pref_offset     -- L1 preference-offset residual, 8 axes in PREF_OFFSET_BOUNDS
#                      (clamped by the L1 update law in learning.label_free, Slice C).
#   marginal_theta  -- L2 marginal outcome head EKF mean, 16 = 8 axes x [g, b]
#                      interleaved exactly like ``ActionBeliefs`` rows; g reuses
#                      ACTION_G_BOUNDS and b reuses ACTION_B_BOUNDS (spec §3.1/§3.3).
#   marginal_sigma  -- L2 diagonal parameter covariance, 16 values in ACTION_SIGMA_BOUNDS.
#   len_baseline    -- rolling user length baseline in [0,1] (behavioural statistic).
LABEL_FREE_PREF_OFFSET_DIM = AXIS_DIM  # 8
LABEL_FREE_MARGINAL_DIM = AXIS_DIM * THETA_PARAMS  # 16 = 8 axes x [g, b]
MARGINAL_COUNT_CAP = ACTION_COUNT_CAP  # 65535 (reuses the per-action EKF count cap)
REACTION_COUNT_CAP = 65535
LEN_BASELINE_BOUNDS = (0.0, 1.0)

# Storage-validation intervals widened onto the float16 persistence grid, exactly
# like the continuous bounds above.  ``float16(0.30) = 0.300048828125 > 0.30`` and
# ``float16(1e-4) < 1e-4``, so validating a decoded value against the *declared*
# interval would reject states the L1/L2 clamps are required to produce (the a16
# STATE_QUANTIZE_ERROR trap); every label-free DTO validates against these instead.
PREF_OFFSET_STORED_BOUNDS = quantization_safe_bounds(PREF_OFFSET_BOUNDS)
MARGINAL_G_STORED_BOUNDS = quantization_safe_bounds(ACTION_G_BOUNDS)
MARGINAL_B_STORED_BOUNDS = quantization_safe_bounds(ACTION_B_BOUNDS)
MARGINAL_SIGMA_STORED_BOUNDS = quantization_safe_bounds(ACTION_SIGMA_BOUNDS)
LEN_BASELINE_STORED_BOUNDS = quantization_safe_bounds(LEN_BASELINE_BOUNDS)
# marginal_theta interleaves g (even index) and b (odd index); each position keeps
# its own storage-validation interval so a g-legal value cannot smuggle into a b slot.
MARGINAL_THETA_STORED_BOUNDS = tuple(
    MARGINAL_G_STORED_BOUNDS if index % 2 == 0 else MARGINAL_B_STORED_BOUNDS
    for index in range(LABEL_FREE_MARGINAL_DIM)
)

# Quantization ranges for the ExperienceBuffer (design 13).
_U8_RANGE = (0, 255)
_S16_RANGE = (-32768, 32767)
_ACTION_CODE_NONE = 255


# --------------------------------------------------------------------------- #
# Validation helpers
# --------------------------------------------------------------------------- #


def _check_float_vector(
    values: object,
    length: int,
    bounds: tuple[float, float],
    name: str,
) -> None:
    assert_exact_type(values, tuple, name)
    if len(values) != length:
        raise ValueError(f"{name} must have exactly {length} entries")
    low, high = bounds
    for index, value in enumerate(values):
        assert_exact_type(value, float, f"{name}[{index}]")
        # assert_valid_dto (called by every DTO) already rejects non-finite floats,
        # but bound the range here so a finite out-of-range value also fails closed.
        if not low <= value <= high:
            raise ValueError(f"{name}[{index}] must lie in [{low}, {high}]")


def _check_int_vector(
    values: object,
    length: int,
    bounds: tuple[int, int],
    name: str,
) -> None:
    assert_exact_type(values, tuple, name)
    if len(values) != length:
        raise ValueError(f"{name} must have exactly {length} entries")
    low, high = bounds
    for index, value in enumerate(values):
        assert_exact_type(value, int, f"{name}[{index}]")
        if not low <= value <= high:
            raise ValueError(f"{name}[{index}] must lie in [{low}, {high}]")


def _check_float_vector_indexed(
    values: object,
    per_index_bounds: tuple[tuple[float, float], ...],
    name: str,
) -> None:
    """Like :func:`_check_float_vector` but with a distinct bound per position.

    Used for ``marginal_theta`` whose 16 entries interleave g/b parameters with
    different legal intervals; a single shared interval would let a g-legal value
    validate in a b slot.
    """

    assert_exact_type(values, tuple, name)
    if len(values) != len(per_index_bounds):
        raise ValueError(f"{name} must have exactly {len(per_index_bounds)} entries")
    for index, value in enumerate(values):
        assert_exact_type(value, float, f"{name}[{index}]")
        low, high = per_index_bounds[index]
        if not low <= value <= high:
            raise ValueError(f"{name}[{index}] must lie in [{low}, {high}]")


def _check_digest(value: object, length: int, name: str) -> None:
    assert_exact_type(value, bytes, name)
    if len(value) != length:
        raise ValueError(f"{name} must be exactly {length} bytes")


# --------------------------------------------------------------------------- #
# Action belief sub-state
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ActionBeliefs:
    """Per-action linear-Gaussian belief: EKF mean/covariance, baseline, count.

    ``theta`` and ``sigma`` are ``ACTION_COUNT`` rows of ``AXIS_DIM*THETA_PARAMS``
    values (the ``[g, b]`` parameters per axis and their diagonal variances).
    """

    theta: tuple
    sigma: tuple
    baselines: tuple
    counts: tuple

    def __post_init__(self) -> None:
        params = AXIS_DIM * THETA_PARAMS
        for name, rows in (("theta", self.theta), ("sigma", self.sigma)):
            assert_exact_type(rows, tuple, name)
            if len(rows) != ACTION_COUNT:
                raise ValueError(f"{name} must have exactly {ACTION_COUNT} rows")
            for action_index, row in enumerate(rows):
                assert_exact_type(row, tuple, f"{name}[{action_index}]")
                if len(row) != params:
                    raise ValueError(f"{name}[{action_index}] must have {params} parameters")
                for param_index, value in enumerate(row):
                    assert_exact_type(value, float, f"{name}[{action_index}][{param_index}]")
        _check_float_vector(self.baselines, ACTION_COUNT, BASELINE_STORED_BOUNDS, "baselines")
        _check_int_vector(self.counts, ACTION_COUNT, (0, 2**31 - 1), "counts")
        assert_valid_dto(self)


# --------------------------------------------------------------------------- #
# Experience buffer entry
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ExperienceRecord:
    """One bounded, quantized ExperienceBuffer entry (design 13).

    Observations quantize to unsigned 8-bit, bounded signed features/rewards to
    signed 16-bit, and actions to small integer codes (``255`` = UNKNOWN/none).
    The trace revision key is ``(state.state_generation_id, trace_revision,
    trace_turn_digest)``; the shared generation id and outcome-projector revision
    live once on the enclosing state, never per entry.
    """

    observation_digest: bytes
    encoded_features: tuple
    workspace_broadcast: tuple
    shadow_action_code: int
    actual_action_code: int
    next_observation: tuple
    reward_components: tuple
    trace_revision: int
    trace_turn_digest: bytes

    def __post_init__(self) -> None:
        _check_digest(self.observation_digest, 8, "observation_digest")
        _check_int_vector(
            self.encoded_features, EXPERIENCE_FEATURE_DIM, _S16_RANGE, "encoded_features"
        )
        _check_int_vector(
            self.workspace_broadcast, WORKSPACE_BROADCAST_DIM, _S16_RANGE, "workspace_broadcast"
        )
        _check_int_vector(self.next_observation, 36, _U8_RANGE, "next_observation")
        _check_int_vector(
            self.reward_components, EXPERIENCE_REWARD_DIM, _S16_RANGE, "reward_components"
        )
        assert_exact_type(self.shadow_action_code, int, "shadow_action_code")
        assert_exact_type(self.actual_action_code, int, "actual_action_code")
        if not (0 <= self.shadow_action_code < ACTION_COUNT or self.shadow_action_code == _ACTION_CODE_NONE):
            raise ValueError("shadow_action_code must be a valid action code or 255")
        if not (0 <= self.actual_action_code <= ACTION_COUNT or self.actual_action_code == _ACTION_CODE_NONE):
            raise ValueError("actual_action_code must be a valid action code, UNKNOWN, or 255")
        assert_exact_type(self.trace_revision, int, "trace_revision")
        if not 0 <= self.trace_revision <= 2**32 - 1:
            raise ValueError("trace_revision must fit an unsigned 32-bit integer")
        _check_digest(self.trace_turn_digest, 8, "trace_turn_digest")
        assert_valid_dto(self)


# --------------------------------------------------------------------------- #
# Label-free learner sub-state (formula v2, spec 2026-07-18 §3.1)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class LabelFreeState:
    """Bounded label-free reaction-learning state (spec §3.1).

    A ``None`` :attr:`V3State.label_free` means the whole channel is at its prior;
    a present :class:`LabelFreeState` carries the L1 preference offset
    (``pref_offset``), the L2 marginal outcome head's EKF mean/covariance
    (``marginal_theta`` / ``marginal_sigma``, 16 = 8 axes x ``[g, b]`` interleaved
    exactly like an :class:`ActionBeliefs` row), the marginal update count, the
    user's rolling length baseline, and the count of valid length samples.

    Every field is validated against the same storage-quantization-safe interval
    the codec persists on, so a malformed or out-of-band value fails closed and a
    value legally clamped to a bound still round-trips through the float16 grid.
    """

    pref_offset: tuple
    marginal_theta: tuple
    marginal_sigma: tuple
    marginal_count: int
    len_baseline: float
    reaction_count: int

    def __post_init__(self) -> None:
        _check_float_vector(
            self.pref_offset,
            LABEL_FREE_PREF_OFFSET_DIM,
            PREF_OFFSET_STORED_BOUNDS,
            "pref_offset",
        )
        _check_float_vector_indexed(self.marginal_theta, MARGINAL_THETA_STORED_BOUNDS, "marginal_theta")
        _check_float_vector(
            self.marginal_sigma,
            LABEL_FREE_MARGINAL_DIM,
            MARGINAL_SIGMA_STORED_BOUNDS,
            "marginal_sigma",
        )
        assert_exact_type(self.marginal_count, int, "marginal_count")
        if not 0 <= self.marginal_count <= MARGINAL_COUNT_CAP:
            raise ValueError(f"marginal_count must lie in [0, {MARGINAL_COUNT_CAP}]")
        assert_exact_type(self.len_baseline, float, "len_baseline")
        low, high = LEN_BASELINE_STORED_BOUNDS
        if not low <= self.len_baseline <= high:
            raise ValueError("len_baseline must be a normalized value in [0,1]")
        assert_exact_type(self.reaction_count, int, "reaction_count")
        if not 0 <= self.reaction_count <= REACTION_COUNT_CAP:
            raise ValueError(f"reaction_count must lie in [0, {REACTION_COUNT_CAP}]")
        assert_valid_dto(self)


# --------------------------------------------------------------------------- #
# Pending outcome
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class PendingOutcome:
    """One turn's frozen delayed-credit record (design 8.3).

    The three required fields (origin turn, sequence, shadow action) identify the
    turn; the optional per-axis density/posterior arrays freeze exactly the
    quantities needed to settle credit at ``t+1`` without rereading later state.
    Optional arrays default to empty so a minimal pending record remains valid.
    """

    origin_turn_id: str
    sequence: TurnSequence
    action: Action
    projected_actual_action: Action | None = None
    c: tuple = ()
    v_c: tuple = ()
    reward_scale: float = 1.0
    preference_log_terms_before: tuple = ()
    predictive_mu_actual: tuple = ()
    predictive_v_actual: tuple = ()
    likelihood_r_actual: tuple = ()
    expiry_sequence: TurnSequence | None = None
    preference_revision: str = FORMULA_VERSION
    preference_digest: str = ""
    outcome_projector_revision: str = FORMULA_VERSION
    # Frozen at turn t: context_t in LF_ELIGIBLE_ORIGIN_CONTEXTS (spec §2.2).  The
    # label-free settlement path (Slice C) only fires when this is true; t+1 must
    # not retro-decide eligibility, so it is decided and frozen when the pending is
    # created.  Defaults False so every legacy/minimal record stays valid.
    label_free_eligible: bool = False

    def __post_init__(self) -> None:
        assert_exact_type(self.origin_turn_id, str, "origin_turn_id")
        assert_exact_type(self.sequence, TurnSequence, "sequence")
        assert_exact_type(self.action, Action, "action")
        assert_exact_type(
            self.projected_actual_action, (Action, type(None)), "projected_actual_action"
        )
        for name, values in (
            ("c", self.c),
            ("v_c", self.v_c),
            ("preference_log_terms_before", self.preference_log_terms_before),
            ("predictive_mu_actual", self.predictive_mu_actual),
            ("predictive_v_actual", self.predictive_v_actual),
            ("likelihood_r_actual", self.likelihood_r_actual),
        ):
            assert_exact_type(values, tuple, name)
            if len(values) not in (0, AXIS_DIM):
                raise ValueError(f"{name} must be empty or have {AXIS_DIM} entries")
            for index, value in enumerate(values):
                assert_exact_type(value, float, f"{name}[{index}]")
        assert_exact_type(self.reward_scale, float, "reward_scale")
        assert_exact_type(self.expiry_sequence, (TurnSequence, type(None)), "expiry_sequence")
        assert_exact_type(self.preference_revision, str, "preference_revision")
        assert_exact_type(self.preference_digest, str, "preference_digest")
        assert_exact_type(self.outcome_projector_revision, str, "outcome_projector_revision")
        assert_exact_type(self.label_free_eligible, bool, "label_free_eligible")
        assert_valid_dto(self)
        if not self.origin_turn_id:
            raise ValueError("origin_turn_id must not be empty")


# --------------------------------------------------------------------------- #
# Complete state
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class V3State:
    """Complete bounded cognitive state: persistence envelope + cognitive payload."""

    session_ref: SessionRef
    schema_version: int = STATE_SCHEMA_VERSION
    source_digest: str = ""
    state_generation_id: str = ""
    revision: int = 0
    writer_epoch: int = 0
    session_generation: int = 0
    formula_version: str = FORMULA_VERSION
    model_revision: str = FORMULA_VERSION
    last_committed_turn_sequence: TurnSequence | None = None
    last_committed_turn_id: str | None = None
    latent_axes: tuple = field(default_factory=lambda: tuple(0.0 for _ in range(LATENT_DIM)))
    rho_hold: float = 0.0
    rho_reach: float = 0.0
    style_ring: tuple = ()
    action_beliefs: ActionBeliefs | None = None
    last_snn_summary: tuple | None = None
    pending_outcome: PendingOutcome | None = None
    experiences: tuple = ()
    label_free: LabelFreeState | None = None

    def __post_init__(self) -> None:
        assert_exact_type(self.session_ref, SessionRef, "session_ref")
        assert_exact_type(self.schema_version, int, "schema_version")
        assert_exact_type(self.source_digest, str, "source_digest")
        assert_exact_type(self.state_generation_id, str, "state_generation_id")
        assert_exact_type(self.revision, int, "revision")
        assert_exact_type(self.writer_epoch, int, "writer_epoch")
        assert_exact_type(self.session_generation, int, "session_generation")
        assert_exact_type(self.formula_version, str, "formula_version")
        assert_exact_type(self.model_revision, str, "model_revision")
        assert_exact_type(
            self.last_committed_turn_sequence,
            (TurnSequence, type(None)),
            "last_committed_turn_sequence",
        )
        assert_exact_type(
            self.last_committed_turn_id, (str, type(None)), "last_committed_turn_id"
        )
        _check_float_vector(self.latent_axes, LATENT_DIM, LATENT_AXIS_STORED_BOUNDS, "latent_axes")
        assert_exact_type(self.rho_hold, float, "rho_hold")
        assert_exact_type(self.rho_reach, float, "rho_reach")
        self._validate_style_ring()
        assert_exact_type(self.action_beliefs, (ActionBeliefs, type(None)), "action_beliefs")
        if self.last_snn_summary is not None:
            _check_float_vector(
                self.last_snn_summary, SNN_SUMMARY_DIM, SNN_SUMMARY_STORED_BOUNDS, "last_snn_summary"
            )
        assert_exact_type(
            self.pending_outcome, (PendingOutcome, type(None)), "pending_outcome"
        )
        self._validate_experiences()
        assert_exact_type(self.label_free, (LabelFreeState, type(None)), "label_free")
        assert_valid_dto(self)
        if self.schema_version < 1:
            raise ValueError("schema_version must be positive")
        if self.revision < 0 or self.writer_epoch < 0 or self.session_generation < 0:
            raise ValueError("revision/epoch/generation counters must be non-negative")
        if not 0.0 <= self.rho_hold <= 1.0 or not 0.0 <= self.rho_reach <= 1.0:
            raise ValueError("autonomous refractory values must be in [0,1]")

    def _validate_style_ring(self) -> None:
        assert_exact_type(self.style_ring, tuple, "style_ring")
        if len(self.style_ring) > STYLE_RING_CAPACITY:
            raise ValueError("style_ring exceeds the ring capacity")
        for ring_index, signature in enumerate(self.style_ring):
            assert_exact_type(signature, tuple, f"style_ring[{ring_index}]")
            if len(signature) != STYLE_SIGNATURE_FIELDS:
                raise ValueError("each style signature must have the fixed field count")
            for value in signature:
                assert_exact_type(value, int, f"style_ring[{ring_index}] entry")
                if not 0 <= value <= 255:
                    raise ValueError("style signature buckets must be unsigned 8-bit")

    def _validate_experiences(self) -> None:
        assert_exact_type(self.experiences, tuple, "experiences")
        if len(self.experiences) > EXPERIENCE_CAPACITY:
            raise ValueError("experiences exceed the 64-entry FIFO capacity")
        for record_index, record in enumerate(self.experiences):
            assert_exact_type(record, ExperienceRecord, f"experiences[{record_index}]")


__all__ = [
    "ACTION_COUNT",
    "BASELINE_BOUNDS",
    "BASELINE_STORED_BOUNDS",
    "EXPERIENCE_FEATURE_DIM",
    "EXPERIENCE_REWARD_DIM",
    "LABEL_FREE_MARGINAL_DIM",
    "LABEL_FREE_PREF_OFFSET_DIM",
    "LATENT_DIM",
    "LEN_BASELINE_BOUNDS",
    "LEN_BASELINE_STORED_BOUNDS",
    "MARGINAL_B_STORED_BOUNDS",
    "MARGINAL_COUNT_CAP",
    "MARGINAL_G_STORED_BOUNDS",
    "MARGINAL_SIGMA_STORED_BOUNDS",
    "MARGINAL_THETA_STORED_BOUNDS",
    "PREF_OFFSET_STORED_BOUNDS",
    "REACTION_COUNT_CAP",
    "SNN_SUMMARY_BOUNDS",
    "SNN_SUMMARY_STORED_BOUNDS",
    "STATE_SCHEMA_VERSION",
    "STYLE_RING_CAPACITY",
    "STYLE_SIGNATURE_FIELDS",
    "THETA_PARAMS",
    "WORKSPACE_BROADCAST_DIM",
    "ActionBeliefs",
    "ExperienceRecord",
    "LabelFreeState",
    "PendingOutcome",
    "V3State",
    "quantization_safe_bounds",
]
