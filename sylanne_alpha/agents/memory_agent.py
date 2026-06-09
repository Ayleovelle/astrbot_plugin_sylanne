"""MemoryAgent：记忆召回/巩固 worker（CP8-P3a）。

PRE：关系够亲密且检测到回忆触发时，召回记忆作为高层意图(payload)托管给 SelfCore
（SDK 吃不下结构化记忆内容，由 SelfCore 拼回 surface 供 prompt 注入）。
POST：消化本轮——记忆衰减 tick。
"""

from __future__ import annotations

from typing import Any

from sylanne_alpha.agents.base import (
    POST,
    PRE,
    RULE,
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
        # CP8-P6：gate 恒 RULE，避免误杀 POST 的 tick_decay（记忆衰减是必跑的维护，
        # 浅关系下也要执行）。是否值得 LLM 深度检索 / 是否够亲密召回，由 act 内按
        # phase + 阈值自行判定（阈值=人格函数 base 0.35 + 学习偏置，带钳位护栏）。
        return RULE

    async def act(
        self, session_key: str, mode: str, perceived: dict[str, Any], phase: str = PRE
    ) -> AgentIntent | None:
        p = self._p
        if phase == POST:
            # 消化：记忆衰减（收编自管线的 tick_decay）——必跑，不受亲密度门控
            try:
                ms = p._memory_system_for_session(session_key)
                ms.tick_decay()
            except Exception:
                pass
            return None
        # PRE：关系够亲密才主动翻记忆（阈值是人格函数 + 学习偏置）
        intim = perceived["intimacy_gravity"]
        evo = perceived.get("_evo_delta")
        thr = 0.35 + (evo("intimacy_threshold") if callable(evo) else 0.0)
        if intim < thr:
            return None
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
