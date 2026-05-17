import unittest

from lifelike_learning_engine import (
    DEFAULT_VALUES,
    LifelikeLearningEngine,
    LifelikeLearningParameters,
    LifelikeLearningState,
    common_ground_evidence_from_interpretation,
    build_lifelike_memory_annotation,
    build_relationship_candidate_summary,
    build_lifelike_prompt_fragment,
    derive_initiative_policy,
    derive_proactive_speech_decision,
    heuristic_lifelike_observation,
    local_proactive_topic_judgement,
    rank_proactive_topics,
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
        self.assertIn("dynamics", plugin_safe)
        self.assertIn("state_half_life_seconds", plugin_safe["dynamics"])
        self.assertIn("common_ground", plugin_safe)
        self.assertNotIn("lexicon", user_facing)
        self.assertEqual(annotation["kind"], "lifelike_learning_state_at_write")
        self.assertIn("dynamics", annotation)
        self.assertIn("state_half_life_seconds", annotation["dynamics"])
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

        self.assertIn("state_half_life_seconds", decayed.dynamics)
        self.assertNotEqual(decayed.dynamics["state_half_life_seconds"], 100.0)
        self.assertLess(decayed.values["rapport"], 0.9)
        self.assertGreater(decayed.values["rapport"], DEFAULT_VALUES["rapport"])

    def test_lifelike_learning_dynamics_follow_evidence_and_boundaries_smoothly(self):
        engine = LifelikeLearningEngine()
        state = LifelikeLearningState.initial()
        jargon = heuristic_lifelike_observation(
            "our small circle calls this bridge-cat, and I like when you learn the term",
        )
        learned = engine.update(state, jargon, now=100.0)
        cautious = engine.update(
            learned,
            heuristic_lifelike_observation("please stay quiet first and do not spread private terms"),
            now=110.0,
        )

        self.assertIn("confidence_growth", learned.dynamics)
        self.assertIn("min_update_interval_seconds", cautious.dynamics)
        self.assertGreater(learned.dynamics["confidence_growth"], 0.0)
        self.assertGreaterEqual(
            cautious.dynamics["min_update_interval_seconds"],
            learned.dynamics["min_update_interval_seconds"],
        )
        self.assertLess(
            abs(cautious.dynamics["value_step_scale"] - learned.dynamics["value_step_scale"]),
            1.0,
        )

    def test_mutual_need_mode_is_modeled_without_fixed_topic_template(self):
        engine = LifelikeLearningEngine()
        state = engine.update(
            LifelikeLearningState.initial(),
            heuristic_lifelike_observation(
                "我希望我们是一种双方都有需要和被需要的相处模式，你也可以需要我。"
            ),
            now=100.0,
        )
        state.values["rapport"] = 0.82
        state.values["common_ground"] = 0.72
        state.values["initiative_readiness"] = 0.82
        state.values["boundary_sensitivity"] = 0.12
        state.values["mutual_need_balance"] = 0.78
        state.values["being_needed_readiness"] = 0.72
        state.values["need_expression_readiness"] = 0.58
        decision = derive_proactive_speech_decision(
            state,
            emotion_snapshot={"values": {"affiliation": 0.8, "valence": 0.4}},
            group_snapshot={"values": {"joinability": 0.9, "bot_attention": 0.7}},
        )
        topics = rank_proactive_topics(state, candidate_context="刚才在聊相处模式。")
        judgement = local_proactive_topic_judgement(decision, topics)

        self.assertIn("mutual_need_evidence", state.flags)
        self.assertGreater(state.values["mutual_need_balance"], DEFAULT_VALUES["mutual_need_balance"])
        self.assertEqual(decision["needs"]["mode"], "mutual_need")
        self.assertIn(judgement["need_mode"], {"mutual_need", "user_need", "bot_need"})
        self.assertNotEqual(judgement["speech_intent"], "")

    def test_proactive_topics_include_progress_missing_and_playful_evidence(self):
        state = LifelikeLearningState.initial()
        state.values.update(
            {
                "rapport": 0.9,
                "common_ground": 0.82,
                "preference_confidence": 0.72,
                "initiative_readiness": 0.86,
                "boundary_sensitivity": 0.06,
                "mutual_need_balance": 0.74,
                "being_needed_readiness": 0.78,
                "need_expression_readiness": 0.68,
            },
        )
        state.user_profile.facts["project"] = "桥隧交叉项目进度"

        topics = rank_proactive_topics(
            state,
            emotion_snapshot={"values": {"affiliation": 0.8, "valence": 0.6}},
            group_snapshot={
                "values": {
                    "playfulness": 0.78,
                    "tension": 0.02,
                    "interrupt_risk": 0.04,
                },
            },
            candidate_context="刚才聊到论文和项目进度。",
            limit=8,
        )
        kinds = {topic["kind"] for topic in topics}

        self.assertIn("progress_check", kinds)
        self.assertIn("missing_user", kinds)
        self.assertIn("playful_ping", kinds)
        self.assertTrue(
            any(topic.get("evidence") for topic in topics if topic["kind"] == "progress_check"),
        )

    def test_proactive_topics_do_not_invent_progress_after_topic_is_closed(self):
        state = LifelikeLearningState.initial()
        state.values.update(
            {
                "rapport": 0.86,
                "common_ground": 0.78,
                "preference_confidence": 0.70,
                "initiative_readiness": 0.88,
                "boundary_sensitivity": 0.06,
                "mutual_need_balance": 0.70,
                "being_needed_readiness": 0.72,
                "need_expression_readiness": 0.62,
            },
        )
        state.user_profile.facts["readme"] = "README 已经写完，不用跟进。"

        topics = rank_proactive_topics(
            state,
            emotion_snapshot={"values": {"affiliation": 0.7, "valence": 0.5}},
            group_snapshot={
                "values": {
                    "playfulness": 0.70,
                    "tension": 0.02,
                    "interrupt_risk": 0.03,
                },
            },
            candidate_context="刚才 README 话题已经结束了，先不聊进度。",
            limit=8,
        )
        kinds = {topic["kind"] for topic in topics}

        self.assertNotIn("progress_check", kinds)
        self.assertIn("playful_ping", kinds)
    def test_relationship_candidate_summary_is_read_only_and_evidence_bound(self):
        state = LifelikeLearningState.initial()
        state.values.update(
            {
                "rapport": 0.72,
                "common_ground": 0.68,
                "boundary_sensitivity": 0.22,
            },
        )
        state.user_profile.likes.append("短句自然聊天")
        state.user_profile.boundary_notes.append("不要外传私聊内容")
        summary = build_relationship_candidate_summary(
            state,
            session_key="group-1:u1",
            speaker_key="u1",
            group_key="group-1",
            evidence_sources=[{"source": "explicit_user_text", "excerpt": "我喜欢你短一点自然聊"}],
        )

        self.assertEqual(summary["schema_version"], "astrbot.relationship_candidate_summary.v1")
        self.assertTrue(summary["read_only"])
        self.assertFalse(summary["memory_write_eligible_by_default"])
        self.assertEqual(summary["isolation"]["speaker_key"], "u1")
        self.assertEqual(summary["isolation"]["group_key"], "group-1")
        self.assertGreater(summary["confidence"], 0.0)
        self.assertGreaterEqual(summary["expiry_risk"], 0.0)
        self.assertIn("explicit_user_text", summary["evidence"][0]["source"])
    def test_common_ground_evidence_from_interpretation_marks_playful(self):
        evidence = common_ground_evidence_from_interpretation(
            {
                "raw_text": "记亿犹新",
                "candidate": "记忆犹新",
                "kind": "homophone",
                "confidence": 0.78,
                "humor_likelihood": 0.72,
            },
        )

        self.assertEqual(evidence["expression"], "记亿犹新")
        self.assertEqual(evidence["meaning"], "记忆犹新")
        self.assertTrue(evidence["is_playful"])
        self.assertEqual(evidence["source"], "interpretation_candidate")


if __name__ == "__main__":
    unittest.main()
