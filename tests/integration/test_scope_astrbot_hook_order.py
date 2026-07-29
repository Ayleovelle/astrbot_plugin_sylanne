from __future__ import annotations

from types import SimpleNamespace

import pytest

from main import EmotionalStatePlugin
from sylanne_alpha.scope_identity import ScopeResolver


class _Session:
    platform_id = "adapter"

    def __str__(self) -> str:
        return "adapter:FriendMessage:42"


@pytest.mark.asyncio
async def test_transport_turn_and_persona_freeze_precede_existing_pipeline(
    tmp_path, monkeypatch
) -> None:
    order: list[str] = []

    async def select_persona(**_kwargs):
        order.append("persona resolve")
        return (
            "narrator",
            {"prompt": "quiet", "begin_dialogs": [], "tools": None, "skills": []},
            None,
            False,
        )

    context = SimpleNamespace(
        get_config=lambda *, umo: {"provider_settings": {}},
        persona_manager=SimpleNamespace(resolve_selected_persona=select_persona),
    )
    resolver = ScopeResolver.for_test(context, root=tmp_path)
    extras: dict[str, object] = {}
    event = SimpleNamespace(
        session=_Session(),
        unified_msg_origin="adapter:FriendMessage:42",
        get_platform_id=lambda: "adapter",
        get_platform_name=lambda: "aiocqhttp",
        get_self_id=lambda: "10001",
        get_extra=lambda key: extras.get(key),
        set_extra=lambda key, value: extras.__setitem__(key, value),
    )

    original_transport = resolver.resolve_transport
    monkeypatch.setattr(
        resolver,
        "resolve_transport",
        lambda evt: (order.append("transport"), original_transport(evt))[1],
    )
    original_binding = resolver.delivery_binding
    monkeypatch.setattr(
        resolver,
        "delivery_binding",
        lambda evt, scope: (order.append("binding"), original_binding(evt, scope))[1],
    )
    original_begin = resolver.catalog.begin_turn
    monkeypatch.setattr(
        resolver.catalog,
        "begin_turn",
        lambda scope, binding: (order.append("begin_turn"), original_begin(scope, binding))[1],
    )
    original_activate = resolver._repository.activate_persona_revision
    monkeypatch.setattr(
        resolver._repository,
        "activate_persona_revision",
        lambda candidate: (order.append("activate"), original_activate(candidate))[1],
    )
    original_freeze = resolver.catalog.freeze_persona
    monkeypatch.setattr(
        resolver.catalog,
        "freeze_persona",
        lambda turn, scope: (order.append("freeze"), original_freeze(turn, scope))[1],
    )

    async def existing_pipeline(_event, _request):
        order.append("existing pipeline")

    plugin = SimpleNamespace(
        _scope_resolver_v1=resolver,
        _inbound_dup_gate=lambda _event: False,
        _llm_request_pipeline=SimpleNamespace(_on_llm_request_inner=existing_pipeline),
    )

    assert EmotionalStatePlugin._begin_scope_transport(plugin, event) is True
    transport = extras["_sylanne_transport_scope_v1"]
    await EmotionalStatePlugin._on_llm_request_inner(
        plugin,
        event,
        SimpleNamespace(conversation=SimpleNamespace(persona_id=None)),
    )

    assert order == [
        "transport",
        "binding",
        "begin_turn",
        "persona resolve",
        "activate",
        "freeze",
        "existing pipeline",
    ]
    assert extras["_sylanne_transport_scope_v1"] is transport
    assert extras["_sylanne_resolved_scope_v1"].private_scope_enabled is True
