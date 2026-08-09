"""Pure projection from structured v2 terminal evidence to actual action."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from sylanne_alpha.v2core.shadow_snapshot import V2ResponseCandidateV1


V2_ACTUAL_ACTION_PROJECTION_REVISION_V1 = "sylanne.v2.actual-action-projection.v1"


class ActualAction(Enum):
    SPEAK = "SPEAK"
    HOLD = "HOLD"
    CLARIFY = "CLARIFY"
    REACH = "REACH"
    UNKNOWN = "UNKNOWN"
    UNMATCHED_RESPONSE = "UNMATCHED_RESPONSE"


@dataclass(frozen=True, slots=True)
class V2ActualActionProjectionV1:
    """Versioned pure callable over structured v2 terminal evidence."""

    revision: str = field(default=V2_ACTUAL_ACTION_PROJECTION_REVISION_V1, init=False)

    def __call__(self, candidate: V2ResponseCandidateV1) -> ActualAction:
        if type(candidate) is not V2ResponseCandidateV1:
            raise TypeError("candidate must have exact type V2ResponseCandidateV1")
        if not candidate.correlation_proven or candidate.duplicate_terminal_claim:
            return ActualAction.UNMATCHED_RESPONSE
        if candidate.route_kind == "SILENT":
            return ActualAction.HOLD
        if candidate.route_kind == "SEGMENTED_TEXT":
            if candidate.all_segments_succeeded is True:
                return ActualAction.SPEAK
            return ActualAction.UNKNOWN
        if candidate.route_kind == "PROACTIVE":
            if candidate.proactive_dispatched is True:
                return ActualAction.REACH
            return ActualAction.UNKNOWN
        return ActualAction.UNKNOWN


project_actual_action = V2ActualActionProjectionV1()


__all__ = [
    "ActualAction",
    "V2ActualActionProjectionV1",
    "V2_ACTUAL_ACTION_PROJECTION_REVISION_V1",
    "project_actual_action",
]
