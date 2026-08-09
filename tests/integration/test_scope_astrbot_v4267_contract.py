"""Compatibility contracts for the scoped AstrBot 4.26.7 runtime APIs."""

from __future__ import annotations

import asyncio
import importlib
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest


astrbot = pytest.importorskip("astrbot")
if getattr(astrbot, "__version__", None) != "4.26.7":
    pytest.skip(
        "AstrBot 4.26.7 contract probe requires the pinned runtime",
        allow_module_level=True,
    )

def _parameter_names(callable_obj: object) -> list[str]:
    return list(inspect.signature(callable_obj).parameters)


def _runtime_contract_api() -> tuple[object, ...]:
    """Load the pinned runtime only when its optional provider dependencies exist."""
    try:
        star = importlib.import_module("astrbot.api.star")
        message = importlib.import_module("astrbot.core.agent.message")
        persona_mgr = importlib.import_module("astrbot.core.persona_mgr")
        event = importlib.import_module("astrbot.core.platform.astr_message_event")
        entities = importlib.import_module("astrbot.core.provider.entities")
        gemini = importlib.import_module(
            "astrbot.core.provider.sources.gemini_source"
        )
        context = importlib.import_module("astrbot.core.star.context")
    except ModuleNotFoundError as exc:
        if exc.name is None or exc.name.startswith("astrbot"):
            raise
        pytest.skip(f"AstrBot runtime dependency is unavailable: {exc.name}")

    return (
        event.AstrMessageEvent,
        context.Context,
        message.Message,
        persona_mgr.PersonaManager,
        gemini.ProviderGoogleGenAI,
        entities.ProviderRequest,
        star.StarTools,
        message.TextPart,
        message.dump_messages_with_checkpoints,
    )


def test_astrbot_v4267_scoped_runtime_contract() -> None:
    (
        AstrMessageEvent,
        Context,
        _Message,
        PersonaManager,
        _ProviderGoogleGenAI,
        _ProviderRequest,
        StarTools,
        TextPart,
        _dump_messages_with_checkpoints,
    ) = _runtime_contract_api()

    assert callable(StarTools.get_data_dir)
    assert _parameter_names(AstrMessageEvent.get_self_id) == ["self"]
    assert _parameter_names(PersonaManager.resolve_selected_persona) == [
        "self",
        "umo",
        "conversation_persona_id",
        "platform_name",
        "provider_settings",
    ]
    assert _parameter_names(Context.register_web_api) == [
        "self",
        "route",
        "view_handler",
        "methods",
        "desc",
    ]

    part = TextPart(text="[sylanne_runtime_overlay]\nquiet")
    assert part.mark_as_temp() is part
    assert part._no_save is True

    route = "/astrbot_plugin_sylanne/api/bots/<bot_ref>"
    view_handler = lambda: None
    context = SimpleNamespace(registered_web_apis=[])
    Context.register_web_api(context, route, view_handler, ["GET"], "scope probe")
    assert context.registered_web_apis == [
        (route, view_handler, ["GET"], "scope probe")
    ]

    metadata = Path(__file__).resolve().parents[2] / "metadata.yaml"
    assert 'tested_astrbot_version: "4.26.7"' in metadata.read_text(encoding="utf-8")


def test_astrbot_v4267_temp_text_part_is_current_turn_only() -> None:
    (
        _AstrMessageEvent,
        _Context,
        Message,
        _PersonaManager,
        ProviderGoogleGenAI,
        ProviderRequest,
        _StarTools,
        TextPart,
        dump_messages_with_checkpoints,
    ) = _runtime_contract_api()

    system_prompt = "static persona prompt"
    temporary_overlay = TextPart(text="[sylanne_runtime_overlay] transient").mark_as_temp()
    request = ProviderRequest(
        prompt="ordinary user prompt",
        system_prompt=system_prompt,
        extra_user_content_parts=[temporary_overlay],
    )

    assembled = asyncio.run(
        ProviderGoogleGenAI.assemble_context(
            SimpleNamespace(),
            request.prompt,
            extra_user_content_parts=request.extra_user_content_parts,
        )
    )
    assert assembled == {
        "role": "user",
        "content": [
            {"type": "text", "text": "ordinary user prompt"},
            {"type": "text", "text": "[sylanne_runtime_overlay] transient"},
        ],
    }
    assert request.system_prompt == system_prompt

    persisted = dump_messages_with_checkpoints(
        [
            Message(
                role="user",
                content=[TextPart(text="ordinary user prompt"), temporary_overlay],
            )
        ]
    )
    assert persisted == [
        {
            "role": "user",
            "content": [{"type": "text", "text": "ordinary user prompt"}],
        }
    ]
