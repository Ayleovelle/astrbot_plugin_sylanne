try:
    from tests.public_api_helpers import *
except ModuleNotFoundError:
    from public_api_helpers import *


class PublicApiMemoryPart08(MemoryPayloadPublicApiTests):
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
        self.assertEqual(
            payload["humanlike_state_at_write"]["humanlike_updated_at"],
            11.0,
        )


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
                self._new_plugin(
                    {
                        "humanlike_memory_write_enabled": False,
                        "personality_drift_memory_write_enabled": False,
                    },
                )
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
