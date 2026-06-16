"""IgnitionArbiter + personality_saddle —— 说/不说/主动 的三选一仲裁（Fable 重做版）。

诚实定位（不穿自由能戏服）：这是一个确定性的启发式代价比较器。g_speak/g_hold/g_reach
是三个【经标定测试对齐过量纲】的标量代价，argmin 选行动。它解释得清、测得出、调得动
——不宣称等价于期望自由能最小化或鞍点分岔。

personality_saddle（A7：阈值是人格显函数）——本版只用 surface 【实测真实暴露】的
trait（probe 证实：curiosity/edge/intimacy_gravity/patience/sovereignty_guard/
warmth_bias；没有 extraversion / expression_drive_trait）：
- express_at  = 1.05 − 0.10·curiosity − 0.10·warmth_bias   （好奇+暖底 → 越早开口）
- hold_below  = 0.02 + 0.16·sovereignty_guard               （主权强 → "懒得说"区大）
- hold_floor  = 0.10 + 0.10·patience                        （耐性好 → 更能憋住赌气）
三式在 trait=0.5 中性点精确回到 SDK 旧常数语义（0.95 / 0.10 / 0.15）——锚定不变，
偏离才个性化。没有任何回落到"恒中性"的死轴：三个输入全部真实可变。

被问/未被问分治（保留——这是对的）：
- 被问（有用户文本）默认开口；只有真实积累的沉默代价压过表达鞍距且超过 hold_floor
  才赌气/退缩沉默——冷启动绝不装死（no-ghost）。
- 未被问（空闲轮）默认安静；积累把 argmin 推向 speak/reach。

铁律②：只比较、只选择；不 clamp 任何驱力、不设安全阀。
"""

from __future__ import annotations

from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Intent, Phase

# 中性锚点系数（trait=0.5 ⇒ express_at=0.95 / hold_below=0.10 / hold_floor=0.15）
_EXPRESS_BASE = 1.05
_EXPRESS_W_CURIOSITY = 0.10
_EXPRESS_W_WARMTH_BIAS = 0.10
_HOLD_BASE = 0.02
_HOLD_W_SOVEREIGNTY = 0.16
_FLOOR_BASE = 0.10
_FLOOR_W_PATIENCE = 0.10


def personality_saddle(body: BodySnapshot) -> tuple[float, float, float]:
    """返回 (express_at, hold_below, hold_floor)，全部是真实暴露 trait 的显函数（A7）。

    纯函数、不写回、不 clamp。express_at>1.0 合法（=该人格几乎不被强制开口）。
    """
    curiosity = body.trait("curiosity", 0.5)
    warmth_bias = body.trait("warmth_bias", 0.5)
    sov = body.trait("sovereignty_guard", 0.5)
    patience = body.trait("patience", 0.5)
    express_at = (_EXPRESS_BASE
                  - _EXPRESS_W_CURIOSITY * curiosity
                  - _EXPRESS_W_WARMTH_BIAS * warmth_bias)
    hold_below = _HOLD_BASE + _HOLD_W_SOVEREIGNTY * sov
    hold_floor = _FLOOR_BASE + _FLOOR_W_PATIENCE * patience
    return express_at, hold_below, hold_floor


class IgnitionArbiter:
    """DELIBERATE 末位：speak / hold / reach 三选一。

    驱力来源（显式契约，不靠 source 名猜）：带 flag="speak_drive" 的 Intent，
    贡献 = priority × (confidence or 1)。ExpressionCapability / Mentalize 失同步
    澄清意图带这个 flag。

    hold 胜 → 写 ctx.scratch["silent"]={reason,…}（Renderer 据此 SILENT，D8 必带
    reason 强制日志）。reach 胜（仅空闲轮）→ observability intent 的 action="reach"，
    消费者：integration.consult_idle_reach（自驱心跳）。
    """

    name = "ignition"
    phases = (Phase.DELIBERATE,)

    def deliberate(self, ctx: BeatContext) -> Intent | None:
        body = ctx.body
        express_at, hold_below, hold_floor = personality_saddle(body)

        # —— 有效表达驱力：SDK 表达驱力 + 显式 speak_drive 意图 ——
        eff_drive = float(body.expression_drive)
        for it in ctx.intents:
            if "speak_drive" in (it.flags or ()):
                eff_drive += it.priority * (1.0 if it.confidence is None else it.confidence)

        # —— 三个代价 ——
        g_hold = 0.0
        emo = ctx.domain("emotion")
        if emo is not None and hasattr(emo, "hold_free_energy"):
            try:
                g_hold = float(emo.hold_free_energy(body))
            except Exception:
                g_hold = 0.0
        g_speak = max(0.0, express_at - eff_drive)
        g_reach_raw = 0.0
        has_reach = False
        for it in ctx.intents:
            if it.source == "outreach":
                g_reach_raw = float(it.payload.get("g_reach", 0.0) or 0.0)
                has_reach = g_reach_raw > 0.0
                break
        g_reach = max(0.0, 1.0 - g_reach_raw) if has_reach else float("inf")

        addressed = bool((ctx.text or "").strip())

        if eff_drive >= express_at:
            action = "speak"            # 越过强制表达鞍点（人格显函数）
        elif addressed:
            # 被问默认开口；仅真实积累的沉默代价压过表达鞍距且超过人格化下限才装死
            action = ("hold" if (g_hold > g_speak and g_hold > hold_floor) else "speak")
        else:
            costs = {"hold": g_hold, "speak": g_speak}
            if has_reach:
                costs["reach"] = g_reach
            action = min(costs, key=lambda k: costs[k])

        # 空闲轮折叠：没人问时"开口"与"主动触达"是同一物理行为（发出一条主动消息）。
        # 只要本轮存在 reach 压力，空闲开口一律记 reach——下游（主动桥）只认 reach。
        if not addressed and has_reach and action == "speak":
            action = "reach"

        if action == "hold":
            ctx.scratch["silent"] = {
                "reason": "ignition_hold",
                "g_speak": round(g_speak, 4),
                "g_hold": round(g_hold, 4),
                "express_at": round(express_at, 4),
                "hold_floor": round(hold_floor, 4),
                "eff_drive": round(eff_drive, 4),
            }

        # observability（priority=0 不参与任何融合；reach 决策的唯一可读出口）
        return Intent(
            source=self.name,
            payload={"action": action, "g_speak": g_speak, "g_hold": g_hold,
                     "g_reach": (g_reach if g_reach != float("inf") else None),
                     "express_at": express_at, "hold_below": hold_below,
                     "hold_floor": hold_floor, "eff_drive": eff_drive},
            priority=0.0,
        )


__all__ = ["personality_saddle", "IgnitionArbiter"]
