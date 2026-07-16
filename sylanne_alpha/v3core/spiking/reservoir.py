"""Leaky integrate-and-fire reservoir dynamics (design section 8.2).

96 Dale-typed neurons (77 excitatory, 19 inhibitory) with a deterministic sparse
recurrent topology and no self-loops advance over ``K`` virtual ticks:

    I_i[k]   = clip(B_i*z_in[k] + W_i*z[k-1], -3, 3)
    v_i[k+1] = clip(beta_K*v_i[k] + (1-beta_K)*I_i[k], -2, 2)
    z_i[k+1] = 1[v_i[k+1] >= theta_i and refractory_i == 0]

After a spike, voltage resets to zero and the refractory counter becomes
``refractory_K``.  Intrinsic threshold adaptation happens once after the complete
horizon.  When STDP eligibility is accumulated, the per-neuron pre/post traces
and the per-synapse eligibility tensor evolve alongside the membrane using the
K-adjusted decays.  Any non-finite value rolls back the complete SNN
subtransaction.  Pure stdlib math over immutable tuples: no NumPy, no I/O, no
clocks, no randomness.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from ..formula_v1 import (
    INPUT_TOPOLOGY,
    INPUT_WEIGHT,
    PLASTIC_SYNAPSES,
    RECURRENT_TOPOLOGY,
    SNN_ELIGIBILITY_CLIP,
    SNN_INPUT_CURRENT_CLIP,
    SNN_NEURONS,
    SNN_PRE_POST_TRACE_CLIP,
    SNN_RESET_VOLTAGE,
    SNN_STDP_ANTI_HEBBIAN,
    SNN_SUMMARY_DIM,
    SNN_SUMMARY_POOLS,
    SNN_THRESHOLD_ADAPT_RATE,
    SNN_THRESHOLD_BOUNDS,
    SNN_THRESHOLD_TARGET_RATE,
    SNN_VOLTAGE_CLIP,
    recurrent_initial_weight,
    recurrent_is_plastic,
    snn_horizon_decays,
)
from ..observation.models import ObservationFrame
from ..state.models import SnnState
from .coding import population_spike_trains, spikes_by_tick

_N = SNN_NEURONS
_I_LO, _I_HI = SNN_INPUT_CURRENT_CLIP
_V_LO, _V_HI = SNN_VOLTAGE_CLIP
_TRACE_LO, _TRACE_HI = SNN_PRE_POST_TRACE_CLIP
_ELIG_LO, _ELIG_HI = SNN_ELIGIBILITY_CLIP
_THETA_LO, _THETA_HI = SNN_THRESHOLD_BOUNDS
_PLASTIC_SYN = PLASTIC_SYNAPSES
_COUNT = len(PLASTIC_SYNAPSES)
_ANTI_HEBBIAN = SNN_STDP_ANTI_HEBBIAN


# --------------------------------------------------------------------------- #
# Precomputed adjacency (pure, from the frozen formula topology)
# --------------------------------------------------------------------------- #

_PLASTIC_INDEX: dict[tuple[int, int], int] = {edge: index for index, edge in enumerate(PLASTIC_SYNAPSES)}


def _build_recurrent_out() -> tuple[tuple[tuple[int, float], ...], ...]:
    """Fixed (non-plastic) outgoing edges per presynaptic neuron: ``pre -> [(post, w)]``."""

    out: list[list[tuple[int, float]]] = [[] for _ in range(_N)]
    for post in range(_N):
        for pre in RECURRENT_TOPOLOGY[post]:
            if not recurrent_is_plastic(post, pre):
                out[pre].append((post, recurrent_initial_weight(post, pre)))
    return tuple(tuple(edges) for edges in out)


def _build_plastic_out() -> tuple[tuple[tuple[int, int], ...], ...]:
    """Plastic outgoing edges per presynaptic neuron: ``pre -> [(post, plastic_index)]``."""

    out: list[list[tuple[int, int]]] = [[] for _ in range(_N)]
    for (post, pre), index in _PLASTIC_INDEX.items():
        out[pre].append((post, index))
    return tuple(tuple(edges) for edges in out)


_REC_OUT_FIXED = _build_recurrent_out()
_REC_OUT_PLASTIC = _build_plastic_out()


# --------------------------------------------------------------------------- #
# Result container (unregistered pure result DTO, mirroring MultiscaleAdvance)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ReservoirResult:
    """Bounded result of one reservoir horizon.

    On ``rolled_back`` the complete SNN subtransaction is discarded: ``snn`` is the
    unchanged previous state and every derived array is neutral.
    """

    snn: SnnState
    spike_counts: tuple[int, ...]
    first_latencies: tuple[int, ...]
    firing_rates: tuple[float, ...]
    summary: tuple[float, ...]
    rolled_back: bool


# --------------------------------------------------------------------------- #
# Small pure helpers
# --------------------------------------------------------------------------- #


def _clip(value: float, low: float, high: float) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return value


def adapt_thresholds(thresholds: tuple[float, ...], spike_counts: tuple[int, ...], ticks: int) -> tuple[float, ...]:
    """Intrinsic threshold adaptation applied once after the complete horizon."""

    return tuple(
        _clip(
            thresholds[i] + SNN_THRESHOLD_ADAPT_RATE * (spike_counts[i] / ticks - SNN_THRESHOLD_TARGET_RATE),
            _THETA_LO,
            _THETA_HI,
        )
        for i in range(_N)
    )


def pooled_summary(spike_counts: tuple[int, ...], first_latencies: tuple[int, ...], ticks: int) -> tuple[float, ...]:
    """The fixed 16-dimensional summary: 8 pool rates then 8 latency confidences."""

    rates: list[float] = []
    confidences: list[float] = []
    for low, high in SNN_SUMMARY_POOLS:
        pool_size = high - low
        rate = sum(spike_counts[i] / ticks for i in range(low, high)) / pool_size
        rates.append(_clip(rate, 0.0, 1.0))
        pool_latencies = [first_latencies[i] for i in range(low, high) if first_latencies[i] >= 0]
        if not pool_latencies:
            confidences.append(0.0)
        else:
            confidences.append(1.0 - min(pool_latencies) / (ticks - 1))
    return tuple(rates + confidences)


def update_eligibility(
    eligibility: tuple[float, ...],
    z: tuple[float, ...],
    pre_prev: tuple[float, ...],
    post_prev: tuple[float, ...],
    elig_decay: float,
) -> tuple[float, ...]:
    """One virtual-step reward-gated eligibility update over the plastic synapses.

    ``e_ij = clip(elig_decay*e_ij + z_i*pre_j(previous) - anti_hebbian*z_j*post_i(previous), -3, 3)``
    where ``i`` is the postsynaptic and ``j`` the presynaptic neuron.
    """

    updated: list[float] = []
    for index, (post_i, pre_j) in enumerate(PLASTIC_SYNAPSES):
        value = (
            elig_decay * eligibility[index]
            + z[post_i] * pre_prev[pre_j]
            - SNN_STDP_ANTI_HEBBIAN * z[pre_j] * post_prev[post_i]
        )
        updated.append(_clip(value, _ELIG_LO, _ELIG_HI))
    return tuple(updated)


def update_traces(
    pre: tuple[float, ...],
    post: tuple[float, ...],
    z: tuple[float, ...],
    pre_decay: float,
    post_decay: float,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """One virtual-step pre/post trace update: ``trace = clip(decay*trace + z, 0, 3)``."""

    new_pre = tuple(_clip(pre_decay * pre[i] + z[i], _TRACE_LO, _TRACE_HI) for i in range(_N))
    new_post = tuple(_clip(post_decay * post[i] + z[i], _TRACE_LO, _TRACE_HI) for i in range(_N))
    return new_pre, new_post


def build_snn_or_rollback(
    previous: SnnState,
    voltages: tuple[float, ...],
    thresholds: tuple[float, ...],
    pre_trace: tuple[float, ...],
    post_trace: tuple[float, ...],
    plastic_weights: tuple[float, ...],
    eligibility: tuple[float, ...],
) -> tuple[SnnState, bool]:
    """Build a new :class:`SnnState`, or roll back the whole subtransaction.

    Any non-finite value (or any value the frozen :class:`SnnState` bounds reject)
    discards the complete candidate and returns the unchanged ``previous`` state.
    """

    for array in (voltages, thresholds, pre_trace, post_trace, plastic_weights, eligibility):
        for value in array:
            if not isfinite(value):
                return previous, True
    try:
        built = SnnState(
            voltages=voltages,
            thresholds=thresholds,
            pre_trace=pre_trace,
            post_trace=post_trace,
            plastic_weights=plastic_weights,
            eligibility=eligibility,
        )
    except (ValueError, TypeError):
        return previous, True
    return built, False


def _rolled_back(previous: SnnState) -> ReservoirResult:
    zeros_int = tuple(0 for _ in range(_N))
    return ReservoirResult(
        snn=previous,
        spike_counts=zeros_int,
        first_latencies=tuple(-1 for _ in range(_N)),
        firing_rates=tuple(0.0 for _ in range(_N)),
        summary=tuple(0.0 for _ in range(SNN_SUMMARY_DIM)),
        rolled_back=True,
    )


# --------------------------------------------------------------------------- #
# Forward pass
# --------------------------------------------------------------------------- #


def run_reservoir(
    snn: object,
    spikes: tuple[tuple[int, ...], ...],
    ticks: int,
    accumulate_eligibility: bool,
) -> ReservoirResult:
    """Advance the reservoir over ``ticks`` virtual steps from ``snn``.

    ``spikes`` is the per-tick tuple of firing input-unit indices (see
    :func:`~sylanne_alpha.v3core.spiking.coding.spikes_by_tick`).  When
    ``accumulate_eligibility`` is false the STDP pre/post traces and eligibility
    pass through unchanged (non-STDP profiles); plastic weights are never modified
    by the forward pass in either case (STDP settles at ``t+1``).
    """

    if type(snn) is not SnnState:
        raise TypeError("snn must have exact type SnnState")
    if type(accumulate_eligibility) is not bool:
        raise TypeError("accumulate_eligibility must be a bool")
    beta, pre_decay, post_decay, elig_decay, refractory_k = snn_horizon_decays(ticks)
    if type(spikes) is not tuple or len(spikes) != ticks:
        raise ValueError("spikes must contain exactly `ticks` per-tick tuples")

    # Mutable working copies; the hot loops inline the clip/update arithmetic (the
    # standalone update_* helpers above carry the same semantics for direct tests,
    # but function-call + tuple-allocation overhead is avoided in the tick loop).
    voltages = list(snn.voltages)
    thresholds = snn.thresholds
    pre = list(snn.pre_trace)
    post = list(snn.post_trace)
    elig = list(snn.eligibility)
    plastic_weights = snn.plastic_weights
    one_minus_beta = 1.0 - beta

    refractory = [0] * _N
    spike_counts = [0] * _N
    first_latency = [-1] * _N
    z_prev = [0.0] * _N

    for tick in range(ticks):
        # input current: scatter INPUT_WEIGHT from each firing input unit to its targets
        drive = [0.0] * _N
        for unit in spikes[tick]:
            for target in INPUT_TOPOLOGY[unit]:
                drive[target] += INPUT_WEIGHT
        # recurrent current: scatter from each firing presynaptic neuron
        for pre_neuron in range(_N):
            if z_prev[pre_neuron]:
                for post_neuron, weight in _REC_OUT_FIXED[pre_neuron]:
                    drive[post_neuron] += weight
                for post_neuron, plastic_index in _REC_OUT_PLASTIC[pre_neuron]:
                    drive[post_neuron] += plastic_weights[plastic_index]

        z = [0.0] * _N
        for i in range(_N):
            current = drive[i]
            if current < _I_LO:
                current = _I_LO
            elif current > _I_HI:
                current = _I_HI
            new_voltage = beta * voltages[i] + one_minus_beta * current
            if new_voltage < _V_LO:
                new_voltage = _V_LO
            elif new_voltage > _V_HI:
                new_voltage = _V_HI
            if refractory[i] == 0 and new_voltage >= thresholds[i]:
                z[i] = 1.0
                voltages[i] = SNN_RESET_VOLTAGE
                refractory[i] = refractory_k
                spike_counts[i] += 1
                if first_latency[i] == -1:
                    first_latency[i] = tick
            else:
                voltages[i] = new_voltage
                if refractory[i] > 0:
                    refractory[i] -= 1

        if accumulate_eligibility:
            for index in range(_COUNT):
                post_i, pre_j = _PLASTIC_SYN[index]
                value = (
                    elig_decay * elig[index]
                    + z[post_i] * pre[pre_j]
                    - _ANTI_HEBBIAN * z[pre_j] * post[post_i]
                )
                if value < _ELIG_LO:
                    value = _ELIG_LO
                elif value > _ELIG_HI:
                    value = _ELIG_HI
                elig[index] = value
            for i in range(_N):
                zp = z[i]
                new_pre = pre_decay * pre[i] + zp
                pre[i] = _TRACE_HI if new_pre > _TRACE_HI else new_pre
                new_post = post_decay * post[i] + zp
                post[i] = _TRACE_HI if new_post > _TRACE_HI else new_post
        z_prev = z

    new_thresholds = adapt_thresholds(thresholds, tuple(spike_counts), ticks)
    built, rolled_back = build_snn_or_rollback(
        snn,
        tuple(voltages),
        new_thresholds,
        tuple(pre),
        tuple(post),
        plastic_weights,
        tuple(elig),
    )
    if rolled_back:
        return _rolled_back(snn)

    counts = tuple(spike_counts)
    latencies = tuple(first_latency)
    return ReservoirResult(
        snn=built,
        spike_counts=counts,
        first_latencies=latencies,
        firing_rates=tuple(count / ticks for count in counts),
        summary=pooled_summary(counts, latencies, ticks),
        rolled_back=False,
    )


def run_reservoir_from_frame(
    snn: object,
    frame: object,
    ticks: int,
    accumulate_eligibility: bool,
) -> ReservoirResult:
    """Convenience: population-code ``frame`` then advance the reservoir."""

    if type(frame) is not ObservationFrame:
        raise TypeError("frame must have exact type ObservationFrame")
    trains = population_spike_trains(frame, ticks)
    return run_reservoir(snn, spikes_by_tick(trains, ticks), ticks, accumulate_eligibility)


__all__ = [
    "ReservoirResult",
    "adapt_thresholds",
    "build_snn_or_rollback",
    "pooled_summary",
    "run_reservoir",
    "run_reservoir_from_frame",
    "update_eligibility",
    "update_traces",
]
