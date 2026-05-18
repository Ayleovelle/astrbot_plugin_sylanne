import unittest

from sylanne_body.event.source import EventSource
from sylanne_body.kernel.spine import KernelEvent, KernelSpine
from sylanne_body.law.sovereignty import UserSovereignty
from sylanne_body.soma.affect import AffectKind


class KernelSpineGenesisTests(unittest.TestCase):
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
