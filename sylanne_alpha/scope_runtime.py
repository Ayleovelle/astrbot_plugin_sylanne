"""Exact, fail-closed ownership for mutable Bot/Persona/Session runtime state.

The scope resolver freezes a :class:`~sylanne_alpha.scope_contracts.SessionScope`
before any private runtime work starts.  This module deliberately accepts only that
frozen scope; it never tries to recover a scope from a raw transport/session value.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
import inspect
from typing import Any

from sylanne_alpha.scope_contracts import (
    PersonaRevisionRef,
    RelationScope,
    ResolvedTransportScope,
    SessionScope,
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


@dataclass(slots=True)
class RelationRuntime:
    """Mutable relationship state belonging to exactly one Persona + relation.

    Relation resolution is intentionally separate from session resolution.  Callers
    without an authenticated ``RelationScope`` must use ``relation_or_none`` and
    skip their observation; creating a default or sibling relation is forbidden.
    """

    scope: RelationScope
    first_interaction_times: dict[str, float] = field(default_factory=dict)
    first_impressions: dict[str, Any] = field(default_factory=dict)
    ritual_registry: object | None = None


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
    relation_runtime_factory: Callable[[RelationScope], RelationRuntime] = field(
        default=lambda scope: RelationRuntime(scope=scope),
        repr=False,
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

    def relation_for(self, scope: RelationScope) -> RelationRuntime:
        """Return an exact authenticated relation owner for this Persona runtime."""

        if type(scope) is not RelationScope:
            raise ScopeMismatch("an authenticated RelationScope is required")
        if scope.persona_ref != self.persona_ref:
            raise ScopeMismatch("relation scope does not belong to persona runtime")
        key = _relation_key(scope)
        runtime = self.relation_runtimes.get(key)
        if runtime is None:
            runtime = self.relation_runtime_factory(scope)
            if type(runtime) is not RelationRuntime or runtime.scope != scope:
                raise ScopeMismatch("relation runtime factory returned an invalid runtime")
            self.relation_runtimes[key] = runtime
        return runtime


@dataclass(frozen=True, slots=True)
class ScopedSessionRuntime:
    """Session-only mutable state addressed by the frozen ``storage_token``."""

    scope: SessionScope
    store: SessionStateStore
    device_fingerprints: dict[str, str] = field(default_factory=dict, compare=False)

    @property
    def storage_token(self) -> str:
        return self.scope.storage_token


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
    ) -> None:
        self._runtime_factory = runtime_factory or self._default_runtime
        self._personas: dict[PersonaKey, PersonaRuntime] = {}
        self._sessions: dict[SessionKey, ScopedSessionRuntime] = {}
        self._latest_sessions: dict[tuple[PersonaKey, str], SessionKey] = {}
        self._highest_session_generations: dict[tuple[PersonaKey, str], int] = {}
        self._released_sessions: set[SessionKey] = set()
        self._retired_personas: set[PersonaKey] = set()
        self._transport_owners: dict[TransportKey, SessionKey] = {}
        self._highest_transport_generations: dict[TransportIdentityKey, int] = {}

    @property
    def persona_count(self) -> int:
        """Number of currently live Persona runtimes (test/diagnostic seam)."""

        return len(self._personas)

    @property
    def session_count(self) -> int:
        """Number of currently live exact Session runtimes (test/diagnostic seam)."""

        return len(self._sessions)

    def live_persona_runtimes(self) -> tuple[PersonaRuntime, ...]:
        """Snapshot live owners for explicit lifecycle shutdown handling."""

        return tuple(self._personas.values())

    def live_session_runtimes(self) -> tuple[ScopedSessionRuntime, ...]:
        """Snapshot exact session owners for explicit lifecycle work."""

        return tuple(self._sessions.values())

    @classmethod
    def for_test(cls) -> ScopeRuntimeRegistry:
        """Create an isolated registry with inert mutable owners."""

        return cls()

    @staticmethod
    def _default_runtime(scope: SessionScope) -> PersonaRuntime:
        return PersonaRuntime(persona_ref=scope.persona_ref)

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
            runtime = ScopedSessionRuntime(scope=scope, store=self.for_scope(scope).store)
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
        if (
            transport.bot_ref != scope.bot_ref
            or transport.session_ref != scope.session_ref
        ):
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
        return runtime.relation_for(scope)

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
        self._cancel_tasks(runtime.session_background_tasks.pop(session_key, set()))
        self._sessions.pop(session_key, None)
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
        self._released_sessions = {
            item for item in self._released_sessions if item[:3] != key
        }
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
            _transport_identity_for_scope(runtime.scope) == identity
            and self.is_live_session(runtime.scope)
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
        candidates.extend(
            task
            for tasks in runtime.session_background_tasks.values()
            for task in tasks
        )
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
    "ScopeMismatch",
    "ScopeRuntimeRegistry",
    "ScopeUnavailable",
    "ScopedSessionRuntime",
    "TransportRuntimeOwner",
]
