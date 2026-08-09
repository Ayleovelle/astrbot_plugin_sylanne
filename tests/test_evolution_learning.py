"""CP8-P4-C 自我进化层单元测试：档案护栏 + 反应式学习。
CP8-P4-E 追加：reflection_bias 钳位/叠加 + ReflectionEngine 三道闸 + 唤醒即弃。"""

import asyncio

from sylanne_alpha.agents.learning import (
    AgentEvolutionArchive,
    EvolutionStore,
    ReflectionEngine,
    ReflexLearner,
)


# ---------------------------------------------------------------------------
# AgentEvolutionArchive: 护栏（钳位/回归/隔离/复位/持久化）
# ---------------------------------------------------------------------------
def test_delta_clamped_within_cap():
    arc = AgentEvolutionArchive("memory")
    # 持续正 reward，delta 不应超过 cap
    for _ in range(500):
        arc.update("intimacy", 1.0, eta=0.01, delta_cap=0.15)
    assert arc.get_delta("intimacy") <= 0.15 + 1e-9


def test_regress_to_baseline_when_no_signal():
    arc = AgentEvolutionArchive("memory")
    # 先推高
    for _ in range(50):
        arc.update("intimacy", 1.0, eta=0.01)
    high = arc.get_delta("intimacy")
    assert high > 0
    # 之后无信号（死区内），回归基线应让 delta 缩小
    for _ in range(200):
        arc.update("intimacy", 0.0, regress=0.05)
    assert arc.get_delta("intimacy") < high * 0.5  # 显著回缩


def test_deadzone_blocks_noise():
    arc = AgentEvolutionArchive("x")
    # reward 在死区内，delta 不应增长（只回归）
    for _ in range(100):
        arc.update("k", 0.02, deadzone=0.05)
    assert abs(arc.get_delta("k")) < 1e-6


def test_factory_reset():
    arc = AgentEvolutionArchive("x")
    for _ in range(50):
        arc.update("k", 1.0, eta=0.01)
    assert arc.get_delta("k") > 0
    arc.reset_to_factory()
    assert arc.get_delta("k") == 0.0


def test_persistence_roundtrip():
    arc = AgentEvolutionArchive("emotion")
    for _ in range(30):
        arc.update("boundary", 1.0, eta=0.01)
    arc.record_outcome(0.8)
    d = arc.to_dict()
    arc2 = AgentEvolutionArchive.from_dict(d)
    assert abs(arc2.get_delta("boundary") - arc.get_delta("boundary")) < 1e-5
    assert abs(arc2.outcome_ema - arc.outcome_ema) < 1e-5


def test_negative_reward_pushes_down():
    arc = AgentEvolutionArchive("proactive")
    for _ in range(50):
        arc.update("openness", -1.0, eta=0.01)
    assert arc.get_delta("openness") < 0  # 被忽略→门槛下调方向


# ---------------------------------------------------------------------------
# ReflexLearner: reward 合成（防 Goodhart：行为强、自评弱）
# ---------------------------------------------------------------------------
def test_reward_behavior_dominates_self():
    rl = ReflexLearner(plugin=None)
    # 行为正（被采纳）但自评低 → reward 仍偏正（行为权重 0.7 > 自评 0.3）
    r = rl.compute_reward(behavior=1.0, self_quality=0.0)
    assert r > 0  # 0.7*1 + 0.3*(-1) = 0.4


def test_reward_self_only_when_no_behavior():
    rl = ReflexLearner(plugin=None)
    r = rl.compute_reward(behavior=0.0, self_quality=1.0)
    assert abs(r - 0.3) < 1e-9  # 仅自评：0.3*(2*1-1)=0.3


def test_reward_clamped():
    rl = ReflexLearner(plugin=None)
    r = rl.compute_reward(behavior=1.0, self_quality=1.0)
    assert r <= 1.0


def test_store_learn_and_get_delta():
    rl = ReflexLearner(plugin=None)
    store = EvolutionStore()
    for _ in range(50):
        rl.learn(store, "proactive", "open_threshold", behavior=-1.0, self_quality=0.2)
    # 持续负反馈 → delta 往负走（学会更保守）
    assert store.get_delta("proactive", "open_threshold") < 0


def test_store_persistence_roundtrip():
    store = EvolutionStore()
    rl = ReflexLearner(plugin=None)
    for _ in range(20):
        rl.learn(store, "memory", "intimacy", behavior=1.0, self_quality=0.8)
    d = store.to_dict()
    store2 = EvolutionStore()
    store2.load_dict(d)
    assert abs(store2.get_delta("memory", "intimacy") - store.get_delta("memory", "intimacy")) < 1e-5


# ---------------------------------------------------------------------------
# CP8-P4-E: reflection_bias 钳位 + 与 reflex delta 叠加 + 持久化
# ---------------------------------------------------------------------------
def test_reflection_bias_clamped_more_conservative():
    arc = AgentEvolutionArchive("memory")
    # 反复朝大目标插值，reflection_bias 不应超过 reflection_cap(0.10)
    for _ in range(50):
        arc.apply_reflection("intimacy", 0.5)
    snap = arc.param_snapshot()["intimacy"]
    assert snap["reflection_bias"] <= 0.10 + 1e-9


def test_get_delta_sums_reflex_and_reflection():
    # 用小幅度，确保两路之和不触发总 cap(0.20)，验证纯叠加语义
    arc = AgentEvolutionArchive("memory")
    for _ in range(5):
        arc.update("k", 1.0, eta=0.01)       # 推高 reflex delta（约 0.05）
    for _ in range(20):
        arc.apply_reflection("k", 0.04)      # 叠加 reflection_bias（约 0.04）
    total = arc.get_delta("k")
    snap = arc.param_snapshot()["k"]
    # snap 值经 round(...,4)，total 未舍入，故用 1e-3 容差比对"是否就是两路之和"
    assert abs(total - (snap["delta"] + snap["reflection_bias"])) < 1e-3
    assert total > snap["delta"]  # 反思偏置确实叠加上去了


def test_get_delta_total_cap_clamps_sum():
    # CP8-P6：两路同向叠加超总 cap(0.20) 时被钳住
    arc = AgentEvolutionArchive("memory")
    for _ in range(500):
        arc.update("k", 1.0, eta=0.01)       # delta 顶到 0.15
    for _ in range(50):
        arc.apply_reflection("k", 0.5)       # reflection_bias 顶到 0.10
    total = arc.get_delta("k")
    assert total <= 0.20 + 1e-9              # 0.15+0.10=0.25 被总 cap 钳到 0.20


def test_reflection_persistence_roundtrip():
    arc = AgentEvolutionArchive("proactive")
    for _ in range(20):
        arc.apply_reflection("open_threshold", -0.08)
    d = arc.to_dict()
    arc2 = AgentEvolutionArchive.from_dict(d)
    s1 = arc.param_snapshot()["open_threshold"]["reflection_bias"]
    s2 = arc2.param_snapshot()["open_threshold"]["reflection_bias"]
    assert abs(s1 - s2) < 1e-5


def test_factory_reset_clears_reflection_bias():
    arc = AgentEvolutionArchive("x")
    for _ in range(20):
        arc.apply_reflection("k", 0.1)
    assert arc.param_snapshot()["k"]["reflection_bias"] != 0.0
    arc.reset_to_factory()
    assert arc.get_delta("k") == 0.0


# ---------------------------------------------------------------------------
# CP8-P4-E: ReflectionEngine 三道闸 + 锁舞唤醒即弃
# ---------------------------------------------------------------------------
class _FakeStore:
    """带 last_user_message_time 的 _store 替身。"""

    def __init__(self):
        self.last_user_message_time = {}


class _FakePlugin:
    def __init__(self, llm_reply=""):
        self._store = _FakeStore()
        self._llm_reply = llm_reply
        self._locks = {}
        self.config = {"sylanne_alpha_reflection_daily_budget": 2}
        self.llm_calls = 0

    def _session_lock(self, sk):
        lock = self._locks.get(sk)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[sk] = lock
        return lock

    async def _main_assessor_llm_call(self, prompt):
        self.llm_calls += 1
        return self._llm_reply


class _FakeSelfCore:
    AWAKE = "awake"
    DROWSY = "drowsy"
    RETIRED = "retired"
    _LEARNABLE = (("memory", "intimacy_threshold"), ("proactive", "open_threshold"))

    def __init__(self, plugin, phase="drowsy"):
        self._p = plugin
        self._evo_stores = {}
        self._phase = phase
        self._reflection_meta = {}

    def reflection_meta(self, sk):
        m = self._reflection_meta.get(sk)
        if m is None:
            m = {}
            self._reflection_meta[sk] = m
        return m

    def autonomy_phase(self, sk, now):
        return self._phase

    def _store(self, sk):
        store = self._evo_stores.get(sk)
        if store is None:
            store = EvolutionStore()
            self._evo_stores[sk] = store
        return store


def _seed_samples(store, n=8):
    for i in range(n):
        store.record_decision(self_quality=0.2, behavior=-1.0, now=1000.0 + i)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_reflection_applies_bias_on_valid_json():
    reply = '{"deltas": {"memory.intimacy_threshold": -0.05}, "summary": "更主动"}'
    p = _FakePlugin(llm_reply=reply)
    sc = _FakeSelfCore(p, phase="drowsy")
    sc._store("s1")
    _seed_samples(sc._evo_stores["s1"])
    eng = ReflectionEngine(p, sc)
    ok = _run(eng.maybe_reflect("s1", now=2000.0))
    assert ok is True
    # reflection_bias 已沉淀（朝 -0.05 插值一步）
    snap = sc._evo_stores["s1"].archive("memory").param_snapshot()
    assert snap["intimacy_threshold"]["reflection_bias"] < 0


def test_reflection_budget_gate_blocks_third_call():
    reply = '{"deltas": {"memory.intimacy_threshold": -0.03}}'
    p = _FakePlugin(llm_reply=reply)
    sc = _FakeSelfCore(p, phase="drowsy")
    sc._store("s1")
    _seed_samples(sc._evo_stores["s1"])
    eng = ReflectionEngine(p, sc)
    eng._min_interval = 0.0  # 关掉间隔闸，单测预算闸
    assert _run(eng.maybe_reflect("s1", now=2000.0)) is True
    assert _run(eng.maybe_reflect("s1", now=2001.0)) is True
    # 第三次：当日预算(2)已用尽 → 跳过，不再调 LLM
    calls_before = p.llm_calls
    assert _run(eng.maybe_reflect("s1", now=2002.0)) is False
    assert p.llm_calls == calls_before


def test_reflection_discarded_when_woke_up():
    """锁外 LLM 跑完后会话已被唤醒（相位非 DROWSY）→ 丢弃影子结果不提交。"""
    reply = '{"deltas": {"memory.intimacy_threshold": -0.05}}'
    p = _FakePlugin(llm_reply=reply)
    sc = _FakeSelfCore(p, phase="drowsy")
    sc._store("s1")
    _seed_samples(sc._evo_stores["s1"])
    eng = ReflectionEngine(p, sc)

    # 包裹 LLM 调用：返回前把相位切到 AWAKE（模拟唤醒）
    orig = p._main_assessor_llm_call

    async def _wake_during(prompt):
        sc._phase = "awake"
        return await orig(prompt)

    p._main_assessor_llm_call = _wake_during
    ok = _run(eng.maybe_reflect("s1", now=2000.0))
    assert ok is False
    # 偏置未提交
    snap = sc._evo_stores["s1"].archive("memory").param_snapshot()
    assert snap.get("intimacy_threshold", {}).get("reflection_bias", 0.0) == 0.0
    # 但 LLM 已烧 + 预算已扣（token 已花费不可退，丢弃也计入预算闸）
    assert p.llm_calls == 1
    assert eng._has_budget("s1", 2000.0) is True   # 还剩 1 次（budget=2）
    eng._min_interval = 0.0
    _run(eng.maybe_reflect("s1", now=2001.0))       # 再触发一次（仍会丢弃）
    assert eng._has_budget("s1", 2001.0) is False   # 预算耗尽，第三次会被闸住


def test_reflection_discard_still_blocks_after_budget():
    """连续唤醒丢弃也要耗尽预算：调 LLM 前扣预算，防 token 悖论绕过。"""
    reply = '{"deltas": {"memory.intimacy_threshold": -0.05}}'
    p = _FakePlugin(llm_reply=reply)
    sc = _FakeSelfCore(p, phase="drowsy")
    sc._store("s1")
    _seed_samples(sc._evo_stores["s1"])
    eng = ReflectionEngine(p, sc)
    eng._min_interval = 0.0

    orig = p._main_assessor_llm_call

    async def _wake_during(prompt):
        sc._phase = "awake"
        out = await orig(prompt)
        sc._phase = "drowsy"  # 复位，下次还能触发
        return out

    p._main_assessor_llm_call = _wake_during
    _run(eng.maybe_reflect("s1", now=2000.0))   # 丢弃，扣 1
    _run(eng.maybe_reflect("s1", now=2001.0))   # 丢弃，扣 1（共 2）
    calls_before = p.llm_calls
    assert _run(eng.maybe_reflect("s1", now=2002.0)) is False  # 预算耗尽
    assert p.llm_calls == calls_before  # 第三次连 LLM 都没调


def test_reflection_skips_when_too_few_samples():
    p = _FakePlugin(llm_reply='{"deltas":{}}')
    sc = _FakeSelfCore(p, phase="drowsy")
    sc._store("s1")
    sc._evo_stores["s1"].record_decision(self_quality=0.5, behavior=0.0, now=1.0)
    eng = ReflectionEngine(p, sc)
    assert _run(eng.maybe_reflect("s1", now=2000.0)) is False
    assert p.llm_calls == 0  # 样本不足，连 LLM 都不调

