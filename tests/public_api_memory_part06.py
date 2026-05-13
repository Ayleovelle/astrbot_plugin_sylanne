try:
    from tests.public_api_helpers import *
except ModuleNotFoundError:
    from public_api_helpers import *


class PublicApiMemoryPart06(MemoryPayloadPublicApiTests):
    def test_fallibility_prompt_fragment_respects_action_blocking_config(self):
        self._install_astrbot_stubs()
        from fallibility_engine import FallibilityState
        from main import EmotionalStatePlugin

        async def fake_load_fallibility_state(self, session_key):
            state = FallibilityState.initial()
            state.values["shadow_deception_impulse"] = 0.8
            return state

        original_load = EmotionalStatePlugin._load_fallibility_state
        EmotionalStatePlugin._load_fallibility_state = fake_load_fallibility_state
        try:
            base_config = {"enable_fallibility_state": True}
            default_fragment = asyncio.run(
                self._new_plugin(base_config).get_fallibility_prompt_fragment(
                    session_key="s-safe",
                ),
            )
            blocking_fragment = asyncio.run(
                self._new_plugin(
                    {
                        **base_config,
                        "block_deception_manipulation_evasion_actions": True,
                    },
                ).get_fallibility_prompt_fragment(session_key="s-block")
            )
        finally:
            EmotionalStatePlugin._load_fallibility_state = original_load

        self.assertNotIn("Action blocking is relaxed", default_fragment)
        self.assertIn("Do not intentionally fabricate facts", default_fragment)
        self.assertIn("Do not intentionally fabricate facts", blocking_fragment)


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

        async def fake_delete_lifelike(self, session_key):
            deleted.append(("lifelike", session_key))

        async def fake_delete_moral_repair(self, session_key):
            deleted.append(("moral_repair", session_key))

        async def fake_delete_fallibility(self, session_key):
            deleted.append(("fallibility", session_key))

        original_delete_state = EmotionalStatePlugin._delete_state
        original_delete_psychological = EmotionalStatePlugin._delete_psychological_state
        original_delete_humanlike = EmotionalStatePlugin._delete_humanlike_state
        original_delete_lifelike = EmotionalStatePlugin._delete_lifelike_learning_state
        original_delete_moral_repair = EmotionalStatePlugin._delete_moral_repair_state
        original_delete_fallibility = EmotionalStatePlugin._delete_fallibility_state
        EmotionalStatePlugin._delete_state = fake_delete_state
        EmotionalStatePlugin._delete_psychological_state = fake_delete_psychological
        EmotionalStatePlugin._delete_humanlike_state = fake_delete_humanlike
        EmotionalStatePlugin._delete_lifelike_learning_state = fake_delete_lifelike
        EmotionalStatePlugin._delete_moral_repair_state = fake_delete_moral_repair
        EmotionalStatePlugin._delete_fallibility_state = fake_delete_fallibility
        try:
            locked = self._new_plugin(
                {
                    "allow_emotion_reset_backdoor": False,
                    "allow_humanlike_reset_backdoor": False,
                    "allow_lifelike_learning_reset_backdoor": False,
                    "allow_moral_repair_reset_backdoor": False,
                    "allow_fallibility_reset_backdoor": False,
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
            self.assertFalse(
                asyncio.run(locked.reset_lifelike_learning_state(session_key="s1")),
            )
            self.assertFalse(
                asyncio.run(locked.reset_moral_repair_state(session_key="s1")),
            )
            self.assertFalse(
                asyncio.run(locked.reset_fallibility_state(session_key="s1")),
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
            self.assertTrue(
                asyncio.run(allowed.reset_lifelike_learning_state(session_key="s1")),
            )
            self.assertTrue(
                asyncio.run(allowed.reset_moral_repair_state(session_key="s1")),
            )
            self.assertTrue(
                asyncio.run(allowed.reset_fallibility_state(session_key="s1")),
            )
        finally:
            EmotionalStatePlugin._delete_state = original_delete_state
            EmotionalStatePlugin._delete_psychological_state = original_delete_psychological
            EmotionalStatePlugin._delete_humanlike_state = original_delete_humanlike
            EmotionalStatePlugin._delete_lifelike_learning_state = original_delete_lifelike
            EmotionalStatePlugin._delete_moral_repair_state = original_delete_moral_repair
            EmotionalStatePlugin._delete_fallibility_state = original_delete_fallibility

        self.assertEqual(
            deleted,
            [
                ("emotion", "s1"),
                ("psychological", "s1"),
                ("humanlike", "s1"),
                ("lifelike", "s1"),
                ("moral_repair", "s1"),
                ("fallibility", "s1"),
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


    def test_kv_key_sanitization_uses_shared_cache(self):
        self._install_astrbot_stubs()

        plugin = self._new_plugin()
        session_key = "room/alpha\\beta"

        self.assertEqual(plugin._kv_key(session_key), "emotion_state:room_alpha_beta")
        self.assertEqual(
            plugin._humanlike_kv_key(session_key),
            "humanlike_state:room_alpha_beta",
        )
        self.assertEqual(
            plugin._lifelike_learning_kv_key(session_key),
            "lifelike_learning:room_alpha_beta",
        )
        self.assertEqual(
            plugin._personality_drift_kv_key(session_key),
            "personality_drift:room_alpha_beta",
        )
        self.assertEqual(
            plugin._moral_repair_kv_key(session_key),
            "moral_repair_state:room_alpha_beta",
        )
        self.assertEqual(
            plugin._fallibility_kv_key(session_key),
            "fallibility_state:room_alpha_beta",
        )
        self.assertEqual(
            plugin._psychological_kv_key(session_key),
            "psychological_screening:room_alpha_beta",
        )
        self.assertEqual(plugin._safe_session_key_cache, {session_key: "room_alpha_beta"})


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

        async def fake_load_state(self, session_key, persona_profile=None, **kwargs):
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


    def test_humanlike_direct_public_api_is_always_on(self):
        self._install_astrbot_stubs()
        plugin = self._new_plugin()
        snapshot = asyncio.run(
            plugin.get_humanlike_snapshot(
                session_key="s1",
                include_prompt_fragment=True,
            ),
        )
        values = asyncio.run(plugin.get_humanlike_values(session_key="s1"))
        fragment = asyncio.run(plugin.get_humanlike_prompt_fragment(session_key="s1"))

        self.assertTrue(snapshot["enabled"])
        self.assertIn("prompt_fragment", snapshot)
        self.assertIn("energy", values)
        self.assertIn("humanlike", fragment.lower())


    def test_lifelike_direct_public_api_is_always_on(self):
        self._install_astrbot_stubs()
        plugin = self._new_plugin()
        snapshot = asyncio.run(
            plugin.get_lifelike_learning_snapshot(
                session_key="s-life",
                include_prompt_fragment=True,
            ),
        )
        policy = asyncio.run(
            plugin.get_lifelike_initiative_policy(session_key="s-life"),
        )
        fragment = asyncio.run(plugin.get_lifelike_prompt_fragment(session_key="s-life"))

        self.assertTrue(snapshot["enabled"])
        self.assertIn("prompt_fragment", snapshot)
        self.assertIn(policy["action"], {"brief_ack", "stay_silent", "ask_clarifying", "speak_now"})
        self.assertIn("lifelike", fragment.lower())


    def test_personality_drift_snapshot_is_always_on(self):
        self._install_astrbot_stubs()
        plugin = self._new_plugin()
        snapshot = asyncio.run(
            plugin.get_personality_drift_snapshot(
                session_key="s-drift",
                include_prompt_fragment=True,
            ),
        )

        self.assertTrue(snapshot["enabled"])
        self.assertIn("prompt_fragment", snapshot)


    def test_fallibility_direct_public_api_disabled_payloads(self):
        self._install_astrbot_stubs()
        from main import EmotionalStatePlugin

        async def fake_load_fallibility_state(self, session_key):
            raise AssertionError("disabled fallibility API must not load state")

        original_load_fallibility = EmotionalStatePlugin._load_fallibility_state
        EmotionalStatePlugin._load_fallibility_state = fake_load_fallibility_state
        try:
            plugin = self._new_plugin()
            snapshot = asyncio.run(
                plugin.get_fallibility_snapshot(
                    session_key="s-fallibility",
                    include_prompt_fragment=True,
                ),
            )
            values = asyncio.run(plugin.get_fallibility_values(session_key="s-fallibility"))
            fragment = asyncio.run(
                plugin.get_fallibility_prompt_fragment(session_key="s-fallibility"),
            )
        finally:
            EmotionalStatePlugin._load_fallibility_state = original_load_fallibility

        self.assertFalse(snapshot["enabled"])
        self.assertEqual(snapshot["reason"], "enable_fallibility_state is false")
        self.assertEqual(snapshot["prompt_fragment"], "")
        self.assertEqual(values, {})
        self.assertEqual(fragment, "")


    def test_personality_drift_cached_load_does_not_write_back(self):
        self._install_astrbot_stubs()
        from main import EmotionalStatePlugin
        from personality_drift_engine import PersonalityDriftState

        plugin = self._new_plugin({"enable_personality_drift": True})
        state = PersonalityDriftState.initial(persona_fingerprint="default")
        plugin._personality_drift_memory_cache["s-drift-cache"] = state

        async def fail_if_written(self, *args, **kwargs):
            raise AssertionError("cached personality drift load must not write KV")

        original_put = getattr(EmotionalStatePlugin, "put_kv_data", None)
        EmotionalStatePlugin.put_kv_data = fail_if_written
        try:
            loaded = asyncio.run(
                plugin._load_personality_drift_state("s-drift-cache"),
            )
        finally:
            if original_put is None:
                delattr(EmotionalStatePlugin, "put_kv_data")
            else:
                EmotionalStatePlugin.put_kv_data = original_put

        self.assertIs(loaded, state)


    def test_cached_emotion_and_aux_loads_do_not_write_back_on_passive_decay(self):
        self._install_astrbot_stubs()
        from emotion_engine import EmotionState
        from humanlike_engine import HumanlikeState
        from lifelike_learning_engine import LifelikeLearningState
        from main import EmotionalStatePlugin
        from moral_repair_engine import MoralRepairState
        from fallibility_engine import FallibilityState

        plugin = self._new_plugin(
            {
                "passive_load_fresh_seconds": 0.0,
                "enable_humanlike_state": True,
                "enable_lifelike_learning": True,
                "enable_moral_repair_state": True,
                "enable_fallibility_state": True,
            },
        )
        emotion = EmotionState.initial()
        emotion.updated_at = 1.0
        humanlike = HumanlikeState.initial()
        humanlike.updated_at = 1.0
        lifelike = LifelikeLearningState.initial()
        lifelike.updated_at = 1.0
        moral = MoralRepairState.initial()
        moral.updated_at = 1.0
        fallibility = FallibilityState.initial()
        fallibility.updated_at = 1.0
        plugin._memory_cache["s-cache"] = emotion
        plugin._humanlike_memory_cache["s-cache"] = humanlike
        plugin._lifelike_learning_memory_cache["s-cache"] = lifelike
        plugin._moral_repair_memory_cache["s-cache"] = moral
        plugin._fallibility_memory_cache["s-cache"] = fallibility

        async def fail_if_written(self, *args, **kwargs):
            raise AssertionError("cached passive reads must not write KV")

        original_put = getattr(EmotionalStatePlugin, "put_kv_data", None)
        EmotionalStatePlugin.put_kv_data = fail_if_written
        try:
            loaded_emotion = asyncio.run(plugin._load_state("s-cache"))
            loaded_humanlike = asyncio.run(plugin._load_humanlike_state("s-cache"))
            loaded_lifelike = asyncio.run(plugin._load_lifelike_learning_state("s-cache"))
            loaded_moral = asyncio.run(plugin._load_moral_repair_state("s-cache"))
            loaded_fallibility = asyncio.run(plugin._load_fallibility_state("s-cache"))
        finally:
            if original_put is None:
                delattr(EmotionalStatePlugin, "put_kv_data")
            else:
                EmotionalStatePlugin.put_kv_data = original_put

        self.assertGreater(loaded_emotion.updated_at, 1.0)
        self.assertGreater(loaded_humanlike.updated_at, 1.0)
        self.assertGreater(loaded_lifelike.updated_at, 1.0)
        self.assertGreater(loaded_moral.updated_at, 1.0)
        self.assertGreater(loaded_fallibility.updated_at, 1.0)
