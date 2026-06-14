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

import collections
import hashlib
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
    hits = sum(1 for kw in _EMOTION_KEYWORDS if kw in response_lower)
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


__all__ = ["DIALOGUE_SCHEMA_VERSION", "segment_dialogue", "self_score", "ModeRouter", "IntrospectionHook", "SocraticMode", "ProbingMode", "WindowManager", "SilenceBreaker"]


# ---------------------------------------------------------------------------
# Item 102: 上下文窗口滑动压缩策略
# ---------------------------------------------------------------------------


class WindowManager:
    """上下文窗口管理：按重要性分层压缩。"""

    def __init__(self, max_tokens: int = 4000):
        self._max_tokens = max_tokens

    def compress(self, messages: list[dict], importance_tags: dict[int, str]) -> list[dict]:
        """压缩消息列表使其不超过 token 预算。

        importance_tags: {msg_index: "ephemeral"|"notable"|"landmark"}
        """
        # 估算当前 token 数
        total = sum(len(m.get("content", "")) // 2 for m in messages)
        if total <= self._max_tokens:
            return messages

        # 按重要性分层：landmark 保留原文，notable 截断到 100 字，ephemeral 丢弃
        result = []
        for i, msg in enumerate(messages):
            tag = importance_tags.get(i, "ephemeral")
            if tag == "landmark":
                result.append(msg)
            elif tag == "notable":
                content = msg.get("content", "")
                if len(content) > 100:
                    msg = dict(msg)
                    msg["content"] = content[:100] + "…"
                result.append(msg)
            # ephemeral: 只保留最近 3 条

        # 补充最近 3 条 ephemeral
        recent_ephemeral = [
            m for i, m in enumerate(messages[-3:])
            if importance_tags.get(len(messages) - 3 + i, "ephemeral") == "ephemeral"
        ]
        result.extend(recent_ephemeral)
        return result


# ---------------------------------------------------------------------------
# Item 91 & 99: 对话模式动态切换引擎
# ---------------------------------------------------------------------------

# 模式过渡话术映射（覆盖所有 4×3=12 种非自身组合）
_TRANSITION_HINTS: dict[tuple[str, str], str] = {
    ("serious", "playful"): "语气可以轻松一些",
    ("serious", "comfort"): "放下分析，先关心对方的感受",
    ("serious", "curious"): "带着好奇心去探索这个话题",
    ("playful", "serious"): "收起玩笑，认真对待",
    ("playful", "comfort"): "收起玩笑，认真倾听",
    ("playful", "curious"): "保持轻松，但多问几个为什么",
    ("comfort", "serious"): "情绪稳定后回到正常交流",
    ("comfort", "playful"): "心情好转了，可以开点小玩笑",
    ("comfort", "curious"): "情绪平复后，一起探索新的可能",
    ("curious", "serious"): "好奇心满足了，回到正题",
    ("curious", "playful"): "探索够了，轻松聊聊",
    ("curious", "comfort"): "先放下好奇，关注对方的状态",
}


class ModeRouter:
    """根据情绪向量动态切换对话模式。

    四种模式：
    - comfort: 安慰模式（低 valence 时触发）
    - playful: 轻松模式（低 tension + 正向 valence）
    - curious: 好奇模式（高 surprise）
    - serious: 严肃模式（默认）
    """

    MODES = ("comfort", "playful", "serious", "curious")

    def __init__(self):
        self._current_mode: str = "serious"
        self._mode_history: collections.deque = collections.deque(maxlen=50)

    @property
    def current_mode(self) -> str:
        """当前对话模式。"""
        return self._current_mode

    def route(self, valence: float, tension: float, surprise: float) -> str:
        """根据情绪向量选择对话模式。

        参数:
            valence: 情感效价 [-1, 1]，负值=消极，正值=积极
            tension: 紧张度 [-1, 1]，负值=放松，正值=紧张
            surprise: 惊讶度 [0, 1]

        返回:
            选中的模式名称
        """
        if valence < -0.3:
            new_mode = "comfort"
        elif tension < -0.2 and valence > 0.2:
            new_mode = "playful"
        elif surprise > 0.5:
            new_mode = "curious"
        else:
            new_mode = "serious"

        if new_mode != self._current_mode:
            self._mode_history.append(self._current_mode)
            self._current_mode = new_mode

        return self._current_mode

    @staticmethod
    def get_transition_hint(old_mode: str, new_mode: str) -> str:
        """返回模式切换时的过渡话术提示。

        参数:
            old_mode: 切换前的模式
            new_mode: 切换后的模式

        返回:
            过渡话术字符串；若模式相同则返回空字符串
        """
        if old_mode == new_mode:
            return ""
        return _TRANSITION_HINTS.get((old_mode, new_mode), "")


# ---------------------------------------------------------------------------
# Item 119: 自评分数异常自动复盘
# ---------------------------------------------------------------------------


class IntrospectionHook:
    """自评分数异常检测——连续低分时触发自动复盘提示。

    与 self_score 配合使用：每轮对话结束后将自评分数传入 check()，
    当连续 streak 轮平均分低于 threshold 时，生成复盘提示注入下一轮 prompt。

    设计意图：让 Sylanne 具备"自我觉察"能力——
    不是被动等待外部反馈，而是主动发现对话质量下滑并调整策略。
    """

    def __init__(self, threshold: float = 0.4, streak: int = 3):
        self._low_scores: int = 0
        self._threshold = threshold
        self._streak = streak

    def check(self, score: dict[str, float]) -> str | None:
        """检查自评分数，必要时生成复盘提示。

        Args:
            score: self_score 返回的多维度评分字典，值域 [0, 1]。

        Returns:
            复盘提示字符串（当连续低分达到阈值时），否则 None。
        """
        avg = sum(score.values()) / max(len(score), 1)
        if avg < self._threshold:
            self._low_scores += 1
        else:
            self._low_scores = 0

        if self._low_scores >= self._streak:
            self._low_scores = 0
            # 生成复盘提示：指出最弱维度
            worst = min(score, key=score.get)
            return f"连续对话质量偏低，主要问题在{worst}维度，下轮调整策略"
        return None


# ---------------------------------------------------------------------------
# Item 78: 苏格拉底式追问模式
# ---------------------------------------------------------------------------


class SocraticMode:
    """苏格拉底式追问模式——检测用户模糊观点时激活温和追问。

    设计意图：
      当用户表达不确定的观点（"可能"、"也许"、"大概"等）且 Sylanne 的好奇心
      足够高时，通过开放式问题引导对方深入思考，而非直接给出答案。

    约束：
      - 连续追问不超过 max_consecutive 次，避免变成审讯
      - 好奇心阈值 > 0.5 才激活，确保追问出于真实兴趣
      - 用户给出明确回答后自动退出追问模式
    """

    def __init__(self, max_consecutive: int = 3):
        self._consecutive_probes = 0
        self._max = max_consecutive
        self._active = False

    @property
    def active(self) -> bool:
        """当前是否处于追问模式。"""
        return self._active

    @property
    def consecutive_probes(self) -> int:
        """已连续追问的次数。"""
        return self._consecutive_probes

    def should_activate(self, text: str, curiosity: float) -> bool:
        """检测用户表达模糊观点时是否应激活追问模式。

        Args:
            text: 用户消息文本。
            curiosity: 当前好奇心水平 [0, 1]。

        Returns:
            是否应激活追问模式。
        """
        vague_markers = (
            "可能", "也许", "大概", "不确定", "感觉", "好像", "似乎",
            "maybe", "probably", "I think", "not sure",
        )
        has_vague = any(m in text for m in vague_markers)
        return has_vague and curiosity > 0.5 and self._consecutive_probes < self._max

    def activate(self) -> None:
        """激活追问模式，递增追问计数。"""
        self._active = True
        self._consecutive_probes += 1

    def deactivate(self) -> None:
        """退出追问模式，重置计数。"""
        self._active = False
        self._consecutive_probes = 0

    def get_probe_hint(self) -> str:
        """返回当前轮次的追问策略提示。

        根据已追问次数递进：
          1. 开放式问题引导
          2. 温和追问原因
          3. 轻微反例引发反思

        Returns:
            追问提示字符串。
        """
        hints = [
            "用开放式问题引导对方深入思考",
            "温和地追问'为什么这么觉得'",
            "提出一个轻微的反例让对方反思",
        ]
        idx = min(self._consecutive_probes - 1, len(hints) - 1)
        return hints[max(0, idx)]


# ---------------------------------------------------------------------------
# Item 127: 新关系的"试探"模式
# ---------------------------------------------------------------------------


class ProbingMode:
    """新关系试探模式：前 3 天嵌入轻量试探建立画像。

    在关系处于 infant 阶段时，每隔一定 tick 数自动插入一个试探性问题，
    帮助 Sylanne 快速了解用户偏好（话题、回复风格、禁忌话题）。

    约束：
    - 仅在 relationship_stage == "infant" 时激活
    - 最多使用 3 个试探问题
    - tick_count % 5 == 3 时触发（避免过于频繁）
    """

    PROBES = [
        "你平时喜欢聊什么话题？",
        "你更喜欢简短的回复还是详细的？",
        "有什么话题是你不太想聊的吗？",
    ]

    def __init__(self):
        self._probes_used: int = 0

    def should_probe(self, relationship_stage: str, tick_count: int) -> bool:
        """判断当前是否应该发出试探问题。

        Args:
            relationship_stage: 当前关系阶段（infant/young/mature/deep）。
            tick_count: 当前计算 tick 计数。

        Returns:
            True 表示应该发出试探。
        """
        return (
            relationship_stage == "infant"
            and tick_count % 5 == 3
            and self._probes_used < len(self.PROBES)
        )

    def get_probe(self) -> str:
        """获取下一个试探问题并递增计数。

        Returns:
            试探问题文本。
        """
        probe = self.PROBES[self._probes_used % len(self.PROBES)]
        self._probes_used += 1
        return probe


# ---------------------------------------------------------------------------
# Item 150: 沉默后的"破冰"模板
# ---------------------------------------------------------------------------


class SilenceBreaker:
    """根据沉默类型和持续时间选择破冰方式。

    沉默不是单一的——它可能源于受伤、消化信息、疏远或满足。
    不同类型的沉默需要不同的破冰策略：
    - hurt: 受伤沉默，需要温柔试探
    - digesting: 消化中，短时间不打扰
    - distant: 疏远，轻松打招呼
    - content: 满足的沉默，偶尔想起对方

    duration 以小时为单位，< 6h 为 short，>= 6h 为 long。
    返回空字符串表示不主动破冰。
    """

    TEMPLATES: dict[tuple[str, str], str] = {
        ("hurt", "short"): "……你还在吗？",
        ("hurt", "long"): "我想了很久，也许我该说点什么。",
        ("digesting", "short"): "",  # 不主动破冰
        ("digesting", "long"): "想好了吗？不急。",
        ("distant", "short"): "嗨。",
        ("distant", "long"): "好久不见。",
        ("content", "short"): "",
        ("content", "long"): "嗯…突然想到你。",
    }

    def get_breaker(self, texture: str, duration_hours: float) -> str:
        """根据沉默质地和持续时间返回破冰文本。

        Args:
            texture: 沉默类型，可选 "hurt"/"digesting"/"distant"/"content"。
            duration_hours: 沉默持续时间（小时）。

        Returns:
            破冰文本，空字符串表示不主动破冰。
        """
        length = "short" if duration_hours < 6 else "long"
        return self.TEMPLATES.get((texture, length), "")
