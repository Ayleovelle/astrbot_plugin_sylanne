from __future__ import annotations

import ast
import math
from dataclasses import FrozenInstanceError, fields, is_dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, get_type_hints

import pytest

from sylanne_alpha.v2core.shadow_snapshot import (
    RESPONSE_ROUTE_KINDS,
    SeedSnapshotUnavailable,
    V2_RESPONSE_CANDIDATE_SCHEMA_V1,
    V2_SEED_SNAPSHOT_SCHEMA_V1,
    V2_TURN_OBSERVATION_SCHEMA_V1,
    V2ResponseCandidateV1,
    V2SeedSnapshotV1,
    V2TurnObservationSnapshotV1,
    freeze_seed_snapshot_fallback,
    freeze_seed_snapshot_owned,
    normalize_reply_kind_token,
)


class _Domain:
    def __init__(self, state: dict[str, Any], *, lock: Any = None) -> None:
        self.state = state
        self.lock = lock
        self.calls = 0

    def to_dict(self) -> dict[str, Any]:
        if self.lock is not None:
            assert self.lock.held is True
        self.calls += 1
        return self.state


class _BodyPort:
    def __init__(self, body: object, *, lock: Any = None) -> None:
        self.body = body
        self.lock = lock
        self.observe_calls = 0

    def observe(self) -> object:
        if self.lock is not None:
            assert self.lock.held is True
        self.observe_calls += 1
        return self.body

    def snapshot(self) -> dict[str, object]:
        raise AssertionError("seed export must use public observe(), not snapshot()")


class _TrackingAsyncLock:
    def __init__(self) -> None:
        self.held = False
        self.enter_count = 0
        self.exit_count = 0

    async def __aenter__(self) -> _TrackingAsyncLock:
        assert self.held is False
        self.held = True
        self.enter_count += 1
        return self

    async def __aexit__(self, *_exc: object) -> None:
        assert self.held is True
        self.held = False
        self.exit_count += 1


def _body() -> SimpleNamespace:
    return SimpleNamespace(
        session_key="raw-session-must-not-survive",
        turns=91,
        warmth=0.25,
        tension=0.4,
        repair_pressure=0.2,
        intimacy_gravity=0.8,
        surprise=0.3,
        mean_surprise=0.45,
        precision=0.7,
        scar=0.1,
        strain=0.2,
        sovereignty=0.9,
        exhaustion=0.15,
        expression_drive=-0.35,
        threshold_drift=0.05,
        epoch=7,
        void_pressure=1.25,
        load=0.6,
        plasticity=0.55,
        boundary_pressure=0.4,
        personality={"raw-personality": 1.0},
        raw={"secret": "must-not-survive"},
    )


def _runtime(*, lock: _TrackingAsyncLock | None = None) -> tuple[dict[str, object], dict[str, _Domain], _BodyPort]:
    emotion_state = {
        "fast_ema": 0.3,
        "slow_ema": -0.1,
        "unexpressed": 1.75,
        "samples": [0.1, 0.2],
        "raw_text": "must-not-survive",
    }
    user_state = {
        "hesitation_ema": 0.12,
        "bond_ema": 0.76,
        "style_sketch": {
            "len": 14.0,
            "punct": 0.5,
            "warmth": -0.2,
            "unknown": 999.0,
        },
        "last_user_text": "must-not-survive",
    }
    narrative_state = {
        "ossification": {
            "warmth": 0.2,
            "tension": 0.3,
            "repair_pressure": 0.4,
            "unknown": 1.0,
        },
        "baseline_traits": {
            "curiosity": 0.6,
            "warmth_bias": 0.7,
            "sovereignty_guard": 0.8,
            "patience": 0.9,
            "unknown": 1.0,
        },
        "anchors": [{"note": "must-not-survive"}],
    }
    adaptation_state = {
        "style_target": {"len": 12.0, "punct": 0.4, "warmth": 0.1, "unknown": 7.0},
        "expr": {"verbosity": 0.2, "formality": 0.3, "directness": 0.4, "unknown": 8.0},
        "coping": {
            "accompany_silence": 0.51,
            "gentle_probe": 0.52,
            "affirm_empathize": 0.53,
            "self_disclose": 0.54,
            "unknown": 9.0,
        },
        "topics": {"raw topic text": {"aff": 1.0}},
    }
    domains = {
        "emotion": _Domain(emotion_state, lock=lock),
        "usermodel": _Domain(user_state, lock=lock),
        "narrative": _Domain(narrative_state, lock=lock),
        "adaptation": _Domain(adaptation_state, lock=lock),
    }
    body_port = _BodyPort(_body(), lock=lock)
    return {"domains": domains, "body_port": body_port}, domains, body_port


def _walk(value: object) -> list[object]:
    result = [value]
    if is_dataclass(value) and not isinstance(value, type):
        for item in fields(value):
            result.extend(_walk(getattr(value, item.name)))
    elif isinstance(value, tuple):
        for item in value:
            result.extend(_walk(item))
    return result


def test_shadow_snapshot_contracts_are_frozen_versioned_and_have_no_host_escape_hatches() -> None:
    turn = V2TurnObservationSnapshotV1()
    seed = V2SeedSnapshotV1()
    candidate = V2ResponseCandidateV1()

    assert turn.schema_version == V2_TURN_OBSERVATION_SCHEMA_V1
    assert seed.schema_version == V2_SEED_SNAPSHOT_SCHEMA_V1
    assert candidate.schema_version == V2_RESPONSE_CANDIDATE_SCHEMA_V1
    for dto in (turn, seed, candidate):
        assert is_dataclass(dto)
        assert dto.__slots__
        with pytest.raises(FrozenInstanceError):
            dto.schema_version = "mutated"  # type: ignore[misc]

    forbidden_names = {
        "event",
        "request",
        "reply",
        "callback",
        "host",
        "session_key",
        "raw_text",
        "message_text",
        "prompt",
        "memory_text",
        "group_text",
    }
    for contract in (V2TurnObservationSnapshotV1, V2SeedSnapshotV1, V2ResponseCandidateV1):
        assert not forbidden_names.intersection(item.name for item in fields(contract))
        annotation_text = " ".join(repr(hint) for hint in get_type_hints(contract).values())
        assert "typing.Any" not in annotation_text
        assert "<class 'object'>" not in annotation_text
        assert "Callable" not in annotation_text


def test_turn_snapshot_accepts_only_fixed_finite_structured_facts() -> None:
    turn = V2TurnObservationSnapshotV1(
        body_warmth=0.2,
        body_epoch=3,
        text_length=8,
        text_question=True,
        addressed=True,
        history_present=True,
        gap_seconds=12.5,
        memory_relevance=0.8,
        memory_valid_mask=0b0001,
        memory_provenance="AUTHORITATIVE_TURN",
        memory_source_revision=4,
        memory_source_time=10.0,
        memory_privacy_scope="SESSION",
    )
    assert turn.text_length == 8
    assert turn.memory_relevance == 0.8
    assert not any(isinstance(value, (dict, list, set)) for value in _walk(turn))

    for field_name, value in (
        ("body_warmth", math.nan),
        ("text_warm", math.inf),
        ("gap_seconds", -math.inf),
    ):
        with pytest.raises(ValueError, match="finite"):
            V2TurnObservationSnapshotV1(**{field_name: value})
    with pytest.raises(TypeError, match="bool"):
        V2TurnObservationSnapshotV1(text_question=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="mask"):
        V2TurnObservationSnapshotV1(memory_relevance=0.5)
    with pytest.raises(ValueError, match="provenance"):
        V2TurnObservationSnapshotV1(memory_provenance="raw-memory-text")


def test_response_candidate_contains_only_structured_route_evidence() -> None:
    candidate = V2ResponseCandidateV1(
        route_kind="ORDINARY_TEXT",
        reply_kind="SPEAK",
        part_count=1,
        correlation_proven=True,
        after_message_sent=True,
    )
    assert candidate.reply_kind == "SPEAK"
    assert candidate.route_kind == "ORDINARY_TEXT"
    assert candidate.part_count == 1
    assert all(
        is_dataclass(value) or value is None or type(value) in (str, int, bool)
        for value in _walk(candidate)
    )

    with pytest.raises(ValueError, match="part_count"):
        V2ResponseCandidateV1(
            route_kind="ORDINARY_TEXT",
            reply_kind="SPEAK",
            correlation_proven=True,
        )
    with pytest.raises(ValueError, match="reply_kind"):
        V2ResponseCandidateV1(route_kind="SILENT", reply_kind="raw reply text")
    with pytest.raises(ValueError, match="route_kind"):
        V2ResponseCandidateV1(route_kind="raw route text")
    with pytest.raises(ValueError, match="all_segments_succeeded"):
        V2ResponseCandidateV1(
            route_kind="ORDINARY_TEXT",
            reply_kind="SPEAK",
            part_count=2,
            all_segments_succeeded=True,
            correlation_proven=True,
        )

    one_segment_takeover = V2ResponseCandidateV1(
        route_kind="SEGMENTED_TEXT",
        reply_kind="SPEAK",
        part_count=1,
        correlation_proven=True,
        all_segments_succeeded=True,
    )
    assert one_segment_takeover.part_count == 1
    with pytest.raises(ValueError, match="part_count"):
        V2ResponseCandidateV1(
            route_kind="ORDINARY_TEXT",
            reply_kind="SPEAK",
            part_count=257,
            correlation_proven=True,
        )


@pytest.mark.parametrize(
    "candidate",
    [
        V2ResponseCandidateV1(
            route_kind="PROVIDER_FAILURE",
            correlation_proven=True,
        ),
        V2ResponseCandidateV1(
            route_kind="PROACTIVE",
            correlation_proven=True,
            proactive_dispatched=True,
        ),
    ],
)
def test_response_candidate_route_is_a_stable_discriminated_union(
    candidate: V2ResponseCandidateV1,
) -> None:
    assert candidate.route_kind in RESPONSE_ROUTE_KINDS
    with pytest.raises(ValueError, match="after_message_sent"):
        V2ResponseCandidateV1(
            route_kind="SILENT",
            reply_kind="SILENT",
            correlation_proven=True,
            after_message_sent=True,
        )
    with pytest.raises(ValueError, match="PROACTIVE"):
        V2ResponseCandidateV1(
            route_kind="PROACTIVE",
            reply_kind="SILENT",
            correlation_proven=True,
            proactive_dispatched=True,
        )


def test_reply_kind_normalization_survives_enum_class_replacement() -> None:
    from enum import Enum

    class OldReplyKind(Enum):
        SPEAK = "speak"

    class ReloadedReplyKind(Enum):
        SPEAK = "speak"

    assert OldReplyKind.SPEAK is not ReloadedReplyKind.SPEAK
    assert normalize_reply_kind_token(OldReplyKind.SPEAK) == "SPEAK"
    assert normalize_reply_kind_token(ReloadedReplyKind.SPEAK) == "SPEAK"
    assert normalize_reply_kind_token("speak") == "SPEAK"
    candidate = V2ResponseCandidateV1(
        route_kind="ORDINARY_TEXT",
        reply_kind=OldReplyKind.SPEAK,  # type: ignore[arg-type]
        part_count=1,
        correlation_proven=True,
    )
    assert candidate.reply_kind == "SPEAK"


def test_owned_seed_freeze_copies_only_finite_fixed_key_values() -> None:
    rt, domains, body_port = _runtime()
    snapshot = freeze_seed_snapshot_owned(rt)

    assert snapshot.schema_version == V2_SEED_SNAPSHOT_SCHEMA_V1
    assert snapshot.body_warmth == 0.25
    assert snapshot.body_epoch == 7
    assert snapshot.emotion_fast_ema == 0.3
    assert snapshot.emotion_slow_ema == -0.1
    assert snapshot.emotion_unexpressed == 1.75
    assert snapshot.user_hesitation_ema == 0.12
    assert snapshot.user_bond_ema == 0.76
    assert snapshot.user_style_len == 14.0
    assert snapshot.narrative_ossification_repair_pressure == 0.4
    assert snapshot.narrative_baseline_sovereignty_guard == 0.8
    assert snapshot.adaptation_style_warmth == 0.1
    assert snapshot.adaptation_expr_directness == 0.4
    assert snapshot.adaptation_coping_self_disclose == 0.54
    assert body_port.observe_calls == 1
    assert all(domain.calls == 1 for domain in domains.values())
    assert not any(isinstance(value, (dict, list, set)) for value in _walk(snapshot))
    assert "raw-session-must-not-survive" not in repr(snapshot)
    assert "must-not-survive" not in repr(snapshot)

    for domain in domains.values():
        domain.state.clear()
    body_port.body.warmth = 0.99
    assert snapshot.body_warmth == 0.25
    assert snapshot.user_style_len == 14.0


def test_owned_seed_freeze_turns_nonfinite_and_wrongly_typed_values_into_missing_facts() -> None:
    rt, domains, body_port = _runtime()
    domains["emotion"].state["fast_ema"] = math.nan
    domains["emotion"].state["slow_ema"] = math.inf
    domains["usermodel"].state["bond_ema"] = "0.75"
    domains["narrative"].state["baseline_traits"]["patience"] = True
    domains["adaptation"].state["expr"]["verbosity"] = -math.inf
    body_port.body.precision = math.nan
    body_port.body.epoch = True

    snapshot = freeze_seed_snapshot_owned(rt)

    assert snapshot.emotion_fast_ema is None
    assert snapshot.emotion_slow_ema is None
    assert snapshot.user_bond_ema is None
    assert snapshot.narrative_baseline_patience is None
    assert snapshot.adaptation_expr_verbosity is None
    assert snapshot.body_precision is None
    assert snapshot.body_epoch is None


def test_owned_seed_freeze_treats_extreme_integer_as_missing_instead_of_raising() -> None:
    rt, domains, body_port = _runtime()
    huge = 10**10000
    domains["emotion"].state["fast_ema"] = huge
    body_port.body.warmth = huge
    body_port.body.epoch = huge

    snapshot = freeze_seed_snapshot_owned(rt)

    assert snapshot.emotion_fast_ema is None
    assert snapshot.body_warmth is None
    assert snapshot.body_epoch is None


@pytest.mark.asyncio
async def test_fallback_freeze_uses_real_plugin_session_lock_and_releases_before_return() -> None:
    lock = _TrackingAsyncLock()
    rt, domains, body_port = _runtime(lock=lock)

    class _Plugin:
        def __init__(self) -> None:
            self._v2core_runtimes = {"session-a": rt}
            self.lock_keys: list[str] = []

        def _session_lock(self, session_key: str) -> _TrackingAsyncLock:
            self.lock_keys.append(session_key)
            return lock

    plugin = _Plugin()
    snapshot = await freeze_seed_snapshot_fallback(plugin, "session-a")

    assert snapshot.user_bond_ema == 0.76
    assert plugin.lock_keys == ["session-a"]
    assert lock.enter_count == lock.exit_count == 1
    assert lock.held is False
    assert all(domain.calls == 1 for domain in domains.values())
    assert body_port.observe_calls == 1


@pytest.mark.asyncio
async def test_fallback_freeze_fails_closed_without_the_production_lock_factory() -> None:
    class _Plugin:
        _v2core_runtimes: dict[str, object] = {}

    with pytest.raises(RuntimeError, match="_session_lock"):
        await freeze_seed_snapshot_fallback(_Plugin(), "session-a")


@pytest.mark.asyncio
async def test_fallback_freeze_marks_absent_runtime_unavailable_and_releases_lock() -> None:
    lock = _TrackingAsyncLock()

    class _Plugin:
        _v2core_runtimes: dict[str, object] = {}

        def _session_lock(self, _session_key: str) -> _TrackingAsyncLock:
            return lock

    with pytest.raises(SeedSnapshotUnavailable, match="runtime"):
        await freeze_seed_snapshot_fallback(_Plugin(), "missing")
    assert lock.enter_count == lock.exit_count == 1


@pytest.mark.asyncio
async def test_fallback_freeze_releases_lock_when_required_source_raises() -> None:
    lock = _TrackingAsyncLock()
    rt, domains, _body_port = _runtime(lock=lock)

    def _raise() -> dict[str, Any]:
        raise RuntimeError("source failed")

    domains["emotion"].to_dict = _raise  # type: ignore[method-assign]

    class _Plugin:
        _v2core_runtimes = {"session-a": rt}

        def _session_lock(self, _session_key: str) -> _TrackingAsyncLock:
            return lock

    with pytest.raises(SeedSnapshotUnavailable, match="emotion"):
        await freeze_seed_snapshot_fallback(_Plugin(), "session-a")
    assert lock.enter_count == lock.exit_count == 1
    assert lock.held is False


def test_owned_seed_freeze_rejects_mapping_proxies_with_live_behavior() -> None:
    from collections import UserDict

    rt, _domains, _body_port = _runtime()
    with pytest.raises(SeedSnapshotUnavailable, match="runtime"):
        freeze_seed_snapshot_owned(UserDict(rt))


def test_shadow_snapshot_module_never_imports_engine_or_mutates_host_extra() -> None:
    path = Path("sylanne_alpha/v2core/shadow_snapshot.py")
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert not any(name == "sylanne_alpha._engine" or name.startswith("sylanne_alpha._engine.") for name in imports)
    assert "set_extra" not in source
    assert "SessionLocks" not in source
    assert ".locks.turn" not in source
    assert "sylanne_alpha.v3bridge" not in source
    assert "_state_repository" not in source
