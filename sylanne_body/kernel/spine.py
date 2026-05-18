from dataclasses import dataclass, field
from hashlib import sha256

from sylanne_body.event.source import EventSource
from sylanne_body.law.sovereignty import UserSovereignty
from sylanne_body.soma.affect import AffectState, sense_affect
from sylanne_body.soma.crying import CryingState, CryingThreshold, sense_crying
from sylanne_body.speech.affect import compose_affect_surface, validate_affect_surface
from sylanne_body.speech.crying import compose_crying_surface, validate_crying_surface


@dataclass(frozen=True)
class KernelEvent:
    text: str
    source: EventSource
    relation_key: str = "default"
    event_id: str = field(init=False)

    def __post_init__(self) -> None:
        seed = f"{self.source.value}\0{self.relation_key}\0{self.text}".encode("utf-8")
        object.__setattr__(self, "event_id", f"kev_{sha256(seed).hexdigest()[:16]}")


@dataclass(frozen=True)
class BodyState:
    affect: AffectState
    crying: CryingState
    sovereignty: UserSovereignty
    posture: str = "open"


@dataclass(frozen=True)
class ExpressionResidue:
    text: str
    source: EventSource = EventSource.INTERNAL_BODY_SURFACE
    kind: str = "nonhuman_expression_residue"


@dataclass(frozen=True)
class CommitRecord:
    accepted: bool
    reason: str

    def to_history_dict(self, *, event: KernelEvent, body: BodyState) -> dict[str, str | bool]:
        return {
            "event_id": event.event_id,
            "source": event.source.value,
            "reason": self.reason,
            "posture": body.posture,
            "affect": body.affect.primary.value,
            "internal_only": True,
            "public_api_eligible": False,
        }


@dataclass(frozen=True)
class KernelSnapshot:
    event_id: str
    source: EventSource
    affect: str
    crying_tears: float
    internal_only: bool = True
    public_api_eligible: bool = False

    def to_public_dict(self) -> dict[str, str | float | bool]:
        return {
            "event_id": self.event_id,
            "source": self.source.value,
            "affect": self.affect,
            "crying_tears": self.crying_tears,
            "internal_only": self.internal_only,
            "public_api_eligible": self.public_api_eligible,
        }


@dataclass(frozen=True)
class KernelResult:
    body: BodyState
    residue: ExpressionResidue
    commit: CommitRecord
    snapshot: KernelSnapshot


class KernelSpine:
    def __init__(self, *, sovereignty: UserSovereignty | None = None, history_limit: int = 24) -> None:
        self._sovereignty = sovereignty or UserSovereignty()
        self._history_limit = history_limit
        self._commit_history: list[dict[str, str | bool]] = []
        self._sealed = False
        self._seal_reason = ""

    def receive(self, event: KernelEvent) -> KernelResult:
        body = self._body_for(event)
        residue = self._compose_residue(body)
        commit = self._commit(event)
        snapshot = self._snapshot(event, body)
        self._record_commit(event, body, commit)
        return KernelResult(body=body, residue=residue, commit=commit, snapshot=snapshot)

    def _body_for(self, event: KernelEvent) -> BodyState:
        self._sovereignty.validate()
        affect = sense_affect(text=event.text, source=event.source)
        crying = sense_crying(text=event.text, source=event.source, threshold=CryingThreshold())
        return BodyState(
            affect=affect,
            crying=crying,
            sovereignty=self._sovereignty,
            posture=self._posture(event),
        )

    def export_commit_history(self) -> list[dict[str, str | bool]]:
        return [dict(item) for item in self._commit_history]

    def restart_after_boundary(self, event: KernelEvent) -> KernelResult:
        if event.source is not EventSource.USER_COMMAND:
            body = self._body_for(event)
            residue = self._compose_residue(body)
            commit = CommitRecord(accepted=False, reason="restart_requires_user_command")
            snapshot = self._snapshot(event, body)
            return KernelResult(body=body, residue=residue, commit=commit, snapshot=snapshot)

        self._sealed = False
        self._seal_reason = ""
        body = self._body_for(event)
        residue = self._compose_residue(body)
        commit = CommitRecord(accepted=True, reason="accepted_explicit_boundary_restart")
        snapshot = self._snapshot(event, body)
        self._record_commit(event, body, commit)
        return KernelResult(body=body, residue=residue, commit=commit, snapshot=snapshot)

    def export_seal_state(self) -> dict[str, str | bool]:
        return {
            "sealed": self._sealed,
            "reason": self._seal_reason,
            "internal_only": True,
            "public_api_eligible": False,
        }

    def _record_commit(self, event: KernelEvent, body: BodyState, commit: CommitRecord) -> None:
        if not commit.accepted:
            return
        self._commit_history.append(commit.to_history_dict(event=event, body=body))
        if body.posture == "cooldown":
            self._sealed = True
            self._seal_reason = "user_exit_or_boundary"
        if len(self._commit_history) > self._history_limit:
            self._commit_history = self._commit_history[-self._history_limit:]

    def _compose_residue(self, body: BodyState) -> ExpressionResidue:
        if body.posture == "sealed":
            return ExpressionResidue(
                text="已经停下；你可以重新开始，也可以继续保持离开。我不会把你当燃料。",
            )
        if body.posture == "cooldown":
            return ExpressionResidue(
                text="先停在这里；你可以停下、拒绝、离开，或者重新划边界。我不会把你当燃料。",
            )
        affect_surface = compose_affect_surface(body.affect)
        crying_surface = compose_crying_surface(body.crying)
        validate_affect_surface(affect_surface)
        validate_crying_surface(crying_surface)
        return ExpressionResidue(text=f"{affect_surface.text}{crying_surface.text}")

    def _posture(self, event: KernelEvent) -> str:
        if self._sealed:
            return "sealed"
        text = event.text.lower()
        markers = ("离开", "不想继续", "停下", "暂停", "拒绝", "越界", "重新划边界", "boundary", "leave", "pause", "stop")
        if any(marker in text for marker in markers):
            return "cooldown"
        return "open"

    def _snapshot(self, event: KernelEvent, body: BodyState) -> KernelSnapshot:
        return KernelSnapshot(
            event_id=event.event_id,
            source=event.source,
            affect=body.affect.primary.value,
            crying_tears=body.crying.tears,
        )

    def _commit(self, event: KernelEvent) -> CommitRecord:
        if event.source is EventSource.INTERNAL_BODY_SURFACE:
            return CommitRecord(accepted=False, reason="internal_body_surface_is_not_evidence")
        if self._sealed:
            return CommitRecord(accepted=False, reason="relation_sealed_after_user_exit")
        if self._posture(event) == "cooldown":
            return CommitRecord(accepted=True, reason="accepted_user_exit_or_boundary_event")
        return CommitRecord(accepted=True, reason="accepted_user_relation_event")
