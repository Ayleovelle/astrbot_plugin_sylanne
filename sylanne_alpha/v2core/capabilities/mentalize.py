"""Mentalize + Appraisal —— 预测你 + 真评价（Fable 重做版）。

MentalizeCapability：
- PERCEPT：经 UserModelDomain 预判你这条消息的处置，挂 scratch["you_probably"]。
  【真实消费者】fragment.build_mind_fragment ——"对你"一行进入 LLM system prompt，
  她对你的模型从此真的影响她说出的话（旧版此信号无人消费）。
- DELIBERATE：失同步时产"想跟你确认"意图（flag="speak_drive"，IgnitionArbiter 计入
  表达驱力——失同步是开口的理由之一）。

AppraisalCapability（PERCEPT）：对【你这条消息本身】做多维评价——旧版只读 body
（把她自己的心情回声成"评价"），本版评价的是刺激：
- 效价证据  ← lexicon 文本信号（warm−cold）
- 苦恼证据  ← distress 信号（→ wound_risk）
- 期望失配  ← UserModel.expectation() vs 本条证据（你反常 → 唤起）
- 触动反常  ← Distill.atypicality()（这条对我身体的触动不寻常 → 唤起）
- novelty   ← body.surprise（canonical PE，不重算）

产出 scratch["assessment"]={valence,arousal,wound_risk}。
【真实入体通道】：llm_request_pipeline 在 host.on_request(assessment=…) 处合并它
（apply_assessment 是 SDK 唯一消费 assessment 的入口，实测 on_response 不收）。
不再有旧版"空文本补一拍 request tick"的统计污染。不产 intent 标签——绝不喂
computation_spine 里 intent=="撒娇" 的硬编码路径。

铁律②：评价值不 clamp 上限（valence 天然 [-1,1] 语义域除外——那是量纲不是闸）。
"""

from __future__ import annotations

import math
from typing import Any

from sylanne_alpha.v2core.contracts import BeatContext, Intent, Phase
from sylanne_alpha.v2core.lexicon import TextSignals, read_signals


class MentalizeCapability:
    """读心：PERCEPT 预判你（喂心象片段），DELIBERATE 失同步求澄清（喂点火）。无独占态。"""

    name = "mentalize"
    phases = (Phase.PERCEPT, Phase.DELIBERATE)

    def __init__(self, *, sync_floor: float = 0.4, priority: float = 0.5) -> None:
        self._sync_floor = sync_floor
        self._priority = priority

    def perceive(self, ctx: BeatContext) -> Intent | None:
        um = ctx.domain("usermodel")
        if um is None or not ctx.text:
            return None
        view = um.predict_you(ctx.body, ctx.text)
        # 消费者：fragment.build_mind_fragment（"对你"行）
        ctx.scratch["you_probably"] = {
            "disposition": view.predicted_disposition,
            "grip": view.grip,
            "synchrony": view.synchrony,
        }
        return Intent(
            source=self.name,
            payload={"you_probably": view.predicted_disposition, "grip": view.grip},
            priority=self._priority * view.grip,
            confidence=view.grip,
        )

    def deliberate(self, ctx: BeatContext) -> Intent | None:
        um = ctx.domain("usermodel")
        if um is None:
            return None
        sync = float(um.synchrony())
        if sync >= self._sync_floor:
            return None
        urgency = self._sync_floor - sync
        # flag="speak_drive"：IgnitionArbiter 据此计入表达驱力（失同步推她开口确认）
        return Intent(
            source=self.name,
            payload={"want": "clarify_you", "synchrony": sync},
            priority=min(1.0, self._priority + urgency),
            confidence=1.0 - sync,
            flags=("speak_drive",),
        )


class AppraisalCapability:
    """评价：PERCEPT 对你这条消息做多维评价 → scratch["assessment"]（request tick 入体）。"""

    name = "appraisal"
    phases = (Phase.PERCEPT,)

    def __init__(self, *, priority: float = 0.6) -> None:
        self._priority = priority

    def perceive(self, ctx: BeatContext) -> Intent | None:
        text = ctx.text or ""
        if not text:
            return None
        body = ctx.body
        sig: TextSignals = ctx.scratch.get("signals") or read_signals(text)

        # —— 证据收集（全部关于刺激，不是她自己的心情回声）——
        valence_cue = sig.valence_cue                      # 文本效价（有符号）
        distress_cue = sig.distress                        # 苦恼线索
        novelty = float(body.surprise)                     # canonical PE

        expectancy_violation = 0.0
        um = ctx.domain("usermodel")
        if um is not None and hasattr(um, "expectation"):
            try:
                from sylanne_alpha.v2core.domains.user_model import evidence_from_signals
                expect = um.expectation()
                actual = evidence_from_signals(sig)
                if actual:
                    expectancy_violation = math.sqrt(sum(
                        (actual.get(k, 0.0) - expect.get(k, 0.0)) ** 2 for k in expect
                    ) / max(1, len(expect)))
            except Exception:
                expectancy_violation = 0.0

        atypical = 0.0
        distill = ctx.domain("distill")
        if distill is not None and hasattr(distill, "atypicality"):
            try:
                atypical = float(distill.atypicality(text, body))
            except Exception:
                atypical = 0.0

        # —— 评价 → assessment（SDK apply_assessment 的真实消费键）——
        # valence ∈ [-1,1] 语义域：tanh 是量纲映射不是安全闸（文本密度无上界）。
        valence = math.tanh(valence_cue - 0.6 * distress_cue)
        arousal = novelty * 0.4 + expectancy_violation * 0.3 + atypical * 0.3 + sig.exclaim * 0.2
        wound_risk = min(1.0, distress_cue * 0.5 + max(0.0, -valence_cue) * 0.4)

        appraisal = {
            "valence": round(valence, 4),
            "arousal": round(arousal, 4),
            "wound_risk": round(wound_risk, 4),
            "novelty": round(novelty, 4),
            "expectancy_violation": round(expectancy_violation, 4),
            "atypicality": round(atypical, 4),
        }
        # 消费者①：integration.consume_pending_assessment → host.on_request(assessment=…)
        ctx.scratch["assessment"] = {
            "valence": appraisal["valence"],
            "arousal": appraisal["arousal"],
            "wound_risk": appraisal["wound_risk"],
        }
        # 消费者②：fragment（评价摘要不进片段，但 observability intent 供调试/测试断言）
        return Intent(source=self.name, payload={"appraisal": appraisal},
                      priority=self._priority, confidence=None)


__all__ = ["MentalizeCapability", "AppraisalCapability"]
