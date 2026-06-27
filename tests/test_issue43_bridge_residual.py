"""issue#43 Wave2 回归：主动发言桥接 override 残留加固（provenance 还原 + per-sid 锁）。

原 bug（根因 (c)）：dispatch 注入 proactive_prompt 后进程崩溃 → finally 没跑 → 大饼磁盘
永久残留 Sylanne 的临时素材 → 大饼自驱定时复用同一素材反复发（主动消息复读）；并发
dispatch∥adjust_countdown 跨段非原子也会把残留写回复活（竞态②）。

修复（不碰大饼）：
- per-sid 锁短临界区序列化 dispatch∥adjust，RMW 只还原自己注入的键 → 治竞态②，
  且锁【不跨】check_and_chat（否则下方 test_concurrent_adjust 会死锁挂住）。
- 注入前把干净基线存 Sylanne 自己 KV（sidecar），启动 recover_inflight_baselines
  精确还原（含用户自配 pp）→ 治崩溃残留①。
- 绝不按 key/value 盲删 proactive_prompt（红队 BLOCKER：那是大饼一级用户配置，
  盲删=砸用户配置 + 破不碰大饼）。test_recovery_noop_* 即此防回归。
"""

import asyncio
import unittest

from sylanne_alpha.proactive_bridge import ProactiveBridge

_KV = ProactiveBridge._BASELINE_KV


class FakeOverrideManager:
    def __init__(self):
        self.store: dict[str, dict] = {}
        self._set_n = 0
        self.fail_on_set_call: int | None = None  # 让第 N 次 set_override 抛错（模拟瞬时失败）
        self.fail_get: bool = False  # 让 get_override 抛错（模拟瞬时读失败）

    def get_override(self, sid: str) -> dict:
        if self.fail_get:
            raise RuntimeError("transient get_override failure")
        return dict(self.store.get(sid, {}))

    async def set_override(self, sid: str, patch: dict) -> None:
        self._set_n += 1
        if self.fail_on_set_call is not None and self._set_n == self.fail_on_set_call:
            raise RuntimeError("transient set_override failure")
        if patch:  # 模拟大饼：set_override({}) 即 pop
            self.store[sid] = dict(patch)
        else:
            self.store.pop(sid, None)

    async def delete_override(self, sid: str) -> None:
        self.store.pop(sid, None)


class FakeDaPing:
    def __init__(self):
        self.session_override_manager = FakeOverrideManager()
        self.received_pp = None
        self._on_check = None  # 注入 check_and_chat 期间的副作用（模拟并发 dispatch/tick）
        self._on_schedule = None  # 注入 _schedule_next_chat_and_save 期间的副作用（并发 adjust）

    async def check_and_chat(self, sid: str) -> None:
        self.received_pp = self.session_override_manager.store.get(sid, {}).get(
            "proactive_prompt"
        )
        if self._on_check is not None:
            await self._on_check(sid)

    async def _schedule_next_chat_and_save(self, sid: str) -> None:
        if self._on_schedule is not None:
            await self._on_schedule(sid)


class _Meta:
    def __init__(self, star):
        self.star_cls = star


class FakeContext:
    def __init__(self, star):
        self._star = star

    def get_registered_star(self, name: str):
        return _Meta(self._star) if name == "astrbot_plugin_proactive_chat" else None


class _Store:
    def __init__(self):
        self.session_origins: dict[str, str] = {}


class FakeKVSylanne:
    """带 KV 的 Sylanne 插件替身（sidecar 持久化用）。"""

    def __init__(self, star, *, body=None, guard_allowed=True, kv_enabled=True):
        self.context = FakeContext(star)
        self._store = _Store()
        self.config: dict = {}
        self._kv: dict = {}
        self._kv_enabled = kv_enabled
        self._body = body
        self._guard_allowed = guard_allowed

    def _has_kv_api(self) -> bool:
        return self._kv_enabled

    async def get_kv_data(self, key, default=None):
        return self._kv.get(key, default)

    async def put_kv_data(self, key, value):
        self._kv[key] = value

    async def proactive_sylanne(self, *, session_key: str, now: float = 0.0) -> dict:
        out = {"decision": {}, "guard": {"allowed": self._guard_allowed}}
        if self._body is not None:
            out["body"] = self._body
        return out


def _run(coro, timeout=5.0):
    async def _w():
        return await asyncio.wait_for(coro, timeout)

    return asyncio.run(_w())


class TestProvenanceRecovery(unittest.TestCase):
    def test_user_pp_preserved_after_normal_dispatch(self):
        """正常收尾：用户自配 pp + 其它配置完好还原，sidecar 清空。"""
        star = FakeDaPing()
        star.session_override_manager.store["s1"] = {
            "proactive_prompt": "USER_PP", "tts_settings": {"x": 1}
        }
        syl = FakeKVSylanne(star)
        bridge = ProactiveBridge(syl)

        res = _run(bridge.dispatch("s1", "MOTIVATION"))
        self.assertTrue(res["dispatched"])
        self.assertEqual(star.received_pp, "MOTIVATION")  # check 时生效的是注入素材
        self.assertEqual(
            star.session_override_manager.store["s1"],
            {"proactive_prompt": "USER_PP", "tts_settings": {"x": 1}},
        )
        self.assertEqual(syl._kv.get(_KV), {})  # sidecar 用完即清

    def test_crash_residual_recovered_to_user_baseline(self):
        """① 崩溃残留：注入已落盘 + sidecar 存着干净基线 → 启动还原回用户 pp。"""
        star = FakeDaPing()
        syl = FakeKVSylanne(star)
        bridge = ProactiveBridge(syl)
        # 构造崩溃后磁盘态
        star.session_override_manager.store["s1"] = {"proactive_prompt": "MOTIVATION_RESIDUAL"}
        syl._kv[_KV] = {"s1": {"proactive_prompt": "USER_PP"}}

        n = _run(bridge.recover_inflight_baselines())
        self.assertEqual(n, 1)
        self.assertEqual(
            star.session_override_manager.store["s1"], {"proactive_prompt": "USER_PP"}
        )
        self.assertEqual(syl._kv[_KV], {})  # sidecar 清空

    def test_crash_residual_empty_baseline_deletes(self):
        """用户本无 override：崩溃残留应被删干净（基线为空 → delete）。"""
        star = FakeDaPing()
        syl = FakeKVSylanne(star)
        bridge = ProactiveBridge(syl)
        star.session_override_manager.store["s1"] = {"proactive_prompt": "MOTIVATION_RESIDUAL"}
        syl._kv[_KV] = {"s1": {}}

        _run(bridge.recover_inflight_baselines())
        self.assertNotIn("s1", star.session_override_manager.store)

    def test_recovery_noop_without_sidecar(self):
        """红队 BLOCKER 防回归：无 sidecar 记录时，绝不动大饼的用户 pp（不盲删）。"""
        star = FakeDaPing()
        star.session_override_manager.store["s1"] = {"proactive_prompt": "USER_PP"}
        syl = FakeKVSylanne(star)
        bridge = ProactiveBridge(syl)

        n = _run(bridge.recover_inflight_baselines())
        self.assertEqual(n, 0)
        self.assertEqual(
            star.session_override_manager.store["s1"], {"proactive_prompt": "USER_PP"}
        )

    def test_recovery_noop_without_kv_api(self):
        """无 KV 能力：recover 静默降级返回 0，不抛。"""
        star = FakeDaPing()
        syl = FakeKVSylanne(star, kv_enabled=False)
        bridge = ProactiveBridge(syl)
        self.assertEqual(_run(bridge.recover_inflight_baselines()), 0)

    def test_recovery_preserves_non_dispatch_keys(self):
        """恢复只 RMW dispatch 拥有的键（pp/segmented）；schedule 等其它键不被波及
        （红队 finding：原先 set_override(整条 baseline) 会把并发 adjust 的临时 schedule 当
        永久配置写回）。"""
        star = FakeDaPing()
        syl = FakeKVSylanne(star)
        bridge = ProactiveBridge(syl)
        star.session_override_manager.store["s1"] = {
            "proactive_prompt": "MOTIV_RESIDUAL",
            "schedule_settings": {"min_interval_minutes": 1},
        }
        syl._kv[_KV] = {"s1": {"proactive_prompt": "USER_PP"}}  # 只存 dispatch 拥有键
        _run(bridge.recover_inflight_baselines())
        final = star.session_override_manager.store["s1"]
        self.assertEqual(final.get("proactive_prompt"), "USER_PP", "pp 还原用户基线")
        self.assertEqual(
            final.get("schedule_settings"), {"min_interval_minutes": 1},
            "非 dispatch 拥有的 schedule 不被恢复波及",
        )

    def test_get_override_failure_aborts_restore_no_wipe(self):
        """gemini PR#46：get_override 抛异常时绝不能用 cur={} 重写——会抹掉读失败时没读到的
        并发键。读失败须中止：_restore_dispatch_keys 返 False、_restore_schedule_keys 不写，
        override 全键原样保留。"""
        star = FakeDaPing()
        syl = FakeKVSylanne(star)
        bridge = ProactiveBridge(syl)
        mgr = star.session_override_manager
        live = {"proactive_prompt": "桥注入", "schedule_settings": {"min_interval_minutes": 1}}
        mgr.store["s1"] = dict(live)
        mgr.fail_get = True
        # dispatch 还原：读失败 → 返回 False（保留 sidecar 下次再修），且一个键都不许动
        ok = _run(bridge._restore_dispatch_keys(mgr, "s1", {}))
        self.assertFalse(ok, "读失败应返回 False")
        self.assertEqual(mgr.store["s1"], live, "读失败不得用 cur={} 重写抹掉任何键")
        # schedule 还原：读失败 → 不写，键全保留
        _run(bridge._restore_schedule_keys(mgr, "s1", {}))
        self.assertEqual(mgr.store["s1"], live, "schedule 读失败同样不得抹键")


class TestRaceSerialization(unittest.TestCase):
    def test_concurrent_adjust_during_dispatch_no_residual(self):
        """竞态②：dispatch 的 check_and_chat 期间穿插一次完整 adjust_countdown（同 sid），
        结束后收敛——pp 还原用户基线、schedule 不残留、sidecar 清空。

        若锁错误地跨 check_and_chat，adjust 段1 的 _lock_for(sid) 会死锁，本测试超时失败。
        """
        star = FakeDaPing()
        star.session_override_manager.store["s1"] = {"proactive_prompt": "USER_PP"}
        syl = FakeKVSylanne(star, body={"needs": {"need_expression": 1.0}})
        bridge = ProactiveBridge(syl)

        async def _interleave(sid):
            await bridge.adjust_countdown("s1")

        star._on_check = _interleave

        res = _run(bridge.dispatch("s1", "MOTIVATION"))
        self.assertTrue(res["dispatched"])
        final = star.session_override_manager.store.get("s1", {})
        self.assertEqual(final.get("proactive_prompt"), "USER_PP", "并发后 pp 必须还原用户基线")
        self.assertNotIn("schedule_settings", final, "adjust 的临时 schedule 不得残留")
        self.assertEqual(syl._kv.get(_KV), {})

    def test_lock_keyed_on_resolved_origin(self):
        """锁键必须用 resolved origin：两个不同 raw key 解析到同一 origin → 同一把锁
        （否则 dispatch/adjust 锁到不同键、白锁，竞态②不修）。"""
        star = FakeDaPing()
        syl = FakeKVSylanne(star)
        syl._store.session_origins = {"sk::agent:u1": "umo:1"}
        bridge = ProactiveBridge(syl)

        sid = bridge._resolve_origin("sk::agent:u1")
        self.assertEqual(sid, "umo:1")
        self.assertIs(bridge._lock_for(sid), bridge._lock_for(sid))

    def test_concurrent_dispatch_dispatch_no_residual(self):
        """竞态②同方法版（验证红队 MAJOR）：两个 dispatch 真并发同 sid。锁不跨 LLM 窗口，
        若无 in-flight 闸，第二个会把第一个的注入误当基线 → pp 残留复读。修复后：只一个注入，
        另一个 dispatch_in_flight，结束 store 还原用户基线、sidecar 清空。"""
        star = FakeDaPing()
        star.session_override_manager.store["s1"] = {"proactive_prompt": "USER_PP"}
        syl = FakeKVSylanne(star)
        bridge = ProactiveBridge(syl)

        async def run():
            gate = asyncio.Event()
            in_check = asyncio.Event()

            async def _suspend(sid):
                in_check.set()
                await gate.wait()  # 第一个 dispatch 卡在 check_and_chat（已注入、锁已释放）

            star._on_check = _suspend
            t1 = asyncio.create_task(bridge.dispatch("s1", "MOTIV_A"))
            await in_check.wait()
            r2 = await bridge.dispatch("s1", "MOTIV_B")  # 并发进来，应被 in-flight 闸挡
            gate.set()
            r1 = await t1
            return r1, r2

        r1, r2 = _run(run())
        self.assertTrue(r1["dispatched"])
        self.assertFalse(r2["dispatched"])
        self.assertEqual(r2["reason"], "dispatch_in_flight")
        final = star.session_override_manager.store.get("s1", {})
        self.assertEqual(final.get("proactive_prompt"), "USER_PP", "并发 dispatch 后无 pp 残留")
        self.assertEqual(syl._kv.get(_KV), {})

    def test_concurrent_adjust_adjust_no_residual(self):
        """adjust∥adjust 真并发同 sid：in-flight 闸保证只一个注入，无 schedule 残留。"""
        star = FakeDaPing()
        star.session_override_manager.store["s1"] = {"proactive_prompt": "USER_PP"}
        syl = FakeKVSylanne(star, body={"needs": {"need_expression": 1.0}})
        bridge = ProactiveBridge(syl)

        async def run():
            gate = asyncio.Event()
            in_sched = asyncio.Event()

            async def _suspend(sid):
                in_sched.set()
                await gate.wait()  # 第一个 adjust 卡在 _schedule（已注入、锁已释放）

            star._on_schedule = _suspend
            t1 = asyncio.create_task(bridge.adjust_countdown("s1"))
            await in_sched.wait()
            r2 = await bridge.adjust_countdown("s1")  # 并发，应被 in-flight 闸挡
            gate.set()
            r1 = await t1
            return r1, r2

        r1, r2 = _run(run())
        self.assertTrue(r1["adjusted"])
        self.assertFalse(r2["adjusted"])
        self.assertEqual(r2["reason"], "adjust_in_flight")
        final = star.session_override_manager.store.get("s1", {})
        self.assertEqual(final.get("proactive_prompt"), "USER_PP")
        self.assertNotIn("schedule_settings", final, "并发 adjust 后无 schedule 残留")

    def test_transient_restore_failure_keeps_sidecar_for_recover(self):
        """复审 CLUSTER A：段3 restore 瞬时失败时，绝不清掉 sidecar——保留 breadcrumb 让
        启动 recover 修复。原 bug：无条件清 sidecar → 注入素材永久残留 = 重现 issue#43。"""
        star = FakeDaPing()
        star.session_override_manager.store["s1"] = {"proactive_prompt": "USER_PP"}
        syl = FakeKVSylanne(star)
        bridge = ProactiveBridge(syl)
        star.session_override_manager.fail_on_set_call = 2  # set#1 注入成功, set#2 还原失败

        res = _run(bridge.dispatch("s1", "MOTIV"))
        self.assertTrue(res["dispatched"])
        # 还原失败 → sidecar 必须保住干净基线（没被清）
        self.assertEqual(syl._kv.get(_KV), {"s1": {"proactive_prompt": "USER_PP"}})

        # 启动 recover 修复（此时 set 恢复正常）
        star.session_override_manager.fail_on_set_call = None
        n = _run(bridge.recover_inflight_baselines())
        self.assertEqual(n, 1)
        self.assertEqual(
            star.session_override_manager.store["s1"], {"proactive_prompt": "USER_PP"}
        )
        self.assertEqual(syl._kv.get(_KV), {})

    def test_cancel_mid_dispatch_restores_store_via_finally(self):
        """复审 CLUSTER A：CancelledError 打断 dispatch 时，段3 在 finally 里仍把 override
        还原干净（原 bug：段3 在 finally 外，取消会跳过 → 注入残留 + 可被后续 dispatch latch 死）。"""
        star = FakeDaPing()
        star.session_override_manager.store["s1"] = {"proactive_prompt": "USER_PP"}
        syl = FakeKVSylanne(star)
        bridge = ProactiveBridge(syl)

        async def _cancel(sid):
            raise asyncio.CancelledError()

        star._on_check = _cancel

        async def run():
            try:
                await bridge.dispatch("s1", "MOTIV")
            except asyncio.CancelledError:
                pass

        _run(run())
        self.assertEqual(
            star.session_override_manager.store["s1"], {"proactive_prompt": "USER_PP"},
            "段3 在 finally → 取消也还原, store 不留注入残留",
        )
        self.assertNotIn("s1", bridge._inflight_dispatch)

    def test_latching_prevented_via_sidecar_baseline(self):
        """复审 CLUSTER A anti-latching：上次 dispatch 没还原干净（override 脏 + sidecar 留着
        干净基线），下次 dispatch 用 sidecar 基线还原，不把脏残留当基线 latch 死。"""
        star = FakeDaPing()
        syl = FakeKVSylanne(star)
        bridge = ProactiveBridge(syl)
        # 崩溃后态：override 脏=注入残留, sidecar 留着干净基线 USER_PP
        star.session_override_manager.store["s1"] = {"proactive_prompt": "MOTIV_OLD_RESIDUAL"}
        syl._kv[_KV] = {"s1": {"proactive_prompt": "USER_PP"}}

        res = _run(bridge.dispatch("s1", "MOTIV_NEW"))
        self.assertTrue(res["dispatched"])
        # 用 sidecar 基线(USER_PP)还原, 不信脏 live → 残留被清成用户 pp
        self.assertEqual(
            star.session_override_manager.store["s1"], {"proactive_prompt": "USER_PP"}
        )
        self.assertEqual(syl._kv.get(_KV), {})

    def test_recover_failure_preserves_that_breadcrumb(self):
        """复审 CLUSTER A：recover 不再先清空整个 sidecar；某 sid 还原失败时只保留它的
        breadcrumb，其它 sid 照常修好。"""
        star = FakeDaPing()
        syl = FakeKVSylanne(star)
        bridge = ProactiveBridge(syl)
        star.session_override_manager.store = {
            "s1": {"proactive_prompt": "RESID1"}, "s2": {"proactive_prompt": "RESID2"}
        }
        syl._kv[_KV] = {
            "s1": {"proactive_prompt": "USER1"}, "s2": {"proactive_prompt": "USER2"}
        }
        star.session_override_manager.fail_on_set_call = 1  # s1 的还原 set 失败, s2 成功

        n = _run(bridge.recover_inflight_baselines())
        self.assertEqual(n, 1)
        remaining = syl._kv.get(_KV, {})
        self.assertIn("s1", remaining, "失败的 sid breadcrumb 必须保留")
        self.assertNotIn("s2", remaining, "成功的 sid breadcrumb 已清")
        self.assertEqual(
            star.session_override_manager.store["s2"], {"proactive_prompt": "USER2"}
        )

    def test_baseexception_in_check_clears_inflight(self):
        """段2 抛 BaseException（如 CancelledError）时，in-flight 闸必被 try/finally 清掉，
        不留永久阻塞（round-3 硬化：原 try/except-Exception+顺序段3 会漏清）。"""

        class _Boom(BaseException):
            pass

        star = FakeDaPing()
        syl = FakeKVSylanne(star)
        bridge = ProactiveBridge(syl)

        async def _boom(sid):
            raise _Boom()

        star._on_check = _boom
        with self.assertRaises(_Boom):
            _run(bridge.dispatch("s1", "MOTIV"))
        self.assertNotIn("s1", bridge._inflight_dispatch, "BaseException 后 in-flight 闸必须已清")
        # 后续同 sid dispatch 不被永久阻塞
        star._on_check = None
        r2 = _run(bridge.dispatch("s1", "MOTIV2"))
        self.assertTrue(r2["dispatched"], "取消/异常后 sid 不卡死，后续 dispatch 正常")
