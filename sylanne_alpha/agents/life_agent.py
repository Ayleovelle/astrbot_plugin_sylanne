"""LifeAgent：作息/生活节律 worker（CP8-P3a 取用 + P3b 自驱演化）。

双时点：
- PRE：把待分享的生命事件作为高层意图托管，供 prompt 注入（请求侧取用）。
- AUTONOMOUS：无用户消息时自主演化作息/生活事件（驱动 LifeSimulator.simulate_tick），
  实现「没人说话也活着」。演化是全局的（一个 bot 一套作息），由 AutonomyScheduler
  在全局时点调用一次（非每会话）。

C 方案核心：LifeSimulator 不再自跑 _loop，演化驱动收归本 agent，单一心跳同构。
间隔门控（原 _loop 的 interval_seconds * jitter）改由本 agent gate 判定。
"""

from __future__ import annotations

import random
import time
from typing import Any

from sylanne_alpha.agents.base import (
    AUTONOMOUS,
    PRE,
    RULE,
    SKIP,
    AgentIntent,
    CognitiveAgent,
)


class LifeAgent(CognitiveAgent):
    name = "life"
    phases = (PRE, AUTONOMOUS)

    def perceive(self, surface: dict[str, Any]) -> dict[str, Any]:
        sim = getattr(self._p, "_life_simulator", None)
        has_share = False
        enabled = False
        due = False
        if sim is not None:
            try:
                enabled = bool(sim.enabled)
                has_share = bool(sim.pending_share_events())
                # 自驱演化间隔门控（复现原 _loop 的 interval_seconds * jitter）
                now = time.time()
                last = float(getattr(sim.state, "last_simulation_time", 0.0) or 0.0)
                interval = sim.interval_seconds * random.uniform(0.4, 1.8)
                due = enabled and (now - last) >= interval
            except Exception:
                pass
        return {"has_pending_share": has_share, "enabled": enabled, "autonomy_due": due}

    def gate(self, perceived: dict[str, Any]) -> str:
        # PRE 与 AUTONOMOUS 共用 gate；具体行为由 act 按 phase 分流。
        if perceived.get("has_pending_share") or perceived.get("autonomy_due"):
            return RULE
        return SKIP

    async def act(
        self, session_key: str, mode: str, perceived: dict[str, Any], phase: str = PRE
    ) -> AgentIntent | None:
        sim = getattr(self._p, "_life_simulator", None)
        if sim is None:
            return None

        if phase == AUTONOMOUS:
            # 自驱演化：驱动 LifeSimulator 跑一次模拟 tick（生成事件/注入 body/触发 outreach）。
            # 全局一次，不产意图贡献（演化副作用即目的）。
            if perceived.get("autonomy_due"):
                try:
                    await sim.simulate_tick()
                except Exception:
                    pass
            return None

        if phase == PRE:
            try:
                ctx = sim.recent_context_for_prompt(limit=3)
            except Exception:
                return None
            if not ctx:
                return None
            return AgentIntent(source=self.name, payload={"life_context": ctx}, priority=0.3)
        return None
