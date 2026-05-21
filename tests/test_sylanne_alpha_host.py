from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sylanne_alpha.host import SylanneAlphaHost, SylanneAlphaHostEvent


class SylanneAlphaHostTests(unittest.TestCase):
    def test_host_boots_without_legacy_main_shadow(self):
        with tempfile.TemporaryDirectory() as tmp:
            host = SylanneAlphaHost(root=Path(tmp), session_key="room:alpha")

            surface = host.diagnostics()

        self.assertEqual(surface["schema_version"], "sylanne.alpha.body.v1")
        self.assertEqual(surface["session_key"], "room:alpha")
        self.assertNotIn("emotion_state", str(surface))
        self.assertNotIn("lifelike_learning", str(surface))

    def test_host_observes_request_and_response_through_kernel(self):
        with tempfile.TemporaryDirectory() as tmp:
            host = SylanneAlphaHost(root=Path(tmp), session_key="room:alpha")

            request_surface = host.on_request(SylanneAlphaHostEvent(text="我在这里", confidence=0.5, flags=["safe"], now=1.0))
            response_surface = host.on_response(SylanneAlphaHostEvent(text="我也在", confidence=0.7, flags=["safe"], now=2.0))

            self.assertEqual(request_surface["decision"]["action"], "wait")
            self.assertGreater(response_surface["body"]["pulse"]["beat"], request_surface["body"]["pulse"]["beat"])
            self.assertGreaterEqual(len(response_surface["body"]["memory"]["traces"]), 2)

    def test_host_persists_between_instances(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            host = SylanneAlphaHost(root=root, session_key="room:alpha")
            host.on_request(SylanneAlphaHostEvent(text="留下", flags=["safe"], now=1.0))

            restored = SylanneAlphaHost(root=root, session_key="room:alpha")
            surface = restored.diagnostics()

        self.assertEqual(surface["turns"], 1)
        self.assertEqual(surface["body"]["memory"]["traces"][0]["text"], "留下")

    def test_host_complete_runtime_flow_import_dialogue_proactive_pause_resume_restore(self):
        legacy = {
            "memory": {"records": [{"id": "old", "text": "旧关系数据"}]},
            "relationship": {"values": {"closeness": 0.8}},
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            host = SylanneAlphaHost(root=root, session_key="room:full", legacy=legacy)
            start = host.diagnostics()
            request = host.on_request(SylanneAlphaHostEvent(text="我回来了", confidence=0.8, flags=["safe"], now=1.0))
            response = host.on_response(SylanneAlphaHostEvent(text="我听见了", confidence=0.8, flags=["safe"], now=2.0))
            proactive = host.on_proactive_check(SylanneAlphaHostEvent(flags=["safe"], now=80.0))
            paused = host.on_request(SylanneAlphaHostEvent(flags=["pause"], now=81.0))
            resumed = host.on_request(SylanneAlphaHostEvent(flags=["resume", "safe"], now=82.0))
            restored = SylanneAlphaHost(root=root, session_key="room:full").diagnostics()

        self.assertEqual(start["body"]["memory"]["traces"][0]["text"], "旧关系数据")
        self.assertGreater(response["turns"], request["turns"])
        self.assertEqual(proactive["host_payload"]["kind"], "proactive_dispatch")
        self.assertFalse(paused["guard"]["allowed"])
        self.assertTrue(resumed["guard"]["allowed"])
        self.assertGreaterEqual(restored["turns"], 5)

    def test_host_import_does_not_require_astrbot_or_old_engines(self):
        import sylanne_alpha.host as host_module

        self.assertTrue(hasattr(host_module, "SylanneAlphaHost"))
        self.assertFalse(hasattr(host_module, "EmotionState"))
        self.assertFalse(hasattr(host_module, "LifelikeLearningState"))


if __name__ == "__main__":
    unittest.main()
