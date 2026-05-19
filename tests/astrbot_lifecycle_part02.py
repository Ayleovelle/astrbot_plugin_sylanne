import asyncio
import collections
import sys
import time
import types
from types import SimpleNamespace

try:
    from tests.astrbot_lifecycle_helpers import (
        AstrBotLifecycleTests,
        FakeEvent,
        bind_async,
        fake_observation,
        fake_request,
        new_plugin,
    )
except ModuleNotFoundError:
    from astrbot_lifecycle_helpers import (
        AstrBotLifecycleTests,
        FakeEvent,
        bind_async,
        fake_observation,
        fake_request,
        new_plugin,
    )


class AstrBotLifecyclePart02(AstrBotLifecycleTests):
    def test_non_gemini_tool_request_hides_all_sylanne_tools_but_keeps_foreign_tools(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "state_injection_max_added_chars": 2400,
                "state_injection_max_parts": 8,
                "enable_realtime_chat": True,
                "realtime_chat_style_prompt_enabled": True,
            },
        )
        self._bind_common_state_hooks(plugin)

        async def fake_get_current_chat_provider_id(*, umo):
            return "openai/gpt-5.5"

        plugin.context = SimpleNamespace(
            get_current_chat_provider_id=fake_get_current_chat_provider_id,
        )
        request = fake_request(session_id="s-unified-tool-entry", prompt="查一下当前状态")
        request.tools = [
            {"type": "function", "function": {"name": "query_agent_state"}},
            {"type": "function", "function": {"name": "get_bot_emotion_state"}},
            {"type": "function", "function": {"name": "get_bot_integrated_self_state"}},
            {"type": "function", "function": {"name": "search_web"}},
        ]
        request.tool_choice = {
            "type": "function",
            "function": {"name": "get_bot_emotion_state"},
        }

        asyncio.run(plugin.on_llm_request(FakeEvent("s-unified-tool-entry"), request))

        remaining_names = [
            item.get("function", {}).get("name")
            for item in request.tools
            if isinstance(item, dict)
        ]
        self.assertEqual(remaining_names, ["search_web"])
        self.assertEqual(request.tool_choice, "auto")
        diagnostics = asyncio.run(
            plugin.get_agent_runtime_diagnostics("s-unified-tool-entry"),
        )
        injection = diagnostics["state_injection"]
        self.assertEqual(injection["context_owner"], "sylanne_plugin")
        self.assertIn(
            "sylanne_llm_tools",
            {item.get("source") for item in injection["skipped"]},
        )

    def test_claude_tool_use_request_yields_agent_owned_context(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_realtime_chat": True,
                "realtime_chat_style_prompt_enabled": True,
            },
        )
        self._bind_common_state_hooks(plugin)

        async def fake_get_current_chat_provider_id(*, umo):
            return "anthropic/claude-sonnet-4-6"

        plugin.context = SimpleNamespace(
            get_current_chat_provider_id=fake_get_current_chat_provider_id,
        )
        request = fake_request(session_id="s-claude-tool-use", prompt="继续工具结果")
        request.contexts = [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "search_web",
                        "input": {"query": "Sylanne"},
                    },
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_1",
                        "content": "ok",
                    },
                ],
            },
        ]

        asyncio.run(plugin.on_llm_request(FakeEvent("s-claude-tool-use"), request))

        self.assertEqual(request.extra_user_content_parts, [])
        diagnostics = asyncio.run(
            plugin.get_agent_runtime_diagnostics("s-claude-tool-use"),
        )
        injection = diagnostics["state_injection"]
        self.assertEqual(injection["compat_mode"], "claude_tool_use")
        self.assertEqual(injection["context_owner"], "agent")
        self.assertIn("agent_owned_context", injection["warnings"])


    def test_claude_without_tool_context_keeps_sylanne_injection(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_realtime_chat": True,
                "realtime_chat_style_prompt_enabled": True,
            },
        )
        self._bind_common_state_hooks(plugin)

        async def fake_get_current_chat_provider_id(*, umo):
            return "claude-opus-4-7"

        plugin.context = SimpleNamespace(
            get_current_chat_provider_id=fake_get_current_chat_provider_id,
        )
        request = fake_request(session_id="s-claude-normal", prompt="hello")

        asyncio.run(plugin.on_llm_request(FakeEvent("s-claude-normal"), request))

        injected = "\n".join(self._request_text_parts(request))
        self.assertIn("bot_emotion_state", injected)
        diagnostics = asyncio.run(
            plugin.get_agent_runtime_diagnostics("s-claude-normal"),
        )
        self.assertEqual(diagnostics["state_injection"]["compat_mode"], "")
        self.assertEqual(
            diagnostics["state_injection"]["context_owner"],
            "sylanne_plugin",
        )


    def test_claude_tool_use_response_is_not_intercepted(self):
        plugin = new_plugin()
        response = SimpleNamespace(
            completion_text="",
            stop_reason="tool_use",
            content=[
                {
                    "type": "tool_use",
                    "id": "toolu_2",
                    "name": "search_web",
                    "input": {"query": "Sylanne"},
                },
            ],
        )

        self.assertTrue(plugin._response_has_tool_call_payload(response))


    def test_gemini_request_with_only_sylanne_tools_removes_tools_and_disables_tool_choice(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_realtime_chat": True,
                "realtime_chat_style_prompt_enabled": True,
            },
        )
        self._bind_common_state_hooks(plugin)

        async def fake_get_current_chat_provider_id(*, umo):
            return "哈基米/gemini-3.1-flash-lite-preview"

        plugin.context = SimpleNamespace(
            get_current_chat_provider_id=fake_get_current_chat_provider_id,
        )
        request = fake_request(session_id="s-gemini-sylanne-only-tools", prompt="查一下状态")
        request.tools = [
            {"type": "function", "function": {"name": "query_agent_state"}},
            {"type": "function", "function": {"name": "get_bot_emotion_state"}},
        ]
        request.tool_choice = {
            "type": "function",
            "function": {"name": "query_agent_state"},
        }

        asyncio.run(plugin.on_llm_request(FakeEvent("s-gemini-sylanne-only-tools"), request))

        remaining_names = [
            item.get("function", {}).get("name")
            for item in request.tools
            if isinstance(item, dict)
        ]
        self.assertEqual(remaining_names, [])
        self.assertEqual(request.tool_choice, "none")
        diagnostics = asyncio.run(
            plugin.get_agent_runtime_diagnostics("s-gemini-sylanne-only-tools"),
        )
        injection = diagnostics["state_injection"]
        self.assertEqual(injection["compat_mode"], "")
        self.assertIn(
            "sylanne_llm_tools",
            {item.get("source") for item in injection["skipped"]},
        )


    def test_gemini_removed_sylanne_tool_choice_falls_back_to_auto(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_realtime_chat": True,
                "realtime_chat_style_prompt_enabled": True,
            },
        )
        self._bind_common_state_hooks(plugin)

        async def fake_get_current_chat_provider_id(*, umo):
            return "哈基米/gemini-3.1-flash-lite-preview"

        plugin.context = SimpleNamespace(
            get_current_chat_provider_id=fake_get_current_chat_provider_id,
        )
        request = fake_request(session_id="s-gemini-removed-tool-choice", prompt="查情绪")
        request.tools = [
            {"type": "function", "function": {"name": "query_agent_state"}},
            {"type": "function", "function": {"name": "get_bot_emotion_state"}},
        ]
        request.tool_choice = {
            "type": "function",
            "function": {"name": "get_bot_emotion_state"},
        }

        asyncio.run(plugin.on_llm_request(FakeEvent("s-gemini-removed-tool-choice"), request))

        self.assertEqual(
            [
                item.get("function", {}).get("name")
                for item in request.tools
                if isinstance(item, dict)
            ],
            [],
        )
        self.assertEqual(request.tool_choice, "none")


    def test_gemini_chat_provider_does_not_change_context_owner(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "emotion_provider_id": "safe-assessor-provider",
                "enable_realtime_chat": True,
                "realtime_chat_style_prompt_enabled": True,
            },
        )
        self._bind_common_state_hooks(plugin)

        async def fake_get_current_chat_provider_id(*, umo):
            return "哈基米/gemini-2.5-pro"

        plugin.context = SimpleNamespace(
            get_current_chat_provider_id=fake_get_current_chat_provider_id,
        )
        request = fake_request(session_id="s-gemini-chat-provider", prompt="hello")

        asyncio.run(plugin.on_llm_request(FakeEvent("s-gemini-chat-provider"), request))

        injected = "\n".join(self._request_text_parts(request))
        self.assertNotIn("sylanne_gemini_visible_output_guard", injected)
        self.assertIn("bot_emotion_state", injected)
        self.assertIn("realtime_chat_style", injected)
        diagnostics = asyncio.run(
            plugin.get_agent_runtime_diagnostics("s-gemini-chat-provider"),
        )
        self.assertEqual(diagnostics["state_injection"]["compat_mode"], "")
        self.assertEqual(
            diagnostics["state_injection"]["context_owner"],
            "sylanne_plugin",
        )


    def test_gemini_emotion_provider_does_not_force_chat_context_owner(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "emotion_provider_id": "gemini-assessor-provider",
                "enable_realtime_chat": True,
                "realtime_chat_style_prompt_enabled": True,
            },
        )
        self._bind_common_state_hooks(plugin)

        async def fake_get_current_chat_provider_id(*, umo):
            return "openai/gpt-5.5"

        plugin.context = SimpleNamespace(
            get_current_chat_provider_id=fake_get_current_chat_provider_id,
        )
        request = fake_request(session_id="s-chat-provider-over-assessor", prompt="hello")

        asyncio.run(plugin.on_llm_request(FakeEvent("s-chat-provider-over-assessor"), request))

        diagnostics = asyncio.run(
            plugin.get_agent_runtime_diagnostics("s-chat-provider-over-assessor"),
        )
        self.assertEqual(diagnostics["state_injection"]["compat_mode"], "")
        self.assertEqual(
            diagnostics["state_injection"]["context_owner"],
            "sylanne_plugin",
        )


    def test_model_hint_keeps_normal_context_budget_for_all_models(self):
        plugin = new_plugin()

        for hint in (
            "safe-non-gemini-assessor",
            "openai/gpt-5.5 | non-gemini",
            "google/gemini-3.1-flash-lite",
        ):
            with self.subTest(hint=hint):
                budget = plugin._state_injection_budget_for_request(
                    "s-model-hint-budget",
                    fake_request(session_id="s-model-hint-budget", prompt="hello"),
                    model_hint=hint,
                )
                self.assertEqual(budget.compat_mode, "")
                self.assertEqual(budget.max_added_chars, 2400)
                self.assertEqual(budget.max_parts, 8)


    def test_gemini_tool_result_context_uses_normal_state_budget(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_realtime_chat": True,
                "realtime_chat_style_prompt_enabled": True,
            },
        )
        self._bind_common_state_hooks(plugin)

        async def fake_get_current_chat_provider_id(*, umo):
            return "google/gemini-pro"

        plugin.context = SimpleNamespace(
            get_current_chat_provider_id=fake_get_current_chat_provider_id,
        )
        request = fake_request(session_id="s-gemini-tool-result", prompt="继续回答")
        request.contexts = [
            {"role": "assistant", "tool_calls": [{"id": "call_1"}]},
            {"role": "tool", "tool_call_id": "call_1", "content": '{"ok": true}'},
        ]

        asyncio.run(plugin.on_llm_request(FakeEvent("s-gemini-tool-result"), request))

        injected = "\n".join(self._request_text_parts(request))
        self.assertNotIn("sylanne_gemini_visible_output_guard", injected)
        self.assertIn("bot_emotion_state", injected)
        self.assertIn("realtime_chat_style", injected)


    def test_non_gemini_request_keeps_normal_state_budget(self):
        plugin = new_plugin(
            {
                "state_injection_max_added_chars": 2400,
                "state_injection_max_parts": 8,
            },
        )
        request = fake_request(session_id="s-gpt-budget", prompt="hello")
        request.model = "gpt-5.5"

        model_hint = plugin._request_model_hint_text(request)
        budget = plugin._state_injection_budget_for_request(
            "s-gpt-budget",
            request,
            model_hint=model_hint,
        )

        self.assertEqual(budget.compat_mode, "")
        self.assertEqual(budget.max_added_chars, 2400)
        self.assertEqual(budget.max_parts, 8)
        self.assertEqual(request.extra_user_content_parts, [])


    def test_gemini_request_keeps_normal_state_budget(self):
        plugin = new_plugin(
            {
                "state_injection_max_added_chars": 2400,
                "state_injection_max_parts": 8,
            },
        )
        request = fake_request(session_id="s-gemini-budget", prompt="hello")
        request.model = "gemini-3-flash-preview"

        model_hint = plugin._request_model_hint_text(request)
        budget = plugin._state_injection_budget_for_request(
            "s-gemini-budget",
            request,
            model_hint=model_hint,
        )

        self.assertEqual(budget.compat_mode, "")
        self.assertEqual(budget.max_added_chars, 2400)
        self.assertEqual(budget.max_parts, 8)
        self.assertEqual(request.extra_user_content_parts, [])


    def test_full_state_injection_falls_back_to_compact_under_added_budget(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "runtime_parameter_debug_override_enabled": True,
                "state_injection_detail": "full",
                "state_injection_request_budget_chars": 8000,
                "state_injection_reserved_chars": 500,
                "state_injection_max_added_chars": 700,
            },
        )
        self._bind_common_state_hooks(plugin)
        request = fake_request(session_id="s-full-budget", prompt="hello")

        asyncio.run(plugin.on_llm_request(FakeEvent("s-full-budget"), request))

        text = self._find_text_part(request, "bot_emotion_state")
        self.assertIn('detail="compact"', text)
        self.assertLess(len(text), 700)
        diagnostics = asyncio.run(
            plugin.get_agent_runtime_diagnostics("s-full-budget"),
        )
        injection = diagnostics["state_injection"]
        self.assertIn("emotion.compact_fallback", {
            item["source"] for item in injection["appended"]
        })
        self.assertIn("max_added_chars_exceeded", injection["warnings"])


    def test_public_inject_emotion_context_respects_state_budget(self):
        plugin = new_plugin(
            {
                "state_injection_request_budget_chars": 500,
                "state_injection_reserved_chars": 100,
            },
        )

        async def fake_fragment(self, event, request=None):
            return "fragment-" + "x" * 200

        bind_async(plugin, "get_emotion_prompt_fragment", fake_fragment)
        request = fake_request(session_id="s-public-budget", prompt="hello")
        request.system_prompt = "already-" + "y" * 800

        asyncio.run(
            plugin.inject_emotion_context(FakeEvent("s-public-budget"), request),
        )

        self.assertEqual(request.extra_user_content_parts, [])
        diagnostics = asyncio.run(
            plugin.get_agent_runtime_diagnostics("s-public-budget"),
        )
        self.assertIn(
            "request_over_budget",
            diagnostics["state_injection"]["warnings"],
        )


    def test_provider_id_is_cached_within_ttl(self):
        plugin = new_plugin({"provider_id_cache_ttl_seconds": 30.0})
        calls = []

        async def fake_get_current_chat_provider_id(*, umo):
            calls.append(umo)
            return "provider-fast"

        plugin.context = SimpleNamespace(
            get_current_chat_provider_id=fake_get_current_chat_provider_id,
        )

        first = asyncio.run(plugin._provider_id(FakeEvent("s-provider")))
        second = asyncio.run(plugin._provider_id(FakeEvent("s-provider")))

        self.assertEqual(first, "provider-fast")
        self.assertEqual(second, "provider-fast")
        self.assertEqual(calls, ["s-provider"])


    def test_request_model_hint_refetches_chat_provider_after_llm_switch(self):
        plugin = new_plugin({"provider_id_cache_ttl_seconds": 30.0})
        providers = collections.deque(
            [
                "gemini-3-flash-preview",
                "openai/gpt-5.5",
            ],
        )
        calls = []

        async def fake_get_current_chat_provider_id(*, umo):
            calls.append(umo)
            return providers.popleft()

        plugin.context = SimpleNamespace(
            get_current_chat_provider_id=fake_get_current_chat_provider_id,
        )

        first_hint = asyncio.run(
            plugin._request_model_hint_for_event(
                FakeEvent("s-provider-switch"),
                fake_request(session_id="s-provider-switch", prompt="first"),
            ),
        )
        second_hint = asyncio.run(
            plugin._request_model_hint_for_event(
                FakeEvent("s-provider-switch"),
                fake_request(session_id="s-provider-switch", prompt="second"),
            ),
        )

        self.assertIn("gemini-3-flash-preview", first_hint)
        self.assertIn("openai/gpt-5.5", second_hint)
        self.assertNotIn("gemini", second_hint.lower())
        self.assertEqual(calls, ["s-provider-switch", "s-provider-switch"])


    def test_on_llm_request_recomputes_context_owner_after_llm_switch(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "provider_id_cache_ttl_seconds": 30.0,
                "enable_realtime_chat": True,
                "realtime_chat_style_prompt_enabled": True,
            },
        )
        self._bind_common_state_hooks(plugin)
        providers = collections.deque(
            [
                "gemini-3-flash-preview",
                "openai/gpt-5.5",
            ],
        )

        async def fake_get_current_chat_provider_id(*, umo):
            return providers.popleft()

        plugin.context = SimpleNamespace(
            get_current_chat_provider_id=fake_get_current_chat_provider_id,
        )

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent("s-context-owner-switch"),
                fake_request(session_id="s-context-owner-switch", prompt="first"),
            ),
        )
        first_diagnostics = asyncio.run(
            plugin.get_agent_runtime_diagnostics("s-context-owner-switch"),
        )
        self.assertEqual(first_diagnostics["state_injection"]["compat_mode"], "")
        self.assertEqual(
            first_diagnostics["state_injection"]["context_owner"],
            "sylanne_plugin",
        )

        second_request = fake_request(
            session_id="s-context-owner-switch",
            prompt="second",
        )
        asyncio.run(
            plugin.on_llm_request(
                FakeEvent("s-context-owner-switch"),
                second_request,
            ),
        )
        second_diagnostics = asyncio.run(
            plugin.get_agent_runtime_diagnostics("s-context-owner-switch"),
        )
        second_injection = second_diagnostics["state_injection"]

        self.assertEqual(second_injection["compat_mode"], "")
        self.assertEqual(second_injection["context_owner"], "sylanne_plugin")
        self.assertIn("realtime_chat_style", "\n".join(self._request_text_parts(second_request)))


    def test_assessor_timeout_falls_back_to_heuristic(self):
        from emotion_engine import EmotionState

        plugin = new_plugin({"assessor_timeout_seconds": 0.01})

        async def fake_provider_id(self, event):
            return "slow-provider"

        async def slow_llm_generate(**kwargs):
            await asyncio.sleep(0.2)
            return SimpleNamespace(completion_text='{"label":"late"}')

        bind_async(plugin, "_provider_id", fake_provider_id)
        plugin.context = SimpleNamespace(llm_generate=slow_llm_generate)

        observation = asyncio.run(
            plugin._assess_emotion(
                event=FakeEvent("s-timeout"),
                phase="pre_response",
                previous_state=EmotionState.initial(),
                persona_profile=None,
                context_text="",
                current_text="thank you",
            ),
        )

        self.assertEqual(observation.source, "heuristic")


    def test_assessor_retries_once_after_empty_model_output(self):
        from emotion_engine import EmotionState

        plugin = new_plugin({"enable_low_signal_light_assessment": False})
        attempts = []

        async def fake_provider_id(self, event):
            return "empty-once-provider"

        async def flaky_call_llm(self, **kwargs):
            attempts.append(kwargs)
            if len(attempts) == 1:
                raise RuntimeError(
                    "OpenAI completion has no usable output. "
                    "response_id=resp-empty, finish_reason=stop",
                )
            return SimpleNamespace(
                completion_text=(
                    '{"label":"calm","dimensions":{"valence":0.1,'
                    '"arousal":0.0,"dominance":0.0,"affiliation":0.0,'
                    '"certainty":0.0,"control":0.0,"surprise":0.0},'
                    '"confidence":0.7,"reason":"retry success"}'
                ),
            )

        bind_async(plugin, "_provider_id", fake_provider_id)
        bind_async(plugin, "_call_internal_assessor_llm", flaky_call_llm)

        observation = asyncio.run(
            plugin._assess_emotion(
                event=FakeEvent("s-empty-retry"),
                phase="pre_response",
                previous_state=EmotionState.initial(),
                persona_profile=None,
                context_text="previous context",
                current_text="please update the picture style",
            ),
        )

        self.assertEqual(len(attempts), 2)
        self.assertEqual(observation.source, "llm")
        self.assertEqual(observation.label, "calm")


    def test_on_llm_response_updates_for_both_timing(self):
        plugin = new_plugin({"assessment_timing": "both"})
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        plugin._last_request_text["s-both"] = "cached request context"
        response = SimpleNamespace(completion_text="assistant completion")

        async def run_response_and_drain():
            await plugin.on_llm_response(FakeEvent("s-both"), response)
            await self._await_background_tasks(plugin)

        asyncio.run(run_response_and_drain())

        self.assertEqual(len(saves), 1)
        self.assertEqual(saves[0][0], "s-both")
        self.assertEqual(saves[0][1].label, "warm")
        self.assertEqual(assessment_calls[0]["phase"], "post_response")
        self.assertEqual(assessment_calls[0]["context_text"], "cached request context")
        self.assertEqual(assessment_calls[0]["current_text"], "assistant completion")


    def test_on_llm_response_pre_timing_clears_memory_workset_after_reply(self):
        plugin = new_plugin({"assessment_timing": "pre", "inject_state": False})
        self._bind_common_state_hooks(plugin)
        request = fake_request(session_id="s-pre-workset", prompt="我论文还没修完捏")

        async def run_turn():
            await plugin.on_llm_request(
                FakeEvent("s-pre-workset", message="我论文还没修完捏"),
                request,
            )
            plugin._sylanne_memory_recall_worksets["s-pre-workset"] = collections.deque(
                [object()],
                maxlen=5,
            )
            await plugin.on_llm_response(
                FakeEvent("s-pre-workset"),
                SimpleNamespace(completion_text="先把论文改完。"),
            )

        asyncio.run(run_turn())

        self.assertNotIn("s-pre-workset", plugin._sylanne_memory_recall_worksets)


    def test_on_llm_response_overlaps_moral_state_load_with_assessment(self):
        from moral_repair_engine import MoralRepairState

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_moral_repair_state": True,
            },
        )
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        moral_saves = []
        plugin._last_request_text["s-moral-overlap"] = "cached request context"

        async def slow_assess(self, **kwargs):
            assessment_calls.append(kwargs)
            await asyncio.sleep(0.05)
            return fake_observation()

        async def slow_load_moral(self, session_key, **kwargs):
            await asyncio.sleep(0.05)
            return MoralRepairState.initial()

        async def fake_save_moral(self, session_key, state):
            moral_saves.append((session_key, state))

        bind_async(plugin, "_assess_emotion", slow_assess)
        bind_async(plugin, "_load_moral_repair_state", slow_load_moral)
        bind_async(plugin, "_save_moral_repair_state", fake_save_moral)

        async def run_response_and_drain():
            started = time.perf_counter()
            await plugin.on_llm_response(
                FakeEvent("s-moral-overlap"),
                SimpleNamespace(completion_text="I am sorry and will repair it."),
            )
            elapsed = time.perf_counter() - started
            self.assertGreaterEqual(len(plugin._background_tasks), 1)
            await self._await_background_tasks(plugin)
            return elapsed

        elapsed = asyncio.run(run_response_and_drain())

        self.assertLess(elapsed, 0.09)
        self.assertEqual(len(saves), 1)
        self.assertEqual(len(moral_saves), 1)
        self.assertEqual(moral_saves[0][0], "s-moral-overlap")
