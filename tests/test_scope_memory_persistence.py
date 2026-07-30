"""Gateway-only memory persistence contracts before legacy ingress switches."""

from __future__ import annotations

import importlib

import pytest

from sylanne_alpha.memory_system import MemorySystem
from sylanne_alpha.scope_repository import (
    ScopeRepository,
    ScopedPersistenceGateway,
    StaleScopeWrite,
)
from tests.scope_fixtures import scopes


def _scoped_state_type():
    module = importlib.import_module("sylanne_alpha.state_persistence")
    state_type = getattr(module, "ScopedStatePersistence", None)
    assert state_type is not None, "Task 6 needs gateway-bound scoped state persistence"
    return state_type


def _scoped_facade_type():
    module = importlib.import_module("sylanne_alpha.memory_facade")
    facade_type = getattr(module, "ScopedMemoryFacade", None)
    assert facade_type is not None, "Task 6 needs a gateway-bound memory facade"
    return facade_type


def _scoped_throat_type():
    module = importlib.import_module("sylanne_alpha.memory_write_throat")
    throat_type = getattr(module, "ScopedMemoryWriteThroat", None)
    assert throat_type is not None, "Task 6 needs a gateway-bound memory write throat"
    return throat_type


@pytest.mark.asyncio
async def test_scoped_memory_restart_isolated_for_same_transport_value(tmp_path, scopes) -> None:
    """Bot/Persona scopes with the same transport value never share memory."""

    state_type = _scoped_state_type()
    facade_type = _scoped_facade_type()
    repository = ScopeRepository(tmp_path / "scope-v1")
    left_scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    right_scope = repository.create_scope(scopes.bot_b_persona_a, expected_absent=True)
    assert left_scope.session_ref.token == right_scope.session_ref.token

    left_memory = MemorySystem()
    left_memory.write("left-scope-only")
    left = facade_type(state_type(ScopedPersistenceGateway(repository, left_scope)))
    right = facade_type(state_type(ScopedPersistenceGateway(repository, right_scope)))

    assert await left.save_memory(left_memory) is True
    assert await right.load_memory() is None
    assert repository.component_path(left_scope, "memory") != repository.component_path(right_scope, "memory")

    restarted = facade_type(state_type(ScopedPersistenceGateway(repository, left_scope)))
    restored = await restarted.load_memory()
    assert restored is not None
    assert restored.to_dict() == left_memory.to_dict()


@pytest.mark.asyncio
async def test_scoped_memory_save_uses_component_generation_cas(tmp_path, scopes) -> None:
    """Independent writers must load before they can advance the memory snapshot."""

    state_type = _scoped_state_type()
    throat_type = _scoped_throat_type()
    repository = ScopeRepository(tmp_path / "scope-v1")
    active = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    gateway = ScopedPersistenceGateway(repository, active)
    first = state_type(gateway)
    second = state_type(gateway)
    memory = MemorySystem()
    memory.write("first-generation")

    assert await throat_type(first).save_memory(memory) is True
    with pytest.raises(StaleScopeWrite, match="generation_stale"):
        await second.save_memory(memory)

    restored = await second.load_memory()
    assert restored is not None
    assert await second.save_memory(restored) is True
    stored = repository.read_component(active, "memory")
    assert stored is not None and stored.generation == 2


@pytest.mark.asyncio
async def test_scoped_memory_delayed_save_captures_gateway_and_generation(
    tmp_path,
    scopes,
) -> None:
    """Delayed work is stale after either a newer memory CAS or a scope reset."""

    state_type = _scoped_state_type()
    throat_type = _scoped_throat_type()
    repository = ScopeRepository(tmp_path / "scope-v1")
    active = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    gateway = ScopedPersistenceGateway(repository, active)
    state = state_type(gateway)
    memory = MemorySystem()
    memory.write("captured-before-delay")
    assert await state.save_memory(memory) is True

    delayed = throat_type(state).schedule_memory_save(memory, delay_seconds=0.01)
    newer = state_type(gateway)
    loaded = await newer.load_memory()
    assert loaded is not None
    assert await newer.save_memory(loaded) is True
    assert await delayed is False

    stored = repository.read_component(active, "memory")
    assert stored is not None and stored.generation == 2

    reset_delayed = state.schedule_memory_save(memory, delay_seconds=0.01)
    replacement = repository.invalidate_scope(
        active,
        expected_scope_generation=active.scope_generation,
        reason="reset",
    )
    assert await reset_delayed is False
    assert repository.read_component(replacement, "memory") is None
    with pytest.raises(StaleScopeWrite, match="scope_generation_stale"):
        await state.save_memory(memory)


@pytest.mark.asyncio
async def test_scoped_memory_delayed_save_freezes_nested_payload_before_yield(
    tmp_path,
    scopes,
) -> None:
    """A delayed memory write persists its exact scheduling-time JSON snapshot."""

    state_type = _scoped_state_type()
    repository = ScopeRepository(tmp_path / "scope-v1")
    active = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    state = state_type(ScopedPersistenceGateway(repository, active))
    memory = MemorySystem()
    followup = {
        "topic_snippet": "captured-before-delay",
        "due_ts_estimate": 1.0,
        "session_key": "ephemeral-source",
        "created_ts": 1.0,
    }
    memory._pending_followups.append(followup)

    delayed = state.schedule_memory_save(memory, delay_seconds=0.01)
    followup["topic_snippet"] = "mutated-after-schedule"

    assert await delayed is True
    stored = repository.read_component(active, "memory")
    assert stored is not None
    assert stored.payload["pending_followups"] == [
        {
            "topic_snippet": "captured-before-delay",
            "due_ts_estimate": 1.0,
            "session_key": "ephemeral-source",
            "created_ts": 1.0,
        }
    ]
    restored = MemorySystem.create_from_dict(stored.payload)
    assert restored._pending_followups[0]["topic_snippet"] == "captured-before-delay"


@pytest.mark.asyncio
async def test_scoped_memory_seams_reject_non_gateway_inputs_and_legacy_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    scopes,
) -> None:
    """Scoped APIs have no raw token or legacy StatePersistence escape hatch."""

    state_module = importlib.import_module("sylanne_alpha.state_persistence")
    facade_module = importlib.import_module("sylanne_alpha.memory_facade")
    state_type = _scoped_state_type()
    facade_type = _scoped_facade_type()
    throat_type = _scoped_throat_type()

    class _LegacyStateTrap:
        calls = 0

        def __init__(self, *_args, **_kwargs) -> None:
            type(self).calls += 1
            raise AssertionError("scoped path must not construct legacy StatePersistence")

    class _LegacyFacadeTrap:
        calls = 0

        def __init__(self, *_args, **_kwargs) -> None:
            type(self).calls += 1
            raise AssertionError("scoped path must not construct legacy MemoryFacade")

    monkeypatch.setattr(state_module, "StatePersistence", _LegacyStateTrap)
    monkeypatch.setattr(facade_module, "MemoryFacade", _LegacyFacadeTrap)

    with pytest.raises(ValueError, match="gateway"):
        state_type(object())
    with pytest.raises(ValueError, match="ScopedStatePersistence"):
        facade_type(object())
    with pytest.raises(ValueError, match="ScopedStatePersistence"):
        throat_type(object())

    repository = ScopeRepository(tmp_path / "scope-v1")
    active = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    facade = facade_type(state_type(ScopedPersistenceGateway(repository, active)))
    with pytest.raises(TypeError):
        await facade.load_memory(active.session_ref.token)

    assert _LegacyStateTrap.calls == 0
    assert _LegacyFacadeTrap.calls == 0
