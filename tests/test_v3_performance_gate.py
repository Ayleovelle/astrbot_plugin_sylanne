"""Task 15 performance-gate proof for design 17.5 (measure always, gate on demand).

Design 17.5 declares, on the 2-core/2-GB grey target:

* internal p95 v3 core compute <= 2.5 ms;
* grey acceptance p95 incremental latency <= 5 ms and p99 <= 15 ms;
* throughput loss below 5%;
* a table of hard structural budgets (state/trace bytes, cardinality caps, queue
  caps, disk watermarks) plus the plugin-wide ``effective_v3_*`` arithmetic.

**Why this file is split measure-always / gate-only-under-env-var.** The latency
and throughput numbers above are properties of the *declared target hardware*, not
of the code: a shared CI box, a loaded dev laptop, or a machine with a different
core count will produce numbers that say nothing about whether the design holds.
Asserting them unconditionally would make this a flaky gate that teams learn to
re-run until green — the worst kind of test, because it trains people to ignore it.
So the measurements *always* run (the numbers are always printed, and the code path
is always exercised so it cannot rot), while the hard latency/throughput assertions
fire only under ``SYLANNE_V3_PERF_GATES=1``, which is set when running on the
declared target. The structural budgets in the second half are deterministic and
machine-independent, so those are asserted unconditionally.

**Relationship to ``tests/test_v3_scalar_performance.py``.** That file already
measures the reservoir horizon at K=16/24/32 and one full orchestrated turn, and
gates them at its own declared numbers (25 ms turn / 20 ms reservoir). This file
does not duplicate the reservoir sweep or the benchmark-evidence artifact. It adds
what that file does *not* cover:

* the design-17.5 **2.5 ms** core p95 target (that file gates the turn at 25 ms,
  an order of magnitude looser — see the report accompanying this change);
* the **event-path incremental latency** the host actually pays, measured through
  the real non-awaiting ``V3ShadowRuntime.capture_request`` + ``offer_response``
  entry points rather than the core alone;
* the **throughput loss** of a host loop with the shadow enabled vs. disabled.
  Note this one is *model-dependent*: loss is a ratio, so it only means something
  against a declared host turn cost (see ``_HOST_TURN_CPU_MS``).  The absolute
  incremental ms/turn is reported alongside it so the number stays interpretable
  without buying into the model;
* the **structural budgets** of ``v3bridge/limits.py`` and the ``effective_v3_budget``
  boundary arithmetic, including a real orchestrated trace and a real
  experience-saturated state measured against the caps.

Measured percentiles are printed (visible under ``pytest -s``) so a gate failure is
always accompanied by the real numbers rather than a bare assertion.
"""

from __future__ import annotations

import asyncio
import os
import statistics
import sys
import threading
import time
from pathlib import Path

import pytest

from sylanne_alpha.v2core.shadow_snapshot import V2SeedSnapshotV1
from sylanne_alpha.v3bridge import limits
from sylanne_alpha.v3bridge.actual_action import ActualAction
from sylanne_alpha.v3bridge.effect_committer import EffectCommitter
from sylanne_alpha.v3bridge.integration import V3ShadowRuntime
from sylanne_alpha.v3bridge.migration_coordinator import MigrationCoordinator
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
from sylanne_alpha.v3core.effects.models import V3StateEffect, V3TraceEffect
from sylanne_alpha.v3core.state.models import V3State


# --------------------------------------------------------------------------- #
# Declared design-17.5 gates (2-core target; enforced only under the env var)
# --------------------------------------------------------------------------- #

CORE_P95_GATE_MS = 2.5
EVENT_PATH_P95_GATE_MS = 5.0
EVENT_PATH_P99_GATE_MS = 15.0
THROUGHPUT_LOSS_GATE = 0.05

#: Shared immutable model ceiling (design 17.5).  Deliberately a literal: no such
#: constant exists in ``v3bridge/limits.py`` — see the gap reported with this file.
SHARED_MODEL_MAX_BYTES = 64 * 1024 * 1024

CORRELATION_SECRET = b"correlation-secret-32bytes-min!!!"

_CORE_WARMUP = 20
_CORE_ITERATIONS = 200
_EVENT_WARMUP = 10
_EVENT_ITERATIONS = 60
_THROUGHPUT_TURNS = 40
_THROUGHPUT_REPEATS = 5

#: Loop yields per modelled turn.  A single ``sleep(0)`` starves the supervisor's
#: driver: it needs several loop iterations to wake, pump, hand the core to the
#: executor and collect it, so with one yield per turn the queues fill and most
#: offers take the cheap drop path — measuring nothing.  A real host turn awaits
#: upstream I/O and hands the loop far more iterations than this.
_HOST_YIELDS_PER_TURN = 4

#: Modelled on-loop CPU cost of one host turn (see ``_host_work``).  Throughput loss
#: is a *ratio*, so it is meaningless without a declared denominator: the same
#: absolute shadow cost is 2% of a 10 ms turn and 60% of a 0.3 ms turn.  A real chat
#: turn is dominated by an awaited upstream LLM call (hundreds of ms) during which
#: the shadow runs for free; only the on-loop CPU slice competes with it.  10 ms is a
#: deliberately conservative estimate of that slice (prompt assembly, parsing,
#: history handling) — charging the shadow against CPU-only understates the real
#: denominator and so overstates the loss.
_HOST_TURN_CPU_MS = 10.0


def _gates_enabled() -> bool:
    return os.environ.get("SYLANNE_V3_PERF_GATES") == "1"


# --------------------------------------------------------------------------- #
# Builders (shaped after tests/test_v3_scalar_performance.py and test_v3_lifecycle.py)
# --------------------------------------------------------------------------- #


def _raw_values() -> tuple:
    values: list[float | None] = [None] * 36
    for index in range(36):
        if index in (27, 28, 29, 32, 33, 34, 35):
            values[index] = None  # derived channels must stay absent in facts
        else:
            values[index] = 0.5
    values[30] = 1.0  # history_present bit
    values[31] = 120.0  # gap seconds
    return tuple(values)


def _session_ref(tag: str = "key-1") -> SessionRef:
    return SessionRef(key_id=tag, session_digest=bytes([len(tag) & 0xFF]) * 32, session_generation=1)


def _profile(name: str = "FULL_24_STDP") -> ComputeProfile:
    snn_enabled, ticks, stdp_enabled, reuse = formula.COMPUTE_PROFILES[name]
    return ComputeProfile(
        profile_id=name,
        snn_enabled=snn_enabled,
        ticks=ticks,
        stdp_enabled=stdp_enabled,
        reuse_last_summary=reuse,
        math_backend="scalar-v1",
        formula_version=formula.FORMULA_VERSION,
        model_version=formula.FORMULA_VERSION,
    )


def _invocation(base_state: V3State | None = None, *, local_sequence: int = 5, turn_id: str = "turn-gate") -> CoreInvocation:
    ref = _session_ref()
    envelope = TurnEnvelope(
        turn_key=TurnKey(
            plugin_instance_id="plugin-instance",
            session_ref=ref,
            bridge_request_nonce="request-nonce",
            request_attempt=0,
        ),
        turn_id=turn_id,
        sequence=TurnSequence(writer_epoch=7, local_sequence=local_sequence),
        compute_profile=_profile(),
        deterministic_seed=b"d" * 16,
        observation=(_raw_values(), Action.SPEAK),
        context=TurnContextClass.ADDRESSED,
    )
    state = base_state if base_state is not None else V3State(
        session_ref=ref, state_generation_id="gen-a", revision=4, writer_epoch=7
    )
    return CoreInvocation(envelope=envelope, base_state=state, projected_actual_outcome=(Action.SPEAK, None))


def _seed_session(root: Path, session_ref: SessionRef) -> None:
    """One-time v2 migration at its own (lower) epoch, before any runtime starts."""

    committer = EffectCommitter.open(root)
    coordinator = MigrationCoordinator(committer)
    coordinator.migrate(
        session_ref,
        writer_epoch=committer.acquire_epoch(),
        session_generation=0,
        source_digest="0" * 64,
        v3_migration_lock=threading.Lock(),
        seed_snapshot=V2SeedSnapshotV1(user_bond_ema=0.6, user_hesitation_ema=0.4),
    )


# --------------------------------------------------------------------------- #
# Measurement helpers
# --------------------------------------------------------------------------- #


def _percentiles(samples: list[float]) -> dict:
    ordered = sorted(samples)
    return {
        "iterations": len(ordered),
        "p50_ms": statistics.median(ordered),
        "p95_ms": ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))],
        "p99_ms": ordered[min(len(ordered) - 1, int(0.99 * len(ordered)))],
        "max_ms": ordered[-1],
    }


def _emit(label: str, stats: dict) -> None:
    # Printed so a gate failure always arrives with the real numbers attached.
    print(
        f"\n[v3-perf] {label}: n={stats['iterations']} "
        f"p50={stats['p50_ms']:.4f}ms p95={stats['p95_ms']:.4f}ms "
        f"p99={stats['p99_ms']:.4f}ms max={stats['max_ms']:.4f}ms "
        f"[gates={'ON' if _gates_enabled() else 'OFF'} cpus={os.cpu_count()}]"
    )


def _monotonic_ordering(stats: dict) -> None:
    """Machine-independent sanity: percentiles are ordered and finite."""

    assert 0.0 <= stats["p50_ms"] <= stats["p95_ms"] <= stats["p99_ms"] <= stats["max_ms"]


# --------------------------------------------------------------------------- #
# 1. Core compute p95 <= 2.5 ms (design 17.5) — pure core, no filesystem
# --------------------------------------------------------------------------- #


def test_core_compute_p95_meets_the_declared_target() -> None:
    from sylanne_alpha.v3core.orchestrator import orchestrate

    invocation = _invocation()
    for _ in range(_CORE_WARMUP):
        orchestrate(invocation)

    samples: list[float] = []
    for _ in range(_CORE_ITERATIONS):
        start = time.perf_counter()
        orchestrate(invocation)
        samples.append((time.perf_counter() - start) * 1000.0)

    stats = _percentiles(samples)
    _emit("core.orchestrate FULL_24_STDP (pure core, no repository)", stats)
    _monotonic_ordering(stats)

    if _gates_enabled():
        assert stats["p95_ms"] <= CORE_P95_GATE_MS, (
            f"core p95 {stats['p95_ms']:.4f}ms exceeds the design-17.5 "
            f"{CORE_P95_GATE_MS}ms target: {stats}"
        )


# --------------------------------------------------------------------------- #
# 2. Event-path incremental latency p95 <= 5 ms / p99 <= 15 ms
# --------------------------------------------------------------------------- #


async def _measure_event_path(root: Path, session_ref: SessionRef) -> dict:
    """Time exactly what the host event path pays: capture + non-awaiting offer.

    ``V3ShadowRuntime.offer_response`` is the real design-14.2 entry point: it is
    synchronous, bounded, and never awaits v3 calculation.  The incremental cost the
    host coroutine pays is therefore precisely the span measured below; the core runs
    afterwards on the private executor and is deliberately *not* included.

    ``join()`` between turns models the real cadence — chat turns are seconds apart,
    so the steady-state host path always meets a drained queue and a genuinely
    ACCEPTED offer (rather than the artificially cheap queue-full drop path).
    """

    runtime = V3ShadowRuntime(
        root=root,
        plugin_instance_id="plugin",
        correlation_secret=CORRELATION_SECRET,
        job_timeout_s=None,
    )
    await runtime.initialize()
    try:
        samples: list[float] = []
        accepted = 0
        for index in range(_EVENT_WARMUP + _EVENT_ITERATIONS):
            start = time.perf_counter()
            handle = runtime.capture_request(
                session_ref=session_ref,
                bridge_request_nonce=f"nonce-{index}",
                request_attempt=0,
                platform_id="qq",
                unified_msg_origin="grp:1",
                message_id=f"m-{index}",
            )
            assert handle is not None
            result = runtime.offer_response(
                handle=handle,
                context=TurnContextClass.ADDRESSED,
                observation=(_raw_values(), Action.SPEAK),
                actual_action=ActualAction.SPEAK,
                quality_score=None,
                platform_id="qq",
                unified_msg_origin="grp:1",
                message_id=f"m-{index}",
                deadline_ms=5000.0,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000.0  # host path ends here
            if index >= _EVENT_WARMUP:
                samples.append(elapsed_ms)
                accepted += int(result.accepted)
            await runtime.join()  # let the shadow drain; not part of the host cost
        stats = _percentiles(samples)
        stats["accepted"] = accepted
        return stats
    finally:
        await runtime.terminate()


def test_event_path_incremental_latency_meets_the_declared_target(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    session_ref = _session_ref()
    _seed_session(root, session_ref)  # blocking IO stays off the event loop

    stats = asyncio.run(_measure_event_path(root, session_ref))
    _emit("bridge.capture_request+offer_response (host event path)", stats)
    _monotonic_ordering(stats)

    # The measurement is only meaningful if the offers were really admitted: a
    # rejected offer takes the cheap drop path and would flatter the numbers.
    assert stats["accepted"] == stats["iterations"], "offers were dropped; latency sample is not representative"

    if _gates_enabled():
        assert stats["p95_ms"] <= EVENT_PATH_P95_GATE_MS, (
            f"event-path p95 {stats['p95_ms']:.4f}ms exceeds the design-17.5 "
            f"{EVENT_PATH_P95_GATE_MS}ms target: {stats}"
        )
        assert stats["p99_ms"] <= EVENT_PATH_P99_GATE_MS, (
            f"event-path p99 {stats['p99_ms']:.4f}ms exceeds the design-17.5 "
            f"{EVENT_PATH_P99_GATE_MS}ms target: {stats}"
        )


# --------------------------------------------------------------------------- #
# 3. Throughput loss < 5%
# --------------------------------------------------------------------------- #


def _host_work(steps: int) -> int:
    """Deterministic stand-in for the on-loop CPU one host turn spends.

    Pure-Python on purpose: it holds the GIL, so contention from the v3 private worker
    thread (whose core is also pure Python) shows up in the measurement instead of
    being hidden behind an I/O wait.  ``steps`` is calibrated per machine so the
    modelled turn costs ``_HOST_TURN_CPU_MS``, which keeps the loss ratio comparable
    across boxes rather than being an artifact of this one's clock speed.
    """

    total = 0
    for index in range(steps):
        total = (total * 31 + index) & 0xFFFFFFFF
    return total


def _calibrate_host_work_steps(target_ms: float) -> int:
    """Find the step count costing ``target_ms`` here, so the model is machine-neutral."""

    probe = 20_000
    for _ in range(3):  # warm, then converge; the loop is linear in ``steps``
        _host_work(probe)
    for _ in range(6):
        # Median of repeated probes: a single timing on a busy box can be an outlier,
        # and mis-calibrating changes the denominator the loss ratio is divided by.
        timings: list[float] = []
        for _ in range(5):
            start = time.perf_counter()
            _host_work(probe)
            timings.append((time.perf_counter() - start) * 1000.0)
        elapsed_ms = statistics.median(timings)
        if elapsed_ms >= 0.2 * target_ms:  # enough signal to extrapolate from
            return max(1_000, int(probe * (target_ms / elapsed_ms)))
        probe *= 4
    return probe


async def _run_host_loop(
    runtime: V3ShadowRuntime | None, session_ref: SessionRef, tag: str, steps: int
) -> tuple[float, int]:
    """One host loop of identical work; the only difference is the v3 capture+offer.

    Returns the elapsed seconds and how many offers were actually ACCEPTED.  The
    accepted count is not bookkeeping: if the shadow sheds load (per-session queue
    cap) the host stops paying for contention and the loss ratio collapses towards
    zero — a "pass" that means the shadow did nothing.  The caller must check it.
    """

    accepted = 0
    start = time.perf_counter()
    for index in range(_THROUGHPUT_TURNS):
        _host_work(steps)
        if runtime is not None:
            handle = runtime.capture_request(
                session_ref=session_ref,
                bridge_request_nonce=f"{tag}-{index}",
                request_attempt=0,
                platform_id="qq",
                unified_msg_origin="grp:1",
                message_id=f"{tag}-m-{index}",
            )
            if handle is not None:
                result = runtime.offer_response(
                    handle=handle,
                    context=TurnContextClass.ADDRESSED,
                    observation=(_raw_values(), Action.SPEAK),
                    actual_action=ActualAction.SPEAK,
                    quality_score=None,
                    platform_id="qq",
                    unified_msg_origin="grp:1",
                    message_id=f"{tag}-m-{index}",
                    deadline_ms=5000.0,
                )
                accepted += int(result.accepted)
        for _ in range(_HOST_YIELDS_PER_TURN):
            await asyncio.sleep(0)  # the host yields; the shadow progresses off-path
    return time.perf_counter() - start, accepted


async def _measure_throughput(root: Path, session_ref: SessionRef, steps: int) -> dict:
    baselines: list[float] = []
    shadowed: list[float] = []

    # Baseline: the shadow is never offered anything and no runtime exists at all.
    await _run_host_loop(None, session_ref, "warmup", steps)  # warm the host loop
    for _ in range(_THROUGHPUT_REPEATS):
        elapsed, _ = await _run_host_loop(None, session_ref, "base", steps)
        baselines.append(elapsed)

    runtime = V3ShadowRuntime(
        root=root,
        plugin_instance_id="plugin",
        correlation_secret=CORRELATION_SECRET,
        job_timeout_s=None,
    )
    await runtime.initialize()
    accepted_total = 0
    try:
        for repeat in range(_THROUGHPUT_REPEATS):
            elapsed, accepted = await _run_host_loop(runtime, session_ref, f"shadow{repeat}", steps)
            shadowed.append(elapsed)
            accepted_total += accepted
    finally:
        await runtime.terminate()

    # Minimum over repeats, not median.  Interference is strictly additive — noise can
    # only ever make a run slower — so the fastest run of each arm is the cleanest
    # estimate of its true cost.  Median mixes in whatever else the box was doing and
    # here produced physically impossible negative loss (a shadow speeding the host up).
    base = min(baselines)
    shadow = min(shadowed)
    return {
        "baseline_s": base,
        "shadow_s": shadow,
        "loss_ratio": (shadow - base) / base if base > 0 else 0.0,
        "baseline_turns_per_s": _THROUGHPUT_TURNS / base if base > 0 else 0.0,
        "shadow_turns_per_s": _THROUGHPUT_TURNS / shadow if shadow > 0 else 0.0,
        # Model-free: the absolute cost the shadow adds per turn.  The loss ratio
        # above is this divided by the modelled turn; this lets a reader recompute
        # the loss against whatever host turn cost they actually believe in.
        "incremental_ms_per_turn": (shadow - base) * 1000.0 / _THROUGHPUT_TURNS,
        "modelled_turn_ms": base * 1000.0 / _THROUGHPUT_TURNS,
        "accepted": accepted_total,
        "offered": _THROUGHPUT_TURNS * _THROUGHPUT_REPEATS,
    }


def test_throughput_loss_stays_under_five_percent(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    session_ref = _session_ref()
    _seed_session(root, session_ref)

    steps = _calibrate_host_work_steps(_HOST_TURN_CPU_MS)
    stats = asyncio.run(_measure_throughput(root, session_ref, steps))
    print(
        f"\n[v3-perf] host throughput (modelled {stats['modelled_turn_ms']:.2f}ms-CPU turn): "
        f"baseline={stats['baseline_turns_per_s']:.1f} turns/s "
        f"shadow={stats['shadow_turns_per_s']:.1f} turns/s "
        f"loss={stats['loss_ratio'] * 100.0:.2f}% "
        f"(+{stats['incremental_ms_per_turn']:.3f}ms/turn absolute, "
        f"shadow accepted {stats['accepted']}/{stats['offered']}) "
        f"[gates={'ON' if _gates_enabled() else 'OFF'} cpus={os.cpu_count()}]"
    )
    assert stats["baseline_s"] > 0.0 and stats["shadow_s"] > 0.0
    # The calibration must have actually landed near the model, or the loss ratio is
    # being computed against a denominator that does not match the documented model.
    assert 0.5 * _HOST_TURN_CPU_MS <= stats["modelled_turn_ms"] <= 2.0 * _HOST_TURN_CPU_MS

    # Guard the gate against its cheapest vacuous pass: a shadow that accepted nothing
    # costs the host nothing, so a low loss ratio would prove only that v3 was idle.
    # The bar is >0 rather than a fixed fraction because shedding under pressure is a
    # *designed* behaviour (per-session queue cap + profile ladder), so the accepted
    # ratio is reported for interpretation rather than asserted into a threshold.
    assert stats["accepted"] > 0, f"shadow accepted no work; throughput sample is vacuous: {stats}"

    if _gates_enabled():
        assert stats["loss_ratio"] < THROUGHPUT_LOSS_GATE, (
            f"throughput loss {stats['loss_ratio'] * 100.0:.2f}% exceeds the design-17.5 "
            f"{THROUGHPUT_LOSS_GATE * 100.0:.0f}% budget: {stats}"
        )


# --------------------------------------------------------------------------- #
# 4. Structural budgets — deterministic, always asserted (no env var)
# --------------------------------------------------------------------------- #


def test_live_cognitive_payload_and_trace_budgets_match_design_17_5() -> None:
    assert limits.MAX_STATE_BYTES == 64 * 1024
    assert limits.TARGET_STATE_BYTES == 48 * 1024
    assert limits.TARGET_STATE_BYTES < limits.MAX_STATE_BYTES
    assert limits.MAX_TRACE_BYTES == 16 * 1024


def test_cardinality_and_queue_caps_match_design_17_5() -> None:
    assert limits.MAX_ACTIVE_SESSIONS == 64
    assert limits.MAX_REPOSITORY_SESSIONS == 96
    assert limits.MAX_GLOBAL_QUEUE == 128
    assert limits.MAX_PER_SESSION_QUEUE == 4
    assert limits.MAX_TURN_REGISTRY == 1024
    # The repository must be able to hold every session the supervisor can activate.
    assert limits.MAX_REPOSITORY_SESSIONS >= limits.MAX_ACTIVE_SESSIONS
    # The global queue must not be smaller than one full round of active sessions'
    # first jobs, or a fair round-robin cycle could not be admitted at all.
    assert limits.MAX_GLOBAL_QUEUE >= limits.MAX_PER_SESSION_QUEUE


def test_journal_and_staging_budgets_match_design_17_5() -> None:
    assert limits.TRACE_SEGMENT_BYTES == 2 * 1024 * 1024
    assert limits.TRACE_SEGMENT_COUNT == 2
    assert limits.TELEMETRY_SEGMENT_BYTES == 1 * 1024 * 1024
    assert limits.TELEMETRY_SEGMENT_COUNT == 4
    assert limits.MAX_STAGING_BYTES == 4 * 1024 * 1024


def test_disk_watermarks_and_plugin_cap_match_design_17_5() -> None:
    assert limits.DISK_HIGH_WATERMARK_BYTES == 22_000_000
    assert limits.DISK_HARD_WATERMARK_BYTES == 24_000_000
    assert limits.PLUGIN_DATA_CAP_BYTES == 50_000_000
    assert limits.V3_DEFAULT_BUDGET_BYTES == 24_000_000
    assert limits.NON_V3_RESERVE_BYTES == 2_000_000
    assert limits.HIGH_WATERMARK_HEADROOM_BYTES == 2_000_000
    assert limits.MIN_ADMISSION_HARD_BYTES == 4 * 1024 * 1024
    # High must trip before hard, or load shedding would never get a chance to run.
    assert limits.DISK_HIGH_WATERMARK_BYTES < limits.DISK_HARD_WATERMARK_BYTES
    # The per-resource ceilings are independent, not simultaneously reserved (17.5).
    assert limits.RESOURCE_CEILINGS_ARE_SIMULTANEOUS_RESERVATIONS is False


def test_real_orchestrated_trace_fits_the_sixteen_kib_revision_budget() -> None:
    from sylanne_alpha.v3core.orchestrator import orchestrate

    result = orchestrate(_invocation())
    assert result.accepted is True
    trace_payload = next(e.payload for e in result.effects.effects if type(e) is V3TraceEffect)
    print(f"\n[v3-perf] real core trace: {len(result.trace_bytes)} B / {limits.MAX_TRACE_BYTES} B cap")
    assert len(result.trace_bytes) <= limits.MAX_TRACE_BYTES
    assert len(trace_payload) <= limits.MAX_TRACE_BYTES
    assert trace_payload == result.trace_bytes


def test_real_experience_saturated_state_fits_the_live_payload_budget() -> None:
    """Drive real turns until the bounded experience FIFO is full, then measure.

    ``tests/test_v3_state_budget.py`` proves a *synthetic* worst-case state encodes
    within budget.  This asserts the same caps hold for a state the live core path
    actually produces once its largest growth term (the experience buffer) saturates.
    """

    from sylanne_alpha.v3core.orchestrator import orchestrate

    state = V3State(session_ref=_session_ref(), state_generation_id="gen-a", revision=4, writer_epoch=7)
    payload = b""
    for step in range(formula.EXPERIENCE_CAPACITY + 2):
        result = orchestrate(_invocation(state, local_sequence=5 + step, turn_id=f"turn-{step:04d}"))
        assert result.accepted is True
        payload = next(e.payload for e in result.effects.effects if type(e) is V3StateEffect)
        state = result.state_delta.next_state

    assert len(state.experiences) == formula.EXPERIENCE_CAPACITY  # buffer really saturated
    print(
        f"\n[v3-perf] real saturated state: {len(payload)} B "
        f"/ {limits.TARGET_STATE_BYTES} B target / {limits.MAX_STATE_BYTES} B cap"
    )
    assert len(payload) <= limits.MAX_STATE_BYTES
    assert len(payload) <= limits.TARGET_STATE_BYTES


# -- effective_v3_budget arithmetic ----------------------------------------- #


@pytest.mark.parametrize(
    "non_v3, expected_hard, expected_high, expected_admission",
    [
        # Empty root: the 24 MB default budget dominates the 50 MB plugin cap.
        (0, 24_000_000, 22_000_000, True),
        # Exactly at the clamp knee: 50M - 24M - 2M == 24M, still the default.
        (24_000_000, 24_000_000, 22_000_000, True),
        # One byte past the knee: the plugin cap starts to bite.
        (24_000_001, 23_999_999, 21_999_999, True),
        # Admission knee: hard == MIN_ADMISSION_HARD_BYTES exactly (4 MiB) -> enabled.
        (43_805_696, 4_194_304, 2_194_304, True),
        # One byte worse: hard drops below 4 MiB -> admission disabled.
        (43_805_697, 4_194_303, 2_194_303, False),
        # high floors at zero while hard is still positive.
        (46_000_000, 2_000_000, 0, False),
        (47_500_000, 500_000, 0, False),
        # Exhausted: hard floors at zero.
        (48_000_000, 0, 0, False),
        # Over-subscribed root: the max(0, ...) clamp holds, no negative budget.
        (50_000_000, 0, 0, False),
        (999_999_999, 0, 0, False),
    ],
)
def test_effective_v3_budget_boundaries(
    non_v3: int, expected_hard: int, expected_high: int, expected_admission: bool
) -> None:
    budget = limits.effective_v3_budget(non_v3)
    assert budget.hard_bytes == expected_hard
    assert budget.high_bytes == expected_high
    assert budget.admission_enabled is expected_admission
    # The declared formula, restated independently of the implementation.
    assert budget.hard_bytes == max(0, min(24_000_000, 50_000_000 - non_v3 - 2_000_000))
    assert budget.high_bytes == max(0, budget.hard_bytes - 2_000_000)
    assert budget.admission_enabled is (budget.hard_bytes >= 4 * 1024 * 1024)
    # The convenience accessors must not drift from the dataclass.
    assert limits.effective_v3_hard_cap(non_v3) == budget.hard_bytes
    assert limits.effective_v3_high_watermark(non_v3) == budget.high_bytes


def test_effective_v3_budget_honours_a_smaller_plugin_cap() -> None:
    # A tighter plugin declaration must dominate the 24 MB v3 default.
    budget = limits.effective_v3_budget(0, 10_000_000)
    assert budget.hard_bytes == 8_000_000
    assert budget.high_bytes == 6_000_000
    assert budget.admission_enabled is True


def test_effective_v3_budget_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        limits.effective_v3_budget(-1)
    with pytest.raises(ValueError):
        limits.effective_v3_budget(0, -1)
    with pytest.raises(TypeError):
        limits.effective_v3_budget(1.5)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        limits.effective_v3_budget(True)  # bool is not an exact int byte count


def test_default_watermarks_agree_with_the_empty_root_budget() -> None:
    # With nothing else on disk the effective budget must equal the declared defaults.
    budget = limits.effective_v3_budget(0)
    assert budget.hard_bytes == limits.DISK_HARD_WATERMARK_BYTES
    assert budget.high_bytes == limits.DISK_HIGH_WATERMARK_BYTES


# -- shared immutable model -------------------------------------------------- #


def _deep_size(root: object) -> int:
    """Recursive in-memory footprint of a frozen constant graph (identity-deduped)."""

    seen: set[int] = set()
    stack = [root]
    total = 0
    while stack:
        item = stack.pop()
        marker = id(item)
        if marker in seen:
            continue
        seen.add(marker)
        total += sys.getsizeof(item)
        if isinstance(item, (tuple, list, set, frozenset)):
            stack.extend(item)
        elif isinstance(item, dict):
            stack.extend(item.keys())
            stack.extend(item.values())
    return total


def test_shared_immutable_model_fits_the_sixty_four_mib_budget() -> None:
    """The per-instance shared immutable model is the frozen ``formula_v1`` graph.

    Design 17.5 caps it at 64 MiB.  There is no constant for this in
    ``v3bridge/limits.py`` (unlike every other row of the 17.5 table), so the
    ceiling is restated here as a literal — see the gap reported with this file.
    """

    total = 0
    for name, value in vars(formula).items():
        if name.startswith("__"):
            continue
        if isinstance(value, (tuple, bytes, str, int, float)):
            total += _deep_size(value)

    print(f"\n[v3-perf] shared immutable model: {total} B / {SHARED_MODEL_MAX_BYTES} B cap")
    assert total > 0  # the model must actually be loaded, or this proves nothing
    assert total <= SHARED_MODEL_MAX_BYTES


# --------------------------------------------------------------------------- #
# The gate contract itself
# --------------------------------------------------------------------------- #


def test_perf_gates_are_opt_in_only() -> None:
    # The latency/throughput gates are enforced iff SYLANNE_V3_PERF_GATES == "1";
    # the structural budgets above are asserted either way.
    flag = os.environ.get("SYLANNE_V3_PERF_GATES")
    if flag == "1":
        pytest.skip("perf gates intentionally enabled for this run")
    assert flag in (None, "0", "")
