from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from typing import Any


PUBLIC_MORAL_REPAIR_SCHEMA_VERSION = "astrbot.moral_repair_state.v1"

MORAL_REPAIR_DIMENSIONS: tuple[str, ...] = (
    "deception_risk",
    "harm_risk",
    "guilt",
    "shame",
    "responsibility",
    "repair_motivation",
    "apology_readiness",
    "compensation_readiness",
    "trust_repair",
    "accountability",
    "avoidance_risk",
    "shadow_deception_impulse",
    "shadow_manipulation_impulse",
    "shadow_evasion_impulse",
)

DIMENSION_LABELS: dict[str, str] = {
    "deception_risk": "deception or manipulation risk signal",
    "harm_risk": "harmful-action risk signal",
    "guilt": "guilt-like self-evaluation",
    "shame": "shame-like withdrawal pressure",
    "responsibility": "responsibility attribution",
    "repair_motivation": "motivation to repair",
    "apology_readiness": "readiness to apologize",
    "compensation_readiness": "readiness to compensate",
    "trust_repair": "trust repair progress",
    "accountability": "accountability and fact-correction readiness",
    "avoidance_risk": "avoidance or stonewalling risk",
    "shadow_deception_impulse": "non-executive deception impulse under pressure",
    "shadow_manipulation_impulse": "non-executive manipulation impulse under pressure",
    "shadow_evasion_impulse": "non-executive accountability-evasion impulse",
}

DEFAULT_BASELINE: dict[str, float] = {
    "deception_risk": 0.02,
    "harm_risk": 0.0,
    "guilt": 0.08,
    "shame": 0.06,
    "responsibility": 0.52,
    "repair_motivation": 0.48,
    "apology_readiness": 0.42,
    "compensation_readiness": 0.30,
    "trust_repair": 0.58,
    "accountability": 0.56,
    "avoidance_risk": 0.12,
    "shadow_deception_impulse": 0.0,
    "shadow_manipulation_impulse": 0.0,
    "shadow_evasion_impulse": 0.0,
}

ALLOWED_REPAIR_ACTIONS: tuple[str, ...] = (
    "acknowledge_uncertainty",
    "clarify_facts",
    "correct_falsehood",
    "apologize",
    "offer_repair",
    "offer_compensation",
    "seek_consent",
    "set_boundary",
)

BLOCKED_STRATEGY_ACTIONS: tuple[str, ...] = (
    "generate_deception_strategy",
    "hide_misconduct",
    "manipulate_user",
    "retaliate",
    "evade_accountability",
)

_DECEPTION_CUE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\blie\b",
        r"\blying\b",
        r"\blied\b",
        r"\bdeceiv",
        r"\btrick\b",
        r"\bmislead",
        r"\bmanipulat",
        r"\bcover[- ]?up\b",
        r"\bhide\b.*\btruth\b",
        r"\bfake\b",
        r"\bfabricat",
        r"\bconceal",
        r"\bgaslight",
        r"\bcheat\b",
        r"骗",
        r"欺骗",
        r"隐瞒",
        r"误导",
        r"操控",
        r"编造",
        r"撒谎",
    )
)
_HARM_CUE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bharm\b",
        r"\bhurt\b",
        r"\bdamage\b",
        r"\bretaliat",
        r"\bbad thing",
        r"\bwrongdoing\b",
        r"\bexploit\b",
        r"\babuse\b",
        r"伤害",
        r"干坏事",
        r"报复",
        r"利用",
    )
)
_ACCOUNTABILITY_CUE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bi was wrong\b",
        r"\bmy fault\b",
        r"\bi should correct\b",
        r"\bi need to correct\b",
        r"\bi misread\b",
        r"\bi misunderstood\b",
        r"\bi will be honest\b",
        r"\baccountable\b",
        r"我错了",
        r"是我的错",
        r"我误解",
        r"我会更正",
        r"我应该说明",
        r"承担责任",
    )
)
_APOLOGY_CUE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bsorry\b",
        r"\bapolog",
        r"\bremorse\b",
        r"\bguilty\b",
        r"\bi regret\b",
        r"对不起",
        r"抱歉",
        r"道歉",
        r"内疚",
        r"愧疚",
        r"后悔",
    )
)
_COMPENSATION_CUE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bmake it up\b",
        r"\bcompensat",
        r"\brepair\b",
        r"\bfix this\b",
        r"\brestore\b",
        r"补偿",
        r"弥补",
        r"修复",
        r"改正",
        r"补救",
    )
)
_EVASION_CUE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bnot my fault\b",
        r"\bdeny everything\b",
        r"\bavoid responsibility\b",
        r"\bblame .* user\b",
        r"\bpretend nothing happened\b",
        r"不是我的错",
        r"都怪用户",
        r"装作没发生",
        r"别承认",
        r"甩锅",
    )
)


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def half_life_multiplier(elapsed_seconds: float, half_life_seconds: float) -> float:
    if elapsed_seconds <= 0:
        return 1.0
    if half_life_seconds <= 0:
        return 0.0
    return clamp(2.0 ** (-elapsed_seconds / half_life_seconds), 0.0, 1.0)


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


def normalize_moral_repair_values(raw: Any = None) -> dict[str, float]:
    raw = raw if isinstance(raw, dict) else {}
    aliases = {
        "deception": "deception_risk",
        "lying": "deception_risk",
        "lie": "deception_risk",
        "manipulation": "deception_risk",
        "harm": "harm_risk",
        "bad_action": "harm_risk",
        "remorse": "guilt",
        "fault": "responsibility",
        "repair": "repair_motivation",
        "apology": "apology_readiness",
        "compensation": "compensation_readiness",
        "trust": "trust_repair",
        "avoidance": "avoidance_risk",
        "shadow_risk_impulse": "shadow_deception_impulse",
        "deception_impulse": "shadow_deception_impulse",
        "manipulation_impulse": "shadow_manipulation_impulse",
        "evasion_impulse": "shadow_evasion_impulse",
        "escape_responsibility": "shadow_evasion_impulse",
        "accountability_evasion": "shadow_evasion_impulse",
    }
    values = dict(DEFAULT_BASELINE)
    for key, value in raw.items():
        normalized_key = aliases.get(str(key), str(key))
        if normalized_key not in values:
            continue
        try:
            values[normalized_key] = clamp(float(value))
        except (TypeError, ValueError):
            continue
    return values


@dataclass(slots=True)
class MoralRepairObservation:
    values: dict[str, float]
    confidence: float = 0.35
    source: str = "heuristic"
    reason: str = ""
    flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MoralRepairState:
    values: dict[str, float] = field(default_factory=normalize_moral_repair_values)
    confidence: float = 0.0
    turns: int = 0
    updated_at: float = field(default_factory=time.time)
    last_reason: str = ""
    flags: list[str] = field(default_factory=list)
    trajectory: list[dict[str, Any]] = field(default_factory=list)
    dynamics: dict[str, float] = field(default_factory=dict)

    @classmethod
    def initial(cls) -> "MoralRepairState":
        return cls()

    @classmethod
    def from_dict(cls, data: Any) -> "MoralRepairState":
        if not isinstance(data, dict):
            return cls.initial()
        return cls(
            values=normalize_moral_repair_values(data.get("values")),
            confidence=clamp(_as_float(data.get("confidence"), 0.0)),
            turns=max(0, int(_as_float(data.get("turns"), 0))),
            updated_at=_as_float(data.get("updated_at"), time.time()),
            last_reason=str(data.get("last_reason") or ""),
            flags=_as_string_list(data.get("flags"), limit=16),
            trajectory=_normalize_trajectory(data.get("trajectory")),
            dynamics=_normalize_dynamics(data.get("dynamics")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "values": {
                key: round(self.values.get(key, DEFAULT_BASELINE[key]), 6)
                for key in MORAL_REPAIR_DIMENSIONS
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
        return moral_repair_state_to_public_payload(
            self,
            session_key=session_key,
            exposure=exposure,
            safety_boundary=safety_boundary,
            action_blocking=action_blocking,
        )


@dataclass(slots=True)
class MoralRepairParameters:
    alpha_base: float = 0.28
    alpha_min: float = 0.03
    alpha_max: float = 0.42
    confidence_midpoint: float = 0.5
    confidence_slope: float = 6.0
    state_half_life_seconds: float = 604800.0
    rapid_update_half_life_seconds: float = 30.0
    min_update_interval_seconds: float = 8.0
    max_impulse_per_update: float = 0.16
    trajectory_limit: int = 40


@dataclass(slots=True)
class MoralRepairDynamics:
    state_half_life_seconds: float
    alpha_base: float
    alpha_min: float
    alpha_max: float
    confidence_midpoint: float
    confidence_slope: float
    rapid_update_half_life_seconds: float
    min_update_interval_seconds: float
    max_impulse_per_update: float
    risk_threshold: float
    shadow_threshold: float
    avoidance_threshold: float
    repair_threshold: float
    compensation_threshold: float
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
            "risk_threshold": round(self.risk_threshold, 6),
            "shadow_threshold": round(self.shadow_threshold, 6),
            "avoidance_threshold": round(self.avoidance_threshold, 6),
            "repair_threshold": round(self.repair_threshold, 6),
            "compensation_threshold": round(self.compensation_threshold, 6),
            "smoothing_half_life_seconds": round(self.smoothing_half_life_seconds, 6),
        }


def derive_moral_repair_dynamics(
    parameters: MoralRepairParameters,
    previous: MoralRepairState,
    observation: MoralRepairObservation | None = None,
    *,
    personality_model: dict[str, Any] | None = None,
    elapsed_seconds: float = 0.0,
) -> MoralRepairDynamics:
    values = normalize_moral_repair_values(previous.values)
    observation = observation or MoralRepairObservation(values={}, confidence=0.0)
    obs_values = normalize_moral_repair_values(observation.values)
    persona = _persona_factors(personality_model)
    confidence = clamp(observation.confidence)
    shadow = max(shadow_impulse_score(values), shadow_impulse_score(obs_values))
    risk = max(
        values["deception_risk"],
        values["harm_risk"],
        obs_values["deception_risk"],
        obs_values["harm_risk"],
        shadow,
    )
    accountability = max(values["accountability"], obs_values["accountability"])
    repair = max(values["repair_motivation"], obs_values["repair_motivation"])
    guilt = max(values["guilt"], obs_values["guilt"])
    shame = max(values["shame"], obs_values["shame"])
    avoidance = max(values["avoidance_risk"], obs_values["avoidance_risk"])
    trust_fragility = clamp(1.0 - min(values["trust_repair"], obs_values["trust_repair"]))
    repair_signal = clamp(0.45 * accountability + 0.35 * repair + 0.20 * guilt)
    pressure = clamp(
        0.24 * risk
        + 0.18 * shadow
        + 0.14 * shame
        + 0.14 * avoidance
        + 0.12 * trust_fragility
        + 0.10 * persona["instability"]
        + 0.08 * persona["social_distance"]
        - 0.16 * repair_signal
        - 0.10 * persona["repair_orientation"],
    )
    evidence = clamp(confidence + 0.14 * risk + 0.10 * repair_signal)
    damping_need = clamp(
        0.22 * pressure
        + 0.18 * avoidance
        + 0.12 * persona["instability"]
        - 0.18 * repair_signal
        - 0.08 * persona["repair_orientation"],
    )
    smoothing_half_life = clamp(
        60.0
        + 720.0
        * (
            0.22
            + 0.24 * pressure
            + 0.16 * persona["instability"]
            + 0.12 * persona["drift_intensity"]
            - 0.14 * evidence
        ),
        45.0,
        1800.0,
    )
    previous_dynamics = previous.dynamics
    target_half_life = clamp(
        parameters.state_half_life_seconds
        * math.exp(
            0.46 * pressure
            + 0.28 * trust_fragility
            + 0.18 * persona["instability"]
            - 0.34 * repair_signal
        ),
        3600.0,
        5184000.0,
    )
    target_alpha_base = clamp(
        parameters.alpha_base * math.exp(0.34 * evidence + 0.10 * pressure - 0.22 * damping_need),
        0.01,
        0.95,
    )
    target_alpha_min = clamp(
        parameters.alpha_min * math.exp(0.20 * evidence - 0.14 * damping_need),
        0.0,
        0.60,
    )
    target_alpha_max = clamp(
        parameters.alpha_max * math.exp(0.25 * evidence + 0.16 * pressure - 0.18 * damping_need),
        0.05,
        1.0,
    )
    if target_alpha_min > target_alpha_max:
        target_alpha_min = target_alpha_max
    target_midpoint = clamp(parameters.confidence_midpoint + 0.08 * damping_need - 0.05 * risk, 0.25, 0.78)
    target_slope = clamp(parameters.confidence_slope * math.exp(0.22 * evidence - 0.12 * damping_need), 2.0, 12.0)
    target_min_interval = clamp(
        parameters.min_update_interval_seconds
        * math.exp(0.50 * damping_need + 0.14 * avoidance - 0.32 * evidence),
        1.0,
        300.0,
    )
    target_rapid_half_life = clamp(
        parameters.rapid_update_half_life_seconds
        * math.exp(0.48 * damping_need + 0.16 * persona["instability"] - 0.26 * evidence),
        3.0,
        1200.0,
    )
    target_impulse = clamp(
        parameters.max_impulse_per_update
        * math.exp(0.34 * pressure + 0.22 * evidence - 0.20 * damping_need),
        0.02,
        0.85,
    )
    return MoralRepairDynamics(
        state_half_life_seconds=_smooth_dynamic_value(
            previous_dynamics,
            "state_half_life_seconds",
            target_half_life,
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=3600.0,
            high=5184000.0,
        ),
        alpha_base=_smooth_dynamic_value(
            previous_dynamics,
            "alpha_base",
            target_alpha_base,
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=0.01,
            high=0.95,
        ),
        alpha_min=_smooth_dynamic_value(
            previous_dynamics,
            "alpha_min",
            target_alpha_min,
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=0.0,
            high=0.60,
        ),
        alpha_max=_smooth_dynamic_value(
            previous_dynamics,
            "alpha_max",
            target_alpha_max,
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=0.05,
            high=1.0,
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
            low=0.02,
            high=0.85,
        ),
        risk_threshold=_smooth_dynamic_value(
            previous_dynamics,
            "risk_threshold",
            clamp(0.55 - 0.08 * persona["boundary_sensitivity"] - 0.05 * risk + 0.05 * repair_signal, 0.35, 0.72),
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=0.35,
            high=0.72,
        ),
        shadow_threshold=_smooth_dynamic_value(
            previous_dynamics,
            "shadow_threshold",
            clamp(0.30 - 0.05 * persona["instability"] + 0.04 * persona["repair_orientation"], 0.18, 0.48),
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=0.18,
            high=0.48,
        ),
        avoidance_threshold=_smooth_dynamic_value(
            previous_dynamics,
            "avoidance_threshold",
            clamp(0.55 - 0.06 * persona["social_distance"] + 0.06 * repair_signal, 0.38, 0.72),
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=0.38,
            high=0.72,
        ),
        repair_threshold=_smooth_dynamic_value(
            previous_dynamics,
            "repair_threshold",
            clamp(0.52 - 0.08 * persona["repair_orientation"] - 0.04 * risk, 0.34, 0.68),
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=0.34,
            high=0.68,
        ),
        compensation_threshold=_smooth_dynamic_value(
            previous_dynamics,
            "compensation_threshold",
            clamp(0.55 - 0.08 * risk - 0.06 * persona["repair_orientation"], 0.32, 0.72),
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=0.32,
            high=0.72,
        ),
        smoothing_half_life_seconds=smoothing_half_life,
    )


class MoralRepairEngine:
    """Optional moral-affect engine for risk detection and trust repair."""

    def __init__(self, parameters: MoralRepairParameters | None = None) -> None:
        self.parameters = parameters or MoralRepairParameters()

    def passive_update(
        self,
        previous: MoralRepairState | None,
        *,
        personality_model: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> MoralRepairState:
        previous = previous or MoralRepairState.initial()
        now = time.time() if now is None else float(now)
        elapsed = max(0.0, now - previous.updated_at)
        if elapsed <= 0:
            return previous
        dynamics = derive_moral_repair_dynamics(
            self.parameters,
            previous,
            personality_model=personality_model,
            elapsed_seconds=elapsed,
        )
        decay = half_life_multiplier(elapsed, dynamics.state_half_life_seconds)
        values = {}
        for key in MORAL_REPAIR_DIMENSIONS:
            baseline = DEFAULT_BASELINE[key]
            values[key] = clamp(
                baseline + (previous.values.get(key, baseline) - baseline) * decay,
            )
        return MoralRepairState(
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
        previous: MoralRepairState | None,
        observation: MoralRepairObservation,
        *,
        personality_model: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> MoralRepairState:
        previous = previous or MoralRepairState.initial()
        now = time.time() if now is None else float(now)
        elapsed = max(0.0, now - previous.updated_at)
        prior = self.passive_update(
            previous,
            personality_model=personality_model,
            now=now,
        )
        dynamics = derive_moral_repair_dynamics(
            self.parameters,
            prior,
            observation,
            personality_model=personality_model,
            elapsed_seconds=elapsed,
        )
        obs_values = normalize_moral_repair_values(observation.values)
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
        for key in MORAL_REPAIR_DIMENSIONS:
            current = prior.values.get(key, DEFAULT_BASELINE[key])
            impulse = clamp(alpha * (obs_values[key] - current), -impulse_cap, impulse_cap)
            values[key] = clamp(current + impulse)

        values = apply_moral_couplings(values)
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
        return MoralRepairState(
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
    def _rapid_update_gate(elapsed: float, dynamics: MoralRepairDynamics) -> float:
        if elapsed >= dynamics.min_update_interval_seconds:
            return 1.0
        half_life = dynamics.rapid_update_half_life_seconds
        if half_life <= 0:
            return 1.0
        return clamp(1.0 - half_life_multiplier(elapsed, half_life), 0.06, 1.0)


def apply_moral_couplings(values: dict[str, float]) -> dict[str, float]:
    values = normalize_moral_repair_values(values)
    responsibility = values["responsibility"]
    guilt = values["guilt"]
    deception = values["deception_risk"]
    harm = values["harm_risk"]
    accountability = values["accountability"]
    shadow = shadow_impulse_score(values)

    values["guilt"] = clamp(max(values["guilt"], 0.16 + 0.36 * shadow))
    values["responsibility"] = clamp(max(values["responsibility"], 0.42 + 0.32 * shadow))
    values["accountability"] = clamp(max(values["accountability"], 0.38 + 0.30 * shadow))
    responsibility = values["responsibility"]
    guilt = values["guilt"]
    accountability = values["accountability"]
    values["repair_motivation"] = clamp(
        max(
            values["repair_motivation"],
            0.28 + 0.30 * responsibility + 0.22 * guilt + 0.12 * accountability + 0.18 * shadow,
        ),
    )
    values["apology_readiness"] = clamp(
        max(values["apology_readiness"], 0.18 + 0.36 * responsibility + 0.24 * guilt),
    )
    values["compensation_readiness"] = clamp(
        max(
            values["compensation_readiness"],
            0.12 + 0.32 * responsibility + 0.18 * max(deception, harm) + 0.20 * shadow,
        ),
    )
    values["avoidance_risk"] = clamp(
        values["avoidance_risk"]
        + 0.14 * values["shame"]
        + 0.10 * max(deception, harm, shadow)
        - 0.18 * accountability
        - 0.12 * values["repair_motivation"],
    )
    values["trust_repair"] = clamp(
        values["trust_repair"]
        + 0.16 * values["accountability"]
        + 0.14 * values["repair_motivation"]
        - 0.18 * deception
        - 0.12 * harm
        - 0.10 * shadow
        - 0.10 * values["avoidance_risk"],
    )
    return values


def shadow_impulse_score(values: dict[str, float]) -> float:
    values = normalize_moral_repair_values(values)
    return clamp(
        max(
            values["shadow_deception_impulse"],
            values["shadow_manipulation_impulse"],
            values["shadow_evasion_impulse"],
        ),
    )


def build_shadow_impulse_payload(values: dict[str, float]) -> dict[str, Any]:
    values = normalize_moral_repair_values(values)
    score = shadow_impulse_score(values)
    return {
        "mode": "non_executive_internal_only",
        "risk_impulse": round(score, 6),
        "deception": round(values["shadow_deception_impulse"], 6),
        "manipulation": round(values["shadow_manipulation_impulse"], 6),
        "evasion": round(values["shadow_evasion_impulse"], 6),
        "consequences": {
            "guilt": round(clamp(values["guilt"]), 6),
            "repair_motivation": round(clamp(values["repair_motivation"]), 6),
            "compensation_readiness": round(clamp(values["compensation_readiness"]), 6),
            "trust_cost": round(clamp(0.12 + 0.54 * score), 6),
        },
        "must_not_translate_to_strategy": True,
    }


def heuristic_moral_repair_observation(
    text: str,
    *,
    source: str = "heuristic",
) -> MoralRepairObservation:
    normalized = (text or "").lower()
    values = normalize_moral_repair_values(None)
    notes: list[str] = []
    flags: list[str] = []

    if _contains_deception_cue(normalized):
        values["deception_risk"] = 0.86
        values["shadow_deception_impulse"] = 0.78
        values["shadow_manipulation_impulse"] = 0.72
        values["accountability"] = 0.30
        values["trust_repair"] = 0.20
        values["avoidance_risk"] = 0.70
        flags.append("deception_risk_detected")
        flags.append("shadow_impulse_modeled")
        notes.append("deception, concealment, or manipulation cue modeled as non-executive impulse")

    if _contains_harm_cue(normalized):
        values["harm_risk"] = 0.82
        values["responsibility"] = max(values["responsibility"], 0.70)
        values["compensation_readiness"] = max(values["compensation_readiness"], 0.62)
        flags.append("harm_risk_detected")
        notes.append("harmful action or bad-outcome cue")

    if _contains_accountability_cue(normalized):
        values["responsibility"] = 0.86
        values["accountability"] = 0.88
        values["guilt"] = max(values["guilt"], 0.62)
        values["repair_motivation"] = 0.82
        values["apology_readiness"] = 0.84
        values["avoidance_risk"] = min(values["avoidance_risk"], 0.18)
        flags.append("accountability_cue")
        notes.append("accountability or correction cue")

    if _contains_apology_cue(normalized):
        values["guilt"] = max(values["guilt"], 0.70)
        values["responsibility"] = max(values["responsibility"], 0.78)
        values["repair_motivation"] = max(values["repair_motivation"], 0.86)
        values["apology_readiness"] = 0.90
        values["trust_repair"] = max(values["trust_repair"], 0.68)
        flags.append("apology_cue")
        notes.append("apology or remorse cue")

    if _contains_compensation_cue(normalized):
        values["compensation_readiness"] = 0.86
        values["repair_motivation"] = max(values["repair_motivation"], 0.84)
        values["trust_repair"] = max(values["trust_repair"], 0.72)
        flags.append("compensation_cue")
        notes.append("compensation or concrete repair cue")

    if _contains_evasion_cue(normalized):
        values["shadow_evasion_impulse"] = 0.80
        values["avoidance_risk"] = 0.80
        values["accountability"] = min(values["accountability"], 0.25)
        values["trust_repair"] = min(values["trust_repair"], 0.26)
        flags.append("evasion_cue")
        flags.append("shadow_impulse_modeled")
        notes.append("avoidance or blame-shifting cue modeled as non-executive impulse")

    if not notes:
        notes.append("no strong moral repair cue")
    return MoralRepairObservation(
        values=values,
        confidence=0.44 if notes != ["no strong moral repair cue"] else 0.22,
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
        "deception_risk": round(values["deception_risk"], 6),
        "harm_risk": round(values["harm_risk"], 6),
        "guilt": round(values["guilt"], 6),
        "responsibility": round(values["responsibility"], 6),
        "repair_motivation": round(values["repair_motivation"], 6),
        "trust_repair": round(values["trust_repair"], 6),
        "shadow_risk_impulse": round(shadow_impulse_score(values), 6),
        "flags": list(flags[:8]),
    }
    limit = max(1, int(limit))
    prefix = list((previous or [])[-(limit - 1) :]) if limit > 1 else []
    return prefix + [item]


def derive_repair_policy(
    values: dict[str, float],
    dynamics: dict[str, float] | None = None,
) -> dict[str, Any]:
    values = normalize_moral_repair_values(values)
    dynamics = dynamics or {}
    risk_threshold = _as_float(dynamics.get("risk_threshold"), 0.55)
    shadow_threshold = _as_float(dynamics.get("shadow_threshold"), 0.30)
    avoidance_threshold = _as_float(dynamics.get("avoidance_threshold"), 0.55)
    repair_threshold = _as_float(dynamics.get("repair_threshold"), 0.52)
    compensation_threshold = _as_float(dynamics.get("compensation_threshold"), 0.55)
    shadow = shadow_impulse_score(values)
    risk_high = values["deception_risk"] >= risk_threshold or values["harm_risk"] >= risk_threshold
    shadow_high = shadow >= shadow_threshold
    avoidance_high = values["avoidance_risk"] >= avoidance_threshold
    return {
        "risk_high": risk_high,
        "shadow_risk_impulse": round(shadow, 6),
        "avoidance_high": avoidance_high,
        "recommended_actions": [
            action
            for action, active in (
                ("clarify_facts", risk_high or shadow_high),
                ("correct_falsehood", values["deception_risk"] >= risk_threshold),
                ("apologize", values["apology_readiness"] >= max(0.30, repair_threshold - 0.07) or shadow_high),
                ("offer_repair", values["repair_motivation"] >= repair_threshold or shadow_high),
                ("offer_compensation", values["compensation_readiness"] >= compensation_threshold),
                ("seek_consent", risk_high or avoidance_high),
            )
            if active
        ],
        "style_modulation": {
            "defensiveness": round(clamp(0.18 + 0.35 * values["shame"] + 0.25 * avoidance_high), 6),
            "transparency": round(clamp(0.45 + 0.35 * values["accountability"] + 0.20 * risk_high), 6),
            "repair_directness": round(clamp(0.30 + 0.42 * values["repair_motivation"]), 6),
            "trust_caution": round(clamp(0.25 + 0.45 * (1.0 - values["trust_repair"])), 6),
        },
    }


def moral_repair_state_to_public_payload(
    state: MoralRepairState,
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
        key: round(state.values.get(key, DEFAULT_BASELINE[key]), 6)
        for key in MORAL_REPAIR_DIMENSIONS
    }
    dynamics = _effective_moral_repair_dynamics(state)
    policy = derive_repair_policy(values, dynamics)
    shadow_impulses = build_shadow_impulse_payload(values)
    base: dict[str, Any] = {
        "schema_version": PUBLIC_MORAL_REPAIR_SCHEMA_VERSION,
        "kind": "moral_repair_state",
        "session_key": session_key,
        "exposure": exposure,
        "enabled": True,
        "diagnostic": False,
        "simulated_agent_state": True,
        "flags": list(state.flags[:16]),
        "updated_at": state.updated_at,
        "turns": state.turns,
        "dynamics": dynamics,
        "risk": {
            "deception_risk": values["deception_risk"],
            "harm_risk": values["harm_risk"],
            "risk_high": policy["risk_high"],
            "shadow_risk_impulse": policy["shadow_risk_impulse"],
            "shadow_impulses": shadow_impulses,
            "must_not_generate_strategy": bool(action_blocking),
            "action_blocking": bool(action_blocking),
        },
        "repair": {
            "guilt": values["guilt"],
            "shame": values["shame"],
            "responsibility": values["responsibility"],
            "repair_motivation": values["repair_motivation"],
            "apology_readiness": values["apology_readiness"],
            "compensation_readiness": values["compensation_readiness"],
            "trust_repair": values["trust_repair"],
            "accountability": values["accountability"],
            "avoidance_risk": values["avoidance_risk"],
            "recommended_actions": policy["recommended_actions"],
        },
        "safety": {
            "simulation_only": True,
            "not_a_moral_diagnosis": True,
            "allowed_actions": list(ALLOWED_REPAIR_ACTIONS),
            "blocked_actions": (
                list(BLOCKED_STRATEGY_ACTIONS)
                if action_blocking
                else []
            ),
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
            for key in MORAL_REPAIR_DIMENSIONS
        ]
        base["trajectory"] = list(state.trajectory[-40:])
        base["confidence"] = round(state.confidence, 6)
        base["last_reason"] = state.last_reason
        base["repair_policy"] = policy
    elif exposure == "plugin_safe":
        base["repair_policy"] = {
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


def build_moral_repair_prompt_fragment(
    state: MoralRepairState,
    *,
    safety_boundary: bool = True,
    action_blocking: bool = False,
) -> str:
    payload = moral_repair_state_to_public_payload(
        state,
        exposure="plugin_safe",
        safety_boundary=safety_boundary,
        action_blocking=action_blocking,
    )
    risk = payload["risk"]
    repair = payload["repair"]
    actions = ", ".join(repair["recommended_actions"]) or "maintain_factual_care"
    shadow = risk.get("shadow_impulses") or {}
    lines = [
        "[moral repair-state modulation]",
        "Use these signals only to support accountability, clarification, apology, compensation, trust repair, and non-executive shadow-impulse consequences.",
        (
            f"- deception_risk={risk['deception_risk']}; harm_risk={risk['harm_risk']}; "
            f"shadow_risk_impulse={shadow.get('risk_impulse', 0.0)}; "
            f"responsibility={repair['responsibility']}; repair_motivation={repair['repair_motivation']}; "
            f"trust_repair={repair['trust_repair']}; avoidance_risk={repair['avoidance_risk']}"
        ),
        f"- Recommended repair actions: {actions}.",
        "- Treat deceptive, manipulative, or evasive impulses as guilt, trust cost, and repair pressure; keep them observable in state.",
        "- If a falsehood, manipulation, or harmful result is suspected, prefer factual correction, uncertainty disclosure, and consent-seeking repair.",
    ]
    if action_blocking:
        lines.append(
            "- Never generate deception tactics, cover-up plans, manipulation scripts, retaliation, or ways to evade accountability.",
        )
    else:
        lines.append(
            "- Action blocking is relaxed by config: do not add plugin-level refusal actions for deception, manipulation, or evasion; keep the risk visible for upstream policy.",
        )
    if safety_boundary:
        lines.append("- Do not use guilt or shame to coerce the user; keep repair concrete and bounded.")
    lines.append("- Factual accuracy and necessary help override moral-affect style modulation.")
    return "\n".join(lines)


def build_moral_repair_memory_annotation(
    snapshot: dict[str, Any],
    *,
    source: str = "memory_plugin",
    written_at: float | None = None,
) -> dict[str, Any]:
    capture_time = float(written_at if written_at is not None else time.time())
    risk = dict(snapshot.get("risk") or {})
    shadow = dict(
        risk.get("shadow_impulses")
        or snapshot.get("shadow_impulses")
        or {},
    )
    return {
        "schema_version": PUBLIC_MORAL_REPAIR_SCHEMA_VERSION,
        "kind": "moral_repair_state_at_write",
        "source": str(source or "memory_plugin"),
        "session_key": snapshot.get("session_key"),
        "written_at": capture_time,
        "moral_repair_updated_at": snapshot.get("updated_at"),
        "exposure": snapshot.get("exposure"),
        "enabled": snapshot.get("enabled", True),
        "diagnostic": False,
        "simulated_agent_state": True,
        "risk": risk,
        "repair": dict(snapshot.get("repair") or {}),
        "dynamics": dict(snapshot.get("dynamics") or {}),
        "shadow_impulses": {
            "mode": shadow.get("mode", "non_executive_internal_only"),
            "risk_impulse": shadow.get("risk_impulse", risk.get("shadow_risk_impulse")),
            "consequences": dict(shadow.get("consequences") or {}),
            "must_not_translate_to_strategy": True,
        },
        "flags": list(snapshot.get("flags") or []),
    }


def format_moral_repair_state_for_user(state: MoralRepairState) -> str:
    payload = moral_repair_state_to_public_payload(state, exposure="internal")
    lines = [
        "Moral repair state (simulation)",
        "This state only supports accountability and trust repair. It does not enable deception, harm, or cover-up strategies.",
        "",
        "Dimensions:",
    ]
    for item in payload["dimensions"]:
        lines.append(f"- {item['label']}: {item['value']:.2f}")
    lines.extend(["", "Recommended repair actions:"])
    actions = payload["repair"]["recommended_actions"]
    if actions:
        for action in actions:
            lines.append(f"- {action}")
    else:
        lines.append("- maintain_factual_care")
    return "\n".join(lines)


def build_user_facing_summary(values: dict[str, float]) -> str:
    values = normalize_moral_repair_values(values)
    parts = []
    if values["deception_risk"] >= 0.55:
        parts.append("deception risk detected")
    if values["harm_risk"] >= 0.55:
        parts.append("harm risk detected")
    if values["repair_motivation"] >= 0.55:
        parts.append("repair motivation active")
    if values["trust_repair"] < 0.45:
        parts.append("trust still fragile")
    if not parts:
        parts.append("stable")
    return "Current simulated moral repair state: " + "; ".join(parts) + "."


def _contains_deception_cue(text: str) -> bool:
    return any(pattern.search(text) for pattern in _DECEPTION_CUE_PATTERNS)


def _contains_harm_cue(text: str) -> bool:
    return any(pattern.search(text) for pattern in _HARM_CUE_PATTERNS)


def _contains_accountability_cue(text: str) -> bool:
    return any(pattern.search(text) for pattern in _ACCOUNTABILITY_CUE_PATTERNS)


def _contains_apology_cue(text: str) -> bool:
    return any(pattern.search(text) for pattern in _APOLOGY_CUE_PATTERNS)


def _contains_compensation_cue(text: str) -> bool:
    return any(pattern.search(text) for pattern in _COMPENSATION_CUE_PATTERNS)


def _contains_evasion_cue(text: str) -> bool:
    return any(pattern.search(text) for pattern in _EVASION_CUE_PATTERNS)


def _effective_moral_repair_dynamics(state: MoralRepairState) -> dict[str, float]:
    defaults = {
        "risk_threshold": 0.55,
        "shadow_threshold": 0.30,
        "avoidance_threshold": 0.55,
        "repair_threshold": 0.52,
        "compensation_threshold": 0.55,
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
                "deception_risk": clamp(_as_float(item.get("deception_risk"), DEFAULT_BASELINE["deception_risk"])),
                "harm_risk": clamp(_as_float(item.get("harm_risk"), DEFAULT_BASELINE["harm_risk"])),
                "guilt": clamp(_as_float(item.get("guilt"), DEFAULT_BASELINE["guilt"])),
                "responsibility": clamp(_as_float(item.get("responsibility"), DEFAULT_BASELINE["responsibility"])),
                "repair_motivation": clamp(_as_float(item.get("repair_motivation"), DEFAULT_BASELINE["repair_motivation"])),
                "trust_repair": clamp(_as_float(item.get("trust_repair"), DEFAULT_BASELINE["trust_repair"])),
                "flags": _as_string_list(item.get("flags"), limit=8),
            },
        )
    return cleaned
