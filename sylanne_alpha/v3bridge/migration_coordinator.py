"""One-time v2 seeding and explicit crash recovery for the v3 shadow (design 15.2).

``MigrationCoordinator`` orchestrates the migration protocol without ever
touching the repository directly (only :class:`EffectCommitter` may): it obtains
an immutable ``V2SeedSnapshotV1`` under the v2 turn lock, releases that lock
*before* taking any v3 lock, converts it into a sanitized core-owned
``SeedFrame``, pure-projects the initial ``V3State`` via ``SeedProjector``, and
asks the committer to atomically journal ``SeedRecord + initial state + receipt
+ trace`` as one generation.  Concurrent migration yields exactly one seed.

Recovery is a pure decision over three observable facts (committed pointer,
digest-valid generation seed anchor, loadable cognitive payload) and never
rereads v2 — a corrupt payload is re-projected from the *stored* immutable seed,
and a corrupt/missing seed starts a neutral generation.  v2 state is never
overwritten, deleted, or reverse-projected.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, fields
from enum import Enum

from sylanne_alpha.v2core.shadow_snapshot import V2SeedSnapshotV1
from sylanne_alpha.v3bridge.effect_committer import (
    CommitStatus,
    EffectCommitter,
    MigrationCommit,
)
from sylanne_alpha.v3core.canonical import canonical_sha256
from sylanne_alpha.v3core.contracts import SessionRef, TurnSequence
from sylanne_alpha.v3core.state.models import V3State
from sylanne_alpha.v3core.state.seed import SeedFrame, SeedProjector, neutral_seed_frame


SEED_RECORD_SCHEMA_V1 = "sylanne.v3.seed-record.v1"
MIGRATION_RECEIPT_SCHEMA_V1 = "sylanne.v3.migration-receipt.v1"
MIGRATOR_VERSION = "sylanne.v3.migrator.v1"

_SEED_FIELD_NAMES = tuple(
    descriptor.name for descriptor in fields(SeedFrame) if descriptor.name != "style_signature_seed"
)


# --------------------------------------------------------------------------- #
# v2 -> core seed conversion (bridge-only; v3core never imports the v2 DTO)
# --------------------------------------------------------------------------- #


def _clip_unit(value: float) -> float:
    if value > 1.0:
        return 1.0
    if value < -1.0:
        return -1.0
    return value


def _centered01(value: float | None) -> float | None:
    """Center a v2 [0,1] EMA on the neutral 0.0 seed fixed point."""

    if value is None:
        return None
    return _clip_unit(2.0 * float(value) - 1.0)


def _bounded(value: float | None) -> float | None:
    """Bound an already-signed v2 deviation into the seed range."""

    if value is None:
        return None
    return _clip_unit(float(value))


def seed_frame_from_v2(snapshot: V2SeedSnapshotV1) -> SeedFrame:
    """Project the immutable v2 seed facts onto a sanitized core ``SeedFrame``.

    Mapping (design 15.2): v2 hesitation/bond -> uncertainty/affiliation seed,
    v2 emotion fast/slow -> fast/mid valence seed, v2 narrative/ossification ->
    slow affiliation/agency seed.  Only the axes for which a distinct v2 fact
    exists are seeded; a missing (``None``) fact stays neutral.
    """

    if type(snapshot) is not V2SeedSnapshotV1:
        raise TypeError("seed_frame_from_v2 requires a V2SeedSnapshotV1")
    return SeedFrame(
        bond=_centered01(snapshot.user_bond_ema),
        hesitation=_centered01(snapshot.user_hesitation_ema),
        emotion_valence_fast=_bounded(snapshot.emotion_fast_ema),
        emotion_valence_slow=_bounded(snapshot.emotion_slow_ema),
        narrative=_centered01(snapshot.narrative_baseline_warmth_bias),
        ossification=_centered01(snapshot.narrative_ossification_tension),
    )


# --------------------------------------------------------------------------- #
# Sanitized seed anchor <-> SeedFrame
# --------------------------------------------------------------------------- #


def build_seed_anchor(
    generation_id: str,
    frame: SeedFrame,
    *,
    session_generation: int,
    provenance: str,
) -> dict:
    """Build the sanitized, digest-anchored immutable generation seed record."""

    seed = {
        "fields": {name: getattr(frame, name) for name in _SEED_FIELD_NAMES},
        "style_signature_seed": (
            list(frame.style_signature_seed) if frame.style_signature_seed is not None else None
        ),
    }
    seed_digest = canonical_sha256(seed)
    return {
        "schema": SEED_RECORD_SCHEMA_V1,
        "state_generation_id": generation_id,
        "session_generation": session_generation,
        "provenance": provenance,
        "seed": seed,
        "seed_digest": seed_digest,
        "receipt": {
            "schema": MIGRATION_RECEIPT_SCHEMA_V1,
            "seed_digest": seed_digest,
            "migrator_version": MIGRATOR_VERSION,
            "state_generation_id": generation_id,
            "initial_revision": 0,
        },
    }


def _frame_from_anchor(anchor: dict) -> SeedFrame:
    seed = anchor["seed"]
    stored = seed["fields"]
    style = seed.get("style_signature_seed")
    kwargs: dict[str, object] = {}
    for name in _SEED_FIELD_NAMES:
        value = stored.get(name)
        kwargs[name] = None if value is None else float(value)
    style_seed = tuple(int(bucket) for bucket in style) if style is not None else None
    return SeedFrame(style_signature_seed=style_seed, **kwargs)


def new_generation_id() -> str:
    """Allocate an opaque, never-reused state generation id."""

    return os.urandom(16).hex()


def _migration_trace(generation_id: str, kind: str) -> bytes:
    return canonical_sha256({"migration": kind, "generation": generation_id}).encode("ascii")


# --------------------------------------------------------------------------- #
# Recovery vocabulary
# --------------------------------------------------------------------------- #


class RecoveryDecision(Enum):
    FRESH_MIGRATION_REQUIRED = "FRESH_MIGRATION_REQUIRED"  # rows 1 & 2
    LOADED_EXISTING = "LOADED_EXISTING"  # row 3
    RECOVERED_FROM_SEED = "RECOVERED_FROM_SEED"  # row 4
    RECOVERED_NEUTRAL = "RECOVERED_NEUTRAL"  # row 5


@dataclass(frozen=True, slots=True)
class RecoveryOutcome:
    decision: RecoveryDecision
    state: V3State | None
    generation_id: str | None


@dataclass(frozen=True, slots=True)
class MigrationOutcome:
    status: CommitStatus
    generation_id: str | None
    state: V3State | None


# --------------------------------------------------------------------------- #
# Coordinator
# --------------------------------------------------------------------------- #


class MigrationCoordinator:
    """Freezes v2 once, projects, and atomically seeds; recovers without v2."""

    def __init__(self, committer: EffectCommitter, *, projector: SeedProjector | None = None) -> None:
        self._committer = committer
        self._projector = projector if projector is not None else SeedProjector()

    def migrate(
        self,
        session_ref: SessionRef,
        *,
        writer_epoch: int,
        session_generation: int,
        source_digest: str,
        v3_migration_lock: object,
        seed_snapshot: V2SeedSnapshotV1 | None = None,
        freeze_v2_seed: object = None,
    ) -> MigrationOutcome:
        # Idempotency BEFORE any v2 read: an already-migrated session never
        # refreezes v2 or reprojects learned state.
        if self._committer.has_committed_pointer(session_ref):
            return self._already_migrated(session_ref)

        if seed_snapshot is None:
            if freeze_v2_seed is None:
                raise ValueError("migrate requires either seed_snapshot or freeze_v2_seed")
            # The freezer owns the v2 turn lock and releases it before returning.
            seed_snapshot = freeze_v2_seed()
        if type(seed_snapshot) is not V2SeedSnapshotV1:
            raise TypeError("frozen seed must be a V2SeedSnapshotV1")
        frame = seed_frame_from_v2(seed_snapshot)

        # The v3 migration lock is taken strictly AFTER the v2 lock is released;
        # v2 and v3 locks are never held together.
        with v3_migration_lock:
            if self._committer.has_committed_pointer(session_ref):
                return self._already_migrated(session_ref)
            generation_id = new_generation_id()
            initial = self._projector.build_initial_state(
                frame,
                session_ref=session_ref,
                state_generation_id=generation_id,
                source_digest=source_digest,
                session_generation=session_generation,
                writer_epoch=writer_epoch,
            )
            anchor = build_seed_anchor(
                generation_id, frame, session_generation=session_generation, provenance="V2_SEED"
            )
            outcome = self._committer.commit_migration(
                MigrationCommit(
                    session_ref=session_ref,
                    initial_state=initial,
                    anchor=anchor,
                    trace_bytes=_migration_trace(generation_id, "seed"),
                    turn_id=f"v3-migration-{generation_id}",
                    turn_sequence=TurnSequence(writer_epoch, 1),
                )
            )
            if outcome.status is CommitStatus.COMMITTED:
                return MigrationOutcome(CommitStatus.COMMITTED, generation_id, initial)
            return self._already_migrated(session_ref, fallback_status=outcome.status)

    def recover(
        self,
        session_ref: SessionRef,
        *,
        writer_epoch: int,
        session_generation: int,
        source_digest: str,
    ) -> RecoveryOutcome:
        # Row 1 (absent) / Row 2 (orphan staging only): no committed pointer.
        if not self._committer.has_committed_pointer(session_ref):
            self._committer.clean_orphan_anchors(session_ref)
            return RecoveryOutcome(RecoveryDecision.FRESH_MIGRATION_REQUIRED, None, None)

        state = self._committer.load_valid_state(session_ref)
        anchor = self._committer.read_anchor(session_ref)

        if anchor is not None:
            if state is not None:
                # Row 3: committed and internally consistent -> load learned state.
                return RecoveryOutcome(RecoveryDecision.LOADED_EXISTING, state, state.state_generation_id)
            # Row 4: digest-valid seed, missing/corrupt payload -> re-project from
            # the STORED immutable seed; v2 is never reread.
            frame = _frame_from_anchor(anchor)
            return self._quarantine_new_generation(
                session_ref,
                frame,
                writer_epoch=writer_epoch,
                session_generation=session_generation,
                source_digest=source_digest,
                provenance="RECOVERED_FROM_SEED",
                decision=RecoveryDecision.RECOVERED_FROM_SEED,
            )

        # Row 5: missing/corrupt seed -> quarantine and start a neutral generation;
        # never silently reread current v2 as if it were the original seed.
        return self._quarantine_new_generation(
            session_ref,
            neutral_seed_frame(),
            writer_epoch=writer_epoch,
            session_generation=session_generation,
            source_digest=source_digest,
            provenance="RECOVERED_NEUTRAL",
            decision=RecoveryDecision.RECOVERED_NEUTRAL,
        )

    # -- helpers -------------------------------------------------------------

    def _already_migrated(
        self, session_ref: SessionRef, *, fallback_status: CommitStatus = CommitStatus.ALREADY_MIGRATED
    ) -> MigrationOutcome:
        return MigrationOutcome(
            fallback_status,
            self._committer.pointer_generation(session_ref),
            self._committer.load_valid_state(session_ref),
        )

    def _quarantine_new_generation(
        self,
        session_ref: SessionRef,
        frame: SeedFrame,
        *,
        writer_epoch: int,
        session_generation: int,
        source_digest: str,
        provenance: str,
        decision: RecoveryDecision,
    ) -> RecoveryOutcome:
        high_watermark = self._committer.pointer_high_watermark(session_ref)
        generation_id = new_generation_id()
        initial = self._projector.build_initial_state(
            frame,
            session_ref=session_ref,
            state_generation_id=generation_id,
            source_digest=source_digest,
            session_generation=session_generation,
            writer_epoch=writer_epoch,
        )
        anchor = build_seed_anchor(
            generation_id, frame, session_generation=session_generation, provenance=provenance
        )
        self._committer.quarantine_new_generation(
            session_ref,
            initial_state=initial,
            anchor=anchor,
            trace_bytes=_migration_trace(generation_id, "recovery"),
            turn_id=f"v3-recover-{generation_id}",
            writer_epoch=writer_epoch,
            high_watermark=high_watermark,
        )
        return RecoveryOutcome(decision, initial, generation_id)


__all__ = [
    "MIGRATION_RECEIPT_SCHEMA_V1",
    "MIGRATOR_VERSION",
    "MigrationCoordinator",
    "MigrationOutcome",
    "RecoveryDecision",
    "RecoveryOutcome",
    "SEED_RECORD_SCHEMA_V1",
    "build_seed_anchor",
    "new_generation_id",
    "seed_frame_from_v2",
]
