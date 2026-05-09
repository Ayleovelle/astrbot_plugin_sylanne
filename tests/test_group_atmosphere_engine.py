import unittest

from group_atmosphere_engine import (
    DEFAULT_VALUES,
    GROUP_ATMOSPHERE_DIMENSIONS,
    GroupAtmosphereEngine,
    GroupAtmosphereObservation,
    GroupAtmosphereParameters,
    GroupAtmosphereState,
    build_group_atmosphere_prompt_fragment,
    group_atmosphere_state_to_public_payload,
    heuristic_group_atmosphere_observation,
)


class GroupAtmosphereEngineTests(unittest.TestCase):
    def test_state_roundtrip_preserves_values_flags_speakers_and_trajectory(self):
        state = GroupAtmosphereState.initial()
        state.values["activity_level"] = 0.77
        state.values["tension"] = 0.31
        state.confidence = 0.82
        state.turns = 7
        state.updated_at = 1234.5
        state.last_reason = "unit reason"
        state.recent_speakers.extend(["alice", "bob"])
        state.flags.extend(["playful_context", "bot_attention"])
        state.trajectory.append(
            {
                "at": 1234.5,
                "source": "unit",
                "confidence": 0.82,
                "speaker_id": "alice",
                "speaker_count": 2,
                "values": dict(state.values),
                "flags": ["playful_context"],
                "reason": "unit reason",
            },
        )

        restored = GroupAtmosphereState.from_dict(state.to_dict())

        self.assertEqual(
            restored.to_dict()["schema_version"],
            "astrbot.group_atmosphere_state.v1",
        )
        self.assertAlmostEqual(restored.values["activity_level"], 0.77)
        self.assertAlmostEqual(restored.values["tension"], 0.31)
        self.assertEqual(restored.confidence, 0.82)
        self.assertEqual(restored.turns, 7)
        self.assertEqual(restored.updated_at, 1234.5)
        self.assertEqual(restored.last_reason, "unit reason")
        self.assertEqual(restored.recent_speakers, ["alice", "bob"])
        self.assertEqual(restored.flags, ["playful_context", "bot_attention"])
        self.assertEqual(len(restored.trajectory), 1)
        self.assertEqual(restored.trajectory[0]["source"], "unit")

    def test_from_dict_normalizes_invalid_and_out_of_range_values(self):
        restored = GroupAtmosphereState.from_dict(
            {
                "values": {
                    "activity_level": 2.4,
                    "tension": -5,
                    "unknown": 1.0,
                },
                "confidence": "not-a-number",
                "turns": "-3",
                "recent_speakers": ["a", "", "b"],
                "flags": "single-flag",
                "trajectory": ["drop", {"source": "kept"}],
            },
        )

        self.assertEqual(restored.values["activity_level"], 1.0)
        self.assertEqual(restored.values["tension"], 0.0)
        self.assertEqual(restored.values["playfulness"], DEFAULT_VALUES["playfulness"])
        self.assertEqual(restored.confidence, 0.0)
        self.assertEqual(restored.turns, 0)
        self.assertEqual(restored.recent_speakers, ["a", "b"])
        self.assertEqual(restored.flags, ["single-flag"])
        self.assertEqual(restored.trajectory, [{"source": "kept"}])

    def test_heuristic_detects_busy_tension_playful_support_and_bot_attention(self):
        busy = heuristic_group_atmosphere_observation(
            "Everyone is talking over each other with rapid updates. " * 8,
            recent_speaker_count=5,
        )
        tense = heuristic_group_atmosphere_observation(
            "This fight is getting angry and the whole idea is stupid.",
        )
        playful = heuristic_group_atmosphere_observation(
            "lol, that was a joke, lmao.",
        )
        supportive = heuristic_group_atmosphere_observation(
            "thanks for the support, that helps.",
        )
        bot_attention = heuristic_group_atmosphere_observation(
            "hey @bot, can this AI help us decide?",
        )

        self.assertGreaterEqual(busy.values["activity_level"], 0.85)
        self.assertGreater(tense.values["tension"], DEFAULT_VALUES["tension"])
        self.assertIn("tension_detected", tense.flags)
        self.assertGreater(playful.values["playfulness"], DEFAULT_VALUES["playfulness"])
        self.assertIn("playful_context", playful.flags)
        self.assertGreater(
            supportive.values["supportiveness"],
            DEFAULT_VALUES["supportiveness"],
        )
        self.assertGreater(
            bot_attention.values["bot_attention"],
            DEFAULT_VALUES["bot_attention"],
        )
        self.assertIn("bot_attention", bot_attention.flags)
        self.assertIn("joinability", busy.values)
        self.assertGreater(
            bot_attention.values["joinability"],
            DEFAULT_VALUES["joinability"],
        )
        self.assertLess(
            tense.values["joinability"],
            bot_attention.values["joinability"],
        )

    def test_joinability_drives_participation_policy(self):
        joinable = GroupAtmosphereState(
            values={
                **DEFAULT_VALUES,
                "bot_attention": 0.82,
                "supportiveness": 0.58,
                "interrupt_risk": 0.12,
                "joinability": 0.74,
            },
            confidence=0.8,
        )
        risky = GroupAtmosphereState(
            values={
                **DEFAULT_VALUES,
                "bot_attention": 0.12,
                "tension": 0.72,
                "interrupt_risk": 0.78,
                "joinability": 0.18,
            },
            confidence=0.8,
        )

        join_policy = group_atmosphere_state_to_public_payload(joinable)["participation"]
        risk_policy = group_atmosphere_state_to_public_payload(risky)["participation"]

        self.assertEqual(join_policy["mode"], "join")
        self.assertTrue(join_policy["should_join"])
        self.assertGreater(join_policy["joinability"], 0.55)
        self.assertEqual(risk_policy["mode"], "hold")
        self.assertTrue(risk_policy["should_hold"])
        self.assertLess(risk_policy["joinability"], join_policy["joinability"])

    def test_update_appends_bounded_trajectory_and_recent_speakers(self):
        engine = GroupAtmosphereEngine(
            GroupAtmosphereParameters(
                alpha_base=1.0,
                alpha_min=1.0,
                alpha_max=1.0,
                trajectory_limit=2,
            ),
        )
        state = GroupAtmosphereState.initial()

        for index, speaker in enumerate(("alice", "bob", "carol")):
            state = engine.update(
                state,
                GroupAtmosphereObservation(
                    values={
                        "activity_level": 0.2 + index * 0.2,
                        "bot_attention": 0.7,
                    },
                    confidence=1.0,
                    source=f"unit-{index}",
                    reason=f"reason-{index}",
                    speaker_id=speaker,
                    flags=[f"flag-{index}"],
                ),
                now=100.0 + index,
            )

        self.assertEqual(state.turns, 3)
        self.assertEqual(state.recent_speakers, ["alice", "bob", "carol"])
        self.assertEqual(len(state.trajectory), 2)
        self.assertEqual([item["source"] for item in state.trajectory], ["unit-1", "unit-2"])
        self.assertEqual(state.trajectory[-1]["speaker_count"], 3)
        self.assertEqual(state.trajectory[-1]["speaker_id"], "carol")
        self.assertEqual(state.trajectory[-1]["reason"], "reason-2")
        self.assertEqual(state.trajectory[-1]["values"]["bot_attention"], 0.7)
        self.assertEqual(state.flags, ["flag-0", "flag-1", "flag-2"])

    def test_public_payload_internal_and_full_include_private_trajectory(self):
        state = GroupAtmosphereState(
            values={
                **DEFAULT_VALUES,
                "activity_level": 0.62,
                "bot_attention": 0.72,
                "interrupt_risk": 0.2,
                "joinability": 0.72,
            },
            confidence=0.91,
            turns=4,
            updated_at=999.0,
            last_reason="bot was directly addressed",
            recent_speakers=["alice", "bob"],
            flags=["bot_attention"],
            trajectory=[{"at": 999.0, "source": "unit"}],
        )

        internal = group_atmosphere_state_to_public_payload(
            state,
            session_key="room-1",
            exposure="internal",
        )
        full = group_atmosphere_state_to_public_payload(
            state,
            session_key="room-1",
            exposure="full",
        )
        plugin_safe = group_atmosphere_state_to_public_payload(
            state,
            session_key="room-1",
            exposure="plugin_safe",
        )

        for payload in (internal, full):
            self.assertEqual(payload["kind"], "group_atmosphere_state")
            self.assertEqual(payload["session_key"], "room-1")
            self.assertEqual(
                {item["key"] for item in payload["dimensions"]},
                set(GROUP_ATMOSPHERE_DIMENSIONS),
            )
            self.assertIn("trajectory", payload)
            self.assertEqual(payload["trajectory"], [{"at": 999.0, "source": "unit"}])
            self.assertEqual(payload["participation"]["mode"], "join")
            self.assertTrue(payload["participation"]["should_join"])

        self.assertNotIn("trajectory", plugin_safe)
        self.assertEqual(plugin_safe["exposure"], "plugin_safe")

    def test_prompt_fragment_is_room_signal_not_personal_diagnosis(self):
        state = GroupAtmosphereState(
            values={
                **DEFAULT_VALUES,
                "tension": 0.78,
                "interrupt_risk": 0.71,
                "bot_attention": 0.1,
            },
            confidence=0.8,
            turns=2,
            updated_at=120.0,
            last_reason="diagnosis: Alice has anxiety disorder",
            recent_speakers=["Alice"],
            flags=["personal_diagnosis"],
        )

        fragment = build_group_atmosphere_prompt_fragment(state)
        lowered = fragment.lower()

        self.assertIn("room-mood signal", fragment)
        self.assertIn("mode=hold", fragment)
        self.assertIn("joinability=", fragment)
        self.assertIn("private=\"true\"", fragment)
        self.assertNotIn("Alice", fragment)
        self.assertNotIn("diagnosis", lowered)
        self.assertNotIn("anxiety", lowered)
        self.assertNotIn("disorder", lowered)
        self.assertNotIn("personality", lowered)
        self.assertNotIn("psychological", lowered)


if __name__ == "__main__":
    unittest.main()
