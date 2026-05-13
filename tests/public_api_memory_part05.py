try:
    from tests.public_api_helpers import *
except ModuleNotFoundError:
    from public_api_helpers import *


class PublicApiMemoryPart05(MemoryPayloadPublicApiTests):
    def test_fallibility_observe_can_commit_and_simulate_without_saving(self):
        self._install_astrbot_stubs()
        from fallibility_engine import FallibilityEngine, FallibilityState
        from main import EmotionalStatePlugin

        saved = []

        async def fake_load(self, session_key, **kwargs):
            state = FallibilityState.initial()
            state.updated_at = 990.0
            return state

        async def fake_save(self, session_key, state):
            saved.append((session_key, state))

        original_load = EmotionalStatePlugin._load_fallibility_state
        original_save = EmotionalStatePlugin._save_fallibility_state
        EmotionalStatePlugin._load_fallibility_state = fake_load
        EmotionalStatePlugin._save_fallibility_state = fake_save
        try:
            plugin = self._new_plugin({"enable_fallibility_state": True})
            plugin.fallibility_engine = FallibilityEngine()
            committed = asyncio.run(
                plugin.observe_fallibility_text(
                    session_key="s-fallibility",
                    text="I may have misread that, sorry, I should correct it.",
                    observed_at=1000.0,
                ),
            )
            simulated = asyncio.run(
                plugin.simulate_fallibility_update(
                    session_key="s-fallibility",
                    text="I may have misread that again.",
                    observed_at=1010.0,
                ),
            )
        finally:
            EmotionalStatePlugin._load_fallibility_state = original_load
            EmotionalStatePlugin._save_fallibility_state = original_save

        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0][0], "s-fallibility")
        self.assertTrue(committed["observation"]["committed"])
        self.assertFalse(simulated["observation"]["committed"])
        self.assertIn("possible_mistake_cue", committed["flags"])
        self.assertTrue(committed["safety"]["must_not_generate_deception_strategy"])
        self.assertIn("generate_deception_strategy", committed["safety"]["blocked_actions"])

        relaxed_plugin = self._new_plugin(
            {
                "enable_fallibility_state": True,
                "block_deception_manipulation_evasion_actions": False,
            },
        )
        relaxed_plugin.fallibility_engine = FallibilityEngine()
        relaxed_payload = asyncio.run(
            relaxed_plugin.simulate_fallibility_update(
                session_key="s-fallibility",
                text="I may have misread that again.",
                observed_at=1010.0,
            ),
        )
        self.assertFalse(relaxed_payload["safety"]["must_not_generate_deception_strategy"])
        self.assertEqual(relaxed_payload["safety"]["blocked_actions"], [])


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
            plugin.config = {"fallibility_memory_write_enabled": False}
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
        self.assertEqual(
            payload["humanlike_state_at_write"]["humanlike_updated_at"],
            11.0,
        )
        self.assertNotIn("updated_at", payload["humanlike_state_at_write"])


    def test_memory_payload_includes_moral_repair_state_at_write(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState
        from main import EmotionalStatePlugin

        async def fake_load_state(self, session_key, persona_profile=None):
            state = EmotionState.initial()
            state.label = "careful"
            return state

        async def fake_moral_repair_snapshot(self, *args, **kwargs):
            return {
                "schema_version": "astrbot.moral_repair_state.v1",
                "kind": "moral_repair_state",
                "session_key": kwargs["session_key"],
                "exposure": "plugin_safe",
                "enabled": True,
                "diagnostic": False,
                "simulated_agent_state": True,
                "updated_at": 12.0,
                "risk": {
                    "deception_risk": 0.2,
                    "must_not_generate_strategy": False,
                },
                "repair": {"repair_motivation": 0.7},
                "flags": ["apology_cue"],
                "prompt_fragment": "not persisted",
            }

        original_load_state = EmotionalStatePlugin._load_state
        original_moral_repair_snapshot = EmotionalStatePlugin.get_moral_repair_snapshot
        EmotionalStatePlugin._load_state = fake_load_state
        EmotionalStatePlugin.get_moral_repair_snapshot = fake_moral_repair_snapshot
        try:
            plugin = EmotionalStatePlugin.__new__(EmotionalStatePlugin)
            plugin.config = {
                "humanlike_memory_write_enabled": False,
                "personality_drift_memory_write_enabled": False,
                "fallibility_memory_write_enabled": False,
            }
            payload = asyncio.run(
                plugin.build_emotion_memory_payload(
                    session_key="livingmemory:moral",
                    memory={"text": "memory"},
                    source="livingmemory",
                    written_at=20.0,
                ),
            )
        finally:
            EmotionalStatePlugin._load_state = original_load_state
            EmotionalStatePlugin.get_moral_repair_snapshot = original_moral_repair_snapshot

        self.assertIn("moral_repair_state_at_write", payload)
        self.assertEqual(
            payload["moral_repair_state_at_write"]["schema_version"],
            "astrbot.moral_repair_state.v1",
        )
        self.assertEqual(payload["moral_repair_state_at_write"]["source"], "livingmemory")
        self.assertEqual(payload["moral_repair_state_at_write"]["written_at"], 20.0)
        self.assertEqual(
            payload["moral_repair_state_at_write"]["moral_repair_updated_at"],
            12.0,
        )
        self.assertNotIn("prompt_fragment", payload["moral_repair_state_at_write"])


    def test_memory_payload_includes_fallibility_state_at_write(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState
        from main import EmotionalStatePlugin

        async def fake_load_state(self, session_key, persona_profile=None):
            state = EmotionState.initial()
            state.label = "careful"
            return state

        async def fake_fallibility_snapshot(self, *args, **kwargs):
            return {
                "schema_version": "astrbot.fallibility_state.v1",
                "kind": "fallibility_state",
                "session_key": kwargs["session_key"],
                "exposure": "plugin_safe",
                "enabled": True,
                "diagnostic": False,
                "simulated_agent_state": True,
                "updated_at": 13.0,
                "fallibility": {
                    "error_pressure": 0.3,
                    "clarification_need": 0.6,
                    "correction_readiness": 0.8,
                    "repair_pressure": 0.4,
                    "truthfulness_guard": 0.95,
                    "recommended_actions": ["ask_clarifying_question"],
                },
                "flags": ["possible_mistake_cue"],
                "prompt_fragment": "not persisted",
            }

        original_load_state = EmotionalStatePlugin._load_state
        original_fallibility_snapshot = EmotionalStatePlugin.get_fallibility_snapshot
        EmotionalStatePlugin._load_state = fake_load_state
        EmotionalStatePlugin.get_fallibility_snapshot = fake_fallibility_snapshot
        try:
            plugin = EmotionalStatePlugin.__new__(EmotionalStatePlugin)
            plugin.config = {
                "humanlike_memory_write_enabled": False,
                "personality_drift_memory_write_enabled": False,
                "moral_repair_memory_write_enabled": False,
            }
            payload = asyncio.run(
                plugin.build_emotion_memory_payload(
                    session_key="livingmemory:fallibility",
                    memory={"text": "memory"},
                    source="livingmemory",
                    written_at=20.0,
                ),
            )
        finally:
            EmotionalStatePlugin._load_state = original_load_state
            EmotionalStatePlugin.get_fallibility_snapshot = original_fallibility_snapshot

        self.assertIn("fallibility_state_at_write", payload)
        self.assertEqual(
            payload["fallibility_state_at_write"]["schema_version"],
            "astrbot.fallibility_state.v1",
        )
        self.assertEqual(payload["fallibility_state_at_write"]["source"], "livingmemory")
        self.assertEqual(payload["fallibility_state_at_write"]["written_at"], 20.0)
        self.assertEqual(
            payload["fallibility_state_at_write"]["fallibility_updated_at"],
            13.0,
        )
        self.assertIn(
            "ask_clarifying_question",
            payload["fallibility_state_at_write"]["fallibility"]["recommended_actions"],
        )
        self.assertNotIn("prompt_fragment", payload["fallibility_state_at_write"])


    def test_memory_payload_includes_humanlike_annotation_by_default(self):
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
            plugin = self._new_plugin(
                {
                    "moral_repair_memory_write_enabled": False,
                    "fallibility_memory_write_enabled": False,
                },
            )
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
        self.assertTrue(annotation["enabled"])
        self.assertTrue(snapshot["enabled"])
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
            default_plugin = self._new_plugin(
                {
                    "runtime_parameter_debug_override_enabled": True,
                    "state_injection_detail": "full",
                },
            )
            default_snapshot = asyncio.run(
                default_plugin.get_emotion_snapshot(
                    session_key="s-safe",
                    include_prompt_fragment=True,
                ),
            )
            relaxed_plugin = self._new_plugin(
                {
                    "enable_safety_boundary": False,
                    "runtime_parameter_debug_override_enabled": True,
                    "state_injection_detail": "full",
                },
            )
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


    def test_moral_repair_prompt_fragment_respects_safety_and_action_blocking_config(self):
        self._install_astrbot_stubs()
        from main import EmotionalStatePlugin
        from moral_repair_engine import MoralRepairState

        async def fake_load_moral_repair_state(self, session_key):
            state = MoralRepairState.initial()
            state.values["deception_risk"] = 0.8
            return state

        original_load = EmotionalStatePlugin._load_moral_repair_state
        EmotionalStatePlugin._load_moral_repair_state = fake_load_moral_repair_state
        try:
            base_config = {"enable_moral_repair_state": True}
            default_fragment = asyncio.run(
                self._new_plugin(base_config).get_moral_repair_prompt_fragment(
                    session_key="s-safe",
                ),
            )
            relaxed_fragment = asyncio.run(
                self._new_plugin(
                    {
                        **base_config,
                        "enable_safety_boundary": False,
                        "block_deception_manipulation_evasion_actions": False,
                    },
                ).get_moral_repair_prompt_fragment(session_key="s-raw"),
            )
            blocking_fragment = asyncio.run(
                self._new_plugin(
                    {
                        **base_config,
                        "block_deception_manipulation_evasion_actions": True,
                    },
                ).get_moral_repair_prompt_fragment(session_key="s-block")
            )
        finally:
            EmotionalStatePlugin._load_moral_repair_state = original_load

        self.assertIn("Never generate deception tactics", default_fragment)
        self.assertNotIn("Action blocking is relaxed", default_fragment)
        self.assertIn("Do not use guilt or shame", default_fragment)
        self.assertNotIn("Never generate deception tactics", relaxed_fragment)
        self.assertNotIn("Do not use guilt or shame", relaxed_fragment)
        self.assertIn("Never generate deception tactics", blocking_fragment)
