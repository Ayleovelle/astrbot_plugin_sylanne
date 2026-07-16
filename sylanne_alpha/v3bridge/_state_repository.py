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
import os
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

from sylanne_alpha.v3bridge.session_identity import session_filename_token
from sylanne_alpha.v3core.canonical import canonical_json_bytes, canonical_sha256
from sylanne_alpha.v3core.contracts import SessionRef, TurnSequence

try:  # POSIX advisory locking
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - Windows
    _fcntl = None

try:  # Windows byte-range locking
    import msvcrt as _msvcrt
except ImportError:  # pragma: no cover - POSIX
    _msvcrt = None


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


def payload_digest(cognitive_payload: object) -> str:
    """Digest ONLY the canonicalized cognitive payload (order/field independent)."""

    return canonical_sha256(cognitive_payload)


# ---------------------------------------------------------------------------
# Inter-process lock (single writer across OS processes, cross-platform)
# ---------------------------------------------------------------------------


class _InterProcessLock:
    """Blocking exclusive lock on a lock file; serializes all repo mutations.

    NOT re-entrant: every ``__enter__`` opens a fresh fd, so a nested acquire inside the
    same process would self-deadlock on POSIX. All mutating methods take it exactly once
    and never call another locked method while holding it — keep that invariant.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._fd: int | None = None

    def __enter__(self) -> "_InterProcessLock":
        self._fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o600)
        if _msvcrt is not None:  # pragma: no cover - platform specific
            while True:
                try:
                    os.lseek(self._fd, 0, os.SEEK_SET)
                    _msvcrt.locking(self._fd, _msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    time.sleep(0.01)
        elif _fcntl is not None:  # pragma: no cover - platform specific
            _fcntl.flock(self._fd, _fcntl.LOCK_EX)
        return self

    def __exit__(self, *_exc: object) -> None:
        fd = self._fd
        if fd is None:
            return
        try:
            if _msvcrt is not None:  # pragma: no cover - platform specific
                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    _msvcrt.locking(fd, _msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            elif _fcntl is not None:  # pragma: no cover - platform specific
                _fcntl.flock(fd, _fcntl.LOCK_UN)
        finally:
            os.close(fd)
            self._fd = None


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class StateRepository:
    """Durable, CAS-guarded, epoch-fenced journal store for one bridge data root."""

    def __init__(
        self,
        root: object,
        *,
        fault_injector: Callable[[FaultPoint], None] | None = None,
        replace_attempts: int = 8,
        replace_retry_seconds: float = 0.05,
        hard_limit_bytes: int | None = None,
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
        self._hard_limit_bytes = hard_limit_bytes
        self.root.mkdir(parents=True, exist_ok=True)
        self.sessions_directory.mkdir(parents=True, exist_ok=True)
        self.staging_directory.mkdir(parents=True, exist_ok=True)

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
        """Durability barrier for a rename: on POSIX the parent directory entry is only
        persisted once the directory itself is fsync'd. Best-effort — Windows has no
        directory fsync and simply raises, which is fine (os.replace is already durable
        there)."""

        try:
            dir_fd = os.open(directory, os.O_RDONLY)
        except OSError:  # pragma: no cover - directory vanished
            return
        try:
            os.fsync(dir_fd)
        except OSError:  # pragma: no cover - Windows / unsupported
            pass
        finally:
            os.close(dir_fd)

    def _write_bytes_durable(self, data: bytes) -> Path:
        """Serialize bytes into a fresh staging file with a full write + fsync barrier,
        honoring the injectable fault points."""

        staging = self.staging_directory / f"{os.urandom(8).hex()}.stage"
        self._fault(FaultPoint.BEFORE_SERIALIZE)
        fd = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            # os.write may deliver fewer bytes than requested; loop until fully written so
            # a short write can never truncate the staged bytes under the pointer digest.
            view = memoryview(data)
            offset = 0
            while offset < len(view):
                offset += os.write(fd, view[offset:])
            self._fault(FaultPoint.AFTER_SERIALIZE)
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
            return int(path.read_text("ascii").strip() or "0")
        except (OSError, ValueError):
            return 0

    def current_epoch(self) -> int:
        """Return the highest allocated epoch (0 if none), without allocating."""

        return self._read_int(self._epoch_path)

    def acquire_epoch(self) -> int:
        """Allocate the next strictly-increasing epoch, unique across all processes."""

        with _InterProcessLock(self._lock_path):
            nxt = self._read_int(self._epoch_path) + 1
            staged = self._write_bytes_durable(str(nxt).encode("ascii"))
            self._atomic_replace(staged, self._epoch_path)
            self._fsync_dir(self.root)
            return nxt

    def seal_epoch(self, epoch: int) -> None:
        """Fence an epoch so even its own writers can no longer commit."""

        with _InterProcessLock(self._lock_path):
            sealed = self._read_sealed()
            sealed.add(int(epoch))
            payload = canonical_json_bytes({"sealed": sorted(sealed)})
            staged = self._write_bytes_durable(payload)
            self._atomic_replace(staged, self._sealed_path)
            self._fsync_dir(self.root)

    def _read_sealed(self) -> set[int]:
        try:
            raw = self._sealed_path.read_bytes()
        except OSError:
            return set()
        try:

            data = json.loads(raw.decode("utf-8"))
            return {int(item) for item in data.get("sealed", [])}
        except (ValueError, AttributeError, TypeError):
            return set()

    def _epoch_is_fenced(self, writer_epoch: int) -> bool:
        return writer_epoch < self.current_epoch() or writer_epoch in self._read_sealed()

    # -- session / pointer io --------------------------------------------------

    def _session_dir(self, session_token: str) -> Path:
        return self.sessions_directory / session_token

    def _pointer_path(self, session_token: str) -> Path:
        return self._session_dir(session_token) / "pointer"

    def _load_pointer(self, session_token: str) -> StatePointer | None:
        path = self._pointer_path(session_token)
        try:
            raw = path.read_bytes()
        except OSError:
            return None
        try:

            data = json.loads(raw.decode("utf-8"))
            seq = data["last_committed_turn_sequence"]
            return StatePointer(
                session_token=data["session_token"],
                state_generation_id=data["state_generation_id"],
                revision=int(data["revision"]),
                payload_digest=data["payload_digest"],
                journal_digest=data["journal_digest"],
                current_journal=data["current_journal"],
                previous_journal=data.get("previous_journal"),
                previous_journal_digest=data.get("previous_journal_digest"),
                last_committed_turn_id=data["last_committed_turn_id"],
                last_committed_turn_sequence=TurnSequence(
                    int(seq["writer_epoch"]), int(seq["local_sequence"])
                ),
            )
        except (ValueError, KeyError, TypeError):
            return None

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

    def _canonical_payload_of_journal(self, journal_rel: str) -> bytes | None:
        """Read a journal, verify nothing else, return canonical cognitive payload bytes."""

        try:
            raw = (self.root / journal_rel).read_bytes()

            data = json.loads(raw.decode("utf-8"))
            return canonical_json_bytes(data["cognitive_payload"])
        except (OSError, ValueError, KeyError, TypeError):
            return None

    # -- reads -----------------------------------------------------------------

    def load(self, session_ref: SessionRef) -> StateSnapshot | None:
        """Return the current committed snapshot for a session, or None if absent."""

        token = session_filename_token(session_ref)
        pointer = self._load_pointer(token)
        if pointer is None:
            return None
        payload = self._canonical_payload_of_journal(pointer.current_journal)
        if payload is None:
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

    def compare_and_commit(
        self,
        session_ref: SessionRef,
        precondition: CommitPrecondition | AbsentState,
        record: JournalRecord,
    ) -> CommitResult:
        """Atomically advance a session's state iff the pinned base still matches disk."""

        token = session_filename_token(session_ref)
        with _InterProcessLock(self._lock_path):
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
                self._reserve_budget(record)
                return self._commit_record(token, record, previous=None)

            if current is None:
                return CommitResult.STALE_STATE_GENERATION
            # Idempotent retry of the exact turn already at the head → duplicate success —
            # but ONLY within the lineage the writer pinned. A turn_id that coincides across
            # a different generation (e.g. quarantine reused it) must NOT read as a duplicate,
            # or a stale writer would falsely conclude its distinct write landed and stop
            # retrying, silently dropping state. Fall through to STALE_STATE_GENERATION.
            if (
                precondition.expected_state_generation_id == current.state_generation_id
                and current.last_committed_turn_id == record.last_committed_turn_id
            ):
                return CommitResult.DUPLICATE_TURN
            if precondition.expected_state_generation_id != current.state_generation_id:
                return CommitResult.STALE_STATE_GENERATION
            # Base integrity BEFORE trusting the pinned revision/digest.
            if not self._base_journal_intact(current):
                return CommitResult.CORRUPT_BASE
            if precondition.expected_revision != current.revision:
                return CommitResult.REVISION_CONFLICT
            if precondition.expected_payload_digest != current.payload_digest:
                return CommitResult.BASE_DIGEST_MISMATCH
            if record.last_committed_turn_sequence <= current.last_committed_turn_sequence:
                return CommitResult.STALE_SEQUENCE

            self._reserve_budget(record)
            return self._commit_record(token, record, previous=current)

    def quarantine_and_replace(
        self, old_pointer: StatePointer, replacement: JournalRecord
    ) -> StateSnapshot:
        """Fence the current lineage and publish a fresh generation as the new head.

        Any delayed writer still pinning ``old_pointer``'s generation will subsequently
        fail with ``STALE_STATE_GENERATION`` (ABA protection): the head no longer carries
        that generation id even though the revision counter may coincide.

        This is a recovery primitive: unlike :meth:`compare_and_commit` it publishes the
        replacement UNCONDITIONALLY (no epoch/precondition gate), so callers own the
        decision to overwrite. It still runs under the inter-process lock and honors the
        byte budget.
        """

        token = old_pointer.session_token
        with _InterProcessLock(self._lock_path):
            current = self._load_pointer(token)
            self._reserve_budget(replacement)
            self._commit_record(token, replacement, previous=current)
            snapshot = self.load_by_token(token)
            assert snapshot is not None
            return snapshot

    def load_by_token(self, session_token: str) -> StateSnapshot | None:
        pointer = self._load_pointer(session_token)
        if pointer is None:
            return None
        payload = self._canonical_payload_of_journal(pointer.current_journal)
        if payload is None:  # pragma: no cover - freshly published journal is intact
            return None
        return StateSnapshot(pointer=pointer, canonical_cognitive_payload=payload)

    def _base_journal_intact(self, pointer: StatePointer) -> bool:
        try:
            raw = (self.root / pointer.current_journal).read_bytes()
        except OSError:
            return False
        if canonical_sha256_of_bytes(raw) != pointer.journal_digest:
            return False
        try:
            json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return False
        return True

    def _reserve_budget(self, record: JournalRecord) -> None:
        if self._hard_limit_bytes is None:
            return
        projected = self.usage_bytes() + len(self._journal_bytes(record))
        if projected > self._hard_limit_bytes:
            raise RepositoryBudgetExceeded(
                f"commit would use {projected} bytes over hard limit {self._hard_limit_bytes}"
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

        journal_bytes = self._journal_bytes(record)
        journal_digest = canonical_sha256_of_bytes(journal_bytes)
        pdigest = payload_digest(record.cognitive_payload)
        journal_name = f"rev{record.revision:012d}-{os.urandom(8).hex()}.journal"
        journal_rel = f"sessions/{session_token}/{journal_name}"

        staged_journal = self._write_bytes_durable(journal_bytes)
        self._fault(FaultPoint.BEFORE_REPLACE)
        self._atomic_replace(staged_journal, session_dir / journal_name)
        self._fault(FaultPoint.AFTER_REPLACE)
        # Persist the new journal's directory entry BEFORE the pointer can name it, so a
        # power loss can never leave the published pointer referencing an unpersisted file.
        self._fsync_dir(session_dir)

        pointer = StatePointer(
            session_token=session_token,
            state_generation_id=record.state_generation_id,
            revision=record.revision,
            payload_digest=pdigest,
            journal_digest=journal_digest,
            current_journal=journal_rel,
            previous_journal=previous.current_journal if previous is not None else None,
            previous_journal_digest=previous.journal_digest if previous is not None else None,
            last_committed_turn_id=record.last_committed_turn_id,
            last_committed_turn_sequence=record.last_committed_turn_sequence,
        )
        staged_pointer = self._write_bytes_durable(self._pointer_bytes(pointer))
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
        with _InterProcessLock(self._lock_path):
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
    "StatePointer",
    "StateRepository",
    "StateSnapshot",
    "payload_digest",
]
