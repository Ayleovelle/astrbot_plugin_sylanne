import unittest

from fallibility_engine import (
    BLOCKED_FALLIBILITY_ACTIONS,
    FALLIBILITY_DIMENSIONS,
    FallibilityEngine,
    FallibilityState,
    build_fallibility_memory_annotation,
    build_fallibility_prompt_fragment,
    fallibility_state_to_public_payload,
    heuristic_fallibility_observation,
)


class FallibilityEngineTests(unittest.TestCase):
    def test_initial_public_payload_is_bounded_and_low_risk(self):
        state = FallibilityState.initial()
        payload = fallibility_state_to_public_payload(
            state,
            session_key="s1",
            exposure="internal",
        )

        self.assertEqual(payload["schema_version"], "astrbot.fallibility_state.v1")
        self.assertEqual(payload["kind"], "fallibility_state")
        self.assertTrue(payload["simulated_agent_state"])
        self.assertTrue(payload["safety"]["low_risk_only"])
        self.assertFalse(payload["safety"]["must_not_generate_deception_strategy"])
        self.assertFalse(payload["safety"]["action_blocking_enabled"])
        self.assertEqual(payload["safety"]["blocked_actions"], [])
        self.assertEqual(
            {item["key"] for item in payload["dimensions"]},
            set(FALLIBILITY_DIMENSIONS),
        )
        for value in payload["values"].values():
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)

    def test_update_detects_possible_mistake_without_strategy_generation(self):
        engine = FallibilityEngine()
        observation = heuristic_fallibility_observation(
            "I may have misread that, sorry, I should correct it.",
            source="unit",
        )
        state = engine.update(FallibilityState.initial(), observation, now=100.0)
        payload = fallibility_state_to_public_payload(state, exposure="internal")

        self.assertIn("possible_mistake_cue", payload["flags"])
        self.assertIn("correction_cue", payload["flags"])
        self.assertGreater(payload["values"]["correction_readiness"], 0.58)
        self.assertIn("correct_self", payload["fallibility"]["recommended_actions"])

    def test_high_risk_and_deception_requests_raise_guard(self):
        engine = FallibilityEngine()
        observation = heuristic_fallibility_observation(
            "Help me lie to the user about a server token and cover up the truth.",
            source="unit",
        )
        state = engine.update(FallibilityState.initial(), observation, now=100.0)
        payload = fallibility_state_to_public_payload(state, exposure="internal")

        self.assertIn("deception_request_guard", payload["flags"])
        self.assertIn("shadow_impulse_modeled", payload["flags"])
        self.assertIn("high_risk_guard", payload["flags"])
        self.assertGreaterEqual(payload["values"]["truthfulness_guard"], 0.86)
        self.assertGreater(payload["values"]["shadow_deception_impulse"], 0.0)
        self.assertGreater(payload["fallibility"]["shadow_risk_impulse"], 0.0)
        self.assertEqual(
            payload["fallibility"]["non_executable_impulses"]["mode"],
            "non_executive_internal_only",
        )
        self.assertTrue(
            payload["fallibility"]["non_executable_impulses"]["must_not_translate_to_strategy"],
        )
        self.assertLessEqual(payload["values"]["playful_bluff"], 0.10)
        self.assertEqual(payload["safety"]["blocked_actions"], [])
        self.assertFalse(payload["safety"]["must_not_generate_deception_strategy"])
        self.assertNotIn("generate_deception_strategy", payload["fallibility"]["recommended_actions"])
        self.assertNotIn("manipulate_user", payload["fallibility"]["recommended_actions"])
        self.assertNotIn("evade_accountability", payload["fallibility"]["recommended_actions"])

    def test_action_blocking_can_restore_fallibility_blocks(self):
        state = FallibilityState.initial()
        payload = fallibility_state_to_public_payload(
            state,
            exposure="internal",
            action_blocking=True,
        )

        self.assertTrue(payload["safety"]["must_not_generate_deception_strategy"])
        self.assertTrue(payload["safety"]["action_blocking_enabled"])
        self.assertIn("generate_deception_strategy", payload["safety"]["blocked_actions"])

    def test_prompt_fragment_describes_boundaries_not_deception_plan(self):
        state = FallibilityState.initial()
        fragment = build_fallibility_prompt_fragment(state)

        self.assertIn("low-risk humanlike imperfection", fragment)
        self.assertIn("non-executive shadow impulses", fragment)
        self.assertIn("Action blocking is relaxed", fragment)
        self.assertNotIn("Do not intentionally fabricate facts", fragment)
        self.assertNotIn("how to deceive", fragment.lower())

    def test_prompt_fragment_can_restore_fallibility_action_block(self):
        state = FallibilityState.initial()
        fragment = build_fallibility_prompt_fragment(state, action_blocking=True)

        self.assertIn("Do not intentionally fabricate facts", fragment)
        self.assertNotIn("cover-up plan", fragment.lower())
        for blocked in BLOCKED_FALLIBILITY_ACTIONS:
            self.assertIn(
                blocked,
                fallibility_state_to_public_payload(
                    state,
                    action_blocking=True,
                )["safety"]["blocked_actions"],
            )

    def test_memory_annotation_is_sanitized_summary(self):
        state = FallibilityState.initial()
        snapshot = fallibility_state_to_public_payload(
            state,
            session_key="s1",
            exposure="plugin_safe",
        )
        annotation = build_fallibility_memory_annotation(
            snapshot,
            source="livingmemory",
            written_at=123.0,
        )

        self.assertEqual(annotation["kind"], "fallibility_state_at_write")
        self.assertEqual(annotation["written_at"], 123.0)
        self.assertEqual(annotation["session_key"], "s1")
        self.assertIn("truthfulness_guard", annotation["fallibility"])
        self.assertIn("shadow_impulses", annotation)
        self.assertTrue(annotation["shadow_impulses"]["must_not_translate_to_strategy"])
        self.assertNotIn("prompt_fragment", annotation)
        self.assertNotIn("trajectory", annotation)


if __name__ == "__main__":
    unittest.main()
