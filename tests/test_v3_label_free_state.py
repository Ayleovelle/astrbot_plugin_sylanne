"""RED/GREEN tests for the formula-v2 label-free learner state (Slice B).

The 2026-07-18 label-free reaction-learning spec (§3.1) adds a bounded
:class:`LabelFreeState` sub-state (the L1 preference offset, the L2 marginal
outcome head's EKF mean/covariance, a rolling user length baseline, and two
counters), an optional ``V3State.label_free`` slot, and a
``PendingOutcome.label_free_eligible`` flag frozen at turn ``t``.  The state
schema bumps to 2 and the packed codec to 4 (reading 1..4).

These tests pin Slice B exactly: the DTO validates every field against its
storage-quantization-safe bound and fails closed on anything out of band; the
codec round-trips the new fields bit-for-bit; a legacy (v1/v2/v3) blob with no
label-free segment migrates to ``label_free=None`` / ``label_free_eligible=False``
(migration is缺省, never a rewrite); the worst case still fits the budget; and the
float16 image of ``PREF_OFFSET_BOUNDS`` (``float16(0.30) > 0.30``) survives a
round trip (the a16 quantization-is-persistence trap).
"""

from __future__ import annotations

import base64
import binascii
import struct
import zlib

import pytest

from sylanne_alpha.v3bridge import limits
from sylanne_alpha.v3core.contracts import Action, SessionRef, TurnSequence
from sylanne_alpha.v3core.formula_v1 import (
    ACTION_B_BOUNDS,
    ACTION_G_BOUNDS,
    ACTION_SIGMA_BOUNDS,
    AXIS_DIM,
    FORMULA_VERSION,
    LEN_BASELINE_INIT,
    MARGINAL_INITIAL_B,
    MARGINAL_INITIAL_G,
    PREF_OFFSET_BOUNDS,
)
from sylanne_alpha.v3core.state.codec import (
    STATE_CODEC_MAGIC,
    STATE_CODEC_VERSION,
    SUPPORTED_STATE_CODEC_VERSIONS,
    StateCodecError,
    decode_state,
    encode_state,
)
from sylanne_alpha.v3core.state.models import (
    LABEL_FREE_MARGINAL_DIM,
    LABEL_FREE_PREF_OFFSET_DIM,
    MARGINAL_COUNT_CAP,
    PREF_OFFSET_STORED_BOUNDS,
    REACTION_COUNT_CAP,
    STATE_SCHEMA_VERSION,
    LabelFreeState,
    PendingOutcome,
    V3State,
)


def _snap16(value: float) -> float:
    return struct.unpack(">e", struct.pack(">e", value))[0]


def _session_ref(generation: int = 1) -> SessionRef:
    return SessionRef(key_id="key-v1", session_digest=b"s" * 32, session_generation=generation)


def _label_free(
    *,
    pref: float = 0.1,
    g: float = MARGINAL_INITIAL_G,
    b: float = 0.05,
    sigma: float = 0.1,
    marginal_count: int = 42,
    len_baseline: float = LEN_BASELINE_INIT,
    reaction_count: int = 7,
) -> LabelFreeState:
    """A fully populated, float16-snapped LabelFreeState (so it round-trips exactly)."""

    return LabelFreeState(
        pref_offset=tuple(_snap16(pref) for _ in range(LABEL_FREE_PREF_OFFSET_DIM)),
        marginal_theta=tuple(
            _snap16(g) if index % 2 == 0 else _snap16(b) for index in range(LABEL_FREE_MARGINAL_DIM)
        ),
        marginal_sigma=tuple(_snap16(sigma) for _ in range(LABEL_FREE_MARGINAL_DIM)),
        marginal_count=marginal_count,
        len_baseline=_snap16(len_baseline),
        reaction_count=reaction_count,
    )


def _reframe(body: bytes) -> bytes:
    """Frame a raw codec body with a fresh CRC exactly like ``encode_state``."""

    framed = body + struct.pack(">I", binascii.crc32(body) & 0xFFFFFFFF)
    return base64.b64encode(zlib.compress(framed, 9))


def _legacy_string(value: str) -> bytes:
    data = value.encode("utf-8")
    return struct.pack(">H", len(data)) + data


def _v3_neutral_blob() -> bytes:
    """Hand-built valid v3 blob (no SNN segment, no label-free segment).

    A pre-Slice-B blob has no label-free segment at all; decoding it must yield
    ``label_free=None`` without rereading or rewriting anything.
    """

    body = STATE_CODEC_MAGIC + struct.pack(">H", 3)  # version 3
    body += struct.pack(">H", 1)  # schema_version (legacy states were schema 1)
    body += struct.pack(">Q", 0)  # revision
    body += struct.pack(">Q", 0)  # writer_epoch
    body += struct.pack(">Q", 0)  # session_generation (header)
    body += _legacy_string("key-v1")  # session_ref.key_id
    body += b"s" * 32  # session_digest
    body += struct.pack(">Q", 1)  # session_ref.session_generation
    body += _legacy_string(FORMULA_VERSION)  # formula_version
    body += _legacy_string("")  # source_digest
    body += _legacy_string("")  # state_generation_id
    body += _legacy_string(FORMULA_VERSION)  # model_revision
    body += struct.pack(">B", 0)  # last_committed_turn_id: None
    body += struct.pack(">B", 0)  # last_committed_turn_sequence: None
    body += struct.pack(">24f", *([0.0] * 24))  # latent axes (v>=2: float32)
    body += struct.pack(">e", 0.0)  # rho_hold
    body += struct.pack(">e", 0.0)  # rho_reach
    body += struct.pack(">B", 0)  # style ring count
    # v3: no SNN segment.
    body += struct.pack(">B", 0)  # beliefs: None
    body += struct.pack(">B", 0)  # summary: None
    body += struct.pack(">B", 0)  # pending: None
    body += struct.pack(">H", 0)  # experiences count
    # v3: no label-free segment.
    return _reframe(body)


# --------------------------------------------------------------------------- #
# Version bumps
# --------------------------------------------------------------------------- #


def test_schema_and_codec_versions_are_bumped_for_label_free() -> None:
    assert STATE_SCHEMA_VERSION == 2
    assert STATE_CODEC_VERSION == 4
    assert SUPPORTED_STATE_CODEC_VERSIONS == (1, 2, 3, 4)


# --------------------------------------------------------------------------- #
# LabelFreeState DTO: shape, freeze, per-field bound validation
# --------------------------------------------------------------------------- #


def test_label_free_state_is_frozen_and_has_the_declared_shape() -> None:
    lf = _label_free()
    assert len(lf.pref_offset) == LABEL_FREE_PREF_OFFSET_DIM == AXIS_DIM
    assert len(lf.marginal_theta) == LABEL_FREE_MARGINAL_DIM == AXIS_DIM * 2
    assert len(lf.marginal_sigma) == LABEL_FREE_MARGINAL_DIM
    with pytest.raises(Exception):
        lf.marginal_count = 5  # type: ignore[misc]


def test_neutral_label_free_prior_is_none() -> None:
    # None means "the whole channel is at its prior"; a minimal state carries it.
    assert V3State(session_ref=_session_ref()).label_free is None
    assert PendingOutcome(
        origin_turn_id="t",
        sequence=TurnSequence(0, 1),
        action=Action.SPEAK,
    ).label_free_eligible is False


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"pref": 0.5}, id="pref-offset-over-bound"),
        pytest.param({"pref": -0.5}, id="pref-offset-under-bound"),
        pytest.param({"g": 2.0}, id="marginal-g-over-bound"),
        pytest.param({"g": 0.0}, id="marginal-g-under-bound"),
        pytest.param({"b": 1.0}, id="marginal-b-over-bound"),
        pytest.param({"sigma": 5.0}, id="marginal-sigma-over-bound"),
        pytest.param({"sigma": 0.0}, id="marginal-sigma-under-bound"),
        pytest.param({"len_baseline": 1.5}, id="len-baseline-over-bound"),
        pytest.param({"len_baseline": -0.1}, id="len-baseline-under-bound"),
        pytest.param({"marginal_count": MARGINAL_COUNT_CAP + 1}, id="marginal-count-over-cap"),
        pytest.param({"marginal_count": -1}, id="marginal-count-negative"),
        pytest.param({"reaction_count": REACTION_COUNT_CAP + 1}, id="reaction-count-over-cap"),
        pytest.param({"reaction_count": -1}, id="reaction-count-negative"),
    ],
)
def test_label_free_state_rejects_out_of_band_fields(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        _label_free(**kwargs)


def test_marginal_theta_bounds_are_position_aware() -> None:
    """theta is interleaved [g0,b0,g1,b1,...]: a g-legal value in a b-slot must fail.

    ``1.0`` is inside ACTION_G_BOUNDS (0.5..1.2) but outside ACTION_B_BOUNDS
    (-0.5..0.5), so it validates in an even (g) slot and is rejected in an odd (b)
    slot -- proving the per-index bounds are not a single shared interval.
    """

    even_ok = tuple(
        1.0 if index == 0 else (_snap16(MARGINAL_INITIAL_G) if index % 2 == 0 else _snap16(0.0))
        for index in range(LABEL_FREE_MARGINAL_DIM)
    )
    LabelFreeState(
        pref_offset=tuple(0.0 for _ in range(LABEL_FREE_PREF_OFFSET_DIM)),
        marginal_theta=even_ok,
        marginal_sigma=tuple(_snap16(0.1) for _ in range(LABEL_FREE_MARGINAL_DIM)),
        marginal_count=0,
        len_baseline=_snap16(LEN_BASELINE_INIT),
        reaction_count=0,
    )
    odd_bad = tuple(
        1.0 if index == 1 else (_snap16(MARGINAL_INITIAL_G) if index % 2 == 0 else _snap16(0.0))
        for index in range(LABEL_FREE_MARGINAL_DIM)
    )
    with pytest.raises(ValueError):
        LabelFreeState(
            pref_offset=tuple(0.0 for _ in range(LABEL_FREE_PREF_OFFSET_DIM)),
            marginal_theta=odd_bad,
            marginal_sigma=tuple(_snap16(0.1) for _ in range(LABEL_FREE_MARGINAL_DIM)),
            marginal_count=0,
            len_baseline=_snap16(LEN_BASELINE_INIT),
            reaction_count=0,
        )


@pytest.mark.parametrize("field", ["marginal_count", "reaction_count"])
def test_counts_reject_bool_impersonating_int(field: str) -> None:
    with pytest.raises(TypeError):
        _label_free(**{field: True})  # type: ignore[arg-type]


@pytest.mark.parametrize("length", [LABEL_FREE_PREF_OFFSET_DIM - 1, LABEL_FREE_PREF_OFFSET_DIM + 1])
def test_pref_offset_rejects_wrong_length(length: int) -> None:
    with pytest.raises(ValueError):
        LabelFreeState(
            pref_offset=tuple(0.0 for _ in range(length)),
            marginal_theta=tuple(
                _snap16(MARGINAL_INITIAL_G) if i % 2 == 0 else _snap16(MARGINAL_INITIAL_B)
                for i in range(LABEL_FREE_MARGINAL_DIM)
            ),
            marginal_sigma=tuple(_snap16(0.1) for _ in range(LABEL_FREE_MARGINAL_DIM)),
            marginal_count=0,
            len_baseline=_snap16(LEN_BASELINE_INIT),
            reaction_count=0,
        )


def test_pending_outcome_rejects_non_bool_eligibility() -> None:
    with pytest.raises(TypeError):
        PendingOutcome(
            origin_turn_id="t",
            sequence=TurnSequence(0, 1),
            action=Action.SPEAK,
            label_free_eligible=1,  # type: ignore[arg-type]
        )


# --------------------------------------------------------------------------- #
# Quantization-safe pref_offset bound (a16: quantization IS persistence)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("corner", ["low", "high"])
def test_pref_offset_at_its_float16_image_round_trips(corner: str) -> None:
    """float16(0.30) = 0.300048828125 > 0.30: the value stored when L1 clamps an
    offset to its bound must validate (via quantization_safe_bounds) and be a
    round-trip fixed point -- otherwise a crash reload would loop forever.
    """

    declared = PREF_OFFSET_BOUNDS[0 if corner == "low" else 1]
    stored = _snap16(declared)
    if corner == "high":
        assert stored > declared  # the a16 trap: the grid image escapes the interval
    else:
        assert stored < declared
    low, high = PREF_OFFSET_STORED_BOUNDS
    assert low <= stored <= high  # the widened storage interval accepts it

    lf = _label_free()
    lf = LabelFreeState(
        pref_offset=tuple(stored for _ in range(LABEL_FREE_PREF_OFFSET_DIM)),
        marginal_theta=lf.marginal_theta,
        marginal_sigma=lf.marginal_sigma,
        marginal_count=lf.marginal_count,
        len_baseline=lf.len_baseline,
        reaction_count=lf.reaction_count,
    )
    state = V3State(session_ref=_session_ref(), label_free=lf)
    blob = encode_state(state)
    restored = decode_state(blob)  # must not raise
    assert restored == state
    assert encode_state(restored) == blob  # reload is a fixed point


# --------------------------------------------------------------------------- #
# Codec round-trip of the new fields
# --------------------------------------------------------------------------- #


def test_label_free_state_round_trips_through_the_codec() -> None:
    state = V3State(session_ref=_session_ref(), revision=3, label_free=_label_free())
    restored = decode_state(encode_state(state))
    assert restored == state
    assert restored.label_free == state.label_free


def test_pending_label_free_eligible_round_trips() -> None:
    for eligible in (True, False):
        pending = PendingOutcome(
            origin_turn_id="turn-t",
            sequence=TurnSequence(writer_epoch=7, local_sequence=11),
            action=Action.SPEAK,
            label_free_eligible=eligible,
        )
        state = V3State(session_ref=_session_ref(), pending_outcome=pending, label_free=_label_free())
        restored = decode_state(encode_state(state))
        assert restored.pending_outcome is not None
        assert restored.pending_outcome.label_free_eligible is eligible
        assert restored == state


def test_encoding_with_label_free_is_deterministic() -> None:
    state = V3State(session_ref=_session_ref(), label_free=_label_free())
    assert encode_state(state) == encode_state(state)


# --------------------------------------------------------------------------- #
# Backward-compatible read migration: legacy blobs decode label_free as None
# --------------------------------------------------------------------------- #


def test_v3_blob_without_label_free_segment_decodes_as_none() -> None:
    decoded = decode_state(_v3_neutral_blob())
    assert decoded.label_free is None
    assert decoded.schema_version == 1  # a legacy blob keeps its stored schema version
    assert decoded == V3State(session_ref=_session_ref(), schema_version=1)
    # A migrated state re-emits as the current (v4) codec and round-trips.
    assert decode_state(encode_state(decoded)) == decoded


def test_v4_encode_of_migrated_state_carries_a_label_free_segment() -> None:
    migrated = decode_state(_v3_neutral_blob())
    reencoded = encode_state(migrated)
    body = zlib.decompress(base64.b64decode(reencoded))
    version = struct.unpack(">H", body[len(STATE_CODEC_MAGIC) : len(STATE_CODEC_MAGIC) + 2])[0]
    assert version == 4


# --------------------------------------------------------------------------- #
# Fail-closed on a malformed label-free segment
# --------------------------------------------------------------------------- #


def test_decode_fails_closed_on_a_non_finite_label_free_half_float() -> None:
    state = V3State(session_ref=_session_ref(), label_free=_label_free(sigma=0.123))
    body = bytearray(zlib.decompress(base64.b64decode(encode_state(state))))
    sigma_run = struct.pack(">e", _snap16(0.123)) * 6  # only appears in marginal_sigma
    index = body.find(sigma_run)
    assert index != -1
    body[index : index + 2] = struct.pack(">e", float("inf"))
    with pytest.raises(StateCodecError):
        decode_state(_reframe(bytes(body)))


def test_decode_fails_closed_on_a_truncated_label_free_segment() -> None:
    state = V3State(session_ref=_session_ref(), label_free=_label_free())
    body = zlib.decompress(base64.b64decode(encode_state(state)))
    # Drop the CRC and the last four bytes of the label-free segment: the reader
    # runs off the end and must fail closed rather than return a partial state.
    with pytest.raises(StateCodecError):
        decode_state(_reframe(body[:-8]))


def test_decode_fails_closed_on_an_out_of_band_stored_label_free_value() -> None:
    """A hand-forged blob whose stored pref_offset is grossly out of band must be
    rejected on decode -- the DTO bound is enforced through the codec, not bypassed.
    """

    state = V3State(session_ref=_session_ref(), label_free=_label_free(pref=0.1))
    body = bytearray(zlib.decompress(base64.b64decode(encode_state(state))))
    offset_run = struct.pack(">e", _snap16(0.1)) * 8  # the eight pref_offset halves
    index = body.find(offset_run)
    assert index != -1
    body[index : index + 2] = struct.pack(">e", _snap16(0.9))  # far outside PREF_OFFSET_BOUNDS
    with pytest.raises(StateCodecError):
        decode_state(_reframe(bytes(body)))


# --------------------------------------------------------------------------- #
# Worst-case size still fits the budget
# --------------------------------------------------------------------------- #


def test_worst_case_state_with_label_free_stays_within_the_budget() -> None:
    from tests.test_v3_state_budget import _worst_case_state

    state = _worst_case_state()
    assert state.label_free is not None  # the worst case now exercises the new field
    blob = encode_state(state)
    assert len(blob) <= limits.TARGET_STATE_BYTES
    assert len(blob) <= limits.MAX_STATE_BYTES
    # The full label-free block is a bounded, fixed cost.
    assert decode_state(blob) == state
