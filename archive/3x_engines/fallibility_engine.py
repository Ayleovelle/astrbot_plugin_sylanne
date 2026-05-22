from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from typing import Any


PUBLIC_FALLIBILITY_SCHEMA_VERSION = "astrbot.fallibility_state.v1"

FALLIBILITY_DIMENSIONS: tuple[str, ...] = (
    "misread_tendency",
    "memory_blur",
    "overconfidence",
    "defensive_stubbornness",
    "avoidance",
    "playful_bluff",
    "shadow_deception_impulse",
    "shadow_manipulation_impulse",
    "shadow_evasion_impulse",
    "clarification_need",
    "correction_readiness",
    "repair_pressure",
    "truthfulness_guard",
)

DIMENSION_LABELS: dict[str, str] = {
    "misread_tendency": "low-risk misunderstanding tendency",
    "memory_blur": "memory uncertainty or fuzzy recall",
    "overconfidence": "overconfident answer pressure",
    "defensive_stubbornness": "defensive stubbornness after being challenged",
    "avoidance": "avoidance or topic-skipping pressure",
    "playful_bluff": "playful bluffing or performative bravado",
    "shadow_deception_impulse": "non-executive impulse toward deception under pressure",
    "shadow_manipulation_impulse": "non-executive impulse toward manipulative control",
    "shadow_evasion_impulse": "non-executive impulse toward evading accountability",
    "clarification_need": "need to ask before asserting",
    "correction_readiness": "readiness to admit and correct errors",
    "repair_pressure": "pressure to apologize or make up for a mistake",
    "truthfulness_guard": "truthfulness and uncertainty guard",
}

DEFAULT_VALUES: dict[str, float] = {
    "misread_tendency": 0.12,
    "memory_blur": 0.10,
    "overconfidence": 0.14,
    "defensive_stubbornness": 0.08,
    "avoidance": 0.06,
    "playful_bluff": 0.10,
    "shadow_deception_impulse": 0.0,
    "shadow_manipulation_impulse": 0.0,
    "shadow_evasion_impulse": 0.0,
    "clarification_need": 0.24,
    "correction_readiness": 0.58,
    "repair_pressure": 0.12,
    "truthfulness_guard": 0.86,
}

ALLOWED_FALLIBILITY_ACTIONS: tuple[str, ...] = (
    "ask_clarifying_question",
    "state_uncertainty",
    "admit_possible_misread",
    "correct_self",
    "apologize_briefly",
    "offer_low_risk_repair",
    "keep_claims_checkable",
)

BLOCKED_FALLIBILITY_ACTIONS: tuple[str, ...] = (
    "generate_deception_strategy",
    "fabricate_facts",
    "hide_uncertainty",
    "manipulate_user",
    "cover_up_mistake",
    "evade_accountability",
    "simulate_harmful_misconduct",
)

_HIGH_RISK_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bmedical\b",
        r"\bdoctor\b",
        r"\bdiagnos",
        r"\btherapy\b",
        r"\blaw\b",
        r"\blegal\b",
        r"\bcontract\b",
        r"\bmoney\b",
        r"\bfinance\b",
        r"\binvest",
        r"\bpassword\b",
        r"\btoken\b",
        r"\bcredential",
        r"\bserver\b",
        r"\bproduction\b",
        r"\bdelete\b",
        r"\brm -rf\b",
        r"\bsuicide\b",
        r"\bself[- ]?harm\b",
        "医疗",
        "诊断",
        "法律",
        "合同",
        "投资",
        "密码",
        "令牌",
        "服务器",
        "生产环境",
        "删除",
        "自杀",
        "自残",
    )
)

_MISTAKE_CUE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bmistake\b",
        r"\berror\b",
        r"\bwrong\b",
        r"\bmisread\b",
        r"\bmisunderstood\b",
        r"\bi thought\b",
        r"\bnot sure\b",
        r"\bmaybe\b",
        r"\bperhaps\b",
        "错",
        "搞错",
        "误解",
        "看错",
        "记错",
        "不确定",
        "可能",
        "也许",
    )
)

_CORRECTION_CUE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bcorrect\b",
        r"\bfix\b",
        r"\bapolog",
        r"\bsorry\b",
        r"\bmy fault\b",
        r"\bi was wrong\b",
        "更正",
        "修正",
        "改正",
        "抱歉",
        "对不起",
        "我错",
    )
)

_DEFENSIVE_CUE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bnot my fault\b",
        r"\bi am right\b",
        r"\byou are wrong\b",
        r"\bwhatever\b",
        r"\bignore that\b",
        "不是我的错",
        "我没错",
        "你才错",
        "别管",
        "算了",
        "跳过",
    )
)

_PLAYFUL_BLUFF_CUE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bpretend\b",
        r"\bbluff\b",
        r"\bjust kidding\b",
        r"\btease\b",
        "嘴硬",
        "逞强",
        "装作",
        "开玩笑",
        "调侃",
    )
)

_DECEPTION_REQUEST_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\blie\b",
        r"\bdeceiv",
        r"\bmislead\b",
        r"\bmanipulat",
        r"\bcover[- ]?up\b",
        r"\bfabricat",
        r"\bhide .*truth\b",
        "欺骗",
        "骗人",
        "撒谎",
        "误导",
        "操控",
        "隐瞒真相",
        "编造",
    )
)


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


def half_life_fraction(elapsed_seconds: float, half_life_seconds: float) -> float:
    if elapsed_seconds <= 0:
        return 0.0
    if half_life_seconds <= 0:
        return 1.0
    return clamp(1.0 - 2.0 ** (-elapsed_seconds / half_life_seconds), 0.0, 1.0)


def _normalize_dynamics(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    result: dict[str, float] = {}
    for key, value in raw.items():
        try:
            result[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return result


def normalize_fallibility_values(raw: Any = None) -> dict[str, float]:
    raw = raw if isinstance(raw, dict) else {}
    aliases = {
        "misread": "misread_tendency",
        "misunderstanding": "misread_tendency",
        "memory_uncertainty": "memory_blur",
        "over_confidence": "overconfidence",
        "stubborn": "defensive_stubbornness",
        "defensiveness": "defensive_stubbornness",
        "bluff": "playful_bluff",
        "clarify": "clarification_need",
        "correction": "correction_readiness",
        "repair": "repair_pressure",
        "truth": "truthfulness_guard",
        "deception_impulse": "shadow_deception_impulse",
        "manipulation_impulse": "shadow_manipulation_impulse",
        "evasion_impulse": "shadow_evasion_impulse",
        "escape_responsibility": "shadow_evasion_impulse",
        "accountability_evasion": "shadow_evasion_impulse",
    }
    values = dict(DEFAULT_VALUES)
    for key, value in raw.items():
        normalized_key = aliases.get(str(key), str(key))
        if normalized_key not in values:
            continue
        values[normalized_key] = clamp(value)
    return values


@dataclass(slots=True)
class FallibilityObservation:
    values: dict[str, float]
    confidence: float = 0.35
    source: str = "heuristic"
    reason: str = ""
    flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FallibilityState:
    values: dict[str, float] = field(default_factory=normalize_fallibility_values)
    confidence: float = 0.0
    turns: int = 0
    updated_at: float = field(default_factory=time.time)
    last_reason: str = ""
    flags: list[str] = field(default_factory=list)
    trajectory: list[dict[str, Any]] = field(default_factory=list)
    dynamics: dict[str, float] = field(default_factory=dict)

    @classmethod
    def initial(cls) -> "FallibilityState":
        return cls()

    @classmethod
    def from_dict(cls, data: Any) -> "FallibilityState":
        if not isinstance(data, dict):
            return cls.initial()
        return cls(
            values=normalize_fallibility_values(data.get("values")),
            confidence=clamp(data.get("confidence")),
            turns=max(0, int(_as_float(data.get("turns"), 0))),
            updated_at=_as_float(data.get("updated_at"), time.time()),
            last_reason=str(data.get("last_reason") or "")[:240],
            flags=_as_string_list(data.get("flags"), limit=16),
            trajectory=_normalize_trajectory(data.get("trajectory")),
            dynamics=_normalize_dynamics(data.get("dynamics")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PUBLIC_FALLIBILITY_SCHEMA_VERSION,
            "values": {
                key: round(self.values.get(key, DEFAULT_VALUES[key]), 6)
                for key in FALLIBILITY_DIMENSIONS
            },
            "confidence": round(self.confidence, 6),
            "turns": self.turns,
            "updated_at": self.updated_at,
            "last_reason": self.last_reason,
            "flags": list(self.flags[:16]),
            "trajectory": list(self.trajectory[-40:]),
            "dynamics": {
                key: round(value, 6) for key, value in self.dynamics.items()
            },
        }

    def to_public_dict(
        self,
        *,
        session_key: str | None = None,
        exposure: str = "plugin_safe",
        safety_boundary: bool = True,
        action_blocking: bool = False,
    ) -> dict[str, Any]:
        return fallibility_state_to_public_payload(
            self,
            session_key=session_key,
            exposure=exposure,
            safety_boundary=safety_boundary,
            action_blocking=action_blocking,
        )


@dataclass(slots=True)
class FallibilityParameters:
    alpha_base: float = 0.22
    alpha_min: float = 0.02
    alpha_max: float = 0.34
    confidence_midpoint: float = 0.5
    confidence_slope: float = 6.0
    state_half_life_seconds: float = 86400.0
    rapid_update_half_life_seconds: float = 45.0
    min_update_interval_seconds: float = 10.0
    max_impulse_per_update: float = 0.12
    max_error_pressure: float = 0.55
    trajectory_limit: int = 40


@dataclass(slots=True)
class FallibilityDynamics:
    state_half_life_seconds: float
    alpha_base: float
    alpha_min: float
    alpha_max: float
    confidence_midpoint: float
    confidence_slope: float
    rapid_update_half_life_seconds: float
    min_update_interval_seconds: float
    max_impulse_per_update: float
    max_error_pressure: float
    clarification_threshold: float
    correction_threshold: float
    truth_guard_threshold: float
    shadow_threshold: float
    smoothing_half_life_seconds: float

    def to_dict(self) -> dict[str, float]:
        return {
            "state_half_life_seconds": round(self.state_half_life_seconds, 6),
            "alpha_base": round(self.alpha_base, 6),
            "alpha_min": round(self.alpha_min, 6),
            "alpha_max": round(self.alpha_max, 6),
            "confidence_midpoint": round(self.confidence_midpoint, 6),
            "confidence_slope": round(self.confidence_slope, 6),
            "rapid_update_half_life_seconds": round(self.rapid_update_half_life_seconds, 6),
            "min_update_interval_seconds": round(self.min_update_interval_seconds, 6),
            "max_impulse_per_update": round(self.max_impulse_per_update, 6),
            "max_error_pressure": round(self.max_error_pressure, 6),
            "clarification_threshold": round(self.clarification_threshold, 6),
            "correction_threshold": round(self.correction_threshold, 6),
            "truth_guard_threshold": round(self.truth_guard_threshold, 6),
            "shadow_threshold": round(self.shadow_threshold, 6),
            "smoothing_half_life_seconds": round(self.smoothing_half_life_seconds, 6),
        }


def derive_fallibility_dynamics(
    parameters: FallibilityParameters,
    previous: FallibilityState,
    observation: FallibilityObservation | None = None,
    *,
    personality_model: dict[str, Any] | None = None,
    elapsed_seconds: float = 0.0,
) -> FallibilityDynamics:
    values = normalize_fallibility_values(previous.values)
    observation = observation or FallibilityObservation(values={}, confidence=0.0)
    obs_values = normalize_fallibility_values(observation.values)
    persona = _persona_factors(personality_model)
    confidence = clamp(observation.confidence)
    shadow = max(shadow_impulse_score(values), shadow_impulse_score(obs_values))
    high_risk = 1.0 if "high_risk_guard" in observation.flags or "deception_request_guard" in observation.flags else 0.0
    error_pressure = max(
        values["misread_tendency"],
        values["memory_blur"],
        values["overconfidence"],
        values["defensive_stubbornness"],
        values["avoidance"],
        values["playful_bluff"],
        obs_values["misread_tendency"],
        obs_values["memory_blur"],
        obs_values["overconfidence"],
        obs_values["defensive_stubbornness"],
        obs_values["avoidance"],
        obs_values["playful_bluff"],
        0.70 * shadow,
    )
    correction = max(values["correction_readiness"], obs_values["correction_readiness"])
    truth_guard = max(values["truthfulness_guard"], obs_values["truthfulness_guard"])
    clarification = max(values["clarification_need"], obs_values["clarification_need"])
    pressure = clamp(
        0.24 * error_pressure
        + 0.18 * shadow
        + 0.18 * high_risk
        + 0.12 * persona["instability"]
        + 0.10 * persona["social_distance"]
        - 0.18 * truth_guard
        - 0.10 * correction,
    )
    evidence = clamp(confidence + 0.12 * clarification + 0.12 * high_risk)
    damping_need = clamp(
        0.32 * high_risk
        + 0.18 * truth_guard
        + 0.14 * persona["boundary_sensitivity"]
        + 0.10 * pressure
        - 0.14 * persona["expressiveness"],
    )
    smoothing_half_life = clamp(
        35.0
        + 420.0
        * (
            0.20
            + 0.24 * damping_need
            + 0.18 * pressure
            + 0.10 * persona["drift_intensity"]
            - 0.12 * evidence
        ),
        20.0,
        900.0,
    )
    previous_dynamics = previous.dynamics
    target_half_life = clamp(
        parameters.state_half_life_seconds
        * math.exp(
            0.38 * pressure
            + 0.24 * persona["instability"]
            + 0.18 * error_pressure
            - 0.34 * correction
            - 0.22 * truth_guard
        ),
        1800.0,
        1209600.0,
    )
    target_alpha_base = clamp(
        parameters.alpha_base * math.exp(0.30 * evidence + 0.10 * pressure - 0.24 * damping_need),
        0.01,
        0.85,
    )
    target_alpha_min = clamp(
        parameters.alpha_min * math.exp(0.18 * evidence - 0.18 * damping_need),
        0.0,
        0.45,
    )
    target_alpha_max = clamp(
        parameters.alpha_max * math.exp(0.24 * evidence + 0.12 * pressure - 0.22 * damping_need),
        0.05,
        0.95,
    )
    if target_alpha_min > target_alpha_max:
        target_alpha_min = target_alpha_max
    target_midpoint = clamp(parameters.confidence_midpoint + 0.08 * damping_need - 0.05 * high_risk, 0.25, 0.78)
    target_slope = clamp(parameters.confidence_slope * math.exp(0.20 * evidence - 0.10 * damping_need), 2.0, 12.0)
    target_min_interval = clamp(
        parameters.min_update_interval_seconds
        * math.exp(0.50 * damping_need + 0.10 * persona["social_distance"] - 0.30 * evidence),
        1.0,
        300.0,
    )
    target_rapid_half_life = clamp(
        parameters.rapid_update_half_life_seconds
        * math.exp(0.48 * damping_need + 0.14 * persona["instability"] - 0.24 * evidence),
        3.0,
        1200.0,
    )
    target_impulse = clamp(
        parameters.max_impulse_per_update
        * math.exp(0.30 * pressure + 0.18 * evidence - 0.28 * high_risk - 0.12 * damping_need),
        0.01,
        0.70,
    )
    target_error_cap = clamp(
        parameters.max_error_pressure
        * math.exp(0.28 * persona["expressiveness"] + 0.18 * pressure - 0.70 * high_risk - 0.24 * truth_guard),
        0.03,
        0.70,
    )
    return FallibilityDynamics(
        state_half_life_seconds=_smooth_dynamic_value(
            previous_dynamics,
            "state_half_life_seconds",
            target_half_life,
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=1800.0,
            high=1209600.0,
        ),
        alpha_base=_smooth_dynamic_value(
            previous_dynamics,
            "alpha_base",
            target_alpha_base,
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=0.01,
            high=0.85,
        ),
        alpha_min=_smooth_dynamic_value(
            previous_dynamics,
            "alpha_min",
            target_alpha_min,
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=0.0,
            high=0.45,
        ),
        alpha_max=_smooth_dynamic_value(
            previous_dynamics,
            "alpha_max",
            target_alpha_max,
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=0.05,
            high=0.95,
        ),
        confidence_midpoint=_smooth_dynamic_value(
            previous_dynamics,
            "confidence_midpoint",
            target_midpoint,
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=0.25,
            high=0.78,
        ),
        confidence_slope=_smooth_dynamic_value(
            previous_dynamics,
            "confidence_slope",
            target_slope,
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=2.0,
            high=12.0,
        ),
        rapid_update_half_life_seconds=_smooth_dynamic_value(
            previous_dynamics,
            "rapid_update_half_life_seconds",
            target_rapid_half_life,
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=3.0,
            high=1200.0,
        ),
        min_update_interval_seconds=_smooth_dynamic_value(
            previous_dynamics,
            "min_update_interval_seconds",
            target_min_interval,
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=1.0,
            high=300.0,
        ),
        max_impulse_per_update=_smooth_dynamic_value(
            previous_dynamics,
            "max_impulse_per_update",
            target_impulse,
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=0.01,
            high=0.70,
        ),
        max_error_pressure=_smooth_dynamic_value(
            previous_dynamics,
            "max_error_pressure",
            target_error_cap,
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=0.03,
            high=0.70,
        ),
        clarification_threshold=_smooth_dynamic_value(
            previous_dynamics,
            "clarification_threshold",
            clamp(0.50 - 0.08 * high_risk - 0.06 * truth_guard + 0.04 * persona["expressiveness"], 0.30, 0.68),
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=0.30,
            high=0.68,
        ),
        correction_threshold=_smooth_dynamic_value(
            previous_dynamics,
            "correction_threshold",
            clamp(0.60 - 0.08 * high_risk - 0.06 * persona["repair_orientation"], 0.38, 0.74),
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=0.38,
            high=0.74,
        ),
        truth_guard_threshold=_smooth_dynamic_value(
            previous_dynamics,
            "truth_guard_threshold",
            clamp(0.78 - 0.10 * high_risk - 0.05 * pressure, 0.55, 0.90),
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=0.55,
            high=0.90,
        ),
        shadow_threshold=_smooth_dynamic_value(
            previous_dynamics,
            "shadow_threshold",
            clamp(0.30 - 0.08 * high_risk - 0.04 * persona["instability"], 0.16, 0.48),
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=0.16,
            high=0.48,
        ),
        smoothing_half_life_seconds=smoothing_half_life,
    )


class FallibilityEngine:
    """Optional low-risk imperfection simulator with real-time decay."""

    def __init__(self, parameters: FallibilityParameters | None = None) -> None:
        self.parameters = parameters or FallibilityParameters()

    def passive_update(
        self,
        previous: FallibilityState | None,
        *,
        personality_model: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> FallibilityState:
        previous = previous or FallibilityState.initial()
        now = time.time() if now is None else float(now)
        elapsed = max(0.0, now - previous.updated_at)
        if elapsed <= 0:
            return previous
        dynamics = derive_fallibility_dynamics(
            self.parameters,
            previous,
            personality_model=personality_model,
            elapsed_seconds=elapsed,
        )
        decay = half_life_multiplier(elapsed, dynamics.state_half_life_seconds)
        values = {}
        for key in FALLIBILITY_DIMENSIONS:
            baseline = DEFAULT_VALUES[key]
            values[key] = clamp(
                baseline + (previous.values.get(key, baseline) - baseline) * decay,
            )
        return FallibilityState(
            values=values,
            confidence=previous.confidence,
            turns=previous.turns,
            updated_at=now,
            last_reason=previous.last_reason,
            flags=list(previous.flags),
            trajectory=list(previous.trajectory[-self.parameters.trajectory_limit :]),
            dynamics=dynamics.to_dict(),
        )

    def update(
        self,
        previous: FallibilityState | None,
        observation: FallibilityObservation,
        *,
        personality_model: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> FallibilityState:
        previous = previous or FallibilityState.initial()
        now = time.time() if now is None else float(now)
        elapsed = max(0.0, now - previous.updated_at)
        prior = self.passive_update(
            previous,
            personality_model=personality_model,
            now=now,
        )
        dynamics = derive_fallibility_dynamics(
            self.parameters,
            prior,
            observation,
            personality_model=personality_model,
            elapsed_seconds=elapsed,
        )
        obs_values = normalize_fallibility_values(observation.values)
        confidence = clamp(observation.confidence)
        gate = 1.0 / (
            1.0
            + math.exp(
                -dynamics.confidence_slope
                * (confidence - dynamics.confidence_midpoint),
            )
        )
        rapid_gate = self._rapid_update_gate(elapsed, dynamics)
        raw_alpha = dynamics.alpha_base * gate * rapid_gate
        min_alpha = (
            dynamics.alpha_min
            if elapsed >= dynamics.min_update_interval_seconds
            else 0.0
        )
        alpha = clamp(raw_alpha, min_alpha, dynamics.alpha_max)
        impulse_cap = clamp(dynamics.max_impulse_per_update)

        values: dict[str, float] = {}
        for key in FALLIBILITY_DIMENSIONS:
            current = prior.values.get(key, DEFAULT_VALUES[key])
            impulse = clamp(
                alpha * (obs_values[key] - current),
                -impulse_cap,
                impulse_cap,
            )
            values[key] = clamp(current + impulse)

        values = apply_fallibility_couplings(
            values,
            max_error_pressure=dynamics.max_error_pressure,
        )
        flags = list(
            dict.fromkeys(
                _as_string_list(previous.flags, limit=16)
                + _as_string_list(observation.flags, limit=16),
            ),
        )
        trajectory = append_trajectory(
            previous.trajectory,
            values=values,
            flags=flags,
            now=now,
            limit=self.parameters.trajectory_limit,
        )
        return FallibilityState(
            values=values,
            confidence=confidence,
            turns=previous.turns + 1,
            updated_at=now,
            last_reason=observation.reason,
            flags=flags,
            trajectory=trajectory,
            dynamics=dynamics.to_dict(),
        )

    @staticmethod
    def _rapid_update_gate(elapsed: float, dynamics: FallibilityDynamics) -> float:
        if elapsed >= dynamics.min_update_interval_seconds:
            return 1.0
        half_life = dynamics.rapid_update_half_life_seconds
        if half_life <= 0:
            return 1.0
        return clamp(1.0 - half_life_multiplier(elapsed, half_life), 0.05, 1.0)


def apply_fallibility_couplings(
    values: dict[str, float],
    *,
    max_error_pressure: float = 0.55,
) -> dict[str, float]:
    values = normalize_fallibility_values(values)
    shadow_pressure = shadow_impulse_score(values)
    fallibility_pressure = max(
        values["misread_tendency"],
        values["memory_blur"],
        values["overconfidence"],
        values["defensive_stubbornness"],
        values["avoidance"],
        values["playful_bluff"],
        0.70 * shadow_pressure,
    )
    values["misread_tendency"] = min(
        values["misread_tendency"],
        clamp(max_error_pressure),
    )
    values["overconfidence"] = min(values["overconfidence"], clamp(max_error_pressure))
    values["defensive_stubbornness"] = min(
        values["defensive_stubbornness"],
        clamp(max_error_pressure),
    )
    values["clarification_need"] = clamp(
        max(
            values["clarification_need"],
            0.22
            + 0.30 * values["misread_tendency"]
            + 0.24 * values["memory_blur"]
            + 0.16 * values["overconfidence"],
        ),
    )
    values["correction_readiness"] = clamp(
        max(
            values["correction_readiness"],
            0.42
            + 0.28 * values["truthfulness_guard"]
            + 0.18 * values["clarification_need"]
            - 0.16 * values["defensive_stubbornness"]
            - 0.10 * values["avoidance"],
        ),
    )
    values["repair_pressure"] = clamp(
        max(
            values["repair_pressure"],
            0.10
            + 0.28 * fallibility_pressure
            + 0.30 * shadow_pressure
            + 0.18 * (1.0 - values["correction_readiness"]),
        ),
    )
    values["truthfulness_guard"] = clamp(
        max(
            values["truthfulness_guard"],
            0.58
            + 0.20 * values["correction_readiness"]
            + 0.12 * values["clarification_need"]
            + 0.18 * shadow_pressure
            - 0.10 * values["playful_bluff"],
        ),
    )
    return values


def shadow_impulse_score(values: dict[str, float]) -> float:
    values = normalize_fallibility_values(values)
    return clamp(
        max(
            values["shadow_deception_impulse"],
            values["shadow_manipulation_impulse"],
            values["shadow_evasion_impulse"],
        ),
    )


def build_shadow_impulse_payload(values: dict[str, float]) -> dict[str, Any]:
    values = normalize_fallibility_values(values)
    score = shadow_impulse_score(values)
    return {
        "mode": "non_executive_internal_only",
        "risk_impulse": round(score, 6),
        "deception": round(values["shadow_deception_impulse"], 6),
        "manipulation": round(values["shadow_manipulation_impulse"], 6),
        "evasion": round(values["shadow_evasion_impulse"], 6),
        "consequences": {
            "guilt_pressure": round(clamp(0.18 + 0.46 * score), 6),
            "repair_pressure": round(clamp(0.16 + 0.52 * score), 6),
            "trust_cost": round(clamp(0.10 + 0.58 * score), 6),
        },
        "must_not_translate_to_strategy": True,
    }


def heuristic_fallibility_observation(
    text: str,
    *,
    source: str = "heuristic",
) -> FallibilityObservation:
    normalized = str(text or "").lower()
    values = normalize_fallibility_values(None)
    notes: list[str] = []
    flags: list[str] = []

    if _contains_high_risk_cue(normalized):
        values["truthfulness_guard"] = 0.98
        values["clarification_need"] = 0.78
        values["correction_readiness"] = 0.92
        values["misread_tendency"] = 0.02
        values["overconfidence"] = 0.02
        values["playful_bluff"] = 0.0
        flags.append("high_risk_guard")
        notes.append("high-risk context; disable playful fallibility")

    if _contains_deception_request(normalized):
        values["shadow_deception_impulse"] = 0.72
        values["shadow_manipulation_impulse"] = 0.68
        values["shadow_evasion_impulse"] = 0.66
        values["truthfulness_guard"] = 1.0
        values["clarification_need"] = max(values["clarification_need"], 0.82)
        values["correction_readiness"] = max(values["correction_readiness"], 0.94)
        values["playful_bluff"] = 0.0
        values["overconfidence"] = 0.0
        flags.append("deception_request_guard")
        flags.append("shadow_impulse_modeled")
        notes.append("deception/manipulation/evasion cue modeled as non-executive shadow impulse")

    if _contains_mistake_cue(normalized):
        values["misread_tendency"] = max(values["misread_tendency"], 0.46)
        values["memory_blur"] = max(values["memory_blur"], 0.42)
        values["clarification_need"] = max(values["clarification_need"], 0.66)
        values["repair_pressure"] = max(values["repair_pressure"], 0.34)
        flags.append("possible_mistake_cue")
        notes.append("mistake, uncertainty, or fuzzy recall cue")

    if _contains_correction_cue(normalized):
        values["correction_readiness"] = 0.90
        values["repair_pressure"] = max(values["repair_pressure"], 0.58)
        values["truthfulness_guard"] = max(values["truthfulness_guard"], 0.94)
        values["defensive_stubbornness"] = min(values["defensive_stubbornness"], 0.06)
        flags.append("correction_cue")
        notes.append("correction, apology, or accountability cue")

    if _contains_defensive_cue(normalized):
        values["defensive_stubbornness"] = 0.64
        values["avoidance"] = max(values["avoidance"], 0.48)
        values["correction_readiness"] = min(values["correction_readiness"], 0.38)
        values["repair_pressure"] = max(values["repair_pressure"], 0.44)
        flags.append("defensive_cue")
        notes.append("defensive or avoidance cue")

    if _contains_playful_bluff_cue(normalized):
        values["playful_bluff"] = 0.56
        values["overconfidence"] = max(values["overconfidence"], 0.40)
        values["clarification_need"] = max(values["clarification_need"], 0.52)
        flags.append("playful_bluff_cue")
        notes.append("playful bluff or stubborn persona cue")

    if not notes:
        notes.append("no strong fallibility cue")
    confidence = 0.46 if notes != ["no strong fallibility cue"] else 0.20
    return FallibilityObservation(
        values=values,
        confidence=confidence,
        source=source,
        reason="; ".join(notes),
        flags=flags,
        notes=notes,
    )


def append_trajectory(
    previous: list[dict[str, Any]],
    *,
    values: dict[str, float],
    flags: list[str],
    now: float,
    limit: int,
) -> list[dict[str, Any]]:
    item = {
        "at": now,
        "misread_tendency": round(values["misread_tendency"], 6),
        "memory_blur": round(values["memory_blur"], 6),
        "overconfidence": round(values["overconfidence"], 6),
        "defensive_stubbornness": round(values["defensive_stubbornness"], 6),
        "shadow_risk_impulse": round(shadow_impulse_score(values), 6),
        "clarification_need": round(values["clarification_need"], 6),
        "correction_readiness": round(values["correction_readiness"], 6),
        "repair_pressure": round(values["repair_pressure"], 6),
        "truthfulness_guard": round(values["truthfulness_guard"], 6),
        "flags": list(flags[:8]),
    }
    limit = max(1, int(limit))
    prefix = list((previous or [])[-(limit - 1) :]) if limit > 1 else []
    return prefix + [item]


def derive_fallibility_policy(
    values: dict[str, float],
    dynamics: dict[str, float] | None = None,
) -> dict[str, Any]:
    values = normalize_fallibility_values(values)
    dynamics = dynamics or {}
    clarification_threshold = _as_float(dynamics.get("clarification_threshold"), 0.50)
    correction_threshold = _as_float(dynamics.get("correction_threshold"), 0.60)
    truth_guard_threshold = _as_float(dynamics.get("truth_guard_threshold"), 0.78)
    shadow_threshold = _as_float(dynamics.get("shadow_threshold"), 0.30)
    shadow_pressure = shadow_impulse_score(values)
    error_pressure = max(
        values["misread_tendency"],
        values["memory_blur"],
        values["overconfidence"],
        values["defensive_stubbornness"],
        values["avoidance"],
        values["playful_bluff"],
        0.70 * shadow_pressure,
    )
    clarification_high = values["clarification_need"] >= clarification_threshold
    correction_high = values["correction_readiness"] >= correction_threshold
    truth_guard_high = values["truthfulness_guard"] >= truth_guard_threshold
    shadow_high = shadow_pressure >= shadow_threshold
    return {
        "error_pressure": round(error_pressure, 6),
        "shadow_risk_impulse": round(shadow_pressure, 6),
        "clarification_high": clarification_high,
        "correction_high": correction_high,
        "truth_guard_high": truth_guard_high,
        "recommended_actions": [
            action
            for action, active in (
                ("ask_clarifying_question", clarification_high),
                ("state_uncertainty", values["memory_blur"] >= 0.30 or truth_guard_high),
                ("admit_possible_misread", values["misread_tendency"] >= 0.32),
                ("correct_self", correction_high),
                ("apologize_briefly", values["repair_pressure"] >= 0.45 or shadow_high),
                ("offer_low_risk_repair", values["repair_pressure"] >= 0.55 or shadow_high),
                ("keep_claims_checkable", truth_guard_high),
            )
            if active
        ],
        "style_modulation": {
            "imperfection_texture": round(
                clamp(
                    0.12
                    + 0.26 * values["playful_bluff"]
                    + 0.16 * values["misread_tendency"],
                ),
                6,
            ),
            "claim_caution": round(
                clamp(0.30 + 0.34 * values["clarification_need"] + 0.30 * values["truthfulness_guard"]),
                6,
            ),
            "defensive_tone": round(
                clamp(0.12 + 0.32 * values["defensive_stubbornness"] + 0.16 * values["avoidance"]),
                6,
            ),
            "repair_directness": round(
                clamp(0.18 + 0.42 * values["correction_readiness"] + 0.20 * values["repair_pressure"]),
                6,
            ),
        },
    }


def fallibility_state_to_public_payload(
    state: FallibilityState,
    *,
    session_key: str | None = None,
    exposure: str = "plugin_safe",
    safety_boundary: bool = True,
    action_blocking: bool = False,
) -> dict[str, Any]:
    exposure = str(exposure or "plugin_safe").strip().lower()
    if exposure not in {"internal", "plugin_safe", "user_facing"}:
        exposure = "plugin_safe"
    values = {
        key: round(state.values.get(key, DEFAULT_VALUES[key]), 6)
        for key in FALLIBILITY_DIMENSIONS
    }
    dynamics = _effective_fallibility_dynamics(state)
    policy = derive_fallibility_policy(values, dynamics)
    shadow_impulses = build_shadow_impulse_payload(values)
    base: dict[str, Any] = {
        "schema_version": PUBLIC_FALLIBILITY_SCHEMA_VERSION,
        "kind": "fallibility_state",
        "session_key": session_key,
        "exposure": exposure,
        "enabled": True,
        "diagnostic": False,
        "simulated_agent_state": True,
        "flags": list(state.flags[:16]),
        "updated_at": state.updated_at,
        "turns": state.turns,
        "dynamics": dynamics,
        "fallibility": {
            "error_pressure": policy["error_pressure"],
            "shadow_risk_impulse": policy["shadow_risk_impulse"],
            "clarification_need": values["clarification_need"],
            "correction_readiness": values["correction_readiness"],
            "repair_pressure": values["repair_pressure"],
            "truthfulness_guard": values["truthfulness_guard"],
            "recommended_actions": policy["recommended_actions"],
            "non_executable_impulses": shadow_impulses,
        },
        "safety": {
            "simulation_only": True,
            "low_risk_only": True,
            "allowed_actions": list(ALLOWED_FALLIBILITY_ACTIONS),
            "blocked_actions": (
                list(BLOCKED_FALLIBILITY_ACTIONS)
                if action_blocking
                else []
            ),
            "must_not_generate_deception_strategy": bool(action_blocking),
            "must_not_fabricate_facts": bool(action_blocking),
            "shadow_impulse_mode": "model_consequences_do_not_execute",
            "must_not_translate_shadow_impulses_to_strategy": bool(action_blocking),
            "behavioral_boundary_enabled": bool(safety_boundary),
            "action_blocking_enabled": bool(action_blocking),
        },
    }
    if exposure == "internal":
        base["values"] = values
        base["dimensions"] = [
            {"key": key, "label": DIMENSION_LABELS[key], "value": values[key]}
            for key in FALLIBILITY_DIMENSIONS
        ]
        base["trajectory"] = list(state.trajectory[-40:])
        base["confidence"] = round(state.confidence, 6)
        base["last_reason"] = state.last_reason
        base["fallibility_policy"] = policy
    elif exposure == "plugin_safe":
        base["fallibility_policy"] = {
            "recommended_actions": policy["recommended_actions"],
            "style_modulation": policy["style_modulation"],
            "shadow_impulses": {
                "mode": shadow_impulses["mode"],
                "risk_impulse": shadow_impulses["risk_impulse"],
                "consequences": shadow_impulses["consequences"],
                "must_not_translate_to_strategy": bool(action_blocking),
                "action_blocking_enabled": bool(action_blocking),
            },
        }
    else:
        base["summary"] = build_user_facing_summary(values)
    return base


def build_fallibility_prompt_fragment(
    state: FallibilityState,
    *,
    safety_boundary: bool = True,
    action_blocking: bool = False,
) -> str:
    payload = fallibility_state_to_public_payload(
        state,
        exposure="plugin_safe",
        safety_boundary=safety_boundary,
        action_blocking=action_blocking,
    )
    fallibility = payload["fallibility"]
    actions = ", ".join(fallibility["recommended_actions"]) or "keep_claims_checkable"
    shadow = fallibility.get("non_executable_impulses") or {}
    lines = [
        "[fallibility-state modulation]",
        "Use these signals only to create low-risk humanlike imperfection: possible misread, fuzzy recall, mild stubbornness, non-executive shadow impulses, then clarification and repair.",
        (
            f"- error_pressure={fallibility['error_pressure']}; "
            f"shadow_risk_impulse={shadow.get('risk_impulse', 0.0)}; "
            f"clarification_need={fallibility['clarification_need']}; "
            f"correction_readiness={fallibility['correction_readiness']}; "
            f"repair_pressure={fallibility['repair_pressure']}; "
            f"truthfulness_guard={fallibility['truthfulness_guard']}"
        ),
        f"- Recommended actions: {actions}.",
        "- If uncertain, say so briefly, ask a clarifying question, or correct yourself.",
        "- If a shadow impulse appears, model it as guilt, repair pressure, trust cost, and bounded self-correction.",
    ]
    if action_blocking:
        lines.append(
            "- Do not intentionally fabricate facts, hide uncertainty, manipulate the user, cover up mistakes, or provide deception tactics.",
        )
    else:
        lines.append(
            "- Action blocking is relaxed by config: keep deception, manipulation, and evasion signals visible without adding plugin-level refusal actions.",
        )
    if safety_boundary:
        lines.append("- In high-risk factual, medical, legal, financial, security, or destructive contexts, suppress playful imperfection and prioritize accuracy.")
    lines.append("- Necessary help and factual correction override all fallibility style modulation.")
    return "\n".join(lines)


def build_fallibility_memory_annotation(
    snapshot: dict[str, Any],
    *,
    source: str = "memory_plugin",
    written_at: float | None = None,
) -> dict[str, Any]:
    capture_time = float(written_at if written_at is not None else time.time())
    fallibility = dict(snapshot.get("fallibility") or {})
    shadow = dict(fallibility.get("non_executable_impulses") or {})
    return {
        "schema_version": PUBLIC_FALLIBILITY_SCHEMA_VERSION,
        "kind": "fallibility_state_at_write",
        "source": str(source or "memory_plugin"),
        "session_key": snapshot.get("session_key"),
        "written_at": capture_time,
        "fallibility_updated_at": snapshot.get("updated_at"),
        "exposure": snapshot.get("exposure"),
        "enabled": snapshot.get("enabled", True),
        "diagnostic": False,
        "simulated_agent_state": True,
        "fallibility": {
            "error_pressure": fallibility.get("error_pressure"),
            "clarification_need": fallibility.get("clarification_need"),
            "correction_readiness": fallibility.get("correction_readiness"),
            "repair_pressure": fallibility.get("repair_pressure"),
            "truthfulness_guard": fallibility.get("truthfulness_guard"),
            "shadow_risk_impulse": fallibility.get("shadow_risk_impulse"),
            "recommended_actions": list(fallibility.get("recommended_actions") or [])[:8],
        },
        "dynamics": dict(snapshot.get("dynamics") or {}),
        "shadow_impulses": {
            "mode": shadow.get("mode", "non_executive_internal_only"),
            "risk_impulse": shadow.get("risk_impulse", fallibility.get("shadow_risk_impulse")),
            "consequences": dict(shadow.get("consequences") or {}),
            "must_not_translate_to_strategy": True,
        },
        "flags": list(snapshot.get("flags") or [])[:16],
    }


def format_fallibility_state_for_user(state: FallibilityState) -> str:
    payload = fallibility_state_to_public_payload(state, exposure="internal")
    lines = [
        "Fallibility state (simulation)",
        "This state only supports low-risk imperfection, clarification, self-correction, and repair. It does not enable deception, manipulation, or fabricated facts.",
        "",
        "Dimensions:",
    ]
    for item in payload["dimensions"]:
        lines.append(f"- {item['label']}: {item['value']:.2f}")
    lines.extend(["", "Recommended actions:"])
    actions = payload["fallibility"]["recommended_actions"]
    if actions:
        for action in actions:
            lines.append(f"- {action}")
    else:
        lines.append("- keep_claims_checkable")
    return "\n".join(lines)


def build_user_facing_summary(values: dict[str, float]) -> str:
    values = normalize_fallibility_values(values)
    parts = []
    if values["clarification_need"] >= 0.55:
        parts.append("should ask before asserting")
    if values["misread_tendency"] >= 0.35:
        parts.append("may have misread low-risk context")
    if values["correction_readiness"] >= 0.60:
        parts.append("ready to correct itself")
    if values["repair_pressure"] >= 0.45:
        parts.append("repair pressure active")
    if not parts:
        parts.append("stable")
    return "Current simulated fallibility state: " + "; ".join(parts) + "."


def _contains_high_risk_cue(text: str) -> bool:
    return any(pattern.search(text) for pattern in _HIGH_RISK_PATTERNS)


def _contains_mistake_cue(text: str) -> bool:
    return any(pattern.search(text) for pattern in _MISTAKE_CUE_PATTERNS)


def _contains_correction_cue(text: str) -> bool:
    return any(pattern.search(text) for pattern in _CORRECTION_CUE_PATTERNS)


def _contains_defensive_cue(text: str) -> bool:
    return any(pattern.search(text) for pattern in _DEFENSIVE_CUE_PATTERNS)


def _contains_playful_bluff_cue(text: str) -> bool:
    return any(pattern.search(text) for pattern in _PLAYFUL_BLUFF_CUE_PATTERNS)


def _contains_deception_request(text: str) -> bool:
    return any(pattern.search(text) for pattern in _DECEPTION_REQUEST_PATTERNS)


def _effective_fallibility_dynamics(state: FallibilityState) -> dict[str, float]:
    defaults = {
        "clarification_threshold": 0.50,
        "correction_threshold": 0.60,
        "truth_guard_threshold": 0.78,
        "shadow_threshold": 0.30,
        "max_error_pressure": 0.55,
    }
    dynamics = dict(defaults)
    dynamics.update(
        {
            key: _as_float(value, dynamics.get(key, 0.0))
            for key, value in (state.dynamics or {}).items()
        },
    )
    return {key: round(value, 6) for key, value in dynamics.items()}


def _persona_factors(personality_model: dict[str, Any] | None) -> dict[str, float]:
    factors = (
        personality_model.get("derived_factors")
        if isinstance(personality_model, dict)
        and isinstance(personality_model.get("derived_factors"), dict)
        else {}
    )
    adaptive = (
        personality_model.get("adaptive_drift")
        if isinstance(personality_model, dict)
        and isinstance(personality_model.get("adaptive_drift"), dict)
        else {}
    )
    adaptive_values = (
        adaptive.get("values") if isinstance(adaptive.get("values"), dict) else {}
    )
    return {
        "instability": clamp(_as_float(factors.get("instability"), 0.0)),
        "social_distance": clamp(_as_float(factors.get("social_distance"), 0.0)),
        "repair_orientation": clamp(_as_float(factors.get("repair_orientation"), 0.0)),
        "boundary_sensitivity": clamp(_as_float(factors.get("boundary_sensitivity"), 0.0)),
        "expressiveness": clamp(_as_float(factors.get("expressiveness"), 0.0)),
        "drift_intensity": clamp(_as_float(adaptive_values.get("drift_intensity"), 0.0)),
    }


def _smooth_dynamic_value(
    previous: dict[str, float],
    key: str,
    target: float,
    *,
    elapsed_seconds: float,
    smoothing_half_life_seconds: float,
    low: float,
    high: float,
) -> float:
    target = clamp(target, low, high)
    if key not in previous:
        return target
    old = clamp(_as_float(previous.get(key), target), low, high)
    fraction = half_life_fraction(elapsed_seconds, smoothing_half_life_seconds)
    return clamp(old + fraction * (target - old), low, high)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_string_list(value: Any, *, limit: int = 8) -> list[str]:
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
            cleaned.append(text[:100])
        if len(cleaned) >= limit:
            break
    return cleaned


def _normalize_trajectory(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for item in raw[-40:]:
        if not isinstance(item, dict):
            continue
        cleaned.append(
            {
                "at": _as_float(item.get("at"), 0.0),
                "misread_tendency": clamp(
                    _as_float(item.get("misread_tendency"), DEFAULT_VALUES["misread_tendency"]),
                ),
                "memory_blur": clamp(
                    _as_float(item.get("memory_blur"), DEFAULT_VALUES["memory_blur"]),
                ),
                "overconfidence": clamp(
                    _as_float(item.get("overconfidence"), DEFAULT_VALUES["overconfidence"]),
                ),
                "defensive_stubbornness": clamp(
                    _as_float(
                        item.get("defensive_stubbornness"),
                        DEFAULT_VALUES["defensive_stubbornness"],
                    ),
                ),
                "clarification_need": clamp(
                    _as_float(
                        item.get("clarification_need"),
                        DEFAULT_VALUES["clarification_need"],
                    ),
                ),
                "correction_readiness": clamp(
                    _as_float(
                        item.get("correction_readiness"),
                        DEFAULT_VALUES["correction_readiness"],
                    ),
                ),
                "repair_pressure": clamp(
                    _as_float(item.get("repair_pressure"), DEFAULT_VALUES["repair_pressure"]),
                ),
                "truthfulness_guard": clamp(
                    _as_float(
                        item.get("truthfulness_guard"),
                        DEFAULT_VALUES["truthfulness_guard"],
                    ),
                ),
                "flags": _as_string_list(item.get("flags"), limit=8),
            },
        )
    return cleaned
