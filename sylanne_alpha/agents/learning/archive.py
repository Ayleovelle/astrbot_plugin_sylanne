"""Agent 进化档案 + 护栏（CP8-P4-C 自我进化）。

每个 agent 一份档案，存「学到的门控参数偏置」+ 效果聚合统计 + 审计/快照。
持久化走 per-session KV（接入 main 的持久化流程）。

护栏（team/skeptic 三铁律之护栏1：防双环共振 + 可回滚）：
- 钳位：所有可学习偏置硬上下限（±delta_cap），漂不出去。
- 回归基线：每次更新朝 0 拉一个小系数（无信号自动复位），防单向锁定。
- 与 embodiment 隔离：只动「临时偏置 Δ」，不写人格特质基线（embodiment 自有漂移）。
- 审计 + 快照：每次变更记日志，支持一键复位到出厂（全 0）。
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class _ParamState:
    """单个可学习门控偏置的状态：当前偏置 + EMA 信号 + 钳位。"""

    delta: float = 0.0          # 当前学到的偏置（叠加在 base 人格函数上）
    reward_ema: float = 0.0     # 效果信号的指数滑动平均（聚合，不存逐条）
    delta_cap: float = 0.15     # 硬钳位：|delta| ≤ cap（防漂出）
    updates: int = 0            # 累计更新次数（审计用）

    def clamp(self) -> None:
        if self.delta > self.delta_cap:
            self.delta = self.delta_cap
        elif self.delta < -self.delta_cap:
            self.delta = -self.delta_cap


class AgentEvolutionArchive:
    """单个 agent 的进化档案。持有若干可学习门控偏置 + 效果统计 + 审计。

    设计为纯数据 + 逻辑，不依赖运行时，可完整单测。
    """

    __slots__ = ("agent_name", "_params", "_audit", "_outcome_ema", "_created_at")

    def __init__(self, agent_name: str) -> None:
        self.agent_name = agent_name
        self._params: dict[str, _ParamState] = {}
        # 审计日志：环形缓冲，存最近 N 次变更（旧值/新值/触发/时间）
        self._audit: deque[dict[str, Any]] = deque(maxlen=50)
        # 综合效果 EMA（跨所有维度的整体质量趋势，用于回滚判据）
        self._outcome_ema: float = 0.5
        self._created_at: float = time.time()

    def ensure_param(self, key: str, *, delta_cap: float = 0.15) -> _ParamState:
        ps = self._params.get(key)
        if ps is None:
            ps = _ParamState(delta_cap=delta_cap)
            self._params[key] = ps
        return ps

    def get_delta(self, key: str) -> float:
        """读某门控参数当前学到的偏置（gate 里叠加用）。无则 0。"""
        ps = self._params.get(key)
        return ps.delta if ps is not None else 0.0

    def update(
        self,
        key: str,
        reward: float,
        *,
        eta: float = 0.002,
        deadzone: float = 0.05,
        regress: float = 0.01,
        delta_cap: float = 0.15,
    ) -> None:
        """反应式更新（层次1）：EMA + 死区 + 回归基线 + 钳位。

        - reward ∈ [-1,1]：正=当前策略有效，负=无效。
        - 死区：|reward|<deadzone 不调（噪声不驱动）。
        - 回归：每次朝 0 拉 regress 比例（无持续信号自动复位，防单向锁定）。
        - eta 极小 + 钳位：漂移慢且有界（时间尺度与 embodiment 分离）。
        """
        ps = self.ensure_param(key, delta_cap=delta_cap)
        ps.reward_ema = 0.9 * ps.reward_ema + 0.1 * reward
        old = ps.delta
        # 回归基线：先朝 0 收缩
        ps.delta *= (1.0 - regress)
        # 死区外才学习
        if abs(reward) >= deadzone:
            ps.delta += eta * (1.0 if reward > 0 else -1.0)
        ps.clamp()
        ps.updates += 1
        if abs(ps.delta - old) > 1e-9:
            self._audit.append({
                "t": time.time(), "key": key, "old": round(old, 6),
                "new": round(ps.delta, 6), "reward": round(reward, 4),
            })

    def record_outcome(self, quality: float) -> None:
        """记录综合效果（用于回滚判据/背离监控）。"""
        self._outcome_ema = 0.9 * self._outcome_ema + 0.1 * quality

    @property
    def outcome_ema(self) -> float:
        return self._outcome_ema

    def reset_to_factory(self) -> None:
        """一键出厂复位：清空所有学到的偏置（护栏：可回滚）。"""
        for ps in self._params.values():
            ps.delta = 0.0
            ps.reward_ema = 0.0
        self._audit.append({"t": time.time(), "key": "*", "action": "factory_reset"})

    # ---- 持久化 ----
    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "outcome_ema": round(self._outcome_ema, 6),
            "params": {
                k: {"delta": round(ps.delta, 6), "reward_ema": round(ps.reward_ema, 6),
                    "delta_cap": ps.delta_cap, "updates": ps.updates}
                for k, ps in self._params.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentEvolutionArchive":
        arc = cls(str(data.get("agent_name", "?")))
        arc._outcome_ema = float(data.get("outcome_ema", 0.5))
        for k, pd in (data.get("params") or {}).items():
            ps = _ParamState(
                delta=float(pd.get("delta", 0.0)),
                reward_ema=float(pd.get("reward_ema", 0.0)),
                delta_cap=float(pd.get("delta_cap", 0.15)),
                updates=int(pd.get("updates", 0)),
            )
            ps.clamp()
            arc._params[k] = ps
        return arc
