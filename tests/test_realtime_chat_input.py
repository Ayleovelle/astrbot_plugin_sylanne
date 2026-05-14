import unittest

from realtime_chat_input import (
    RealtimeInputSettings,
    build_realtime_input_fragment_injection,
    observe_realtime_input_fragment,
)


class RealtimeChatInputTests(unittest.TestCase):
    def test_fragment_observer_holds_obvious_split_phrase_until_merged(self):
        windows = {}
        settings = RealtimeInputSettings(max_window_seconds=3.2)

        first = observe_realtime_input_fragment(
            windows,
            session_key="s-split",
            speaker_key="u1",
            text="我！",
            now=100.0,
            settings=settings,
        )
        second = observe_realtime_input_fragment(
            windows,
            session_key="s-split",
            speaker_key="u1",
            text="就！",
            now=100.2,
            settings=settings,
        )
        third = observe_realtime_input_fragment(
            windows,
            session_key="s-split",
            speaker_key="u1",
            text="是！",
            now=100.4,
            settings=settings,
        )

        self.assertTrue(first["should_hold"])
        self.assertTrue(second["should_hold"])
        self.assertFalse(third.get("should_hold", False))
        self.assertTrue(third["should_inject"])
        self.assertEqual(third["display_sequence"], "我！ / 就！ / 是！")
        self.assertEqual(third["merged_intent"], "我！ 就！ 是！")

    def test_fragment_observer_emits_semantic_question_without_terminal_punctuation(self):
        windows = {}
        settings = RealtimeInputSettings(max_window_seconds=3.2)

        first = observe_realtime_input_fragment(
            windows,
            session_key="s-question",
            speaker_key="u1",
            text="我只是很纳闷",
            now=200.0,
            settings=settings,
        )
        second = observe_realtime_input_fragment(
            windows,
            session_key="s-question",
            speaker_key="u1",
            text="为啥你要问我",
            now=200.2,
            settings=settings,
        )
        third = observe_realtime_input_fragment(
            windows,
            session_key="s-question",
            speaker_key="u1",
            text="是从哪里看来的",
            now=200.4,
            settings=settings,
        )

        self.assertTrue(first["should_hold"])
        self.assertTrue(second["should_hold"])
        self.assertFalse(third.get("should_hold", False))
        self.assertTrue(third["should_inject"])
        self.assertEqual(
            third["merged_intent"],
            "我只是很纳闷 为啥你要问我 是从哪里看来的",
        )

    def test_fragment_observer_does_not_hold_common_standalone_short_reply(self):
        windows = {}
        payload = observe_realtime_input_fragment(
            windows,
            session_key="s-ack",
            speaker_key="u1",
            text="好！",
            now=300.0,
            settings=RealtimeInputSettings(max_window_seconds=3.2),
        )

        self.assertFalse(payload["should_hold"])
        self.assertFalse(payload["should_inject"])
        self.assertEqual(windows, {})

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

    def test_short_fragments_are_ordered_by_message_time_not_task_arrival(self):
        windows = {}
        settings = RealtimeInputSettings(max_window_seconds=3.2)
        observe_realtime_input_fragment(
            windows,
            session_key="s-out-of-order",
            speaker_key="u1",
            text="感觉",
            now=100.0,
            settings=settings,
        )
        observe_realtime_input_fragment(
            windows,
            session_key="s-out-of-order",
            speaker_key="u1",
            text="骂人",
            now=100.4,
            settings=settings,
        )
        payload = observe_realtime_input_fragment(
            windows,
            session_key="s-out-of-order",
            speaker_key="u1",
            text="你",
            now=100.2,
            settings=settings,
        )

        self.assertTrue(payload["should_hold"])
        self.assertEqual(payload["display_sequence"], "感觉 / 你 / 骂人")
        self.assertEqual(payload["merged_intent"], "感觉 你 骂人")

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

    def test_hanging_purpose_clause_waits_for_following_fragment(self):
        windows = {}
        settings = RealtimeInputSettings(max_window_seconds=5.0, max_fragments=6)
        sequence = [
            "你要这样想",
            "我大修",
            "是为了",
            "让你更好地去",
            "记住呀",
        ]
        payloads = [
            observe_realtime_input_fragment(
                windows,
                session_key="s-purpose",
                speaker_key="u1",
                text=text,
                now=float(index),
                settings=settings,
            )
            for index, text in enumerate(sequence)
        ]

        self.assertFalse(payloads[2]["should_inject"])
        self.assertTrue(payloads[2]["should_hold"])
        self.assertFalse(payloads[3]["should_inject"])
        self.assertTrue(payloads[3]["should_hold"])
        self.assertTrue(payloads[4]["should_inject"])
        self.assertIn("是为了", payloads[4]["merged_intent"])
        self.assertIn("让你更好地去", payloads[4]["merged_intent"])
        self.assertIn("记住呀", payloads[4]["merged_intent"])


if __name__ == "__main__":
    unittest.main()
