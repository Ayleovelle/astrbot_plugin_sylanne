from dataclasses import dataclass

from sylanne_body.event.normalize import normalize_event
from sylanne_body.law.immunity import BoundaryImmunity
from sylanne_body.memory.blood import MemoryBlood
from sylanne_body.nerve.timeline import NerveTimeline
from sylanne_body.speech.gate import ExpressionGate


@dataclass(frozen=True)
class AdapterResult:
    reply_text: str
    posture: str
    action: str
    relation_epoch: int
    persistence_allowed: bool
    proactive_contact_allowed: bool
    internal_only: bool = True
    public_api_eligible: bool = False

    def to_public_dict(self) -> dict[str, str | int | bool]:
        return {
            "posture": self.posture,
            "action": self.action,
            "relation_epoch": self.relation_epoch,
            "persistence_allowed": self.persistence_allowed,
            "proactive_contact_allowed": self.proactive_contact_allowed,
            "internal_only": self.internal_only,
            "public_api_eligible": self.public_api_eligible,
        }


class KernelAdapter:
    def __init__(self) -> None:
        self._relation_epoch = 0
        self._blood = MemoryBlood()
        self._timeline = NerveTimeline()
        self._immunity = BoundaryImmunity()
        self._gate = ExpressionGate()

    def receive(self, *, text: str, source: str) -> AdapterResult:
        event = normalize_event(text=text, source=source)
        decision = self._immunity.evaluate(event)
        if decision.action == "delete_memory":
            self._relation_epoch += 1
            self._blood.clear_for_epoch(relation_epoch=self._relation_epoch)
        self._timeline.observe(event, relation_epoch=self._relation_epoch)
        if decision.persistence_allowed:
            self._blood.absorb(event, relation_epoch=self._relation_epoch)
        if decision.posture == "cooldown":
            self._timeline.mark_sealed(reason=decision.reason, relation_epoch=self._relation_epoch)
        surface = self._gate.compose(decision)
        return AdapterResult(
            reply_text=surface.text,
            posture=decision.posture,
            action=decision.action,
            relation_epoch=self._relation_epoch,
            persistence_allowed=decision.persistence_allowed,
            proactive_contact_allowed=decision.proactive_contact_allowed,
        )

    def export_state(self) -> dict[str, str | int | bool]:
        timeline_state = self._timeline.export_state()
        return {
            "relation_epoch": self._relation_epoch,
            "memory_trace_count": len(self._blood.export_traces()),
            "nerve_pulse_count": timeline_state["pulse_count"],
            "sealed": timeline_state["sealed"],
            "internal_only": True,
            "public_api_eligible": False,
            "allow_public_export": False,
            "allow_debug_snapshot": False,
            "allow_inference_as_evidence": False,
        }
