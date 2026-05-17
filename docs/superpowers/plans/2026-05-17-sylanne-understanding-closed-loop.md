# Sylanne Understanding Closed Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Sylanne's audited understanding loop: event ledger, lifecycle state machine, pun/typo interpretation, memory gating, expression restraint, prompt injection, and diagnostics.

**Architecture:** Add focused helper modules for event ledger, interpretation, and expression/memory policy, then wire them into `main.py` at request/response lifecycle boundaries. Keep AstrBot's native context as the source of truth; Sylanne adds short auditable side-channel summaries only.

**Tech Stack:** Python 3.10+, stdlib dataclasses/deque/re/hashlib/time, existing AstrBot plugin hooks in `main.py`, existing pytest lifecycle and engine tests.

---

## File Structure

- Create: `conversation_event_ledger.py`
  - Owns event records, bounded per-session ledger queues, lifecycle audit helpers, and short summaries.
- Create: `interpretation_engine.py`
  - Owns typo/homophone/slang/nickname/joke candidate generation and memory gate classification.
- Create: `expression_policy.py`
  - Owns reply posture selection: brief/tool-like/clarify/listen/emotional/playful/minimal.
- Modify: `main.py`
  - Instantiates caches, records user/assistant ledger events, calls lifecycle audit before shadow injection, injects short prompt blocks, exposes diagnostics.
- Modify: `lifelike_learning_engine.py`
  - Extends common-ground support with interpreted expression evidence while keeping hard facts separate.
- Modify: `public_api.py`
  - Adds optional fields to diagnostics/result payloads without breaking existing callers.
- Test: `tests/test_conversation_event_ledger.py`
- Test: `tests/test_interpretation_engine.py`
- Test: `tests/test_expression_policy.py`
- Test: `tests/test_lifelike_learning_engine.py`
- Test: `tests/astrbot_lifecycle_part11.py`
- Test: `tests/astrbot_lifecycle_part15.py`
- Test: `tests/test_command_tools.py`
- Docs later: `README.md`, `CHANGELOG.md`, `metadata.yaml`, `docs/remote_testing.md`, `docs/release_branch_sync_checklist.md` when shipping `2.7.0`.

---

### Task 1: Conversation event ledger core

**Files:**
- Create: `conversation_event_ledger.py`
- Test: `tests/test_conversation_event_ledger.py`

- [ ] **Step 1: Write the failing ledger ring-buffer test**

Create `tests/test_conversation_event_ledger.py` with:

```python
from conversation_event_ledger import (
    ConversationEventLedger,
    LedgerEvent,
    build_ledger_summary,
)


def test_ledger_keeps_bounded_recent_events_per_session():
    ledger = ConversationEventLedger(max_events_per_session=2)

    ledger.record(
        LedgerEvent(
            event_id="e1",
            session_key="s1",
            speaker_key="u1",
            role="user",
            raw_text="第一句",
            normalized_text="第一句",
            event_time={"epoch": 1.0, "local_time": "2026-05-17 10:00:00"},
        ),
    )
    ledger.record(
        LedgerEvent(
            event_id="e2",
            session_key="s1",
            speaker_key="u1",
            role="assistant",
            raw_text="第二句",
            normalized_text="第二句",
            delivery_status="delivered",
            topic_state="completed",
            event_time={"epoch": 2.0, "local_time": "2026-05-17 10:00:01"},
        ),
    )
    ledger.record(
        LedgerEvent(
            event_id="e3",
            session_key="s1",
            speaker_key="u1",
            role="user",
            raw_text="第三句",
            normalized_text="第三句",
            event_time={"epoch": 3.0, "local_time": "2026-05-17 10:00:02"},
        ),
    )

    events = ledger.recent("s1")
    assert [event.event_id for event in events] == ["e2", "e3"]
    summary = build_ledger_summary(events)
    assert "[sylanne_event_ledger_summary]" in summary
    assert "assistant; status=delivered; topic=completed" in summary
    assert "第三句" in summary
    assert "第一句" not in summary
```

- [ ] **Step 2: Run the test to verify RED**

Run:

```bash
python -m pytest tests/test_conversation_event_ledger.py::test_ledger_keeps_bounded_recent_events_per_session -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'conversation_event_ledger'`.

- [ ] **Step 3: Implement minimal ledger module**

Create `conversation_event_ledger.py`:

```python
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from hashlib import sha1
from typing import Any


LEDGER_SUMMARY_MAX_EVENTS = 5
LEDGER_TEXT_LIMIT = 160


@dataclass(slots=True)
class LedgerEvent:
    event_id: str
    session_key: str
    speaker_key: str = ""
    role: str = "user"
    raw_text: str = ""
    normalized_text: str = ""
    media_summary: str = ""
    quote_summary: str = ""
    event_time: dict[str, Any] = field(default_factory=dict)
    delivery_status: str = ""
    topic_state: str = "open"
    interpretations: list[dict[str, Any]] = field(default_factory=list)
    memory_gate: dict[str, Any] = field(default_factory=dict)


def stable_event_id(session_key: str, role: str, text: str, epoch: float | int | None) -> str:
    payload = f"{session_key}\n{role}\n{text}\n{epoch if epoch is not None else ''}"
    return sha1(payload.encode("utf-8")).hexdigest()[:12]


class ConversationEventLedger:
    def __init__(self, *, max_events_per_session: int = 24) -> None:
        self.max_events_per_session = max(1, int(max_events_per_session))
        self._events: dict[str, deque[LedgerEvent]] = {}

    def record(self, event: LedgerEvent) -> None:
        key = str(event.session_key or "global")
        queue = self._events.setdefault(key, deque(maxlen=self.max_events_per_session))
        if queue.maxlen != self.max_events_per_session:
            queue = deque(queue, maxlen=self.max_events_per_session)
            self._events[key] = queue
        queue.append(event)

    def recent(self, session_key: str, *, limit: int | None = None) -> list[LedgerEvent]:
        key = str(session_key or "global")
        events = list(self._events.get(key) or ())
        if limit is None:
            return events
        return events[-max(0, int(limit)):]

    def clear(self, session_key: str | None = None) -> None:
        if session_key is None:
            self._events.clear()
        else:
            self._events.pop(str(session_key or "global"), None)


def _short(text: str, limit: int = LEDGER_TEXT_LIMIT) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)] + "…"


def build_ledger_summary(events: list[LedgerEvent], *, limit: int = LEDGER_SUMMARY_MAX_EVENTS) -> str:
    selected = events[-max(0, int(limit)):]
    lines = [
        "[sylanne_event_ledger_summary]",
        "以下是 Sylanne 的短期事件账本摘要，只用于审计和指代消解，不覆盖 AstrBot 原生上下文。",
    ]
    for event in selected:
        status = event.delivery_status or ""
        topic = event.topic_state or "open"
        epoch = event.event_time.get("epoch", "") if isinstance(event.event_time, dict) else ""
        head = f"{event.role}; status={status}; topic={topic}; epoch={epoch}; id={event.event_id}"
        lines.append(head)
        if event.raw_text:
            lines.append("raw=" + _short(event.raw_text))
        if event.media_summary:
            lines.append("media=" + _short(event.media_summary, 96))
        if event.quote_summary:
            lines.append("quote=" + _short(event.quote_summary, 96))
    return "\n".join(lines).strip()
```

- [ ] **Step 4: Run the test to verify GREEN**

Run:

```bash
python -m pytest tests/test_conversation_event_ledger.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add conversation_event_ledger.py tests/test_conversation_event_ledger.py
git commit -m "feat: add conversation event ledger"
```

---

### Task 2: Lifecycle auditor for completed vs continuation shadow

**Files:**
- Modify: `conversation_event_ledger.py`
- Test: `tests/test_conversation_event_ledger.py`
- Modify later integration: `main.py`

- [ ] **Step 1: Write failing lifecycle tests**

Append to `tests/test_conversation_event_ledger.py`:

```python
from conversation_event_ledger import audit_shadow_lifecycle


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
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
python -m pytest tests/test_conversation_event_ledger.py::test_lifecycle_marks_completed_delivered_reply_for_unrelated_new_turn tests/test_conversation_event_ledger.py::test_lifecycle_keeps_shadow_for_explicit_prior_reference -q
```

Expected: FAIL with `ImportError` or missing function.

- [ ] **Step 3: Implement lifecycle audit helper**

Append to `conversation_event_ledger.py`:

```python
_CORRECTION_MARKERS = (
    "不是", "不对", "我没说", "我没讲", "没有说", "没有讲",
    "什么时候和你说", "谁跟你说", "你理解错", "你误会",
)

_EXPLICIT_PRIOR_REFERENCE_MARKERS = (
    "刚才你说", "刚刚你说", "你刚才说", "你刚刚说", "上一句", "上一段", "上一轮",
    "再说一遍", "重复一遍", "接着说", "接上", "续上", "说完", "没说完",
    "那句话", "这句话", "那段话", "这段话", "刚才的话", "刚刚的话",
    "what did you say", "say that again", "repeat that",
)


def _compact_text(text: str) -> str:
    return "".join(str(text or "").lower().split())


def looks_like_user_correction(text: str) -> bool:
    compact = _compact_text(text)
    return any(marker in compact for marker in _CORRECTION_MARKERS)


def looks_like_explicit_prior_reference(text: str) -> bool:
    compact = _compact_text(text)
    return any(marker in compact for marker in _EXPLICIT_PRIOR_REFERENCE_MARKERS)


def audit_shadow_lifecycle(
    *,
    previous_assistant_text: str,
    current_user_text: str,
    delivery_status: str,
    has_interrupted_breakpoint: bool,
) -> dict[str, Any]:
    current = str(current_user_text or "").strip()
    status = str(delivery_status or "delivered")
    if has_interrupted_breakpoint or status == "interrupted":
        return {
            "topic_state": "needs_followup",
            "should_inject_shadow": True,
            "release_reason": "interrupted_reply_breakpoint",
        }
    if looks_like_user_correction(current):
        return {
            "topic_state": "corrected",
            "should_inject_shadow": True,
            "release_reason": "user_correction_or_source_query",
        }
    if looks_like_explicit_prior_reference(current):
        return {
            "topic_state": "needs_followup",
            "should_inject_shadow": True,
            "release_reason": "explicit_prior_reference",
        }
    return {
        "topic_state": "completed",
        "should_inject_shadow": False,
        "release_reason": "delivered_topic_completed",
    }
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
python -m pytest tests/test_conversation_event_ledger.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add conversation_event_ledger.py tests/test_conversation_event_ledger.py
git commit -m "feat: add shadow lifecycle auditor"
```

---

### Task 3: Wire ledger and lifecycle auditor into shadow memory

**Files:**
- Modify: `main.py`
- Test: `tests/astrbot_lifecycle_part11.py`

- [ ] **Step 1: Write failing lifecycle integration test**

Add to `tests/astrbot_lifecycle_part11.py` near existing shadow memory tests:

```python
    def test_shadow_memory_uses_lifecycle_audit_not_plain_continue_keyword(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
            },
        )
        self._bind_common_state_hooks(plugin)
        plugin._record_realtime_ordinary_history_backfill(
            "s-shadow-lifecycle-audit",
            role="assistant",
            content="我想对他们说：请先读 README，再按步骤安装。",
            input_epoch=21,
            source="unit_test",
            delivery_status="delivered",
        )
        request = fake_request(
            session_id="s-shadow-lifecycle-audit",
            prompt="继续说一下 shadow 模块，判断话题完成度来自动释放",
        )

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "s-shadow-lifecycle-audit",
                    message="继续说一下 shadow 模块，判断话题完成度来自动释放",
                    sender_id="u1",
                ),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        assert "sylanne_shadow_memory" not in injected
        assert "sylanne_lifecycle_audit" in injected
        assert "topic_state=completed" in injected
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
python -m pytest tests/astrbot_lifecycle_part11.py::AstrBotLifecyclePart11::test_shadow_memory_uses_lifecycle_audit_not_plain_continue_keyword -q
```

Expected: FAIL because no lifecycle audit block is injected.

- [ ] **Step 3: Import and initialize ledger**

In `main.py`, add import near other local imports:

```python
from .conversation_event_ledger import (
    ConversationEventLedger,
    LedgerEvent,
    audit_shadow_lifecycle,
    build_ledger_summary,
    stable_event_id,
)
```

Also support direct test import fallback in the existing import fallback block if needed:

```python
from conversation_event_ledger import (
    ConversationEventLedger,
    LedgerEvent,
    audit_shadow_lifecycle,
    build_ledger_summary,
    stable_event_id,
)
```

In `EmotionalStatePlugin.__init__`, add:

```python
        self._conversation_event_ledger = ConversationEventLedger(max_events_per_session=24)
```

- [ ] **Step 4: Add lifecycle audit injection helper**

In `main.py` near `_append_realtime_ordinary_history_backfills_if_any`, add:

```python
    def _append_lifecycle_audit_context(
        self,
        request: ProviderRequest,
        *,
        decision: dict[str, Any],
        current_user_text: str,
    ) -> bool:
        lines = [
            "[sylanne_lifecycle_audit]",
            "这是 Sylanne 对上一轮投递/话题状态的审计结果，只用于释放或保留临时上下文，不覆盖当前用户原文。",
            "topic_state={state}; should_inject_shadow={inject}; release_reason={reason}".format(
                state=str(decision.get("topic_state") or ""),
                inject="true" if decision.get("should_inject_shadow") else "false",
                reason=str(decision.get("release_reason") or ""),
            ),
            "current_user=" + self._head_one_line(str(current_user_text or ""), 160),
        ]
        return self._append_temp_text_part(
            request,
            "\n".join(lines),
            source="lifecycle_audit",
        )
```

- [ ] **Step 5: Replace keyword gate in `_append_realtime_ordinary_history_backfills_if_any`**

Inside `_append_realtime_ordinary_history_backfills_if_any`, after `valid_items` is built and before selecting items, compute the latest item decision:

```python
        latest = valid_items[-1] if valid_items else None
        if latest is not None:
            decision = audit_shadow_lifecycle(
                previous_assistant_text=str(latest.get("content") or ""),
                current_user_text=current_user_text,
                delivery_status=str(latest.get("delivery_status") or "delivered"),
                has_interrupted_breakpoint=self._has_pending_interrupted_reply_breakpoint(key),
            )
            self._append_lifecycle_audit_context(
                request,
                decision=decision,
                current_user_text=current_user_text,
            )
            if not decision.get("should_inject_shadow"):
                self._realtime_ordinary_history_backfill_cache().pop(key, None)
                self._mark_realtime_delivery_context_dirty(key)
                return False
```

Remove the earlier direct `_shadow_memory_backfill_relevant_to_current_turn(...)` gate after this test is green.

- [ ] **Step 6: Run integration tests to verify GREEN**

Run:

```bash
python -m pytest tests/astrbot_lifecycle_part11.py::AstrBotLifecyclePart11::test_shadow_memory_uses_lifecycle_audit_not_plain_continue_keyword tests/astrbot_lifecycle_part11.py::AstrBotLifecyclePart11::test_shadow_memory_backfill_has_reuse_guard_for_user_correction -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add main.py tests/astrbot_lifecycle_part11.py
git commit -m "feat: audit shadow memory lifecycle"
```

---

### Task 4: Interpretation engine for typo, homophone, slang, and joke candidates

**Files:**
- Create: `interpretation_engine.py`
- Test: `tests/test_interpretation_engine.py`

- [ ] **Step 1: Write failing interpretation tests**

Create `tests/test_interpretation_engine.py`:

```python
from interpretation_engine import interpret_user_text, classify_memory_gate


def test_typo_correction_pattern_yields_candidate_without_memorizing():
    result = interpret_user_text("我打错了，不是桥粱，是桥梁。")

    assert result["candidates"][0]["kind"] == "typo"
    assert result["candidates"][0]["raw_text"] == "桥粱"
    assert result["candidates"][0]["candidate"] == "桥梁"
    assert result["candidates"][0]["should_memorize"] is False


def test_homophone_joke_is_common_ground_not_hard_fact():
    result = interpret_user_text("这个插件真是记亿犹新，谐音梗啦")
    gate = classify_memory_gate(result["candidates"][0])

    assert result["candidates"][0]["kind"] == "homophone"
    assert result["candidates"][0]["humor_likelihood"] >= 0.5
    assert gate["layer"] == "joke_or_bit"
    assert gate["allow_long_term_fact"] is False
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
python -m pytest tests/test_interpretation_engine.py -q
```

Expected: FAIL with missing module.

- [ ] **Step 3: Implement minimal interpretation engine**

Create `interpretation_engine.py`:

```python
from __future__ import annotations

import re
from typing import Any


_CONFIRMED_TYPO_PATTERN = re.compile(r"不是\s*(?P<wrong>[^，。,.\s]{1,12})\s*[，,]?\s*是\s*(?P<right>[^，。,.\s]{1,12})")
_HOMOPHONE_HINTS = ("谐音", "梗", "笑死", "哈哈", "草", "hh", "hhh")
_COMMON_HOMOPHONE_BITS = {
    "记亿犹新": "记忆犹新",
    "绝绝紫": "绝绝子",
    "针不戳": "真不错",
}


def _candidate(
    *,
    raw_text: str,
    candidate: str,
    kind: str,
    confidence: float,
    humor_likelihood: float,
    evidence: list[str],
    should_ask_confirmation: bool,
    should_memorize: bool,
) -> dict[str, Any]:
    return {
        "raw_text": raw_text,
        "candidate": candidate,
        "kind": kind,
        "confidence": round(max(0.0, min(1.0, confidence)), 3),
        "humor_likelihood": round(max(0.0, min(1.0, humor_likelihood)), 3),
        "evidence": evidence,
        "should_ask_confirmation": bool(should_ask_confirmation),
        "should_memorize": bool(should_memorize),
    }


def interpret_user_text(text: str, *, common_ground: dict[str, str] | None = None) -> dict[str, Any]:
    value = str(text or "").strip()
    candidates: list[dict[str, Any]] = []
    typo_match = _CONFIRMED_TYPO_PATTERN.search(value)
    if typo_match:
        candidates.append(
            _candidate(
                raw_text=typo_match.group("wrong"),
                candidate=typo_match.group("right"),
                kind="typo",
                confidence=0.92,
                humor_likelihood=0.05,
                evidence=["explicit_not_x_but_y_correction"],
                should_ask_confirmation=False,
                should_memorize=False,
            ),
        )
    for raw, normalized in _COMMON_HOMOPHONE_BITS.items():
        if raw in value:
            humor = 0.72 if any(hint in value.lower() for hint in _HOMOPHONE_HINTS) else 0.55
            candidates.append(
                _candidate(
                    raw_text=raw,
                    candidate=normalized,
                    kind="homophone",
                    confidence=0.78,
                    humor_likelihood=humor,
                    evidence=["known_lightweight_homophone", "joke_hint" if humor >= 0.7 else "surface_homophone"],
                    should_ask_confirmation=False,
                    should_memorize=True,
                ),
            )
    for raw, normalized in (common_ground or {}).items():
        if raw and raw in value:
            candidates.append(
                _candidate(
                    raw_text=raw,
                    candidate=normalized,
                    kind="slang",
                    confidence=0.86,
                    humor_likelihood=0.35,
                    evidence=["confirmed_common_ground"],
                    should_ask_confirmation=False,
                    should_memorize=True,
                ),
            )
    return {"raw_text": value, "candidates": candidates}


def classify_memory_gate(candidate: dict[str, Any]) -> dict[str, Any]:
    kind = str(candidate.get("kind") or "uncertain")
    confidence = float(candidate.get("confidence") or 0.0)
    humor = float(candidate.get("humor_likelihood") or 0.0)
    if kind in {"homophone", "joke", "nickname", "slang"} and humor >= 0.45:
        return {
            "layer": "joke_or_bit",
            "allow_long_term_fact": False,
            "allow_common_ground": bool(candidate.get("should_memorize")),
            "reason": "playful_or_common_ground_expression",
        }
    if kind == "typo" and confidence >= 0.85:
        return {
            "layer": "correction",
            "allow_long_term_fact": False,
            "allow_common_ground": False,
            "reason": "explicit_typo_correction_not_fact",
        }
    return {
        "layer": "uncertain_interpretation",
        "allow_long_term_fact": False,
        "allow_common_ground": False,
        "reason": "low_confidence_or_unclassified",
    }
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
python -m pytest tests/test_interpretation_engine.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add interpretation_engine.py tests/test_interpretation_engine.py
git commit -m "feat: add pun and typo interpretation engine"
```

---

### Task 5: Expression policy engine

**Files:**
- Create: `expression_policy.py`
- Test: `tests/test_expression_policy.py`

- [ ] **Step 1: Write failing expression policy tests**

Create `tests/test_expression_policy.py`:

```python
from expression_policy import choose_expression_policy, build_expression_policy_prompt


def test_technical_question_prefers_tool_like_brief_answer():
    policy = choose_expression_policy(
        current_user_text="帮我提交并创建 release",
        interpretation_candidates=[],
        is_user_correction=False,
        is_low_signal=False,
    )

    assert policy["posture"] == "tool_like"
    assert policy["verbosity"] == "brief"
    assert "technical_or_workflow_request" in policy["reasons"]


def test_low_confidence_interpretation_prefers_clarify():
    policy = choose_expression_policy(
        current_user_text="这个记亿是什么",
        interpretation_candidates=[{"confidence": 0.42, "kind": "homophone", "candidate": "记忆"}],
        is_user_correction=False,
        is_low_signal=False,
    )

    assert policy["posture"] == "clarify"
    prompt = build_expression_policy_prompt(policy)
    assert "[sylanne_expression_policy]" in prompt
    assert "不要强行玩梗" in prompt
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
python -m pytest tests/test_expression_policy.py -q
```

Expected: FAIL with missing module.

- [ ] **Step 3: Implement expression policy**

Create `expression_policy.py`:

```python
from __future__ import annotations

from typing import Any


_TECHNICAL_MARKERS = (
    "提交", "commit", "release", "版本", "测试", "报错", "修复", "文件", "代码", "打包", "github", "git",
)


def choose_expression_policy(
    *,
    current_user_text: str,
    interpretation_candidates: list[dict[str, Any]],
    is_user_correction: bool,
    is_low_signal: bool,
) -> dict[str, Any]:
    text = str(current_user_text or "").lower()
    reasons: list[str] = []
    if is_low_signal:
        return {"posture": "silent_or_minimal", "verbosity": "minimal", "reasons": ["low_signal_turn"]}
    if is_user_correction:
        return {"posture": "clarify", "verbosity": "brief", "reasons": ["user_correction_priority"]}
    if any(float(item.get("confidence") or 0.0) < 0.55 for item in interpretation_candidates):
        return {"posture": "clarify", "verbosity": "brief", "reasons": ["low_confidence_interpretation"]}
    if any(marker in text for marker in _TECHNICAL_MARKERS):
        reasons.append("technical_or_workflow_request")
        return {"posture": "tool_like", "verbosity": "brief", "reasons": reasons}
    if any(str(item.get("kind") or "") in {"homophone", "joke", "slang"} for item in interpretation_candidates):
        return {"posture": "playful", "verbosity": "short", "reasons": ["high_confidence_playful_interpretation"]}
    return {"posture": "brief_answer", "verbosity": "normal", "reasons": ["default_conversational_turn"]}


def build_expression_policy_prompt(policy: dict[str, Any]) -> str:
    posture = str(policy.get("posture") or "brief_answer")
    verbosity = str(policy.get("verbosity") or "normal")
    reasons = ",".join(str(item) for item in policy.get("reasons") or [])
    lines = [
        "[sylanne_expression_policy]",
        f"posture={posture}; verbosity={verbosity}; reasons={reasons}",
        "当前用户原文优先；按姿态选择回复长度和语气，不要每轮都浓烈、撒娇或文学化。",
    ]
    if posture == "clarify":
        lines.append("解释候选不确定时，轻轻确认；不要强行玩梗，也不要把候选当事实。")
    if posture == "tool_like":
        lines.append("本轮优先完成任务，短句说明结果；不要过度情绪化。")
    if posture == "silent_or_minimal":
        lines.append("低信号轮次保持克制，可以短应或先听，不要扩写旧话题。")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
python -m pytest tests/test_expression_policy.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add expression_policy.py tests/test_expression_policy.py
git commit -m "feat: add expression restraint policy"
```

---

### Task 6: Wire interpretation and expression policy into request prompt

**Files:**
- Modify: `main.py`
- Test: `tests/astrbot_lifecycle_part15.py`

- [ ] **Step 1: Write failing lifecycle prompt test**

Add to `tests/astrbot_lifecycle_part15.py`:

```python
    def test_request_injects_interpretation_and_expression_policy_without_overriding_raw_text(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": False,
                "enable_realtime_chat": True,
                "enable_sticker_reaction": False,
                "use_llm_assessor": False,
            },
        )
        self._bind_common_state_hooks(plugin)
        request = fake_request(session_id="s-interpretation-policy", prompt="这个插件真是记亿犹新，谐音梗啦")

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "s-interpretation-policy",
                    message="这个插件真是记亿犹新，谐音梗啦",
                    sender_id="u1",
                ),
                request,
            ),
        )

        injected = "\n".join(self._request_text_parts(request))
        assert "[sylanne_interpretation_candidates]" in injected
        assert "raw_text=记亿犹新" in injected
        assert "candidate=记忆犹新" in injected
        assert "不覆盖用户原文" in injected
        assert "[sylanne_expression_policy]" in injected
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
python -m pytest tests/astrbot_lifecycle_part15.py::AstrBotLifecyclePart15::test_request_injects_interpretation_and_expression_policy_without_overriding_raw_text -q
```

Expected: FAIL because prompt blocks are absent.

- [ ] **Step 3: Import engines in `main.py`**

Add local/fallback imports:

```python
from .interpretation_engine import classify_memory_gate, interpret_user_text
from .expression_policy import build_expression_policy_prompt, choose_expression_policy
```

Fallback:

```python
from interpretation_engine import classify_memory_gate, interpret_user_text
from expression_policy import build_expression_policy_prompt, choose_expression_policy
```

- [ ] **Step 4: Add prompt append helpers in `main.py`**

Add methods:

```python
    def _append_interpretation_candidates_context(
        self,
        request: ProviderRequest,
        candidates: list[dict[str, Any]],
    ) -> bool:
        if not candidates:
            return False
        lines = [
            "[sylanne_interpretation_candidates]",
            "以下是错别字、谐音、黑话或昵称的候选解释；不覆盖用户原文，不确定时应轻轻确认。",
        ]
        for item in candidates[:3]:
            gate = classify_memory_gate(item)
            lines.append(
                "raw_text={raw}; candidate={candidate}; kind={kind}; confidence={confidence}; humor={humor}; memory_layer={layer}".format(
                    raw=self._head_one_line(str(item.get("raw_text") or ""), 60),
                    candidate=self._head_one_line(str(item.get("candidate") or ""), 60),
                    kind=str(item.get("kind") or "uncertain"),
                    confidence=item.get("confidence"),
                    humor=item.get("humor_likelihood"),
                    layer=str(gate.get("layer") or "uncertain_interpretation"),
                ),
            )
        return self._append_temp_text_part(request, "\n".join(lines), source="interpretation_candidates")

    def _append_expression_policy_context(
        self,
        request: ProviderRequest,
        policy: dict[str, Any],
    ) -> bool:
        return self._append_temp_text_part(
            request,
            build_expression_policy_prompt(policy),
            source="expression_policy",
        )
```

- [ ] **Step 5: Call helpers in `on_llm_request` after `current_user_text` is computed**

Insert after current user text/media normalization:

```python
        interpretation_payload = interpret_user_text(current_user_text)
        interpretation_candidates = list(interpretation_payload.get("candidates") or [])
        self._append_interpretation_candidates_context(
            request,
            interpretation_candidates,
        )
        expression_policy = choose_expression_policy(
            current_user_text=current_user_text,
            interpretation_candidates=interpretation_candidates,
            is_user_correction=self._looks_like_user_correction_or_source_query(current_user_text),
            is_low_signal=self._should_defer_realtime_shadow_for_low_signal(current_user_text),
        )
        self._append_expression_policy_context(request, expression_policy)
```

- [ ] **Step 6: Run test to verify GREEN**

Run:

```bash
python -m pytest tests/astrbot_lifecycle_part15.py::AstrBotLifecyclePart15::test_request_injects_interpretation_and_expression_policy_without_overriding_raw_text -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add main.py tests/astrbot_lifecycle_part15.py
git commit -m "feat: inject interpretation and expression policy"
```

---

### Task 7: Common-ground write policy integration

**Files:**
- Modify: `lifelike_learning_engine.py`
- Test: `tests/test_lifelike_learning_engine.py`

- [ ] **Step 1: Write failing common-ground interpretation test**

Append to `tests/test_lifelike_learning_engine.py`:

```python
from interpretation_engine import classify_memory_gate, interpret_user_text


def test_confirmed_homophone_is_common_ground_not_fact():
    result = interpret_user_text("这个插件真是记亿犹新，谐音梗啦")
    candidate = result["candidates"][0]
    gate = classify_memory_gate(candidate)

    assert gate["allow_common_ground"] is True
    assert gate["allow_long_term_fact"] is False
    assert gate["layer"] == "joke_or_bit"
```

- [ ] **Step 2: Run test to verify RED or existing GREEN**

Run:

```bash
python -m pytest tests/test_lifelike_learning_engine.py::test_confirmed_homophone_is_common_ground_not_fact -q
```

Expected: PASS if Task 4 already covered the gate. If PASS immediately, keep this as cross-module contract and proceed.

- [ ] **Step 3: Add common-ground evidence adapter**

In `lifelike_learning_engine.py`, add a small adapter near existing common-ground/jargon helpers:

```python
def common_ground_evidence_from_interpretation(candidate: dict[str, Any]) -> dict[str, Any]:
    raw = str(candidate.get("raw_text") or "").strip()
    meaning = str(candidate.get("candidate") or "").strip()
    kind = str(candidate.get("kind") or "uncertain")
    confidence = max(0.0, min(1.0, float(candidate.get("confidence") or 0.0)))
    humor = max(0.0, min(1.0, float(candidate.get("humor_likelihood") or 0.0)))
    return {
        "expression": raw,
        "meaning": meaning,
        "kind": kind,
        "confidence": round(confidence, 3),
        "humor_likelihood": round(humor, 3),
        "is_playful": kind in {"homophone", "joke", "nickname", "slang"} or humor >= 0.45,
        "source": "interpretation_candidate",
    }
```

- [ ] **Step 4: Add adapter test**

Append:

```python
from lifelike_learning_engine import common_ground_evidence_from_interpretation


def test_common_ground_evidence_from_interpretation_marks_playful():
    evidence = common_ground_evidence_from_interpretation(
        {
            "raw_text": "记亿犹新",
            "candidate": "记忆犹新",
            "kind": "homophone",
            "confidence": 0.78,
            "humor_likelihood": 0.72,
        },
    )

    assert evidence["expression"] == "记亿犹新"
    assert evidence["meaning"] == "记忆犹新"
    assert evidence["is_playful"] is True
    assert evidence["source"] == "interpretation_candidate"
```

- [ ] **Step 5: Run tests**

Run:

```bash
python -m pytest tests/test_lifelike_learning_engine.py::test_common_ground_evidence_from_interpretation_marks_playful tests/test_lifelike_learning_engine.py::test_confirmed_homophone_is_common_ground_not_fact -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add lifelike_learning_engine.py tests/test_lifelike_learning_engine.py
git commit -m "feat: route interpretations to common ground"
```

---

### Task 8: Diagnostics surface for closed loop

**Files:**
- Modify: `main.py`
- Modify: `public_api.py`
- Test: `tests/test_command_tools.py`

- [ ] **Step 1: Write failing diagnostics test**

Append to `tests/test_command_tools.py` near runtime diagnostics tests:

```python
    def test_runtime_diagnostics_include_understanding_closed_loop(self):
        plugin = new_plugin({"assessment_timing": "post", "inject_state": False})
        self._bind_common_state_hooks(plugin)
        event = FakeEvent("s-closed-loop-diag", message="这个插件真是记亿犹新，谐音梗啦", sender_id="u1")
        request = fake_request(session_id="s-closed-loop-diag", prompt="这个插件真是记亿犹新，谐音梗啦")

        asyncio.run(plugin.on_llm_request(event, request))
        payload = asyncio.run(plugin.get_agent_runtime_diagnostics(event, include_sessions=True))

        assert "understanding_closed_loop" in payload
        closed_loop = payload["understanding_closed_loop"]
        assert "ledger_tail" in closed_loop
        assert "interpretation_candidates" in closed_loop
        assert "expression_policy" in closed_loop
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
python -m pytest tests/test_command_tools.py::CommandToolTests::test_runtime_diagnostics_include_understanding_closed_loop -q
```

Expected: FAIL because `understanding_closed_loop` is absent.

- [ ] **Step 3: Store last closed-loop diagnostics in `main.py`**

In `__init__`:

```python
        self._last_understanding_closed_loop: dict[str, dict[str, Any]] = {}
```

After interpretation/expression policy in `on_llm_request`:

```python
        self._last_understanding_closed_loop[session_key] = {
            "interpretation_candidates": interpretation_candidates[:3],
            "expression_policy": expression_policy,
        }
```

When recording lifecycle audit, also set:

```python
        self._last_understanding_closed_loop.setdefault(key, {})["lifecycle_audit"] = dict(decision)
```

- [ ] **Step 4: Add diagnostics payload helper**

In `main.py` near diagnostics helpers:

```python
    def _understanding_closed_loop_diagnostics(self, session_key: str) -> dict[str, Any]:
        key = str(session_key or "global")
        latest = dict(getattr(self, "_last_understanding_closed_loop", {}).get(key) or {})
        ledger = getattr(self, "_conversation_event_ledger", None)
        ledger_tail = []
        if ledger is not None:
            for event in ledger.recent(key, limit=5):
                ledger_tail.append(
                    {
                        "event_id": event.event_id,
                        "role": event.role,
                        "topic_state": event.topic_state,
                        "delivery_status": event.delivery_status,
                        "raw_text": self._head_one_line(event.raw_text, 120),
                    },
                )
        latest["ledger_tail"] = ledger_tail
        latest.setdefault("interpretation_candidates", [])
        latest.setdefault("expression_policy", {})
        latest.setdefault("lifecycle_audit", {})
        return latest
```

Add into `get_agent_runtime_diagnostics(...)` result:

```python
payload["understanding_closed_loop"] = self._understanding_closed_loop_diagnostics(identity.conversation_id)
```

- [ ] **Step 5: Run test to verify GREEN**

Run:

```bash
python -m pytest tests/test_command_tools.py::CommandToolTests::test_runtime_diagnostics_include_understanding_closed_loop -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add main.py public_api.py tests/test_command_tools.py
git commit -m "feat: expose understanding closed-loop diagnostics"
```

---

### Task 9: Docs, version, package, and full verification

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `metadata.yaml`
- Modify: `main.py`
- Modify: `docs/remote_testing.md`
- Modify: `docs/release_branch_sync_checklist.md`
- Package: `dist/astrbot_plugin_sylanne.zip`

- [ ] **Step 1: Update version references to `2.7.0`**

Use a controlled script:

```bash
python - <<'PY'
from pathlib import Path
for name in [
    'metadata.yaml',
    'README.md',
    'main.py',
    'docs/remote_testing.md',
    'docs/release_branch_sync_checklist.md',
]:
    path = Path(name)
    text = path.read_text(encoding='utf-8')
    text = text.replace('2.6.2', '2.7.0')
    text = text.replace('262-当前版本发布记录', '270-当前版本发布记录')
    path.write_text(text, encoding='utf-8')
PY
```

- [ ] **Step 2: Add changelog entry**

Insert at top of `CHANGELOG.md` after the intro:

```markdown
## 2.7.0

发布日期：2026-05-17

### 新增

- 新增 Sylanne understanding closed loop：短期 conversation event ledger、lifecycle auditor、pun/typo/common-ground interpreter、memory gate 和 expression policy。
- `shadow memory` 生命周期改为审计状态机：完整送达但话题已完成的内容会释放；只有纠正、短答绑定、明确指回上一轮或被打断时才作为临时连续性线索。
- 新增错别字、谐音梗、黑话、昵称候选解释；候选不会覆盖用户原文，低置信候选只用于本轮，高置信玩笑进入 common-ground 而不是 hard fact。
- 新增表达克制策略：技术问题优先工具型短答，纠正优先确认，低信号优先少说，谐音梗高置信时才短接梗。

### 验证

- 新增 ledger、lifecycle、interpretation、memory gate、expression policy 和 diagnostics 定向测试。
- 全量测试与 zip 预检通过。
```

- [ ] **Step 3: Run full tests**

Run:

```bash
python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 4: Build package and preflight**

Run:

```bash
python scripts/package_plugin.py
node scripts/plugin_zip_preflight.js dist/astrbot_plugin_sylanne.zip astrbot_plugin_sylanne
```

Expected: package path printed and JSON with `"ok":true`.

- [ ] **Step 5: Inspect package version and checksum**

Run:

```bash
python - <<'PY'
import hashlib, re, zipfile
from pathlib import Path
p = Path('dist/astrbot_plugin_sylanne.zip')
with zipfile.ZipFile(p) as z:
    meta = z.read('astrbot_plugin_sylanne/metadata.yaml').decode('utf-8')
    readme = z.read('astrbot_plugin_sylanne/README.md').decode('utf-8')
version = re.search(r'^version:\s*(.+)$', meta, re.M).group(1).strip()
print('version', version)
print('readme_has_270', '2.7.0 当前版本发布记录' in readme)
print('size', p.stat().st_size)
print('sha256', hashlib.sha256(p.read_bytes()).hexdigest())
PY
```

Expected: `version 2.7.0`, `readme_has_270 True`.

- [ ] **Step 6: Commit release**

```bash
git add README.md CHANGELOG.md metadata.yaml main.py docs/remote_testing.md docs/release_branch_sync_checklist.md dist/astrbot_plugin_sylanne.zip
git commit -m "release: prepare v2.7.0 understanding closed loop"
```

---

## Self-Review

- Spec coverage:
  - Ledger: Tasks 1, 3, 8.
  - Lifecycle auditor: Tasks 2, 3.
  - Pun/typo/homophone interpreter: Tasks 4, 6.
  - Common-ground learning and memory gate: Tasks 4, 7.
  - Expression restraint: Tasks 5, 6.
  - Prompt injection: Task 6.
  - Diagnostics: Task 8.
  - Release/package: Task 9.
- Placeholder scan: no `TBD`, `TODO`, `later`, or unspecified test steps are present.
- Type consistency:
  - `LedgerEvent`, `ConversationEventLedger`, `audit_shadow_lifecycle`, `interpret_user_text`, `classify_memory_gate`, `choose_expression_policy`, and `build_expression_policy_prompt` are introduced before later tasks reference them.
  - Prompt markers match the spec: `[sylanne_event_ledger_summary]`, `[sylanne_lifecycle_audit]`, `[sylanne_interpretation_candidates]`, `[sylanne_expression_policy]`.
