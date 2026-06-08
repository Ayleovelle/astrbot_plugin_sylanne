"""CP8-P4-C 自我进化层单元测试：档案护栏 + 反应式学习。"""

from sylanne_alpha.agents.learning import (
    AgentEvolutionArchive,
    EvolutionStore,
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
