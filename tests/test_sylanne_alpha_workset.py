from __future__ import annotations

import unittest

from sylanne_alpha.workset import build_fragment_workset


class SylanneAlphaWorksetTests(unittest.TestCase):
    def test_workset_integrates_fragments_shadow_and_memory_under_budget(self):
        workset = build_fragment_workset(
            session_key="room",
            fragments=["我刚才没说完", "是关于服务器卡死"],
            shadow={"summary": "上一轮 Sylanne 的回复被用户打断", "consume": True},
            memory_matches=[
                {"id": "m1", "text": "服务器曾经因为同步 IO 卡死", "weight": 0.9},
                {"id": "m2", "text": "无关闲聊", "weight": 0.1},
            ],
            max_items=3,
        )

        self.assertEqual(workset["schema_version"], "sylanne.alpha.workset.v1")
        self.assertEqual(workset["current_intent"], "我刚才没说完 是关于服务器卡死")
        self.assertLessEqual(len(workset["items"]), 3)
        self.assertEqual(workset["items"][0]["kind"], "current_intent")
        self.assertIn("shadow_continuity", [item["kind"] for item in workset["items"]])
        self.assertNotIn("raw_fragments", workset)

    def test_blackboard_workset_collects_department_evidence_without_raw_leakage(self):
        workset = build_fragment_workset(
            session_key="room",
            fragments=["你刚才为什么停住了"],
            shadow={"summary": "上一轮被打断", "consume": True},
            memory_matches=[{"id": "m1", "text": "用户不喜欢死锁等待", "weight": 0.8}],
            dialogue={"segment": "interruption", "confidence": 0.7},
            personality={"signature": "quiet-burning", "drift": 0.02},
            body={"need": 0.4, "risk": 0.3, "plasticity": 0.2},
            assessor={"lane": "local", "suggestion": "wait", "confidence": 0.6},
            guard={"allowed": False, "flags": ["boundary_immunity"], "risk_score": 0.7},
            attention={"primary": "guard", "weights": {"guard": 0.9, "memory": 0.5}},
        )

        self.assertEqual(workset["mode"], "blackboard")
        self.assertEqual(
            [item["department"] for item in workset["evidence"]],
            ["dialogue", "memory", "personality", "body", "assessor", "guard", "attention"],
        )
        self.assertEqual(workset["coordination"]["primary_department"], "guard")
        self.assertEqual(workset["coordination"]["fast_path"], ["dialogue", "memory", "body", "guard", "attention"])
        self.assertEqual(workset["coordination"]["slow_path"], ["personality", "assessor"])
        self.assertNotIn("raw_fragments", workset)
        self.assertIn("Sylanne blackboard", workset["prompt_fragment"])


if __name__ == "__main__":
    unittest.main()
