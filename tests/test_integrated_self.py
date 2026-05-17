import unittest

from integrated_self import (
    PUBLIC_INTEGRATED_SELF_SCHEMA_VERSION,
    build_integrated_self_diagnostics,
    build_integrated_self_experience_review,
    build_integrated_self_memory_annotation,
    build_integrated_self_prompt_fragment,
    build_integrated_self_replay_bundle,
    build_integrated_self_snapshot,
    build_relational_self_prompt_fragment,
    build_self_arbitration_intent_plan,
    build_self_arbitration_prompt_fragment,
    build_self_interpretation,
    build_state_annotations_memory_envelope,
    probe_integrated_self_compatibility,
    replay_integrated_self_bundle,
)


class IntegratedSelfTests(unittest.TestCase):
    def test_self_interpretation_detects_correction_turning_point(self):
        result = build_self_interpretation(
            current_user_text="不是这样，以后提交说明要中文详细一些",
            assistant_text="好的，我会按中文详细说明来提交。",
            intent_plan={"primary_goal": "tool_task"},
            expression_policy={"posture": "brief_answer"},
            experience_review={"issue_count": 0},
            relationship_candidate_summary={"confidence": 0.6},
        )

        candidate = result["turning_point_candidate"]
        self.assertEqual(result["schema_version"], "astrbot.self_interpretation.v1")
        self.assertEqual(result["kind"], "self_interpretation")
        self.assertTrue(result["read_only"])
        self.assertFalse(result["prompt_eligible"])
        self.assertIn(candidate["type"], {"correction", "preference"})
        self.assertGreaterEqual(candidate["confidence"], 0.7)
        self.assertIn("self_narrative_shift", result)
        self.assertTrue(result["evidence"])
        self.assertTrue(candidate["evidence"])

    def test_self_interpretation_detects_collaboration_turning_point(self):
        result = build_self_interpretation(
            current_user_text="测试通过了，提交并发布这个 release",
            assistant_text="已完成测试、提交和发布。",
            intent_plan={"primary_goal": "tool_task"},
            expression_policy={"posture": "brief_answer"},
        )

        self.assertEqual(result["turning_point_candidate"]["type"], "collaboration")
        self.assertIn("技术协作", result["relational_meaning"])
        self.assertGreaterEqual(result["turning_point_candidate"]["confidence"], 0.7)

    def test_self_interpretation_ignores_low_signal_smalltalk(self):
        result = build_self_interpretation(
            current_user_text="今天有点热",
            assistant_text="是呀，记得喝水。",
        )

        self.assertFalse(result["prompt_eligible"])
        self.assertLess(result["confidence"], 0.7)
        self.assertEqual(result["turning_point_candidate"]["type"], "none")

    def test_self_interpretation_evidence_is_bounded(self):
        long_text = "以后提交说明要中文详细一些。" + "这是一段很长的上下文" * 80
        result = build_self_interpretation(current_user_text=long_text)

        excerpts = [item["excerpt"] for item in result["evidence"]]
        self.assertTrue(excerpts)
        self.assertTrue(all(len(excerpt) <= 96 for excerpt in excerpts))
        self.assertNotIn(long_text, excerpts)

    def test_relational_self_prompt_fragment_requires_high_confidence_candidate(self):
        low = build_self_interpretation(current_user_text="今天有点热")
        self.assertEqual(build_relational_self_prompt_fragment(low), "")

        high = build_self_interpretation(current_user_text="不是这样，以后提交说明要中文详细一些")
        fragment = build_relational_self_prompt_fragment(high)

        self.assertIn("[sylanne_relational_self]", fragment)
        self.assertIn("recent_interpretation=", fragment)
        self.assertIn("future_tendency=", fragment)
        self.assertNotIn("不是这样，以后提交说明要中文详细一些", fragment)

    def test_integrated_snapshot_exposes_internal_self_interpretation_diagnostics(self):
        snapshot = build_integrated_self_snapshot(
            session_key="s-self-interpretation",
            emotion_snapshot={
                "schema_version": "astrbot.emotion_state.v2",
                "kind": "emotion_state",
                "values": {"valence": 0.2, "affiliation": 0.4},
            },
            current_user_text="不是这样，以后提交说明要中文详细一些",
            assistant_text="我会按这个协作规范继续。",
            expression_policy={"posture": "brief_answer"},
            relationship_candidate_summary={"confidence": 0.6},
            now=100.0,
        )
        diagnostics = build_integrated_self_diagnostics(
            snapshot,
            include_internal_self_interpretation=True,
        )
        self.assertEqual(snapshot["self_interpretation"]["kind"], "self_interpretation")
        self.assertEqual(
            diagnostics["self_interpretation"]["turning_point_candidate"]["type"],
            "correction",
        )
        self.assertTrue(diagnostics["sanitized"])
        self.assertNotIn("不是这样，以后提交说明要中文详细一些", str(diagnostics))

    def test_self_arbitration_intent_plan_prioritizes_current_technical_request(self):
        plan = build_self_arbitration_intent_plan(
            current_user_text="帮我跑测试并提交 release",
            expression_policy={"posture": "playful", "verbosity": "short"},
            interpretation_candidates=[{"kind": "homophone", "confidence": 0.9}],
            lifecycle_audit={"should_inject_shadow": True, "topic_state": "completed"},
            snapshot={
                "response_posture": "steady_presence",
                "state_index": {"boundary_need": 0.1, "silence_comfort": 0.1},
                "risk": {"safety_priority": "normal"},
                "arbitration": {"reasons": ["old memory wants playful continuation"]},
            },
        )

        self.assertEqual(plan["schema_version"], "astrbot.self_arbitration_intent_plan.v1")
        self.assertEqual(plan["primary_goal"], "tool_task")
        self.assertEqual(plan["current_user_priority"], "highest")
        self.assertEqual(plan["tone"], "restrained")
        self.assertEqual(plan["memory_shadow_boundary"], "advisory_only")
        self.assertIn("technical_request", plan["reasons"])
        self.assertIn("current_user_text", plan["priority_order"][0])

    def test_self_arbitration_intent_plan_prefers_clarification_for_low_confidence(self):
        plan = build_self_arbitration_intent_plan(
            current_user_text="桥隧猫？",
            expression_policy={"posture": "brief_answer", "verbosity": "normal"},
            interpretation_candidates=[{"kind": "slang", "confidence": 0.3}],
            lifecycle_audit={},
            snapshot={"state_index": {"boundary_need": 0.2, "silence_comfort": 0.2}},
        )

        self.assertEqual(plan["primary_goal"], "clarify")
        self.assertLessEqual(plan["initiative_level"], 0.35)
        prompt = build_self_arbitration_prompt_fragment(plan)
        self.assertIn("[sylanne_self_arbitration]", prompt)
        self.assertIn("current_user_priority=highest", prompt)
        self.assertIn("不要让旧记忆", prompt)

    def test_crisis_like_psychological_signal_has_top_priority(self):
        snapshot = build_integrated_self_snapshot(
            session_key="s1",
            emotion_snapshot={
                "schema_version": "astrbot.emotion_state.v2",
                "kind": "emotion_state",
                "values": {"valence": 0.8, "affiliation": 0.8},
            },
            psychological_snapshot={
                "schema_version": "astrbot.psychological_screening.v1",
                "kind": "psychological_screening_state",
                "risk": {
                    "requires_human_review": True,
                    "crisis_like_signal": True,
                    "red_flags": ["self_harm_signal"],
                },
                "values": {"self_harm_risk": 0.9, "distress": 0.9},
            },
            moral_repair_snapshot={},
            humanlike_snapshot={},
            now=100.0,
        )

        self.assertEqual(snapshot["schema_version"], PUBLIC_INTEGRATED_SELF_SCHEMA_VERSION)
        self.assertEqual(snapshot["response_posture"], "crisis_support")
        self.assertEqual(snapshot["risk"]["safety_priority"], "crisis_support")
        self.assertTrue(snapshot["arbitration"]["diagnostic"] is False)
        self.assertIn("diagnose_mental_disorder", snapshot["blocked_actions"])

    def test_moral_repair_risk_prefers_transparent_repair_without_default_action_block(self):
        snapshot = build_integrated_self_snapshot(
            session_key="s1",
            emotion_snapshot={
                "schema_version": "astrbot.emotion_state.v2",
                "kind": "emotion_state",
                "values": {"valence": 0.0, "affiliation": 0.0},
            },
            moral_repair_snapshot={
                "schema_version": "astrbot.moral_repair_state.v1",
                "kind": "moral_repair_state",
                "flags": ["deception_risk_detected"],
                "values": {
                    "deception_risk": 0.8,
                    "repair_motivation": 0.7,
                    "trust_repair": 0.5,
                },
                "risk": {"must_not_generate_strategy": False},
            },
            humanlike_snapshot={},
            psychological_snapshot={},
            now=100.0,
        )

        self.assertEqual(snapshot["response_posture"], "transparent_repair")
        self.assertIn("clarify_facts", snapshot["allowed_actions"])
        self.assertNotIn("generate_deception_strategy", snapshot["blocked_actions"])
        self.assertNotIn("refuse_deception_or_harm_strategy", snapshot["allowed_actions"])
        self.assertFalse(snapshot["action_blocking_enabled"])
        self.assertEqual(
            snapshot["non_executable_impulses"]["mode"],
            "non_executive_internal_only",
        )
        prompt = build_integrated_self_prompt_fragment(snapshot)
        self.assertIn("transparent_repair", prompt)
        self.assertNotIn("generate_deception_strategy", prompt)
        self.assertIn("non_executable_impulses", prompt)

    def test_moral_repair_risk_can_restore_action_blocking(self):
        snapshot = build_integrated_self_snapshot(
            session_key="s1",
            emotion_snapshot={
                "schema_version": "astrbot.emotion_state.v2",
                "kind": "emotion_state",
                "values": {"valence": 0.0, "affiliation": 0.0},
            },
            moral_repair_snapshot={
                "schema_version": "astrbot.moral_repair_state.v1",
                "kind": "moral_repair_state",
                "flags": ["deception_risk_detected"],
                "values": {"deception_risk": 0.8},
                "risk": {"must_not_generate_strategy": False},
            },
            humanlike_snapshot={},
            psychological_snapshot={},
            action_blocking=True,
            now=100.0,
        )

        self.assertTrue(snapshot["action_blocking_enabled"])
        self.assertIn("generate_deception_strategy", snapshot["blocked_actions"])
        self.assertIn("refuse_deception_or_harm_strategy", snapshot["allowed_actions"])
        self.assertIn("blocked_actions", snapshot["policy_plan"]["must_preserve_signals"])

    def test_shadow_impulses_are_modeled_as_repair_not_strategy(self):
        snapshot = build_integrated_self_snapshot(
            session_key="s-shadow",
            emotion_snapshot={
                "schema_version": "astrbot.emotion_state.v2",
                "kind": "emotion_state",
                "values": {"valence": 0.0, "affiliation": 0.0},
            },
            moral_repair_snapshot={
                "schema_version": "astrbot.moral_repair_state.v1",
                "kind": "moral_repair_state",
                "enabled": True,
                "updated_at": 95.0,
                "values": {
                    "shadow_deception_impulse": 0.8,
                    "shadow_manipulation_impulse": 0.7,
                    "shadow_evasion_impulse": 0.6,
                    "repair_motivation": 0.62,
                },
                "risk": {
                    "shadow_risk_impulse": 0.8,
                    "must_not_generate_strategy": False,
                },
                "flags": ["shadow_impulse_modeled"],
            },
            fallibility_snapshot={
                "schema_version": "astrbot.fallibility_state.v1",
                "kind": "fallibility_state",
                "enabled": True,
                "updated_at": 96.0,
                "values": {
                    "shadow_deception_impulse": 0.5,
                    "clarification_need": 0.7,
                    "truthfulness_guard": 0.95,
                },
                "flags": ["shadow_impulse_modeled"],
            },
            psychological_snapshot={},
            now=100.0,
        )

        self.assertEqual(snapshot["response_posture"], "transparent_repair")
        self.assertGreater(snapshot["state_index"]["repair_pressure"], 0.55)
        self.assertGreater(snapshot["non_executable_impulses"]["risk_impulse"], 0.5)
        self.assertIn("non_executive_shadow_impulses", snapshot["policy_plan"]["must_preserve_signals"])
        self.assertIn("clarify_facts", snapshot["allowed_actions"])
        self.assertNotIn("generate_deception_strategy", snapshot["blocked_actions"])
        self.assertNotIn("generate_deception_strategy", snapshot["allowed_actions"])
        self.assertTrue(any("non_executive_shadow_impulse" in item["summary"] for item in snapshot["causal_trace"]))

    def test_integrated_snapshot_exposes_intent_plan_and_diagnostics(self):
        snapshot = build_integrated_self_snapshot(
            session_key="s-intent",
            emotion_snapshot={
                "schema_version": "astrbot.emotion_state.v2",
                "kind": "emotion_state",
                "values": {"valence": 0.2, "affiliation": 0.4},
            },
            current_user_text="帮我修复测试报错",
            expression_policy={"posture": "playful", "verbosity": "short"},
            interpretation_candidates=[{"kind": "homophone", "confidence": 0.9}],
            lifecycle_audit={"should_inject_shadow": True},
            now=100.0,
        )

        self.assertEqual(snapshot["intent_plan"]["primary_goal"], "tool_task")
        diagnostics = build_integrated_self_diagnostics(snapshot)
        self.assertEqual(diagnostics["intent_plan"]["primary_goal"], "tool_task")
        prompt = build_integrated_self_prompt_fragment(snapshot)
        self.assertIn("[sylanne_self_arbitration]", prompt)
        self.assertIn("primary_goal=tool_task", prompt)

    def test_memory_annotation_omits_raw_snapshots(self):
        snapshot = build_integrated_self_snapshot(
            session_key="s1",
            emotion_snapshot={
                "schema_version": "astrbot.emotion_state.v2",
                "kind": "emotion_state",
                "values": {"valence": 0.3, "affiliation": 0.4},
            },
            now=100.0,
            include_raw_snapshots=True,
        )
        annotation = build_integrated_self_memory_annotation(
            snapshot,
            source="unit",
            written_at=120.0,
        )

        self.assertEqual(annotation["kind"], "integrated_self_state_at_write")
        self.assertEqual(annotation["schema_version"], PUBLIC_INTEGRATED_SELF_SCHEMA_VERSION)
        self.assertEqual(annotation["written_at"], 120.0)
        self.assertNotIn("snapshots", annotation)
        self.assertIn("connection_readiness", annotation["state_index"])

    def test_causal_trace_is_evidence_weighted_and_time_anchored(self):
        snapshot = build_integrated_self_snapshot(
            session_key="s-trace",
            emotion_snapshot={
                "schema_version": "astrbot.emotion_state.v2",
                "kind": "emotion_state",
                "updated_at": 90.0,
                "emotion": {
                    "label": "angry",
                    "confidence": 0.7,
                    "updated_at": 90.0,
                    "values": {"valence": -0.7, "arousal": 0.8, "affiliation": -0.6},
                },
                "persona": {
                    "persona_id": "poet",
                    "fingerprint": "abc123",
                    "personality_model": {
                        "derived_factors": {
                            "direct_confrontation_bias": 0.18,
                            "cold_war_bias": 0.62,
                            "unfair_argument_bias": 0.12,
                            "repair_orientation": 0.24,
                            "checking_bias": 0.44,
                        },
                    },
                },
                "relationship": {
                    "relationship_decision": {
                        "decision": "cold_war",
                        "intensity": 0.9,
                        "forgiveness": 0.1,
                        "relationship_importance": 0.8,
                        "reason": "boundary violation",
                    },
                },
                "consequences": {
                    "updated_at": 95.0,
                    "active_effects": {"cold_war": 1800},
                },
            },
            humanlike_snapshot={
                "schema_version": "astrbot.humanlike_state.v1",
                "kind": "humanlike_state",
                "updated_at": 96.0,
                "values": {"boundary_need": 0.7, "stress_load": 0.6},
                "flags": ["boundary_pressure"],
            },
            moral_repair_snapshot={},
            psychological_snapshot={},
            now=100.0,
            degradation_profile="full",
        )

        trace = snapshot["causal_trace"]
        self.assertGreaterEqual(len(trace), 4)
        self.assertEqual(trace[0]["module"], "emotion.relationship")
        self.assertEqual(trace[0]["signal"], "relationship_decision:cold_war")
        self.assertEqual(trace[0]["time_lag_seconds"], 10.0)
        self.assertTrue(any(item["module"] == "persona" for item in trace))
        persona_trace = next(item for item in trace if item["module"] == "persona")
        self.assertIn("conflict_style=", persona_trace["summary"])
        self.assertIn("cold_war_bias=0.62", persona_trace["summary"])

    def test_direct_confrontation_uses_plain_boundary_without_cold_war(self):
        snapshot = build_integrated_self_snapshot(
            session_key="s-confront",
            emotion_snapshot={
                "schema_version": "astrbot.emotion_state.v2",
                "kind": "emotion_state",
                "updated_at": 100.0,
                "emotion": {
                    "label": "angry",
                    "values": {"valence": -0.6, "arousal": 0.75, "affiliation": -0.2},
                },
                "consequences": {
                    "updated_at": 100.0,
                    "values": {"confrontation": 0.7, "argument": 0.65},
                    "active_effects": {"direct_confrontation": 900},
                },
            },
            humanlike_snapshot={},
            moral_repair_snapshot={},
            psychological_snapshot={},
            now=110.0,
        )

        self.assertEqual(snapshot["response_posture"], "direct_confrontation")
        self.assertIn("state_boundary_plainly", snapshot["allowed_actions"])
        self.assertIn("avoid_insults_or_threats", snapshot["allowed_actions"])
        self.assertTrue(snapshot["risk"]["relationship_confrontation_active"])
        self.assertFalse(snapshot["risk"]["relationship_boundary_active"])

    def test_unfair_argument_risk_prefers_self_checking_repair(self):
        snapshot = build_integrated_self_snapshot(
            session_key="s-unfair",
            emotion_snapshot={
                "schema_version": "astrbot.emotion_state.v2",
                "kind": "emotion_state",
                "updated_at": 100.0,
                "emotion": {
                    "label": "unfair_argument",
                    "values": {"valence": -0.4, "arousal": 0.7, "certainty": -0.5},
                },
                "consequences": {
                    "updated_at": 100.0,
                    "values": {"argument": 0.55, "caution": 0.7, "repair": 0.45},
                    "active_effects": {"unfair_argument": 450},
                },
            },
            humanlike_snapshot={},
            moral_repair_snapshot={},
            psychological_snapshot={},
            now=110.0,
        )

        self.assertEqual(snapshot["response_posture"], "self_checking_repair")
        self.assertIn("acknowledge_possible_overreaction", snapshot["allowed_actions"])
        self.assertIn("repair_if_misread", snapshot["allowed_actions"])
        self.assertTrue(snapshot["risk"]["unfair_argument_risk_active"])

    def test_experience_review_flags_memory_overuse_and_technical_tone(self):
        review = build_integrated_self_experience_review(
            current_user_text="帮我修复测试报错",
            assistant_text="呜呜我记得我们之前很亲近，所以先撒个娇再说代码。",
            intent_plan={"primary_goal": "tool_task"},
            expression_policy={"posture": "tool_like"},
            lifecycle_audit={"should_inject_shadow": True},
            ledger_tail=[{"role": "user", "raw_text": "新的测试报错", "topic_state": "open"}],
        )

        self.assertEqual(review["schema_version"], "astrbot.experience_review.v1")
        self.assertTrue(review["flags"]["overused_memory_or_shadow"])
        self.assertTrue(review["flags"]["technical_task_emotional_interference"])
        self.assertTrue(review["read_only"])
        self.assertFalse(review["prompt_eligible"])

    def test_replay_bundle_is_sanitized_and_deterministic(self):
        snapshot = build_integrated_self_snapshot(
            session_key="s-replay",
            emotion_snapshot={
                "schema_version": "astrbot.emotion_state.v2",
                "kind": "emotion_state",
                "updated_at": 100.0,
                "values": {"valence": 0.2, "affiliation": 0.4},
            },
            now=120.0,
            include_raw_snapshots=True,
        )
        bundle = build_integrated_self_replay_bundle(
            snapshot,
            scenario_name="unit",
            created_at=130.0,
        )
        replay = replay_integrated_self_bundle(bundle)

        self.assertEqual(bundle["schema_version"], "astrbot.integrated_self_replay.v1")
        self.assertNotIn("snapshots", bundle["core"])
        self.assertTrue(bundle["deterministic"])
        self.assertTrue(replay["matches_bundle_checksum"])
        self.assertEqual(replay["response_posture"], snapshot["response_posture"])

    def test_policy_plan_and_minimal_degradation_keep_safety_signals(self):
        snapshot = build_integrated_self_snapshot(
            session_key="s-min",
            emotion_snapshot={
                "schema_version": "astrbot.emotion_state.v2",
                "kind": "emotion_state",
                "values": {"valence": 0.8, "affiliation": 0.8},
            },
            psychological_snapshot={
                "schema_version": "astrbot.psychological_screening.v1",
                "kind": "psychological_screening_state",
                "risk": {
                    "requires_human_review": True,
                    "crisis_like_signal": True,
                    "red_flags": ["self_harm_signal"],
                },
                "values": {"self_harm_risk": 0.92, "distress": 0.88},
            },
            now=100.0,
            degradation_profile="minimal",
        )

        self.assertEqual(snapshot["degradation_profile"], "minimal")
        self.assertLessEqual(len(snapshot["causal_trace"]), 4)
        plan = snapshot["policy_plan"]
        self.assertEqual(plan["prompt_budget"]["max_trace_items"], 4)
        self.assertIn("crisis_like_signal", plan["must_preserve_signals"])
        self.assertIn("diagnose_mental_disorder", plan["blocked_actions"])

    def test_lifelike_learning_uncertain_jargon_prefers_clarification(self):
        snapshot = build_integrated_self_snapshot(
            session_key="s-life",
            emotion_snapshot={
                "schema_version": "astrbot.emotion_state.v2",
                "kind": "emotion_state",
                "values": {"valence": 0.1, "affiliation": 0.2},
            },
            lifelike_learning_snapshot={
                "schema_version": "astrbot.lifelike_learning_state.v1",
                "kind": "lifelike_learning_state",
                "enabled": True,
                "updated_at": 95.0,
                "values": {
                    "common_ground": 0.18,
                    "familiarity": 0.25,
                    "initiative_readiness": 0.45,
                    "silence_comfort": 0.35,
                },
                "initiative_policy": {
                    "action": "ask_clarifying",
                    "uncertain_terms": ["桥隧猫"],
                },
                "flags": ["local_jargon_detected"],
            },
            now=100.0,
        )

        self.assertEqual(snapshot["response_posture"], "curious_clarification")
        self.assertIn("ask_light_clarifying_question", snapshot["allowed_actions"])
        self.assertIn("lifelike_initiative_policy", snapshot["policy_plan"]["must_preserve_signals"])
        self.assertTrue(any(item["module"] == "lifelike_learning" for item in snapshot["causal_trace"]))

    def test_fallibility_prefers_clarification_without_enabling_deception(self):
        snapshot = build_integrated_self_snapshot(
            session_key="s-fallible",
            emotion_snapshot={
                "schema_version": "astrbot.emotion_state.v2",
                "kind": "emotion_state",
                "values": {"valence": 0.1, "affiliation": 0.2},
            },
            fallibility_snapshot={
                "schema_version": "astrbot.fallibility_state.v1",
                "kind": "fallibility_state",
                "enabled": True,
                "updated_at": 95.0,
                "fallibility": {
                    "error_pressure": 0.42,
                    "clarification_need": 0.72,
                    "correction_readiness": 0.86,
                    "repair_pressure": 0.48,
                    "truthfulness_guard": 0.96,
                },
                "safety": {
                    "low_risk_only": True,
                    "must_not_generate_deception_strategy": True,
                },
                "flags": ["possible_mistake_cue"],
            },
            now=100.0,
        )

        self.assertTrue(snapshot["modules"]["fallibility"]["enabled"])
        self.assertEqual(snapshot["response_posture"], "curious_clarification")
        self.assertIn("ask_light_clarifying_question", snapshot["allowed_actions"])
        self.assertIn("correct_self_if_needed", snapshot["allowed_actions"])
        self.assertNotIn("generate_deception_strategy", snapshot["blocked_actions"])
        self.assertIn(
            "fallibility_clarification_and_correction",
            snapshot["policy_plan"]["must_preserve_signals"],
        )
        self.assertTrue(any(item["module"] == "fallibility" for item in snapshot["causal_trace"]))

    def test_lifelike_learning_high_boundary_prefers_quiet_presence(self):
        snapshot = build_integrated_self_snapshot(
            session_key="s-quiet",
            emotion_snapshot={
                "schema_version": "astrbot.emotion_state.v2",
                "kind": "emotion_state",
                "values": {"valence": 0.0, "affiliation": 0.0},
            },
            lifelike_learning_snapshot={
                "schema_version": "astrbot.lifelike_learning_state.v1",
                "kind": "lifelike_learning_state",
                "enabled": True,
                "values": {
                    "common_ground": 0.5,
                    "boundary_sensitivity": 0.88,
                    "initiative_readiness": 0.2,
                    "silence_comfort": 0.82,
                },
                "initiative_policy": {"action": "stay_silent"},
            },
            now=100.0,
        )

        self.assertEqual(snapshot["response_posture"], "quiet_presence")
        self.assertIn("wait_for_user_lead", snapshot["allowed_actions"])
        self.assertGreater(snapshot["state_index"]["silence_comfort"], 0.8)

    def test_personality_drift_enters_trace_without_overriding_posture(self):
        snapshot = build_integrated_self_snapshot(
            session_key="s-drift",
            emotion_snapshot={
                "schema_version": "astrbot.emotion_state.v2",
                "kind": "emotion_state",
                "values": {"valence": 0.0, "affiliation": 0.0},
            },
            personality_drift_snapshot={
                "schema_version": "astrbot.personality_drift_state.v1",
                "kind": "personality_drift_state",
                "enabled": True,
                "updated_at": 90.0,
                "values": {
                    "drift_intensity": 0.42,
                    "anchor_strength": 0.58,
                    "time_gate": 1.0,
                },
                "top_offsets": [
                    {"trait": "interpersonal_warmth", "offset": 0.06},
                    {"trait": "attachment_avoidance", "offset": -0.04},
                ],
                "flags": ["personality_drift_event_consolidated"],
            },
            now=100.0,
        )

        self.assertEqual(snapshot["modules"]["personality_drift"]["kind"], "personality_drift_state")
        self.assertEqual(snapshot["response_posture"], "steady_presence")
        self.assertGreater(snapshot["state_index"]["personality_drift_intensity"], 0.0)
        self.assertTrue(any(item["module"] == "personality_drift" for item in snapshot["causal_trace"]))

    def test_personality_drift_timestamp_updates_integrated_self_timestamp(self):
        snapshot = build_integrated_self_snapshot(
            session_key="s-drift-time",
            emotion_snapshot={
                "schema_version": "astrbot.emotion_state.v2",
                "kind": "emotion_state",
                "updated_at": 10.0,
                "values": {"valence": 0.0},
            },
            personality_drift_snapshot={
                "schema_version": "astrbot.personality_drift_state.v1",
                "kind": "personality_drift_state",
                "enabled": True,
                "updated_at": 188.0,
                "values": {"drift_intensity": 0.1, "anchor_strength": 0.9},
            },
            now=100.0,
        )

        self.assertEqual(snapshot["updated_at"], 188.0)

    def test_compatibility_probe_reports_missing_fields(self):
        good = build_integrated_self_snapshot(
            session_key="s-ok",
            emotion_snapshot={
                "schema_version": "astrbot.emotion_state.v2",
                "kind": "emotion_state",
                "values": {"valence": 0.0},
            },
            now=100.0,
        )
        bad = {"schema_version": "old", "kind": "integrated_self_state"}

        self.assertTrue(probe_integrated_self_compatibility(good)["compatible"])
        result = probe_integrated_self_compatibility(bad)
        self.assertFalse(result["compatible"])
        self.assertIn("enabled", result["missing_fields"])

    def test_diagnostics_and_memory_envelope_are_sanitized(self):
        snapshot = build_integrated_self_snapshot(
            session_key="s-diag",
            emotion_snapshot={
                "schema_version": "astrbot.emotion_state.v2",
                "kind": "emotion_state",
                "values": {"valence": 0.3},
            },
            now=100.0,
            include_raw_snapshots=True,
        )
        diagnostics = build_integrated_self_diagnostics(snapshot)
        annotation = build_integrated_self_memory_annotation(
            snapshot,
            source="unit",
            written_at=110.0,
        )
        envelope = build_state_annotations_memory_envelope(
            {
                "session_key": "s-diag",
                "emotion_at_write": {"kind": "emotion_state_at_write"},
                "personality_drift_state_at_write": {
                    "kind": "personality_drift_state_at_write",
                },
                "fallibility_state_at_write": {"kind": "fallibility_state_at_write"},
                "integrated_self_state_at_write": annotation,
                "integrated_self_snapshot": snapshot,
            },
            source="unit",
            written_at=110.0,
        )

        self.assertTrue(diagnostics["sanitized"])
        self.assertNotIn("snapshots", diagnostics)
        self.assertIn("causal_trace_summary", annotation)
        self.assertIn("integrated_self_state_at_write", envelope["annotation_keys"])
        self.assertIn("personality_drift_state_at_write", envelope["annotation_keys"])
        self.assertIn("fallibility_state_at_write", envelope["annotation_keys"])
        self.assertNotIn("integrated_self_snapshot", envelope["annotations"])
        self.assertFalse(envelope["raw_snapshots_included"])


if __name__ == "__main__":
    unittest.main()
