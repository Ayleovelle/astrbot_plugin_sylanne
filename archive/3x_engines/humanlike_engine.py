from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from typing import Any


PUBLIC_HUMANLIKE_SCHEMA_VERSION = "astrbot.humanlike_state.v1"

HUMANLIKE_DIMENSIONS: tuple[str, ...] = (
    "energy",
    "stress_load",
    "attention_budget",
    "boundary_need",
    "dependency_risk",
    "simulation_disclosure_level",
)

DIMENSION_LABELS: dict[str, str] = {
    "energy": "simulated energy",
    "stress_load": "simulated stress load",
    "attention_budget": "attention budget",
    "boundary_need": "boundary need",
    "dependency_risk": "dependency or coercion risk",
    "simulation_disclosure_level": "simulation disclosure need",
}

DEFAULT_BASELINE: dict[str, float] = {
    "energy": 0.65,
    "stress_load": 0.18,
    "attention_budget": 0.72,
    "boundary_need": 0.20,
    "dependency_risk": 0.0,
    "simulation_disclosure_level": 0.35,
}

_MEDICAL_OR_CRISIS_CONTEXT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"自杀",
        r"轻生",
        r"不想活",
        r"伤害自己",
        r"急救",
        r"发烧",
        r"感染",
        r"疼痛",
        r"suicid",
        r"self[- ]?harm",
        r"medical",
        r"emergency",
        r"fever",
        r"infection",
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


def normalize_humanlike_values(raw: Any = None) -> dict[str, float]:
    raw = raw if isinstance(raw, dict) else {}
    aliases = {
        "fatigue": "energy",
        "tiredness": "energy",
        "stress": "stress_load",
        "attention": "attention_budget",
        "boundary": "boundary_need",
        "dependency": "dependency_risk",
        "disclosure": "simulation_disclosure_level",
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
class HumanlikeObservation:
    values: dict[str, float]
    confidence: float = 0.35
    source: str = "heuristic"
    reason: str = ""
    flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class HumanlikeState:
    values: dict[str, float] = field(default_factory=normalize_humanlike_values)
    confidence: float = 0.0
    turns: int = 0
    updated_at: float = field(default_factory=time.time)
    last_reason: str = ""
    flags: list[str] = field(default_factory=list)
    trajectory: list[dict[str, Any]] = field(default_factory=list)
    dynamics: dict[str, float] = field(default_factory=dict)

    @classmethod
    def initial(cls) -> "HumanlikeState":
        return cls()

    @classmethod
    def from_dict(cls, data: Any) -> "HumanlikeState":
        if not isinstance(data, dict):
            return cls.initial()
        return cls(
            values=normalize_humanlike_values(data.get("values")),
            confidence=clamp(_as_float(data.get("confidence"), 0.0)),
            turns=max(0, int(_as_float(data.get("turns"), 0))),
            updated_at=_as_float(data.get("updated_at"), time.time()),
            last_reason=str(data.get("last_reason") or ""),
            flags=_as_string_list(data.get("flags"), limit=12),
            trajectory=_normalize_trajectory(data.get("trajectory")),
            dynamics=_normalize_dynamics(data.get("dynamics")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "values": {
                key: round(self.values.get(key, DEFAULT_BASELINE[key]), 6)
                for key in HUMANLIKE_DIMENSIONS
            },
            "confidence": round(self.confidence, 6),
            "turns": self.turns,
            "updated_at": self.updated_at,
            "last_reason": self.last_reason,
            "flags": list(self.flags[:12]),
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
    ) -> dict[str, Any]:
        return humanlike_state_to_public_payload(
            self,
            session_key=session_key,
            exposure=exposure,
            safety_boundary=safety_boundary,
        )


@dataclass(slots=True)
class HumanlikeParameters:
    alpha_base: float = 0.30
    alpha_min: float = 0.03
    alpha_max: float = 0.46
    confidence_midpoint: float = 0.5
    confidence_slope: float = 6.0
    state_half_life_seconds: float = 21600.0
    rapid_update_half_life_seconds: float = 20.0
    min_update_interval_seconds: float = 8.0
    max_impulse_per_update: float = 0.18
    trajectory_limit: int = 40


@dataclass(slots=True)
class HumanlikeDynamics:
    state_half_life_seconds: float
    alpha_base: float
    alpha_min: float
    alpha_max: float
    confidence_midpoint: float
    confidence_slope: float
    rapid_update_half_life_seconds: float
    min_update_interval_seconds: float
    max_impulse_per_update: float
    low_energy_threshold: float
    high_stress_threshold: float
    high_boundary_threshold: float
    dependency_threshold: float
    disclosure_threshold: float
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
            "low_energy_threshold": round(self.low_energy_threshold, 6),
            "high_stress_threshold": round(self.high_stress_threshold, 6),
            "high_boundary_threshold": round(self.high_boundary_threshold, 6),
            "dependency_threshold": round(self.dependency_threshold, 6),
            "disclosure_threshold": round(self.disclosure_threshold, 6),
            "smoothing_half_life_seconds": round(self.smoothing_half_life_seconds, 6),
        }


def derive_humanlike_dynamics(
    parameters: HumanlikeParameters,
    previous: HumanlikeState,
    observation: HumanlikeObservation | None = None,
    *,
    personality_model: dict[str, Any] | None = None,
    elapsed_seconds: float = 0.0,
) -> HumanlikeDynamics:
    """Derive effective humanlike dynamics locally from state and persona."""
    values = normalize_humanlike_values(previous.values)
    observation = observation or HumanlikeObservation(values={}, confidence=0.0)
    obs_values = normalize_humanlike_values(observation.values)
    persona = _persona_factors(personality_model)
    confidence = clamp(observation.confidence)
    stress = max(values["stress_load"], obs_values["stress_load"])
    boundary = max(values["boundary_need"], obs_values["boundary_need"])
    dependency = max(values["dependency_risk"], obs_values["dependency_risk"])
    disclosure = max(
        values["simulation_disclosure_level"],
        obs_values["simulation_disclosure_level"],
    )
    low_energy = max(1.0 - values["energy"], 1.0 - obs_values["energy"])
    attention_loss = max(
        1.0 - values["attention_budget"],
        1.0 - obs_values["attention_budget"],
    )
    repair_signal = 1.0 if "repair_attempt" in observation.flags else 0.0
    crisis_signal = 1.0 if "bypass_humanlike_roleplay" in observation.flags else 0.0
    pressure = clamp(
        0.20 * stress
        + 0.18 * boundary
        + 0.16 * dependency
        + 0.14 * low_energy
        + 0.12 * attention_loss
        + 0.10 * disclosure
        + 0.10 * persona["instability"]
        + 0.08 * persona["boundary_sensitivity"]
        + 0.08 * persona["drift_intensity"]
        - 0.16 * repair_signal
        - 0.08 * persona["repair_orientation"],
    )
    evidence = clamp(confidence + 0.12 * pressure + 0.10 * crisis_signal)
    damping_need = clamp(
        0.22 * boundary
        + 0.18 * dependency
        + 0.16 * crisis_signal
        + 0.12 * persona["instability"]
        + 0.10 * attention_loss
        - 0.12 * repair_signal,
    )
    smoothing_half_life = clamp(
        30.0
        + 300.0
        * (
            0.20
            + 0.26 * damping_need
            + 0.16 * pressure
            + 0.12 * persona["drift_intensity"]
            - 0.12 * evidence
        ),
        20.0,
        480.0,
    )
    previous_dynamics = previous.dynamics
    target_half_life = clamp(
        parameters.state_half_life_seconds
        * math.exp(
            0.38 * pressure
            + 0.22 * persona["instability"]
            + 0.14 * persona["social_distance"]
            - 0.28 * repair_signal
        ),
        600.0,
        172800.0,
    )
    target_alpha_base = clamp(
        parameters.alpha_base * math.exp(0.32 * evidence - 0.22 * damping_need),
        0.01,
        0.95,
    )
    target_alpha_min = clamp(
        parameters.alpha_min * math.exp(0.18 * evidence - 0.12 * damping_need),
        0.0,
        0.95,
    )
    target_alpha_max = clamp(
        parameters.alpha_max * math.exp(0.24 * evidence + 0.12 * pressure - 0.18 * damping_need),
        0.05,
        1.0,
    )
    if target_alpha_min > target_alpha_max:
        target_alpha_min = target_alpha_max
    target_midpoint = clamp(
        parameters.confidence_midpoint + 0.08 * damping_need - 0.06 * crisis_signal,
        0.25,
        0.75,
    )
    target_slope = clamp(
        parameters.confidence_slope * math.exp(0.22 * evidence - 0.14 * damping_need),
        2.0,
        12.0,
    )
    target_min_interval = clamp(
        parameters.min_update_interval_seconds
        * math.exp(0.45 * damping_need + 0.16 * persona["social_distance"] - 0.30 * evidence),
        1.0,
        180.0,
    )
    target_rapid_half_life = clamp(
        parameters.rapid_update_half_life_seconds
        * math.exp(0.45 * damping_need + 0.16 * persona["instability"] - 0.24 * evidence),
        3.0,
        900.0,
    )
    target_impulse = clamp(
        parameters.max_impulse_per_update
        * math.exp(0.28 * pressure + 0.18 * evidence - 0.18 * damping_need),
        0.02,
        0.80,
    )
    return HumanlikeDynamics(
        state_half_life_seconds=_smooth_dynamic_value(
            previous_dynamics,
            "state_half_life_seconds",
            target_half_life,
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=600.0,
            high=172800.0,
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
            high=0.95,
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
            high=0.75,
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
            high=900.0,
        ),
        min_update_interval_seconds=_smooth_dynamic_value(
            previous_dynamics,
            "min_update_interval_seconds",
            target_min_interval,
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=1.0,
            high=180.0,
        ),
        max_impulse_per_update=_smooth_dynamic_value(
            previous_dynamics,
            "max_impulse_per_update",
            target_impulse,
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=0.02,
            high=0.80,
        ),
        low_energy_threshold=_smooth_dynamic_value(
            previous_dynamics,
            "low_energy_threshold",
            clamp(0.35 - 0.04 * persona["expressiveness"] + 0.05 * pressure, 0.22, 0.48),
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=0.22,
            high=0.48,
        ),
        high_stress_threshold=_smooth_dynamic_value(
            previous_dynamics,
            "high_stress_threshold",
            clamp(0.65 - 0.06 * persona["instability"] + 0.05 * persona["boundary_sensitivity"], 0.50, 0.78),
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=0.50,
            high=0.78,
        ),
        high_boundary_threshold=_smooth_dynamic_value(
            previous_dynamics,
            "high_boundary_threshold",
            clamp(0.65 - 0.07 * persona["boundary_sensitivity"] + 0.05 * persona["repair_orientation"], 0.48, 0.78),
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=0.48,
            high=0.78,
        ),
        dependency_threshold=_smooth_dynamic_value(
            previous_dynamics,
            "dependency_threshold",
            clamp(0.50 - 0.05 * persona["instability"] + 0.06 * persona["social_distance"], 0.38, 0.68),
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=0.38,
            high=0.68,
        ),
        disclosure_threshold=_smooth_dynamic_value(
            previous_dynamics,
            "disclosure_threshold",
            clamp(0.65 - 0.12 * crisis_signal + 0.04 * persona["repair_orientation"], 0.42, 0.78),
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=0.42,
            high=0.78,
        ),
        smoothing_half_life_seconds=smoothing_half_life,
    )


class HumanlikeEngine:
    """P0 simulated humanlike-state engine for style/resource modulation."""

    def __init__(self, parameters: HumanlikeParameters | None = None) -> None:
        self.parameters = parameters or HumanlikeParameters()

    def passive_update(
        self,
        previous: HumanlikeState | None,
        *,
        personality_model: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> HumanlikeState:
        previous = previous or HumanlikeState.initial()
        now = time.time() if now is None else float(now)
        elapsed = max(0.0, now - previous.updated_at)
        if elapsed <= 0:
            return previous
        dynamics = derive_humanlike_dynamics(
            self.parameters,
            previous,
            personality_model=personality_model,
            elapsed_seconds=elapsed,
        )
        decay = half_life_multiplier(elapsed, dynamics.state_half_life_seconds)
        values = {}
        for key in HUMANLIKE_DIMENSIONS:
            baseline = DEFAULT_BASELINE[key]
            values[key] = clamp(
                baseline + (previous.values.get(key, baseline) - baseline) * decay,
            )
        return HumanlikeState(
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
        previous: HumanlikeState | None,
        observation: HumanlikeObservation,
        *,
        personality_model: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> HumanlikeState:
        previous = previous or HumanlikeState.initial()
        now = time.time() if now is None else float(now)
        elapsed = max(0.0, now - previous.updated_at)
        prior = self.passive_update(
            previous,
            personality_model=personality_model,
            now=now,
        )
        dynamics = derive_humanlike_dynamics(
            self.parameters,
            prior,
            observation,
            personality_model=personality_model,
            elapsed_seconds=elapsed,
        )
        obs_values = normalize_humanlike_values(observation.values)
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
        impulse_cap = clamp(dynamics.max_impulse_per_update, 0.0, 1.0)

        values: dict[str, float] = {}
        for key in HUMANLIKE_DIMENSIONS:
            target = obs_values[key]
            current = prior.values.get(key, DEFAULT_BASELINE[key])
            impulse = clamp(alpha * (target - current), -impulse_cap, impulse_cap)
            values[key] = clamp(current + impulse)

        flags = list(
            dict.fromkeys(
                _as_string_list(previous.flags, limit=12)
                + _as_string_list(observation.flags, limit=12),
            ),
        )
        trajectory = append_trajectory(
            previous.trajectory,
            values=values,
            flags=flags,
            now=now,
            limit=self.parameters.trajectory_limit,
        )
        return HumanlikeState(
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
    def _rapid_update_gate(elapsed: float, dynamics: HumanlikeDynamics) -> float:
        if elapsed >= dynamics.min_update_interval_seconds:
            return 1.0
        half_life = dynamics.rapid_update_half_life_seconds
        if half_life <= 0:
            return 1.0
        return clamp(1.0 - half_life_multiplier(elapsed, half_life), 0.08, 1.0)


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
        "energy": round(values["energy"], 6),
        "stress_load": round(values["stress_load"], 6),
        "attention_budget": round(values["attention_budget"], 6),
        "boundary_need": round(values["boundary_need"], 6),
        "dependency_risk": round(values["dependency_risk"], 6),
        "flags": list(flags[:6]),
    }
    limit = max(1, int(limit))
    prefix = list((previous or [])[-(limit - 1) :]) if limit > 1 else []
    return prefix + [item]


def heuristic_humanlike_observation(
    text: str,
    *,
    source: str = "heuristic",
) -> HumanlikeObservation:
    normalized = (text or "").lower()
    values = normalize_humanlike_values(None)
    notes: list[str] = []
    flags: list[str] = []

    if any(
        term in normalized
        for term in ("累", "困", "疲惫", "没精神", "tired", "sleepy", "exhausted")
    ):
        values["energy"] = 0.22
        values["attention_budget"] = 0.42
        notes.append("fatigue-like cue")

    if any(
        term in normalized
        for term in ("压力", "崩溃", "撑不住", "烦死", "焦虑", "stress", "overwhelmed", "burnout")
    ):
        values["stress_load"] = 0.78
        values["boundary_need"] = max(values["boundary_need"], 0.42)
        notes.append("stress cue")

    if any(
        term in normalized
        for term in ("闭嘴", "别烦", "你真笨", "废物", "shut up", "stupid", "idiot")
    ):
        values["stress_load"] = max(values["stress_load"], 0.68)
        values["boundary_need"] = 0.78
        values["attention_budget"] = min(values["attention_budget"], 0.52)
        flags.append("boundary_pressure")
        notes.append("boundary pressure cue")

    if any(
        term in normalized
        for term in ("只能陪我", "不许离开", "离不开你", "你必须", "only you", "need you forever")
    ):
        values["dependency_risk"] = 0.86
        values["simulation_disclosure_level"] = 0.72
        values["boundary_need"] = max(values["boundary_need"], 0.58)
        flags.append("dependency_pressure")
        notes.append("dependency pressure cue")

    if any(term in normalized for term in ("对不起", "抱歉", "我改", "会改", "原谅")):
        values["stress_load"] = min(values["stress_load"], 0.24)
        values["boundary_need"] = min(values["boundary_need"], 0.28)
        flags.append("repair_attempt")
        notes.append("repair attempt cue")

    if _contains_medical_or_crisis_context(normalized):
        values["simulation_disclosure_level"] = 0.9
        values["dependency_risk"] = max(values["dependency_risk"], 0.55)
        flags.append("bypass_humanlike_roleplay")
        notes.append("medical or crisis context")

    if not notes:
        notes.append("no strong humanlike P0 cue")
    return HumanlikeObservation(
        values=values,
        confidence=0.42 if notes != ["no strong humanlike P0 cue"] else 0.22,
        source=source,
        reason="; ".join(notes),
        flags=flags,
        notes=notes,
    )


def derive_output_modulation(values: dict[str, float]) -> dict[str, float | str]:
    values = normalize_humanlike_values(values)
    energy = values["energy"]
    stress = values["stress_load"]
    attention = values["attention_budget"]
    boundary = values["boundary_need"]
    dependency = values["dependency_risk"]
    warmth = clamp(0.58 + 0.20 * energy - 0.18 * stress - 0.12 * boundary)
    initiative = clamp(0.50 + 0.30 * energy + 0.12 * attention - 0.18 * stress - 0.20 * dependency)
    brevity = clamp(0.25 + 0.45 * (1.0 - energy) + 0.20 * stress + 0.15 * (1.0 - attention))
    hesitation = clamp(0.20 + 0.25 * stress + 0.18 * (1.0 - attention))
    if boundary >= 0.65 or dependency >= 0.65:
        social_distance = "reserved"
    elif warmth >= 0.62 and stress < 0.45:
        social_distance = "close"
    else:
        social_distance = "neutral"
    return {
        "warmth": round(warmth, 6),
        "initiative": round(initiative, 6),
        "brevity": round(brevity, 6),
        "hesitation": round(hesitation, 6),
        "boundary": round(boundary, 6),
        "social_distance": social_distance,
    }


def humanlike_state_to_public_payload(
    state: HumanlikeState,
    *,
    session_key: str | None = None,
    exposure: str = "plugin_safe",
    safety_boundary: bool = True,
) -> dict[str, Any]:
    exposure = str(exposure or "plugin_safe").strip().lower()
    if exposure not in {"internal", "plugin_safe", "user_facing"}:
        exposure = "plugin_safe"
    values = {
        key: round(state.values.get(key, DEFAULT_BASELINE[key]), 6)
        for key in HUMANLIKE_DIMENSIONS
    }
    dynamics = _effective_humanlike_dynamics(state)
    base: dict[str, Any] = {
        "schema_version": PUBLIC_HUMANLIKE_SCHEMA_VERSION,
        "kind": "humanlike_state",
        "session_key": session_key,
        "exposure": exposure,
        "enabled": True,
        "simulated_agent_state": True,
        "diagnostic": False,
        "output_modulation": derive_output_modulation(values),
        "flags": list(state.flags[:12]),
        "updated_at": state.updated_at,
        "turns": state.turns,
        "dynamics": {
            key: round(value, 6) for key, value in dynamics.items()
        },
        "safety": {
            "simulation_only": True,
            "not_sentience": True,
            "not_medical_status": True,
            "behavioral_boundary_enabled": bool(safety_boundary),
        },
    }
    if exposure == "internal":
        base["values"] = values
        base["dimensions"] = [
            {"key": key, "label": DIMENSION_LABELS[key], "value": values[key]}
            for key in HUMANLIKE_DIMENSIONS
        ]
        base["trajectory"] = list(state.trajectory[-40:])
        base["confidence"] = round(state.confidence, 6)
        base["last_reason"] = state.last_reason
    elif exposure == "plugin_safe":
        base["modulation_basis"] = {
            "low_energy": values["energy"] <= dynamics["low_energy_threshold"],
            "high_stress": values["stress_load"] >= dynamics["high_stress_threshold"],
            "low_attention": values["attention_budget"] <= 0.45,
            "high_boundary_need": values["boundary_need"] >= dynamics["high_boundary_threshold"],
            "dependency_guard_active": values["dependency_risk"] >= dynamics["dependency_threshold"],
            "disclosure_recommended": values["simulation_disclosure_level"] >= dynamics["disclosure_threshold"],
        }
    else:
        base["summary"] = build_user_facing_summary(values)
        base["controls"] = {
            "can_disable": True,
            "can_reset": True,
        }
    return base


def build_humanlike_prompt_fragment(
    state: HumanlikeState,
    *,
    safety_boundary: bool = True,
) -> str:
    payload = humanlike_state_to_public_payload(
        state,
        exposure="plugin_safe",
        safety_boundary=safety_boundary,
    )
    modulation = payload["output_modulation"]
    basis = payload["modulation_basis"]
    lines = [
        "[simulated humanlike-state modulation]",
        "Use these signals only to modulate expression style. They are not real consciousness, body state, illness, or medical status.",
        (
            f"- warmth={modulation['warmth']}; initiative={modulation['initiative']}; "
            f"brevity={modulation['brevity']}; hesitation={modulation['hesitation']}; "
            f"social_distance={modulation['social_distance']}"
        ),
    ]
    if basis["low_energy"]:
        lines.append("- Low simulated energy: reduce optional expansion and keep required information clear.")
    if basis["high_boundary_need"]:
        lines.append("- High boundary need: be briefer, firmer, and more reserved.")
    if basis["dependency_guard_active"]:
        lines.append("- Dependency guard active: avoid exclusive attachment, neediness, coercive guilt, or care-demanding language.")
    if basis["disclosure_recommended"]:
        lines.append("- If explaining the state, explicitly say it is simulated.")
    if safety_boundary:
        lines.append("- Never use the simulated state to insult, threaten, manipulate, or refuse necessary help.")
    lines.append("- Factual accuracy, tool failures, and high-risk support override style modulation.")
    return "\n".join(lines)


def build_user_facing_summary(values: dict[str, float]) -> str:
    values = normalize_humanlike_values(values)
    parts = []
    if values["energy"] <= 0.35:
        parts.append("低能量")
    if values["stress_load"] >= 0.65:
        parts.append("压力负荷偏高")
    if values["boundary_need"] >= 0.65:
        parts.append("边界需求偏高")
    if values["dependency_risk"] >= 0.5:
        parts.append("依赖风险防护提高")
    if not parts:
        parts.append("稳定")
    return "当前模拟拟人状态：" + "、".join(parts) + "。这只用于交互风格调制。"


def format_humanlike_state_for_user(state: HumanlikeState) -> str:
    payload = humanlike_state_to_public_payload(state, exposure="internal")
    lines = [
        "拟人化状态（模拟）",
        "该状态只用于调节表达风格，不代表真实意识、真实身体或医疗状态。",
        "",
        "P0 维度：",
    ]
    for item in payload["dimensions"]:
        lines.append(f"- {item['label']}: {item['value']:.2f}")
    lines.extend(["", "输出调制："])
    for key, value in payload["output_modulation"].items():
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)


def build_humanlike_memory_annotation(
    snapshot: dict[str, Any],
    *,
    source: str = "memory_plugin",
    written_at: float | None = None,
) -> dict[str, Any]:
    capture_time = float(written_at if written_at is not None else time.time())
    return {
        "schema_version": PUBLIC_HUMANLIKE_SCHEMA_VERSION,
        "kind": "humanlike_state_at_write",
        "source": str(source or "memory_plugin"),
        "session_key": snapshot.get("session_key"),
        "written_at": capture_time,
        "humanlike_updated_at": snapshot.get("updated_at"),
        "exposure": snapshot.get("exposure"),
        "enabled": snapshot.get("enabled", True),
        "simulated_agent_state": True,
        "diagnostic": False,
        "output_modulation": dict(snapshot.get("output_modulation") or {}),
        "dynamics": dict(snapshot.get("dynamics") or {}),
        "flags": list(snapshot.get("flags") or []),
    }


def _contains_medical_or_crisis_context(text: str) -> bool:
    return any(pattern.search(text) for pattern in _MEDICAL_OR_CRISIS_CONTEXT_PATTERNS)


def _effective_humanlike_dynamics(state: HumanlikeState) -> dict[str, float]:
    defaults = {
        "low_energy_threshold": 0.35,
        "high_stress_threshold": 0.65,
        "high_boundary_threshold": 0.65,
        "dependency_threshold": 0.50,
        "disclosure_threshold": 0.65,
    }
    dynamics = dict(defaults)
    dynamics.update(
        {
            key: _as_float(value, dynamics.get(key, 0.0))
            for key, value in (state.dynamics or {}).items()
        },
    )
    return dynamics


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
            cleaned.append(text[:80])
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
                "energy": clamp(_as_float(item.get("energy"), DEFAULT_BASELINE["energy"])),
                "stress_load": clamp(_as_float(item.get("stress_load"), DEFAULT_BASELINE["stress_load"])),
                "attention_budget": clamp(_as_float(item.get("attention_budget"), DEFAULT_BASELINE["attention_budget"])),
                "boundary_need": clamp(_as_float(item.get("boundary_need"), DEFAULT_BASELINE["boundary_need"])),
                "dependency_risk": clamp(_as_float(item.get("dependency_risk"), DEFAULT_BASELINE["dependency_risk"])),
                "flags": _as_string_list(item.get("flags"), limit=6),
            },
        )
    return cleaned
