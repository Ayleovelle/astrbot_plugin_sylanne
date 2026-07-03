"""MEM-03 PR-4：持久化 pending-delete 索引 + 启动扫描 + 全局锁——回归测试。

覆盖卡片要求的五类测试：
  1. register-then-clear：正常删除 op 首步登记、末步摘除。
  2. 崩溃残留补删：primary 已空 + 侧车残留 → 扫描补删 + 摘除 entry。
  3. BLOCKER 负测试：primary 非空 → 绝不重放，数据原样保留，entry 保留。
  4. fail-closed：持久镜像里存在未决 entry 时，hydrate 拒绝合并、load 拒绝准入。
  5. 全局锁：两条并发 register 不互相踩踏丢更新（含反事实证明竞态真实存在）。
"""

from __future__ import annotations

import asyncio

from sylanne_alpha.memory_legacy_formats import quarantine_kv_key
from sylanne_alpha.memory_system import MemorySystem
from sylanne_alpha.session_context import SessionContext
from sylanne_alpha.session_state_store import SessionStateStore
from sylanne_alpha.state_persistence import PENDING_DELETE_INDEX_KV_KEY, StatePersistence


class _FakePlugin:
    """最小化插件替身，复刻 tests/test_mem02_restore_wiring.py 的写法。"""

    def __init__(self, shared_kv: dict | None = None) -> None:
        self._store = SessionStateStore()
        self._background_tasks: list = []
        self.config: dict = {}
        self._config: dict = {}
        self._kv: dict = shared_kv if shared_kv is not None else {}
        self._amnesia_sessions: set = set()
        self.kv_call_log: list[tuple[str, str]] = []
        self._session_ctx = SessionContext(self)
        self._state_persistence = StatePersistence(self)
        # 测试默认模拟"initialize() 的 pending-delete 启动扫描已完成"——生产里 WebUI
        # load 只发生在 init 之后。需要测 pre-scan fail-closed 的用例显式设回 False。
        self._state_persistence._pending_delete_scan_done = True

    async def get_kv_data(self, key: str, default=None):  # noqa: ANN001
        return self._kv.get(key, default)

    async def put_kv_data(self, key: str, value) -> None:  # noqa: ANN001
        self._kv[key] = value
        self.kv_call_log.append(("put", key))

    async def delete_kv_data(self, key: str) -> None:
        self._kv.pop(key, None)
        self.kv_call_log.append(("delete", key))

    def _memory_system_for_session(self, session_key: str) -> MemorySystem:
        return self._session_ctx.memory_system_for_session(session_key)

    def _memory_system_has_content(self, memory_system) -> bool:  # noqa: ANN001
        return self._session_ctx.memory_system_has_content(memory_system)


_ARCHIVE_TEMPLATE = {
    "version": "3.0.0",
    "l1": [
        {
            "id": "seed",
            "text": "待保护记忆",
            "weight": 1.0,
            "temperature": 0.0,
            "age_ticks": 0,
            "created_at": 1.0,
        }
    ],
    "l2": [],
    "l3_nodes": {},
    "l3_edges": [],
}


def _empty_archive() -> dict:
    return {"version": "3.0.0", "l1": [], "l2": [], "l3_nodes": {}, "l3_edges": []}


# ===========================================================================
# 1. register-then-clear
# ===========================================================================


def test_register_before_delete_and_clear_after_normal_delete() -> None:
    """正常删除 op：首步登记 entry（进程内镜像 + 索引 KV 都可见），末步（三键+scrub
    全部跑完后）摘除——索引 KV 结束时不再含该 session。用暂停内层 _impl 的手法
    在 op 执行【期间】拍一张快照，证明 register 确实发生在删除完成之前，而不是
    只在事后碰巧两头都是空。
    """

    async def go() -> None:
        shared_kv: dict = {}
        p = _FakePlugin(shared_kv)
        sp = p._state_persistence
        sk = "sess:reg-clear"
        safe = sp._safe_session_key(sk)

        mem = p._memory_system_for_session(sk)
        mem._hydrated = True
        mem.write_summary(text="待删记忆", source_turns=1, session_key=sk)
        await sp.save_sylanne_memory_state(sk, mem)
        assert shared_kv["sylanne_memory_state:sess:reg-clear"]["l1"]

        started = asyncio.Event()
        release = asyncio.Event()
        original_impl = sp._delete_sylanne_memory_state_impl

        async def paused_impl(session_key: str) -> bool:
            started.set()
            await release.wait()
            # PR-4 gate CRITICAL：impl 现在返回是否全删成功，op 壳据此 gate clear——
            # 包装器必须【转发】返回值，否则 deleted_ok=None(falsy) 会误判成删除失败、不摘 entry。
            return await original_impl(session_key)

        sp._delete_sylanne_memory_state_impl = paused_impl  # type: ignore[method-assign]

        delete_task = asyncio.create_task(sp.delete_sylanne_memory_state(sk))
        await started.wait()

        # Op 正在跑（还没删任何键）——此刻 register 必须已经发生。
        assert safe in sp._pending_delete_mirror, "register 未在删除开始前登记进程内镜像"
        index_blob = shared_kv.get(PENDING_DELETE_INDEX_KV_KEY)
        assert index_blob is not None and safe in index_blob["entries"], (
            "register 未把 entry 落盘进索引 KV"
        )

        release.set()
        await delete_task

        # 全部删除步骤跑完——clear 必须已经发生。
        assert safe not in sp._pending_delete_mirror, "clear 未在删除完成后摘除进程内镜像"
        index_blob = shared_kv.get(PENDING_DELETE_INDEX_KV_KEY)
        assert not index_blob or safe not in index_blob.get("entries", {}), (
            "clear 未把 entry 从索引 KV 摘除"
        )

    asyncio.run(go())


def test_register_clear_also_wraps_purge_and_session_delete_ops() -> None:
    """purge_session_after_meltdown / _on_session_deleted 两条复合删除 op 同样必须
    首尾包裹 register/clear，且不因为内部调用 `_delete_sylanne_memory_state_impl`
    （而非 `_delete_sylanne_memory_state_op`）而漏登记——三个 op 都各自恰好一次
    register + 一次 clear（非双重）。
    """

    async def go_purge() -> None:
        shared_kv: dict = {
            "sylanne_memory_state:sess:melt": dict(_empty_archive()),
        }
        p = _FakePlugin(shared_kv)
        sp = p._state_persistence
        sk = "sess:melt"
        safe = sp._safe_session_key(sk)

        await sp.purge_session_after_meltdown(sk)

        assert safe not in sp._pending_delete_mirror
        index_blob = shared_kv.get(PENDING_DELETE_INDEX_KV_KEY)
        assert not index_blob or safe not in index_blob.get("entries", {})

    async def go_session_delete() -> None:
        shared_kv: dict = {}
        p = _FakePlugin(shared_kv)
        sp = p._state_persistence
        sk = "sess:on-deleted"
        safe = sp._safe_session_key(sk)
        mem = p._memory_system_for_session(sk)
        mem._hydrated = True
        mem.write_summary(text="x", source_turns=1, session_key=sk)
        await sp.save_sylanne_memory_state(sk, mem)

        sp._on_session_deleted(sk)
        # fire-and-forget：等 drainer 跑完。
        for _ in range(10):
            drainer = sp._throat._drainers.get(sk)
            if drainer is None:
                break
            await asyncio.gather(drainer, return_exceptions=True)

        assert safe not in sp._pending_delete_mirror
        index_blob = shared_kv.get(PENDING_DELETE_INDEX_KV_KEY)
        assert not index_blob or safe not in index_blob.get("entries", {})

    asyncio.run(go_purge())
    asyncio.run(go_session_delete())


# ===========================================================================
# 2. 崩溃残留：primary 已空/缺失 → 扫描补删侧车键 + 摘除 entry
# ===========================================================================


def test_scan_finishes_crash_residue_when_primary_missing_or_empty() -> None:
    """两个子场景合一：primary 完全缺失（sess:crash-missing）与 primary 键存在但
    l1/l2/l3 皆空（sess:crash-empty）——都必须被判定为"delete 已经开始执行"，
    补删残留的 backup_v2/quarantine 侧车键，并摘除各自的索引 entry。
    """

    async def go() -> None:
        shared_kv: dict = {}
        p = _FakePlugin(shared_kv)
        sp = p._state_persistence

        entries: dict = {}
        for sk in ("sess:crash-missing", "sess:crash-empty"):
            safe = sp._safe_session_key(sk)
            backup_key = sp.sylanne_memory_backup_v2_kv_key(sk)
            q_key = quarantine_kv_key(safe)
            shared_kv[backup_key] = {"data": {"l1": [{"text": "旧明文"}]}, "_crc32": 1}
            shared_kv[q_key] = [{"raw": {"text": "隔离残留"}}]
            entries[safe] = {"epoch": 1, "ts": 100.0}

        # sess:crash-empty 的 primary 键存在但内容为空（另一半场景）；
        # sess:crash-missing 的 primary 键干脆不存在。
        empty_safe = sp._safe_session_key("sess:crash-empty")
        shared_kv[sp.sylanne_memory_kv_key(empty_safe)] = _empty_archive()

        shared_kv[PENDING_DELETE_INDEX_KV_KEY] = {"version": 1, "entries": entries}

        await sp._scan_pending_deletes()

        for sk in ("sess:crash-missing", "sess:crash-empty"):
            safe = sp._safe_session_key(sk)
            backup_key = sp.sylanne_memory_backup_v2_kv_key(sk)
            q_key = quarantine_kv_key(safe)
            assert backup_key not in shared_kv, f"{sk} 崩溃残留 backup_v2 未被扫描补删"
            assert q_key not in shared_kv, f"{sk} 崩溃残留 quarantine 未被扫描补删"
            assert safe not in sp._pending_delete_mirror, f"{sk} 的 entry 未被摘除"

        index_blob = shared_kv.get(PENDING_DELETE_INDEX_KV_KEY)
        assert not index_blob or not index_blob.get("entries"), (
            "扫描完成后索引 KV 里不应还残留任何 entry"
        )

    asyncio.run(go())


def test_scan_multi_entry_does_not_lose_unprocessed_entry_from_persisted_index() -> None:
    """自我审查踩中的一个真实排序坑（已修复，本测试是它的回归锁）：索引里同时有
    两条 entry——一条（按字典遍历顺序先处理）primary 缺失该被 finish+clear，另
    一条（后处理）primary 非空该被保留。如果扫描"边遍历边决定清不清"而不是
    "先把全部 entry 整体载入镜像、再逐条决断"，第一条触发的 clear 会用一份还
    没包含第二条的镜像快照整体覆盖持久化 KV，导致第二条本该保留的 entry 在
    扫描过程中被意外从持久化索引里抹掉（即便进程内镜像最终仍然正确）——若
    进程恰好在扫描完成前后崩溃，第二条 entry 的持久证据就没了。
    """

    async def go() -> None:
        shared_kv: dict = {}
        p = _FakePlugin(shared_kv)
        sp = p._state_persistence

        finish_sk = "sess:order-finish"
        keep_sk = "sess:order-keep"
        finish_safe = sp._safe_session_key(finish_sk)
        keep_safe = sp._safe_session_key(keep_sk)

        # finish_safe 在字典里排在前面——扫描按插入顺序会先处理它。
        shared_kv[PENDING_DELETE_INDEX_KV_KEY] = {
            "version": 1,
            "entries": {
                finish_safe: {"epoch": 1, "ts": 1.0},
                keep_safe: {"epoch": 1, "ts": 2.0},
            },
        }
        # keep_safe 的 primary 非空——该被保留（绝不重放）；finish_safe 的 primary
        # 缺失——该被补删 + 摘除。
        shared_kv[sp.sylanne_memory_kv_key(keep_safe)] = {
            "version": "3.0.0",
            "l1": [
                {
                    "id": "x",
                    "text": "保留中的合法数据",
                    "weight": 1.0,
                    "temperature": 0.0,
                    "age_ticks": 0,
                    "created_at": 1.0,
                }
            ],
            "l2": [],
            "l3_nodes": {},
            "l3_edges": [],
        }

        await sp._scan_pending_deletes()

        assert finish_safe not in sp._pending_delete_mirror
        assert keep_safe in sp._pending_delete_mirror, "进程内镜像丢了未处理完的 entry"

        index_blob = shared_kv.get(PENDING_DELETE_INDEX_KV_KEY)
        assert index_blob is not None
        assert finish_safe not in index_blob["entries"]
        assert keep_safe in index_blob["entries"], (
            "排序坑回归：持久化索引在扫描中途被一次 clear 的整体快照覆盖，"
            "丢失了尚未处理完的 entry"
        )

    asyncio.run(go())


# ===========================================================================
# 3. BLOCKER 负测试：primary 非空 → 绝不重放
# ===========================================================================


def test_scan_refuses_to_replay_when_primary_nonempty_blocker() -> None:
    """红队头号红线：primary 非空（模拟回滚到 Phase-0 期间用户产生了合法新记忆，
    再次升级后仍看到这条陈旧 entry）——扫描绝不能把这份新数据当成"该删的旧数据"
    重放删除。数据必须原样保留，entry 必须保留（交管理员），且必须记 error。
    """

    async def go() -> None:
        sk = "sess:rollback-newdata"
        kv_key = "sylanne_memory_state:sess:rollback-newdata"
        shared_kv: dict = {
            kv_key: {
                "version": "3.0.0",
                "l1": [
                    {
                        "id": "new",
                        "text": "回滚期用户产生的合法新记忆",
                        "weight": 1.0,
                        "temperature": 0.0,
                        "age_ticks": 0,
                        "created_at": 2.0,
                    }
                ],
                "l2": [],
                "l3_nodes": {},
                "l3_edges": [],
            }
        }
        p = _FakePlugin(shared_kv)
        sp = p._state_persistence
        safe = sp._safe_session_key(sk)
        backup_key = sp.sylanne_memory_backup_v2_kv_key(sk)
        shared_kv[backup_key] = {"data": {"l1": [{"text": "旧明文"}]}, "_crc32": 1}
        shared_kv[PENDING_DELETE_INDEX_KV_KEY] = {
            "version": 1,
            "entries": {safe: {"epoch": 1, "ts": 100.0}},
        }

        await sp._scan_pending_deletes()

        # BLOCKER：数据必须原样保留，一个字节都不能动。
        assert shared_kv[kv_key]["l1"][0]["text"] == "回滚期用户产生的合法新记忆", (
            "BLOCKER 回归：扫描盲重放摧毁了回滚期产生的合法新数据"
        )
        assert backup_key in shared_kv, "BLOCKER 回归：非重放场景下备份键也被误删了"

        # entry 必须保留——交管理员决断，不能被这次扫描静默解决掉。
        assert safe in sp._pending_delete_mirror, (
            "primary 非空时 entry 被错误地摘除了（应保留，交管理员）"
        )
        index_blob = shared_kv[PENDING_DELETE_INDEX_KV_KEY]
        assert safe in index_blob["entries"], "primary 非空时索引 KV 里的 entry 被错误摘除"

    asyncio.run(go())


# ===========================================================================
# 4. fail-closed：持久镜像里的未决 entry 阻断 hydrate / load-admit
# ===========================================================================


def test_hydrate_fail_closed_when_persistent_mirror_has_unresolved_entry() -> None:
    """跨重启信号（不是本进程咽喉的排队/inflight 状态，纯粹是"扫描发现过一条歧义
    entry、已经载入镜像"）——即使咽喉本身完全空闲，hydrate 也必须拒绝合并。
    """

    async def go() -> None:
        sk = "sess:persist-mirror-hydrate"
        kv_key = "sylanne_memory_state:sess:persist-mirror-hydrate"
        shared_kv: dict = {kv_key: dict(_ARCHIVE_TEMPLATE)}
        p = _FakePlugin(shared_kv)
        sp = p._state_persistence
        safe = sp._safe_session_key(sk)

        # 懒创建之外手动摆一个未补水的空活体在 store 占位（聚焦测试 hydrate 这一道
        # 闸门本身，不依赖 memory_system_for_session 的自动调度时序）。
        mem = MemorySystem()
        p._store.memory_systems.set(sk, mem)
        assert mem._hydrated is False

        assert sp._throat.has_pending_delete(sk) is False  # 确认信号只来自持久镜像
        sp._pending_delete_mirror[safe] = {"epoch": 0, "ts": 1.0}

        await sp.hydrate_memory_system(sk)

        assert mem._hydrated is False, (
            "持久 pending-delete 未决时 hydrate 仍然合并了 KV 归档（fail-closed 回归）"
        )
        assert not p._memory_system_has_content(mem)

    asyncio.run(go())


def test_hydrate_admits_normally_once_persistent_entry_cleared() -> None:
    """反事实对照：一旦镜像里的 entry 被摘除（entry 解决之后），hydrate 必须正常
    合并——证明上面的拒绝不是"恒拒绝"这种退化实现骗过测试。
    """

    async def go() -> None:
        sk = "sess:persist-mirror-hydrate-ok"
        kv_key = "sylanne_memory_state:sess:persist-mirror-hydrate-ok"
        shared_kv: dict = {kv_key: dict(_ARCHIVE_TEMPLATE)}
        p = _FakePlugin(shared_kv)
        sp = p._state_persistence

        mem = MemorySystem()
        p._store.memory_systems.set(sk, mem)

        await sp.hydrate_memory_system(sk)

        assert mem._hydrated is True, "无未决 entry 时 hydrate 却没有正常合并（回归）"
        assert p._memory_system_has_content(mem)

    asyncio.run(go())


def test_load_admit_fail_closed_when_persistent_mirror_has_unresolved_entry() -> None:
    """同上，但测 load 准入：跨重启持久镜像信号必须让 `_load_admit_ok` 判假，
    `load_sylanne_memory_state` 只返回游离展示副本，绝不准入 store。
    """

    async def go() -> None:
        sk = "sess:persist-mirror-load"
        kv_key = "sylanne_memory_state:sess:persist-mirror-load"
        shared_kv: dict = {kv_key: dict(_ARCHIVE_TEMPLATE)}
        p = _FakePlugin(shared_kv)
        sp = p._state_persistence
        safe = sp._safe_session_key(sk)

        assert sp._throat.has_pending_delete(sk) is False
        sp._pending_delete_mirror[safe] = {"epoch": 0, "ts": 1.0}

        loaded = await sp.load_sylanne_memory_state(sk)

        assert loaded is not None  # 仍返回可渲染的展示副本（WebUI 读路径不受影响）
        assert any(
            getattr(it, "text", None) == "待保护记忆"
            for it in list(getattr(loaded, "_l1", []) or [])
        )
        assert p._store.memory_systems.get(sk) is not loaded, (
            "持久 pending-delete 未决时 load 把游离副本准入成了 store 占位者（回归）"
        )
        assert p._store.sylanne_memory_cache.get(sk) is not loaded

    asyncio.run(go())


def test_load_admits_normally_once_persistent_entry_cleared() -> None:
    """反事实对照：没有未决 entry 时，load 必须正常准入。"""

    async def go() -> None:
        sk = "sess:persist-mirror-load-ok"
        kv_key = "sylanne_memory_state:sess:persist-mirror-load-ok"
        shared_kv: dict = {kv_key: dict(_ARCHIVE_TEMPLATE)}
        p = _FakePlugin(shared_kv)
        sp = p._state_persistence

        loaded = await sp.load_sylanne_memory_state(sk)
        assert loaded is not None
        assert p._store.memory_systems.get(sk) is loaded, (
            "无未决 entry 时 load 却没有正常准入（回归）"
        )

    asyncio.run(go())


def test_load_fail_closed_until_startup_scan_done() -> None:
    """PR-4 gate（startup-ordering fail-open）：initialize() 的启动扫描【完成之前】，
    WebUI load 一律不准入 store（只返回游离副本供渲染），防抢跑的读漏检跨重启崩溃
    残留而复活。扫描完成（空索引 → scan_done=True）后恢复正常准入。
    """

    async def go() -> None:
        sk = "sess:pre-scan"
        kv_key = "sylanne_memory_state:sess:pre-scan"
        shared_kv: dict = {kv_key: dict(_ARCHIVE_TEMPLATE)}
        p = _FakePlugin(shared_kv)
        sp = p._state_persistence
        sp._pending_delete_scan_done = False  # 模拟 initialize() 尚未跑扫描

        loaded = await sp.load_sylanne_memory_state(sk)
        assert loaded is not None  # 仍返回对象供渲染
        assert p._store.memory_systems.get(sk) is None, (
            "pre-scan 抢跑的 load 把归档准入了 store（startup fail-open 回归）"
        )

        await sp._scan_pending_deletes()  # 空索引 → 扫描完成
        assert sp._pending_delete_scan_done is True
        loaded2 = await sp.load_sylanne_memory_state(sk)
        assert p._store.memory_systems.get(sk) is loaded2, (
            "扫描完成后 load 仍未恢复正常准入"
        )

    asyncio.run(go())


# ===========================================================================
# 5. 全局锁：并发 register 不丢更新
# ===========================================================================


class _GatedPutKVPlugin(_FakePlugin):
    """`put_kv_data` 在真正写入前可被显式挂起、等测试放行——用来在 register 的
    critical section 内部制造一个确定性的挂起点，验证全局锁是否真的把
    "镜像快照 → 落盘" 这段临界区串行化了（而不是靠运气从不撞车）。
    """

    def __init__(self, shared_kv: dict | None = None) -> None:
        super().__init__(shared_kv)
        self.pause_put = asyncio.Event()
        self.put_paused_signal = asyncio.Event()
        self._should_pause_next_put = False

    async def put_kv_data(self, key, value) -> None:  # noqa: ANN001
        if self._should_pause_next_put:
            self._should_pause_next_put = False
            self.put_paused_signal.set()
            await self.pause_put.wait()
        self._kv[key] = value
        self.kv_call_log.append(("put", key))


def test_global_lock_serializes_concurrent_register_critical_section() -> None:
    """核心保证：全局锁必须把两条并发 register 的"镜像快照 → 整体落盘"临界区
    完全串行化——A 卡在它的 KV put 里（仍持锁）时，B 必须连镜像都还没碰到；
    A 被放行、完整跑完（含锁释放）之后，B 才能推进。最终两个 session 的 entry
    都必须完整出现在持久化索引里（不丢更新）。
    """

    async def go() -> None:
        p = _GatedPutKVPlugin()
        sp = p._state_persistence

        p._should_pause_next_put = True
        task_a = asyncio.create_task(
            sp._register_pending_delete("sess:lock-a", epoch=1)
        )
        await p.put_paused_signal.wait()  # A 已进入锁内部、正卡在它的 KV put 里。

        task_b = asyncio.create_task(
            sp._register_pending_delete("sess:lock-b", epoch=1)
        )
        # 给 B 几个调度轮次的机会——若锁失效，B 会径直修改镜像；若锁生效，B 应该
        # 卡在获取锁那一步，进程内镜像此刻不该出现 sess:lock-b。
        for _ in range(3):
            await asyncio.sleep(0)
        assert "sess:lock-b" not in sp._pending_delete_mirror, (
            "全局锁未生效——B 在 A 仍持锁未完成时就已经修改了镜像（critical section 交错）"
        )

        p.pause_put.set()  # 放行 A，完成它的 put + 释放锁。
        await task_a
        await task_b

        blob = p._kv[PENDING_DELETE_INDEX_KV_KEY]
        assert "sess:lock-a" in blob["entries"]
        assert "sess:lock-b" in blob["entries"], (
            "全局锁未真正串行化——B 的 entry 从最终持久化索引里丢失了（lost update）"
        )
        assert set(sp._pending_delete_mirror.keys()) == {"sess:lock-a", "sess:lock-b"}

    asyncio.run(go())


async def _register_pending_delete_no_lock(sp: StatePersistence, session_key: str, epoch: int) -> None:
    """反事实：复刻 `_register_pending_delete_safe` 但故意跳过全局锁——用来证明
    "去掉锁真的会丢更新"不是危言耸听，这条竞态是这份设计（镜像快照→整体落盘）
    在没有互斥保护时真实会踩中的坑，而不是测试本身编造出来的假想敌。
    """
    safe = sp._safe_session_key(session_key)
    sp._pending_delete_mirror[safe] = {"epoch": epoch, "ts": 0.0}
    blob = {"version": 1, "entries": dict(sp._pending_delete_mirror)}
    await sp._p.put_kv_data(PENDING_DELETE_INDEX_KV_KEY, blob)


def test_without_lock_counterfactual_reproduces_lost_update() -> None:
    """反事实（证明竞态真实存在，非空跑）：用与上面同款的显式事件控制摆出
    "先拍快照的一方反而后落盘"的精确交错——A 先拍到只含自己的快照后被卡住；
    B 后拍到含 A+B 的完整快照并【先】落盘；A 恢复后用它那份更旧、更小的快照
    覆盖落盘，B 的 entry 从持久化 KV 里消失。跳过锁时这个坑必然踩中。
    """

    async def go() -> None:
        p = _FakePlugin()
        sp = p._state_persistence

        a_snapshotted = asyncio.Event()
        release_a = asyncio.Event()

        async def register_a_no_lock() -> None:
            safe = sp._safe_session_key("sess:race-a")
            sp._pending_delete_mirror[safe] = {"epoch": 1, "ts": 0.0}
            blob = {"version": 1, "entries": dict(sp._pending_delete_mirror)}  # 只含 A
            a_snapshotted.set()
            await release_a.wait()  # 模拟 "A 的落盘 IO 比 B 慢"
            await p.put_kv_data(PENDING_DELETE_INDEX_KV_KEY, blob)

        async def register_b_no_lock() -> None:
            await a_snapshotted.wait()  # 确保 A 已经拍完快照（此刻只含 A）
            safe = sp._safe_session_key("sess:race-b")
            sp._pending_delete_mirror[safe] = {"epoch": 1, "ts": 0.0}
            blob = {"version": 1, "entries": dict(sp._pending_delete_mirror)}  # 含 A+B
            await p.put_kv_data(PENDING_DELETE_INDEX_KV_KEY, blob)  # 先落盘（完整快照）
            release_a.set()  # B 落盘完，才放行 A 用旧快照落盘（覆盖）

        await asyncio.gather(register_a_no_lock(), register_b_no_lock())

        blob = p._kv[PENDING_DELETE_INDEX_KV_KEY]
        assert "sess:race-b" not in blob["entries"], (
            "反事实未复现丢更新——交错时序未按预期发生，测试失真"
        )
        assert "sess:race-a" in blob["entries"]
        # in-process 镜像本身不丢（synchronous 赋值不涉及 await）——丢的只是这次
        # KV 落盘快照的完整性，这正是本卡片强调"全局锁保护的是持久化一致性"。
        assert "sess:race-b" in sp._pending_delete_mirror

    asyncio.run(go())


def test_delete_kv_failure_keeps_pending_delete_entry_no_resurrection() -> None:
    """PR-4 gate CRITICAL 回归：删除时 KV delete 瞬时故障（`_delete_kv_key_with_retry`
    fail-safe 不抛、归档幸存），删除 op 必须【保留】pending-delete entry 而【不】无条件
    摘除——否则 `_has_unresolved_pending_delete` 变 False、hydrate/load 继续把非空归档
    复活。这修的是"一次瞬时 KV 删除故障就复活已删/已 wipe 记忆"的红线洞。
    """

    async def go() -> None:
        shared_kv: dict = {}
        p = _FakePlugin(shared_kv)
        sp = p._state_persistence
        sk = "sess:del-fail"
        kv_key = sp.sylanne_memory_kv_key(sk)

        mem = p._memory_system_for_session(sk)
        mem._hydrated = True
        mem.write_summary(text="待删记忆", source_turns=1, session_key=sk)
        await sp.save_sylanne_memory_state(sk, mem)
        assert shared_kv[kv_key]["l1"]

        # 让 delete_kv_data 瞬时故障（一直抛）——put 仍正常（register/索引写不受影响）。
        async def failing_delete(key: str) -> None:
            raise RuntimeError("transient KV delete outage")

        p.delete_kv_data = failing_delete  # type: ignore[method-assign]

        await sp.delete_sylanne_memory_state(sk)

        # 归档没删掉（delete 全故障），entry 必须保留 → 仍算 pending → hydrate/load fail-closed。
        assert shared_kv.get(kv_key, {}).get("l1"), "归档应仍在（delete 故障未删掉）"
        assert sp._has_unresolved_pending_delete(sk), (
            "删除失败却摘掉了 pending-delete entry → hydrate/load 会复活已删记忆（CRITICAL 回归）"
        )

    asyncio.run(go())
