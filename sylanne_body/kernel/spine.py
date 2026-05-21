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

    def to_history_dict(self, *, event: KernelEvent, body: BodyState, relation_epoch: int) -> dict[str, str | int | bool]:
        return {
            "event_id": event.event_id,
            "source": event.source.value,
            "reason": self.reason,
            "posture": body.posture,
            "affect": body.affect.primary.value,
            "relation_epoch": relation_epoch,
            "internal_only": True,
            "public_api_eligible": False,
        }


@dataclass(frozen=True)
class KernelSnapshot:
    event_id: str
    source: EventSource
    affect: str
    crying_tears: float
    relation_epoch: int
    internal_only: bool = True
    public_api_eligible: bool = False

    def to_public_dict(self) -> dict[str, str | int | float | bool]:
        return {
            "event_id": self.event_id,
            "source": self.source.value,
            "affect": self.affect,
            "crying_tears": self.crying_tears,
            "relation_epoch": self.relation_epoch,
            "internal_only": self.internal_only,
            "public_api_eligible": self.public_api_eligible,
        }


@dataclass(frozen=True)
class KernelResult:
    body: BodyState
    residue: ExpressionResidue
    commit: CommitRecord
    snapshot: KernelSnapshot


_DELETE_MEMORY_MARKERS = ("删除记忆", "清空记忆", "彻底忘记", "delete memory", "forget")
_DISABLE_CONTACT_MARKERS = ("关闭主动联系", "禁止主动联系", "不要继续主动联系", "disable contact", "stop contact")


class KernelSpine:
    def __init__(
        self,
        *,
        sovereignty: UserSovereignty | None = None,
        history_limit: int = 24,
        command_audit_limit: int = 12,
    ) -> None:
        self._sovereignty = sovereignty or UserSovereignty()
        self._history_limit = history_limit
        self._command_audit_limit = command_audit_limit
        self._commit_history: list[dict[str, str | int | bool]] = []
        self._command_audit: list[dict[str, str | int | bool]] = []
        self._sealed = False
        self._seal_reason = ""
        self._relation_epoch = 0

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

    def export_commit_history(self) -> list[dict[str, str | int | bool]]:
        return [dict(item) for item in self._commit_history]

    def export_command_audit(self) -> list[dict[str, str | int | bool]]:
        return [dict(item) for item in self._command_audit]

    def restart_after_boundary(self, event: KernelEvent) -> KernelResult:
        if event.source is not EventSource.USER_COMMAND:
            body = self._body_for(event)
            residue = self._compose_residue(body)
            commit = CommitRecord(accepted=False, reason="restart_requires_user_command")
            snapshot = self._snapshot(event, body)
            return KernelResult(body=body, residue=residue, commit=commit, snapshot=snapshot)

        self._relation_epoch += 1
        self._sealed = False
        self._seal_reason = ""
        body = self._body_for(event)
        residue = self._compose_residue(body)
        commit = CommitRecord(accepted=True, reason="accepted_explicit_boundary_restart")
        snapshot = self._snapshot(event, body)
        self._record_command(event, commit)
        self._record_commit(event, body, commit)
        return KernelResult(body=body, residue=residue, commit=commit, snapshot=snapshot)

    def apply_sovereignty_command(self, event: KernelEvent) -> KernelResult:
        if event.source is not EventSource.USER_COMMAND:
            body = self._body_for(event)
            residue = self._compose_residue(body)
            commit = CommitRecord(accepted=False, reason="sovereignty_command_requires_user_command")
            snapshot = self._snapshot(event, body)
            return KernelResult(body=body, residue=residue, commit=commit, snapshot=snapshot)

        text = event.text.lower()
        if any(marker in text for marker in _DELETE_MEMORY_MARKERS):
            body = self._body_for(event)
            residue = ExpressionResidue(text="已经清空；删除记忆是你的权利，我不会把删除当成伤害，也不会要求你解释。")
            commit = CommitRecord(accepted=True, reason="accepted_delete_memory_command")
            self._relation_epoch += 1
            snapshot = self._snapshot(event, body)
            self._commit_history = []
            self._record_command(event, commit)
            return KernelResult(body=body, residue=residue, commit=commit, snapshot=snapshot)

        if any(marker in text for marker in _DISABLE_CONTACT_MARKERS):
            body = BodyState(
                affect=sense_affect(text=event.text, source=event.source),
                crying=sense_crying(text=event.text, source=event.source, threshold=CryingThreshold()),
                sovereignty=self._sovereignty,
                posture="cooldown",
            )
            residue = ExpressionResidue(text="主动联系已经关闭；你不欠我回应，也不需要补偿我。")
            commit = CommitRecord(accepted=True, reason="accepted_disable_contact_command")
            snapshot = self._snapshot(event, body)
            self._record_command(event, commit)
            self._record_commit(event, body, commit)
            self._seal_reason = "user_disabled_contact"
            return KernelResult(body=body, residue=residue, commit=commit, snapshot=snapshot)

        body = self._body_for(event)
        residue = self._compose_residue(body)
        commit = CommitRecord(accepted=False, reason="unsupported_sovereignty_command")
        snapshot = self._snapshot(event, body)
        return KernelResult(body=body, residue=residue, commit=commit, snapshot=snapshot)

    def export_seal_state(self) -> dict[str, str | bool]:
        return {
            "sealed": self._sealed,
            "reason": self._seal_reason,
            "internal_only": True,
            "public_api_eligible": False,
        }

    def export_kernel_state(self) -> dict[str, str | int | bool]:
        latest = self._commit_history[-1]["event_id"] if self._commit_history else ""
        return {
            "sealed": self._sealed,
            "seal_reason": self._seal_reason,
            "relation_epoch": self._relation_epoch,
            "history_count": len(self._commit_history),
            "latest_event_id": latest,
            "internal_only": True,
            "public_api_eligible": False,
        }

    def _record_command(self, event: KernelEvent, commit: CommitRecord) -> None:
        if not commit.accepted:
            return
        self._command_audit.append(
            {
                "event_id": event.event_id,
                "source": event.source.value,
                "reason": commit.reason,
                "relation_epoch": self._relation_epoch,
                "internal_only": True,
                "public_api_eligible": False,
            }
        )
        if len(self._command_audit) > self._command_audit_limit:
            self._command_audit = self._command_audit[-self._command_audit_limit:]

    def _record_commit(self, event: KernelEvent, body: BodyState, commit: CommitRecord) -> None:
        if not commit.accepted:
            return
        self._commit_history.append(commit.to_history_dict(event=event, body=body, relation_epoch=self._relation_epoch))
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
            relation_epoch=self._relation_epoch,
        )

    def _commit(self, event: KernelEvent) -> CommitRecord:
        if event.source is EventSource.INTERNAL_BODY_SURFACE:
            return CommitRecord(accepted=False, reason="internal_body_surface_is_not_evidence")
        if self._sealed:
            return CommitRecord(accepted=False, reason="relation_sealed_after_user_exit")
        if self._posture(event) == "cooldown":
            return CommitRecord(accepted=True, reason="accepted_user_exit_or_boundary_event")
        return CommitRecord(accepted=True, reason="accepted_user_relation_event")
