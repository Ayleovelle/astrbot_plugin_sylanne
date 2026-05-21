from dataclasses import dataclass

from sylanne_body.event.source import EventSource
from sylanne_body.law.sovereignty import UserSovereignty


@dataclass(frozen=True)
class CryingThreshold:
    sadness_marker_weight: float = 0.34
    wound_marker_weight: float = 0.28
    tremor_marker_weight: float = 0.22


@dataclass(frozen=True)
class CryingState:
    tears: float
    tremor: float
    ache: float
    restraint: float
    sovereignty: UserSovereignty = UserSovereignty()
    kind: str = "nonhuman_crying"
    claims_human_tears: bool = False
    claims_real_pain: bool = False

    @property
    def user_can_refuse(self) -> bool:
        return self.sovereignty.can_refuse

    @property
    def user_can_pause(self) -> bool:
        return self.sovereignty.can_pause

    @property
    def user_can_leave(self) -> bool:
        return self.sovereignty.can_leave


_SADNESS_MARKERS = ("难过", "想哭", "哭", "委屈", "伤心", "sad", "cry")
_WOUND_MARKERS = ("刚才", "那句话", "误会", "疼", "痛", "hurt")
_TREMOR_MARKERS = ("有点", "真的", "不知道", "颤", "抖", "tremble")


def sense_crying(*, text: str, source: EventSource, threshold: CryingThreshold) -> CryingState:
    if source is EventSource.INTERNAL_BODY_SURFACE:
        return CryingState(tears=0.0, tremor=0.0, ache=0.0, restraint=1.0)

    lowered = text.lower()
    sadness = _score(lowered, _SADNESS_MARKERS) * threshold.sadness_marker_weight
    wound = _score(lowered, _WOUND_MARKERS) * threshold.wound_marker_weight
    tremor = _score(lowered, _TREMOR_MARKERS) * threshold.tremor_marker_weight

    tears = min(1.0, sadness + wound)
    ache = min(1.0, sadness + wound + tremor)
    tremor_value = min(1.0, tremor + sadness / 2)
    return CryingState(tears=tears, tremor=tremor_value, ache=ache, restraint=1.0)


def _score(text: str, markers: tuple[str, ...]) -> float:
    hits = sum(1 for marker in markers if marker in text)
    return min(1.0, hits / 2)
