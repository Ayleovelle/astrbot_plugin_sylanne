from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any


PUBLIC_LIFELIKE_LEARNING_SCHEMA_VERSION = "astrbot.lifelike_learning_state.v1"
PUBLIC_COMMON_GROUND_SCHEMA_VERSION = "astrbot.common_ground_lexicon.v1"

LIFELIKE_DIMENSIONS: tuple[str, ...] = (
    "familiarity",
    "common_ground",
    "jargon_density",
    "preference_confidence",
    "rapport",
    "boundary_sensitivity",
    "initiative_readiness",
    "silence_comfort",
)

DEFAULT_VALUES: dict[str, float] = {
    "familiarity": 0.08,
    "common_ground": 0.05,
    "jargon_density": 0.0,
    "preference_confidence": 0.0,
    "rapport": 0.16,
    "boundary_sensitivity": 0.24,
    "initiative_readiness": 0.35,
    "silence_comfort": 0.30,
}

KNOWN_GENERIC_TERMS = {
    "bot",
    "gpt",
    "llm",
    "ai",
    "api",
    "json",
    "python",
    "github",
    "readme",
    "astrbot",
    "livingmemory",
}

_STYLE_AVOID_MARKDOWN_RE = re.compile(r"别.*(?:长篇大论|markdown|分点|列表)")
_STYLE_NATURAL_RE = re.compile(r"(?:自然|闲聊|像人|口语|短一点|少分点)")
_STYLE_RIGOR_RE = re.compile(r"(?:详细|严谨|公式|文献|测试)")
_BOUNDARY_NO_FAKE_OR_LEAK_RE = re.compile(
    r"(?:别|不要|不许).{0,8}(?:装懂|乱用|外传|泄露)"
)
_BOUNDARY_SILENCE_RE = re.compile(r"(?:闭嘴|别说话|先别回|少说|安静)")
_BOUNDARY_PRIVATE_RE = re.compile(r"(?:隐私|小圈子|私下|不要外传)")


def clamp(value: Any, lower: float = 0.0, upper: float = 1.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = lower
    return max(lower, min(upper, number))


def half_life_multiplier(elapsed_seconds: float, half_life_seconds: float) -> float:
    if elapsed_seconds <= 0:
        return 1.0
    if half_life_seconds <= 0:
        return 0.0
    return clamp(2.0 ** (-elapsed_seconds / half_life_seconds))


@dataclass(slots=True)
class JargonEntry:
    term: str
    surface_forms: list[str] = field(default_factory=list)
    candidate_meanings: list[str] = field(default_factory=list)
    community_context: str = ""
    confidence: float = 0.0
    evidence_count: int = 0
    first_seen_at: float = field(default_factory=time.time)
    last_seen_at: float = field(default_factory=time.time)
    ask_before_using: bool = True
    sensitive: bool = False

    @classmethod
    def from_dict(cls, data: Any) -> "JargonEntry | None":
        if not isinstance(data, dict):
            return None
        term = _clean_term(data.get("term"))
        if not term:
            return None
        return cls(
            term=term,
            surface_forms=_string_list(data.get("surface_forms"), limit=8),
            candidate_meanings=_string_list(data.get("candidate_meanings"), limit=6),
            community_context=str(data.get("community_context") or "")[:120],
            confidence=clamp(data.get("confidence")),
            evidence_count=max(0, int(_as_float(data.get("evidence_count"), 0))),
            first_seen_at=_as_float(data.get("first_seen_at"), time.time()),
            last_seen_at=_as_float(data.get("last_seen_at"), time.time()),
            ask_before_using=bool(data.get("ask_before_using", True)),
            sensitive=bool(data.get("sensitive", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "term": self.term,
            "surface_forms": list(dict.fromkeys([self.term] + self.surface_forms))[:8],
            "candidate_meanings": list(self.candidate_meanings[:6]),
            "community_context": self.community_context,
            "confidence": round(self.confidence, 6),
            "evidence_count": self.evidence_count,
            "first_seen_at": self.first_seen_at,
            "last_seen_at": self.last_seen_at,
            "ask_before_using": bool(self.ask_before_using),
            "sensitive": bool(self.sensitive),
        }


@dataclass(slots=True)
class UserProfileEvidence:
    facts: dict[str, str] = field(default_factory=dict)
    likes: list[str] = field(default_factory=list)
    dislikes: list[str] = field(default_factory=list)
    style_preferences: list[str] = field(default_factory=list)
    boundary_notes: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Any) -> "UserProfileEvidence":
        if not isinstance(data, dict):
            return cls()
        facts_raw = data.get("facts") if isinstance(data.get("facts"), dict) else {}
        return cls(
            facts={
                str(key)[:48]: str(value)[:160]
                for key, value in facts_raw.items()
                if str(key).strip() and str(value).strip()
            },
            likes=_string_list(data.get("likes"), limit=24),
            dislikes=_string_list(data.get("dislikes"), limit=24),
            style_preferences=_string_list(data.get("style_preferences"), limit=24),
            boundary_notes=_string_list(data.get("boundary_notes"), limit=24),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "facts": dict(list(self.facts.items())[:32]),
            "likes": list(self.likes[:24]),
            "dislikes": list(self.dislikes[:24]),
            "style_preferences": list(self.style_preferences[:24]),
            "boundary_notes": list(self.boundary_notes[:24]),
        }


def _copy_jargon_entry(entry: JargonEntry) -> JargonEntry:
    return JargonEntry(
        term=entry.term,
        surface_forms=list(entry.surface_forms[:8]),
        candidate_meanings=list(entry.candidate_meanings[:6]),
        community_context=entry.community_context[:120],
        confidence=entry.confidence,
        evidence_count=entry.evidence_count,
        first_seen_at=entry.first_seen_at,
        last_seen_at=entry.last_seen_at,
        ask_before_using=entry.ask_before_using,
        sensitive=entry.sensitive,
    )


def _copy_user_profile(profile: UserProfileEvidence) -> UserProfileEvidence:
    return UserProfileEvidence(
        facts=dict(list(profile.facts.items())[:32]),
        likes=list(profile.likes[:24]),
        dislikes=list(profile.dislikes[:24]),
        style_preferences=list(profile.style_preferences[:24]),
        boundary_notes=list(profile.boundary_notes[:24]),
    )


@dataclass(slots=True)
class LifelikeLearningState:
    values: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_VALUES))
    lexicon: dict[str, JargonEntry] = field(default_factory=dict)
    user_profile: UserProfileEvidence = field(default_factory=UserProfileEvidence)
    turns: int = 0
    updated_at: float = field(default_factory=time.time)
    last_observation: str = ""
    flags: list[str] = field(default_factory=list)
    trajectory: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def initial(cls) -> "LifelikeLearningState":
        return cls()

    @classmethod
    def from_dict(cls, data: Any) -> "LifelikeLearningState":
        if not isinstance(data, dict):
            return cls.initial()
        values = dict(DEFAULT_VALUES)
        raw_values = data.get("values") if isinstance(data.get("values"), dict) else {}
        for key, value in raw_values.items():
            if key in values:
                values[key] = clamp(value)
        lexicon: dict[str, JargonEntry] = {}
        raw_lexicon = data.get("lexicon") if isinstance(data.get("lexicon"), dict) else {}
        for key, item in raw_lexicon.items():
            entry = JargonEntry.from_dict(item)
            if entry is not None:
                lexicon[entry.term or _clean_term(key)] = entry
        return cls(
            values=values,
            lexicon=lexicon,
            user_profile=UserProfileEvidence.from_dict(data.get("user_profile")),
            turns=max(0, int(_as_float(data.get("turns"), 0))),
            updated_at=_as_float(data.get("updated_at"), time.time()),
            last_observation=str(data.get("last_observation") or "")[:240],
            flags=_string_list(data.get("flags"), limit=16),
            trajectory=_normalize_trajectory(data.get("trajectory")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PUBLIC_LIFELIKE_LEARNING_SCHEMA_VERSION,
            "values": {
                key: round(self.values.get(key, DEFAULT_VALUES[key]), 6)
                for key in LIFELIKE_DIMENSIONS
            },
            "lexicon": {
                key: value.to_dict()
                for key, value in sorted(self.lexicon.items())
            },
            "user_profile": self.user_profile.to_dict(),
            "turns": self.turns,
            "updated_at": self.updated_at,
            "last_observation": self.last_observation,
            "flags": list(self.flags[:16]),
            "trajectory": list(self.trajectory[-60:]),
        }

    def to_public_dict(
        self,
        *,
        session_key: str | None = None,
        exposure: str = "plugin_safe",
    ) -> dict[str, Any]:
        return lifelike_state_to_public_payload(
            self,
            session_key=session_key,
            exposure=exposure,
        )


@dataclass(slots=True)
class LifelikeLearningParameters:
    state_half_life_seconds: float = 2592000.0
    min_update_interval_seconds: float = 10.0
    max_terms: int = 120
    trajectory_limit: int = 60
    confidence_growth: float = 0.25


@dataclass(slots=True)
class LifelikeObservation:
    text: str
    terms: list[str] = field(default_factory=list)
    facts: dict[str, str] = field(default_factory=dict)
    likes: list[str] = field(default_factory=list)
    dislikes: list[str] = field(default_factory=list)
    style_preferences: list[str] = field(default_factory=list)
    boundary_notes: list[str] = field(default_factory=list)
    confidence: float = 0.35
    source: str = "heuristic"
    reason: str = ""
    flags: list[str] = field(default_factory=list)


class LifelikeLearningEngine:
    def __init__(self, parameters: LifelikeLearningParameters | None = None) -> None:
        self.parameters = parameters or LifelikeLearningParameters()

    def passive_update(
        self,
        previous: LifelikeLearningState | None,
        *,
        now: float | None = None,
    ) -> LifelikeLearningState:
        previous = previous or LifelikeLearningState.initial()
        now = time.time() if now is None else float(now)
        elapsed = max(0.0, now - previous.updated_at)
        if elapsed <= 0:
            return previous
        decay = half_life_multiplier(elapsed, self.parameters.state_half_life_seconds)
        values = {}
        for key in LIFELIKE_DIMENSIONS:
            baseline = DEFAULT_VALUES[key]
            values[key] = clamp(
                baseline + (previous.values.get(key, baseline) - baseline) * decay,
            )
        return LifelikeLearningState(
            values=values,
            lexicon=dict(previous.lexicon),
            user_profile=_copy_user_profile(previous.user_profile),
            turns=previous.turns,
            updated_at=now,
            last_observation=previous.last_observation,
            flags=list(previous.flags),
            trajectory=list(previous.trajectory[-self.parameters.trajectory_limit :]),
        )

    def update(
        self,
        previous: LifelikeLearningState | None,
        observation: LifelikeObservation,
        *,
        now: float | None = None,
    ) -> LifelikeLearningState:
        previous = previous or LifelikeLearningState.initial()
        now = time.time() if now is None else float(now)
        prior = self.passive_update(previous, now=now)
        elapsed = max(0.0, now - previous.updated_at)
        interval_gate = (
            0.25
            if elapsed < self.parameters.min_update_interval_seconds
            else 1.0
        )
        evidence = clamp(observation.confidence) * interval_gate
        lexicon = self._update_lexicon(prior.lexicon, observation, now, evidence)
        profile = self._update_profile(prior.user_profile, observation)
        values = self._update_values(prior.values, observation, lexicon, profile, evidence)
        flags = _dedupe(prior.flags + observation.flags)
        trajectory = append_trajectory(
            prior.trajectory,
            values=values,
            terms=observation.terms,
            flags=flags,
            now=now,
            limit=self.parameters.trajectory_limit,
        )
        return LifelikeLearningState(
            values=values,
            lexicon=lexicon,
            user_profile=profile,
            turns=prior.turns + 1,
            updated_at=now,
            last_observation=observation.reason or "lifelike learning update",
            flags=flags,
            trajectory=trajectory,
        )

    def _update_lexicon(
        self,
        previous: dict[str, JargonEntry],
        observation: LifelikeObservation,
        now: float,
        evidence: float,
    ) -> dict[str, JargonEntry]:
        lexicon = {key: _copy_jargon_entry(value) for key, value in previous.items()}
        for raw_term in observation.terms:
            term = _clean_term(raw_term)
            if not term:
                continue
            entry = lexicon.get(term)
            if entry is None:
                entry = JargonEntry(
                    term=term,
                    surface_forms=[raw_term],
                    candidate_meanings=_guess_candidate_meanings(
                        term,
                        observation.text,
                    ),
                    community_context=_guess_community_context(observation.text),
                    confidence=0.0,
                    evidence_count=0,
                    first_seen_at=now,
                    last_seen_at=now,
                    sensitive=_is_sensitive_context(observation.text),
                )
            entry.surface_forms = list(dict.fromkeys(entry.surface_forms + [raw_term]))[:8]
            guessed = _guess_candidate_meanings(term, observation.text)
            entry.candidate_meanings = list(
                dict.fromkeys(entry.candidate_meanings + guessed),
            )[:6]
            entry.community_context = (
                entry.community_context or _guess_community_context(observation.text)
            )[:120]
            entry.evidence_count += 1
            growth = self.parameters.confidence_growth * max(0.20, evidence)
            entry.confidence = clamp(entry.confidence + growth)
            entry.ask_before_using = entry.confidence < 0.72 or entry.sensitive
            entry.sensitive = entry.sensitive or _is_sensitive_context(observation.text)
            entry.last_seen_at = now
            lexicon[term] = entry
        if len(lexicon) > self.parameters.max_terms:
            sorted_items = sorted(
                lexicon.items(),
                key=lambda item: (item[1].confidence, item[1].last_seen_at),
                reverse=True,
            )
            lexicon = dict(sorted_items[: self.parameters.max_terms])
        return lexicon

    def _update_profile(
        self,
        previous: UserProfileEvidence,
        observation: LifelikeObservation,
    ) -> UserProfileEvidence:
        profile = _copy_user_profile(previous)
        profile.facts.update(
            {
                str(key)[:48]: str(value)[:160]
                for key, value in observation.facts.items()
                if str(key).strip() and str(value).strip()
            },
        )
        profile.likes = _dedupe(profile.likes + observation.likes)[:24]
        profile.dislikes = _dedupe(profile.dislikes + observation.dislikes)[:24]
        profile.style_preferences = _dedupe(
            profile.style_preferences + observation.style_preferences,
        )[:24]
        profile.boundary_notes = _dedupe(
            profile.boundary_notes + observation.boundary_notes,
        )[:24]
        return profile

    def _update_values(
        self,
        previous: dict[str, float],
        observation: LifelikeObservation,
        lexicon: dict[str, JargonEntry],
        profile: UserProfileEvidence,
        evidence: float,
    ) -> dict[str, float]:
        values = dict(DEFAULT_VALUES)
        values.update({key: clamp(previous.get(key, DEFAULT_VALUES[key])) for key in LIFELIKE_DIMENSIONS})
        term_signal = clamp(len(observation.terms) / 4.0)
        profile_signal = clamp(
            (
                len(profile.facts)
                + len(profile.likes)
                + len(profile.dislikes)
                + len(profile.style_preferences)
            )
            / 24.0,
        )
        confident_terms = [
            entry for entry in lexicon.values()
            if entry.confidence >= 0.55 and not entry.sensitive
        ]
        values["familiarity"] = clamp(values["familiarity"] + 0.035 * evidence + 0.015 * profile_signal)
        values["common_ground"] = clamp(values["common_ground"] + 0.045 * evidence + 0.08 * clamp(len(confident_terms) / 12.0))
        values["jargon_density"] = clamp(0.80 * values["jargon_density"] + 0.20 * term_signal)
        values["preference_confidence"] = clamp(values["preference_confidence"] + 0.08 * evidence * profile_signal)
        values["rapport"] = clamp(
            values["rapport"]
            + 0.025 * evidence
            + 0.025 * len(observation.likes) / 4.0
            - 0.030 * len(observation.boundary_notes) / 4.0,
        )
        values["boundary_sensitivity"] = clamp(
            values["boundary_sensitivity"]
            + 0.060 * len(observation.boundary_notes) / 3.0
            + 0.025 * len(observation.dislikes) / 5.0,
        )
        values["initiative_readiness"] = clamp(
            0.42
            + 0.25 * values["rapport"]
            + 0.18 * values["common_ground"]
            - 0.22 * values["boundary_sensitivity"],
        )
        values["silence_comfort"] = clamp(
            0.30
            + 0.34 * values["boundary_sensitivity"]
            + 0.18 * (1.0 - values["initiative_readiness"]),
        )
        return {key: round(values[key], 6) for key in LIFELIKE_DIMENSIONS}


def heuristic_lifelike_observation(
    text: str,
    *,
    source: str = "heuristic",
) -> LifelikeObservation:
    text = str(text or "")
    terms = extract_candidate_terms(text)
    facts = extract_user_facts(text)
    likes, dislikes = extract_preferences(text)
    style_preferences = extract_style_preferences(text)
    boundary_notes = extract_boundary_notes(text)
    flags: list[str] = []
    if terms:
        flags.append("local_jargon_detected")
    if facts or likes or dislikes or style_preferences:
        flags.append("user_profile_evidence")
    if boundary_notes:
        flags.append("boundary_preference_evidence")
    reason_parts = []
    if terms:
        reason_parts.append(f"terms={','.join(terms[:6])}")
    if facts:
        reason_parts.append("facts")
    if likes or dislikes:
        reason_parts.append("preferences")
    if style_preferences:
        reason_parts.append("style")
    if boundary_notes:
        reason_parts.append("boundaries")
    if not reason_parts:
        reason_parts.append("low-signal common-ground observation")
    return LifelikeObservation(
        text=text,
        terms=terms,
        facts=facts,
        likes=likes,
        dislikes=dislikes,
        style_preferences=style_preferences,
        boundary_notes=boundary_notes,
        confidence=0.52 if flags else 0.24,
        source=source,
        reason="; ".join(reason_parts),
        flags=flags,
    )


def derive_initiative_policy(
    state: LifelikeLearningState | dict[str, Any],
    *,
    emotion_snapshot: dict[str, Any] | None = None,
    humanlike_snapshot: dict[str, Any] | None = None,
    risk: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(state, LifelikeLearningState):
        values = state.values
        flags = state.flags
        lexicon = state.lexicon
    else:
        values = _values_from_public_or_state_dict(state)
        flags = _string_list(state.get("flags") if isinstance(state, dict) else [])
        raw_lexicon = state.get("lexicon") if isinstance(state, dict) else {}
        lexicon = {}
        if isinstance(raw_lexicon, dict):
            for key, value in raw_lexicon.items():
                entry = JargonEntry.from_dict(value)
                if entry is not None:
                    lexicon[key] = entry
    risk = risk or {}
    human_values = _nested_values(humanlike_snapshot or {})
    emotion_values = _nested_values(emotion_snapshot or {})
    boundary = max(
        values.get("boundary_sensitivity", 0.0),
        human_values.get("boundary_need", 0.0),
        0.75 if risk.get("relationship_boundary_active") else 0.0,
    )
    safety = 1.0 if risk.get("crisis_like_signal") else 0.0
    common = values.get("common_ground", 0.0)
    initiative = clamp(
        values.get("initiative_readiness", 0.0)
        + 0.18 * common
        + 0.12 * emotion_values.get("affiliation", 0.0)
        - 0.28 * boundary
        - 0.35 * safety,
    )
    uncertain_terms = [
        entry.term for entry in lexicon.values()
        if entry and entry.ask_before_using and entry.confidence >= 0.18
    ][:6]
    if safety >= 0.9:
        action = "safety_interrupt"
    elif uncertain_terms and common < 0.42:
        action = "ask_clarifying"
    elif boundary >= 0.72:
        action = "stay_silent"
    elif initiative >= 0.68:
        action = "speak_now"
    elif initiative >= 0.42:
        action = "brief_ack"
    else:
        action = "stay_silent"
    return {
        "schema_version": "astrbot.lifelike_initiative_policy.v1",
        "kind": "lifelike_initiative_policy",
        "action": action,
        "initiative_score": round(initiative, 6),
        "silence_score": round(clamp(values.get("silence_comfort", 0.0) + 0.24 * boundary), 6),
        "common_ground": round(common, 6),
        "boundary": round(clamp(boundary), 6),
        "uncertain_terms": uncertain_terms,
        "flags": flags[:12],
        "allowed_actions": _initiative_allowed_actions(action),
    }


def lifelike_state_to_public_payload(
    state: LifelikeLearningState,
    *,
    session_key: str | None = None,
    exposure: str = "plugin_safe",
) -> dict[str, Any]:
    exposure = str(exposure or "plugin_safe").strip().lower()
    if exposure not in {"internal", "plugin_safe", "user_facing"}:
        exposure = "plugin_safe"
    values = {
        key: round(state.values.get(key, DEFAULT_VALUES[key]), 6)
        for key in LIFELIKE_DIMENSIONS
    }
    lexicon_items = [entry.to_dict() for entry in state.lexicon.values()]
    lexicon_items.sort(key=lambda item: (-item["confidence"], item["term"]))
    policy = derive_initiative_policy(state)
    payload: dict[str, Any] = {
        "schema_version": PUBLIC_LIFELIKE_LEARNING_SCHEMA_VERSION,
        "common_ground_schema_version": PUBLIC_COMMON_GROUND_SCHEMA_VERSION,
        "kind": "lifelike_learning_state",
        "session_key": session_key,
        "exposure": exposure,
        "enabled": True,
        "updated_at": state.updated_at,
        "turns": state.turns,
        "flags": list(state.flags[:16]),
        "initiative_policy": policy,
        "summary": build_lifelike_summary(values, lexicon_items, state.user_profile),
        "privacy": {
            "session_scoped": True,
            "raw_message_text_excluded": True,
            "ask_before_using_uncertain_terms": True,
            "can_reset": True,
        },
    }
    if exposure == "internal":
        payload["values"] = values
        payload["dimensions"] = [
            {"key": key, "value": values[key]}
            for key in LIFELIKE_DIMENSIONS
        ]
        payload["lexicon"] = {
            item["term"]: item
            for item in lexicon_items
        }
        payload["user_profile"] = state.user_profile.to_dict()
        payload["trajectory"] = list(state.trajectory[-60:])
        payload["last_observation"] = state.last_observation
    elif exposure == "plugin_safe":
        payload["common_ground"] = {
            "known_terms": [
                {
                    "term": item["term"],
                    "confidence": item["confidence"],
                    "ask_before_using": item["ask_before_using"],
                    "sensitive": item["sensitive"],
                }
                for item in lexicon_items[:24]
            ],
            "profile_counts": {
                "facts": len(state.user_profile.facts),
                "likes": len(state.user_profile.likes),
                "dislikes": len(state.user_profile.dislikes),
                "style_preferences": len(state.user_profile.style_preferences),
                "boundary_notes": len(state.user_profile.boundary_notes),
            },
        }
    else:
        payload["controls"] = {"can_reset": True}
    return payload


def build_lifelike_prompt_fragment(state: LifelikeLearningState) -> str:
    payload = state.to_public_dict(exposure="plugin_safe")
    policy = payload["initiative_policy"]
    terms = payload["common_ground"]["known_terms"]
    confident = [item["term"] for item in terms if not item["ask_before_using"]][:8]
    uncertain = [item["term"] for item in terms if item["ask_before_using"]][:8]
    lines = [
        "[lifelike common-ground modulation]",
        "Use this as conversation memory and pacing guidance, not as factual proof.",
        f"- initiative_action={policy['action']}; initiative_score={policy['initiative_score']}; silence_score={policy['silence_score']}",
    ]
    if confident:
        lines.append("- Locally learned terms you may use naturally when relevant: " + ", ".join(confident))
    if uncertain:
        lines.append("- Uncertain local terms: do not pretend to know them; ask lightly before using: " + ", ".join(uncertain))
    counts = payload["common_ground"]["profile_counts"]
    lines.append(
        "- User model counts: "
        + ", ".join(f"{key}={value}" for key, value in counts.items())
    )
    lines.append("- Prefer natural short conversational turns; avoid default long assistant-style lists unless the user asks.")
    lines.append("- Silence, brief acknowledgement, or a small clarifying question can be better than over-answering.")
    return "\n".join(lines)


def build_lifelike_memory_annotation(
    snapshot: dict[str, Any],
    *,
    source: str = "livingmemory",
    written_at: float | None = None,
) -> dict[str, Any]:
    common_ground = snapshot.get("common_ground") if isinstance(snapshot.get("common_ground"), dict) else {}
    return {
        "schema_version": PUBLIC_LIFELIKE_LEARNING_SCHEMA_VERSION,
        "kind": "lifelike_learning_state_at_write",
        "source": str(source or "livingmemory"),
        "written_at": time.time() if written_at is None else float(written_at),
        "captured_at": snapshot.get("updated_at"),
        "session_key": snapshot.get("session_key"),
        "initiative_policy": dict(snapshot.get("initiative_policy") or {}),
        "known_terms": list(common_ground.get("known_terms") or [])[:16],
        "profile_counts": dict(common_ground.get("profile_counts") or {}),
        "flags": list(snapshot.get("flags") or []),
        "privacy": dict(snapshot.get("privacy") or {}),
    }


def format_lifelike_state_for_user(state: LifelikeLearningState) -> str:
    payload = state.to_public_dict(exposure="internal")
    lines = [
        "生命化学习状态：",
        f"- initiative: {payload['initiative_policy']['action']} ({payload['initiative_policy']['initiative_score']:.2f})",
        f"- common_ground: {payload['values']['common_ground']:.2f}",
        f"- familiarity: {payload['values']['familiarity']:.2f}",
        f"- boundary_sensitivity: {payload['values']['boundary_sensitivity']:.2f}",
    ]
    terms = list(payload.get("lexicon", {}))[:12]
    if terms:
        lines.append("- learned_terms: " + ", ".join(terms))
    counts = {
        key: len(value) if not isinstance(value, dict) else len(value)
        for key, value in payload.get("user_profile", {}).items()
    }
    lines.append("- profile_counts: " + ", ".join(f"{key}={value}" for key, value in counts.items()))
    return "\n".join(lines)


def build_lifelike_summary(
    values: dict[str, float],
    lexicon_items: list[dict[str, Any]],
    profile: UserProfileEvidence,
) -> str:
    term_count = len(lexicon_items)
    confident_count = sum(1 for item in lexicon_items if not item["ask_before_using"])
    profile_count = (
        len(profile.facts)
        + len(profile.likes)
        + len(profile.dislikes)
        + len(profile.style_preferences)
        + len(profile.boundary_notes)
    )
    return (
        f"common_ground={values['common_ground']:.2f}; "
        f"terms={term_count}; confident_terms={confident_count}; "
        f"profile_evidence={profile_count}; "
        f"initiative={values['initiative_readiness']:.2f}"
    )


def extract_candidate_terms(text: str) -> list[str]:
    candidates: list[str] = []
    patterns = (
        r"[A-Za-z][A-Za-z0-9_./+-]{2,24}",
        r"[\u4e00-\u9fff]{2,8}(?:梗|厨|推|圈|党|批|人|味|感|流|向|门|学|术|活|坑)",
        r"[\u4e00-\u9fffA-Za-z0-9_]{2,16}(?=就是|是指|指的是|=)",
        r"(?<=叫)[\u4e00-\u9fffA-Za-z0-9_]{2,16}",
        r"(?<=称呼)[\u4e00-\u9fffA-Za-z0-9_]{2,16}",
        r"(?<=黑话)[\u4e00-\u9fffA-Za-z0-9_]{2,16}",
    )
    for pattern in patterns:
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            term = _clean_term(match)
            if term:
                candidates.append(term)
    quoted = re.findall(r"[「『“\"]([^」』”\"]{2,24})[」』”\"]", text)
    for item in quoted:
        term = _clean_term(item)
        if term:
            candidates.append(term)
    return _dedupe(candidates)[:12]


def extract_user_facts(text: str) -> dict[str, str]:
    facts: dict[str, str] = {}
    patterns = (
        (r"我是\s*([^，。！？\n]*(?:大学|研究生|博士|硕士|本科|专业|方向)[^，。！？\n]*)", "background"),
        (r"(?:我是|我叫|我的名字是)\s*([^，。！？\n]{2,32})", "self_identity"),
        (r"我(?:在|就读于|来自)\s*([^，。！？\n]{2,48})", "background"),
        (r"我的(?:专业|方向|研究方向)是\s*([^，。！？\n]{2,48})", "field"),
    )
    for pattern, key in patterns:
        match = re.search(pattern, text)
        if match:
            facts[key] = match.group(1).strip()[:160]
    return facts


def extract_preferences(text: str) -> tuple[list[str], list[str]]:
    likes: list[str] = []
    dislikes: list[str] = []
    for pattern, target in (
        (r"我(?:喜欢|偏好|爱看|爱玩|想要)\s*([^，。！？\n]{1,48})", likes),
        (r"我(?:不喜欢|讨厌|别给我|不想要)\s*([^，。！？\n]{1,48})", dislikes),
    ):
        for match in re.findall(pattern, text):
            item = _clean_phrase(match)
            if item:
                target.append(item)
    return _dedupe(likes)[:8], _dedupe(dislikes)[:8]


def extract_style_preferences(text: str) -> list[str]:
    preferences = []
    if _STYLE_AVOID_MARKDOWN_RE.search(text):
        preferences.append("avoid_long_markdown_lists")
    if _STYLE_NATURAL_RE.search(text):
        preferences.append("natural_conversational_style")
    if _STYLE_RIGOR_RE.search(text):
        preferences.append("rigorous_engineering_detail_when_requested")
    return preferences


def extract_boundary_notes(text: str) -> list[str]:
    notes = []
    if _BOUNDARY_NO_FAKE_OR_LEAK_RE.search(text):
        notes.append("do_not_fake_or_leak_local_terms")
    if _BOUNDARY_SILENCE_RE.search(text):
        notes.append("respect_silence_or_brief_reply")
    if _BOUNDARY_PRIVATE_RE.search(text):
        notes.append("keep_common_ground_session_scoped")
    return notes


def append_trajectory(
    previous: list[dict[str, Any]],
    *,
    values: dict[str, float],
    terms: list[str],
    flags: list[str],
    now: float,
    limit: int,
) -> list[dict[str, Any]]:
    item = {
        "at": now,
        "familiarity": round(values["familiarity"], 6),
        "common_ground": round(values["common_ground"], 6),
        "jargon_density": round(values["jargon_density"], 6),
        "initiative_readiness": round(values["initiative_readiness"], 6),
        "silence_comfort": round(values["silence_comfort"], 6),
        "terms": list(terms[:6]),
        "flags": list(flags[:8]),
    }
    limit = max(1, int(limit))
    prefix = list((previous or [])[-(limit - 1) :]) if limit > 1 else []
    return prefix + [item]


def _initiative_allowed_actions(action: str) -> list[str]:
    mapping = {
        "safety_interrupt": ["interrupt_for_safety", "be_clear", "avoid_roleplay_escalation"],
        "ask_clarifying": ["ask_light_clarifying_question", "avoid_pretending_to_know"],
        "stay_silent": ["do_not_force_topic", "use_minimal_ack_if_required"],
        "speak_now": ["open_naturally", "use_shared_context_when_relevant"],
        "brief_ack": ["brief_acknowledgement", "follow_user_lead"],
        "repair_initiative": ["acknowledge_rupture", "offer_concrete_repair"],
    }
    return mapping.get(action, mapping["brief_ack"])


def _values_from_public_or_state_dict(data: dict[str, Any]) -> dict[str, float]:
    if isinstance(data.get("values"), dict):
        return {
            key: clamp(data["values"].get(key, DEFAULT_VALUES[key]))
            for key in LIFELIKE_DIMENSIONS
        }
    return dict(DEFAULT_VALUES)


def _nested_values(snapshot: dict[str, Any]) -> dict[str, float]:
    raw: dict[str, Any] = {}
    if isinstance(snapshot.get("values"), dict):
        raw.update(snapshot["values"])
    if isinstance(snapshot.get("emotion"), dict) and isinstance(snapshot["emotion"].get("values"), dict):
        raw.update(snapshot["emotion"]["values"])
    for key in ("output_modulation", "modulation_basis", "risk", "state_index"):
        if isinstance(snapshot.get(key), dict):
            raw.update(snapshot[key])
    return {str(key): clamp(value, -1.0, 1.0) for key, value in raw.items()}


def _guess_candidate_meanings(term: str, text: str) -> list[str]:
    meanings = []
    meaning_match = re.search(
        rf"{re.escape(term)}(?:就是|是|=|指的是)\s*([^，。！？\n]{{2,60}})",
        text,
    )
    if meaning_match:
        meanings.append(meaning_match.group(1).strip()[:80])
    if not meanings:
        meanings.append("local context term; meaning requires more evidence")
    return meanings


def _guess_community_context(text: str) -> str:
    if "二次元" in text or "漫展" in text or "cos" in text.lower():
        return "anime/game fandom context"
    if "实验室" in text or "论文" in text or "研究" in text:
        return "research or lab context"
    if "群" in text or "小圈子" in text or "黑话" in text:
        return "small-community jargon context"
    return "conversation-local context"


def _is_sensitive_context(text: str) -> bool:
    return bool(re.search(r"(隐私|私下|不要外传|小圈子|黑话|密码|token|账号)", text, re.IGNORECASE))


def _clean_term(value: Any) -> str:
    text = str(value or "").strip().strip("，。！？,.!?:;：；()（）[]【】")
    if not (2 <= len(text) <= 32):
        return ""
    lowered = text.lower()
    if lowered in KNOWN_GENERIC_TERMS:
        return ""
    if re.fullmatch(r"\d+", text):
        return ""
    digest = sha256(text.encode("utf-8")).hexdigest()
    if len(set(digest[:8])) <= 2:
        return ""
    return text


def _clean_phrase(value: Any) -> str:
    text = str(value or "").strip().strip("，。！？,.!?:;：；")
    return text[:80] if text else ""


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _string_list(value: Any, *, limit: int = 8) -> list[str]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        items = []
    cleaned: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text:
            cleaned.append(text[:120])
        if len(cleaned) >= limit:
            break
    return cleaned


def _dedupe(items: list[str]) -> list[str]:
    result = []
    seen = set()
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _normalize_trajectory(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for item in raw[-60:]:
        if not isinstance(item, dict):
            continue
        cleaned.append(
            {
                "at": _as_float(item.get("at"), time.time()),
                "familiarity": clamp(item.get("familiarity")),
                "common_ground": clamp(item.get("common_ground")),
                "jargon_density": clamp(item.get("jargon_density")),
                "initiative_readiness": clamp(item.get("initiative_readiness")),
                "silence_comfort": clamp(item.get("silence_comfort")),
                "terms": _string_list(item.get("terms"), limit=6),
                "flags": _string_list(item.get("flags"), limit=8),
            },
        )
    return cleaned
