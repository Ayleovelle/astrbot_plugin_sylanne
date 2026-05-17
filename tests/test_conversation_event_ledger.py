from conversation_event_ledger import (
    ConversationEventLedger,
    LedgerEvent,
    audit_shadow_lifecycle,
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
    assert summary.startswith("[sylanne_event_ledger_summary]")
    assert "bounded recent events" in summary
    assert "assistant; status=delivered; topic=completed" in summary
    assert "third text" in summary
    assert "first text" not in summary


def test_lifecycle_marks_completed_delivered_reply_for_unrelated_new_turn():
    decision = audit_shadow_lifecycle(
        previous_assistant_text="我想对他们说：请先读 README，再按步骤安装。",
        current_user_text="继续说一下 shadow 模块，判断话题完成度来自动释放",
        delivery_status="delivered",
        has_interrupted_breakpoint=False,
    )
    assert decision["topic_state"] == "completed"
    assert decision["should_inject_shadow"] is False
    assert decision["release_reason"] == "delivered_topic_completed"
    assert decision["previous_assistant_excerpt"] == "我想对他们说：请先读 README，再按步骤安装。"


def test_lifecycle_keeps_shadow_for_explicit_prior_reference():
    decision = audit_shadow_lifecycle(
        previous_assistant_text="我刚才说先读 README。",
        current_user_text="刚才你说的 README 是哪一段？",
        delivery_status="delivered",
        has_interrupted_breakpoint=False,
    )
    assert decision["topic_state"] == "needs_followup"
    assert decision["should_inject_shadow"] is True
    assert decision["release_reason"] == "explicit_prior_reference"
    assert decision["previous_assistant_excerpt"] == "我刚才说先读 README。"
