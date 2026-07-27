from __future__ import annotations

import ast
import logging
import random
import re
from typing import Any

REALTIME_PLAN_SCHEMA_VERSION = "sylanne.alpha.realtime_plan.v1"


def realtime_flags(cfg: dict[str, Any] | None) -> tuple[bool, bool]:
    """即时聊天两开关的单一读取入口：(realtime_enabled, intercept)。

    次要修复②（realtime 完整重做设计）：此前请求侧（llm_request_pipeline）只认
    正规键 sylanne_alpha_realtime_chat_enabled / sylanne_alpha_realtime_intercept_
    llm_response，响应侧（llm_response_pipeline）额外兼容旧别名
    enable_realtime_chat / realtime_chat_intercept_llm_response——两侧口径不一致，
    若只设别名键，请求侧会误判两开关都关（M4a 请求侧强制关流因此漏触发）。
    现在两侧统一走这一个函数，别名与正规键任一为真即算开启。
    """
    _cfg = cfg or {}
    enabled = bool(
        _cfg.get("sylanne_alpha_realtime_chat_enabled") or _cfg.get("enable_realtime_chat")
    )
    intercept = bool(
        _cfg.get("sylanne_alpha_realtime_intercept_llm_response")
        or _cfg.get("realtime_chat_intercept_llm_response")
    )
    return enabled, intercept


def strip_draft_blocks(text: str) -> str:
    cleaned = str(text or "")
    for tag in ("draft_notes", "thinking", "think"):
        cleaned = re.sub(rf"(?is)<{tag}[^>]*>.*?</{tag}>", "", cleaned)
    lines = cleaned.replace("\r\n", "\n").split("\n")
    visible: list[str] = []
    hidden_tag: str | None = None
    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()
        opening = re.fullmatch(r"<([a-z_]+)[^>]*>", lower)
        closing = re.fullmatch(r"</([a-z_]+)>", lower)
        if opening and opening.group(1) in {"draft_notes", "thinking", "think"}:
            hidden_tag = opening.group(1)
            continue
        if closing and closing.group(1) == hidden_tag:
            hidden_tag = None
            continue
        if hidden_tag is None:
            visible.append(line)
    return "\n".join(visible).strip()


# 整段长度硬截断（不同于 _cap_parts 的"限段数"）。当前唯一调用方：path3 TTS——
# text 整段进语音合成，段数无意义、只长度有害（数分钟音频）。按字符数在句末标点回退
# 截断；找不到句末标点时退而求安全 ASCII 边界（不切坏代码/URL token，M2 审查），
# 再不行才硬切。阈值放宽，只兜异常长。
def truncate_at_sentence(text: str, max_chars: int) -> str:
    """超过 max_chars 时在 <=max_chars 内截断：优先句末标点 → 安全 ASCII 边界 → 硬切。"""
    if max_chars <= 0:
        return ""
    s = str(text or "")
    if len(s) <= max_chars:
        return s
    cut = s[:max_chars]
    lo = max_chars // 2
    # ① 句末标点
    for j in range(len(cut) - 1, lo - 1, -1):
        if cut[j] in "。！？!?；;\n":
            return cut[: j + 1]
    # ② 安全边界：切点不能落在一个 ASCII token（标识符/URL）中间（复用既有判定）
    for j in range(len(cut) - 1, lo - 1, -1):
        if _safe_ascii_boundary(s, j):
            return cut[:j].rstrip() or cut[:j]
    # ③ 实在没有 → 硬切
    return cut


# 出站分段硬上限：单条回复最多发这么多段 IM。防 thinking 泄露/超长回复被
# _split_text 按行碎成几十上百段连发轰炸用户（2026-06-15 事故 Turn8：86 段）。
# 超限时【合并尾部】成一段（不丢内容，只少发几条），而非丢弃——交付型成品常落在
# 末尾，丢尾会把真正的答案删掉。这是兜底闸：正常人格回复远到不了 12 段。
_DEFAULT_MAX_PARTS = 12

# T1-02 打碎节拍器：分段延迟不再是纯确定性公式（人类打字节奏本身有抖动，恒定节拍才是
# "机器味"信号）。两个独立效应，都在【预算 scale 之后】叠加，不改变原有 scale 语义：
#   ① 逐段抖动：每段延迟乘 uniform(0.6,1.4)（±40%），乘完仍走既有 min(4.2,...) 硬顶——
#      因此单段绝不超过原上限，总预算不会被抖动系统性推高（cap 会把超冲部分削回去，
#      期望值仍贴近预算，只加方差不加偏置）。
#   ② 走神停顿：整条回复 5% 概率选一个非首段，让它的延迟越过 4.2s 硬顶冲到 5~9s——
#      模拟"打字打到一半愣了一下"，故意不受 cap 约束（这就是"走神"的点）。
# 两者都吃 rng 参数（对齐 variant_pool.choose 的既有约定：默认走全局 random 模块，
# 测试传 random.Random(seed) 进来即可复现）。
_JITTER_MIN = 0.6
_JITTER_MAX = 1.4
_DISTRACTED_PAUSE_PROBABILITY = 0.05
_DISTRACTED_PAUSE_MIN = 5.0
_DISTRACTED_PAUSE_MAX = 9.0

# Model-authored pause classes describe intent only; local code merely maps that
# intent to a bounded delivery delay.  It never decides where a semantic break is.
_SEMANTIC_PAUSE_RANGES: dict[str, tuple[float, float]] = {
    "soft": (0.45, 1.25),
    "normal": (1.25, 2.75),
    "deep": (2.75, 4.8),
}


def _cap_parts(parts: list[str], *, max_parts: int) -> list[str]:
    """把分段数压到 max_parts 以内：保留前 max_parts-1 段，其余合并成最后一段。"""
    if max_parts <= 0 or len(parts) <= max_parts:
        return parts
    head = parts[: max_parts - 1]
    tail = [p for p in parts[max_parts - 1 :] if p]
    # Parts are exact slices of the clean completion.  Adding a newline here
    # would mutate both visible output and persisted history.
    merged_tail = "".join(tail)
    if merged_tail:
        head.append(merged_tail)
    return head


def _trim_semantic_delivery_boundaries(parts: list[str]) -> list[str]:
    """Remove transport-only whitespace around separately sent semantic beats.

    The parser keeps every authored character so persisted history remains
    lossless.  Once those slices become separate IM messages, however, leading
    or trailing line breaks render as empty rows inside a bubble.  Trim only
    multi-part semantic delivery; ordinary and oversized single-message text
    keeps its exact bytes.
    """

    if len(parts) <= 1:
        return parts
    return [part.strip() for part in parts]


def realtime_plan(
    session_key: str,
    text: str,
    *,
    max_part_chars: int = 48,
    chars_per_second: float = 7.5,
    max_parts: int = _DEFAULT_MAX_PARTS,
    rng: random.Random | None = None,
    first_delay: float = 0.0,
    semantic_parts: Any | None = None,
    oversize_safety_chars: int = 1200,
) -> dict[str, Any]:
    raw = str(text or "")
    visible = (
        strip_draft_blocks(raw)
        if re.search(r"(?is)</?(?:draft_notes|thinking|think)\b", raw)
        else raw
    )
    semantic = _coerce_semantic_parts(semantic_parts, expected_text=visible)
    if semantic is not None:
        parts, pause_classes = semantic
        segmentation_source = "model_semantic_beats"
    elif visible and len(visible) > max(0, int(oversize_safety_chars)):
        parts = _split_text_preserving(visible, max_part_chars=max_part_chars)
        pause_classes = None
        segmentation_source = "oversize_safety"
    else:
        parts = [visible] if visible else []
        pause_classes = None
        segmentation_source = "single_fallback"
    capped = _cap_parts(parts, max_parts=max_parts)
    if pause_classes is not None and len(capped) != len(parts):
        pause_classes = pause_classes[: len(capped)]
    delivery_parts = (
        _trim_semantic_delivery_boundaries(capped)
        if semantic is not None
        else capped
    )
    return {
        "schema_version": REALTIME_PLAN_SCHEMA_VERSION,
        "kind": "realtime_chat_plan",
        "session_key": session_key,
        "enabled": True,
        "max_parts": max_parts,
        "capped": len(capped) != len(parts),
        "uncapped_count": len(parts),
        "message_count": len(delivery_parts),
        "segmentation_source": segmentation_source,
        "message_parts": _message_parts(
            delivery_parts,
            chars_per_second=chars_per_second,
            rng=rng,
            first_delay=first_delay,
            pause_classes=pause_classes,
        ),
        "source_text_chars": len(raw),
    }


def _message_parts(
    parts: list[str],
    *,
    chars_per_second: float = 7.5,
    rng: random.Random | None = None,
    first_delay: float = 0.0,
    pause_classes: list[str | None] | None = None,
) -> list[dict[str, Any]]:
    picker = rng if rng is not None else random
    raw_delays = [
        _typing_delay(previous, chars_per_second=chars_per_second)
        for previous, _ in _previous_and_current(parts)
    ]
    budget = min(36.0, max(0.0, (len(parts) - 1) * 3.2))
    total = sum(raw_delays)
    scale = 1.0 if total <= budget or total <= 0 else budget / total

    # 走神：整条回复只掷一次骰子（不是每段掷），命中则挑一个非首段（index>=1）
    # 走神；无非首段（单段回复）时天然掷不到。
    distracted_index: int | None = None
    if (
        pause_classes is None
        and len(parts) > 1
        and picker.random() < _DISTRACTED_PAUSE_PROBABILITY
    ):
        distracted_index = picker.randrange(1, len(parts))

    message_parts: list[dict[str, Any]] = []
    for index, (part, delay) in enumerate(zip(parts, raw_delays, strict=True)):
        if index == 0 and first_delay > 0:
            # T1-01：首段延迟改用调用方算好的"读信+启动打字"时间（长消息/深夜情绪/
            # 隔久重逢都比裸 0 更真实），不再走原本恒为 0 的首段起手式。不吃抖动/
            # 走神——那两个效应是段内打字节奏，首段前的这段是完全不同的"读"阶段。
            final_delay = first_delay
        elif pause_classes is not None and index > 0:
            pause_class = pause_classes[index]
            low, high = _SEMANTIC_PAUSE_RANGES[pause_class or "normal"]
            final_delay = picker.uniform(low, high)
        elif index == distracted_index:
            final_delay = picker.uniform(_DISTRACTED_PAUSE_MIN, _DISTRACTED_PAUSE_MAX)
        else:
            jitter = picker.uniform(_JITTER_MIN, _JITTER_MAX)
            final_delay = min(4.2, delay * scale * jitter)
        message_parts.append(
            {
                "index": index,
                "text": part,
                "delay_before_seconds": round(final_delay, 3),
            }
        )
    return message_parts


def _coerce_semantic_parts(
    semantic_parts: Any | None,
    *,
    expected_text: str,
) -> tuple[list[str], list[str | None]] | None:
    """Validate parser output without inferring or repairing semantic boundaries."""

    if semantic_parts is None or isinstance(semantic_parts, (str, bytes, dict)):
        return None
    try:
        candidates = list(semantic_parts)
    except TypeError:
        return None
    if not candidates:
        return None

    texts: list[str] = []
    pauses: list[str | None] = []
    for index, item in enumerate(candidates):
        if isinstance(item, dict):
            part_text = item.get("text")
            pause = item.get("pause_before")
        else:
            part_text = getattr(item, "text", None)
            pause = getattr(item, "pause_before", None)
        if not isinstance(part_text, str) or not part_text:
            return None
        if hasattr(pause, "value"):
            pause = getattr(pause, "value")
        if pause is not None:
            pause = str(pause).strip().lower()
        if index == 0:
            if pause not in (None, ""):
                return None
            pause = None
        elif pause not in _SEMANTIC_PAUSE_RANGES:
            return None
        texts.append(part_text)
        pauses.append(pause)
    if "".join(texts) != expected_text:
        return None
    return texts, pauses


def _split_text_preserving(text: str, *, max_part_chars: int) -> list[str]:
    """Deterministic oversized anti-flood splitter that conserves every character."""

    if not text:
        return []
    limit = max(1, int(max_part_chars))
    remaining = text
    parts: list[str] = []
    while len(remaining) > limit:
        split_at = _split_index(remaining, max_part_chars=limit)
        if _would_split_protected_ascii_token(remaining, split_at):
            while split_at < len(remaining) and _is_ascii_token_char(remaining[split_at]):
                split_at += 1
        split_at = min(len(remaining), max(1, split_at))
        parts.append(remaining[:split_at])
        remaining = remaining[split_at:]
    if remaining:
        parts.append(remaining)
    return parts


def _previous_and_current(parts: list[str]) -> list[tuple[str, str]]:
    return [
        (parts[index - 1] if index > 0 else "", part)
        for index, part in enumerate(parts)
    ]


def _typing_delay(previous_text: str, *, chars_per_second: float = 7.5) -> float:
    if not previous_text:
        return 0.0
    visible_chars = sum(1 for char in str(previous_text) if not char.isspace())
    punctuation_pause = (
        0.75
        if str(previous_text).rstrip().endswith(("。", "！", "？", ".", "!", "?"))
        else 0.35
    )
    return round(
        min(4.2, max(0.8, visible_chars / chars_per_second + punctuation_pause)), 3
    )


def realtime_dispatch(session_key: str, text: str) -> dict[str, Any]:
    plan = realtime_plan(session_key, text)
    return {
        "kind": "realtime_chat_dispatch",
        "session_key": session_key,
        "sent": bool(plan["message_parts"]),
        "plan": plan,
    }


def _split_text(text: str, *, max_part_chars: int) -> list[str]:
    if not text:
        return []
    fragments = [
        part.strip() for part in text.replace("\r\n", "\n").split("\n") if part.strip()
    ]
    if not fragments:
        fragments = [text.strip()]
    parts: list[str] = []
    for fragment in fragments:
        parts.extend(
            _merge_short_parts(
                _split_fragment(fragment, max_part_chars=max_part_chars),
                max_part_chars=max_part_chars,
            )
        )
    return parts


def _split_fragment(text: str, *, max_part_chars: int) -> list[str]:
    pieces: list[str] = []
    remaining = text.strip()
    while remaining:
        if len(remaining) <= max_part_chars:
            pieces.append(remaining)
            break
        split_at = _split_index(remaining, max_part_chars=max_part_chars)
        if _would_split_protected_ascii_token(remaining, split_at):
            pieces.append(remaining)
            break
        pieces.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    return pieces


def _merge_short_parts(parts: list[str], *, max_part_chars: int) -> list[str]:
    merged: list[str] = []
    for part in parts:
        if not part:
            continue
        if merged and _should_merge_with_previous(
            merged[-1], part, max_part_chars=max_part_chars
        ):
            merged[-1] = f"{merged[-1]}{part}"
        else:
            merged.append(part)
    return merged


def _should_merge_with_previous(
    previous: str, current: str, *, max_part_chars: int
) -> bool:
    if len(previous) + len(current) > max_part_chars:
        return False
    return _is_too_short_part(current) or len(previous) + len(current) <= max(
        14, max_part_chars // 2
    )


def _is_too_short_part(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    return len(stripped) <= 4 and all(not char.isspace() for char in stripped)


def _split_index(text: str, *, max_part_chars: int) -> int:
    window = text[:max_part_chars]
    semantic = _preferred_split_index(window, "。！？!?；;")
    if semantic is not None:
        return semantic
    soft = _preferred_split_index(window, "，、,：:")
    if soft is not None:
        return soft
    for index in range(len(window) - 1, max(0, max_part_chars // 2) - 1, -1):
        if window[index].isspace() and _safe_ascii_boundary(text, index):
            return index + 1
    for index in range(len(window) - 1, max(0, max_part_chars // 2) - 1, -1):
        if _safe_cjk_boundary(text, index):
            return index
    return max_part_chars


def _preferred_split_index(window: str, delimiters: str) -> int | None:
    for index in range(len(window) - 1, max(0, len(window) // 2) - 1, -1):
        if window[index] in delimiters:
            return index + 1
    return None


def _safe_ascii_boundary(text: str, index: int) -> bool:
    previous_char = text[index - 1] if index > 0 else ""
    next_char = text[index + 1] if index + 1 < len(text) else ""
    return not (_is_ascii_token_char(previous_char) and _is_ascii_token_char(next_char))


def _safe_cjk_boundary(text: str, index: int) -> bool:
    if index <= 0 or index >= len(text):
        return False
    previous_char = text[index - 1]
    next_char = text[index]
    if _is_ascii_token_char(previous_char) or _is_ascii_token_char(next_char):
        return False
    return not _ascii_token_crosses_boundary(text, index)


def _ascii_token_crosses_boundary(text: str, index: int) -> bool:
    if index <= 0 or index >= len(text):
        return False
    return _is_ascii_token_char(text[index - 1]) and _is_ascii_token_char(text[index])


def _is_ascii_token_char(char: str) -> bool:
    return bool(char) and (
        char.isascii() and (char.isalnum() or char in ":/_?&=.-#%+_")
    )


def _protected_ascii_prefix_length(text: str) -> int:
    index = 0
    while index < len(text) and _is_ascii_token_char(text[index]):
        index += 1
    return index


def _would_split_protected_ascii_token(text: str, split_at: int) -> bool:
    if split_at <= 0 or split_at >= len(text):
        return False
    return _is_ascii_token_char(text[split_at - 1]) and _is_ascii_token_char(
        text[split_at]
    )


# ── T3 防护：把 LLM completion 归一为纯文本（防 content-parts 列表/repr 漏进正文）──
_LOG = logging.getLogger("astrbot_plugin_sylanne")
_content_parts_warned = False


def normalize_completion_text(value: Any) -> str:
    """把 LLM completion 归一为纯文本。

    防 T3：某些 OpenAI 兼容 provider（含 OpenAI 兼容 Gemini 端点）走完 tool 轮后把
    assistant content 返成 content-parts 列表 [{'type':'text','text':...}]，或返回它已被
    str() 成的单引号 repr（流式拼接还可能截断）。裸 str() 会把这串结构原样漏进正文。

    铁律（复审 CLUSTER B）：**只在确为 content-parts 时改写，绝不吃掉/截断正经内容**——
    正经回复恰好以 [{...'type'...}] 开头（如模型在讲 JSON schema）必须原样保留。
    ① 真 list：抽 text 拼接；但若抽不到且不像 content-parts（如 [1,2,3]）→ 原样 str()。
    ② repr 字符串：仅当【整串完整解析为含 text 的 content-parts】或【其流式截断】才抽；
       否则（带尾部 prose、非 content-parts、image-only）→ 退回原文。③ 其它 → 原样 str()。
    """
    if isinstance(value, list):
        if not value:
            return ""  # 空 list = 无内容（保持旧 `or ""` 语义）
        joined = _join_content_parts(value)
        if joined or _looks_like_content_parts(value):
            _warn_content_parts("list")
            return joined
        return str(value)  # 不像 content-parts 的 list → 不吃，原样 str
    s = "" if value is None else str(value)
    head = s.lstrip()
    if head.startswith("[{") and ("'type'" in head[:120] or '"type"' in head[:120]):
        recovered = _recover_content_parts_repr(head)
        if recovered:  # 仅在确抽到 content-parts 文本时改写；None/空 → 退回原文（绝不吃成空）
            _warn_content_parts("repr-str")
            return recovered
    return s


def _warn_content_parts(shape: str) -> None:
    """一次性告警：completion 归一触发（兼作运行期 list-vs-repr 判别探针）。"""
    global _content_parts_warned
    if not _content_parts_warned:
        _content_parts_warned = True
        _LOG.warning(
            "Sylanne T3: LLM completion 是 content-parts(%s)，已归一为纯文本"
            "（provider 把 content 返成 [{'type':'text',...}] 列表/repr，AstrBot 未归一）。",
            shape,
        )


def _looks_like_content_parts(value: Any) -> bool:
    """非空 list 且每项是带 'type' 键的 dict 或 str → 像 OpenAI content-parts。"""
    if not isinstance(value, list) or not value:
        return False
    for part in value:
        if isinstance(part, str):
            continue
        if isinstance(part, dict) and "type" in part:
            continue
        return False
    return True


def _join_content_parts(parts: Any) -> str:
    """从 content-parts（list[dict|str]）抽 text 拼接；非 text part（image/tool 等）丢弃。"""
    out: list[str] = []
    for part in parts if isinstance(parts, list) else []:
        if isinstance(part, dict):
            if part.get("type") in (None, "text"):
                txt = part.get("text")
                if isinstance(txt, str):
                    out.append(txt)
        elif isinstance(part, str):
            out.append(part)
    return "\n".join(p for p in out if p)


def _recover_content_parts_repr(s: str) -> str | None:
    """从 content-parts 的 repr 字符串抽回纯文本。**只用 literal_eval（不用脆弱正则）**：
    仅当整串完整解析为含 text 的 content-parts、或其流式截断补尾后能完整解析，才返回文本；
    其它（尾部带 prose、非 content-parts list、image-only）一律返回 None → 调用方退回原文，
    绝不吃掉/截断/串味正经内容（复审 CLUSTER B：丢正则的嵌套-text 误抽 + 转义截断 bug）。
    """
    # ① 整串完整字面量（literal_eval 本就拒绝尾部多余 prose，故 prose 会落到 ② 并失败）
    try:
        parsed = ast.literal_eval(s)
    except Exception:  # 解析不可信 provider 输出：任何解析期异常（含 RecursionError/MemoryError）都退回原文，绝不崩管线
        pass
    else:
        if isinstance(parsed, list):
            return _join_content_parts(parsed) or None  # list 但无 text → None（退回原文）
        return None  # 完整解析但非 list → 不是 content-parts
    # ② 流式截断（整串解析失败）：补常见缺尾再试，只认能解析出【含 text】的 content-parts。
    #    悬空尾部反斜杠只可能是被截断的转义（绝非有意义内容），去掉再试一轮——否则截断恰好
    #    落在 \ 上时整串补尾都解析失败 → 漏出 raw repr（复审 LANE B residual leak）。
    bases = [s]
    if s.endswith("\\"):
        bases.append(s.rstrip("\\"))
    for base in bases:
        for suffix in ("'}]", '"}]', "']}]", "}]", "]"):
            try:
                parsed = ast.literal_eval(base + suffix)
            except Exception:  # 同上：补尾再解析的任何异常都跳过该候选，绝不崩管线
                continue
            if isinstance(parsed, list):
                joined = _join_content_parts(parsed)
                if joined:
                    return joined
    return None


__all__ = [
    "strip_draft_blocks",
    "truncate_at_sentence",
    "realtime_plan",
    "realtime_dispatch",
    "normalize_completion_text",
]
