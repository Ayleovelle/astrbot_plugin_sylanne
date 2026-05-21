from __future__ import annotations

import unittest

from sylanne_alpha.assessor import assess_with_lanes


class SylanneAlphaAssessorTests(unittest.TestCase):
    def test_fast_assessor_disabled_uses_local_gate_even_with_provider(self):
        calls: list[str] = []

        def provider(prompt: str) -> dict[str, object]:
            calls.append(prompt)
            return {"complete": True}

        result = assess_with_lanes(
            text="我想问一下",
            switches={"fast_assessor": {"enabled": False, "provider_id": "fast"}},
            fast_provider=provider,
        )

        self.assertEqual(result["schema_version"], "sylanne.alpha.assessor.v1")
        self.assertEqual(result["source"], "local_gate")
        self.assertEqual(calls, [])

    def test_fast_assessor_failure_falls_back_without_blocking(self):
        def provider(prompt: str) -> dict[str, object]:
            raise TimeoutError("too slow")

        result = assess_with_lanes(
            text="还有一点",
            switches={"fast_assessor": {"enabled": True, "provider_id": "fast"}},
            fast_provider=provider,
        )

        self.assertEqual(result["source"], "local_gate")
        self.assertEqual(result["fallback_reason"], "fast_assessor_failed")
        self.assertIn(result["decision"], {"hold", "release"})

    def test_fast_assessor_success_returns_structured_decision_without_raw_prompt(self):
        def provider(prompt: str) -> dict[str, object]:
            return {"decision": "release", "confidence": 0.8, "reason": "complete_intent"}

        result = assess_with_lanes(
            text="我说完了。",
            switches={"fast_assessor": {"enabled": True, "provider_id": "fast"}},
            fast_provider=provider,
        )

        self.assertEqual(result["source"], "fast_assessor")
        self.assertEqual(result["decision"], "release")
        self.assertNotIn("prompt", result)
        self.assertNotIn("raw_text", result)


if __name__ == "__main__":
    unittest.main()
