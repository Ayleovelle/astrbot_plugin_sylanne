# Legacy: being replaced by memory_system.py. Kept for backward-compatible public API methods.
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
    keyword_matches = _keyword_matches(query, records)
    if keyword_matches:
        return _payload("keyword", keyword_matches[:limit])
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
    return {
        "id": str(record.get("id") or ""),
        "text": str(record.get("text") or "")[:500],
        "score": round(float(score), 6),
    }


def _payload(source: str, matches: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": EMBEDDING_MEMORY_SCHEMA_VERSION,
        "source": source,
        "matches": matches,
        "count": len(matches),
    }


def _cosine(left: list[float], right: list[float]) -> float:
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
