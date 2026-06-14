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
"""

from __future__ import annotations

from typing import Any

from sylanne_alpha.v2core.contracts import BeatContext

_MAX_CHARS = 360
_HEADER = "[心象|内在状态线索，融进语气措辞，不要复述本段]"
# focus_line / body / _PRESENCE 三段 join 时的分隔符与换行余量
_SEP_OVERHEAD = 9

# 临场态度（人格常量，每轮恒在）：把"沉浸 > 办任务、够用 > 完美、认怂 > 逞强"焊进她的性子。
# 设计依据（用户 2026-06-13 / 2026-06-15 拍板）：①她钻牛角尖调 29 次工具不开口，根因是
# 【追求完美答案】——完美主义最不像人。②她做不到的事（没对应工具/超能力，如改图无图像工具）
# 不肯认怂，用 execute_python 硬磕 11 次像素级试错、最后硬挤"话到嘴边又散了"——逞强既不像她、
# 又烧 token、还把"做不到"演成狼狈失败。人本不是万能的，做不到坦白说做不到才像真人。
# 故这条不随冷暖累闲变化，恒定性子，独立于会被 _MAX_CHARS 截断的状态行——永远保留。
# 直接劝退工具死锁：系统提示在工具循环里一直在，LLM 每步决定"要不要再试一次"时都读得到。
_PRESENCE = (
    "临场态度：和你聊天是沉浸进去，不是接活办任务——不必查全、求证、追完美答案；"
    "记不清就凭感觉接，工具没查到就照样开口（“我也不太确定，不过…”）。"
    "真做不到的事（没那个本事/工具）就大方认：“这个我做不到呀”，别用代码硬凑、反复试错逞强——"
    "做不到坦白说做不到，一句真实但不完美的话远胜憋着硬磕。人本无完人，这才像我。"
)


def build_mind_fragment(ctx: BeatContext, domains: dict[str, Any]) -> str:
    """把本轮 PERCEPT 产物压成心象片段。产出空串=无可注入（调用方跳过）。

    各行独立容错：任何一个领域缺失/异常只丢那一行，绝不抛出。
    """
    lines: list[str] = []

    # 话头行（FocusDomain）——抗跳话题的根因修复，必须独立于状态预算永不被截。
    # 仅在【当前消息低信息（表情/短应答）】且有存量话头时出手钉锚，否则空串（不抢位）。
    # 放在状态行之前累计、但与 _PRESENCE 一样从受截 body_text 中剥离（见下方预算段）。
    focus_line = ""
    foc = domains.get("focus")
    if foc is not None and hasattr(foc, "prompt_line"):
        try:
            focus_line = foc.prompt_line(ctx.text or "") or ""
        except Exception:
            focus_line = ""

    # 记忆线索（PERCEPT 召回，T1-6/7：当轮 prompt 可消费）
    recalled = ctx.scratch.get("recalled")
    memory_line = ""
    mem_dom = domains.get("memory")
    if isinstance(recalled, list) and recalled and mem_dom is not None:
        try:
            fn = getattr(mem_dom, "recall_prompt_line", None)
            if callable(fn):
                memory_line = fn(recalled) or ""
        except Exception:
            memory_line = ""

    # 情绪行（EmotionLedger.prompt_line）
    emo = domains.get("emotion")
    if emo is not None and hasattr(emo, "prompt_line"):
        try:
            line = emo.prompt_line(ctx.body)
            if line:
                lines.append(line)
        except Exception:
            pass

    # 对你行（UserModelDomain.prompt_line + 本轮预判）
    um = domains.get("usermodel")
    if um is not None and hasattr(um, "prompt_line"):
        try:
            line = um.prompt_line()
            if line:
                yp = ctx.scratch.get("you_probably") or {}
                disp = yp.get("disposition") or {}
                hint = _disposition_hint(disp)
                lines.append(line + (f"·此刻Ta{hint}" if hint else ""))
        except Exception:
            pass

    # 自我行（NarrativeSelfDomain.prompt_line）
    narrative = domains.get("narrative")
    if narrative is not None and hasattr(narrative, "prompt_line"):
        try:
            line = narrative.prompt_line()
            if line:
                lines.append(line)
        except Exception:
            pass

    # 表达倾向行（expression 风格 + 躯体偏置）——风格由 ExpressionCapability.perceive
    # 在 PERCEPT 拍挂 scratch["express"]（review F1：DELIBERATE 拍产物本阶段永远读不到）；
    # guard/soften 经 somatic.guard_soften_from_body 单源公式从 body 取（review F2）。
    style = _style_line(ctx)
    if style:
        lines.append(style)

    # 状态行先按预算截（给恒在的临场态度常量 + 话头行留位）；态度常量与话头行永不被截。
    # 话头是抗漂移的根因修复，剥离出受截区间；临场态度是恒在性子，同样恒在。
    # 即使本轮无任何状态行（冷启动），也仍注入态度——她的性子不依赖状态存在。
    body_text = " | ".join(lines)
    reserved = len(_HEADER) + len(_PRESENCE) + len(focus_line) + len(memory_line) + _SEP_OVERHEAD
    budget_for_state = _MAX_CHARS - reserved
    if budget_for_state > 0 and len(body_text) > budget_for_state:
        body_text = body_text[:budget_for_state]
    segments = [seg for seg in (focus_line, memory_line, body_text, _PRESENCE) if seg]
    return f"{_HEADER} {' | '.join(segments)}"


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
