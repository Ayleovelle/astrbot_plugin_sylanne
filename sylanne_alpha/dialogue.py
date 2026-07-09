"""Sylanne-Embodiment: 对话分段与中断检测模块。

负责将连续的用户消息流切分为语义段落（segment），
并检测话题转换、消息续接、撤回等对话动力学信号。

核心功能：
- 对话分段：判断新消息是"续接上文"还是"开启新话题"
- 中断检测：识别用户在机器人回复过程中的打断行为
- 动作建议：如检测到打断，建议取消正在进行的实时派发
- 对话质量自评：从连贯性/情感匹配/信息密度三维度打分

与其他组件的关系：
- 被 body.py 在每条用户消息到达时调用
- 输出的 segment_id 用于关联同一话题的多条消息
- interruption 信息供实时派发系统决定是否取消当前回复
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

DIALOGUE_SCHEMA_VERSION = "sylanne.alpha.dialogue.v1"

# 话题转换标记词：出现这些词时判定为新话题
_TOPIC_SHIFT_MARKERS = ("换个话题", "另外", "对了", "服务器", "卡死", "报错", "bug")
# 续接标记词：出现这些词时判定为延续上一段
_CONTINUATION_MARKERS = ("还有", "而且", "然后", "就是", "也", "继续")


def segment_dialogue(
    *,
    session_key: str,
    text: str = "",
    now: float = 0.0,
    previous: dict[str, Any] | None = None,
    flags: list[str] | None = None,
    reply_in_progress: bool = False,
) -> dict[str, Any]:
    """对一条用户消息进行对话分段分析。

    参数:
        session_key: 会话标识
        text: 用户消息文本
        now: 消息时间戳
        previous: 上一条分段结果（用于判断续接）
        flags: 外部标记（如 "withdrawal" 表示撤回）
        reply_in_progress: 机器人是否正在回复中

    返回:
        包含 segment_id、relation、interruption、actions 等的分析结果
    """
    flags = list(flags or [])
    normalized = " ".join(str(text or "").split())
    previous_id = str((previous or {}).get("segment_id") or "")
    relation = _relation(normalized, previous=previous, flags=flags)
    # 续接时复用上一段的 segment_id，否则生成新 id
    segment_id = (
        previous_id
        if previous_id and relation == "continuation"
        else _segment_id(session_key, normalized, now)
    )
    interruption = _interruption(relation, reply_in_progress=reply_in_progress)
    # 如果检测到打断且机器人正在回复，建议取消实时派发
    actions = (
        ["cancel_realtime_dispatch"]
        if interruption["detected"] and reply_in_progress
        else []
    )
    return {
        "schema_version": DIALOGUE_SCHEMA_VERSION,
        "session_key": session_key,
        "segment_id": segment_id,
        "relation": relation,
        "message_time": now,
        "features": {
            "chars": len(normalized),
            "short_fragment": len(normalized) <= 24,
            "topic_shift": relation == "topic_shift",
            "withdrawal": relation == "withdrawal",
        },
        "interruption": interruption,
        "actions": actions,
        "text_preview": normalized[:80],
    }


def _relation(text: str, *, previous: dict[str, Any] | None, flags: list[str]) -> str:
    """判断当前消息与上文的关系类型。

    返回值：
    - "withdrawal": 消息撤回
    - "topic_shift": 话题转换
    - "continuation": 续接上文（短消息或含续接标记词）
    - "new_segment": 新的独立段落
    """
    if "withdrawal" in flags:
        return "withdrawal"
    if any(marker in text for marker in _TOPIC_SHIFT_MARKERS):
        return "topic_shift"
    if previous and (
        len(text) <= 24 or any(marker in text for marker in _CONTINUATION_MARKERS)
    ):
        return "continuation"
    return "new_segment"


def _interruption(relation: str, *, reply_in_progress: bool) -> dict[str, Any]:
    """判断是否构成中断事件。"""
    if relation == "withdrawal":
        return {"detected": True, "reason": "message_withdrawal"}
    if reply_in_progress and relation == "topic_shift":
        return {"detected": True, "reason": "user_topic_shift_during_reply"}
    return {"detected": False, "reason": "none"}


def _segment_id(session_key: str, text: str, now: float) -> str:
    """生成确定性的段落 ID（blake2s 哈希）。"""
    seed = f"{session_key}\0{text}\0{now:.3f}".encode("utf-8")
    return "seg-" + hashlib.blake2s(seed, digest_size=6).hexdigest()


# ---------------------------------------------------------------------------
# 对话质量自评打分器
# ---------------------------------------------------------------------------

# 情感关键词列表（标定 2026-06-15，核查任务 w9ijk6ipa + 红队）
# 红队 must-fix：删单字歧义词（爱→可爱、笑→笑话、乐→音乐 等子串假命中是最大假阳性源），
# 单字替换为无歧义多字词；扩口语情感词族（真Gemini口语"温热/真挚/陪伴/暖暖"旧表全 miss）。
# 只放多字词 + 无歧义英文词，规避子串误命中。
_EMOTION_KEYWORDS = tuple(dict.fromkeys((
    # —— 旧表保留的多字词 ——
    "开心", "高兴", "难过", "伤心", "生气", "愤怒", "害怕", "担心",
    "喜欢", "讨厌", "感动", "失望", "惊喜", "焦虑", "温暖", "孤独",
    "幸福", "痛苦", "期待", "无聊", "感谢", "抱歉", "想念", "安心",
    # —— 单字歧义词的无歧义替身（替代删掉的 烦/累/爱/恨/哭/笑/怒/悲/乐/忧）——
    "烦躁", "疲惫", "疲倦", "哭泣", "微笑", "愤恨", "怨恨", "悲伤", "忧愁", "快乐",
    # —— 口语情感词族扩充（红队验证无子串歧义）——
    "温热", "温柔", "暖心", "贴心", "窝心", "治愈", "真挚", "真诚", "珍惜", "珍贵",
    "珍重", "可惜", "不舍", "舍不得", "留恋", "眷恋", "依恋", "陪伴", "陪着", "倾诉",
    "牵挂", "思念", "想你", "在乎", "心疼", "疼爱", "心酸", "委屈", "失落", "落寞",
    "难受", "欣慰", "欢喜", "激动", "兴奋", "甜蜜", "美好", "感激", "感恩", "踏实",
    "安稳", "心动", "动心", "喜爱", "迷恋", "沉醉", "满足", "温馨", "亲密", "暖暖",
    # —— 英文（词级，子串风险低）——
    "happy", "sad", "angry", "love", "hate", "sorry", "thank",
    "miss", "fear", "hope", "joy", "pain", "warm", "cold",
    "caring", "gentle", "tender", "cherish", "grateful", "lonely",
    "comfort", "touched", "longing", "embrace", "accompany",
)))

# 词边界匹配（核查任务 wzwd8i0ta #6 + 红队复审）：英文情感词裸子串匹配会假阳性
# （warm∈warmth、miss∈dismiss、joy∈enjoy）。按语言分两路：中文无空格、夹在更长的中文里
# 时 \b 反而会漏命中，故仍用子串 in；英文则左侧禁接 ASCII 字母（挡掉 dismiss/enjoy 这类
# 前缀粘连，及 warmth 这类非屈折尾缀），右侧允许常见屈折后缀（复数/过去式/进行时/比较级/
# -ful），避免把人设常用的英文情感词屈折形（thanks/loved/missed/missing/warmer/painful）
# 误杀成 0——self_score 本就偏保守，不能再雪上加霜。
# 计数语义：捕获组只圈词根（后缀在组外），findall 取词根去重 → 仍是"命中的不同关键词数"
# （同旧 `in` 的 distinct-keyword 计数，loved/loving 不会被当成两个 love 重复计）。
_CJK_EMOTION_KEYWORDS = tuple(kw for kw in _EMOTION_KEYWORDS if not kw.isascii())
_ASCII_EMOTION_KEYWORDS = tuple(kw for kw in _EMOTION_KEYWORDS if kw.isascii())
_ASCII_EMOTION_RE = re.compile(
    r"(?<![a-z])(" + "|".join(re.escape(kw) for kw in _ASCII_EMOTION_KEYWORDS) + r")"
    r"(?:s|es|ed|d|ing|er|ers|ful)?(?![a-z])"
)
# 去 e 屈折形补丁：词根本身以 e 收尾时（love/hate/hope/embrace），-ing 会先删掉词根的 e
# （loving/hating/hoping/embracing），普通子串规则匹配不到裸词根，需单独兜底。命中后把
# 词根还原（去掉的 e 补回）再并入去重集合，保持 loved/loving 只算一次的既有语义。
_E_DROP_EMOTION_KEYWORDS = tuple(kw for kw in _ASCII_EMOTION_KEYWORDS if kw.endswith("e"))
_ASCII_EMOTION_ING_RE = (
    re.compile(
        r"(?<![a-z])(" + "|".join(re.escape(kw[:-1]) for kw in _E_DROP_EMOTION_KEYWORDS) + r")ing(?![a-z])"
    )
    if _E_DROP_EMOTION_KEYWORDS
    else None
)


def _count_emotion_hits(response_lower: str) -> int:
    """命中的不同情感词数（中文子串 + 英文词根去重）。语义同旧 `in` 的 distinct 计数，
    去 dismiss/enjoy/warmth 假阳性，但保留 thanks/loved/missed 等真实屈折形。"""
    cjk = sum(1 for kw in _CJK_EMOTION_KEYWORDS if kw in response_lower)
    ascii_matches = set(_ASCII_EMOTION_RE.findall(response_lower))
    if _ASCII_EMOTION_ING_RE is not None:
        ascii_matches.update(stem + "e" for stem in _ASCII_EMOTION_ING_RE.findall(response_lower))
    return cjk + len(ascii_matches)


def self_score(
    text: str,
    response: str,
    session_context: Any = None,
) -> dict[str, float]:
    """对话质量自评：从连贯性/情感匹配/信息密度三维度打 0-1 分。

    启发式评分规则：
    - 连贯性（coherence）：response 长度与 text 长度的比值在 0.5-3.0 之间得高分
    - 情感匹配（emotion_match）：response 中包含情感关键词的比例
    - 信息密度（info_density）：response 中非重复词占总词数的比例

    参数:
        text: 用户输入文本
        response: 系统回复文本
        session_context: 可选的会话上下文（预留扩展）

    返回:
        {"coherence": float, "emotion_match": float, "info_density": float}
        每个维度范围 [0.0, 1.0]
    """
    text_len = max(1, len(text.strip()))
    response_len = len(response.strip())

    # --- 连贯性：长度比（标定 2026-06-15）---
    # eff_user_len 地板 8：短问句（"嗯"/"在吗"）做分母会把 ratio 炸大；上限 3.0→6.0：
    # "user 短问、bot 走心长答" 是常态，旧窄区间冤杀（真机轮2 ratio3.67→0.778）。
    eff_user_len = max(text_len, 8)
    ratio = response_len / eff_user_len
    if ratio < 0.5:
        coherence = max(0.0, ratio / 0.5)              # 过短：线性衰减
    elif ratio <= 6.0:
        coherence = 1.0
    else:
        coherence = max(0.0, 1.0 - (ratio - 6.0) / 6.0)  # 6.0~12.0 线性归零

    # --- 情感匹配（标定 2026-06-15）---
    # 旧 hits/3.0 要凑 3 词→中文单条深情常 1-2 词被系统性假阴性；但首命中给太高又会假阳性。
    # 折中：命中数封顶 3（抗堆砌）+ 首命中 0.35（1 词不足以单独把均值顶过 0.7 门，需另一维配合）。
    # 映射：0→0.0  1→0.35  2→0.60  3→0.85
    response_lower = response.lower()
    tokens = _tokenize(response)
    n_tok = max(1, len(tokens))
    hits = _count_emotion_hits(response_lower)
    h = min(hits, 3)
    emotion_match = 0.0 if h == 0 else min(1.0, 0.35 + 0.25 * (h - 1))

    # --- 信息密度：MATTR（标定 2026-06-15，Covington & McFall 2010）---
    # 全局 TTR 随长度单调下降（长走心答被结构性压低）；定窗滑动 TTR 均值长度解耦。
    # n<=window 退化为普通 TTR，旧用例零漂移。
    info_density = _mattr(tokens, window=40)

    # --- 两道全局闸（红队 must-fix，选 B：penalty 乘三维）---
    # 抗堆砌：情感词占 token 比异常高 = 非自然语言堆词（实测堆砌 0.984→mid，踢出 HIGH）。
    # 短敷衍地板：回复过短整体压低（"嗯嗩好的" 不该靠 coherence=1 虚高）。
    emo_density = hits / n_tok
    stuff_factor = 0.4 if emo_density > 0.30 else 1.0
    short_factor = min(1.0, response_len / 12)
    penalty = stuff_factor * short_factor
    coherence *= penalty
    emotion_match *= penalty
    info_density *= penalty

    return {
        "coherence": round(coherence, 6),
        "emotion_match": round(emotion_match, 6),
        "info_density": round(info_density, 6),
    }


def _mattr(tokens: list[str], window: int = 40) -> float:
    """Moving-Average Type-Token Ratio：定窗滑动求 TTR 均值，长度归一。

    短文（n<=window）退化为普通 TTR，与旧 unique/total 行为一致（向后兼容）。
    长文用定窗滑动，免受 TTR 随长度单调下降的结构性压低（Covington & McFall 2010）。
    """
    n = len(tokens)
    if n == 0:
        return 0.0
    if n <= window:
        return len(set(tokens)) / n
    from collections import Counter

    counts = Counter(tokens[:window])
    acc = len(counts)
    n_windows = n - window + 1
    for i in range(1, n_windows):
        out_tok = tokens[i - 1]
        counts[out_tok] -= 1
        if counts[out_tok] == 0:
            del counts[out_tok]
        counts[tokens[i + window - 1]] += 1
        acc += len(counts)
    return (acc / n_windows) / window


def _tokenize(text: str) -> list[str]:
    """简单分词：中文按字切分，英文按空格切分，混合处理。"""
    tokens: list[str] = []
    buf: list[str] = []
    for ch in text:
        if "一" <= ch <= "鿿":
            # 中文字符：先 flush 英文 buffer，再加入单字
            if buf:
                tokens.append("".join(buf))
                buf.clear()
            tokens.append(ch)
        elif ch.isspace():
            if buf:
                tokens.append("".join(buf))
                buf.clear()
        else:
            buf.append(ch)
    if buf:
        tokens.append("".join(buf))
    return tokens


__all__ = ["DIALOGUE_SCHEMA_VERSION", "segment_dialogue", "self_score"]
