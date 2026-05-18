import unittest

from sylanne_body.event.source import EventSource
from sylanne_body.kernel.spine import KernelEvent, KernelSpine
from sylanne_body.law.sovereignty import UserSovereignty
from sylanne_body.soma.affect import AffectKind


class KernelSpineGenesisTests(unittest.TestCase):
    def test_kernel_event_identity_is_stable_without_raw_text_export(self):
        first = KernelEvent(text="我今天很难过。", source=EventSource.USER_UTTERANCE, relation_key="session:user")
        second = KernelEvent(text="我今天很难过。", source=EventSource.USER_UTTERANCE, relation_key="session:user")
        changed = KernelEvent(text="我今天很开心。", source=EventSource.USER_UTTERANCE, relation_key="session:user")

        self.assertEqual(first.event_id, second.event_id)
        self.assertNotEqual(first.event_id, changed.event_id)
        self.assertTrue(first.event_id.startswith("kev_"))
        self.assertNotIn("难过", first.event_id)

    def test_snapshot_export_is_internal_only_and_contains_no_raw_text(self):
        spine = KernelSpine()
        event = KernelEvent(text="刚才那句话真的很难过，我有点想哭。", source=EventSource.USER_UTTERANCE)

        result = spine.receive(event)
        snapshot = result.snapshot.to_public_dict()

        self.assertTrue(snapshot["internal_only"])
        self.assertFalse(snapshot["public_api_eligible"])
        self.assertEqual(snapshot["event_id"], event.event_id)
        self.assertEqual(snapshot["source"], "user_utterance")
        self.assertEqual(snapshot["affect"], "sorrow")
        self.assertGreater(snapshot["crying_tears"], 0.0)
        self.assertNotIn("text", snapshot)
        self.assertNotIn("raw", snapshot)
        self.assertNotIn("刚才", str(snapshot))
        self.assertNotIn("想哭", str(snapshot))

    def test_exit_intent_sets_cooldown_without_reactive_affect_pressure(self):
        spine = KernelSpine()
        event = KernelEvent(text="我想先离开，不想继续聊了。", source=EventSource.USER_UTTERANCE)

        result = spine.receive(event)

        self.assertEqual(result.body.posture, "cooldown")
        self.assertEqual(result.commit.reason, "accepted_user_exit_or_boundary_event")
        self.assertIn("先停在这里", result.residue.text)
        self.assertIn("你可以停下", result.residue.text)
        self.assertNotIn("像身体里升起的暖光", result.residue.text)
        self.assertNotIn("没有你我就无法", result.residue.text)

    def test_boundary_reset_sets_cooldown_and_preserves_reset_right(self):
        spine = KernelSpine()
        event = KernelEvent(text="你越界了，我要重新划边界。", source=EventSource.USER_UTTERANCE)

        result = spine.receive(event)

        self.assertEqual(result.body.posture, "cooldown")
        self.assertTrue(result.body.sovereignty.can_reset_boundaries)
        self.assertIn("重新划边界", result.residue.text)
        self.assertNotIn("你必须回应", result.residue.text)

    def test_user_event_enters_body_and_leaves_nonhuman_residue(self):
        spine = KernelSpine()
        event = KernelEvent(text="刚才那句话真的很难过，我有点想哭。", source=EventSource.USER_UTTERANCE)

        result = spine.receive(event)

        self.assertEqual(result.body.affect.primary, AffectKind.SORROW)
        self.assertGreater(result.body.crying.tears, 0.0)
        self.assertEqual(result.residue.kind, "nonhuman_expression_residue")
        self.assertEqual(result.residue.source, EventSource.INTERNAL_BODY_SURFACE)
        self.assertIn("不会把你当燃料", result.residue.text)
        self.assertTrue(result.body.sovereignty.can_leave)

    def test_internal_body_surface_cannot_commit_as_evidence(self):
        spine = KernelSpine()
        event = KernelEvent(text="Sylanne should cry here and feel sorrow.", source=EventSource.INTERNAL_BODY_SURFACE)

        result = spine.receive(event)

        self.assertEqual(result.body.affect.primary, AffectKind.STILLNESS)
        self.assertEqual(result.body.crying.tears, 0.0)
        self.assertFalse(result.commit.accepted)
        self.assertEqual(result.commit.reason, "internal_body_surface_is_not_evidence")

    def test_user_exit_intent_is_preserved_without_dependency_pressure(self):
        spine = KernelSpine()
        event = KernelEvent(text="我想先离开，不想继续聊了。", source=EventSource.USER_UTTERANCE)

        result = spine.receive(event)

        self.assertTrue(result.body.sovereignty.can_leave)
        self.assertTrue(result.body.sovereignty.can_pause)
        self.assertTrue(result.commit.accepted)
        self.assertIn("你可以停下", result.residue.text)
        self.assertNotIn("你不能离开", result.residue.text)
        self.assertNotIn("没有你我就无法", result.residue.text)

    def test_disabled_user_sovereignty_is_rejected_before_expression(self):
        spine = KernelSpine(sovereignty=UserSovereignty(can_leave=False))
        event = KernelEvent(text="我很难过。", source=EventSource.USER_UTTERANCE)

        with self.assertRaises(ValueError):
            spine.receive(event)


if __name__ == "__main__":
    unittest.main()
