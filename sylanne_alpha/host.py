from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .kernel import AlphaKernelEvent
from .runtime import AlphaRuntime


@dataclass(slots=True)
class SylanneAlphaHostEvent:
    text: str = ""
    confidence: float = 0.0
    flags: list[str] = field(default_factory=list)
    now: float = 0.0
    values: dict[str, float] = field(default_factory=dict)
    event_time: dict[str, Any] = field(default_factory=dict)

    def to_kernel_event(self) -> AlphaKernelEvent:
        return AlphaKernelEvent(
            text=self.text,
            values=dict(self.values),
            confidence=self.confidence,
            flags=list(self.flags),
            now=self.now,
            event_time=dict(self.event_time),
        )


@dataclass(slots=True)
class SylanneAlphaHost:
    root: Path | str
    session_key: str = "default"
    legacy: dict[str, Any] | None = None
    runtime: AlphaRuntime = field(init=False)
    kernel: Any = field(init=False)

    def __post_init__(self) -> None:
        self.runtime = AlphaRuntime(Path(self.root))
        self.kernel = self.runtime.load(self.session_key, legacy=self.legacy)

    def on_request(self, event: SylanneAlphaHostEvent | dict[str, Any] | None = None, assessment: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._tick(event, phase="request", assessment=assessment)

    def on_response(self, event: SylanneAlphaHostEvent | dict[str, Any] | None = None) -> dict[str, Any]:
        return self._tick(event, phase="response")

    def on_chat(self, event: SylanneAlphaHostEvent | dict[str, Any] | None = None) -> dict[str, Any]:
        request_surface = self._tick(event, phase="chat_request")
        reply_text = self._reply_text(request_surface)
        response_event = self._event(event)
        response_surface = self._tick(
            SylanneAlphaHostEvent(
                text=reply_text,
                confidence=0.7,
                flags=["chat_response", "safe"],
                now=response_event.now,
                values=dict(response_event.values),
                event_time=dict(response_event.event_time),
            ),
            phase="response",
        )
        return {
            "schema_version": "sylanne.alpha.chat.v1",
            "session_key": self.session_key,
            "ok": True,
            "reply_text": reply_text,
            "action": response_surface["decision"]["action"],
            "request": request_surface,
            "surface": response_surface,
        }

    def on_proactive_check(self, event: SylanneAlphaHostEvent | dict[str, Any] | None = None) -> dict[str, Any]:
        surface = self._tick(event, phase="proactive")
        if surface["host_payload"].get("should_send"):
            self.kernel.body.immunity.interruption_budget = max(0.0, self.kernel.body.immunity.interruption_budget - 0.2)
            self.kernel.body.immunity.cooldown = max(self.kernel.body.immunity.cooldown, 0.35)
            self.runtime.save(self.kernel)
            return self.kernel.surface()
        return surface

    def diagnostics(self) -> dict[str, Any]:
        return self.kernel.surface()

    def snapshot(self) -> dict[str, Any]:
        return self.kernel.snapshot()

    def _tick(self, event: SylanneAlphaHostEvent | dict[str, Any] | None, *, phase: str, assessment: dict[str, Any] | None = None) -> dict[str, Any]:
        host_event = self._event(event)
        flags = list(dict.fromkeys([phase, *host_event.flags]))
        surface = self.kernel.tick(
            AlphaKernelEvent(
                text=host_event.text,
                values=dict(host_event.values),
                confidence=host_event.confidence,
                flags=flags,
                now=host_event.now,
                event_time=dict(host_event.event_time),
            ),
            assessment=assessment,
        )["surface"]
        self.runtime.save(self.kernel)
        return surface

    def _reply_text(self, surface: dict[str, Any]) -> str:
        decision = surface["decision"]
        guard = surface["guard"]
        if not guard["allowed"]:
            return "我先退一步。"
        if decision["action"] == "repair":
            return "刚才那一下我会放轻一点。"
        if decision["action"] == "withdraw":
            return "我听到了，先安静一点。"
        if decision["action"] in {"express", "reach_out", "explore"}:
            return "我在听，你继续说。"
        return "嗯，我记下了。"

    def _event(self, event: SylanneAlphaHostEvent | dict[str, Any] | None) -> SylanneAlphaHostEvent:
        if isinstance(event, SylanneAlphaHostEvent):
            return event
        payload = event or {}
        return SylanneAlphaHostEvent(
            text=str(payload.get("text") or ""),
            confidence=float(payload.get("confidence") or 0.0),
            flags=list(payload.get("flags") or []),
            now=float(payload.get("now") or 0.0),
            values=dict(payload.get("values") or {}),
            event_time=dict(payload.get("event_time") if isinstance(payload.get("event_time"), dict) else {}),
        )
