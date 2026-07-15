"""Minimal frozen state contracts for the first v3 implementation gate."""

from __future__ import annotations

from dataclasses import dataclass

from ..canonical import assert_exact_type, assert_valid_dto
from ..contracts import Action, SessionRef, TurnSequence


@dataclass(frozen=True, slots=True)
class PendingOutcome:
    origin_turn_id: str
    sequence: TurnSequence
    action: Action

    def __post_init__(self) -> None:
        assert_exact_type(self.origin_turn_id, str, "origin_turn_id")
        assert_exact_type(self.sequence, TurnSequence, "sequence")
        assert_exact_type(self.action, Action, "action")
        assert_valid_dto(self)
        if not self.origin_turn_id:
            raise ValueError("origin_turn_id must not be empty")


@dataclass(frozen=True, slots=True)
class V3State:
    session_ref: SessionRef
    revision: int = 0
    pending_outcome: PendingOutcome | None = None
    rho_hold: float = 0.0
    rho_reach: float = 0.0

    def __post_init__(self) -> None:
        assert_exact_type(self.session_ref, SessionRef, "session_ref")
        assert_exact_type(self.revision, int, "revision")
        assert_exact_type(self.pending_outcome, (PendingOutcome, type(None)), "pending_outcome")
        assert_exact_type(self.rho_hold, float, "rho_hold")
        assert_exact_type(self.rho_reach, float, "rho_reach")
        assert_valid_dto(self)
        if self.revision < 0:
            raise ValueError("revision must be non-negative")
        if not 0.0 <= self.rho_hold <= 1.0 or not 0.0 <= self.rho_reach <= 1.0:
            raise ValueError("autonomous refractory values must be in [0,1]")
