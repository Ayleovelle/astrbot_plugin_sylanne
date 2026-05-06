import asyncio
import sys
import types
import unittest
from types import SimpleNamespace

from public_api import (
    EMOTION_MEMORY_SCHEMA_VERSION,
    PSYCHOLOGICAL_SCREENING_SCHEMA_VERSION,
    get_emotion_service,
)


class FakeContext:
    def __init__(self, metadata):
        self.metadata = metadata

    def get_registered_star(self, name):
        if name == "astrbot_plugin_emotional_state":
            return self.metadata
        return None


class FakeEmotionService:
    emotion_api_version = "1.0"
    emotion_schema_version = "astrbot.emotion_state.v2"
    emotion_memory_schema_version = "astrbot.emotion_memory.v1"
    psychological_screening_schema_version = "astrbot.psychological_screening.v1"

    async def get_emotion_snapshot(self, *args, **kwargs):
        return {}

    async def get_emotion_state(self, *args, **kwargs):
        return {}

    async def get_emotion_values(self, *args, **kwargs):
        return {}

    async def get_emotion_consequences(self, *args, **kwargs):
        return {}

    async def get_emotion_relationship(self, *args, **kwargs):
        return {}

    async def get_emotion_prompt_fragment(self, *args, **kwargs):
        return ""

    async def build_emotion_memory_payload(self, *args, **kwargs):
        return {}

    async def observe_emotion_text(self, *args, **kwargs):
        return {}

    async def get_psychological_screening_snapshot(self, *args, **kwargs):
        return {}

    async def get_psychological_screening_values(self, *args, **kwargs):
        return {}

    async def observe_psychological_text(self, *args, **kwargs):
        return {}

    async def simulate_psychological_update(self, *args, **kwargs):
        return {}

    async def reset_psychological_screening_state(self, *args, **kwargs):
        return True

    async def simulate_emotion_update(self, *args, **kwargs):
        return {}

    async def reset_emotion_state(self, *args, **kwargs):
        return True


class PublicApiTests(unittest.TestCase):
    def test_get_emotion_service_returns_activated_plugin(self):
        plugin = FakeEmotionService()
        context = FakeContext(SimpleNamespace(activated=True, star_cls=plugin))
        self.assertIs(get_emotion_service(context), plugin)

    def test_get_emotion_service_rejects_inactive_plugin(self):
        plugin = FakeEmotionService()
        context = FakeContext(SimpleNamespace(activated=False, star_cls=plugin))
        self.assertIsNone(get_emotion_service(context))

    def test_get_emotion_service_rejects_incomplete_plugin(self):
        context = FakeContext(SimpleNamespace(activated=True, star_cls=object()))
        self.assertIsNone(get_emotion_service(context))

    def test_memory_schema_constant_is_exported(self):
        self.assertEqual(EMOTION_MEMORY_SCHEMA_VERSION, "astrbot.emotion_memory.v1")

    def test_psychological_screening_schema_constant_is_exported(self):
        self.assertEqual(
            PSYCHOLOGICAL_SCREENING_SCHEMA_VERSION,
            "astrbot.psychological_screening.v1",
        )

    def test_get_emotion_service_rejects_plugin_without_memory_payload_api(self):
        class OldEmotionService(FakeEmotionService):
            build_emotion_memory_payload = None

        context = FakeContext(
            SimpleNamespace(activated=True, star_cls=OldEmotionService()),
        )
        self.assertIsNone(get_emotion_service(context))

    def test_get_emotion_service_rejects_plugin_without_psychological_api(self):
        class OldEmotionService(FakeEmotionService):
            observe_psychological_text = None

        context = FakeContext(
            SimpleNamespace(activated=True, star_cls=OldEmotionService()),
        )
        self.assertIsNone(get_emotion_service(context))


class MemoryPayloadPublicApiTests(unittest.TestCase):
    def _install_astrbot_stubs(self):
        def passthrough_decorator(*args, **kwargs):
            def decorate(func):
                return func

            return decorate

        class FakeFilter:
            on_llm_request = staticmethod(passthrough_decorator)
            on_llm_response = staticmethod(passthrough_decorator)
            llm_tool = staticmethod(passthrough_decorator)
            command = staticmethod(passthrough_decorator)

        class FakeTextPart:
            def __init__(self, text=""):
                self.text = text

            def mark_as_temp(self):
                return self

        astrbot = types.ModuleType("astrbot")
        api = types.ModuleType("astrbot.api")
        api.AstrBotConfig = dict
        api.logger = SimpleNamespace(debug=lambda *args, **kwargs: None)

        event = types.ModuleType("astrbot.api.event")
        event.AstrMessageEvent = object
        event.filter = FakeFilter

        provider = types.ModuleType("astrbot.api.provider")
        provider.LLMResponse = object
        provider.ProviderRequest = object

        star = types.ModuleType("astrbot.api.star")
        star.Context = object

        class FakeStar:
            def __init__(self, context=None):
                self.context = context

        star.Star = FakeStar
        star.register = passthrough_decorator

        core = types.ModuleType("astrbot.core")
        agent = types.ModuleType("astrbot.core.agent")
        message = types.ModuleType("astrbot.core.agent.message")
        message.TextPart = FakeTextPart

        sys.modules.setdefault("astrbot", astrbot)
        sys.modules.setdefault("astrbot.api", api)
        sys.modules.setdefault("astrbot.api.event", event)
        sys.modules.setdefault("astrbot.api.provider", provider)
        sys.modules.setdefault("astrbot.api.star", star)
        sys.modules.setdefault("astrbot.core", core)
        sys.modules.setdefault("astrbot.core.agent", agent)
        sys.modules.setdefault("astrbot.core.agent.message", message)

    def test_plugin_method_uses_explicit_session_key_without_writing_state(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState
        from main import EmotionalStatePlugin

        calls = []

        async def fake_load_state(self, session_key, persona_profile=None):
            calls.append((session_key, persona_profile))
            state = EmotionState.initial()
            state.label = "calm"
            state.updated_at = 10.0
            return state

        original_load_state = EmotionalStatePlugin._load_state
        original_save_state = EmotionalStatePlugin._save_state
        EmotionalStatePlugin._load_state = fake_load_state
        EmotionalStatePlugin._save_state = (
            lambda self, session_key, state: (_ for _ in ()).throw(
                AssertionError("memory payload must be read-only"),
            )
        )
        try:
            plugin = EmotionalStatePlugin.__new__(EmotionalStatePlugin)
            plugin.config = {}
            payload = asyncio.run(
                plugin.build_emotion_memory_payload(
                    session_key="livingmemory:user-1",
                    memory={"text": "memory"},
                    source="livingmemory",
                    written_at=20.0,
                ),
            )
        finally:
            EmotionalStatePlugin._load_state = original_load_state
            EmotionalStatePlugin._save_state = original_save_state

        self.assertEqual(calls[0][0], "livingmemory:user-1")
        self.assertEqual(payload["session_key"], "livingmemory:user-1")
        self.assertEqual(payload["emotion_at_write"]["label"], "calm")
        self.assertEqual(payload["emotion_at_write"]["written_at"], 20.0)
        self.assertEqual(payload["memory"]["text"], "memory")

    def test_low_reasoning_mode_uses_short_prompt_and_context_limit(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState, build_persona_profile
        from main import EmotionalStatePlugin
        from prompts import LOW_REASONING_ASSESSOR_SYSTEM_PROMPT

        captured = {}

        class FakeContext:
            async def llm_generate(self, **kwargs):
                captured.update(kwargs)
                return SimpleNamespace(
                    completion_text=(
                        '{"label":"calm","dimensions":{"valence":0.1},'
                        '"confidence":0.8,"appraisal":{},"reason":"ok"}'
                    ),
                )

        async def fake_provider_id(self, event):
            return "provider"

        original_provider_id = EmotionalStatePlugin._provider_id
        EmotionalStatePlugin._provider_id = fake_provider_id
        try:
            plugin = EmotionalStatePlugin.__new__(EmotionalStatePlugin)
            plugin.config = {
                "low_reasoning_friendly_mode": True,
                "max_context_chars": 5000,
                "low_reasoning_max_context_chars": 60,
            }
            plugin.context = FakeContext()
            observation = asyncio.run(
                plugin._assess_emotion(
                    event=SimpleNamespace(unified_msg_origin="s1"),
                    phase="pre_response",
                    previous_state=EmotionState.initial(),
                    persona_profile=build_persona_profile(
                        persona_id="p",
                        name="p",
                        text="谨慎",
                    ),
                    context_text="A" * 200,
                    current_text="B" * 200,
                ),
            )
        finally:
            EmotionalStatePlugin._provider_id = original_provider_id

        self.assertEqual(captured["system_prompt"], LOW_REASONING_ASSESSOR_SYSTEM_PROMPT)
        self.assertIn("低推理模型友好模式", captured["prompt"])
        self.assertNotIn("A" * 80, captured["prompt"])
        self.assertNotIn("B" * 80, captured["prompt"])
        self.assertEqual(observation.label, "calm")

    def test_low_reasoning_mode_is_disabled_by_default(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState, build_persona_profile
        from main import EmotionalStatePlugin
        from prompts import ASSESSOR_SYSTEM_PROMPT

        captured = {}

        class FakeContext:
            async def llm_generate(self, **kwargs):
                captured.update(kwargs)
                return SimpleNamespace(
                    completion_text=(
                        '{"label":"neutral","dimensions":{"valence":0.0},'
                        '"confidence":0.7,"appraisal":{},"reason":"ok"}'
                    ),
                )

        async def fake_provider_id(self, event):
            return "provider"

        original_provider_id = EmotionalStatePlugin._provider_id
        EmotionalStatePlugin._provider_id = fake_provider_id
        try:
            plugin = EmotionalStatePlugin.__new__(EmotionalStatePlugin)
            plugin.config = {}
            plugin.context = FakeContext()
            observation = asyncio.run(
                plugin._assess_emotion(
                    event=SimpleNamespace(unified_msg_origin="s1"),
                    phase="pre_response",
                    previous_state=EmotionState.initial(),
                    persona_profile=build_persona_profile(
                        persona_id="p",
                        name="p",
                        text="谨慎",
                    ),
                    context_text="ctx",
                    current_text="text",
                ),
            )
        finally:
            EmotionalStatePlugin._provider_id = original_provider_id

        self.assertEqual(captured["system_prompt"], ASSESSOR_SYSTEM_PROMPT)
        self.assertNotIn("低推理模型友好模式", captured["prompt"])
        self.assertIn("citation_ids", captured["prompt"])
        self.assertEqual(observation.label, "neutral")

    def test_psychological_observe_is_disabled_by_default_for_commits(self):
        self._install_astrbot_stubs()
        from main import EmotionalStatePlugin
        from psychological_screening import PsychologicalScreeningEngine

        plugin = EmotionalStatePlugin.__new__(EmotionalStatePlugin)
        plugin.config = {}
        plugin.psychological_engine = PsychologicalScreeningEngine()
        plugin._psychological_memory_cache = {}
        payload = asyncio.run(
            plugin.observe_psychological_text(
                session_key="s1",
                text="我压力很大",
                commit=True,
            ),
        )
        self.assertFalse(payload["enabled"])
        self.assertFalse(payload["diagnostic"])

    def test_psychological_observe_can_commit_when_enabled(self):
        self._install_astrbot_stubs()
        from main import EmotionalStatePlugin
        from psychological_screening import PsychologicalScreeningEngine

        saved = []

        async def fake_load(self, session_key):
            from psychological_screening import PsychologicalScreeningState

            return PsychologicalScreeningState.initial()

        async def fake_save(self, session_key, state):
            saved.append((session_key, state))

        original_load = EmotionalStatePlugin._load_psychological_state
        original_save = EmotionalStatePlugin._save_psychological_state
        EmotionalStatePlugin._load_psychological_state = fake_load
        EmotionalStatePlugin._save_psychological_state = fake_save
        try:
            plugin = EmotionalStatePlugin.__new__(EmotionalStatePlugin)
            plugin.config = {"enable_psychological_screening": True}
            plugin.psychological_engine = PsychologicalScreeningEngine()
            payload = asyncio.run(
                plugin.observe_psychological_text(
                    session_key="s1",
                    text="我焦虑到睡不着",
                    commit=True,
                    observed_at=1000.0,
                ),
            )
        finally:
            EmotionalStatePlugin._load_psychological_state = original_load
            EmotionalStatePlugin._save_psychological_state = original_save

        self.assertEqual(saved[0][0], "s1")
        self.assertGreater(payload["values"]["anxiety_tension"], 0.0)
        self.assertFalse(payload["diagnostic"])


if __name__ == "__main__":
    unittest.main()
