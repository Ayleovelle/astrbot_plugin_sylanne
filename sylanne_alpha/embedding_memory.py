"""Sylanne-Embodiment: 向量嵌入记忆模块（旧版兼容层）。

本模块已被 memory_system.py 的三层记忆系统取代，
保留仅为提供向后兼容的公开 API 方法。

核心功能：基于向量余弦相似度的语义检索，
当关键词匹配失败时回退到嵌入向量匹配。
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

EMBEDDING_MEMORY_SCHEMA_VERSION = "sylanne.alpha.embedding_memory.v1"


def recall_with_embedding_assist(
    *,
    query: str,
    records: list[dict[str, Any]],
    enabled: bool = False,
    embed_query: Callable[[str], list[float]] | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """带嵌入向量辅助的记忆召回。

    召回策略（优先级从高到低）：
    1. 关键词匹配：如果有命中，直接返回（最快）
    2. 向量相似度：关键词无命中且 enabled=True 时，用余弦相似度排序

    参数:
        query: 查询文本
        records: 记忆记录列表，每条包含 text 和可选的 embedding 字段
        enabled: 是否启用向量检索（需要 embed_query 回调）
        embed_query: 将查询文本转为向量的回调函数
        limit: 最多返回条数

    返回:
        包含 schema_version、source（检索方式）、matches、count 的结果字典
    """
    # 优先尝试关键词匹配（零延迟）
    keyword_matches = _keyword_matches(query, records)
    if keyword_matches:
        return _payload("keyword", keyword_matches[:limit])
    # 关键词无命中，尝试向量检索
    if not enabled or embed_query is None:
        return _payload("keyword", [])
    vector_records = [
        record for record in records if isinstance(record.get("embedding"), list)
    ]
    if not vector_records:
        return _payload("keyword", [])
    try:
        query_vector = [float(value) for value in embed_query(query)]
    except Exception:
        return _payload("keyword", [])
    # 按余弦相似度降序排列
    ranked = sorted(
        (
            (
                _cosine(
                    query_vector,
                    [float(value) for value in record.get("embedding", [])],
                ),
                record,
            )
            for record in vector_records
        ),
        key=lambda pair: pair[0],
        reverse=True,
    )
    matches = [_sanitize(record, score=score) for score, record in ranked if score > 0]
    return _payload("embedding", matches[:limit])


def _keyword_matches(query: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """简单关键词匹配：按空格分词，任一词命中即算匹配。"""
    terms = [term for term in str(query or "").split() if term]
    if not terms and query:
        terms = [str(query)]
    matches = []
    for record in records:
        text = str(record.get("text") or "")
        if any(term in text for term in terms):
            matches.append(_sanitize(record, score=float(record.get("weight") or 0.0)))
    return sorted(matches, key=lambda item: item.get("score", 0.0), reverse=True)


def _sanitize(record: dict[str, Any], *, score: float) -> dict[str, Any]:
    """清洗记录：只保留 id、text（截断 500 字）、score。"""
    return {
        "id": str(record.get("id") or ""),
        "text": str(record.get("text") or "")[:500],
        "score": round(float(score), 6),
    }


def _payload(source: str, matches: list[dict[str, Any]]) -> dict[str, Any]:
    """构造标准返回格式。"""
    return {
        "schema_version": EMBEDDING_MEMORY_SCHEMA_VERSION,
        "source": source,
        "matches": matches,
        "count": len(matches),
    }


def _cosine(left: list[float], right: list[float]) -> float:
    """计算两个向量的余弦相似度。维度不等时取较短的。"""
    size = min(len(left), len(right))
    if size == 0:
        return 0.0
    dot = sum(left[index] * right[index] for index in range(size))
    left_norm = math.sqrt(sum(value * value for value in left[:size]))
    right_norm = math.sqrt(sum(value * value for value in right[:size]))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


# ---------------------------------------------------------------------------
# Item 116: 学习驱动知识图谱扩展
# ---------------------------------------------------------------------------


class KnowledgeFrontier:
    """识别用户频繁提及但 Sylanne 理解薄弱的领域。

    通过追踪话题的提及频率和 Sylanne 的理解置信度，
    计算学习优先级（高频提及 × 低置信度），帮助 Sylanne
    识别最需要主动学习的知识领域。

    与其他组件的关系：
    - 被对话处理流程调用 observe_topic() 记录话题
    - 提供 get_learning_targets() 供主动学习调度器使用
    - 支持序列化/反序列化以持久化存储
    """

    def __init__(self, max_topics: int = 20):
        self._topic_mentions: dict[str, int] = {}  # topic -> mention count
        self._topic_confidence: dict[str, float] = {}  # topic -> Sylanne 的理解置信度
        self._max = max_topics

    def observe_topic(self, topic: str, sylanne_confidence: float = 0.5):
        """记录用户提及的话题和 Sylanne 的理解程度。

        参数:
            topic: 话题标识
            sylanne_confidence: Sylanne 对该话题的理解置信度 [0, 1]
        """
        self._topic_mentions[topic] = self._topic_mentions.get(topic, 0) + 1
        # 置信度取最近值
        self._topic_confidence[topic] = sylanne_confidence
        # 超出上限时移除最少提及的
        if len(self._topic_mentions) > self._max:
            min_topic = min(self._topic_mentions, key=self._topic_mentions.get)  # type: ignore[arg-type]
            del self._topic_mentions[min_topic]
            self._topic_confidence.pop(min_topic, None)

    def get_learning_targets(self, top_n: int = 3) -> list[dict]:
        """返回最需要学习的话题（高频提及 + 低置信度）。

        学习优先级 = 提及频率 × (1 - 置信度)

        参数:
            top_n: 返回前 N 个最高优先级话题

        返回:
            按优先级降序排列的话题列表
        """
        scored = []
        for topic, count in self._topic_mentions.items():
            confidence = self._topic_confidence.get(topic, 0.5)
            # 学习优先级 = 提及频率 × (1 - 置信度)
            priority = count * (1 - confidence)
            scored.append(
                {
                    "topic": topic,
                    "mentions": count,
                    "confidence": confidence,
                    "priority": priority,
                }
            )
        scored.sort(key=lambda x: x["priority"], reverse=True)
        return scored[:top_n]

    def to_dict(self) -> dict:
        """序列化为字典。"""
        return {
            "mentions": dict(self._topic_mentions),
            "confidence": dict(self._topic_confidence),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeFrontier":
        """从字典恢复 KnowledgeFrontier 实例。"""
        kf = cls()
        kf._topic_mentions = data.get("mentions", {})
        kf._topic_confidence = data.get("confidence", {})
        return kf


__all__ = [
    "EMBEDDING_MEMORY_SCHEMA_VERSION",
    "recall_with_embedding_assist",
    "KnowledgeFrontier",
]
