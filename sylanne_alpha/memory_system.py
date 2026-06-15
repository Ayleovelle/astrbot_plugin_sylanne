"""
Sylanne-Embodiment 三层记忆系统 v2

基于 docs/memory_system_v2_design.md 的实现。
纯 Python，无外部依赖。所有操作 < 5ms（典型负载下）。

v2 核心变更（相对 v1）:
  - 写入时机: 会话结束时写摘要到 L1（而非每条消息写原文）
  - L2 下沉: 12h 定时整理确认后下沉（而非 L1 溢出）
  - L2→L3: 30 天未被召回（而非 weight 阈值）
  - 召回后: 文本重写 + 温度漂移（reconsolidation v2）

三层结构:
  L1 (Hot Pool)  - deque, maxlen=60, 近期对话摘要
  L2 (Warm Pool) - list, 已确认的重要记忆, 向量相似度召回
  L3 (Cold Pool) - 实体-关系图, clarity 衰减
"""

from __future__ import annotations

import math
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any


class RecallMode(Enum):
    """召回引擎模式（阶段0 灰度开关）。

    LEGACY     — 现有两阶段四维加权召回（默认，行为零变化）。
    SHADOW     — 新旧并跑：返回 LEGACY 结果，后台计算 ACTIVATION 并记录差异（不影响线上）。
    ACTIVATION — ACT-R 激活核召回（阶段1+ 实现后启用）。
    """

    LEGACY = "legacy"
    SHADOW = "shadow"
    ACTIVATION = "activation"

# ---------------------------------------------------------------------------
# 写入时重要性启发式（模块级，零 LLM）
#
# 提到模块级，使 MemoryItem.from_dict 无需反向依赖 MemorySystem（消除分层倒置：
# 数据类不应回调聚合根的静态方法）。MemorySystem 仍暴露同名静态方法薄封装兼容旧调用。
# ---------------------------------------------------------------------------

# 承诺/事实类关键词：名字、日期、数字、喜好、约定等高保留信号
_COMMITMENT_KW = (
    "喜欢", "讨厌", "答应", "约定", "约好", "记得", "别忘", "一定", "保证",
    "承诺", "生日", "纪念", "名字", "叫我", "我叫", "明天", "后天", "下周",
    "下个月", "号见", "点见", "等我", "等你",
)


def _has_commitment_kw(text: str) -> bool:
    """检测文本是否含承诺/事实类关键词（关键词表 + 阿拉伯数字模式）。"""
    if not text:
        return False
    for kw in _COMMITMENT_KW:
        if kw in text:
            return True
    # 含阿拉伯数字（日期/数量/时间）也视为高信息
    return any(c.isdigit() for c in text)


def _compute_importance_heuristic(
    text: str, source_turns: int, temperature: float
) -> float:
    """写入时零-LLM 重要性打分，复用 source_turns/temperature/长度/承诺关键词。

    - 基线 0.30
    - 聊得久（source_turns 多）→ 更重要
    - 情绪强烈（|temperature| 大）→ 更重要
    - 信息量（文本长）→ 更重要
    - 含承诺/事实类关键词 → 加成
    """
    t = max(-1.0, min(1.0, float(temperature)))
    imp = 0.30
    imp += 0.25 * min(source_turns / 4.0, 1.0)
    imp += 0.30 * abs(t)
    imp += 0.15 * min(len(text) / 120.0, 1.0)
    if _has_commitment_kw(text):
        imp += 0.20
    return max(0.0, min(1.0, imp))


# ---------------------------------------------------------------------------
# 阶段2：L3 spreading activation 关系语义强度规则表（零 LLM）
#
# 关系类型决定激活沿边扩散的强度：核心情感/归属关系传导强，弱关联传导弱。
# ingest 时按此表给 GraphEdge.strength 赋值；表外关系回退默认值。
# ---------------------------------------------------------------------------
_RELATION_WEIGHTS: dict[str, float] = {
    "爱": 1.0, "喜欢": 0.9, "讨厌": 0.8, "害怕": 0.8, "想念": 0.85,
    "是": 0.85, "属于": 0.8, "拥有": 0.85, "等于": 0.85,
    "参与": 0.6, "发生在": 0.6, "提到": 0.55, "相关": 0.5, "认识": 0.6,
    "类似": 0.3, "可能": 0.25,
}
_RELATION_WEIGHT_DEFAULT = 0.4


def _relation_strength(relation: str) -> float:
    """按关系类型查语义强度；含子串匹配以容忍 LLM 抽取的措辞变体。"""
    if relation in _RELATION_WEIGHTS:
        return _RELATION_WEIGHTS[relation]
    for kw, w in _RELATION_WEIGHTS.items():
        if kw in relation:
            return w
    return _RELATION_WEIGHT_DEFAULT


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class MemoryItem:
    """单条记忆条目，驻留于 L1 或 L2。

    字段说明：
    - weight: 记忆权重 [0,1]，衰减到 0 时被回收
    - temperature: 情绪温度，正值=温暖记忆，负值=冷淡记忆
    - age_ticks: 年龄计数器，每次 tick_decay 递增
    - confirmed: 是否经过 12h 整理确认（确认后才能下沉到 L2）
    - recall_count: 被召回次数（召回会强化权重）
    - rewrite_count: 被重写次数（reconsolidation，上限 20 次）
    """

    id: str
    text: str
    weight: float
    temperature: float
    age_ticks: int
    embedding: list[float] | None
    created_at: float
    source_turns: int = 1
    confirmed: bool = False
    recall_count: int = 0
    last_recalled_tick: int = 0
    rewrite_count: int = 0
    # 记忆来源："dialogue"=与用户真实对话；"life_sim"=Sylanne 自己的生活模拟/心境
    source: str = "dialogue"
    # 拟人化召回重构：重要性（写入时零-LLM 启发式打分，持久化）
    importance: float = 0.5
    # 召回刷新时间戳（与 created_at 解耦：created_at 保护真实创建时间，
    # last_recalled_ts 在被召回时刷新，使 recency 复活）
    last_recalled_ts: float = 0.0
    # 阶段0地基（ACT-R base-level learning 用）：EMA 激活累加器，近似 Σtⱼ⁻ᵈ。
    # 命中时按 acc = acc*(dt_h**-d) + 1 递推，免存完整召回时间序列。默认 1.0=单次编码。
    # LEGACY 召回路径不读它，仅在 ACTIVATION 模式生效——阶段0 只负责持久化与回填。
    actr_acc: float = 1.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "weight": self.weight,
            "temperature": self.temperature,
            "age_ticks": self.age_ticks,
            "embedding": self.embedding,
            "created_at": self.created_at,
            "source_turns": self.source_turns,
            "confirmed": self.confirmed,
            "recall_count": self.recall_count,
            "last_recalled_tick": self.last_recalled_tick,
            "rewrite_count": self.rewrite_count,
            "source": self.source,
            "importance": self.importance,
            "last_recalled_ts": self.last_recalled_ts,
            "actr_acc": self.actr_acc,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryItem":
        # 旧存档兼容：importance 缺省时用启发式回填（而非固定 0.5）。
        # last_recalled_ts 缺省 0.0 即可——recency 评分取 max(created_at, last_recalled_ts)，
        # 0.0 会自然回退到 created_at，二者等效。
        created_at = d["created_at"]
        if "importance" in d:
            # clamp 到 [0,1]：旧/异常存档若写入越界值会让 recency τ 极度膨胀、永不衰减。
            importance = max(0.0, min(1.0, float(d["importance"])))
        else:
            importance = _compute_importance_heuristic(
                d["text"],
                d.get("source_turns", 1),
                d.get("temperature", 0.0),
            )
        return cls(
            id=d["id"],
            text=d["text"],
            weight=d["weight"],
            temperature=d["temperature"],
            age_ticks=d["age_ticks"],
            embedding=d.get("embedding"),
            created_at=created_at,
            source_turns=d.get("source_turns", 1),
            confirmed=d.get("confirmed", False),
            recall_count=d.get("recall_count", 0),
            last_recalled_tick=d.get("last_recalled_tick", 0),
            rewrite_count=d.get("rewrite_count", 0),
            source=d.get("source", "dialogue"),
            importance=importance,
            last_recalled_ts=float(d.get("last_recalled_ts", 0.0)),
            # 旧存档无 actr_acc：回填 1.0（中性激活）而非用未知历史 d 重算召回序列，
            # 避免历史与新 d 语义不匹配。频次信号仍由 recall_count 保留，阶段1 ACT-R
            # 可参考。切到 ACTIVATION 后头几次召回会自然把 acc 累积正常化。
            actr_acc=float(d.get("actr_acc", 1.0)),
        )


@dataclass
class MemoryResult:
    """召回结果，包含最终评分和来源层信息。

    final_score 是综合评分，由层权重、记忆权重、相关度、情绪偏差共同决定。
    """

    text: str
    layer: str  # "L1" | "L2" | "L3"
    weight: float
    relevance: float
    clarity: float
    temperature: float
    final_score: float
    created_at: float  # 记忆创建时间戳，用于生成相对时间标签
    recall_count: int = 0  # 被召回次数，参与 _recency_score 的 τ（衰减变慢）
    emotional_weight: float = 0.5  # 情感权重 [0,1]
    recall_reason: str = ""  # 召回原因: keyword_match / vector_similarity / temporal_proximity / association_graph
    # 记忆来源："dialogue"=与用户真实对话；"life_sim"=Sylanne 自己的生活模拟/心境
    source: str = "dialogue"
    # 拟人化召回重构：重要性（注入/调试用，来自 item.importance 或 L3 clarity 近似）
    importance: float = 0.5
    # 命中后刷新用：指向底层 MemoryItem/GraphNode 的引用（不参与比较/repr）
    source_obj: Any = field(default=None, repr=False, compare=False)
    # 阶段0地基（可观测）：ACTIVATION 模式下的置信分级与激活值；LEGACY 下保持默认。
    # confidence ∈ {clear, vague, tot}（阶段3 启用），activation 为 ACT-R 激活归一值。
    confidence: str = "clear"
    activation: float = 0.0
    # 调试快照（每候选的打分分解，影子模式/WebUI 用；不参与比较/repr）
    debug: dict = field(default_factory=dict, repr=False, compare=False)

    # ------------------------------------------------------------------
    # 记忆温度（Item 147）
    # ------------------------------------------------------------------

    @property
    def memory_temperature(self) -> str:
        """基于创建时间和召回次数计算记忆温度。

        - hot: 24h 内创建 或 最近被召回（recall_count > 0 且 created_at 在 48h 内）
        - warm: 7 天内
        - cold: 30 天+
        """
        now = time.time()
        age_seconds = now - self.created_at if self.created_at > 0 else float("inf")
        age_days = age_seconds / 86400

        # hot: 24h 内 或 最近被频繁召回（48h 内且有召回记录）
        if age_days <= 1.0:
            return "hot"
        if age_days <= 2.0 and self.recall_count > 0:
            return "hot"
        # warm: 7 天内
        if age_days <= 7.0:
            return "warm"
        # cold: 30 天+（7~30 天之间也归为 warm）
        if age_days <= 30.0:
            return "warm"
        return "cold"


@dataclass
class GraphNode:
    """L3 知识图谱节点。

    temporal_type 决定衰减行为：
    - permanent: 永不衰减（如"用户喜欢猫"）
    - evolving: 有时效性，超过 staleness_threshold 天后加速衰减
    - episodic: 普通衰减（默认）
    """

    id: str
    label: str
    type: str  # person/topic/event/preference/boundary
    temporal_type: str  # permanent/evolving/episodic
    emotion_weight: float  # [-1.0, 1.0]
    clarity: float  # [0.0, 1.0]
    recall_count: int = 0
    valid_from: str | None = None  # ISO date for evolving
    staleness_threshold: int = 180  # days, default 6 months
    # 拟人化召回：节点真实创建时间 + 召回刷新时间戳（与 MemoryItem 对齐）。
    # 缺失时 recency 评分会退化为中性 0.5，因此创建/命中时必须写入。
    created_at: float = 0.0
    last_recalled_ts: float = 0.0
    # 阶段0地基（ACT-R）：与 MemoryItem 对齐的 EMA 激活累加器。LEGACY 路径不读。
    actr_acc: float = 1.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "type": self.type,
            "temporal_type": self.temporal_type,
            "emotion_weight": self.emotion_weight,
            "clarity": self.clarity,
            "recall_count": self.recall_count,
            "valid_from": self.valid_from,
            "staleness_threshold": self.staleness_threshold,
            "created_at": self.created_at,
            "last_recalled_ts": self.last_recalled_ts,
            "actr_acc": self.actr_acc,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GraphNode":
        return cls(
            id=d["id"],
            label=d["label"],
            type=d["type"],
            temporal_type=d.get("temporal_type", "episodic"),
            emotion_weight=d["emotion_weight"],
            clarity=d["clarity"],
            recall_count=d.get("recall_count", 0),
            valid_from=d.get("valid_from"),
            staleness_threshold=d.get("staleness_threshold", 180),
            created_at=float(d.get("created_at", 0.0)),
            last_recalled_ts=float(d.get("last_recalled_ts", 0.0)),
            actr_acc=float(d.get("actr_acc", 1.0)),
        )


@dataclass
class GraphEdge:
    """L3 知识图谱边。"""

    source: str
    target: str
    relation: str
    emotion_weight: float  # [-1.0, 1.0]
    clarity: float  # [0.0, 1.0]
    last_recalled: int = 0  # tick
    # 阶段0地基（阶段2 spreading activation 用）：关系语义强度 [0,1]。
    # ingest 时按关系类型规则表赋值（阶段2 落地），缺省回退到 clarity*|emotion| 的近似。
    # LEGACY 路径不读它，仅持久化与回填。
    strength: float = 1.0

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "relation": self.relation,
            "emotion_weight": self.emotion_weight,
            "clarity": self.clarity,
            "last_recalled": self.last_recalled,
            "strength": self.strength,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GraphEdge":
        return cls(
            source=d["source"],
            target=d["target"],
            relation=d["relation"],
            emotion_weight=d["emotion_weight"],
            clarity=d["clarity"],
            last_recalled=d.get("last_recalled", 0),
            # 旧存档无 strength：用 clarity*|emotion_weight| 近似回填（情绪越强、越清晰
            # 的关系语义强度越高），clamp [0,1]。阶段2 上线后新边按关系规则表赋值。
            strength=float(
                d.get(
                    "strength",
                    max(0.0, min(1.0, d["clarity"] * abs(d["emotion_weight"]))),
                )
            ),
        )


@dataclass
class ConversationBuffer:
    """会话暂存区，对话进行中暂存原文，不写入 MemorySystem。

    v2 设计：对话进行中不直接写入记忆系统，
    而是在会话结束（idle 超时或达到 20 轮）时生成摘要再写入 L1。
    这避免了"每条消息都写入"导致的噪声问题。
    """

    session_key: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    last_activity: float = 0.0
    turn_count: int = 0
    last_flush_ts: float = 0.0

    def append(self, role: str, text: str, ts: float | None = None) -> None:
        now = ts or time.time()
        self.messages.append({"role": role, "text": text, "ts": now})
        self.last_activity = now
        if role == "bot":
            self.turn_count += 1

    def _in_active_exchange(self, now: float) -> bool:
        """结构判定：是否处于"活跃来回"中（任务/纠正链进行中，不是真闲置）。

        2026-06-15 事故：用户连续纠正改写任务，轮次间隔 ~90s，被 60s idle flush
        抽干上下文，Agent 读到空 buffer 转去翻 SQLite 主动消息→话题彻底漂走。
        纯结构信号（消息条数 + 近端轮次间隔），不看内容：最近 3 条里若有快速来回
        （相邻间隔中位数 < 90s），说明这是一段活着的对话线程，给更长的 idle 宽限。
        """
        msgs = self.messages
        if len(msgs) < 3:
            return False
        recent = msgs[-4:]
        gaps = [
            float(recent[i]["ts"]) - float(recent[i - 1]["ts"])
            for i in range(1, len(recent))
            if recent[i].get("ts") and recent[i - 1].get("ts")
        ]
        if not gaps:
            return False
        gaps.sort()
        median_gap = gaps[len(gaps) // 2]
        # 近端轮次密集（来回快）且整体未冷太久 → 仍算活跃
        return median_gap < 90.0 and (now - self.last_activity) < 240.0

    def should_flush(self, idle_seconds: float = 60.0, max_turns: int = 20) -> str:
        """返回触发原因，空字符串表示不需要 flush。"""
        if not self.messages:
            return ""
        if self.turn_count >= max_turns:
            return "max_turns"
        now = time.time()
        # 活跃来回中（任务/纠正链）：把 idle 宽限拉长到 3x，别在用户连续纠正的
        # 间隙里把任务态 flush 掉（事故根因 L3）。仍受 max_turns 硬上限兜底。
        effective_idle = idle_seconds * 3.0 if self._in_active_exchange(now) else idle_seconds
        if now - self.last_activity >= effective_idle:
            has_user = any(m.get("role") == "user" for m in self.messages)
            if not has_user and now - self.last_activity < idle_seconds * 3:
                return ""
            return "idle"
        return ""

    def drain(self) -> list[dict[str, Any]]:
        """取出所有消息并重置计数。"""
        msgs = self.messages[:]
        self.messages.clear()
        self.turn_count = 0
        self.last_flush_ts = time.time()
        return msgs

    def inject_context(self, entries: list[dict]) -> None:
        """注入群聊旁观消息作为背景上下文（插入到头部）。"""
        for i, entry in enumerate(entries):
            self.messages.insert(
                i,
                {
                    "role": "group_observed",
                    "text": entry["text"],
                    "ts": entry["ts"],
                    "sender_id": entry.get("sender_id", ""),
                },
            )

    def to_dict(self) -> dict:
        return {
            "session_key": self.session_key,
            "messages": self.messages,
            "last_activity": self.last_activity,
            "turn_count": self.turn_count,
            "last_flush_ts": self.last_flush_ts,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ConversationBuffer":
        buf = cls(session_key=d["session_key"])
        buf.messages = d.get("messages", [])
        buf.last_activity = d.get("last_activity", 0.0)
        buf.turn_count = d.get("turn_count", 0)
        buf.last_flush_ts = d.get("last_flush_ts", 0.0)
        return buf


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

# 模块级 jieba 导入（避免每次 _tokenize 调用都尝试 import）
try:
    import jieba as _jieba
except ImportError:
    _jieba = None


def _cosine(a: list[float], b: list[float]) -> float:
    """内联余弦相似度计算。输入退化时返回 -1.0 哨兵值。"""
    if not a or not b or len(a) != len(b):
        return -1.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na <= 0.0 or nb <= 0.0:
        return -1.0
    return dot / (na * nb)


def _tokenize(text: str) -> set[str]:
    """中文分词：优先 jieba，fallback 到字符 bigram + 空格分词混合。"""
    text = text.lower().strip()
    if not text:
        return set()
    if _jieba is not None:
        return set(
            w
            for w in _jieba.cut(text)
            if len(w.strip()) >= 1 and w.strip() not in _STOPWORDS
        )
    # Fallback: 空格分词（英文）+ 字符 bigram（中文）
    tokens: set[str] = set()
    for word in text.split():
        if len(word) >= 2:
            tokens.add(word)
    # 中文字符 bigram
    chars = [c for c in text if "一" <= c <= "鿿"]
    for i in range(len(chars) - 1):
        tokens.add(chars[i] + chars[i + 1])
    # 单字也加入（短查询时有用）
    for c in chars:
        tokens.add(c)
    return tokens


_STOPWORDS = frozenset("的了是在我你他她它们这那有不会就都也要能可以说到和与及")


def _keyword_overlap(query: str, text: str) -> float:
    """关键词重叠度计算，支持中文（jieba 或 bigram 回退）。"""
    q_words = _tokenize(query)
    t_words = _tokenize(text)
    if not q_words or not t_words:
        return 0.0
    intersection = q_words & t_words
    return len(intersection) / max(len(q_words), 1)


def _keyword_overlap_precomputed(query_tokens: set[str], text: str) -> float:
    """关键词重叠度计算（query 已预分词，避免重复 tokenize）。"""
    if not query_tokens:
        return 0.0
    t_words = _tokenize(text)
    if not t_words:
        return 0.0
    intersection = query_tokens & t_words
    return len(intersection) / max(len(query_tokens), 1)


# ---------------------------------------------------------------------------
# AnniversaryDetector (Item 33)
# ---------------------------------------------------------------------------


class AnniversaryDetector:
    """追踪关系里程碑日期。"""

    def __init__(self) -> None:
        self._milestones: dict[str, dict] = {}  # session_key -> {first_chat, important_events: [...]}

    def record_first_chat(self, session_key: str, timestamp: float) -> None:
        if session_key not in self._milestones:
            self._milestones[session_key] = {"first_chat": timestamp, "important_events": []}

    def record_important_event(self, session_key: str, event: str, timestamp: float) -> None:
        if session_key in self._milestones:
            self._milestones[session_key]["important_events"].append({"event": event, "timestamp": timestamp})

    def check_anniversaries(self, session_key: str, now: float) -> list[str]:
        """检查是否有纪念日到期。返回纪念描述列表。"""
        results: list[str] = []
        data = self._milestones.get(session_key)
        if not data:
            return results

        first = data["first_chat"]
        age_days = (now - first) / 86400

        # 里程碑检测
        milestones = [7, 30, 90, 180, 365]
        for m in milestones:
            if m - 0.5 <= age_days <= m + 0.5:
                results.append(f"认识第 {m} 天")

        return results

    def to_dict(self) -> dict:
        return dict(self._milestones)

    @classmethod
    def from_dict(cls, data: dict) -> "AnniversaryDetector":
        det = cls()
        det._milestones = data
        return det


# ---------------------------------------------------------------------------
# MemorySystem
# ---------------------------------------------------------------------------

# v2 常量
IDLE_FLUSH_SECONDS = 60.0  # 空闲多久触发 flush
MAX_TURNS_BEFORE_FLUSH = 20  # 最多多少轮触发 flush
CONSOLIDATION_INTERVAL_HOURS = 12  # 整理间隔（小时）
CONSOLIDATION_KEEP_RECENT_HOURS = 2  # 整理时保护最近 N 小时的未确认条目
L2_COMPRESSION_AGE_TICKS = 3000  # L2→L3 压缩阈值（约 30 天，按 100 条/天计）
REWRITE_FREEZE_AFTER = 20  # 单条记忆最多重写次数（防止无限 reconsolidation）


class MemorySystem:
    """三层记忆系统 v2 主接口。

    L1: Hot Pool (deque, maxlen=60) - 近期对话摘要，未确认的可能被丢弃
    L2: Warm Pool (list) - 已确认的重要记忆，支持向量相似度召回和 reconsolidation
    L3: Cold Pool (graph) - 实体-关系图，clarity 缓慢衰减

    核心流程：
    1. 对话中：消息暂存在 ConversationBuffer
    2. 会话结束：摘要写入 L1（write_summary）
    3. 12h 整理：确认重要条目，下沉到 L2（sink_to_l2）
    4. 30 天未召回：L2 条目压缩为 L3 图谱节点
    5. 召回时：三层并行查询，加权合并返回 top-k

    人格驱动参数：
    - base_decay: 基础衰减率（尽责性低→衰减快）
    - reconsolidation_rate: 召回时情绪温度的更新率（开放性高→更新快）
    - positive_recall_bias: 正向记忆的召回偏好（宜人性高→偏好正向）
    """

    _LAYER_WEIGHTS = {"L1": 1.0, "L2": 0.7, "L3": 0.4}
    _L1_CAPACITY = 60
    _L3_NODE_LIMIT = 1000

    # 拟人化召回：阶段1宽召回候选数（仅按 relevance 粗筛取 top-K）
    _RECALL_WIDE_K = 20
    # 高重要性旁路保底：阶段1额外保留 importance 最高的 N 条进入 rerank，
    # 防止 relevance 低但极重要（承诺/约定）的条目被 top-K 截断。
    _RECALL_IMPORTANCE_BYPASS = 3
    _RECALL_IMPORTANCE_BYPASS_FLOOR = 0.8
    # recency τ 公式中 recall_count 的封顶（10 次后 τ 增益饱和，约 6 倍基线），
    # 防止高频老记忆衰减无限变慢、永久垄断召回。
    _RECENCY_RECALL_CAP = 10
    # 近期记忆（5 分钟内）关键词 relevance=0 时的兜底分，确保进入阶段2 rerank。
    _RECENT_FLOOR_RELEVANCE = 0.05

    # 记忆温度前缀映射（Item 148）
    _TEMPERATURE_PREFIXES = {
        "hot": "（刚才提到）",
        "warm": "（之前聊过）",
        "cold": "（很久以前）",
    }

    # P1 性能优化：衰减/GC 频率控制
    _DECAY_L3_EVERY_N = 5       # L3 clarity 衰减每 N tick 执行一次
    _GC_EVERY_N = 20            # GC（剪枝死节点/重建列表）每 N tick 执行一次
    _GC_L2_SIZE_THRESHOLD = 600  # L2 超过此大小时强制 GC

    def __init__(self, **kwargs) -> None:
        self._l1: deque[MemoryItem] = deque(maxlen=self._L1_CAPACITY)
        self._l2: list[MemoryItem] = []
        self._l3_nodes: dict[str, GraphNode] = {}
        self._l3_edges: list[GraphEdge] = []
        self._tick: int = 0
        self._last_consolidation_ts: float = 0.0
        self._recalled_l2_items: list[MemoryItem] = []
        self._gc_tick_counter: int = 0  # GC 计数器
        self._inverted_index = InvertedIndex()
        # 阶段0 召回灰度开关：默认 LEGACY（零行为变化）。可由 kwargs 或环境变量
        # SYLANNE_RECALL_MODE 覆盖；非法值静默回退 LEGACY。
        self._recall_mode: RecallMode = self._resolve_recall_mode(
            kwargs.get("recall_mode")
        )
        # SHADOW 模式下记录最近一次新旧召回差异（供 get_debug_snapshot 读取）
        self._last_shadow_diff: dict[str, Any] | None = None
        self._params: dict[str, float] = {
            "base_decay": 0.02,
            "age_coeff": 0.15,
            "recall_boost": 0.03,
            "age_reset_factor": 0.5,
            "reconsolidation_rate": 0.05,
            "compression_threshold": 0.15,
            "mood_weight": 0.2,
            "positive_recall_bias": 1.0,
            "cold_memory_decay_factor": 1.0,
            "neuroticism": 0.5,
            # 拟人化召回四维权重（和=1，由人格推导覆盖）
            "w_rel": 0.45,
            "w_rec": 0.25,
            "w_imp": 0.15,
            "w_emo": 0.15,
            # 人格化硬门控基线（composite < gate → 丢弃，空召回优于错召回）
            "recall_gate_base": 0.20,
            # 阶段1 ACT-R 激活核参数默认值（无人格时也能跑 ACTIVATION 模式）
            "actr_d": 0.50,
            "actr_importance_scale": 1.25,
            "actr_emo_scale": 0.35,
            "actr_base_threshold": -1.1,
            "w_rel_act": 0.55,
            "w_act": 0.45,
            # 阶段3 软召回三级置信 + 情感特权默认值
            "theta_clear": 0.55,
            "theta_tot": 0.15,
            "emotion_privilege_k": 0.20,
            "emo_bypass_floor": 0.55,
            "emo_bypass_imp_floor": 0.55,
            "l1_confidence": 0.85,
            # 原始人格值（子方法 novelty/spreading 读取；无人格时中性 0.5）
            "perception_acuity_raw": 0.5,
            "relational_gravity_raw": 0.5,
            "inner_order_raw": 0.5,
            "boundary_permeability": 0.5,
        }

        personality_keys = {
            "openness",
            "conscientiousness",
            "extraversion",
            "agreeableness",
            "neuroticism",
            "expression_drive_trait",
            "perception_acuity",
            "boundary_permeability",
            "inner_order",
            "relational_gravity",
        }
        personality = {k: v for k, v in kwargs.items() if k in personality_keys}
        if personality:
            self.derive_params(personality)

    # ------------------------------------------------------------------
    # 人格参数推导
    # ------------------------------------------------------------------

    def derive_params(self, personality: dict[str, float]) -> None:
        """从人格向量推导记忆系统参数。

        接受 Big Five 或 Embodiment Five 名称。
        人格如何影响记忆：
        - 高尽责性(C) → 低衰减率（记忆保持更久）
        - 高神经质(N) → 高年龄系数（旧记忆衰减更快）+ 情绪权重更大
        - 高开放性(O) → 高 reconsolidation 率（记忆更容易被重写）
        - 高宜人性(A) → 正向记忆召回偏好更强
        """
        openness_val = personality.get(
            "openness", personality.get("boundary_permeability", 0.5)
        )
        C = personality.get("conscientiousness", personality.get("inner_order", 0.5))
        _E = personality.get(
            "extraversion", personality.get("expression_drive_trait", 0.5)
        )  # noqa: F841
        A = personality.get("agreeableness", personality.get("relational_gravity", 0.5))
        N = personality.get("neuroticism", personality.get("perception_acuity", 0.5))

        self._params["base_decay"] = 0.01 + (1 - C) * 0.03
        self._params["age_coeff"] = 0.1 + N * 0.1
        self._params["reconsolidation_rate"] = 0.03 + openness_val * 0.04
        self._params["mood_weight"] = 0.1 + N * 0.2
        self._params["compression_threshold"] = 0.15 + openness_val * 0.10
        self._params["positive_recall_bias"] = 1.0 + A * 0.3
        # 高神经质 → 低温记忆衰减更慢（更难忘记冷淡/负面记忆）
        self._params["cold_memory_decay_factor"] = 1.0 - N * 0.5
        self._params["neuroticism"] = N

        # ---- 拟人化召回：四维权重 = 人格函数（归一化和=1）----
        # perception_acuity（感知敏锐）→ 语义相关主导；缺省回退 N。
        # relational_gravity（关系引力）→ mood-congruent 主导；缺省回退 A。
        pa = personality.get("perception_acuity", N)
        rg = personality.get("relational_gravity", A)
        raw_rel = 0.40 + pa * 0.60  # 感知敏锐→语义相关主导
        raw_rec = 0.30 + N * 0.30   # 神经质→更黏近期
        raw_imp = 0.30 + C * 0.50   # 尽责→重要性导向
        raw_emo = 0.20 + rg * 0.60  # 关系引力→mood-congruent 主导
        s = raw_rel + raw_rec + raw_imp + raw_emo
        if s <= 0:
            s = 1.0
        self._params["w_rel"] = raw_rel / s
        self._params["w_rec"] = raw_rec / s
        self._params["w_imp"] = raw_imp / s
        self._params["w_emo"] = raw_emo / s
        # 人格化硬门控：高感知人格门槛更高（更挑剔，宁缺毋滥）
        self._params["recall_gate_base"] = 0.20 + pa * 0.15

        # ---- 阶段1：ACT-R 激活核参数（ACTIVATION 模式用；LEGACY 不读）----
        io = personality.get("inner_order", C)
        # 存原始人格值供子方法读取（novelty/spreading 等按需取，避免重算/失配）。
        self._params["perception_acuity_raw"] = pa
        self._params["relational_gravity_raw"] = rg
        self._params["inner_order_raw"] = io
        self._params["boundary_permeability"] = personality.get(
            "boundary_permeability", personality.get("openness", 0.5)
        )
        # base-level 衰减率 d ∈[0.30,0.70]：高内秩序/尽责→d 小→衰减慢→记得久。
        self._params["actr_d"] = 0.70 - io * 0.40
        # importance 作 activation 先验偏置的幅度 ∈[0.5,2.0]：高尽责→更重视重要性。
        # 注意：importance 在 ACTIVATION 模式只经此处进入打分（不再有独立 w_imp 维度），
        # 避免 LEGACY 曾犯的双重计入。
        self._params["actr_importance_scale"] = 0.5 + C * 1.5
        # mood-congruent 对检索阈值的调节系数 ∈[0.1,0.6]：高关系引力→情绪更影响门控。
        self._params["actr_emo_scale"] = 0.1 + rg * 0.5
        # 激活门控基线（A < threshold → 丢弃）∈[-1.5,-0.7]：高感知→门槛略高、更挑剔。
        self._params["actr_base_threshold"] = -1.5 + pa * 0.8
        # ACTIVATION 模式二维权重：composite = w_rel_act*rel + w_act*activation。
        # （recency+frequency 已被 base-level 统一吸收，importance 已并入 activation，
        # emotional 走 threshold 调节，故只剩 rel 与 activation 两维。）
        raw_rel_act = 0.40 + pa * 0.60   # 感知敏锐→语义相关主导
        raw_act = 0.40 + io * 0.40       # 内秩序→激活（频次/近因/重要）主导
        sa = raw_rel_act + raw_act
        if sa <= 0:
            sa = 1.0
        self._params["w_rel_act"] = raw_rel_act / sa
        self._params["w_act"] = raw_act / sa

        # ---- 阶段3：软召回三级置信阈值 + 情感特权（ACTIVATION 模式用）----
        # 修正 LEGACY 的"感知越敏锐 gate 越高→越健忘"反直觉：这里 pa 高 → 分辨更细
        # （clear 门槛略高使 vague 区间更宽），而非整体更难召回。
        self._params["theta_clear"] = 0.45 + pa * 0.20   # 确信阈值 ∈[0.45,0.65]
        self._params["theta_tot"] = 0.10 + C * 0.10      # 舌尖下限 ∈[0.10,0.20]
        # 情感特权：高关系引力→情感记忆获得更大激活加成、更低旁路门槛。
        self._params["emotion_privilege_k"] = 0.10 + rg * 0.25   # ∈[0.10,0.35]
        self._params["emo_bypass_floor"] = 0.65 - rg * 0.20      # ∈[0.45,0.65]
        self._params["emo_bypass_imp_floor"] = 0.65 - rg * 0.15  # ∈[0.50,0.65]
        # 阶段2：L1 层置信折扣（仅 ACTIVATION 用，取代 _LAYER_WEIGHTS 硬乘）。
        # L1 是未确认近期摘要，尽责性高→对未确认记忆更挑剔（折扣更狠）。
        # L2 已确认、L3 已有 clarity 衰减，不再额外折扣（否则与 activation 重复惩罚）。
        self._params["l1_confidence"] = 0.70 + io * 0.30  # ∈[0.70,1.0]

    # ------------------------------------------------------------------
    # 写入（v2：基于摘要）
    # ------------------------------------------------------------------

    _MAX_SUMMARY_CHARS = 500

    def write_summary(
        self,
        text: str,
        source_turns: int = 1,
        embedding: list[float] | None = None,
        temperature: float = 0.0,
        source: str = "dialogue",
        importance: float | None = None,
    ) -> MemoryItem:
        """v2 写入：将对话摘要写入 L1。由会话结束/20轮保底触发。

        source: "dialogue"=与用户真实对话；"life_sim"=Sylanne 自己的生活模拟/心境。
        importance: 重要性 [0,1]，None 时用零-LLM 启发式打分（_compute_importance）。
        """
        text = text[: self._MAX_SUMMARY_CHARS]
        if importance is None:
            # 基础启发式 + 新颖度（RPE）加成：重复内容不再因文本长而持续拿高分。
            importance = self._compute_importance(text, source_turns, temperature)
            importance = min(1.0, importance + self._compute_novelty_bonus(text))
        # L1 满时，把最老的已确认项下沉到 L2（防止静默丢失）
        if len(self._l1) >= self._L1_CAPACITY:
            self._overflow_rescue()

        item = MemoryItem(
            id=uuid.uuid4().hex[:12],
            text=text,
            weight=1.0,
            temperature=temperature,
            age_ticks=0,
            embedding=embedding,
            created_at=time.time(),
            source_turns=source_turns,
            confirmed=False,
            recall_count=0,
            last_recalled_tick=0,
            rewrite_count=0,
            source=source,
            importance=importance,
        )
        self._l1.append(item)
        self._index_memory_item(item)
        return item

    def _index_memory_item(self, item: MemoryItem) -> None:
        kws = [w for w in _tokenize(item.text) if len(w) >= 2][:24]
        if kws:
            self._inverted_index.add(item.id, kws)

    # ------------------------------------------------------------------
    # 写入时重要性启发式（薄封装，实现已提到模块级 _compute_importance_heuristic，
    # 见文件顶部——避免 MemoryItem.from_dict 反向依赖本类，消除分层倒置）
    # ------------------------------------------------------------------

    # 兼容别名：旧引用 MemorySystem._COMMITMENT_KW 仍可用
    _COMMITMENT_KW = _COMMITMENT_KW

    @staticmethod
    def _has_commitment_kw(text: str) -> bool:
        return _has_commitment_kw(text)

    @staticmethod
    def _compute_importance(
        text: str, source_turns: int, temperature: float
    ) -> float:
        return _compute_importance_heuristic(text, source_turns, temperature)

    def _compute_novelty_bonus(self, text: str) -> float:
        """惊讶度/预测误差（RPE）启发式：内容越新颖（与近期记忆重合越少）→ 越重要。

        修复"重复信息打高分"——_compute_importance 里文本越长分越高，导致反复说
        "今天好累"这类重复内容持续拿高 importance。这里用与最近 L1/L2 条目的关键词
        重叠度做反向加成（新颖→加分，重复→不加）。零 LLM，复用 _keyword_overlap。
        文献依据：dopamine reward-prediction-error（Schultz 1997）——意外的事更该记住。
        """
        sample = (list(self._l1)[-10:] + self._l2[-10:])
        if not sample:
            return 0.2  # 无参照（首条记忆）：视为新颖，给中性偏上加成
        overlaps = [_keyword_overlap(text, m.text) for m in sample]
        avg_overlap = sum(overlaps) / len(overlaps)
        pa = self._params.get("perception_acuity_raw", 0.5)
        # 新颖度 = 1 - 平均重合；感知敏锐者对新颖更敏感（加成幅度更大）。
        return min(0.4, (1.0 - avg_overlap) * 0.4 * (0.5 + pa * 0.5))

    def _overflow_rescue(self) -> None:
        """L1 满时，把最老的已确认项下沉到 L2，未确认的丢弃。"""
        if not self._l1:
            return
        oldest = self._l1[0]
        if oldest.confirmed:
            oldest.age_ticks = 0
            self._l2.append(oldest)
        # deque.append 会自动 pop 左侧，这里不需要手动 popleft

    def write(
        self,
        text: str,
        embedding: list[float] | None = None,
        temperature: float = 0.0,
    ) -> None:
        """v1 兼容接口：直接写入 L1。v2 中仅用于迁移/测试。"""
        self.write_summary(
            text=text, source_turns=1, embedding=embedding, temperature=temperature
        )

    # ------------------------------------------------------------------
    # 12h 整理（v2）
    # ------------------------------------------------------------------

    def consolidation_candidates(self) -> list[MemoryItem]:
        """返回 L1 中可以下沉到 L2 的条目（已确认即可，不受保护期限制）。"""
        return [item for item in self._l1 if item.confirmed]

    def mark_confirmed(self, item_ids: list[str]) -> None:
        """12h 整理确认：标记 L1 条目为已确认。"""
        id_set = set(item_ids)
        for item in self._l1:
            if item.id in id_set:
                item.confirmed = True

    def sink_to_l2(self, item_ids: list[str]) -> None:
        """将已确认的 L1 条目下沉到 L2。"""
        id_set = set(item_ids)
        to_move = [item for item in self._l1 if item.id in id_set]
        for item in to_move:
            item.age_ticks = 0
            self._l2.append(item)
        if len(self._l2) > 500:
            self._l2.sort(key=lambda it: it.weight, reverse=True)
            self._l2 = self._l2[:500]
        self._l1 = deque(
            (item for item in self._l1 if item.id not in id_set),
            maxlen=self._L1_CAPACITY,
        )

    def clear_unconfirmed(
        self, keep_recent_hours: float = CONSOLIDATION_KEEP_RECENT_HOURS
    ) -> int:
        """清除 L1 中未确认的条目。

        规则：
        - 已确认的永远保留（等待下沉）
        - 未确认 + 超过保护期(2h) → 丢弃
        - 如果 L1 满了但全是 2h 内的未确认 → 丢弃最早的腾出空间
        """
        cutoff = time.time() - keep_recent_hours * 3600
        before = len(self._l1)
        # 先按正常规则清除：保留已确认的 + 2h 内的
        kept = deque(
            (item for item in self._l1 if item.confirmed or item.created_at >= cutoff),
            maxlen=self._L1_CAPACITY,
        )
        # 如果清除后仍然满了，丢弃最早的未确认条目
        if len(kept) >= self._L1_CAPACITY:
            unconfirmed = [
                (i, item) for i, item in enumerate(kept) if not item.confirmed
            ]
            if unconfirmed:
                # 按时间排序，丢弃最早的
                unconfirmed.sort(key=lambda x: x[1].created_at)
                drop_count = len(kept) - self._L1_CAPACITY + 5  # 腾出 5 个位置
                drop_ids = {
                    unconfirmed[i][1].id
                    for i in range(min(drop_count, len(unconfirmed)))
                }
                kept = deque(
                    (item for item in kept if item.id not in drop_ids),
                    maxlen=self._L1_CAPACITY,
                )
        self._l1 = kept
        return before - len(self._l1)

    def needs_consolidation(self) -> bool:
        """检查是否需要执行整理。触发条件：每天 6:00/18:00 或 L1 满 60 条。"""
        # 保底：L1 满了就触发
        if len(self._l1) >= self._L1_CAPACITY:
            return True
        # 定时：每天 6:00 和 18:00（基于系统时区）
        from datetime import datetime

        now = datetime.now()
        # 计算上次整理后是否跨过了 6:00 或 18:00
        if self._last_consolidation_ts == 0.0:
            return len(self._l1) > 0
        last = datetime.fromtimestamp(self._last_consolidation_ts)
        # 检查从 last 到 now 之间是否经过了 6:00 或 18:00
        for target_hour in (6, 18):
            target = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
            if last < target <= now:
                return True
        # 跨天的情况
        if last.date() < now.date():
            return True
        return False

    def mark_consolidation_done(self) -> None:
        self._last_consolidation_ts = time.time()

    # ------------------------------------------------------------------
    # Tick 衰减
    # ------------------------------------------------------------------

    def tick_decay(self) -> None:
        """推进衰减时钟一步。每条消息调用一次。

        性能优化（P1）：
        - L2 衰减：每 tick 执行（轻量，仅数值运算）
        - L3 clarity 衰减：每 _DECAY_L3_EVERY_N tick 执行
        - GC（剪枝/列表重建）：每 _GC_EVERY_N tick 或 L2 超阈值时执行
        """
        self._tick += 1
        self._gc_tick_counter += 1
        base_decay = self._params["base_decay"]
        age_coeff = self._params["age_coeff"]
        neuroticism = self._params["neuroticism"]
        cold_decay_factor = self._params["cold_memory_decay_factor"]

        # --- L2 衰减（每 tick，轻量） ---
        for item in self._l2:
            decay_rate = base_decay * (1 + age_coeff * math.log(item.age_ticks + 1))
            item.age_ticks += 1
            if item.temperature < 0.3 and neuroticism > 0.6:
                decay_rate *= cold_decay_factor
            item.weight *= 1 - decay_rate
            if item.weight < 1e-10:
                item.weight = 0.0

        # --- L3 clarity 衰减（每 N tick，用单调递增的 _tick 判断） ---
        if self._tick % self._DECAY_L3_EVERY_N == 0:
            # 批量衰减：0.998^N 等效于连续 N 次 *0.998
            l3_decay = 0.998 ** self._DECAY_L3_EVERY_N
            now = date.today()
            for node in self._l3_nodes.values():
                if node.temporal_type == "permanent":
                    continue
                elif node.temporal_type == "evolving" and node.valid_from:
                    try:
                        valid_from_date = date.fromisoformat(node.valid_from)
                        days_since = (now - valid_from_date).days
                    except (ValueError, TypeError):
                        days_since = 0
                    if days_since > node.staleness_threshold:
                        staleness = 1 + 0.5 * math.log(
                            (days_since - node.staleness_threshold) / 30 + 1
                        )
                        node.clarity *= l3_decay / staleness
                    else:
                        node.clarity *= l3_decay
                else:
                    node.clarity *= l3_decay

            for edge in self._l3_edges:
                edge.clarity *= l3_decay

        # --- GC（每 N tick 或 L2 超阈值） ---
        need_gc = (
            self._gc_tick_counter >= self._GC_EVERY_N
            or len(self._l2) > self._GC_L2_SIZE_THRESHOLD
        )
        if need_gc:
            self._gc_tick_counter = 0
            self._gc_l2()
            self._gc_l3()

    def _gc_l2(self) -> None:
        """就地过滤 L2 中 weight=0 的死条目。"""
        if not self._l2:
            return
        # 就地过滤：仅在有死条目时重建
        dead_count = sum(1 for item in self._l2 if item.weight <= 0.0)
        if dead_count > 0:
            self._l2[:] = [item for item in self._l2 if item.weight > 0.0]

    def _gc_l3(self) -> None:
        """回收 L3 中 clarity 低于阈值的节点和边，强制节点数上限。"""
        gc_threshold = 0.1
        dead_nodes = [
            nid for nid, node in self._l3_nodes.items() if node.clarity < gc_threshold
        ]
        for nid in dead_nodes:
            del self._l3_nodes[nid]

        if len(self._l3_nodes) > self._L3_NODE_LIMIT:
            removable = [
                (nid, node)
                for nid, node in self._l3_nodes.items()
                if node.temporal_type != "permanent"
            ]
            removable.sort(key=lambda x: x[1].clarity)
            excess = len(self._l3_nodes) - self._L3_NODE_LIMIT
            for nid, _node in removable[:excess]:
                dead_nodes.append(nid)
                del self._l3_nodes[nid]

        dead_node_set = set(dead_nodes)
        self._l3_edges = [
            e
            for e in self._l3_edges
            if e.clarity >= gc_threshold
            and e.source not in dead_node_set
            and e.target not in dead_node_set
        ]

        # 清理 label/edge 索引中的 stale entries
        if dead_node_set:
            if hasattr(self, "_l3_label_index"):
                self._l3_label_index = {
                    label: nid for label, nid in self._l3_label_index.items()
                    if nid not in dead_node_set
                }
            if hasattr(self, "_l3_edge_index"):
                self._l3_edge_index = {
                    key: idx for key, idx in self._l3_edge_index.items()
                    if idx < len(self._l3_edges)
                }

    # ------------------------------------------------------------------
    # 拟人化召回：四维归一化打分 helper（全部 clamp 到 [0,1]）
    #
    # 注：原 _ebbinghaus_retention（Item 95，R=e^(-t/S)）已删除——其"复习/情感
    # 提升稳定性、衰减变慢"的思想已被 _recency_score 的 τ 吸收（τ 随 recall_count/
    # importance 增大）。两者并存会对近期记忆双重衰减，故不再保留。
    # ------------------------------------------------------------------

    @staticmethod
    def _recency_score(
        created_at: float,
        last_recalled_ts: float,
        recall_count: int,
        importance: float,
        now: float,
    ) -> float:
        """近期性评分。被召回会刷新 last_recalled_ts 使其复活。

        τ（时间常数）吸收原 Ebbinghaus 的稳定性思想：召回越多/越重要 → 衰减越慢。
        因此 recall 中不再单独乘 Ebbinghaus retention，避免对近期记忆双重衰减。
        """
        eff_ts = max(created_at, last_recalled_ts)
        if eff_ts <= 0:
            return 0.5  # 无时间信息（如部分 L3 节点）给中性值
        dt_h = max(0.0, (now - eff_ts) / 3600.0)
        # recall_count 封顶（防止高频老记忆 τ 无限膨胀、永久霸占召回槽 —— rich-get-richer）。
        rc = min(max(0, recall_count), MemorySystem._RECENCY_RECALL_CAP)
        # τ 只随 recall_count（频次）放大，不再乘 (1+importance)：
        # importance 已作为独立维度进入 _composite(w_imp*imp)，再让它膨胀 τ 是双重计入，
        # 会让高 importance 记忆在 recency 维也被不公平抬高。改为对高 importance 记忆
        # 施加一个小幅 recency 加成（nudge），保留"重要的东西更不易被时间冲淡"的直觉，
        # 但量级远小于旧式乘子，避免主导排序。
        tau = 200.0 * (1 + 0.5 * rc)
        base_recency = math.exp(-dt_h / tau)  # ∈(0,1]
        importance_nudge = 0.05 * max(0.0, importance - 0.5)
        return min(1.0, base_recency + importance_nudge)

    def _emotional_match_score(
        self, temperature: float, warmth: float
    ) -> float:
        """情绪一致性评分（mood-congruent）。两者均 clamp 到 [-1,1]。"""
        t = max(-1.0, min(1.0, temperature))
        w = max(-1.0, min(1.0, warmth))
        base = 1.0 - abs(t - w) / 2.0  # ∈[0,1]
        if t > 0:  # 宜人性正向偏好：正向记忆按 bias 乘法放大
            # 旧式 base += (bias-1)*0.1 在 bias∈[1.0,1.3] 下最大仅 +0.03，
            # 再经 w_emo(~0.15) 稀释后对 composite 影响 <0.005，人格参数形同虚设。
            # 改乘法：bias=1.3、base=0.7 → 0.91，正向偏好真正进入排序。
            base *= self._params["positive_recall_bias"]
        return max(0.0, min(1.0, base))

    def _composite(
        self, rel: float, rec: float, imp: float, emo: float
    ) -> float:
        """四维加权合成分（权重为人格函数，和=1）。"""
        p = self._params
        return (
            p["w_rel"] * rel
            + p["w_rec"] * rec
            + p["w_imp"] * imp
            + p["w_emo"] * emo
        )

    # ------------------------------------------------------------------
    # 召回（v2：三层并行 + reconsolidation 钩子）
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_recall_mode(explicit: Any) -> "RecallMode":
        """决定召回模式：显式参数 > 环境变量 SYLANNE_RECALL_MODE > 默认 LEGACY。

        非法值静默回退 LEGACY，绝不让一个配置错误阻断召回。
        """
        import os

        if isinstance(explicit, RecallMode):
            return explicit
        raw = explicit if isinstance(explicit, str) else os.environ.get(
            "SYLANNE_RECALL_MODE", ""
        )
        try:
            return RecallMode(str(raw).strip().lower())
        except ValueError:
            return RecallMode.LEGACY

    def recall(
        self,
        query: str,
        query_embedding: list[float] | None = None,
        current_warmth: float = 0.0,
        limit: int = 5,
    ) -> list[MemoryResult]:
        """召回入口分发器（阶段0 灰度）。

        - LEGACY：现有两阶段四维加权召回（默认，行为零变化）。
        - ACTIVATION：ACT-R 激活核召回（阶段1+ 实现，未实现前回退 LEGACY）。
        - SHADOW：返回 LEGACY 结果，同时后台跑 ACTIVATION 记录差异（不影响返回值）。
        """
        mode = self._recall_mode
        if mode is RecallMode.LEGACY:
            return self._recall_legacy(query, query_embedding, current_warmth, limit)
        if mode is RecallMode.ACTIVATION:
            activation_fn = getattr(self, "_recall_activation", None)
            if activation_fn is None:
                # 阶段1 未落地：安全回退，不让开关把召回打瘫。
                return self._recall_legacy(
                    query, query_embedding, current_warmth, limit
                )
            return activation_fn(query, query_embedding, current_warmth, limit)
        # SHADOW：以 LEGACY 为准返回，新引擎仅观测
        legacy = self._recall_legacy(query, query_embedding, current_warmth, limit)
        activation_fn = getattr(self, "_recall_activation", None)
        if activation_fn is not None:
            try:
                # observe_only：影子评估不能污染记忆状态（不刷新 actr_acc/不 reinforce），
                # 否则 LEGACY 返回的同时新引擎偷偷"练习"了 actr_acc，影子就不是纯观测。
                new = activation_fn(
                    query, query_embedding, current_warmth, limit, observe_only=True
                )
                self._record_shadow_diff(query, legacy, new)
            except Exception as e:  # 影子计算绝不能影响线上返回
                import logging

                logging.getLogger("astrbot_plugin_sylanne").warning(
                    "Sylanne recall shadow 计算失败（不影响返回）：%s", e
                )
        return legacy

    # 影子历史滚动缓冲上限（评估足够、内存可控）
    _SHADOW_HISTORY_MAX = 50

    def _record_shadow_diff(
        self,
        query: str,
        legacy: list["MemoryResult"],
        new: list["MemoryResult"],
    ) -> None:
        """记录 LEGACY vs ACTIVATION 召回的 top 集合差异，供影子模式离线评估。

        差异同时：①存最近一条 _last_shadow_diff；②追加进滚动历史 _shadow_history
        （供 get_debug_snapshot / WebUI 拉取批量评估）；③打 info 日志（运维可 grep 收集）。
        """
        legacy_texts = [r.text for r in legacy]
        new_texts = [r.text for r in new]
        ls, ns = set(legacy_texts), set(new_texts)
        union = ls | ns
        overlap = (len(ls & ns) / len(union)) if union else 1.0
        diff = {
            "query": query[:100],
            "legacy_top": legacy_texts[:5],
            "activation_top": new_texts[:5],
            "overlap": round(overlap, 3),
            "only_legacy": list(ls - ns)[:5],
            "only_activation": list(ns - ls)[:5],
            "ts": time.time(),
        }
        self._last_shadow_diff = diff
        hist = getattr(self, "_shadow_history", None)
        if hist is None:
            hist = self._shadow_history = []
        hist.append(diff)
        if len(hist) > self._SHADOW_HISTORY_MAX:
            del hist[: len(hist) - self._SHADOW_HISTORY_MAX]
        import logging
        logging.getLogger("astrbot_plugin_sylanne").info(
            "Sylanne recall shadow diff: overlap=%.3f only_legacy=%d only_act=%d q=%r",
            overlap, len(ls - ns), len(ns - ls), query[:40],
        )

    # ------------------------------------------------------------------
    # 阶段1 宽召回（LEGACY 与 ACTIVATION 共享，差异只在阶段2 rerank）
    # ------------------------------------------------------------------

    def _gather_pool(
        self,
        query: str,
        query_embedding: list[float] | None,
        now: float,
    ) -> list[dict]:
        """遍历 L1/L2/L3 产出候选池（只算 relevance）。

        候选记录：{rel, reason, obj, layer, text, temperature, importance,
                   created_at, last_recalled_ts, recall_count, clarity}。
        近期记忆（5min 内）relevance=0 也给兜底分强制入池（recency 通道）。
        """
        query_tokens = _tokenize(query)
        pool: list[dict] = []
        index_ids: set[str] = set()
        if query.strip():
            index_ids = set(
                self._inverted_index.query(list(query_tokens)[:15], top_k=15)
            )
        in_pool: set[str] = set()

        for item in self._l1:
            relevance, reason = self._compute_relevance_with_reason(
                query, query_embedding, item.text, item.embedding, query_tokens
            )
            is_recent = now - item.created_at < 300
            if relevance <= 0.0:
                if not is_recent:
                    continue
                relevance = self._RECENT_FLOOR_RELEVANCE
                reason = "temporal_proximity"
            elif is_recent and relevance < 0.2:
                reason = "temporal_proximity"
            pool.append({
                "rel": relevance, "reason": reason, "obj": item, "layer": "L1",
                "text": item.text, "temperature": item.temperature,
                "importance": item.importance, "created_at": item.created_at,
                "last_recalled_ts": item.last_recalled_ts,
                "recall_count": item.recall_count, "clarity": 1.0,
            })
            in_pool.add(item.id)

        for item in self._l2:
            relevance, reason = self._compute_relevance_with_reason(
                query, query_embedding, item.text, item.embedding, query_tokens
            )
            if relevance <= 0.0 and item.id in index_ids:
                relevance = 0.12
                reason = "inverted_index"
            if relevance <= 0.0:
                continue
            pool.append({
                "rel": relevance, "reason": reason, "obj": item, "layer": "L2",
                "text": item.text, "temperature": item.temperature,
                "importance": item.importance, "created_at": item.created_at,
                "last_recalled_ts": item.last_recalled_ts,
                "recall_count": item.recall_count, "clarity": 1.0,
            })
            in_pool.add(item.id)

        for item in self._l2:
            if item.id in index_ids and item.id not in in_pool:
                pool.append({
                    "rel": 0.12, "reason": "inverted_index", "obj": item, "layer": "L2",
                    "text": item.text, "temperature": item.temperature,
                    "importance": item.importance, "created_at": item.created_at,
                    "last_recalled_ts": item.last_recalled_ts,
                    "recall_count": item.recall_count, "clarity": 1.0,
                })

        # L3 候选（节点匹配，带 relevance；importance 用 clarity 近似）
        pool.extend(self._recall_l3_candidates(query))
        return pool

    def _select_wide(self, pool: list[dict]) -> list[dict]:
        """按 relevance 排序取 top-WIDE_K，高重要性条目旁路保底（防被截断）。"""
        pool.sort(key=lambda c: c["rel"], reverse=True)
        wide = pool[: self._RECALL_WIDE_K]
        if len(pool) > self._RECALL_WIDE_K:
            in_wide = {id(c["obj"]) for c in wide}
            bypass = [
                c for c in pool[self._RECALL_WIDE_K:]
                if c["importance"] >= self._RECALL_IMPORTANCE_BYPASS_FLOOR
                and id(c["obj"]) not in in_wide
            ]
            bypass.sort(key=lambda c: c["importance"], reverse=True)
            wide = wide + bypass[: self._RECALL_IMPORTANCE_BYPASS]
        return wide

    def _apply_emotion_bypass(
        self, pool: list[dict], wide: list[dict], current_warmth: float
    ) -> list[dict]:
        """情感特权旁路（阶段3）：把强情绪 + 较高重要性的记忆补回候选。

        实现"情感强烈的记忆即使语义不相关也会浮现"——情感陪伴的核心。
        仅在当前心境本身带情绪（|current_warmth| 偏离中性）时触发：中性闲聊时不该
        被无关旧情绪记忆打断；用户情绪起伏时，与之"同频/呼应"的强情绪记忆才浮现
        （mood-congruent retrieval）。补回项仍需过 _classify_confidence，激活太低
        会落到 tot（模糊浮现）或被丢弃，不会硬塞确信内容。
        """
        if abs(current_warmth) < 0.3:
            return wide  # 心境中性：不触发情感旁路
        emo_floor = self._params.get("emo_bypass_floor", 0.55)
        imp_floor = self._params.get("emo_bypass_imp_floor", 0.55)
        in_wide = {id(c["obj"]) for c in wide}
        # 直接扫 L1/L2（不依赖 pool——pool 已按 relevance 过滤掉 rel=0 的项，
        # 而情感旁路的全部意义就是召回语义不相关但情感强烈的记忆）。
        extra: list[dict] = []
        for layer, store in (("L1", self._l1), ("L2", self._l2)):
            for item in store:
                if id(item) in in_wide:
                    continue
                # 情绪需与当前心境同向（都正或都负），避免开心时翻出难过事
                if abs(item.temperature) < emo_floor or item.importance < imp_floor:
                    continue
                if (item.temperature >= 0) != (current_warmth >= 0):
                    continue
                extra.append({
                    "rel": 0.0, "reason": "emotion_bypass", "obj": item,
                    "layer": layer, "text": item.text,
                    "temperature": item.temperature, "importance": item.importance,
                    "created_at": item.created_at,
                    "last_recalled_ts": item.last_recalled_ts,
                    "recall_count": item.recall_count, "clarity": 1.0,
                })
        extra.sort(
            key=lambda c: abs(c["temperature"]) * c["importance"], reverse=True
        )
        return wide + extra[:2]

    def _recall_legacy(
        self,
        query: str,
        query_embedding: list[float] | None = None,
        current_warmth: float = 0.0,
        limit: int = 5,
    ) -> list[MemoryResult]:
        """拟人化两阶段召回（LEGACY，原 recall() 实现，逐行未改）。

        阶段1（宽召回）：遍历 L1/L2/L3，只算 relevance 粗筛，rel>0 入池，
                         按 relevance 排序取 top-WIDE_K，并对高重要性条目设旁路保底。
        阶段2（rerank）：对候选算四维 composite（rel/recency/importance/emotional），
                         comp<gate 丢弃（人格化硬门控，空召回优于错召回），
                         final = layer_weight × composite，排序取 top-limit。
        命中后刷新 last_recalled_ts（使 recency 复活）+ importance 微增 + L2 reinforce。
        """
        now = time.time()

        # ---- 阶段1：宽召回（LEGACY/ACTIVATION 共享，只算 relevance）----
        pool = self._gather_pool(query, query_embedding, now)
        wide = self._select_wide(pool)

        # ---- 阶段2：rerank，算完整四维 composite ----
        gate = self._params["recall_gate_base"]
        results: list[MemoryResult] = []
        for c in wide:
            rel = c["rel"]
            rec = self._recency_score(
                c["created_at"], c["last_recalled_ts"],
                c["recall_count"], c["importance"], now,
            )
            imp = c["importance"]
            emo = self._emotional_match_score(c["temperature"], current_warmth)
            comp = self._composite(rel, rec, imp, emo)
            if comp < gate:
                continue  # 空召回优于错召回
            final = self._LAYER_WEIGHTS[c["layer"]] * comp
            results.append(MemoryResult(
                text=c["text"],
                layer=c["layer"],
                weight=getattr(c["obj"], "weight", c["clarity"]),
                relevance=rel,
                clarity=c["clarity"],
                temperature=c["temperature"],
                final_score=final,
                created_at=c["created_at"],
                recall_count=c["recall_count"],
                emotional_weight=max(0.0, min(1.0, abs(c["temperature"]))),
                recall_reason=c["reason"],
                source=getattr(c["obj"], "source", "dialogue"),
                importance=imp,
                source_obj=c["obj"],
            ))

        results.sort(key=lambda r: r.final_score, reverse=True)
        top = results[:limit]

        # 命中刷新 → recency 复活 + frequency + L2 reinforce
        self._recalled_l2_items: list[MemoryItem] = []
        for r in top:
            self._refresh_recall(r.source_obj, now, current_warmth, r.layer)
        return top

    # ------------------------------------------------------------------
    # 阶段1：ACT-R 激活核（base-level learning + EMA 近似）
    # ------------------------------------------------------------------

    # base-level 归一化区间：A=B+imp_scale*imp。B=ln(decayed)，decayed≈acc*dt^-d。
    # 单次编码、间隔 1h 时 B≈0；长期不召回 B 趋向负；高频近召回 B>0。经验区间 [-4, B_max]。
    _ACTR_B_MIN = -4.0
    # Δt 下限（小时）：ACT-R 中 t⁻ᵈ 在 t<1 时会 >1 反向爆炸（刚创建即召回时 Δt→0
    # 会让激活炸到上千）。标准做法是给时间间隔一个最小单位。取 0.25h（15min）：
    # 同一会话内的连续召回不会被算成"无限近"而虚高，跨会话间隔则正常衰减。
    _ACTR_MIN_DT_H = 0.25

    # 阶段2 spreading activation：扩散硬上限（防爆炸/超预算）与激活地板（剪枝）。
    _SPREAD_MAX_NODES = 30        # 单次召回扩散触达的新节点总数上限
    _SPREAD_ACTIVATION_FLOOR = 0.08  # 扩散增量低于此值则剪枝，不再传导
    _SPREAD_REL_CAP = 0.6         # 扩散节点作为候选的 relevance 上限（弱于直接命中）

    def _update_actr_acc(self, obj: Any, now: float) -> None:
        """ACT-R base-level learning 的 EMA 近似递推（命中时调用）。

        精确式 B=ln(Σ tⱼ⁻ᵈ) 需存全部召回时间戳；这里用单标量累加器近似：
            acc ← acc * (Δt_h)⁻ᵈ + 1
        Δt_h 为距上次召回（或创建）的小时数，下限 _ACTR_MIN_DT_H 防 t⁻ᵈ 爆炸。
        等价于"把已有激活按幂律衰减到当下，再叠加本次召回的 +1"。
        Petrov(2006) 证明该近似与完整序列误差 < 0.05 nats。
        """
        d = self._params.get("actr_d", 0.5)
        lrt = obj.last_recalled_ts if getattr(obj, "last_recalled_ts", 0.0) > 0 \
            else obj.created_at
        dt_h = max((now - lrt) / 3600.0, self._ACTR_MIN_DT_H)
        decayed = obj.actr_acc * (dt_h ** -d)
        obj.actr_acc = min(decayed + 1.0, 1e6)  # 防溢出上限

    def _activation_score(
        self,
        actr_acc: float,
        last_recalled_ts: float,
        created_at: float,
        importance: float,
        temperature: float,
        current_warmth: float,
        now: float,
    ) -> tuple[float, bool]:
        """ACT-R 激活：A = ln(acc·Δt⁻ᵈ) + imp_scale·importance；返回 (归一激活, 是否过门控)。

        - base-level B = ln(decayed) 统一编码频次+近因（acc 越大、Δt 越小 → B 越高）。
        - importance 作先验偏置加到 A（**唯一**计入点，不再有独立维度，杜绝双重计入）。
        - emotional（mood-congruent）不进 A，而是降低检索阈值（情绪契合→更易被想起），
          对应 ACT-R 的 retrieval threshold 调节，也实现"情感记忆特权"。
        """
        d = self._params.get("actr_d", 0.5)
        imp_scale = self._params.get("actr_importance_scale", 1.25)
        emo_scale = self._params.get("actr_emo_scale", 0.35)
        base_threshold = self._params.get("actr_base_threshold", -1.1)

        eff_ts = max(last_recalled_ts, created_at)
        if eff_ts <= 0:
            dt_h = 1.0  # 无时间信息（部分 L3 节点）给中性 1h
        else:
            dt_h = max((now - eff_ts) / 3600.0, self._ACTR_MIN_DT_H)
        decayed = max(actr_acc * (dt_h ** -d), 1e-10)
        B = math.log(decayed)
        A = B + imp_scale * max(0.0, min(1.0, importance))

        b_max = 1.5 + imp_scale
        act_norm = max(0.0, min(1.0, (A - self._ACTR_B_MIN) / (b_max - self._ACTR_B_MIN)))

        t = max(-1.0, min(1.0, temperature))
        w = max(-1.0, min(1.0, current_warmth))
        emo_match = 1.0 - abs(t - w) / 2.0          # ∈[0,1]
        effective_threshold = base_threshold - emo_scale * emo_match  # 情绪契合→阈值下降
        passes = A >= effective_threshold
        return act_norm, passes

    # ------------------------------------------------------------------
    # 阶段3：软召回三级置信 + 情感特权 + 舌尖现象
    # ------------------------------------------------------------------

    def _compute_final_activation(
        self,
        act_norm: float,
        emotional_weight: float,
        current_warmth: float,
        temperature: float,
    ) -> float:
        """在归一激活上叠加情感特权加成：强情绪且与当前心境契合的记忆被抬高。

        实现"她对情感强烈的事记得更牢"——情感陪伴的核心价值。仅对 emo_w>0.6 生效。
        """
        k = self._params.get("emotion_privilege_k", 0.20)
        bonus = 0.0
        if emotional_weight > 0.6:
            congruence = 1.0 - abs(
                max(-1.0, min(1.0, temperature)) - max(-1.0, min(1.0, current_warmth))
            ) / 2.0
            bonus = k * emotional_weight * congruence
        return min(1.0, act_norm + bonus)

    def _classify_confidence(
        self, activation: float, importance: float, emotional_weight: float
    ) -> str | None:
        """三级置信分级（替代硬门控）。返回 clear/vague/tot 或 None（彻底想不起）。

        - activation ≥ theta_clear → "clear"：确信记得。
        - activation ≥ theta_tot   → "vague"：依稀记得（注入时模糊措辞）。
        - 否则若 importance/emotion 够高 → "tot"：舌尖现象（知道有这么回事但记不清）。
          这比干净遗忘更拟人、更暖——"她记得我"胜过"她忘了"。
        - 都不满足 → None：丢弃（空召回优于错召回）。
        """
        if activation >= self._params.get("theta_clear", 0.55):
            return "clear"
        if activation >= self._params.get("theta_tot", 0.15):
            return "vague"
        if importance >= 0.7 or emotional_weight >= 0.6:
            return "tot"
        return None

    def _layer_confidence(self, layer: str) -> float:
        """ACTIVATION 模式的层置信因子（取代 _LAYER_WEIGHTS 硬乘）。

        L1 未确认近期摘要 → 折扣（人格化，尽责性高更挑剔）；
        L2 已确认、L3 已有 clarity 衰减 → 不折扣（避免与 activation 重复惩罚）。
        """
        if layer == "L1":
            return self._params.get("l1_confidence", 0.85)
        return 1.0

    # ------------------------------------------------------------------
    # 阶段2：L3 spreading activation（让图谱的边参与召回——联想扩散）
    # ------------------------------------------------------------------

    @staticmethod
    def _edge_weight(edge: "GraphEdge", current_warmth: float) -> float:
        """边的传导权重：clarity × strength × 情绪契合调节，clamp [0,1]。

        情绪与当前心境契合的关系传导更强（mood-congruent 联想），系数 ∈[0.7,1.3]。
        """
        emo_align = 1.0 - abs(edge.emotion_weight - current_warmth) / 2.0  # ∈[0,1]
        emotion_modifier = 0.7 + 0.6 * emo_align                           # ∈[0.7,1.3]
        return max(0.0, min(1.0, edge.clarity * edge.strength * emotion_modifier))

    def _build_adjacency(self) -> dict[str, list[tuple[str, "GraphEdge"]]]:
        """按需构建邻接表（node_id → [(邻居 id, edge), ...]）。

        刻意每次召回重建（边数上限 2000，O(E) dict 操作 < 0.5ms），而非维护持久
        _l3_adj 索引——后者需在 加边/GC/反序列化 三处同步，是高发不一致 bug 源
        （见重构评审 facet E）。无状态重建以极小成本换正确性。
        """
        adj: dict[str, list[tuple[str, GraphEdge]]] = {}
        for edge in self._l3_edges:
            if edge.source in self._l3_nodes and edge.target in self._l3_nodes:
                adj.setdefault(edge.source, []).append((edge.target, edge))
                adj.setdefault(edge.target, []).append((edge.source, edge))
        return adj

    def _spread_activation(
        self, seed_activations: dict[str, float], current_warmth: float
    ) -> dict[str, float]:
        """从种子节点沿边扩散激活（最多 2 跳，fan effect 抑制 + 硬上限剪枝）。

        返回 {node_id: spread_activation}（仅含扩散新增节点，不含种子）。
        - fan effect（Anderson）：连接数多的节点向每个邻居传导被 1/√fan 稀释，
          避免"枢纽节点"把激活无差别灌给所有邻居。
        - boundary 节点不接收扩散（用户边界/禁忌不该被无关联想拽出）。
        - 低于 floor 的增量剪枝；触达节点数达上限即停（防爆炸 + 守 <5ms 预算）。
        """
        if not seed_activations or not self._l3_edges:
            return {}
        bp = self._params.get("boundary_permeability", 0.5)
        hop1_decay = 0.3 + bp * 0.5  # 开放性越高→联想扩散越远 ∈[0.3,0.8]
        floor = self._SPREAD_ACTIVATION_FLOOR
        adj = self._build_adjacency()

        spread: dict[str, float] = {}
        count = 0

        def _emit(src_id: str, src_act: float, decay: float) -> bool:
            """从 src 向邻居传导一跳。返回是否已达上限。"""
            nonlocal count
            neighbors = adj.get(src_id, [])
            if not neighbors:
                return False
            fan_penalty = 1.0 / math.sqrt(len(neighbors))
            for nbr_id, edge in neighbors:
                if nbr_id in seed_activations:
                    continue  # 种子节点已直接命中，不重复
                nbr = self._l3_nodes.get(nbr_id)
                if nbr is None or nbr.type == "boundary":
                    continue
                delta = src_act * self._edge_weight(edge, current_warmth) \
                    * fan_penalty * decay
                if delta < floor:
                    continue
                if nbr_id not in spread:
                    count += 1
                spread[nbr_id] = max(spread.get(nbr_id, 0.0), delta)
                if count >= self._SPREAD_MAX_NODES:
                    return True
            return False

        # 第一跳：从种子出发
        for sid, sact in seed_activations.items():
            if sact < floor:
                continue
            if _emit(sid, sact, hop1_decay):
                return spread

        # 第二跳：仅从第一跳新增节点出发，衰减平方
        hop2_decay = hop1_decay ** 2
        for sid, sact in list(spread.items()):
            if sact < floor:
                continue
            if _emit(sid, sact, hop2_decay):
                return spread

        return spread

    def _spreading_candidates(
        self, pool: list[dict], current_warmth: float, now: float
    ) -> list[dict]:
        """基于已匹配的 L3 候选做 spreading，产出扩散节点的额外候选。

        种子激活 = 直接命中的 L3 节点的 relevance；扩散到的邻居节点封装为新候选，
        relevance = 扩散激活值（上限 _SPREAD_REL_CAP），reason=spreading_activation。
        """
        seeds: dict[str, float] = {}
        for c in pool:
            if c["layer"] == "L3" and hasattr(c["obj"], "id"):
                nid = c["obj"].id
                seeds[nid] = max(seeds.get(nid, 0.0), c["rel"])
        if not seeds:
            return []

        spread = self._spread_activation(seeds, current_warmth)
        in_pool = {c["obj"].id for c in pool
                   if c["layer"] == "L3" and hasattr(c["obj"], "id")}
        extra: list[dict] = []
        for nid, act in spread.items():
            if nid in in_pool:
                continue
            node = self._l3_nodes.get(nid)
            if node is None or node.clarity < 0.1:
                continue
            extra.append({
                "rel": min(self._SPREAD_REL_CAP, act),
                "reason": "spreading_activation",
                "obj": node,
                "layer": "L3",
                "text": node.label,
                "temperature": node.emotion_weight,
                "importance": node.clarity,
                "created_at": getattr(node, "created_at", 0.0),
                "last_recalled_ts": getattr(node, "last_recalled_ts", 0.0),
                "recall_count": node.recall_count,
                "clarity": node.clarity,
            })
        return extra

    def _recall_activation(
        self,
        query: str,
        query_embedding: list[float] | None = None,
        current_warmth: float = 0.0,
        limit: int = 5,
        observe_only: bool = False,
    ) -> list[MemoryResult]:
        """ACT-R 激活核召回（ACTIVATION 模式）。

        observe_only=True（SHADOW 影子评估）时不施加任何命中副作用——不刷新
        actr_acc/last_recalled_ts、不 reinforce L2，保证影子是纯只读观测。

        阶段1（宽召回）：与 LEGACY 共享 _gather_pool；额外做 L3 spreading activation，
                         把联想到的邻居节点也纳入候选池。
        阶段2（rerank）：composite = w_rel_act·rel + w_act·activation。
        阶段3（软召回）：不再硬丢弃低分项，而按激活分三级置信（clear/vague/tot）；
                         强情绪记忆走特权旁路 + 激活加成；舌尖项保留为模糊浮现。
        命中按 base-level 更新 acc。
        """
        now = time.time()
        pool = self._gather_pool(query, query_embedding, now)
        # 阶段2 L3 扩散激活：让图谱的边参与召回（联想浮现）。
        pool.extend(self._spreading_candidates(pool, current_warmth, now))
        wide = self._select_wide(pool)
        # 阶段3 情感特权旁路：强情绪 + 较高重要性的记忆即使 relevance 低被 WIDE_K
        # 截断，也补回候选——情感陪伴里"她记得那次你难过"比语义相关更重要。
        wide = self._apply_emotion_bypass(pool, wide, current_warmth)

        w_rel = self._params.get("w_rel_act", 0.55)
        w_act = self._params.get("w_act", 0.45)
        results: list[MemoryResult] = []
        for c in wide:
            rel = c["rel"]
            act_norm, _ = self._activation_score(
                getattr(c["obj"], "actr_acc", 1.0),
                c["last_recalled_ts"], c["created_at"],
                c["importance"], c["temperature"], current_warmth, now,
            )
            emo_w = max(0.0, min(1.0, abs(c["temperature"])))
            # 情感特权加成后再分级（强情绪记忆更容易够到 clear/vague）
            final_act = self._compute_final_activation(
                act_norm, emo_w, current_warmth, c["temperature"]
            )
            confidence = self._classify_confidence(final_act, c["importance"], emo_w)
            if confidence is None:
                continue  # 彻底想不起（连舌尖都够不到）
            comp = w_rel * rel + w_act * final_act
            # ACTIVATION 用 _layer_confidence 取代 _LAYER_WEIGHTS 硬乘：
            # recency/frequency/importance 已被 activation 编码，再按 L1=1/L2=.7/L3=.4
            # 硬乘是重复惩罚。仅对 L1（未确认）保留置信折扣。
            final = self._layer_confidence(c["layer"]) * comp
            results.append(MemoryResult(
                text=c["text"],
                layer=c["layer"],
                weight=getattr(c["obj"], "weight", c["clarity"]),
                relevance=rel,
                clarity=c["clarity"],
                temperature=c["temperature"],
                final_score=final,
                created_at=c["created_at"],
                recall_count=c["recall_count"],
                emotional_weight=emo_w,
                recall_reason=c["reason"],
                source=getattr(c["obj"], "source", "dialogue"),
                importance=c["importance"],
                activation=final_act,
                confidence=confidence,
                source_obj=c["obj"],
                debug={"rel": round(rel, 3), "act": round(act_norm, 3),
                       "final_act": round(final_act, 3), "conf": confidence,
                       "comp": round(comp, 3)},
            ))

        results.sort(key=lambda r: r.final_score, reverse=True)
        top = results[:limit]

        if observe_only:
            return top  # 影子评估：纯只读，不施加命中副作用
        self._recalled_l2_items: list[MemoryItem] = []
        for r in top:
            self._refresh_recall(
                r.source_obj, now, current_warmth, r.layer, update_actr=True
            )
        return top

    # ------------------------------------------------------------------
    # 可观测（阶段0：零副作用快照，供 WebUI/影子模式调试）
    # ------------------------------------------------------------------

    def get_debug_snapshot(self) -> dict:
        """返回召回引擎当前状态快照（只读，无副作用）。

        供 WebUI dashboard 轮询 / 影子模式离线评估使用。不触发任何召回或衰减。
        """
        hist = getattr(self, "_shadow_history", []) or []
        shadow_stats = None
        if hist:
            overlaps = [d["overlap"] for d in hist]
            shadow_stats = {
                "samples": len(hist),
                "avg_overlap": round(sum(overlaps) / len(overlaps), 3),
                "min_overlap": round(min(overlaps), 3),
            }
        return {
            "recall_mode": self._recall_mode.value,
            "l1_size": len(self._l1),
            "l2_size": len(self._l2),
            "l3_nodes": len(self._l3_nodes),
            "l3_edges": len(self._l3_edges),
            "tick": self._tick,
            "params": dict(self._params),
            "last_shadow_diff": self._last_shadow_diff,
            "shadow_stats": shadow_stats,
            "shadow_history": hist[-10:],  # 最近 10 条，避免快照过大
        }

    def _refresh_recall(
        self, obj: Any, now: float, current_warmth: float, layer: str,
        update_actr: bool = False,
    ) -> None:
        """命中后刷新：last_recalled_ts=now + importance 微增 + 层内强化。

        update_actr=True（ACTIVATION 模式）时，先按 base-level learning 递推 actr_acc，
        必须在 last_recalled_ts 被刷新为 now *之前* 调用（_update_actr_acc 用旧 ts 算 dt）。
        """
        if obj is None:
            return
        beta = self._params["reconsolidation_rate"]
        if layer == "L3":
            # GraphNode：clarity 微增 + recall_count + 刷新 last_recalled_ts
            # （否则 recency 永远退化为中性 0.5，L3 的近期性维度形同虚设）
            if update_actr and hasattr(obj, "actr_acc"):
                self._update_actr_acc(obj, now)
            if hasattr(obj, "clarity"):
                obj.clarity = min(obj.clarity + 0.05, 1.0)
            if hasattr(obj, "recall_count"):
                obj.recall_count += 1
            if hasattr(obj, "last_recalled_ts"):
                obj.last_recalled_ts = now
            # reconsolidation：L3 节点情绪也随当前心境漂移（与 L2 对称，否则
            # 三层 reconsolidation 不一致——只有 L2 的记忆会被心境重塑）
            if hasattr(obj, "emotion_weight"):
                obj.emotion_weight = obj.emotion_weight * (1 - beta) + current_warmth * beta
            return
        # L1/L2 MemoryItem
        if update_actr:
            self._update_actr_acc(obj, now)  # 用旧 last_recalled_ts 算 dt
        obj.last_recalled_ts = now
        # importance 增益随接近上限而衰减（越重要的条目每次命中加得越少），
        # 配合 τ 的 recall_count 封顶，共同抑制 rich-get-richer 垄断。
        obj.importance = min(1.0, obj.importance + 0.02 * max(0.3, 1.0 - obj.importance))
        if layer == "L2":
            self._reinforce_l2(obj, current_warmth)
            self._recalled_l2_items.append(obj)
        else:
            # L1：刷新频率/召回时钟 + reconsolidation 温度漂移（与 L2 对称）。
            # 不做 L2 的权重强化（L1 是未确认近期摘要，强化留到下沉 L2 后）。
            obj.recall_count += 1
            obj.last_recalled_tick = self._tick
            obj.temperature = obj.temperature * (1 - beta) + current_warmth * beta

    def get_recalled_l2_items(self) -> list[MemoryItem]:
        """返回上次 recall() 中被命中的 L2 条目（供外部 reconsolidation 重写）。"""
        return getattr(self, "_recalled_l2_items", [])

    def rewrite_item(self, item_id: str, new_text: str) -> bool:
        """Reconsolidation v2: 用重写后的文本覆盖记忆条目。

        同时遍历 L1 与 L2——召回可能命中 L1 条目（近期摘要），若只查 L2，
        对 L1 命中项的 reconsolidation 重写会静默失败（找不到 → 返回 False）。
        """
        for store in (self._l1, self._l2):
            for item in store:
                if item.id == item_id:
                    if item.rewrite_count >= REWRITE_FREEZE_AFTER:
                        return False
                    item.text = new_text
                    item.rewrite_count += 1
                    item.weight = min(1.0, item.weight + 0.03)
                    return True
        return False

    # ------------------------------------------------------------------
    # Item 149: 记忆的"突然升温"
    # ------------------------------------------------------------------

    def reheat_memory(self, memory_id: str, reason: str) -> bool:
        """将指定记忆条目"突然升温"——刷新 last_recalled_ts 使 recency 复活。

        重构后：只刷新 last_recalled_ts（而非覆盖 created_at），保护真实创建时间
        用于注入时的相对时间标签。recency 评分基于 max(created_at, last_recalled_ts)，
        因此刷新 last_recalled_ts 即可让该记忆在下次召回获得更高近期性分。

        同时记录 reheat 原因到日志。

        Args:
            memory_id: 目标记忆条目的 ID。
            reason: 升温原因（用于日志记录）。

        Returns:
            True 表示成功找到并升温，False 表示未找到该 ID。
        """
        import logging

        _logger = logging.getLogger("astrbot_plugin_sylanne")
        now = time.time()

        # 在 L1 / L2 中查找
        for pool in (self._l1, self._l2):
            for item in pool:
                if item.id == memory_id:
                    item.last_recalled_ts = now
                    item.recall_count += 1
                    item.last_recalled_tick = self._tick
                    _logger.info(
                        f"Sylanne memory reheat: id={memory_id}, reason={reason}"
                    )
                    return True

        _logger.debug(
            f"Sylanne memory reheat failed: id={memory_id} not found"
        )
        return False

    def _compute_relevance(
        self,
        query: str,
        query_embedding: list[float] | None,
        text: str,
        item_embedding: list[float] | None,
        query_tokens: set[str] | None = None,
    ) -> float:
        if query_embedding and item_embedding:
            cos = _cosine(query_embedding, item_embedding)
            if cos >= 0.0:
                return cos
        if query_tokens is not None:
            return _keyword_overlap_precomputed(query_tokens, text)
        return _keyword_overlap(query, text)

    def _compute_relevance_with_reason(
        self,
        query: str,
        query_embedding: list[float] | None,
        text: str,
        item_embedding: list[float] | None,
        query_tokens: set[str] | None = None,
    ) -> tuple[float, str]:
        """计算相关度并返回召回原因。"""
        if query_embedding and item_embedding:
            cos = _cosine(query_embedding, item_embedding)
            if cos >= 0.0:
                return cos, "vector_similarity"
        if query_tokens is not None:
            kw = _keyword_overlap_precomputed(query_tokens, text)
        else:
            kw = _keyword_overlap(query, text)
        if kw > 0.0:
            return kw, "keyword_match"
        return 0.0, ""

    def _reinforce_l2(self, item: MemoryItem, current_warmth: float) -> None:
        """对被召回的 L2 条目施加强化：增加权重、重置年龄、更新情绪温度。"""
        item.weight += self._params["recall_boost"]
        item.weight = min(item.weight, 1.0)
        item.age_ticks = int(item.age_ticks * self._params["age_reset_factor"])
        item.recall_count += 1
        item.last_recalled_tick = self._tick
        beta = self._params["reconsolidation_rate"]
        item.temperature = item.temperature * (1 - beta) + current_warmth * beta

    def _recall_l3_candidates(self, query: str) -> list[dict]:
        """阶段1：从 L3 图谱按关键词匹配节点标签产出候选（只算 relevance）。

        不在此处计算 final_score 或施加强化副作用——final_score 由阶段2 统一
        composite 计算，节点强化（recall_count/clarity）由命中后 _refresh_recall 施加。
        importance 用 node.clarity 近似，emotional 用 node.emotion_weight（作温度）。
        """
        candidates: list[dict] = []
        query_lower = query.lower()
        # 用 _tokenize（jieba）而非 .split()：L1/L2 都用 _tokenize，L3 若用 .split()
        # 对中文（无空格）几乎切不出词，词级交集恒空、只能退到子串匹配，三层口径不一致。
        query_words = _tokenize(query)

        matched_nodes: list[GraphNode] = []
        for node in self._l3_nodes.values():
            if node.type == "boundary":
                if node.label.lower() not in query_lower:
                    continue
            label_words = _tokenize(node.label)
            if label_words & query_words or node.label.lower() in query_lower:
                matched_nodes.append(node)

        for node in matched_nodes:
            if node.clarity < 0.1:
                continue
            connected_texts: list[str] = []
            for edge in self._l3_edges:
                if edge.source == node.id or edge.target == node.id:
                    src_label = self._l3_nodes.get(edge.source)
                    tgt_label = self._l3_nodes.get(edge.target)
                    if src_label and tgt_label:
                        fragment = (
                            f"{src_label.label} {edge.relation} {tgt_label.label}"
                        )
                        connected_texts.append(fragment)

            text = node.label
            if connected_texts:
                text = f"{node.label}: {'; '.join(connected_texts[:3])}"

            # relevance：词级用对称 Jaccard（交集/并集），避免短 label 单词命中即虚高
            # （旧式 交集/len(query) 让 1 词 label 命中就得 0.33-0.5，挤占 L1/L2 槽位）。
            # 用 _tokenize 与上方匹配口径、与 L1/L2 口径一致。
            label_lower = node.label.lower()
            label_words = _tokenize(node.label)
            overlap = query_words & label_words
            if overlap:
                relevance = len(overlap) / max(len(query_words | label_words), 1)
            elif label_lower and label_lower in query_lower:
                # 整标签作为子串命中（中文无空格分词时的主路径，否则词级交集恒空、
                # relevance=0 被丢弃 → 中文 L3 召回瘫痪）。按标签字符占比给分，
                # 上限 0.5：子串命中证据强度弱于词级重合。
                relevance = min(0.5, len(label_lower) / max(len(query_lower), 1))
            else:
                continue
            if relevance <= 0.0:
                continue

            candidates.append({
                "rel": relevance,
                "reason": "association_graph",
                "obj": node,
                "layer": "L3",
                "text": text,
                "temperature": node.emotion_weight,  # emotional 用 emotion_weight
                "importance": node.clarity,           # importance 用 clarity 近似
                "created_at": getattr(node, "created_at", 0.0),
                "last_recalled_ts": getattr(node, "last_recalled_ts", 0.0),
                "recall_count": node.recall_count,
                "clarity": node.clarity,
            })

        return candidates

    # ------------------------------------------------------------------
    # 召回格式化（v2：分层注入）
    # ------------------------------------------------------------------

    def format_recall_injection(
        self,
        results: list[MemoryResult],
        max_items: int = 3,
    ) -> str:
        """格式化召回结果为 prompt 注入文本。

        使用记忆温度前缀（hot/warm/cold）提供时间距离感知，
        同时保留具体相对时间标签作为补充信息。
        L3 层额外标注可信度/模糊度。
        """
        if not results:
            return ""  # 空召回优于错召回（配合门控）
        lines = ["[记忆参考]"]
        now = time.time()
        for r in results[:max_items]:
            # 生活模拟记忆：这是 Sylanne 自己的生活/心境，不是和对方聊过的，
            # 用专属前缀避免 LLM 误以为"和用户真实聊过/发生过"
            if getattr(r, "source", "dialogue") == "life_sim":
                lines.append(f"（我自己经历的）{r.text}")
                continue
            # 阶段3 软召回：按置信度用不同措辞，让 LLM 感知"确信记得"vs"依稀"vs"舌尖"。
            # confidence 默认 "clear"（LEGACY 结果不带分级 → 走原确信路径，行为不变）。
            confidence = getattr(r, "confidence", "clear")
            time_label = self._relative_time_label(now, r.created_at)
            if confidence == "tot":
                # 舌尖现象：知道有这么回事但记不清内容——不直述细节，只给情感线索。
                lines.append(
                    f"（好像有件事和你有关{self._emotion_hint(r.temperature)}，"
                    f"但我一时记不太清了…）"
                )
                continue
            if confidence == "vague":
                snippet = r.text[:60]
                lines.append(
                    f"（依稀记得·{time_label}）好像是{snippet}……不过细节记得不太清了。"
                )
                continue
            # clear：确信记得（原有逻辑）
            temp_prefix = self._TEMPERATURE_PREFIXES.get(
                r.memory_temperature, "（之前聊过）"
            )
            if r.layer == "L3" and r.clarity < 0.7:
                prefix = f"{temp_prefix[:-1]}·{time_label}/模糊印象）"
            elif r.layer == "L3":
                prefix = f"{temp_prefix[:-1]}·{time_label}/长期认知）"
            else:
                prefix = f"{temp_prefix[:-1]}·{time_label}）"
            lines.append(f"{prefix}{r.text}")
        return "\n".join(lines)

    @staticmethod
    def _emotion_hint(temperature: float) -> str:
        """按温度返回情感线索（舌尖现象用，不泄露记忆内容细节）。"""
        if temperature >= 0.5:
            return "（是件挺开心的事）"
        if temperature <= -0.5:
            return "（那次你情绪有点低落）"
        if temperature < 0:
            return "（当时气氛有点微妙）"
        return ""

    @staticmethod
    def _relative_time_label(now: float, created_at: float) -> str:
        """将时间戳差值转换为自然语言相对时间标签。

        设计原则：给 LLM 足够的时间感知粒度，
        让它能区分"刚才说的"和"几天前聊过的"。
        """
        if not created_at or created_at <= 0:
            return "较早前"
        diff = now - created_at
        if diff < 60:
            return "刚才"
        elif diff < 3600:
            minutes = int(diff / 60)
            return f"{minutes}分钟前"
        elif diff < 86400:
            hours = int(diff / 3600)
            return f"{hours}小时前"
        elif diff < 172800:
            return "昨天"
        elif diff < 604800:
            days = int(diff / 86400)
            return f"{days}天前"
        elif diff < 2592000:
            weeks = int(diff / 604800)
            return f"{weeks}周前"
        else:
            months = int(diff / 2592000)
            return f"{months}个月前"

    # ------------------------------------------------------------------
    # 30 天 L2→L3 压缩（v2）
    # ------------------------------------------------------------------

    def compress_check(self) -> list[MemoryItem]:
        """v2: 返回 L2 中 30 天未被召回的条目（按 age_ticks 判断）。"""
        return [
            item for item in self._l2 if item.age_ticks >= L2_COMPRESSION_AGE_TICKS
        ][:10]

    def remove_compressed(self, item_ids: list[str]) -> None:
        """压缩完成后，从 L2 中移除已压缩的条目。"""
        id_set = set(item_ids)
        self._l2 = [item for item in self._l2 if item.id not in id_set]

    # ------------------------------------------------------------------
    # L3 图谱摄入
    # ------------------------------------------------------------------

    def ingest_graph_triples(self, triples: list) -> None:
        """将 LLM 实体抽取结果合并入 L3 图。"""
        for triple in triples:
            if isinstance(triple, (list, tuple)):
                subj_label = str(triple[0])
                relation = str(triple[1])
                obj_label = str(triple[2])
                emotion = float(triple[3]) if len(triple) > 3 else 0.0
                clarity = float(triple[4]) if len(triple) > 4 else 0.5
                temporal_type = "episodic"
                valid_from = None
                subj_type = "topic"
                obj_type = "topic"
            else:
                subj_label = triple["subject"]
                obj_label = triple["object"]
                relation = triple["relation"]
                emotion = triple.get("emotion_weight", 0.0)
                clarity = triple.get("clarity", 0.5)
                temporal_type = triple.get("temporal_type", "episodic")
                valid_from = triple.get("valid_from")
                subj_type = triple.get("subject_type", "topic")
                obj_type = triple.get("object_type", "topic")

            subj_node = self._find_or_create_node(
                label=subj_label,
                node_type=subj_type,
                emotion_weight=emotion,
                clarity=clarity,
                temporal_type=temporal_type,
                valid_from=valid_from,
            )
            obj_node = self._find_or_create_node(
                label=obj_label,
                node_type=obj_type,
                emotion_weight=emotion,
                clarity=clarity,
                temporal_type=temporal_type,
                valid_from=valid_from,
            )
            self._find_or_create_edge(
                source=subj_node.id,
                target=obj_node.id,
                relation=relation,
                emotion_weight=emotion,
                clarity=clarity,
            )

        if len(self._l3_nodes) > self._L3_NODE_LIMIT:
            self._gc_l3()

    def _find_or_create_node(
        self,
        label: str,
        node_type: str,
        emotion_weight: float,
        clarity: float,
        temporal_type: str = "episodic",
        valid_from: str | None = None,
    ) -> GraphNode:
        if not hasattr(self, "_l3_label_index"):
            self._l3_label_index = {n.label: nid for nid, n in self._l3_nodes.items()}
        existing_id = self._l3_label_index.get(label)
        if existing_id and existing_id in self._l3_nodes:
            node = self._l3_nodes[existing_id]
            node.clarity = max(node.clarity, clarity)
            node.emotion_weight = (node.emotion_weight + emotion_weight) / 2
            return node
        node = GraphNode(
            id=uuid.uuid4().hex[:12],
            label=label,
            type=node_type,
            temporal_type=temporal_type,
            emotion_weight=emotion_weight,
            clarity=clarity,
            recall_count=0,
            valid_from=valid_from,
            staleness_threshold=180,
            created_at=time.time(),
        )
        self._l3_nodes[node.id] = node
        self._l3_label_index[label] = node.id
        return node

    def _find_or_create_edge(
        self,
        source: str,
        target: str,
        relation: str,
        emotion_weight: float,
        clarity: float,
    ) -> GraphEdge:
        if not hasattr(self, "_l3_edge_index"):
            self._l3_edge_index = {
                (e.source, e.target, e.relation): i for i, e in enumerate(self._l3_edges)
            }
        key = (source, target, relation)
        idx = self._l3_edge_index.get(key)
        if idx is not None and idx < len(self._l3_edges):
            edge = self._l3_edges[idx]
            if edge.source == source and edge.target == target and edge.relation == relation:
                edge.emotion_weight = (edge.emotion_weight + emotion_weight) / 2
                edge.clarity = max(edge.clarity, clarity)
                return edge
        edge = GraphEdge(
            source=source,
            target=target,
            relation=relation,
            emotion_weight=emotion_weight,
            clarity=clarity,
            last_recalled=self._tick,
            strength=_relation_strength(relation),  # 阶段2 spreading 用
        )
        self._l3_edges.append(edge)
        self._l3_edge_index[key] = len(self._l3_edges) - 1
        if len(self._l3_edges) > 2000:
            self._l3_edges.sort(key=lambda e: e.clarity, reverse=True)
            self._l3_edges = self._l3_edges[:1500]
            self._l3_edge_index = {
                (e.source, e.target, e.relation): i for i, e in enumerate(self._l3_edges)
            }
        return edge

    # ------------------------------------------------------------------
    # Item 58: 对话缓冲区压缩
    # ------------------------------------------------------------------

    def compress_old_turns(self, session_key: str, max_turns: int = 20) -> int:
        """压缩对话缓冲区中超出 max_turns 的旧消息。

        将最旧的 N 条（超出部分）合并为一条摘要（前 50 字 + "..."），
        不调用 LLM，纯本地截断合并。

        Args:
            session_key: 会话标识（用于日志，实际操作在 L1 上）
            max_turns: 保留的最大条目数

        Returns:
            压缩掉的条数
        """
        if len(self._l1) <= max_turns:
            return 0
        overflow = len(self._l1) - max_turns
        # 取出最旧的 overflow 条
        old_items: list[MemoryItem] = []
        for _ in range(overflow):
            old_items.append(self._l1.popleft())
        # 合并为一条摘要
        merged_text = " | ".join(item.text[:50] for item in old_items)
        if len(merged_text) > 200:
            merged_text = merged_text[:200] + "..."
        avg_temp = sum(item.temperature for item in old_items) / len(old_items)
        # importance 取被合并条目的最大值，而非默认 0.5：一批旧消息里若含承诺/约定
        # 等高重要性条目，压缩后不能把它稀释成中性，否则重要信号在压缩时静默丢失。
        max_imp = max((item.importance for item in old_items), default=0.5)
        self._l1.appendleft(
            MemoryItem(
                id=uuid.uuid4().hex[:12],
                text=f"[压缩摘要] {merged_text}",
                weight=0.5,
                temperature=avg_temp,
                age_ticks=max(item.age_ticks for item in old_items),
                embedding=None,
                created_at=old_items[0].created_at,
                source_turns=sum(item.source_turns for item in old_items),
                confirmed=False,
                recall_count=0,
                last_recalled_tick=0,
                rewrite_count=0,
                importance=max_imp,
            )
        )
        return overflow

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """序列化全部三层为可 JSON 化的 dict。"""
        return {
            "version": "2.0.0",
            "tick": self._tick,
            "last_consolidation_ts": self._last_consolidation_ts,
            "params": dict(self._params),
            "l1": [item.to_dict() for item in self._l1],
            "l2": [item.to_dict() for item in self._l2],
            "l3_nodes": {nid: node.to_dict() for nid, node in self._l3_nodes.items()},
            "l3_edges": [edge.to_dict() for edge in self._l3_edges],
        }

    def from_dict(self, data: dict) -> "MemorySystem":
        """从 dict 恢复全部三层状态（就地修改并返回 self）。"""
        self._restore_from_data(data)
        return self

    @classmethod
    def create_from_dict(cls, data: dict) -> "MemorySystem":
        """从 dict 创建新的 MemorySystem 实例。"""
        mem = cls()
        mem._restore_from_data(data)
        return mem

    def _restore_from_data(self, data: dict) -> None:
        """就地从 dict 恢复全部三层状态。兼容 v1 和 v2 格式。"""
        self._tick = data.get("tick", 0)
        self._last_consolidation_ts = data.get("last_consolidation_ts", 0.0)
        saved_params = data.get("params")
        if saved_params is not None:
            self._params.update(saved_params)

        l1_items = [MemoryItem.from_dict(d) for d in data.get("l1", [])]
        self._l1 = deque(l1_items, maxlen=self._L1_CAPACITY)
        self._l2 = [MemoryItem.from_dict(d) for d in data.get("l2", [])]
        self._l3_nodes = {
            nid: GraphNode.from_dict(nd) for nid, nd in data.get("l3_nodes", {}).items()
        }
        self._l3_edges = [GraphEdge.from_dict(ed) for ed in data.get("l3_edges", [])]
        self._l3_label_index: dict[str, str] = {
            n.label: nid for nid, n in self._l3_nodes.items()
        }
        self._l3_edge_index: dict[tuple[str, str, str], int] = {
            (e.source, e.target, e.relation): i for i, e in enumerate(self._l3_edges)
        }


# ---------------------------------------------------------------------------
# Item 13: 倒排索引加速召回
# ---------------------------------------------------------------------------


class InvertedIndex:
    """简单倒排索引：关键词 → 记忆 ID 列表。"""

    def __init__(self) -> None:
        self._index: dict[str, set[str]] = {}  # keyword -> {memory_id, ...}

    def add(self, memory_id: str, keywords: list[str]) -> None:
        for kw in keywords:
            if kw not in self._index:
                self._index[kw] = set()
            self._index[kw].add(memory_id)

    def remove(self, memory_id: str) -> None:
        for kw_set in self._index.values():
            kw_set.discard(memory_id)

    def query(self, keywords: list[str], top_k: int = 10) -> list[str]:
        """返回匹配最多关键词的 memory_id 列表。"""
        scores: dict[str, int] = {}
        for kw in keywords:
            for mid in self._index.get(kw, set()):
                scores[mid] = scores.get(mid, 0) + 1
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [mid for mid, _ in ranked[:top_k]]

    def size(self) -> int:
        return sum(len(v) for v in self._index.values())


# ---------------------------------------------------------------------------
# Item 35: 关系考古学（简化版）
# ---------------------------------------------------------------------------


class ArchaeologyEngine:
    """关系考古学：从冷记忆中发掘被遗忘的关系模式。"""

    def __init__(self) -> None:
        self._last_dig: float = 0
        self._findings: list[dict] = []

    def should_dig(self, now: float) -> bool:
        """每 24h 最多挖掘一次。"""
        return now - self._last_dig > 86400

    def dig(self, cold_memories: list, max_findings: int = 3) -> list[dict]:
        """从冷记忆中发掘模式。"""
        self._last_dig = time.time()

        if len(cold_memories) < 5:
            return []

        # 简单模式发掘：找到重复出现的关键词/主题
        word_freq: dict[str, int] = {}
        for mem in cold_memories:
            text = getattr(mem, "text", str(mem))
            # 简单分词
            for word in text.split():
                if len(word) >= 2:
                    word_freq[word] = word_freq.get(word, 0) + 1

        # 高频词 = 被遗忘的模式
        patterns = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[
            :max_findings
        ]
        findings = [
            {
                "pattern": p[0],
                "frequency": p[1],
                "interpretation": f"在过去的对话中，'{p[0]}' 反复出现了 {p[1]} 次",
            }
            for p in patterns
            if p[1] >= 3
        ]

        self._findings.extend(findings)
        return findings

    def get_recent_findings(self, n: int = 5) -> list[dict]:
        return self._findings[-n:]


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mem = MemorySystem()
    mem.derive_params(
        {
            "openness": 0.7,
            "conscientiousness": 0.5,
            "extraversion": 0.6,
            "agreeableness": 0.8,
            "neuroticism": 0.4,
        }
    )

    # v2: write summaries
    mem.write_summary(
        "聊了关于猫的话题，用户说家里有两只猫", source_turns=5, temperature=0.6
    )
    mem.write_summary(
        "讨论了期末考试压力，用户说下周有三门考试", source_turns=8, temperature=0.3
    )
    mem.write_summary(
        "用户提到喜欢开放世界游戏，特别是地平线系列",
        source_turns=3,
        embedding=[0.1] * 8,
        temperature=0.7,
    )

    # Mark confirmed and sink
    ids = [item.id for item in mem._l1]
    mem.mark_confirmed(ids)
    candidates = mem.consolidation_candidates()
    mem.sink_to_l2([c.id for c in candidates])
    print(f"L1: {len(mem._l1)}, L2: {len(mem._l2)}")

    # Recall
    results = mem.recall("猫", current_warmth=0.5)
    print(f"Recall results: {len(results)}")
    for r in results[:3]:
        print(f"  [{r.layer}] score={r.final_score:.3f} text={r.text[:40]}")

    # Format injection
    print(mem.format_recall_injection(results))

    # Compression (30-day)
    for item in mem._l2:
        item.age_ticks = 3500
    to_compress = mem.compress_check()
    print(f"Items ready for 30-day compression: {len(to_compress)}")

    # Serialization roundtrip
    data = mem.to_dict()
    mem2 = MemorySystem.create_from_dict(data)
    print(
        f"Restored: L1={len(mem2._l1)}, L2={len(mem2._l2)}, version={data['version']}"
    )

    # Graph ingestion
    mem.ingest_graph_triples(
        [
            {
                "subject": "用户",
                "relation": "喜欢",
                "object": "猫",
                "subject_type": "person",
                "object_type": "preference",
                "emotion_weight": 0.8,
                "clarity": 0.9,
                "temporal_type": "permanent",
            },
        ]
    )
    print(f"L3 nodes={len(mem._l3_nodes)}, edges={len(mem._l3_edges)}")

    # ConversationBuffer test
    buf = ConversationBuffer(session_key="test")
    buf.append("user", "你好")
    buf.append("bot", "你好呀")
    assert buf.turn_count == 1
    assert buf.should_flush(idle_seconds=0.001, max_turns=20) == ""
    import time as _t

    _t.sleep(0.01)
    assert buf.should_flush(idle_seconds=0.001, max_turns=20) == "idle"
    msgs = buf.drain()
    assert len(msgs) == 2 and buf.turn_count == 0

    print("ALL OK")
