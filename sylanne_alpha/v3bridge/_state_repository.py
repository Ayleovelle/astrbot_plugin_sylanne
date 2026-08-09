"""Crash-safe, multiprocess-safe compare-and-commit state repository for v3bridge.

This is the durable substrate under the fenced v3 turn registry. Each session's
cognitive state is a linear journal of immutable :class:`JournalRecord` revisions,
advanced only through an optimistic :meth:`StateRepository.compare_and_commit` whose
precondition pins the exact base (epoch, generation, revision, payload digest, turn
sequence). Publication is a single atomic pointer swap, so a crash at any point in the
write sequence either leaves the previous committed revision fully intact or exposes
the new one — never a partial state (see the ``FaultPoint`` fault-injection contract).

Concurrency safety is process-level: epoch allocation, CAS, quarantine, and byte-budget
reservation all run under a single inter-process file lock, so two OS processes racing
the same base produce exactly one winner and one typed rejection. Nothing here imports
the vendored engine or any raw host identifier — sessions are addressed only by the
opaque :class:`SessionRef` token.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import TracebackType
from typing import Callable

import portalocker

from sylanne_alpha.v3bridge.limits import PLUGIN_DATA_CAP_BYTES, effective_v3_hard_cap
from sylanne_alpha.v3bridge.session_identity import session_filename_token
from sylanne_alpha.v3core.canonical import canonical_json_bytes, canonical_sha256
from sylanne_alpha.v3core.contracts import SessionRef, TurnSequence


_JOURNAL_REFERENCE_PATTERN = re.compile(
    r"sessions/(s3-[0-9a-f]{64})/rev[0-9]{12}-[0-9a-f]{16}\.journal"
)


# ---------------------------------------------------------------------------
# Public vocabulary
# ---------------------------------------------------------------------------


class CommitResult(Enum):
    """Frozen outcome vocabulary for :meth:`StateRepository.compare_and_commit`."""

    COMMITTED = "COMMITTED"
    ALREADY_MIGRATED = "ALREADY_MIGRATED"
    DUPLICATE_TURN = "DUPLICATE_TURN"
    STALE_EPOCH = "STALE_EPOCH"
    STALE_STATE_GENERATION = "STALE_STATE_GENERATION"
    REVISION_CONFLICT = "REVISION_CONFLICT"
    BASE_DIGEST_MISMATCH = "BASE_DIGEST_MISMATCH"
    STALE_SEQUENCE = "STALE_SEQUENCE"
    CORRUPT_BASE = "CORRUPT_BASE"


class FaultPoint(Enum):
    """Ordered points in the write/publish sequence for crash-safety testing."""

    BEFORE_SERIALIZE = "BEFORE_SERIALIZE"
    AFTER_SERIALIZE = "AFTER_SERIALIZE"
    BEFORE_FLUSH = "BEFORE_FLUSH"
    AFTER_FLUSH = "AFTER_FLUSH"
    BEFORE_FSYNC = "BEFORE_FSYNC"
    AFTER_FSYNC = "AFTER_FSYNC"
    BEFORE_CLOSE = "BEFORE_CLOSE"
    AFTER_CLOSE = "AFTER_CLOSE"
    BEFORE_REPLACE = "BEFORE_REPLACE"
    AFTER_REPLACE = "AFTER_REPLACE"
    BEFORE_POINTER_PUBLISH = "BEFORE_POINTER_PUBLISH"
    AFTER_POINTER_PUBLISH = "AFTER_POINTER_PUBLISH"


class RepositoryBudgetExceeded(Exception):
    """Raised when a commit's reserved bytes would exceed the hard disk budget."""


class RepositoryCorruptionError(RuntimeError):
    """Raised when a durable repository artifact exists but cannot be trusted."""


class RepositoryCASConflict(RuntimeError):
    """Raised when a recovery replacement no longer matches its exact old pointer."""


@dataclass(frozen=True)
class AbsentState:
    """Precondition sentinel asserting no committed state exists for the session yet."""


@dataclass(frozen=True)
class CommitPrecondition:
    """Optimistic base pin: the commit only lands if every field still matches disk."""

    writer_epoch: int
    expected_state_generation_id: str
    expected_revision: int
    expected_payload_digest: str
    turn_id: str
    turn_sequence: TurnSequence


@dataclass(frozen=True)
class JournalRecord:
    """One immutable committed revision of a session's cognitive state."""

    schema_version: int
    formula_version: str
    source_digest: str
    state_generation_id: str
    revision: int
    writer_epoch: int
    session_generation: int
    model_revision: str
    last_committed_turn_sequence: TurnSequence
    last_committed_turn_id: str
    cognitive_payload: object
    deterministic_trace: object
    # cognitive_payload / deterministic_trace must be canonical-serializable (JSON-shaped:
    # None/bool/int/finite-float/str/bytes/list/tuple and str-keyed maps). A non-serializable
    # value raises TypeError from canonical_json_bytes during budget/serialize — BEFORE any
    # staging write — so a bad payload fails closed and never publishes a partial commit.


@dataclass(frozen=True)
class StatePointer:
    """The atomically published head naming the current (and previous) journal."""

    session_token: str
    state_generation_id: str
    revision: int
    payload_digest: str
    journal_digest: str
    current_journal: str
    previous_journal: str | None
    previous_journal_digest: str | None
    last_committed_turn_id: str
    last_committed_turn_sequence: TurnSequence


@dataclass(frozen=True)
class StateSnapshot:
    """A loaded head: its pointer plus the canonical bytes of the current payload."""

    pointer: StatePointer
    canonical_cognitive_payload: bytes


@dataclass(frozen=True)
class _CommitPlan:
    """Exact immutable bytes and pointer used for peak-budget admission and publish."""

    journal_name: str
    journal_bytes: bytes
    pointer: StatePointer
    pointer_bytes: bytes


def payload_digest(cognitive_payload: object) -> str:
    """Digest ONLY the canonicalized cognitive payload (order/field independent)."""

    return canonical_sha256(cognitive_payload)


# ---------------------------------------------------------------------------
# Inter-process lock (single writer across OS processes, cross-platform)
# ---------------------------------------------------------------------------


class _InterProcessLock:
    """Bounded exclusive portalocker scope serializing all repository mutations.

    The lock is deliberately non-blocking at the OS layer so portalocker's monotonic
    timeout loop remains effective on Windows and POSIX. Permanent open/locking errors
    propagate immediately; only genuine lock contention is retried until the deadline.
    This scope is not re-entrant, so mutating methods acquire it exactly once.
    """

    def __init__(self, path: Path, *, timeout_seconds: float) -> None:
        self._path = path
        self._timeout_seconds = timeout_seconds
        check_interval = min(0.05, max(0.001, timeout_seconds / 4.0))
        self._lock = portalocker.Lock(
            path,
            mode="a+b",
            timeout=timeout_seconds,
            check_interval=check_interval,
            flags=portalocker.LOCK_EX | portalocker.LOCK_NB,
        )

    def __enter__(self) -> "_InterProcessLock":
        self._lock.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._lock.__exit__(exc_type, exc_value, traceback)


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class StateRepository:
    """Durable, CAS-guarded, epoch-fenced journal store for one bridge data root."""

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        fault_injector: Callable[[FaultPoint], None] | None = None,
        replace_attempts: int = 8,
        replace_retry_seconds: float = 0.05,
        hard_limit_bytes: int | None = None,
        non_v3_bytes: int = 0,
        plugin_cap_bytes: int = PLUGIN_DATA_CAP_BYTES,
        lock_timeout_seconds: float = 2.0,
    ) -> None:
        self.root = Path(os.fspath(root))
        self.sessions_directory = self.root / "sessions"
        self.staging_directory = self.root / "staging"
        self._lock_path = self.root / ".repo.lock"
        self._epoch_path = self.root / "epoch"
        self._sealed_path = self.root / "sealed"
        self._fault_injector = fault_injector
        self._replace_attempts = max(1, int(replace_attempts))
        self._replace_retry_seconds = max(0.0, float(replace_retry_seconds))
        if hard_limit_bytes is None:
            hard_limit_bytes = effective_v3_hard_cap(non_v3_bytes, plugin_cap_bytes)
        if type(hard_limit_bytes) is not int:
            raise TypeError("hard_limit_bytes must have exact type int")
        if hard_limit_bytes < 0:
            raise ValueError("hard_limit_bytes must be non-negative")
        if isinstance(lock_timeout_seconds, bool) or not isinstance(
            lock_timeout_seconds, (int, float)
        ):
            raise TypeError("lock_timeout_seconds must be a finite number")
        lock_timeout = float(lock_timeout_seconds)
        if not math.isfinite(lock_timeout) or lock_timeout < 0.0:
            raise ValueError("lock_timeout_seconds must be finite and non-negative")
        self._hard_limit_bytes = hard_limit_bytes
        self._lock_timeout_seconds = lock_timeout
        self.root.mkdir(parents=True, exist_ok=True)
        self.sessions_directory.mkdir(parents=True, exist_ok=True)
        self.staging_directory.mkdir(parents=True, exist_ok=True)

    @property
    def hard_limit_bytes(self) -> int:
        """Current v3 namespace hard cap, including anchors and staging bytes."""

        return self._hard_limit_bytes

    def _repository_lock(self) -> _InterProcessLock:
        return _InterProcessLock(
            self._lock_path,
            timeout_seconds=self._lock_timeout_seconds,
        )

    # -- fault / atomic helpers ------------------------------------------------

    def _fault(self, point: FaultPoint) -> None:
        if self._fault_injector is not None:
            self._fault_injector(point)

    def _atomic_replace(self, source: Path, destination: Path) -> None:
        """os.replace with bounded retries for Windows sharing violations (winerror 32)."""

        last: OSError | None = None
        for attempt in range(self._replace_attempts):
            try:
                os.replace(source, destination)
                return
            except PermissionError as exc:  # pragma: no cover - Windows sharing race
                if getattr(exc, "winerror", None) != 32:
                    raise
                last = exc
                if attempt + 1 < self._replace_attempts:
                    time.sleep(self._replace_retry_seconds)
        if last is not None:  # pragma: no cover - exhausted retries
            raise last

    @staticmethod
    def _fsync_dir(directory: Path) -> None:
        """Sync a renamed directory entry only on platforms supporting directory fsync."""

        if os.name == "nt":  # Windows does not expose directory fsync through os.open.
            return
        try:
            dir_fd = os.open(directory, os.O_RDONLY)
        except OSError:  # pragma: no cover - unsupported platform/filesystem
            return
        try:
            os.fsync(dir_fd)
        except OSError:  # pragma: no cover - unsupported filesystem
            pass
        finally:
            os.close(dir_fd)

    def _write_bytes_durable(self, data: bytes) -> Path:
        """Write bytes to a fresh staging file with a full write + fsync barrier."""

        staging = self.staging_directory / f"{os.urandom(8).hex()}.stage"
        fd = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            # os.write may deliver fewer bytes than requested; loop until fully written so
            # a short write can never truncate the staged bytes under the pointer digest.
            view = memoryview(data)
            offset = 0
            while offset < len(view):
                offset += os.write(fd, view[offset:])
            self._fault(FaultPoint.BEFORE_FLUSH)
            # os.write is unbuffered (no user-space flush needed); fsync is the barrier.
            self._fault(FaultPoint.AFTER_FLUSH)
            self._fault(FaultPoint.BEFORE_FSYNC)
            os.fsync(fd)
            self._fault(FaultPoint.AFTER_FSYNC)
            self._fault(FaultPoint.BEFORE_CLOSE)
        finally:
            os.close(fd)
        self._fault(FaultPoint.AFTER_CLOSE)
        return staging

    # -- epoch fence -----------------------------------------------------------

    def _read_int(self, path: Path) -> int:
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            return 0
        except OSError as exc:
            raise RepositoryCorruptionError(f"epoch is unreadable: {path.name}") from exc
        try:
            value = int(raw.decode("ascii"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise RepositoryCorruptionError("epoch contains an invalid integer") from exc
        if value < 1 or raw != str(value).encode("ascii"):
            raise RepositoryCorruptionError("epoch contains a non-canonical integer")
        return value

    def current_epoch(self) -> int:
        """Return the highest allocated epoch (0 if none), without allocating."""

        return self._read_int(self._epoch_path)

    def acquire_epoch(self) -> int:
        """Allocate the next strictly-increasing epoch, unique across all processes."""

        with self._repository_lock():
            nxt = self._read_int(self._epoch_path) + 1
            self._fault(FaultPoint.BEFORE_SERIALIZE)
            encoded = str(nxt).encode("ascii")
            self._fault(FaultPoint.AFTER_SERIALIZE)
            self._reserve_peak(len(encoded), operation="epoch allocation")
            staged = self._write_bytes_durable(encoded)
            self._atomic_replace(staged, self._epoch_path)
            self._fsync_dir(self.root)
            return nxt

    def seal_epoch(self, epoch: int) -> None:
        """Fence an epoch so even its own writers can no longer commit."""

        with self._repository_lock():
            sealed = self._read_sealed()
            sealed.add(int(epoch))
            self._fault(FaultPoint.BEFORE_SERIALIZE)
            payload = canonical_json_bytes({"sealed": sorted(sealed)})
            self._fault(FaultPoint.AFTER_SERIALIZE)
            self._reserve_peak(len(payload), operation="epoch sealing")
            staged = self._write_bytes_durable(payload)
            self._atomic_replace(staged, self._sealed_path)
            self._fsync_dir(self.root)

    def _read_sealed(self) -> set[int]:
        try:
            raw = self._sealed_path.read_bytes()
        except FileNotFoundError:
            return set()
        except OSError as exc:
            raise RepositoryCorruptionError("epoch seal is unreadable") from exc
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise RepositoryCorruptionError("epoch seal is invalid JSON") from exc
        if type(data) is not dict or set(data) != {"sealed"}:
            raise RepositoryCorruptionError("epoch seal has an invalid envelope")
        items = data["sealed"]
        if type(items) is not list or any(type(item) is not int or item < 1 for item in items):
            raise RepositoryCorruptionError("epoch seal contains invalid epochs")
        sealed = set(items)
        if len(sealed) != len(items) or raw != canonical_json_bytes({"sealed": sorted(sealed)}):
            raise RepositoryCorruptionError("epoch seal is not canonical")
        return sealed

    def _epoch_is_fenced(self, writer_epoch: int) -> bool:
        return writer_epoch < self.current_epoch() or writer_epoch in self._read_sealed()

    # -- session / pointer io --------------------------------------------------

    def _session_dir(self, session_token: str) -> Path:
        return self.sessions_directory / session_token

    def _pointer_path(self, session_token: str) -> Path:
        return self._session_dir(session_token) / "pointer"

    @staticmethod
    def _is_digest(value: object) -> bool:
        return (
            type(value) is str
            and len(value) == 64
            and value == value.lower()
            and all(character in "0123456789abcdef" for character in value)
        )

    @staticmethod
    def _validate_journal_reference(value: object, session_token: str) -> str:
        if type(value) is not str:
            raise RepositoryCorruptionError("pointer journal reference is not text")
        match = _JOURNAL_REFERENCE_PATTERN.fullmatch(value)
        if match is None or match.group(1) != session_token:
            raise RepositoryCorruptionError(
                "pointer journal reference is not canonical for its session"
            )
        return value

    def _load_pointer(self, session_token: str) -> StatePointer | None:
        path = self._pointer_path(session_token)
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise RepositoryCorruptionError("pointer is unreadable") from exc
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise RepositoryCorruptionError("pointer is invalid JSON") from exc
        expected_fields = {
            "session_token",
            "state_generation_id",
            "revision",
            "payload_digest",
            "journal_digest",
            "current_journal",
            "previous_journal",
            "previous_journal_digest",
            "last_committed_turn_id",
            "last_committed_turn_sequence",
        }
        if type(data) is not dict or set(data) != expected_fields:
            raise RepositoryCorruptionError("pointer has an invalid envelope")
        try:
            canonical = canonical_json_bytes(data)
        except (TypeError, ValueError) as exc:
            raise RepositoryCorruptionError("pointer is not canonicalizable") from exc
        if raw != canonical:
            raise RepositoryCorruptionError("pointer is not canonical")
        if data["session_token"] != session_token:
            raise RepositoryCorruptionError("pointer session token does not match its namespace")
        generation = data["state_generation_id"]
        revision = data["revision"]
        last_turn_id = data["last_committed_turn_id"]
        if type(generation) is not str or not generation:
            raise RepositoryCorruptionError("pointer generation is invalid")
        if type(revision) is not int or revision < 0:
            raise RepositoryCorruptionError("pointer revision is invalid")
        if type(last_turn_id) is not str or not last_turn_id:
            raise RepositoryCorruptionError("pointer turn id is invalid")
        if not self._is_digest(data["payload_digest"]):
            raise RepositoryCorruptionError("pointer payload digest is invalid")
        if not self._is_digest(data["journal_digest"]):
            raise RepositoryCorruptionError("pointer journal digest is invalid")
        current_journal = self._validate_journal_reference(
            data["current_journal"], session_token
        )
        previous_journal = data["previous_journal"]
        previous_digest = data["previous_journal_digest"]
        if previous_journal is None:
            if previous_digest is not None:
                raise RepositoryCorruptionError("pointer previous journal digest is orphaned")
        else:
            previous_journal = self._validate_journal_reference(previous_journal, session_token)
            if previous_journal == current_journal or not self._is_digest(previous_digest):
                raise RepositoryCorruptionError("pointer previous journal is invalid")
        sequence_data = data["last_committed_turn_sequence"]
        if type(sequence_data) is not dict or set(sequence_data) != {
            "writer_epoch",
            "local_sequence",
        }:
            raise RepositoryCorruptionError("pointer turn sequence is invalid")
        writer_epoch = sequence_data["writer_epoch"]
        local_sequence = sequence_data["local_sequence"]
        if type(writer_epoch) is not int or type(local_sequence) is not int:
            raise RepositoryCorruptionError("pointer turn sequence is invalid")
        try:
            sequence = TurnSequence(writer_epoch, local_sequence)
        except (TypeError, ValueError) as exc:
            raise RepositoryCorruptionError("pointer turn sequence is invalid") from exc
        return StatePointer(
            session_token=session_token,
            state_generation_id=generation,
            revision=revision,
            payload_digest=data["payload_digest"],
            journal_digest=data["journal_digest"],
            current_journal=current_journal,
            previous_journal=previous_journal,
            previous_journal_digest=previous_digest,
            last_committed_turn_id=last_turn_id,
            last_committed_turn_sequence=sequence,
        )

    def _pointer_bytes(self, pointer: StatePointer) -> bytes:
        return canonical_json_bytes(
            {
                "session_token": pointer.session_token,
                "state_generation_id": pointer.state_generation_id,
                "revision": pointer.revision,
                "payload_digest": pointer.payload_digest,
                "journal_digest": pointer.journal_digest,
                "current_journal": pointer.current_journal,
                "previous_journal": pointer.previous_journal,
                "previous_journal_digest": pointer.previous_journal_digest,
                "last_committed_turn_id": pointer.last_committed_turn_id,
                "last_committed_turn_sequence": {
                    "writer_epoch": pointer.last_committed_turn_sequence.writer_epoch,
                    "local_sequence": pointer.last_committed_turn_sequence.local_sequence,
                },
            }
        )

    @staticmethod
    def _journal_bytes(record: JournalRecord) -> bytes:
        return canonical_json_bytes(
            {
                "schema_version": record.schema_version,
                "formula_version": record.formula_version,
                "source_digest": record.source_digest,
                "state_generation_id": record.state_generation_id,
                "revision": record.revision,
                "writer_epoch": record.writer_epoch,
                "session_generation": record.session_generation,
                "model_revision": record.model_revision,
                "last_committed_turn_sequence": {
                    "writer_epoch": record.last_committed_turn_sequence.writer_epoch,
                    "local_sequence": record.last_committed_turn_sequence.local_sequence,
                },
                "last_committed_turn_id": record.last_committed_turn_id,
                "cognitive_payload": record.cognitive_payload,
                "deterministic_trace": record.deterministic_trace,
            }
        )

    def _verified_payload(self, pointer: StatePointer) -> bytes:
        """Load the current journal only after its pointer contract fully agrees."""

        try:
            raw = (self.root / pointer.current_journal).read_bytes()
        except OSError as exc:
            raise RepositoryCorruptionError("current journal is unreadable") from exc
        if canonical_sha256_of_bytes(raw) != pointer.journal_digest:
            raise RepositoryCorruptionError("current journal digest does not match pointer")
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise RepositoryCorruptionError("current journal is invalid JSON") from exc
        expected_fields = {
            "schema_version",
            "formula_version",
            "source_digest",
            "state_generation_id",
            "revision",
            "writer_epoch",
            "session_generation",
            "model_revision",
            "last_committed_turn_sequence",
            "last_committed_turn_id",
            "cognitive_payload",
            "deterministic_trace",
        }
        if type(data) is not dict or set(data) != expected_fields:
            raise RepositoryCorruptionError("current journal has an invalid envelope")
        try:
            if raw != canonical_json_bytes(data):
                raise RepositoryCorruptionError("current journal is not canonical")
            payload = canonical_json_bytes(data["cognitive_payload"])
        except (TypeError, ValueError) as exc:
            raise RepositoryCorruptionError("current journal is not canonicalizable") from exc
        if data["state_generation_id"] != pointer.state_generation_id:
            raise RepositoryCorruptionError("journal generation does not match pointer")
        if type(data["revision"]) is not int or data["revision"] != pointer.revision:
            raise RepositoryCorruptionError("journal revision does not match pointer")
        if payload_digest(data["cognitive_payload"]) != pointer.payload_digest:
            raise RepositoryCorruptionError("journal payload digest does not match pointer")
        if data["last_committed_turn_id"] != pointer.last_committed_turn_id:
            raise RepositoryCorruptionError("journal turn id does not match pointer")
        sequence = data["last_committed_turn_sequence"]
        if type(sequence) is not dict or sequence != {
            "writer_epoch": pointer.last_committed_turn_sequence.writer_epoch,
            "local_sequence": pointer.last_committed_turn_sequence.local_sequence,
        }:
            raise RepositoryCorruptionError("journal turn sequence does not match pointer")
        writer_epoch = data["writer_epoch"]
        if (
            type(writer_epoch) is not int
            or writer_epoch < pointer.last_committed_turn_sequence.writer_epoch
        ):
            raise RepositoryCorruptionError(
                "journal writer epoch predates the committed high-watermark"
            )
        return payload

    # -- reads -----------------------------------------------------------------

    def load(self, session_ref: SessionRef) -> StateSnapshot | None:
        """Return the current committed snapshot for a session, or None if absent."""

        token = session_filename_token(session_ref)
        pointer = self._load_pointer(token)
        if pointer is None:
            return None
        try:
            payload = self._verified_payload(pointer)
        except RepositoryCorruptionError:
            return None
        return StateSnapshot(pointer=pointer, canonical_cognitive_payload=payload)

    def usage_bytes(self) -> int:
        """Total bytes currently occupied under the repository root."""

        total = 0
        for path in self.root.rglob("*"):
            if path.is_file():
                try:
                    total += path.stat().st_size
                except OSError:  # pragma: no cover - race with concurrent delete
                    continue
        return total

    # -- writes ----------------------------------------------------------------

    def write_seed_anchor(
        self,
        session_token: str,
        generation_id: str,
        data: bytes,
    ) -> None:
        """Atomically publish one framed seed anchor under the repository budget."""

        if type(session_token) is not str or not session_token:
            raise TypeError("session_token must be non-empty str")
        if type(generation_id) is not str or not generation_id:
            raise TypeError("generation_id must be non-empty str")
        if type(data) is not bytes:
            raise TypeError("seed anchor data must have exact type bytes")
        directory = self.root / "anchors" / session_token
        destination = directory / f"{generation_id}.anchor"
        with self._repository_lock():
            directory.mkdir(parents=True, exist_ok=True)
            self._reserve_peak(len(data), operation="seed anchor")
            staged = self._write_bytes_durable(data)
            self._atomic_replace(staged, destination)
            self._fsync_dir(directory)

    def remove_seed_anchor_if_unreferenced(
        self,
        session_token: str,
        generation_id: str,
    ) -> bool:
        """Durably remove a losing anchor unless it is the published generation.

        Migration writes the immutable anchor before publishing its pointer.  A CAS
        loser must therefore re-check the authoritative pointer under the repository
        lock before rollback; a direct unlink could race another process and remove
        the winner's seed.
        """

        if type(session_token) is not str or not session_token:
            raise TypeError("session_token must be non-empty str")
        if type(generation_id) is not str or not generation_id:
            raise TypeError("generation_id must be non-empty str")
        directory = self.root / "anchors" / session_token
        destination = directory / f"{generation_id}.anchor"
        with self._repository_lock():
            pointer = self._load_pointer(session_token)
            if pointer is not None and pointer.state_generation_id == generation_id:
                return False
            try:
                destination.unlink()
            except OSError:  # already gone or best-effort cleanup unavailable
                return False
            self._fsync_dir(directory)
            return True

    def clean_seed_anchors(self, session_token: str) -> int:
        """Keep only the anchor named by the lock-held current pointer.

        With no pointer every anchor is a pre-publication orphan.  Pointer discovery,
        unlink and the directory durability barrier share one mutation fence, so
        recovery cannot delete an anchor concurrently being published by migration.
        """

        if type(session_token) is not str or not session_token:
            raise TypeError("session_token must be non-empty str")
        directory = self.root / "anchors" / session_token
        with self._repository_lock():
            pointer = self._load_pointer(session_token)
            keep = pointer.state_generation_id if pointer is not None else None
            if not directory.exists():
                return 0
            removed = 0
            for path in directory.glob("*.anchor"):
                if keep is not None and path.stem == keep:
                    continue
                try:
                    path.unlink()
                    removed += 1
                except OSError:  # pragma: no cover - already gone / best effort
                    pass
            if removed:
                self._fsync_dir(directory)
            return removed

    def compare_and_commit(
        self,
        session_ref: SessionRef,
        precondition: CommitPrecondition | AbsentState,
        record: JournalRecord,
    ) -> CommitResult:
        """Atomically advance a session's state iff the pinned base still matches disk."""

        token = session_filename_token(session_ref)
        with self._repository_lock():
            if self._epoch_is_fenced(record.writer_epoch):
                return CommitResult.STALE_EPOCH

            current = self._load_pointer(token)

            if isinstance(precondition, AbsentState):
                if current is not None:
                    # Genesis idempotency only within the SAME generation: a bare turn_id
                    # match across a different lineage is ALREADY_MIGRATED, not a duplicate.
                    if (
                        current.state_generation_id == record.state_generation_id
                        and current.last_committed_turn_id == record.last_committed_turn_id
                    ):
                        return CommitResult.DUPLICATE_TURN
                    return CommitResult.ALREADY_MIGRATED
                return self._commit_record(token, record, previous=None)

            if current is None:
                return CommitResult.STALE_STATE_GENERATION
            if precondition.expected_state_generation_id != current.state_generation_id:
                return CommitResult.STALE_STATE_GENERATION
            # Base integrity BEFORE trusting the pinned revision/digest.
            if not self._base_journal_intact(current):
                return CommitResult.CORRUPT_BASE
            # Idempotent retry of the exact turn already at the head → duplicate success,
            # but only after proving that head is intact and in the lineage the writer
            # pinned. Otherwise a corrupt or quarantined head could hide a dropped write.
            if current.last_committed_turn_id == record.last_committed_turn_id:
                return CommitResult.DUPLICATE_TURN
            if precondition.expected_revision != current.revision:
                return CommitResult.REVISION_CONFLICT
            if precondition.expected_payload_digest != current.payload_digest:
                return CommitResult.BASE_DIGEST_MISMATCH
            if record.last_committed_turn_sequence <= current.last_committed_turn_sequence:
                return CommitResult.STALE_SEQUENCE

            return self._commit_record(token, record, previous=current)

    def quarantine_and_replace(
        self, old_pointer: StatePointer, replacement: JournalRecord
    ) -> StateSnapshot:
        """Fence the current lineage and publish a fresh generation as the new head.

        Any delayed writer still pinning ``old_pointer``'s generation will subsequently
        fail with ``STALE_STATE_GENERATION`` (ABA protection): the head no longer carries
        that generation id even though the revision counter may coincide.

        This is a recovery primitive: unlike :meth:`compare_and_commit` it has no epoch
        gate, but publication remains an exact pointer CAS. A caller that inspected an
        older head cannot overwrite an intervening commit or quarantine.
        """

        token = old_pointer.session_token
        with self._repository_lock():
            current = self._load_pointer(token)
            if current is None or current != old_pointer:
                raise RepositoryCASConflict("repository pointer changed before quarantine")
            if replacement.state_generation_id == old_pointer.state_generation_id:
                raise ValueError("quarantine replacement must allocate a new generation")
            if (
                replacement.last_committed_turn_sequence
                < old_pointer.last_committed_turn_sequence
            ):
                raise ValueError("quarantine replacement cannot lower the turn high-watermark")
            result = self._commit_record(token, replacement, previous=current)
            if result is not CommitResult.COMMITTED:
                raise RepositoryCorruptionError("quarantine replacement was not committed")
            published = self._load_pointer(token)
            if published is None:
                raise RepositoryCorruptionError("quarantine pointer disappeared after publish")
            payload = self._verified_payload(published)
            return StateSnapshot(
                pointer=published,
                canonical_cognitive_payload=payload,
            )

    def load_by_token(self, session_token: str) -> StateSnapshot | None:
        pointer = self._load_pointer(session_token)
        if pointer is None:
            return None
        try:
            payload = self._verified_payload(pointer)
        except RepositoryCorruptionError:
            return None
        return StateSnapshot(pointer=pointer, canonical_cognitive_payload=payload)

    def _base_journal_intact(self, pointer: StatePointer) -> bool:
        try:
            self._verified_payload(pointer)
        except RepositoryCorruptionError:
            return False
        return True

    def _reserve_peak(self, staging_bytes: int, *, operation: str) -> None:
        """Admit an operation only if its exact lock-held file peak fits the cap."""

        projected = self.usage_bytes() + staging_bytes
        if projected > self._hard_limit_bytes:
            raise RepositoryBudgetExceeded(
                f"{operation} would peak at {projected} bytes over hard limit "
                f"{self._hard_limit_bytes}"
            )

    def _plan_commit(
        self,
        session_token: str,
        record: JournalRecord,
        *,
        previous: StatePointer | None,
    ) -> _CommitPlan:
        self._fault(FaultPoint.BEFORE_SERIALIZE)
        journal_bytes = self._journal_bytes(record)
        journal_digest = canonical_sha256_of_bytes(journal_bytes)
        pdigest = payload_digest(record.cognitive_payload)
        journal_name = f"rev{record.revision:012d}-{os.urandom(8).hex()}.journal"
        journal_rel = f"sessions/{session_token}/{journal_name}"
        pointer = StatePointer(
            session_token=session_token,
            state_generation_id=record.state_generation_id,
            revision=record.revision,
            payload_digest=pdigest,
            journal_digest=journal_digest,
            current_journal=journal_rel,
            previous_journal=previous.current_journal if previous is not None else None,
            previous_journal_digest=(
                previous.journal_digest if previous is not None else None
            ),
            last_committed_turn_id=record.last_committed_turn_id,
            last_committed_turn_sequence=record.last_committed_turn_sequence,
        )
        pointer_bytes = self._pointer_bytes(pointer)
        self._fault(FaultPoint.AFTER_SERIALIZE)
        return _CommitPlan(
            journal_name=journal_name,
            journal_bytes=journal_bytes,
            pointer=pointer,
            pointer_bytes=pointer_bytes,
        )

    def _commit_record(
        self,
        session_token: str,
        record: JournalRecord,
        *,
        previous: StatePointer | None,
    ) -> CommitResult:
        session_dir = self._session_dir(session_token)
        session_dir.mkdir(parents=True, exist_ok=True)
        plan = self._plan_commit(session_token, record, previous=previous)
        # Existing current+previous journals, pointer, anchors, telemetry, lock and
        # orphan staging are already included by usage_bytes(). During publication the
        # exact additional peak is the new journal plus the staged replacement pointer.
        self._reserve_peak(
            len(plan.journal_bytes) + len(plan.pointer_bytes),
            operation="state commit",
        )

        staged_journal = self._write_bytes_durable(plan.journal_bytes)
        self._fault(FaultPoint.BEFORE_REPLACE)
        self._atomic_replace(staged_journal, session_dir / plan.journal_name)
        self._fault(FaultPoint.AFTER_REPLACE)
        # Persist the new journal's directory entry BEFORE the pointer can name it, so a
        # power loss can never leave the published pointer referencing an unpersisted file.
        self._fsync_dir(session_dir)

        staged_pointer = self._write_bytes_durable(plan.pointer_bytes)
        self._fault(FaultPoint.BEFORE_POINTER_PUBLISH)
        self._atomic_replace(staged_pointer, self._pointer_path(session_token))
        self._fault(FaultPoint.AFTER_POINTER_PUBLISH)
        self._fsync_dir(session_dir)

        # Retention: keep only current + previous. The journal that fell two behind the
        # new head is now unreferenced and safe to delete (publication already succeeded).
        if previous is not None and previous.previous_journal is not None:
            stale = self.root / previous.previous_journal
            try:
                stale.unlink()
            except OSError:  # pragma: no cover - already gone
                pass
        return CommitResult.COMMITTED

    # -- recovery --------------------------------------------------------------

    def recover_orphans(self) -> int:
        """Remove staging leftovers and unreferenced journals; return count removed."""

        removed = 0
        with self._repository_lock():
            for path in self.staging_directory.glob("*"):
                if path.is_file():
                    try:
                        path.unlink()
                        removed += 1
                    except OSError:  # pragma: no cover
                        pass
            for session_dir in self.sessions_directory.glob("*"):
                if not session_dir.is_dir():
                    continue
                pointer = self._load_pointer(session_dir.name)
                referenced: set[str] = set()
                if pointer is not None:
                    referenced.add((self.root / pointer.current_journal).name)
                    if pointer.previous_journal is not None:
                        referenced.add((self.root / pointer.previous_journal).name)
                for journal in session_dir.glob("*.journal"):
                    if journal.name not in referenced:
                        try:
                            journal.unlink()
                            removed += 1
                        except OSError:  # pragma: no cover
                            pass
        return removed


def canonical_sha256_of_bytes(data: bytes) -> str:
    """SHA-256 hex of raw bytes (journal-file integrity, distinct from payload digest)."""

    return hashlib.sha256(data).hexdigest()


__all__ = [
    "AbsentState",
    "CommitPrecondition",
    "CommitResult",
    "FaultPoint",
    "JournalRecord",
    "RepositoryBudgetExceeded",
    "RepositoryCASConflict",
    "RepositoryCorruptionError",
    "StatePointer",
    "StateRepository",
    "StateSnapshot",
    "payload_digest",
]
