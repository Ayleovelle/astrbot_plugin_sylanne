"""Frozen contracts shared by deterministic v3 core components."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .canonical import assert_exact_type, assert_valid_dto


class Action(Enum):
    SPEAK = "SPEAK"
    HOLD = "HOLD"
    CLARIFY = "CLARIFY"
    REACH = "REACH"


class TurnContextClass(Enum):
    ADDRESSED = "ADDRESSED"
    AMBIENT = "AMBIENT"
    PROACTIVE = "PROACTIVE"
    IDLE = "IDLE"


@dataclass(frozen=True, slots=True)
class SessionRef:
    """Bridge-owned opaque partition identity with no raw host identifier."""

    key_id: str
    session_digest: bytes
    session_generation: int

    def __post_init__(self) -> None:
        assert_exact_type(self.key_id, str, "key_id")
        assert_exact_type(self.session_digest, bytes, "session_digest")
        assert_exact_type(self.session_generation, int, "session_generation")
        assert_valid_dto(self)
        if not self.key_id:
            raise ValueError("key_id must not be empty")
        if len(self.session_digest) != 32:
            raise ValueError("session_digest must be a full 256-bit digest")
        if self.session_generation < 0:
            raise ValueError("session_generation must be non-negative")


@dataclass(frozen=True, order=True, slots=True)
class TurnSequence:
    """A sequence token ordered only inside its bridge-owned SessionRef partition."""

    writer_epoch: int
    local_sequence: int

    def __post_init__(self) -> None:
        assert_exact_type(self.writer_epoch, int, "writer_epoch")
        assert_exact_type(self.local_sequence, int, "local_sequence")
        assert_valid_dto(self)
        if self.writer_epoch < 0 or self.local_sequence < 1:
            raise ValueError("turn sequence values are non-negative and one-based")


@dataclass(frozen=True, slots=True)
class TurnKey:
    plugin_instance_id: str
    session_ref: SessionRef
    bridge_request_nonce: str
    request_attempt: int

    def __post_init__(self) -> None:
        assert_exact_type(self.plugin_instance_id, str, "plugin_instance_id")
        assert_exact_type(self.session_ref, SessionRef, "session_ref")
        assert_exact_type(self.bridge_request_nonce, str, "bridge_request_nonce")
        assert_exact_type(self.request_attempt, int, "request_attempt")
        assert_valid_dto(self)
        if not self.plugin_instance_id or not self.bridge_request_nonce:
            raise ValueError("turn key identifiers must not be empty")
        if self.request_attempt < 0:
            raise ValueError("request_attempt must be non-negative")


@dataclass(frozen=True, slots=True)
class ComputeProfile:
    profile_id: str
    snn_enabled: bool
    ticks: int
    stdp_enabled: bool
    reuse_last_summary: bool
    math_backend: str
    formula_version: str
    model_version: str

    def __post_init__(self) -> None:
        assert_exact_type(self.profile_id, str, "profile_id")
        assert_exact_type(self.snn_enabled, bool, "snn_enabled")
        assert_exact_type(self.ticks, int, "ticks")
        assert_exact_type(self.stdp_enabled, bool, "stdp_enabled")
        assert_exact_type(self.reuse_last_summary, bool, "reuse_last_summary")
        assert_exact_type(self.math_backend, str, "math_backend")
        assert_exact_type(self.formula_version, str, "formula_version")
        assert_exact_type(self.model_version, str, "model_version")
        assert_valid_dto(self)
        if self.ticks < 0:
            raise ValueError("ticks must be non-negative")
        if not all((self.profile_id, self.math_backend, self.formula_version, self.model_version)):
            raise ValueError("profile identifiers must not be empty")


@dataclass(frozen=True, slots=True)
class TurnEnvelope:
    """Pure deterministic turn input; deadlines and host objects stay in v3bridge."""

    turn_key: TurnKey
    turn_id: str
    sequence: TurnSequence
    compute_profile: ComputeProfile
    deterministic_seed: bytes
    observation: object
    context: TurnContextClass

    def __post_init__(self) -> None:
        assert_exact_type(self.turn_key, TurnKey, "turn_key")
        assert_exact_type(self.turn_id, str, "turn_id")
        assert_exact_type(self.sequence, TurnSequence, "sequence")
        assert_exact_type(self.compute_profile, ComputeProfile, "compute_profile")
        assert_exact_type(self.deterministic_seed, bytes, "deterministic_seed")
        assert_exact_type(self.context, TurnContextClass, "context")
        assert_valid_dto(self)
        if not self.turn_id or not self.deterministic_seed:
            raise ValueError("turn_id and deterministic_seed must not be empty")


@dataclass(frozen=True, slots=True)
class CoreInvocation:
    """Pure core invocation containing only declared immutable DTOs."""

    envelope: TurnEnvelope
    base_state: object
    projected_actual_outcome: object | None

    def __post_init__(self) -> None:
        assert_exact_type(self.envelope, TurnEnvelope, "envelope")
        assert_valid_dto(self)
