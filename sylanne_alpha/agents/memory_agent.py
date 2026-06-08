"""MemoryAgent：记忆召回/巩固 worker（CP8-P3a）。

PRE：关系够亲密且检测到回忆触发时，召回记忆作为高层意图(payload)托管给 SelfCore
（SDK 吃不下结构化记忆内容，由 SelfCore 拼回 surface 供 prompt 注入）。
POST：消化本轮——记忆衰减 tick。
"""

from __future__ import annotations

from typing import Any

from sylanne_alpha.agents.base import (
    LLM,
    POST,
    PRE,
    RULE,
    SKIP,
    AgentIntent,
    CognitiveAgent,
)


class MemoryAgent(CognitiveAgent):
    name = "memory"
    phases = (PRE, POST)

    def perceive(self, surface: dict[str, Any]) -> dict[str, Any]:
        hp = surface.get("host_payload", {})
        traits = hp.get("personality", {}).get("traits", {})
        emo = hp.get("affect_dynamics", {}).get("computation_emotion", {})
        return {
            "intimacy_gravity": float(traits.get("intimacy_gravity", 0.5)),
            "warmth": float(emo.get("warmth", 0.0)),
            "repair_pressure": float(emo.get("repair_pressure", 0.0)),
        }

    def gate(self, perceived: dict[str, Any]) -> str:
        intim = perceived["intimacy_gravity"]
        # 关系太浅不主动翻记忆（阈值是人格函数）
        if intim < 0.35:
            return SKIP
        # 修复压力高 → 深度关联检索值得 LLM；否则廉价 KV 召回
        if perceived["repair_pressure"] > 0.6 and intim > 0.65:
            return LLM
        return RULE

    async def act(
        self, session_key: str, mode: str, perceived: dict[str, Any], phase: str = PRE
    ) -> AgentIntent | None:
        p = self._p
        if phase == POST:
            # 消化：记忆衰减（收编自管线的 tick_decay）
            try:
                ms = p._memory_system_for_session(session_key)
                ms.tick_decay()
            except Exception:
                pass
            return None
        # PRE：召回，作为高层意图托管
        text = p._store.last_user_texts.get(session_key, "")
        if not text:
            return None
        try:
            ms = p._memory_system_for_session(session_key)
            results = ms.recall(text, None, perceived["warmth"], limit=3)
        except Exception:
            return None
        if not results:
            return None
        recalled = [getattr(r, "text", str(r)) for r in results]
        return AgentIntent(
            source=self.name,
            payload={"recalled_memories": recalled},
            priority=0.4,
        )
