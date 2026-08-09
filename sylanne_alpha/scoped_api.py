"""Shared authorization boundary for the private scoped WebUI API.

The service is intentionally independent of aiohttp and AstrBot.  Both HTTP
hosts adapt their request objects into :class:`ScopedApiRequest` and receive
the same authorization result, generation fences, and redacted payloads.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Final, Mapping, TypeAlias

from .scope_contracts import (
    PersonaApiEcho,
    PersonaApiPathEcho,
    PersonaScope,
    RelationScope,
    ScopeApiEcho,
    ScopeApiPathEcho,
    ScopedPrincipal,
    SessionScope,
)
from .scope_repository import (
    RepositoryCorruptionError,
    ScopeBotNotFound,
    ScopeParentMismatch,
    ScopePersonaNotFound,
    ScopeRepository,
    StaleScopeWrite,
)
from .scope_runtime import ScopeRuntimeRegistry


SCOPED_API_ROOT: Final[str] = "/api/v1/bots/{bot_ref}/personas/{persona_ref}/sessions/{session_ref}"
SCOPE_NONCE_HEADER: Final[str] = "X-Sylanne-Scope-Nonce"

SCOPED_API_ENDPOINTS: Final[frozenset[str]] = frozenset(
    {
        "scope",
        "state",
        "observation-history",
        "diagnostics",
        "memory-pools",
        "memory/consolidate",
        "memory/sink",
        "memory/meltdown",
        "memory/meltdown-nonce",
        "legacy-claim",
        "stream",
        "ws",
    }
)
_SCOPED_API_METHODS: Final[dict[str, str]] = {
    "scope": "GET",
    "state": "GET",
    "observation-history": "GET",
    "diagnostics": "GET",
    "memory-pools": "GET",
    "memory/consolidate": "POST",
    "memory/sink": "POST",
    "memory/meltdown": "POST",
    "memory/meltdown-nonce": "GET",
    "legacy-claim": "POST",
    "stream": "GET",
    "ws": "GET",
}
SCOPED_API_METHODS: Final[Mapping[str, str]] = MappingProxyType(_SCOPED_API_METHODS)
PrincipalScopeGrant: TypeAlias = Callable[
    [ScopedPrincipal, SessionScope, str], RelationScope | None
]
PrincipalPersonaGrant: TypeAlias = Callable[
    [ScopedPrincipal, PersonaScope, str], RelationScope | None
]

_NONCE_PREFIX: Final[str] = "scope_nonce_v1_"
_NONCE_TTL_MS: Final[int] = 30_000
_SAFE_NONCE_CHARS: Final[frozenset[str]] = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
)


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _is_shaped_nonce(value: object, prefix: str) -> bool:
    if type(value) is not str or not value.startswith(prefix):
        return False
    suffix = value[len(prefix) :]
    return len(suffix) >= 16 and all(character in _SAFE_NONCE_CHARS for character in suffix)


def scoped_api_path(path: ScopeApiPathEcho, endpoint: str = "scope") -> str:
    """Build the only accepted private API root without a session selector."""

    if type(path) is not ScopeApiPathEcho:
        raise ValueError("path must be a ScopeApiPathEcho")
    normalized = _require_endpoint(endpoint)
    root = SCOPED_API_ROOT.format(
        bot_ref=path.bot_ref,
        persona_ref=path.persona_ref,
        session_ref=path.session_ref,
    )
    return root if normalized == "scope" else f"{root}/{normalized}"


def _require_endpoint(value: object) -> str:
    if type(value) is not str:
        raise ValueError("endpoint must be a str")
    normalized = value.strip().strip("/") or "scope"
    if normalized not in SCOPED_API_ENDPOINTS:
        raise ValueError("unsupported scoped API endpoint")
    return normalized


def _require_method(value: object) -> str:
    if type(value) is not str:
        raise ValueError("method must be a str")
    normalized = value.upper()
    if normalized not in {"GET", "POST"}:
        raise ValueError("unsupported scoped API method")
    return normalized


def _scoped_action(endpoint: object, method: object) -> str:
    """Return the canonical endpoint action carried by each one-use nonce."""

    normalized_method = _require_method(method)
    route = scoped_api_route_spec(endpoint)
    if route.method != normalized_method:
        raise ValueError("scoped API method does not match endpoint")
    return route.action


@dataclass(frozen=True, slots=True)
class ScopeRouteSpec:
    """Transport-neutral endpoint/action contract owned by the core gate."""

    endpoint: str
    method: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "endpoint", _require_endpoint(self.endpoint))
        object.__setattr__(self, "method", _require_method(self.method))
        if SCOPED_API_METHODS[self.endpoint] != self.method:
            raise ValueError("scoped API method does not match endpoint")

    @property
    def action(self) -> str:
        return f"{self.method}:{self.endpoint}"


@dataclass(frozen=True, slots=True)
class PersonaRouteSpec:
    """Transport-neutral Persona resource/action contract owned by the core gate."""

    endpoint: str
    method: str

    def __post_init__(self) -> None:
        if type(self.endpoint) is not str or self.endpoint != "dossier":
            raise ValueError("unsupported Persona API endpoint")
        if type(self.method) is not str or self.method != "GET":
            raise ValueError("Persona dossier requires GET")

    @property
    def action(self) -> str:
        return f"{self.method}:persona-{self.endpoint}"


PERSONA_DOSSIER_ROUTE_SPEC: Final[PersonaRouteSpec] = PersonaRouteSpec(
    endpoint="dossier",
    method="GET",
)


SCOPED_API_ROUTE_SPECS: Final = MappingProxyType(
    {
        endpoint: ScopeRouteSpec(endpoint=endpoint, method=method)
        for endpoint, method in SCOPED_API_METHODS.items()
    }
)


def scoped_api_route_spec(endpoint: object) -> ScopeRouteSpec:
    """Return the immutable method/action contract for one supported endpoint."""

    return SCOPED_API_ROUTE_SPECS[_require_endpoint(endpoint)]


def _require_principal(principal: object) -> ScopedPrincipal:
    if type(principal) is not ScopedPrincipal:
        raise ValueError("principal must be a ScopedPrincipal")
    return principal


@dataclass(frozen=True, slots=True)
class ScopedApiRequest:
    """Pure transport-neutral request DTO for one exact scoped endpoint."""

    path: ScopeApiPathEcho
    nonce: str | None
    endpoint: str = "scope"
    method: str = "GET"
    principal: ScopedPrincipal | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if type(self.path) is not ScopeApiPathEcho:
            raise ValueError("path must be a ScopeApiPathEcho")
        object.__setattr__(self, "endpoint", _require_endpoint(self.endpoint))
        object.__setattr__(self, "method", _require_method(self.method))
        if SCOPED_API_METHODS[self.endpoint] != self.method:
            raise ValueError("scoped API method does not match endpoint")
        if self.nonce is not None and type(self.nonce) is not str:
            raise ValueError("nonce must be a str or None")
        if self.principal is not None:
            _require_principal(self.principal)

    @classmethod
    def from_tokens(
        cls,
        *,
        bot_ref: str,
        persona_ref: str,
        session_ref: str,
        nonce: str | None,
        endpoint: str = "scope",
        method: str = "GET",
        principal: ScopedPrincipal | None = None,
    ) -> ScopedApiRequest:
        return cls(
            path=ScopeApiPathEcho(
                bot_ref=bot_ref,
                persona_ref=persona_ref,
                session_ref=session_ref,
            ),
            nonce=nonce,
            endpoint=endpoint,
            method=method,
            principal=principal,
        )


@dataclass(frozen=True, slots=True)
class ScopedApiError:
    """Stable, redacted failure projection shared by both WebUI hosts."""

    status: int
    code: str
    websocket_close_code: int | None = None

    def __post_init__(self) -> None:
        if type(self.status) is not int or self.status not in {
            400,
            403,
            404,
            409,
            410,
            503,
        }:
            raise ValueError("status must be a scoped API status")
        if type(self.code) is not str or not self.code:
            raise ValueError("code must be a non-empty str")
        if self.websocket_close_code is not None and type(self.websocket_close_code) is not int:
            raise ValueError("websocket_close_code must be an int or None")

    def public_payload(self) -> dict[str, str]:
        return {"error": self.code}


class ScopedApiRuntimeUnavailable(RuntimeError):
    """A final locked catalog fence could not read trusted durable state."""


@dataclass(frozen=True, slots=True)
class ScopedApiAuthorization:
    """A consumed scope nonce bound to one redacted path and generation tuple."""

    scope: SessionScope = field(repr=False)
    relation_scope: RelationScope = field(repr=False)
    turn_generation: int = field(repr=False)
    expires_at_ms: int = field(repr=False)
    principal: ScopedPrincipal = field(repr=False)
    action: str = field(repr=False)
    echo: ScopeApiEcho

    def __post_init__(self) -> None:
        if type(self.scope) is not SessionScope:
            raise ValueError("scope must be a SessionScope")
        if type(self.relation_scope) is not RelationScope:
            raise ValueError("relation_scope must be a RelationScope")
        if (
            self.relation_scope.bot_ref != self.scope.bot_ref
            or self.relation_scope.persona_ref != self.scope.persona_ref
        ):
            raise ValueError("relation scope does not belong to session scope")
        if type(self.turn_generation) is not int or self.turn_generation < 0:
            raise ValueError("turn_generation must be a non-negative int")
        if type(self.expires_at_ms) is not int or self.expires_at_ms < 0:
            raise ValueError("expires_at_ms must be a non-negative int")
        if type(self.principal) is not ScopedPrincipal:
            raise ValueError("principal must be a ScopedPrincipal")
        if type(self.action) is not str or self.action not in {
            _scoped_action(endpoint, method)
            for endpoint, method in SCOPED_API_METHODS.items()
        }:
            raise ValueError("action must be a supported scoped API action")
        if type(self.echo) is not ScopeApiEcho:
            raise ValueError("echo must be a ScopeApiEcho")

    def public_payload(self) -> dict[str, object]:
        """Return only opaque references and redacted scope availability."""

        payload: dict[str, object] = {
            "ok": True,
            "scope": {
                "bot_ref": self.echo.scope.bot_ref,
                "persona_ref": self.echo.scope.persona_ref,
                "session_ref": self.echo.scope.session_ref,
            },
            "scope_generation": self.echo.scope_generation,
            "resolved_at_ms": self.echo.resolved_at_ms,
            "status": "available",
        }
        generations = {
            "bot": self.echo.bot_generation,
            "persona_lifecycle": self.echo.persona_lifecycle_generation,
            "session": self.echo.session_generation,
            "relation": self.echo.relation_generation,
            "scope": self.echo.scope_generation,
            "turn": self.echo.turn_generation,
        }
        if all(value is not None for value in generations.values()):
            payload["generations"] = generations
        return payload


@dataclass(frozen=True, slots=True)
class _NonceRecord:
    scope: SessionScope
    relation_scope: RelationScope
    turn_generation: int
    expires_at_ms: int
    principal: ScopedPrincipal
    action: str


class ScopedApiService:
    """One shared exact resolver, nonce issuer, and generation fence.

    ``turn_lookup`` and the locked turn fence are deliberately supplied by the
    host.  Production passes ``SessionCatalog.current_exact`` for normal
    checks and ``turn_fence_locked`` for the final claim transaction; the
    service never scans a catalog or invents a transport owner itself.
    """

    def __init__(
        self,
        repository: ScopeRepository,
        registry: ScopeRuntimeRegistry,
        *,
        turn_lookup: Callable[[SessionScope], object | None],
        turn_fence_locked: Callable[[SessionScope, int], bool] | None = None,
        clock_ms: Callable[[], int] | None = None,
        nonce_ttl_ms: int = _NONCE_TTL_MS,
        principal_scope_grant: PrincipalScopeGrant | None = None,
        principal_persona_grant: PrincipalPersonaGrant | None = None,
    ) -> None:
        if type(repository) is not ScopeRepository:
            raise ValueError("repository must be a ScopeRepository")
        if type(registry) is not ScopeRuntimeRegistry:
            raise ValueError("registry must be a ScopeRuntimeRegistry")
        if not callable(turn_lookup):
            raise ValueError("turn_lookup must be callable")
        if turn_fence_locked is not None and not callable(turn_fence_locked):
            raise ValueError("turn_fence_locked must be callable or None")
        if type(nonce_ttl_ms) is not int or nonce_ttl_ms <= 0:
            raise ValueError("nonce_ttl_ms must be a positive int")
        if principal_scope_grant is not None and not callable(principal_scope_grant):
            raise ValueError("principal_scope_grant must be callable or None")
        if principal_persona_grant is not None and not callable(principal_persona_grant):
            raise ValueError("principal_persona_grant must be callable or None")
        self._repository = repository
        self._registry = registry
        self._turn_lookup = turn_lookup
        self._turn_fence_locked = turn_fence_locked
        self._clock_ms = clock_ms or _now_ms
        self._nonce_ttl_ms = nonce_ttl_ms
        self._principal_scope_grant = principal_scope_grant
        self._principal_persona_grant = principal_persona_grant
        self._lock = threading.RLock()
        self._pending_nonces: dict[str, _NonceRecord] = {}
        self._retired_nonces: dict[str, tuple[int, str]] = {}

    def catalog_payload(self) -> dict[str, object] | ScopedApiError:
        """Return the redacted, authoritative catalog of live exact scopes."""

        try:
            scopes = self._repository.list_active_scopes()
        except (OSError, RepositoryCorruptionError, TypeError, ValueError):
            return ScopedApiError(503, "scope_repository_unavailable")
        entries: list[dict[str, object]] = []
        for scope in scopes:
            if not self._registry.is_live_session(scope):
                continue
            entries.append(
                {
                    "scope": {
                        "bot_ref": scope.bot_ref.token,
                        "persona_ref": scope.persona_ref.token,
                        "session_ref": scope.session_ref.token,
                    },
                    "generations": {
                        "bot": scope.bot_ref.generation,
                        "persona_lifecycle": scope.persona_ref.lifecycle_generation,
                        "session": scope.session_ref.generation,
                        "scope": scope.scope_generation,
                    },
                }
            )
        return {"ok": True, "scopes": entries}

    def persona_dossier_payload(
        self,
        bot_ref: object,
        persona_ref: object,
        *,
        principal: ScopedPrincipal | None = None,
    ) -> dict[str, object] | ScopedApiError:
        """Project one authorized active Persona without selecting a Session."""

        try:
            path = PersonaApiPathEcho(bot_ref=bot_ref, persona_ref=persona_ref)
        except ValueError:
            return ScopedApiError(400, "invalid_persona_request")
        if type(principal) is not ScopedPrincipal:
            return ScopedApiError(403, "scope_principal_required")
        persona_scope = self.resolve_persona(path.bot_ref, path.persona_ref)
        if isinstance(persona_scope, ScopedApiError):
            return persona_scope
        authorization = self._authorize_persona_dossier(principal, persona_scope)
        if isinstance(authorization, ScopedApiError):
            return authorization
        try:
            dossier = self._repository.read_persona_dossier(path.bot_ref, path.persona_ref)
        except (KeyError, StaleScopeWrite):
            return self._stale_error()
        except (OSError, RepositoryCorruptionError, TypeError, ValueError):
            return ScopedApiError(503, "scope_repository_unavailable")

        active = dossier.persona_ref
        if active.bot_ref != persona_scope.bot_ref or active != persona_scope.persona_ref:
            return self._stale_error()
        authorization = self._authorize_persona_dossier(principal, persona_scope)
        if isinstance(authorization, ScopedApiError):
            return authorization

        genesis: dict[str, object] = {"state": "awaiting"}
        genesis_snapshot = dossier.genesis
        genesis_payload = None if genesis_snapshot is None else genesis_snapshot.payload
        if type(genesis_payload) is dict and genesis_payload.get("state") == "active":
            profile = genesis_payload.get("accepted_profile")
            metadata = genesis_payload.get("safe_metadata")
            accepted_at_ms = metadata.get("accepted_at_ms") if type(metadata) is dict else None
            if (
                type(profile) is dict
                and genesis_payload.get("growth_enabled") is True
                and type(accepted_at_ms) is int
                and accepted_at_ms >= 0
            ):
                genesis = {
                    "state": "active",
                    "priors": profile,
                    "growth_enabled": True,
                    "accepted_at_ms": accepted_at_ms,
                }

        short_ref = active.token[-8:]
        echo = PersonaApiEcho(
            scope=PersonaApiPathEcho(
                bot_ref=active.bot_ref.token,
                persona_ref=active.token,
            ),
            scope_generation=active.lifecycle_generation,
            resolved_at_ms=self._clock_ms(),
        )
        return {
            "ok": True,
            "scope": {
                "bot_ref": echo.scope.bot_ref,
                "persona_ref": echo.scope.persona_ref,
            },
            "scope_generation": echo.scope_generation,
            "resolved_at_ms": echo.resolved_at_ms,
            "generations": {
                "bot": active.bot_ref.generation,
                "persona_lifecycle": active.lifecycle_generation,
            },
            "persona": {
                "display": f"Persona {short_ref}",
                "ref_short": short_ref,
                "fingerprint_short": active.source_fingerprint[-12:],
                "resolution": "active",
                "genesis": genesis,
                "updated_at_ms": dossier.updated_at_ms,
            },
        }

    def resolve_persona(
        self,
        bot_ref: object,
        persona_ref: object,
    ) -> PersonaScope | ScopedApiError:
        """Resolve one exact active Persona without selecting a Session sibling."""

        try:
            path = PersonaApiPathEcho(bot_ref=bot_ref, persona_ref=persona_ref)
        except ValueError:
            return ScopedApiError(400, "invalid_persona_request")
        try:
            active = self._repository.resolve_exact_persona(
                path.bot_ref,
                path.persona_ref,
            )
        except ScopeBotNotFound:
            return ScopedApiError(404, "scope_bot_not_found")
        except ScopeParentMismatch:
            return ScopedApiError(403, "scope_persona_not_owned")
        except ScopePersonaNotFound:
            return ScopedApiError(404, "scope_persona_not_found")
        except StaleScopeWrite:
            return self._stale_error()
        except (OSError, RepositoryCorruptionError, TypeError, ValueError):
            return ScopedApiError(503, "scope_repository_unavailable")
        return PersonaScope(bot_ref=active.bot_ref, persona_ref=active)

    def resolve(
        self,
        bot_ref: object,
        persona_ref: object,
        session_ref: object,
    ) -> SessionScope | ScopedApiError:
        """Resolve only the requested parent chain; never select a sibling scope."""

        try:
            path = ScopeApiPathEcho(
                bot_ref=bot_ref,
                persona_ref=persona_ref,
                session_ref=session_ref,
            )
        except ValueError:
            return ScopedApiError(400, "invalid_scoped_request")
        try:
            return self._repository.resolve_exact_scope(
                path.bot_ref,
                path.persona_ref,
                path.session_ref,
            )
        except KeyError:
            return self._missing_parent_error(path)
        except StaleScopeWrite:
            return self._stale_error()
        except (OSError, RepositoryCorruptionError, TypeError, ValueError):
            return ScopedApiError(503, "scope_repository_unavailable")

    def bootstrap_nonce(
        self,
        path: ScopeApiPathEcho,
        *,
        principal: ScopedPrincipal | None = None,
        endpoint: str = "scope",
        method: str = "GET",
    ) -> str | ScopedApiError:
        """Mint or refresh one nonce for a live, uniquely owned exact scope."""

        if type(path) is not ScopeApiPathEcho:
            return ScopedApiError(400, "invalid_scoped_request")
        try:
            authenticated_principal = _require_principal(principal)
            route = ScopeRouteSpec(endpoint=endpoint, method=method)
        except ValueError:
            if principal is None:
                return ScopedApiError(403, "scope_principal_required")
            return ScopedApiError(400, "invalid_scoped_request")
        scope = self.resolve(path.bot_ref, path.persona_ref, path.session_ref)
        if isinstance(scope, ScopedApiError):
            return scope
        relation_scope = self._principal_grant(
            authenticated_principal,
            scope,
            route.action,
        )
        if relation_scope is None:
            return ScopedApiError(403, "scope_principal_forbidden")
        if not self._registry.is_live_session(scope):
            return ScopedApiError(410, "scope_required")
        try:
            turn = self._turn_lookup(scope)
        except KeyError:
            return ScopedApiError(410, "scope_required")
        except (OSError, RepositoryCorruptionError):
            return ScopedApiError(503, "scope_repository_unavailable")
        except Exception:  # noqa: BLE001 - host lookup must fail closed
            return ScopedApiError(410, "scope_required")
        turn_generation = getattr(turn, "turn_generation", None)
        if type(turn_generation) is not int:
            return ScopedApiError(410, "scope_required")
        try:
            return self.issue_nonce(
                scope,
                relation_scope,
                turn_generation=turn_generation,
                principal=authenticated_principal,
                endpoint=route.endpoint,
                method=route.method,
            )
        except RuntimeError as exc:
            if str(exc) == "scope_principal_forbidden":
                return ScopedApiError(403, "scope_principal_forbidden")
            return ScopedApiError(410, "scope_required")

    def issue_nonce(
        self,
        scope: SessionScope,
        relation_scope: RelationScope,
        *,
        turn_generation: int,
        principal: ScopedPrincipal,
        endpoint: str = "state",
        method: str = "GET",
    ) -> str:
        """Mint one opaque bearer capability after exact live-scope validation."""

        record = self._validated_record(
            scope,
            relation_scope,
            turn_generation,
            principal=_require_principal(principal),
            action=_scoped_action(endpoint, method),
        )
        nonce = f"{_NONCE_PREFIX}{secrets.token_urlsafe(24)}"
        with self._lock:
            self._purge_expired_locked(self._clock_ms())
            self._pending_nonces[nonce] = record
        return nonce

    def authorize(
        self,
        request: ScopedApiRequest,
    ) -> ScopedApiAuthorization | ScopedApiError:
        """Consume one scope nonce and resolve only its exact token triple."""

        if type(request) is not ScopedApiRequest:
            return ScopedApiError(400, "invalid_scoped_request")
        if request.nonce is None:
            return ScopedApiError(400, "scope_nonce_required")
        if not _is_shaped_nonce(request.nonce, _NONCE_PREFIX):
            return ScopedApiError(400, "invalid_scope_nonce")
        if request.principal is None:
            return ScopedApiError(403, "scope_principal_required")
        now_ms = self._clock_ms()
        with self._lock:
            self._purge_expired_locked(now_ms)
            record = self._pending_nonces.pop(request.nonce, None)
            if record is None:
                retired = self._retired_nonces.get(request.nonce)
                code = "scope_nonce_invalid" if retired is None else retired[1]
                return ScopedApiError(403, code)
            self._retired_nonces[request.nonce] = (
                record.expires_at_ms,
                "scope_nonce_replayed",
            )
        if not self._path_matches(request.path, record.scope):
            # Reject before repository lookup so a sibling path cannot reveal
            # whether any of its opaque tokens exist.
            return ScopedApiError(403, "scope_nonce_mismatch")
        if (
            _require_principal(request.principal) != record.principal
            or _scoped_action(request.endpoint, request.method) != record.action
        ):
            # This token is already retired above. A mismatched request must
            # never consult a scope, relation, or transport runtime.
            return ScopedApiError(409, "scope_nonce_binding_mismatch")
        return self._authorize_record(record, now_ms)

    def revalidate(
        self,
        authorization: ScopedApiAuthorization,
    ) -> ScopedApiAuthorization | ScopedApiError:
        """Re-check every fence before an SSE or WebSocket send."""

        if type(authorization) is not ScopedApiAuthorization:
            return ScopedApiError(400, "invalid_scoped_authorization")
        if self._clock_ms() > authorization.expires_at_ms:
            return self._stale_error()
        record = _NonceRecord(
            scope=authorization.scope,
            relation_scope=authorization.relation_scope,
            turn_generation=authorization.turn_generation,
            expires_at_ms=authorization.expires_at_ms,
            principal=authorization.principal,
            action=authorization.action,
        )
        result = self._authorize_record(record, self._clock_ms(), stream=True)
        return authorization if isinstance(result, ScopedApiAuthorization) else result

    def runtime_fence(self, authorization: ScopedApiAuthorization) -> bool:
        """Check final runtime state while the caller already owns repository lock.

        ``LegacyScopeClaimService.claim_memory`` invokes this from its existing
        repository transaction.  The runtime registry is an in-process fast
        fence only; the locked catalog fence validates frozen active scope and
        protected binding, including a newer turn committed by another process.
        """

        if type(authorization) is not ScopedApiAuthorization:
            return False
        try:
            if self._clock_ms() > authorization.expires_at_ms:
                return False
            if not self._registry.is_live_session(authorization.scope):
                return False
            if self._registry.relation_or_none(authorization.relation_scope) is None:
                return False
            if not self._registry.matches_published_turn(
                authorization.scope,
                authorization.turn_generation,
            ):
                return False
            fence_locked = self._turn_fence_locked
            if not callable(fence_locked):
                return False
            return fence_locked(
                authorization.scope,
                authorization.turn_generation,
            ) is True
        except (RepositoryCorruptionError, OSError) as exc:
            raise ScopedApiRuntimeUnavailable("locked runtime authority unavailable") from exc
        except Exception:  # noqa: BLE001 - runtime authority must fail closed
            return False

    def stream_stale_payload(self) -> dict[str, object]:
        """Return the sole marker a streaming host may emit before closing."""

        return {"event": "scope_stale", "data": {"error": "scope_stale"}}

    def _authorize_record(
        self,
        record: _NonceRecord,
        now_ms: int,
        *,
        stream: bool = False,
    ) -> ScopedApiAuthorization | ScopedApiError:
        if now_ms > record.expires_at_ms:
            return self._stale_error() if stream else ScopedApiError(403, "scope_nonce_expired")
        try:
            resolved = self._repository.resolve_exact_scope(
                record.scope.bot_ref.token,
                record.scope.persona_ref.token,
                record.scope.session_ref.token,
            )
        except KeyError:
            # A record can only be issued after the scope existed.  Its later
            # disappearance is a generation fence, never an existence probe.
            return self._stale_error()
        except StaleScopeWrite:
            return self._stale_error()
        except (OSError, RepositoryCorruptionError):
            return ScopedApiError(503, "scope_repository_unavailable")
        except (TypeError, ValueError):
            return ScopedApiError(503, "scope_repository_unavailable")
        if resolved != record.scope:
            return self._stale_error()
        grant = self._principal_grant(record.principal, resolved, record.action)
        if grant is None or grant != record.relation_scope:
            return ScopedApiError(403, "scope_principal_forbidden")
        try:
            self._repository.validate_relation_scope(record.relation_scope)
        except StaleScopeWrite:
            return self._stale_error()
        except (OSError, RepositoryCorruptionError, TypeError, ValueError):
            return ScopedApiError(503, "scope_repository_unavailable")
        if (
            record.relation_scope.bot_ref != resolved.bot_ref
            or record.relation_scope.persona_ref != resolved.persona_ref
        ):
            return self._stale_error()
        if not self._registry.is_live_session(resolved):
            return self._stale_error() if stream else ScopedApiError(410, "scope_required")
        try:
            relation_runtime = self._registry.relation_or_none(record.relation_scope)
        except Exception:  # noqa: BLE001 - private runtime must fail closed
            relation_runtime = None
        if relation_runtime is None:
            return self._stale_error() if stream else ScopedApiError(410, "scope_required")
        try:
            turn = self._turn_lookup(resolved)
        except KeyError:
            return self._stale_error()
        except (OSError, RepositoryCorruptionError):
            return ScopedApiError(503, "scope_repository_unavailable")
        except Exception:  # noqa: BLE001 - a host lookup cannot disclose details
            return self._stale_error() if stream else ScopedApiError(410, "scope_required")
        if not self._turn_matches(turn, resolved, record.turn_generation):
            return self._stale_error()
        if not self._registry.publish_frozen_turn(
            resolved,
            record.turn_generation,
        ):
            return self._stale_error()
        return ScopedApiAuthorization(
            scope=resolved,
            relation_scope=record.relation_scope,
            turn_generation=record.turn_generation,
            expires_at_ms=record.expires_at_ms,
            principal=record.principal,
            action=record.action,
            echo=ScopeApiEcho(
                scope=ScopeApiPathEcho(
                    bot_ref=resolved.bot_ref.token,
                    persona_ref=resolved.persona_ref.token,
                    session_ref=resolved.session_ref.token,
                ),
                scope_generation=resolved.scope_generation,
                resolved_at_ms=now_ms,
                bot_generation=resolved.bot_ref.generation,
                persona_lifecycle_generation=(
                    resolved.persona_ref.lifecycle_generation
                ),
                session_generation=resolved.session_ref.generation,
                relation_generation=record.relation_scope.relation_generation,
                turn_generation=record.turn_generation,
            ),
        )

    def _validated_record(
        self,
        scope: SessionScope,
        relation_scope: RelationScope,
        turn_generation: int,
        *,
        principal: ScopedPrincipal,
        action: str,
    ) -> _NonceRecord:
        if type(scope) is not SessionScope:
            raise ValueError("scope must be a SessionScope")
        if type(relation_scope) is not RelationScope:
            raise ValueError("relation_scope must be a RelationScope")
        if type(turn_generation) is not int or turn_generation < 0:
            raise ValueError("turn_generation must be a non-negative int")
        if type(principal) is not ScopedPrincipal:
            raise ValueError("principal must be a ScopedPrincipal")
        if type(action) is not str or action not in {
            _scoped_action(endpoint, method)
            for endpoint, method in SCOPED_API_METHODS.items()
        }:
            raise ValueError("action must be a supported scoped API action")
        if (
            relation_scope.bot_ref != scope.bot_ref
            or relation_scope.persona_ref != scope.persona_ref
        ):
            raise ValueError("relation scope does not belong to session scope")
        now_ms = self._clock_ms()
        record = _NonceRecord(
            scope=scope,
            relation_scope=relation_scope,
            turn_generation=turn_generation,
            expires_at_ms=now_ms + self._nonce_ttl_ms,
            principal=principal,
            action=action,
        )
        validated = self._authorize_record(record, now_ms)
        if isinstance(validated, ScopedApiError):
            raise RuntimeError(validated.code)
        return record

    @staticmethod
    def _path_matches(path: ScopeApiPathEcho, scope: SessionScope) -> bool:
        return (
            path.bot_ref == scope.bot_ref.token
            and path.persona_ref == scope.persona_ref.token
            and path.session_ref == scope.session_ref.token
        )

    def _principal_grant(
        self,
        principal: ScopedPrincipal,
        scope: SessionScope,
        action: str,
    ) -> RelationScope | None:
        """Return one live-authority candidate, failing closed on every ambiguity."""

        grant_issuer = self._principal_scope_grant
        if not callable(grant_issuer):
            return None
        try:
            grant = grant_issuer(principal, scope, action)
        except Exception:  # noqa: BLE001 - external identity proof must fail closed
            return None
        if (
            type(grant) is not RelationScope
            or grant.bot_ref != scope.bot_ref
            or grant.persona_ref != scope.persona_ref
        ):
            return None
        return grant

    def _persona_grant(
        self,
        principal: ScopedPrincipal,
        scope: PersonaScope,
        action: str,
    ) -> RelationScope | None:
        """Return one exact Persona grant, failing closed on every ambiguity."""

        grant_issuer = self._principal_persona_grant
        if not callable(grant_issuer):
            return None
        try:
            grant = grant_issuer(principal, scope, action)
        except Exception:  # noqa: BLE001 - external identity proof must fail closed
            return None
        if (
            type(grant) is not RelationScope
            or grant.bot_ref != scope.bot_ref
            or grant.persona_ref != scope.persona_ref
        ):
            return None
        return grant

    def _authorize_persona_dossier(
        self,
        principal: ScopedPrincipal,
        scope: PersonaScope,
    ) -> RelationScope | ScopedApiError:
        """Fence the authoritative grant before returning Persona-only data."""

        grant = self._persona_grant(
            principal,
            scope,
            PERSONA_DOSSIER_ROUTE_SPEC.action,
        )
        if grant is None:
            return ScopedApiError(403, "scope_principal_forbidden")
        try:
            self._repository.validate_relation_scope(grant)
        except (KeyError, StaleScopeWrite, ValueError):
            return ScopedApiError(403, "scope_principal_forbidden")
        except (OSError, RepositoryCorruptionError, TypeError):
            return ScopedApiError(503, "scope_repository_unavailable")
        try:
            relation_runtime = self._registry.relation_or_none(grant)
        except Exception:  # noqa: BLE001 - private runtime must fail closed
            relation_runtime = None
        if relation_runtime is None:
            return ScopedApiError(403, "scope_principal_forbidden")
        return grant

    def _missing_parent_error(self, path: ScopeApiPathEcho) -> ScopedApiError:
        """Classify only parent ownership after an exact lookup has missed.

        The catalog is used strictly as an existence/parentage index.  Its
        entries are never selected or returned, so an exact path cannot fall
        back to a sibling Bot, Persona, or Session.
        """

        try:
            scopes = self._repository.list_active_scopes()
        except (OSError, RepositoryCorruptionError, TypeError, ValueError):
            return ScopedApiError(503, "scope_repository_unavailable")
        if not any(scope.bot_ref.token == path.bot_ref for scope in scopes):
            return ScopedApiError(404, "scope_bot_not_found")
        has_requested_persona_parent = any(
            scope.bot_ref.token == path.bot_ref
            and scope.persona_ref.token == path.persona_ref
            for scope in scopes
        )
        if not has_requested_persona_parent:
            if any(scope.persona_ref.token == path.persona_ref for scope in scopes):
                return ScopedApiError(403, "scope_persona_not_owned")
            return ScopedApiError(404, "scope_persona_not_found")
        if any(scope.session_ref.token == path.session_ref for scope in scopes):
            return ScopedApiError(403, "scope_session_not_owned")
        return ScopedApiError(404, "scope_session_not_found")

    @staticmethod
    def _turn_matches(
        turn: object | None,
        scope: SessionScope,
        turn_generation: int,
    ) -> bool:
        return bool(
            turn is not None
            and getattr(turn, "bot_ref", None) == scope.bot_ref.token
            and getattr(turn, "session_ref", None) == scope.session_ref.token
            and getattr(turn, "session_generation", None) == scope.session_ref.generation
            and getattr(turn, "turn_generation", None) == turn_generation
            and getattr(turn, "turn_state", None) == "frozen"
            and getattr(turn, "active_persona_ref", None) == scope.persona_ref.token
            and getattr(turn, "persona_lifecycle_generation", None)
            == scope.persona_ref.lifecycle_generation
            and getattr(turn, "active_scope_token", None) == scope.storage_token
            and getattr(turn, "scope_generation", None) == scope.scope_generation
        )

    @staticmethod
    def _stale_error() -> ScopedApiError:
        return ScopedApiError(409, "scope_stale", websocket_close_code=4409)

    def _purge_expired_locked(self, now_ms: int) -> None:
        for pending, retired, expired_code in (
            (self._pending_nonces, self._retired_nonces, "scope_nonce_expired"),
        ):
            for nonce, record in tuple(pending.items()):
                if record.expires_at_ms < now_ms:
                    pending.pop(nonce, None)
                    retired[nonce] = (record.expires_at_ms, expired_code)
            for nonce, (expires_at_ms, _code) in tuple(retired.items()):
                if expires_at_ms + self._nonce_ttl_ms < now_ms:
                    retired.pop(nonce, None)


def scoped_api_service_for_plugin(plugin: object) -> ScopedApiService | None:
    """Return the sole host-shared service without creating a private runtime.

    A WebUI request is not allowed to lazily resolve a Persona, relation, or
    transport turn.  The function therefore accepts only a resolver and runtime
    registry that were already published by the normal message lifecycle.
    """

    existing = getattr(plugin, "_scoped_api_service", None)
    if type(existing) is ScopedApiService:
        return (
            existing
            if (
                callable(existing._principal_scope_grant)
                and callable(existing._principal_persona_grant)
            )
            else None
        )
    registry = getattr(plugin, "_scope_runtime_registry", None)
    resolver = getattr(plugin, "_scope_resolver_v1", None)
    repository = getattr(resolver, "_repository", None)
    catalog = getattr(resolver, "catalog", None)
    current_exact = getattr(catalog, "current_exact", None)
    catalog_turn_fence_locked = getattr(catalog, "turn_fence_locked", None)
    principal_scope_grant = getattr(plugin, "_scoped_api_principal_scope_grant", None)
    principal_persona_grant = getattr(plugin, "_scoped_api_principal_persona_grant", None)
    if (
        type(registry) is not ScopeRuntimeRegistry
        or type(repository) is not ScopeRepository
        or registry.repository is not repository
        or not callable(current_exact)
        or not callable(principal_scope_grant)
        or not callable(principal_persona_grant)
    ):
        return None

    def turn_lookup(scope: SessionScope) -> object | None:
        return current_exact(scope.bot_ref.token, scope.session_ref.token)

    turn_fence_locked: Callable[[SessionScope, int], bool] | None = None
    if (
        getattr(catalog, "repository", None) is repository
        and callable(catalog_turn_fence_locked)
    ):
        def turn_fence_locked(scope: SessionScope, generation: int) -> bool:
            return catalog_turn_fence_locked(scope, generation) is True

    service = ScopedApiService(
        repository,
        registry,
        turn_lookup=turn_lookup,
        turn_fence_locked=turn_fence_locked,
        principal_scope_grant=principal_scope_grant,
        principal_persona_grant=principal_persona_grant,
    )
    try:
        setattr(plugin, "_scoped_api_service", service)
    except Exception:  # noqa: BLE001 - immutable test/plugin facades may still use it
        pass
    return service


def issue_scoped_api_nonce_for_binding(
    service: object,
    binding: object,
) -> str | None:
    """Mint a UI nonce only from the current frozen runtime binding.

    This is intentionally not a path-based bootstrap.  The caller must already
    hold the request-local relation runtime produced by the authenticated
    transport flow, so an HTTP client cannot manufacture a relation selector.
    """

    if type(service) is not ScopedApiService:
        return None
    scope = getattr(binding, "scope", None)
    relation_runtime = getattr(binding, "relation_runtime", None)
    relation_scope = getattr(relation_runtime, "scope", None)
    turn_generation = getattr(binding, "turn_generation", None)
    principal = getattr(binding, "principal", None)
    if (
        type(scope) is not SessionScope
        or type(relation_scope) is not RelationScope
        or type(turn_generation) is not int
        or type(principal) is not ScopedPrincipal
    ):
        return None
    try:
        return service.issue_nonce(
            scope,
            relation_scope,
            turn_generation=turn_generation,
            principal=principal,
        )
    except Exception:  # noqa: BLE001 - an unavailable private scope mints nothing
        return None


__all__ = [
    "SCOPED_API_ENDPOINTS",
    "SCOPED_API_METHODS",
    "SCOPED_API_ROUTE_SPECS",
    "SCOPED_API_ROOT",
    "PERSONA_DOSSIER_ROUTE_SPEC",
    "SCOPE_NONCE_HEADER",
    "PersonaRouteSpec",
    "PrincipalPersonaGrant",
    "PrincipalScopeGrant",
    "ScopeRouteSpec",
    "ScopedApiAuthorization",
    "ScopedApiError",
    "ScopedApiRequest",
    "ScopedApiRuntimeUnavailable",
    "ScopedApiService",
    "issue_scoped_api_nonce_for_binding",
    "scoped_api_service_for_plugin",
    "scoped_api_path",
    "scoped_api_route_spec",
]
