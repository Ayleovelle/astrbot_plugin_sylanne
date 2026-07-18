"""Deterministic byte codec and digest helpers for :class:`CoreDecisionTrace`.

The canonical trace is a single self-describing byte string::

    base64( MAGIC || version || packed-fields || CRC32 )

Field order, enum spelling, array shape, endianness, and packed-number
representation are all fixed (design section 16.2).  Required fixed-shape numeric
values are packed as big-endian IEEE-754 doubles (``>d``) so byte-identical
replay reproduces them losslessly; counts and per-neuron integers use big-endian
signed 32-bit words (``>i``).  ``canonical_trace_bytes`` is deterministic and
``decode_trace_bytes`` is its exact inverse.

Digest dependencies are one-way (design section 13): ``payload_digest`` is a pure
function of the cognitive payload; the trace may embed that digest but never its
own; ``trace_digest`` hashes the trace bytes; and ``journal_digest`` closes over
both and lives only in the pointer/index envelope.

Only stdlib ``struct``/``zlib``/``base64``/``binascii``/``hashlib`` are imported,
honoring the ``v3core`` import firewall.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import struct
from math import isfinite

from ..formula_v1 import AXIS_DIM, OBSERVATION_DIM, SNN_NEURONS, SNN_SUMMARY_DIM, STATE_DIM
from .models import TRACE_SCHEMA_VERSION, CoreDecisionTrace


TRACE_CODEC_MAGIC = b"SYL3TR"
TRACE_CODEC_VERSION = 1
# Design section 16.2: a worst-case legal trace serializes to at most 16 KiB.
# The bridge's ``limits.MAX_TRACE_BYTES`` holds the same constant; the pure core
# owns its own copy so it never imports the bridge.
TRACE_HARD_CAP_BYTES = 16 * 1024

_JOURNAL_DOMAIN = b"SYL3\x01JOURNAL\x00"


class TraceOverflowError(ValueError):
    """Raised when a complete canonical trace exceeds the 16 KiB hard cap."""


class TraceCodecError(ValueError):
    """Raised for any malformed encoded trace; never returns a partial trace."""


# --------------------------------------------------------------------------- #
# Writer / reader
# --------------------------------------------------------------------------- #


class _TW:
    __slots__ = ("_chunks",)

    def __init__(self) -> None:
        self._chunks: list[bytes] = []

    def u8(self, value: int) -> None:
        self._chunks.append(struct.pack(">B", value))

    def u16(self, value: int) -> None:
        self._chunks.append(struct.pack(">H", value))

    def u64(self, value: int) -> None:
        self._chunks.append(struct.pack(">Q", value))

    def i32(self, value: int) -> None:
        self._chunks.append(struct.pack(">i", value))

    def f64(self, value: float) -> None:
        if not isfinite(value):
            raise TraceCodecError("trace floats must be finite")
        self._chunks.append(struct.pack(">d", value))

    def boolean(self, value: bool) -> None:
        self._chunks.append(struct.pack(">B", 1 if value else 0))

    def string(self, value: str) -> None:
        data = value.encode("utf-8")
        if len(data) > 0xFFFF:
            raise TraceCodecError("trace string field exceeds 16-bit length")
        self._chunks.append(struct.pack(">H", len(data)))
        self._chunks.append(data)

    def blob(self, value: bytes) -> None:
        if len(value) > 0xFFFF:
            raise TraceCodecError("trace bytes field exceeds 16-bit length")
        self._chunks.append(struct.pack(">H", len(value)))
        self._chunks.append(value)

    def f64_fixed(self, values: tuple) -> None:
        for value in values:
            self.f64(value)

    def i32_fixed(self, values: tuple) -> None:
        for value in values:
            self.i32(value)

    def f64_vec(self, values: tuple) -> None:
        self.u16(len(values))
        for value in values:
            self.f64(value)

    def i32_vec(self, values: tuple) -> None:
        self.u16(len(values))
        for value in values:
            self.i32(value)

    def string_vec(self, values: tuple) -> None:
        self.u16(len(values))
        for value in values:
            self.string(value)

    def pair_vec(self, values: tuple) -> None:
        self.u16(len(values))
        for name, value in values:
            self.string(name)
            self.f64(value)

    def getvalue(self) -> bytes:
        return b"".join(self._chunks)


class _TR:
    __slots__ = ("_data", "_offset")

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._offset = 0

    def _take(self, count: int) -> bytes:
        end = self._offset + count
        if end > len(self._data):
            raise TraceCodecError("encoded trace truncated")
        chunk = self._data[self._offset : end]
        self._offset = end
        return chunk

    def remaining(self) -> int:
        return len(self._data) - self._offset

    def u8(self) -> int:
        return struct.unpack(">B", self._take(1))[0]

    def u16(self) -> int:
        return struct.unpack(">H", self._take(2))[0]

    def u64(self) -> int:
        return struct.unpack(">Q", self._take(8))[0]

    def i32(self) -> int:
        return struct.unpack(">i", self._take(4))[0]

    def f64(self) -> float:
        value = struct.unpack(">d", self._take(8))[0]
        if not isfinite(value):
            raise TraceCodecError("encoded trace contains a non-finite double")
        return value

    def boolean(self) -> bool:
        return self.u8() == 1

    def string(self) -> str:
        length = self.u16()
        try:
            return self._take(length).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TraceCodecError("invalid utf-8 trace string") from exc

    def blob(self) -> bytes:
        return self._take(self.u16())

    def f64_fixed(self, count: int) -> tuple:
        return tuple(self.f64() for _ in range(count))

    def i32_fixed(self, count: int) -> tuple:
        return tuple(self.i32() for _ in range(count))

    def f64_vec(self) -> tuple:
        return tuple(self.f64() for _ in range(self.u16()))

    def i32_vec(self) -> tuple:
        return tuple(self.i32() for _ in range(self.u16()))

    def string_vec(self) -> tuple:
        return tuple(self.string() for _ in range(self.u16()))

    def pair_vec(self) -> tuple:
        return tuple((self.string(), self.f64()) for _ in range(self.u16()))


# --------------------------------------------------------------------------- #
# Encode
# --------------------------------------------------------------------------- #


def _pack_body(trace: CoreDecisionTrace) -> bytes:
    w = _TW()
    w.u8(len(TRACE_CODEC_MAGIC))
    # identity / revisions / digests
    w.u16(trace.schema_version)
    w.string(trace.turn_id)
    w.u64(trace.writer_epoch)
    w.u64(trace.local_sequence)
    w.string(trace.formula_version)
    w.string(trace.formula_digest)
    w.string(trace.model_revision)
    w.string(trace.state_generation_id)
    w.string(trace.source_digest)
    w.u64(trace.base_revision)
    w.u64(trace.next_revision)
    w.string(trace.input_digest)
    w.string(trace.payload_digest)
    # compute profile
    w.string(trace.profile_id)
    w.boolean(trace.profile_snn_enabled)
    w.u64(trace.profile_ticks)
    w.boolean(trace.profile_stdp_enabled)
    w.boolean(trace.profile_reuse_last_summary)
    w.string(trace.math_backend)
    w.string(trace.profile_digest)
    w.blob(trace.seed)
    # deterministic / continuous
    w.f64_fixed(trace.observation_values)
    w.u64(trace.observation_valid_mask)
    w.f64_fixed(trace.decision_state)
    w.f64_fixed(trace.drive)
    w.f64_fixed(trace.next_latent_axes)
    w.boolean(trace.dynamics_advanced)
    # SNN
    w.boolean(trace.snn_ran)
    w.boolean(trace.snn_rolled_back)
    w.boolean(trace.snn_summary_valid)
    w.f64(trace.weight_saturation)
    w.i32_fixed(trace.spike_counts)
    w.i32_fixed(trace.first_latencies)
    w.f64_fixed(trace.snn_summary)
    # workspace
    w.string(trace.workspace_mode)
    w.string_vec(trace.proposal_ids)
    w.i32_fixed(trace.proposal_sources)
    w.f64_fixed(trace.proposal_salience)
    w.f64_fixed(trace.proposal_confidence)
    w.f64_fixed(trace.activation)
    w.f64_fixed(trace.inhibition)
    w.f64_fixed(trace.effective_salience)
    w.string_vec(trace.broadcast_ids)
    w.pair_vec(trace.support)
    w.pair_vec(trace.log_evidence)
    w.f64_fixed(trace.source_refractory_next)
    # inference
    w.string_vec(trace.candidate_actions)
    for row in trace.candidate_mu:
        w.f64_fixed(row)
    for row in trace.candidate_predictive_var:
        w.f64_fixed(row)
    w.f64_fixed(trace.candidate_prior_log)
    w.f64_fixed(trace.candidate_workspace_evidence)
    w.f64_fixed(trace.candidate_refractory)
    w.f64_fixed(trace.candidate_risk)
    w.f64_fixed(trace.candidate_ambiguity)
    w.f64_fixed(trace.candidate_information_gain)
    w.f64_fixed(trace.candidate_expected_free_energy)
    w.f64_fixed(trace.candidate_logit)
    w.f64_fixed(trace.candidate_posterior)
    w.string(trace.selected_action)
    w.f64(trace.policy_confidence)
    # refractory
    w.f64(trace.rho_hold_before)
    w.f64(trace.rho_reach_before)
    w.f64(trace.rho_hold_after)
    w.f64(trace.rho_reach_after)
    # expression
    w.string(trace.length_bucket)
    w.f64(trace.pace)
    w.f64(trace.directness)
    w.f64(trace.warmth)
    w.boolean(trace.hesitation)
    w.i32_fixed(trace.style_signature)
    # decision comparison / degradation
    w.string(trace.shadow_action)
    w.string(trace.actual_action)
    w.boolean(trace.disagreement)
    w.string(trace.disagreement_reason)
    w.string(trace.degradation_reason)
    # formula v2 label-free reaction learning (spec §4.3)
    w.f64(trace.r_react)
    w.boolean(trace.reaction_valid)
    w.string(trace.lf_censor_reason)
    w.f64_fixed(trace.pref_offset_after)
    w.f64_fixed(trace.marginal_mu)
    return w.getvalue()


def canonical_trace_bytes(trace: CoreDecisionTrace) -> bytes:
    """Serialize a trace into its deterministic base64/packed canonical bytes."""

    if type(trace) is not CoreDecisionTrace:
        raise TraceCodecError("canonical_trace_bytes requires a CoreDecisionTrace")
    body = TRACE_CODEC_MAGIC + struct.pack(">H", TRACE_CODEC_VERSION) + _pack_body(trace)
    framed = body + struct.pack(">I", binascii.crc32(body) & 0xFFFFFFFF)
    return base64.b64encode(framed)


def trace_digest_hex(trace_bytes: bytes) -> str:
    """Return the lowercase SHA-256 digest of the canonical trace bytes."""

    if type(trace_bytes) is not bytes:
        raise TraceCodecError("trace_digest_hex requires bytes")
    return hashlib.sha256(trace_bytes).hexdigest()


def compute_journal_digest(
    payload_digest: str,
    payload_len: int,
    trace_digest: str,
    trace_len: int,
) -> str:
    """Length-framed digest over the repository envelope (payload -> trace -> journal).

    The journal digest closes over both the cognitive payload and the trace
    digests; it lives only in the pointer/index envelope and is never embedded in
    the payload, trace, or migration receipt (design section 13/15.1).
    """

    for name, value in (("payload_digest", payload_digest), ("trace_digest", trace_digest)):
        if type(value) is not str:
            raise TypeError(f"{name} must be a hex string")
    for name, value in (("payload_len", payload_len), ("trace_len", trace_len)):
        if type(value) is not int or type(value) is bool or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")

    def framed(chunk: bytes) -> bytes:
        return struct.pack(">I", len(chunk)) + chunk

    material = (
        _JOURNAL_DOMAIN
        + framed(payload_digest.encode("utf-8"))
        + framed(struct.pack(">Q", payload_len))
        + framed(trace_digest.encode("utf-8"))
        + framed(struct.pack(">Q", trace_len))
    )
    return hashlib.sha256(material).hexdigest()


# --------------------------------------------------------------------------- #
# Decode (exact inverse; used by replay/round-trip verification)
# --------------------------------------------------------------------------- #


def decode_trace_bytes(blob: object) -> CoreDecisionTrace:
    """Decode canonical trace bytes back into an exact :class:`CoreDecisionTrace`."""

    if type(blob) is not bytes:
        raise TraceCodecError("decode_trace_bytes requires bytes")
    try:
        framed = base64.b64decode(blob, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise TraceCodecError("invalid base64 trace container") from exc
    if len(framed) < len(TRACE_CODEC_MAGIC) + 2 + 4:
        raise TraceCodecError("encoded trace too short")
    body, crc_bytes = framed[:-4], framed[-4:]
    if struct.unpack(">I", crc_bytes)[0] != (binascii.crc32(body) & 0xFFFFFFFF):
        raise TraceCodecError("trace CRC mismatch")

    if body[: len(TRACE_CODEC_MAGIC)] != TRACE_CODEC_MAGIC:
        raise TraceCodecError("bad trace magic")
    version = struct.unpack(">H", body[len(TRACE_CODEC_MAGIC) : len(TRACE_CODEC_MAGIC) + 2])[0]
    if version != TRACE_CODEC_VERSION:
        raise TraceCodecError("unsupported trace codec version")

    r = _TR(body[len(TRACE_CODEC_MAGIC) + 2 :])
    if r.u8() != len(TRACE_CODEC_MAGIC):
        raise TraceCodecError("bad trace framing")

    schema_version = r.u16()
    turn_id = r.string()
    writer_epoch = r.u64()
    local_sequence = r.u64()
    formula_version = r.string()
    formula_digest = r.string()
    model_revision = r.string()
    state_generation_id = r.string()
    source_digest = r.string()
    base_revision = r.u64()
    next_revision = r.u64()
    input_digest = r.string()
    payload_digest = r.string()
    profile_id = r.string()
    profile_snn_enabled = r.boolean()
    profile_ticks = r.u64()
    profile_stdp_enabled = r.boolean()
    profile_reuse_last_summary = r.boolean()
    math_backend = r.string()
    profile_digest = r.string()
    seed = r.blob()
    observation_values = r.f64_fixed(OBSERVATION_DIM)
    observation_valid_mask = r.u64()
    decision_state = r.f64_fixed(AXIS_DIM)
    drive = r.f64_fixed(AXIS_DIM)
    next_latent_axes = r.f64_fixed(STATE_DIM)
    dynamics_advanced = r.boolean()
    snn_ran = r.boolean()
    snn_rolled_back = r.boolean()
    snn_summary_valid = r.boolean()
    weight_saturation = r.f64()
    spike_counts = r.i32_fixed(SNN_NEURONS)
    first_latencies = r.i32_fixed(SNN_NEURONS)
    snn_summary = r.f64_fixed(SNN_SUMMARY_DIM)
    workspace_mode = r.string()
    proposal_ids = r.string_vec()
    proposal_count = len(proposal_ids)
    proposal_sources = r.i32_fixed(proposal_count)
    proposal_salience = r.f64_fixed(proposal_count)
    proposal_confidence = r.f64_fixed(proposal_count)
    activation = r.f64_fixed(proposal_count)
    inhibition = r.f64_fixed(proposal_count)
    effective_salience = r.f64_fixed(proposal_count)
    broadcast_ids = r.string_vec()
    support = r.pair_vec()
    log_evidence = r.pair_vec()
    source_refractory_next = r.f64_fixed(8)
    candidate_actions = r.string_vec()
    candidate_count = len(candidate_actions)
    candidate_mu = tuple(r.f64_fixed(AXIS_DIM) for _ in range(candidate_count))
    candidate_predictive_var = tuple(r.f64_fixed(AXIS_DIM) for _ in range(candidate_count))
    candidate_prior_log = r.f64_fixed(candidate_count)
    candidate_workspace_evidence = r.f64_fixed(candidate_count)
    candidate_refractory = r.f64_fixed(candidate_count)
    candidate_risk = r.f64_fixed(candidate_count)
    candidate_ambiguity = r.f64_fixed(candidate_count)
    candidate_information_gain = r.f64_fixed(candidate_count)
    candidate_expected_free_energy = r.f64_fixed(candidate_count)
    candidate_logit = r.f64_fixed(candidate_count)
    candidate_posterior = r.f64_fixed(candidate_count)
    selected_action = r.string()
    policy_confidence = r.f64()
    rho_hold_before = r.f64()
    rho_reach_before = r.f64()
    rho_hold_after = r.f64()
    rho_reach_after = r.f64()
    length_bucket = r.string()
    pace = r.f64()
    directness = r.f64()
    warmth = r.f64()
    hesitation = r.boolean()
    style_signature = r.i32_fixed(4)
    shadow_action = r.string()
    actual_action = r.string()
    disagreement = r.boolean()
    disagreement_reason = r.string()
    degradation_reason = r.string()
    r_react = r.f64()
    reaction_valid = r.boolean()
    lf_censor_reason = r.string()
    pref_offset_after = r.f64_fixed(AXIS_DIM)
    marginal_mu = r.f64_fixed(AXIS_DIM)
    if r.remaining() != 0:
        raise TraceCodecError("trailing bytes after encoded trace")

    try:
        return CoreDecisionTrace(
            schema_version=schema_version,
            turn_id=turn_id,
            writer_epoch=writer_epoch,
            local_sequence=local_sequence,
            formula_version=formula_version,
            formula_digest=formula_digest,
            model_revision=model_revision,
            state_generation_id=state_generation_id,
            source_digest=source_digest,
            base_revision=base_revision,
            next_revision=next_revision,
            input_digest=input_digest,
            payload_digest=payload_digest,
            profile_id=profile_id,
            profile_snn_enabled=profile_snn_enabled,
            profile_ticks=profile_ticks,
            profile_stdp_enabled=profile_stdp_enabled,
            profile_reuse_last_summary=profile_reuse_last_summary,
            math_backend=math_backend,
            profile_digest=profile_digest,
            seed=seed,
            observation_values=observation_values,
            observation_valid_mask=observation_valid_mask,
            decision_state=decision_state,
            drive=drive,
            next_latent_axes=next_latent_axes,
            dynamics_advanced=dynamics_advanced,
            snn_ran=snn_ran,
            snn_rolled_back=snn_rolled_back,
            snn_summary_valid=snn_summary_valid,
            weight_saturation=weight_saturation,
            spike_counts=spike_counts,
            first_latencies=first_latencies,
            snn_summary=snn_summary,
            workspace_mode=workspace_mode,
            proposal_ids=proposal_ids,
            proposal_sources=proposal_sources,
            proposal_salience=proposal_salience,
            proposal_confidence=proposal_confidence,
            activation=activation,
            inhibition=inhibition,
            effective_salience=effective_salience,
            broadcast_ids=broadcast_ids,
            support=support,
            log_evidence=log_evidence,
            source_refractory_next=source_refractory_next,
            candidate_actions=candidate_actions,
            candidate_mu=candidate_mu,
            candidate_predictive_var=candidate_predictive_var,
            candidate_prior_log=candidate_prior_log,
            candidate_workspace_evidence=candidate_workspace_evidence,
            candidate_refractory=candidate_refractory,
            candidate_risk=candidate_risk,
            candidate_ambiguity=candidate_ambiguity,
            candidate_information_gain=candidate_information_gain,
            candidate_expected_free_energy=candidate_expected_free_energy,
            candidate_logit=candidate_logit,
            candidate_posterior=candidate_posterior,
            selected_action=selected_action,
            policy_confidence=policy_confidence,
            rho_hold_before=rho_hold_before,
            rho_reach_before=rho_reach_before,
            rho_hold_after=rho_hold_after,
            rho_reach_after=rho_reach_after,
            length_bucket=length_bucket,
            pace=pace,
            directness=directness,
            warmth=warmth,
            hesitation=hesitation,
            style_signature=style_signature,
            shadow_action=shadow_action,
            actual_action=actual_action,
            disagreement=disagreement,
            disagreement_reason=disagreement_reason,
            degradation_reason=degradation_reason,
            r_react=r_react,
            reaction_valid=reaction_valid,
            lf_censor_reason=lf_censor_reason,
            pref_offset_after=pref_offset_after,
            marginal_mu=marginal_mu,
        )
    except (ValueError, TypeError) as exc:
        raise TraceCodecError(str(exc)) from exc


__all__ = [
    "TRACE_CODEC_MAGIC",
    "TRACE_CODEC_VERSION",
    "TRACE_HARD_CAP_BYTES",
    "TraceCodecError",
    "TraceOverflowError",
    "canonical_trace_bytes",
    "compute_journal_digest",
    "decode_trace_bytes",
    "trace_digest_hex",
]
