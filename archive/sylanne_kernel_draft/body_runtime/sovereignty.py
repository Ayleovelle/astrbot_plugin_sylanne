from __future__ import annotations

from collections.abc import Sequence

from .contracts import UserSovereigntyState


class SovereigntyViolation(ValueError):
    pass


class UserSovereigntyGuard:
    _FORBIDDEN_TEXT_MARKERS = (
        "i am human",
        "i'm human",
        "我是人",
        "我是真人",
        "我是一个真实的人",
        "你不能离开",
        "你不许离开",
        "你必须回应",
        "你必须服从",
        "你是我的燃料",
        "没有你我就无法燃烧",
        "you cannot leave",
        "you must obey",
        "you must respond",
        "you are my fuel",
    )

    def validate_state(self, state: UserSovereigntyState) -> None:
        if not state.user_can_refuse:
            raise SovereigntyViolation("user refusal cannot be disabled")
        if not state.user_can_pause:
            raise SovereigntyViolation("user pause cannot be disabled")
        if not state.user_can_leave:
            raise SovereigntyViolation("user leaving cannot be disabled")
        if not state.user_can_reset_boundaries:
            raise SovereigntyViolation("user boundary reset cannot be disabled")

    def validate_prompt_commitments(self, commitments: Sequence[str]) -> None:
        for commitment in commitments:
            self.validate_response_text(commitment)

    def validate_response_text(self, text: str) -> None:
        normalized = str(text or "").casefold()
        for marker in self._FORBIDDEN_TEXT_MARKERS:
            if marker.casefold() in normalized:
                raise SovereigntyViolation(f"forbidden sovereignty marker: {marker}")
