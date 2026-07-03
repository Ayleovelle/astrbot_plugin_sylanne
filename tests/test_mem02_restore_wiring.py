"""MEM-02: 恢复接线修复 + hydration 守护——回归测试。

覆盖卡片里的三道闸门：
  (a) 首次懒创建 MemorySystem 时后台调度 KV 归档补水，非破坏性合并（不整层替换）。
  (b) 未补水的空 MemorySystem 不允许覆盖 KV 里已存在的非空归档。
  (c) memory_systems BoundedDict LRU 驱逐 / release_session 前先落盘。

以及冻结契约：_memory_system_for_session 签名/同步返回不变。
"""

from __future__ import annotations

import asyncio

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
    """反复 gather，直到没有新任务产生为止（补水任务本身不会再派生任务，一轮足够）。"""
    seen: set[int] = set()
    for _ in range(5):
        pending = [t for t in list(p._background_tasks) if id(t) not in seen]
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


def test_release_session_persists_before_pop() -> None:
    """_on_session_deleted 应在 release_session 硬删除前先落盘非空记忆。"""
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

    # _on_session_deleted 末尾会异步清空该 session 的全部 KV（AstrBot 会话真删除语义，
    # 比 LRU 驱逐更彻底），所以最终态里这个 key 会被删掉——但核心断言是"落盘确实发生
    # 过、且发生在删除之前"，而不是最终 KV 里还留着什么。
    put_indices = [
        i for i, (op, key) in enumerate(p.kv_call_log) if op == "put" and key == persisted_key
    ]
    delete_indices = [
        i for i, (op, key) in enumerate(p.kv_call_log) if op == "delete" and key == persisted_key
    ]
    assert put_indices, "release 前从未真正落盘——MEM-02③ 未生效"
    assert delete_indices, "会话删除的 KV 清理链路未触发（测试前提被破坏）"
    assert min(put_indices) < min(delete_indices), "落盘发生在清理删除之后，顺序错了"
    assert persisted_key not in shared_kv, "全会话删除的最终态应仍是 KV 被清空（未破坏既有清理语义）"


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


def test_hydrate_leaves_unrecognized_legacy_format_unhydrated() -> None:
    """遗留 SylanneMemoryState（records 字段，非 l1/l2/l3_nodes/l3_edges 新格式）
    补水时本方法不懂怎么合并——不能翻 _hydrated，否则下一次周期性 save 就会用
    活体的空对象把这份旧档覆盖掉。宁可让保护闸门一直挡着，直到活体自然积累出
    真实内容（这时 has_content 天然为真，闸门不再相关）。
    """
    shared_kv: dict = {}

    async def go() -> None:
        p = _FakePlugin(shared_kv)
        kv_key = "sylanne_memory_state:sess:legacy"
        shared_kv[kv_key] = {"records": [{"text": "旧版记忆", "depth": 0.9}]}

        mem = p._memory_system_for_session("sess:legacy")
        assert mem._hydrated is False
        await _drain_background_tasks(p)

        # 无法识别的旧格式：既没有被合并，也没有被翻 hydrated。
        assert mem._hydrated is False
        assert shared_kv[kv_key] == {"records": [{"text": "旧版记忆", "depth": 0.9}]}

        # 保护闸门仍然生效：这时如果有代码尝试用这个空活体去 save，应该被拦下。
        await p._state_persistence.save_sylanne_memory_state("sess:legacy", mem)
        assert shared_kv[kv_key] == {"records": [{"text": "旧版记忆", "depth": 0.9}]}, (
            "未识别的旧格式档案被空对象覆盖了"
        )

    asyncio.run(go())
