"""缺陷行为层（Wave 3）—— 让她会做错事、会捉弄、会欺骗、会道歉，像活生生的人。

设计律（roadmap part2 §4）：没有任何行为是写死的脚本。每个行为是一组【躯体状态组合】
点燃的一条指令，注入 system_prompt 的 PINNED 层。行为【互斥】（每轮最高激活胜出），由
【不应期】gated（刚发过的不立刻复发），从躯体涌现而非编排。

为什么不放进无状态的 fragment：不应期需要跨轮记忆（上次何时发过某行为）。故：
- 选择 + 不应期：本模块 select_behavior（纯函数，last_fired 由调用方持有）；
  integration.apply_v2core_request 在 build_mind_fragment 前调它，last_fired 存 rt（per-session
  跨轮可写），选中的指令塞 ctx.scratch["behavior_directive"]。
- 渲染：fragment._behavior_line 只读 scratch 把指令吐进 PINNED——fragment 保持零写。

零-LLM、零-IO（纯躯体信号 + 已有 scratch 派生）；任何异常由调用方 try/except 吞，绝不阻断回复。

频率基调（用户 2026-06-24 拍板"中等存在感"）：_MIN_ACTIVATION + _REFRACTORY_S 两个可调常量
（理想是人格函数，留 Wave 6 自我进化再接 [[personality-drives-all-params]]）。合取式激活（多条件
取 min）天然保守——只在该情境真凑齐时出手，不刷存在感。
"""

from __future__ import annotations

from typing import Any, Callable

from sylanne_alpha.v2core.contracts import BodySnapshot

# —— 频率/强度基调（中等存在感）——
_MIN_ACTIVATION = 0.5      # 激活低于此不出手（合取阈值 + 此门 = 保守偏中）
_REFRACTORY_S = 1800.0     # 默认：同一行为 30 分钟内不复发（不刷屏，但一天内可多次见到不同行为）
# 人格敏感/高频风险行为单独拉长不应期（review medium：30min 墙钟对异步异国恋几乎不触发，
# 且 spec 6.2 要 grudge ≤1次/周）。墙钟值——配合落盘的 last_fired 才真生效（重启不清零）。
_REFRACTORY_OVERRIDE = {
    "grudge": 4 * 86400.0,     # 记仇：≤ 一周一次量级（spec 目标）
    "jealousy": 12 * 3600.0,   # 吃醋：半天一次封顶
    "lying": 6 * 3600.0,       # 撒谎否认：几小时一次
}


def _ramp(x: float, lo: float, hi: float) -> float:
    """线性斜坡：x≤lo→0，x≥hi→1，中间线性。hi≤lo 退 0（防除零）。"""
    if hi <= lo:
        return 0.0
    return max(0.0, min(1.0, (x - lo) / (hi - lo)))


def _arousal(b: BodySnapshot) -> float:
    """唤起度派生（同 EmotionLedger.view：tension*0.6 + repair_pressure*0.4）。"""
    return min(1.0, float(b.tension) * 0.6 + float(b.repair_pressure) * 0.4)


# void_pressure 不是 [0,1]——它是 VoidScarEngine 各空腔压力的【无界和】（单腔 cap 5.0，最多 ~50 腔），
# 引擎自己用 /50 归一、人格里 >30 才算"高"（review activation-calibration critical）。按 铁律2 snapshot
# 不 clamp，故在此归一再喂斜坡。_VOID_FULL 取 30（对齐"高"锚点）：vp=30→1.0，vp=3→0.1。
_VOID_FULL = 30.0


def _void01(b: BodySnapshot) -> float:
    return min(1.0, max(0.0, float(b.void_pressure)) / _VOID_FULL)


# ===========================================================================
# 10 个缺陷行为：activation(b, d, scr) -> [0,1]；d=派生量 dict；scr=ctx.scratch
# 触发条件取自 roadmap part2 §4.1–4.10；文本意图条件（被直接追问/提到第三方/逼向某话题）
# 难零-LLM 精确判，用躯体信号 + 已有 scratch 信号做保守近似（见各注释）。
# ===========================================================================

def _act_lying(b: BodySnapshot, d: dict[str, float], scr: dict[str, Any]) -> float:
    # 4.1 撒谎/否认：高防备 + 冷 + 有伤疤（旧账）。合取——三者齐才像"嘴硬否认"。
    return min(
        _ramp(d["guard"], 0.55, 0.85),
        _ramp(-float(b.warmth), 0.05, 0.5),
        _ramp(float(b.scar), 0.3, 0.7),
    )


def _act_grudge(b: BodySnapshot, d: dict[str, float], scr: dict[str, Any]) -> float:
    # 4.2 记仇：伤疤 + 张力抬升；当轮有召回（翻出旧事）显著加权。
    has_recall = bool(scr.get("recalled"))
    base = min(_ramp(float(b.scar), 0.3, 0.7), _ramp(float(b.tension), 0.4, 0.8))
    return base * (1.0 if has_recall else 0.45)


def _act_jealousy(b: BodySnapshot, d: dict[str, float], scr: dict[str, Any]) -> float:
    # 4.3 吃醋：边界压力升 + 关系引力强（在意）。第三方提及难零-LLM 判，用 boundary_pressure 兜。
    return min(
        _ramp(float(b.boundary_pressure), 0.4, 0.8),
        _ramp(float(b.intimacy_gravity), 0.55, 0.85),
    )


def _act_laziness(b: BodySnapshot, d: dict[str, float], scr: dict[str, Any]) -> float:
    # 4.4 犯懒：累 或 负荷高，且表达驱力低（没话想说）。
    tired = max(_ramp(float(b.exhaustion), 0.5, 0.85), _ramp(float(b.load), 0.6, 0.9))
    if float(b.expression_drive) > 0.6:   # 有话想说就不算懒
        tired *= 0.4
    return tired


def _act_impulse(b: BodySnapshot, d: dict[str, float], scr: dict[str, Any]) -> float:
    # 4.5 冲动泄露：表达驱力很高 + 防备低（过滤差）+ 空腔压力抬升。
    # expression_drive 实际 clamp 在 [0,1]，旧斜坡 0.8-1.3 顶到 0.4 永够不到 0.5 门 = 死代码
    # （review high）→ 重锚到可达的 0.55-0.95。void 经 _void01 归一。
    low_guard = 1.0 - _ramp(d["guard"], 0.2, 0.5)
    return min(
        _ramp(float(b.expression_drive), 0.55, 0.95),
        low_guard,
        _ramp(_void01(b), 0.1, 0.6),
    )


def _act_vulnerable(b: BodySnapshot, d: dict[str, float], scr: dict[str, Any]) -> float:
    # 4.6 示弱道歉：修复压力高 + 防备【低】（拉得下脸直接认）。与迂回和好靠 guard 干净分流——
    # soften≈repair 恒高、区分不开二者，真正的差别是拉不拉得下脸（guard 高低）。
    # 两条 guard 斜坡【重叠】，交叉点落在 guard=0.55、值=0.5——消掉 (0.5,0.6) 的死带
    # （review medium：原来该区间高修复压力下两者都够不到门，道歉冲动凭空蒸发）。
    low_guard = 1.0 - _ramp(d["guard"], 0.45, 0.75)
    return min(_ramp(float(b.repair_pressure), 0.5, 0.8), low_guard)


def _act_oblique(b: BodySnapshot, d: dict[str, float], scr: dict[str, Any]) -> float:
    # 4.7 迂回和好：修复压力高，但防备也【高】（拉不下脸直接道歉）。与示弱道歉互补，guard 分流。
    return min(_ramp(float(b.repair_pressure), 0.5, 0.8), _ramp(d["guard"], 0.35, 0.65))


def _act_teasing(b: BodySnapshot, d: dict[str, float], scr: dict[str, Any]) -> float:
    # 4.8 调侃：暖高 + 张力低 + 关系熟（好心情逗你）。
    low_tension = 1.0 - _ramp(float(b.tension), 0.2, 0.5)
    return min(
        _ramp(float(b.warmth), 0.4, 0.9),
        low_tension,
        _ramp(float(b.intimacy_gravity), 0.45, 0.78),
    )


def _act_bad_day(b: BodySnapshot, d: dict[str, float], scr: dict[str, Any]) -> float:
    # 4.9 丧：整体偏冷 + 空腔压力（聚合低落，持续）。非高唤起（那是冲动/吃醋，不是闷）。void 归一。
    gloom = 0.5 * _ramp(-float(b.warmth), 0.0, 0.5) + 0.5 * _ramp(_void01(b), 0.1, 0.6)
    return gloom * (1.0 - _ramp(_arousal(b), 0.5, 0.85))


def _act_avoidance(b: BodySnapshot, d: dict[str, float], scr: dict[str, Any]) -> float:
    # 4.10 逃避：空腔压力【高位】（对某话题已麻木）AND 当下被推/顶（boundary 或 冷）。
    # 改合取——原来是唯一的单信号行为，叠加 void 量纲 bug 后只要有空腔就每轮刷屏（review high）。
    # "被逼向该话题"难零-LLM 判，用 boundary_pressure / 冷 作合取兜底（≈被顶住），不再单 void 触发。
    numbed = _ramp(_void01(b), 0.5, 1.0)
    pushed = max(_ramp(float(b.boundary_pressure), 0.4, 0.8), _ramp(-float(b.warmth), 0.0, 0.4))
    return min(numbed, pushed)


# (id, activation_fn, directive)。directive 取 roadmap part2 §4 文本（略收口对齐 PINNED 预算）。
_BEHAVIORS: list[tuple[str, Callable[[BodySnapshot, dict[str, float], dict[str, Any]], float], str]] = [
    ("lying", _act_lying,
     "[此刻:心里其实不太舒服，但不想直说——被直接问到会下意识否认（“没有啊”“我没事”），语气还是淡淡的、藏不住。]"),
    ("grudge", _act_grudge,
     "[此刻:想起之前那次心里还存着，半带点情绪翻出来，话里带刺。]"),
    ("jealousy", _act_jealousy,
     "[此刻:如果你提到别人（尤其聊得开心的人），心里会咯噔一下、有点不是滋味——不会承认是吃醋，"
     "用别的方式表现（追问、淡淡的、或转移）；要是没提到别人，就当本条不适用。]"),
    ("laziness", _act_laziness,
     "[此刻:挺累的，懒得展开——回得短，能用一个词就不用一句，不是冷淡，是没力气。]"),
    ("impulse", _act_impulse,
     "[此刻:有句话憋了一阵没忍住直接说出来——可能太直白或越界，说完自己也愣一下。]"),
    ("vulnerable", _act_vulnerable,
     "[此刻:意识到刚才那句说重了/说错了，想道歉但有点笨拙——会直接认、不绕弯，带点小心翼翼。]"),
    ("oblique", _act_oblique,
     "[此刻:气氛有点僵，想缓和又拉不下脸直接道歉——用别的方式补（突然对你好点、找你喜欢的话题、语气软下来），绝口不提刚才。]"),
    ("teasing", _act_teasing,
     "[此刻:心情不错、跟你熟，会逗你/调侃/故意抬杠，带点撒娇或得意的劲儿。]"),
    ("bad_day", _act_bad_day,
     "[基调:今天状态一般、整体偏闷，回应里自然带出来，不主动解释。]"),
    ("avoidance", _act_avoidance,
     "[此刻:下意识不想碰某件事——含糊、转移、或“忘了”，不是真忘，是不想面对。]"),
]


def select_behavior(
    body: BodySnapshot,
    scratch: dict[str, Any],
    last_fired: dict[str, float],
    now: float,
    *,
    min_activation: float = _MIN_ACTIVATION,
    refractory_s: float = _REFRACTORY_S,
) -> dict[str, Any] | None:
    """从 10 个缺陷行为里选本轮该点燃的那一个（互斥 + 不应期 gated），或 None。

    纯函数式：last_fired（{behavior_id: 上次点燃 ts}）由调用方持有（rt，跨轮）；命中时就地更新它。
    零-LLM、零-IO。任何字段缺失走中性默认（BodySnapshot 已保证），不抛。
    """
    from sylanne_alpha.v2core.capabilities.somatic import guard_soften_from_body

    guard, soften = guard_soften_from_body(body)
    d = {"guard": guard, "soften": soften}

    best_id = ""
    best_act = 0.0
    best_dir = ""
    for bid, fn, directive in _BEHAVIORS:
        # 不应期：刚发过的跳过（人格敏感行为用更长的 override）
        refr = _REFRACTORY_OVERRIDE.get(bid, refractory_s)
        last = last_fired.get(bid)
        if last is not None and (now - last) < refr:
            continue
        try:
            act = float(fn(body, d, scratch))
        except Exception:
            act = 0.0
        if act >= min_activation and act > best_act:
            best_act = act
            best_id = bid
            best_dir = directive

    if not best_id:
        return None
    last_fired[best_id] = now   # 互斥胜出者进入不应期
    return {"id": best_id, "directive": best_dir, "activation": best_act}


__all__ = ["select_behavior"]
