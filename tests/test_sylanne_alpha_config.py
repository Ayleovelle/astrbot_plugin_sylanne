from __future__ import annotations

import importlib
import sys
import unittest
from types import SimpleNamespace


class SylanneAlphaConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        sys.modules.pop("main", None)

    def test_plugin_exposes_4x_boundary_switches_with_safe_defaults(self):
        main = importlib.import_module("main")
        plugin = main.EmotionalStatePlugin(context=SimpleNamespace(), config={})

        switches = plugin.sylanne_alpha_switches()

        self.assertEqual(switches["schema_version"], "sylanne.alpha.config.v1")
        self.assertFalse(switches["realtime_chat"]["enabled"])
        self.assertFalse(switches["proactive_dispatch"]["enabled"])
        self.assertFalse(switches["embedding_memory"]["enabled"])
        self.assertEqual(switches["embedding_memory"]["provider_id"], "")
        self.assertFalse(switches["assessor_llm"]["enabled"])
        self.assertEqual(switches["assessor_llm"]["provider_id"], "")
        self.assertTrue(switches["fast_assessor"]["enabled"])
        self.assertEqual(switches["fast_assessor"]["provider_id"], "")
        self.assertGreaterEqual(switches["background_workers"]["max_workers"], 1)
        self.assertEqual(switches["safety"]["relational_public_export"], "blocked")

    def test_plugin_normalizes_explicit_4x_boundary_switches(self):
        main = importlib.import_module("main")
        plugin = main.EmotionalStatePlugin(
            context=SimpleNamespace(),
            config={
                "sylanne_alpha_realtime_chat_enabled": True,
                "sylanne_alpha_proactive_dispatch_enabled": True,
                "sylanne_alpha_embedding_memory_enabled": True,
                "sylanne_alpha_assessor_llm_enabled": True,
                "sylanne_alpha_fast_assessor_enabled": False,
                "sylanne_alpha_embedding_memory_provider_id": "embed/provider",
                "sylanne_alpha_assessor_provider_id": "judge/provider",
                "sylanne_alpha_fast_assessor_provider_id": "fast/provider",
                "sylanne_alpha_background_workers_enabled": True,
                "sylanne_alpha_background_max_workers": 3,
            },
        )

        switches = plugin.sylanne_alpha_switches()

        self.assertTrue(switches["realtime_chat"]["enabled"])
        self.assertTrue(switches["proactive_dispatch"]["enabled"])
        self.assertTrue(switches["embedding_memory"]["enabled"])
        self.assertEqual(switches["embedding_memory"]["provider_id"], "embed/provider")
        self.assertTrue(switches["assessor_llm"]["enabled"])
        self.assertEqual(switches["assessor_llm"]["provider_id"], "judge/provider")
        self.assertFalse(switches["fast_assessor"]["enabled"])
        self.assertEqual(switches["fast_assessor"]["provider_id"], "fast/provider")
        self.assertTrue(switches["background_workers"]["enabled"])
        self.assertEqual(switches["background_workers"]["max_workers"], 3)


if __name__ == "__main__":
    unittest.main()
