"""Task 10 scalar core performance proof (design 16.3, plan spike C).

Warms up and measures two separable core costs, both away from any repository
fsync (the pure core never touches disk):

* the 96-neuron reservoir horizon at ``K = 16/24/32`` virtual ticks; and
* one complete deterministic turn (encoder/snn/dynamics/workspace/policy plus
  canonical trace serialization) via the orchestrator.

Percentiles p50/p95/p99 are recorded for each.  The declared latency gate fails
only when ``SYLANNE_V3_PERF_GATES=1`` on the 2-core target; a normal test run
always passes.  An encoded benchmark JSON with an environment fingerprint is
written to the ignored evidence directory (best effort, never fatal).
"""

from __future__ import annotations

import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path

import pytest

from sylanne_alpha.v3core import formula_v1 as formula
from sylanne_alpha.v3core.contracts import (
    Action,
    ComputeProfile,
    CoreInvocation,
    SessionRef,
    TurnContextClass,
    TurnEnvelope,
    TurnKey,
    TurnSequence,
)
from sylanne_alpha.v3core.observation.encoder import encode_observation
from sylanne_alpha.v3core.observation.models import ObservationFacts
from sylanne_alpha.v3core.orchestrator import build_initial_snn_state, orchestrate
from sylanne_alpha.v3core.spiking.reservoir import run_reservoir_from_frame
from sylanne_alpha.v3core.state.models import V3State


# Declared p95 latency gates for the 2-core grey target.  Enforced only under
# SYLANNE_V3_PERF_GATES=1 so ordinary runs never flake.
DECLARED_TURN_P95_GATE_MS = 25.0
DECLARED_RESERVOIR_P95_GATE_MS = 20.0


def _raw_values() -> tuple:
    values: list[float | None] = [None] * 36
    for index in range(36):
        if index not in (27, 28, 29, 32, 33, 34, 35):
            values[index] = 0.5
    values[30] = 1.0
    values[31] = 120.0
    return tuple(values)


def _session_ref() -> SessionRef:
    return SessionRef(key_id="key-v1", session_digest=b"s" * 32, session_generation=1)


def _frame() -> object:
    return encode_observation(
        ObservationFacts(raw_values=_raw_values(), context=TurnContextClass.ADDRESSED, previous_action=Action.SPEAK)
    )


def _turn_invocation() -> CoreInvocation:
    envelope = TurnEnvelope(
        turn_key=TurnKey(
            plugin_instance_id="plugin-instance",
            session_ref=_session_ref(),
            bridge_request_nonce="request-nonce",
            request_attempt=0,
        ),
        turn_id="turn-bench",
        sequence=TurnSequence(writer_epoch=7, local_sequence=5),
        compute_profile=ComputeProfile(
            profile_id="FULL_24_STDP",
            snn_enabled=True,
            ticks=24,
            stdp_enabled=True,
            reuse_last_summary=False,
            math_backend="scalar-v1",
            formula_version=formula.FORMULA_VERSION,
            model_version=formula.FORMULA_VERSION,
        ),
        deterministic_seed=b"d" * 16,
        observation=(_raw_values(), Action.SPEAK),
        context=TurnContextClass.ADDRESSED,
    )
    return CoreInvocation(
        envelope=envelope,
        base_state=V3State(session_ref=_session_ref(), state_generation_id="gen-a", revision=4, writer_epoch=7),
        projected_actual_outcome=(Action.SPEAK, None),
    )


def _percentiles(label: str, samples: list[float], extra: dict) -> dict:
    samples.sort()
    return {
        "label": label,
        "iterations": len(samples),
        "p50_ms": statistics.median(samples),
        "p95_ms": samples[min(len(samples) - 1, int(0.95 * len(samples)))],
        "p99_ms": samples[min(len(samples) - 1, int(0.99 * len(samples)))],
        **extra,
    }


def _measure_reservoir(ticks: int, iterations: int = 60, warmup: int = 15) -> dict:
    snn = build_initial_snn_state()
    frame = _frame()
    for _ in range(warmup):
        run_reservoir_from_frame(snn, frame, ticks, True)
    samples: list[float] = []
    for _ in range(iterations):
        start = time.perf_counter()
        run_reservoir_from_frame(snn, frame, ticks, True)
        samples.append((time.perf_counter() - start) * 1000.0)
    return _percentiles("reservoir", samples, {"ticks": ticks, "neurons": formula.SNN_NEURONS})


def _measure_turn(iterations: int = 60, warmup: int = 15) -> dict:
    invocation = _turn_invocation()
    for _ in range(warmup):
        orchestrate(invocation)
    samples: list[float] = []
    for _ in range(iterations):
        start = time.perf_counter()
        orchestrate(invocation)
        samples.append((time.perf_counter() - start) * 1000.0)
    return _percentiles("full_turn", samples, {"ticks": 24, "neurons": formula.SNN_NEURONS})


def test_scalar_core_performance_is_measured_and_optionally_gated() -> None:
    reservoir_results = [_measure_reservoir(ticks) for ticks in (16, 24, 32)]
    turn_result = _measure_turn()
    fingerprint = {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "math_backend": "scalar-v1",
        "formula_digest": formula.FORMULA_DIGEST,
    }
    payload = {
        "fingerprint": fingerprint,
        "reservoir": reservoir_results,
        "full_turn": turn_result,
    }

    # Best-effort encoded benchmark evidence (ignored directory; never fatal).
    try:
        evidence_dir = Path("artifacts/v3/evidence/benchmarks")
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / f"scalar-{fingerprint['python']}.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
    except OSError:
        pass

    for measurement in (*reservoir_results, turn_result):
        assert measurement["p50_ms"] <= measurement["p95_ms"] <= measurement["p99_ms"]
        assert measurement["p99_ms"] >= 0.0

    if os.environ.get("SYLANNE_V3_PERF_GATES") == "1":
        worst_reservoir_p95 = max(measurement["p95_ms"] for measurement in reservoir_results)
        assert worst_reservoir_p95 < DECLARED_RESERVOIR_P95_GATE_MS, (
            f"reservoir p95 {worst_reservoir_p95:.3f}ms exceeds the declared "
            f"{DECLARED_RESERVOIR_P95_GATE_MS}ms gate: {payload}"
        )
        assert turn_result["p95_ms"] < DECLARED_TURN_P95_GATE_MS, (
            f"full-turn p95 {turn_result['p95_ms']:.3f}ms exceeds the declared "
            f"{DECLARED_TURN_P95_GATE_MS}ms gate: {payload}"
        )


def test_perf_gate_is_opt_in_only() -> None:
    # The gate is opt-in: it is enforced iff SYLANNE_V3_PERF_GATES == "1".
    flag = os.environ.get("SYLANNE_V3_PERF_GATES")
    if flag == "1":
        pytest.skip("perf gate intentionally enabled for this run")
    assert flag in (None, "0", "")
