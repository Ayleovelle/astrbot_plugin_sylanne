from __future__ import annotations

import multiprocessing
import queue
import time
from pathlib import Path

import portalocker

from sylanne_alpha.v3bridge._state_repository import (
    AbsentState,
    CommitPrecondition,
    CommitResult,
    JournalRecord,
    RepositoryBudgetExceeded,
    StateRepository,
)
from sylanne_alpha.v3bridge.session_identity import SessionIdentityKey
from sylanne_alpha.v3core.contracts import SessionRef, TurnSequence


_IDENTITY = SessionIdentityKey(key_id="repository-mp-v1", secret=b"m" * 32)


def _session(name: str) -> SessionRef:
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
    payload_size: int = 16,
) -> JournalRecord:
    return JournalRecord(
        schema_version=1,
        formula_version="formula-v1",
        source_digest="b" * 64,
        state_generation_id=generation,
        revision=revision,
        writer_epoch=epoch,
        session_generation=0,
        model_revision="model-v1",
        last_committed_turn_sequence=TurnSequence(epoch, sequence),
        last_committed_turn_id=turn_id,
        cognitive_payload={"blob": "x" * payload_size},
        deterministic_trace={"turn": turn_id},
    )


def _epoch_worker(root: str, start, output) -> None:
    start.wait()
    output.put(StateRepository(Path(root)).acquire_epoch())


def _cas_worker(
    root: str,
    session_ref: SessionRef,
    precondition: CommitPrecondition,
    record: JournalRecord,
    start,
    output,
) -> None:
    start.wait()
    result = StateRepository(Path(root)).compare_and_commit(
        session_ref,
        precondition,
        record,
    )
    output.put(result.value)


def _budget_worker(
    root: str,
    hard_limit_bytes: int,
    session_ref: SessionRef,
    record: JournalRecord,
    start,
    output,
) -> None:
    start.wait()
    try:
        result = StateRepository(
            Path(root),
            hard_limit_bytes=hard_limit_bytes,
        ).compare_and_commit(session_ref, AbsentState(), record)
    except RepositoryBudgetExceeded:
        output.put("BUDGET")
    else:
        output.put(result.value)


def _lock_holder(root: str, ready, release, output) -> None:
    lock_path = Path(root) / ".repo.lock"
    try:
        with portalocker.Lock(
            lock_path,
            mode="a+b",
            timeout=1.0,
            flags=portalocker.LOCK_EX | portalocker.LOCK_NB,
        ):
            ready.set()
            if not release.wait(10.0):
                output.put(("holder-timeout",))
                return
            output.put(("released",))
    except Exception as exc:  # pragma: no cover - diagnostic worker path
        output.put(("holder-error", type(exc).__module__, type(exc).__name__, str(exc)))


def _lock_timeout_worker(root: str, output) -> None:
    started = time.monotonic()
    try:
        StateRepository(Path(root), lock_timeout_seconds=0.2).acquire_epoch()
    except Exception as exc:
        output.put(
            (
                "error",
                type(exc).__module__,
                type(exc).__name__,
                time.monotonic() - started,
            )
        )
    else:
        output.put(("committed", time.monotonic() - started))


def _start_and_join(processes: list[multiprocessing.Process]) -> None:
    for process in processes:
        process.start()
    deadline = time.monotonic() + 20.0
    try:
        for process in processes:
            process.join(max(0.0, deadline - time.monotonic()))
        assert all(not process.is_alive() for process in processes)
        assert all(process.exitcode == 0 for process in processes)
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
            process.join(timeout=2.0)


def _drain(output, count: int) -> list[object]:
    values = []
    for _ in range(count):
        try:
            values.append(output.get(timeout=5.0))
        except queue.Empty as exc:  # pragma: no cover - diagnostic failure path
            raise AssertionError("worker exited without a result") from exc
    return values


def test_multiprocess_epoch_allocation_is_unique_and_monotonic(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    output = context.Queue()
    processes = [
        context.Process(target=_epoch_worker, args=(str(tmp_path), start, output))
        for _ in range(4)
    ]

    for process in processes:
        process.start()
    start.set()
    deadline = time.monotonic() + 20.0
    try:
        for process in processes:
            process.join(max(0.0, deadline - time.monotonic()))
        assert all(not process.is_alive() for process in processes)
        assert all(process.exitcode == 0 for process in processes)
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
            process.join(timeout=2.0)

    epochs = sorted(_drain(output, len(processes)))
    assert epochs == [1, 2, 3, 4]
    assert StateRepository(tmp_path).current_epoch() == 4


def test_multiprocess_repository_lock_timeout_is_bounded(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    release = context.Event()
    holder_output = context.Queue()
    contender_output = context.Queue()
    holder = context.Process(
        target=_lock_holder,
        args=(str(tmp_path), ready, release, holder_output),
    )
    contender = context.Process(
        target=_lock_timeout_worker,
        args=(str(tmp_path), contender_output),
    )

    holder.start()
    try:
        assert ready.wait(5.0), _drain(holder_output, 1)
        contender.start()
        contender.join(timeout=3.0)
        assert not contender.is_alive()
        assert contender.exitcode == 0
        outcome = _drain(contender_output, 1)[0]
        assert outcome[0] == "error"
        assert outcome[1] == "portalocker.exceptions"
        assert outcome[2] == "AlreadyLocked"
        assert 0.1 <= outcome[3] < 2.0
    finally:
        release.set()
        if contender.is_alive():
            contender.terminate()
        contender.join(timeout=2.0)
        holder.join(timeout=5.0)
        if holder.is_alive():
            holder.terminate()
        holder.join(timeout=2.0)

    assert holder.exitcode == 0
    assert _drain(holder_output, 1) == [("released",)]


def test_multiprocess_compare_and_commit_has_exactly_one_winner(tmp_path: Path) -> None:
    repo = StateRepository(tmp_path)
    epoch = repo.acquire_epoch()
    session_ref = _session("cas")
    base = _record(
        generation="a" * 32,
        revision=0,
        epoch=epoch,
        turn_id="turn-1",
        sequence=1,
    )
    assert repo.compare_and_commit(session_ref, AbsentState(), base) is CommitResult.COMMITTED
    snapshot = repo.load(session_ref)
    assert snapshot is not None

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

    def precondition(record: JournalRecord) -> CommitPrecondition:
        return CommitPrecondition(
            writer_epoch=epoch,
            expected_state_generation_id=snapshot.pointer.state_generation_id,
            expected_revision=snapshot.pointer.revision,
            expected_payload_digest=snapshot.pointer.payload_digest,
            turn_id=record.last_committed_turn_id,
            turn_sequence=record.last_committed_turn_sequence,
        )

    context = multiprocessing.get_context("spawn")
    start = context.Event()
    output = context.Queue()
    processes = [
        context.Process(
            target=_cas_worker,
            args=(str(tmp_path), session_ref, precondition(record), record, start, output),
        )
        for record in (first, second)
    ]
    for process in processes:
        process.start()
    start.set()
    deadline = time.monotonic() + 20.0
    try:
        for process in processes:
            process.join(max(0.0, deadline - time.monotonic()))
        assert all(not process.is_alive() for process in processes)
        assert all(process.exitcode == 0 for process in processes)
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
            process.join(timeout=2.0)

    assert sorted(_drain(output, 2)) == ["COMMITTED", "REVISION_CONFLICT"]
    loaded = repo.load(session_ref)
    assert loaded is not None and loaded.pointer.revision == 1


def test_budget_lock_prevents_two_processes_reserving_same_bytes(tmp_path: Path) -> None:
    hard_limit_bytes = 9_000
    repo = StateRepository(tmp_path, hard_limit_bytes=hard_limit_bytes)
    epoch = repo.acquire_epoch()
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    output = context.Queue()
    records = [
        _record(
            generation=character * 32,
            revision=0,
            epoch=epoch,
            turn_id=f"turn-{character}",
            sequence=1,
            payload_size=5_000,
        )
        for character in ("a", "b")
    ]
    processes = [
        context.Process(
            target=_budget_worker,
            args=(
                str(tmp_path),
                hard_limit_bytes,
                _session(f"budget-{index}"),
                record,
                start,
                output,
            ),
        )
        for index, record in enumerate(records)
    ]
    for process in processes:
        process.start()
    start.set()
    deadline = time.monotonic() + 20.0
    try:
        for process in processes:
            process.join(max(0.0, deadline - time.monotonic()))
        assert all(not process.is_alive() for process in processes)
        assert all(process.exitcode == 0 for process in processes)
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
            process.join(timeout=2.0)

    assert sorted(_drain(output, 2)) == ["BUDGET", "COMMITTED"]
    assert repo.usage_bytes() <= hard_limit_bytes
