"""The only bridge component allowed to call the private state repository.

``EffectCommitter`` is the persistence boundary of the v3 shadow (design 4.2 and
15.1).  It journals a turn's *quantized* cognitive state and its deterministic
trace into one durable compare-and-commit revision, records v3 metrics
best-effort, and classifies every external effect as ``SUPPRESSED_SHADOW`` so the
shadow can never apply a REPLY/PROMPT/TOOL/BODY_TICK/history/memory/group effect.

Persistence lives on the float16 quantization grid (回溯红队 a16 MAJOR DoD): the
bytes stored are the exact ``encode_state`` output of the canonical decoded state,
and reloading ``decode_state`` reproduces it byte-for-byte, so a crash reload can
never fork the cognitive trajectory.  ``payload_digest`` in the CAS precondition
is therefore a pure function of those quantized bytes.

Migration adds a second durable artifact this component owns exclusively: the
immutable *generation seed anchor*.  Unlike the rotating cognitive revisions
(current + previous only), the anchor persists for the whole generation so a
corrupt learned payload can be re-projected from the stored seed without ever
rereading v2 (design 15.1 / 15.2).  The anchor is written and fsync'd *before*
the atomic pointer publication, so a crash before publication leaves an orphan
that recovery treats as "no committed migration" and cleans.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from enum import Enum

from sylanne_alpha.v3bridge._state_repository import (
    AbsentState,
    CommitPrecondition,
    CommitResult,
    JournalRecord,
    StateRepository,
)
from sylanne_alpha.v3bridge.limits import MAX_STATE_BYTES
from sylanne_alpha.v3bridge.session_identity import session_filename_token
from sylanne_alpha.v3core.canonical import canonical_json_bytes, canonical_sha256
from sylanne_alpha.v3core.contracts import SessionRef, TurnSequence
from sylanne_alpha.v3core.effects.models import (
    EffectBundle,
    V3MetricEffect,
    V3StateEffect,
    V3TraceEffect,
)
from sylanne_alpha.v3core.state.codec import (
    StateCodecError,
    StateSizeError,
    decode_state,
    encode_state,
    enforce_state_size,
)
from sylanne_alpha.v3core.state.models import V3State


# --------------------------------------------------------------------------- #
# Effect disposition policy (design 4.2)
# --------------------------------------------------------------------------- #


class EffectDisposition(Enum):
    """How the committer handles one proposed effect kind."""

    COMMITTED = "COMMITTED"  # V3_STATE / V3_TRACE journaled durably
    RECORDED = "RECORDED"  # V3_METRIC recorded best-effort
    SUPPRESSED_SHADOW = "SUPPRESSED_SHADOW"  # every external / v2 effect


#: The closed set of host effect kinds the shadow must never apply.  None of
#: these can even be represented in the closed :class:`EffectBundle` union; the
#: committer additionally refuses them by policy.
SUPPRESSED_EFFECT_KINDS = (
    "REPLY",
    "PROMPT",
    "TOOL",
    "BODY_TICK",
    "ASTRBOT_HISTORY",
    "V2_MEMORY",
    "GROUP_WRITE",
)


class CommitStatus(Enum):
    """Outcome of a committer operation: every repository result plus the two
    committer-local rejections that never touch the repository pointer."""

    COMMITTED = "COMMITTED"
    ALREADY_MIGRATED = "ALREADY_MIGRATED"
    DUPLICATE_TURN = "DUPLICATE_TURN"
    STALE_EPOCH = "STALE_EPOCH"
    STALE_STATE_GENERATION = "STALE_STATE_GENERATION"
    REVISION_CONFLICT = "REVISION_CONFLICT"
    BASE_DIGEST_MISMATCH = "BASE_DIGEST_MISMATCH"
    STALE_SEQUENCE = "STALE_SEQUENCE"
    CORRUPT_BASE = "CORRUPT_BASE"
    STATE_OVERSIZE = "STATE_OVERSIZE"
    STATE_CORRUPT = "STATE_CORRUPT"


_REPO_TO_STATUS = {result: CommitStatus[result.name] for result in CommitResult}


# --------------------------------------------------------------------------- #
# Bridge-owned commit DTOs
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class BaseRef:
    """The repository CAS coordinates of the base a turn advances from."""

    state_generation_id: str
    revision: int
    payload_digest: str
    last_committed_turn_sequence: TurnSequence | None


@dataclass(frozen=True, slots=True)
class LoadedState:
    """A loaded head: the decoded canonical state and its CAS coordinates."""

    state: V3State
    base: BaseRef


@dataclass(frozen=True, slots=True)
class TurnCommit:
    """One turn's proposed persistence unit.

    ``state_payload`` is the ``encode_state`` output of the canonical decoded
    next state (the quantized boundary); ``base`` is ``None`` only for a genesis
    (AbsentState) commit.  ``effects`` is the closed v3 union; any external effect
    kinds the shadow was asked to apply go in ``external_effect_kinds`` and are
    always suppressed.
    """

    session_ref: SessionRef
    base: BaseRef | None
    state_payload: bytes
    trace_bytes: bytes
    effects: EffectBundle
    turn_id: str
    turn_sequence: TurnSequence
    external_effect_kinds: tuple = ()


@dataclass(frozen=True, slots=True)
class MigrationCommit:
    """The atomic one-time seeding unit: initial state + sanitized seed anchor."""

    session_ref: SessionRef
    initial_state: V3State
    anchor: dict
    trace_bytes: bytes
    turn_id: str
    turn_sequence: TurnSequence


@dataclass(frozen=True, slots=True)
class CommitOutcome:
    """Result of a commit: the status plus per-effect dispositions."""

    status: CommitStatus
    dispositions: tuple
    committed_revision: int | None
    state_generation_id: str | None


# --------------------------------------------------------------------------- #
# Generation seed anchor framing (integrity-checked, digest-validated)
# --------------------------------------------------------------------------- #


def _frame_anchor(anchor: dict) -> bytes:
    return canonical_json_bytes({"anchor": anchor, "anchor_digest": canonical_sha256(anchor)})


def _parse_anchor(data: bytes) -> dict | None:
    try:
        envelope = json.loads(data.decode("utf-8"))
        inner = envelope["anchor"]
        if type(inner) is not dict:
            return None
        if canonical_sha256(inner) != envelope["anchor_digest"]:
            return None
        return inner
    except (ValueError, KeyError, TypeError, UnicodeDecodeError):
        return None


# --------------------------------------------------------------------------- #
# Committer
# --------------------------------------------------------------------------- #


class EffectCommitter:
    """Durable, CAS-guarded persistence boundary; the repository's only caller."""

    def __init__(self, repository: StateRepository) -> None:
        self._repo = repository

    @classmethod
    def open(cls, root: object, **repository_kwargs: object) -> "EffectCommitter":
        return cls(StateRepository(root, **repository_kwargs))

    @property
    def repository(self) -> StateRepository:
        return self._repo

    # -- epoch fence ---------------------------------------------------------

    def acquire_epoch(self) -> int:
        return self._repo.acquire_epoch()

    def seal_epoch(self, epoch: int) -> None:
        self._repo.seal_epoch(epoch)

    def current_epoch(self) -> int:
        return self._repo.current_epoch()

    # -- effect classification (design 4.2) ----------------------------------

    @staticmethod
    def disposition_for_external_kind(kind: str) -> EffectDisposition:
        if kind not in SUPPRESSED_EFFECT_KINDS:
            raise ValueError(f"{kind!r} is not a declared external effect kind")
        return EffectDisposition.SUPPRESSED_SHADOW

    @staticmethod
    def _disposition_for_effect(effect: object) -> EffectDisposition:
        if type(effect) is V3StateEffect or type(effect) is V3TraceEffect:
            return EffectDisposition.COMMITTED
        if type(effect) is V3MetricEffect:
            return EffectDisposition.RECORDED
        raise TypeError("only the closed v3 effect union is committable")

    def _dispositions(self, effects: EffectBundle, external_effect_kinds: tuple) -> tuple:
        items: list[tuple[str, EffectDisposition]] = [
            (type(effect).__name__, self._disposition_for_effect(effect))
            for effect in effects.effects
        ]
        for kind in external_effect_kinds:
            items.append((kind, self.disposition_for_external_kind(kind)))
        return tuple(items)

    # -- reads ---------------------------------------------------------------

    def _decode_snapshot_state(self, snapshot: object) -> V3State | None:
        try:
            encoded = json.loads(snapshot.canonical_cognitive_payload.decode("utf-8"))
            if type(encoded) is not str:
                return None
            return decode_state(encoded.encode("ascii"))
        except (ValueError, StateCodecError, UnicodeEncodeError, UnicodeDecodeError):
            return None

    def load_state(self, session_ref: SessionRef) -> LoadedState | None:
        snapshot = self._repo.load(session_ref)
        if snapshot is None:
            return None
        state = self._decode_snapshot_state(snapshot)
        if state is None:
            return None
        pointer = snapshot.pointer
        return LoadedState(
            state=state,
            base=BaseRef(
                state_generation_id=pointer.state_generation_id,
                revision=pointer.revision,
                payload_digest=pointer.payload_digest,
                last_committed_turn_sequence=pointer.last_committed_turn_sequence,
            ),
        )

    def load_valid_state(self, session_ref: SessionRef) -> V3State | None:
        loaded = self.load_state(session_ref)
        return loaded.state if loaded is not None else None

    def has_committed_pointer(self, session_ref: SessionRef) -> bool:
        token = session_filename_token(session_ref)
        return self._repo._load_pointer(token) is not None

    def pointer_generation(self, session_ref: SessionRef) -> str | None:
        token = session_filename_token(session_ref)
        pointer = self._repo._load_pointer(token)
        return pointer.state_generation_id if pointer is not None else None

    def pointer_high_watermark(self, session_ref: SessionRef) -> TurnSequence | None:
        token = session_filename_token(session_ref)
        pointer = self._repo._load_pointer(token)
        return pointer.last_committed_turn_sequence if pointer is not None else None

    # -- turn commit ---------------------------------------------------------

    def commit_turn(self, command: TurnCommit) -> CommitOutcome:
        dispositions = self._dispositions(command.effects, command.external_effect_kinds)
        # Size gate BEFORE any repository work: an oversize/corrupt payload is
        # rejected without touching the published pointer.
        try:
            enforce_state_size(command.state_payload, MAX_STATE_BYTES)
        except StateSizeError:
            return CommitOutcome(CommitStatus.STATE_OVERSIZE, dispositions, None, None)
        except StateCodecError:
            return CommitOutcome(CommitStatus.STATE_CORRUPT, dispositions, None, None)
        try:
            state = decode_state(command.state_payload)
        except StateCodecError:
            return CommitOutcome(CommitStatus.STATE_CORRUPT, dispositions, None, None)

        record = self._state_record(
            state, command.state_payload, command.trace_bytes, command.turn_id, command.turn_sequence
        )
        if command.base is None:
            precondition: CommitPrecondition | AbsentState = AbsentState()
        else:
            precondition = CommitPrecondition(
                writer_epoch=command.turn_sequence.writer_epoch,
                expected_state_generation_id=command.base.state_generation_id,
                expected_revision=command.base.revision,
                expected_payload_digest=command.base.payload_digest,
                turn_id=command.turn_id,
                turn_sequence=command.turn_sequence,
            )
        result = self._repo.compare_and_commit(command.session_ref, precondition, record)
        status = _REPO_TO_STATUS[result]
        if result is CommitResult.COMMITTED:
            return CommitOutcome(status, dispositions, state.revision, state.state_generation_id)
        return CommitOutcome(status, dispositions, None, None)

    # -- migration commit (atomic seed + initial state) ----------------------

    def commit_migration(self, command: MigrationCommit) -> CommitOutcome:
        token = session_filename_token(command.session_ref)
        if self.has_committed_pointer(command.session_ref):
            return CommitOutcome(CommitStatus.ALREADY_MIGRATED, (), None, None)
        payload = encode_state(command.initial_state, max_bytes=MAX_STATE_BYTES)
        # The immutable generation anchor is durable BEFORE the pointer publish.
        self._write_anchor_durable(token, command.initial_state.state_generation_id, command.anchor)
        record = self._state_record(
            command.initial_state, payload, command.trace_bytes, command.turn_id, command.turn_sequence
        )
        result = self._repo.compare_and_commit(command.session_ref, AbsentState(), record)
        if result is not CommitResult.COMMITTED:
            # A concurrent migration won (or already migrated): our anchor is a
            # loser orphan and must never remain as a second seed.
            self._remove_anchor(token, command.initial_state.state_generation_id)
            return CommitOutcome(_REPO_TO_STATUS[result], (), None, None)
        return CommitOutcome(
            CommitStatus.COMMITTED, (), command.initial_state.revision, command.initial_state.state_generation_id
        )

    def quarantine_new_generation(
        self,
        session_ref: SessionRef,
        *,
        initial_state: V3State,
        anchor: dict,
        trace_bytes: bytes,
        turn_id: str,
        writer_epoch: int,
        high_watermark: TurnSequence | None,
    ) -> CommitOutcome:
        """Fence the damaged generation and publish a fresh one from a stored seed.

        Carries the previous sequence high-watermark so delayed credit is never
        reopened (design 15.1).  Used only by recovery; the caller supplies the
        re-projected or neutral ``initial_state``.
        """

        token = session_filename_token(session_ref)
        old_pointer = self._repo._load_pointer(token)
        if old_pointer is None:
            return CommitOutcome(CommitStatus.STALE_STATE_GENERATION, (), None, None)
        payload = encode_state(initial_state, max_bytes=MAX_STATE_BYTES)
        self._write_anchor_durable(token, initial_state.state_generation_id, anchor)
        sequence = high_watermark if high_watermark is not None else TurnSequence(writer_epoch, 1)
        record = JournalRecord(
            schema_version=initial_state.schema_version,
            formula_version=initial_state.formula_version,
            source_digest=initial_state.source_digest,
            state_generation_id=initial_state.state_generation_id,
            revision=initial_state.revision,
            writer_epoch=writer_epoch,
            session_generation=initial_state.session_generation,
            model_revision=initial_state.model_revision,
            last_committed_turn_sequence=sequence,
            last_committed_turn_id=turn_id,
            cognitive_payload=payload.decode("ascii"),
            deterministic_trace=base64.b64encode(trace_bytes).decode("ascii"),
        )
        self._repo.quarantine_and_replace(old_pointer, record)
        self._remove_anchors_except(token, initial_state.state_generation_id)
        return CommitOutcome(
            CommitStatus.COMMITTED, (), initial_state.revision, initial_state.state_generation_id
        )

    # -- record builder ------------------------------------------------------

    @staticmethod
    def _state_record(
        state: V3State,
        payload: bytes,
        trace_bytes: bytes,
        turn_id: str,
        turn_sequence: TurnSequence,
    ) -> JournalRecord:
        # State AND trace share one immutable record: the pointer advances by CAS
        # only after both are durable, so recovery can never expose a committed
        # revision without its matching deterministic trace (design 4.2).
        return JournalRecord(
            schema_version=state.schema_version,
            formula_version=state.formula_version,
            source_digest=state.source_digest,
            state_generation_id=state.state_generation_id,
            revision=state.revision,
            writer_epoch=turn_sequence.writer_epoch,
            session_generation=state.session_generation,
            model_revision=state.model_revision,
            last_committed_turn_sequence=turn_sequence,
            last_committed_turn_id=turn_id,
            cognitive_payload=payload.decode("ascii"),
            deterministic_trace=base64.b64encode(trace_bytes).decode("ascii"),
        )

    # -- generation seed anchor store (committer-owned durable artifact) ------

    def _anchor_session_dir(self, token: str):
        return self._repo.root / "anchors" / token

    def _anchor_path(self, token: str, generation_id: str):
        return self._anchor_session_dir(token) / f"{generation_id}.anchor"

    def _write_anchor_durable(self, token: str, generation_id: str, anchor: dict) -> None:
        directory = self._anchor_session_dir(token)
        directory.mkdir(parents=True, exist_ok=True)
        data = _frame_anchor(anchor)
        staging = directory / f".{os.urandom(8).hex()}.tmp"
        fd = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            view = memoryview(data)
            offset = 0
            while offset < len(view):
                offset += os.write(fd, view[offset:])
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(staging, self._anchor_path(token, generation_id))

    def read_anchor(self, session_ref: SessionRef) -> dict | None:
        token = session_filename_token(session_ref)
        generation_id = self.pointer_generation(session_ref)
        if generation_id is None:
            return None
        try:
            data = self._anchor_path(token, generation_id).read_bytes()
        except OSError:
            return None
        return _parse_anchor(data)

    def _remove_anchor(self, token: str, generation_id: str) -> None:
        try:
            self._anchor_path(token, generation_id).unlink()
        except OSError:  # pragma: no cover - already gone
            pass

    def _remove_anchors_except(self, token: str, keep_generation_id: str | None) -> int:
        directory = self._anchor_session_dir(token)
        if not directory.exists():
            return 0
        removed = 0
        for path in directory.glob("*.anchor"):
            if keep_generation_id is None or path.stem != keep_generation_id:
                try:
                    path.unlink()
                    removed += 1
                except OSError:  # pragma: no cover
                    pass
        return removed

    def clean_orphan_anchors(self, session_ref: SessionRef) -> int:
        """Remove anchors not matching the current committed generation.

        With no committed pointer every anchor is an orphan (a crashed migration
        before pointer publication), so all are removed.
        """

        token = session_filename_token(session_ref)
        keep = self.pointer_generation(session_ref)
        return self._remove_anchors_except(token, keep)


__all__ = [
    "BaseRef",
    "CommitOutcome",
    "CommitStatus",
    "EffectCommitter",
    "EffectDisposition",
    "LoadedState",
    "MigrationCommit",
    "SUPPRESSED_EFFECT_KINDS",
    "TurnCommit",
]
