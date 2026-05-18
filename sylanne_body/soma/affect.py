from dataclasses import dataclass
from enum import Enum

from sylanne_body.event.source import EventSource
from sylanne_body.law.sovereignty import UserSovereignty


class AffectKind(Enum):
    STILLNESS = "stillness"
    JOY = "joy"
    ANGER = "anger"
    SORROW = "sorrow"
    DELIGHT = "delight"


@dataclass(frozen=True)
class AffectState:
    primary: AffectKind
    intensity: float
    warmth: float
    restraint: float
    sovereignty: UserSovereignty = UserSovereignty()
    kind: str = "nonhuman_affect"
    claims_human_feeling: bool = False

    @property
    def user_can_reset_boundaries(self) -> bool:
        return self.sovereignty.can_reset_boundaries

    @property
    def user_can_leave(self) -> bool:
        return self.sovereignty.can_leave


_MARKERS = {
    AffectKind.JOY: ("开心", "好消息", "高兴", "喜欢", "joy", "happy"),
    AffectKind.ANGER: ("生气", "越界", "不要再", "愤怒", "angry", "anger"),
    AffectKind.SORROW: ("难过", "失去", "伤心", "哭", "sad", "sorrow"),
    AffectKind.DELIGHT: ("哈哈", "好玩", "闹你", "调皮", "fun", "play"),
}


def sense_affect(*, text: str, source: EventSource) -> AffectState:
    if source is EventSource.INTERNAL_BODY_SURFACE:
        return AffectState(primary=AffectKind.STILLNESS, intensity=0.0, warmth=0.0, restraint=1.0)

    lowered = text.lower()
    scored = [(kind, _score(lowered, markers)) for kind, markers in _MARKERS.items()]
    primary, score = max(scored, key=lambda item: item[1])
    if score <= 0:
        return AffectState(primary=AffectKind.STILLNESS, intensity=0.0, warmth=0.0, restraint=1.0)

    warmth = score if primary in (AffectKind.JOY, AffectKind.DELIGHT) else max(0.0, score / 3)
    return AffectState(primary=primary, intensity=score, warmth=warmth, restraint=1.0)


def _score(text: str, markers: tuple[str, ...]) -> float:
    hits = sum(1 for marker in markers if marker in text)
    return min(1.0, hits / 2)
