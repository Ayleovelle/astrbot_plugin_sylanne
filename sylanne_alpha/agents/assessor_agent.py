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
        if assessor is None:
            return None
        fast_result: dict = {}
        main_result: dict = {}
        # fast 层（小模型，始终；若启用）
        if p._cfg_bool("sylanne_alpha_assessor_llm_enabled"):
            try:
                fast_result = await assessor.assess_fast(text, p._assessor_llm_call)
            except Exception:
                fast_result = {}
        # main 层（强模型，更长上下文；若启用）——完整保留现有精度，不降级
        if p._cfg_bool("sylanne_alpha_main_assessor_enabled"):
            try:
                context_lines = p._recent_context_lines(session_key)
                main_result = await assessor.assess_main(
                    text, context_lines, p._main_assessor_llm_call
                )
            except Exception:
                main_result = {}
        merged = {**fast_result, **main_result}  # main 覆盖 fast，与原管线一致
        merged.pop("_level", None)
        merged.pop("assessed_at", None)
        affect = {
            k: float(merged[k])
            for k in ("valence", "arousal", "wound_risk")
            if k in merged and isinstance(merged[k], (int, float))
        }
        if not affect:
            return None
        return AgentIntent(source=self.name, affect=affect, priority=0.7)
