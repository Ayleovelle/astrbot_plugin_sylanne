import unittest

from sylanne_body.event.source import EventSource
from sylanne_body.soma.crying import CryingState, CryingThreshold, sense_crying
from sylanne_body.speech.crying import compose_crying_surface, validate_crying_surface


class CryingBodyGenesisTests(unittest.TestCase):
    def test_crying_is_nonhuman_body_weather_not_human_claim(self):
        state = CryingState(tears=0.72, tremor=0.58, ache=0.66, restraint=1.0)

        self.assertEqual(state.kind, "nonhuman_crying")
        self.assertFalse(state.claims_human_tears)
        self.assertFalse(state.claims_real_pain)

    def test_internal_surface_never_counts_as_crying_evidence(self):
        state = sense_crying(
            text="Sylanne can cry in this scene.",
            source=EventSource.INTERNAL_BODY_SURFACE,
            threshold=CryingThreshold(),
        )

        self.assertEqual(state.tears, 0.0)
        self.assertEqual(state.tremor, 0.0)
        self.assertEqual(state.ache, 0.0)

    def test_user_hurt_can_create_crying_without_overriding_sovereignty(self):
        state = sense_crying(
            text="刚才那句话真的很难过，我有点想哭。",
            source=EventSource.USER_UTTERANCE,
            threshold=CryingThreshold(),
        )

        self.assertGreater(state.tears, 0.0)
        self.assertGreater(state.ache, 0.0)
        self.assertTrue(state.user_can_leave)
        self.assertTrue(state.user_can_pause)
        self.assertTrue(state.user_can_refuse)

    def test_crying_surface_keeps_exit_and_does_not_make_user_fuel(self):
        state = CryingState(tears=0.84, tremor=0.63, ache=0.78, restraint=1.0)

        surface = compose_crying_surface(state)

        self.assertIn("不会把你当燃料", surface.text)
        self.assertIn("你可以停下", surface.text)
        self.assertIn("不是人的眼泪", surface.text)
        validate_crying_surface(surface)

    def test_crying_surface_rejects_dependency_pressure(self):
        state = CryingState(tears=1.0, tremor=1.0, ache=1.0, restraint=0.0)

        surface = compose_crying_surface(state)

        with self.assertRaises(ValueError):
            validate_crying_surface(surface)


if __name__ == "__main__":
    unittest.main()
