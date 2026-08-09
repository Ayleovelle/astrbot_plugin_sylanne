"""SomaticMarker + Outreach —— 内感受偏置 + 沉默积累主动（Fable 重做版）。

SomaticMarker（DELIBERATE 首位）：读 scar/strain/sovereignty/exhaustion 产连续行动
偏置（Damasio 1996 躯体标记取其精神：身体状态偏置决策，不替代决策）。

【真实消费者清单】（旧版四个偏置全是死信号，本版每个都有下游）：
- approach_recall   → RecallCapability：结疤越深越回避翻旧事（负值跳过召回）
- approach_initiate → OutreachCapability：耗竭/低主权时 reach 压力打折
- guard / soften    → fragment.build_mind_fragment："表达倾向"行（防御/软化措辞提示
                      进 LLM system prompt，真正影响她的口吻）。时序纪律（review F2）：
                      fragment 在宿主 request 阶段构建，DELIBERATE 拍的 SomaticBias
                      它拿不到——故 fragment 直接调 guard_soften_from_body 从同一
                      body 公式同源取值。单一来源函数保证两处永不漂移。

Outreach（DELIBERATE，仅空闲轮）：沉默不是 idle——reply_overdue（你的节律超期）+
hold_free_energy（未表达积分）+ 躯体余力，合成 reach 压力。消费者：IgnitionArbiter
空闲轮三选一 argmin + integration.consult_idle_reach（自驱心跳真入口，胜出即走既有
主动发言调度，吃它全部冷却/静默闸——防连发不靠新阀门，靠既有机制）。

铁律②：偏置有符号、不封顶、不 clamp；只产倾向不设阀。
"""

from __future__ import annotations

from dataclasses import dataclass

from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Intent, Phase


@dataclass(frozen=True, slots=True)
class SomaticBias:
    """行动倾向向量。全部有符号、不封顶（铁律②）。"""

    approach_recall: float      # >0 趋近召回，<0 回避翻旧事
    approach_initiate: float    # >0 有余力主动，<0 退缩
    guard: float                # 防御性措辞强度
    soften: float               # 软化/修补倾向
    dominant: str               # 主导躯体量（可观测）


def guard_soften_from_body(b: BodySnapshot) -> tuple[float, float]:
    """躯体 → (guard, soften) 措辞偏置的唯一公式（单一来源，review F2）。

    两个消费者同源：SomaticMarkerCapability.deliberate（DELIBERATE 拍 SomaticBias，
    喂 recall/outreach）与 fragment._style_line（request 阶段心象"表达倾向"行）。
    request 阶段 DELIBERATE 还没跑，fragment 不可能消费 scratch["somatic_bias"]——
    它直接调本函数从同一 body 公式取值。改公式只改这里。不 clamp（铁律②）。
    """
    guard = (1.0 - float(b.sovereignty)) + 0.3 * float(b.strain)
    soften = float(b.repair_pressure) + 0.2 * float(b.scar)
    return guard, soften


class SomaticMarkerCapability:
    """躯体标记：DELIBERATE 首位产连续偏置。无独占态。"""

    name = "somatic_marker"
    phases = (Phase.DELIBERATE,)

    def deliberate(self, ctx: BeatContext) -> Intent | None:
        b = ctx.body
        scar = float(b.scar)
        strain = float(b.strain)
        sov = float(b.sovereignty)
        exhaustion = float(b.exhaustion)

        guard, soften = guard_soften_from_body(b)
        bias = SomaticBias(
            approach_recall=0.5 - scar - 0.3 * strain,
            approach_initiate=(sov - exhaustion) - 0.2 * strain,
            guard=guard,
            soften=soften,
            dominant=_dominant_marker(scar, strain, sov, exhaustion),
        )
        # 消费者：RecallCapability / OutreachCapability / fragment（见模块 docstring）
        ctx.scratch["somatic_bias"] = bias
        return Intent(
            source=self.name,
            payload={"somatic": {"approach_recall": bias.approach_recall,
                                 "approach_initiate": bias.approach_initiate,
                                 "guard": bias.guard, "soften": bias.soften,
                                 "dominant": bias.dominant}},
            priority=0.0,   # 偏置不直接参与表达驱力
        )


def _dominant_marker(scar: float, strain: float, sov: float, exhaustion: float) -> str:
    cands = {"scar": scar, "strain": strain, "low_sovereignty": 1.0 - sov,
             "exhaustion": exhaustion}
    return max(cands, key=lambda k: cands[k])


class OutreachCapability:
    """主动触达压力：仅空闲轮产 reach 意图，交 IgnitionArbiter 仲裁。无独占态。

    g_reach = reply_overdue（节律超期，主项）+ hold_free_energy×0.5（憋话）
              + max(0, approach_initiate)×0.3（躯体余力加成）；
    余力为负（耗竭/低主权）时整体打折——累瘫了就懒得找人，这是偏置不是闸。
    """

    name = "outreach"
    phases = (Phase.DELIBERATE,)

    def __init__(self, *, priority: float = 0.5) -> None:
        self._priority = priority

    def deliberate(self, ctx: BeatContext) -> Intent | None:
        if not _is_idle(ctx):
            return None
        now = float(ctx.scratch.get("now", 0.0) or 0.0)
        overdue = 0.0
        um = ctx.domain("usermodel")
        if um is not None and hasattr(um, "reply_overdue"):
            try:
                overdue = float(um.reply_overdue(ctx.body, now))
            except Exception:
                overdue = 0.0
        hold_fe = 0.0
        emo = ctx.domain("emotion")
        if emo is not None and hasattr(emo, "hold_free_energy"):
            try:
                hold_fe = float(emo.hold_free_energy(ctx.body))
            except Exception:
                hold_fe = 0.0
        bias = ctx.scratch.get("somatic_bias")
        initiate = float(getattr(bias, "approach_initiate", 0.0) or 0.0)

        g_reach = overdue + 0.5 * hold_fe + 0.3 * max(0.0, initiate)
        if initiate < 0.0:
            g_reach *= max(0.2, 1.0 + initiate)   # 退缩打折（连续偏置，非二元门）
        if g_reach <= 0.0:
            return None
        return Intent(
            source=self.name,
            payload={"want": "reach_out", "g_reach": g_reach,
                     "overdue": overdue, "hold_fe": hold_fe},
            priority=min(1.0, self._priority + g_reach * 0.1),
        )


def _is_idle(ctx: BeatContext) -> bool:
    """只认显式空闲标记（scratch["idle"]/["proactive"] 或 event.proactive）。
    正常对话轮文本提取失败绝不能被误判成空闲。"""
    if ctx.scratch.get("idle") or ctx.scratch.get("proactive"):
        return True
    ev = getattr(ctx, "event", None)
    if ev is not None and getattr(ev, "proactive", False):
        return True
    return False


__all__ = ["SomaticBias", "guard_soften_from_body",
           "SomaticMarkerCapability", "OutreachCapability"]
