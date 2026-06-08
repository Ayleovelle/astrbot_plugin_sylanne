"""DialogueAgent：组织最终表达 worker（CP8-P3a）。

时点：POST（消化本轮——基于 surface 的 decision/guard 判断表达，广播回复观测）。
门控：decision.action==wait 或 guard 不允许 → SKIP；真要说话 → LLM(组织表达)。
注：分段执行(realtime_plan)是纯函数留管线，DialogueAgent 管"对表达的认知判断"。
"""

from __future__ import annotations

from typing import Any

from sylanne_alpha.agents.base import LLM, RESPONSE_POST, SKIP, AgentIntent, CognitiveAgent
from sylanne_alpha.agents.event_bus import ResponseObserved


class DialogueAgent(CognitiveAgent):
    name = "dialogue"
    phases = (RESPONSE_POST,)

    def perceive(self, surface: dict[str, Any]) -> dict[str, Any]:
        decision = surface.get("decision", {})
        guard = surface.get("guard", {})
        return {
            "action": str(decision.get("action", "")),
            "allowed": bool(guard.get("allowed", True)),
            "confidence": float(decision.get("confidence", 0.0)),
        }

    def gate(self, perceived: dict[str, Any]) -> str:
        if perceived["action"] == "wait":
            return SKIP
        if not perceived["allowed"]:
            return SKIP
        return LLM  # 真要说话，组织表达（回话主调用）

    async def act(
        self, session_key: str, mode: str, perceived: dict[str, Any], phase: str = RESPONSE_POST
    ) -> AgentIntent | None:
        if phase != RESPONSE_POST:
            return None
        bot_text = self._p._store.last_bot_texts.get(session_key, "")
        self.emit(ResponseObserved(
            source=self.name, session_key=session_key,
            text=bot_text, confidence=perceived["confidence"],
        ))
        return None
