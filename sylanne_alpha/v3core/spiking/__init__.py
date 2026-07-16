"""Deterministic sparse spiking path for Sylanne v3 (design section 8)."""

from .coding import encode_unit, population_spike_trains, spikes_by_tick
from .plasticity import (
    apply_stdp,
    compute_credit_gate,
    settle_stdp,
    stdp_delta,
    update_baseline,
)
from .reservoir import (
    ReservoirResult,
    adapt_thresholds,
    build_snn_or_rollback,
    pooled_summary,
    run_reservoir,
    run_reservoir_from_frame,
    update_eligibility,
    update_traces,
)

__all__ = [
    "ReservoirResult",
    "adapt_thresholds",
    "apply_stdp",
    "build_snn_or_rollback",
    "compute_credit_gate",
    "encode_unit",
    "pooled_summary",
    "population_spike_trains",
    "run_reservoir",
    "run_reservoir_from_frame",
    "settle_stdp",
    "spikes_by_tick",
    "stdp_delta",
    "update_eligibility",
    "update_traces",
]
