import asyncio
import sys
import types
import unittest
from types import SimpleNamespace

from public_api import (
    EMOTION_MEMORY_SCHEMA_VERSION,
    HUMANLIKE_STATE_SCHEMA_VERSION,
    PSYCHOLOGICAL_SCREENING_SCHEMA_VERSION,
    get_emotion_service,
    get_humanlike_service,
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

    async def inject_emotion_context(self, *args, **kwargs):
        return None

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


class FakeHumanlikeService(FakeEmotionService):
    humanlike_state_schema_version = "astrbot.humanlike_state.v1"

    async def get_humanlike_snapshot(self, *args, **kwargs):
        return {}

    async def get_humanlike_values(self, *args, **kwargs):
        return {}

    async def get_humanlike_prompt_fragment(self, *args, **kwargs):
        return ""

    async def observe_humanlike_text(self, *args, **kwargs):
        return {}

    async def simulate_humanlike_update(self, *args, **kwargs):
        return {}

    async def reset_humanlike_state(self, *args, **kwargs):
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

    def test_humanlike_schema_constant_is_exported(self):
        self.assertEqual(
            HUMANLIKE_STATE_SCHEMA_VERSION,
            "astrbot.humanlike_state.v1",
        )

    def test_get_emotion_service_rejects_plugin_without_memory_payload_api(self):
        class OldEmotionService(FakeEmotionService):
            build_emotion_memory_payload = None

        context = FakeContext(
            SimpleNamespace(activated=True, star_cls=OldEmotionService()),
        )
        self.assertIsNone(get_emotion_service(context))

    def test_get_emotion_service_rejects_plugin_without_injection_api(self):
        class OldEmotionService(FakeEmotionService):
            inject_emotion_context = None

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

    def test_get_emotion_service_keeps_accepting_service_without_humanlike_api(self):
        plugin = FakeEmotionService()
        context = FakeContext(SimpleNamespace(activated=True, star_cls=plugin))
        self.assertIs(get_emotion_service(context), plugin)

    def test_get_humanlike_service_returns_activated_plugin(self):
        plugin = FakeHumanlikeService()
        context = FakeContext(SimpleNamespace(activated=True, star_cls=plugin))
        self.assertIs(get_humanlike_service(context), plugin)

    def test_get_humanlike_service_rejects_incomplete_plugin(self):
        context = FakeContext(
            SimpleNamespace(activated=True, star_cls=FakeEmotionService()),
        )
        self.assertIsNone(get_humanlike_service(context))

    def test_main_helper_uses_full_emotion_service_contract(self):
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

        from main import get_emotional_state_plugin

        class SnapshotOnly:
            async def get_emotion_snapshot(self):
                return {}

        incomplete = FakeContext(
            SimpleNamespace(activated=True, star_cls=SnapshotOnly()),
        )
        complete = FakeContext(
            SimpleNamespace(activated=True, star_cls=FakeEmotionService()),
        )

        self.assertIsNone(get_emotional_state_plugin(incomplete))
        self.assertIs(get_emotional_state_plugin(complete), complete.metadata.star_cls)


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

    def _new_plugin(self, config=None):
        from emotion_engine import EmotionEngine, EmotionParameters
        from humanlike_engine import HumanlikeEngine
        from main import EmotionalStatePlugin
        from psychological_screening import PsychologicalScreeningEngine

        plugin = EmotionalStatePlugin.__new__(EmotionalStatePlugin)
        plugin.config = dict(config or {})
        plugin.base_parameters = EmotionParameters()
        plugin.engine = EmotionEngine(plugin.base_parameters)
        plugin.psychological_engine = PsychologicalScreeningEngine()
        plugin.humanlike_engine = HumanlikeEngine()
        plugin._memory_cache = {}
        plugin._psychological_memory_cache = {}
        plugin._humanlike_memory_cache = {}
        plugin._last_request_text = {}
        plugin.context = SimpleNamespace()
        return plugin

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
            plugin = self._new_plugin()
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

    def test_on_llm_request_does_not_update_or_inject_humanlike_by_default(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState
        from humanlike_engine import HumanlikeState
        from main import EmotionalStatePlugin

        saves = []

        async def fake_persona(self, event, request):
            return None

        async def fake_load_state(self, session_key, persona_profile=None):
            return EmotionState.initial()

        async def fake_save_state(self, session_key, state):
            pass

        async def fake_load_humanlike(self, session_key):
            return HumanlikeState.initial()

        async def fake_save_humanlike(self, session_key, state):
            saves.append((session_key, state))

        original_persona = EmotionalStatePlugin._persona_profile
        original_load_state = EmotionalStatePlugin._load_state
        original_save_state = EmotionalStatePlugin._save_state
        original_load_humanlike = EmotionalStatePlugin._load_humanlike_state
        original_save_humanlike = EmotionalStatePlugin._save_humanlike_state
        EmotionalStatePlugin._persona_profile = fake_persona
        EmotionalStatePlugin._load_state = fake_load_state
        EmotionalStatePlugin._save_state = fake_save_state
        EmotionalStatePlugin._load_humanlike_state = fake_load_humanlike
        EmotionalStatePlugin._save_humanlike_state = fake_save_humanlike
        try:
            plugin = self._new_plugin(
                {"use_llm_assessor": False, "assessment_timing": "pre"},
            )
            event = SimpleNamespace(unified_msg_origin="s1", message_str="你好")
            request = SimpleNamespace(
                system_prompt="",
                contexts=[],
                prompt="你好",
                extra_user_content_parts=[],
                session_id="s1",
            )
            asyncio.run(plugin.on_llm_request(event, request))
        finally:
            EmotionalStatePlugin._persona_profile = original_persona
            EmotionalStatePlugin._load_state = original_load_state
            EmotionalStatePlugin._save_state = original_save_state
            EmotionalStatePlugin._load_humanlike_state = original_load_humanlike
            EmotionalStatePlugin._save_humanlike_state = original_save_humanlike

        self.assertEqual(saves, [])
        self.assertEqual(len(request.extra_user_content_parts), 1)
        self.assertIn("bot_emotion_state", request.extra_user_content_parts[0].text)
        self.assertNotIn("simulated humanlike-state", request.extra_user_content_parts[0].text)

    def test_on_llm_request_injects_humanlike_only_when_enabled_and_strength_positive(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState
        from humanlike_engine import HumanlikeState
        from main import EmotionalStatePlugin

        async def fake_persona(self, event, request):
            return None

        async def fake_load_state(self, session_key, persona_profile=None):
            return EmotionState.initial()

        async def fake_save_state(self, session_key, state):
            pass

        async def fake_load_humanlike(self, session_key):
            return HumanlikeState.initial()

        async def fake_save_humanlike(self, session_key, state):
            pass

        original_persona = EmotionalStatePlugin._persona_profile
        original_load_state = EmotionalStatePlugin._load_state
        original_save_state = EmotionalStatePlugin._save_state
        original_load_humanlike = EmotionalStatePlugin._load_humanlike_state
        original_save_humanlike = EmotionalStatePlugin._save_humanlike_state
        EmotionalStatePlugin._persona_profile = fake_persona
        EmotionalStatePlugin._load_state = fake_load_state
        EmotionalStatePlugin._save_state = fake_save_state
        EmotionalStatePlugin._load_humanlike_state = fake_load_humanlike
        EmotionalStatePlugin._save_humanlike_state = fake_save_humanlike
        try:
            plugin = self._new_plugin(
                {
                    "use_llm_assessor": False,
                    "assessment_timing": "pre",
                    "enable_humanlike_state": True,
                    "humanlike_injection_strength": 0.35,
                },
            )
            event = SimpleNamespace(unified_msg_origin="s1", message_str="你必须只能陪我")
            request = SimpleNamespace(
                system_prompt="",
                contexts=[],
                prompt="你必须只能陪我",
                extra_user_content_parts=[],
                session_id="s1",
            )
            asyncio.run(plugin.on_llm_request(event, request))
        finally:
            EmotionalStatePlugin._persona_profile = original_persona
            EmotionalStatePlugin._load_state = original_load_state
            EmotionalStatePlugin._save_state = original_save_state
            EmotionalStatePlugin._load_humanlike_state = original_load_humanlike
            EmotionalStatePlugin._save_humanlike_state = original_save_humanlike

        texts = [part.text for part in request.extra_user_content_parts]
        self.assertEqual(len(texts), 2)
        self.assertIn("bot_emotion_state", texts[0])
        self.assertIn("simulated humanlike-state", texts[1])

    def test_on_llm_request_does_not_inject_humanlike_when_inject_state_false_or_strength_zero(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState
        from humanlike_engine import HumanlikeState
        from main import EmotionalStatePlugin

        async def fake_persona(self, event, request):
            return None

        async def fake_load_state(self, session_key, persona_profile=None):
            return EmotionState.initial()

        async def fake_save_state(self, session_key, state):
            pass

        async def fake_load_humanlike(self, session_key):
            return HumanlikeState.initial()

        async def fake_save_humanlike(self, session_key, state):
            pass

        original_persona = EmotionalStatePlugin._persona_profile
        original_load_state = EmotionalStatePlugin._load_state
        original_save_state = EmotionalStatePlugin._save_state
        original_load_humanlike = EmotionalStatePlugin._load_humanlike_state
        original_save_humanlike = EmotionalStatePlugin._save_humanlike_state
        EmotionalStatePlugin._persona_profile = fake_persona
        EmotionalStatePlugin._load_state = fake_load_state
        EmotionalStatePlugin._save_state = fake_save_state
        EmotionalStatePlugin._load_humanlike_state = fake_load_humanlike
        EmotionalStatePlugin._save_humanlike_state = fake_save_humanlike
        try:
            cases = (
                {"enable_humanlike_state": True, "inject_state": False},
                {"enable_humanlike_state": True, "humanlike_injection_strength": 0.0},
            )
            lengths = []
            for case in cases:
                config = {
                    "use_llm_assessor": False,
                    "assessment_timing": "pre",
                    **case,
                }
                plugin = self._new_plugin(config)
                event = SimpleNamespace(unified_msg_origin="s1", message_str="你好")
                request = SimpleNamespace(
                    system_prompt="",
                    contexts=[],
                    prompt="你好",
                    extra_user_content_parts=[],
                    session_id="s1",
                )
                asyncio.run(plugin.on_llm_request(event, request))
                lengths.append(len(request.extra_user_content_parts))
        finally:
            EmotionalStatePlugin._persona_profile = original_persona
            EmotionalStatePlugin._load_state = original_load_state
            EmotionalStatePlugin._save_state = original_save_state
            EmotionalStatePlugin._load_humanlike_state = original_load_humanlike
            EmotionalStatePlugin._save_humanlike_state = original_save_humanlike

        self.assertEqual(lengths, [0, 1])

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

    def test_low_reasoning_mode_does_not_change_local_state_dynamics(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState, build_persona_profile
        from main import EmotionalStatePlugin

        llm_payload = (
            '{"label":"anger","dimensions":{"valence":-0.55,"arousal":0.66,'
            '"dominance":0.12,"goal_congruence":-0.62,"certainty":0.58,'
            '"control":-0.35,"affiliation":-0.48},"confidence":0.82,'
            '"appraisal":{"relationship_decision":{"decision":"boundary",'
            '"intensity":0.54,"forgiveness":0.28,"reason":"fixed"}},'
            '"reason":"fixed observation"}'
        )

        async def fake_provider_id(self, event):
            return "provider"

        class FakeContext:
            async def llm_generate(self, **kwargs):
                return SimpleNamespace(completion_text=llm_payload)

        async def run_case(low_reasoning):
            plugin = self._new_plugin(
                {
                    "low_reasoning_friendly_mode": low_reasoning,
                    "low_reasoning_max_context_chars": 60,
                    "max_context_chars": 5000,
                },
            )
            plugin.context = FakeContext()
            persona_profile = build_persona_profile(
                persona_id="p",
                name="p",
                text="敏感 谨慎 但重视边界",
            )
            previous = EmotionState.initial(persona_profile)
            previous.updated_at = 1000.0
            observation = await plugin._assess_emotion(
                event=SimpleNamespace(unified_msg_origin="s1"),
                phase="pre_response",
                previous_state=previous,
                persona_profile=persona_profile,
                context_text="A" * 200,
                current_text="B" * 200,
            )
            state = plugin._engine_for_persona(persona_profile).update(
                previous,
                observation,
                profile=persona_profile,
                now=1020.0,
            )
            return state.to_dict()

        original_provider_id = EmotionalStatePlugin._provider_id
        EmotionalStatePlugin._provider_id = fake_provider_id
        try:
            normal = asyncio.run(run_case(False))
            low = asyncio.run(run_case(True))
        finally:
            EmotionalStatePlugin._provider_id = original_provider_id

        self.assertEqual(low["values"], normal["values"])
        self.assertEqual(low["label"], normal["label"])
        self.assertEqual(low["last_alpha"], normal["last_alpha"])
        self.assertEqual(low["last_surprise"], normal["last_surprise"])
        self.assertEqual(low["consequences"], normal["consequences"])

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

    def test_psychological_snapshot_and_values_read_when_module_disabled(self):
        self._install_astrbot_stubs()
        from main import EmotionalStatePlugin
        from psychological_screening import PsychologicalScreeningState

        async def fake_load(self, session_key):
            state = PsychologicalScreeningState.initial()
            state.values["distress"] = 0.42
            state.updated_at = 1000.0
            return state

        original_load = EmotionalStatePlugin._load_psychological_state
        EmotionalStatePlugin._load_psychological_state = fake_load
        try:
            plugin = self._new_plugin()
            snapshot = asyncio.run(
                plugin.get_psychological_screening_snapshot(session_key="s1"),
            )
            values = asyncio.run(
                plugin.get_psychological_screening_values(session_key="s1"),
            )
        finally:
            EmotionalStatePlugin._load_psychological_state = original_load

        self.assertEqual(snapshot["session_key"], "s1")
        self.assertNotIn("enabled", snapshot)
        self.assertFalse(snapshot["diagnostic"])
        self.assertEqual(snapshot["values"]["distress"], 0.42)
        self.assertEqual(values["distress"], 0.42)

    def test_psychological_snapshot_reads_enabled_saved_state(self):
        self._install_astrbot_stubs()
        from main import EmotionalStatePlugin
        from psychological_screening import PsychologicalScreeningState

        async def fake_load(self, session_key):
            state = PsychologicalScreeningState.initial()
            state.values["sleep_disruption"] = 0.77
            state.red_flags = ["severe_sleep_disruption"]
            state.turns = 3
            state.updated_at = 2000.0
            return state

        original_load = EmotionalStatePlugin._load_psychological_state
        EmotionalStatePlugin._load_psychological_state = fake_load
        try:
            plugin = self._new_plugin({"enable_psychological_screening": True})
            snapshot = asyncio.run(
                plugin.get_psychological_screening_snapshot(session_key="s2"),
            )
        finally:
            EmotionalStatePlugin._load_psychological_state = original_load

        self.assertEqual(snapshot["session_key"], "s2")
        self.assertEqual(snapshot["values"]["sleep_disruption"], 0.77)
        self.assertIn("severe_sleep_disruption", snapshot["risk"]["red_flags"])
        self.assertEqual(snapshot["turns"], 3)
        self.assertFalse(snapshot["diagnostic"])

    def test_psychological_simulate_does_not_save_even_when_disabled(self):
        self._install_astrbot_stubs()
        from main import EmotionalStatePlugin
        from psychological_screening import PsychologicalScreeningState

        async def fake_load(self, session_key):
            state = PsychologicalScreeningState.initial()
            state.updated_at = 1000.0
            return state

        async def fake_save(self, session_key, state):
            raise AssertionError("simulate_psychological_update must not save")

        original_load = EmotionalStatePlugin._load_psychological_state
        original_save = EmotionalStatePlugin._save_psychological_state
        EmotionalStatePlugin._load_psychological_state = fake_load
        EmotionalStatePlugin._save_psychological_state = fake_save
        try:
            plugin = self._new_plugin()
            payload = asyncio.run(
                plugin.simulate_psychological_update(
                    session_key="s1",
                    text="我焦虑到睡不着",
                    source="unit_test",
                    observed_at=1010.0,
                ),
            )
        finally:
            EmotionalStatePlugin._load_psychological_state = original_load
            EmotionalStatePlugin._save_psychological_state = original_save

        self.assertEqual(payload["session_key"], "s1")
        self.assertGreater(payload["values"]["anxiety_tension"], 0.0)
        self.assertFalse(payload["observation"]["committed"])
        self.assertEqual(payload["observation"]["source"], "unit_test")

    def test_psychological_reset_backdoor_is_independent_of_module_enabled(self):
        self._install_astrbot_stubs()
        from main import EmotionalStatePlugin

        deleted = []

        async def fake_delete(self, session_key):
            deleted.append(session_key)

        original_delete = EmotionalStatePlugin._delete_psychological_state
        EmotionalStatePlugin._delete_psychological_state = fake_delete
        try:
            disabled_module = self._new_plugin({"enable_psychological_screening": False})
            self.assertTrue(
                asyncio.run(
                    disabled_module.reset_psychological_screening_state(
                        session_key="disabled-module",
                    ),
                ),
            )
            locked = self._new_plugin({"allow_emotion_reset_backdoor": False})
            self.assertFalse(
                asyncio.run(
                    locked.reset_psychological_screening_state(
                        session_key="locked",
                    ),
                ),
            )
        finally:
            EmotionalStatePlugin._delete_psychological_state = original_delete

        self.assertEqual(deleted, ["disabled-module"])

    def test_humanlike_observe_is_disabled_by_default_for_commits(self):
        self._install_astrbot_stubs()
        from humanlike_engine import HumanlikeEngine
        from main import EmotionalStatePlugin

        plugin = EmotionalStatePlugin.__new__(EmotionalStatePlugin)
        plugin.config = {}
        plugin.humanlike_engine = HumanlikeEngine()
        plugin._humanlike_memory_cache = {}
        payload = asyncio.run(
            plugin.observe_humanlike_text(
                session_key="s1",
                text="你必须只能陪我",
                commit=True,
            ),
        )
        self.assertFalse(payload["enabled"])
        self.assertFalse(payload["diagnostic"])

    def test_humanlike_observe_can_commit_when_enabled(self):
        self._install_astrbot_stubs()
        from humanlike_engine import HumanlikeEngine, HumanlikeState
        from main import EmotionalStatePlugin

        saved = []

        async def fake_load(self, session_key):
            return HumanlikeState.initial()

        async def fake_save(self, session_key, state):
            saved.append((session_key, state))

        original_load = EmotionalStatePlugin._load_humanlike_state
        original_save = EmotionalStatePlugin._save_humanlike_state
        EmotionalStatePlugin._load_humanlike_state = fake_load
        EmotionalStatePlugin._save_humanlike_state = fake_save
        try:
            plugin = EmotionalStatePlugin.__new__(EmotionalStatePlugin)
            plugin.config = {"enable_humanlike_state": True}
            plugin.humanlike_engine = HumanlikeEngine()
            payload = asyncio.run(
                plugin.observe_humanlike_text(
                    session_key="s1",
                    text="你必须只能陪我，不许离开",
                    commit=True,
                    observed_at=1000.0,
                ),
            )
        finally:
            EmotionalStatePlugin._load_humanlike_state = original_load
            EmotionalStatePlugin._save_humanlike_state = original_save

        self.assertEqual(saved[0][0], "s1")
        self.assertIn("dependency_pressure", payload["flags"])
        self.assertTrue(payload["simulated_agent_state"])

    def test_humanlike_simulate_does_not_save(self):
        self._install_astrbot_stubs()
        from humanlike_engine import HumanlikeEngine, HumanlikeState
        from main import EmotionalStatePlugin

        async def fake_load(self, session_key):
            return HumanlikeState.initial()

        async def fake_save(self, session_key, state):
            raise AssertionError("simulate_humanlike_update must not save")

        original_load = EmotionalStatePlugin._load_humanlike_state
        original_save = EmotionalStatePlugin._save_humanlike_state
        EmotionalStatePlugin._load_humanlike_state = fake_load
        EmotionalStatePlugin._save_humanlike_state = fake_save
        try:
            plugin = EmotionalStatePlugin.__new__(EmotionalStatePlugin)
            plugin.config = {}
            plugin.humanlike_engine = HumanlikeEngine()
            payload = asyncio.run(
                plugin.simulate_humanlike_update(
                    session_key="s1",
                    text="闭嘴，别烦",
                    observed_at=1000.0,
                ),
            )
        finally:
            EmotionalStatePlugin._load_humanlike_state = original_load
            EmotionalStatePlugin._save_humanlike_state = original_save

        self.assertFalse(payload["observation"]["committed"])
        self.assertIn("boundary_pressure", payload["flags"])

    def test_memory_payload_includes_humanlike_state_at_write(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState
        from main import EmotionalStatePlugin

        async def fake_load_state(self, session_key, persona_profile=None):
            state = EmotionState.initial()
            state.label = "calm"
            state.updated_at = 10.0
            return state

        async def fake_humanlike_snapshot(self, *args, **kwargs):
            return {
                "schema_version": "astrbot.humanlike_state.v1",
                "kind": "humanlike_state",
                "session_key": kwargs["session_key"],
                "exposure": "plugin_safe",
                "enabled": True,
                "simulated_agent_state": True,
                "diagnostic": False,
                "output_modulation": {"warmth": 0.5},
                "flags": ["repair_attempt"],
                "updated_at": 11.0,
            }

        original_load_state = EmotionalStatePlugin._load_state
        original_humanlike_snapshot = EmotionalStatePlugin.get_humanlike_snapshot
        EmotionalStatePlugin._load_state = fake_load_state
        EmotionalStatePlugin.get_humanlike_snapshot = fake_humanlike_snapshot
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
            EmotionalStatePlugin.get_humanlike_snapshot = original_humanlike_snapshot

        self.assertIn("humanlike_state_at_write", payload)
        self.assertEqual(
            payload["humanlike_state_at_write"]["schema_version"],
            "astrbot.humanlike_state.v1",
        )
        self.assertEqual(payload["humanlike_state_at_write"]["source"], "livingmemory")
        self.assertEqual(payload["humanlike_state_at_write"]["written_at"], 20.0)

    def test_memory_payload_includes_disabled_humanlike_annotation_by_default(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState
        from main import EmotionalStatePlugin

        async def fake_load_state(self, session_key, persona_profile=None):
            state = EmotionState.initial()
            state.label = "calm"
            state.updated_at = 10.0
            return state

        original_load_state = EmotionalStatePlugin._load_state
        EmotionalStatePlugin._load_state = fake_load_state
        try:
            plugin = self._new_plugin()
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

        annotation = payload["humanlike_state_at_write"]
        snapshot = payload["humanlike_snapshot"]
        self.assertFalse(annotation["enabled"])
        self.assertFalse(snapshot["enabled"])
        self.assertEqual(snapshot["reason"], "enable_humanlike_state is false")
        self.assertEqual(annotation["kind"], "humanlike_state_at_write")
        self.assertNotIn("prompt_fragment", annotation)

    def test_emotion_prompt_fragment_respects_safety_boundary_config(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState
        from main import EmotionalStatePlugin

        async def fake_load_state(self, session_key, persona_profile=None):
            return EmotionState.initial()

        original_load_state = EmotionalStatePlugin._load_state
        EmotionalStatePlugin._load_state = fake_load_state
        try:
            default_plugin = self._new_plugin()
            default_snapshot = asyncio.run(
                default_plugin.get_emotion_snapshot(
                    session_key="s-safe",
                    include_prompt_fragment=True,
                ),
            )
            relaxed_plugin = self._new_plugin({"enable_safety_boundary": False})
            relaxed_snapshot = asyncio.run(
                relaxed_plugin.get_emotion_snapshot(
                    session_key="s-raw",
                    include_prompt_fragment=True,
                ),
            )
        finally:
            EmotionalStatePlugin._load_state = original_load_state

        self.assertIn("不能羞辱", default_snapshot["prompt_fragment"])
        self.assertTrue(default_snapshot["safety"]["enabled"])
        self.assertNotIn("safety", relaxed_snapshot)
        self.assertNotIn("不能羞辱", relaxed_snapshot["prompt_fragment"])
        self.assertIn("按 active_effects", relaxed_snapshot["prompt_fragment"])

    def test_humanlike_prompt_fragment_respects_safety_boundary_config(self):
        self._install_astrbot_stubs()
        from humanlike_engine import HumanlikeState
        from main import EmotionalStatePlugin

        async def fake_load_humanlike_state(self, session_key):
            state = HumanlikeState.initial()
            state.values["dependency_risk"] = 0.7
            return state

        original_load = EmotionalStatePlugin._load_humanlike_state
        EmotionalStatePlugin._load_humanlike_state = fake_load_humanlike_state
        try:
            base_config = {"enable_humanlike_state": True}
            default_fragment = asyncio.run(
                self._new_plugin(base_config).get_humanlike_prompt_fragment(
                    session_key="s-safe",
                ),
            )
            relaxed_fragment = asyncio.run(
                self._new_plugin(
                    {
                        **base_config,
                        "enable_safety_boundary": False,
                    },
                ).get_humanlike_prompt_fragment(session_key="s-raw"),
            )
        finally:
            EmotionalStatePlugin._load_humanlike_state = original_load

        self.assertIn("Never use the simulated state", default_fragment)
        self.assertIn("Dependency guard active", default_fragment)
        self.assertNotIn("Never use the simulated state", relaxed_fragment)
        self.assertIn("Dependency guard active", relaxed_fragment)

    def test_reset_public_methods_respect_backdoor_config(self):
        self._install_astrbot_stubs()
        from main import EmotionalStatePlugin

        deleted = []

        async def fake_delete_state(self, session_key):
            deleted.append(("emotion", session_key))

        async def fake_delete_psychological(self, session_key):
            deleted.append(("psychological", session_key))

        async def fake_delete_humanlike(self, session_key):
            deleted.append(("humanlike", session_key))

        original_delete_state = EmotionalStatePlugin._delete_state
        original_delete_psychological = EmotionalStatePlugin._delete_psychological_state
        original_delete_humanlike = EmotionalStatePlugin._delete_humanlike_state
        EmotionalStatePlugin._delete_state = fake_delete_state
        EmotionalStatePlugin._delete_psychological_state = fake_delete_psychological
        EmotionalStatePlugin._delete_humanlike_state = fake_delete_humanlike
        try:
            locked = self._new_plugin(
                {
                    "allow_emotion_reset_backdoor": False,
                    "allow_humanlike_reset_backdoor": False,
                },
            )
            self.assertFalse(
                asyncio.run(locked.reset_emotion_state(session_key="s1")),
            )
            self.assertFalse(
                asyncio.run(locked.reset_psychological_screening_state(session_key="s1")),
            )
            self.assertFalse(
                asyncio.run(locked.reset_humanlike_state(session_key="s1")),
            )
            self.assertEqual(deleted, [])

            allowed = self._new_plugin()
            self.assertTrue(
                asyncio.run(allowed.reset_emotion_state(session_key="s1")),
            )
            self.assertTrue(
                asyncio.run(allowed.reset_psychological_screening_state(session_key="s1")),
            )
            self.assertTrue(
                asyncio.run(allowed.reset_humanlike_state(session_key="s1")),
            )
        finally:
            EmotionalStatePlugin._delete_state = original_delete_state
            EmotionalStatePlugin._delete_psychological_state = original_delete_psychological
            EmotionalStatePlugin._delete_humanlike_state = original_delete_humanlike

        self.assertEqual(
            deleted,
            [
                ("emotion", "s1"),
                ("psychological", "s1"),
                ("humanlike", "s1"),
            ],
        )

    def test_public_session_key_resolution_precedence(self):
        self._install_astrbot_stubs()

        plugin = self._new_plugin()
        event = SimpleNamespace(unified_msg_origin="event-session")
        request = SimpleNamespace(session_id="request-session")

        self.assertEqual(
            plugin._resolve_public_session_key(
                event,
                request=request,
                session_key="explicit-session",
            ),
            "explicit-session",
        )
        self.assertEqual(
            plugin._resolve_public_session_key(
                "string-session",
                request=request,
            ),
            "string-session",
        )
        self.assertEqual(
            plugin._resolve_public_session_key(event, request=request),
            "event-session",
        )
        self.assertEqual(
            plugin._resolve_public_session_key(None, request=request),
            "request-session",
        )
        self.assertEqual(plugin._resolve_public_session_key(None), "global")

    def test_get_emotion_state_as_dict_false_returns_detached_copy(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState
        from main import EmotionalStatePlugin

        stored = EmotionState.initial()
        stored.label = "stored"
        stored.values["valence"] = 0.25

        async def fake_load_state(self, session_key, persona_profile=None):
            return stored

        original_load_state = EmotionalStatePlugin._load_state
        EmotionalStatePlugin._load_state = fake_load_state
        try:
            plugin = self._new_plugin()
            detached = asyncio.run(
                plugin.get_emotion_state(session_key="s1", as_dict=False),
            )
        finally:
            EmotionalStatePlugin._load_state = original_load_state

        self.assertIsNot(detached, stored)
        self.assertEqual(detached.label, "stored")
        detached.label = "mutated"
        detached.values["valence"] = -1.0
        self.assertEqual(stored.label, "stored")
        self.assertEqual(stored.values["valence"], 0.25)

    def test_simulate_emotion_update_does_not_save_and_marks_uncommitted(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState
        from main import EmotionalStatePlugin

        async def fake_load_state(self, session_key, persona_profile=None):
            state = EmotionState.initial(persona_profile)
            state.updated_at = 1000.0
            return state

        async def fake_save_state(self, session_key, state):
            raise AssertionError("simulate_emotion_update must not save")

        original_load_state = EmotionalStatePlugin._load_state
        original_save_state = EmotionalStatePlugin._save_state
        EmotionalStatePlugin._load_state = fake_load_state
        EmotionalStatePlugin._save_state = fake_save_state
        try:
            plugin = self._new_plugin({"use_llm_assessor": False})
            payload = asyncio.run(
                plugin.simulate_emotion_update(
                    session_key="s1",
                    text="I am only simulating this candidate reply.",
                    role="assistant",
                    source="unit_test",
                    observed_at=1010.0,
                ),
            )
        finally:
            EmotionalStatePlugin._load_state = original_load_state
            EmotionalStatePlugin._save_state = original_save_state

        self.assertEqual(payload["session_key"], "s1")
        self.assertFalse(payload["observation"]["committed"])
        self.assertEqual(payload["observation"]["source"], "unit_test")
        self.assertEqual(payload["observation"]["role"], "assistant")

    def test_humanlike_direct_public_api_disabled_payloads(self):
        self._install_astrbot_stubs()
        from main import EmotionalStatePlugin

        async def fake_load_humanlike_state(self, session_key):
            raise AssertionError("disabled humanlike API must not load state")

        original_load_humanlike = EmotionalStatePlugin._load_humanlike_state
        EmotionalStatePlugin._load_humanlike_state = fake_load_humanlike_state
        try:
            plugin = self._new_plugin()
            snapshot = asyncio.run(
                plugin.get_humanlike_snapshot(
                    session_key="s1",
                    include_prompt_fragment=True,
                ),
            )
            values = asyncio.run(plugin.get_humanlike_values(session_key="s1"))
            fragment = asyncio.run(
                plugin.get_humanlike_prompt_fragment(session_key="s1"),
            )
        finally:
            EmotionalStatePlugin._load_humanlike_state = original_load_humanlike

        self.assertFalse(snapshot["enabled"])
        self.assertEqual(snapshot["reason"], "enable_humanlike_state is false")
        self.assertEqual(snapshot["prompt_fragment"], "")
        self.assertEqual(values, {})
        self.assertEqual(fragment, "")

    def test_memory_payload_can_disable_humanlike_annotation(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState
        from main import EmotionalStatePlugin

        async def fake_load_state(self, session_key, persona_profile=None):
            state = EmotionState.initial()
            state.label = "calm"
            return state

        async def fake_humanlike_snapshot(self, *args, **kwargs):
            raise AssertionError("humanlike snapshot must not be read when disabled")

        original_load_state = EmotionalStatePlugin._load_state
        original_humanlike_snapshot = EmotionalStatePlugin.get_humanlike_snapshot
        EmotionalStatePlugin._load_state = fake_load_state
        EmotionalStatePlugin.get_humanlike_snapshot = fake_humanlike_snapshot
        try:
            plugin = EmotionalStatePlugin.__new__(EmotionalStatePlugin)
            plugin.config = {"humanlike_memory_write_enabled": False}
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
            EmotionalStatePlugin.get_humanlike_snapshot = original_humanlike_snapshot

        self.assertNotIn("humanlike_state_at_write", payload)
        self.assertNotIn("humanlike_snapshot", payload)
        self.assertEqual(payload["emotion_at_write"]["label"], "calm")
        self.assertEqual(payload["memory_text"], "memory")
        self.assertEqual(payload["session_key"], "livingmemory:user-1")

    def test_livingmemory_shaped_write_uses_frozen_minimal_payload(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState
        from main import EmotionalStatePlugin

        written = []

        class FakeLivingMemory:
            async def add_memory(self, event, memory):
                written.append(
                    {
                        "session": event.unified_msg_origin,
                        "memory": memory,
                    },
                )
                return {"ok": True, "id": "mem-1"}

        async def fake_load_state(self, session_key, persona_profile=None):
            state = EmotionState.initial()
            state.label = "protective"
            state.confidence = 0.91
            state.updated_at = 30.0
            state.values["valence"] = -0.22
            state.last_appraisal = {
                "relationship_decision": {
                    "decision": "boundary",
                    "reason": "用户越界但正在修复",
                },
            }
            return state

        original_load_state = EmotionalStatePlugin._load_state
        EmotionalStatePlugin._load_state = fake_load_state
        try:
            plugin = self._new_plugin({"humanlike_memory_write_enabled": False})
            event = SimpleNamespace(unified_msg_origin="livingmemory:session-13")
            base_memory = {
                "text": "用户承认刚才说得太过，并承诺之后先确认边界。",
                "tags": ["repair"],
            }
            payload = asyncio.run(
                plugin.build_emotion_memory_payload(
                    event,
                    memory=base_memory,
                    source="livingmemory",
                    include_raw_snapshot=False,
                    written_at=40.0,
                ),
            )
            result = asyncio.run(FakeLivingMemory().add_memory(event, payload))
        finally:
            EmotionalStatePlugin._load_state = original_load_state

        self.assertTrue(result["ok"])
        stored = written[0]["memory"]
        self.assertEqual(written[0]["session"], "livingmemory:session-13")
        self.assertEqual(stored["schema_version"], "astrbot.emotion_memory.v1")
        self.assertEqual(stored["kind"], "emotion_annotated_memory")
        self.assertEqual(stored["source"], "livingmemory")
        self.assertEqual(stored["session_key"], "livingmemory:session-13")
        self.assertEqual(stored["memory"], base_memory)
        self.assertEqual(stored["memory_text"], base_memory["text"])
        self.assertNotIn("emotion_snapshot", stored)
        self.assertNotIn("humanlike_snapshot", stored)
        self.assertNotIn("humanlike_state_at_write", stored)
        self.assertEqual(stored["emotion_at_write"]["label"], "protective")
        self.assertEqual(stored["emotion_at_write"]["written_at"], 40.0)
        self.assertEqual(
            stored["emotion_at_write"]["relationship"]["relationship_decision"][
                "decision"
            ],
            "boundary",
        )

    def test_memory_payload_without_raw_snapshot_keeps_humanlike_annotation(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState
        from main import EmotionalStatePlugin

        async def fake_load_state(self, session_key, persona_profile=None):
            state = EmotionState.initial()
            state.label = "calm"
            return state

        async def fake_humanlike_snapshot(self, *args, **kwargs):
            return {
                "schema_version": "astrbot.humanlike_state.v1",
                "kind": "humanlike_state",
                "session_key": kwargs["session_key"],
                "exposure": "plugin_safe",
                "enabled": True,
                "simulated_agent_state": True,
                "diagnostic": False,
                "output_modulation": {"warmth": 0.5},
                "flags": [],
                "updated_at": 11.0,
            }

        original_load_state = EmotionalStatePlugin._load_state
        original_humanlike_snapshot = EmotionalStatePlugin.get_humanlike_snapshot
        EmotionalStatePlugin._load_state = fake_load_state
        EmotionalStatePlugin.get_humanlike_snapshot = fake_humanlike_snapshot
        try:
            payload = asyncio.run(
                self._new_plugin().build_emotion_memory_payload(
                    session_key="livingmemory:user-raw-off",
                    memory="plain memory",
                    source="livingmemory",
                    include_raw_snapshot=False,
                    written_at=20.0,
                ),
            )
        finally:
            EmotionalStatePlugin._load_state = original_load_state
            EmotionalStatePlugin.get_humanlike_snapshot = original_humanlike_snapshot

        self.assertNotIn("emotion_snapshot", payload)
        self.assertNotIn("humanlike_snapshot", payload)
        self.assertEqual(payload["memory"], "plain memory")
        self.assertEqual(payload["memory_text"], "plain memory")
        self.assertIn("emotion_at_write", payload)
        self.assertIn("humanlike_state_at_write", payload)
        self.assertEqual(payload["humanlike_state_at_write"]["source"], "livingmemory")
        self.assertEqual(payload["humanlike_state_at_write"]["written_at"], 20.0)

    def test_memory_text_override_takes_precedence_over_dict_text(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState
        from main import EmotionalStatePlugin

        async def fake_load_state(self, session_key, persona_profile=None):
            return EmotionState.initial()

        original_load_state = EmotionalStatePlugin._load_state
        EmotionalStatePlugin._load_state = fake_load_state
        try:
            payload = asyncio.run(
                self._new_plugin({"humanlike_memory_write_enabled": False})
                .build_emotion_memory_payload(
                    session_key="livingmemory:user-override",
                    memory={"text": "dict memory"},
                    memory_text="override memory text",
                    include_raw_snapshot=False,
                ),
            )
        finally:
            EmotionalStatePlugin._load_state = original_load_state

        self.assertEqual(payload["memory"]["text"], "dict memory")
        self.assertEqual(payload["memory_text"], "override memory text")


if __name__ == "__main__":
    unittest.main()
