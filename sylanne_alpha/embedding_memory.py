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


__all__ = ["EMBEDDING_MEMORY_SCHEMA_VERSION", "recall_with_embedding_assist"]
