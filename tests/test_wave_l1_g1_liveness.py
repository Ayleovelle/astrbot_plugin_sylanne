"""Wave-L1/G1：T2-07（主动反馈回路）+ T1-04（复活 RhythmLearner）接线测试。

覆盖：
- T2-07①：on_message 收到用户消息时调用 life_sim.record_user_response
  （此前 record_user_response 是零生产调用方的死代码，她只能学到"被无视"）。
- T1-04①：on_message 调用 RhythmLearner.observe_user_message（而不是只调
  低层 _record_tempo），画像学习真正跑起来。
- T1-04②：RhythmLearner 状态节流落盘（镜像 _life_sim_throttled_save）。
- T1-04③：recent_ignored_rate 不再跨会话污染，改为按 session_key 读取。

把插件真实方法用 MethodType 绑到最小 fake plugin，测真实逻辑而非复刻品
（沿用 test_rel_throttle_trailing.py / test_m8_dispatch_audit.py 的既有模式）。
"""

from __future__ import annotations

import asyncio
import time
import types

import main as main_mod
from sylanne_alpha.bounded_dict import BoundedDict
from sylanne_alpha.llm_response_pipeline import LLMResponsePipeline
from sylanne_alpha.rhythm_learner import RhythmLearner
from sylanne_alpha.session_state_store import SessionMap


def _session_map(name: str) -> SessionMap:
    return SessionMap(name, BoundedDict(maxsize=200))


class _FakeEngine:
    def __init__(self, obs: dict | None = None):
        self._obs = obs or {"warmth": 0.9, "coherence": 0.9, "tension": 0.0}

    def observe(self):
        return self._obs

    def expression_drive(self):
        return 0.5


class _FakeComputation:
    def __init__(self, obs=None):
        self.engine = _FakeEngine(obs)


class _FakeKernel:
    def __init__(self, obs=None):
        self.computation = _FakeComputation(obs)


class _FakeHost:
    def __init__(self, obs=None):
        self.kernel = _FakeKernel(obs)


def _fake_event(session_key="priv:owner-1", text="在干嘛呢"):
    return types.SimpleNamespace(unified_msg_origin=session_key, message_str=text)


class _FakeHosts:
    """仅暴露 on_message 用到的非创建式 .get()（模拟 hosts.get(session_key)）。"""

    def __init__(self, host_by_key: dict | None = None):
        self._d = host_by_key or {}

    def get(self, key, default=None):
        return self._d.get(key, default)


def _make_on_message_plugin(record_calls: list, obs=None):
    """构造仅含 on_message 依赖的最小 fake plugin。

    obs=None 模拟该会话尚无 host（on_message 不应为此新建 host，engine_obs
    退化为空字典）；传 obs 则模拟已存在 host 且其 engine.observe() 返回 obs。
    """
    p = types.SimpleNamespace()
    p._session_ctx = types.SimpleNamespace(
        session_key=lambda ev, sk="": getattr(ev, "unified_msg_origin", sk)
    )
    hosts = _FakeHosts({"priv:owner-1": _FakeHost(obs)} if obs is not None else {})
    p._store = types.SimpleNamespace(
        last_user_message_time=_session_map("last_user_message_time"),
        hosts=hosts,
    )
    # 不设 _proactive_scheduler：on_message 用 getattr(..., None) 兜底，验证可选依赖缺失不炸。

    class _FakeLifeSim:
        def record_user_response(self, session_key, now=None):
            record_calls.append((session_key, now))
            return 1

    p._life_simulator = _FakeLifeSim()
    p._rhythm_learner = RhythmLearner(intimacy_threshold=0.6)

    async def _noop_save():
        return None

    p._rhythm_learner_throttled_save = _noop_save
    p.on_message = types.MethodType(main_mod.EmotionalStatePlugin.on_message, p)
    return p


# ---------------------------------------------------------------------------
# T2-07①：on_message → life_sim.record_user_response
# ---------------------------------------------------------------------------


def test_on_message_records_user_response_on_life_sim():
    calls: list = []
    p = _make_on_message_plugin(calls)
    asyncio.run(p.on_message(_fake_event("priv:owner-1")))
    assert len(calls) == 1
    assert calls[0][0] == "priv:owner-1"


def test_on_message_survives_missing_record_user_response_method():
    """life_sim 存在但没有 record_user_response（旧版/mock）时不应炸——hasattr 兜底。"""
    p = _make_on_message_plugin([])
    p._life_simulator = types.SimpleNamespace()  # 无 record_user_response
    # 不应抛异常
    asyncio.run(p.on_message(_fake_event("priv:owner-1")))


def test_on_message_survives_missing_life_simulator():
    p = _make_on_message_plugin([])
    p._life_simulator = None
    asyncio.run(p.on_message(_fake_event("priv:owner-1")))


# ---------------------------------------------------------------------------
# T1-04①：on_message → RhythmLearner.observe_user_message（真正学习画像）
# ---------------------------------------------------------------------------


def test_on_message_feeds_rhythm_learner_tempo_always():
    """不受亲密度门控：tempo 必须被记录（is_intimate=False 时也一样）。"""
    p = _make_on_message_plugin([], obs={"warmth": 0.0, "coherence": 0.0, "tension": 1.0})
    asyncio.run(p.on_message(_fake_event("priv:owner-1")))
    assert p._rhythm_learner.session_tempo("priv:owner-1") >= 0.0
    assert "priv:owner-1" in p._rhythm_learner._tempo_timestamps


def test_on_message_without_existing_host_still_records_tempo_and_skips_creation():
    """会话尚无 host（如纯群噪音消息）时：不应为它新建 host（用 hosts.get 非创建式
    查询），tempo 仍照常记录，engine_obs 退化为空字典。"""
    p = _make_on_message_plugin([])  # obs=None → hosts 为空字典，无任何 host
    assert p._store.hosts.get("priv:owner-1") is None
    asyncio.run(p.on_message(_fake_event("priv:owner-1")))
    # 仍未凭空创建 host（fake hosts 容器本身就没有创建能力，能跑通即证明
    # on_message 没有走 self._host() 这条会创建 host 的路径）
    assert p._store.hosts.get("priv:owner-1") is None
    assert p._rhythm_learner.session_tempo("priv:owner-1") >= 0.0
    assert p._rhythm_learner.profile("priv:owner-1") is None  # 无 host→非亲密→不建画像


class _FakeHostPartialKernel:
    """host.kernel 存在但内部链路不完整（模拟 partially initialized host）：
    kernel 上没有 .computation，访问 kernel.computation.engine.observe() 会抛
    AttributeError。"""

    def __init__(self):
        self.kernel = types.SimpleNamespace()  # 无 .computation


def test_on_message_survives_partially_initialized_kernel_chain_tempo_still_recorded():
    """kernel 链路本身抛 AttributeError（非 kernel is None）时，engine_obs 应退化为
    {}，但 tempo 记录（observe_user_message）不能被一起吞掉——回归此前『engine_obs
    获取与 observe_user_message 共享一个 try block』导致的静默跳过 bug。"""
    p = _make_on_message_plugin([])
    p._store.hosts = _FakeHosts({"priv:owner-1": _FakeHostPartialKernel()})
    asyncio.run(p.on_message(_fake_event("priv:owner-1")))
    assert p._rhythm_learner.session_tempo("priv:owner-1") >= 0.0
    assert "priv:owner-1" in p._rhythm_learner._tempo_timestamps
    assert p._rhythm_learner.profile("priv:owner-1") is None  # engine_obs={} → 非亲密


def test_on_message_learns_profile_when_intimate():
    """亲密度够（warmth 高）时应学习消息长度画像。"""
    p = _make_on_message_plugin([], obs={"warmth": 0.9, "coherence": 0.9, "tension": 0.0})
    for i in range(10):
        asyncio.run(
            p.on_message(_fake_event("priv:owner-1", text=f"这是第{i}条测试消息内容"))
        )
    profile = p._rhythm_learner.profile("priv:owner-1")
    assert profile is not None
    assert len(profile._msg_lengths) == 10


def test_on_message_skips_profile_when_not_intimate():
    """亲密度不够时只记 tempo，不建画像。"""
    p = _make_on_message_plugin([], obs={"warmth": 0.0, "coherence": 0.0, "tension": 1.0})
    for i in range(10):
        asyncio.run(p.on_message(_fake_event("priv:owner-1", text="消息")))
    assert p._rhythm_learner.profile("priv:owner-1") is None


# ---------------------------------------------------------------------------
# T1-04②：RhythmLearner 节流落盘（镜像 _life_sim_throttled_save 时序契约）
# ---------------------------------------------------------------------------


def _make_throttle_plugin():
    p = types.SimpleNamespace()
    p._rhythm_learner = RhythmLearner(intimacy_threshold=0.6)
    p._rhythm_learner_last_save_ts = 0.0
    p._rhythm_learner_dirty_in_flight = False
    p._kv_writes: list = []

    async def _put_kv_data(key, value):
        p._kv_writes.append((key, value))

    def _has_kv_api():
        return True

    p.put_kv_data = _put_kv_data
    p._has_kv_api = _has_kv_api
    p._rhythm_learner_throttled_save = types.MethodType(
        main_mod.EmotionalStatePlugin._rhythm_learner_throttled_save, p
    )
    return p


def test_rhythm_learner_throttled_save_first_call_writes():
    p = _make_throttle_plugin()
    asyncio.run(p._rhythm_learner_throttled_save())
    assert len(p._kv_writes) == 1
    assert p._kv_writes[0][0] == "sylanne_rhythm_learner_state"


def test_rhythm_learner_throttled_save_within_gap_skips():
    p = _make_throttle_plugin()
    asyncio.run(p._rhythm_learner_throttled_save())
    asyncio.run(p._rhythm_learner_throttled_save())
    assert len(p._kv_writes) == 1  # 第二次在 min-gap 内被节流


def test_rhythm_learner_throttled_save_noop_without_kv_api():
    p = _make_throttle_plugin()
    p._has_kv_api = lambda: False
    asyncio.run(p._rhythm_learner_throttled_save())
    assert p._kv_writes == []


def test_rhythm_learner_state_roundtrip_via_to_dict_from_dict():
    """T1-04②依赖的序列化契约：学到的画像应能原样恢复。"""
    learner = RhythmLearner(intimacy_threshold=0.6)
    for i in range(10):
        learner.observe_user_message(
            "sessA", f"消息{i}测试内容", float(i), {"warmth": 0.9, "coherence": 0.9, "tension": 0.0}
        )
    data = learner.to_dict()
    restored = RhythmLearner.from_dict(data)
    assert restored.profile("sessA") is not None
    assert restored.profile("sessA").confidence == learner.profile("sessA").confidence


def test_rhythm_learner_from_dict_tolerates_legacy_missing_fields():
    """向后兼容：旧档缺字段时 from_dict 不应炸。"""
    restored = RhythmLearner.from_dict({})
    assert restored.profile("anything") is None


# ---------------------------------------------------------------------------
# T1-04③：recent_ignored_rate 按 session_key 隔离，不再跨会话污染
# ---------------------------------------------------------------------------


def _recent_ignored_rate(store, session_key: str, now: float) -> float:
    """复刻 llm_response_pipeline.py 里的计算片段，直接验证隔离行为。"""
    recent_ignored = 0.0
    last_expr_at = store.last_bot_expression_time.get(session_key, 0.0)
    last_user_at = store.last_user_message_time.get(session_key, 0.0)
    if last_expr_at > 0 and last_user_at < last_expr_at:
        silence = now - last_expr_at
        if silence > 300.0:
            recent_ignored = min(1.0, (silence - 300.0) / 300.0)
    return recent_ignored


def test_recent_ignored_rate_isolated_per_session():
    """A 会话被"忽略"很久，不应污染刚刚活跃的 B 会话。"""
    store = types.SimpleNamespace(
        last_bot_expression_time=_session_map("last_bot_expression_time"),
        last_user_message_time=_session_map("last_user_message_time"),
    )
    now = time.time()
    # A：很久以前表达过，用户一直没再开口 → 应该判定"被忽略"
    store.last_bot_expression_time.set("sessA", now - 1000.0)
    store.last_user_message_time.set("sessA", now - 1200.0)
    # B：刚刚才互动过 → 不该被 A 拖累
    store.last_bot_expression_time.set("sessB", now - 5.0)
    store.last_user_message_time.set("sessB", now - 1.0)

    assert _recent_ignored_rate(store, "sessA", now) > 0.0
    assert _recent_ignored_rate(store, "sessB", now) == 0.0


def test_recent_ignored_rate_zero_when_user_already_replied():
    store = types.SimpleNamespace(
        last_bot_expression_time=_session_map("last_bot_expression_time"),
        last_user_message_time=_session_map("last_user_message_time"),
    )
    now = time.time()
    store.last_bot_expression_time.set("sessA", now - 1000.0)
    store.last_user_message_time.set("sessA", now - 1.0)  # 用户刚回过
    assert _recent_ignored_rate(store, "sessA", now) == 0.0


def test_llm_response_pipeline_uses_session_scoped_ignored_rate():
    """端到端锚点：确认 llm_response_pipeline 真的按 session_key 读取，而不是
    再退回 .values() 跨会话池（只匹配真代码行，不误伤解释性注释）。"""
    import inspect

    src = inspect.getsource(LLMResponsePipeline)
    assert "last_bot_expression_time.get(session_key" in src
    assert "for t in self._p._store.last_bot_expression_time.values()" not in src
