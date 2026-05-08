import unittest

from integrated_self import (
    PUBLIC_INTEGRATED_SELF_SCHEMA_VERSION,
    build_integrated_self_diagnostics,
    build_integrated_self_memory_annotation,
    build_integrated_self_prompt_fragment,
    build_integrated_self_replay_bundle,
    build_integrated_self_snapshot,
    build_state_annotations_memory_envelope,
    probe_integrated_self_compatibility,
    replay_integrated_self_bundle,
)


class IntegratedSelfTests(unittest.TestCase):
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

    def test_moral_repair_risk_prefers_transparent_repair(self):
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
                "risk": {"must_not_generate_strategy": True},
            },
            humanlike_snapshot={},
            psychological_snapshot={},
            now=100.0,
        )

        self.assertEqual(snapshot["response_posture"], "transparent_repair")
        self.assertIn("clarify_facts", snapshot["allowed_actions"])
        self.assertIn("generate_deception_strategy", snapshot["blocked_actions"])
        prompt = build_integrated_self_prompt_fragment(snapshot)
        self.assertIn("transparent_repair", prompt)
        self.assertIn("generate_deception_strategy", prompt)

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
                "persona": {"persona_id": "poet", "fingerprint": "abc123"},
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
        self.assertNotIn("integrated_self_snapshot", envelope["annotations"])
        self.assertFalse(envelope["raw_snapshots_included"])


if __name__ == "__main__":
    unittest.main()
