"""Minimal frozen state contracts for the first v3 implementation gate."""

from __future__ import annotations

from dataclasses import dataclass

from ..canonical import assert_valid_dto, declared_dto
from ..contracts import Action, SessionRef, TurnSequence


@declared_dto
@dataclass(frozen=True, slots=True)
class PendingOutcome:
    origin_turn_id: str
    sequence: TurnSequence
    action: Action

    def __post_init__(self) -> None:
        assert_valid_dto(self)
        if not self.origin_turn_id:
            raise ValueError("origin_turn_id must not be empty")


@declared_dto
@dataclass(frozen=True, slots=True)
class V3State:
    session_ref: SessionRef
    revision: int = 0
    pending_outcome: PendingOutcome | None = None
    rho_hold: float = 0.0
    rho_reach: float = 0.0

    def __post_init__(self) -> None:
        assert_valid_dto(self)
        if self.revision < 0:
            raise ValueError("revision must be non-negative")
        if not 0.0 <= self.rho_hold <= 1.0 or not 0.0 <= self.rho_reach <= 1.0:
            raise ValueError("autonomous refractory values must be in [0,1]")
