"""Per-turn delivery ledger for realtime segmented replies.

The LLM completion is only an intent.  Conversation history becomes authoritative
after transport confirms which bubbles were actually sent.  This module keeps that
small boundary explicit and independent from AstrBot's provider/history objects.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SegmentedDeliveryTurn:
    """Mutable delivery receipt owned by one inbound event/assistant turn."""

    session_key: str
    input_epoch: int
    planned_parts: tuple[str, ...]
    origin: str = ""
    dispatch_parts: tuple[dict[str, Any], ...] = ()
    cleaned_text: str = ""
    expression_drive: float = 0.0
    delivered_parts: list[str] = field(default_factory=list)
    status: str = "planned"
    history_settled: bool = False
    observed: bool = False
    task: asyncio.Task[Any] | None = field(default=None, repr=False)
    run_context: Any | None = field(default=None, repr=False)
    response: Any | None = field(default=None, repr=False)
    _interrupted: asyncio.Event = field(default_factory=asyncio.Event, repr=False)

    def interrupt(self) -> None:
        """Request a cooperative stop without cancelling an in-flight send call."""

        self._interrupted.set()

    def should_stop(self, current_input_epoch: int) -> bool:
        return self._interrupted.is_set() or current_input_epoch > self.input_epoch

    async def wait_delay(self, seconds: float) -> bool:
        """Wait for one typing delay; return False when interrupted first."""

        if self._interrupted.is_set():
            return False
        if seconds <= 0:
            return True
        try:
            await asyncio.wait_for(self._interrupted.wait(), timeout=seconds)
        except TimeoutError:
            return True
        return False

    def mark_delivered(self, text: str) -> None:
        if text:
            self.delivered_parts.append(text)

    @property
    def transcript(self) -> str:
        """Canonical assistant text: exactly the successful visible bubbles."""

        return "\n".join(part for part in self.delivered_parts if part)


__all__ = ["SegmentedDeliveryTurn"]
