from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from math import exp
from hashlib import sha256
import json
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
    "mutual_need_balance",
    "being_needed_readiness",
    "need_expression_readiness",
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
    "mutual_need_balance": 0.28,
    "being_needed_readiness": 0.30,
    "need_expression_readiness": 0.18,
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
_MUTUAL_NEED_RE = re.compile(
    r"(?:互相需要|双方都有需要|被需要|需要和被需要|互需|彼此需要|互相照顾)"
)
_USER_NEED_RE = re.compile(
    r"(?:我需要|想让你|陪我|帮我|安慰|听我说|别走|需要陪伴|需要确认|需要回应)"
)
_BOT_NEEDED_RE = re.compile(
    r"(?:你需要我|你也可以需要|bot.*需要|让.*被需要|我也想帮上忙|可以依靠我)"
)
_PROGRESS_TOPIC_RE = re.compile(
    r"(?:进度|做到哪|怎么样了|论文|作业|项目|实验|测试|服务器|仓库|代码|迭代|复习|考试|ddl|deadline|"
    r"研究|课题|开题|投稿|桥梁|隧道|模型|训练|数据|报告|文档|README)",
    re.IGNORECASE,
)
_PROGRESS_EXPLICIT_RE = re.compile(
    r"(?:进度|做到哪|怎么样了|还顺|卡住|推进|deadline|ddl|截止|未完成|待办|还没|继续|"
    r"提醒|跟进|催我|检查一下|帮我盯|这周|今天|明天|今晚|月底|开题|投稿|实验结果|测试结果)",
    re.IGNORECASE,
)
_PROGRESS_CLOSED_RE = re.compile(
    r"(?:已经|已|刚刚|刚才)?(?:完成|搞完|做完|结束|收尾完|解决了|不用跟进|别跟进|先不聊|话题结束|不用管)",
    re.IGNORECASE,
)


def clamp(value: Any, lower: float = 0.0, upper: float = 1.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = lower
    return max(lower, min(upper, number))


def _progress_evidence_excerpt(text: str) -> str:
    value = " ".join(str(text or "").split()).strip()
    if not value:
        return ""
    if _PROGRESS_CLOSED_RE.search(value):
        return ""
    if not _PROGRESS_TOPIC_RE.search(value):
        return ""
    if not _PROGRESS_EXPLICIT_RE.search(value):
        return ""
    return value[-120:]


def half_life_multiplier(elapsed_seconds: float, half_life_seconds: float) -> float:
    if elapsed_seconds <= 0:
        return 1.0
    if half_life_seconds <= 0:
        return 0.0
    return clamp(2.0 ** (-elapsed_seconds / half_life_seconds))


def half_life_fraction(elapsed_seconds: float, half_life_seconds: float) -> float:
    if elapsed_seconds <= 0:
        return 0.0
    if half_life_seconds <= 0:
        return 1.0
    return clamp(1.0 - 2.0 ** (-elapsed_seconds / half_life_seconds))


def sigmoid(value: float) -> float:
    if value >= 40:
        return 1.0
    if value <= -40:
        return 0.0
    return 1.0 / (1.0 + exp(-value))


def _normalize_dynamics(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    return {
        str(key): max(0.0, _as_float(value, 0.0))
        for key, value in raw.items()
    }


def _smooth_dynamic_value(
    previous: dict[str, float],
    key: str,
    target: float,
    *,
    elapsed_seconds: float,
    smoothing_half_life_seconds: float,
    lower: float,
    upper: float,
) -> float:
    target = clamp(target, lower, upper)
    if key not in previous:
        return target
    fraction = half_life_fraction(elapsed_seconds, smoothing_half_life_seconds)
    old = clamp(previous.get(key), lower, upper)
    return clamp(old + fraction * (target - old), lower, upper)


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
    need_notes: list[str] = field(default_factory=list)
    speaking_style: dict[str, float] = field(default_factory=dict)

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
            need_notes=_string_list(data.get("need_notes"), limit=24),
            speaking_style=_normalize_speaking_style(data.get("speaking_style")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "facts": dict(list(self.facts.items())[:32]),
            "likes": list(self.likes[:24]),
            "dislikes": list(self.dislikes[:24]),
            "style_preferences": list(self.style_preferences[:24]),
            "boundary_notes": list(self.boundary_notes[:24]),
            "need_notes": list(self.need_notes[:24]),
            "speaking_style": dict(self.speaking_style),
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
        need_notes=list(profile.need_notes[:24]),
        speaking_style=dict(profile.speaking_style),
    )


@dataclass(slots=True)
class LifelikeLearningState:
    values: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_VALUES))
    lexicon: dict[str, JargonEntry] = field(default_factory=dict)
    user_profile: UserProfileEvidence = field(default_factory=UserProfileEvidence)
    dynamics: dict[str, float] = field(default_factory=dict)
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
            dynamics=_normalize_dynamics(data.get("dynamics")),
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
            "dynamics": {
                key: round(value, 6) for key, value in self.dynamics.items()
            },
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
class LifelikeLearningDynamics:
    state_half_life_seconds: float
    min_update_interval_seconds: float
    confidence_growth: float
    value_step_scale: float
    smoothing_half_life_seconds: float

    def to_dict(self) -> dict[str, float]:
        return {
            "state_half_life_seconds": round(self.state_half_life_seconds, 6),
            "min_update_interval_seconds": round(self.min_update_interval_seconds, 6),
            "confidence_growth": round(self.confidence_growth, 6),
            "value_step_scale": round(self.value_step_scale, 6),
            "smoothing_half_life_seconds": round(self.smoothing_half_life_seconds, 6),
        }


@dataclass(slots=True)
class LifelikeObservation:
    text: str
    terms: list[str] = field(default_factory=list)
    facts: dict[str, str] = field(default_factory=dict)
    likes: list[str] = field(default_factory=list)
    dislikes: list[str] = field(default_factory=list)
    style_preferences: list[str] = field(default_factory=list)
    boundary_notes: list[str] = field(default_factory=list)
    need_notes: list[str] = field(default_factory=list)
    speaking_style: dict[str, float] = field(default_factory=dict)
    confidence: float = 0.35
    source: str = "heuristic"
    reason: str = ""
    flags: list[str] = field(default_factory=list)


def derive_lifelike_learning_dynamics(
    parameters: LifelikeLearningParameters,
    previous: LifelikeLearningState,
    observation: LifelikeObservation | None = None,
    *,
    elapsed_seconds: float = 0.0,
) -> LifelikeLearningDynamics:
    values = {
        key: clamp(previous.values.get(key, DEFAULT_VALUES[key]))
        for key in LIFELIKE_DIMENSIONS
    }
    observation = observation or LifelikeObservation(text="", confidence=0.0)
    term_signal = clamp(len(observation.terms) / 4.0)
    profile_signal = clamp(
        (
            len(previous.user_profile.facts)
            + len(previous.user_profile.likes)
            + len(previous.user_profile.dislikes)
            + len(previous.user_profile.style_preferences)
            + len(previous.user_profile.need_notes)
        )
        / 28.0,
    )
    boundary_load = clamp(
        values["boundary_sensitivity"]
        + 0.18 * len(observation.boundary_notes) / 4.0,
    )
    rapport = values["rapport"]
    common_ground = values["common_ground"]
    need_balance = values["mutual_need_balance"]
    uncertainty = clamp(
        1.0
        - 0.45 * values["preference_confidence"]
        - 0.35 * common_ground
        - 0.20 * profile_signal,
    )
    evidence_quality = clamp(
        observation.confidence
        + 0.14 * term_signal
        + 0.10 * profile_signal
        + 0.08 * need_balance
        - 0.12 * boundary_load,
    )
    adapt_pressure = clamp(
        0.24 * term_signal
        + 0.20 * profile_signal
        + 0.18 * rapport
        + 0.16 * common_ground
        + 0.12 * need_balance
        + 0.10 * evidence_quality
        - 0.24 * boundary_load,
    )
    smoothing_half_life = clamp(
        25.0
        + 210.0
        * (
            0.22
            + 0.24 * boundary_load
            + 0.20 * uncertainty
            + 0.14 * values["silence_comfort"]
            - 0.16 * adapt_pressure
        ),
        15.0,
        360.0,
    )
    target_half_life = clamp(
        parameters.state_half_life_seconds
        * exp(
            0.36 * common_ground
            + 0.28 * values["familiarity"]
            + 0.22 * rapport
            + 0.16 * boundary_load
            - 0.26 * uncertainty
            - 0.14 * adapt_pressure
        ),
        86400.0,
        15552000.0,
    )
    target_interval = clamp(
        parameters.min_update_interval_seconds
        * exp(
            0.64 * boundary_load
            + 0.26 * values["silence_comfort"]
            + 0.18 * uncertainty
            - 0.46 * evidence_quality
            - 0.20 * adapt_pressure
        ),
        1.0,
        120.0,
    )
    target_growth = clamp(
        parameters.confidence_growth
        * exp(
            0.52 * evidence_quality
            + 0.20 * term_signal
            + 0.16 * common_ground
            - 0.38 * boundary_load
            - 0.22 * uncertainty
        ),
        0.04,
        0.55,
    )
    target_step_scale = clamp(
        1.0
        + 0.38 * adapt_pressure
        + 0.20 * evidence_quality
        - 0.32 * boundary_load
        - 0.18 * uncertainty,
        0.35,
        1.75,
    )
    previous_dynamics = previous.dynamics
    return LifelikeLearningDynamics(
        state_half_life_seconds=_smooth_dynamic_value(
            previous_dynamics,
            "state_half_life_seconds",
            target_half_life,
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            lower=86400.0,
            upper=15552000.0,
        ),
        min_update_interval_seconds=_smooth_dynamic_value(
            previous_dynamics,
            "min_update_interval_seconds",
            target_interval,
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            lower=1.0,
            upper=120.0,
        ),
        confidence_growth=_smooth_dynamic_value(
            previous_dynamics,
            "confidence_growth",
            target_growth,
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            lower=0.04,
            upper=0.55,
        ),
        value_step_scale=_smooth_dynamic_value(
            previous_dynamics,
            "value_step_scale",
            target_step_scale,
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            lower=0.35,
            upper=1.75,
        ),
        smoothing_half_life_seconds=smoothing_half_life,
    )


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
        dynamics = derive_lifelike_learning_dynamics(
            self.parameters,
            previous,
            elapsed_seconds=elapsed,
        )
        decay = half_life_multiplier(elapsed, dynamics.state_half_life_seconds)
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
            dynamics=dynamics.to_dict(),
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
        dynamics = derive_lifelike_learning_dynamics(
            self.parameters,
            prior,
            observation,
            elapsed_seconds=elapsed,
        )
        interval_gate = (
            0.25
            if elapsed < dynamics.min_update_interval_seconds
            else 1.0
        )
        evidence = clamp(observation.confidence) * interval_gate
        lexicon = self._update_lexicon(
            prior.lexicon,
            observation,
            now,
            evidence,
            dynamics,
        )
        profile = self._update_profile(prior.user_profile, observation)
        values = self._update_values(
            prior.values,
            observation,
            lexicon,
            profile,
            evidence,
            dynamics,
        )
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
            dynamics=dynamics.to_dict(),
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
        dynamics: LifelikeLearningDynamics,
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
            growth = dynamics.confidence_growth * max(0.20, evidence)
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
        profile.need_notes = _dedupe(
            profile.need_notes + observation.need_notes,
        )[:24]
        profile.speaking_style = _merge_speaking_style(
            profile.speaking_style,
            observation.speaking_style,
            observation.confidence,
        )
        return profile

    def _update_values(
        self,
        previous: dict[str, float],
        observation: LifelikeObservation,
        lexicon: dict[str, JargonEntry],
        profile: UserProfileEvidence,
        evidence: float,
        dynamics: LifelikeLearningDynamics,
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
                + len(profile.need_notes)
            )
            / 28.0,
        )
        mutual_need_signal = clamp(len(observation.need_notes) / 3.0)
        confident_terms = [
            entry for entry in lexicon.values()
            if entry.confidence >= 0.55 and not entry.sensitive
        ]
        step = dynamics.value_step_scale
        values["familiarity"] = clamp(values["familiarity"] + step * (0.035 * evidence + 0.015 * profile_signal))
        values["common_ground"] = clamp(values["common_ground"] + step * (0.045 * evidence + 0.08 * clamp(len(confident_terms) / 12.0)))
        jargon_alpha = clamp(0.20 * step, 0.05, 0.55)
        values["jargon_density"] = clamp(
            (1.0 - jargon_alpha) * values["jargon_density"] + jargon_alpha * term_signal,
        )
        values["preference_confidence"] = clamp(values["preference_confidence"] + step * 0.08 * evidence * profile_signal)
        values["rapport"] = clamp(
            values["rapport"]
            + step * (
                0.025 * evidence
                + 0.025 * len(observation.likes) / 4.0
                - 0.030 * len(observation.boundary_notes) / 4.0
            ),
        )
        values["boundary_sensitivity"] = clamp(
            values["boundary_sensitivity"]
            + step
            * (
                0.060 * len(observation.boundary_notes) / 3.0
                + 0.025 * len(observation.dislikes) / 5.0
            ),
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
        values["mutual_need_balance"] = clamp(
            values["mutual_need_balance"]
            + step
            * (
                0.070 * evidence * mutual_need_signal
                + 0.035 * values["rapport"]
                + 0.025 * values["common_ground"]
                - 0.045 * values["boundary_sensitivity"]
            ),
        )
        values["being_needed_readiness"] = clamp(
            0.20
            + 0.32 * values["rapport"]
            + 0.22 * values["mutual_need_balance"]
            + 0.14 * values["common_ground"]
            - 0.18 * values["boundary_sensitivity"],
        )
        values["need_expression_readiness"] = clamp(
            0.12
            + 0.24 * values["rapport"]
            + 0.24 * values["mutual_need_balance"]
            + 0.12 * values["familiarity"]
            - 0.28 * values["boundary_sensitivity"]
            - 0.12 * values["silence_comfort"],
        )
        return {key: round(values[key], 6) for key in LIFELIKE_DIMENSIONS}


def heuristic_lifelike_observation(
    text: str,
    *,
    source: str = "heuristic",
) -> LifelikeObservation:
    text = str(text or "")
    speaking_style = infer_speaking_style(text)
    terms = extract_candidate_terms(text)
    facts = extract_user_facts(text)
    likes, dislikes = extract_preferences(text)
    style_preferences = extract_style_preferences(text)
    boundary_notes = extract_boundary_notes(text)
    need_notes = extract_need_notes(text)
    flags: list[str] = []
    if terms:
        flags.append("local_jargon_detected")
    if facts or likes or dislikes or style_preferences:
        flags.append("user_profile_evidence")
    if boundary_notes:
        flags.append("boundary_preference_evidence")
    if need_notes:
        flags.append("mutual_need_evidence")
    if speaking_style.get("confidence", 0.0) >= 0.18:
        flags.append("speaking_style_evidence")
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
    if need_notes:
        reason_parts.append("mutual_need")
    if speaking_style.get("confidence", 0.0) >= 0.18:
        reason_parts.append("speaking_style")
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
        need_notes=need_notes,
        speaking_style=speaking_style,
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


def derive_proactive_speech_decision(
    state: LifelikeLearningState | dict[str, Any],
    *,
    emotion_snapshot: dict[str, Any] | None = None,
    humanlike_snapshot: dict[str, Any] | None = None,
    group_snapshot: dict[str, Any] | None = None,
    risk: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Formula-driven decision for proactive speaking; it never sends messages."""
    values = (
        state.values
        if isinstance(state, LifelikeLearningState)
        else _values_from_public_or_state_dict(state)
    )
    emotion_values = _nested_values(emotion_snapshot or {})
    human_values = _nested_values(humanlike_snapshot or {})
    group_values = _nested_values(group_snapshot or {})
    risk = risk or {}
    moral_values = _nested_values(risk.get("moral_repair") or {})
    fallibility_values = _nested_values(risk.get("fallibility") or {})
    initiative = values.get("initiative_readiness", 0.0)
    common = values.get("common_ground", 0.0)
    rapport = values.get("rapport", 0.0)
    mutual_need = values.get("mutual_need_balance", 0.0)
    being_needed = values.get("being_needed_readiness", 0.0)
    need_expression = values.get("need_expression_readiness", 0.0)
    affiliation = emotion_values.get("affiliation", 0.0)
    valence = emotion_values.get("valence", 0.0)
    joinability = group_values.get("joinability", initiative)
    attention = group_values.get("bot_attention", 0.0)
    boundary = max(
        values.get("boundary_sensitivity", 0.0),
        human_values.get("boundary_need", 0.0),
        moral_values.get("harm_risk", 0.0),
        fallibility_values.get("truthfulness_guard", 0.0) * 0.55,
    )
    overload = max(
        group_values.get("interrupt_risk", 0.0),
        group_values.get("tension", 0.0) * 0.85,
        human_values.get("dependency_risk", 0.0) * 0.75,
    )
    uncertainty = max(
        0.0,
        1.0 - values.get("preference_confidence", 0.0),
    )
    repair_need = max(
        moral_values.get("repair_motivation", 0.0),
        moral_values.get("trust_repair", 0.0),
        fallibility_values.get("repair_pressure", 0.0),
    )
    companionship_need = clamp(
        0.36 * mutual_need
        + 0.28 * being_needed
        + 0.20 * need_expression
        + 0.14 * rapport
        + 0.12 * max(0.0, affiliation),
    )
    user_need_to_be_met = clamp(
        0.36 * being_needed
        + 0.22 * common
        + 0.18 * rapport
        + 0.14 * max(0.0, affiliation)
        - 0.16 * boundary,
    )
    bot_need_to_express = clamp(
        0.38 * need_expression
        + 0.22 * mutual_need
        + 0.18 * rapport
        - 0.22 * overload
        - 0.18 * boundary,
    )
    utility = (
        1.35 * initiative
        + 0.90 * common
        + 0.70 * rapport
        + 0.55 * affiliation
        + 0.45 * joinability
        + 0.30 * attention
        + 0.22 * max(0.0, valence)
        + 0.28 * repair_need
        + 0.36 * companionship_need
        + 0.24 * user_need_to_be_met
        + 0.18 * bot_need_to_express
        - 1.10 * boundary
        - 0.92 * overload
        - 0.42 * uncertainty
        - 1.72
    )
    proactive_score = sigmoid(utility)
    cooldown_active = bool(
        (group_snapshot or {}).get("participation", {}).get("cooldown_active"),
    )
    blocked = cooldown_active and attention < 0.78
    should_speak = proactive_score >= 0.62 and not blocked and boundary < 0.82
    if should_speak and repair_need >= 0.55:
        action = "repair_bid"
    elif should_speak and user_need_to_be_met >= 0.58:
        action = "respond_to_need"
    elif should_speak and bot_need_to_express >= 0.54:
        action = "express_small_need"
    elif should_speak and uncertainty >= 0.58:
        action = "ask_lightly"
    elif should_speak:
        action = "speak_now"
    elif proactive_score >= 0.45 and not blocked:
        action = "brief_ack"
    else:
        action = "stay_silent"
    reasons = []
    for label, value in (
        ("initiative", initiative),
        ("common_ground", common),
        ("rapport", rapport),
        ("joinability", joinability),
        ("repair_need", repair_need),
        ("companionship_need", companionship_need),
        ("user_need_to_be_met", user_need_to_be_met),
        ("bot_need_to_express", bot_need_to_express),
        ("boundary", boundary),
        ("overload", overload),
        ("uncertainty", uncertainty),
    ):
        reasons.append(f"{label}={value:.2f}")
    flags = []
    if cooldown_active:
        flags.append("group_cooldown_active")
    if boundary >= 0.72:
        flags.append("boundary_prefers_silence")
    if overload >= 0.65:
        flags.append("high_interrupt_risk")
    if repair_need >= 0.55:
        flags.append("repair_topic_preferred")
    if companionship_need >= 0.50:
        flags.append("mutual_need_mode")
    if user_need_to_be_met >= 0.58:
        flags.append("user_need_preferred")
    if bot_need_to_express >= 0.54:
        flags.append("bot_need_expression_possible")
    return {
        "schema_version": "astrbot.proactive_speech_policy.v1",
        "kind": "proactive_speech_decision",
        "action": action,
        "should_speak": bool(should_speak),
        "score": round(proactive_score, 6),
        "threshold": 0.62,
        "utility": round(utility, 6),
        "signals": {
            "initiative": round(initiative, 6),
            "common_ground": round(common, 6),
            "rapport": round(rapport, 6),
            "affiliation": round(affiliation, 6),
            "joinability": round(joinability, 6),
            "attention": round(attention, 6),
            "repair_need": round(repair_need, 6),
            "companionship_need": round(companionship_need, 6),
            "user_need_to_be_met": round(user_need_to_be_met, 6),
            "bot_need_to_express": round(bot_need_to_express, 6),
            "mutual_need_balance": round(mutual_need, 6),
            "being_needed_readiness": round(being_needed, 6),
            "need_expression_readiness": round(need_expression, 6),
            "boundary": round(boundary, 6),
            "overload": round(overload, 6),
            "uncertainty": round(uncertainty, 6),
        },
        "cooldown_blocked": bool(blocked),
        "needs": {
            "mode": "mutual_need" if companionship_need >= 0.50 else "ordinary",
            "companionship_need": round(companionship_need, 6),
            "user_need_to_be_met": round(user_need_to_be_met, 6),
            "bot_need_to_express": round(bot_need_to_express, 6),
            "guardrails": {
                "avoid_clinginess": True,
                "respect_boundary": boundary < 0.82,
                "silence_can_be_care": overload >= 0.65 or boundary >= 0.72,
            },
        },
        "flags": flags,
        "reason": "; ".join(reasons),
    }


def rank_proactive_topics(
    state: LifelikeLearningState | dict[str, Any],
    *,
    emotion_snapshot: dict[str, Any] | None = None,
    group_snapshot: dict[str, Any] | None = None,
    risk: dict[str, Any] | None = None,
    candidate_context: str = "",
    limit: int = 5,
) -> list[dict[str, Any]]:
    values = (
        state.values
        if isinstance(state, LifelikeLearningState)
        else _values_from_public_or_state_dict(state)
    )
    if isinstance(state, LifelikeLearningState):
        lexicon = state.lexicon
        profile = state.user_profile
    else:
        raw_lexicon = state.get("lexicon") if isinstance(state, dict) else {}
        lexicon = {}
        if isinstance(raw_lexicon, dict):
            for key, value in raw_lexicon.items():
                entry = JargonEntry.from_dict(value)
                if entry is not None:
                    lexicon[key] = entry
        profile = UserProfileEvidence.from_dict(
            state.get("user_profile") if isinstance(state, dict) else {},
        )
    emotion_values = _nested_values(emotion_snapshot or {})
    group_values = _nested_values(group_snapshot or {})
    risk = risk or {}
    moral_values = _nested_values(risk.get("moral_repair") or {})
    fallibility_values = _nested_values(risk.get("fallibility") or {})
    context_terms = set(extract_candidate_terms(candidate_context))
    candidates: list[dict[str, Any]] = []
    for entry in lexicon.values():
        if entry.sensitive:
            risk_penalty = 0.75
        elif entry.ask_before_using:
            risk_penalty = 0.28
        else:
            risk_penalty = 0.05
        novelty = 1.0 if entry.term not in context_terms else 0.25
        score = (
            0.42 * entry.confidence
            + 0.22 * values.get("common_ground", 0.0)
            + 0.16 * novelty
            + 0.10 * values.get("rapport", 0.0)
            - 0.35 * risk_penalty
        )
        candidates.append(
            {
                "topic": entry.term,
                "kind": "learned_term",
                "score": round(clamp(score), 6),
                "ask_before_using": bool(entry.ask_before_using),
                "confidence": round(entry.confidence, 6),
                "reason": "本地黑话/共同语境候选",
            },
        )
    for like in profile.likes[:12]:
        score = (
            0.35 * values.get("preference_confidence", 0.0)
            + 0.25 * values.get("rapport", 0.0)
            + 0.20 * max(0.0, emotion_values.get("valence", 0.0))
            + 0.10 * group_values.get("playfulness", 0.0)
        )
        candidates.append(
            {
                "topic": like,
                "kind": "user_preference",
                "score": round(clamp(score), 6),
                "ask_before_using": False,
                "confidence": round(values.get("preference_confidence", 0.0), 6),
                "reason": "用户偏好候选",
            },
        )
    repair_need = max(
        moral_values.get("repair_motivation", 0.0),
        moral_values.get("trust_repair", 0.0),
        fallibility_values.get("repair_pressure", 0.0),
    )
    if repair_need >= 0.35:
        candidates.append(
            {
                "topic": "轻量修复/澄清",
                "kind": "relationship_repair",
                "score": round(clamp(0.42 + 0.45 * repair_need), 6),
                "ask_before_using": False,
                "confidence": round(repair_need, 6),
                "reason": "修复压力较高，优先选择低打扰澄清",
            },
        )
    mutual_need = values.get("mutual_need_balance", 0.0)
    being_needed = values.get("being_needed_readiness", 0.0)
    need_expression = values.get("need_expression_readiness", 0.0)
    boundary = values.get("boundary_sensitivity", 0.0)
    rapport = values.get("rapport", 0.0)
    common = values.get("common_ground", 0.0)
    playfulness = group_values.get("playfulness", 0.0)
    progress_sources: list[str] = []
    for key, value in list(profile.facts.items())[:16]:
        item = f"{key}: {value}".strip(": ")
        excerpt = _progress_evidence_excerpt(item)
        if excerpt:
            progress_sources.append(excerpt)
    for note in profile.need_notes[:12]:
        excerpt = _progress_evidence_excerpt(note)
        if excerpt:
            progress_sources.append(excerpt)
    if candidate_context:
        excerpt = _progress_evidence_excerpt(candidate_context)
        if excerpt:
            progress_sources.append(excerpt)
    progress_sources = _dedupe(progress_sources)[:4]
    if progress_sources:
        progress_score = (
            0.22
            + 0.24 * common
            + 0.20 * values.get("preference_confidence", 0.0)
            + 0.16 * being_needed
            + 0.12 * rapport
            - 0.14 * boundary
        )
        candidates.append(
            {
                "topic": progress_sources[0],
                "kind": "progress_check",
                "score": round(clamp(progress_score), 6),
                "ask_before_using": False,
                "confidence": round(clamp(0.35 + 0.35 * common), 6),
                "reason": "用户近期事项或上下文出现进度线索，适合低打扰关心进展",
                "evidence": {
                    "sources": progress_sources,
                    "common_ground": round(common, 6),
                    "being_needed_readiness": round(being_needed, 6),
                },
            },
        )
    missing_score = (
        0.18
        + 0.28 * need_expression
        + 0.24 * mutual_need
        + 0.16 * rapport
        + 0.12 * max(0.0, emotion_values.get("affiliation", 0.0))
        - 0.24 * boundary
    )
    if missing_score >= 0.36:
        candidates.append(
            {
                "topic": "",
                "kind": "missing_user",
                "score": round(clamp(missing_score), 6),
                "ask_before_using": True,
                "confidence": round(clamp(max(need_expression, mutual_need, rapport)), 6),
                "reason": "互需与亲近信号较高，允许表达克制的想念或想确认用户是否还在",
                "evidence": {
                    "need_expression_readiness": round(need_expression, 6),
                    "mutual_need_balance": round(mutual_need, 6),
                    "rapport": round(rapport, 6),
                },
            },
        )
    playful_score = (
        0.16
        + 0.30 * playfulness
        + 0.18 * rapport
        + 0.12 * max(0.0, emotion_values.get("valence", 0.0))
        - 0.20 * boundary
        - 0.22 * group_values.get("tension", 0.0)
        - 0.18 * group_values.get("interrupt_risk", 0.0)
    )
    if playful_score >= 0.34:
        candidates.append(
            {
                "topic": "",
                "kind": "playful_ping",
                "score": round(clamp(playful_score), 6),
                "ask_before_using": True,
                "confidence": round(clamp(max(playfulness, rapport)), 6),
                "reason": "群聊或关系氛围较轻松，适合调皮地轻轻打扰一下",
                "evidence": {
                    "playfulness": round(playfulness, 6),
                    "rapport": round(rapport, 6),
                    "interrupt_risk": round(group_values.get("interrupt_risk", 0.0), 6),
                },
            },
        )
    prank_score = playful_score - 0.08 + 0.10 * common - 0.10 * boundary
    if prank_score >= 0.42:
        candidates.append(
            {
                "topic": "",
                "kind": "prank_light",
                "score": round(clamp(prank_score), 6),
                "ask_before_using": True,
                "confidence": round(clamp(max(playfulness, common)), 6),
                "reason": "轻松氛围和共同语境足够，可选择不伤人的轻量整蛊式开场",
                "evidence": {
                    "playfulness": round(playfulness, 6),
                    "common_ground": round(common, 6),
                    "boundary_sensitivity": round(boundary, 6),
                },
            },
        )
    if max(mutual_need, being_needed, need_expression) >= 0.32:
        candidates.append(
            {
                "topic": "",
                "kind": "mutual_need",
                "score": round(
                    clamp(
                        0.22
                        + 0.30 * mutual_need
                        + 0.24 * being_needed
                        + 0.18 * need_expression
                        + 0.12 * values.get("rapport", 0.0)
                        - 0.16 * boundary,
                    ),
                    6,
                ),
                "ask_before_using": True,
                "confidence": round(max(mutual_need, being_needed, need_expression), 6),
                "reason": "双方都有需要与被需要的相处模式候选，具体话题需由上下文和 LLM 裁决",
                "evidence": {
                    "mutual_need_balance": round(mutual_need, 6),
                    "being_needed_readiness": round(being_needed, 6),
                    "need_expression_readiness": round(need_expression, 6),
                },
            },
        )
    if not candidates:
        candidates.append(
            {
                "topic": "",
                "kind": "fallback",
                "score": round(clamp(values.get("initiative_readiness", 0.0)), 6),
                "ask_before_using": False,
                "confidence": round(values.get("common_ground", 0.0), 6),
                "reason": "共同语境不足时交给上下文和 LLM 判断是否简短关心、继续倾听或保持沉默",
            },
        )
    candidates.sort(key=lambda item: (-item["score"], item["topic"]))
    return candidates[: max(1, int(limit))]


def build_proactive_topic_assessment_prompt(
    *,
    decision: dict[str, Any],
    topic_candidates: list[dict[str, Any]],
    candidate_context: str = "",
    max_context_chars: int = 1600,
) -> str:
    context = str(candidate_context or "")[-max(0, int(max_context_chars)) :]
    return f"""你是 AstrBot 情绪插件内部的主动发言裁决器。
你的任务不是替 bot 直接聊天，而是判断：他/她此刻如果主动开口，应该满足什么需求、围绕什么话题、该不该保持沉默。

约束：
1. 不要使用预设话题模板。只能根据上下文、状态信号、候选证据和关系需要选择话题。
2. “双方都有需要和被需要”可以成立，但必须克制：不能黏人，不能用情绪绑架用户，不能假装知道没有证据的黑话。
3. 可以选择关心用户某件事的进度、表达克制想念、调皮打扰、轻量整蛊或关系修复；但必须能从候选证据、最近上下文或状态信号中说明理由。
4. progress_check 必须有明确证据：近期任务、期限、未完成事项、用户要求提醒/跟进或上下文中仍在推进的事项；话题已经结束时不要问进度。
5. 如果候选上下文提示上一条主动发言没有得到回应、只收到低信号回应或仍在等待回应，不要重复同一个话题，也不要隔几个小时继续追问同一个进度/身体状态问题。
6. 用户长时间没聊天时，只能保守猜测可能在忙、休息、睡觉或暂时不方便；不能断言用户冷淡、无视，也不能用负面情绪施压。
7. 如果只是想开口但没有可靠话题，要优先保持沉默；若确实只是想念用户，可选择 missing_user，但 draft_message 必须是短、低压力、允许不回复的轻触达，不能继续抓旧话题。
8. 轻量整蛊只能是无害玩笑、假装敲门、卖关子一秒这种短互动，不能欺骗事实、威胁、羞辱、诱导转账或破坏用户任务。
9. 如果证据不足，topic_text 留空或写成轻量澄清方向；不要编造用户喜好。
10. 输出必须是 JSON 对象，不要输出 Markdown。

主动发言模型结果：
{json_dumps_compact(decision)}

候选证据：
{json_dumps_compact(topic_candidates)}

最近上下文：
{context or "(无上下文)"}

输出 JSON schema：
{{
  "should_speak": true,
  "need_mode": "user_need|bot_need|mutual_need|repair|clarify|listen|silence|progress_check|missing_user|playful_ping|prank_light",
  "topic_text": "由上下文推理出的具体话题；无合适话题时留空",
  "speech_intent": "一句话说明主动开口想满足什么需要",
  "opening_style": "short_care|light_question|repair_bid|shared_context|quiet_presence|stay_silent|progress_check|playful_ping|tiny_prank",
  "topic_evidence": "一句话说明话题证据来自哪里，例如用户近期事项、共同语境、状态信号或最近上下文",
  "draft_message": "给发送层参考的一句短消息，不要超过 80 个汉字；不确定时留空",
  "confidence": 0.0,
  "reason": "一句话解释为什么此刻这样处理"
}}"""


def normalize_proactive_topic_judgement(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    need_mode = str(data.get("need_mode") or "clarify").strip()
    if need_mode not in {
        "user_need",
        "bot_need",
        "mutual_need",
        "repair",
        "clarify",
        "listen",
        "silence",
        "progress_check",
        "missing_user",
        "playful_ping",
        "prank_light",
    }:
        need_mode = "clarify"
    opening_style = str(data.get("opening_style") or "light_question").strip()
    if opening_style not in {
        "short_care",
        "light_question",
        "repair_bid",
        "shared_context",
        "quiet_presence",
        "stay_silent",
        "progress_check",
        "playful_ping",
        "tiny_prank",
    }:
        opening_style = "light_question"
    return {
        "schema_version": "astrbot.proactive_topic_judgement.v1",
        "kind": "llm_topic_judgement",
        "should_speak": bool(data.get("should_speak", True)),
        "need_mode": need_mode,
        "topic_text": str(data.get("topic_text") or "").strip()[:160],
        "speech_intent": str(data.get("speech_intent") or "").strip()[:200],
        "opening_style": opening_style,
        "topic_evidence": str(data.get("topic_evidence") or "").strip()[:240],
        "draft_message": str(data.get("draft_message") or "").strip()[:120],
        "confidence": round(clamp(data.get("confidence")), 6),
        "reason": str(data.get("reason") or "").strip()[:240],
        "source": "llm",
    }


def local_proactive_topic_judgement(
    decision: dict[str, Any],
    topic_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    needs = decision.get("needs") if isinstance(decision.get("needs"), dict) else {}
    flags = set(decision.get("flags") or [])
    action = str(decision.get("action") or "")
    selected = topic_candidates[0] if topic_candidates else {}
    selected_kind = str(selected.get("kind") or "")
    if action == "stay_silent":
        need_mode = "silence"
        opening_style = "stay_silent"
    elif selected_kind in {"progress_check", "missing_user", "playful_ping", "prank_light"}:
        need_mode = selected_kind
        opening_style = {
            "progress_check": "progress_check",
            "missing_user": "light_question",
            "playful_ping": "playful_ping",
            "prank_light": "tiny_prank",
        }[selected_kind]
    elif "repair_topic_preferred" in flags or action == "repair_bid":
        need_mode = "repair"
        opening_style = "repair_bid"
    elif "user_need_preferred" in flags or action == "respond_to_need":
        need_mode = "user_need"
        opening_style = "short_care"
    elif "bot_need_expression_possible" in flags or action == "express_small_need":
        need_mode = "bot_need"
        opening_style = "light_question"
    elif needs.get("mode") == "mutual_need":
        need_mode = "mutual_need"
        opening_style = "quiet_presence"
    elif action == "ask_lightly":
        need_mode = "clarify"
        opening_style = "light_question"
    else:
        need_mode = "listen"
        opening_style = "quiet_presence"
    topic_text = str(selected.get("topic") or "").strip()
    topic_evidence = selected.get("reason", "")
    if isinstance(selected.get("evidence"), dict):
        topic_evidence = json_dumps_compact(selected.get("evidence"))
    return {
        "schema_version": "astrbot.proactive_topic_judgement.v1",
        "kind": "llm_topic_judgement",
        "should_speak": bool(decision.get("should_speak")) and need_mode != "silence",
        "need_mode": need_mode,
        "topic_text": topic_text[:160],
        "speech_intent": _local_topic_intent(need_mode),
        "opening_style": opening_style,
        "topic_evidence": str(topic_evidence or "")[:240],
        "draft_message": _local_topic_draft(need_mode, topic_text),
        "confidence": round(clamp(selected.get("confidence", decision.get("score", 0.0))), 6),
        "reason": "本地回退：根据需求向量、边界和候选证据选择发言方向，具体措辞交给上层 LLM。",
        "source": "local_fallback",
    }


def json_dumps_compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _local_topic_intent(need_mode: str) -> str:
    mapping = {
        "user_need": "回应用户此刻被支持、被听见或被陪伴的需要。",
        "bot_need": "轻量表达他/她也希望被需要、被确认或参与关系的需要。",
        "mutual_need": "维持双方都有需要和被需要的平衡感。",
        "repair": "降低误会或关系破裂后的残余张力。",
        "clarify": "在证据不足时先温和确认，不装懂。",
        "listen": "保持低打扰陪伴，把话语权留给用户。",
        "silence": "此刻沉默或极短回应比主动展开更合适。",
        "progress_check": "基于用户近期事项或上下文进度线索，低打扰地关心进展。",
        "missing_user": "表达克制的想念和陪伴需要，同时给用户保留不回复的空间。",
        "playful_ping": "在氛围轻松时调皮地打个招呼，维持有来有往的关系感。",
        "prank_light": "用无害的小玩笑制造一点互动感，不改变事实也不制造压力。",
    }
    return mapping.get(need_mode, mapping["clarify"])


def _local_topic_draft(need_mode: str, topic_text: str) -> str:
    topic = str(topic_text or "").strip()
    if need_mode == "progress_check":
        if topic:
            return f"那、那个……你之前提到的{topic}，现在进度还顺吗？"
        return ""
    if need_mode == "missing_user":
        return "那、那个……我只是路过确认一下，你今天还好吗？"
    if need_mode == "playful_ping":
        return "咦，我、我来轻轻敲一下门。你现在方便被打扰一下吗？"
    if need_mode == "prank_light":
        return "等、等等，我发现一件很重要的小事：你是不是又在偷偷忙到忘记休息了？"
    if need_mode == "repair":
        return "那、那个……刚才如果我哪里说重了，我想先轻轻澄清一下。"
    if need_mode == "user_need":
        return "那、那个……你现在需要我陪你把这件事顺一下吗？"
    if need_mode == "bot_need":
        return "我、我也想参与一点点，可以吗？"
    if need_mode == "mutual_need":
        return "那、那个……我想确认一下，我们现在这样互相需要的节奏还舒服吗？"
    if need_mode == "clarify":
        return "我有点不确定，能不能轻轻确认一句？"
    if need_mode == "listen":
        return "我在。你要是想继续说，我会听。"
    return ""


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
    payload["dynamics"] = {
        key: round(value, 6) for key, value in state.dynamics.items()
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
    if policy.get("action") in {"respond_to_need", "express_small_need"} or state.values.get(
        "mutual_need_balance",
        0.0,
    ) >= 0.42:
        lines.append(
            "- Mutual-need mode may be relevant: let both sides have needs and be needed, but keep it light and non-clinging.",
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
    initiative_policy = (
        snapshot.get("initiative_policy")
        if isinstance(snapshot.get("initiative_policy"), dict)
        else {}
    )
    needs = initiative_policy.get("needs") if isinstance(initiative_policy.get("needs"), dict) else {}
    user_profile = (
        snapshot.get("user_profile")
        if isinstance(snapshot.get("user_profile"), dict)
        else {}
    )
    return {
        "schema_version": PUBLIC_LIFELIKE_LEARNING_SCHEMA_VERSION,
        "kind": "lifelike_learning_state_at_write",
        "source": str(source or "livingmemory"),
        "written_at": time.time() if written_at is None else float(written_at),
        "captured_at": snapshot.get("updated_at"),
        "session_key": snapshot.get("session_key"),
        "dynamics": dict(snapshot.get("dynamics") or {}),
        "initiative_policy": dict(initiative_policy),
        "mutual_need": {
            "mode": needs.get("mode"),
            "known_need_notes": list(user_profile.get("need_notes") or [])[:8],
        },
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
        f"- mutual_need_balance: {payload['values']['mutual_need_balance']:.2f}",
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


def infer_speaking_style(text: str) -> dict[str, float]:
    text = str(text or "").strip()
    if not text:
        return {}
    char_count = len(text)
    sentence_units = [
        item.strip()
        for item in re.split(r"[。！？!?…\n]+", text)
        if item.strip()
    ]
    unit_count = max(1, len(sentence_units))
    avg_unit_chars = char_count / unit_count
    newline_density = clamp(text.count("\n") / max(1.0, char_count / 80.0))
    punctuation_count = len(re.findall(r"[，。！？、,.!?…~～；;：:]", text))
    punctuation_density = clamp(punctuation_count / max(1.0, char_count / 24.0))
    short_turn_bias = clamp((24.0 - avg_unit_chars) / 22.0)
    long_turn_bias = clamp((avg_unit_chars - 38.0) / 56.0)
    fragment_bias = clamp(
        0.46 * short_turn_bias
        + 0.24 * newline_density
        + 0.18 * punctuation_density
        + 0.12 * clamp((unit_count - 1) / 5.0),
    )
    formal_block_bias = clamp(
        0.55 * long_turn_bias
        + 0.25 * (1.0 - punctuation_density)
        + 0.20 * (1.0 - newline_density),
    )
    typing_speed_bias = clamp(
        0.50
        + 0.20 * long_turn_bias
        - 0.16 * short_turn_bias
        + 0.10 * punctuation_density,
    )
    confidence = clamp(min(1.0, char_count / 120.0) * (0.55 + 0.10 * min(unit_count, 4)))
    return {
        "avg_unit_chars": round(avg_unit_chars, 6),
        "short_turn_bias": round(short_turn_bias, 6),
        "long_turn_bias": round(long_turn_bias, 6),
        "fragment_bias": round(fragment_bias, 6),
        "formal_block_bias": round(formal_block_bias, 6),
        "punctuation_density": round(punctuation_density, 6),
        "newline_density": round(newline_density, 6),
        "typing_speed_bias": round(typing_speed_bias, 6),
        "confidence": round(confidence, 6),
    }


def _normalize_speaking_style(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    keys = {
        "avg_unit_chars",
        "short_turn_bias",
        "long_turn_bias",
        "fragment_bias",
        "formal_block_bias",
        "punctuation_density",
        "newline_density",
        "typing_speed_bias",
        "confidence",
    }
    result: dict[str, float] = {}
    for key in keys:
        if key not in raw:
            continue
        value = _as_float(raw.get(key), 0.0)
        if key == "avg_unit_chars":
            result[key] = round(max(1.0, min(240.0, value)), 6)
        else:
            result[key] = round(clamp(value), 6)
    return result


def _merge_speaking_style(
    previous: dict[str, float],
    observed: dict[str, float],
    confidence: float,
) -> dict[str, float]:
    observed = _normalize_speaking_style(observed)
    if not observed:
        return _normalize_speaking_style(previous)
    previous = _normalize_speaking_style(previous)
    alpha = clamp(0.12 + 0.28 * confidence + 0.20 * observed.get("confidence", 0.0), 0.08, 0.48)
    merged: dict[str, float] = {}
    for key, value in observed.items():
        old = previous.get(key, value)
        if key == "confidence":
            merged[key] = round(max(old, value), 6)
        else:
            merged[key] = round(old + alpha * (value - old), 6)
    for key, value in previous.items():
        merged.setdefault(key, value)
    return _normalize_speaking_style(merged)


def extract_boundary_notes(text: str) -> list[str]:
    notes = []
    if _BOUNDARY_NO_FAKE_OR_LEAK_RE.search(text):
        notes.append("do_not_fake_or_leak_local_terms")
    if _BOUNDARY_SILENCE_RE.search(text):
        notes.append("respect_silence_or_brief_reply")
    if _BOUNDARY_PRIVATE_RE.search(text):
        notes.append("keep_common_ground_session_scoped")
    return notes


def extract_need_notes(text: str) -> list[str]:
    notes = []
    if _MUTUAL_NEED_RE.search(text):
        notes.append("mutual_need_mode")
    if _USER_NEED_RE.search(text):
        notes.append("user_expresses_need")
    if _BOT_NEEDED_RE.search(text):
        notes.append("bot_allowed_to_be_needed")
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
        "mutual_need_balance": round(values["mutual_need_balance"], 6),
        "being_needed_readiness": round(values["being_needed_readiness"], 6),
        "need_expression_readiness": round(values["need_expression_readiness"], 6),
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
                "mutual_need_balance": clamp(item.get("mutual_need_balance")),
                "being_needed_readiness": clamp(item.get("being_needed_readiness")),
                "need_expression_readiness": clamp(
                    item.get("need_expression_readiness"),
                ),
                "terms": _string_list(item.get("terms"), limit=6),
                "flags": _string_list(item.get("flags"), limit=8),
            },
        )
    return cleaned
