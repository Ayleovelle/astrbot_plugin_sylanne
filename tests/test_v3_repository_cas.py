from __future__ import annotations

import json
import threading
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import sylanne_alpha.v3bridge._state_repository as repository_module
from sylanne_alpha.v3bridge._state_repository import (
    AbsentState,
    CommitPrecondition,
    CommitResult,
    FaultPoint,
    JournalRecord,
    RepositoryBudgetExceeded,
    RepositoryCorruptionError,
    StateRepository,
    payload_digest,
)
from sylanne_alpha.v3bridge.session_identity import (
    SessionIdentityKey,
    session_filename_token,
)
from sylanne_alpha.v3core.canonical import canonical_json_bytes
from sylanne_alpha.v3core.contracts import SessionRef, TurnSequence


_IDENTITY = SessionIdentityKey(key_id="repository-v1", secret=b"r" * 32)
_JOURNAL_SESSION_TOKEN = f"s3-{'a' * 64}"
_JOURNAL_NAME = "rev000000000001-0123456789abcdef.journal"
_JOURNAL_REFERENCE = f"sessions/{_JOURNAL_SESSION_TOKEN}/{_JOURNAL_NAME}"


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


def test_journal_reference_accepts_only_repository_generated_shape() -> None:
    assert (
        StateRepository._validate_journal_reference(
            _JOURNAL_REFERENCE,
            _JOURNAL_SESSION_TOKEN,
        )
        == _JOURNAL_REFERENCE
    )


def test_journal_reference_accepts_the_real_session_token_format() -> None:
    token = session_filename_token(_session("journal-reference"))
    reference = f"sessions/{token}/{_JOURNAL_NAME}"

    assert StateRepository._validate_journal_reference(reference, token) == reference


@pytest.mark.parametrize(
    "reference",
    [
        None,
        f"sessions/{_JOURNAL_SESSION_TOKEN}/arbitrary.journal",
        f"sessions/{_JOURNAL_SESSION_TOKEN}/rev00000000001-0123456789abcdef.journal",
        f"sessions/{_JOURNAL_SESSION_TOKEN}/rev000000000001-0123456789abcde.journal",
        f"sessions/{_JOURNAL_SESSION_TOKEN}/rev000000000001-0123456789ABCDEf.journal",
        f"sessions/{_JOURNAL_SESSION_TOKEN}/rev000000000001-0123456789abcdef\\nested.journal",
        f"sessions/{_JOURNAL_SESSION_TOKEN}/C:\\{_JOURNAL_NAME}",
        f"sessions/{_JOURNAL_SESSION_TOKEN}/\\\\server\\share\\{_JOURNAL_NAME}",
        f"sessions\\{_JOURNAL_SESSION_TOKEN}/{_JOURNAL_NAME}",
        f"sessions/{_JOURNAL_SESSION_TOKEN}\\{_JOURNAL_NAME}",
        f"sessions/{_JOURNAL_SESSION_TOKEN}/./{_JOURNAL_NAME}",
        f"sessions//{_JOURNAL_SESSION_TOKEN}/{_JOURNAL_NAME}",
        f"sessions/s3-{'b' * 64}/{_JOURNAL_NAME}",
        f"sessions/{'a' * 64}/{_JOURNAL_NAME}",
        f"sessions/s4-{'a' * 64}/{_JOURNAL_NAME}",
        f"C:/sessions/{_JOURNAL_SESSION_TOKEN}/{_JOURNAL_NAME}",
        f"//server/share/sessions/{_JOURNAL_SESSION_TOKEN}/{_JOURNAL_NAME}",
    ],
    ids=[
        "non-text",
        "arbitrary-name",
        "short-revision",
        "short-nonce",
        "uppercase-nonce",
        "backslash-in-name",
        "drive-in-name",
        "unc-in-name",
        "mixed-root-separator",
        "mixed-leaf-separator",
        "dot-segment",
        "repeated-separator",
        "wrong-session-token",
        "missing-token-version",
        "wrong-token-version",
        "drive-prefix",
        "unc-prefix",
    ],
)
def test_journal_reference_rejects_noncanonical_or_cross_namespace_paths(
    reference: object,
) -> None:
    with pytest.raises(RepositoryCorruptionError, match="journal reference"):
        StateRepository._validate_journal_reference(
            reference,
            _JOURNAL_SESSION_TOKEN,
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


def test_quarantine_rechecks_exact_old_pointer_under_repository_lock(tmp_path: Path) -> None:
    repo = StateRepository(tmp_path)
    epoch = repo.acquire_epoch()
    session_ref = _session("quarantine-cas")
    old = _create(
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
    advanced = _record(
        generation="a" * 32,
        revision=1,
        epoch=epoch,
        turn_id="turn-2",
        sequence=2,
    )
    assert (
        repo.compare_and_commit(session_ref, _precondition(old, advanced), advanced)
        is CommitResult.COMMITTED
    )

    replacement = _record(
        generation="b" * 32,
        revision=0,
        epoch=epoch,
        turn_id="recovery",
        sequence=2,
        payload={"recovered": True},
    )
    with pytest.raises(RuntimeError, match="pointer changed"):
        repo.quarantine_and_replace(old.pointer, replacement)

    loaded = repo.load(session_ref)
    assert loaded is not None
    assert loaded.pointer.state_generation_id == "a" * 32
    assert loaded.pointer.revision == 1


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


def test_corrupt_epoch_is_not_treated_as_epoch_zero(tmp_path: Path) -> None:
    repo = StateRepository(tmp_path)
    repo._epoch_path.write_bytes(b"not-an-epoch")

    with pytest.raises(RuntimeError, match="epoch"):
        repo.current_epoch()
    with pytest.raises(RuntimeError, match="epoch"):
        repo.acquire_epoch()
    assert repo._epoch_path.read_bytes() == b"not-an-epoch"


def test_corrupt_epoch_seal_is_not_treated_as_empty(tmp_path: Path) -> None:
    repo = StateRepository(tmp_path)
    epoch = repo.acquire_epoch()
    repo._sealed_path.write_bytes(b"{corrupt")
    record = _record(
        generation="a" * 32,
        revision=0,
        epoch=epoch,
        turn_id="turn-1",
        sequence=1,
    )

    with pytest.raises(RuntimeError, match="seal"):
        repo.compare_and_commit(_session("corrupt-seal"), AbsentState(), record)
    assert repo.load(_session("corrupt-seal")) is None


def test_corrupt_pointer_is_not_treated_as_absent_state(tmp_path: Path) -> None:
    repo = StateRepository(tmp_path)
    epoch = repo.acquire_epoch()
    session_ref = _session("corrupt-pointer")
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
    pointer_path = tmp_path / "sessions" / snapshot.pointer.session_token / "pointer"
    pointer_path.write_bytes(b"{corrupt")

    with pytest.raises(RuntimeError, match="pointer"):
        repo.load(session_ref)
    with pytest.raises(RuntimeError, match="pointer"):
        repo.compare_and_commit(
            session_ref,
            AbsentState(),
            _record(
                generation="b" * 32,
                revision=0,
                epoch=epoch,
                turn_id="turn-2",
                sequence=2,
            ),
        )
    assert pointer_path.read_bytes() == b"{corrupt"


@pytest.mark.parametrize(
    "tamper",
    ["session_token", "generation", "revision", "payload_digest"],
)
def test_load_validates_pointer_against_current_journal(
    tmp_path: Path,
    tamper: str,
) -> None:
    repo = StateRepository(tmp_path)
    epoch = repo.acquire_epoch()
    session_ref = _session(f"load-{tamper}")
    snapshot = _create(
        repo,
        session_ref,
        _record(
            generation="a" * 32,
            revision=7,
            epoch=epoch,
            turn_id="turn-1",
            sequence=1,
            payload={"value": "trusted"},
        ),
    )
    pointer_path = tmp_path / "sessions" / snapshot.pointer.session_token / "pointer"
    journal_path = tmp_path / snapshot.pointer.current_journal
    pointer_data = json.loads(pointer_path.read_text("utf-8"))
    journal_data = json.loads(journal_path.read_text("utf-8"))

    if tamper == "session_token":
        pointer_data["session_token"] = "f" * 64
    elif tamper == "generation":
        journal_data["state_generation_id"] = "b" * 32
    elif tamper == "revision":
        journal_data["revision"] = 8
    else:
        journal_data["cognitive_payload"] = {"value": "tampered"}

    if tamper != "session_token":
        journal_bytes = canonical_json_bytes(journal_data)
        journal_path.write_bytes(journal_bytes)
        pointer_data["journal_digest"] = repository_module.canonical_sha256_of_bytes(
            journal_bytes
        )
    pointer_path.write_bytes(canonical_json_bytes(pointer_data))

    if tamper == "session_token":
        with pytest.raises(RuntimeError, match="pointer"):
            repo.load(session_ref)
    else:
        assert repo.load(session_ref) is None


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
    duplicate_id_on_corrupt_base = replace(
        valid,
        last_committed_turn_id=snapshot.pointer.last_committed_turn_id,
    )
    assert (
        repo.compare_and_commit(
            _session(),
            _precondition(snapshot, duplicate_id_on_corrupt_base),
            duplicate_id_on_corrupt_base,
        )
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


def test_budget_reserves_pointer_staging_at_old_plus_new_peak(tmp_path: Path) -> None:
    base_repo = StateRepository(tmp_path, hard_limit_bytes=1_000_000)
    epoch = base_repo.acquire_epoch()
    session_ref = _session("budget-peak")
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
        payload={"blob": "x" * 512},
    )
    journal_only_limit = base_repo.usage_bytes() + len(base_repo._journal_bytes(next_record))
    limited = StateRepository(tmp_path, hard_limit_bytes=journal_only_limit)

    with pytest.raises(repository_module.RepositoryBudgetExceeded):
        limited.compare_and_commit(
            session_ref,
            _precondition(snapshot, next_record),
            next_record,
        )
    loaded = base_repo.load(session_ref)
    assert loaded is not None and loaded.pointer.revision == 0


def test_budget_counts_anchor_and_other_namespace_files(tmp_path: Path) -> None:
    repo = StateRepository(tmp_path, hard_limit_bytes=1_000_000)
    epoch = repo.acquire_epoch()
    record = _record(
        generation="a" * 32,
        revision=0,
        epoch=epoch,
        turn_id="turn-1",
        sequence=1,
        payload={"blob": "x" * 256},
    )
    usage_before_anchor = repo.usage_bytes()
    anchor = tmp_path / "anchors" / "opaque" / "seed.anchor"
    anchor.parent.mkdir(parents=True)
    anchor.write_bytes(b"a" * 4096)
    hard_limit = usage_before_anchor + len(repo._journal_bytes(record)) + 2048
    limited = StateRepository(tmp_path, hard_limit_bytes=hard_limit)

    with pytest.raises(repository_module.RepositoryBudgetExceeded):
        limited.compare_and_commit(_session("budget-anchor"), AbsentState(), record)
    assert anchor.exists()


def test_concurrent_seed_anchor_writes_share_lock_and_peak_budget(tmp_path: Path) -> None:
    """Two repository instances cannot both reserve the last anchor-sized bytes."""

    payload = b"a" * 128
    first = StateRepository(tmp_path, hard_limit_bytes=len(payload))
    second = StateRepository(tmp_path, hard_limit_bytes=len(payload))
    gate = threading.Barrier(2)
    outcomes: list[object] = []

    def write(repo: StateRepository, token: str) -> None:
        gate.wait()
        try:
            repo.write_seed_anchor(token, "generation", payload)
        except Exception as exc:  # captured for the cross-thread assertion below
            outcomes.append(exc)
        else:
            outcomes.append("written")

    workers = [
        threading.Thread(target=write, args=(first, "a" * 64)),
        threading.Thread(target=write, args=(second, "b" * 64)),
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=5.0)

    assert all(not worker.is_alive() for worker in workers)
    assert outcomes.count("written") == 1
    failures = [item for item in outcomes if isinstance(item, BaseException)]
    assert len(failures) == 1
    assert isinstance(failures[0], RepositoryBudgetExceeded)
    anchors = list((first.root / "anchors").rglob("*.anchor"))
    assert len(anchors) == 1
    assert first.usage_bytes() <= first.hard_limit_bytes


def test_seed_anchor_cleanup_is_lock_scoped_fsyncs_and_preserves_the_live_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Loser/orphan rollback must share the repository's mutation fence.

    Reading a pointer and then unlinking anchors outside that fence lets recovery
    delete a migration anchor between its durable write and pointer publication.
    Cleanup therefore derives the live generation and removes only other anchors
    while holding the same cross-process lock, then syncs the directory entry.
    """

    repo = StateRepository(tmp_path, hard_limit_bytes=1_000_000, lock_timeout_seconds=1.0)
    epoch = repo.acquire_epoch()
    session_ref = _session("anchor-cleanup")
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
    token = snapshot.pointer.session_token
    live = repo.root / "anchors" / token / f"{'a' * 32}.anchor"
    orphan = repo.root / "anchors" / token / f"{'b' * 32}.anchor"
    repo.write_seed_anchor(token, "a" * 32, b"live")
    repo.write_seed_anchor(token, "b" * 32, b"orphan")

    synced: list[Path] = []
    original_fsync_dir = repo._fsync_dir

    def record_fsync(directory: Path) -> None:
        synced.append(directory)
        original_fsync_dir(directory)

    monkeypatch.setattr(repo, "_fsync_dir", record_fsync)
    outcome: list[object] = []
    finished = threading.Event()

    def clean() -> None:
        try:
            outcome.append(repo.clean_seed_anchors(token))
        except Exception as exc:  # captured for the thread-safe assertion below
            outcome.append(exc)
        finally:
            finished.set()

    with repository_module.portalocker.Lock(
        repo._lock_path,
        mode="a+b",
        timeout=1.0,
        flags=(
            repository_module.portalocker.LOCK_EX
            | repository_module.portalocker.LOCK_NB
        ),
    ):
        worker = threading.Thread(target=clean)
        worker.start()
        time.sleep(0.05)
        assert not finished.is_set(), "anchor cleanup bypassed the repository lock"

    worker.join(timeout=2.0)
    assert not worker.is_alive()
    assert outcome == [1]
    assert live.exists()
    assert not orphan.exists()
    assert live.parent in synced


def test_default_budget_uses_effective_v3_hard_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, int]] = []

    def fake_effective_cap(non_v3_bytes: int, plugin_cap_bytes: int) -> int:
        calls.append((non_v3_bytes, plugin_cap_bytes))
        return 12_345

    monkeypatch.setattr(
        repository_module,
        "effective_v3_hard_cap",
        fake_effective_cap,
        raising=False,
    )
    repo = StateRepository(tmp_path, non_v3_bytes=321, plugin_cap_bytes=654)

    assert calls == [(321, 654)]
    assert repo.hard_limit_bytes == 12_345


def test_repository_lock_uses_bounded_portalocker_scope_and_propagates_permanent_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    class PermanentlyFailingLock:
        def __init__(self, _path: object, **kwargs: object) -> None:
            calls.append(kwargs)

        def __enter__(self):
            raise PermissionError("permanent lock error")

        def __exit__(self, *_exc: object) -> None:
            return None

    fake_portalocker = SimpleNamespace(
        Lock=PermanentlyFailingLock,
        LOCK_EX=1,
        LOCK_NB=2,
    )
    monkeypatch.setattr(repository_module, "portalocker", fake_portalocker, raising=False)
    repo = StateRepository(tmp_path, lock_timeout_seconds=0.125)

    with pytest.raises(PermissionError, match="permanent lock error"):
        repo.acquire_epoch()
    assert len(calls) == 1
    assert calls[0]["timeout"] == 0.125


def test_requirements_declares_portalocker_lower_bound_without_exact_pin() -> None:
    requirements = (Path(__file__).parents[1] / "requirements.txt").read_text("utf-8")
    assert "portalocker>=2.10" in requirements.splitlines()
    assert "portalocker==" not in requirements


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
