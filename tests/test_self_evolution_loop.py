"""自我进化闭环 phase 测试（feat/self-evolution-loop）。

覆盖两件事：
  #29 evo_delta 接通 live 门控：进化偏置经 ctx.evo_bias 喂回 IgnitionArbiter（说/主动）
      与 MemoryDomain.intimacy_ok（召回），叠加在人格函数基线上、带二次钳位。
  #31 self_score 奖励改滚动基线：自评支点从固定 0.5 改成近期 self_score 的 EMA，
      奖励＝"比近期平均好/差"；配套放开 behavior==0 守卫（滚动基线使其安全）。
"""

from __future__ import annotations

from sylanne_alpha.agents.learning.archive import AgentEvolutionArchive
from sylanne_alpha.agents.learning.reflex import EvolutionStore, ReflexLearner
from sylanne_alpha.v2core.capabilities.ignition import IgnitionArbiter, personality_saddle
from sylanne_alpha.v2core.capabilities.recall import RecallCapability
from sylanne_alpha.v2core.contracts import (
    _EVO_BIAS_CAP,
    BeatContext,
    BodySnapshot,
    Phase,
)
from sylanne_alpha.v2core.domains.memory import MemoryDomain


# ===========================================================================
# #31 —— self_score 奖励滚动基线
# ===========================================================================

def test_compute_reward_default_baseline_back_compat():
    """缺省 self_baseline=0.5 时精确回到旧式 (q*2-1)，向后兼容锚点不变。"""
    rl = ReflexLearner(plugin=None)
    for q in (0.0, 0.25, 0.5, 0.75, 1.0):
        old = 0.3 * (q * 2.0 - 1.0)          # 旧公式：behavior=0 时 r = W_SELF*(q*2-1)
        got = rl.compute_reward(behavior=0.0, self_quality=q)
        assert abs(got - max(-1.0, min(1.0, old))) < 1e-9


def test_compute_reward_rolling_baseline_beats_absolute_pivot():
    """根因复现：保守评估器把好回复判到 0.45。

    固定 0.5 支点 → 自评项恒负（够不到门）；滚动基线 0.40 → 0.45 高于近期平均 → 正信号。
    """
    rl = ReflexLearner(plugin=None)
    # 固定支点（旧行为）：0.45 < 0.5 → 负
    assert rl.compute_reward(behavior=0.0, self_quality=0.45) < 0
    # 滚动支点 0.40：0.45 高于近期平均 → 正（即便绝对值 < 0.5）
    assert rl.compute_reward(behavior=0.0, self_quality=0.45, self_baseline=0.40) > 0


def test_compute_reward_behavior_still_dominates_self():
    """放滚动基线后行为仍是强信号：被忽略(-1)即便自评高于基线，reward 仍偏负。"""
    rl = ReflexLearner(plugin=None)
    r = rl.compute_reward(behavior=-1.0, self_quality=0.9, self_baseline=0.4)
    assert r < 0  # 0.7*(-1) + 0.3*clamp((0.9-0.4)*2)=−0.7+0.3=−0.4


def test_learn_uses_archive_outcome_ema_as_rolling_baseline():
    """learn 读 arc.outcome_ema 作支点：种子把基线压低后，绝对偏低的好回复也驱动门控。"""
    rl = ReflexLearner(plugin=None)
    store = EvolutionStore()
    arc = store.archive("memory")
    # 把近期平均压到 ~0.30（保守评估器场景）
    for _ in range(40):
        arc.record_outcome(0.30)
    assert arc.outcome_ema < 0.35
    # behavior==0（行为未知，异步常态），自评 0.50 持续高于近期平均 → 门控被驱动（正向）
    for _ in range(20):
        rl.learn(store, "memory", "k", behavior=0.0, self_quality=0.50)
    assert store.get_delta("memory", "k") > 0   # 自评在行为未知轮也能驱动了（#31 放闸生效）


def test_rolling_baseline_self_neutral_at_steady_state():
    """关键反 Goodhart：稳态(质量=近期平均)时自评项→0、死区拦截，门控不被自我强化。"""
    rl = ReflexLearner(plugin=None)
    store = EvolutionStore()
    arc = store.archive("memory")
    for _ in range(100):
        arc.record_outcome(0.45)            # 近期平均收敛到 0.45
    before = store.get_delta("memory", "k")
    for _ in range(50):
        rl.learn(store, "memory", "k", behavior=0.0, self_quality=0.45)  # 恰好等于平均
    after = store.get_delta("memory", "k")
    assert abs(after - before) < 1e-9       # (q-baseline)=0 → 死区拦 → 门控零漂移


def test_learn_behavior_path_unchanged_by_rolling_baseline():
    """behavior≠0 时仍按行为方向走（强信号主导），滚动基线只调味不翻号。"""
    rl = ReflexLearner(plugin=None)
    store = EvolutionStore()
    for _ in range(50):
        rl.learn(store, "proactive", "open_threshold", behavior=-1.0, self_quality=0.9)
    # 持续被忽略 → 更主动（delta 负），即便自评很高也压不翻行为信号
    assert store.get_delta("proactive", "open_threshold") < 0


def test_self_only_drift_is_clamped():
    """放闸后单向【质量趋势】最坏情形也被 ±delta_cap 钳死，不会无界放大。"""
    rl = ReflexLearner(plugin=None)
    store = EvolutionStore()
    arc = store.archive("memory")
    # 人为制造持续"高于基线"：每轮把基线手动压回低位，逼自评恒正同号（最坏对抗场景）
    for _ in range(2000):
        arc._outcome_ema = 0.2          # 强制基线滞后（趋势攻击的极端）
        rl.learn(store, "memory", "k", behavior=0.0, self_quality=0.8)
    assert store.get_delta("memory", "k") <= 0.15 + 1e-9   # 反射 cap 兜底


# ===========================================================================
# #29 —— evo_delta 接通 live 门控
# ===========================================================================

def _body(**kw) -> BodySnapshot:
    return BodySnapshot(session_key="s", turns=1, **kw)


def _ctx(body: BodySnapshot, *, evo: dict[str, float] | None = None,
         text: str = "") -> BeatContext:
    ctx = BeatContext(session_key="s", event=None, body=body, text=text)
    if evo is not None:
        ctx.scratch["evo_delta"] = lambda a, k: evo.get(f"{a}.{k}", 0.0)
    return ctx


def test_evo_bias_absent_provider_is_zero():
    """无 provider（旧路径/测试）→ 0.0：门控落回纯人格基线，零行为变化。"""
    ctx = _ctx(_body())
    assert ctx.evo_bias("proactive", "open_threshold") == 0.0


def test_evo_bias_reads_and_clamps():
    """provider 值透传，但超 ±_EVO_BIAS_CAP 被二次钳位（live 门控的最后一道刹车）。"""
    ctx = _ctx(_body(), evo={"proactive.open_threshold": -0.30,
                             "memory.intimacy_threshold": 0.05})
    assert ctx.evo_bias("proactive", "open_threshold") == -_EVO_BIAS_CAP  # -0.30 → -0.15
    assert abs(ctx.evo_bias("memory", "intimacy_threshold") - 0.05) < 1e-9  # 范围内透传


def test_evo_bias_provider_exception_is_zero():
    """provider 抛异常 → 0.0（学习层故障绝不阻断/改写门控）。"""
    ctx = _ctx(_body())

    def _boom(a, k):
        raise RuntimeError("boom")

    ctx.scratch["evo_delta"] = _boom
    assert ctx.evo_bias("proactive", "open_threshold") == 0.0


def test_intimacy_ok_respects_negative_bias():
    """memory.intimacy_threshold 负偏置 → 降门槛 → 略低于基线的关系也愿意翻记忆（更主动）。"""
    ms = _DummyMS()
    dom = MemoryDomain(ms)
    just_below = _body(intimacy_gravity=0.30)        # 基线 0.35，原本不过
    assert dom.intimacy_ok(just_below) is False
    assert dom.intimacy_ok(just_below, bias=-0.10) is True   # 阈值 0.35-0.10=0.25 ≤ 0.30


def test_intimacy_ok_positive_bias_raises_bar():
    """正偏置 → 抬高门槛 → 略高于基线也被挡（更收敛）。"""
    dom = MemoryDomain(_DummyMS())
    just_above = _body(intimacy_gravity=0.40)
    assert dom.intimacy_ok(just_above) is True
    assert dom.intimacy_ok(just_above, bias=0.10) is False   # 阈值 0.45 > 0.40


def test_ignition_open_bias_lowers_express_at():
    """proactive.open_threshold 负偏置叠到 IgnitionArbiter 的 express_at（说/主动门槛降低）。"""
    body = _body()
    base_express = personality_saddle(body)[0]
    # 无偏置基线
    base_ctx = _ctx(body, text="在吗")
    base_ctx.phase = Phase.DELIBERATE
    base_payload = IgnitionArbiter().deliberate(base_ctx).payload
    assert abs(base_payload["express_at"] - base_express) < 1e-9
    # 负偏置 → express_at 降低恰好 0.12
    biased = _ctx(body, evo={"proactive.open_threshold": -0.12}, text="在吗")
    biased.phase = Phase.DELIBERATE
    biased_payload = IgnitionArbiter().deliberate(biased).payload
    assert abs(biased_payload["express_at"] - (base_express - 0.12)) < 1e-9


def test_ignition_cold_addressed_still_speaks_under_bias():
    """no-ghost 红线不被偏置破坏：被问 + 冷躯体，任何偏置下仍必 speak。"""
    body = _body(expression_drive=0.0)
    for b in (-_EVO_BIAS_CAP, 0.0, _EVO_BIAS_CAP):
        ctx = _ctx(body, evo={"proactive.open_threshold": b}, text="在吗")
        ctx.phase = Phase.DELIBERATE
        assert IgnitionArbiter().deliberate(ctx).payload["action"] == "speak"


def test_recall_capability_threads_bias_to_intimacy_ok():
    """RecallCapability 把 ctx.evo_bias 透传给 intimacy_ok（接线核验，捕获实参）。"""
    seen: dict[str, float] = {}

    class _CaptureMem:
        name = "memory"

        def intimacy_ok(self, body, *, bias: float = 0.0) -> bool:  # noqa: ANN001
            seen["bias"] = bias
            return False   # 返回 False 即可短路，足够验证 bias 被传

    body = _body(intimacy_gravity=0.9)
    ctx = _ctx(body, evo={"memory.intimacy_threshold": -0.07}, text="记得吗")
    ctx.phase = Phase.DELIBERATE
    ctx.domains["memory"] = _CaptureMem()
    RecallCapability().deliberate(ctx)
    assert abs(seen.get("bias", 0.0) - (-0.07)) < 1e-9


# --- 轻量 MemorySystem 替身（只为 intimacy_ok，不触召回）-------------------
class _DummyMS:
    def recall(self, *a, **k):   # pragma: no cover - 本组测试不调召回
        return []
