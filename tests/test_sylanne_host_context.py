from __future__ import annotations

import unittest

from sylanne_body.host_context import build_interpretation_candidates_context


class HostContextModuleTests(unittest.TestCase):
    def test_build_interpretation_candidates_context_limits_and_formats_candidates(self):
        text = build_interpretation_candidates_context(
            [
                {
                    "raw_text": "寄忆",
                    "candidate": "记忆",
                    "kind": "homophone",
                    "confidence": 0.91,
                    "humor_likelihood": 0.2,
                    "memory_layer": "episodic",
                },
                {
                    "raw_text": "螺旋",
                    "candidate": "继续展开",
                    "kind": "slang",
                    "confidence": 0.62,
                    "humor_likelihood": 0.1,
                    "memory_layer": "uncertain_interpretation",
                },
                {"raw_text": "third", "candidate": "三号", "kind": "nickname"},
                {"raw_text": "fourth", "candidate": "四号", "kind": "nickname"},
            ],
            memory_gate_classifier=lambda item: {"layer": item.get("memory_layer")},
            head_one_line=lambda value, limit: value[:limit],
        )

        self.assertIn("[sylanne_interpretation_candidates]", text)
        self.assertIn("raw_text=寄忆; candidate=记忆; kind=homophone", text)
        self.assertIn("memory_layer=episodic", text)
        self.assertIn("raw_text=third; candidate=三号", text)
        self.assertNotIn("fourth", text)

    def test_build_interpretation_candidates_context_returns_empty_without_candidates(self):
        self.assertEqual(
            "",
            build_interpretation_candidates_context(
                [],
                memory_gate_classifier=lambda item: {"layer": "unused"},
                head_one_line=lambda value, limit: value[:limit],
            ),
        )


if __name__ == "__main__":
    unittest.main()
