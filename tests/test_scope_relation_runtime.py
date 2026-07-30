"""Task-6 inactive relation runtime contracts."""

from __future__ import annotations

import json

import pytest

from sylanne_alpha.person_profile import (
    PersonProfile,
    load_relation_person_profile,
    save_relation_person_profile,
)
from sylanne_alpha.person_shelf import (
    PersonShelfBucket,
    ShelfItem,
    load_relation_person_shelf,
    save_relation_person_shelf,
)
from sylanne_alpha.relationship_layer import (
    load_relation_relationship_state,
    save_relation_relationship_state,
)
from sylanne_alpha.scope_contracts import VerifiedSubjectInput
from sylanne_alpha.scope_identity import ScopeIdentityKey
from sylanne_alpha.scope_repository import RelationScopedPersistenceGateway, ScopeRepository, StaleScopeWrite
from sylanne_alpha.scope_runtime import ScopeRuntimeRegistry
from tests.scope_fixtures import scopes


def _identity() -> ScopeIdentityKey:
    return ScopeIdentityKey(key_id="scope-key-relation-runtime", secret=b"s" * 32)


def _subject(identity: ScopeIdentityKey, scope):
    subject = identity.authenticated_subject(
        scope.bot_ref,
        VerifiedSubjectInput(platform_realm="adapter", subject_id="same-person"),
    )
    assert subject is not None
    return subject


def test_relation_runtime_shares_exact_person_across_sessions_only_within_bot_persona(tmp_path, scopes) -> None:
    repository = ScopeRepository(tmp_path / "scope-v1")
    first = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    second = repository.create_scope(scopes.bot_a_persona_a_second_session, expected_absent=True)
    other_persona = repository.create_scope(scopes.bot_a_persona_b, expected_absent=True)
    other_bot = repository.create_scope(scopes.bot_b_persona_a, expected_absent=True)
    identity = _identity()
    registry = ScopeRuntimeRegistry(repository=repository)

    left = registry.relation_for(first, _subject(identity, first))
    same_person = registry.relation_for(second, _subject(identity, second))
    isolated_persona = registry.relation_for(other_persona, _subject(identity, other_persona))
    isolated_bot = registry.relation_for(other_bot, _subject(identity, other_bot))

    assert left is not None
    assert left is same_person
    assert left is not isolated_persona
    assert left is not isolated_bot
    assert type(left.persistence) is RelationScopedPersistenceGateway
    assert left.scope.persona_ref == first.persona_ref
    assert registry.relation_for(first, None) is None


def test_relation_runtime_persists_only_opaque_relation_components_and_restarts(tmp_path, scopes) -> None:
    raw_sender = "RAW-SENDER-NEVER-PERSIST"
    raw_platform = "RAW-PLATFORM-NEVER-PERSIST"
    repository = ScopeRepository(tmp_path / "scope-v1")
    active = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    identity = _identity()
    subject = identity.authenticated_subject(
        active.bot_ref,
        VerifiedSubjectInput(platform_realm=raw_platform, subject_id=raw_sender),
    )
    assert subject is not None
    first_registry = ScopeRuntimeRegistry(repository=repository)
    runtime = first_registry.relation_for(active, subject)
    assert runtime is not None and runtime.persistence is not None

    profile_generation = save_relation_person_profile(
        runtime.persistence,
        PersonProfile(preference_count=3),
        expected_generation=0,
    )
    shelf_generation = save_relation_person_shelf(
        runtime.persistence,
        PersonShelfBucket(
            items=[ShelfItem("remember", "private", "origin", 1.0, 1.0)]
        ),
        expected_generation=0,
    )
    relationship_generation = save_relation_relationship_state(
        runtime.persistence,
        {"trust": 0.75},
        expected_generation=0,
    )
    assert (profile_generation, shelf_generation, relationship_generation) == (1, 1, 1)

    restarted = ScopeRuntimeRegistry(repository=ScopeRepository(tmp_path / "scope-v1"))
    recovered = restarted.relation_for(active, subject)
    assert recovered is not None and recovered.persistence is not None
    assert load_relation_person_profile(recovered.persistence).profile.preference_count == 3
    assert len(load_relation_person_shelf(recovered.persistence).bucket.items) == 1
    assert load_relation_relationship_state(recovered.persistence).state == {"trust": 0.75}
    persisted_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in repository.root.rglob("*.json")
    )
    assert raw_sender not in persisted_text
    assert raw_platform not in persisted_text
    assert raw_sender not in json.dumps(runtime.scope.__dict__ if hasattr(runtime.scope, "__dict__") else {})


def test_relation_reactivation_allocates_new_runtime_and_fences_stale_gateway(tmp_path, scopes) -> None:
    repository = ScopeRepository(tmp_path / "scope-v1")
    active = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    identity = _identity()
    subject = _subject(identity, active)
    registry = ScopeRuntimeRegistry(repository=repository)
    old = registry.relation_for(active, subject)
    assert old is not None and old.persistence is not None
    assert old.persistence.save("relationship", expected_generation=0, payload={"before": True}) == 1

    old.persistence.purge(reason="test-retire")
    replacement = registry.relation_for(active, subject)

    assert replacement is not None and replacement.persistence is not None
    assert replacement is not old
    assert replacement.scope.relation_generation == old.scope.relation_generation + 1
    with pytest.raises(StaleScopeWrite, match="relation_generation_stale"):
        old.persistence.save("relationship", expected_generation=1, payload={"late": True})
    assert replacement.persistence.load("relationship") is None


def test_relation_relationship_payload_rejects_raw_identity_beneath_non_string_parent_key(
    tmp_path,
    scopes,
) -> None:
    repository = ScopeRepository(tmp_path / "scope-v1")
    active = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    identity = _identity()
    runtime = ScopeRuntimeRegistry(repository=repository).relation_for(
        active,
        _subject(identity, active),
    )
    assert runtime is not None and runtime.persistence is not None

    with pytest.raises(ValueError, match="raw identity keys"):
        save_relation_relationship_state(
            runtime.persistence,
            {1: {"sender_id": "RAW-SENDER"}},  # type: ignore[dict-item]
            expected_generation=0,
        )
