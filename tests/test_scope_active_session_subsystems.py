"""Active scope-v1 construction contracts for session-owned subsystems."""

from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

import pytest

from sylanne_alpha.life_simulation import LifeSimulator
from sylanne_alpha.proactive_scheduler import ProactiveScheduler
from sylanne_alpha.rhythm_learner import RhythmLearner
from sylanne_alpha.scope_repository import ScopeRepository, ScopedPersistenceGateway
from sylanne_alpha.social_field import SocialFieldCollector
from tests.scope_fixtures import scopes


def _gateway(repository: ScopeRepository, scope) -> ScopedPersistenceGateway:
    return ScopedPersistenceGateway(repository, scope)


def _scheduler_plugin() -> SimpleNamespace:
    return SimpleNamespace(config={})


def test_active_scoped_session_subsystems_restore_without_scope_identity(
    tmp_path,
    scopes,
) -> None:
    """Life/rhythm/social/scheduler are real scoped constructors, not adapters."""

    repository = ScopeRepository(tmp_path / "scope-v1")
    left_scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    right_scope = repository.create_scope(scopes.bot_b_persona_a, expected_absent=True)
    left_gateway = _gateway(repository, left_scope)

    life = LifeSimulator(persistence=left_gateway)
    life.state.current_activity = "reading"
    assert life.flush_scoped_state() == 1

    rhythm = RhythmLearner(persistence=left_gateway)
    rhythm.observe_scoped_user_message(
        text="a rhythm sample",
        timestamp=100.0,
        engine_observation={"warmth": 1.0},
    )
    assert rhythm.flush_scoped_state() == 1

    social = SocialFieldCollector(persistence=left_gateway)
    social.collect(
        group_id="raw-group-42",
        sender_id="raw-sender-7",
        text="hello from a group",
        now=100.0,
    )
    assert social.flush_scoped_state() == 1

    scheduler = ProactiveScheduler(_scheduler_plugin(), persistence=left_gateway)
    scheduler.record_scoped_message_time(100.0)
    scheduler.register_scoped_ritual("goodnight", 22, 23)
    scheduler.record_scoped_feedback(101.0, "positive")
    assert scheduler.flush_scoped_state() == 1

    restored_life = LifeSimulator(persistence=left_gateway)
    restored_rhythm = RhythmLearner(persistence=left_gateway)
    restored_social = SocialFieldCollector(persistence=left_gateway)
    restored_scheduler = ProactiveScheduler(_scheduler_plugin(), persistence=left_gateway)

    assert restored_life.state.current_activity == "reading"
    assert restored_rhythm.scoped_profile() is not None
    assert restored_social.scoped_group_snapshot("raw-group-42")["silence_ticks"] == 1
    assert restored_scheduler.scoped_last_message_time() == 100.0
    ritual_now = time.mktime((2026, 1, 1, 22, 31, 0, 0, 0, -1))
    assert restored_scheduler.check_scoped_ritual_absence(now=ritual_now) == "goodnight"

    # Same raw transport values under a different Bot are a different component
    # path, and the scoped payload itself never carries an identity selector.
    for component in ("life", "rhythm", "social", "scheduler"):
        snapshot = repository.read_component(left_scope, component)
        assert snapshot is not None
        assert repository.read_component(right_scope, component) is None
        serialized = json.dumps(snapshot.payload, sort_keys=True)
        assert "raw-group-42" not in serialized
        assert "raw-sender-7" not in serialized
        assert left_scope.storage_token not in serialized
        assert "session_key" not in serialized
        assert "origin_session" not in serialized
        assert '"default"' not in serialized


def test_scoped_subsystems_reject_raw_legacy_calls_and_discard_stale_flush(
    tmp_path,
    scopes,
) -> None:
    """A scoped object cannot redirect work via a raw/default session value."""

    async def exercise() -> None:
        repository = ScopeRepository(tmp_path / "scope-v1")
        scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
        gateway = _gateway(repository, scope)

        life = LifeSimulator(persistence=gateway)
        rhythm = RhythmLearner(persistence=gateway)
        social = SocialFieldCollector(persistence=gateway)
        scheduler = ProactiveScheduler(_scheduler_plugin(), persistence=gateway)

        with pytest.raises(ValueError, match="scoped"):
            life.record_user_response("default")
        with pytest.raises(ValueError, match="scoped"):
            rhythm.observe_user_message("default", "text", 1.0, {"warmth": 1.0})
        with pytest.raises(ValueError, match="scoped"):
            social.is_group_context_by_key("default")
        with pytest.raises(ValueError, match="scoped"):
            scheduler.record_feedback("default", 1.0, "positive")

        life.state.current_activity = "stale"
        delayed = life.schedule_scoped_flush(delay_seconds=0.01)
        repository.invalidate_scope(
            scope,
            expected_scope_generation=scope.scope_generation,
            reason="reset",
        )
        assert await delayed is False

    asyncio.run(exercise())


def test_active_scoped_v2_and_v3_shadow_components_restore_and_fence(tmp_path, scopes) -> None:
    """Production V2/V3 constructors use the exact engine components, never KV/files."""

    from sylanne_alpha.v2core.integration import ScopedV2DomainPersistence
    from sylanne_alpha.v3bridge.integration import ScopedV3ShadowState

    class Domain:
        def __init__(self, value: str = "") -> None:
            self.value = value

        def to_dict(self) -> dict[str, object]:
            return {"value": self.value}

        def load_dict(self, payload: dict[str, object]) -> None:
            self.value = str(payload["value"])

    repository = ScopeRepository(tmp_path / "scope-v1")
    left_scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    right_scope = repository.create_scope(scopes.bot_b_persona_a, expected_absent=True)
    left_gateway = _gateway(repository, left_scope)

    first = ScopedV2DomainPersistence(left_gateway)
    domains = {"emotion": Domain("left")}
    assert first.save(domains, behavior_last_fired={"id": 12.0}) == 1
    restored_domain = Domain()
    restored = ScopedV2DomainPersistence(left_gateway)
    assert restored.load_into({"emotion": restored_domain}) == {"id": 12.0}
    assert restored_domain.value == "left"
    assert ScopedV2DomainPersistence(_gateway(repository, right_scope)).load_into({"emotion": Domain()}) == {}

    shadow = ScopedV3ShadowState(left_gateway)
    assert shadow.save({"schema_version": "sylanne.v3.shadow.v1", "state": {"mood": "left"}}) == 1
    assert ScopedV3ShadowState(left_gateway).load() == {
        "schema_version": "sylanne.v3.shadow.v1",
        "state": {"mood": "left"},
    }
    assert ScopedV3ShadowState(_gateway(repository, right_scope)).load() is None

    for component in ("v2", "v3-shadow"):
        snapshot = repository.read_component(left_scope, component)
        assert snapshot is not None
        assert repository.read_component(right_scope, component) is None
        serialized = json.dumps(snapshot.payload, sort_keys=True)
        assert left_scope.storage_token not in serialized
        assert "session_key" not in serialized
        assert "storage_token" not in serialized


def test_scoped_scheduler_preserves_opaque_relation_ritual_path(tmp_path, scopes) -> None:
    """The real relation-token scheduler handoff remains reachable in scoped mode."""

    repository = ScopeRepository(tmp_path / "scope-v1")
    scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    scheduler = ProactiveScheduler(_scheduler_plugin(), persistence=_gateway(repository, scope))
    relation_token = "relation_v1_fixture_relation"
    scheduler.record_scoped_message_time(100.0)
    scheduler.register_ritual(relation_token, "goodnight", 22, 23)
    assert scheduler.flush_scoped_state() == 1

    restored = ProactiveScheduler(_scheduler_plugin(), persistence=_gateway(repository, scope))
    ritual_now = time.mktime((2026, 1, 1, 22, 31, 0, 0, 0, -1))
    assert restored.check_ritual_absence(relation_token, now=ritual_now) == "goodnight"
