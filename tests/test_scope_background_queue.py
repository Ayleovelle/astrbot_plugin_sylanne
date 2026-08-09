"""Production scoped-background-queue persistence contracts."""

from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path

import pytest

from sylanne_alpha.background_queue import BackgroundPostJob, BackgroundPostQueue
from sylanne_alpha.memory_system import MemorySystem
from sylanne_alpha.scope_repository import (
    ScopeRepository,
    ScopedPersistenceGateway,
    StaleScopeWrite,
)
from tests.scope_fixtures import scopes


@pytest.mark.asyncio
async def test_scoped_queue_checkpoint_isolated_restart_safe_and_never_serializes_identity(
    tmp_path,
    scopes,
) -> None:
    """Queue recovery is bound to one frozen scope, with no KV compatibility path."""

    repository = ScopeRepository(tmp_path / "scope-v1")
    left_scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    other_persona_scope = repository.create_scope(
        scopes.bot_a_persona_b,
        expected_absent=True,
    )
    right_scope = repository.create_scope(scopes.bot_b_persona_a, expected_absent=True)
    assert left_scope.session_ref.token == other_persona_scope.session_ref.token
    assert left_scope.session_ref.token == right_scope.session_ref.token
    left = BackgroundPostQueue(ScopedPersistenceGateway(repository, left_scope))
    other_persona = BackgroundPostQueue(
        ScopedPersistenceGateway(repository, other_persona_scope)
    )
    right = BackgroundPostQueue(ScopedPersistenceGateway(repository, right_scope))
    left.enqueue(
        BackgroundPostJob(
            event=None,
            identity="authenticated-subject-must-not-persist",
            reply_text="left",
            context_key="left-context",
            sequence=1,
            enqueued_at=1.0,
        )
    )
    other_persona.enqueue(
        BackgroundPostJob(
            event=None,
            identity="same-transport-other-persona",
            reply_text="other-persona",
            context_key="other-persona-context",
            sequence=1,
            enqueued_at=1.0,
        )
    )
    right.enqueue(
        BackgroundPostJob(
            event=None,
            identity="other-subject",
            reply_text="right",
            context_key="right-context",
            sequence=1,
            enqueued_at=1.0,
        )
    )

    assert await left.save_checkpoint() is True
    assert await other_persona.save_checkpoint() is True
    assert await right.save_checkpoint() is True
    stored = repository.read_component(left_scope, "background-queue")
    assert stored is not None
    assert "authenticated-subject-must-not-persist" not in json.dumps(stored.payload)
    assert repository.component_path(left_scope, "background-queue") != repository.component_path(
        right_scope,
        "background-queue",
    )

    restarted = BackgroundPostQueue(ScopedPersistenceGateway(repository, left_scope))
    assert await restarted.recover_queue() is True
    leased = restarted.lease_next(now=2.0, lease_seconds=10.0)
    assert leased is not None and leased.reply_text == "left"
    other_persona_restarted = BackgroundPostQueue(
        ScopedPersistenceGateway(repository, other_persona_scope)
    )
    assert await other_persona_restarted.recover_queue() is True
    other_persona_job = other_persona_restarted.lease_next(now=2.0, lease_seconds=10.0)
    assert other_persona_job is not None and other_persona_job.reply_text == "other-persona"


@pytest.mark.asyncio
async def test_delayed_scoped_queue_checkpoint_is_rejected_after_scope_reset(
    tmp_path,
    scopes,
) -> None:
    """The delayed checkpoint captures its gateway instead of resolving a latest session."""

    repository = ScopeRepository(tmp_path / "scope-v1")
    active = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    queue = BackgroundPostQueue(ScopedPersistenceGateway(repository, active))
    queue.enqueue(
        BackgroundPostJob(None, "subject", "late", "context", 1, 1.0)
    )
    delayed = queue.schedule_checkpoint(delay_seconds=0.01)
    replacement = repository.invalidate_scope(
        active,
        expected_scope_generation=active.scope_generation,
        reason="reset",
    )

    assert await delayed is False
    assert repository.read_component(replacement, "background-queue") is None
    with pytest.raises(StaleScopeWrite, match="scope_generation_stale"):
        await queue.save_checkpoint()


@pytest.mark.asyncio
async def test_scoped_queue_recovers_an_empty_captured_checkpoint(
    tmp_path,
    scopes,
) -> None:
    """An empty scoped snapshot remains recoverable without any session lookup."""

    repository = ScopeRepository(tmp_path / "scope-v1")
    active = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    gateway = ScopedPersistenceGateway(repository, active)

    assert await BackgroundPostQueue(gateway).save_checkpoint() is True
    restarted = BackgroundPostQueue(gateway)
    assert await restarted.recover_queue() is True
    assert restarted.lease_next(now=1.0, lease_seconds=1.0) is None


@pytest.mark.asyncio
async def test_delayed_scoped_queue_checkpoint_discards_when_a_newer_cas_wins(
    tmp_path,
    scopes,
) -> None:
    """A delayed checkpoint must not overwrite a checkpoint saved after scheduling."""

    repository = ScopeRepository(tmp_path / "scope-v1")
    active = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    queue = BackgroundPostQueue(ScopedPersistenceGateway(repository, active))
    queue.enqueue(BackgroundPostJob(None, "subject", "first", "context", 1, 1.0))
    delayed = queue.schedule_checkpoint(delay_seconds=0.01)

    assert await queue.save_checkpoint() is True
    queue.enqueue(BackgroundPostJob(None, "subject", "second", "context", 2, 2.0))

    assert await delayed is False
    stored = repository.read_component(active, "background-queue")
    assert stored is not None and stored.generation == 1
    assert [job["reply_text"] for job in stored.payload["jobs"]] == ["first"]


@pytest.mark.asyncio
async def test_recovered_job_has_no_reactive_event_or_identity(
    tmp_path,
    scopes,
) -> None:
    """Restart recovery cannot revive an event capable of reactive delivery."""

    class ReactiveEvent:
        calls = 0

        async def send(self, _text: str) -> None:
            self.calls += 1

    repository = ScopeRepository(tmp_path / "scope-v1")
    active = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    queue = BackgroundPostQueue(ScopedPersistenceGateway(repository, active))
    reactive_event = ReactiveEvent()
    queue.enqueue(
        BackgroundPostJob(reactive_event, "subject", "saved", "context", 1, 1.0)
    )
    assert await queue.save_checkpoint() is True

    restarted = BackgroundPostQueue(ScopedPersistenceGateway(repository, active))
    assert await restarted.recover_queue() is True

    processed: list[str] = []

    async def private_processor(job: BackgroundPostJob) -> bool:
        assert job.event is None
        assert job.identity == ""
        processed.append(job.reply_text)
        return True

    assert await restarted.drain(private_processor, now=2.0) == 1
    assert processed == ["saved"]
    assert reactive_event.calls == 0


def test_active_queue_has_no_raw_key_default_or_kv_branch() -> None:
    """The active entrypoint is scope-capability-only; legacy stays elsewhere."""

    source = (
        Path(__file__).parents[1] / "sylanne_alpha" / "background_queue.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "checkpoint_kv_key",
        "get_kv_data",
        "put_kv_data",
        "delete_kv_data",
    ):
        assert forbidden not in source
    assert "PluginHost" not in source
    assert "default" not in source.lower()

    tree = ast.parse(source)
    queue_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "BackgroundPostQueue"
    )
    for method in (
        node
        for node in queue_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ):
        names = [argument.arg for argument in (*method.args.posonlyargs, *method.args.args)]
        names.extend(argument.arg for argument in method.args.kwonlyargs)
        assert "session_key" not in names


def test_main_has_no_legacy_raw_session_queue_dispatch() -> None:
    """The scoped production path cannot call the retired queue API surface."""

    source = (Path(__file__).parents[1] / "main.py").read_text(encoding="utf-8")
    for retired in (
        "checkpoint_kv_key",
        "adaptive_worker_decision",
        "max_workers",
        "job_to_dict",
        "drain_assessments",
    ):
        assert retired not in source
    assert "schedule_checkpoint(session_key)" not in source
    assert "save_checkpoint(session_key)" not in source
    assert "recover_queue(session_key)" not in source
    assert "recover_expired_active(session_key)" not in source


@pytest.mark.asyncio
async def test_scoped_state_persistence_captures_memory_generation_for_delayed_save(
    tmp_path,
    scopes,
) -> None:
    """Memory state uses only the captured scoped gateway and rejects stale work."""

    module = importlib.import_module("sylanne_alpha.state_persistence")
    state_type = getattr(module, "ScopedStatePersistence", None)
    assert state_type is not None, "Task 6 needs scoped StatePersistence"
    repository = ScopeRepository(tmp_path / "scope-v1")
    active = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    state = state_type(ScopedPersistenceGateway(repository, active))
    memory = MemorySystem()

    assert await state.save_memory(memory) is True
    restored = await state_type(
        ScopedPersistenceGateway(repository, active)
    ).load_memory()
    assert restored is not None and restored.to_dict() == memory.to_dict()

    delayed = state.schedule_memory_save(memory, delay_seconds=0.01)
    replacement = repository.invalidate_scope(
        active,
        expected_scope_generation=active.scope_generation,
        reason="reset",
    )

    assert await delayed is False
    assert repository.read_component(replacement, "memory") is None
    with pytest.raises(StaleScopeWrite, match="scope_generation_stale"):
        await state.save_memory(memory)
