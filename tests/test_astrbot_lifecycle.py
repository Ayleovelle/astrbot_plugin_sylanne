import asyncio
import collections
import time
import unittest
from types import SimpleNamespace

try:
    from tests.test_command_tools import bind_async, install_astrbot_stubs, new_plugin
except ModuleNotFoundError:
    from test_command_tools import bind_async, install_astrbot_stubs, new_plugin


class FakeEvent:
    def __init__(self, session_id="session-1", message="hello", sender_id=None, sender_name=None):
        self.unified_msg_origin = session_id
        self.message_str = message
        self._sender_id = sender_id
        self._sender_name = sender_name

    def get_sender_id(self):
        return self._sender_id or ""

    def get_sender_name(self):
        return self._sender_name or ""


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

        async def fake_load_humanlike(self, session_key, *, now=None):
            seen_now.append(("humanlike", now))
            state = HumanlikeState.initial()
            state.updated_at = 1.0
            return state

        async def fake_load_lifelike(self, session_key, *, now=None):
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

        async def fake_load_moral(self, session_key, *, now=None):
            seen_now.append(("moral", now))
            state = MoralRepairState.initial()
            state.updated_at = 1.0
            return state

        async def fake_load_fallibility(self, session_key, *, now=None):
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
        self.assertEqual(len(request.extra_user_content_parts), 1)
        self.assertIn("bot_emotion_state", request.extra_user_content_parts[0].text)
        self.assertIn('detail="compact"', request.extra_user_content_parts[0].text)
        self.assertIn("get_bot_emotion_state", request.extra_user_content_parts[0].text)
        self.assertLess(len(request.extra_user_content_parts[0].text), 700)

    def test_state_injection_full_mode_keeps_verbose_emotion_fragment(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "state_injection_detail": "full",
            },
        )
        saves = []
        self._bind_common_state_hooks(plugin, saves=saves)
        request = fake_request(prompt="hello")

        asyncio.run(plugin.on_llm_request(FakeEvent("s-post-full"), request))

        self.assertEqual(saves, [])
        self.assertEqual(len(request.extra_user_content_parts), 1)
        text = request.extra_user_content_parts[0].text
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

    def test_full_state_injection_falls_back_to_compact_under_added_budget(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "state_injection_detail": "full",
                "state_injection_request_budget_chars": 8000,
                "state_injection_reserved_chars": 500,
                "state_injection_max_added_chars": 700,
            },
        )
        self._bind_common_state_hooks(plugin)
        request = fake_request(session_id="s-full-budget", prompt="hello")

        asyncio.run(plugin.on_llm_request(FakeEvent("s-full-budget"), request))

        self.assertEqual(len(request.extra_user_content_parts), 1)
        text = request.extra_user_content_parts[0].text
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

        asyncio.run(plugin.on_llm_response(FakeEvent("s-both"), response))

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

        started = time.perf_counter()
        asyncio.run(
            plugin.on_llm_response(
                FakeEvent("s-moral-overlap"),
                SimpleNamespace(completion_text="I am sorry and will repair it."),
            ),
        )
        elapsed = time.perf_counter() - started

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

    def test_background_post_assessment_parallelizes_same_session_assessments(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "background_post_assessment": True,
                "background_post_max_workers": 2,
            },
        )
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
            while len(started_texts) < 2:
                await asyncio.sleep(0)
            self.assertEqual(started_texts, ["reply-1", "reply-2"])
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

    def test_background_post_commit_failure_retries_and_preserves_following_order(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "background_post_assessment": True,
                "background_post_queue_checkpoint_enabled": True,
                "background_post_max_workers": 3,
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

    def test_background_post_assessment_handles_large_burst_with_five_workers(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "background_post_assessment": True,
                "background_post_max_workers": 5,
                "background_post_queue_checkpoint_enabled": False,
            },
        )
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
            self.assertLessEqual(
                diagnostics["background_post_assessment"]["active_workers"],
                5,
            )
            await asyncio.wait_for(next(iter(plugin._background_tasks)), timeout=2.0)

        asyncio.run(run_burst())

        self.assertEqual(len(assessment_calls), 50)
        self.assertEqual(
            [state.label for _, state in saves],
            [f"reply-{index:02d}" for index in range(50)],
        )
        self.assertLessEqual(max_active, 5)
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
        self.assertTrue(
            any("get_bot_group_atmosphere_state" in text for text in texts),
        )
        self.assertGreaterEqual(
            group_saves[0][1].values["bot_attention"],
            0.29,
        )

    def test_group_atmosphere_join_cooldown_persists_even_in_pre_timing(self):
        plugin = new_plugin(
            {
                "assessment_timing": "pre",
                "group_atmosphere_join_cooldown_turns": 2,
                "group_atmosphere_join_cooldown_seconds": 45.0,
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
        self.assertEqual(payload["cooldown"]["cooldown_remaining_turns"], 2)

    def test_group_atmosphere_diff_injection_sends_small_no_change_fragment(self):
        from group_atmosphere_engine import GroupAtmosphereState

        plugin = new_plugin(
            {
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
        asyncio.run(plugin.on_llm_response(FakeEvent("s-bad"), response))

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
        texts = [part.text for part in request.extra_user_content_parts]
        self.assertEqual(len(texts), 1)
        self.assertIn("bot_emotion_state", texts[0])
        self.assertNotIn("simulated humanlike-state", texts[0])

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
        texts = [part.text for part in request.extra_user_content_parts]
        self.assertEqual(len(texts), 1)
        self.assertIn("bot_emotion_state", texts[0])
        self.assertNotIn("lifelike common-ground", texts[0])

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

        texts = [part.text for part in request.extra_user_content_parts]
        self.assertEqual(len(texts), 2)
        self.assertIn("bot_emotion_state", texts[0])
        self.assertIn("bot_auxiliary_state", texts[1])
        self.assertIn("get_bot_lifelike_learning_state", texts[1])

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
        texts = [part.text for part in request.extra_user_content_parts]
        self.assertEqual(len(texts), 1)
        self.assertIn("bot_emotion_state", texts[0])
        self.assertNotIn("fallibility-state modulation", texts[0])

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

        texts = [part.text for part in request.extra_user_content_parts]
        self.assertEqual(len(texts), 2)
        self.assertIn("bot_emotion_state", texts[0])
        self.assertIn("bot_auxiliary_state", texts[1])
        self.assertIn("get_bot_fallibility_state", texts[1])

    def test_auxiliary_state_injection_full_mode_keeps_legacy_fragments(self):
        from lifelike_learning_engine import LifelikeLearningState

        plugin = new_plugin(
            {
                "assessment_timing": "post",
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

        texts = [part.text for part in request.extra_user_content_parts]
        self.assertEqual(len(texts), 2)
        self.assertIn("lifelike common-ground", texts[1])
        self.assertNotIn("bot_auxiliary_state", texts[1])

    def test_auxiliary_state_injection_off_skips_auxiliary_fragments(self):
        from lifelike_learning_engine import LifelikeLearningState

        plugin = new_plugin(
            {
                "assessment_timing": "post",
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

        texts = [part.text for part in request.extra_user_content_parts]
        self.assertEqual(len(texts), 1)
        self.assertIn("bot_emotion_state", texts[0])

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
                "enable_personality_drift": True,
                "personality_drift_injection_strength": 0.0,
                "personality_drift_event_threshold": 0.01,
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
        texts = [part.text for part in request.extra_user_content_parts]
        self.assertEqual(len(texts), 1)
        self.assertNotIn("personality drift modulation", texts[0])

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

        texts = [part.text for part in request.extra_user_content_parts]
        self.assertEqual(len(texts), 2)
        self.assertIn("bot_emotion_state", texts[0])
        self.assertIn("bot_auxiliary_state", texts[1])
        self.assertIn("get_bot_personality_drift_state", texts[1])
        self.assertNotIn("personality drift modulation", texts[1])

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


if __name__ == "__main__":
    unittest.main()
