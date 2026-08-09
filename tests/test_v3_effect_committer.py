"""RED/GREEN tests for Task 11 EffectCommitter (design 4.2 / 15.1).

The committer is the *only* component allowed to call the private repository.  It
journals a turn's quantized state and deterministic trace into one durable CAS
revision, records v3 metrics best-effort, and suppresses every external effect as
``SUPPRESSED_SHADOW``.  Persistence is on the float16 quantization grid: the bytes
it stores decode back to exactly the committed state (回溯红队 a16 MAJOR DoD).
"""

from __future__ import annotations

import ast
import base64
import json
from pathlib import Path

import pytest

from sylanne_alpha.v3bridge.effect_committer import (
    BaseRef,
    CommitStatus,
    EffectCommitter,
    EffectDisposition,
    LoadedState,
    SUPPRESSED_EFFECT_KINDS,
    TurnCommit,
)
from sylanne_alpha.v3bridge.limits import MAX_STATE_BYTES
from sylanne_alpha.v3bridge.session_identity import SessionIdentityKey, session_filename_token
from sylanne_alpha.v3core import formula_v1 as formula
from sylanne_alpha.v3core.canonical import canonical_sha256
from sylanne_alpha.v3core.contracts import (
    Action,
    ComputeProfile,
    CoreInvocation,
    TurnContextClass,
    TurnEnvelope,
    TurnKey,
    TurnSequence,
)
from sylanne_alpha.v3core.effects.models import (
    EffectBundle,
    V3MetricEffect,
    V3StateEffect,
    V3TraceEffect,
)
from sylanne_alpha.v3core.orchestrator import orchestrate
from sylanne_alpha.v3core.state.codec import decode_state, encode_state
from sylanne_alpha.v3core.state.models import V3State
from sylanne_alpha.v3core.state.seed import SeedProjector, neutral_seed_frame


_IDENTITY = SessionIdentityKey(key_id="committer-v1", secret=b"c" * 32)
_REPO_ROOT = Path(__file__).resolve().parents[1]


def _ref(name: str = "umo-1"):
    ref = _IDENTITY.session_ref("qq", name, session_generation=0)
    assert ref is not None
    return ref


def _raw_values() -> tuple:
    values: list[float | None] = [None] * 36
    for index in range(36):
        if index in (27, 28, 29, 32, 33, 34, 35):
            values[index] = None
        else:
            values[index] = 0.5
    values[30] = 1.0
    values[31] = 120.0
    return tuple(values)


def _profile(name: str = "FULL_24_STDP") -> ComputeProfile:
    snn_enabled, ticks, stdp_enabled, reuse = formula.COMPUTE_PROFILES[name]
    return ComputeProfile(
        profile_id=name,
        snn_enabled=snn_enabled,
        ticks=ticks,
        stdp_enabled=stdp_enabled,
        reuse_last_summary=reuse,
        math_backend="scalar-v1",
        formula_version=formula.FORMULA_VERSION,
        model_version=formula.FORMULA_VERSION,
    )


def _envelope(ref, epoch: int, local_sequence: int, turn_id: str) -> TurnEnvelope:
    return TurnEnvelope(
        turn_key=TurnKey(
            plugin_instance_id="plugin",
            session_ref=ref,
            bridge_request_nonce="nonce",
            request_attempt=0,
        ),
        turn_id=turn_id,
        sequence=TurnSequence(epoch, local_sequence),
        compute_profile=_profile(),
        deterministic_seed=b"d" * 16,
        observation=(_raw_values(), Action.SPEAK),
        context=TurnContextClass.ADDRESSED,
    )


def _genesis_state(ref, epoch: int, generation: str = "gen-a") -> V3State:
    return SeedProjector().build_initial_state(
        neutral_seed_frame(),
        session_ref=ref,
        state_generation_id=generation,
        source_digest="a" * 64,
        session_generation=0,
        writer_epoch=epoch,
    )


def _bundle(payload: bytes, trace: bytes) -> EffectBundle:
    return EffectBundle(
        effects=(
            V3StateEffect(payload=payload),
            V3TraceEffect(payload=trace),
            V3MetricEffect(name="v3_shadow_turn", value=1.0),
        )
    )


def _commit_genesis(committer: EffectCommitter, ref, epoch: int) -> LoadedState:
    state = _genesis_state(ref, epoch)
    payload = encode_state(state, max_bytes=MAX_STATE_BYTES)
    outcome = committer.commit_turn(
        TurnCommit(
            session_ref=ref,
            base=None,
            state_payload=payload,
            trace_bytes=b"genesis-trace",
            effects=_bundle(payload, b"genesis-trace"),
            turn_id="v3-genesis",
            turn_sequence=TurnSequence(epoch, 1),
        )
    )
    assert outcome.status is CommitStatus.COMMITTED
    loaded = committer.load_state(ref)
    assert loaded is not None
    return loaded


def _advance(committer: EffectCommitter, loaded: LoadedState, ref, epoch: int, local_sequence: int, turn_id: str):
    result = orchestrate(
        CoreInvocation(
            envelope=_envelope(ref, epoch, local_sequence, turn_id),
            base_state=loaded.state,
            projected_actual_outcome=(Action.SPEAK, None),
        )
    )
    assert result.accepted is True
    state_payload = next(e.payload for e in result.effects.effects if type(e) is V3StateEffect)
    trace_bytes = next(e.payload for e in result.effects.effects if type(e) is V3TraceEffect)
    outcome = committer.commit_turn(
        TurnCommit(
            session_ref=ref,
            base=loaded.base,
            state_payload=state_payload,
            trace_bytes=trace_bytes,
            effects=result.effects,
            turn_id=turn_id,
            turn_sequence=TurnSequence(epoch, local_sequence),
        )
    )
    return outcome, result


# --------------------------------------------------------------------------- #
# Import firewall: only EffectCommitter may import the private repository
# --------------------------------------------------------------------------- #


def _modules_importing_private_repository() -> set[str]:
    package = _REPO_ROOT / "sylanne_alpha"
    hits: set[str] = set()
    for path in package.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if (node.module or "").split(".")[-1] == "_state_repository":
                    hits.add(path.relative_to(_REPO_ROOT).as_posix())
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[-1] == "_state_repository":
                        hits.add(path.relative_to(_REPO_ROOT).as_posix())
    return hits


def test_only_effect_committer_imports_the_private_repository() -> None:
    assert _modules_importing_private_repository() == {
        "sylanne_alpha/v3bridge/effect_committer.py"
    }


# --------------------------------------------------------------------------- #
# Closed effect policy: every external effect is SUPPRESSED_SHADOW
# --------------------------------------------------------------------------- #


def test_every_external_effect_kind_is_suppressed_shadow() -> None:
    assert set(SUPPRESSED_EFFECT_KINDS) == {
        "REPLY",
        "PROMPT",
        "TOOL",
        "BODY_TICK",
        "ASTRBOT_HISTORY",
        "V2_MEMORY",
        "GROUP_WRITE",
    }
    for kind in SUPPRESSED_EFFECT_KINDS:
        assert EffectCommitter.disposition_for_external_kind(kind) is EffectDisposition.SUPPRESSED_SHADOW


def test_effect_bundle_is_a_closed_union_and_rejects_external_effects() -> None:
    class ForeignEffect:
        pass

    with pytest.raises(TypeError):
        EffectBundle(effects=(ForeignEffect(),))


def test_commit_dispositions_journal_state_trace_record_metric_suppress_external(tmp_path: Path) -> None:
    committer = EffectCommitter.open(tmp_path)
    committer.acquire_epoch()
    epoch = committer.current_epoch()
    genesis = _commit_genesis(committer, _ref(), epoch)
    outcome, _ = _advance(committer, genesis, _ref(), epoch, 2, "turn-2")
    assert outcome.status is CommitStatus.COMMITTED
    by_kind: dict[str, EffectDisposition] = dict(outcome.dispositions)
    assert by_kind["V3StateEffect"] is EffectDisposition.COMMITTED
    assert by_kind["V3TraceEffect"] is EffectDisposition.COMMITTED
    assert by_kind["V3MetricEffect"] is EffectDisposition.RECORDED
    # A turn that also requests external effects suppresses each one.
    outcome2, _ = _advance_with_external(committer, committer.load_state(_ref()), _ref(), epoch, 3, "turn-3")
    external = {kind: disp for kind, disp in outcome2.dispositions if kind in SUPPRESSED_EFFECT_KINDS}
    assert external and all(disp is EffectDisposition.SUPPRESSED_SHADOW for disp in external.values())


def _advance_with_external(committer, loaded, ref, epoch, local_sequence, turn_id):
    result = orchestrate(
        CoreInvocation(
            envelope=_envelope(ref, epoch, local_sequence, turn_id),
            base_state=loaded.state,
            projected_actual_outcome=(Action.SPEAK, None),
        )
    )
    state_payload = next(e.payload for e in result.effects.effects if type(e) is V3StateEffect)
    trace_bytes = next(e.payload for e in result.effects.effects if type(e) is V3TraceEffect)
    outcome = committer.commit_turn(
        TurnCommit(
            session_ref=ref,
            base=loaded.base,
            state_payload=state_payload,
            trace_bytes=trace_bytes,
            effects=result.effects,
            turn_id=turn_id,
            turn_sequence=TurnSequence(epoch, local_sequence),
            external_effect_kinds=tuple(SUPPRESSED_EFFECT_KINDS),
        )
    )
    return outcome, result


# --------------------------------------------------------------------------- #
# State + trace share ONE durable journal record
# --------------------------------------------------------------------------- #


def test_state_and_trace_share_one_durable_journal_record(tmp_path: Path) -> None:
    committer = EffectCommitter.open(tmp_path)
    committer.acquire_epoch()
    epoch = committer.current_epoch()
    genesis = _commit_genesis(committer, _ref(), epoch)
    outcome, result = _advance(committer, genesis, _ref(), epoch, 2, "turn-2")
    assert outcome.status is CommitStatus.COMMITTED

    repo = committer.repository
    pointer = repo._load_pointer(session_filename_token(_ref()))
    assert pointer is not None
    record = json.loads((repo.root / pointer.current_journal).read_bytes())
    # One record carries BOTH the cognitive payload and the deterministic trace.
    assert record["cognitive_payload"]
    assert record["deterministic_trace"]
    recovered_state = decode_state(record["cognitive_payload"].encode("ascii"))
    assert recovered_state == result.state_delta.next_state
    recovered_trace = base64.b64decode(record["deterministic_trace"])
    assert recovered_trace == result.trace_bytes


# --------------------------------------------------------------------------- #
# Quantize-on-persist DoD: stored bytes decode back to the committed state
# --------------------------------------------------------------------------- #


def test_committer_persists_the_float16_quantized_state_and_reload_matches(tmp_path: Path) -> None:
    committer = EffectCommitter.open(tmp_path)
    committer.acquire_epoch()
    epoch = committer.current_epoch()
    genesis = _commit_genesis(committer, _ref(), epoch)
    outcome, result = _advance(committer, genesis, _ref(), epoch, 2, "turn-2")
    canonical = result.state_delta.next_state
    # decode(encode(x)) == x for the REAL compute product once quantized.
    assert decode_state(encode_state(canonical)) == canonical
    reloaded = committer.load_state(_ref())
    assert reloaded is not None
    assert reloaded.state == canonical
    # payload_digest is computed from the quantized persistence bytes.
    assert reloaded.base.payload_digest == canonical_sha256(encode_state(canonical).decode("ascii"))


# --------------------------------------------------------------------------- #
# CAS advance + conflict + oversize rejection without pointer change
# --------------------------------------------------------------------------- #


def test_commit_turn_advances_revision_and_rejects_a_stale_base(tmp_path: Path) -> None:
    committer = EffectCommitter.open(tmp_path)
    committer.acquire_epoch()
    epoch = committer.current_epoch()
    genesis = _commit_genesis(committer, _ref(), epoch)
    first, _ = _advance(committer, genesis, _ref(), epoch, 2, "turn-2")
    assert first.status is CommitStatus.COMMITTED
    assert first.committed_revision == 1
    # Re-using the stale genesis base after revision 1 landed is a CAS conflict.
    stale, _ = _advance(committer, genesis, _ref(), epoch, 3, "turn-3")
    assert stale.status is CommitStatus.REVISION_CONFLICT


def test_oversize_state_is_rejected_without_touching_the_pointer(tmp_path: Path) -> None:
    committer = EffectCommitter.open(tmp_path)
    committer.acquire_epoch()
    epoch = committer.current_epoch()
    genesis = _commit_genesis(committer, _ref(), epoch)
    before = committer.load_state(_ref())
    assert before is not None
    oversize = b"x" * (MAX_STATE_BYTES + 1)
    outcome = committer.commit_turn(
        TurnCommit(
            session_ref=_ref(),
            base=before.base,
            state_payload=oversize,
            trace_bytes=b"t",
            effects=EffectBundle(effects=()),
            turn_id="oversize",
            turn_sequence=TurnSequence(epoch, 2),
        )
    )
    assert outcome.status is CommitStatus.STATE_OVERSIZE
    after = committer.load_state(_ref())
    assert after is not None
    assert after.state == before.state
    assert after.base == before.base


def test_base_ref_round_trips_the_repository_cas_coordinates(tmp_path: Path) -> None:
    committer = EffectCommitter.open(tmp_path)
    committer.acquire_epoch()
    epoch = committer.current_epoch()
    genesis = _commit_genesis(committer, _ref(), epoch)
    assert type(genesis.base) is BaseRef
    assert genesis.base.revision == 0
    assert genesis.base.state_generation_id == "gen-a"
    assert len(genesis.base.payload_digest) == 64
