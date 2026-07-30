"""RED/green contracts for the active scope-v1 persistence boundary.

These tests deliberately exercise repository-backed objects rather than raw
session strings.  A stale object must stay stale; it must never be rebound to
the runtime which happens to be current when its delayed save runs.
"""

from __future__ import annotations

import ast
import importlib
import json
from dataclasses import FrozenInstanceError, is_dataclass, replace
from pathlib import Path

import pytest

from sylanne_alpha import scope_repository as scope_repository_module
from sylanne_alpha.scope_contracts import RelationRef, RelationScope
from sylanne_alpha.scope_repository import (
    RelationScopedPersistenceGateway,
    ScopeRepository,
    ScopedPersistenceGateway,
    StaleScopeWrite,
)
from tests.scope_fixtures import scopes


def test_session_components_are_allowlisted_and_never_accept_legacy_names(
    tmp_path,
    scopes,
) -> None:
    """Only the bounded scoped component vocabulary may reach disk."""

    repository = ScopeRepository(tmp_path / "scope-v1")
    active = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)

    # This string is path-safe and therefore passed the pre-Task-6 generic
    # component validator.  The scoped repository must reject it nonetheless.
    with pytest.raises(ValueError, match="unsupported scoped component"):
        repository.component_path(active, "legacy-kv")


def test_scoped_gateway_captures_the_exact_session_generation(tmp_path, scopes) -> None:
    """A delayed session save cannot follow reset into the replacement scope."""

    repository = ScopeRepository(tmp_path / "scope-v1")
    active = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    gateway_type = getattr(scope_repository_module, "ScopedPersistenceGateway", None)

    assert gateway_type is not None, "Task 6 needs an immutable session gateway"
    gateway = gateway_type(repository, active)
    assert is_dataclass(gateway)
    with pytest.raises(FrozenInstanceError):
        gateway.scope = active

    assert gateway.save("memory", expected_generation=0, payload={"items": ["old"]}) == 1
    repository.invalidate_scope(
        active,
        expected_scope_generation=active.scope_generation,
        reason="reset",
    )

    with pytest.raises(StaleScopeWrite, match="scope_generation_stale"):
        gateway.save("memory", expected_generation=1, payload={"items": ["late"]})


def test_relation_activation_is_durable_and_fences_every_parent_generation(
    tmp_path,
    scopes,
) -> None:
    """Relation state is exact Bot/Persona/relation state, never a session key."""

    repository = ScopeRepository(tmp_path / "scope-v1")
    session = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    relation_ref = RelationRef(
        token="relation_v1_fixture_subject",
        bot_ref=session.bot_ref,
    )
    activate = getattr(repository, "activate_relation_scope", None)

    assert callable(activate), "Task 6 needs repository-owned relation activation"
    first = activate(session.persona_ref, relation_ref)
    gateway_type = getattr(scope_repository_module, "RelationScopedPersistenceGateway", None)
    assert gateway_type is not None, "Task 6 needs an immutable relation gateway"
    gateway = gateway_type(repository, first)

    assert gateway.save(
        "relationship",
        expected_generation=0,
        payload={"trust": 0.5},
    ) == 1
    retired = repository.invalidate_relation(
        first,
        expected_relation_generation=first.relation_generation,
        reason="purge",
    )
    reactivated = activate(session.persona_ref, relation_ref)
    assert retired.relation_generation == first.relation_generation
    assert reactivated.relation_generation == first.relation_generation + 1

    with pytest.raises(StaleScopeWrite, match="relation_generation_stale"):
        gateway.save(
            "relationship",
            expected_generation=1,
            payload={"trust": 1.0},
        )

    repository.retire_persona_revision(
        session.persona_ref,
        expected_lifecycle_generation=session.persona_ref.lifecycle_generation,
        reason="retire",
    )
    with pytest.raises(StaleScopeWrite, match="persona_lifecycle_stale"):
        repository.read_relation_component(reactivated, "relationship")


def test_persona_reactivation_retires_only_its_prior_relation_lineage(
    tmp_path,
    scopes,
) -> None:
    """A retired Persona epoch cannot leak relation bytes into its successor.

    The restart between retirement and reactivation is deliberate: metadata left
    behind by a stopped process must rebind only through the next authoritative
    Persona lifecycle, while sibling Bot/Persona relation partitions stay live.
    """

    root = tmp_path / "scope-v1"
    repository = ScopeRepository(root)
    target_session = repository.create_scope(
        scopes.bot_a_persona_a,
        expected_absent=True,
    )
    target_relation = RelationRef(
        token="relation_v1_lifecycle_subject",
        bot_ref=target_session.bot_ref,
    )
    old_relation = repository.activate_relation_scope(
        target_session.persona_ref,
        target_relation,
    )
    old_gateway = RelationScopedPersistenceGateway(repository, old_relation)
    assert old_gateway.save(
        "relationship",
        expected_generation=0,
        payload={"trust": 0.5},
    ) == 1

    # The same opaque relation token is intentionally reused beneath a sibling
    # Persona and a different Bot.  They prove retirement walks one exact
    # Bot/Persona relation tree, rather than a token-shaped global namespace.
    sibling_session = repository.create_scope(
        scopes.bot_a_persona_b,
        expected_absent=True,
    )
    sibling_relation = repository.activate_relation_scope(
        sibling_session.persona_ref,
        RelationRef(
            token=target_relation.token,
            bot_ref=sibling_session.bot_ref,
        ),
    )
    assert repository.write_relation_component(
        sibling_relation,
        "relationship",
        expected_generation=0,
        payload={"trust": 0.7},
    ) == 1

    other_bot_session = repository.create_scope(
        scopes.bot_b_persona_a,
        expected_absent=True,
    )
    other_bot_relation = repository.activate_relation_scope(
        other_bot_session.persona_ref,
        RelationRef(
            token=target_relation.token,
            bot_ref=other_bot_session.bot_ref,
        ),
    )
    assert repository.write_relation_component(
        other_bot_relation,
        "relationship",
        expected_generation=0,
        payload={"trust": 0.9},
    ) == 1

    retired = repository.retire_persona_revision(
        target_session.persona_ref,
        expected_lifecycle_generation=target_session.persona_ref.lifecycle_generation,
        reason="persona-retire",
    )
    assert retired.lifecycle_generation == target_session.persona_ref.lifecycle_generation + 1

    # A fresh repository instance exercises the durable recovery path rather
    # than relying on process-local lifecycle state.
    restarted = ScopeRepository(root)
    reactivated_persona = restarted.activate_persona_revision(
        replace(target_session.persona_ref, lifecycle_generation=0)
    )
    reactivated_relation = restarted.activate_relation_scope(
        reactivated_persona,
        target_relation,
    )

    assert reactivated_relation.relation_generation == old_relation.relation_generation + 1
    assert restarted.read_relation_component(reactivated_relation, "relationship") is None
    with pytest.raises(StaleScopeWrite, match="persona_lifecycle_stale"):
        old_gateway.save(
            "relationship",
            expected_generation=1,
            payload={"trust": 1.0},
        )

    sibling_snapshot = restarted.read_relation_component(sibling_relation, "relationship")
    assert sibling_snapshot is not None and sibling_snapshot.payload == {"trust": 0.7}
    other_bot_snapshot = restarted.read_relation_component(
        other_bot_relation,
        "relationship",
    )
    assert other_bot_snapshot is not None and other_bot_snapshot.payload == {"trust": 0.9}


def test_relation_expected_absent_rejects_an_existing_generation_zero_relation(
    tmp_path,
    scopes,
) -> None:
    """A second create cannot smuggle through just because generation is zero."""

    repository = ScopeRepository(tmp_path / "scope-v1")
    session = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    candidate = RelationScope(
        bot_ref=session.bot_ref,
        persona_ref=session.persona_ref,
        relation_ref=RelationRef(
            token="relation_v1_expected_absent",
            bot_ref=session.bot_ref,
        ),
        relation_generation=0,
    )

    assert repository.create_relation_scope(candidate, expected_absent=True) == candidate
    with pytest.raises(StaleScopeWrite, match="relation_exists"):
        repository.create_relation_scope(candidate, expected_absent=True)


def test_scope_invalidation_removes_old_components_before_publishing_generation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    scopes,
) -> None:
    """A crash after durable metadata cannot leave readable old-generation bytes."""

    repository = ScopeRepository(tmp_path / "scope-v1")
    active = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    repository.write_component(
        active,
        "memory",
        expected_generation=0,
        payload={"old": True},
    )
    old_component = repository.component_path(active, "memory")
    original_replace = repository._atomic_json_replace

    def assert_clean_before_publish(path, document, *, owner_only=False):
        if (
            path == repository.scope_meta_path(active)
            and document.get("scope_generation") == active.scope_generation + 1
        ):
            assert old_component.exists() is False
        return original_replace(path, document, owner_only=owner_only)

    monkeypatch.setattr(repository, "_atomic_json_replace", assert_clean_before_publish)

    next_scope = repository.invalidate_scope(
        active,
        expected_scope_generation=active.scope_generation,
        reason="reset",
    )

    assert repository.read_component(next_scope, "memory") is None


def _scoped_host_module():
    try:
        return importlib.import_module("sylanne_alpha.scoped_host_runtime")
    except ModuleNotFoundError:
        return None


def test_scoped_host_runtime_never_touches_legacy_files_or_kv(tmp_path, scopes) -> None:
    """Injected scoped runtime owns host persistence even when given a legacy root."""

    module = _scoped_host_module()
    assert module is not None, "Task 6 needs ScopedAlphaRuntime/ScopedHostRuntime"
    adapter_type = getattr(module, "ScopedHostRuntime", None)
    assert adapter_type is not None

    repository = ScopeRepository(tmp_path / "scope-v1")
    active = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    legacy_root = tmp_path / "legacy"

    class _LegacyKv:
        put_calls: list[object] = []

        async def put_kv_data(self, *_args, **_kwargs) -> None:
            self.put_calls.append((_args, _kwargs))

    legacy_kv = _LegacyKv()
    adapter = adapter_type(
        ScopedPersistenceGateway(repository, active),
        root=legacy_root,
        profile=None,
        pel_enabled=False,
        legacy_kv=legacy_kv,
    )
    host = adapter.build_host()

    host.on_request({"text": "hello", "now": 1.0})
    host.flush()

    assert repository.read_component(active, "host") is not None
    assert list(legacy_root.rglob("*.alpha.json")) == []
    assert list(legacy_root.rglob("*.buffer.json")) == []
    assert legacy_kv.put_calls == []


def test_scoped_host_restart_reads_only_its_frozen_scope_v1_snapshot(
    tmp_path,
    scopes,
) -> None:
    """A new scoped host restores only its own scope-v1 host component."""

    module = _scoped_host_module()
    assert module is not None, "Task 6 needs ScopedHostRuntime"
    adapter_type = getattr(module, "ScopedHostRuntime", None)
    assert adapter_type is not None
    repository = ScopeRepository(tmp_path / "scope-v1")
    active = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    persistence = ScopedPersistenceGateway(repository, active)

    first = adapter_type(
        persistence,
        root=tmp_path / "legacy",
        profile=None,
        pel_enabled=False,
    ).build_host()
    first.on_request({"text": "hello", "now": 1.0})
    first.flush()
    expected = first.snapshot()
    stored = repository.read_component(active, "host")
    assert stored is not None and stored.payload == expected

    legacy_root = tmp_path / "other-legacy-root"
    legacy_root.mkdir()
    (legacy_root / f"{active.storage_token}.alpha.json").write_text(
        json.dumps(
            {
                "schema_version": "sylanne.alpha.body.v1",
                "session_key": active.storage_token,
                "turns": 999,
            }
        ),
        encoding="utf-8",
    )

    restored = adapter_type(
        persistence,
        root=legacy_root,
        profile=None,
        pel_enabled=False,
    ).build_host()

    # AlphaKernel.restore deliberately reconstitutes some derived computation
    # caches, so assert the persisted semantic state rather than cache timing.
    assert restored.kernel.turns == expected["turns"]
    assert restored.kernel.body.to_dict() == expected["body"]
    assert restored.kernel.last_event == expected["last_event"]


def test_scoped_alpha_runtime_rejects_foreign_tokens_and_stale_host_or_buffer_saves(
    tmp_path,
    scopes,
) -> None:
    """Host CoW snapshots carry the captured gateway, not a current-session lookup."""

    module = _scoped_host_module()
    assert module is not None, "Task 6 needs ScopedAlphaRuntime"
    runtime_type = getattr(module, "ScopedAlphaRuntime", None)
    assert runtime_type is not None
    repository = ScopeRepository(tmp_path / "scope-v1")
    active = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    runtime = runtime_type(ScopedPersistenceGateway(repository, active), None, False)

    with pytest.raises(ValueError, match="frozen scope"):
        runtime.load("scope_v1_someone_else")

    kernel = runtime.load(active.storage_token)
    runtime.save(kernel)
    runtime.save_buffer(active.storage_token, {"messages": ["before-reset"]})
    repository.invalidate_scope(
        active,
        expected_scope_generation=active.scope_generation,
        reason="reset",
    )

    with pytest.raises(StaleScopeWrite, match="scope_generation_stale"):
        runtime.save_snapshot(active.storage_token, kernel.snapshot())
    with pytest.raises(StaleScopeWrite, match="scope_generation_stale"):
        runtime.save_buffer(active.storage_token, {"messages": ["late"]})


def test_active_entrypoints_have_no_default_or_raw_session_persistence() -> None:
    root = Path(__file__).parents[1]
    checked = [
        root / "main.py",
        root / "sylanne_alpha" / "background_queue.py",
        root / "sylanne_alpha" / "session_context.py",
        root / "sylanne_alpha" / "memory_system.py",
        root / "sylanne_alpha" / "person_profile.py",
        root / "sylanne_alpha" / "person_shelf.py",
        root / "sylanne_alpha" / "life_simulation.py",
        root / "sylanne_alpha" / "social_field.py",
        root / "sylanne_alpha" / "proactive_scheduler.py",
        root / "sylanne_alpha" / "v2core" / "integration.py",
    ]
    forbidden_calls: list[tuple[str, int, str]] = []
    for path in checked:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            rendered = ast.unparse(node)
            if '"default"' in rendered and (
                "memory_system_for_session" in rendered
                or "session_key" in rendered
                or "most_recent_host_key" in rendered
            ):
                forbidden_calls.append((path.name, node.lineno, rendered))
    assert forbidden_calls == []

    background_source = (root / "sylanne_alpha" / "background_queue.py").read_text(
        encoding="utf-8",
    )
    for forbidden in (
        "checkpoint_kv_key",
        "get_kv_data",
        "put_kv_data",
        "delete_kv_data",
    ):
        assert forbidden not in background_source

    session_context_source = (
        root / "sylanne_alpha" / "session_context.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "_first_interaction_times",
        "_device_fingerprints",
        "_first_impressions",
        "_ritual_registry",
        "_RITUAL_REGISTRY_KV_KEY",
    ):
        assert forbidden not in session_context_source

    main_source = (root / "main.py").read_text(encoding="utf-8")
    main_tree = ast.parse(main_source)
    hook_functions = {
        node.name: node
        for node in ast.walk(main_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name
        in {
            "on_message",
            "on_llm_request",
            "_on_llm_request_inner",
            "_process_llm_request_final",
        }
    }
    def sender_reads(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.Call]:
        return [
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and (
                "get_sender_id" in ast.unparse(node.func)
                or "resolve_authenticated_identity" in ast.unparse(node.func)
            )
        ]

    on_message_calls = sender_reads(hook_functions["on_message"])
    assert on_message_calls == []

    request_hook = hook_functions["_on_llm_request_inner"]
    request_sender_reads = sender_reads(request_hook)
    assert len(request_sender_reads) == 1
    assert "resolve_authenticated_identity" in ast.unparse(
        request_sender_reads[0].func
    )
    prepare_calls = [
        node
        for node in ast.walk(request_hook)
        if isinstance(node, ast.Call)
        and "_prepare_scope_persona" in ast.unparse(node.func)
    ]
    freeze_calls = [
        node
        for node in ast.walk(request_hook)
        if isinstance(node, ast.Call)
        and "_freeze_scope_persona" in ast.unparse(node.func)
    ]
    assert len(prepare_calls) == 1
    assert len(freeze_calls) == 1
    assert (
        prepare_calls[0].lineno
        < request_sender_reads[0].lineno
        < freeze_calls[0].lineno
    )

    request_source = ast.get_source_segment(main_source, request_hook)
    assert request_source is not None
    assert request_source.index("_prepare_scope_persona") < request_source.index(
        "resolve_authenticated_identity"
    ) < request_source.index("_freeze_scope_persona")

    for name in (
        "on_llm_request",
        "_process_llm_request_final",
    ):
        assert sender_reads(hook_functions[name]) == []
