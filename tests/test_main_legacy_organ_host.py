import unittest

try:
    from tests.astrbot_lifecycle_helpers import install_astrbot_stubs, new_plugin
except ModuleNotFoundError:
    from astrbot_lifecycle_helpers import install_astrbot_stubs, new_plugin


class MainLegacyOrganHostTests(unittest.TestCase):
    def setUp(self):
        install_astrbot_stubs()

    def test_host_registers_legacy_modules_as_body_organs_without_public_export(self):
        plugin = new_plugin()

        organs = plugin._sylanne_legacy_organs
        roles = {organ.module_name: organ.organ_role for organ in organs}

        self.assertEqual("nerve_material", roles["conversation_event_ledger"])
        self.assertEqual("blood_trace_material", roles["memory_engine"])
        self.assertEqual("heart_temperature_material", roles["emotion_engine"])
        self.assertEqual("boundary_immunity_material", roles["fallibility_engine"])
        self.assertEqual("relational_wound_material", roles["moral_repair_engine"])
        self.assertEqual("expression_muscle_material", roles["lifelike_learning_engine"])
        self.assertEqual("long_term_tissue_material", roles["personality_drift_engine"])
        self.assertEqual("body_schema_material", roles["integrated_self"])
        self.assertEqual("foundation_organ_material", roles["project_life_engine"])
        self.assertFalse(any("human" in organ.describe().lower() for organ in organs))
        self.assertFalse(any("我是人" in organ.describe() for organ in organs))


if __name__ == "__main__":
    unittest.main()
