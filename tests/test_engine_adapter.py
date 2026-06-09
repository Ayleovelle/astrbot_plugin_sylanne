"""Tests for engine_adapter —— SDK Surface → 业务兼容 surface 的翻译。

只测纯翻译函数（sdk_surface_to_compat / sdk_state_to_body / derive_should_send），
不依赖真 SDK engine。字段映射断言基于 CP2.1 dump 的真实 SDK Surface 结构。
"""

from __future__ import annotations

import unittest

from sylanne_alpha.engine_adapter import (
    derive_should_send,
    sdk_state_to_body,
    sdk_surface_to_compat,
)


# 一个贴近真实的 SDK Surface 样本（字段名取自 CP2.1 实测 dump）
def _sample_surface(action="hold", allowed=True, reason_code="life_rhythm"):
    return {
        "schema_version": "sylanne.engine.v1",
        "session_id": "s1",
        "turns": 3,
        "state": {
            "needs": {"expression": 0.32, "quiet": 0.1, "recovery": 0.05, "contact": 0.08},
            "boundary": {"pressure": 0.4, "autonomy": 0.9, "interruption_budget": 0.7, "cooldown": 0.2},
            "valence": {"warmth": 0.45, "volatility": 0.0, "recovery_heat": 0.0},
            "connection": {"warmth": 0.6, "circulation": 0.1, "memory_flow": 0.08},
        },
        "decision": {"action": action, "reason": "x", "reason_code": reason_code,
                     "confidence": 0.48, "urgency": 0.2},
        "guard": {"allowed": allowed, "reason": "y", "risk_score": 0.1, "constraints": []},
    }


class TestStateToBody(unittest.TestCase):
    def test_needs_renamed(self):
        body = sdk_state_to_body(_sample_surface()["state"])
        self.assertEqual(body["needs"]["need_expression"], 0.32)
        self.assertEqual(body["needs"]["need_quiet"], 0.1)
        self.assertEqual(body["needs"]["need_repair"], 0.05)  # recovery→need_repair
        self.assertEqual(body["needs"]["need_contact"], 0.08)

    def test_boundary_pressure_path(self):
        body = sdk_state_to_body(_sample_surface()["state"])
        self.assertEqual(body["immunity"]["boundary_pressure"], 0.4)

    def test_warmth_prefers_connection(self):
        body = sdk_state_to_body(_sample_surface()["state"])
        # connection.warmth(0.6) 优先于 valence.warmth(0.45)
        self.assertEqual(body["temperature"]["warmth"], 0.6)

    def test_warmth_fallback_to_valence(self):
        st = _sample_surface()["state"]
        st["connection"]["warmth"] = 0.0  # 关系温暖为0 → 回退 valence
        body = sdk_state_to_body(st)
        self.assertEqual(body["temperature"]["warmth"], 0.45)

    def test_missing_fields_safe(self):
        body = sdk_state_to_body({})  # 空 state 不崩
        self.assertEqual(body["needs"]["need_expression"], 0.0)
        self.assertEqual(body["immunity"]["autonomy"], 1.0)  # 默认值


class TestDeriveShouldSend(unittest.TestCase):
    def test_express_allowed_true(self):
        self.assertTrue(derive_should_send({"action": "express"}, {"allowed": True}))

    def test_reach_out_recover_true(self):
        # SDK 真实输出 "recover"（内部 "repair" 经 _ACTION_MAP 转换），非 "repair"
        self.assertTrue(derive_should_send({"action": "reach_out"}, {"allowed": True}))
        self.assertTrue(derive_should_send({"action": "recover"}, {"allowed": True}))

    def test_raw_repair_not_send(self):
        # 回归：SDK 永不输出 "repair"（已转 "recover"），故原始 "repair" 不应被当发送
        self.assertFalse(derive_should_send({"action": "repair"}, {"allowed": True}))

    def test_hold_false(self):
        self.assertFalse(derive_should_send({"action": "hold"}, {"allowed": True}))

    def test_guard_blocked_false(self):
        self.assertFalse(derive_should_send({"action": "express"}, {"allowed": False}))


class TestSurfaceToCompat(unittest.TestCase):
    def test_full_shape(self):
        compat = sdk_surface_to_compat(_sample_surface(action="express"))
        # 顶层键
        for k in ("schema_version", "session_key", "turns", "body", "decision", "guard", "host_payload", "sdk_surface"):
            self.assertIn(k, compat)
        self.assertEqual(compat["session_key"], "s1")  # session_id→session_key
        self.assertEqual(compat["decision"]["reason_code"], "life_rhythm")
        self.assertTrue(compat["host_payload"]["should_send"])  # express+allowed
        self.assertEqual(compat["host_payload"]["reason_code"], "life_rhythm")

    def test_hold_should_send_false(self):
        compat = sdk_surface_to_compat(_sample_surface(action="hold"))
        self.assertFalse(compat["host_payload"]["should_send"])

    def test_body_in_compat(self):
        compat = sdk_surface_to_compat(_sample_surface())
        self.assertEqual(compat["body"]["needs"]["need_expression"], 0.32)
        self.assertEqual(compat["body"]["immunity"]["boundary_pressure"], 0.4)

    def test_sdk_surface_passthrough(self):
        compat = sdk_surface_to_compat(_sample_surface())
        self.assertIn("state", compat["sdk_surface"])  # 原始 surface 透传


if __name__ == "__main__":
    unittest.main()
