from dataclasses import dataclass

from sylanne_body.event.normalize import NormalizedEvent


_EXIT_MARKERS = ("离开", "停下", "暂停", "不要继续", "拒绝", "越界", "leave", "stop", "pause")


@dataclass(frozen=True)
class ImmunityDecision:
    posture: str
    action: str
    reason: str
    persistence_allowed: bool
    proactive_contact_allowed: bool
    internal_only: bool = True
    public_api_eligible: bool = False


class BoundaryImmunity:
    def evaluate(self, event: NormalizedEvent) -> ImmunityDecision:
        if event.intent == "delete_memory":
            return ImmunityDecision(
                posture="cooldown",
                action="delete_memory",
                reason="delete_memory_command",
                persistence_allowed=False,
                proactive_contact_allowed=False,
            )
        if event.intent == "disable_contact":
            return ImmunityDecision(
                posture="cooldown",
                action="disable_contact",
                reason="disable_contact_command",
                persistence_allowed=False,
                proactive_contact_allowed=False,
            )
        lowered = event.text.lower()
        if any(marker in lowered for marker in _EXIT_MARKERS):
            return ImmunityDecision(
                posture="cooldown",
                action="preserve_exit",
                reason="user_exit_or_boundary",
                persistence_allowed=False,
                proactive_contact_allowed=False,
            )
        return ImmunityDecision(
            posture="open",
            action="continue",
            reason="open_relation_event",
            persistence_allowed=event.evidence_eligible,
            proactive_contact_allowed=False,
        )
