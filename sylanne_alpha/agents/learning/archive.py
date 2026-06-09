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
    """单个可学习门控偏置的状态：当前偏置 + EMA 信号 + 钳位。

    两路偏置物理隔离、各自独立钳位（护栏 FM1 防双环共振）：
    - delta：层次1 反应式学习的高频微调（每轮 EMA，自动回归基线）。
    - reflection_bias：层次2 睡眠反思沉淀的低频偏置（DROWSY 首拍 LLM 元认知产出）。
    gate 读取的总偏置 = delta + reflection_bias，二者来源/时间尺度不同，分开存。
    """

    delta: float = 0.0          # 层次1 反应式学到的偏置（高频）
    reward_ema: float = 0.0     # 效果信号的指数滑动平均（聚合，不存逐条）
    delta_cap: float = 0.15     # 硬钳位：|delta| ≤ cap（防漂出）
    updates: int = 0            # 累计更新次数（审计用）
    reflection_bias: float = 0.0  # 层次2 反思沉淀的偏置（低频，睡眠期产出）
    reflection_cap: float = 0.10  # 反思偏置硬钳位（比反射更保守）

    def clamp(self) -> None:
        if self.delta > self.delta_cap:
            self.delta = self.delta_cap
        elif self.delta < -self.delta_cap:
            self.delta = -self.delta_cap
        if self.reflection_bias > self.reflection_cap:
            self.reflection_bias = self.reflection_cap
        elif self.reflection_bias < -self.reflection_cap:
            self.reflection_bias = -self.reflection_cap


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
        """读某门控参数当前学到的总偏置（gate 里叠加用）= 反射 + 反思。无则 0。"""
        ps = self._params.get(key)
        return (ps.delta + ps.reflection_bias) if ps is not None else 0.0

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

    def apply_reflection(
        self, key: str, target_bias: float, *, lerp: float = 0.5, delta_cap: float = 0.15
    ) -> None:
        """层次2 反思沉淀（低频）：把某门控参数的 reflection_bias 朝 LLM 给的目标
        偏置插值收拢一步，再钳位 + 审计。

        - 用插值（lerp，默认 0.5）而非直接赋值：单次反思不能一步到位，
          多次反思才逼近目标（防一次坏推理把偏置打满，护栏 FM1）。
        - reflection_bias 与 delta 物理隔离、独立钳位（reflection_cap 更保守）。
        """
        ps = self.ensure_param(key, delta_cap=delta_cap)
        old = ps.reflection_bias
        ps.reflection_bias += (target_bias - ps.reflection_bias) * max(0.0, min(1.0, lerp))
        ps.clamp()
        if abs(ps.reflection_bias - old) > 1e-9:
            self._audit.append({
                "t": time.time(), "key": key, "old": round(old, 6),
                "new": round(ps.reflection_bias, 6), "src": "reflection",
            })

    @property
    def outcome_ema(self) -> float:
        return self._outcome_ema

    def param_snapshot(self) -> dict[str, dict[str, float]]:
        """只读快照：各门控参数当前两路偏置（供反思 prompt 描述现状）。"""
        return {
            k: {"delta": round(ps.delta, 4), "reflection_bias": round(ps.reflection_bias, 4)}
            for k, ps in self._params.items()
        }

    def reset_to_factory(self) -> None:
        """一键出厂复位：清空所有学到的偏置（护栏：可回滚）。"""
        for ps in self._params.values():
            ps.delta = 0.0
            ps.reward_ema = 0.0
            ps.reflection_bias = 0.0
        self._audit.append({"t": time.time(), "key": "*", "action": "factory_reset"})

    # ---- 持久化 ----
    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "outcome_ema": round(self._outcome_ema, 6),
            "params": {
                k: {"delta": round(ps.delta, 6), "reward_ema": round(ps.reward_ema, 6),
                    "delta_cap": ps.delta_cap, "updates": ps.updates,
                    "reflection_bias": round(ps.reflection_bias, 6),
                    "reflection_cap": ps.reflection_cap}
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
                reflection_bias=float(pd.get("reflection_bias", 0.0)),
                reflection_cap=float(pd.get("reflection_cap", 0.10)),
            )
            ps.clamp()
            arc._params[k] = ps
        return arc
