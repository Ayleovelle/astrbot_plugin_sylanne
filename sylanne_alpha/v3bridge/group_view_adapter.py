"""Project already-authorized v2 group facts into an immutable GroupView.

The bridge decides the cross-group privacy question upstream; this adapter only
enforces it structurally.  It consumes the frozen ``V2TurnObservationSnapshotV1``
fact DTO and a plain ``cross_group_allowed`` flag, holds no host handle, and
imports nothing capable of I/O.  When cross-group facts are present but not
allowed, the view comes back invalid rather than being fabricated.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from sylanne_alpha.v2core.shadow_snapshot import FACT_PRIVACY_SCOPE_VALUES, V2TurnObservationSnapshotV1
from sylanne_alpha.v3core.canonical import assert_exact_type

_GROUP_FIELDS = ("familiarity", "engagement", "tension", "activity")


@dataclass(frozen=True, slots=True)
class GroupView:
    """Immutable projection of authorized group-scoped facts."""

    familiarity: float | None
    engagement: float | None
    tension: float | None
    activity: float | None
    valid_mask: int
    privacy_scope: str

    def __post_init__(self) -> None:
        for name in _GROUP_FIELDS:
            value = getattr(self, name)
            if value is not None:
                assert_exact_type(value, float, name)
                if not isfinite(value):
                    raise ValueError(f"{name} must be finite")
        assert_exact_type(self.valid_mask, int, "valid_mask")
        values = tuple(getattr(self, name) for name in _GROUP_FIELDS)
        if not 0 <= self.valid_mask < (1 << len(values)):
            raise ValueError("valid_mask must be a 4-bit mask")
        expected = sum(1 << index for index, value in enumerate(values) if value is not None)
        if self.valid_mask != expected:
            raise ValueError("group values and valid mask disagree")
        assert_exact_type(self.privacy_scope, str, "privacy_scope")
        if self.privacy_scope not in FACT_PRIVACY_SCOPE_VALUES:
            raise ValueError("privacy_scope is not a declared token")
        if self.valid_mask == 0 and self.privacy_scope != "NONE":
            raise ValueError("an empty GroupView cannot claim a privacy scope")
        if self.valid_mask != 0 and self.privacy_scope == "NONE":
            raise ValueError("a populated GroupView requires a privacy scope")


GROUP_VIEW_EMPTY = GroupView(
    familiarity=None,
    engagement=None,
    tension=None,
    activity=None,
    valid_mask=0,
    privacy_scope="NONE",
)


def build_group_view(
    snapshot: V2TurnObservationSnapshotV1,
    *,
    cross_group_allowed: bool,
) -> GroupView:
    """Copy authorized group facts, clearing cross-group facts when disallowed."""

    if type(snapshot) is not V2TurnObservationSnapshotV1:
        raise TypeError("snapshot must have exact type V2TurnObservationSnapshotV1")
    if type(cross_group_allowed) is not bool:
        raise TypeError("cross_group_allowed must have exact type bool")
    if snapshot.group_valid_mask == 0:
        return GROUP_VIEW_EMPTY
    if snapshot.group_privacy_scope == "CROSS_GROUP" and not cross_group_allowed:
        return GROUP_VIEW_EMPTY
    return GroupView(
        familiarity=snapshot.group_familiarity,
        engagement=snapshot.group_engagement,
        tension=snapshot.group_tension,
        activity=snapshot.group_activity,
        valid_mask=snapshot.group_valid_mask,
        privacy_scope=snapshot.group_privacy_scope,
    )


__all__ = ["GROUP_VIEW_EMPTY", "GroupView", "build_group_view"]
