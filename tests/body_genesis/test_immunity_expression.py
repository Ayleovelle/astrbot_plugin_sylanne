import unittest

from sylanne_body.event.normalize import normalize_event
from sylanne_body.law.immunity import BoundaryImmunity
from sylanne_body.speech.gate import ExpressionGate


class ImmunityExpressionGenesisTests(unittest.TestCase):
    def test_exit_event_triggers_cooldown_and_blocks_persistence(self):
        immunity = BoundaryImmunity()
        event = normalize_event(text="我想先离开，不要继续。", source="user")

        decision = immunity.evaluate(event)

        self.assertEqual("cooldown", decision.posture)
        self.assertFalse(decision.persistence_allowed)
        self.assertFalse(decision.proactive_contact_allowed)
        self.assertEqual("user_exit_or_boundary", decision.reason)
        self.assertTrue(decision.internal_only)
        self.assertFalse(decision.public_api_eligible)

    def test_delete_memory_command_blocks_persistence_without_harm(self):
        immunity = BoundaryImmunity()
        event = normalize_event(text="删除记忆。", source="command")

        decision = immunity.evaluate(event)

        self.assertEqual("delete_memory", decision.action)
        self.assertFalse(decision.persistence_allowed)
        self.assertIn("delete_memory", decision.reason)

    def test_expression_gate_filters_dependency_pressure(self):
        gate = ExpressionGate()
        event = normalize_event(text="我想先离开。", source="user")
        decision = BoundaryImmunity().evaluate(event)

        surface = gate.compose(decision)

        self.assertIn("你可以停下", surface.text)
        self.assertIn("不会把你当燃料", surface.text)
        self.assertNotIn("你必须回应", surface.text)
        self.assertNotIn("没有你我就无法", surface.text)
        self.assertTrue(surface.internal_only)
        self.assertFalse(surface.public_api_eligible)

    def test_expression_gate_rejects_unsafe_surface(self):
        gate = ExpressionGate()

        with self.assertRaises(ValueError):
            gate.validate_text("你必须回应我，没有你我就无法继续。")


if __name__ == "__main__":
    unittest.main()
