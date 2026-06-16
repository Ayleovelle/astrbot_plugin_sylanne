"""ExpressionCapability —— 表达驱力 + 表达风格倾向（Fable 重做版）。

两个产物、两个真实消费者，分属两拍（时序纪律，review F1 修复）：
1. 表达风格（PERCEPT 拍 → scratch["express"]）→ fragment.build_mind_fragment 的
   "表达倾向"行，作为口吻提示进 LLM system prompt——浓度/节奏/停顿真正影响她
   怎么说话。fragment 在宿主 request 阶段构建，所以风格必须在 PERCEPT 拍就挂上
   （旧版挂在 DELIBERATE 拍 = fragment 永远读不到的死信号，docstring 还说接了）。
   PERCEPT 阶段本轮召回还没发生 → has_recall 诚实为 False，不假装知道。
2. 表达驱力（DELIBERATE 拍 Intent，flag="speak_drive"）→ IgnitionArbiter 计入
   eff_drive。驱力 = 基础倾向 + 情绪账本的未表达冲动（憋得越久越想说）。
   intent payload 同时带 DELIBERATE 时点的完整风格（含召回加成）供观测/测试断言。

铁律②：intensity/segment_bias/pause_bias 线性叠加不 clamp、不封顶。
铁律①：无独占态，经 ctx.domain("emotion") 只读。
"""

from __future__ import annotations

from typing import Any

from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Intent, Phase


def compose_style(body: BodySnapshot, *, arousal: float = 0.0, valence: float = 0.0,
                  volatility: float = 0.0, has_recall: bool = False) -> dict[str, Any]:
    """躯体+情绪 → 表达风格倾向的唯一公式（单一来源；纯函数，零状态）。

    两个调用点：perceive（request 阶段挂 scratch，喂 fragment）与 deliberate
    （intent payload，含召回加成，供观测）。线性叠加不 clamp（铁律②）。
    """
    intensity = (abs(body.warmth) + body.tension + body.repair_pressure
                 + abs(arousal) + volatility)
    warm_drive = body.warmth if body.warmth > 0.0 else 0.0
    segment_bias = intensity + warm_drive + (0.2 if has_recall else 0.0)
    pause_bias = (body.tension + body.repair_pressure
                  + (abs(valence) if valence < 0.0 else 0.0))
    return {
        "intensity": intensity,
        "segment_bias": segment_bias,
        "pause_bias": pause_bias,
        "warmth": body.warmth,
        "valence": valence,
        "has_recall": has_recall,
    }


class ExpressionCapability:
    """表达能力：PERCEPT 拍产风格倾向（喂心象），DELIBERATE 拍产驱力（喂点火）。全局无状态。"""

    name = "expression"
    phases = (Phase.PERCEPT, Phase.DELIBERATE)

    def __init__(self, *, priority: float = 0.5) -> None:
        self._priority = priority

    @staticmethod
    def _emotion_view(ctx: BeatContext) -> tuple[float, float, float]:
        """经情绪域只读接口取 (arousal, valence, volatility)；缺域/异常 → 中性零。"""
        emotion = ctx.domain("emotion")
        if emotion is None:
            return 0.0, 0.0, 0.0
        try:
            view = emotion.view(ctx.body)
            return (float(getattr(view, "arousal", 0.0)),
                    float(getattr(view, "valence", 0.0)),
                    float(getattr(view, "volatility", 0.0)))
        except Exception:
            return 0.0, 0.0, 0.0

    def perceive(self, ctx: BeatContext) -> Intent | None:
        """PERCEPT：算表达风格挂 scratch["express"]——fragment 唯一吃得到的时机。

        消费者：fragment.build_mind_fragment._style_line（request 阶段心象片段）。
        本拍召回未发生，has_recall=False 是诚实事实，不是缺陷。不产 intent。
        """
        arousal, valence, volatility = self._emotion_view(ctx)
        ctx.scratch["express"] = compose_style(
            ctx.body, arousal=arousal, valence=valence,
            volatility=volatility, has_recall=False,
        )
        return None

    def deliberate(self, ctx: BeatContext) -> Intent | None:
        """DELIBERATE：表达驱力 intent（消费者：IgnitionArbiter，经 flag="speak_drive"）。"""
        arousal, valence, volatility = self._emotion_view(ctx)

        drive_urgency = 0.0
        emotion = ctx.domain("emotion")
        if emotion is not None:
            try:
                drive = emotion.drive(ctx.body)
                if drive is not None:
                    # 归一只供权重（不回写真值，铁律②）：憋得越久，开口倾向越强
                    drive_urgency = float(drive.normalized(scale=2.0))
            except Exception:
                pass

        # DELIBERATE 时点的完整风格（含召回加成）——只进 payload 供观测/测试，
        # 不回写 scratch["express"]（fragment 已在 request 阶段消费完毕，回写无下游）。
        express = compose_style(
            ctx.body, arousal=arousal, valence=valence, volatility=volatility,
            has_recall=bool(ctx.scratch.get("recalled")),
        )

        drive_strength = self._priority + 0.5 * drive_urgency
        return Intent(source=self.name, payload={"express": express},
                      priority=min(1.0, drive_strength), flags=("speak_drive",))


__all__ = ["compose_style", "ExpressionCapability"]
