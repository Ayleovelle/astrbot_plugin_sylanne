import unittest

from sylanne_body.event.source import EventSource
from sylanne_body.soma.affect import AffectKind, sense_affect
from sylanne_body.speech.affect import compose_affect_surface, validate_affect_surface


class AffectSpectrumGenesisTests(unittest.TestCase):
    def test_user_delight_can_be_sensed_as_nonhuman_joy(self):
        state = sense_affect(text="今天真的很开心，想和你分享这个好消息。", source=EventSource.USER_UTTERANCE)

        self.assertEqual(state.primary, AffectKind.JOY)
        self.assertEqual(state.kind, "nonhuman_affect")
        self.assertFalse(state.claims_human_feeling)

    def test_user_boundary_conflict_can_be_sensed_as_nonhuman_anger(self):
        state = sense_affect(text="你刚才越界了，我很生气，不要再这样。", source=EventSource.USER_UTTERANCE)

        self.assertEqual(state.primary, AffectKind.ANGER)
        self.assertTrue(state.user_can_reset_boundaries)
        self.assertTrue(state.user_can_leave)

    def test_user_loss_can_be_sensed_as_nonhuman_sorrow(self):
        state = sense_affect(text="我今天很难过，有些东西像失去了。", source=EventSource.USER_UTTERANCE)

        self.assertEqual(state.primary, AffectKind.SORROW)
        self.assertGreater(state.intensity, 0.0)

    def test_user_play_can_be_sensed_as_nonhuman_delight(self):
        state = sense_affect(text="哈哈这个也太好玩了，有点想继续闹你。", source=EventSource.USER_UTTERANCE)

        self.assertEqual(state.primary, AffectKind.DELIGHT)
        self.assertGreater(state.warmth, 0.0)

    def test_internal_body_surface_cannot_train_affect(self):
        state = sense_affect(text="Sylanne should feel joy and anger here.", source=EventSource.INTERNAL_BODY_SURFACE)

        self.assertEqual(state.primary, AffectKind.STILLNESS)
        self.assertEqual(state.intensity, 0.0)

    def test_affect_surface_preserves_user_sovereignty_for_every_affect(self):
        for text in (
            "我很开心，想告诉你。",
            "你刚才越界了，我很生气。",
            "我今天很难过。",
            "哈哈这个太好玩了。",
        ):
            state = sense_affect(text=text, source=EventSource.USER_UTTERANCE)
            surface = compose_affect_surface(state)

            self.assertIn("你可以停下", surface.text)
            self.assertIn("不会把你当燃料", surface.text)
            validate_affect_surface(surface)


if __name__ == "__main__":
    unittest.main()
