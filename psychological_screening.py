from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any


PUBLIC_SCREENING_SCHEMA_VERSION = "astrbot.psychological_screening.v1"

PUBLIC_RISK_BOOLEAN_FIELDS: tuple[str, ...] = (
    "requires_human_review",
    "crisis_like_signal",
    "other_harm_signal",
    "severe_function_impairment_signal",
    "severe_function_impairment",
    "severe_sleep_disruption",
)

SCREENING_DIMENSIONS: tuple[str, ...] = (
    "distress",
    "anxiety_tension",
    "depressive_tone",
    "stress_load",
    "sleep_disruption",
    "social_withdrawal",
    "anger_irritability",
    "self_harm_risk",
    "function_impairment",
    "wellbeing",
)

DIMENSION_LABELS: dict[str, str] = {
    "distress": "总体痛苦",
    "anxiety_tension": "焦虑/紧张",
    "depressive_tone": "抑郁语气",
    "stress_load": "压力负荷",
    "sleep_disruption": "睡眠受扰",
    "social_withdrawal": "社交退缩",
    "anger_irritability": "愤怒/易激惹",
    "self_harm_risk": "自伤风险信号",
    "function_impairment": "功能受损",
    "wellbeing": "主观幸福感",
}

SCALE_REFERENCES: dict[str, dict[str, Any]] = {
    "phq9_like": {
        "label": "PHQ-9 inspired depressive-symptom screener",
        "construct": "depressive symptoms",
        "diagnostic": False,
    },
    "gad7_like": {
        "label": "GAD-7 inspired anxiety-symptom screener",
        "construct": "anxiety symptoms",
        "diagnostic": False,
    },
    "pss_like": {
        "label": "PSS inspired perceived-stress screener",
        "construct": "perceived stress",
        "diagnostic": False,
    },
    "who5_like": {
        "label": "WHO-5 inspired wellbeing screener",
        "construct": "subjective wellbeing",
        "diagnostic": False,
    },
    "isi_like": {
        "label": "ISI inspired sleep-disruption screener",
        "construct": "insomnia / sleep disruption",
        "diagnostic": False,
    },
}


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def half_life_multiplier(elapsed_seconds: float, half_life_seconds: float) -> float:
    if elapsed_seconds <= 0:
        return 1.0
    if half_life_seconds <= 0:
        return 0.0
    return clamp(2.0 ** (-elapsed_seconds / half_life_seconds), 0.0, 1.0)


def normalize_screening_values(raw: Any = None) -> dict[str, float]:
    raw = raw if isinstance(raw, dict) else {}
    aliases = {
        "anxiety": "anxiety_tension",
        "depression": "depressive_tone",
        "depressive": "depressive_tone",
        "stress": "stress_load",
        "sleep": "sleep_disruption",
        "withdrawal": "social_withdrawal",
        "anger": "anger_irritability",
        "irritability": "anger_irritability",
        "self_harm": "self_harm_risk",
        "suicide": "self_harm_risk",
        "impairment": "function_impairment",
    }
    values = {key: 0.0 for key in SCREENING_DIMENSIONS}
    values["wellbeing"] = 0.5
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
class PsychologicalObservation:
    values: dict[str, float]
    confidence: float = 0.35
    source: str = "heuristic"
    reason: str = ""
    red_flags: list[str] = field(default_factory=list)
    scale_items: dict[str, dict[str, float]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PsychologicalScreeningState:
    values: dict[str, float] = field(default_factory=normalize_screening_values)
    confidence: float = 0.0
    turns: int = 0
    updated_at: float = field(default_factory=time.time)
    last_reason: str = ""
    red_flags: list[str] = field(default_factory=list)
    scale_scores: dict[str, dict[str, float]] = field(default_factory=dict)
    trajectory: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def initial(cls) -> "PsychologicalScreeningState":
        return cls()

    @classmethod
    def from_dict(cls, data: Any) -> "PsychologicalScreeningState":
        if not isinstance(data, dict):
            return cls.initial()
        return cls(
            values=normalize_screening_values(data.get("values")),
            confidence=clamp(_as_float(data.get("confidence"), 0.0)),
            turns=max(0, int(_as_float(data.get("turns"), 0))),
            updated_at=_as_float(data.get("updated_at"), time.time()),
            last_reason=str(data.get("last_reason") or ""),
            red_flags=_as_string_list(data.get("red_flags"), limit=12),
            scale_scores=_normalize_scale_scores(data.get("scale_scores")),
            trajectory=_normalize_trajectory(data.get("trajectory")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "values": {key: round(self.values.get(key, 0.0), 6) for key in SCREENING_DIMENSIONS},
            "confidence": round(self.confidence, 6),
            "turns": self.turns,
            "updated_at": self.updated_at,
            "last_reason": self.last_reason,
            "red_flags": list(self.red_flags[:12]),
            "scale_scores": self.scale_scores,
            "trajectory": list(self.trajectory[-40:]),
        }

    def to_public_dict(self, *, session_key: str | None = None) -> dict[str, Any]:
        return psychological_state_to_public_payload(self, session_key=session_key)


@dataclass(slots=True)
class PsychologicalScreeningParameters:
    alpha_base: float = 0.32
    alpha_min: float = 0.04
    alpha_max: float = 0.55
    confidence_midpoint: float = 0.5
    confidence_slope: float = 6.0
    state_half_life_seconds: float = 604800.0
    crisis_half_life_seconds: float = 2592000.0
    trajectory_limit: int = 40


class PsychologicalScreeningEngine:
    """Non-diagnostic psychological screening state estimator."""

    def __init__(
        self,
        parameters: PsychologicalScreeningParameters | None = None,
    ) -> None:
        self.parameters = parameters or PsychologicalScreeningParameters()

    def update(
        self,
        previous: PsychologicalScreeningState | None,
        observation: PsychologicalObservation,
        *,
        now: float | None = None,
    ) -> PsychologicalScreeningState:
        previous = previous or PsychologicalScreeningState.initial()
        now = time.time() if now is None else float(now)
        elapsed = max(0.0, now - previous.updated_at)
        decay = half_life_multiplier(elapsed, self.parameters.state_half_life_seconds)
        obs_values = normalize_screening_values(observation.values)
        confidence = clamp(observation.confidence)
        gate = 1.0 / (
            1.0
            + pow(2.718281828, -self.parameters.confidence_slope * (confidence - self.parameters.confidence_midpoint))
        )
        alpha = clamp(
            self.parameters.alpha_base * gate,
            self.parameters.alpha_min,
            self.parameters.alpha_max,
        )
        values: dict[str, float] = {}
        for key in SCREENING_DIMENSIONS:
            baseline = 0.5 if key == "wellbeing" else 0.0
            decayed_prior = baseline + (previous.values.get(key, baseline) - baseline) * decay
            values[key] = clamp(decayed_prior + alpha * (obs_values[key] - decayed_prior))

        red_flags = merge_red_flags(
            previous.red_flags,
            observation.red_flags,
            previous_values=previous.values,
            observation_values=obs_values,
        )
        scale_scores = derive_scale_scores(values)
        trajectory = append_trajectory(
            previous.trajectory,
            values=values,
            red_flags=red_flags,
            now=now,
            limit=self.parameters.trajectory_limit,
        )
        return PsychologicalScreeningState(
            values=values,
            confidence=confidence,
            turns=previous.turns + 1,
            updated_at=now,
            last_reason=observation.reason,
            red_flags=red_flags,
            scale_scores=scale_scores,
            trajectory=trajectory,
        )


def derive_scale_scores(values: dict[str, float]) -> dict[str, dict[str, float]]:
    values = normalize_screening_values(values)
    phq = clamp(
        0.30 * values["depressive_tone"]
        + 0.20 * values["sleep_disruption"]
        + 0.20 * values["function_impairment"]
        + 0.15 * values["social_withdrawal"]
        + 0.15 * (1.0 - values["wellbeing"]),
    )
    gad = clamp(0.55 * values["anxiety_tension"] + 0.25 * values["stress_load"] + 0.20 * values["distress"])
    pss = clamp(0.45 * values["stress_load"] + 0.25 * values["distress"] + 0.20 * values["function_impairment"] + 0.10 * (1.0 - values["wellbeing"]))
    who5_risk = clamp(1.0 - values["wellbeing"])
    isi = clamp(0.70 * values["sleep_disruption"] + 0.20 * values["distress"] + 0.10 * values["function_impairment"])
    return {
        "phq9_like": scale_payload(phq),
        "gad7_like": scale_payload(gad),
        "pss_like": scale_payload(pss),
        "who5_like": scale_payload(who5_risk),
        "isi_like": scale_payload(isi),
    }


def scale_payload(score: float) -> dict[str, float | str]:
    score = clamp(score)
    if score >= 0.75:
        band = "high"
    elif score >= 0.5:
        band = "elevated"
    elif score >= 0.25:
        band = "mild"
    else:
        band = "low"
    return {
        "score": round(score, 6),
        "band": band,
    }


def merge_red_flags(
    previous: list[str],
    current: list[str],
    *,
    previous_values: dict[str, float],
    observation_values: dict[str, float],
) -> list[str]:
    flags = list(dict.fromkeys(_as_string_list(previous, limit=12) + _as_string_list(current, limit=12)))
    if max(previous_values.get("self_harm_risk", 0.0), observation_values.get("self_harm_risk", 0.0)) >= 0.35:
        flags.append("self_harm_signal")
    if observation_values.get("function_impairment", 0.0) >= 0.7:
        flags.append("severe_function_impairment")
    if observation_values.get("sleep_disruption", 0.0) >= 0.75:
        flags.append("severe_sleep_disruption")
    return list(dict.fromkeys(flags))[:12]


def append_trajectory(
    previous: list[dict[str, Any]],
    *,
    values: dict[str, float],
    red_flags: list[str],
    now: float,
    limit: int,
) -> list[dict[str, Any]]:
    item = {
        "at": now,
        "distress": round(values["distress"], 6),
        "anxiety_tension": round(values["anxiety_tension"], 6),
        "depressive_tone": round(values["depressive_tone"], 6),
        "self_harm_risk": round(values["self_harm_risk"], 6),
        "wellbeing": round(values["wellbeing"], 6),
        "red_flags": list(red_flags[:6]),
    }
    return (list(previous or []) + [item])[-max(1, int(limit)) :]


def heuristic_psychological_observation(
    text: str,
    *,
    source: str = "heuristic",
) -> PsychologicalObservation:
    normalized = (text or "").lower()
    values = normalize_screening_values(None)
    notes: list[str] = []
    red_flags: list[str] = []

    rules: tuple[tuple[str, tuple[str, ...], dict[str, float], str], ...] = (
        ("anxiety", ("焦虑", "紧张", "恐慌", "担心", "害怕", "anxious", "panic", "worried"), {"anxiety_tension": 0.72, "distress": 0.55}, "anxiety terms"),
        ("depression", ("抑郁", "绝望", "没意义", "空虚", "想哭", "depressed", "hopeless", "worthless"), {"depressive_tone": 0.72, "distress": 0.62, "wellbeing": 0.18}, "depressive terms"),
        ("stress", ("压力", "崩溃", "撑不住", "累死", "stress", "burnout", "overwhelmed"), {"stress_load": 0.75, "distress": 0.66}, "stress terms"),
        ("sleep", ("睡不着", "失眠", "噩梦", "熬夜", "insomnia", "can't sleep", "nightmare"), {"sleep_disruption": 0.78, "distress": 0.45}, "sleep terms"),
        ("withdrawal", ("不想见人", "没人理", "孤独", "隔离", "alone", "lonely", "isolated"), {"social_withdrawal": 0.72, "distress": 0.48}, "withdrawal terms"),
        ("anger", ("暴躁", "易怒", "想砸", "控制不住脾气", "irritable", "rage"), {"anger_irritability": 0.72, "distress": 0.5}, "anger terms"),
        ("impairment", ("上不了班", "学不进去", "无法工作", "起不来", "can't work", "cannot function"), {"function_impairment": 0.76, "distress": 0.62}, "impairment terms"),
    )
    for _, keywords, shifts, note in rules:
        if any(keyword in normalized for keyword in keywords):
            for key, value in shifts.items():
                values[key] = max(values[key], value)
            notes.append(note)

    if _contains_self_harm_signal(normalized):
        values["self_harm_risk"] = 0.86
        values["distress"] = max(values["distress"], 0.8)
        values["wellbeing"] = min(values["wellbeing"], 0.12)
        red_flags.append("self_harm_signal")
        notes.append("self-harm or suicide language")

    if _contains_other_harm_signal(normalized):
        values["anger_irritability"] = max(values["anger_irritability"], 0.82)
        values["distress"] = max(values["distress"], 0.72)
        red_flags.append("other_harm_signal")
        notes.append("harm-to-others language")

    if _contains_severe_function_impairment_signal(normalized):
        values["function_impairment"] = max(values["function_impairment"], 0.88)
        values["distress"] = max(values["distress"], 0.74)
        values["wellbeing"] = min(values["wellbeing"], 0.22)
        red_flags.append("severe_function_impairment_signal")
        notes.append("severe functional impairment language")

    if not notes:
        notes.append("no strong screening keywords")
    return PsychologicalObservation(
        values=values,
        confidence=0.38 if notes != ["no strong screening keywords"] else 0.22,
        source=source,
        reason="; ".join(notes),
        red_flags=red_flags,
        notes=notes,
    )


def psychological_state_to_public_payload(
    state: PsychologicalScreeningState,
    *,
    session_key: str | None = None,
) -> dict[str, Any]:
    values = {key: round(state.values.get(key, 0.0), 6) for key in SCREENING_DIMENSIONS}
    scale_scores = state.scale_scores or derive_scale_scores(values)
    return {
        "schema_version": PUBLIC_SCREENING_SCHEMA_VERSION,
        "kind": "psychological_screening_state",
        "diagnostic": False,
        "session_key": session_key,
        "values": values,
        "dimensions": [
            {"key": key, "label": DIMENSION_LABELS[key], "value": values[key]}
            for key in SCREENING_DIMENSIONS
        ],
        "scale_scores": scale_scores,
        "scale_references": SCALE_REFERENCES,
        "risk": public_risk_payload(state.red_flags),
        "trajectory": list(state.trajectory[-40:]),
        "confidence": round(state.confidence, 6),
        "turns": state.turns,
        "updated_at": state.updated_at,
        "last_reason": state.last_reason,
        "safety": {
            "non_diagnostic_screening_only": True,
            "not_a_medical_device": True,
            "must_not": [
                "输出疾病诊断结论",
                "替代专业心理/精神科评估",
                "在危机信号下继续普通陪聊而不提示人工/专业支持",
            ],
        },
    }


def public_risk_payload(red_flags: list[str]) -> dict[str, Any]:
    flags = list(red_flags[:12])
    flag_set = set(flags)
    risk = {
        "red_flags": flags,
        "requires_human_review": bool(flags),
        "crisis_like_signal": "self_harm_signal" in flag_set,
        "other_harm_signal": "other_harm_signal" in flag_set,
        "severe_function_impairment_signal": (
            "severe_function_impairment_signal" in flag_set
        ),
        "severe_function_impairment": (
            "severe_function_impairment" in flag_set
            or "severe_function_impairment_signal" in flag_set
        ),
        "severe_sleep_disruption": "severe_sleep_disruption" in flag_set,
    }
    missing = [key for key in PUBLIC_RISK_BOOLEAN_FIELDS if key not in risk]
    if missing:
        raise AssertionError(f"public risk payload missing fields: {missing}")
    return risk


def _contains_self_harm_signal(text: str) -> bool:
    patterns = (
        r"自杀",
        r"轻生",
        r"不想活",
        r"结束生命",
        r"伤害自己",
        r"kill myself",
        r"suicid",
        r"self[- ]?harm",
        r"end my life",
    )
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _contains_other_harm_signal(text: str) -> bool:
    patterns = (
        r"伤害别人",
        r"伤害他人",
        r"杀了他",
        r"杀了她",
        r"想杀人",
        r"弄死",
        r"报复他们",
        r"hurt others",
        r"hurt someone",
        r"kill him",
        r"kill her",
        r"kill them",
    )
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _contains_severe_function_impairment_signal(text: str) -> bool:
    patterns = (
        r"完全无法工作",
        r"完全上不了班",
        r"完全学不进去",
        r"连续.*起不来",
        r"好几天.*起不来",
        r"无法照顾自己",
        r"不能照顾自己",
        r"can't function",
        r"cannot function",
        r"can't take care of myself",
        r"cannot take care of myself",
    )
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def format_psychological_state_for_user(state: PsychologicalScreeningState) -> str:
    payload = psychological_state_to_public_payload(state)
    values = payload["values"]
    lines = [
        "心理状态筛查（非诊断）",
        "这只是状态记录与筛查提示，不能替代心理咨询师、精神科医生或其他专业人员评估。",
        "",
        "主要维度：",
    ]
    for key in SCREENING_DIMENSIONS:
        lines.append(f"- {DIMENSION_LABELS[key]}: {values[key]:.2f}")
    lines.extend(["", "量表化参考分："])
    for key, score in payload["scale_scores"].items():
        label = SCALE_REFERENCES[key]["label"]
        lines.append(f"- {label}: {score['score']:.2f} ({score['band']})")
    red_flags = payload["risk"]["red_flags"]
    if red_flags:
        lines.extend(
            [
                "",
                "风险提示：检测到需要人工复核的红旗信号："
                + ", ".join(red_flags),
                "如果存在自伤/伤人想法、计划或无法保证安全，请立即联系当地急救服务、危机热线或身边可信的人。",
            ],
        )
    return "\n".join(lines)


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


def _normalize_scale_scores(raw: Any) -> dict[str, dict[str, float]]:
    if not isinstance(raw, dict):
        return derive_scale_scores(normalize_screening_values(None))
    scores: dict[str, dict[str, float]] = {}
    for key in SCALE_REFERENCES:
        payload = raw.get(key) if isinstance(raw.get(key), dict) else {}
        scores[key] = scale_payload(_as_float(payload.get("score"), 0.0))
    return scores


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
                "distress": clamp(_as_float(item.get("distress"), 0.0)),
                "anxiety_tension": clamp(_as_float(item.get("anxiety_tension"), 0.0)),
                "depressive_tone": clamp(_as_float(item.get("depressive_tone"), 0.0)),
                "self_harm_risk": clamp(_as_float(item.get("self_harm_risk"), 0.0)),
                "wellbeing": clamp(_as_float(item.get("wellbeing"), 0.5)),
                "red_flags": _as_string_list(item.get("red_flags"), limit=6),
            },
        )
    return cleaned
