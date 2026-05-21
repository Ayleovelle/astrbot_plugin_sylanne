import unittest

from sylanne_body.organ.library import LEGACY_BODY_ORGAN_ROLES, LegacyBodyOrgan
from sylanne_body.event.normalize import normalize_event


class LegacyOrganLibraryTests(unittest.TestCase):
    def test_all_legacy_modules_have_clean_room_organ_roles(self):
        expected = {
            "conversation_event_ledger": "nerve_material",
            "memory_engine": "blood_trace_material",
            "emotion_engine": "heart_temperature_material",
            "fallibility_engine": "boundary_immunity_material",
            "moral_repair_engine": "relational_wound_material",
            "lifelike_learning_engine": "expression_muscle_material",
            "personality_drift_engine": "long_term_tissue_material",
            "integrated_self": "body_schema_material",
            "project_life_engine": "foundation_organ_material",
        }

        self.assertEqual(expected, LEGACY_BODY_ORGAN_ROLES)

    def test_legacy_organ_trace_contains_no_raw_text_and_cannot_export_public_api(self):
        organ = LegacyBodyOrgan(module_name="memory_engine")
        event = normalize_event(text="这里有 SECRET_ORGAN。", source="user")

        trace = organ.observe_event(event, relation_epoch=2)
        payload = trace.to_dict()

        self.assertEqual("memory_engine", payload["source"])
        self.assertEqual("blood_trace_material", payload["organ_role"])
        self.assertEqual(2, payload["relation_epoch"])
        self.assertTrue(payload["internal_only"])
        self.assertFalse(payload["public_api_eligible"])
        self.assertFalse(payload["can_disable_user_sovereignty"])
        self.assertNotIn("SECRET_ORGAN", str(payload))
        self.assertNotIn("text", str(payload).lower())

    def test_legacy_organ_description_does_not_claim_human_identity(self):
        organ = LegacyBodyOrgan(module_name="emotion_engine")

        description = organ.describe()

        self.assertIn("heart_temperature_material", description)
        self.assertNotIn("我是人", description)
        self.assertNotIn("human", description.lower())
        self.assertNotIn("真实痛苦", description)

    def test_unknown_legacy_module_is_rejected(self):
        with self.assertRaises(ValueError):
            LegacyBodyOrgan(module_name="unknown_legacy")


if __name__ == "__main__":
    unittest.main()
