"""MEM-02: 恢复接线修复 + hydration 守护——回归测试。

覆盖卡片里的三道闸门：
  (a) 首次懒创建 MemorySystem 时后台调度 KV 归档补水，非破坏性合并（不整层替换）。
  (b) 未补水的空 MemorySystem 不允许覆盖 KV 里已存在的非空归档。
  (c) memory_systems BoundedDict LRU 驱逐前先落盘。

以及冻结契约：_memory_system_for_session 签名/同步返回不变。

MEM-03 PR-2 附加：_on_session_deleted 废除了驱逐路径以外那次"release_session 前
先落盘"（那是 F4 窗口的成因本身，见 test_release_session_no_persist_then_delete），
真删除类操作改经单写咽喉 + 化身栅栏，见文末 PR-2 小节。
"""

from __future__ import annotations

import asyncio
import json

from sylanne_alpha.memory_system import GraphNode, MemoryItem, MemorySystem
from sylanne_alpha.session_context import SessionContext
from sylanne_alpha.session_state_store import SessionStateStore
from sylanne_alpha.state_persistence import StatePersistence


class _FakePlugin:
    """最小化的插件替身：只暴露 MEM-02 涉及路径需要的属性/方法。"""

    def __init__(self, shared_kv: dict | None = None) -> None:
        self._store = SessionStateStore()
        self._background_tasks: list = []
        self.config: dict = {}
        self._config: dict = {}
        self._kv: dict = shared_kv if shared_kv is not None else {}
        self._amnesia_sessions: set = set()
        # 记录 put/delete 的调用顺序，用于验证"落盘先于清理/驱逐"这类时序断言。
        self.kv_call_log: list[tuple[str, str]] = []
        # 顺序与 main.py 一致：先 store，再 session_ctx / state_persistence。
        self._session_ctx = SessionContext(self)
        self._state_persistence = StatePersistence(self)

    async def get_kv_data(self, key: str, default=None):  # noqa: ANN001
        return self._kv.get(key, default)

    async def put_kv_data(self, key: str, value) -> None:  # noqa: ANN001
        self._kv[key] = value
        self.kv_call_log.append(("put", key))

    async def delete_kv_data(self, key: str) -> None:
        self._kv.pop(key, None)
        self.kv_call_log.append(("delete", key))

    # ---- main.py 上真实存在的委托方法（frozen 契约）----
    def _memory_system_for_session(self, session_key: str) -> MemorySystem:
        return self._session_ctx.memory_system_for_session(session_key)

    def _memory_system_has_content(self, memory_system) -> bool:  # noqa: ANN001
        return self._session_ctx.memory_system_has_content(memory_system)


async def _drain_background_tasks(p: _FakePlugin) -> None:
    """反复 gather，直到没有新任务产生为止（补水任务本身不会再派生任务，一轮足够）。

    MEM-03 PR-2：hydrate 调度改经单写咽喉提交（kind="hydrate"），不再落进
    `p._background_tasks`——它现在跑在 `StatePersistence._throat` 的 per-session
    drainer 任务里（`throat._drainers[session_key]`）。只 gather
    `p._background_tasks` 不再足以等到 hydrate 真正跑完，这里一并纳入当前存活的
    drainer 任务，否则测试会在 hydrate 真正合并归档前就走到断言。
    """
    seen: set[int] = set()
    for _ in range(10):
        pending = [t for t in list(p._background_tasks) if id(t) not in seen]
        throat = getattr(p._state_persistence, "_throat", None)
        if throat is not None:
            pending += [
                t for t in list(throat._drainers.values()) if id(t) not in seen
            ]
        if not pending:
            return
        for t in pending:
            seen.add(id(t))
        await asyncio.gather(*pending, return_exceptions=True)


def test_frozen_accessor_signature_unchanged() -> None:
    """_memory_system_for_session 必须保持同步签名，返回 MemorySystem 而非协程。"""
    p = _FakePlugin()
    result = p._memory_system_for_session("sess:sig")
    assert isinstance(result, MemorySystem)
    assert not asyncio.iscoroutine(result)


def test_restart_zeroing_regression() -> None:
    """restart-zeroing 回归：populate → save KV → 模拟重启（body 通道断链）→
    第一条消息不覆盖 KV → hydration 完成后 recall 能看到旧内容。
    """
    shared_kv: dict = {}

    async def phase1_populate_and_save() -> None:
        p1 = _FakePlugin(shared_kv)
        mem = p1._memory_system_for_session("sess:restart")
        mem.write_summary(
            text="用户喜欢猫，讨厌香菜",
            source_turns=3,
            temperature=0.6,
            session_key="sess:restart",
        )
        await p1._state_persistence.save_sylanne_memory_state("sess:restart", mem)

    asyncio.run(phase1_populate_and_save())

    kv_key = "sylanne_memory_state:sess:restart"
    assert kv_key in shared_kv
    assert shared_kv[kv_key]["l1"], "phase1 应已经把摘要落进 KV 归档"

    async def phase2_simulate_restart() -> None:
        # 新插件实例 = 模拟进程重启：内存态（_store）全新，但共享同一份 KV。
        p2 = _FakePlugin(shared_kv)
        mem2 = p2._memory_system_for_session("sess:restart")

        # 懒创建出来的是全新空对象，尚未补水。
        assert mem2._hydrated is False
        assert not p2._memory_system_has_content(mem2)

        # 补水后台任务此刻还没跑完——模拟"重启后收到的第一条消息"触发的周期性保存。
        await p2._state_persistence.save_sylanne_memory_state("sess:restart", mem2)

        # 核心断言：KV 里的真实归档不能被这次空写入抹掉。
        assert shared_kv[kv_key]["l1"], "空对象覆盖了 KV 里的非空归档——restart-zeroing 复现"

        # 让后台补水任务跑完。
        await _drain_background_tasks(p2)

        assert mem2._hydrated is True
        assert p2._memory_system_has_content(mem2)
        results = mem2.recall(
            query="猫", query_embedding=None, current_warmth=0.0, limit=5
        )
        assert any("猫" in r.text for r in results), "补水后 recall 应该能看到重启前的记忆"

    asyncio.run(phase2_simulate_restart())


def test_empty_over_nonempty_write_refused_directly() -> None:
    """更直接地单测闸门本身：未 hydrated 的空 MemorySystem 不能覆盖非空 KV。"""
    shared_kv: dict = {}

    async def go() -> None:
        p = _FakePlugin(shared_kv)
        seeded = MemorySystem()
        seeded.write_summary(text="种子记忆", source_turns=1, session_key="sess:guard")
        await p._state_persistence.save_sylanne_memory_state("sess:guard", seeded)
        assert shared_kv["sylanne_memory_state:sess:guard"]["l1"]

        empty = MemorySystem()
        assert empty._hydrated is False
        await p._state_persistence.save_sylanne_memory_state("sess:guard", empty)
        assert shared_kv["sylanne_memory_state:sess:guard"]["l1"], "闸门未生效：空对象覆盖了非空 KV"

        # 一旦标记为 hydrated（例如真的走过补水/恢复），允许写入（即便结果仍是空——
        # 这是"确实检查过、KV 也确实没有更多内容"或"用户显式清空"的场景）。
        empty._hydrated = True
        await p._state_persistence.save_sylanne_memory_state("sess:guard", empty)
        assert shared_kv["sylanne_memory_state:sess:guard"]["l1"] == [], (
            "已 hydrated 的写入应该被允许通过（不应该被闸门拦截）"
        )

    asyncio.run(go())


def test_evict_persists_via_bounded_dict_on_evict() -> None:
    """memory_systems 的 BoundedDict LRU 驱逐时应触发落盘（MEM-02③）。

    on_evict 回调内部用 safe_ensure_future 调度落盘任务——若没有正在运行的事件
    循环，safe_ensure_future 会直接关闭协程静默放弃（这是仓库既有的安全降级
    语义，非本卡片改动），所以驱逐动作本身也必须发生在 `asyncio.run` 内部，
    与真实运行时（chat 路径全程在事件循环里）一致。
    """
    shared_kv: dict = {}
    p = _FakePlugin(shared_kv)
    # 缩小容量以低成本触发驱逐，不必真塞 100 个 session。
    p._store.memory_systems._d.maxsize = 2

    async def go() -> None:
        mem_a = p._memory_system_for_session("sess:evict-a")
        mem_a.write_summary(text="A 的记忆", source_turns=1, session_key="sess:evict-a")
        mem_a._hydrated = True  # 视为已经补水过，专注测试驱逐落盘本身
        p._store.memory_systems.set("sess:evict-a", mem_a)

        p._memory_system_for_session("sess:evict-b")
        # 第三个 session 触发超容量驱逐，驱逐掉最久未用的 "sess:evict-a"。
        p._memory_system_for_session("sess:evict-c")

        assert not p._store.memory_systems.has("sess:evict-a"), "未真正被驱逐，测试前提不成立"
        await _drain_background_tasks(p)
        # 驱逐落盘不应该把被驱逐的对象重新塞回活体 store——否则"驱逐"名不副实。
        assert not p._store.memory_systems.has("sess:evict-a"), (
            "驱逐落盘任务把被驱逐的 session 复活回了 memory_systems"
        )

    asyncio.run(go())

    assert "sylanne_memory_state:sess:evict-a" in shared_kv, "驱逐时未落盘"
    assert shared_kv["sylanne_memory_state:sess:evict-a"]["l1"], "驱逐落盘内容为空/丢失"


def test_release_session_no_persist_then_delete() -> None:
    """MEM-03 PR-2：_on_session_deleted 废除了死的 persist-then-cleanup（F4 窗口的
    成因本身）——真删除的终态就是"已删除"，不再有"先落盘、再删除"这一步，也就不
    存在"删除后被自己的落盘复活"的时序窗口。验证：release_session 硬删除前的内容
    从未被写回 KV（没有任何 put），删除后记忆键确实清空。
    """
    shared_kv: dict = {}
    p = _FakePlugin(shared_kv)

    async def go() -> None:
        mem = p._memory_system_for_session("sess:release")
        mem.write_summary(text="release 前的记忆", source_turns=1, session_key="sess:release")
        mem._hydrated = True
        p._store.memory_systems.set("sess:release", mem)

        p._state_persistence._on_session_deleted("sess:release")
        await _drain_background_tasks(p)

    asyncio.run(go())

    persisted_key = "sylanne_memory_state:sess:release"
    assert not p._store.memory_systems.has("sess:release"), "release_session 未清理 memory_systems"

    put_indices = [
        i for i, (op, key) in enumerate(p.kv_call_log) if op == "put" and key == persisted_key
    ]
    delete_indices = [
        i for i, (op, key) in enumerate(p.kv_call_log) if op == "delete" and key == persisted_key
    ]
    assert not put_indices, (
        "废除的 persist-then-cleanup 复活了——真删除不该再对这个 key 有任何 put（F4 abolition 回归）"
    )
    assert delete_indices, "会话删除的 KV 清理链路未触发（测试前提被破坏）"
    assert persisted_key not in shared_kv, "全会话删除的最终态应是 KV 被清空"


def test_hydration_merge_prefers_newer_by_created_at() -> None:
    """merge_kv_archive: 同 id 冲突取 created_at/last_recalled_ts 更大（更新）的版本，
    KV 独有的条目正常并入。
    """
    live = MemorySystem()
    # 模拟重启后、补水任务跑完前，活体已经在这几个 tick 内写入的新版本（id 冲突项）。
    fresh_item = MemoryItem(
        id="shared-id",
        text="活体新版本（更新）",
        weight=1.0,
        temperature=0.5,
        age_ticks=0,
        embedding=None,
        created_at=2000.0,
        last_recalled_ts=2000.0,
    )
    live._l1.append(fresh_item)

    kv_data = {
        "version": "2.0.0",
        "tick": 42,
        "last_consolidation_ts": 0.0,
        "params": {},
        "l1": [
            {
                "id": "shared-id",
                "text": "KV 里的旧版本（应该被更新版本盖过）",
                "weight": 0.5,
                "temperature": 0.3,
                "age_ticks": 5,
                "embedding": None,
                "created_at": 100.0,
                "source_turns": 1,
                "confirmed": False,
                "recall_count": 0,
                "last_recalled_tick": 0,
                "rewrite_count": 0,
                "source": "dialogue",
                "importance": 0.5,
                "last_recalled_ts": 100.0,
                "actr_acc": 1.0,
                "confidence": 0.5,
                "privacy_level": "open",
                "life_event_id": "",
            },
            {
                "id": "kv-only-id",
                "text": "KV 独有的条目",
                "weight": 0.7,
                "temperature": 0.4,
                "age_ticks": 3,
                "embedding": None,
                "created_at": 50.0,
                "source_turns": 1,
                "confirmed": False,
                "recall_count": 0,
                "last_recalled_tick": 0,
                "rewrite_count": 0,
                "source": "dialogue",
                "importance": 0.5,
                "last_recalled_ts": 0.0,
                "actr_acc": 1.0,
                "confidence": 0.5,
                "privacy_level": "open",
                "life_event_id": "",
            },
        ],
        "l2": [],
        "l3_nodes": {},
        "l3_edges": [],
        "pending_followups": [],
    }

    live.merge_kv_archive(kv_data)

    by_id = {item.id: item for item in live._l1}
    assert set(by_id.keys()) == {"shared-id", "kv-only-id"}
    assert by_id["shared-id"].text == "活体新版本（更新）", "冲突 id 应保留更新鲜的版本"
    assert by_id["kv-only-id"].text == "KV 独有的条目"
    # tick 取二者较大值（KV 42 > 活体 0）。
    assert live._tick == 42


def test_hydration_merge_unions_l3_nodes() -> None:
    """L3 图节点按 id 并集，活体已有的 id 不被 KV 覆盖。"""
    live = MemorySystem()
    live._l3_nodes["n1"] = GraphNode(
        id="n1",
        label="活体节点",
        type="topic",
        temporal_type="episodic",
        emotion_weight=0.0,
        clarity=0.9,
    )

    kv_data = {
        "tick": 0,
        "last_consolidation_ts": 0.0,
        "l1": [],
        "l2": [],
        "l3_nodes": {
            "n1": {
                "id": "n1",
                "label": "KV 里的同名节点（不该覆盖活体）",
                "type": "topic",
                "temporal_type": "episodic",
                "emotion_weight": 0.0,
                "clarity": 0.1,
            },
            "n2": {
                "id": "n2",
                "label": "KV 独有节点",
                "type": "topic",
                "temporal_type": "episodic",
                "emotion_weight": 0.0,
                "clarity": 0.5,
            },
        },
        "l3_edges": [],
        "pending_followups": [],
    }

    live.merge_kv_archive(kv_data)

    assert live._l3_nodes["n1"].label == "活体节点"
    assert "n2" in live._l3_nodes
    assert live._l3_nodes["n2"].label == "KV 独有节点"


def test_hydrate_migrates_legacy_records_format() -> None:
    """FIX F（红队 L1-04/L2-4）：遗留 SylanneMemoryState（records 字段）补水时经
    normalize_memory_blob 识别 + 迁移读取，合并进活体并翻 _hydrated——而不是像修复
    前那样在聊天恢复路径永远不加载（旧行为把一份能迁移的老档判成"不认识"，只有
    开 WebUI 走 load_sylanne_memory_state 才会迁移，即"记忆时有时无"根因之一）。
    """
    shared_kv: dict = {}

    async def go() -> None:
        p = _FakePlugin(shared_kv)
        kv_key = "sylanne_memory_state:sess:legacy"
        shared_kv[kv_key] = {"records": [{"text": "旧版记忆", "depth": 0.9}]}

        mem = p._memory_system_for_session("sess:legacy")
        assert mem._hydrated is False
        await _drain_background_tasks(p)

        # 遗留 records 档被识别 + 迁移 + 合并进活体，_hydrated 翻 True。
        assert mem._hydrated is True
        all_texts = [it.text for it in list(mem._l1) + list(mem._l2)]
        assert "旧版记忆" in all_texts, f"遗留记忆未迁移进活体: {all_texts}"

    asyncio.run(go())


def test_hydrate_leaves_partial_unrecognized_blob_unhydrated() -> None:
    """FIX A/F：一份被 _kv_archive_has_content 判为"有内容"、但 normalize_memory_blob
    认不出的残缺/未知 blob（例如只有 l1 键、缺 l2/l3——真实 to_dict 永远四键齐全，
    这种只可能来自截断/损坏），补水刻意【不】翻 _hydrated，让 fail-closed 守卫继续
    挡着，绝不用空/零星活体覆盖一份读得到但解析不了的归档。
    """
    shared_kv: dict = {}

    async def go() -> None:
        p = _FakePlugin(shared_kv)
        kv_key = "sylanne_memory_state:sess:partial"
        # 只有 l1 键（缺 l2/l3_nodes/l3_edges）：_kv_archive_has_content=True，但
        # normalize 的 _MEMORY_SYSTEM_SHAPE_KEYS.issubset 需四键齐全 → 返回 None。
        original = {
            "l1": [
                {
                    "id": "x",
                    "text": "残档",
                    "weight": 1.0,
                    "temperature": 0.0,
                    "age_ticks": 0,
                    "created_at": 0.0,
                }
            ]
        }
        shared_kv[kv_key] = dict(original)

        mem = p._memory_system_for_session("sess:partial")
        await _drain_background_tasks(p)

        # 认不出的残缺档：不合并、不翻 hydrated。
        assert mem._hydrated is False
        # 守卫仍生效：空/未补水活体 save 不得覆盖这份读得到但不认识的归档。
        await p._state_persistence.save_sylanne_memory_state("sess:partial", mem)
        assert shared_kv[kv_key] == original, "未识别的残缺档被覆盖了"

    asyncio.run(go())


# ===========================================================================
# 合并前对抗闸（PR #55 gate）确认的 fail-open 洞 —— fail-closed 回归证明
# ===========================================================================


class _RaisingKVPlugin(_FakePlugin):
    """get_kv_data 可被切成"读即抛"，模拟瞬时 KV/DB 抖动。"""

    def __init__(self, shared_kv: dict | None = None) -> None:
        super().__init__(shared_kv)
        self.raise_reads = False

    async def get_kv_data(self, key: str, default=None):  # noqa: ANN001
        if self.raise_reads:
            raise RuntimeError("simulated transient KV read failure")
        return await super().get_kv_data(key, default)


class _CorruptReadbackPlugin(_FakePlugin):
    """备份 blob 写进去后，回读时返回损坏值（模拟存储层回读损坏）。"""

    async def get_kv_data(self, key: str, default=None):  # noqa: ANN001
        if key.startswith("sylanne_memory_state_backup_v2:") and key in self._kv:
            return "corrupted-not-a-dict"
        return await super().get_kv_data(key, default)


def test_hydrate_read_exception_leaves_unhydrated_and_guard_active() -> None:
    """FIX A / C（红队 L1-01/L2-1/L3-1，CRITICAL）：补水时 KV 读【抛异常】绝不能被
    当成"归档不存在"而翻 _hydrated——那会解除守卫、让下一次 save 用空活体覆盖真档，
    即重启清零 bug 原地复活。读失败必须保持 _hydrated=False（fail-closed）；且守卫
    自己的 KV 读若也抛异常，同样 fail-closed 拒绝落盘。
    """
    shared_kv: dict = {}
    kv_key = "sylanne_memory_state:sess:raise"

    async def seed() -> None:
        p0 = _FakePlugin(shared_kv)
        mem = p0._memory_system_for_session("sess:raise")
        mem.write_summary(
            text="重要记忆", source_turns=2, temperature=0.5, session_key="sess:raise"
        )
        await p0._state_persistence.save_sylanne_memory_state("sess:raise", mem)

    asyncio.run(seed())
    assert shared_kv[kv_key]["l1"]
    original = json.loads(json.dumps(shared_kv[kv_key]))

    async def go() -> None:
        p = _RaisingKVPlugin(shared_kv)
        mem = p._memory_system_for_session("sess:raise")  # 排补水任务
        p.raise_reads = True  # 补水读 + 守卫读都会抛
        await _drain_background_tasks(p)

        # FIX A：读失败 → 保持未补水（fail-closed）。
        assert mem._hydrated is False
        # FIX C：守卫读也抛 → fail-closed 拒绝 save → 真档一字不改。
        await p._state_persistence.save_sylanne_memory_state("sess:raise", mem)
        assert shared_kv[kv_key] == original, (
            "读异常被 fail-open 当成空档，真实归档被覆盖（重启清零复活）"
        )

    asyncio.run(go())


def test_nonempty_unhydrated_refused_not_just_empty() -> None:
    """FIX B（红队 L2-2，CRITICAL）：守卫此前嵌在 `if is_empty:` 里——一个非空但
    【未补水】的活体（补水前零星写入了几条新内容）会穿过守卫、用只含零星内容的
    to_dict 覆盖掉尚未合并的完整归档。守卫改为：未补水 + KV 有内容 → 一律拒绝，
    无论活体当前是空还是非空。
    """
    shared_kv: dict = {}
    kv_key = "sylanne_memory_state:sess:partial2"

    async def seed() -> None:
        p0 = _FakePlugin(shared_kv)
        mem = p0._memory_system_for_session("sess:partial2")
        for i in range(5):
            mem.write_summary(
                text=f"完整归档记忆{i}",
                source_turns=2,
                temperature=0.3,
                session_key="sess:partial2",
            )
        await p0._state_persistence.save_sylanne_memory_state("sess:partial2", mem)

    asyncio.run(seed())
    archive = json.loads(json.dumps(shared_kv[kv_key]))
    assert len(archive["l1"]) >= 1

    async def go() -> None:
        p = _FakePlugin(shared_kv)
        # 直接构造未补水非空活体（不经 accessor，不排补水任务）——隔离守卫行为。
        # 注：MEM-03 咽喉把 save 放进 drainer op（会 yield），若经 accessor 建 mem 则
        # 挂起的补水任务可能在 save op 验守卫前抢先补水，结果写出 archive∪零星（无损超集，
        # 不是 == archive）。那是竞态时序产物、两种赛果都无损；本测试专验守卫拒写这一支，
        # 故直接建 mem 令其确定性。
        mem = MemorySystem()
        mem.write_summary(
            text="补水前的零星新内容",
            source_turns=1,
            temperature=0.2,
            session_key="sess:partial2",
        )
        assert mem._hydrated is False
        assert p._memory_system_has_content(mem) is True  # 非空

        # save：旧代码 is_empty=False 会穿过守卫覆盖；新代码（未补水 + KV 有内容）拒绝。
        await p._state_persistence.save_sylanne_memory_state("sess:partial2", mem)
        assert shared_kv[kv_key] == archive, (
            "非空未补水活体覆盖了完整归档（FIX B 回归）"
        )

    asyncio.run(go())


def test_evicted_unhydrated_nonempty_does_not_clobber_archive() -> None:
    """FIX E（红队 L1-03）：一个非空但未补水的活体被 LRU 挤出时，_persist_memory_kv_only
    落盘路径同样受 fail-closed 守卫——不得用它（只含零星内容）覆盖尚未合并的完整归档。
    直接构造活体 + 触发驱逐回调，隔离补水任务，专测驱逐路径。
    """
    shared_kv: dict = {}
    kv_key = "sylanne_memory_state:sess:evict2"

    async def seed() -> None:
        p0 = _FakePlugin(shared_kv)
        mem = p0._memory_system_for_session("sess:evict2")
        for i in range(4):
            mem.write_summary(
                text=f"完整归档{i}",
                source_turns=2,
                temperature=0.3,
                session_key="sess:evict2",
            )
        await p0._state_persistence.save_sylanne_memory_state("sess:evict2", mem)

    asyncio.run(seed())
    archive = json.loads(json.dumps(shared_kv[kv_key]))

    async def go() -> None:
        p = _FakePlugin(shared_kv)
        mem = MemorySystem()  # 不经 accessor，不排补水任务
        mem.write_summary(
            text="补水前零星", source_turns=1, temperature=0.2, session_key="sess:evict2"
        )
        assert mem._hydrated is False and p._memory_system_has_content(mem)

        # 直接触发 LRU 驱逐回调（同步），内部 fire-and-forget 走 _persist_memory_kv_only。
        p._state_persistence._on_memory_system_evicted("sess:evict2", mem)
        await _drain_background_tasks(p)

        assert shared_kv[kv_key] == archive, (
            "驱逐落盘用非空未补水活体覆盖了完整归档（FIX E 回归）"
        )

    asyncio.run(go())


def test_corrupt_existing_backup_is_revalidated_not_trusted() -> None:
    """FIX D（红队 L1-02）：备份门 step-1 不能只凭 backup_key 存在就放行——一份损坏的
    既有备份（CRC 不符）必须被识别、删除、用现有真档重新备份，而不是被当成"已安全
    备份"从而在无可信备份下放行 v3 覆盖。
    """
    shared_kv: dict = {}
    kv_key = "sylanne_memory_state:sess:bk"
    backup_key = "sylanne_memory_state_backup_v2:sess:bk"
    shared_kv[kv_key] = {
        "version": "3.0.0",
        "l1": [
            {
                "id": "a",
                "text": "真档",
                "weight": 1.0,
                "temperature": 0.0,
                "age_ticks": 0,
                "created_at": 0.0,
            }
        ],
        "l2": [],
        "l3_nodes": {},
        "l3_edges": [],
    }
    # 损坏的既有备份：是 dict、有两个键，但 CRC 与 data 不符。
    shared_kv[backup_key] = {"data": {"garbage": True}, "_crc32": 12345}

    async def go() -> None:
        p = _FakePlugin(shared_kv)
        sp = p._state_persistence
        gate_ok = await sp._ensure_v2_backup_before_v3_write("sess:bk", kv_key, backup_key)
        assert gate_ok is True
        new_bk = shared_kv.get(backup_key)
        assert sp._backup_blob_is_valid(new_bk), "step-1 未重建可信备份"
        assert new_bk["data"] == shared_kv[kv_key], "重建备份没有快照现有真档"

    asyncio.run(go())


def test_backup_readback_corruption_fails_closed_and_deletes_poison() -> None:
    """FIX D（红队 L1-02）：备份写入后回读损坏（非 dict）→ fail-closed 返回 False
    （跳过 v3 写入），并【删除】这次写坏的备份 blob，否则下次 step-1 会把它当"已备份"
    放行，在无可信备份下覆盖旧数据。
    """
    shared_kv: dict = {}
    kv_key = "sylanne_memory_state:sess:bk2"
    backup_key = "sylanne_memory_state_backup_v2:sess:bk2"
    shared_kv[kv_key] = {
        "version": "3.0.0",
        "l1": [
            {
                "id": "a",
                "text": "真档",
                "weight": 1.0,
                "temperature": 0.0,
                "age_ticks": 0,
                "created_at": 0.0,
            }
        ],
        "l2": [],
        "l3_nodes": {},
        "l3_edges": [],
    }

    async def go() -> None:
        p = _CorruptReadbackPlugin(shared_kv)
        sp = p._state_persistence
        gate_ok = await sp._ensure_v2_backup_before_v3_write(
            "sess:bk2", kv_key, backup_key
        )
        assert gate_ok is False, "回读损坏必须 fail-closed"
        assert backup_key not in shared_kv, "写坏的备份没被删除，会毒化下次 step-1"

    asyncio.run(go())


# ===========================================================================
# 二轮对抗闸（re-gate）确认的相邻洞 —— 回归证明
# ===========================================================================


def test_hydrate_survives_dirty_created_at_no_persist_freeze() -> None:
    """FIX F1/F3（re-gate 现场复现的 MAJOR）：KV 归档里一条 item 的 created_at 是非
    数字字符串（损坏/异构写入），补水时经 from_dict/_merge_items_by_id 的 fail-closed
    清洗照常合并、翻 _hydrated——绝不崩溃 merge_kv_archive、绝不让补水任务猝死把
    session 永久冻结（守卫从此拒绝一切落盘、新记忆全丢且每次重启复现）。
    """
    shared_kv: dict = {}
    kv_key = "sylanne_memory_state:sess:dirty"
    shared_kv[kv_key] = {
        "version": "3.0.0",
        "l1": [
            {
                "id": "good",
                "text": "干净记忆",
                "weight": 1.0,
                "temperature": 0.0,
                "age_ticks": 0,
                "created_at": 100.0,
            }
        ],
        "l2": [
            {
                "id": "bad",
                "text": "脏 created_at 记忆",
                "weight": 1.0,
                "temperature": 0.0,
                "age_ticks": 0,
                "created_at": "2025-01-01T00:00:00",  # 非数字字符串
            }
        ],
        "l3_nodes": {},
        "l3_edges": [],
    }

    async def go() -> None:
        p = _FakePlugin(shared_kv)
        mem = p._memory_system_for_session("sess:dirty")
        await _drain_background_tasks(p)

        # 没崩溃、成功补水。
        assert mem._hydrated is True
        texts = [it.text for it in list(mem._l1) + list(mem._l2)]
        assert "干净记忆" in texts
        assert "脏 created_at 记忆" in texts  # 脏值被清洗成 0.0，条目照样进来

        # session 没被冻结：hydrated 后守卫放行，后续新记忆正常落盘。
        mem.write_summary(
            text="补水后新记忆", source_turns=1, temperature=0.1, session_key="sess:dirty"
        )
        await p._state_persistence.save_sylanne_memory_state("sess:dirty", mem)
        blob = shared_kv[kv_key]
        saved = [it.get("text") for it in blob.get("l1", []) + blob.get("l2", [])]
        assert "补水后新记忆" in saved, "hydrated session 落盘失败——疑似冻结未解除"

    asyncio.run(go())


def test_session_delete_purges_all_keys_no_resurrect() -> None:
    """FIX F4 + F5（delete 路径）：会话删除时 persist(窗口桥接) 与 cleanup(删除) 串行、
    删除在后——删除后记忆主键 + backup_v2 + quarantine 三键必须全空，不会被无序的
    persist 任务重新写回复活（F4），也不残留明文副本（F5）。
    """
    from sylanne_alpha.memory_legacy_formats import quarantine_kv_key

    shared_kv: dict = {}

    async def go() -> None:
        p = _FakePlugin(shared_kv)
        sp = p._state_persistence
        safe = sp._safe_session_key("sess:del")
        kv_key = sp.sylanne_memory_kv_key("sess:del")
        backup_key = sp.sylanne_memory_backup_v2_kv_key("sess:del")
        q_key = quarantine_kv_key(safe)

        mem = p._memory_system_for_session("sess:del")
        mem.write_summary(
            text="待删记忆", source_turns=2, temperature=0.3, session_key="sess:del"
        )
        await p._state_persistence.save_sylanne_memory_state("sess:del", mem)
        # 预置备份 + 隔离侧车（模拟迁移期留下的明文副本）。
        shared_kv[backup_key] = {"data": {"l1": [{"text": "旧明文"}]}, "_crc32": 1}
        shared_kv[q_key] = [{"raw": {"text": "隔离明文"}}]
        assert kv_key in shared_kv

        sp._on_session_deleted("sess:del")
        await _drain_background_tasks(p)

        assert kv_key not in shared_kv, "已删除会话的记忆键被 persist 复活了（F4 回归）"
        assert backup_key not in shared_kv, "删除后 backup_v2 明文副本仍在（F5 回归）"
        assert q_key not in shared_kv, "删除后 quarantine 明文副本仍在（F5 回归）"

    asyncio.run(go())


def test_meltdown_purges_backup_and_quarantine_keys() -> None:
    """FIX F5（meltdown 路径）：WebUI meltdown（"抹掉我的记忆"）必须连 backup_v2 /
    quarantine 两个新键一并清掉，否则清除后仍留完整明文副本（隐私/留存违约）。
    """
    from sylanne_alpha.memory_legacy_formats import quarantine_kv_key

    shared_kv: dict = {}

    async def go() -> None:
        p = _FakePlugin(shared_kv)
        sp = p._state_persistence
        safe = sp._safe_session_key("sess:melt")
        kv_key = sp.sylanne_memory_kv_key("sess:melt")
        backup_key = sp.sylanne_memory_backup_v2_kv_key("sess:melt")
        q_key = quarantine_kv_key(safe)

        shared_kv[kv_key] = {
            "version": "3.0.0",
            "l1": [],
            "l2": [],
            "l3_nodes": {},
            "l3_edges": [],
        }
        shared_kv[backup_key] = {"data": {"l1": [{"text": "旧明文"}]}, "_crc32": 1}
        shared_kv[q_key] = [{"raw": {"text": "隔离明文"}}]

        await sp.purge_session_after_meltdown("sess:melt")

        assert kv_key not in shared_kv
        assert backup_key not in shared_kv, "meltdown 后 backup_v2 明文副本仍在（F5 回归）"
        assert q_key not in shared_kv, "meltdown 后 quarantine 明文副本仍在（F5 回归）"

    asyncio.run(go())


def test_delete_memory_state_purges_all_three_keys() -> None:
    """FIX F5（第三条路径 /api/purge_data，gate3 finding）：delete_sylanne_memory_state
    是"删除某会话记忆"的规范原语，所有清除入口（含 WebUI /api/purge_data 显式抹除，
    它经 _delete_sylanne_memory_state 汇到本原语）都必须一次删掉记忆子系统的全部三个
    KV 键——primary / backup_v2 / quarantine。原语只删 primary 就会让 purge_data 端点
    留下明文副本。
    """
    from sylanne_alpha.memory_legacy_formats import quarantine_kv_key

    shared_kv: dict = {}

    async def go() -> None:
        p = _FakePlugin(shared_kv)
        sp = p._state_persistence
        safe = sp._safe_session_key("sess:purge")
        kv_key = sp.sylanne_memory_kv_key("sess:purge")
        backup_key = sp.sylanne_memory_backup_v2_kv_key("sess:purge")
        q_key = quarantine_kv_key(safe)
        shared_kv[kv_key] = {"version": "3.0.0", "l1": [{"text": "明文"}]}
        shared_kv[backup_key] = {"data": {"l1": [{"text": "备份明文"}]}, "_crc32": 1}
        shared_kv[q_key] = [{"raw": {"text": "隔离明文"}}]

        # purge_data 端点等价路径：_delete_sylanne_memory_state -> delete_sylanne_memory_state
        await sp.delete_sylanne_memory_state("sess:purge")

        assert kv_key not in shared_kv
        assert backup_key not in shared_kv, "规范原语漏删 backup_v2（purge_data 端点会泄漏）"
        assert q_key not in shared_kv, "规范原语漏删 quarantine（purge_data 端点会泄漏）"

    asyncio.run(go())


def test_explicit_wipe_latch_prevents_hydration_resurrection() -> None:
    """FIX F1/F2（完整性复审 gate 现场复现）：显式擦除（meltdown/purge_data）清空活体
    后必须置 _hydrated=True，否则懒创建时排的后台补水任务会在 handler 后续 await 期间、
    从【尚未删除】的 KV 旧档把记忆合并回活体，随后周期 save 又写回 KV——擦除被自己的
    补水复活。本测试按真实 handler 时序复现：懒创建(排补水)→清空+置hydrated→跑补水
    （此刻 KV 旧档仍在）→活体仍空→删 KV→周期 save 不复活。
    """
    shared_kv: dict = {}
    kv_key = "sylanne_memory_state:sess:wipe"

    async def seed() -> None:
        p0 = _FakePlugin(shared_kv)
        mem = p0._memory_system_for_session("sess:wipe")
        mem.write_summary(
            text="待擦除记忆", source_turns=2, temperature=0.4, session_key="sess:wipe"
        )
        await p0._state_persistence.save_sylanne_memory_state("sess:wipe", mem)

    asyncio.run(seed())
    assert shared_kv[kv_key]["l1"]

    async def go() -> None:
        p = _FakePlugin(shared_kv)
        # 擦除一个 not-loaded session：懒创建空活体 + 排后台补水任务。
        mem = p._memory_system_for_session("sess:wipe")
        assert mem._hydrated is False
        # 模拟擦除 handler：清空 + 置 _hydrated=True（F1/F2 latch）。
        mem._l1.clear()
        mem._l2.clear()
        mem._l3_nodes.clear()
        mem._l3_edges.clear()
        mem._tick = 0
        mem._hydrated = True
        # 跑补水任务——此刻 KV 旧档【仍在】（真实 handler 先 await 删别的键，记忆键最后删）。
        # 无 latch 时补水会读到旧档并合并回活体；有 latch 则顶部 _hydrated 检查直接放弃。
        await _drain_background_tasks(p)
        assert not p._memory_system_has_content(mem), "补水把已擦除记忆复活回活体（F1 回归）"

        # 之后才删记忆 KV 键。
        await p._state_persistence.delete_sylanne_memory_state("sess:wipe")
        # 再来一次周期 save：活体已空且 hydrated，写回的是空档，不复活内容。
        await p._state_persistence.save_sylanne_memory_state("sess:wipe", mem)
        assert not shared_kv.get(kv_key, {}).get("l1"), "擦除后 save 把归档复活了（F1 回归）"

    asyncio.run(go())


# ===========================================================================
# MEM-03 PR-1：单写咽喉根治 F2 备份门 TOCTOU —— 集成回归（含反事实，非空跑）
# ===========================================================================


class _SuspendingKVPlugin(_FakePlugin):
    """get/put 前 await sleep(0)，制造真实挂起点——让并发 op 的 read-check-write
    有机会交错（否则同步 fake KV 从不 yield，gather 的 save 会内联串行、测试失真）。
    """

    async def get_kv_data(self, key: str, default=None):  # noqa: ANN001
        await asyncio.sleep(0)
        return self._kv.get(key, default)

    async def put_kv_data(self, key: str, value) -> None:  # noqa: ANN001
        await asyncio.sleep(0)
        self._kv[key] = value
        self.kv_call_log.append(("put", key))


_F2_ARCHIVE = {
    "version": "3.0.0",
    "l1": [
        {
            "id": "old",
            "text": "旧档",
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


def _f2_make_state(txt: str) -> MemorySystem:
    m = MemorySystem()
    m._hydrated = True  # 已补水，守卫放行
    m.write_summary(text=txt, source_turns=1, temperature=0.1, session_key="sess:f2")
    return m


def test_throat_serializes_concurrent_v3_first_writes_f2() -> None:
    """MEM-03 PR-1（F2 根治）：同 session 两条并发 v3 首写经咽喉串行——备份门的
    read-check-write 不再交错，v2 备份恰写一次。用【会挂起】的 fake KV 制造真实交错，
    并配【反事实】（绕过咽喉直跑 _impl）证明：不串行化时备份门 TOCTOU 真会重写备份
    （≥2 次），咽喉才是修复者——本测试非空。
    """
    backup_key = "sylanne_memory_state_backup_v2:sess:f2"

    async def via_throat() -> list[str]:
        p = _SuspendingKVPlugin({"sylanne_memory_state:sess:f2": dict(_F2_ARCHIVE)})
        await asyncio.gather(
            p._state_persistence.save_sylanne_memory_state("sess:f2", _f2_make_state("A")),
            p._state_persistence.save_sylanne_memory_state("sess:f2", _f2_make_state("B")),
        )
        assert p._state_persistence._backup_blob_is_valid(p._kv[backup_key])
        assert p._kv[backup_key]["data"]["l1"][0]["text"] == "旧档"
        return [k for (op, k) in p.kv_call_log if op == "put" and k == backup_key]

    async def bypass_throat() -> list[str]:
        # 反事实：绕过咽喉，直接并发跑 _impl → 备份门无串行化，TOCTOU 显形。
        p = _SuspendingKVPlugin({"sylanne_memory_state:sess:f2": dict(_F2_ARCHIVE)})
        sp = p._state_persistence
        await asyncio.gather(
            sp._save_sylanne_memory_state_impl("sess:f2", _f2_make_state("A")),
            sp._save_sylanne_memory_state_impl("sess:f2", _f2_make_state("B")),
        )
        return [k for (op, k) in p.kv_call_log if op == "put" and k == backup_key]

    puts_throat = asyncio.run(via_throat())
    assert len(puts_throat) == 1, (
        f"咽喉未串行化备份门：v2 备份被写了 {len(puts_throat)} 次"
    )

    puts_bypass = asyncio.run(bypass_throat())
    assert len(puts_bypass) >= 2, (
        f"反事实未复现备份门 TOCTOU（应≥2 次备份写，说明挂起点未触发交错，测试失真）："
        f"{len(puts_bypass)}"
    )


# ===========================================================================
# MEM-03 PR-2：删除臂激活化身栅栏 —— 集成回归
# ===========================================================================


class _FakeKernelBody:
    def __init__(self) -> None:
        self.memory: dict = {}


class _FakeKernel:
    def __init__(self) -> None:
        self.body = _FakeKernelBody()


class _FakeRuntime:
    def __init__(self) -> None:
        self.save_calls = 0

    def save(self, kernel) -> None:  # noqa: ANN001
        self.save_calls += 1


class _FakeHost:
    def __init__(self) -> None:
        self.kernel = _FakeKernel()
        self.runtime = _FakeRuntime()


class _FakePluginWithHost(_FakePlugin):
    """扩展基础 fake plugin，加一个可返回 fake host 的 `_host()`——PR-2 的 kernel
    .alpha.json 文件 scrub（红队 must-fix 第 4 条复活臂）只有在 `_p._host()` 存在时
    才会真正执行，基础 `_FakePlugin` 没有这个方法（调用会被 scrub helper 的
    try/except 吞掉、静默 no-op），这里补上以便直接断言 scrub 生效。
    """

    def __init__(self, shared_kv: dict | None = None) -> None:
        super().__init__(shared_kv)
        self._fake_hosts: dict[str, _FakeHost] = {}

    def _host(self, session_key: str) -> _FakeHost:
        return self._fake_hosts.setdefault(session_key, _FakeHost())


def test_delete_recreate_f3_hydrate_rejected() -> None:
    """F3（hydrate 复活臂闭合）：memory_system_for_session 懒创建时排的 hydrate op
    （入队时纪元 0），若在真正执行前该 session 被删（bump 纪元），必须被验章拒绝——
    不能把已经被删掉的 v3 归档合并回活体。用真实时序复现"hydrate 已入队、尚未
    执行，此刻会话被删"的窗口：memory_system_for_session 只排队不 drain，delete
    在同一事件循环 tick 内同步 bump 纪元后才第一次 await，drain 在那次 await 才
    真正跑起来，此时 hydrate 与 delete 已经【同队列】按提交序等待执行。
    """
    kv_key = "sylanne_memory_state:sess:f3"
    backup_key = "sylanne_memory_state_backup_v2:sess:f3"
    from sylanne_alpha.memory_legacy_formats import quarantine_kv_key

    shared_kv: dict = {
        kv_key: {
            "version": "3.0.0",
            "l1": [
                {
                    "id": "doomed",
                    "text": "注定被删的记忆",
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
    }

    async def go() -> None:
        p = _FakePlugin(shared_kv)
        sp = p._state_persistence
        safe = sp._safe_session_key("sess:f3")
        q_key = quarantine_kv_key(safe)

        mem = p._memory_system_for_session("sess:f3")  # 排 hydrate（token=0），未 drain
        assert mem._hydrated is False

        # BEFORE draining：立即删除。delete_sylanne_memory_state 内部先同步
        # bump_epoch（纪元 0→1），再 submit delete op，然后才第一次 await——这次
        # await 才让 drainer 真正开始跑，此时队列里是 [hydrate(token=0), delete(豁免)]。
        await sp.delete_sylanne_memory_state("sess:f3")

        # 陈旧 hydrate 被拒：活体没有被合并、也没有被标记为已补水。
        assert mem._hydrated is False, "陈旧 hydrate 未被验章拒绝——F3 hydrate 臂复活"
        assert not p._memory_system_has_content(mem)
        assert sp._throat.reject_count >= 1

        # delete op 正常执行：三键全空。
        assert kv_key not in shared_kv
        assert backup_key not in shared_kv
        assert q_key not in shared_kv

    asyncio.run(go())


def test_stale_ref_save_rejected_blocker1() -> None:
    """BLOCKER-1：一个不再是 store 占位者的陈旧 MemorySystem 引用（例如某个更早、
    已被替换掉的并发请求持有的对象），在其所属 session 被删除（bump 纪元）之后，
    携带它的 save 必须被栅栏拒绝——不能借由这个陈旧对象把已删归档重新写回 KV。

    与 bump-and-restamp（占位者权威兜底）区分开：这里的 stale_ref 从头到尾都【不是】
    store 里的占位者（current_occupant 才是），所以不会被 bump 时的 restamp 捎带
    放行——这正是"删除后陈旧引用复活"（F3）本体，也是本卡片列出的 BLOCKER-1。
    """
    shared_kv: dict = {}

    async def go() -> None:
        p = _FakePlugin(shared_kv)
        sp = p._state_persistence

        stale_ref = MemorySystem()
        sp._throat.stamp(stale_ref, "sess:stale")  # 盖 epoch 0

        current_occupant = MemorySystem()
        p._store.memory_systems.set("sess:stale", current_occupant)
        sp._throat.stamp(current_occupant, "sess:stale")  # 同为 epoch 0

        # 删除：bump 纪元至 1。bump-and-restamp 只重新盖占位者（current_occupant）；
        # stale_ref 不是占位者，纹丝不动，仍钉在陈旧的 epoch 0。
        await sp.delete_sylanne_memory_state("sess:stale")
        assert current_occupant._incarnation_epoch == 1
        assert stale_ref._incarnation_epoch == 0

        stale_ref.write_summary(
            text="幽灵记忆（不该写回）", source_turns=1, session_key="sess:stale"
        )
        await sp.save_sylanne_memory_state("sess:stale", stale_ref)

        kv_key = "sylanne_memory_state:sess:stale"
        assert kv_key not in shared_kv, "陈旧引用的 save 未被栅栏拒绝——F3/BLOCKER-1 复活"
        assert sp._throat.reject_count >= 1

    asyncio.run(go())


def test_meltdown_then_chat_still_persists_restamp() -> None:
    """meltdown-then-chat 回归（bump-and-restamp 必要性）：meltdown 清空活体但复用
    同一对象继续当占位者（真实 WebUI handler 语义）——purge_session_after_meltdown
    的 bump 若只 bump 不 restamp，占位者会因为携带旧印章被永久拒写，meltdown 后
    继续聊天产生的新记忆会【永远】落不了盘，比记忆复活更糟。这里验证 restamp 确实
    生效：meltdown 之后，同一对象 write_summary + save 必须成功持久化。
    """
    shared_kv: dict = {}

    async def go() -> None:
        p = _FakePlugin(shared_kv)
        sp = p._state_persistence
        kv_key = "sylanne_memory_state:sess:melt2"

        mem = p._memory_system_for_session("sess:melt2")
        mem.write_summary(
            text="即将被抹掉的记忆", source_turns=1, session_key="sess:melt2"
        )
        mem._hydrated = True
        await sp.save_sylanne_memory_state("sess:melt2", mem)
        assert shared_kv[kv_key]["l1"]

        # 真实 meltdown handler 语义：原地清空但复用同一个对象继续当占位者。
        mem._l1.clear()
        mem._l2.clear()
        mem._l3_nodes.clear()
        mem._l3_edges.clear()
        mem._tick = 0
        mem._hydrated = True
        await sp.purge_session_after_meltdown("sess:melt2")
        assert kv_key not in shared_kv
        # bump-and-restamp 生效：占位者印章已追平最新纪元。
        assert mem._incarnation_epoch == sp._throat.current_epoch("sess:melt2")

        # 继续聊天：同一对象写入新内容，必须仍能落盘。
        mem.write_summary(
            text="meltdown 后的新记忆", source_turns=1, session_key="sess:melt2"
        )
        await sp.save_sylanne_memory_state("sess:melt2", mem)
        assert shared_kv.get(kv_key, {}).get("l1"), (
            "meltdown 的 bump 只 bump 不 restamp——新记忆被永久拒写（比复活更糟的回归）"
        )

    asyncio.run(go())


def test_alpha_json_scrub_on_session_delete() -> None:
    """红队 must-fix（第 4 条复活臂）：_on_session_deleted 必须清空 kernel 文件里的
    body.memory['_memory_system'] + traces——否则 WebUI overview salvage（
    load_sylanne_memory_state 第 5 级 .alpha.json 直读回退）会把这份文件残留读回来，
    再被下一次周期性 save 写回 KV，等于"删除"从未真正发生。
    """
    p = _FakePluginWithHost()

    async def go() -> None:
        host = p._host("sess:scrub")
        host.kernel.body.memory["_memory_system"] = {
            "l1": [{"id": "x", "text": "残留明文"}]
        }
        host.kernel.body.memory["traces"] = ["旧 trace"]

        p._state_persistence._on_session_deleted("sess:scrub")
        await _drain_background_tasks(p)

        assert "_memory_system" not in host.kernel.body.memory, (
            "kernel .alpha.json 文件里的 _memory_system 残留未被 scrub"
        )
        assert host.kernel.body.memory.get("traces") == []
        assert host.runtime.save_calls >= 1, "scrub 后没有把清空结果写回 kernel 文件"

    asyncio.run(go())


def test_v2core_domains_purged_on_plain_session_delete() -> None:
    """红队 MINOR-3：sylanne_v2core_domains:{safe}（reconsolidation overlay，legacy
    键含原始记忆 TEXT）在 meltdown 路径早已清（purge_session_after_meltdown），但
    普通会话删除（_on_session_deleted）此前漏删，留下明文残留。PR-2 补上。
    """
    shared_kv: dict = {}
    p = _FakePlugin(shared_kv)
    safe = p._state_persistence._safe_session_key("sess:domains")
    domains_key = f"sylanne_v2core_domains:{safe}"
    shared_kv[domains_key] = {"legacy": {"text": "reconsolidation 明文"}}

    async def go() -> None:
        p._state_persistence._on_session_deleted("sess:domains")
        await _drain_background_tasks(p)

    asyncio.run(go())

    assert domains_key not in shared_kv, (
        "普通会话删除未清 sylanne_v2core_domains 侧车键（红队 MINOR-3 回归）"
    )


def test_purge_after_meltdown_no_self_deadlock() -> None:
    """purge_session_after_meltdown 的复合 op 必须内部调用
    `_delete_sylanne_memory_state_impl`（而非公开壳 `delete_sylanne_memory_state`）——
    否则壳会对同一 session 队列再 submit+await，命中咽喉的 task-identity re-entrancy
    断言（立即 RuntimeError，单 drainer 等自己完成本就是死锁），purge 就永远无法
    正常完成。用超时包一层，回归时快速失败而不是挂起整条测试流水线。
    """
    shared_kv: dict = {}

    async def go() -> None:
        p = _FakePlugin(shared_kv)
        sp = p._state_persistence
        kv_key = "sylanne_memory_state:sess:nodeadlock"

        mem = p._memory_system_for_session("sess:nodeadlock")
        mem.write_summary(
            text="待清除", source_turns=1, session_key="sess:nodeadlock"
        )
        mem._hydrated = True
        await sp.save_sylanne_memory_state("sess:nodeadlock", mem)
        assert shared_kv[kv_key]["l1"]

        await asyncio.wait_for(
            sp.purge_session_after_meltdown("sess:nodeadlock"), timeout=2.0
        )
        assert kv_key not in shared_kv

    asyncio.run(go())


def test_delete_kv_key_with_retry_recovers_from_transient_failure() -> None:
    """有界重试本体：一个键的删除前两次抛异常、第三次成功——必须最终被删掉（而不是
    第一次失败就放弃）。同时验证耗尽重试次数仍不抛出（fail-safe，不中断整个 op）。
    """
    shared_kv = {"k1": 1, "k2": 2}

    class _FlakyPlugin(_FakePlugin):
        def __init__(self, shared_kv: dict) -> None:
            super().__init__(shared_kv)
            self.fail_left = {"k1": 2}  # k1 前两次失败，第三次成功

        async def delete_kv_data(self, key: str) -> None:  # noqa: ANN001
            left = self.fail_left.get(key, 0)
            if left > 0:
                self.fail_left[key] = left - 1
                raise RuntimeError("simulated transient delete failure")
            await super().delete_kv_data(key)

    async def go() -> None:
        p = _FlakyPlugin(shared_kv)
        sp = p._state_persistence

        await sp._delete_kv_key_with_retry("k1")
        assert "k1" not in shared_kv, "有界重试未在耗尽前的成功尝试上恢复删除"

        # k2 恒失败（永远不会调用 super()），耗尽 3 次重试后必须放弃但不抛异常。
        async def always_fail(key: str) -> None:  # noqa: ANN001
            raise RuntimeError("always fails")

        p.delete_kv_data = always_fail  # type: ignore[assignment]
        await sp._delete_kv_key_with_retry("k2")  # 不应抛异常
        assert "k2" in shared_kv, "k2 应仍在（重试耗尽后放弃，但 fail-safe 不代表能删掉）"

    asyncio.run(go())


def test_hydrate_schedule_reaches_throat_from_worker_thread() -> None:
    """design §8 PR-2 行（"stdlib 线程 meltdown 真达咽喉执行"）：真实 WebUI meltdown
    handler（webui_server.py 的 stdlib ThreadingHTTPServer 工作线程）会在【无
    running loop】的线程里同步调用 `_memory_system_for_session(session)`——这个
    accessor 内部现在经 `throat.submit(kind="hydrate")` 调度补水（PR-2 前是
    `safe_ensure_future`，在无 running loop 的线程里会静默 `coro.close()` 丢弃，
    从未真正补过水）。验证：off-loop 调用确实把 hydrate op 送进了绑定 loop 的
    咽喉队列并真正执行到底，而不是静默丢弃。
    """
    import threading
    import time

    kv_key = "sylanne_memory_state:sess:thread"
    shared_kv: dict = {
        kv_key: {
            "version": "3.0.0",
            "l1": [
                {
                    "id": "a",
                    "text": "线程补水记忆",
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
    }
    p = _FakePlugin(shared_kv)
    result: dict = {}

    async def go() -> None:
        loop = asyncio.get_running_loop()
        p._state_persistence._throat.bind_loop(loop)

        def worker() -> None:
            # 无 running loop 的线程——真实 webui_server.py meltdown handler 的调用
            # 现场（见该文件 ~2290-2294 行 mem_getter(session) 的同步调用）。
            result["mem"] = p._memory_system_for_session("sess:thread")

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        # 轮询等待：call_soon_threadsafe 排的 _enqueue 回调、以及随后的 drainer 任务
        # 都要等本 loop 有机会跑才会执行，不能假设 t.join() 一返回就已经跑完。
        deadline = time.monotonic() + 3.0
        while not result.get("mem")._hydrated:
            if time.monotonic() > deadline:
                raise AssertionError("off-loop hydrate 在超时内未完成——咽喉未真正执行")
            await asyncio.sleep(0.01)

    asyncio.run(go())

    mem = result["mem"]
    assert mem._hydrated is True, "off-loop 调用未真正把 hydrate 送进咽喉执行"
    all_texts = [it.text for it in list(mem._l1) + list(mem._l2)]
    assert "线程补水记忆" in all_texts, f"补水内容缺失: {all_texts}"


def test_session_delete_fences_pipeline_held_occupant_ref_blocker1() -> None:
    """PR-2 gate 修正 / BLOCKER-1 真场景：pipeline 跨 LLM await 攥着【当前占位者】引用，
    期间会话被 AstrBot 删除。delete 的 bump 必须在 release_session【之后】（占位者已
    pop、occupant=None、不 restamp），使那个旧占位者引用的后续 save 被化身栅栏拒绝——
    已删记忆不复活。若 bump 在 release 之前（会把待删占位者 restamp 成新纪元），其 save
    反被放行 = 复活，本测试拦回。
    """
    shared_kv: dict = {}
    kv_key = "sylanne_memory_state:sess:del-f3"

    async def go() -> None:
        p = _FakePlugin(shared_kv)
        ref = p._memory_system_for_session("sess:del-f3")  # 建占位者，印章 epoch 0
        ref._hydrated = True
        ref.write_summary(
            text="待删记忆", source_turns=2, temperature=0.3, session_key="sess:del-f3"
        )
        await p._state_persistence.save_sylanne_memory_state("sess:del-f3", ref)
        assert kv_key in shared_kv and shared_kv[kv_key]["l1"]

        throat = p._state_persistence._throat
        rc0 = throat.reject_count

        # AstrBot 删除会话（同步回调）：release 弹出占位者 → bump(occupant=None) → 删 op。
        p._state_persistence._on_session_deleted("sess:del-f3")
        await _drain_background_tasks(p)
        assert kv_key not in shared_kv, "删除 op 未删掉记忆键"

        # pipeline 用它一直攥着的旧占位者引用落盘 → 必须被栅栏拒绝，不得复活。
        await p._state_persistence.save_sylanne_memory_state("sess:del-f3", ref)
        await _drain_background_tasks(p)
        assert kv_key not in shared_kv, (
            "已删记忆被 stale 占位者引用的 save 复活了（BLOCKER-1 / bump-after-release 回归）"
        )
        assert throat.reject_count > rc0, "化身栅栏未拒绝 stale-ref save（fence 未生效）"

    asyncio.run(go())
