from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from sylanne_alpha.scope_contracts import (
    BotDeliveryRef,
    BotRef,
    PersonaApiEcho,
    PersonaApiPathEcho,
    PersonaRevisionRef,
    PersonaScope,
    ProactiveDeliveryLease,
    ProactiveIntentDraft,
    RelationRef,
    RelationScope,
    ResolvedScope,
    ResolvedTransportScope,
    ScopeApiEcho,
    ScopeApiPathEcho,
    ScopeDiagnosticEcho,
    SessionRef,
    SessionScope,
    TurnDeliveryLease,
)


def _bot() -> BotRef:
    return BotRef(token="bot_v1_A", generation=2)


def _persona(bot: BotRef | None = None) -> PersonaRevisionRef:
    return PersonaRevisionRef(
        token="persona_v1_P",
        bot_ref=bot or _bot(),
        persona_id_digest="f" * 64,
        source_fingerprint="a" * 64,
        lifecycle_generation=0,
    )


def _session(bot: BotRef | None = None) -> SessionRef:
    return SessionRef(token="session_v1_S", bot_ref=bot or _bot(), generation=5)


def test_session_scope_uses_only_opaque_storage_components_and_is_frozen() -> None:
    bot = _bot()
    persona = _persona(bot)
    session = _session(bot)
    scope = SessionScope(
        bot_ref=bot,
        persona_ref=persona,
        session_ref=session,
        storage_token="scope_v1_X",
        scope_generation=3,
    )

    assert scope.storage_components() == ("bot_v1_A", "persona_v1_P", "session_v1_S")
    with pytest.raises(FrozenInstanceError):
        scope.storage_token = "scope_v1_changed"  # type: ignore[misc]


def test_session_scope_rejects_persona_owned_by_a_different_bot() -> None:
    bot = _bot()
    other_bot = BotRef(token="bot_v1_B", generation=0)

    with pytest.raises(ValueError, match="^persona does not belong to bot$"):
        SessionScope(
            bot_ref=bot,
            persona_ref=_persona(other_bot),
            session_ref=_session(bot),
            storage_token="scope_v1_X",
            scope_generation=3,
        )


def test_scope_contracts_validate_parentage_tokens_and_generations() -> None:
    bot = _bot()
    persona = _persona(bot)
    session = _session(bot)
    relation = RelationRef(token="relation_v1_R", bot_ref=bot)

    assert PersonaScope(bot_ref=bot, persona_ref=persona).persona_ref is persona
    assert RelationScope(
        bot_ref=bot,
        persona_ref=persona,
        relation_ref=relation,
        relation_generation=4,
    ).relation_ref is relation
    assert ResolvedTransportScope(
        bot_ref=bot,
        session_ref=session,
        identity_quality="verified",
        private_scope_enabled=True,
        disabled_reason=None,
    ).session_ref is session

    with pytest.raises(ValueError, match="^invalid bot_v1_ token$"):
        BotRef(token="bot_v2_A", generation=0)
    with pytest.raises(ValueError, match="^invalid scope_v1_ token$"):
        TurnDeliveryLease(
            transport_session_token="session_v1_S",
            resolved_scope_token="scope_v2_X",
            session_generation=0,
            scope_generation=0,
            turn_generation=0,
        )
    with pytest.raises(ValueError, match="^generation must be a non-negative int$"):
        SessionRef(token="session_v1_S", bot_ref=bot, generation=True)  # type: ignore[arg-type]


def test_api_diagnostics_and_delivery_contracts_keep_sensitive_fields_redacted() -> None:
    bot = _bot()
    persona = _persona(bot)
    session = _session(bot)
    scope = SessionScope(
        bot_ref=bot,
        persona_ref=persona,
        session_ref=session,
        storage_token="scope_v1_X",
        scope_generation=3,
    )

    assert ScopeDiagnosticEcho(
        bot_ref=bot,
        persona_ref=persona,
        session_ref=session,
        scope_generation=3,
        resolved_at_ms=12,
    ).scope_generation == 3
    assert ScopeApiEcho(
        scope=ScopeApiPathEcho(bot_ref=bot, persona_ref=persona, session_ref=session),
        scope_generation=3,
        resolved_at_ms=12,
    ).scope.session_ref is session
    assert PersonaApiEcho(
        scope=PersonaApiPathEcho(bot_ref=bot, persona_ref=persona),
        scope_generation=0,
        resolved_at_ms=12,
    ).scope.persona_ref is persona
    assert ResolvedScope.disabled("unverified", resolved_at_ms=12) == ResolvedScope(
        scope=None,
        persona_source=None,
        identity_quality=None,
        resolution_source=None,
        resolved_at_ms=12,
        private_scope_enabled=False,
        disabled_reason="unverified",
        turn_generation=None,
    )

    lease = TurnDeliveryLease(
        transport_session_token="session_v1_S",
        resolved_scope_token="scope_v1_X",
        session_generation=5,
        scope_generation=3,
        turn_generation=9,
    )
    proactive_lease = ProactiveDeliveryLease(
        transport_session_token="session_v1_S",
        resolved_scope_token="scope_v1_X",
        expected_persona_token="persona_v1_P",
        persona_lifecycle_generation=0,
        session_generation=5,
        scope_generation=3,
        expected_turn_generation=9,
        expires_at_ms=15,
    )
    delivery = BotDeliveryRef(
        token="delivery_v1_D",
        delivery_id="delivery-id",
        bot_ref=bot,
        persona_ref=persona,
        session_ref=session,
        platform_id="platform-secret",
        self_id="self-secret",
        target_address="target-secret",
        adapter_capability="send-secret",
    )
    draft = ProactiveIntentDraft(
        delivery_ref=delivery,
        lease=proactive_lease,
        text="message-secret",
        idempotent=True,
        issuer_mac="mac-secret",
    )

    assert lease.turn_generation == 9
    assert draft.delivery_ref is delivery
    assert all(secret not in repr(delivery) for secret in ("platform-secret", "self-secret", "target-secret", "send-secret"))
    assert all(secret not in repr(draft) for secret in ("message-secret", "mac-secret"))
