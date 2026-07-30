"""Atomic Task-6 runtime cutover contracts."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from main import EmotionalStatePlugin, _V3ShadowFacade
from sylanne_alpha.background_queue import BackgroundPostJob, BackgroundPostQueue
from sylanne_alpha.life_simulation import LifeSimulator
from sylanne_alpha.memory_system import ConversationBuffer, MemorySystem
from sylanne_alpha.proactive_scheduler import ProactiveScheduler
from sylanne_alpha.rhythm_learner import RhythmLearner
from sylanne_alpha.scope_contracts import (
    AuthenticatedSubject,
    RelationRef,
    RelationScope,
    ResolvedScope,
)
from sylanne_alpha.scope_repository import ScopeRepository, ScopedPersistenceGateway
from sylanne_alpha.scope_identity import PersonaSource
from sylanne_alpha.scope_runtime import (
    RelationRuntime,
    RequestRuntimeView,
    ScopeMismatch,
    ScopeRuntimeRegistry,
    ScopedSessionRuntime,
)
from sylanne_alpha.scoped_host_runtime import ScopedHostRuntime
from sylanne_alpha.social_field import SocialFieldCollector
from sylanne_alpha.state_persistence import StatePersistence
from sylanne_alpha.v2core.integration import ScopedV2DomainPersistence
from tests.scope_fixtures import scopes


def test_repository_binding_is_public_one_time_and_precedes_every_runtime(
    tmp_path,
    scopes,
) -> None:
    first = ScopeRepository(tmp_path / "first")
    second = ScopeRepository(tmp_path / "second")
    registry = ScopeRuntimeRegistry.for_test()

    assert registry.repository is None
    registry.bind_repository(first)
    assert registry.repository is first
    registry.bind_repository(first)

    with pytest.raises(ScopeMismatch, match="already bound"):
        registry.bind_repository(second)

    registry.exact_session(scopes.bot_a_persona_a)
    with pytest.raises(ScopeMismatch, match="runtime"):
        registry.bind_repository(first)


def test_repository_cannot_be_bound_after_persona_runtime_exists(tmp_path, scopes) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    registry.for_scope(scopes.bot_a_persona_a)

    with pytest.raises(ScopeMismatch, match="runtime"):
        registry.bind_repository(ScopeRepository(tmp_path / "scope-v1"))


def test_scoped_session_runtime_constructs_every_gateway_bound_owner(
    tmp_path,
    scopes,
) -> None:
    repository = ScopeRepository(tmp_path / "scope-v1")
    scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    gateway = ScopedPersistenceGateway(repository, scope)
    scheduler_plugin = SimpleNamespace()

    session = ScopedSessionRuntime.build(
        scope=scope,
        store=ScopeRuntimeRegistry.for_test().for_scope(scope).store,
        persistence=gateway,
        host_session_factory=lambda frozen: ScopedHostRuntime(
            frozen,
            root=Path(tmp_path / "legacy"),
            profile=None,
            pel_enabled=False,
        ).build_session(),
        memory_system_factory=lambda: MemorySystem(),
        conversation_factory=ConversationBuffer.from_dict,
        background_queue_factory=BackgroundPostQueue,
        life_simulator_factory=lambda frozen: LifeSimulator(
            config={},
            persistence=frozen,
        ),
        rhythm_learner_factory=lambda frozen: RhythmLearner(
            persistence=frozen,
        ),
        social_field_factory=lambda frozen: SocialFieldCollector(
            config={},
            persistence=frozen,
        ),
        proactive_scheduler_factory=lambda frozen: ProactiveScheduler(
            scheduler_plugin,
            persistence=frozen,
        ),
        v2_persistence_factory=ScopedV2DomainPersistence,
    )

    assert session.persistence is gateway
    assert session.host_session.gateway is gateway
    assert session.host is session.host_session.host
    assert session.memory_facade is session.host_session.memory
    assert type(session.memory_system) is MemorySystem
    assert session.conversation_buffer.session_key == scope.storage_token
    assert session.background_queue.persistence is gateway
    assert session.life_simulator.persistence is gateway
    assert session.rhythm_learner.persistence is gateway
    assert session.social_field.persistence is gateway
    assert session.proactive_scheduler.persistence is gateway
    assert session.v2_persistence.persistence is gateway


def test_scoped_session_runtime_rejects_a_sibling_component_factory(
    tmp_path,
    scopes,
) -> None:
    repository = ScopeRepository(tmp_path / "scope-v1")
    left = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    right = repository.create_scope(scopes.bot_b_persona_a, expected_absent=True)
    left_gateway = ScopedPersistenceGateway(repository, left)
    right_gateway = ScopedPersistenceGateway(repository, right)

    with pytest.raises(ScopeMismatch, match="background_queue"):
        ScopedSessionRuntime.build(
            scope=left,
            store=ScopeRuntimeRegistry.for_test().for_scope(left).store,
            persistence=left_gateway,
            host_session_factory=lambda frozen: ScopedHostRuntime(
                frozen,
                root=Path(tmp_path / "legacy"),
                profile=None,
                pel_enabled=False,
            ).build_session(),
            memory_system_factory=MemorySystem,
            conversation_factory=ConversationBuffer.from_dict,
            background_queue_factory=lambda _frozen: BackgroundPostQueue(
                right_gateway
            ),
        )


@pytest.mark.asyncio
async def test_scoped_session_runtime_recovers_its_exact_queue_before_publication(
    tmp_path,
    scopes,
) -> None:
    """A constructed active runtime must restore only its frozen queue."""

    repository = ScopeRepository(tmp_path / "scope-v1")
    scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    gateway = ScopedPersistenceGateway(repository, scope)
    persisted_queue = BackgroundPostQueue(gateway)
    persisted_queue.enqueue(
        BackgroundPostJob(None, "", "restored", "scope", 1, 1.0)
    )
    assert await persisted_queue.save_checkpoint() is True

    registry = ScopeRuntimeRegistry.for_test()
    session = ScopedSessionRuntime.build(
        scope=scope,
        store=registry.for_scope(scope).store,
        persistence=gateway,
        host_session_factory=lambda frozen: ScopedHostRuntime(
            frozen,
            root=Path(tmp_path / "legacy"),
            profile=None,
            pel_enabled=False,
        ).build_session(),
        memory_system_factory=MemorySystem,
        conversation_factory=ConversationBuffer.from_dict,
        background_queue_factory=BackgroundPostQueue,
    )

    restored = session.background_queue.lease_next(now=2.0, lease_seconds=10.0)
    assert restored is not None
    assert restored.reply_text == "restored"


@pytest.mark.asyncio
async def test_releasing_exact_scoped_session_checkpoints_its_queue(
    tmp_path,
    scopes,
) -> None:
    """Release receives a frozen scope and must not lose its queue checkpoint."""

    repository = ScopeRepository(tmp_path / "scope-v1")
    scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)

    def build_session(scope, persona, persistence):
        return ScopedSessionRuntime(
            scope=scope,
            store=persona.store,
            persistence=persistence,
            background_queue=BackgroundPostQueue(persistence),
        )

    registry = ScopeRuntimeRegistry.for_test(
        repository=repository,
        session_runtime_factory=build_session,
    )
    session = registry.exact_session(scope)
    session.background_queue.enqueue(
        BackgroundPostJob(None, "", "checkpointed", "scope", 1, 1.0)
    )

    registry.release_session(scope)

    restarted = BackgroundPostQueue(ScopedPersistenceGateway(repository, scope))
    assert await restarted.recover_queue() is True
    restored = restarted.lease_next(now=2.0, lease_seconds=10.0)
    assert restored is not None
    assert restored.reply_text == "checkpointed"


@pytest.mark.asyncio
async def test_shutdown_checkpoints_each_live_exact_scoped_queue(
    tmp_path,
    scopes,
) -> None:
    """Shutdown saves queue state from exact runtime snapshots, never raw keys."""

    repository = ScopeRepository(tmp_path / "scope-v1")
    scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)

    def build_session(scope, persona, persistence):
        return ScopedSessionRuntime(
            scope=scope,
            store=persona.store,
            persistence=persistence,
            background_queue=BackgroundPostQueue(persistence),
        )

    registry = ScopeRuntimeRegistry.for_test(
        repository=repository,
        session_runtime_factory=build_session,
    )
    session = registry.exact_session(scope)
    session.background_queue.enqueue(
        BackgroundPostJob(None, "", "shutdown", "scope", 1, 1.0)
    )

    plugin = SimpleNamespace(_scope_runtime_registry=registry)
    await EmotionalStatePlugin._save_live_scoped_queue_checkpoints(plugin)

    restarted = BackgroundPostQueue(ScopedPersistenceGateway(repository, scope))
    assert await restarted.recover_queue() is True
    restored = restarted.lease_next(now=2.0, lease_seconds=10.0)
    assert restored is not None
    assert restored.reply_text == "shutdown"


def test_scoped_lifecycle_release_requires_exact_frozen_scope(tmp_path, scopes) -> None:
    """A lifecycle adapter releases only the scope it was explicitly given."""

    repository = ScopeRepository(tmp_path / "scope-v1")
    left = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    right = repository.create_scope(scopes.bot_b_persona_a, expected_absent=True)
    registry = ScopeRuntimeRegistry.for_test(repository=repository)
    registry.exact_session(left)
    registry.exact_session(right)
    persistence = object.__new__(StatePersistence)
    persistence._p = SimpleNamespace(_scope_runtime_registry=registry)
    plugin = SimpleNamespace(_state_persistence=persistence)

    assert EmotionalStatePlugin._release_scoped_session(plugin, left) is True
    assert registry.is_live_session(left) is False
    assert registry.is_live_session(right) is True
    assert EmotionalStatePlugin._release_scoped_session(plugin, left) is False
    assert EmotionalStatePlugin._release_scoped_session(plugin, left.storage_token) is False


@pytest.mark.asyncio
async def test_scoped_session_runtime_restores_memory_and_conversation_before_publication(
    tmp_path,
    scopes,
) -> None:
    repository = ScopeRepository(tmp_path / "scope-v1")
    scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    gateway = ScopedPersistenceGateway(repository, scope)
    persisted_memory = MemorySystem()
    persisted_memory.write("scope-owned memory")
    gateway.save(
        "memory",
        expected_generation=0,
        payload=persisted_memory.to_dict(),
    )
    gateway.save(
        "conversation",
        expected_generation=0,
        payload={
            "session_key": scope.storage_token,
            "messages": [{"role": "user", "text": "scope-owned conversation"}],
            "last_activity": 1.0,
            "turn_count": 0,
            "last_flush_ts": 0.0,
        },
    )

    session = ScopedSessionRuntime.build(
        scope=scope,
        store=ScopeRuntimeRegistry.for_test().for_scope(scope).store,
        persistence=gateway,
        host_session_factory=lambda frozen: ScopedHostRuntime(
            frozen,
            root=Path(tmp_path / "legacy"),
            profile=None,
            pel_enabled=False,
        ).build_session(),
        memory_system_factory=lambda: MemorySystem(),
        conversation_factory=ConversationBuffer.from_dict,
    )

    assert session.memory_system.to_dict() == persisted_memory.to_dict()
    assert session.conversation_buffer.messages == [
        {"role": "user", "text": "scope-owned conversation"}
    ]
    session.memory_system.write("saved after restart")
    assert await session.memory_facade.save_memory(session.memory_system) is True
    reloaded = await session.memory_facade.load_memory()
    assert reloaded is not None
    assert any(item.text == "saved after restart" for item in reloaded._l1)


@pytest.mark.asyncio
async def test_direct_llm_hook_with_registry_requires_subject_carrier_without_resolver() -> None:
    class _Event:
        def __init__(self) -> None:
            self.extras: dict[str, object] = {}

        def get_extra(self, key: str, default=None):
            return self.extras.get(key, default)

        def set_extra(self, key: str, value: object) -> None:
            self.extras[key] = value

    event = _Event()
    plugin = SimpleNamespace(
        _scope_runtime_registry=ScopeRuntimeRegistry.for_test(),
    )

    await EmotionalStatePlugin._on_llm_request_inner(plugin, event, object())

    resolved = event.get_extra("_sylanne_resolved_scope_v1")
    assert type(resolved) is ResolvedScope
    assert resolved.private_scope_enabled is False
    assert resolved.disabled_reason == "turn_subject_proof_mismatch"
    assert plugin._scope_runtime_registry.persona_count == 0
    assert plugin._scope_runtime_registry.session_count == 0


def test_request_view_binds_the_exact_turn_subject_relation(scopes) -> None:
    scope = scopes.bot_a_persona_a
    registry = ScopeRuntimeRegistry.for_test()
    persona = registry.for_scope(scope)
    session = registry.exact_session(scope)
    subject = AuthenticatedSubject(
        relation_ref=RelationRef("relation_v1_subject_a", scope.bot_ref),
        identity_quality="event_get_sender_id",
    )
    other_subject = AuthenticatedSubject(
        relation_ref=RelationRef("relation_v1_subject_b", scope.bot_ref),
        identity_quality="event_get_sender_id",
    )
    relation = RelationRuntime(
        RelationScope(
            bot_ref=scope.bot_ref,
            persona_ref=scope.persona_ref,
            relation_ref=subject.relation_ref,
            relation_generation=0,
        )
    )
    resolved = ResolvedScope(
        scope=scope,
        persona_source=PersonaSource(
            persona_id="task6-view",
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

    RequestRuntimeView(
        resolved=resolved,
        persona_runtime=persona,
        session_runtime=session,
        relation_runtime=relation,
        subject=subject,
    )
    with pytest.raises(ValueError, match="parent scope"):
        RequestRuntimeView(
            resolved=resolved,
            persona_runtime=persona,
            session_runtime=session,
            relation_runtime=relation,
            subject=other_subject,
        )
    with pytest.raises(ValueError, match="missing subject"):
        RequestRuntimeView(
            resolved=resolved,
            persona_runtime=persona,
            session_runtime=session,
            relation_runtime=relation,
            subject=None,
        )


def test_registry_is_the_only_request_view_issuer_and_rejects_whole_view_swap(
    scopes,
) -> None:
    scope = scopes.bot_a_persona_a
    registry = ScopeRuntimeRegistry.for_test()
    persona = registry.for_scope(scope)
    session = registry.exact_session(scope)
    alice = AuthenticatedSubject(
        relation_ref=RelationRef("relation_v1_alice", scope.bot_ref),
        identity_quality="event_get_sender_id",
    )
    bob = AuthenticatedSubject(
        relation_ref=RelationRef("relation_v1_bob", scope.bot_ref),
        identity_quality="event_get_sender_id",
    )
    alice_relation = persona.relation_for(
        RelationScope(
            bot_ref=scope.bot_ref,
            persona_ref=scope.persona_ref,
            relation_ref=alice.relation_ref,
            relation_generation=0,
        )
    )
    bob_relation = persona.relation_for(
        RelationScope(
            bot_ref=scope.bot_ref,
            persona_ref=scope.persona_ref,
            relation_ref=bob.relation_ref,
            relation_generation=0,
        )
    )
    resolved = ResolvedScope(
        scope=scope,
        persona_source=PersonaSource(
            persona_id="task6-issued-view",
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
        turn_generation=7,
    )

    issued = registry.issue_request_view(
        resolved,
        subject=alice,
        relation_runtime=alice_relation,
    )
    forged_bob = RequestRuntimeView(
        resolved=resolved,
        persona_runtime=persona,
        session_runtime=session,
        relation_runtime=bob_relation,
        subject=bob,
    )

    assert registry.is_issued_request_view(issued) is True
    assert registry.is_issued_request_view(forged_bob) is False
    with pytest.raises(ScopeMismatch, match="already issued"):
        registry.issue_request_view(
            resolved,
            subject=bob,
            relation_runtime=bob_relation,
        )


def test_scoped_v3_settlement_accepts_silent_and_fallback_terminal_evidence(
    scopes,
) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    scope = scopes.bot_a_persona_a
    session = registry.exact_session(scope)

    class _State:
        def __init__(self) -> None:
            self.payloads: list[dict[str, object]] = []

        def save(self, payload):
            self.payloads.append(payload)
            return len(self.payloads)

    state = _State()
    object.__setattr__(session, "v3_shadow_state", state)
    current = [
        SimpleNamespace(
            scope=scope,
            session_runtime=session,
            turn_generation=11,
        )
    ]
    plugin = SimpleNamespace(
        _scope_runtime_registry=registry,
        _bound_runtime=lambda: current[0],
    )
    facade = _V3ShadowFacade(plugin)

    assert facade.settle_scoped(
        scope=scope,
        route_kind="SILENT",
        reply_kind="SILENT",
    )
    current[0] = SimpleNamespace(
        scope=scope,
        session_runtime=session,
        turn_generation=12,
    )
    assert facade.settle_scoped(
        scope=scope,
        route_kind="FALLBACK",
        reply_kind="TEXT",
        part_count=1,
        after_message_sent=True,
        all_segments_succeeded=True,
        proactive_dispatched=False,
        token=9,
    )

    assert state.payloads[0]["route_kind"] == "SILENT"
    assert state.payloads[1] == {
        "schema_version": "sylanne.v3-shadow-settlement.v1",
        "route_kind": "FALLBACK",
        "reply_kind": "TEXT",
        "part_count": 1,
        "after_message_sent": True,
        "all_segments_succeeded": True,
        "proactive_dispatched": False,
        "token": 9,
        "turn_generation": 12,
    }
    assert state.payloads[0]["turn_generation"] == 11


def test_request_view_seals_are_bounded_and_terminal_release_invalidates_old_view(
    scopes,
) -> None:
    scope = scopes.bot_a_persona_a
    registry = ScopeRuntimeRegistry.for_test()
    issued: list[RequestRuntimeView] = []
    for generation in range(32):
        resolved = ResolvedScope(
            scope=scope,
            persona_source=PersonaSource(
                persona_id="task6-bounded-seals",
                prompt="quiet",
                begin_dialogs=(),
                tools=None,
                skills=None,
                resolution_source="test",
            ),
            identity_quality="event_self_id",
            resolution_source="test",
            resolved_at_ms=generation + 1,
            private_scope_enabled=True,
            disabled_reason=None,
            turn_generation=generation,
        )
        issued.append(
            registry.issue_request_view(
                resolved,
                subject=None,
                relation_runtime=None,
            )
        )

    assert registry.issued_request_view_count <= 8
    assert registry.is_issued_request_view(issued[0]) is False
    latest = issued[-1]
    assert registry.release_request_view(latest) is True
    assert registry.is_issued_request_view(latest) is False
