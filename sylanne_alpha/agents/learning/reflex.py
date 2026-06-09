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
      reward = w_behav * behavior_signal + w_self * (self_score_quality*2-1)
    其中 behavior_signal：被忽略=-1，被续聊/采纳=+1，未知=0。
    """

    # 防 Goodhart：自评权重远低于可观测行为
    W_BEHAVIOR = 0.7
    W_SELF = 0.3

    def __init__(self, plugin: Any) -> None:
        self._p = plugin

    def compute_reward(self, *, behavior: float, self_quality: float | None) -> float:
        """behavior ∈ {-1,0,1}（被忽略/未知/被采纳）；self_quality ∈ [0,1] 或 None。"""
        r = self.W_BEHAVIOR * behavior
        if self_quality is not None:
            r += self.W_SELF * (self_quality * 2.0 - 1.0)
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
        reward = self.compute_reward(behavior=behavior, self_quality=self_quality)
        arc = store.archive(agent_name)
        arc.update(param_key, reward, delta_cap=delta_cap)
        if self_quality is not None:
            arc.record_outcome(self_quality)
