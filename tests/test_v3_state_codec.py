"""RED/GREEN tests for the canonical packed v3 state codec (Task 6).

``encode_state`` packs a :class:`V3State` into a self-describing, versioned,
CRC-protected, zlib+base64 payload of packed float16/int16/uint8 arrays;
``decode_state`` is its exact inverse for a canonically quantized state.  Every
malformed input (wrong magic/version, CRC mismatch, truncation, non-finite
half-floats, oversize experience buffer, out-of-bounds values) must fail closed
with a typed error and never return a half-decoded state.

formula v2 deleted the SNN sub-state (``SnnState``) and the pending outcome's
STDP fields; the codec bumped to v3 and reads past a legacy v1/v2 SnnState segment
on decode.  The bounded reals that survive are the latent axes, the per-action
reward baseline, and the vestigial reuse summary.
"""

from __future__ import annotations

import base64
import struct
import zlib

import pytest

from sylanne_alpha.v3core.contracts import Action, SessionRef, TurnSequence
from sylanne_alpha.v3core.formula_v1 import FORMULA_VERSION
from sylanne_alpha.v3core.learning.label_free import prior_label_free
from sylanne_alpha.v3core.state import codec
from sylanne_alpha.v3core.state.codec import (
    STATE_CODEC_MAGIC,
    StateCodecError,
    decode_state,
    encode_state,
)
from sylanne_alpha.v3core.state.models import (
    ACTION_COUNT,
    EXPERIENCE_FEATURE_DIM,
    EXPERIENCE_REWARD_DIM,
    THETA_PARAMS,
    WORKSPACE_BROADCAST_DIM,
    ActionBeliefs,
    ExperienceRecord,
    PendingOutcome,
    STATE_SCHEMA_VERSION,
    V3State,
    BASELINE_BOUNDS,
    BASELINE_STORED_BOUNDS,
    LATENT_AXIS_BOUNDS,
    LATENT_AXIS_STORED_BOUNDS,
    SNN_SUMMARY_BOUNDS,
    SNN_SUMMARY_STORED_BOUNDS,
)
from sylanne_alpha.v3core.formula_v1 import AXIS_DIM, EXPERIENCE_CAPACITY, SNN_SUMMARY_DIM


LEGACY_FORMULA_VERSION = "sylanne.v3.formula.v1"


def _snap16(value: float) -> float:
    return struct.unpack(">e", struct.pack(">e", value))[0]


def _session_ref(generation: int = 1) -> SessionRef:
    return SessionRef(key_id="key-v1", session_digest=b"s" * 32, session_generation=generation)


def _action_beliefs() -> ActionBeliefs:
    params = AXIS_DIM * THETA_PARAMS
    return ActionBeliefs(
        theta=tuple(tuple(_snap16(0.1) for _ in range(params)) for _ in range(ACTION_COUNT)),
        sigma=tuple(tuple(_snap16(0.1) for _ in range(params)) for _ in range(ACTION_COUNT)),
        baselines=tuple(_snap16(0.0) for _ in range(ACTION_COUNT)),
        counts=tuple(3 for _ in range(ACTION_COUNT)),
    )


def _pending_outcome() -> PendingOutcome:
    return PendingOutcome(
        origin_turn_id="turn-t",
        sequence=TurnSequence(writer_epoch=7, local_sequence=11),
        action=Action.SPEAK,
        projected_actual_action=Action.HOLD,
        c=tuple(_snap16(0.1) for _ in range(AXIS_DIM)),
        v_c=tuple(_snap16(0.25) for _ in range(AXIS_DIM)),
        reward_scale=_snap16(1.0),
        preference_log_terms_before=tuple(_snap16(-0.5) for _ in range(AXIS_DIM)),
        predictive_mu_actual=tuple(_snap16(0.2) for _ in range(AXIS_DIM)),
        predictive_v_actual=tuple(_snap16(0.25) for _ in range(AXIS_DIM)),
        likelihood_r_actual=tuple(_snap16(0.20) for _ in range(AXIS_DIM)),
        expiry_sequence=TurnSequence(writer_epoch=7, local_sequence=12),
        preference_revision=FORMULA_VERSION,
        preference_digest="0" * 64,
        outcome_projector_revision=FORMULA_VERSION,
    )


def _experience(index: int) -> ExperienceRecord:
    return ExperienceRecord(
        observation_digest=struct.pack(">Q", index),
        encoded_features=tuple((index * 7 + i) % 4000 - 2000 for i in range(EXPERIENCE_FEATURE_DIM)),
        workspace_broadcast=tuple((index + i) % 3000 - 1500 for i in range(WORKSPACE_BROADCAST_DIM)),
        shadow_action_code=index % 4,
        actual_action_code=(index + 1) % 5,
        next_observation=tuple((index * 3 + i) % 256 for i in range(36)),
        reward_components=tuple((index - i) % 2000 - 1000 for i in range(EXPERIENCE_REWARD_DIM)),
        trace_revision=index + 1,
        trace_turn_digest=struct.pack(">Q", index * 2 + 1),
    )


def _worst_case_state(experience_count: int = EXPERIENCE_CAPACITY) -> V3State:
    return V3State(
        session_ref=_session_ref(),
        schema_version=STATE_SCHEMA_VERSION,
        source_digest="src-digest",
        state_generation_id="gen-worst",
        revision=123456,
        writer_epoch=99,
        session_generation=1,
        formula_version=FORMULA_VERSION,
        model_revision=FORMULA_VERSION,
        last_committed_turn_sequence=TurnSequence(writer_epoch=99, local_sequence=250),
        last_committed_turn_id="turn-worst",
        latent_axes=tuple(_snap16(0.5) for _ in range(24)),
        rho_hold=_snap16(0.5),
        rho_reach=_snap16(0.25),
        style_ring=tuple((1, 2, 3, 0) for _ in range(4)),
        action_beliefs=_action_beliefs(),
        last_snn_summary=tuple(_snap16(0.25) for _ in range(SNN_SUMMARY_DIM)),
        pending_outcome=_pending_outcome(),
        experiences=tuple(_experience(i) for i in range(experience_count)),
    )


def _rewrap(body: bytes) -> bytes:
    """Re-emit an encoded blob from raw (uncompressed) codec body bytes."""

    return base64.b64encode(zlib.compress(body))


def _unwrap(blob: bytes) -> bytes:
    return zlib.decompress(base64.b64decode(blob))


def test_encode_decode_round_trips_a_neutral_state_exactly() -> None:
    state = V3State(session_ref=_session_ref())
    assert decode_state(encode_state(state)) == state


def test_encode_decode_round_trips_a_worst_case_state_exactly() -> None:
    state = _worst_case_state()
    blob = encode_state(state)
    restored = decode_state(blob)
    assert restored == state
    assert restored.action_beliefs == state.action_beliefs
    assert restored.pending_outcome == state.pending_outcome
    assert len(restored.experiences) == EXPERIENCE_CAPACITY
    assert restored.experiences == state.experiences


def test_encoding_is_deterministic() -> None:
    state = _worst_case_state()
    assert encode_state(state) == encode_state(state)


def test_decode_rejects_a_corrupt_magic() -> None:
    body = _unwrap(encode_state(V3State(session_ref=_session_ref())))
    assert body[: len(STATE_CODEC_MAGIC)] == STATE_CODEC_MAGIC
    tampered = b"XXXX" + body[4:]
    with pytest.raises(StateCodecError):
        decode_state(_rewrap(tampered))


def test_decode_rejects_a_wrong_version() -> None:
    body = bytearray(_unwrap(encode_state(V3State(session_ref=_session_ref()))))
    offset = len(STATE_CODEC_MAGIC)
    body[offset] = body[offset] ^ 0xFF
    with pytest.raises(StateCodecError):
        decode_state(_rewrap(bytes(body)))


def test_decode_rejects_a_crc_mismatch() -> None:
    body = bytearray(_unwrap(encode_state(_worst_case_state())))
    # Flip a byte in the packed payload (before the trailing CRC word).
    body[len(body) // 2] ^= 0x01
    with pytest.raises(StateCodecError):
        decode_state(_rewrap(bytes(body)))


def test_decode_rejects_truncated_and_trailing_garbage_payloads() -> None:
    blob = encode_state(_worst_case_state())
    body = _unwrap(blob)
    with pytest.raises(StateCodecError):
        decode_state(_rewrap(body[:-4]))
    with pytest.raises(StateCodecError):
        decode_state(_rewrap(body + b"\x00\x00\x00\x00"))


def test_decode_rejects_non_base64_and_non_zlib_containers() -> None:
    with pytest.raises(StateCodecError):
        decode_state(b"not base64 !!!")
    with pytest.raises(StateCodecError):
        decode_state(base64.b64encode(b"not a zlib stream"))


def test_decode_rejects_non_finite_half_floats() -> None:
    state = _worst_case_state()
    body = bytearray(_unwrap(encode_state(state)))
    half_inf = struct.pack(">e", float("inf"))
    # The last_snn_summary block is a run of repeated 0.25 half-floats; that pattern
    # only appears there, so it targets a float region unambiguously.  (latent_axes is
    # now float32, so a float16 run no longer lives there.)
    summary_run = struct.pack(">e", _snap16(0.25)) * 6
    index = body.find(summary_run)
    assert index != -1
    body[index : index + 2] = half_inf
    with pytest.raises(StateCodecError):
        decode_state(_rewrap(bytes(body)))


# --------------------------------------------------------------------------- #
# v1/v2 -> v3 read migration: legacy SnnState segment + STDP pending fields are
# read past and discarded (the SNN no longer exists), the rest decodes unchanged.
# --------------------------------------------------------------------------- #


def _legacy_string(value: str) -> bytes:
    data = value.encode("utf-8")
    return struct.pack(">H", len(data)) + data


def _legacy_v2_blob(*, with_pending: bool) -> bytes:
    """Hand-build a v2 codec blob (SnnState segment present, legacy pending layout).

    Mirrors the pre-formula-v2 on-disk format exactly so ``decode_state`` exercises
    its migration path: version 2, a present 96-neuron SnnState segment, and (when
    ``with_pending``) a pending outcome carrying the removed ``stdp_credit_enabled``
    byte and ``packed_eligibility`` block.
    """

    import binascii

    body = b"SYL3ST" + struct.pack(">H", 2)
    # header
    body += struct.pack(">H", 1)  # schema_version
    body += struct.pack(">Q", 0)  # revision
    body += struct.pack(">Q", 0)  # writer_epoch
    body += struct.pack(">Q", 0)  # session_generation (state header)
    body += _legacy_string("key-v1")  # session_ref.key_id
    body += b"s" * 32  # session_digest
    body += struct.pack(">Q", 1)  # session_ref.session_generation
    body += _legacy_string(LEGACY_FORMULA_VERSION)  # formula_version
    body += _legacy_string("")  # source_digest
    body += _legacy_string("")  # state_generation_id
    body += _legacy_string(LEGACY_FORMULA_VERSION)  # model_revision
    body += struct.pack(">B", 0)  # last_committed_turn_id: None
    body += struct.pack(">B", 0)  # last_committed_turn_sequence: None
    # continuous (v2: latent as float32)
    body += struct.pack(">24f", *([0.0] * 24))
    body += struct.pack(">e", 0.0)  # rho_hold
    body += struct.pack(">e", 0.0)  # rho_reach
    body += struct.pack(">B", 0)  # style_ring count
    # legacy SnnState segment: present, 96-neuron half-float arrays + plastic block
    body += struct.pack(">B", 1)  # snn present
    for _ in range(4):  # voltages / thresholds / pre_trace / post_trace
        body += struct.pack(">96e", *([0.0] * 96))
    plastic = 5  # arbitrary legacy plastic count; the migration only reads-and-skips it
    body += struct.pack(">I", plastic)
    body += struct.pack(">%de" % plastic, *([0.0] * plastic))  # plastic_weights
    body += struct.pack(">%de" % plastic, *([0.0] * plastic))  # eligibility
    body += struct.pack(">B", 0)  # beliefs: None
    body += struct.pack(">B", 0)  # summary: None
    if with_pending:
        body += struct.pack(">B", 1)  # pending present
        body += _legacy_string("turn-legacy")
        body += struct.pack(">Q", 7) + struct.pack(">Q", 11)  # sequence
        body += struct.pack(">B", 0)  # action = SPEAK
        body += struct.pack(">B", 1)  # projected_actual_action = HOLD
        body += struct.pack(">B", 1)  # legacy stdp_credit_enabled = True
        for _ in range(6):  # c / v_c / pref_log / mu / v / r each: len 8 + 8 half-floats
            body += struct.pack(">B", 8) + struct.pack(">8e", *([0.0] * 8))
        body += struct.pack(">e", 1.0)  # reward_scale
        body += struct.pack(">B", 1)  # legacy packed_eligibility present
        body += struct.pack(">I", plastic) + struct.pack(">%de" % plastic, *([0.0] * plastic))
        body += struct.pack(">B", 0)  # expiry_sequence: None
        body += _legacy_string(LEGACY_FORMULA_VERSION)  # preference_revision
        body += _legacy_string("0" * 64)  # preference_digest
        body += _legacy_string(LEGACY_FORMULA_VERSION)  # outcome_projector_revision
    else:
        body += struct.pack(">B", 0)  # pending: None
    body += struct.pack(">H", 0)  # experiences count
    framed = body + struct.pack(">I", binascii.crc32(body) & 0xFFFFFFFF)
    return base64.b64encode(zlib.compress(framed, 9))


def test_legacy_v2_blob_migrates_by_discarding_the_snn_segment() -> None:
    decoded = decode_state(_legacy_v2_blob(with_pending=False))
    # The SnnState segment is gone and the absent label-free segment migrates to
    # None; codec4 upgrades the legacy schema/formula header before exposing the
    # state, so no current producer can accidentally re-emit a v1 header.
    assert decoded == V3State(session_ref=_session_ref())
    assert decoded.schema_version == STATE_SCHEMA_VERSION == 2
    assert decoded.formula_version == FORMULA_VERSION == "sylanne.v3.formula.v2"
    assert decoded.model_revision == FORMULA_VERSION
    assert decoded.label_free is None
    assert not hasattr(decoded, "snn")
    # The next encode emits the current (v4) version and round-trips.
    assert decode_state(encode_state(decoded)) == decoded


def test_codec4_encoder_refuses_label_free_state_under_a_legacy_header() -> None:
    inconsistent = V3State(
        session_ref=_session_ref(),
        schema_version=1,
        formula_version=LEGACY_FORMULA_VERSION,
        model_revision=LEGACY_FORMULA_VERSION,
        label_free=prior_label_free(),
    )

    with pytest.raises(StateCodecError, match="current schema/formula"):
        encode_state(inconsistent)


def test_legacy_v2_pending_migrates_by_discarding_stdp_fields() -> None:
    decoded = decode_state(_legacy_v2_blob(with_pending=True))
    pending = decoded.pending_outcome
    assert pending is not None
    assert pending.origin_turn_id == "turn-legacy"
    assert pending.action is Action.SPEAK
    assert pending.projected_actual_action is Action.HOLD
    assert pending.c == tuple(0.0 for _ in range(AXIS_DIM))
    assert pending.reward_scale == 1.0
    assert pending.preference_digest == "0" * 64
    # A pre-v4 pending record has no eligibility bit; it migrates to False缺省.
    assert pending.label_free_eligible is False
    # The removed STDP fields do not resurface on the migrated record.
    assert not hasattr(pending, "stdp_credit_enabled")
    assert not hasattr(pending, "packed_eligibility")
    # A migrated state round-trips as v4.
    assert decode_state(encode_state(decoded)) == decoded


def test_v3state_rejects_more_than_the_capacity_of_experiences() -> None:
    with pytest.raises(ValueError):
        _worst_case_state(experience_count=EXPERIENCE_CAPACITY + 1)


def test_experience_record_rejects_out_of_range_quantized_values() -> None:
    with pytest.raises(ValueError):
        ExperienceRecord(
            observation_digest=b"\x00" * 8,
            encoded_features=tuple(0 for _ in range(EXPERIENCE_FEATURE_DIM)),
            workspace_broadcast=tuple(0 for _ in range(WORKSPACE_BROADCAST_DIM)),
            shadow_action_code=0,
            actual_action_code=0,
            next_observation=tuple(999 for _ in range(36)),  # u8 overflow
            reward_components=tuple(0 for _ in range(EXPERIENCE_REWARD_DIM)),
            trace_revision=1,
            trace_turn_digest=b"\x00" * 8,
        )


# --------------------------------------------------------------------------- #
# Quantization-safe bounds (回溯红队 a16: quantization IS persistence)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("corner", ["low", "high"])
def test_a_state_clamped_to_any_bound_survives_a_round_trip(corner: str) -> None:
    """The a16 DoD: decode(encode(x)) holds for ANY state legally clamped to a bound.

    formula v2 deleted the SNN scalar bounds (0.65 threshold floor / 0.35 plastic
    ceiling) whose float16 image originally triggered the STATE_QUANTIZE_ERROR
    livelock, so that specific reload fork can no longer occur.  The surviving bounded
    reals -- latent axes (float32), the per-action reward baseline, and the vestigial
    reuse summary -- are validated on the same quantization-safe grid, and a state
    clamped to any of their bounds must still round-trip to a fixed point.
    """

    index = 0 if corner == "low" else 1
    params = AXIS_DIM * THETA_PARAMS
    state = V3State(
        session_ref=_session_ref(),
        latent_axes=tuple(LATENT_AXIS_BOUNDS[index] for _ in range(24)),
        last_snn_summary=tuple(SNN_SUMMARY_BOUNDS[index] for _ in range(SNN_SUMMARY_DIM)),
        action_beliefs=ActionBeliefs(
            theta=tuple(tuple(0.0 for _ in range(params)) for _ in range(ACTION_COUNT)),
            sigma=tuple(tuple(_snap16(0.1) for _ in range(params)) for _ in range(ACTION_COUNT)),
            baselines=tuple(BASELINE_BOUNDS[index] for _ in range(ACTION_COUNT)),
            counts=tuple(0 for _ in range(ACTION_COUNT)),
        ),
    )
    blob = encode_state(state)
    restored = decode_state(blob)  # must not raise
    # Reloading is a fixed point: the grid value re-encodes to the same bytes, so a
    # crash reload can never fork the trajectory.
    assert encode_state(restored) == blob
    assert restored == state  # all these bounds are exactly representable on the grid


def test_continuous_payload_bounds_match_the_code_that_clamps_them() -> None:
    """latent/baselines/summary are pinned to the bound their own producer enforces,
    so a grossly out-of-range value fails closed instead of validating as if in band.
    """

    assert LATENT_AXIS_BOUNDS == (-1.0, 1.0)  # design 9 / dynamics.multiscale._clip_unit
    assert BASELINE_BOUNDS == (-1.0, 1.0)  # per-action reward EMA (learning.outcomes.update_baseline)
    assert SNN_SUMMARY_BOUNDS == (0.0, 1.0)  # vestigial reuse summary (always None now)
    # All three sit exactly on the float16 grid, so the storage widening is a no-op:
    # the tightening costs no quantization margin.
    assert LATENT_AXIS_STORED_BOUNDS == LATENT_AXIS_BOUNDS
    assert BASELINE_STORED_BOUNDS == BASELINE_BOUNDS
    assert SNN_SUMMARY_STORED_BOUNDS == SNN_SUMMARY_BOUNDS


def test_out_of_band_latent_baselines_and_summary_now_fail_closed() -> None:
    ref = _session_ref()
    with pytest.raises(ValueError):  # 2.0 validated fine under the old (-16,16)
        V3State(session_ref=ref, latent_axes=tuple(2.0 for _ in range(24)))
    with pytest.raises(ValueError):
        V3State(session_ref=ref, last_snn_summary=tuple(1.5 for _ in range(SNN_SUMMARY_DIM)))
    with pytest.raises(ValueError):
        V3State(session_ref=ref, last_snn_summary=tuple(-0.5 for _ in range(SNN_SUMMARY_DIM)))
    with pytest.raises(ValueError):
        ActionBeliefs(
            theta=tuple(tuple(0.0 for _ in range(AXIS_DIM * THETA_PARAMS)) for _ in range(ACTION_COUNT)),
            sigma=tuple(tuple(0.5 for _ in range(AXIS_DIM * THETA_PARAMS)) for _ in range(ACTION_COUNT)),
            baselines=tuple(3.0 for _ in range(ACTION_COUNT)),
            counts=tuple(0 for _ in range(ACTION_COUNT)),
        )
    # ...while the legal extremes the producers really emit still construct.
    V3State(session_ref=ref, latent_axes=tuple(1.0 for _ in range(24)))
    V3State(session_ref=ref, last_snn_summary=tuple(1.0 for _ in range(SNN_SUMMARY_DIM)))
