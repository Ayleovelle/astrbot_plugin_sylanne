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

import datetime
import re

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



# ===========================================================================
# T2-01①：g_hold 的语境食粮（红队 kill fix：hold 此前只能吃 emo.hold_free_energy，
# 而它只在 SILENT 之后才积累——沉默从未发生过就永远没食粮，死循环）。
#
# 这里给 g_hold 加一路【与未表达积分正交】的语境代价：本轮消息本身有多"不值得
# 认真开口"（低信息量/连发轰炸/边界压力/深夜）。量级刻意压得很小（见各常量），
# 只让 hold 在多个信号叠加、且人格+当下表达驱力恰好把 g_speak 压低时才真的够得着
# ——"可能"而非"常见"，仅本模块 deliberate() 消费，不进 emotion 领域的真值。
#
# 门控：只有 T2-01 总开关（integration 经 ctx.scratch["deliberate_silence_enabled"]
# 注入）打开时才计算，config 默认关时这条食粮恒 0（零行为变化，不改变默认沉默频率）。
# ===========================================================================

_CONTEXT_HOLD_ENABLED_KEY = "deliberate_silence_enabled"

_LOW_INFO_ACKS = frozenset({
    "哦", "嗯", "嗯嗯", "哦哦", "额", "呵呵", "草", "6", "666",
    "ok", "OK", "Ok", "好", "好的", "是", "是的", "嗯呢", "？", "?", "。", "...", "……",
})
_LOW_INFO_MAXLEN = 2      # 短应答字数上限（超过此长度不再按"低信息量"计）
_LOW_INFO_HOLD = 0.12     # 低信息量消息（表情/短应答/复读）贡献
_BURST_WINDOW_S = 8.0     # 视作"连发"的绝对间隔窗（秒），冷启动无节律 EMA 也能识别
_BURST_HOLD = 0.10        # 连发轰炸贡献（越贴近 0 秒越接近满额）
_BOUNDARY_HOLD = 0.10     # 边界压力贡献（吃醋/被顶——不想好声好气接话）
_NIGHT_HOLD = 0.08        # 深夜（23:00–06:00，中国时区）贡献
_HAS_WORD_RE = re.compile(r"[\w一-鿿]")
_CHINA_TZ = datetime.timezone(datetime.timedelta(hours=8))


def _ramp01(x: float, lo: float, hi: float) -> float:
    """线性斜坡 [0,1]：x≤lo→0，x≥hi→1。hi≤lo 退 0（防除零，与 behavior.py 同款独立实现）。"""
    if hi <= lo:
        return 0.0
    return max(0.0, min(1.0, (x - lo) / (hi - lo)))


def _is_low_info_text(text: str, last_text: str) -> bool:
    """本轮文本是否"不值得认真开口"：短应答词表 / 纯表情符号(无字母数字汉字) / 逐字复读上一条。

    空文本不算（那是空闲轮，走别的分支，不在此列）。
    """
    if not text:
        return False
    if text == last_text and last_text:
        return True
    if len(text) <= _LOW_INFO_MAXLEN and text in _LOW_INFO_ACKS:
        return True
    if not _HAS_WORD_RE.search(text):
        return True   # 纯符号/表情，没有一个字母数字汉字
    return False


def _is_deep_night(now: float) -> bool:
    """是否处于深夜（23:00–06:00，中国时区）。now<=0（测试/无时钟）→ False，不臆测。"""
    if now <= 0.0:
        return False
    try:
        hour = datetime.datetime.fromtimestamp(now, tz=_CHINA_TZ).hour
    except (OverflowError, OSError, ValueError):
        return False
    return hour >= 23 or hour < 6


def context_hold_food(ctx: BeatContext) -> float:
    """T2-01①：g_hold 的语境食粮，纯函数、只读、不封顶叠加但单项均已很小（铁律②）。

    ctx.scratch["deliberate_silence_enabled"] 非真值 → 恒 0（config 默认关＝零变化）。
    """
    if not ctx.scratch.get(_CONTEXT_HOLD_ENABLED_KEY):
        return 0.0
    food = 0.0
    text = (ctx.text or "").strip()
    um = ctx.domain("usermodel")
    last_text = ""
    if um is not None and hasattr(um, "last_user_text"):
        try:
            last_text = str(um.last_user_text() or "")
        except Exception:
            last_text = ""
    if _is_low_info_text(text, last_text):
        food += _LOW_INFO_HOLD

    now = float(ctx.scratch.get("now", 0.0) or 0.0)
    if text and um is not None and hasattr(um, "seconds_since_last_user"):
        try:
            gap = um.seconds_since_last_user(now)
        except Exception:
            gap = None
        if gap is not None and gap < _BURST_WINDOW_S:
            food += _BURST_HOLD * (1.0 - _ramp01(gap, 0.0, _BURST_WINDOW_S))

    food += _BOUNDARY_HOLD * _ramp01(float(ctx.body.boundary_pressure), 0.4, 0.85)

    if _is_deep_night(now):
        food += _NIGHT_HOLD

    return food


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

        # #29 进化偏置喂回 live 门控：把 reflex/反思 学到的 proactive.open_threshold 偏置
        # 叠加在人格鞍点 express_at 上（人格显函数仍是主项，学习只微调，带 ±0.15 二次钳位）。
        # express_at 同时管"说/不说"(g_speak=express_at-eff_drive) 与空闲"主动"(speak 折叠成
        # reach)。负偏置=降门槛=空闲更主动（约定见 ctx.evo_bias）。注意子分支非全同向（红队实测）：
        # addressed-hold 分支里 g_speak 随负偏置下降，会让"被直接说话时"更易成 hold（赌气）——即
        # "空闲更主动"与"被问更易赌气"经 g_speak 同一杠杆耦合，量级被 ±0.15 钳死、仅窄窗触发。
        # 不进 personality_saddle（保持其为纯人格函数、无运行时耦合），只在仲裁处叠加。
        express_at += ctx.evo_bias("proactive", "open_threshold")

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
        # T2-01①：语境食粮——与未表达积分正交的独立信号，破"hold 从未发生过就永远
        # 没食粮"的死循环（config 关时 context_hold_food 恒 0，见其函数文档）。
        g_hold += context_hold_food(ctx)
        # T2-03⑤：收尾窗口内的临时 hold 偏置——integration 只在仍处于 winddown 窗口时
        # 才写非零值（见 integration._start_winddown_window / apply_v2core_request），
        # 窗口外/功能关闭恒读到 0.0，与该功能不存在时零差异。
        g_hold += float(ctx.scratch.get("winddown_hold_bias", 0.0) or 0.0)
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


__all__ = ["personality_saddle", "context_hold_food", "IgnitionArbiter"]
