"""Explicit, one-time copy claims for legacy memory snapshots.

This module deliberately has no AstrBot, KV, transport, or ``.alpha.json``
reader.  A caller must submit a concrete memory payload to the owner-only
legacy inventory and then present a service-issued destination capability for
one exact :class:`SessionScope`.  The durable source fingerprint is the only
cross-process claim key; raw legacy identifiers never select an owner.
"""

from __future__ import annotations

import hashlib
import json
import math
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .scope_contracts import SessionScope
from .scope_repository import RepositoryCorruptionError, ScopeRepository, StaleScopeWrite


_SOURCE_SCHEMA = "sylanne.scope.legacy-source.v1"
_QUARANTINE_SCHEMA = "sylanne.scope.legacy-quarantine.v1"
_CAPABILITY_ISSUER = object()
_SOURCE_ISSUER = object()
_MAX_TEXT_BYTES = 4096
_MAX_INVENTORY_LIST_LIMIT = 100


class LegacyScopeClaimError(RuntimeError):
    """A legacy source cannot be copied into the requested scoped owner."""


class LegacyClaimConflict(LegacyScopeClaimError):
    """The durable source fingerprint is already bound incompatibly."""


class LegacyClaimQuarantined(LegacyScopeClaimError):
    """Malformed, drifted, or untrusted input was isolated without a target write."""


@dataclass(frozen=True, slots=True, repr=False)
class LegacyInventorySource:
    """A service-issued handle for one explicitly inventoried source."""

    source_fingerprint: str
    actor_id: str
    source_id: str
    payload_digest: str
    _service_nonce: object = field(repr=False, compare=False)
    _issuer: object = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class LegacyInventoryRecord:
    """Opaque, safe metadata for one verified legacy source."""

    record_id: str
    source_kind: str
    checksum: str
    byte_size: int


@dataclass(frozen=True, slots=True, repr=False)
class LegacyDestinationCapability:
    """Single-use authority for one service instance and frozen SessionScope."""

    scope: SessionScope
    actor_id: str
    capability_id: str
    _service_nonce: object = field(repr=False, compare=False)
    _issuer: object = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class LegacyClaimResult:
    """Durable outcome of one source-to-scope memory copy."""

    source_fingerprint: str
    payload_digest: str
    target_generation: int
    idempotent: bool
    recovered: bool


def _require_text(value: object, name: str) -> str:
    if type(value) is not str:
        raise ValueError(f"{name} must be an exact non-empty str")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError as exc:
        raise ValueError(f"{name} must be an exact non-empty str") from exc
    if not encoded or len(encoded) > _MAX_TEXT_BYTES:
        raise ValueError(f"{name} must be an exact non-empty str")
    return value


def _require_digest(value: object, name: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase sha256 digest")
    return value


def _canonical_json_snapshot(value: object) -> dict[str, object]:
    """Detach exact JSON data without allowing coercion or non-finite values."""

    def normalize(item: object) -> object:
        if item is None or type(item) in (bool, int, str):
            return item
        if type(item) is float:
            if not math.isfinite(item):
                raise ValueError("legacy memory payload contains a non-finite float")
            return item
        if type(item) in (list, tuple):
            return [normalize(child) for child in item]
        if type(item) is dict:
            normalized: dict[str, object] = {}
            for key, child in item.items():
                if type(key) is not str:
                    raise TypeError("legacy memory payload object keys must be exact str")
                normalized[key] = normalize(child)
            return normalized
        raise TypeError(
            "legacy memory payload contains a value that is not JSON-safe: "
            f"{type(item).__qualname__}"
        )

    normalized = normalize(value)
    if type(normalized) is not dict:
        raise TypeError("legacy memory payload must be an exact dict")
    encoded = json.dumps(
        normalized,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    detached = json.loads(encoded)
    if type(detached) is not dict:
        raise RuntimeError("legacy memory payload did not decode to an exact dict")
    return detached


def _canonical_bytes(value: dict[str, object]) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _strict_memory_payload(payload: object) -> tuple[dict[str, object], bytes, str]:
    """Accept only the current complete ``MemorySystem.to_dict`` schema.

    Legacy flexible readers deliberately tolerate old and partial formats.  A
    copy claim is a different boundary: it must not make a malformed legacy
    blob look like a valid scoped memory snapshot.
    """

    normalized = _canonical_json_snapshot(payload)
    expected_fields = {
        "version",
        "tick",
        "last_consolidation_ts",
        "params",
        "l1",
        "l2",
        "l3_nodes",
        "l3_edges",
        "pending_followups",
    }
    if set(normalized) != expected_fields:
        raise ValueError("legacy memory payload has an invalid schema envelope")
    if normalized["version"] != "3.0.0":
        raise ValueError("legacy memory payload has an unsupported schema version")
    if type(normalized["tick"]) is not int or int(normalized["tick"]) < 0:
        raise ValueError("legacy memory payload tick is invalid")
    timestamp = normalized["last_consolidation_ts"]
    if type(timestamp) not in (int, float) or not math.isfinite(float(timestamp)):
        raise ValueError("legacy memory payload consolidation timestamp is invalid")
    if type(normalized["params"]) is not dict:
        raise ValueError("legacy memory payload params is invalid")
    if type(normalized["l1"]) is not list or type(normalized["l2"]) is not list:
        raise ValueError("legacy memory payload layers are invalid")
    if type(normalized["l3_nodes"]) is not dict or type(normalized["l3_edges"]) is not list:
        raise ValueError("legacy memory payload graph is invalid")
    if type(normalized["pending_followups"]) is not list:
        raise ValueError("legacy memory payload followups are invalid")
    if any(type(item) is not dict for item in normalized["l1"]):
        raise ValueError("legacy memory payload l1 items are invalid")
    if any(type(item) is not dict for item in normalized["l2"]):
        raise ValueError("legacy memory payload l2 items are invalid")
    if any(type(item) is not dict for item in normalized["l3_nodes"].values()):
        raise ValueError("legacy memory payload graph nodes are invalid")
    if any(type(item) is not dict for item in normalized["l3_edges"]):
        raise ValueError("legacy memory payload graph edges are invalid")
    if any(type(item) is not dict for item in normalized["pending_followups"]):
        raise ValueError("legacy memory payload followups are invalid")

    # ``MemorySystem`` is the production schema authority.  Its canonical
    # output must exactly match the submitted shape so unknown/additive fields
    # and tolerated malformed records cannot cross this import boundary.
    from .memory_system import MemorySystem

    try:
        restored = MemorySystem.create_from_dict(normalized).to_dict()
    except Exception as exc:  # The input is quarantined by the caller.
        raise ValueError("legacy memory payload cannot be restored strictly") from exc
    if _canonical_bytes(restored) != _canonical_bytes(normalized):
        raise ValueError("legacy memory payload is not a strict current snapshot")
    payload_bytes = _canonical_bytes(normalized)
    return normalized, payload_bytes, _digest(payload_bytes)


def _scope_record(scope: SessionScope) -> dict[str, object]:
    return {
        "storage_token": scope.storage_token,
        "scope_generation": scope.scope_generation,
        "bot_ref": scope.bot_ref.token,
        "bot_generation": scope.bot_ref.generation,
        "persona_ref": scope.persona_ref.token,
        "persona_lifecycle_generation": scope.persona_ref.lifecycle_generation,
        "session_ref": scope.session_ref.token,
        "session_generation": scope.session_ref.generation,
    }


def _result_from_claim(
    fingerprint: str,
    claim: dict[str, object],
    *,
    idempotent: bool,
    recovered: bool,
) -> LegacyClaimResult:
    target_generation = claim.get("target_generation")
    if type(target_generation) is not int or target_generation < 1:
        raise RepositoryCorruptionError("legacy claim target generation is invalid")
    return LegacyClaimResult(
        source_fingerprint=fingerprint,
        payload_digest=_require_digest(claim.get("payload_digest"), "payload_digest"),
        target_generation=target_generation,
        idempotent=idempotent,
        recovered=recovered,
    )


class LegacyScopeClaimService:
    """Own explicit legacy inventory and copy claims for one repository instance."""

    def __init__(
        self,
        repository: ScopeRepository,
        *,
        fault_injector: Callable[[str], None] | None = None,
    ) -> None:
        if type(repository) is not ScopeRepository:
            raise ValueError("repository must be a ScopeRepository")
        if fault_injector is not None and not callable(fault_injector):
            raise ValueError("fault_injector must be callable or None")
        self._repository = repository
        self._fault_injector = fault_injector
        self._service_nonce = object()
        self._capability_lock = threading.Lock()
        self._issued_destinations: dict[str, LegacyDestinationCapability] = {}
        self._used_destination_ids: set[str] = set()

    @property
    def repository(self) -> ScopeRepository:
        return self._repository

    def _fault(self, point: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector(point)

    def _issue_source(
        self,
        *,
        fingerprint: str,
        actor_id: str,
        source_id: str,
        payload_digest: str,
    ) -> LegacyInventorySource:
        return LegacyInventorySource(
            source_fingerprint=fingerprint,
            actor_id=actor_id,
            source_id=source_id,
            payload_digest=payload_digest,
            _service_nonce=self._service_nonce,
            _issuer=_SOURCE_ISSUER,
        )

    def _require_source(self, source: object) -> LegacyInventorySource:
        if (
            type(source) is not LegacyInventorySource
            or source._issuer is not _SOURCE_ISSUER
            or source._service_nonce is not self._service_nonce
        ):
            raise LegacyClaimQuarantined("legacy source was not issued by this service")
        _require_digest(source.source_fingerprint, "source_fingerprint")
        _require_digest(source.payload_digest, "payload_digest")
        _require_text(source.actor_id, "actor_id")
        _require_text(source.source_id, "source_id")
        return source

    def issue_destination(
        self,
        scope: SessionScope,
        *,
        actor_id: str,
    ) -> LegacyDestinationCapability:
        """Issue one process-local, single-use authority for an exact scope."""

        if type(scope) is not SessionScope:
            raise ValueError("scope must be a SessionScope")
        actor = _require_text(actor_id, "actor_id")
        capability = LegacyDestinationCapability(
            scope=scope,
            actor_id=actor,
            capability_id=secrets.token_urlsafe(32),
            _service_nonce=self._service_nonce,
            _issuer=_CAPABILITY_ISSUER,
        )
        with self._capability_lock:
            self._issued_destinations[capability.capability_id] = capability
        return capability

    def _consume_destination(
        self,
        capability: object,
    ) -> LegacyDestinationCapability:
        if (
            type(capability) is not LegacyDestinationCapability
            or capability._issuer is not _CAPABILITY_ISSUER
            or capability._service_nonce is not self._service_nonce
        ):
            raise LegacyClaimQuarantined("legacy destination was not issued by this service")
        with self._capability_lock:
            if self._issued_destinations.get(capability.capability_id) is not capability:
                raise LegacyClaimQuarantined("legacy destination capability is unknown")
            if capability.capability_id in self._used_destination_ids:
                raise LegacyClaimConflict("legacy destination capability is single-use")
            self._used_destination_ids.add(capability.capability_id)
        return capability

    @staticmethod
    def _inventory_record(
        *,
        actor_id: str,
        source_id: str,
        fingerprint: str,
        payload_digest: str,
    ) -> dict[str, object]:
        return {
            "actor_id": actor_id,
            "source_id": source_id,
            "payload_digest": payload_digest,
            "source_path": f"sources/{fingerprint}.json",
        }

    @staticmethod
    def _source_document(
        *,
        actor_id: str,
        source_id: str,
        fingerprint: str,
        payload_digest: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        return {
            "schema_version": _SOURCE_SCHEMA,
            "source_fingerprint": fingerprint,
            "actor_id": actor_id,
            "source_id": source_id,
            "payload_digest": payload_digest,
            "payload": payload,
        }

    @staticmethod
    def _next_manifest(
        manifest: dict[str, object],
        *,
        inventory: dict[str, object] | None = None,
        claims: dict[str, object] | None = None,
    ) -> dict[str, object]:
        generation = manifest.get("generation")
        if type(generation) is not int or generation < 0:
            raise RepositoryCorruptionError("legacy unscoped manifest generation is invalid")
        current_inventory = manifest.get("inventory")
        current_claims = manifest.get("claims")
        if type(current_inventory) is not dict or type(current_claims) is not dict:
            raise RepositoryCorruptionError("legacy unscoped manifest collections are invalid")
        return {
            "schema_version": "sylanne.scope.legacy-unscoped.v1",
            "generation": generation + 1,
            "inventory": dict(current_inventory) if inventory is None else inventory,
            "claims": dict(current_claims) if claims is None else claims,
        }

    def _quarantine_locked(
        self,
        *,
        reason: str,
        fingerprint: str | None = None,
        actor_id: str | None = None,
        source_id: str | None = None,
        payload_digest: str | None = None,
    ) -> None:
        document: dict[str, object] = {
            "schema_version": _QUARANTINE_SCHEMA,
            "reason": _require_text(reason, "reason"),
            "recorded_at_ms": time.time_ns() // 1_000_000,
        }
        if fingerprint is not None:
            document["source_fingerprint"] = _require_digest(
                fingerprint,
                "source_fingerprint",
            )
        if actor_id is not None:
            document["actor_id"] = _require_text(actor_id, "actor_id")
        if source_id is not None:
            document["source_id"] = _require_text(source_id, "source_id")
        if payload_digest is not None:
            document["payload_digest"] = _require_digest(
                payload_digest,
                "payload_digest",
            )
        self._repository._write_legacy_unscoped_quarantine_locked(document)

    def _verified_inventory_locked(
        self,
        source: LegacyInventorySource,
    ) -> tuple[dict[str, object], dict[str, object], bytes]:
        """Validate the manifest and immutable source before any target write."""

        manifest = self._repository._read_legacy_unscoped_manifest_locked()
        inventory = manifest["inventory"]
        if type(inventory) is not dict:
            raise RepositoryCorruptionError("legacy inventory is invalid")
        record = inventory.get(source.source_fingerprint)
        expected_record = self._inventory_record(
            actor_id=source.actor_id,
            source_id=source.source_id,
            fingerprint=source.source_fingerprint,
            payload_digest=source.payload_digest,
        )
        if record != expected_record:
            raise LegacyClaimConflict("legacy inventory record conflicts with source handle")
        loaded = self._repository._read_legacy_unscoped_source_locked(
            source.source_fingerprint,
        )
        if loaded is None:
            raise RepositoryCorruptionError("legacy inventory source is missing")
        raw, document = loaded
        expected_fields = {
            "schema_version",
            "source_fingerprint",
            "actor_id",
            "source_id",
            "payload_digest",
            "payload",
        }
        if set(document) != expected_fields or raw != _canonical_bytes(document):
            raise RepositoryCorruptionError("legacy inventory source is invalid")
        if (
            document["schema_version"] != _SOURCE_SCHEMA
            or document["source_fingerprint"] != source.source_fingerprint
            or document["actor_id"] != source.actor_id
            or document["source_id"] != source.source_id
            or document["payload_digest"] != source.payload_digest
        ):
            raise LegacyClaimConflict("legacy inventory source drifted")
        payload, payload_bytes, payload_digest = _strict_memory_payload(document["payload"])
        if (
            payload_digest != source.payload_digest
            or payload_digest != source.source_fingerprint
        ):
            raise LegacyClaimConflict("legacy inventory content digest drifted")
        return manifest, payload, payload_bytes

    def inventory_memory(
        self,
        *,
        actor_id: str,
        source_id: str,
        payload: object,
    ) -> LegacyInventorySource:
        """Store one caller-supplied source; never discover legacy data implicitly."""

        actor = _require_text(actor_id, "actor_id")
        source_name = _require_text(source_id, "source_id")
        try:
            memory, payload_bytes, fingerprint = _strict_memory_payload(payload)
        except (TypeError, ValueError) as exc:
            with self._repository.transaction():
                self._quarantine_locked(
                    reason="malformed_source",
                    actor_id=actor,
                    source_id=source_name,
                )
            raise LegacyClaimQuarantined("legacy source is not a strict memory snapshot") from exc

        record = self._inventory_record(
            actor_id=actor,
            source_id=source_name,
            fingerprint=fingerprint,
            payload_digest=fingerprint,
        )
        document = self._source_document(
            actor_id=actor,
            source_id=source_name,
            fingerprint=fingerprint,
            payload_digest=fingerprint,
            payload=memory,
        )
        with self._repository.transaction():
            try:
                manifest = self._repository._read_legacy_unscoped_manifest_locked()
                inventory = manifest["inventory"]
                if type(inventory) is not dict:
                    raise RepositoryCorruptionError("legacy inventory is invalid")
                existing = inventory.get(fingerprint)
                loaded = self._repository._read_legacy_unscoped_source_locked(fingerprint)
                if existing is not None:
                    if existing != record:
                        self._quarantine_locked(
                            reason="inventory_actor_or_source_conflict",
                            fingerprint=fingerprint,
                            actor_id=actor,
                            source_id=source_name,
                            payload_digest=fingerprint,
                        )
                        raise LegacyClaimConflict("legacy source fingerprint is already inventoried")
                    if loaded is None:
                        raise RepositoryCorruptionError("legacy inventory source is missing")
                    raw, durable = loaded
                    if raw != _canonical_bytes(document) or durable != document:
                        self._quarantine_locked(
                            reason="inventory_source_drift",
                            fingerprint=fingerprint,
                            actor_id=actor,
                            source_id=source_name,
                            payload_digest=fingerprint,
                        )
                        raise LegacyClaimQuarantined("legacy inventory source drifted")
                    return self._issue_source(
                        fingerprint=fingerprint,
                        actor_id=actor,
                        source_id=source_name,
                        payload_digest=fingerprint,
                    )
                if loaded is not None:
                    raw, durable = loaded
                    if raw != _canonical_bytes(document) or durable != document:
                        self._quarantine_locked(
                            reason="orphan_source_conflict",
                            fingerprint=fingerprint,
                            actor_id=actor,
                            source_id=source_name,
                            payload_digest=fingerprint,
                        )
                        raise LegacyClaimConflict("orphaned legacy source conflicts with inventory")
                else:
                    self._repository._write_legacy_unscoped_source_locked(
                        fingerprint,
                        document,
                    )
                next_inventory = dict(inventory)
                next_inventory[fingerprint] = record
                self._repository._write_legacy_unscoped_manifest_locked(
                    self._next_manifest(manifest, inventory=next_inventory)
                )
            except LegacyScopeClaimError:
                raise
            except (OSError, RepositoryCorruptionError, ValueError) as exc:
                self._quarantine_locked(
                    reason="inventory_acl_or_manifest_failure",
                    fingerprint=fingerprint,
                    actor_id=actor,
                    source_id=source_name,
                    payload_digest=fingerprint,
                )
                raise LegacyClaimQuarantined("legacy source inventory was quarantined") from exc
        return self._issue_source(
            fingerprint=fingerprint,
            actor_id=actor,
            source_id=source_name,
            payload_digest=fingerprint,
        )

    def lookup_memory_source(self, source_fingerprint: str) -> LegacyInventorySource:
        """Re-issue a local source handle from explicit durable inventory only."""

        fingerprint = _require_digest(source_fingerprint, "source_fingerprint")
        with self._repository.transaction():
            try:
                manifest = self._repository._read_legacy_unscoped_manifest_locked()
                inventory = manifest["inventory"]
                if type(inventory) is not dict:
                    raise RepositoryCorruptionError("legacy inventory is invalid")
                record = inventory.get(fingerprint)
                if type(record) is not dict or set(record) != {
                    "actor_id",
                    "source_id",
                    "payload_digest",
                    "source_path",
                }:
                    raise RepositoryCorruptionError("legacy inventory record is invalid")
                actor = _require_text(record["actor_id"], "actor_id")
                source_id = _require_text(record["source_id"], "source_id")
                digest = _require_digest(record["payload_digest"], "payload_digest")
                if record["source_path"] != f"sources/{fingerprint}.json":
                    raise RepositoryCorruptionError("legacy inventory source path is invalid")
                source = self._issue_source(
                    fingerprint=fingerprint,
                    actor_id=actor,
                    source_id=source_id,
                    payload_digest=digest,
                )
                self._verified_inventory_locked(source)
                return source
            except (LegacyScopeClaimError, OSError, RepositoryCorruptionError, ValueError) as exc:
                self._quarantine_locked(
                    reason="inventory_lookup_failure",
                    fingerprint=fingerprint,
                )
                raise LegacyClaimQuarantined("legacy source lookup was quarantined") from exc

    def list_inventory(self, *, limit: int = _MAX_INVENTORY_LIST_LIMIT) -> tuple[LegacyInventoryRecord, ...]:
        """Enumerate a bounded, read-only view of strictly verified source metadata."""

        if type(limit) is not int or not 1 <= limit <= _MAX_INVENTORY_LIST_LIMIT:
            raise ValueError(
                f"limit must be an exact int from 1 to {_MAX_INVENTORY_LIST_LIMIT}"
            )
        records: list[LegacyInventoryRecord] = []
        try:
            with self._repository.transaction():
                manifest = self._repository._read_legacy_unscoped_manifest_locked()
                inventory = manifest["inventory"]
                if type(inventory) is not dict:
                    raise RepositoryCorruptionError("legacy inventory is invalid")
                for fingerprint in sorted(inventory)[:limit]:
                    record = inventory[fingerprint]
                    _require_digest(fingerprint, "source_fingerprint")
                    if type(record) is not dict or set(record) != {
                        "actor_id",
                        "source_id",
                        "payload_digest",
                        "source_path",
                    }:
                        raise RepositoryCorruptionError("legacy inventory record is invalid")
                    actor = _require_text(record["actor_id"], "actor_id")
                    source_id = _require_text(record["source_id"], "source_id")
                    digest = _require_digest(record["payload_digest"], "payload_digest")
                    if record["source_path"] != f"sources/{fingerprint}.json":
                        raise RepositoryCorruptionError("legacy inventory source path is invalid")
                    source = self._issue_source(
                        fingerprint=fingerprint,
                        actor_id=actor,
                        source_id=source_id,
                        payload_digest=digest,
                    )
                    _manifest, _payload, payload_bytes = self._verified_inventory_locked(source)
                    records.append(
                        LegacyInventoryRecord(
                            record_id=fingerprint,
                            source_kind="explicit_memory_snapshot",
                            checksum=digest,
                            byte_size=len(payload_bytes),
                        )
                    )
        except (LegacyScopeClaimError, OSError, RepositoryCorruptionError, ValueError) as exc:
            raise LegacyClaimQuarantined("legacy inventory listing rejected unsafe record") from exc
        return tuple(records)

    def read_inventory_payload(self, source: LegacyInventorySource) -> dict[str, object]:
        """Return a detached source copy for diagnostics; source bytes stay immutable."""

        source = self._require_source(source)
        with self._repository.transaction():
            try:
                _manifest, payload, _payload_bytes = self._verified_inventory_locked(source)
                return _canonical_json_snapshot(payload)
            except LegacyClaimConflict:
                self._quarantine_locked(
                    reason="inventory_read_conflict",
                    fingerprint=source.source_fingerprint,
                    actor_id=source.actor_id,
                    source_id=source.source_id,
                    payload_digest=source.payload_digest,
                )
                raise
            except (OSError, RepositoryCorruptionError, ValueError) as exc:
                self._quarantine_locked(
                    reason="inventory_read_failure",
                    fingerprint=source.source_fingerprint,
                    actor_id=source.actor_id,
                    source_id=source.source_id,
                    payload_digest=source.payload_digest,
                )
                raise LegacyClaimQuarantined("legacy source read was quarantined") from exc

    @staticmethod
    def _claim_record(
        *,
        source: LegacyInventorySource,
        scope: SessionScope,
        state: str,
        target_generation: int | None,
    ) -> dict[str, object]:
        if state not in {"pending", "completed"}:
            raise ValueError("legacy claim state is invalid")
        return {
            "actor_id": source.actor_id,
            "destination": _scope_record(scope),
            "payload_digest": source.payload_digest,
            "state": state,
            "target_generation": target_generation,
        }

    def _claim_matches(
        self,
        claim: object,
        *,
        source: LegacyInventorySource,
        scope: SessionScope,
    ) -> dict[str, object] | None:
        if type(claim) is not dict:
            return None
        if set(claim) != {
            "actor_id",
            "destination",
            "payload_digest",
            "state",
            "target_generation",
        }:
            return None
        if (
            claim["actor_id"] != source.actor_id
            or claim["destination"] != _scope_record(scope)
            or claim["payload_digest"] != source.payload_digest
        ):
            return None
        state = claim["state"]
        generation = claim["target_generation"]
        if state == "pending" and generation is None:
            return claim
        if state == "completed" and type(generation) is int and generation >= 1:
            return claim
        return None

    def _target_agrees_locked(
        self,
        *,
        scope: SessionScope,
        payload_digest: str,
        expected_generation: int | None,
    ) -> int | None:
        snapshot = self._repository._read_snapshot_locked(
            self._repository.component_path(scope, "memory"),
            quarantine_on_error=False,
        )
        if snapshot is None:
            return None
        try:
            _payload, _bytes, actual_digest = _strict_memory_payload(snapshot.payload)
        except (TypeError, ValueError):
            return None
        if actual_digest != payload_digest:
            return None
        if expected_generation is not None and snapshot.generation != expected_generation:
            return None
        return snapshot.generation

    def _recover_or_idempotent_locked(
        self,
        *,
        manifest: dict[str, object],
        source: LegacyInventorySource,
        scope: SessionScope,
        claim: dict[str, object],
    ) -> LegacyClaimResult:
        state = claim["state"]
        expected_generation = claim["target_generation"]
        if state == "pending":
            expected_generation = None
        actual_generation = self._target_agrees_locked(
            scope=scope,
            payload_digest=source.payload_digest,
            expected_generation=expected_generation if type(expected_generation) is int else None,
        )
        if actual_generation is None:
            raise LegacyClaimConflict("legacy claim target does not agree with manifest")
        if state == "completed":
            return _result_from_claim(
                source.source_fingerprint,
                claim,
                idempotent=True,
                recovered=False,
            )
        completed = self._claim_record(
            source=source,
            scope=scope,
            state="completed",
            target_generation=actual_generation,
        )
        claims = manifest["claims"]
        if type(claims) is not dict:
            raise RepositoryCorruptionError("legacy claims index is invalid")
        next_claims = dict(claims)
        next_claims[source.source_fingerprint] = completed
        self._repository._write_legacy_unscoped_manifest_locked(
            self._next_manifest(manifest, claims=next_claims)
        )
        return _result_from_claim(
            source.source_fingerprint,
            completed,
            idempotent=True,
            recovered=True,
        )

    def claim_memory(
        self,
        destination: LegacyDestinationCapability,
        source: LegacyInventorySource,
    ) -> LegacyClaimResult:
        """Copy one explicit source through ``memory`` generation zero exactly once."""

        destination = self._consume_destination(destination)
        source = self._require_source(source)
        if destination.actor_id != source.actor_id:
            with self._repository.transaction():
                self._quarantine_locked(
                    reason="claim_actor_conflict",
                    fingerprint=source.source_fingerprint,
                    actor_id=source.actor_id,
                    source_id=source.source_id,
                    payload_digest=source.payload_digest,
                )
            raise LegacyClaimConflict("legacy claim actor does not match destination")

        stage = None
        try:
            with self._repository.transaction():
                # The first fence rejects purge/retire/ABA capabilities before
                # a staging or target operation can happen.
                self._repository._validate_session_scope_locked(destination.scope)
                manifest, payload, payload_bytes = self._verified_inventory_locked(source)
                claims = manifest["claims"]
                if type(claims) is not dict:
                    raise RepositoryCorruptionError("legacy claims index is invalid")
                existing = claims.get(source.source_fingerprint)
                resumed_pending = False
                if existing is not None:
                    matched = self._claim_matches(
                        existing,
                        source=source,
                        scope=destination.scope,
                    )
                    if matched is None:
                        raise LegacyClaimConflict("legacy source fingerprint is already claimed")
                    target = self._repository._read_snapshot_locked(
                        self._repository.component_path(destination.scope, "memory"),
                        quarantine_on_error=False,
                    )
                    if matched["state"] != "pending" or target is not None:
                        return self._recover_or_idempotent_locked(
                            manifest=manifest,
                            source=source,
                            scope=destination.scope,
                            claim=matched,
                        )
                    # A crash after durable staging but before target publish
                    # leaves a valid pending reservation. Re-stage immutable
                    # source bytes and resume only for the exact same claim.
                    resumed_pending = True
                    next_claims = dict(claims)
                else:
                    # A normal scoped writer owns this destination already.  Do
                    # not reserve this source or overwrite its component.
                    if self._repository._read_snapshot_locked(
                        self._repository.component_path(destination.scope, "memory"),
                        quarantine_on_error=False,
                    ) is not None:
                        raise LegacyClaimConflict("legacy destination memory already exists")

                    pending = self._claim_record(
                        source=source,
                        scope=destination.scope,
                        state="pending",
                        target_generation=None,
                    )
                    next_claims = dict(claims)
                    next_claims[source.source_fingerprint] = pending
                    # Reserve the cross-process source key before target publish.
                    self._repository._write_legacy_unscoped_manifest_locked(
                        self._next_manifest(manifest, claims=next_claims)
                    )
                stage = self._repository._write_legacy_unscoped_stage_locked(
                    source.source_fingerprint,
                    payload_bytes,
                )
                if stage.read_bytes() != payload_bytes:
                    raise RepositoryCorruptionError("legacy staging digest verification failed")
                self._fault("after_stage")

                # Revalidate around the owner-only staging barrier.  The
                # repository lock keeps the check/write pair serializable even
                # when a second process owns another ScopeRepository object.
                self._repository._validate_session_scope_locked(destination.scope)
                target_generation = self._repository._write_snapshot_locked(
                    self._repository.component_path(destination.scope, "memory"),
                    expected_generation=0,
                    payload=payload,
                )
                self._fault("after_target_write")
                self._repository._validate_session_scope_locked(destination.scope)
                completed = self._claim_record(
                    source=source,
                    scope=destination.scope,
                    state="completed",
                    target_generation=target_generation,
                )
                next_claims[source.source_fingerprint] = completed
                self._repository._write_legacy_unscoped_manifest_locked(
                    self._next_manifest(
                        self._repository._read_legacy_unscoped_manifest_locked(),
                        claims=next_claims,
                    )
                )
                if stage is not None:
                    stage.unlink(missing_ok=True)
                return _result_from_claim(
                    source.source_fingerprint,
                    completed,
                    idempotent=False,
                    recovered=resumed_pending,
                )
        except StaleScopeWrite:
            # Lifecycle fences are expected failures, not a reason to mutate a
            # target or reinterpret the source under a later scope generation.
            raise
        except LegacyScopeClaimError:
            with self._repository.transaction():
                self._quarantine_locked(
                    reason="claim_conflict_or_source_drift",
                    fingerprint=source.source_fingerprint,
                    actor_id=source.actor_id,
                    source_id=source.source_id,
                    payload_digest=source.payload_digest,
                )
            raise
        except (OSError, RepositoryCorruptionError, TypeError, ValueError) as exc:
            with self._repository.transaction():
                self._quarantine_locked(
                    reason="claim_acl_or_source_failure",
                    fingerprint=source.source_fingerprint,
                    actor_id=source.actor_id,
                    source_id=source.source_id,
                    payload_digest=source.payload_digest,
                )
            raise LegacyClaimQuarantined("legacy claim was quarantined") from exc


__all__ = [
    "LegacyClaimConflict",
    "LegacyClaimQuarantined",
    "LegacyClaimResult",
    "LegacyDestinationCapability",
    "LegacyInventoryRecord",
    "LegacyInventorySource",
    "LegacyScopeClaimError",
    "LegacyScopeClaimService",
]
