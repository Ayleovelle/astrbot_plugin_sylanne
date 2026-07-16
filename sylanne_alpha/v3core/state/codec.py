"""Canonical packed byte codec and global size gate for :class:`V3State`.

The on-disk cognitive payload is a single self-describing byte string:

    base64( zlib( MAGIC || version || header || packed-payload || CRC32 ) )

Numeric arrays are packed big-endian as IEEE-754 half floats (``>e``) for
bounded reals, signed 16-bit (``>h``) for quantized features/rewards, and
unsigned 8-bit for quantized observations, exactly as design section 13
prescribes.  ``encode_state`` is deterministic; ``decode_state`` is its exact
inverse for a canonically quantized state and fails closed on any malformed
input (bad magic/version, CRC mismatch, truncation, trailing bytes, non-finite
half floats, Dale-violating SNN weights, or out-of-bounds values).

The module imports only stdlib ``struct``/``zlib``/``base64``/``binascii`` and
pure ``v3core`` models, honoring the ``v3core`` import firewall.  The hard size
ceiling itself lives in ``v3bridge.limits``; callers pass it in via
``enforce_state_size`` / ``encode_state(max_bytes=...)`` so the pure core never
imports the bridge.
"""

from __future__ import annotations

import base64
import binascii
import struct
import zlib
from math import isfinite

from ..formula_v1 import AXIS_DIM, OBSERVATION_DIM, SNN_SUMMARY_DIM
from .models import (
    ACTION_COUNT,
    EXPERIENCE_FEATURE_DIM,
    EXPERIENCE_REWARD_DIM,
    LATENT_DIM,
    PLASTIC_SYNAPSE_COUNT,
    SNN_NEURON_COUNT,
    STYLE_RING_CAPACITY,
    STYLE_SIGNATURE_FIELDS,
    THETA_PARAMS,
    WORKSPACE_BROADCAST_DIM,
    ActionBeliefs,
    ExperienceRecord,
    PendingOutcome,
    SnnState,
    V3State,
)
from ..contracts import Action, SessionRef, TurnSequence


STATE_CODEC_MAGIC = b"SYL3ST"
STATE_CODEC_VERSION = 1
MAX_STATE_BYTES_DEFAULT = None

_ACTION_ORDER = (Action.SPEAK, Action.HOLD, Action.CLARIFY, Action.REACH)
_ACTION_TO_CODE = {action: code for code, action in enumerate(_ACTION_ORDER)}
_CODE_TO_ACTION = {code: action for code, action in enumerate(_ACTION_ORDER)}
_ACTION_CODE_NONE = 255
_THETA_ROW = AXIS_DIM * THETA_PARAMS


class StateCodecError(ValueError):
    """Raised for any malformed encoded state; never returns a partial state."""


class StateSizeError(ValueError):
    """Raised when an encoded state exceeds the hard byte ceiling."""


# --------------------------------------------------------------------------- #
# Low-level writer / reader
# --------------------------------------------------------------------------- #


class _Writer:
    __slots__ = ("_chunks",)

    def __init__(self) -> None:
        self._chunks: list[bytes] = []

    def raw(self, data: bytes) -> None:
        self._chunks.append(data)

    def u8(self, value: int) -> None:
        self._chunks.append(struct.pack(">B", value))

    def u16(self, value: int) -> None:
        self._chunks.append(struct.pack(">H", value))

    def u32(self, value: int) -> None:
        self._chunks.append(struct.pack(">I", value))

    def u64(self, value: int) -> None:
        self._chunks.append(struct.pack(">Q", value))

    def f16(self, value: float) -> None:
        self._chunks.append(struct.pack(">e", value))

    def s16(self, value: int) -> None:
        self._chunks.append(struct.pack(">h", value))

    def f16_vec(self, values: tuple) -> None:
        self._chunks.append(struct.pack(">%de" % len(values), *values))

    def s16_vec(self, values: tuple) -> None:
        self._chunks.append(struct.pack(">%dh" % len(values), *values))

    def u8_vec(self, values: tuple) -> None:
        self._chunks.append(struct.pack(">%dB" % len(values), *values))

    def string(self, value: str) -> None:
        data = value.encode("utf-8")
        if len(data) > 0xFFFF:
            raise StateCodecError("string field exceeds 16-bit length")
        self._chunks.append(struct.pack(">H", len(data)))
        self._chunks.append(data)

    def opt_string(self, value: str | None) -> None:
        if value is None:
            self.u8(0)
            return
        self.u8(1)
        self.string(value)

    def sequence(self, sequence: TurnSequence) -> None:
        self.u64(sequence.writer_epoch)
        self.u64(sequence.local_sequence)

    def opt_sequence(self, sequence: TurnSequence | None) -> None:
        if sequence is None:
            self.u8(0)
            return
        self.u8(1)
        self.sequence(sequence)

    def getvalue(self) -> bytes:
        return b"".join(self._chunks)


class _Reader:
    __slots__ = ("_data", "_offset")

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._offset = 0

    def _take(self, count: int) -> bytes:
        end = self._offset + count
        if end > len(self._data):
            raise StateCodecError("encoded state truncated")
        chunk = self._data[self._offset : end]
        self._offset = end
        return chunk

    def remaining(self) -> int:
        return len(self._data) - self._offset

    def u8(self) -> int:
        return struct.unpack(">B", self._take(1))[0]

    def u16(self) -> int:
        return struct.unpack(">H", self._take(2))[0]

    def u32(self) -> int:
        return struct.unpack(">I", self._take(4))[0]

    def u64(self) -> int:
        return struct.unpack(">Q", self._take(8))[0]

    def f16(self) -> float:
        value = struct.unpack(">e", self._take(2))[0]
        if not isfinite(value):
            raise StateCodecError("encoded state contains a non-finite half float")
        return value

    def s16(self) -> int:
        return struct.unpack(">h", self._take(2))[0]

    def f16_vec(self, count: int) -> tuple:
        values = struct.unpack(">%de" % count, self._take(2 * count))
        if not all(isfinite(value) for value in values):
            raise StateCodecError("encoded state contains a non-finite half float")
        return values

    def s16_vec(self, count: int) -> tuple:
        return struct.unpack(">%dh" % count, self._take(2 * count))

    def u8_vec(self, count: int) -> tuple:
        return struct.unpack(">%dB" % count, self._take(count))

    def string(self) -> str:
        length = self.u16()
        try:
            return self._take(length).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise StateCodecError("invalid utf-8 string field") from exc

    def opt_string(self) -> str | None:
        return self.string() if self.u8() else None

    def sequence(self) -> TurnSequence:
        return _guard(lambda: TurnSequence(self.u64(), self.u64()))

    def opt_sequence(self) -> TurnSequence | None:
        return self.sequence() if self.u8() else None


def _guard(builder):
    try:
        return builder()
    except (ValueError, TypeError) as exc:
        raise StateCodecError(str(exc)) from exc


# --------------------------------------------------------------------------- #
# Encode
# --------------------------------------------------------------------------- #


def encode_state(state: V3State, *, max_bytes: int | None = MAX_STATE_BYTES_DEFAULT) -> bytes:
    """Encode a state to its canonical base64/zlib packed payload."""

    if type(state) is not V3State:
        raise StateCodecError("encode_state requires a V3State")
    writer = _Writer()
    writer.raw(STATE_CODEC_MAGIC)
    writer.u16(STATE_CODEC_VERSION)
    _write_header(writer, state)
    _write_continuous(writer, state)
    _write_snn(writer, state.snn)
    _write_beliefs(writer, state.action_beliefs)
    _write_summary(writer, state.last_snn_summary)
    _write_pending(writer, state.pending_outcome)
    _write_experiences(writer, state.experiences)
    body = writer.getvalue()
    framed = body + struct.pack(">I", binascii.crc32(body) & 0xFFFFFFFF)
    blob = base64.b64encode(zlib.compress(framed, 9))
    if max_bytes is not None:
        enforce_state_size(blob, max_bytes)
    return blob


def _write_header(writer: _Writer, state: V3State) -> None:
    writer.u16(state.schema_version)
    writer.u64(state.revision)
    writer.u64(state.writer_epoch)
    writer.u64(state.session_generation)
    writer.string(state.session_ref.key_id)
    writer.raw(state.session_ref.session_digest)  # fixed 32 bytes
    writer.u64(state.session_ref.session_generation)
    writer.string(state.formula_version)
    writer.string(state.source_digest)
    writer.string(state.state_generation_id)
    writer.string(state.model_revision)
    writer.opt_string(state.last_committed_turn_id)
    writer.opt_sequence(state.last_committed_turn_sequence)


def _write_continuous(writer: _Writer, state: V3State) -> None:
    writer.f16_vec(state.latent_axes)
    writer.f16(state.rho_hold)
    writer.f16(state.rho_reach)
    writer.u8(len(state.style_ring))
    for signature in state.style_ring:
        writer.u8_vec(signature)


def _write_snn(writer: _Writer, snn: SnnState | None) -> None:
    if snn is None:
        writer.u8(0)
        return
    writer.u8(1)
    writer.f16_vec(snn.voltages)
    writer.f16_vec(snn.thresholds)
    writer.f16_vec(snn.pre_trace)
    writer.f16_vec(snn.post_trace)
    writer.u32(len(snn.plastic_weights))
    writer.f16_vec(snn.plastic_weights)
    writer.f16_vec(snn.eligibility)


def _write_beliefs(writer: _Writer, beliefs: ActionBeliefs | None) -> None:
    if beliefs is None:
        writer.u8(0)
        return
    writer.u8(1)
    for row in beliefs.theta:
        writer.f16_vec(row)
    for row in beliefs.sigma:
        writer.f16_vec(row)
    writer.f16_vec(beliefs.baselines)
    for count in beliefs.counts:
        writer.u32(count)


def _write_summary(writer: _Writer, summary: tuple | None) -> None:
    if summary is None:
        writer.u8(0)
        return
    writer.u8(1)
    writer.f16_vec(summary)


def _action_code(action: Action | None) -> int:
    if action is None:
        return _ACTION_CODE_NONE
    return _ACTION_TO_CODE[action]


def _write_optional_axis_vector(writer: _Writer, values: tuple) -> None:
    writer.u8(len(values))
    writer.f16_vec(values)


def _write_pending(writer: _Writer, pending: PendingOutcome | None) -> None:
    if pending is None:
        writer.u8(0)
        return
    writer.u8(1)
    writer.string(pending.origin_turn_id)
    writer.sequence(pending.sequence)
    writer.u8(_action_code(pending.action))
    writer.u8(_action_code(pending.projected_actual_action))
    writer.u8(1 if pending.stdp_credit_enabled else 0)
    for values in (
        pending.c,
        pending.v_c,
        pending.preference_log_terms_before,
        pending.predictive_mu_actual,
        pending.predictive_v_actual,
        pending.likelihood_r_actual,
    ):
        _write_optional_axis_vector(writer, values)
    writer.f16(pending.reward_scale)
    if pending.packed_eligibility is None:
        writer.u8(0)
    else:
        writer.u8(1)
        writer.u32(len(pending.packed_eligibility))
        writer.f16_vec(pending.packed_eligibility)
    writer.opt_sequence(pending.expiry_sequence)
    writer.string(pending.preference_revision)
    writer.string(pending.preference_digest)
    writer.string(pending.outcome_projector_revision)


def _write_experiences(writer: _Writer, experiences: tuple) -> None:
    writer.u16(len(experiences))
    for record in experiences:
        writer.raw(record.observation_digest)  # fixed 8 bytes
        writer.s16_vec(record.encoded_features)
        writer.s16_vec(record.workspace_broadcast)
        writer.u8(record.shadow_action_code)
        writer.u8(record.actual_action_code)
        writer.u8_vec(record.next_observation)
        writer.s16_vec(record.reward_components)
        writer.u32(record.trace_revision)
        writer.raw(record.trace_turn_digest)  # fixed 8 bytes


# --------------------------------------------------------------------------- #
# Decode
# --------------------------------------------------------------------------- #


def decode_state(blob: object) -> V3State:
    """Decode a canonical packed payload back into an exact :class:`V3State`."""

    if type(blob) is not bytes:
        raise StateCodecError("decode_state requires bytes")
    try:
        compressed = base64.b64decode(blob, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise StateCodecError("invalid base64 container") from exc
    try:
        framed = zlib.decompress(compressed)
    except zlib.error as exc:
        raise StateCodecError("invalid zlib container") from exc
    if len(framed) < len(STATE_CODEC_MAGIC) + 2 + 4:
        raise StateCodecError("encoded state too short")
    body, crc_bytes = framed[:-4], framed[-4:]
    if struct.unpack(">I", crc_bytes)[0] != (binascii.crc32(body) & 0xFFFFFFFF):
        raise StateCodecError("state CRC mismatch")

    reader = _Reader(body)
    if reader._take(len(STATE_CODEC_MAGIC)) != STATE_CODEC_MAGIC:
        raise StateCodecError("bad state magic")
    if reader.u16() != STATE_CODEC_VERSION:
        raise StateCodecError("unsupported state codec version")

    header = _read_header(reader)
    latent = reader.f16_vec(LATENT_DIM)
    rho_hold = reader.f16()
    rho_reach = reader.f16()
    style_ring = _read_style_ring(reader)
    snn = _read_snn(reader)
    beliefs = _read_beliefs(reader)
    summary = _read_summary(reader)
    pending = _read_pending(reader)
    experiences = _read_experiences(reader)
    if reader.remaining() != 0:
        raise StateCodecError("trailing bytes after encoded state")

    return _guard(
        lambda: V3State(
            session_ref=header["session_ref"],
            schema_version=header["schema_version"],
            source_digest=header["source_digest"],
            state_generation_id=header["state_generation_id"],
            revision=header["revision"],
            writer_epoch=header["writer_epoch"],
            session_generation=header["session_generation"],
            formula_version=header["formula_version"],
            model_revision=header["model_revision"],
            last_committed_turn_sequence=header["last_committed_turn_sequence"],
            last_committed_turn_id=header["last_committed_turn_id"],
            latent_axes=latent,
            rho_hold=rho_hold,
            rho_reach=rho_reach,
            style_ring=style_ring,
            snn=snn,
            action_beliefs=beliefs,
            last_snn_summary=summary,
            pending_outcome=pending,
            experiences=experiences,
        )
    )


def _read_header(reader: _Reader) -> dict:
    schema_version = reader.u16()
    revision = reader.u64()
    writer_epoch = reader.u64()
    session_generation = reader.u64()
    key_id = reader.string()
    session_digest = reader._take(32)
    ref_generation = reader.u64()
    session_ref = _guard(
        lambda: SessionRef(
            key_id=key_id,
            session_digest=session_digest,
            session_generation=ref_generation,
        )
    )
    formula_version = reader.string()
    source_digest = reader.string()
    state_generation_id = reader.string()
    model_revision = reader.string()
    last_committed_turn_id = reader.opt_string()
    last_committed_turn_sequence = reader.opt_sequence()
    return {
        "schema_version": schema_version,
        "revision": revision,
        "writer_epoch": writer_epoch,
        "session_generation": session_generation,
        "session_ref": session_ref,
        "formula_version": formula_version,
        "source_digest": source_digest,
        "state_generation_id": state_generation_id,
        "model_revision": model_revision,
        "last_committed_turn_id": last_committed_turn_id,
        "last_committed_turn_sequence": last_committed_turn_sequence,
    }


def _read_style_ring(reader: _Reader) -> tuple:
    count = reader.u8()
    if count > STYLE_RING_CAPACITY:
        raise StateCodecError("style ring exceeds capacity")
    return tuple(reader.u8_vec(STYLE_SIGNATURE_FIELDS) for _ in range(count))


def _read_snn(reader: _Reader) -> SnnState | None:
    if reader.u8() == 0:
        return None
    voltages = reader.f16_vec(SNN_NEURON_COUNT)
    thresholds = reader.f16_vec(SNN_NEURON_COUNT)
    pre_trace = reader.f16_vec(SNN_NEURON_COUNT)
    post_trace = reader.f16_vec(SNN_NEURON_COUNT)
    plastic_count = reader.u32()
    if plastic_count != PLASTIC_SYNAPSE_COUNT:
        raise StateCodecError("plastic synapse count does not match the topology")
    plastic_weights = reader.f16_vec(plastic_count)
    eligibility = reader.f16_vec(plastic_count)
    return _guard(
        lambda: SnnState(
            voltages=voltages,
            thresholds=thresholds,
            pre_trace=pre_trace,
            post_trace=post_trace,
            plastic_weights=plastic_weights,
            eligibility=eligibility,
        )
    )


def _read_beliefs(reader: _Reader) -> ActionBeliefs | None:
    if reader.u8() == 0:
        return None
    theta = tuple(reader.f16_vec(_THETA_ROW) for _ in range(ACTION_COUNT))
    sigma = tuple(reader.f16_vec(_THETA_ROW) for _ in range(ACTION_COUNT))
    baselines = reader.f16_vec(ACTION_COUNT)
    counts = tuple(reader.u32() for _ in range(ACTION_COUNT))
    return _guard(
        lambda: ActionBeliefs(theta=theta, sigma=sigma, baselines=baselines, counts=counts)
    )


def _read_summary(reader: _Reader) -> tuple | None:
    if reader.u8() == 0:
        return None
    return reader.f16_vec(SNN_SUMMARY_DIM)


def _decode_action(code: int) -> Action | None:
    if code == _ACTION_CODE_NONE:
        return None
    if code not in _CODE_TO_ACTION:
        raise StateCodecError("invalid action code")
    return _CODE_TO_ACTION[code]


def _read_optional_axis_vector(reader: _Reader) -> tuple:
    length = reader.u8()
    if length not in (0, AXIS_DIM):
        raise StateCodecError("optional axis vector has an illegal length")
    return reader.f16_vec(length)


def _read_pending(reader: _Reader) -> PendingOutcome | None:
    if reader.u8() == 0:
        return None
    origin_turn_id = reader.string()
    sequence = reader.sequence()
    action = _decode_action(reader.u8())
    if action is None:
        raise StateCodecError("pending outcome must have a shadow action")
    projected_actual_action = _decode_action(reader.u8())
    stdp_credit_enabled = reader.u8() == 1
    c = _read_optional_axis_vector(reader)
    v_c = _read_optional_axis_vector(reader)
    preference_log_terms_before = _read_optional_axis_vector(reader)
    predictive_mu_actual = _read_optional_axis_vector(reader)
    predictive_v_actual = _read_optional_axis_vector(reader)
    likelihood_r_actual = _read_optional_axis_vector(reader)
    reward_scale = reader.f16()
    if reader.u8() == 1:
        eligibility_count = reader.u32()
        if eligibility_count != PLASTIC_SYNAPSE_COUNT:
            raise StateCodecError("packed eligibility count does not match the topology")
        packed_eligibility: tuple | None = reader.f16_vec(eligibility_count)
    else:
        packed_eligibility = None
    expiry_sequence = reader.opt_sequence()
    preference_revision = reader.string()
    preference_digest = reader.string()
    outcome_projector_revision = reader.string()
    return _guard(
        lambda: PendingOutcome(
            origin_turn_id=origin_turn_id,
            sequence=sequence,
            action=action,
            projected_actual_action=projected_actual_action,
            stdp_credit_enabled=stdp_credit_enabled,
            c=c,
            v_c=v_c,
            reward_scale=reward_scale,
            preference_log_terms_before=preference_log_terms_before,
            predictive_mu_actual=predictive_mu_actual,
            predictive_v_actual=predictive_v_actual,
            likelihood_r_actual=likelihood_r_actual,
            packed_eligibility=packed_eligibility,
            expiry_sequence=expiry_sequence,
            preference_revision=preference_revision,
            preference_digest=preference_digest,
            outcome_projector_revision=outcome_projector_revision,
        )
    )


def _read_experiences(reader: _Reader) -> tuple:
    count = reader.u16()
    records = []
    for _ in range(count):
        observation_digest = reader._take(8)
        encoded_features = reader.s16_vec(EXPERIENCE_FEATURE_DIM)
        workspace_broadcast = reader.s16_vec(WORKSPACE_BROADCAST_DIM)
        shadow_action_code = reader.u8()
        actual_action_code = reader.u8()
        next_observation = reader.u8_vec(OBSERVATION_DIM)
        reward_components = reader.s16_vec(EXPERIENCE_REWARD_DIM)
        trace_revision = reader.u32()
        trace_turn_digest = reader._take(8)
        records.append(
            _guard(
                lambda observation_digest=observation_digest,
                encoded_features=encoded_features,
                workspace_broadcast=workspace_broadcast,
                shadow_action_code=shadow_action_code,
                actual_action_code=actual_action_code,
                next_observation=next_observation,
                reward_components=reward_components,
                trace_revision=trace_revision,
                trace_turn_digest=trace_turn_digest: ExperienceRecord(
                    observation_digest=observation_digest,
                    encoded_features=encoded_features,
                    workspace_broadcast=workspace_broadcast,
                    shadow_action_code=shadow_action_code,
                    actual_action_code=actual_action_code,
                    next_observation=next_observation,
                    reward_components=reward_components,
                    trace_revision=trace_revision,
                    trace_turn_digest=trace_turn_digest,
                )
            )
        )
    return tuple(records)


# --------------------------------------------------------------------------- #
# Global size gate
# --------------------------------------------------------------------------- #


def enforce_state_size(payload: object, max_bytes: int) -> bytes:
    """Fail closed if an encoded payload exceeds the hard byte ceiling."""

    if type(payload) is not bytes:
        raise StateCodecError("size gate requires the encoded bytes")
    if type(max_bytes) is not int or type(max_bytes) is bool or max_bytes < 0:
        raise StateCodecError("max_bytes must be a non-negative integer")
    if len(payload) > max_bytes:
        raise StateSizeError(f"encoded state is {len(payload)} bytes over ceiling {max_bytes}")
    return payload


__all__ = [
    "MAX_STATE_BYTES_DEFAULT",
    "STATE_CODEC_MAGIC",
    "STATE_CODEC_VERSION",
    "StateCodecError",
    "StateSizeError",
    "decode_state",
    "encode_state",
    "enforce_state_size",
]
