"""Host-facing assembly of the v3 shadow bridge (plan Task 12; wired by Task 13).

:class:`V3ShadowRuntime` owns the whole bridge object graph — the
:class:`EffectCommitter`, the :class:`MigrationCoordinator`, the
:class:`SequenceLedger`, the :class:`TurnRegistry`, the :class:`IsolationCounters`,
the :class:`TelemetrySink`, the :class:`ProfileSelector`, and the
:class:`ShadowSupervisor` — behind a small lifecycle surface the plugin drives:

* ``initialize()`` acquires the writer epoch **before** the private worker starts and
  fail-closes only v3;
* ``offer_response(...)`` performs the immutable capture-claim and a single
  non-blocking bounded offer on the event-loop path;
* ``terminate()`` runs the exact ordered supervisor teardown and does not return
  until every v3 worker thread has exited.

The runtime never places v3 futures in ``plugin._background_tasks`` and never mutates
v2 reply/prompt/history/memory/body state.  Task 13 supplies the real host facts; this
module only owns the ownership boundary and the deterministic wiring.
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from pathlib import Path
from typing import Any, Coroutine

from sylanne_alpha.scoped_engine_persistence import ScopedEnginePersistence
from sylanne_alpha.scope_repository import ScopedPersistenceGateway
from sylanne_alpha.v2core.shadow_snapshot import V2SeedSnapshotV1
from sylanne_alpha.v3bridge.actual_action import ActualAction
from sylanne_alpha.v3bridge.effect_committer import EffectCommitter
from sylanne_alpha.v3bridge.limits import (
    MAX_ACTIVE_SESSIONS,
    MAX_GLOBAL_QUEUE,
    MAX_PER_SESSION_QUEUE,
    PLUGIN_DATA_CAP_BYTES,
    effective_v3_budget,
)
from sylanne_alpha.v3bridge.migration_coordinator import (
    MigrationCoordinator,
    MigrationOutcome,
    RecoveryOutcome,
)
from sylanne_alpha.v3bridge.models import RepositoryAdmissionState
from sylanne_alpha.v3bridge.profile_selector import ProfileSelector
from sylanne_alpha.v3bridge.runtime_telemetry import IsolationCounters, TelemetrySink
from sylanne_alpha.v3bridge.shadow_supervisor import (
    OfferResult,
    OfferStatus,
    ShadowJob,
    ShadowSupervisor,
)
from sylanne_alpha.v3bridge.turn_registry import SequenceLedger, TurnHandle, TurnRegistry
from sylanne_alpha.v3core.contracts import ReactionFacts, SessionRef, TurnContextClass, TurnSequence
from sylanne_alpha.v3core.orchestrator import orchestrate


DEFAULT_SHADOW_DEADLINE_MS = 250.0


class ScopedV3ShadowState:
    """The scope-v1 state seam for one V3 shadow component.

    This intentionally has no filesystem root, raw session reference, or
    fallback selector.  The legacy journal runtime remains an explicit separate
    construction path until main wiring routes V3 shadow snapshots through this
    capability.
    """

    def __init__(self, persistence: ScopedPersistenceGateway) -> None:
        self._engine = ScopedEnginePersistence(persistence)

    @property
    def persistence(self) -> ScopedPersistenceGateway:
        return self._engine.persistence

    def load(self) -> dict[str, object] | None:
        snapshot = self._engine.load_v3_shadow()
        return None if snapshot is None else snapshot.payload

    def save(self, payload: object) -> int:
        return self._engine.save_v3_shadow(payload)

    def save_delayed(self, payload: object) -> Coroutine[Any, Any, bool]:
        return self._engine.save_v3_shadow_delayed(payload)

    def schedule_save(self, payload: object, *, delay_seconds: float = 0.0) -> asyncio.Task[bool]:
        return self._engine.schedule_v3_shadow_save(payload, delay_seconds=delay_seconds)


def _tree_usage_bytes(root: Path, *, excluded: Path) -> int:
    """Measure regular files below ``root`` without following links."""

    if not root.exists():
        return 0
    excluded_key = os.path.normcase(os.path.abspath(os.fspath(excluded)))
    total = 0
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                entry_key = os.path.normcase(os.path.abspath(entry.path))
                if entry_key == excluded_key:
                    continue
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                except FileNotFoundError:
                    continue
    return total


class V3ShadowRuntime:
    """The single object the plugin owns for the isolated grey shadow lifecycle."""

    def __init__(
        self,
        *,
        root: str | os.PathLike[str],
        plugin_instance_id: str,
        correlation_secret: bytes,
        telemetry_capacity: int = 256,
        monotonic=time.monotonic,
        compute=orchestrate,
        load_snapshot_provider=None,
        plugin_data_root: str | os.PathLike[str] | None = None,
        non_v3_bytes: int | None = None,
        plugin_cap_bytes: int = PLUGIN_DATA_CAP_BYTES,
        default_deadline_ms: float = DEFAULT_SHADOW_DEADLINE_MS,
        per_session_cap: int = MAX_PER_SESSION_QUEUE,
        global_cap: int = MAX_GLOBAL_QUEUE,
        max_sessions: int = MAX_ACTIVE_SESSIONS,
        job_timeout_s: float | None = 30.0,
        drain_timeout_s: float = 5.0,
        shutdown_step_timeout_s: float = 5.0,
        persistence: ScopedPersistenceGateway | None = None,
    ) -> None:
        self._plugin_instance_id = plugin_instance_id
        self._correlation_secret = correlation_secret
        self._monotonic = monotonic
        self._compute = compute
        self._load_snapshot_provider = load_snapshot_provider
        self._default_deadline_ms = float(default_deadline_ms)
        self._per_session_cap = per_session_cap
        self._global_cap = global_cap
        self._max_sessions = max_sessions
        self._job_timeout_s = job_timeout_s
        self._drain_timeout_s = drain_timeout_s
        self._shutdown_step_timeout_s = shutdown_step_timeout_s
        self._scoped_shadow_state = (
            None if persistence is None else ScopedV3ShadowState(persistence)
        )
        self._restored_scoped_shadow = (
            None if self._scoped_shadow_state is None else self._scoped_shadow_state.load()
        )

        repository_root = Path(os.fspath(root))
        if plugin_data_root is not None and non_v3_bytes is not None:
            raise ValueError("pass plugin_data_root or non_v3_bytes, not both")
        if non_v3_bytes is None:
            non_v3_bytes = (
                _tree_usage_bytes(Path(os.fspath(plugin_data_root)), excluded=repository_root)
                if plugin_data_root is not None
                else 0
            )
        self._repository_budget = effective_v3_budget(non_v3_bytes, plugin_cap_bytes)
        self.committer = EffectCommitter.open(
            repository_root,
            hard_limit_bytes=self._repository_budget.hard_bytes,
        )
        self.coordinator = MigrationCoordinator(self.committer)
        self.ledger = SequenceLedger()
        self.counters = IsolationCounters()
        self.telemetry = TelemetrySink(capacity=telemetry_capacity)
        self.profile_selector = ProfileSelector()
        self._migration_lock = threading.Lock()

        self.registry: TurnRegistry | None = None
        self.supervisor: ShadowSupervisor | None = None
        self._epoch: int | None = None

    @property
    def scoped_persistence(self) -> ScopedPersistenceGateway | None:
        """Return the frozen V3 scope capability when this runtime was scoped."""

        state = self._scoped_shadow_state
        return None if state is None else state.persistence

    @property
    def restored_scoped_shadow(self) -> dict[str, object] | None:
        """Expose the construction-time V3 snapshot without a raw session lookup."""

        snapshot = self._restored_scoped_shadow
        return None if snapshot is None else dict(snapshot)

    def save_scoped_shadow(self, payload: object) -> int:
        """CAS-write a V3 shadow snapshot through the captured gateway only."""

        state = self._scoped_shadow_state
        if state is None:
            raise ValueError("scoped persistence is not configured")
        generation = state.save(payload)
        restored = state.load()
        self._restored_scoped_shadow = restored
        return generation

    def schedule_scoped_shadow_save(
        self,
        payload: object,
        *,
        delay_seconds: float = 0.0,
    ) -> asyncio.Task[bool]:
        """Capture a delayed V3 component write; stale scope work is discarded."""

        state = self._scoped_shadow_state
        if state is None:
            raise ValueError("scoped persistence is not configured")
        return state.schedule_save(payload, delay_seconds=delay_seconds)

    # -- lifecycle -----------------------------------------------------------

    @property
    def epoch(self) -> int | None:
        return self._epoch

    @property
    def initialized(self) -> bool:
        return self.supervisor is not None and self.supervisor.initialized

    async def initialize(self) -> None:
        if self.initialized:
            return
        # Acquire the writer epoch BEFORE the worker starts; fail-close v3 only.
        self._epoch = await asyncio.to_thread(self.committer.acquire_epoch)
        self.registry = TurnRegistry(
            plugin_instance_id=self._plugin_instance_id,
            correlation_secret=self._correlation_secret,
            writer_epoch=self._epoch,
            sequence_ledger=self.ledger,
        )
        self.supervisor = ShadowSupervisor(
            committer=self.committer,
            ledger=self.ledger,
            counters=self.counters,
            registry=self.registry,
            telemetry_sink=self.telemetry,
            profile_selector=self.profile_selector,
            plugin_instance_id=self._plugin_instance_id,
            monotonic=self._monotonic,
            compute=self._compute,
            load_snapshot_provider=self._load_snapshot_provider,
            repository_admission_provider=(
                None
                if self._load_snapshot_provider is not None
                else self._repository_admission
            ),
            per_session_cap=self._per_session_cap,
            global_cap=self._global_cap,
            max_sessions=self._max_sessions,
            job_timeout_s=self._job_timeout_s,
            drain_timeout_s=self._drain_timeout_s,
            shutdown_step_timeout_s=self._shutdown_step_timeout_s,
        )
        await self.supervisor.initialize(epoch=self._epoch)

    async def terminate(self) -> None:
        if self.supervisor is not None:
            await self.supervisor.terminate()

    async def join(self) -> None:
        if self.supervisor is not None:
            await self.supervisor.join()

    # -- migration -----------------------------------------------------------

    def _repository_admission(self) -> RepositoryAdmissionState:
        usage = self.committer.repository.usage_bytes()
        budget = self._repository_budget
        if not budget.admission_enabled or usage >= budget.hard_bytes:
            return RepositoryAdmissionState.HARD_STOP
        if usage >= budget.high_bytes:
            return RepositoryAdmissionState.HIGH_WATERMARK
        return RepositoryAdmissionState.OPEN

    def recover(
        self,
        session_ref: SessionRef,
        *,
        source_digest: str,
        session_generation: int = 0,
        writer_epoch: int | None = None,
    ) -> RecoveryOutcome:
        epoch = self._epoch if writer_epoch is None else int(writer_epoch)
        if epoch is None:
            raise RuntimeError("v3 runtime is not initialized")
        return self.coordinator.recover(
            session_ref,
            writer_epoch=epoch,
            session_generation=session_generation,
            source_digest=source_digest,
        )

    def migrate(
        self,
        session_ref: SessionRef,
        *,
        source_digest: str,
        session_generation: int = 0,
        writer_epoch: int | None = None,
        v3_migration_lock: object | None = None,
        seed_snapshot: V2SeedSnapshotV1 | None = None,
        freeze_v2_seed: object = None,
    ) -> MigrationOutcome:
        """One-time v2 seeding for a session (design 15.2).

        Production migration uses the already-acquired supervisor epoch. Sequence 1 is
        reserved for the genesis commit before live capture, so the first turn starts
        at 2 without acquiring a newer epoch that would fence the running worker.
        """

        if writer_epoch is None:
            epoch = self._epoch
            if epoch is None:
                epoch = self.committer.acquire_epoch()
        else:
            epoch = int(writer_epoch)
        outcome = self.coordinator.migrate(
            session_ref,
            writer_epoch=epoch,
            session_generation=session_generation,
            source_digest=source_digest,
            v3_migration_lock=self._migration_lock
            if v3_migration_lock is None
            else v3_migration_lock,
            seed_snapshot=seed_snapshot,
            freeze_v2_seed=freeze_v2_seed,
        )
        high_watermark = self.committer.pointer_high_watermark(session_ref)
        if high_watermark is not None:
            self.ledger.resume_committed(session_ref=session_ref, sequence=high_watermark)
        return outcome

    def reserve_migration_sequence(self, session_ref: SessionRef) -> TurnSequence:
        """Reserve the current epoch's genesis slot before first live capture."""

        if self._epoch is None:
            raise RuntimeError("v3 runtime is not initialized")
        sequence = TurnSequence(self._epoch, 1)
        if not self.ledger.reserve(session_ref=session_ref, sequence=sequence):
            raise RuntimeError("v3 sequence ledger could not reserve migration slot")
        return sequence

    def complete_migration_sequence(self, session_ref: SessionRef) -> bool:
        """Publish the in-memory migration barrier after durable base validation."""

        if self._epoch is None:
            return False
        return self.ledger.resume_committed(
            session_ref=session_ref,
            sequence=TurnSequence(self._epoch, 1),
        )

    # -- capture + offer (event-loop path) -----------------------------------

    def capture_request(
        self,
        *,
        session_ref: SessionRef,
        bridge_request_nonce: str,
        request_attempt: int,
        platform_id: object,
        unified_msg_origin: object,
        message_id: object,
        now: float | None = None,
    ) -> TurnHandle | None:
        assert self.registry is not None
        return self.registry.capture_request(
            session_ref=session_ref,
            bridge_request_nonce=bridge_request_nonce,
            request_attempt=request_attempt,
            platform_id=platform_id,
            unified_msg_origin=unified_msg_origin,
            message_id=message_id,
            now=self._monotonic() if now is None else now,
        )

    def offer_response(
        self,
        *,
        handle: TurnHandle,
        context: TurnContextClass,
        observation: object,
        actual_action: ActualAction,
        quality_score: float | None,
        reaction_facts: ReactionFacts | None = None,
        platform_id: object,
        unified_msg_origin: object,
        message_id: object,
        deadline_ms: float | None = None,
        now: float | None = None,
    ) -> OfferResult:
        """Claim the terminal, freeze a :class:`ShadowJob`, and offer it (non-blocking)."""

        assert self.registry is not None and self.supervisor is not None
        moment = self._monotonic() if now is None else now
        claimed = self.registry.claim_response(
            handle=handle,
            platform_id=platform_id,
            unified_msg_origin=unified_msg_origin,
            message_id=message_id,
            now=moment,
        )
        if not claimed:
            return OfferResult(OfferStatus.DROPPED_ADMISSION_CLOSED)
        ms = self._default_deadline_ms if deadline_ms is None else float(deadline_ms)
        job = ShadowJob(
            turn_key=handle.turn_key,
            turn_id=handle.turn_id,
            sequence=handle.sequence,
            session_ref=handle.turn_key.session_ref,
            context=context,
            observation=observation,
            actual_action=actual_action,
            quality_score=quality_score,
            reaction_facts=reaction_facts,
            deadline_monotonic=moment + ms / 1000.0,
            handle=handle,
        )
        return self.supervisor.offer(job)


__all__ = [
    "DEFAULT_SHADOW_DEADLINE_MS",
    "V3ShadowRuntime",
]
