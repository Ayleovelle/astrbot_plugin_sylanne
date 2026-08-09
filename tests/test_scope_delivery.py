from __future__ import annotations

import asyncio
from dataclasses import asdict, fields, replace
from typing import Any, Callable

import pytest

from sylanne_alpha.scope_contracts import ResolvedScope, TurnDeliveryLease
from sylanne_alpha.scope_delivery import (
    DeliveryClaim,
    DeliveryLeaseRejected,
    DeliveryState,
    DeliveryStateError,
    ProcessLocalDeliveryTurn,
    ReactiveDeliveryCoordinator,
)
from sylanne_alpha.scope_identity import PersonaSource
from sylanne_alpha.scope_runtime import RequestRuntimeView, ScopeRuntimeRegistry
from tests.scope_fixtures import scopes


def _issued_view(
    scopes: Any,
) -> tuple[ScopeRuntimeRegistry, RequestRuntimeView]:
    registry = ScopeRuntimeRegistry.for_test()
    scope = scopes.bot_a_persona_a
    view = registry.issue_request_view(
        ResolvedScope(
            scope=scope,
            persona_source=PersonaSource(
                persona_id="scope-delivery-fixture",
                prompt="quiet",
                begin_dialogs=(),
                tools=None,
                skills=None,
                resolution_source="test",
            ),
            identity_quality="event_self_id",
            resolution_source="test",
            resolved_at_ms=1,
            private_scope_enabled=True,
            disabled_reason=None,
            turn_generation=7,
        ),
        subject=None,
        relation_runtime=None,
    )
    return registry, view


def _lease(view: RequestRuntimeView) -> TurnDeliveryLease:
    scope = view.resolved.scope
    assert scope is not None
    turn_generation = view.resolved.turn_generation
    assert turn_generation is not None
    return TurnDeliveryLease(
        transport_session_token=scope.session_ref.token,
        resolved_scope_token=scope.storage_token,
        bot_binding_generation=scope.bot_ref.generation,
        persona_lifecycle_generation=scope.persona_ref.lifecycle_generation,
        session_generation=scope.session_ref.generation,
        scope_generation=scope.scope_generation,
        turn_generation=turn_generation,
    )


def test_turn_delivery_lease_binds_bot_and_persona_generations(scopes: Any) -> None:
    scope = scopes.bot_a_persona_a
    lease = TurnDeliveryLease(
        transport_session_token=scope.session_ref.token,
        resolved_scope_token=scope.storage_token,
        bot_binding_generation=scope.bot_ref.generation,
        persona_lifecycle_generation=scope.persona_ref.lifecycle_generation,
        session_generation=scope.session_ref.generation,
        scope_generation=scope.scope_generation,
        turn_generation=7,
    )

    assert lease.bot_binding_generation == scope.bot_ref.generation
    assert lease.persona_lifecycle_generation == scope.persona_ref.lifecycle_generation


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("bot_binding_generation", True),
        ("persona_lifecycle_generation", "1"),
    ],
)
def test_turn_delivery_lease_rejects_non_integer_identity_generations(
    scopes: Any,
    field_name: str,
    value: object,
) -> None:
    scope = scopes.bot_a_persona_a
    kwargs: dict[str, object] = {
        "transport_session_token": scope.session_ref.token,
        "resolved_scope_token": scope.storage_token,
        "bot_binding_generation": scope.bot_ref.generation,
        "persona_lifecycle_generation": scope.persona_ref.lifecycle_generation,
        "session_generation": scope.session_ref.generation,
        "scope_generation": scope.scope_generation,
        "turn_generation": 7,
    }
    kwargs[field_name] = value

    with pytest.raises(ValueError, match=field_name):
        TurnDeliveryLease(**kwargs)  # type: ignore[arg-type]


def _coordinator(
    registry: ScopeRuntimeRegistry,
    *,
    parts: tuple[str, ...] = ("first", "second"),
) -> ReactiveDeliveryCoordinator:
    return ReactiveDeliveryCoordinator(
        ProcessLocalDeliveryTurn(planned_parts=parts),
        is_issued_request_view=registry.is_issued_request_view,
    )


class _Event:
    def __init__(
        self,
        *,
        after_send: Callable[[], None] | None = None,
        send_error: BaseException | None = None,
        plain_error_at: int | None = None,
    ) -> None:
        self.after_send = after_send
        self.send_error = send_error
        self.plain_error_at = plain_error_at
        self.plain_calls: list[str] = []
        self.send_calls: list[object] = []

    def plain_result(self, text: str) -> tuple[str, str]:
        self.plain_calls.append(text)
        if self.plain_error_at == len(self.plain_calls):
            raise RuntimeError("plain result failed before send")
        return ("plain", text)

    async def send(self, result: object) -> None:
        self.send_calls.append(result)
        if self.send_error is not None:
            raise self.send_error
        if self.after_send is not None:
            self.after_send()


def test_delivery_uses_only_event_plain_result_and_send_after_exact_claim(
    scopes: Any,
) -> None:
    async def scenario() -> None:
        registry, view = _issued_view(scopes)
        coordinator = _coordinator(registry)

        assert coordinator.state is DeliveryState.PLANNED
        event = _Event()
        claim = coordinator.claim(view=view, lease=_lease(view), event=event)
        assert coordinator.state is DeliveryState.CLAIMED

        snapshot = await coordinator.deliver(event=event, claim=claim)

        assert event.plain_calls == ["first", "second"]
        assert event.send_calls == [("plain", "first"), ("plain", "second")]
        assert snapshot.state is DeliveryState.SENT_CONFIRMED
        assert snapshot.confirmed_parts == 2
        assert coordinator.turn.confirmed_parts == ("first", "second")
        assert coordinator.transition_history == (
            DeliveryState.PLANNED,
            DeliveryState.CLAIMED,
            DeliveryState.SENDING,
            DeliveryState.SENT_CONFIRMED,
        )
        assert not hasattr(coordinator, "event")
        assert not hasattr(coordinator, "_event")

    asyncio.run(scenario())


def test_unissued_view_and_generation_mismatch_cannot_be_claimed(scopes: Any) -> None:
    registry, view = _issued_view(scopes)
    forged = RequestRuntimeView(
        resolved=view.resolved,
        persona_runtime=view.persona_runtime,
        session_runtime=view.session_runtime,
    )
    coordinator = _coordinator(registry)
    event = _Event()

    with pytest.raises(DeliveryLeaseRejected):
        coordinator.claim(view=forged, lease=_lease(forged), event=event)

    stale_lease = replace(
        _lease(view),
        scope_generation=_lease(view).scope_generation + 1,
    )
    with pytest.raises(DeliveryLeaseRejected):
        coordinator.claim(view=view, lease=stale_lease, event=event)

    assert coordinator.state is DeliveryState.PLANNED


@pytest.mark.parametrize(
    "field_name",
    ("bot_binding_generation", "persona_lifecycle_generation"),
)
def test_bot_and_persona_generation_mismatch_cannot_be_claimed(
    scopes: Any,
    field_name: str,
) -> None:
    registry, view = _issued_view(scopes)
    coordinator = _coordinator(registry)
    lease = replace(
        _lease(view),
        **{field_name: getattr(_lease(view), field_name) + 1},
    )

    with pytest.raises(DeliveryLeaseRejected):
        coordinator.claim(view=view, lease=lease, event=_Event())


def test_claim_is_sealed_to_the_original_event_identity(scopes: Any) -> None:
    async def scenario() -> None:
        registry, view = _issued_view(scopes)
        coordinator = _coordinator(registry, parts=("only",))
        original_event = _Event()
        replacement_event = _Event()
        claim = coordinator.claim(
            view=view,
            lease=_lease(view),
            event=original_event,
        )

        with pytest.raises(DeliveryLeaseRejected):
            await coordinator.deliver(event=replacement_event, claim=claim)

        assert original_event.send_calls == []
        assert replacement_event.send_calls == []
        assert coordinator.state is DeliveryState.CLAIMED

    asyncio.run(scenario())


def test_released_and_recreated_view_cannot_revalidate_the_old_claim(
    scopes: Any,
) -> None:
    async def scenario() -> None:
        registry, view = _issued_view(scopes)
        coordinator = _coordinator(registry, parts=("only",))

        def release_and_recreate() -> None:
            assert registry.release_request_view(view) is True
            replacement = registry.issue_request_view(
                view.resolved,
                subject=None,
                relation_runtime=None,
            )
            assert registry.is_issued_request_view(replacement) is True

        event = _Event(after_send=release_and_recreate)
        claim = coordinator.claim(view=view, lease=_lease(view), event=event)
        snapshot = await coordinator.deliver(event=event, claim=claim)

        assert snapshot.state is DeliveryState.OUTCOME_UNKNOWN
        assert snapshot.confirmed_parts == 0
        assert len(event.send_calls) == 1

    asyncio.run(scenario())


def test_concurrent_terminal_delivery_callback_is_rejected_and_never_retried(
    scopes: Any,
) -> None:
    class _BlockingEvent(_Event):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()
            self.release = asyncio.Event()

        async def send(self, result: object) -> None:
            self.send_calls.append(result)
            self.started.set()
            await self.release.wait()

    async def scenario() -> None:
        registry, view = _issued_view(scopes)
        coordinator = _coordinator(registry, parts=("only",))
        event = _BlockingEvent()
        claim = coordinator.claim(view=view, lease=_lease(view), event=event)
        first = asyncio.create_task(coordinator.deliver(event=event, claim=claim))
        await event.started.wait()

        with pytest.raises(DeliveryStateError):
            await coordinator.deliver(event=event, claim=claim)

        event.release.set()
        snapshot = await first
        assert snapshot.state is DeliveryState.SENT_CONFIRMED
        assert len(event.send_calls) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("invalidate", ["view", "fence"])
def test_stale_view_or_fence_fails_before_send(
    scopes: Any,
    invalidate: str,
) -> None:
    async def scenario() -> None:
        registry, view = _issued_view(scopes)
        coordinator = _coordinator(registry)
        event = _Event()
        claim = coordinator.claim(view=view, lease=_lease(view), event=event)
        if invalidate == "view":
            assert registry.release_request_view(view) is True
        else:
            coordinator.invalidate_claim()

        snapshot = await coordinator.deliver(event=event, claim=claim)

        assert snapshot.state is DeliveryState.FAILED_BEFORE_SEND
        assert snapshot.confirmed_parts == 0
        assert event.plain_calls == []
        assert event.send_calls == []

    asyncio.run(scenario())


def test_exact_view_and_fence_are_revalidated_before_every_segment(scopes: Any) -> None:
    async def scenario() -> None:
        registry, view = _issued_view(scopes)
        coordinator = _coordinator(registry)
        event = _Event(after_send=lambda: registry.release_request_view(view))
        claim = coordinator.claim(view=view, lease=_lease(view), event=event)

        snapshot = await coordinator.deliver(event=event, claim=claim)

        assert snapshot.state is DeliveryState.OUTCOME_UNKNOWN
        assert snapshot.confirmed_parts == 0
        assert event.send_calls == [("plain", "first")]
        assert coordinator.turn.confirmed_parts == ()

    asyncio.run(scenario())


def test_before_send_gate_preserves_one_claim_and_stops_before_the_next_segment(
    scopes: Any,
) -> None:
    async def scenario() -> None:
        registry, view = _issued_view(scopes)
        coordinator = _coordinator(registry)
        event = _Event()
        claim = coordinator.claim(view=view, lease=_lease(view), event=event)
        gate_calls: list[tuple[int, str]] = []

        async def before_send(index: int, text: str) -> bool:
            gate_calls.append((index, text))
            return index == 0

        snapshot = await coordinator.deliver(
            event=event,
            claim=claim,
            before_send=before_send,
        )

        assert gate_calls == [(0, "first"), (1, "second")]
        assert event.send_calls == [("plain", "first")]
        assert snapshot.state is DeliveryState.PARTIAL
        assert coordinator.turn.confirmed_parts == ("first",)

    asyncio.run(scenario())


def test_cancellation_while_waiting_at_the_before_send_gate_finishes_before_send(
    scopes: Any,
) -> None:
    async def scenario() -> None:
        registry, view = _issued_view(scopes)
        coordinator = _coordinator(registry, parts=("only",))
        event = _Event()
        claim = coordinator.claim(view=view, lease=_lease(view), event=event)
        started = asyncio.Event()
        release = asyncio.Event()

        async def before_send(_index: int, _text: str) -> bool:
            started.set()
            await release.wait()
            return True

        task = asyncio.create_task(
            coordinator.deliver(
                event=event,
                claim=claim,
                before_send=before_send,
            )
        )
        await started.wait()
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert coordinator.state is DeliveryState.FAILED_BEFORE_SEND
        assert event.send_calls == []

    asyncio.run(scenario())


def test_send_exception_is_outcome_unknown_and_never_retried(scopes: Any) -> None:
    async def scenario() -> None:
        registry, view = _issued_view(scopes)
        coordinator = _coordinator(registry, parts=("only",))
        event = _Event(send_error=RuntimeError("transport result unknown"))
        claim = coordinator.claim(view=view, lease=_lease(view), event=event)

        with pytest.raises(RuntimeError, match="transport result unknown"):
            await coordinator.deliver(event=event, claim=claim)

        assert coordinator.state is DeliveryState.OUTCOME_UNKNOWN
        assert coordinator.turn.confirmed_parts == ()
        assert len(event.send_calls) == 1
        with pytest.raises(DeliveryStateError):
            await coordinator.deliver(event=event, claim=claim)
        assert len(event.send_calls) == 1

    asyncio.run(scenario())


def test_cancellation_during_send_is_outcome_unknown_and_propagates(scopes: Any) -> None:
    class _BlockingEvent(_Event):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()
            self.release = asyncio.Event()

        async def send(self, result: object) -> None:
            self.send_calls.append(result)
            self.started.set()
            await self.release.wait()

    async def scenario() -> None:
        registry, view = _issued_view(scopes)
        coordinator = _coordinator(registry, parts=("only",))
        event = _BlockingEvent()
        claim = coordinator.claim(view=view, lease=_lease(view), event=event)

        task = asyncio.create_task(coordinator.deliver(event=event, claim=claim))
        await event.started.wait()
        assert coordinator.state is DeliveryState.SENDING
        assert coordinator.turn.confirmed_parts == ()

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert coordinator.state is DeliveryState.OUTCOME_UNKNOWN
        assert coordinator.turn.confirmed_parts == ()
        assert len(event.send_calls) == 1

    asyncio.run(scenario())


def test_send_return_not_after_message_hook_confirms_local_completion(
    scopes: Any,
) -> None:
    class _BlockingEvent(_Event):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()
            self.release = asyncio.Event()

        async def send(self, result: object) -> None:
            self.send_calls.append(result)
            self.started.set()
            await self.release.wait()

    async def scenario() -> None:
        registry, view = _issued_view(scopes)
        coordinator = _coordinator(registry, parts=("only",))
        event = _BlockingEvent()
        claim = coordinator.claim(view=view, lease=_lease(view), event=event)

        task = asyncio.create_task(coordinator.deliver(event=event, claim=claim))
        await event.started.wait()
        assert coordinator.state is DeliveryState.SENDING
        assert coordinator.snapshot.confirmed_parts == 0

        event.release.set()
        snapshot = await task
        assert snapshot.state is DeliveryState.SENT_CONFIRMED
        assert snapshot.confirmed_parts == 1

    asyncio.run(scenario())


def test_claim_requires_exact_types(scopes: Any) -> None:
    registry, view = _issued_view(scopes)
    coordinator = _coordinator(registry)
    event = _Event()

    with pytest.raises(DeliveryLeaseRejected):
        coordinator.claim(view=object(), lease=_lease(view), event=event)  # type: ignore[arg-type]
    with pytest.raises(DeliveryLeaseRejected):
        coordinator.claim(view=view, lease=object(), event=event)  # type: ignore[arg-type]


def test_forged_claim_with_current_values_cannot_send(scopes: Any) -> None:
    async def scenario() -> None:
        registry, view = _issued_view(scopes)
        coordinator = _coordinator(registry, parts=("only",))
        event = _Event()
        claim = coordinator.claim(view=view, lease=_lease(view), event=event)
        forged = DeliveryClaim(
            lease=claim.lease,
            fence=claim.fence,
            view=claim.view,
            event=claim.event,
        )

        snapshot = await coordinator.deliver(event=event, claim=forged)

        assert snapshot.state is DeliveryState.FAILED_BEFORE_SEND
        assert event.plain_calls == []
        assert event.send_calls == []

    asyncio.run(scenario())


def test_process_local_turn_and_snapshot_exclude_persistence_unsafe_fields(
    scopes: Any,
) -> None:
    registry, _ = _issued_view(scopes)
    coordinator = _coordinator(registry)

    assert {item.name for item in fields(ProcessLocalDeliveryTurn)} == {
        "planned_parts",
        "_confirmed_parts",
    }
    for forbidden in (
        "session_key",
        "origin",
        "run_context",
        "response",
        "event",
        "umo",
        "address",
    ):
        assert not hasattr(coordinator.turn, forbidden)

    assert asdict(coordinator.snapshot) == {
        "state": DeliveryState.PLANNED,
        "planned_parts": 2,
        "confirmed_parts": 0,
    }


@pytest.mark.parametrize(
    ("plain_error_at", "expected_state", "confirmed"),
    [
        (1, DeliveryState.FAILED_BEFORE_SEND, ()),
        (2, DeliveryState.PARTIAL, ("first",)),
    ],
)
def test_plain_result_failure_is_known_before_send(
    scopes: Any,
    plain_error_at: int,
    expected_state: DeliveryState,
    confirmed: tuple[str, ...],
) -> None:
    async def scenario() -> None:
        registry, view = _issued_view(scopes)
        coordinator = _coordinator(registry)
        event = _Event(plain_error_at=plain_error_at)
        claim = coordinator.claim(view=view, lease=_lease(view), event=event)

        with pytest.raises(RuntimeError, match="plain result failed before send"):
            await coordinator.deliver(event=event, claim=claim)

        assert coordinator.state is expected_state
        assert coordinator.turn.confirmed_parts == confirmed
        assert len(event.send_calls) == len(confirmed)
        with pytest.raises(DeliveryStateError):
            await coordinator.deliver(event=event, claim=claim)

    asyncio.run(scenario())
