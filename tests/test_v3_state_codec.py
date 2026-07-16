"""RED/GREEN tests for the canonical packed v3 state codec (Task 6).

``encode_state`` packs a :class:`V3State` into a self-describing, versioned,
CRC-protected, zlib+base64 payload of packed float16/int16/uint8 arrays;
``decode_state`` is its exact inverse for a canonically quantized state.  Every
malformed input (wrong magic/version, CRC mismatch, truncation, non-finite
half-floats, Dale-violating SNN weights, oversize experience buffer) must fail
closed with a typed error and never return a half-decoded state.
"""

from __future__ import annotations

import base64
import struct
import zlib

import pytest

from sylanne_alpha.v3core.contracts import Action, SessionRef, TurnSequence
from sylanne_alpha.v3core.formula_v1 import FORMULA_VERSION
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
    PLASTIC_SYNAPSE_COUNT,
    SNN_NEURON_COUNT,
    THETA_PARAMS,
    WORKSPACE_BROADCAST_DIM,
    ActionBeliefs,
    ExperienceRecord,
    PendingOutcome,
    SnnState,
    V3State,
)
from sylanne_alpha.v3core.formula_v1 import AXIS_DIM, EXPERIENCE_CAPACITY, SNN_SUMMARY_DIM


def _snap16(value: float) -> float:
    return struct.unpack(">e", struct.pack(">e", value))[0]


def _session_ref(generation: int = 1) -> SessionRef:
    return SessionRef(key_id="key-v1", session_digest=b"s" * 32, session_generation=generation)


def _snn_state(weight: float = 0.3125) -> SnnState:  # 5/16 is exact in float16 and unique here
    n = SNN_NEURON_COUNT
    p = PLASTIC_SYNAPSE_COUNT
    return SnnState(
        voltages=tuple(_snap16(0.25) for _ in range(n)),
        thresholds=tuple(_snap16(1.0) for _ in range(n)),
        pre_trace=tuple(_snap16(0.5) for _ in range(n)),
        post_trace=tuple(_snap16(0.5) for _ in range(n)),
        plastic_weights=tuple(_snap16(weight) for _ in range(p)),
        eligibility=tuple(_snap16(0.5) for _ in range(p)),
    )


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
        stdp_credit_enabled=True,
        c=tuple(_snap16(0.1) for _ in range(AXIS_DIM)),
        v_c=tuple(_snap16(0.25) for _ in range(AXIS_DIM)),
        reward_scale=_snap16(1.0),
        preference_log_terms_before=tuple(_snap16(-0.5) for _ in range(AXIS_DIM)),
        predictive_mu_actual=tuple(_snap16(0.2) for _ in range(AXIS_DIM)),
        predictive_v_actual=tuple(_snap16(0.25) for _ in range(AXIS_DIM)),
        likelihood_r_actual=tuple(_snap16(0.20) for _ in range(AXIS_DIM)),
        packed_eligibility=tuple(_snap16(0.3) for _ in range(PLASTIC_SYNAPSE_COUNT)),
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
        schema_version=1,
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
        snn=_snn_state(),
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
    assert restored.snn == state.snn
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
    # The 24-axis latent block is a long run of repeated 0.5 half-floats; that
    # pattern only appears there, so it targets a float region unambiguously.
    latent_run = struct.pack(">e", _snap16(0.5)) * 6
    index = body.find(latent_run)
    assert index != -1
    body[index : index + 2] = half_inf
    with pytest.raises(StateCodecError):
        decode_state(_rewrap(bytes(body)))


def test_decode_rejects_dale_violating_plastic_weights() -> None:
    state = _worst_case_state()
    body = bytearray(_unwrap(encode_state(state)))
    # 0.3125 is used only for plastic weights, so this uniquely targets one.
    positive = struct.pack(">e", _snap16(0.3125))
    negative = struct.pack(">e", _snap16(-0.3125))
    index = body.rfind(positive)
    assert index != -1
    body[index : index + 2] = negative
    with pytest.raises(StateCodecError):
        decode_state(_rewrap(bytes(body)))


def test_snn_state_construction_enforces_dale_and_bounds() -> None:
    good = _snn_state()
    with pytest.raises(ValueError):
        SnnState(
            voltages=good.voltages,
            thresholds=good.thresholds,
            pre_trace=good.pre_trace,
            post_trace=good.post_trace,
            plastic_weights=tuple(-0.1 for _ in range(PLASTIC_SYNAPSE_COUNT)),
            eligibility=good.eligibility,
        )
    with pytest.raises(ValueError):
        SnnState(
            voltages=good.voltages[:-1],
            thresholds=good.thresholds,
            pre_trace=good.pre_trace,
            post_trace=good.post_trace,
            plastic_weights=good.plastic_weights,
            eligibility=good.eligibility,
        )


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
