"""RED/GREEN tests for Task 8 population + time coding (design section 8.1).

The coding stage is pure ``v3core``: it maps the immutable 36-channel
:class:`ObservationFrame` onto deterministic latency spike trains over ``K``
virtual ticks for the 108 population inputs (36 channels x 3 centers).  Every
unit of an invalid channel is silent for the complete horizon, and no
probabilistic spike insertion is ever used.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest

from sylanne_alpha.v3core import formula_v1 as formula
from sylanne_alpha.v3core.observation.models import ObservationFrame
from sylanne_alpha.v3core.spiking import coding

OBSERVATION_DIM = formula.OBSERVATION_DIM
POPULATION_INPUT_COUNT = formula.POPULATION_INPUT_COUNT
CENTERS = formula.SNN_CODING_CENTERS
SIGMA = formula.SNN_CODING_SIGMA


# --------------------------------------------------------------------------- #
# Builders + independent reference
# --------------------------------------------------------------------------- #


def _frame(overrides: dict[int, float] | None = None, valid: set[int] | None = None) -> ObservationFrame:
    values = list(formula.SEMANTIC_DEFAULTS)
    for channel, value in (overrides or {}).items():
        values[channel] = value
    mask = 0
    for channel in valid or set():
        mask |= 1 << channel
    return ObservationFrame(values=tuple(values), valid_mask=mask)


def _ref_unit(value: float, center: float, ticks: int) -> tuple[int, ...]:
    q = math.exp(-((value - center) ** 2) / (2.0 * SIGMA * SIGMA))
    if q < formula.SNN_CODING_SPIKE_Q_FLOOR:
        return ()
    latency = 1 + math.floor((ticks - 2) * (1.0 - q))
    spikes = [latency]
    if q >= formula.SNN_CODING_SECOND_SPIKE_Q:
        second = min(ticks - 1, latency + ticks // 2)
        if second != latency:
            spikes.append(second)
    return tuple(spikes)


def _ref_channel(value: float, ticks: int) -> tuple[tuple[int, ...], ...]:
    return tuple(_ref_unit(value, center, ticks) for center in CENTERS)


# --------------------------------------------------------------------------- #
# Firewall
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


def test_spiking_modules_import_nothing_forbidden() -> None:
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
        "random",
        "threading",
        "concurrent.futures",
        "portalocker",
    )
    for path in (
        "sylanne_alpha/v3core/spiking/__init__.py",
        "sylanne_alpha/v3core/spiking/coding.py",
        "sylanne_alpha/v3core/spiking/reservoir.py",
        "sylanne_alpha/v3core/spiking/plasticity.py",
    ):
        for name in _imported_modules(path):
            assert not any(name == item or name.startswith(item + ".") for item in forbidden), (path, name)


# --------------------------------------------------------------------------- #
# 36 x 3 coding and channel-major / center-inner layout
# --------------------------------------------------------------------------- #


def test_population_has_exactly_36x3_inputs() -> None:
    assert formula.SNN_CODING_UNITS_PER_CHANNEL == 3
    assert OBSERVATION_DIM * 3 == POPULATION_INPUT_COUNT == 108
    trains = coding.population_spike_trains(_frame(valid={25}, overrides={25: 0.9}), 24)
    assert type(trains) is tuple
    assert len(trains) == POPULATION_INPUT_COUNT
    for train in trains:
        assert type(train) is tuple
        assert all(type(tick) is int for tick in train)


def test_layout_is_channel_major_center_inner() -> None:
    # channel 25 valid at 0.9 -> only its three units (base index 3*25 == 75) may fire;
    # the far center-0.0 unit is correctly silent (q = exp(-6.48) << 0.08)
    trains = coding.population_spike_trains(_frame(valid={25}, overrides={25: 0.9}), 24)
    expected = _ref_channel(0.9, 24)
    assert 3 * 25 == 75
    assert (trains[75], trains[76], trains[77]) == expected
    assert trains[75] == ()  # center 0.0 far from 0.9
    assert trains[76] and trains[77]  # center 0.5 and on-center 1.0 fire
    for index in range(POPULATION_INPUT_COUNT):
        if index not in (75, 76, 77):
            assert trains[index] == ()


# --------------------------------------------------------------------------- #
# Invalid channels are silent for the whole horizon
# --------------------------------------------------------------------------- #


def test_invalid_channels_emit_no_spikes_regardless_of_value() -> None:
    for raw in (0.0, 0.25, 0.5, 0.9, 1.0):
        trains = coding.population_spike_trains(_frame(overrides={25: raw}), 24)  # mask bit 25 clear
        assert trains[75] == trains[76] == trains[77] == ()
    # every unit silent when no channel is valid
    all_silent = coding.population_spike_trains(_frame(), 24)
    assert all(train == () for train in all_silent)


def test_only_valid_channel_units_fire() -> None:
    trains = coding.population_spike_trains(_frame(valid={0, 25}, overrides={0: 0.2, 25: 0.9}), 24)
    for channel in range(OBSERVATION_DIM):
        base = 3 * channel
        units = (trains[base], trains[base + 1], trains[base + 2])
        if channel in (0, 25):
            assert any(units), f"valid channel {channel} must emit at least one spike"
        else:
            assert units == ((), (), ())


# --------------------------------------------------------------------------- #
# Deterministic latency: q floor, second spike, exact formula
# --------------------------------------------------------------------------- #


def test_far_center_unit_below_q_floor_is_silent() -> None:
    # value 0.0 at center 1.0 -> q = exp(-8) << 0.08 -> that unit never fires,
    # but the on-center unit fires twice (q == 1 >= 0.75).
    trains = coding.population_spike_trains(_frame(valid={4}, overrides={4: 0.0}), 24)
    base = 3 * 4
    on_center, mid_center, far_center = trains[base], trains[base + 1], trains[base + 2]
    assert far_center == ()  # center 1.0, q = exp(-8)
    assert on_center == _ref_unit(0.0, 0.0, 24)
    assert len(on_center) == 2  # q == 1 -> a second spike
    assert mid_center == _ref_unit(0.0, 0.5, 24)


@pytest.mark.parametrize("ticks", [16, 24, 32])
@pytest.mark.parametrize("value", [0.0, 0.13, 0.37, 0.5, 0.62, 0.88, 1.0])
def test_latency_matches_frozen_formula_exactly(value: float, ticks: int) -> None:
    trains = coding.population_spike_trains(_frame(valid={7}, overrides={7: value}), ticks)
    base = 3 * 7
    assert (trains[base], trains[base + 1], trains[base + 2]) == _ref_channel(value, ticks)
    # spike indexes always inside [1, K-1]
    for unit in (trains[base], trains[base + 1], trains[base + 2]):
        for tick in unit:
            assert 1 <= tick <= ticks - 1


def test_second_spike_only_when_q_at_least_075_and_distinct() -> None:
    # on-center value gives q == 1: first spike at latency 1, second at 1 + K//2
    trains = coding.population_spike_trains(_frame(valid={2}, overrides={2: 0.5}), 24)
    mid_unit = trains[3 * 2 + 1]  # center 0.5
    assert mid_unit == (1, 1 + 24 // 2)
    assert formula.spike_latency(1.0, 24) == 1


def test_coding_is_deterministic() -> None:
    frame = _frame(valid={0, 4, 25}, overrides={0: 0.3, 4: 0.7, 25: 0.55})
    assert coding.population_spike_trains(frame, 24) == coding.population_spike_trains(frame, 24)


# --------------------------------------------------------------------------- #
# K decay equivalence (same normalized horizon)
# --------------------------------------------------------------------------- #


def test_horizon_decays_are_k_invariant_and_beta24_is_090() -> None:
    # Each decay resamples the SAME normalized horizon: decay_K ** K = exp(-1/tau)
    # is invariant across K.  For the membrane that horizon value is 0.90**24; for
    # eligibility it is 0.95**24.  The K=24 profile reproduces the 0.90/0.95 anchors.
    beta_horizon = None
    elig_horizon = None
    for ticks in (16, 24, 32):
        beta, pre_decay, post_decay, elig_decay, refractory = formula.snn_horizon_decays(ticks)
        assert beta == pytest.approx(math.exp(-(1.0 / ticks) / formula.TAU_MEMBRANE))
        assert pre_decay == post_decay
        this_beta_horizon = round(beta**ticks, 12)
        this_elig_horizon = round(elig_decay**ticks, 12)
        if beta_horizon is None:
            beta_horizon, elig_horizon = this_beta_horizon, this_elig_horizon
        assert this_beta_horizon == beta_horizon
        assert this_elig_horizon == elig_horizon
        assert refractory == max(1, round(ticks / 12))
    assert beta_horizon == pytest.approx(0.90**24, abs=1e-9)
    assert elig_horizon == pytest.approx(0.95**24, abs=1e-9)
    beta24, _, _, elig24, _ = formula.snn_horizon_decays(24)
    assert beta24 == pytest.approx(0.90)
    assert elig24 == pytest.approx(0.95)
    assert formula.snn_horizon_decays(24)[4] == 2
    assert formula.snn_horizon_decays(16)[4] == 1
    assert formula.snn_horizon_decays(32)[4] == 3


@pytest.mark.parametrize("bad", [0, 8, 48, 24.0, True, -24])
def test_horizon_decays_reject_illegal_tick_counts(bad: object) -> None:
    with pytest.raises(ValueError):
        formula.snn_horizon_decays(bad)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# spikes_by_tick projection consumed by the reservoir
# --------------------------------------------------------------------------- #


def test_spikes_by_tick_partitions_units_by_firing_tick() -> None:
    ticks = 24
    frame = _frame(valid={0, 25}, overrides={0: 0.2, 25: 0.9})
    trains = coding.population_spike_trains(frame, ticks)
    by_tick = coding.spikes_by_tick(trains, ticks)
    assert type(by_tick) is tuple and len(by_tick) == ticks
    # every unit/tick pair round-trips exactly, and no unit fires at tick 0
    reconstructed: dict[int, list[int]] = {}
    for k in range(ticks):
        for unit in by_tick[k]:
            reconstructed.setdefault(unit, []).append(k)
        assert all(0 <= unit < POPULATION_INPUT_COUNT for unit in by_tick[k])
    for unit_index, train in enumerate(trains):
        assert tuple(sorted(reconstructed.get(unit_index, []))) == tuple(sorted(set(train)))
    assert not by_tick[0]
