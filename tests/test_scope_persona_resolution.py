from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

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
