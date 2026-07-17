"""RED/GREEN tests for Task 12: private executor, profiles, and the supervisor.

These prove the design-14.2/14.3 invariants of the off-event-loop shadow:

* ``offer()`` is bounded, non-blocking, and never a coroutine;
* every session is processed serially by exactly one private worker;
* the single worker gives fair, starvation-free round-robin service;
* a :class:`ComputeProfile` is frozen *before* the core runs;
* a monotonic deadline is checked only *between* named stages;
* a timeout discards the whole partial invocation (no state, no trace);
* a sealed/older writer epoch can never publish;
* the seven design-16.1 isolation counters stay zero.

The private executor uses ``ThreadPoolExecutor(max_workers=1,
thread_name_prefix="sylanne-v3")`` and v3 futures are never placed in a plugin's
``_background_tasks``.
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from sylanne_alpha.v2core.shadow_snapshot import V2SeedSnapshotV1
from sylanne_alpha.v3bridge import limits
from sylanne_alpha.v3bridge.actual_action import ActualAction
from sylanne_alpha.v3bridge.comparator import ShadowComparison, compare, to_core_action
from sylanne_alpha.v3bridge._state_repository import FaultPoint
from sylanne_alpha.v3bridge.effect_committer import EffectCommitter
from sylanne_alpha.v3bridge.migration_coordinator import MigrationCoordinator
from sylanne_alpha.v3bridge.models import LoadSnapshotV1, RepositoryAdmissionState
from sylanne_alpha.v3bridge.profile_selector import (
    ProfileSelector,
    build_compute_profile,
    immediate_load_level,
)
from sylanne_alpha.v3bridge.runtime_telemetry import IsolationCounters, TelemetrySink
from sylanne_alpha.v3bridge.shadow_supervisor import (
    SHUTDOWN_ORDER,
    THREAD_NAME_PREFIX,
    OfferStatus,
    SessionQueues,
    ShadowJob,
    ShadowSupervisor,
)
from sylanne_alpha.v3bridge.turn_registry import SequenceLedger, SequenceStatus
from sylanne_alpha.v3core import formula_v1 as formula
from sylanne_alpha.v3core import orchestrator
from sylanne_alpha.v3core.contracts import (
    Action,
    SessionRef,
    TurnContextClass,
    TurnKey,
    TurnSequence,
)


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #


def _raw_values(overrides: dict[int, float] | None = None) -> tuple:
    values: list[float | None] = [None] * 36
    for index in range(36):
        if index in (27, 28, 29, 32, 33, 34, 35):
            values[index] = None
        else:
            values[index] = 0.5
    values[30] = 1.0
    values[31] = 120.0
    for index, value in (overrides or {}).items():
        values[index] = value
    return tuple(values)


def _session_ref(tag: str = "key-1", generation: int = 1) -> SessionRef:
    return SessionRef(key_id=tag, session_digest=bytes([hash(tag) & 0xFF]) * 32, session_generation=generation)


def _snapshot(fill: float = 0.0, age: float = 0.0, p95: float = 0.0, admission=RepositoryAdmissionState.OPEN) -> LoadSnapshotV1:
    return LoadSnapshotV1(
        global_queue_fill=fill,
        oldest_job_age_ms=age,
        committed_compute_p95_ms=p95,
        repository_admission=admission,
    )


def _seed_session(committer: EffectCommitter, session_ref: SessionRef) -> int:
    """Migrate a session at its own (lower) epoch; return that migration epoch."""

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
    actual: ActualAction = ActualAction.SPEAK,
    quality: float | None = None,
    deadline_monotonic: float = 1e18,
    previous_action: Action | None = Action.SPEAK,
    context: TurnContextClass = TurnContextClass.ADDRESSED,
    nonce: str | None = None,
) -> ShadowJob:
    sequence = ledger.allocate(session_ref=session_ref, writer_epoch=epoch)
    assert sequence is not None
    request_nonce = nonce if nonce is not None else f"nonce-{sequence.local_sequence}-{session_ref.key_id}"
    turn_key = TurnKey(
        plugin_instance_id="plugin",
        session_ref=session_ref,
        bridge_request_nonce=request_nonce,
        request_attempt=0,
    )
    return ShadowJob(
        turn_key=turn_key,
        turn_id=f"turn-{session_ref.key_id}-{sequence.local_sequence}",
        sequence=sequence,
        session_ref=session_ref,
        context=context,
        observation=(_raw_values(), previous_action),
        actual_action=actual,
        quality_score=quality,
        deadline_monotonic=deadline_monotonic,
    )


class _Recorder:
    """A thread-safe compute wrapper recording call args and worker concurrency."""

    def __init__(self, inner=orchestrator.orchestrate) -> None:
        self._inner = inner
        self.invocations: list = []
        self.arg_counts: list = []
        self._lock = threading.Lock()
        self._active = 0
        self.max_concurrency = 0

    def __call__(self, invocation, *extra):
        with self._lock:
            self.invocations.append(invocation)
            self.arg_counts.append(1 + len(extra))
            self._active += 1
            self.max_concurrency = max(self.max_concurrency, self._active)
        try:
            return self._inner(invocation)
        finally:
            with self._lock:
                self._active -= 1


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
# ProfileSelector — degrade immediately, recover slowly (design 14.2 / manifest)
# --------------------------------------------------------------------------- #


def test_profile_selector_nominal_is_full_24_stdp() -> None:
    selection = ProfileSelector().select(_snapshot())
    assert selection.level == 0
    assert selection.profile_name == "FULL_24_STDP"
    assert selection.profile is not None
    assert selection.skip is False and selection.dropped is False


@pytest.mark.parametrize(
    "fill, expected_level, expected_name",
    [
        (0.0, 0, "FULL_24_STDP"),
        (0.25, 1, "FULL_24_NO_STDP"),
        (0.50, 2, "SNN_16_NO_STDP"),
        (0.70, 3, "REUSE_LAST_SNN_SUMMARY"),
        (0.85, 4, "DETERMINISTIC_CONTINUOUS_ONLY"),
        (1.0, 5, "SKIP_V3_TURN"),
    ],
)
def test_profile_ladder_maps_each_fill_threshold(fill, expected_level, expected_name) -> None:
    selection = ProfileSelector().select(_snapshot(fill=fill))
    assert selection.level == expected_level
    assert selection.profile_name == expected_name
    if expected_level == 5:
        assert selection.skip is True and selection.profile is None


def test_profile_degrade_triggers_on_any_axis() -> None:
    assert immediate_load_level(_snapshot(age=200.0)) == 4
    assert immediate_load_level(_snapshot(p95=5.0)) == 3
    assert immediate_load_level(_snapshot(fill=1.0)) == 5


def test_profile_degradation_is_immediate_jump() -> None:
    selector = ProfileSelector()
    selection = selector.select(_snapshot(fill=0.85))
    assert selection.level == 4  # jumped straight from 0 to 4


def test_profile_recovery_takes_32_consecutive_good_snapshots() -> None:
    selector = ProfileSelector()
    selector.select(_snapshot(fill=0.85))  # level 4
    assert selector.level == 4
    # 31 good snapshots are not yet enough to step down one level.
    for _ in range(formula.RECOVERY_CONSECUTIVE_SNAPSHOTS - 1):
        selector.select(_snapshot())
    assert selector.level == 4
    selector.select(_snapshot())  # the 32nd good snapshot steps down exactly one level
    assert selector.level == 3


def test_profile_recovery_run_resets_on_a_bad_snapshot() -> None:
    selector = ProfileSelector()
    selector.select(_snapshot(fill=0.85))
    for _ in range(20):
        selector.select(_snapshot())
    # fill 0.70 is above 80% of level-4's entry threshold (0.68), so it is NOT a
    # recovery snapshot: the clean run resets even though it does not re-degrade.
    selector.select(_snapshot(fill=0.70))
    assert selector.level == 4
    for _ in range(formula.RECOVERY_CONSECUTIVE_SNAPSHOTS - 1):
        selector.select(_snapshot())
    assert selector.level == 4  # run restarted, not yet 32 clean ones


def test_repository_hard_stop_forces_skip_and_drop() -> None:
    selection = ProfileSelector().select(_snapshot(admission=RepositoryAdmissionState.HARD_STOP))
    assert selection.skip is True
    assert selection.dropped is True
    assert selection.reason == "REPOSITORY_HARD_STOP"
    assert selection.profile is None


def test_reuse_without_prior_summary_falls_back_to_deterministic() -> None:
    selector = ProfileSelector()
    selection = selector.select(_snapshot(fill=0.70), has_prior_summary=False)
    assert selection.level == 3
    assert selection.profile_name == "DETERMINISTIC_CONTINUOUS_ONLY"
    assert selection.reason == "REUSE_WITHOUT_SUMMARY"


def test_build_compute_profile_rejects_skip() -> None:
    with pytest.raises(ValueError):
        build_compute_profile("SKIP_V3_TURN")


# --------------------------------------------------------------------------- #
# Comparator (design 14.2 step 8)
# --------------------------------------------------------------------------- #


def test_comparator_agreement_and_disagreement() -> None:
    assert compare(Action.SPEAK, ActualAction.SPEAK).agree is True
    disagree = compare(Action.HOLD, ActualAction.SPEAK)
    assert disagree.agree is False and disagree.reason == "DISAGREE"


def test_comparator_known_hold_contradiction_is_the_safety_proxy() -> None:
    assert compare(Action.SPEAK, ActualAction.HOLD).known_hold_contradiction is True
    assert compare(Action.REACH, ActualAction.HOLD).known_hold_contradiction is True
    assert compare(Action.HOLD, ActualAction.HOLD).known_hold_contradiction is False


def test_comparator_unknown_and_unmatched_never_settle() -> None:
    for actual, reason in ((ActualAction.UNKNOWN, "ACTUAL_UNKNOWN"), (ActualAction.UNMATCHED_RESPONSE, "ACTUAL_UNMATCHED")):
        comparison = compare(Action.SPEAK, actual)
        assert isinstance(comparison, ShadowComparison)
        assert comparison.agree is False
        assert comparison.known_hold_contradiction is False
        assert comparison.reason == reason
        assert to_core_action(actual) is None


# --------------------------------------------------------------------------- #
# SessionQueues — bounded, serial per session, fair round-robin
# --------------------------------------------------------------------------- #


def test_offer_is_a_plain_non_coroutine_function() -> None:
    assert asyncio.iscoroutinefunction(ShadowSupervisor.offer) is False


def test_session_queue_enforces_per_session_cap() -> None:
    queues = SessionQueues(per_session_cap=limits.MAX_PER_SESSION_QUEUE, global_cap=limits.MAX_GLOBAL_QUEUE, max_sessions=limits.MAX_ACTIVE_SESSIONS)
    ledger = SequenceLedger()
    ref = _session_ref()
    accepted = 0
    for _ in range(limits.MAX_PER_SESSION_QUEUE + 3):
        job = _make_job(ledger, ref, 1)
        if queues.offer(job, 0.0) is OfferStatus.ACCEPTED:
            accepted += 1
    assert accepted == limits.MAX_PER_SESSION_QUEUE


def test_session_queue_enforces_global_cap() -> None:
    queues = SessionQueues(per_session_cap=1000, global_cap=limits.MAX_GLOBAL_QUEUE, max_sessions=limits.MAX_ACTIVE_SESSIONS)
    ledger = SequenceLedger()
    ref = _session_ref()
    accepted = sum(
        queues.offer(_make_job(ledger, ref, 1), 0.0) is OfferStatus.ACCEPTED
        for _ in range(limits.MAX_GLOBAL_QUEUE + 5)
    )
    assert accepted == limits.MAX_GLOBAL_QUEUE
    assert queues.offer(_make_job(ledger, ref, 1), 0.0) is OfferStatus.DROPPED_GLOBAL_FULL


def test_session_queue_enforces_max_sessions() -> None:
    queues = SessionQueues(per_session_cap=4, global_cap=1000, max_sessions=2)
    ledger = SequenceLedger()
    assert queues.offer(_make_job(ledger, _session_ref("a"), 1), 0.0) is OfferStatus.ACCEPTED
    assert queues.offer(_make_job(ledger, _session_ref("b"), 1), 0.0) is OfferStatus.ACCEPTED
    assert queues.offer(_make_job(ledger, _session_ref("c"), 1), 0.0) is OfferStatus.DROPPED_MAX_SESSIONS


def test_round_robin_serves_one_job_per_nonempty_session_preserving_order() -> None:
    queues = SessionQueues(per_session_cap=4, global_cap=1000, max_sessions=16)
    ledger = SequenceLedger()
    a, b = _session_ref("a"), _session_ref("b")
    ja1 = _make_job(ledger, a, 1)
    ja2 = _make_job(ledger, a, 1)
    jb1 = _make_job(ledger, b, 1)
    for job in (ja1, ja2, jb1):
        assert queues.offer(job, 0.0) is OfferStatus.ACCEPTED
    batch1 = queues.next_round_robin_batch()
    assert len(batch1) == 2  # one from a, one from b
    assert {job.session_ref for job in batch1} == {a, b}
    # per-session FIFO: session a's first job is ja1, not ja2
    a_job = next(job for job in batch1 if job.session_ref == a)
    assert a_job.turn_id == ja1.turn_id
    batch2 = queues.next_round_robin_batch()
    assert len(batch2) == 1 and batch2[0].turn_id == ja2.turn_id
    assert queues.next_round_robin_batch() == ()


def test_round_robin_does_not_starve_a_late_session() -> None:
    queues = SessionQueues(per_session_cap=4, global_cap=1000, max_sessions=16)
    ledger = SequenceLedger()
    busy = _session_ref("busy")
    for _ in range(4):
        queues.offer(_make_job(ledger, busy, 1), 0.0)
    # A late session shows up; it must be served on the very next cycle.
    late = _session_ref("late")
    queues.offer(_make_job(ledger, late, 1), 0.0)
    batch = queues.next_round_robin_batch()
    assert late in {job.session_ref for job in batch}


# --------------------------------------------------------------------------- #
# Supervisor execution semantics
# --------------------------------------------------------------------------- #


def test_single_private_worker_serializes_and_is_named(tmp_path) -> None:
    async def scenario(tmp_path):
        recorder = _Recorder()
        committer, ledger, counters, telemetry, supervisor = _build_supervisor(
            tmp_path, compute=recorder, job_timeout_s=None
        )
        refs = [_session_ref(f"s{i}") for i in range(3)]
        for ref in refs:
            _seed_session(committer, ref)
        await supervisor.initialize()
        assert THREAD_NAME_PREFIX == "sylanne-v3"
        for ref in refs:
            supervisor.offer(_make_job(ledger, ref, supervisor.epoch))
        await supervisor.join()
        await supervisor.terminate()
        # Exactly one worker thread ever ran the core: strict serialization.
        assert recorder.max_concurrency == 1
        assert len(recorder.invocations) == 3
        # every commit landed
        assert sum(1 for t in telemetry.recent() if t.outcome == "COMMITTED") == 3
        assert counters.all_zero()

    asyncio.run(scenario(tmp_path))


def test_v3_futures_never_enter_plugin_background_tasks(tmp_path) -> None:
    async def scenario(tmp_path):
        background_tasks: set = set()  # the legacy/v2-owned set
        committer, ledger, counters, telemetry, supervisor = _build_supervisor(tmp_path, job_timeout_s=None)
        ref = _session_ref()
        _seed_session(committer, ref)
        await supervisor.initialize()
        # the supervisor owns its own tracked-task set...
        assert supervisor.tracked_task_count >= 1
        supervisor.offer(_make_job(ledger, ref, supervisor.epoch))
        await supervisor.join()
        # ...and never touched the legacy background-tasks set.
        assert background_tasks == set()
        assert supervisor._executor._max_workers == 1
        assert supervisor._executor._thread_name_prefix == THREAD_NAME_PREFIX
        await supervisor.terminate()

    asyncio.run(scenario(tmp_path))


class _IOWatchingCommitter:
    """Delegates to a real committer, recording which thread each repository call ran on.

    Optionally blocks (``time.sleep``, i.e. exactly what an fsync/flock contention
    does to its caller) so a test can measure what that costs the host loop.
    """

    def __init__(self, inner: EffectCommitter, *, block_s: float = 0.0) -> None:
        self._inner = inner
        self._block_s = block_s
        self.load_threads: list = []
        self.commit_threads: list = []

    def __getattr__(self, name):  # acquire_epoch / seal_epoch / everything else
        return getattr(self._inner, name)

    def load_state(self, session_ref):
        self.load_threads.append(threading.current_thread().name)
        if self._block_s:
            time.sleep(self._block_s)
        return self._inner.load_state(session_ref)

    def commit_turn(self, command):
        self.commit_threads.append(threading.current_thread().name)
        if self._block_s:
            time.sleep(self._block_s)
        return self._inner.commit_turn(command)


def test_repository_io_runs_on_the_v3_worker_not_the_event_loop(tmp_path) -> None:
    """load_state/commit_turn fsync and take a cross-process lock: never inline on the loop.

    Regression guard for a real defect: ``_process_job`` is scheduled with
    ``create_task`` on the *host* loop, so a synchronous committer call there made v2's
    loop wait on v3's disk IO -- violating design 14.2 ("v3 never adds backpressure to
    v2") and reintroducing the hang class this project has been burned by, which no
    ``except`` can contain.
    """

    async def scenario(tmp_path):
        inner = EffectCommitter.open(tmp_path)
        watcher = _IOWatchingCommitter(inner)
        ref = _session_ref()
        _seed_session(inner, ref)
        ledger = SequenceLedger()
        telemetry = TelemetrySink()
        supervisor = ShadowSupervisor(
            committer=watcher,
            ledger=ledger,
            counters=IsolationCounters(),
            telemetry_sink=telemetry,
            job_timeout_s=None,
        )
        loop_thread = threading.current_thread().name
        await supervisor.initialize()
        supervisor.offer(_make_job(ledger, ref, supervisor.epoch))
        await supervisor.join()
        await supervisor.terminate()

        assert sum(1 for t in telemetry.recent() if t.outcome == "COMMITTED") == 1
        assert watcher.load_threads and watcher.commit_threads
        # Both repository phases ran on the v3-private worker...
        for name in watcher.load_threads + watcher.commit_threads:
            assert name.startswith(THREAD_NAME_PREFIX), name
            # ...which is by construction not the thread running the event loop.
            assert name != loop_thread

    asyncio.run(scenario(tmp_path))


def test_slow_repository_io_does_not_stall_the_event_loop(tmp_path) -> None:
    """Quantitative proof: a blocking repository must not show up as loop stall.

    A high-frequency heartbeat measures the worst gap between consecutive loop
    iterations while a turn whose load+commit block for 250 ms each is processed. If
    the IO ran inline the heartbeat could not tick for ~500 ms; offloaded, the loop
    keeps servicing it throughout.
    """

    async def scenario(tmp_path):
        block_s = 0.25
        inner = EffectCommitter.open(tmp_path)
        watcher = _IOWatchingCommitter(inner, block_s=block_s)
        ref = _session_ref()
        _seed_session(inner, ref)
        ledger = SequenceLedger()
        telemetry = TelemetrySink()
        supervisor = ShadowSupervisor(
            committer=watcher,
            ledger=ledger,
            counters=IsolationCounters(),
            telemetry_sink=telemetry,
            job_timeout_s=None,
        )
        await supervisor.initialize()

        stalls: list = []
        beating = True

        async def heartbeat() -> None:
            previous = time.monotonic()
            while beating:
                await asyncio.sleep(0)
                now = time.monotonic()
                stalls.append(now - previous)
                previous = now

        pulse = asyncio.create_task(heartbeat())
        supervisor.offer(_make_job(ledger, ref, supervisor.epoch))
        await supervisor.join()
        beating = False
        await pulse
        await supervisor.terminate()

        assert sum(1 for t in telemetry.recent() if t.outcome == "COMMITTED") == 1
        assert watcher.load_threads and watcher.commit_threads
        worst = max(stalls)
        # The loop kept turning throughout ~500 ms of blocking repository IO. The
        # bound is deliberately far below one block: inline IO would stall ~250 ms.
        assert worst < block_s / 5, f"event loop stalled {worst * 1000:.1f} ms on v3 IO"

    asyncio.run(scenario(tmp_path))


def test_terminate_does_not_stall_the_event_loop_while_the_repo_lock_is_held(tmp_path) -> None:
    """terminate()'s seal_epoch must not block the loop behind our own worker's lock.

    Found by adversarial review of the offload fix itself: moving commit_turn onto the
    v3 worker is what first lets the loop reach terminate() *while a v3 thread holds
    the cross-process repo lock*. ``seal_epoch`` takes that same non-reentrant lock and
    fsyncs, so sealing inline moved the stall out of ``_process_job`` and into
    ``terminate()`` rather than removing it. Measured before the fix: 3031.7 ms of loop
    stall inside terminate(); after: ~5 ms.

    ``drain_timeout_s`` is deliberately shorter than the commit so the bounded drain
    expires and terminate really does reach seal_epoch with the commit still in flight.
    The stall must be injected INSIDE the repository lock (a plain sleep around
    ``commit_turn`` holds no lock and reproduces nothing).
    """

    async def scenario(tmp_path):
        block_s = 0.6
        armed = threading.Event()
        hit = threading.Event()

        def injector(point) -> None:
            # Block while holding the cross-process repo lock, exactly as a slow fsync
            # or a contended flock does. Armed only after seeding, which uses this same
            # fault point for its own migration commit.
            if point is FaultPoint.BEFORE_POINTER_PUBLISH and armed.is_set() and not hit.is_set():
                hit.set()
                time.sleep(block_s)

        committer = EffectCommitter.open(tmp_path, fault_injector=injector)
        ref = _session_ref()
        _seed_session(committer, ref)
        ledger = SequenceLedger()
        supervisor = ShadowSupervisor(
            committer=committer,
            ledger=ledger,
            counters=IsolationCounters(),
            telemetry_sink=TelemetrySink(),
            job_timeout_s=None,
            drain_timeout_s=0.05,  # expires well before the commit finishes
        )
        await supervisor.initialize()
        armed.set()
        supervisor.offer(_make_job(ledger, ref, supervisor.epoch))

        stalls: list = []
        beating = True

        async def heartbeat() -> None:
            previous = time.monotonic()
            while beating:
                await asyncio.sleep(0)
                now = time.monotonic()
                stalls.append(now - previous)
                previous = now

        pulse = asyncio.create_task(heartbeat())
        # Wait (off-loop) until the commit really holds the repo lock.
        assert await asyncio.to_thread(hit.wait, 5.0), "fault never fired: the test would prove nothing"
        mark = len(stalls)
        await supervisor.terminate()
        beating = False
        await pulse

        worst_during_terminate = max(stalls[mark:]) if len(stalls) > mark else 0.0
        assert worst_during_terminate < block_s / 4, (
            f"terminate() stalled the loop {worst_during_terminate * 1000:.1f} ms on repo IO"
        )
        # The exact ordered teardown is unchanged by the offload.
        assert supervisor.shutdown_trace == SHUTDOWN_ORDER

    asyncio.run(scenario(tmp_path))


def test_profile_is_frozen_before_the_core_runs(tmp_path) -> None:
    async def scenario(tmp_path):
        recorder = _Recorder()
        committer, ledger, counters, telemetry, supervisor = _build_supervisor(
            tmp_path, compute=recorder, job_timeout_s=None
        )
        ref = _session_ref()
        _seed_session(committer, ref)
        await supervisor.initialize()
        supervisor.offer(_make_job(ledger, ref, supervisor.epoch))
        await supervisor.join()
        await supervisor.terminate()
        assert len(recorder.invocations) == 1
        invocation = recorder.invocations[0]
        # The core received exactly one positional arg (the immutable invocation);
        # no clock, no deadline, no cancellation callback.
        assert recorder.arg_counts[0] == 1
        profile = invocation.envelope.compute_profile
        assert profile.profile_id == "FULL_24_STDP"
        # profile is consistent with the frozen manifest (core would reject otherwise)
        assert (profile.snn_enabled, profile.ticks, profile.stdp_enabled, profile.reuse_last_summary) == formula.FULL_24_STDP

    asyncio.run(scenario(tmp_path))


def test_deadline_checked_only_between_stages_timeout_before_compute(tmp_path) -> None:
    async def scenario(tmp_path):
        clock_value = [2_000.0]  # already past the deadline on the very first check
        recorder = _Recorder()
        committer, ledger, counters, telemetry, supervisor = _build_supervisor(
            tmp_path, compute=recorder, job_timeout_s=None, monotonic=lambda: clock_value[0]
        )
        ref = _session_ref()
        _seed_session(committer, ref)
        await supervisor.initialize()
        base_before = committer.load_state(ref).base.revision
        supervisor.offer(_make_job(ledger, ref, supervisor.epoch, deadline_monotonic=1_000.0))
        await supervisor.join()
        await supervisor.terminate()
        record = telemetry.last()
        assert record.outcome == "TIMEOUT" and record.timed_out is True
        # the first stage boundary tripped; the core was never entered
        assert record.deadline_checkpoints == ("before_load",)
        assert len(recorder.invocations) == 0
        # no state advanced, no trace
        assert committer.load_state(ref).base.revision == base_before
        assert counters.all_zero()

    asyncio.run(scenario(tmp_path))


def test_timeout_after_compute_leaves_no_state_or_trace(tmp_path) -> None:
    async def scenario(tmp_path):
        clock_value = [1_000.0]

        def bumping_compute(invocation):
            # The core is opaque to the clock; the supervisor's next checkpoint sees time pass.
            result = orchestrator.orchestrate(invocation)
            clock_value[0] = 5_000.0  # jump past the deadline before the commit checkpoint
            return result

        committer, ledger, counters, telemetry, supervisor = _build_supervisor(
            tmp_path, compute=bumping_compute, job_timeout_s=None, monotonic=lambda: clock_value[0]
        )
        ref = _session_ref()
        _seed_session(committer, ref)
        await supervisor.initialize()
        base_before = committer.load_state(ref).base.revision
        supervisor.offer(_make_job(ledger, ref, supervisor.epoch, deadline_monotonic=1_500.0))
        await supervisor.join()
        await supervisor.terminate()
        record = telemetry.last()
        assert record.outcome == "TIMEOUT" and record.timed_out is True
        assert record.deadline_checkpoints[-1] == "before_commit"
        # compute ran, but nothing was committed: no state, no trace.
        assert committer.load_state(ref).base.revision == base_before
        assert counters.all_zero()

    asyncio.run(scenario(tmp_path))


def test_executor_timeout_discards_the_invocation_without_state(tmp_path) -> None:
    async def scenario(tmp_path):
        release = threading.Event()

        def slow_compute(invocation):
            # The single worker is stuck past the bounded await; the supervisor abandons
            # the result (a running thread cannot be cancelled) and commits nothing.
            release.wait(timeout=3.0)
            return orchestrator.orchestrate(invocation)

        committer, ledger, counters, telemetry, supervisor = _build_supervisor(
            tmp_path, compute=slow_compute, job_timeout_s=0.05
        )
        ref = _session_ref()
        _seed_session(committer, ref)
        await supervisor.initialize()
        base_before = committer.load_state(ref).base.revision
        supervisor.offer(_make_job(ledger, ref, supervisor.epoch))
        await supervisor.join()
        record = telemetry.last()
        assert record.outcome == "TIMEOUT" and record.timed_out is True
        # the executor bound tripped inside the compute phase; commit was never reached
        assert record.deadline_checkpoints[-1] == "before_compute"
        assert committer.load_state(ref).base.revision == base_before
        assert counters.all_zero()
        release.set()  # let the orphaned worker finish so shutdown can join it
        await supervisor.terminate()
        assert ShadowSupervisor.worker_thread_names() == ()

    asyncio.run(scenario(tmp_path))


def test_old_epoch_cannot_publish(tmp_path) -> None:
    async def scenario(tmp_path):
        committer, ledger, counters, telemetry, supervisor = _build_supervisor(tmp_path, job_timeout_s=None)
        ref = _session_ref()
        _seed_session(committer, ref)
        await supervisor.initialize()
        live_epoch = supervisor.epoch

        def sealing_compute(invocation):
            result = orchestrator.orchestrate(invocation)
            # A newer writer fences this epoch before the commit lands.
            committer.seal_epoch(live_epoch)
            return result

        supervisor._compute = sealing_compute  # inject after initialize for this scenario
        base_before = committer.load_state(ref).base.revision
        job = _make_job(ledger, ref, live_epoch)
        supervisor.offer(job)
        await supervisor.join()
        record = telemetry.last()
        assert record.outcome == "DROPPED_STALE_EPOCH"
        assert record.cas_committed is False
        # the fenced turn did not advance the published state
        assert committer.load_state(ref).base.revision == base_before
        assert ledger.status(ref, job.sequence) is SequenceStatus.DROPPED
        assert counters.all_zero()
        # terminate is still clean even though the epoch was sealed mid-flight
        await supervisor.terminate()

    asyncio.run(scenario(tmp_path))


def test_repository_hard_stop_skips_the_turn_without_state(tmp_path) -> None:
    async def scenario(tmp_path):
        recorder = _Recorder()
        committer, ledger, counters, telemetry, supervisor = _build_supervisor(
            tmp_path,
            compute=recorder,
            job_timeout_s=None,
            load_snapshot_provider=lambda: _snapshot(admission=RepositoryAdmissionState.HARD_STOP),
        )
        ref = _session_ref()
        _seed_session(committer, ref)
        await supervisor.initialize()
        base_before = committer.load_state(ref).base.revision
        supervisor.offer(_make_job(ledger, ref, supervisor.epoch))
        await supervisor.join()
        await supervisor.terminate()
        record = telemetry.last()
        assert record.outcome == "REPOSITORY_HARD_STOP"
        assert len(recorder.invocations) == 0  # the core never ran
        assert committer.load_state(ref).base.revision == base_before
        assert counters.all_zero()

    asyncio.run(scenario(tmp_path))
