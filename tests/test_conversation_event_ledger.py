from conversation_event_ledger import (
    ConversationEventLedger,
    LedgerEvent,
    audit_shadow_lifecycle,
    build_ledger_summary,
    build_relational_time_layer,
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




def test_relational_time_layer_builds_bounded_internal_continuity():
    events = [
        LedgerEvent(
            event_id="e1",
            session_key="s-time",
            role="user",
            raw_text="不是这样，以后发布说明只写这次更新了什么，不要列很长旧功能。",
            event_time={"epoch": 100.0, "local_time": "2026-05-18 10:00", "timezone": "Asia/Shanghai"},
            topic_state="corrected",
            interpretations=[{"type": "correction", "confidence": 0.82}],
        ),
        LedgerEvent(
            event_id="e2",
            session_key="s-time",
            role="assistant",
            raw_text="我会按这个边界整理发布说明。",
            event_time={"epoch": 160.0, "local_time": "2026-05-18 10:01", "timezone": "Asia/Shanghai"},
            delivery_status="delivered",
            topic_state="completed",
        ),
        LedgerEvent(
            event_id="e3",
            session_key="s-time",
            role="user",
            raw_text="继续推进 exp2，把关系时间层做成内部研究信号。",
            event_time={"epoch": 7200.0, "local_time": "2026-05-18 12:00", "timezone": "Asia/Shanghai"},
            topic_state="open",
        ),
    ]

    layer = build_relational_time_layer(
        events,
        self_interpretation={
            "turning_point_candidate": {
                "type": "collaboration",
                "confidence": 0.78,
            },
        },
        relationship_candidate_summary={"confidence": 0.66},
        now=7300.0,
    )

    assert layer["schema_version"] == "astrbot.relational_time_layer.v1"
    assert layer["kind"] == "relational_time_layer"
    assert layer["internal_only"] is True
    assert layer["public_api_eligible"] is False
    assert layer["span"]["event_count"] == 3
    assert layer["span"]["duration_seconds"] == 7100.0
    assert layer["continuity"]["phase"] == "active_continuity"
    assert "correction" in layer["continuity"]["turning_point_types"]
    assert "collaboration" in layer["continuity"]["turning_point_types"]
    assert layer["continuity"]["relationship_time_weight"] > 0.5
    assert len(layer["events"]) == 3
    assert "发布说明只写这次更新" not in str(layer)
    assert "message_length" in layer["events"][0]["evidence"]


def test_relational_time_layer_ignores_cross_session_events_and_low_signal():
    events = [
        LedgerEvent(event_id="a", session_key="s-a", role="user", raw_text="你好", event_time={"epoch": 1.0}),
        LedgerEvent(event_id="b", session_key="s-b", role="user", raw_text="以后默认中文", event_time={"epoch": 2.0}),
    ]

    layer = build_relational_time_layer(events, session_key="s-a", now=3.0)

    assert layer["span"]["event_count"] == 1
    assert layer["continuity"]["phase"] == "low_signal"
    assert layer["continuity"]["relationship_time_weight"] == 0.0
    assert layer["events"][0]["event_id"] == "a"
