"""Behavior contracts for LLM request-pipeline service injection."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline
from sylanne_alpha.plugin_services import PluginServices


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
