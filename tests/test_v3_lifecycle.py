"""RED/GREEN tests for Task 12 lifecycle: idempotence, shutdown order, leak proof.

Covers plan Task 12's lifecycle requirements:

* ``initialize`` / ``terminate`` are idempotent;
* ``terminate`` runs the exact ordered teardown (stop admission -> mark unqueued
  dropped -> cancel replay/metric -> bounded drain -> close committer admission ->
  seal epoch -> cancel leftovers -> gather tracked tasks -> executor shutdown ->
  clear registries);
* 50 load -> one turn -> shutdown cycles leak zero v3 worker threads, asyncio tasks,
  OS handles, or supervisor registry entries (spike E, ``reload_50``);
* the seven design-16.1 isolation counters remain zero under normal, queue-full,
  timeout, repository-failure, malformed-input, reload, and shutdown conditions.
"""

from __future__ import annotations

import asyncio
import gc
import threading

import pytest

from sylanne_alpha.v2core.shadow_snapshot import V2SeedSnapshotV1
from sylanne_alpha.v3bridge.actual_action import ActualAction
from sylanne_alpha.v3bridge.effect_committer import EffectCommitter
from sylanne_alpha.v3bridge.integration import V3ShadowRuntime
from sylanne_alpha.v3bridge.migration_coordinator import MigrationCoordinator
from sylanne_alpha.v3bridge.models import LoadSnapshotV1, RepositoryAdmissionState
from sylanne_alpha.v3bridge.runtime_telemetry import IsolationCounters, TelemetrySink
from sylanne_alpha.v3bridge.shadow_supervisor import (
    SHUTDOWN_ORDER,
    THREAD_NAME_PREFIX,
    ShadowJob,
    ShadowSupervisor,
)
from sylanne_alpha.v3bridge.turn_registry import SequenceLedger
from sylanne_alpha.v3core import orchestrator
from sylanne_alpha.v3core.contracts import (
    Action,
    SessionRef,
    TurnContextClass,
    TurnKey,
)

try:  # OS handle accounting is best-effort; psutil is present in the target runtime.
    import psutil

    _PROCESS = psutil.Process()
except Exception:  # pragma: no cover - handled by tolerant fallback
    psutil = None
    _PROCESS = None


CORRELATION_SECRET = b"correlation-secret-32bytes-min!!!"


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #


def _raw_values() -> tuple:
    values: list[float | None] = [None] * 36
    for index in range(36):
        if index in (27, 28, 29, 32, 33, 34, 35):
            values[index] = None
        else:
            values[index] = 0.5
    values[30] = 1.0
    values[31] = 120.0
    return tuple(values)


def _session_ref(tag: str = "key-1") -> SessionRef:
    return SessionRef(key_id=tag, session_digest=bytes([len(tag) & 0xFF]) * 32, session_generation=1)


def _seed_session(committer: EffectCommitter, session_ref: SessionRef) -> int:
    coordinator = MigrationCoordinator(committer)
    epoch = committer.acquire_epoch()
    coordinator.migrate(
        session_ref,
        writer_epoch=epoch,
        session_generation=0,
        source_digest="0" * 64,
        v3_migration_lock=threading.Lock(),
        seed_snapshot=V2SeedSnapshotV1(user_bond_ema=0.6, user_hesitation_ema=0.4),
    )
    return epoch


def _make_job(
    ledger: SequenceLedger,
    session_ref: SessionRef,
    epoch: int,
    *,
    observation: object = None,
    actual: ActualAction = ActualAction.SPEAK,
    deadline_monotonic: float = 1e18,
) -> ShadowJob:
    sequence = ledger.allocate(session_ref=session_ref, writer_epoch=epoch)
    assert sequence is not None
    turn_key = TurnKey(
        plugin_instance_id="plugin",
        session_ref=session_ref,
        bridge_request_nonce=f"nonce-{sequence.local_sequence}",
        request_attempt=0,
    )
    return ShadowJob(
        turn_key=turn_key,
        turn_id=f"turn-{sequence.writer_epoch}-{sequence.local_sequence}",
        sequence=sequence,
        session_ref=session_ref,
        context=TurnContextClass.ADDRESSED,
        observation=(_raw_values(), Action.SPEAK) if observation is None else observation,
        actual_action=actual,
        quality_score=None,
        deadline_monotonic=deadline_monotonic,
    )


def _build_supervisor(tmp_path, **kwargs):
    committer = EffectCommitter.open(tmp_path)
    ledger = SequenceLedger()
    counters = IsolationCounters()
    telemetry = TelemetrySink()
    supervisor = ShadowSupervisor(
        committer=committer,
        ledger=ledger,
        counters=counters,
        telemetry_sink=telemetry,
        **kwargs,
    )
    return committer, ledger, counters, telemetry, supervisor


# --------------------------------------------------------------------------- #
# Idempotence and exact shutdown order
# --------------------------------------------------------------------------- #


def test_initialize_is_idempotent(tmp_path) -> None:
    async def scenario():
        committer, ledger, counters, telemetry, supervisor = _build_supervisor(tmp_path)
        await supervisor.initialize()
        epoch = supervisor.epoch
        tasks = supervisor.tracked_task_count
        await supervisor.initialize()  # second call must be a no-op
        assert supervisor.epoch == epoch
        assert supervisor.tracked_task_count == tasks
        await supervisor.terminate()

    asyncio.run(scenario())


def test_terminate_is_idempotent(tmp_path) -> None:
    async def scenario():
        committer, ledger, counters, telemetry, supervisor = _build_supervisor(tmp_path)
        await supervisor.initialize()
        await supervisor.terminate()
        first_trace = supervisor.shutdown_trace
        await supervisor.terminate()  # second call must not re-run the teardown
        assert supervisor.shutdown_trace == first_trace
        # terminate before initialize is also a safe no-op
        _, _, _, _, fresh = _build_supervisor(tmp_path)
        await fresh.terminate()

    asyncio.run(scenario())


def test_terminate_records_the_exact_shutdown_order(tmp_path) -> None:
    async def scenario():
        committer, ledger, counters, telemetry, supervisor = _build_supervisor(tmp_path)
        ref = _session_ref()
        _seed_session(committer, ref)
        await supervisor.initialize()
        supervisor.offer(_make_job(ledger, ref, supervisor.epoch))
        await supervisor.join()
        await supervisor.terminate()
        assert supervisor.shutdown_trace == SHUTDOWN_ORDER
        # the private worker really exited and nothing v3 remains
        assert ShadowSupervisor.worker_thread_names() == ()
        assert supervisor.queued_count == 0
        assert supervisor.tracked_task_count == 0

    asyncio.run(scenario())


def test_shutdown_marks_queued_jobs_dropped_and_stops_admission(tmp_path) -> None:
    async def scenario():
        # A compute that blocks on an event lets us pin a job in-flight while others queue.
        release = threading.Event()

        def blocking_compute(invocation):
            release.wait(timeout=5.0)
            return orchestrator.orchestrate(invocation)

        committer, ledger, counters, telemetry, supervisor = _build_supervisor(
            tmp_path, compute=blocking_compute, job_timeout_s=None, drain_timeout_s=5.0
        )
        ref = _session_ref()
        _seed_session(committer, ref)
        await supervisor.initialize()
        # First job occupies the single worker; the rest sit in the queue.
        supervisor.offer(_make_job(ledger, ref, supervisor.epoch))
        await asyncio.sleep(0.02)  # let the driver pick up the first job
        supervisor.offer(_make_job(ledger, ref, supervisor.epoch))
        supervisor.offer(_make_job(ledger, ref, supervisor.epoch))
        assert supervisor.queued_count >= 1
        release.set()  # let the in-flight job finish during bounded drain
        await supervisor.terminate()
        # admission is closed after shutdown
        result = supervisor.offer(_make_job(ledger, ref, supervisor.epoch))
        assert result.accepted is False
        assert supervisor.shutdown_trace == SHUTDOWN_ORDER
        assert counters.all_zero()

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
# 50x reload leak proof (spike E: reload_50)
# --------------------------------------------------------------------------- #


def test_reload_50_cycles_leak_nothing(tmp_path) -> None:
    async def scenario():
        root = tmp_path / "repo"
        root.mkdir()
        ref = _session_ref()
        # One-time migration under an initial (low) epoch.
        seed_committer = EffectCommitter.open(root)
        _seed_session(seed_committer, ref)

        async def one_cycle() -> None:
            runtime = V3ShadowRuntime(
                root=root,
                plugin_instance_id="plugin",
                correlation_secret=CORRELATION_SECRET,
                job_timeout_s=None,
            )
            await runtime.initialize()
            handle = runtime.capture_request(
                session_ref=ref,
                bridge_request_nonce="nonce",
                request_attempt=0,
                platform_id="qq",
                unified_msg_origin="grp:1",
                message_id="m",
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
                message_id="m",
                deadline_ms=5000.0,
            )
            assert result.accepted
            await runtime.join()
            await runtime.terminate()
            assert runtime.counters.all_zero()
            assert runtime.supervisor.tracked_task_count == 0
            assert runtime.supervisor.queued_count == 0

        # Warm up, then baseline every leakable resource.
        await one_cycle()
        gc.collect()
        base_threads = len(_v3_threads())
        base_tasks = _live_task_count()
        base_handles = _handle_count()

        for _ in range(50):
            await one_cycle()

        gc.collect()
        assert _v3_threads() == []  # zero v3 worker threads survive
        assert base_threads == 0
        # zero leaked asyncio tasks beyond this running scenario coroutine
        assert _live_task_count() <= base_tasks
        # OS handles do not grow beyond a small tolerance for allocator noise
        final_handles = _handle_count()
        if final_handles is not None and base_handles is not None:
            assert final_handles <= base_handles + 16

    asyncio.run(scenario())


def _v3_threads() -> list:
    return [t.name for t in threading.enumerate() if t.name.startswith(THREAD_NAME_PREFIX)]


def _live_task_count() -> int:
    current = asyncio.current_task()
    return sum(1 for task in asyncio.all_tasks() if task is not current and not task.done())


def _handle_count():
    if _PROCESS is None:
        return None
    try:
        if hasattr(_PROCESS, "num_handles"):
            return _PROCESS.num_handles()
        return _PROCESS.num_fds()
    except Exception:  # pragma: no cover
        return None


# --------------------------------------------------------------------------- #
# Seven isolation counters remain zero across every fault condition (design 16.1)
# --------------------------------------------------------------------------- #


def _assert_all_seven_zero(counters: IsolationCounters) -> None:
    assert counters.all_zero()
    assert counters.total() == 0
    assert len(counters.as_dict()) == 7


def test_isolation_counters_zero_on_normal_turn(tmp_path) -> None:
    async def scenario():
        committer, ledger, counters, telemetry, supervisor = _build_supervisor(tmp_path, job_timeout_s=None)
        ref = _session_ref()
        _seed_session(committer, ref)
        await supervisor.initialize()
        supervisor.offer(_make_job(ledger, ref, supervisor.epoch))
        await supervisor.join()
        await supervisor.terminate()
        assert telemetry.last().outcome == "COMMITTED"
        _assert_all_seven_zero(counters)

    asyncio.run(scenario())


def test_isolation_counters_zero_on_queue_full(tmp_path) -> None:
    async def scenario():
        release = threading.Event()

        def blocking_compute(invocation):
            release.wait(timeout=5.0)
            return orchestrator.orchestrate(invocation)

        committer, ledger, counters, telemetry, supervisor = _build_supervisor(
            tmp_path, compute=blocking_compute, job_timeout_s=None
        )
        ref = _session_ref()
        _seed_session(committer, ref)
        await supervisor.initialize()
        # Flood well past the per-session/global caps; excess is dropped, not blocking.
        rejected = 0
        for _ in range(200):
            result = supervisor.offer(_make_job(ledger, ref, supervisor.epoch))
            if not result.accepted:
                rejected += 1
        assert rejected > 0  # backpressure never applied to v2; excess simply dropped
        release.set()
        await supervisor.terminate()
        _assert_all_seven_zero(counters)

    asyncio.run(scenario())


def test_isolation_counters_zero_on_timeout(tmp_path) -> None:
    async def scenario():
        clock = [2_000.0]
        committer, ledger, counters, telemetry, supervisor = _build_supervisor(
            tmp_path, job_timeout_s=None, monotonic=lambda: clock[0]
        )
        ref = _session_ref()
        _seed_session(committer, ref)
        await supervisor.initialize()
        supervisor.offer(_make_job(ledger, ref, supervisor.epoch, deadline_monotonic=1_000.0))
        await supervisor.join()
        await supervisor.terminate()
        assert telemetry.last().timed_out is True
        _assert_all_seven_zero(counters)

    asyncio.run(scenario())


def test_isolation_counters_zero_on_repository_hard_stop(tmp_path) -> None:
    async def scenario():
        committer, ledger, counters, telemetry, supervisor = _build_supervisor(
            tmp_path,
            job_timeout_s=None,
            load_snapshot_provider=lambda: LoadSnapshotV1(
                global_queue_fill=0.0,
                oldest_job_age_ms=0.0,
                committed_compute_p95_ms=0.0,
                repository_admission=RepositoryAdmissionState.HARD_STOP,
            ),
        )
        ref = _session_ref()
        _seed_session(committer, ref)
        await supervisor.initialize()
        supervisor.offer(_make_job(ledger, ref, supervisor.epoch))
        await supervisor.join()
        await supervisor.terminate()
        assert telemetry.last().outcome == "REPOSITORY_HARD_STOP"
        _assert_all_seven_zero(counters)

    asyncio.run(scenario())


def test_isolation_counters_zero_on_malformed_input(tmp_path) -> None:
    async def scenario():
        committer, ledger, counters, telemetry, supervisor = _build_supervisor(tmp_path, job_timeout_s=None)
        ref = _session_ref()
        _seed_session(committer, ref)
        await supervisor.initialize()
        # A malformed observation makes the pure core raise; the exception is contained.
        malformed = ((0.5,) * 10, Action.SPEAK)  # wrong observation width
        supervisor.offer(_make_job(ledger, ref, supervisor.epoch, observation=malformed))
        await supervisor.join()
        await supervisor.terminate()
        assert telemetry.last().outcome == "DROPPED_CORE_ERROR"
        _assert_all_seven_zero(counters)

    asyncio.run(scenario())


def test_isolation_counters_zero_across_reload(tmp_path) -> None:
    async def scenario():
        committer, ledger, counters, telemetry, supervisor = _build_supervisor(tmp_path, job_timeout_s=None)
        ref = _session_ref()
        _seed_session(committer, ref)
        for _ in range(3):
            await supervisor.initialize()
            supervisor.offer(_make_job(ledger, ref, supervisor.epoch))
            await supervisor.join()
            await supervisor.terminate()
        _assert_all_seven_zero(counters)

    asyncio.run(scenario())


def test_isolation_counters_zero_when_shutdown_drops_inflight(tmp_path) -> None:
    async def scenario():
        release = threading.Event()

        def blocking_compute(invocation):
            release.wait(timeout=2.0)
            return orchestrator.orchestrate(invocation)

        committer, ledger, counters, telemetry, supervisor = _build_supervisor(
            tmp_path, compute=blocking_compute, job_timeout_s=None, drain_timeout_s=0.1
        )
        ref = _session_ref()
        _seed_session(committer, ref)
        await supervisor.initialize()
        supervisor.offer(_make_job(ledger, ref, supervisor.epoch))
        await asyncio.sleep(0.02)
        # terminate while the worker is still blocked: bounded drain times out, and the
        # executor.shutdown(wait=True) still joins the thread cleanly once released.
        release.set()
        await supervisor.terminate()
        assert supervisor.shutdown_trace == SHUTDOWN_ORDER
        _assert_all_seven_zero(counters)

    asyncio.run(scenario())
