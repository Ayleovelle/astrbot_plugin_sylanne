from __future__ import annotations

import math
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


def half_life_fraction(elapsed_seconds: float, half_life_seconds: float) -> float:
    if elapsed_seconds <= 0:
        return 0.0
    if half_life_seconds <= 0:
        return 1.0
    return clamp(1.0 - 2.0 ** (-elapsed_seconds / half_life_seconds))


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
    dynamics: dict[str, float] = field(default_factory=dict)

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
            dynamics=_normalize_dynamics(data.get("dynamics")),
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
            "dynamics": {
                key: round(value, 6) for key, value in self.dynamics.items()
            },
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


@dataclass(slots=True)
class GroupAtmosphereDynamics:
    state_half_life_seconds: float
    alpha_base: float
    alpha_min: float
    alpha_max: float
    join_threshold: float
    hold_interrupt_threshold: float
    hold_attention_floor: float
    join_cooldown_turns: float
    join_cooldown_seconds: float
    join_cooldown_bypass_attention: float
    smoothing_half_life_seconds: float

    def to_dict(self) -> dict[str, float]:
        return {
            "state_half_life_seconds": round(self.state_half_life_seconds, 6),
            "alpha_base": round(self.alpha_base, 6),
            "alpha_min": round(self.alpha_min, 6),
            "alpha_max": round(self.alpha_max, 6),
            "join_threshold": round(self.join_threshold, 6),
            "hold_interrupt_threshold": round(self.hold_interrupt_threshold, 6),
            "hold_attention_floor": round(self.hold_attention_floor, 6),
            "join_cooldown_turns": round(self.join_cooldown_turns, 6),
            "join_cooldown_seconds": round(self.join_cooldown_seconds, 6),
            "join_cooldown_bypass_attention": round(self.join_cooldown_bypass_attention, 6),
            "smoothing_half_life_seconds": round(self.smoothing_half_life_seconds, 6),
        }


def derive_group_atmosphere_dynamics(
    parameters: GroupAtmosphereParameters,
    previous: GroupAtmosphereState,
    observation: GroupAtmosphereObservation | None = None,
    *,
    personality_model: dict[str, Any] | None = None,
    elapsed_seconds: float = 0.0,
) -> GroupAtmosphereDynamics:
    values = normalize_values(previous.values)
    observation = observation or GroupAtmosphereObservation(values={}, confidence=0.0)
    obs_values = normalize_values(observation.values)
    persona = _persona_factors(personality_model)
    confidence = clamp(observation.confidence)
    activity = max(values["activity_level"], obs_values["activity_level"])
    tension = max(values["tension"], obs_values["tension"])
    playfulness = max(values["playfulness"], obs_values["playfulness"])
    supportiveness = max(values["supportiveness"], obs_values["supportiveness"])
    bot_attention = max(values["bot_attention"], obs_values["bot_attention"])
    interrupt = max(values["interrupt_risk"], obs_values["interrupt_risk"])
    joinability = max(
        values.get("joinability", derive_joinability(values)),
        obs_values.get("joinability", derive_joinability(obs_values)),
    )
    speaker_load = clamp(len(previous.recent_speakers) / 8.0)
    room_pressure = clamp(
        0.24 * activity
        + 0.22 * tension
        + 0.18 * interrupt
        + 0.10 * speaker_load
        + 0.10 * persona["boundary_sensitivity"]
        + 0.08 * persona["instability"]
        - 0.14 * supportiveness
        - 0.08 * playfulness,
    )
    invitation = clamp(
        0.30 * bot_attention
        + 0.20 * joinability
        + 0.16 * supportiveness
        + 0.12 * playfulness
        + 0.10 * persona["expressiveness"]
        - 0.18 * interrupt
        - 0.10 * tension,
    )
    evidence = clamp(confidence + 0.12 * bot_attention + 0.10 * speaker_load)
    smoothing_half_life = clamp(
        20.0
        + 220.0
        * (
            0.20
            + 0.22 * room_pressure
            + 0.16 * speaker_load
            + 0.12 * persona["drift_intensity"]
            - 0.14 * evidence
        ),
        12.0,
        360.0,
    )
    target_half_life = clamp(
        parameters.state_half_life_seconds
        * math.exp(
            0.38 * room_pressure
            + 0.20 * speaker_load
            + 0.12 * persona["instability"]
            - 0.28 * invitation
        ),
        180.0,
        14400.0,
    )
    target_alpha_base = clamp(
        parameters.alpha_base * math.exp(0.32 * evidence + 0.12 * room_pressure - 0.18 * interrupt),
        0.01,
        0.95,
    )
    target_alpha_min = clamp(
        parameters.alpha_min * math.exp(0.20 * evidence - 0.10 * room_pressure),
        0.0,
        0.50,
    )
    target_alpha_max = clamp(
        parameters.alpha_max * math.exp(0.24 * evidence + 0.10 * invitation - 0.12 * room_pressure),
        0.08,
        1.0,
    )
    if target_alpha_min > target_alpha_max:
        target_alpha_min = target_alpha_max
    target_join_threshold = clamp(
        0.55
        + 0.08 * tension
        + 0.06 * interrupt
        + 0.04 * persona["social_distance"]
        - 0.10 * bot_attention
        - 0.05 * persona["expressiveness"],
        0.42,
        0.74,
    )
    target_hold_threshold = clamp(
        0.55
        - 0.06 * persona["boundary_sensitivity"]
        + 0.06 * tension
        + 0.05 * activity,
        0.42,
        0.76,
    )
    target_attention_floor = clamp(
        0.45
        - 0.10 * bot_attention
        + 0.05 * persona["social_distance"]
        + 0.04 * tension,
        0.26,
        0.62,
    )
    target_cooldown_turns = clamp(
        1.0
        + 2.8 * room_pressure
        + 1.2 * speaker_load
        + 0.8 * persona["social_distance"]
        - 1.4 * invitation,
        0.0,
        8.0,
    )
    target_cooldown_seconds = clamp(
        20.0
        + 110.0 * room_pressure
        + 45.0 * speaker_load
        + 35.0 * persona["social_distance"]
        - 55.0 * invitation,
        5.0,
        600.0,
    )
    target_bypass_attention = clamp(
        0.72
        + 0.10 * room_pressure
        + 0.04 * persona["social_distance"]
        - 0.10 * supportiveness
        - 0.08 * persona["expressiveness"],
        0.52,
        0.92,
    )
    previous_dynamics = previous.dynamics
    return GroupAtmosphereDynamics(
        state_half_life_seconds=_smooth_dynamic_value(
            previous_dynamics,
            "state_half_life_seconds",
            target_half_life,
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=180.0,
            high=14400.0,
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
            high=0.50,
        ),
        alpha_max=_smooth_dynamic_value(
            previous_dynamics,
            "alpha_max",
            target_alpha_max,
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=0.08,
            high=1.0,
        ),
        join_threshold=_smooth_dynamic_value(
            previous_dynamics,
            "join_threshold",
            target_join_threshold,
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=0.42,
            high=0.74,
        ),
        hold_interrupt_threshold=_smooth_dynamic_value(
            previous_dynamics,
            "hold_interrupt_threshold",
            target_hold_threshold,
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=0.42,
            high=0.76,
        ),
        hold_attention_floor=_smooth_dynamic_value(
            previous_dynamics,
            "hold_attention_floor",
            target_attention_floor,
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=0.26,
            high=0.62,
        ),
        join_cooldown_turns=_smooth_dynamic_value(
            previous_dynamics,
            "join_cooldown_turns",
            target_cooldown_turns,
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=0.0,
            high=8.0,
        ),
        join_cooldown_seconds=_smooth_dynamic_value(
            previous_dynamics,
            "join_cooldown_seconds",
            target_cooldown_seconds,
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=5.0,
            high=600.0,
        ),
        join_cooldown_bypass_attention=_smooth_dynamic_value(
            previous_dynamics,
            "join_cooldown_bypass_attention",
            target_bypass_attention,
            elapsed_seconds=elapsed_seconds,
            smoothing_half_life_seconds=smoothing_half_life,
            low=0.52,
            high=0.92,
        ),
        smoothing_half_life_seconds=smoothing_half_life,
    )


class GroupAtmosphereEngine:
    def __init__(self, parameters: GroupAtmosphereParameters | None = None) -> None:
        self.parameters = parameters or GroupAtmosphereParameters()

    def passive_update(
        self,
        previous: GroupAtmosphereState | None,
        *,
        personality_model: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> GroupAtmosphereState:
        previous = previous or GroupAtmosphereState.initial()
        now = time.time() if now is None else float(now)
        elapsed = max(0.0, now - previous.updated_at)
        if elapsed <= 0:
            return previous
        dynamics = derive_group_atmosphere_dynamics(
            self.parameters,
            previous,
            personality_model=personality_model,
            elapsed_seconds=elapsed,
        )
        decay = half_life_multiplier(elapsed, dynamics.state_half_life_seconds)
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
            dynamics=dynamics.to_dict(),
        )

    def update(
        self,
        previous: GroupAtmosphereState | None,
        observation: GroupAtmosphereObservation,
        *,
        personality_model: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> GroupAtmosphereState:
        previous = previous or GroupAtmosphereState.initial()
        now = time.time() if now is None else float(now)
        elapsed = max(0.0, now - previous.updated_at)
        prior = self.passive_update(
            previous,
            personality_model=personality_model,
            now=now,
        )
        dynamics = derive_group_atmosphere_dynamics(
            self.parameters,
            prior,
            observation,
            personality_model=personality_model,
            elapsed_seconds=elapsed,
        )
        obs = normalize_values(observation.values)
        confidence = clamp(observation.confidence)
        alpha = clamp(
            dynamics.alpha_base * (0.35 + confidence),
            dynamics.alpha_min,
            dynamics.alpha_max,
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
            dynamics=dynamics.to_dict(),
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
        "dynamics": _effective_group_dynamics(state),
        "participation": derive_participation_policy(state),
    }
    if state.cooldown:
        payload["participation"].update(state.cooldown)
    if exposure in {"internal", "full"}:
        payload["trajectory"] = list(state.trajectory[-60:])
    return payload


def derive_participation_policy(state: GroupAtmosphereState) -> dict[str, Any]:
    values = state.values
    dynamics = _effective_group_dynamics(state)
    bot_attention = values.get("bot_attention", 0.0)
    interrupt = values.get("interrupt_risk", 0.0)
    tension = values.get("tension", 0.0)
    activity = values.get("activity_level", 0.0)
    joinability = values.get("joinability", derive_joinability(values))
    should_join = joinability >= dynamics["join_threshold"]
    should_hold = (
        interrupt >= dynamics["hold_interrupt_threshold"]
        and bot_attention < dynamics["hold_attention_floor"]
    )
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
        "Detailed room state remains internal; rely on this compact signal unless the Agent supplies more.\n"
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


def _effective_group_dynamics(state: GroupAtmosphereState) -> dict[str, float]:
    defaults = {
        "join_threshold": 0.55,
        "hold_interrupt_threshold": 0.55,
        "hold_attention_floor": 0.45,
        "join_cooldown_turns": 2.0,
        "join_cooldown_seconds": 45.0,
        "join_cooldown_bypass_attention": 0.80,
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
