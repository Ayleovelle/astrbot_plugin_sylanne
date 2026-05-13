import asyncio
import collections
import sys
import time
import types
import unittest
from types import SimpleNamespace

try:
    from tests.test_command_tools import bind_async, install_astrbot_stubs, new_plugin
except ModuleNotFoundError:
    from test_command_tools import bind_async, install_astrbot_stubs, new_plugin


class FakeEvent:
    def __init__(
        self,
        session_id="session-1",
        message="hello",
        sender_id=None,
        sender_name=None,
        platform_name="",
        platform_id="",
        group_id="",
    ):
        self.unified_msg_origin = session_id
        self.message_str = message
        self._sender_id = sender_id
        self._sender_name = sender_name
        self._platform_name = platform_name
        self._platform_id = platform_id
        self._group_id = group_id
        self.stopped = False
        self.stop_reason = ""

    def get_sender_id(self):
        return self._sender_id or ""

    def get_sender_name(self):
        return self._sender_name or ""

    def get_platform_name(self):
        return self._platform_name or ""

    def get_platform_id(self):
        return self._platform_id or ""

    def get_group_id(self):
        return self._group_id or ""

    def stop_event(self):
        self.stopped = True
        self.stop_reason = getattr(self, "_sylanne_default_response_stop_reason", "")


def fake_request(session_id="session-1", prompt="hello"):
    return SimpleNamespace(
        system_prompt="",
        contexts=[],
        prompt=prompt,
        extra_user_content_parts=[],
        session_id=session_id,
    )


def fake_observation(label="warm"):
    from emotion_engine import EmotionObservation

    return EmotionObservation(
        values={
            "valence": 0.48,
            "arousal": 0.22,
            "dominance": 0.18,
            "goal_congruence": 0.42,
            "certainty": 0.36,
            "control": 0.24,
            "affiliation": 0.52,
        },
        confidence=0.72,
        label=label,
        source="unit_test",
        reason="fixed lifecycle observation",
    )


class AstrBotLifecycleTests(unittest.TestCase):
    def setUp(self):
        install_astrbot_stubs()

    def _request_text_parts(self, request):
        return [part.text for part in request.extra_user_content_parts]

    def _find_text_part(self, request, marker):
        for text in self._request_text_parts(request):
            if marker in text:
                return text
        self.fail(f"missing injected text fragment containing {marker!r}")

    def _assert_no_text_part_contains(self, request, marker):
        for text in self._request_text_parts(request):
            self.assertNotIn(marker, text)

    async def _await_background_tasks(self, plugin, timeout=1.0):
        tasks = list(getattr(plugin, "_background_tasks", set()))
        if tasks:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=False),
                timeout=timeout,
            )

    def _bind_common_state_hooks(self, plugin, *, saves=None, assessment_calls=None):
        from emotion_engine import EmotionState

        saves = saves if saves is not None else []
        assessment_calls = assessment_calls if assessment_calls is not None else []

        async def fake_persona(self, event, request):
            return None

        async def fake_load_state(self, session_key, persona_profile=None, **kwargs):
            state = EmotionState.initial()
            state.updated_at = 1000.0
            return state

        async def fake_assess_emotion(self, **kwargs):
            assessment_calls.append(kwargs)
            return fake_observation()

        async def fake_save_state(self, session_key, state):
            saves.append((session_key, state))

        bind_async(plugin, "_persona_profile", fake_persona)
        bind_async(plugin, "_load_state", fake_load_state)
        bind_async(plugin, "_assess_emotion", fake_assess_emotion)
        bind_async(plugin, "_save_state", fake_save_state)
        return saves, assessment_calls

    def test_internal_llm_guard_skips_request_and_response_hooks(self):
        from main import _INTERNAL_LLM_CALL

        plugin = new_plugin()

        async def fail_if_loaded(self, *args, **kwargs):
            raise AssertionError("internal LLM calls must not touch lifecycle state")

        bind_async(plugin, "_load_state", fail_if_loaded)
        request = fake_request()
        response = SimpleNamespace(completion_text="assistant text")

        token = _INTERNAL_LLM_CALL.set(True)
        try:
            asyncio.run(plugin.on_llm_request(FakeEvent(), request))
            asyncio.run(plugin.on_llm_response(FakeEvent(), response))
        finally:
            _INTERNAL_LLM_CALL.reset(token)

        self.assertEqual(request.extra_user_content_parts, [])

    def test_disabled_plugin_skips_request_and_response_hooks(self):
        plugin = new_plugin({"enabled": False})

        async def fail_if_loaded(self, *args, **kwargs):
            raise AssertionError("disabled plugin must not touch lifecycle state")

        bind_async(plugin, "_load_state", fail_if_loaded)
        request = fake_request()
        response = SimpleNamespace(completion_text="assistant text")

        asyncio.run(plugin.on_llm_request(FakeEvent(), request))
        asyncio.run(plugin.on_llm_response(FakeEvent(), response))

        self.assertEqual(request.extra_user_content_parts, [])

    def test_on_llm_request_pre_updates_and_respects_inject_state_false(self):
        plugin = new_plugin({"assessment_timing": "pre", "inject_state": False})
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        request = fake_request(prompt="用户当前消息")

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent("s-pre", message="用户当前消息"),
                request,
            ),
        )

        self.assertEqual(len(saves), 1)
        self.assertEqual(saves[0][0], "s-pre")
        self.assertEqual(saves[0][1].label, "warm")
        self.assertEqual(request.extra_user_content_parts, [])
        self.assertEqual(assessment_calls[0]["phase"], "pre_response")
        self.assertEqual(assessment_calls[0]["current_text"], "用户当前消息")
        self.assertIn("用户当前消息", plugin._last_request_text["s-pre"])

    def test_benchmark_simulated_time_drives_lifecycle_update_timestamp(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
                "inject_state": False,
                "benchmark_enable_simulated_time": True,
                "benchmark_time_offset_seconds": 86400.0,
            },
        )
        saves, _ = self._bind_common_state_hooks(plugin)
        request = fake_request(session_id="s-sim-time", prompt="lifecycle marker")
        before = time.time()

        asyncio.run(plugin.on_llm_request(FakeEvent("s-sim-time"), request))

        self.assertEqual(len(saves), 1)
        self.assertGreaterEqual(saves[0][1].updated_at, before + 86399.0)
        self.assertLessEqual(saves[0][1].updated_at, time.time() + 86401.0)

    def test_benchmark_time_offset_is_ignored_until_explicitly_enabled(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
                "inject_state": False,
                "benchmark_enable_simulated_time": False,
                "benchmark_time_offset_seconds": 31536000.0,
            },
        )
        saves, _ = self._bind_common_state_hooks(plugin)
        request = fake_request(session_id="s-real-time", prompt="normal marker")
        before = time.time()

        asyncio.run(plugin.on_llm_request(FakeEvent("s-real-time"), request))

        self.assertEqual(len(saves), 1)
        self.assertGreaterEqual(saves[0][1].updated_at, before)
        self.assertLessEqual(saves[0][1].updated_at, time.time() + 1.0)

    def test_simulated_time_reaches_injection_only_auxiliary_fallback_loads(self):
        from fallibility_engine import FallibilityState
        from humanlike_engine import HumanlikeState
        from lifelike_learning_engine import LifelikeLearningState
        from moral_repair_engine import MoralRepairState
        from personality_drift_engine import PersonalityDriftState

        offset = 604800.0
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_humanlike_state": True,
                "enable_lifelike_learning": True,
                "enable_personality_drift": True,
                "enable_moral_repair_state": True,
                "enable_fallibility_state": True,
                "fallibility_injection_strength": 0.3,
                "benchmark_enable_simulated_time": True,
                "benchmark_time_offset_seconds": offset,
            },
        )
        self._bind_common_state_hooks(plugin)
        seen_now = []

        async def fake_load_humanlike(self, session_key, personality_model=None, *, now=None):
            seen_now.append(("humanlike", now))
            state = HumanlikeState.initial()
            state.updated_at = 1.0
            return state

        async def fake_load_lifelike(self, session_key, personality_model=None, *, now=None):
            seen_now.append(("lifelike", now))
            state = LifelikeLearningState.initial()
            state.updated_at = 1.0
            return state

        async def fake_load_drift(self, session_key, profile=None, *, now=None):
            seen_now.append(("drift", now))
            return PersonalityDriftState.initial(
                persona_fingerprint=profile.fingerprint if profile else "default",
                now=1.0,
            )

        async def fake_load_moral(self, session_key, personality_model=None, *, now=None):
            seen_now.append(("moral", now))
            state = MoralRepairState.initial()
            state.updated_at = 1.0
            return state

        async def fake_load_fallibility(self, session_key, personality_model=None, *, now=None):
            seen_now.append(("fallibility", now))
            state = FallibilityState.initial()
            state.updated_at = 1.0
            return state

        async def fake_save_aux(self, session_key, state):
            pass

        bind_async(plugin, "_load_humanlike_state", fake_load_humanlike)
        bind_async(plugin, "_load_lifelike_learning_state", fake_load_lifelike)
        bind_async(plugin, "_load_personality_drift_state", fake_load_drift)
        bind_async(plugin, "_load_moral_repair_state", fake_load_moral)
        bind_async(plugin, "_load_fallibility_state", fake_load_fallibility)
        bind_async(plugin, "_save_humanlike_state", fake_save_aux)
        bind_async(plugin, "_save_lifelike_learning_state", fake_save_aux)
        bind_async(plugin, "_save_personality_drift_state", fake_save_aux)
        bind_async(plugin, "_save_moral_repair_state", fake_save_aux)
        bind_async(plugin, "_save_fallibility_state", fake_save_aux)
        request = fake_request(session_id="s-fallback-simtime", prompt="quiet update")
        before = time.time()

        asyncio.run(plugin.on_llm_request(FakeEvent("s-fallback-simtime"), request))

        self.assertEqual(
            {name for name, _ in seen_now},
            {"humanlike", "lifelike", "drift", "moral", "fallibility"},
        )
        for _, observed_at in seen_now:
            self.assertGreaterEqual(observed_at, before + offset - 1.0)
            self.assertLessEqual(observed_at, time.time() + offset + 1.0)

    def test_on_llm_request_post_timing_skips_pre_assessment_but_injects_state(self):
        plugin = new_plugin({"assessment_timing": "post"})
        saves = []
        self._bind_common_state_hooks(plugin, saves=saves)

        async def fail_if_assessed(self, **kwargs):
            raise AssertionError("post timing must not assess during request hook")

        bind_async(plugin, "_assess_emotion", fail_if_assessed)
        request = fake_request(prompt="hello")

        asyncio.run(plugin.on_llm_request(FakeEvent("s-post"), request))

        self.assertEqual(saves, [])
        emotion_text = self._find_text_part(request, "bot_emotion_state")
        self.assertIn('detail="compact"', emotion_text)
        self.assertIn("Detailed state remains internal", emotion_text)
        self.assertNotIn("get_bot_emotion_state", emotion_text)
        self.assertNotIn("query_agent_state(", emotion_text)
        self.assertLess(len(emotion_text), 700)

    def test_state_injection_full_mode_keeps_verbose_emotion_fragment(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "runtime_parameter_debug_override_enabled": True,
                "state_injection_detail": "full",
            },
        )
        saves = []
        self._bind_common_state_hooks(plugin, saves=saves)
        request = fake_request(prompt="hello")

        asyncio.run(plugin.on_llm_request(FakeEvent("s-post-full"), request))

        self.assertEqual(saves, [])
        text = self._find_text_part(request, "bot_emotion_state")
        self.assertIn("bot_emotion_state", text)
        self.assertNotIn('detail="compact"', text)
        self.assertGreater(len(text), 700)

    def test_request_to_text_clips_context_before_assessor(self):
        plugin = new_plugin({"request_context_max_chars": 320})
        request = fake_request(prompt="current-" + "x" * 500)
        request.system_prompt = "system-" + "s" * 500
        request.contexts = [
            {"role": "user", "content": "old-" + "a" * 1200},
            {"role": "assistant", "content": "reply-" + "b" * 1200},
        ]

        text = plugin._request_to_text(request)

        self.assertLessEqual(len(text), 320 + len("\n...\n"))
        self.assertIn("[current_user]", text)
        self.assertNotIn("a" * 700, text)

    def test_request_to_text_only_reads_tail_context_without_full_copy(self):
        plugin = new_plugin({"request_context_max_chars": 1200})
        touched = []
        original_context_item_to_text = plugin._context_item_to_text

        def tracking_context_item_to_text(item):
            touched.append(item["content"])
            return original_context_item_to_text(item)

        plugin._context_item_to_text = tracking_context_item_to_text
        request = fake_request(prompt="current")
        request.contexts = [
            {"role": "user", "content": f"context-{index}"}
            for index in range(20)
        ]

        text = plugin._request_to_text(request)

        self.assertEqual(touched, [f"context-{index}" for index in range(12, 20)])
        self.assertIn("context-19", text)
        self.assertNotIn("context-0", text)

    def test_state_injection_skips_when_visible_request_is_over_budget(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "state_injection_request_budget_chars": 1200,
                "state_injection_reserved_chars": 200,
                "state_injection_max_added_chars": 800,
            },
        )
        self._bind_common_state_hooks(plugin)
        request = fake_request(session_id="s-over-budget", prompt="current")
        request.system_prompt = "persona-" + "p" * 2000
        request.contexts = [{"role": "user", "content": "history-" + "h" * 2000}]

        asyncio.run(plugin.on_llm_request(FakeEvent("s-over-budget"), request))

        self.assertEqual(request.extra_user_content_parts, [])
        diagnostics = asyncio.run(
            plugin.get_agent_runtime_diagnostics("s-over-budget"),
        )
        injection = diagnostics["state_injection"]
        self.assertEqual(injection["added_chars"], 0)
        self.assertIn("request_over_budget", injection["warnings"])
        serialized = str(injection)
        self.assertNotIn("persona-" + "p" * 20, serialized)
        self.assertNotIn("history-" + "h" * 20, serialized)

    def test_gemini_requests_use_the_same_context_path_as_other_models(self):
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
        plugin._record_realtime_assistant_history_shadow(
            "s-gemini-guard",
            full_text="你是用 IP 直连的，还是域名呀？",
            input_epoch=1,
            message_parts=[{"text": "你是用 IP 直连的，还是域名呀？"}],
        )

        async def fake_get_current_chat_provider_id(*, umo):
            return "哈基米/gemini-3-flash-preview"

        plugin.context = SimpleNamespace(
            get_current_chat_provider_id=fake_get_current_chat_provider_id,
        )
        request = fake_request(session_id="s-gemini-guard", prompt="hello")

        asyncio.run(plugin.on_llm_request(FakeEvent("s-gemini-guard"), request))

        injected = "\n".join(self._request_text_parts(request))
        self.assertNotIn("sylanne_gemini_visible_output_guard", injected)
        self.assertIn("sylanne_realtime_pending_bot_question", injected)
        self.assertIn("bot_emotion_state", injected)
        self.assertIn("realtime_chat_style", injected)
        diagnostics = asyncio.run(
            plugin.get_agent_runtime_diagnostics("s-gemini-guard"),
        )
        injection = diagnostics["state_injection"]
        self.assertEqual(injection["compat_mode"], "")
        self.assertEqual(injection["context_owner"], "sylanne_plugin")
        self.assertEqual(injection["max_added_chars"], 2400)
        self.assertGreater(injection["added_chars"], 0)
        appended_sources = {item.get("source") for item in injection["appended"]}
        self.assertIn("emotion", appended_sources)
        self.assertIn("realtime_chat.style", appended_sources)

    def test_gemini_tool_request_hides_sylanne_tools_and_keeps_foreign_tools(self):
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
            return "哈基米/gemini-3-flash-preview"

        plugin.context = SimpleNamespace(
            get_current_chat_provider_id=fake_get_current_chat_provider_id,
        )
        request = fake_request(session_id="s-gemini-tool-guard", prompt="帮我查一下记忆")
        request.tools = [
            {
                "type": "function",
                "function": {
                    "name": "query_agent_state",
                    "description": "查询状态",
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_bot_emotion_state",
                    "description": "情绪状态",
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_web",
                    "description": "其他插件工具",
                },
            },
        ]

        asyncio.run(plugin.on_llm_request(FakeEvent("s-gemini-tool-guard"), request))

        remaining_names = [
            item.get("function", {}).get("name")
            for item in request.tools
            if isinstance(item, dict)
        ]
        self.assertEqual(remaining_names, ["search_web"])
        diagnostics = asyncio.run(
            plugin.get_agent_runtime_diagnostics("s-gemini-tool-guard"),
        )
        injection = diagnostics["state_injection"]
        self.assertEqual(injection["compat_mode"], "")
        self.assertEqual(injection["context_owner"], "sylanne_plugin")
        appended_sources = {item.get("source") for item in injection["appended"]}
        skipped_sources = {item.get("source") for item in injection["skipped"]}
        self.assertIn("emotion", appended_sources)
        self.assertIn("realtime_chat.style", appended_sources)
        self.assertIn("sylanne_llm_tools", skipped_sources)

    def test_gemini_native_function_declarations_prune_only_sylanne_tools(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "state_injection_max_added_chars": 2400,
                "state_injection_max_parts": 8,
            },
        )
        self._bind_common_state_hooks(plugin)

        async def fake_get_current_chat_provider_id(*, umo):
            return "哈基米/gemini-3-flash-preview"

        plugin.context = SimpleNamespace(
            get_current_chat_provider_id=fake_get_current_chat_provider_id,
        )
        request = fake_request(session_id="s-gemini-native-tools", prompt="查一下")
        request.tools = [
            {
                "function_declarations": [
                    {"name": "query_agent_state", "description": "internal state"},
                    {"name": "get_bot_emotion_state", "description": "legacy state"},
                    {"name": "aiimg_generate", "description": "foreign image tool"},
                ],
            },
            {
                "functionDeclarations": [
                    {"name": "get_bot_integrated_self_state"},
                    {"name": "search_web"},
                ],
            },
        ]
        request.params = {
            "tools": [
                {
                    "function_declarations": [
                        {"name": "get_bot_humanlike_state"},
                        {"name": "music_search"},
                    ],
                },
            ],
        }

        asyncio.run(plugin.on_llm_request(FakeEvent("s-gemini-native-tools"), request))

        self.assertEqual(
            request.tools,
            [
                {
                    "function_declarations": [
                        {"name": "aiimg_generate", "description": "foreign image tool"},
                    ],
                },
                {
                    "functionDeclarations": [
                        {"name": "search_web"},
                    ],
                },
            ],
        )
        self.assertEqual(
            request.params["tools"],
            [
                {
                    "function_declarations": [
                        {"name": "music_search"},
                    ],
                },
            ],
        )
        diagnostics = asyncio.run(
            plugin.get_agent_runtime_diagnostics("s-gemini-native-tools"),
        )
        self.assertIn(
            "sylanne_llm_tools",
            {item.get("source") for item in diagnostics["state_injection"]["skipped"]},
        )

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

    def test_background_post_assessment_returns_without_waiting_for_assessment(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "background_post_assessment": True,
            },
        )
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        completed = asyncio.Event()

        async def slow_assess(self, **kwargs):
            assessment_calls.append(kwargs)
            await asyncio.sleep(0.05)
            return fake_observation()

        bind_async(plugin, "_assess_emotion", slow_assess)
        plugin._last_request_text["s-background-post"] = "cached request context"

        async def run_response_hook():
            started = time.perf_counter()
            await plugin.on_llm_response(
                FakeEvent("s-background-post"),
                SimpleNamespace(completion_text="assistant completion"),
            )
            hook_elapsed = time.perf_counter() - started
            self.assertEqual(saves, [])
            self.assertEqual(len(plugin._background_tasks), 1)
            await asyncio.wait_for(next(iter(plugin._background_tasks)), timeout=1.0)
            completed.set()
            return hook_elapsed

        elapsed = asyncio.run(run_response_hook())

        self.assertLess(elapsed, 0.03)
        self.assertTrue(completed.is_set())
        self.assertEqual(len(saves), 1)
        self.assertEqual(saves[0][0], "s-background-post")
        self.assertEqual(assessment_calls[0]["phase"], "post_response")
        self.assertEqual(assessment_calls[0]["context_text"], "cached request context")

    def test_background_tasks_are_cancelled_on_terminate(self):
        plugin = new_plugin()

        async def never_finishes():
            await asyncio.Event().wait()

        async def run_terminate():
            plugin._schedule_background_task(
                never_finishes(),
                label="unit_test_never_finishes",
            )
            self.assertEqual(len(plugin._background_tasks), 1)
            await plugin.terminate()

        asyncio.run(run_terminate())

        self.assertEqual(plugin._background_tasks, set())
        self.assertEqual(plugin._background_post_tasks, {})
        self.assertEqual(plugin._background_post_queues, {})
        self.assertEqual(plugin._background_post_sequence, {})
        self.assertEqual(plugin._background_post_skipped, {})

    def test_background_post_assessment_freezes_request_context_at_schedule_time(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "background_post_assessment": True,
            },
        )
        self._bind_common_state_hooks(plugin)
        assessment_started = asyncio.Event()
        release_assessment = asyncio.Event()
        assessment_calls = []

        async def pausing_assess(self, **kwargs):
            assessment_calls.append(kwargs)
            assessment_started.set()
            await release_assessment.wait()
            return fake_observation()

        bind_async(plugin, "_assess_emotion", pausing_assess)
        plugin._last_request_text["s-background-race"] = "first request context"

        async def run_response_hook():
            await plugin.on_llm_response(
                FakeEvent("s-background-race"),
                SimpleNamespace(completion_text="assistant completion"),
            )
            await asyncio.wait_for(assessment_started.wait(), timeout=1.0)
            plugin._last_request_text["s-background-race"] = "second request context"
            release_assessment.set()
            await asyncio.wait_for(next(iter(plugin._background_tasks)), timeout=1.0)

        asyncio.run(run_response_hook())

        self.assertEqual(
            assessment_calls[0]["context_text"],
            "first request context",
        )

    def test_background_post_assessment_serializes_same_session_burst_fifo(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "background_post_assessment": True,
            },
        )
        saves = []
        self._bind_common_state_hooks(plugin, saves=saves)
        saves.clear()
        release_assessment = asyncio.Event()
        assessment_calls = []

        async def pausing_assess(self, **kwargs):
            assessment_calls.append(kwargs)
            if len(assessment_calls) == 1:
                await release_assessment.wait()
            return fake_observation(kwargs["current_text"])

        bind_async(plugin, "_assess_emotion", pausing_assess)

        async def run_burst():
            plugin._last_request_text["s-burst"] = "ctx-1"
            await plugin.on_llm_response(
                FakeEvent("s-burst"),
                SimpleNamespace(completion_text="reply-1"),
            )
            while not assessment_calls:
                await asyncio.sleep(0)

            plugin._last_request_text["s-burst"] = "ctx-2"
            await plugin.on_llm_response(
                FakeEvent("s-burst"),
                SimpleNamespace(completion_text="reply-2"),
            )
            plugin._last_request_text["s-burst"] = "ctx-3"
            await plugin.on_llm_response(
                FakeEvent("s-burst"),
                SimpleNamespace(completion_text="reply-3"),
            )

            self.assertEqual(len(plugin._background_tasks), 1)
            self.assertEqual(len(plugin._background_post_tasks), 1)
            self.assertEqual(len(plugin._background_post_queues["s-burst"]), 2)
            release_assessment.set()
            await asyncio.wait_for(next(iter(plugin._background_tasks)), timeout=1.0)

        asyncio.run(run_burst())

        self.assertEqual(
            [call["current_text"] for call in assessment_calls],
            ["reply-1", "reply-2", "reply-3"],
        )
        self.assertEqual(
            [call["context_text"] for call in assessment_calls],
            ["ctx-1", "ctx-2", "ctx-3"],
        )
        self.assertEqual(
            [state.label for _, state in saves],
            ["reply-1", "reply-2", "reply-3"],
        )
        self.assertEqual(plugin._background_tasks, set())
        self.assertEqual(plugin._background_post_tasks, {})
        self.assertEqual(plugin._background_post_queues, {})

    def test_background_post_assessment_keeps_sessions_parallel(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "background_post_assessment": True,
            },
        )
        self._bind_common_state_hooks(plugin)
        release_assessment = asyncio.Event()
        started_sessions = set()

        async def pausing_assess(self, **kwargs):
            started_sessions.add(kwargs["event"].unified_msg_origin)
            await release_assessment.wait()
            return fake_observation(kwargs["current_text"])

        bind_async(plugin, "_assess_emotion", pausing_assess)

        async def run_parallel_sessions():
            plugin._last_request_text["s-a"] = "ctx-a"
            plugin._last_request_text["s-b"] = "ctx-b"
            await plugin.on_llm_response(
                FakeEvent("s-a"),
                SimpleNamespace(completion_text="reply-a"),
            )
            await plugin.on_llm_response(
                FakeEvent("s-b"),
                SimpleNamespace(completion_text="reply-b"),
            )
            while started_sessions != {"s-a", "s-b"}:
                await asyncio.sleep(0)
            self.assertEqual(len(plugin._background_tasks), 2)
            self.assertEqual(len(plugin._background_post_tasks), 2)
            release_assessment.set()
            await asyncio.gather(*list(plugin._background_tasks))

        asyncio.run(run_parallel_sessions())

        self.assertEqual(started_sessions, {"s-a", "s-b"})

    def _bind_background_worker_environment(
        self,
        plugin,
        *,
        level="normal",
        worker_cap=6,
        cpu=0.2,
        memory=0.3,
        now=None,
    ):
        if now is not None:
            plugin._test_now = now

            def observed_now(self):
                return self._test_now

            plugin._observed_now = observed_now.__get__(plugin, type(plugin))

        def resource_pressure(self):
            if cpu is None and memory is None:
                combined = 0.0
            else:
                combined = max(
                    value
                    for value in (cpu, memory)
                    if value is not None
                )
            return {
                "cpu_load_ratio": cpu,
                "cpu_source": "unit_test",
                "memory_load_ratio": memory,
                "memory_source": "unit_test",
                "combined_load_ratio": combined,
                "unknown": level == "unknown",
                "level": level,
                "worker_cap": worker_cap,
                "reason": f"environment_pressure_{level}",
                "sampled_at": getattr(plugin, "_test_now", time.time()),
            }

        plugin._background_post_resource_pressure = resource_pressure.__get__(
            plugin,
            type(plugin),
        )

    def test_background_post_assessment_parallelizes_same_session_assessments(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "background_post_assessment": True,
                "enable_dynamic_background_workers": True,
            },
        )
        self._bind_background_worker_environment(plugin, now=1000.0)
        saves, _ = self._bind_common_state_hooks(plugin)
        release_assessment = asyncio.Event()
        started_texts = []

        async def pausing_assess(self, **kwargs):
            started_texts.append(kwargs["current_text"])
            await release_assessment.wait()
            return fake_observation(kwargs["current_text"])

        bind_async(plugin, "_assess_emotion", pausing_assess)

        async def run_same_session_workers():
            for index in range(1, 5):
                plugin._last_request_text["s-same-limit"] = f"ctx-{index}"
                await plugin.on_llm_response(
                    FakeEvent("s-same-limit"),
                    SimpleNamespace(completion_text=f"reply-{index}"),
                )
            expected_workers = plugin._background_post_max_workers("s-same-limit")
            while len(started_texts) < expected_workers:
                await asyncio.sleep(0)
            self.assertEqual(
                started_texts,
                [f"reply-{index}" for index in range(1, expected_workers + 1)],
            )
            self.assertEqual(len(plugin._background_tasks), 1)
            self.assertEqual(len(plugin._background_post_tasks), 1)
            release_assessment.set()
            await asyncio.wait_for(next(iter(plugin._background_tasks)), timeout=1.0)

        asyncio.run(run_same_session_workers())

        self.assertEqual(
            started_texts,
            ["reply-1", "reply-2", "reply-3", "reply-4"],
        )
        self.assertEqual(
            [state.label for _, state in saves],
            ["reply-1", "reply-2", "reply-3", "reply-4"],
        )

    def test_background_post_workers_stay_single_without_dynamic_scale(self):
        from main import _BackgroundPostJob

        plugin = new_plugin({"enable_dynamic_background_workers": False})
        self._bind_background_worker_environment(plugin, now=1000.0)
        event = FakeEvent("s-worker-default")
        identity = plugin._agent_identity(event)
        plugin._background_post_queues["s-worker-default"] = collections.deque(
            [
                _BackgroundPostJob(
                    event,
                    identity,
                    f"reply-{index}",
                    f"ctx-{index}",
                    index,
                    time.time(),
                )
                for index in range(1, 40)
            ],
        )

        decision = plugin._background_post_adaptive_worker_decision(
            "s-worker-default",
        )

        self.assertEqual(decision["desired_workers"], 1)
        self.assertEqual(decision["dynamic_extra_workers"], 0)
        self.assertIn("dynamic_scale_disabled", decision["reasons"])
        self.assertTrue(decision["idle_workers_close_automatically"])

    def test_background_post_workers_scale_by_pressure_when_enabled(self):
        from main import _BackgroundPostJob

        plugin = new_plugin({"enable_dynamic_background_workers": True})
        self._bind_background_worker_environment(plugin, now=1000.0)
        event = FakeEvent("s-worker-adaptive")
        identity = plugin._agent_identity(event)

        def set_ready_queue(size):
            plugin._background_post_queues["s-worker-adaptive"] = collections.deque(
                [
                    _BackgroundPostJob(
                        event,
                        identity,
                        f"reply-{index}",
                        f"ctx-{index}",
                        index,
                        time.time(),
                    )
                    for index in range(1, size + 1)
                ],
            )

        for size, expected_target in [(1, 1), (2, 2), (5, 3), (10, 4), (32, 6)]:
            with self.subTest(size=size):
                plugin._background_post_worker_state.clear()
                set_ready_queue(size)
                decision = plugin._background_post_adaptive_worker_decision(
                    "s-worker-adaptive",
                )
                self.assertEqual(decision["queue_target_workers"], expected_target)
                self.assertLessEqual(decision["desired_workers"], 2)
                self.assertGreaterEqual(decision["desired_workers"], 1)
                self.assertEqual(
                    decision["dynamic_extra_workers"],
                    max(0, decision["desired_workers"] - 1),
                )
                self.assertTrue(decision["idle_workers_close_automatically"])

    def test_background_post_workers_ramp_up_in_steps_and_cooldown(self):
        from main import _BackgroundPostJob

        plugin = new_plugin({"enable_dynamic_background_workers": True})
        self._bind_background_worker_environment(plugin, now=1000.0)
        event = FakeEvent("s-worker-ramp")
        identity = plugin._agent_identity(event)
        plugin._background_post_queues["s-worker-ramp"] = collections.deque(
            [
                _BackgroundPostJob(
                    event,
                    identity,
                    f"reply-{index}",
                    f"ctx-{index}",
                    index,
                    900.0,
                )
                for index in range(1, 40)
            ],
        )

        first = plugin._background_post_adaptive_worker_decision(
            "s-worker-ramp",
            commit_scale=True,
        )
        self.assertTrue(first["scale_state"]["committed"])
        second = plugin._background_post_adaptive_worker_decision(
            "s-worker-ramp",
            commit_scale=True,
        )
        plugin._test_now += first["scale_state"]["scale_interval_seconds"] + 0.01
        third = plugin._background_post_adaptive_worker_decision(
            "s-worker-ramp",
            commit_scale=True,
        )

        self.assertEqual(first["queue_target_workers"], 6)
        self.assertEqual(first["desired_workers"], 2)
        self.assertEqual(second["desired_workers"], 2)
        self.assertIn("worker_scale_cooldown", second["reasons"])
        self.assertEqual(third["desired_workers"], 3)
        self.assertIn("worker_scale_step_up", third["reasons"])

    def test_background_post_worker_preview_does_not_commit_scale_state(self):
        from main import _BackgroundPostJob

        plugin = new_plugin({"enable_dynamic_background_workers": True})
        self._bind_background_worker_environment(plugin, now=1000.0)
        event = FakeEvent("s-worker-preview")
        identity = plugin._agent_identity(event)
        plugin._background_post_queues["s-worker-preview"] = collections.deque(
            [
                _BackgroundPostJob(
                    event,
                    identity,
                    f"reply-{index}",
                    f"ctx-{index}",
                    index,
                    900.0,
                )
                for index in range(1, 40)
            ],
        )

        preview = plugin._background_post_adaptive_worker_decision("s-worker-preview")
        self.assertFalse(preview["scale_state"]["committed"])
        self.assertNotIn("s-worker-preview", plugin._background_post_worker_state)

        dispatch_slots = plugin._background_post_max_workers("s-worker-preview")

        self.assertEqual(dispatch_slots, 2)
        self.assertIn("s-worker-preview", plugin._background_post_worker_state)

    def test_background_post_workers_throttle_under_environment_pressure(self):
        from main import _BackgroundPostJob

        plugin = new_plugin({"enable_dynamic_background_workers": True})
        self._bind_background_worker_environment(
            plugin,
            level="high",
            worker_cap=2,
            cpu=0.91,
            memory=0.62,
            now=1000.0,
        )
        event = FakeEvent("s-worker-throttle")
        identity = plugin._agent_identity(event)
        plugin._background_post_queues["s-worker-throttle"] = collections.deque(
            [
                _BackgroundPostJob(
                    event,
                    identity,
                    f"reply-{index}",
                    f"ctx-{index}",
                    index,
                    900.0,
                )
                for index in range(1, 40)
            ],
        )

        decision = plugin._background_post_adaptive_worker_decision(
            "s-worker-throttle",
        )

        self.assertEqual(decision["queue_target_workers"], 6)
        self.assertEqual(decision["target_workers"], 2)
        self.assertLessEqual(decision["desired_workers"], 2)
        self.assertLessEqual(decision["dispatch_workers"], 2)
        self.assertEqual(decision["resource_pressure"]["level"], "high")
        self.assertIn("environment_pressure_high", decision["reasons"])

    def test_background_post_workers_respect_global_worker_budget(self):
        from main import _BackgroundPostJob

        plugin = new_plugin({"enable_dynamic_background_workers": True})
        self._bind_background_worker_environment(plugin, now=1000.0)
        event = FakeEvent("s-worker-budget")
        identity = plugin._agent_identity(event)
        plugin._background_post_active["busy-a"] = {
            index: _BackgroundPostJob(event, identity, "busy", "ctx", index, 990.0)
            for index in range(1, 4)
        }
        plugin._background_post_active["busy-b"] = {
            index: _BackgroundPostJob(event, identity, "busy", "ctx", index + 10, 990.0)
            for index in range(1, 4)
        }
        plugin._background_post_queues["s-worker-budget"] = collections.deque(
            [
                _BackgroundPostJob(
                    event,
                    identity,
                    f"reply-{index}",
                    f"ctx-{index}",
                    index,
                    900.0,
                )
                for index in range(1, 40)
            ],
        )

        decision = plugin._background_post_adaptive_worker_decision(
            "s-worker-budget",
        )

        self.assertEqual(decision["global_worker_cap"], 6)
        self.assertEqual(decision["global_active_other_workers"], 6)
        self.assertEqual(decision["dispatch_workers"], 0)
        self.assertIn("global_worker_budget_exhausted", decision["reasons"])

    def test_background_post_workers_use_conservative_cap_when_environment_unknown(self):
        from main import _BackgroundPostJob

        plugin = new_plugin({"enable_dynamic_background_workers": True})
        self._bind_background_worker_environment(
            plugin,
            level="unknown",
            worker_cap=2,
            cpu=None,
            memory=None,
            now=1000.0,
        )
        event = FakeEvent("s-worker-unknown")
        identity = plugin._agent_identity(event)
        plugin._background_post_queues["s-worker-unknown"] = collections.deque(
            [
                _BackgroundPostJob(
                    event,
                    identity,
                    f"reply-{index}",
                    f"ctx-{index}",
                    index,
                    900.0,
                )
                for index in range(1, 40)
            ],
        )

        decision = plugin._background_post_adaptive_worker_decision(
            "s-worker-unknown",
        )

        self.assertEqual(decision["resource_pressure"]["level"], "unknown")
        self.assertEqual(decision["target_workers"], 2)
        self.assertLessEqual(decision["dispatch_workers"], 2)
        self.assertIn("environment_pressure_unknown", decision["reasons"])

    def test_internal_assessor_llm_concurrency_uses_separate_guard(self):
        from main import _BackgroundPostJob

        plugin = new_plugin({"enable_dynamic_background_workers": True})
        self._bind_background_worker_environment(plugin, now=1000.0)
        event = FakeEvent("s-llm-guard")
        identity = plugin._agent_identity(event)
        plugin._background_post_queues["s-llm-guard"] = collections.deque(
            [
                _BackgroundPostJob(
                    event,
                    identity,
                    f"reply-{index}",
                    f"ctx-{index}",
                    index,
                    time.time(),
                )
                for index in range(1, 6)
            ],
        )

        worker_decision = plugin._background_post_adaptive_worker_decision(
            "s-llm-guard",
        )
        llm_decision = plugin._internal_assessor_llm_concurrency_decision()

        self.assertEqual(worker_decision["queue_target_workers"], 3)
        self.assertLessEqual(worker_decision["desired_workers"], 2)
        self.assertEqual(llm_decision["limit"], 2)
        self.assertEqual(llm_decision["base_limit"], 2)
        self.assertEqual(llm_decision["burst_limit"], 3)
        self.assertIn("base_two_lane_guard", llm_decision["reasons"])

        plugin._background_post_queues["s-llm-guard"] = collections.deque(
            [
                _BackgroundPostJob(
                    event,
                    identity,
                    f"reply-{index}",
                    f"ctx-{index}",
                    index,
                    time.time(),
                )
                for index in range(1, 34)
            ],
        )

        worker_decision = plugin._background_post_adaptive_worker_decision(
            "s-llm-guard",
        )
        llm_decision = plugin._internal_assessor_llm_concurrency_decision()

        self.assertEqual(worker_decision["queue_target_workers"], 6)
        self.assertLessEqual(worker_decision["desired_workers"], 3)
        self.assertEqual(llm_decision["limit"], 3)
        self.assertIn("temporary_extreme_backlog_burst", llm_decision["reasons"])

    def test_internal_assessor_llm_guard_limits_provider_concurrency(self):
        plugin = new_plugin({"enable_dynamic_background_workers": True})
        active = 0
        max_active = 0

        async def fake_generate(**kwargs):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.01)
            active -= 1
            return SimpleNamespace(completion_text="{}")

        plugin.context.llm_generate = fake_generate

        async def run_calls():
            await asyncio.gather(
                *(
                    plugin._call_internal_assessor_llm(
                        provider_id="provider",
                        prompt=f"prompt-{index}",
                        system_prompt="system",
                    )
                    for index in range(8)
                ),
            )

        asyncio.run(run_calls())

        self.assertEqual(max_active, 2)
        self.assertEqual(plugin._internal_assessor_llm_inflight, 0)

    def test_background_post_commit_failure_retries_and_preserves_following_order(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "background_post_assessment": True,
                "background_post_queue_checkpoint_enabled": True,
                "enable_dynamic_background_workers": True,
                "background_post_retry_base_delay_seconds": 0.0,
                "background_post_retry_max_attempts": 3,
            },
        )
        saves, _ = self._bind_common_state_hooks(plugin)
        stored = {}
        save_attempts = []

        async def fake_put_kv(self, key, value):
            stored[key] = value

        async def fake_delete_kv(self, key):
            stored.pop(key, None)

        async def fake_save_state(self, session_key, state):
            save_attempts.append(state.label)
            if state.label == "reply-1" and save_attempts.count("reply-1") == 1:
                raise RuntimeError("commit failed")
            saves.append((session_key, state))

        bind_async(plugin, "put_kv_data", fake_put_kv)
        bind_async(plugin, "delete_kv_data", fake_delete_kv)
        bind_async(plugin, "_save_state", fake_save_state)

        async def label_assess(self, **kwargs):
            return fake_observation(kwargs["current_text"])

        bind_async(plugin, "_assess_emotion", label_assess)

        async def run_retry():
            for index in range(1, 4):
                plugin._last_request_text["s-commit-retry"] = f"ctx-{index}"
                await plugin.on_llm_response(
                    FakeEvent("s-commit-retry"),
                    SimpleNamespace(completion_text=f"reply-{index}"),
                )
            task = next(iter(plugin._background_tasks))
            await asyncio.wait_for(task, timeout=1.0)

        asyncio.run(run_retry())

        self.assertEqual(
            save_attempts,
            ["reply-1", "reply-1", "reply-2", "reply-3"],
        )
        self.assertEqual(
            [state.label for _, state in saves],
            ["reply-1", "reply-2", "reply-3"],
        )
        self.assertEqual(plugin._background_post_last_committed["s-commit-retry"], 3)
        self.assertEqual(plugin._background_post_queues, {})
        self.assertEqual(plugin._background_post_active, {})
        self.assertNotIn(
            plugin._background_post_checkpoint_kv_key("s-commit-retry"),
            stored,
        )

    def test_background_post_failure_dead_letters_after_retry_limit(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "background_post_assessment": True,
                "background_post_queue_checkpoint_enabled": True,
                "background_post_retry_base_delay_seconds": 0.0,
                "background_post_retry_max_attempts": 2,
            },
        )
        self._bind_common_state_hooks(plugin)

        async def fail_assess(self, **kwargs):
            raise RuntimeError("assessor down")

        bind_async(plugin, "_assess_emotion", fail_assess)

        async def run_dead_letter():
            plugin._last_request_text["s-dead"] = "secret ctx"
            await plugin.on_llm_response(
                FakeEvent("s-dead", message="secret user text"),
                SimpleNamespace(completion_text="secret reply"),
            )
            await asyncio.wait_for(next(iter(plugin._background_tasks)), timeout=1.0)
            return await plugin.get_agent_runtime_diagnostics("s-dead")

        diagnostics = asyncio.run(run_dead_letter())
        bg = diagnostics["background_post_assessment"]

        self.assertEqual(bg["dead_letter_count"], 1)
        self.assertEqual(bg["warning_level"], "error")
        self.assertIn("dead_letter", bg["warnings"])
        self.assertEqual(bg["dead_letters"][0]["sequence"], 1)
        self.assertEqual(bg["dead_letters"][0]["attempts"], 2)
        serialized = str(bg)
        self.assertNotIn("secret user text", serialized)
        self.assertNotIn("secret reply", serialized)
        self.assertNotIn("secret ctx", serialized)

    def test_background_post_checkpoint_v2_preserves_retry_and_dead_letter_metadata(self):
        plugin = new_plugin({"background_post_queue_checkpoint_enabled": True})
        stored = {}

        async def fake_put_kv(self, key, value):
            stored[key] = value

        async def fake_get_kv(self, key, default=None):
            return stored.get(key, default)

        bind_async(plugin, "put_kv_data", fake_put_kv)
        bind_async(plugin, "get_kv_data", fake_get_kv)
        event = FakeEvent("s-checkpoint-v2", message="user", sender_id="u1")
        identity = plugin._agent_identity(event)
        from main import _BackgroundPostJob

        retrying = _BackgroundPostJob(event, identity, "reply", "ctx", 1, 100.0)
        retrying.attempts = 1
        retrying.next_retry_at = 123.0
        retrying.last_error_type = "RuntimeError"
        retrying.last_error_message = "temporary"
        retrying.last_failed_at = 120.0
        dead = _BackgroundPostJob(event, identity, "dead reply", "dead ctx", 2, 101.0)
        dead.attempts = 3
        dead.last_error_type = "TimeoutError"
        dead.last_failed_at = 130.0
        dead.dead_lettered_at = 131.0
        plugin._background_post_queues["s-checkpoint-v2"] = collections.deque([retrying])
        plugin._background_post_dead_letters["s-checkpoint-v2"] = collections.deque([dead])
        plugin._background_post_sequence["s-checkpoint-v2"] = 2
        plugin._background_post_latest_enqueued["s-checkpoint-v2"] = 2

        async def save_and_recover():
            await plugin._save_background_post_checkpoint("s-checkpoint-v2")
            recovered = new_plugin({"background_post_queue_checkpoint_enabled": True})
            bind_async(recovered, "get_kv_data", fake_get_kv)
            await recovered._recover_background_post_queue("s-checkpoint-v2")
            return recovered

        recovered = asyncio.run(save_and_recover())
        recovered_job = recovered._background_post_queues["s-checkpoint-v2"][0]
        recovered_dead = recovered._background_post_dead_letters["s-checkpoint-v2"][0]

        self.assertEqual(recovered_job.sequence, 1)
        self.assertEqual(recovered_job.attempts, 1)
        self.assertEqual(recovered_job.next_retry_at, 123.0)
        self.assertEqual(recovered_job.last_error_type, "RuntimeError")
        self.assertIsNone(recovered_job.leased_at)
        self.assertIsNone(recovered_job.lease_until)
        self.assertEqual(recovered_dead.sequence, 2)
        self.assertEqual(recovered_dead.attempts, 3)
        self.assertEqual(recovered_dead.last_error_type, "TimeoutError")
        checkpoint = stored[plugin._background_post_checkpoint_kv_key("s-checkpoint-v2")]
        self.assertEqual(checkpoint["schema_version"], "astrbot.background_post_queue.v2")
        self.assertNotIn("response_text", checkpoint["dead_letters"][0])
        self.assertNotIn("request_context_text", checkpoint["dead_letters"][0])

    def test_sylanne_memory_state_uses_dedicated_kv_cache_and_delete(self):
        from memory_engine import MemoryRecord, SylanneMemoryState

        plugin = new_plugin()
        stored = {}

        async def fake_get_kv(self, key, default=None):
            return stored.get(key, default)

        async def fake_put_kv(self, key, value):
            stored[key] = value

        async def fake_delete_kv(self, key):
            stored.pop(key, None)

        bind_async(plugin, "get_kv_data", fake_get_kv)
        bind_async(plugin, "put_kv_data", fake_put_kv)
        bind_async(plugin, "delete_kv_data", fake_delete_kv)
        state = SylanneMemoryState.initial(now=10.0)
        state.records.append(
            MemoryRecord(
                text="用户刚才解释过，他们指插件的其他用户。",
                summary="他们指插件的其他用户。",
                session_key="room/with\\slash",
                created_at=10.0,
                updated_at=10.0,
                depth=0.84,
                confidence=0.75,
            ),
        )

        asyncio.run(plugin._save_sylanne_memory_state("room/with\\slash", state))
        saved_key = plugin._sylanne_memory_kv_key("room/with\\slash")

        self.assertEqual(saved_key, "sylanne_memory_state:room_with_slash")
        self.assertIn(saved_key, stored)
        plugin._sylanne_memory_cache.clear()
        loaded = asyncio.run(plugin._load_sylanne_memory_state("room/with\\slash"))
        self.assertEqual(loaded.records[0].summary, "他们指插件的其他用户。")
        self.assertEqual(plugin._sylanne_memory_cache["room/with\\slash"], loaded)

        asyncio.run(plugin._delete_sylanne_memory_state("room/with\\slash"))

        self.assertNotIn(saved_key, stored)
        self.assertNotIn("room/with\\slash", plugin._sylanne_memory_cache)

    def test_sylanne_memory_load_persists_real_time_forgetting(self):
        from memory_engine import MemoryRecord, SylanneMemoryState

        plugin = new_plugin()
        stored = {}

        async def fake_get_kv(self, key, default=None):
            return stored.get(key, default)

        async def fake_put_kv(self, key, value):
            stored[key] = value

        bind_async(plugin, "get_kv_data", fake_get_kv)
        bind_async(plugin, "put_kv_data", fake_put_kv)
        state = SylanneMemoryState.initial(now=0.0)
        state.dynamics.decay_half_life_seconds = 10.0
        state.records.append(
            MemoryRecord(
                text="一次很弱的临时噪声。",
                summary="临时噪声。",
                session_key="s-forget-kv",
                created_at=0.0,
                updated_at=0.0,
                depth=0.05,
                confidence=0.06,
                auto_parameters={"decay_half_life_seconds": 10.0},
            ),
        )
        stored[plugin._sylanne_memory_kv_key("s-forget-kv")] = state.to_dict()

        loaded = asyncio.run(
            plugin._load_sylanne_memory_state("s-forget-kv", now=120.0),
        )

        saved = stored[plugin._sylanne_memory_kv_key("s-forget-kv")]
        self.assertEqual(loaded.records, [])
        self.assertEqual(saved["records"], [])
        self.assertIn("forgotten=1", saved["dynamics"]["notes"])

    def test_background_post_recovery_merges_checkpoint_before_new_local_job(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "background_post_assessment": True,
                "background_post_queue_checkpoint_enabled": True,
            },
        )
        saves, _ = self._bind_common_state_hooks(plugin)
        stored = {}
        event = FakeEvent("s-merge-recover", message="old user", sender_id="u1")
        identity = plugin._agent_identity(event)
        from main import _BackgroundPostJob

        old_job = _BackgroundPostJob(event, identity, "reply-old", "ctx-old", 1, 100.0)
        stored[plugin._background_post_checkpoint_kv_key("s-merge-recover")] = {
            "schema_version": "astrbot.background_post_queue.v2",
            "session_key": "s-merge-recover",
            "latest_enqueued": 1,
            "last_committed": 0,
            "jobs": [plugin._background_post_job_to_dict(old_job)],
            "dead_letters": [],
        }

        async def fake_get_kv(self, key, default=None):
            return stored.get(key, default)

        async def fake_put_kv(self, key, value):
            stored[key] = value

        async def fake_delete_kv(self, key):
            stored.pop(key, None)

        async def label_assess(self, **kwargs):
            return fake_observation(kwargs["current_text"])

        bind_async(plugin, "get_kv_data", fake_get_kv)
        bind_async(plugin, "put_kv_data", fake_put_kv)
        bind_async(plugin, "delete_kv_data", fake_delete_kv)
        bind_async(plugin, "_assess_emotion", label_assess)

        async def run_merge():
            plugin._last_request_text["s-merge-recover"] = "ctx-new"
            await plugin.on_llm_response(
                FakeEvent("s-merge-recover", message="new user", sender_id="u1"),
                SimpleNamespace(completion_text="reply-new"),
            )
            await asyncio.wait_for(next(iter(plugin._background_tasks)), timeout=1.0)

        asyncio.run(run_merge())

        self.assertEqual(
            [state.label.rsplit("\n", 1)[-1] for key, state in saves if key == "s-merge-recover"],
            ["reply-old", "reply-new"],
        )
        self.assertEqual(plugin._background_post_last_committed["s-merge-recover"], 2)
        self.assertNotIn(
            plugin._background_post_checkpoint_kv_key("s-merge-recover"),
            stored,
        )

    def test_background_post_recovery_retries_after_transient_kv_failure(self):
        plugin = new_plugin({"background_post_queue_checkpoint_enabled": True})
        event = FakeEvent("s-recover-retry", sender_id="u1")
        identity = plugin._agent_identity(event)
        from main import _BackgroundPostJob

        old_job = _BackgroundPostJob(event, identity, "reply-old", "ctx-old", 1, 100.0)
        checkpoint = {
            "schema_version": "astrbot.background_post_queue.v2",
            "session_key": "s-recover-retry",
            "latest_enqueued": 1,
            "last_committed": 0,
            "jobs": [plugin._background_post_job_to_dict(old_job)],
            "dead_letters": [],
        }
        calls = 0

        async def flaky_get_kv(self, key, default=None):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("temporary kv failure")
            return checkpoint

        bind_async(plugin, "get_kv_data", flaky_get_kv)

        async def recover_twice():
            first = await plugin._recover_background_post_queue("s-recover-retry")
            second = await plugin._recover_background_post_queue("s-recover-retry")
            return first, second

        first, second = asyncio.run(recover_twice())

        self.assertFalse(first)
        self.assertTrue(second)
        self.assertEqual(calls, 2)
        self.assertEqual(
            [job.sequence for job in plugin._background_post_queues["s-recover-retry"]],
            [1],
        )

    def test_terminate_saves_final_background_post_checkpoint(self):
        plugin = new_plugin({"background_post_queue_checkpoint_enabled": True})
        stored = {}
        event = FakeEvent("s-terminate-final", sender_id="u1")
        identity = plugin._agent_identity(event)
        from main import _BackgroundPostJob

        plugin._background_post_recovered_sessions.add("s-terminate-final")
        plugin._background_post_queues["s-terminate-final"] = collections.deque(
            [
                _BackgroundPostJob(event, identity, "reply-final", "ctx-final", 1, 100.0),
            ],
        )
        plugin._background_post_sequence["s-terminate-final"] = 1
        plugin._background_post_latest_enqueued["s-terminate-final"] = 1

        async def fake_put_kv(self, key, value):
            stored[key] = value

        async def fake_delete_kv(self, key):
            stored.pop(key, None)

        bind_async(plugin, "put_kv_data", fake_put_kv)
        bind_async(plugin, "delete_kv_data", fake_delete_kv)

        asyncio.run(plugin.terminate())

        checkpoint = stored[plugin._background_post_checkpoint_kv_key("s-terminate-final")]
        self.assertEqual(checkpoint["schema_version"], "astrbot.background_post_queue.v2")
        self.assertEqual([item["sequence"] for item in checkpoint["jobs"]], [1])
        self.assertEqual(plugin._background_post_queues, {})

    def test_background_post_expired_lease_requeues_job_in_sequence_order(self):
        plugin = new_plugin({"background_post_job_lease_seconds": 1.0})
        event = FakeEvent("s-lease")
        identity = plugin._agent_identity(event)
        from main import _BackgroundPostJob

        active_one = _BackgroundPostJob(event, identity, "reply-1", "ctx-1", 1, 100.0)
        active_two = _BackgroundPostJob(event, identity, "reply-2", "ctx-2", 2, 101.0)
        for job in (active_one, active_two):
            job.leased_at = 100.0
            job.lease_until = 101.0
        plugin._background_post_active["s-lease"] = {1: active_one, 2: active_two}
        plugin._background_post_queues["s-lease"] = collections.deque()
        plugin.config["benchmark_enable_simulated_time"] = True
        plugin.config["benchmark_time_offset_seconds"] = 1000.0

        recovered_count = plugin._recover_expired_background_post_active("s-lease")

        self.assertEqual(recovered_count, 2)
        self.assertEqual(
            [job.sequence for job in plugin._background_post_queues["s-lease"]],
            [1, 2],
        )

    def test_state_injection_diff_mode_sends_small_no_change_fragment(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "state_injection_detail": "compact",
                "state_injection_compact_mode": "diff",
                "state_injection_diff_force_every_turns": 99,
            },
        )
        self._bind_common_state_hooks(plugin)

        first = fake_request(session_id="s-diff", prompt="hello")
        second = fake_request(session_id="s-diff", prompt="again")

        asyncio.run(plugin.on_llm_request(FakeEvent("s-diff"), first))
        plugin._consume_conversation_pending_response_epoch("s-diff")
        asyncio.run(plugin.on_llm_request(FakeEvent("s-diff"), second))

        first_text = first.extra_user_content_parts[0].text
        second_text = second.extra_user_content_parts[0].text
        self.assertIn('detail="compact"', first_text)
        self.assertIn('detail="diff"', second_text)
        self.assertIn("No material emotion-state change", second_text)
        self.assertLess(len(second_text), len(first_text))

    def test_background_post_queue_limit_drops_oldest_only_when_configured(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "background_post_assessment": True,
                "background_post_queue_limit": 2,
            },
        )
        saves, _ = self._bind_common_state_hooks(plugin)
        release_assessment = asyncio.Event()
        assessment_calls = []

        async def pausing_assess(self, **kwargs):
            assessment_calls.append(kwargs)
            if len(assessment_calls) == 1:
                await release_assessment.wait()
            return fake_observation(kwargs["current_text"])

        bind_async(plugin, "_assess_emotion", pausing_assess)

        async def run_limited_queue():
            plugin._last_request_text["s-queue-limit"] = "ctx-1"
            await plugin.on_llm_response(
                FakeEvent("s-queue-limit"),
                SimpleNamespace(completion_text="reply-1"),
            )
            while not assessment_calls:
                await asyncio.sleep(0)
            for index in range(2, 5):
                plugin._last_request_text["s-queue-limit"] = f"ctx-{index}"
                await plugin.on_llm_response(
                    FakeEvent("s-queue-limit"),
                    SimpleNamespace(completion_text=f"reply-{index}"),
                )
            self.assertEqual(len(plugin._background_post_queues["s-queue-limit"]), 2)
            release_assessment.set()
            await asyncio.wait_for(next(iter(plugin._background_tasks)), timeout=1.0)

        asyncio.run(run_limited_queue())

        self.assertEqual(
            [call["current_text"] for call in assessment_calls],
            ["reply-1", "reply-3", "reply-4"],
        )
        self.assertEqual(
            [state.label for _, state in saves],
            ["reply-1", "reply-3", "reply-4"],
        )

    def test_background_post_assessment_handles_large_burst_with_adaptive_workers(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "background_post_assessment": True,
                "enable_dynamic_background_workers": True,
                "background_post_queue_checkpoint_enabled": False,
            },
        )
        self._bind_background_worker_environment(plugin, now=1000.0)
        saves, _ = self._bind_common_state_hooks(plugin)
        active = 0
        max_active = 0
        assessment_calls = []

        async def tracked_assess(self, **kwargs):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            assessment_calls.append(kwargs["current_text"])
            await asyncio.sleep(0)
            active -= 1
            return fake_observation(kwargs["current_text"])

        bind_async(plugin, "_assess_emotion", tracked_assess)

        async def run_burst():
            for index in range(50):
                plugin._last_request_text["s-pressure"] = f"ctx-{index}"
                await plugin.on_llm_response(
                    FakeEvent("s-pressure"),
                    SimpleNamespace(completion_text=f"reply-{index:02d}"),
                )
            diagnostics = await plugin.get_agent_runtime_diagnostics("s-pressure")
            bg = diagnostics["background_post_assessment"]
            self.assertEqual(bg["worker_policy"], "adaptive_resource_guarded_pressure")
            self.assertGreaterEqual(bg["max_workers"], 1)
            self.assertLessEqual(
                bg["active_workers"],
                bg["worker_global_cap"],
            )
            await asyncio.wait_for(next(iter(plugin._background_tasks)), timeout=2.0)

        asyncio.run(run_burst())

        self.assertEqual(len(assessment_calls), 50)
        self.assertEqual(
            [state.label for _, state in saves],
            [f"reply-{index:02d}" for index in range(50)],
        )
        self.assertGreater(max_active, 1)
        self.assertLessEqual(max_active, 6)
        diagnostics = asyncio.run(plugin.get_agent_runtime_diagnostics("s-pressure"))
        bg = diagnostics["background_post_assessment"]
        self.assertEqual(bg["lag_count"], 0)
        self.assertEqual(bg["state_lag_count"], 0)
        self.assertEqual(bg["latest_enqueued"], 50)
        self.assertEqual(bg["last_committed"], 50)

    def test_background_post_checkpoint_recovers_uncommitted_queue(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "background_post_assessment": True,
                "background_post_queue_checkpoint_enabled": True,
            },
        )
        saves, _ = self._bind_common_state_hooks(plugin)
        stored = {}

        async def fake_put_kv(self, key, value):
            stored[key] = value

        async def fake_get_kv(self, key, default=None):
            return stored.get(key, default)

        async def fake_delete_kv(self, key):
            stored.pop(key, None)

        bind_async(plugin, "put_kv_data", fake_put_kv)
        bind_async(plugin, "get_kv_data", fake_get_kv)
        bind_async(plugin, "delete_kv_data", fake_delete_kv)
        event = FakeEvent(
            "s-recover",
            message="user message",
            sender_id="user-a",
            sender_name="Alice",
        )
        identity = plugin._agent_identity(event)
        from main import _BackgroundPostJob

        plugin._background_post_queues["s-recover"] = collections.deque(
            [
                _BackgroundPostJob(event, identity, "reply-1", "ctx-1", 1, 100.0),
                _BackgroundPostJob(event, identity, "reply-2", "ctx-2", 2, 101.0),
            ],
        )
        plugin._background_post_sequence["s-recover"] = 2
        plugin._background_post_latest_enqueued["s-recover"] = 2

        async def save_then_recover():
            await plugin._save_background_post_checkpoint("s-recover")
            recovered = new_plugin(
                {
                    "assessment_timing": "post",
                    "background_post_assessment": True,
                    "background_post_queue_checkpoint_enabled": True,
                },
            )
            assessment_calls = []
            self._bind_common_state_hooks(
                recovered,
                saves=saves,
                assessment_calls=assessment_calls,
            )

            async def label_assess(self, **kwargs):
                assessment_calls.append(kwargs)
                return fake_observation(kwargs["current_text"])

            bind_async(recovered, "_assess_emotion", label_assess)
            bind_async(recovered, "put_kv_data", fake_put_kv)
            bind_async(recovered, "get_kv_data", fake_get_kv)
            bind_async(recovered, "delete_kv_data", fake_delete_kv)
            await recovered._recover_background_post_queue("s-recover")
            self.assertEqual(len(recovered._background_post_queues["s-recover"]), 2)
            task = recovered._schedule_background_task(
                recovered._drain_background_post_assessments("s-recover"),
                label="recover-test",
            )
            recovered._background_post_tasks["s-recover"] = task
            await asyncio.wait_for(task, timeout=1.0)
            return recovered

        recovered = asyncio.run(save_then_recover())

        self.assertEqual(
            [state.label.rsplit("\n", 1)[-1] for _, state in saves],
            ["reply-1", "reply-1", "reply-2", "reply-2"],
        )
        self.assertEqual(recovered._background_post_last_committed["s-recover"], 2)
        self.assertNotIn(
            recovered._background_post_checkpoint_kv_key("s-recover"),
            stored,
        )

    def test_low_signal_light_assessment_skips_provider_lookup(self):
        from emotion_engine import EmotionState

        plugin = new_plugin({"enable_low_signal_light_assessment": True})

        async def fail_provider(self, event):
            raise AssertionError("low-signal text must not call provider lookup")

        bind_async(plugin, "_provider_id", fail_provider)

        observation = asyncio.run(
            plugin._assess_emotion(
                event=FakeEvent("s-low", message="嗯嗯"),
                phase="pre_response",
                previous_state=EmotionState.initial(),
                persona_profile=None,
                context_text="",
                current_text="嗯嗯",
            ),
        )

        self.assertEqual(observation.source, "low_signal")
        self.assertTrue(observation.appraisal["low_signal"])
        self.assertEqual(observation.appraisal["signal_kind"], "short_ack")
        self.assertLessEqual(observation.confidence, 0.28)

    def test_group_agent_tracks_conversation_and_speakers_separately(self):
        plugin = new_plugin({"assessment_timing": "pre", "inject_state": False})
        saves = []
        assessment_calls = []
        states = {}

        async def fake_persona(self, event, request):
            return None

        async def fake_load_state(self, session_key, persona_profile=None, **kwargs):
            from emotion_engine import EmotionState

            states.setdefault(session_key, EmotionState.initial())
            return states[session_key]

        async def fake_save_state(self, session_key, state):
            states[session_key] = state
            saves.append((session_key, state))

        async def fake_assess_emotion(self, **kwargs):
            assessment_calls.append(kwargs)
            return fake_observation(kwargs["event"].get_sender_id())

        bind_async(plugin, "_persona_profile", fake_persona)
        bind_async(plugin, "_load_state", fake_load_state)
        bind_async(plugin, "_save_state", fake_save_state)
        bind_async(plugin, "_assess_emotion", fake_assess_emotion)

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent("group-1", message="from A", sender_id="user-a"),
                fake_request(session_id="group-1", prompt="from A"),
            ),
        )
        asyncio.run(
            plugin.on_llm_request(
                FakeEvent("group-1", message="from B", sender_id="user-b"),
                fake_request(session_id="group-1", prompt="from B"),
            ),
        )

        saved_keys = [key for key, _ in saves]
        self.assertEqual(
            saved_keys,
            [
                "group-1",
                "group-1::speaker:user-a",
                "group-1",
                "group-1::speaker:user-b",
            ],
        )
        self.assertIn("[speaker:user-a]\nfrom A", assessment_calls[0]["current_text"])
        self.assertIn("[speaker:user-b]\nfrom B", assessment_calls[1]["current_text"])
        self.assertEqual(states["group-1"].turns, 2)
        self.assertEqual(states["group-1::speaker:user-a"].turns, 1)
        self.assertEqual(states["group-1::speaker:user-b"].turns, 1)

    def test_group_agent_injects_current_speaker_track(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": True,
                "agent_speaker_relationship_tracking": True,
            },
        )

        async def fake_persona(self, event, request):
            return None

        bind_async(plugin, "_persona_profile", fake_persona)
        request = fake_request(session_id="group-2", prompt="hello")

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "group-2",
                    message="hello",
                    sender_id="user-a",
                    sender_name="Alice",
                ),
                request,
            ),
        )

        injected_texts = [
            getattr(part, "text", "")
            for part in request.extra_user_content_parts
        ]
        self.assertTrue(
            any("<bot_emotion_speaker_track" in text for text in injected_texts),
        )
        self.assertTrue(
            any("Alice(user-a)" in text for text in injected_texts),
        )

    def test_group_atmosphere_updates_and_injects_compact_state_for_group_turn(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": True,
            },
        )
        group_saves = []

        async def fake_persona(self, event, request):
            return None

        async def fake_save_group(self, session_key, state):
            group_saves.append((session_key, state))
            self._group_atmosphere_memory_cache[session_key] = state

        bind_async(plugin, "_persona_profile", fake_persona)
        bind_async(plugin, "_save_group_atmosphere_state", fake_save_group)
        request = fake_request(session_id="group-room", prompt="@bot 哈哈 来看看")

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "group-room",
                    message="@bot 哈哈 来看看",
                    sender_id="user-a",
                    sender_name="Alice",
                ),
                request,
            ),
        )

        texts = [getattr(part, "text", "") for part in request.extra_user_content_parts]
        self.assertEqual(len(group_saves), 1)
        self.assertEqual(group_saves[0][0], "group-room")
        self.assertIn("group-room", plugin._agent_identity_profile_cache)
        self.assertIn("group-room::speaker:user-a", plugin._agent_identity_profile_cache)
        self.assertTrue(any('name="group_atmosphere"' in text for text in texts))
        joined = "\n".join(texts)
        self.assertNotIn("query_agent_state(", joined)
        self.assertNotIn("get_bot_group_atmosphere_state", joined)
        self.assertGreaterEqual(
            group_saves[0][1].values["bot_attention"],
            0.29,
        )

    def test_group_atmosphere_join_cooldown_persists_even_in_pre_timing(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
            },
        )
        saved = []

        async def fake_put_kv(self, key, value):
            saved.append((key, value))

        bind_async(plugin, "put_kv_data", fake_put_kv)

        asyncio.run(
            plugin.on_llm_response(
                FakeEvent("group-cooldown", sender_id="user-a", sender_name="Alice"),
                SimpleNamespace(completion_text="assistant joined"),
            ),
        )

        self.assertEqual(len(saved), 1)
        key, payload = saved[0]
        self.assertEqual(key, plugin._group_atmosphere_kv_key("group-cooldown"))
        self.assertEqual(payload["last_bot_join_turn"], 0)
        self.assertIsNotNone(payload["last_bot_join_at"])
        self.assertFalse(payload["cooldown"]["cooldown_active"])
        self.assertIn("join_cooldown_turns", payload["dynamics"])
        self.assertEqual(
            payload["cooldown"]["cooldown_remaining_turns"],
            int(round(payload["dynamics"]["join_cooldown_turns"])),
        )

    def test_group_atmosphere_diff_injection_sends_small_no_change_fragment(self):
        from group_atmosphere_engine import GroupAtmosphereState

        plugin = new_plugin(
            {
                "runtime_parameter_debug_override_enabled": True,
                "state_injection_compact_mode": "diff",
                "group_atmosphere_injection_diff_threshold": 0.08,
            },
        )
        state = GroupAtmosphereState.initial()

        first = plugin._build_group_atmosphere_injection_for_session(
            "group-diff",
            state,
        )
        second = plugin._build_group_atmosphere_injection_for_session(
            "group-diff",
            state,
        )

        self.assertIn("bot_group_atmosphere", first)
        self.assertIn('detail="diff"', second)
        self.assertIn("No material room-mood change", second)
        self.assertLess(len(second), len(first))

    def test_agent_identity_alias_drift_keeps_speaker_track_stable(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
            },
        )

        async def fake_persona(self, event, request):
            return None

        bind_async(plugin, "_persona_profile", fake_persona)

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "group-alias",
                    message="first name",
                    sender_id="user-a",
                    sender_name="Alice",
                ),
                fake_request(session_id="group-alias", prompt="first name"),
            ),
        )
        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "group-alias",
                    message="new name",
                    sender_id="user-a",
                    sender_name="Alicia",
                ),
                fake_request(session_id="group-alias", prompt="new name"),
            ),
        )

        profile = asyncio.run(
            plugin.get_agent_identity_profile(
                FakeEvent("group-alias", sender_id="user-a", sender_name="Alicia"),
            ),
        )
        self.assertEqual(profile["speaker_track_id"], "group-alias::speaker:user-a")
        self.assertEqual(profile["current_display_name"], "Alicia")
        self.assertEqual(
            [alias["name"] for alias in profile["aliases"]],
            ["Alice", "Alicia"],
        )

    def test_agent_identity_profile_prunes_stale_silent_speakers(self):
        plugin = new_plugin(
            {
                "agent_identity_profile_limit": 3,
                "agent_identity_ttl_seconds": 10.0,
            },
        )
        now = plugin._observed_now()
        plugin._agent_identity_profile_cache = {
            "group-prune": {
                "schema_version": "astrbot.agent_identity.v1",
                "conversation_id": "group-prune",
                "updated_at": now,
            },
            "group-prune::speaker:old": {
                "schema_version": "astrbot.agent_identity.v1",
                "conversation_id": "group-prune",
                "speaker_track_id": "group-prune::speaker:old",
                "updated_at": now - 99.0,
            },
            "group-prune::speaker:recent": {
                "schema_version": "astrbot.agent_identity.v1",
                "conversation_id": "group-prune",
                "speaker_track_id": "group-prune::speaker:recent",
                "updated_at": now - 1.0,
            },
        }

        profile = asyncio.run(
            plugin.get_agent_identity_profile(
                FakeEvent("group-prune", sender_id="new", sender_name="New"),
            ),
        )

        self.assertEqual(profile["speaker_track_id"], "group-prune::speaker:new")
        self.assertIn("group-prune", plugin._agent_identity_profile_cache)
        self.assertIn(
            "group-prune::speaker:new",
            plugin._agent_identity_profile_cache,
        )
        self.assertIn(
            "group-prune::speaker:recent",
            plugin._agent_identity_profile_cache,
        )
        self.assertNotIn(
            "group-prune::speaker:old",
            plugin._agent_identity_profile_cache,
        )

    def test_agent_causal_trail_records_sanitized_refs_not_raw_prompt(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
                "inject_state": False,
            },
        )
        self._bind_common_state_hooks(plugin)
        request = fake_request(
            session_id="group-trail",
            prompt="secret phrase should be excerpted only",
        )

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "group-trail",
                    message="secret phrase should be excerpted only",
                    sender_id="user-a",
                    sender_name="Alice",
                ),
                request,
            ),
        )

        trail = asyncio.run(
            plugin.get_agent_trail(
                FakeEvent("group-trail", sender_id="user-a", sender_name="Alice"),
                limit=10,
            ),
        )
        modules = [item["module"] for item in trail["items"]]
        self.assertIn("emotion", modules)
        self.assertIn("group_atmosphere", modules)
        for item in trail["items"]:
            self.assertIn("text_hash", item["input_ref"])
            self.assertIn("char_count", item["input_ref"])
            self.assertNotIn("input_text", item)

    def test_invalid_assessment_timing_falls_back_to_post(self):
        plugin = new_plugin({"assessment_timing": "bad-value"})
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        request = fake_request(session_id="s-bad", prompt="request text")
        response = SimpleNamespace(completion_text="assistant text")

        asyncio.run(plugin.on_llm_request(FakeEvent("s-bad"), request))

        async def run_response_and_drain():
            await plugin.on_llm_response(FakeEvent("s-bad"), response)
            await self._await_background_tasks(plugin)

        asyncio.run(run_response_and_drain())

        self.assertEqual(plugin._assessment_timing(), "post")
        self.assertEqual(len(saves), 1)
        self.assertEqual(
            [call["phase"] for call in assessment_calls],
            ["post_response"],
        )

    def test_on_llm_response_ignores_blank_completion(self):
        plugin = new_plugin({"assessment_timing": "both"})
        self._bind_common_state_hooks(plugin)

        async def fail_if_persona_loaded(self, *args, **kwargs):
            raise AssertionError("blank completion must not load persona state")

        async def fail_if_loaded(self, *args, **kwargs):
            raise AssertionError("blank completion must not load emotion state")

        async def fail_if_assessed(self, **kwargs):
            raise AssertionError("blank completion must not be assessed")

        async def fail_if_saved(self, session_key, state):
            raise AssertionError("blank completion must not be saved")

        bind_async(plugin, "_persona_profile", fail_if_persona_loaded)
        bind_async(plugin, "_load_state", fail_if_loaded)
        bind_async(plugin, "_assess_emotion", fail_if_assessed)
        bind_async(plugin, "_save_state", fail_if_saved)

        asyncio.run(
            plugin.on_llm_response(
                FakeEvent("s-blank"),
                SimpleNamespace(completion_text="   "),
            ),
        )

    def test_humanlike_enabled_with_zero_strength_updates_without_injection(self):
        from humanlike_engine import HumanlikeState

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_humanlike_state": True,
                "humanlike_injection_strength": 0.0,
            },
        )
        self._bind_common_state_hooks(plugin)
        humanlike_saves = []

        async def fake_load_humanlike_state(self, session_key, **kwargs):
            return HumanlikeState.initial()

        async def fake_save_humanlike_state(self, session_key, state):
            humanlike_saves.append((session_key, state))

        bind_async(plugin, "_load_humanlike_state", fake_load_humanlike_state)
        bind_async(plugin, "_save_humanlike_state", fake_save_humanlike_state)
        request = fake_request(session_id="s-humanlike", prompt="only you forever")

        asyncio.run(plugin.on_llm_request(FakeEvent("s-humanlike"), request))

        self.assertEqual(len(humanlike_saves), 1)
        self.assertEqual(humanlike_saves[0][0], "s-humanlike")
        self._find_text_part(request, "bot_emotion_state")
        self._assert_no_text_part_contains(request, "simulated humanlike-state")

    def test_lifelike_learning_enabled_with_zero_strength_updates_without_injection(self):
        from lifelike_learning_engine import LifelikeLearningState

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_lifelike_learning": True,
                "lifelike_learning_injection_strength": 0.0,
            },
        )
        self._bind_common_state_hooks(plugin)
        lifelike_saves = []

        async def fake_load_lifelike_state(self, session_key, **kwargs):
            return LifelikeLearningState.initial()

        async def fake_save_lifelike_state(self, session_key, state):
            lifelike_saves.append((session_key, state))

        bind_async(plugin, "_load_lifelike_learning_state", fake_load_lifelike_state)
        bind_async(plugin, "_save_lifelike_learning_state", fake_save_lifelike_state)
        request = fake_request(
            session_id="s-life",
            prompt="『桥隧猫』就是会熬夜改桥梁模型的人。",
        )

        asyncio.run(plugin.on_llm_request(FakeEvent("s-life"), request))

        self.assertEqual(len(lifelike_saves), 1)
        self.assertEqual(lifelike_saves[0][0], "s-life")
        self.assertIn("桥隧猫", lifelike_saves[0][1].lexicon)
        self._find_text_part(request, "bot_emotion_state")
        self._assert_no_text_part_contains(request, "lifelike common-ground")

    def test_lifelike_learning_injects_when_enabled_and_strength_positive(self):
        from lifelike_learning_engine import LifelikeLearningState

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_lifelike_learning": True,
                "lifelike_learning_injection_strength": 0.3,
            },
        )
        self._bind_common_state_hooks(plugin)

        async def fake_load_lifelike_state(self, session_key, **kwargs):
            return LifelikeLearningState.initial()

        async def fake_save_lifelike_state(self, session_key, state):
            pass

        bind_async(plugin, "_load_lifelike_learning_state", fake_load_lifelike_state)
        bind_async(plugin, "_save_lifelike_learning_state", fake_save_lifelike_state)
        request = fake_request(
            session_id="s-life-inject",
            prompt="我喜欢自然闲聊，桥隧猫就是会熬夜改模型的人。",
        )

        asyncio.run(plugin.on_llm_request(FakeEvent("s-life-inject"), request))

        self._find_text_part(request, "bot_emotion_state")
        auxiliary_text = self._find_text_part(
            request,
            'name="lifelike_learning"',
        )
        self.assertIn("bot_auxiliary_state", auxiliary_text)
        self.assertNotIn("query_agent_state(", auxiliary_text)

    def test_fallibility_enabled_with_zero_strength_updates_without_injection(self):
        from fallibility_engine import FallibilityState

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_fallibility_state": True,
                "fallibility_injection_strength": 0.0,
            },
        )
        self._bind_common_state_hooks(plugin)
        fallibility_saves = []

        async def fake_load_fallibility_state(self, session_key, **kwargs):
            return FallibilityState.initial()

        async def fake_save_fallibility_state(self, session_key, state):
            fallibility_saves.append((session_key, state))

        bind_async(plugin, "_load_fallibility_state", fake_load_fallibility_state)
        bind_async(plugin, "_save_fallibility_state", fake_save_fallibility_state)
        request = fake_request(
            session_id="s-fallibility",
            prompt="I may have misread that, sorry, I should correct it.",
        )

        asyncio.run(plugin.on_llm_request(FakeEvent("s-fallibility"), request))

        self.assertEqual(len(fallibility_saves), 1)
        self.assertEqual(fallibility_saves[0][0], "s-fallibility")
        self.assertIn("possible_mistake_cue", fallibility_saves[0][1].flags)
        self._find_text_part(request, "bot_emotion_state")
        self._assert_no_text_part_contains(request, "fallibility-state modulation")

    def test_fallibility_injects_when_enabled_and_strength_positive(self):
        from fallibility_engine import FallibilityState

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_fallibility_state": True,
                "fallibility_injection_strength": 0.3,
            },
        )
        self._bind_common_state_hooks(plugin)

        async def fake_load_fallibility_state(self, session_key, **kwargs):
            return FallibilityState.initial()

        async def fake_save_fallibility_state(self, session_key, state):
            pass

        bind_async(plugin, "_load_fallibility_state", fake_load_fallibility_state)
        bind_async(plugin, "_save_fallibility_state", fake_save_fallibility_state)
        request = fake_request(
            session_id="s-fallibility-inject",
            prompt="I may have misread that.",
        )

        asyncio.run(plugin.on_llm_request(FakeEvent("s-fallibility-inject"), request))

        self._find_text_part(request, "bot_emotion_state")
        auxiliary_text = self._find_text_part(
            request,
            'name="fallibility"',
        )
        self.assertIn("bot_auxiliary_state", auxiliary_text)
        self.assertNotIn("query_agent_state(", auxiliary_text)

    def test_auxiliary_state_injection_full_mode_keeps_legacy_fragments(self):
        from lifelike_learning_engine import LifelikeLearningState

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "runtime_parameter_debug_override_enabled": True,
                "enable_lifelike_learning": True,
                "lifelike_learning_injection_strength": 0.3,
                "auxiliary_state_injection_detail": "full",
            },
        )
        self._bind_common_state_hooks(plugin)

        async def fake_load_lifelike_state(self, session_key, **kwargs):
            return LifelikeLearningState.initial()

        async def fake_save_lifelike_state(self, session_key, state):
            pass

        bind_async(plugin, "_load_lifelike_learning_state", fake_load_lifelike_state)
        bind_async(plugin, "_save_lifelike_learning_state", fake_save_lifelike_state)
        request = fake_request(session_id="s-life-full", prompt="hello")

        asyncio.run(plugin.on_llm_request(FakeEvent("s-life-full"), request))

        text = self._find_text_part(request, "lifelike common-ground")
        self.assertNotIn("bot_auxiliary_state", text)

    def test_auxiliary_state_injection_off_skips_auxiliary_fragments(self):
        from lifelike_learning_engine import LifelikeLearningState

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "runtime_parameter_debug_override_enabled": True,
                "enable_lifelike_learning": True,
                "lifelike_learning_injection_strength": 0.3,
                "auxiliary_state_injection_detail": "off",
            },
        )
        self._bind_common_state_hooks(plugin)

        async def fake_load_lifelike_state(self, session_key, **kwargs):
            return LifelikeLearningState.initial()

        async def fake_save_lifelike_state(self, session_key, state):
            pass

        bind_async(plugin, "_load_lifelike_learning_state", fake_load_lifelike_state)
        bind_async(plugin, "_save_lifelike_learning_state", fake_save_lifelike_state)
        request = fake_request(session_id="s-life-off", prompt="hello")

        asyncio.run(plugin.on_llm_request(FakeEvent("s-life-off"), request))

        texts = self._request_text_parts(request)
        state_texts = [
            text
            for text in texts
            if text.startswith("<bot_") or "bot_auxiliary_state" in text
        ]
        self.assertEqual(len(state_texts), 1)
        self.assertIn("bot_emotion_state", state_texts[0])

    def test_on_llm_request_overlaps_auxiliary_state_loads(self):
        from humanlike_engine import HumanlikeState
        from lifelike_learning_engine import LifelikeLearningState
        from moral_repair_engine import MoralRepairState
        from fallibility_engine import FallibilityState

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_humanlike_state": True,
                "enable_lifelike_learning": True,
                "enable_moral_repair_state": True,
                "enable_fallibility_state": True,
                "humanlike_injection_strength": 0.0,
                "lifelike_learning_injection_strength": 0.0,
                "moral_repair_injection_strength": 0.0,
                "fallibility_injection_strength": 0.0,
            },
        )
        self._bind_common_state_hooks(plugin)
        saves = []

        async def slow_humanlike(self, session_key, **kwargs):
            await asyncio.sleep(0.05)
            return HumanlikeState.initial()

        async def slow_lifelike(self, session_key, **kwargs):
            await asyncio.sleep(0.05)
            return LifelikeLearningState.initial()

        async def slow_moral(self, session_key, **kwargs):
            await asyncio.sleep(0.05)
            return MoralRepairState.initial()

        async def slow_fallibility(self, session_key, **kwargs):
            await asyncio.sleep(0.05)
            return FallibilityState.initial()

        async def save_aux(self, session_key, state):
            saves.append((session_key, type(state).__name__))

        bind_async(plugin, "_load_humanlike_state", slow_humanlike)
        bind_async(plugin, "_load_lifelike_learning_state", slow_lifelike)
        bind_async(plugin, "_load_moral_repair_state", slow_moral)
        bind_async(plugin, "_load_fallibility_state", slow_fallibility)
        bind_async(plugin, "_save_humanlike_state", save_aux)
        bind_async(plugin, "_save_lifelike_learning_state", save_aux)
        bind_async(plugin, "_save_moral_repair_state", save_aux)
        bind_async(plugin, "_save_fallibility_state", save_aux)

        started = time.perf_counter()
        asyncio.run(
            plugin.on_llm_request(
                FakeEvent("s-aux-overlap"),
                fake_request(session_id="s-aux-overlap", prompt="sorry, 桥隧猫 means bridge tunnel friend"),
            ),
        )
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 0.16)
        self.assertEqual(
            [state_name for _, state_name in saves],
            [
                "HumanlikeState",
                "LifelikeLearningState",
                "MoralRepairState",
                "FallibilityState",
            ],
        )

    def test_personality_drift_enabled_uses_real_time_state_without_forcing_prompt(self):
        from personality_drift_engine import (
            PersonalityDriftEngine,
            PersonalityDriftParameters,
            PersonalityDriftState,
        )

        plugin = new_plugin(
            {
                "assessment_timing": "post",
            },
        )
        plugin.personality_drift_engine = PersonalityDriftEngine(
            PersonalityDriftParameters(event_threshold=0.01),
        )
        self._bind_common_state_hooks(plugin)
        drift_saves = []

        async def fake_load_personality_drift_state(
            self,
            session_key,
            profile=None,
            **kwargs,
        ):
            return PersonalityDriftState.initial(
                persona_fingerprint=profile.fingerprint if profile else "default",
                now=0.0,
            )

        async def fake_save_personality_drift_state(self, session_key, state):
            drift_saves.append((session_key, state))

        bind_async(plugin, "_load_personality_drift_state", fake_load_personality_drift_state)
        bind_async(plugin, "_save_personality_drift_state", fake_save_personality_drift_state)
        event_text = "thank you, I trust you, and I want us to keep learning together"
        request = fake_request(session_id="s-drift", prompt=event_text)

        asyncio.run(plugin.on_llm_request(FakeEvent("s-drift", message=event_text), request))

        self.assertGreaterEqual(len(drift_saves), 1)
        self.assertEqual(drift_saves[-1][0], "s-drift")
        self.assertGreaterEqual(drift_saves[-1][1].evidence_count, 1)
        self._find_text_part(request, "bot_emotion_state")
        self._assert_no_text_part_contains(request, "personality drift modulation")

    def test_personality_drift_ignores_replayed_request_context_as_new_event(self):
        from personality_drift_engine import PersonalityDriftState

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_personality_drift": True,
                "personality_drift_injection_strength": 0.0,
            },
        )
        self._bind_common_state_hooks(plugin)
        drift_saves = []

        async def fake_load_personality_drift_state(
            self,
            session_key,
            profile=None,
            **kwargs,
        ):
            return PersonalityDriftState.initial(
                persona_fingerprint=profile.fingerprint if profile else "default",
                now=0.0,
            )

        async def fake_save_personality_drift_state(self, session_key, state):
            drift_saves.append((session_key, state))

        bind_async(plugin, "_load_personality_drift_state", fake_load_personality_drift_state)
        bind_async(plugin, "_save_personality_drift_state", fake_save_personality_drift_state)
        request = fake_request(session_id="s-drift-context", prompt="普通新消息")
        request.contexts = [
            {
                "role": "user",
                "content": "谢谢你一直陪伴我，我信任你，也想一起继续学习。",
            },
        ]

        asyncio.run(plugin.on_llm_request(FakeEvent("s-drift-context"), request))

        self.assertEqual(drift_saves, [])

    def test_personality_drift_injects_when_enabled_and_strength_positive(self):
        from personality_drift_engine import PersonalityDriftState

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_personality_drift": True,
                "personality_drift_injection_strength": 0.22,
            },
        )
        self._bind_common_state_hooks(plugin)

        async def fake_load_personality_drift_state(
            self,
            session_key,
            profile=None,
            **kwargs,
        ):
            state = PersonalityDriftState.initial(
                persona_fingerprint=profile.fingerprint if profile else "default",
                now=0.0,
            )
            state.trait_offsets["interpersonal_warmth"] = 0.06
            state.values["drift_intensity"] = 0.2
            return state

        async def fake_save_personality_drift_state(self, session_key, state):
            pass

        bind_async(plugin, "_load_personality_drift_state", fake_load_personality_drift_state)
        bind_async(plugin, "_save_personality_drift_state", fake_save_personality_drift_state)
        request = fake_request(session_id="s-drift-inject", prompt="谢谢你，继续一起研究。")

        asyncio.run(plugin.on_llm_request(FakeEvent("s-drift-inject"), request))

        self._find_text_part(request, "bot_emotion_state")
        auxiliary_text = self._find_text_part(
            request,
            'name="personality_drift"',
        )
        self.assertIn("bot_auxiliary_state", auxiliary_text)
        self.assertNotIn("query_agent_state(", auxiliary_text)
        self._assert_no_text_part_contains(request, "personality drift modulation")

    def test_personality_drift_request_reuses_loaded_state_for_runtime_update_and_injection(self):
        from personality_drift_engine import PersonalityDriftState

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_personality_drift": True,
                "personality_drift_injection_strength": 0.22,
            },
        )
        self._bind_common_state_hooks(plugin)
        loads = []

        async def fake_load_personality_drift_state(
            self,
            session_key,
            profile=None,
            **kwargs,
        ):
            loads.append(session_key)
            state = PersonalityDriftState.initial(
                persona_fingerprint=profile.fingerprint if profile else "default",
                now=0.0,
            )
            state.trait_offsets["interpersonal_warmth"] = 0.04
            state.values["drift_intensity"] = 0.2
            return state

        async def fake_save_personality_drift_state(self, session_key, state):
            pass

        bind_async(plugin, "_load_personality_drift_state", fake_load_personality_drift_state)
        bind_async(plugin, "_save_personality_drift_state", fake_save_personality_drift_state)
        request = fake_request(session_id="s-drift-reuse", prompt="thank you")

        asyncio.run(plugin.on_llm_request(FakeEvent("s-drift-reuse"), request))

        self.assertEqual(loads, ["s-drift-reuse"])

    def test_realtime_chat_plan_splits_reply_and_bounds_delay(self):
        plugin = new_plugin(
            {
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_max_parts": 4,
                "realtime_chat_max_part_chars": 18,
                "realtime_chat_min_delay_seconds": 0.1,
                "realtime_chat_max_delay_seconds": 1.0,
                "enable_sticker_reaction": False,
            },
        )

        plan = asyncio.run(
            plugin.get_realtime_chat_plan(
                "s-realtime-plan",
                "那、那个……我先确认一下。这个地方可以拆开说！然后再慢慢收束。",
            ),
        )

        self.assertEqual(plan["kind"], "realtime_chat_plan")
        self.assertGreaterEqual(plan["message_count"], 2)
        runtime_limit = plan["settings"]["max_part_chars"]
        for part in plan["message_parts"]:
            self.assertLessEqual(len(part["text"]), runtime_limit)
            self.assertLessEqual(part["delay_before_seconds"], 1.0)
            self.assertGreaterEqual(part["delay_before_seconds"], 0.0)

    def test_realtime_chat_plan_keeps_long_tail_without_ellipsis(self):
        plugin = new_plugin(
            {
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_max_parts": 3,
                "realtime_chat_max_part_chars": 8,
                "enable_sticker_reaction": False,
            },
        )

        plan = asyncio.run(
            plugin.get_realtime_chat_plan(
                "s-realtime-tail",
                "第一句短。第二句短。第三句短。第四句短。第五句短。第六句短。第七句短。第八句短。第九句短。第十句短。",
            ),
        )

        self.assertEqual(plan["kind"], "realtime_chat_plan")
        self.assertGreater(plan["message_count"], 3)
        runtime_limit = plan["settings"]["max_part_chars"]
        for part in plan["message_parts"]:
            self.assertLessEqual(len(part["text"]), runtime_limit)
        self.assertNotIn("...", plan["message_parts"][-1]["text"])

    def test_realtime_chat_plan_keeps_explicit_line_break_fragments(self):
        plugin = new_plugin(
            {
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_max_parts": 8,
                "realtime_chat_max_part_chars": 80,
                "enable_sticker_reaction": False,
            },
        )

        plan = asyncio.run(
            plugin.get_realtime_chat_plan(
                "s-realtime-line-fragments",
                "第一段先说。\n第二段单独发。\n第三段也拆开。\n第四段继续拆。"
                "\n第五段保持碎片。"
            ),
        )

        parts = [part["text"] for part in plan["message_parts"]]
        self.assertGreaterEqual(plan["message_count"], 5)
        self.assertIn("第一段先说。", parts[0])
        self.assertIn("第二段单独发。", parts[1])
        self.assertIn("第三段也拆开。", parts[2])
        self.assertTrue(all("\n" not in part for part in parts))

    def test_realtime_dispatch_force_splits_oversized_parts_before_send(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin({"enable_sticker_reaction": False})
        plugin.context = FakeContext()
        long_text = (
            "one very long realtime message without any helpful newline or markdown "
            "that must be split by the plugin before it reaches the chat platform"
        )
        plan = {
            "session_key": "s-force-split",
            "settings": {"max_part_chars": 24, "min_part_chars": 3},
            "message_parts": [
                {"index": 0, "text": long_text, "delay_before_seconds": 0.0},
            ],
        }

        asyncio.run(
            plugin._send_realtime_chat_plan(
                FakeEvent("s-force-split"),
                plan,
                source="unit_test",
            ),
        )

        self.assertGreater(len(sent), 1)
        self.assertTrue(
            all(len(message.replace("message:", "")) <= 24 for _, message in sent),
        )

    def test_realtime_chat_runtime_settings_are_personality_adaptive(self):
        plugin = new_plugin(
            {
                "enable_sticker_reaction": False,
                "realtime_chat_max_parts": 1,
                "realtime_chat_max_part_chars": 999,
                "realtime_chat_chars_per_second": 1.0,
                "realtime_chat_min_delay_seconds": 9.0,
                "realtime_chat_max_delay_seconds": 9.0,
            },
        )

        async def fake_runtime_profile(self, *args, **kwargs):
            return SimpleNamespace(
                personality_model={
                    "derived_factors": {
                        "expressiveness": 0.92,
                        "social_distance": 0.08,
                        "boundary_sensitivity": 0.18,
                        "instability": 0.22,
                    },
                    "trait_scores": {
                        "interpersonal_warmth": 0.82,
                        "agreeableness": 0.74,
                    },
                },
            )

        bind_async(plugin, "_public_runtime_persona_profile", fake_runtime_profile)

        plan = asyncio.run(
            plugin.get_realtime_chat_plan(
                FakeEvent("s-adaptive-chat"),
                "第一句。第二句！第三句也想分开说。第四句慢慢收束。",
            ),
        )

        adaptive = plan["adaptive"]["realtime_chat"]
        self.assertFalse(adaptive["debug_override_used"])
        self.assertEqual(adaptive["source"], "personality_emotion_atmosphere")
        self.assertGreater(plan["message_count"], 1)
        self.assertNotEqual(plan["typing"]["chars_per_second"], 1.0)
        self.assertLess(plan["settings"]["max_part_chars"], 999)
        self.assertLess(plan["typing"]["min_delay_seconds"], 9.0)

    def test_lifelike_learning_records_user_speaking_style(self):
        from lifelike_learning_engine import LifelikeLearningState

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_lifelike_learning": True,
                "lifelike_learning_injection_strength": 0.0,
            },
        )
        self._bind_common_state_hooks(plugin)
        lifelike_saves = []

        async def fake_load_lifelike_state(self, session_key, **kwargs):
            return LifelikeLearningState.initial()

        async def fake_save_lifelike_state(self, session_key, state):
            lifelike_saves.append(state)

        bind_async(plugin, "_load_lifelike_learning_state", fake_load_lifelike_state)
        bind_async(plugin, "_save_lifelike_learning_state", fake_save_lifelike_state)

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent("s-speaking-style"),
                fake_request(
                    session_id="s-speaking-style",
                    prompt="嗯嗯。\n这个要拆开说！\n别写成长篇 markdown，短一点自然一点。",
                ),
            ),
        )

        style = lifelike_saves[-1].user_profile.speaking_style
        self.assertGreater(style["confidence"], 0.0)
        self.assertGreater(style["fragment_bias"], 0.3)
        self.assertGreater(style["short_turn_bias"], 0.1)

    def test_realtime_chat_adapts_split_strategy_to_user_speaking_style(self):
        from lifelike_learning_engine import LifelikeLearningState

        text = "第一句先说明问题。第二句补一点上下文。第三句再说处理方式。第四句慢慢收束。第五句留个余地。"

        async def fake_profile(self, *args, **kwargs):
            return None

        async def fake_emotion(self, *args, **kwargs):
            return {}

        async def fake_group(self, *args, **kwargs):
            return {}

        async def short_style_state(self, session_key, **kwargs):
            state = LifelikeLearningState.initial()
            state.user_profile.style_preferences = [
                "natural_conversational_style",
                "avoid_long_markdown_lists",
            ]
            state.user_profile.speaking_style = {
                "fragment_bias": 0.92,
                "short_turn_bias": 0.86,
                "formal_block_bias": 0.08,
                "typing_speed_bias": 0.48,
                "confidence": 0.95,
            }
            return state

        async def long_style_state(self, session_key, **kwargs):
            state = LifelikeLearningState.initial()
            state.user_profile.style_preferences = [
                "rigorous_engineering_detail_when_requested",
            ]
            state.user_profile.speaking_style = {
                "fragment_bias": 0.08,
                "short_turn_bias": 0.04,
                "formal_block_bias": 0.92,
                "typing_speed_bias": 0.68,
                "confidence": 0.95,
            }
            return state

        short_plugin = new_plugin({"enable_sticker_reaction": False})
        long_plugin = new_plugin({"enable_sticker_reaction": False})
        for plugin in (short_plugin, long_plugin):
            bind_async(plugin, "_public_runtime_persona_profile", fake_profile)
            bind_async(plugin, "get_emotion_values", fake_emotion)
            bind_async(plugin, "get_group_atmosphere_values", fake_group)
        bind_async(short_plugin, "_load_lifelike_learning_state", short_style_state)
        bind_async(long_plugin, "_load_lifelike_learning_state", long_style_state)

        short_plan = asyncio.run(short_plugin.get_realtime_chat_plan("s-short-style", text))
        long_plan = asyncio.run(long_plugin.get_realtime_chat_plan("s-long-style", text))

        short_adaptive = short_plan["adaptive"]["realtime_chat"]
        self.assertTrue(short_adaptive["user_style_adaptation"]["enabled"])
        self.assertLess(
            short_plan["settings"]["max_part_chars"],
            long_plan["settings"]["max_part_chars"],
        )
        self.assertGreaterEqual(
            short_plan["message_count"],
            long_plan["message_count"],
        )
        serialized = str(short_adaptive)
        self.assertNotIn("style_preferences", serialized)
        self.assertNotIn("speaking_style", serialized)

    def test_proactive_dispatch_policy_is_adaptive_not_fixed_config(self):
        plugin = new_plugin(
            {
                "proactive_speech_max_chars": 1,
                "proactive_speech_dispatch_ttl_seconds": 1,
                "proactive_speech_dispatch_cooldown_seconds": 1.0,
            },
        )
        decision = {
            "should_speak": True,
            "action": "speak_now",
            "score": 0.78,
            "signals": {
                "boundary": 0.18,
                "overload": 0.12,
                "repair_need": 0.08,
                "companionship_need": 0.66,
                "user_need_to_be_met": 0.52,
                "bot_need_to_express": 0.48,
            },
            "topic_judgement": {
                "should_speak": True,
                "need_mode": "mutual_need",
                "opening_style": "shared_context",
                "draft_message": "那、那个……我想确认一下，我们现在这样互相需要的节奏还舒服吗？",
                "topic_evidence": "mutual_need_balance 高",
            },
        }

        dispatch = plugin._build_proactive_dispatch_request(
            decision,
            event_or_session=FakeEvent("s-proactive-adaptive"),
            session_key="s-proactive-adaptive",
            candidate_context="",
        )

        self.assertIn("adaptive_policy", dispatch)
        self.assertFalse(dispatch["adaptive_policy"]["debug_override_used"])
        self.assertGreater(dispatch["max_chars"], 1)
        self.assertGreater(dispatch["ttl_seconds"], 1)
        self.assertGreater(dispatch["cooldown_seconds"], 1.0)

    def test_on_llm_request_registers_proactive_candidate_session(self):
        plugin = new_plugin({"assessment_timing": "post", "inject_state": False})
        request = fake_request(session_id="s-proactive-candidate", prompt="明天提醒我看实验。")

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "s-proactive-candidate",
                    message="明天提醒我看实验。",
                    sender_id="u-1",
                    sender_name="A.L",
                ),
                request,
            ),
        )

        candidate = plugin._proactive_candidate_sessions["s-proactive-candidate"]
        self.assertEqual(candidate["unified_msg_origin"], "s-proactive-candidate")
        self.assertIn("明天提醒我看实验", candidate["last_user_text_excerpt"])
        self.assertEqual(candidate["speaker_id"], "u-1")

    def test_proactive_scheduler_default_disabled_does_not_start(self):
        plugin = new_plugin({"assessment_timing": "post", "inject_state": False})

        async def fail_if_started(self):
            raise AssertionError("proactive scheduler should stay disabled by default")

        bind_async(plugin, "_proactive_scheduler_loop", fail_if_started)

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent("s-proactive-disabled", message="只是普通聊天。"),
                fake_request(session_id="s-proactive-disabled", prompt="只是普通聊天。"),
            ),
        )

        self.assertIsNone(plugin._proactive_scheduler_task)
        self.assertEqual(plugin._background_tasks, set())

    def test_proactive_scheduler_defaults_are_low_frequency(self):
        import main

        plugin = new_plugin({"enable_proactive_speech_scheduler": True})

        self.assertGreaterEqual(main.PROACTIVE_SCHEDULER_NORMAL_DELAY_SECONDS, 900.0)
        self.assertGreaterEqual(main.PROACTIVE_SCHEDULER_IDLE_DELAY_SECONDS, 1800.0)
        self.assertGreaterEqual(main.PROACTIVE_SCHEDULER_SESSION_RECHECK_SECONDS, 3600.0)
        self.assertEqual(main.PROACTIVE_SCHEDULER_MAX_CHECKS_PER_ROUND, 1)
        self.assertEqual(
            plugin._proactive_scheduler_next_delay({"checked": 0}),
            main.PROACTIVE_SCHEDULER_IDLE_DELAY_SECONDS,
        )
        self.assertEqual(
            plugin._proactive_scheduler_next_delay({"checked": 1}),
            main.PROACTIVE_SCHEDULER_NORMAL_DELAY_SECONDS,
        )

    def test_proactive_scheduler_dispatches_registered_session_when_enabled(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_proactive_speech_dispatch": True,
                "enable_proactive_speech_scheduler": True,
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_min_delay_seconds": 0.0,
                "realtime_chat_max_delay_seconds": 0.0,
                "enable_sticker_reaction": False,
            },
        )
        plugin._background_post_resource_pressure = lambda: {
            "level": "normal",
            "worker_cap": 6,
            "reason": "unit_test_normal_pressure",
        }
        dispatched = []

        async def fake_dispatch(self, event_or_session, **kwargs):
            dispatched.append(
                {
                    "event": event_or_session,
                    "candidate_context": kwargs.get("candidate_context", ""),
                    "dry_run": kwargs.get("dry_run"),
                },
            )
            return {
                "schema_version": "astrbot.proactive_dispatch_result.v1",
                "kind": "proactive_dispatch_result",
                "session_key": "s-proactive-run",
                "sent": True,
                "blocked_reason": "",
            }

        bind_async(plugin, "request_proactive_speech_dispatch", fake_dispatch)

        async def run_once():
            await plugin.on_llm_request(
                FakeEvent("s-proactive-run", message="这周项目进度有点卡。"),
                fake_request(session_id="s-proactive-run", prompt="这周项目进度有点卡。"),
            )
            result = await plugin._run_proactive_scheduler_once()
            await plugin.terminate()
            return result

        result = asyncio.run(run_once())

        self.assertEqual(result["checked"], 1)
        self.assertEqual(result["dispatched"], 1)
        self.assertEqual(dispatched[0]["event"].unified_msg_origin, "s-proactive-run")
        self.assertFalse(dispatched[0]["dry_run"])
        self.assertIn("最近用户消息", dispatched[0]["candidate_context"])

    def test_proactive_scheduler_context_uses_recent_window_not_only_last_message(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_proactive_speech_dispatch": True,
                "enable_proactive_speech_scheduler": True,
            },
        )
        plugin._background_post_resource_pressure = lambda: {
            "level": "normal",
            "worker_cap": 6,
            "reason": "unit_test_normal_pressure",
        }
        dispatched = []

        async def fake_dispatch(self, event_or_session, **kwargs):
            dispatched.append(kwargs.get("candidate_context", ""))
            return {
                "schema_version": "astrbot.proactive_dispatch_result.v1",
                "kind": "proactive_dispatch_result",
                "session_key": "s-proactive-window",
                "sent": True,
                "blocked_reason": "",
            }

        bind_async(plugin, "request_proactive_speech_dispatch", fake_dispatch)

        async def run_window():
            for text in (
                "这周桥隧交叉实验卡在传感器数据清洗。",
                "我明天要给导师汇报，但是有点没底。",
                "如果晚上我没动静，你可以轻轻提醒我整理图表。",
            ):
                await plugin.on_llm_request(
                    FakeEvent("s-proactive-window", message=text, sender_id="u1"),
                    fake_request(session_id="s-proactive-window", prompt=text),
                )
            return await plugin._run_proactive_scheduler_once()

        result = asyncio.run(run_window())

        self.assertEqual(result["checked"], 1)
        context = dispatched[0]
        self.assertIn("近期上下文摘要", context)
        self.assertIn("传感器数据清洗", context)
        self.assertIn("导师汇报", context)
        self.assertIn("整理图表", context)
        self.assertGreater(len(context), 160)

    def test_proactive_scheduler_context_can_include_sylanne_memory_summary(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_proactive_speech_dispatch": True,
                "enable_proactive_speech_scheduler": True,
            },
        )
        plugin._background_post_resource_pressure = lambda: {
            "level": "normal",
            "worker_cap": 6,
            "reason": "unit_test_normal_pressure",
        }
        from memory_engine import MemoryRecord, SylanneMemoryState

        class FakeLivingMemory:
            async def search_memory(self, session_key=None, query="", limit=3):
                raise AssertionError("proactive scheduler must use Sylanne memory")

        class FakeContext:
            def get_registered_star(self, name):
                if name == "astrbot_plugin_livingmemory":
                    return SimpleNamespace(activated=True, star_cls=FakeLivingMemory())
                return None

        plugin.context = FakeContext()
        plugin._observed_now = lambda: 20.0
        state = SylanneMemoryState.initial(now=0.0)
        state.records.extend(
            [
                MemoryRecord(
                    text="用户之前说过，今晚改论文图表时容易焦虑。",
                    summary="用户今晚改论文图表时容易焦虑。",
                    session_key="s-proactive-memory",
                    created_at=10.0,
                    updated_at=10.0,
                    depth=0.9,
                    confidence=0.82,
                ),
                MemoryRecord(
                    text="用户喜欢被轻轻提醒，而不是被命令。",
                    summary="用户喜欢被轻轻提醒，而不是被命令。",
                    session_key="s-proactive-memory",
                    created_at=11.0,
                    updated_at=11.0,
                    depth=0.86,
                    confidence=0.8,
                ),
            ],
        )
        plugin._sylanne_memory_cache["s-proactive-memory"] = state
        dispatched = []

        async def fake_dispatch(self, event_or_session, **kwargs):
            dispatched.append(kwargs.get("candidate_context", ""))
            return {
                "schema_version": "astrbot.proactive_dispatch_result.v1",
                "kind": "proactive_dispatch_result",
                "session_key": "s-proactive-memory",
                "sent": True,
                "blocked_reason": "",
            }

        bind_async(plugin, "request_proactive_speech_dispatch", fake_dispatch)

        async def run_memory_context():
            await plugin.on_llm_request(
                FakeEvent("s-proactive-memory", message="今晚我可能要继续改图。", sender_id="u1"),
                fake_request(session_id="s-proactive-memory", prompt="今晚我可能要继续改图。"),
            )
            return await plugin._run_proactive_scheduler_once()

        result = asyncio.run(run_memory_context())

        self.assertEqual(result["checked"], 1)
        context = dispatched[0]
        self.assertIn("Sylanne 自有记忆召回摘要", context)
        self.assertIn("论文图表", context)
        self.assertIn("轻轻提醒", context)

    def test_proactive_scheduler_context_includes_recent_request_context_excerpt(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_proactive_speech_dispatch": True,
                "enable_proactive_speech_scheduler": True,
            },
        )
        plugin._background_post_resource_pressure = lambda: {
            "level": "normal",
            "worker_cap": 6,
            "reason": "unit_test_normal_pressure",
        }
        dispatched = []

        async def fake_dispatch(self, event_or_session, **kwargs):
            dispatched.append(kwargs.get("candidate_context", ""))
            return {
                "schema_version": "astrbot.proactive_dispatch_result.v1",
                "kind": "proactive_dispatch_result",
                "session_key": "s-proactive-context-excerpt",
                "sent": True,
                "blocked_reason": "",
            }

        bind_async(plugin, "request_proactive_speech_dispatch", fake_dispatch)

        async def run_context_excerpt():
            request = fake_request(
                session_id="s-proactive-context-excerpt",
                prompt="那你有什么想对他们说的吗",
            )
            request.contexts = [
                {
                    "role": "user",
                    "content": "刚才说的他们，是插件的其他用户，不是恋爱关系里的其他人。",
                },
                {
                    "role": "assistant",
                    "content": "我理解了，是想对插件使用者说一点话。",
                },
            ]
            await plugin.on_llm_request(
                FakeEvent(
                    "s-proactive-context-excerpt",
                    message="那你有什么想对他们说的吗",
                    sender_id="u1",
                ),
                request,
            )
            return await plugin._run_proactive_scheduler_once()

        result = asyncio.run(run_context_excerpt())

        self.assertEqual(result["checked"], 1)
        context = dispatched[0]
        self.assertIn("近期上下文摘要", context)
        self.assertIn("最近请求上下文", context)
        self.assertIn("插件的其他用户", context)

    def test_proactive_scheduler_marks_unanswered_before_repeating_topic(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_proactive_speech_dispatch": True,
                "enable_proactive_speech_scheduler": True,
            },
        )
        plugin._background_post_resource_pressure = lambda: {
            "level": "normal",
            "worker_cap": 6,
            "reason": "unit_test_normal_pressure",
        }
        plugin._observed_now = lambda: 1_000_000.0
        session_key = "s-proactive-unanswered"
        plugin._proactive_candidate_sessions[session_key] = {
            "schema_version": "astrbot.proactive_candidate_session.v1",
            "session_key": session_key,
            "unified_msg_origin": session_key,
            "last_seen_at": 999_000.0,
            "last_user_text_excerpt": "咖啡啊",
            "candidate_context_excerpt": "用户刚才说喝了咖啡反而想睡，话题已经被主动发言追问过。",
            "speaker_id": "u1",
            "speaker_name": "哀洛芙",
        }
        plugin._proactive_dispatch_audit = {
            session_key: collections.deque(
                [
                    {
                        "sent": True,
                        "sent_at": 999_100.0,
                        "feedback_status": "pending",
                        "feedback_window_seconds": 60.0,
                        "need_mode": "progress_check",
                        "topic_text": "咖啡反而变困",
                        "topic_evidence": "上一次用户聊到咖啡",
                    },
                ],
                maxlen=24,
            ),
        }
        dispatched = []
        lifelike_observations = []
        emotion_observations = []

        async def fake_dispatch(self, event_or_session, **kwargs):
            dispatched.append(kwargs.get("candidate_context", ""))
            return {
                "schema_version": "astrbot.proactive_dispatch_result.v1",
                "kind": "proactive_dispatch_result",
                "session_key": session_key,
                "sent": False,
                "blocked_reason": "unit_test",
            }

        async def fake_observe_lifelike_text(self, event_or_session=None, text="", **kwargs):
            lifelike_observations.append({"text": text, **kwargs})
            return {"ok": True}

        async def fake_observe_emotion_text(self, event_or_session=None, text="", **kwargs):
            emotion_observations.append({"text": text, **kwargs})
            return {"ok": True}

        bind_async(plugin, "request_proactive_speech_dispatch", fake_dispatch)
        bind_async(plugin, "observe_lifelike_text", fake_observe_lifelike_text)
        bind_async(plugin, "observe_emotion_text", fake_observe_emotion_text)

        result = asyncio.run(plugin._run_proactive_scheduler_once())

        self.assertEqual(result["checked"], 1)
        audit = plugin._proactive_dispatch_audit[session_key][-1]
        self.assertEqual(audit["feedback_status"], "unanswered")
        self.assertEqual(lifelike_observations[0]["source"], "proactive_feedback")
        self.assertEqual(emotion_observations[0]["source"], "proactive_unanswered_feedback")
        self.assertFalse(emotion_observations[0]["use_llm"])
        context = dispatched[0]
        self.assertIn("上一条主动发言没有得到回应", context)
        self.assertIn("咖啡反而变困", context)
        self.assertIn("不要重复同一个话题", context)
        self.assertIn("可能是在忙、休息或暂时不方便聊天", context)
        self.assertIn("如果只是想念用户", context)

    def test_proactive_scheduler_settles_unanswered_even_when_recheck_skips_session(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_proactive_speech_dispatch": True,
                "enable_proactive_speech_scheduler": True,
            },
        )
        plugin._background_post_resource_pressure = lambda: {
            "level": "normal",
            "worker_cap": 6,
            "reason": "unit_test_normal_pressure",
        }
        plugin._observed_now = lambda: 1_000_000.0
        session_key = "s-proactive-recheck-unanswered"
        plugin._proactive_candidate_sessions[session_key] = {
            "schema_version": "astrbot.proactive_candidate_session.v1",
            "session_key": session_key,
            "unified_msg_origin": session_key,
            "last_seen_at": 999_000.0,
            "last_user_text_excerpt": "coffee",
            "speaker_id": "u1",
        }
        plugin._proactive_scheduler_last_checked[session_key] = 999_999.0
        plugin._proactive_dispatch_audit = {
            session_key: collections.deque(
                [
                    {
                        "sent": True,
                        "sent_at": 999_100.0,
                        "feedback_status": "pending",
                        "feedback_window_seconds": 60.0,
                        "need_mode": "progress_check",
                        "topic_text": "coffee sleepy",
                    },
                ],
                maxlen=24,
            ),
        }
        lifelike_observations = []
        emotion_observations = []

        async def fake_observe_lifelike_text(self, event_or_session=None, text="", **kwargs):
            lifelike_observations.append({"text": text, **kwargs})
            return {"ok": True}

        async def fake_observe_emotion_text(self, event_or_session=None, text="", **kwargs):
            emotion_observations.append({"text": text, **kwargs})
            return {"ok": True}

        bind_async(plugin, "observe_lifelike_text", fake_observe_lifelike_text)
        bind_async(plugin, "observe_emotion_text", fake_observe_emotion_text)

        result = asyncio.run(plugin._run_proactive_scheduler_once())

        self.assertEqual(result["checked"], 0)
        audit = plugin._proactive_dispatch_audit[session_key][-1]
        self.assertEqual(audit["feedback_status"], "unanswered")
        self.assertEqual(lifelike_observations[0]["source"], "proactive_feedback")
        self.assertEqual(emotion_observations[0]["source"], "proactive_unanswered_feedback")

    def test_on_llm_request_can_include_sylanne_memory_summary(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
                "realtime_input_completion_probe_delay_seconds": 0.0,
                "realtime_input_completion_max_wait_seconds": 0.3,
            },
        )
        self._bind_common_state_hooks(plugin)
        from memory_engine import MemoryRecord, SylanneMemoryState

        calls = []

        class FakeLivingMemory:
            async def search_memory(self, session_key=None, query="", limit=3):
                calls.append({"session_key": session_key, "query": query, "limit": limit})
                raise AssertionError("on_llm_request must not call LivingMemory")

        class FakeContext:
            def get_registered_star(self, name):
                if name == "astrbot_plugin_livingmemory":
                    return SimpleNamespace(activated=True, star_cls=FakeLivingMemory())
                return None

        plugin.context = FakeContext()
        state = SylanneMemoryState.initial(now=0.0)
        state.records.extend(
            [
                MemoryRecord(
                    text="用户刚才解释过，“他们”指插件的其他用户。",
                    summary="用户刚才解释过，“他们”指插件的其他用户。",
                    session_key="s-request-memory",
                    created_at=10.0,
                    updated_at=10.0,
                    depth=0.9,
                    confidence=0.84,
                ),
                MemoryRecord(
                    text="用户希望 bot 回答时不要把插件用户误会成恋爱对象。",
                    summary="用户希望 bot 回答时不要把插件用户误会成恋爱对象。",
                    session_key="s-request-memory",
                    created_at=11.0,
                    updated_at=11.0,
                    depth=0.88,
                    confidence=0.81,
                ),
            ],
        )
        plugin._sylanne_memory_cache["s-request-memory"] = state
        request = fake_request(
            session_id="s-request-memory",
            prompt="那你有什么想对他们说的吗",
        )
        request.contexts = [
            {
                "role": "user",
                "content": "不是啊，我是说插件的其他用户。",
            },
        ]

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "s-request-memory",
                    message="那你有什么想对他们说的吗",
                    sender_id="u1",
                ),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertEqual(calls, [])
        self.assertIn("sylanne_memory_recall", injected)
        self.assertIn("用户刚才解释过", injected)
        self.assertIn("不要把插件用户误会成恋爱对象", injected)

    def test_on_llm_request_can_use_configured_embedding_provider_for_memory_recall(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
                "sylanne_memory_vector_retrieval_enabled": True,
                "sylanne_memory_embedding_provider_id": "embed-a",
            },
        )
        self._bind_common_state_hooks(plugin)
        from memory_engine import MemoryRecord, SylanneMemoryState

        class FakeEmbeddingProvider:
            provider_config = {"id": "embed-a", "provider_type": "embedding"}

            async def get_embedding(self, text):
                if "needle-query" in text or "alpha beta gamma" in text:
                    return [1.0, 0.0, 0.0]
                return [0.0, 1.0, 0.0]

            async def get_embeddings(self, texts):
                return [await self.get_embedding(text) for text in texts]

            def get_dim(self):
                return 3

        provider = FakeEmbeddingProvider()

        class FakeContext:
            def get_provider_by_id(self, provider_id):
                return provider if provider_id == "embed-a" else None

            def get_all_embedding_providers(self):
                return [provider]

        plugin.context = FakeContext()
        state = SylanneMemoryState.initial(now=0.0)
        state.records.extend(
            [
                MemoryRecord(
                    memory_id="dense-hit",
                    text="alpha beta gamma",
                    summary="alpha beta gamma",
                    session_key="s-vector-request",
                    created_at=10.0,
                    updated_at=10.0,
                    depth=0.52,
                    confidence=0.64,
                ),
                MemoryRecord(
                    memory_id="dense-miss",
                    text="delta epsilon zeta",
                    summary="delta epsilon zeta",
                    session_key="s-vector-request",
                    created_at=11.0,
                    updated_at=11.0,
                    depth=0.92,
                    confidence=0.90,
                ),
            ],
        )
        plugin._sylanne_memory_cache["s-vector-request"] = state
        saved = []

        async def fake_save_memory(self, session_key, saved_state):
            saved.append(saved_state.to_dict())
            self._sylanne_memory_cache[session_key] = saved_state

        bind_async(plugin, "_save_sylanne_memory_state", fake_save_memory)
        request = fake_request(
            session_id="s-vector-request",
            prompt="needle-query",
        )

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "s-vector-request",
                    message="needle-query",
                    sender_id="u1",
                ),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertIn("sylanne_memory_recall", injected)
        self.assertIn("alpha beta gamma", injected)
        self.assertNotIn("delta epsilon zeta", injected)
        self.assertTrue(saved)
        saved_records = saved[-1]["records"]
        self.assertTrue(any(record["semantic_embedding"] for record in saved_records))
        self.assertTrue(
            all(record["embedding_provider_id"] == "embed-a" for record in saved_records),
        )

    def test_on_llm_request_reinforces_recalled_sylanne_memory(self):
        from memory_engine import MemoryRecord, SylanneMemoryState

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
            },
        )
        self._bind_common_state_hooks(plugin)
        plugin._observed_now = lambda: 20.0
        state = SylanneMemoryState.initial(now=0.0)
        state.records.append(
            MemoryRecord(
                text="用户说过插件文档页不要显示旧版本。",
                summary="插件文档页不要显示旧版本。",
                session_key="s-reinforce-request",
                speaker_id="u1",
                created_at=10.0,
                updated_at=10.0,
                depth=0.42,
                confidence=0.44,
                layers={"semantic": 0.8},
            ),
        )
        plugin._sylanne_memory_cache["s-reinforce-request"] = state
        saved = []

        async def fake_save_memory(self, session_key, saved_state):
            saved.append((session_key, saved_state.to_dict()))
            self._sylanne_memory_cache[session_key] = saved_state

        bind_async(plugin, "_save_sylanne_memory_state", fake_save_memory)
        request = fake_request(
            session_id="s-reinforce-request",
            prompt="为什么插件文档页还是旧版本",
        )

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "s-reinforce-request",
                    message="为什么插件文档页还是旧版本",
                    sender_id="u1",
                ),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertIn("sylanne_memory_recall", injected)
        self.assertEqual(saved[-1][0], "s-reinforce-request")
        saved_record = saved[-1][1]["records"][0]
        self.assertEqual(saved_record["recall_count"], 1)
        self.assertGreater(saved_record["depth"], 0.42)

    def test_on_llm_request_can_include_associated_sylanne_memory(self):
        from memory_engine import MemoryRecord, SylanneMemoryState

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
            },
        )
        self._bind_common_state_hooks(plugin)
        state = SylanneMemoryState.initial(now=0.0)
        state.dynamics.recall_limit = 1
        state.dynamics.associative_recall_limit = 1
        state.records.extend(
            [
                MemoryRecord(
                    memory_id="core-them",
                    text="用户解释过：他们指插件的其他用户，不是恋爱对象。",
                    summary="他们指插件的其他用户。",
                    session_key="s-associated-request",
                    created_at=10.0,
                    updated_at=10.0,
                    depth=0.91,
                    confidence=0.84,
                    associations={"tone-soft": 0.88},
                ),
                MemoryRecord(
                    memory_id="tone-soft",
                    text="用户希望 Sylanne 对插件使用者说话时温和一点，别像炫耀。",
                    summary="对插件使用者说话要温和，别炫耀。",
                    session_key="s-associated-request",
                    created_at=11.0,
                    updated_at=11.0,
                    depth=0.74,
                    confidence=0.70,
                ),
            ],
        )
        plugin._sylanne_memory_cache["s-associated-request"] = state
        request = fake_request(
            session_id="s-associated-request",
            prompt="那你想对他们说什么",
        )

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "s-associated-request",
                    message="那你想对他们说什么",
                    sender_id="u1",
                ),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertIn("sylanne_memory_recall", injected)
        self.assertIn("他们指插件的其他用户", injected)
        self.assertIn("对插件使用者说话要温和", injected)
        self.assertLessEqual(len(injected), 1800)

    def test_on_llm_request_does_not_call_external_livingmemory(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
            },
        )
        self._bind_common_state_hooks(plugin)
        calls = []

        class FakeLivingMemory:
            async def search_memory(self, session_key=None, query="", limit=3):
                calls.append({"session_key": session_key, "query": query, "limit": limit})
                return [{"text": "should not be injected by default"}]

        class FakeContext:
            def get_registered_star(self, name):
                if name == "astrbot_plugin_livingmemory":
                    return SimpleNamespace(activated=True, star_cls=FakeLivingMemory())
                return None

        plugin.context = FakeContext()
        request = fake_request(session_id="s-request-memory-default-off", prompt="他们呢")

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent("s-request-memory-default-off", message="他们呢", sender_id="u1"),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertEqual(calls, [])
        self.assertNotIn("sylanne_memory_recall", injected)

    def test_on_llm_request_sylanne_memory_recall_failure_silently_degrades(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
            },
        )
        self._bind_common_state_hooks(plugin)

        async def broken_load_memory(self, session_key, *, now=None):
            raise RuntimeError("sylanne memory unavailable")

        bind_async(plugin, "_load_sylanne_memory_state", broken_load_memory)
        request = fake_request(session_id="s-request-memory-fail", prompt="他们呢")

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent("s-request-memory-fail", message="他们呢", sender_id="u1"),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertNotIn("sylanne_memory_recall", injected)

    def test_sylanne_memory_recall_query_excludes_existing_recall_parts(self):
        plugin = new_plugin()
        request = fake_request(session_id="s-memory-query", prompt="current prompt")
        request.contexts = [
            {"role": "user", "content": "recent user context"},
        ]
        request.extra_user_content_parts.extend(
            [
                SimpleNamespace(
                    text="[sylanne_memory_recall]\nold recalled memory must not become a query",
                ),
                SimpleNamespace(text="new temporary context can join query"),
            ],
        )

        query = plugin._sylanne_memory_recall_query_for_request(
            request,
            current_user_text="current prompt",
        )

        self.assertIn("new temporary context", query)
        self.assertNotIn("old recalled memory", query)
        self.assertNotIn("sylanne_memory_recall", query)

    def test_context_compression_summary_is_used_for_memory_query(self):
        plugin = new_plugin()
        request = fake_request(
            session_id="s-compressed-memory-query",
            prompt="what should I tell them now?",
        )
        request.contexts = [
            {
                "role": "system",
                "content": (
                    "AstrBot 自动压缩上下文摘要：用户刚才说明 them 指插件的其他使用者；"
                    "助手已经道歉并准备给插件使用者留一句话。"
                ),
            },
        ]

        query = plugin._sylanne_memory_recall_query_for_request(
            request,
            current_user_text="what should I tell them now?",
        )

        self.assertIn("自动压缩上下文摘要", query)
        self.assertIn("插件的其他使用者", query)
        self.assertIn("what should I tell them now?", query)

    def test_context_compression_summary_strips_sylanne_internal_blocks(self):
        plugin = new_plugin()
        request = fake_request(
            session_id="s-compressed-internal-strip",
            prompt="continue",
        )
        request.contexts = [
            {
                "role": "system",
                "content": (
                    "自动压缩上下文摘要：用户问的是插件使用者。\n"
                    "[sylanne_memory_recall]\n"
                    "old internal recall must not re-enter query\n"
                    "[sylanne_realtime_assistant_history]\n"
                    "old realtime shadow must not re-enter query\n"
                    "摘要结束。"
                ),
            },
        ]

        query = plugin._sylanne_memory_recall_query_for_request(
            request,
            current_user_text="continue",
        )

        self.assertIn("插件使用者", query)
        self.assertNotIn("old internal recall", query)
        self.assertNotIn("old realtime shadow", query)
        self.assertNotIn("sylanne_memory_recall", query)
        self.assertNotIn("sylanne_realtime_assistant_history", query)

    def test_context_compression_summary_strips_inline_sylanne_markers(self):
        plugin = new_plugin()
        request = fake_request(
            session_id="s-compressed-inline-strip",
            prompt="continue",
        )
        request.contexts = [
            {
                "role": "system",
                "content": (
                    "自动压缩上下文摘要：用户问的是插件使用者。"
                    "[sylanne_memory_recall] old inline recall must not re-enter query。"
                ),
            },
        ]

        query = plugin._sylanne_memory_recall_query_for_request(
            request,
            current_user_text="continue",
        )

        self.assertIn("插件使用者", query)
        self.assertNotIn("old inline recall", query)
        self.assertNotIn("sylanne_memory_recall", query)

    def test_context_compression_summary_prevents_duplicate_realtime_shadow(self):
        plugin = new_plugin({"enable_realtime_chat": True, "enable_sticker_reaction": False})
        plugin._record_realtime_assistant_history_shadow(
            "s-compressed-shadow",
            full_text="assistant already summarized by official compression",
            input_epoch=1,
            message_parts=[{"text": "assistant already summarized by official compression"}],
            source="unit_test",
        )
        request = fake_request(
            session_id="s-compressed-shadow",
            prompt="continue from that",
        )
        request.contexts = [
            {
                "role": "system",
                "content": (
                    "官方自动压缩上下文摘要：上一轮助手已经说过 "
                    "assistant already summarized by official compression。"
                    "[sylanne_realtime_assistant_history]"
                ),
            },
        ]

        appended = plugin._append_realtime_assistant_history_shadow_if_any(
            request,
            "s-compressed-shadow",
            budget=None,
            current_user_text="continue from that",
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertFalse(appended)
        self.assertNotIn("sylanne_realtime_assistant_history", injected)
        queue = plugin._realtime_assistant_history_shadow_cache()["s-compressed-shadow"]
        self.assertTrue(queue[-1]["consumed"])
        self.assertEqual(queue[-1]["consumed_reason"], "official_context_compression_summary")

    def test_short_answer_anchors_to_previous_realtime_choice_question(self):
        plugin = new_plugin({"enable_realtime_chat": True, "enable_sticker_reaction": False})
        plugin._record_realtime_assistant_history_shadow(
            "s-choice-anchor",
            full_text="你是用 IP 直连的，还是域名呀？",
            input_epoch=1,
            message_parts=[{"text": "你是用 IP 直连的，还是域名呀？"}],
            source="unit_test",
        )
        request = fake_request(session_id="s-choice-anchor", prompt="IP")

        appended = plugin._append_realtime_continuity_context_if_any(
            request,
            "s-choice-anchor",
            budget=None,
            current_user_text="IP",
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertTrue(appended)
        self.assertIn("sylanne_realtime_pending_bot_question", injected)
        self.assertIn("上一轮 bot 刚提出了一个未闭合问题", injected)
        self.assertIn("你是用 IP 直连的，还是域名呀？", injected)
        self.assertIn("current_user_short_answer=IP", injected)

    def test_on_llm_request_keeps_short_answer_context_for_previous_bot_question(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
                "realtime_input_completion_probe_delay_seconds": 0.0,
                "realtime_input_completion_max_wait_seconds": 0.0,
            },
        )
        self._bind_common_state_hooks(plugin)
        plugin._record_realtime_assistant_history_shadow(
            "s-choice-request",
            full_text="你是用 IP 直连的，还是域名呀？",
            input_epoch=1,
            message_parts=[{"text": "你是用 IP 直连的，还是域名呀？"}],
            source="unit_test",
        )
        request = fake_request(session_id="s-choice-request", prompt="IP")

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent("s-choice-request", message="IP", sender_id="u1"),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertIn("sylanne_realtime_pending_bot_question", injected)
        self.assertIn("current_user_short_answer=IP", injected)
        self.assertIn("你是用 IP 直连的，还是域名呀？", injected)

    def test_short_answer_context_keeps_question_cluster_for_split_reply(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
                "realtime_input_completion_probe_delay_seconds": 0.0,
                "realtime_input_completion_max_wait_seconds": 0.0,
            },
        )
        self._bind_common_state_hooks(plugin)
        plugin._record_realtime_assistant_history_shadow(
            "s-question-cluster",
            full_text=(
                "喝了杯什么呀？这么神奇，一喝就困？"
                "☕️ 可别告诉我你又是那种熬到天亮才去补觉的夜猫子模式。"
            ),
            input_epoch=1,
            message_parts=[
                {"text": "喝了杯什么呀？"},
                {"text": "这么神奇，"},
                {"text": "一喝就困？"},
                {"text": "☕️ 可别告诉我你又是那种熬到天亮才去补觉的夜猫子模式。"},
            ],
            source="unit_test",
        )
        request = fake_request(session_id="s-question-cluster", prompt="咖啡啊")

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent("s-question-cluster", message="咖啡啊", sender_id="u1"),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertIn("sylanne_realtime_pending_bot_question", injected)
        self.assertIn("喝了杯什么呀？", injected)
        self.assertIn("一喝就困？", injected)
        self.assertIn("current_user_short_answer=咖啡啊", injected)
        self.assertIn("不要把它当成用户正在发起新的行动", injected)

    def test_interrupted_reply_recovery_can_include_sylanne_memory_summary(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
            },
        )
        self._bind_common_state_hooks(plugin)
        plugin._record_interrupted_reply_breakpoint(
            "s-breakpoint-memory",
            full_text="刚才我误会了其他用户的意思，后面本来要补一句给插件使用者的话。",
            sent_parts=["刚才我误会了。"],
            unsent_parts=["后面本来要补一句给插件使用者的话。"],
            input_epoch=1,
            reason="user_interrupted",
        )
        from memory_engine import MemoryRecord, SylanneMemoryState

        class FakeLivingMemory:
            async def search_memory(self, session_key=None, query="", limit=3):
                raise AssertionError("interrupted recovery must use Sylanne memory")

        class FakeContext:
            def get_registered_star(self, name):
                if name == "astrbot_plugin_livingmemory":
                    return SimpleNamespace(activated=True, star_cls=FakeLivingMemory())
                return None

        plugin.context = FakeContext()
        state = SylanneMemoryState.initial(now=0.0)
        state.records.append(
            MemoryRecord(
                text="他们在这段对话里指插件的其他使用者。",
                summary="他们在这段对话里指插件的其他使用者。",
                session_key="s-breakpoint-memory",
                created_at=10.0,
                updated_at=10.0,
                depth=0.9,
                confidence=0.82,
            ),
        )
        plugin._sylanne_memory_cache["s-breakpoint-memory"] = state
        request = fake_request(session_id="s-breakpoint-memory", prompt="那他们呢")

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent("s-breakpoint-memory", message="那他们呢", sender_id="u1"),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertIn("sylanne_interrupted_reply_breakpoint", injected)
        self.assertIn("sylanne_memory_recall", injected)
        self.assertIn("其他使用者", injected)

    def test_proactive_scheduler_skips_missing_unified_origin(self):
        plugin = new_plugin(
            {
                "enable_proactive_speech_dispatch": True,
                "enable_proactive_speech_scheduler": True,
            },
        )
        plugin._background_post_resource_pressure = lambda: {
            "level": "normal",
            "worker_cap": 6,
            "reason": "unit_test_normal_pressure",
        }
        plugin._proactive_candidate_sessions = {
            "s-missing-origin": {
                "session_key": "s-missing-origin",
                "unified_msg_origin": "",
                "last_seen_at": plugin._observed_now(),
                "last_user_text_excerpt": "缺少 origin。",
            },
        }

        async def fail_if_dispatched(self, *args, **kwargs):
            raise AssertionError("missing origin candidate must not dispatch")

        bind_async(plugin, "request_proactive_speech_dispatch", fail_if_dispatched)

        result = asyncio.run(plugin._run_proactive_scheduler_once())

        self.assertEqual(result["checked"], 0)
        self.assertEqual(result["dispatched"], 0)

    def test_terminate_clears_proactive_scheduler_state(self):
        plugin = new_plugin({"enable_proactive_speech_scheduler": True})
        plugin._ensure_proactive_scheduler_state()
        plugin._proactive_candidate_sessions = {
            "s-old": {
                "session_key": "s-old",
                "unified_msg_origin": "s-old",
                "last_seen_at": plugin._observed_now(),
            },
        }
        plugin._proactive_scheduler_locks["s-old"] = asyncio.Lock()

        asyncio.run(plugin.terminate())

        self.assertIsNone(plugin._proactive_scheduler_task)
        self.assertEqual(plugin._proactive_candidate_sessions, {})
        self.assertEqual(plugin._proactive_scheduler_locks, {})

    def test_sticker_send_is_blocked_when_llm_consistency_rejects_candidate(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin()
        plugin.context = FakeContext()

        async def reject_sticker(self, *args, **kwargs):
            return {
                "approved": False,
                "reason": "candidate mood conflicts with reply",
                "source": "unit_test",
            }

        bind_async(plugin, "_judge_sticker_consistency", reject_sticker)
        plan = {
            "session_key": "s-sticker-check",
            "message_parts": [
                {"index": 0, "text": "那、那个……先慢慢来。", "delay_before_seconds": 0.0},
            ],
            "sticker": {
                "should_send": True,
                "intent": "comfort",
                "candidate": {
                    "path": "C:/tmp/angry.gif",
                    "name": "angry",
                    "tags": ["angry"],
                },
            },
        }

        result = asyncio.run(
            plugin._send_realtime_chat_plan(
                FakeEvent("s-sticker-check"),
                plan,
                source="unit_test",
            ),
        )

        self.assertEqual(len(sent), 1)
        self.assertEqual(result["sticker_result"]["sent"], False)
        self.assertEqual(result["sticker_result"]["blocked_reason"], "llm_rejected")

    def test_realtime_chat_plan_sends_url_sticker_as_image_message(self):
        sent = []

        class StrictMessageChain:
            def __init__(self):
                self.parts = []

            def message(self, text):
                self.parts.append(("message", text))
                return self

            def file_image(self, path):
                self.parts.append(("file_image", path))
                return self

            def __str__(self):
                return "|".join(f"{kind}:{value}" for kind, value in self.parts)

        class FakeImage:
            @staticmethod
            def fromURL(url):
                return ("image_url_component", url)

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message), list(getattr(message, "parts", []))))
                return {"ok": True}

        plugin = new_plugin()
        plugin.context = FakeContext()

        async def approve_sticker(self, *args, **kwargs):
            return {
                "approved": True,
                "reason": "unit test accepts candidate",
                "source": "unit_test",
            }

        bind_async(plugin, "_judge_sticker_consistency", approve_sticker)
        plan = {
            "session_key": "s-url-sticker",
            "message_parts": [
                {"index": 0, "text": "look", "delay_before_seconds": 0.0},
            ],
            "sticker": {
                "should_send": True,
                "intent": "playful",
                "candidate": {
                    "url": "https://example.test/sylanne.png",
                    "name": "url-sticker",
                },
            },
        }

        event_module = sys.modules["astrbot.api.event"]
        old_chain = event_module.MessageChain
        component_module = types.ModuleType("astrbot.api.message_components")
        component_module.Image = FakeImage
        old_component_module = sys.modules.get("astrbot.api.message_components")
        event_module.MessageChain = StrictMessageChain
        sys.modules["astrbot.api.message_components"] = component_module
        try:
            result = asyncio.run(
                plugin._send_realtime_chat_plan(
                    FakeEvent("s-url-sticker"),
                    plan,
                    source="unit_test",
                ),
            )
        finally:
            event_module.MessageChain = old_chain
            if old_component_module is None:
                sys.modules.pop("astrbot.api.message_components", None)
            else:
                sys.modules["astrbot.api.message_components"] = old_component_module

        self.assertEqual(result["sticker_result"]["sent"], True)
        self.assertTrue(
            any(
                ("image_url_component", "https://example.test/sylanne.png") in parts
                for _, _, parts in sent
            ),
        )
        self.assertFalse(any("[表情包]" in text for _, text, _ in sent))

    def test_sticker_consistency_parser_treats_string_false_as_rejected(self):
        plugin = new_plugin()

        judgement = plugin._parse_sticker_consistency_judgement(
            '{"approved": "false", "reason": "语气不一致"}',
        )

        self.assertIsNotNone(judgement)
        self.assertFalse(judgement["approved"])
        self.assertEqual(judgement["source"], "llm_consistency_gate")

    def test_sticker_consistency_skips_llm_when_local_gate_approves(self):
        plugin = new_plugin(
            {
                "use_llm_assessor": True,
                "sticker_llm_consistency_check_enabled": True,
            },
        )
        calls = []

        async def fake_provider_id(self, event):
            return "provider"

        async def fail_call_llm(self, **kwargs):
            calls.append(kwargs)
            raise AssertionError("approved local sticker should not call LLM")

        bind_async(plugin, "_provider_id", fake_provider_id)
        bind_async(plugin, "_call_internal_assessor_llm", fail_call_llm)

        judgement = asyncio.run(
            plugin._judge_sticker_consistency(
                FakeEvent("s-sticker-local-fast"),
                plan={
                    "message_parts": [
                        {"text": "今天进度不错，给你一个开心的表情。"},
                    ],
                },
                sticker={"intent": "celebrate"},
                candidate={
                    "name": "happy.png",
                    "tags": ["happy", "celebrate"],
                },
            ),
        )

        self.assertEqual(calls, [])
        self.assertTrue(judgement["approved"])
        self.assertEqual(judgement["source"], "local_consistency_gate")

    def test_sticker_consistency_uses_fast_assessor_for_llm_gate(self):
        plugin = new_plugin(
            {
                "use_llm_assessor": True,
                "sticker_llm_consistency_check_enabled": True,
                "fast_assessor_provider_id": "fast-json-provider",
                "fast_assessor_timeout_seconds": 1.25,
                "fast_assessor_temperature": 0.0,
            },
        )
        calls = []

        async def fake_provider_id(self, event):
            return "regular-provider"

        async def fake_call_llm(
            self,
            *,
            provider_id,
            prompt,
            system_prompt,
            temperature=None,
            timeout_seconds=None,
        ):
            calls.append((provider_id, prompt, system_prompt, temperature, timeout_seconds))
            return SimpleNamespace(
                completion_text='{"approved": true, "reason": "语气一致"}',
            )

        bind_async(plugin, "_provider_id", fake_provider_id)
        bind_async(plugin, "_call_internal_assessor_llm", fake_call_llm)

        judgement = asyncio.run(
            plugin._judge_sticker_consistency(
                FakeEvent("s-sticker-fast-assessor"),
                plan={
                    "message_parts": [
                        {"text": "我有点生气，不想笑。"},
                    ],
                },
                sticker={"intent": "celebrate"},
                candidate={
                    "name": "angry.png",
                    "tags": ["angry"],
                },
            ),
        )

        self.assertEqual(calls[0][0], "fast-json-provider")
        self.assertEqual(calls[0][3], 0.0)
        self.assertEqual(calls[0][4], 1.25)
        self.assertTrue(judgement["approved"])

    def test_proactive_cold_reply_is_recorded_as_lifelike_feedback(self):
        plugin = new_plugin()
        plugin._proactive_dispatch_audit = {
            "s-cold": collections.deque(
                [
                    {
                        "sent": True,
                        "sent_at": 100.0,
                        "feedback_status": "pending",
                        "feedback_window_seconds": 10.0,
                        "need_mode": "playful_ping",
                    },
                ],
                maxlen=24,
            ),
        }
        observations = []

        async def fake_observe_lifelike_text(self, event_or_session=None, text="", **kwargs):
            observations.append({"text": text, **kwargs})
            return {"ok": True}

        bind_async(plugin, "observe_lifelike_text", fake_observe_lifelike_text)

        asyncio.run(
            plugin._observe_proactive_dispatch_feedback(
                "s-cold",
                "嗯",
                observed_at=125.0,
            ),
        )

        audit = plugin._proactive_dispatch_audit["s-cold"][-1]
        self.assertEqual(audit["feedback_status"], "cold_reply")
        self.assertEqual(observations[0]["source"], "proactive_feedback")
        self.assertIn("更谨慎", observations[0]["text"])

    def test_realtime_chat_dispatch_dry_run_does_not_send(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, message))

        plugin = new_plugin({"enable_sticker_reaction": False})
        plugin.context = FakeContext()

        result = asyncio.run(
            plugin.request_realtime_chat_dispatch(
                FakeEvent("s-realtime-dry"),
                "第一句。第二句。",
                dry_run=True,
            ),
        )

        self.assertFalse(result["sent"])
        self.assertEqual(result["blocked_reason"], "dry_run")
        self.assertEqual(sent, [])

    def test_realtime_chat_dispatch_sends_parts_in_order(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin(
            {
                "runtime_parameter_debug_override_enabled": True,
                "enable_sticker_reaction": False,
                "realtime_chat_min_delay_seconds": 0.0,
                "realtime_chat_max_delay_seconds": 0.0,
            },
        )
        plugin.context = FakeContext()

        result = asyncio.run(
            plugin.request_realtime_chat_dispatch(
                FakeEvent("s-realtime-send"),
                "第一句。第二句！",
                dry_run=False,
            ),
        )

        self.assertTrue(result["sent"])
        self.assertEqual([origin for origin, _ in sent], ["s-realtime-send", "s-realtime-send"])
        self.assertIn("第一句", sent[0][1])
        self.assertIn("第二句", sent[1][1])

    def test_realtime_chat_explicit_dispatch_still_respects_cooldown(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin(
            {
                "runtime_parameter_debug_override_enabled": True,
                "enable_sticker_reaction": False,
                "realtime_chat_session_cooldown_seconds": 9999.0,
            },
        )
        plugin.context = FakeContext()
        plugin._last_realtime_chat_adaptive_settings = {
            "s-dispatch-cooldown": {
                "realtime_chat": {
                    "values": {"valence": 0.2},
                    "restraint": 0.0,
                },
            },
        }
        plugin._realtime_chat_last_sent = {"s-dispatch-cooldown": time.time()}

        result = asyncio.run(
            plugin.request_realtime_chat_dispatch(
                FakeEvent("s-dispatch-cooldown"),
                "第一句。第二句。",
                dry_run=False,
            ),
        )

        self.assertFalse(result["sent"])
        self.assertEqual(result["blocked_reason"], "cooldown_active")
        self.assertEqual(sent, [])

    def test_on_llm_response_intercepts_completion_and_schedules_realtime_send(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_realtime_chat": True,
                "realtime_chat_intercept_llm_response": True,
                "enable_sticker_reaction": False,
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_min_delay_seconds": 0.0,
                "realtime_chat_max_delay_seconds": 0.0,
            },
        )
        plugin.context = FakeContext()
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        response = SimpleNamespace(completion_text="第一句。第二句。")

        event = FakeEvent("s-intercept", platform_name="aiocqhttp")

        async def run_response():
            await plugin.on_llm_response(event, response)
            await self._await_background_tasks(plugin)

        asyncio.run(run_response())

        self.assertIn("sylanne_realtime_delivery_status", response.completion_text)
        self.assertIn("delivery_status=pending_dispatch", response.completion_text)
        self.assertIn("planned_parts=2", response.completion_text)
        self.assertIn("这不等于已经全部发给用户", response.completion_text)
        self.assertEqual(
            getattr(response, "_sylanne_intercepted_completion_text", ""),
            "第一句。第二句。",
        )
        self.assertTrue(event.stopped)
        self.assertEqual(len(sent), 2)
        self.assertEqual(assessment_calls[0]["current_text"], "第一句。第二句。")
        self.assertEqual(saves[0][0], "s-intercept")

    def test_on_llm_response_repeated_hook_call_sends_realtime_reply_once(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_realtime_chat": True,
                "realtime_chat_intercept_llm_response": True,
                "enable_sticker_reaction": False,
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_min_delay_seconds": 0.0,
                "realtime_chat_max_delay_seconds": 0.0,
            },
        )
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        response = SimpleNamespace(completion_text="重复接管第一句。重复接管第二句。")

        async def run_response_twice():
            first_event = FakeEvent("s-intercept-once", platform_name="aiocqhttp")
            await plugin.on_llm_response(first_event, response)
            await self._await_background_tasks(plugin)
            first_sent_count = len(sent)
            second_event = FakeEvent("s-intercept-once", platform_name="aiocqhttp")
            await plugin.on_llm_response(second_event, response)
            await self._await_background_tasks(plugin)
            duplicate_response = SimpleNamespace(
                completion_text="重复接管第一句。重复接管第二句。",
            )
            third_event = FakeEvent("s-intercept-once", platform_name="aiocqhttp")
            await plugin.on_llm_response(third_event, duplicate_response)
            await self._await_background_tasks(plugin)
            return first_event, second_event, third_event, duplicate_response, first_sent_count

        (
            first_event,
            second_event,
            third_event,
            duplicate_response,
            first_sent_count,
        ) = asyncio.run(run_response_twice())

        self.assertTrue(first_event.stopped)
        self.assertTrue(second_event.stopped)
        self.assertTrue(third_event.stopped)
        self.assertEqual(len(sent), first_sent_count)
        self.assertEqual(first_sent_count, 2)
        sent_text = "\n".join(item[1] for item in sent)
        self.assertNotIn("sylanne_realtime_delivery_status", sent_text)
        self.assertEqual(
            getattr(response, "_sylanne_intercepted_completion_text", ""),
            "重复接管第一句。重复接管第二句。",
        )
        self.assertEqual(
            getattr(duplicate_response, "_sylanne_intercepted_completion_text", ""),
            "重复接管第一句。重复接管第二句。",
        )
        queue = plugin._realtime_assistant_history_shadow_cache()["s-intercept-once"]
        self.assertEqual(len(queue), 1)

    def test_on_llm_response_does_not_intercept_tool_call_response(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_realtime_chat": True,
                "realtime_chat_intercept_llm_response": True,
                "enable_sticker_reaction": False,
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_min_delay_seconds": 0.0,
                "realtime_chat_max_delay_seconds": 0.0,
            },
        )
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        response = SimpleNamespace(
            completion_text="我需要调用工具查一下。",
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "query_sylanne_memory", "arguments": "{}"},
                },
            ],
        )
        plugin._conversation_input_epoch = {"s-tool-call": 1}
        plugin._record_conversation_pending_response_epoch("s-tool-call", 1)
        event = FakeEvent("s-tool-call", platform_name="aiocqhttp")

        asyncio.run(plugin.on_llm_response(event, response))

        self.assertFalse(event.stopped)
        self.assertEqual(response.completion_text, "我需要调用工具查一下。")
        self.assertFalse(hasattr(response, "_sylanne_intercepted_completion_text"))
        self.assertEqual(sent, [])
        self.assertEqual(
            list(plugin._conversation_pending_response_epochs["s-tool-call"]),
            [1],
        )

    def test_external_tool_call_response_is_left_to_agent_loop(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_realtime_chat": True,
                "realtime_chat_intercept_llm_response": True,
                "enable_sticker_reaction": False,
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_min_delay_seconds": 0.0,
                "realtime_chat_max_delay_seconds": 0.0,
            },
        )
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        response = SimpleNamespace(
            completion_text="",
            choices=[
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": "call_img_1",
                                "type": "function",
                                "function": {
                                    "name": "aiimg_generate",
                                    "arguments": '{"mode":"edit_ref","prompt":"match face style"}',
                                },
                            },
                        ],
                    },
                },
            ],
        )
        plugin._conversation_input_epoch = {"s-external-tool-call": 1}
        plugin._record_conversation_pending_response_epoch("s-external-tool-call", 1)
        event = FakeEvent("s-external-tool-call", platform_name="aiocqhttp")

        asyncio.run(plugin.on_llm_response(event, response))

        self.assertFalse(event.stopped)
        self.assertEqual(response.completion_text, "")
        self.assertFalse(hasattr(response, "_sylanne_intercepted_completion_text"))
        self.assertEqual(sent, [])
        self.assertEqual(
            list(plugin._conversation_pending_response_epochs["s-external-tool-call"]),
            [1],
        )

    def test_on_llm_response_suppresses_sylanne_tool_json_result(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_realtime_chat": True,
                "realtime_chat_intercept_llm_response": True,
                "enable_sticker_reaction": False,
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_min_delay_seconds": 0.0,
                "realtime_chat_max_delay_seconds": 0.0,
            },
        )
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        tool_json = (
            '{"schema_version":"astrbot.emotion_state.v2",'
            '"api_version":"1.0",'
            '"kind":"emotion_state",'
            '"emotion":{"values":{"valence":0.278675}},'
            '"persona":{"name":"小哀同学"}}'
        )
        response = SimpleNamespace(completion_text=tool_json)
        plugin._conversation_input_epoch = {"s-tool-json": 1}
        plugin._record_conversation_pending_response_epoch("s-tool-json", 1)
        event = FakeEvent("s-tool-json", platform_name="aiocqhttp")

        asyncio.run(plugin.on_llm_response(event, response))

        self.assertTrue(event.stopped)
        self.assertEqual(response.completion_text, "")
        self.assertEqual(
            getattr(response, "_sylanne_intercepted_completion_text", ""),
            tool_json,
        )
        self.assertEqual(
            getattr(response, "_sylanne_intercepted_completion_reason", ""),
            "sylanne_tool_json_result_suppressed",
        )
        self.assertEqual(
            getattr(event, "_sylanne_default_response_stop_reason", ""),
            "sylanne_tool_json_result_suppressed",
        )
        self.assertEqual(sent, [])
        self.assertEqual(
            list(plugin._conversation_pending_response_epochs["s-tool-json"]),
            [1],
        )

    def test_on_llm_response_leaves_structured_role_tool_result_to_agent_loop(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_realtime_chat": True,
                "realtime_chat_intercept_llm_response": True,
                "enable_sticker_reaction": False,
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_min_delay_seconds": 0.0,
                "realtime_chat_max_delay_seconds": 0.0,
            },
        )
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        response = SimpleNamespace(
            role="tool",
            tool_call_id="call_state",
            completion_text='{"kind":"tool_result","content":"internal state only"}',
        )
        plugin._conversation_input_epoch = {"s-role-tool": 1}
        plugin._record_conversation_pending_response_epoch("s-role-tool", 1)
        event = FakeEvent("s-role-tool", platform_name="aiocqhttp")

        asyncio.run(plugin.on_llm_response(event, response))

        self.assertFalse(event.stopped)
        self.assertEqual(
            response.completion_text,
            '{"kind":"tool_result","content":"internal state only"}',
        )
        self.assertFalse(hasattr(response, "_sylanne_intercepted_completion_text"))
        self.assertEqual(sent, [])
        self.assertEqual(
            list(plugin._conversation_pending_response_epochs["s-role-tool"]),
            [1],
        )

    def test_tool_call_response_bypass_preserves_pending_epoch_for_final_reply(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_realtime_chat": True,
                "realtime_chat_intercept_llm_response": True,
                "enable_sticker_reaction": False,
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_min_delay_seconds": 0.0,
                "realtime_chat_max_delay_seconds": 0.0,
            },
        )
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        plugin._conversation_input_epoch = {"s-tool-final": 1}
        plugin._record_conversation_pending_response_epoch("s-tool-final", 1)
        tool_response = SimpleNamespace(
            completion_text="正在调用工具。",
            message=SimpleNamespace(
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "query_sylanne_memory", "arguments": "{}"},
                    },
                ],
            ),
        )
        final_response = SimpleNamespace(completion_text="查到了。第一句。第二句。")
        first_event = FakeEvent("s-tool-final", platform_name="aiocqhttp")
        final_event = FakeEvent("s-tool-final", platform_name="aiocqhttp")

        async def run_turn():
            await plugin.on_llm_response(first_event, tool_response)
            await plugin.on_llm_response(final_event, final_response)
            await self._await_background_tasks(plugin)

        asyncio.run(run_turn())

        self.assertFalse(first_event.stopped)
        self.assertTrue(final_event.stopped)
        self.assertIn("sylanne_realtime_delivery_status", final_response.completion_text)
        self.assertIn("查到了。第一句。第二句。", final_response.completion_text)
        sent_text = "\n".join(item[1] for item in sent)
        self.assertIn("message:查到了。", sent_text)
        self.assertIn("message:第一句。", sent_text)
        self.assertIn("message:第二句。", sent_text)
        self.assertNotIn("s-tool-final", plugin._conversation_pending_response_epochs)

    def test_on_llm_response_intercept_writes_visible_realtime_logs(self):
        import main

        sent = []
        logs = []
        original_logger = main.logger

        class FakeLogger:
            def info(self, message):
                logs.append(str(message))

            def debug(self, message):
                logs.append(str(message))

            def warning(self, message):
                logs.append(str(message))

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_realtime_chat": True,
                "realtime_chat_intercept_llm_response": True,
                "enable_sticker_reaction": False,
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_min_delay_seconds": 0.0,
                "realtime_chat_max_delay_seconds": 0.0,
            },
        )
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        response = SimpleNamespace(completion_text="第一句。第二句。")

        async def run_response():
            await plugin.on_llm_response(
                FakeEvent("s-intercept-log", platform_name="aiocqhttp"),
                response,
            )
            await self._await_background_tasks(plugin)

        try:
            main.logger = FakeLogger()
            asyncio.run(run_response())
        finally:
            main.logger = original_logger

        joined = "\n".join(logs)
        self.assertIn("即时聊天接管主回复", joined)
        self.assertIn("准备分条发送", joined)
        self.assertIn("已发送分条 1/2", joined)
        self.assertIn("分条发送完成", joined)
        self.assertIn("第一句", joined)
        self.assertEqual(len(sent), 2)

    def test_on_llm_response_intercept_preserves_result_chain_images(self):
        from astrbot.api.event import MessageChain

        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message), list(getattr(message, "parts", []))))
                return {"ok": True}

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_realtime_chat": True,
                "realtime_chat_intercept_llm_response": True,
                "enable_sticker_reaction": False,
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_min_delay_seconds": 0.0,
                "realtime_chat_max_delay_seconds": 0.0,
            },
        )
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        response = SimpleNamespace(
            completion_text="look at this image. it should still arrive.",
            result_chain=MessageChain()
            .message("look at this image. it should still arrive.")
            .file_image("C:/tmp/sylanne-image.png"),
        )

        async def run_response():
            await plugin.on_llm_response(
                FakeEvent("s-intercept-image", platform_name="aiocqhttp"),
                response,
            )
            await self._await_background_tasks(plugin)

        asyncio.run(run_response())

        self.assertIn("sylanne_realtime_delivery_status", response.completion_text)
        self.assertIn("look at this image. it should still arrive.", response.completion_text)
        self.assertEqual(
            getattr(response, "_sylanne_intercepted_completion_text", ""),
            "look at this image. it should still arrive.",
        )
        self.assertTrue(
            any(("file_image", "C:/tmp/sylanne-image.png") in parts for _, _, parts in sent),
        )
        self.assertTrue(
            any(
                kind == "message" and "look at this image" in str(value)
                for _, _, parts in sent
                for kind, value in parts
            ),
        )

    def test_on_llm_response_intercepts_even_when_realtime_send_cooldown_is_active(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_realtime_chat": True,
                "realtime_chat_intercept_llm_response": True,
                "enable_sticker_reaction": False,
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_session_cooldown_seconds": 9999.0,
                "realtime_chat_min_delay_seconds": 0.0,
                "realtime_chat_max_delay_seconds": 0.0,
            },
        )
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        plugin._last_realtime_chat_adaptive_settings = {
            "s-intercept-cooldown": {
                "realtime_chat": {
                    "values": {"valence": 0.2},
                    "restraint": 0.0,
                },
            },
        }
        plugin._realtime_chat_last_sent = {"s-intercept-cooldown": time.time()}
        response = SimpleNamespace(completion_text="第一句。第二句。")

        async def run_response():
            await plugin.on_llm_response(
                FakeEvent("s-intercept-cooldown", platform_name="aiocqhttp"),
                response,
            )
            await self._await_background_tasks(plugin)

        asyncio.run(run_response())

        self.assertIn("sylanne_realtime_delivery_status", response.completion_text)
        self.assertIn("planned_parts=2", response.completion_text)
        self.assertEqual(
            getattr(response, "_sylanne_intercepted_completion_text", ""),
            "第一句。第二句。",
        )
        self.assertTrue(sent)
        self.assertGreaterEqual(len(sent), 2)

    def test_realtime_intercept_preserves_assistant_context_for_next_turn(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "realtime_chat_intercept_llm_response": True,
                "enable_sticker_reaction": False,
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_min_delay_seconds": 0.0,
                "realtime_chat_max_delay_seconds": 0.0,
            },
        )
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        response = SimpleNamespace(
            completion_text="我理解错了，你说的是插件的其他用户。我想对他们说：请先读 README。",
        )

        async def run_turns():
            await plugin.on_llm_response(
                FakeEvent("s-realtime-history", platform_name="aiocqhttp"),
                response,
            )
            await self._await_background_tasks(plugin)
            next_request = fake_request(
                session_id="s-realtime-history",
                prompt="那你有什么想对他们说的吗",
            )
            await plugin.on_llm_request(
                FakeEvent("s-realtime-history", message="那你有什么想对他们说的吗"),
                next_request,
            )
            duplicate_request = fake_request(
                session_id="s-realtime-history",
                prompt="再说一遍",
            )
            await plugin.on_llm_request(
                FakeEvent("s-realtime-history", message="再说一遍"),
                duplicate_request,
            )
            return next_request, duplicate_request

        next_request, duplicate_request = asyncio.run(run_turns())

        injected = "\n".join(self._request_text_parts(next_request))
        duplicate_injected = "\n".join(self._request_text_parts(duplicate_request))
        self.assertIn("sylanne_realtime_delivery_status", response.completion_text)
        self.assertIn("delivery_status=pending_dispatch", response.completion_text)
        self.assertIn(
            "插件的其他用户",
            getattr(response, "_sylanne_intercepted_completion_text", ""),
        )
        self.assertTrue(sent)
        self.assertIn("sylanne_realtime_assistant_history", injected)
        self.assertIn("插件的其他用户", injected)
        self.assertIn("请先读 README", injected)
        self.assertLessEqual(len(injected), 1100)
        self.assertNotIn("sylanne_realtime_assistant_history", duplicate_injected)

    def test_realtime_shadow_recovers_from_kv_after_plugin_reload(self):
        stored = {}
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        async def fake_get_kv(self, key, default=None):
            return stored.get(key, default)

        async def fake_put_kv(self, key, value):
            stored[key] = value

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "realtime_chat_intercept_llm_response": True,
                "enable_sticker_reaction": False,
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_min_delay_seconds": 0.0,
                "realtime_chat_max_delay_seconds": 0.0,
            },
        )
        plugin.context = FakeContext()
        bind_async(plugin, "get_kv_data", fake_get_kv)
        bind_async(plugin, "put_kv_data", fake_put_kv)
        self._bind_common_state_hooks(plugin)
        response = SimpleNamespace(completion_text="更新前接管的回复，平台普通历史里没有。")

        async def run_and_reload():
            await plugin.on_llm_response(
                FakeEvent("s-reload-shadow", platform_name="aiocqhttp"),
                response,
            )
            await self._await_background_tasks(plugin)
            recovered = new_plugin(
                {
                    "assessment_timing": "post",
                    "inject_state": False,
                    "enable_realtime_chat": True,
                    "enable_sticker_reaction": False,
                    "use_llm_assessor": False,
                    "realtime_input_completion_probe_delay_seconds": 0.0,
                    "realtime_input_completion_max_wait_seconds": 0.0,
                },
            )
            bind_async(recovered, "get_kv_data", fake_get_kv)
            bind_async(recovered, "put_kv_data", fake_put_kv)
            self._bind_common_state_hooks(recovered)
            request = fake_request(
                session_id="s-reload-shadow",
                prompt="刚才你说什么",
            )
            await recovered.on_llm_request(
                FakeEvent("s-reload-shadow", message="刚才你说什么", sender_id="u1"),
                request,
            )
            duplicate_request = fake_request(
                session_id="s-reload-shadow",
                prompt="再说一遍",
            )
            await recovered.on_llm_request(
                FakeEvent("s-reload-shadow", message="再说一遍", sender_id="u1"),
                duplicate_request,
            )
            return request, duplicate_request, recovered

        request, duplicate_request, recovered = asyncio.run(run_and_reload())

        saved_key = plugin._realtime_delivery_context_kv_key("s-reload-shadow")
        injected = "\n".join(self._request_text_parts(request))
        duplicate_injected = "\n".join(self._request_text_parts(duplicate_request))
        self.assertIn(saved_key, stored)
        self.assertIn("sylanne_realtime_assistant_history", injected)
        self.assertIn("更新前接管的回复", injected)
        self.assertNotIn("sylanne_realtime_assistant_history", duplicate_injected)
        recovered_payload = stored[saved_key]
        self.assertTrue(recovered_payload["shadows"][-1]["consumed"])
        self.assertIn("s-reload-shadow", recovered._realtime_assistant_history_shadow_cache())

    def test_realtime_shadow_restore_retries_after_transient_kv_failure(self):
        calls = {"get": 0}
        stored_key = "realtime_delivery_context:s-retry-shadow"
        stored = {
            stored_key: {
                "schema_version": "astrbot.realtime_delivery_context.v1",
                "kind": "realtime_delivery_context",
                "session_key": "s-retry-shadow",
                "shadows": [
                    {
                        "schema_version": "astrbot.realtime_assistant_history_shadow.v1",
                        "session_key": "s-retry-shadow",
                        "input_epoch": 1,
                        "source": "llm_response_intercept",
                        "delivery_status": "delivered",
                        "message_count": 1,
                        "sent_count": 1,
                        "unsent_count": 0,
                        "full_text": "第一次 KV 失败后仍应恢复的回复",
                        "full_text_excerpt": "第一次 KV 失败后仍应恢复的回复",
                        "excerpt": "第一次 KV 失败后仍应恢复的回复",
                        "full_text_hash": "retry-shadow",
                        "consumed": False,
                    },
                ],
                "breakpoints": [],
            },
        }

        async def flaky_get_kv(self, key, default=None):
            calls["get"] += 1
            if calls["get"] == 1:
                raise RuntimeError("temporary kv read failure")
            return stored.get(key, default)

        async def fake_put_kv(self, key, value):
            stored[key] = value

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
                "realtime_input_completion_probe_delay_seconds": 0.0,
                "realtime_input_completion_max_wait_seconds": 0.0,
            },
        )
        bind_async(plugin, "get_kv_data", flaky_get_kv)
        bind_async(plugin, "put_kv_data", fake_put_kv)
        self._bind_common_state_hooks(plugin)
        first = fake_request(session_id="s-retry-shadow", prompt="我先确认一个无关问题")
        second = fake_request(
            session_id="s-retry-shadow",
            prompt="刚才你通过接管发给我的那句完整回复是什么",
        )

        async def run_retry_restore():
            await plugin.on_llm_request(
                FakeEvent("s-retry-shadow", message="我先确认一个无关问题", sender_id="u1"),
                first,
            )
            await plugin.on_llm_request(
                FakeEvent(
                    "s-retry-shadow",
                    message="刚才你通过接管发给我的那句完整回复是什么",
                    sender_id="u1",
                ),
                second,
            )

        asyncio.run(run_retry_restore())

        self.assertGreaterEqual(calls["get"], 2)
        self.assertNotIn(
            "sylanne_realtime_assistant_history",
            "\n".join(self._request_text_parts(first)),
        )
        self.assertIn(
            "第一次 KV 失败后仍应恢复的回复",
            "\n".join(self._request_text_parts(second)),
        )

    def test_realtime_intercept_skips_shadow_when_agent_history_keeps_reply(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "realtime_chat_intercept_llm_response": True,
                "enable_sticker_reaction": False,
                "runtime_parameter_debug_override_enabled": True,
                "realtime_chat_min_delay_seconds": 0.0,
                "realtime_chat_max_delay_seconds": 0.0,
            },
        )
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        response = SimpleNamespace(
            completion_text="你是用 IP 直连的，还是域名呀？",
        )

        async def run_turns():
            await plugin.on_llm_response(
                FakeEvent("s-agent-history-kept", platform_name="aiocqhttp"),
                response,
            )
            await self._await_background_tasks(plugin)
            next_request = fake_request(
                session_id="s-agent-history-kept",
                prompt="IP",
            )
            next_request.contexts = [
                {
                    "role": "assistant",
                    "content": response.completion_text,
                },
            ]
            await plugin.on_llm_request(
                FakeEvent("s-agent-history-kept", message="IP", sender_id="u1"),
                next_request,
            )
            return next_request

        next_request = asyncio.run(run_turns())

        injected = "\n".join(self._request_text_parts(next_request))
        self.assertEqual(
            getattr(response, "_sylanne_intercepted_completion_text", ""),
            "你是用 IP 直连的，还是域名呀？",
        )
        intercepted = getattr(response, "_sylanne_intercepted_completion_text", "")
        self.assertIn(intercepted, response.completion_text)
        self.assertIn("sylanne_realtime_delivery_status", response.completion_text)
        self.assertTrue(sent)
        self.assertNotIn("sylanne_realtime_assistant_history", injected)
        self.assertNotIn("sylanne_realtime_pending_bot_question", injected)

    def test_unknown_platform_streaming_response_is_not_replayed(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_realtime_chat": True,
                "realtime_chat_intercept_llm_response": True,
                "enable_sticker_reaction": False,
            },
        )
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        response = SimpleNamespace(
            completion_text="dashboard stream should stay in the visible response.",
        )
        event = FakeEvent("web-session", platform_name="dashboard")

        asyncio.run(
            plugin.on_llm_response(
                event,
                response,
            ),
        )

        self.assertEqual(
            response.completion_text,
            "dashboard stream should stay in the visible response.",
        )
        self.assertFalse(event.stopped)
        self.assertEqual(sent, [])

    def test_on_llm_response_drops_stale_realtime_reply_after_user_interrupts(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_realtime_chat": True,
                "realtime_chat_intercept_llm_response": True,
                "enable_sticker_reaction": False,
            },
        )
        plugin.context = FakeContext()
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        first_event = FakeEvent("s-interrupt", message="第一条问题")
        second_event = FakeEvent("s-interrupt", message="用户已经补充了新消息")
        response = SimpleNamespace(completion_text="这是旧问题的长回复。")

        async def run_interrupt():
            await plugin.on_llm_request(
                first_event,
                fake_request(session_id="s-interrupt", prompt="第一条问题"),
            )
            await plugin.on_llm_request(
                second_event,
                fake_request(session_id="s-interrupt", prompt="用户已经补充了新消息"),
            )
            await plugin.on_llm_response(first_event, response)
            await self._await_background_tasks(plugin)

        asyncio.run(run_interrupt())

        self.assertEqual(response.completion_text, "")
        self.assertEqual(
            getattr(response, "_sylanne_intercepted_completion_text", ""),
            "这是旧问题的长回复。",
        )
        self.assertEqual(sent, [])
        self.assertEqual(saves, [])
        self.assertEqual(assessment_calls, [])

    def test_on_llm_response_uses_pending_epoch_when_response_event_is_new_object(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "enable_realtime_chat": True,
                "realtime_chat_intercept_llm_response": True,
                "enable_sticker_reaction": False,
            },
        )
        plugin.context = FakeContext()
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        response = SimpleNamespace(completion_text="这是旧问题的长回复。")

        async def run_interrupt():
            await plugin.on_llm_request(
                FakeEvent("s-interrupt-new-event", message="第一条问题"),
                fake_request(session_id="s-interrupt-new-event", prompt="第一条问题"),
            )
            await plugin.on_llm_request(
                FakeEvent("s-interrupt-new-event", message="用户已经补充了新消息"),
                fake_request(
                    session_id="s-interrupt-new-event",
                    prompt="用户已经补充了新消息",
                ),
            )
            await plugin.on_llm_response(
                FakeEvent("s-interrupt-new-event", message="response wrapper"),
                response,
            )
            await self._await_background_tasks(plugin)

        asyncio.run(run_interrupt())

        self.assertEqual(response.completion_text, "")
        self.assertEqual(
            getattr(response, "_sylanne_intercepted_completion_text", ""),
            "这是旧问题的长回复。",
        )
        self.assertEqual(sent, [])
        self.assertEqual(saves, [])
        self.assertEqual(assessment_calls, [])

    def test_on_llm_response_uses_event_epoch_when_responses_return_out_of_order(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": False,
            },
        )
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        first_event = FakeEvent("s-out-of-order", message="old question")
        second_event = FakeEvent("s-out-of-order", message="new correction")
        old_response = SimpleNamespace(completion_text="old answer")
        new_response = SimpleNamespace(completion_text="new answer")

        async def run_out_of_order():
            await plugin.on_llm_request(
                first_event,
                fake_request(session_id="s-out-of-order", prompt="old question"),
            )
            await plugin.on_llm_request(
                second_event,
                fake_request(session_id="s-out-of-order", prompt="new correction"),
            )
            await plugin.on_llm_response(second_event, new_response)
            await plugin.on_llm_response(first_event, old_response)
            await self._await_background_tasks(plugin)

        asyncio.run(run_out_of_order())

        self.assertEqual(new_response.completion_text, "new answer")
        self.assertEqual(old_response.completion_text, "")
        self.assertEqual(
            getattr(old_response, "_sylanne_intercepted_completion_text", ""),
            "old answer",
        )
        self.assertTrue(first_event.stopped)
        self.assertEqual(len(saves), 1)
        self.assertEqual(assessment_calls[0]["current_text"], "new answer")

    def test_active_agent_followup_merges_pending_user_turn_before_llm(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
                "realtime_input_completion_probe_delay_seconds": 0.0,
                "realtime_input_completion_max_wait_seconds": 0.0,
            },
        )
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        first_request = fake_request(
            session_id="s-active-followup",
            prompt="只有一点点开心嘛",
        )
        second_request = fake_request(
            session_id="s-active-followup",
            prompt="那我要咬死你了😋",
        )

        async def run_followup():
            await plugin.on_llm_request(
                FakeEvent(
                    "s-active-followup",
                    message="只有一点点开心嘛",
                    sender_id="u1",
                ),
                first_request,
            )
            await plugin.on_llm_request(
                FakeEvent(
                    "s-active-followup",
                    message="那我要咬死你了😋",
                    sender_id="u1",
                ),
                second_request,
            )

        asyncio.run(run_followup())

        injected = "\n".join(self._request_text_parts(second_request))
        self.assertIn("sylanne_active_agent_followup_merge", injected)
        self.assertIn("只有一点点开心嘛", injected)
        self.assertIn("那我要咬死你了😋", injected)
        self.assertIn("merged_current_user=只有一点点开心嘛 / 那我要咬死你了😋", injected)
        self.assertIn("只有一点点开心嘛", plugin._last_request_text["s-active-followup"])
        self.assertIn("那我要咬死你了😋", plugin._last_request_text["s-active-followup"])
        self.assertGreaterEqual(len(saves), 2)
        self.assertEqual(len(assessment_calls), 2)
        self.assertIn("只有一点点开心嘛", assessment_calls[-1]["current_text"])
        self.assertIn("那我要咬死你了😋", assessment_calls[-1]["current_text"])

    def test_active_agent_followup_merges_pending_user_turn_before_tool_request(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
                "realtime_input_completion_probe_delay_seconds": 0.0,
                "realtime_input_completion_max_wait_seconds": 0.0,
            },
        )
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        first_request = fake_request(
            session_id="s-active-tool-followup",
            prompt="[引用消息] 我得意思是这张图的脸也要相同风格处理 脸的细节太多了 整体不统一",
        )
        second_request = fake_request(
            session_id="s-active-tool-followup",
            prompt="所以图片捏",
        )
        second_request.tools = [
            {
                "type": "function",
                "function": {
                    "name": "aiimg_generate",
                    "description": "generate or edit images",
                    "parameters": {"type": "object"},
                },
            },
        ]

        async def run_followup():
            await plugin.on_llm_request(
                FakeEvent(
                    "s-active-tool-followup",
                    message=(
                        "[引用消息] 我得意思是这张图的脸也要相同风格处理 "
                        "脸的细节太多了 整体不统一"
                    ),
                    sender_id="u1",
                ),
                first_request,
            )
            await plugin.on_llm_request(
                FakeEvent(
                    "s-active-tool-followup",
                    message="所以图片捏",
                    sender_id="u1",
                ),
                second_request,
            )

        asyncio.run(run_followup())

        injected = "\n".join(self._request_text_parts(second_request))
        self.assertIn("sylanne_active_agent_followup_merge", injected)
        self.assertIn("这张图的脸也要相同风格处理", injected)
        self.assertIn("所以图片捏", injected)
        self.assertIn("merged_current_user=", injected)
        self.assertIn("这张图", plugin._last_request_text["s-active-tool-followup"])
        self.assertIn("所以图片捏", plugin._last_request_text["s-active-tool-followup"])
        self.assertGreaterEqual(len(saves), 2)
        self.assertEqual(len(assessment_calls), 2)
        self.assertIn("这张图的脸也要相同风格处理", assessment_calls[-1]["current_text"])
        self.assertIn("所以图片捏", assessment_calls[-1]["current_text"])

    def test_stale_reply_is_kept_as_compact_breakpoint_for_next_turn(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "realtime_chat_intercept_llm_response": True,
                "enable_sticker_reaction": False,
            },
        )
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        stale_response = SimpleNamespace(
            completion_text="old-answer-start " + ("x" * 1200) + " old-answer-end",
        )

        async def run_interrupt_and_next_turn():
            await plugin.on_llm_request(
                FakeEvent("s-stale-breakpoint", message="first question"),
                fake_request(session_id="s-stale-breakpoint", prompt="first question"),
            )
            await plugin.on_llm_request(
                FakeEvent("s-stale-breakpoint", message="new message interrupts"),
                fake_request(
                    session_id="s-stale-breakpoint",
                    prompt="new message interrupts",
                ),
            )
            await plugin.on_llm_response(
                FakeEvent("s-stale-breakpoint", message="first response wrapper"),
                stale_response,
            )
            next_request = fake_request(
                session_id="s-stale-breakpoint",
                prompt="continue from the new message",
            )
            await plugin.on_llm_request(
                FakeEvent("s-stale-breakpoint", message="continue from the new message"),
                next_request,
            )
            duplicate_request = fake_request(
                session_id="s-stale-breakpoint",
                prompt="another follow up",
            )
            await plugin.on_llm_request(
                FakeEvent("s-stale-breakpoint", message="another follow up"),
                duplicate_request,
            )
            return next_request, duplicate_request

        next_request, duplicate_request = asyncio.run(run_interrupt_and_next_turn())

        injected = "\n".join(self._request_text_parts(next_request))
        duplicate_injected = "\n".join(self._request_text_parts(duplicate_request))
        self.assertEqual(stale_response.completion_text, "")
        self.assertTrue(
            getattr(
                stale_response,
                "_sylanne_intercepted_completion_text",
                "",
            ).startswith("old-answer-start"),
        )
        self.assertEqual(sent, [])
        self.assertIn("sylanne_interrupted_reply_breakpoint", injected)
        self.assertIn("late_llm_response_after_user_message", injected)
        self.assertIn("unsent_count=1", injected)
        self.assertIn("full_hash=", injected)
        breakpoint_text = self._find_text_part(next_request, "sylanne_interrupted_reply_breakpoint")
        self.assertLessEqual(len(breakpoint_text), 900)
        self.assertNotIn("x" * 300, injected)
        self.assertNotIn("...", injected)
        self.assertNotIn("sylanne_interrupted_reply_breakpoint", duplicate_injected)

    def test_realtime_chat_plan_stops_remaining_parts_when_user_interrupts(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin({"enable_sticker_reaction": False})
        plugin.context = FakeContext()
        plugin._conversation_input_epoch = {"s-part-interrupt": 1}
        plan = {
            "session_key": "s-part-interrupt",
            "input_epoch": 1,
            "message_parts": [
                {"index": 0, "text": "第一句", "delay_before_seconds": 0.0},
                {"index": 1, "text": "第二句", "delay_before_seconds": 0.0},
            ],
        }

        original_chain = plugin._build_astrbot_message_chain

        def interrupt_after_first(text):
            message = original_chain(text)
            plugin._conversation_input_epoch["s-part-interrupt"] = 2
            return message

        plugin._build_astrbot_message_chain = interrupt_after_first

        result = asyncio.run(
            plugin._send_realtime_chat_plan(
                FakeEvent("s-part-interrupt"),
                plan,
                source="unit_test",
            ),
        )

        self.assertEqual(len(sent), 1)
        self.assertEqual(result["message_count"], 1)
        self.assertEqual(result["interrupted_reason"], "user_interrupted")
        request = fake_request(session_id="s-part-interrupt", prompt="用户插话")
        appended = plugin._append_interrupted_reply_breakpoint_if_any(
            request,
            "s-part-interrupt",
            budget=None,
        )
        injected = "\n".join(self._request_text_parts(request))
        self.assertTrue(appended)
        self.assertIn("sent_count=1", injected)
        self.assertIn("unsent_count=1", injected)
        self.assertIn("已发送摘要=", injected)
        self.assertIn("未发送开头=", injected)
        self.assertIn("没有完整送达", injected)

    def test_new_request_cancels_sleeping_realtime_dispatch_task(self):
        sent = []
        first_sent = asyncio.Event()

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                first_sent.set()
                return {"ok": True}

        plugin = new_plugin({"enable_realtime_chat": True, "enable_sticker_reaction": False})
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        plugin._conversation_input_epoch = {"s-cancel-sleep": 1}
        plan = {
            "session_key": "s-cancel-sleep",
            "input_epoch": 1,
            "message_parts": [
                {"index": 0, "text": "old first", "delay_before_seconds": 0.0},
                {"index": 1, "text": "old delayed tail", "delay_before_seconds": 30.0},
            ],
        }

        async def run_cancel():
            send_task = asyncio.create_task(
                plugin._send_realtime_chat_plan(
                    FakeEvent("s-cancel-sleep"),
                    plan,
                    source="unit_test",
                ),
            )
            await first_sent.wait()
            await asyncio.sleep(0.12)
            next_request = fake_request(
                session_id="s-cancel-sleep",
                prompt="new message while old reply is sleeping",
            )
            await plugin.on_llm_request(
                FakeEvent("s-cancel-sleep", message="new message while old reply is sleeping"),
                next_request,
            )
            result = await asyncio.wait_for(send_task, timeout=0.25)
            return result, next_request

        result, next_request = asyncio.run(run_cancel())

        injected = "\n".join(self._request_text_parts(next_request))
        self.assertEqual(sent, [("s-cancel-sleep", "message:old first")])
        self.assertEqual(result["message_count"], 1)
        self.assertEqual(result["interrupted_reason"], "user_interrupted")
        self.assertIn("sylanne_realtime_active_dispatch", injected)
        self.assertIn("old first", injected)

    def test_new_request_before_first_chunk_keeps_unsent_reply_context(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin({"enable_realtime_chat": True, "enable_sticker_reaction": False})
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        plugin._conversation_input_epoch = {"s-before-first": 1}
        plan = {
            "session_key": "s-before-first",
            "input_epoch": 1,
            "full_text": "unsent reply mentions plugin users and should remain as context",
            "message_parts": [
                {"index": 0, "text": "unsent reply mentions plugin users", "delay_before_seconds": 30.0},
                {"index": 1, "text": "and should remain as context", "delay_before_seconds": 0.0},
            ],
        }

        async def run_cancel_before_first_chunk():
            send_task = asyncio.create_task(
                plugin._send_realtime_chat_plan(
                    FakeEvent("s-before-first"),
                    plan,
                    source="unit_test",
                ),
            )
            await asyncio.sleep(0.05)
            next_request = fake_request(
                session_id="s-before-first",
                prompt="new user supplement before first chunk",
            )
            await plugin.on_llm_request(
                FakeEvent("s-before-first", message="new user supplement before first chunk"),
                next_request,
            )
            result = await asyncio.wait_for(send_task, timeout=0.25)
            return result, next_request

        result, next_request = asyncio.run(run_cancel_before_first_chunk())

        injected = "\n".join(self._request_text_parts(next_request))
        self.assertEqual(sent, [])
        self.assertEqual(result["message_count"], 0)
        self.assertEqual(result["interrupted_reason"], "user_interrupted")
        self.assertIn("sylanne_realtime_active_dispatch", injected)
        self.assertIn("第一条真正发出前", injected)
        self.assertIn("plugin users", injected)

    def test_zero_sent_interrupted_realtime_reply_becomes_next_turn_breakpoint(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin({"enable_realtime_chat": True, "enable_sticker_reaction": False})
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        plugin._conversation_input_epoch = {"s-zero-breakpoint": 1}
        plan = {
            "session_key": "s-zero-breakpoint",
            "input_epoch": 1,
            "full_text": "unsent intent should survive plugin update",
            "message_parts": [
                {
                    "index": 0,
                    "text": "unsent intent should survive",
                    "delay_before_seconds": 30.0,
                },
                {
                    "index": 1,
                    "text": "plugin update",
                    "delay_before_seconds": 0.0,
                },
            ],
        }

        async def run_zero_sent_interruption():
            send_task = asyncio.create_task(
                plugin._send_realtime_chat_plan(
                    FakeEvent("s-zero-breakpoint"),
                    plan,
                    source="unit_test",
                ),
            )
            await asyncio.sleep(0.05)
            interrupt_request = fake_request(
                session_id="s-zero-breakpoint",
                prompt="new user correction before first chunk",
            )
            await plugin.on_llm_request(
                FakeEvent(
                    "s-zero-breakpoint",
                    message="new user correction before first chunk",
                ),
                interrupt_request,
            )
            result = await asyncio.wait_for(send_task, timeout=0.25)
            next_request = fake_request(
                session_id="s-zero-breakpoint",
                prompt="what did you mean",
            )
            await plugin.on_llm_request(
                FakeEvent("s-zero-breakpoint", message="what did you mean"),
                next_request,
            )
            duplicate_request = fake_request(
                session_id="s-zero-breakpoint",
                prompt="again",
            )
            await plugin.on_llm_request(
                FakeEvent("s-zero-breakpoint", message="again"),
                duplicate_request,
            )
            return result, interrupt_request, next_request, duplicate_request

        result, interrupt_request, next_request, duplicate_request = asyncio.run(
            run_zero_sent_interruption(),
        )

        interrupt_injected = "\n".join(self._request_text_parts(interrupt_request))
        injected = "\n".join(self._request_text_parts(next_request))
        duplicate_injected = "\n".join(self._request_text_parts(duplicate_request))
        self.assertEqual(sent, [])
        self.assertEqual(result["message_count"], 0)
        self.assertEqual(result["interrupted_reason"], "user_interrupted")
        self.assertIn("sylanne_interrupted_reply_breakpoint", interrupt_injected)
        self.assertIn("sent_count=0", interrupt_injected)
        self.assertIn("unsent_count=2", interrupt_injected)
        self.assertIn("unsent intent should survive", interrupt_injected)
        self.assertEqual(interrupt_request.prompt, "new user correction before first chunk")
        self.assertNotIn("sylanne_realtime_assistant_history", injected)
        self.assertNotIn("sylanne_interrupted_reply_breakpoint", duplicate_injected)

    def test_realtime_chat_active_dispatch_is_visible_to_interrupting_request(self):
        sent = []
        first_sent = asyncio.Event()

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                first_sent.set()
                return {"ok": True}

        plugin = new_plugin({"enable_realtime_chat": True, "enable_sticker_reaction": False})
        plugin.context = FakeContext()
        plugin._conversation_input_epoch = {"s-active-interrupt": 1}
        plan = {
            "session_key": "s-active-interrupt",
            "input_epoch": 1,
            "message_parts": [
                {"index": 0, "text": "我理解错了，你说的是插件的其他用户。", "delay_before_seconds": 0.0},
                {"index": 1, "text": "我想对他们说：请先读 README。", "delay_before_seconds": 0.2},
            ],
        }

        async def run_interrupting_request():
            send_task = asyncio.create_task(
                plugin._send_realtime_chat_plan(
                    FakeEvent("s-active-interrupt"),
                    plan,
                    source="unit_test",
                ),
            )
            await first_sent.wait()
            interrupt_request = fake_request(
                session_id="s-active-interrupt",
                prompt="那你有什么想对他们说的吗",
            )
            await plugin.on_llm_request(
                FakeEvent("s-active-interrupt", message="那你有什么想对他们说的吗"),
                interrupt_request,
            )
            plugin._conversation_input_epoch["s-active-interrupt"] = 2
            result = await send_task
            return interrupt_request, result

        interrupt_request, result = asyncio.run(run_interrupting_request())

        injected = "\n".join(self._request_text_parts(interrupt_request))
        self.assertEqual(
            sent,
            [("s-active-interrupt", "message:我理解错了，你说的是插件的其他用户。")],
        )
        self.assertIn("sylanne_realtime_active_dispatch", injected)
        self.assertIn("插件的其他用户", injected)
        self.assertEqual(result["interrupted_reason"], "user_interrupted")

    def test_gemini_followup_tool_request_keeps_prior_image_edit_context(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
            },
        )
        self._bind_common_state_hooks(plugin)
        plugin._record_realtime_assistant_history_shadow(
            "s-image-edit-followup",
            full_text=(
                "确实，刚才那张图的脸部渲染太写实，和几何色块整体不统一。"
                "我这就把脸也处理成相同的几何抽象风格。"
            ),
            input_epoch=1,
            message_parts=[
                {"text": "刚才那张图的脸部渲染太写实。"},
                {"text": "我这就把脸也处理成相同的几何抽象风格。"},
            ],
            source="unit_test",
        )

        async def fake_get_current_chat_provider_id(*, umo):
            return "哈基米/gemini-3-flash-preview"

        plugin.context = SimpleNamespace(
            get_current_chat_provider_id=fake_get_current_chat_provider_id,
        )
        request = fake_request(
            session_id="s-image-edit-followup",
            prompt="所以图片捏",
        )
        request.tools = [
            {
                "type": "function",
                "function": {
                    "name": "aiimg_generate",
                    "description": "generate or edit images",
                    "parameters": {"type": "object"},
                },
            },
        ]
        request.contexts = [
            {
                "role": "user",
                "content": (
                    "[引用消息] 我得意思是这张图的脸也要相同风格处理 "
                    "脸的细节太多了 你这个整体不统一的"
                ),
            },
        ]

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "s-image-edit-followup",
                    message="所以图片捏",
                    sender_id="u1",
                ),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertIn("sylanne_realtime_assistant_history", injected)
        self.assertIn("刚才那张图", injected)
        self.assertIn("几何抽象风格", injected)
        self.assertNotIn("sylanne_gemini_visible_output_guard", injected)

    def test_realtime_chat_interruption_records_low_token_resume_breakpoint(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_sticker_reaction": False,
            },
        )
        plugin.context = FakeContext()
        self._bind_common_state_hooks(plugin)
        plugin._conversation_input_epoch = {"s-part-breakpoint": 1}
        plan = {
            "session_key": "s-part-breakpoint",
            "input_epoch": 1,
            "message_parts": [
                {"index": 0, "text": "first part", "delay_before_seconds": 0.0},
                {
                    "index": 1,
                    "text": "second unsent part " + ("y" * 900),
                    "delay_before_seconds": 0.0,
                },
            ],
        }

        original_chain = plugin._build_astrbot_message_chain

        def interrupt_after_first(text):
            message = original_chain(text)
            plugin._conversation_input_epoch["s-part-breakpoint"] = 2
            return message

        async def run_interruption_and_next_turn():
            plugin._build_astrbot_message_chain = interrupt_after_first
            result = await plugin._send_realtime_chat_plan(
                FakeEvent("s-part-breakpoint"),
                plan,
                source="unit_test",
            )
            plugin._build_astrbot_message_chain = original_chain
            next_request = fake_request(
                session_id="s-part-breakpoint",
                prompt="what were you saying",
            )
            await plugin.on_llm_request(
                FakeEvent("s-part-breakpoint", message="what were you saying"),
                next_request,
            )
            return result, next_request

        result, next_request = asyncio.run(run_interruption_and_next_turn())

        injected = "\n".join(self._request_text_parts(next_request))
        self.assertEqual(len(sent), 1)
        self.assertEqual(result["message_count"], 1)
        self.assertEqual(result["interrupted_reason"], "user_interrupted")
        self.assertIn("sylanne_interrupted_reply_breakpoint", injected)
        self.assertIn("sent_count=1", injected)
        self.assertIn("unsent_count=1", injected)
        self.assertIn("unsent_hash=", injected)
        self.assertLessEqual(len(injected), 720)
        self.assertNotIn("y" * 300, injected)
        self.assertNotIn("...", injected)

    def test_interrupted_realtime_reply_becomes_emotion_observation_context(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
                "realtime_input_completion_probe_delay_seconds": 0.0,
                "realtime_input_completion_max_wait_seconds": 0.0,
            },
        )
        saves = []
        assessment_calls = []
        self._bind_common_state_hooks(plugin, saves=saves, assessment_calls=assessment_calls)
        plugin._record_interrupted_reply_breakpoint(
            "s-interrupt-emotion",
            reason="user_interrupted",
            input_epoch=1,
            sent_parts=["我刚才想说"],
            unsent_parts=["后面还没说完"],
            source="unit_test",
        )
        request = fake_request(session_id="s-interrupt-emotion", prompt="不是，我补充一下")

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent("s-interrupt-emotion", message="不是，我补充一下", sender_id="u1"),
                request,
            ),
        )

        self.assertEqual(len(assessment_calls), 1)
        current_text = assessment_calls[0]["current_text"]
        self.assertIn("assistant_interrupted_event", current_text)
        self.assertIn("可能带来情绪波动", current_text)
        self.assertIn("不要预设一定是正面或负面", current_text)
        self.assertIn("不是，我补充一下", current_text)

    def test_realtime_input_fragments_are_injected_as_one_user_turn(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
                "realtime_input_completion_probe_delay_seconds": 0.05,
                "realtime_input_completion_max_wait_seconds": 0.3,
            },
        )
        plugin._observed_now = lambda: 1000.0
        self._bind_common_state_hooks(plugin)
        requests = [
            fake_request(session_id="s-fragments", prompt=text)
            for text in ("你", "是", "🐷", "吗")
        ]

        async def run_fragments():
            tasks = []
            for request, text in zip(requests, ("你", "是", "🐷", "吗")):
                tasks.append(
                    asyncio.create_task(
                        plugin.on_llm_request(
                            FakeEvent("s-fragments", message=text, sender_id="u1"),
                            request,
                        ),
                    ),
                )
                await asyncio.sleep(0.01)
            await asyncio.gather(*tasks)

        asyncio.run(run_fragments())

        first_three = "\n".join(
            "\n".join(self._request_text_parts(request))
            for request in requests[:3]
        )
        final_injected = "\n".join(self._request_text_parts(requests[-1]))
        for request in requests[:3]:
            self.assertTrue(request._sylanne_realtime_input_hold)
        self.assertFalse(getattr(requests[-1], "_sylanne_realtime_input_hold", False))
        self.assertNotIn("sylanne_user_message_fragments", first_three)
        self.assertIn("sylanne_user_message_fragments", final_injected)
        self.assertIn("同一用户在很短时间内分多条发送", final_injected)
        self.assertIn("你 / 是 / 🐷 / 吗", final_injected)
        self.assertIn("merged_intent=你 是 🐷 吗", final_injected)
        self.assertLessEqual(len(final_injected), 520)

    def test_realtime_input_fragments_hold_request_and_skip_emotion_until_merged(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
                "inject_state": True,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
                "realtime_input_completion_probe_delay_seconds": 0.05,
                "realtime_input_completion_max_wait_seconds": 0.2,
            },
        )
        clock = {"now": 3000.0}
        plugin._observed_now = lambda: clock["now"]
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        events = [FakeEvent("s-hold-fragments", message=text, sender_id="u1") for text in ("我！", "就！", "是！")]
        requests = [
            fake_request(session_id="s-hold-fragments", prompt=text)
            for text in ("我！", "就！", "是！")
        ]

        async def run_fragments():
            tasks = []
            for event, request in zip(events, requests):
                tasks.append(asyncio.create_task(plugin.on_llm_request(event, request)))
                await asyncio.sleep(0.01)
                clock["now"] += 0.2
            await asyncio.gather(*tasks)

        asyncio.run(run_fragments())

        self.assertTrue(events[0].stopped)
        self.assertTrue(events[1].stopped)
        self.assertFalse(events[2].stopped)
        self.assertTrue(requests[0]._sylanne_realtime_input_hold)
        self.assertTrue(requests[1]._sylanne_realtime_input_hold)
        self.assertEqual(requests[0]._sylanne_default_response_stop_reason, "realtime_input_fragment_waiting")
        self.assertEqual(requests[1]._sylanne_default_response_stop_reason, "realtime_input_fragment_waiting")
        self.assertEqual(len(assessment_calls), 1)
        self.assertGreaterEqual(len(saves), 1)
        self.assertIn("我！ 就！ 是！", assessment_calls[0]["current_text"])
        final_injected = "\n".join(self._request_text_parts(requests[-1]))
        self.assertIn("merged_intent=我！ 就！ 是！", final_injected)

    def test_realtime_input_llm_gate_can_release_complete_short_fragment(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": True,
                "realtime_input_completion_llm_gate_enabled": True,
                "fast_assessor_provider_id": "fast-json-provider",
                "realtime_input_completion_probe_delay_seconds": 0.0,
                "realtime_input_completion_max_wait_seconds": 0.01,
            },
        )
        plugin._observed_now = lambda: 4000.0
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        calls = []

        async def fake_provider_id(self, event):
            return "provider"

        async def fake_call_llm(self, *, provider_id, prompt, system_prompt):
            calls.append((provider_id, prompt, system_prompt))
            return SimpleNamespace(
                completion_text='{"is_complete": true, "confidence": 0.91, "reason": "完整强调"}',
            )

        bind_async(plugin, "_provider_id", fake_provider_id)
        bind_async(plugin, "_call_internal_assessor_llm", fake_call_llm)
        event = FakeEvent("s-llm-release", message="我！", sender_id="u1")
        request = fake_request(session_id="s-llm-release", prompt="我！")

        asyncio.run(plugin.on_llm_request(event, request))

        self.assertFalse(event.stopped)
        self.assertFalse(getattr(request, "_sylanne_realtime_input_hold", False))
        self.assertEqual(plugin._realtime_input_fragment_windows, {})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "fast-json-provider")
        self.assertEqual(len(assessment_calls), 1)
        self.assertGreaterEqual(len(saves), 1)

    def test_fast_assessor_provider_is_opt_in_when_fast_unset(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": True,
                "emotion_provider_id": "judge-provider",
                "realtime_input_completion_llm_gate_enabled": True,
                "realtime_input_completion_probe_delay_seconds": 0.0,
                "realtime_input_completion_max_wait_seconds": 0.01,
            },
        )
        plugin._observed_now = lambda: 4010.0
        self._bind_common_state_hooks(plugin)
        calls = []

        async def fake_call_llm(self, *, provider_id, prompt, system_prompt):
            calls.append((provider_id, prompt, system_prompt))
            return SimpleNamespace(
                completion_text='{"is_complete": true, "confidence": 0.91, "reason": "完整短句"}',
            )

        bind_async(plugin, "_call_internal_assessor_llm", fake_call_llm)
        event = FakeEvent("s-llm-release-fallback", message="我！", sender_id="u1")
        request = fake_request(session_id="s-llm-release-fallback", prompt="我！")

        asyncio.run(plugin.on_llm_request(event, request))

        self.assertFalse(event.stopped)
        self.assertEqual(calls, [])

    def test_realtime_input_fast_assessor_prompt_uses_short_context_budget(self):
        plugin = new_plugin(
            {
                "enable_realtime_chat": True,
                "use_llm_assessor": True,
                "fast_assessor_provider_id": "fast-json-provider",
                "fast_assessor_max_context_chars": 260,
            },
        )
        payload = {
            "fragments": ["我只是想补充一下", "这段特别长" + "x" * 1200],
            "merged_intent": "我只是想补充一下 " + "y" * 1200,
        }

        prompt = plugin._build_realtime_input_completion_prompt(
            payload,
            max_chars=plugin._fast_assessor_max_context_chars(),
        )

        self.assertLessEqual(len(prompt), 260)
        self.assertIn("只输出 JSON", prompt)

    def test_realtime_input_complete_llm_gate_skips_remaining_max_wait(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": True,
                "realtime_input_completion_llm_gate_enabled": True,
                "fast_assessor_provider_id": "provider",
                "realtime_input_completion_probe_delay_seconds": 0.0,
                "realtime_input_completion_max_wait_seconds": 4.0,
            },
        )
        plugin._observed_now = lambda: 4050.0
        self._bind_common_state_hooks(plugin)
        waits = []

        async def fake_provider_id(self, event):
            return "provider"

        async def fake_call_llm(self, *, provider_id, prompt, system_prompt):
            return SimpleNamespace(
                completion_text='{"is_complete": true, "confidence": 0.96, "reason": "已经完整"}',
            )

        async def fake_wait(self, session_key, payload, wait_seconds):
            waits.append(wait_seconds)
            return True

        bind_async(plugin, "_provider_id", fake_provider_id)
        bind_async(plugin, "_call_internal_assessor_llm", fake_call_llm)
        bind_async(plugin, "_wait_realtime_input_window_unchanged", fake_wait)
        event = FakeEvent("s-llm-release-fast", message="我！", sender_id="u1")
        request = fake_request(session_id="s-llm-release-fast", prompt="我！")

        asyncio.run(plugin.on_llm_request(event, request))

        self.assertFalse(event.stopped)
        self.assertEqual(waits, [0.0])
        self.assertEqual(plugin._realtime_input_fragment_windows, {})

    def test_realtime_input_llm_gate_releases_incomplete_fragment_after_max_wait(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": True,
                "realtime_input_completion_llm_gate_enabled": True,
                "fast_assessor_provider_id": "provider",
                "realtime_input_completion_probe_delay_seconds": 0.0,
                "realtime_input_completion_max_wait_seconds": 0.02,
            },
        )
        plugin._observed_now = lambda: 4100.0
        saves, assessment_calls = self._bind_common_state_hooks(plugin)

        async def fake_provider_id(self, event):
            return "provider"

        async def fake_call_llm(self, *, provider_id, prompt, system_prompt):
            return SimpleNamespace(
                completion_text='{"is_complete": false, "confidence": 0.88, "reason": "还在铺垫"}',
            )

        bind_async(plugin, "_provider_id", fake_provider_id)
        bind_async(plugin, "_call_internal_assessor_llm", fake_call_llm)
        event = FakeEvent("s-llm-hold", message="我！", sender_id="u1")
        request = fake_request(session_id="s-llm-hold", prompt="我！")

        asyncio.run(plugin.on_llm_request(event, request))

        self.assertFalse(event.stopped)
        self.assertFalse(getattr(request, "_sylanne_realtime_input_hold", False))
        self.assertEqual(len(assessment_calls), 1)
        self.assertGreaterEqual(len(saves), 1)
        injected = "\n".join(self._request_text_parts(request))
        self.assertNotIn("sylanne_user_message_fragments", injected)
        self.assertIn("我！", assessment_calls[0]["current_text"])

    def test_realtime_input_llm_gate_stops_old_fragment_when_user_continues(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": True,
                "realtime_input_completion_llm_gate_enabled": True,
                "fast_assessor_provider_id": "provider",
                "realtime_input_completion_probe_delay_seconds": 0.05,
                "realtime_input_completion_max_wait_seconds": 0.2,
            },
        )
        plugin._observed_now = lambda: 4200.0
        saves, assessment_calls = self._bind_common_state_hooks(plugin)

        async def fake_provider_id(self, event):
            return "provider"

        async def fake_call_llm(self, *, provider_id, prompt, system_prompt):
            return SimpleNamespace(
                completion_text='{"is_complete": false, "confidence": 0.88, "reason": "还在铺垫"}',
            )

        bind_async(plugin, "_provider_id", fake_provider_id)
        bind_async(plugin, "_call_internal_assessor_llm", fake_call_llm)
        first_event = FakeEvent("s-llm-continues", message="我！", sender_id="u1")
        second_event = FakeEvent("s-llm-continues", message="就！", sender_id="u1")
        first_request = fake_request(session_id="s-llm-continues", prompt="我！")
        second_request = fake_request(session_id="s-llm-continues", prompt="就！")

        async def run_two_fragments():
            first_task = asyncio.create_task(plugin.on_llm_request(first_event, first_request))
            await asyncio.sleep(0.01)
            second_task = asyncio.create_task(plugin.on_llm_request(second_event, second_request))
            await asyncio.gather(first_task, second_task)

        asyncio.run(run_two_fragments())

        self.assertTrue(first_event.stopped)
        self.assertTrue(first_request._sylanne_realtime_input_hold)
        self.assertFalse(second_event.stopped)
        self.assertEqual(len(assessment_calls), 1)
        self.assertGreaterEqual(len(saves), 1)

    def test_realtime_input_llm_incomplete_gate_merges_slow_semantic_fragments(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": True,
                "realtime_input_completion_llm_gate_enabled": True,
                "fast_assessor_provider_id": "provider",
                "realtime_input_completion_probe_delay_seconds": 0.01,
                "realtime_input_completion_max_wait_seconds": 4.0,
            },
        )
        clock = {"now": 6000.0}
        plugin._observed_now = lambda: clock["now"]
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        calls = []

        async def fake_provider_id(self, event):
            return "provider"

        async def fake_call_llm(self, *, provider_id, prompt, system_prompt):
            calls.append((provider_id, prompt, system_prompt))
            complete = "是从哪里看来的" in prompt
            return SimpleNamespace(
                completion_text=(
                    '{"is_complete": true, "confidence": 0.93, "reason": "追问已经完整"}'
                    if complete
                    else '{"is_complete": false, "confidence": 0.92, "reason": "铺垫后还在补充追问"}'
                ),
            )

        bind_async(plugin, "_provider_id", fake_provider_id)
        bind_async(plugin, "_call_internal_assessor_llm", fake_call_llm)
        texts = ["我只是很纳闷", "为啥你要问我", "是从哪里看来的"]
        events = [
            FakeEvent("s-slow-semantic-fragments", message=text, sender_id="u1")
            for text in texts
        ]
        requests = [
            fake_request(session_id="s-slow-semantic-fragments", prompt=text)
            for text in texts
        ]

        async def run_fragments():
            first = asyncio.create_task(plugin.on_llm_request(events[0], requests[0]))
            await asyncio.sleep(0.03)
            clock["now"] += 1.5
            second = asyncio.create_task(plugin.on_llm_request(events[1], requests[1]))
            await asyncio.sleep(0.03)
            clock["now"] += 1.2
            third = asyncio.create_task(plugin.on_llm_request(events[2], requests[2]))
            await asyncio.gather(first, second, third)

        asyncio.run(run_fragments())

        self.assertTrue(events[0].stopped)
        self.assertTrue(events[1].stopped)
        self.assertFalse(events[2].stopped)
        final_injected = "\n".join(self._request_text_parts(requests[-1]))
        self.assertIn("sylanne_user_message_fragments", final_injected)
        self.assertIn("我只是很纳闷 / 为啥你要问我 / 是从哪里看来的", final_injected)
        self.assertIn(
            "merged_intent=我只是很纳闷 为啥你要问我 是从哪里看来的",
            final_injected,
        )
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(assessment_calls), 1)
        self.assertGreaterEqual(len(saves), 1)

    def test_realtime_input_llm_gate_blocks_premature_emphasis_release_until_complete(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": True,
                "realtime_input_completion_llm_gate_enabled": True,
                "fast_assessor_provider_id": "provider",
                "realtime_input_completion_probe_delay_seconds": 0.01,
                "realtime_input_completion_max_wait_seconds": 4.0,
            },
        )
        clock = {"now": 7000.0}
        plugin._observed_now = lambda: clock["now"]
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        calls = []

        async def fake_provider_id(self, event):
            return "provider"

        async def fake_call_llm(self, *, provider_id, prompt, system_prompt):
            calls.append(prompt)
            complete = "人！！！" in prompt
            return SimpleNamespace(
                completion_text=(
                    '{"is_complete": true, "confidence": 0.97, "reason": "否定句补完为老人"}'
                    if complete
                    else '{"is_complete": false, "confidence": 0.9, "reason": "否定句还没补完"}'
                ),
            )

        bind_async(plugin, "_provider_id", fake_provider_id)
        bind_async(plugin, "_call_internal_assessor_llm", fake_call_llm)
        texts = ["我！", "不！", "是！", "老！", "年", "人！！！"]
        events = [
            FakeEvent("s-emphasis-fragments", message=text, sender_id="u1")
            for text in texts
        ]
        requests = [
            fake_request(session_id="s-emphasis-fragments", prompt=text)
            for text in texts
        ]

        async def run_fragments():
            tasks = []
            for index, (event, request) in enumerate(zip(events, requests)):
                tasks.append(asyncio.create_task(plugin.on_llm_request(event, request)))
                await asyncio.sleep(0.03)
                if index < len(texts) - 1:
                    clock["now"] += [1.5, 1.0, 1.8, 2.4, 1.9][index]
            await asyncio.gather(*tasks)

        asyncio.run(run_fragments())

        for event in events[:-1]:
            self.assertTrue(event.stopped)
        self.assertFalse(events[-1].stopped)
        final_injected = "\n".join(self._request_text_parts(requests[-1]))
        self.assertIn("sylanne_user_message_fragments", final_injected)
        self.assertIn("我！ / 不！ / 是！ / 老！ / 年 / 人！！！", final_injected)
        self.assertIn("merged_intent=我！ 不！ 是！ 老！ 年 人！！！", final_injected)
        self.assertGreaterEqual(len(calls), 4)
        self.assertEqual(len(assessment_calls), 1)
        self.assertGreaterEqual(len(saves), 1)

    def test_realtime_input_llm_incomplete_release_after_max_wait_when_user_stops(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": True,
                "realtime_input_completion_llm_gate_enabled": True,
                "fast_assessor_provider_id": "provider",
                "realtime_input_completion_probe_delay_seconds": 0.0,
                "realtime_input_completion_max_wait_seconds": 0.12,
            },
        )
        clock = {"now": 8000.0}
        plugin._observed_now = lambda: clock["now"]
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        calls = []

        async def fake_provider_id(self, event):
            return "provider"

        async def fake_call_llm(self, *, provider_id, prompt, system_prompt):
            calls.append(prompt)
            return SimpleNamespace(
                completion_text=(
                    '{"is_complete": false, "confidence": 0.91, '
                    '"reason": "仍像强调铺垫，但用户没有继续输入"}'
                ),
            )

        bind_async(plugin, "_provider_id", fake_provider_id)
        bind_async(plugin, "_call_internal_assessor_llm", fake_call_llm)
        texts = ["我！", "不！", "是！", "老！", "年", "人！！！"]
        events = [
            FakeEvent("s-incomplete-timeout-release", message=text, sender_id="u1")
            for text in texts
        ]
        requests = [
            fake_request(session_id="s-incomplete-timeout-release", prompt=text)
            for text in texts
        ]

        async def run_fragments():
            tasks = []
            for index, (event, request) in enumerate(zip(events, requests)):
                tasks.append(asyncio.create_task(plugin.on_llm_request(event, request)))
                clock["now"] += 0.4 + index * 0.1
                if index < len(events) - 1:
                    await asyncio.sleep(0.02)
            await asyncio.gather(*tasks)

        asyncio.run(run_fragments())

        self.assertFalse(events[-1].stopped)
        final_injected = "\n".join(self._request_text_parts(requests[-1]))
        self.assertIn("sylanne_user_message_fragments", final_injected)
        self.assertIn("我！ / 不！ / 是！ / 老！ / 年 / 人！！！", final_injected)
        self.assertGreaterEqual(len(calls), 1)
        self.assertEqual(len(assessment_calls), 1)
        self.assertGreaterEqual(len(saves), 1)

    def test_realtime_input_low_signal_followup_does_not_consume_history_shadow(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
            },
        )
        self._bind_common_state_hooks(plugin)
        plugin._record_realtime_assistant_history_shadow(
            "s-low-signal-shadow",
            full_text="刚才说的是插件的其他用户，不是恋爱关系里的别人。",
            input_epoch=1,
            message_parts=[
                {"text": "刚才说的是插件的其他用户。"},
            ],
            source="unit_test",
        )
        low_request = fake_request(session_id="s-low-signal-shadow", prompt="?")
        content_request = fake_request(
            session_id="s-low-signal-shadow",
            prompt="他们会怎么看这个插件",
        )

        async def run_requests():
            await plugin.on_llm_request(
                FakeEvent("s-low-signal-shadow", message="?", sender_id="u1"),
                low_request,
            )
            await plugin.on_llm_request(
                FakeEvent(
                    "s-low-signal-shadow",
                    message="他们会怎么看这个插件",
                    sender_id="u1",
                ),
                content_request,
            )

        asyncio.run(run_requests())

        low_injected = "\n".join(self._request_text_parts(low_request))
        content_injected = "\n".join(self._request_text_parts(content_request))
        self.assertNotIn("sylanne_realtime_assistant_history", low_injected)
        self.assertIn("sylanne_realtime_assistant_history", content_injected)
        self.assertIn("插件的其他用户", content_injected)

    def test_user_correction_suppresses_assistant_history_shadow(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
                "realtime_input_completion_probe_delay_seconds": 0.0,
                "realtime_input_completion_max_wait_seconds": 0.0,
            },
        )
        self._bind_common_state_hooks(plugin)
        plugin._record_realtime_assistant_history_shadow(
            "s-correction-shadow",
            full_text="哼，你是不是又在乱想，我才没有其他用户呢。",
            input_epoch=1,
            message_parts=[{"text": "哼，你是不是又在乱想。"}],
            source="unit_test",
        )
        request = fake_request(
            session_id="s-correction-shadow",
            prompt="不是，我是说插件的其他用户，你是从哪里看来的",
        )

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "s-correction-shadow",
                    message="不是，我是说插件的其他用户，你是从哪里看来的",
                    sender_id="u1",
                ),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertIn("sylanne_user_correction_context", injected)
        self.assertNotIn("sylanne_realtime_assistant_history", injected)
        self.assertIn("优先处理用户纠正", injected)

    def test_followup_clarification_gets_repetition_guard(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
            },
        )
        self._bind_common_state_hooks(plugin)
        plugin._record_realtime_assistant_history_shadow(
            "s-memory-clarification",
            full_text=(
                "原来你说的是那个具体的底层功能呀！那个模块就像我们的共同记忆库，"
                "帮我把琐碎的瞬间都沉淀下来。"
            ),
            input_epoch=1,
            message_parts=[
                {"text": "原来你说的是那个具体的底层功能呀！"},
                {"text": "那个模块就像我们的共同记忆库。"},
            ],
            source="unit_test",
        )
        request = fake_request(
            session_id="s-memory-clarification",
            prompt="我只是想好好确认一下嘛 我给你做的嵌入模型记忆模块",
        )

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "s-memory-clarification",
                    message="我只是想好好确认一下嘛 我给你做的嵌入模型记忆模块",
                    sender_id="u1",
                ),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        context_text = "\n".join(str(item) for item in request.contexts)
        self.assertIn("sylanne_user_correction_context", injected)
        self.assertIn("sylanne_history_reuse_guard", injected)
        self.assertIn("不要复述上一轮", injected)
        self.assertIn("二次澄清", injected)
        self.assertIn("原来你说的是那个具体的底层功能", context_text)

    def test_sleep_fact_correction_suppresses_repeated_no_sleep_guess(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
            },
        )
        self._bind_common_state_hooks(plugin)
        plugin._record_realtime_assistant_history_shadow(
            "s-sleep-correction",
            full_text="五点多的早起和四点多的没睡很难区分，你是刚起床还是根本就没睡呀？",
            input_epoch=1,
            message_parts=[
                {"text": "你是刚起床还是根本就没睡呀？"},
            ],
            source="unit_test",
        )
        request = fake_request(
            session_id="s-sleep-correction",
            prompt="我昨晚十点多睡的啦",
        )

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "s-sleep-correction",
                    message="我昨晚十点多睡的啦",
                    sender_id="u1",
                ),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertIn("sylanne_user_correction_context", injected)
        self.assertIn("我昨晚十点多睡的啦", injected)
        self.assertIn("不要再追问或暗示用户没睡", injected)
        self.assertNotIn("sylanne_realtime_assistant_history", injected)
        context_text = "\n".join(str(item) for item in request.contexts)
        self.assertIn("你是刚起床还是根本就没睡呀？", context_text)

    def test_recent_sleep_correction_is_carried_into_next_fragment_answer(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
            },
        )
        self._bind_common_state_hooks(plugin)
        plugin._record_realtime_assistant_history_shadow(
            "s-sleep-then-thesis",
            full_text="你今天是准备继续改论文，还是单纯来找我撒娇呀？",
            input_epoch=1,
            message_parts=[
                {"text": "你今天是准备继续改论文，还是单纯来找我撒娇呀？"},
            ],
            source="unit_test",
        )
        correction_request = fake_request(
            session_id="s-sleep-then-thesis",
            prompt="我昨晚十点多睡的啦",
        )
        thesis_request = fake_request(
            session_id="s-sleep-then-thesis",
            prompt="我今天打算改论文",
        )

        async def run_requests():
            await plugin.on_llm_request(
                FakeEvent(
                    "s-sleep-then-thesis",
                    message="我昨晚十点多睡的啦",
                    sender_id="u1",
                ),
                correction_request,
            )
            await plugin.on_llm_request(
                FakeEvent(
                    "s-sleep-then-thesis",
                    message="我今天打算改论文",
                    sender_id="u1",
                ),
                thesis_request,
            )

        asyncio.run(run_requests())

        injected = "\n".join(self._request_text_parts(thesis_request))
        self.assertIn("sylanne_active_agent_followup_merge", injected)
        self.assertIn("sylanne_user_correction_context", injected)
        self.assertIn("我昨晚十点多睡的啦", injected)
        self.assertIn("不要再追问或暗示用户没睡", injected)
        self.assertIn("merged_current_user=我昨晚十点多睡的啦 / 我今天打算改论文", injected)
        context_text = "\n".join(str(item) for item in thesis_request.contexts)
        self.assertIn("你今天是准备继续改论文", context_text)

    def test_short_scene_followup_keeps_recent_user_activity_context(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
                "realtime_input_completion_probe_delay_seconds": 0.0,
                "realtime_input_completion_max_wait_seconds": 0.0,
            },
        )
        clock = {"now": 3000.0}
        plugin._observed_now = lambda: clock["now"]
        self._bind_common_state_hooks(plugin)
        first_request = fake_request(
            session_id="s-user-scene-context",
            prompt="正在排队买蜜雪捏",
        )
        second_request = fake_request(
            session_id="s-user-scene-context",
            prompt="不过今天有点热",
        )
        third_request = fake_request(
            session_id="s-user-scene-context",
            prompt="我在外面",
        )

        async def run_scene_turns():
            await plugin.on_llm_request(
                FakeEvent(
                    "s-user-scene-context",
                    message="正在排队买蜜雪捏",
                    sender_id="u1",
                ),
                first_request,
            )
            plugin._discard_conversation_pending_response_epoch(
                "s-user-scene-context",
                1,
            )
            clock["now"] += 12.0
            await plugin.on_llm_request(
                FakeEvent(
                    "s-user-scene-context",
                    message="不过今天有点热",
                    sender_id="u1",
                ),
                second_request,
            )
            plugin._discard_conversation_pending_response_epoch(
                "s-user-scene-context",
                2,
            )
            plugin._record_realtime_assistant_history_shadow(
                "s-user-scene-context",
                full_text="你那边现在是晒得热，还是闷闷的那种热呀？",
                input_epoch=2,
                message_parts=[
                    {"text": "你那边现在是晒得热，还是闷闷的那种热呀？"},
                ],
                source="unit_test",
            )
            clock["now"] += 20.0
            await plugin.on_llm_request(
                FakeEvent(
                    "s-user-scene-context",
                    message="我在外面",
                    sender_id="u1",
                ),
                third_request,
            )

        asyncio.run(run_scene_turns())

        injected = "\n".join(self._request_text_parts(third_request))
        self.assertIn("sylanne_recent_user_scene_context", injected)
        self.assertIn("正在排队买蜜雪捏", injected)
        self.assertIn("不过今天有点热", injected)
        self.assertIn("current_user=我在外面", injected)
        self.assertIn("sylanne_realtime_pending_bot_question", injected)
        self.assertNotIn("sylanne_active_agent_followup_merge", injected)

    def test_short_answer_to_pending_question_skips_fragment_completion_gate(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": True,
                "realtime_input_completion_llm_gate_enabled": True,
                "fast_assessor_provider_id": "provider",
                "realtime_input_completion_probe_delay_seconds": 0.65,
                "realtime_input_completion_max_wait_seconds": 4.0,
            },
        )
        self._bind_common_state_hooks(plugin)
        plugin._record_realtime_assistant_history_shadow(
            "s-short-answer-no-gate",
            full_text="喝了杯什么呀？",
            input_epoch=1,
            message_parts=[{"text": "喝了杯什么呀？"}],
            source="unit_test",
        )
        waits = []

        async def fake_provider_id(self, event):
            return "provider"

        async def fail_call_llm(self, **kwargs):
            raise AssertionError("short answer should not call completion gate")

        async def fake_wait(self, session_key, payload, wait_seconds):
            waits.append(wait_seconds)
            return True

        bind_async(plugin, "_provider_id", fake_provider_id)
        bind_async(plugin, "_call_internal_assessor_llm", fail_call_llm)
        bind_async(plugin, "_wait_realtime_input_window_unchanged", fake_wait)
        request = fake_request(session_id="s-short-answer-no-gate", prompt="咖啡啊")

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent("s-short-answer-no-gate", message="咖啡啊", sender_id="u1"),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertFalse(getattr(request, "_sylanne_realtime_input_hold", False))
        self.assertEqual(waits, [])
        self.assertIn("sylanne_realtime_pending_bot_question", injected)
        self.assertIn("current_user_short_answer=咖啡啊", injected)

    def test_realtime_input_fragments_do_not_merge_across_speakers_or_timeout(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
            },
        )
        clock = {"now": 2000.0}
        plugin._observed_now = lambda: clock["now"]
        self._bind_common_state_hooks(plugin)
        first_request = fake_request(session_id="s-fragment-boundary", prompt="你")
        second_request = fake_request(session_id="s-fragment-boundary", prompt="是")
        late_request = fake_request(session_id="s-fragment-boundary", prompt="吗")

        async def run_boundaries():
            await plugin.on_llm_request(
                FakeEvent("s-fragment-boundary", message="你", sender_id="u1"),
                first_request,
            )
            clock["now"] += 0.4
            await plugin.on_llm_request(
                FakeEvent("s-fragment-boundary", message="是", sender_id="u2"),
                second_request,
            )
            clock["now"] += 8.0
            await plugin.on_llm_request(
                FakeEvent("s-fragment-boundary", message="吗", sender_id="u2"),
                late_request,
            )

        asyncio.run(run_boundaries())

        self.assertNotIn(
            "sylanne_user_message_fragments",
            "\n".join(self._request_text_parts(second_request)),
        )
        self.assertNotIn(
            "sylanne_user_message_fragments",
            "\n".join(self._request_text_parts(late_request)),
        )

    def test_observe_user_message_withdrawal_invalidates_pending_output(self):
        plugin = new_plugin()
        plugin._conversation_input_epoch = {"s-withdraw": 1}
        plugin._last_request_text = {"s-withdraw": "错字消息"}
        plugin._proactive_candidate_sessions = {
            "s-withdraw": {
                "session_key": "s-withdraw",
                "unified_msg_origin": "s-withdraw",
                "last_user_text_excerpt": "错字消息",
                "candidate_context_excerpt": "旧上下文",
            },
        }

        result = asyncio.run(
            plugin.observe_user_message_withdrawal(
                session_key="s-withdraw",
                message_id="m-100",
                reason="napcat_friend_recall",
            ),
        )

        self.assertEqual(result["input_epoch"], 2)
        self.assertTrue(plugin._conversation_reply_is_stale("s-withdraw", 1))
        self.assertNotIn("s-withdraw", plugin._last_request_text)
        candidate = plugin._proactive_candidate_sessions["s-withdraw"]
        self.assertEqual(candidate["last_user_text_excerpt"], "")
        self.assertEqual(candidate["last_withdrawn_message_id"], "m-100")

    def test_withdrawal_cancels_sleeping_realtime_dispatch_task(self):
        sent = []
        first_sent = asyncio.Event()

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                first_sent.set()
                return {"ok": True}

        plugin = new_plugin({"enable_realtime_chat": True, "enable_sticker_reaction": False})
        plugin.context = FakeContext()
        plugin._conversation_input_epoch = {"s-withdraw-cancel": 1}
        plan = {
            "session_key": "s-withdraw-cancel",
            "input_epoch": 1,
            "message_parts": [
                {"index": 0, "text": "old first", "delay_before_seconds": 0.0},
                {"index": 1, "text": "old withdrawn tail", "delay_before_seconds": 30.0},
            ],
        }

        async def run_withdrawal_cancel():
            send_task = asyncio.create_task(
                plugin._send_realtime_chat_plan(
                    FakeEvent("s-withdraw-cancel"),
                    plan,
                    source="unit_test",
                ),
            )
            await first_sent.wait()
            await asyncio.sleep(0.12)
            withdrawal = await plugin.observe_user_message_withdrawal(
                session_key="s-withdraw-cancel",
                message_id="m-200",
            )
            result = await asyncio.wait_for(send_task, timeout=0.25)
            return withdrawal, result

        withdrawal, result = asyncio.run(run_withdrawal_cancel())

        self.assertEqual(withdrawal["input_epoch"], 2)
        self.assertEqual(sent, [("s-withdraw-cancel", "message:old first")])
        self.assertEqual(result["message_count"], 1)
        self.assertEqual(result["interrupted_reason"], "user_interrupted")

    def test_napcat_recall_payload_is_parsed_from_raw_notice(self):
        plugin = new_plugin()
        event = SimpleNamespace(
            unified_msg_origin="group_123",
            message_obj=SimpleNamespace(
                raw_message={
                    "post_type": "notice",
                    "notice_type": "group_recall",
                    "group_id": 123,
                    "user_id": 456,
                    "operator_id": 789,
                    "message_id": 10001,
                },
            ),
        )

        payload = plugin._napcat_recall_payload(event)

        self.assertEqual(payload["notice_type"], "group_recall")
        self.assertEqual(payload["message_id"], "10001")
        self.assertEqual(payload["group_id"], "123")
        self.assertEqual(payload["operator_id"], "789")

    def test_observe_user_message_withdrawal_uses_napcat_notice_type_by_default(self):
        plugin = new_plugin()
        event = SimpleNamespace(
            unified_msg_origin="friend_456",
            raw_message={
                "post_type": "notice",
                "notice_type": "friend_recall",
                "user_id": 456,
                "message_id": 20002,
            },
        )

        result = asyncio.run(plugin.observe_user_message_withdrawal(event))

        self.assertEqual(result["session_key"], "friend_456")
        self.assertEqual(result["message_id"], "20002")
        self.assertEqual(result["reason"], "friend_recall")

    def test_napcat_recall_is_injected_for_next_llm_turn(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
            },
        )
        self._bind_common_state_hooks(plugin)
        plugin._last_request_text = {"s-recall-context": "用户刚才撤回前的消息"}
        recall_event = FakeEvent("s-recall-context", message="", platform_name="aiocqhttp")
        recall_event.raw_message = {
            "post_type": "notice",
            "notice_type": "friend_recall",
            "user_id": "u1",
            "message_id": "m-recalled",
        }
        recall_request = fake_request(session_id="s-recall-context", prompt="")
        next_request = fake_request(session_id="s-recall-context", prompt="我重新说一下")

        async def run_recall_then_next_turn():
            await plugin.on_llm_request(recall_event, recall_request)
            await plugin.on_llm_request(
                FakeEvent("s-recall-context", message="我重新说一下", sender_id="u1"),
                next_request,
            )

        asyncio.run(run_recall_then_next_turn())

        injected = "\n".join(self._request_text_parts(next_request))
        self.assertTrue(recall_event.stopped)
        self.assertTrue(recall_request._sylanne_control_event)
        self.assertIn("sylanne_user_message_withdrawal", injected)
        self.assertIn("m-recalled", injected)
        self.assertIn("用户刚才撤回前的消息", injected)

    def test_napcat_input_status_is_held_without_creating_user_turn(self):
        plugin = new_plugin({"enable_realtime_chat": True})
        event = FakeEvent("s-input-status", message="", platform_name="aiocqhttp")
        event.raw_message = {
            "post_type": "notice",
            "notice_type": "notify",
            "sub_type": "input_status",
            "status_text": "对方正在输入",
            "event_type": "1",
            "user_id": "u1",
        }
        request = fake_request(session_id="s-input-status", prompt="")

        asyncio.run(plugin.on_llm_request(event, request))

        self.assertTrue(event.stopped)
        self.assertTrue(request._sylanne_control_event)
        self.assertEqual(
            request._sylanne_default_response_stop_reason,
            "user_typing_status",
        )
        self.assertNotIn("s-input-status", plugin._conversation_input_epoch)
        self.assertIn("s-input-status", plugin._realtime_user_typing_until)

    def test_empty_input_event_holds_without_interrupting_realtime_dispatch(self):
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))
                return {"ok": True}

        plugin = new_plugin(
            {
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "realtime_empty_input_typing_hold_seconds": 0.02,
            },
        )
        plugin.context = FakeContext()
        plugin._conversation_input_epoch = {"s-empty-input": 1}
        plan = {
            "session_key": "s-empty-input",
            "input_epoch": 1,
            "message_parts": [
                {
                    "index": 0,
                    "text": "still sent after typing pause",
                    "delay_before_seconds": 0.05,
                },
            ],
        }

        async def run_empty_event_during_dispatch():
            send_task = asyncio.create_task(
                plugin._send_realtime_chat_plan(
                    FakeEvent("s-empty-input"),
                    plan,
                    source="unit_test",
                ),
            )
            await asyncio.sleep(0.01)
            event = FakeEvent("s-empty-input", message="", platform_name="aiocqhttp")
            request = fake_request(session_id="s-empty-input", prompt="")
            await plugin.on_llm_request(event, request)
            result = await asyncio.wait_for(send_task, timeout=1.0)
            return event, request, result

        event, request, result = asyncio.run(run_empty_event_during_dispatch())

        self.assertTrue(event.stopped)
        self.assertTrue(request._sylanne_control_event)
        self.assertEqual(
            request._sylanne_default_response_stop_reason,
            "user_typing_empty_event",
        )
        self.assertIn("typing_hold_until", request._sylanne_control_event_payload)
        self.assertEqual(plugin._conversation_input_epoch["s-empty-input"], 1)
        self.assertEqual(sent, [("s-empty-input", "message:still sent after typing pause")])
        self.assertNotIn("interrupted_reason", result)

    def test_empty_input_event_without_realtime_dispatch_does_not_create_typing_hold(self):
        plugin = new_plugin(
            {
                "enable_realtime_chat": True,
                "realtime_empty_input_typing_hold_seconds": 0.02,
            },
        )
        event = FakeEvent("s-empty-idle", message="", platform_name="aiocqhttp")
        request = fake_request(session_id="s-empty-idle", prompt="")

        asyncio.run(plugin.on_llm_request(event, request))

        self.assertTrue(event.stopped)
        self.assertTrue(request._sylanne_control_event)
        self.assertEqual(
            request._sylanne_default_response_stop_reason,
            "empty_input_event",
        )
        self.assertNotIn("typing_hold_until", request._sylanne_control_event_payload)
        self.assertNotIn("s-empty-idle", plugin._realtime_user_typing_until)
        self.assertNotIn("s-empty-idle", plugin._conversation_input_epoch)

    def test_observe_sticker_usage_stores_metadata_only(self):
        stored = {}

        async def fake_get(self, key, default=None):
            return stored.get(key, default)

        async def fake_put(self, key, value):
            stored[key] = value

        plugin = new_plugin()
        bind_async(plugin, "get_kv_data", fake_get)
        bind_async(plugin, "put_kv_data", fake_put)

        result = asyncio.run(
            plugin.observe_sticker_usage(
                "s-sticker",
                {
                    "url": "https://example.test/a.gif",
                    "name": "笑死",
                    "binary": "not stored",
                    "interest_score": 0.9,
                },
            ),
        )

        self.assertTrue(result["committed"])
        self.assertEqual(result["memory_count"], 1)
        saved = next(iter(stored.values()))[0]
        self.assertEqual(saved["url"], "https://example.test/a.gif")
        self.assertNotIn("binary", saved)


if __name__ == "__main__":
    unittest.main()
