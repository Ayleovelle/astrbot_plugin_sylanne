import unittest

from memory_engine import (
    MemoryRecord,
    SylanneMemoryState,
    build_memory_prompt_fragment,
    derive_memory_dynamics,
    observe_memory_event,
    recall_memory,
)


class SylanneMemoryEngineTests(unittest.TestCase):
    def test_memory_dynamics_are_derived_without_user_tunable_parameters(self):
        emotion = {
            "emotion": {
                "label": "hurt",
                "confidence": 0.82,
                "values": {
                    "valence": -0.55,
                    "arousal": 0.72,
                    "affiliation": -0.38,
                    "certainty": 0.64,
                },
            },
            "relationship": {
                "decision": "boundary",
                "conflict_analysis": {"cause": "user_fault"},
            },
        }
        personality = {
            "trait_offsets": {
                "neuroticism": 0.42,
                "agreeableness": -0.2,
                "attachment_anxiety": 0.38,
                "emotion_regulation_capacity": -0.24,
            },
            "values": {
                "drift_intensity": 0.44,
                "anchor_strength": 0.76,
                "relationship_sensitivity": 0.55,
            },
        }
        lifelike = {
            "values": {
                "rapport": 0.74,
                "common_ground": 0.66,
                "preference_confidence": 0.51,
                "boundary_sensitivity": 0.58,
            },
        }

        dynamics = derive_memory_dynamics(
            emotion_snapshot=emotion,
            personality_drift_snapshot=personality,
            lifelike_snapshot=lifelike,
            group_atmosphere_snapshot={},
            now=1000.0,
        )

        self.assertGreater(dynamics.salience_bias, 0.55)
        self.assertGreater(dynamics.relationship_weight, 0.65)
        self.assertGreater(dynamics.consolidation_gain, 0.45)
        self.assertGreater(dynamics.decay_half_life_seconds, 86400.0)
        self.assertGreaterEqual(dynamics.recall_limit, 2)
        self.assertLessEqual(dynamics.recall_limit, 5)
        self.assertGreaterEqual(dynamics.recall_maturation_seconds, 0.0)
        self.assertLessEqual(dynamics.recall_maturation_seconds, 12.0)
        self.assertIn("auto_derived", dynamics.notes)

    def test_observe_memory_event_consolidates_and_recall_decays_with_real_time(self):
        state = SylanneMemoryState.initial(now=0.0)
        state = observe_memory_event(
            state,
            text="用户解释过：他们指插件的其他用户，不是恋爱对象。",
            session_key="s-memory",
            speaker_id="u1",
            emotion_snapshot={
                "emotion": {
                    "label": "guarded",
                    "confidence": 0.86,
                    "values": {"valence": -0.4, "arousal": 0.66, "affiliation": -0.2},
                },
                "relationship": {"decision": "clarify"},
            },
            lifelike_snapshot={
                "values": {"rapport": 0.7, "common_ground": 0.62},
            },
            now=10.0,
        )

        self.assertEqual(len(state.records), 1)
        record = state.records[0]
        self.assertGreater(record.depth, 0.45)
        self.assertIn("episodic", record.layers)
        self.assertIn("relationship", record.layers)
        self.assertEqual(record.auto_parameters["recall_limit"], state.dynamics.recall_limit)
        self.assertEqual(
            record.auto_parameters["recall_maturation_seconds"],
            state.dynamics.to_dict()["recall_maturation_seconds"],
        )

        fresh = recall_memory(
            state,
            query="那你有什么想对他们说的吗",
            now=60.0,
        )
        old = recall_memory(
            state,
            query="那你有什么想对他们说的吗",
            now=60.0 + state.dynamics.decay_half_life_seconds * 4,
        )

        self.assertEqual(len(fresh), 1)
        self.assertEqual(len(old), 1)
        self.assertGreater(fresh[0].score, old[0].score)
        self.assertGreater(fresh[0].score, 0.2)

    def test_prompt_fragment_is_bounded_and_marks_first_party_memory(self):
        state = SylanneMemoryState.initial(now=0.0)
        state.records.append(
            MemoryRecord(
                text="用户说过 README 要尽量中文，不要像炫耀。",
                summary="README 要中文、克制，不要炫耀。",
                session_key="s-doc",
                speaker_id="u1",
                created_at=10.0,
                updated_at=10.0,
                depth=0.82,
                confidence=0.74,
                layers={"episodic": 0.7, "semantic": 0.6, "relationship": 0.4},
            ),
        )

        fragment = build_memory_prompt_fragment(
            recall_memory(state, query="README 怎么写", now=20.0),
            session_key="s-doc",
            max_chars=220,
        )

        self.assertIn("sylanne_memory_recall", fragment)
        self.assertIn("README 要中文", fragment)
        self.assertLessEqual(len(fragment), 220)


if __name__ == "__main__":
    unittest.main()
