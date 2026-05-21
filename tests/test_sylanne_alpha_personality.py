from __future__ import annotations

import unittest

from sylanne_alpha.personality import initial_personality, drift_personality


class SylanneAlphaPersonalityTests(unittest.TestCase):
    def test_initial_personality_is_stable_but_not_blank(self):
        first = initial_personality("room:a", seed_text="Sylanne Soulful")
        second = initial_personality("room:a", seed_text="Sylanne Soulful")
        other = initial_personality("room:b", seed_text="Sylanne Soulful")

        self.assertEqual(first, second)
        self.assertNotEqual(first["signature"], other["signature"])
        self.assertEqual(first["schema_version"], "sylanne.alpha.personality.v1")
        self.assertGreater(first["traits"]["warmth_bias"], 0.0)
        self.assertIn("voice", first)

    def test_personality_drifts_slowly_and_records_plasticity(self):
        base = initial_personality("room:drift", seed_text="Sylanne Soulful")
        drifted = drift_personality(base, event={"text": "我想让你更锋利一点", "confidence": 0.9}, rate=0.05)

        self.assertEqual(drifted["schema_version"], "sylanne.alpha.personality.v1")
        self.assertNotEqual(drifted["traits"], base["traits"])
        for name, value in drifted["traits"].items():
            self.assertLessEqual(abs(value - base["traits"][name]), 0.05)
        self.assertEqual(drifted["drift"]["mode"], "slow_plasticity")
        self.assertGreater(drifted["drift"]["events"], base["drift"]["events"])

    def test_personality_drift_never_exports_raw_event_text(self):
        base = initial_personality("room:safe", seed_text="Sylanne Soulful")
        drifted = drift_personality(base, event={"text": "一段很私密的话", "confidence": 1.0}, rate=0.05)

        self.assertNotIn("raw_text", drifted)
        self.assertNotIn("一段很私密的话", str(drifted))


if __name__ == "__main__":
    unittest.main()
