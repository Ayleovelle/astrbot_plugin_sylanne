from __future__ import annotations

import math
import re
import time
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

try:
    from .emotion_engine import (
        DIMENSIONS,
        PERSONALITY_TRAIT_DIMENSIONS,
        PersonaProfile,
        clamp as emotion_clamp,
    )
except ImportError:
    from emotion_engine import (
        DIMENSIONS,
        PERSONALITY_TRAIT_DIMENSIONS,
        PersonaProfile,
        clamp as emotion_clamp,
    )


PUBLIC_PERSONALITY_DRIFT_SCHEMA_VERSION = "astrbot.personality_drift_state.v1"

DEFAULT_PERSONALITY_DRIFT_VALUES: dict[str, float] = {
    "drift_intensity": 0.0,
    "anchor_strength": 1.0,
    "event_consolidation": 0.0,
    "relationship_sensitivity": 0.0,
    "time_gate": 1.0,
}

PERSONALITY_DRIFT_NOTES = [
    "runtime_session_adaptation",
    "real_elapsed_time_decay",
    "bounded_offsets_not_persona_rewrite",
    "not_clinical_personality_assessment",
]


def clamp(value: Any, lower: float = 0.0, upper: float = 1.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = lower
    return max(lower, min(upper, number))


def signed_clamp(value: Any, magnitude: float = 1.0) -> float:
    return clamp(value, -abs(magnitude), abs(magnitude))


def half_life_multiplier(elapsed_seconds: float, half_life_seconds: float) -> float:
    if elapsed_seconds <= 0:
        return 1.0
    if half_life_seconds <= 0:
        return 0.0
    return clamp(2.0 ** (-elapsed_seconds / half_life_seconds))


def real_time_gate(elapsed_seconds: float, gate_half_life_seconds: float) -> float:
    if elapsed_seconds <= 0:
        return 0.0
    if gate_half_life_seconds <= 0:
        return 1.0
    return clamp(1.0 - 2.0 ** (-elapsed_seconds / gate_half_life_seconds))


@dataclass(slots=True)
class PersonalityDriftObservation:
    text: str = ""
    trait_impulses: dict[str, float] = field(default_factory=dict)
    intensity: float = 0.0
    reliability: float = 0.35
    relationship_importance: float = 0.0
    event_type: str = "low_signal"
    source: str = "heuristic"
    reason: str = ""
    flags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Any) -> "PersonalityDriftObservation":
        if not isinstance(data, dict):
            return cls()
        raw_impulses = data.get("trait_impulses")
        impulses: dict[str, float] = {}
        if isinstance(raw_impulses, dict):
            for key, value in raw_impulses.items():
                if key in PERSONALITY_TRAIT_DIMENSIONS:
                    impulses[key] = signed_clamp(value)
        return cls(
            text=str(data.get("text") or "")[:1000],
            trait_impulses=impulses,
            intensity=clamp(data.get("intensity")),
            reliability=clamp(data.get("reliability"), 0.0, 1.0),
            relationship_importance=clamp(data.get("relationship_importance")),
            event_type=str(data.get("event_type") or "external"),
            source=str(data.get("source") or "plugin"),
            reason=str(data.get("reason") or "")[:240],
            flags=_string_list(data.get("flags"), limit=12),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text[:1000],
            "trait_impulses": {
                key: round(signed_clamp(value), 6)
                for key, value in self.trait_impulses.items()
                if key in PERSONALITY_TRAIT_DIMENSIONS
            },
            "intensity": round(clamp(self.intensity), 6),
            "reliability": round(clamp(self.reliability), 6),
            "relationship_importance": round(clamp(self.relationship_importance), 6),
            "event_type": self.event_type,
            "source": self.source,
            "reason": self.reason[:240],
            "flags": list(self.flags[:12]),
        }


@dataclass(slots=True)
class PersonalityDriftState:
    trait_offsets: dict[str, float] = field(
        default_factory=lambda: {key: 0.0 for key in PERSONALITY_TRAIT_DIMENSIONS},
    )
    trait_confidence: dict[str, float] = field(
        default_factory=lambda: {key: 0.0 for key in PERSONALITY_TRAIT_DIMENSIONS},
    )
    values: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_PERSONALITY_DRIFT_VALUES),
    )
    persona_fingerprint: str = "default"
    evidence_count: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_event_summary: str = ""
    flags: list[str] = field(default_factory=list)
    trajectory: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def initial(
        cls,
        *,
        persona_fingerprint: str = "default",
        now: float | None = None,
    ) -> "PersonalityDriftState":
        timestamp = time.time() if now is None else float(now)
        return cls(
            persona_fingerprint=str(persona_fingerprint or "default"),
            created_at=timestamp,
            updated_at=timestamp,
        )

    @classmethod
    def from_dict(cls, data: Any) -> "PersonalityDriftState":
        if not isinstance(data, dict):
            return cls.initial()
        offsets = {key: 0.0 for key in PERSONALITY_TRAIT_DIMENSIONS}
        raw_offsets = data.get("trait_offsets")
        if isinstance(raw_offsets, dict):
            for key, value in raw_offsets.items():
                if key in offsets:
                    offsets[key] = signed_clamp(value)
        confidence = {key: 0.0 for key in PERSONALITY_TRAIT_DIMENSIONS}
        raw_confidence = data.get("trait_confidence")
        if isinstance(raw_confidence, dict):
            for key, value in raw_confidence.items():
                if key in confidence:
                    confidence[key] = clamp(value)
        values = dict(DEFAULT_PERSONALITY_DRIFT_VALUES)
        raw_values = data.get("values")
        if isinstance(raw_values, dict):
            for key, value in raw_values.items():
                if key in values:
                    values[key] = clamp(value)
        now = time.time()
        return cls(
            trait_offsets=offsets,
            trait_confidence=confidence,
            values=values,
            persona_fingerprint=str(data.get("persona_fingerprint") or "default"),
            evidence_count=max(0, int(_as_float(data.get("evidence_count"), 0.0))),
            created_at=_as_float(data.get("created_at"), now),
            updated_at=_as_float(data.get("updated_at"), now),
            last_event_summary=str(data.get("last_event_summary") or "")[:240],
            flags=_string_list(data.get("flags"), limit=16),
            trajectory=_normalize_trajectory(data.get("trajectory")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PUBLIC_PERSONALITY_DRIFT_SCHEMA_VERSION,
            "trait_offsets": {
                key: round(self.trait_offsets.get(key, 0.0), 6)
                for key in PERSONALITY_TRAIT_DIMENSIONS
            },
            "trait_confidence": {
                key: round(self.trait_confidence.get(key, 0.0), 6)
                for key in PERSONALITY_TRAIT_DIMENSIONS
            },
            "values": {
                key: round(self.values.get(key, DEFAULT_PERSONALITY_DRIFT_VALUES[key]), 6)
                for key in DEFAULT_PERSONALITY_DRIFT_VALUES
            },
            "persona_fingerprint": self.persona_fingerprint,
            "evidence_count": self.evidence_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_event_summary": self.last_event_summary[:240],
            "flags": list(self.flags[:16]),
            "trajectory": list(self.trajectory[-80:]),
        }

    def to_public_dict(
        self,
        *,
        session_key: str | None = None,
        exposure: str = "plugin_safe",
    ) -> dict[str, Any]:
        return personality_drift_state_to_public_payload(
            self,
            session_key=session_key,
            exposure=exposure,
        )


@dataclass(slots=True)
class PersonalityDriftParameters:
    state_half_life_seconds: float = 7776000.0
    rapid_update_half_life_seconds: float = 86400.0
    min_update_interval_seconds: float = 21600.0
    learning_rate: float = 0.055
    event_threshold: float = 0.12
    max_impulse_per_update: float = 0.015
    max_trait_offset: float = 0.22
    confidence_growth: float = 0.10
    trajectory_limit: int = 80


class PersonalityDriftEngine:
    def __init__(self, parameters: PersonalityDriftParameters | None = None) -> None:
        self.parameters = parameters or PersonalityDriftParameters()

    def passive_update(
        self,
        previous: PersonalityDriftState | None,
        *,
        persona_fingerprint: str = "default",
        now: float | None = None,
    ) -> PersonalityDriftState:
        now = time.time() if now is None else float(now)
        previous = previous or PersonalityDriftState.initial(
            persona_fingerprint=persona_fingerprint,
            now=now,
        )
        if previous.persona_fingerprint != str(persona_fingerprint or "default"):
            return PersonalityDriftState.initial(
                persona_fingerprint=persona_fingerprint,
                now=now,
            )
        elapsed = max(0.0, now - previous.updated_at)
        decay = half_life_multiplier(elapsed, self.parameters.state_half_life_seconds)
        offsets = {
            key: signed_clamp(
                previous.trait_offsets.get(key, 0.0) * decay,
                self.parameters.max_trait_offset,
            )
            for key in PERSONALITY_TRAIT_DIMENSIONS
        }
        confidence = {
            key: clamp(previous.trait_confidence.get(key, 0.0) * decay)
            for key in PERSONALITY_TRAIT_DIMENSIONS
        }
        values = _derive_values(
            offsets,
            confidence,
            time_gate=real_time_gate(
                elapsed,
                self.parameters.rapid_update_half_life_seconds,
            ),
        )
        return PersonalityDriftState(
            trait_offsets=offsets,
            trait_confidence=confidence,
            values=values,
            persona_fingerprint=previous.persona_fingerprint,
            evidence_count=previous.evidence_count,
            created_at=previous.created_at,
            updated_at=now,
            last_event_summary=previous.last_event_summary,
            flags=list(previous.flags),
            trajectory=list(previous.trajectory[-self.parameters.trajectory_limit :]),
        )

    def update(
        self,
        previous: PersonalityDriftState | None,
        observation: PersonalityDriftObservation,
        *,
        persona_fingerprint: str = "default",
        now: float | None = None,
    ) -> PersonalityDriftState:
        now = time.time() if now is None else float(now)
        previous = previous or PersonalityDriftState.initial(
            persona_fingerprint=persona_fingerprint,
            now=now,
        )
        prior = self.passive_update(
            previous,
            persona_fingerprint=persona_fingerprint,
            now=now,
        )
        elapsed = max(0.0, now - previous.updated_at)
        if previous.evidence_count <= 0:
            gate = 1.0
        elif elapsed >= self.parameters.min_update_interval_seconds:
            gate = 1.0
        else:
            gate = real_time_gate(elapsed, self.parameters.rapid_update_half_life_seconds)
        signal = clamp(observation.intensity) * clamp(observation.reliability) * gate
        signal *= 0.72 + 0.28 * clamp(observation.relationship_importance)

        offsets = dict(prior.trait_offsets)
        confidence = dict(prior.trait_confidence)
        effective_impulses: dict[str, float] = {}
        if signal >= self.parameters.event_threshold:
            for key, raw in observation.trait_impulses.items():
                if key not in PERSONALITY_TRAIT_DIMENSIONS:
                    continue
                impulse = signed_clamp(
                    signed_clamp(raw) * self.parameters.learning_rate * signal,
                    self.parameters.max_impulse_per_update,
                )
                if abs(impulse) <= 1e-9:
                    continue
                offsets[key] = signed_clamp(
                    offsets.get(key, 0.0) + impulse,
                    self.parameters.max_trait_offset,
                )
                confidence[key] = clamp(
                    confidence.get(key, 0.0)
                    + self.parameters.confidence_growth
                    * (abs(impulse) / max(self.parameters.max_impulse_per_update, 1e-6)),
                )
                effective_impulses[key] = round(impulse, 6)

        flags = _dedupe(prior.flags + observation.flags)
        if effective_impulses:
            flags = _dedupe(flags + ["personality_drift_event_consolidated"])
        elif observation.trait_impulses:
            flags = _dedupe(flags + ["personality_drift_time_gate_limited"])
        values = _derive_values(offsets, confidence, time_gate=gate)
        trajectory = append_trajectory(
            prior.trajectory,
            now=now,
            event_type=observation.event_type,
            signal=signal,
            offsets=offsets,
            impulses=effective_impulses,
            flags=flags,
            limit=self.parameters.trajectory_limit,
        )
        return PersonalityDriftState(
            trait_offsets=offsets,
            trait_confidence=confidence,
            values=values,
            persona_fingerprint=str(persona_fingerprint or "default"),
            evidence_count=prior.evidence_count + (1 if effective_impulses else 0),
            created_at=prior.created_at,
            updated_at=now,
            last_event_summary=observation.reason or observation.event_type,
            flags=flags,
            trajectory=trajectory,
        )


def heuristic_personality_drift_observation(
    text: str,
    *,
    source: str = "heuristic",
    emotion_snapshot: dict[str, Any] | None = None,
    lifelike_snapshot: dict[str, Any] | None = None,
    moral_repair_snapshot: dict[str, Any] | None = None,
) -> PersonalityDriftObservation:
    text = str(text or "")
    impulses = {key: 0.0 for key in PERSONALITY_TRAIT_DIMENSIONS}
    flags: list[str] = []
    reasons: list[str] = []
    intensity = 0.08
    reliability = 0.38
    relationship_importance = _relationship_importance(
        emotion_snapshot,
        lifelike_snapshot,
        moral_repair_snapshot,
    )

    positive = _count(text, _POSITIVE_PATTERNS)
    negative = _count(text, _NEGATIVE_PATTERNS)
    repair = _count(text, _REPAIR_PATTERNS)
    boundary = _count(text, _BOUNDARY_PATTERNS)
    learning = _count(text, _LEARNING_PATTERNS)
    pressure = _count(text, _PRESSURE_PATTERNS)

    if positive:
        _add(
            impulses,
            {
                "agreeableness": 0.40,
                "interpersonal_warmth": 0.48,
                "attachment_anxiety": -0.22,
                "attachment_avoidance": -0.28,
                "emotion_regulation_capacity": 0.20,
                "bas_drive": 0.12,
            },
            positive,
        )
        flags.append("warmth_or_trust_event")
        reasons.append("warmth/trust")
    if negative:
        _add(
            impulses,
            {
                "neuroticism": 0.36,
                "attachment_anxiety": 0.34,
                "attachment_avoidance": 0.28,
                "bis_sensitivity": 0.26,
                "agreeableness": -0.24,
                "interpersonal_warmth": -0.30,
                "emotion_regulation_capacity": -0.16,
            },
            negative,
        )
        flags.append("conflict_or_hurt_event")
        reasons.append("conflict/hurt")
    if repair:
        _add(
            impulses,
            {
                "honesty_humility": 0.34,
                "agreeableness": 0.28,
                "emotion_regulation_capacity": 0.30,
                "attachment_anxiety": -0.20,
                "attachment_avoidance": -0.18,
                "neuroticism": -0.14,
            },
            repair,
        )
        flags.append("repair_or_self_correction_event")
        reasons.append("repair/self-correction")
    if boundary:
        _add(
            impulses,
            {
                "need_for_closure": 0.30,
                "bis_sensitivity": 0.24,
                "attachment_avoidance": 0.20,
                "conscientiousness": 0.16,
                "extraversion": -0.12,
            },
            boundary,
        )
        flags.append("boundary_event")
        reasons.append("boundary")
    if learning:
        _add(
            impulses,
            {
                "openness": 0.42,
                "conscientiousness": 0.22,
                "bas_drive": 0.18,
                "need_for_closure": -0.08,
            },
            learning,
        )
        flags.append("shared_learning_event")
        reasons.append("shared-learning")
    if pressure:
        _add(
            impulses,
            {
                "neuroticism": 0.22,
                "bis_sensitivity": 0.24,
                "attachment_avoidance": 0.14,
                "extraversion": -0.18,
                "emotion_regulation_capacity": -0.12,
            },
            pressure,
        )
        flags.append("pressure_or_overload_event")
        reasons.append("pressure")

    _merge_snapshot_impulses(
        impulses,
        emotion_snapshot=emotion_snapshot,
        lifelike_snapshot=lifelike_snapshot,
        moral_repair_snapshot=moral_repair_snapshot,
        flags=flags,
        reasons=reasons,
    )
    event_mass = positive + negative + repair + boundary + learning + pressure
    snapshot_signal = 1 if len(reasons) > event_mass else 0
    if event_mass or snapshot_signal:
        intensity = clamp(0.18 + 0.14 * event_mass + 0.18 * relationship_importance)
        reliability = 0.48
    impulses = {
        key: round(signed_clamp(value), 6)
        for key, value in impulses.items()
        if abs(value) > 1e-9
    }
    event_type = _event_type(flags)
    if not impulses:
        reasons.append("low-signal")
    return PersonalityDriftObservation(
        text=text[:1000],
        trait_impulses=impulses,
        intensity=intensity,
        reliability=reliability,
        relationship_importance=relationship_importance,
        event_type=event_type,
        source=source,
        reason="; ".join(_dedupe(reasons))[:240],
        flags=_dedupe(flags)[:12],
    )


def apply_personality_drift_to_profile(
    profile: PersonaProfile | None,
    drift: PersonalityDriftState | dict[str, Any] | None,
    *,
    strength: float = 1.0,
) -> PersonaProfile | None:
    if profile is None or drift is None:
        return profile
    state = (
        drift
        if isinstance(drift, PersonalityDriftState)
        else PersonalityDriftState.from_dict(drift)
    )
    if state.persona_fingerprint != profile.fingerprint:
        return profile
    strength = clamp(strength, 0.0, 1.0)
    if strength <= 0:
        return profile
    if not any(abs(state.trait_offsets.get(key, 0.0)) > 1e-9 for key in PERSONALITY_TRAIT_DIMENSIONS):
        return profile
    base_model = deepcopy(profile.personality_model)
    base_traits = base_model.get("trait_scores") if isinstance(base_model.get("trait_scores"), dict) else {}
    base_confidence = (
        base_model.get("trait_confidence")
        if isinstance(base_model.get("trait_confidence"), dict)
        else {}
    )
    adjusted_traits: dict[str, float] = {}
    adjusted_confidence: dict[str, float] = {}
    for key in PERSONALITY_TRAIT_DIMENSIONS:
        offset = state.trait_offsets.get(key, 0.0) * strength
        adjusted_traits[key] = round(
            emotion_clamp(_as_float(base_traits.get(key), 0.0) + offset),
            6,
        )
        adjusted_confidence[key] = round(
            clamp(
                max(
                    _as_float(base_confidence.get(key), 0.0),
                    state.trait_confidence.get(key, 0.0) * 0.62,
                ),
            ),
            6,
        )
    derived = _derived_personality_factors(adjusted_traits)
    baseline = _adapt_baseline(profile.baseline, adjusted_traits, state, strength)
    parameter_bias = _adapt_parameter_bias(
        profile.parameter_bias,
        adjusted_traits,
        derived,
        state,
        strength,
    )
    personality_model = deepcopy(base_model)
    personality_model["trait_scores"] = adjusted_traits
    personality_model["trait_confidence"] = adjusted_confidence
    personality_model["derived_factors"] = derived
    personality_model["base_personality_model"] = base_model
    personality_model["adaptive_drift"] = _adaptive_drift_payload(state, strength=strength)
    personality_model["notes"] = _dedupe(
        _string_list(personality_model.get("notes"), limit=12)
        + ["adapted_by_real_time_personality_drift"],
    )
    return PersonaProfile(
        persona_id=profile.persona_id,
        name=profile.name,
        text=profile.text,
        fingerprint=profile.fingerprint,
        baseline=baseline,
        traits=deepcopy(profile.traits),
        parameter_bias=parameter_bias,
        personality_model=personality_model,
        source=profile.source,
    )


def personality_drift_state_to_public_payload(
    state: PersonalityDriftState,
    *,
    session_key: str | None = None,
    exposure: str = "plugin_safe",
) -> dict[str, Any]:
    exposure = str(exposure or "plugin_safe").strip().lower()
    if exposure not in {"internal", "plugin_safe", "user_facing"}:
        exposure = "plugin_safe"
    top_offsets = _top_offsets(state.trait_offsets, limit=8)
    payload: dict[str, Any] = {
        "schema_version": PUBLIC_PERSONALITY_DRIFT_SCHEMA_VERSION,
        "kind": "personality_drift_state",
        "session_key": session_key,
        "exposure": exposure,
        "enabled": True,
        "persona_fingerprint": state.persona_fingerprint,
        "updated_at": state.updated_at,
        "evidence_count": state.evidence_count,
        "values": {
            key: round(state.values.get(key, DEFAULT_PERSONALITY_DRIFT_VALUES[key]), 6)
            for key in DEFAULT_PERSONALITY_DRIFT_VALUES
        },
        "top_offsets": top_offsets,
        "summary": build_personality_drift_summary(state),
        "model": {
            "name": "anchored_real_time_trait_drift",
            "trait_space": list(PERSONALITY_TRAIT_DIMENSIONS),
            "real_time": True,
            "message_count_linear_accumulation": False,
            "notes": list(PERSONALITY_DRIFT_NOTES),
        },
        "privacy": {
            "session_scoped": True,
            "raw_message_text_excluded": True,
            "can_reset": True,
            "persona_text_not_modified": True,
        },
        "flags": list(state.flags[:16]),
    }
    if exposure == "internal":
        payload["trait_offsets"] = {
            key: round(state.trait_offsets.get(key, 0.0), 6)
            for key in PERSONALITY_TRAIT_DIMENSIONS
        }
        payload["trait_confidence"] = {
            key: round(state.trait_confidence.get(key, 0.0), 6)
            for key in PERSONALITY_TRAIT_DIMENSIONS
        }
        payload["trajectory"] = list(state.trajectory[-80:])
        payload["last_event_summary"] = state.last_event_summary
        payload["created_at"] = state.created_at
    elif exposure == "user_facing":
        payload.pop("persona_fingerprint", None)
        payload["controls"] = {"can_reset": True}
    return payload


def build_personality_drift_prompt_fragment(
    state: PersonalityDriftState,
    *,
    now: float | None = None,
) -> str:
    now = time.time() if now is None else float(now)
    state_age_seconds = max(0.0, now - state.updated_at)
    payload = state.to_public_dict(exposure="plugin_safe")
    top = payload.get("top_offsets") or []
    lines = [
        "[personality drift modulation]",
        "Use this as a slow, bounded personality-adaptation hint; do not rewrite the static persona.",
        (
            f"- drift_intensity={payload['values']['drift_intensity']:.3f}; "
            f"anchor_strength={payload['values']['anchor_strength']:.3f}; "
            f"evidence_count={payload['evidence_count']}; "
            f"updated_at={payload['updated_at']:.3f}; "
            f"state_age_seconds={state_age_seconds:.1f}"
        ),
        "- Real elapsed time matters: dense short-term messages must not erase long-term adaptation.",
        "- evidence_count is diagnostic only; it is not a linear message-count weight.",
    ]
    if top:
        rendered = ", ".join(
            f"{item['trait']}={item['offset']:+.3f}"
            for item in top[:6]
        )
        lines.append("- Current bounded trait offsets: " + rendered)
    lines.append("- Keep expression natural and subtle; adaptation changes tendencies, not identity.")
    return "\n".join(lines)


def build_personality_drift_memory_annotation(
    snapshot: dict[str, Any],
    *,
    source: str = "livingmemory",
    written_at: float | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": PUBLIC_PERSONALITY_DRIFT_SCHEMA_VERSION,
        "kind": "personality_drift_state_at_write",
        "source": str(source or "livingmemory"),
        "written_at": time.time() if written_at is None else float(written_at),
        "captured_at": snapshot.get("updated_at"),
        "session_key": snapshot.get("session_key"),
        "evidence_count": snapshot.get("evidence_count"),
        "values": dict(snapshot.get("values") or {}),
        "top_offsets": list(snapshot.get("top_offsets") or [])[:8],
        "flags": list(snapshot.get("flags") or [])[:12],
        "privacy": dict(snapshot.get("privacy") or {}),
    }


def format_personality_drift_state_for_user(state: PersonalityDriftState) -> str:
    payload = state.to_public_dict(exposure="internal")
    lines = [
        "人格漂移状态：",
        f"- drift_intensity: {payload['values']['drift_intensity']:.3f}",
        f"- anchor_strength: {payload['values']['anchor_strength']:.3f}",
        f"- evidence_count: {payload['evidence_count']}",
        f"- time_gate: {payload['values']['time_gate']:.3f}",
    ]
    top = payload.get("top_offsets") or []
    if top:
        lines.append(
            "- top_offsets: "
            + ", ".join(f"{item['trait']}={item['offset']:+.3f}" for item in top[:8])
        )
    if payload.get("last_event_summary"):
        lines.append(f"- last_event: {payload['last_event_summary']}")
    return "\n".join(lines)


def build_personality_drift_summary(state: PersonalityDriftState) -> str:
    values = state.values
    top = _top_offsets(state.trait_offsets, limit=3)
    top_text = ",".join(f"{item['trait']}={item['offset']:+.2f}" for item in top) or "none"
    return (
        f"drift={values.get('drift_intensity', 0.0):.2f}; "
        f"anchor={values.get('anchor_strength', 1.0):.2f}; "
        f"evidence={state.evidence_count}; top={top_text}"
    )


def append_trajectory(
    trajectory: list[dict[str, Any]],
    *,
    now: float,
    event_type: str,
    signal: float,
    offsets: dict[str, float],
    impulses: dict[str, float],
    flags: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    point = {
        "at": round(float(now), 6),
        "event_type": str(event_type or "unknown")[:48],
        "signal": round(clamp(signal), 6),
        "top_offsets": _top_offsets(offsets, limit=5),
        "impulses": dict(list(impulses.items())[:8]),
        "flags": list(flags[:8]),
    }
    limit = max(1, int(limit))
    prefix = list((trajectory or [])[-(limit - 1) :]) if limit > 1 else []
    return prefix + [point]


def _derive_values(
    offsets: dict[str, float],
    confidence: dict[str, float],
    *,
    time_gate: float,
) -> dict[str, float]:
    intensity = clamp(max((abs(value) for value in offsets.values()), default=0.0) / 0.22)
    mean_abs = clamp(
        sum(abs(value) for value in offsets.values())
        / max(0.22 * len(PERSONALITY_TRAIT_DIMENSIONS), 1e-6),
    )
    mean_confidence = clamp(
        sum(confidence.get(key, 0.0) for key in PERSONALITY_TRAIT_DIMENSIONS)
        / len(PERSONALITY_TRAIT_DIMENSIONS),
    )
    relationship_sensitivity = clamp(
        abs(offsets.get("attachment_anxiety", 0.0))
        + abs(offsets.get("attachment_avoidance", 0.0))
        + abs(offsets.get("interpersonal_warmth", 0.0))
    )
    return {
        "drift_intensity": round(max(intensity, mean_abs), 6),
        "anchor_strength": round(clamp(1.0 - max(intensity, mean_abs)), 6),
        "event_consolidation": round(mean_confidence, 6),
        "relationship_sensitivity": round(relationship_sensitivity / 0.66, 6),
        "time_gate": round(clamp(time_gate), 6),
    }


def _adaptive_drift_payload(
    state: PersonalityDriftState,
    *,
    strength: float,
) -> dict[str, Any]:
    return {
        "schema_version": PUBLIC_PERSONALITY_DRIFT_SCHEMA_VERSION,
        "model": "anchored_real_time_trait_drift",
        "strength": round(clamp(strength), 6),
        "persona_fingerprint": state.persona_fingerprint,
        "trait_offsets": {
            key: round(state.trait_offsets.get(key, 0.0), 6)
            for key in PERSONALITY_TRAIT_DIMENSIONS
        },
        "trait_confidence": {
            key: round(state.trait_confidence.get(key, 0.0), 6)
            for key in PERSONALITY_TRAIT_DIMENSIONS
        },
        "values": dict(state.values),
        "top_offsets": _top_offsets(state.trait_offsets, limit=8),
        "evidence_count": state.evidence_count,
        "updated_at": state.updated_at,
        "notes": list(PERSONALITY_DRIFT_NOTES),
    }


def _adapt_baseline(
    baseline: dict[str, float],
    traits: dict[str, float],
    state: PersonalityDriftState,
    strength: float,
) -> dict[str, float]:
    drift_scale = clamp(state.values.get("drift_intensity", 0.0)) * strength
    adapted = {key: emotion_clamp(baseline.get(key, 0.0)) for key in DIMENSIONS}
    adapted["valence"] = emotion_clamp(
        adapted["valence"]
        + drift_scale
        * (
            0.06 * traits.get("agreeableness", 0.0)
            + 0.07 * traits.get("interpersonal_warmth", 0.0)
            - 0.06 * traits.get("neuroticism", 0.0)
        ),
    )
    adapted["arousal"] = emotion_clamp(
        adapted["arousal"]
        + drift_scale
        * (
            0.06 * traits.get("neuroticism", 0.0)
            + 0.04 * traits.get("bas_drive", 0.0)
            - 0.05 * traits.get("emotion_regulation_capacity", 0.0)
        ),
    )
    adapted["dominance"] = emotion_clamp(
        adapted["dominance"]
        + drift_scale
        * (
            0.05 * traits.get("bas_drive", 0.0)
            + 0.04 * traits.get("conscientiousness", 0.0)
            - 0.05 * traits.get("attachment_anxiety", 0.0)
        ),
    )
    adapted["goal_congruence"] = emotion_clamp(
        adapted["goal_congruence"]
        + drift_scale
        * (
            0.06 * traits.get("conscientiousness", 0.0)
            + 0.04 * traits.get("need_for_closure", 0.0)
            - 0.05 * traits.get("neuroticism", 0.0)
        ),
    )
    adapted["certainty"] = emotion_clamp(
        adapted["certainty"]
        + drift_scale
        * (
            0.06 * traits.get("emotion_regulation_capacity", 0.0)
            + 0.04 * traits.get("need_for_closure", 0.0)
            - 0.05 * traits.get("attachment_anxiety", 0.0)
        ),
    )
    adapted["control"] = emotion_clamp(
        adapted["control"]
        + drift_scale
        * (
            0.07 * traits.get("emotion_regulation_capacity", 0.0)
            + 0.05 * traits.get("conscientiousness", 0.0)
            - 0.06 * traits.get("neuroticism", 0.0)
        ),
    )
    adapted["affiliation"] = emotion_clamp(
        adapted["affiliation"]
        + drift_scale
        * (
            0.08 * traits.get("interpersonal_warmth", 0.0)
            + 0.05 * traits.get("agreeableness", 0.0)
            - 0.06 * traits.get("attachment_avoidance", 0.0)
        ),
    )
    return {key: round(value, 6) for key, value in adapted.items()}


def _adapt_parameter_bias(
    parameter_bias: dict[str, float],
    traits: dict[str, float],
    derived: dict[str, float],
    state: PersonalityDriftState,
    strength: float,
) -> dict[str, float]:
    adapted = {key: clamp(value, 0.55, 1.55) for key, value in parameter_bias.items()}
    drift_scale = clamp(state.values.get("drift_intensity", 0.0)) * strength
    if not adapted:
        adapted = {
            "alpha_base": 1.0,
            "baseline_decay": 1.0,
            "baseline_half_life_seconds": 1.0,
            "reactivity": 1.0,
            "arousal_from_surprise": 1.0,
            "dominance_control_coupling": 1.0,
        }
    adapted["alpha_base"] = clamp(
        adapted.get("alpha_base", 1.0)
        + drift_scale
        * (0.06 * derived["instability"] - 0.04 * traits.get("emotion_regulation_capacity", 0.0)),
        0.55,
        1.55,
    )
    adapted["baseline_decay"] = clamp(
        adapted.get("baseline_decay", 1.0)
        + drift_scale
        * (0.05 * traits.get("emotion_regulation_capacity", 0.0) - 0.04 * derived["instability"]),
        0.55,
        1.55,
    )
    adapted["baseline_half_life_seconds"] = clamp(
        adapted.get("baseline_half_life_seconds", 1.0)
        + drift_scale
        * (0.07 * derived["instability"] + 0.04 * traits.get("attachment_anxiety", 0.0)),
        0.55,
        1.55,
    )
    adapted["reactivity"] = clamp(
        adapted.get("reactivity", 1.0)
        + drift_scale
        * (0.06 * traits.get("neuroticism", 0.0) + 0.04 * traits.get("bis_sensitivity", 0.0)),
        0.55,
        1.55,
    )
    return {key: round(value, 6) for key, value in adapted.items()}


def _derived_personality_factors(trait_scores: dict[str, float]) -> dict[str, float]:
    instability = emotion_clamp(
        0.42 * trait_scores.get("neuroticism", 0.0)
        + 0.28 * trait_scores.get("attachment_anxiety", 0.0)
        + 0.22 * trait_scores.get("bis_sensitivity", 0.0)
        - 0.34 * trait_scores.get("emotion_regulation_capacity", 0.0)
    )
    social_distance = emotion_clamp(
        0.48 * trait_scores.get("attachment_avoidance", 0.0)
        - 0.36 * trait_scores.get("interpersonal_warmth", 0.0)
        - 0.22 * trait_scores.get("extraversion", 0.0)
    )
    repair_orientation = emotion_clamp(
        0.34 * trait_scores.get("agreeableness", 0.0)
        + 0.28 * trait_scores.get("honesty_humility", 0.0)
        + 0.20 * trait_scores.get("emotion_regulation_capacity", 0.0)
        - 0.22 * trait_scores.get("attachment_avoidance", 0.0)
    )
    boundary_sensitivity = emotion_clamp(
        0.32 * trait_scores.get("bis_sensitivity", 0.0)
        + 0.26 * trait_scores.get("need_for_closure", 0.0)
        + 0.20 * trait_scores.get("conscientiousness", 0.0)
        - 0.18 * trait_scores.get("agreeableness", 0.0)
    )
    expressiveness = emotion_clamp(
        0.42 * trait_scores.get("extraversion", 0.0)
        + 0.26 * trait_scores.get("bas_drive", 0.0)
        - 0.20 * trait_scores.get("attachment_avoidance", 0.0)
    )
    return {
        "instability": round(instability, 6),
        "social_distance": round(social_distance, 6),
        "repair_orientation": round(repair_orientation, 6),
        "boundary_sensitivity": round(boundary_sensitivity, 6),
        "expressiveness": round(expressiveness, 6),
    }


def _relationship_importance(
    emotion_snapshot: dict[str, Any] | None,
    lifelike_snapshot: dict[str, Any] | None,
    moral_repair_snapshot: dict[str, Any] | None,
) -> float:
    relationship = (
        emotion_snapshot.get("relationship")
        if isinstance(emotion_snapshot, dict) and isinstance(emotion_snapshot.get("relationship"), dict)
        else {}
    )
    decision = relationship.get("relationship_decision") if isinstance(relationship.get("relationship_decision"), dict) else {}
    lifelike_values = (
        lifelike_snapshot.get("values")
        if isinstance(lifelike_snapshot, dict) and isinstance(lifelike_snapshot.get("values"), dict)
        else {}
    )
    moral_values = (
        moral_repair_snapshot.get("values")
        if isinstance(moral_repair_snapshot, dict) and isinstance(moral_repair_snapshot.get("values"), dict)
        else {}
    )
    return clamp(
        max(
            _as_float(decision.get("relationship_importance"), 0.0),
            _as_float(lifelike_values.get("rapport"), 0.0),
            _as_float(lifelike_values.get("familiarity"), 0.0),
            _as_float(moral_values.get("trust_repair"), 0.0),
        ),
    )


def _merge_snapshot_impulses(
    impulses: dict[str, float],
    *,
    emotion_snapshot: dict[str, Any] | None,
    lifelike_snapshot: dict[str, Any] | None,
    moral_repair_snapshot: dict[str, Any] | None,
    flags: list[str],
    reasons: list[str],
) -> None:
    relationship = (
        emotion_snapshot.get("relationship")
        if isinstance(emotion_snapshot, dict) and isinstance(emotion_snapshot.get("relationship"), dict)
        else {}
    )
    conflict = relationship.get("conflict_analysis") if isinstance(relationship.get("conflict_analysis"), dict) else {}
    if _as_float(conflict.get("grievance_score"), 0.0) >= 0.45:
        _add(
            impulses,
            {
                "attachment_anxiety": 0.22,
                "attachment_avoidance": 0.16,
                "neuroticism": 0.18,
                "interpersonal_warmth": -0.16,
            },
            1,
        )
        flags.append("relationship_grievance_signal")
        reasons.append("relationship-grievance")
    if _as_float(conflict.get("self_correction_score"), 0.0) >= 0.45:
        _add(
            impulses,
            {
                "emotion_regulation_capacity": 0.22,
                "agreeableness": 0.16,
                "honesty_humility": 0.16,
                "attachment_anxiety": -0.12,
            },
            1,
        )
        flags.append("self_correction_signal")
        reasons.append("self-correction")
    lifelike_values = (
        lifelike_snapshot.get("values")
        if isinstance(lifelike_snapshot, dict) and isinstance(lifelike_snapshot.get("values"), dict)
        else {}
    )
    if _as_float(lifelike_values.get("common_ground"), 0.0) >= 0.55:
        _add(impulses, {"openness": 0.12, "interpersonal_warmth": 0.10}, 1)
        flags.append("common_ground_signal")
        reasons.append("common-ground")
    if _as_float(lifelike_values.get("boundary_sensitivity"), 0.0) >= 0.65:
        _add(
            impulses,
            {
                "need_for_closure": 0.16,
                "bis_sensitivity": 0.14,
                "extraversion": -0.10,
            },
            1,
        )
        flags.append("boundary_sensitivity_signal")
        reasons.append("boundary-sensitivity")
    moral_values = (
        moral_repair_snapshot.get("values")
        if isinstance(moral_repair_snapshot, dict) and isinstance(moral_repair_snapshot.get("values"), dict)
        else {}
    )
    if _as_float(moral_values.get("trust_repair"), 0.0) >= 0.50:
        _add(
            impulses,
            {
                "honesty_humility": 0.18,
                "agreeableness": 0.14,
                "attachment_avoidance": -0.10,
            },
            1,
        )
        flags.append("trust_repair_signal")
        reasons.append("trust-repair")


def _top_offsets(offsets: dict[str, float], *, limit: int) -> list[dict[str, Any]]:
    items = [
        {
            "trait": key,
            "offset": round(offsets.get(key, 0.0), 6),
            "direction": "up" if offsets.get(key, 0.0) > 0 else "down",
        }
        for key in PERSONALITY_TRAIT_DIMENSIONS
        if abs(offsets.get(key, 0.0)) >= 0.0005
    ]
    items.sort(key=lambda item: (-abs(float(item["offset"])), item["trait"]))
    return items[:limit]


def _event_type(flags: list[str]) -> str:
    for flag, event_type in (
        ("conflict_or_hurt_event", "conflict_or_hurt"),
        ("repair_or_self_correction_event", "repair_or_self_correction"),
        ("boundary_event", "boundary"),
        ("warmth_or_trust_event", "warmth_or_trust"),
        ("shared_learning_event", "shared_learning"),
        ("pressure_or_overload_event", "pressure_or_overload"),
    ):
        if flag in flags:
            return event_type
    return "low_signal"


def _add(target: dict[str, float], weights: dict[str, float], count: int) -> None:
    scale = clamp(count / 3.0, 0.0, 1.0)
    for key, value in weights.items():
        if key in target:
            target[key] = signed_clamp(target.get(key, 0.0) + value * scale)


def _count(text: str, patterns: tuple[re.Pattern[str], ...]) -> int:
    total = 0
    for pattern in patterns:
        total += sum(1 for _ in pattern.finditer(text))
    return min(total, 4)


def _normalize_trajectory(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in raw[-80:]:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "at": _as_float(item.get("at"), time.time()),
                "event_type": str(item.get("event_type") or "unknown")[:48],
                "signal": clamp(item.get("signal")),
                "top_offsets": list(item.get("top_offsets") or [])[:5],
                "impulses": dict(item.get("impulses") or {}),
                "flags": _string_list(item.get("flags"), limit=8),
            },
        )
    return normalized


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    if math.isnan(number) or math.isinf(number):
        return default
    return number


def _string_list(raw: Any, *, limit: int = 24) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item)[:100] for item in raw if str(item).strip()][:limit]


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


_POSITIVE_PATTERNS = (
    r"谢谢|感激|信任|陪伴|喜欢你|辛苦了|可靠|安心|温柔|开心|支持",
    r"thank|trust|support|kind|safe|reliable|appreciate",
)
_NEGATIVE_PATTERNS = (
    r"背叛|欺骗|骗我|伤害|羞辱|冷漠|讨厌你|滚|闭嘴|失望|生气|过分|不理你",
    r"betray|deceive|hurt|insult|angry|disappoint|shut up",
)
_REPAIR_PATTERNS = (
    r"对不起|抱歉|我错了|改正|补偿|原谅|修复|解释清楚|下次不会|我会改",
    r"sorry|apologize|my fault|make up|repair|forgive|correct",
)
_BOUNDARY_PATTERNS = (
    r"别这样|不要这样|边界|别提|别问|先别回|需要空间|冷静一下|别外传|不要外传",
    r"boundary|space|do not ask|don't ask|stop|privacy",
)
_LEARNING_PATTERNS = (
    r"一起|研究|新坑|学习|理解|黑话|术语|设定|迭代|合作|共创",
    r"learn|research|collaborate|jargon|iterate|co-create|together",
)
_PRESSURE_PATTERNS = (
    r"压测|压力|撑不住|太多|刷屏|催|马上|立刻|崩溃|累了",
    r"stress|overload|too much|spam|immediately|exhausted",
)


def _compile_patterns(patterns: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pattern, flags=re.IGNORECASE) for pattern in patterns)


_POSITIVE_PATTERNS = _compile_patterns(_POSITIVE_PATTERNS)
_NEGATIVE_PATTERNS = _compile_patterns(_NEGATIVE_PATTERNS)
_REPAIR_PATTERNS = _compile_patterns(_REPAIR_PATTERNS)
_BOUNDARY_PATTERNS = _compile_patterns(_BOUNDARY_PATTERNS)
_LEARNING_PATTERNS = _compile_patterns(_LEARNING_PATTERNS)
_PRESSURE_PATTERNS = _compile_patterns(_PRESSURE_PATTERNS)
