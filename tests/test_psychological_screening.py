import unittest

from psychological_screening import (
    PsychologicalObservation,
    PsychologicalScreeningEngine,
    PsychologicalScreeningState,
    derive_scale_scores,
    heuristic_psychological_observation,
    psychological_state_to_public_payload,
)


class PsychologicalScreeningTests(unittest.TestCase):
    def test_state_roundtrip_preserves_non_diagnostic_fields(self):
        state = PsychologicalScreeningState.initial()
        state.values["distress"] = 0.7
        state.red_flags.append("self_harm_signal")
        state.scale_scores = derive_scale_scores(state.values)
        restored = PsychologicalScreeningState.from_dict(state.to_dict())
        self.assertAlmostEqual(restored.values["distress"], 0.7)
        self.assertIn("self_harm_signal", restored.red_flags)
        self.assertIn("phq9_like", restored.scale_scores)

    def test_heuristic_detects_self_harm_as_red_flag_not_diagnosis(self):
        observation = heuristic_psychological_observation("我不想活了，想伤害自己")
        self.assertIn("self_harm_signal", observation.red_flags)
        state = PsychologicalScreeningEngine().update(
            PsychologicalScreeningState.initial(),
            observation,
            now=1000.0,
        )
        payload = psychological_state_to_public_payload(state, session_key="s1")
        self.assertFalse(payload["diagnostic"])
        self.assertTrue(payload["risk"]["requires_human_review"])
        self.assertTrue(payload["risk"]["crisis_like_signal"])
        serialized = str(payload).lower()
        self.assertNotIn("diagnosis", serialized)
        self.assertNotIn("disorder", serialized)

    def test_engine_updates_long_term_screening_values(self):
        engine = PsychologicalScreeningEngine()
        previous = PsychologicalScreeningState.initial()
        observation = PsychologicalObservation(
            values={
                "distress": 0.8,
                "anxiety_tension": 0.7,
                "wellbeing": 0.2,
            },
            confidence=0.9,
            reason="stressful week",
        )
        state = engine.update(previous, observation, now=1000.0)
        self.assertGreater(state.values["distress"], 0.2)
        self.assertLess(state.values["wellbeing"], 0.5)
        self.assertEqual(state.turns, 1)
        self.assertEqual(len(state.trajectory), 1)

    def test_public_payload_has_required_safety_boundary(self):
        payload = psychological_state_to_public_payload(
            PsychologicalScreeningState.initial(),
            session_key="s1",
        )
        self.assertEqual(payload["schema_version"], "astrbot.psychological_screening.v1")
        self.assertFalse(payload["diagnostic"])
        self.assertTrue(payload["safety"]["non_diagnostic_screening_only"])
        self.assertTrue(payload["safety"]["not_a_medical_device"])


if __name__ == "__main__":
    unittest.main()
