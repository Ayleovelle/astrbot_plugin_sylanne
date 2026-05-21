from __future__ import annotations

import unittest

from sylanne_alpha.dialogue import segment_dialogue


class SylanneAlphaDialogueTests(unittest.TestCase):
    def test_short_followup_keeps_same_segment_and_marks_continuation(self):
        first = segment_dialogue(session_key="room", text="我今天有点累", now=1.0)
        second = segment_dialogue(session_key="room", text="还有点想你", now=3.0, previous=first)

        self.assertEqual(first["schema_version"], "sylanne.alpha.dialogue.v1")
        self.assertEqual(second["segment_id"], first["segment_id"])
        self.assertEqual(second["relation"], "continuation")
        self.assertFalse(second["interruption"]["detected"])

    def test_topic_shift_starts_new_segment_and_detects_interruption(self):
        first = segment_dialogue(session_key="room", text="我今天有点累", now=1.0)
        second = segment_dialogue(
            session_key="room",
            text="换个话题，服务器又卡死了",
            now=2.0,
            previous=first,
            reply_in_progress=True,
        )

        self.assertNotEqual(second["segment_id"], first["segment_id"])
        self.assertEqual(second["relation"], "topic_shift")
        self.assertTrue(second["interruption"]["detected"])
        self.assertEqual(second["interruption"]["reason"], "user_topic_shift_during_reply")
        self.assertIn("cancel_realtime_dispatch", second["actions"])

    def test_withdrawal_marks_interruption_without_raw_export(self):
        result = segment_dialogue(session_key="room", text="撤回了一条消息", now=5.0, flags=["withdrawal"])

        self.assertEqual(result["relation"], "withdrawal")
        self.assertTrue(result["interruption"]["detected"])
        self.assertNotIn("raw_text", result)


if __name__ == "__main__":
    unittest.main()
