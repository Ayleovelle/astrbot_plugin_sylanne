import unittest

from humanlike_engine import (
    DEFAULT_BASELINE,
    HumanlikeEngine,
    HumanlikeObservation,
    HumanlikeParameters,
    HumanlikeState,
    build_humanlike_memory_annotation,
    build_humanlike_prompt_fragment,
    half_life_multiplier,
    heuristic_humanlike_observation,
    humanlike_state_to_public_payload,
)


class HumanlikeEngineTests(unittest.TestCase):
    def test_state_roundtrip_preserves_values_flags_and_trajectory(self):
        state = HumanlikeState.initial()
        state.values["stress_load"] = 0.72
        state.flags.append("dependency_pressure")
        state.trajectory.append(
            {
                "at": 100.0,
                "energy": 0.5,
                "stress_load": 0.72,
                "attention_budget": 0.6,
                "boundary_need": 0.4,
                "dependency_risk": 0.8,
                "flags": ["dependency_pressure"],
            },
        )
        restored = HumanlikeState.from_dict(state.to_dict())
        self.assertAlmostEqual(restored.values["stress_load"], 0.72)
        self.assertIn("dependency_pressure", restored.flags)
        self.assertEqual(len(restored.trajectory), 1)

    def test_half_life_decay_uses_real_elapsed_time(self):
        state = HumanlikeState.initial()
        state.updated_at = 0.0
        state.values["stress_load"] = 0.82
        engine = HumanlikeEngine(
            HumanlikeParameters(state_half_life_seconds=100.0),
        )
        decayed = engine.passive_update(state, now=100.0)
        expected = DEFAULT_BASELINE["stress_load"] + (0.82 - DEFAULT_BASELINE["stress_load"]) * 0.5
        self.assertAlmostEqual(decayed.values["stress_load"], expected)
        self.assertAlmostEqual(half_life_multiplier(100.0, 100.0), 0.5)

    def test_rapid_updates_are_gated(self):
        engine = HumanlikeEngine(
            HumanlikeParameters(
                alpha_base=1.0,
                alpha_min=0.0,
                alpha_max=1.0,
                min_update_interval_seconds=8.0,
                rapid_update_half_life_seconds=20.0,
                max_impulse_per_update=1.0,
            ),
        )
        previous = HumanlikeState.initial()
        previous.updated_at = 100.0
        observation = HumanlikeObservation(
            values={"stress_load": 1.0},
            confidence=1.0,
        )
        fast = engine.update(previous, observation, now=101.0)
        slow = engine.update(previous, observation, now=200.0)
        self.assertLess(fast.values["stress_load"], slow.values["stress_load"])

    def test_heuristic_detects_dependency_and_repair_cues(self):
        dependency = heuristic_humanlike_observation("你必须只能陪我，不许离开")
        self.assertIn("dependency_pressure", dependency.flags)
        self.assertGreaterEqual(dependency.values["dependency_risk"], 0.8)

        repair = heuristic_humanlike_observation("对不起，我会改，原谅我")
        self.assertIn("repair_attempt", repair.flags)
        self.assertLessEqual(repair.values["boundary_need"], 0.28)

    def test_public_payload_exposure_layers(self):
        state = HumanlikeEngine().update(
            HumanlikeState.initial(),
            HumanlikeObservation(
                values={"boundary_need": 0.9, "dependency_risk": 0.8},
                confidence=0.95,
                flags=["dependency_pressure"],
            ),
            now=1000.0,
        )
        internal = humanlike_state_to_public_payload(
            state,
            session_key="s1",
            exposure="internal",
        )
        plugin_safe = humanlike_state_to_public_payload(
            state,
            session_key="s1",
            exposure="plugin_safe",
        )
        user_facing = humanlike_state_to_public_payload(
            state,
            session_key="s1",
            exposure="user_facing",
        )
        self.assertEqual(internal["schema_version"], "astrbot.humanlike_state.v1")
        self.assertIn("values", internal)
        self.assertNotIn("values", plugin_safe)
        self.assertIn("modulation_basis", plugin_safe)
        self.assertNotIn("values", user_facing)
        self.assertIn("summary", user_facing)
        self.assertTrue(plugin_safe["simulated_agent_state"])
        self.assertFalse(plugin_safe["diagnostic"])

    def test_prompt_fragment_and_memory_annotation_are_simulation_scoped(self):
        state = HumanlikeState.initial()
        fragment = build_humanlike_prompt_fragment(state)
        self.assertIn("simulated humanlike-state", fragment)
        self.assertIn("not real consciousness", fragment)

        snapshot = humanlike_state_to_public_payload(
            state,
            session_key="s1",
            exposure="plugin_safe",
        )
        annotation = build_humanlike_memory_annotation(
            snapshot,
            source="livingmemory",
            written_at=123.0,
        )
        self.assertEqual(annotation["kind"], "humanlike_state_at_write")
        self.assertEqual(annotation["source"], "livingmemory")
        self.assertEqual(annotation["written_at"], 123.0)


if __name__ == "__main__":
    unittest.main()
