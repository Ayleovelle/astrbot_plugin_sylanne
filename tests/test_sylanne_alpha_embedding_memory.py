from __future__ import annotations

import unittest

from sylanne_alpha.embedding_memory import recall_with_embedding_assist


class SylanneAlphaEmbeddingMemoryTests(unittest.TestCase):
    def test_keyword_hit_does_not_call_embedding_provider(self):
        calls: list[str] = []

        def embed(text: str) -> list[float]:
            calls.append(text)
            return [1.0, 0.0]

        result = recall_with_embedding_assist(
            query="服务器",
            records=[{"id": "m1", "text": "服务器卡死经验", "weight": 0.7}],
            enabled=True,
            embed_query=embed,
        )

        self.assertEqual(result["schema_version"], "sylanne.alpha.embedding_memory.v1")
        self.assertEqual(result["source"], "keyword")
        self.assertEqual(calls, [])
        self.assertEqual(result["matches"][0]["id"], "m1")

    def test_embedding_assist_runs_only_when_no_keyword_hit_and_vectors_exist(self):
        calls: list[str] = []

        def embed(text: str) -> list[float]:
            calls.append(text)
            return [1.0, 0.0]

        result = recall_with_embedding_assist(
            query="宕机",
            records=[{"id": "m1", "text": "容器压力", "embedding": [0.9, 0.1], "weight": 0.5}],
            enabled=True,
            embed_query=embed,
        )

        self.assertEqual(result["source"], "embedding")
        self.assertEqual(calls, ["宕机"])
        self.assertEqual(result["matches"][0]["id"], "m1")

    def test_embedding_disabled_falls_back_to_keyword_empty(self):
        result = recall_with_embedding_assist(
            query="宕机",
            records=[{"id": "m1", "text": "容器压力", "embedding": [0.9, 0.1]}],
            enabled=False,
            embed_query=lambda text: [1.0, 0.0],
        )

        self.assertEqual(result["source"], "keyword")
        self.assertEqual(result["matches"], [])


if __name__ == "__main__":
    unittest.main()
