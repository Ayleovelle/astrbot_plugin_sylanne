"""Behavior contracts for LLM request-pipeline service injection."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from typing import Any

from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline
from sylanne_alpha.memory_system import ConversationBuffer, MemorySystem
from sylanne_alpha.person_shelf import (
    PersonShelfBucket,
    ShelfItem,
    person_shelf_kv_key,
    save_person_shelf,
)
from sylanne_alpha.plugin_services import PluginServices
from sylanne_alpha.session_state_store import SessionStateStore


class _Provider:
    def __init__(self, provider_id: str, text: str) -> None:
        self.id = provider_id
        self.provider_id = provider_id
        self.model_name = "gpt-4o"
        self.text = text

    async def text_chat(self, **_kwargs: Any) -> Any:
        return SimpleNamespace(completion_text=self.text)


class _Context:
    def __init__(self, provider: _Provider) -> None:
        self.provider = provider
        self.llm_generate_calls: list[dict[str, Any]] = []

    def get_provider_by_id(self, provider_id: str) -> _Provider | None:
        return self.provider if provider_id == self.provider.id else None

    def get_all_providers(self) -> list[_Provider]:
        return [self.provider]

    def get_using_provider(self, umo: str | None = None) -> _Provider:
        return self.provider

    def get_current_chat_provider_id(self, umo: str) -> str:
        return self.provider.id

    async def llm_generate(self, **kwargs: Any) -> Any:
        self.llm_generate_calls.append(kwargs)
        return SimpleNamespace(completion_text=self.provider.text)


class _CompatibilityPlugin:
    def __init__(self, name: str) -> None:
        self.config = {"name": name}
        self._config = {"wrong": name}
        self.logger = object()
        self.context = object()
        self._rhythm_learner = object()
        self._social_field = object()
        self.put_kv_data = object()
        self.get_kv_data = object()
        self.delete_kv_data = object()
        self._session_key = object()
        self._host = object()
        self._schedule_buffer_persist = object()
        self._has_conversation_manager = object()
        self._sync_message_to_conv_mgr = object()
        self.observe_response = object()
        self._astrbot_message = object()
        self._observed_now = object()
        self._assess_emotion = object()
        self._save_state = object()
        self._state_persistence = object()


def test_default_constructor_builds_exact_instance_local_services() -> None:
    plugin_a = _CompatibilityPlugin("a")
    plugin_b = _CompatibilityPlugin("b")

    pipe_a = LLMRequestPipeline(plugin_a)  # type: ignore[arg-type]
    pipe_b = LLMRequestPipeline(plugin_b)  # type: ignore[arg-type]

    assert pipe_a._plugin is pipe_a._p is plugin_a
    assert pipe_b._plugin is pipe_b._p is plugin_b
    assert pipe_a._services is not pipe_b._services
    expected = {
        "config": "config",
        "logger": "logger",
        "context": "context",
        "rhythm_learner": "_rhythm_learner",
        "social_field": "_social_field",
        "put_kv_data": "put_kv_data",
        "get_kv_data": "get_kv_data",
        "delete_kv_data": "delete_kv_data",
        "session_key_fn": "_session_key",
        "host_fn": "_host",
        "schedule_buffer_persist_fn": "_schedule_buffer_persist",
        "has_conversation_manager_fn": "_has_conversation_manager",
        "sync_message_to_conv_mgr_fn": "_sync_message_to_conv_mgr",
        "observe_response_fn": "observe_response",
        "astrbot_message_fn": "_astrbot_message",
        "observed_now_fn": "_observed_now",
        "assess_emotion_fn": "_assess_emotion",
        "save_state_fn": "_save_state",
        "state_persistence": "_state_persistence",
    }
    for service_name, plugin_name in expected.items():
        assert getattr(pipe_a._services, service_name) is getattr(plugin_a, plugin_name)
    assert pipe_b._services.config is plugin_b.config


class _PoisonPlugin:
    def __init__(self) -> None:
        self.accesses: list[str] = []
        self._cached_system_prompts: dict[str, str] = {}
        self._amnesia_sessions: set[str] = set()
        self._scope_runtime_registry = None
        self._store = SimpleNamespace(hosts={})
        self._life_simulator_started = True

    def __getattr__(self, name: str) -> Any:
        if name in {
            "config",
            "_config",
            "context",
            "_rhythm_learner",
            "_social_field",
            "_host",
        }:
            self.accesses.append(name)
            raise AssertionError(f"plugin fallback forbidden: {name}")
        raise AttributeError(name)


def test_explicit_services_are_the_only_provider_authority_per_instance() -> None:
    plugin_a = _PoisonPlugin()
    plugin_b = _PoisonPlugin()
    context_a = _Context(_Provider("provider-a", "reply-a"))
    context_b = _Context(_Provider("provider-b", "reply-b"))
    services_a = PluginServices(
        config={"provider_key": "provider-a"},
        context=context_a,
    )
    services_b = PluginServices(
        config={"provider_key": "provider-b"},
        context=context_b,
    )

    pipe_a = LLMRequestPipeline(plugin_a, services=services_a)  # type: ignore[arg-type]
    pipe_b = LLMRequestPipeline(plugin_b, services=services_b)  # type: ignore[arg-type]
    result_a = asyncio.run(
        pipe_a._generic_llm_call("a", provider_config_keys=["provider_key"])
    )
    result_b = asyncio.run(
        pipe_b._generic_llm_call("b", provider_config_keys=["provider_key"])
    )

    assert result_a == "reply-a"
    assert result_b == "reply-b"
    assert pipe_a._services is services_a
    assert pipe_b._services is services_b
    assert plugin_a.accesses == []
    assert plugin_b.accesses == []


def test_missing_explicit_provider_context_fails_closed_without_plugin_fallback() -> None:
    plugin = _PoisonPlugin()
    pipe = LLMRequestPipeline(
        plugin,  # type: ignore[arg-type]
        services=PluginServices(config={"provider_key": "provider-a"}),
    )

    result = asyncio.run(
        pipe._generic_llm_call("work", provider_config_keys=["provider_key"])
    )

    assert result == ""
    assert plugin.accesses == []


def test_transcription_uses_explicit_config_and_context_only() -> None:
    plugin = _PoisonPlugin()
    context = _Context(_Provider("vision", "画面很温暖"))
    pipe = LLMRequestPipeline(
        plugin,  # type: ignore[arg-type]
        services=PluginServices(
            config={
                "sylanne_alpha_transcription_enabled": True,
                "sylanne_alpha_transcription_provider_id": "vision",
            },
            context=context,
        ),
    )
    event = SimpleNamespace(
        unified_msg_origin="platform:private:user",
        message_obj=SimpleNamespace(
            message=[SimpleNamespace(type="image", url="https://example/image.png")]
        ),
    )

    result = asyncio.run(pipe._transcribe_non_text(event, ""))

    assert result == "[用户发送图片：画面很温暖]"
    assert context.llm_generate_calls[0]["provider_id"] == "vision"
    assert plugin.accesses == []


def test_missing_rhythm_social_and_host_services_do_not_probe_plugin() -> None:
    plugin = _PoisonPlugin()
    pipe = LLMRequestPipeline(
        plugin,  # type: ignore[arg-type]
        services=PluginServices(config={}),
    )
    request = SimpleNamespace(extra_user_content_parts=[])

    pipe._assemble_final_prompt(
        request=request,
        session_key="session",
        budget=None,
        gap_seconds=0.0,
        current_prompt="hello",
        time_fragment="",
        message_text="hello",
        state_fragment="",
        unfinished_fragment="",
        outreach_fragment="",
        memory_fragment="",
    )

    assert pipe._most_recent_intimate_host_key() == ""
    assert pipe._recent_context_lines("session") == []
    assert plugin.accesses == []


class _PrivateSocial:
    def is_group_context_by_key(self, _session_key: str) -> bool:
        return False


class _TrackedHosts:
    def __init__(self) -> None:
        self.items_calls = 0

    def items(self) -> list[tuple[str, Any]]:
        self.items_calls += 1
        return []


def _persona_binding(prompt: str) -> SimpleNamespace:
    return SimpleNamespace(
        request_runtime_view=SimpleNamespace(
            resolved=SimpleNamespace(persona_source=SimpleNamespace(prompt=prompt))
        )
    )


def test_explicit_same_plugin_same_session_prompt_caches_are_instance_local() -> None:
    plugin = _PoisonPlugin()
    plugin._cached_system_prompts = {"same": "plugin-poison"}
    current = {"prompt": "persona-a"}
    plugin._bound_runtime = lambda: _persona_binding(current["prompt"])
    services_a = PluginServices(config={}, observed_now_fn=lambda: 101.0)
    services_b = PluginServices(config={}, observed_now_fn=lambda: 202.0)
    pipe_a = LLMRequestPipeline(plugin, services=services_a)  # type: ignore[arg-type]
    pipe_b = LLMRequestPipeline(plugin, services=services_b)  # type: ignore[arg-type]

    pipe_a._cache_system_prompt("same")
    current["prompt"] = "persona-b"
    pipe_b._cache_system_prompt("same")

    assert pipe_a._life_sim_persona_getter("same") == "persona-a"
    assert pipe_b._life_sim_persona_getter("same") == "persona-b"
    assert plugin._cached_system_prompts == {"same": "plugin-poison"}


def test_explicit_services_never_consume_plugin_amnesia_or_scan_recent_hosts() -> None:
    plugin = _PoisonPlugin()
    tracked_hosts = _TrackedHosts()
    plugin._store = SimpleNamespace(hosts=tracked_hosts)
    plugin._amnesia_sessions = {"same"}
    services_a = PluginServices(
        config={}, social_field=_PrivateSocial(), observed_now_fn=lambda: 101.0
    )
    services_b = PluginServices(
        config={}, social_field=_PrivateSocial(), observed_now_fn=lambda: 202.0
    )
    pipe_a = LLMRequestPipeline(plugin, services=services_a)  # type: ignore[arg-type]
    pipe_b = LLMRequestPipeline(plugin, services=services_b)  # type: ignore[arg-type]

    assert pipe_a._take_amnesia_pending("same") is False
    assert pipe_b._take_amnesia_pending("same") is False
    assert plugin._amnesia_sessions == {"same"}
    assert pipe_a._most_recent_intimate_host_key() == ""
    assert pipe_b._most_recent_intimate_host_key() == ""
    asyncio.run(pipe_a._life_sim_outreach("do not route", "calm"))
    assert tracked_hosts.items_calls == 0


def test_default_mode_retains_plugin_clock_cache_and_amnesia_compatibility() -> None:
    plugin = _PoisonPlugin()
    plugin._observed_now = lambda: 303.0
    plugin._amnesia_sessions = {"same"}
    plugin._bound_runtime = lambda: _persona_binding("default-persona")
    pipe = LLMRequestPipeline(plugin)  # type: ignore[arg-type]

    pipe._cache_system_prompt("same")

    assert pipe._now() == 303.0
    assert plugin._cached_system_prompts == {"same": "default-persona"}
    assert pipe._take_amnesia_pending("same") is True
    assert plugin._amnesia_sessions == set()


class _ExplodingCaptureHost:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_request(self, event: Any, *, assessment: Any = None) -> None:
        self.events.append(event)
        raise RuntimeError("stop after event capture")


def test_explicit_same_plugin_observation_uses_each_service_clock_and_no_fallback() -> None:
    plugin = _PoisonPlugin()
    plugin._autonomy_scheduler = None
    plugin._computation_logs = []
    plugin_event_time_calls: list[float] = []
    plugin_observe_calls: list[dict[str, Any]] = []

    def _plugin_event_time(now: float) -> dict[str, Any]:
        plugin_event_time_calls.append(now)
        return {"epoch": -1.0}

    async def _plugin_observe_request(*_args: Any, **kwargs: Any) -> None:
        plugin_observe_calls.append(kwargs)

    plugin._event_time = _plugin_event_time
    plugin.observe_request = _plugin_observe_request
    host_a = _ExplodingCaptureHost()
    host_b = _ExplodingCaptureHost()
    pipe_a = LLMRequestPipeline(
        plugin,  # type: ignore[arg-type]
        services=PluginServices(
            config={}, host_fn=lambda _sk: host_a, observed_now_fn=lambda: 101.25
        ),
    )
    pipe_b = LLMRequestPipeline(
        plugin,  # type: ignore[arg-type]
        services=PluginServices(
            config={}, host_fn=lambda _sk: host_b, observed_now_fn=lambda: 202.5
        ),
    )

    asyncio.run(pipe_a._background_observe_request("same", "a"))
    asyncio.run(pipe_b._background_observe_request("same", "b"))

    assert host_a.events[0].now == 101.25
    assert host_a.events[0].event_time["epoch"] == 101.25
    assert host_b.events[0].now == 202.5
    assert host_b.events[0].event_time["epoch"] == 202.5
    assert plugin_event_time_calls == []
    assert plugin_observe_calls == []


def test_explicit_missing_observed_clock_fails_closed_without_plugin_fallback() -> None:
    plugin = _PoisonPlugin()
    plugin._autonomy_scheduler = None
    host = _ExplodingCaptureHost()
    pipe = LLMRequestPipeline(
        plugin,  # type: ignore[arg-type]
        services=PluginServices(config={}, host_fn=lambda _sk: host),
    )

    assert pipe._now() is None
    asyncio.run(pipe._background_observe_request("same", "ignored"))
    assert host.events == []


class _ShelfHost:
    class _Engine:
        def observe(self) -> dict[str, float]:
            return {"warmth": 0.5}

    def __init__(self) -> None:
        self.kernel = SimpleNamespace(
            computation=SimpleNamespace(engine=self._Engine())
        )


class _ShelfRuntimePlugin:
    """Shared runtime whose KV API is a trap in explicit-services mode."""

    def __init__(self) -> None:
        self._store = SessionStateStore()
        self._cached_system_prompts: dict[str, str] = {}
        self._scope_runtime_registry = None
        self._background_tasks: list[Any] = []
        self._memory_systems: dict[str, MemorySystem] = {}
        self._host_obj = _ShelfHost()
        self.plugin_kv: dict[str, Any] = {}
        self.plugin_kv_calls: list[tuple[str, str]] = []

    async def get_kv_data(self, key: str, default: Any = None) -> Any:
        self.plugin_kv_calls.append(("get", key))
        return self.plugin_kv.get(key, default)

    async def put_kv_data(self, key: str, value: Any) -> None:
        self.plugin_kv_calls.append(("put", key))
        self.plugin_kv[key] = value

    async def delete_kv_data(self, key: str) -> None:
        self.plugin_kv_calls.append(("delete", key))
        self.plugin_kv.pop(key, None)

    def _cfg(self, key: str, default: str = "") -> str:
        values = {
            "sylanne_alpha_cross_session_mode": "on",
            "sylanne_alpha_cross_session_scope": "all",
            "sylanne_alpha_cross_visibility_tier": "same_group",
        }
        return values.get(key, default)

    def _cfg_bool(self, key: str, default: bool = False) -> bool:
        if key == "sylanne_alpha_cross_dialogue":
            return True
        return default

    def _host(self, _session_key: str) -> _ShelfHost:
        return self._host_obj

    def _memory_system_for_session(self, session_key: str) -> MemorySystem:
        return self._memory_systems.setdefault(session_key, MemorySystem())

    async def _persist_kernel(self, _session_key: str, _host: Any) -> None:
        return None

    async def _save_sylanne_memory_state(
        self, _session_key: str, _memory_system: MemorySystem
    ) -> None:
        return None


def _explicit_shelf_services(
    plugin: _ShelfRuntimePlugin,
    backend: dict[str, Any],
    observed_now: float,
) -> PluginServices:
    async def _get(key: str, default: Any = None) -> Any:
        return backend.get(key, default)

    async def _put(key: str, value: Any) -> None:
        backend[key] = value

    async def _delete(key: str) -> None:
        backend.pop(key, None)

    return PluginServices(
        config={},
        social_field=_PrivateSocial(),
        get_kv_data=_get,
        put_kv_data=_put,
        delete_kv_data=_delete,
        host_fn=plugin._host,
        observed_now_fn=lambda: observed_now,
        state_persistence=SimpleNamespace(
            _safe_session_key=lambda session_key: session_key
        ),
    )


class _PrivateShelfEvent:
    def get_platform_id(self) -> str:
        return "unit"

    def get_sender_id(self) -> str:
        return "person"

    def get_message_type(self) -> SimpleNamespace:
        return SimpleNamespace(name="FRIEND_MESSAGE")

    def get_group_id(self) -> str:
        return ""


def test_explicit_same_plugin_shelf_recall_reads_only_each_service_backend() -> None:
    plugin = _ShelfRuntimePlugin()
    backend_a: dict[str, Any] = {}
    backend_b: dict[str, Any] = {}
    services_a = _explicit_shelf_services(plugin, backend_a, 101.0)
    services_b = _explicit_shelf_services(plugin, backend_b, 202.0)
    asyncio.run(
        save_person_shelf(
            services_a,
            "unit",
            "person",
            PersonShelfBucket(
                items=[ShelfItem("from-a", "private", "same", 101.0, 1.0)]
            ),
        )
    )
    asyncio.run(
        save_person_shelf(
            services_b,
            "unit",
            "person",
            PersonShelfBucket(
                items=[ShelfItem("from-b", "private", "same", 202.0, 1.0)]
            ),
        )
    )
    pipe_a = LLMRequestPipeline(plugin, services=services_a)  # type: ignore[arg-type]
    pipe_b = LLMRequestPipeline(plugin, services=services_b)  # type: ignore[arg-type]
    settings = SimpleNamespace(scope="all", visibility_tier="same_group")
    event = _PrivateShelfEvent()

    fragment_a = asyncio.run(
        pipe_a._recall_person_shelf_fragment(event, "same", settings)
    )
    fragment_b = asyncio.run(
        pipe_b._recall_person_shelf_fragment(event, "same", settings)
    )

    assert "from-a" in fragment_a and "from-b" not in fragment_a
    assert "from-b" in fragment_b and "from-a" not in fragment_b
    assert plugin.plugin_kv_calls == []


def _seed_shelf_buffer(plugin: _ShelfRuntimePlugin) -> None:
    buf = plugin._store.conversation_buffers.get_or_create(
        "same", lambda: ConversationBuffer(session_key="same")
    )
    buf.append("user", "hello")
    buf.append("bot", "hello back")


def test_explicit_same_plugin_shelf_writes_use_service_backend_and_clock() -> None:
    plugin = _ShelfRuntimePlugin()
    plugin._store.set_authenticated_identity(
        "same",
        sender_id="person",
        platform="unit",
        origin_scope="private",
        origin_id="same",
    )
    backend_a: dict[str, Any] = {}
    backend_b: dict[str, Any] = {}
    services_a = _explicit_shelf_services(plugin, backend_a, 101.0)
    services_b = _explicit_shelf_services(plugin, backend_b, 202.0)
    pipe_a = LLMRequestPipeline(plugin, services=services_a)  # type: ignore[arg-type]
    pipe_b = LLMRequestPipeline(plugin, services=services_b)  # type: ignore[arg-type]

    async def _summary(_prompt: str) -> str:
        return "service-owned summary"

    pipe_a._summarizer_llm_call = _summary
    pipe_b._summarizer_llm_call = _summary
    _seed_shelf_buffer(plugin)
    asyncio.run(pipe_a._flush_conversation_to_l1("same"))
    snapshot_a = deepcopy(backend_a)
    _seed_shelf_buffer(plugin)
    asyncio.run(pipe_b._flush_conversation_to_l1("same"))

    shelf_key = person_shelf_kv_key("unit", "person")
    assert backend_a[shelf_key]["items"][0]["created_at"] == 101.0
    assert backend_b[shelf_key]["items"][0]["created_at"] == 202.0
    assert backend_a == snapshot_a
    assert plugin.plugin_kv == {}
    assert plugin.plugin_kv_calls == []
