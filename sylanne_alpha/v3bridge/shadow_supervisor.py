"""The v3-private off-event-loop shadow supervisor (design 14.2 / 14.3, plan Task 12).

The authoritative v2 response path only performs an immutable capture and a
*non-blocking* bounded :meth:`ShadowSupervisor.offer`; it never awaits v3
calculation.  All core calculation and canonical trace serialization *and every
repository access* (``load_state`` / ``commit_turn``, which fsync and take a
cross-process file lock) run in a v3-private
``ThreadPoolExecutor(max_workers=1, thread_name_prefix="sylanne-v3")`` via
:meth:`ShadowSupervisor._offload`, so cross-session execution is deliberately
globally serialized on the 2-core target.  Nothing that blocks may run inline on
the host loop: v3 must never add backpressure to v2 (design 14.2), and a wedged
fsync/flock is a hang, not an exception -- no ``except`` can contain it.
v3 futures/tasks are tracked in a v3-owned set and are **never** placed in the
plugin's ``_background_tasks``, whose shutdown order is owned by legacy/v2
subsystems.

Scheduling is a deterministic round-robin: each cycle takes at most one job from
every non-empty per-session queue, preserving per-session order and preventing a
busy session from starving another.  A frozen :class:`ComputeProfile` is selected
*before* the first core stage.  A monotonic deadline is checked only *between* named
supervisor phases — never inside the pure core, which reads no clock and no
cancellation callback.  A deadline (or executor) timeout discards the entire partial
invocation: no state, no trace, no telemetry join target — only bounded
:class:`RuntimeTelemetry`.  A sealed/older writer epoch can never publish.

The one stage that is *not* deadline-bounded is the CAS commit: orphaning a commit
cannot cancel the thread, so the write could still land after we recorded the turn
as dropped, and a torn ledger is worse than a slow one.  Because ``terminate``'s
drain *is* bounded, a slow commit can outlive the drain and have its supervising
await cancelled; :meth:`ShadowSupervisor._commit_offload` therefore fences the
commit with a done-callback that reports the real outcome (``COMMITTED_ORPHANED``
when the write landed unsupervised) even though the awaiting coroutine never
resumes.  The ledger, the telemetry and the disk cannot disagree.

``initialize`` / ``terminate`` are idempotent.  ``terminate`` performs the exact
ordered teardown of plan Task 12 and does not return until every v3 worker thread has
exited and every tracked task is gathered.
"""

from __future__ import annotations

import asyncio
import hashlib
import threading
import time
from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from sylanne_alpha.v3bridge.actual_action import ActualAction
from sylanne_alpha.v3bridge.comparator import compare as _default_compare
from sylanne_alpha.v3bridge.comparator import to_core_action
from sylanne_alpha.v3bridge.effect_committer import (
    CommitStatus,
    EffectCommitter,
    TurnCommit,
)
from sylanne_alpha.v3bridge.limits import (
    MAX_ACTIVE_SESSIONS,
    MAX_GLOBAL_QUEUE,
    MAX_PER_SESSION_QUEUE,
    WORKER_COUNT,
)
from sylanne_alpha.v3bridge.models import LoadSnapshotV1, RepositoryAdmissionState
from sylanne_alpha.v3bridge.profile_selector import ProfileSelector
from sylanne_alpha.v3bridge.runtime_telemetry import (
    IsolationCounters,
    RuntimeTelemetry,
    TelemetrySink,
)
from sylanne_alpha.v3bridge.turn_registry import SequenceLedger, TurnHandle, TurnRegistry
from sylanne_alpha.v3core.canonical import canonical_sha256
from sylanne_alpha.v3core.contracts import (
    CoreInvocation,
    ReactionFacts,
    SessionRef,
    TurnContextClass,
    TurnEnvelope,
    TurnKey,
    TurnSequence,
)
from sylanne_alpha.v3core.effects.models import V3StateEffect
from sylanne_alpha.v3core.orchestrator import orchestrate


THREAD_NAME_PREFIX = "sylanne-v3"

#: The exact ordered teardown names recorded by :meth:`ShadowSupervisor.terminate`.
SHUTDOWN_ORDER = (
    "stop_admission_detach",
    "mark_unqueued_dropped",
    "cancel_replay_metric",
    "bounded_drain",
    "close_committer_admission",
    "seal_epoch",
    "cancel_leftovers",
    "gather_tracked_tasks",
    "executor_shutdown",
    "clear_registries",
)


class _CoreTimeout(Exception):
    """Internal signal: the private executor did not finish within the bound."""


class _ResultFuture(Protocol):
    """Structural result surface shared by asyncio and concurrent futures."""

    def cancelled(self) -> bool: ...

    def result(self) -> object: ...


# --------------------------------------------------------------------------- #
# Offer result vocabulary
# --------------------------------------------------------------------------- #


class OfferStatus(Enum):
    ACCEPTED = "ACCEPTED"
    DROPPED_ADMISSION_CLOSED = "DROPPED_ADMISSION_CLOSED"
    DROPPED_SESSION_FULL = "DROPPED_SESSION_FULL"
    DROPPED_GLOBAL_FULL = "DROPPED_GLOBAL_FULL"
    DROPPED_MAX_SESSIONS = "DROPPED_MAX_SESSIONS"


@dataclass(frozen=True, slots=True)
class OfferResult:
    status: OfferStatus

    @property
    def accepted(self) -> bool:
        return self.status is OfferStatus.ACCEPTED


# --------------------------------------------------------------------------- #
# Immutable shadow job (design 14.2: "offers an immutable ShadowJob")
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ShadowJob:
    """One captured turn offered to the supervisor; the deadline lives only here."""

    turn_key: TurnKey
    turn_id: str
    sequence: TurnSequence
    session_ref: SessionRef
    context: TurnContextClass
    observation: object
    actual_action: ActualAction
    quality_score: float | None
    deadline_monotonic: float
    reaction_facts: ReactionFacts | None = None
    handle: TurnHandle | None = None

    def __post_init__(self) -> None:
        if type(self.turn_key) is not TurnKey:
            raise TypeError("turn_key must have exact type TurnKey")
        if type(self.sequence) is not TurnSequence:
            raise TypeError("sequence must have exact type TurnSequence")
        if type(self.session_ref) is not SessionRef:
            raise TypeError("session_ref must have exact type SessionRef")
        if type(self.context) is not TurnContextClass:
            raise TypeError("context must have exact type TurnContextClass")
        if type(self.actual_action) is not ActualAction:
            raise TypeError("actual_action must have exact type ActualAction")
        if self.quality_score is not None and type(self.quality_score) is not float:
            raise TypeError("quality_score must be float or None")
        if self.reaction_facts is not None and type(self.reaction_facts) is not ReactionFacts:
            raise TypeError("reaction_facts must be ReactionFacts or None")
        if type(self.deadline_monotonic) is not float:
            raise TypeError("deadline_monotonic must have exact type float")
        if self.handle is not None and type(self.handle) is not TurnHandle:
            raise TypeError("handle must be a TurnHandle or None")


# --------------------------------------------------------------------------- #
# Bounded per-session queues with deterministic round-robin scheduling
# --------------------------------------------------------------------------- #


class SessionQueues:
    """Bounded per-session FIFO queues with fair, starvation-free round-robin.

    Every non-empty session is served exactly once per :meth:`next_round_robin_batch`
    cycle, so no busy session can starve another; a rotating start index only shuffles
    the intra-cycle service order.  Per-session order is preserved (FIFO).
    """

    __slots__ = ("_queues", "_per_session_cap", "_global_cap", "_max_sessions", "_total", "_rotation", "_lock")

    def __init__(self, *, per_session_cap: int, global_cap: int, max_sessions: int) -> None:
        self._per_session_cap = int(per_session_cap)
        self._global_cap = int(global_cap)
        self._max_sessions = int(max_sessions)
        self._queues: "OrderedDict[SessionRef, deque]" = OrderedDict()
        self._total = 0
        self._rotation = 0
        self._lock = threading.Lock()

    def offer(self, job: ShadowJob, enqueued_monotonic: float) -> OfferStatus:
        with self._lock:
            if self._total >= self._global_cap:
                return OfferStatus.DROPPED_GLOBAL_FULL
            dq = self._queues.get(job.session_ref)
            if dq is None:
                if len(self._queues) >= self._max_sessions:
                    return OfferStatus.DROPPED_MAX_SESSIONS
                dq = deque()
                self._queues[job.session_ref] = dq
            if len(dq) >= self._per_session_cap:
                if not dq:
                    del self._queues[job.session_ref]
                return OfferStatus.DROPPED_SESSION_FULL
            dq.append((enqueued_monotonic, job))
            self._total += 1
            return OfferStatus.ACCEPTED

    def next_round_robin_batch(self) -> tuple:
        with self._lock:
            if not self._queues:
                return ()
            keys = list(self._queues.keys())
            count = len(keys)
            start = self._rotation % count
            ordered = keys[start:] + keys[:start]
            batch = []
            for key in ordered:
                dq = self._queues.get(key)
                if dq:
                    _, job = dq.popleft()
                    batch.append(job)
                    self._total -= 1
                if not dq:
                    del self._queues[key]
            self._rotation += 1
            return tuple(batch)

    def drain_all(self) -> tuple:
        with self._lock:
            drained = [job for dq in self._queues.values() for _, job in dq]
            self._queues.clear()
            self._total = 0
            return tuple(drained)

    def clear(self) -> None:
        with self._lock:
            self._queues.clear()
            self._total = 0
            self._rotation = 0

    def oldest_age_ms(self, now: float) -> float:
        with self._lock:
            oldest = None
            for dq in self._queues.values():
                for enqueued, _ in dq:
                    if oldest is None or enqueued < oldest:
                        oldest = enqueued
            if oldest is None:
                return 0.0
            return max(0.0, (now - oldest) * 1000.0)

    def fill_ratio(self) -> float:
        with self._lock:
            if self._global_cap <= 0:
                return 0.0
            ratio = self._total / self._global_cap
            return 1.0 if ratio > 1.0 else ratio

    @property
    def total(self) -> int:
        with self._lock:
            return self._total

    @property
    def session_count(self) -> int:
        with self._lock:
            return len(self._queues)

    def is_empty(self) -> bool:
        with self._lock:
            return self._total == 0


# --------------------------------------------------------------------------- #
# Supervisor
# --------------------------------------------------------------------------- #


class ShadowSupervisor:
    """Owns the private executor, the queues, the driver task, and the lifecycle."""

    def __init__(
        self,
        *,
        committer: EffectCommitter,
        ledger: SequenceLedger,
        counters: IsolationCounters,
        registry: TurnRegistry | None = None,
        telemetry_sink: TelemetrySink | None = None,
        profile_selector: ProfileSelector | None = None,
        comparator=_default_compare,
        plugin_instance_id: str = "plugin",
        monotonic=time.monotonic,
        compute=orchestrate,
        load_snapshot_provider=None,
        repository_admission_provider=None,
        per_session_cap: int = MAX_PER_SESSION_QUEUE,
        global_cap: int = MAX_GLOBAL_QUEUE,
        max_sessions: int = MAX_ACTIVE_SESSIONS,
        job_timeout_s: float | None = 30.0,
        drain_timeout_s: float = 5.0,
        shutdown_step_timeout_s: float = 5.0,
    ) -> None:
        self._committer = committer
        self._ledger = ledger
        self._counters = counters
        self._registry = registry
        self._telemetry_sink = telemetry_sink
        self._profile_selector = profile_selector if profile_selector is not None else ProfileSelector()
        self._comparator = comparator
        self._plugin_instance_id = plugin_instance_id
        self._monotonic = monotonic
        self._compute = compute
        self._load_snapshot_provider = load_snapshot_provider
        self._repository_admission_provider = repository_admission_provider
        self._job_timeout_s = job_timeout_s
        self._drain_timeout_s = float(drain_timeout_s)
        self._shutdown_step_timeout_s = max(0.0, float(shutdown_step_timeout_s))

        self._queues = SessionQueues(
            per_session_cap=per_session_cap, global_cap=global_cap, max_sessions=max_sessions
        )

        # Lifecycle state.
        self._initialized = False
        self._shutdown_started = False
        self._accepting = False
        self._running = False
        self._committer_admission_open = False
        self._epoch: int | None = None

        # Async plumbing (created at initialize on the running loop).
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread_ident: int | None = None
        self._executor: ThreadPoolExecutor | None = None
        self._wake: asyncio.Event | None = None
        self._idle: asyncio.Event | None = None
        self._all_done: asyncio.Event | None = None
        self._sidecar_park: asyncio.Event | None = None
        self._driver_task: asyncio.Task | None = None
        self._aux_tasks: set = set()
        self._tracked: set = set()
        self._inflight = None
        # Only an in-flight repository commit may outlive driver cancellation and
        # still publish.  Its done-fence owns finalization/accounting until the real
        # outcome is known; every other cancelled phase is read/pure compute and can
        # be retired fail-closed immediately. ``_commit_cancellation_job`` is the
        # one-turn handoff marker consumed by ``_pump``; ``_orphan_commit_job`` stays
        # live until the executor reports the true repository result.
        self._commit_cancellation_job: ShadowJob | None = None
        self._orphan_commit_job: ShadowJob | None = None
        # The orphan completion callback runs on the private worker so it can still
        # reconcile a late repository result after the host loop has closed.  Protect
        # its ownership handoff and outstanding counter from the loop/worker race.
        self._completion_lock = threading.Lock()

        self._outstanding = 0
        self._p95_samples: deque = deque(maxlen=64)
        self._shutdown_trace: list = []
        self._shutdown_failures: deque = deque(maxlen=16)
        self._shutdown_helpers: set = set()

    # -- introspection -------------------------------------------------------

    @property
    def epoch(self) -> int | None:
        return self._epoch

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    def shutdown_trace(self) -> tuple:
        return tuple(self._shutdown_trace)

    @property
    def shutdown_failures(self) -> tuple:
        return tuple(self._shutdown_failures)

    @property
    def queued_count(self) -> int:
        return self._queues.total

    @property
    def outstanding(self) -> int:
        with self._completion_lock:
            return self._outstanding

    @property
    def tracked_task_count(self) -> int:
        return len(self._tracked)

    @staticmethod
    def worker_thread_names() -> tuple:
        return tuple(t.name for t in threading.enumerate() if t.name.startswith(THREAD_NAME_PREFIX))

    # -- lifecycle -----------------------------------------------------------

    async def initialize(self, *, epoch: int | None = None) -> None:
        if self._initialized:
            return
        self._loop = asyncio.get_running_loop()
        self._loop_thread_ident = threading.get_ident()
        self._epoch = self._committer.acquire_epoch() if epoch is None else int(epoch)
        self._executor = ThreadPoolExecutor(
            max_workers=WORKER_COUNT, thread_name_prefix=THREAD_NAME_PREFIX
        )
        self._wake = asyncio.Event()
        self._idle = asyncio.Event()
        self._idle.set()
        self._all_done = asyncio.Event()
        self._all_done.set()
        self._sidecar_park = asyncio.Event()
        self._shutdown_trace = []
        self._shutdown_failures.clear()
        self._shutdown_started = False
        self._accepting = True
        self._running = True
        self._committer_admission_open = True
        with self._completion_lock:
            self._outstanding = 0
            self._orphan_commit_job = None
        self._commit_cancellation_job = None

        self._driver_task = self._loop.create_task(self._driver())
        self._tracked.add(self._driver_task)
        replay_task = self._loop.create_task(self._idle_replay_sidecar())
        metric_task = self._loop.create_task(self._metric_sidecar())
        self._aux_tasks = {replay_task, metric_task}
        self._tracked.add(replay_task)
        self._tracked.add(metric_task)
        self._initialized = True

    def offer(self, job: ShadowJob) -> OfferResult:
        """Bounded, non-blocking, non-awaiting admission (design 14.2 event-loop path)."""

        if type(job) is not ShadowJob:
            raise TypeError("offer requires an immutable ShadowJob")
        if not self._accepting:
            return OfferResult(OfferStatus.DROPPED_ADMISSION_CLOSED)
        now = self._monotonic()
        status = self._queues.offer(job, now)
        if status is OfferStatus.ACCEPTED:
            with self._completion_lock:
                self._outstanding += 1
            if self._all_done is not None:
                self._all_done.clear()
            if self._registry is not None and job.handle is not None:
                self._registry.mark_enqueued(handle=job.handle, now=now)
            else:
                self._ledger.mark_accepted(job.session_ref, job.sequence)
            self._signal_wake()
        else:
            # A rejected offer is not backpressure: record the drop and move on.
            self._ledger.mark_dropped(job.session_ref, job.sequence)
        return OfferResult(status)

    async def join(self) -> None:
        """Wait until every accepted job has been processed (test/support helper)."""

        if not self._initialized or self._all_done is None:
            return
        await self._all_done.wait()

    async def terminate(self) -> None:
        """Idempotent, exactly-ordered teardown (plan Task 12)."""

        if not self._initialized:
            return
        if self._shutdown_started:
            return
        self._shutdown_started = True
        trace = self._shutdown_trace

        # 1. stop admission / detach from the event-loop path.
        self._accepting = False
        self._running = False
        trace.append("stop_admission_detach")

        # 2. mark every still-queued (unstarted) job dropped; never processed.
        for job in self._queues.drain_all():
            self._ledger.mark_dropped(job.session_ref, job.sequence)
            self._finalize(job, dropped=True)
            self._release_outstanding()
        trace.append("mark_unqueued_dropped")

        # 3. cancel the replay / metric sidecars.
        for task in self._aux_tasks:
            task.cancel()
        trace.append("cancel_replay_metric")

        # 4. bounded drain: let the single in-flight job finish, bounded by a deadline.
        if self._idle is not None:
            try:
                await asyncio.wait_for(self._idle.wait(), timeout=self._drain_timeout_s)
            except asyncio.TimeoutError:
                pass
        trace.append("bounded_drain")

        # 5. close committer admission so nothing else publishes.
        self._committer_admission_open = False
        trace.append("close_committer_admission")

        # 6. seal the writer epoch (repository fence: an old epoch can never publish).
        #    ``seal_epoch`` takes the cross-process repo lock and fsyncs, so it is
        #    offloaded for the same reason as step 9: if the bounded drain above timed
        #    out, our own worker still holds that lock, and sealing inline would block
        #    the host loop for the rest of that commit.  It goes to the default
        #    executor rather than the v3 worker on purpose -- the v3 worker may be busy
        #    with exactly the commit we are waiting on, and queueing the safety fence
        #    behind it would delay the fence instead of the loop.  The step order is
        #    unchanged: the await still completes before "seal_epoch" is traced.
        if self._epoch is not None:
            await self._bounded_shutdown_step(
                "seal_epoch",
                self._committer.seal_epoch,
                self._epoch,
            )
        trace.append("seal_epoch")

        # 7. cancel any leftover tracked tasks (the driver and residue).
        for task in tuple(self._tracked):
            if not task.done():
                task.cancel()
        trace.append("cancel_leftovers")

        # 8. gather every tracked task, absorbing cancellation/exceptions.
        if self._tracked:
            await asyncio.gather(*self._tracked, return_exceptions=True)
        trace.append("gather_tracked_tasks")

        # 9. ask the private executor to stop, bounded like every blocking teardown
        #    step.  A running OS thread cannot be cancelled; if this bound expires,
        #    its commit completion fence reconciles directly on that worker later.
        #    ``shutdown(wait=True)`` joins worker threads, so calling it directly here
        #    would block the whole event loop until an orphaned (timed-out) compute
        #    thread finishes — v2's own teardown runs after ours, so a wedged core
        #    would wedge v2.  Hand the join to a helper thread instead so the loop stays
        #    live while the bounded wait is active.  The helper may outlive this
        #    coroutine after a timeout; correctness therefore cannot depend on the loop
        #    remaining alive until the join finishes.
        if self._executor is not None:
            await self._bounded_shutdown_step(
                "executor_shutdown",
                self._executor.shutdown,
                wait=True,
                cancel_futures=True,
            )
        trace.append("executor_shutdown")

        # 10. clear the supervisor-owned registries.
        self._queues.clear()
        self._tracked.clear()
        self._aux_tasks.clear()
        self._inflight = None
        self._driver_task = None
        self._executor = None
        trace.append("clear_registries")

        self._initialized = False

    async def _bounded_shutdown_step(self, name: str, fn, *args, **kwargs) -> None:
        """Run blocking teardown without letting a wedged OS call hold the host."""

        task = asyncio.create_task(asyncio.to_thread(fn, *args, **kwargs))
        self._shutdown_helpers.add(task)

        def completed(done: asyncio.Task) -> None:
            self._shutdown_helpers.discard(done)
            _discard_future_result(done)

        task.add_done_callback(completed)
        try:
            await asyncio.wait_for(
                asyncio.shield(task),
                timeout=self._shutdown_step_timeout_s,
            )
        except asyncio.TimeoutError:
            self._shutdown_failures.append((name, "TimeoutError"))
        except Exception as exc:  # noqa: BLE001 - teardown must continue fail-closed
            self._shutdown_failures.append((name, type(exc).__name__))

    # -- driver + sidecars ---------------------------------------------------

    async def _driver(self) -> None:
        assert self._wake is not None and self._idle is not None
        while True:
            self._idle.set()
            await self._wake.wait()
            self._wake.clear()
            self._idle.clear()
            if not self._running:
                self._idle.set()
                return
            await self._pump()

    async def _pump(self) -> None:
        while True:
            batch = self._queues.next_round_robin_batch()
            if not batch:
                break
            for job in batch:
                try:
                    await self._process_job(job)
                except asyncio.CancelledError:
                    # A commit cancellation is owned by its orphan fence because the
                    # worker may still publish.  Loads/profile reads/pure compute
                    # cannot publish, so retire those immediately instead of leaking
                    # one accepted job and leaving ``_all_done`` cleared forever.
                    if self._commit_cancellation_job is job:
                        self._commit_cancellation_job = None
                    else:
                        self._contain_shutdown_cancellation(job)
                        self._release_outstanding()
                    raise
                except Exception as exc:  # noqa: BLE001 - one bad shadow job is isolated
                    self._contain_job_failure(job, exc)
                self._release_outstanding()

    async def _idle_replay_sidecar(self) -> None:
        # Read-only idle replay is an observability/calibration sidecar (design 16.3):
        # it never changes decisions or state.  In this build it parks on a never-set
        # event and is cancelled first during shutdown ("cancel replay/metric").
        assert self._sidecar_park is not None
        await self._sidecar_park.wait()

    async def _metric_sidecar(self) -> None:
        # Best-effort telemetry heartbeat; counters are pulled on demand, so this task
        # parks until it is cancelled in the exact shutdown order.
        assert self._sidecar_park is not None
        await self._sidecar_park.wait()

    def _signal_wake(self) -> None:
        if self._loop is None or self._wake is None:
            return
        if threading.get_ident() == self._loop_thread_ident:
            self._wake.set()
        else:  # pragma: no cover - offer is called from the loop thread in practice
            self._loop.call_soon_threadsafe(self._wake.set)

    # -- per-job processing (design 14.2 steps, 14.3 degradation) ------------

    async def _process_job(self, job: ShadowJob) -> None:
        checkpoints: list = []

        # Phase ADMIT: reject stale/duplicate by the committed high-watermark.
        watermarks = self._ledger.status_high_watermarks(job.session_ref)
        if watermarks.committed is not None and job.sequence <= watermarks.committed:
            self._finalize(job, dropped=True)
            self._emit(job, "DROPPED_STALE", dropped=True, timed_out=False, checkpoints=checkpoints)
            return

        if not self._deadline_ok(job, "before_load", checkpoints):
            self._timeout(job, "", 0, checkpoints)
            return

        # Phase LOAD: the CAS base.  The repository read takes a cross-process file
        # lock and reads fsync'd files, so it runs in the v3-private worker, never
        # inline on the host loop.  A load that outruns the job bound is orphaned and
        # the whole invocation is discarded; a read publishes nothing, so an orphan
        # left behind by a timeout is harmless.
        try:
            loaded = await self._offload(
                self._committer.load_state, job.session_ref, timeout=self._job_timeout_s
            )
        except _CoreTimeout:
            self._timeout(job, "", 0, checkpoints)
            return
        if loaded is None:
            self._finalize(job, dropped=True)
            self._emit(job, "DROPPED_NO_BASE", dropped=True, timed_out=False, checkpoints=checkpoints)
            return

        if not self._deadline_ok(job, "before_profile", checkpoints):
            self._timeout(job, "", 0, checkpoints)
            return

        # Phase PROFILE: select and FREEZE one profile before any core stage.
        try:
            snapshot = await self._load_snapshot()
        except _CoreTimeout:
            self._timeout(job, "", 0, checkpoints)
            return
        except Exception:  # noqa: BLE001 - load observation is shadow-only
            self._finalize(job, dropped=True)
            self._emit(
                job,
                "DROPPED_LOAD_ERROR",
                dropped=True,
                timed_out=False,
                checkpoints=checkpoints,
            )
            return
        selection = self._profile_selector.select(snapshot)
        if selection.skip:
            outcome = "REPOSITORY_HARD_STOP" if selection.dropped else "SKIP"
            self._finalize(job, dropped=True)
            self._emit(
                job, outcome, dropped=True, timed_out=False, checkpoints=checkpoints,
                reason=selection.reason, level=selection.level,
            )
            return
        profile = selection.profile  # frozen from here on
        assert profile is not None  # ProfileSelection guarantees this for non-skip results.

        invocation = self._build_invocation(job, loaded.state, profile)

        if not self._deadline_ok(job, "before_compute", checkpoints):
            self._timeout(job, profile.profile_id, selection.level, checkpoints)
            return

        # Phase COMPUTE: pure core in the single private worker; no clock, no callback.
        compute_start = self._monotonic()
        try:
            result = await self._run_core(invocation)
        except _CoreTimeout:
            self._timeout(job, profile.profile_id, selection.level, checkpoints)
            return
        except Exception:  # noqa: BLE001 - every core exception is contained (design 14.3)
            self._finalize(job, dropped=True)
            self._emit(
                job, "DROPPED_CORE_ERROR", dropped=True, timed_out=False, checkpoints=checkpoints,
                profile_id=profile.profile_id, level=selection.level,
            )
            return
        compute_us = max(0.0, (self._monotonic() - compute_start) * 1_000_000.0)

        if not self._deadline_ok(job, "before_commit", checkpoints):
            self._timeout(job, profile.profile_id, selection.level, checkpoints)
            return

        if not result.accepted:
            self._finalize(job, dropped=True)
            self._emit(
                job, "DROPPED_CORE_REJECTED", dropped=True, timed_out=False, checkpoints=checkpoints,
                profile_id=profile.profile_id, level=selection.level,
            )
            return

        # Phase COMPARE (design 14.2 step 8): shadow vs v2 actual behavior.
        self._comparator(result.decision_plan.action, job.actual_action)

        # A closed shutdown fence forbids any further publication.
        if not self._committer_admission_open:
            self._finalize(job, dropped=True)
            self._emit(
                job, "SHUTDOWN_DROPPED", dropped=True, timed_out=False, checkpoints=checkpoints,
                profile_id=profile.profile_id, level=selection.level,
            )
            return

        # Phase COMMIT: one CAS-guarded state+trace journal record.
        command = TurnCommit(
            session_ref=job.session_ref,
            base=loaded.base,
            state_payload=self._state_payload_of(result.effects),
            trace_bytes=result.trace_bytes,
            effects=result.effects,
            turn_id=job.turn_id,
            turn_sequence=job.sequence,
        )
        # The CAS commit fsyncs the journal and takes the cross-process lock, so it
        # too runs in the v3-private worker.  Deliberately NOT bounded by the job
        # timeout: orphaning a commit cannot cancel the thread, so the write could
        # still land while we recorded the turn as dropped -- a torn ledger is worse
        # than a slow one.
        #
        # Be precise about what that costs, because the comment here used to overclaim:
        # the host loop is never blocked (we are awaiting a future), but this await is
        # genuinely UNBOUNDED.  terminate() does not bound it either -- only its step-4
        # drain is deadlined; step 9's ``shutdown(wait=True)`` is a join, not a bound,
        # and main.py awaits terminate() without a wait_for.  A wedged commit therefore
        # wedges v3 shutdown (it can no longer wedge v2's loop, which is the point of
        # this fix).  If the drain deadline expires first, step 7 cancels the driver
        # mid-await -- the write still lands, so ``_commit_offload`` installs an orphan
        # fence that records the real outcome even though this coroutine never resumes.
        outcome = await self._commit_offload(
            command, job, profile.profile_id, selection.level, checkpoints, compute_us
        )
        if outcome.status is CommitStatus.COMMITTED:
            self._p95_samples.append(compute_us / 1000.0)
            self._finalize(job, dropped=False)
            self._emit(
                job, "COMMITTED", dropped=False, timed_out=False, checkpoints=checkpoints,
                profile_id=profile.profile_id, level=selection.level,
                commit_status=outcome.status.name, cas=True,
                stage_timings=(("compute_us", compute_us),),
            )
            return
        if outcome.status is CommitStatus.STALE_EPOCH:
            self._finalize(job, dropped=True)
            self._emit(
                job, "DROPPED_STALE_EPOCH", dropped=True, timed_out=False, checkpoints=checkpoints,
                profile_id=profile.profile_id, level=selection.level,
                commit_status=outcome.status.name,
            )
            return
        self._finalize(job, dropped=True)
        self._emit(
            job, "DROPPED_COMMIT_CONFLICT", dropped=True, timed_out=False, checkpoints=checkpoints,
            profile_id=profile.profile_id, level=selection.level, commit_status=outcome.status.name,
        )

    async def _offload(self, fn, *args, timeout: float | None):
        """Run ``fn`` on the v3-private worker, never on the host event loop.

        Everything that blocks -- the pure core *and* the repository's fsync/flock IO
        -- goes through here, so the single ``sylanne-v3`` worker keeps its
        deliberate global serialization across sessions and the host loop is only
        ever suspended on an await (design 14.2: v3 never adds backpressure to v2).

        ``timeout=None`` awaits to completion.  Otherwise a timeout orphans the
        future (a running thread cannot be cancelled); it is collected by
        ``executor.shutdown(wait=True)`` and its result discarded.
        """

        assert self._loop is not None and self._executor is not None
        future = self._loop.run_in_executor(self._executor, fn, *args)
        self._inflight = future
        try:
            if timeout is None:
                return await future
            done, _pending = await asyncio.wait({future}, timeout=timeout)
            if future not in done:
                future.add_done_callback(_discard_future_result)
                raise _CoreTimeout
            return future.result()
        finally:
            self._inflight = None

    async def _commit_offload(
        self, command, job: ShadowJob, profile_id: str, level: int, checkpoints: list, compute_us: float
    ):
        """Offload the unbounded CAS commit behind a fence that survives our cancellation.

        The problem this solves: the commit is deliberately not bounded by the job
        timeout (orphaning a commit cannot cancel the thread, so a torn ledger is worse
        than a slow one), but ``terminate``'s step-4 drain *is* bounded.  When that drain
        expires with a commit in flight, step 7 cancels the driver task mid-await.  The
        write still lands -- but ``_process_job`` never resumes, so ``_finalize``/
        ``_emit`` never ran: the turn published, yet the ledger said nothing, telemetry
        was empty, and ``outstanding`` stayed at 1 because the CancelledError unwinds
        straight through ``_pump``'s decrement.  The ledger and the disk disagreed about
        a turn that really happened.

        The driver awaits a shielded asyncio wrapper, while the fence is a done-callback
        on the underlying *executor* future.  Driver cancellation therefore leaves the
        wrapper attached to the real result; the concurrent future completes only when
        the worker thread is actually finished and carries the true status.
        ``concurrent.futures`` runs that callback on the worker thread.  It settles the
        thread-safe ledger/registry and bounded telemetry sink there instead of merely
        reposting to the host loop: bounded executor shutdown may return first and the
        host may close its loop before the repository call completes.  An ownership
        marker makes an early normal callback a no-op; the cancellation handler settles
        synchronously if completion won that narrow race.
        """

        assert self._loop is not None and self._executor is not None
        executor_future = self._executor.submit(self._committer.commit_turn, command)
        awaited = asyncio.wrap_future(executor_future, loop=self._loop)
        # Registered AFTER wrap_future, so the wrapper receives the real result first.
        executor_future.add_done_callback(
            lambda done_future: self._complete_orphan_fence(
                done_future, job, profile_id, level, checkpoints, compute_us
            )
        )
        self._inflight = awaited
        try:
            # Shield keeps the wrapper attached to the real concurrent-future result.
            # Driver cancellation is handled below without converting a completed
            # commit into a cancelled wrapper and without guessing publication status.
            return await asyncio.shield(awaited)
        except asyncio.CancelledError:
            self._commit_cancellation_job = job
            with self._completion_lock:
                self._orphan_commit_job = job
            # The executor may have finished just before cancellation was delivered,
            # in which case its callback already ran while no orphan marker existed.
            # Settle synchronously on the loop so that narrow race cannot lose the
            # real outcome; a later worker callback becomes an identity-guarded no-op.
            if executor_future.done():
                self._settle_orphaned_commit(
                    executor_future,
                    job,
                    profile_id,
                    level,
                    checkpoints,
                    compute_us,
                )
            raise
        finally:
            self._inflight = None

    def _complete_orphan_fence(
        self, executor_future, job, profile_id, level, checkpoints, compute_us
    ) -> None:
        """Runs on the v3 worker and settles without depending on host-loop liveness."""

        self._settle_orphaned_commit(
            executor_future,
            job,
            profile_id,
            level,
            checkpoints,
            compute_us,
        )

    def _settle_orphaned_commit(
        self, executor_future, job, profile_id, level, checkpoints, compute_us
    ) -> None:
        """Record a commit whose supervising await was cut off.

        Fires only after ``_commit_offload`` marks this job orphaned, which is exactly
        "the driver was cancelled out of the await and will never record this outcome".
        When the await is intact the driver owns the outcome and this is a no-op, so the
        two paths can never both finalize the same job.  The ownership check is locked
        because either the loop's cancellation path or the worker callback may win.
        """

        with self._completion_lock:
            if self._orphan_commit_job is not job:
                return  # the awaiting driver resumed normally and owns this outcome
            self._orphan_commit_job = None

        if executor_future.cancelled() or executor_future.exception() is not None:
            # Nothing reached the repository: either the executor shutdown cancelled a
            # commit that had not started, or commit_turn raised. Reporting the fence as
            # the reason publication did not happen is accurate here (unlike the
            # COMMITTED case, where SHUTDOWN_DROPPED would be a lie).
            self._finalize(job, dropped=True)
            self._emit(
                job, "SHUTDOWN_DROPPED", dropped=True, timed_out=False, checkpoints=checkpoints,
                profile_id=profile_id, level=level,
            )
            self._release_outstanding()
            return

        outcome = executor_future.result()
        if outcome.status is CommitStatus.COMMITTED:
            # The write is on disk. Say so, and mark the ledger committed to match it.
            self._finalize(job, dropped=False)
            self._emit(
                job, "COMMITTED_ORPHANED", dropped=False, timed_out=False, checkpoints=checkpoints,
                profile_id=profile_id, level=level, commit_status=outcome.status.name, cas=True,
                stage_timings=(("compute_us", compute_us),),
            )
        elif outcome.status is CommitStatus.STALE_EPOCH:
            self._finalize(job, dropped=True)
            self._emit(
                job, "DROPPED_STALE_EPOCH", dropped=True, timed_out=False, checkpoints=checkpoints,
                profile_id=profile_id, level=level, commit_status=outcome.status.name,
            )
        else:
            self._finalize(job, dropped=True)
            self._emit(
                job, "DROPPED_COMMIT_CONFLICT", dropped=True, timed_out=False, checkpoints=checkpoints,
                profile_id=profile_id, level=level, commit_status=outcome.status.name,
            )
        self._release_outstanding()

    def _release_outstanding(self) -> None:
        """Retire exactly one accepted job from the outstanding count."""

        with self._completion_lock:
            if self._outstanding > 0:
                self._outstanding -= 1
            all_done = self._outstanding == 0
        if not all_done or self._all_done is None:
            return
        if threading.get_ident() == self._loop_thread_ident:
            self._all_done.set()
            return
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(self._all_done.set)
        except RuntimeError:  # the host loop closed between the check and the post
            pass

    def _contain_job_failure(self, job: ShadowJob, exc: Exception) -> None:
        """Fail one job closed without allowing persistence/telemetry to kill the driver."""

        try:
            self._finalize(job, dropped=True)
        except Exception:  # noqa: BLE001 - ledger/registry failure cannot escape the shadow
            pass
        try:
            self._emit(
                job,
                "DROPPED_RUNTIME_ERROR",
                dropped=True,
                timed_out=False,
                checkpoints=[],
                reason=type(exc).__name__,
            )
        except Exception:  # noqa: BLE001 - observability is best-effort, driver liveness is not
            pass

    def _contain_shutdown_cancellation(self, job: ShadowJob) -> None:
        """Retire a cancelled non-commit phase without swallowing cancellation."""

        try:
            self._finalize(job, dropped=True)
        except Exception:  # noqa: BLE001 - teardown accounting remains fail-isolated
            pass
        try:
            self._emit(
                job,
                "SHUTDOWN_DROPPED",
                dropped=True,
                timed_out=False,
                checkpoints=[],
            )
        except Exception:  # noqa: BLE001 - telemetry cannot block teardown
            pass

    async def _run_core(self, invocation: CoreInvocation):
        return await self._offload(self._compute, invocation, timeout=self._job_timeout_s)

    # -- helpers -------------------------------------------------------------

    def _deadline_ok(self, job: ShadowJob, phase: str, checkpoints: list) -> bool:
        checkpoints.append(phase)
        return self._monotonic() <= job.deadline_monotonic

    def _timeout(self, job: ShadowJob, profile_id: str, level: int, checkpoints: list) -> None:
        # Discard the whole partial invocation: no state, no trace committed.
        self._finalize(job, dropped=True)
        self._emit(
            job, "TIMEOUT", dropped=True, timed_out=True, checkpoints=checkpoints,
            profile_id=profile_id, level=level,
        )

    async def _load_snapshot(self) -> LoadSnapshotV1:
        if self._load_snapshot_provider is not None:
            snapshot = await self._offload(
                self._load_snapshot_provider,
                timeout=self._job_timeout_s,
            )
            if type(snapshot) is not LoadSnapshotV1:
                raise TypeError("load_snapshot_provider must return a LoadSnapshotV1")
            return snapshot
        admission = RepositoryAdmissionState.OPEN
        if self._repository_admission_provider is not None:
            admission = await self._offload(
                self._repository_admission_provider,
                timeout=self._job_timeout_s,
            )
            if type(admission) is not RepositoryAdmissionState:
                raise TypeError(
                    "repository_admission_provider must return RepositoryAdmissionState"
                )
        now = self._monotonic()
        return LoadSnapshotV1(
            global_queue_fill=self._queues.fill_ratio(),
            oldest_job_age_ms=self._queues.oldest_age_ms(now),
            committed_compute_p95_ms=self._p95_ms(),
            repository_admission=admission,
        )

    def _p95_ms(self) -> float:
        if not self._p95_samples:
            return 0.0
        ordered = sorted(self._p95_samples)
        index = int(0.95 * (len(ordered) - 1) + 0.5)
        if index >= len(ordered):
            index = len(ordered) - 1
        return float(ordered[index])

    def _build_invocation(self, job: ShadowJob, base_state, profile) -> CoreInvocation:
        seed = self._derive_seed(job, profile)
        envelope = TurnEnvelope(
            turn_key=job.turn_key,
            turn_id=job.turn_id,
            sequence=job.sequence,
            compute_profile=profile,
            deterministic_seed=seed,
            observation=job.observation,
            context=job.context,
        )
        core_action = to_core_action(job.actual_action)
        projected = None if core_action is None else (core_action, job.quality_score)
        return CoreInvocation(
            envelope=envelope,
            base_state=base_state,
            projected_actual_outcome=projected,
            reaction_facts=job.reaction_facts,
        )

    @staticmethod
    def _derive_seed(job: ShadowJob, profile) -> bytes:
        digest = hashlib.sha256()
        digest.update(b"SYL3-ENVELOPE-SEED-v1\x00")
        digest.update(job.turn_id.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(str(job.sequence.writer_epoch).encode("ascii"))
        digest.update(b"\x00")
        digest.update(str(job.sequence.local_sequence).encode("ascii"))
        digest.update(b"\x00")
        digest.update(canonical_sha256(profile).encode("ascii"))
        digest.update(b"\x00")
        digest.update(canonical_sha256(job.session_ref).encode("ascii"))
        digest.update(b"\x00")
        digest.update(job.context.value.encode("ascii"))
        return digest.digest()[:16]

    @staticmethod
    def _state_payload_of(effects) -> bytes:
        for effect in effects.effects:
            if type(effect) is V3StateEffect:
                return effect.payload
        raise ValueError("core effect bundle is missing its state effect")

    def _finalize(self, job: ShadowJob, *, dropped: bool) -> None:
        now = self._monotonic()
        if self._registry is not None and job.handle is not None:
            if self._registry.finalize(handle=job.handle, now=now, dropped=dropped):
                return
        self._ledger_finalize(job, dropped)

    def _ledger_finalize(self, job: ShadowJob, dropped: bool) -> None:
        if dropped:
            self._ledger.mark_dropped(job.session_ref, job.sequence)
        else:
            self._ledger.mark_committed(job.session_ref, job.sequence)

    def _emit(
        self,
        job: ShadowJob,
        outcome: str,
        *,
        dropped: bool,
        timed_out: bool,
        checkpoints: list,
        profile_id: str = "",
        reason: str = "",
        level: int = 0,
        commit_status: str = "",
        cas: bool = False,
        stage_timings: tuple = (),
    ) -> None:
        if self._telemetry_sink is None:
            return
        if not reason and profile_id:
            reason = "NOMINAL" if level == 0 else "LOAD_PRESSURE"
        telemetry = RuntimeTelemetry(
            turn_id=job.turn_id,
            session_key_id=job.session_ref.key_id,
            writer_epoch=self._epoch if self._epoch is not None else job.sequence.writer_epoch,
            plugin_instance_id=self._plugin_instance_id,
            outcome=outcome,
            profile_id=profile_id,
            profile_selection_reason=reason,
            load_level=level,
            queue_accepted=True,
            dropped=dropped,
            timed_out=timed_out,
            commit_status=commit_status,
            cas_committed=cas,
            retry_count=0,
            load_fill=self._queues.fill_ratio(),
            stage_timings_us=stage_timings,
            deadline_checkpoints=tuple(checkpoints),
        )
        self._telemetry_sink.record(telemetry)


def _discard_future_result(future: _ResultFuture) -> None:
    """Retrieve (and drop) a completed future's ordinary failure to avoid warnings.

    Both asyncio and concurrent futures expose this structural surface.  A genuinely
    cancelled future is already accounted for by its owner and needs no retrieval;
    an ``asyncio.CancelledError`` carried as a result payload is deliberately *not*
    swallowed because cancellation must keep its control-flow meaning.
    """

    if future.cancelled():
        return
    try:
        future.result()
    except Exception:  # noqa: BLE001 - ordinary failed orphans are intentionally ignored
        pass


__all__ = [
    "SHUTDOWN_ORDER",
    "THREAD_NAME_PREFIX",
    "OfferResult",
    "OfferStatus",
    "SessionQueues",
    "ShadowJob",
    "ShadowSupervisor",
]
