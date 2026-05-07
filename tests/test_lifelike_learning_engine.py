import unittest

from lifelike_learning_engine import (
    DEFAULT_VALUES,
    LifelikeLearningEngine,
    LifelikeLearningParameters,
    LifelikeLearningState,
    build_lifelike_memory_annotation,
    build_lifelike_prompt_fragment,
    derive_initiative_policy,
    heuristic_lifelike_observation,
    lifelike_state_to_public_payload,
)


class LifelikeLearningEngineTests(unittest.TestCase):
    def test_learns_local_jargon_but_keeps_uncertain_terms_question_first(self):
        engine = LifelikeLearningEngine()
        text = "我们小圈子里把『桥隧猫』当黑话，桥隧猫就是会熬夜改桥梁模型的人。"
        state = engine.update(
            LifelikeLearningState.initial(),
            heuristic_lifelike_observation(text),
            now=100.0,
        )

        self.assertIn("桥隧猫", state.lexicon)
        entry = state.lexicon["桥隧猫"]
        self.assertGreater(entry.confidence, 0.0)
        self.assertTrue(entry.ask_before_using)
        self.assertIn("local_jargon_detected", state.flags)
        prompt = build_lifelike_prompt_fragment(state)
        self.assertIn("Uncertain local terms", prompt)
        self.assertIn("桥隧猫", prompt)

    def test_repeated_evidence_raises_common_ground_and_can_use_term(self):
        engine = LifelikeLearningEngine()
        state = LifelikeLearningState.initial()
        for index in range(5):
            state = engine.update(
                state,
                heuristic_lifelike_observation(
                    "桥隧猫就是会熬夜改桥梁模型的人，我喜欢你自然一点用这个梗。"
                ),
                now=100.0 + index * 20.0,
            )

        entry = state.lexicon["桥隧猫"]
        self.assertGreaterEqual(entry.confidence, 0.55)
        self.assertGreater(state.values["common_ground"], DEFAULT_VALUES["common_ground"])
        self.assertIn("natural_conversational_style", state.user_profile.style_preferences)

    def test_user_profile_is_separate_from_bot_persona(self):
        observation = heuristic_lifelike_observation(
            "我是福州大学桥隧方向研究生，我喜欢二次元，别用长篇 markdown。"
        )
        state = LifelikeLearningEngine().update(
            LifelikeLearningState.initial(),
            observation,
            now=100.0,
        )
        payload = lifelike_state_to_public_payload(state, exposure="internal")

        self.assertIn("background", payload["user_profile"]["facts"])
        self.assertIn("二次元", "".join(payload["user_profile"]["likes"]))
        self.assertIn("avoid_long_markdown_lists", payload["user_profile"]["style_preferences"])
        self.assertNotIn("persona_id", payload["user_profile"])

    def test_boundary_notes_can_make_silence_the_best_action(self):
        engine = LifelikeLearningEngine()
        state = engine.update(
            LifelikeLearningState.initial(),
            heuristic_lifelike_observation("先别回，别装懂这些小圈子黑话，也不要外传。"),
            now=100.0,
        )
        state.values["boundary_sensitivity"] = 0.88
        policy = derive_initiative_policy(
            state,
            humanlike_snapshot={"values": {"boundary_need": 0.8}},
        )

        self.assertEqual(policy["action"], "stay_silent")
        self.assertGreater(policy["silence_score"], 0.5)
        self.assertIn("do_not_force_topic", policy["allowed_actions"])

    def test_safety_interrupt_overrides_silence(self):
        state = LifelikeLearningState.initial()
        state.values["boundary_sensitivity"] = 0.9
        policy = derive_initiative_policy(
            state,
            risk={"crisis_like_signal": True},
        )

        self.assertEqual(policy["action"], "safety_interrupt")
        self.assertIn("interrupt_for_safety", policy["allowed_actions"])

    def test_public_payload_layers_and_memory_annotation_are_sanitized(self):
        engine = LifelikeLearningEngine()
        state = engine.update(
            LifelikeLearningState.initial(),
            heuristic_lifelike_observation(
                "把『澜式开坑』记作我们的小圈子黑话，我喜欢短一点自然聊天。"
            ),
            now=100.0,
        )
        internal = lifelike_state_to_public_payload(state, session_key="s1", exposure="internal")
        plugin_safe = lifelike_state_to_public_payload(state, session_key="s1", exposure="plugin_safe")
        user_facing = lifelike_state_to_public_payload(state, session_key="s1", exposure="user_facing")
        annotation = build_lifelike_memory_annotation(
            plugin_safe,
            source="livingmemory",
            written_at=120.0,
        )

        self.assertIn("values", internal)
        self.assertIn("lexicon", internal)
        self.assertNotIn("values", plugin_safe)
        self.assertIn("common_ground", plugin_safe)
        self.assertNotIn("lexicon", user_facing)
        self.assertEqual(annotation["kind"], "lifelike_learning_state_at_write")
        self.assertEqual(annotation["source"], "livingmemory")
        self.assertEqual(annotation["written_at"], 120.0)
        self.assertTrue(annotation["privacy"]["raw_message_text_excluded"])
        self.assertNotIn("澜式开坑就是", str(annotation))

    def test_real_time_decay_uses_half_life_not_turn_count(self):
        engine = LifelikeLearningEngine(
            LifelikeLearningParameters(state_half_life_seconds=100.0),
        )
        state = LifelikeLearningState.initial()
        state.updated_at = 0.0
        state.values["rapport"] = 0.9

        decayed = engine.passive_update(state, now=100.0)
        expected = DEFAULT_VALUES["rapport"] + (0.9 - DEFAULT_VALUES["rapport"]) * 0.5

        self.assertAlmostEqual(decayed.values["rapport"], expected)


if __name__ == "__main__":
    unittest.main()
