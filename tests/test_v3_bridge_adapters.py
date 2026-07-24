"""RED/GREEN tests for the v3 bridge observation/memory/group adapters.

The adapters may read already-authorized immutable v2 fact DTOs, but must be
structurally incapable of reaching a database, recall, an LLM, a callback, or a
live domain: they accept only frozen fact DTOs plus primitives, and their
modules import nothing that can perform I/O.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from sylanne_alpha.v2core.shadow_snapshot import V2TurnObservationSnapshotV1
from sylanne_alpha.v3bridge import group_view_adapter, memory_view_adapter, observation_adapter
from sylanne_alpha.v3bridge.actual_action import ActualAction
from sylanne_alpha.v3bridge.group_view_adapter import GroupView, build_group_view
from sylanne_alpha.v3bridge.memory_view_adapter import MemoryView, build_memory_view
from sylanne_alpha.v3bridge.observation_adapter import (
    build_observation_facts,
    build_outcome_frame,
    encode_snapshot,
)
from sylanne_alpha.v3core.contracts import Action, TurnContextClass
from sylanne_alpha.v3core.observation.models import ObservationFacts, ObservationFrame, OutcomeFrame


_ADAPTER_MODULES = (observation_adapter, memory_view_adapter, group_view_adapter)

# Modules a pure fact adapter must never touch (DB / network / host / live domain).
_FORBIDDEN_IMPORT_PREFIXES = (
    "astrbot",
    "sqlite3",
    "socket",
    "subprocess",
    "asyncio",
    "threading",
    "concurrent.futures",
    "requests",
    "aiohttp",
    "httpx",
    "urllib",
    "sylanne_alpha._engine",
    "sylanne_alpha.llm_request_pipeline",
    "sylanne_alpha.llm_response_pipeline",
)


def _snapshot(
    *,
    memory: bool = True,
    group_scope: str | None = "SAME_GROUP",
) -> V2TurnObservationSnapshotV1:
    kwargs: dict[str, object] = dict(
        body_warmth=0.8,
        body_tension=0.2,
        body_repair_pressure=0.3,
        body_intimacy_gravity=0.5,
        body_surprise=0.6,
        body_mean_surprise=0.4,
        body_precision=0.7,
        body_scar=1.0,
        body_strain=0.5,
        body_sovereignty=0.9,
        body_exhaustion=0.25,
        body_expression_drive=0.4,
        body_threshold_drift=-0.5,
        body_epoch=7,
        body_void_pressure=2.0,
        body_load=1.0,
        body_plasticity=0.5,
        body_boundary_pressure=0.1,
        text_length=10,
        text_warm=2.0,
        text_cold=0.5,
        text_distress=0.35,
        text_question=True,
        text_exclaim=0.15,
        text_punct=0.4,
        text_valence_cue=0.65,
        text_engagement_cue=0.65,
        history_present=True,
        gap_seconds=60.0,
    )
    if memory:
        kwargs.update(
            memory_relevance=0.7,
            memory_confidence=0.6,
            memory_temperature=0.5,
            memory_age_seconds=120.0,
            memory_valid_mask=0b1111,
            memory_provenance="AUTHORITATIVE_TURN",
            memory_source_revision=3,
            memory_source_time=100.0,
            memory_privacy_scope="PERSON",
        )
    if group_scope is not None:
        kwargs.update(
            group_familiarity=0.4,
            group_engagement=0.5,
            group_tension=0.3,
            group_activity=0.6,
            group_valid_mask=0b1111,
            group_provenance="AUTHORITATIVE_TURN",
            group_source_revision=2,
            group_source_time=90.0,
            group_privacy_scope=group_scope,
        )
    return V2TurnObservationSnapshotV1(**kwargs)  # type: ignore[arg-type]


# --- structural isolation proofs -------------------------------------------------


def test_adapter_modules_import_nothing_capable_of_io() -> None:
    for module in _ADAPTER_MODULES:
        path = Path(inspect.getfile(module))
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != "open", module.__name__
        for name in names:
            for forbidden in _FORBIDDEN_IMPORT_PREFIXES:
                assert not (name == forbidden or name.startswith(forbidden + ".")), (module.__name__, name)


def test_adapter_entrypoints_accept_only_frozen_facts_and_primitives() -> None:
    allowed_annotations = {
        "V2TurnObservationSnapshotV1",
        "TurnContextClass",
        "ActualAction",
        "bool",
        "ObservationFrame",
    }
    forbidden_parameter_names = {"plugin", "event", "callback", "conn", "db", "session", "loop", "recall", "llm"}
    for func in (build_observation_facts, encode_snapshot, build_memory_view, build_group_view, build_outcome_frame):
        signature = inspect.signature(func)
        for name, parameter in signature.parameters.items():
            assert name not in forbidden_parameter_names, (func.__name__, name)
            annotation = parameter.annotation
            rendered = annotation if isinstance(annotation, str) else getattr(annotation, "__name__", str(annotation))
            # Optional annotations render as "Action | None"; the leading token is what matters.
            head = rendered.split("|")[0].strip()
            assert head in allowed_annotations, (func.__name__, name, rendered)


def test_snapshot_facts_carry_no_host_handles() -> None:
    snapshot = _snapshot()
    for field_name in snapshot.__dataclass_fields__:
        value = getattr(snapshot, field_name)
        assert value is None or type(value) in (bool, int, float, str), field_name
        assert not callable(value), field_name


# --- observation adapter --------------------------------------------------------


def test_observation_adapter_builds_immutable_core_facts() -> None:
    facts = build_observation_facts(_snapshot(), TurnContextClass.ADDRESSED, ActualAction.SPEAK)
    assert type(facts) is ObservationFacts
    assert facts.context is TurnContextClass.ADDRESSED
    assert facts.previous_action is Action.SPEAK
    # Derived channels remain None; value channels are populated.
    for index in (27, 28, 29, 32, 33, 34, 35):
        assert facts.raw_values[index] is None
    assert facts.raw_values[0] == 0.8
    assert facts.raw_values[22] == 1.0  # question bool -> 1.0
    assert facts.raw_values[13] == 7.0  # epoch int -> float


def test_encode_snapshot_maps_unknown_actual_action_to_cleared_channels() -> None:
    frame = encode_snapshot(_snapshot(), TurnContextClass.AMBIENT, ActualAction.UNKNOWN)
    assert type(frame) is ObservationFrame
    for index in (32, 33, 34, 35):
        assert not (frame.valid_mask >> index) & 1
    frame_unmatched = encode_snapshot(_snapshot(), TurnContextClass.AMBIENT, ActualAction.UNMATCHED_RESPONSE)
    assert not any((frame_unmatched.valid_mask >> index) & 1 for index in (32, 33, 34, 35))


def test_encode_snapshot_rejects_context_bits_that_contradict_the_class() -> None:
    # Snapshot says addressed=True, but caller claims AMBIENT context: contradiction.
    conflicting = V2TurnObservationSnapshotV1(body_warmth=0.5, addressed=True)
    with pytest.raises(ValueError):
        encode_snapshot(conflicting, TurnContextClass.AMBIENT, ActualAction.HOLD)


def test_encode_snapshot_is_deterministic() -> None:
    first = encode_snapshot(_snapshot(), TurnContextClass.ADDRESSED, ActualAction.SPEAK)
    second = encode_snapshot(_snapshot(), TurnContextClass.ADDRESSED, ActualAction.SPEAK)
    assert first == second


# --- memory adapter -------------------------------------------------------------


def test_memory_view_projects_authorized_facts() -> None:
    view = build_memory_view(_snapshot(memory=True))
    assert type(view) is MemoryView
    assert view.valid_mask == 0b1111
    assert view.privacy_scope == "PERSON"
    assert (view.relevance, view.confidence, view.temperature, view.age_seconds) == (0.7, 0.6, 0.5, 120.0)


def test_memory_view_is_empty_when_no_authorized_facts() -> None:
    view = build_memory_view(_snapshot(memory=False))
    assert view.valid_mask == 0
    assert view.privacy_scope == "NONE"
    assert view.relevance is None


# --- group adapter / cross-group privacy ---------------------------------------


def test_group_view_projects_authorized_same_group_facts() -> None:
    view = build_group_view(_snapshot(group_scope="SAME_GROUP"), cross_group_allowed=False)
    assert type(view) is GroupView
    assert view.valid_mask == 0b1111
    assert view.privacy_scope == "SAME_GROUP"
    assert (view.familiarity, view.engagement, view.tension, view.activity) == (0.4, 0.5, 0.3, 0.6)


def test_cross_group_facts_are_invalid_when_cross_group_disabled() -> None:
    view = build_group_view(_snapshot(group_scope="CROSS_GROUP"), cross_group_allowed=False)
    assert view.valid_mask == 0
    assert view.privacy_scope == "NONE"
    # Never fabricated: no value survives.
    assert (view.familiarity, view.engagement, view.tension, view.activity) == (None, None, None, None)


def test_cross_group_facts_pass_when_cross_group_enabled() -> None:
    view = build_group_view(_snapshot(group_scope="CROSS_GROUP"), cross_group_allowed=True)
    assert view.valid_mask == 0b1111
    assert view.privacy_scope == "CROSS_GROUP"


def test_group_view_is_empty_without_authorized_facts() -> None:
    view = build_group_view(_snapshot(group_scope=None), cross_group_allowed=True)
    assert view.valid_mask == 0
    assert view.privacy_scope == "NONE"


# --- outcome frame delegated through the bridge ---------------------------------


def test_bridge_build_outcome_frame_delegates_to_core_projection() -> None:
    frame = encode_snapshot(_snapshot(), TurnContextClass.ADDRESSED, ActualAction.SPEAK)
    outcome = build_outcome_frame(frame)
    assert type(outcome) is OutcomeFrame
    assert 0 <= outcome.valid_mask < (1 << 8)
    assert all(-1.0 <= value <= 1.0 for value in outcome.y)
