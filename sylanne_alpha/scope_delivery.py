"""Fail-closed, scope-bound delivery for one reactive assistant turn.

The raw AstrBot event is deliberately accepted only by :meth:`deliver` and is
never retained on the coordinator.  A normal ``event.send`` return is treated
as local transport acceptance/completion, not as a remote receipt.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from .scope_contracts import TurnDeliveryLease
from .scope_runtime import RequestRuntimeView


class DeliveryState(str, Enum):
    """The complete state machine for one delivery attempt."""

    PLANNED = "planned"
    CLAIMED = "claimed"
    SENDING = "sending"
    SENT_CONFIRMED = "sent_confirmed"
    PARTIAL = "partial"
    FAILED_BEFORE_SEND = "failed_before_send"
    OUTCOME_UNKNOWN = "outcome_unknown"


_TERMINAL_STATES = frozenset(
    {
        DeliveryState.SENT_CONFIRMED,
        DeliveryState.PARTIAL,
        DeliveryState.FAILED_BEFORE_SEND,
        DeliveryState.OUTCOME_UNKNOWN,
    }
)


class DeliveryStateError(RuntimeError):
    """Raised when a caller attempts an illegal state transition or retry."""


class DeliveryLeaseRejected(ValueError):
    """Raised when a claim is not sealed to the exact live request view."""


class _AstrBotSendEvent(Protocol):
    def plain_result(self, text: str) -> object: ...

    async def send(self, result: object) -> object: ...


@dataclass(slots=True)
class ProcessLocalDeliveryTurn:
    """Minimal message-part state that must never cross a persistence boundary."""

    planned_parts: tuple[str, ...] = field(repr=False)
    _confirmed_parts: list[str] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        if (
            type(self.planned_parts) is not tuple
            or not self.planned_parts
            or any(type(part) is not str or not part for part in self.planned_parts)
        ):
            raise ValueError("planned_parts must be a non-empty tuple of text")

    @property
    def confirmed_parts(self) -> tuple[str, ...]:
        """Return process-local text confirmed by normal ``event.send`` returns."""

        return tuple(self._confirmed_parts)

    def _mark_confirmed(self, text: str) -> None:
        self._confirmed_parts.append(text)


@dataclass(frozen=True, slots=True)
class DeliveryClaim:
    """Process-local claim sealed to one issued request view and fence."""

    lease: TurnDeliveryLease
    fence: int
    view: RequestRuntimeView = field(repr=False, compare=False)
    event: _AstrBotSendEvent = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class DeliverySnapshot:
    """Persistence-safe progress metadata with no event or transport address."""

    state: DeliveryState
    planned_parts: int
    confirmed_parts: int


class ReactiveDeliveryCoordinator:
    """Coordinate exactly one fail-closed segmented delivery attempt."""

    __slots__ = (
        "_active_claim",
        "_fence",
        "_is_issued_request_view",
        "_state",
        "_transition_history",
        "_turn",
    )

    def __init__(
        self,
        turn: ProcessLocalDeliveryTurn,
        *,
        is_issued_request_view: Callable[[object], bool],
    ) -> None:
        if type(turn) is not ProcessLocalDeliveryTurn:
            raise TypeError("turn must be an exact ProcessLocalDeliveryTurn")
        if turn.confirmed_parts:
            raise DeliveryStateError("turn must be a fresh planned delivery")
        if not callable(is_issued_request_view):
            raise TypeError("is_issued_request_view must be callable")

        self._turn = turn
        self._is_issued_request_view = is_issued_request_view
        self._state = DeliveryState.PLANNED
        self._transition_history = [DeliveryState.PLANNED]
        self._fence = 0
        self._active_claim: DeliveryClaim | None = None

    @property
    def turn(self) -> ProcessLocalDeliveryTurn:
        return self._turn

    @property
    def state(self) -> DeliveryState:
        return self._state

    @property
    def snapshot(self) -> DeliverySnapshot:
        return DeliverySnapshot(
            state=self._state,
            planned_parts=len(self._turn.planned_parts),
            confirmed_parts=len(self._turn.confirmed_parts),
        )

    @property
    def transition_history(self) -> tuple[DeliveryState, ...]:
        return tuple(self._transition_history)

    def claim(
        self,
        *,
        view: RequestRuntimeView,
        lease: TurnDeliveryLease,
        event: _AstrBotSendEvent,
    ) -> DeliveryClaim:
        """Claim the planned turn using an exact registry-issued request seal."""

        if self._state is not DeliveryState.PLANNED:
            raise DeliveryStateError("only a planned delivery can be claimed")
        if (
            type(view) is not RequestRuntimeView
            or type(lease) is not TurnDeliveryLease
            or not self._is_send_event(event)
            or not self._view_is_current(view)
            or not self._lease_matches_view(lease, view)
        ):
            raise DeliveryLeaseRejected("delivery claim is stale or scope-mismatched")

        self._fence += 1
        claim = DeliveryClaim(lease=lease, fence=self._fence, view=view, event=event)
        self._active_claim = claim
        self._transition(DeliveryState.CLAIMED)
        return claim

    def invalidate_claim(self) -> None:
        """Advance the local fence so an already queued claim cannot send."""

        self._fence += 1

    async def deliver(
        self,
        *,
        event: _AstrBotSendEvent,
        claim: DeliveryClaim,
        before_send: Callable[[int, str], Awaitable[bool] | bool] | None = None,
    ) -> DeliverySnapshot:
        """Send each segment once, validating the complete seal before each call.

        Gate and result-building failures are known-before-send outcomes.  Once
        ``event.send`` starts, cancellation or failure leaves the outcome unknown.
        Exceptions are propagated, and terminal attempts cannot be called again.
        """

        if self._state is not DeliveryState.CLAIMED:
            raise DeliveryStateError("delivery is not in the claimed state")
        if type(claim) is not DeliveryClaim or event is not claim.event:
            raise DeliveryLeaseRejected("delivery event does not match the claimed original event")
        self._transition(DeliveryState.SENDING)

        for index, text in enumerate(self._turn.planned_parts):
            if not self._claim_is_current(claim):
                self._finish_without_send()
                return self.snapshot

            if before_send is not None:
                try:
                    permitted = before_send(index, text)
                    if inspect.isawaitable(permitted):
                        permitted = await permitted
                except asyncio.CancelledError:
                    self._finish_without_send()
                    raise
                except Exception:
                    self._finish_without_send()
                    raise
                if permitted is not True:
                    self._finish_without_send()
                    return self.snapshot
                if not self._claim_is_current(claim):
                    self._finish_without_send()
                    return self.snapshot

            try:
                result = event.plain_result(text)
            except asyncio.CancelledError:
                self._finish_without_send()
                raise
            except Exception:
                self._finish_without_send()
                raise

            try:
                await event.send(result)
            except asyncio.CancelledError:
                self._transition(DeliveryState.OUTCOME_UNKNOWN)
                raise
            except Exception:
                self._transition(DeliveryState.OUTCOME_UNKNOWN)
                raise

            if not self._claim_is_current(claim):
                self._transition(DeliveryState.OUTCOME_UNKNOWN)
                return self.snapshot
            self._turn._mark_confirmed(text)

        self._transition(DeliveryState.SENT_CONFIRMED)
        return self.snapshot

    def _view_is_current(self, view: RequestRuntimeView) -> bool:
        try:
            return self._is_issued_request_view(view) is True
        except Exception:
            return False

    @staticmethod
    def _is_send_event(candidate: object) -> bool:
        return callable(getattr(candidate, "plain_result", None)) and callable(
            getattr(candidate, "send", None)
        )

    @staticmethod
    def _lease_matches_view(
        lease: TurnDeliveryLease,
        view: RequestRuntimeView,
    ) -> bool:
        scope = view.resolved.scope
        turn_generation = view.resolved.turn_generation
        return (
            scope is not None
            and turn_generation is not None
            and lease.transport_session_token == scope.session_ref.token
            and lease.resolved_scope_token == scope.storage_token
            and lease.bot_binding_generation == scope.bot_ref.generation
            and lease.persona_lifecycle_generation == scope.persona_ref.lifecycle_generation
            and lease.session_generation == scope.session_ref.generation
            and lease.scope_generation == scope.scope_generation
            and lease.turn_generation == turn_generation
        )

    def _claim_is_current(self, claim: DeliveryClaim) -> bool:
        active = self._active_claim
        return (
            type(claim) is DeliveryClaim
            and claim is active
            and claim.fence == self._fence
            and type(claim.lease) is TurnDeliveryLease
            and type(claim.view) is RequestRuntimeView
            and self._view_is_current(claim.view)
            and self._lease_matches_view(claim.lease, claim.view)
        )

    def _finish_without_send(self) -> None:
        if self._turn.confirmed_parts:
            self._transition(DeliveryState.PARTIAL)
        else:
            self._transition(DeliveryState.FAILED_BEFORE_SEND)

    def _transition(self, target: DeliveryState) -> None:
        allowed = {
            DeliveryState.PLANNED: frozenset({DeliveryState.CLAIMED}),
            DeliveryState.CLAIMED: frozenset({DeliveryState.SENDING}),
            DeliveryState.SENDING: _TERMINAL_STATES,
        }
        if target not in allowed.get(self._state, frozenset()):
            raise DeliveryStateError(
                f"illegal delivery transition: {self._state.value} -> {target.value}"
            )
        self._state = target
        self._transition_history.append(target)


__all__ = [
    "DeliveryClaim",
    "DeliveryLeaseRejected",
    "DeliverySnapshot",
    "DeliveryState",
    "DeliveryStateError",
    "ProcessLocalDeliveryTurn",
    "ReactiveDeliveryCoordinator",
]
