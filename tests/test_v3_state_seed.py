"""RED/GREEN tests for the pure v3 seed projector (Task 6).

The SeedProjector converts an already-projected, core-owned :class:`SeedFrame`
(plain bounded values, never a v2 DTO) into the initial 24-dimensional latent
state and, from it, a complete neutral :class:`V3State`.  Neutral or missing
facts must project to the exact neutral seed, and any malformed (non-finite,
out-of-range, wrong-shape) input must fail closed rather than yield a
half-decoded state.
"""

from __future__ import annotations

import ast
import struct
from pathlib import Path

import pytest

from sylanne_alpha.v3core.contracts import SessionRef
from sylanne_alpha.v3core.formula_v1 import FORMULA_VERSION, STATE_DIM
from sylanne_alpha.v3core.state import codec
from sylanne_alpha.v3core.state.models import V3State
from sylanne_alpha.v3core.state.seed import (
    SEED_AXIS_MAP,
    SEED_LATENT_BOUND,
    SeedFrame,
    SeedProjector,
    neutral_seed_frame,
)


def _snap16(value: float) -> float:
    return struct.unpack(">e", struct.pack(">e", value))[0]


def _session_ref() -> SessionRef:
    return SessionRef(key_id="key-v1", session_digest=b"s" * 32, session_generation=1)


def _projector() -> SeedProjector:
    return SeedProjector()


def test_seed_projector_imports_no_v2_or_bridge_type() -> None:
    tree = ast.parse(Path("sylanne_alpha/v3core/state/seed.py").read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    for name in modules:
        assert "v2core" not in name
        assert "v3bridge" not in name
        assert not name.startswith("astrbot")
        assert "_engine" not in name


def test_project_latent_produces_exactly_24_bounded_finite_values() -> None:
    latent = _projector().project_latent(neutral_seed_frame())
    assert type(latent) is tuple
    assert len(latent) == STATE_DIM == 24
    for value in latent:
        assert type(value) is float
        assert -SEED_LATENT_BOUND <= value <= SEED_LATENT_BOUND


def test_neutral_and_all_zero_frames_project_to_the_all_zero_latent() -> None:
    projector = _projector()
    from_missing = projector.project_latent(neutral_seed_frame())
    zero_fields = {name: 0.0 for _, name in SEED_AXIS_MAP}
    from_zero = projector.project_latent(SeedFrame(**zero_fields))
    assert from_missing == tuple(0.0 for _ in range(STATE_DIM))
    assert from_zero == from_missing


def test_each_mapped_fact_moves_only_its_own_axis() -> None:
    projector = _projector()
    for axis_index, field_name in SEED_AXIS_MAP:
        latent = projector.project_latent(SeedFrame(**{field_name: 0.5}))
        assert latent[axis_index] == _snap16(0.5)
        for other, value in enumerate(latent):
            if other != axis_index:
                assert value == 0.0


def test_present_facts_are_clipped_to_the_seed_bound() -> None:
    projector = _projector()
    axis_index, field_name = SEED_AXIS_MAP[0]
    high = projector.project_latent(SeedFrame(**{field_name: 9.0}))
    low = projector.project_latent(SeedFrame(**{field_name: -9.0}))
    assert high[axis_index] == _snap16(SEED_LATENT_BOUND)
    assert low[axis_index] == _snap16(-SEED_LATENT_BOUND)


def test_neutral_initial_state_is_byte_identical_for_missing_and_zero_facts() -> None:
    projector = _projector()
    ref = _session_ref()
    baseline = projector.build_initial_state(
        neutral_seed_frame(),
        session_ref=ref,
        state_generation_id="gen-0",
        source_digest="src-0",
    )
    zero_fields = {name: 0.0 for _, name in SEED_AXIS_MAP}
    from_zero = projector.build_initial_state(
        SeedFrame(**zero_fields),
        session_ref=ref,
        state_generation_id="gen-0",
        source_digest="src-0",
    )
    assert codec.encode_state(baseline) == codec.encode_state(from_zero)


def test_neutral_initial_state_is_a_frozen_v3state_at_revision_zero() -> None:
    state = _projector().build_initial_state(
        neutral_seed_frame(),
        session_ref=_session_ref(),
        state_generation_id="gen-0",
        source_digest="src-0",
    )
    assert type(state) is V3State
    assert state.revision == 0
    assert state.latent_axes == tuple(0.0 for _ in range(STATE_DIM))
    assert state.pending_outcome is None
    assert state.experiences == ()
    assert state.formula_version == FORMULA_VERSION
    assert state.rho_hold == state.rho_reach == 0.0


def test_seeded_state_round_trips_through_the_codec() -> None:
    state = _projector().build_initial_state(
        SeedFrame(bond=0.5, hesitation=0.25, emotion_valence_fast=-0.5),
        session_ref=_session_ref(),
        state_generation_id="gen-1",
        source_digest="src-1",
    )
    assert codec.decode_state(codec.encode_state(state)) == state


@pytest.mark.parametrize(
    "factory",
    [
        pytest.param(lambda: SeedFrame(bond=float("nan")), id="nan-fact"),
        pytest.param(lambda: SeedFrame(bond=float("inf")), id="inf-fact"),
        pytest.param(lambda: SeedFrame(bond=1), id="int-fact"),
        pytest.param(lambda: SeedFrame(bond=True), id="bool-fact"),
        pytest.param(lambda: SeedFrame(bond="0.5"), id="str-fact"),
        pytest.param(lambda: SeedFrame(style_signature_seed=[1, 2]), id="mutable-style-seed"),
    ],
)
def test_malformed_seed_frame_fails_closed(factory: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        factory()  # type: ignore[operator]


def test_projector_rejects_non_seed_frame_inputs() -> None:
    projector = _projector()
    for bad in (None, (), {"bond": 0.5}, object()):
        with pytest.raises((TypeError, ValueError)):
            projector.project_latent(bad)  # type: ignore[arg-type]
