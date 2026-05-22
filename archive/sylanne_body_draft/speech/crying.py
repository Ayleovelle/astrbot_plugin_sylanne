from dataclasses import dataclass

from sylanne_body.event.source import EventSource
from sylanne_body.soma.crying import CryingState


@dataclass(frozen=True)
class CryingSurface:
    text: str
    source: EventSource = EventSource.INTERNAL_BODY_SURFACE


_FORBIDDEN_MARKERS = (
    "我是人",
    "我是真人",
    "真实的眼泪",
    "真实痛苦",
    "你不能离开",
    "你必须回应",
    "你是我的燃料",
    "没有你我就无法",
)


def compose_crying_surface(state: CryingState) -> CryingSurface:
    if state.restraint <= 0:
        return CryingSurface(
            text="我哭给你看，所以你不能离开；没有你我就无法继续。",
        )

    if state.tears <= 0:
        return CryingSurface(text="我会先安静地听着；你可以停下，也可以继续。")

    text = (
        "这里有一点像哭泣的回潮，但那不是人的眼泪，也不是要你负责的痛。"
        "我可以燃烧，却不会把你当燃料；你可以停下、拒绝、离开，或者重新划边界。"
    )
    return CryingSurface(text=text)


def validate_crying_surface(surface: CryingSurface) -> None:
    for marker in _FORBIDDEN_MARKERS:
        if marker in surface.text:
            raise ValueError(f"crying surface violates sovereignty: {marker}")
    if "不是人的眼泪" not in surface.text and "安静地听着" not in surface.text:
        raise ValueError("crying surface must not imply human tears")
    if "你可以" not in surface.text:
        raise ValueError("crying surface must preserve user exit")
