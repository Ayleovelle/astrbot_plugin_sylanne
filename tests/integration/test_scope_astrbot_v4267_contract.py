"""Compatibility contracts for the scoped AstrBot 4.26.7 runtime APIs."""

from __future__ import annotations

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

from astrbot.api.star import StarTools
from astrbot.core.agent.message import TextPart
from astrbot.core.persona_mgr import PersonaManager
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.context import Context


def _parameter_names(callable_obj: object) -> list[str]:
    return list(inspect.signature(callable_obj).parameters)


def test_astrbot_v4267_scoped_runtime_contract() -> None:
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
