"""Contracts for the scope-v1 V2/V3 snapshot adapter.

The adapter deliberately owns no session lookup or legacy persistence path.  It
receives only one frozen :class:`ScopedPersistenceGateway`, so all identity and
lifecycle fencing remains with ``ScopeRepository``.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Any

import pytest

from sylanne_alpha.scope_repository import (
    ScopeRepository,
    ScopedPersistenceGateway,
    StaleScopeWrite,
)
from sylanne_alpha.v2core.shadow_snapshot import V2SeedSnapshotV1
from tests.scope_fixtures import scopes


def _adapter(gateway: ScopedPersistenceGateway) -> Any:
    from sylanne_alpha.scoped_engine_persistence import ScopedEnginePersistence

    return ScopedEnginePersistence(gateway)


def test_v2_and_v3_shadow_are_isolated_by_scope_and_preserve_snapshot_shapes(
    tmp_path,
    scopes,
) -> None:
    """Identical transport-facing session values cannot join Bot/Persona state."""

    repository = ScopeRepository(tmp_path / "scope-v1")
    first_scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    persona_other_scope = repository.create_scope(scopes.bot_a_persona_b, expected_absent=True)
    bot_other_scope = repository.create_scope(scopes.bot_b_persona_a, expected_absent=True)
    first = _adapter(ScopedPersistenceGateway(repository, first_scope))
    persona_other = _adapter(ScopedPersistenceGateway(repository, persona_other_scope))
    bot_other = _adapter(ScopedPersistenceGateway(repository, bot_other_scope))

    v2_snapshot = V2SeedSnapshotV1(user_bond_ema=0.75, body_warmth=0.25)
    assert first.save_v2(v2_snapshot) == 1
    assert persona_other.save_v2({"schema_version": "v2.persona", "value": "other"}) == 1
    assert bot_other.save_v2({"schema_version": "v2.bot", "value": "other-bot"}) == 1
    assert first.load_v2().payload == asdict(v2_snapshot)
    assert persona_other.load_v2().payload == {"schema_version": "v2.persona", "value": "other"}
    assert bot_other.load_v2().payload == {"schema_version": "v2.bot", "value": "other-bot"}

    v3_snapshot = {
        "schema_version": "sylanne.v3.shadow.v1",
        "state": {"warmth": 0.2, "bands": ["soft", "guarded"]},
    }
    assert first.save_v3_shadow(v3_snapshot) == 1
    assert persona_other.save_v3_shadow({"schema_version": "v3.persona", "state": {}}) == 1
    assert bot_other.save_v3_shadow({"schema_version": "v3.bot", "state": {}}) == 1
    assert first.load_v3_shadow().payload == v3_snapshot
    assert persona_other.load_v3_shadow().payload == {"schema_version": "v3.persona", "state": {}}
    assert bot_other.load_v3_shadow().payload == {"schema_version": "v3.bot", "state": {}}


def test_v2_and_v3_shadow_have_independent_generations_and_restart_loads(
    tmp_path,
    scopes,
) -> None:
    """Each exact component has its own CAS lineage across adapter restart."""

    repository = ScopeRepository(tmp_path / "scope-v1")
    scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    gateway = ScopedPersistenceGateway(repository, scope)
    first = _adapter(gateway)

    assert first.save_v2({"schema_version": "v2.one", "revision": 1}) == 1
    assert first.save_v3_shadow({"schema_version": "v3.one", "revision": 1}) == 1
    assert first.save_v2({"schema_version": "v2.one", "revision": 2}) == 2

    restarted = _adapter(gateway)
    v2 = restarted.load_v2()
    v3 = restarted.load_v3_shadow()
    assert v2 is not None and v2.generation == 2 and v2.payload["revision"] == 2
    assert v3 is not None and v3.generation == 1 and v3.payload["revision"] == 1
    assert restarted.save_v3_shadow({"schema_version": "v3.one", "revision": 2}) == 2

    stale = _adapter(gateway)
    stale.load_v2()
    assert restarted.save_v2({"schema_version": "v2.one", "revision": 3}) == 3
    with pytest.raises(StaleScopeWrite):
        stale.save_v2({"schema_version": "v2.one", "revision": "late"})


@pytest.mark.asyncio
async def test_delayed_save_captures_payload_generation_and_gateway_before_yield(
    tmp_path,
    scopes,
) -> None:
    """Delayed writes fail closed after a newer CAS or a scoped reset."""

    repository = ScopeRepository(tmp_path / "scope-v1")
    scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    adapter = _adapter(ScopedPersistenceGateway(repository, scope))
    assert adapter.save_v2({"schema_version": "v2.test", "revision": 1}) == 1

    delayed_payload = {"schema_version": "v2.test", "nested": {"revision": 2}}
    delayed = asyncio.create_task(adapter.save_v2_delayed(delayed_payload))
    await asyncio.sleep(0)
    delayed_payload["nested"]["revision"] = 999
    assert adapter.save_v2({"schema_version": "v2.test", "revision": 3}) == 2
    assert await delayed is False
    stored = adapter.load_v2()
    assert stored is not None and stored.payload == {"schema_version": "v2.test", "revision": 3}

    # Calling the delayed API itself freezes the CAS head.  The caller need
    # not give the returned coroutine a chance to run before another write.
    captured_before_task = adapter.save_v2_delayed(
        {"schema_version": "v2.test", "revision": 4},
    )
    assert adapter.save_v2({"schema_version": "v2.test", "revision": 5}) == 3
    assert await captured_before_task is False
    stored = adapter.load_v2()
    assert stored is not None and stored.payload == {"schema_version": "v2.test", "revision": 5}

    reset_delayed = asyncio.create_task(adapter.save_v3_shadow_delayed({"schema_version": "v3.test", "revision": 1}))
    await asyncio.sleep(0)
    repository.invalidate_scope(
        scope,
        expected_scope_generation=scope.scope_generation,
        reason="reset",
    )
    assert await reset_delayed is False


def test_adapter_rejects_invalid_or_raw_style_input_and_never_uses_legacy_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    scopes,
) -> None:
    """The adapter has one scoped gateway path and no raw-key fallback."""

    from sylanne_alpha.scoped_engine_persistence import ScopedEnginePersistence

    repository = ScopeRepository(tmp_path / "scope-v1")
    scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    adapter = _adapter(ScopedPersistenceGateway(repository, scope))
    legacy_calls: list[object] = []

    def forbidden_legacy(*args: object, **kwargs: object) -> object:
        legacy_calls.append((args, kwargs))
        raise AssertionError("scoped engine persistence must not use legacy session persistence")

    monkeypatch.setattr(repository, "read_session", forbidden_legacy)
    monkeypatch.setattr(repository, "write_session", forbidden_legacy)

    assert adapter.save_v2({"schema_version": "v2.test", "ok": [1, {"fine": True}]}) == 1
    assert adapter.load_v2() is not None
    assert legacy_calls == []

    with pytest.raises(ValueError, match="exact JSON object"):
        adapter.save_v2(["not", "an", "object"])
    with pytest.raises(ValueError, match="ScopedPersistenceGateway"):
        ScopedEnginePersistence(object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="JSON-safe"):
        adapter.save_v3_shadow({"schema_version": "v3.test", "bad": {1, 2}})
    with pytest.raises(ValueError, match="JSON-safe"):
        adapter.save_v2({"schema_version": "v2.test", "bad": ("never", "coerce")})
    with pytest.raises(ValueError, match="raw scope identity"):
        adapter.save_v2({"schema_version": "v2.test", "session_key": "raw"})
    with pytest.raises(ValueError, match="raw scope identity"):
        adapter.save_v3_shadow({"schema_version": "v3.test", "storage_token": "raw"})
    with pytest.raises(ValueError, match="exact str"):
        adapter.save_v2({"schema_version": "v2.test", 1: "not-a-json-key"})


def test_adapter_canonical_deep_copies_saved_and_loaded_payloads(tmp_path, scopes) -> None:
    """Immediate snapshots cannot retain mutable aliases across the boundary."""

    repository = ScopeRepository(tmp_path / "scope-v1")
    scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    adapter = _adapter(ScopedPersistenceGateway(repository, scope))
    source = {"schema_version": "v3.test", "nested": {"value": 1}}

    assert adapter.save_v3_shadow(source) == 1
    source["nested"]["value"] = 999
    loaded = adapter.load_v3_shadow()
    assert loaded is not None and loaded.payload == {"schema_version": "v3.test", "nested": {"value": 1}}
    loaded.payload["nested"]["value"] = 333
    reread = adapter.load_v3_shadow()
    assert reread is not None and reread.payload == {"schema_version": "v3.test", "nested": {"value": 1}}
