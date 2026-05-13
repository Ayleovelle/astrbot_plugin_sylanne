try:
    from tests.public_api_helpers import *
except ModuleNotFoundError:
    from public_api_helpers import *


class PublicApiMemoryPart07(MemoryPayloadPublicApiTests):
    def test_lifelike_observe_can_commit_and_simulate_without_saving(self):
        self._install_astrbot_stubs()
        from lifelike_learning_engine import LifelikeLearningState
        from main import EmotionalStatePlugin

        saved = []

        async def fake_load(self, session_key, **kwargs):
            state = LifelikeLearningState.initial()
            state.updated_at = 100.0
            return state

        async def fake_save(self, session_key, state):
            saved.append((session_key, state))

        original_load = EmotionalStatePlugin._load_lifelike_learning_state
        original_save = EmotionalStatePlugin._save_lifelike_learning_state
        EmotionalStatePlugin._load_lifelike_learning_state = fake_load
        EmotionalStatePlugin._save_lifelike_learning_state = fake_save
        try:
            plugin = self._new_plugin({"enable_lifelike_learning": True})
            committed = asyncio.run(
                plugin.observe_lifelike_text(
                    session_key="s-life",
                    text="『桥隧猫』就是会熬夜改桥梁模型的人，我喜欢自然聊天。",
                    observed_at=120.0,
                ),
            )
            simulated = asyncio.run(
                plugin.simulate_lifelike_update(
                    session_key="s-life",
                    text="桥隧猫就是会熬夜改桥梁模型的人。",
                    observed_at=130.0,
                ),
            )
        finally:
            EmotionalStatePlugin._load_lifelike_learning_state = original_load
            EmotionalStatePlugin._save_lifelike_learning_state = original_save

        self.assertEqual(saved[0][0], "s-life")
        self.assertTrue(committed["observation"]["committed"])
        self.assertIn("桥隧猫", committed["lexicon"])
        self.assertFalse(simulated["observation"]["committed"])
        self.assertEqual(len(saved), 1)


    def test_public_observe_methods_pass_observed_at_into_state_loads(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState
        from fallibility_engine import FallibilityEngine, FallibilityState
        from humanlike_engine import HumanlikeEngine, HumanlikeState
        from lifelike_learning_engine import LifelikeLearningEngine, LifelikeLearningState
        from main import EmotionalStatePlugin
        from moral_repair_engine import MoralRepairEngine, MoralRepairState
        from personality_drift_engine import PersonalityDriftEngine, PersonalityDriftState

        observed_at = 12345.0
        load_calls = []

        async def fake_load_emotion(self, session_key, persona_profile=None, *, now=None):
            load_calls.append(("emotion", now))
            state = EmotionState.initial(persona_profile)
            state.updated_at = 100.0
            return state

        async def fake_load_humanlike(self, session_key, personality_model=None, *, now=None):
            load_calls.append(("humanlike", now))
            state = HumanlikeState.initial()
            state.updated_at = 100.0
            return state

        async def fake_load_lifelike(self, session_key, personality_model=None, *, now=None):
            load_calls.append(("lifelike", now))
            state = LifelikeLearningState.initial()
            state.updated_at = 100.0
            return state

        async def fake_load_drift(self, session_key, profile=None, *, now=None):
            load_calls.append(("drift", now))
            return PersonalityDriftState.initial(
                persona_fingerprint=profile.fingerprint if profile else "default",
                now=100.0,
            )

        async def fake_load_moral(self, session_key, personality_model=None, *, now=None):
            load_calls.append(("moral", now))
            state = MoralRepairState.initial()
            state.updated_at = 100.0
            return state

        async def fake_load_fallibility(self, session_key, personality_model=None, *, now=None):
            load_calls.append(("fallibility", now))
            state = FallibilityState.initial()
            state.updated_at = 100.0
            return state

        async def fake_save(self, session_key, state):
            pass

        originals = {
            "_load_state": EmotionalStatePlugin._load_state,
            "_load_humanlike_state": EmotionalStatePlugin._load_humanlike_state,
            "_load_lifelike_learning_state": EmotionalStatePlugin._load_lifelike_learning_state,
            "_load_personality_drift_state": EmotionalStatePlugin._load_personality_drift_state,
            "_load_moral_repair_state": EmotionalStatePlugin._load_moral_repair_state,
            "_load_fallibility_state": EmotionalStatePlugin._load_fallibility_state,
            "_save_state": EmotionalStatePlugin._save_state,
            "_save_humanlike_state": EmotionalStatePlugin._save_humanlike_state,
            "_save_lifelike_learning_state": EmotionalStatePlugin._save_lifelike_learning_state,
            "_save_personality_drift_state": EmotionalStatePlugin._save_personality_drift_state,
            "_save_moral_repair_state": EmotionalStatePlugin._save_moral_repair_state,
            "_save_fallibility_state": EmotionalStatePlugin._save_fallibility_state,
        }
        EmotionalStatePlugin._load_state = fake_load_emotion
        EmotionalStatePlugin._load_humanlike_state = fake_load_humanlike
        EmotionalStatePlugin._load_lifelike_learning_state = fake_load_lifelike
        EmotionalStatePlugin._load_personality_drift_state = fake_load_drift
        EmotionalStatePlugin._load_moral_repair_state = fake_load_moral
        EmotionalStatePlugin._load_fallibility_state = fake_load_fallibility
        EmotionalStatePlugin._save_state = fake_save
        EmotionalStatePlugin._save_humanlike_state = fake_save
        EmotionalStatePlugin._save_lifelike_learning_state = fake_save
        EmotionalStatePlugin._save_personality_drift_state = fake_save
        EmotionalStatePlugin._save_moral_repair_state = fake_save
        EmotionalStatePlugin._save_fallibility_state = fake_save
        try:
            plugin = self._new_plugin(
                {
                    "use_llm_assessor": False,
                    "enable_humanlike_state": True,
                    "enable_lifelike_learning": True,
                    "enable_personality_drift": True,
                    "enable_moral_repair_state": True,
                    "enable_fallibility_state": True,
                },
            )
            plugin.humanlike_engine = HumanlikeEngine()
            plugin.lifelike_learning_engine = LifelikeLearningEngine()
            plugin.personality_drift_engine = PersonalityDriftEngine()
            plugin.moral_repair_engine = MoralRepairEngine()
            plugin.fallibility_engine = FallibilityEngine()
            asyncio.run(
                plugin.observe_emotion_text(
                    session_key="s-public-now",
                    text="thank you",
                    use_llm=False,
                    observed_at=observed_at,
                ),
            )
            asyncio.run(
                plugin.observe_humanlike_text(
                    session_key="s-public-now",
                    text="please stay",
                    observed_at=observed_at,
                ),
            )
            asyncio.run(
                plugin.observe_lifelike_text(
                    session_key="s-public-now",
                    text="桥隧猫就是会熬夜改桥梁模型的人。",
                    observed_at=observed_at,
                ),
            )
            asyncio.run(
                plugin.observe_personality_drift_event(
                    session_key="s-public-now",
                    text="thank you, I trust you",
                    observed_at=observed_at,
                ),
            )
            asyncio.run(
                plugin.observe_moral_repair_text(
                    session_key="s-public-now",
                    text="I was wrong and I will repair it.",
                    observed_at=observed_at,
                ),
            )
            asyncio.run(
                plugin.observe_fallibility_text(
                    session_key="s-public-now",
                    text="I may have misread that and should correct it.",
                    observed_at=observed_at,
                ),
            )
        finally:
            for name, original in originals.items():
                setattr(EmotionalStatePlugin, name, original)

        self.assertEqual(
            load_calls,
            [
                ("emotion", observed_at),
                ("humanlike", observed_at),
                ("lifelike", observed_at),
                ("drift", observed_at),
                ("moral", observed_at),
                ("fallibility", observed_at),
            ],
        )


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
            plugin.config = {
                "humanlike_memory_write_enabled": False,
                "personality_drift_memory_write_enabled": False,
                "fallibility_memory_write_enabled": False,
            }
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


    def test_memory_payload_can_include_lifelike_annotation_without_raw_snapshot(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState
        from main import EmotionalStatePlugin

        async def fake_load_state(self, session_key, persona_profile=None):
            state = EmotionState.initial()
            state.label = "curious"
            return state

        async def fake_lifelike_snapshot(self, *args, **kwargs):
            return {
                "schema_version": "astrbot.lifelike_learning_state.v1",
                "kind": "lifelike_learning_state",
                "session_key": kwargs["session_key"],
                "enabled": True,
                "updated_at": 12.0,
                "initiative_policy": {
                    "action": "ask_clarifying",
                    "uncertain_terms": ["桥隧猫"],
                },
                "common_ground": {
                    "known_terms": [
                        {
                            "term": "桥隧猫",
                            "confidence": 0.4,
                            "ask_before_using": True,
                            "sensitive": False,
                        },
                    ],
                    "profile_counts": {"likes": 1},
                },
                "flags": ["local_jargon_detected"],
                "dynamics": {"state_half_life_seconds": 1234.0},
                "privacy": {"raw_message_text_excluded": True},
            }

        original_load_state = EmotionalStatePlugin._load_state
        original_lifelike_snapshot = EmotionalStatePlugin.get_lifelike_learning_snapshot
        EmotionalStatePlugin._load_state = fake_load_state
        EmotionalStatePlugin.get_lifelike_learning_snapshot = fake_lifelike_snapshot
        try:
            payload = asyncio.run(
                self._new_plugin(
                    {
                        "humanlike_memory_write_enabled": False,
                        "moral_repair_memory_write_enabled": False,
                        "personality_drift_memory_write_enabled": False,
                    },
                ).build_emotion_memory_payload(
                    session_key="livingmemory:lifelike",
                    memory="plain memory",
                    source="livingmemory",
                    include_raw_snapshot=False,
                    written_at=20.0,
                ),
            )
        finally:
            EmotionalStatePlugin._load_state = original_load_state
            EmotionalStatePlugin.get_lifelike_learning_snapshot = original_lifelike_snapshot

        self.assertIn("lifelike_learning_state_at_write", payload)
        self.assertNotIn("lifelike_learning_snapshot", payload)
        annotation = payload["lifelike_learning_state_at_write"]
        self.assertEqual(annotation["kind"], "lifelike_learning_state_at_write")
        self.assertEqual(annotation["initiative_policy"]["action"], "ask_clarifying")
        self.assertEqual(annotation["dynamics"]["state_half_life_seconds"], 1234.0)
        envelope = payload["state_annotations_at_write"]
        self.assertIn("lifelike_learning_state_at_write", envelope["annotation_keys"])
        self.assertIn("lifelike_learning_state_at_write", envelope["annotations"])


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
            plugin = self._new_plugin(
                {
                    "humanlike_memory_write_enabled": False,
                    "personality_drift_memory_write_enabled": False,
                },
            )
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


    def test_query_sylanne_memory_public_api_is_read_only(self):
        self._install_astrbot_stubs()
        from memory_engine import MemoryRecord, SylanneMemoryState

        plugin = self._new_plugin()
        state = SylanneMemoryState.initial(now=10.0)
        state.records.append(
            MemoryRecord(
                text="User prefers concise README quick-start examples.",
                summary="Concise README quick-start examples.",
                session_key="s-public-memory-query",
                created_at=10.0,
                updated_at=10.0,
                depth=0.86,
                confidence=0.8,
                recall_count=0,
            ),
        )
        plugin._sylanne_memory_cache = {"s-public-memory-query": state}

        payload = asyncio.run(
            plugin.query_sylanne_memory(
                session_key="s-public-memory-query",
                query="README quick-start",
                now=12.0,
            ),
        )

        self.assertTrue(payload["enabled"])
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["result_count"], 1)
        self.assertIn("README", payload["results"][0]["summary"])
        self.assertEqual(state.records[0].recall_count, 0)
