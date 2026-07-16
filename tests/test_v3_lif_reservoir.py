"""RED/GREEN tests for Task 8 LIF reservoir dynamics (design section 8.2).

The reservoir is pure ``v3core``: 96 Dale-typed neurons (77 excitatory, 19
inhibitory) with a deterministic sparse recurrent topology and no self-loops
advance over ``K`` virtual ticks.  It outputs firing rate, first-spike latency,
spike counts, and a fixed 16-dimensional pooled summary, and it rolls back the
complete SNN subtransaction on any non-finite value.
"""

from __future__ import annotations

import math

import pytest

from sylanne_alpha.v3core import formula_v1 as formula
from sylanne_alpha.v3core.observation.models import ObservationFrame
from sylanne_alpha.v3core.spiking import coding, reservoir
from sylanne_alpha.v3core.state.models import PLASTIC_SYNAPSE_COUNT, SnnState

N = formula.SNN_NEURONS
SUMMARY_DIM = formula.SNN_SUMMARY_DIM


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #


def _seed_snn(*, voltage: float = 0.0, threshold: float = 1.0) -> SnnState:
    return SnnState(
        voltages=tuple(voltage for _ in range(N)),
        thresholds=tuple(threshold for _ in range(N)),
        pre_trace=tuple(0.0 for _ in range(N)),
        post_trace=tuple(0.0 for _ in range(N)),
        plastic_weights=tuple(formula.RECURRENT_EE_WEIGHT for _ in range(PLASTIC_SYNAPSE_COUNT)),
        eligibility=tuple(0.0 for _ in range(PLASTIC_SYNAPSE_COUNT)),
    )


def _frame(overrides: dict[int, float] | None = None, valid: set[int] | None = None) -> ObservationFrame:
    values = list(formula.SEMANTIC_DEFAULTS)
    for channel, value in (overrides or {}).items():
        values[channel] = value
    mask = 0
    for channel in valid or set():
        mask |= 1 << channel
    return ObservationFrame(values=tuple(values), valid_mask=mask)


def _dense_frame() -> ObservationFrame:
    values = tuple(0.5 + 0.4 * math.sin(index) for index in range(formula.OBSERVATION_DIM))
    values = tuple(min(1.0, max(0.0, v)) for v in values)
    return ObservationFrame(values=values, valid_mask=(1 << formula.OBSERVATION_DIM) - 1)


# --------------------------------------------------------------------------- #
# Population / Dale structure
# --------------------------------------------------------------------------- #


def test_population_split_and_no_self_loops() -> None:
    assert (N, formula.SNN_EXCITATORY, formula.SNN_INHIBITORY) == (96, 77, 19)
    assert formula.SNN_EXCITATORY + formula.SNN_INHIBITORY == N
    for post in range(N):
        sources = formula.recurrent_sources(post)
        assert post not in sources
        for pre in sources:
            weight = formula.recurrent_initial_weight(post, pre)
            if pre >= formula.SNN_EXCITATORY:
                assert weight < 0.0  # inhibitory
            else:
                assert weight > 0.0  # excitatory


# --------------------------------------------------------------------------- #
# Forward pass shape, bounds, determinism
# --------------------------------------------------------------------------- #


def _run(snn: SnnState, frame: ObservationFrame, ticks: int, accumulate: bool = True):
    trains = coding.population_spike_trains(frame, ticks)
    by_tick = coding.spikes_by_tick(trains, ticks)
    return reservoir.run_reservoir(snn, by_tick, ticks, accumulate)


def test_forward_pass_shapes_and_bounds() -> None:
    result = _run(_seed_snn(voltage=1.5, threshold=0.65), _dense_frame(), 24)
    assert result.rolled_back is False
    assert type(result.snn) is SnnState
    assert len(result.spike_counts) == len(result.first_latencies) == len(result.firing_rates) == N
    assert len(result.summary) == SUMMARY_DIM == 16
    for value in result.snn.voltages:
        assert math.isfinite(value)
        assert -2.0 <= value <= 2.0
    for value in result.snn.thresholds:
        assert 0.65 <= value <= 1.35
    for count, rate in zip(result.spike_counts, result.firing_rates):
        assert type(count) is int and count >= 0
        assert rate == pytest.approx(count / 24)
    for index in range(8):
        assert 0.0 <= result.summary[index] <= 1.0  # pool firing rate
        assert 0.0 <= result.summary[8 + index] <= 1.0  # latency confidence


def test_forward_pass_is_deterministic() -> None:
    snn, frame = _seed_snn(voltage=1.5, threshold=0.65), _dense_frame()
    assert _run(snn, frame, 24).summary == _run(snn, frame, 24).summary
    assert _run(snn, frame, 24).snn.voltages == _run(snn, frame, 24).snn.voltages


def test_does_not_mutate_inputs() -> None:
    snn = _seed_snn(voltage=1.5, threshold=0.65)
    voltages, thresholds = snn.voltages, snn.thresholds
    _run(snn, _dense_frame(), 24)
    assert snn.voltages == voltages and snn.thresholds == thresholds


# --------------------------------------------------------------------------- #
# Guaranteed firing (seed above threshold) drives the 16 summaries
# --------------------------------------------------------------------------- #


def test_supra_threshold_seed_fires_every_neuron_once_then_refractory() -> None:
    # v0 = 1.5, theta = 0.65: v[0] = 0.9*1.5 + 0.1*I >= 0.65 for every neuron even
    # with no input, so all fire at tick 0, reset, and enter refractory.
    result = _run(_seed_snn(voltage=1.5, threshold=0.65), _frame(), 24)  # neutral frame, no input
    assert all(count >= 1 for count in result.spike_counts)
    assert all(latency == 0 for latency in result.first_latencies)  # first spike at tick 0
    # eight pool rates are strictly positive because pools 0..47 all fired
    assert all(result.summary[p] > 0.0 for p in range(8))
    # latency confidence for a tick-0 first spike is 1 - 0/(K-1) = 1
    assert all(result.summary[8 + p] == pytest.approx(1.0) for p in range(8))


def test_neutral_frame_with_subthreshold_seed_produces_no_spikes() -> None:
    result = _run(_seed_snn(voltage=0.0, threshold=1.0), _frame(), 24)
    assert result.spike_counts == tuple(0 for _ in range(N))
    assert result.first_latencies == tuple(-1 for _ in range(N))
    assert result.summary == tuple(0.0 for _ in range(SUMMARY_DIM))
    assert result.snn.voltages == tuple(0.0 for _ in range(N))


# --------------------------------------------------------------------------- #
# Intrinsic threshold adaptation (once per horizon)
# --------------------------------------------------------------------------- #


def test_threshold_adaptation_direction_and_clip() -> None:
    thresholds = tuple(1.0 for _ in range(N))
    # rate above target -> increase, below -> decrease, all clipped to [0.65,1.35]
    counts = tuple((6 if i == 0 else (0 if i == 1 else 2)) for i in range(N))
    adapted = reservoir.adapt_thresholds(thresholds, counts, 24)
    assert adapted[0] == pytest.approx(1.0 + 0.01 * (6 / 24 - 0.08))
    assert adapted[0] > 1.0
    assert adapted[1] == pytest.approx(1.0 + 0.01 * (0 / 24 - 0.08))
    assert adapted[1] < 1.0
    # clip: a neuron already at the floor firing nothing stays at the floor
    floor = tuple(0.65 for _ in range(N))
    assert reservoir.adapt_thresholds(floor, tuple(0 for _ in range(N)), 24)[0] == 0.65
    ceil = tuple(1.35 for _ in range(N))
    assert reservoir.adapt_thresholds(ceil, tuple(24 for _ in range(N)), 24)[0] == 1.35


def test_forward_pass_adapts_thresholds_once_after_horizon() -> None:
    # neutral frame, no spikes -> every rate 0 -> theta decreases by 0.01*0.08 once
    result = _run(_seed_snn(voltage=0.0, threshold=1.0), _frame(), 24)
    expected = max(0.65, 1.0 + 0.01 * (0.0 - 0.08))
    assert all(theta == pytest.approx(expected) for theta in result.snn.thresholds)


# --------------------------------------------------------------------------- #
# 16-dim pooled summary
# --------------------------------------------------------------------------- #


def test_pooled_summary_matches_definition() -> None:
    counts = tuple((i % 3) for i in range(N))  # deterministic synthetic counts
    latencies = tuple((i % 5) if (i % 3) else -1 for i in range(N))
    summary = reservoir.pooled_summary(counts, latencies, 24)
    assert len(summary) == 16
    for p in range(8):
        lo, hi = formula.SNN_SUMMARY_POOLS[p]
        rate = sum(counts[i] / 24 for i in range(lo, hi)) / 6
        assert summary[p] == pytest.approx(min(1.0, max(0.0, rate)))
        pool_latencies = [latencies[i] for i in range(lo, hi) if latencies[i] >= 0]
        if not pool_latencies:
            assert summary[8 + p] == 0.0
        else:
            assert summary[8 + p] == pytest.approx(1.0 - min(pool_latencies) / (24 - 1))
    # only neurons 0..47 contribute; 48..95 are recurrent context only
    assert formula.SNN_SUMMARY_POOLS[-1] == (42, 48)


# --------------------------------------------------------------------------- #
# STDP trace / eligibility machinery is gated by accumulate_eligibility
# --------------------------------------------------------------------------- #


def test_traces_only_evolve_when_accumulating_eligibility() -> None:
    snn = _seed_snn(voltage=1.5, threshold=0.65)  # guaranteed spikes
    frozen = _run(snn, _frame(), 24, accumulate=False)
    assert frozen.snn.pre_trace == snn.pre_trace
    assert frozen.snn.post_trace == snn.post_trace
    assert frozen.snn.eligibility == snn.eligibility
    evolved = _run(snn, _frame(), 24, accumulate=True)
    assert evolved.snn.pre_trace != snn.pre_trace  # spikes deposited trace mass


def test_eligibility_update_uses_anti_hebbian_factor_and_clip() -> None:
    plastic = formula.PLASTIC_SYNAPSES
    count = len(plastic)
    zeros = tuple(0.0 for _ in range(N))
    z = tuple(1.0 if i in {plastic[0][0], plastic[0][1]} else 0.0 for i in range(N))
    pre_prev = tuple(2.0 for _ in range(N))
    post_prev = tuple(1.0 for _ in range(N))
    updated = reservoir.update_eligibility(tuple(0.0 for _ in range(count)), z, pre_prev, post_prev, 0.95)
    post_i, pre_j = plastic[0]
    # e = 0.95*0 + z_i*pre_prev[j] - 1.05*z_j*post_prev[i]
    expected = z[post_i] * pre_prev[pre_j] - 1.05 * z[pre_j] * post_prev[post_i]
    assert updated[0] == pytest.approx(max(-3.0, min(3.0, expected)))
    # decay + clip: a large prior eligibility saturates at the clip bound
    saturated = reservoir.update_eligibility(tuple(100.0 for _ in range(count)), zeros, zeros, zeros, 0.95)
    assert all(value == 3.0 for value in saturated)


# --------------------------------------------------------------------------- #
# Non-finite rollback of the whole SNN subtransaction
# --------------------------------------------------------------------------- #


def test_build_snn_or_rollback_rejects_nonfinite_and_keeps_previous() -> None:
    previous = _seed_snn()
    good_voltages = tuple(0.1 for _ in range(N))
    built, rolled_back = reservoir.build_snn_or_rollback(
        previous,
        good_voltages,
        previous.thresholds,
        previous.pre_trace,
        previous.post_trace,
        previous.plastic_weights,
        previous.eligibility,
    )
    assert rolled_back is False
    assert built.voltages == good_voltages
    nan_voltages = tuple(float("nan") if i == 3 else 0.1 for i in range(N))
    built2, rolled_back2 = reservoir.build_snn_or_rollback(
        previous,
        nan_voltages,
        previous.thresholds,
        previous.pre_trace,
        previous.post_trace,
        previous.plastic_weights,
        previous.eligibility,
    )
    assert rolled_back2 is True
    assert built2 is previous  # complete subtransaction rolled back


def test_all_allowed_tick_counts_stay_bounded() -> None:
    for ticks in (16, 24, 32):
        result = _run(_seed_snn(voltage=1.5, threshold=0.65), _dense_frame(), ticks)
        assert result.rolled_back is False
        assert all(math.isfinite(v) and -2.0 <= v <= 2.0 for v in result.snn.voltages)
        assert all(0.65 <= t <= 1.35 for t in result.snn.thresholds)
        assert all(0.0 <= s <= 1.0 for s in result.summary)


def test_ten_thousand_turn_saturation_stays_bounded() -> None:
    snn = _seed_snn(voltage=1.5, threshold=0.65)
    frame = _dense_frame()
    trains = coding.population_spike_trains(frame, 24)
    by_tick = coding.spikes_by_tick(trains, 24)
    for _ in range(10_000):
        result = reservoir.run_reservoir(snn, by_tick, 24, True)
        assert result.rolled_back is False
        snn = result.snn
    assert all(math.isfinite(v) and -2.0 <= v <= 2.0 for v in snn.voltages)
    assert all(0.65 <= t <= 1.35 for t in snn.thresholds)
    assert all(0.0 <= w <= 0.35 for w in snn.plastic_weights)  # no STDP in forward pass
    assert all(-3.0 <= e <= 3.0 for e in snn.eligibility)
