"""SocialAgent：群体氛围感知 worker（CP8-P3a）。

时点：POST（消化本轮——群聊上下文下通知社交场 bot 已回复，重置社交沉默）。
纯统计，零 LLM。收编 _social_field.notify_bot_replied（响应后调用方）。
"""

from __future__ import annotations

from typing import Any

from sylanne_alpha.agents.base import RESPONSE_POST, RULE, SKIP, AgentIntent, CognitiveAgent


class SocialAgent(CognitiveAgent):
    name = "social"
    phases = (RESPONSE_POST,)

    def perceive(self, surface: dict[str, Any]) -> dict[str, Any]:
        # 是否群聊上下文由 session_key 形态/social_field 判定，此处取本轮 bot 文本
        bot_text = self._p._store.last_bot_texts.get("__last__", "")
        return {"bot_text": bot_text}

    def gate(self, perceived: dict[str, Any]) -> str:
        sf = getattr(self._p, "_social_field", None)
        return RULE if sf is not None else SKIP

    async def act(
        self, session_key: str, mode: str, perceived: dict[str, Any], phase: str = RESPONSE_POST
    ) -> AgentIntent | None:
        if phase != RESPONSE_POST:
            return None
        sf = getattr(self._p, "_social_field", None)
        if sf is None:
            return None
        # 仅群聊上下文才通知社交场。group_id 须经 social_field 自己的解析（非 session_key）。
        try:
            if not sf.is_group_context_by_key(session_key):
                return None
            bot_text = self._p._store.last_bot_texts.get(session_key, "")
            if not bot_text:
                return None
            group_id = sf.extract_group_id_from_key(session_key)
            sf.notify_bot_replied(group_id, bot_text)
        except Exception:
            pass
        return None
