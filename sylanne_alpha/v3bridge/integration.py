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

import time

from sylanne_alpha.v3bridge.actual_action import ActualAction
from sylanne_alpha.v3bridge.effect_committer import EffectCommitter
from sylanne_alpha.v3bridge.migration_coordinator import MigrationCoordinator, MigrationOutcome
from sylanne_alpha.v3bridge.profile_selector import ProfileSelector
from sylanne_alpha.v3bridge.runtime_telemetry import IsolationCounters, TelemetrySink
from sylanne_alpha.v3bridge.shadow_supervisor import (
    OfferResult,
    OfferStatus,
    ShadowJob,
    ShadowSupervisor,
)
from sylanne_alpha.v3bridge.turn_registry import SequenceLedger, TurnHandle, TurnRegistry
from sylanne_alpha.v3core.contracts import SessionRef, TurnContextClass
from sylanne_alpha.v3core.orchestrator import orchestrate


DEFAULT_SHADOW_DEADLINE_MS = 250.0


class V3ShadowRuntime:
    """The single object the plugin owns for the isolated grey shadow lifecycle."""

    def __init__(
        self,
        *,
        root: object,
        plugin_instance_id: str,
        correlation_secret: bytes,
        telemetry_capacity: int = 256,
        monotonic=time.monotonic,
        compute=orchestrate,
        load_snapshot_provider=None,
        default_deadline_ms: float = DEFAULT_SHADOW_DEADLINE_MS,
        **supervisor_kwargs: object,
    ) -> None:
        self._plugin_instance_id = plugin_instance_id
        self._correlation_secret = correlation_secret
        self._monotonic = monotonic
        self._compute = compute
        self._load_snapshot_provider = load_snapshot_provider
        self._default_deadline_ms = float(default_deadline_ms)
        self._supervisor_kwargs = supervisor_kwargs

        self.committer = EffectCommitter.open(root)
        self.coordinator = MigrationCoordinator(self.committer)
        self.ledger = SequenceLedger()
        self.counters = IsolationCounters()
        self.telemetry = TelemetrySink(capacity=telemetry_capacity)
        self.profile_selector = ProfileSelector()

        self.registry: TurnRegistry | None = None
        self.supervisor: ShadowSupervisor | None = None
        self._epoch: int | None = None

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
        self._epoch = self.committer.acquire_epoch()
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
            **self._supervisor_kwargs,
        )
        await self.supervisor.initialize(epoch=self._epoch)

    async def terminate(self) -> None:
        if self.supervisor is not None:
            await self.supervisor.terminate()

    async def join(self) -> None:
        if self.supervisor is not None:
            await self.supervisor.join()

    # -- migration -----------------------------------------------------------

    def migrate(
        self,
        session_ref: SessionRef,
        *,
        source_digest: str,
        session_generation: int = 0,
        writer_epoch: int | None = None,
        v3_migration_lock: object,
        seed_snapshot: object = None,
        freeze_v2_seed: object = None,
    ) -> MigrationOutcome:
        """One-time v2 seeding for a session (design 15.2).

        The migration commits at its own writer epoch, always strictly below the epoch
        the running supervisor acquires at :meth:`initialize`, so the first live turn's
        sequence strictly exceeds the genesis sequence.
        """

        epoch = self.committer.acquire_epoch() if writer_epoch is None else int(writer_epoch)
        return self.coordinator.migrate(
            session_ref,
            writer_epoch=epoch,
            session_generation=session_generation,
            source_digest=source_digest,
            v3_migration_lock=v3_migration_lock,
            seed_snapshot=seed_snapshot,
            freeze_v2_seed=freeze_v2_seed,
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
            deadline_monotonic=moment + ms / 1000.0,
            handle=handle,
        )
        return self.supervisor.offer(job)


__all__ = [
    "DEFAULT_SHADOW_DEADLINE_MS",
    "V3ShadowRuntime",
]
