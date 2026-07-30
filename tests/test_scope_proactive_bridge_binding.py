"""Exact scoped owner contracts for ProactiveBridge."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from sylanne_alpha.memory_system import MemorySystem
from sylanne_alpha.proactive_bridge import ProactiveBridge
from sylanne_alpha.scope_contracts import RelationRef, RelationScope
from sylanne_alpha.scope_runtime import (
    RelationRuntime,
    ScopeRuntimeRegistry,
)
from sylanne_alpha.session_context import SessionContext
from tests.scope_fixtures import scopes


class _Scheduler:
    def __init__(self) -> None:
        self.tokens: list[str] = []

    def check_ritual_absence(self, relation_token: str):
        self.tokens.append(relation_token)
        return "night"

    def register_ritual(
        self,
        relation_token: str,
        _name: str,
        _start: int,
        _end: int,
    ) -> None:
        self.tokens.append(relation_token)


@pytest.mark.asyncio
async def test_scoped_ritual_reason_uses_bound_session_scheduler_and_relation_token(
    scopes,
) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    scope = scopes.bot_a_persona_a
    session = registry.exact_session(scope)
    scheduler = _Scheduler()
    object.__setattr__(session, "proactive_scheduler", scheduler)
    relation = RelationRuntime(
        RelationScope(
            bot_ref=scope.bot_ref,
            persona_ref=scope.persona_ref,
            relation_ref=RelationRef(
                "relation_v1_proactive_bridge",
                scope.bot_ref,
            ),
            relation_generation=0,
        )
    )
    binding = SimpleNamespace(
        scope=scope,
        session_runtime=session,
        relation_runtime=relation,
    )
    global_scheduler = _Scheduler()
    plugin = SimpleNamespace(
        _scope_runtime_registry=registry,
        _bound_runtime=lambda: binding,
        _proactive_scheduler=global_scheduler,
    )

    result = await ProactiveBridge(plugin).infer_reason_code(scope.storage_token)

    assert result == "ritual"
    assert scheduler.tokens == [relation.scope.relation_ref.token]
    assert global_scheduler.tokens == []


@pytest.mark.asyncio
async def test_scoped_ritual_reason_without_exact_binding_does_not_fallback_global(
    scopes,
) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    registry.exact_session(scopes.bot_a_persona_a)
    global_scheduler = _Scheduler()
    plugin = SimpleNamespace(
        _scope_runtime_registry=registry,
        _bound_runtime=lambda: None,
        _proactive_scheduler=global_scheduler,
    )

    result = await ProactiveBridge(plugin).infer_reason_code(
        scopes.bot_a_persona_a.storage_token
    )

    assert result == "life_rhythm"
    assert global_scheduler.tokens == []


def test_scoped_memory_probe_reads_only_bound_session_owner(scopes) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    scope = scopes.bot_a_persona_a
    session = registry.exact_session(scope)
    owned_memory = MemorySystem()
    object.__setattr__(session, "memory_system", owned_memory)
    binding = SimpleNamespace(scope=scope, session_runtime=session)

    class _Plugin:
        _scope_runtime_registry = registry

        def _bound_runtime(self):
            return binding

        def _memory_system_for_session(self, _session_key):
            raise AssertionError("scoped bridge must not call the raw getter")

        @property
        def _store(self):
            raise AssertionError("scoped bridge must not read a raw store")

    bridge = ProactiveBridge(_Plugin())

    assert bridge._memory_system_if_exists(scope.storage_token) is owned_memory
    assert bridge._memory_system_if_exists("raw-foreign-session") is None


def test_interleaved_shared_relation_ritual_updates_only_current_session_scheduler(
    scopes,
    tmp_path,
) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    first_scope = scopes.bot_a_persona_a
    second_scope = scopes.bot_a_persona_a_second_session
    first_session = registry.exact_session(first_scope)
    second_session = registry.exact_session(second_scope)
    first_scheduler = _Scheduler()
    second_scheduler = _Scheduler()
    object.__setattr__(first_session, "proactive_scheduler", first_scheduler)
    object.__setattr__(second_session, "proactive_scheduler", second_scheduler)
    relation = registry.for_scope(first_scope).relation_for(
        RelationScope(
            bot_ref=first_scope.bot_ref,
            persona_ref=first_scope.persona_ref,
            relation_ref=RelationRef(
                "relation_v1_interleaved",
                first_scope.bot_ref,
            ),
            relation_generation=0,
        )
    )
    current = [
        SimpleNamespace(
            scope=second_scope,
            session_runtime=second_session,
            relation_runtime=relation,
        )
    ]

    class _Plugin:
        _scope_runtime_registry = registry
        config = {"data_dir": str(tmp_path)}

        def _bound_runtime(self):
            return current[0]

        def _active_scoped_session_runtime(self):
            return current[0].session_runtime

        def _active_relation_runtime(self):
            return current[0].relation_runtime

    context = SessionContext(_Plugin())
    current[0] = SimpleNamespace(
        scope=first_scope,
        session_runtime=first_session,
        relation_runtime=relation,
    )
    for offset in range(3):
        context.observe_ritual_pattern(
            first_scope.storage_token,
            22,
            "night",
            observed_at=100.0 + offset,
        )

    assert first_scheduler.tokens == [relation.scope.relation_ref.token]
    assert second_scheduler.tokens == []
