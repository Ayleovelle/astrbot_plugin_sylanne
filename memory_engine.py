from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
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


@dataclass(slots=True)
class MemoryDynamics:
    salience_bias: float = 0.35
    relationship_weight: float = 0.35
    consolidation_gain: float = 0.35
    decay_half_life_seconds: float = 7 * 86400.0
    interference_sensitivity: float = 0.35
    compression_threshold: float = 0.55
    recall_limit: int = 3
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
            "recall_maturation_seconds": round(self.recall_maturation_seconds, 6),
            "notes": list(self.notes[:8]),
        }


@dataclass(slots=True)
class MemoryRecord:
    text: str
    summary: str
    session_key: str
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
    auto_parameters: dict[str, Any] = field(default_factory=dict)

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
        return cls(
            text=text or summary,
            summary=summary,
            session_key=str(data.get("session_key") or "global"),
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
            auto_parameters=dict(data.get("auto_parameters") or {})
            if isinstance(data.get("auto_parameters"), dict)
            else {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
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
            "auto_parameters": dict(self.auto_parameters),
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
        recall_maturation_seconds=recall_maturation_seconds,
        notes=[
            "auto_derived",
            "personality_to_memory_dynamics",
            "real_time_decay",
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
    else:
        state.records.append(record)
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
) -> list[MemoryRecallItem]:
    timestamp = time.time() if now is None else float(now)
    query = _clean_text(query, 900)
    if not query:
        return []
    recall_limit = max(1, min(5, int(limit or state.dynamics.recall_limit or 3)))
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
        semantic = max(
            _similarity(query, record.summary),
            0.82 * _similarity(query, record.text),
        )
        if semantic <= 0 and record.depth < 0.72:
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
        if record.depth > 0.55:
            reasons.append("deep_memory")
        if freshness > 0.4:
            reasons.append("real_time_fresh")
        items.append(MemoryRecallItem(record=record, score=score, reasons=reasons))
    items.sort(key=lambda item: item.score, reverse=True)
    return items[:recall_limit]


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
        "以下是 Sylanne 自有记忆模块的限长召回摘要，用来理解指代、偏好、共同经历和相处方式；不要逐字复述，也不要把它当作用户刚刚亲口说的话。",
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
    return [record for _, record in scored[:hard_limit]]


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
