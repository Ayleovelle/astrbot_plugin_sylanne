"""Tests for EmotionSpiritBridge —— Sylanne ↔ astrbot_plugin_emotion_spirit 适配桥（Design B）。

2026-06-29 本机装 emotion_spirit v1.1.0、11-agent 工作流深挖真实 API 后，用户拍板 Design B：
  - 记忆仍以 Sylanne 原生为主控；只【消费】它的稳定情绪/躯体状态注入 system_prompt 当背景。
  - 引擎共享确认结构上不可行 → align_shared_engine 永久 no-op、移除开关。
  - 记忆写入路由（memory_backend）作 Phase 2 镜像双写预置，当前不接线但已修真 bug。

测试替身按【实测 API】构造（非旧脚手架幻觉）：
  - 实例属性 _pool / _public_api / _persona_mode（main.py:78/220）。
  - PublicAPI.get_emotion_state/get_body_state 是 **async**、cold session 返 None。
  - MemoryPool.add(..., participants=, privacy=) / recall(keyword, current_user=, max_results=)，
    recall 返回带 .tier/.emotional_weight/.text 的对象（非 .pool/.score）。
"""

from __future__ import annotations

import asyncio
import unittest

from sylanne_alpha.emotion_spirit_bridge import (
    EMOTION_SPIRIT_STAR_NAME,
    EmotionSpiritBridge,
    _bucket,
    _clamp,
    _clamp01,
)


# ---------------------------------------------------------------------------
# 测试替身：按实测 emotion_spirit v1.1.0 API 构造
# ---------------------------------------------------------------------------
class FakeEntry:
    """模拟 emotion_spirit UnifiedEntry：真实字段 .tier/.emotional_weight/.text。"""

    def __init__(self, text: str, tier: str, emotional_weight: float) -> None:
        self.text = text
        self.tier = tier
        self.emotional_weight = emotional_weight
        self.source_user = "user1"


class FakeMemoryPool:
    """模拟 emotion_spirit MemoryPool：真实 add/recall 签名，记录调用。"""

    def __init__(self) -> None:
        self.added: list[dict] = []
        self.recall_calls: list[tuple] = []

    def add(
        self,
        text,
        raw_weight=None,
        phi=None,
        tags=None,
        source_user=None,
        participants=None,
        privacy="private",
        entities=None,
    ) -> FakeEntry:
        self.added.append(
            {
                "text": text,
                "raw_weight": raw_weight,
                "phi": phi,
                "tags": list(tags or []),
                "source_user": source_user,
                "participants": set(participants) if participants else None,
            }
        )
        return FakeEntry(text, "buffer", raw_weight or 0.0)

    def recall(self, keyword, current_user=None, max_results=5, privacy_filter=None):
        self.recall_calls.append(
            {"keyword": keyword, "current_user": current_user, "max_results": max_results}
        )
        return [
            FakeEntry("warm-hit", "warm", 0.8),
            FakeEntry("ghost-hit", "ghost", 0.2),
        ]


class FakePublicAPI:
    """实测：get_emotion_state/get_body_state 是 async，cold session 返 None。"""

    async def get_emotion_state(self, session_key, include_trajectory=False):
        if session_key == "cold":
            return None
        out = {
            "pad_primary": "平静",
            "pad_label": "neutral",          # 已弃用别名，渲染应优先 pad_primary
            "pad_intensity": 0.82,           # 渲染应分桶成「高」，不得出现裸 0.82
            "pad_valence": 0.3,
        }
        if include_trajectory:
            out["emotion_trajectory"] = [{"valence": 0.3, "timestamp": 1.0}]
        return out

    async def get_body_state(self, session_key):
        if session_key == "cold":
            return None
        return {"pad_primary": "平静", "warmth": 0.9, "pulse": 0.2,
                "expression": 0.5, "repair": 0.1}


class FakeEmotionSpiritStar:
    """模拟 EmotionSpiritPlugin(Star) 实例：grounded 属性 _pool / _public_api / _persona_mode。"""

    def __init__(self, *, with_api=True, persona_mode="enabled") -> None:
        self._pool = FakeMemoryPool()
        self._persona_mode = persona_mode
        if with_api:
            self._public_api = FakePublicAPI()


class FakeMeta:
    def __init__(self, star_cls) -> None:
        self.star_cls = star_cls


class FakeContext:
    """模拟 AstrBot context.get_registered_star。star=None 模拟未安装。"""

    def __init__(self, star) -> None:
        self._star = star

    def get_registered_star(self, name: str):
        if name == EMOTION_SPIRIT_STAR_NAME and self._star is not None:
            return FakeMeta(self._star)
        return None


class FakeNativeMemory:
    """模拟 Sylanne 原生 memory_system（fallback 目标）。"""

    def __init__(self) -> None:
        self.writes: list[dict] = []
        self.recall_calls: list[tuple] = []

    def write_summary(self, text, **kwargs) -> None:
        self.writes.append({"text": text, **kwargs})

    def recall(self, query, limit=5):
        self.recall_calls.append((query, limit))
        return []


class FakeSylanne:
    """模拟 Sylanne 插件实例，仅注入桥所需的最小依赖（context + config）。"""

    def __init__(self, star) -> None:
        self.context = FakeContext(star)
        self.config = {"sylanne_alpha_emotion_spirit_bridge_enabled": True}


def _run(coro, timeout=5.0):
    async def _w():
        return await asyncio.wait_for(coro, timeout)

    return asyncio.run(_w())


# ---------------------------------------------------------------------------
# 没装 emotion_spirit → 完全 no-op
# ---------------------------------------------------------------------------
class TestNotInstalledIsNoOp(unittest.TestCase):
    def setUp(self) -> None:
        self.syl = FakeSylanne(star=None)
        self.bridge = EmotionSpiritBridge(self.syl)

    def test_available_false(self):
        self.assertFalse(self.bridge.available())

    def test_activate_is_noop(self):
        res = self.bridge.activate()
        self.assertFalse(res["active"])
        self.assertEqual(res["reason"], "not_installed")
        self.assertFalse(self.bridge.is_active())

    def test_memory_backend_none(self):
        self.assertIsNone(self.bridge.memory_backend(FakeNativeMemory()))

    def test_pull_context_all_none(self):
        ctx = _run(self.bridge.pull_context("s:1:1"))
        self.assertEqual(ctx, {"emotion_state": None, "body_state": None})

    def test_consume_state_block_empty(self):
        self.assertEqual(_run(self.bridge.consume_state_block("s:1:1")), "")

    def test_reassert_false(self):
        self.assertFalse(self.bridge.reassert_persona_disabled())

    def test_deactivate_noop(self):
        self.assertFalse(self.bridge.deactivate()["restored"])

    def test_engine_share_permanent_noop(self):
        res = _run(self.bridge.align_shared_engine())
        self.assertFalse(res["aligned"])
        self.assertEqual(res["reason"], "infeasible_cross_namespace_registry")

    def test_all_public_methods_no_exception(self):
        b = self.bridge
        self.assertFalse(b.available())
        self.assertFalse(b.activate()["active"])
        self.assertIsNone(b.memory_backend())
        self.assertEqual(_run(b.pull_context("x")), {"emotion_state": None, "body_state": None})
        self.assertEqual(_run(b.consume_state_block("x")), "")
        self.assertFalse(b.reassert_persona_disabled())
        self.assertFalse(b.deactivate()["restored"])
        self.assertFalse(b.is_active())
        self.assertFalse(_run(b.align_shared_engine(lambda s, u: ""))["aligned"])


# ---------------------------------------------------------------------------
# 装了 emotion_spirit → 激活 + persona_mode disabled + 自愈重申
# ---------------------------------------------------------------------------
class TestInstalledActivation(unittest.TestCase):
    def test_available_true(self):
        bridge = EmotionSpiritBridge(FakeSylanne(FakeEmotionSpiritStar()))
        self.assertTrue(bridge.available())

    def test_activate_sets_persona_mode_disabled(self):
        star = FakeEmotionSpiritStar(persona_mode="enabled")
        bridge = EmotionSpiritBridge(FakeSylanne(star))
        res = bridge.activate()
        self.assertTrue(res["active"])
        self.assertTrue(bridge.is_active())
        self.assertEqual(star._persona_mode, "disabled")
        self.assertIn("setattr:_persona_mode", res["persona_mode_disabled"]["via"])

    def test_deactivate_restores_persona_mode(self):
        star = FakeEmotionSpiritStar(persona_mode="auto")
        bridge = EmotionSpiritBridge(FakeSylanne(star))
        bridge.activate()
        self.assertEqual(star._persona_mode, "disabled")
        res = bridge.deactivate()
        self.assertTrue(res["restored"])
        self.assertEqual(star._persona_mode, "auto")   # 还原成接管前的值，不留痕
        self.assertFalse(bridge.is_active())

    def test_reassert_self_heals_external_revert(self):
        """用户/配置中途把 persona_mode 改回 'auto' → 每轮 reassert 自愈成 'disabled'。"""
        star = FakeEmotionSpiritStar(persona_mode="enabled")
        bridge = EmotionSpiritBridge(FakeSylanne(star))
        bridge.activate()
        star._persona_mode = "auto"                    # 外部偷偷改回
        self.assertTrue(bridge.reassert_persona_disabled())
        self.assertEqual(star._persona_mode, "disabled")
        # 已是 disabled → 不再无谓写
        self.assertFalse(bridge.reassert_persona_disabled())

    def test_deactivate_deletes_attr_when_absent_before(self):
        star = FakeEmotionSpiritStar()
        delattr(star, "_persona_mode")
        bridge = EmotionSpiritBridge(FakeSylanne(star))
        bridge.activate()
        self.assertEqual(star._persona_mode, "disabled")
        res = bridge.deactivate()
        self.assertTrue(res["restored"])
        self.assertFalse(hasattr(star, "_persona_mode"))

    def test_deactivate_restores_none_when_prev_was_none(self):
        star = FakeEmotionSpiritStar(persona_mode=None)
        bridge = EmotionSpiritBridge(FakeSylanne(star))
        bridge.activate()
        self.assertEqual(star._persona_mode, "disabled")
        res = bridge.deactivate()
        self.assertTrue(res["restored"])
        self.assertIsNone(star._persona_mode)


# ---------------------------------------------------------------------------
# 消费：拉稳定状态 + 渲染观察式背景块（粗粒度、无裸 float）
# ---------------------------------------------------------------------------
class TestConsumeState(unittest.TestCase):
    def setUp(self) -> None:
        self.star = FakeEmotionSpiritStar()
        self.bridge = EmotionSpiritBridge(FakeSylanne(self.star))
        self.bridge.activate()

    def test_pull_context_awaits_async_api(self):
        ctx = _run(self.bridge.pull_context("s:9:9", include_trajectory=True))
        self.assertEqual(ctx["emotion_state"]["pad_primary"], "平静")
        self.assertIn("emotion_trajectory", ctx["emotion_state"])
        self.assertEqual(ctx["body_state"]["warmth"], 0.9)

    def test_pull_context_cold_session_none(self):
        ctx = _run(self.bridge.pull_context("cold"))
        self.assertIsNone(ctx["emotion_state"])
        self.assertIsNone(ctx["body_state"])

    def test_consume_state_block_observational_coarse(self):
        block = _run(self.bridge.consume_state_block("s:9:9"))
        self.assertIn("[emotion_spirit 内在状态]", block)
        self.assertIn("背景参考", block)               # 观察式措辞
        self.assertIn("情绪基调: 平静", block)          # pad_primary 优先
        self.assertNotIn("neutral", block)             # 不用已弃用的 pad_label
        self.assertIn("强度高", block)                  # 0.82 → 高（分桶）
        self.assertIn("暖意高", block)                  # warmth 0.9 → 高
        self.assertIn("联结低", block)                  # pulse 0.2 → 低
        # 关键：不得泄露裸 float（断掉模型复读→EMA 自强化回环）
        self.assertNotIn("0.82", block)
        self.assertNotIn("0.9", block)

    def test_consume_state_block_empty_on_cold(self):
        self.assertEqual(_run(self.bridge.consume_state_block("cold")), "")

    def test_consume_state_block_empty_when_inactive(self):
        b = EmotionSpiritBridge(FakeSylanne(FakeEmotionSpiritStar()))  # 未 activate
        self.assertEqual(_run(b.consume_state_block("s:1:1")), "")


# ---------------------------------------------------------------------------
# 记忆后端（Phase 2 预置）：写读 bug 已修，行为正确
# ---------------------------------------------------------------------------
class TestMemoryBackendPrep(unittest.TestCase):
    def setUp(self) -> None:
        self.star = FakeEmotionSpiritStar()
        self.bridge = EmotionSpiritBridge(FakeSylanne(self.star))
        self.bridge.activate()
        self.native = FakeNativeMemory()
        self.backend = self.bridge.memory_backend(self.native)

    def test_add_routes_with_clamped_weight_and_namespaced_tags(self):
        res = self.backend.add(
            "记得我喜欢猫",
            importance=0.9,           # > cap 0.75 → 应被钳
            confidence=0.7,
            source="user_explicit",
            life_event_id="evt-42",
            source_user="user1",
            tags=["fav"],
        )
        self.assertEqual(res["routed"], "emotion_spirit")
        self.assertEqual(len(self.star._pool.added), 1)
        self.assertEqual(len(self.native.writes), 0)
        rec = self.star._pool.added[0]
        self.assertAlmostEqual(rec["raw_weight"], 0.75)        # 钳在 bypass 阈下
        self.assertEqual(rec["source_user"], "user1")
        self.assertEqual(rec["participants"], {"user1"})        # 收窄 owner，无 <global>
        # tags 全部命名空间化，防与 'betrayal'/'collapse' 促进触发词碰撞
        self.assertIn("syl:fav", rec["tags"])
        self.assertIn("syl:life_event_id:evt-42", rec["tags"])
        self.assertIn("syl:source:user_explicit", rec["tags"])

    def test_add_without_owner_fails_closed_to_native(self):
        """缺 source_user → 绝不写进 es 池（避免无主/全局可见写洞），fail-closed 走原生。"""
        res = self.backend.add("无主记忆", importance=0.5, source_user=None)
        self.assertEqual(res["routed"], "native")
        self.assertEqual(len(self.star._pool.added), 0)
        self.assertEqual(len(self.native.writes), 1)

    def test_recall_requires_current_user_and_maps_tier(self):
        results = self.backend.recall("猫", current_user="user1", k=3)
        self.assertEqual(len(self.star._pool.recall_calls), 1)
        call = self.star._pool.recall_calls[0]
        self.assertEqual(call["current_user"], "user1")
        self.assertEqual(call["max_results"], 3)               # 正确传 max_results 非 k=
        layers = {r["layer"] for r in results}
        self.assertIn("L2", layers)                            # warm → L2
        self.assertIn("L3", layers)                            # ghost → L3
        self.assertEqual(results[0]["text"], "warm-hit")
        self.assertAlmostEqual(results[0]["score"], 0.8)       # 读 .emotional_weight

    def test_recall_without_current_user_does_not_leak(self):
        """current_user=None → 绝不调它的 recall（那会捞全员私货串号），降级原生。"""
        out = self.backend.recall("猫", current_user=None, k=3)
        self.assertEqual(self.star._pool.recall_calls, [])     # 没碰 es 池
        self.assertEqual(self.native.recall_calls, [("猫", 3)])
        self.assertEqual(out, [])

    def test_add_pool_failure_falls_back_to_native(self):
        def _boom(*a, **k):
            raise RuntimeError("pool down")

        self.star._pool.add = _boom  # type: ignore
        res = self.backend.add("x", importance=0.5, source_user="user1")
        self.assertEqual(res["routed"], "native")
        self.assertEqual(len(self.native.writes), 1)

    def test_recall_pool_failure_falls_back_to_native(self):
        def _boom(*a, **k):
            raise RuntimeError("recall down")

        self.star._pool.recall = _boom  # type: ignore
        out = self.backend.recall("猫", current_user="user1", k=2)
        self.assertEqual(self.native.recall_calls, [("猫", 2)])
        self.assertEqual(out, [])


# ---------------------------------------------------------------------------
# 优雅降级 + 引擎共享永久 no-op
# ---------------------------------------------------------------------------
class TestGracefulDegradation(unittest.TestCase):
    def test_missing_api_available_but_consume_empty(self):
        star = FakeEmotionSpiritStar(with_api=False)   # 只有 _pool，缺 _public_api
        bridge = EmotionSpiritBridge(FakeSylanne(star))
        self.assertTrue(bridge.available())
        bridge.activate()
        self.assertEqual(_run(bridge.consume_state_block("s:1:1")), "")

    def test_engine_share_noop_ignores_llm(self):
        star = FakeEmotionSpiritStar()
        bridge = EmotionSpiritBridge(FakeSylanne(star))
        bridge.activate()
        res = _run(bridge.align_shared_engine(lambda s, u: ""))
        self.assertFalse(res["aligned"])
        self.assertEqual(res["reason"], "infeasible_cross_namespace_registry")
        self.assertIn("note", res)


class FakePoolNoParticipants:
    """模拟 add() 缺 participants kwarg 的旧/变体 MemoryPool（探测应降级、不靠 catch TypeError）。"""

    def __init__(self) -> None:
        self.added: list[dict] = []

    def add(self, text, raw_weight=None, phi=None, tags=None, source_user=None):
        self.added.append({"text": text, "raw_weight": raw_weight, "source_user": source_user})


# ---------------------------------------------------------------------------
# 红队复审修复回归：NaN 分桶/钳位、不可哈希 fail-closed、缺 participants 签名探测
# ---------------------------------------------------------------------------
class TestBugFixes(unittest.TestCase):
    def test_bucket_coarse_and_nonfinite_skipped(self):
        self.assertEqual(_bucket(None), "")
        self.assertEqual(_bucket("x"), "")
        self.assertEqual(_bucket(0.2), "低")
        self.assertEqual(_bucket(0.5), "中")
        self.assertEqual(_bucket(0.9), "高")
        # NaN/±inf 跳过（不渲染成假「高」）
        self.assertEqual(_bucket(float("nan")), "")
        self.assertEqual(_bucket(float("inf")), "")
        self.assertEqual(_bucket(float("-inf")), "")

    def test_clamp_nan_maps_to_default_not_upper_bound(self):
        self.assertAlmostEqual(_clamp(0.9, 0.0, 0.75), 0.75)        # 正常钳上界
        self.assertAlmostEqual(_clamp(float("nan"), 0.0, 0.75, default=0.5), 0.5)
        self.assertAlmostEqual(_clamp01(float("nan")), 0.5)        # 不悄悄变 1.0
        self.assertAlmostEqual(_clamp(float("inf"), 0.0, 0.75, default=0.5), 0.5)

    def _backend(self):
        star = FakeEmotionSpiritStar()
        bridge = EmotionSpiritBridge(FakeSylanne(star))
        bridge.activate()
        return star, bridge.memory_backend(FakeNativeMemory())

    def test_add_nan_importance_uses_safe_default_weight(self):
        star, backend = self._backend()
        backend.add("x", importance=float("nan"), source_user="u1")
        self.assertAlmostEqual(star._pool.added[0]["raw_weight"], 0.5)  # 不是上界 0.75

    def test_unhashable_source_user_fails_closed_to_native(self):
        star, backend = self._backend()
        native = backend._native
        res = backend.add("x", importance=0.5, source_user=["unhashable"])
        self.assertEqual(res["routed"], "native")          # fail-closed，不退成全局可见写
        self.assertEqual(len(star._pool.added), 0)
        self.assertEqual(len(native.writes), 1)

    def test_pool_without_participants_param_routes_ok_no_participants(self):
        """add() 缺 participants：靠 inspect.signature 探测降级，不误把内部 TypeError 当签名不符。"""
        star = FakeEmotionSpiritStar()
        star._pool = FakePoolNoParticipants()
        bridge = EmotionSpiritBridge(FakeSylanne(star))
        bridge.activate()
        backend = bridge.memory_backend(FakeNativeMemory())
        res = backend.add("x", importance=0.5, source_user="u1", tags=["fav"])
        self.assertEqual(res["routed"], "emotion_spirit")
        self.assertEqual(res["reason"], "ok_no_participants")
        self.assertEqual(len(star._pool.added), 1)         # 只写一次，无重复
        self.assertEqual(star._pool.added[0]["source_user"], "u1")


if __name__ == "__main__":
    unittest.main()
