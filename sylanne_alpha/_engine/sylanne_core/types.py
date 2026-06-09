"""Type definitions for Sylanne-Core SDK output.

All public API methods return typed dicts defined here. The Surface type
is the primary output of engine.process() and engine.tick().

Type hierarchy::

    Surface
    ├── state: AffectiveState (8 subsystems + needs)
    ├── personality: PersonalityState (deep 5D + surface 6D)
    ├── decision: Decision (action + confidence + urgency)
    ├── guard: Guard (allowed + constraints)
    ├── dynamics: Dynamics (affect/moral/uncertainty/relational_time)
    └── debug: dict | None (pipeline internals, if diagnostics=True)
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

EngineStatus = Literal["init", "running", "degraded", "closed"]


class RhythmState(TypedDict):
    beat: float
    stability: float
    strain: float


class ConnectionState(TypedDict):
    warmth: float
    circulation: float
    memory_flow: float


class AdaptationState(TypedDict):
    plasticity: float
    sensitivity: float
    repetition: int
    threshold_drift: float


class ResponsivenessState(TypedDict):
    readiness: float
    fatigue: float
    trained_reach: float


class ValenceState(TypedDict):
    warmth: float
    volatility: float
    recovery_heat: float


class DamageState(TypedDict):
    open: float
    accumulated: float
    sensitivity: float
    recovery: float


class BoundaryState(TypedDict):
    pressure: float
    autonomy: float
    interruption_budget: float
    cooldown: float
    paused: bool


class CapacityState(TypedDict):
    load: float
    exhaustion: float
    recovery_debt: float


class NeedsState(TypedDict):
    expression: float
    quiet: float
    recovery: float
    contact: float


class AffectiveState(TypedDict):
    rhythm: RhythmState
    connection: ConnectionState
    adaptation: AdaptationState
    responsiveness: ResponsivenessState
    valence: ValenceState
    damage: DamageState
    boundary: BoundaryState
    capacity: CapacityState
    needs: NeedsState


class DeepPersonality(TypedDict):
    expression_drive: float
    perception_acuity: float
    boundary_permeability: float
    inner_coherence: float
    relational_gravity: float


class SurfacePersonality(TypedDict):
    warmth_bias: float
    directness: float
    curiosity: float
    patience: float
    intimacy_pull: float
    autonomy_guard: float


class PersonalityState(TypedDict):
    schema_version: str
    deep: DeepPersonality
    surface: SurfacePersonality


class Decision(TypedDict):
    action: str
    reason: str
    reason_code: str
    confidence: float
    urgency: float


class Guard(TypedDict):
    allowed: bool
    reason: str
    risk_score: float
    constraints: list[str]


class AffectDynamics(TypedDict):
    recovery_drive: float
    expression_drive: float
    quiet_drive: float


class MoralState(TypedDict):
    state: str
    events: int


class UncertaintyState(TypedDict):
    claim_caution: float
    events: int


class RelationalTime(TypedDict):
    interval_seconds: float
    total_duration: float
    phase: str


class HotPoolDiagnostics(TypedDict):
    temperature: float
    volume: float
    pressure: float
    material_count: int
    cascade_active: bool
    cascade_intensity: float
    sensitivity_multiplier: float
    in_recovery: bool
    collapse_count: int


class Dynamics(TypedDict):
    affect: AffectDynamics
    moral_state: MoralState
    uncertainty: UncertaintyState
    relational_time: RelationalTime
    hot_pool: HotPoolDiagnostics


class PADOutput(TypedDict):
    """PAD dimensional emotion output (Mehrabian & Russell 1974).

    Maps the internal N-dim affective state to the standard 3D PAD space
    plus a categorical label and confidence score.
    """

    valence: float  # [-1, 1] — hedonic tone (Pleasure axis)
    arousal: float  # [0, 1] — physiological activation
    dominance: float  # [0, 1] — perceived control
    label: str  # categorical emotion label (e.g. "joy", "anger", "neutral")
    confidence: float  # [0, 1] — classification confidence


class HealthStatus(TypedDict):
    status: EngineStatus
    active_sessions: int
    data_dir_exists: bool
    llm_configured: bool
    embedding_configured: bool


class Surface(TypedDict):
    schema_version: str
    session_id: str
    turns: int
    timestamp: float
    state: AffectiveState
    personality: PersonalityState
    decision: Decision
    guard: Guard
    pipeline: dict[str, Any]
    dynamics: Dynamics
    pad: PADOutput
    debug: dict[str, Any] | None
