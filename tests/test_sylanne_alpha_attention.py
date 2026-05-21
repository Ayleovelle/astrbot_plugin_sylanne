import unittest
from pathlib import Path

from sylanne_alpha.attention import SPARSE_ATTENTION_ROUTES, TinyBodyAttention, body_tokens, focus_information_flood, project_attention_delta
from sylanne_alpha.body import AlphaBodyState


ROOT = Path(__file__).resolve().parents[1]


class SylanneAlphaAttentionTests(unittest.TestCase):
    def test_body_attention_turns_fragment_events_into_bounded_body_delta(self):
        body = AlphaBodyState()
        event = body.event_vector(text="我在这里", flags=["safe"], confidence=0.8)
        core = TinyBodyAttention(hidden_dim=16, heads=2)

        result = core.update(body.state_vector(), event)

        self.assertEqual(result["schema_version"], "sylanne.alpha.attention.v1")
        self.assertLessEqual(result["cost"]["tokens"], 32)
        self.assertLessEqual(result["cost"]["hidden_dim"], 32)
        self.assertEqual(result["cost"]["layers"], 1)
        self.assertIn("bloodflow", result["attention"]["event.safe"])
        self.assertIn("immunity", result["attention"]["event.safe"])
        delta = result["delta"]
        self.assertGreater(delta["bloodflow.warmth"], 0.0)
        self.assertGreater(delta["temperature.warmth"], 0.0)
        self.assertLessEqual(abs(delta["bloodflow.warmth"]), 0.08)
        self.assertLessEqual(abs(delta["temperature.warmth"]), 0.08)

    def test_attention_delta_preserves_symbolic_guard_state(self):
        body = AlphaBodyState()
        body.immunity.interruption_budget = 0.18
        event = body.event_vector(text="", flags=["idle"], confidence=0.0, elapsed=8.0)

        delta = project_attention_delta(TinyBodyAttention().update(body.state_vector(), event))

        self.assertGreater(delta["needs.need_contact"], 0.0)
        self.assertGreater(delta["muscle.readiness"], 0.0)
        self.assertGreaterEqual(delta["immunity.interruption_budget"], 0.0)
        self.assertLessEqual(delta["immunity.interruption_budget"], 0.02)

    def test_body_tokens_are_small_stable_and_non_linguistic(self):
        tokens = body_tokens(AlphaBodyState().state_vector(), {"safe": 1.0, "has_text": 1.0})
        names = [token.name for token in tokens]

        self.assertLessEqual(len(tokens), 32)
        self.assertIn("organ.bloodflow", names)
        self.assertIn("law.immunity", names)
        self.assertIn("need.expression", names)
        self.assertIn("event.safe", names)
        self.assertTrue(all(len(token.values) <= 4 for token in tokens))
        self.assertTrue(all(isinstance(value, float) for token in tokens for value in token.values))

    def test_attention_uses_sparse_routes_instead_of_dense_token_pairs(self):
        body = AlphaBodyState()
        event = body.event_vector(text="别靠近", flags=["boundary", "hurt"], confidence=0.4)
        result = TinyBodyAttention().update(body.state_vector(), event)

        self.assertIn("event.boundary", SPARSE_ATTENTION_ROUTES)
        self.assertIn("immunity", SPARSE_ATTENTION_ROUTES["event.boundary"])
        self.assertEqual(result["cost"]["route_edges"], sum(len(targets) for targets in result["attention"].values()))
        self.assertLess(result["cost"]["route_edges"], result["cost"]["tokens"] ** 2)
        self.assertEqual(result["cost"]["route_complexity"], "O(E*R)")

    def test_tiny_attention_focuses_multi_person_information_flood(self):
        flood = focus_information_flood(
            [
                {"speaker": "alice", "text": "继续刚才的事", "flags": ["safe"], "confidence": 0.8, "now": 1.0},
                {"speaker": "bob", "text": "你为什么不理我", "flags": ["hurt", "boundary"], "confidence": 0.9, "now": 1.1},
                {"speaker": "alice", "text": "服务器又卡了", "flags": ["safe"], "confidence": 0.7, "now": 1.2},
                {"speaker": "carol", "text": "在吗", "flags": ["safe"], "confidence": 0.4, "now": 1.3},
                {"speaker": "dora", "text": "新的记忆结构和身体 attention 可以一起算吗", "flags": ["safe"], "confidence": 0.5, "now": 1.4},
            ],
            max_speakers=3,
            max_events=4,
            interests={"记忆": 0.9, "attention": 0.8},
        )

        self.assertEqual(flood["schema_version"], "sylanne.alpha.attention.flood.v1")
        self.assertEqual(flood["pressure"], 1.0)
        self.assertLessEqual(len(flood["selected_events"]), 4)
        self.assertEqual([speaker["speaker"] for speaker in flood["speakers"]], ["bob", "dora", "alice"])
        self.assertEqual(flood["selected_events"][0]["speaker"], "bob")
        self.assertIn("hurt", flood["selected_events"][0]["flags"])
        self.assertEqual(flood["selected_events"][1]["speaker"], "dora")
        self.assertEqual(flood["selected_events"][1]["interest_matches"], ["记忆", "attention"])
        self.assertEqual(flood["deferred_count"], 1)
        self.assertNotIn("raw_events", flood)

        from sylanne_alpha.vector import EVENT_INDEX, STATE_INDEX, WEIGHT_TERMS, linear_delta

        event = {"safe": 1.0, "has_text": 1.0, "elapsed": 2.0}
        delta = linear_delta(event)

        self.assertEqual(STATE_INDEX["bloodflow.warmth"], 12)
        self.assertEqual(EVENT_INDEX["safe"], 4)
        self.assertTrue(WEIGHT_TERMS)
        self.assertTrue(all(isinstance(axis_index, int) for axis_index, _ in WEIGHT_TERMS))
        self.assertAlmostEqual(delta["bloodflow.warmth"], 0.06)
        self.assertAlmostEqual(delta["pulse.beat"], 2.0)

    def test_theory_article_documents_tiny_body_attention_not_llm_replacement(self):
        article = (ROOT / "docs" / "sylanne_4_alpha_tiny_body_attention.md").read_text(encoding="utf-8")

        self.assertIn("# Sylanne 4.0 alpha 微型身体注意力层", article)
        self.assertIn("LLM 负责语言，tiny body attention 负责身体流通", article)
        self.assertIn("1C 1G", article)
        self.assertIn("symbolic guard", article)
        self.assertIn("不是语言模型", article)
        self.assertIn("O(T^2 d)", article)
        self.assertIn("token_count <= 32", article)
        self.assertIn("hidden_dim <= 32", article)
        self.assertNotIn("CUDA", article)


if __name__ == "__main__":
    unittest.main()
