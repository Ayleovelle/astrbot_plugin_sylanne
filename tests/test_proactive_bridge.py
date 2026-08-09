"""Tests for ProactiveBridge —— Sylanne→大饼 主动发言桥接。

验证深度适配主动发言的桥接逻辑：
  - dispatch 注入素材到大饼 proactive_prompt → 触发 check_and_chat → 用完恢复/清理
  - session_key 剥后缀对齐大饼 unified_msg_origin
  - 大饼未安装/接口缺失时静默降级
  - infer_reason_code 多源触发优先级（仪式 > 计算栈 void/scar > 默认）
  - build_motivation_text 带人设语气 + 缘由 + 事件 + 生活上下文

设计约束：不改大饼源码、不污染全局（只写单会话 override，用完即清）。
"""

from __future__ import annotations

import asyncio
import time
import unittest

from sylanne_alpha.memory_system import MemorySystem
from sylanne_alpha.proactive_bridge import ProactiveBridge


# ---------------------------------------------------------------------------
# 测试替身：模拟大饼插件的会话级 override 接口与 check_and_chat
# ---------------------------------------------------------------------------
class FakeOverrideManager:
    """模拟大饼 session_override_manager：记录调用序，存单会话 override。"""

    def __init__(self) -> None:
        self.store: dict[str, dict] = {}
        self.calls: list[tuple] = []

    def get_override(self, sid: str) -> dict:
        self.calls.append(("get", sid))
        return dict(self.store.get(sid, {}))

    async def set_override(self, sid: str, patch: dict) -> None:
        self.calls.append(("set", sid, dict(patch)))
        self.store[sid] = dict(patch)

    async def delete_override(self, sid: str) -> None:
        self.calls.append(("del", sid))
        self.store.pop(sid, None)


class FakeProactivePlugin:
    """模拟大饼插件实例：check_and_chat 读当前 override 的 proactive_prompt。"""

    def __init__(self, schedule_settings=None) -> None:
        self.session_override_manager = FakeOverrideManager()
        self.received: str | None = None
        self.timezone = None
        self._schedule_settings = schedule_settings or {}
        # 记录 _schedule_next_chat_and_save 被调用时生效的 interval（验证 min=max=target 注入）
        self.scheduled_interval: tuple | None = None
        self.seg_enable_at_check = None

    def _get_session_config(self, sid: str) -> dict:
        # 合并 base + 当前 override（模拟大饼 get_effective）
        base = {"schedule_settings": dict(self._schedule_settings)}
        ov = self.session_override_manager.store.get(sid, {})
        ov_sched = ov.get("schedule_settings", {}) if isinstance(ov, dict) else {}
        merged = {**base["schedule_settings"], **ov_sched}
        return {"schedule_settings": merged}

    async def check_and_chat(self, sid: str) -> None:
        self.session_override_manager.calls.append(("check", sid))
        self.received = self.session_override_manager.store.get(sid, {}).get(
            "proactive_prompt"
        )
        # 捕获 check 时生效的分段开关（验证接管时已被关掉）
        ov = self.session_override_manager.store.get(sid, {})
        seg = ov.get("segmented_reply_settings", {}) if isinstance(ov, dict) else {}
        self.seg_enable_at_check = seg.get("enable") if isinstance(seg, dict) else None

    async def _schedule_next_chat_and_save(self, sid: str) -> None:
        # 读取调用时生效的 interval（此刻 override 应已被 adjust 写入）
        sched = self._get_session_config(sid)["schedule_settings"]
        self.scheduled_interval = (
            sched.get("min_interval_minutes"),
            sched.get("max_interval_minutes"),
        )


class FakeMeta:
    def __init__(self, star_cls) -> None:
        self.star_cls = star_cls


class FakeContext:
    def __init__(self, star_cls) -> None:
        self._star = star_cls

    def get_registered_star(self, name: str):
        if name == "astrbot_plugin_proactive_chat":
            return FakeMeta(self._star)
        return None


class FakeScheduler:
    def __init__(self, ritual=None) -> None:
        self._ritual = ritual

    def check_ritual_absence(self, sid: str):
        return self._ritual


class FakeSimulator:
    def recent_context_for_prompt(self, limit: int = 2) -> str:
        return "（Sylanne 最近的生活：在看一本旧书）"


class _FakeStore:
    """最小 _store 替身：仅提供 session_origins 映射（session_key→UMO）。"""

    def __init__(self, origins=None):
        self.session_origins = dict(origins or {})


class FakeSylanne:
    """模拟 Sylanne 插件实例，注入桥接所需的最小依赖。"""

    def __init__(
        self, context, *, ritual=None, reason_code=None, origins=None,
        body=None, guard_allowed=True, memory_system=None,
    ) -> None:
        self.context = context
        # 真实路径：映射存在 _store.session_origins（收消息时 pipeline 写入）
        self._store = _FakeStore(origins)
        self.config = {"sylanne_persona_name": "知花"}
        self._proactive_scheduler = FakeScheduler(ritual)
        self._life_simulator = FakeSimulator()
        self._reason_code = reason_code
        self._body = body
        self._guard_allowed = guard_allowed
        self.proactive_calls = 0
        # T2-05②：可选注入的 memory_system，供 infer_reason_code/build_motivation_text
        # 查待跟进线索（不传则 _memory_system_for_session 不存在，行为与改动前一致）。
        self._memory_system = memory_system

    def _memory_system_for_session(self, session_key: str):
        return self._memory_system

    async def proactive_sylanne(self, *, session_key: str, now: float = 0.0) -> dict:
        self.proactive_calls += 1
        out: dict = {"decision": {}}
        if self._reason_code:
            out["decision"] = {"reason_code": self._reason_code}
        if self._body is not None:
            out["body"] = self._body
        out["guard"] = {"allowed": self._guard_allowed}
        return out


class TestDispatch(unittest.TestCase):
    def test_dispatch_injects_material_and_cleans_up(self):
        """无原 override：注入素材→触发→读到素材→用完删除清理。"""
        plugin = FakeProactivePlugin()
        syl = FakeSylanne(
            FakeContext(plugin),
            origins={"aiocqhttp:GroupMessage:123::agent:u1": "aiocqhttp:GroupMessage:123"},
        )
        bridge = ProactiveBridge(syl)
        self.assertTrue(bridge.available())

        res = asyncio.run(bridge.dispatch("aiocqhttp:GroupMessage:123::agent:u1", "素材A"))
        self.assertTrue(res["dispatched"])
        self.assertEqual(plugin.received, "素材A")
        # 调用序（issue#43 Wave2 三段式）：get(基线) → set(注入) → check → get(RMW还原读) → del
        kinds = [c[0] for c in plugin.session_override_manager.calls]
        self.assertEqual(kinds, ["get", "set", "check", "get", "del"])
        # session_id 已剥后缀
        for c in plugin.session_override_manager.calls:
            if len(c) > 1:
                self.assertEqual(c[1], "aiocqhttp:GroupMessage:123")
        # 用完清空，不留痕
        self.assertEqual(plugin.session_override_manager.store, {})

    def test_dispatch_restores_existing_override(self):
        """有原 override：触发时用临时素材，事后恢复原值而非删除。"""
        plugin = FakeProactivePlugin()
        plugin.session_override_manager.store["s:1:1"] = {
            "enable": True,
            "proactive_prompt": "原始动机",
        }
        syl = FakeSylanne(FakeContext(plugin))
        bridge = ProactiveBridge(syl)

        res = asyncio.run(bridge.dispatch("s:1:1", "临时素材"))
        self.assertTrue(res["dispatched"])
        self.assertEqual(plugin.received, "临时素材")
        self.assertEqual(
            plugin.session_override_manager.store["s:1:1"],
            {"enable": True, "proactive_prompt": "原始动机"},
        )

    def test_resolve_origin_strips_suffix_without_mapping(self):
        """无 _session_origins 映射时，回退剥掉 ::agent:/::speaker: 后缀。"""
        plugin = FakeProactivePlugin()
        syl = FakeSylanne(FakeContext(plugin))
        bridge = ProactiveBridge(syl)
        asyncio.run(bridge.dispatch("plat:Group:42::speaker:u9", "x"))
        self.assertEqual(plugin.received, "x")
        sids = {c[1] for c in plugin.session_override_manager.calls if len(c) > 1}
        self.assertEqual(sids, {"plat:Group:42"})

    def test_resolve_origin_uses_store_mapping(self):
        """有 _store.session_origins 映射时优先用映射的 UMO（不止是剥后缀）。

        回归：映射曾被错读成 p._session_origins（不存在）而恒走剥后缀回退。
        此处映射的 UMO 与"剥后缀"结果不同，确保走的是映射而非回退。
        """
        plugin = FakeProactivePlugin()
        syl = FakeSylanne(
            FakeContext(plugin),
            origins={"sk_internal::agent:u1": "aiocqhttp:GroupMessage:777"},
        )
        bridge = ProactiveBridge(syl)
        asyncio.run(bridge.dispatch("sk_internal::agent:u1", "x"))
        sids = {c[1] for c in plugin.session_override_manager.calls if len(c) > 1}
        # 映射命中 → 用真实 UMO；若错走回退则会是 "sk_internal"
        self.assertEqual(sids, {"aiocqhttp:GroupMessage:777"})


class TestGracefulDegrade(unittest.TestCase):
    def test_not_installed(self):
        """大饼未安装：available False，dispatch 静默降级。"""

        class EmptyContext:
            def get_registered_star(self, name):
                return None

        syl = FakeSylanne(EmptyContext())
        bridge = ProactiveBridge(syl)
        self.assertFalse(bridge.available())
        res = asyncio.run(bridge.dispatch("x::agent:y", "hi"))
        self.assertFalse(res["dispatched"])
        self.assertIn("not_installed", res["reason"])

    def test_api_missing(self):
        """大饼存在但缺关键接口：降级，不抛异常。"""

        class HalfPlugin:
            pass

        syl = FakeSylanne(FakeContext(HalfPlugin()))
        bridge = ProactiveBridge(syl)
        self.assertFalse(bridge.available())
        res = asyncio.run(bridge.dispatch("s:1:1", "hi"))
        self.assertFalse(res["dispatched"])


class TestInferReasonCode(unittest.TestCase):
    def test_ritual_takes_priority(self):
        """仪式缺席优先于计算栈缘由。"""
        syl = FakeSylanne(FakeContext(FakeProactivePlugin()), ritual="晚安", reason_code="void")
        rc = asyncio.run(ProactiveBridge(syl).infer_reason_code("s:1:1"))
        self.assertEqual(rc, "ritual")

    def test_computation_stack_reason(self):
        """无仪式时取计算栈 reason_code（void/scar）。"""
        syl = FakeSylanne(FakeContext(FakeProactivePlugin()), ritual=None, reason_code="scar")
        rc = asyncio.run(ProactiveBridge(syl).infer_reason_code("s:1:1"))
        self.assertEqual(rc, "scar")

    def test_default_life_rhythm(self):
        """仪式与计算栈都无 → 回退 life_rhythm。"""
        syl = FakeSylanne(FakeContext(FakeProactivePlugin()), ritual=None, reason_code=None)
        rc = asyncio.run(ProactiveBridge(syl).infer_reason_code("s:1:1"))
        self.assertEqual(rc, "life_rhythm")

    def test_surface_reuse_skips_internal_call(self):
        """传入预计算 surface → 不再内部调 proactive_sylanne（消除双调用）。"""
        syl = FakeSylanne(FakeContext(FakeProactivePlugin()), ritual=None, reason_code="void")
        bridge = ProactiveBridge(syl)
        surface = {"decision": {"reason_code": "scar"}}
        rc = asyncio.run(bridge.infer_reason_code("s:1:1", surface=surface))
        self.assertEqual(rc, "scar")  # 用的是传入 surface 的 reason_code
        self.assertEqual(syl.proactive_calls, 0)  # 没有内部调用

    def test_no_surface_still_calls_internally(self):
        """不传 surface → 维持原行为，内部调一次 proactive_sylanne。"""
        syl = FakeSylanne(FakeContext(FakeProactivePlugin()), ritual=None, reason_code="void")
        bridge = ProactiveBridge(syl)
        rc = asyncio.run(bridge.infer_reason_code("s:1:1"))
        self.assertEqual(rc, "void")
        self.assertEqual(syl.proactive_calls, 1)

    def test_ritual_priority_over_surface(self):
        """仪式命中时优先返回 ritual，即使传了 surface 也不被覆盖。"""
        syl = FakeSylanne(FakeContext(FakeProactivePlugin()), ritual="晚安", reason_code="void")
        bridge = ProactiveBridge(syl)
        surface = {"decision": {"reason_code": "scar"}}
        rc = asyncio.run(bridge.infer_reason_code("s:1:1", surface=surface))
        self.assertEqual(rc, "ritual")

    # -- T2-05②：跟进线索到期 reason_code --------------------------------

    def test_user_followup_beats_computation_stack(self):
        """跟进线索到期时，优先于计算栈缘由（void/scar）返回 user_followup。"""
        mem = MemorySystem()
        mem.write_summary("我答应你明天一定去面试", source_turns=2, temperature=0.5)
        # 强制到期（写入时的模糊估计通常在未来，这里直接改到过去以模拟"已到期"）。
        mem._pending_followups[0]["due_ts_estimate"] = time.time() - 10.0
        syl = FakeSylanne(
            FakeContext(FakeProactivePlugin()), ritual=None, reason_code="void",
            memory_system=mem,
        )
        rc = asyncio.run(ProactiveBridge(syl).infer_reason_code("s:1:1"))
        self.assertEqual(rc, "user_followup")

    def test_ritual_priority_over_user_followup(self):
        """仪式缺席仍然优先于跟进线索（既有优先级不因新增检查而改变）。"""
        mem = MemorySystem()
        mem.write_summary("我答应你明天一定去面试", source_turns=2, temperature=0.5)
        mem._pending_followups[0]["due_ts_estimate"] = time.time() - 10.0
        syl = FakeSylanne(
            FakeContext(FakeProactivePlugin()), ritual="晚安", reason_code="void",
            memory_system=mem,
        )
        rc = asyncio.run(ProactiveBridge(syl).infer_reason_code("s:1:1"))
        self.assertEqual(rc, "ritual")

    def test_no_due_followup_falls_through_to_computation_stack(self):
        """跟进线索存在但未到期 → 不应命中 user_followup，继续走计算栈缘由。"""
        mem = MemorySystem()
        mem.write_summary("我答应你明天一定去面试", source_turns=2, temperature=0.5)
        # 保留写入时估计的未来到期时间（未过期）
        syl = FakeSylanne(
            FakeContext(FakeProactivePlugin()), ritual=None, reason_code="scar",
            memory_system=mem,
        )
        rc = asyncio.run(ProactiveBridge(syl).infer_reason_code("s:1:1"))
        self.assertEqual(rc, "scar")


class TestBuildMotivationText(unittest.TestCase):
    def test_contains_persona_reason_event_context(self):
        """素材应含：人设名 + 缘由语 + 事件 + 生活上下文 + 含蓄语气提示。"""
        syl = FakeSylanne(FakeContext(FakeProactivePlugin()))
        bridge = ProactiveBridge(syl)
        text = bridge.build_motivation_text(
            "[life_event] 路过花店闻到栀子花",
            "温柔",
            reason_code="scar",
            session_key="s:1:1",
        )
        self.assertIn("知花", text)
        self.assertIn("没说完的事", text)
        self.assertIn("栀子花", text)
        self.assertNotIn("[life_event]", text)
        self.assertIn("旧书", text)
        self.assertIn("含蓄", text)

    def test_unknown_reason_code_omits_phrase(self):
        """未知 reason_code 不塞缘由语，但其余部分仍在。"""
        syl = FakeSylanne(FakeContext(FakeProactivePlugin()))
        text = ProactiveBridge(syl).build_motivation_text(
            "随便走走", "平静", reason_code="unknown_xyz", session_key="s:1:1"
        )
        self.assertIn("知花", text)
        self.assertIn("随便走走", text)

    def test_user_followup_includes_topic(self):
        """T2-05②：user_followup 缘由应带上到期线索的话题片段。"""
        mem = MemorySystem()
        mem.write_summary("我答应你明天一定去面试", source_turns=2, temperature=0.5)
        mem._pending_followups[0]["due_ts_estimate"] = time.time() - 10.0
        syl = FakeSylanne(FakeContext(FakeProactivePlugin()), memory_system=mem)
        text = ProactiveBridge(syl).build_motivation_text(
            "随便走走", "平静", reason_code="user_followup", session_key="s:1:1",
        )
        self.assertIn("面试", text)
        self.assertIn("想问问后来怎么样了", text)

    def test_user_followup_without_topic_uses_generic_phrase(self):
        """无法取到 topic（无 memory_system）时退化为通用措辞，不报错。"""
        syl = FakeSylanne(FakeContext(FakeProactivePlugin()))
        text = ProactiveBridge(syl).build_motivation_text(
            "随便走走", "平静", reason_code="user_followup", session_key="s:1:1",
        )
        self.assertIn("想问问后来怎么样了", text)


class _HasGuardStore:
    """MINOR(b) 专用替身：提供 .memory_systems.has()，可控制返回 True/False，
    并记录 _memory_system_for_session 是否真的被调用过（懒创建探针）。"""

    def __init__(self, has_result: bool) -> None:
        self._has_result = has_result
        self.has_calls: list[str] = []

        class _Map:
            def __init__(self, outer: "_HasGuardStore") -> None:
                self._outer = outer

            def has(self, session_key: str) -> bool:
                self._outer.has_calls.append(session_key)
                return self._outer._has_result

        self.memory_systems = _Map(self)


class TestInferReasonCodeMemorySystemGuard(unittest.TestCase):
    """MINOR(b)：infer_reason_code 的跟进线索检查经 .has() 守卫，不该为没有
    memory_system 的会话触发 _memory_system_for_session 的懒创建。"""

    def test_has_false_skips_getter_no_phantom_session(self):
        """store 报告该会话【没有】memory_system → 直接跳过，getter 压根不被调用。"""
        store = _HasGuardStore(has_result=False)
        getter_calls: list[str] = []

        def _mem_getter(sk: str):
            getter_calls.append(sk)
            raise AssertionError("不该为 has()=False 的会话调用懒创建 getter")

        syl = FakeSylanne(FakeContext(FakeProactivePlugin()), ritual=None, reason_code="scar")
        syl._store = store
        syl._memory_system_for_session = _mem_getter
        rc = asyncio.run(ProactiveBridge(syl).infer_reason_code("brand_new"))
        # 跳过 user_followup 检查，落回计算栈缘由
        self.assertEqual(rc, "scar")
        self.assertEqual(getter_calls, [])
        self.assertIn("brand_new", store.has_calls)

    def test_has_true_still_checks_due_followup(self):
        """store 报告该会话【已有】memory_system → 正常经 getter 查到期线索。"""
        mem = MemorySystem()
        mem.write_summary("我答应你明天一定去面试", source_turns=2, temperature=0.5)
        mem._pending_followups[0]["due_ts_estimate"] = time.time() - 10.0

        store = _HasGuardStore(has_result=True)
        syl = FakeSylanne(
            FakeContext(FakeProactivePlugin()), ritual=None, reason_code="void",
            memory_system=mem,
        )
        syl._store = store
        rc = asyncio.run(ProactiveBridge(syl).infer_reason_code("s:1:1"))
        self.assertEqual(rc, "user_followup")
        self.assertIn("s:1:1", store.has_calls)

    def test_no_guard_capability_falls_back_to_direct_getter_call(self):
        """测试替身若不提供 _store.memory_systems（没有守卫能力，如既有 FakeSylanne
        默认的 _FakeStore）→ 退化为直接调用 getter，行为与改动前一致（不因新增
        守卫而破坏没有该能力的调用方）。"""
        mem = MemorySystem()
        mem.write_summary("我答应你明天一定去面试", source_turns=2, temperature=0.5)
        mem._pending_followups[0]["due_ts_estimate"] = time.time() - 10.0
        syl = FakeSylanne(
            FakeContext(FakeProactivePlugin()), ritual=None, reason_code="void",
            memory_system=mem,
        )
        rc = asyncio.run(ProactiveBridge(syl).infer_reason_code("s:1:1"))
        self.assertEqual(rc, "user_followup")


class TestConsumeFollowupOnDispatch(unittest.TestCase):
    """MAJOR-1：user_followup 标签的消息真正发出后，消费掉产生该标签的那条
    待跟进线索（bridge.consume_followup_on_dispatch，供两条 dispatch 路径调用）。
    """

    def test_consumes_due_entry_when_reason_code_is_user_followup(self):
        mem = MemorySystem()
        mem.write_summary("我答应你明天一定去面试", source_turns=2, temperature=0.5)
        mem._pending_followups[0]["due_ts_estimate"] = time.time() - 10.0
        syl = FakeSylanne(FakeContext(FakeProactivePlugin()), memory_system=mem)
        bridge = ProactiveBridge(syl)

        bridge.consume_followup_on_dispatch("s:1:1", "user_followup")

        self.assertEqual(mem._pending_followups, [])

    def test_noop_when_reason_code_is_not_user_followup(self):
        """标签不是 user_followup 时是 no-op——不该误删跟这次发言无关的线索。"""
        mem = MemorySystem()
        mem.write_summary("我答应你明天一定去面试", source_turns=2, temperature=0.5)
        mem._pending_followups[0]["due_ts_estimate"] = time.time() - 10.0
        syl = FakeSylanne(FakeContext(FakeProactivePlugin()), memory_system=mem)
        bridge = ProactiveBridge(syl)

        bridge.consume_followup_on_dispatch("s:1:1", "void")

        self.assertEqual(len(mem._pending_followups), 1)

    def test_noop_when_no_memory_system(self):
        """没有 memory_system 时静默 no-op，不报错。"""
        syl = FakeSylanne(FakeContext(FakeProactivePlugin()))
        bridge = ProactiveBridge(syl)
        bridge.consume_followup_on_dispatch("s:1:1", "user_followup")  # 不应抛异常

    def test_noop_when_no_due_entry(self):
        """有 memory_system 但没有到期线索时是 no-op（防误删未到期的线索）。"""
        mem = MemorySystem()
        mem.write_summary("我答应你明天一定去面试", source_turns=2, temperature=0.5)
        # 保留写入时估计的未来到期时间（未过期）
        syl = FakeSylanne(FakeContext(FakeProactivePlugin()), memory_system=mem)
        bridge = ProactiveBridge(syl)

        bridge.consume_followup_on_dispatch("s:1:1", "user_followup")

        self.assertEqual(len(mem._pending_followups), 1)


class TestEndToEnd(unittest.TestCase):
    def test_full_chain_ritual_to_dispatch(self):
        """端到端：仪式缺席→推断缘由→构造素材→dispatch→大饼读到含缘由素材→清理。"""
        plugin = FakeProactivePlugin()
        syl = FakeSylanne(FakeContext(plugin), ritual="晚安")
        bridge = ProactiveBridge(syl)

        async def run():
            rc = await bridge.infer_reason_code("aiocqhttp:Group:9")
            text = bridge.build_motivation_text(
                "[life_event] 今天降温了", "有点想念", reason_code=rc,
                session_key="aiocqhttp:Group:9",
            )
            return await bridge.dispatch("aiocqhttp:Group:9", text)

        res = asyncio.run(run())
        self.assertTrue(res["dispatched"])
        self.assertIn("降温", plugin.received)
        self.assertIn("没出现", plugin.received)
        self.assertEqual(plugin.session_override_manager.store, {})


class TestTimeGate(unittest.TestCase):
    """时间闸门：复用大饼 quiet_hours + min_interval 公式。"""

    def test_quiet_hours_blocks(self):
        """当前小时落在 quiet_hours 区间 → 闸门压住。"""
        import datetime

        hour = datetime.datetime.now().hour
        # 构造一个必然覆盖当前小时的免打扰区间（0-23）
        plugin = FakeProactivePlugin(schedule_settings={"quiet_hours": "0-23"})
        # 0-23 表示 0<=h<23；若当前正好 23 点，用 23-0 跨天覆盖
        if hour == 23:
            plugin = FakeProactivePlugin(schedule_settings={"quiet_hours": "23-0"})
        syl = FakeSylanne(FakeContext(plugin))
        bridge = ProactiveBridge(syl)
        allowed, reason = bridge.should_dispatch_now("s:1:1")
        self.assertFalse(allowed)
        self.assertEqual(reason, "quiet_hours")

    def test_allows_when_not_quiet_and_first_time(self):
        """非免打扰且首次触发 → 放行。"""
        # 构造一个必然不覆盖当前小时的窄区间
        import datetime

        hour = datetime.datetime.now().hour
        # quiet 设成"下一个小时的单点"，当前小时一定不在内
        nxt = (hour + 2) % 24
        plugin = FakeProactivePlugin(
            schedule_settings={"quiet_hours": f"{nxt}-{(nxt + 1) % 24}", "min_interval_minutes": 30}
        )
        syl = FakeSylanne(FakeContext(plugin))
        bridge = ProactiveBridge(syl)
        allowed, reason = bridge.should_dispatch_now("s:1:1")
        self.assertTrue(allowed, f"应放行，实际 reason={reason}")
        self.assertEqual(reason, "ok")

    def test_min_interval_throttle(self):
        """距上次桥接触发不足 min_interval → 节流压住。"""
        import datetime
        import time as _t

        hour = datetime.datetime.now().hour
        nxt = (hour + 2) % 24
        plugin = FakeProactivePlugin(
            schedule_settings={"quiet_hours": f"{nxt}-{(nxt + 1) % 24}", "min_interval_minutes": 30}
        )
        syl = FakeSylanne(FakeContext(plugin))
        bridge = ProactiveBridge(syl)
        sid = bridge._resolve_origin("s:1:1")
        # 模拟刚刚触发过
        bridge._last_bridge_dispatch[sid] = _t.time()
        allowed, reason = bridge.should_dispatch_now("s:1:1")
        self.assertFalse(allowed)
        self.assertEqual(reason, "min_interval_throttle")

    def test_dispatch_records_timestamp(self):
        """dispatch 成功后记录触发时间，供后续节流。"""
        plugin = FakeProactivePlugin()
        syl = FakeSylanne(FakeContext(plugin))
        bridge = ProactiveBridge(syl)
        asyncio.run(bridge.dispatch("s:1:1", "素材"))
        self.assertIn("s:1:1", bridge._last_bridge_dispatch)
        self.assertGreater(bridge._last_bridge_dispatch["s:1:1"], 0)


class TestAdjustCountdown(unittest.TestCase):
    """拨动大饼倒计时：Sylanne 内在节律 → 大饼下一次主动发言时机。"""

    def _make(self, body, guard_allowed=True, sched=None):
        plugin = FakeProactivePlugin(
            schedule_settings=sched or {"min_interval_minutes": 30, "max_interval_minutes": 900}
        )
        syl = FakeSylanne(FakeContext(plugin), body=body, guard_allowed=guard_allowed)
        return plugin, ProactiveBridge(syl)

    def test_high_urge_shortens_countdown(self):
        """想表达强烈(need_expression 高) → 倒计时拉到接近 min。"""
        plugin, bridge = self._make(
            {"needs": {"need_expression": 1.0, "need_repair": 0.0, "need_quiet": 0.0},
             "immunity": {"boundary_pressure": 0.0}}
        )
        res = asyncio.run(bridge.adjust_countdown("s:1:1"))
        self.assertTrue(res["adjusted"])
        self.assertEqual(res["target_minutes"], 30)  # net=1 → lo_min
        # 重排时生效的 interval 应是 min=max=30
        self.assertEqual(plugin.scheduled_interval, (30, 30))

    def test_high_quiet_lengthens_countdown(self):
        """想安静(need_quiet 高) → 倒计时拉到接近 max。"""
        plugin, bridge = self._make(
            {"needs": {"need_expression": 0.0, "need_repair": 0.0, "need_quiet": 1.0},
             "immunity": {"boundary_pressure": 0.0}}
        )
        res = asyncio.run(bridge.adjust_countdown("s:1:1"))
        self.assertTrue(res["adjusted"])
        self.assertEqual(res["target_minutes"], 900)  # net=0 → hi_min
        self.assertEqual(plugin.scheduled_interval, (900, 900))

    def test_guard_blocked_skips(self):
        """guard 不允许 → 不拨，尊重安全阀。"""
        plugin, bridge = self._make(
            {"needs": {"need_expression": 1.0}}, guard_allowed=False
        )
        res = asyncio.run(bridge.adjust_countdown("s:1:1"))
        self.assertFalse(res["adjusted"])
        self.assertEqual(res["reason"], "guard_blocked")
        self.assertIsNone(plugin.scheduled_interval)  # 未重排

    def test_override_restored_after_adjust(self):
        """拨完恢复原 schedule_settings override，不留痕。"""
        plugin, bridge = self._make(
            {"needs": {"need_expression": 0.8}, "immunity": {}}
        )
        plugin.session_override_manager.store["s:1:1"] = {"enable": True}
        asyncio.run(bridge.adjust_countdown("s:1:1"))
        # 拨完应恢复成原来的 {"enable": True}，不残留临时 schedule_settings
        self.assertEqual(
            plugin.session_override_manager.store.get("s:1:1"), {"enable": True}
        )

    def test_unavailable_plugin_no_crash(self):
        """大饼不可用 → 静默返回，不抛。"""

        class EmptyContext:
            def get_registered_star(self, name):
                return None

        syl = FakeSylanne(EmptyContext(), body={"needs": {"need_expression": 1.0}})
        bridge = ProactiveBridge(syl)
        res = asyncio.run(bridge.adjust_countdown("s:1:1"))
        self.assertFalse(res["adjusted"])


class TestSegmentTakeover(unittest.TestCase):
    """分段接管标记机制：dispatch 登记 → 钩子认领（一次性消费）。"""

    def test_dispatch_marks_takeover_when_enabled(self):
        """开关开启时，dispatch 关掉大饼分段并登记接管标记（钩子未触发时 finally 兜底清除）。"""
        plugin = FakeProactivePlugin()
        syl = FakeSylanne(FakeContext(plugin))
        syl.config["sylanne_alpha_proactive_segment_takeover"] = True
        bridge = ProactiveBridge(syl)
        asyncio.run(bridge.dispatch("s:1:1", "素材"))
        # check_and_chat 时生效的 override 应已把大饼分段关掉
        self.assertEqual(plugin.seg_enable_at_check, False)
        # 钩子未触发（无 AstrBot 管线），finally 兜底清除标记，集合为空
        self.assertEqual(bridge._pending_segment_takeover, set())

    def test_claim_consumes_marker_once(self):
        """claim 一次性消费：首次 True，再次 False。"""
        syl = FakeSylanne(FakeContext(FakeProactivePlugin()))
        bridge = ProactiveBridge(syl)
        bridge._pending_segment_takeover.add("plat:Group:1")
        self.assertTrue(bridge.claim_segment_takeover("plat:Group:1"))
        self.assertFalse(bridge.claim_segment_takeover("plat:Group:1"))

    def test_claim_unmarked_origin_false(self):
        """未登记的 origin → claim 返回 False（不误伤正常消息）。"""
        syl = FakeSylanne(FakeContext(FakeProactivePlugin()))
        bridge = ProactiveBridge(syl)
        self.assertFalse(bridge.claim_segment_takeover("plat:Group:other"))

    def test_takeover_disabled_no_marker(self):
        """开关关闭时 dispatch 不登记接管标记。"""
        plugin = FakeProactivePlugin()
        syl = FakeSylanne(FakeContext(plugin))
        # 默认未设置 sylanne_alpha_proactive_segment_takeover
        bridge = ProactiveBridge(syl)
        self.assertFalse(bridge._segment_takeover_enabled())


class TestHesitation(unittest.TestCase):
    """犹豫：人类粗糙的迟疑感，由计算栈状态为主 + warmth 调制。"""

    def test_high_boundary_pressure_high_hesitation(self):
        """怕打扰(boundary_pressure 高) → 犹豫强。"""
        h = ProactiveBridge.compute_hesitation(
            {"immunity": {"boundary_pressure": 1.0}, "needs": {}, "temperature": {"warmth": 0.0}}
        )
        self.assertGreater(h, 0.8)

    def test_high_expression_low_hesitation(self):
        """想表达(need_expression 高) → 犹豫弱。"""
        h = ProactiveBridge.compute_hesitation(
            {"immunity": {"boundary_pressure": 0.3}, "needs": {"need_expression": 1.0},
             "temperature": {"warmth": 0.5}}
        )
        self.assertEqual(h, 0.0)

    def test_warmth_reduces_hesitation(self):
        """熟悉(warmth 高) → 犹豫被压低。"""
        cold = ProactiveBridge.compute_hesitation(
            {"needs": {"need_quiet": 0.8}, "temperature": {"warmth": 0.0}}
        )
        warm = ProactiveBridge.compute_hesitation(
            {"needs": {"need_quiet": 0.8}, "temperature": {"warmth": 1.0}}
        )
        self.assertLess(warm, cold)

    def test_plan_no_hesitation_when_calm(self):
        """低犹豫(想表达强) → 不停顿、不收回、无踌躇词。"""
        syl = FakeSylanne(FakeContext(FakeProactivePlugin()))
        bridge = ProactiveBridge(syl)
        plan = bridge.hesitation_plan(
            {"needs": {"need_expression": 1.0}, "temperature": {"warmth": 1.0}}
        )
        self.assertEqual(plan["hesitation"], 0.0)
        self.assertEqual(plan["pre_delay_seconds"], 0.0)
        self.assertFalse(plan["withdraw"])
        self.assertEqual(plan["filler"], "")

    def test_plan_high_hesitation_delays(self):
        """高犹豫 → 有发前停顿（固定随机种子保证确定）。"""
        import random as _r

        syl = FakeSylanne(FakeContext(FakeProactivePlugin()))
        bridge = ProactiveBridge(syl)
        _r.seed(12345)
        plan = bridge.hesitation_plan(
            {"immunity": {"boundary_pressure": 1.0}, "needs": {}, "temperature": {"warmth": 0.0}}
        )
        self.assertGreater(plan["hesitation"], 0.8)
        self.assertGreater(plan["pre_delay_seconds"], 0.0)

    def test_apply_segment_hesitation_low_noop(self):
        """低犹豫 → 分段原样返回。"""
        syl = FakeSylanne(FakeContext(FakeProactivePlugin()))
        bridge = ProactiveBridge(syl)
        parts = [{"index": 0, "text": "你好", "delay_before_seconds": 0.5}]
        out = bridge.apply_segment_hesitation(
            parts, {"needs": {"need_expression": 1.0}, "temperature": {"warmth": 1.0}}
        )
        self.assertEqual(out, parts)

    def test_apply_segment_hesitation_high_mutates(self):
        """高犹豫 → 分段被注入加长停顿或省略号（固定种子）。"""
        import random as _r

        syl = FakeSylanne(FakeContext(FakeProactivePlugin()))
        bridge = ProactiveBridge(syl)
        parts = [
            {"index": 0, "text": "在吗", "delay_before_seconds": 0.5},
            {"index": 1, "text": "想跟你说个事", "delay_before_seconds": 1.0},
        ]
        _r.seed(7)
        out = bridge.apply_segment_hesitation(
            parts, {"immunity": {"boundary_pressure": 1.0}, "needs": {}, "temperature": {"warmth": 0.0}}
        )
        # 至少一处 delay 被拉长，或有段尾追加了省略号
        delay_grew = any(
            out[i]["delay_before_seconds"] > parts[i]["delay_before_seconds"]
            for i in range(len(parts))
        )
        ellipsis_added = any("……" in p["text"] for p in out)
        self.assertTrue(delay_grew or ellipsis_added)


if __name__ == "__main__":
    unittest.main()
