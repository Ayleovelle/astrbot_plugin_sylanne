"""WebUI API 端点契约测试（验证端点注册和基本响应格式）。"""
import asyncio
import json
import socket
import sys
from contextlib import closing
from pathlib import Path
from types import ModuleType, SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

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


def test_probe_handler_reads_the_plugin_config_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """The active probe route must not depend on an unbound service container."""
    import sylanne_alpha.webui_routes as webui_routes

    async def no_network_probe(_fn):
        return {"ok": False, "error": "test"}

    monkeypatch.setattr(webui_routes.asyncio, "to_thread", no_network_probe)
    plugin = SimpleNamespace(
        _config={
            "sylanne_webui_enabled": False,
            "sylanne_webui_host": "127.0.0.9",
            "sylanne_webui_port": 2818,
        },
        _webui_runtime_info=lambda: {"runtime_id": "probe-test"},
        _iter_loaded_webui_server_modules=lambda: [],
    )

    payload = asyncio.run(webui_routes.WebUIRoutes(plugin).probe_handler())

    assert payload["enabled"] is False
    assert payload["host"] == "127.0.0.9"
    assert payload["port"] == 2818


@pytest.mark.parametrize(
    ("handler_name", "relative_path", "content_type"),
    [
        ("logo_handler", "logo.png", "image/png"),
        ("dashboard_handler", "UI/index.html", "text/html; charset=utf-8"),
    ],
)
def test_static_handlers_resolve_the_canonical_plugin_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    handler_name: str,
    relative_path: str,
    content_type: str,
) -> None:
    """Logo and dashboard routes must use WebUIRoutes._plugin_dir."""
    from sylanne_alpha.webui_routes import WebUIRoutes

    target = tmp_path / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"fixture")
    web = ModuleType("astrbot.api.web")
    web.error_response = lambda message, status_code: {"error": message, "status": status_code}
    web.file_response = lambda path, content_type: {
        "path": Path(path),
        "content_type": content_type,
    }
    monkeypatch.setitem(sys.modules, "astrbot.api.web", web)
    monkeypatch.setattr(WebUIRoutes, "_plugin_dir", str(tmp_path))

    response = asyncio.run(getattr(WebUIRoutes(SimpleNamespace()), handler_name)())

    assert response == {"path": target, "content_type": content_type}


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


class _ObservationStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def query(
        self,
        session: str,
        *,
        group: str,
        from_ms: int | None,
        to_ms: int | None,
        max_points: int,
    ) -> dict:
        self.calls.append(
            {
                "session": session,
                "group": group,
                "from_ms": from_ms,
                "to_ms": to_ms,
                "max_points": max_points,
            }
        )
        return {
            "schema_version": "sylanne.observation.history.v1",
            "session": session,
            "group": group,
            "points": [],
            "sample_count": 0,
            "downsampled": False,
            "partial": False,
            "storage": {
                "used_bytes": 17,
                "limit_bytes": 0,
                "oldest_ms": None,
                "segment_count": 0,
                "cleanup_active": False,
            },
        }


def _observation_plugin(store: _ObservationStore | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        _session_ctx=SimpleNamespace(
            observation_history_store=store or _ObservationStore()
        )
    )


def test_observation_history_query_parser_validates_and_clamps() -> None:
    from sylanne_alpha.webui_routes import parse_observation_history_query

    assert parse_observation_history_query(
        {
            "session": " friend:42 ",
            "group": "timing",
            "from_ms": "0",
            "to_ms": "900",
            "max_points": "5000",
        }
    ) == {
        "session": "friend:42",
        "group": "timing",
        "from_ms": 0,
        "to_ms": 900,
        "max_points": 1000,
    }
    assert parse_observation_history_query(
        {"session": "s", "group": "emotion"}
    )["max_points"] == 240
    assert parse_observation_history_query(
        {"session": "s", "group": "emotion", "max_points": "-7"}
    )["max_points"] == 1


@pytest.mark.parametrize(
    ("query", "message"),
    [
        ({"session": "", "group": "emotion"}, "session"),
        ({"session": "s", "group": "route"}, "group"),
        ({"session": "s", "group": "unknown"}, "group"),
        ({"session": "s", "group": "emotion", "from_ms": "-1"}, "from_ms"),
        ({"session": "s", "group": "emotion", "to_ms": "-1"}, "to_ms"),
        ({"session": "s", "group": "emotion", "from_ms": "1.5"}, "from_ms"),
        ({"session": "s", "group": "emotion", "to_ms": ""}, "to_ms"),
        ({"session": "s", "group": "emotion", "max_points": "many"}, "max_points"),
        (
            {
                "session": "s",
                "group": "emotion",
                "from_ms": "11",
                "to_ms": "10",
            },
            "from_ms",
        ),
    ],
)
def test_observation_history_query_parser_rejects_invalid_values(
    query: dict[str, str],
    message: str,
) -> None:
    from sylanne_alpha.webui_routes import parse_observation_history_query

    with pytest.raises(ValueError, match=message):
        parse_observation_history_query(query)


def test_observation_history_payload_is_the_single_store_query_mapping() -> None:
    from sylanne_alpha.webui_routes import build_observation_history_payload

    store = _ObservationStore()
    payload = build_observation_history_payload(
        _observation_plugin(store),
        {
            "session": "session-a",
            "group": "routing",
            "from_ms": "10",
            "to_ms": "20",
            "max_points": "12",
        },
    )

    assert store.calls == [
        {
            "session": "session-a",
            "group": "routing",
            "from_ms": 10,
            "to_ms": 20,
            "max_points": 12,
        }
    ]
    assert payload["storage"]["limit_bytes"] is None


def test_native_observation_history_handler_and_error_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sylanne_alpha.webui_routes import WebUIRoutes

    store = _ObservationStore()
    plugin = _observation_plugin(store)
    web = ModuleType("astrbot.api.web")
    web.request = SimpleNamespace(
        query={"session": "native-session", "group": "boundary"}
    )
    monkeypatch.setitem(sys.modules, "astrbot.api.web", web)

    payload = asyncio.run(WebUIRoutes(plugin).observation_history_handler())
    assert payload["session"] == "native-session"
    assert store.calls[-1]["max_points"] == 240

    web.request.query = {"session": "", "group": "boundary"}
    error = asyncio.run(WebUIRoutes(plugin).observation_history_handler())
    assert set(error) == {"error"}
    assert "session" in error["error"]


def test_native_observation_history_route_is_explicitly_retired() -> None:
    import inspect
    import main
    from sylanne_alpha.webui_routes import LEGACY_SCOPED_PRIVATE_ROUTES

    source = inspect.getsource(main.EmotionalStatePlugin._register_web_apis)

    assert ("/api/observation_history", ("GET",)) in LEGACY_SCOPED_PRIVATE_ROUTES
    assert "LEGACY_SCOPED_PRIVATE_ROUTES" in source
    assert "legacy_scope_gone_handler" in source


def _unused_local_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as stream:
        stream.bind(("127.0.0.1", 0))
        return int(stream.getsockname()[1])


def test_aiohttp_observation_history_endpoint_is_retired_before_payload() -> None:
    from aiohttp import ClientSession
    from sylanne_alpha import webui_server

    async def exercise() -> None:
        token = "observation-test-token"
        port = _unused_local_port()
        store = _ObservationStore()
        plugin = _observation_plugin(store)
        webui_server._active_token = token
        task = asyncio.create_task(
            webui_server.start_webui_server(plugin, host="127.0.0.1", port=port)
        )
        try:
            async with ClientSession(
                headers={"Authorization": f"Bearer {token}"}
            ) as client:
                response = None
                for _ in range(100):
                    try:
                        response = await client.get(
                            f"http://127.0.0.1:{port}/api/observation_history",
                            params={"session": "aiohttp", "group": "feedback"},
                        )
                        break
                    except OSError:
                        await asyncio.sleep(0.01)
                assert response is not None
                async with response:
                    assert response.status == 410
                    assert await response.json() == {"error": "scope_required"}
            assert store.calls == []
        finally:
            task.cancel()
            await task

    asyncio.run(exercise())


def test_stdlib_observation_history_endpoint_is_retired_before_payload() -> None:
    from sylanne_alpha import webui_server

    token = "observation-test-token"
    store = _ObservationStore()
    plugin = _observation_plugin(store)
    webui_server._active_token = token
    webui_server.start_webui_thread_server(plugin, host="127.0.0.1", port=0)
    try:
        assert webui_server._httpd is not None
        port = int(webui_server._httpd.server_address[1])
        request = Request(
            f"http://127.0.0.1:{port}/api/observation_history"
            "?session=stdlib&group=gate&max_points=2",
            headers={"Authorization": f"Bearer {token}"},
        )
        with pytest.raises(HTTPError) as caught:
            urlopen(request, timeout=2)
        assert caught.value.code == 410
        assert store.calls == []
    finally:
        asyncio.run(webui_server.stop_webui_server())


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


def test_native_pages_state_after_tick_is_json_serializable(monkeypatch) -> None:
    from sylanne_alpha._engine.sylanne_core.compute.kernel import AlphaKernel
    from sylanne_alpha.webui_routes import WebUIRoutes

    session_key = "native-pages"
    kernel = AlphaKernel.boot(session_key)
    kernel.tick({"text": "serialization probe", "now": 1.0})
    host = SimpleNamespace(kernel=kernel)
    plugin = SimpleNamespace(
        _hosts={session_key: host},
        _known_webui_sessions=lambda requested: [session_key],
        _host=lambda requested: host,
        _webui_runtime_info=lambda: {"runtime_id": "test-runtime"},
        _persona_profile=lambda requested: {},
        _life_simulator=SimpleNamespace(to_dict=lambda: {}),
    )
    web = ModuleType("astrbot.api.web")
    web.request = SimpleNamespace(query={"session": session_key})
    monkeypatch.setitem(sys.modules, "astrbot.api.web", web)

    payload = asyncio.run(WebUIRoutes(plugin).state_handler())

    assert isinstance(kernel.computation.last_hdc_sample, bytearray)
    json.dumps(payload)
    assert payload["layers"]["L1_HDC"]["sample_bits"] == list(
        kernel.computation.last_hdc_sample
    )


if __name__ == "__main__":
    test_glossary_data()
    test_config_presets()
    print("All WebUI contract tests passed!")
