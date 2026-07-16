"""Population and time coding for the deterministic v3 spiking path (design 8.1).

Each valid scalar observation channel is population-coded around the three fixed
centers ``{0, 0.5, 1}``, producing three encoder units.  The 36 channels give
exactly :data:`~sylanne_alpha.v3core.formula_v1.POPULATION_INPUT_COUNT` (108)
inputs ordered channel-major / center-inner, so ``input_index = 3*channel + r``
for center rank ``r`` in ``0,1,2``.

Every unit emits a single deterministic latency spike when its response
``q >= 0.08`` and a second spike at ``min(K-1, latency + floor(K/2))`` when
``q >= 0.75`` and that index differs from the first.  All three units of an
invalid channel stay silent for the complete horizon, and no probabilistic
spike insertion is ever used.  This module is pure stdlib math over immutable
tuples: no NumPy, no I/O, no clocks, no randomness.
"""

from __future__ import annotations

from math import exp

from ..formula_v1 import (
    OBSERVATION_DIM,
    POPULATION_INPUT_COUNT,
    SNN_CODING_CENTERS,
    SNN_CODING_SECOND_SPIKE_Q,
    SNN_CODING_SIGMA,
    SNN_CODING_SPIKE_Q_FLOOR,
    SNN_CODING_UNITS_PER_CHANNEL,
    SNN_ALLOWED_TICKS,
    spike_latency,
)
from ..observation.models import ObservationFrame

_TWO_SIGMA_SQUARED = 2.0 * SNN_CODING_SIGMA * SNN_CODING_SIGMA


def _check_ticks(ticks: int) -> None:
    if type(ticks) is not int or isinstance(ticks, bool) or ticks not in SNN_ALLOWED_TICKS:
        raise ValueError("ticks must be one of the allowed v1 tick counts")


def encode_unit(value: float, center: float, ticks: int) -> tuple[int, ...]:
    """Return the deterministic spike ticks for one population-coding unit.

    ``q = exp(-(value-center)^2 / (2*sigma^2))``.  A unit below the ``q`` floor
    stays silent; otherwise it fires once at ``latency`` and, when ``q`` reaches
    the second-spike response, again at ``min(K-1, latency + floor(K/2))`` if that
    tick differs from the first.
    """

    q = exp(-((value - center) ** 2) / _TWO_SIGMA_SQUARED)
    if q < SNN_CODING_SPIKE_Q_FLOOR:
        return ()
    latency = spike_latency(q, ticks)
    if q < SNN_CODING_SECOND_SPIKE_Q:
        return (latency,)
    second = min(ticks - 1, latency + ticks // 2)
    if second == latency:
        return (latency,)
    return (latency, second)


def population_spike_trains(frame: object, ticks: int) -> tuple[tuple[int, ...], ...]:
    """Encode a frame into 108 per-unit spike trains (channel-major, center-inner).

    Only valid channels (``valid_mask`` bit set) are coded; every unit of an
    invalid channel is an empty tuple.  Changing an invalid channel's raw value
    can therefore never change any spike train.
    """

    if type(frame) is not ObservationFrame:
        raise TypeError("frame must have exact type ObservationFrame")
    _check_ticks(ticks)

    trains: list[tuple[int, ...]] = []
    for channel in range(OBSERVATION_DIM):
        if frame.is_valid(channel):
            value = frame.values[channel]
            for center in SNN_CODING_CENTERS:
                trains.append(encode_unit(value, center, ticks))
        else:
            trains.extend(() for _ in range(SNN_CODING_UNITS_PER_CHANNEL))
    if len(trains) != POPULATION_INPUT_COUNT:
        raise ValueError("population coding must produce exactly POPULATION_INPUT_COUNT trains")
    return tuple(trains)


def spikes_by_tick(spike_trains: tuple[tuple[int, ...], ...], ticks: int) -> tuple[tuple[int, ...], ...]:
    """Invert per-unit trains into per-tick tuples of firing input-unit indices."""

    _check_ticks(ticks)
    if type(spike_trains) is not tuple or len(spike_trains) != POPULATION_INPUT_COUNT:
        raise ValueError("spike_trains must be POPULATION_INPUT_COUNT trains")
    buckets: list[list[int]] = [[] for _ in range(ticks)]
    for unit_index, train in enumerate(spike_trains):
        for tick in train:
            if type(tick) is not int or not 0 <= tick < ticks:
                raise ValueError("spike tick out of the horizon")
            if not buckets[tick] or buckets[tick][-1] != unit_index:
                buckets[tick].append(unit_index)
    return tuple(tuple(bucket) for bucket in buckets)


__all__ = ["encode_unit", "population_spike_trains", "spikes_by_tick"]
