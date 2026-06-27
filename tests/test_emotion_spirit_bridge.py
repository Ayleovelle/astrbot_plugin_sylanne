"""Tests for EmotionSpiritBridge —— Sylanne ↔ astrbot_plugin_emotion_spirit 适配桥。

核心验证两条路径（对应任务约束②④）：
  - 装了（探到 emotion_spirit）：桥激活 + persona_mode 被设 "disabled" + 记忆路由到 MemoryPool。
  - 没装：available()/is_active()/memory_backend() 全 no-op，调任何方法零副作用、零异常。

另验证：pull_context 合并、deactivate 还原 persona_mode、引擎共享默认保守关、缺方法优雅降级。
设计约束：不硬 import emotion_spirit，全鸭子类型；未装时对 Sylanne 现有行为零影响。
"""

from __future__ import annotations

import asyncio
import unittest

from sylanne_alpha.emotion_spirit_bridge import (
    EMOTION_SPIRIT_STAR_NAME,
    EmotionSpiritBridge,
)


# ---------------------------------------------------------------------------
# 测试替身：模拟 emotion_spirit 插件（仿 proactive 测试里的 FakeDaPing）
# ---------------------------------------------------------------------------
class FakeMemoryPool:
    """模拟 emotion_spirit MemoryPool：记录 add/recall 调用。"""

    def __init__(self) -> None:
        self.added: list[dict] = []
        self.recall_calls: list[tuple] = []

    def add(self, text, raw_weight=None, phi=None, tags=None, source_user=None) -> None:
        self.added.append(
            {
                "text": text,
                "raw_weight": raw_weight,
                "phi": phi,
                "tags": list(tags or []),
                "source_user": source_user,
            }
        )

    def recall(self, query, k=5):
        self.recall_calls.append((query, k))
        return [
            {"text": "warm-hit", "pool": "warm", "score": 0.8, "source_user": "user1"},
            {"text": "ghost-hit", "pool": "ghost", "score": 0.2, "source_user": "self"},
        ]


class FakePublicAPI:
    def get_emotion_state(self, session_key, include_trajectory=False):
        return {"valence": 0.3, "arousal": 0.6, "session": session_key,
                "trajectory": include_trajectory}

    def get_body_state(self, session_key):
        return {"energy": 0.7, "session": session_key}


class FakePromptInjector:
    def build_context(self, session_key):
        return f"[emotion_spirit context for {session_key}]"


class FakeEmotionSpiritStar:
    """模拟 EmotionSpiritPlugin(Star) 实例：暴露记忆池/公共 API/注入器 + persona_mode 门控。"""

    def __init__(self, *, with_api=True, persona_mode="enabled") -> None:
        self.memory_pool = FakeMemoryPool()
        self._persona_mode = persona_mode
        if with_api:
            self.public_api = FakePublicAPI()
            self.prompt_injector = FakePromptInjector()


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
    """模拟 Sylanne 插件实例，仅注入桥所需的最小依赖（context）。"""

    def __init__(self, star) -> None:
        self.context = FakeContext(star)
        self.config = {"sylanne_alpha_emotion_spirit_bridge_enabled": True}


def _run(coro, timeout=5.0):
    async def _w():
        return await asyncio.wait_for(coro, timeout)

    return asyncio.run(_w())


# ---------------------------------------------------------------------------
# 没装 emotion_spirit → 完全 no-op（任务约束②④的核心证明）
# ---------------------------------------------------------------------------
class TestNotInstalledIsNoOp(unittest.TestCase):
    def setUp(self) -> None:
        self.syl = FakeSylanne(star=None)  # 未安装
        self.bridge = EmotionSpiritBridge(self.syl)

    def test_available_false(self):
        self.assertFalse(self.bridge.available())

    def test_activate_is_noop(self):
        res = self.bridge.activate()
        self.assertFalse(res["active"])
        self.assertEqual(res["reason"], "not_installed")
        self.assertFalse(self.bridge.is_active())

    def test_memory_backend_none(self):
        # 未激活 → None；调用方据此继续走原生 memory_system（现有路径一字不改）
        self.assertIsNone(self.bridge.memory_backend(FakeNativeMemory()))

    def test_pull_context_all_none(self):
        ctx = self.bridge.pull_context("s:1:1")
        self.assertEqual(
            ctx, {"emotion_state": None, "body_state": None, "context": None}
        )

    def test_deactivate_noop(self):
        res = self.bridge.deactivate()
        self.assertFalse(res["restored"])

    def test_engine_share_default_off(self):
        async def _llm(sysp, user):  # pragma: no cover - 不应被调用
            return ""

        res = _run(self.bridge.align_shared_engine(_llm))
        self.assertFalse(res["aligned"])
        self.assertEqual(res["reason"], "disabled_by_default")
        self.assertIn("note", res)

    def test_all_public_methods_no_exception_and_no_side_effect(self):
        """逐一调每个公共方法：无异常、无副作用（star=None 时本就无可改对象）。"""
        b = self.bridge
        self.assertFalse(b.available())
        self.assertFalse(b.activate()["active"])
        self.assertIsNone(b.memory_backend())
        self.assertIsNotNone(b.pull_context("x"))
        self.assertFalse(b.deactivate()["restored"])
        self.assertFalse(b.is_active())

        async def _llm(s, u):  # pragma: no cover
            return ""

        # 即便显式 enabled，star=None 时检测门控直接 not_installed：data_dir 不解析、
        # 绝不 import/建任何引擎（红队 B1 回归防护）。
        res = _run(b.align_shared_engine(_llm, enabled=True))
        self.assertFalse(res["aligned"])
        self.assertEqual(res["reason"], "not_installed")
        self.assertIsNone(res["data_dir"])
        # data_dir 推算在未装时返回 None（不凭空合成路径）
        self.assertIsNone(b._emotion_spirit_data_dir())


# ---------------------------------------------------------------------------
# 装了 emotion_spirit → 激活 + persona_mode disabled + 记忆路由
# ---------------------------------------------------------------------------
class TestInstalledActivation(unittest.TestCase):
    def test_available_true(self):
        star = FakeEmotionSpiritStar()
        bridge = EmotionSpiritBridge(FakeSylanne(star))
        self.assertTrue(bridge.available())

    def test_activate_sets_persona_mode_disabled(self):
        star = FakeEmotionSpiritStar(persona_mode="enabled")
        bridge = EmotionSpiritBridge(FakeSylanne(star))
        res = bridge.activate()
        self.assertTrue(res["active"])
        self.assertTrue(bridge.is_active())
        # 核心：emotion_spirit 的 persona 注入被关掉（== "disabled" 即早返不注入）
        self.assertEqual(star._persona_mode, "disabled")

    def test_deactivate_restores_persona_mode(self):
        star = FakeEmotionSpiritStar(persona_mode="default")
        bridge = EmotionSpiritBridge(FakeSylanne(star))
        bridge.activate()
        self.assertEqual(star._persona_mode, "disabled")
        res = bridge.deactivate()
        self.assertTrue(res["restored"])
        self.assertEqual(star._persona_mode, "default")  # 还原成接管前的值，不留痕
        self.assertFalse(bridge.is_active())

    def test_memory_backend_routes_add_to_pool(self):
        star = FakeEmotionSpiritStar()
        bridge = EmotionSpiritBridge(FakeSylanne(star))
        bridge.activate()
        native = FakeNativeMemory()
        backend = bridge.memory_backend(native)
        self.assertIsNotNone(backend)
        self.assertTrue(backend.routes_to_emotion_spirit)

        res = backend.add(
            "记得我喜欢猫",
            importance=0.9,
            confidence=0.7,
            temperature=0.5,
            source="user_explicit",
            life_event_id="evt-42",
            source_user="user1",
        )
        self.assertEqual(res["routed"], "emotion_spirit")
        # 写进了 emotion_spirit 池，没碰原生
        self.assertEqual(len(star.memory_pool.added), 1)
        self.assertEqual(len(native.writes), 0)
        rec = star.memory_pool.added[0]
        self.assertEqual(rec["text"], "记得我喜欢猫")
        self.assertAlmostEqual(rec["raw_weight"], 0.9)        # importance → raw_weight
        self.assertAlmostEqual(rec["phi"], 0.7)               # confidence → phi
        self.assertEqual(rec["source_user"], "user1")
        # life_event_id / source 映射进 tags（去重键 + 来源保留）
        self.assertIn("life_event_id:evt-42", rec["tags"])
        self.assertIn("source:user_explicit", rec["tags"])

    def test_memory_backend_routes_recall_to_pool(self):
        star = FakeEmotionSpiritStar()
        bridge = EmotionSpiritBridge(FakeSylanne(star))
        bridge.activate()
        backend = bridge.memory_backend(FakeNativeMemory())
        results = backend.recall("猫", k=3)
        self.assertEqual(star.memory_pool.recall_calls, [("猫", 3)])
        # 4 层池 → L1/L2/L3 映射归一
        layers = {r["layer"] for r in results}
        self.assertIn("L2", layers)   # warm → L2
        self.assertIn("L3", layers)   # ghost → L3
        self.assertEqual(results[0]["text"], "warm-hit")

    def test_pull_context_merges_state(self):
        star = FakeEmotionSpiritStar()
        bridge = EmotionSpiritBridge(FakeSylanne(star))
        bridge.activate()
        ctx = bridge.pull_context("s:9:9", include_trajectory=True)
        self.assertEqual(ctx["emotion_state"]["valence"], 0.3)
        self.assertTrue(ctx["emotion_state"]["trajectory"])
        self.assertEqual(ctx["body_state"]["energy"], 0.7)
        self.assertIn("emotion_spirit context", ctx["context"])


# ---------------------------------------------------------------------------
# 优雅降级：emotion_spirit 在场但缺方法 / 抛错 → 不崩、降级
# ---------------------------------------------------------------------------
class TestGracefulDegradation(unittest.TestCase):
    def test_missing_api_still_available_but_context_none(self):
        # star 只有 memory_pool，缺 public_api / prompt_injector
        star = FakeEmotionSpiritStar(with_api=False)
        bridge = EmotionSpiritBridge(FakeSylanne(star))
        self.assertTrue(bridge.available())  # 探到即 available（probe 只 warning）
        bridge.activate()
        ctx = bridge.pull_context("s:1:1")
        self.assertIsNone(ctx["emotion_state"])
        self.assertIsNone(ctx["context"])

    def test_pool_add_failure_falls_back_to_native(self):
        star = FakeEmotionSpiritStar()

        def _boom(*a, **k):
            raise RuntimeError("pool down")

        star.memory_pool.add = _boom  # type: ignore
        bridge = EmotionSpiritBridge(FakeSylanne(star))
        bridge.activate()
        native = FakeNativeMemory()
        backend = bridge.memory_backend(native)
        res = backend.add("x", importance=0.5)
        # 池写失败 → 降级到原生 memory_system
        self.assertEqual(res["routed"], "native")
        self.assertEqual(len(native.writes), 1)

    def test_recall_pool_failure_falls_back_to_native(self):
        star = FakeEmotionSpiritStar()

        def _boom(*a, **k):
            raise RuntimeError("recall down")

        star.memory_pool.recall = _boom  # type: ignore
        bridge = EmotionSpiritBridge(FakeSylanne(star))
        bridge.activate()
        native = FakeNativeMemory()
        backend = bridge.memory_backend(native)
        out = backend.recall("猫", k=2)
        # 池召回失败 → 降级原生 recall（被调用），返回空列表（原生替身无数据）
        self.assertEqual(native.recall_calls, [("猫", 2)])
        self.assertEqual(out, [])

    def test_engine_share_installed_no_llm_no_engine(self):
        """装了但不传 llm：仍不建引擎（no_llm_callable），data_dir 推算不依赖 astrbot 实例属性。"""
        star = FakeEmotionSpiritStar()
        star.data_dir = "/tmp/es/sylanne_sessions"  # type: ignore
        bridge = EmotionSpiritBridge(FakeSylanne(star))
        bridge.activate()
        res = _run(bridge.align_shared_engine(None, enabled=True))
        self.assertFalse(res["aligned"])
        self.assertEqual(res["reason"], "no_llm_callable")

    def test_persona_mode_written_directly_to_grounded_field(self):
        """直接写 grounded 门控字段 _persona_mode（emotion_spirit 的 gate 直读它）。"""
        star = FakeEmotionSpiritStar(persona_mode="enabled")
        bridge = EmotionSpiritBridge(FakeSylanne(star))
        res = bridge.activate()
        self.assertTrue(res["active"])
        self.assertEqual(star._persona_mode, "disabled")
        self.assertIn("setattr:_persona_mode", res["persona_mode_disabled"]["via"])

    def test_deactivate_deletes_attr_when_absent_before(self):
        """接管前没有 persona_mode 字段：deactivate 应删除我们写入的（不留痕，哨兵区分）。"""
        star = FakeEmotionSpiritStar()
        delattr(star, "_persona_mode")  # 模拟接管前根本没有该字段
        self.assertFalse(hasattr(star, "_persona_mode"))
        bridge = EmotionSpiritBridge(FakeSylanne(star))
        bridge.activate()
        self.assertEqual(star._persona_mode, "disabled")  # 接管写入
        res = bridge.deactivate()
        self.assertTrue(res["restored"])
        self.assertFalse(hasattr(star, "_persona_mode"))  # 删回不留痕

    def test_deactivate_restores_none_when_prev_was_none(self):
        """接管前字段值就是 None：哨兵保证 deactivate 还原成 None 而非删除。"""
        star = FakeEmotionSpiritStar(persona_mode=None)
        bridge = EmotionSpiritBridge(FakeSylanne(star))
        bridge.activate()
        self.assertEqual(star._persona_mode, "disabled")
        res = bridge.deactivate()
        self.assertTrue(res["restored"])
        self.assertIsNone(star._persona_mode)  # 还原成 None，不被当作「不存在」删掉


# ---------------------------------------------------------------------------
# 引擎共享对齐：默认关 + 缺 llm + note 永远在
# ---------------------------------------------------------------------------
class TestEngineShareConservative(unittest.TestCase):
    def test_enabled_but_no_llm(self):
        star = FakeEmotionSpiritStar()
        bridge = EmotionSpiritBridge(FakeSylanne(star))
        bridge.activate()
        res = _run(bridge.align_shared_engine(None, enabled=True))
        self.assertFalse(res["aligned"])
        self.assertEqual(res["reason"], "no_llm_callable")
        self.assertIn("note", res)

    def test_note_always_warns_about_local_verification(self):
        star = FakeEmotionSpiritStar()
        bridge = EmotionSpiritBridge(FakeSylanne(star))

        async def _llm(s, u):  # pragma: no cover
            return ""

        res = _run(bridge.align_shared_engine(_llm, enabled=False))
        self.assertFalse(res["aligned"])
        self.assertIn("核实", res["note"])


if __name__ == "__main__":
    unittest.main()
