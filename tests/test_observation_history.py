from __future__ import annotations

import hashlib
import importlib
import json
import logging
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytest_plugins = ("tests.scope_fixtures",)


def _history_module() -> Any:
    try:
        return importlib.import_module("sylanne_alpha.observation_history")
    except ModuleNotFoundError:
        pytest.fail("sylanne_alpha.observation_history is not implemented")


def _snapshot(value: float = 0.25) -> dict[str, Any]:
    return {
        "schema_version": "sylanne.alpha.v1",
        "session_key": "snapshot-session-must-not-win",
        "turns": 12,
        "body": {
            "memory": {"contents": "PRIVATE MEMORY"},
            "prompt_text": "PRIVATE PROMPT",
        },
        "last_event": {"text": "PRIVATE LAST EVENT", "token": "secret-token"},
        "previous_event": {"text": "PRIVATE PREVIOUS EVENT"},
        "audit": {"chat_text": "PRIVATE CHAT"},
        "computation": {
            "tick_count": 9,
            "gate": {
                "precision": 0.73,
                "mean_surprise": 0.41,
                "history_len": 4,
                "surprise_history": [0.1, 0.2],
                "prediction": "PRIVATE TOKEN MATERIAL",
            },
            "route_counts": {"resonance": 7, "skip": 2},
            "boundary": {
                "boundary_integrity": 0.91,
                "internal_entropy": 0.08,
                "stability": 0.8372,
                "repair_rate": 0.03,
                "phase_transitions": 3,
                "phase_transition_log": [{"reason": "PRIVATE"}],
            },
            "expression": {
                "pressure": 0.22,
                "threshold": 0.61,
                "silence_duration": 8.5,
                "expression_count": 6,
                "pressures": [0.2, 0.4],
            },
            "expression_drive": 0.44,
            "feedback_counts": {"accepted": 5, "ignored": 2, "rejected": 1},
            "timing": {
                "total_ms": 2.5,
                "perception": 0.1,
                "gate": 0.2,
                "void_scar": 0.3,
                "sheaf": 0.4,
                "hgt": 0.5,
                "boundary": 0.6,
                "expression": 0.7,
                "rolling_samples": [1, 2, 3],
                "private_note": "PRIVATE TIMING",
            },
            "engine": {"memory": "PRIVATE ENGINE STATE"},
        },
        "_last_computation_result": {
            "emotion": {
                "warmth": value,
                "arousal": 0.2,
                "valence": -0.1,
                "tension": 0.3,
                "curiosity": 0.4,
                "repair_pressure": 0.05,
                "expression_drive": 0.44,
                "boundary_firmness": 0.75,
                "coherence": 0.82,
                "chat_text": "PRIVATE EMOTION TEXT",
            },
            "surprise": 0.37,
            "route": "resonance",
            "expression_state": {
                "mode": "silent",
                "prompt": "PRIVATE EXPRESSION PROMPT",
            },
            "text": "PRIVATE RESULT TEXT",
            "recalled": [{"text": "PRIVATE RECALLED TEXT"}],
        },
    }


def _jsonl_paths(root: Path) -> set[Path]:
    return set(root.rglob("*.jsonl"))


def _append_values(
    store: Any,
    session: str,
    values: list[float],
    *,
    start_ms: int = 1_000,
) -> None:
    for offset, value in enumerate(values):
        assert store.append_snapshot(
            session,
            _snapshot(value),
            captured_at_ms=start_ms + offset,
        )


def test_projection_is_explicit_finite_allow_list() -> None:
    history = _history_module()
    snapshot = _snapshot()
    snapshot["_last_computation_result"]["emotion"]["warmth"] = float("nan")
    snapshot["computation"]["boundary"]["repair_rate"] = float("inf")
    snapshot["computation"]["timing"]["gate"] = float("nan")
    snapshot["computation"]["timing"]["expression"] = "0.7"

    row = history.project_observation("user/../../unsafe", snapshot, 1_234)

    assert row["schema_version"] == "sylanne.observation.sample.v1"
    assert row["captured_at_ms"] == 1_234
    assert row["session"] == "user/../../unsafe"
    assert row["turns"] == 12
    assert row["tick_count"] == 9
    assert set(row["groups"]) == {
        "emotion",
        "gate",
        "route",
        "timing",
        "boundary",
        "expression",
        "feedback",
    }
    assert row["groups"]["emotion"] == {
        "arousal": 0.2,
        "valence": -0.1,
        "tension": 0.3,
        "curiosity": 0.4,
        "repair_pressure": 0.05,
        "expression_drive": 0.44,
        "boundary_firmness": 0.75,
        "coherence": 0.82,
    }
    assert row["groups"]["gate"] == {
        "surprise": 0.37,
        "precision": 0.73,
        "mean_surprise": 0.41,
        "history_len": 4,
    }
    assert row["groups"]["route"] == {
        "route": "resonance",
        "route_counts": {"resonance": 7, "skip": 2},
    }
    assert row["groups"]["timing"] == {
        "total_ms": 2.5,
        "perception": 0.1,
        "void_scar": 0.3,
        "sheaf": 0.4,
        "hgt": 0.5,
        "boundary": 0.6,
    }
    assert row["groups"]["boundary"] == {
        "boundary_integrity": 0.91,
        "internal_entropy": 0.08,
        "stability": 0.8372,
        "phase_transitions": 3,
    }
    assert row["groups"]["expression"] == {
        "pressure": 0.22,
        "threshold": 0.61,
        "silence_duration": 8.5,
        "expression_count": 6,
        "drive": 0.44,
        "mode": "silent",
    }
    assert row["groups"]["feedback"] == {
        "accepted": 5,
        "ignored": 2,
        "rejected": 1,
    }
    serialized = json.dumps(row, ensure_ascii=False)
    for forbidden in (
        "PRIVATE",
        "last_event",
        "previous_event",
        "prompt",
        "memory",
        "token",
        "recalled",
        "chat_text",
    ):
        assert forbidden not in serialized
    assert len(row["digest"]) == 64


def test_scoped_web_history_requires_exact_scope_and_fails_fast_on_repository_lock(
    tmp_path: Path,
    scopes: Any,
) -> None:
    from sylanne_alpha.observation_history import ObservationHistoryStore
    from sylanne_alpha.scope_repository import ScopeRepository
    from sylanne_alpha.webui_routes import _scoped_history_payload

    root = tmp_path / "scope-v1"
    repository = ScopeRepository(root)
    scope = repository.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    store = ObservationHistoryStore.from_scope_repository(repository, limit_bytes=0)
    assert store.append(scope, _snapshot(0.4), captured_at_ms=100)

    unlocked = store.query_nowait(
        scope,
        group="emotion",
        from_ms=None,
        to_ms=None,
        max_points=240,
    )
    assert unlocked["sample_count"] == 1
    assert unlocked["storage"]["cleanup_active"] is False
    assert unlocked["storage"]["budget_unsatisfiable"] is False
    with pytest.raises(ValueError, match="frozen SessionScope"):
        store.query_nowait(
            scope.storage_token,
            group="emotion",
            from_ms=None,
            to_ms=None,
            max_points=240,
        )

    plugin = SimpleNamespace(
        _session_ctx=SimpleNamespace(observation_history_store=store)
    )
    competing = ScopeRepository(root)
    with competing.transaction():
        started = time.perf_counter()
        locked = _scoped_history_payload(plugin, SimpleNamespace(scope=scope))
        elapsed = time.perf_counter() - started

    assert elapsed < 0.25
    assert locked == {"sample_count": 0, "points": [], "storage": {}}


def test_resonance_spine_snapshot_projects_latest_real_timings_in_ms() -> None:
    from sylanne_alpha._engine.sylanne_core.compute.kernel import AlphaKernel

    kernel = AlphaKernel.boot("timing-session")
    before = kernel.computation.to_dict()["timing"]
    assert before == {}

    kernel.tick({"text": "measure a real computation", "now": 1.0})
    timing = kernel.computation.to_dict()["timing"]

    assert timing["total_ms"] == pytest.approx(
        kernel.computation._timings[-1] / 1_000_000.0
    )
    for layer, samples in kernel.computation._layer_timings.items():
        assert timing[layer] == pytest.approx(samples[-1] / 1_000_000.0)
    assert all(value >= 0 for value in timing.values())
    json.dumps(timing)


def test_projection_digest_ignores_capture_time_but_includes_session_and_values() -> None:
    history = _history_module()

    first = history.project_observation("session-a", _snapshot(0.2), 100)
    later = history.project_observation("session-a", _snapshot(0.2), 200)
    other_session = history.project_observation("session-b", _snapshot(0.2), 100)
    changed = history.project_observation("session-a", _snapshot(0.3), 100)

    assert first["digest"] == later["digest"]
    assert first["digest"] != other_session["digest"]
    assert first["digest"] != changed["digest"]


def test_runtime_calls_sink_only_after_successful_atomic_replace(
    tmp_path: Path,
) -> None:
    from sylanne_alpha._engine.sylanne_core.compute.runtime import AlphaRuntime

    seen: list[tuple[str, dict[str, Any]]] = []
    runtime = AlphaRuntime(tmp_path)
    runtime.set_observation_sink(lambda session, snapshot: seen.append((session, snapshot)))
    snapshot = _snapshot()

    runtime.save_snapshot("session-a", snapshot)

    assert seen == [("session-a", snapshot)]
    assert json.loads(runtime._path("session-a").read_text(encoding="utf-8")) == snapshot


def test_runtime_replace_failure_does_not_call_sink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_module = importlib.import_module("sylanne_alpha._engine.sylanne_core.compute.runtime")
    seen: list[str] = []
    runtime = runtime_module.AlphaRuntime(tmp_path)
    runtime.set_observation_sink(lambda session, _snapshot: seen.append(session))

    def fail_replace(_src: object, _dst: object) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(runtime_module.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        runtime.save_snapshot("session-a", _snapshot())

    assert seen == []
    assert not runtime._path("session-a").exists()
    assert not runtime._path("session-a").with_suffix(".json.tmp").exists()


def test_runtime_sink_failure_is_warning_and_fail_open(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from sylanne_alpha._engine.sylanne_core.compute.runtime import AlphaRuntime

    runtime = AlphaRuntime(tmp_path)

    def fail_sink(_session: str, _snapshot: dict[str, Any]) -> None:
        raise RuntimeError("history unavailable")

    runtime.set_observation_sink(fail_sink)

    with caplog.at_level(logging.WARNING, logger="sylanne_core"):
        runtime.save_snapshot("session-a", _snapshot())

    assert runtime._path("session-a").exists()
    assert "observation history append failed" in caplog.text.lower()


def test_append_deduplicates_across_restart_and_query_is_chronological(
    tmp_path: Path,
) -> None:
    history = _history_module()
    store = history.ObservationHistoryStore(tmp_path, lambda: 0)

    assert store.append_snapshot("session-a", _snapshot(0.2), captured_at_ms=300)
    assert not store.append_snapshot("session-a", _snapshot(0.2), captured_at_ms=400)
    assert store.append_snapshot("session-a", _snapshot(0.3), captured_at_ms=100)
    assert (tmp_path / "manifest.json").is_file()

    restarted = history.ObservationHistoryStore(tmp_path, lambda: 0)
    assert not restarted.append_snapshot("session-a", _snapshot(0.3), captured_at_ms=500)
    result = restarted.query(
        "session-a",
        group="emotion",
        from_ms=None,
        to_ms=None,
        max_points=None,
    )

    assert [point["from_ms"] for point in result["points"]] == [100, 300]
    assert [point["first"]["warmth"] for point in result["points"]] == [0.3, 0.2]
    assert result["sample_count"] == 2
    assert result["partial"] is False
    assert result["storage"]["segment_count"] == 1


@pytest.mark.parametrize("manifest_contents", [None, "{broken"])
def test_missing_or_corrupt_manifest_is_rebuilt_by_scanning_segments(
    tmp_path: Path,
    manifest_contents: str | None,
) -> None:
    history = _history_module()
    store = history.ObservationHistoryStore(tmp_path, lambda: 0)
    assert store.append_snapshot("session-a", _snapshot(0.2), captured_at_ms=100)
    manifest = tmp_path / "manifest.json"
    if manifest_contents is None:
        manifest.unlink()
    else:
        manifest.write_text(manifest_contents, encoding="utf-8")

    rebuilt = history.ObservationHistoryStore(tmp_path, lambda: 0)
    result = rebuilt.query("session-a", group="emotion", from_ms=None, to_ms=None, max_points=None)

    assert [point["first"]["warmth"] for point in result["points"]] == [0.2]
    parsed_manifest = json.loads(manifest.read_text(encoding="utf-8"))
    assert parsed_manifest["schema_version"] == "sylanne.observation.manifest.v1"


def test_invalid_utf8_manifest_is_rebuilt_by_scanning_segments(
    tmp_path: Path,
) -> None:
    history = _history_module()
    store = history.ObservationHistoryStore(tmp_path, lambda: 0)
    assert store.append_snapshot("session-a", _snapshot(0.2), captured_at_ms=100)
    manifest = tmp_path / "manifest.json"
    manifest.write_bytes(b"\xff\xfe\xfa invalid utf-8")

    try:
        rebuilt = history.ObservationHistoryStore(tmp_path, lambda: 0)
    except UnicodeDecodeError:
        pytest.fail("invalid UTF-8 manifest was not treated as corrupt")
    result = rebuilt.query("session-a", group="emotion", from_ms=None, to_ms=None, max_points=None)

    assert [point["first"]["warmth"] for point in result["points"]] == [0.2]
    assert json.loads(manifest.read_text(encoding="utf-8"))["schema_version"] == "sylanne.observation.manifest.v1"


def test_manifest_with_reused_next_segment_number_is_rebuilt(
    tmp_path: Path,
) -> None:
    history = _history_module()
    store = history.ObservationHistoryStore(
        tmp_path,
        lambda: 0,
        segment_bytes=1,
    )
    _append_values(store, "session-a", [0.1, 0.2], start_ms=100)
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    session_meta = next(iter(manifest["sessions"].values()))
    session_meta["next_segment"] = 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    rebuilt = history.ObservationHistoryStore(
        tmp_path,
        lambda: 0,
        segment_bytes=1,
    )
    assert rebuilt.append_snapshot(
        "session-a",
        _snapshot(0.3),
        captured_at_ms=102,
    )
    result = rebuilt.query("session-a", group="emotion", from_ms=None, to_ms=None, max_points=None)

    assert [point["first"]["warmth"] for point in result["points"]] == [0.1, 0.2, 0.3]
    assert {path.name for path in _jsonl_paths(tmp_path)} == {
        "segment-00000001.jsonl",
        "segment-00000002.jsonl",
        "segment-00000003.jsonl",
    }


def test_corrupt_or_truncated_rows_are_skipped_and_mark_query_partial(
    tmp_path: Path,
) -> None:
    history = _history_module()
    store = history.ObservationHistoryStore(tmp_path, lambda: 0)
    assert store.append_snapshot("session-a", _snapshot(0.2), captured_at_ms=100)
    [segment] = _jsonl_paths(tmp_path)
    with segment.open("ab") as stream:
        stream.write(b'{"schema_version":"sylanne.observation.sample.v1"')

    result = store.query("session-a", group="emotion", from_ms=None, to_ms=None, max_points=None)

    assert [point["first"]["warmth"] for point in result["points"]] == [0.2]
    assert result["partial"] is True


def test_restart_closes_truncated_active_segment_before_next_append(
    tmp_path: Path,
) -> None:
    history = _history_module()
    store = history.ObservationHistoryStore(tmp_path, lambda: 0)
    assert store.append_snapshot("session-a", _snapshot(0.2), captured_at_ms=100)
    [segment] = _jsonl_paths(tmp_path)
    with segment.open("ab") as stream:
        stream.write(b'{"truncated":')

    restarted = history.ObservationHistoryStore(tmp_path, lambda: 0)
    assert restarted.append_snapshot(
        "session-a",
        _snapshot(0.3),
        captured_at_ms=200,
    )
    result = restarted.query("session-a", group="emotion", from_ms=None, to_ms=None, max_points=None)

    assert [point["first"]["warmth"] for point in result["points"]] == [0.2, 0.3]
    assert result["partial"] is True
    assert result["storage"]["segment_count"] == 2


def test_query_filters_range_and_reports_dynamic_global_storage_metadata(
    tmp_path: Path,
) -> None:
    history = _history_module()
    limit = [128]
    store = history.ObservationHistoryStore(tmp_path, lambda: limit[0])
    _append_values(store, "session-a", [0.1, 0.2, 0.3], start_ms=100)

    limit[0] = 0
    result = store.query("session-a", group="emotion", from_ms=101, to_ms=102, max_points=1)

    assert result["points"] == [
        {
            "from_ms": 101,
            "to_ms": 102,
            "first": {
                "warmth": 0.2,
                "arousal": 0.2,
                "valence": -0.1,
                "tension": 0.3,
                "curiosity": 0.4,
                "repair_pressure": 0.05,
                "expression_drive": 0.44,
                "boundary_firmness": 0.75,
                "coherence": 0.82,
            },
            "last": {
                "warmth": 0.3,
                "arousal": 0.2,
                "valence": -0.1,
                "tension": 0.3,
                "curiosity": 0.4,
                "repair_pressure": 0.05,
                "expression_drive": 0.44,
                "boundary_firmness": 0.75,
                "coherence": 0.82,
            },
            "min": {
                "warmth": 0.2,
                "arousal": 0.2,
                "valence": -0.1,
                "tension": 0.3,
                "curiosity": 0.4,
                "repair_pressure": 0.05,
                "expression_drive": 0.44,
                "boundary_firmness": 0.75,
                "coherence": 0.82,
            },
            "max": {
                "warmth": 0.3,
                "arousal": 0.2,
                "valence": -0.1,
                "tension": 0.3,
                "curiosity": 0.4,
                "repair_pressure": 0.05,
                "expression_drive": 0.44,
                "boundary_firmness": 0.75,
                "coherence": 0.82,
            },
        }
    ]
    assert result["storage"]["limit_bytes"] == 0
    assert result["storage"]["used_bytes"] > 0
    assert result["storage"]["oldest_ms"] == 100
    assert result["sample_count"] == 2
    assert result["downsampled"] is True


def test_query_downsamples_into_deterministic_time_buckets(
    tmp_path: Path,
) -> None:
    history = _history_module()
    store = history.ObservationHistoryStore(tmp_path, lambda: 0)
    samples = (
        (100, 0.4),
        (110, 0.1),
        (120, 0.3),
        (130, 0.8),
        (140, 0.2),
        (150, 0.6),
    )
    for captured_at_ms, value in samples:
        assert store.append_snapshot(
            "session-a",
            _snapshot(value),
            captured_at_ms=captured_at_ms,
        )

    result = store.query(
        "session-a",
        group="emotion",
        from_ms=None,
        to_ms=None,
        max_points=2,
    )

    assert result["sample_count"] == 6
    assert result["downsampled"] is True
    assert len(result["points"]) == 2
    assert [
        (
            point["from_ms"],
            point["to_ms"],
            point["first"]["warmth"],
            point["last"]["warmth"],
            point["min"]["warmth"],
            point["max"]["warmth"],
        )
        for point in result["points"]
    ] == [
        (100, 120, 0.4, 0.3, 0.1, 0.4),
        (130, 150, 0.8, 0.6, 0.2, 0.8),
    ]
    assert result == store.query(
        "session-a",
        group="emotion",
        from_ms=None,
        to_ms=None,
        max_points=2,
    )


def test_query_uses_one_bucket_per_sample_when_not_downsampled(
    tmp_path: Path,
) -> None:
    history = _history_module()
    store = history.ObservationHistoryStore(tmp_path, lambda: 0)
    _append_values(store, "session-a", [0.2, 0.4], start_ms=20)

    result = store.query(
        "session-a",
        group="emotion",
        from_ms=None,
        to_ms=None,
        max_points=2,
    )

    assert result["downsampled"] is False
    assert [point["from_ms"] for point in result["points"]] == [20, 21]
    assert [point["to_ms"] for point in result["points"]] == [20, 21]
    assert all(set(point) == {"from_ms", "to_ms", "first", "last", "min", "max"} for point in result["points"])
    assert all(
        point["first"] == point["last"] == point["min"] == point["max"]
        for point in result["points"]
    )


def test_query_aggregates_each_numeric_metric_across_missing_values(
    tmp_path: Path,
) -> None:
    history = _history_module()
    store = history.ObservationHistoryStore(tmp_path, lambda: 0)
    first = _snapshot(0.2)
    del first["_last_computation_result"]["emotion"]["warmth"]
    first["_last_computation_result"]["emotion"]["arousal"] = 0.1
    second = _snapshot(0.5)
    del second["_last_computation_result"]["emotion"]["arousal"]

    assert store.append_snapshot("session-a", first, captured_at_ms=100)
    assert store.append_snapshot("session-a", second, captured_at_ms=200)

    [bucket] = store.query(
        "session-a",
        group="emotion",
        from_ms=None,
        to_ms=None,
        max_points=1,
    )["points"]

    assert bucket["first"]["arousal"] == 0.1
    assert bucket["last"]["arousal"] == 0.1
    assert bucket["first"]["warmth"] == 0.5
    assert bucket["last"]["warmth"] == 0.5
    assert bucket["min"]["warmth"] == 0.5
    assert bucket["max"]["warmth"] == 0.5


def test_query_routing_and_expression_drop_discrete_values(
    tmp_path: Path,
) -> None:
    history = _history_module()
    store = history.ObservationHistoryStore(tmp_path, lambda: 0)
    assert store.append_snapshot(
        "session-a",
        _snapshot(),
        captured_at_ms=100,
    )

    [routing] = store.query(
        "session-a",
        group="routing",
        from_ms=None,
        to_ms=None,
        max_points=None,
    )["points"]
    [expression] = store.query(
        "session-a",
        group="expression",
        from_ms=None,
        to_ms=None,
        max_points=None,
    )["points"]

    assert routing["first"] == {"resonance": 7, "skip": 2}
    assert routing["last"] == routing["min"] == routing["max"] == routing["first"]
    assert "route" not in json.dumps(routing)
    assert "mode" not in json.dumps(expression)
    assert all(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for summary in ("first", "last", "min", "max")
        for value in expression[summary].values()
    )


def test_unknown_session_returns_empty_strict_history_response(
    tmp_path: Path,
) -> None:
    history = _history_module()
    store = history.ObservationHistoryStore(tmp_path, lambda: 0)

    result = store.query(
        "missing-session",
        group="timing",
        from_ms=10,
        to_ms=20,
        max_points=20,
    )

    assert set(result) == {
        "schema_version",
        "session",
        "group",
        "points",
        "sample_count",
        "downsampled",
        "partial",
        "storage",
    }
    assert result["schema_version"] == "sylanne.observation.history.v1"
    assert result["session"] == "missing-session"
    assert result["group"] == "timing"
    assert result["points"] == []
    assert result["sample_count"] == 0
    assert result["downsampled"] is False
    assert result["partial"] is False


def test_query_skips_old_rows_without_numeric_values_for_requested_group(
    tmp_path: Path,
) -> None:
    history = _history_module()
    old_snapshot = _snapshot()
    del old_snapshot["computation"]["timing"]
    old_row = history.project_observation(
        "session-a",
        old_snapshot,
        100,
    )
    del old_row["groups"]["timing"]
    old_row["digest"] = history._digest_payload(old_row)
    session_dir = tmp_path / hashlib.sha256(b"session-a").hexdigest()
    session_dir.mkdir(parents=True)
    (session_dir / "segment-00000001.jsonl").write_bytes(
        json.dumps(
            old_row,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    store = history.ObservationHistoryStore(tmp_path, lambda: 0)

    result = store.query(
        "session-a",
        group="timing",
        from_ms=None,
        to_ms=None,
        max_points=1,
    )

    assert result["points"] == []
    assert result["sample_count"] == 0
    assert result["downsampled"] is False
    assert result["partial"] is False
    assert result["storage"]["segment_count"] == 1
    assert result["storage"]["oldest_ms"] == 100
    assert result["storage"]["used_bytes"] > 0


def test_storage_used_bytes_counts_manifest_and_segments_but_not_temp(
    tmp_path: Path,
) -> None:
    history = _history_module()
    store = history.ObservationHistoryStore(tmp_path, lambda: 0)
    assert store.append_snapshot("session-a", _snapshot(0.2), captured_at_ms=100)
    manifest = tmp_path / "manifest.json"
    segments = _jsonl_paths(tmp_path)
    (tmp_path / "manifest.json.tmp").write_bytes(b"temporary-unmanaged-bytes")

    storage = store.query(
        "session-a",
        group="emotion",
        from_ms=None,
        to_ms=None,
        max_points=None,
    )["storage"]

    assert storage["used_bytes"] == manifest.stat().st_size + sum(path.stat().st_size for path in segments)


def test_unlimited_budget_never_deletes_segments(tmp_path: Path) -> None:
    history = _history_module()
    store = history.ObservationHistoryStore(
        tmp_path,
        lambda: 0,
        segment_bytes=1,
    )
    _append_values(store, "session-a", [0.1, 0.2, 0.3, 0.4])
    before = _jsonl_paths(tmp_path)

    assert store.maintenance() is False
    assert _jsonl_paths(tmp_path) == before
    assert len(before) == 4


def test_cleanup_deletes_at_most_one_oldest_closed_segment_per_pass(
    tmp_path: Path,
) -> None:
    history = _history_module()
    limit = [0]
    store = history.ObservationHistoryStore(
        tmp_path,
        lambda: limit[0],
        segment_bytes=1,
    )
    _append_values(store, "session-a", [0.1, 0.2, 0.3, 0.4])
    before = _jsonl_paths(tmp_path)
    oldest = tmp_path / hashlib.sha256("session-a".encode("utf-8")).hexdigest() / "segment-00000001.jsonl"
    limit[0] = 1

    assert store.append_snapshot("session-a", _snapshot(0.5), captured_at_ms=2_000)
    after_append = _jsonl_paths(tmp_path)

    assert len(before - after_append) == 1
    assert oldest not in after_append
    assert len(after_append - before) == 1
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    session_meta = next(iter(manifest["sessions"].values()))
    active = tmp_path / session_meta["active_segment"]
    assert active in after_append

    before_maintenance = set(after_append)
    assert store.maintenance() is True
    assert len(before_maintenance - _jsonl_paths(tmp_path)) == 1
    assert active in _jsonl_paths(tmp_path)


def test_cleanup_orders_closed_segments_by_oldest_sample_first(
    tmp_path: Path,
) -> None:
    history = _history_module()
    encoded_row_bytes = (
        len(
            json.dumps(
                history.project_observation("session-a", _snapshot(0.1), 100),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        + 1
    )
    limit = [0]
    store = history.ObservationHistoryStore(
        tmp_path,
        lambda: limit[0],
        segment_bytes=encoded_row_bytes * 2 + 100,
    )
    for captured_at_ms, value in ((100, 0.1), (1_000, 0.2), (2_000, 0.3)):
        assert store.append_snapshot(
            "session-a",
            _snapshot(value),
            captured_at_ms=captured_at_ms,
        )
    for captured_at_ms, value in ((500, 0.4), (600, 0.5), (2_100, 0.6)):
        assert store.append_snapshot(
            "session-b",
            _snapshot(value),
            captured_at_ms=captured_at_ms,
        )

    key_a = hashlib.sha256("session-a".encode("utf-8")).hexdigest()
    key_b = hashlib.sha256("session-b".encode("utf-8")).hexdigest()
    closed_a = tmp_path / key_a / "segment-00000001.jsonl"
    closed_b = tmp_path / key_b / "segment-00000001.jsonl"
    active_a = tmp_path / key_a / "segment-00000002.jsonl"
    active_b = tmp_path / key_b / "segment-00000002.jsonl"
    assert all(path.is_file() for path in (closed_a, closed_b, active_a, active_b))
    limit[0] = 1

    assert store.maintenance() is True

    assert not closed_a.exists()
    assert closed_b.exists()
    assert active_a.exists()
    assert active_b.exists()


def test_repeated_maintenance_reaches_ninety_percent_cleanup_target(
    tmp_path: Path,
) -> None:
    history = _history_module()
    limit = [0]
    store = history.ObservationHistoryStore(
        tmp_path,
        lambda: limit[0],
        segment_bytes=1,
    )
    _append_values(
        store,
        "session-a",
        [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
    )
    initial = store.query("session-a", group="emotion", from_ms=None, to_ms=None, max_points=None)["storage"][
        "used_bytes"
    ]
    limit[0] = initial // 2

    for _ in range(20):
        if not store.maintenance():
            break

    storage = store.query("session-a", group="emotion", from_ms=None, to_ms=None, max_points=None)["storage"]
    assert storage["used_bytes"] <= int(limit[0] * 0.9)
    assert storage["cleanup_active"] is False
    assert len(_jsonl_paths(tmp_path)) >= 1


def test_duplicate_append_passes_continue_cleanup_until_target(
    tmp_path: Path,
) -> None:
    history = _history_module()
    limit = [0]
    store = history.ObservationHistoryStore(
        tmp_path,
        lambda: limit[0],
        segment_bytes=1,
    )
    values = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    _append_values(store, "session-a", values)
    initial = store.query("session-a", group="emotion", from_ms=None, to_ms=None, max_points=None)["storage"][
        "used_bytes"
    ]
    limit[0] = initial // 2

    for captured_at_ms in range(3_000, 3_020):
        assert not store.append_snapshot(
            "session-a",
            _snapshot(values[-1]),
            captured_at_ms=captured_at_ms,
        )
        storage = store.query(
            "session-a",
            group="emotion",
            from_ms=None,
            to_ms=None,
            max_points=None,
        )["storage"]
        if not storage["cleanup_active"] and storage["used_bytes"] <= int(limit[0] * 0.9):
            break

    assert storage["used_bytes"] <= int(limit[0] * 0.9)
    assert storage["cleanup_active"] is False


def test_multiple_sessions_share_one_budget_and_oldest_is_global(
    tmp_path: Path,
) -> None:
    history = _history_module()
    limit = [0]
    store = history.ObservationHistoryStore(
        tmp_path,
        lambda: limit[0],
        segment_bytes=1,
    )
    _append_values(store, "session/a", [0.1, 0.2, 0.3], start_ms=100)
    _append_values(store, "session-b", [0.4, 0.5, 0.6], start_ms=200)
    key_a = hashlib.sha256("session/a".encode("utf-8")).hexdigest()
    oldest_a = tmp_path / key_a / "segment-00000001.jsonl"
    assert oldest_a.is_file()
    limit[0] = 1

    assert store.append_snapshot("session-b", _snapshot(0.7), captured_at_ms=300)

    assert not oldest_a.exists()
    assert any(path.parent.name == key_a for path in _jsonl_paths(tmp_path))
    assert any(
        path.parent.name == hashlib.sha256("session-b".encode("utf-8")).hexdigest() for path in _jsonl_paths(tmp_path)
    )


def test_session_context_uses_one_store_and_rebinds_new_and_cached_hosts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_context_module = importlib.import_module("sylanne_alpha.session_context")
    state_store_module = importlib.import_module("sylanne_alpha.session_state_store")

    class FakeRuntime:
        def __init__(self) -> None:
            self.sink: Any = None

        def set_observation_sink(self, sink: Any) -> None:
            self.sink = sink

        def load_buffer(self, _session: str) -> None:
            return None

    class FakeComputation:
        def __init__(self) -> None:
            self.encoder = object()

        def replace_encoder(self, encoder: object) -> None:
            self.encoder = encoder

    class FakeHost:
        def __init__(self, root: str, session_key: str) -> None:
            self.root = root
            self.session_key = session_key
            self.runtime = FakeRuntime()
            self.kernel = SimpleNamespace(
                personality={},
                computation=FakeComputation(),
                body=SimpleNamespace(memory={}),
                _personality=lambda: {},
            )

    class FakePlugin:
        _MAX_HOSTS = 50
        _shared_encoder = None

        def __init__(self) -> None:
            self.config = {"sylanne_webui_history_storage_limit_mb": -5}
            self._config = self.config
            self._store = state_store_module.SessionStateStore()

    monkeypatch.setattr(session_context_module, "SylanneAlphaHost", FakeHost)
    monkeypatch.setattr(
        session_context_module,
        "resolve_data_root",
        lambda _config: str(tmp_path),
    )
    plugin = FakePlugin()
    context = session_context_module.SessionContext(plugin)
    monkeypatch.setattr(context, "_schedule_person_profile_seed", lambda *a, **k: None)
    monkeypatch.setattr(
        context,
        "memory_system_for_session",
        lambda _session: SimpleNamespace(derive_params=lambda _p: None),
    )
    monkeypatch.setattr(context, "memory_system_has_content", lambda _memory: True)

    created = context.host("session-a")
    first_sink = created.runtime.sink
    assert callable(first_sink)
    assert context.observation_history_store.root == tmp_path / "observation-history"
    metadata = context.observation_history_store.query(
        "unknown", group="emotion", from_ms=None, to_ms=None, max_points=None
    )["storage"]
    assert metadata["limit_bytes"] == 128 * 1024 * 1024

    created.runtime.sink = None
    cached = context.host("session-a")
    assert cached is created
    assert callable(cached.runtime.sink)
    assert cached.runtime.sink is first_sink

    plugin.config["sylanne_webui_history_storage_limit_mb"] = 0
    assert (
        context.observation_history_store.query("unknown", group="emotion", from_ms=None, to_ms=None, max_points=None)[
            "storage"
        ]["limit_bytes"]
        == 0
    )
    plugin.config["sylanne_webui_history_storage_limit_mb"] = 2
    assert (
        context.observation_history_store.query("unknown", group="emotion", from_ms=None, to_ms=None, max_points=None)[
            "storage"
        ]["limit_bytes"]
        == 2 * 1024 * 1024
    )


def test_history_limit_configuration_schema_is_exact() -> None:
    schema = json.loads(Path("_conf_schema.json").read_text(encoding="utf-8"))

    assert schema["sylanne_webui_history_storage_limit_mb"] == {
        "description": "全局观测历史容量上限（MB）；0 表示无限制，不按天过期。",
        "type": "int",
        "default": 128,
        "hint": "记录长期保留；超过上限后按最旧已封闭分段逐步清理。",
    }
