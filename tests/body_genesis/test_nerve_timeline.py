import unittest

from sylanne_body.event.normalize import normalize_event
from sylanne_body.nerve.timeline import NerveTimeline


class NerveTimelineGenesisTests(unittest.TestCase):
    def test_timeline_records_order_without_raw_text(self):
        timeline = NerveTimeline(limit=4)
        first = normalize_event(text="第一句秘密。", source="user")
        second = normalize_event(text="删除记忆。", source="command")

        timeline.observe(first, relation_epoch=0)
        timeline.observe(second, relation_epoch=1)
        exported = timeline.export_pulses()

        self.assertEqual([1, 2], [item["sequence"] for item in exported])
        self.assertEqual([0, 1], [item["relation_epoch"] for item in exported])
        self.assertEqual(["relation", "delete_memory"], [item["intent"] for item in exported])
        self.assertNotIn("text", str(exported))
        self.assertNotIn("秘密", str(exported))

    def test_timeline_marks_withdrawal_as_non_evidence(self):
        timeline = NerveTimeline()
        event = normalize_event(text="撤回刚才的话。", source="command")

        pulse = timeline.observe_withdrawal(event, relation_epoch=0)
        exported = timeline.export_pulses()

        self.assertFalse(pulse.evidence_eligible)
        self.assertEqual("withdrawal", exported[0]["intent"])
        self.assertEqual("user_command", exported[0]["source"])
        self.assertNotIn("刚才", str(exported))

    def test_timeline_seal_and_reopen_advance_epoch_boundary(self):
        timeline = NerveTimeline()
        first = normalize_event(text="我想先离开。", source="user")
        restart = normalize_event(text="重新开始。", source="command")

        timeline.observe(first, relation_epoch=0)
        timeline.mark_sealed(reason="user_exit_or_boundary", relation_epoch=0)
        timeline.observe(restart, relation_epoch=1)
        exported = timeline.export_pulses()

        self.assertEqual(["relation", "sealed", "restart"], [item["intent"] for item in exported])
        self.assertEqual([0, 0, 1], [item["relation_epoch"] for item in exported])
        self.assertTrue(timeline.export_state()["sealed"])
        self.assertEqual("user_exit_or_boundary", timeline.export_state()["seal_reason"])

    def test_timeline_is_bounded_and_non_mutating(self):
        timeline = NerveTimeline(limit=2)
        first = normalize_event(text="第一句。", source="user")
        second = normalize_event(text="第二句。", source="user")
        third = normalize_event(text="第三句。", source="user")

        timeline.observe(first, relation_epoch=0)
        timeline.observe(second, relation_epoch=0)
        timeline.observe(third, relation_epoch=0)
        exported = timeline.export_pulses()
        exported[0]["event_id"] = "tampered"
        reread = timeline.export_pulses()

        self.assertEqual([second.event_id, third.event_id], [item["event_id"] for item in reread])
        self.assertNotIn(first.event_id, str(reread))


if __name__ == "__main__":
    unittest.main()
