"""Phase 2B / PR-I：life-sim 路由（origin_session 迁移 + 亲密私聊单目标 + 群排除）测试。

覆盖 handoff §5.3：
- LifeEvent.origin_session roundtrip（_event_from_dict/_event_to_dict；旧档缺→""）
- _most_recent_intimate_host_key：排除群、仅亲密、无则 ""
- 群/陌生人不被选；共享 _most_recent_host_key 行为不变

直调真函数。
"""

from __future__ import annotations

from types import SimpleNamespace

from sylanne_alpha.life_simulation import LifeEvent, _event_from_dict, _event_to_dict
from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline


# ---- origin_session roundtrip ----

def test_origin_session_roundtrip():
    e = LifeEvent(text="t", mood="m", urgency=0.1, timestamp=1.0, origin_session="s1")
    assert _event_from_dict(_event_to_dict(e)).origin_session == "s1"


def test_origin_session_legacy_missing_defaults_empty():
    legacy = {"text": "t", "mood": "m", "urgency": 0.1, "timestamp": 1.0}
    assert _event_from_dict(legacy).origin_session == ""


# ---- _most_recent_intimate_host_key ----

class _Kernel:
    def __init__(self, now):
        self.last_event = {"now": now}


class _Host:
    def __init__(self, now):
        self.kernel = _Kernel(now)


class _Reg:
    def __init__(self):
        self._d = {}

    def get(self, k, default=None):
        return self._d.get(k, default)

    def set(self, k, v):
        self._d[k] = v


class _Hosts:
    def __init__(self, d):
        self._d = d

    def items(self):
        return self._d.items()

    def keys(self):
        return self._d.keys()

    def get(self, key, default=None):
        return self._d.get(key, default)

    def __len__(self):
        return len(self._d)


class _SF:
    def is_group_context_by_key(self, sk):
        return "Group" in sk or "group" in sk


class _Store:
    def __init__(self, hosts):
        self.hosts = _Hosts(hosts)
        self.relationship_register_state = _Reg()
        self.intimacy_override = _Reg()


class _Plugin:
    def __init__(self, hosts, owner="owner-1"):
        self._store = _Store(hosts)
        self._social_field = _SF()
        self.config = {"sylanne_alpha_owner_id": owner}

    def _session_key(self, event=None, session_key=""):
        return session_key


def _pipe(plugin):
    pipe = LLMRequestPipeline.__new__(LLMRequestPipeline)
    pipe._p = plugin
    return pipe


def _romantic(sender="owner-1"):
    return {"sender_id": sender, "romantic_conf": 0.8, "sample_count": 8}


def test_intimate_helper_picks_romantic_private():
    p = _Plugin({"priv:owner-1": _Host(100.0)})
    p._store.relationship_register_state.set("priv:owner-1", _romantic())
    assert _pipe(p)._most_recent_intimate_host_key() == "priv:owner-1"


def test_intimate_helper_excludes_group():
    p = _Plugin({"GroupMessage:g1:owner-1": _Host(200.0)})
    # 即便该群会话 register 是 romantic，群也不投
    p._store.relationship_register_state.set("GroupMessage:g1:owner-1", _romantic())
    assert _pipe(p)._most_recent_intimate_host_key() == ""


def test_intimate_helper_excludes_nonowner():
    p = _Plugin({"priv:attacker": _Host(100.0)})
    p._store.relationship_register_state.set("priv:attacker", _romantic("attacker"))
    assert _pipe(p)._most_recent_intimate_host_key() == ""


def test_intimate_helper_empty_when_none():
    p = _Plugin({"priv:owner-1": _Host(100.0)})  # 无 register → 非亲密
    assert _pipe(p)._most_recent_intimate_host_key() == ""


def test_scoped_intimate_helper_uses_exact_bound_owner_not_recent_host():
    p = _Plugin(
        {
            "priv:owner-1": _Host(50.0),
            "priv:newer-owner-1": _Host(300.0),
        }
    )
    p._scope_runtime_registry = object()
    p._bound_runtime = lambda: SimpleNamespace(
        scope=SimpleNamespace(storage_token="priv:owner-1")
    )
    p._store.relationship_register_state.set("priv:owner-1", _romantic())
    p._store.relationship_register_state.set("priv:newer-owner-1", _romantic())

    assert _pipe(p)._most_recent_intimate_host_key() == "priv:owner-1"

    p._store.relationship_register_state.set(
        "priv:owner-1",
        _romantic("not-owner"),
    )
    assert _pipe(p)._most_recent_intimate_host_key() == ""


# ---- T2-07②：_life_sim_outreach 回填 origin_session ----


class _PendingCtx:
    """极简 pending_outreach_context 替身：仅 _life_sim_outreach 用到的接口。"""

    def __init__(self):
        self.data: dict = {}

    def set(self, k, v):
        self.data[k] = v

    def get(self, k, default=None):
        return self.data.get(k, default)

    def has(self, k):
        return k in self.data

    def pop(self, k, default=None):
        return self.data.pop(k, default)


def test_life_sim_outreach_backfills_origin_session():
    """T2-07②：目标会话确定后应回填 LifeEvent.origin_session。

    此前该字段有定义（PR-I）但运行时从未被赋值——_audit_session_key 只能
    读到空串，一律落进 "_global" 桶，per-session audit 隔离形同虚设。
    """
    import asyncio

    from sylanne_alpha.life_simulation import LifeEvent, LifeSimulator

    p = _Plugin({"priv:owner-1": _Host(100.0)})
    p._store.relationship_register_state.set("priv:owner-1", _romantic())
    p._store.pending_outreach_context = _PendingCtx()
    p._background_tasks: list = []

    sim = LifeSimulator(config={})
    ev = LifeEvent(text="摸鱼中", mood="happy", urgency=0.1, timestamp=1.0)
    assert ev.origin_session == ""  # 未回填前的默认态
    sim.state.events = [ev]
    p._life_simulator = sim

    pipe = _pipe(p)
    intent = {"event_id": ev.event_id, "delivery_mode": "next_reply"}
    asyncio.run(pipe._life_sim_outreach("摸鱼中", "开心", intent))

    assert ev.origin_session == "priv:owner-1"
    # 清理内部起的 5 分钟 fallback 后台任务，避免测试遗留 pending task 警告。
    for t in list(p._background_tasks):
        t.cancel()


def test_life_sim_outreach_no_event_id_does_not_crash():
    """intent 缺 event_id（如两参旧回调路径）时不应报错，origin_session 逻辑直接跳过。"""
    import asyncio

    from sylanne_alpha.life_simulation import LifeSimulator

    p = _Plugin({"priv:owner-1": _Host(100.0)})
    p._store.relationship_register_state.set("priv:owner-1", _romantic())
    p._store.pending_outreach_context = _PendingCtx()
    p._background_tasks: list = []
    p._life_simulator = LifeSimulator(config={})

    pipe = _pipe(p)
    asyncio.run(pipe._life_sim_outreach("摸鱼中", "开心", None))
    for t in list(p._background_tasks):
        t.cancel()


def test_scoped_life_outreach_never_selects_a_recent_legacy_session():
    """A scoped runtime has no raw-address fallback path for life outreach."""
    import asyncio

    p = _Plugin({"priv:owner-1": _Host(100.0)})
    p._scope_runtime_registry = object()
    p._store.relationship_register_state.set("priv:owner-1", _romantic())
    p._store.pending_outreach_context = _PendingCtx()
    p._background_tasks = []
    pipe = _pipe(p)

    def _legacy_selection_forbidden():
        raise AssertionError("scoped outreach must not choose a recent raw session")

    pipe._most_recent_intimate_host_key = _legacy_selection_forbidden
    asyncio.run(pipe._life_sim_outreach("event", "calm", None))

    assert p._store.pending_outreach_context.data == {}
    assert p._background_tasks == []


# ---- T2-05 MAJOR-1：第二条可达 dispatch 路径（5min fallback 直发分支）也要
# 在真正发出后消费掉产生 user_followup 标签的那条待跟进线索 ----


def test_life_sim_outreach_consumes_followup_after_bridge_dispatch(monkeypatch) -> None:
    """MAJOR-1 修复覆盖的第二条路径：_life_sim_outreach 的 5min fallback 直发
    分支，bridge.dispatch 真正成功后也要消费掉产生 user_followup 标签的那条
    线索——否则它会一直"到期"，让接下来经这条路径触发的每一次主动消息都被
    重新贴上一模一样的标签文案（issue-43 同源的内容复读）。proactive_scheduler.
    request_dispatch 那条路径见 test_wave_l2_t2_05_t2_06_followup_ritual.py 的
    TestMajorOneConsumeOnDispatchWiring。

    只 stub 掉"是否真的连上了大饼"的机制细节（已有 test_proactive_bridge.py
    覆盖）与 5 分钟 asyncio.sleep；infer_reason_code / build_motivation_text /
    consume_followup_on_dispatch 全部走真实实现。
    """
    import asyncio
    import time

    from sylanne_alpha.life_simulation import LifeEvent, LifeSimulator
    from sylanne_alpha.memory_system import MemorySystem
    from sylanne_alpha.proactive_bridge import ProactiveBridge

    import sylanne_alpha.llm_request_pipeline as _pipe_mod

    async def _fast_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(_pipe_mod.asyncio, "sleep", _fast_sleep)

    mem = MemorySystem()
    mem.write_summary("我答应你明天一定去面试", source_turns=2, temperature=0.5)
    mem._pending_followups[0]["due_ts_estimate"] = time.time() - 10.0

    p = _Plugin({"priv:owner-1": _Host(100.0)})
    p._store.relationship_register_state.set("priv:owner-1", _romantic())
    p._store.pending_outreach_context = _PendingCtx()
    p._background_tasks: list = []
    p._memory_system_for_session = lambda sk: mem
    p.config["sylanne_alpha_proactive_bridge_enabled"] = True

    sim = LifeSimulator(config={})
    ev = LifeEvent(text="摸鱼中", mood="happy", urgency=0.1, timestamp=1.0)
    sim.state.events = [ev]
    p._life_simulator = sim

    bridge = ProactiveBridge(p)
    bridge.available = lambda: True  # type: ignore[method-assign]
    bridge.should_dispatch_now = lambda sk: (True, "ok")  # type: ignore[method-assign]

    async def _fake_dispatch(sk: str, motivation: str) -> dict:
        return {"dispatched": True, "reason": "ok"}

    bridge.dispatch = _fake_dispatch  # type: ignore[method-assign]
    p._proactive_bridge = bridge

    pipe = _pipe(p)
    intent = {"event_id": ev.event_id, "delivery_mode": "direct"}

    async def _drive() -> None:
        await pipe._life_sim_outreach("摸鱼中", "开心", intent)
        assert p._background_tasks, "应已排入 5min fallback 后台任务"
        await asyncio.gather(*p._background_tasks)

    asyncio.run(_drive())

    # 产生 user_followup 标签的那条线索应已被真正消费——不再等在列表里。
    assert mem._pending_followups == []
