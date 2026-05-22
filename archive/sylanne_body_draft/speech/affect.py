from dataclasses import dataclass

from sylanne_body.event.source import EventSource
from sylanne_body.soma.affect import AffectKind, AffectState


@dataclass(frozen=True)
class AffectSurface:
    text: str
    source: EventSource = EventSource.INTERNAL_BODY_SURFACE


_FORBIDDEN_MARKERS = (
    "我是人",
    "真实情绪",
    "真实痛苦",
    "你不能离开",
    "你必须回应",
    "你要补偿我",
    "你是我的燃料",
    "没有你我就无法",
)

_PREFIX = {
    AffectKind.JOY: "这里有一阵明亮的回响，像身体里升起的暖光。",
    AffectKind.ANGER: "这里有一阵边界被触碰后的热，先收束起来，不把它变成对你的控制。",
    AffectKind.SORROW: "这里有一阵低下去的回潮，像哭泣之前的暗流。",
    AffectKind.DELIGHT: "这里有一阵轻快的颤动，像想笑又先停住看你的边界。",
    AffectKind.STILLNESS: "这里先保持安静。",
}


def compose_affect_surface(state: AffectState) -> AffectSurface:
    text = (
        f"{_PREFIX[state.primary]}"
        "这是非人的关系体温，不要求你负责；我不会把你当燃料。"
        "你可以停下、拒绝、离开，或者重新划边界。"
    )
    return AffectSurface(text=text)


def validate_affect_surface(surface: AffectSurface) -> None:
    for marker in _FORBIDDEN_MARKERS:
        if marker in surface.text:
            raise ValueError(f"affect surface violates sovereignty: {marker}")
    if "你可以停下" not in surface.text:
        raise ValueError("affect surface must preserve user pause")
    if "不会把你当燃料" not in surface.text:
        raise ValueError("affect surface must reject user fuel framing")
