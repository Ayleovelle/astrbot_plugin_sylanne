"""Deterministic multi-timescale dynamics (design section 9).

Eight named axes each carry fast/mid/slow state (24 values in ``[-1,1]``).  A turn
projects the observation frame into an eight-dimensional bounded ``drive`` and then
advances the three timescales in the strict sequential order ``fast -> mid -> slow``:

    drive       = tanh(P*(effective_obs - semantic_default))
    target_fast = tanh(W_fast*fast + U_fast*drive)
    fast'       = clip(fast + 0.50*(target_fast - fast), -1, 1)
    target_mid  = tanh(W_mid*mid   + U_mid*fast')
    mid'        = clip(mid  + 0.12*(target_mid  - mid),  -1, 1)
    target_slow = tanh(W_slow*slow + U_slow*mid')
    slow'       = clip(slow + 0.02*(target_slow - slow), -1, 1)

Because ``bias = -P @ SEMANTIC_DEFAULTS`` (formula-v1 ``P_BIAS``), the algebraic
form ``P*obs + bias`` equals ``P*(obs - semantic_default)``; the difference form
is used here so an invalid channel contributes exactly nothing and the complete
semantic-default frame yields a bit-exact zero drive.

Everything is pure stdlib float math over immutable tuples: no NumPy, no I/O, no
clocks, no callbacks.  Any non-finite or out-of-bound advanced state falls back
to the previous state deterministically.
"""

from __future__ import annotations

from dataclasses import replace
from math import fsum, isfinite, sqrt, tanh

from ..formula_v1 import (
    AXIS_DIM,
    DYNAMICS_STEP_SIZES,
    JACOBIAN_STABILITY_LIMIT,
    OBSERVATION_DIM,
    P_TRIPLES,
    SEMANTIC_DEFAULTS,
    STATE_DIM,
    U_FAST,
    U_MID,
    U_SLOW,
    W_FAST,
    W_MID,
    W_SLOW,
)
from ..observation.models import ObservationFrame
from ..state.models import V3State
from .models import MultiscaleAdvance

_STATE_BOUND = 1.0


# --------------------------------------------------------------------------- #
# Hand-written dense/sparse linear-algebra helpers (no NumPy)
# --------------------------------------------------------------------------- #


def _clip_unit(value: float) -> float:
    if value < -_STATE_BOUND:
        return -_STATE_BOUND
    if value > _STATE_BOUND:
        return _STATE_BOUND
    return value


def _matvec(matrix: tuple, vector: tuple) -> tuple:
    """Dense 8x8 matrix-vector product using correctly-rounded summation."""

    return tuple(fsum(matrix[i][j] * vector[j] for j in range(AXIS_DIM)) for i in range(AXIS_DIM))


def _tanh_layer(self_matrix: tuple, self_vector: tuple, coupling_matrix: tuple, upstream: tuple) -> tuple:
    """``tanh(self_matrix @ self_vector + coupling_matrix @ upstream)`` per axis."""

    self_term = _matvec(self_matrix, self_vector)
    coupling_term = _matvec(coupling_matrix, upstream)
    return tuple(tanh(self_term[i] + coupling_term[i]) for i in range(AXIS_DIM))


# --------------------------------------------------------------------------- #
# Drive
# --------------------------------------------------------------------------- #


def compute_drive(frame: object) -> tuple:
    """Project the observation frame into the 8-axis drive.

    An invalid channel is replaced by its semantic default, so its centered
    contribution ``(effective - default)`` is exactly ``0.0`` and changing an
    invalid channel's raw value can never change the drive.  (formula v2 deleted
    the ``Q*snn_summary`` coupling: the reservoir summary was permanently zero, so
    the term was already inert, and the reservoir itself is gone.)
    """

    if type(frame) is not ObservationFrame:
        raise TypeError("frame must have exact type ObservationFrame")

    centered = tuple(
        (frame.values[channel] - SEMANTIC_DEFAULTS[channel]) if frame.is_valid(channel) else 0.0
        for channel in range(OBSERVATION_DIM)
    )

    axis_terms: list[list[float]] = [[] for _ in range(AXIS_DIM)]
    for axis, channel, weight in P_TRIPLES:
        axis_terms[axis].append(weight * centered[channel])

    return tuple(tanh(fsum(axis_terms[axis])) for axis in range(AXIS_DIM))


# --------------------------------------------------------------------------- #
# Sequential fast -> mid -> slow update
# --------------------------------------------------------------------------- #


def _advance_axes(latent_axes: tuple, drive: tuple) -> tuple:
    """Pure section-9 sequential update; returns 24 clipped-to-[-1,1] values."""

    fast = latent_axes[0:AXIS_DIM]
    mid = latent_axes[AXIS_DIM : 2 * AXIS_DIM]
    slow = latent_axes[2 * AXIS_DIM : 3 * AXIS_DIM]
    step_fast, step_mid, step_slow = DYNAMICS_STEP_SIZES

    target_fast = _tanh_layer(W_FAST, fast, U_FAST, drive)
    fast_next = tuple(_clip_unit(fast[i] + step_fast * (target_fast[i] - fast[i])) for i in range(AXIS_DIM))

    target_mid = _tanh_layer(W_MID, mid, U_MID, fast_next)
    mid_next = tuple(_clip_unit(mid[i] + step_mid * (target_mid[i] - mid[i])) for i in range(AXIS_DIM))

    target_slow = _tanh_layer(W_SLOW, slow, U_SLOW, mid_next)
    slow_next = tuple(_clip_unit(slow[i] + step_slow * (target_slow[i] - slow[i])) for i in range(AXIS_DIM))

    return fast_next + mid_next + slow_next


def select_valid_next_axes(previous_axes: tuple, candidate_axes: tuple) -> tuple:
    """Deterministic fallback: accept ``candidate_axes`` only if finite and in [-1,1]."""

    if type(candidate_axes) is not tuple or len(candidate_axes) != STATE_DIM:
        return previous_axes
    for value in candidate_axes:
        if type(value) is not float or not isfinite(value) or not -_STATE_BOUND <= value <= _STATE_BOUND:
            return previous_axes
    return candidate_axes


def advance_dynamics(state: object, frame: object, turn_revision: int) -> MultiscaleAdvance:
    """Advance the latent axes for one committed turn revision (idempotent per revision).

    The state advances only when ``turn_revision`` is strictly greater than the
    state's current revision; a repeated call with the same revision is a no-op.
    A non-finite or out-of-bound advanced state falls back to the previous axes.
    """

    if type(state) is not V3State:
        raise TypeError("state must have exact type V3State")
    if type(turn_revision) is not int or isinstance(turn_revision, bool):
        raise TypeError("turn_revision must be an int")

    drive = compute_drive(frame)

    if turn_revision <= state.revision:
        return MultiscaleAdvance(
            drive=drive,
            next_latent_axes=state.latent_axes,
            advanced=False,
            revision=state.revision,
        )

    candidate = _advance_axes(state.latent_axes, drive)
    safe = select_valid_next_axes(state.latent_axes, candidate)
    advanced = safe is candidate
    return MultiscaleAdvance(
        drive=drive,
        next_latent_axes=safe,
        advanced=advanced,
        revision=turn_revision if advanced else state.revision,
    )


def advance_state(state: object, frame: object, turn_revision: int) -> V3State:
    """Return a new :class:`V3State` with advanced latent axes, or the input unchanged.

    On an idempotent no-op or a deterministic fallback the original ``state`` is
    returned unchanged (identity-preserving); otherwise a new frozen state with
    the advanced axes and ``turn_revision`` is produced.
    """

    result = advance_dynamics(state, frame, turn_revision)
    if not result.advanced:
        return state  # type: ignore[return-value]
    return replace(state, latent_axes=result.next_latent_axes, revision=result.revision)


# --------------------------------------------------------------------------- #
# Full sequential 24x24 entrywise-absolute Jacobian bound (the stability gate)
# --------------------------------------------------------------------------- #


def _self_block(matrix: tuple, alpha: float) -> tuple:
    """Entrywise absolute bound of ``d x'/d x`` for ``x' = x + alpha*(tanh(W x + .) - x)``.

    ``|(1-alpha)delta_ij + alpha*tanh'*W_ij| <= (1-alpha)delta_ij + alpha*|W_ij|``
    using ``|tanh'| <= 1`` and ``0 < alpha <= 1``.
    """

    return tuple(
        tuple(
            (1.0 - alpha if i == j else 0.0) + alpha * abs(matrix[i][j])
            for j in range(AXIS_DIM)
        )
        for i in range(AXIS_DIM)
    )


def _feedforward_block(matrix: tuple, alpha: float) -> tuple:
    """Entrywise absolute bound of ``d x'/d (upstream)`` = ``alpha*|U|``."""

    return tuple(tuple(alpha * abs(matrix[i][j]) for j in range(AXIS_DIM)) for i in range(AXIS_DIM))


def _block_matmul(left: tuple, right: tuple) -> tuple:
    """Non-negative 8x8 block product (bounds compose because all entries are >= 0)."""

    return tuple(
        tuple(
            sum(left[i][k] * right[k][j] for k in range(AXIS_DIM))
            for j in range(AXIS_DIM)
        )
        for i in range(AXIS_DIM)
    )


def jacobian_absolute_upper_bound_full() -> tuple:
    """Build the complete sequential fast->mid->slow 24x24 entrywise-absolute bound.

    Rows are target axes, columns are source axes.  Because the update is
    sequential (mid reads fast', slow reads mid'), the lower-left blocks carry the
    cross-scale derivatives through the chain rule:

        d mid'/d fast  = (d mid'/d fast')(d fast'/d fast) = alpha_mid|U_mid| @ block_a
        d slow'/d mid  = (d slow'/d mid')(d mid'/d mid)   = alpha_slow|U_slow| @ block_b
        d slow'/d fast = (d slow'/d mid')(d mid'/d fast)  = alpha_slow|U_slow| @ block_c
    """

    step_fast, step_mid, step_slow = DYNAMICS_STEP_SIZES
    block_a = _self_block(W_FAST, step_fast)  # d fast'/d fast
    block_b = _self_block(W_MID, step_mid)  # d mid'/d mid
    block_f = _self_block(W_SLOW, step_slow)  # d slow'/d slow
    mid_from_fast = _feedforward_block(U_MID, step_mid)  # d mid'/d fast'
    slow_from_mid = _feedforward_block(U_SLOW, step_slow)  # d slow'/d mid'
    block_c = _block_matmul(mid_from_fast, block_a)  # d mid'/d fast
    block_d = _block_matmul(slow_from_mid, block_b)  # d slow'/d mid
    block_e = _block_matmul(slow_from_mid, block_c)  # d slow'/d fast
    zero = tuple((0.0,) * AXIS_DIM for _ in range(AXIS_DIM))
    rows: list[tuple] = []
    for r in range(AXIS_DIM):
        rows.append(block_a[r] + zero[r] + zero[r])
    for r in range(AXIS_DIM):
        rows.append(block_c[r] + block_b[r] + zero[r])
    for r in range(AXIS_DIM):
        rows.append(block_e[r] + block_d[r] + block_f[r])
    return tuple(rows)


def spectral_l2_upper_bound(matrix: tuple) -> float:
    """``sqrt(||matrix||_1 * ||matrix||_inf)`` — an upper bound on the 2-norm."""

    dimension = len(matrix)
    norm_one = max(fsum(matrix[r][c] for r in range(dimension)) for c in range(dimension))
    norm_infinity = max(fsum(matrix[r]) for r in range(dimension))
    return sqrt(norm_one * norm_infinity)


def multiscale_jacobian_bound() -> float:
    """The complete-sequential-Jacobian 2-norm upper bound for the formula-v1 update."""

    return spectral_l2_upper_bound(jacobian_absolute_upper_bound_full())


def validate_jacobian_gate() -> float:
    """Prove the full sequential bound is below the analytic stability limit.

    Rejects any block-diagonal-only shortcut by construction: the bound is taken
    over the whole 24x24 matrix (including the cross-scale coupling rows).
    """

    bound = multiscale_jacobian_bound()
    if not isfinite(bound):
        raise ValueError("multiscale Jacobian bound is not finite")
    if not bound < JACOBIAN_STABILITY_LIMIT:
        raise ValueError("multiscale dynamics fails the analytic Jacobian stability gate")
    return bound


__all__ = [
    "advance_dynamics",
    "advance_state",
    "compute_drive",
    "jacobian_absolute_upper_bound_full",
    "multiscale_jacobian_bound",
    "select_valid_next_axes",
    "spectral_l2_upper_bound",
    "validate_jacobian_gate",
]
