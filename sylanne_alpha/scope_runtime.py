"""Exact, fail-closed ownership for mutable Bot/Persona/Session runtime state.

The scope resolver freezes a :class:`~sylanne_alpha.scope_contracts.SessionScope`
before any private runtime work starts.  This module deliberately accepts only that
frozen scope; it never tries to recover a scope from a raw transport/session value.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
import inspect
import math
import time
from typing import Any

from sylanne_alpha.scope_contracts import (
    AuthenticatedSubject,
    PersonaRevisionRef,
    RelationScope,
    ResolvedScope,
    ResolvedTransportScope,
    SessionScope,
)
from sylanne_alpha.scope_repository import (
    RelationScopedPersistenceGateway,
    ScopeRepository,
    ScopedPersistenceGateway,
)
from sylanne_alpha.session_state_store import SessionStateStore


class ScopeMismatch(RuntimeError):
    """Raised when an operation does not name one exact live scoped runtime."""


class ScopeUnavailable(ScopeMismatch):
    """Raised when an active path has no verified frozen private scope."""


PersonaKey = tuple[str, str, int]
SessionKey = tuple[str, str, int, str, int]
RelationKey = tuple[str, str, int, str, int]
TransportKey = tuple[str, int, str, int]
TransportIdentityKey = tuple[str, int, str]
RequestViewKey = tuple[str, str, int, str, int, int]
_MAX_REQUEST_VIEWS_PER_SESSION = 8
_MAX_REQUEST_VIEWS_GLOBAL = 1024


def _require_scope(scope: object) -> SessionScope:
    if type(scope) is not SessionScope:
        raise ScopeMismatch("a frozen SessionScope is required")
    return scope


def _persona_key(scope: SessionScope) -> PersonaKey:
    return (
        scope.bot_ref.token,
        scope.persona_ref.token,
        scope.persona_ref.lifecycle_generation,
    )


def _session_key(scope: SessionScope) -> SessionKey:
    return (
        scope.bot_ref.token,
        scope.persona_ref.token,
        scope.persona_ref.lifecycle_generation,
        scope.storage_token,
        scope.scope_generation,
    )


def _relation_key(scope: RelationScope) -> RelationKey:
    return (
        scope.bot_ref.token,
        scope.persona_ref.token,
        scope.persona_ref.lifecycle_generation,
        scope.relation_ref.token,
        scope.relation_generation,
    )


def _transport_key(transport: ResolvedTransportScope) -> TransportKey:
    if (
        type(transport) is not ResolvedTransportScope
        or transport.private_scope_enabled is not True
        or transport.bot_ref is None
        or transport.session_ref is None
    ):
        raise ScopeMismatch("an authenticated transport scope is required")
    return (
        transport.bot_ref.token,
        transport.bot_ref.generation,
        transport.session_ref.token,
        transport.session_ref.generation,
    )


def _transport_identity_for_scope(scope: SessionScope) -> TransportIdentityKey:
    return (
        scope.bot_ref.token,
        scope.bot_ref.generation,
        scope.session_ref.token,
    )


RELATIONSHIP_STAGES = {
    "infant": (0.0, 3.0),
    "young": (3.0, 14.0),
    "mature": (14.0, 90.0),
    "deep": (90.0, float("inf")),
}


def _finite_float(value: object, *, name: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def get_relationship_stage(first_interaction: float, *, now: float | None = None) -> str:
    """Return the age stage for one relation-owned first interaction timestamp."""

    first = _finite_float(first_interaction, name="first_interaction")
    current = time.time() if now is None else _finite_float(now, name="now")
    age_days = max(0.0, (current - first) / 86_400)
    for stage, (low, high) in RELATIONSHIP_STAGES.items():
        if low <= age_days < high:
            return stage
    return "deep"


@dataclass(frozen=True, slots=True)
class FirstImpression:
    """An immutable first-conversation anchor owned by one RelationRuntime."""

    valence: float
    topic_type: str
    user_style: str
    quality: float
    timestamp: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "valence",
            max(-1.0, min(1.0, _finite_float(self.valence, name="valence"))),
        )
        if type(self.topic_type) is not str or not self.topic_type:
            raise ValueError("topic_type must be a non-empty str")
        if type(self.user_style) is not str or not self.user_style:
            raise ValueError("user_style must be a non-empty str")
        object.__setattr__(
            self,
            "quality",
            max(0.0, min(1.0, _finite_float(self.quality, name="quality"))),
        )
        object.__setattr__(self, "timestamp", _finite_float(self.timestamp, name="timestamp"))

    def anchor_weight(self, relationship_age_days: float) -> float:
        age = _finite_float(relationship_age_days, name="relationship_age_days")
        if age < 7:
            return 1.0
        if age < 30:
            return 1.0 - ((age - 7) / 23) * 0.75
        return 0.15 + self.quality * 0.1

    def to_dict(self) -> dict[str, object]:
        return {
            "valence": self.valence,
            "topic_type": self.topic_type,
            "user_style": self.user_style,
            "quality": self.quality,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: object) -> FirstImpression | None:
        if type(data) is not dict:
            return None
        try:
            return cls(
                valence=data["valence"],
                topic_type=data["topic_type"],
                user_style=data["user_style"],
                quality=data["quality"],
                timestamp=data["timestamp"],
            )
        except (KeyError, TypeError, ValueError):
            return None


class RitualRegistry:
    """One relation-local ritual registry, addressed solely by pattern name."""

    def __init__(self) -> None:
        self._rituals: dict[str, dict[str, object]] = {}
        self._observations: dict[str, list[float]] = {}

    @staticmethod
    def _pattern(pattern: object) -> str:
        if type(pattern) is not str or not pattern:
            raise ValueError("pattern must be a non-empty str")
        return pattern

    @staticmethod
    def _hour(hour: object) -> int:
        if type(hour) is not int or not 0 <= hour <= 23:
            raise ValueError("hour must be an int from 0 to 23")
        return hour

    def observe_pattern(
        self,
        hour: int,
        pattern: str,
        *,
        observed_at: float | None = None,
    ) -> dict[str, object] | None:
        name = self._pattern(pattern)
        current_hour = self._hour(hour)
        timestamp = time.time() if observed_at is None else _finite_float(observed_at, name="observed_at")
        observations = self._observations.setdefault(name, [])
        observations.append(timestamp)
        if len(observations) >= 3:
            self._rituals[name] = {
                "hour_start": current_hour,
                "hour_end": (current_hour + 1) % 24,
                "pattern": name,
            }
            self._observations[name] = observations[-5:]
        return self.get_ritual(name)

    def get_ritual(self, pattern: str) -> dict[str, object] | None:
        name = self._pattern(pattern)
        ritual = self._rituals.get(name)
        return None if ritual is None else dict(ritual)

    def get_active_rituals(self) -> list[dict[str, object]]:
        return [dict(self._rituals[name]) for name in sorted(self._rituals)]

    def to_dict(self) -> dict[str, object]:
        return {
            "rituals": {name: dict(value) for name, value in self._rituals.items()},
            "observations": {name: list(value) for name, value in self._observations.items()},
        }

    @classmethod
    def from_dict(cls, data: object) -> RitualRegistry:
        registry = cls()
        if type(data) is not dict:
            return registry
        rituals = data.get("rituals")
        if type(rituals) is dict:
            for key, value in rituals.items():
                if type(key) is not str or type(value) is not dict:
                    continue
                try:
                    hour_start = cls._hour(value.get("hour_start"))
                    hour_end = cls._hour(value.get("hour_end"))
                    pattern = cls._pattern(value.get("pattern"))
                except ValueError:
                    continue
                if pattern == key:
                    registry._rituals[pattern] = {
                        "hour_start": hour_start,
                        "hour_end": hour_end,
                        "pattern": pattern,
                    }
        observations = data.get("observations")
        if type(observations) is dict:
            for key, values in observations.items():
                if type(key) is not str or type(values) is not list:
                    continue
                restored: list[float] = []
                for value in values:
                    try:
                        restored.append(_finite_float(value, name="observation"))
                    except ValueError:
                        continue
                if restored:
                    registry._observations[key] = restored[-5:]
        return registry


@dataclass(slots=True)
class RelationRuntime:
    """Mutable relationship state belonging to exactly one Persona + relation.

    The three locally-owned components are written through one immutable relation
    gateway.  No method accepts a raw sender, platform, or session identifier.
    """

    scope: RelationScope
    persistence: RelationScopedPersistenceGateway | None = None
    profile_generation: int = 0
    shelf_generation: int = 0
    relationship_generation: int = 0
    relationship_age_generation: int = 0
    first_impression_generation: int = 0
    ritual_generation: int = 0
    ritual_registry: RitualRegistry = field(default_factory=RitualRegistry)
    _first_interaction: float | None = field(default=None, init=False, repr=False)
    _first_impression: FirstImpression | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self.scope) is not RelationScope:
            raise ScopeMismatch("an exact RelationScope is required")
        if self.persistence is not None and (
            type(self.persistence) is not RelationScopedPersistenceGateway or self.persistence.scope != self.scope
        ):
            raise ScopeMismatch("relation persistence does not match relation scope")
        if type(self.ritual_registry) is not RitualRegistry:
            raise ValueError("ritual_registry must be a RitualRegistry")
        for value, name in (
            (self.profile_generation, "profile_generation"),
            (self.shelf_generation, "shelf_generation"),
            (self.relationship_generation, "relationship_generation"),
            (self.relationship_age_generation, "relationship_age_generation"),
            (self.first_impression_generation, "first_impression_generation"),
            (self.ritual_generation, "ritual_generation"),
        ):
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a non-negative int")
        if self.persistence is not None:
            self._restore_owned_state()

    @property
    def gateway(self) -> RelationScopedPersistenceGateway | None:
        """Compatibility spelling for the immutable relation persistence capability."""

        return self.persistence

    def _restore_owned_state(self) -> None:
        persistence = self.persistence
        if persistence is None:
            return
        age = persistence.load("relationship-age")
        if age is not None:
            self.relationship_age_generation = age.generation
            if type(age.payload) is dict:
                try:
                    self._first_interaction = _finite_float(
                        age.payload.get("first_interaction"),
                        name="first_interaction",
                    )
                except ValueError:
                    self._first_interaction = None
        impression = persistence.load("first-impression")
        if impression is not None:
            self.first_impression_generation = impression.generation
            self._first_impression = FirstImpression.from_dict(impression.payload)
        ritual = persistence.load("ritual")
        if ritual is not None:
            self.ritual_generation = ritual.generation
            self.ritual_registry = RitualRegistry.from_dict(ritual.payload)

    def _save(
        self,
        component: str,
        *,
        expected_generation: int,
        payload: dict[str, object],
    ) -> int:
        persistence = self.persistence
        if persistence is None:
            return expected_generation + 1
        return persistence.save(
            component,
            expected_generation=expected_generation,
            payload=payload,
        )

    def first_interaction_time(self) -> float | None:
        return self._first_interaction

    def record_first_interaction(self, timestamp: float) -> float:
        """Record the first interaction once; subsequent observations preserve it."""

        existing = self._first_interaction
        if existing is not None:
            return existing
        return self.set_first_interaction_time(timestamp)

    def ensure_first_interaction_time(self, *, now: float | None = None) -> float:
        existing = self._first_interaction
        if existing is not None:
            return existing
        return self.record_first_interaction(time.time() if now is None else now)

    def set_first_interaction_time(self, timestamp: float) -> float:
        value = _finite_float(timestamp, name="timestamp")
        generation = self._save(
            "relationship-age",
            expected_generation=self.relationship_age_generation,
            payload={"first_interaction": value},
        )
        self._first_interaction = value
        self.relationship_age_generation = generation
        return value

    def relationship_stage(self, *, now: float | None = None) -> str | None:
        first = self._first_interaction
        return None if first is None else get_relationship_stage(first, now=now)

    def accelerate_relationship(self, intensity: float, *, now: float | None = None) -> float:
        bounded = max(0.0, min(1.0, _finite_float(intensity, name="intensity")))
        first = self.ensure_first_interaction_time(now=now)
        floor = first - 30 * 86_400
        return self.set_first_interaction_time(max(floor, first - bounded * 24 * 3_600))

    def first_impression(self) -> FirstImpression | None:
        return self._first_impression

    def record_first_impression(
        self,
        *,
        valence: float,
        topic_type: str,
        user_style: str,
        quality: float,
        timestamp: float | None = None,
    ) -> FirstImpression:
        existing = self._first_impression
        if existing is not None:
            return existing
        impression = FirstImpression(
            valence=valence,
            topic_type=topic_type,
            user_style=user_style,
            quality=quality,
            timestamp=time.time() if timestamp is None else timestamp,
        )
        generation = self._save(
            "first-impression",
            expected_generation=self.first_impression_generation,
            payload=impression.to_dict(),
        )
        self._first_impression = impression
        self.first_impression_generation = generation
        return impression

    def observe_ritual(
        self,
        *,
        hour: int,
        pattern: str,
        observed_at: float | None = None,
    ) -> dict[str, object] | None:
        # Copy first so a failed CAS never mutates an already stale owner.
        next_registry = RitualRegistry.from_dict(self.ritual_registry.to_dict())
        ritual = next_registry.observe_pattern(
            hour,
            pattern,
            observed_at=observed_at,
        )
        generation = self._save(
            "ritual",
            expected_generation=self.ritual_generation,
            payload=next_registry.to_dict(),
        )
        self.ritual_registry = next_registry
        self.ritual_generation = generation
        return ritual

    def ritual(self, pattern: str) -> dict[str, object] | None:
        return self.ritual_registry.get_ritual(pattern)

    def flush(self) -> None:
        """Writes are eager; this is an explicit no-op handoff seam."""

    def active_rituals(self) -> tuple[dict[str, object], ...]:
        """Return detached relation hints for one request-bound scheduler."""

        return tuple(self.ritual_registry.get_active_rituals())


@dataclass(slots=True)
class PersonaRuntime:
    """All mutable owners shared by one Bot + Persona revision only."""

    persona_ref: PersonaRevisionRef
    store: SessionStateStore = field(default_factory=SessionStateStore)
    memory_factory: Callable[[SessionScope], object] = field(
        default=lambda _scope: object(),
        repr=False,
    )
    memory_systems: dict[str, object] = field(default_factory=dict)
    life_simulator: object | None = None
    rhythm_learner: object | None = None
    social_field: object | None = None
    proactive_scheduler: object | None = None
    proactive_scheduler_task: Any | None = field(default=None, repr=False)
    self_core: object | None = None
    autonomy_scheduler: object | None = None
    autonomy_scheduler_task: Any | None = field(default=None, repr=False)
    background_queue: object | None = None
    background_post_recovered_sessions: set[str] = field(default_factory=set)
    life_simulator_started: bool = False
    rhythm_learner_last_save_ts: float = 0.0
    rhythm_learner_dirty_in_flight: bool = False
    life_sim_last_save_ts: float = 0.0
    life_sim_dirty_in_flight: bool = False
    relation_runtimes: dict[RelationKey, RelationRuntime] = field(default_factory=dict)
    v2core_runtimes: dict[str, dict[str, Any]] = field(default_factory=dict)
    v2core_pending_saves: set[Any] = field(default_factory=set, repr=False)
    v2core_save_locks: dict[str, Any] = field(default_factory=dict, repr=False)
    session_background_tasks: dict[SessionKey, set[Any]] = field(
        default_factory=dict,
        repr=False,
    )
    relation_runtime_factory: Callable[[RelationScope, RelationScopedPersistenceGateway | None], RelationRuntime] = (
        field(
            default=lambda scope, persistence=None: RelationRuntime(
                scope=scope,
                persistence=persistence,
            ),
            repr=False,
        )
    )
    background_tasks: set[Any] = field(default_factory=set, repr=False)
    generation: int = 0

    def memory_system_for(self, scope: SessionScope) -> object:
        """Return a memory owner for this exact scope, never a fallback owner."""

        scope = _require_scope(scope)
        if scope.persona_ref != self.persona_ref:
            raise ScopeMismatch("memory scope does not belong to persona runtime")
        memory = self.memory_systems.get(scope.storage_token)
        if memory is None:
            memory = self.memory_factory(scope)
            self.memory_systems[scope.storage_token] = memory
        return memory

    def relation_for(
        self,
        scope: RelationScope,
        *,
        persistence: RelationScopedPersistenceGateway | None = None,
        factory: Callable[[RelationScope, RelationScopedPersistenceGateway | None], RelationRuntime] | None = None,
    ) -> RelationRuntime:
        """Return an exact authenticated relation owner for this Persona runtime."""

        if type(scope) is not RelationScope:
            raise ScopeMismatch("an authenticated RelationScope is required")
        if scope.persona_ref != self.persona_ref:
            raise ScopeMismatch("relation scope does not belong to persona runtime")
        if persistence is not None and (
            type(persistence) is not RelationScopedPersistenceGateway or persistence.scope != scope
        ):
            raise ScopeMismatch("relation persistence does not match relation scope")
        key = _relation_key(scope)
        runtime = self.relation_runtimes.get(key)
        if runtime is None:
            runtime = (
                self.relation_runtime_factory(scope, persistence) if factory is None else factory(scope, persistence)
            )
            if type(runtime) is not RelationRuntime or runtime.scope != scope or runtime.persistence != persistence:
                raise ScopeMismatch("relation runtime factory returned an invalid runtime")
            self.relation_runtimes[key] = runtime
        elif runtime.persistence != persistence:
            raise ScopeMismatch("relation runtime persistence does not match exact scope")
        return runtime


@dataclass(slots=True)
class ScopedSessionLifecycle:
    """Mutable lifecycle bookkeeping belonging to one exact Session owner."""

    proactive_scheduler_task: Any | None = None
    life_simulator_started: bool = False
    rhythm_learner_last_save_ts: float = 0.0
    rhythm_learner_dirty_in_flight: bool = False
    life_sim_last_save_ts: float = 0.0
    life_sim_dirty_in_flight: bool = False


@dataclass(frozen=True, slots=True)
class ScopedSessionRuntime:
    """Exact construction owner for one gateway-bound Session runtime.

    A bare registry-free/test runtime may contain only ``scope`` and ``store``.
    Production construction goes through :meth:`build`, which captures one
    immutable persistence gateway and constructs every Session-owned object
    before the runtime is published by :class:`ScopeRuntimeRegistry`.
    """

    scope: SessionScope
    store: SessionStateStore
    persistence: ScopedPersistenceGateway | None = None
    host_session: object | None = field(default=None, compare=False, repr=False)
    host: object | None = field(default=None, compare=False, repr=False)
    conversation_buffer: object | None = field(default=None, compare=False, repr=False)
    memory_facade: object | None = field(default=None, compare=False, repr=False)
    memory_system: object | None = field(default=None, compare=False, repr=False)
    background_queue: object | None = field(default=None, compare=False, repr=False)
    life_simulator: object | None = field(default=None, compare=False, repr=False)
    rhythm_learner: object | None = field(default=None, compare=False, repr=False)
    social_field: object | None = field(default=None, compare=False, repr=False)
    proactive_scheduler: object | None = field(default=None, compare=False, repr=False)
    v2_persistence: object | None = field(default=None, compare=False, repr=False)
    v3_shadow_state: object | None = field(default=None, compare=False, repr=False)
    lifecycle: ScopedSessionLifecycle = field(
        default_factory=ScopedSessionLifecycle,
        compare=False,
        repr=False,
    )
    _device_context_owner: object | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        if type(self.scope) is not SessionScope:
            raise ScopeMismatch("an exact SessionScope is required")
        if self.persistence is not None and (
            type(self.persistence) is not ScopedPersistenceGateway or self.persistence.scope != self.scope
        ):
            raise ScopeMismatch("session persistence does not match exact scope")
        if type(self.lifecycle) is not ScopedSessionLifecycle:
            raise ScopeMismatch("session lifecycle owner is invalid")
        if self.host_session is not None:
            if self.persistence is None:
                raise ScopeMismatch("gateway-bound host requires session persistence")
            if getattr(self.host_session, "gateway", None) is not self.persistence:
                raise ScopeMismatch("host session does not own the exact persistence gateway")
            if getattr(self.host_session, "host", None) is not self.host:
                raise ScopeMismatch("host session does not own the published host")
            if getattr(self.host_session, "memory", None) is not self.memory_facade:
                raise ScopeMismatch("host session does not own the published memory facade")
        for name in (
            "background_queue",
            "life_simulator",
            "rhythm_learner",
            "social_field",
            "proactive_scheduler",
            "v2_persistence",
            "v3_shadow_state",
        ):
            owner = getattr(self, name)
            if owner is not None and getattr(owner, "persistence", None) is not self.persistence:
                raise ScopeMismatch(
                    f"{name} does not own the exact persistence gateway"
                )

    @classmethod
    def build(
        cls,
        *,
        scope: SessionScope,
        store: SessionStateStore,
        persistence: ScopedPersistenceGateway,
        host_session_factory: Callable[[ScopedPersistenceGateway], object],
        memory_system_factory: Callable[[], object],
        conversation_factory: Callable[[dict[str, object]], object],
        background_queue_factory: Callable[[ScopedPersistenceGateway], object] | None = None,
        life_simulator_factory: Callable[[ScopedPersistenceGateway], object] | None = None,
        rhythm_learner_factory: Callable[[ScopedPersistenceGateway], object] | None = None,
        social_field_factory: Callable[[ScopedPersistenceGateway], object] | None = None,
        proactive_scheduler_factory: Callable[[ScopedPersistenceGateway], object] | None = None,
        v2_persistence_factory: Callable[[ScopedPersistenceGateway], object] | None = None,
        v3_shadow_state_factory: Callable[[ScopedPersistenceGateway], object] | None = None,
    ) -> ScopedSessionRuntime:
        """Construct and restore every Session owner before registry publication."""

        scope = _require_scope(scope)
        if type(persistence) is not ScopedPersistenceGateway or persistence.scope != scope:
            raise ScopeMismatch("session persistence does not match exact scope")
        for factory, name in (
            (host_session_factory, "host_session_factory"),
            (memory_system_factory, "memory_system_factory"),
            (conversation_factory, "conversation_factory"),
        ):
            if not callable(factory):
                raise ValueError(f"{name} must be callable")

        host_session = host_session_factory(persistence)
        host = getattr(host_session, "host", None)
        memory_facade = getattr(host_session, "memory", None)
        if (
            getattr(host_session, "gateway", None) is not persistence
            or host is None
            or memory_facade is None
        ):
            raise ScopeMismatch("host session factory returned an invalid scoped owner")

        memory_system = memory_system_factory()
        state = getattr(host_session, "state", None)
        restore_memory = getattr(state, "restore_memory_into", None)
        if not callable(restore_memory):
            raise ScopeMismatch("host session has no scoped memory restore seam")
        restore_memory(memory_system)

        buffer_data = host_session.load_buffer()
        if buffer_data is None:
            from sylanne_alpha.memory_system import ConversationBuffer

            conversation_buffer = ConversationBuffer(session_key=scope.storage_token)
        else:
            conversation_buffer = conversation_factory(buffer_data)
        if getattr(conversation_buffer, "session_key", None) != scope.storage_token:
            raise ScopeMismatch("conversation buffer does not match exact scope")

        def construct(
            factory: Callable[[ScopedPersistenceGateway], object] | None,
        ) -> object | None:
            return None if factory is None else factory(persistence)

        background_queue = construct(background_queue_factory)
        recover_queue = getattr(background_queue, "recover_before_publication", None)
        if callable(recover_queue):
            recover_queue()

        return cls(
            scope=scope,
            store=store,
            persistence=persistence,
            host_session=host_session,
            host=host,
            conversation_buffer=conversation_buffer,
            memory_facade=memory_facade,
            memory_system=memory_system,
            background_queue=background_queue,
            life_simulator=construct(life_simulator_factory),
            rhythm_learner=construct(rhythm_learner_factory),
            social_field=construct(social_field_factory),
            proactive_scheduler=construct(proactive_scheduler_factory),
            v2_persistence=construct(v2_persistence_factory),
            v3_shadow_state=construct(v3_shadow_state_factory),
        )

    @property
    def storage_token(self) -> str:
        return self.scope.storage_token

    def device_context_owner(self) -> object | None:
        """Return the session's frozen device context without a raw session key.

        The local import avoids a module cycle: ``session_context`` consumes this
        runtime type, while this lazy factory is only reached after construction.
        """

        owner = self._device_context_owner
        if owner is not None:
            return owner
        persistence = self.persistence
        if persistence is None:
            return None
        from sylanne_alpha.session_context import ScopedDeviceContext

        owner = ScopedDeviceContext(persistence)
        object.__setattr__(self, "_device_context_owner", owner)
        return owner


@dataclass(frozen=True, slots=True)
class RequestRuntimeView:
    """One immutable request view with no sibling/default runtime selection."""

    resolved: ResolvedScope
    persona_runtime: PersonaRuntime
    session_runtime: ScopedSessionRuntime
    relation_runtime: RelationRuntime | None = None
    subject: AuthenticatedSubject | None = None

    def __post_init__(self) -> None:
        if type(self.resolved) is not ResolvedScope or self.resolved.scope is None:
            raise ValueError("request runtime requires an enabled resolved scope")
        if type(self.persona_runtime) is not PersonaRuntime:
            raise ValueError("persona_runtime must be a PersonaRuntime")
        if type(self.session_runtime) is not ScopedSessionRuntime:
            raise ValueError("session_runtime must be a ScopedSessionRuntime")
        scope = self.resolved.scope
        if (
            self.persona_runtime.persona_ref != scope.persona_ref
            or self.session_runtime.scope != scope
            or self.session_runtime.store is not self.persona_runtime.store
        ):
            raise ValueError("request runtime parent scope mismatch")
        if self.subject is not None and type(self.subject) is not AuthenticatedSubject:
            raise ValueError("subject must be an AuthenticatedSubject or None")
        if self.subject is None and self.relation_runtime is not None:
            raise ValueError("missing subject cannot carry a relation runtime")
        if self.subject is not None and self.relation_runtime is None:
            raise ValueError("authenticated subject requires its relation runtime")
        if self.relation_runtime is not None:
            relation = self.relation_runtime
            if (
                type(relation) is not RelationRuntime
                or relation.scope.bot_ref != scope.bot_ref
                or relation.scope.persona_ref != scope.persona_ref
                or relation.scope.relation_ref != self.subject.relation_ref
            ):
                raise ValueError("request runtime parent scope mismatch")


@dataclass(frozen=True, slots=True)
class TransportRuntimeOwner:
    """Non-creating transport lookup result for one already-frozen runtime."""

    scope: SessionScope
    persona_runtime: PersonaRuntime
    session_runtime: ScopedSessionRuntime


class ScopeRuntimeRegistry:
    """Registry with no default, most-recent, or sibling selection behavior."""

    def __init__(
        self,
        runtime_factory: Callable[[SessionScope], PersonaRuntime] | None = None,
        *,
        repository: ScopeRepository | None = None,
        session_runtime_factory: Callable[
            [SessionScope, PersonaRuntime, ScopedPersistenceGateway | None],
            ScopedSessionRuntime,
        ]
        | None = None,
        relation_runtime_factory: Callable[[RelationScope, RelationScopedPersistenceGateway | None], RelationRuntime]
        | None = None,
    ) -> None:
        if repository is not None and not isinstance(repository, ScopeRepository):
            raise ValueError("repository must be a ScopeRepository or None")
        if relation_runtime_factory is not None and not callable(relation_runtime_factory):
            raise ValueError("relation_runtime_factory must be callable or None")
        self._runtime_factory = runtime_factory or self._default_runtime
        self._repository = repository
        self._session_runtime_factory = (
            session_runtime_factory or self._default_session_runtime
        )
        self._relation_runtime_factory = relation_runtime_factory or self._default_relation_runtime
        self._personas: dict[PersonaKey, PersonaRuntime] = {}
        self._sessions: dict[SessionKey, ScopedSessionRuntime] = {}
        self._latest_sessions: dict[tuple[PersonaKey, str], SessionKey] = {}
        self._highest_session_generations: dict[tuple[PersonaKey, str], int] = {}
        self._released_sessions: set[SessionKey] = set()
        self._retired_personas: set[PersonaKey] = set()
        self._transport_owners: dict[TransportKey, SessionKey] = {}
        self._highest_transport_generations: dict[TransportIdentityKey, int] = {}
        self._request_views: OrderedDict[
            RequestViewKey,
            RequestRuntimeView,
        ] = OrderedDict()

    @property
    def repository(self) -> ScopeRepository | None:
        """Return the immutable repository binding, never a mutable selector."""

        return self._repository

    def bind_repository(self, repository: ScopeRepository) -> None:
        """Bind the sole scope repository before any runtime owner exists."""

        if not isinstance(repository, ScopeRepository):
            raise ValueError("repository must be a ScopeRepository")
        if (
            self._personas
            or self._sessions
            or self._transport_owners
            or self._retired_personas
            or self._released_sessions
            or self._latest_sessions
            or self._highest_session_generations
            or self._highest_transport_generations
            or self._request_views
        ):
            raise ScopeMismatch("repository binding must precede every runtime")
        if self._repository is repository:
            return
        if self._repository is not None:
            raise ScopeMismatch("repository is already bound")
        self._repository = repository

    @property
    def persona_count(self) -> int:
        """Number of currently live Persona runtimes (test/diagnostic seam)."""

        return len(self._personas)

    @property
    def session_count(self) -> int:
        """Number of currently live exact Session runtimes (test/diagnostic seam)."""

        return len(self._sessions)

    @property
    def issued_request_view_count(self) -> int:
        """Bounded number of still-valid request view seals."""

        return len(self._request_views)

    def live_persona_runtimes(self) -> tuple[PersonaRuntime, ...]:
        """Snapshot live owners for explicit lifecycle shutdown handling."""

        return tuple(self._personas.values())

    def live_session_runtimes(self) -> tuple[ScopedSessionRuntime, ...]:
        """Snapshot exact session owners for explicit lifecycle work."""

        return tuple(self._sessions.values())

    @staticmethod
    def _request_view_key(
        scope: SessionScope,
        turn_generation: int,
    ) -> RequestViewKey:
        session = _session_key(scope)
        return (*session, turn_generation)

    def issue_request_view(
        self,
        resolved: ResolvedScope,
        *,
        subject: AuthenticatedSubject | None,
        relation_runtime: RelationRuntime | None,
    ) -> RequestRuntimeView:
        """Issue the sole immutable runtime view for one exact frozen turn."""

        if (
            type(resolved) is not ResolvedScope
            or resolved.private_scope_enabled is not True
            or resolved.scope is None
        ):
            raise ScopeMismatch("request view requires an enabled resolved scope")
        scope = _require_scope(resolved.scope)
        view = RequestRuntimeView(
            resolved=resolved,
            persona_runtime=self.for_scope(scope),
            session_runtime=self.exact_session(scope),
            relation_runtime=relation_runtime,
            subject=subject,
        )
        key = self._request_view_key(scope, resolved.turn_generation)
        existing = self._request_views.get(key)
        if existing is not None:
            if (
                existing.resolved is resolved
                and existing.subject == subject
                and existing.relation_runtime is relation_runtime
            ):
                return existing
            raise ScopeMismatch("a request runtime view is already issued for this turn")
        self._request_views[key] = view
        self._request_views.move_to_end(key)
        session_prefix = key[:5]
        same_session = [
            item for item in self._request_views if item[:5] == session_prefix
        ]
        while len(same_session) > _MAX_REQUEST_VIEWS_PER_SESSION:
            oldest = same_session.pop(0)
            self._request_views.pop(oldest, None)
        while len(self._request_views) > _MAX_REQUEST_VIEWS_GLOBAL:
            self._request_views.popitem(last=False)
        self._sync_relation_rituals(view)
        return view

    def is_issued_request_view(self, candidate: object) -> bool:
        """Validate object identity against the registry-issued turn seal."""

        if type(candidate) is not RequestRuntimeView:
            return False
        scope = candidate.resolved.scope
        if scope is None or not self.is_live_session(scope):
            return False
        key = self._request_view_key(scope, candidate.resolved.turn_generation)
        if self._request_views.get(key) is not candidate:
            return False
        if (
            self._personas.get(_persona_key(scope)) is not candidate.persona_runtime
            or self._sessions.get(_session_key(scope)) is not candidate.session_runtime
        ):
            return False
        relation = candidate.relation_runtime
        if relation is not None and self.relation_or_none(relation.scope) is not relation:
            return False
        return True

    def release_request_view(self, candidate: object) -> bool:
        """Release only the exact issued object; never select a replacement."""

        if type(candidate) is not RequestRuntimeView:
            return False
        scope = candidate.resolved.scope
        if scope is None:
            return False
        key = self._request_view_key(scope, candidate.resolved.turn_generation)
        if self._request_views.get(key) is not candidate:
            return False
        self._request_views.pop(key, None)
        return True

    @staticmethod
    def _sync_relation_rituals(view: RequestRuntimeView) -> None:
        relation = view.relation_runtime
        if relation is None:
            return
        scheduler = view.session_runtime.proactive_scheduler
        register = getattr(scheduler, "register_ritual", None)
        if not callable(register):
            return
        for ritual in relation.active_rituals():
            register(
                relation.scope.relation_ref.token,
                str(ritual["pattern"]),
                int(ritual["hour_start"]),
                int(ritual["hour_end"]),
            )

    @classmethod
    def for_test(
        cls,
        *,
        repository: ScopeRepository | None = None,
        session_runtime_factory: Callable[
            [SessionScope, PersonaRuntime, ScopedPersistenceGateway | None],
            ScopedSessionRuntime,
        ]
        | None = None,
        relation_runtime_factory: Callable[[RelationScope, RelationScopedPersistenceGateway | None], RelationRuntime]
        | None = None,
    ) -> ScopeRuntimeRegistry:
        """Create an isolated registry with inert mutable owners."""

        return cls(
            repository=repository,
            session_runtime_factory=session_runtime_factory,
            relation_runtime_factory=relation_runtime_factory,
        )

    @staticmethod
    def _default_runtime(scope: SessionScope) -> PersonaRuntime:
        return PersonaRuntime(persona_ref=scope.persona_ref)

    @staticmethod
    def _default_relation_runtime(
        scope: RelationScope,
        persistence: RelationScopedPersistenceGateway | None,
    ) -> RelationRuntime:
        return RelationRuntime(scope=scope, persistence=persistence)

    @staticmethod
    def _default_session_runtime(
        scope: SessionScope,
        persona_runtime: PersonaRuntime,
        persistence: ScopedPersistenceGateway | None,
    ) -> ScopedSessionRuntime:
        return ScopedSessionRuntime(
            scope=scope,
            store=persona_runtime.store,
            persistence=persistence,
        )

    def _new_runtime(self, scope: SessionScope) -> PersonaRuntime:
        runtime = self._runtime_factory(scope)
        if type(runtime) is not PersonaRuntime:
            raise ScopeMismatch("runtime factory must return a PersonaRuntime")
        if runtime.persona_ref != scope.persona_ref:
            raise ScopeMismatch("runtime factory returned a sibling persona runtime")
        return runtime

    def for_scope(self, scope: SessionScope) -> PersonaRuntime:
        """Return the exact Persona runtime identified by a frozen scope."""

        scope = _require_scope(scope)
        key = _persona_key(scope)
        if key in self._retired_personas:
            raise ScopeMismatch("persona runtime has been retired")
        runtime = self._personas.get(key)
        if runtime is None:
            runtime = self._new_runtime(scope)
            self._personas[key] = runtime
        return runtime

    def exact_session(self, scope: SessionScope) -> ScopedSessionRuntime:
        """Return the exact session runtime; a missing scope is never inferred."""

        scope = _require_scope(scope)
        key = _session_key(scope)
        if _persona_key(scope) in self._retired_personas:
            raise ScopeMismatch("persona runtime has been retired")
        generation_key = (_persona_key(scope), scope.storage_token)
        highest_generation = self._highest_session_generations.get(generation_key)
        if highest_generation is not None and scope.scope_generation < highest_generation:
            raise ScopeMismatch("session scope generation is stale")
        if key in self._released_sessions:
            raise ScopeMismatch("session runtime has been released")
        runtime = self._sessions.get(key)
        if runtime is None:
            persistence = None if self._repository is None else ScopedPersistenceGateway(self._repository, scope)
            persona_runtime = self.for_scope(scope)
            runtime = self._session_runtime_factory(
                scope,
                persona_runtime,
                persistence,
            )
            if (
                type(runtime) is not ScopedSessionRuntime
                or runtime.scope != scope
                or runtime.store is not persona_runtime.store
                or runtime.persistence is not persistence
            ):
                raise ScopeMismatch(
                    "session runtime factory returned an invalid exact owner"
                )
            self._sessions[key] = runtime
            self._latest_sessions[generation_key] = key
            self._highest_session_generations[generation_key] = scope.scope_generation
        return runtime

    def exact_session_or_none(
        self,
        scope: SessionScope | None,
    ) -> ScopedSessionRuntime | None:
        """Return ``None`` for unavailable/retired scope, never a sibling session."""

        if scope is None:
            return None
        scope = _require_scope(scope)
        if _persona_key(scope) in self._retired_personas:
            return None
        try:
            return self.exact_session(scope)
        except ScopeMismatch:
            return None

    def publish_transport_owner(
        self,
        transport: ResolvedTransportScope,
        scope: SessionScope,
    ) -> bool:
        """Publish one already-frozen runtime for exact pre-request safety work.

        This method is deliberately non-creating.  The caller must have completed
        Persona freeze and constructed the exact session runtime first.  A raw
        transport identifier can never create, select, or bind private state.
        """

        try:
            scope = _require_scope(scope)
            transport_key = _transport_key(transport)
        except ScopeMismatch:
            return False
        if transport.bot_ref != scope.bot_ref or transport.session_ref != scope.session_ref:
            return False
        session_key = _session_key(scope)
        session_runtime = self._sessions.get(session_key)
        persona_runtime = self._personas.get(_persona_key(scope))
        if (
            session_runtime is None
            or persona_runtime is None
            or session_runtime.scope != scope
            or session_runtime.store is not persona_runtime.store
            or not self.is_live_session(scope)
        ):
            return False
        # SessionRef generation is a monotonic authority fence.  A late old
        # request may remain a live exact runtime, but it must never evict the
        # newer transport owner.  Same-generation publication remains valid for
        # a later successfully frozen Persona switch.
        identity = transport_key[:3]
        generation = transport_key[3]
        highest_generation = self._highest_transport_generations.get(identity)
        if highest_generation is not None and generation < highest_generation:
            return False
        self._highest_transport_generations[identity] = generation
        for key in list(self._transport_owners):
            if key[:3] == identity and key != transport_key:
                self._transport_owners.pop(key, None)
        self._transport_owners[transport_key] = session_key
        return True

    def transport_owner_or_none(
        self,
        transport: ResolvedTransportScope,
    ) -> TransportRuntimeOwner | None:
        """Resolve an exact published owner without creating or guessing one."""

        try:
            transport_key = _transport_key(transport)
        except ScopeMismatch:
            return None
        session_key = self._transport_owners.get(transport_key)
        if session_key is None:
            return None
        session_runtime = self._sessions.get(session_key)
        if session_runtime is None:
            self._transport_owners.pop(transport_key, None)
            self._drop_unused_transport_generation_fence(transport_key[:3])
            return None
        scope = session_runtime.scope
        persona_runtime = self._personas.get(_persona_key(scope))
        if (
            persona_runtime is None
            or transport.bot_ref != scope.bot_ref
            or transport.session_ref != scope.session_ref
            or session_runtime.store is not persona_runtime.store
            or not self.is_live_session(scope)
        ):
            self._transport_owners.pop(transport_key, None)
            self._drop_unused_transport_generation_fence(transport_key[:3])
            return None
        return TransportRuntimeOwner(
            scope=scope,
            persona_runtime=persona_runtime,
            session_runtime=session_runtime,
        )

    def is_live_session(self, scope: SessionScope) -> bool:
        """Whether ``scope`` still names the current exact session owner.

        This is deliberately non-creating.  Delayed callbacks use it immediately
        before a write so an old generation can never resurrect or overwrite a
        newer session with the same opaque storage token.
        """

        try:
            scope = _require_scope(scope)
        except ScopeMismatch:
            return False
        persona_key = _persona_key(scope)
        if persona_key in self._retired_personas:
            return False
        key = _session_key(scope)
        if key in self._released_sessions or key not in self._sessions:
            return False
        return self._latest_sessions.get((persona_key, scope.storage_token)) == key

    def track_session_task(self, scope: SessionScope, task: Any) -> bool:
        """Associate a callback task with its exact session for release fencing."""

        if not self.is_live_session(scope):
            cancel = getattr(task, "cancel", None)
            if callable(cancel):
                cancel()
            return False
        runtime = self._personas.get(_persona_key(scope))
        if runtime is None:
            return False
        key = _session_key(scope)
        tasks = runtime.session_background_tasks.setdefault(key, set())
        tasks.add(task)

        def _discard(done_task: Any) -> None:
            tasks.discard(done_task)
            if not tasks:
                runtime.session_background_tasks.pop(key, None)

        callback = getattr(task, "add_done_callback", None)
        if callable(callback):
            callback(_discard)
        return True

    def relation_for(
        self,
        scope: SessionScope,
        subject: AuthenticatedSubject | None,
    ) -> RelationRuntime | None:
        """Activate one exact authenticated relation beneath a validated session.

        Absence is an intentional no-op.  There is no raw subject fallback and no
        selection of a first/latest relation: the repository decides the active
        relation generation under its lock, and the full Bot/Persona/lifecycle/
        relation/generation key selects the only runtime owner.
        """

        scope = _require_scope(scope)
        if subject is None:
            return None
        if type(subject) is not AuthenticatedSubject:
            raise ScopeMismatch("an AuthenticatedSubject or None is required")
        repository = self._repository
        if repository is None:
            return None
        repository.validate_session_scope(scope)
        session_runtime = self.exact_session(scope)
        persona_runtime = self.for_scope(scope)
        if session_runtime.store is not persona_runtime.store:
            raise ScopeMismatch("session runtime does not belong to persona runtime")
        relation_scope = repository.activate_relation_scope(
            scope.persona_ref,
            subject.relation_ref,
        )
        if relation_scope.bot_ref != scope.bot_ref or relation_scope.persona_ref != scope.persona_ref:
            raise ScopeMismatch("activated relation does not belong to session scope")
        persistence = RelationScopedPersistenceGateway(repository, relation_scope)
        return persona_runtime.relation_for(
            relation_scope,
            persistence=persistence,
            factory=self._relation_runtime_factory,
        )

    def relation_or_none(self, scope: RelationScope | None) -> RelationRuntime | None:
        """Resolve only an authenticated relation scope; absence is a no-op."""

        if scope is None:
            return None
        if type(scope) is not RelationScope:
            raise ScopeMismatch("an authenticated RelationScope is required")
        key: PersonaKey = (
            scope.bot_ref.token,
            scope.persona_ref.token,
            scope.persona_ref.lifecycle_generation,
        )
        if key in self._retired_personas:
            return None
        runtime = self._personas.get(key)
        if runtime is None:
            # A RelationScope has no SessionScope from which to invoke the normal
            # factory.  Do not fabricate a default session/persona runtime.
            return None
        relation = runtime.relation_runtimes.get(_relation_key(scope))
        if relation is None:
            return None
        if type(relation) is not RelationRuntime or relation.scope != scope:
            raise ScopeMismatch("relation runtime does not match exact relation scope")
        return relation

    def release_session(self, scope: SessionScope) -> None:
        """Release only this exact session without creating or changing siblings."""

        scope = _require_scope(scope)
        persona_key = _persona_key(scope)
        if persona_key in self._retired_personas:
            return
        runtime = self._personas.get(persona_key)
        if runtime is None:
            return
        session_key = _session_key(scope)
        transport_identity = _transport_identity_for_scope(scope)
        for transport_key, owner_key in list(self._transport_owners.items()):
            if owner_key == session_key:
                self._transport_owners.pop(transport_key, None)
        self._released_sessions.add(session_key)
        session_runtime = self._sessions.get(session_key)
        if session_runtime is not None:
            checkpoint = getattr(
                session_runtime.background_queue,
                "save_checkpoint_now",
                None,
            )
            if callable(checkpoint):
                try:
                    checkpoint()
                except Exception:
                    pass
            self._cancel_tasks((session_runtime.lifecycle.proactive_scheduler_task,))
        self._cancel_tasks(runtime.session_background_tasks.pop(session_key, set()))
        self._sessions.pop(session_key, None)
        for key in [item for item in self._request_views if item[:5] == session_key]:
            self._request_views.pop(key, None)
        self._drop_unused_transport_generation_fence(transport_identity)
        latest_key = (persona_key, scope.storage_token)
        current_key = self._latest_sessions.get(latest_key)
        if current_key is not None and current_key != session_key:
            return
        for owner in (runtime.self_core, runtime.autonomy_scheduler):
            forget = getattr(owner, "forget_session", None)
            if callable(forget):
                try:
                    forget(scope.storage_token)
                except Exception:
                    pass
        runtime.store.release_session(scope.storage_token)
        runtime.memory_systems.pop(scope.storage_token, None)
        for cache_key, value in list(runtime.v2core_runtimes.items()):
            if isinstance(value, dict) and value.get("scope") == scope:
                runtime.v2core_runtimes.pop(cache_key, None)
        if current_key == session_key:
            self._latest_sessions.pop(latest_key, None)

    def retire_persona(self, scope: SessionScope | PersonaRevisionRef) -> bool:
        """Fence a lifecycle generation and cancel only that Persona's owned tasks.

        The caller must resolve the next lifecycle generation before asking for a
        replacement.  A retired key remains fenced, so an old scope cannot silently
        recreate its prior runtime after a release or shutdown race.
        """

        if type(scope) is SessionScope:
            key = _persona_key(scope)
        elif type(scope) is PersonaRevisionRef:
            key = (
                scope.bot_ref.token,
                scope.token,
                scope.lifecycle_generation,
            )
        else:
            raise ScopeMismatch("a SessionScope or PersonaRevisionRef is required")
        if key in self._retired_personas:
            return False
        self._retired_personas.add(key)
        runtime = self._personas.pop(key, None)
        transport_identities = {
            _transport_identity_for_scope(session_runtime.scope)
            for session_key, session_runtime in self._sessions.items()
            if session_key[:3] == key
        }
        for session_key in [item for item in self._sessions if item[:3] == key]:
            self._sessions.pop(session_key, None)
        for request_key in [item for item in self._request_views if item[:3] == key]:
            self._request_views.pop(request_key, None)
        for latest_key in [item for item in self._latest_sessions if item[0] == key]:
            self._latest_sessions.pop(latest_key, None)
        for generation_key in [item for item in self._highest_session_generations if item[0] == key]:
            self._highest_session_generations.pop(generation_key, None)
        for transport_key, session_key in list(self._transport_owners.items()):
            if session_key[:3] == key:
                transport_identities.add(transport_key[:3])
                self._transport_owners.pop(transport_key, None)
        for identity in transport_identities:
            self._drop_unused_transport_generation_fence(identity)
        self._released_sessions = {item for item in self._released_sessions if item[:3] != key}
        if runtime is not None:
            self._cancel_runtime_tasks(runtime)
            runtime.memory_systems.clear()
            runtime.v2core_runtimes.clear()
            runtime.v2core_pending_saves.clear()
            runtime.v2core_save_locks.clear()
            runtime.store.reset_all()
            runtime.relation_runtimes.clear()
        return runtime is not None

    def _drop_unused_transport_generation_fence(
        self,
        identity: TransportIdentityKey,
    ) -> None:
        """Drop high-water state only when no exact session can late-publish."""

        if any(
            _transport_identity_for_scope(runtime.scope) == identity and self.is_live_session(runtime.scope)
            for runtime in self._sessions.values()
        ):
            return
        self._highest_transport_generations.pop(identity, None)

    @staticmethod
    def _cancel_runtime_tasks(runtime: PersonaRuntime) -> None:
        """Best-effort cancellation without touching process-global task ownership."""

        candidates: list[Any] = list(runtime.background_tasks)
        if runtime.proactive_scheduler_task is not None:
            candidates.append(runtime.proactive_scheduler_task)
        if runtime.autonomy_scheduler_task is not None:
            candidates.append(runtime.autonomy_scheduler_task)
        candidates.extend(task for tasks in runtime.session_background_tasks.values() for task in tasks)
        candidates.extend(runtime.store.background_post_checkpoint_tasks.values())
        ScopeRuntimeRegistry._cancel_tasks(candidates)
        runtime.proactive_scheduler_task = None
        runtime.autonomy_scheduler_task = None
        runtime.session_background_tasks.clear()
        scheduler = runtime.proactive_scheduler
        stop = getattr(scheduler, "stop", None)
        # Scheduler implementations which need awaiting must register their task in
        # ``background_tasks``.  Calling an async stop hook from this synchronous
        # fence would create an unowned coroutine and can resurrect retired state.
        if callable(stop) and not inspect.iscoroutinefunction(stop):
            try:
                stop()
            except Exception:
                pass
        autonomy_scheduler = runtime.autonomy_scheduler
        autonomy_stop = getattr(autonomy_scheduler, "stop", None)
        if callable(autonomy_stop) and not inspect.iscoroutinefunction(autonomy_stop):
            try:
                autonomy_stop()
            except Exception:
                pass

    @staticmethod
    def _unique(items: Iterable[Any]) -> Iterable[Any]:
        seen: set[int] = set()
        for item in items:
            marker = id(item)
            if marker not in seen:
                seen.add(marker)
                yield item

    @staticmethod
    def _cancel_tasks(tasks: Iterable[Any]) -> None:
        for candidate in ScopeRuntimeRegistry._unique(tasks):
            cancel = getattr(candidate, "cancel", None)
            if callable(cancel):
                try:
                    cancel()
                except Exception:
                    pass


__all__ = [
    "PersonaRuntime",
    "RelationRuntime",
    "RequestRuntimeView",
    "ScopeMismatch",
    "ScopeRuntimeRegistry",
    "ScopeUnavailable",
    "ScopedSessionRuntime",
    "ScopedSessionLifecycle",
    "TransportRuntimeOwner",
]
