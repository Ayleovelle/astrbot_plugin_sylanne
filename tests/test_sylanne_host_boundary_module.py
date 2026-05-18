from __future__ import annotations

import unittest

from sylanne_body.host_boundary import append_auxiliary_state


class HostBoundaryModuleTests(unittest.TestCase):
    def test_append_auxiliary_state_builds_full_fragment_and_runs_after_append(self):
        calls = []
        after_calls = []
        decision = type("Decision", (), {"auxiliary_detail": "full"})()

        def append_text_part(request, text, *, source, budget):
            calls.append((request, text, source, budget))
            return True

        appended = append_auxiliary_state(
            request="request",
            state_name="group_atmosphere",
            full_builder=lambda: "full-fragment",
            source="group_atmosphere",
            injection_decision=decision,
            injection_budget="budget",
            append_text_part=append_text_part,
            build_state_injection=lambda state_name, full_builder, decision: f"{state_name}:{full_builder()}:{decision.auxiliary_detail}",
            build_compact_injection=lambda state_name: f"compact:{state_name}",
            fallback_source="group_atmosphere.compact_fallback",
            after_append=lambda: after_calls.append("after"),
        )

        self.assertTrue(appended)
        self.assertEqual(
            [("request", "group_atmosphere:full-fragment:full", "group_atmosphere", "budget")],
            calls,
        )
        self.assertEqual(["after"], after_calls)

    def test_append_auxiliary_state_uses_compact_fallback_only_when_full_mode_append_fails(self):
        calls = []
        decision = type("Decision", (), {"auxiliary_detail": "full"})()

        def append_text_part(request, text, *, source, budget):
            calls.append((text, source))
            return source.endswith("compact_fallback")

        appended = append_auxiliary_state(
            request="request",
            state_name="humanlike",
            full_builder=lambda: "too-large",
            source="humanlike",
            injection_decision=decision,
            injection_budget="budget",
            append_text_part=append_text_part,
            build_state_injection=lambda state_name, full_builder, decision: full_builder(),
            build_compact_injection=lambda state_name: f"compact:{state_name}",
            fallback_source="humanlike.compact_fallback",
        )

        self.assertFalse(appended)
        self.assertEqual(
            [("too-large", "humanlike"), ("compact:humanlike", "humanlike.compact_fallback")],
            calls,
        )

    def test_append_auxiliary_state_does_not_fallback_when_compact_mode_append_fails(self):
        calls = []
        decision = type("Decision", (), {"auxiliary_detail": "compact"})()

        def append_text_part(request, text, *, source, budget):
            calls.append((text, source))
            return False

        appended = append_auxiliary_state(
            request="request",
            state_name="lifelike_learning",
            full_builder=lambda: "ignored",
            source="lifelike_learning",
            injection_decision=decision,
            injection_budget="budget",
            append_text_part=append_text_part,
            build_state_injection=lambda state_name, full_builder, decision: "compact-via-decision",
            build_compact_injection=lambda state_name: f"fallback:{state_name}",
            fallback_source="lifelike_learning.compact_fallback",
        )

        self.assertFalse(appended)
        self.assertEqual([("compact-via-decision", "lifelike_learning")], calls)


if __name__ == "__main__":
    unittest.main()
