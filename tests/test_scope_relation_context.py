"""Task-6 ownership contracts for relation and session context state."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from sylanne_alpha.scope_contracts import ResolvedScope, VerifiedSubjectInput
from sylanne_alpha.scope_identity import PersonaSource, ScopeIdentityKey
from sylanne_alpha.scope_repository import ScopeRepository, StaleScopeWrite
from sylanne_alpha.scope_runtime import ScopeRuntimeRegistry
from sylanne_alpha.session_context import SessionContext
from tests.scope_fixtures import scopes


def _identity() -> ScopeIdentityKey:
    return ScopeIdentityKey(key_id="scope-key-relation-context", secret=b"r" * 32)


def _subject(identity: ScopeIdentityKey, scope):
    subject = identity.authenticated_subject(
        scope.bot_ref,
        VerifiedSubjectInput(platform_realm="adapter", subject_id="same-person"),
    )
    assert subject is not None
    return subject


class _BoundPlugin:
    def __init__(self, registry: ScopeRuntimeRegistry, session, relation, data_dir: Path) -> None:
        self._scope_runtime_registry = registry
        self._session = session
        self._relation = relation
        self.config = {"data_dir": str(data_dir)}

    def _active_scoped_session_runtime(self):
        return self._session

    def _active_relation_runtime(self):
        return self._relation


class _RawIdentityTrapStore:
    def __init__(self) -> None:
        self.calls = 0

    def get_authenticated_identity(self, session_key: str):
        del session_key
        self.calls += 1
        raise AssertionError("scoped paths must not read a raw authenticated identity")


class _RecordingRelationScheduler:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int, int]] = []

    def register_ritual(
        self,
        owner_token: str,
        pattern: str,
        hour_start: int,
        hour_end: int,
    ) -> None:
        self.calls.append((owner_token, pattern, hour_start, hour_end))


def test_relation_context_is_shared_per_authenticated_person_and_restores(
    tmp_path,
    scopes,
) -> None:
    repository = ScopeRepository(tmp_path / "scope-v1")
    left_scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    second_scope = repository.create_scope(
        scopes.bot_a_persona_a_second_session,
        expected_absent=True,
    )
    other_persona_scope = repository.create_scope(scopes.bot_a_persona_b, expected_absent=True)
    other_bot_scope = repository.create_scope(scopes.bot_b_persona_a, expected_absent=True)
    identity = _identity()
    registry = ScopeRuntimeRegistry(repository=repository)

    owner = registry.relation_for(left_scope, _subject(identity, left_scope))
    same_person = registry.relation_for(second_scope, _subject(identity, second_scope))
    other_persona = registry.relation_for(
        other_persona_scope,
        _subject(identity, other_persona_scope),
    )
    other_bot = registry.relation_for(other_bot_scope, _subject(identity, other_bot_scope))
    assert owner is not None
    assert owner is same_person
    assert other_persona is not None and other_bot is not None
    assert owner is not other_persona
    assert owner is not other_bot
    assert registry.relation_for(left_scope, None) is None
    assert registry.relation_or_none(owner.scope) is owner

    owner.record_first_interaction(100.0)
    owner.record_first_impression(
        valence=0.8,
        topic_type="deep",
        user_style="brief",
        quality=0.9,
    )
    for _ in range(3):
        owner.observe_ritual(hour=22, pattern="goodnight", observed_at=100.0)
    owner.flush()

    assert owner.first_interaction_time() == 100.0
    assert owner.first_impression() is not None
    assert owner.first_impression().topic_type == "deep"
    assert owner.ritual("goodnight") == {
        "hour_start": 22,
        "hour_end": 23,
        "pattern": "goodnight",
    }
    assert other_persona.first_interaction_time() is None
    assert other_bot.first_impression() is None
    assert other_bot.ritual("goodnight") is None

    restarted_repository = ScopeRepository(tmp_path / "scope-v1")
    restarted_registry = ScopeRuntimeRegistry(repository=restarted_repository)
    restarted_scheduler = _RecordingRelationScheduler()
    restarted_session = restarted_registry.exact_session(left_scope)
    object.__setattr__(
        restarted_session,
        "proactive_scheduler",
        restarted_scheduler,
    )
    restarted_subject = _subject(identity, left_scope)
    restarted = restarted_registry.relation_for(left_scope, restarted_subject)
    assert restarted is not None
    assert restarted.first_interaction_time() == 100.0
    assert restarted.first_impression() is not None
    assert restarted.first_impression().topic_type == "deep"
    assert restarted.ritual("goodnight") == {
        "hour_start": 22,
        "hour_end": 23,
        "pattern": "goodnight",
    }
    assert restarted_registry.relation_or_none(restarted.scope) is restarted
    assert restarted.scope.relation_ref.token.startswith("relation_v1_")
    assert ":" not in restarted.scope.relation_ref.token
    assert "same-person" not in restarted.scope.relation_ref.token
    resolved = ResolvedScope(
        scope=left_scope,
        persona_source=PersonaSource(
            persona_id="relation-context-fixture",
            prompt="quiet",
            begin_dialogs=(),
            tools=None,
            skills=None,
            resolution_source="test",
        ),
        identity_quality="event_self_id",
        resolution_source="test",
        resolved_at_ms=1,
        private_scope_enabled=True,
        disabled_reason=None,
        turn_generation=1,
    )
    issued = restarted_registry.issue_request_view(
        resolved,
        subject=restarted_subject,
        relation_runtime=restarted,
    )
    assert issued.session_runtime is restarted_session
    assert issued.relation_runtime is restarted
    assert restarted_registry.is_issued_request_view(issued) is True
    assert restarted_scheduler.calls == [(restarted.scope.relation_ref.token, "goodnight", 22, 23)]


def test_relation_context_cas_fences_retired_relation_and_persona(tmp_path, scopes) -> None:
    repository = ScopeRepository(tmp_path / "scope-v1")
    active = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    identity = _identity()
    subject = _subject(identity, active)
    registry = ScopeRuntimeRegistry(repository=repository)
    old = registry.relation_for(active, subject)
    assert old is not None
    old.record_first_interaction(10.0)
    assert old.persistence is not None

    old.persistence.purge(reason="test-retire")
    with pytest.raises(StaleScopeWrite, match="relation_generation_stale"):
        old.set_first_interaction_time(20.0)

    replacement = registry.relation_for(active, subject)
    assert replacement is not None and replacement is not old
    replacement.record_first_interaction(30.0)
    repository.retire_persona_revision(
        active.persona_ref,
        expected_lifecycle_generation=active.persona_ref.lifecycle_generation,
        reason="test-persona-retire",
    )
    with pytest.raises(StaleScopeWrite, match="persona_lifecycle_stale"):
        replacement.record_first_impression(
            valence=0.1,
            topic_type="casual",
            user_style="brief",
            quality=0.5,
        )


def test_future_first_interaction_clamps_relation_age_at_zero(tmp_path, scopes) -> None:
    repository = ScopeRepository(tmp_path / "scope-v1")
    active = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    identity = _identity()
    runtime = ScopeRuntimeRegistry(repository=repository).relation_for(
        active,
        _subject(identity, active),
    )
    assert runtime is not None
    runtime.record_first_interaction(1_000.0)
    assert runtime.relationship_stage(now=999.0) == "infant"


def test_device_context_is_session_owned_scoped_and_never_persists_raw_ua(
    tmp_path,
    scopes,
) -> None:
    repository = ScopeRepository(tmp_path / "scope-v1")
    left_scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    right_scope = repository.create_scope(
        scopes.bot_a_persona_a_second_session,
        expected_absent=True,
    )
    registry = ScopeRuntimeRegistry(repository=repository)
    left_session = registry.exact_session(left_scope)
    right_session = registry.exact_session(right_scope)
    raw_desktop = "Mozilla/5.0 (Windows NT 10.0) secret-desktop-device"
    raw_mobile = "Mozilla/5.0 (iPhone; CPU iPhone OS) secret-mobile-device"

    left_device = left_session.device_context_owner()
    right_device = right_session.device_context_owner()
    assert left_device is not None and right_device is not None
    assert left_device.detect_change(raw_desktop) is None
    assert right_device.detect_change(raw_mobile) is None
    assert repository.component_path(left_scope, "device-context") != repository.component_path(
        right_scope, "device-context"
    )

    left_snapshot = repository.read_component(left_scope, "device-context")
    right_snapshot = repository.read_component(right_scope, "device-context")
    assert left_snapshot is not None and right_snapshot is not None
    persisted = json.dumps(
        {"left": left_snapshot.payload, "right": right_snapshot.payload},
        ensure_ascii=False,
    )
    assert raw_desktop not in persisted
    assert raw_mobile not in persisted
    assert left_snapshot.payload["category"] == "desktop"
    assert right_snapshot.payload["category"] == "mobile"
    assert set(left_snapshot.payload) == {"digest", "category"}

    restarted_registry = ScopeRuntimeRegistry(repository=ScopeRepository(tmp_path / "scope-v1"))
    restarted_session = restarted_registry.exact_session(left_scope)
    restarted_device = restarted_session.device_context_owner()
    assert restarted_device is not None
    assert restarted_device.detect_change(raw_desktop) is None
    assert restarted_device.detect_change(raw_mobile) == "换到手机了？我简短些。"


def test_device_context_owner_captures_gateway_and_cannot_follow_new_binding(
    tmp_path,
    scopes,
) -> None:
    repository = ScopeRepository(tmp_path / "scope-v1")
    left_scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    right_scope = repository.create_scope(
        scopes.bot_a_persona_a_second_session,
        expected_absent=True,
    )
    registry = ScopeRuntimeRegistry(repository=repository)
    left_session = registry.exact_session(left_scope)
    right_session = registry.exact_session(right_scope)
    left_device = left_session.device_context_owner()
    right_device = right_session.device_context_owner()
    assert left_device is not None and right_device is not None

    # The owner is constructed before a hypothetical request binding changes.
    # It has no session/token parameter that could be redirected to the right
    # session, and its captured gateway remains the left exact scope.
    assert left_device.gateway == left_session.persistence
    assert right_device.gateway == right_session.persistence
    assert left_device.detect_change("Mozilla/5.0 (Windows NT 10.0) left") is None
    assert left_device.detect_change("Mozilla/5.0 (iPhone) left-mobile") == "换到手机了？我简短些。"
    left_payload = repository.read_component(left_scope, "device-context")
    assert left_payload is not None
    assert repository.read_component(right_scope, "device-context") is None

    # SessionContext's legacy-shaped helper may not route a scoped call through
    # a mutable active-runtime lookup.
    plugin = _BoundPlugin(registry, right_session, None, tmp_path)
    context = SessionContext(plugin)
    assert context.detect_device_change("foreign-session", "Mozilla/5.0 (Android)") is None
    assert repository.read_component(right_scope, "device-context") is None


def test_scoped_person_profile_seed_does_not_fallback_to_raw_identity(tmp_path, scopes) -> None:
    repository = ScopeRepository(tmp_path / "scope-v1")
    scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    registry = ScopeRuntimeRegistry(repository=repository)
    plugin = _BoundPlugin(registry, registry.exact_session(scope), None, tmp_path)
    raw_identity_store = _RawIdentityTrapStore()
    plugin._store = raw_identity_store
    context = SessionContext(plugin)

    context._schedule_person_profile_seed("foreign-session", object(), is_true_birth=True)
    asyncio.run(
        context._seed_person_profile_async(
            "foreign-session",
            object(),
            platform="adapter",
            sender_id="raw-subject",
            is_true_birth=True,
            kernel_last_activity=0.0,
        )
    )

    assert raw_identity_store.calls == 0


def test_session_context_source_has_no_legacy_relation_or_device_state_names() -> None:
    source = Path("sylanne_alpha/session_context.py").read_text(encoding="utf-8")
    for forbidden in (
        "_first_interaction_times",
        "_device_fingerprints",
        "_first_impressions",
        "_ritual_registry",
        "_RITUAL_REGISTRY_KV_KEY",
    ):
        assert forbidden not in source
