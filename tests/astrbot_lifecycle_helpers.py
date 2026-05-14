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
        timestamp=None,
    ):
        self.unified_msg_origin = session_id
        self.message_str = message
        self._sender_id = sender_id
        self._sender_name = sender_name
        self._platform_name = platform_name
        self._platform_id = platform_id
        self._group_id = group_id
        self.timestamp = timestamp
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


# 公共夹具留在这里，生命周期测试正文按主题分片，避免单文件继续膨胀。
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

    def _bind_background_worker_environment(
        self,
        plugin,
        *,
        level="normal",
        worker_cap=6,
        cpu=0.12,
        memory=0.22,
        now=1000.0,
    ):
        plugin._test_now = float(now)

        def fake_now(self):
            return float(getattr(self, "_test_now", now))

        def fake_resource_pressure(self):
            unknown = level == "unknown" or (cpu is None and memory is None)
            combined = max(
                [
                    ratio
                    for ratio in (cpu, memory)
                    if isinstance(ratio, (int, float))
                ],
                default=0.0,
            )
            reason = "environment_pressure_unknown" if unknown else f"environment_pressure_{level}"
            return {
                "cpu_load_ratio": cpu,
                "cpu_source": "unit_test",
                "memory_load_ratio": memory,
                "memory_source": "unit_test",
                "combined_load_ratio": combined,
                "unknown": unknown,
                "level": level,
                "worker_cap": worker_cap,
                "reason": reason,
                "sampled_at": self._observed_now(),
            }

        plugin._observed_now = types.MethodType(fake_now, plugin)
        plugin._background_post_resource_pressure = types.MethodType(
            fake_resource_pressure,
            plugin,
        )

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

