from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import sylanne_alpha.v3bridge._state_repository as repository_module
from sylanne_alpha.v3bridge._state_repository import (
    AbsentState,
    CommitPrecondition,
    CommitResult,
    FaultPoint,
    JournalRecord,
    StateRepository,
    payload_digest,
)
from sylanne_alpha.v3bridge.session_identity import SessionIdentityKey
from sylanne_alpha.v3core.canonical import canonical_json_bytes
from sylanne_alpha.v3core.contracts import SessionRef, TurnSequence


_IDENTITY = SessionIdentityKey(key_id="repository-v1", secret=b"r" * 32)


def _session(name: str = "umo-1") -> SessionRef:
    ref = _IDENTITY.session_ref("qq", name, session_generation=0)
    assert ref is not None
    return ref


def _record(
    *,
    generation: str,
    revision: int,
    epoch: int,
    turn_id: str,
    sequence: int,
    payload: object | None = None,
    trace: object | None = None,
) -> JournalRecord:
    return JournalRecord(
        schema_version=1,
        formula_version="formula-v1",
        source_digest="a" * 64,
        state_generation_id=generation,
        revision=revision,
        writer_epoch=epoch,
        session_generation=0,
        model_revision="model-v1",
        last_committed_turn_sequence=TurnSequence(epoch, sequence),
        last_committed_turn_id=turn_id,
        cognitive_payload={"value": revision} if payload is None else payload,
        deterministic_trace={"turn": turn_id} if trace is None else trace,
    )


def _create(
    repo: StateRepository,
    session_ref: SessionRef,
    record: JournalRecord,
):
    assert repo.compare_and_commit(session_ref, AbsentState(), record) is CommitResult.COMMITTED
    snapshot = repo.load(session_ref)
    assert snapshot is not None
    return snapshot


def _precondition(snapshot, record: JournalRecord) -> CommitPrecondition:
    return CommitPrecondition(
        writer_epoch=record.writer_epoch,
        expected_state_generation_id=snapshot.pointer.state_generation_id,
        expected_revision=snapshot.pointer.revision,
        expected_payload_digest=snapshot.pointer.payload_digest,
        turn_id=record.last_committed_turn_id,
        turn_sequence=record.last_committed_turn_sequence,
    )


def test_commit_result_vocabulary_is_frozen_and_complete() -> None:
    assert {item.value for item in CommitResult} == {
        "COMMITTED",
        "ALREADY_MIGRATED",
        "DUPLICATE_TURN",
        "STALE_EPOCH",
        "STALE_STATE_GENERATION",
        "REVISION_CONFLICT",
        "BASE_DIGEST_MISMATCH",
        "STALE_SEQUENCE",
        "CORRUPT_BASE",
    }


def test_payload_digest_hashes_only_canonical_cognitive_payload(tmp_path: Path) -> None:
    repo = StateRepository(tmp_path)
    epoch = repo.acquire_epoch()
    cognitive_payload = {"z": [3, 2, 1], "a": {"finite": 0.25}}
    first = _record(
        generation="1" * 32,
        revision=0,
        epoch=epoch,
        turn_id="turn-a",
        sequence=1,
        payload=cognitive_payload,
        trace={"trace": "first"},
    )
    second = _record(
        generation="2" * 32,
        revision=99,
        epoch=epoch,
        turn_id="turn-b",
        sequence=7,
        payload={"a": {"finite": 0.25}, "z": [3, 2, 1]},
        trace={"trace": "different", "metadata": [1, 2, 3]},
    )

    first_snapshot = _create(repo, _session("digest-a"), first)
    second_snapshot = _create(repo, _session("digest-b"), second)

    assert first_snapshot.pointer.payload_digest == second_snapshot.pointer.payload_digest
    assert first_snapshot.pointer.payload_digest == payload_digest(cognitive_payload)
    assert "payload_digest" not in first_snapshot.canonical_cognitive_payload.decode("ascii")


def test_compare_and_commit_has_one_cas_winner(tmp_path: Path) -> None:
    repo = StateRepository(tmp_path)
    epoch = repo.acquire_epoch()
    base = _record(
        generation="a" * 32,
        revision=0,
        epoch=epoch,
        turn_id="turn-1",
        sequence=1,
    )
    snapshot = _create(repo, _session("cas"), base)
    first = _record(
        generation="a" * 32,
        revision=1,
        epoch=epoch,
        turn_id="turn-2a",
        sequence=2,
    )
    second = _record(
        generation="a" * 32,
        revision=1,
        epoch=epoch,
        turn_id="turn-2b",
        sequence=3,
    )

    assert (
        repo.compare_and_commit(_session("cas"), _precondition(snapshot, first), first)
        is CommitResult.COMMITTED
    )
    assert (
        repo.compare_and_commit(_session("cas"), _precondition(snapshot, second), second)
        is CommitResult.REVISION_CONFLICT
    )


def test_retry_after_pointer_publication_is_duplicate_turn(tmp_path: Path) -> None:
    repo = StateRepository(tmp_path)
    epoch = repo.acquire_epoch()
    snapshot = _create(
        repo,
        _session(),
        _record(
            generation="a" * 32,
            revision=0,
            epoch=epoch,
            turn_id="turn-1",
            sequence=1,
        ),
    )
    next_record = _record(
        generation="a" * 32,
        revision=1,
        epoch=epoch,
        turn_id="turn-2",
        sequence=2,
    )
    precondition = _precondition(snapshot, next_record)

    assert repo.compare_and_commit(_session(), precondition, next_record) is CommitResult.COMMITTED
    assert (
        repo.compare_and_commit(_session(), precondition, next_record)
        is CommitResult.DUPLICATE_TURN
    )


def test_old_generation_cannot_commit_after_quarantine_aba(tmp_path: Path) -> None:
    repo = StateRepository(tmp_path)
    epoch = repo.acquire_epoch()
    old = _create(
        repo,
        _session(),
        _record(
            generation="a" * 32,
            revision=0,
            epoch=epoch,
            turn_id="turn-1",
            sequence=1,
        ),
    )
    delayed = _record(
        generation="a" * 32,
        revision=1,
        epoch=epoch,
        turn_id="turn-2",
        sequence=2,
    )
    replacement = repo.quarantine_and_replace(
        old.pointer,
        _record(
            generation="b" * 32,
            revision=0,
            epoch=epoch,
            turn_id="turn-1",
            sequence=1,
            payload={"recovered": True},
        ),
    )

    assert replacement.pointer.state_generation_id != old.pointer.state_generation_id
    assert (
        repo.compare_and_commit(_session(), _precondition(old, delayed), delayed)
        is CommitResult.STALE_STATE_GENERATION
    )


def test_reused_turn_id_across_generation_is_not_duplicate(tmp_path: Path) -> None:
    """Red-team F2: after quarantine reuses a turn_id under a NEW generation, a stale
    writer pinning the OLD generation and retrying that same turn_id must be fenced with
    STALE_STATE_GENERATION — never a false DUPLICATE_TURN that would hide a dropped write."""
    repo = StateRepository(tmp_path)
    epoch = repo.acquire_epoch()
    old = _create(
        repo,
        _session(),
        _record(generation="a" * 32, revision=0, epoch=epoch, turn_id="turn-1", sequence=1),
    )
    # Quarantine republishes generation "b" but reuses turn_id "turn-1".
    repo.quarantine_and_replace(
        old.pointer,
        _record(
            generation="b" * 32,
            revision=0,
            epoch=epoch,
            turn_id="turn-1",
            sequence=1,
            payload={"recovered": True},
        ),
    )
    # Stale writer still on generation "a" retries the same turn_id "turn-1".
    stale_retry = _record(
        generation="a" * 32, revision=1, epoch=epoch, turn_id="turn-1", sequence=2
    )
    assert (
        repo.compare_and_commit(_session(), _precondition(old, stale_retry), stale_retry)
        is CommitResult.STALE_STATE_GENERATION
    )


def test_short_os_write_is_looped_so_journal_is_not_truncated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Red-team F3: os.write may deliver fewer bytes than requested; the durable writer
    must loop so a short write never truncates a staged file under its published digest."""
    repo = StateRepository(tmp_path)
    epoch = repo.acquire_epoch()
    real_write = repository_module.os.write

    def short_write(fd: int, data) -> int:
        # Deliver at most 4 bytes per call, forcing many partial writes.
        return real_write(fd, bytes(data[:4]))

    monkeypatch.setattr(repository_module.os, "write", short_write)
    session_ref = _session()
    record = _record(
        generation="a" * 32,
        revision=0,
        epoch=epoch,
        turn_id="turn-1",
        sequence=1,
        payload={"blob": "z" * 200},
    )
    assert repo.compare_and_commit(session_ref, AbsentState(), record) is CommitResult.COMMITTED
    monkeypatch.undo()
    snapshot = repo.load(session_ref)
    assert snapshot is not None
    assert snapshot.pointer.payload_digest == payload_digest({"blob": "z" * 200})
    assert snapshot.canonical_cognitive_payload == canonical_json_bytes({"blob": "z" * 200})


def test_new_epoch_and_seal_fence_old_writers(tmp_path: Path) -> None:
    repo = StateRepository(tmp_path)
    old_epoch = repo.acquire_epoch()
    snapshot = _create(
        repo,
        _session(),
        _record(
            generation="a" * 32,
            revision=0,
            epoch=old_epoch,
            turn_id="turn-1",
            sequence=1,
        ),
    )
    delayed = _record(
        generation="a" * 32,
        revision=1,
        epoch=old_epoch,
        turn_id="turn-2",
        sequence=2,
    )

    assert repo.acquire_epoch() > old_epoch
    assert (
        repo.compare_and_commit(_session(), _precondition(snapshot, delayed), delayed)
        is CommitResult.STALE_EPOCH
    )

    active_epoch = repo.acquire_epoch()
    repo.seal_epoch(active_epoch)
    absent = _record(
        generation="b" * 32,
        revision=0,
        epoch=active_epoch,
        turn_id="sealed-turn",
        sequence=1,
    )
    assert (
        repo.compare_and_commit(_session("sealed"), AbsentState(), absent)
        is CommitResult.STALE_EPOCH
    )


def test_digest_revision_sequence_and_corrupt_base_results(tmp_path: Path) -> None:
    repo = StateRepository(tmp_path)
    epoch = repo.acquire_epoch()
    snapshot = _create(
        repo,
        _session(),
        _record(
            generation="a" * 32,
            revision=0,
            epoch=epoch,
            turn_id="turn-1",
            sequence=2,
        ),
    )
    valid = _record(
        generation="a" * 32,
        revision=1,
        epoch=epoch,
        turn_id="turn-2",
        sequence=3,
    )

    assert (
        repo.compare_and_commit(
            _session(),
            replace(_precondition(snapshot, valid), expected_payload_digest="0" * 64),
            valid,
        )
        is CommitResult.BASE_DIGEST_MISMATCH
    )
    stale_sequence = replace(
        valid,
        last_committed_turn_sequence=TurnSequence(epoch, 2),
        last_committed_turn_id="other-turn",
    )
    assert (
        repo.compare_and_commit(
            _session(), _precondition(snapshot, stale_sequence), stale_sequence
        )
        is CommitResult.STALE_SEQUENCE
    )

    current_path = tmp_path / snapshot.pointer.current_journal
    current_path.write_bytes(b"{corrupt")
    assert (
        repo.compare_and_commit(_session(), _precondition(snapshot, valid), valid)
        is CommitResult.CORRUPT_BASE
    )


def test_repository_retains_only_current_and_previous_revision(tmp_path: Path) -> None:
    repo = StateRepository(tmp_path)
    epoch = repo.acquire_epoch()
    session_ref = _session()
    snapshot = _create(
        repo,
        session_ref,
        _record(
            generation="a" * 32,
            revision=0,
            epoch=epoch,
            turn_id="turn-1",
            sequence=1,
        ),
    )
    for revision in range(1, 4):
        record = _record(
            generation="a" * 32,
            revision=revision,
            epoch=epoch,
            turn_id=f"turn-{revision + 1}",
            sequence=revision + 1,
        )
        assert (
            repo.compare_and_commit(session_ref, _precondition(snapshot, record), record)
            is CommitResult.COMMITTED
        )
        loaded = repo.load(session_ref)
        assert loaded is not None
        snapshot = loaded

    assert len(list(repo.sessions_directory.rglob("*.journal"))) == 2
    assert snapshot.pointer.previous_journal is not None


@pytest.mark.parametrize(
    "fault_point",
    [
        FaultPoint.BEFORE_SERIALIZE,
        FaultPoint.AFTER_SERIALIZE,
        FaultPoint.BEFORE_FLUSH,
        FaultPoint.AFTER_FLUSH,
        FaultPoint.BEFORE_FSYNC,
        FaultPoint.AFTER_FSYNC,
        FaultPoint.BEFORE_CLOSE,
        FaultPoint.AFTER_CLOSE,
        FaultPoint.BEFORE_REPLACE,
        FaultPoint.AFTER_REPLACE,
        FaultPoint.BEFORE_POINTER_PUBLISH,
        FaultPoint.AFTER_POINTER_PUBLISH,
    ],
)
def test_fault_injection_never_publishes_partial_state(
    tmp_path: Path,
    fault_point: FaultPoint,
) -> None:
    base_repo = StateRepository(tmp_path)
    epoch = base_repo.acquire_epoch()
    session_ref = _session()
    snapshot = _create(
        base_repo,
        session_ref,
        _record(
            generation="a" * 32,
            revision=0,
            epoch=epoch,
            turn_id="turn-1",
            sequence=1,
        ),
    )
    next_record = _record(
        generation="a" * 32,
        revision=1,
        epoch=epoch,
        turn_id="turn-2",
        sequence=2,
    )

    def inject(point: FaultPoint) -> None:
        if point is fault_point:
            raise RuntimeError(f"injected {point.value}")

    failing_repo = StateRepository(tmp_path, fault_injector=inject)
    with pytest.raises(RuntimeError, match="injected"):
        failing_repo.compare_and_commit(
            session_ref,
            _precondition(snapshot, next_record),
            next_record,
        )

    recovered_repo = StateRepository(tmp_path)
    loaded = recovered_repo.load(session_ref)
    assert loaded is not None
    expected_revision = 1 if fault_point is FaultPoint.AFTER_POINTER_PUBLISH else 0
    assert loaded.pointer.revision == expected_revision
    recovered_repo.recover_orphans()
    assert not list(recovered_repo.staging_directory.glob("*"))
    assert len(list(recovered_repo.sessions_directory.rglob("*.journal"))) <= 2


def test_windows_replace_retries_are_bounded_and_succeed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = StateRepository(tmp_path, replace_attempts=4, replace_retry_seconds=0.0)
    epoch = repo.acquire_epoch()
    session_ref = _session()
    snapshot = _create(
        repo,
        session_ref,
        _record(
            generation="a" * 32,
            revision=0,
            epoch=epoch,
            turn_id="turn-1",
            sequence=1,
        ),
    )
    next_record = _record(
        generation="a" * 32,
        revision=1,
        epoch=epoch,
        turn_id="turn-2",
        sequence=2,
    )
    real_replace = repository_module.os.replace
    attempts = 0

    def flaky_replace(source, destination) -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            error = PermissionError("sharing violation")
            error.winerror = 32
            raise error
        real_replace(source, destination)

    monkeypatch.setattr(repository_module.os, "replace", flaky_replace)

    assert (
        repo.compare_and_commit(session_ref, _precondition(snapshot, next_record), next_record)
        is CommitResult.COMMITTED
    )
    assert attempts >= 3


def test_unreachable_staging_is_removed_without_publication(tmp_path: Path) -> None:
    repo = StateRepository(tmp_path)
    epoch = repo.acquire_epoch()
    session_ref = _session()
    snapshot = _create(
        repo,
        session_ref,
        _record(
            generation="a" * 32,
            revision=0,
            epoch=epoch,
            turn_id="turn-1",
            sequence=1,
        ),
    )
    repo.staging_directory.mkdir(parents=True, exist_ok=True)
    (repo.staging_directory / "orphan.stage").write_bytes(b'{"looks":"valid"}')

    assert repo.recover_orphans() >= 1
    loaded = repo.load(session_ref)
    assert loaded is not None
    assert loaded.pointer == snapshot.pointer
    assert not list(repo.staging_directory.glob("*"))
