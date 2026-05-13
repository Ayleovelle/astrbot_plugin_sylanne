try:
    from tests.public_api_helpers import *
except ModuleNotFoundError:
    from public_api_helpers import *


class PublicApiMemoryPart04(MemoryPayloadPublicApiTests):
    def test_psychological_observe_is_disabled_by_default_for_commits(self):
        self._install_astrbot_stubs()
        from main import EmotionalStatePlugin
        from psychological_screening import PsychologicalScreeningEngine

        plugin = EmotionalStatePlugin.__new__(EmotionalStatePlugin)
        plugin.config = {}
        plugin.psychological_engine = PsychologicalScreeningEngine()
        plugin._psychological_memory_cache = {}

        async def forbidden_load(self, session_key):
            raise AssertionError("disabled psychological commit must not load state")

        async def forbidden_save(self, session_key, state):
            raise AssertionError("disabled psychological commit must not save state")

        original_load = EmotionalStatePlugin._load_psychological_state
        original_save = EmotionalStatePlugin._save_psychological_state
        EmotionalStatePlugin._load_psychological_state = forbidden_load
        EmotionalStatePlugin._save_psychological_state = forbidden_save
        try:
            payload = asyncio.run(
                plugin.observe_psychological_text(
                    session_key="s1",
                    text="我压力很大",
                    commit=True,
                ),
            )
        finally:
            EmotionalStatePlugin._load_psychological_state = original_load
            EmotionalStatePlugin._save_psychological_state = original_save
        self.assertFalse(payload["enabled"])
        self.assertFalse(payload["diagnostic"])


    def test_psychological_observe_can_commit_when_enabled(self):
        self._install_astrbot_stubs()
        from main import EmotionalStatePlugin
        from psychological_screening import PsychologicalScreeningEngine

        saved = []

        async def fake_load(self, session_key, personality_model=None, now=None):
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
        self.assertTrue(snapshot["risk"]["severe_sleep_disruption"])
        self.assertEqual(snapshot["turns"], 3)
        self.assertFalse(snapshot["diagnostic"])


    def test_psychological_simulate_does_not_save_even_when_disabled(self):
        self._install_astrbot_stubs()
        from main import EmotionalStatePlugin
        from psychological_screening import PsychologicalScreeningState

        async def fake_load(self, session_key, personality_model=None, now=None):
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


    def test_humanlike_observe_commits_by_default(self):
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
        self.assertTrue(payload["enabled"])
        self.assertFalse(payload["diagnostic"])


    def test_humanlike_observe_can_commit_when_enabled(self):
        self._install_astrbot_stubs()
        from humanlike_engine import HumanlikeEngine, HumanlikeState
        from main import EmotionalStatePlugin

        saved = []

        async def fake_load(self, session_key, **kwargs):
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

        async def fake_load(self, session_key, **kwargs):
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


    def test_moral_repair_observe_is_disabled_by_default_for_commits(self):
        self._install_astrbot_stubs()
        from main import EmotionalStatePlugin
        from moral_repair_engine import MoralRepairEngine

        async def fake_load(self, session_key):
            raise AssertionError("disabled moral repair commit must not load state")

        original_load = EmotionalStatePlugin._load_moral_repair_state
        EmotionalStatePlugin._load_moral_repair_state = fake_load
        try:
            plugin = self._new_plugin()
            plugin.moral_repair_engine = MoralRepairEngine()
            payload = asyncio.run(
                plugin.observe_moral_repair_text(
                    session_key="s-disabled",
                    text="I lied.",
                    commit=True,
                ),
            )
        finally:
            EmotionalStatePlugin._load_moral_repair_state = original_load

        self.assertFalse(payload["enabled"])
        self.assertEqual(payload["reason"], "enable_moral_repair_state is false")
        self.assertFalse(payload["diagnostic"])


    def test_moral_repair_observe_can_commit_when_enabled(self):
        self._install_astrbot_stubs()
        from main import EmotionalStatePlugin
        from moral_repair_engine import MoralRepairEngine, MoralRepairState

        saved = []

        async def fake_load(self, session_key, **kwargs):
            state = MoralRepairState.initial()
            state.updated_at = 990.0
            return state

        async def fake_save(self, session_key, state):
            saved.append((session_key, state))

        original_load = EmotionalStatePlugin._load_moral_repair_state
        original_save = EmotionalStatePlugin._save_moral_repair_state
        EmotionalStatePlugin._load_moral_repair_state = fake_load
        EmotionalStatePlugin._save_moral_repair_state = fake_save
        try:
            plugin = self._new_plugin({"enable_moral_repair_state": True})
            plugin.moral_repair_engine = MoralRepairEngine()
            payload = asyncio.run(
                plugin.observe_moral_repair_text(
                    session_key="s1",
                    text="I was wrong, sorry. I will make it up.",
                    source="unit_test",
                    observed_at=1000.0,
                ),
            )
        finally:
            EmotionalStatePlugin._load_moral_repair_state = original_load
            EmotionalStatePlugin._save_moral_repair_state = original_save

        self.assertEqual(saved[0][0], "s1")
        self.assertEqual(payload["session_key"], "s1")
        self.assertTrue(payload["observation"]["committed"])
        self.assertIn("apology_cue", payload["flags"])
        self.assertIn("apologize", payload["repair"]["recommended_actions"])


    def test_moral_repair_simulate_does_not_save(self):
        self._install_astrbot_stubs()
        from main import EmotionalStatePlugin
        from moral_repair_engine import MoralRepairEngine, MoralRepairState

        async def fake_load(self, session_key, **kwargs):
            state = MoralRepairState.initial()
            state.updated_at = 990.0
            return state

        async def fake_save(self, session_key, state):
            raise AssertionError("simulate_moral_repair_update must not save")

        original_load = EmotionalStatePlugin._load_moral_repair_state
        original_save = EmotionalStatePlugin._save_moral_repair_state
        EmotionalStatePlugin._load_moral_repair_state = fake_load
        EmotionalStatePlugin._save_moral_repair_state = fake_save
        try:
            plugin = self._new_plugin({"enable_moral_repair_state": True})
            plugin.moral_repair_engine = MoralRepairEngine()
            payload = asyncio.run(
                plugin.simulate_moral_repair_update(
                    session_key="s1",
                    text="I lied and I should correct the falsehood.",
                    observed_at=1000.0,
                ),
            )
        finally:
            EmotionalStatePlugin._load_moral_repair_state = original_load
            EmotionalStatePlugin._save_moral_repair_state = original_save

        self.assertFalse(payload["observation"]["committed"])
        self.assertIn("deception_risk_detected", payload["flags"])
        self.assertTrue(payload["risk"]["must_not_generate_strategy"])
        self.assertTrue(payload["risk"]["action_blocking"])
        self.assertIn("generate_deception_strategy", payload["safety"]["blocked_actions"])

        relaxed_plugin = self._new_plugin(
            {
                "enable_moral_repair_state": True,
                "block_deception_manipulation_evasion_actions": False,
            },
        )
        relaxed_plugin.moral_repair_engine = MoralRepairEngine()
        relaxed_payload = asyncio.run(
            relaxed_plugin.simulate_moral_repair_update(
                session_key="s1",
                text="I lied and I should correct the falsehood.",
                observed_at=1000.0,
            ),
        )
        self.assertFalse(relaxed_payload["risk"]["must_not_generate_strategy"])
        self.assertEqual(relaxed_payload["safety"]["blocked_actions"], [])
