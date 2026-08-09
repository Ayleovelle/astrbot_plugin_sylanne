"""Pure read-side features derived from the 24-dimensional latent axes.

The multi-timescale dynamics (section 9) evolves 24 latent values laid out as
three contiguous timescale blocks ``[fast(0..7) | mid(8..15) | slow(16..23)]`` in
axis order.  Downstream cognition (the SNN drive coupling, the global workspace,
and finite-action inference) never reads the raw 24 values directly; it reads the
eight-dimensional *decision state* defined in design section 11.2:

    s = clip(0.50*fast + 0.30*mid + 0.20*slow, -1, 1)

This module is the single, versioned place that turns advanced latent axes into
that read view.  It is pure ``v3core`` stdlib math over immutable tuples and adds
no state of its own.
"""

from __future__ import annotations

import math

from .formula_v1 import AXIS_DIM, DECISION_STATE_BLEND, STATE_DIM


def _check_latent(latent_axes: object) -> tuple:
    if type(latent_axes) is not tuple:
        raise TypeError("latent_axes must be a tuple")
    if len(latent_axes) != STATE_DIM:
        raise ValueError(f"latent_axes must have exactly {STATE_DIM} entries")
    for index, value in enumerate(latent_axes):
        if type(value) is not float:
            raise TypeError(f"latent_axes[{index}] must be a float")
        if not math.isfinite(value):
            raise ValueError(f"latent_axes[{index}] must be finite")
    return latent_axes


def split_timescales(latent_axes: tuple) -> tuple[tuple, tuple, tuple]:
    """Split the 24 latent axes into the ``(fast, mid, slow)`` 8-vectors."""

    values = _check_latent(latent_axes)
    return (
        values[0:AXIS_DIM],
        values[AXIS_DIM : 2 * AXIS_DIM],
        values[2 * AXIS_DIM : 3 * AXIS_DIM],
    )


def _clip(value: float) -> float:
    if value < -1.0:
        return -1.0
    if value > 1.0:
        return 1.0
    return value


def decision_state(latent_axes: tuple) -> tuple:
    """Return the eight-dimensional decision state ``s`` (design section 11.2).

    ``s_i = clip(0.50*fast_i + 0.30*mid_i + 0.20*slow_i, -1, 1)``.
    """

    fast, mid, slow = split_timescales(latent_axes)
    weight_fast, weight_mid, weight_slow = DECISION_STATE_BLEND
    return tuple(
        _clip(weight_fast * fast[i] + weight_mid * mid[i] + weight_slow * slow[i])
        for i in range(AXIS_DIM)
    )


__all__ = ["DECISION_STATE_BLEND", "decision_state", "split_timescales"]
