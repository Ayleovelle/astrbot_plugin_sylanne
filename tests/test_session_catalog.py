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
from sylanne_alpha.scope_repository import ScopeRepository
from sylanne_alpha.session_catalog import ProtectedDeliveryBinding, SessionCatalog


def _transport() -> ResolvedTransportScope:
    bot = BotRef(token="bot_v1_A", generation=0)
    return ResolvedTransportScope(
        bot_ref=bot,
        session_ref=SessionRef(token="session_v1_S", bot_ref=bot, generation=0),
        identity_quality="event_self_id",
        private_scope_enabled=True,
        disabled_reason=None,
    )


def _scope(*, persona_token: str) -> SessionScope:
    transport = _transport()
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


def _binding() -> ProtectedDeliveryBinding:
    return ProtectedDeliveryBinding(
        platform_id="private-platform-id",
        self_id="private-self-id",
        message_session="private:FriendMessage:42",
        target_address="private-target-address",
        adapter_capability="reactive_only",
        account_proof_digest="proof-v1",
        account_proof_generation=0,
        account_proof_expires_at_ms=1,
        binding_generation=0,
    )


def test_transport_catalog_persists_monotonic_turn_and_fails_closed_after_resolving_restart(
    tmp_path: Path,
) -> None:
    repository = ScopeRepository(tmp_path)
    scope = repository.create_scope(_scope(persona_token="persona_v1_A"), expected_absent=True)
    catalog = SessionCatalog(repository)

    first = catalog.begin_turn(_transport(), _binding())
    frozen = catalog.freeze_persona(first, scope)

    restarted = SessionCatalog(ScopeRepository(tmp_path))
    restored = restarted.current(_transport().session_ref.token)
    assert restored.turn_generation == frozen.turn_generation
    assert restored.turn_state == "frozen"
    assert restored.active_persona_ref == scope.persona_ref.token

    second = restarted.begin_turn(_transport(), _binding())
    unresolved = SessionCatalog(ScopeRepository(tmp_path)).current(_transport().session_ref.token)
    assert second.turn_generation == frozen.turn_generation + 1
    assert unresolved.turn_state == "resolving"
    assert SessionCatalog(ScopeRepository(tmp_path)).can_issue_proactive(unresolved) is False


def test_a_to_b_to_a_allocates_a_fresh_persisted_turn_generation(tmp_path: Path) -> None:
    repository = ScopeRepository(tmp_path)
    scope_a = repository.create_scope(_scope(persona_token="persona_v1_A"), expected_absent=True)
    scope_b = repository.create_scope(_scope(persona_token="persona_v1_B"), expected_absent=True)
    catalog = SessionCatalog(repository)

    generations = []
    for scope in (scope_a, scope_b, scope_a):
        turn = catalog.begin_turn(_transport(), _binding())
        generations.append(catalog.freeze_persona(turn, scope).turn_generation)

    assert generations == sorted(set(generations))


def test_catalog_accepts_only_opaque_session_token_and_never_exposes_delivery_secret(
    tmp_path: Path,
) -> None:
    repository = ScopeRepository(tmp_path)
    scope = repository.create_scope(_scope(persona_token="persona_v1_A"), expected_absent=True)
    catalog = SessionCatalog(repository)
    turn = catalog.begin_turn(_transport(), _binding())
    catalog.freeze_persona(turn, scope)

    with pytest.raises(ValueError):
        catalog.current("not-an-opaque-session-token")
    assert "private-platform-id" not in repr(_binding())
    assert "private-target-address" not in repr(catalog.current("session_v1_S"))

    binding_path = repository.transport_delivery_binding_path("bot_v1_A", "session_v1_S")
    assert "private-platform-id" not in str(binding_path)
    assert binding_path.exists()
