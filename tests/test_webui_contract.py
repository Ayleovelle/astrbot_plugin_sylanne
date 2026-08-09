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
    assert "sylanne_alpha_fast_assessor_provider_id" not in schema
    assert "sylanne_alpha_fast_assessor_enabled" not in schema
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


def test_standalone_state_supports_resonance_spine_without_empty_fallback() -> None:
    from sylanne_alpha._engine.sylanne_core.compute.kernel import AlphaKernel
    from sylanne_alpha.webui_server import _build_state

    kernel = AlphaKernel.boot("session-1")
    kernel.computation._route_counts = {"resonance": 3, "skip": 1}
    plugin = SimpleNamespace(
        _config={},
        _hosts={"session-1": SimpleNamespace(kernel=kernel)},
        _last_user_texts={},
        _last_bot_texts={},
        _webui_runtime_id="test-runtime",
    )

    state = _build_state(plugin, session="session-1")

    assert state["current_session"] == "session-1"
    assert state["tick_count"] == kernel.computation._tick_count
    assert state["layers"]["L5_HGT"]["source"] == "moe_hgt"
    assert state["emotion"]["coherence"] == 1.0
    assert state["schema_version"] == "sylanne.webui.state.v2"
    assert state["route_stats"] == {"resonance": 3, "skip": 1}
    assert state["route_distribution"] == {"RESONANCE": 3, "SKIP": 1}
    assert all(isinstance(item, dict) for item in state["sessions"])
    assert next(item for item in state["sessions"] if item["id"] == "session-1") == {
        "id": "session-1",
        "name": "session-1",
        "tick_count": 0,
    }


def test_standalone_state_exposes_real_resonance_layer_timings() -> None:
    from sylanne_alpha._engine.sylanne_core.compute.kernel import AlphaKernel
    from sylanne_alpha.webui_server import _build_state

    kernel = AlphaKernel.boot("timed-session")
    kernel.tick({"text": "timing probe", "now": 1.0})
    plugin = SimpleNamespace(
        _config={},
        _hosts={"timed-session": SimpleNamespace(kernel=kernel)},
        _last_user_texts={},
        _last_bot_texts={},
        _webui_runtime_id="test-runtime",
    )

    state = _build_state(plugin, session="timed-session")

    assert kernel.computation.latest_timing_ns > 0
    assert [item["id"] for item in state["spine_layers"]] == [
        "L1",
        "L2",
        "L3",
        "L4",
        "L5",
        "L6",
        "L7",
    ]
    assert all(item["count"] == 1 for item in state["spine_layers"])
    assert all(item["avg"] > 0 for item in state["spine_layers"])


def test_standalone_default_session_selects_most_active_host() -> None:
    from sylanne_alpha._engine.sylanne_core.compute.kernel import AlphaKernel
    from sylanne_alpha.webui_server import _build_state

    default_kernel = AlphaKernel.boot("default")
    active_kernel = AlphaKernel.boot("active-session")
    default_kernel.computation._tick_count = 0
    active_kernel.computation._tick_count = 7
    plugin = SimpleNamespace(
        _config={},
        _hosts={
            "default": SimpleNamespace(kernel=default_kernel),
            "active-session": SimpleNamespace(kernel=active_kernel),
        },
        _last_user_texts={},
        _last_bot_texts={},
        _webui_runtime_id="test-runtime",
    )

    state = _build_state(plugin, session="default")

    assert state["current_session"] == "active-session"
    assert state["session_id"] == "active-session"
    assert state["tick_count"] == 7


def test_native_spine_layers_map_internal_timing_keys_to_l1_l7() -> None:
    from sylanne_alpha.webui_routes import WebUIRoutes

    internal_keys = [
        "perception",
        "gate",
        "void_scar",
        "sheaf",
        "hgt",
        "boundary",
        "expression",
    ]
    timing = {
        key: {
            "mean_ns": index * 1_000_000,
            "p50_ns": (index + 10) * 1_000_000,
            "p99_ns": (index + 20) * 1_000_000,
            "count": index,
        }
        for index, key in enumerate(internal_keys, start=1)
    }
    comp = SimpleNamespace(timing_stats=lambda: timing)

    layers = WebUIRoutes(SimpleNamespace())._frontend_spine_layers(comp)

    assert [item["id"] for item in layers] == [
        "L1",
        "L2",
        "L3",
        "L4",
        "L5",
        "L6",
        "L7",
    ]
    assert [
        (
            item["avg"],
            item["p50"],
            item["p99"],
            item["count"],
            item["status"],
        )
        for item in layers
    ] == [
        (float(index), float(index + 10), float(index + 20), index, "active")
        for index in range(1, 8)
    ]


if __name__ == "__main__":
    test_glossary_data()
    test_config_presets()
    print("All WebUI contract tests passed!")
