"""Frozen v3 cognitive state models (Task 6 schema).

A :class:`V3State` carries the persistence envelope headers required by design
section 15.1 (schema/formula/model revisions, opaque state-generation id, writer
epoch, sequence fence) alongside the complete bounded cognitive payload: the
24-dimensional continuous latent axes, the per-session spiking sub-state, the
per-action linear-Gaussian belief, the autonomous refractory scalars, the style
signature ring, an optional reuse SNN summary, an optional settled
:class:`PendingOutcome`, and a bounded 64-entry FIFO :class:`ExperienceRecord`
buffer.

Every numeric field is finite and bounded, every collection has a fixed or
capped length grounded in the frozen formula manifest, and the SNN sub-state is
Dale-checked at construction so a malformed value can never form a state.  The
canonical packed byte encoding of these models lives in :mod:`.codec`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from struct import pack, unpack

from ..canonical import assert_exact_type, assert_valid_dto
from ..contracts import Action, SessionRef, TurnSequence
from ..formula_v1 import (
    AXIS_DIM,
    EXPERIENCE_CAPACITY,
    FORMULA_VERSION,
    RECURRENT_TOPOLOGY,
    SNN_BASELINE_BOUNDS,
    SNN_EXCITATORY,
    SNN_NEURONS,
    SNN_SUMMARY_DIM,
    STATE_DIM,
    STYLE_SIGNATURE_RING_CAPACITY,
)


# --------------------------------------------------------------------------- #
# Fixed shapes derived from the frozen formula manifest
# --------------------------------------------------------------------------- #

STATE_SCHEMA_VERSION = 1
LATENT_DIM = STATE_DIM  # 24 = 8 axes x 3 timescales
SNN_NEURON_COUNT = SNN_NEURONS  # 96
ACTION_COUNT = 4  # SPEAK, HOLD, CLARIFY, REACH
THETA_PARAMS = 2  # theta_ai = [g_ai, b_ai] per axis (design 11.3)
STYLE_RING_CAPACITY = STYLE_SIGNATURE_RING_CAPACITY  # 4
STYLE_SIGNATURE_FIELDS = 4  # (length, pace, directness/warmth, hesitation) buckets
WORKSPACE_BROADCAST_DIM = 8  # one salience per workspace proposal slot
EXPERIENCE_FEATURE_DIM = STATE_DIM  # quantized continuous/path feature vector
EXPERIENCE_REWARD_DIM = AXIS_DIM  # per-axis reward components

# SNN scalar bounds (design 8.2 / 8.3).  Excitatory plastic weights are the only
# per-session synapses, so they are non-negative; the Dale gate rejects any
# negative plastic weight.
#
# These are the *declared* (semantic) bounds: what the core clamps to and what the
# saturation metric measures against.  They are NOT what a reloaded state is
# validated against -- see ``quantization_safe_bounds`` below.
PLASTIC_WEIGHT_BOUNDS = (0.0, 0.35)
ELIGIBILITY_BOUNDS = (-3.0, 3.0)
THRESHOLD_BOUNDS = (0.65, 1.35)
TRACE_BOUNDS = (0.0, 3.0)
VOLTAGE_BOUNDS = (-8.0, 8.0)


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
#   baselines    -- design 8.3: clip(0.95*baseline + 0.05*reward, -1, 1); the frozen
#                   manifest constant is reused rather than restated.
#   last_snn_summary -- ``spiking.reservoir.pooled_summary``: 8 pool rates clipped to
#                   [0,1] then 8 latency confidences ``1 - latency/(ticks-1)``, also
#                   in [0,1].
# These were all declared (-16, 16) -- up to 16x looser than the real clamp, so a
# grossly out-of-range value would have validated as if it were in band.
LATENT_AXIS_BOUNDS = (-1.0, 1.0)
BASELINE_BOUNDS = SNN_BASELINE_BOUNDS
SNN_SUMMARY_BOUNDS = (0.0, 1.0)

# Storage-validation intervals: the declared bounds above, widened onto the float16
# persistence grid.  Every DTO validates against these; nothing clamps to them.
# -1.0/0.0/1.0/3.0/8.0 are all exactly representable in float16, so those intervals
# come back unchanged -- only the 0.65 floor and the 0.35 ceiling actually move.
PLASTIC_WEIGHT_STORED_BOUNDS = quantization_safe_bounds(PLASTIC_WEIGHT_BOUNDS)
ELIGIBILITY_STORED_BOUNDS = quantization_safe_bounds(ELIGIBILITY_BOUNDS)
THRESHOLD_STORED_BOUNDS = quantization_safe_bounds(THRESHOLD_BOUNDS)
TRACE_STORED_BOUNDS = quantization_safe_bounds(TRACE_BOUNDS)
VOLTAGE_STORED_BOUNDS = quantization_safe_bounds(VOLTAGE_BOUNDS)
LATENT_AXIS_STORED_BOUNDS = quantization_safe_bounds(LATENT_AXIS_BOUNDS)
BASELINE_STORED_BOUNDS = quantization_safe_bounds(BASELINE_BOUNDS)
SNN_SUMMARY_STORED_BOUNDS = quantization_safe_bounds(SNN_SUMMARY_BOUNDS)

# Quantization ranges for the ExperienceBuffer (design 13).
_U8_RANGE = (0, 255)
_S16_RANGE = (-32768, 32767)
_ACTION_CODE_NONE = 255


def _plastic_synapse_count() -> int:
    """Count the excitatory-to-excitatory (plastic) recurrent synapses."""

    total = 0
    for post in range(SNN_EXCITATORY):
        for pre in RECURRENT_TOPOLOGY[post]:
            if pre < SNN_EXCITATORY:
                total += 1
    return total


PLASTIC_SYNAPSE_COUNT = _plastic_synapse_count()


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


def _check_digest(value: object, length: int, name: str) -> None:
    assert_exact_type(value, bytes, name)
    if len(value) != length:
        raise ValueError(f"{name} must be exactly {length} bytes")


# --------------------------------------------------------------------------- #
# SNN sub-state
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class SnnState:
    """Per-session spiking reservoir state: absolute (not delta) packed arrays.

    Shared topology and immutable initial weights are model constants and are
    never copied here; only the per-session evolving values are stored.  All
    plastic synapses are excitatory-to-excitatory, so every plastic weight is
    non-negative (Dale) and bounded to ``PLASTIC_WEIGHT_BOUNDS``.
    """

    voltages: tuple
    thresholds: tuple
    pre_trace: tuple
    post_trace: tuple
    plastic_weights: tuple
    eligibility: tuple

    def __post_init__(self) -> None:
        # Bounds are the float16-widened *storage* intervals: this state is validated
        # after a decode, so it lives on the quantization grid (see
        # ``quantization_safe_bounds``), not on the exact declared interval.
        _check_float_vector(self.voltages, SNN_NEURON_COUNT, VOLTAGE_STORED_BOUNDS, "voltages")
        _check_float_vector(
            self.thresholds, SNN_NEURON_COUNT, THRESHOLD_STORED_BOUNDS, "thresholds"
        )
        _check_float_vector(self.pre_trace, SNN_NEURON_COUNT, TRACE_STORED_BOUNDS, "pre_trace")
        _check_float_vector(self.post_trace, SNN_NEURON_COUNT, TRACE_STORED_BOUNDS, "post_trace")
        _check_float_vector(
            self.plastic_weights,
            PLASTIC_SYNAPSE_COUNT,
            PLASTIC_WEIGHT_STORED_BOUNDS,
            "plastic_weights",
        )
        _check_float_vector(
            self.eligibility, PLASTIC_SYNAPSE_COUNT, ELIGIBILITY_STORED_BOUNDS, "eligibility"
        )
        assert_valid_dto(self)


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
    stdp_credit_enabled: bool = False
    c: tuple = ()
    v_c: tuple = ()
    reward_scale: float = 1.0
    preference_log_terms_before: tuple = ()
    predictive_mu_actual: tuple = ()
    predictive_v_actual: tuple = ()
    likelihood_r_actual: tuple = ()
    packed_eligibility: tuple | None = None
    expiry_sequence: TurnSequence | None = None
    preference_revision: str = FORMULA_VERSION
    preference_digest: str = ""
    outcome_projector_revision: str = FORMULA_VERSION

    def __post_init__(self) -> None:
        assert_exact_type(self.origin_turn_id, str, "origin_turn_id")
        assert_exact_type(self.sequence, TurnSequence, "sequence")
        assert_exact_type(self.action, Action, "action")
        assert_exact_type(
            self.projected_actual_action, (Action, type(None)), "projected_actual_action"
        )
        assert_exact_type(self.stdp_credit_enabled, bool, "stdp_credit_enabled")
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
        if self.packed_eligibility is not None:
            _check_float_vector(
                self.packed_eligibility,
                PLASTIC_SYNAPSE_COUNT,
                ELIGIBILITY_STORED_BOUNDS,
                "packed_eligibility",
            )
        assert_exact_type(self.expiry_sequence, (TurnSequence, type(None)), "expiry_sequence")
        assert_exact_type(self.preference_revision, str, "preference_revision")
        assert_exact_type(self.preference_digest, str, "preference_digest")
        assert_exact_type(self.outcome_projector_revision, str, "outcome_projector_revision")
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
    snn: SnnState | None = None
    action_beliefs: ActionBeliefs | None = None
    last_snn_summary: tuple | None = None
    pending_outcome: PendingOutcome | None = None
    experiences: tuple = ()

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
        assert_exact_type(self.snn, (SnnState, type(None)), "snn")
        assert_exact_type(self.action_beliefs, (ActionBeliefs, type(None)), "action_beliefs")
        if self.last_snn_summary is not None:
            _check_float_vector(
                self.last_snn_summary, SNN_SUMMARY_DIM, SNN_SUMMARY_STORED_BOUNDS, "last_snn_summary"
            )
        assert_exact_type(
            self.pending_outcome, (PendingOutcome, type(None)), "pending_outcome"
        )
        self._validate_experiences()
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
    "ELIGIBILITY_BOUNDS",
    "ELIGIBILITY_STORED_BOUNDS",
    "EXPERIENCE_FEATURE_DIM",
    "EXPERIENCE_REWARD_DIM",
    "LATENT_DIM",
    "PLASTIC_SYNAPSE_COUNT",
    "PLASTIC_WEIGHT_BOUNDS",
    "PLASTIC_WEIGHT_STORED_BOUNDS",
    "SNN_NEURON_COUNT",
    "STATE_SCHEMA_VERSION",
    "STYLE_RING_CAPACITY",
    "STYLE_SIGNATURE_FIELDS",
    "THETA_PARAMS",
    "THRESHOLD_BOUNDS",
    "THRESHOLD_STORED_BOUNDS",
    "TRACE_BOUNDS",
    "TRACE_STORED_BOUNDS",
    "VOLTAGE_BOUNDS",
    "VOLTAGE_STORED_BOUNDS",
    "WORKSPACE_BROADCAST_DIM",
    "ActionBeliefs",
    "ExperienceRecord",
    "PendingOutcome",
    "SnnState",
    "V3State",
    "quantization_safe_bounds",
]
