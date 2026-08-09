from __future__ import annotations

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
