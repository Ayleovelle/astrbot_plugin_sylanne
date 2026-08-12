from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from typing import get_type_hints

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
from sylanne_alpha.scope_identity import PersonaSource, ScopeIdentityKey
from tests.scope_fixtures import scope_storage_token


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


def _persona_source() -> PersonaSource:
    return PersonaSource(
        persona_id="persona.main",
        prompt="A concise assistant.",
        begin_dialogs=("hello",),
        tools=None,
        skills=None,
        resolution_source="catalog",
    )


def test_session_scope_uses_only_opaque_storage_components_and_is_frozen() -> None:
    bot = _bot()
    persona = _persona(bot)
    session = _session(bot)
    scope = SessionScope(
        bot_ref=bot,
        persona_ref=persona,
        session_ref=session,
        storage_token=scope_storage_token("contract-frozen"),
        scope_generation=3,
    )

    assert scope.storage_components() == ("bot_v1_A", "persona_v1_P", "session_v1_S")
    with pytest.raises(FrozenInstanceError):
        scope.storage_token = "scope_v1_changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "storage_token",
    [
        "scope_v1_fake",
        "scope_v1_" + "a" * 42,
        "scope_v1_" + "a" * 44,
    ],
)
def test_session_scope_rejects_noncanonical_storage_token_shapes(
    storage_token: str,
) -> None:
    bot = _bot()

    with pytest.raises(ValueError):
        SessionScope(
            bot_ref=bot,
            persona_ref=_persona(bot),
            session_ref=_session(bot),
            storage_token=storage_token,
            scope_generation=3,
        )


def test_session_scope_accepts_identity_minted_storage_token() -> None:
    bot = _bot()
    persona = _persona(bot)
    session = _session(bot)
    token = ScopeIdentityKey(
        key_id="scope-contract-test",
        secret=b"k" * 32,
    ).scope_token(bot, persona, session)

    scope = SessionScope(
        bot_ref=bot,
        persona_ref=persona,
        session_ref=session,
        storage_token=token,
        scope_generation=3,
    )

    assert scope.storage_token == token
    assert len(token.removeprefix("scope_v1_")) == 43


def test_session_scope_rejects_persona_owned_by_a_different_bot() -> None:
    bot = _bot()
    other_bot = BotRef(token="bot_v1_B", generation=0)

    with pytest.raises(ValueError, match="^persona does not belong to bot$"):
        SessionScope(
            bot_ref=bot,
            persona_ref=_persona(other_bot),
            session_ref=_session(bot),
            storage_token=scope_storage_token("contract-parent-mismatch"),
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

    with pytest.raises(ValueError, match="^identity_quality must be a non-empty str$"):
        ResolvedTransportScope(
            bot_ref=bot,
            session_ref=session,
            identity_quality=None,
            private_scope_enabled=True,
            disabled_reason=None,
        )
    assert get_type_hints(ResolvedTransportScope)["identity_quality"] == str | None
    disabled = ResolvedTransportScope.disabled("transport_session_unverified")
    assert disabled.bot_ref is None
    assert disabled.session_ref is None

    with pytest.raises(ValueError, match="^invalid bot_v1_ token$"):
        BotRef(token="bot_v2_A", generation=0)
    with pytest.raises(ValueError, match="^invalid scope_v1_ token$"):
        TurnDeliveryLease(
            transport_session_token="session_v1_S",
            resolved_scope_token="scope_v2_X",
            bot_binding_generation=0,
            persona_lifecycle_generation=0,
            session_generation=0,
            scope_generation=0,
            turn_generation=0,
        )
    with pytest.raises(ValueError, match="^generation must be a non-negative int$"):
        SessionRef(token="session_v1_S", bot_ref=bot, generation=True)  # type: ignore[arg-type]


def test_turn_delivery_lease_binds_bot_and_persona_lifecycle_generations() -> None:
    bot = _bot()
    persona = _persona(bot)
    lease = TurnDeliveryLease(
        transport_session_token="session_v1_S",
        resolved_scope_token="scope_v1_X",
        bot_binding_generation=bot.generation,
        persona_lifecycle_generation=persona.lifecycle_generation,
        session_generation=5,
        scope_generation=3,
        turn_generation=9,
    )

    assert get_type_hints(TurnDeliveryLease)["bot_binding_generation"] is int
    assert get_type_hints(TurnDeliveryLease)["persona_lifecycle_generation"] is int
    assert lease.bot_binding_generation == bot.generation
    assert lease.persona_lifecycle_generation == persona.lifecycle_generation


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("bot_binding_generation", True),
        ("bot_binding_generation", -1),
        ("persona_lifecycle_generation", True),
        ("persona_lifecycle_generation", -1),
    ),
)
def test_turn_delivery_lease_rejects_non_exact_identity_generations(
    field_name: str,
    value: object,
) -> None:
    bot = _bot()
    persona = _persona(bot)
    kwargs: dict[str, object] = {
        "transport_session_token": "session_v1_S",
        "resolved_scope_token": "scope_v1_X",
        "bot_binding_generation": bot.generation,
        "persona_lifecycle_generation": persona.lifecycle_generation,
        "session_generation": 5,
        "scope_generation": 3,
        "turn_generation": 9,
    }
    kwargs[field_name] = value

    with pytest.raises(ValueError, match=f"^{field_name} must be a non-negative int$"):
        TurnDeliveryLease(
            **kwargs  # type: ignore[arg-type]
        )


def test_api_diagnostics_and_delivery_contracts_keep_sensitive_fields_redacted() -> None:
    bot = _bot()
    persona = _persona(bot)
    session = _session(bot)
    scope = SessionScope(
        bot_ref=bot,
        persona_ref=persona,
        session_ref=session,
        storage_token=scope_storage_token("contract-resolved"),
        scope_generation=3,
    )

    diagnostic = ScopeDiagnosticEcho(
        bot_ref=bot.token,
        persona_ref=persona.token,
        session_ref=session.token,
        scope_generation=3,
        resolved_at_ms=12,
    )
    assert diagnostic.scope_generation == 3
    assert (diagnostic.bot_ref, diagnostic.persona_ref, diagnostic.session_ref) == (
        "bot_v1_A",
        "persona_v1_P",
        "session_v1_S",
    )
    assert all(type(value) is str for value in (diagnostic.bot_ref, diagnostic.persona_ref, diagnostic.session_ref))

    scope_path = ScopeApiPathEcho(
        bot_ref=bot.token,
        persona_ref=persona.token,
        session_ref=session.token,
    )
    assert ScopeApiEcho(
        scope=scope_path,
        scope_generation=3,
        resolved_at_ms=12,
    ).scope == scope_path
    assert (scope_path.bot_ref, scope_path.persona_ref, scope_path.session_ref) == (
        "bot_v1_A",
        "persona_v1_P",
        "session_v1_S",
    )

    persona_path = PersonaApiPathEcho(bot_ref=bot.token, persona_ref=persona.token)
    assert PersonaApiEcho(
        scope=persona_path,
        scope_generation=0,
        resolved_at_ms=12,
    ).scope == persona_path
    assert (persona_path.bot_ref, persona_path.persona_ref) == ("bot_v1_A", "persona_v1_P")
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
    assert ResolvedScope.__annotations__["scope"] == "SessionScope | None"
    with pytest.raises(ValueError, match="^scope must be a SessionScope or None$"):
        ResolvedScope(
            scope=PersonaScope(bot_ref=bot, persona_ref=persona),
            persona_source=None,
            identity_quality="verified",
            resolution_source="adapter",
            resolved_at_ms=12,
            private_scope_enabled=True,
            disabled_reason=None,
            turn_generation=0,
        )

    lease = TurnDeliveryLease(
        transport_session_token="session_v1_S",
        resolved_scope_token="scope_v1_X",
        bot_binding_generation=bot.generation,
        persona_lifecycle_generation=persona.lifecycle_generation,
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
    assert type(draft.issuer_mac) is str
    assert json.dumps({"issuer_mac": draft.issuer_mac}) == '{"issuer_mac": "mac-secret"}'
    assert get_type_hints(ProactiveIntentDraft)["issuer_mac"] is str
    with pytest.raises(ValueError, match="^issuer_mac must be an exact str$"):
        ProactiveIntentDraft(
            delivery_ref=delivery,
            lease=proactive_lease,
            text="message-secret",
            idempotent=True,
            issuer_mac=b"mac-secret",  # type: ignore[arg-type]
        )
    assert all(secret not in repr(delivery) for secret in ("platform-secret", "self-secret", "target-secret", "send-secret"))
    assert all(secret not in repr(draft) for secret in ("message-secret", "mac-secret"))


def test_resolved_scope_accepts_only_complete_success_or_disabled_states() -> None:
    bot = _bot()
    scope = SessionScope(
        bot_ref=bot,
        persona_ref=_persona(bot),
        session_ref=_session(bot),
        storage_token=scope_storage_token("contract-active"),
        scope_generation=3,
    )
    source = _persona_source()

    resolved = ResolvedScope(
        scope=scope,
        persona_source=source,
        identity_quality="verified",
        resolution_source="catalog",
        resolved_at_ms=12,
        private_scope_enabled=True,
        disabled_reason=None,
        turn_generation=0,
    )

    assert resolved.scope is scope
    assert resolved.persona_source is source
    assert ResolvedScope.disabled("unverified", resolved_at_ms=12).private_scope_enabled is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"persona_source": None},
        {"identity_quality": None},
        {"resolution_source": None},
        {"private_scope_enabled": False},
        {"disabled_reason": "mixed-state"},
        {"turn_generation": None},
    ],
)
def test_resolved_scope_rejects_mixed_success_states(overrides: dict[str, object]) -> None:
    bot = _bot()
    values: dict[str, object] = {
        "scope": SessionScope(
            bot_ref=bot,
            persona_ref=_persona(bot),
            session_ref=_session(bot),
            storage_token=scope_storage_token("contract-disabled"),
            scope_generation=3,
        ),
        "persona_source": _persona_source(),
        "identity_quality": "verified",
        "resolution_source": "catalog",
        "resolved_at_ms": 12,
        "private_scope_enabled": True,
        "disabled_reason": None,
        "turn_generation": 0,
    }
    values.update(overrides)

    with pytest.raises(ValueError):
        ResolvedScope(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "overrides",
    [
        {"persona_source": _persona_source()},
        {"identity_quality": "verified"},
        {"resolution_source": "catalog"},
        {"private_scope_enabled": True},
        {"disabled_reason": None},
        {"disabled_reason": ""},
        {"turn_generation": 0},
    ],
)
def test_resolved_scope_rejects_mixed_disabled_states(overrides: dict[str, object]) -> None:
    values: dict[str, object] = {
        "scope": None,
        "persona_source": None,
        "identity_quality": None,
        "resolution_source": None,
        "resolved_at_ms": 12,
        "private_scope_enabled": False,
        "disabled_reason": "unverified",
        "turn_generation": None,
    }
    values.update(overrides)

    with pytest.raises(ValueError):
        ResolvedScope(**values)  # type: ignore[arg-type]


def test_resolved_scope_rejects_untrusted_persona_source_without_leaking_repr() -> None:
    marker = "PRIVATE-PROMPT-MARKER"
    bot = _bot()

    with pytest.raises(ValueError) as captured:
        ResolvedScope(
            scope=SessionScope(
                bot_ref=bot,
                persona_ref=_persona(bot),
                session_ref=_session(bot),
                storage_token=scope_storage_token("contract-redaction"),
                scope_generation=3,
            ),
            persona_source={"prompt": marker},  # type: ignore[arg-type]
            identity_quality="verified",
            resolution_source="catalog",
            resolved_at_ms=12,
            private_scope_enabled=True,
            disabled_reason=None,
            turn_generation=0,
        )

    assert str(captured.value) == "persona_source must be a PersonaSource"
    assert marker not in str(captured.value)
    assert marker not in repr(captured.value)
