"""Project already-authorized v2 memory facts into an immutable MemoryView.

This adapter consumes only the frozen ``V2TurnObservationSnapshotV1`` fact DTO.
It holds no host handle and imports nothing capable of I/O, so it is structurally
unable to reach a database, recall, an LLM, a callback, or a live domain.  When
the snapshot carries no authorized memory facts it returns the empty view.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from sylanne_alpha.v2core.shadow_snapshot import FACT_PRIVACY_SCOPE_VALUES, V2TurnObservationSnapshotV1
from sylanne_alpha.v3core.canonical import assert_exact_type

_MEMORY_FIELDS = ("relevance", "confidence", "temperature", "age_seconds")


@dataclass(frozen=True, slots=True)
class MemoryView:
    """Immutable projection of authorized person/session-scoped memory facts."""

    relevance: float | None
    confidence: float | None
    temperature: float | None
    age_seconds: float | None
    valid_mask: int
    privacy_scope: str

    def __post_init__(self) -> None:
        for name in _MEMORY_FIELDS:
            value = getattr(self, name)
            if value is not None:
                assert_exact_type(value, float, name)
                if not isfinite(value):
                    raise ValueError(f"{name} must be finite")
        assert_exact_type(self.valid_mask, int, "valid_mask")
        values = tuple(getattr(self, name) for name in _MEMORY_FIELDS)
        if not 0 <= self.valid_mask < (1 << len(values)):
            raise ValueError("valid_mask must be a 4-bit mask")
        expected = sum(1 << index for index, value in enumerate(values) if value is not None)
        if self.valid_mask != expected:
            raise ValueError("memory values and valid mask disagree")
        assert_exact_type(self.privacy_scope, str, "privacy_scope")
        if self.privacy_scope not in FACT_PRIVACY_SCOPE_VALUES:
            raise ValueError("privacy_scope is not a declared token")
        if self.valid_mask == 0 and self.privacy_scope != "NONE":
            raise ValueError("an empty MemoryView cannot claim a privacy scope")
        if self.valid_mask != 0 and self.privacy_scope == "NONE":
            raise ValueError("a populated MemoryView requires a privacy scope")


MEMORY_VIEW_EMPTY = MemoryView(
    relevance=None,
    confidence=None,
    temperature=None,
    age_seconds=None,
    valid_mask=0,
    privacy_scope="NONE",
)


def build_memory_view(snapshot: V2TurnObservationSnapshotV1) -> MemoryView:
    """Copy authorized memory facts from the frozen snapshot; never fabricate."""

    if type(snapshot) is not V2TurnObservationSnapshotV1:
        raise TypeError("snapshot must have exact type V2TurnObservationSnapshotV1")
    if snapshot.memory_valid_mask == 0:
        return MEMORY_VIEW_EMPTY
    return MemoryView(
        relevance=snapshot.memory_relevance,
        confidence=snapshot.memory_confidence,
        temperature=snapshot.memory_temperature,
        age_seconds=snapshot.memory_age_seconds,
        valid_mask=snapshot.memory_valid_mask,
        privacy_scope=snapshot.memory_privacy_scope,
    )


__all__ = ["MEMORY_VIEW_EMPTY", "MemoryView", "build_memory_view"]
