"""AssessorAgent：自我评估 worker（CP8-P3a）。

时点：PRE（评估用户消息的情感维度，产出 affect 影响本轮计算）。
收编 AsyncAssessor 的 fast/main 双层评估（成唯一调用方）。
门控：完整路径消息 → LLM(main 评估)；普通 → LLM(fast 评估，更轻)。
"""

from __future__ import annotations

from typing import Any

from sylanne_alpha.agents.base import LLM, PRE, AgentIntent, CognitiveAgent


class AssessorAgent(CognitiveAgent):
    name = "assessor"
    phases = (PRE,)

    def perceive(self, surface: dict[str, Any]) -> dict[str, Any]:
        return {}

    def gate(self, perceived: dict[str, Any]) -> str:
        # 评估恒需进行（情感维度是计算的关键输入），始终 LLM 档
        # 受全局预算闸约束，超预算时 SelfCore 会降级
        return LLM

    async def act(
        self, session_key: str, mode: str, perceived: dict[str, Any], phase: str = PRE
    ) -> AgentIntent | None:
        if phase != PRE:
            return None
        p = self._p
        text = p._store.last_user_texts.get(session_key, "")
        if not text:
            return None
        assessor = getattr(p, "_async_assessor", None)
        llm_caller = getattr(p, "_assessor_llm_call", None)
        if assessor is None or llm_caller is None:
            return None
        try:
            result = await assessor.assess_fast(text, llm_caller)
        except Exception:
            return None
        if not result:
            return None
        affect = {
            k: float(result[k])
            for k in ("valence", "arousal", "wound_risk")
            if k in result and isinstance(result[k], (int, float))
        }
        if not affect:
            return None
        return AgentIntent(source=self.name, affect=affect, priority=0.7)
