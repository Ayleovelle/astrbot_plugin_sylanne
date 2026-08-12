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

    def __getattr__(self, name: str) -> Any:
        if name in {
            "config",
            "_config",
            "context",
            "_rhythm_learner",
            "_social_field",
            "_host",
            "_life_simulator_started",
            "_start_life_simulator",
            "_start_webui_if_enabled",
            "_autonomy_scheduler",
            "_computation_logs",
            "_detect_astrbot_group_context",
            "_life_simulator",
            "_proactive_scheduler",
            "_proactive_dispatch_audit",
        }:
            self.accesses.append(name)
            raise AssertionError(f"plugin fallback forbidden: {name}")
        raise AttributeError(name)


class _CachePoisonPlugin:
    @property
    def _cached_system_prompts(self) -> dict[str, str]:
        raise AssertionError("explicit cache must not touch plugin storage")


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


def test_explicit_prompt_cache_does_not_evaluate_plugin_fallback_property() -> None:
    pipe = LLMRequestPipeline(  # type: ignore[arg-type]
        _CachePoisonPlugin(),
        services=PluginServices(config={}),
    )
    pipe._cached_system_prompts["same"] = "service-owned"

    assert pipe._life_sim_persona_getter("same") == "service-owned"


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


class _BudgetWrites:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def set(self, session_key: str, value: Any) -> None:
        self.calls.append((session_key, value))


def _gap_host(last_now: float) -> SimpleNamespace:
    return SimpleNamespace(kernel=SimpleNamespace(last_event={"now": last_now}))


def test_explicit_compute_budget_uses_service_clock_and_host_without_plugin_helpers() -> None:
    plugin = _PoisonPlugin()
    budget_writes = _BudgetWrites()
    plugin._store = SimpleNamespace(last_request_budgets=budget_writes)
    plugin_calls: list[str] = []
    plugin._state_injection_budget_for_request = (
        lambda _sk, _request: plugin_calls.append("budget") or "plugin-budget"
    )
    plugin._time_context_fragment = (
        lambda _sk: plugin_calls.append("time") or "plugin-time"
    )
    pipe_a = LLMRequestPipeline(  # type: ignore[arg-type]
        plugin,
        services=PluginServices(
            config={"state_injection_max_added_chars": 111},
            host_fn=lambda _sk: _gap_host(90.0),
            observed_now_fn=lambda: 100.0,
        ),
    )
    pipe_b = LLMRequestPipeline(  # type: ignore[arg-type]
        plugin,
        services=PluginServices(
            config={"state_injection_max_added_chars": 222},
            host_fn=lambda _sk: _gap_host(200.0),
            observed_now_fn=lambda: 250.0,
        ),
    )

    budget_a, gap_a, prompt_a, time_a = asyncio.run(
        pipe_a._compute_token_budget(SimpleNamespace(prompt="a"), "same")
    )
    budget_b, gap_b, prompt_b, time_b = asyncio.run(
        pipe_b._compute_token_budget(SimpleNamespace(prompt="b"), "same")
    )

    assert (budget_a, gap_a, prompt_a, time_a) == (None, 10.0, "a", "")
    assert (budget_b, gap_b, prompt_b, time_b) == (None, 50.0, "b", "")
    assert plugin_calls == []
    assert budget_writes.calls == []


class _BodyCapture:
    def __init__(self) -> None:
        self.deltas: list[dict[str, float]] = []

    def apply_vector_delta(self, delta: dict[str, float]) -> None:
        self.deltas.append(delta)


def _life_host(warmth: float) -> SimpleNamespace:
    return SimpleNamespace(
        kernel=SimpleNamespace(
            computation=SimpleNamespace(
                engine=SimpleNamespace(observe=lambda: {"warmth": warmth})
            ),
            body=_BodyCapture(),
        )
    )


class _TrackedHostMap:
    def __init__(self, ambient_host: Any) -> None:
        self.ambient_host = ambient_host
        self.get_calls: list[str] = []

    def get(self, session_key: str) -> Any:
        self.get_calls.append(session_key)
        return self.ambient_host


def test_explicit_scoped_life_callbacks_use_each_service_host_only() -> None:
    scope = SimpleNamespace(storage_token="same")
    ambient_host = _life_host(-1.0)
    tracked_hosts = _TrackedHostMap(ambient_host)
    plugin = SimpleNamespace(
        _scope_runtime_registry=object(),
        _bound_runtime=lambda: SimpleNamespace(scope=scope),
        _store=SimpleNamespace(hosts=tracked_hosts),
    )
    host_a = _life_host(0.1)
    host_b = _life_host(0.9)
    pipe_a = LLMRequestPipeline(  # type: ignore[arg-type]
        plugin,
        services=PluginServices(config={}, host_fn=lambda _sk: host_a),
    )
    pipe_b = LLMRequestPipeline(  # type: ignore[arg-type]
        plugin,
        services=PluginServices(config={}, host_fn=lambda _sk: host_b),
    )

    assert pipe_a._life_sim_emotion() == {"warmth": 0.1}
    assert pipe_b._life_sim_emotion() == {"warmth": 0.9}
    pipe_a._life_sim_body_delta({"valence": 1.0, "arousal": 1.0})

    assert host_a.kernel.body.deltas == [
        {
            "bloodflow.warmth": 0.03,
            "temperature.warmth": 0.02,
            "nerve.sensitivity": 0.02,
            "muscle.readiness": 0.015,
        }
    ]
    assert host_b.kernel.body.deltas == []
    assert ambient_host.kernel.body.deltas == []
    assert tracked_hosts.get_calls == []


class _ShelfHost:
    class _Engine:
        def observe(self) -> dict[str, float]:
            return {"warmth": 0.5}

    def __init__(self) -> None:
        self.events: list[Any] = []
        self.kernel = SimpleNamespace(
            computation=SimpleNamespace(engine=self._Engine()),
            _last_computation_result={},
        )

    def on_request(self, event: Any, *, assessment: Any = None) -> None:
        self.events.append((event, assessment))


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
        self.plugin_config_calls: list[str] = []
        self.plugin_persist_calls: list[tuple[str, str]] = []

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
        self.plugin_config_calls.append(key)
        values = {
            "sylanne_alpha_cross_session_mode": "on",
            "sylanne_alpha_cross_session_scope": "all",
            "sylanne_alpha_cross_visibility_tier": "same_group",
        }
        return values.get(key, default)

    def _cfg_bool(self, key: str, default: bool = False) -> bool:
        self.plugin_config_calls.append(key)
        if key == "sylanne_alpha_cross_dialogue":
            return True
        return default

    def _host(self, _session_key: str) -> _ShelfHost:
        return self._host_obj

    def _memory_system_for_session(self, session_key: str) -> MemorySystem:
        return self._memory_systems.setdefault(session_key, MemorySystem())

    async def _persist_kernel(self, _session_key: str, _host: Any) -> None:
        self.plugin_persist_calls.append(("kernel", _session_key))
        return None

    async def _save_sylanne_memory_state(
        self, _session_key: str, _memory_system: MemorySystem
    ) -> None:
        self.plugin_persist_calls.append(("memory", _session_key))
        return None


def _explicit_shelf_services(
    plugin: _ShelfRuntimePlugin,
    backend: dict[str, Any],
    observed_now: float,
    *,
    config: dict[str, Any] | None = None,
    save_state_fn: Any = None,
) -> PluginServices:
    async def _get(key: str, default: Any = None) -> Any:
        return backend.get(key, default)

    async def _put(key: str, value: Any) -> None:
        backend[key] = value

    async def _delete(key: str) -> None:
        backend.pop(key, None)

    service_config = {
        "sylanne_alpha_cross_session_mode": "on",
        "sylanne_alpha_cross_session_scope": "all",
        "sylanne_alpha_cross_visibility_tier": "same_group",
        "sylanne_alpha_cross_dialogue": True,
    }
    if config is not None:
        service_config = config

    return PluginServices(
        config=service_config,
        social_field=_PrivateSocial(),
        get_kv_data=_get,
        put_kv_data=_put,
        delete_kv_data=_delete,
        host_fn=plugin._host,
        observed_now_fn=lambda: observed_now,
        save_state_fn=save_state_fn,
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


def test_explicit_same_plugin_shelf_recall_uses_each_service_config_only() -> None:
    plugin = _ShelfRuntimePlugin()
    backend_a: dict[str, Any] = {}
    backend_b: dict[str, Any] = {}
    services_a = _explicit_shelf_services(plugin, backend_a, 101.0)
    services_b = _explicit_shelf_services(plugin, backend_b, 202.0, config={})
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

    fragment_a = asyncio.run(
        pipe_a._prepare_memory_context(
            "same",
            "hello",
            gap_seconds=200.0,
            realtime_enabled=False,
            history_depth=2,
            event=_PrivateShelfEvent(),
        )
    )[2]
    fragment_b = asyncio.run(
        pipe_b._prepare_memory_context(
            "same",
            "hello",
            gap_seconds=200.0,
            realtime_enabled=False,
            history_depth=2,
            event=_PrivateShelfEvent(),
        )
    )[2]

    assert "from-a" in fragment_a
    assert "from-b" not in fragment_b
    assert plugin.plugin_config_calls == []


def _seed_shelf_buffer(pipe: LLMRequestPipeline) -> None:
    buf = pipe._conversation_buffer_for_session(
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
    _seed_shelf_buffer(pipe_a)
    asyncio.run(pipe_a._flush_conversation_to_l1("same"))
    snapshot_a = deepcopy(backend_a)
    _seed_shelf_buffer(pipe_b)
    asyncio.run(pipe_b._flush_conversation_to_l1("same"))

    shelf_key = person_shelf_kv_key("unit", "person")
    assert backend_a[shelf_key]["items"][0]["created_at"] == 101.0
    assert backend_b[shelf_key]["items"][0]["created_at"] == 202.0
    assert backend_a == snapshot_a
    assert plugin.plugin_kv == {}
    assert plugin.plugin_kv_calls == []


def test_explicit_same_plugin_shelf_write_uses_each_service_config_only() -> None:
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
    pipe_a = LLMRequestPipeline(  # type: ignore[arg-type]
        plugin,
        services=_explicit_shelf_services(plugin, backend_a, 101.0),
    )
    pipe_b = LLMRequestPipeline(  # type: ignore[arg-type]
        plugin,
        services=_explicit_shelf_services(plugin, backend_b, 202.0, config={}),
    )

    async def _summary(_prompt: str) -> str:
        return "service-owned summary"

    pipe_a._summarizer_llm_call = _summary
    pipe_b._summarizer_llm_call = _summary
    _seed_shelf_buffer(pipe_a)
    asyncio.run(pipe_a._flush_conversation_to_l1("same"))
    _seed_shelf_buffer(pipe_b)
    asyncio.run(pipe_b._flush_conversation_to_l1("same"))

    shelf_key = person_shelf_kv_key("unit", "person")
    assert shelf_key in backend_a
    assert shelf_key not in backend_b
    assert plugin.plugin_config_calls == []


def test_explicit_persistence_uses_service_callback_and_missing_is_safe_noop() -> None:
    plugin = _ShelfRuntimePlugin()
    callback_calls: list[str] = []

    async def _save_state(session_key: str) -> None:
        callback_calls.append(session_key)

    pipe_with_callback = LLMRequestPipeline(  # type: ignore[arg-type]
        plugin,
        services=_explicit_shelf_services(
            plugin,
            {},
            101.0,
            config={},
            save_state_fn=_save_state,
        ),
    )
    pipe_without_callback = LLMRequestPipeline(  # type: ignore[arg-type]
        plugin,
        services=_explicit_shelf_services(plugin, {}, 202.0, config={}),
    )

    async def _summary(_prompt: str) -> str:
        return "service-owned summary"

    pipe_with_callback._summarizer_llm_call = _summary
    pipe_without_callback._summarizer_llm_call = _summary
    _seed_shelf_buffer(pipe_with_callback)
    asyncio.run(pipe_with_callback._flush_conversation_to_l1("same"))
    _seed_shelf_buffer(pipe_without_callback)
    asyncio.run(pipe_without_callback._flush_conversation_to_l1("same"))

    assert callback_calls == ["same"]
    assert plugin.plugin_persist_calls == []


class _FullAuthorityPoisonPlugin:
    """Explicit-mode host whose ambient lifecycle integrations are all traps."""

    _BANNED = {
        "_life_simulator_started",
        "_start_life_simulator",
        "_start_webui_if_enabled",
        "_autonomy_scheduler",
        "_computation_logs",
        "_detect_astrbot_group_context",
        "_life_simulator",
        "_proactive_scheduler",
        "_proactive_dispatch_audit",
        "_memory_system_for_session",
    }

    def __init__(self) -> None:
        self.accesses: list[str] = []
        self._scope_runtime_registry = None
        self._store = SessionStateStore()

    def __getattr__(self, name: str) -> Any:
        if name in self._BANNED:
            self.accesses.append(name)
            raise AssertionError(f"explicit ambient capability forbidden: {name}")
        raise AttributeError(name)


class _GroupSocial(_PrivateSocial):
    def is_group_context_by_key(self, _session_key: str) -> bool:
        return True

    def extract_group_id_from_key(self, _session_key: str) -> str:
        return "group"

    def drain_shadow_buffer(self, _group_id: str) -> list[dict[str, Any]]:
        return []


class _ObservationEngine:
    def __init__(self, warmth: float = 0.4) -> None:
        self._warmth = warmth
        self.scar_state = SimpleNamespace(scars=[])
        self.void_space = SimpleNamespace(voids=[])
        self._coherence = 1.0

    def observe(self) -> dict[str, float]:
        return {"warmth": self._warmth}

    def expression_drive(self) -> float:
        return 0.0


class _ObservationHost:
    def __init__(self, warmth: float = 0.4) -> None:
        self.events: list[Any] = []
        self.kernel = SimpleNamespace(
            computation=SimpleNamespace(engine=_ObservationEngine(warmth)),
            _last_computation_result={},
        )

    def on_request(self, event: Any, *, assessment: Any = None) -> None:
        self.events.append((event, assessment))


def test_explicit_lifecycle_and_optional_integrations_never_probe_plugin(
    monkeypatch: Any,
) -> None:
    plugin = _FullAuthorityPoisonPlugin()
    host = _ObservationHost()
    services = PluginServices(
        config={},
        social_field=_GroupSocial(),
        session_key_fn=lambda _event: "",
        host_fn=lambda _session_key: host,
        observed_now_fn=lambda: 101.0,
    )
    pipe = LLMRequestPipeline(plugin, services=services)  # type: ignore[arg-type]
    request = SimpleNamespace(extra_user_content_parts=[])

    asyncio.run(pipe._on_llm_request_inner(SimpleNamespace(), request))
    pipe._assemble_final_prompt(
        request=request,
        session_key="same",
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
    asyncio.run(pipe._background_observe_request("same", "hello"))

    qzone_calls: list[Any] = []

    async def _qzone_trap(plugin_arg: Any, *_args: Any) -> None:
        qzone_calls.append(plugin_arg)

    from sylanne_alpha import qzone_share

    monkeypatch.setattr(qzone_share, "handle_share_intent_candidate", _qzone_trap)
    asyncio.run(pipe._qzone_candidate_handler(SimpleNamespace(), SimpleNamespace()))
    pipe._mark_life_outcome("event", "consumed", "same")
    pipe._record_dispatch_feedback("same", "answered", "event")

    assert host.events
    assert qzone_calls == []
    assert plugin.accesses == []
    assert "_background_tasks" not in plugin.__dict__
    assert plugin._store.conversation_buffers.snapshot_items() == []


class _AssessmentHost:
    def __init__(self, warmth: float) -> None:
        self.kernel = SimpleNamespace(
            computation=SimpleNamespace(
                engine=SimpleNamespace(
                    observe=lambda: {
                        "warmth": warmth,
                        "tension": 0.0,
                        "coherence": 1.0,
                        "void_pressure": 0.0,
                    }
                ),
                sheaf=SimpleNamespace(
                    observe=lambda: {"dissociation_pressure": 0.0}
                ),
                expression=SimpleNamespace(state=lambda: {"intensity": 0.0}),
                _last_assessment={},
            )
        )


def test_explicit_same_plugin_same_session_assessment_state_is_pipeline_owned() -> None:
    plugin = _ShelfRuntimePlugin()
    host = _AssessmentHost(0.4)
    services_a = PluginServices(config={}, host_fn=lambda _sk: host)
    services_b = PluginServices(config={}, host_fn=lambda _sk: host)
    pipe_a = LLMRequestPipeline(plugin, services=services_a)  # type: ignore[arg-type]
    pipe_b = LLMRequestPipeline(plugin, services=services_b)  # type: ignore[arg-type]

    async def _first_pair() -> tuple[str, str]:
        first = await asyncio.gather(
            pipe_a._dispatch_assessment("same", 1.0),
            pipe_b._dispatch_assessment("same", 1.0),
        )
        return first[0], first[1]

    first_a, first_b = asyncio.run(_first_pair())
    second_a = asyncio.run(pipe_a._dispatch_assessment("same", 1.0))

    assert first_a == "[当前状态：亲近感中]"
    assert first_b == "[当前状态：亲近感中]"
    assert second_a == ""
    assert plugin._store.last_injected_states.snapshot_items() == []


def test_explicit_same_plugin_same_session_buffers_and_memory_are_pipeline_owned() -> None:
    plugin = _ShelfRuntimePlugin()
    services_a = _explicit_shelf_services(plugin, {}, 101.0, config={})
    services_b = _explicit_shelf_services(plugin, {}, 202.0, config={})
    pipe_a = LLMRequestPipeline(plugin, services=services_a)  # type: ignore[arg-type]
    pipe_b = LLMRequestPipeline(plugin, services=services_b)  # type: ignore[arg-type]
    prompts_a: list[str] = []
    prompts_b: list[str] = []

    async def _summary_a(prompt: str) -> str:
        prompts_a.append(prompt)
        return "summary-a"

    async def _summary_b(prompt: str) -> str:
        prompts_b.append(prompt)
        return "summary-b"

    pipe_a._summarizer_llm_call = _summary_a
    pipe_b._summarizer_llm_call = _summary_b

    async def _exercise() -> None:
        await asyncio.gather(
            pipe_a._background_observe_request("same", "a-one"),
            pipe_b._background_observe_request("same", "b-one"),
        )
        await asyncio.gather(
            pipe_a._flush_conversation_to_l1("same"),
            pipe_b._flush_conversation_to_l1("same"),
        )
        await pipe_a._background_observe_request("same", "a-two")
        await pipe_a._flush_conversation_to_l1("same")

    asyncio.run(_exercise())

    assert len(prompts_a) == 2
    assert len(prompts_b) == 1
    assert "a-one" in prompts_a[0] and "b-one" not in prompts_a[0]
    assert "b-one" in prompts_b[0] and "a-one" not in prompts_b[0]
    assert "a-two" in prompts_a[1] and "b-one" not in prompts_a[1]
    assert pipe_a._memory_system_for_session("same") is not pipe_b._memory_system_for_session(
        "same"
    )
    assert plugin._store.conversation_buffers.snapshot_items() == []
    assert plugin._memory_systems == {}


def test_legacy_new_only_shelf_recall_lazily_builds_compat_services() -> None:
    plugin = _ShelfRuntimePlugin()
    plugin.config = {}
    plugin._social_field = _PrivateSocial()
    plugin.plugin_kv[person_shelf_kv_key("unit", "person")] = PersonShelfBucket(
        items=[ShelfItem("legacy-positive", "private", "same", 101.0, 1.0)]
    ).to_dict()
    pipe = LLMRequestPipeline.__new__(LLMRequestPipeline)
    pipe._p = plugin
    pipe._plugin = plugin

    fragment = asyncio.run(
        pipe._recall_person_shelf_fragment(
            _PrivateShelfEvent(),
            "same",
            SimpleNamespace(scope="all", visibility_tier="same_group"),
        )
    )

    assert "legacy-positive" in fragment
    assert plugin.plugin_kv_calls == [
        ("get", person_shelf_kv_key("unit", "person"))
    ]


def test_explicit_new_only_missing_services_fails_closed_without_plugin_fallback() -> None:
    plugin = _FullAuthorityPoisonPlugin()
    pipe = LLMRequestPipeline.__new__(LLMRequestPipeline)
    pipe._p = plugin
    pipe._plugin = plugin
    pipe._services_explicit = True

    fragment = asyncio.run(
        pipe._recall_person_shelf_fragment(
            _PrivateShelfEvent(),
            "same",
            SimpleNamespace(scope="all", visibility_tier="same_group"),
        )
    )

    assert fragment == ""
    assert plugin.accesses == []
