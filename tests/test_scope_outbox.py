from __future__ import annotations

import asyncio
import multiprocessing as mp
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import get_type_hints

import pytest

from sylanne_alpha.proactive_bridge import ProactiveBridge
from sylanne_alpha.proactive_scheduler import ProactiveScheduler
from sylanne_alpha.scope_contracts import (
    BotRef,
    PersonaRevisionRef,
    ResolvedTransportScope,
    SessionRef,
    SessionScope,
)
from sylanne_alpha.scope_delivery import (
    AccountAwareTransport,
    AstrBotAccountAwareTransport,
    DeliveryNotSent,
    DeliveryOutbox,
    DeliveryOutboxWorker,
    DeliveryReceipt,
    DeliveryStatus,
    ScopedDeliveryGateway,
    UnverifiedDeliveryIntent,
)
from sylanne_alpha.scope_identity import (
    AdapterAccountProof,
    BotBinding,
    CurrentAdapterAccountProof,
    ScopeResolver,
    load_or_create_scope_identity_key,
)
from sylanne_alpha.scope_repository import ScopeRepository, ScopedPersistenceGateway
from sylanne_alpha.scope_runtime import ScopeRuntimeRegistry
from sylanne_alpha.session_catalog import ProtectedDeliveryBinding, SessionCatalog
from tests.scope_fixtures import scope_storage_token


_PLATFORM = "test-platform"
_SELF_ID = "test-account"
_SECOND_PLATFORM = "test-platform-b"
_SECOND_SELF_ID = "test-account-b"
_SESSION = "test:FriendMessage:42"
_TARGET = "test-target-address"
_PROOF_DIGEST = "proof-set-v1"
_NOW_MS = 1_000
_EXPIRES_AT_MS = 10_000


class _StaticProofs:
    def __init__(self, current: CurrentAdapterAccountProof | None) -> None:
        self.current_value = current
        self._by_platform: dict[str, CurrentAdapterAccountProof] = {}

    def current(self, platform_id: str) -> CurrentAdapterAccountProof | None:
        current = self.current_value
        if current is not None and current.proof.platform_id == platform_id:
            return current
        return self._by_platform.get(platform_id)


class _Transport:
    def __init__(self) -> None:
        self.addressable = True
        self.behavior = "confirm"
        self.calls: list[str] = []
        self.normal_return: object = None
        self.receipt_delivery_id: str | None = None

    def can_address(self, _delivery_ref) -> bool:
        return self.addressable

    async def send(self, delivery_ref, _text: str) -> object:
        self.calls.append(delivery_ref.delivery_id)
        if self.behavior == "send_then_lose_receipt":
            raise RuntimeError("receipt lost after adapter accepted send")
        if self.behavior == "fail_before_send":
            raise RuntimeError("adapter proved no send")
        if self.behavior == "ordinary_return":
            return self.normal_return
        return DeliveryReceipt(
            delivery_id=self.receipt_delivery_id or delivery_ref.delivery_id
        )


def test_transport_protocol_treats_adapter_result_as_unverified_object() -> None:
    assert get_type_hints(AccountAwareTransport.send)["return"] is object


def _transport_scope(
    bot: BotRef,
    *,
    session_token: str = "session_v1_outbox",
) -> ResolvedTransportScope:
    return ResolvedTransportScope(
        bot_ref=bot,
        session_ref=SessionRef(token=session_token, bot_ref=bot, generation=0),
        identity_quality="event_self_id",
        private_scope_enabled=True,
        disabled_reason=None,
    )


def _scope(
    bot: BotRef,
    persona_token: str,
    *,
    session_token: str = "session_v1_outbox",
) -> SessionScope:
    transport = _transport_scope(bot, session_token=session_token)
    return SessionScope(
        bot_ref=bot,
        persona_ref=PersonaRevisionRef(
            token=persona_token,
            bot_ref=bot,
            persona_id_digest="a" * 64,
            source_fingerprint=("b" if persona_token.endswith("a") else "c") * 64,
            lifecycle_generation=0,
        ),
        session_ref=transport.session_ref,
        storage_token=scope_storage_token(f"outbox-{persona_token}"),
        scope_generation=0,
    )


def _binding(
    *,
    adapter_capability: str = "proactive",
    platform_id: str = _PLATFORM,
    self_id: str = _SELF_ID,
) -> ProtectedDeliveryBinding:
    return ProtectedDeliveryBinding(
        platform_id=platform_id,
        self_id=self_id,
        message_session=_SESSION,
        target_address=_TARGET,
        adapter_capability=adapter_capability,
        account_proof_digest=_PROOF_DIGEST,
        account_proof_generation=0,
        account_proof_expires_at_ms=_EXPIRES_AT_MS,
        binding_generation=0,
    )


def _current_proof(
    bot: BotRef,
    *,
    platform_id: str = _PLATFORM,
) -> CurrentAdapterAccountProof:
    return CurrentAdapterAccountProof(
        proof=AdapterAccountProof(
            platform_id=platform_id,
            bot_ref=bot,
            proof_generation=0,
            verified_at_ms=0,
            expires_at_ms=_EXPIRES_AT_MS,
            account_set_digest=_PROOF_DIGEST,
            account_count=1,
        ),
        current_account_set_digest=_PROOF_DIGEST,
        current_proof_generation=0,
    )


def _registered_bot(
    catalog: SessionCatalog,
    root: Path,
    *,
    platform_id: str = _PLATFORM,
    self_id: str = _SELF_ID,
) -> BotRef:
    generation = catalog.binding_generation(platform_id, self_id)
    key = load_or_create_scope_identity_key(root / "identity.key")
    return key.bot_ref(
        BotBinding(platform_id=platform_id, self_id=self_id),
        generation,
    )


def _freeze_scope(
    catalog: SessionCatalog,
    scope: SessionScope,
    *,
    adapter_capability: str = "proactive",
    platform_id: str = _PLATFORM,
    self_id: str = _SELF_ID,
) -> None:
    catalog.freeze_persona(
        catalog.begin_turn(
            _transport_scope(scope.bot_ref, session_token=scope.session_ref.token),
            _binding(
                adapter_capability=adapter_capability,
                platform_id=platform_id,
                self_id=self_id,
            ),
        ),
        scope,
    )


@pytest.fixture
def outbox_context(tmp_path: Path):
    repository = ScopeRepository(tmp_path / "scope-v1")
    bootstrap = SessionCatalog(repository, clock_ms=lambda: _NOW_MS)
    bot = _registered_bot(bootstrap, repository.root)
    proofs = _StaticProofs(_current_proof(bot))
    catalog = SessionCatalog(
        repository,
        account_proofs=proofs,
        clock_ms=lambda: _NOW_MS,
    )
    scope = repository.create_scope(
        _scope(bot, "persona_v1_outbox_a"),
        expected_absent=True,
    )
    _freeze_scope(catalog, scope)
    return SimpleNamespace(
        repository=repository,
        catalog=catalog,
        proofs=proofs,
        bot=bot,
        scope=scope,
    )


def _issued_draft(
    context: SimpleNamespace,
    *,
    text: str = "hello",
    idempotent: bool = False,
    scope: SessionScope | None = None,
):
    return context.catalog.issue_proactive_intent(
        context.scope if scope is None else scope,
        text=text,
        idempotent=idempotent,
        expires_at_ms=_EXPIRES_AT_MS,
    )


def _second_bot_scope(outbox_context) -> tuple[BotRef, SessionScope]:
    bot = _registered_bot(
        outbox_context.catalog,
        outbox_context.repository.root,
        platform_id=_SECOND_PLATFORM,
        self_id=_SECOND_SELF_ID,
    )
    outbox_context.proofs._by_platform[_SECOND_PLATFORM] = _current_proof(
        bot,
        platform_id=_SECOND_PLATFORM,
    )
    scope = outbox_context.repository.create_scope(
        _scope(bot, "persona_v1_outbox_c"),
        expected_absent=True,
    )
    _freeze_scope(
        outbox_context.catalog,
        scope,
        platform_id=_SECOND_PLATFORM,
        self_id=_SECOND_SELF_ID,
    )
    return bot, scope


def _outbox(context: SimpleNamespace) -> DeliveryOutbox:
    return DeliveryOutbox(
        context.repository,
        context.catalog,
        clock_ms=lambda: _NOW_MS,
    )


def _hold_repository_lock(root: str, ready, release) -> None:
    repository = ScopeRepository(root)
    with repository.transaction():
        ready.set()
        release.wait(10)


def test_delivery_diagnostics_are_exact_scope_generation_bound_and_redacted(
    outbox_context,
) -> None:
    outbox = _outbox(outbox_context)
    pending = outbox.enqueue(_issued_draft(outbox_context, text="pending-secret"))
    failed = outbox.enqueue(_issued_draft(outbox_context, text="failed-secret"))
    unknown = outbox.enqueue(_issued_draft(outbox_context, text="unknown-secret"))
    suppressed = outbox.enqueue(_issued_draft(outbox_context, text="suppressed-secret"))

    failed_claim = outbox.claim(failed.delivery_ref, worker_id="worker-failed")
    assert failed_claim is not None
    failed_dispatch = outbox.mark_dispatching(failed_claim, worker_id="worker-failed")
    assert failed_dispatch is not None
    assert outbox.settle(
        failed_dispatch,
        worker_id="worker-failed",
        status=DeliveryStatus.FAILED_RETRYABLE,
        reason="adapter_rejected_before_send",
    ) is not None

    unknown_claim = outbox.claim(unknown.delivery_ref, worker_id="worker-unknown")
    assert unknown_claim is not None
    unknown_dispatch = outbox.mark_dispatching(unknown_claim, worker_id="worker-unknown")
    assert unknown_dispatch is not None
    assert outbox.settle(
        unknown_dispatch,
        worker_id="worker-unknown",
        status=DeliveryStatus.OUTCOME_UNKNOWN,
    ) is not None
    assert outbox.suppress(suppressed, reason="account_unavailable") is not None

    _other_bot, other_scope = _second_bot_scope(outbox_context)
    outbox.enqueue(_issued_draft(outbox_context, text="other-bot-secret", scope=other_scope))

    diagnostics = outbox.diagnostics(outbox_context.scope)
    assert diagnostics == {
        "pending": 1,
        "failed_retryable": 1,
        "outcome_unknown": 1,
        "suppressed": 1,
    }
    assert set(diagnostics) <= {
        "pending",
        "failed_retryable",
        "outcome_unknown",
        "suppressed",
        "last_reason",
    }
    assert "secret" not in repr(diagnostics)
    assert pending.delivery_ref.token not in repr(diagnostics)

    replacement = outbox_context.repository.create_scope(
        _scope(outbox_context.bot, "persona_v1_outbox_b"),
        expected_absent=True,
    )
    _freeze_scope(outbox_context.catalog, replacement)
    assert outbox.diagnostics(outbox_context.scope) is None
    assert outbox.diagnostics(replacement) == {
        "pending": 0,
        "failed_retryable": 0,
        "outcome_unknown": 0,
        "suppressed": 0,
    }


def test_delivery_diagnostics_and_state_dto_fail_fast_when_repository_is_busy(
    outbox_context,
) -> None:
    from sylanne_alpha.webui_routes import scoped_api_payload

    outbox = _outbox(outbox_context)
    outbox.enqueue(_issued_draft(outbox_context, text="private-lock-probe"))
    process_context = mp.get_context("spawn")
    ready = process_context.Event()
    release = process_context.Event()
    holder = process_context.Process(
        target=_hold_repository_lock,
        args=(str(outbox_context.repository.root), ready, release),
    )
    holder.start()
    assert ready.wait(10)

    class Authorization:
        scope = outbox_context.scope

        @staticmethod
        def public_payload() -> dict[str, object]:
            return {"ok": True}

    try:
        started = time.perf_counter()
        assert outbox.diagnostics(outbox_context.scope) is None
        diagnostics_elapsed = time.perf_counter() - started

        started = time.perf_counter()
        payload = asyncio.run(
            scoped_api_payload(
                SimpleNamespace(_scope_delivery_outbox=outbox),
                Authorization(),
                "state",
            )
        )
        state_elapsed = time.perf_counter() - started
    finally:
        release.set()
        holder.join(10)
        if holder.is_alive():
            holder.terminate()
            holder.join(5)

    assert holder.exitcode == 0
    assert diagnostics_elapsed < 0.25
    assert state_elapsed < 0.25
    assert payload["delivery"] == {
        "pending": 0,
        "failed_retryable": 0,
        "outcome_unknown": 0,
        "suppressed": 0,
    }
    assert "private-lock-probe" not in repr(payload)


def _claim_in_subprocess(
    root: str,
    delivery_ref,
    current_proof: CurrentAdapterAccountProof,
    worker_id: str,
    start,
    results,
) -> None:
    start.wait(10)
    repository = ScopeRepository(root)
    catalog = SessionCatalog(
        repository,
        account_proofs=_StaticProofs(current_proof),
        clock_ms=lambda: _NOW_MS,
    )
    claim = DeliveryOutbox(repository, catalog, clock_ms=lambda: _NOW_MS).claim(
        delivery_ref,
        worker_id=worker_id,
    )
    results.put(claim is not None)


def test_unverified_or_forged_intent_has_zero_outbox_writes(outbox_context) -> None:
    outbox = _outbox(outbox_context)
    path = outbox_context.repository.delivery_outbox_path(outbox_context.scope)

    with pytest.raises(UnverifiedDeliveryIntent):
        outbox.enqueue(outbox_context.scope)
    assert not path.exists()

    issued = _issued_draft(outbox_context)
    with pytest.raises(UnverifiedDeliveryIntent):
        outbox.enqueue(replace(issued, text="forged"))
    assert not path.exists()


def test_default_account_proof_provider_fails_closed(outbox_context) -> None:
    unavailable_catalog = SessionCatalog(
        outbox_context.repository,
        clock_ms=lambda: _NOW_MS,
    )

    with pytest.raises(ValueError, match="not issuable"):
        unavailable_catalog.issue_proactive_intent(
            outbox_context.scope,
            text="hello",
            idempotent=True,
            expires_at_ms=_EXPIRES_AT_MS,
        )
    assert not outbox_context.repository.delivery_outbox_path(
        outbox_context.scope
    ).exists()


def test_expired_item_becomes_terminal_without_sending(outbox_context) -> None:
    item = _outbox(outbox_context).enqueue(_issued_draft(outbox_context))
    expired_outbox = DeliveryOutbox(
        outbox_context.repository,
        outbox_context.catalog,
        clock_ms=lambda: _EXPIRES_AT_MS,
    )

    assert expired_outbox.claim(item.delivery_ref, worker_id="worker-a") is None
    assert expired_outbox.get(item.delivery_ref).status is DeliveryStatus.EXPIRED


def test_cross_process_claim_cas_allows_exactly_one_worker(outbox_context) -> None:
    outbox = _outbox(outbox_context)
    item = outbox.enqueue(_issued_draft(outbox_context, idempotent=True))
    process_context = mp.get_context("spawn")
    start = process_context.Event()
    results = process_context.Queue()
    workers = [
        process_context.Process(
            target=_claim_in_subprocess,
            args=(
                str(outbox_context.repository.root),
                item.delivery_ref,
                outbox_context.proofs.current_value,
                worker_id,
                start,
                results,
            ),
        )
        for worker_id in ("worker-a", "worker-b")
    ]
    for worker in workers:
        worker.start()
    start.set()
    outcomes = [results.get(timeout=15) for _ in workers]
    for worker in workers:
        worker.join(timeout=15)
        assert worker.exitcode == 0

    assert outcomes.count(True) == 1
    assert outbox.get(item.delivery_ref).status is DeliveryStatus.CLAIMED


def test_crash_before_send_returns_claimed_item_to_pending(outbox_context) -> None:
    outbox = _outbox(outbox_context)
    item = outbox.enqueue(_issued_draft(outbox_context))
    assert outbox.claim(item.delivery_ref, worker_id="worker-a") is not None

    recovered = _outbox(outbox_context).recover_after_restart()

    assert recovered[item.delivery_ref].status is DeliveryStatus.PENDING


@pytest.mark.parametrize(
    ("adapter_capability", "idempotent", "expected"),
    [
        ("proactive", False, DeliveryStatus.OUTCOME_UNKNOWN),
        ("proactive", True, DeliveryStatus.OUTCOME_UNKNOWN),
        ("proactive_idempotent_v1", True, DeliveryStatus.FAILED_RETRYABLE),
    ],
)
def test_dispatching_crash_has_capability_safe_recovery(
    outbox_context,
    adapter_capability: str,
    idempotent: bool,
    expected: DeliveryStatus,
) -> None:
    outbox = _outbox(outbox_context)
    _freeze_scope(
        outbox_context.catalog,
        outbox_context.scope,
        adapter_capability=adapter_capability,
    )
    item = outbox.enqueue(_issued_draft(outbox_context, idempotent=idempotent))
    claim = outbox.claim(item.delivery_ref, worker_id="worker-a")
    assert claim is not None
    assert outbox.mark_dispatching(claim, worker_id="worker-a") is not None

    recovered = _outbox(outbox_context).recover_after_restart()

    assert recovered[item.delivery_ref].status is expected
    if expected is DeliveryStatus.FAILED_RETRYABLE:
        retry = outbox.claim(item.delivery_ref, worker_id="worker-b")
        assert retry is not None
        assert retry.delivery_id == item.delivery_id
    else:
        assert outbox.claim(item.delivery_ref, worker_id="worker-b") is None


def test_non_idempotent_receipt_loss_is_never_automatically_retried(outbox_context) -> None:
    async def scenario() -> None:
        outbox = _outbox(outbox_context)
        item = outbox.enqueue(_issued_draft(outbox_context, idempotent=False))
        transport = _Transport()
        transport.behavior = "send_then_lose_receipt"

        await outbox.dispatch_one(transport, outbox_context.bot, worker_id="worker-a")
        await outbox.dispatch_one(transport, outbox_context.bot, worker_id="worker-b")

        assert outbox.get(item.delivery_ref).status is DeliveryStatus.OUTCOME_UNKNOWN
        assert transport.calls == [item.delivery_id]

    asyncio.run(scenario())


@pytest.mark.parametrize("ordinary_return", [None, "accepted", object()])
def test_normal_transport_return_is_never_a_confirmed_receipt(
    outbox_context, ordinary_return: object
) -> None:
    async def scenario() -> None:
        outbox = _outbox(outbox_context)
        item = outbox.enqueue(_issued_draft(outbox_context, idempotent=True))
        transport = _Transport()
        transport.behavior = "ordinary_return"
        transport.normal_return = ordinary_return

        await outbox.dispatch_one(transport, outbox_context.bot, worker_id="worker-a")
        await outbox.dispatch_one(transport, outbox_context.bot, worker_id="worker-b")

        assert outbox.get(item.delivery_ref).status is DeliveryStatus.OUTCOME_UNKNOWN
        assert transport.calls == [item.delivery_id]

    asyncio.run(scenario())


def test_confirmed_receipt_must_bind_the_issued_delivery_id(outbox_context) -> None:
    async def scenario() -> None:
        outbox = _outbox(outbox_context)
        item = outbox.enqueue(_issued_draft(outbox_context, idempotent=True))
        transport = _Transport()
        transport.receipt_delivery_id = "other-delivery"

        await outbox.dispatch_one(transport, outbox_context.bot, worker_id="worker-a")

        assert outbox.get(item.delivery_ref).status is DeliveryStatus.OUTCOME_UNKNOWN
        assert transport.calls == [item.delivery_id]

    asyncio.run(scenario())


def test_idempotent_retry_reuses_the_issued_delivery_id(outbox_context) -> None:
    async def scenario() -> None:
        outbox = _outbox(outbox_context)
        _freeze_scope(
            outbox_context.catalog,
            outbox_context.scope,
            adapter_capability="proactive_idempotent_v1",
        )
        item = outbox.enqueue(_issued_draft(outbox_context, idempotent=True))
        transport = _Transport()
        transport.behavior = "send_then_lose_receipt"

        await outbox.dispatch_one(transport, outbox_context.bot, worker_id="worker-a")
        transport.behavior = "confirm"
        await outbox.dispatch_one(transport, outbox_context.bot, worker_id="worker-b")

        assert outbox.get(item.delivery_ref).status is DeliveryStatus.SENT_CONFIRMED
        assert transport.calls == [item.delivery_id, item.delivery_id]

    asyncio.run(scenario())


def test_plain_proactive_adapter_never_retries_an_unknown_send(outbox_context) -> None:
    async def scenario() -> None:
        outbox = _outbox(outbox_context)
        item = outbox.enqueue(_issued_draft(outbox_context, idempotent=True))
        transport = _Transport()
        transport.behavior = "send_then_lose_receipt"

        await outbox.dispatch_one(transport, outbox_context.bot, worker_id="worker-a")
        await outbox.dispatch_one(transport, outbox_context.bot, worker_id="worker-b")

        assert outbox.get(item.delivery_ref).status is DeliveryStatus.OUTCOME_UNKNOWN
        assert transport.calls == [item.delivery_id]

    asyncio.run(scenario())


def test_proven_pre_send_failure_retries_even_when_non_idempotent(outbox_context) -> None:
    class _PreSendFailureTransport(_Transport):
        def __init__(self) -> None:
            super().__init__()
            self.attempt = 0

        async def send(self, delivery_ref, _text: str) -> object:
            self.calls.append(delivery_ref.delivery_id)
            self.attempt += 1
            if self.attempt == 1:
                raise DeliveryNotSent("adapter rejected before send")
            return DeliveryReceipt(delivery_ref.delivery_id)

    async def scenario() -> None:
        outbox = _outbox(outbox_context)
        item = outbox.enqueue(_issued_draft(outbox_context, idempotent=False))
        transport = _PreSendFailureTransport()

        first = await outbox.dispatch_one(
            transport,
            outbox_context.bot,
            worker_id="worker-a",
        )
        assert first is not None
        assert first.status is DeliveryStatus.FAILED_RETRYABLE
        assert first.reason == "adapter_rejected_before_send"

        second = await outbox.dispatch_one(
            transport,
            outbox_context.bot,
            worker_id="worker-a",
        )
        assert second is not None
        assert second.status is DeliveryStatus.SENT_CONFIRMED
        assert transport.calls == [item.delivery_id, item.delivery_id]

    asyncio.run(scenario())


def test_second_startup_never_replays_a_live_plain_dispatch(outbox_context) -> None:
    class _PausedTransport(_Transport):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()
            self.release = asyncio.Event()

        async def send(self, delivery_ref, _text: str) -> object:
            self.calls.append(delivery_ref.delivery_id)
            self.started.set()
            await self.release.wait()
            return DeliveryReceipt(delivery_ref.delivery_id)

    async def scenario() -> None:
        first = _outbox(outbox_context)
        second = _outbox(outbox_context)
        item = first.enqueue(_issued_draft(outbox_context, idempotent=True))
        first_transport = _PausedTransport()
        second_transport = _Transport()
        first_task = asyncio.create_task(
            first.dispatch_one(
                first_transport,
                outbox_context.bot,
                worker_id="worker-a",
            )
        )
        await first_transport.started.wait()

        recovered = second.recover_after_restart()
        assert recovered[item.delivery_ref].status is DeliveryStatus.OUTCOME_UNKNOWN
        assert (
            await second.dispatch_one(
                second_transport,
                outbox_context.bot,
                worker_id="worker-b",
            )
            is None
        )
        assert second_transport.calls == []

        first_transport.release.set()
        await first_task
        assert first.get(item.delivery_ref).status is DeliveryStatus.OUTCOME_UNKNOWN

    asyncio.run(scenario())


def test_account_change_or_unaddressable_transport_suppresses_without_send(
    outbox_context,
) -> None:
    async def scenario() -> None:
        outbox = _outbox(outbox_context)
        item = outbox.enqueue(_issued_draft(outbox_context, idempotent=True))
        transport = _Transport()
        transport.addressable = False

        await outbox.dispatch_one(transport, outbox_context.bot, worker_id="worker-a")

        assert outbox.get(item.delivery_ref).status is DeliveryStatus.SUPPRESSED
        assert transport.calls == []

    asyncio.run(scenario())


def test_proof_change_or_multi_account_suppresses_before_claim(outbox_context) -> None:
    outbox = _outbox(outbox_context)
    item = outbox.enqueue(_issued_draft(outbox_context, idempotent=True))
    live = outbox_context.proofs.current_value
    assert live is not None
    outbox_context.proofs.current_value = CurrentAdapterAccountProof(
        proof=replace(live.proof, account_count=2),
        current_account_set_digest=live.current_account_set_digest,
        current_proof_generation=live.current_proof_generation,
    )

    assert outbox.claim(item.delivery_ref, worker_id="worker-a") is None
    assert outbox.get(item.delivery_ref).status is DeliveryStatus.SUPPRESSED


def test_account_change_at_the_send_boundary_suppresses_before_send(outbox_context) -> None:
    class _ChangingTransport(_Transport):
        def __init__(self) -> None:
            super().__init__()
            self.address_checks = 0

        def can_address(self, delivery_ref) -> bool:
            self.address_checks += 1
            if self.address_checks == 2:
                current = outbox_context.proofs.current_value
                assert current is not None
                outbox_context.proofs.current_value = CurrentAdapterAccountProof(
                    proof=replace(current.proof, account_count=2),
                    current_account_set_digest=current.current_account_set_digest,
                    current_proof_generation=current.current_proof_generation,
                )
            return super().can_address(delivery_ref)

    async def scenario() -> None:
        outbox = _outbox(outbox_context)
        item = outbox.enqueue(_issued_draft(outbox_context, idempotent=True))
        transport = _ChangingTransport()

        await outbox.dispatch_one(transport, outbox_context.bot, worker_id="worker-a")

        assert outbox.get(item.delivery_ref).status is DeliveryStatus.SUPPRESSED
        assert transport.calls == []

    asyncio.run(scenario())


def test_account_change_after_send_leaves_the_outcome_unknown(outbox_context) -> None:
    class _ReceiptChangingTransport(_Transport):
        async def send(self, delivery_ref, text: str) -> str:
            receipt = await super().send(delivery_ref, text)
            current = outbox_context.proofs.current_value
            assert current is not None
            outbox_context.proofs.current_value = CurrentAdapterAccountProof(
                proof=replace(current.proof, account_count=2),
                current_account_set_digest=current.current_account_set_digest,
                current_proof_generation=current.current_proof_generation,
            )
            return receipt

    async def scenario() -> None:
        outbox = _outbox(outbox_context)
        item = outbox.enqueue(_issued_draft(outbox_context, idempotent=True))
        transport = _ReceiptChangingTransport()

        await outbox.dispatch_one(transport, outbox_context.bot, worker_id="worker-a")

        assert outbox.get(item.delivery_ref).status is DeliveryStatus.OUTCOME_UNKNOWN
        assert transport.calls == [item.delivery_id]

    asyncio.run(scenario())


def test_persona_a_to_b_to_a_never_revives_an_old_lease(outbox_context) -> None:
    async def scenario() -> None:
        repository = outbox_context.repository
        catalog = outbox_context.catalog
        outbox = DeliveryOutbox(repository, catalog, clock_ms=lambda: _NOW_MS)
        old = outbox.enqueue(_issued_draft(outbox_context, idempotent=True))
        scope_b = repository.create_scope(
            _scope(outbox_context.bot, "persona_v1_outbox_b"),
            expected_absent=True,
        )
        _freeze_scope(catalog, scope_b)
        transport = _Transport()

        await outbox.dispatch_one(transport, outbox_context.bot, worker_id="worker-a")
        _freeze_scope(catalog, outbox_context.scope)
        await outbox.dispatch_one(transport, outbox_context.bot, worker_id="worker-b")

        assert outbox.get(old.delivery_ref).status is DeliveryStatus.SUPPRESSED
        assert transport.calls == []
        fresh = _issued_draft(outbox_context, text="fresh", idempotent=True)
        fresh_item = outbox.enqueue(fresh)
        await outbox.dispatch_one(transport, outbox_context.bot, worker_id="worker-c")
        assert outbox.get(fresh_item.delivery_ref).status is DeliveryStatus.SENT_CONFIRMED
        assert transport.calls == [fresh_item.delivery_id]

    asyncio.run(scenario())


def test_persona_a_to_b_to_a_during_send_makes_old_receipt_outcome_unknown(
    outbox_context,
) -> None:
    class _TakeoverDuringSendTransport(_Transport):
        def __init__(self) -> None:
            super().__init__()
            self._sends = 0

        async def send(self, delivery_ref, _text: str) -> object:
            self.calls.append(delivery_ref.delivery_id)
            self._sends += 1
            await asyncio.sleep(0)
            if self._sends != 1:
                return DeliveryReceipt(delivery_ref.delivery_id)
            scope_b = outbox_context.repository.create_scope(
                _scope(outbox_context.bot, "persona_v1_outbox_b"),
                expected_absent=True,
            )
            _freeze_scope(outbox_context.catalog, scope_b)
            _freeze_scope(outbox_context.catalog, outbox_context.scope)
            return DeliveryReceipt(delivery_ref.delivery_id)

    async def scenario() -> None:
        outbox = _outbox(outbox_context)
        old = outbox.enqueue(_issued_draft(outbox_context, idempotent=True))
        transport = _TakeoverDuringSendTransport()

        await outbox.dispatch_one(transport, outbox_context.bot, worker_id="worker-a")

        assert outbox.get(old.delivery_ref).status is DeliveryStatus.OUTCOME_UNKNOWN
        assert transport.calls == [old.delivery_id]

        fresh = outbox.enqueue(
            _issued_draft(outbox_context, text="fresh", idempotent=True)
        )
        await outbox.dispatch_one(transport, outbox_context.bot, worker_id="worker-b")

        assert outbox.get(fresh.delivery_ref).status is DeliveryStatus.SENT_CONFIRMED
        assert transport.calls == [old.delivery_id, fresh.delivery_id]

    asyncio.run(scenario())


def test_scoped_bridge_never_uses_the_legacy_direct_send_path(outbox_context) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    session_runtime = registry.exact_session(outbox_context.scope)
    binding = SimpleNamespace(
        scope=outbox_context.scope,
        session_runtime=session_runtime,
        relation_runtime=None,
    )

    class _LegacyPlugin:
        def __init__(self) -> None:
            self.calls = 0
            self.session_override_manager = object()

        async def check_and_chat(self, _origin: str) -> None:
            self.calls += 1

    legacy = _LegacyPlugin()
    plugin = SimpleNamespace(
        _scope_runtime_registry=registry,
        _bound_runtime=lambda: binding,
        context=SimpleNamespace(get_registered_star=lambda _name: legacy),
    )

    result = asyncio.run(
        ProactiveBridge(plugin).dispatch(outbox_context.scope.storage_token, "hello")
    )

    assert result == {"dispatched": False, "reason": "scoped_outbox_required"}
    assert legacy.calls == 0


def test_scoped_scheduler_stops_before_legacy_dispatch_request(outbox_context) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    session_runtime = registry.exact_session(outbox_context.scope)
    binding = SimpleNamespace(
        scope=outbox_context.scope,
        session_runtime=session_runtime,
        relation_runtime=None,
    )
    plugin = SimpleNamespace(_bound_runtime=lambda: binding)
    scheduler = ProactiveScheduler(plugin)

    def _legacy_dispatch_request_forbidden(*_args, **_kwargs):
        raise AssertionError("scoped scheduler must not prepare a legacy dispatch")

    scheduler.build_dispatch_request = _legacy_dispatch_request_forbidden
    result = asyncio.run(
        scheduler.request_dispatch(session_key=outbox_context.scope.storage_token)
    )

    assert result == {
        "dispatched": False,
        "reason": "scoped_outbox_required",
        "session_key": outbox_context.scope.storage_token,
    }


def test_scope_resolver_passes_the_live_proof_provider_to_its_catalog(
    tmp_path: Path,
) -> None:
    proofs = _StaticProofs(None)

    resolver = ScopeResolver.for_context(
        SimpleNamespace(),
        tmp_path / "scope-v1",
        account_proofs=proofs,
    )

    assert resolver._account_proofs is proofs
    assert resolver.catalog._account_proofs is proofs

    default_resolver = ScopeResolver.for_context(
        SimpleNamespace(),
        tmp_path / "default-scope-v1",
    )
    assert default_resolver._account_proofs is default_resolver.catalog._account_proofs


def test_delivery_binding_requires_live_proof_and_platform_proactive_capability(
    tmp_path: Path,
) -> None:
    class _Session:
        platform_id = _PLATFORM

        def __str__(self) -> str:
            return _SESSION

    class _Event:
        session = _Session()

        def get_platform_id(self) -> str:
            return _PLATFORM

        def get_self_id(self) -> str:
            return _SELF_ID

    class _Platform:
        def __init__(self, enabled: bool) -> None:
            self.enabled = enabled

        def meta(self):
            return SimpleNamespace(support_proactive_message=self.enabled)

    platform = _Platform(enabled=True)
    context = SimpleNamespace(get_platform_inst=lambda _platform_id: platform)
    proofs = _StaticProofs(None)
    resolver = ScopeResolver.for_context(
        context,
        tmp_path / "scope-v1",
        account_proofs=proofs,
    )
    event = _Event()
    transport = resolver.resolve_transport(event)
    assert transport.bot_ref is not None
    now_ms = time.time_ns() // 1_000_000
    proofs.current_value = CurrentAdapterAccountProof(
        proof=AdapterAccountProof(
            platform_id=_PLATFORM,
            bot_ref=transport.bot_ref,
            proof_generation=0,
            verified_at_ms=now_ms - 1,
            expires_at_ms=now_ms + 10_000,
            account_set_digest=_PROOF_DIGEST,
            account_count=1,
        ),
        current_account_set_digest=_PROOF_DIGEST,
        current_proof_generation=0,
    )

    binding = resolver.delivery_binding(event, transport)

    assert binding is not None
    assert binding.adapter_capability == "proactive_send_v1"
    assert binding.account_proof_digest == _PROOF_DIGEST

    platform.enabled = False
    assert resolver.delivery_binding(event, transport).adapter_capability == "reactive_only"


def test_astrbot_transport_returns_ordinary_adapter_results_without_forging_receipts(
    outbox_context,
) -> None:
    class _Chain:
        def __init__(self) -> None:
            self.text = ""

        def message(self, text: str):
            self.text = text
            return self

    class _Platform:
        def meta(self):
            return SimpleNamespace(support_proactive_message=True)

    sent: list[tuple[str, _Chain]] = []

    class _Context:
        def get_platform_inst(self, platform_id: str):
            assert platform_id == _PLATFORM
            return _Platform()

        def send_message(self, session: str, chain: _Chain) -> bool:
            sent.append((session, chain))
            return True

    async def scenario() -> None:
        draft = _issued_draft(outbox_context)
        delivery_ref = replace(
            draft.delivery_ref,
            adapter_capability="proactive_send_v1",
        )
        transport = AstrBotAccountAwareTransport(
            _Context(),
            outbox_context.proofs,
            message_chain_factory=_Chain,
            clock_ms=lambda: _NOW_MS,
        )

        assert transport.can_address(delivery_ref) is True
        assert await transport.send(delivery_ref, "hello") is True
        assert sent[0][0] == _TARGET
        assert sent[0][1].text == "hello"

    asyncio.run(scenario())


def test_astrbot_transport_raises_only_for_a_proven_false_before_send(
    outbox_context,
) -> None:
    class _Platform:
        def meta(self):
            return SimpleNamespace(support_proactive_message=True)

    class _Context:
        def get_platform_inst(self, _platform_id: str):
            return _Platform()

        def send_message(self, _session: str, _chain: object) -> bool:
            return False

    async def scenario() -> None:
        draft = _issued_draft(outbox_context)
        delivery_ref = replace(
            draft.delivery_ref,
            adapter_capability="proactive_send_v1",
        )
        transport = AstrBotAccountAwareTransport(
            _Context(),
            outbox_context.proofs,
            clock_ms=lambda: _NOW_MS,
        )

        with pytest.raises(DeliveryNotSent):
            await transport.send(delivery_ref, "hello")

    asyncio.run(scenario())


def test_cancelling_after_dispatch_boundary_keeps_dispatching_durable(
    outbox_context,
) -> None:
    class _CancellingTransport(_Transport):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()
            self.release = asyncio.Event()

        async def send(self, delivery_ref, text: str) -> object:
            self.calls.append(delivery_ref.delivery_id)
            self.started.set()
            await self.release.wait()
            return DeliveryReceipt(delivery_ref.delivery_id)

    async def scenario() -> None:
        outbox = _outbox(outbox_context)
        item = outbox.enqueue(_issued_draft(outbox_context, idempotent=True))
        transport = _CancellingTransport()
        task = asyncio.create_task(
            outbox.dispatch_one(
                transport,
                outbox_context.bot,
                worker_id="worker-a",
            )
        )
        await transport.started.wait()
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task
        assert outbox.get(item.delivery_ref).status is DeliveryStatus.DISPATCHING

    asyncio.run(scenario())


def test_release_claimed_for_exact_worker_preserves_foreign_and_dispatching(
    outbox_context,
) -> None:
    outbox = _outbox(outbox_context)
    local = outbox.enqueue(_issued_draft(outbox_context, text="local"))
    foreign = outbox.enqueue(_issued_draft(outbox_context, text="foreign"))
    inflight = outbox.enqueue(_issued_draft(outbox_context, text="inflight"))
    local_claim = outbox.claim(local.delivery_ref, worker_id="local-worker")
    foreign_claim = outbox.claim(foreign.delivery_ref, worker_id="foreign-worker")
    inflight_claim = outbox.claim(inflight.delivery_ref, worker_id="local-worker")

    assert local_claim is not None
    assert foreign_claim is not None
    assert inflight_claim is not None
    inflight_dispatching = outbox.mark_dispatching(
        inflight_claim,
        worker_id="local-worker",
    )
    assert inflight_dispatching is not None

    released = outbox.release_claimed_for_worker(worker_id="local-worker")

    released_local = released[local.delivery_ref]
    assert released_local.status is DeliveryStatus.PENDING
    assert released_local.claim_worker_id is None
    assert released_local.claim_expires_at_ms is None
    assert released_local.item_generation == local_claim.item_generation + 1
    assert outbox.get(foreign.delivery_ref) == foreign_claim
    assert outbox.get(inflight.delivery_ref) == inflight_dispatching


def test_release_claimed_for_worker_does_not_overwrite_a_newer_foreign_claim(
    outbox_context,
) -> None:
    now_ms = [_NOW_MS]
    outbox = DeliveryOutbox(
        outbox_context.repository,
        outbox_context.catalog,
        claim_lease_ms=1,
        clock_ms=lambda: now_ms[0],
    )
    item = outbox.enqueue(_issued_draft(outbox_context))
    first_claim = outbox.claim(item.delivery_ref, worker_id="local-worker")
    assert first_claim is not None

    now_ms[0] += 2
    foreign_claim = outbox.claim(item.delivery_ref, worker_id="foreign-worker")
    assert foreign_claim is not None
    assert foreign_claim.claim_generation == first_claim.claim_generation + 1

    assert outbox.release_claimed_for_worker(worker_id="local-worker") == {}
    assert outbox.get(item.delivery_ref) == foreign_claim


def test_stopping_worker_releases_only_its_claimed_work_after_cancellation(
    outbox_context,
) -> None:
    async def scenario() -> None:
        outbox = _outbox(outbox_context)
        local = outbox.enqueue(_issued_draft(outbox_context, text="local"))
        foreign = outbox.enqueue(_issued_draft(outbox_context, text="foreign"))
        inflight = outbox.enqueue(_issued_draft(outbox_context, text="inflight"))
        worker = DeliveryOutboxWorker(
            outbox,
            lambda: None,
            bot_ref=outbox_context.bot,
            worker_id="local-worker",
            idle_wait_seconds=60.0,
        )
        local_claim = outbox.claim(local.delivery_ref, worker_id="local-worker")
        foreign_claim = outbox.claim(foreign.delivery_ref, worker_id="foreign-worker")
        inflight_claim = outbox.claim(inflight.delivery_ref, worker_id="local-worker")
        assert local_claim is not None
        assert foreign_claim is not None
        assert inflight_claim is not None
        inflight_dispatching = outbox.mark_dispatching(
            inflight_claim,
            worker_id="local-worker",
        )
        assert inflight_dispatching is not None

        worker.start()
        await asyncio.sleep(0)
        await worker.stop()

        assert outbox.get(local.delivery_ref).status is DeliveryStatus.PENDING
        assert outbox.get(foreign.delivery_ref) == foreign_claim
        assert outbox.get(inflight.delivery_ref) == inflight_dispatching

    asyncio.run(scenario())


def test_scoped_delivery_gateway_issues_only_for_its_exact_live_scope(
    outbox_context,
) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    registry.exact_session(outbox_context.scope)
    wakeups: list[bool] = []
    gateway = ScopedDeliveryGateway(
        outbox_context.scope,
        registry,
        _outbox(outbox_context),
        wake=lambda: wakeups.append(True),
        clock_ms=lambda: _NOW_MS,
    )

    item = gateway.enqueue(text="hello", idempotent=True, expires_at_ms=_EXPIRES_AT_MS)

    assert item is not None
    assert item.status is DeliveryStatus.PENDING
    assert wakeups == [True]
    with pytest.raises(ValueError):
        ScopedDeliveryGateway(
            "raw-session",
            registry,
            _outbox(outbox_context),
        )


def test_outbox_worker_waits_for_wake_and_stops_by_cancelling_its_loop(
    outbox_context,
) -> None:
    async def scenario() -> None:
        outbox = _outbox(outbox_context)
        transport = _Transport()
        worker = DeliveryOutboxWorker(
            outbox,
            transport,
            bot_ref=outbox_context.bot,
            worker_id="worker-a",
            idle_wait_seconds=60.0,
        )
        worker.start()
        item = outbox.enqueue(_issued_draft(outbox_context, idempotent=True))
        worker.wake()

        for _ in range(20):
            if outbox.get(item.delivery_ref).status is DeliveryStatus.SENT_CONFIRMED:
                break
            await asyncio.sleep(0)

        assert outbox.get(item.delivery_ref).status is DeliveryStatus.SENT_CONFIRMED
        await worker.stop()
        assert worker.running is False

    asyncio.run(scenario())


def test_outbox_worker_never_claims_or_sends_another_bot_item(outbox_context) -> None:
    async def scenario() -> None:
        outbox = _outbox(outbox_context)
        second_bot, second_scope = _second_bot_scope(outbox_context)
        first_item = outbox.enqueue(_issued_draft(outbox_context, text="first"))
        second_item = outbox.enqueue(
            _issued_draft(outbox_context, text="second", scope=second_scope)
        )
        first_transport = _Transport()
        second_transport = _Transport()
        first_worker = DeliveryOutboxWorker(
            outbox,
            first_transport,
            bot_ref=outbox_context.bot,
            worker_id="first-worker",
            idle_wait_seconds=60.0,
        )
        second_worker = DeliveryOutboxWorker(
            outbox,
            second_transport,
            bot_ref=second_bot,
            worker_id="second-worker",
            idle_wait_seconds=60.0,
        )
        try:
            first_worker.start()
            first_worker.wake()
            for _ in range(20):
                if (
                    outbox.get(first_item.delivery_ref).status
                    is DeliveryStatus.SENT_CONFIRMED
                ):
                    break
                await asyncio.sleep(0)

            assert outbox.get(first_item.delivery_ref).status is DeliveryStatus.SENT_CONFIRMED
            assert outbox.get(second_item.delivery_ref).status is DeliveryStatus.PENDING
            assert first_transport.calls == [first_item.delivery_id]
            assert second_transport.calls == []

            second_worker.start()
            second_worker.wake()
            for _ in range(20):
                if (
                    outbox.get(second_item.delivery_ref).status
                    is DeliveryStatus.SENT_CONFIRMED
                ):
                    break
                await asyncio.sleep(0)

            assert outbox.get(second_item.delivery_ref).status is DeliveryStatus.SENT_CONFIRMED
            assert second_transport.calls == [second_item.delivery_id]
        finally:
            await first_worker.stop()
            await second_worker.stop()

    asyncio.run(scenario())


def test_outbox_dispatch_rejects_a_bot_ref_with_the_wrong_generation(
    outbox_context,
) -> None:
    async def scenario() -> None:
        outbox = _outbox(outbox_context)
        item = outbox.enqueue(_issued_draft(outbox_context))
        stale_bot = replace(
            outbox_context.bot,
            generation=outbox_context.bot.generation + 1,
        )
        transport = _Transport()

        assert (
            await outbox.dispatch_one(
                transport,
                stale_bot,
                worker_id="stale-generation-worker",
            )
            is None
        )
        assert outbox.get(item.delivery_ref).status is DeliveryStatus.PENDING
        assert transport.calls == []

    asyncio.run(scenario())


def test_one_bot_worker_dispatches_multiple_live_persona_scopes(outbox_context) -> None:
    async def scenario() -> None:
        outbox = _outbox(outbox_context)
        second_scope = outbox_context.repository.create_scope(
            _scope(
                outbox_context.bot,
                "persona_v1_outbox_b",
                session_token="session_v1_outbox_b",
            ),
            expected_absent=True,
        )
        _freeze_scope(outbox_context.catalog, second_scope)
        first_item = outbox.enqueue(_issued_draft(outbox_context, text="first"))
        second_item = outbox.enqueue(
            _issued_draft(outbox_context, text="second", scope=second_scope)
        )
        transport = _Transport()
        worker = DeliveryOutboxWorker(
            outbox,
            transport,
            bot_ref=outbox_context.bot,
            worker_id="same-bot-worker",
            idle_wait_seconds=60.0,
        )
        try:
            worker.start()
            worker.wake()
            for _ in range(40):
                statuses = {
                    outbox.get(first_item.delivery_ref).status,
                    outbox.get(second_item.delivery_ref).status,
                }
                if statuses == {DeliveryStatus.SENT_CONFIRMED}:
                    break
                await asyncio.sleep(0)

            assert outbox.get(first_item.delivery_ref).status is DeliveryStatus.SENT_CONFIRMED
            assert outbox.get(second_item.delivery_ref).status is DeliveryStatus.SENT_CONFIRMED
            assert set(transport.calls) == {first_item.delivery_id, second_item.delivery_id}
        finally:
            await worker.stop()

    asyncio.run(scenario())


def test_plugin_scoped_enqueue_reaches_the_durable_worker(outbox_context) -> None:
    """The public plugin gateway retains the exact scope through delivery."""

    from main import EmotionalStatePlugin

    registry = ScopeRuntimeRegistry.for_test(repository=outbox_context.repository)
    registry.exact_session(outbox_context.scope)
    outbox = _outbox(outbox_context)
    transport = _Transport()
    worker = DeliveryOutboxWorker(
        outbox,
        transport,
        bot_ref=outbox_context.bot,
        worker_id="plugin-worker",
        idle_wait_seconds=60.0,
    )
    resolver = ScopeResolver(
        SimpleNamespace(),
        repository=outbox_context.repository,
        catalog=outbox_context.catalog,
        identity=load_or_create_scope_identity_key(
            outbox_context.repository.root / "identity.key"
        ),
        account_proofs=outbox_context.proofs,
    )
    plugin = object.__new__(EmotionalStatePlugin)
    plugin._scope_resolver_v1 = resolver
    plugin._scope_runtime_registry = registry
    plugin._scope_delivery_outbox = outbox
    plugin._scope_delivery_workers = {outbox_context.bot: worker}
    plugin._scope_delivery_recovered = True
    plugin._scope_account_proof_provider = outbox_context.proofs

    async def scenario() -> None:
        try:
            item = plugin.enqueue_scoped_proactive_intent(
                outbox_context.scope,
                text="hello",
                idempotent=True,
                expires_at_ms=_EXPIRES_AT_MS,
            )
            assert item is not None
            for _ in range(20):
                if outbox.get(item.delivery_ref).status is DeliveryStatus.SENT_CONFIRMED:
                    break
                await asyncio.sleep(0)
            assert outbox.get(item.delivery_ref).status is DeliveryStatus.SENT_CONFIRMED
            assert transport.calls == [item.delivery_id]
        finally:
            await worker.stop()

    asyncio.run(scenario())


def test_plugin_configures_process_unique_scope_delivery_worker_ids(
    outbox_context,
) -> None:
    from main import EmotionalStatePlugin

    resolver = ScopeResolver(
        SimpleNamespace(),
        repository=outbox_context.repository,
        catalog=outbox_context.catalog,
        identity=load_or_create_scope_identity_key(
            outbox_context.repository.root / "identity.key"
        ),
        account_proofs=outbox_context.proofs,
    )
    first = object.__new__(EmotionalStatePlugin)
    second = object.__new__(EmotionalStatePlugin)
    for plugin in (first, second):
        plugin.context = SimpleNamespace()
        plugin._scope_account_proof_provider = outbox_context.proofs
        plugin._configure_scope_delivery(resolver)

    first_worker = first._scope_delivery_worker_for_bot(outbox_context.bot)
    second_worker = second._scope_delivery_worker_for_bot(outbox_context.bot)
    assert type(first_worker) is DeliveryOutboxWorker
    assert type(second_worker) is DeliveryOutboxWorker
    assert first_worker._worker_id.startswith("scope-delivery-worker:")
    assert second_worker._worker_id.startswith("scope-delivery-worker:")
    assert first_worker._worker_id != second_worker._worker_id


def test_start_provisions_live_bot_workers_after_one_outbox_recovery(
    outbox_context,
    monkeypatch,
) -> None:
    from main import EmotionalStatePlugin

    async def scenario() -> None:
        second_bot, second_scope = _second_bot_scope(outbox_context)
        registry = ScopeRuntimeRegistry.for_test(repository=outbox_context.repository)
        registry.exact_session(outbox_context.scope)
        registry.exact_session(second_scope)
        outbox = _outbox(outbox_context)
        recovery_calls: list[str] = []
        monkeypatch.setattr(
            outbox,
            "recover_after_restart",
            lambda: recovery_calls.append("recover") or {},
        )
        monkeypatch.setattr(
            outbox,
            "expire",
            lambda: recovery_calls.append("expire") or {},
        )
        plugin = object.__new__(EmotionalStatePlugin)
        plugin.context = SimpleNamespace()
        plugin._scope_account_proof_provider = outbox_context.proofs
        plugin._scope_runtime_registry = registry
        plugin._scope_delivery_outbox = outbox
        plugin._scope_delivery_workers = {}
        plugin._scope_delivery_recovered = False

        plugin._start_scope_delivery_worker()

        workers = plugin._scope_delivery_workers
        assert set(workers) == {outbox_context.bot, second_bot}
        assert all(worker.running for worker in workers.values())
        assert recovery_calls == ["recover", "expire"]

        plugin._start_scope_delivery_worker(second_bot)

        assert recovery_calls == ["recover", "expire"]
        for worker in tuple(workers.values()):
            await worker.stop()

    asyncio.run(scenario())


def test_plugin_scoped_enqueue_rejects_new_intents_after_termination_begins(
    outbox_context,
) -> None:
    from main import EmotionalStatePlugin

    registry = ScopeRuntimeRegistry.for_test(repository=outbox_context.repository)
    registry.exact_session(outbox_context.scope)
    outbox = _outbox(outbox_context)
    resolver = ScopeResolver(
        SimpleNamespace(),
        repository=outbox_context.repository,
        catalog=outbox_context.catalog,
        identity=load_or_create_scope_identity_key(
            outbox_context.repository.root / "identity.key"
        ),
        account_proofs=outbox_context.proofs,
    )
    plugin = object.__new__(EmotionalStatePlugin)
    plugin._scope_resolver_v1 = resolver
    plugin._scope_runtime_registry = registry
    plugin._scope_delivery_outbox = outbox
    plugin._scope_delivery_workers = {
        outbox_context.bot: DeliveryOutboxWorker(
            outbox,
            _Transport(),
            bot_ref=outbox_context.bot,
        )
    }
    plugin._scope_delivery_accepting = False

    assert (
        plugin.enqueue_scoped_proactive_intent(
            outbox_context.scope,
            text="must not persist",
            idempotent=True,
            expires_at_ms=_EXPIRES_AT_MS,
        )
        is None
    )
    assert not outbox_context.repository.delivery_outbox_path(
        outbox_context.scope
    ).exists()


def test_scoped_scheduler_enqueues_with_its_exact_persistence_scope(
    outbox_context,
) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    session_runtime = registry.exact_session(outbox_context.scope)
    binding = SimpleNamespace(
        scope=outbox_context.scope,
        session_runtime=session_runtime,
        relation_runtime=None,
    )
    issued: list[tuple[SessionScope, str, bool]] = []

    def enqueue(scope: SessionScope, *, text: str, idempotent: bool, **_kwargs):
        issued.append((scope, text, idempotent))
        return SimpleNamespace(delivery_id="delivery_v1_scheduler")

    plugin = SimpleNamespace(
        _scope_runtime_registry=registry,
        _bound_runtime=lambda: binding,
        enqueue_scoped_proactive_intent=enqueue,
    )
    scheduler = ProactiveScheduler(
        plugin,
        persistence=ScopedPersistenceGateway(
            outbox_context.repository,
            outbox_context.scope,
        ),
    )

    result = asyncio.run(
        scheduler.request_dispatch(
            session_key=outbox_context.scope.storage_token,
            text="hello",
            idempotent=True,
        )
    )

    assert result["dispatched"] is True
    assert result["queued"] is True
    assert issued == [(outbox_context.scope, "hello", True)]


def test_scoped_life_outreach_requires_and_forwards_its_exact_scope(
    outbox_context,
) -> None:
    from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline

    registry = ScopeRuntimeRegistry.for_test()
    session_runtime = registry.exact_session(outbox_context.scope)
    binding = SimpleNamespace(
        scope=outbox_context.scope,
        session_runtime=session_runtime,
    )
    issued: list[tuple[SessionScope, str, bool]] = []

    def enqueue(scope: SessionScope, *, text: str, idempotent: bool, **_kwargs):
        issued.append((scope, text, idempotent))
        return object()

    pipeline = LLMRequestPipeline(
        SimpleNamespace(
            _scope_runtime_registry=registry,
            _bound_runtime=lambda: binding,
            enqueue_scoped_proactive_intent=enqueue,
        )
    )

    async def scenario() -> None:
        await pipeline._life_sim_outreach(
            "[life_event] hello",
            "warm",
            {"expires_at": 4_000_000_000.0},
            scope=outbox_context.scope,
        )
        await pipeline._life_sim_outreach("must not enqueue", "warm")

    asyncio.run(scenario())

    assert issued == [(outbox_context.scope, "[life_event] hello", False)]


def test_plugin_provider_registration_updates_the_existing_scope_catalog(
    outbox_context,
) -> None:
    from main import EmotionalStatePlugin

    plugin = object.__new__(EmotionalStatePlugin)
    resolver = SimpleNamespace(catalog=outbox_context.catalog)
    plugin._scope_resolver_v1 = resolver
    proofs = _StaticProofs(_current_proof(outbox_context.bot))

    plugin.register_adapter_account_proof_provider(proofs)

    assert plugin._scope_account_proof_provider is proofs
    assert resolver._account_proofs is proofs
    assert outbox_context.catalog._account_proofs is proofs
    with pytest.raises(ValueError):
        plugin.register_adapter_account_proof_provider(object())
