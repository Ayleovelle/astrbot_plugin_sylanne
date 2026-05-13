from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from hashlib import sha1
from typing import Any


PUBLIC_MEMORY_STORE_SCHEMA_VERSION = "astrbot.sylanne_memory_state.v1"


def clamp(value: Any, lower: float = 0.0, upper: float = 1.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = lower
    return max(lower, min(upper, number))


def signed_clamp(value: Any, magnitude: float = 1.0) -> float:
    return clamp(value, -abs(magnitude), abs(magnitude))


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clean_text(text: Any, limit: int = 1200) -> str:
    raw = re.sub(r"\s+", " ", str(text or "")).strip()
    return raw[:limit]


def _clip(text: str, limit: int) -> str:
    if limit <= 0:
        return ""
    text = str(text or "")
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _values(snapshot: Any, key: str = "values") -> dict[str, float]:
    if not isinstance(snapshot, dict):
        return {}
    raw = snapshot.get(key)
    if not isinstance(raw, dict):
        raw = (snapshot.get("emotion") or {}).get(key)
    if not isinstance(raw, dict):
        return {}
    return {str(k): _as_float(v, 0.0) for k, v in raw.items()}


def _nested(snapshot: Any, *path: str) -> Any:
    current = snapshot
    for item in path:
        if not isinstance(current, dict):
            return None
        current = current.get(item)
    return current


def half_life_multiplier(elapsed_seconds: float, half_life_seconds: float) -> float:
    if elapsed_seconds <= 0:
        return 1.0
    if half_life_seconds <= 0:
        return 0.0
    return clamp(2.0 ** (-elapsed_seconds / half_life_seconds))


def _tokenize(text: str) -> set[str]:
    text = str(text or "").lower()
    tokens = set(re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]{1,4}", text))
    cjk_runs = re.findall(r"[\u4e00-\u9fff]+", text)
    for run in cjk_runs:
        for size in (1, 2, 3, 4):
            if len(run) < size:
                continue
            for index in range(0, len(run) - size + 1):
                tokens.add(run[index : index + size])
    return {token for token in tokens if token.strip()}


def _similarity(query: str, text: str) -> float:
    q = _tokenize(query)
    t = _tokenize(text)
    if not q or not t:
        return 0.0
    return len(q & t) / math.sqrt(len(q) * len(t))


def _record_context_similarity(query: str, record: "MemoryRecord") -> float:
    return max(
        _similarity(query, record.summary),
        0.82 * _similarity(query, record.text),
    )


ASSOCIATED_RECALL_CONTEXT_FLOOR = 0.08
ASSOCIATED_RECALL_CONTEXT_STOP_TOKENS = {
    "user",
    "users",
    "current",
    "message",
    "previous",
    "previously",
    "before",
    "the",
    "this",
    "that",
    "with",
    "more",
    "less",
    "and",
    "or",
    "is",
    "are",
    "was",
    "were",
    "has",
    "have",
    "had",
    "about",
    "liked",
    "likes",
    "like",
    "need",
    "needs",
    "正在",
    "当前",
    "消息",
    "用户",
    "之前",
    "喜欢",
    "需要",
}


def _associated_context_tokens(text: str) -> set[str]:
    tokens = _tokenize(text)
    return {
        token
        for token in tokens
        if token not in ASSOCIATED_RECALL_CONTEXT_STOP_TOKENS
        and not re.fullmatch(r"[\u4e00-\u9fff]", token)
    }


def _associated_context_similarity(query: str, text: str) -> float:
    q = _associated_context_tokens(query)
    t = _associated_context_tokens(text)
    if not q or not t:
        return 0.0
    return len(q & t) / math.sqrt(len(q) * len(t))


def _record_associated_context_similarity(
    query: str,
    record: "MemoryRecord",
) -> float:
    return max(
        _associated_context_similarity(query, record.summary),
        0.82 * _associated_context_similarity(query, record.text),
    )


def _latin_context_guard_applies(*parts: str) -> bool:
    text = " ".join(str(part or "") for part in parts)
    latin_chars = len(re.findall(r"[a-zA-Z]", text))
    cjk_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    return latin_chars > 0 and latin_chars >= cjk_chars


def normalize_embedding(raw: Any, *, limit: int = 4096) -> list[float]:
    if not isinstance(raw, (list, tuple)):
        return []
    values: list[float] = []
    for item in raw[:limit]:
        try:
            number = float(item)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            values.append(number)
    norm = math.sqrt(sum(value * value for value in values))
    if norm <= 1.0e-12:
        return []
    return [value / norm for value in values]


def clean_embedding(raw: Any, *, limit: int = 4096) -> list[float]:
    if not isinstance(raw, (list, tuple)):
        return []
    values: list[float] = []
    for item in raw[:limit]:
        try:
            number = float(item)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            values.append(number)
    return values


def embedding_cosine(first: Any, second: Any) -> float:
    left = normalize_embedding(first)
    right = normalize_embedding(second)
    if not left or not right or len(left) != len(right):
        return 0.0
    return clamp(sum(a * b for a, b in zip(left, right)))


def memory_embedding_text(record: "MemoryRecord") -> str:
    return _clip(
        " / ".join(
            part
            for part in (
                str(getattr(record, "summary", "") or "").strip(),
                str(getattr(record, "text", "") or "").strip(),
            )
            if part
        ),
        1200,
    )


def memory_embedding_text_hash(text: str) -> str:
    return sha1(_clean_text(text, 1200).encode("utf-8", errors="ignore")).hexdigest()[:16]


def memory_record_needs_embedding(
    record: "MemoryRecord",
    *,
    provider_id: str,
) -> bool:
    provider = str(provider_id or "").strip()
    if not provider:
        return False
    text = memory_embedding_text(record)
    if not text:
        return False
    return (
        not getattr(record, "semantic_embedding", None)
        or str(getattr(record, "embedding_provider_id", "") or "") != provider
        or str(getattr(record, "embedding_text_hash", "") or "")
        != memory_embedding_text_hash(text)
    )


def apply_memory_record_embedding(
    record: "MemoryRecord",
    embedding: Any,
    *,
    provider_id: str,
    now: float | None = None,
) -> bool:
    vector = normalize_embedding(embedding)
    provider = str(provider_id or "").strip()
    if not vector or not provider:
        return False
    text = memory_embedding_text(record)
    if not text:
        return False
    record.semantic_embedding = vector
    record.embedding_provider_id = provider
    record.embedding_updated_at = time.time() if now is None else float(now)
    record.embedding_text_hash = memory_embedding_text_hash(text)
    return True


@dataclass(slots=True)
class MemoryDynamics:
    salience_bias: float = 0.35
    relationship_weight: float = 0.35
    consolidation_gain: float = 0.35
    decay_half_life_seconds: float = 7 * 86400.0
    interference_sensitivity: float = 0.35
    compression_threshold: float = 0.55
    recall_limit: int = 3
    associative_recall_limit: int = 2
    recall_maturation_seconds: float = 2.0
    notes: list[str] = field(default_factory=lambda: ["auto_derived"])

    @classmethod
    def from_dict(cls, data: Any) -> "MemoryDynamics":
        if not isinstance(data, dict):
            return cls()
        return cls(
            salience_bias=clamp(data.get("salience_bias")),
            relationship_weight=clamp(data.get("relationship_weight")),
            consolidation_gain=clamp(data.get("consolidation_gain")),
            decay_half_life_seconds=max(
                3600.0,
                _as_float(data.get("decay_half_life_seconds"), 7 * 86400.0),
            ),
            interference_sensitivity=clamp(data.get("interference_sensitivity")),
            compression_threshold=clamp(data.get("compression_threshold")),
            recall_limit=max(1, min(5, int(_as_float(data.get("recall_limit"), 3)))),
            associative_recall_limit=max(
                0,
                min(2, int(_as_float(data.get("associative_recall_limit"), 2))),
            ),
            recall_maturation_seconds=max(
                0.0,
                min(20.0, _as_float(data.get("recall_maturation_seconds"), 2.0)),
            ),
            notes=_string_list(data.get("notes"), limit=8) or ["auto_derived"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "salience_bias": round(self.salience_bias, 6),
            "relationship_weight": round(self.relationship_weight, 6),
            "consolidation_gain": round(self.consolidation_gain, 6),
            "decay_half_life_seconds": round(self.decay_half_life_seconds, 6),
            "interference_sensitivity": round(self.interference_sensitivity, 6),
            "compression_threshold": round(self.compression_threshold, 6),
            "recall_limit": int(self.recall_limit),
            "associative_recall_limit": int(self.associative_recall_limit),
            "recall_maturation_seconds": round(self.recall_maturation_seconds, 6),
            "notes": list(self.notes[:8]),
        }


@dataclass(slots=True)
class MemoryRecord:
    text: str
    summary: str
    session_key: str
    memory_id: str = ""
    speaker_id: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    depth: float = 0.0
    confidence: float = 0.35
    layers: dict[str, float] = field(default_factory=dict)
    emotional_signature: dict[str, float] = field(default_factory=dict)
    relationship_signature: dict[str, Any] = field(default_factory=dict)
    evidence_count: int = 1
    recall_count: int = 0
    last_recalled_at: float = 0.0
    interference: float = 0.0
    associations: dict[str, float] = field(default_factory=dict)
    auto_parameters: dict[str, Any] = field(default_factory=dict)
    semantic_embedding: list[float] = field(default_factory=list)
    embedding_provider_id: str = ""
    embedding_updated_at: float = 0.0
    embedding_text_hash: str = ""

    @classmethod
    def from_dict(cls, data: Any) -> "MemoryRecord | None":
        if not isinstance(data, dict):
            return None
        text = _clean_text(data.get("text"), 1600)
        summary = _clean_text(data.get("summary"), 360) or _clip(text, 180)
        if not text and not summary:
            return None
        layers = {
            str(k): clamp(v)
            for k, v in (data.get("layers") or {}).items()
            if str(k).strip()
        } if isinstance(data.get("layers"), dict) else {}
        memory_id = str(data.get("memory_id") or "").strip()
        if not memory_id:
            memory_id = _make_memory_id(
                str(data.get("session_key") or "global"),
                summary or text,
                _as_float(data.get("created_at"), 0.0),
                str(data.get("speaker_id") or ""),
            )
        return cls(
            text=text or summary,
            summary=summary,
            session_key=str(data.get("session_key") or "global"),
            memory_id=memory_id,
            speaker_id=str(data.get("speaker_id") or ""),
            created_at=_as_float(data.get("created_at"), time.time()),
            updated_at=_as_float(data.get("updated_at"), time.time()),
            depth=clamp(data.get("depth")),
            confidence=clamp(data.get("confidence"), 0.0, 1.0),
            layers=layers,
            emotional_signature={
                str(k): signed_clamp(v)
                for k, v in (data.get("emotional_signature") or {}).items()
            } if isinstance(data.get("emotional_signature"), dict) else {},
            relationship_signature=dict(data.get("relationship_signature") or {})
            if isinstance(data.get("relationship_signature"), dict)
            else {},
            evidence_count=max(1, int(_as_float(data.get("evidence_count"), 1))),
            recall_count=max(0, int(_as_float(data.get("recall_count"), 0))),
            last_recalled_at=_as_float(data.get("last_recalled_at"), 0.0),
            interference=clamp(data.get("interference")),
            associations={
                str(k): clamp(v)
                for k, v in (data.get("associations") or {}).items()
                if str(k).strip()
            } if isinstance(data.get("associations"), dict) else {},
            auto_parameters=dict(data.get("auto_parameters") or {})
            if isinstance(data.get("auto_parameters"), dict)
            else {},
            semantic_embedding=clean_embedding(data.get("semantic_embedding")),
            embedding_provider_id=str(data.get("embedding_provider_id") or ""),
            embedding_updated_at=_as_float(data.get("embedding_updated_at"), 0.0),
            embedding_text_hash=str(data.get("embedding_text_hash") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "text": self.text[:1600],
            "summary": self.summary[:360],
            "session_key": self.session_key,
            "speaker_id": self.speaker_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "depth": round(clamp(self.depth), 6),
            "confidence": round(clamp(self.confidence), 6),
            "layers": {k: round(clamp(v), 6) for k, v in self.layers.items()},
            "emotional_signature": {
                k: round(signed_clamp(v), 6)
                for k, v in self.emotional_signature.items()
            },
            "relationship_signature": dict(self.relationship_signature),
            "evidence_count": int(self.evidence_count),
            "recall_count": int(self.recall_count),
            "last_recalled_at": self.last_recalled_at,
            "interference": round(clamp(self.interference), 6),
            "associations": {
                k: round(clamp(v), 6)
                for k, v in self.associations.items()
                if str(k).strip() and clamp(v) > 0.0
            },
            "auto_parameters": dict(self.auto_parameters),
            "semantic_embedding": [round(float(value), 8) for value in self.semantic_embedding],
            "embedding_provider_id": str(self.embedding_provider_id or ""),
            "embedding_updated_at": float(self.embedding_updated_at or 0.0),
            "embedding_text_hash": str(self.embedding_text_hash or ""),
        }


@dataclass(slots=True)
class SylanneMemoryState:
    records: list[MemoryRecord] = field(default_factory=list)
    dynamics: MemoryDynamics = field(default_factory=MemoryDynamics)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    compaction_summary: str = ""
    event_count: int = 0

    @classmethod
    def initial(cls, *, now: float | None = None) -> "SylanneMemoryState":
        timestamp = time.time() if now is None else float(now)
        return cls(created_at=timestamp, updated_at=timestamp)

    @classmethod
    def from_dict(cls, data: Any) -> "SylanneMemoryState":
        if not isinstance(data, dict):
            return cls.initial()
        records = []
        for item in data.get("records") or []:
            record = MemoryRecord.from_dict(item)
            if record is not None:
                records.append(record)
        now = time.time()
        return cls(
            records=records[-128:],
            dynamics=MemoryDynamics.from_dict(data.get("dynamics")),
            created_at=_as_float(data.get("created_at"), now),
            updated_at=_as_float(data.get("updated_at"), now),
            compaction_summary=str(data.get("compaction_summary") or "")[:1200],
            event_count=max(0, int(_as_float(data.get("event_count"), len(records)))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PUBLIC_MEMORY_STORE_SCHEMA_VERSION,
            "records": [record.to_dict() for record in self.records[-128:]],
            "dynamics": self.dynamics.to_dict(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "compaction_summary": self.compaction_summary[:1200],
            "event_count": int(self.event_count),
        }


@dataclass(slots=True)
class MemoryRecallItem:
    record: MemoryRecord
    score: float
    reasons: list[str] = field(default_factory=list)


def derive_memory_dynamics(
    *,
    emotion_snapshot: dict[str, Any] | None = None,
    personality_drift_snapshot: dict[str, Any] | None = None,
    lifelike_snapshot: dict[str, Any] | None = None,
    group_atmosphere_snapshot: dict[str, Any] | None = None,
    now: float | None = None,
) -> MemoryDynamics:
    del now
    emotion_values = _values(emotion_snapshot)
    lifelike_values = _values(lifelike_snapshot)
    group_values = _values(group_atmosphere_snapshot)
    drift_values = _values(personality_drift_snapshot)
    trait_offsets = (
        personality_drift_snapshot.get("trait_offsets")
        if isinstance(personality_drift_snapshot, dict)
        else {}
    )
    trait_offsets = trait_offsets if isinstance(trait_offsets, dict) else {}

    valence = signed_clamp(emotion_values.get("valence", 0.0))
    arousal = clamp(abs(emotion_values.get("arousal", 0.0)))
    affiliation = signed_clamp(emotion_values.get("affiliation", 0.0))
    certainty = clamp(abs(emotion_values.get("certainty", 0.0)))
    confidence = clamp(_nested(emotion_snapshot, "emotion", "confidence"), 0.0, 1.0)
    rapport = clamp(lifelike_values.get("rapport", 0.0))
    common_ground = clamp(lifelike_values.get("common_ground", 0.0))
    preference_confidence = clamp(lifelike_values.get("preference_confidence", 0.0))
    boundary_sensitivity = clamp(lifelike_values.get("boundary_sensitivity", 0.0))
    drift_intensity = clamp(drift_values.get("drift_intensity", 0.0))
    anchor_strength = clamp(drift_values.get("anchor_strength", 1.0))
    relationship_sensitivity = clamp(drift_values.get("relationship_sensitivity", 0.0))
    neuroticism = clamp(abs(_as_float(trait_offsets.get("neuroticism"), 0.0)))
    attachment = clamp(abs(_as_float(trait_offsets.get("attachment_anxiety"), 0.0)))
    regulation_gap = clamp(max(0.0, -_as_float(
        trait_offsets.get("emotion_regulation_capacity"),
        0.0,
    )))
    tension = clamp(group_values.get("tension", 0.0))
    interruption = clamp(group_values.get("interrupt_risk", 0.0))
    conflict_cause = str(
        _nested(emotion_snapshot, "relationship", "conflict_analysis", "cause") or "",
    )
    relationship_decision = str(_nested(emotion_snapshot, "relationship", "decision") or "")
    conflict_bonus = 0.18 if conflict_cause or relationship_decision in {
        "boundary",
        "repair",
        "clarify",
    } else 0.0

    salience = clamp(
        0.18
        + 0.24 * arousal
        + 0.18 * abs(valence)
        + 0.16 * confidence
        + 0.12 * certainty
        + conflict_bonus,
    )
    relationship = clamp(
        0.14
        + 0.25 * rapport
        + 0.20 * common_ground
        + 0.16 * max(0.0, abs(affiliation))
        + 0.14 * relationship_sensitivity
        + 0.11 * boundary_sensitivity,
    )
    consolidation = clamp(
        0.16
        + 0.22 * salience
        + 0.20 * relationship
        + 0.14 * preference_confidence
        + 0.12 * anchor_strength
        + 0.08 * drift_intensity,
    )
    decay_days = 2.0 + 24.0 * consolidation + 8.0 * relationship + 5.0 * common_ground
    decay_days *= 1.0 + 0.45 * neuroticism + 0.35 * attachment
    decay_days *= 1.0 + 0.25 * regulation_gap
    decay_days = max(0.5, min(60.0, decay_days))
    interference = clamp(0.18 + 0.28 * tension + 0.22 * interruption + 0.18 * (1.0 - certainty))
    compression_threshold = clamp(0.38 + 0.28 * consolidation + 0.18 * common_ground)
    recall_limit = int(round(2 + 3 * clamp(0.45 * relationship + 0.35 * salience + 0.20 * common_ground)))
    recall_limit = max(2, min(5, recall_limit))
    associative_recall_limit = int(round(2 * clamp(0.50 * common_ground + 0.30 * relationship + 0.20 * consolidation)))
    associative_recall_limit = max(0, min(2, associative_recall_limit))
    recall_maturation_seconds = clamp(
        0.8
        + 3.6 * interference
        + 2.4 * tension
        + 1.8 * interruption
        + 1.2 * (1.0 - certainty)
        - 1.4 * consolidation,
        0.0,
        12.0,
    )

    return MemoryDynamics(
        salience_bias=salience,
        relationship_weight=relationship,
        consolidation_gain=consolidation,
        decay_half_life_seconds=decay_days * 86400.0,
        interference_sensitivity=interference,
        compression_threshold=compression_threshold,
        recall_limit=recall_limit,
        associative_recall_limit=associative_recall_limit,
        recall_maturation_seconds=recall_maturation_seconds,
        notes=[
            "auto_derived",
            "personality_to_memory_dynamics",
            "real_time_decay",
            "associative_memory_budgeted",
            "no_user_tunable_core_parameters",
        ],
    )


def observe_memory_event(
    state: SylanneMemoryState,
    *,
    text: str,
    session_key: str,
    speaker_id: str = "",
    emotion_snapshot: dict[str, Any] | None = None,
    personality_drift_snapshot: dict[str, Any] | None = None,
    lifelike_snapshot: dict[str, Any] | None = None,
    group_atmosphere_snapshot: dict[str, Any] | None = None,
    now: float | None = None,
) -> SylanneMemoryState:
    timestamp = time.time() if now is None else float(now)
    text = _clean_text(text, 1600)
    if not text:
        return state
    dynamics = derive_memory_dynamics(
        emotion_snapshot=emotion_snapshot,
        personality_drift_snapshot=personality_drift_snapshot,
        lifelike_snapshot=lifelike_snapshot,
        group_atmosphere_snapshot=group_atmosphere_snapshot,
        now=timestamp,
    )
    summary = _summarize_memory_text(text)
    layers = _derive_layers(
        text,
        dynamics=dynamics,
        emotion_snapshot=emotion_snapshot,
        lifelike_snapshot=lifelike_snapshot,
    )
    depth = clamp(
        0.16
        + 0.28 * dynamics.salience_bias
        + 0.24 * dynamics.relationship_weight
        + 0.22 * dynamics.consolidation_gain
        + 0.10 * max(layers.values() or [0.0]),
    )
    confidence = clamp(
        0.28
        + 0.30 * dynamics.consolidation_gain
        + 0.18 * (_nested(emotion_snapshot, "emotion", "confidence") or 0.0)
        + 0.12 * len(text) / 280.0,
    )
    record = MemoryRecord(
        text=text,
        summary=summary,
        session_key=str(session_key or "global"),
        memory_id=_make_memory_id(
            str(session_key or "global"),
            summary,
            timestamp,
            str(speaker_id or ""),
        ),
        speaker_id=str(speaker_id or ""),
        created_at=timestamp,
        updated_at=timestamp,
        depth=depth,
        confidence=confidence,
        layers=layers,
        emotional_signature=_values(emotion_snapshot),
        relationship_signature={
            "decision": _nested(emotion_snapshot, "relationship", "decision") or "",
            "cause": _nested(
                emotion_snapshot,
                "relationship",
                "conflict_analysis",
                "cause",
            )
            or "",
        },
        auto_parameters=dynamics.to_dict(),
    )
    existing = _find_merge_candidate(state.records, record)
    if existing is not None:
        mix = clamp(0.25 + 0.35 * dynamics.consolidation_gain)
        existing.text = _clip(existing.text + " / " + text, 1600)
        existing.summary = _summarize_memory_text(existing.text)
        existing.updated_at = timestamp
        existing.evidence_count += 1
        existing.depth = clamp(existing.depth + mix * (depth - existing.depth) + 0.08)
        existing.confidence = clamp(existing.confidence + mix * (confidence - existing.confidence) + 0.05)
        existing.layers = _merge_layer_weights(existing.layers, layers, mix=mix)
        existing.auto_parameters = dynamics.to_dict()
        target = existing
    else:
        state.records.append(record)
        target = record
    _refresh_memory_associations(
        state.records,
        target,
        dynamics=dynamics,
        now=timestamp,
    )
    state.records = _compact_records(state.records, dynamics=dynamics, now=timestamp)
    state.dynamics = dynamics
    state.updated_at = timestamp
    state.event_count += 1
    return state


def recall_memory(
    state: SylanneMemoryState,
    *,
    query: str,
    now: float | None = None,
    limit: int | None = None,
    query_embedding: Any = None,
    embedding_provider_id: str = "",
) -> list[MemoryRecallItem]:
    timestamp = time.time() if now is None else float(now)
    query = _clean_text(query, 900)
    if not query:
        return []
    recall_limit = max(1, min(5, int(limit or state.dynamics.recall_limit or 3)))
    associative_limit = max(0, min(2, int(state.dynamics.associative_recall_limit)))
    normalized_query_embedding = normalize_embedding(query_embedding)
    embedding_provider_id = str(embedding_provider_id or "").strip()
    items: list[MemoryRecallItem] = []
    for record in state.records:
        elapsed = max(0.0, timestamp - record.updated_at)
        freshness = half_life_multiplier(
            elapsed,
            _as_float(
                record.auto_parameters.get("decay_half_life_seconds"),
                state.dynamics.decay_half_life_seconds,
            ),
        )
        semantic = _record_context_similarity(query, record)
        vector_semantic = 0.0
        if (
            normalized_query_embedding
            and embedding_provider_id
            and str(record.embedding_provider_id or "") == embedding_provider_id
            and record.semantic_embedding
        ):
            vector_semantic = embedding_cosine(
                normalized_query_embedding,
                record.semantic_embedding,
            )
            if vector_semantic > 0.0:
                semantic = max(
                    semantic,
                    clamp(0.66 * vector_semantic + 0.34 * semantic),
                )
        if semantic <= 0.0:
            continue
        score = clamp(
            0.42 * semantic
            + 0.24 * record.depth
            + 0.18 * record.confidence
            + 0.16 * freshness
            - 0.22 * record.interference,
        )
        if score <= 0.08:
            continue
        reasons = []
        if semantic > 0.1:
            reasons.append("semantic_match")
        if vector_semantic > 0.22:
            reasons.append("vector_match")
        if record.depth > 0.55:
            reasons.append("deep_memory")
        if freshness > 0.4:
            reasons.append("real_time_fresh")
        items.append(MemoryRecallItem(record=record, score=score, reasons=reasons))
    items.sort(key=lambda item: item.score, reverse=True)
    primary = items[:recall_limit]
    if not primary or associative_limit <= 0:
        return primary
    associated = _associated_recall_items(
        state.records,
        primary,
        query=query,
        now=timestamp,
        limit=associative_limit,
        state=state,
    )
    combined = primary + associated
    combined.sort(key=lambda item: item.score, reverse=True)
    return combined[: recall_limit + associative_limit]


def reinforce_recalled_memories(
    state: SylanneMemoryState,
    items: list[MemoryRecallItem],
    *,
    query: str = "",
    now: float | None = None,
) -> SylanneMemoryState:
    """Strengthen memories after they are actually recalled into context."""
    if not items:
        return state
    timestamp = time.time() if now is None else float(now)
    query = _clean_text(query, 900)
    by_id = {id(item.record): item for item in items}
    for record in state.records:
        item = by_id.get(id(record))
        if item is None:
            continue
        semantic = max(
            _similarity(query, record.summary),
            0.82 * _similarity(query, record.text),
        ) if query else 0.0
        retrieval_gain = clamp(
            0.018
            + 0.050 * item.score
            + 0.028 * semantic
            + 0.018 * state.dynamics.consolidation_gain,
            0.0,
            0.12,
        )
        record.recall_count += 1
        record.last_recalled_at = timestamp
        record.depth = clamp(record.depth + retrieval_gain * (1.0 - record.depth))
        record.confidence = clamp(
            record.confidence + 0.72 * retrieval_gain * (1.0 - record.confidence),
        )
        record.interference = clamp(
            record.interference * (1.0 - 0.35 * retrieval_gain),
        )
        params = dict(record.auto_parameters or {})
        params["retrieval_reinforcement"] = {
            "last_query_excerpt": _clip(query, 120),
            "last_score": round(clamp(item.score), 6),
            "gain": round(retrieval_gain, 6),
            "updated_at": timestamp,
        }
        params["last_decay_at"] = timestamp
        record.auto_parameters = params
    state.updated_at = max(state.updated_at, timestamp)
    return state


def apply_memory_time_decay(
    state: SylanneMemoryState,
    *,
    now: float | None = None,
    hard_limit: int = 128,
) -> SylanneMemoryState:
    """Apply real-time forgetting and prune weak stale memories."""
    timestamp = time.time() if now is None else float(now)
    kept: list[MemoryRecord] = []
    forgotten = 0
    changed = False
    for record in state.records:
        params = dict(record.auto_parameters or {})
        last_decay_at = _as_float(params.get("last_decay_at"), record.updated_at)
        elapsed = max(0.0, timestamp - last_decay_at)
        half_life = _as_float(
            params.get("decay_half_life_seconds"),
            state.dynamics.decay_half_life_seconds,
        )
        retention = half_life_multiplier(elapsed, half_life)
        consolidation = clamp(
            0.46 * record.depth
            + 0.26 * record.confidence
            + 0.16 * min(1.0, record.evidence_count / 4.0)
            + 0.12 * min(1.0, record.recall_count / 5.0),
        )
        survival = clamp(0.34 * retention + 0.66 * consolidation)
        if survival < 0.12 and record.evidence_count <= 1 and record.recall_count <= 0:
            forgotten += 1
            changed = True
            continue
        decay_pressure = clamp(1.0 - retention)
        if decay_pressure > 0.0001:
            record.depth = clamp(
                record.depth * (1.0 - 0.18 * decay_pressure * (1.0 - consolidation)),
            )
            record.confidence = clamp(
                record.confidence * (1.0 - 0.14 * decay_pressure * (1.0 - consolidation)),
            )
            record.interference = clamp(
                record.interference
                + state.dynamics.interference_sensitivity * 0.035 * decay_pressure,
            )
            params["last_decay_at"] = timestamp
            record.auto_parameters = params
            changed = True
        kept.append(record)
    compacted = _compact_records(kept, dynamics=state.dynamics, now=timestamp, hard_limit=hard_limit)
    if len(compacted) != len(kept):
        changed = True
    state.records = compacted
    notes = [note for note in state.dynamics.notes if not note.startswith("forgotten=")]
    if forgotten:
        notes.append(f"forgotten={forgotten}")
        changed = True
    state.dynamics.notes = notes[:8]
    if changed:
        state.updated_at = max(state.updated_at, timestamp)
    return state


def build_memory_prompt_fragment(
    items: list[MemoryRecallItem],
    *,
    session_key: str,
    max_chars: int = 720,
) -> str:
    if not items or max_chars <= 0:
        return ""
    lines = [
        "[sylanne_memory_recall]",
        "以下是 Sylanne 自有记忆模块的限长召回摘要，用来理解指代、偏好、共同经历和相处方式；当前连续用户意图、打断断点和正在发生的上下文优先，记忆只作旁注补充，若冲突应忽略记忆。",
        f"session_key={_clip(str(session_key or 'global'), 80)}; result_count={min(len(items), 5)}",
    ]
    for index, item in enumerate(items[:5], 1):
        record = item.record
        lines.append(
            f"{index}. {_clip(record.summary or record.text, 190)}"
            f" | depth={record.depth:.2f}, score={item.score:.2f}"
        )
    return _clip("\n".join(lines), max_chars)


def _summarize_memory_text(text: str) -> str:
    text = _clean_text(text, 360)
    for sep in ("。", "！", "？", ".", "!", "?"):
        if sep in text:
            head = text.split(sep, 1)[0].strip()
            if 8 <= len(head) <= 180:
                return head + sep
    return _clip(text, 180)


def _derive_layers(
    text: str,
    *,
    dynamics: MemoryDynamics,
    emotion_snapshot: dict[str, Any] | None,
    lifelike_snapshot: dict[str, Any] | None,
) -> dict[str, float]:
    values = _values(lifelike_snapshot)
    emotion_values = _values(emotion_snapshot)
    has_preference = bool(re.search(r"喜欢|讨厌|希望|不要|偏好|习惯|想要|不想", text))
    has_event = bool(re.search(r"刚才|昨天|今天|以后|之前|解释|发生|说过|做了", text))
    has_relation = bool(re.search(r"你|我|我们|关系|用户|群|男朋友|朋友|道歉|误会", text))
    return {
        "episodic": clamp(0.22 + 0.38 * has_event + 0.20 * dynamics.salience_bias),
        "semantic": clamp(0.18 + 0.36 * has_preference + 0.18 * values.get("common_ground", 0.0)),
        "relationship": clamp(0.16 + 0.40 * has_relation + 0.20 * dynamics.relationship_weight),
        "policy": clamp(0.12 + 0.30 * has_preference + 0.14 * abs(emotion_values.get("control", 0.0))),
    }


def _make_memory_id(
    session_key: str,
    summary: str,
    created_at: float,
    speaker_id: str = "",
) -> str:
    seed = f"{session_key}|{speaker_id}|{created_at:.6f}|{summary[:240]}"
    return sha1(seed.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _find_merge_candidate(
    records: list[MemoryRecord],
    record: MemoryRecord,
) -> MemoryRecord | None:
    for existing in reversed(records[-16:]):
        if existing.session_key != record.session_key:
            continue
        if _similarity(existing.summary, record.summary) >= 0.62:
            return existing
    return None


def _refresh_memory_associations(
    records: list[MemoryRecord],
    target: MemoryRecord,
    *,
    dynamics: MemoryDynamics,
    now: float,
    window: int = 24,
    per_record_limit: int = 3,
) -> None:
    if not target.memory_id:
        target.memory_id = _make_memory_id(
            target.session_key,
            target.summary or target.text,
            target.created_at,
            target.speaker_id,
        )
    candidates = []
    for other in records[-window:]:
        if other is target or other.session_key != target.session_key:
            continue
        if not other.memory_id:
            other.memory_id = _make_memory_id(
                other.session_key,
                other.summary or other.text,
                other.created_at,
                other.speaker_id,
            )
        weight = _association_weight(
            target,
            other,
            dynamics=dynamics,
            now=now,
        )
        if weight >= 0.24:
            candidates.append((weight, other))
    candidates.sort(key=lambda item: item[0], reverse=True)
    target.associations = {
        other.memory_id: round(weight, 6)
        for weight, other in candidates[:per_record_limit]
    }
    for weight, other in candidates[:per_record_limit]:
        merged = dict(other.associations or {})
        merged[target.memory_id] = max(clamp(weight * 0.92), clamp(merged.get(target.memory_id, 0.0)))
        sorted_edges = sorted(merged.items(), key=lambda item: clamp(item[1]), reverse=True)
        other.associations = {
            str(memory_id): round(clamp(edge_weight), 6)
            for memory_id, edge_weight in sorted_edges[:per_record_limit]
            if str(memory_id).strip() and str(memory_id) != other.memory_id
        }


def _association_weight(
    first: MemoryRecord,
    second: MemoryRecord,
    *,
    dynamics: MemoryDynamics,
    now: float,
) -> float:
    semantic = max(
        _similarity(first.summary, second.summary),
        0.78 * _similarity(first.text, second.text),
    )
    shared_layers = set(first.layers) & set(second.layers)
    layer_overlap = 0.0
    if shared_layers:
        layer_overlap = sum(
            min(clamp(first.layers.get(key)), clamp(second.layers.get(key)))
            for key in shared_layers
        ) / max(1, len(shared_layers))
    emotional_keys = set(first.emotional_signature) & set(second.emotional_signature)
    emotional_proximity = 0.0
    if emotional_keys:
        distance = sum(
            abs(first.emotional_signature.get(key, 0.0) - second.emotional_signature.get(key, 0.0))
            for key in emotional_keys
        ) / max(1, len(emotional_keys))
        emotional_proximity = clamp(1.0 - distance / 2.0)
    temporal = half_life_multiplier(
        abs(first.updated_at - second.updated_at),
        max(3600.0, dynamics.decay_half_life_seconds * 0.18),
    )
    consolidation = clamp(
        0.5 * min(first.depth, second.depth)
        + 0.3 * min(first.confidence, second.confidence)
        + 0.2 * dynamics.consolidation_gain,
    )
    return clamp(
        0.34 * semantic
        + 0.24 * layer_overlap
        + 0.16 * emotional_proximity
        + 0.14 * temporal
        + 0.12 * consolidation,
    )


def _associated_recall_items(
    records: list[MemoryRecord],
    primary: list[MemoryRecallItem],
    *,
    query: str,
    now: float,
    limit: int,
    state: SylanneMemoryState,
) -> list[MemoryRecallItem]:
    del now
    if limit <= 0:
        return []
    by_id = {
        record.memory_id: record
        for record in records
        if record.memory_id
    }
    used_ids = {item.record.memory_id for item in primary if item.record.memory_id}
    candidates: dict[str, MemoryRecallItem] = {}
    for parent in primary:
        parent_id = parent.record.memory_id
        if not parent_id:
            continue
        for target_id, weight in sorted(
            (parent.record.associations or {}).items(),
            key=lambda item: clamp(item[1]),
            reverse=True,
        ):
            if target_id in used_ids:
                continue
            record = by_id.get(target_id)
            if record is None or record.session_key != parent.record.session_key:
                continue
            association = clamp(weight)
            if association < 0.24:
                continue
            context_query = _associated_context_query(query, parent.record)
            context_semantic = _record_context_similarity(context_query, record)
            filtered_context_semantic = _record_associated_context_similarity(
                context_query,
                record,
            )
            if context_query and context_semantic < ASSOCIATED_RECALL_CONTEXT_FLOOR:
                continue
            if (
                _latin_context_guard_applies(context_query, record.summary, record.text)
                and filtered_context_semantic < ASSOCIATED_RECALL_CONTEXT_FLOOR
            ):
                continue
            context_semantic = max(context_semantic, filtered_context_semantic)
            score = _associated_recall_score(
                parent=parent,
                association=association,
                record=record,
                dynamics=state.dynamics,
                context_semantic=context_semantic,
            )
            if score <= 0.08:
                continue
            existing = candidates.get(target_id)
            if existing is None or score > existing.score:
                candidates[target_id] = MemoryRecallItem(
                    record=record,
                    score=score,
                    reasons=[
                        "associative_recall",
                        "context_link",
                        f"linked_from={parent_id}",
                    ],
                )
    selected = sorted(candidates.values(), key=lambda item: item.score, reverse=True)
    return selected[:limit]


def _associated_context_query(query: str, parent: MemoryRecord) -> str:
    return "\n".join(
        part
        for part in (
            query,
            parent.summary,
            parent.text,
        )
        if part
    )


def _associated_recall_score(
    *,
    parent: MemoryRecallItem,
    association: float,
    record: MemoryRecord,
    dynamics: MemoryDynamics,
    context_semantic: float,
) -> float:
    return clamp(
        parent.score
        * (0.42 + 0.20 * dynamics.consolidation_gain)
        * association
        + 0.12 * context_semantic
        + 0.10 * record.depth
        + 0.06 * record.confidence
        - 0.14 * record.interference,
    )


def _prune_memory_associations(records: list[MemoryRecord]) -> None:
    existing_ids = {
        record.memory_id
        for record in records
        if record.memory_id
    }
    for record in records:
        if not record.memory_id:
            record.memory_id = _make_memory_id(
                record.session_key,
                record.summary or record.text,
                record.created_at,
                record.speaker_id,
            )
            existing_ids.add(record.memory_id)
        record.associations = {
            str(memory_id): clamp(weight)
            for memory_id, weight in (record.associations or {}).items()
            if str(memory_id) in existing_ids
            and str(memory_id) != record.memory_id
            and clamp(weight) > 0.0
        }


def _merge_layer_weights(
    old: dict[str, float],
    new: dict[str, float],
    *,
    mix: float,
) -> dict[str, float]:
    keys = set(old) | set(new)
    return {
        key: clamp((1.0 - mix) * old.get(key, 0.0) + mix * new.get(key, 0.0))
        for key in keys
    }


def _compact_records(
    records: list[MemoryRecord],
    *,
    dynamics: MemoryDynamics,
    now: float,
    hard_limit: int = 128,
) -> list[MemoryRecord]:
    if len(records) <= hard_limit:
        _prune_memory_associations(records)
        return records
    scored = []
    for record in records:
        freshness = half_life_multiplier(
            max(0.0, now - record.updated_at),
            _as_float(
                record.auto_parameters.get("decay_half_life_seconds"),
                dynamics.decay_half_life_seconds,
            ),
        )
        keep_score = 0.45 * record.depth + 0.25 * record.confidence + 0.20 * freshness + 0.10 * min(1.0, record.evidence_count / 4)
        scored.append((keep_score, record))
    scored.sort(key=lambda item: item[0], reverse=True)
    compacted = [record for _, record in scored[:hard_limit]]
    _prune_memory_associations(compacted)
    return compacted


def _string_list(value: Any, *, limit: int = 8) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, (list, tuple, set)) else [value]
    result: list[str] = []
    for item in items:
        text = _clean_text(item, 120)
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result
