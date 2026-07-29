from __future__ import annotations

from pathlib import Path

import pytest

from sylanne_alpha.scope_contracts import (
    BotRef,
    PersonaRevisionRef,
    ResolvedTransportScope,
    SessionRef,
    SessionScope,
)
from sylanne_alpha.scope_identity import BotBinding, load_or_create_scope_identity_key
from sylanne_alpha.scope_repository import ScopeRepository
from sylanne_alpha.session_catalog import ProtectedDeliveryBinding, SessionCatalog


def _transport(bot: BotRef) -> ResolvedTransportScope:
    return ResolvedTransportScope(
        bot_ref=bot,
        session_ref=SessionRef(token="session_v1_S", bot_ref=bot, generation=0),
        identity_quality="event_self_id",
        private_scope_enabled=True,
        disabled_reason=None,
    )


def _scope(*, bot: BotRef, persona_token: str) -> SessionScope:
    transport = _transport(bot)
    persona = PersonaRevisionRef(
        token=persona_token,
        bot_ref=transport.bot_ref,
        persona_id_digest="a" * 64,
        source_fingerprint=("b" if persona_token.endswith("A") else "c") * 64,
        lifecycle_generation=0,
    )
    return SessionScope(
        bot_ref=transport.bot_ref,
        persona_ref=persona,
        session_ref=transport.session_ref,
        storage_token=f"scope_v1_{persona_token.rsplit('_', 1)[-1]}",
        scope_generation=0,
    )


def _binding(*, binding_generation: int = 0) -> ProtectedDeliveryBinding:
    return ProtectedDeliveryBinding(
        platform_id="private-platform-id",
        self_id="private-self-id",
        message_session="private:FriendMessage:42",
        target_address="private-target-address",
        adapter_capability="reactive_only",
        account_proof_digest="proof-v1",
        account_proof_generation=0,
        account_proof_expires_at_ms=1,
        binding_generation=binding_generation,
    )


def _registered_bot(catalog: SessionCatalog, root: Path) -> BotRef:
    generation = catalog.binding_generation(
        "private-platform-id",
        "private-self-id",
    )
    key = load_or_create_scope_identity_key(root / "identity.key")
    return key.bot_ref(
        BotBinding(
            platform_id="private-platform-id",
            self_id="private-self-id",
        ),
        generation,
    )


def _current_proof(
    *,
    digest: str = "proof-v1",
    generation: int = 0,
    now_ms: int = 0,
) -> dict[str, object]:
    return {
        "current_account_proof_digest": digest,
        "current_account_proof_generation": generation,
        "now_ms": now_ms,
    }


def test_transport_catalog_persists_monotonic_turn_and_fails_closed_after_resolving_restart(
    tmp_path: Path,
) -> None:
    repository = ScopeRepository(tmp_path)
    catalog = SessionCatalog(repository)
    bot = _registered_bot(catalog, tmp_path)
    scope = repository.create_scope(
        _scope(bot=bot, persona_token="persona_v1_A"),
        expected_absent=True,
    )

    first = catalog.begin_turn(_transport(bot), _binding())
    frozen = catalog.freeze_persona(first, scope)

    restarted = SessionCatalog(ScopeRepository(tmp_path))
    restored = restarted.current(_transport(bot).session_ref.token)
    assert restored.turn_generation == frozen.turn_generation
    assert restored.turn_state == "frozen"
    assert restored.active_persona_ref == scope.persona_ref.token

    second = restarted.begin_turn(_transport(bot), _binding())
    unresolved = SessionCatalog(ScopeRepository(tmp_path)).current(
        _transport(bot).session_ref.token
    )
    assert second.turn_generation == frozen.turn_generation + 1
    assert unresolved.turn_state == "resolving"
    assert SessionCatalog(ScopeRepository(tmp_path)).can_issue_proactive(unresolved) is False


def test_a_to_b_to_a_allocates_a_fresh_persisted_turn_generation(tmp_path: Path) -> None:
    repository = ScopeRepository(tmp_path)
    catalog = SessionCatalog(repository)
    bot = _registered_bot(catalog, tmp_path)
    scope_a = repository.create_scope(
        _scope(bot=bot, persona_token="persona_v1_A"),
        expected_absent=True,
    )
    scope_b = repository.create_scope(
        _scope(bot=bot, persona_token="persona_v1_B"),
        expected_absent=True,
    )

    generations = []
    for scope in (scope_a, scope_b, scope_a):
        turn = catalog.begin_turn(_transport(bot), _binding())
        generations.append(catalog.freeze_persona(turn, scope).turn_generation)

    assert generations == sorted(set(generations))


def test_catalog_accepts_only_opaque_session_token_and_never_exposes_delivery_secret(
    tmp_path: Path,
) -> None:
    repository = ScopeRepository(tmp_path)
    catalog = SessionCatalog(repository)
    bot = _registered_bot(catalog, tmp_path)
    scope = repository.create_scope(
        _scope(bot=bot, persona_token="persona_v1_A"),
        expected_absent=True,
    )
    turn = catalog.begin_turn(_transport(bot), _binding())
    catalog.freeze_persona(turn, scope)

    with pytest.raises(ValueError):
        catalog.current("not-an-opaque-session-token")
    assert "private-platform-id" not in repr(_binding())
    assert "private-target-address" not in repr(catalog.current("session_v1_S"))

    binding_path = repository.transport_delivery_binding_path(bot.token, "session_v1_S")
    assert "private-platform-id" not in str(binding_path)
    assert binding_path.exists()


def test_binding_authority_is_opaque_and_restart_stable(tmp_path: Path) -> None:
    repository = ScopeRepository(tmp_path)
    catalog = SessionCatalog(repository)

    first = catalog.binding_generation("private-platform-id", "private-self-id")
    restarted = SessionCatalog(ScopeRepository(tmp_path))
    second = restarted.binding_generation("private-platform-id", "private-self-id")

    assert first == second == 0
    for path in tmp_path.rglob("*"):
        assert "private-platform-id" not in str(path)
        assert "private-self-id" not in str(path)
        if path.suffix == ".json":
            document = path.read_text(encoding="utf-8")
            assert "private-platform-id" not in document
            assert "private-self-id" not in document


def test_missing_binding_authority_rejects_without_any_scope_write(
    tmp_path: Path,
) -> None:
    repository = ScopeRepository(tmp_path)
    catalog = SessionCatalog(repository)
    key = load_or_create_scope_identity_key(tmp_path / "identity.key")
    bot = key.bot_ref(
        BotBinding(
            platform_id="private-platform-id",
            self_id="private-self-id",
        ),
        generation=0,
    )

    with pytest.raises(ValueError, match="bot binding authority is missing"):
        catalog.begin_turn(_transport(bot), _binding())

    assert not (
        repository.bots_directory / bot.token / "manifest.json"
    ).exists()
    assert not repository.transport_catalog_path(
        bot.token,
        "session_v1_S",
    ).exists()
    assert not repository.transport_delivery_binding_path(
        bot.token,
        "session_v1_S",
    ).exists()


def test_forged_bot_and_stale_binding_reject_without_turn_write(tmp_path: Path) -> None:
    repository = ScopeRepository(tmp_path)
    catalog = SessionCatalog(repository)
    bot = _registered_bot(catalog, tmp_path)
    forged_bot = BotRef(token="bot_v1_forged", generation=0)

    with pytest.raises(ValueError, match="bot binding"):
        catalog.begin_turn(_transport(forged_bot), _binding())
    assert not repository.transport_catalog_path(
        forged_bot.token,
        "session_v1_S",
    ).exists()

    with pytest.raises(ValueError, match="binding generation"):
        catalog.begin_turn(
            _transport(bot),
            _binding(binding_generation=1),
        )
    assert not repository.transport_catalog_path(
        bot.token,
        "session_v1_S",
    ).exists()


def test_proactive_authorization_requires_live_current_proof(tmp_path: Path) -> None:
    repository = ScopeRepository(tmp_path)
    catalog = SessionCatalog(repository)
    bot = _registered_bot(catalog, tmp_path)
    scope = repository.create_scope(
        _scope(bot=bot, persona_token="persona_v1_A"),
        expected_absent=True,
    )
    frozen = catalog.freeze_persona(
        catalog.begin_turn(_transport(bot), _binding()),
        scope,
    )

    assert catalog.can_issue_proactive(frozen) is False
    assert catalog.can_issue_proactive(frozen, **_current_proof()) is True
    assert (
        catalog.can_issue_proactive(
            frozen,
            **_current_proof(digest="changed-proof"),
        )
        is False
    )
    assert (
        catalog.can_issue_proactive(
            frozen,
            **_current_proof(generation=1),
        )
        is False
    )
    assert (
        catalog.can_issue_proactive(
            frozen,
            **_current_proof(now_ms=1),
        )
        is False
    )


def test_proactive_authorization_reloads_scope_and_persona_lifecycle(
    tmp_path: Path,
) -> None:
    repository = ScopeRepository(tmp_path)
    catalog = SessionCatalog(repository)
    bot = _registered_bot(catalog, tmp_path)
    scope_a = repository.create_scope(
        _scope(bot=bot, persona_token="persona_v1_A"),
        expected_absent=True,
    )
    frozen_a = catalog.freeze_persona(
        catalog.begin_turn(_transport(bot), _binding()),
        scope_a,
    )
    repository.invalidate_scope(
        scope_a,
        expected_scope_generation=scope_a.scope_generation,
        reason="reset",
    )

    assert catalog.can_issue_proactive(frozen_a, **_current_proof()) is False

    scope_b = repository.create_scope(
        _scope(bot=bot, persona_token="persona_v1_B"),
        expected_absent=True,
    )
    frozen_b = catalog.freeze_persona(
        catalog.begin_turn(_transport(bot), _binding()),
        scope_b,
    )
    repository.retire_persona_revision(
        scope_b.persona_ref,
        expected_lifecycle_generation=scope_b.persona_ref.lifecycle_generation,
        reason="retired",
    )

    assert catalog.can_issue_proactive(frozen_b, **_current_proof()) is False
