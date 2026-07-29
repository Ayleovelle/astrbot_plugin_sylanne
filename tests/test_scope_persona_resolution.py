from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from sylanne_alpha.scope_identity import AdapterAccountProof, BotBinding, ScopeResolver


class _Session:
    platform_id = "adapter"

    def __str__(self) -> str:
        return "adapter:FriendMessage:42"


def _event(*, self_id: str = "10001", session: object | None = None) -> object:
    event = SimpleNamespace(
        session=_Session() if session is None else session,
        unified_msg_origin="adapter:FriendMessage:42",
        get_platform_id=lambda: "adapter",
        get_platform_name=lambda: "aiocqhttp",
        get_self_id=lambda: self_id,
    )
    extras: dict[str, object] = {}
    event.get_extra = lambda key, default=None: extras.get(key, default)
    event.set_extra = lambda key, value: extras.__setitem__(key, value)
    return event


@pytest.mark.asyncio
async def test_resolver_uses_astrbot_effective_persona_and_freezes_it() -> None:
    manager = SimpleNamespace(
        resolve_selected_persona=AsyncMock(
            return_value=(
                "narrator",
                {
                    "prompt": "calm observer",
                    "begin_dialogs": ["hello"],
                    "tools": None,
                    "skills": [],
                },
                None,
                False,
            )
        )
    )
    context = SimpleNamespace(
        persona_manager=manager,
        get_config=lambda *, umo: {
            "provider_settings": {"default_personality": "narrator"}
        },
    )
    event = _event()
    request = SimpleNamespace(conversation=SimpleNamespace(persona_id=None))

    resolved = await ScopeResolver.for_test(context).resolve(event, request)

    assert resolved.private_scope_enabled is True
    assert resolved.persona_source is not None
    assert resolved.persona_source.persona_id == "narrator"
    assert resolved.persona_source.prompt == "calm observer"
    assert resolved.scope is not None
    assert resolved.scope.bot_ref.token.startswith("bot_v1_")
    manager.resolve_selected_persona.assert_awaited_once_with(
        umo="adapter:FriendMessage:42",
        conversation_persona_id=None,
        platform_name="aiocqhttp",
        provider_settings={"default_personality": "narrator"},
    )


@pytest.mark.asyncio
async def test_third_party_request_without_conversation_does_not_call_persona_manager() -> None:
    manager = SimpleNamespace(resolve_selected_persona=AsyncMock())
    context = SimpleNamespace(persona_manager=manager, get_config=AsyncMock())

    result = await ScopeResolver.for_test(context).resolve(
        _event(), SimpleNamespace(conversation=None)
    )

    assert result.private_scope_enabled is False
    assert result.disabled_reason == "persona_application_unverified"
    manager.resolve_selected_persona.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolver_fails_closed_for_missing_bot_or_managed_persona() -> None:
    resolver = ScopeResolver.for_test(None)

    missing_bot = await resolver.resolve_test_values(
        platform_id="adapter",
        self_id="",
        umo="adapter:FriendMessage:42",
        persona_id="narrator",
    )
    managed = await resolver.resolve_test_values(
        platform_id="adapter",
        self_id="10001",
        umo="adapter:FriendMessage:42",
        persona_id="sylanne_embodiment_42",
    )

    assert missing_bot.disabled_reason == "bot_identity_unverified"
    assert managed.disabled_reason == "managed_persona_forbidden"


@pytest.mark.asyncio
async def test_empty_or_wrong_platform_umo_fails_closed() -> None:
    resolver = ScopeResolver.for_test(None)

    empty = await resolver.resolve_test_values(
        platform_id="adapter", self_id="10001", umo="", persona_id="narrator"
    )
    conflict = await resolver.resolve_test_values(
        platform_id="adapter",
        self_id="10001",
        umo="other:FriendMessage:42",
        persona_id="narrator",
    )

    assert empty.disabled_reason == "transport_session_unverified"
    assert conflict.disabled_reason == "umo_platform_conflict"


@pytest.mark.asyncio
async def test_missing_self_accepts_only_live_proof_for_persisted_binding() -> None:
    resolver = ScopeResolver.for_test(None)
    generation = resolver.catalog.binding_generation("adapter", "known-account")
    bot_ref = resolver._identity.bot_ref(
        BotBinding(platform_id="adapter", self_id="known-account"), generation
    )
    proof = AdapterAccountProof(
        platform_id="adapter",
        bot_ref=bot_ref,
        proof_generation=4,
        verified_at_ms=900,
        expires_at_ms=2_000,
        account_set_digest="current",
        account_count=1,
    )

    resolved = await resolver.resolve_test_values(
        platform_id="adapter",
        self_id="",
        umo="adapter:FriendMessage:42",
        persona_id="narrator",
        proof=proof,
        current_account_set_digest="current",
        current_proof_generation=4,
        now_ms=1_000,
    )

    assert resolved.private_scope_enabled is True
    assert resolved.identity_quality == "single_account_proven"


@pytest.mark.asyncio
async def test_unified_origin_must_match_canonical_session_before_persona_lookup() -> None:
    manager = SimpleNamespace(resolve_selected_persona=AsyncMock())
    context = SimpleNamespace(
        persona_manager=manager,
        get_config=Mock(return_value={"provider_settings": {}}),
    )
    resolver = ScopeResolver.for_test(context)
    event = _event()
    event.unified_msg_origin = "adapter:FriendMessage:different"
    request = SimpleNamespace(conversation=SimpleNamespace(persona_id=None))
    transport = resolver.resolve_transport(event)
    binding = resolver.delivery_binding(event, transport)
    assert binding is not None
    turn = resolver.catalog.begin_turn(
        transport,
        binding,
        publish=lambda _turn: True,
    )
    event.set_extra("_sylanne_transport_scope_v1", transport)
    event.set_extra("_sylanne_transport_turn_v1", turn)

    resolved = await resolver.resolve(event, request)

    assert resolved.private_scope_enabled is False
    assert resolved.disabled_reason == "umo_session_conflict"
    context.get_config.assert_not_called()
    manager.resolve_selected_persona.assert_not_awaited()
    assert resolver.catalog.current(transport.session_ref.token).turn_state == "resolving"


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["umo", "session", "turn"])
async def test_persona_await_parent_mutation_fails_before_scope_publication(
    tmp_path,
    mutation: str,
) -> None:
    event = _event()
    turn_holder: dict[str, object] = {}

    async def select_persona(**_kwargs):
        if mutation == "umo":
            event.unified_msg_origin = "adapter:FriendMessage:different"
        elif mutation == "session":
            class _ChangedSession:
                platform_id = "adapter"

                def __str__(self) -> str:
                    return "adapter:FriendMessage:different"

            event.session = _ChangedSession()
            event.unified_msg_origin = "adapter:FriendMessage:different"
        else:
            event.set_extra(
                "_sylanne_transport_turn_v1",
                replace(
                    turn_holder["turn"],
                    updated_at_ms=turn_holder["turn"].updated_at_ms + 1,
                ),
            )
        return (
            "narrator",
            {"prompt": "quiet", "begin_dialogs": [], "tools": None, "skills": []},
            None,
            False,
        )

    context = SimpleNamespace(
        persona_manager=SimpleNamespace(
            resolve_selected_persona=AsyncMock(side_effect=select_persona)
        ),
        get_config=lambda *, umo: {"provider_settings": {}},
    )
    resolver = ScopeResolver.for_test(context, root=tmp_path)
    transport = resolver.resolve_transport(event)
    binding = resolver.delivery_binding(event, transport)
    assert binding is not None

    def publish(turn) -> bool:
        event.set_extra("_sylanne_transport_scope_v1", transport)
        event.set_extra("_sylanne_transport_turn_v1", turn)
        return (
            event.get_extra("_sylanne_transport_scope_v1") is transport
            and event.get_extra("_sylanne_transport_turn_v1") is turn
        )

    turn = resolver.catalog.begin_turn(transport, binding, publish=publish)
    turn_holder["turn"] = turn

    result = await resolver.resolve(
        event,
        SimpleNamespace(conversation=SimpleNamespace(persona_id=None)),
    )

    assert result.private_scope_enabled is False
    assert resolver.catalog.current(transport.session_ref.token) == turn
    assert resolver.catalog.current(transport.session_ref.token).turn_state == "resolving"
    persona_root = (
        resolver._repository.bots_directory / transport.bot_ref.token / "personas"
    )
    assert not persona_root.exists() or list(persona_root.rglob("*")) == []
    with resolver._repository.transaction():
        assert resolver._repository._read_catalog_locked()["scopes"] == {}
