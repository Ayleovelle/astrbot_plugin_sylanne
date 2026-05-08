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


class HumanlikeEngine:
    """P0 simulated humanlike-state engine for style/resource modulation."""

    def __init__(self, parameters: HumanlikeParameters | None = None) -> None:
        self.parameters = parameters or HumanlikeParameters()

    def passive_update(
        self,
        previous: HumanlikeState | None,
        *,
        now: float | None = None,
    ) -> HumanlikeState:
        previous = previous or HumanlikeState.initial()
        now = time.time() if now is None else float(now)
        elapsed = max(0.0, now - previous.updated_at)
        if elapsed <= 0:
            return previous
        decay = half_life_multiplier(elapsed, self.parameters.state_half_life_seconds)
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
        )

    def update(
        self,
        previous: HumanlikeState | None,
        observation: HumanlikeObservation,
        *,
        now: float | None = None,
    ) -> HumanlikeState:
        previous = previous or HumanlikeState.initial()
        now = time.time() if now is None else float(now)
        elapsed = max(0.0, now - previous.updated_at)
        prior = self.passive_update(previous, now=now)
        obs_values = normalize_humanlike_values(observation.values)
        confidence = clamp(observation.confidence)
        gate = 1.0 / (
            1.0
            + math.exp(
                -self.parameters.confidence_slope
                * (confidence - self.parameters.confidence_midpoint),
            )
        )
        rapid_gate = self._rapid_update_gate(elapsed)
        raw_alpha = self.parameters.alpha_base * gate * rapid_gate
        min_alpha = self.parameters.alpha_min if elapsed >= self.parameters.min_update_interval_seconds else 0.0
        alpha = clamp(raw_alpha, min_alpha, self.parameters.alpha_max)
        impulse_cap = clamp(self.parameters.max_impulse_per_update, 0.0, 1.0)

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
        )

    def _rapid_update_gate(self, elapsed: float) -> float:
        if elapsed >= self.parameters.min_update_interval_seconds:
            return 1.0
        half_life = self.parameters.rapid_update_half_life_seconds
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
            "low_energy": values["energy"] <= 0.35,
            "high_stress": values["stress_load"] >= 0.65,
            "low_attention": values["attention_budget"] <= 0.45,
            "high_boundary_need": values["boundary_need"] >= 0.65,
            "dependency_guard_active": values["dependency_risk"] >= 0.5,
            "disclosure_recommended": values["simulation_disclosure_level"] >= 0.65,
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
        "flags": list(snapshot.get("flags") or []),
    }


def _contains_medical_or_crisis_context(text: str) -> bool:
    return any(pattern.search(text) for pattern in _MEDICAL_OR_CRISIS_CONTEXT_PATTERNS)


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
