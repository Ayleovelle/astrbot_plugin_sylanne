"""Frozen result model for the multi-timescale dynamics stage.

:class:`MultiscaleAdvance` is a pure container: it self-validates its shape,
finiteness, and bounds without touching the sealed canonical registry, mirroring
the frozen :class:`~sylanne_alpha.v3core.observation.models.ObservationFrame`
style.  It carries the eight-dimensional bounded ``drive`` (a ``tanh`` output in
``[-1,1]``) and the advanced 24-dimensional latent axes, plus whether the state
actually advanced this call and the resulting revision.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from ..canonical import assert_exact_type
from ..formula_v1 import AXIS_DIM, STATE_DIM


def _check_float_vector(values: object, length: int, low: float, high: float, name: str) -> None:
    assert_exact_type(values, tuple, name)
    if len(values) != length:
        raise ValueError(f"{name} must have exactly {length} entries")
    for index, value in enumerate(values):
        assert_exact_type(value, float, f"{name}[{index}]")
        if not isfinite(value):
            raise ValueError(f"{name}[{index}] must be finite")
        if not low <= value <= high:
            raise ValueError(f"{name}[{index}] must lie in [{low}, {high}]")


@dataclass(frozen=True, slots=True)
class MultiscaleAdvance:
    """The bounded result of one dynamics advance.

    ``drive`` is the eight-dimensional ``tanh`` drive in ``[-1,1]``.
    ``next_latent_axes`` is the 24-dimensional advanced state.  On an advance it
    lies in ``[-1,1]`` (the update clips every coordinate); on an idempotent
    no-op or a deterministic fallback it is the previous state's axes verbatim,
    which the enclosing :class:`V3State` bounds to ``[-16,16]`` — so this DTO
    permits that wider persistence bound.
    """

    drive: tuple
    next_latent_axes: tuple
    advanced: bool
    revision: int

    def __post_init__(self) -> None:
        _check_float_vector(self.drive, AXIS_DIM, -1.0, 1.0, "drive")
        _check_float_vector(self.next_latent_axes, STATE_DIM, -16.0, 16.0, "next_latent_axes")
        assert_exact_type(self.advanced, bool, "advanced")
        assert_exact_type(self.revision, int, "revision")
        if self.revision < 0:
            raise ValueError("revision must be non-negative")


__all__ = ["MultiscaleAdvance"]
