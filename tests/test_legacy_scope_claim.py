"""Contracts for explicit legacy-memory copy claims into one frozen scope."""

from __future__ import annotations

import asyncio
from dataclasses import fields

import pytest

from sylanne_alpha.memory_system import MemorySystem
from sylanne_alpha.scope_repository import ScopeRepository
from sylanne_alpha.state_persistence import StatePersistence
from tests.scope_fixtures import scopes


def _memory_payload() -> dict[str, object]:
    return MemorySystem().to_dict()


def test_explicit_inventory_claim_copies_one_memory_snapshot_without_moving_source(
    tmp_path,
    scopes,
) -> None:
    """A claim is explicit, scope-bound, and leaves the inventory source intact."""

    from sylanne_alpha.legacy_scope_claim import LegacyScopeClaimService

    repository = ScopeRepository(tmp_path / "scope-v1")
    scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    service = LegacyScopeClaimService(repository)
    payload = _memory_payload()

    source = service.inventory_memory(
        actor_id="operator-a",
        source_id="manual-export-001",
        payload=payload,
    )
    result = service.claim_memory(
        service.issue_destination(scope, actor_id="operator-a"),
        source,
    )

    stored = repository.read_component(scope, "memory")
    assert stored is not None
    assert stored.generation == 1
    assert stored.payload == payload
    assert result.idempotent is False
    assert service.read_inventory_payload(source) == payload
    assert payload == _memory_payload()
    assert service.read_inventory_payload(source) is not payload


def test_registry_present_state_persistence_never_replays_legacy_memory_fallbacks() -> None:
    """The compatibility reader must not inspect KV/body/alpha in scoped mode."""

    class _Map:
        def __init__(self, value=None) -> None:
            self.value = value

        def get(self, _key, _default=None):
            return self.value

        def set(self, _key, value) -> None:
            self.value = value

        def set_on_evict(self, _callback) -> None:
            pass

    class _Store:
        def __init__(self) -> None:
            self.memory_systems = _Map(MemorySystem())
            self.sylanne_memory_cache = _Map()

    class _Plugin:
        def __init__(self) -> None:
            self._store = _Store()
            self._scope_runtime_registry = object()
            self.kv_reads = 0
            self.kv_writes = 0

        async def get_kv_data(self, _key, _default=None):
            self.kv_reads += 1
            return MemorySystem().to_dict()

        async def put_kv_data(self, _key, _value) -> None:
            self.kv_writes += 1

    plugin = _Plugin()
    persistence = StatePersistence(plugin)

    assert asyncio.run(persistence.load_sylanne_memory_state("scope_v1_bound")) is None
    asyncio.run(persistence.hydrate_memory_system("scope_v1_bound"))
    asyncio.run(persistence.save_sylanne_memory_state("scope_v1_bound", MemorySystem()))
    assert plugin.kv_reads == 0
    assert plugin.kv_writes == 0


def test_claim_is_cross_instance_idempotent_but_rejects_another_destination(
    tmp_path,
    scopes,
) -> None:
    """The persisted source fingerprint is one global key, not a local cache key."""

    from sylanne_alpha.legacy_scope_claim import (
        LegacyClaimConflict,
        LegacyScopeClaimService,
    )

    root = tmp_path / "scope-v1"
    first_repository = ScopeRepository(root)
    first_scope = first_repository.create_scope(
        scopes.bot_a_persona_a,
        expected_absent=True,
    )
    sibling_scope = first_repository.create_scope(
        scopes.bot_a_persona_a_second_session,
        expected_absent=True,
    )
    first_service = LegacyScopeClaimService(first_repository)
    source = first_service.inventory_memory(
        actor_id="operator-a",
        source_id="manual-export-001",
        payload=_memory_payload(),
    )
    first_service.claim_memory(
        first_service.issue_destination(first_scope, actor_id="operator-a"),
        source,
    )

    # A fresh service/repository instance exercises the durable claim index.
    restarted_repository = ScopeRepository(root)
    restarted_service = LegacyScopeClaimService(restarted_repository)
    recovered_source = restarted_service.lookup_memory_source(source.source_fingerprint)
    retry = restarted_service.claim_memory(
        restarted_service.issue_destination(first_scope, actor_id="operator-a"),
        recovered_source,
    )
    assert retry.idempotent is True
    assert retry.recovered is False

    with pytest.raises(LegacyClaimConflict):
        restarted_service.claim_memory(
            restarted_service.issue_destination(sibling_scope, actor_id="operator-a"),
            recovered_source,
        )
    assert restarted_repository.read_component(sibling_scope, "memory") is None

    with pytest.raises(LegacyClaimConflict):
        restarted_service.inventory_memory(
            actor_id="operator-b",
            source_id="manual-export-001",
            payload=_memory_payload(),
        )


def test_claim_recovers_a_post_copy_crash_only_from_matching_target_and_manifest(
    tmp_path,
    scopes,
) -> None:
    """A pending claim completes after restart only when the copied bytes agree."""

    from sylanne_alpha.legacy_scope_claim import LegacyScopeClaimService

    class _CrashAfterTarget(RuntimeError):
        pass

    def crash_after_target(point: str) -> None:
        if point == "after_target_write":
            raise _CrashAfterTarget()

    root = tmp_path / "scope-v1"
    repository = ScopeRepository(root)
    scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    crashing = LegacyScopeClaimService(repository, fault_injector=crash_after_target)
    source = crashing.inventory_memory(
        actor_id="operator-a",
        source_id="manual-export-001",
        payload=_memory_payload(),
    )

    with pytest.raises(_CrashAfterTarget):
        crashing.claim_memory(
            crashing.issue_destination(scope, actor_id="operator-a"),
            source,
        )
    copied = repository.read_component(scope, "memory")
    assert copied is not None and copied.generation == 1

    restarted = LegacyScopeClaimService(ScopeRepository(root))
    recovered = restarted.claim_memory(
        restarted.issue_destination(scope, actor_id="operator-a"),
        restarted.lookup_memory_source(source.source_fingerprint),
    )
    assert recovered.idempotent is True
    assert recovered.recovered is True
    assert repository.read_component(scope, "memory").generation == 1


def test_claim_resumes_after_staging_crash_without_publishing_partial_target(
    tmp_path,
    scopes,
) -> None:
    """A durable pending claim can resume when staging finished before the crash."""

    from sylanne_alpha.legacy_scope_claim import LegacyScopeClaimService

    class _CrashAfterStage(RuntimeError):
        pass

    def crash_after_stage(point: str) -> None:
        if point == "after_stage":
            raise _CrashAfterStage()

    root = tmp_path / "scope-v1"
    repository = ScopeRepository(root)
    scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    crashing = LegacyScopeClaimService(repository, fault_injector=crash_after_stage)
    source = crashing.inventory_memory(
        actor_id="operator-a",
        source_id="manual-export-001",
        payload=_memory_payload(),
    )

    with pytest.raises(_CrashAfterStage):
        crashing.claim_memory(
            crashing.issue_destination(scope, actor_id="operator-a"),
            source,
        )
    assert repository.read_component(scope, "memory") is None

    restarted = LegacyScopeClaimService(ScopeRepository(root))
    resumed = restarted.claim_memory(
        restarted.issue_destination(scope, actor_id="operator-a"),
        restarted.lookup_memory_source(source.source_fingerprint),
    )
    assert resumed.idempotent is False
    assert resumed.recovered is True
    assert repository.read_component(scope, "memory").generation == 1


def test_stale_destination_capability_never_creates_a_memory_component(
    tmp_path,
    scopes,
) -> None:
    """Purge/ABA fences are checked before staging or writing the destination."""

    from sylanne_alpha.legacy_scope_claim import LegacyScopeClaimService
    from sylanne_alpha.scope_repository import StaleScopeWrite

    repository = ScopeRepository(tmp_path / "scope-v1")
    original = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    service = LegacyScopeClaimService(repository)
    source = service.inventory_memory(
        actor_id="operator-a",
        source_id="manual-export-001",
        payload=_memory_payload(),
    )
    stale_destination = service.issue_destination(original, actor_id="operator-a")
    replacement = repository.purge_session(original, reason="test-purge")

    with pytest.raises(StaleScopeWrite):
        service.claim_memory(stale_destination, source)
    assert repository.read_component(replacement, "memory") is None


def test_authorization_guard_denial_never_quarantines_or_writes_target(
    tmp_path,
    scopes,
) -> None:
    from sylanne_alpha.legacy_scope_claim import (
        LegacyClaimAuthorizationDenied,
        LegacyScopeClaimService,
    )

    repository = ScopeRepository(tmp_path / "scope-v1")
    scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    service = LegacyScopeClaimService(repository)
    source = service.inventory_memory(
        actor_id="operator-a", source_id="manual-export-001", payload=_memory_payload()
    )
    quarantine = repository.legacy_unscoped_root / "quarantine"
    before = tuple(quarantine.glob("*.json")) if quarantine.exists() else ()

    with pytest.raises(LegacyClaimAuthorizationDenied):
        service.claim_memory(
            service.issue_destination(scope, actor_id="operator-a"),
            source,
            authorization_guard=lambda: False,
        )

    assert repository.read_component(scope, "memory") is None
    after = tuple(quarantine.glob("*.json")) if quarantine.exists() else ()
    assert after == before


def test_malformed_source_is_quarantined_before_any_scope_can_be_selected(
    tmp_path,
) -> None:
    """A legacy-shaped or partial blob cannot become a scoped memory snapshot."""

    from sylanne_alpha.legacy_scope_claim import (
        LegacyClaimQuarantined,
        LegacyScopeClaimService,
    )

    repository = ScopeRepository(tmp_path / "scope-v1")
    service = LegacyScopeClaimService(repository)

    with pytest.raises(LegacyClaimQuarantined):
        service.inventory_memory(
            actor_id="operator-a",
            source_id="manual-export-001",
            payload={"schema_version": "astrbot.sylanne_memory_state.v1", "records": []},
        )
    quarantine = repository.legacy_unscoped_root / "quarantine"
    assert any(quarantine.glob("*.json"))


def test_drifted_inventory_source_is_quarantined_without_target_mutation(
    tmp_path,
    scopes,
) -> None:
    """Digest drift discovered at claim time is isolated before the component CAS."""

    from sylanne_alpha.legacy_scope_claim import (
        LegacyClaimConflict,
        LegacyScopeClaimService,
    )

    repository = ScopeRepository(tmp_path / "scope-v1")
    scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    service = LegacyScopeClaimService(repository)
    source = service.inventory_memory(
        actor_id="operator-a",
        source_id="manual-export-001",
        payload=_memory_payload(),
    )
    drifted_payload = _memory_payload()
    drifted_payload["tick"] = 1
    with repository.transaction():
        repository._write_legacy_unscoped_source_locked(
            source.source_fingerprint,
            {
                "schema_version": "sylanne.scope.legacy-source.v1",
                "source_fingerprint": source.source_fingerprint,
                "actor_id": source.actor_id,
                "source_id": source.source_id,
                "payload_digest": source.payload_digest,
                "payload": drifted_payload,
            },
        )

    with pytest.raises(LegacyClaimConflict):
        service.claim_memory(
            service.issue_destination(scope, actor_id="operator-a"),
            source,
        )
    assert repository.read_component(scope, "memory") is None
    assert any((repository.legacy_unscoped_root / "quarantine").glob("*.json"))


def test_inventory_list_returns_only_bounded_opaque_metadata_without_mutation(
    tmp_path,
    scopes,
) -> None:
    """Enumeration never leaks source identifiers, bytes, or target ownership."""

    from sylanne_alpha.legacy_scope_claim import LegacyScopeClaimService

    repository = ScopeRepository(tmp_path / "scope-v1")
    scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    service = LegacyScopeClaimService(repository)
    payload = _memory_payload()
    first = service.inventory_memory(
        actor_id="platform:operator-a",
        source_id="self:manual-export-001",
        payload=payload,
    )
    second_payload = _memory_payload()
    second_payload["tick"] = 1
    second = service.inventory_memory(
        actor_id="platform:operator-b",
        source_id="target:manual-export-002",
        payload=second_payload,
    )
    manifest_before = repository.legacy_unscoped_manifest_path.read_bytes()

    listed = service.list_inventory(limit=1)

    assert len(listed) == 1
    record = listed[0]
    assert record.record_id in {first.source_fingerprint, second.source_fingerprint}
    assert record.source_kind == "explicit_memory_snapshot"
    assert record.checksum == record.record_id
    assert record.byte_size > 0
    assert {field.name for field in fields(type(record))} == {
        "record_id",
        "source_kind",
        "checksum",
        "byte_size",
    }
    rendered = repr(record)
    assert "platform:operator-a" not in rendered
    assert "self:manual-export-001" not in rendered
    assert "target:manual-export-002" not in rendered
    assert "payload" not in rendered
    assert "source_path" not in rendered
    assert repository.legacy_unscoped_manifest_path.read_bytes() == manifest_before
    assert repository.read_component(scope, "memory") is None
    assert not (repository.legacy_unscoped_root / "quarantine").exists()


def test_inventory_list_fails_closed_on_malformed_source_without_quarantine_mutation(
    tmp_path,
    scopes,
) -> None:
    """A read-only listing rejects malformed durable bytes without side effects."""

    from sylanne_alpha.legacy_scope_claim import (
        LegacyClaimQuarantined,
        LegacyScopeClaimService,
    )

    repository = ScopeRepository(tmp_path / "scope-v1")
    scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    service = LegacyScopeClaimService(repository)
    source = service.inventory_memory(
        actor_id="operator-a",
        source_id="manual-export-001",
        payload=_memory_payload(),
    )
    with repository.transaction():
        repository._write_legacy_unscoped_source_locked(
            source.source_fingerprint,
            {
                "schema_version": "sylanne.scope.legacy-source.v1",
                "source_fingerprint": source.source_fingerprint,
                "actor_id": source.actor_id,
                "source_id": source.source_id,
                "payload_digest": source.payload_digest,
                "payload": {"not": "a strict memory snapshot"},
            },
        )
    manifest_before = repository.legacy_unscoped_manifest_path.read_bytes()

    with pytest.raises(LegacyClaimQuarantined, match="legacy inventory listing"):
        service.list_inventory()

    assert repository.legacy_unscoped_manifest_path.read_bytes() == manifest_before
    assert repository.read_component(scope, "memory") is None
    assert not (repository.legacy_unscoped_root / "quarantine").exists()


def test_inventory_list_does_not_open_sources_after_the_requested_limit(
    tmp_path,
    scopes,
) -> None:
    """A damaged later record cannot block a deterministic bounded first page."""

    from sylanne_alpha.legacy_scope_claim import (
        LegacyClaimQuarantined,
        LegacyScopeClaimService,
    )

    repository = ScopeRepository(tmp_path / "scope-v1")
    scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    service = LegacyScopeClaimService(repository)
    first_payload = _memory_payload()
    second_payload = _memory_payload()
    second_payload["tick"] = 1
    sources = sorted(
        (
            service.inventory_memory(
                actor_id="operator-a",
                source_id="manual-export-001",
                payload=first_payload,
            ),
            service.inventory_memory(
                actor_id="operator-b",
                source_id="manual-export-002",
                payload=second_payload,
            ),
        ),
        key=lambda source: source.source_fingerprint,
    )
    expected, damaged = sources
    with repository.transaction():
        repository._write_legacy_unscoped_source_locked(
            damaged.source_fingerprint,
            {
                "schema_version": "sylanne.scope.legacy-source.v1",
                "source_fingerprint": damaged.source_fingerprint,
                "actor_id": damaged.actor_id,
                "source_id": damaged.source_id,
                "payload_digest": damaged.payload_digest,
                "payload": {"not": "a strict memory snapshot"},
            },
        )
    manifest_before = repository.legacy_unscoped_manifest_path.read_bytes()

    listed = service.list_inventory(limit=1)

    assert listed[0].record_id == expected.source_fingerprint
    assert listed[0].checksum == expected.payload_digest
    assert repository.legacy_unscoped_manifest_path.read_bytes() == manifest_before
    assert repository.read_component(scope, "memory") is None
    assert not (repository.legacy_unscoped_root / "quarantine").exists()
    with pytest.raises(LegacyClaimQuarantined, match="legacy inventory listing"):
        service.list_inventory(limit=2)
    assert repository.legacy_unscoped_manifest_path.read_bytes() == manifest_before
    assert repository.read_component(scope, "memory") is None
    assert not (repository.legacy_unscoped_root / "quarantine").exists()
