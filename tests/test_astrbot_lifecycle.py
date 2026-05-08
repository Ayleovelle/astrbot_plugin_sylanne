import asyncio
import time
import unittest
from types import SimpleNamespace

try:
    from tests.test_command_tools import bind_async, install_astrbot_stubs, new_plugin
except ModuleNotFoundError:
    from test_command_tools import bind_async, install_astrbot_stubs, new_plugin


class FakeEvent:
    def __init__(self, session_id="session-1", message="hello"):
        self.unified_msg_origin = session_id
        self.message_str = message


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
        self.assertIn("lifelike common-ground", texts[1])

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
        self.assertIn("fallibility-state modulation", texts[1])

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
        self.assertIn("personality drift modulation", texts[1])

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
