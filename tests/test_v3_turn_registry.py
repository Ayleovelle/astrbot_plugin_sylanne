from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from threading import Barrier

import pytest

import sylanne_alpha.v3bridge.turn_registry as turn_registry_module
from sylanne_alpha.v2core.shadow_snapshot import V2ResponseCandidateV1
from sylanne_alpha.v3bridge.actual_action import (
    V2_ACTUAL_ACTION_PROJECTION_REVISION_V1,
    ActualAction,
    V2ActualActionProjectionV1,
    project_actual_action,
)
from sylanne_alpha.v3bridge.limits import MAX_REPOSITORY_SESSIONS, MAX_TURN_REGISTRY
from sylanne_alpha.v3bridge.session_identity import SessionIdentityKey
from sylanne_alpha.v3bridge.turn_registry import (
    CreditAdjacency,
    SequenceLedger,
    SequenceHighWatermarks,
    SequenceStatus,
    TurnHandle,
    TurnRegistry,
    TurnRegistryState,
)
from sylanne_alpha.v3core.canonical import canonical_sha256
from sylanne_alpha.v3core.contracts import SessionRef, TurnKey, TurnSequence


_IDENTITY = SessionIdentityKey(key_id="session-v1", secret=b"s" * 32)


def _session(name: str = "umo-1"):
    session_ref = _IDENTITY.session_ref("qq", name, session_generation=0)
    assert session_ref is not None
    return session_ref


def _registry(
    *,
    capacity: int = 16,
    ttl_seconds: float = 30.0,
    ledger: SequenceLedger | None = None,
) -> TurnRegistry:
    return TurnRegistry(
        plugin_instance_id="plugin-1",
        correlation_secret=b"c" * 32,
        writer_epoch=7,
        capacity=capacity,
        ttl_seconds=ttl_seconds,
        sequence_ledger=ledger,
    )


def _capture(
    registry: TurnRegistry,
    *,
    nonce: str = "request-1",
    message_id: object = "message-1",
    session_ref=None,
    now: float = 10.0,
):
    return registry.capture_request(
        session_ref=_session() if session_ref is None else session_ref,
        bridge_request_nonce=nonce,
        request_attempt=0,
        platform_id="qq",
        unified_msg_origin="umo-1",
        message_id=message_id,
        now=now,
    )


def test_turn_registry_accepts_only_one_of_two_terminal_claims() -> None:
    registry = _registry()
    handle = _capture(registry)

    assert handle is not None
    assert registry.claim_response(
        handle=handle,
        platform_id="qq",
        unified_msg_origin="umo-1",
        message_id="message-1",
        now=11.0,
    )
    assert not registry.claim_response(
        handle=handle,
        platform_id="qq",
        unified_msg_origin="umo-1",
        message_id="message-1",
        now=12.0,
    )
    assert registry.stats().captures == 1
    assert registry.stats().terminal_attempts == 2
    assert registry.stats().accepted_terminal_claims == 1


def test_turn_id_is_exactly_the_canonical_turn_key_digest() -> None:
    registry = _registry()
    handle = _capture(registry)

    assert handle is not None
    assert handle.turn_id == canonical_sha256(handle.turn_key)


def test_capture_hash_failure_has_no_registry_or_sequence_side_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = SequenceLedger(max_sessions=1, history_capacity=4)
    registry = _registry(ledger=ledger)

    def fail_hash(value: object) -> str:
        assert type(value) is TurnKey
        raise ValueError("injected canonical failure")

    with monkeypatch.context() as patch:
        patch.setattr(turn_registry_module, "canonical_sha256", fail_hash)
        with pytest.raises(ValueError, match="injected canonical failure"):
            _capture(registry)

    assert ledger.record_count == 0
    assert registry.entry_count == 0
    assert registry.correlation_count == 0
    assert registry.stats().captures == 0
    valid = _capture(registry)
    assert valid is not None and valid.sequence.local_sequence == 1


def test_oversized_request_attempt_is_rejected_before_hash_or_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = SequenceLedger(max_sessions=1, history_capacity=4)
    registry = _registry(ledger=ledger)

    def unexpected_hash(value: object) -> str:
        raise AssertionError(f"hash called for invalid boundary: {type(value).__name__}")

    with monkeypatch.context() as patch:
        patch.setattr(turn_registry_module, "canonical_sha256", unexpected_hash)
        with pytest.raises(ValueError):
            registry.capture_request(
                session_ref=_session(),
                bridge_request_nonce="request-1",
                request_attempt=10**5000,
                platform_id="qq",
                unified_msg_origin="umo-1",
                message_id="message-1",
                now=1.0,
            )

    assert ledger.record_count == 0
    assert registry.entry_count == registry.correlation_count == 0
    valid = _capture(registry)
    assert valid is not None and valid.sequence.local_sequence == 1


def test_same_turn_key_keeps_turn_id_after_tombstone_expiry_and_new_sequence() -> None:
    registry = _registry(ttl_seconds=5.0)
    first = _capture(registry, now=1.0)
    second = _capture(registry, now=6.0)

    assert first is not None and second is not None
    assert first.turn_key == second.turn_key
    assert first.sequence != second.sequence
    assert first.turn_id == second.turn_id == canonical_sha256(first.turn_key)


def test_turn_registry_enforces_every_state_transition_and_final_claim_tombstone() -> None:
    registry = _registry()
    handle = _capture(registry)
    assert handle is not None
    assert registry.state_for(handle) is TurnRegistryState.REQUEST_CAPTURED
    assert not registry.mark_enqueued(handle=handle, now=10.5)
    assert not registry.finalize(handle=handle, now=10.5)

    assert registry.claim_response(
        handle=handle,
        platform_id="qq",
        unified_msg_origin="umo-1",
        message_id="message-1",
        now=11.0,
    )
    assert registry.state_for(handle) is TurnRegistryState.RESPONSE_CLAIMED
    assert not registry.finalize(handle=handle, now=11.5)
    assert registry.mark_enqueued(handle=handle, now=12.0)
    assert not registry.mark_enqueued(handle=handle, now=12.5)
    assert registry.state_for(handle) is TurnRegistryState.ENQUEUED
    assert registry.finalize(handle=handle, now=13.0)
    assert registry.state_for(handle) is TurnRegistryState.FINALIZED
    assert not registry.claim_response(
        handle=handle,
        platform_id="qq",
        unified_msg_origin="umo-1",
        message_id="message-1",
        now=14.0,
    )


@pytest.mark.parametrize(
    ("platform_id", "unified_msg_origin", "message_id"),
    [
        (None, "umo-1", "message-1"),
        ("", "umo-1", "message-1"),
        ("qq", None, "message-1"),
        ("qq", "", "message-1"),
        ("qq", "umo-1", None),
        ("qq", "umo-1", ""),
    ],
)
def test_missing_correlation_component_does_not_capture_or_allocate_sequence(
    platform_id: object,
    unified_msg_origin: object,
    message_id: object,
) -> None:
    registry = _registry()
    assert (
        registry.capture_request(
            session_ref=_session(),
            bridge_request_nonce="missing",
            request_attempt=0,
            platform_id=platform_id,
            unified_msg_origin=unified_msg_origin,
            message_id=message_id,
            now=1.0,
        )
        is None
    )

    valid = _capture(registry, now=2.0)
    assert valid is not None
    assert valid.sequence.local_sequence == 1


def test_duplicate_turn_key_or_correlation_is_rejected_before_sequence_allocation() -> None:
    registry = _registry()
    first = _capture(registry)
    assert first is not None and first.sequence.local_sequence == 1

    duplicate_key = _capture(registry, message_id="different-message")
    duplicate_correlation = _capture(registry, nonce="request-2")
    unique = _capture(registry, nonce="request-3", message_id="message-3")

    assert duplicate_key is None
    assert duplicate_correlation is None
    assert unique is not None
    assert unique.sequence.local_sequence == 2


def test_full_capacity_never_evicts_live_entry_or_consumes_sequence() -> None:
    registry = _registry(capacity=2)
    first = _capture(registry, nonce="request-1", message_id="message-1")
    second = _capture(registry, nonce="request-2", message_id="message-2")
    refused = _capture(registry, nonce="request-3", message_id="message-3")

    assert first is not None and second is not None
    assert refused is None
    assert registry.entry_count == registry.correlation_count == 2
    assert registry.claim_response(
        handle=first,
        platform_id="qq",
        unified_msg_origin="umo-1",
        message_id="message-1",
        now=11.0,
    )
    assert registry.mark_enqueued(handle=first, now=12.0)
    assert registry.finalize(handle=first, now=13.0)

    admitted = _capture(registry, nonce="request-3", message_id="message-3", now=14.0)
    assert admitted is not None
    assert admitted.sequence.local_sequence == 3
    assert registry.state_for(second) is TurnRegistryState.REQUEST_CAPTURED


def test_ttl_equality_is_stale_and_records_orphan_as_dropped() -> None:
    registry = _registry(ttl_seconds=5.0)
    before_boundary = _capture(registry, nonce="before", message_id="before", now=1.0)
    assert before_boundary is not None
    assert registry.claim_response(
        handle=before_boundary,
        platform_id="qq",
        unified_msg_origin="umo-1",
        message_id="before",
        now=5.999,
    )

    at_boundary = _capture(registry, nonce="at", message_id="at", now=10.0)
    assert at_boundary is not None
    assert not registry.claim_response(
        handle=at_boundary,
        platform_id="qq",
        unified_msg_origin="umo-1",
        message_id="at",
        now=15.0,
    )
    assert registry.state_for(at_boundary) is None
    assert registry.sequence_status(at_boundary) is SequenceStatus.DROPPED


def test_explicit_cleanup_removes_orphan_indexes_and_records_dropped() -> None:
    registry = _registry(ttl_seconds=5.0)
    handle = _capture(registry, now=3.0)
    assert handle is not None

    cleaned = registry.cleanup(now=8.0)

    assert cleaned == (handle,)
    assert registry.entry_count == 0
    assert registry.correlation_count == 0
    assert registry.sequence_status(handle) is SequenceStatus.DROPPED


@pytest.mark.parametrize("bad_now", [float("nan"), float("inf"), -1.0])
def test_registry_rejects_non_finite_or_negative_now(bad_now: float) -> None:
    registry = _registry()
    with pytest.raises(ValueError):
        _capture(registry, now=bad_now)


@pytest.mark.parametrize("bad_now", [True, 1, "1"])
def test_registry_rejects_wrong_semantic_now_type(bad_now: object) -> None:
    registry = _registry()
    with pytest.raises(TypeError):
        _capture(registry, now=bad_now)  # type: ignore[arg-type]


def test_registry_rejects_forged_turn_handle_without_consuming_real_claim() -> None:
    registry = _registry()
    handle = _capture(registry)
    assert handle is not None
    forged = replace(handle, turn_id="0" * 64)

    assert not registry.claim_response(
        handle=forged,
        platform_id="qq",
        unified_msg_origin="umo-1",
        message_id="message-1",
        now=11.0,
    )
    assert registry.claim_response(
        handle=handle,
        platform_id="qq",
        unified_msg_origin="umo-1",
        message_id="message-1",
        now=12.0,
    )


def test_threaded_capture_allocates_unique_session_local_sequences() -> None:
    registry = _registry(capacity=128)

    def capture(index: int):
        return _capture(
            registry,
            nonce=f"request-{index}",
            message_id=f"message-{index}",
            now=1.0,
        )

    with ThreadPoolExecutor(max_workers=16) as pool:
        handles = list(pool.map(capture, range(64)))

    assert all(handle is not None for handle in handles)
    assert {handle.sequence.local_sequence for handle in handles if handle is not None} == set(
        range(1, 65)
    )
    assert registry.entry_count == registry.correlation_count == 64


def test_two_threads_claiming_same_handle_accept_exactly_one() -> None:
    registry = _registry()
    handle = _capture(registry)
    assert handle is not None
    barrier = Barrier(2)

    def claim() -> bool:
        barrier.wait()
        return registry.claim_response(
            handle=handle,
            platform_id="qq",
            unified_msg_origin="umo-1",
            message_id="message-1",
            now=11.0,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: claim(), range(2)))

    assert sorted(results) == [False, True]
    stats = registry.stats()
    assert stats.terminal_attempts == 2
    assert stats.accepted_terminal_claims == 1


def test_claim_programmer_errors_do_not_count_but_unmatched_callbacks_do() -> None:
    registry = _registry()
    handle = _capture(registry)
    assert handle is not None

    with pytest.raises(TypeError):
        registry.claim_response(
            handle=object(),  # type: ignore[arg-type]
            platform_id="qq",
            unified_msg_origin="umo-1",
            message_id="message-1",
            now=11.0,
        )
    with pytest.raises(TypeError):
        registry.claim_response(
            handle=handle,
            platform_id=object(),
            unified_msg_origin="umo-1",
            message_id="message-1",
            now=11.0,
        )
    assert registry.stats().terminal_attempts == 0

    assert not registry.claim_response(
        handle=None,
        platform_id="qq",
        unified_msg_origin="umo-1",
        message_id="message-1",
        now=12.0,
    )
    assert not registry.claim_response(
        handle=handle,
        platform_id="qq",
        unified_msg_origin="umo-1",
        message_id=None,
        now=13.0,
    )
    assert registry.claim_response(
        handle=handle,
        platform_id="qq",
        unified_msg_origin="umo-1",
        message_id="message-1",
        now=14.0,
    )
    stats = registry.stats()
    assert stats.terminal_attempts == 3
    assert stats.accepted_terminal_claims == 1


def test_sequence_ledger_partitions_allocation_by_session_and_epoch() -> None:
    ledger = SequenceLedger(max_sessions=4, history_capacity=16)
    session_a = _session("umo-a")
    session_b = _session("umo-b")

    a1 = ledger.allocate(session_ref=session_a, writer_epoch=7)
    b1 = ledger.allocate(session_ref=session_b, writer_epoch=7)
    a2 = ledger.allocate(session_ref=session_a, writer_epoch=7)

    assert a1 is not None and b1 is not None and a2 is not None
    assert (a1.local_sequence, b1.local_sequence, a2.local_sequence) == (1, 1, 2)
    assert ledger.credit_adjacency(session_a, a1, session_a, a2) is CreditAdjacency.ADJACENT
    assert (
        ledger.credit_adjacency(session_a, a1, session_b, b1)
        is CreditAdjacency.CENSORED_CROSS_SESSION
    )

    a_reload = ledger.allocate(session_ref=session_a, writer_epoch=8)
    assert a_reload is not None
    assert a_reload.local_sequence == 1
    assert a_reload > a2
    assert (
        ledger.credit_adjacency(session_a, a2, session_a, a_reload)
        is CreditAdjacency.CENSORED_CROSS_EPOCH
    )


def test_dropped_intermediate_sequence_censors_adjacency_and_is_never_reused() -> None:
    ledger = SequenceLedger(max_sessions=1, history_capacity=8)
    session_ref = _session()
    first = ledger.allocate(session_ref=session_ref, writer_epoch=7)
    dropped = ledger.allocate(session_ref=session_ref, writer_epoch=7)
    third = ledger.allocate(session_ref=session_ref, writer_epoch=7)
    assert first is not None and dropped is not None and third is not None

    assert ledger.mark_dropped(session_ref, dropped)
    assert ledger.status(session_ref, dropped) is SequenceStatus.DROPPED
    assert (
        ledger.credit_adjacency(session_ref, first, session_ref, third)
        is CreditAdjacency.CENSORED_DROPPED_GAP
    )
    fourth = ledger.allocate(session_ref=session_ref, writer_epoch=7)
    assert fourth is not None and fourth.local_sequence == 4


def test_sequence_ledger_enforces_status_transitions() -> None:
    ledger = SequenceLedger(max_sessions=1, history_capacity=4)
    session_ref = _session()
    sequence = ledger.allocate(session_ref=session_ref, writer_epoch=7)
    assert sequence is not None

    assert ledger.status(session_ref, sequence) is SequenceStatus.ALLOCATED
    assert not ledger.mark_committed(session_ref, sequence)
    assert ledger.mark_accepted(session_ref, sequence)
    assert not ledger.mark_accepted(session_ref, sequence)
    assert ledger.mark_committed(session_ref, sequence)
    assert not ledger.mark_dropped(session_ref, sequence)
    assert ledger.status(session_ref, sequence) is SequenceStatus.COMMITTED


def test_sequence_status_high_watermarks_track_each_transition_and_are_frozen() -> None:
    ledger = SequenceLedger(max_sessions=1, history_capacity=8)
    session_ref = _session()
    accepted_then_committed = ledger.allocate(session_ref=session_ref, writer_epoch=7)
    directly_dropped = ledger.allocate(session_ref=session_ref, writer_epoch=7)
    assert accepted_then_committed is not None and directly_dropped is not None
    assert ledger.status_high_watermarks(session_ref) == SequenceHighWatermarks(
        accepted=None,
        dropped=None,
        committed=None,
    )

    assert ledger.mark_accepted(session_ref, accepted_then_committed)
    assert ledger.status_high_watermarks(session_ref).accepted == accepted_then_committed
    assert ledger.mark_committed(session_ref, accepted_then_committed)
    assert ledger.status_high_watermarks(session_ref).committed == accepted_then_committed
    assert ledger.mark_dropped(session_ref, directly_dropped)
    high_watermarks = ledger.status_high_watermarks(session_ref)

    assert high_watermarks == SequenceHighWatermarks(
        accepted=accepted_then_committed,
        dropped=directly_dropped,
        committed=accepted_then_committed,
    )
    with pytest.raises(FrozenInstanceError):
        high_watermarks.dropped = None  # type: ignore[misc]


def test_sequence_status_high_watermarks_do_not_regress_or_advance_on_failed_transition() -> None:
    ledger = SequenceLedger(max_sessions=1, history_capacity=8)
    session_ref = _session()
    old_first = ledger.allocate(session_ref=session_ref, writer_epoch=7)
    old_second = ledger.allocate(session_ref=session_ref, writer_epoch=7)
    assert old_first is not None and old_second is not None

    assert ledger.mark_accepted(session_ref, old_second)
    assert ledger.mark_accepted(session_ref, old_first)
    assert ledger.status_high_watermarks(session_ref).accepted == old_second
    assert ledger.mark_committed(session_ref, old_second)
    assert ledger.mark_committed(session_ref, old_first)
    assert ledger.status_high_watermarks(session_ref).committed == old_second

    new_epoch = ledger.allocate(session_ref=session_ref, writer_epoch=8)
    failed_commit = ledger.allocate(session_ref=session_ref, writer_epoch=8)
    assert new_epoch is not None and failed_commit is not None
    assert ledger.mark_accepted(session_ref, new_epoch)
    assert ledger.mark_committed(session_ref, new_epoch)
    before_failed_transition = ledger.status_high_watermarks(session_ref)
    assert not ledger.mark_committed(session_ref, failed_commit)
    assert ledger.status_high_watermarks(session_ref) == before_failed_transition
    assert before_failed_transition.accepted == new_epoch
    assert before_failed_transition.committed == new_epoch


def test_sequence_ledger_caps_sessions_and_history_fail_closed() -> None:
    ledger = SequenceLedger(max_sessions=1, history_capacity=2)
    session_a = _session("umo-a")
    session_b = _session("umo-b")
    first = ledger.allocate(session_ref=session_a, writer_epoch=7)
    second = ledger.allocate(session_ref=session_a, writer_epoch=7)

    assert first is not None and second is not None
    assert ledger.allocate(session_ref=session_a, writer_epoch=7) is None
    assert ledger.allocate(session_ref=session_b, writer_epoch=7) is None
    assert ledger.session_count == 1
    assert ledger.record_count == 2
    assert ledger.high_watermark(session_a) == second


def test_sequence_ledger_recycles_oldest_terminal_history_without_resetting_sequence() -> None:
    ledger = SequenceLedger(max_sessions=1, history_capacity=2)
    session_ref = _session()
    allocated = []

    for expected_local in range(1, 7):
        sequence = ledger.allocate(session_ref=session_ref, writer_epoch=7)
        assert sequence is not None
        assert sequence.local_sequence == expected_local
        allocated.append(sequence)
        assert ledger.mark_accepted(session_ref, sequence)
        assert ledger.mark_committed(session_ref, sequence)
        assert ledger.record_count <= 2

    assert ledger.high_watermark(session_ref) == allocated[-1]
    assert ledger.status(session_ref, allocated[0]) is None
    assert ledger.status(session_ref, allocated[-1]) is SequenceStatus.COMMITTED
    assert (
        ledger.credit_adjacency(
            session_ref,
            allocated[0],
            session_ref,
            allocated[1],
        )
        is CreditAdjacency.CENSORED_HISTORY_UNAVAILABLE
    )


def test_status_high_watermarks_do_not_reserve_terminal_history_slots() -> None:
    ledger = SequenceLedger(max_sessions=1, history_capacity=2)
    session_ref = _session()
    committed = ledger.allocate(session_ref=session_ref, writer_epoch=7)
    dropped = ledger.allocate(session_ref=session_ref, writer_epoch=7)
    assert committed is not None and dropped is not None
    assert ledger.mark_accepted(session_ref, committed)
    assert ledger.mark_committed(session_ref, committed)
    assert ledger.mark_accepted(session_ref, dropped)
    assert ledger.mark_dropped(session_ref, dropped)

    third = ledger.allocate(session_ref=session_ref, writer_epoch=7)

    assert third is not None and third.local_sequence == 3
    assert ledger.record_count == 2
    assert ledger.status(session_ref, committed) is None
    assert ledger.status_high_watermarks(session_ref) == SequenceHighWatermarks(
        accepted=dropped,
        dropped=dropped,
        committed=committed,
    )


def test_sequence_ledger_history_capacity_is_global_across_sessions() -> None:
    ledger = SequenceLedger(max_sessions=2, history_capacity=3)
    session_a = _session("umo-a")
    session_b = _session("umo-b")
    a1 = ledger.allocate(session_ref=session_a, writer_epoch=7)
    b1 = ledger.allocate(session_ref=session_b, writer_epoch=7)
    a2 = ledger.allocate(session_ref=session_a, writer_epoch=7)
    assert a1 is not None and b1 is not None and a2 is not None
    assert ledger.record_count == 3

    assert ledger.allocate(session_ref=session_b, writer_epoch=7) is None
    assert ledger.mark_dropped(session_a, a1)
    assert ledger.mark_dropped(session_a, a2)
    a3 = ledger.allocate(session_ref=session_a, writer_epoch=7)

    assert a3 is not None and a3.local_sequence == 3
    assert ledger.record_count == 3
    assert ledger.status(session_a, a1) is None
    assert ledger.status(session_a, a2) is SequenceStatus.DROPPED
    assert ledger.status(session_b, b1) is SequenceStatus.ALLOCATED


def test_terminal_churn_in_other_session_preserves_status_high_watermark_evidence() -> None:
    ledger = SequenceLedger(max_sessions=2, history_capacity=3)
    session_a = _session("umo-a")
    session_b = _session("umo-b")
    a1 = ledger.allocate(session_ref=session_a, writer_epoch=7)
    assert a1 is not None
    assert ledger.mark_accepted(session_a, a1)
    assert ledger.mark_committed(session_a, a1)

    for _ in range(8):
        b_sequence = ledger.allocate(session_ref=session_b, writer_epoch=7)
        assert b_sequence is not None
        assert ledger.mark_accepted(session_b, b_sequence)
        assert ledger.mark_committed(session_b, b_sequence)
        assert ledger.record_count <= 3

    a2 = ledger.allocate(session_ref=session_a, writer_epoch=7)
    assert a2 is not None
    assert ledger.mark_accepted(session_a, a2)

    assert ledger.status(session_a, a1) is None
    assert ledger.status(session_a, a2) is SequenceStatus.ACCEPTED
    assert ledger.status_high_watermarks(session_a) == SequenceHighWatermarks(
        accepted=a2,
        dropped=None,
        committed=a1,
    )
    assert ledger.credit_adjacency(session_a, a1, session_a, a2) is CreditAdjacency.ADJACENT


def test_credit_adjacency_explicit_dropped_current_detail_overrides_high_watermark_fallback() -> None:
    ledger = SequenceLedger(max_sessions=1, history_capacity=2)
    session_ref = _session()
    first = ledger.allocate(session_ref=session_ref, writer_epoch=7)
    second = ledger.allocate(session_ref=session_ref, writer_epoch=7)
    assert first is not None and second is not None
    assert ledger.mark_accepted(session_ref, first)
    assert ledger.mark_committed(session_ref, first)
    assert ledger.mark_accepted(session_ref, second)
    assert ledger.mark_dropped(session_ref, second)
    third = ledger.allocate(session_ref=session_ref, writer_epoch=7)
    assert third is not None
    assert ledger.mark_dropped(session_ref, third)
    assert ledger.status(session_ref, first) is None
    assert ledger.status(session_ref, second) is SequenceStatus.DROPPED

    assert (
        ledger.credit_adjacency(session_ref, first, session_ref, second)
        is CreditAdjacency.CENSORED_DROPPED_GAP
    )


def test_credit_adjacency_later_dropped_high_watermark_censors_missing_old_detail() -> None:
    ledger = SequenceLedger(max_sessions=1, history_capacity=2)
    session_ref = _session()
    first = ledger.allocate(session_ref=session_ref, writer_epoch=7)
    second = ledger.allocate(session_ref=session_ref, writer_epoch=7)
    assert first is not None and second is not None
    assert ledger.mark_accepted(session_ref, first)
    assert ledger.mark_committed(session_ref, first)
    assert ledger.mark_accepted(session_ref, second)
    assert ledger.mark_dropped(session_ref, second)
    third = ledger.allocate(session_ref=session_ref, writer_epoch=7)
    assert third is not None
    assert ledger.mark_dropped(session_ref, third)
    fourth = ledger.allocate(session_ref=session_ref, writer_epoch=7)
    assert fourth is not None
    assert ledger.status(session_ref, first) is None
    assert ledger.status(session_ref, second) is None

    assert (
        ledger.credit_adjacency(session_ref, first, session_ref, second)
        is CreditAdjacency.CENSORED_HISTORY_UNAVAILABLE
    )


def test_credit_adjacency_old_epoch_pair_is_censored_after_partition_reload() -> None:
    ledger = SequenceLedger(max_sessions=1, history_capacity=8)
    session_ref = _session()
    first = ledger.allocate(session_ref=session_ref, writer_epoch=7)
    second = ledger.allocate(session_ref=session_ref, writer_epoch=7)
    assert first is not None and second is not None
    assert ledger.mark_accepted(session_ref, first)
    assert ledger.mark_committed(session_ref, first)
    assert ledger.mark_accepted(session_ref, second)
    assert ledger.credit_adjacency(session_ref, first, session_ref, second) is CreditAdjacency.ADJACENT

    reloaded = ledger.allocate(session_ref=session_ref, writer_epoch=8)

    assert reloaded is not None
    assert (
        ledger.credit_adjacency(session_ref, first, session_ref, second)
        is CreditAdjacency.CENSORED_CROSS_EPOCH
    )


def test_history_allocation_fails_closed_when_only_live_records_remain() -> None:
    ledger = SequenceLedger(max_sessions=3, history_capacity=3)
    session_a = _session("umo-a")
    session_b = _session("umo-b")
    session_c = _session("umo-c")
    a1 = ledger.allocate(session_ref=session_a, writer_epoch=7)
    b1 = ledger.allocate(session_ref=session_b, writer_epoch=7)
    c1 = ledger.allocate(session_ref=session_c, writer_epoch=7)
    assert a1 is not None and b1 is not None and c1 is not None

    assert ledger.allocate(session_ref=session_a, writer_epoch=7) is None
    assert ledger.record_count == 3
    assert ledger.status(session_a, a1) is SequenceStatus.ALLOCATED
    assert ledger.status(session_b, b1) is SequenceStatus.ALLOCATED
    assert ledger.status(session_c, c1) is SequenceStatus.ALLOCATED


def test_sequence_ledger_rejects_limits_above_frozen_resource_ceilings() -> None:
    with pytest.raises(ValueError):
        SequenceLedger(max_sessions=MAX_REPOSITORY_SESSIONS + 1)
    with pytest.raises(ValueError):
        SequenceLedger(history_capacity=MAX_TURN_REGISTRY + 1)


def test_bridge_integer_and_identifier_caps_accept_edges_and_reject_oversize() -> None:
    assert turn_registry_module.MAX_SIGNED_64 == (1 << 63) - 1
    assert turn_registry_module.MAX_PLUGIN_INSTANCE_ID_BYTES == 96
    assert turn_registry_module.MAX_BRIDGE_REQUEST_NONCE_BYTES == 256
    identity = SessionIdentityKey(key_id="bounded", secret=b"s" * 32)
    session_ref = identity.session_ref(
        "qq",
        "umo-1",
        session_generation=turn_registry_module.MAX_SIGNED_64,
    )
    assert session_ref is not None
    registry = TurnRegistry(
        plugin_instance_id="p" * 96,
        correlation_secret=b"c" * 32,
        writer_epoch=turn_registry_module.MAX_SIGNED_64,
    )

    handle = registry.capture_request(
        session_ref=session_ref,
        bridge_request_nonce="n" * 256,
        request_attempt=turn_registry_module.MAX_SIGNED_64,
        platform_id="qq",
        unified_msg_origin="umo-1",
        message_id="message-1",
        now=1.0,
    )

    assert handle is not None
    with pytest.raises(ValueError):
        TurnRegistry(
            plugin_instance_id="p" * 97,
            correlation_secret=b"c" * 32,
            writer_epoch=0,
        )
    with pytest.raises(ValueError):
        TurnRegistry(
            plugin_instance_id="plugin",
            correlation_secret=b"c" * 32,
            writer_epoch=turn_registry_module.MAX_SIGNED_64 + 1,
        )


def test_capture_rejects_oversized_nonce_and_forged_session_ref_before_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = SequenceLedger(max_sessions=1, history_capacity=8)
    registry = _registry(ledger=ledger)
    forged_refs = (
        SessionRef(
            key_id="k",
            session_digest=b"d" * 32,
            session_generation=turn_registry_module.MAX_SIGNED_64 + 1,
        ),
        SessionRef(
            key_id="k" * 129,
            session_digest=b"d" * 32,
            session_generation=0,
        ),
    )

    def unexpected_hash(value: object) -> str:
        raise AssertionError(f"hash called for invalid boundary: {type(value).__name__}")

    with monkeypatch.context() as patch:
        patch.setattr(turn_registry_module, "canonical_sha256", unexpected_hash)
        with pytest.raises(ValueError):
            registry.capture_request(
                session_ref=_session(),
                bridge_request_nonce="n" * 257,
                request_attempt=0,
                platform_id="qq",
                unified_msg_origin="umo-1",
                message_id="message-1",
                now=1.0,
            )
        for forged_ref in forged_refs:
            with pytest.raises(ValueError):
                registry.capture_request(
                    session_ref=forged_ref,
                    bridge_request_nonce="request",
                    request_attempt=0,
                    platform_id="qq",
                    unified_msg_origin="umo-1",
                    message_id="message-1",
                    now=1.0,
                )

    assert ledger.record_count == 0
    assert registry.entry_count == registry.correlation_count == 0


def test_sequence_validation_rejects_values_above_signed_64_bit() -> None:
    ledger = SequenceLedger(max_sessions=1, history_capacity=4)
    session_ref = _session()
    with pytest.raises(ValueError):
        ledger.allocate(
            session_ref=session_ref,
            writer_epoch=turn_registry_module.MAX_SIGNED_64 + 1,
        )
    oversized_sequence = TurnSequence(
        writer_epoch=0,
        local_sequence=turn_registry_module.MAX_SIGNED_64 + 1,
    )
    with pytest.raises(ValueError):
        ledger.status(session_ref, oversized_sequence)


def test_registry_fails_closed_when_sequence_partition_capacity_is_full() -> None:
    ledger = SequenceLedger(max_sessions=1, history_capacity=4)
    registry = _registry(ledger=ledger)
    session_a = _session("umo-a")
    session_b = _session("umo-b")

    first = _capture(registry, session_ref=session_a, nonce="a1", message_id="a1")
    refused = _capture(registry, session_ref=session_b, nonce="b1", message_id="b1")
    second = _capture(registry, session_ref=session_a, nonce="a2", message_id="a2")

    assert first is not None and first.sequence.local_sequence == 1
    assert refused is None
    assert second is not None and second.sequence.local_sequence == 2
    assert registry.entry_count == registry.correlation_count == 2


def test_turn_handle_rejects_wrong_semantic_field_types() -> None:
    registry = _registry()
    handle = _capture(registry)
    assert handle is not None
    with pytest.raises(TypeError):
        TurnHandle(
            turn_key=object(),  # type: ignore[arg-type]
            turn_id=handle.turn_id,
            sequence=handle.sequence,
        )


@pytest.mark.parametrize("bad_local_sequence", [True, 1.0])
def test_bridge_rejects_forged_turn_sequence_semantic_types(
    bad_local_sequence: object,
) -> None:
    forged = object.__new__(TurnSequence)
    object.__setattr__(forged, "writer_epoch", 7)
    object.__setattr__(forged, "local_sequence", bad_local_sequence)

    with pytest.raises(TypeError, match="local_sequence"):
        TurnHandle(
            turn_key=TurnKey(
                plugin_instance_id="plugin-1",
                session_ref=_session(),
                bridge_request_nonce="request-1",
                request_attempt=0,
            ),
            turn_id="turn-id",
            sequence=forged,
        )


def test_v2_actual_action_projector_is_versioned_frozen_and_pure() -> None:
    projector = V2ActualActionProjectionV1()
    candidate = V2ResponseCandidateV1(
        route_kind="ORDINARY_TEXT",
        reply_kind="SPEAK",
        part_count=1,
        correlation_proven=True,
        after_message_sent=True,
    )

    assert projector.revision == V2_ACTUAL_ACTION_PROJECTION_REVISION_V1
    assert isinstance(project_actual_action, V2ActualActionProjectionV1)
    assert ActualAction.CLARIFY.value == "CLARIFY"
    assert projector(candidate) is ActualAction.UNKNOWN
    assert projector(candidate) is ActualAction.UNKNOWN
    with pytest.raises(FrozenInstanceError):
        projector.revision = "mutated"  # type: ignore[misc]


def test_v2_actual_action_duplicate_flag_is_defensive_unmatched_evidence() -> None:
    candidate = V2ResponseCandidateV1(
        route_kind="ORDINARY_TEXT",
        reply_kind="SPEAK",
        part_count=1,
        correlation_proven=True,
        after_message_sent=True,
        duplicate_terminal_claim=True,
    )

    assert project_actual_action(candidate) is ActualAction.UNMATCHED_RESPONSE
