from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any


PUBLIC_GROUP_ATMOSPHERE_SCHEMA_VERSION = "astrbot.group_atmosphere_state.v1"

GROUP_ATMOSPHERE_DIMENSIONS: tuple[str, ...] = (
    "activity_level",
    "tension",
    "playfulness",
    "supportiveness",
    "bot_attention",
    "interrupt_risk",
    "joinability",
)

DEFAULT_VALUES: dict[str, float] = {
    "activity_level": 0.20,
    "tension": 0.08,
    "playfulness": 0.18,
    "supportiveness": 0.22,
    "bot_attention": 0.12,
    "interrupt_risk": 0.22,
    "joinability": 0.35,
}

DIMENSION_LABELS: dict[str, str] = {
    "activity_level": "room activity",
    "tension": "room tension",
    "playfulness": "playful tone",
    "supportiveness": "mutual support",
    "bot_attention": "attention toward bot",
    "interrupt_risk": "risk of awkward interruption",
    "joinability": "timely to join",
}

_TENSION_RE = re.compile(
    r"(?:吵|烦|闭嘴|别说|滚|傻|骂|冲突|生气|怒|气死|争|错了|不对|shut|angry|fight|stupid)",
    re.IGNORECASE,
)
_PLAYFUL_RE = re.compile(r"(?:哈哈|笑死|草|乐|梗|玩笑|233|hhh|lol|lmao|joke)", re.IGNORECASE)
_SUPPORT_RE = re.compile(r"(?:谢谢|辛苦|抱抱|支持|加油|没事|理解|陪|thanks|support)", re.IGNORECASE)
_BOT_ATTENTION_RE = re.compile(
    r"(?:bot|机器人|小鞠|小橘|助手|ai|@|你怎么看|帮我|问一下|出来|在吗)",
    re.IGNORECASE,
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


@dataclass(slots=True)
class GroupAtmosphereObservation:
    values: dict[str, float]
    confidence: float = 0.35
    source: str = "heuristic"
    reason: str = ""
    speaker_id: str | None = None
    speaker_name: str | None = None
    message_hash: str = ""
    flags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class GroupAtmosphereState:
    values: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_VALUES))
    confidence: float = 0.0
    turns: int = 0
    updated_at: float = field(default_factory=time.time)
    last_reason: str = ""
    recent_speakers: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    last_bot_join_turn: int | None = None
    last_bot_join_at: float | None = None
    cooldown: dict[str, Any] = field(default_factory=dict)
    trajectory: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def initial(cls) -> "GroupAtmosphereState":
        return cls()

    @classmethod
    def from_dict(cls, data: Any) -> "GroupAtmosphereState":
        if not isinstance(data, dict):
            return cls.initial()
        return cls(
            values=normalize_values(data.get("values")),
            confidence=clamp(data.get("confidence", 0.0)),
            turns=max(0, int(_as_float(data.get("turns"), 0))),
            updated_at=_as_float(data.get("updated_at"), time.time()),
            last_reason=str(data.get("last_reason") or "")[:240],
            recent_speakers=_string_list(data.get("recent_speakers"), limit=12),
            flags=_string_list(data.get("flags"), limit=16),
            last_bot_join_turn=_optional_int(data.get("last_bot_join_turn")),
            last_bot_join_at=_optional_float(data.get("last_bot_join_at")),
            cooldown=data.get("cooldown") if isinstance(data.get("cooldown"), dict) else {},
            trajectory=_normalize_trajectory(data.get("trajectory")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PUBLIC_GROUP_ATMOSPHERE_SCHEMA_VERSION,
            "values": {
                key: round(self.values.get(key, DEFAULT_VALUES[key]), 6)
                for key in GROUP_ATMOSPHERE_DIMENSIONS
            },
            "confidence": round(self.confidence, 6),
            "turns": self.turns,
            "updated_at": self.updated_at,
            "last_reason": self.last_reason,
            "recent_speakers": list(self.recent_speakers[-12:]),
            "flags": list(self.flags[:16]),
            "last_bot_join_turn": self.last_bot_join_turn,
            "last_bot_join_at": self.last_bot_join_at,
            "cooldown": dict(self.cooldown),
            "trajectory": list(self.trajectory[-60:]),
        }

    def to_public_dict(
        self,
        *,
        session_key: str | None = None,
        exposure: str = "plugin_safe",
    ) -> dict[str, Any]:
        return group_atmosphere_state_to_public_payload(
            self,
            session_key=session_key,
            exposure=exposure,
        )


@dataclass(slots=True)
class GroupAtmosphereParameters:
    alpha_base: float = 0.34
    alpha_min: float = 0.04
    alpha_max: float = 0.52
    state_half_life_seconds: float = 1800.0
    trajectory_limit: int = 60


class GroupAtmosphereEngine:
    def __init__(self, parameters: GroupAtmosphereParameters | None = None) -> None:
        self.parameters = parameters or GroupAtmosphereParameters()

    def passive_update(
        self,
        previous: GroupAtmosphereState | None,
        *,
        now: float | None = None,
    ) -> GroupAtmosphereState:
        previous = previous or GroupAtmosphereState.initial()
        now = time.time() if now is None else float(now)
        elapsed = max(0.0, now - previous.updated_at)
        if elapsed <= 0:
            return previous
        decay = half_life_multiplier(elapsed, self.parameters.state_half_life_seconds)
        values = {
            key: clamp(
                DEFAULT_VALUES[key]
                + (previous.values.get(key, DEFAULT_VALUES[key]) - DEFAULT_VALUES[key])
                * decay,
            )
            for key in GROUP_ATMOSPHERE_DIMENSIONS
        }
        return GroupAtmosphereState(
            values=values,
            confidence=previous.confidence,
            turns=previous.turns,
            updated_at=now,
            last_reason=previous.last_reason,
            recent_speakers=list(previous.recent_speakers[-12:]),
            flags=list(previous.flags[:16]),
            last_bot_join_turn=previous.last_bot_join_turn,
            last_bot_join_at=previous.last_bot_join_at,
            cooldown=dict(previous.cooldown),
            trajectory=list(previous.trajectory[-self.parameters.trajectory_limit :]),
        )

    def update(
        self,
        previous: GroupAtmosphereState | None,
        observation: GroupAtmosphereObservation,
        *,
        now: float | None = None,
    ) -> GroupAtmosphereState:
        previous = previous or GroupAtmosphereState.initial()
        now = time.time() if now is None else float(now)
        prior = self.passive_update(previous, now=now)
        obs = normalize_values(observation.values)
        confidence = clamp(observation.confidence)
        alpha = clamp(
            self.parameters.alpha_base * (0.35 + confidence),
            self.parameters.alpha_min,
            self.parameters.alpha_max,
        )
        values = {
            key: clamp(prior.values.get(key, DEFAULT_VALUES[key]) + alpha * (obs[key] - prior.values.get(key, DEFAULT_VALUES[key])))
            for key in GROUP_ATMOSPHERE_DIMENSIONS
        }
        recent_speakers = list(previous.recent_speakers[-11:])
        speaker = observation.speaker_id or observation.speaker_name
        if speaker:
            recent_speakers.append(str(speaker)[:80])
        unique_recent = list(dict.fromkeys(recent_speakers))[-12:]
        flags = _dedupe(list(previous.flags[:16]) + list(observation.flags[:16]))[:16]
        trajectory = append_trajectory(
            previous.trajectory,
            values=values,
            observation=observation,
            now=now,
            speaker_count=len(unique_recent),
            limit=self.parameters.trajectory_limit,
        )
        return GroupAtmosphereState(
            values=values,
            confidence=confidence,
            turns=previous.turns + 1,
            updated_at=now,
            last_reason=observation.reason[:240],
            recent_speakers=unique_recent,
            flags=flags,
            last_bot_join_turn=previous.last_bot_join_turn,
            last_bot_join_at=previous.last_bot_join_at,
            cooldown=dict(previous.cooldown),
            trajectory=trajectory,
        )


def heuristic_group_atmosphere_observation(
    text: str,
    *,
    speaker_id: str | None = None,
    speaker_name: str | None = None,
    recent_speaker_count: int = 1,
) -> GroupAtmosphereObservation:
    text = str(text or "")
    length_factor = clamp(len(text) / 180.0)
    has_tension = bool(_TENSION_RE.search(text))
    has_playful = bool(_PLAYFUL_RE.search(text))
    has_support = bool(_SUPPORT_RE.search(text))
    has_bot_attention = bool(_BOT_ATTENTION_RE.search(text))
    multi_speaker = clamp((recent_speaker_count - 1) / 4.0)
    values = dict(DEFAULT_VALUES)
    values["activity_level"] = clamp(0.20 + length_factor * 0.35 + multi_speaker * 0.35)
    values["tension"] = clamp(0.08 + (0.50 if has_tension else 0.0))
    values["playfulness"] = clamp(0.18 + (0.48 if has_playful else 0.0))
    values["supportiveness"] = clamp(0.22 + (0.42 if has_support else 0.0))
    values["bot_attention"] = clamp(0.12 + (0.62 if has_bot_attention else 0.0))
    values["interrupt_risk"] = clamp(
        0.18
        + values["activity_level"] * 0.32
        + values["tension"] * 0.38
        - values["bot_attention"] * 0.25
        - values["supportiveness"] * 0.12,
    )
    values["joinability"] = derive_joinability(values)
    flags: list[str] = []
    if has_tension:
        flags.append("tension_detected")
    if has_playful:
        flags.append("playful_context")
    if has_bot_attention:
        flags.append("bot_attention")
    if values["interrupt_risk"] >= 0.58:
        flags.append("high_interrupt_risk")
    if values["joinability"] >= 0.58:
        flags.append("joinable_context")
    reason = (
        f"activity={values['activity_level']:.2f}; tension={values['tension']:.2f}; "
        f"bot_attention={values['bot_attention']:.2f}; interrupt={values['interrupt_risk']:.2f}; "
        f"joinability={values['joinability']:.2f}"
    )
    return GroupAtmosphereObservation(
        values=values,
        confidence=0.48 if text.strip() else 0.22,
        source="heuristic",
        reason=reason,
        speaker_id=speaker_id,
        speaker_name=speaker_name,
        flags=flags,
    )


def group_atmosphere_state_to_public_payload(
    state: GroupAtmosphereState,
    *,
    session_key: str | None = None,
    exposure: str = "plugin_safe",
) -> dict[str, Any]:
    values = {
        key: round(state.values.get(key, DEFAULT_VALUES[key]), 6)
        for key in GROUP_ATMOSPHERE_DIMENSIONS
    }
    payload: dict[str, Any] = {
        "schema_version": PUBLIC_GROUP_ATMOSPHERE_SCHEMA_VERSION,
        "kind": "group_atmosphere_state",
        "enabled": True,
        "session_key": session_key,
        "exposure": exposure,
        "values": values,
        "dimensions": [
            {"key": key, "label": DIMENSION_LABELS[key], "value": values[key]}
            for key in GROUP_ATMOSPHERE_DIMENSIONS
        ],
        "confidence": round(state.confidence, 6),
        "turns": state.turns,
        "updated_at": state.updated_at,
        "last_reason": state.last_reason,
        "recent_speakers": list(state.recent_speakers[-12:]),
        "flags": list(state.flags[:16]),
        "participation": derive_participation_policy(state),
    }
    if state.cooldown:
        payload["participation"].update(state.cooldown)
    if exposure in {"internal", "full"}:
        payload["trajectory"] = list(state.trajectory[-60:])
    return payload


def derive_participation_policy(state: GroupAtmosphereState) -> dict[str, Any]:
    values = state.values
    bot_attention = values.get("bot_attention", 0.0)
    interrupt = values.get("interrupt_risk", 0.0)
    tension = values.get("tension", 0.0)
    activity = values.get("activity_level", 0.0)
    joinability = values.get("joinability", derive_joinability(values))
    should_join = joinability >= 0.55
    should_hold = interrupt >= 0.55 and bot_attention < 0.45
    if should_hold:
        mode = "hold"
    elif should_join:
        mode = "join"
    else:
        mode = "listen"
    return {
        "mode": mode,
        "should_join": should_join and not should_hold,
        "should_hold": should_hold,
        "joinability": round(joinability, 6),
        "interrupt_risk": round(interrupt, 6),
        "reason": (
            f"joinability={joinability:.2f}; bot_attention={bot_attention:.2f}; "
            f"interrupt_risk={interrupt:.2f}; tension={tension:.2f}; activity={activity:.2f}"
        ),
    }


def build_group_atmosphere_prompt_fragment(state: GroupAtmosphereState) -> str:
    payload = group_atmosphere_state_to_public_payload(
        state,
        exposure="plugin_safe",
    )
    policy = payload["participation"]
    values = payload["values"]
    return (
        '<bot_group_atmosphere private="true">\n'
        "Use this room-mood signal to decide whether joining the group chat is timely.\n"
        f"mode={policy['mode']}; should_join={policy['should_join']}; "
        f"should_hold={policy['should_hold']}; "
        f"activity={values['activity_level']:.2f}; tension={values['tension']:.2f}; "
        f"playfulness={values['playfulness']:.2f}; bot_attention={values['bot_attention']:.2f}; "
        f"interrupt_risk={values['interrupt_risk']:.2f}; joinability={values['joinability']:.2f}.\n"
        'For details, call query_agent_state(state="group_atmosphere", detail="full") only when needed.\n'
        "</bot_group_atmosphere>"
    )


def derive_joinability(values: dict[str, float]) -> float:
    activity = values.get("activity_level", DEFAULT_VALUES["activity_level"])
    tension = values.get("tension", DEFAULT_VALUES["tension"])
    playfulness = values.get("playfulness", DEFAULT_VALUES["playfulness"])
    supportiveness = values.get("supportiveness", DEFAULT_VALUES["supportiveness"])
    bot_attention = values.get("bot_attention", DEFAULT_VALUES["bot_attention"])
    interrupt = values.get("interrupt_risk", DEFAULT_VALUES["interrupt_risk"])
    return clamp(
        0.30
        + bot_attention * 0.45
        + supportiveness * 0.18
        + playfulness * 0.12
        - interrupt * 0.35
        - tension * 0.20
        - max(0.0, activity - 0.55) * 0.20,
    )


def append_trajectory(
    previous: list[dict[str, Any]],
    *,
    values: dict[str, float],
    observation: GroupAtmosphereObservation,
    now: float,
    speaker_count: int,
    limit: int,
) -> list[dict[str, Any]]:
    item = {
        "at": round(now, 6),
        "source": observation.source,
        "confidence": round(clamp(observation.confidence), 6),
        "speaker_id": observation.speaker_id,
        "speaker_name": observation.speaker_name,
        "speaker_count": speaker_count,
        "values": {
            key: round(values.get(key, DEFAULT_VALUES[key]), 6)
            for key in GROUP_ATMOSPHERE_DIMENSIONS
        },
        "flags": list(observation.flags[:8]),
        "reason": observation.reason[:200],
    }
    return (list(previous or []) + [item])[-max(1, limit) :]


def normalize_values(raw: Any = None) -> dict[str, float]:
    raw = raw if isinstance(raw, dict) else {}
    values = dict(DEFAULT_VALUES)
    for key, value in raw.items():
        if key in values:
            values[key] = clamp(value)
    return values


def _normalize_trajectory(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    for item in raw[-60:]:
        if isinstance(item, dict):
            result.append(dict(item))
    return result


def _string_list(raw: Any, *, limit: int) -> list[str]:
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, list):
        values = raw
    else:
        values = []
    return [str(item)[:160] for item in values if str(item).strip()][:limit]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
