from dataclasses import dataclass

from sylanne_body.event.normalize import NormalizedEvent
from sylanne_body.event.source import EventSource


@dataclass(frozen=True)
class NervePulse:
    event_id: str
    source: str
    intent: str
    sequence: int
    relation_epoch: int
    evidence_eligible: bool
    internal_only: bool = True
    public_api_eligible: bool = False

    def to_dict(self) -> dict[str, str | int | bool]:
        return {
            "event_id": self.event_id,
            "source": self.source,
            "intent": self.intent,
            "sequence": self.sequence,
            "relation_epoch": self.relation_epoch,
            "evidence_eligible": self.evidence_eligible,
            "internal_only": self.internal_only,
            "public_api_eligible": self.public_api_eligible,
        }


class NerveTimeline:
    def __init__(self, *, limit: int = 48) -> None:
        self._limit = limit
        self._sequence = 0
        self._pulses: list[NervePulse] = []
        self._sealed = False
        self._seal_reason = ""

    def observe(self, event: NormalizedEvent, *, relation_epoch: int) -> NervePulse:
        return self._append(
            event_id=event.event_id,
            source=event.source.value,
            intent=event.intent,
            relation_epoch=relation_epoch,
            evidence_eligible=event.evidence_eligible,
        )

    def observe_withdrawal(self, event: NormalizedEvent, *, relation_epoch: int) -> NervePulse:
        return self._append(
            event_id=event.event_id,
            source=EventSource.USER_COMMAND.value,
            intent="withdrawal",
            relation_epoch=relation_epoch,
            evidence_eligible=False,
        )

    def mark_sealed(self, *, reason: str, relation_epoch: int) -> NervePulse:
        self._sealed = True
        self._seal_reason = reason
        return self._append(
            event_id=f"seal_{relation_epoch}_{self._sequence + 1}",
            source=EventSource.USER_COMMAND.value,
            intent="sealed",
            relation_epoch=relation_epoch,
            evidence_eligible=False,
        )

    def export_pulses(self) -> list[dict[str, str | int | bool]]:
        return [pulse.to_dict() for pulse in self._pulses]

    def export_state(self) -> dict[str, str | int | bool]:
        return {
            "sealed": self._sealed,
            "seal_reason": self._seal_reason,
            "pulse_count": len(self._pulses),
            "latest_sequence": self._sequence,
            "internal_only": True,
            "public_api_eligible": False,
        }

    def _append(
        self,
        *,
        event_id: str,
        source: str,
        intent: str,
        relation_epoch: int,
        evidence_eligible: bool,
    ) -> NervePulse:
        self._sequence += 1
        pulse = NervePulse(
            event_id=event_id,
            source=source,
            intent=intent,
            sequence=self._sequence,
            relation_epoch=relation_epoch,
            evidence_eligible=evidence_eligible,
        )
        self._pulses.append(pulse)
        if len(self._pulses) > self._limit:
            self._pulses = self._pulses[-self._limit:]
        return pulse
