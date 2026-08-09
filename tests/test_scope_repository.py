from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import pytest

from sylanne_alpha.scope_contracts import (
    BotRef,
    PersonaRevisionRef,
    RelationRef,
    SessionRef,
    SessionScope,
)
from sylanne_alpha.scope_identity import load_or_create_scope_identity_key
from sylanne_alpha.scope_repository import (
    RepositoryCorruptionError,
    ScopeBotNotFound,
    ScopeParentMismatch,
    ScopePersonaNotFound,
    ScopeRepository,
    StaleScopeWrite,
)


def _scope(
    *,
    generation: int = 0,
    bot_token: str = "bot_v1_A",
    persona_token: str = "persona_v1_P",
    session_token: str = "session_v1_S",
) -> SessionScope:
    bot = BotRef(token=bot_token, generation=0)
    persona = PersonaRevisionRef(
        token=persona_token,
        bot_ref=bot,
        persona_id_digest="a" * 64,
        source_fingerprint="b" * 64,
        lifecycle_generation=generation,
    )
    session = SessionRef(token=session_token, bot_ref=bot, generation=0)
    return SessionScope(
        bot_ref=bot,
        persona_ref=persona,
        session_ref=session,
        storage_token=f"scope_v1_{session_token.rsplit('_', 1)[-1]}",
        scope_generation=0,
    )


def test_snapshot_cas_and_local_quarantine_advance_catalog_generation(tmp_path: Path) -> None:
    repository = ScopeRepository(tmp_path)
    components = ("bot_v1_A", "persona_v1_P", "session_v1_S")

    assert repository.write_session(components, expected_generation=0, payload={"value": "A"}) == 1
    with pytest.raises(StaleScopeWrite):
        repository.write_session(components, expected_generation=0, payload={"value": "B"})
    assert repository.read_session(components).payload == {"value": "A"}

    snapshot = repository.session_path(components)
    snapshot.write_text("{broken", encoding="utf-8")

    assert repository.read_session(components) is None
    quarantined = list((snapshot.parent / "quarantine").glob("snapshot.*.corrupt.json"))
    assert len(quarantined) == 1
    assert "bot_v1_A" in str(quarantined[0])
    assert json.loads(repository.catalog_path.read_text(encoding="utf-8"))["generation"] >= 2


def test_scope_identity_key_is_stable_and_corruption_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "identity.key"

    first = load_or_create_scope_identity_key(path)
    second = load_or_create_scope_identity_key(path)

    assert first.key_id == second.key_id
    assert first.secret == second.secret
    path.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="scope identity key"):
        load_or_create_scope_identity_key(path)


def test_webui_principal_issuer_is_stable_domain_separated_and_never_request_created(tmp_path: Path) -> None:
    first = ScopeRepository(tmp_path)
    second = ScopeRepository(tmp_path)

    pages = first.derive_webui_principal_token("pages", "operator")
    assert pages is not None
    assert pages == second.derive_webui_principal_token("pages", "operator")
    assert pages != first.derive_webui_principal_token("standalone", "operator")
    assert "operator" not in pages
    first._webui_principal_secret = None
    assert first.derive_webui_principal_token("pages", "operator") is None


def test_scope_lifecycle_generation_is_not_component_generation(tmp_path: Path) -> None:
    repository = ScopeRepository(tmp_path)
    active = repository.create_scope(_scope(), expected_absent=True)

    assert repository.write_component(
        active,
        "memory",
        expected_generation=0,
        payload={"items": []},
    ) == 1
    unchanged = repository.resolve_scope(active.storage_token)
    invalidated = repository.invalidate_scope(
        active,
        expected_scope_generation=active.scope_generation,
        reason="reset",
    )

    assert unchanged.scope_generation == active.scope_generation
    assert invalidated.scope_generation == active.scope_generation + 1
    assert repository.read_component(invalidated, "memory") is None
    with pytest.raises(StaleScopeWrite, match="scope_generation_stale"):
        repository.invalidate_scope(
            active,
            expected_scope_generation=active.scope_generation,
            reason="purge",
        )


def test_exact_scope_resolver_uses_the_three_opaque_path_tokens(tmp_path: Path) -> None:
    repository = ScopeRepository(tmp_path)
    active = repository.create_scope(_scope(), expected_absent=True)

    assert repository.resolve_exact_scope(
        active.bot_ref.token,
        active.persona_ref.token,
        active.session_ref.token,
    ) == active

    with pytest.raises(KeyError):
        repository.resolve_exact_scope(
            active.bot_ref.token,
            active.persona_ref.token,
            "session_v1_missing",
        )


def test_exact_persona_resolver_is_parent_aware_session_free_and_read_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = ScopeRepository(tmp_path)
    active = repository.activate_persona_revision(_scope().persona_ref)
    foreign = repository.activate_persona_revision(
        _scope(
            bot_token="bot_v1_B",
            persona_token="persona_v1_foreign",
        ).persona_ref
    )
    watched = (
        repository.catalog_path,
        repository.bots_directory / active.bot_ref.token / "manifest.json",
        repository.persona_manifest_path(active),
        repository.bots_directory / foreign.bot_ref.token / "manifest.json",
        repository.persona_manifest_path(foreign),
    )
    before = {path: path.read_bytes() for path in watched}
    monkeypatch.setattr(
        repository,
        "list_active_scopes",
        lambda: (_ for _ in ()).throw(
            AssertionError("Persona resolver must not enumerate Session scopes")
        ),
    )

    assert repository.resolve_exact_persona(
        active.bot_ref.token,
        active.token,
    ) == active
    assert {path: path.read_bytes() for path in watched} == before
    with pytest.raises(ScopeBotNotFound):
        repository.resolve_exact_persona("bot_v1_missing", active.token)
    with pytest.raises(ScopeParentMismatch):
        repository.resolve_exact_persona(active.bot_ref.token, foreign.token)
    with pytest.raises(ScopePersonaNotFound):
        repository.resolve_exact_persona(active.bot_ref.token, "persona_v1_missing")

    repository.retire_persona_revision(
        active,
        expected_lifecycle_generation=active.lifecycle_generation,
        reason="test",
    )
    with pytest.raises(StaleScopeWrite, match="persona_lifecycle_stale"):
        repository.resolve_exact_persona(active.bot_ref.token, active.token)


def test_exact_persona_resolver_hides_retired_foreign_personas_and_propagates_corruption(
    tmp_path: Path,
) -> None:
    repository = ScopeRepository(tmp_path)
    active = repository.activate_persona_revision(_scope().persona_ref)
    foreign = repository.activate_persona_revision(
        _scope(
            bot_token="bot_v1_B",
            persona_token="persona_v1_foreign",
        ).persona_ref
    )
    repository.retire_persona_revision(
        foreign,
        expected_lifecycle_generation=foreign.lifecycle_generation,
        reason="test",
    )

    with pytest.raises(ScopePersonaNotFound):
        repository.resolve_exact_persona(active.bot_ref.token, foreign.token)

    corrupt_foreign = repository.activate_persona_revision(
        _scope(
            bot_token="bot_v1_B",
            persona_token="persona_v1_corrupt_foreign",
        ).persona_ref
    )
    repository.persona_manifest_path(corrupt_foreign).write_text("{broken", encoding="utf-8")
    with pytest.raises(RepositoryCorruptionError):
        repository.resolve_exact_persona(active.bot_ref.token, corrupt_foreign.token)

    repository.persona_manifest_path(active).write_text("{broken", encoding="utf-8")
    with pytest.raises(RepositoryCorruptionError):
        repository.resolve_exact_persona(active.bot_ref.token, active.token)


def test_persona_retirement_reactivation_fences_stale_genesis_writer(tmp_path: Path) -> None:
    repository = ScopeRepository(tmp_path)
    active = repository.activate_persona_revision(_scope().persona_ref)
    retired = repository.retire_persona_revision(
        active,
        expected_lifecycle_generation=active.lifecycle_generation,
        reason="purge",
    )
    recreated = repository.activate_persona_revision(replace(active, lifecycle_generation=0))

    assert retired.token == active.token == recreated.token
    assert recreated.lifecycle_generation == active.lifecycle_generation + 1
    with pytest.raises(StaleScopeWrite, match="persona_lifecycle_stale"):
        repository.write_genesis(
            active,
            expected_lifecycle_generation=active.lifecycle_generation,
            payload={"traits_prior": {}},
        )


def test_relation_activation_recovers_after_persona_retirement_interrupt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A stop after Persona retirement cannot revive prior relation bytes."""

    repository = ScopeRepository(tmp_path)
    session = repository.create_scope(_scope(), expected_absent=True)
    relation_ref = RelationRef(
        token="relation_v1_interrupted_lifecycle",
        bot_ref=session.bot_ref,
    )
    old_relation = repository.activate_relation_scope(session.persona_ref, relation_ref)
    assert repository.write_relation_component(
        old_relation,
        "relationship",
        expected_generation=0,
        payload={"old": True},
    ) == 1
    old_component = repository.relation_component_path(old_relation, "relationship")

    def interrupt_relation_retirement(*_args, **_kwargs) -> None:
        raise OSError("injected relation retirement interruption")

    monkeypatch.setattr(
        repository,
        "_retire_persona_relations_locked",
        interrupt_relation_retirement,
    )
    with pytest.raises(OSError, match="injected relation retirement interruption"):
        repository.retire_persona_revision(
            session.persona_ref,
            expected_lifecycle_generation=session.persona_ref.lifecycle_generation,
            reason="retire",
        )
    assert old_component.exists()

    restarted = ScopeRepository(tmp_path)
    reactivated_persona = restarted.activate_persona_revision(
        replace(session.persona_ref, lifecycle_generation=0)
    )
    reactivated_relation = restarted.activate_relation_scope(
        reactivated_persona,
        relation_ref,
    )

    assert reactivated_relation.relation_generation == old_relation.relation_generation + 1
    assert restarted.read_relation_component(reactivated_relation, "relationship") is None
    assert old_component.exists() is False
    with pytest.raises(StaleScopeWrite, match="persona_lifecycle_stale"):
        restarted.write_relation_component(
            old_relation,
            "relationship",
            expected_generation=1,
            payload={"late": True},
        )


def test_relation_lifecycle_recovery_keeps_static_and_future_parents_fenced(
    tmp_path: Path,
) -> None:
    """Only an older exact Persona lifecycle is eligible for recovery."""

    repository = ScopeRepository(tmp_path)
    session = repository.create_scope(_scope(), expected_absent=True)
    relation_ref = RelationRef(
        token="relation_v1_parent_fence",
        bot_ref=session.bot_ref,
    )
    relation = repository.activate_relation_scope(session.persona_ref, relation_ref)
    metadata_path = repository.relation_meta_path(relation)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    metadata["persona_lifecycle_generation"] = (
        session.persona_ref.lifecycle_generation + 1
    )
    repository._atomic_json_replace(metadata_path, metadata)
    with pytest.raises(ScopeParentMismatch, match="relation metadata parent mismatch"):
        repository.activate_relation_scope(session.persona_ref, relation_ref)

    metadata["persona_lifecycle_generation"] = session.persona_ref.lifecycle_generation
    metadata["persona_ref"] = "persona_v1_foreign"
    repository._atomic_json_replace(metadata_path, metadata)
    with pytest.raises(ScopeParentMismatch, match="relation metadata parent mismatch"):
        repository.activate_relation_scope(session.persona_ref, relation_ref)


def test_scope_resolution_reloads_authoritative_parent_chain(tmp_path: Path) -> None:
    repository = ScopeRepository(tmp_path)
    active = repository.create_scope(_scope(), expected_absent=True)

    reloaded = ScopeRepository(tmp_path).resolve_scope(active.storage_token)

    assert reloaded == active


def test_scope_create_retry_repairs_missing_catalog_registration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = ScopeRepository(tmp_path)
    candidate = _scope()
    original_commit = repository._commit_catalog_generation_locked
    failed_registration = False

    def fail_first_registration(
        *,
        registration: tuple[str, str, str, str] | None = None,
    ) -> int:
        nonlocal failed_registration
        if registration is not None and not failed_registration:
            failed_registration = True
            raise OSError("injected catalog publish failure")
        return original_commit(registration=registration)

    monkeypatch.setattr(
        repository,
        "_commit_catalog_generation_locked",
        fail_first_registration,
    )

    with pytest.raises(OSError, match="injected catalog publish failure"):
        repository.create_scope(candidate)

    assert repository.scope_meta_path(candidate).exists()
    orphaned_catalog = repository._read_catalog_locked()
    assert candidate.storage_token not in orphaned_catalog["scopes"]

    recovered = repository.create_scope(candidate)
    assert repository.resolve_scope(candidate.storage_token) == recovered
    generation_after_repair = repository._read_catalog_locked()["generation"]

    assert repository.create_scope(candidate) == recovered
    assert (
        repository._read_catalog_locked()["generation"]
        == generation_after_repair
    )


def test_scope_root_adapter_uses_only_startools_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from sylanne_alpha import infra

    astrbot = ModuleType("astrbot")
    api = ModuleType("astrbot.api")
    star = ModuleType("astrbot.api.star")

    class _StarTools:
        @staticmethod
        def get_data_dir(name: str) -> Path:
            assert name == "astrbot_plugin_sylanne"
            return tmp_path / "plugin-data"

    star.StarTools = _StarTools
    monkeypatch.setitem(sys.modules, "astrbot", astrbot)
    monkeypatch.setitem(sys.modules, "astrbot.api", api)
    monkeypatch.setitem(sys.modules, "astrbot.api.star", star)
    monkeypatch.setattr(infra, "resolve_data_root", lambda: (_ for _ in ()).throw(AssertionError()))

    assert infra.resolve_scope_v1_root() == tmp_path / "plugin-data" / "scope-v1"


@pytest.mark.parametrize(
    "payload",
    (
        ".",
        "..",
        "../escape",
        "..\\escape",
        "/absolute",
        "C:escape",
        "line\nbreak",
        "é",
    ),
)
def test_all_public_scope_tokens_reject_non_path_safe_payloads(payload: str) -> None:
    bot = BotRef(token="bot_v1_A", generation=0)
    persona = PersonaRevisionRef(
        token="persona_v1_P",
        bot_ref=bot,
        persona_id_digest="a" * 64,
        source_fingerprint="b" * 64,
        lifecycle_generation=0,
    )
    session = SessionRef(token="session_v1_S", bot_ref=bot, generation=0)

    with pytest.raises(ValueError):
        BotRef(token=f"bot_v1_{payload}", generation=0)
    with pytest.raises(ValueError):
        PersonaRevisionRef(
            token=f"persona_v1_{payload}",
            bot_ref=bot,
            persona_id_digest="a" * 64,
            source_fingerprint="b" * 64,
            lifecycle_generation=0,
        )
    with pytest.raises(ValueError):
        SessionRef(token=f"session_v1_{payload}", bot_ref=bot, generation=0)
    with pytest.raises(ValueError):
        RelationRef(token=f"relation_v1_{payload}", bot_ref=bot)
    with pytest.raises(ValueError):
        SessionScope(
            bot_ref=bot,
            persona_ref=persona,
            session_ref=session,
            storage_token=f"scope_v1_{payload}",
            scope_generation=0,
        )


def test_repository_path_helpers_revalidate_tokens_before_computing_paths(
    tmp_path: Path,
) -> None:
    root = tmp_path / "scope-v1"
    repository = ScopeRepository(root)

    with pytest.raises(ValueError):
        repository.session_path(
            (
                "bot_v1_A/../../../../outside",
                "persona_v1_P",
                "session_v1_S",
            )
        )
    with pytest.raises(ValueError):
        repository.transport_catalog_path(
            "bot_v1_A",
            "session_v1_..\\outside",
        )

    assert not (tmp_path.parent / "outside").exists()


def test_exact_scope_resolution_rejects_orphaned_scope_metadata(tmp_path: Path) -> None:
    repository = ScopeRepository(tmp_path)
    active = repository.create_scope(_scope(), expected_absent=True)

    catalog = repository._read_catalog_locked()
    repository._atomic_json_replace(
        repository.catalog_path,
        {
            "schema_version": catalog["schema_version"],
            "generation": int(catalog["generation"]) + 1,
            "scopes": {},
        },
    )

    with pytest.raises(KeyError, match="scope not found"):
        repository.resolve_exact_scope(
            active.bot_ref.token,
            active.persona_ref.token,
            active.session_ref.token,
        )


def test_list_active_scopes_reads_only_authoritative_catalog(tmp_path: Path) -> None:
    repository = ScopeRepository(tmp_path)
    active = repository.create_scope(_scope(), expected_absent=True)

    assert repository.list_active_scopes() == (active,)


def test_list_active_scopes_excludes_retired_persona_registrations(tmp_path: Path) -> None:
    repository = ScopeRepository(tmp_path)
    active = repository.create_scope(_scope(), expected_absent=True)
    repository.retire_persona_revision(
        active.persona_ref,
        expected_lifecycle_generation=active.persona_ref.lifecycle_generation,
        reason="test",
    )

    assert repository.list_active_scopes() == ()
