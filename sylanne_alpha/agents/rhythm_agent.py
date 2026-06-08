"""RhythmAgent：对话节奏学习 worker（CP8-P3a 第一个真收编样板）。

收编现有管线中散落的节奏学习调用，成为 _rhythm_learner.observe_user_message 的
唯一调用方，消除 on_message(T1 _record_tempo) 与 _background_observe_request(T5)
对同一会话 tempo 的潜在双记。

时点：POST（host 计算完出新 surface 后消化结果、更新节奏画像）。
门控：复用 RhythmLearner.is_intimate 逻辑——亲密度够才学习节奏（否则只记 tempo）。
"""

from __future__ import annotations

from typing import Any

from sylanne_alpha.agents.base import POST, RULE, AgentIntent, CognitiveAgent


class RhythmAgent(CognitiveAgent):
    """节奏学习官能。POST 时点消化本轮计算结果，更新对话节奏画像。"""

    name = "rhythm"
    phases = (POST,)

    def perceive(self, surface: dict[str, Any]) -> dict[str, Any]:
        """从 surface 抽取情感信号（warmth/coherence/tension），供门控判亲密度。"""
        emo = (
            surface.get("host_payload", {})
            .get("affect_dynamics", {})
            .get("computation_emotion", {})
        )
        return {
            "warmth": float(emo.get("warmth", 0.0)),
            "coherence": float(emo.get("coherence", 1.0)),
            "tension": float(emo.get("tension", 0.0)),
        }

    def gate(self, perceived: dict[str, Any]) -> str:
        """节奏学习始终需要记录（tempo 不受门控），故恒 RULE（廉价，零 LLM）。

        是否进入"亲密学习"由 observe_user_message 内部的 is_intimate 再判，
        这里只决定"要不要跑 act"——只要有本轮消息就跑。
        """
        return RULE

    async def act(
        self, session_key: str, mode: str, perceived: dict[str, Any], phase: str = POST
    ) -> AgentIntent | None:
        """收编：调 _rhythm_learner.observe_user_message（成唯一调用方）。

        需要本轮用户文本与 engine 观测。文本取自本轮缓存的最后用户文本，
        engine_observation 取自当前 host 计算栈。无副作用以外的意图贡献，返回 None。
        """
        if phase != POST:
            return None
        p = self._p
        text = p._store.last_user_texts.get(session_key, "")
        if not text:
            return None
        host = p._store.hosts.get(session_key)
        if host is None:
            return None
        try:
            engine_obs = host.kernel.computation.engine.observe()
        except Exception:
            engine_obs = {}
        import time as _time

        p._rhythm_learner.observe_user_message(session_key, text, _time.time(), engine_obs)
        return None
