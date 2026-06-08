"""LifeAgent：作息/生活节律 worker（CP8-P3a）。

时点：PRE（把待分享的生命事件作为高层意图托管，供 prompt 注入）。
纯规则，零 LLM——作息是时间函数，由 LifeSimulator 后台循环演化，本 agent 只取用。
"""

from __future__ import annotations

from typing import Any

from sylanne_alpha.agents.base import PRE, RULE, SKIP, AgentIntent, CognitiveAgent


class LifeAgent(CognitiveAgent):
    name = "life"
    phases = (PRE,)

    def perceive(self, surface: dict[str, Any]) -> dict[str, Any]:
        sim = getattr(self._p, "_life_simulator", None)
        has_share = False
        if sim is not None:
            try:
                has_share = bool(sim.pending_share_events())
            except Exception:
                has_share = False
        return {"has_pending_share": has_share}

    def gate(self, perceived: dict[str, Any]) -> str:
        return RULE if perceived["has_pending_share"] else SKIP

    async def act(
        self, session_key: str, mode: str, perceived: dict[str, Any], phase: str = PRE
    ) -> AgentIntent | None:
        if phase != PRE:
            return None
        sim = getattr(self._p, "_life_simulator", None)
        if sim is None:
            return None
        try:
            ctx = sim.recent_context_for_prompt(limit=3)
        except Exception:
            return None
        if not ctx:
            return None
        return AgentIntent(source=self.name, payload={"life_context": ctx}, priority=0.3)
