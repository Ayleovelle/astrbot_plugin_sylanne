"""DialogueAgent：组织最终表达 worker（CP8-P3a）+ 对话质量自评进化（CP8-P4）。

时点：RESPONSE_POST（bot 回复后——广播回复观测 + 算 self_score 质量自评，
质量信号经 feedback_quality 反馈进人格漂移，实现"越聊回复越校准"）。

注：self_score 是启发式自评（弱信号），只作人格漂移的弱先验，不作强监督
（防 Goodhart 陷阱——自评高分≠用户满意）。质量阈值保守。
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
        p = self._p
        bot_text = p._store.last_bot_texts.get(session_key, "")
        user_text = p._store.last_user_texts.get(session_key, "")
        self.emit(ResponseObserved(
            source=self.name, session_key=session_key,
            text=bot_text, confidence=perceived["confidence"],
        ))
        # CP8-P4：对话质量自评 → 人格漂移反馈（self_score 零 LLM，启发式弱信号）
        if bot_text and user_text:
            try:
                from sylanne_alpha.dialogue import self_score
                score = self_score(user_text, bot_text)
                # 三维均值作综合质量；阈值保守（防自评噪声驱动激进漂移）
                quality = (
                    score.get("coherence", 0.0)
                    + score.get("emotion_match", 0.0)
                    + score.get("info_density", 0.0)
                ) / 3.0
                host = p._store.hosts.get(session_key)
                comp = getattr(getattr(host, "kernel", None), "computation", None)
                fq = getattr(comp, "feedback_quality", None)
                if callable(fq):
                    if quality >= 0.7:
                        fq("dialogue_quality_high")
                    elif quality <= 0.35:
                        fq("dialogue_quality_low")
            except Exception:
                pass
        return None
