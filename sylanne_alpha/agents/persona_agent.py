"""PersonaAgent：人格一致性守护 worker（CP8-P3a）。

切法 X：leader 算人格数值，PersonaAgent 管"人格一致性守护/投射策略"。
时点：PRE。门控：一致性(coherence)破裂 → LLM 重整；轻微漂移 → RULE 微调。
"""

from __future__ import annotations

from typing import Any

from sylanne_alpha.agents.base import LLM, PRE, RULE, SKIP, AgentIntent, CognitiveAgent


class PersonaAgent(CognitiveAgent):
    name = "persona"
    phases = (PRE,)

    def perceive(self, surface: dict[str, Any]) -> dict[str, Any]:
        hp = surface.get("host_payload", {})
        emo = hp.get("affect_dynamics", {}).get("computation_emotion", {})
        drift = hp.get("personality", {}).get("drift", {})
        return {
            "coherence": float(emo.get("coherence", 1.0)),
            "plasticity": float(drift.get("plasticity", 0.0)),
        }

    def gate(self, perceived: dict[str, Any]) -> str:
        coher = perceived["coherence"]
        if coher < 0.45:
            return LLM  # 一致性破裂，需重整人格投射
        if perceived["plasticity"] < 0.3 and coher > 0.7:
            return SKIP  # 人格稳，无需介入
        return RULE

    async def act(
        self, session_key: str, mode: str, perceived: dict[str, Any], phase: str = PRE
    ) -> AgentIntent | None:
        if phase != PRE:
            return None
        # 人格守护以"低 confidence_hint"提示计算层在一致性低时更谨慎
        if perceived["coherence"] < 0.45:
            return AgentIntent(
                source=self.name,
                confidence_hint=0.4,
                priority=0.6,
                payload={"persona_caution": "low_coherence"},
            )
        return None
