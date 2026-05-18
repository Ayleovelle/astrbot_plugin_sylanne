from dataclasses import dataclass

from sylanne_body.event.normalize import NormalizedEvent


@dataclass(frozen=True)
class BloodTrace:
    event_id: str
    source: str
    intent: str
    relation_epoch: int
    accepted: bool
    reason: str
    internal_only: bool = True
    public_api_eligible: bool = False

    def to_dict(self) -> dict[str, str | int | bool]:
        return {
            "event_id": self.event_id,
            "source": self.source,
            "intent": self.intent,
            "relation_epoch": self.relation_epoch,
            "accepted": self.accepted,
            "reason": self.reason,
            "internal_only": self.internal_only,
            "public_api_eligible": self.public_api_eligible,
        }


class MemoryBlood:
    def __init__(self, *, limit: int = 24) -> None:
        self._limit = limit
        self._traces: list[BloodTrace] = []

    def absorb(self, event: NormalizedEvent, *, relation_epoch: int) -> BloodTrace:
        if not event.evidence_eligible:
            return BloodTrace(
                event_id=event.event_id,
                source=event.source.value,
                intent=event.intent,
                relation_epoch=relation_epoch,
                accepted=False,
                reason="event_source_not_memory_evidence",
            )
        trace = BloodTrace(
            event_id=event.event_id,
            source=event.source.value,
            intent=event.intent,
            relation_epoch=relation_epoch,
            accepted=True,
            reason="accepted_irreversible_memory_trace",
        )
        self._traces.append(trace)
        if len(self._traces) > self._limit:
            self._traces = self._traces[-self._limit:]
        return trace

    def clear_for_epoch(self, *, relation_epoch: int) -> None:
        self._traces = [trace for trace in self._traces if trace.relation_epoch >= relation_epoch]

    def export_traces(self) -> list[dict[str, str | int | bool]]:
        return [trace.to_dict() for trace in self._traces]
