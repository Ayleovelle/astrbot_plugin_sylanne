"""Bounded bridge registry joining request and response hook callbacks."""

from __future__ import annotations

import hmac
import math
import threading
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum

from sylanne_alpha.v3bridge.limits import (
    MAX_REPOSITORY_SESSIONS,
    MAX_TURN_REGISTRY,
    TURN_REGISTRY_TTL_SECONDS,
)
from sylanne_alpha.v3bridge.session_identity import (
    MAX_SIGNED_64,
    SESSION_IDENTITY_MAX_KEY_ID_BYTES,
    SessionIdentityKey,
)
from sylanne_alpha.v3core.canonical import canonical_sha256
from sylanne_alpha.v3core.contracts import SessionRef, TurnKey, TurnSequence


MAX_PLUGIN_INSTANCE_ID_BYTES = 96
MAX_BRIDGE_REQUEST_NONCE_BYTES = 256


def _required_text(value: object, name: str, *, max_bytes: int | None = None) -> str:
    if type(value) is not str:
        raise TypeError(f"{name} must have exact type str")
    if not value:
        raise ValueError(f"{name} must not be empty")
    if max_bytes is not None:
        if len(value) > max_bytes:
            raise ValueError(f"{name} exceeds {max_bytes} UTF-8 bytes")
        if len(value.encode("utf-8")) > max_bytes:
            raise ValueError(f"{name} exceeds {max_bytes} UTF-8 bytes")
    return value


def _positive_int(value: object, name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must have exact type int")
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


def _writer_epoch(value: object) -> int:
    if type(value) is not int:
        raise TypeError("writer_epoch must have exact type int")
    if not 0 <= value <= MAX_SIGNED_64:
        raise ValueError("writer_epoch must be a signed 64-bit non-negative integer")
    return value


def _bounded_nonnegative_int(value: object, name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must have exact type int")
    if not 0 <= value <= MAX_SIGNED_64:
        raise ValueError(f"{name} must be a signed 64-bit non-negative integer")
    return value


def _validate_session_ref(session_ref: object) -> SessionRef:
    if type(session_ref) is not SessionRef:
        raise TypeError("session_ref must have exact type SessionRef")
    _required_text(
        session_ref.key_id,
        "session_ref.key_id",
        max_bytes=SESSION_IDENTITY_MAX_KEY_ID_BYTES,
    )
    if type(session_ref.session_digest) is not bytes:
        raise TypeError("session_ref.session_digest must have exact type bytes")
    if len(session_ref.session_digest) != 32:
        raise ValueError("session_ref.session_digest must be a full 256-bit digest")
    _bounded_nonnegative_int(
        session_ref.session_generation,
        "session_ref.session_generation",
    )
    return session_ref


def _validate_sequence(sequence: object) -> TurnSequence:
    if type(sequence) is not TurnSequence:
        raise TypeError("sequence must have exact type TurnSequence")
    _writer_epoch(sequence.writer_epoch)
    if type(sequence.local_sequence) is not int:
        raise TypeError("local_sequence must have exact type int")
    if not 1 <= sequence.local_sequence <= MAX_SIGNED_64:
        raise ValueError("local_sequence must be a signed 64-bit positive integer")
    return sequence


def _validate_turn_key(turn_key: object) -> TurnKey:
    if type(turn_key) is not TurnKey:
        raise TypeError("turn_key must have exact type TurnKey")
    _required_text(
        turn_key.plugin_instance_id,
        "turn_key.plugin_instance_id",
        max_bytes=MAX_PLUGIN_INSTANCE_ID_BYTES,
    )
    _validate_session_ref(turn_key.session_ref)
    _required_text(
        turn_key.bridge_request_nonce,
        "turn_key.bridge_request_nonce",
        max_bytes=MAX_BRIDGE_REQUEST_NONCE_BYTES,
    )
    _bounded_nonnegative_int(turn_key.request_attempt, "turn_key.request_attempt")
    return turn_key


def _now(value: object) -> float:
    if type(value) is not float:
        raise TypeError("now must have exact type float")
    if not math.isfinite(value) or value < 0.0:
        raise ValueError("now must be finite and non-negative")
    return value


class TurnRegistryState(Enum):
    REQUEST_CAPTURED = "REQUEST_CAPTURED"
    RESPONSE_CLAIMED = "RESPONSE_CLAIMED"
    ENQUEUED = "ENQUEUED"
    FINALIZED = "FINALIZED"


class SequenceStatus(Enum):
    ALLOCATED = "ALLOCATED"
    ACCEPTED = "ACCEPTED"
    DROPPED = "DROPPED"
    COMMITTED = "COMMITTED"


@dataclass(frozen=True, slots=True)
class SequenceHighWatermarks:
    accepted: TurnSequence | None = None
    dropped: TurnSequence | None = None
    committed: TurnSequence | None = None

    def __post_init__(self) -> None:
        for name in ("accepted", "dropped", "committed"):
            value = getattr(self, name)
            if value is not None and type(value) is not TurnSequence:
                raise TypeError(f"{name} must have exact type TurnSequence or be missing")


class CreditAdjacency(Enum):
    ADJACENT = "ADJACENT"
    CENSORED_CROSS_SESSION = "CENSORED_CROSS_SESSION"
    CENSORED_CROSS_EPOCH = "CENSORED_CROSS_EPOCH"
    CENSORED_DROPPED_GAP = "CENSORED_DROPPED_GAP"
    CENSORED_NON_ADJACENT = "CENSORED_NON_ADJACENT"
    CENSORED_HISTORY_UNAVAILABLE = "CENSORED_HISTORY_UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class TurnHandle:
    """Raw-identifier-free value handle passed between authoritative hooks."""

    turn_key: TurnKey
    turn_id: str
    sequence: TurnSequence

    def __post_init__(self) -> None:
        _validate_turn_key(self.turn_key)
        _required_text(self.turn_id, "turn_id")
        _validate_sequence(self.sequence)


@dataclass(frozen=True, slots=True)
class RegistryStats:
    captures: int
    terminal_attempts: int
    accepted_terminal_claims: int


@dataclass(slots=True)
class _SequencePartition:
    current_epoch: int | None
    next_local_sequence: int
    high_watermark: TurnSequence | None
    status_high_watermarks: SequenceHighWatermarks
    records: dict[TurnSequence, SequenceStatus]


class SequenceLedger:
    """Bounded sequence allocator and status history partitioned by SessionRef."""

    def __init__(
        self,
        *,
        max_sessions: int = MAX_REPOSITORY_SESSIONS,
        history_capacity: int = MAX_TURN_REGISTRY,
    ) -> None:
        self._max_sessions = _positive_int(max_sessions, "max_sessions")
        self._history_capacity = _positive_int(history_capacity, "history_capacity")
        if self._max_sessions > MAX_REPOSITORY_SESSIONS:
            raise ValueError("max_sessions exceeds MAX_REPOSITORY_SESSIONS")
        if self._history_capacity > MAX_TURN_REGISTRY:
            raise ValueError("history_capacity exceeds MAX_TURN_REGISTRY")
        self._partitions: dict[SessionRef, _SequencePartition] = {}
        self._history_order: OrderedDict[tuple[SessionRef, TurnSequence], None] = OrderedDict()
        self._lock = threading.RLock()

    @staticmethod
    def _validate_session_ref(session_ref: object) -> SessionRef:
        return _validate_session_ref(session_ref)

    @staticmethod
    def _validate_sequence(sequence: object) -> TurnSequence:
        return _validate_sequence(sequence)

    def allocate(self, *, session_ref: SessionRef, writer_epoch: int) -> TurnSequence | None:
        session_ref = self._validate_session_ref(session_ref)
        writer_epoch = _writer_epoch(writer_epoch)
        with self._lock:
            partition = self._partitions.get(session_ref)
            if (
                partition is not None
                and partition.current_epoch is not None
                and writer_epoch < partition.current_epoch
            ):
                return None
            if partition is None:
                if len(self._partitions) >= self._max_sessions:
                    return None
            if partition is None or partition.current_epoch != writer_epoch:
                next_local = 1
            else:
                next_local = partition.next_local_sequence + 1
            if next_local > MAX_SIGNED_64:
                return None
            while len(self._history_order) >= self._history_capacity:
                if not self._evict_oldest_terminal_locked():
                    return None
            if partition is None:
                partition = _SequencePartition(
                    current_epoch=None,
                    next_local_sequence=0,
                    high_watermark=None,
                    status_high_watermarks=SequenceHighWatermarks(),
                    records={},
                )
                self._partitions[session_ref] = partition
            if partition.current_epoch != writer_epoch:
                partition.current_epoch = writer_epoch
                partition.next_local_sequence = 0
            sequence = TurnSequence(writer_epoch=writer_epoch, local_sequence=next_local)
            if sequence in partition.records:
                return None
            partition.records[sequence] = SequenceStatus.ALLOCATED
            self._history_order[(session_ref, sequence)] = None
            partition.next_local_sequence = next_local
            partition.high_watermark = sequence
            return sequence

    def _evict_oldest_terminal_locked(self) -> bool:
        for record_key in tuple(self._history_order):
            session_ref, sequence = record_key
            partition = self._partitions[session_ref]
            if partition.records.get(sequence) not in {
                SequenceStatus.COMMITTED,
                SequenceStatus.DROPPED,
            }:
                continue
            del partition.records[sequence]
            del self._history_order[record_key]
            return True
        return False

    def status(self, session_ref: SessionRef, sequence: TurnSequence) -> SequenceStatus | None:
        session_ref = self._validate_session_ref(session_ref)
        sequence = self._validate_sequence(sequence)
        with self._lock:
            partition = self._partitions.get(session_ref)
            return None if partition is None else partition.records.get(sequence)

    def _transition(
        self,
        session_ref: SessionRef,
        sequence: TurnSequence,
        *,
        expected: tuple[SequenceStatus, ...],
        target: SequenceStatus,
    ) -> bool:
        session_ref = self._validate_session_ref(session_ref)
        sequence = self._validate_sequence(sequence)
        with self._lock:
            partition = self._partitions.get(session_ref)
            if partition is None or partition.records.get(sequence) not in expected:
                return False
            partition.records[sequence] = target
            current = partition.status_high_watermarks
            accepted = current.accepted
            dropped = current.dropped
            committed = current.committed
            if target is SequenceStatus.ACCEPTED and (accepted is None or sequence > accepted):
                accepted = sequence
            elif target is SequenceStatus.DROPPED and (dropped is None or sequence > dropped):
                dropped = sequence
            elif target is SequenceStatus.COMMITTED and (
                committed is None or sequence > committed
            ):
                committed = sequence
            partition.status_high_watermarks = SequenceHighWatermarks(
                accepted=accepted,
                dropped=dropped,
                committed=committed,
            )
            return True

    def mark_accepted(self, session_ref: SessionRef, sequence: TurnSequence) -> bool:
        return self._transition(
            session_ref,
            sequence,
            expected=(SequenceStatus.ALLOCATED,),
            target=SequenceStatus.ACCEPTED,
        )

    def mark_dropped(self, session_ref: SessionRef, sequence: TurnSequence) -> bool:
        return self._transition(
            session_ref,
            sequence,
            expected=(SequenceStatus.ALLOCATED, SequenceStatus.ACCEPTED),
            target=SequenceStatus.DROPPED,
        )

    def mark_committed(self, session_ref: SessionRef, sequence: TurnSequence) -> bool:
        return self._transition(
            session_ref,
            sequence,
            expected=(SequenceStatus.ACCEPTED,),
            target=SequenceStatus.COMMITTED,
        )

    def credit_adjacency(
        self,
        previous_session_ref: SessionRef,
        previous_sequence: TurnSequence,
        current_session_ref: SessionRef,
        current_sequence: TurnSequence,
    ) -> CreditAdjacency:
        previous_session_ref = self._validate_session_ref(previous_session_ref)
        current_session_ref = self._validate_session_ref(current_session_ref)
        previous_sequence = self._validate_sequence(previous_sequence)
        current_sequence = self._validate_sequence(current_sequence)
        if previous_session_ref != current_session_ref:
            return CreditAdjacency.CENSORED_CROSS_SESSION
        if previous_sequence.writer_epoch != current_sequence.writer_epoch:
            return CreditAdjacency.CENSORED_CROSS_EPOCH
        with self._lock:
            partition = self._partitions.get(previous_session_ref)
            if partition is None:
                return CreditAdjacency.CENSORED_HISTORY_UNAVAILABLE
            if partition.current_epoch != current_sequence.writer_epoch:
                return CreditAdjacency.CENSORED_CROSS_EPOCH
            low = previous_sequence.local_sequence
            high = current_sequence.local_sequence
            if high <= low:
                return CreditAdjacency.CENSORED_NON_ADJACENT
            previous_status = partition.records.get(previous_sequence)
            current_status = partition.records.get(current_sequence)
            if (
                previous_status is SequenceStatus.DROPPED
                or current_status is SequenceStatus.DROPPED
            ):
                return CreditAdjacency.CENSORED_DROPPED_GAP
            dropped_high_watermark = partition.status_high_watermarks.dropped
            if (
                dropped_high_watermark is not None
                and dropped_high_watermark.writer_epoch == previous_sequence.writer_epoch
                and low < dropped_high_watermark.local_sequence <= high
            ):
                return CreditAdjacency.CENSORED_DROPPED_GAP
            if high != low + 1:
                return CreditAdjacency.CENSORED_NON_ADJACENT
            if previous_status is None or current_status is None:
                high_watermarks = partition.status_high_watermarks
                if (
                    dropped_high_watermark is not None
                    and dropped_high_watermark.writer_epoch
                    == previous_sequence.writer_epoch
                    and dropped_high_watermark.local_sequence > high
                ):
                    return CreditAdjacency.CENSORED_HISTORY_UNAVAILABLE
                if (
                    high_watermarks.committed == previous_sequence
                    and high_watermarks.accepted == current_sequence
                ):
                    return CreditAdjacency.ADJACENT
                return CreditAdjacency.CENSORED_HISTORY_UNAVAILABLE
            for sequence, status in partition.records.items():
                if (
                    sequence.writer_epoch == previous_sequence.writer_epoch
                    and low < sequence.local_sequence <= high
                    and status is SequenceStatus.DROPPED
                ):
                    return CreditAdjacency.CENSORED_DROPPED_GAP
            return CreditAdjacency.ADJACENT

    def high_watermark(self, session_ref: SessionRef) -> TurnSequence | None:
        session_ref = self._validate_session_ref(session_ref)
        with self._lock:
            partition = self._partitions.get(session_ref)
            return None if partition is None else partition.high_watermark

    def status_high_watermarks(self, session_ref: SessionRef) -> SequenceHighWatermarks:
        session_ref = self._validate_session_ref(session_ref)
        with self._lock:
            partition = self._partitions.get(session_ref)
            if partition is None:
                return SequenceHighWatermarks()
            return partition.status_high_watermarks

    @property
    def session_count(self) -> int:
        with self._lock:
            return len(self._partitions)

    @property
    def record_count(self) -> int:
        with self._lock:
            return len(self._history_order)


@dataclass(slots=True)
class _RegistryEntry:
    handle: TurnHandle
    correlation: bytes
    state: TurnRegistryState
    touched_at: float


class TurnRegistry:
    """Thread-safe bounded TurnKey registry with no host object or raw ID storage."""

    def __init__(
        self,
        *,
        plugin_instance_id: str,
        correlation_secret: bytes,
        writer_epoch: int,
        capacity: int = MAX_TURN_REGISTRY,
        ttl_seconds: float = float(TURN_REGISTRY_TTL_SECONDS),
        sequence_ledger: SequenceLedger | None = None,
    ) -> None:
        self._plugin_instance_id = _required_text(
            plugin_instance_id,
            "plugin_instance_id",
            max_bytes=MAX_PLUGIN_INSTANCE_ID_BYTES,
        )
        if type(correlation_secret) is not bytes:
            raise TypeError("correlation_secret must have exact type bytes")
        if not correlation_secret:
            raise ValueError("correlation_secret must not be empty")
        self._writer_epoch = _writer_epoch(writer_epoch)
        self._capacity = _positive_int(capacity, "capacity")
        if self._capacity > MAX_TURN_REGISTRY:
            raise ValueError("capacity exceeds MAX_TURN_REGISTRY")
        if type(ttl_seconds) is not float:
            raise TypeError("ttl_seconds must have exact type float")
        if not math.isfinite(ttl_seconds) or ttl_seconds <= 0.0:
            raise ValueError("ttl_seconds must be finite and positive")
        if sequence_ledger is not None and type(sequence_ledger) is not SequenceLedger:
            raise TypeError("sequence_ledger must have exact type SequenceLedger")
        self._ttl_seconds = ttl_seconds
        self._ledger = sequence_ledger or SequenceLedger()
        self._correlation_key = SessionIdentityKey(
            key_id=f"turn-correlation:{self._plugin_instance_id}",
            secret=correlation_secret,
        )
        self._entries: dict[TurnKey, _RegistryEntry] = {}
        self._correlation_index: dict[bytes, TurnKey] = {}
        self._captures = 0
        self._terminal_attempts = 0
        self._accepted_terminal_claims = 0
        self._lock = threading.RLock()

    def _remove_locked(self, turn_key: TurnKey, *, orphaned: bool) -> TurnHandle | None:
        entry = self._entries.pop(turn_key, None)
        if entry is None:
            return None
        if self._correlation_index.get(entry.correlation) == turn_key:
            del self._correlation_index[entry.correlation]
        if orphaned and entry.state is not TurnRegistryState.FINALIZED:
            self._ledger.mark_dropped(turn_key.session_ref, entry.handle.sequence)
        return entry.handle

    def _cleanup_stale_locked(self, now: float) -> tuple[TurnHandle, ...]:
        stale_keys = tuple(
            turn_key
            for turn_key, entry in self._entries.items()
            if now - entry.touched_at >= self._ttl_seconds
        )
        cleaned: list[TurnHandle] = []
        for turn_key in stale_keys:
            handle = self._remove_locked(turn_key, orphaned=True)
            if handle is not None:
                cleaned.append(handle)
        return tuple(cleaned)

    def _make_room_locked(self, now: float) -> bool:
        self._cleanup_stale_locked(now)
        while len(self._entries) >= self._capacity:
            finalized = [
                (entry.touched_at, entry.handle.turn_id, turn_key)
                for turn_key, entry in self._entries.items()
                if entry.state is TurnRegistryState.FINALIZED
            ]
            if not finalized:
                return False
            _, _, turn_key = min(finalized)
            self._remove_locked(turn_key, orphaned=False)
        return True

    def capture_request(
        self,
        *,
        session_ref: SessionRef | None,
        bridge_request_nonce: str,
        request_attempt: int,
        platform_id: object,
        unified_msg_origin: object,
        message_id: object,
        now: float,
    ) -> TurnHandle | None:
        now = _now(now)
        if session_ref is None:
            return None
        session_ref = _validate_session_ref(session_ref)
        bridge_request_nonce = _required_text(
            bridge_request_nonce,
            "bridge_request_nonce",
            max_bytes=MAX_BRIDGE_REQUEST_NONCE_BYTES,
        )
        request_attempt = _bounded_nonnegative_int(request_attempt, "request_attempt")
        correlation = self._correlation_key.correlation_digest(
            platform_id,
            unified_msg_origin,
            message_id,
        )
        if correlation is None:
            return None
        turn_key = TurnKey(
            plugin_instance_id=self._plugin_instance_id,
            session_ref=session_ref,
            bridge_request_nonce=bridge_request_nonce,
            request_attempt=request_attempt,
        )
        turn_id = canonical_sha256(turn_key)
        with self._lock:
            self._cleanup_stale_locked(now)
            if turn_key in self._entries or correlation in self._correlation_index:
                return None
            if not self._make_room_locked(now):
                return None
            sequence = self._ledger.allocate(
                session_ref=session_ref,
                writer_epoch=self._writer_epoch,
            )
            if sequence is None:
                return None
            handle = TurnHandle(turn_key=turn_key, turn_id=turn_id, sequence=sequence)
            self._entries[turn_key] = _RegistryEntry(
                handle=handle,
                correlation=correlation,
                state=TurnRegistryState.REQUEST_CAPTURED,
                touched_at=now,
            )
            self._correlation_index[correlation] = turn_key
            self._captures += 1
            return handle

    def claim_response(
        self,
        *,
        handle: TurnHandle | None,
        platform_id: object,
        unified_msg_origin: object,
        message_id: object,
        now: float,
    ) -> bool:
        now = _now(now)
        if handle is not None and type(handle) is not TurnHandle:
            raise TypeError("handle must have exact type TurnHandle or be missing")
        correlation = self._correlation_key.correlation_digest(
            platform_id,
            unified_msg_origin,
            message_id,
        )
        with self._lock:
            self._terminal_attempts += 1
            self._cleanup_stale_locked(now)
            if handle is None or correlation is None:
                return False
            entry = self._entries.get(handle.turn_key)
            if entry is None or entry.handle != handle:
                return False
            if entry.state is not TurnRegistryState.REQUEST_CAPTURED:
                return False
            if self._correlation_index.get(correlation) != handle.turn_key:
                return False
            if not hmac.compare_digest(entry.correlation, correlation):
                return False
            entry.state = TurnRegistryState.RESPONSE_CLAIMED
            entry.touched_at = now
            self._accepted_terminal_claims += 1
            return True

    def mark_enqueued(self, *, handle: TurnHandle, now: float) -> bool:
        now = _now(now)
        if type(handle) is not TurnHandle:
            raise TypeError("handle must have exact type TurnHandle")
        with self._lock:
            self._cleanup_stale_locked(now)
            entry = self._entries.get(handle.turn_key)
            if (
                entry is None
                or entry.handle != handle
                or entry.state is not TurnRegistryState.RESPONSE_CLAIMED
            ):
                return False
            if not self._ledger.mark_accepted(handle.turn_key.session_ref, handle.sequence):
                return False
            entry.state = TurnRegistryState.ENQUEUED
            entry.touched_at = now
            return True

    def finalize(self, *, handle: TurnHandle, now: float, dropped: bool = False) -> bool:
        now = _now(now)
        if type(handle) is not TurnHandle:
            raise TypeError("handle must have exact type TurnHandle")
        if type(dropped) is not bool:
            raise TypeError("dropped must have exact type bool")
        with self._lock:
            self._cleanup_stale_locked(now)
            entry = self._entries.get(handle.turn_key)
            if entry is None or entry.handle != handle or entry.state is not TurnRegistryState.ENQUEUED:
                return False
            transition = self._ledger.mark_dropped if dropped else self._ledger.mark_committed
            if not transition(handle.turn_key.session_ref, handle.sequence):
                return False
            entry.state = TurnRegistryState.FINALIZED
            entry.touched_at = now
            return True

    def cleanup(self, *, now: float) -> tuple[TurnHandle, ...]:
        now = _now(now)
        with self._lock:
            return self._cleanup_stale_locked(now)

    def state_for(self, handle: TurnHandle) -> TurnRegistryState | None:
        if type(handle) is not TurnHandle:
            raise TypeError("handle must have exact type TurnHandle")
        with self._lock:
            entry = self._entries.get(handle.turn_key)
            if entry is None or entry.handle != handle:
                return None
            return entry.state

    def sequence_status(self, handle: TurnHandle) -> SequenceStatus | None:
        if type(handle) is not TurnHandle:
            raise TypeError("handle must have exact type TurnHandle")
        return self._ledger.status(handle.turn_key.session_ref, handle.sequence)

    def stats(self) -> RegistryStats:
        with self._lock:
            return RegistryStats(
                captures=self._captures,
                terminal_attempts=self._terminal_attempts,
                accepted_terminal_claims=self._accepted_terminal_claims,
            )

    @property
    def entry_count(self) -> int:
        with self._lock:
            return len(self._entries)

    @property
    def correlation_count(self) -> int:
        with self._lock:
            return len(self._correlation_index)


__all__ = [
    "CreditAdjacency",
    "MAX_BRIDGE_REQUEST_NONCE_BYTES",
    "MAX_PLUGIN_INSTANCE_ID_BYTES",
    "MAX_SIGNED_64",
    "RegistryStats",
    "SequenceLedger",
    "SequenceHighWatermarks",
    "SequenceStatus",
    "TurnHandle",
    "TurnRegistry",
    "TurnRegistryState",
]
