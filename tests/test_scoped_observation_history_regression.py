from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from sylanne_alpha.observation_history import ObservationHistoryStore
from sylanne_alpha.scope_repository import ScopeRepository
pytest_plugins = ("tests.scope_fixtures",)


def _active_scope(repository: ScopeRepository, scope: Any) -> Any:
    return repository.create_scope(scope, expected_absent=True)


def test_latest_closed_segment_must_be_the_last_closed_segment(
    tmp_path: Path,
    scopes: Any,
) -> None:
    repository = ScopeRepository(tmp_path / "scope-v1")
    scope = _active_scope(repository, scopes.bot_a_persona_a)
    store = ObservationHistoryStore.from_scope_repository(repository, limit_bytes=0)

    store._seed_closed(scope, [1, 1], mark_latest=True)
    manifest = store.manifest.to_dict()
    metadata = manifest["scopes"][scope.storage_token]
    metadata["latest_closed_segment"] = metadata["segments"][0]["path"]

    assert store._scoped_scope_meta_valid(scope.storage_token, metadata) is False


def test_cleanup_hysteresis_stays_active_until_target_ratio(
    tmp_path: Path,
    scopes: Any,
) -> None:
    repository = ScopeRepository(tmp_path / "scope-v1")
    scope = _active_scope(repository, scopes.bot_a_persona_a)
    limit_holder = {"value": 0}
    store = ObservationHistoryStore.from_scope_repository(
        repository,
        max_bytes_provider=lambda: limit_holder["value"],
        target_ratio=0.9,
    )

    store._seed_closed(scope, [1] * 10, mark_latest=True)
    used = store._scoped_used_bytes()
    limit_holder["value"] = used + 1
    with repository.transaction():
        store._refresh_scoped_manifest_locked()
        store._manifest["cleanup_active"] = True
        result = store._scoped_cleanup_once_locked(trigger="regression")

    assert bool(result) is True
    assert result.cleanup_active is True


def test_cleanup_persists_opaque_echo_after_purge_and_inactive_scope(
    tmp_path: Path,
    scopes: Any,
) -> None:
    repository = ScopeRepository(tmp_path / "scope-v1")
    scope = _active_scope(repository, scopes.bot_a_persona_a)
    limit = {"value": 0}
    store = ObservationHistoryStore.from_scope_repository(
        repository,
        max_bytes_provider=lambda: limit["value"],
    )
    store._seed_closed(scope, [32, 32], mark_latest=True)

    purged = repository.purge_session(scope, reason="test-purge")
    repository.retire_persona_revision(
        purged.persona_ref,
        expected_lifecycle_generation=purged.persona_ref.lifecycle_generation,
        reason="test-retire",
    )
    limit["value"] = 1

    result = store.cleanup_once()
    manifest = json.loads(repository.observation_manifest_path.read_text(encoding="utf-8"))
    diagnostics = manifest["cleanup_diagnostics"]

    assert result.deleted_scope == scope.storage_token
    assert result.deleted_segment == "segment-00000001.jsonl"
    assert result.manifest_generation == manifest["generation"]
    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic == {
        "scope": {
            "bot_ref": scope.bot_ref.token,
            "persona_ref": scope.persona_ref.token,
            "session_ref": scope.session_ref.token,
            "scope_generation": 2,
            "resolved_at_ms": diagnostic["scope"]["resolved_at_ms"],
        },
        "manifest_generation": manifest["generation"],
        "segment": "segment-00000001.jsonl",
        "before_bytes": diagnostic["before_bytes"],
        "after_bytes": diagnostic["after_bytes"],
        "cursor": scope.storage_token,
        "trigger": "maintenance",
        "unfinished_reason": "cleanup_active",
    }
    assert diagnostic["scope"]["resolved_at_ms"] >= 0
    assert diagnostic["before_bytes"] > diagnostic["after_bytes"] >= 0
    assert "scope_v1_" not in diagnostic["segment"]
    assert "/" not in diagnostic["segment"]
    assert "\\" not in diagnostic["segment"]

    restarted = ObservationHistoryStore.from_scope_repository(
        repository,
        max_bytes_provider=lambda: limit["value"],
    )
    assert restarted.manifest["cleanup_diagnostics"] == diagnostics


def test_old_v2_manifest_without_diagnostics_is_compatible_and_upgrades_on_cleanup(
    tmp_path: Path,
    scopes: Any,
) -> None:
    repository = ScopeRepository(tmp_path / "scope-v1")
    scope = _active_scope(repository, scopes.bot_a_persona_a)
    limit = {"value": 0}
    store = ObservationHistoryStore.from_scope_repository(
        repository,
        max_bytes_provider=lambda: limit["value"],
    )
    store._seed_closed(scope, [1, 1], mark_latest=True)

    legacy = store.manifest.to_dict()
    legacy.pop("cleanup_diagnostics", None)
    repository._atomic_json_replace(repository.observation_manifest_path, legacy)

    restarted = ObservationHistoryStore.from_scope_repository(
        repository,
        max_bytes_provider=lambda: limit["value"],
    )
    assert restarted.manifest["scopes"] == legacy["scopes"]
    assert restarted.manifest["cleanup_diagnostics"] == []

    limit["value"] = 1
    restarted.cleanup_once()
    persisted = json.loads(repository.observation_manifest_path.read_text(encoding="utf-8"))
    assert len(persisted["cleanup_diagnostics"]) == 1
    assert persisted["cleanup_diagnostics"][0]["trigger"] == "maintenance"


def test_corrupt_cleanup_diagnostics_are_cleared_without_rebuilding_history(
    tmp_path: Path,
    scopes: Any,
) -> None:
    repository = ScopeRepository(tmp_path / "scope-v1")
    scope = _active_scope(repository, scopes.bot_a_persona_a)
    store = ObservationHistoryStore.from_scope_repository(repository, limit_bytes=0)
    assert store.append(scope, {"signal": 1}, captured_at_ms=1)
    before = store.manifest.to_dict()
    corrupt = dict(before)
    corrupt["cleanup_diagnostics"] = [{"exception": "PRIVATE observed text C:\\unsafe"}]
    repository._atomic_json_replace(repository.observation_manifest_path, corrupt)

    restarted = ObservationHistoryStore.from_scope_repository(repository, limit_bytes=0)
    persisted = json.loads(repository.observation_manifest_path.read_text(encoding="utf-8"))

    assert restarted.read(scope)
    assert restarted.manifest["scopes"] == before["scopes"]
    assert restarted.manifest["cleanup_diagnostics"] == []
    assert persisted["cleanup_diagnostics"] == []
    assert "PRIVATE observed text" not in repository.observation_manifest_path.read_text(
        encoding="utf-8"
    )


def test_cleanup_diagnostics_remain_bounded_to_sixty_four_entries(
    tmp_path: Path,
    scopes: Any,
) -> None:
    repository = ScopeRepository(tmp_path / "scope-v1")
    scope = _active_scope(repository, scopes.bot_a_persona_a)
    limit = {"value": 0}
    store = ObservationHistoryStore.from_scope_repository(
        repository,
        max_bytes_provider=lambda: limit["value"],
    )
    store._seed_closed(scope, [1] * 66, mark_latest=True)
    limit["value"] = 1

    for _ in range(65):
        assert store.cleanup_once().deleted_segment is not None

    manifest = store.manifest.to_dict()
    assert len(manifest["cleanup_diagnostics"]) == 64
    assert all(
        item["trigger"] == "maintenance" and item["segment"] is not None
        for item in manifest["cleanup_diagnostics"]
    )


def test_unlimited_cleanup_noop_preserves_manifest_bytes_and_generation(
    tmp_path: Path,
) -> None:
    repository = ScopeRepository(tmp_path / "scope-v1")
    store = ObservationHistoryStore.from_scope_repository(repository, limit_bytes=0)
    before = repository.observation_manifest_path.read_bytes()
    generation = store.manifest["generation"]

    for _ in range(3):
        result = store.cleanup_once()
        assert result.manifest_generation == generation
        assert result.deleted_segment is None
        assert result.cleanup_active is False
        assert result.budget_unsatisfiable is False

    assert repository.observation_manifest_path.read_bytes() == before
    assert store.manifest["generation"] == generation
    assert store.manifest["cleanup_diagnostics"] == []


def test_duplicate_append_with_noop_cleanup_does_not_write_manifest(
    tmp_path: Path,
    scopes: Any,
) -> None:
    repository = ScopeRepository(tmp_path / "scope-v1")
    scope = _active_scope(repository, scopes.bot_a_persona_a)
    store = ObservationHistoryStore.from_scope_repository(repository, limit_bytes=0)
    assert store.append(scope, {"signal": 1}, captured_at_ms=1)
    before = repository.observation_manifest_path.read_bytes()
    generation = store.manifest["generation"]

    assert not store.append(scope, {"signal": 1}, captured_at_ms=2)

    assert repository.observation_manifest_path.read_bytes() == before
    assert store.manifest["generation"] == generation
    assert store.manifest["cleanup_diagnostics"] == []


def test_cleanup_diagnostics_are_excluded_from_quota_and_do_not_churn(
    tmp_path: Path,
    scopes: Any,
) -> None:
    repository = ScopeRepository(tmp_path / "scope-v1")
    scope = _active_scope(repository, scopes.bot_a_persona_a)
    limit = {"value": 0}
    store = ObservationHistoryStore.from_scope_repository(
        repository,
        max_bytes_provider=lambda: limit["value"],
    )
    store._seed_closed(scope, [10_000, 1], mark_latest=True)
    limit["value"] = 1

    assert store.cleanup_once().deleted_segment == "segment-00000001.jsonl"
    quota_manifest = store.manifest.to_dict()
    quota_document = dict(quota_manifest)
    quota_document.pop("cleanup_diagnostics")
    quota_bytes = len(
        json.dumps(
            quota_document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ) + sum(
        int(metadata["used_bytes"])
        for metadata in quota_document["scopes"].values()
    )
    limit["value"] = math.ceil((quota_bytes + 1) / 0.9)

    settled = store.cleanup_once()
    assert settled.deleted_segment is None
    assert settled.budget_unsatisfiable is False
    assert settled.cleanup_active is False
    settled_document = store.manifest.to_dict()
    settled_document.pop("cleanup_diagnostics")
    settled_quota_bytes = len(
        json.dumps(
            settled_document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ) + sum(
        int(metadata["used_bytes"])
        for metadata in settled_document["scopes"].values()
    )
    assert store._scoped_used_bytes() == settled_quota_bytes

    before = repository.observation_manifest_path.read_bytes()
    generation = store.manifest["generation"]
    diagnostics = store.manifest["cleanup_diagnostics"]
    repeated = store.cleanup_once()

    assert repeated.manifest_generation == generation
    assert repository.observation_manifest_path.read_bytes() == before
    assert store.manifest["generation"] == generation
    assert store.manifest["cleanup_diagnostics"] == diagnostics


def test_cleanup_diagnostic_after_bytes_matches_post_write_quota_generation(
    tmp_path: Path,
) -> None:
    repository = ScopeRepository(tmp_path / "scope-v1")
    store = ObservationHistoryStore.from_scope_repository(repository, limit_bytes=0)
    seeded = store.manifest.to_dict()
    seeded["generation"] = 9
    seeded["cleanup_active"] = True
    repository._atomic_json_replace(repository.observation_manifest_path, seeded)

    restarted = ObservationHistoryStore.from_scope_repository(repository, limit_bytes=0)
    result = restarted.cleanup_once()
    manifest = restarted.manifest.to_dict()

    assert result.manifest_generation == 10
    assert manifest["generation"] == 10
    assert manifest["cleanup_diagnostics"][-1]["after_bytes"] == restarted._scoped_used_bytes()


def test_append_with_noop_cleanup_uses_one_outer_manifest_generation(
    tmp_path: Path,
    scopes: Any,
) -> None:
    repository = ScopeRepository(tmp_path / "scope-v1")
    scope = _active_scope(repository, scopes.bot_a_persona_a)
    store = ObservationHistoryStore.from_scope_repository(repository, limit_bytes=0)
    before = store.manifest["generation"]

    assert store.append(scope, {"signal": 1}, captured_at_ms=1)

    manifest = store.manifest.to_dict()
    assert manifest["generation"] == before + 1
    assert manifest["cleanup_diagnostics"] == []
