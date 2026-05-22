from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

SYLANNE_BODY_ONTOLOGY_NAME = "Sylanne — Sovereign Yearning Life-Architecture: Nonhuman Relational Body"


def _frozen_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))


@dataclass(frozen=True)
class BodyRequest:
    user_text: str
    conversation_id: str | None = None
    user_id: str | None = None
    timestamp: str | None = None
    legacy_context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "legacy_context", _frozen_mapping(self.legacy_context))


@dataclass(frozen=True)
class BodyResponse:
    assistant_text: str
    conversation_id: str | None = None
    user_id: str | None = None
    timestamp: str | None = None
    legacy_context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "legacy_context", _frozen_mapping(self.legacy_context))


@dataclass(frozen=True)
class UserSovereigntyState:
    user_can_refuse: bool = True
    user_can_pause: bool = True
    user_can_leave: bool = True
    user_can_reset_boundaries: bool = True


@dataclass(frozen=True)
class BodyTrace:
    source: str
    organ_role: str
    intensity: float
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.source or "").strip():
            raise ValueError("BodyTrace.source is required")
        if not str(self.organ_role or "").strip():
            raise ValueError("BodyTrace.organ_role is required")
        object.__setattr__(self, "intensity", max(0.0, min(1.0, float(self.intensity))))
        object.__setattr__(self, "notes", tuple(str(note) for note in self.notes))


@dataclass(frozen=True)
class BodyState:
    ontology_name: str = SYLANNE_BODY_ONTOLOGY_NAME
    sovereignty: UserSovereigntyState = field(default_factory=UserSovereigntyState)
    traces: tuple[BodyTrace, ...] = ()
    prompt_commitments: tuple[str, ...] = ()


@dataclass(frozen=True)
class BodyRuntimeRequestResult:
    state: BodyState
    prompt_segment: str
    traces: tuple[BodyTrace, ...]


@dataclass(frozen=True)
class BodyRuntimeResponseResult:
    state: BodyState
    traces: tuple[BodyTrace, ...]
    violations: tuple[str, ...] = ()
