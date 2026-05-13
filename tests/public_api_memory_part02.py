try:
    from tests.public_api_helpers import *
except ModuleNotFoundError:
    from public_api_helpers import *


class PublicApiMemoryPart02(MemoryPayloadPublicApiTests):
    def test_on_llm_request_injects_humanlike_only_when_enabled_and_strength_positive(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState
        from humanlike_engine import HumanlikeState
        from main import EmotionalStatePlugin

        async def fake_persona(self, event, request):
            return None

        async def fake_load_state(self, session_key, persona_profile=None, **kwargs):
            return EmotionState.initial()

        async def fake_save_state(self, session_key, state):
            pass

        async def fake_load_humanlike(self, session_key, **kwargs):
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
        self.assertGreaterEqual(len(texts), 4)
        self.assertIn("bot_emotion_state", texts[0])
        joined = "\n".join(texts[1:])
        self.assertIn("bot_auxiliary_state", joined)
        self.assertIn('name="humanlike"', joined)
        self.assertIn('name="lifelike_learning"', joined)
        self.assertIn('name="personality_drift"', joined)
        self.assertIn("Detailed state-tool access is internal", joined)
        self.assertNotIn("query_agent_state(", joined)
        self.assertNotIn("get_bot_humanlike_state", joined)


    def test_on_llm_request_can_use_full_auxiliary_injection_for_compatibility(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState
        from humanlike_engine import HumanlikeState
        from main import EmotionalStatePlugin

        async def fake_persona(self, event, request):
            return None

        async def fake_load_state(self, session_key, persona_profile=None, **kwargs):
            return EmotionState.initial()

        async def fake_save_state(self, session_key, state):
            pass

        async def fake_load_humanlike(self, session_key, **kwargs):
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
                    "runtime_parameter_debug_override_enabled": True,
                    "auxiliary_state_injection_detail": "full",
                },
            )
            event = SimpleNamespace(unified_msg_origin="s1", message_str="hello")
            request = SimpleNamespace(
                system_prompt="",
                contexts=[],
                prompt="hello",
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
        self.assertGreaterEqual(len(texts), 4)
        self.assertIn("simulated humanlike-state", "\n".join(texts[1:]))


    def test_on_llm_request_does_not_inject_humanlike_when_inject_state_false_or_strength_zero(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState
        from humanlike_engine import HumanlikeState
        from main import EmotionalStatePlugin

        async def fake_persona(self, event, request):
            return None

        async def fake_load_state(self, session_key, persona_profile=None, **kwargs):
            return EmotionState.initial()

        async def fake_save_state(self, session_key, state):
            pass

        async def fake_load_humanlike(self, session_key, **kwargs):
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
                {"inject_state": False},
                {
                    "runtime_parameter_debug_override_enabled": True,
                    "auxiliary_state_injection_detail": "off",
                },
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
                state_parts = [
                    part
                    for part in request.extra_user_content_parts
                    if str(part.text).startswith("<bot_")
                    or "bot_auxiliary_state" in str(part.text)
                ]
                lengths.append(len(state_parts))
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


    def test_proactive_speech_decision_uses_llm_for_need_and_topic_judgement(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState
        from group_atmosphere_engine import GroupAtmosphereState
        from humanlike_engine import HumanlikeState
        from lifelike_learning_engine import LifelikeLearningState
        from main import EmotionalStatePlugin

        captured = {}

        class FakeContext:
            async def llm_generate(self, **kwargs):
                captured.update(kwargs)
                return SimpleNamespace(
                    completion_text=(
                        '{"should_speak":true,"need_mode":"mutual_need",'
                        '"topic_text":"围绕刚才的相处方式轻轻确认一下",'
                        '"speech_intent":"让双方都有需要和被需要的空间",'
                        '"opening_style":"light_question","confidence":0.82,'
                        '"reason":"上下文明确提出互需模式"}'
                    ),
                )

        async def fake_provider_id(self, event):
            return "provider"

        async def fake_load_state(self, session_key, persona_profile=None, *, now=None):
            state = EmotionState.initial()
            state.values["affiliation"] = 0.8
            state.values["valence"] = 0.4
            return state

        async def fake_lifelike(self, session_key, *, now=None):
            state = LifelikeLearningState.initial()
            state.values.update(
                {
                    "rapport": 0.86,
                    "common_ground": 0.74,
                    "initiative_readiness": 0.88,
                    "boundary_sensitivity": 0.08,
                    "mutual_need_balance": 0.80,
                    "being_needed_readiness": 0.76,
                    "need_expression_readiness": 0.62,
                },
            )
            state.user_profile.need_notes = ["mutual_need_mode"]
            return state

        async def fake_humanlike(self, session_key, *, now=None):
            return HumanlikeState.initial()

        async def fake_group(self, session_key, *, now=None):
            state = GroupAtmosphereState.initial()
            state.values["joinability"] = 0.9
            state.values["bot_attention"] = 0.8
            return state

        originals = {
            "_provider_id": EmotionalStatePlugin._provider_id,
            "_load_state": EmotionalStatePlugin._load_state,
            "_load_lifelike_learning_state": EmotionalStatePlugin._load_lifelike_learning_state,
            "_load_humanlike_state": EmotionalStatePlugin._load_humanlike_state,
            "_load_group_atmosphere_state": EmotionalStatePlugin._load_group_atmosphere_state,
        }
        EmotionalStatePlugin._provider_id = fake_provider_id
        EmotionalStatePlugin._load_state = fake_load_state
        EmotionalStatePlugin._load_lifelike_learning_state = fake_lifelike
        EmotionalStatePlugin._load_humanlike_state = fake_humanlike
        EmotionalStatePlugin._load_group_atmosphere_state = fake_group
        try:
            plugin = self._new_plugin({"use_llm_assessor": True})
            plugin.context = FakeContext()
            decision = asyncio.run(
                plugin.get_proactive_speech_decision(
                    SimpleNamespace(unified_msg_origin="s-need"),
                    candidate_context="我希望双方都有需要和被需要。",
                ),
            )
        finally:
            for name, value in originals.items():
                setattr(EmotionalStatePlugin, name, value)

        self.assertIn("主动发言裁决器", captured["system_prompt"])
        self.assertIn("双方都有需要", captured["prompt"])
        self.assertEqual(decision["topic_judgement"]["source"], "llm")
        self.assertEqual(decision["topic_judgement"]["need_mode"], "mutual_need")
        self.assertEqual(decision["selected_topic"]["source"], "llm")
        self.assertTrue(decision["should_speak"])
        self.assertTrue(decision["dispatch_request"]["requested"])
        self.assertIn("message_text", decision["dispatch_request"])
