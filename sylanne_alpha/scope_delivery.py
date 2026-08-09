"""Fail-closed, scope-bound delivery for one reactive assistant turn.

The raw AstrBot event is deliberately accepted only by :meth:`deliver` and is
never retained on the coordinator.  A normal ``event.send`` return is treated
as local transport acceptance/completion, not as a remote receipt.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Protocol

from .scope_contracts import (
    BotDeliveryRef,
    BotRef,
    PersonaRevisionRef,
    ProactiveDeliveryLease,
    ProactiveIntentDraft,
    SessionRef,
    SessionScope,
    TurnDeliveryLease,
)
from .scope_repository import (
    RepositoryCorruptionError,
    ScopeRepository,
    _canonical_json_bytes,
)
from .scope_identity import CurrentAdapterAccountProof, resolve_proven_single_account
from .scope_runtime import RequestRuntimeView
from .session_catalog import SessionCatalog


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


class DeliveryStatus(str, Enum):
    """Durable proactive delivery states.

    ``DISPATCHING`` is persisted before the external send starts.  Recovery may
    retry it only when the sealed adapter capability declares external
    idempotency; ordinary transports remain outcome-unknown.
    """

    PENDING = "pending"
    CLAIMED = "claimed"
    DISPATCHING = "dispatching"
    SENT_CONFIRMED = "sent_confirmed"
    FAILED_RETRYABLE = "failed_retryable"
    OUTCOME_UNKNOWN = "outcome_unknown"
    SUPPRESSED = "suppressed"
    EXPIRED = "expired"


_OUTBOX_SCHEMA = "sylanne.delivery.outbox.v1"
_OUTBOX_TERMINAL = frozenset(
    {
        DeliveryStatus.SENT_CONFIRMED,
        DeliveryStatus.OUTCOME_UNKNOWN,
        DeliveryStatus.SUPPRESSED,
        DeliveryStatus.EXPIRED,
    }
)
_SAFE_OUTBOX_REASONS = frozenset(
    {
        "account_unavailable",
        "claim_expired",
        "claim_recovered",
        "adapter_rejected_before_send",
        "expired",
        "lease_invalid",
        "persona_or_turn_superseded",
        "transport_unavailable",
    }
)
_IDEMPOTENT_DELIVERY_CAPABILITIES = frozenset(
    {
        "proactive_idempotent",
        "proactive_idempotent_v1",
    }
)


class UnverifiedDeliveryIntent(ValueError):
    """A caller attempted to bypass the SessionCatalog intent issuer."""


class DeliveryNotSent(RuntimeError):
    """An adapter can prove its failure happened before it started a send."""


@dataclass(frozen=True, slots=True)
class DeliveryReceipt:
    """Explicit remote confirmation bound to one durable delivery id."""

    delivery_id: str

    def __post_init__(self) -> None:
        if type(self.delivery_id) is not str or not self.delivery_id:
            raise ValueError("delivery_id must be a non-empty string")


class AccountAwareTransport(Protocol):
    """The only proactive transport boundary accepted by the durable outbox."""

    def can_address(self, delivery_ref: BotDeliveryRef) -> bool: ...

    async def send(
        self, delivery_ref: BotDeliveryRef, text: str
    ) -> object: ...


class AstrBotAccountAwareTransport:
    """Fail-closed proactive adapter for AstrBot's account-scoped send API.

    AstrBot's ``Context.send_message`` result is local adapter feedback only.
    This adapter deliberately returns it unchanged: the outbox can classify only
    an explicit :class:`DeliveryReceipt` as remote confirmation.
    """

    def __init__(
        self,
        context: object,
        account_proofs: object,
        *,
        message_chain_factory: Callable[[], object] | None = None,
        clock_ms: Callable[[], int] | None = None,
    ) -> None:
        if not callable(getattr(account_proofs, "current", None)):
            raise ValueError("account_proofs must expose current(platform_id)")
        if message_chain_factory is not None and not callable(message_chain_factory):
            raise ValueError("message_chain_factory must be callable or None")
        if clock_ms is not None and not callable(clock_ms):
            raise ValueError("clock_ms must be callable or None")
        self._context = context
        self._account_proofs = account_proofs
        self._message_chain_factory = message_chain_factory or self._new_message_chain
        self._clock_ms = clock_ms or (lambda: time.time_ns() // 1_000_000)

    @staticmethod
    def _new_message_chain() -> object:
        try:
            from astrbot.api.event import MessageChain  # type: ignore

            return MessageChain()
        except Exception:
            class _FallbackMessageChain:
                def __init__(self) -> None:
                    self.chain: list[str] = []

                def message(self, text: str) -> _FallbackMessageChain:
                    self.chain.append(text)
                    return self

            return _FallbackMessageChain()

    def _now_ms(self) -> int | None:
        try:
            value = self._clock_ms()
        except Exception:
            return None
        return value if type(value) is int and value >= 0 else None

    def _live_proof_matches(self, delivery_ref: BotDeliveryRef) -> bool:
        now_ms = self._now_ms()
        if now_ms is None:
            return False
        try:
            current = self._account_proofs.current(delivery_ref.platform_id)
        except Exception:
            return False
        if type(current) is not CurrentAdapterAccountProof:
            return False
        proven = resolve_proven_single_account(
            current.proof,
            platform_id=delivery_ref.platform_id,
            current_account_set_digest=current.current_account_set_digest,
            current_proof_generation=current.current_proof_generation,
            now_ms=now_ms,
        )
        return proven == delivery_ref.bot_ref

    def _platform_supports_proactive(self, platform_id: str) -> bool:
        getter = getattr(self._context, "get_platform_inst", None)
        if not callable(getter):
            return False
        try:
            platform = getter(platform_id)
            meta = getattr(platform, "meta", None)
            details = meta() if callable(meta) else None
            return getattr(details, "support_proactive_message", None) is True
        except Exception:
            return False

    def can_address(self, delivery_ref: BotDeliveryRef) -> bool:
        """Revalidate account, BotRef, and platform capability at every boundary."""

        return bool(
            type(delivery_ref) is BotDeliveryRef
            and delivery_ref.adapter_capability == "proactive_send_v1"
            and callable(getattr(self._context, "send_message", None))
            and self._live_proof_matches(delivery_ref)
            and self._platform_supports_proactive(delivery_ref.platform_id)
        )

    async def send(self, delivery_ref: BotDeliveryRef, text: str) -> object:
        if type(delivery_ref) is not BotDeliveryRef or type(text) is not str or not text:
            raise DeliveryNotSent("proactive delivery input is invalid")
        if not self.can_address(delivery_ref):
            raise DeliveryNotSent("proactive account or platform is unavailable")
        try:
            chain = self._message_chain_factory()
            build = getattr(chain, "message", None)
            if not callable(build):
                raise DeliveryNotSent("AstrBot MessageChain is unavailable")
            payload = build(text)
            if payload is None:
                payload = chain
            result = self._context.send_message(delivery_ref.target_address, payload)
            if inspect.isawaitable(result):
                result = await result
        except DeliveryNotSent:
            raise
        if result is False:
            raise DeliveryNotSent("AstrBot rejected delivery before send")
        return result


@dataclass(frozen=True, slots=True, repr=False)
class DeliveryItem:
    """Safe in-process projection of one durable outbox item.

    The full sealed draft stays repr-hidden.  It is never emitted by logging or
    API-facing code; the persistence layer is the sole owner of address data.
    """

    delivery_ref: BotDeliveryRef
    delivery_id: str
    status: DeliveryStatus
    idempotent: bool
    item_generation: int
    claim_worker_id: str | None = field(default=None, repr=False)
    claim_generation: int = 0
    claim_expires_at_ms: int | None = field(default=None, repr=False)
    reason: str | None = None
    _draft: ProactiveIntentDraft = field(repr=False, compare=False, default=None)  # type: ignore[assignment]


DeliveryEnvelope = DeliveryItem


def _ref_document(ref: BotDeliveryRef) -> dict[str, object]:
    return {
        "token": ref.token,
        "delivery_id": ref.delivery_id,
        "bot_ref": {"token": ref.bot_ref.token, "generation": ref.bot_ref.generation},
        "persona_ref": {
            "token": ref.persona_ref.token,
            "bot_ref": {
                "token": ref.persona_ref.bot_ref.token,
                "generation": ref.persona_ref.bot_ref.generation,
            },
            "persona_id_digest": ref.persona_ref.persona_id_digest,
            "source_fingerprint": ref.persona_ref.source_fingerprint,
            "lifecycle_generation": ref.persona_ref.lifecycle_generation,
        },
        "session_ref": {
            "token": ref.session_ref.token,
            "bot_ref": {
                "token": ref.session_ref.bot_ref.token,
                "generation": ref.session_ref.bot_ref.generation,
            },
            "generation": ref.session_ref.generation,
        },
        "platform_id": ref.platform_id,
        "self_id": ref.self_id,
        "target_address": ref.target_address,
        "adapter_capability": ref.adapter_capability,
    }


def _ref_from_document(document: object) -> BotDeliveryRef:
    if type(document) is not dict or set(document) != {
        "token",
        "delivery_id",
        "bot_ref",
        "persona_ref",
        "session_ref",
        "platform_id",
        "self_id",
        "target_address",
        "adapter_capability",
    }:
        raise ValueError("delivery reference is invalid")
    bot = document["bot_ref"]
    persona = document["persona_ref"]
    session = document["session_ref"]
    if (
        type(bot) is not dict
        or set(bot) != {"token", "generation"}
        or type(persona) is not dict
        or set(persona)
        != {
            "token",
            "bot_ref",
            "persona_id_digest",
            "source_fingerprint",
            "lifecycle_generation",
        }
        or type(session) is not dict
        or set(session) != {"token", "bot_ref", "generation"}
    ):
        raise ValueError("delivery reference is invalid")
    persona_bot = persona["bot_ref"]
    session_bot = session["bot_ref"]
    if (
        type(persona_bot) is not dict
        or set(persona_bot) != {"token", "generation"}
        or type(session_bot) is not dict
        or set(session_bot) != {"token", "generation"}
    ):
        raise ValueError("delivery reference is invalid")
    bot_ref = BotRef(token=bot["token"], generation=bot["generation"])
    return BotDeliveryRef(
        token=document["token"],
        delivery_id=document["delivery_id"],
        bot_ref=bot_ref,
        persona_ref=PersonaRevisionRef(
            token=persona["token"],
            bot_ref=BotRef(
                token=persona_bot["token"],
                generation=persona_bot["generation"],
            ),
            persona_id_digest=persona["persona_id_digest"],
            source_fingerprint=persona["source_fingerprint"],
            lifecycle_generation=persona["lifecycle_generation"],
        ),
        session_ref=SessionRef(
            token=session["token"],
            bot_ref=BotRef(
                token=session_bot["token"],
                generation=session_bot["generation"],
            ),
            generation=session["generation"],
        ),
        platform_id=document["platform_id"],
        self_id=document["self_id"],
        target_address=document["target_address"],
        adapter_capability=document["adapter_capability"],
    )


def _lease_document(lease: ProactiveDeliveryLease) -> dict[str, object]:
    return {
        "transport_session_token": lease.transport_session_token,
        "resolved_scope_token": lease.resolved_scope_token,
        "expected_persona_token": lease.expected_persona_token,
        "persona_lifecycle_generation": lease.persona_lifecycle_generation,
        "session_generation": lease.session_generation,
        "scope_generation": lease.scope_generation,
        "expected_turn_generation": lease.expected_turn_generation,
        "expires_at_ms": lease.expires_at_ms,
    }


def _lease_from_document(document: object) -> ProactiveDeliveryLease:
    if type(document) is not dict or set(document) != {
        "transport_session_token",
        "resolved_scope_token",
        "expected_persona_token",
        "persona_lifecycle_generation",
        "session_generation",
        "scope_generation",
        "expected_turn_generation",
        "expires_at_ms",
    }:
        raise ValueError("proactive delivery lease is invalid")
    return ProactiveDeliveryLease(**document)


def _draft_document(draft: ProactiveIntentDraft) -> dict[str, object]:
    return {
        "delivery_ref": _ref_document(draft.delivery_ref),
        "lease": _lease_document(draft.lease),
        "text": draft.text,
        "idempotent": draft.idempotent,
        "issuer_mac": draft.issuer_mac,
    }


def _draft_from_document(document: object) -> ProactiveIntentDraft:
    if type(document) is not dict or set(document) != {
        "delivery_ref",
        "lease",
        "text",
        "idempotent",
        "issuer_mac",
    }:
        raise ValueError("proactive draft is invalid")
    return ProactiveIntentDraft(
        delivery_ref=_ref_from_document(document["delivery_ref"]),
        lease=_lease_from_document(document["lease"]),
        text=document["text"],
        idempotent=document["idempotent"],
        issuer_mac=document["issuer_mac"],
    )


def _item_document(item: DeliveryItem) -> dict[str, object]:
    return {
        "item_generation": item.item_generation,
        "status": item.status.value,
        "draft": _draft_document(item._draft),
        "claim_worker_id": item.claim_worker_id,
        "claim_generation": item.claim_generation,
        "claim_expires_at_ms": item.claim_expires_at_ms,
        "reason": item.reason,
    }


def _item_from_document(document: object) -> DeliveryItem:
    if type(document) is not dict or set(document) != {
        "item_generation",
        "status",
        "draft",
        "claim_worker_id",
        "claim_generation",
        "claim_expires_at_ms",
        "reason",
    }:
        raise ValueError("delivery outbox item is invalid")
    draft = _draft_from_document(document["draft"])
    try:
        status = DeliveryStatus(document["status"])
    except (TypeError, ValueError) as exc:
        raise ValueError("delivery outbox item status is invalid") from exc
    generation = document["item_generation"]
    claim_generation = document["claim_generation"]
    worker_id = document["claim_worker_id"]
    claim_expires_at_ms = document["claim_expires_at_ms"]
    reason = document["reason"]
    if (
        type(generation) is not int
        or generation < 1
        or type(claim_generation) is not int
        or claim_generation < 0
        or (worker_id is not None and (type(worker_id) is not str or not worker_id))
        or (
            claim_expires_at_ms is not None
            and (type(claim_expires_at_ms) is not int or claim_expires_at_ms < 0)
        )
        or (reason is not None and reason not in _SAFE_OUTBOX_REASONS)
    ):
        raise ValueError("delivery outbox item is invalid")
    if draft.delivery_ref.delivery_id != draft.delivery_ref.token:
        raise ValueError("delivery outbox item is invalid")
    return DeliveryItem(
        delivery_ref=draft.delivery_ref,
        delivery_id=draft.delivery_ref.delivery_id,
        status=status,
        idempotent=draft.idempotent,
        item_generation=generation,
        claim_worker_id=worker_id,
        claim_generation=claim_generation,
        claim_expires_at_ms=claim_expires_at_ms,
        reason=reason,
        _draft=draft,
    )


def _scope_for_draft(draft: ProactiveIntentDraft) -> SessionScope:
    return SessionScope(
        bot_ref=draft.delivery_ref.bot_ref,
        persona_ref=draft.delivery_ref.persona_ref,
        session_ref=draft.delivery_ref.session_ref,
        storage_token=draft.lease.resolved_scope_token,
        scope_generation=draft.lease.scope_generation,
    )


def _lookup_scope(ref: BotDeliveryRef) -> SessionScope:
    """Build a path-only scope; no authority decision uses this placeholder."""

    return SessionScope(
        bot_ref=ref.bot_ref,
        persona_ref=ref.persona_ref,
        session_ref=ref.session_ref,
        storage_token="scope_v1_outbox_lookup",
        scope_generation=0,
    )


class DeliveryOutbox:
    """Cross-process durable owner for proactive-only delivery attempts."""

    def __init__(
        self,
        repository: ScopeRepository,
        catalog: SessionCatalog,
        *,
        claim_lease_ms: int = 30_000,
        clock_ms: Callable[[], int] | None = None,
    ) -> None:
        if type(repository) is not ScopeRepository:
            raise ValueError("repository must be a ScopeRepository")
        if type(catalog) is not SessionCatalog or catalog.repository is not repository:
            raise ValueError("catalog must own the same ScopeRepository")
        if type(claim_lease_ms) is not int or claim_lease_ms < 1:
            raise ValueError("claim_lease_ms must be a positive int")
        if clock_ms is not None and not callable(clock_ms):
            raise ValueError("clock_ms must be callable or None")
        self.repository = repository
        self.catalog = catalog
        self._claim_lease_ms = claim_lease_ms
        self._clock_ms = clock_ms or (lambda: time.time_ns() // 1_000_000)

    def _now_ms(self) -> int:
        value = self._clock_ms()
        if type(value) is not int or value < 0:
            raise ValueError("outbox clock returned an invalid timestamp")
        return value

    @staticmethod
    def _new_document(scope: SessionScope) -> dict[str, object]:
        return {
            "schema_version": _OUTBOX_SCHEMA,
            "generation": 0,
            "bot_ref": scope.bot_ref.token,
            "persona_ref": scope.persona_ref.token,
            "items": {},
        }

    def _load_document_locked(
        self,
        scope: SessionScope,
    ) -> tuple[int, dict[str, DeliveryItem]]:
        loaded = self.repository._read_delivery_outbox_locked(scope)
        if loaded is None:
            return 0, {}
        raw, document = loaded
        if raw != _canonical_json_bytes(document) or set(document) != {
            "schema_version",
            "generation",
            "bot_ref",
            "persona_ref",
            "items",
        }:
            raise RepositoryCorruptionError("delivery outbox is invalid")
        generation = document["generation"]
        raw_items = document["items"]
        if (
            document["schema_version"] != _OUTBOX_SCHEMA
            or type(generation) is not int
            or generation < 1
            or document["bot_ref"] != scope.bot_ref.token
            or document["persona_ref"] != scope.persona_ref.token
            or type(raw_items) is not dict
        ):
            raise RepositoryCorruptionError("delivery outbox is invalid")
        items: dict[str, DeliveryItem] = {}
        try:
            for token, raw_item in raw_items.items():
                if type(token) is not str:
                    raise ValueError("outbox key is invalid")
                item = _item_from_document(raw_item)
                if (
                    item.delivery_ref.token != token
                    or item.delivery_ref.bot_ref != scope.bot_ref
                    or item.delivery_ref.persona_ref != scope.persona_ref
                ):
                    raise ValueError("outbox parent is invalid")
                items[token] = item
        except ValueError as exc:
            raise RepositoryCorruptionError("delivery outbox is invalid") from exc
        return generation, items

    def _write_document_locked(
        self,
        scope: SessionScope,
        *,
        expected_generation: int,
        items: dict[str, DeliveryItem],
    ) -> None:
        document = {
            "schema_version": _OUTBOX_SCHEMA,
            "generation": expected_generation + 1,
            "bot_ref": scope.bot_ref.token,
            "persona_ref": scope.persona_ref.token,
            "items": {token: _item_document(item) for token, item in items.items()},
        }
        self.repository._write_delivery_outbox_locked(scope, document)

    @staticmethod
    def _current_item(
        stored: DeliveryItem | None,
        expected: DeliveryItem,
    ) -> bool:
        return (
            stored is not None
            and stored.delivery_ref == expected.delivery_ref
            and stored.item_generation == expected.item_generation
            and stored.claim_generation == expected.claim_generation
        )

    @staticmethod
    def _replace_item(
        item: DeliveryItem,
        *,
        status: DeliveryStatus,
        reason: str | None,
        claim_worker_id: str | None = None,
        claim_generation: int | None = None,
        claim_expires_at_ms: int | None = None,
    ) -> DeliveryItem:
        return replace(
            item,
            status=status,
            item_generation=item.item_generation + 1,
            claim_worker_id=claim_worker_id,
            claim_generation=(
                item.claim_generation if claim_generation is None else claim_generation
            ),
            claim_expires_at_ms=claim_expires_at_ms,
            reason=reason,
        )

    def _valid_draft_locked(self, item: DeliveryItem, now_ms: int) -> bool:
        return self.catalog._verify_proactive_intent_locked(
            item._draft,
            now_ms=now_ms,
        )

    @staticmethod
    def _retry_after_unknown_is_safe(item: DeliveryItem) -> bool:
        """Require both caller intent and adapter-proven external idempotency."""

        return (
            item.idempotent
            and item.delivery_ref.adapter_capability
            in _IDEMPOTENT_DELIVERY_CAPABILITIES
        )

    @classmethod
    def _retryable_failure_is_safe(cls, item: DeliveryItem) -> bool:
        """Allow known pre-send failures without requiring remote idempotency."""

        return item.reason == "adapter_rejected_before_send" or cls._retry_after_unknown_is_safe(item)

    @staticmethod
    def _stale_reason(item: DeliveryItem) -> str:
        return "persona_or_turn_superseded" if item.status is not DeliveryStatus.PENDING else "lease_invalid"

    def enqueue(self, draft: object) -> DeliveryItem:
        """Persist only a fresh SessionCatalog-issued proactive draft."""

        if type(draft) is not ProactiveIntentDraft:
            raise UnverifiedDeliveryIntent("proactive intent was not catalog-issued")
        now_ms = self._now_ms()
        try:
            scope = _scope_for_draft(draft)
        except ValueError as exc:
            raise UnverifiedDeliveryIntent("proactive intent is malformed") from exc
        with self.repository.transaction():
            if not self.catalog._verify_proactive_intent_locked(draft, now_ms=now_ms):
                raise UnverifiedDeliveryIntent("proactive intent is stale or forged")
            generation, items = self._load_document_locked(scope)
            existing = items.get(draft.delivery_ref.token)
            if existing is not None:
                if existing._draft == draft:
                    return existing
                raise UnverifiedDeliveryIntent("delivery token already exists")
            item = DeliveryItem(
                delivery_ref=draft.delivery_ref,
                delivery_id=draft.delivery_ref.delivery_id,
                status=DeliveryStatus.PENDING,
                idempotent=draft.idempotent,
                item_generation=1,
                _draft=draft,
            )
            items[item.delivery_ref.token] = item
            self._write_document_locked(
                scope,
                expected_generation=generation,
                items=items,
            )
            return item

    def _load_item_locked(
        self,
        delivery_ref: BotDeliveryRef,
    ) -> tuple[SessionScope, int, dict[str, DeliveryItem], DeliveryItem] | None:
        scope = _lookup_scope(delivery_ref)
        generation, items = self._load_document_locked(scope)
        item = items.get(delivery_ref.token)
        if item is None or item.delivery_ref != delivery_ref:
            return None
        return scope, generation, items, item

    def get(self, delivery_ref: object) -> DeliveryItem | None:
        if type(delivery_ref) is not BotDeliveryRef:
            return None
        try:
            with self.repository.transaction():
                loaded = self._load_item_locked(delivery_ref)
                return None if loaded is None else loaded[3]
        except (RepositoryCorruptionError, ValueError):
            return None

    def _suppress_locked(
        self,
        scope: SessionScope,
        generation: int,
        items: dict[str, DeliveryItem],
        item: DeliveryItem,
        *,
        reason: str,
    ) -> DeliveryItem | None:
        if reason not in _SAFE_OUTBOX_REASONS or item.status in _OUTBOX_TERMINAL:
            return None
        current = items.get(item.delivery_ref.token)
        if not self._current_item(current, item):
            return None
        suppressed = self._replace_item(
            item,
            status=DeliveryStatus.SUPPRESSED,
            reason=reason,
        )
        items[item.delivery_ref.token] = suppressed
        self._write_document_locked(
            scope,
            expected_generation=generation,
            items=items,
        )
        return suppressed

    def _expire_locked(
        self,
        scope: SessionScope,
        generation: int,
        items: dict[str, DeliveryItem],
        item: DeliveryItem,
    ) -> DeliveryItem | None:
        if item.status in _OUTBOX_TERMINAL:
            return None
        current = items.get(item.delivery_ref.token)
        if not self._current_item(current, item):
            return None
        expired = self._replace_item(
            item,
            status=DeliveryStatus.EXPIRED,
            reason="expired",
        )
        items[item.delivery_ref.token] = expired
        self._write_document_locked(
            scope,
            expected_generation=generation,
            items=items,
        )
        return expired

    def claim(self, delivery_ref: object, *, worker_id: str) -> DeliveryItem | None:
        """Acquire one fenced, expiring claim with a fresh live lease check."""

        if type(delivery_ref) is not BotDeliveryRef or type(worker_id) is not str or not worker_id:
            return None
        now_ms = self._now_ms()
        try:
            with self.repository.transaction():
                loaded = self._load_item_locked(delivery_ref)
                if loaded is None:
                    return None
                scope, generation, items, item = loaded
                if item.status is DeliveryStatus.CLAIMED:
                    if (
                        item.claim_expires_at_ms is None
                        or now_ms < item.claim_expires_at_ms
                    ):
                        return None
                    item = self._replace_item(
                        item,
                        status=DeliveryStatus.PENDING,
                        reason="claim_expired",
                    )
                    items[item.delivery_ref.token] = item
                if (
                    item.status is DeliveryStatus.FAILED_RETRYABLE
                    and not self._retryable_failure_is_safe(item)
                ):
                    item = self._replace_item(
                        item,
                        status=DeliveryStatus.OUTCOME_UNKNOWN,
                        reason=None,
                    )
                    items[item.delivery_ref.token] = item
                    self._write_document_locked(
                        scope,
                        expected_generation=generation,
                        items=items,
                    )
                    return item
                if item.status not in {
                    DeliveryStatus.PENDING,
                    DeliveryStatus.FAILED_RETRYABLE,
                }:
                    return None
                if now_ms >= item._draft.lease.expires_at_ms:
                    self._expire_locked(
                        scope,
                        generation,
                        items,
                        item,
                    )
                    return None
                if not self._valid_draft_locked(item, now_ms):
                    self._suppress_locked(
                        scope,
                        generation,
                        items,
                        item,
                        reason=self._stale_reason(item),
                    )
                    return None
                claimed = self._replace_item(
                    item,
                    status=DeliveryStatus.CLAIMED,
                    reason=None,
                    claim_worker_id=worker_id,
                    claim_generation=item.claim_generation + 1,
                    claim_expires_at_ms=now_ms + self._claim_lease_ms,
                )
                items[claimed.delivery_ref.token] = claimed
                self._write_document_locked(
                    scope,
                    expected_generation=generation,
                    items=items,
                )
                return claimed
        except (RepositoryCorruptionError, ValueError):
            return None

    def mark_dispatching(
        self,
        claim: object,
        *,
        worker_id: str,
    ) -> DeliveryItem | None:
        """Durably cross the external-side-effect boundary before ``await send``."""

        if type(claim) is not DeliveryItem or type(worker_id) is not str or not worker_id:
            return None
        now_ms = self._now_ms()
        try:
            with self.repository.transaction():
                loaded = self._load_item_locked(claim.delivery_ref)
                if loaded is None:
                    return None
                scope, generation, items, item = loaded
                if (
                    not self._current_item(item, claim)
                    or item.status is not DeliveryStatus.CLAIMED
                    or item.claim_worker_id != worker_id
                ):
                    return None
                if (
                    item.claim_expires_at_ms is None
                    or now_ms >= item.claim_expires_at_ms
                ):
                    pending = self._replace_item(
                        item,
                        status=DeliveryStatus.PENDING,
                        reason="claim_expired",
                    )
                    items[pending.delivery_ref.token] = pending
                    self._write_document_locked(
                        scope,
                        expected_generation=generation,
                        items=items,
                    )
                    return None
                if not self._valid_draft_locked(item, now_ms):
                    self._suppress_locked(
                        scope,
                        generation,
                        items,
                        item,
                        reason=self._stale_reason(item),
                    )
                    return None
                dispatching = self._replace_item(
                    item,
                    status=DeliveryStatus.DISPATCHING,
                    reason=None,
                    claim_worker_id=item.claim_worker_id,
                    claim_generation=item.claim_generation,
                    claim_expires_at_ms=item.claim_expires_at_ms,
                )
                items[dispatching.delivery_ref.token] = dispatching
                self._write_document_locked(
                    scope,
                    expected_generation=generation,
                    items=items,
                )
                return dispatching
        except (RepositoryCorruptionError, ValueError):
            return None

    def settle(
        self,
        claim: object,
        *,
        worker_id: str,
        status: DeliveryStatus,
        reason: str | None = None,
    ) -> DeliveryItem | None:
        """Settle a persisted dispatch using its item and claim generations."""

        if (
            type(claim) is not DeliveryItem
            or type(worker_id) is not str
            or not worker_id
            or status
            not in {
                DeliveryStatus.SENT_CONFIRMED,
                DeliveryStatus.FAILED_RETRYABLE,
                DeliveryStatus.OUTCOME_UNKNOWN,
            }
            or (reason is not None and reason not in _SAFE_OUTBOX_REASONS)
        ):
            return None
        now_ms = self._now_ms()
        try:
            with self.repository.transaction():
                loaded = self._load_item_locked(claim.delivery_ref)
                if loaded is None:
                    return None
                scope, generation, items, item = loaded
                if (
                    not self._current_item(item, claim)
                    or item.status is not DeliveryStatus.DISPATCHING
                    or item.claim_worker_id != worker_id
                ):
                    return None
                if (
                    status is not DeliveryStatus.OUTCOME_UNKNOWN
                    and not self._valid_draft_locked(item, now_ms)
                ):
                    status = DeliveryStatus.OUTCOME_UNKNOWN
                    reason = None
                settled = self._replace_item(
                    item,
                    status=status,
                    reason=reason,
                    claim_worker_id=item.claim_worker_id,
                    claim_generation=item.claim_generation,
                    claim_expires_at_ms=item.claim_expires_at_ms,
                )
                items[settled.delivery_ref.token] = settled
                self._write_document_locked(
                    scope,
                    expected_generation=generation,
                    items=items,
                )
                return settled
        except (RepositoryCorruptionError, ValueError):
            return None

    def suppress(
        self,
        claim: object,
        *,
        reason: str = "account_unavailable",
    ) -> DeliveryItem | None:
        """Suppress a not-yet-sent item without ever redirecting its address."""

        if type(claim) is not DeliveryItem or reason not in _SAFE_OUTBOX_REASONS:
            return None
        try:
            with self.repository.transaction():
                loaded = self._load_item_locked(claim.delivery_ref)
                if loaded is None:
                    return None
                scope, generation, items, item = loaded
                if not self._current_item(item, claim):
                    return None
                return self._suppress_locked(
                    scope,
                    generation,
                    items,
                    item,
                    reason=reason,
                )
        except (RepositoryCorruptionError, ValueError):
            return None

    def _all_items_locked(self) -> list[DeliveryItem]:
        items: list[DeliveryItem] = []
        for _path, raw, document in self.repository._iter_delivery_outboxes_locked():
            if raw != _canonical_json_bytes(document) or type(document.get("items")) is not dict:
                raise RepositoryCorruptionError("delivery outbox is invalid")
            for raw_item in document["items"].values():
                item = _item_from_document(raw_item)
                if (
                    document.get("bot_ref") != item.delivery_ref.bot_ref.token
                    or document.get("persona_ref") != item.delivery_ref.persona_ref.token
                ):
                    raise RepositoryCorruptionError("delivery outbox parent is invalid")
                items.append(item)
        return items

    def _next_candidate(self) -> DeliveryItem | None:
        try:
            with self.repository.transaction():
                candidates = [
                    item
                    for item in self._all_items_locked()
                    if item.status
                    in {DeliveryStatus.PENDING, DeliveryStatus.FAILED_RETRYABLE}
                ]
                if not candidates:
                    return None
                return min(candidates, key=lambda item: item.delivery_ref.token)
        except (RepositoryCorruptionError, ValueError):
            return None

    def recover_after_restart(self) -> dict[BotDeliveryRef, DeliveryItem]:
        """Classify durable claims without replaying non-idempotent sends."""

        now_ms = self._now_ms()
        recovered: dict[BotDeliveryRef, DeliveryItem] = {}
        try:
            with self.repository.transaction():
                grouped: dict[tuple[str, str], list[DeliveryItem]] = {}
                for item in self._all_items_locked():
                    grouped.setdefault(
                        (
                            item.delivery_ref.bot_ref.token,
                            item.delivery_ref.persona_ref.token,
                        ),
                        [],
                    ).append(item)
                for items_in_document in grouped.values():
                    anchor = items_in_document[0]
                    scope = _scope_for_draft(anchor._draft)
                    generation, items = self._load_document_locked(scope)
                    changed = False
                    for token, item in tuple(items.items()):
                        replacement: DeliveryItem | None = None
                        if (
                            item.status
                            in {
                                DeliveryStatus.PENDING,
                                DeliveryStatus.CLAIMED,
                                DeliveryStatus.FAILED_RETRYABLE,
                            }
                            and now_ms >= item._draft.lease.expires_at_ms
                        ):
                            replacement = self._replace_item(
                                item,
                                status=DeliveryStatus.EXPIRED,
                                reason="expired",
                            )
                        elif item.status is DeliveryStatus.CLAIMED:
                            replacement = self._replace_item(
                                item,
                                status=DeliveryStatus.PENDING,
                                reason="claim_recovered",
                            )
                        elif item.status is DeliveryStatus.DISPATCHING:
                            if (
                                self._retry_after_unknown_is_safe(item)
                                and self._valid_draft_locked(item, now_ms)
                            ):
                                replacement = self._replace_item(
                                    item,
                                    status=DeliveryStatus.FAILED_RETRYABLE,
                                    reason=None,
                                )
                            else:
                                replacement = self._replace_item(
                                    item,
                                    status=DeliveryStatus.OUTCOME_UNKNOWN,
                                    reason=None,
                                )
                        elif (
                            item.status
                            in {DeliveryStatus.PENDING, DeliveryStatus.FAILED_RETRYABLE}
                            and not self._valid_draft_locked(item, now_ms)
                        ):
                            replacement = self._replace_item(
                                item,
                                status=DeliveryStatus.SUPPRESSED,
                                reason=self._stale_reason(item),
                            )
                        elif (
                            item.status is DeliveryStatus.FAILED_RETRYABLE
                            and not self._retryable_failure_is_safe(item)
                        ):
                            replacement = self._replace_item(
                                item,
                                status=DeliveryStatus.OUTCOME_UNKNOWN,
                                reason=None,
                            )
                        if replacement is not None:
                            items[token] = replacement
                            item = replacement
                            changed = True
                        recovered[item.delivery_ref] = item
                    if changed:
                        self._write_document_locked(
                            scope,
                            expected_generation=generation,
                            items=items,
                        )
        except (RepositoryCorruptionError, ValueError):
            return recovered
        return recovered

    def expire(self) -> dict[BotDeliveryRef, DeliveryItem]:
        """Expire queued work; never rewrite an in-flight dispatch as unsent."""

        now_ms = self._now_ms()
        expired: dict[BotDeliveryRef, DeliveryItem] = {}
        try:
            with self.repository.transaction():
                grouped: dict[tuple[str, str], list[DeliveryItem]] = {}
                for item in self._all_items_locked():
                    grouped.setdefault(
                        (
                            item.delivery_ref.bot_ref.token,
                            item.delivery_ref.persona_ref.token,
                        ),
                        [],
                    ).append(item)
                for items_in_document in grouped.values():
                    scope = _scope_for_draft(items_in_document[0]._draft)
                    generation, items = self._load_document_locked(scope)
                    changed = False
                    for token, item in tuple(items.items()):
                        if (
                            item.status
                            in {
                                DeliveryStatus.PENDING,
                                DeliveryStatus.CLAIMED,
                                DeliveryStatus.FAILED_RETRYABLE,
                            }
                            and now_ms >= item._draft.lease.expires_at_ms
                        ):
                            item = self._replace_item(
                                item,
                                status=DeliveryStatus.EXPIRED,
                                reason="expired",
                            )
                            items[token] = item
                            expired[item.delivery_ref] = item
                            changed = True
                    if changed:
                        self._write_document_locked(
                            scope,
                            expected_generation=generation,
                            items=items,
                        )
        except (RepositoryCorruptionError, ValueError):
            return expired
        return expired

    async def dispatch_one(
        self,
        transport: AccountAwareTransport,
        *,
        worker_id: str = "outbox-worker",
    ) -> DeliveryItem | None:
        """Claim and attempt exactly one item using an account-aware transport."""

        candidate = self._next_candidate()
        if candidate is None:
            return None
        claim = self.claim(candidate.delivery_ref, worker_id=worker_id)
        if claim is None:
            return self.get(candidate.delivery_ref)
        can_address = getattr(transport, "can_address", None)
        send = getattr(transport, "send", None)
        try:
            addressable = callable(can_address) and can_address(claim.delivery_ref) is True
        except Exception:
            addressable = False
        if not addressable or not callable(send):
            return self.suppress(claim, reason="account_unavailable")
        dispatching = self.mark_dispatching(claim, worker_id=worker_id)
        if dispatching is None:
            return self.get(claim.delivery_ref)

        # Revalidate immediately before the externally visible send.  There is
        # no await between this check and calling the adapter.
        try:
            addressable = callable(can_address) and can_address(dispatching.delivery_ref) is True
        except Exception:
            addressable = False
        if not addressable:
            return self.suppress(dispatching, reason="account_unavailable")
        now_ms = self._now_ms()
        with self.repository.transaction():
            loaded = self._load_item_locked(dispatching.delivery_ref)
            valid = (
                loaded is not None
                and self._current_item(loaded[3], dispatching)
                and self._valid_draft_locked(loaded[3], now_ms)
            )
        if not valid:
            return self.suppress(dispatching, reason="lease_invalid")

        try:
            pending = send(dispatching.delivery_ref, dispatching._draft.text)
            if not inspect.isawaitable(pending):
                raise RuntimeError("account-aware transport returned no awaitable receipt")
            receipt = await pending
        except asyncio.CancelledError:
            # DISPATCHING was durably written before awaiting the adapter.  A
            # stopped worker has no reliable knowledge of the remote outcome.
            raise
        except DeliveryNotSent:
            return self.settle(
                dispatching,
                worker_id=worker_id,
                status=DeliveryStatus.FAILED_RETRYABLE,
                reason="adapter_rejected_before_send",
            )
        except Exception:
            return self.settle(
                dispatching,
                worker_id=worker_id,
                status=(
                    DeliveryStatus.FAILED_RETRYABLE
                    if self._retry_after_unknown_is_safe(dispatching)
                    else DeliveryStatus.OUTCOME_UNKNOWN
                ),
            )
        if (
            type(receipt) is not DeliveryReceipt
            or receipt.delivery_id != dispatching.delivery_id
        ):
            return self.settle(
                dispatching,
                worker_id=worker_id,
                status=DeliveryStatus.OUTCOME_UNKNOWN,
            )
        return self.settle(
            dispatching,
            worker_id=worker_id,
            status=DeliveryStatus.SENT_CONFIRMED,
        )


class ScopedDeliveryGateway:
    """Capability to enqueue proactive work for one exact live SessionScope."""

    def __init__(
        self,
        scope: SessionScope,
        registry: object,
        outbox: DeliveryOutbox,
        *,
        wake: Callable[[], object] | None = None,
        clock_ms: Callable[[], int] | None = None,
        default_lease_ms: int = 300_000,
    ) -> None:
        if type(scope) is not SessionScope:
            raise ValueError("scope must be an exact SessionScope")
        if not callable(getattr(registry, "is_live_session", None)):
            raise ValueError("registry must expose is_live_session(scope)")
        if type(outbox) is not DeliveryOutbox:
            raise ValueError("outbox must be a DeliveryOutbox")
        if wake is not None and not callable(wake):
            raise ValueError("wake must be callable or None")
        if clock_ms is not None and not callable(clock_ms):
            raise ValueError("clock_ms must be callable or None")
        if type(default_lease_ms) is not int or default_lease_ms < 1:
            raise ValueError("default_lease_ms must be a positive int")
        self.scope = scope
        self._registry = registry
        self._outbox = outbox
        self._wake = wake
        self._clock_ms = clock_ms or (lambda: time.time_ns() // 1_000_000)
        self._default_lease_ms = default_lease_ms

    def enqueue(
        self,
        *,
        text: str,
        idempotent: bool,
        expires_at_ms: int | None = None,
    ) -> DeliveryItem | None:
        """Issue and persist a sealed draft, but only while this scope is live."""

        if self._registry.is_live_session(self.scope) is not True:
            return None
        expiry = expires_at_ms
        if expiry is None:
            try:
                now_ms = self._clock_ms()
            except Exception:
                return None
            if type(now_ms) is not int or now_ms < 0:
                return None
            expiry = now_ms + self._default_lease_ms
        try:
            draft = self._outbox.catalog.issue_proactive_intent(
                self.scope,
                text=text,
                idempotent=idempotent,
                expires_at_ms=expiry,
            )
            item = self._outbox.enqueue(draft)
        except (UnverifiedDeliveryIntent, ValueError):
            return None
        wake = self._wake
        if wake is not None:
            try:
                wake()
            except Exception:
                pass
        return item


class DeliveryOutboxWorker:
    """A bounded in-process consumer for one durable outbox.

    The worker intentionally owns no address state.  Its transport revalidates
    the account on every send, while the outbox retains the only durable record.
    """

    def __init__(
        self,
        outbox: DeliveryOutbox,
        transport: AccountAwareTransport | Callable[[], AccountAwareTransport],
        *,
        worker_id: str = "outbox-worker",
        idle_wait_seconds: float = 1.0,
    ) -> None:
        if type(outbox) is not DeliveryOutbox:
            raise ValueError("outbox must be a DeliveryOutbox")
        if (
            type(worker_id) is not str
            or not worker_id
            or type(idle_wait_seconds) not in (int, float)
            or idle_wait_seconds <= 0
        ):
            raise ValueError("worker inputs are invalid")
        if not callable(getattr(transport, "send", None)) and not callable(transport):
            raise ValueError("transport must send or be a transport factory")
        self._outbox = outbox
        self._transport = transport
        self._worker_id = worker_id
        self._idle_wait_seconds = float(idle_wait_seconds)
        self._wakeup = asyncio.Event()
        self._stopped = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def wake(self) -> None:
        self._wakeup.set()

    def start(self) -> asyncio.Task[None]:
        task = self._task
        if task is not None and not task.done():
            return task
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            raise RuntimeError("outbox worker requires a running event loop") from None
        self._stopped.clear()
        task = loop.create_task(self.run(), name=f"sylanne-{self._worker_id}")
        self._task = task
        return task

    def _current_transport(self) -> AccountAwareTransport | None:
        candidate = self._transport
        if not callable(getattr(candidate, "send", None)):
            try:
                candidate = candidate()  # type: ignore[operator]
            except Exception:
                return None
        return candidate if callable(getattr(candidate, "send", None)) else None

    async def _wait_for_wake(self) -> None:
        if self._wakeup.is_set():
            self._wakeup.clear()
            return
        try:
            await asyncio.wait_for(
                self._wakeup.wait(),
                timeout=self._idle_wait_seconds,
            )
        except asyncio.TimeoutError:
            pass
        finally:
            self._wakeup.clear()

    async def run(self) -> None:
        while not self._stopped.is_set():
            transport = self._current_transport()
            if transport is None:
                await self._wait_for_wake()
                continue
            try:
                item = await self._outbox.dispatch_one(
                    transport,
                    worker_id=self._worker_id,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                item = None
            if item is not None:
                if item.status is DeliveryStatus.FAILED_RETRYABLE:
                    await self._wait_for_wake()
                else:
                    await asyncio.sleep(0)
                continue
            await self._wait_for_wake()

    async def stop(self) -> None:
        self._stopped.set()
        self.wake()
        task = self._task
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


__all__ = [
    "AccountAwareTransport",
    "AstrBotAccountAwareTransport",
    "DeliveryEnvelope",
    "DeliveryClaim",
    "DeliveryItem",
    "DeliveryLeaseRejected",
    "DeliveryNotSent",
    "DeliveryOutbox",
    "DeliveryOutboxWorker",
    "DeliveryReceipt",
    "DeliverySnapshot",
    "DeliveryState",
    "DeliveryStateError",
    "DeliveryStatus",
    "ProcessLocalDeliveryTurn",
    "ReactiveDeliveryCoordinator",
    "ScopedDeliveryGateway",
    "UnverifiedDeliveryIntent",
]
