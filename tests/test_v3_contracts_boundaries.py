from __future__ import annotations

import ast
import hashlib
import io
import math
import struct
from dataclasses import FrozenInstanceError, dataclass, fields, is_dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType

import pytest

from sylanne_alpha.v3bridge import limits
from sylanne_alpha.v3bridge.build_flags import BUILD_CHANNEL, V3_SHADOW_ENABLED
from sylanne_alpha.v3bridge.limits import EffectiveV3Budget
from sylanne_alpha.v3bridge.models import LoadSnapshotV1, RepositoryAdmissionState
from sylanne_alpha.v3core import formula_v1 as formula
from sylanne_alpha.v3core import canonical
from sylanne_alpha.v3core.canonical import assert_valid_dto
from sylanne_alpha.v3core.contracts import (
    Action,
    ComputeProfile,
    CoreInvocation,
    SessionRef,
    TurnContextClass,
    TurnEnvelope,
    TurnKey,
    TurnSequence,
)
from sylanne_alpha.v3core.effects.models import (
    EFFECT_TYPES,
    EffectBundle,
    V3MetricEffect,
    V3StateEffect,
    V3TraceEffect,
)
from sylanne_alpha.v3core.state.models import PendingOutcome, V3State


def _session_ref() -> SessionRef:
    return SessionRef(key_id="key-v1", session_digest=b"s" * 32, session_generation=1)


def _profile() -> ComputeProfile:
    return ComputeProfile(
        profile_id="FULL_24_STDP",
        snn_enabled=True,
        ticks=24,
        stdp_enabled=True,
        reuse_last_summary=False,
        math_backend="scalar-v1",
        formula_version=formula.FORMULA_VERSION,
        model_version=formula.FORMULA_VERSION,
    )


def _envelope(observation: object = (0.0, 1.0)) -> TurnEnvelope:
    ref = _session_ref()
    return TurnEnvelope(
        turn_key=TurnKey(
            plugin_instance_id="plugin-instance",
            session_ref=ref,
            bridge_request_nonce="request-nonce",
            request_attempt=0,
        ),
        turn_id="turn-digest",
        sequence=TurnSequence(writer_epoch=7, local_sequence=11),
        compute_profile=_profile(),
        deterministic_seed=b"d" * 16,
        observation=observation,
        context=TurnContextClass.ADDRESSED,
    )


def _assert_frozen(instance: object, field_name: str) -> None:
    assert is_dataclass(instance)
    with pytest.raises(FrozenInstanceError):
        setattr(instance, field_name, getattr(instance, field_name))


def _matrix(rows: int, columns: int, triples: tuple[tuple[int, int, float], ...]) -> tuple[tuple[float, ...], ...]:
    result = [[0.0 for _ in range(columns)] for _ in range(rows)]
    for row, column, value in triples:
        result[row][column] = value
    return tuple(tuple(row) for row in result)


def _matrix_multiply(
    left: tuple[tuple[float, ...], ...],
    right: tuple[tuple[float, ...], ...],
) -> tuple[tuple[float, ...], ...]:
    return tuple(
        tuple(sum(left[row][item] * right[item][column] for item in range(len(right))) for column in range(len(right[0])))
        for row in range(len(left))
    )


def _imported_module_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_v3_contracts_are_frozen_and_sequence_partition_is_bridge_owned() -> None:
    sequence = TurnSequence(writer_epoch=7, local_sequence=11)
    assert tuple(field.name for field in fields(sequence)) == ("writer_epoch", "local_sequence")
    _assert_frozen(sequence, "local_sequence")

    ref = _session_ref()
    assert len(ref.session_digest) == 32
    _assert_frozen(ref, "session_generation")
    _assert_frozen(_profile(), "ticks")


def test_core_envelopes_have_no_runtime_or_host_escape_hatches() -> None:
    state = V3State(session_ref=_session_ref())
    invocation = CoreInvocation(
        envelope=_envelope(),
        base_state=state,
        projected_actual_outcome=None,
    )
    for contract in (TurnEnvelope, CoreInvocation, EffectBundle):
        names = {field.name for field in fields(contract)}
        assert not names & {"deadline", "timeout", "callback", "host", "event", "reply", "path"}
    _assert_frozen(invocation, "projected_actual_outcome")


@pytest.mark.parametrize(
    "bad_value",
    [
        pytest.param(lambda: None, id="callable"),
        pytest.param(Path("host-path"), id="path"),
        pytest.param(io.BytesIO(b"host-file"), id="file-handle"),
        pytest.param(object(), id="host-object"),
        pytest.param([1, 2], id="mutable-list"),
        pytest.param({"x": 1}, id="raw-dict"),
        pytest.param(float("nan"), id="nan"),
        pytest.param(float("inf"), id="infinity"),
    ],
)
def test_recursive_dto_validation_rejects_host_mutable_and_nonfinite_values(bad_value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        assert_valid_dto(bad_value)
    with pytest.raises((TypeError, ValueError)):
        _envelope(observation=(bad_value,))


def test_recursive_dto_validation_rejects_async_primitives() -> None:
    import asyncio

    with pytest.raises(TypeError):
        assert_valid_dto(asyncio.Lock())


def test_recursive_dto_validation_accepts_only_declared_immutable_dtos() -> None:
    envelope = _envelope(observation=(None, True, 7, 0.25, "ok", b"bytes", (Action.SPEAK,)))
    assert assert_valid_dto(envelope) is None


def test_recursive_dto_validation_rejects_undeclared_frozen_dataclasses_and_enums() -> None:
    @dataclass(frozen=True)
    class HostFrozenDataclass:
        value: int

    class HostEnum(Enum):
        VALUE = "value"

    with pytest.raises(TypeError):
        assert_valid_dto(HostFrozenDataclass(1))
    with pytest.raises(TypeError):
        assert_valid_dto(HostEnum.VALUE)


def test_core_canonical_registry_is_closed_after_one_explicit_bootstrap() -> None:
    @dataclass(frozen=True)
    class ExternalDto:
        value: int

    class ExternalEnum(Enum):
        VALUE = "value"

    assert type(canonical._DECLARED_DTO_TYPES) is frozenset
    assert type(canonical._DECLARED_ENUM_TYPES) is frozenset
    assert SessionRef in canonical._DECLARED_DTO_TYPES
    assert Action in canonical._DECLARED_ENUM_TYPES
    assert LoadSnapshotV1 not in canonical._DECLARED_DTO_TYPES
    assert RepositoryAdmissionState not in canonical._DECLARED_ENUM_TYPES
    with pytest.raises(RuntimeError, match="sealed"):
        canonical.declared_dto(ExternalDto)
    with pytest.raises(RuntimeError, match="sealed"):
        canonical.declared_enum(ExternalEnum)
    with pytest.raises(RuntimeError, match="sealed"):
        canonical._install_declared_types(dto_types=(), enum_types=())


def test_declared_enum_values_are_recursively_immutable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Action.SPEAK, "_value_", ["mutable"])
    with pytest.raises(TypeError, match="unsupported DTO type"):
        assert_valid_dto(Action.SPEAK)


@pytest.mark.parametrize(
    "factory",
    [
        pytest.param(lambda: SessionRef(key_id=1, session_digest=b"s" * 32, session_generation=1), id="session-key"),
        pytest.param(lambda: SessionRef(key_id="key", session_digest="s" * 32, session_generation=1), id="session-digest"),
        pytest.param(lambda: SessionRef(key_id="key", session_digest=b"s" * 32, session_generation=True), id="session-generation-bool"),
        pytest.param(lambda: TurnSequence(writer_epoch=True, local_sequence=1), id="sequence-bool"),
        pytest.param(
            lambda: TurnKey(
                plugin_instance_id="plugin",
                session_ref="not-a-session",
                bridge_request_nonce="nonce",
                request_attempt=0,
            ),
            id="turn-key-session",
        ),
        pytest.param(
            lambda: ComputeProfile(
                profile_id="profile",
                snn_enabled=1,
                ticks=24,
                stdp_enabled=True,
                reuse_last_summary=False,
                math_backend="scalar",
                formula_version="formula",
                model_version="model",
            ),
            id="profile-bool",
        ),
        pytest.param(
            lambda: TurnEnvelope(
                turn_key=_envelope().turn_key,
                turn_id="turn",
                sequence=TurnSequence(0, 1),
                compute_profile=_profile(),
                deterministic_seed=b"seed",
                observation=(),
                context="ADDRESSED",
            ),
            id="envelope-context",
        ),
        pytest.param(
            lambda: CoreInvocation(envelope="not-an-envelope", base_state=(), projected_actual_outcome=None),
            id="invocation-envelope",
        ),
        pytest.param(lambda: V3StateEffect(payload="state"), id="state-effect-payload"),
        pytest.param(lambda: V3TraceEffect(payload="trace"), id="trace-effect-payload"),
        pytest.param(lambda: V3MetricEffect(name="metric", value=True), id="metric-bool"),
        pytest.param(
            lambda: PendingOutcome(
                origin_turn_id="turn",
                sequence=TurnSequence(0, 1),
                action="SPEAK",
            ),
            id="pending-action",
        ),
        pytest.param(lambda: V3State(session_ref=_session_ref(), revision=True), id="state-revision-bool"),
        pytest.param(lambda: V3State(session_ref=_session_ref(), rho_hold=0), id="state-rho-int"),
        pytest.param(
            lambda: LoadSnapshotV1(
                global_queue_fill=0,
                oldest_job_age_ms=0.0,
                committed_compute_p95_ms=0.0,
                repository_admission=RepositoryAdmissionState.OPEN,
            ),
            id="bridge-load-int",
        ),
        pytest.param(lambda: EffectiveV3Budget(hard_bytes=True, high_bytes=0, admission_enabled=True), id="budget-bool"),
    ],
)
def test_all_v3_dataclasses_reject_values_with_wrong_semantic_types(factory: object) -> None:
    with pytest.raises(TypeError, match="type"):
        factory()  # type: ignore[operator]


def test_effect_bundle_is_a_closed_frozen_union() -> None:
    effects = (
        V3StateEffect(payload=b"state"),
        V3TraceEffect(payload=b"trace"),
        V3MetricEffect(name="turns", value=1.0),
    )
    assert EFFECT_TYPES == (V3StateEffect, V3TraceEffect, V3MetricEffect)
    bundle = EffectBundle(effects=effects)
    _assert_frozen(bundle, "effects")
    with pytest.raises(TypeError):
        EffectBundle(effects=(object(),))  # type: ignore[arg-type]


def test_minimal_state_and_pending_outcome_are_frozen() -> None:
    pending = PendingOutcome(
        origin_turn_id="turn-digest",
        sequence=TurnSequence(writer_epoch=7, local_sequence=11),
        action=Action.SPEAK,
    )
    state = V3State(session_ref=_session_ref(), revision=1, pending_outcome=pending)
    _assert_frozen(pending, "action")
    _assert_frozen(state, "revision")
    assert state.rho_hold == state.rho_reach == 0.0


def test_build_flags_are_source_off_by_default_and_have_no_configuration_entrypoint() -> None:
    assert V3_SHADOW_ENABLED is False
    assert BUILD_CHANNEL == "source"
    path = Path("sylanne_alpha/v3bridge/build_flags.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assigned = {
        target.id
        for node in tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        for target in ((node.targets if isinstance(node, ast.Assign) else [node.target]))
        if isinstance(target, ast.Name)
    }
    assert assigned == {"V3_SHADOW_ENABLED", "BUILD_CHANNEL"}
    assert not any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) for node in tree.body)


def test_resource_limits_and_effective_plugin_budget_are_exact() -> None:
    expected = {
        "MAX_ACTIVE_SESSIONS": 64,
        "MAX_REPOSITORY_SESSIONS": 96,
        "MAX_STATE_BYTES": 64 * 1024,
        "TARGET_STATE_BYTES": 48 * 1024,
        "MAX_TRACE_BYTES": 16 * 1024,
        "MAX_GLOBAL_QUEUE": 128,
        "MAX_PER_SESSION_QUEUE": 4,
        "MAX_TURN_REGISTRY": 1024,
        "TURN_REGISTRY_TTL_SECONDS": 15 * 60,
        "WORKER_COUNT": 1,
        "TRACE_SEGMENT_BYTES": 2 * 1024 * 1024,
        "TRACE_SEGMENT_COUNT": 2,
        "TELEMETRY_SEGMENT_BYTES": 1 * 1024 * 1024,
        "TELEMETRY_SEGMENT_COUNT": 4,
        "MAX_STAGING_BYTES": 4 * 1024 * 1024,
        "V3_DEFAULT_BUDGET_BYTES": 24_000_000,
        "NON_V3_RESERVE_BYTES": 2_000_000,
        "DISK_HIGH_WATERMARK_BYTES": 22_000_000,
        "DISK_HARD_WATERMARK_BYTES": 24_000_000,
    }
    assert {name: getattr(limits, name) for name in expected} == expected
    assert limits.PLUGIN_DATA_CAP_BYTES == 50_000_000

    dominant = limits.effective_v3_budget(non_v3_bytes=0)
    assert (dominant.hard_bytes, dominant.high_bytes, dominant.admission_enabled) == (24_000_000, 22_000_000, True)
    assert limits.effective_v3_budget(non_v3_bytes=24_000_000) == dominant
    constrained = limits.effective_v3_budget(non_v3_bytes=25_000_000)
    assert (constrained.hard_bytes, constrained.high_bytes) == (23_000_000, 21_000_000)

    below_minimum = limits.effective_v3_budget(
        non_v3_bytes=50_000_000 - 2_000_000 - (4 * 1024 * 1024 - 1)
    )
    assert below_minimum.admission_enabled is False
    assert limits.RESOURCE_CEILINGS_ARE_SIMULTANEOUS_RESERVATIONS is False


def test_effective_v3_budget_handles_minimum_custom_and_invalid_caps() -> None:
    minimum = 4 * 1024 * 1024
    assert limits.effective_v3_budget(0, minimum) == EffectiveV3Budget(2_194_304, 194_304, False)
    assert limits.effective_v3_budget(0, 0) == EffectiveV3Budget(0, 0, False)
    assert limits.effective_v3_budget(1_000_000, 10_000_000) == EffectiveV3Budget(7_000_000, 5_000_000, True)
    for args in ((-1,), (0, -1)):
        with pytest.raises(ValueError, match="non-negative"):
            limits.effective_v3_budget(*args)
    for args in ((False,), (0, 4.0), ("0",)):
        with pytest.raises(TypeError, match="integer"):
            limits.effective_v3_budget(*args)  # type: ignore[arg-type]


def test_bridge_load_snapshot_is_frozen_and_repository_hard_stop_is_explicit() -> None:
    snapshot = LoadSnapshotV1(
        global_queue_fill=0.25,
        oldest_job_age_ms=25.0,
        committed_compute_p95_ms=2.5,
        repository_admission=RepositoryAdmissionState.OPEN,
    )
    _assert_frozen(snapshot, "global_queue_fill")
    assert RepositoryAdmissionState.HARD_STOP.value == "HARD_STOP"


def test_formula_dimensions_and_sparse_drive_are_exact() -> None:
    assert formula.FORMULA_VERSION == "sylanne.v3.formula.v1"
    # formula v2 deleted the SNN cognition dimensions/time-constants; SNN_NEURONS and
    # SNN_SUMMARY_DIM survive only as trace-telemetry layout constants.
    assert (
        formula.OBSERVATION_DIM,
        formula.AXIS_DIM,
        formula.STATE_DIM,
        formula.SNN_NEURONS,
        formula.SNN_SUMMARY_DIM,
        formula.WORKSPACE_CAPACITY,
        formula.EXPERIENCE_CAPACITY,
    ) == (36, 8, 24, 96, 16, 8, 64)

    expected_p = (
        (0, 25, 0.55),
        (0, 0, 0.45),
        (1, 23, 0.35),
        (1, 21, 0.35),
        (1, 4, 0.30),
        (2, 1, -0.40),
        (2, 2, -0.35),
        (2, 17, -0.25),
        (3, 0, 0.35),
        (3, 19, 0.35),
        (3, 20, -0.25),
        (3, 26, 0.20),
        (4, 22, 0.30),
        (4, 4, 0.35),
        (4, 6, -0.35),
        (5, 4, 0.70),
        (5, 5, -0.30),
        (6, 9, 0.70),
        (6, 17, -0.30),
        (7, 11, 0.50),
        (7, 14, 0.30),
        (7, 10, -0.20),
    )
    assert formula.P_TRIPLES == expected_p
    assert formula.P_MATRIX == _matrix(8, 36, expected_p)


def test_formula_semantic_defaults_centering_bias_and_context_priors_are_exact() -> None:
    assert len(formula.SEMANTIC_DEFAULTS) == formula.OBSERVATION_DIM == 36
    assert formula.CENTER_SCALE == 2.0
    assert formula.CENTER_OFFSET == -1.0
    assert formula.P_BIAS == tuple(
        -sum(weight * formula.SEMANTIC_DEFAULTS[column] for column, weight in enumerate(row))
        for row in formula.P_MATRIX
    )
    assert formula.CONTEXT_ACTION_PRIORS == {
        "ADDRESSED": {"SPEAK": 0.55, "CLARIFY": 0.25, "HOLD": 0.20},
        "AMBIENT": {"HOLD": 0.75, "SPEAK": 0.25},
        "PROACTIVE": {"HOLD": 0.80, "REACH": 0.20},
        "IDLE": {"HOLD": 1.0},
    }
    assert formula.ACTION_TIE_ORDER == ("HOLD", "CLARIFY", "SPEAK", "REACH")


def test_formula_dynamics_matrices_use_target_rows_and_source_columns() -> None:
    off_diagonal = {
        (0, 2): 0.06,
        (0, 3): 0.06,
        (1, 4): 0.06,
        (4, 2): -0.06,
        (6, 3): 0.05,
        (7, 6): 0.05,
    }
    for name, diagonal, scale in (
        ("W_FAST", 0.30, 1.0),
        ("W_MID", 0.35, 5.0 / 6.0),
        ("W_SLOW", 0.36, 0.5),
    ):
        matrix = getattr(formula, name)
        assert len(matrix) == 8 and all(len(row) == 8 for row in matrix)
        for row in range(8):
            for column in range(8):
                expected = diagonal if row == column else off_diagonal.get((row, column), 0.0) * scale
                assert matrix[row][column] == pytest.approx(expected)
    for name, diagonal in (("U_FAST", 0.80), ("U_MID", 0.75), ("U_SLOW", 0.65)):
        matrix = getattr(formula, name)
        assert matrix == tuple(tuple(diagonal if row == column else 0.0 for column in range(8)) for row in range(8))

    identity = tuple(tuple(1.0 if row == column else 0.0 for column in range(8)) for row in range(8))

    def self_block(matrix: tuple[tuple[float, ...], ...], alpha: float) -> tuple[tuple[float, ...], ...]:
        return tuple(
            tuple((1.0 - alpha if row == column else 0.0) + alpha * abs(matrix[row][column]) for column in range(8))
            for row in range(8)
        )

    block_a = self_block(formula.W_FAST, 0.50)
    block_b = self_block(formula.W_MID, 0.12)
    block_f = self_block(formula.W_SLOW, 0.02)
    mid_from_fast = tuple(tuple(0.12 * 0.75 * value for value in row) for row in block_a)
    slow_from_mid = tuple(tuple(0.02 * 0.65 * value for value in row) for row in block_b)
    slow_from_fast = _matrix_multiply(
        tuple(tuple(0.02 * 0.65 * value for value in row) for row in identity),
        mid_from_fast,
    )
    zero = tuple((0.0,) * 8 for _ in range(8))
    expected_jacobian = tuple(
        [block_a[row] + zero[row] + zero[row] for row in range(8)]
        + [mid_from_fast[row] + block_b[row] + zero[row] for row in range(8)]
        + [slow_from_fast[row] + slow_from_mid[row] + block_f[row] for row in range(8)]
    )
    actual_jacobian = formula.jacobian_absolute_upper_bound()
    assert len(actual_jacobian) == 24 and all(len(row) == 24 for row in actual_jacobian)
    for actual_row, expected_row in zip(actual_jacobian, expected_jacobian):
        assert actual_row == pytest.approx(expected_row)

    norm_one = max(sum(actual_jacobian[row][column] for row in range(24)) for column in range(24))
    norm_infinity = max(sum(row) for row in actual_jacobian)
    expected_bound = math.sqrt(norm_one * norm_infinity)
    bound = formula.validate_formula_manifest()
    assert bound == pytest.approx(expected_bound)
    assert bound < 0.995
    assert formula.JACOBIAN_VALIDATION_METHOD == "abs-block-sqrt-l1-linf"


def test_formula_validator_rejects_bad_shapes(monkeypatch: pytest.MonkeyPatch) -> None:
    # formula v2 deleted the SNN population / Q-matrix / recurrent-topology checks;
    # the continuous P/W/U matrices, step sizes, and the Jacobian gate remain.
    for name, bad_value in (
        ("P_MATRIX", ((0.0,),)),
        ("W_FAST", ((0.0,),)),
        ("U_SLOW", ((0.0,),)),
    ):
        with monkeypatch.context() as scoped:
            scoped.setattr(formula, name, bad_value)
            with pytest.raises(ValueError):
                formula.validate_formula_manifest()
    jacobian_calls: list[bool] = []
    with monkeypatch.context() as scoped:
        scoped.setattr(formula, "W_FAST", ((0.0,),))
        scoped.setattr(
            formula,
            "jacobian_absolute_upper_bound",
            lambda: jacobian_calls.append(True),
        )
        with pytest.raises(ValueError):
            formula.validate_formula_manifest()
    assert jacobian_calls == []
    for name, bad_value in (
        ("DYNAMICS_STEP_SIZES", (0.50,)),
        ("JACOBIAN_ABSOLUTE_UPPER_BOUND", ((0.0,),)),
    ):
        jacobian_calls = []
        with monkeypatch.context() as scoped:
            scoped.setattr(formula, name, bad_value)
            scoped.setattr(
                formula,
                "jacobian_absolute_upper_bound",
                lambda: jacobian_calls.append(True),
            )
            with pytest.raises(ValueError):
                formula.validate_formula_manifest()
        assert jacobian_calls == []
    with monkeypatch.context() as scoped:
        scoped.setattr(formula, "jacobian_absolute_upper_bound", lambda: ((0.0,),))
        with pytest.raises(ValueError, match="Jacobian"):
            formula.validate_formula_manifest()


def test_formula_validator_normalizes_extreme_numeric_values_to_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    defaults = list(formula.SEMANTIC_DEFAULTS)
    defaults[0] = 10**10000
    monkeypatch.setattr(formula, "SEMANTIC_DEFAULTS", tuple(defaults))
    with pytest.raises(ValueError, match="finite"):
        formula.validate_formula_manifest()


def test_formula_validator_rejects_materialized_jacobian_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # formula v2 deleted the recurrent/input topology and its materialization checks;
    # the materialized Jacobian drift check remains.
    with monkeypatch.context() as scoped:
        scoped.setattr(
            formula,
            "JACOBIAN_ABSOLUTE_UPPER_BOUND",
            tuple((0.0,) * formula.STATE_DIM for _ in range(formula.STATE_DIM)),
        )
        with pytest.raises(ValueError, match="materialized Jacobian"):
            formula.validate_formula_manifest()


def test_formula_validator_rejects_bias_priors_and_full_bound_mismatches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with monkeypatch.context() as scoped:
        scoped.setattr(formula, "P_BIAS", (0.0,) * formula.AXIS_DIM)
        with pytest.raises(ValueError, match="P_BIAS"):
            formula.validate_formula_manifest()
    with monkeypatch.context() as scoped:
        scoped.setattr(formula, "CONTEXT_ACTION_PRIORS", {"IDLE": {"HOLD": 0.5}})
        with pytest.raises(ValueError, match="context"):
            formula.validate_formula_manifest()
    with monkeypatch.context() as scoped:
        scoped.setattr(formula, "JACOBIAN_STABILITY_BOUND", 0.0)
        with pytest.raises(ValueError, match="bound"):
            formula.validate_formula_manifest()


@pytest.mark.parametrize(
    "priors",
    [
        pytest.param({"IDLE": {"HOLD": 1.0}}, id="missing-contexts"),
        pytest.param(
            {
                "ADDRESSED": {"SPEAK": 0.55, "REACH": 0.25, "HOLD": 0.20},
                "AMBIENT": {"HOLD": 0.75, "SPEAK": 0.25},
                "PROACTIVE": {"HOLD": 0.80, "REACH": 0.20},
                "IDLE": {"HOLD": 1.0},
            },
            id="illegal-action",
        ),
        pytest.param(
            {
                "ADDRESSED": {"SPEAK": 0.55, "CLARIFY": 0.25, "HOLD": 0.20},
                "AMBIENT": {"HOLD": 0.75, "SPEAK": 0.25},
                "PROACTIVE": {"HOLD": 1.0, "REACH": 0.0},
                "IDLE": {"HOLD": 1.0},
            },
            id="non-positive-probability",
        ),
        pytest.param(
            {
                "ADDRESSED": {"SPEAK": 0.55, "CLARIFY": 0.25, "HOLD": 0.20},
                "AMBIENT": {"HOLD": 0.75, "SPEAK": 0.25},
                "PROACTIVE": {"HOLD": 0.70, "REACH": 0.20},
                "IDLE": {"HOLD": 1.0},
            },
            id="not-normalized",
        ),
    ],
)
def test_formula_validator_rejects_invalid_context_prior_details(
    monkeypatch: pytest.MonkeyPatch,
    priors: object,
) -> None:
    monkeypatch.setattr(formula, "CONTEXT_ACTION_PRIORS", priors)
    with pytest.raises(ValueError, match="context"):
        formula.validate_formula_manifest()


def test_formula_validator_treats_named_context_mapping_order_as_nonsemantic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reordered_priors = {
        "IDLE": {"HOLD": 1.0},
        "PROACTIVE": {"REACH": 0.20, "HOLD": 0.80},
        "AMBIENT": {"SPEAK": 0.25, "HOLD": 0.75},
        "ADDRESSED": {"HOLD": 0.20, "CLARIFY": 0.25, "SPEAK": 0.55},
    }
    monkeypatch.setattr(formula, "CONTEXT_ACTION_PRIORS", reordered_priors)
    assert formula.validate_formula_manifest() == formula.JACOBIAN_STABILITY_BOUND
    assert canonical.canonical_json_bytes(formula.build_formula_manifest()) == formula.FORMULA_CANONICAL_JSON


def test_proposal_manifest_is_frozen_exactly() -> None:
    # formula v2 deleted the snn-novelty proposal (old index 6) and the SNN summary
    # pools/definition.  The survivors are NOT renumbered in key space: their
    # (action, source-basis, group) key triples are byte-identical to formula v1, so
    # continuity-speak keeps source basis 11 and key coordinate 10 is a permanent
    # tombstone that no proposal uses.
    assert formula.PROPOSAL_IDS == (
        "body-speak",
        "affect-speak",
        "uncertainty-clarify",
        "boundary-hold",
        "fatigue-hold",
        "affiliation-reach",
        "continuity-speak",
    )
    assert formula.PROPOSAL_COUNT == 7
    assert formula.PROPOSAL_SALIENCE_FORMULAS == (
        ("body-speak", "1.2*expression_pressure + 0.5*arousal + 0.3*center(expression_drive)"),
        ("affect-speak", "0.9*abs(valence) + 0.7*affiliation + 0.4*safety"),
        ("uncertainty-clarify", "1.4*uncertainty + 0.4*novelty"),
        ("boundary-hold", "-1.3*safety - 0.6*agency + 0.5*center(boundary_pressure)"),
        ("fatigue-hold", "1.4*center(exhaustion) - 0.4*expression_pressure"),
        ("affiliation-reach", "1.1*affiliation + 0.8*expression_pressure + 0.3*novelty"),
        (
            "continuity-speak",
            "0.8*center(history_present) + 0.6*center(engagement) + 0.4*affiliation",
        ),
    )
    assert formula.PROPOSAL_KEY_WEIGHTS == (1.0, 0.75, 0.50)
    assert formula.PROPOSAL_ACTION_BASIS == (0, 1, 2, 3)
    assert formula.PROPOSAL_SOURCE_BASIS == (4, 5, 6, 7, 8, 9, 11)  # 10 = snn-novelty tombstone
    assert formula.PROPOSAL_GROUP_COORDS == (12, 12, 13, 14, 12, 15, 15)
    assert formula.PROPOSAL_REQUIRED_BITS == ((11,), (), (), (17,), (10,), (), (26, 30))
    assert formula.PROPOSAL_SALIENCE_BOUNDS == (-4.0, 4.0)
    assert formula.PROPOSAL_CONFIDENCE_FORMULA == "clip01(0.5 + 0.25*abs(salience))"
    assert formula.center(0.0) == -1.0
    assert formula.center(0.5) == 0.0
    assert formula.center(1.0) == 1.0
    for key in formula.PROPOSAL_KEYS:
        assert len(key) == 16
        assert math.sqrt(sum(value * value for value in key)) == pytest.approx(1.0)
    # No surviving proposal uses key coordinate 10 (the snn-novelty tombstone).
    assert all(key[10] == 0.0 for key in formula.PROPOSAL_KEYS)


def test_expression_v1_constraints_are_frozen_without_literal_openings() -> None:
    assert formula.EXPRESSION_REVISION == formula.FORMULA_VERSION
    assert formula.HOLD_EXPRESSION == (0, 0.0, 0.50, 0.50, False)
    assert formula.SPEAK_LENGTH_THRESHOLDS == (-0.25, 0.45)
    assert formula.SPEAK_PACE_FORMULA == "clip01(0.50+0.20*arousal-0.20*center(exhaustion))"
    assert formula.SPEAK_DIRECTNESS_FORMULA == "clip01(0.50+0.25*agency-0.20*uncertainty)"
    assert formula.SPEAK_WARMTH_FORMULA == "clip01(0.50+0.25*affiliation+0.15*valence)"
    assert formula.CLARIFY_EXPRESSION == ("SHORT", 0.45, 0.75)
    assert formula.CLARIFY_WARMTH_FORMULA == "clip01(0.50+0.20*affiliation)"
    assert formula.CLARIFY_HESITATION_UNCERTAINTY_THRESHOLD == 0.55
    assert formula.REACH_AFFILIATION_MEDIUM_THRESHOLD == 0.60
    assert formula.REACH_EXPRESSION == ("SHORT_OR_MEDIUM", 0.40, 0.45)
    assert formula.REACH_WARMTH_FORMULA == "clip01(0.70+0.20*affiliation)"
    assert formula.STYLE_SIGNATURE_RING_CAPACITY == 4
    assert formula.STYLE_REPEAT_SUPPRESSION_LOOKBACK == 2
    assert formula.STYLE_REPEAT_RESPONSE == ("hesitation=false", "length=one_bucket_shorter")
    assert formula.EXPRESSION_LITERAL_OPENING_ALLOWED is False


def test_action_belief_reward_and_refractory_constants_are_exact() -> None:
    assert (
        formula.ACTION_INITIAL_G,
        formula.ACTION_INITIAL_V,
        formula.ACTION_INITIAL_R,
        formula.ACTION_INITIAL_COVARIANCE,
        formula.ACTION_INITIAL_COUNT,
        formula.ACTION_INITIAL_BASELINE,
        formula.ACTION_Q_THETA,
        formula.ACTION_REWARD_SCALE,
    ) == (0.85, 0.25, 0.20, (0.10, 0.10), 0, 0.0, 1e-4, 1.0)
    assert formula.ACTION_BIAS == (
        ("SPEAK", (0.05, 0.05, 0.05, 0.08, -0.05, 0.05, 0.03, 0.08)),
        ("HOLD", (0.00, -0.05, 0.08, 0.00, -0.05, -0.05, 0.05, -0.08)),
        ("CLARIFY", (0.00, 0.00, 0.05, 0.02, -0.12, 0.02, 0.02, -0.02)),
        ("REACH", (0.05, 0.05, 0.03, 0.12, -0.03, 0.08, 0.02, 0.10)),
    )
    assert formula.PREFERENCE_REVISION == formula.FORMULA_VERSION
    assert formula.OUTCOME_PROJECTOR_REVISION == formula.FORMULA_VERSION
    assert formula.ACTION_MODEL_REVISION == formula.FORMULA_VERSION
    assert formula.REWARD_BRANCHES == (
        "no valid outcome dimension -> censored",
        "invalid quality_score -> r_preference",
        "otherwise clip(0.70*r_preference+0.30*(2*quality_score-1),-1,1)",
    )
    assert formula.WORKSPACE_EVIDENCE_FORMULA == "clip(2*(support_a-mean_legal_support),-2,2)"
    assert (
        formula.RHO_HOLD_INITIAL,
        formula.RHO_REACH_INITIAL,
        formula.RHO_DECAY,
        formula.RHO_PRE_SCORE_PENALTY_MULTIPLIER,
        formula.RHO_POST_SELECTION_INCREMENT,
        formula.RHO_BOUNDS,
    ) == (0.0, 0.0, 0.80, 2.0, 0.35, (0.0, 1.0))
    assert formula.RHO_PENALTY_CONTEXTS == ("PROACTIVE", "IDLE")
    assert formula.RHO_DECAY_ONLY_CONTEXTS == ("ADDRESSED", "AMBIENT")


def test_profiles_and_load_thresholds_are_exact() -> None:
    assert formula.FULL_24_STDP == (True, 24, True, False)
    assert formula.FULL_24_NO_STDP == (True, 24, False, False)
    assert formula.SNN_16_NO_STDP == (True, 16, False, False)
    assert formula.REUSE_LAST_SNN_SUMMARY == (False, 0, False, True)
    assert formula.DETERMINISTIC_CONTINUOUS_ONLY == (False, 0, False, False)
    assert formula.PROFILE_LADDER == (
        "FULL_24_STDP",
        "FULL_24_NO_STDP",
        "SNN_16_NO_STDP",
        "REUSE_LAST_SNN_SUMMARY",
        "DETERMINISTIC_CONTINUOUS_ONLY",
        "SKIP_V3_TURN",
    )
    assert formula.LOAD_THRESHOLDS[:-1] == (
        (0.25, 25.0, 2.5),
        (0.50, 50.0, 3.5),
        (0.70, 100.0, 5.0),
        (0.85, 200.0, 8.0),
    )
    assert formula.LOAD_THRESHOLDS[-1][:2] == (1.0, 500.0)
    assert math.isinf(formula.LOAD_THRESHOLDS[-1][2])
    assert formula.RECOVERY_CONSECUTIVE_SNAPSHOTS == 32
    assert formula.RECOVERY_THRESHOLD_RATIO == 0.80
    assert formula.REPOSITORY_HARD_STOP_PROFILE == "SKIP_V3_TURN"


def test_formula_manifest_uses_named_mappings_for_all_material_semantics() -> None:
    manifest = formula.FORMULA_MANIFEST
    assert manifest["observation"] == {
        "dimension": formula.OBSERVATION_DIM,
        "semantic_defaults": formula.SEMANTIC_DEFAULTS,
        "center_scale": formula.CENTER_SCALE,
        "center_offset": formula.CENTER_OFFSET,
    }
    assert manifest["dynamics"]["p_matrix"] == formula.P_MATRIX
    assert manifest["dynamics"]["p_bias"] == formula.P_BIAS
    # formula v2 removed the whole "spiking" manifest section (and dynamics.q_matrix).
    assert "spiking" not in manifest
    assert "snn_summary" not in manifest
    assert "q_matrix" not in manifest["dynamics"]
    assert manifest["action_selection"]["context_priors"] == formula.CONTEXT_ACTION_PRIORS
    assert manifest["action_selection"]["tie_order"] == formula.ACTION_TIE_ORDER
    assert manifest["load_shedding"]["profile_fields"] == (
        "snn_enabled",
        "ticks",
        "stdp_enabled",
        "reuse_last_summary",
    )
    assert manifest["load_shedding"]["profiles"] == formula.COMPUTE_PROFILES
    assert manifest["load_shedding"]["reuse_last_summary_fallback"] == "DETERMINISTIC_CONTINUOUS_ONLY"
    assert manifest["expression"]["clarify_hesitation_semantics"] == (
        "hesitation is true iff action is CLARIFY and uncertainty >= threshold"
    )
    assert manifest["validation"]["jacobian_absolute_upper_bound"] == formula.JACOBIAN_ABSOLUTE_UPPER_BOUND
    assert manifest["validation"]["jacobian_stability_bound"] == formula.JACOBIAN_STABILITY_BOUND


def test_formula_manifest_builder_tracks_semantic_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = formula.FORMULA_CANONICAL_JSON
    monkeypatch.setattr(formula, "CENTER_SCALE", formula.CENTER_SCALE + 1.0)
    rebuilt = formula.build_formula_manifest()
    assert canonical.canonical_json_bytes(rebuilt) != baseline


def test_formula_digest_is_canonical_and_golden() -> None:
    assert type(formula.FORMULA_MANIFEST) is MappingProxyType
    assert len(formula.FORMULA_DIGEST) == 64
    assert formula.FORMULA_DIGEST == hashlib.sha256(formula.FORMULA_CANONICAL_JSON).hexdigest()
    # formula v2 digest: the SNN subsystem (dimensions snn_*, dynamics.q_matrix, the
    # whole spiking + snn_summary manifest sections, and the snn-novelty proposal)
    # was removed from the manifest.  This is an intentional digest bump for a
    # behaviour change; the pre-deletion (formula v1) digest was
    # 47c690a78944a408dee245c20833b5f8fff8fa066e2faa92f6ae736511cbffa2.
    assert formula.FORMULA_DIGEST == "d3998ec2f0fa00046abfeae2a224f7703013bb2bdd893367a025e238f72d5ea4"


def test_v3core_import_firewall() -> None:
    forbidden = {
        "astrbot",
        "sylanne_alpha.v2core",
        "sylanne_alpha._engine",
        "asyncio",
        "time",
        "logging",
        "os",
        "pathlib",
        "io",
        "tempfile",
        "shutil",
        "socket",
        "subprocess",
        "threading",
        "concurrent.futures",
        "portalocker",
        "numpy",
    }
    for path in Path("sylanne_alpha/v3core").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = _imported_module_names(tree)
        assert not any(
            name == item or name.startswith(item + ".")
            for name in imports
            for item in forbidden
        )
        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "open"
            for node in ast.walk(tree)
        )
