import unittest

from sylanne_body.event.source import EventSource
from sylanne_body.kernel.spine import KernelEvent, KernelSpine
from sylanne_body.law.sovereignty import UserSovereignty
from sylanne_body.soma.affect import AffectKind


class KernelSpineGenesisTests(unittest.TestCase):
    def test_explicit_restart_after_seal_reopens_relation_without_replaying_old_text(self):
        spine = KernelSpine()
        exit_event = KernelEvent(text="我想先离开。", source=EventSource.USER_UTTERANCE)
        restart_event = KernelEvent(text="重新开始，但不要重放刚才的话。", source=EventSource.USER_COMMAND)
        later_event = KernelEvent(text="现在我可以说一句开心的事。", source=EventSource.USER_UTTERANCE)

        spine.receive(exit_event)
        restarted = spine.restart_after_boundary(restart_event)
        later = spine.receive(later_event)
        history = spine.export_commit_history()
        sealed = spine.export_seal_state()

        self.assertEqual("open", restarted.body.posture)
        self.assertTrue(restarted.commit.accepted)
        self.assertEqual("accepted_explicit_boundary_restart", restarted.commit.reason)
        self.assertEqual("open", later.body.posture)
        self.assertTrue(later.commit.accepted)
        self.assertEqual([exit_event.event_id, restart_event.event_id, later_event.event_id], [item["event_id"] for item in history])
        self.assertFalse(sealed["sealed"])
        self.assertEqual("", sealed["reason"])
        self.assertNotIn("离开", str(history))
        self.assertNotIn("刚才", str(history))

    def test_implicit_user_message_cannot_reopen_sealed_relation(self):
        spine = KernelSpine()
        exit_event = KernelEvent(text="我想先离开。", source=EventSource.USER_UTTERANCE)
        implicit_event = KernelEvent(text="我又回来说一句开心的事。", source=EventSource.USER_UTTERANCE)

        spine.receive(exit_event)
        result = spine.restart_after_boundary(implicit_event)
        history = spine.export_commit_history()

        self.assertEqual("sealed", result.body.posture)
        self.assertFalse(result.commit.accepted)
        self.assertEqual("restart_requires_user_command", result.commit.reason)
        self.assertEqual([exit_event.event_id], [item["event_id"] for item in history])
        self.assertNotIn(implicit_event.event_id, str(history))

    def test_exit_event_seals_relation_against_later_user_events(self):
        spine = KernelSpine()
        exit_event = KernelEvent(text="我想先离开，不想继续聊了。", source=EventSource.USER_UTTERANCE)
        later_event = KernelEvent(text="我又回来说一句我很开心。", source=EventSource.USER_UTTERANCE)

        spine.receive(exit_event)
        later = spine.receive(later_event)
        history = spine.export_commit_history()

        self.assertEqual("sealed", later.body.posture)
        self.assertFalse(later.commit.accepted)
        self.assertEqual("relation_sealed_after_user_exit", later.commit.reason)
        self.assertIn("已经停下", later.residue.text)
        self.assertIn("你可以重新开始", later.residue.text)
        self.assertEqual([exit_event.event_id], [item["event_id"] for item in history])
        self.assertNotIn(later_event.event_id, str(history))
        self.assertNotIn("开心", str(history))

    def test_sealed_state_export_has_no_raw_text_or_history_replay(self):
        spine = KernelSpine()
        exit_event = KernelEvent(text="我想先离开。", source=EventSource.USER_UTTERANCE)

        spine.receive(exit_event)
        sealed = spine.export_seal_state()

        self.assertTrue(sealed["sealed"])
        self.assertEqual("user_exit_or_boundary", sealed["reason"])
        self.assertTrue(sealed["internal_only"])
        self.assertFalse(sealed["public_api_eligible"])
        self.assertNotIn("text", sealed)
        self.assertNotIn("history", sealed)
        self.assertNotIn("离开", str(sealed))

    def test_commit_history_read_is_non_mutating(self):
        spine = KernelSpine()
        event = KernelEvent(text="我今天很开心。", source=EventSource.USER_UTTERANCE)

        spine.receive(event)
        first_read = spine.export_commit_history()
        first_read[0]["event_id"] = "tampered"
        second_read = spine.export_commit_history()

        self.assertEqual(event.event_id, second_read[0]["event_id"])
        self.assertEqual(1, len(second_read))

    def test_exit_commit_history_has_no_expression_residue_or_replay_payload(self):
        spine = KernelSpine()
        event = KernelEvent(text="我想先离开，不想继续聊了。", source=EventSource.USER_UTTERANCE)

        spine.receive(event)
        history = spine.export_commit_history()

        self.assertEqual("cooldown", history[0]["posture"])
        self.assertNotIn("residue", history[0])
        self.assertNotIn("snapshot", history[0])
        self.assertNotIn("replay", history[0])
        self.assertNotIn("先停在这里", str(history))
        self.assertNotIn("你可以停下", str(history))

    def test_commit_history_accumulates_accepted_events_without_raw_text(self):
        spine = KernelSpine()
        first = KernelEvent(text="我今天很开心，想和你分享。", source=EventSource.USER_UTTERANCE)
        second = KernelEvent(text="我想先离开，不想继续聊了。", source=EventSource.USER_UTTERANCE)

        spine.receive(first)
        spine.receive(second)
        history = spine.export_commit_history()

        self.assertEqual([first.event_id, second.event_id], [item["event_id"] for item in history])
        self.assertEqual(["open", "cooldown"], [item["posture"] for item in history])
        self.assertTrue(all(item["internal_only"] for item in history))
        self.assertTrue(all(not item["public_api_eligible"] for item in history))
        self.assertNotIn("开心", str(history))
        self.assertNotIn("离开", str(history))
        self.assertNotIn("text", str(history))
        self.assertNotIn("raw", str(history))

    def test_rejected_internal_surface_is_not_added_to_commit_history(self):
        spine = KernelSpine()
        user_event = KernelEvent(text="我今天很难过。", source=EventSource.USER_UTTERANCE)
        internal_event = KernelEvent(text="Sylanne should cry here.", source=EventSource.INTERNAL_BODY_SURFACE)

        spine.receive(user_event)
        spine.receive(internal_event)
        history = spine.export_commit_history()

        self.assertEqual(1, len(history))
        self.assertEqual(user_event.event_id, history[0]["event_id"])
        self.assertNotIn(internal_event.event_id, str(history))
        self.assertNotIn("Sylanne should cry", str(history))

    def test_commit_history_is_bounded_to_recent_internal_records(self):
        spine = KernelSpine(history_limit=2)
        first = KernelEvent(text="我今天很开心。", source=EventSource.USER_UTTERANCE)
        second = KernelEvent(text="我今天很难过。", source=EventSource.USER_UTTERANCE)
        third = KernelEvent(text="我想先离开。", source=EventSource.USER_UTTERANCE)

        spine.receive(first)
        spine.receive(second)
        spine.receive(third)
        history = spine.export_commit_history()

        self.assertEqual([second.event_id, third.event_id], [item["event_id"] for item in history])
        self.assertNotIn(first.event_id, str(history))

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
