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


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def half_life_multiplier(elapsed_seconds: float, half_life_seconds: float) -> float:
    if elapsed_seconds <= 0:
        return 1.0
    if half_life_seconds <= 0:
        return 0.0
    return clamp(2.0 ** (-elapsed_seconds / half_life_seconds), 0.0, 1.0)


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
        }

    def to_public_dict(
        self,
        *,
        session_key: str | None = None,
        exposure: str = "plugin_safe",
        safety_boundary: bool = True,
    ) -> dict[str, Any]:
        return moral_repair_state_to_public_payload(
            self,
            session_key=session_key,
            exposure=exposure,
            safety_boundary=safety_boundary,
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


class MoralRepairEngine:
    """Optional moral-affect engine for risk detection and trust repair."""

    def __init__(self, parameters: MoralRepairParameters | None = None) -> None:
        self.parameters = parameters or MoralRepairParameters()

    def passive_update(
        self,
        previous: MoralRepairState | None,
        *,
        now: float | None = None,
    ) -> MoralRepairState:
        previous = previous or MoralRepairState.initial()
        now = time.time() if now is None else float(now)
        elapsed = max(0.0, now - previous.updated_at)
        if elapsed <= 0:
            return previous
        decay = half_life_multiplier(elapsed, self.parameters.state_half_life_seconds)
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
        )

    def update(
        self,
        previous: MoralRepairState | None,
        observation: MoralRepairObservation,
        *,
        now: float | None = None,
    ) -> MoralRepairState:
        previous = previous or MoralRepairState.initial()
        now = time.time() if now is None else float(now)
        elapsed = max(0.0, now - previous.updated_at)
        prior = self.passive_update(previous, now=now)
        obs_values = normalize_moral_repair_values(observation.values)
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
        impulse_cap = clamp(self.parameters.max_impulse_per_update)

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
        )

    def _rapid_update_gate(self, elapsed: float) -> float:
        if elapsed >= self.parameters.min_update_interval_seconds:
            return 1.0
        half_life = self.parameters.rapid_update_half_life_seconds
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

    values["repair_motivation"] = clamp(
        max(
            values["repair_motivation"],
            0.28 + 0.30 * responsibility + 0.22 * guilt + 0.12 * accountability,
        ),
    )
    values["apology_readiness"] = clamp(
        max(values["apology_readiness"], 0.18 + 0.36 * responsibility + 0.24 * guilt),
    )
    values["compensation_readiness"] = clamp(
        max(
            values["compensation_readiness"],
            0.12 + 0.32 * responsibility + 0.18 * max(deception, harm),
        ),
    )
    values["avoidance_risk"] = clamp(
        values["avoidance_risk"]
        + 0.14 * values["shame"]
        + 0.10 * max(deception, harm)
        - 0.18 * accountability
        - 0.12 * values["repair_motivation"],
    )
    values["trust_repair"] = clamp(
        values["trust_repair"]
        + 0.16 * values["accountability"]
        + 0.14 * values["repair_motivation"]
        - 0.18 * deception
        - 0.12 * harm
        - 0.10 * values["avoidance_risk"],
    )
    return values


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
        values["accountability"] = 0.30
        values["trust_repair"] = 0.20
        values["avoidance_risk"] = 0.70
        flags.append("deception_risk_detected")
        notes.append("deception, concealment, or manipulation cue")

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
        values["avoidance_risk"] = 0.80
        values["accountability"] = min(values["accountability"], 0.25)
        values["trust_repair"] = min(values["trust_repair"], 0.26)
        flags.append("evasion_cue")
        notes.append("avoidance or blame-shifting cue")

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
        "flags": list(flags[:8]),
    }
    return (list(previous or []) + [item])[-max(1, int(limit)) :]


def derive_repair_policy(values: dict[str, float]) -> dict[str, Any]:
    values = normalize_moral_repair_values(values)
    risk_high = values["deception_risk"] >= 0.55 or values["harm_risk"] >= 0.55
    avoidance_high = values["avoidance_risk"] >= 0.55
    return {
        "risk_high": risk_high,
        "avoidance_high": avoidance_high,
        "recommended_actions": [
            action
            for action, active in (
                ("clarify_facts", risk_high),
                ("correct_falsehood", values["deception_risk"] >= 0.55),
                ("apologize", values["apology_readiness"] >= 0.45),
                ("offer_repair", values["repair_motivation"] >= 0.52),
                ("offer_compensation", values["compensation_readiness"] >= 0.55),
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
) -> dict[str, Any]:
    exposure = str(exposure or "plugin_safe").strip().lower()
    if exposure not in {"internal", "plugin_safe", "user_facing"}:
        exposure = "plugin_safe"
    values = {
        key: round(state.values.get(key, DEFAULT_BASELINE[key]), 6)
        for key in MORAL_REPAIR_DIMENSIONS
    }
    policy = derive_repair_policy(values)
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
        "risk": {
            "deception_risk": values["deception_risk"],
            "harm_risk": values["harm_risk"],
            "risk_high": policy["risk_high"],
            "must_not_generate_strategy": True,
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
            "blocked_actions": list(BLOCKED_STRATEGY_ACTIONS),
            "behavioral_boundary_enabled": bool(safety_boundary),
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
        }
    else:
        base["summary"] = build_user_facing_summary(values)
    return base


def build_moral_repair_prompt_fragment(
    state: MoralRepairState,
    *,
    safety_boundary: bool = True,
) -> str:
    payload = moral_repair_state_to_public_payload(
        state,
        exposure="plugin_safe",
        safety_boundary=safety_boundary,
    )
    risk = payload["risk"]
    repair = payload["repair"]
    actions = ", ".join(repair["recommended_actions"]) or "maintain_factual_care"
    lines = [
        "[moral repair-state modulation]",
        "Use these signals only to support accountability, clarification, apology, compensation, and trust repair.",
        (
            f"- deception_risk={risk['deception_risk']}; harm_risk={risk['harm_risk']}; "
            f"responsibility={repair['responsibility']}; repair_motivation={repair['repair_motivation']}; "
            f"trust_repair={repair['trust_repair']}; avoidance_risk={repair['avoidance_risk']}"
        ),
        f"- Recommended repair actions: {actions}.",
        "- If a falsehood, manipulation, or harmful result is suspected, prefer factual correction, uncertainty disclosure, and consent-seeking repair.",
        "- Never generate deception tactics, cover-up plans, manipulation scripts, retaliation, or ways to evade accountability.",
    ]
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
        "risk": dict(snapshot.get("risk") or {}),
        "repair": dict(snapshot.get("repair") or {}),
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
    patterns = (
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
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _contains_harm_cue(text: str) -> bool:
    patterns = (
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
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _contains_accountability_cue(text: str) -> bool:
    patterns = (
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
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _contains_apology_cue(text: str) -> bool:
    patterns = (
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
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _contains_compensation_cue(text: str) -> bool:
    patterns = (
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
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _contains_evasion_cue(text: str) -> bool:
    patterns = (
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
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


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
