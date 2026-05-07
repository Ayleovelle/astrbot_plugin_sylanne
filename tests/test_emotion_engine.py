import unittest

from emotion_engine import (
    EmotionEngine,
    EmotionObservation,
    EmotionParameters,
    EmotionState,
    apply_persona_to_parameters,
    build_emotion_memory_payload,
    build_persona_profile,
    consequence_state_to_public_payload,
    emotion_state_to_public_payload,
    extract_json_object,
    observation_from_llm_text,
    persona_profile_to_public_payload,
    relationship_state_to_public_payload,
)


class EmotionEngineTests(unittest.TestCase):
    def test_extract_json_from_fenced_text(self):
        parsed = extract_json_object('```json\n{"confidence": 0.8}\n```')
        self.assertEqual(parsed["confidence"], 0.8)

    def test_observation_from_llm_text_accepts_dimensions(self):
        observation = observation_from_llm_text(
            """
            {
              "label": "embarrassed",
              "dimensions": {
                "valence": -0.1,
                "arousal": 0.7,
                "dominance": -0.3,
                "goal_congruence": -0.2,
                "certainty": -0.1,
                "control": -0.4,
                "affiliation": 0.2
              },
              "confidence": 0.75,
              "reason": "test"
            }
            """,
        )
        self.assertIsNotNone(observation)
        self.assertAlmostEqual(observation.values["arousal"], 0.7)
        self.assertEqual(observation.label, "embarrassed")

    def test_observation_from_llm_text_preserves_relationship_decision(self):
        observation = observation_from_llm_text(
            """
            {
              "label": "anger",
              "dimensions": {"valence": -0.5, "arousal": 0.5},
              "confidence": 0.8,
              "appraisal": {
                "relationship_decision": {
                  "decision": "cold_war",
                  "intensity": 0.7,
                  "forgiveness": 0.1,
                  "relationship_importance": 0.4,
                  "reason": "test"
                }
              }
            }
            """,
        )
        self.assertEqual(
            observation.appraisal["relationship_decision"]["decision"],
            "cold_war",
        )

    def test_observation_from_llm_text_preserves_conflict_analysis(self):
        observation = observation_from_llm_text(
            """
            {
              "label": "hurt",
              "dimensions": {"valence": -0.4, "arousal": 0.2},
              "confidence": 0.8,
              "appraisal": {
                "conflict_analysis": {
                  "cause": "user_fault",
                  "fault_severity": 0.8,
                  "user_acknowledged": true,
                  "apology_sincerity": 0.7,
                  "repaired": true,
                  "repair_quality": 0.9,
                  "repeat_offense": 0.1,
                  "bot_whim_level": 0.0,
                  "reason": "用户承认并补救。"
                }
              }
            }
            """,
        )
        conflict = observation.appraisal["conflict_analysis"]
        self.assertEqual(conflict["cause"], "user_fault")
        self.assertTrue(conflict["repaired"])

    def test_conflict_analysis_derives_repair_status(self):
        payload = relationship_state_to_public_payload(
            {
                "conflict_analysis": {
                    "cause": "user_fault",
                    "fault_severity": 0.7,
                    "user_acknowledged": True,
                    "apology_sincerity": 0.8,
                    "repaired": True,
                    "repair_quality": 0.9,
                    "repeat_offense": 0.0,
                    "bot_whim_level": 0.0,
                    "apology_completeness": {
                        "responsibility_acknowledgement": 0.9,
                        "harm_acknowledgement": 0.8,
                        "remorse": 0.9,
                        "repair_offer": 0.8,
                        "future_commitment": 0.7,
                    },
                    "restorative_action": 0.86,
                    "trust_damage": 0.1,
                    "evidence": {
                        "primary_theory": "forgiveness",
                        "citation_ids": ["KB0584"],
                        "evidence_strength": "moderate",
                        "uncertainty_reason": "",
                    },
                },
            },
        )
        self.assertEqual(payload["repair_status"], "restored")
        self.assertGreater(payload["repair_signal"], 0.85)
        self.assertLess(payload["grievance_score"], 0.2)
        self.assertEqual(
            payload["conflict_analysis"]["evidence"]["primary_theory"],
            "forgiveness",
        )

    def test_conflict_analysis_supports_rich_appraisal_fields(self):
        payload = relationship_state_to_public_payload(
            {
                "conflict_analysis": {
                    "cause": "user_fault",
                    "fault_severity": 0.6,
                    "perceived_intentionality": 0.7,
                    "responsibility_attribution": {
                        "target": "user",
                        "confidence": 0.8,
                    },
                    "controllability": 0.6,
                    "norm_violation_type": ["boundary_crossing"],
                    "trust_damage": 0.7,
                    "ambiguity_level": 0.2,
                    "misread_likelihood": 0.1,
                    "withdrawal_motive": "self_protection",
                    "boundary_legitimacy": 0.8,
                    "emotion_regulation_load": 0.5,
                    "evidence": {
                        "primary_theory": "appraisal",
                        "citation_ids": ["KB0031", "KB0009"],
                        "evidence_strength": "strong",
                    },
                },
            },
        )
        conflict = payload["conflict_analysis"]
        self.assertEqual(conflict["responsibility_attribution"]["target"], "user")
        self.assertIn("boundary_crossing", conflict["norm_violation_type"])
        self.assertEqual(conflict["withdrawal_motive"], "self_protection")
        self.assertGreater(conflict["grievance_score"], 0.5)

    def test_update_moves_state_toward_observation(self):
        engine = EmotionEngine()
        previous = EmotionState.initial()
        previous.updated_at = 1000.0
        observation = EmotionObservation(
            values={
                "valence": 0.8,
                "arousal": 0.6,
                "dominance": 0.4,
                "goal_congruence": 0.7,
                "certainty": 0.5,
                "control": 0.5,
                "affiliation": 0.8,
            },
            confidence=0.9,
            label="warm",
        )
        updated = engine.update(previous, observation, now=1010.0)
        self.assertGreater(updated.values["valence"], previous.values["valence"])
        self.assertGreater(updated.last_alpha, 0)
        self.assertLessEqual(updated.values["valence"], 1.0)

    def test_state_roundtrip(self):
        state = EmotionState.initial()
        restored = EmotionState.from_dict(state.to_dict())
        self.assertEqual(restored.turns, state.turns)
        self.assertIn("valence", restored.values)

    def test_persona_profile_changes_baseline(self):
        warm = build_persona_profile(
            persona_id="warm",
            name="warm",
            text="温柔 友好 关心 用户，乐观 开朗",
        )
        shy = build_persona_profile(
            persona_id="shy",
            name="shy",
            text="害羞 内向 迟疑 紧张，说话谨慎",
        )
        self.assertNotEqual(warm.fingerprint, shy.fingerprint)
        self.assertGreater(warm.baseline["affiliation"], shy.baseline["affiliation"])
        self.assertLess(shy.baseline["dominance"], warm.baseline["dominance"])

    def test_persona_bias_changes_parameters(self):
        profile = build_persona_profile(
            persona_id="volatile",
            name="volatile",
            text="情绪化 敏感 激动 冲动",
        )
        engine = EmotionEngine()
        biased = apply_persona_to_parameters(engine.parameters, profile)
        self.assertGreaterEqual(biased.reactivity, engine.parameters.reactivity)

    def test_update_records_persona_fingerprint(self):
        profile = build_persona_profile(
            persona_id="careful",
            name="careful",
            text="认真 负责 谨慎 可靠",
        )
        engine = EmotionEngine(baseline=profile.baseline)
        previous = EmotionState.initial(profile)
        previous.updated_at = 1000.0
        state = engine.update(
            previous,
            EmotionObservation(values=profile.baseline, confidence=0.6),
            profile=profile,
            now=1010.0,
        )
        self.assertEqual(state.persona_fingerprint, profile.fingerprint)

    def test_anger_state_triggers_boundary_consequence(self):
        engine = EmotionEngine()
        previous = EmotionState.initial()
        previous.updated_at = 1000.0
        state = engine.update(
            previous,
            EmotionObservation(
                values={
                    "valence": -0.8,
                    "arousal": 0.8,
                    "dominance": 0.8,
                    "goal_congruence": -0.7,
                    "certainty": 0.7,
                    "control": 0.4,
                    "affiliation": -0.2,
                },
                confidence=0.95,
                label="anger",
            ),
            now=1010.0,
        )
        self.assertIn("direct_boundary", state.consequences.active_effects)
        self.assertGreater(state.consequences.values["confrontation"], 0.0)

    def test_low_affiliation_negative_state_triggers_cold_war(self):
        engine = EmotionEngine()
        previous = EmotionState.initial()
        previous.updated_at = 1000.0
        previous.values.update(
            valence=-0.75,
            arousal=-0.45,
            dominance=-0.15,
            goal_congruence=-0.55,
            certainty=0.35,
            control=-0.45,
            affiliation=-0.75,
        )
        state = engine.update(
            previous,
            EmotionObservation(
                values=previous.values,
                confidence=0.9,
                label="hurt_withdrawal",
            ),
            now=1010.0,
        )
        self.assertIn("cold_war", state.consequences.active_effects)
        self.assertGreater(state.consequences.values["withdrawal"], 0.0)
        self.assertGreaterEqual(state.consequences.active_effects["cold_war"], 1700)

    def test_llm_relationship_decision_can_forgive_instead_of_cold_war(self):
        engine = EmotionEngine()
        previous = EmotionState.initial()
        previous.updated_at = 1000.0
        previous.consequences.updated_at = 1000.0
        previous.consequences.active_effects["cold_war"] = 1200
        previous.consequences.effect_expires_at["cold_war"] = 2200.0
        observation = EmotionObservation(
            values={
                "valence": -0.7,
                "arousal": -0.45,
                "dominance": -0.1,
                "goal_congruence": -0.55,
                "certainty": 0.25,
                "control": -0.4,
                "affiliation": -0.65,
            },
            confidence=0.9,
            label="hurt_but_forgiving",
            appraisal={
                "relationship_decision": {
                    "decision": "forgive",
                    "intensity": 0.8,
                    "forgiveness": 0.9,
                    "relationship_importance": 0.8,
                    "reason": "用户已经认真道歉。",
                },
            },
        )
        state = engine.update(previous, observation, now=1010.0)
        self.assertNotIn("cold_war", state.consequences.active_effects)
        self.assertLess(state.consequences.values["withdrawal"], 0.5)
        self.assertLess(state.consequences.values["rumination"], 0.5)
        self.assertGreater(state.consequences.values["repair"], 0.0)
        self.assertGreater(state.consequences.values["approach"], 0.0)

    def test_llm_relationship_decision_can_escalate_to_cold_war(self):
        engine = EmotionEngine()
        previous = EmotionState.initial()
        previous.updated_at = 1000.0
        observation = EmotionObservation(
            values={
                "valence": -0.45,
                "arousal": 0.1,
                "dominance": -0.1,
                "goal_congruence": -0.2,
                "certainty": 0.4,
                "control": -0.2,
                "affiliation": -0.2,
            },
            confidence=0.85,
            label="hurt",
            appraisal={
                "relationship_decision": {
                    "decision": "cold_war",
                    "intensity": 0.75,
                    "forgiveness": 0.1,
                    "relationship_importance": 0.3,
                    "reason": "用户持续冒犯且没有修复信号。",
                },
            },
        )
        state = engine.update(previous, observation, now=1010.0)
        self.assertIn("cold_war", state.consequences.active_effects)
        self.assertGreater(state.consequences.values["withdrawal"], 0.0)

    def test_conflict_user_fault_unrepaired_strengthens_boundary(self):
        engine = EmotionEngine()
        previous = EmotionState.initial()
        previous.updated_at = 1000.0
        observation = EmotionObservation(
            values={
                "valence": -0.35,
                "arousal": 0.25,
                "dominance": 0.1,
                "goal_congruence": -0.25,
                "certainty": 0.6,
                "control": 0.2,
                "affiliation": -0.15,
            },
            confidence=0.85,
            label="offended",
            appraisal={
                "relationship_decision": {
                    "decision": "boundary",
                    "intensity": 0.35,
                    "forgiveness": 0.1,
                    "relationship_importance": 0.4,
                    "reason": "需要说明问题。",
                },
                "conflict_analysis": {
                    "cause": "user_fault",
                    "fault_severity": 0.9,
                    "perceived_intentionality": 0.7,
                    "controllability": 0.7,
                    "trust_damage": 0.4,
                    "boundary_legitimacy": 0.8,
                    "user_acknowledged": False,
                    "apology_sincerity": 0.0,
                    "repaired": False,
                    "repair_quality": 0.0,
                    "repeat_offense": 0.8,
                    "bot_whim_level": 0.0,
                    "reason": "用户重复犯错且没有补救。",
                },
            },
        )
        state = engine.update(previous, observation, now=1010.0)
        self.assertIn("direct_boundary", state.consequences.active_effects)
        self.assertGreater(state.consequences.values["confrontation"], 0.5)

    def test_conflict_repaired_user_fault_clears_cold_war(self):
        engine = EmotionEngine()
        previous = EmotionState.initial()
        previous.updated_at = 1000.0
        previous.consequences.updated_at = 1000.0
        previous.consequences.active_effects["cold_war"] = 1200
        previous.consequences.effect_expires_at["cold_war"] = 2200.0
        previous.consequences.values["withdrawal"] = 0.9
        previous.consequences.values["rumination"] = 0.8
        observation = EmotionObservation(
            values={
                "valence": -0.4,
                "arousal": 0.05,
                "dominance": -0.1,
                "goal_congruence": -0.2,
                "certainty": 0.5,
                "control": 0.2,
                "affiliation": 0.1,
            },
            confidence=0.85,
            label="softening",
            appraisal={
                "relationship_decision": {
                    "decision": "repair",
                    "intensity": 0.6,
                    "forgiveness": 0.75,
                    "relationship_importance": 0.8,
                    "reason": "用户愿意修正。",
                },
                "conflict_analysis": {
                    "cause": "user_fault",
                    "fault_severity": 0.7,
                    "user_acknowledged": True,
                    "apology_sincerity": 0.8,
                    "repaired": True,
                    "repair_quality": 0.85,
                    "repeat_offense": 0.1,
                    "bot_whim_level": 0.0,
                    "reason": "错误已经被承认并补救。",
                },
            },
        )
        state = engine.update(previous, observation, now=1010.0)
        self.assertNotIn("cold_war", state.consequences.active_effects)
        self.assertLess(state.consequences.values["withdrawal"], 0.7)
        self.assertLess(state.consequences.values["rumination"], 0.7)

    def test_conflict_bot_whim_reduces_cold_war(self):
        engine = EmotionEngine()
        previous = EmotionState.initial()
        previous.updated_at = 1000.0
        observation = EmotionObservation(
            values={
                "valence": -0.65,
                "arousal": -0.35,
                "dominance": -0.1,
                "goal_congruence": -0.4,
                "certainty": 0.2,
                "control": -0.3,
                "affiliation": -0.55,
            },
            confidence=0.85,
            label="moody",
            appraisal={
                "relationship_decision": {
                    "decision": "cold_war",
                    "intensity": 0.6,
                    "forgiveness": 0.2,
                    "relationship_importance": 0.7,
                    "reason": "他/她一时任性。",
                },
                "conflict_analysis": {
                    "cause": "bot_whim",
                    "fault_severity": 0.1,
                    "user_acknowledged": False,
                    "apology_sincerity": 0.0,
                    "repaired": False,
                    "repair_quality": 0.0,
                    "repeat_offense": 0.0,
                    "bot_whim_level": 0.9,
                    "reason": "主要是他/她任性，不应惩罚用户。",
                },
            },
        )
        state = engine.update(previous, observation, now=1010.0)
        self.assertNotIn("cold_war", state.consequences.active_effects)
        self.assertGreater(state.consequences.values["repair"], 0.0)

    def test_conflict_bot_misread_clears_existing_cold_war_and_residue(self):
        engine = EmotionEngine()
        previous = EmotionState.initial()
        previous.updated_at = 1000.0
        previous.consequences.updated_at = 1000.0
        previous.consequences.active_effects["cold_war"] = 1200
        previous.consequences.effect_expires_at["cold_war"] = 2200.0
        previous.consequences.values["withdrawal"] = 0.9
        previous.consequences.values["rumination"] = 0.85
        observation = EmotionObservation(
            values={
                "valence": -0.55,
                "arousal": -0.25,
                "dominance": -0.1,
                "goal_congruence": -0.3,
                "certainty": -0.2,
                "control": -0.2,
                "affiliation": -0.45,
            },
            confidence=0.85,
            label="misread_softening",
            appraisal={
                "relationship_decision": {
                    "decision": "cold_war",
                    "intensity": 0.55,
                    "forgiveness": 0.1,
                    "relationship_importance": 0.7,
                    "reason": "他/她误读了用户意图。",
                },
                "conflict_analysis": {
                    "cause": "bot_misread",
                    "fault_severity": 0.1,
                    "user_acknowledged": False,
                    "apology_sincerity": 0.0,
                    "repaired": False,
                    "repair_quality": 0.0,
                    "repeat_offense": 0.0,
                    "bot_whim_level": 0.85,
                    "reason": "主要是他/她误读，不应继续冷处理用户。",
                },
            },
        )
        state = engine.update(previous, observation, now=1010.0)
        self.assertNotIn("cold_war", state.consequences.active_effects)
        self.assertLess(state.consequences.values["withdrawal"], 0.6)
        self.assertLess(state.consequences.values["rumination"], 0.65)
        self.assertGreater(state.consequences.values["repair"], 0.0)

    def test_conflict_without_relationship_decision_still_shapes_consequences(self):
        engine = EmotionEngine()
        previous = EmotionState.initial()
        previous.updated_at = 1000.0
        observation = EmotionObservation(
            values={
                "valence": -0.2,
                "arousal": 0.1,
                "dominance": 0.0,
                "goal_congruence": -0.1,
                "certainty": 0.5,
                "control": 0.1,
                "affiliation": -0.05,
            },
            confidence=0.8,
            label="offended",
            appraisal={
                "conflict_analysis": {
                    "cause": "user_fault",
                    "fault_severity": 0.9,
                    "perceived_intentionality": 0.7,
                    "controllability": 0.7,
                    "trust_damage": 0.4,
                    "boundary_legitimacy": 0.8,
                    "user_acknowledged": False,
                    "apology_sincerity": 0.0,
                    "repaired": False,
                    "repair_quality": 0.0,
                    "repeat_offense": 0.7,
                    "bot_whim_level": 0.0,
                    "reason": "用户犯错且没有修正。",
                },
            },
        )
        state = engine.update(previous, observation, now=1010.0)
        self.assertIn("direct_boundary", state.consequences.active_effects)
        self.assertGreater(state.consequences.values["confrontation"], 0.45)
        self.assertEqual(
            state.last_appraisal["conflict_analysis"]["cause"],
            "user_fault",
        )

    def test_ambiguity_and_misread_clear_cold_war_without_relationship_decision(self):
        engine = EmotionEngine()
        previous = EmotionState.initial()
        previous.updated_at = 1000.0
        previous.consequences.updated_at = 1000.0
        previous.consequences.active_effects["cold_war"] = 1200
        previous.consequences.effect_expires_at["cold_war"] = 2200.0
        previous.consequences.values["confrontation"] = 0.8
        observation = EmotionObservation(
            values={
                "valence": -0.35,
                "arousal": -0.2,
                "dominance": -0.1,
                "goal_congruence": -0.25,
                "certainty": -0.4,
                "control": -0.2,
                "affiliation": -0.3,
            },
            confidence=0.82,
            label="uncertain_hurt",
            appraisal={
                "conflict_analysis": {
                    "cause": "mutual",
                    "fault_severity": 0.4,
                    "ambiguity_level": 0.82,
                    "misread_likelihood": 0.78,
                    "bot_whim_level": 0.2,
                    "withdrawal_motive": "uncertainty",
                    "reason": "语义可能被误读。",
                },
            },
        )
        state = engine.update(previous, observation, now=1010.0)
        self.assertNotIn("cold_war", state.consequences.active_effects)
        self.assertIn("careful_checking", state.consequences.active_effects)
        self.assertLess(state.consequences.values["confrontation"], 0.7)

    def test_trust_damage_and_resentment_preserve_caution_after_repair(self):
        engine = EmotionEngine()
        previous = EmotionState.initial()
        previous.updated_at = 1000.0
        observation = EmotionObservation(
            values={
                "valence": -0.4,
                "arousal": 0.1,
                "dominance": 0.1,
                "goal_congruence": -0.3,
                "certainty": 0.4,
                "control": 0.2,
                "affiliation": 0.0,
            },
            confidence=0.85,
            label="repaired_but_careful",
            appraisal={
                "conflict_analysis": {
                    "cause": "user_fault",
                    "fault_severity": 0.7,
                    "user_acknowledged": True,
                    "apology_sincerity": 0.8,
                    "repaired": True,
                    "repair_quality": 0.78,
                    "trust_damage": 0.72,
                    "resentment_residue": 0.58,
                    "forgiveness_readiness": 0.72,
                    "withdrawal_motive": "self_protection",
                },
            },
        )
        state = engine.update(previous, observation, now=1010.0)
        self.assertGreater(state.consequences.values["repair"], 0.0)
        self.assertGreater(state.consequences.values["caution"], 0.25)
        self.assertGreater(state.consequences.values["rumination"], 0.0)

    def test_llm_relationship_decision_boundary_does_not_start_cold_war(self):
        engine = EmotionEngine()
        previous = EmotionState.initial()
        previous.updated_at = 1000.0
        observation = EmotionObservation(
            values={
                "valence": -0.75,
                "arousal": 0.75,
                "dominance": 0.7,
                "goal_congruence": -0.65,
                "certainty": 0.7,
                "control": 0.3,
                "affiliation": -0.4,
            },
            confidence=0.9,
            label="anger_boundary",
            appraisal={
                "relationship_decision": {
                    "decision": "boundary",
                    "intensity": 0.8,
                    "forgiveness": 0.2,
                    "relationship_importance": 0.5,
                    "reason": "需要明确边界，但还没到冷处理。",
                },
            },
        )
        state = engine.update(previous, observation, now=1010.0)
        self.assertIn("direct_boundary", state.consequences.active_effects)
        self.assertNotIn("cold_war", state.consequences.active_effects)

    def test_consequence_state_decays_by_real_time(self):
        engine = EmotionEngine(
            EmotionParameters(
                consequence_half_life_seconds=100.0,
                baseline_half_life_seconds=100.0,
            ),
        )
        previous = EmotionState.initial()
        previous.updated_at = 1000.0
        previous.consequences.values["withdrawal"] = 1.0
        previous.consequences.updated_at = 1000.0
        previous.consequences.effect_expires_at["cold_war"] = 1200.0
        previous.consequences.active_effects["cold_war"] = 200
        state = engine.passive_update(
            previous,
            now=1100.0,
        )
        self.assertAlmostEqual(state.consequences.values["withdrawal"], 0.5)
        self.assertEqual(state.consequences.active_effects.get("cold_war"), 100)

    def test_rapid_updates_do_not_flush_persistent_effects(self):
        engine = EmotionEngine(
            EmotionParameters(
                min_update_interval_seconds=8.0,
                rapid_update_half_life_seconds=20.0,
                consequence_half_life_seconds=3600.0,
                cold_war_duration_seconds=1800.0,
            ),
        )
        previous = EmotionState.initial()
        previous.updated_at = 1000.0
        previous.consequences.updated_at = 1000.0
        previous.consequences.values["withdrawal"] = 1.0
        previous.consequences.active_effects["cold_war"] = 1800
        previous.consequences.effect_expires_at["cold_war"] = 2800.0
        neutral = EmotionObservation(values=previous.values, confidence=0.2)
        state = previous
        for step in range(1, 25):
            state = engine.update(state, neutral, now=1000.0 + step)
        self.assertGreater(state.consequences.values["withdrawal"], 0.95)
        self.assertGreater(state.consequences.active_effects["cold_war"], 1750)

    def test_public_payload_has_versioned_contract(self):
        state = EmotionState.initial()
        state.consequences.active_effects["cold_war"] = 2
        payload = emotion_state_to_public_payload(
            state,
            session_key="test-session",
            prompt_fragment="prompt fragment",
        )
        self.assertEqual(payload["schema_version"], "astrbot.emotion_state.v2")
        self.assertEqual(payload["api_version"], "1.0")
        self.assertEqual(payload["session_key"], "test-session")
        self.assertIn("valence", payload["emotion"]["values"])
        self.assertEqual(len(payload["emotion"]["dimensions"]), 7)
        self.assertIn("cold_war", payload["consequences"]["active_effects"])
        self.assertIn(
            "cold_war",
            payload["consequences"]["active_effect_remaining_seconds"],
        )
        self.assertTrue(payload["safety"]["computational_state_only"])
        self.assertEqual(payload["prompt_fragment"], "prompt fragment")

    def test_public_payload_exposes_relationship_contract(self):
        state = EmotionState.initial()
        state.last_appraisal = {
            "relationship_decision": {
                "decision": "repair",
                "intensity": 0.6,
                "forgiveness": 0.75,
                "relationship_importance": 0.8,
                "reason": "用户已补救。",
            },
            "conflict_analysis": {
                "cause": "user_fault",
                "fault_severity": 0.7,
                "user_acknowledged": True,
                "apology_sincerity": 0.8,
                "repaired": True,
                "repair_quality": 0.85,
                "repeat_offense": 0.1,
                "bot_whim_level": 0.0,
                "reason": "错误已被修正。",
            },
        }
        payload = emotion_state_to_public_payload(state)
        self.assertEqual(payload["relationship"]["repair_status"], "restored")
        self.assertEqual(
            payload["relationship"]["relationship_decision"]["decision"],
            "repair",
        )
        self.assertEqual(
            payload["relationship"]["conflict_analysis"]["cause"],
            "user_fault",
        )

    def test_public_payload_can_omit_safety_boundary(self):
        state = EmotionState.initial()
        payload = emotion_state_to_public_payload(state, include_safety=False)
        self.assertNotIn("safety", payload)

    def test_memory_payload_freezes_emotion_at_write_time(self):
        state = EmotionState.initial()
        state.label = "hurt"
        state.confidence = 0.82
        state.updated_at = 1234.5
        state.values["valence"] = -0.4
        state.last_reason = "user ignored a boundary"
        snapshot = emotion_state_to_public_payload(
            state,
            session_key="session-1",
            prompt_fragment="private prompt",
        )
        payload = build_emotion_memory_payload(
            memory={"text": "user made a promise"},
            memory_text="user made a promise",
            source="livingmemory",
            snapshot=snapshot,
            include_prompt_fragment=False,
            written_at=1300.0,
        )
        self.assertEqual(payload["schema_version"], "astrbot.emotion_memory.v1")
        self.assertEqual(payload["kind"], "emotion_annotated_memory")
        self.assertEqual(payload["memory"]["text"], "user made a promise")
        self.assertEqual(payload["emotion_at_write"]["label"], "hurt")
        self.assertEqual(payload["emotion_at_write"]["written_at"], 1300.0)
        self.assertEqual(payload["emotion_at_write"]["emotion_updated_at"], 1234.5)
        self.assertEqual(payload["emotion_at_write"]["values"]["valence"], -0.4)
        self.assertIn("relationship", payload["emotion_at_write"])
        self.assertIn("consequences", payload["emotion_at_write"])
        self.assertIn("emotion_snapshot", payload)
        self.assertNotIn("prompt_fragment", payload["emotion_at_write"])
        self.assertNotIn("prompt_fragment", payload["emotion_snapshot"])

    def test_memory_payload_deep_freezes_nested_snapshot_fields(self):
        snapshot = {
            "schema_version": "astrbot.emotion_state.v2",
            "api_version": "1.0",
            "session_key": "s-deep",
            "emotion": {
                "label": "guarded",
                "confidence": 0.88,
                "values": {"valence": -0.3},
                "last_appraisal": {
                    "conflict_analysis": {
                        "cause": "user_fault",
                        "evidence": {"citation_ids": ["KB0001"]},
                    },
                },
            },
            "relationship": {
                "decision": "boundary",
                "conflict_analysis": {
                    "cause": "user_fault",
                    "norm_violation_type": ["boundary_crossing"],
                },
            },
            "consequences": {
                "active_effects": {"direct_boundary": 900},
            },
            "persona": {"name": "careful"},
        }

        payload = build_emotion_memory_payload(
            snapshot=snapshot,
            memory={"text": "memory"},
            written_at=123.0,
        )
        snapshot["relationship"]["conflict_analysis"]["cause"] = "bot_misread"
        snapshot["relationship"]["conflict_analysis"]["norm_violation_type"].append(
            "mutated",
        )
        snapshot["consequences"]["active_effects"]["direct_boundary"] = 0
        snapshot["emotion"]["last_appraisal"]["conflict_analysis"]["evidence"][
            "citation_ids"
        ].append("MUTATED")

        frozen = payload["emotion_at_write"]
        self.assertEqual(
            frozen["relationship"]["conflict_analysis"]["cause"],
            "user_fault",
        )
        self.assertEqual(
            frozen["relationship"]["conflict_analysis"]["norm_violation_type"],
            ["boundary_crossing"],
        )
        self.assertEqual(
            frozen["consequences"]["active_effects"]["direct_boundary"],
            900,
        )
        self.assertEqual(
            frozen["last_appraisal"]["conflict_analysis"]["evidence"]["citation_ids"],
            ["KB0001"],
        )

    def test_memory_payload_derives_text_from_string_memory(self):
        state = EmotionState.initial()
        snapshot = emotion_state_to_public_payload(state, session_key="session-1")
        payload = build_emotion_memory_payload(
            memory="plain memory",
            snapshot=snapshot,
            include_raw_snapshot=False,
        )
        self.assertEqual(payload["memory_text"], "plain memory")
        self.assertNotIn("emotion_snapshot", payload)

    def test_memory_payload_can_include_prompt_fragment_when_requested(self):
        state = EmotionState.initial()
        snapshot = emotion_state_to_public_payload(
            state,
            session_key="session-1",
            prompt_fragment="prompt fragment",
        )
        payload = build_emotion_memory_payload(
            memory="raw memory",
            source="livingmemory",
            snapshot=snapshot,
            include_prompt_fragment=True,
        )
        self.assertEqual(
            payload["emotion_at_write"]["prompt_fragment"],
            "prompt fragment",
        )

    def test_public_persona_payload_excludes_raw_persona_text(self):
        profile = build_persona_profile(
            persona_id="shy",
            name="shy",
            text="害羞 内向 迟疑 紧张",
        )
        payload = persona_profile_to_public_payload(profile)
        self.assertEqual(payload["persona_id"], "shy")
        self.assertIn("baseline", payload)
        self.assertIn("traits", payload)
        self.assertNotIn("text", payload)

    def test_public_consequence_payload_labels_active_effects(self):
        state = EmotionState.initial()
        state.consequences.active_effects["direct_boundary"] = 2
        payload = consequence_state_to_public_payload(state.consequences)
        self.assertEqual(payload["active_effect_labels"]["direct_boundary"], "直接设边界")
        self.assertEqual(len(payload["dimensions"]), 10)

    def test_state_injection_safety_boundary_is_configurable(self):
        from prompts import build_state_injection

        state = EmotionState.initial()
        safe = build_state_injection(state, safety_boundary=True)
        raw = build_state_injection(state, safety_boundary=False)
        self.assertIn("不能羞辱", safe)
        self.assertNotIn("不能羞辱", raw)
        self.assertIn("调制语气", raw)

    def test_assessment_prompts_keep_gender_neutral_bot_reference(self):
        from prompts import build_assessment_prompt

        profile = build_persona_profile(
            persona_id="persona",
            name="persona",
            text="敏感 谨慎",
        )
        state = EmotionState.initial(profile)
        normal = build_assessment_prompt(
            phase="pre_response",
            previous_state=state,
            persona_profile=profile,
            context_text="用户道歉了",
            current_text="对不起，我会改。",
            max_context_chars=200,
        )
        light = build_assessment_prompt(
            phase="pre_response",
            previous_state=state,
            persona_profile=profile,
            context_text="用户道歉了",
            current_text="对不起，我会改。",
            max_context_chars=200,
            low_reasoning_friendly=True,
        )

        self.assertIn("他/她", normal)
        self.assertIn("生气/受伤原因", light)
        self.assertNotIn("为什么他会", normal)
        self.assertNotIn("为什么她会", normal)

    def test_low_reasoning_assessment_prompt_is_shorter_but_compatible(self):
        from prompts import build_assessment_prompt

        profile = build_persona_profile(
            persona_id="quiet",
            name="quiet",
            text="谨慎 内向 重视边界",
        )
        state = EmotionState.initial(profile)
        kwargs = {
            "phase": "pre_response",
            "previous_state": state,
            "persona_profile": profile,
            "context_text": "用户之前道歉，但又重复开过界玩笑。" * 20,
            "current_text": "对不起，我会改。",
            "max_context_chars": 1200,
        }
        full = build_assessment_prompt(**kwargs)
        light = build_assessment_prompt(**kwargs, low_reasoning_friendly=True)
        self.assertLess(len(light), len(full))
        self.assertIn("低推理模型友好模式", light)
        self.assertIn("relationship_decision", light)
        self.assertIn("conflict_analysis", light)
        self.assertIn("forgive|repair|boundary|cold_war|escalate|none", light)
        self.assertNotIn("citation_ids", light)


if __name__ == "__main__":
    unittest.main()
