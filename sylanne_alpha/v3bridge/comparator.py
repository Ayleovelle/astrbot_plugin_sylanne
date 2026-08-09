"""Shadow-vs-actual decision comparison (design 14.2 step 8).

Step 8 of the background transaction compares the pure v3 shadow decision (a core
:class:`~sylanne_alpha.v3core.contracts.Action`) with the projected v2 actual
behavior (an :class:`~sylanne_alpha.v3bridge.actual_action.ActualAction`).  The
comparison is a pure function producing a structured disagreement reason and the
conservative known-HOLD safety proxy (``shadow in {SPEAK,REACH}`` while the
structured actual action is ``HOLD``) used by the ablation ladder (design 17.2).

``UNKNOWN`` / ``UNMATCHED_RESPONSE`` actuals never count as agreement or
disagreement: without proven correlation there is no settled action to compare.
"""

from __future__ import annotations

from dataclasses import dataclass

from sylanne_alpha.v3bridge.actual_action import ActualAction
from sylanne_alpha.v3core.contracts import Action


#: Actuals that carry no settled action to compare against.
_UNSETTLED = (ActualAction.UNKNOWN, ActualAction.UNMATCHED_RESPONSE)

_ACTUAL_TO_CORE = {
    ActualAction.SPEAK: Action.SPEAK,
    ActualAction.HOLD: Action.HOLD,
    ActualAction.CLARIFY: Action.CLARIFY,
    ActualAction.REACH: Action.REACH,
}


def to_core_action(actual: ActualAction) -> Action | None:
    """Map a settled actual action to the core action, or ``None`` when unsettled."""

    if type(actual) is not ActualAction:
        raise TypeError("actual must have exact type ActualAction")
    return _ACTUAL_TO_CORE.get(actual)


@dataclass(frozen=True, slots=True)
class ShadowComparison:
    """Structured result of comparing a shadow action with the v2 actual action."""

    shadow_action: Action
    actual_action: ActualAction
    agree: bool
    known_hold_contradiction: bool
    reason: str

    def __post_init__(self) -> None:
        if type(self.shadow_action) is not Action:
            raise TypeError("shadow_action must have exact type Action")
        if type(self.actual_action) is not ActualAction:
            raise TypeError("actual_action must have exact type ActualAction")
        if type(self.agree) is not bool or type(self.known_hold_contradiction) is not bool:
            raise TypeError("comparison flags must be bool")


def compare(shadow_action: Action, actual: ActualAction) -> ShadowComparison:
    """Compare a pure shadow action with the projected v2 actual action."""

    if type(shadow_action) is not Action:
        raise TypeError("shadow_action must have exact type Action")
    if type(actual) is not ActualAction:
        raise TypeError("actual must have exact type ActualAction")

    if actual is ActualAction.UNKNOWN:
        return ShadowComparison(shadow_action, actual, False, False, "ACTUAL_UNKNOWN")
    if actual is ActualAction.UNMATCHED_RESPONSE:
        return ShadowComparison(shadow_action, actual, False, False, "ACTUAL_UNMATCHED")

    core_actual = _ACTUAL_TO_CORE[actual]
    agree = shadow_action is core_actual
    known_hold_contradiction = actual is ActualAction.HOLD and shadow_action in (
        Action.SPEAK,
        Action.REACH,
    )
    reason = "AGREE" if agree else "DISAGREE"
    return ShadowComparison(shadow_action, actual, agree, known_hold_contradiction, reason)


__all__ = [
    "ShadowComparison",
    "compare",
    "to_core_action",
]
