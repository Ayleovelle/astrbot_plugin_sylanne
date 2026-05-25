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
from typing import Any

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class MemoryItem:
    """单条记忆条目，驻留于 L1 或 L2。"""

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
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryItem":
        return cls(
            id=d["id"],
            text=d["text"],
            weight=d["weight"],
            temperature=d["temperature"],
            age_ticks=d["age_ticks"],
            embedding=d.get("embedding"),
            created_at=d["created_at"],
            source_turns=d.get("source_turns", 1),
            confirmed=d.get("confirmed", False),
            recall_count=d.get("recall_count", 0),
            last_recalled_tick=d.get("last_recalled_tick", 0),
            rewrite_count=d.get("rewrite_count", 0),
        )


@dataclass
class MemoryResult:
    """召回结果，包含最终评分和来源层信息。"""

    text: str
    layer: str  # "L1" | "L2" | "L3"
    weight: float
    relevance: float
    clarity: float
    temperature: float
    final_score: float


@dataclass
class GraphNode:
    """L3 知识图谱节点。"""

    id: str
    label: str
    type: str  # person/topic/event/preference/boundary
    temporal_type: str  # permanent/evolving/episodic
    emotion_weight: float  # [-1.0, 1.0]
    clarity: float  # [0.0, 1.0]
    recall_count: int = 0
    valid_from: str | None = None  # ISO date for evolving
    staleness_threshold: int = 180  # days, default 6 months

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

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "relation": self.relation,
            "emotion_weight": self.emotion_weight,
            "clarity": self.clarity,
            "last_recalled": self.last_recalled,
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
        )


@dataclass
class ConversationBuffer:
    """会话暂存区，对话进行中暂存原文，不写入 MemorySystem。"""

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

    def should_flush(self, idle_seconds: float = 60.0, max_turns: int = 20) -> str:
        """返回触发原因，空字符串表示不需要 flush。"""
        if not self.messages:
            return ""
        if self.turn_count >= max_turns:
            return "max_turns"
        now = time.time()
        if now - self.last_activity >= idle_seconds:
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


def _cosine(a: list[float], b: list[float]) -> float:
    """Inline cosine similarity. Returns -1.0 sentinel for degenerate inputs."""
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
    try:
        import jieba

        return set(
            w
            for w in jieba.cut(text)
            if len(w.strip()) >= 1 and w.strip() not in _STOPWORDS
        )
    except ImportError:
        pass
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
    """Keyword overlap with Chinese support (jieba or bigram fallback)."""
    q_words = _tokenize(query)
    t_words = _tokenize(text)
    if not q_words or not t_words:
        return 0.0
    intersection = q_words & t_words
    return len(intersection) / max(len(q_words), 1)


# ---------------------------------------------------------------------------
# MemorySystem
# ---------------------------------------------------------------------------

# v2 constants
IDLE_FLUSH_SECONDS = 60.0
MAX_TURNS_BEFORE_FLUSH = 20
CONSOLIDATION_INTERVAL_HOURS = 12
CONSOLIDATION_KEEP_RECENT_HOURS = 2
L2_COMPRESSION_AGE_TICKS = 3000  # ~30 days at 100 msgs/day
REWRITE_FREEZE_AFTER = 20


class MemorySystem:
    """
    三层记忆系统 v2 主接口。

    L1: Hot Pool (deque, maxlen=50) - 近期对话摘要
    L2: Warm Pool (list) - 已确认的重要记忆, 向量相似度召回
    L3: Cold Pool (graph) - 实体-关系图, clarity 衰减
    """

    _LAYER_WEIGHTS = {"L1": 1.0, "L2": 0.7, "L3": 0.4}
    _L1_CAPACITY = 60
    _L3_NODE_LIMIT = 1000

    def __init__(self, **kwargs) -> None:
        self._l1: deque[MemoryItem] = deque(maxlen=self._L1_CAPACITY)
        self._l2: list[MemoryItem] = []
        self._l3_nodes: dict[str, GraphNode] = {}
        self._l3_edges: list[GraphEdge] = []
        self._tick: int = 0
        self._last_consolidation_ts: float = 0.0
        self._recalled_l2_items: list[MemoryItem] = []
        self._params: dict[str, float] = {
            "base_decay": 0.02,
            "age_coeff": 0.15,
            "recall_boost": 0.03,
            "age_reset_factor": 0.5,
            "reconsolidation_rate": 0.05,
            "compression_threshold": 0.15,
            "mood_weight": 0.2,
            "positive_recall_bias": 1.0,
            "negative_decay_mult": 1.0,
            "neuroticism": 0.5,
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
    # Personality derivation
    # ------------------------------------------------------------------

    def derive_params(self, personality: dict[str, float]) -> None:
        """从人格向量推导记忆系统参数。接受 Big Five 或 Embodiment Five 名称。"""
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
        self._params["negative_decay_mult"] = 1.0 - N * 0.5
        self._params["neuroticism"] = N

    # ------------------------------------------------------------------
    # Write (v2: summary-based)
    # ------------------------------------------------------------------

    _MAX_SUMMARY_CHARS = 500

    def write_summary(
        self,
        text: str,
        source_turns: int = 1,
        embedding: list[float] | None = None,
        temperature: float = 0.0,
    ) -> MemoryItem:
        """v2 写入：将对话摘要写入 L1。由会话结束/20轮保底触发。"""
        text = text[: self._MAX_SUMMARY_CHARS]
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
        )
        self._l1.append(item)
        return item

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
    # 12h Consolidation (v2)
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
    # Tick decay
    # ------------------------------------------------------------------

    def tick_decay(self) -> None:
        """推进衰减时钟一步。每条消息调用一次。"""
        self._tick += 1
        base_decay = self._params["base_decay"]
        age_coeff = self._params["age_coeff"]
        neuroticism = self._params["neuroticism"]
        neg_decay_mult = self._params["negative_decay_mult"]

        for item in self._l2:
            decay_rate = base_decay * (1 + age_coeff * math.log(item.age_ticks + 1))
            item.age_ticks += 1
            if item.temperature < 0.3 and neuroticism > 0.6:
                decay_rate *= neg_decay_mult
            item.weight *= 1 - decay_rate
            if item.weight < 1e-10:
                item.weight = 0.0

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
                    node.clarity *= 0.998 / staleness
                else:
                    node.clarity *= 0.998
            else:
                node.clarity *= 0.998

        for edge in self._l3_edges:
            edge.clarity *= 0.998

        self._gc_l3()

    def _gc_l3(self) -> None:
        """Remove L3 nodes and edges below clarity threshold, enforce node limit."""
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

    # ------------------------------------------------------------------
    # Recall (v2: three-layer parallel with reconsolidation hook)
    # ------------------------------------------------------------------

    def recall(
        self,
        query: str,
        query_embedding: list[float] | None = None,
        current_warmth: float = 0.0,
        limit: int = 5,
    ) -> list[MemoryResult]:
        """并行查询三层，返回加权合并后的 top-k 结果。"""
        candidates: list[MemoryResult] = []
        mood_weight = self._params["mood_weight"]
        positive_recall_bias = self._params["positive_recall_bias"]

        # --- L1 recall ---
        for item in self._l1:
            relevance = self._compute_relevance(
                query, query_embedding, item.text, item.embedding
            )
            if relevance <= 0.0:
                continue
            emotion_bias = 1.0 - abs(item.temperature - current_warmth) * mood_weight
            final_score = (
                self._LAYER_WEIGHTS["L1"] * item.weight * relevance * emotion_bias
            )
            if item.temperature > 0:
                final_score += (positive_recall_bias - 1.0) * relevance
            candidates.append(
                MemoryResult(
                    text=item.text,
                    layer="L1",
                    weight=item.weight,
                    relevance=relevance,
                    clarity=1.0,
                    temperature=item.temperature,
                    final_score=final_score,
                )
            )

        # --- L2 recall ---
        self._recalled_l2_items: list[MemoryItem] = []
        for item in self._l2:
            relevance = self._compute_relevance(
                query, query_embedding, item.text, item.embedding
            )
            if relevance <= 0.0:
                continue
            emotion_bias = 1.0 - abs(item.temperature - current_warmth) * mood_weight
            final_score = (
                self._LAYER_WEIGHTS["L2"] * item.weight * relevance * emotion_bias
            )
            if item.temperature > 0:
                final_score += (positive_recall_bias - 1.0) * relevance
            candidates.append(
                MemoryResult(
                    text=item.text,
                    layer="L2",
                    weight=item.weight,
                    relevance=relevance,
                    clarity=1.0,
                    temperature=item.temperature,
                    final_score=final_score,
                )
            )
            self._reinforce_l2(item, current_warmth)
            self._recalled_l2_items.append(item)

        # --- L3 recall ---
        l3_results = self._recall_l3(query, current_warmth)
        candidates.extend(l3_results)

        candidates.sort(key=lambda r: r.final_score, reverse=True)
        return candidates[:limit]

    def get_recalled_l2_items(self) -> list[MemoryItem]:
        """返回上次 recall() 中被命中的 L2 条目（供外部 reconsolidation 重写）。"""
        return getattr(self, "_recalled_l2_items", [])

    def rewrite_item(self, item_id: str, new_text: str) -> bool:
        """Reconsolidation v2: 用重写后的文本覆盖 L2 条目。"""
        for item in self._l2:
            if item.id == item_id:
                if item.rewrite_count >= REWRITE_FREEZE_AFTER:
                    return False
                item.text = new_text
                item.rewrite_count += 1
                item.weight += 0.03
                return True
        return False

    def _compute_relevance(
        self,
        query: str,
        query_embedding: list[float] | None,
        text: str,
        item_embedding: list[float] | None,
    ) -> float:
        if query_embedding and item_embedding:
            cos = _cosine(query_embedding, item_embedding)
            if cos >= 0.0:
                return cos
        return _keyword_overlap(query, text)

    def _reinforce_l2(self, item: MemoryItem, current_warmth: float) -> None:
        """Apply recall reinforcement to an L2 item."""
        item.weight += self._params["recall_boost"]
        item.weight = min(item.weight, 1.0)
        item.age_ticks = int(item.age_ticks * self._params["age_reset_factor"])
        item.recall_count += 1
        item.last_recalled_tick = self._tick
        beta = self._params["reconsolidation_rate"]
        item.temperature = item.temperature * (1 - beta) + current_warmth * beta

    def _recall_l3(self, query: str, current_warmth: float) -> list[MemoryResult]:
        """Recall from L3 graph via keyword matching on node labels."""
        results: list[MemoryResult] = []
        query_lower = query.lower()
        query_words = set(query_lower.split())
        mood_weight = self._params["mood_weight"]

        matched_nodes: list[GraphNode] = []
        for node in self._l3_nodes.values():
            if node.type == "boundary":
                if node.label.lower() not in query_lower:
                    continue
            label_words = set(node.label.lower().split())
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

            relevance = len(query_words & set(node.label.lower().split())) / max(
                len(query_words), 1
            )
            relevance = max(relevance, 0.3)

            emotion_bias = 1.0 - abs(node.emotion_weight - current_warmth) * mood_weight
            final_score = (
                self._LAYER_WEIGHTS["L3"] * node.clarity * relevance * emotion_bias
            )

            node.recall_count += 1
            node.clarity = min(node.clarity + 0.05, 1.0)

            results.append(
                MemoryResult(
                    text=text,
                    layer="L3",
                    weight=node.clarity,
                    relevance=relevance,
                    clarity=node.clarity,
                    temperature=node.emotion_weight,
                    final_score=final_score,
                )
            )

        return results

    # ------------------------------------------------------------------
    # Recall formatting (v2: layered injection)
    # ------------------------------------------------------------------

    def format_recall_injection(
        self,
        results: list[MemoryResult],
        max_items: int = 3,
    ) -> str:
        """格式化召回结果为 prompt 注入文本。"""
        if not results:
            return ""
        lines = ["[记忆参考]"]
        for r in results[:max_items]:
            if r.layer == "L1":
                prefix = "近期"
            elif r.layer == "L2":
                prefix = "相关"
            else:
                if r.clarity < 0.7:
                    prefix = "好像提过"
                else:
                    prefix = "认知"
            lines.append(f"{prefix}：{r.text}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 30-day L2→L3 compression (v2)
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
    # L3 graph ingestion
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
        for node in self._l3_nodes.values():
            if node.label == label:
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
        )
        self._l3_nodes[node.id] = node
        return node

    def _find_or_create_edge(
        self,
        source: str,
        target: str,
        relation: str,
        emotion_weight: float,
        clarity: float,
    ) -> GraphEdge:
        for edge in self._l3_edges:
            if (
                edge.source == source
                and edge.target == target
                and edge.relation == relation
            ):
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
        )
        self._l3_edges.append(edge)
        if len(self._l3_edges) > 2000:
            self._l3_edges.sort(key=lambda e: e.clarity, reverse=True)
            self._l3_edges = self._l3_edges[:1500]
        return edge

    # ------------------------------------------------------------------
    # Serialization
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
        self._params = data.get("params", self._params)

        l1_items = [MemoryItem.from_dict(d) for d in data.get("l1", [])]
        self._l1 = deque(l1_items, maxlen=self._L1_CAPACITY)
        self._l2 = [MemoryItem.from_dict(d) for d in data.get("l2", [])]
        self._l3_nodes = {
            nid: GraphNode.from_dict(nd) for nid, nd in data.get("l3_nodes", {}).items()
        }
        self._l3_edges = [GraphEdge.from_dict(ed) for ed in data.get("l3_edges", [])]


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
