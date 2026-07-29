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
from sylanne_alpha.scope_repository import ScopeRepository, StaleScopeWrite


def _scope(*, generation: int = 0, persona_token: str = "persona_v1_P") -> SessionScope:
    bot = BotRef(token="bot_v1_A", generation=0)
    persona = PersonaRevisionRef(
        token=persona_token,
        bot_ref=bot,
        persona_id_digest="a" * 64,
        source_fingerprint="b" * 64,
        lifecycle_generation=generation,
    )
    session = SessionRef(token="session_v1_S", bot_ref=bot, generation=0)
    return SessionScope(
        bot_ref=bot,
        persona_ref=persona,
        session_ref=session,
        storage_token=f"scope_v1_{persona_token.rsplit('_', 1)[-1]}",
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


def test_scope_resolution_reloads_authoritative_parent_chain(tmp_path: Path) -> None:
    repository = ScopeRepository(tmp_path)
    active = repository.create_scope(_scope(), expected_absent=True)

    reloaded = ScopeRepository(tmp_path).resolve_scope(active.storage_token)

    assert reloaded == active


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
