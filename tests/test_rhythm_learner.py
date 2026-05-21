"""Tests for adaptive rhythm learning."""
import unittest
from sylanne_alpha.rhythm_learner import RhythmLearner, RhythmProfile


class TestRhythmProfile(unittest.TestCase):
    def test_no_confidence_below_min_samples(self):
        p = RhythmProfile()
        for i in range(5):
            p.observe(f"msg {i}", 1000.0 + i * 3.0)
        self.assertEqual(p.confidence, 0.0)

    def test_confidence_grows_with_samples(self):
        p = RhythmProfile()
        for i in range(20):
            p.observe("hello world" * 3, 1000.0 + i * 5.0)
        self.assertGreater(p.confidence, 0.0)

    def test_learns_short_messages(self):
        p = RhythmProfile()
        for i in range(15):
            p.observe("嗯嗯", 1000.0 + i * 2.0)
        self.assertLess(p.avg_part_chars, 20)

    def test_learns_long_messages(self):
        p = RhythmProfile()
        long_msg = "这是一条比较长的消息，包含了很多内容和想法，用来测试长消息的学习效果"
        for i in range(15):
            p.observe(long_msg, 1000.0 + i * 8.0)
        self.assertGreater(p.avg_part_chars, 30)

    def test_modulate_blends_toward_user(self):
        p = RhythmProfile()
        short_msg = "嗯"
        for i in range(30):
            p.observe(short_msg, 1000.0 + i * 1.5)
        max_part, cps = p.modulate(48, 7.5, blend=0.8)
        self.assertLess(max_part, 48)

    def test_modulate_no_effect_at_zero_blend(self):
        p = RhythmProfile()
        for i in range(30):
            p.observe("hi", 1000.0 + i * 1.0)
        max_part, cps = p.modulate(48, 7.5, blend=0.0)
        self.assertEqual(max_part, 48)
        self.assertEqual(cps, 7.5)

    def test_serialization_roundtrip(self):
        p = RhythmProfile()
        for i in range(12):
            p.observe(f"message number {i}", 1000.0 + i * 4.0)
        data = p.to_dict()
        p2 = RhythmProfile.from_dict(data)
        self.assertAlmostEqual(p.confidence, p2.confidence, places=4)
        self.assertAlmostEqual(p.avg_part_chars, p2.avg_part_chars, places=4)


class TestRhythmLearner(unittest.TestCase):
    def test_only_learns_from_intimate_users(self):
        learner = RhythmLearner(intimacy_threshold=0.6)
        cold_obs = {"warmth": 0.1, "coherence": 0.5, "tension": 0.8}
        for i in range(20):
            learner.observe_user_message("cold_user", "hello", 1000.0 + i * 3.0, cold_obs)
        profile = learner.profile("cold_user")
        self.assertIsNone(profile)

    def test_learns_from_intimate_users(self):
        learner = RhythmLearner(intimacy_threshold=0.6)
        warm_obs = {"warmth": 0.9, "coherence": 0.9, "tension": 0.1}
        for i in range(20):
            learner.observe_user_message("warm_user", "你好呀", 1000.0 + i * 2.0, warm_obs)
        profile = learner.profile("warm_user")
        self.assertIsNotNone(profile)
        self.assertGreater(profile.confidence, 0.0)

    def test_get_rhythm_params_default_when_no_data(self):
        learner = RhythmLearner()
        max_part, cps = learner.get_rhythm_params("unknown_session")
        self.assertEqual(max_part, 48)
        self.assertEqual(cps, 7.5)

    def test_get_rhythm_params_adapts_with_data(self):
        learner = RhythmLearner(intimacy_threshold=0.3)
        warm_obs = {"warmth": 0.8, "coherence": 0.8, "tension": 0.1}
        short_msg = "嗯嗯好"
        for i in range(30):
            learner.observe_user_message("s1", short_msg, 1000.0 + i * 1.5, warm_obs)
        max_part, cps = learner.get_rhythm_params("s1")
        self.assertLess(max_part, 48)

    def test_serialization_roundtrip(self):
        learner = RhythmLearner(intimacy_threshold=0.5)
        warm_obs = {"warmth": 0.9, "coherence": 0.9, "tension": 0.0}
        for i in range(15):
            learner.observe_user_message("s1", "test msg", 1000.0 + i * 3.0, warm_obs)
        data = learner.to_dict()
        learner2 = RhythmLearner.from_dict(data, intimacy_threshold=0.5)
        p1 = learner.profile("s1")
        p2 = learner2.profile("s1")
        self.assertIsNotNone(p2)
        self.assertAlmostEqual(p1.confidence, p2.confidence, places=4)

    def test_intimacy_check(self):
        learner = RhythmLearner(intimacy_threshold=0.6)
        self.assertTrue(learner.is_intimate({"warmth": 0.9, "coherence": 0.9, "tension": 0.0}))
        self.assertFalse(learner.is_intimate({"warmth": 0.2, "coherence": 0.3, "tension": 0.9}))


if __name__ == "__main__":
    unittest.main()
