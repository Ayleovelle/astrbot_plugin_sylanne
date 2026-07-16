"""RED/GREEN tests for Task 7 multi-timescale dynamics.

The dynamics stage is pure ``v3core``: it maps a bounded :class:`V3State`
(24-dim latent axes laid out as ``[fast|mid|slow] x 8``) plus an immutable
:class:`ObservationFrame` (36 normalized values + 36-bit validity mask) onto the
next latent axes using the frozen design section 9 update equations and the
approved formula-v1 constants.  It performs no I/O, imports nothing forbidden by
the firewall, and never mutates its inputs.

The most important property proven here is the *complete sequential* 24x24
entrywise-absolute triangular Jacobian gate: the true operator-norm upper bound
``sqrt(||J||1 * ||J||inf) = 0.9948652052815999 < 0.995`` must be built from the
full ``fast -> mid -> slow`` composition (with the cross-scale coupling rows),
and a block-diagonal-only / per-scale shortcut must be explicitly rejected.
"""

from __future__ import annotations

import ast
from decimal import Decimal, getcontext
from fractions import Fraction
from math import isclose, isfinite, sqrt, tanh
from pathlib import Path

import pytest

from sylanne_alpha.v3core import features
from sylanne_alpha.v3core import formula_v1 as formula
from sylanne_alpha.v3core.contracts import SessionRef
from sylanne_alpha.v3core.dynamics import (
    MultiscaleAdvance,
    advance_dynamics,
    advance_state,
    compute_drive,
    jacobian_absolute_upper_bound_full,
    multiscale_jacobian_bound,
    select_valid_next_axes,
    spectral_l2_upper_bound,
    validate_jacobian_gate,
)
from sylanne_alpha.v3core.observation.models import ObservationFrame
from sylanne_alpha.v3core.state.models import V3State

AXIS_DIM = formula.AXIS_DIM
STATE_DIM = formula.STATE_DIM
OBSERVATION_DIM = formula.OBSERVATION_DIM
MANIFEST_JACOBIAN_BOUND = 0.9948652052815999


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #


def _session_ref() -> SessionRef:
    return SessionRef(key_id="key-v1", session_digest=b"s" * 32, session_generation=1)


def _state(latent: tuple | None = None, revision: int = 0) -> V3State:
    if latent is None:
        latent = tuple(0.0 for _ in range(STATE_DIM))
    return V3State(
        session_ref=_session_ref(),
        state_generation_id="gen-1",
        source_digest="",
        revision=revision,
        latent_axes=latent,
    )


def _frame(overrides: dict[int, float] | None = None, valid: set[int] | None = None) -> ObservationFrame:
    """Build a frame from the semantic defaults with optional per-channel overrides."""

    values = list(formula.SEMANTIC_DEFAULTS)
    if overrides:
        for channel, value in overrides.items():
            values[channel] = value
    mask = 0
    for channel in valid or set():
        mask |= 1 << channel
    return ObservationFrame(values=tuple(values), valid_mask=mask)


# --------------------------------------------------------------------------- #
# Independent 24x24 Jacobian reference (built inside the test on purpose)
# --------------------------------------------------------------------------- #


def _self_block(matrix: tuple, alpha: float) -> list[list[float]]:
    """|d x'/d x| entrywise bound for x' = x + alpha*(tanh(W x + ...) - x), |tanh'|<=1."""

    return [
        [(1.0 - alpha if i == j else 0.0) + alpha * abs(matrix[i][j]) for j in range(AXIS_DIM)]
        for i in range(AXIS_DIM)
    ]


def _feedforward_block(matrix: tuple, alpha: float) -> list[list[float]]:
    """|d x'/d (upstream scale)| entrywise bound = alpha*|U|, |tanh'|<=1."""

    return [[alpha * abs(matrix[i][j]) for j in range(AXIS_DIM)] for i in range(AXIS_DIM)]


def _matmul(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    return [
        [sum(left[i][k] * right[k][j] for k in range(AXIS_DIM)) for j in range(AXIS_DIM)]
        for i in range(AXIS_DIM)
    ]


def _build_full_sequential_jacobian() -> list[list[float]]:
    """The complete fast->mid->slow 24x24 entrywise-absolute triangular bound.

    Chain rule through the *sequential* update: fast advances first, mid reads the
    already-advanced fast', and slow reads the already-advanced mid'.  Hence the
    lower-left blocks (mid<-fast, slow<-fast, slow<-mid) are nonzero and MUST be
    included; omitting them is the invalid block-diagonal shortcut.
    """

    a_fast, a_mid, a_slow = formula.DYNAMICS_STEP_SIZES
    block_a = _self_block(formula.W_FAST, a_fast)  # d fast'/d fast
    block_b = _self_block(formula.W_MID, a_mid)  # d mid'/d mid
    block_f = _self_block(formula.W_SLOW, a_slow)  # d slow'/d slow
    mid_from_fast = _feedforward_block(formula.U_MID, a_mid)  # d mid'/d fast'
    slow_from_mid = _feedforward_block(formula.U_SLOW, a_slow)  # d slow'/d mid'
    block_c = _matmul(mid_from_fast, block_a)  # d mid'/d fast (via fast')
    block_d = _matmul(slow_from_mid, block_b)  # d slow'/d mid (via mid')
    block_e = _matmul(slow_from_mid, block_c)  # d slow'/d fast (via mid'<-fast')
    zero = [[0.0] * AXIS_DIM for _ in range(AXIS_DIM)]
    rows: list[list[float]] = []
    for r in range(AXIS_DIM):
        rows.append(list(block_a[r]) + list(zero[r]) + list(zero[r]))
    for r in range(AXIS_DIM):
        rows.append(list(block_c[r]) + list(block_b[r]) + list(zero[r]))
    for r in range(AXIS_DIM):
        rows.append(list(block_e[r]) + list(block_d[r]) + list(block_f[r]))
    return rows


def _double_spectral_bound(matrix: list[list[float]]) -> float:
    n = len(matrix)
    norm_one = max(sum(matrix[r][c] for r in range(n)) for c in range(n))
    norm_inf = max(sum(matrix[r]) for r in range(n))
    return sqrt(norm_one * norm_inf)


def _exact_spectral_bound(matrix: list[list[float]]) -> float:
    """Correctly-rounded sqrt(||J||1*||J||inf) via exact rationals then one Decimal sqrt."""

    getcontext().prec = 60
    n = len(matrix)
    rational = [[Fraction(matrix[r][c]) for c in range(n)] for r in range(n)]
    norm_one = max(sum((rational[r][c] for r in range(n)), Fraction(0)) for c in range(n))
    norm_inf = max(sum(rational[r], Fraction(0)) for r in range(n))
    product = norm_one * norm_inf
    root = (Decimal(product.numerator) / Decimal(product.denominator)).sqrt()
    return float(root)


def _block_diagonal_only(matrix: list[list[float]]) -> list[list[float]]:
    n = len(matrix)
    out = [[0.0] * n for _ in range(n)]
    for block in range(3):
        base = block * AXIS_DIM
        for i in range(AXIS_DIM):
            for j in range(AXIS_DIM):
                out[base + i][base + j] = matrix[base + i][base + j]
    return out


# --------------------------------------------------------------------------- #
# Firewall / structure
# --------------------------------------------------------------------------- #


def _imported_modules(path: str) -> set[str]:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_dynamics_and_features_import_nothing_forbidden() -> None:
    forbidden = (
        "astrbot",
        "sylanne_alpha.v2core",
        "sylanne_alpha._engine",
        "asyncio",
        "time",
        "logging",
        "os",
        "pathlib",
        "io",
        "numpy",
        "threading",
        "concurrent.futures",
        "portalocker",
    )
    for path in (
        "sylanne_alpha/v3core/features.py",
        "sylanne_alpha/v3core/dynamics/__init__.py",
        "sylanne_alpha/v3core/dynamics/models.py",
        "sylanne_alpha/v3core/dynamics/multiscale.py",
    ):
        imports = _imported_modules(path)
        for name in imports:
            assert not any(name == item or name.startswith(item + ".") for item in forbidden), (
                path,
                name,
            )


def test_state_is_exactly_8x3_24_values() -> None:
    assert STATE_DIM == 24 == 3 * AXIS_DIM
    result = advance_dynamics(_state(), _frame({25: 0.9}, {25}), turn_revision=1)
    assert type(result) is MultiscaleAdvance
    assert type(result.next_latent_axes) is tuple
    assert len(result.next_latent_axes) == 24
    fast, mid, slow = features.split_timescales(result.next_latent_axes)
    assert len(fast) == len(mid) == len(slow) == AXIS_DIM
    assert len(result.drive) == AXIS_DIM
    for value in result.next_latent_axes:
        assert type(value) is float
        assert -1.0 <= value <= 1.0


# --------------------------------------------------------------------------- #
# Approved constants used verbatim
# --------------------------------------------------------------------------- #


def test_approved_formula_constants_used_verbatim() -> None:
    # design section 9 step sizes and coupling gains, asserted against formula_v1
    assert formula.DYNAMICS_STEP_SIZES == (0.50, 0.12, 0.02)
    assert formula.SELF_DIAGONALS == (0.30, 0.35, 0.36)
    for i in range(AXIS_DIM):
        for j in range(AXIS_DIM):
            expected = 0.80 if i == j else 0.0
            assert formula.U_FAST[i][j] == expected
            assert formula.U_MID[i][j] == (0.75 if i == j else 0.0)
            assert formula.U_SLOW[i][j] == (0.65 if i == j else 0.0)
    # self-matrix diagonals and the exact off-diagonal couplings (fast scale)
    assert formula.W_FAST[0][0] == 0.30
    assert formula.W_MID[0][0] == 0.35
    assert formula.W_SLOW[0][0] == 0.36
    assert formula.W_FAST[0][2] == pytest.approx(0.06)  # safety -> valence
    assert formula.W_FAST[0][3] == pytest.approx(0.06)  # affiliation -> valence
    assert formula.W_FAST[1][4] == pytest.approx(0.06)  # uncertainty -> arousal
    assert formula.W_FAST[4][2] == pytest.approx(-0.06)  # safety -> uncertainty
    assert formula.W_FAST[6][3] == pytest.approx(0.05)  # affiliation -> agency
    assert formula.W_FAST[7][6] == pytest.approx(0.05)  # agency -> expression_pressure
    # mid uses 5/6 and slow 1/2 of the fast couplings
    assert formula.W_MID[0][2] == pytest.approx(0.06 * 5.0 / 6.0)
    assert formula.W_SLOW[0][2] == pytest.approx(0.06 * 0.5)
    # bias identity: bias = -P @ SEMANTIC_DEFAULTS
    expected_bias = tuple(
        -sum(weight * formula.SEMANTIC_DEFAULTS[c] for c, weight in enumerate(row))
        for row in formula.P_MATRIX
    )
    assert formula.P_BIAS == expected_bias


def test_single_step_matches_section_9_equations() -> None:
    """The advance reproduces the exact fast/mid/slow tanh update, verbatim constants."""

    frame = _frame({25: 0.9, 4: 0.8, 11: 0.7}, {25, 4, 11})
    drive = compute_drive(frame)
    latent = tuple(0.05 * (i - 12) for i in range(STATE_DIM))  # a nonzero, bounded state
    state = _state(latent=tuple(round(v, 6) for v in latent))

    fast = list(state.latent_axes[0:8])
    mid = list(state.latent_axes[8:16])
    slow = list(state.latent_axes[16:24])
    a_fast, a_mid, a_slow = formula.DYNAMICS_STEP_SIZES

    def clip(v: float) -> float:
        return -1.0 if v < -1.0 else 1.0 if v > 1.0 else v

    tf = [
        tanh(sum(formula.W_FAST[i][j] * fast[j] for j in range(8)) + sum(formula.U_FAST[i][j] * drive[j] for j in range(8)))
        for i in range(8)
    ]
    fast2 = [clip(fast[i] + a_fast * (tf[i] - fast[i])) for i in range(8)]
    tm = [
        tanh(sum(formula.W_MID[i][j] * mid[j] for j in range(8)) + sum(formula.U_MID[i][j] * fast2[j] for j in range(8)))
        for i in range(8)
    ]
    mid2 = [clip(mid[i] + a_mid * (tm[i] - mid[i])) for i in range(8)]
    ts = [
        tanh(sum(formula.W_SLOW[i][j] * slow[j] for j in range(8)) + sum(formula.U_SLOW[i][j] * mid2[j] for j in range(8)))
        for i in range(8)
    ]
    slow2 = [clip(slow[i] + a_slow * (ts[i] - slow[i])) for i in range(8)]
    expected = fast2 + mid2 + slow2

    result = advance_dynamics(state, frame, turn_revision=state.revision + 1)
    assert len(result.next_latent_axes) == 24
    for got, want in zip(result.next_latent_axes, expected):
        assert isclose(got, want, rel_tol=0.0, abs_tol=1e-12)


# --------------------------------------------------------------------------- #
# Neutral zero drive / invalid channel exclusion
# --------------------------------------------------------------------------- #


def test_semantic_default_frame_yields_exactly_zero_drive() -> None:
    # every channel valid, all values at the semantic default
    all_valid = _frame(valid=set(range(OBSERVATION_DIM)))
    drive_valid = compute_drive(all_valid)
    assert drive_valid == tuple(0.0 for _ in range(AXIS_DIM))
    # no channel valid (defaults inert) -> also exactly zero
    none_valid = _frame()
    assert compute_drive(none_valid) == tuple(0.0 for _ in range(AXIS_DIM))
    # an explicit zero SNN summary cannot perturb the neutral drive
    assert compute_drive(all_valid, tuple(0.0 for _ in range(formula.SNN_SUMMARY_DIM))) == tuple(
        0.0 for _ in range(AXIS_DIM)
    )
    # and advancing the neutral state from a neutral frame changes nothing
    neutral = _state()
    advanced = advance_state(neutral, none_valid, turn_revision=1)
    assert advanced.latent_axes == neutral.latent_axes


def test_drive_uses_exact_p_and_q_weights() -> None:
    # channel 25 (valence, weight 0.55) valid at 0.9; default is 0.5 -> centered 0.4
    frame = _frame({25: 0.9}, {25})
    drive = compute_drive(frame)
    assert isclose(drive[0], tanh(0.55 * (0.9 - 0.5)), rel_tol=0.0, abs_tol=1e-12)
    for axis in range(1, AXIS_DIM):
        assert drive[axis] == 0.0  # channel 25 feeds only axis 0
    # Q maps snn_summary: Q[0][0] = 0.20 feeds axis 0's drive
    summary = tuple(1.0 if index == 0 else 0.0 for index in range(formula.SNN_SUMMARY_DIM))
    snn_drive = compute_drive(_frame(), summary)
    assert isclose(snn_drive[0], tanh(0.20 * 1.0), rel_tol=0.0, abs_tol=1e-12)
    for axis in range(1, AXIS_DIM):
        assert snn_drive[axis] == 0.0


def test_invalid_channels_are_excluded_from_drive_and_next_state() -> None:
    neutral_drive = compute_drive(_frame())
    # channel 25 drives valence (0,25,0.55); with it VALID the drive changes
    valid_25 = _frame({25: 0.9}, {25})
    invalid_25 = _frame({25: 0.9})  # same value, but mask bit clear
    assert compute_drive(valid_25) != neutral_drive
    assert compute_drive(invalid_25) == neutral_drive
    # changing an invalid channel's raw value does not change the drive
    invalid_low = _frame({25: 0.1})
    invalid_high = _frame({25: 0.95})
    assert compute_drive(invalid_low) == compute_drive(invalid_high) == neutral_drive
    # ...nor the next state
    base = _state()
    from_invalid = advance_dynamics(base, invalid_high, turn_revision=1)
    from_neutral = advance_dynamics(base, _frame(), turn_revision=1)
    from_valid = advance_dynamics(base, valid_25, turn_revision=1)
    assert from_invalid.next_latent_axes == from_neutral.next_latent_axes
    assert from_valid.next_latent_axes != from_neutral.next_latent_axes


# --------------------------------------------------------------------------- #
# Idempotency per revision + determinism + fallback
# --------------------------------------------------------------------------- #


def test_same_revision_advances_state_exactly_once() -> None:
    base = _state(revision=0)
    frame = _frame({25: 0.9, 11: 0.8}, {25, 11})
    first = advance_state(base, frame, turn_revision=1)
    assert first.revision == 1
    assert first.latent_axes != base.latent_axes
    # a second call with the SAME revision must not re-advance
    second = advance_state(first, frame, turn_revision=1)
    assert second.revision == 1
    assert second.latent_axes == first.latent_axes
    assert second is first  # idempotent no-op returns the input state unchanged
    # advance_dynamics reports the no-op explicitly
    repeat = advance_dynamics(first, frame, turn_revision=1)
    assert repeat.advanced is False
    assert repeat.next_latent_axes == first.latent_axes


def test_advance_is_deterministic_and_bounded_under_extreme_drive() -> None:
    frame = _frame({c: 1.0 for c in range(OBSERVATION_DIM)}, set(range(OBSERVATION_DIM)))
    base = _state(latent=tuple(1.0 if i % 2 == 0 else -1.0 for i in range(STATE_DIM)))
    a = advance_dynamics(base, frame, turn_revision=1)
    b = advance_dynamics(base, frame, turn_revision=1)
    assert a.next_latent_axes == b.next_latent_axes  # deterministic
    for value in a.next_latent_axes:
        assert isfinite(value)
        assert -1.0 <= value <= 1.0
    for value in a.drive:
        assert isfinite(value)
        assert -1.0 <= value <= 1.0


def test_fallback_selects_previous_axes_on_nonfinite_or_out_of_bound() -> None:
    previous = tuple(0.1 * (i - 12) for i in range(STATE_DIM))
    good = tuple(0.0 for _ in range(STATE_DIM))
    assert select_valid_next_axes(previous, good) == good  # candidate accepted
    nan_axes = tuple(float("nan") if i == 3 else 0.0 for i in range(STATE_DIM))
    assert select_valid_next_axes(previous, nan_axes) == previous  # rejected -> previous
    out_of_bound = tuple(2.0 if i == 5 else 0.0 for i in range(STATE_DIM))
    assert select_valid_next_axes(previous, out_of_bound) == previous


def test_advance_does_not_mutate_inputs() -> None:
    base = _state()
    frame = _frame({25: 0.9}, {25})
    base_latent = base.latent_axes
    frame_values = frame.values
    advance_state(base, frame, turn_revision=1)
    assert base.latent_axes == base_latent
    assert frame.values == frame_values
    assert base.revision == 0


# --------------------------------------------------------------------------- #
# Features (decision-state blend read for Task 8/9)
# --------------------------------------------------------------------------- #


def test_decision_state_blend_reads_fast_mid_slow() -> None:
    fast = tuple(0.4 for _ in range(AXIS_DIM))
    mid = tuple(0.2 for _ in range(AXIS_DIM))
    slow = tuple(-1.0 for _ in range(AXIS_DIM))
    latent = fast + mid + slow
    weights = formula.DECISION_STATE_BLEND
    assert weights == (0.50, 0.30, 0.20)
    blended = features.decision_state(latent)
    assert len(blended) == AXIS_DIM
    for i in range(AXIS_DIM):
        expect = 0.50 * fast[i] + 0.30 * mid[i] + 0.20 * slow[i]
        assert isclose(blended[i], expect, rel_tol=0.0, abs_tol=1e-12)
        assert -1.0 <= blended[i] <= 1.0
    # blend is clipped to [-1,1]
    saturated = tuple(1.0 for _ in range(STATE_DIM))
    assert features.decision_state(saturated) == tuple(1.0 for _ in range(AXIS_DIM))


# --------------------------------------------------------------------------- #
# THE CRITICAL GATE: full sequential 24x24 Jacobian bound
# --------------------------------------------------------------------------- #


def test_full_sequential_jacobian_is_the_complete_bound_under_0995() -> None:
    reference = _build_full_sequential_jacobian()
    assert len(reference) == 24
    assert all(len(row) == 24 for row in reference)

    reference_tuple = tuple(tuple(row) for row in reference)
    # the dynamics validator reproduces the same full sequential matrix ...
    assert jacobian_absolute_upper_bound_full() == reference_tuple
    # ... and it equals the frozen formula-v1 manifest Jacobian
    assert reference_tuple == formula.JACOBIAN_ABSOLUTE_UPPER_BOUND

    bound = spectral_l2_upper_bound(reference)
    # (1) strict analytic stability gate
    assert bound < 0.995
    # (2) equals the manifest / design value to full float tolerance (1-ULP IEEE-754
    #     pipeline artifact: the exact rational value rounds to ...999, doubles give ...998)
    assert isclose(bound, MANIFEST_JACOBIAN_BOUND, rel_tol=0.0, abs_tol=1e-12)
    exact = _exact_spectral_bound(reference)
    assert exact == MANIFEST_JACOBIAN_BOUND  # correctly-rounded true value is bit-exact
    # (3) double pipeline is consistent with the frozen manifest bound
    assert bound == formula.JACOBIAN_STABILITY_BOUND
    assert multiscale_jacobian_bound() == formula.JACOBIAN_STABILITY_BOUND
    assert validate_jacobian_gate() == formula.JACOBIAN_STABILITY_BOUND


def test_block_diagonal_only_bound_is_rejected_as_invalid_shortcut() -> None:
    reference = _build_full_sequential_jacobian()
    full_bound = spectral_l2_upper_bound(reference)

    # A block-diagonal-only / per-scale bound omits the fast->mid->slow coupling
    # rows; it is strictly smaller and MUST NOT be used as the stability bound.
    diagonal_only = _block_diagonal_only(reference)
    diagonal_bound = spectral_l2_upper_bound(diagonal_only)
    assert diagonal_bound < full_bound - 1e-3

    # per-scale self-block bounds individually are all below the full bound too
    for block in range(3):
        base = block * AXIS_DIM
        sub = [row[base : base + AXIS_DIM] for row in diagonal_only[base : base + AXIS_DIM]]
        assert spectral_l2_upper_bound(sub) <= diagonal_bound

    # prove the full bound genuinely used the cross-scale coupling rows: the
    # lower-left blocks (mid<-fast, slow<-fast, slow<-mid) are nonzero.
    assert any(reference[r][c] != 0.0 for r in range(8, 16) for c in range(0, 8))  # mid <- fast
    assert any(reference[r][c] != 0.0 for r in range(16, 24) for c in range(0, 8))  # slow <- fast
    assert any(reference[r][c] != 0.0 for r in range(16, 24) for c in range(8, 16))  # slow <- mid
    # ...and the upper-right blocks stay zero (strictly triangular, causal order)
    assert all(reference[r][c] == 0.0 for r in range(0, 8) for c in range(8, 24))
    assert all(reference[r][c] == 0.0 for r in range(8, 16) for c in range(16, 24))
