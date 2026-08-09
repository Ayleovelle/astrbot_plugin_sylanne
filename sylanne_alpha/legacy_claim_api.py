"""Small host-neutral adapter for ACL-fenced legacy inventory and copy claims."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from typing import Any

from .legacy_claim_authority import LEGACY_CLAIM_ACTION, LegacyClaimAuthority, LegacyClaimIntent
from .legacy_scope_claim import (
    LegacyClaimAuthorizationDenied,
    LegacyClaimConflict,
    LegacyClaimQuarantined,
    LegacyScopeClaimService,
)
from .scope_contracts import RelationScope, ScopeApiPathEcho, ScopedPrincipal, SessionScope


@dataclass(frozen=True, slots=True)
class LegacyClaimApiError:
    status: int
    code: str

    def public_payload(self) -> dict[str, str]:
        return {"error": self.code}


class LegacyClaimApi:
    """Expose only redacted projections; route adapters own body/nonce parsing."""

    def __init__(self, authority: LegacyClaimAuthority, claims: Any) -> None:
        if type(authority) is not LegacyClaimAuthority:
            raise ValueError("authority must be a LegacyClaimAuthority")
        self.authority = authority
        self.claims = claims

    def inventory_payload(self, principal: ScopedPrincipal) -> dict[str, object] | LegacyClaimApiError:
        if type(principal) is not ScopedPrincipal or not self.authority.inventory_view_allowed(principal):
            return LegacyClaimApiError(403, "scope_principal_forbidden")
        try:
            records = self.claims.list_inventory()
        except (LegacyClaimQuarantined, LegacyClaimConflict, OSError, ValueError):
            return LegacyClaimApiError(409, "legacy_claim_unavailable")
        return {
            "ok": True,
            "records": [
                {
                    "record_id": item.record_id,
                    "source_kind": item.source_kind,
                    "checksum": item.checksum,
                    "byte_size": item.byte_size,
                }
                for item in records
            ],
        }

    def preflight(
        self, principal: ScopedPrincipal, record_id: object, path: ScopeApiPathEcho
    ) -> LegacyClaimIntent | LegacyClaimApiError:
        intent = self.authority.preflight_claim(principal, record_id, path)
        return intent if intent is not None else LegacyClaimApiError(403, "scope_principal_forbidden")

    def claim_after_authorization(
        self,
        intent: LegacyClaimIntent,
        *,
        principal: ScopedPrincipal,
        record_id: str,
        scope: SessionScope,
        relation_scope: RelationScope,
        post_lookup_revalidate: Callable[[], bool],
        runtime_fence: Callable[[], bool],
    ) -> dict[str, object] | LegacyClaimApiError:
        if not callable(post_lookup_revalidate) or not callable(runtime_fence):
            return LegacyClaimApiError(409, "scope_stale")
        if not self.authority.revalidate_pre_source(
            intent, principal=principal, record_id=record_id, scope=scope,
            relation_scope=relation_scope, action=LEGACY_CLAIM_ACTION,
        ):
            return LegacyClaimApiError(403, "scope_principal_forbidden")
        try:
            source = self.claims.lookup_memory_source(record_id)
        except (LegacyClaimQuarantined, LegacyClaimConflict, OSError, ValueError):
            return LegacyClaimApiError(409, "legacy_claim_unavailable")
        try:
            if post_lookup_revalidate() is not True:
                return LegacyClaimApiError(409, "scope_stale")
        except Exception:  # noqa: BLE001 - host runtime revalidation fails closed
            return LegacyClaimApiError(409, "scope_stale")
        if not self.authority.revalidate_claim(
            intent, principal=principal, record_id=record_id, scope=scope,
            relation_scope=relation_scope, action=LEGACY_CLAIM_ACTION, actor_id=source.actor_id,
        ):
            return LegacyClaimApiError(403, "scope_principal_forbidden")
        destination = self.claims.issue_destination(scope, actor_id=source.actor_id)
        runtime_stale = False

        def guard() -> bool:
            nonlocal runtime_stale
            try:
                if runtime_fence() is not True:
                    runtime_stale = True
                    return False
                return self.authority.revalidate_claim_locked(
                    intent, principal=principal, record_id=record_id, scope=scope,
                    relation_scope=relation_scope, action=LEGACY_CLAIM_ACTION, actor_id=source.actor_id,
                )
            except Exception:  # noqa: BLE001 - final authorization fence fails closed
                runtime_stale = True
                return False

        try:
            result = self.claims.claim_memory(destination, source, authorization_guard=guard)
        except LegacyClaimAuthorizationDenied:
            return LegacyClaimApiError(
                409 if runtime_stale else 403,
                "scope_stale" if runtime_stale else "scope_principal_forbidden",
            )
        except (LegacyClaimQuarantined, LegacyClaimConflict, OSError, ValueError):
            return LegacyClaimApiError(409, "legacy_claim_unavailable")
        return {
            "ok": True,
            "claim": {
                "record_id": record_id,
                "status": "idempotent" if result.idempotent else "copied",
            },
        }


def legacy_claim_api_for_plugin(plugin: object) -> LegacyClaimApi | None:
    """Return only an existing-resolver repository-backed adapter; never create a resolver."""

    resolver = getattr(plugin, "_scope_resolver_v1", None)
    repository = getattr(resolver, "_repository", None)
    if repository is None:
        return None
    existing = getattr(plugin, "_legacy_claim_api", None)
    if type(existing) is LegacyClaimApi and existing.authority.repository is repository:
        return existing
    try:
        created = LegacyClaimApi(LegacyClaimAuthority(repository), LegacyScopeClaimService(repository))
    except Exception:  # noqa: BLE001 - web host must fail closed
        return None
    plugin._legacy_claim_api = created
    return created


__all__ = ["LegacyClaimApi", "LegacyClaimApiError", "legacy_claim_api_for_plugin"]
