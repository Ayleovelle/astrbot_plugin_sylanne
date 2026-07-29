"""Regression coverage for exact mutable-runtime ownership."""

from __future__ import annotations

import asyncio
import contextvars
import sys
from dataclasses import replace
from types import ModuleType, SimpleNamespace
from unittest.mock import ANY, AsyncMock, Mock

import pytest

from main import EmotionalStatePlugin
from sylanne_alpha._engine.sylanne_core.compute.host import SylanneAlphaHost
from sylanne_alpha.background_queue import BackgroundPostQueue
from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline
from sylanne_alpha.proactive_scheduler import ProactiveScheduler
from sylanne_alpha.public_api import PublicAPI
from sylanne_alpha.scope_contracts import (
    RelationRef,
    RelationScope,
    ResolvedScope,
    ResolvedTransportScope,
    SessionRef,
)
from sylanne_alpha.scope_identity import PersonaSource
from sylanne_alpha.scope_runtime import (
    ScopeMismatch,
    ScopeRuntimeRegistry,
    ScopeUnavailable,
)
from sylanne_alpha.session_context import SessionContext
from sylanne_alpha.v2core import integration
from sylanne_alpha.webui_routes import WebUIRoutes
from tests.scope_fixtures import scopes


def _transport_scope(scope) -> ResolvedTransportScope:
    return ResolvedTransportScope(
        bot_ref=scope.bot_ref,
        session_ref=scope.session_ref,
        identity_quality="fixture_exact",
        private_scope_enabled=True,
        disabled_reason=None,
    )


def _resolved_scope(scope) -> ResolvedScope:
    return ResolvedScope(
        scope=scope,
        persona_source=PersonaSource(
            persona_id="scope-runtime-test",
            prompt="quiet",
            begin_dialogs=(),
            tools=None,
            skills=None,
            resolution_source="test",
        ),
        identity_quality="verified",
        resolution_source="test",
        resolved_at_ms=1,
        private_scope_enabled=True,
        disabled_reason=None,
        turn_generation=0,
    )


def _persona_plugin() -> EmotionalStatePlugin:
    plugin = object.__new__(EmotionalStatePlugin)
    plugin.config = {
        "sylanne_alpha_autonomy_awake_divisor": 1,
        "sylanne_alpha_autonomy_scan_interval_seconds": 3600,
    }
    plugin._config = plugin.config
    plugin._scope_runtime_binding = contextvars.ContextVar(
        "test_scope_runtime_binding",
        default=None,
    )
    plugin._state_persistence = SimpleNamespace(
        _wire_memory_eviction_persistence=lambda _store: None,
        terminate=AsyncMock(),
    )
    plugin._session_ctx = SimpleNamespace(
        memory_system_for_session=lambda _session: object(),
    )
    noop = lambda *_args, **_kwargs: None
    plugin._llm_request_pipeline = SimpleNamespace(
        _life_sim_llm_call=noop,
        _life_sim_outreach=noop,
        _life_sim_emotion=noop,
        _life_sim_body_delta=noop,
        _life_sim_persona_getter=noop,
        _life_sim_memory_summary=noop,
        _qzone_candidate_handler=noop,
    )
    plugin._scope_runtime_registry = ScopeRuntimeRegistry(
        plugin._create_persona_runtime,
    )
    plugin._background_tasks = []
    plugin._emotion_spirit_bridge = None
    plugin._qzone_audit = None
    plugin._qzone_http_session = None
    plugin._v3_shadow = SimpleNamespace(
        begin_shutdown=Mock(),
        terminate=AsyncMock(),
    )
    return plugin


def test_transport_safety_uses_only_published_exact_runtime_and_fences_stale(
    scopes,
) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    scope = scopes.bot_a_persona_a
    runtime = registry.for_scope(scope)
    session_runtime = registry.exact_session(scope)
    transport = _transport_scope(scope)

    class _Turn:
        interrupted = 0

        def interrupt(self) -> None:
            self.interrupted += 1

    turn = _Turn()
    runtime.store.conversation_input_epoch.set(scope.storage_token, 4)
    runtime.store.segmented_delivery_turns.set(scope.storage_token, turn)
    event = SimpleNamespace(
        extras={},
        set_extra=lambda key, value: event.extras.__setitem__(key, value),
    )
    plugin = SimpleNamespace(_scope_runtime_registry=registry)

    # A frozen runtime is not transport authority until publication succeeds.
    EmotionalStatePlugin._advance_transport_delivery_fence(plugin, event, transport)
    assert runtime.store.conversation_input_epoch.get(scope.storage_token) == 4
    assert turn.interrupted == 0

    assert registry.publish_transport_owner(transport, scope) is True
    owner = registry.transport_owner_or_none(transport)
    assert owner is not None
    assert owner.scope == scope
    assert owner.persona_runtime is runtime
    assert owner.session_runtime is session_runtime

    EmotionalStatePlugin._advance_transport_delivery_fence(plugin, event, transport)
    assert runtime.store.conversation_input_epoch.get(scope.storage_token) == 5
    assert event.extras["_syl_input_epoch"] == 5
    assert turn.interrupted == 1

    unknown_transport = replace(
        transport,
        session_ref=SessionRef(
            token=transport.session_ref.token,
            bot_ref=transport.bot_ref,
            generation=transport.session_ref.generation + 1,
        ),
    )
    EmotionalStatePlugin._advance_transport_delivery_fence(
        plugin,
        event,
        unknown_transport,
    )
    assert runtime.store.conversation_input_epoch.get(scope.storage_token) == 5
    assert turn.interrupted == 1

    registry.release_session(scope)
    assert registry.transport_owner_or_none(transport) is None
    EmotionalStatePlugin._advance_transport_delivery_fence(plugin, event, transport)
    assert turn.interrupted == 1


def test_transport_owner_publication_rejects_late_lower_session_generation(
    scopes,
) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    base = scopes.bot_a_persona_a
    generation_zero = replace(
        base,
        storage_token="scope_v1_transport_generation_zero",
    )
    generation_one = replace(
        base,
        session_ref=SessionRef(
            token=base.session_ref.token,
            bot_ref=base.bot_ref,
            generation=1,
        ),
        storage_token="scope_v1_transport_generation_one",
    )
    registry.exact_session(generation_zero)
    generation_one_runtime = registry.exact_session(generation_one)
    old_transport = _transport_scope(generation_zero)
    new_transport = _transport_scope(generation_one)

    assert registry.publish_transport_owner(old_transport, generation_zero) is True
    assert registry.publish_transport_owner(new_transport, generation_one) is True
    assert registry.transport_owner_or_none(old_transport) is None
    assert registry.publish_transport_owner(old_transport, generation_zero) is False

    owner = registry.transport_owner_or_none(new_transport)
    assert owner is not None
    assert owner.scope == generation_one
    assert owner.session_runtime is generation_one_runtime

    # Releasing the high owner must not reopen rollback while a lower-generation
    # exact session can still issue a late publication.
    registry.release_session(generation_one)
    assert registry.publish_transport_owner(old_transport, generation_zero) is False

    # Once no exact session for the opaque identity remains, lifecycle cleanup
    # may discard the fence and permit a genuinely new owner.
    registry.release_session(generation_zero)
    fresh = replace(
        scopes.bot_a_persona_b,
        session_ref=generation_zero.session_ref,
        storage_token="scope_v1_transport_generation_fresh",
    )
    fresh_runtime = registry.exact_session(fresh)
    assert registry.publish_transport_owner(old_transport, fresh) is True
    fresh_owner = registry.transport_owner_or_none(old_transport)
    assert fresh_owner is not None
    assert fresh_owner.scope == fresh
    assert fresh_owner.session_runtime is fresh_runtime


def test_same_transport_generation_can_follow_a_later_frozen_persona(scopes) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    session_ref = SessionRef(
        token=scopes.bot_a_persona_a.session_ref.token,
        bot_ref=scopes.bot_a_persona_a.bot_ref,
        generation=1,
    )
    first = replace(
        scopes.bot_a_persona_a,
        session_ref=session_ref,
        storage_token="scope_v1_transport_persona_first",
    )
    second = replace(
        scopes.bot_a_persona_b,
        session_ref=session_ref,
        storage_token="scope_v1_transport_persona_second",
    )
    registry.exact_session(first)
    second_runtime = registry.exact_session(second)
    transport = _transport_scope(first)

    assert registry.publish_transport_owner(transport, first) is True
    assert registry.publish_transport_owner(transport, second) is True
    owner = registry.transport_owner_or_none(transport)
    assert owner is not None
    assert owner.scope == second
    assert owner.session_runtime is second_runtime


def test_registry_free_store_seam_cannot_bypass_a_scoped_registry(scopes) -> None:
    plugin = object.__new__(EmotionalStatePlugin)
    legacy_store = SimpleNamespace(owner="registry-free")

    plugin._store = legacy_store
    assert plugin._store is legacy_store

    plugin._scope_runtime_registry = ScopeRuntimeRegistry.for_test()
    plugin._scope_runtime_registry.exact_session(scopes.bot_a_persona_a)
    plugin._scope_runtime_binding = contextvars.ContextVar(
        "test_registry_store_binding",
        default=None,
    )

    with pytest.raises(ScopeUnavailable):
        _ = plugin._store
    with pytest.raises(ScopeUnavailable):
        plugin._store = SimpleNamespace(owner="forbidden")


@pytest.mark.asyncio
async def test_persona_autonomy_owners_activate_independently_and_retire_exactly(
    scopes,
    monkeypatch,
) -> None:
    plugin = _persona_plugin()

    left_scope = scopes.bot_a_persona_a
    right_scope = scopes.bot_a_persona_b
    left = plugin._scope_runtime_registry.for_scope(left_scope)
    right = plugin._scope_runtime_registry.for_scope(right_scope)
    plugin._scope_runtime_registry.exact_session(left_scope)
    plugin._scope_runtime_registry.exact_session(right_scope)

    assert left.self_core is not right.self_core
    assert left.autonomy_scheduler is not right.autonomy_scheduler

    async def _freeze(_plugin, event, _request):
        return event.resolved_scope

    async def _ready(*_args):
        return True

    async def _scope_tail(*_args):
        return None

    monkeypatch.setattr(EmotionalStatePlugin, "_freeze_scope_persona", _freeze)
    monkeypatch.setattr(
        EmotionalStatePlugin,
        "_on_message_after_scope_frozen",
        _ready,
    )
    monkeypatch.setattr(
        EmotionalStatePlugin,
        "_on_scope_ready_llm_request",
        _scope_tail,
    )
    plugin._bind_runtime_for_event = lambda event: plugin._bind_runtime_for_scope(
        event.resolved_scope.scope
    )

    def _event(scope):
        transport = _transport_scope(scope)
        return SimpleNamespace(
            resolved_scope=_resolved_scope(scope),
            get_extra=lambda key: (
                transport if key == "_sylanne_transport_scope_v1" else None
            ),
        )

    # Production request flow starts each frozen Persona owner exactly once.
    await EmotionalStatePlugin._on_llm_request_inner(
        plugin,
        _event(left_scope),
        object(),
    )
    await EmotionalStatePlugin._on_llm_request_inner(
        plugin,
        _event(right_scope),
        object(),
    )

    left_task = left.autonomy_scheduler_task
    right_task = right.autonomy_scheduler_task
    assert left.life_simulator_started is True
    assert right.life_simulator_started is True
    assert left_task is not None and right_task is not None
    assert left_task is not right_task
    assert left_task.cancelled() is False
    assert right_task.cancelled() is False

    host = SimpleNamespace(kernel=SimpleNamespace(surface=lambda: {"owner": "right"}))
    right.store.hosts.set(right_scope.storage_token, host)
    tick = AsyncMock()
    monkeypatch.setattr(right.autonomy_scheduler, "_tick_session", tick)
    monkeypatch.setattr(
        right.autonomy_scheduler.self_core,
        "autonomy_phase",
        lambda _session, _now: right.autonomy_scheduler.self_core.AWAKE,
    )
    run_cycle = AsyncMock()
    monkeypatch.setattr(
        right.autonomy_scheduler.self_core,
        "run_autonomous_cycle",
        run_cycle,
    )

    # The scheduler has no ambient request binding here.  It must still use only
    # the captured PersonaRuntime store and a Persona owner token for global work.
    right.autonomy_scheduler._tick_count = 1
    await right.autonomy_scheduler._scan_once()
    tick.assert_awaited_once()
    assert tick.await_args.args[:2] == (right_scope.storage_token, host)
    run_cycle.assert_awaited_once_with(right.persona_ref.token, {})

    assert plugin._scope_runtime_registry.retire_persona(left_scope) is True
    await asyncio.sleep(0)
    assert left_task.done() is True
    assert left.autonomy_scheduler._task is None
    assert right_task.done() is False
    assert plugin._scope_runtime_registry.for_scope(right_scope) is right

    plugin._scope_runtime_registry.retire_persona(right_scope)
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_terminate_drains_and_consolidates_every_persona_autonomy_owner(
    scopes,
    monkeypatch,
) -> None:
    plugin = _persona_plugin()
    left_scope = scopes.bot_a_persona_a
    right_scope = scopes.bot_a_persona_b
    left = plugin._scope_runtime_registry.for_scope(left_scope)
    right = plugin._scope_runtime_registry.for_scope(right_scope)
    plugin._scope_runtime_registry.exact_session(left_scope)
    plugin._scope_runtime_registry.exact_session(right_scope)

    with plugin._bind_runtime_for_scope(left_scope):
        plugin._start_life_simulator()
    with plugin._bind_runtime_for_scope(right_scope):
        plugin._start_life_simulator()
    left_task = left.autonomy_scheduler_task
    right_task = right.autonomy_scheduler_task
    assert left_task is not None and right_task is not None

    left_consolidate = AsyncMock()
    right_consolidate = AsyncMock()
    left.autonomy_scheduler._consolidation = SimpleNamespace(
        consolidate=left_consolidate,
    )
    right.autonomy_scheduler._consolidation = SimpleNamespace(
        consolidate=right_consolidate,
    )
    stop_webui = AsyncMock()
    monkeypatch.setattr("main.stop_webui_server", stop_webui)

    # terminate() is intentionally unbound.  Reading the plugin-global
    # _autonomy_scheduler property here would raise ScopeUnavailable.
    await plugin.terminate()

    assert left_task.done() is True
    assert right_task.done() is True
    assert left.autonomy_scheduler._task is None
    assert right.autonomy_scheduler._task is None
    left_consolidate.assert_awaited_once_with(left_scope.storage_token, ANY)
    right_consolidate.assert_awaited_once_with(right_scope.storage_token, ANY)
    plugin._state_persistence.terminate.assert_awaited_once()
    stop_webui.assert_awaited_once()


def test_persona_switch_restores_exact_runtime_without_cross_bot_aliasing(scopes) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    a1, b1, a2 = (
        scopes.bot_a_persona_a,
        scopes.bot_a_persona_b,
        scopes.bot_b_persona_a,
    )

    a_runtime = registry.for_scope(a1)
    b_runtime = registry.for_scope(b1)
    other_bot_runtime = registry.for_scope(a2)
    a_runtime.store.last_user_texts.set(a1.storage_token, "A")
    b_runtime.store.last_user_texts.set(b1.storage_token, "B")
    other_bot_runtime.store.last_user_texts.set(a2.storage_token, "other bot")

    assert registry.for_scope(a1) is a_runtime
    assert registry.for_scope(a1).store.last_user_texts.get(a1.storage_token) == "A"
    assert registry.for_scope(b1).store.last_user_texts.get(b1.storage_token) == "B"
    assert registry.for_scope(a2).store.last_user_texts.get(a2.storage_token) == "other bot"
    assert a_runtime is not b_runtime
    assert a_runtime is not other_bot_runtime


def test_releasing_one_scope_does_not_mutate_siblings(scopes) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    left = registry.for_scope(scopes.bot_a_persona_a)
    right = registry.for_scope(scopes.bot_b_persona_a)
    left.store.last_bot_texts.set(scopes.bot_a_persona_a.storage_token, "discard")
    right.store.last_bot_texts.set(scopes.bot_b_persona_a.storage_token, "safe")

    registry.release_session(scopes.bot_a_persona_a)

    assert left.store.last_bot_texts.get(scopes.bot_a_persona_a.storage_token) is None
    assert right.store.last_bot_texts.get(scopes.bot_b_persona_a.storage_token) == "safe"


def test_runtime_never_selects_a_sibling_session(scopes) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    first = scopes.bot_a_persona_a
    second = scopes.bot_a_persona_a_second_session
    registry.for_scope(second).store.last_user_texts.set(second.storage_token, "sibling")

    assert registry.exact_session(first).storage_token == first.storage_token
    assert registry.exact_session_or_none(None) is None
    assert registry.for_scope(first).store.last_user_texts.get(first.storage_token) is None


def test_missing_or_invalid_scope_fails_closed() -> None:
    registry = ScopeRuntimeRegistry.for_test()

    with pytest.raises(ScopeMismatch):
        registry.for_scope(None)
    with pytest.raises(ScopeMismatch):
        registry.exact_session(None)
    with pytest.raises(ScopeMismatch):
        registry.release_session(None)


def test_recreated_persona_generation_never_reuses_old_runtime(scopes) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    original = registry.for_scope(scopes.bot_a_persona_a)
    recreated = registry.for_scope(scopes.bot_a_persona_a_recreated)

    assert original is not recreated
    registry.retire_persona(scopes.bot_a_persona_a)
    assert registry.exact_session_or_none(scopes.bot_a_persona_a) is None
    with pytest.raises(ScopeMismatch):
        registry.for_scope(scopes.bot_a_persona_a)
    with pytest.raises(ScopeMismatch):
        registry.exact_session(scopes.bot_a_persona_a)
    assert registry.persona_count == 1
    assert registry.session_count == 0
    assert registry.for_scope(scopes.bot_a_persona_a_recreated) is recreated


def test_same_storage_token_with_new_scope_generation_has_its_own_session_runtime(
    scopes,
) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    old_scope = scopes.bot_a_persona_a
    new_scope = replace(old_scope, scope_generation=1)

    old_runtime = registry.exact_session(old_scope)
    new_runtime = registry.exact_session(new_scope)
    old_runtime.device_fingerprints["device"] = "old"

    assert old_runtime is not new_runtime
    assert new_runtime.device_fingerprints == {}
    assert registry.session_count == 2


def test_releasing_old_scope_generation_cannot_clear_new_generation_state(scopes) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    old_scope = scopes.bot_a_persona_a
    new_scope = replace(old_scope, scope_generation=1)
    registry.exact_session(old_scope)
    registry.exact_session(new_scope)
    store = registry.for_scope(new_scope).store
    store.last_user_texts.set(new_scope.storage_token, "new generation")

    registry.release_session(old_scope)

    assert store.last_user_texts.get(new_scope.storage_token) == "new generation"
    assert registry.session_count == 1


def test_late_old_generation_cannot_replace_or_release_new_session(scopes) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    old_scope = scopes.bot_a_persona_a
    new_scope = replace(old_scope, scope_generation=1)
    registry.exact_session(new_scope)
    store = registry.for_scope(new_scope).store
    store.last_user_texts.set(new_scope.storage_token, "new generation")

    with pytest.raises(ScopeMismatch):
        registry.exact_session(old_scope)
    registry.release_session(old_scope)

    assert store.last_user_texts.get(new_scope.storage_token) == "new generation"
    assert registry.exact_session(new_scope).storage_token == new_scope.storage_token


def test_wrong_persona_queue_cannot_write_the_bound_persona_scope(scopes) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    left_scope = scopes.bot_a_persona_a
    right_scope = scopes.bot_a_persona_b
    left_runtime = registry.for_scope(left_scope)
    right_runtime = registry.for_scope(right_scope)
    registry.exact_session(left_scope)
    registry.exact_session(right_scope)

    class _Plugin:
        _scope_runtime_registry = registry

        def __init__(self) -> None:
            self.binding = SimpleNamespace(
                scope=right_scope,
                persona_runtime=right_runtime,
            )

        def _bound_runtime(self):
            return self.binding

    plugin = _Plugin()
    left_queue = BackgroundPostQueue(
        plugin,
        owner_persona_ref=left_scope.persona_ref,
    )
    left_runtime.background_queue = left_queue

    decision = left_queue.adaptive_worker_decision(right_scope.storage_token)

    assert decision["dispatch_workers"] == 0
    assert decision["reasons"] == ["scope_unavailable"]


def test_v2core_same_raw_session_isolated_by_full_scope(scopes, tmp_path) -> None:
    class _ScopedPlugin:
        def __init__(self) -> None:
            self._config: dict[str, object] = {}
            self._scope_runtime_registry = ScopeRuntimeRegistry.for_test()
            self._hosts: dict[str, SylanneAlphaHost] = {}

        def _host_for_scope(self, scope):
            host = self._hosts.get(scope.storage_token)
            if host is None:
                host = SylanneAlphaHost(
                    root=str(tmp_path),
                    session_key=scope.storage_token,
                )
                self._hosts[scope.storage_token] = host
            return host

        def _memory_system_for_scope(self, _scope):
            return None

    plugin = _ScopedPlugin()

    left = integration.runtime_for(plugin, scopes.bot_a_persona_a)
    right = integration.runtime_for(plugin, scopes.bot_b_persona_a)

    assert left is not right
    assert left["storage_token"] != right["storage_token"]


def test_scoped_audit_amnesia_and_scheduler_task_have_no_global_owner(scopes) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    scope = scopes.bot_a_persona_a
    persona_runtime = registry.for_scope(scope)
    session_runtime = registry.exact_session(scope)

    class _Plugin:
        _scope_runtime_registry = registry
        config = {
            "enable_proactive_speech_dispatch": True,
            "proactive_speech_dispatch_cooldown_seconds": 10.0,
        }

        def _bound_runtime(self):
            return SimpleNamespace(
                scope=scope,
                persona_runtime=persona_runtime,
                session_runtime=session_runtime,
            )

    plugin = _Plugin()
    pipeline = LLMRequestPipeline(plugin)

    pipeline._record_dispatch_feedback(scope.storage_token, "unanswered", "event-1")
    pipeline._record_dispatch_feedback("sibling-session", "unanswered", "wrong-owner")

    audit = persona_runtime.store.proactive_dispatch_audit.get(scope.storage_token)
    assert len(audit) == 1
    assert audit[0]["feedback_status"] == "unanswered"
    assert audit[0]["event_id"] == "event-1"
    policy = ProactiveScheduler(plugin).derive_dispatch_policy(
        session_key=scope.storage_token
    )
    assert policy["feedback_pressure"] == pytest.approx(0.3)

    persona_runtime.store.amnesia_pending.set(scope.storage_token, True)
    assert pipeline._take_amnesia_pending(scope.storage_token) is True
    persona_runtime.store.amnesia_pending.set(scope.storage_token, True)
    assert pipeline._take_amnesia_pending("sibling-session") is False
    assert persona_runtime.store.amnesia_pending.get(scope.storage_token) is True

    class _Task:
        cancelled = False

        def cancel(self) -> None:
            self.cancelled = True

    task = _Task()
    persona_runtime.proactive_scheduler_task = task
    registry.release_session(scope)

    assert persona_runtime.store.proactive_dispatch_audit.get(scope.storage_token) is None
    assert persona_runtime.store.amnesia_pending.get(scope.storage_token) is None
    registry.retire_persona(scope)
    assert task.cancelled is True


def test_relation_observations_noop_without_authenticated_relation_scope(
    scopes, tmp_path
) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    scope = scopes.bot_a_persona_a
    persona_runtime = registry.for_scope(scope)
    session_runtime = registry.exact_session(scope)

    class _Plugin:
        _scope_runtime_registry = registry
        config = {"data_dir": str(tmp_path)}

        def __init__(self) -> None:
            self.put_calls: list[tuple[object, object]] = []

        def _active_scoped_session_runtime(self):
            return session_runtime

        def _active_relation_runtime(self):
            return None

        def _has_kv_api(self) -> bool:
            return True

        async def put_kv_data(self, key, value) -> None:
            self.put_calls.append((key, value))

    plugin = _Plugin()
    context = SessionContext(plugin)

    context.record_first_impression(scope.storage_token, 0.8, "deep", "brief", 0.9)
    context.observe_ritual_pattern(scope.storage_token, 9, "morning_greeting")
    context.accelerate_relationship(scope.storage_token, 1.0)

    assert context._legacy_first_impressions is None
    assert context._legacy_first_interaction_times is None
    assert context._legacy_ritual_registry is None
    assert plugin.put_calls == []
    assert persona_runtime.relation_runtimes == {}


def test_public_session_reader_never_falls_back_to_global_in_scoped_runtime(
    scopes, tmp_path
) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    scope = scopes.bot_a_persona_a
    registry.for_scope(scope)
    session_runtime = registry.exact_session(scope)

    class _Plugin:
        _scope_runtime_registry = registry
        config = {"data_dir": str(tmp_path)}

        def __init__(self) -> None:
            self.active = session_runtime

        def _active_scoped_session_runtime(self):
            return self.active

    plugin = _Plugin()
    context = SessionContext(plugin)

    assert context.resolve_public_session_key(event="foreign-session") == scope.storage_token
    with pytest.raises(ValueError):
        context.resolve_public_session_key(session_key="foreign-session")
    plugin.active = None
    with pytest.raises(ValueError):
        context.resolve_public_session_key()


def test_relation_runtimes_and_rituals_are_exactly_isolated(scopes, tmp_path) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    scope = scopes.bot_a_persona_a
    registry.for_scope(scope)
    session_runtime = registry.exact_session(scope)
    left_scope = RelationScope(
        bot_ref=scope.bot_ref,
        persona_ref=scope.persona_ref,
        relation_ref=RelationRef("relation_v1_fixture_left", scope.bot_ref),
        relation_generation=0,
    )
    right_scope = RelationScope(
        bot_ref=scope.bot_ref,
        persona_ref=scope.persona_ref,
        relation_ref=RelationRef("relation_v1_fixture_right", scope.bot_ref),
        relation_generation=0,
    )
    left = registry.relation_or_none(left_scope)
    right = registry.relation_or_none(right_scope)
    assert left is not None and right is not None and left is not right

    class _Plugin:
        _scope_runtime_registry = registry
        config = {"data_dir": str(tmp_path)}

        def __init__(self) -> None:
            self.relation = left

        def _active_scoped_session_runtime(self):
            return session_runtime

        def _active_relation_runtime(self):
            return self.relation

    plugin = _Plugin()
    context = SessionContext(plugin)
    context.record_first_impression(scope.storage_token, 0.8, "deep", "brief", 0.9)
    first = context.first_interaction_time(scope.storage_token)
    context.accelerate_relationship(scope.storage_token, 1.0)
    assert context.first_interaction_time(scope.storage_token) < first
    for _ in range(3):
        context.observe_ritual_pattern(scope.storage_token, 9, "morning_greeting")

    plugin.relation = right
    context.record_first_impression(scope.storage_token, -0.2, "casual", "verbose", 0.4)
    for _ in range(3):
        context.observe_ritual_pattern(scope.storage_token, 22, "night_farewell")

    assert left.first_impressions is not right.first_impressions
    assert left.ritual_registry is not None
    assert right.ritual_registry is not None
    assert left.ritual_registry is not right.ritual_registry
    assert left.ritual_registry.get_ritual("_relation", "morning_greeting") is not None
    assert left.ritual_registry.get_ritual("_relation", "night_farewell") is None
    assert right.ritual_registry.get_ritual("_relation", "night_farewell") is not None


@pytest.mark.asyncio
async def test_observatory_routes_require_bound_scope_and_use_exact_token(scopes) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    scope = scopes.bot_a_persona_a
    persona_runtime = registry.for_scope(scope)
    session_runtime = registry.exact_session(scope)
    persona_runtime.store.last_understanding_closed_loop.set(
        scope.storage_token,
        {
            "turning_point_lineage_observatory": {
                "lineage": {"owner": scope.storage_token},
                "branches": [],
            }
        },
    )

    class _Plugin:
        _scope_runtime_registry = registry
        config: dict[str, object] = {}

        def __init__(self) -> None:
            self.binding = None
            self._public_api = _ProbePublicAPI(self)

        def _bound_runtime(self):
            return self.binding

        @property
        def _store(self):
            if self.binding is None:
                raise AssertionError("unbound route must not access a private store")
            return self.binding.persona_runtime.store

        async def _lineage_observatory_handler(self) -> dict[str, object]:
            return self._public_api._lineage_observatory_route_payload()

    class _ProbePublicAPI(PublicAPI):
        async def sylanne_observatory(self, *, session_key: str) -> dict[str, str]:
            return {"session_key": session_key}

    plugin = _Plugin()
    routes = WebUIRoutes(plugin)

    assert await plugin._public_api._observatory_route_handler() == {
        "ok": False,
        "error": "scope_unavailable",
    }
    assert plugin._public_api._lineage_observatory_route_payload() == {
        "ok": False,
        "error": "scope_unavailable",
    }
    assert await routes.lineage_observatory_handler() == {
        "ok": False,
        "error": "scope_unavailable",
    }
    assert await plugin._public_api.get_agent_runtime_diagnostics("foreign-session") == {
        "ok": False,
        "error": "scope_unavailable",
    }
    assert await plugin._public_api.observe_user_message_withdrawal(
        session_key="foreign-session"
    ) == {"ok": False, "error": "scope_unavailable"}

    plugin.binding = SimpleNamespace(
        scope=scope,
        persona_runtime=persona_runtime,
        session_runtime=session_runtime,
    )

    assert await plugin._public_api._observatory_route_handler() == {
        "session_key": scope.storage_token,
    }
    payload = plugin._public_api._lineage_observatory_route_payload()
    assert payload["lineage"] == {"owner": scope.storage_token}
    assert await routes.lineage_observatory_handler() == payload
    assert await plugin._public_api.get_agent_runtime_diagnostics(
        "foreign-session"
    ) == {"ok": False, "error": "scope_unavailable"}
    diagnostics = await plugin._public_api.get_agent_runtime_diagnostics(
        scope.storage_token,
        include_sessions=True,
    )
    assert diagnostics["sessions"] == [scope.storage_token]
    assert await plugin._public_api.observe_user_message_withdrawal(
        session_key="foreign-session"
    ) == {"ok": False, "error": "scope_unavailable"}
    withdrawal = await plugin._public_api.observe_user_message_withdrawal(
        session_key=scope.storage_token,
        message_id="message_v1_fixture",
    )
    assert withdrawal["input_epoch"] == 1
    assert persona_runtime.store.conversation_input_epoch.get(scope.storage_token) == 1


@pytest.mark.asyncio
async def test_scoped_webui_state_and_memory_routes_reject_raw_selection(
    scopes, monkeypatch
) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    scope = scopes.bot_a_persona_a
    persona_runtime = registry.for_scope(scope)
    session_runtime = registry.exact_session(scope)

    class _Plugin:
        _scope_runtime_registry = registry

        def __init__(self) -> None:
            self.binding = None

        def _bound_runtime(self):
            return self.binding

    plugin = _Plugin()
    routes = WebUIRoutes(plugin)
    web = ModuleType("astrbot.api.web")
    web.request = SimpleNamespace(query={})
    monkeypatch.setitem(sys.modules, "astrbot.api.web", web)

    assert routes._bound_webui_session_key() is None
    assert await routes.state_handler() == {
        "ok": False,
        "error": "scope_unavailable",
    }
    assert await routes.memory_pools_handler() == {
        "ok": False,
        "error": "scope_unavailable",
    }

    plugin.binding = SimpleNamespace(
        scope=scope,
        persona_runtime=persona_runtime,
        session_runtime=session_runtime,
    )
    assert routes._bound_webui_session_key() == scope.storage_token
    assert routes._bound_webui_session_key("foreign-session") is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler_name", "query", "body"),
    [
        ("state_handler", {"session": "foreign-session"}, {}),
        ("observation_history_handler", {"session": "foreign-session"}, {}),
        ("computation_logs_handler", {"session": "foreign-session"}, {}),
        ("memory_pools_handler", {"session": "foreign-session"}, {}),
        ("memory_meltdown_handler", {}, {"session": "foreign-session"}),
        ("meltdown_nonce_handler", {"session": "foreign-session"}, {}),
        ("memory_consolidate_handler", {}, {"session": "foreign-session"}),
        ("memory_sink_handler", {"session": "foreign-session"}, {}),
        ("life_status_handler", {}, {}),
        ("life_events_handler", {}, {}),
        ("life_projects_handler", {}, {}),
        ("life_audit_handler", {}, {}),
        ("life_diagnostics_handler", {}, {}),
        ("life_controls_handler", {}, {"action": "clear_journal"}),
        ("export_data_handler", {"session_key": "foreign-session"}, {}),
        ("purge_data_handler", {"session_key": "foreign-session"}, {}),
        ("widget_state_handler", {}, {}),
        ("v2core_state_handler", {"session": "foreign-session"}, {}),
        ("admin_inspect_handler", {"session": "foreign-session"}, {}),
        ("admin_quarantine_view_handler", {"session": "foreign-session"}, {}),
        ("admin_pending_deletes_handler", {}, {}),
        (
            "proactive_feedback_handler",
            {},
            {
                "session_key": "foreign-session",
                "timestamp": 0,
                "rating": "positive",
            },
        ),
        ("weekly_report_handler", {}, {}),
        ("memory_decay_curve_handler", {"memory_id": "memory_v1_fixture"}, {}),
        ("personality_export_handler", {}, {}),
        ("personality_import_handler", {}, {"embodiment_five": {}}),
    ],
)
async def test_scoped_private_webui_handlers_fail_closed_without_binding(
    handler_name, query, body, monkeypatch, scopes
) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    registry.exact_session(scopes.bot_a_persona_a)

    class _Plugin:
        _scope_runtime_registry = registry

        def _bound_runtime(self):
            return None

    async def _json():
        return body

    web = ModuleType("astrbot.api.web")
    web.request = SimpleNamespace(query=query, json=_json)
    monkeypatch.setitem(sys.modules, "astrbot.api.web", web)

    result = await getattr(WebUIRoutes(_Plugin()), handler_name)()

    assert result == {"ok": False, "error": "scope_unavailable"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler_name", "query", "body"),
    [
        ("state_handler", {"session": "foreign-session"}, {}),
        ("observation_history_handler", {"session": "foreign-session"}, {}),
        ("computation_logs_handler", {"session": "foreign-session"}, {}),
        ("memory_pools_handler", {"session": "foreign-session"}, {}),
        ("memory_meltdown_handler", {}, {"session": "foreign-session"}),
        ("meltdown_nonce_handler", {"session": "foreign-session"}, {}),
        ("memory_consolidate_handler", {}, {"session": "foreign-session"}),
        ("memory_sink_handler", {"session": "foreign-session"}, {}),
        ("export_data_handler", {"session_key": "foreign-session"}, {}),
        ("purge_data_handler", {"session_key": "foreign-session"}, {}),
        ("v2core_state_handler", {"session": "foreign-session"}, {}),
        ("admin_inspect_handler", {"session": "foreign-session"}, {}),
        ("admin_quarantine_view_handler", {"session": "foreign-session"}, {}),
        (
            "proactive_feedback_handler",
            {},
            {
                "session_key": "foreign-session",
                "timestamp": 0,
                "rating": "positive",
            },
        ),
    ],
)
async def test_scoped_webui_handlers_reject_foreign_session_with_live_binding(
    handler_name, query, body, monkeypatch, scopes
) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    scope = scopes.bot_a_persona_a
    persona_runtime = registry.for_scope(scope)
    session_runtime = registry.exact_session(scope)

    class _Plugin:
        _scope_runtime_registry = registry

        def _bound_runtime(self):
            return SimpleNamespace(
                scope=scope,
                persona_runtime=persona_runtime,
                session_runtime=session_runtime,
            )

    async def _json():
        return body

    web = ModuleType("astrbot.api.web")
    web.request = SimpleNamespace(query=query, json=_json)
    monkeypatch.setitem(sys.modules, "astrbot.api.web", web)

    result = await getattr(WebUIRoutes(_Plugin()), handler_name)()

    assert result == {"ok": False, "error": "scope_unavailable"}
