"""Scope-bound durable background assessment queues.

The active queue owns exactly one immutable persistence capability.  Legacy
registry/KV behaviour is isolated in ``legacy_background_queue`` and is never
selected from this module.
"""

from __future__ import annotations

import asyncio
import collections
import inspect
import math
from typing import Any, Callable

from sylanne_alpha.scope_repository import ScopedPersistenceGateway, StaleScopeWrite


_COMPONENT = "background-queue"
_SCHEMA_VERSION = "sylanne.scoped-background-queue.v1"
_MAX_JOBS = 500
_ScopeKey = tuple[str, int]


class BackgroundPostJob:
    """One queued post-response assessment with transient transport context."""

    __slots__ = (
        "event",
        "identity",
        "reply_text",
        "context_key",
        "sequence",
        "enqueued_at",
        "attempts",
        "next_retry_at",
        "last_error_type",
        "last_error_message",
        "last_failed_at",
        "dead_lettered_at",
        "leased_at",
        "lease_until",
        "_retries",
    )

    def __init__(
        self,
        event: Any,
        identity: str,
        reply_text: str,
        context_key: str,
        sequence: int,
        enqueued_at: float,
    ) -> None:
        self.event = event
        self.identity = identity
        self.reply_text = reply_text
        self.context_key = context_key
        self.sequence = sequence
        self.enqueued_at = enqueued_at
        self.attempts = 0
        self.next_retry_at = 0.0
        self.last_error_type = ""
        self.last_error_message = ""
        self.last_failed_at = 0.0
        self.dead_lettered_at = 0.0
        self.leased_at = 0.0
        self.lease_until = 0.0
        self._retries = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "reply_text": self.reply_text,
            "context_key": self.context_key,
            "sequence": self.sequence,
            "enqueued_at": self.enqueued_at,
            "attempts": self.attempts,
            "next_retry_at": self.next_retry_at,
            "last_error_type": self.last_error_type,
            "last_error_message": self.last_error_message,
            "last_failed_at": self.last_failed_at,
            "dead_lettered_at": self.dead_lettered_at,
        }


class _QueueState:
    """Mutable state held under one complete scope identity."""

    __slots__ = (
        "queue",
        "active",
        "dead_letters",
        "latest_enqueued",
        "last_committed",
        "generation",
    )

    def __init__(self) -> None:
        self.queue: collections.deque[BackgroundPostJob] = collections.deque(maxlen=_MAX_JOBS)
        self.active: dict[int, BackgroundPostJob] = {}
        self.dead_letters: collections.deque[BackgroundPostJob] = collections.deque(maxlen=_MAX_JOBS)
        self.latest_enqueued = 0
        self.last_committed = 0
        self.generation = 0


class BackgroundPostQueue:
    """A queue permanently bound to one frozen session persistence gateway."""

    def __init__(self, persistence: ScopedPersistenceGateway) -> None:
        if type(persistence) is not ScopedPersistenceGateway:
            raise ValueError("persistence must be a ScopedPersistenceGateway")
        self._persistence = persistence
        self._scope_key: _ScopeKey = (
            persistence.scope.storage_token,
            persistence.scope.scope_generation,
        )
        self._states: dict[_ScopeKey, _QueueState] = {self._scope_key: _QueueState()}

    @property
    def persistence(self) -> ScopedPersistenceGateway:
        """Return the immutable capability captured at construction."""

        return self._persistence

    @property
    def scope(self):
        """Return the frozen scope associated with this queue."""

        return self._persistence.scope

    @property
    def pending_count(self) -> int:
        return len(self._state().queue)

    @property
    def active_count(self) -> int:
        return len(self._state().active)

    @property
    def last_committed(self) -> int:
        return self._state().last_committed

    def _state(self) -> _QueueState:
        return self._states[self._scope_key]

    def _ensure_live(self) -> None:
        self._persistence.repository.validate_session_scope(self._persistence.scope)

    @staticmethod
    def _require_time(value: object, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name} must be a finite number")
        result = float(value)
        if not math.isfinite(result):
            raise ValueError(f"{name} must be a finite number")
        return result

    @staticmethod
    def _require_non_negative_int(value: object, name: str) -> int:
        if type(value) is not int or value < 0:
            raise ValueError(f"{name} must be a non-negative int")
        return value

    @classmethod
    def _serialize_job(cls, job: BackgroundPostJob) -> dict[str, object]:
        """Persist only assessment mechanics and text, never transport handles."""

        return {
            "reply_text": job.reply_text,
            "context_key": job.context_key,
            "sequence": job.sequence,
            "enqueued_at": job.enqueued_at,
            "attempts": job.attempts,
            "next_retry_at": job.next_retry_at,
            "last_error_type": job.last_error_type,
            "last_error_message": job.last_error_message,
            "last_failed_at": job.last_failed_at,
            "dead_lettered_at": job.dead_lettered_at,
        }

    @classmethod
    def _deserialize_job(cls, payload: object) -> BackgroundPostJob:
        if type(payload) is not dict:
            raise ValueError("background queue job must be an exact dict")
        reply_text = payload.get("reply_text")
        context_key = payload.get("context_key")
        if type(reply_text) is not str or type(context_key) is not str:
            raise ValueError("background queue job text must be str")
        job = BackgroundPostJob(
            event=None,
            identity="",
            reply_text=reply_text,
            context_key=context_key,
            sequence=cls._require_non_negative_int(payload.get("sequence"), "sequence"),
            enqueued_at=cls._require_time(payload.get("enqueued_at"), "enqueued_at"),
        )
        job.attempts = cls._require_non_negative_int(payload.get("attempts"), "attempts")
        job.next_retry_at = cls._require_time(payload.get("next_retry_at"), "next_retry_at")
        last_error_type = payload.get("last_error_type")
        last_error_message = payload.get("last_error_message")
        if type(last_error_type) is not str or type(last_error_message) is not str:
            raise ValueError("background queue error metadata must be str")
        job.last_error_type = last_error_type
        job.last_error_message = last_error_message
        job.last_failed_at = cls._require_time(payload.get("last_failed_at"), "last_failed_at")
        job.dead_lettered_at = cls._require_time(payload.get("dead_lettered_at"), "dead_lettered_at")
        return job

    def _checkpoint_payload(self, state: _QueueState) -> dict[str, object]:
        return {
            "schema_version": _SCHEMA_VERSION,
            "latest_enqueued": state.latest_enqueued,
            "last_committed": state.last_committed,
            "jobs": [self._serialize_job(job) for job in state.queue],
            "active_jobs": [self._serialize_job(job) for job in state.active.values()],
            "dead_letters": [self._serialize_job(job) for job in state.dead_letters],
        }

    def enqueue(self, job: BackgroundPostJob) -> bool:
        """Append one live job to this queue's exact scope state."""

        self._ensure_live()
        if type(job) is not BackgroundPostJob:
            raise ValueError("job must be a BackgroundPostJob")
        state = self._state()
        if len(state.queue) >= _MAX_JOBS:
            return False
        state.queue.append(job)
        state.latest_enqueued = max(state.latest_enqueued, job.sequence)
        return True

    def recover_expired_active(self, *, now: float) -> int:
        """Return expired leases only to this captured scope's pending queue."""

        self._ensure_live()
        observed_now = self._require_time(now, "now")
        state = self._state()
        expired = [
            sequence
            for sequence, job in state.active.items()
            if job.lease_until and job.lease_until < observed_now
        ]
        for sequence in sorted(expired):
            job = state.active.pop(sequence)
            job.leased_at = 0.0
            job.lease_until = 0.0
            if len(state.queue) < _MAX_JOBS:
                state.queue.append(job)
        state.queue = collections.deque(
            sorted(state.queue, key=lambda job: job.sequence),
            maxlen=_MAX_JOBS,
        )
        return len(expired)

    def lease_next(self, *, now: float, lease_seconds: float) -> BackgroundPostJob | None:
        """Lease the next due job without any current-session lookup."""

        self._ensure_live()
        observed_now = self._require_time(now, "now")
        duration = self._require_time(lease_seconds, "lease_seconds")
        if duration <= 0.0:
            raise ValueError("lease_seconds must be positive")
        self.recover_expired_active(now=observed_now)
        state = self._state()
        if not state.queue or state.queue[0].next_retry_at > observed_now:
            return None
        job = state.queue.popleft()
        job.leased_at = observed_now
        job.lease_until = observed_now + duration
        state.active[job.sequence] = job
        return job

    def complete(self, job_or_sequence: BackgroundPostJob | int) -> bool:
        """Acknowledge an active lease in this frozen scope only."""

        self._ensure_live()
        if type(job_or_sequence) is BackgroundPostJob:
            sequence = job_or_sequence.sequence
            expected_job: BackgroundPostJob | None = job_or_sequence
        else:
            sequence = self._require_non_negative_int(job_or_sequence, "sequence")
            expected_job = None
        state = self._state()
        active = state.active.get(sequence)
        if active is None or (expected_job is not None and active is not expected_job):
            return False
        state.active.pop(sequence)
        active.leased_at = 0.0
        active.lease_until = 0.0
        state.last_committed = max(state.last_committed, sequence)
        return True

    async def drain(
        self,
        processor: Callable[[BackgroundPostJob], object],
        *,
        now: float,
        lease_seconds: float = 30.0,
    ) -> int:
        """Run due work through a caller-supplied private assessment processor."""

        if not callable(processor):
            raise ValueError("processor must be callable")
        observed_now = self._require_time(now, "now")
        processed = 0
        while True:
            job = self.lease_next(now=observed_now, lease_seconds=lease_seconds)
            if job is None:
                return processed
            outcome = processor(job)
            if inspect.isawaitable(outcome):
                outcome = await outcome
            if outcome is False or not self.complete(job):
                return processed
            processed += 1

    def _save_now(
        self,
        gateway: ScopedPersistenceGateway,
        *,
        state: _QueueState,
        expected_generation: int,
        payload: dict[str, object],
    ) -> bool:
        gateway.repository.validate_session_scope(gateway.scope)
        next_generation = gateway.save(
            _COMPONENT,
            expected_generation=expected_generation,
            payload=payload,
        )
        if gateway is self._persistence and state.generation == expected_generation:
            state.generation = next_generation
        return True

    async def _save(
        self,
        gateway: ScopedPersistenceGateway,
        *,
        state: _QueueState,
        expected_generation: int,
        payload: dict[str, object],
    ) -> bool:
        return self._save_now(
            gateway,
            state=state,
            expected_generation=expected_generation,
            payload=payload,
        )

    def save_checkpoint_now(self) -> bool:
        """Synchronously persist this queue through its captured gateway only."""

        self._ensure_live()
        state = self._state()
        return self._save_now(
            self._persistence,
            state=state,
            expected_generation=state.generation,
            payload=self._checkpoint_payload(state),
        )

    async def save_checkpoint(self) -> bool:
        """CAS-save this scope's queue state in its background component."""

        return self.save_checkpoint_now()

    def schedule_checkpoint(self, *, delay_seconds: float) -> asyncio.Task[bool]:
        """Schedule a write that remains bound to this gateway and generation."""

        delay = self._require_time(delay_seconds, "delay_seconds")
        if delay < 0.0:
            raise ValueError("delay_seconds must be non-negative")
        gateway = self._persistence
        state = self._state()
        generation = state.generation
        payload = self._checkpoint_payload(state)

        async def delayed_save() -> bool:
            await asyncio.sleep(delay)
            try:
                return self._save_now(
                    gateway,
                    state=state,
                    expected_generation=generation,
                    payload=payload,
                )
            except StaleScopeWrite:
                return False

        return asyncio.create_task(delayed_save(), name="scoped_background_queue_checkpoint")

    def recover_before_publication(self) -> bool:
        """Restore this exact queue synchronously before its runtime is published."""

        self._ensure_live()
        snapshot = self._persistence.load(_COMPONENT)
        if snapshot is None or snapshot.payload.get("schema_version") != _SCHEMA_VERSION:
            return False
        payload = snapshot.payload
        jobs_data = payload.get("jobs")
        active_data = payload.get("active_jobs")
        dead_data = payload.get("dead_letters")
        try:
            if type(jobs_data) is not list or type(active_data) is not list or type(dead_data) is not list:
                return False
            if len(jobs_data) + len(active_data) > _MAX_JOBS or len(dead_data) > _MAX_JOBS:
                return False
            recovered_jobs = [self._deserialize_job(item) for item in jobs_data]
            recovered_jobs.extend(self._deserialize_job(item) for item in active_data)
            recovered_dead = [self._deserialize_job(item) for item in dead_data]
            latest = self._require_non_negative_int(payload.get("latest_enqueued"), "latest_enqueued")
            committed = self._require_non_negative_int(payload.get("last_committed"), "last_committed")
        except ValueError:
            return False
        self._ensure_live()
        state = self._state()
        state.queue = collections.deque(
            sorted(recovered_jobs, key=lambda job: job.sequence),
            maxlen=_MAX_JOBS,
        )
        state.active = {}
        state.dead_letters = collections.deque(recovered_dead, maxlen=_MAX_JOBS)
        state.latest_enqueued = max([latest, *(job.sequence for job in recovered_jobs)])
        state.last_committed = committed
        state.generation = snapshot.generation
        return True

    async def recover_queue(self) -> bool:
        """Async compatibility seam for explicit recovery callers/tests."""

        return self.recover_before_publication()


__all__ = ["BackgroundPostJob", "BackgroundPostQueue"]
