"""RED/GREEN tests for Task 11 MigrationCoordinator + recovery (design 15.2).

Migration freezes one immutable ``V2SeedSnapshotV1`` under the v2 turn lock,
releases that lock strictly before any v3 lock, projects a pure initial state,
and atomically commits ``SeedRecord + initial state + receipt + trace`` as one
generation.  The sanitized generation seed is an immutable anchor that outlives
cognitive-revision compaction and can recover a corrupt payload without ever
rereading v2.  Concurrent migration produces exactly one seed.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest

from sylanne_alpha.v3bridge.effect_committer import (
    CommitStatus,
    EffectCommitter,
    MigrationCommit,
    TurnCommit,
)
from sylanne_alpha.v3bridge._state_repository import FaultPoint
from sylanne_alpha.v3bridge.limits import MAX_STATE_BYTES
from sylanne_alpha.v3bridge.session_identity import SessionIdentityKey, session_filename_token
from sylanne_alpha.v3bridge.migration_coordinator import (
    MigrationCoordinator,
    RecoveryDecision,
    build_seed_anchor,
    new_generation_id,
    seed_frame_from_v2,
)
from sylanne_alpha.v2core.shadow_snapshot import V2SeedSnapshotV1
from sylanne_alpha.v3core import formula_v1 as formula
from sylanne_alpha.v3core.contracts import (
    Action,
    ComputeProfile,
    CoreInvocation,
    TurnContextClass,
    TurnEnvelope,
    TurnKey,
    TurnSequence,
)
from sylanne_alpha.v3core.effects.models import EffectBundle, V3StateEffect, V3TraceEffect
from sylanne_alpha.v3core.orchestrator import orchestrate
from sylanne_alpha.v3core.state.seed import SeedProjector


_IDENTITY = SessionIdentityKey(key_id="migration-v1", secret=b"m" * 32)


def _ref(name: str = "umo-1"):
    ref = _IDENTITY.session_ref("qq", name, session_generation=0)
    assert ref is not None
    return ref


def _snapshot() -> V2SeedSnapshotV1:
    return V2SeedSnapshotV1(
        user_bond_ema=0.8,
        user_hesitation_ema=0.2,
        emotion_fast_ema=0.4,
        emotion_slow_ema=-0.3,
        narrative_baseline_warmth_bias=0.6,
        narrative_ossification_tension=0.1,
    )


# --------------------------------------------------------------------------- #
# Fake v2 / v3 locks that record acquire/release ordering
# --------------------------------------------------------------------------- #


class _LockLog:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.freeze_calls = 0


@contextmanager
def _fake_v2_lock(log: _LockLog):
    log.events.append("v2_enter")
    try:
        yield
    finally:
        log.events.append("v2_exit")


@contextmanager
def _fake_v3_lock(log: _LockLog):
    log.events.append("v3_enter")
    try:
        yield
    finally:
        log.events.append("v3_exit")


def _freezer(log: _LockLog, snapshot: V2SeedSnapshotV1):
    def freeze() -> V2SeedSnapshotV1:
        log.freeze_calls += 1
        with _fake_v2_lock(log):
            return snapshot

    return freeze


def _coordinator(committer: EffectCommitter) -> MigrationCoordinator:
    return MigrationCoordinator(committer, projector=SeedProjector())


def _migrate(coordinator: MigrationCoordinator, committer: EffectCommitter, ref, log: _LockLog, snapshot=None):
    return coordinator.migrate(
        ref,
        writer_epoch=committer.current_epoch(),
        session_generation=0,
        source_digest="a" * 64,
        v3_migration_lock=_fake_v3_lock(log),
        freeze_v2_seed=_freezer(log, snapshot or _snapshot()),
    )


# --------------------------------------------------------------------------- #
# Learned-turn helper (orchestrate + commit_turn)
# --------------------------------------------------------------------------- #


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


def _profile() -> ComputeProfile:
    snn_enabled, ticks, stdp_enabled, reuse = formula.COMPUTE_PROFILES["FULL_24_STDP"]
    return ComputeProfile(
        profile_id="FULL_24_STDP",
        snn_enabled=snn_enabled,
        ticks=ticks,
        stdp_enabled=stdp_enabled,
        reuse_last_summary=reuse,
        math_backend="scalar-v1",
        formula_version=formula.FORMULA_VERSION,
        model_version=formula.FORMULA_VERSION,
    )


def _learned_turn(committer: EffectCommitter, ref, epoch: int, local_sequence: int, turn_id: str):
    loaded = committer.load_state(ref)
    assert loaded is not None
    envelope = TurnEnvelope(
        turn_key=TurnKey(plugin_instance_id="p", session_ref=ref, bridge_request_nonce="n", request_attempt=0),
        turn_id=turn_id,
        sequence=TurnSequence(epoch, local_sequence),
        compute_profile=_profile(),
        deterministic_seed=b"d" * 16,
        observation=(_raw_values(), Action.SPEAK),
        context=TurnContextClass.ADDRESSED,
    )
    result = orchestrate(
        CoreInvocation(envelope=envelope, base_state=loaded.state, projected_actual_outcome=(Action.SPEAK, None))
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
    assert outcome.status is CommitStatus.COMMITTED
    return outcome


# --------------------------------------------------------------------------- #
# One atomic migration commit
# --------------------------------------------------------------------------- #


def test_migration_is_one_atomic_seed_state_receipt_trace_commit(tmp_path: Path) -> None:
    committer = EffectCommitter.open(tmp_path)
    committer.acquire_epoch()
    log = _LockLog()
    outcome = _migrate(_coordinator(committer), committer, _ref(), log)
    assert outcome.status is CommitStatus.COMMITTED

    loaded = committer.load_state(_ref())
    assert loaded is not None
    assert loaded.state.revision == 0
    assert loaded.state.state_generation_id == outcome.generation_id

    anchor = committer.read_anchor(_ref())
    assert anchor is not None
    assert anchor["provenance"] == "V2_SEED"
    assert anchor["receipt"]["initial_revision"] == 0
    assert anchor["receipt"]["seed_digest"] == anchor["seed_digest"]

    repo = committer.repository
    journals = list(repo.sessions_directory.rglob("*.journal"))
    assert len(journals) == 1
    anchors = list((repo.root / "anchors").rglob("*.anchor"))
    assert len(anchors) == 1


def test_no_visible_provisional_migration_revision(tmp_path: Path) -> None:
    def inject(point: FaultPoint) -> None:
        if point is FaultPoint.BEFORE_POINTER_PUBLISH:
            raise RuntimeError("crash before migration pointer publish")

    crashing = EffectCommitter.open(tmp_path, fault_injector=inject)
    crashing.acquire_epoch()
    log = _LockLog()
    with pytest.raises(RuntimeError, match="crash before"):
        _migrate(_coordinator(crashing), crashing, _ref(), log)

    # A fresh committer sees no committed migration: no pointer means no seed.
    recovered = EffectCommitter.open(tmp_path)
    recovered.acquire_epoch()
    assert recovered.load_state(_ref()) is None
    outcome = _coordinator(recovered).recover(
        _ref(), writer_epoch=recovered.current_epoch(), session_generation=0, source_digest="a" * 64
    )
    assert outcome.decision is RecoveryDecision.FRESH_MIGRATION_REQUIRED
    # The dangling pre-publish anchor is cleaned; it never became a visible migration.
    assert not list((recovered.repository.root / "anchors").rglob("*.anchor"))


def test_v2_lock_is_released_before_the_v3_lock_is_taken(tmp_path: Path) -> None:
    committer = EffectCommitter.open(tmp_path)
    committer.acquire_epoch()
    log = _LockLog()
    _migrate(_coordinator(committer), committer, _ref(), log)
    assert log.events == ["v2_enter", "v2_exit", "v3_enter", "v3_exit"]
    # v2 and v3 locks are never nested.
    assert log.events.index("v2_exit") < log.events.index("v3_enter")


# --------------------------------------------------------------------------- #
# Concurrent migration produces exactly one seed
# --------------------------------------------------------------------------- #


def test_concurrent_migration_produces_a_single_seed(tmp_path: Path) -> None:
    committer = EffectCommitter.open(tmp_path)
    epoch = committer.acquire_epoch()
    frame = seed_frame_from_v2(_snapshot())

    def _commit(gen: str):
        initial = SeedProjector().build_initial_state(
            frame, session_ref=_ref(), state_generation_id=gen, source_digest="a" * 64, writer_epoch=epoch
        )
        anchor = build_seed_anchor(gen, frame, session_generation=0, provenance="V2_SEED")
        return committer.commit_migration(
            MigrationCommit(
                session_ref=_ref(),
                initial_state=initial,
                anchor=anchor,
                trace_bytes=b"migration-trace",
                turn_id=f"v3-migration-{gen}",
                turn_sequence=TurnSequence(epoch, 1),
            )
        )

    gen_one = new_generation_id()
    gen_two = new_generation_id()
    first = _commit(gen_one)
    second = _commit(gen_two)  # racer that lost the CAS
    assert first.status is CommitStatus.COMMITTED
    assert second.status is CommitStatus.ALREADY_MIGRATED

    # Exactly one live seed anchor survives; the loser's anchor is cleaned.
    anchors = list((committer.repository.root / "anchors").rglob("*.anchor"))
    assert len(anchors) == 1
    assert committer.pointer_generation(_ref()) == gen_one
    loaded = committer.load_state(_ref())
    assert loaded is not None and loaded.state.state_generation_id == gen_one


def test_learned_state_is_never_reprojected_by_a_second_migration(tmp_path: Path) -> None:
    committer = EffectCommitter.open(tmp_path)
    epoch = committer.acquire_epoch()
    log = _LockLog()
    coordinator = _coordinator(committer)
    migrated = _migrate(coordinator, committer, _ref(), log)
    assert migrated.status is CommitStatus.COMMITTED

    _learned_turn(committer, _ref(), epoch, 2, "turn-2")
    _learned_turn(committer, _ref(), epoch, 3, "turn-3")
    before = committer.load_state(_ref())
    assert before is not None and before.state.revision == 2

    second_log = _LockLog()
    again = coordinator.migrate(
        _ref(),
        writer_epoch=epoch,
        session_generation=0,
        source_digest="a" * 64,
        v3_migration_lock=_fake_v3_lock(second_log),
        freeze_v2_seed=_freezer(second_log, _snapshot()),
    )
    assert again.status is CommitStatus.ALREADY_MIGRATED
    assert second_log.freeze_calls == 0  # no v2 reread
    after = committer.load_state(_ref())
    assert after is not None and after.state.revision == 2  # learned state intact
    assert after.state == before.state


# --------------------------------------------------------------------------- #
# Five explicit recovery rows (design 15.2 table)
# --------------------------------------------------------------------------- #


def test_recovery_row1_absent_all_requires_fresh_migration(tmp_path: Path) -> None:
    committer = EffectCommitter.open(tmp_path)
    committer.acquire_epoch()
    outcome = _coordinator(committer).recover(
        _ref(), writer_epoch=committer.current_epoch(), session_generation=0, source_digest="a" * 64
    )
    assert outcome.decision is RecoveryDecision.FRESH_MIGRATION_REQUIRED


def test_recovery_row2_orphan_staging_only_is_cleaned_and_not_migrated(tmp_path: Path) -> None:
    def inject(point: FaultPoint) -> None:
        if point is FaultPoint.BEFORE_POINTER_PUBLISH:
            raise RuntimeError("crash")

    crashing = EffectCommitter.open(tmp_path, fault_injector=inject)
    crashing.acquire_epoch()
    with pytest.raises(RuntimeError):
        _migrate(_coordinator(crashing), crashing, _ref(), _LockLog())

    committer = EffectCommitter.open(tmp_path)
    committer.acquire_epoch()
    assert list((committer.repository.root / "anchors").rglob("*.anchor"))  # orphan present
    outcome = _coordinator(committer).recover(
        _ref(), writer_epoch=committer.current_epoch(), session_generation=0, source_digest="a" * 64
    )
    assert outcome.decision is RecoveryDecision.FRESH_MIGRATION_REQUIRED
    assert not list((committer.repository.root / "anchors").rglob("*.anchor"))


def test_recovery_row3_committed_and_consistent_loads_existing(tmp_path: Path) -> None:
    committer = EffectCommitter.open(tmp_path)
    committer.acquire_epoch()
    migrated = _migrate(_coordinator(committer), committer, _ref(), _LockLog())
    outcome = _coordinator(committer).recover(
        _ref(), writer_epoch=committer.current_epoch(), session_generation=0, source_digest="a" * 64
    )
    assert outcome.decision is RecoveryDecision.LOADED_EXISTING
    assert outcome.state is not None
    assert outcome.state.state_generation_id == migrated.generation_id


def test_recovery_row4_valid_seed_corrupt_payload_reprojects_from_seed(tmp_path: Path) -> None:
    committer = EffectCommitter.open(tmp_path)
    epoch = committer.acquire_epoch()
    log = _LockLog()
    snapshot = _snapshot()
    migrated = _migrate(_coordinator(committer), committer, _ref(), log, snapshot=snapshot)
    old_generation = migrated.generation_id

    # Corrupt the current cognitive payload while the seed anchor stays valid.
    repo = committer.repository
    pointer = repo._load_pointer(session_filename_token(_ref()))
    (repo.root / pointer.current_journal).write_bytes(b"{corrupt-payload")
    assert committer.load_state(_ref()) is None

    outcome = _coordinator(committer).recover(
        _ref(), writer_epoch=epoch, session_generation=0, source_digest="a" * 64
    )
    assert outcome.decision is RecoveryDecision.RECOVERED_FROM_SEED
    assert outcome.generation_id != old_generation
    # The recovered state is the pure projection of the STORED seed (v2 never reread).
    expected_latent = SeedProjector().project_latent(seed_frame_from_v2(snapshot))
    assert outcome.state.latent_axes == expected_latent


def test_recovery_row5_corrupt_seed_starts_a_neutral_generation(tmp_path: Path) -> None:
    committer = EffectCommitter.open(tmp_path)
    epoch = committer.acquire_epoch()
    migrated = _migrate(_coordinator(committer), committer, _ref(), _LockLog())
    old_generation = migrated.generation_id

    # Corrupt the seed anchor of the committed generation.
    token = session_filename_token(_ref())
    anchor_file = next((committer.repository.root / "anchors" / token).glob("*.anchor"))
    anchor_file.write_bytes(b"garbage-anchor")
    assert committer.read_anchor(_ref()) is None

    outcome = _coordinator(committer).recover(
        _ref(), writer_epoch=epoch, session_generation=0, source_digest="a" * 64
    )
    assert outcome.decision is RecoveryDecision.RECOVERED_NEUTRAL
    assert outcome.generation_id != old_generation
    # Neutral generation: every latent axis is the zero fixed point.
    assert outcome.state.latent_axes == tuple(0.0 for _ in outcome.state.latent_axes)


# --------------------------------------------------------------------------- #
# Immutable generation seed anchor survives compaction and recovers a payload
# --------------------------------------------------------------------------- #


def test_seed_anchor_survives_compaction_and_recovers_without_rereading_v2(tmp_path: Path) -> None:
    committer = EffectCommitter.open(tmp_path)
    epoch = committer.acquire_epoch()
    log = _LockLog()
    snapshot = _snapshot()
    coordinator = _coordinator(committer)
    coordinator.migrate(
        _ref(),
        writer_epoch=epoch,
        session_generation=0,
        source_digest="a" * 64,
        v3_migration_lock=_fake_v3_lock(log),
        freeze_v2_seed=_freezer(log, snapshot),
    )

    # Three learned commits rotate the cognitive journals past revision 0.
    for step in range(3):
        _learned_turn(committer, _ref(), epoch, 2 + step, f"turn-{2 + step}")

    repo = committer.repository
    # Compaction retains only current + previous cognitive revision.
    assert len(list(repo.sessions_directory.rglob("*.journal"))) <= 2
    # The immutable generation seed anchor still exists and counts against usage.
    anchors = list((repo.root / "anchors").rglob("*.anchor"))
    assert len(anchors) == 1
    assert anchors[0].stat().st_size > 0
    assert repo.usage_bytes() >= anchors[0].stat().st_size
    high_watermark = committer.pointer_high_watermark(_ref())

    # Corrupt the current learned payload and recover from the surviving seed.
    pointer = repo._load_pointer(session_filename_token(_ref()))
    (repo.root / pointer.current_journal).write_bytes(b"{corrupt")
    assert committer.load_state(_ref()) is None

    recovery_log = _LockLog()
    coordinator2 = MigrationCoordinator(committer, projector=SeedProjector())
    outcome = coordinator2.recover(
        _ref(), writer_epoch=epoch, session_generation=0, source_digest="a" * 64
    )
    assert outcome.decision is RecoveryDecision.RECOVERED_FROM_SEED
    assert recovery_log.freeze_calls == 0  # v2 never reread
    expected_latent = SeedProjector().project_latent(seed_frame_from_v2(snapshot))
    assert outcome.state.latent_axes == expected_latent
    # The replacement generation carries forward the sequence high-watermark.
    assert committer.pointer_high_watermark(_ref()) == high_watermark
