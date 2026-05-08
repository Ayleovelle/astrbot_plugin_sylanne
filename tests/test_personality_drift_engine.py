import unittest

from emotion_engine import build_persona_profile
from personality_drift_engine import (
    PUBLIC_PERSONALITY_DRIFT_SCHEMA_VERSION,
    PersonalityDriftEngine,
    PersonalityDriftObservation,
    PersonalityDriftParameters,
    PersonalityDriftState,
    apply_personality_drift_to_profile,
    build_personality_drift_memory_annotation,
    build_personality_drift_prompt_fragment,
    heuristic_personality_drift_observation,
    personality_drift_state_to_public_payload,
)


class PersonalityDriftEngineTests(unittest.TestCase):
    def test_real_time_gate_blocks_short_term_message_flood(self):
        engine = PersonalityDriftEngine(
            PersonalityDriftParameters(
                state_half_life_seconds=100000.0,
                rapid_update_half_life_seconds=86400.0,
                min_update_interval_seconds=21600.0,
                learning_rate=1.0,
                max_impulse_per_update=0.05,
                event_threshold=0.01,
            ),
        )
        state = PersonalityDriftState.initial(persona_fingerprint="p", now=0.0)
        observation = PersonalityDriftObservation(
            trait_impulses={"attachment_anxiety": 1.0},
            intensity=1.0,
            reliability=1.0,
            relationship_importance=1.0,
            reason="strong event",
        )

        first = engine.update(state, observation, persona_fingerprint="p", now=10.0)
        flooded = engine.update(first, observation, persona_fingerprint="p", now=11.0)
        matured = engine.update(first, observation, persona_fingerprint="p", now=90000.0)

        self.assertGreater(first.trait_offsets["attachment_anxiety"], 0.0)
        self.assertAlmostEqual(
            flooded.trait_offsets["attachment_anxiety"],
            first.trait_offsets["attachment_anxiety"],
            places=3,
        )
        self.assertGreater(
            matured.trait_offsets["attachment_anxiety"],
            first.trait_offsets["attachment_anxiety"],
        )

    def test_passive_update_uses_real_time_half_life_and_anchor_pull(self):
        engine = PersonalityDriftEngine(
            PersonalityDriftParameters(state_half_life_seconds=100.0),
        )
        state = PersonalityDriftState.initial(persona_fingerprint="p", now=0.0)
        state.trait_offsets["interpersonal_warmth"] = 0.20
        state.trait_confidence["interpersonal_warmth"] = 0.80
        state.updated_at = 0.0

        decayed = engine.passive_update(state, persona_fingerprint="p", now=100.0)

        self.assertAlmostEqual(decayed.trait_offsets["interpersonal_warmth"], 0.10)
        self.assertAlmostEqual(decayed.trait_confidence["interpersonal_warmth"], 0.40)

    def test_max_trait_offset_caps_long_term_adaptation(self):
        engine = PersonalityDriftEngine(
            PersonalityDriftParameters(
                rapid_update_half_life_seconds=1.0,
                min_update_interval_seconds=1.0,
                learning_rate=1.0,
                max_impulse_per_update=0.2,
                max_trait_offset=0.12,
                event_threshold=0.01,
            ),
        )
        state = PersonalityDriftState.initial(persona_fingerprint="p", now=0.0)
        observation = PersonalityDriftObservation(
            trait_impulses={"openness": 1.0},
            intensity=1.0,
            reliability=1.0,
            relationship_importance=1.0,
        )
        for index in range(8):
            state = engine.update(
                state,
                observation,
                persona_fingerprint="p",
                now=10.0 + index * 10.0,
            )

        self.assertLessEqual(state.trait_offsets["openness"], 0.12)
        self.assertGreater(state.values["drift_intensity"], 0.0)

    def test_heuristic_observation_maps_repair_to_reduced_anxiety(self):
        observation = heuristic_personality_drift_observation(
            "对不起，我错了，我会改正，也会补偿和修复关系。",
        )

        self.assertIn("repair_or_self_correction_event", observation.flags)
        self.assertGreater(observation.trait_impulses["honesty_humility"], 0.0)
        self.assertLess(observation.trait_impulses["attachment_anxiety"], 0.0)

    def test_heuristic_observation_keeps_compiled_pattern_semantics(self):
        observation = heuristic_personality_drift_observation(
            "thank you, I trust you. sorry, my fault, I will repair it together.",
        )

        self.assertIn("warmth_or_trust_event", observation.flags)
        self.assertIn("repair_or_self_correction_event", observation.flags)
        self.assertGreater(observation.trait_impulses["interpersonal_warmth"], 0.0)
        self.assertGreater(observation.trait_impulses["honesty_humility"], 0.0)

    def test_apply_drift_to_profile_is_bounded_and_non_mutating(self):
        profile = build_persona_profile(
            persona_id="sy",
            name="SY",
            text="温柔、认真、有点害羞，但愿意学习。",
        )
        state = PersonalityDriftState.initial(
            persona_fingerprint=profile.fingerprint,
            now=100.0,
        )
        state.trait_offsets["interpersonal_warmth"] = 0.12
        state.trait_offsets["attachment_avoidance"] = -0.08
        state.trait_confidence["interpersonal_warmth"] = 0.7
        state.evidence_count = 4
        state.values["drift_intensity"] = 0.5

        adapted = apply_personality_drift_to_profile(profile, state, strength=1.0)

        self.assertIsNot(adapted, profile)
        self.assertEqual(adapted.fingerprint, profile.fingerprint)
        self.assertIn("adaptive_drift", adapted.personality_model)
        self.assertIn("base_personality_model", adapted.personality_model)
        self.assertGreater(
            adapted.personality_model["trait_scores"]["interpersonal_warmth"],
            profile.personality_model["trait_scores"]["interpersonal_warmth"],
        )
        self.assertNotIn("adaptive_drift", profile.personality_model)

    def test_apply_empty_drift_returns_original_profile_without_copying(self):
        profile = build_persona_profile(
            persona_id="sy",
            name="SY",
            text="温柔、认真、有点害羞，但愿意学习。",
        )
        state = PersonalityDriftState.initial(
            persona_fingerprint=profile.fingerprint,
            now=100.0,
        )

        adapted = apply_personality_drift_to_profile(profile, state, strength=1.0)

        self.assertIs(adapted, profile)
        self.assertNotIn("adaptive_drift", profile.personality_model)

    def test_public_payload_and_memory_annotation_are_sanitized(self):
        state = PersonalityDriftState.initial(persona_fingerprint="p", now=100.0)
        state.trait_offsets["openness"] = 0.06
        state.values["drift_intensity"] = 0.3
        payload = personality_drift_state_to_public_payload(
            state,
            session_key="s1",
            exposure="plugin_safe",
        )
        annotation = build_personality_drift_memory_annotation(
            payload,
            source="livingmemory",
            written_at=120.0,
        )
        prompt = build_personality_drift_prompt_fragment(state)

        self.assertEqual(payload["schema_version"], PUBLIC_PERSONALITY_DRIFT_SCHEMA_VERSION)
        self.assertNotIn("trait_offsets", payload)
        self.assertEqual(annotation["kind"], "personality_drift_state_at_write")
        self.assertEqual(annotation["written_at"], 120.0)
        self.assertTrue(annotation["privacy"]["raw_message_text_excluded"])
        self.assertIn("Real elapsed time matters", prompt)
        self.assertIn("state_age_seconds", prompt)
        self.assertIn("not a linear message-count weight", prompt)

    def test_prompt_fragment_reports_real_state_age(self):
        state = PersonalityDriftState.initial(persona_fingerprint="p", now=100.0)
        state.updated_at = 100.0

        prompt = build_personality_drift_prompt_fragment(state, now=160.0)

        self.assertIn("updated_at=100.000", prompt)
        self.assertIn("state_age_seconds=60.0", prompt)


if __name__ == "__main__":
    unittest.main()
