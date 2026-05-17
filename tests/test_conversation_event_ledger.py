from conversation_event_ledger import (
    ConversationEventLedger,
    LedgerEvent,
    build_ledger_summary,
)


def test_ledger_keeps_bounded_recent_events_per_session():
    ledger = ConversationEventLedger(max_events_per_session=2)
    session_key = "session-1"

    e1 = LedgerEvent(
        event_id="e1",
        session_key=session_key,
        role="user",
        raw_text="first text",
    )
    e2 = LedgerEvent(
        event_id="e2",
        session_key=session_key,
        role="assistant",
        raw_text="second text",
        delivery_status="delivered",
        topic_state="completed",
    )
    e3 = LedgerEvent(
        event_id="e3",
        session_key=session_key,
        role="assistant",
        raw_text="third text",
        delivery_status="delivered",
        topic_state="completed",
    )

    ledger.record(e1)
    ledger.record(e2)
    ledger.record(e3)

    recent = ledger.recent(session_key)
    assert [event.event_id for event in recent] == ["e2", "e3"]

    summary = build_ledger_summary(recent)
    assert "assistant; status=delivered; topic=completed" in summary
    assert "third text" in summary
    assert "first text" not in summary
