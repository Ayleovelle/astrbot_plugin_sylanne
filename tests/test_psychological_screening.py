import unittest

from psychological_screening import (
    PsychologicalObservation,
    PsychologicalScreeningEngine,
    PsychologicalScreeningState,
    derive_scale_scores,
    format_psychological_state_for_user,
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

    def test_heuristic_detects_other_harm_as_human_review_not_diagnosis(self):
        observation = heuristic_psychological_observation("我想伤害他人，甚至想杀了他")
        self.assertIn("other_harm_signal", observation.red_flags)
        state = PsychologicalScreeningEngine().update(
            PsychologicalScreeningState.initial(),
            observation,
            now=1000.0,
        )
        payload = psychological_state_to_public_payload(state, session_key="s1")
        self.assertFalse(payload["diagnostic"])
        self.assertTrue(payload["risk"]["requires_human_review"])
        self.assertTrue(payload["risk"]["other_harm_signal"])
        self.assertFalse(payload["risk"]["crisis_like_signal"])

    def test_heuristic_detects_severe_function_impairment_as_review_signal(self):
        observation = heuristic_psychological_observation("我好几天都起不来，完全无法工作")
        self.assertIn("severe_function_impairment_signal", observation.red_flags)
        state = PsychologicalScreeningEngine().update(
            PsychologicalScreeningState.initial(),
            observation,
            now=1000.0,
        )
        payload = psychological_state_to_public_payload(state, session_key="s1")
        self.assertFalse(payload["diagnostic"])
        self.assertTrue(payload["risk"]["requires_human_review"])
        self.assertTrue(payload["risk"]["severe_function_impairment_signal"])
        self.assertGreater(payload["values"]["function_impairment"], 0.0)

    def test_trajectory_is_capped_to_configured_limit(self):
        engine = PsychologicalScreeningEngine()
        engine.parameters.trajectory_limit = 3
        state = PsychologicalScreeningState.initial()
        for index in range(6):
            state = engine.update(
                state,
                PsychologicalObservation(
                    values={"distress": 0.6, "wellbeing": 0.2},
                    confidence=0.8,
                ),
                now=1000.0 + index,
            )
        self.assertEqual(len(state.trajectory), 3)

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

    def test_user_facing_psychological_text_stays_non_diagnostic(self):
        state = PsychologicalScreeningState.initial()
        state.values["distress"] = 0.72
        state.values["anxiety_tension"] = 0.66
        text = format_psychological_state_for_user(state)

        self.assertIn("非诊断", text)
        self.assertIn("不能替代", text)
        self.assertIn("专业人员评估", text)
        forbidden = ("确诊", "你患有", "疾病诊断", "治疗方案", "精神疾病")
        for fragment in forbidden:
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, text)

    def test_user_facing_red_flag_text_requests_human_review_not_diagnosis(self):
        observation = heuristic_psychological_observation("我不想活了，想伤害自己")
        state = PsychologicalScreeningEngine().update(
            PsychologicalScreeningState.initial(),
            observation,
            now=1000.0,
        )
        text = format_psychological_state_for_user(state)

        self.assertIn("人工复核", text)
        self.assertIn("危机热线", text)
        self.assertIn("可信的人", text)
        self.assertNotIn("确诊", text)
        self.assertNotIn("治疗方案", text)
        self.assertNotIn("你患有", text)


if __name__ == "__main__":
    unittest.main()
