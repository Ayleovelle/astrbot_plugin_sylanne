import unittest

from realtime_chat_input import (
    RealtimeInputSettings,
    build_realtime_input_fragment_injection,
    observe_realtime_input_fragment,
)


class RealtimeChatInputTests(unittest.TestCase):
    def test_short_fragments_emit_one_merged_intent_on_closing_particle(self):
        windows = {}
        settings = RealtimeInputSettings(max_window_seconds=3.2)
        payload = {}
        for index, text in enumerate(("你", "是", "🐷", "吗")):
            payload = observe_realtime_input_fragment(
                windows,
                session_key="s1",
                speaker_key="u1",
                text=text,
                now=100.0 + index * 0.2,
                settings=settings,
            )

        self.assertTrue(payload["should_inject"])
        self.assertEqual(payload["display_sequence"], "你 / 是 / 🐷 / 吗")
        self.assertEqual(payload["merged_intent"], "你 是 🐷 吗")
        injection = build_realtime_input_fragment_injection(payload)
        self.assertIn("sylanne_user_message_fragments", injection)
        self.assertIn("merged_intent=你 是 🐷 吗", injection)

    def test_timeout_and_speaker_change_start_new_windows(self):
        windows = {}
        settings = RealtimeInputSettings(max_window_seconds=1.0)
        observe_realtime_input_fragment(
            windows,
            session_key="s1",
            speaker_key="u1",
            text="你",
            now=100.0,
            settings=settings,
        )
        changed = observe_realtime_input_fragment(
            windows,
            session_key="s1",
            speaker_key="u2",
            text="是",
            now=100.2,
            settings=settings,
        )
        late = observe_realtime_input_fragment(
            windows,
            session_key="s1",
            speaker_key="u2",
            text="吗",
            now=104.0,
            settings=settings,
        )

        self.assertFalse(changed["should_inject"])
        self.assertFalse(late["should_inject"])


if __name__ == "__main__":
    unittest.main()
