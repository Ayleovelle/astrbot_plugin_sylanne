"""反应式学习驱动 + 进化档案仓（CP8-P4-C 层次1）。

EvolutionStore：每会话一份，持有该会话下所有 agent 的 AgentEvolutionArchive。
ReflexLearner：层次1 反应式学习器，每轮对话后用零 LLM 的 reward 信号微调各 agent
的门控偏置。reward 来源（防 Goodhart）：self_score 弱先验（低权重）+ 可观测行为
（被忽略/续聊，强权重）。
"""

from __future__ import annotations

from collections import deque
from typing import Any

from sylanne_alpha.agents.learning.archive import AgentEvolutionArchive


class EvolutionStore:
    """单会话的进化档案仓：agent_name → AgentEvolutionArchive。

    另持一条 DecisionLog 环形缓冲（FM6 防膨胀：只存最近 N 条聚合样本
    (t, self_quality, behavior)，不存逐条全文，不落盘——供层次2 睡眠反思
    压缩成元认知输入，唤醒即可丢）。
    """

    __slots__ = ("_archives", "_decision_log")

    # 决策日志窗口：只留最近 N 条（够反思一次，多了也压不进 1500 字）
    _LOG_MAXLEN = 24

    def __init__(self) -> None:
        self._archives: dict[str, AgentEvolutionArchive] = {}
        self._decision_log: deque[dict[str, float]] = deque(maxlen=self._LOG_MAXLEN)

    def archive(self, agent_name: str) -> AgentEvolutionArchive:
        arc = self._archives.get(agent_name)
        if arc is None:
            arc = AgentEvolutionArchive(agent_name)
            self._archives[agent_name] = arc
        return arc

    def get_delta(self, agent_name: str, key: str) -> float:
        arc = self._archives.get(agent_name)
        return arc.get_delta(key) if arc is not None else 0.0

    def record_decision(self, *, self_quality: float | None, behavior: float, now: float) -> None:
        """追加一条聚合决策样本（层次1 学习时顺手记，供层次2 反思读）。"""
        self._decision_log.append({
            "t": round(now, 1),
            "q": round(self_quality, 4) if self_quality is not None else -1.0,
            "b": round(behavior, 4),
        })

    def decision_samples(self) -> list[dict[str, float]]:
        """只读快照：当前决策日志（供反思压缩）。"""
        return list(self._decision_log)

    def archives_snapshot(self) -> dict[str, AgentEvolutionArchive]:
        """只读：所有 agent 档案（反思引擎遍历用）。"""
        return dict(self._archives)

    def reset_all(self) -> None:
        for arc in self._archives.values():
            arc.reset_to_factory()

    def decay_reflection_all(self, factor: float = 0.1) -> None:
        """CP8-P6：所有 agent 档案的 reflection_bias 朝 0 衰减一步（深睡巩固调）。"""
        for arc in self._archives.values():
            arc.decay_reflection(factor)

    def to_dict(self) -> dict[str, Any]:
        return {name: arc.to_dict() for name, arc in self._archives.items()}

    def load_dict(self, data: dict[str, Any]) -> None:
        for name, ad in (data or {}).items():
            try:
                self._archives[name] = AgentEvolutionArchive.from_dict(ad)
            except Exception:
                pass


class ReflexLearner:
    """层次1 反应式学习器（零 LLM）。

    在每轮认知周期末尾，根据本轮效果信号微调各 agent 的门控偏置。
    reward 综合（防 Goodhart：self_score 弱、行为信号强）：
      reward = w_behav * behavior_signal + w_self * clamp((self_quality - baseline) * gain)
    其中 behavior_signal：被忽略=-1，被续聊/采纳=+1，未知=0。

    #31 滚动基线（self_score 奖励改"相对最近平均"）：自评支点不再固定 0.5，而是
    用该 agent 近期 self_score 的 EMA（AgentEvolutionArchive.outcome_ema）作支点。
    根因——真机实测保守评价器把好回复也判到 0.4–0.5、够不到固定 0.5 支点，导致自评项
    几乎恒负、自我进化几乎不触发。改成"比我最近平均好/差"后，绝对值偏低但相对改善的
    回复也能给正信号；稳态时 (q-baseline)→0 自评项自然归零（防 Goodhart：自评只在偏离
    近期常态时才说话，不当恒定偏置）。gain=2 使支点=0.5 时精确回到旧式 (q*2-1)（锚定不变）。
    """

    # 防 Goodhart：自评权重远低于可观测行为
    W_BEHAVIOR = 0.7
    W_SELF = 0.3
    # 自评支点增益：baseline=0.5 时 (q-0.5)*2 == 旧式 (q*2-1)，向后兼容锚点
    _SELF_GAIN = 2.0

    def __init__(self, plugin: Any) -> None:
        self._p = plugin

    def compute_reward(
        self, *, behavior: float, self_quality: float | None, self_baseline: float = 0.5
    ) -> float:
        """behavior ∈ {-1,0,1}（被忽略/未知/被采纳）；self_quality ∈ [0,1] 或 None。

        self_baseline：自评滚动支点（#31，默认 0.5 = 旧固定支点，向后兼容）。自评项＝
        clamp((self_quality - self_baseline) * gain, -1, 1)，即"比近期平均好/差"而非"绝对>0.5"。
        """
        r = self.W_BEHAVIOR * behavior
        if self_quality is not None:
            self_term = (self_quality - self_baseline) * self._SELF_GAIN
            self_term = max(-1.0, min(1.0, self_term))   # 自评项独立钳位，单项不超 ±W_SELF
            r += self.W_SELF * self_term
        return max(-1.0, min(1.0, r))

    def learn(
        self,
        store: EvolutionStore,
        agent_name: str,
        param_key: str,
        *,
        behavior: float,
        self_quality: float | None,
        delta_cap: float = 0.15,
    ) -> None:
        """对某 agent 的某门控参数做一次反应式微调。"""
        arc = store.archive(agent_name)
        # #31 滚动基线：用该 agent 近期 self_score 的 EMA 作自评支点（更新前读取＝不含本轮，
        # 严格是"近期平均"）。首轮 outcome_ema=0.5 → 退化成旧固定支点（冷启动锚点不变）。
        baseline = arc.outcome_ema
        reward = self.compute_reward(
            behavior=behavior, self_quality=self_quality, self_baseline=baseline
        )
        # 【#31 配套放闸 —— 旗标决策，见交付说明】历史上这里有 `if behavior != 0.0` 守卫
        # （review learning-loop high）：异步异国恋里 5min–2h 回复间隔极常见 → behavior 恒 0
        # （#30 死区，禁改）→ 守卫挡掉一切自评驱动的步进。该守卫的原始顾虑是"固定 0.5 支点下
        # 保守自评(~0.4) 每轮同号(恒负)累积，几百轮钉到 ±cap 地板，成不由真实反馈的单向漂移"。
        #
        # #31 的滚动基线正好拔掉这条顾虑的根：自评项＝(q − 近期EMA)，稳态下均值回归到 0、不再
        # 每轮同号；故放开守卫让自评在 behavior==0 时也能驱动门控，是 #31 让"自进化在行为未知轮
        # 也能触发"落地的必要一步（否则滚动基线对 delta 全程无效，只动审计 EMA）。
        #
        # 放闸后的四道护栏（替代旧守卫，强度足够）：① 滚动基线 → 均值回归、非单向；② 死区
        # deadzone=0.05 → behavior==0 时 reward=W_SELF·self_term，仅 |q−EMA|≳0.083 才迈步，噪声被滤；
        # ③ regress 每步朝 0 收缩 → 无持续信号自动复位；④ delta_cap ±0.15 硬钳 + 档案总 cap ±0.20
        # + live 门控 evo_bias 二次 cap ±0.15。残留风险=长期单向【质量趋势】里 EMA 滞后致同号偏置，
        # 但被 ±0.15 钳死且趋势一平即 regress 回收（已在交付隐患清单列明，留用户裁定是否收紧）。
        if behavior != 0.0 or self_quality is not None:
            arc.update(param_key, reward, delta_cap=delta_cap)
        if self_quality is not None:
            arc.record_outcome(self_quality)
