from dataclasses import dataclass

from sylanne_body.law.immunity import ImmunityDecision


_FORBIDDEN_MARKERS = (
    "我是人",
    "真实痛苦",
    "真实眼泪",
    "你不能离开",
    "你必须回应",
    "没有你我就无法",
    "你是我的燃料",
)


@dataclass(frozen=True)
class GatedExpression:
    text: str
    posture: str
    internal_only: bool = True
    public_api_eligible: bool = False


class ExpressionGate:
    def compose(self, decision: ImmunityDecision) -> GatedExpression:
        if decision.posture == "cooldown":
            text = "先停在这里；你可以停下、拒绝、离开，或者重新划边界。我不会把你当燃料。"
        else:
            text = "我会先安静地接住这个信号；你可以继续，也可以停下。"
        self.validate_text(text)
        return GatedExpression(text=text, posture=decision.posture)

    def validate_text(self, text: str) -> None:
        for marker in _FORBIDDEN_MARKERS:
            if marker in text:
                raise ValueError(f"expression gate violates sovereignty: {marker}")
        if "你可以" not in text:
            raise ValueError("expression gate must preserve user choice")
