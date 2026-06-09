"""EmotionAgent：情绪表达/边界守护 worker（CP8-P3a）。

切法 X：leader(SDK kernel) 算情绪数值，EmotionAgent 管"对情绪状态的行为反应"
——把情绪强度/边界压力翻译成影响本轮计算的 flags/affect。

时点：PRE（请求发出前产意图，影响 host event 的 flags/confidence/values）。
门控：边界压力逼近或强情绪 → LLM 谨慎措辞；情绪平淡 → SKIP。
"""

from __future__ import annotations

from typing import Any

from sylanne_alpha.agents.base import LLM, PRE, RULE, SKIP, AgentIntent, CognitiveAgent
from sylanne_alpha.agents.event_bus import BoundaryBreached, ExpressionDriveHigh


class EmotionAgent(CognitiveAgent):
    name = "emotion"
    phases = (PRE,)

    def perceive(self, surface: dict[str, Any]) -> dict[str, Any]:
        hp = surface.get("host_payload", {})
        emo = hp.get("affect_dynamics", {}).get("computation_emotion", {})
        body = surface.get("body", {})
        immunity = body.get("immunity", {})
        traits = hp.get("personality", {}).get("traits", {})
        return {
            "valence": float(emo.get("valence", 0.0)),
            "arousal": float(emo.get("arousal", 0.0)),
            "tension": float(emo.get("tension", 0.0)),
            "expression_drive": float(emo.get("expression_drive", 0.0)),
            "boundary_firmness": float(emo.get("boundary_firmness", 0.0)),
            "boundary_pressure": float(immunity.get("boundary_pressure", 0.0)),
            "sovereignty_guard": float(traits.get("sovereignty_guard", 0.5)),
            "edge": float(traits.get("edge", 0.5)),
        }

    def gate(self, perceived: dict[str, Any]) -> str:
        bp = perceived["boundary_pressure"]
        # 边界压力阈值是人格函数：sovereignty_guard 越高越早触发谨慎
        bp_threshold = 0.7 - 0.3 * perceived["sovereignty_guard"]
        if bp > bp_threshold:
            return LLM  # 边界逼近，需谨慎措辞
        intensity = max(abs(perceived["valence"]), perceived["arousal"], perceived["tension"])
        intensity_threshold = 0.6 - 0.2 * perceived["edge"]
        if intensity > intensity_threshold:
            return LLM  # 强情绪，需 LLM 组织表达
        if intensity < 0.2:
            return SKIP  # 情绪平淡，省略
        return RULE

    async def act(
        self, session_key: str, mode: str, perceived: dict[str, Any], phase: str = PRE
    ) -> AgentIntent | None:
        if phase != PRE:
            return None
        flags: list[str] = []
        bp = perceived["boundary_pressure"]
        if bp > 0.6:
            flags.append("boundary")
            self.emit(BoundaryBreached(source=self.name, session_key=session_key, pressure=bp))
        if perceived["valence"] < -0.4:
            flags.append("hurt")
        if perceived["expression_drive"] > 0.6:
            self.emit(ExpressionDriveHigh(
                source=self.name, session_key=session_key, drive=perceived["expression_drive"]
            ))
        affect = {
            "valence": perceived["valence"],
            "arousal": perceived["arousal"],
        }
        # priority 随强度提升：越强的情绪在融合中权重越大
        priority = 0.5 + 0.5 * max(abs(perceived["valence"]), perceived["arousal"])
        return AgentIntent(
            source=self.name,
            flags=flags,
            affect=affect,
            priority=min(1.0, priority),
        )
