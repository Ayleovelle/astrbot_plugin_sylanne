"""SocialAgent：群体氛围感知 worker（CP8-P3a）。

时点：POST（消化本轮——群聊上下文下通知社交场 bot 已回复，重置社交沉默）。
纯统计，零 LLM。收编 _social_field.notify_bot_replied（响应后调用方）。
"""

from __future__ import annotations

from typing import Any

from sylanne_alpha.agents.base import POST, RULE, SKIP, AgentIntent, CognitiveAgent


class SocialAgent(CognitiveAgent):
    name = "social"
    phases = (POST,)

    def perceive(self, surface: dict[str, Any]) -> dict[str, Any]:
        # 是否群聊上下文由 session_key 形态/social_field 判定，此处取本轮 bot 文本
        bot_text = self._p._store.last_bot_texts.get("__last__", "")
        return {"bot_text": bot_text}

    def gate(self, perceived: dict[str, Any]) -> str:
        sf = getattr(self._p, "_social_field", None)
        return RULE if sf is not None else SKIP

    async def act(
        self, session_key: str, mode: str, perceived: dict[str, Any], phase: str = POST
    ) -> AgentIntent | None:
        if phase != POST:
            return None
        sf = getattr(self._p, "_social_field", None)
        if sf is None:
            return None
        bot_text = self._p._store.last_bot_texts.get(session_key, "")
        if not bot_text:
            return None
        try:
            # group_id 由 session_key 推导（社交场内部按 group 维护）
            sf.notify_bot_replied(session_key, bot_text)
        except Exception:
            pass
        return None
