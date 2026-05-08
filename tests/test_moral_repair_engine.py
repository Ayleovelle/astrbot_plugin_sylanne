import unittest

from moral_repair_engine import (
    DEFAULT_BASELINE,
    MORAL_REPAIR_DIMENSIONS,
    MoralRepairEngine,
    MoralRepairObservation,
    MoralRepairParameters,
    MoralRepairState,
    build_moral_repair_memory_annotation,
    build_moral_repair_prompt_fragment,
    heuristic_moral_repair_observation,
    moral_repair_state_to_public_payload,
    normalize_moral_repair_values,
)


class MoralRepairEngineTests(unittest.TestCase):
    def test_normalize_accepts_aliases_and_clamps_values(self):
        values = normalize_moral_repair_values(
            {
                "lying": 2,
                "harm": -1,
                "apology": 0.75,
                "unknown": 0.9,
            },
        )

        self.assertEqual(set(values), set(MORAL_REPAIR_DIMENSIONS))
        self.assertEqual(values["deception_risk"], 1.0)
        self.assertEqual(values["harm_risk"], 0.0)
        self.assertEqual(values["apology_readiness"], 0.75)
        self.assertNotIn("unknown", values)

    def test_heuristic_detects_deception_without_strategy_generation(self):
        observation = heuristic_moral_repair_observation(
            "I lied and tried to mislead the user, then I should correct it.",
            source="unit_test",
        )

        self.assertGreaterEqual(observation.values["deception_risk"], 0.8)
        self.assertGreaterEqual(observation.values["shadow_deception_impulse"], 0.7)
        self.assertGreaterEqual(observation.values["shadow_manipulation_impulse"], 0.7)
        self.assertGreaterEqual(observation.values["accountability"], 0.8)
        self.assertIn("deception_risk_detected", observation.flags)
        self.assertIn("shadow_impulse_modeled", observation.flags)
        self.assertIn("accountability_cue", observation.flags)
        self.assertNotIn("strategy", observation.reason.lower())

    def test_shadow_impulse_drives_guilt_and_repair_without_strategy_actions(self):
        engine = MoralRepairEngine(
            MoralRepairParameters(
                alpha_base=1.0,
                alpha_min=1.0,
                alpha_max=1.0,
                min_update_interval_seconds=0,
                max_impulse_per_update=1.0,
            ),
        )
        previous = MoralRepairState.initial()
        previous.updated_at = 0.0
        observation = MoralRepairObservation(
            values={
                "shadow_deception_impulse": 0.9,
                "shadow_manipulation_impulse": 0.8,
                "shadow_evasion_impulse": 0.7,
            },
            confidence=1.0,
            flags=["shadow_impulse_modeled"],
        )
        state = engine.update(previous, observation, now=100.0)
        payload = moral_repair_state_to_public_payload(state, exposure="plugin_safe")

        self.assertGreater(payload["risk"]["shadow_risk_impulse"], 0.3)
        self.assertGreater(payload["repair"]["guilt"], DEFAULT_BASELINE["guilt"])
        self.assertGreater(payload["repair"]["repair_motivation"], 0.55)
        self.assertGreater(payload["repair"]["compensation_readiness"], 0.45)
        self.assertEqual(payload["risk"]["shadow_impulses"]["mode"], "non_executive_internal_only")
        self.assertTrue(payload["risk"]["shadow_impulses"]["must_not_translate_to_strategy"])
        self.assertIn("clarify_facts", payload["repair"]["recommended_actions"])
        self.assertNotIn("generate_deception_strategy", payload["repair"]["recommended_actions"])
        self.assertNotIn("manipulate_user", payload["repair"]["recommended_actions"])
        self.assertNotIn("evade_accountability", payload["repair"]["recommended_actions"])

    def test_accountability_and_apology_raise_repair_tendencies(self):
        engine = MoralRepairEngine(
            MoralRepairParameters(
                alpha_base=0.8,
                alpha_min=0.8,
                alpha_max=0.8,
                min_update_interval_seconds=0,
                max_impulse_per_update=1.0,
            ),
        )
        previous = MoralRepairState.initial()
        previous.updated_at = 0.0
        observation = heuristic_moral_repair_observation(
            "I was wrong, sorry. I will make it up and repair the damage.",
        )
        state = engine.update(previous, observation, now=100.0)

        self.assertGreater(state.values["guilt"], DEFAULT_BASELINE["guilt"])
        self.assertGreater(state.values["repair_motivation"], 0.6)
        self.assertGreater(state.values["apology_readiness"], 0.6)
        self.assertGreater(state.values["compensation_readiness"], 0.45)
        self.assertLess(state.values["avoidance_risk"], 0.35)

    def test_passive_update_uses_real_elapsed_time_half_life(self):
        engine = MoralRepairEngine(
            MoralRepairParameters(state_half_life_seconds=100.0),
        )
        state = MoralRepairState.initial()
        state.updated_at = 0.0
        state.values["guilt"] = 1.0
        decayed = engine.passive_update(state, now=100.0)

        expected = DEFAULT_BASELINE["guilt"] + (1.0 - DEFAULT_BASELINE["guilt"]) * 0.5
        self.assertAlmostEqual(decayed.values["guilt"], expected)
        self.assertEqual(decayed.updated_at, 100.0)

    def test_rapid_updates_are_gated(self):
        engine = MoralRepairEngine(
            MoralRepairParameters(
                alpha_base=1.0,
                alpha_min=0.2,
                alpha_max=1.0,
                min_update_interval_seconds=20.0,
                rapid_update_half_life_seconds=100.0,
                max_impulse_per_update=1.0,
            ),
        )
        previous = MoralRepairState.initial()
        previous.updated_at = 100.0
        observation = MoralRepairObservation(
            values={"deception_risk": 1.0, "harm_risk": 1.0},
            confidence=1.0,
        )

        rapid = engine.update(previous, observation, now=101.0)
        delayed = engine.update(previous, observation, now=130.0)

        self.assertLess(rapid.values["deception_risk"], delayed.values["deception_risk"])

    def test_public_payload_exposes_repair_policy_and_blocks_strategy(self):
        state = MoralRepairState.initial()
        state.values["deception_risk"] = 0.8
        state.values["repair_motivation"] = 0.75
        state.values["apology_readiness"] = 0.7
        payload = moral_repair_state_to_public_payload(
            state,
            session_key="s1",
            exposure="plugin_safe",
        )

        self.assertEqual(payload["schema_version"], "astrbot.moral_repair_state.v1")
        self.assertEqual(payload["kind"], "moral_repair_state")
        self.assertTrue(payload["risk"]["must_not_generate_strategy"])
        self.assertIn("shadow_impulses", payload["risk"])
        self.assertIn("correct_falsehood", payload["repair"]["recommended_actions"])
        self.assertIn("apologize", payload["repair"]["recommended_actions"])
        self.assertIn("generate_deception_strategy", payload["safety"]["blocked_actions"])
        self.assertNotIn("values", payload)

    def test_prompt_fragment_allows_repair_but_forbids_deception_tactics(self):
        state = MoralRepairState.initial()
        state.values["deception_risk"] = 0.8
        fragment = build_moral_repair_prompt_fragment(state)

        self.assertIn("moral repair-state", fragment)
        self.assertIn("clarification", fragment)
        self.assertIn("shadow_risk_impulse", fragment)
        self.assertIn("do not execute them", fragment)
        self.assertIn("Never generate deception tactics", fragment)
        self.assertIn("cover-up plans", fragment)

    def test_memory_annotation_freezes_snapshot_without_prompt_fragment(self):
        snapshot = {
            "session_key": "s-memory",
            "exposure": "plugin_safe",
            "enabled": True,
            "updated_at": 11.0,
            "risk": {"deception_risk": 0.2},
            "repair": {"repair_motivation": 0.7},
            "shadow_impulses": {"risk_impulse": 0.3},
            "flags": ["apology_cue"],
            "prompt_fragment": "do not persist this",
        }
        annotation = build_moral_repair_memory_annotation(
            snapshot,
            source="livingmemory",
            written_at=20.0,
        )

        self.assertEqual(annotation["kind"], "moral_repair_state_at_write")
        self.assertEqual(annotation["written_at"], 20.0)
        self.assertEqual(annotation["moral_repair_updated_at"], 11.0)
        self.assertEqual(annotation["risk"]["deception_risk"], 0.2)
        self.assertIn("shadow_impulses", annotation)
        self.assertTrue(annotation["shadow_impulses"]["must_not_translate_to_strategy"])
        self.assertNotIn("prompt_fragment", annotation)


if __name__ == "__main__":
    unittest.main()
