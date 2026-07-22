"""WebUI API 端点契约测试（验证端点注册和基本响应格式）。"""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, '.')

def test_glossary_data():
    from sylanne_alpha.webui_routes import GLOSSARY
    assert isinstance(GLOSSARY, dict)
    assert "伤痕" in GLOSSARY
    assert len(GLOSSARY) >= 5

def test_config_presets():
    from sylanne_alpha.webui_routes import CONFIG_PRESETS
    assert "gentle" in CONFIG_PRESETS
    assert "sharp" in CONFIG_PRESETS
    assert "quiet" in CONFIG_PRESETS
    for preset in CONFIG_PRESETS.values():
        assert "name" in preset
        assert "values" in preset


def _schema() -> dict:
    path = Path(__file__).resolve().parents[1] / "_conf_schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_model_routing_schema_is_canonical_and_backward_compatible() -> None:
    schema = _schema()
    assert schema["sylanne_alpha_aux_provider_id"]["_special"] == "select_provider"
    assert schema["sylanne_alpha_aux_provider_id"]["ui_tier"] == "primary"
    assert schema["sylanne_alpha_aux_provider_id"]["default"] == ""
    assert schema["sylanne_alpha_assessor_llm_enabled"]["default"] is False
    assert (
        schema["sylanne_alpha_life_simulation_provider_id"]["ui_tier"]
        == "advanced_provider"
    )
    assert (
        schema["sylanne_alpha_fast_assessor_provider_id"]["ui_tier"]
        == "advanced_provider"
    )
    assert schema["sylanne_alpha_fast_assessor_enabled"]["invisible"] is True
    assert schema["sylanne_alpha_main_assessor_enabled"]["invisible"] is True
    for key, entry in schema.items():
        assert {"description", "type", "default"} <= entry.keys(), key


def test_settings_get_exposes_derived_model_routing_without_rewriting_values() -> None:
    from sylanne_alpha.webui_routes import WebUIRoutes

    schema = _schema()
    config = {
        "sylanne_alpha_aux_provider_id": "",
        "sylanne_alpha_life_simulation_provider_id": "life-explicit",
        "sylanne_alpha_qzone_provider_id": "qzone-explicit",
        "sylanne_alpha_embedding_memory_enabled": False,
    }
    plugin = SimpleNamespace(
        _config=config,
        context=SimpleNamespace(),
        _load_conf_schema=lambda: schema,
    )

    response = asyncio.run(WebUIRoutes(plugin).settings_get_handler())

    assert response["values"]["sylanne_alpha_life_simulation_provider_id"] == "life-explicit"
    assert response["values"]["sylanne_alpha_qzone_provider_id"] == "qzone-explicit"
    routing = response["model_routing"]
    assert routing["chat"]["mode"] == "current_conversation"
    assert routing["auxiliary"]["mode"] == "inherit"
    assert routing["transcription"]["mode"] == "auto"
    assert routing["embedding"]["mode"] == "disabled"
    assert routing["advanced_override_count"] == 2


def test_settings_get_derives_embedding_routing_from_registered_providers() -> None:
    from sylanne_alpha.webui_routes import WebUIRoutes

    schema = _schema()

    def _response(config: dict, provider_ids: list[str]) -> dict:
        providers = [
            SimpleNamespace(provider_config={"id": provider_id, "name": provider_id})
            for provider_id in provider_ids
        ]
        plugin = SimpleNamespace(
            _config=config,
            context=SimpleNamespace(get_all_embedding_providers=lambda: providers),
            _load_conf_schema=lambda: schema,
        )
        return asyncio.run(WebUIRoutes(plugin).settings_get_handler())

    automatic = _response(
        {
            "sylanne_alpha_embedding_memory_enabled": True,
            "sylanne_alpha_embedding_memory_provider_id": "",
        },
        ["embedding-only"],
    )["model_routing"]["embedding"]
    assert automatic == {"mode": "auto", "provider_id": "embedding-only"}

    selection_required = _response(
        {
            "sylanne_alpha_embedding_memory_enabled": True,
            "sylanne_alpha_embedding_memory_provider_id": "",
        },
        ["embedding-a", "embedding-b"],
    )["model_routing"]["embedding"]
    assert selection_required == {"mode": "selection_required"}

    explicit = _response(
        {
            "sylanne_alpha_embedding_memory_enabled": True,
            "sylanne_alpha_embedding_memory_provider_id": "embedding-b",
        },
        ["embedding-a", "embedding-b"],
    )["model_routing"]["embedding"]
    assert explicit == {"mode": "explicit", "provider_id": "embedding-b"}


def test_standalone_settings_payload_keeps_embedding_type_before_generic_dedup() -> None:
    from sylanne_alpha.webui_server import _settings_payload

    embedding = SimpleNamespace(
        provider_id="shared-embedding",
        provider_config={"id": "shared-embedding", "name": "Embedding"},
    )
    chat = SimpleNamespace(
        provider_id="chat",
        provider_config={"id": "chat", "name": "Chat"},
    )
    context = SimpleNamespace(
        get_all_providers=lambda: [embedding, chat],
        get_all_embedding_providers=lambda: [embedding],
    )
    plugin = SimpleNamespace(
        _config={
            "sylanne_alpha_embedding_memory_enabled": True,
            "sylanne_alpha_embedding_memory_provider_id": "",
        },
        context=context,
    )

    payload = asyncio.run(_settings_payload(plugin))

    by_id = {item["id"]: item for item in payload["providers"]}
    assert by_id["shared-embedding"]["type"] == "embedding"
    assert payload["model_routing"]["embedding"] == {
        "mode": "auto",
        "provider_id": "shared-embedding",
    }


def test_standalone_aiohttp_and_stdlib_settings_use_the_same_payload_builder() -> None:
    import inspect

    from sylanne_alpha import webui_server

    async_source = inspect.getsource(webui_server.start_webui_server)
    stdlib_source = inspect.getsource(webui_server.start_webui_thread_server)

    assert "await _settings_payload(current_plugin)" in async_source
    assert "asyncio.run(_settings_payload(current_plugin))" in stdlib_source

if __name__ == "__main__":
    test_glossary_data()
    test_config_presets()
    print("All WebUI contract tests passed!")
