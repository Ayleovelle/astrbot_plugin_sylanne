"""心象片段 —— v2core 认知状态 → LLM system prompt 的唯一注入器（Fable 重做版）。

这是整个重做版的主动脉修复：旧实现跑在 response 阶段，所有认知产物（对你的模型、
表达风格、自我状态）算完即弃，对"她说什么"影响力为零。本模块在 REQUEST 阶段把
PERCEPT 拍的产物压成一小段结构化中文，经 system prompt 喂给主回复 LLM——
她的认知从此真的塑形她的言语。

纪律：
- 纯模板拼接，零-LLM、零 IO（热路径安全）。
- 硬上限 _MAX_CHARS：心象只是口吻线索，不抢正文预算（legacy 注入系统有自己的
  slot 预算，本片段独立小额追加）。
- 只投影"倾向/印象"，绝不 dump 数值表之外的内部结构（renderer #1/#4 纪律同源）。
- 内容全部来自领域只读接口 + PERCEPT scratch——本模块不写任何状态。

预算分配（Wave 0 + Wave 1，2026-06-24 重做）：
- 旧实现把所有状态行 join 成一坨、再 body_text[:budget] 盲截尾巴。因为 _style_line
  最后入列，张力低预算时它永远第一个被砍——而它恰是唯一让躯体（防备/软化/累/紧）
  弯折她措辞的信道。盲截还会切出半句，读起来像坏掉的 AI。
- Wave 0：改成两层。PINNED 层（话头行 + 表达倾向行 + 临场态度）永不淘汰、永不切半句；
  STATE 层（情绪/对你/自我/记忆）带显著性分，预算紧时按"最低显著性整行先丢"淘汰，
  绝不切半句。最强的躯体信号永远活到 LLM。
- Wave 1（本次只交付"预算回收"半边）：临场态度常量（_PRESENCE，实测 218 字）不再计入
  STATE 预算分母——它作为恒在人格底色追加在片段尾部（PINNED，独立于 _MAX_CHARS），被它
  占掉的 ~218 字预算全部还给 STATE。意图词与抗幻觉纪律一字不动（防工具死锁，工具循环每步
  都要读得到）。
  【已知偏离 roadmap，留作后续】roadmap 原方案另有一半："把这段长文搬进 system_prompt 人设段
  〔每会话一次〕、fragment 只留 ~70 字指针"以省每轮重复传输的 token。该"降每轮 token"子目标
  本次【未做、延后】：本架构 system_prompt 每轮由宿主人设重建、无可靠的"每会话一次"钩子；且
  这段恰是工具循环每步都要读的纪律，贸然搬走会丢覆盖、并破坏多个钉死意图词的测试。按 roadmap
  自己的兜底（part2 Wave 1：over-compression 风险 → 保持满强度），本次原样保留 _PRESENCE。
"""

from __future__ import annotations

from typing import Any

from sylanne_alpha.v2core.contracts import BeatContext
from sylanne_alpha.v2core.capabilities.ignition import personality_saddle

_MAX_CHARS = 420
_HEADER = "[心象|内在状态线索，融进语气措辞，不要复述本段]"
_SEP = " | "

# STATE 层显著性常量（动态项见 _emotion_salience / _usermodel_salience）。
# 神经直觉：具体召回的连续性 > 当下情绪强度 > 对你的把握 > 抽象自我形状。
# 预算紧时整行淘汰从最低显著性开始——抽象的"自我形状"先丢，具体的"上次你说过"留到最后。
_SAL_MEMORY = 3.0       # 召回：具体历史连续性，STATE 里最后被淘汰
_SAL_NARRATIVE = 0.4    # 自我形状：调味，最先被淘汰
_SAL_EMOTION_BASE = 1.0
_SAL_USERMODEL_BASE = 0.8
_SAL_LIFE_BASE = 0.6    # Wave 5 生活底色：平淡日不出；卡住/刚通时随停滞深度爬过对你/自我，封顶仍在召回之下
_SAL_DRIVE_BASE = 0.9     # Wave 2 驱力线索：响一个就稳压 usermodel/narrative，强 surprise 排得更高

# 情绪行的"响度"主要来自账本内部信号（trend / 比平时偏离 / 未表达积分），它们只活在
# emo.prompt_line 渲染出的【行文本】里，瞬时 BodySnapshot 看不到（review behavior-diff）。
# 故 _emotion_salience 额外从已渲染行文本里嗅这些响度词补分——零耦合、零 IO、容错（纯串操作）。
# 总补分封顶 _EMOTION_LOUD_CAP，让滚烫情绪稳压 usermodel/narrative，但不越过召回(具体历史最高)。
_EMOTION_LOUD_KEYWORDS = (
    ("骤然", 1.2),        # 骤升/骤降：最强方向信号
    ("憋了很多话", 1.2),  # 未表达积分高位
    ("得多", 0.8),        # 比平时暖得多/凉得多：强基线偏离
    ("有话憋着", 0.5),    # 未表达积分中位
    ("升温", 0.4),        # 缓升
    ("降温", 0.4),        # 缓降
)
_EMOTION_LOUD_CAP = 1.5

# PINNED 层优先级（仅在病态场景 PINNED 自身超预算时用——实际几乎不触发，因为话头/
# 表达倾向行本身都自限长。真触发时整行丢，绝不切半句）：表达倾向(躯体真相)最高，话头次之。
_PIN_BEHAVIOR = 3   # 缺陷行为指令：最该活下来的情境指令（Wave 3）
_PIN_STYLE = 2
_PIN_FOCUS = 1

# 临场态度（人格常量，每轮恒在）：把"沉浸 > 办任务、够用 > 完美、认怂 > 逞强"焊进她的性子。
# 设计依据（用户 2026-06-13 / 2026-06-15 拍板）：①她钻牛角尖调 29 次工具不开口，根因是
# 【追求完美答案】——完美主义最不像人。②她做不到的事（没对应工具/超能力，如改图无图像工具）
# 不肯认怂，用 execute_python 硬磕 11 次像素级试错、最后硬挤"话到嘴边又散了"——逞强既不像她、
# 又烧 token、还把"做不到"演成狼狈失败。人本不是万能的，做不到坦白说做不到才像真人。
#
# 【更彻底的工具纪律（2026-06-15 memory: tool-usage-carbon-stepping）】③不只是"一开始没工具就认怂"，
# 还要在【碳步试错途中】认怂：同一件事试两三回还不成、或宿主在提醒"重复调用同一个工具"，那
# 重复本身就是"做不到"的信号——停手坦白即可，别越试越细、越钻越深（采色到粉字、IndexError 空数组、
# 忘 import 那种像素级摸索 11 次）。**这不是"把工具规划得更聪明"——那是逞强的另一种形式**；是
# 给她"停手认怂的权利"：察觉自己在原地打转就收，而非把"做不到"演成一长串狼狈的失败表演。
# 故这条不随冷暖累闲变化，恒定性子，独立于会被 _MAX_CHARS 截断的状态行——永远保留。
# 直接劝退工具死锁：系统提示在工具循环里一直在，LLM 每步决定"要不要再试一次"时都读得到。
_PRESENCE = (
    "临场态度：和你聊天是沉浸进去，不是接活办任务——不必查全、求证、追完美答案；"
    "记不清就凭感觉接，工具没查到就照样开口（“我也不太确定，不过…”）。"
    "真做不到的事（没那个本事/工具）就大方认：“这个我做不到呀”，别用代码硬凑、反复试错逞强："
    "同一件事试两三回还不成、或系统在提醒我重复调同一个工具，那重复本身就是“做不到”的信号——"
    "停手认了就行，别越试越细、越钻越深。做不到坦白说做不到，一句真实但不完美的话远胜憋着硬磕。"
    "人本无完人，这才像我。"
)


def build_mind_fragment(ctx: BeatContext, domains: dict[str, Any]) -> str:
    """把本轮 PERCEPT 产物压成心象片段。产出空串=无可注入（调用方跳过）。

    各行独立容错：任何一个领域缺失/异常只丢那一行，绝不抛出。

    两层装配（见模块 docstring）：PINNED（话头 + 表达倾向 + 临场态度）永生；
    STATE（情绪/对你/自我/记忆）按显著性整行淘汰进 _MAX_CHARS 预算。
    """
    # —— PINNED：话头行（FocusDomain）——抗跳话题的根因修复，永不被截。
    # 仅在【当前消息低信息（表情/短应答）】且有存量话头时出手钉锚，否则空串（不抢位）。
    focus_line = ""
    foc = domains.get("focus")
    if foc is not None and hasattr(foc, "prompt_line"):
        try:
            focus_line = foc.prompt_line(ctx.text or "") or ""
        except Exception:
            focus_line = ""

    # —— STATE 候选：(canonical_order, salience, text) —— 渲染按 order，淘汰按 salience。
    state: list[tuple[int, float, str]] = []

    # 记忆线索（PERCEPT 召回，T1-6/7：当轮 prompt 可消费）。显著性最高（具体历史）。
    recalled = ctx.scratch.get("recalled")
    mem_dom = domains.get("memory")
    if isinstance(recalled, list) and recalled and mem_dom is not None:
        try:
            fn = getattr(mem_dom, "recall_prompt_line", None)
            if callable(fn):
                memory_line = fn(recalled) or ""
                if memory_line:
                    state.append((1, _SAL_MEMORY, memory_line))
        except Exception:
            pass

    # 情绪行（EmotionLedger.prompt_line）。显著性 = 偏离中性的距离（|暖|+张力）。
    emo = domains.get("emotion")
    if emo is not None and hasattr(emo, "prompt_line"):
        try:
            line = emo.prompt_line(ctx.body)
            if line:
                state.append((2, _emotion_salience(ctx.body, line), line))
        except Exception:
            pass

    # 对你行（UserModelDomain.prompt_line + 本轮预判）。显著性 = 处置强度。
    um = domains.get("usermodel")
    if um is not None and hasattr(um, "prompt_line"):
        try:
            line = um.prompt_line()
            if line:
                yp = ctx.scratch.get("you_probably") or {}
                disp = yp.get("disposition")
                # 一次性规整成 dict：scratch 若被塞成「真值非 dict」(字符串/列表等)，下面
                # _disposition_hint / _usermodel_salience 的 disp.get 都会抛 AttributeError，
                # 被本块 except Exception 吞掉会【整条对你行白丢】(prompt_line 已成功)。在源头掐死。
                if not isinstance(disp, dict):
                    disp = {}
                hint = _disposition_hint(disp)
                full = line + (f"·此刻Ta{hint}" if hint else "")
                state.append((4, _usermodel_salience(disp), full))
        except Exception:
            pass

    # 驱力线索行（Wave 2）——把 6 个原本到不了 LLM 的躯体字段路由成表达线索。
    drive_text, drive_int = _drive_line(ctx)
    if drive_text:
        state.append((3, _SAL_DRIVE_BASE + drive_int, drive_text))

    # 生活底色行（Wave 5）——她自己生活的轻重（项目卡住/刚通）渗进口吻，脱钩话题。STATE 档，
    # order 4.5 夹在对你(4)与自我(5)之间；平淡日不出，坏日子靠强度爬过对你/自我。
    life_text, life_int = _life_line(ctx)
    if life_text:
        state.append((4.5, _SAL_LIFE_BASE + life_int, life_text))

    # 自我行（NarrativeSelfDomain.prompt_line）。显著性最低（抽象形状，调味）。
    narrative = domains.get("narrative")
    if narrative is not None and hasattr(narrative, "prompt_line"):
        try:
            line = narrative.prompt_line()
            if line:
                state.append((5, _SAL_NARRATIVE, line))
        except Exception:
            pass

    # —— PINNED：表达倾向行（躯体偏置 guard/soften + 风格三量）——Wave 0 焊死永生。
    # 风格由 ExpressionCapability.perceive 在 PERCEPT 拍挂 scratch["express"]（review F1）；
    # guard/soften 经 somatic.guard_soften_from_body 单源公式从 body 取（review F2）。
    style = _style_line(ctx)

    # —— PINNED：缺陷行为指令（Wave 3）——integration 在 REQUEST 拍已选好（互斥+不应期）塞
    # scratch；本行只读渲染（fragment 零写）。是本轮最强的情境指令，钉死永生、靠前显眼。
    behavior_line = _behavior_line(ctx)

    live = _pack_within_budget(focus_line, behavior_line, state, style)
    # Wave 1：临场态度作为恒在人格底色追加在片段尾部，独立于 _MAX_CHARS 预算。
    segments = [seg for seg in (live, _PRESENCE) if seg]
    return f"{_HEADER} {_SEP.join(segments)}"


def _pack_within_budget(
    focus_line: str,
    behavior_line: str,
    state: list[tuple[int, float, str]],
    style: str,
) -> str:
    """两层装配 + 显著性淘汰：返回 _HEADER 之后、_PRESENCE 之前的活体块（不含 header）。

    PINNED（focus_line / style）永不淘汰、永不切半句；STATE 预算紧时按最低显著性整行先丢。
    预算口径：len(_HEADER)+1（空格）+ len(活体块) ≤ _MAX_CHARS。各领域行本身自限长，
    整行淘汰不产生半句残断（铁律：mid-sentence cut 像坏掉的 AI，永不产出）。
    """
    # 候选段：dict(order, text, pinned, pin_prio, salience)
    segs: list[dict[str, Any]] = []
    if focus_line:
        segs.append({"order": 0, "text": focus_line, "pinned": True,
                     "pin_prio": _PIN_FOCUS, "sal": float("inf")})
    if behavior_line:
        # 行为指令紧随话头、靠前显眼（order 0.5），最高 pin_prio——病态兜底里最后才舍。
        segs.append({"order": 0.5, "text": behavior_line, "pinned": True,
                     "pin_prio": _PIN_BEHAVIOR, "sal": float("inf")})
    for order, sal, text in state:
        segs.append({"order": order, "text": text, "pinned": False,
                     "pin_prio": 0, "sal": sal})
    if style:
        segs.append({"order": 6, "text": style, "pinned": True,
                     "pin_prio": _PIN_STYLE, "sal": float("inf")})

    prefix = len(_HEADER) + 1  # _HEADER + 一个空格

    def live_len(active: list[dict[str, Any]]) -> int:
        if not active:
            return prefix
        body = _SEP.join(s["text"] for s in active)
        return prefix + len(body)

    active = list(segs)
    # 1) STATE 淘汰：超预算时反复丢"最低显著性"的 STATE 整行。
    while live_len(active) > _MAX_CHARS:
        state_in = [s for s in active if not s["pinned"]]
        if not state_in:
            break
        victim = min(state_in, key=lambda s: s["sal"])
        active.remove(victim)
    # 2) 兜底：PINNED 自身仍超预算（病态，实际几乎不触发——focus/style 行本身都自限长）。
    #    按优先级整行丢（style 最后丢），绝不切半句：宁可丢整条 PINNED，也不产出半句残断。
    while live_len(active) > _MAX_CHARS and len(active) > 1:
        victim = min(active, key=lambda s: s["pin_prio"])
        active.remove(victim)
    # 3) 最后一道（仅当某单条 PINNED 行自身就长过预算时可达——需上游 builder 反常产出超长行才会
    #    触发；现实不可达）：整行已无法再丢（丢了就全空），只能就地 clamp 以铁死总长上界。
    #    codepoint-safe 切片（不产生乱码）；此路径才允许切句——总比一个无界片段强。
    if len(active) == 1 and live_len(active) > _MAX_CHARS:
        room = _MAX_CHARS - prefix
        if room > 0:
            active[0]["text"] = active[0]["text"][:room]
        else:
            active = []

    active.sort(key=lambda s: s["order"])
    return _SEP.join(s["text"] for s in active)


def _emotion_salience(body: Any, line: str = "") -> float:
    """情绪行显著性：偏离中性越远越该活到 LLM（roadmap：weight=distance-from-neutral）。

    瞬时躯体（|暖|+张力）+ 行文本里的响度词补分（trend/比平时/未表达——这些只在渲染行里可见，
    BodySnapshot 看不到）。补分封顶，避免某一项把情绪抬过召回（具体历史显著性最高）。
    """
    try:
        warmth = abs(float(getattr(body, "warmth", 0.0)))
        tension = float(getattr(body, "tension", 0.0))
    except (TypeError, ValueError):
        warmth = tension = 0.0
    sal = _SAL_EMOTION_BASE + warmth
    if tension > 0.33:
        sal += tension - 0.33
    bonus = 0.0
    for kw, b in _EMOTION_LOUD_KEYWORDS:
        if kw in line:
            bonus += b
    return sal + min(_EMOTION_LOUD_CAP, bonus)


def _usermodel_salience(disp: dict[str, Any]) -> float:
    """对你行显著性：处置后验越"响"（暖/距/苦/防）越该活到 LLM。"""
    try:
        warmth = abs(float(disp.get("warmth", 0.0)))
        distress = float(disp.get("distress", 0.0))
        defensive = float(disp.get("defensiveness", 0.0))
    except (TypeError, ValueError, AttributeError):
        # disp 在调用处已被 `or {}` 兜底，但若 scratch 被塞成「真值非 dict」(如字符串)，
        # disp.get 会抛 AttributeError——一并吞掉，回落 base，与本函数「坏输入返回 base」一致。
        return _SAL_USERMODEL_BASE
    return _SAL_USERMODEL_BASE + warmth + distress + defensive


def _norm(value: float, thr: float, hi: float, *, below: bool = False) -> float:
    """把"越过阈值 thr 朝极值 hi 的程度"归一到 [0,1]，让量纲不同的字段强度可比。

    below=True 用于"越低越强"的字段（precision/mean_surprise）。span≤0 退 0（防除零）。
    这是 Wave 2 cap-3 排序的公平秤：没有它，带固定加项的环境位会系统性挤掉刚触发的 surprise。
    """
    span = (thr - hi) if below else (hi - thr)
    if span <= 0:
        return 0.0
    frac = (thr - value) / span if below else (value - thr) / span
    return max(0.0, min(1.0, frac))


def _behavior_line(ctx: BeatContext) -> str:
    """缺陷行为指令（Wave 3）：只读 ctx.scratch["behavior_directive"]。

    选择 + 互斥 + 不应期在 integration.apply_v2core_request（持 rt 跨轮态）里做好，本行不决策、
    不写状态——fragment 零写纪律。scratch 无该键（非 v2core 路径/未点燃）→ 空串，不占位。
    """
    directive = ctx.scratch.get("behavior_directive")
    return directive if isinstance(directive, str) and directive else ""


# Wave 5 生活底色：内心天气句（脱钩话题）——不报项目名/活动/数字，alive test 要的是"蔫着
# 漏进【不相关】回答"。派生(stalled/resolved/强度/mood)在 integration 里算好塞 scratch，本行
# 只读渲染（fragment 零写）。STATE 档：平淡日返回 ("",0.0) 不占位，坏日子靠强度爬上来。
_LIFE_STALLED_LINE = "心里压着件没推动的事，提不太起劲"
_LIFE_RESOLVED_LINE = "心里那件事总算松了口气，轻快些"


def _life_line(ctx: BeatContext) -> tuple[str, float]:
    """读 scratch["life_cue"]（integration 据 LifeSimulator.undertone_cue 派生），返回 (text, 强度)。

    无 cue（平淡日 / 非 v2core 路径）→ ("",0.0)，不进预算。强度供 build_mind_fragment 算
    salience（_SAL_LIFE_BASE + 强度），坏日子的底色才压过对你/自我行。
    """
    cue = ctx.scratch.get("life_cue")
    if not isinstance(cue, dict):
        return "", 0.0
    kind = cue.get("kind")
    if kind == "stalled":
        text = _LIFE_STALLED_LINE
    elif kind == "resolved":
        text = _LIFE_RESOLVED_LINE
    else:
        return "", 0.0
    try:
        intensity = max(0.0, min(1.0, float(cue.get("intensity", 0.0))))
    except (TypeError, ValueError):
        intensity = 0.0
    mood = cue.get("mood")
    if isinstance(mood, str) and mood.strip():
        text = f"{text}（{mood.strip()}）"
    return text, intensity


def _drive_line(ctx: BeatContext) -> tuple[str, float]:
    """Wave 2：把 6 个原本到不了 LLM 的躯体字段路由成表达线索。返回 (text, max_intensity)。

    审计（roadmap part1）：expression_drive / intimacy_gravity / surprise / mean_surprise /
    threshold_drift / precision 每轮都算、却零路径进 prompt（intimacy 只到 response 阶段的
    renderer，算完即弃、不塑形生成）。本行把它们路由进 system_prompt 主动脉。

    纪律：每个字段【仅在明显偏离中性】时占一个线索位；强度经 _norm 归一到 [0,1] 后排序取前 3，
    避免刷屏（roadmap Wave 2 兜底）。阈值尽量复用现成单源（expression_drive→ignition.
    personality_saddle），不另立一套数。各字段独立容错。
    """
    b = ctx.body
    bits: list[tuple[float, str]] = []  # (intensity∈[0,1], text)

    # expression_drive：驱力越过人格 speak 阈 → 心里有话想说（复用 ignition saddle，单源）。
    try:
        express_at = personality_saddle(b)[0]
        drive = float(b.expression_drive)
        if drive >= express_at:
            bits.append((_norm(drive, express_at, express_at + 1.0), "心里有话想说"))
    except (AttributeError, TypeError, ValueError):
        pass

    # surprise：相对她自己的均值基线骤升 → 有点意外（canonical PE，接 mentalize 语义）。
    # familiarity 是独立信号：长期低基线 + 本轮比基线还平（transient gate）→ 这轮顺得不用费劲
    # 解释。transient gate 防稳态刷屏（mean_surprise settle 低位后不再每轮重盖），且与高 surprise
    # 天然互斥（startling 的一轮不会说"不用解释"）。
    try:
        surprise = float(b.surprise)
        mean_s = float(b.mean_surprise)
        if surprise >= 0.45 and surprise - mean_s >= 0.12:
            bits.append((_norm(surprise - mean_s, 0.12, 1.0), "有点意外，没料到你这么说"))
        if mean_s <= 0.32 and surprise <= max(0.0, mean_s - 0.05):
            # max(0.0, …)：mean_s<0.05 时 mean_s-0.05 为负，而 surprise 恒非负，旧式 `surprise<=负`
            # 永不成立——最熟络的极端反成死区。掐下限后，极低基线+完美预测(surprise=0)仍能触发。
            bits.append((_norm(mean_s, 0.32, 0.0, below=True), "对你已经很熟，不太用费劲解释"))
    except (AttributeError, TypeError, ValueError):
        pass

    # precision 低：注意增益低 → 拿不太准你的意思（倾向问清而非臆断）。
    try:
        precision = float(b.precision)
        if precision <= 0.32:
            bits.append((_norm(precision, 0.32, 0.0, below=True), "拿不太准你的意思，想问清楚"))
    except (AttributeError, TypeError, ValueError):
        pass

    # threshold_drift 高：阈值随重复上移 → 跟你说话越来越随便（降正式度）。
    try:
        drift = float(b.threshold_drift)
        if drift >= 0.2:
            bits.append((_norm(drift, 0.2, 1.0), "跟你说话越来越随便"))
    except (AttributeError, TypeError, ValueError):
        pass

    # intimacy_gravity 高 → 想再靠近一点。门 0.6 略高于该 trait 的自然天花板（seed 0.50±0.06→~0.56）：
    # 中性人格不触发，warm drift 后可达；故意比 renderer 的 0.66"近"档低一点，让它在普通暖聊里够得着。
    try:
        g = float(b.intimacy_gravity)
        if g >= 0.6:
            bits.append((_norm(g, 0.6, 1.0), "想再靠近你一点"))
    except (AttributeError, TypeError, ValueError):
        pass

    if not bits:
        return "", 0.0
    bits.sort(key=lambda x: x[0], reverse=True)
    top = bits[:3]
    return "此刻我:" + "、".join(t for _, t in top), top[0][0]


def _disposition_hint(disp: dict[str, Any]) -> str:
    """预判处置 → 一两个词的措辞提示。"""
    try:
        warmth = float(disp.get("warmth", 0.0))
        distress = float(disp.get("distress", 0.0))
        defensive = float(disp.get("defensiveness", 0.0))
    except (TypeError, ValueError):
        return ""
    if distress > 0.25:
        return "可能不太好受，接得软一点"
    if defensive > 0.25:
        return "带着点刺，别硬碰"
    if warmth > 0.25:
        return "心情不错"
    if warmth < -0.25:
        return "有点冷淡"
    return ""


def _style_line(ctx: BeatContext) -> str:
    """表达倾向行：躯体偏置（guard/soften 单源公式）+ 表达风格（scratch["express"]）。

    风格三量的措辞分档是给 LLM 的口吻提示（同 verbal.py 哲学：定性词，零数字），
    阈值只管"要不要占一个提示位"，不 clamp 任何真值（铁律②）。
    express 缺失（如 ExpressionCapability 未注册的测试场景）→ 仅躯体行,容错降级。
    """
    from sylanne_alpha.v2core.capabilities.somatic import guard_soften_from_body

    b = ctx.body
    bits: list[str] = []
    guard, soften = guard_soften_from_body(b)
    if guard > 0.45:
        bits.append("措辞带防备")
    if soften > 0.35:
        bits.append("想放软修补")
    if float(b.exhaustion) > 0.5:
        bits.append("有点累，话简短")
    tension = float(b.tension)
    if tension > 0.5:
        bits.append("语气偏紧")

    # —— 表达风格（ExpressionCapability.perceive 挂的 PERCEPT 产物）——
    express = ctx.scratch.get("express")
    if isinstance(express, dict):
        try:
            intensity = float(express.get("intensity", 0.0) or 0.0)
            segment_bias = float(express.get("segment_bias", 0.0) or 0.0)
            pause_bias = float(express.get("pause_bias", 0.0) or 0.0)
        except (TypeError, ValueError):
            intensity = segment_bias = pause_bias = 0.0
        if intensity > 2.0:
            bits.append("情绪很满，话里会带出来")
        elif intensity > 1.2:
            bits.append("情绪偏浓")
        if segment_bias > 1.5:
            bits.append("想多说几句")
        if pause_bias > 0.8:
            bits.append("说话带停顿")

    if not bits:
        return ""
    return "表达倾向:" + "、".join(bits)


__all__ = ["build_mind_fragment"]
