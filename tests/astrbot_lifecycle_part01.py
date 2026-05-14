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


class AstrBotLifecyclePart01(AstrBotLifecycleTests):
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


    def test_recent_user_scene_context_survives_over_budget_history_when_realtime_disabled(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": False,
                "use_llm_assessor": False,
                "state_injection_request_budget_chars": 1200,
                "state_injection_reserved_chars": 200,
            },
        )
        self._bind_common_state_hooks(plugin)

        async def run_scene_turns():
            await plugin.on_llm_request(
                FakeEvent("s-scene-budget", message="queueing milk tea marker", sender_id="u1"),
                fake_request(session_id="s-scene-budget", prompt="queueing milk tea marker"),
            )
            plugin._conversation_pending_response_epochs.clear()
            plugin._active_agent_pending_user_turns.clear()
            await plugin.on_llm_request(
                FakeEvent("s-scene-budget", message="hot outside marker", sender_id="u1"),
                fake_request(session_id="s-scene-budget", prompt="hot outside marker"),
            )
            plugin._conversation_pending_response_epochs.clear()
            plugin._active_agent_pending_user_turns.clear()
            request = fake_request(session_id="s-scene-budget", prompt="outside now")
            request.contexts = [
                {"role": "user", "content": "very-long-history-" + ("x" * 5000)},
            ]
            await plugin.on_llm_request(
                FakeEvent("s-scene-budget", message="outside now", sender_id="u1"),
                request,
            )
            return request

        request = asyncio.run(run_scene_turns())

        injected = "\n".join(self._request_text_parts(request))
        self.assertIn("sylanne_recent_user_scene_context", injected)
        self.assertIn("queueing milk tea marker", injected)
        self.assertIn("hot outside marker", injected)
        self.assertIn("current_user=outside now", injected)


    def test_active_followup_merge_survives_over_budget_tool_request(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": False,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
                "state_injection_request_budget_chars": 1200,
                "state_injection_reserved_chars": 200,
            },
        )
        self._bind_common_state_hooks(plugin)

        async def run_followup():
            await plugin.on_llm_request(
                FakeEvent(
                    "s-followup-budget",
                    message="edit the quoted image face in the same geometric style",
                    sender_id="u1",
                ),
                fake_request(
                    session_id="s-followup-budget",
                    prompt="edit the quoted image face in the same geometric style",
                ),
            )
            request = fake_request(session_id="s-followup-budget", prompt="so where is the image")
            request.contexts = [
                {"role": "user", "content": "very-long-history-" + ("x" * 5000)},
            ]
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
            await plugin.on_llm_request(
                FakeEvent("s-followup-budget", message="so where is the image", sender_id="u1"),
                request,
            )
            return request

        request = asyncio.run(run_followup())

        injected = "\n".join(self._request_text_parts(request))
        self.assertIn("sylanne_active_agent_followup_merge", injected)
        self.assertIn("edit the quoted image face", injected)
        self.assertIn("so where is the image", injected)
        self.assertIn("merged_current_user=", injected)


    def test_realtime_shadow_survives_over_budget_history(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": False,
                "use_llm_assessor": False,
                "state_injection_request_budget_chars": 1200,
                "state_injection_reserved_chars": 200,
            },
        )
        self._bind_common_state_hooks(plugin)
        plugin._record_realtime_assistant_history_shadow(
            "s-shadow-budget",
            full_text="assistant shadow marker: keep editing the original quoted image",
            input_epoch=1,
            message_parts=[
                {"text": "assistant shadow marker: keep editing the original quoted image"},
            ],
            source="unit_test",
        )
        request = fake_request(session_id="s-shadow-budget", prompt="what did you mean")
        request.contexts = [
            {"role": "user", "content": "very-long-history-" + ("x" * 5000)},
        ]

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent("s-shadow-budget", message="what did you mean", sender_id="u1"),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertIn("sylanne_realtime_assistant_history", injected)
        self.assertIn("assistant shadow marker", injected)


    def test_current_event_time_uses_astrbot_timezone(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": True,
                "use_llm_assessor": False,
                "state_injection_max_added_chars": 2400,
                "state_injection_max_parts": 8,
            },
        )
        self._bind_common_state_hooks(plugin)
        plugin.context = SimpleNamespace(
            get_config=lambda *args, **kwargs: {"timezone": "Asia/Shanghai"},
        )
        request = fake_request(session_id="s-event-time", prompt="still editing thesis")

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "s-event-time",
                    message="still editing thesis",
                    sender_id="u1",
                    timestamp=1778700459.0,
                ),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        self.assertIn("sylanne_current_event_time", injected)
        self.assertIn("Asia/Shanghai", injected)
        self.assertIn("2026-05-14 03:27:39 +08:00", injected)


    def test_realtime_delivery_context_carries_event_time(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": True,
                "use_llm_assessor": False,
                "state_injection_max_added_chars": 2400,
                "state_injection_max_parts": 8,
            },
        )
        self._bind_common_state_hooks(plugin)
        event = FakeEvent(
            "s-realtime-time",
            message="still editing thesis",
            sender_id="u1",
            timestamp=1778700459.0,
        )
        plugin.context = SimpleNamespace(
            get_config=lambda *args, **kwargs: {"timezone": "Asia/Shanghai"},
        )
        event_time = plugin._conversation_time_payload(1778700459.0, event=event)

        envelope = plugin._build_realtime_delivery_envelope_text(
            "assistant reply about the thesis",
            session_key="s-realtime-time",
            input_epoch=3,
            message_parts=[{"text": "assistant reply about the thesis"}],
            event_time=event_time,
        )
        self.assertIn("event_local_time=2026-05-14 03:27:39 +08:00", envelope)
        self.assertIn("timezone=Asia/Shanghai", envelope)
        self.assertIn("disabled or removed", envelope)

        plugin._record_realtime_assistant_history_shadow(
            "s-realtime-time",
            full_text="assistant reply about the thesis",
            input_epoch=3,
            message_parts=[{"text": "assistant reply about the thesis"}],
            source="unit_test",
            event_time=event_time,
        )
        shadow_request = fake_request(session_id="s-realtime-time", prompt="what did you mean")
        plugin._append_realtime_assistant_history_shadow_if_any(
            shadow_request,
            "s-realtime-time",
            budget=None,
            current_user_text="what did you mean",
        )
        shadow_context = "\n".join(self._request_text_parts(shadow_request))
        self.assertIn("event_local_time=2026-05-14 03:27:39 +08:00", shadow_context)
        self.assertIn("timezone=Asia/Shanghai", shadow_context)

        plugin._record_interrupted_reply_breakpoint(
            "s-realtime-time",
            reason="user_interrupted",
            input_epoch=4,
            full_text="interrupted assistant reply",
            unsent_parts=["interrupted assistant reply"],
            event_time=event_time,
        )
        breakpoint_request = fake_request(session_id="s-realtime-time", prompt="continue")
        plugin._append_interrupted_reply_breakpoint_if_any(
            breakpoint_request,
            "s-realtime-time",
            budget=None,
        )
        breakpoint_context = "\n".join(self._request_text_parts(breakpoint_request))
        self.assertIn("event_local_time=2026-05-14 03:27:39 +08:00", breakpoint_context)
        self.assertIn("timezone=Asia/Shanghai", breakpoint_context)

        plugin._start_realtime_chat_active_dispatch(
            "s-realtime-time",
            input_epoch=5,
            full_text="dispatching assistant reply",
            source="unit_test",
            event_time=event_time,
        )
        active_request = fake_request(session_id="s-realtime-time", prompt="wait")
        plugin._append_realtime_chat_active_dispatch_if_any(
            active_request,
            "s-realtime-time",
            budget=None,
        )
        active_context = "\n".join(self._request_text_parts(active_request))
        self.assertIn("trigger_event_local_time=2026-05-14 03:27:39 +08:00", active_context)
        self.assertIn("trigger_timezone=Asia/Shanghai", active_context)


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
