"""RED/GREEN tests for the global v3 state size gate (Task 6).

A worst-case learned state (full action beliefs, a settled ``PendingOutcome``, a
full style ring, the vestigial reuse summary, 64 experiences, and every header)
must encode within the 48 KiB target; the hard gate rejects any encoded payload
above the 64 KiB ceiling before it can reach CAS.  (formula v2 deleted the SNN
sub-state, so no reservoir weights contribute to the payload.)
"""

from __future__ import annotations

import struct

import pytest

from sylanne_alpha.v3bridge import limits
from sylanne_alpha.v3core.contracts import Action, SessionRef, TurnSequence
from sylanne_alpha.v3core.formula_v1 import (
    AXIS_DIM,
    EXPERIENCE_CAPACITY,
    FORMULA_VERSION,
    SNN_SUMMARY_DIM,
)
from sylanne_alpha.v3core.state import codec
from sylanne_alpha.v3core.state.codec import (
    StateSizeError,
    encode_state,
    enforce_state_size,
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
    V3State,
)


def _snap16(value: float) -> float:
    return struct.unpack(">e", struct.pack(">e", value))[0]


def _worst_case_state() -> V3State:
    params = AXIS_DIM * THETA_PARAMS
    beliefs = ActionBeliefs(
        theta=tuple(tuple(_snap16(0.11) for _ in range(params)) for _ in range(ACTION_COUNT)),
        sigma=tuple(tuple(_snap16(0.09) for _ in range(params)) for _ in range(ACTION_COUNT)),
        baselines=tuple(_snap16(0.05) for _ in range(ACTION_COUNT)),
        counts=tuple(255 for _ in range(ACTION_COUNT)),
    )
    pending = PendingOutcome(
        origin_turn_id="turn-worst-case-identifier",
        sequence=TurnSequence(writer_epoch=99, local_sequence=250),
        action=Action.REACH,
        projected_actual_action=Action.SPEAK,
        c=tuple(_snap16(0.1) for _ in range(AXIS_DIM)),
        v_c=tuple(_snap16(0.25) for _ in range(AXIS_DIM)),
        reward_scale=_snap16(1.0),
        preference_log_terms_before=tuple(_snap16(-0.5) for _ in range(AXIS_DIM)),
        predictive_mu_actual=tuple(_snap16(0.2) for _ in range(AXIS_DIM)),
        predictive_v_actual=tuple(_snap16(0.25) for _ in range(AXIS_DIM)),
        likelihood_r_actual=tuple(_snap16(0.20) for _ in range(AXIS_DIM)),
        expiry_sequence=TurnSequence(writer_epoch=99, local_sequence=251),
        preference_revision=FORMULA_VERSION,
        preference_digest="a" * 64,
        outcome_projector_revision=FORMULA_VERSION,
    )
    experiences = tuple(
        ExperienceRecord(
            observation_digest=struct.pack(">Q", i * 2654435761 & 0xFFFFFFFFFFFFFFFF),
            encoded_features=tuple((i * 131 + j) % 65536 - 32768 for j in range(EXPERIENCE_FEATURE_DIM)),
            workspace_broadcast=tuple((i * 17 + j) % 65536 - 32768 for j in range(WORKSPACE_BROADCAST_DIM)),
            shadow_action_code=i % 4,
            actual_action_code=(i * 3) % 5,
            next_observation=tuple((i * 7 + j) % 256 for j in range(36)),
            reward_components=tuple((i * 5 + j) % 65536 - 32768 for j in range(EXPERIENCE_REWARD_DIM)),
            trace_revision=i + 1,
            trace_turn_digest=struct.pack(">Q", i * 40503 & 0xFFFFFFFFFFFFFFFF),
        )
        for i in range(EXPERIENCE_CAPACITY)
    )
    return V3State(
        session_ref=SessionRef(key_id="key-v1", session_digest=b"z" * 32, session_generation=1),
        schema_version=1,
        source_digest="s" * 64,
        state_generation_id="g" * 32,
        revision=2_000_000_000,
        writer_epoch=1_000_000,
        session_generation=7,
        formula_version=FORMULA_VERSION,
        model_revision=FORMULA_VERSION,
        last_committed_turn_sequence=TurnSequence(writer_epoch=1_000_000, local_sequence=999),
        last_committed_turn_id="last-committed-turn-worst-case",
        latent_axes=tuple(_snap16(0.9) for _ in range(24)),
        rho_hold=_snap16(1.0),
        rho_reach=_snap16(1.0),
        style_ring=tuple((3, 2, 1, 1) for _ in range(4)),
        action_beliefs=beliefs,
        last_snn_summary=tuple(_snap16(0.8) for _ in range(SNN_SUMMARY_DIM)),
        pending_outcome=pending,
        experiences=experiences,
    )


def test_worst_case_state_encodes_within_the_target_ceiling() -> None:
    blob = encode_state(_worst_case_state())
    assert len(blob) <= limits.TARGET_STATE_BYTES
    # And is comfortably below the hard ceiling as well.
    assert len(blob) <= limits.MAX_STATE_BYTES
    # The gate accepts the legal worst case.
    assert enforce_state_size(blob, limits.MAX_STATE_BYTES) == blob


def test_worst_case_stays_within_target_even_without_compression_gain() -> None:
    # Prove the ceiling holds independent of payload entropy: the base64 of the raw
    # (uncompressed) framed body is an upper bound on the stored size for any state,
    # since zlib never inflates incompressible data by more than trivial overhead.
    import base64
    import zlib

    blob = encode_state(_worst_case_state())
    framed = zlib.decompress(base64.b64decode(blob))
    incompressible_upper_bound = len(base64.b64encode(framed))
    assert incompressible_upper_bound <= limits.TARGET_STATE_BYTES


def test_encode_state_guarded_accepts_the_legal_worst_case() -> None:
    state = _worst_case_state()
    guarded = encode_state(state, max_bytes=limits.MAX_STATE_BYTES)
    assert guarded == encode_state(state)


def test_size_gate_accepts_at_the_ceiling_and_rejects_above_it() -> None:
    at_ceiling = b"\x00" * limits.MAX_STATE_BYTES
    assert enforce_state_size(at_ceiling, limits.MAX_STATE_BYTES) == at_ceiling
    over = b"\x00" * (limits.MAX_STATE_BYTES + 1)
    with pytest.raises(StateSizeError):
        enforce_state_size(over, limits.MAX_STATE_BYTES)


def test_encode_state_guard_rejects_payloads_over_the_ceiling() -> None:
    # A deliberately tiny ceiling forces the guarded encode path to reject even a
    # legal state, proving the guard actually rejects rather than silently truncating.
    state = _worst_case_state()
    with pytest.raises(StateSizeError):
        encode_state(state, max_bytes=1024)


def test_size_gate_validates_its_arguments() -> None:
    with pytest.raises((TypeError, ValueError)):
        enforce_state_size("not-bytes", limits.MAX_STATE_BYTES)  # type: ignore[arg-type]
    with pytest.raises((TypeError, ValueError)):
        enforce_state_size(b"", -1)


def test_target_and_hard_ceilings_match_the_frozen_budget() -> None:
    assert limits.TARGET_STATE_BYTES == 48 * 1024
    assert limits.MAX_STATE_BYTES == 64 * 1024
    assert codec.MAX_STATE_BYTES_DEFAULT is None
