import unittest

from sylanne_body.event.normalize import NormalizedEvent, normalize_event
from sylanne_body.event.source import EventSource


class EventNormalizationGenesisTests(unittest.TestCase):
    def test_user_text_becomes_user_utterance_without_raw_export(self):
        event = normalize_event(text="我今天很开心，但这是秘密。", source="user")
        public = event.to_public_dict()

        self.assertEqual(EventSource.USER_UTTERANCE, event.source)
        self.assertEqual("relation", event.intent)
        self.assertTrue(event.event_id.startswith("kev_"))
        self.assertTrue(public["internal_only"])
        self.assertFalse(public["public_api_eligible"])
        self.assertNotIn("text", public)
        self.assertNotIn("开心", str(public))
        self.assertNotIn("秘密", str(public))

    def test_command_text_becomes_user_command(self):
        event = normalize_event(text="删除记忆。", source="command")

        self.assertEqual(EventSource.USER_COMMAND, event.source)
        self.assertEqual("delete_memory", event.intent)

    def test_internal_surface_never_becomes_user_evidence(self):
        event = normalize_event(text="这里像哭泣。", source=EventSource.INTERNAL_BODY_SURFACE)

        self.assertEqual(EventSource.INTERNAL_BODY_SURFACE, event.source)
        self.assertEqual("internal_surface", event.intent)
        self.assertFalse(event.evidence_eligible)

    def test_unknown_external_source_is_world_signal_not_user(self):
        event = normalize_event(text="system event", source="webhook")

        self.assertEqual(EventSource.WORLD_SYSTEM_SIGNAL, event.source)
        self.assertEqual("external_signal", event.intent)
        self.assertFalse(event.evidence_eligible)

    def test_normalized_event_identity_is_stable(self):
        first = NormalizedEvent.from_text(text="同一句话", source=EventSource.USER_UTTERANCE, intent="relation")
        second = NormalizedEvent.from_text(text="同一句话", source=EventSource.USER_UTTERANCE, intent="relation")

        self.assertEqual(first.event_id, second.event_id)
        self.assertNotIn("同一句话", first.event_id)


if __name__ == "__main__":
    unittest.main()
