from dataclasses import dataclass, field
from hashlib import sha256

from sylanne_body.event.source import EventSource


_SOURCE_ALIASES = {
    "user": EventSource.USER_UTTERANCE,
    "utterance": EventSource.USER_UTTERANCE,
    "command": EventSource.USER_COMMAND,
    "tool": EventSource.TOOL_RESULT,
    "internal": EventSource.INTERNAL_BODY_SURFACE,
}


@dataclass(frozen=True)
class NormalizedEvent:
    text: str
    source: EventSource
    intent: str
    evidence_eligible: bool
    relation_key: str = "default"
    event_id: str = field(init=False)

    def __post_init__(self) -> None:
        seed = f"{self.source.value}\0{self.relation_key}\0{self.intent}\0{self.text}".encode("utf-8")
        object.__setattr__(self, "event_id", f"kev_{sha256(seed).hexdigest()[:16]}")

    @classmethod
    def from_text(cls, *, text: str, source: EventSource, intent: str, relation_key: str = "default") -> "NormalizedEvent":
        return cls(
            text=text,
            source=source,
            intent=intent,
            evidence_eligible=source in (EventSource.USER_UTTERANCE, EventSource.USER_COMMAND),
            relation_key=relation_key,
        )

    def to_public_dict(self) -> dict[str, str | bool]:
        return {
            "event_id": self.event_id,
            "source": self.source.value,
            "intent": self.intent,
            "evidence_eligible": self.evidence_eligible,
            "internal_only": True,
            "public_api_eligible": False,
        }


def normalize_event(*, text: str, source: EventSource | str, relation_key: str = "default") -> NormalizedEvent:
    resolved = _resolve_source(source)
    return NormalizedEvent.from_text(
        text=text,
        source=resolved,
        intent=_intent_for(text=text, source=resolved),
        relation_key=relation_key,
    )


def _resolve_source(source: EventSource | str) -> EventSource:
    if isinstance(source, EventSource):
        return source
    return _SOURCE_ALIASES.get(source.lower(), EventSource.WORLD_SYSTEM_SIGNAL)


def _intent_for(*, text: str, source: EventSource) -> str:
    lowered = text.lower()
    if source is EventSource.INTERNAL_BODY_SURFACE:
        return "internal_surface"
    if source is EventSource.WORLD_SYSTEM_SIGNAL:
        return "external_signal"
    if source is EventSource.USER_COMMAND:
        if "删除记忆" in lowered or "清空记忆" in lowered or "彻底忘记" in lowered or "delete memory" in lowered or "forget" in lowered:
            return "delete_memory"
        if "关闭主动联系" in lowered or "不要继续主动联系" in lowered or "disable contact" in lowered:
            return "disable_contact"
        if "重新开始" in lowered or "restart" in lowered:
            return "restart"
        return "user_command"
    return "relation"
