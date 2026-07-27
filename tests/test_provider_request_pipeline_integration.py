"""Focused integration contracts for request-pipeline provider routing."""

from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace
from typing import Any

import pytest

from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline
from sylanne_alpha.provider_routing import ProviderFeature


class _Provider:
    def __init__(
        self,
        provider_id: str,
        *,
        text: str | None = None,
        model_name: str = "text-only",
    ) -> None:
        self.id = provider_id
        self.provider_id = provider_id
        self.model_name = model_name
        self.text = text if text is not None else f"reply:{provider_id}"
        self.text_calls: list[dict[str, Any]] = []
        self.embedding_calls: list[str] = []

    async def text_chat(self, **kwargs: Any) -> Any:
        self.text_calls.append(kwargs)
        return SimpleNamespace(completion_text=self.text)

    async def get_embedding(self, text: str) -> list[float]:
        self.embedding_calls.append(text)
        return [0.25, 0.75]


class _Context:
    def __init__(
        self,
        providers: list[_Provider] | None = None,
        *,
        embedding_providers: list[_Provider] | None = None,
        default_id: str = "",
        current_by_umo: dict[str, str] | None = None,
    ) -> None:
        providers = providers or []
        self.providers = {provider.id: provider for provider in providers}
        self.provider_order = list(providers)
        self.embedding_providers = list(embedding_providers or [])
        self.default_id = default_id
        self.current_by_umo = dict(current_by_umo or {})
        self.embedding_inventory_calls = 0
        self.llm_generate_calls: list[dict[str, Any]] = []

    def get_provider_by_id(self, provider_id: str) -> _Provider | None:
        return self.providers.get(provider_id)

    def get_all_providers(self) -> list[_Provider]:
        return list(self.provider_order)

    def get_all_embedding_providers(self) -> list[_Provider]:
        self.embedding_inventory_calls += 1
        return list(self.embedding_providers)

    def get_using_provider(self, umo: str | None = None) -> _Provider | None:
        provider_id = self.current_by_umo.get(umo, self.default_id) if umo else self.default_id
        return self.providers.get(provider_id)

    def get_current_chat_provider_id(self, umo: str) -> str:
        return self.current_by_umo.get(umo, self.default_id)

    async def llm_generate(self, **kwargs: Any) -> Any:
        self.llm_generate_calls.append(kwargs)
        return SimpleNamespace(completion_text="看起来很开心")


class _Plugin:
    def __init__(self, config: dict[str, Any], context: _Context) -> None:
        self._config = config
        self.config = config
        self.context = context


def _pipeline(config: dict[str, Any], context: _Context) -> LLMRequestPipeline:
    return LLMRequestPipeline(_Plugin(config, context))  # type: ignore[arg-type]


def test_fast_assessor_ignores_dead_enable_boolean() -> None:
    legacy = _Provider("legacy", text="must not run")
    context = _Context([legacy])
    pipe = _pipeline(
        {
            "sylanne_alpha_fast_assessor_enabled": True,
            "sylanne_alpha_assessor_provider_id": "legacy",
        },
        context,
    )

    result = asyncio.run(pipe._assessor_llm_call("assess"))

    assert result == ""
    assert legacy.text_calls == []


def test_auxiliary_assessor_ignores_removed_fast_override() -> None:
    fast = _Provider("fast", text="fast assessment")
    aux = _Provider("aux", text="auxiliary assessment")
    context = _Context([fast, aux])
    pipe = _pipeline(
        {
            "sylanne_alpha_assessor_llm_enabled": True,
            "sylanne_alpha_fast_assessor_provider_id": "fast",
            "sylanne_alpha_aux_provider_id": "aux",
        },
        context,
    )

    result = asyncio.run(pipe._assessor_llm_call("assess"))

    assert result == "auxiliary assessment"
    assert fast.text_calls == []
    assert len(aux.text_calls) == 1


def test_auxiliary_assessor_can_follow_the_real_current_conversation_umo() -> None:
    current = _Provider("current", text="current assessment")
    default = _Provider("default", text="wrong assessment")
    context = _Context(
        [current, default],
        default_id="default",
        current_by_umo={"qq:friend:42": "current"},
    )
    pipe = _pipeline({"sylanne_alpha_assessor_llm_enabled": True}, context)

    result = asyncio.run(pipe._assessor_llm_call("assess", umo="qq:friend:42"))

    assert result == "current assessment"
    assert len(current.text_calls) == 1
    assert default.text_calls == []


def test_assessment_dispatch_uses_local_state_without_calling_fast_llm() -> None:
    class _ValueMap:
        def __init__(self) -> None:
            self.values: dict[str, Any] = {}

        def get(self, key: str, default: Any = None) -> Any:
            return self.values.get(key, default)

        def set(self, key: str, value: Any) -> None:
            self.values[key] = value

    class _UnexpectedFastAssessor:
        def __init__(self) -> None:
            self.calls = 0

        async def assess_fast(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
            self.calls += 1
            return {"valence": 1.0, "intent": "覆盖本地状态"}

    context = _Context()
    plugin = _Plugin({"sylanne_alpha_assessor_llm_enabled": True}, context)
    plugin._cfg_bool = lambda _key: True  # type: ignore[attr-defined]
    plugin._async_assessor = _UnexpectedFastAssessor()  # type: ignore[attr-defined]
    plugin._store = SimpleNamespace(  # type: ignore[attr-defined]
        last_injected_states=_ValueMap()
    )
    computation = SimpleNamespace(
        engine=SimpleNamespace(
            observe=lambda: {
                "warmth": 0.4,
                "tension": 0.0,
                "coherence": 1.0,
                "void_pressure": 0.0,
            }
        ),
        expression=SimpleNamespace(state=lambda: {"intensity": 0.0}),
        sheaf=SimpleNamespace(observe=lambda: {}),
        _last_assessment=None,
    )
    plugin._host = lambda _session_key: SimpleNamespace(  # type: ignore[attr-defined]
        kernel=SimpleNamespace(computation=computation)
    )
    pipe = LLMRequestPipeline(plugin)  # type: ignore[arg-type]

    fragment = asyncio.run(
        pipe._dispatch_assessment(
            "session",
            1.0,
        )
    )

    assert plugin._async_assessor.calls == 0  # type: ignore[attr-defined]
    assert "亲近感中" in fragment
    assert "覆盖本地状态" not in fragment


def test_generic_llm_call_keeps_legacy_provider_key_api() -> None:
    legacy = _Provider("legacy", text="legacy result")
    context = _Context([legacy])
    pipe = _pipeline({"custom_provider_key": "legacy"}, context)

    result = asyncio.run(pipe._generic_llm_call("work", provider_config_keys=["custom_provider_key"]))

    assert result == "legacy result"


def test_generic_llm_call_never_retries_an_internal_typeerror() -> None:
    """内部 TypeError 可能发生在付费请求已发出后，单次尝试不得签名探测重放。"""

    class _InternalTypeErrorProvider(_Provider):
        async def text_chat(self, **kwargs: Any) -> Any:
            self.text_calls.append(kwargs)
            raise TypeError("provider failed after dispatch")

    provider = _InternalTypeErrorProvider("legacy")
    context = _Context([provider])
    pipe = _pipeline({"custom_provider_key": "legacy"}, context)

    result = asyncio.run(
        pipe._generic_llm_call(
            "work",
            provider_config_keys=["custom_provider_key"],
            retries=1,
        )
    )

    assert result == ""
    assert len(provider.text_calls) == 1


@pytest.mark.parametrize(
    ("config", "default_id", "expected_id"),
    [
        ({"sylanne_alpha_aux_provider_id": "aux"}, "chat", "aux"),
        ({}, "chat", "chat"),
    ],
)
def test_life_blank_override_inherits_aux_then_chat(config: dict[str, Any], default_id: str, expected_id: str) -> None:
    aux = _Provider("aux", text="aux life")
    chat = _Provider("chat", text="chat life")
    context = _Context([aux, chat], default_id=default_id)
    pipe = _pipeline(config, context)

    result = asyncio.run(pipe._life_sim_llm_call("life"))

    assert result == f"{expected_id} life"
    assert len(context.providers[expected_id].text_calls) == 1


def test_explicit_invalid_life_provider_fails_closed() -> None:
    aux = _Provider("aux", text="must not fall back")
    context = _Context([aux], default_id="aux")
    pipe = _pipeline(
        {
            "sylanne_alpha_life_simulation_provider_id": "deleted",
            "sylanne_alpha_aux_provider_id": "aux",
        },
        context,
    )

    result = asyncio.run(pipe._life_sim_llm_call("life"))

    assert result == ""
    assert aux.text_calls == []


def test_outreach_message_uses_the_same_life_inheritance_route() -> None:
    aux = _Provider("aux", text="想和你说件事")
    context = _Context([aux], default_id="aux")
    pipe = _pipeline({"sylanne_alpha_aux_provider_id": "aux"}, context)

    result = asyncio.run(pipe._generate_outreach_message("散步", "开心"))

    assert result == "想和你说件事"
    assert len(aux.text_calls) == 1


def _image_event() -> Any:
    return SimpleNamespace(
        unified_msg_origin="platform:private:user",
        message_obj=SimpleNamespace(message=[SimpleNamespace(type="image", url="https://example/image.png")]),
    )


def test_transcription_explicit_invalid_provider_fails_before_llm_call() -> None:
    vision = _Provider("vision", model_name="gpt-4o")
    context = _Context([vision], default_id="vision")
    pipe = _pipeline(
        {
            "sylanne_alpha_transcription_enabled": True,
            "sylanne_alpha_transcription_provider_id": "deleted",
        },
        context,
    )

    result = asyncio.run(pipe._transcribe_non_text(_image_event(), ""))

    assert result == "[用户发送了1张图片]"
    assert context.llm_generate_calls == []


def test_transcription_prefers_multimodal_auxiliary_over_inventory_order() -> None:
    other = _Provider("other", model_name="gpt-4o")
    aux = _Provider("aux", model_name="gpt-4o")
    context = _Context([other, aux], default_id="other")
    pipe = _pipeline(
        {
            "sylanne_alpha_transcription_enabled": True,
            "sylanne_alpha_aux_provider_id": "aux",
        },
        context,
    )

    result = asyncio.run(pipe._transcribe_non_text(_image_event(), ""))

    assert result == "[用户发送图片：看起来很开心]"
    assert context.llm_generate_calls[0]["provider_id"] == "aux"


def test_transcription_re_resolves_after_current_conversation_provider_switch() -> None:
    first = _Provider("vision-a", model_name="gpt-4o")
    second = _Provider("vision-b", model_name="gemini-2.5-pro")
    context = _Context(
        [first, second],
        default_id="vision-a",
        current_by_umo={"platform:private:user": "vision-a"},
    )
    pipe = _pipeline({"sylanne_alpha_transcription_enabled": True}, context)
    event = _image_event()

    first_id = asyncio.run(pipe._detect_multimodal_provider(event))
    context.current_by_umo["platform:private:user"] = "vision-b"
    second_id = asyncio.run(pipe._detect_multimodal_provider(event))

    assert first_id == "vision-a"
    assert second_id == "vision-b"


def test_embedding_router_runs_only_after_enabled_gate() -> None:
    embedding = _Provider("embedding")
    context = _Context(embedding_providers=[embedding])
    disabled = _pipeline({}, context)

    disabled_provider = asyncio.run(disabled._embedding_provider_if_enabled())

    assert disabled_provider is None
    assert context.embedding_inventory_calls == 0

    enabled = _pipeline({"sylanne_alpha_embedding_memory_enabled": True}, context)
    enabled_provider = asyncio.run(enabled._embedding_provider_if_enabled())

    assert enabled_provider is embedding
    assert context.embedding_inventory_calls == 1


def test_embedding_router_requires_selection_when_multiple_are_registered() -> None:
    first = _Provider("embedding-a")
    second = _Provider("embedding-b")
    context = _Context(embedding_providers=[first, second])
    pipe = _pipeline({"sylanne_alpha_embedding_memory_enabled": True}, context)

    provider = asyncio.run(pipe._embedding_provider_if_enabled())

    assert provider is None


def test_all_three_embedding_call_sites_use_the_enabled_router_helper() -> None:
    source = inspect.getsource(LLMRequestPipeline)

    assert "_get_embedding_provider" not in source
    assert source.count("await self._embedding_provider_if_enabled()") == 3


def test_generic_feature_api_is_available_for_other_pipeline_callers() -> None:
    life = _Provider("life", text="feature result")
    context = _Context([life])
    pipe = _pipeline({"sylanne_alpha_life_simulation_provider_id": "life"}, context)

    result = asyncio.run(pipe._generic_llm_call("work", feature=ProviderFeature.LIFE))

    assert result == "feature result"


def test_main_assessor_zero_config_does_not_start_using_default_chat() -> None:
    default = _Provider("default", text="must not run")
    context = _Context([default], default_id="default")
    pipe = _pipeline({}, context)

    result = asyncio.run(pipe._main_assessor_llm_call("summarize"))

    assert result == ""
    assert default.text_calls == []
