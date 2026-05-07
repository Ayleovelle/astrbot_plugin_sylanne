import asyncio
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

        async def fake_load_state(self, session_key, persona_profile=None):
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

    def test_invalid_assessment_timing_falls_back_to_both(self):
        plugin = new_plugin({"assessment_timing": "bad-value"})
        saves, assessment_calls = self._bind_common_state_hooks(plugin)
        request = fake_request(session_id="s-bad", prompt="request text")
        response = SimpleNamespace(completion_text="assistant text")

        asyncio.run(plugin.on_llm_request(FakeEvent("s-bad"), request))
        asyncio.run(plugin.on_llm_response(FakeEvent("s-bad"), response))

        self.assertEqual(plugin._assessment_timing(), "both")
        self.assertEqual(len(saves), 2)
        self.assertEqual(
            [call["phase"] for call in assessment_calls],
            ["pre_response", "post_response"],
        )

    def test_on_llm_response_ignores_blank_completion(self):
        plugin = new_plugin({"assessment_timing": "both"})
        self._bind_common_state_hooks(plugin)

        async def fail_if_assessed(self, **kwargs):
            raise AssertionError("blank completion must not be assessed")

        async def fail_if_saved(self, session_key, state):
            raise AssertionError("blank completion must not be saved")

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

        async def fake_load_humanlike_state(self, session_key):
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


if __name__ == "__main__":
    unittest.main()
