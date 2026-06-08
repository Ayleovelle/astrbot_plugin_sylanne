"""ProactiveAgent：主动开口决策 worker（CP8-P3a）。

时点：POST（消化本轮 surface，判断是否该主动开口；主动发言本质在响应后/空闲时）。
门控：guard.allowed + decision.action∈{express,reach_out} + 不怕打扰 + 表达欲强。
收编：proactive_scheduler 的发言决策（成唯一决策方）。
"""

from __future__ import annotations

from typing import Any

from sylanne_alpha.agents.base import POST, RULE, SKIP, AgentIntent, CognitiveAgent
from sylanne_alpha.agents.event_bus import OutreachReady


class ProactiveAgent(CognitiveAgent):
    name = "proactive"
    phases = (POST,)

    def perceive(self, surface: dict[str, Any]) -> dict[str, Any]:
        hp = surface.get("host_payload", {})
        body = surface.get("body", {})
        needs = body.get("needs", {})
        immunity = body.get("immunity", {})
        decision = surface.get("decision", {})
        guard = surface.get("guard", {})
        traits = hp.get("personality", {}).get("traits", {})
        return {
            "allowed": bool(guard.get("allowed", True)),
            "action": str(decision.get("action", "")),
            "need_expression": float(needs.get("need_expression", 0.0)),
            "boundary_pressure": float(immunity.get("boundary_pressure", 0.0)),
            "sovereignty_guard": float(traits.get("sovereignty_guard", 0.5)),
            "intimacy_gravity": float(traits.get("intimacy_gravity", 0.5)),
        }

    def gate(self, perceived: dict[str, Any]) -> str:
        if not perceived["allowed"]:
            return SKIP  # 守卫不允许，硬停
        if perceived["action"] not in ("express", "reach_out"):
            return SKIP  # 决策层无开口意图
        # 怕打扰：边界压力阈值是人格函数
        if perceived["boundary_pressure"] > 0.4 + 0.3 * perceived["sovereignty_guard"]:
            return SKIP
        # 表达欲阈值是人格函数（intimacy 越高越易开口）
        if perceived["need_expression"] > 0.6 - 0.2 * perceived["intimacy_gravity"]:
            return RULE
        return SKIP

    async def act(
        self, session_key: str, mode: str, perceived: dict[str, Any], phase: str = POST
    ) -> AgentIntent | None:
        if phase != POST:
            return None
        # 广播主动开口就绪信号（DialogueAgent 等可订阅）
        self.emit(OutreachReady(
            source=self.name, session_key=session_key,
            reason="need_expression_high", mood="",
        ))
        return None
