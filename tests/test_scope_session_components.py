"""Contracts for gateway-only life/rhythm/social/scheduler scoped state."""

from __future__ import annotations

import importlib

import pytest

from sylanne_alpha.scope_repository import (
    ScopeRepository,
    ScopedPersistenceGateway,
    StaleScopeWrite,
)
from tests.scope_fixtures import scopes


def _store_type():
    module = importlib.import_module("sylanne_alpha.scoped_session_components")
    store_type = getattr(module, "ScopedSessionComponentStore", None)
    assert store_type is not None, "Task 6 needs a scoped session component store"
    return store_type


def test_scoped_session_components_isolate_same_transport_and_restart(tmp_path, scopes) -> None:
    """The same transport value under another Bot never shares state."""

    store_type = _store_type()
    repository = ScopeRepository(tmp_path / "scope-v1")
    left_scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    sibling_persona_scope = repository.create_scope(
        scopes.bot_a_persona_b,
        expected_absent=True,
    )
    right_scope = repository.create_scope(scopes.bot_b_persona_a, expected_absent=True)
    assert left_scope.session_ref.token == right_scope.session_ref.token
    assert left_scope.session_ref.token == sibling_persona_scope.session_ref.token

    left = store_type(ScopedPersistenceGateway(repository, left_scope))
    sibling_persona = store_type(
        ScopedPersistenceGateway(repository, sibling_persona_scope),
    )
    right = store_type(ScopedPersistenceGateway(repository, right_scope))
    values = {
        "life": {"mood": "left-only"},
        "rhythm": {"cadence": ["dawn", "night"]},
        "social": {"contacts": [{"tag": "trusted"}]},
        "scheduler": {"next_tick": 42},
    }
    for component, payload in values.items():
        assert left.save(component, payload) == 1
        assert left.generation(component) == 1
        assert sibling_persona.load(component) is None
        assert sibling_persona.generation(component) == 0
        assert right.load(component) is None
        assert right.generation(component) == 0
        assert repository.component_path(left_scope, component) != repository.component_path(
            right_scope,
            component,
        )

    restarted = store_type(ScopedPersistenceGateway(repository, left_scope))
    for component, expected in values.items():
        assert restarted.load(component) == expected
        assert restarted.generation(component) == 1


def test_scoped_session_components_keep_independent_component_cas(tmp_path, scopes) -> None:
    """Each allowlisted component owns its own generation counter."""

    store_type = _store_type()
    repository = ScopeRepository(tmp_path / "scope-v1")
    active = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    gateway = ScopedPersistenceGateway(repository, active)
    first = store_type(gateway)
    second = store_type(gateway)

    assert first.save("life", {"revision": 1}) == 1
    assert first.save("rhythm", {"revision": 1}) == 1
    with pytest.raises(StaleScopeWrite, match="generation_stale"):
        second.save("life", {"revision": 2})

    assert second.load("life") == {"revision": 1}
    assert second.save("life", {"revision": 2}) == 2
    assert second.save("social", {"revision": 1}) == 1
    assert first.generation("life") == 1
    assert first.generation("rhythm") == 1
    assert second.generation("life") == 2
    assert second.generation("social") == 1


@pytest.mark.asyncio
async def test_delayed_component_save_captures_snapshot_and_fences_newer_or_reset(
    tmp_path,
    scopes,
) -> None:
    """Delayed saves keep their original payload/generation and never rebind."""

    store_type = _store_type()
    repository = ScopeRepository(tmp_path / "scope-v1")
    active = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    gateway = ScopedPersistenceGateway(repository, active)
    store = store_type(gateway)

    payload = {"events": ["captured"]}
    captured = store.schedule_save("scheduler", payload, delay_seconds=0.01)
    payload["events"].append("mutated-after-schedule")
    assert await captured is True
    assert store.load("scheduler") == {"events": ["captured"]}

    delayed = store.schedule_save("scheduler", {"revision": "late"}, delay_seconds=0.01)
    newer = store_type(gateway)
    assert newer.load("scheduler") == {"events": ["captured"]}
    assert newer.save("scheduler", {"revision": "newer"}) == 2
    assert await delayed is False
    stored = repository.read_component(active, "scheduler")
    assert stored is not None
    assert stored.generation == 2
    assert stored.payload == {"revision": "newer"}

    reset_delayed = store.schedule_save("life", {"revision": "reset-late"}, delay_seconds=0.01)
    replacement = repository.invalidate_scope(
        active,
        expected_scope_generation=active.scope_generation,
        reason="reset",
    )
    assert await reset_delayed is False
    assert repository.read_component(replacement, "life") is None
    with pytest.raises(StaleScopeWrite, match="scope_generation_stale"):
        store.save("life", {"revision": "direct-late"})


def test_scoped_session_component_api_rejects_raw_unsupported_and_non_json_inputs(
    tmp_path,
    scopes,
) -> None:
    """This seam accepts only a frozen gateway, an exact component, and JSON."""

    store_type = _store_type()
    with pytest.raises(ValueError, match="gateway"):
        store_type(object())

    repository = ScopeRepository(tmp_path / "scope-v1")
    active = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    store = store_type(ScopedPersistenceGateway(repository, active))

    for raw_or_unsupported in (
        active.session_ref.token,
        active.storage_token,
        "memory",
        "default",
        "latest",
    ):
        with pytest.raises(ValueError, match="unsupported"):
            store.load(raw_or_unsupported)
        with pytest.raises(ValueError, match="unsupported"):
            store.save(raw_or_unsupported, {"x": 1})

    with pytest.raises(ValueError, match="exact dict"):
        store.save("life", ["not", "a", "payload"])
    with pytest.raises(ValueError, match="canonical JSON"):
        store.save("life", {"bad": object()})
    with pytest.raises(ValueError, match="canonical JSON"):
        store.save("life", {"bad": float("nan")})
    with pytest.raises(ValueError, match="object keys"):
        store.save("life", {"nested": [{1: "lossy-key"}]})
    with pytest.raises(ValueError, match="non-negative"):
        store.schedule_save("life", {"x": 1}, delay_seconds=-1.0)

    with pytest.raises(TypeError):
        store.load()
    with pytest.raises(TypeError):
        store.save("life")
