# Transactional Conversation Flush Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace destructive pre-summary buffer draining with a durable, replay-safe per-session flush protocol that commits each conversation batch to main L1 and optional PersonShelf at most once.

**Architecture:** `ConversationBuffer` becomes a one-entry write-ahead log with an active message list and a persisted `PendingFlush`. A dedicated per-session flush lock serializes attempts, while a separate per-session buffer-I/O lock orders debounced writes, prepare checkpoints, and ack checkpoints so an older snapshot cannot overwrite a newer ack. Main L1 and PersonShelf carry the same deterministic `source_batch_id`; memory persistence must report a real success before the buffer is acknowledged.

**Tech Stack:** Python 3.10+, `asyncio`, dataclasses, BLAKE2 (`hashlib.blake2b`), AstrBot v4.26 KV API, atomic JSON file replacement, pytest/`unittest.mock.AsyncMock`.

---

## Scope And Existing Contracts

This plan implements sections 5, 6, and 7.2 of `docs/superpowers/specs/2026-07-14-group-invocation-transactional-memory-design.md`. Group invocation is a separate implementation plan.

Current production contracts that must be preserved unless a task explicitly extends them:

```python
# sylanne_alpha/memory_system.py
ConversationBuffer.append(self, role: str, text: str, ts: float | None = None) -> None
ConversationBuffer.should_flush(self, idle_seconds: float = 60.0, max_turns: int = 20) -> str
ConversationBuffer.drain(self) -> list[dict[str, Any]]
ConversationBuffer.to_dict(self) -> dict
ConversationBuffer.from_dict(cls, d: dict) -> ConversationBuffer

MemorySystem.write_summary(
    self, text: str, source_turns: int = 1,
    embedding: list[float] | None = None, temperature: float = 0.0,
    source: str = "dialogue", importance: float | None = None,
    confidence: float | None = None, privacy_level: str | None = None,
    life_event_id: str = "", session_key: str = "",
) -> MemoryItem

# sylanne_alpha/state_persistence.py
StatePersistence.persist_buffer(
    self, session_key: str, host: SylanneAlphaHost, buf_dict: dict[str, Any]
) -> None
StatePersistence.load_buffer_data(
    self, session_key: str, host: SylanneAlphaHost
) -> dict[str, Any] | None
StatePersistence.schedule_buffer_persist(self, session_key: str) -> None
StatePersistence._do_buffer_persist(self, session_key: str) -> None
StatePersistence.save_sylanne_memory_state(self, session_key: str, state: Any = None) -> None

# sylanne_alpha/_engine/sylanne_core/compute/runtime.py (read-only SDK reference; do not edit)
Runtime.save_buffer(self, session_key: str, buffer_data: dict[str, Any]) -> None
Runtime.load_buffer(self, session_key: str) -> dict[str, Any] | None

# sylanne_alpha/person_shelf.py
save_person_shelf(
    plugin: Any, platform: str, sender_id: str, bucket: PersonShelfBucket
) -> None
```

`Runtime.save_buffer()` already writes `*.buffer.json.tmp`, flushes and `fsync()`s it, then uses `os.replace()`. Do not replace that atomic file primitive. `StatePersistence.persist_buffer()` currently catches and logs KV/file failures and therefore cannot be used as a prepare/ack durability barrier without the Task 4 extension.

## File Map

- Modify `sylanne_alpha/memory_system.py`: `PendingFlush`, reset epochs, batch ID calculation, buffer WAL transitions, `MemoryItem.source_batch_id`, L1 idempotency, and the independent durable flush-receipt ledger.
- Modify `sylanne_alpha/person_shelf.py`: `ShelfItem.source_batch_id`, bucket-level idempotent append, and batch-specific rollback for reset finalization.
- Modify `sylanne_alpha/session_state_store.py`: dedicated flush and buffer-persistence lock maps.
- Create `sylanne_alpha/buffer_file_coordinator.py`: plugin-owned runtime-root-scoped synchronous writer locks and an on-disk revision fence shared by every buffer file write, without modifying the vendored SylannEngine tree.
- Modify `sylanne_alpha/state_persistence.py`: ordered strict/current buffer checkpoints and truthful main-memory persistence result.
- Modify `sylanne_alpha/memory_facade.py`: forward the memory-save boolean.
- Modify `main.py`: forward current-buffer persistence and memory-save boolean; clear pending state on `/reset`.
- Modify `sylanne_alpha/llm_request_pipeline.py`: replace `drain()` orchestration with claim/prepare/process/commit/persist/ack.
- Modify `tests/test_memory_contract_prd.py`: L1 field/default/signature compatibility.
- Modify `tests/test_memory_golden_roundtrip.py`: persisted L1 idempotency round trip.
- Modify `tests/test_v250_foundation.py`: ShelfItem compatibility and round trip.
- Modify `tests/test_v250_shelf_write.py`: source batch propagation through the real shelf write point.
- Create `tests/test_transactional_conversation_buffer.py`: WAL model and retry tests.
- Create `tests/test_transactional_buffer_persistence.py`: ordering and strict checkpoint tests.
- Create `tests/test_transactional_conversation_flush.py`: fault-injected end-to-end state-machine matrix.

---

### Task 1: Add The ConversationBuffer Write-Ahead Log Model

**Files:**
- Modify: `sylanne_alpha/memory_system.py:624`
- Create: `tests/test_transactional_conversation_buffer.py`

- [ ] **Step 1: Write failing model tests**

Cover these exact cases in `tests/test_transactional_conversation_buffer.py`:

```python
def test_claim_moves_active_to_one_immutable_pending_batch():
    buf = ConversationBuffer("s")
    buf.append("user", "same", ts=100.0)
    buf.append("bot", "reply", ts=101.0)
    pending = buf.claim_flush(now=110.0)
    assert pending is not None
    assert buf.messages == []
    assert [m["text"] for m in pending.messages] == ["same", "reply"]
    assert buf.claim_flush(now=111.0) is pending


def test_batch_id_is_stable_for_replay_but_timestamp_sensitive():
    a = ConversationBuffer("s")
    b = ConversationBuffer("s")
    c = ConversationBuffer("s")
    a.append("user", "same", ts=100.0)
    b.append("user", "same", ts=100.0)
    c.append("user", "same", ts=101.0)
    assert a.claim_flush(now=200.0).batch_id == b.claim_flush(now=300.0).batch_id
    assert a.pending_flush.batch_id != c.claim_flush(now=300.0).batch_id


def test_batch_id_is_namespaced_by_session_for_shared_person_shelf():
    a = ConversationBuffer("group-a")
    b = ConversationBuffer("group-b")
    a.append("user", "same", ts=100.0)
    b.append("user", "same", ts=100.0)
    assert a.claim_flush(now=200.0).batch_id != b.claim_flush(now=200.0).batch_id


def test_new_messages_stay_active_while_pending_exists():
    buf = ConversationBuffer("s")
    buf.append("user", "old", ts=1.0)
    old = buf.claim_flush(now=2.0)
    buf.append("user", "new", ts=3.0)
    assert [m["text"] for m in old.messages] == ["old"]
    assert [m["text"] for m in buf.messages] == ["new"]


def test_retry_backoff_is_bounded_and_should_flush_respects_it(monkeypatch):
    buf = ConversationBuffer("s")
    buf.append("user", "x", ts=1.0)
    pending = buf.claim_flush(now=10.0)
    buf.mark_flush_failed(pending.batch_id, now=20.0)
    assert pending.attempts == 1
    assert pending.next_retry_at == 50.0
    monkeypatch.setattr("sylanne_alpha.memory_system.time.time", lambda: 49.0)
    assert buf.should_flush() == ""
    monkeypatch.setattr("sylanne_alpha.memory_system.time.time", lambda: 50.0)
    assert buf.should_flush() == "retry"


def test_legacy_buffer_without_pending_flush_loads_normally():
    buf = ConversationBuffer.from_dict({
        "session_key": "s", "messages": [{"role": "user", "text": "x", "ts": 1.0}],
        "last_activity": 1.0, "turn_count": 0, "last_flush_ts": 0.0,
    })
    assert buf.pending_flush is None
    assert buf.messages[0]["text"] == "x"


def test_pending_roundtrip_preserves_batch_and_retry_metadata():
    buf = ConversationBuffer("s")
    buf.append("user", "x", ts=1.0)
    pending = buf.claim_flush(now=2.0)
    buf.mark_flush_failed(pending.batch_id, now=3.0)
    restored = ConversationBuffer.from_dict(buf.to_dict())
    assert restored.pending_flush.to_dict() == pending.to_dict()


def test_reset_epoch_invalidates_claimed_batch_and_restore_rejects_it():
    buf = ConversationBuffer("s")
    buf.append("user", "old", ts=1.0)
    pending = buf.claim_flush(now=2.0)
    assert pending.flush_epoch == buf.flush_epoch
    buf.clear_all()
    assert buf.flush_epoch == pending.flush_epoch + 1
    assert buf.restore_flush(pending) is False


def test_corrupt_persisted_batch_id_is_recomputed_from_messages():
    buf = ConversationBuffer("s")
    buf.append("user", "x", ts=1.0)
    raw = buf.claim_flush(now=2.0).to_dict()
    raw["batch_id"] = "wrong"
    restored = PendingFlush.from_dict(raw, "s")
    assert restored is not None
    assert restored.batch_id != "wrong"


def test_legacy_reader_projection_keeps_pending_and_active_on_downgrade():
    buf = ConversationBuffer("s")
    buf.append("user", "pending", ts=1.0)
    buf.claim_flush(now=2.0)
    buf.append("user", "active", ts=3.0)
    raw = buf.to_dict()
    assert [m["text"] for m in raw["messages"]] == ["pending", "active"]
    assert [m["text"] for m in raw["active_messages"]] == ["active"]
    legacy = ConversationBuffer.from_dict({
        key: value
        for key, value in raw.items()
        if key not in {"active_messages", "pending_flush", "flush_epoch", "revision"}
    })
    assert [m["text"] for m in legacy.messages] == ["pending", "active"]
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m pytest tests/test_transactional_conversation_buffer.py -q`

Expected: failures because `PendingFlush`, `claim_flush`, `mark_flush_failed`, and `pending_flush` do not exist.

- [ ] **Step 3: Implement the WAL data model**

Add `import json` beside the existing `hashlib` import, then add near `ConversationBuffer`:

```python
_FLUSH_RETRY_BASE_SECONDS = 30.0
_FLUSH_RETRY_MAX_SECONDS = 900.0
_FLUSH_RETRY_MAX_ATTEMPTS = 6


def _conversation_batch_id(
    session_key: str, messages: list[dict[str, Any]]
) -> str:
    canonical = [
        {
            "role": str(message.get("role", "")),
            "text": str(message.get("text", "")),
            "ts": _safe_float(message.get("ts", 0.0), 0.0),
        }
        for message in messages
    ]
    payload = json.dumps(
        {"session_key": str(session_key), "messages": canonical},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.blake2b(payload, digest_size=16).hexdigest()


@dataclass
class PendingFlush:
    batch_id: str
    messages: tuple[dict[str, Any], ...]
    claimed_at: float
    flush_epoch: int
    attempts: int = 0
    next_retry_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "messages": [dict(message) for message in self.messages],
            "claimed_at": self.claimed_at,
            "flush_epoch": self.flush_epoch,
            "attempts": self.attempts,
            "next_retry_at": self.next_retry_at,
        }

    @classmethod
    def from_dict(
        cls, data: Any, session_key: str
    ) -> "PendingFlush | None":
        if not isinstance(data, dict) or not isinstance(data.get("messages"), list):
            return None
        messages = tuple(dict(message) for message in data["messages"] if isinstance(message, dict))
        if not messages:
            return None
        computed = _conversation_batch_id(session_key, list(messages))
        return cls(
            batch_id=computed,
            messages=messages,
            claimed_at=_safe_float(data.get("claimed_at", 0.0), 0.0),
            flush_epoch=max(0, int(_safe_float(data.get("flush_epoch", 0), 0.0))),
            attempts=min(
                _FLUSH_RETRY_MAX_ATTEMPTS,
                max(0, int(_safe_float(data.get("attempts", 0), 0.0))),
            ),
            next_retry_at=max(0.0, _safe_float(data.get("next_retry_at", 0.0), 0.0)),
        )
```

Add `pending_flush: PendingFlush | None = None`, `flush_epoch: int = 0`, and `revision: int = 0` to `ConversationBuffer`. Extend it with:

```python
def claim_flush(self, now: float | None = None) -> PendingFlush | None:
    if self.pending_flush is not None:
        return self.pending_flush
    if not self.messages:
        return None
    claimed_at = time.time() if now is None else float(now)
    messages = tuple(dict(message) for message in self.messages)
    self.pending_flush = PendingFlush(
        batch_id=_conversation_batch_id(self.session_key, list(messages)),
        messages=messages,
        claimed_at=claimed_at,
        flush_epoch=self.flush_epoch,
    )
    self.messages.clear()
    self.turn_count = 0
    self.last_flush_ts = claimed_at
    self.revision += 1
    return self.pending_flush

def mark_flush_failed(self, batch_id: str, now: float | None = None) -> bool:
    pending = self.pending_flush
    if pending is None or pending.batch_id != batch_id:
        return False
    failed_at = time.time() if now is None else float(now)
    pending.attempts = min(_FLUSH_RETRY_MAX_ATTEMPTS, pending.attempts + 1)
    delay = min(
        _FLUSH_RETRY_MAX_SECONDS,
        _FLUSH_RETRY_BASE_SECONDS * (2 ** min(pending.attempts - 1, 5)),
    )
    pending.next_retry_at = failed_at + delay
    self.revision += 1
    return True

def ack_flush(self, batch_id: str) -> bool:
    if self.pending_flush is None or self.pending_flush.batch_id != batch_id:
        return False
    self.pending_flush = None
    self.revision += 1
    return True

def restore_flush(self, pending: PendingFlush) -> bool:
    if self.pending_flush is not None or pending.flush_epoch != self.flush_epoch:
        return False
    self.pending_flush = pending
    self.revision += 1
    return True

def clear_all(self) -> None:
    self.flush_epoch += 1
    self.messages.clear()
    self.pending_flush = None
    self.turn_count = 0
    self.last_flush_ts = time.time()
    self.revision += 1
```

At the start of `should_flush()`, return `"retry"` only when a pending batch exists and `time.time() >= next_retry_at`; while pending is not ready, do not claim accumulated active messages. Add `pending_flush`, monotonic `revision`, `flush_epoch`, and `active_messages` to `to_dict()`. Keep `messages` as a downgrade-safe legacy projection of `pending.messages + active_messages`; new readers use `active_messages` when present, while grey5 readers see every unacknowledged message and can replay rather than lose it. Parse pending with `PendingFlush.from_dict(raw, buf.session_key)`. A restored pending whose `flush_epoch` differs from the buffer's current epoch is discarded fail-closed. Increment `revision` inside `append()` and once per `inject_context()` call in addition to the transitions shown above.

Keep `drain()` as the legacy active-message-only method for existing direct callers/tests. Transactional production flush must stop calling it. `/reset` is migrated to `clear_all()` in Task 6.

- [ ] **Step 4: Run focused and legacy buffer tests**

Run: `python -m pytest tests/test_transactional_conversation_buffer.py tests/test_incident_copywriting_cascade_2026_06_15.py::TestH6BufferIdleFlush -q`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add sylanne_alpha/memory_system.py tests/test_transactional_conversation_buffer.py
git commit -m "feat: add durable conversation flush batches"
```

---

### Task 2: Make Main L1 Writes Idempotent And Persist Commit Receipts

**Files:**
- Modify: `sylanne_alpha/memory_system.py:299,360,385,1235`
- Modify: `tests/test_memory_contract_prd.py`
- Modify: `tests/test_memory_golden_roundtrip.py`

- [ ] **Step 1: Write failing L1 idempotency and compatibility tests**

```python
def test_write_summary_same_source_batch_returns_original_item():
    memory = MemorySystem()
    first = memory.write_summary("first wording", source_batch_id="batch-a")
    replay = memory.write_summary("different replay wording", source_batch_id="batch-a")
    assert replay is first
    assert [item.text for item in memory._l1] == ["first wording"]


def test_write_summary_without_source_batch_keeps_legacy_append_behavior():
    memory = MemorySystem()
    memory.write_summary("same")
    memory.write_summary("same")
    assert len(memory._l1) == 2


def test_legacy_memory_item_defaults_source_batch_to_empty():
    raw = make_valid_memory_item_dict()
    raw.pop("source_batch_id", None)
    assert MemoryItem.from_dict(raw).source_batch_id == ""


def test_source_batch_survives_memory_system_roundtrip():
    memory = MemorySystem()
    memory.write_summary("x", source_batch_id="batch-a")
    restored = MemorySystem.create_from_dict(memory.to_dict())
    assert restored._l1[0].source_batch_id == "batch-a"
    assert restored.write_summary("replay", source_batch_id="batch-a") is restored._l1[0]


def test_flush_receipt_survives_after_source_item_leaves_l1_and_l2():
    memory = MemorySystem()
    memory.record_flush_commit("batch-a")
    restored = MemorySystem.create_from_dict(memory.to_dict())
    restored._l1.clear()
    restored._l2.clear()
    assert restored.has_flush_commit("batch-a") is True
    assert restored.discard_flush_commit("batch-a") is True
    assert restored.has_flush_commit("batch-a") is False


def test_hydrate_merge_unions_receipts_without_source_items():
    archived = MemorySystem()
    archived.record_flush_commit("batch-a")
    live = MemorySystem()
    live.merge_kv_archive(archived.to_dict())
    assert live.has_flush_commit("batch-a") is True
    assert live._l1 == deque()
    assert live._l2 == []


def test_remove_source_batch_also_removes_its_pending_followup():
    memory = MemorySystem()
    memory.write_summary(
        "我答应你明天一定提交材料",
        source_batch_id="reset-race",
        session_key="s",
    )
    assert any(
        entry.get("source_batch_id") == "reset-race"
        for entry in memory._pending_followups
    )
    memory.remove_by_source_batch_id("reset-race")
    assert all(
        entry.get("source_batch_id") != "reset-race"
        for entry in memory._pending_followups
    )
```

Use the existing valid-item fixture shape in `tests/test_memory_contract_prd.py`; do not introduce a second incompatible fixture.

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m pytest tests/test_memory_contract_prd.py tests/test_memory_golden_roundtrip.py -q`

Expected: new tests fail because the field and argument are absent.

- [ ] **Step 3: Extend MemoryItem and write_summary**

Add `source_batch_id: str = ""` after `life_event_id`, normalize it to `str` in `__post_init__`, include it in `to_dict()`, and load it with `d.get("source_batch_id", "")` in `from_dict()`.

Add this helper beside `_find_by_life_event_id()`:

```python
def _find_by_source_batch_id(self, source_batch_id: str) -> MemoryItem | None:
    if not source_batch_id:
        return None
    for item in self._l1:
        if item.source_batch_id == source_batch_id:
            return item
    for item in self._l2:
        if item.source_batch_id == source_batch_id:
            return item
    return None

def remove_by_source_batch_id(self, source_batch_id: str) -> bool:
    if not source_batch_id:
        return False
    removed_ids = {
        item.id for item in [*self._l1, *self._l2]
        if item.source_batch_id == source_batch_id
    }
    self._l1 = deque(
        (item for item in self._l1 if item.id not in removed_ids),
        maxlen=self._L1_CAPACITY,
    )
    self._l2 = [item for item in self._l2 if item.id not in removed_ids]
    for item_id in removed_ids:
        self._inverted_index.remove(item_id)
    before_followups = len(self._pending_followups)
    self._pending_followups = [
        entry for entry in self._pending_followups
        if entry.get("source_batch_id") != source_batch_id
    ]
    return bool(removed_ids) or len(self._pending_followups) != before_followups
```

Append `source_batch_id: str = ""` to `write_summary()` so all existing positional parameters remain stable. Before importance, novelty, capacity, UUID, indexing, and pending-followup work, return `_find_by_source_batch_id(source_batch_id)` when it finds an item. Pass the field into the new `MemoryItem` only for a new write.

Extend `_add_pending_followup(..., source_batch_id: str = "")` and its serialized entry with the same batch ID, and pass it from `write_summary()`. Old followup entries default to empty. This lets reset finalization remove every side effect of one raced dialogue batch without touching unrelated followups.

Add a top-level `self._flush_commit_receipts: set[str]` to `MemorySystem`, serialized as sorted `flush_commit_receipts` and loaded from an optional list with invalid/empty values discarded. This ledger is independent of L1/L2/L3 and therefore survives compression/removal. Add:

```python
def has_flush_commit(self, batch_id: str) -> bool:
    return bool(batch_id) and batch_id in self._flush_commit_receipts

def record_flush_commit(self, batch_id: str) -> bool:
    if not batch_id:
        return False
    before = len(self._flush_commit_receipts)
    self._flush_commit_receipts.add(batch_id)
    return len(self._flush_commit_receipts) != before

def discard_flush_commit(self, batch_id: str) -> bool:
    if batch_id not in self._flush_commit_receipts:
        return False
    self._flush_commit_receipts.remove(batch_id)
    return True
```

Do not treat a receipt as durable merely because it is present in the current object. Task 6 records it immediately before the main-memory save, removes it in `finally` whenever that save did not return `True`, and only uses it as an ack shortcut after a verified save or after archive restoration.

Extend the real restart path `MemorySystem.merge_kv_archive(data)` to union valid incoming `flush_commit_receipts` into the live set. Do not replace the live set, because a conversation can commit locally while async hydration is in flight. Add the merge test above to the same regression command; `create_from_dict()` round-trip alone is not acceptable evidence for production hydration.

Do not reuse `life_event_id`: it has different source semantics and existing life-simulation callers depend on it. Do not bump `CURRENT_SCHEMA_VERSION`; the new field is optional and follows the existing field-backfill doctrine.

- [ ] **Step 4: Run focused memory tests**

Run: `python -m pytest tests/test_memory_contract_prd.py tests/test_memory_golden_roundtrip.py tests/test_memory_recall_facetE_fixes.py -q`

Expected: all pass, including legacy duplicate-text behavior.

- [ ] **Step 5: Commit**

```bash
git add sylanne_alpha/memory_system.py tests/test_memory_contract_prd.py tests/test_memory_golden_roundtrip.py
git commit -m "feat: make conversation summary writes idempotent"
```

---

### Task 3: Make PersonShelf Writes Idempotent By Batch ID

**Files:**
- Modify: `sylanne_alpha/person_shelf.py:104,161`
- Modify: `tests/test_v250_foundation.py`
- Modify: `tests/test_v250_shelf_write.py`

- [ ] **Step 1: Write failing shelf model tests**

```python
def test_shelf_item_legacy_source_batch_default():
    assert ShelfItem.from_dict({}).source_batch_id == ""


def test_bucket_append_idempotent_returns_existing_item():
    bucket = PersonShelfBucket()
    first = ShelfItem("a", "private", "s", 1.0, 1.0, source_batch_id="batch-a")
    replay = ShelfItem("b", "private", "s", 2.0, 1.0, source_batch_id="batch-a")
    assert bucket.append_idempotent(first) is first
    assert bucket.append_idempotent(replay) is first
    assert [item.text for item in bucket.items] == ["a"]


def test_bucket_empty_source_batch_keeps_legacy_append_behavior():
    bucket = PersonShelfBucket()
    bucket.append_idempotent(ShelfItem("a", "private", "s", 1.0, 1.0))
    bucket.append_idempotent(ShelfItem("a", "private", "s", 2.0, 1.0))
    assert len(bucket.items) == 2


def test_bucket_can_rollback_one_raced_batch_without_clearing_older_items():
    bucket = PersonShelfBucket()
    bucket.append_idempotent(ShelfItem("old", "private", "s", 1.0, 1.0, source_batch_id="old"))
    bucket.append_idempotent(ShelfItem("raced", "private", "s", 2.0, 1.0, source_batch_id="reset-race"))
    assert bucket.remove_by_source_batch_id("reset-race") is True
    assert [item.text for item in bucket.items] == ["old"]


@pytest.mark.asyncio
async def test_save_person_shelf_reports_real_write_result():
    ok = ShelfPlugin()
    assert await save_person_shelf(ok, "qq", "u1", PersonShelfBucket()) is True
    failing = ShelfPlugin(put_error=OSError("injected"))
    assert await save_person_shelf(
        failing, "qq", "u1", PersonShelfBucket()
    ) is False
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m pytest tests/test_v250_foundation.py -q`

Expected: new tests fail because `source_batch_id` and `append_idempotent()` are absent.

- [ ] **Step 3: Add ShelfItem field and bucket operation**

Add `source_batch_id: str = ""` after `schema_ver`, normalize to `str`, serialize it, and load with `d.get("source_batch_id", "")`.

Add to `PersonShelfBucket`:

```python
def append_idempotent(self, item: ShelfItem) -> ShelfItem:
    if item.source_batch_id:
        for existing in self.items:
            if existing.source_batch_id == item.source_batch_id:
                return existing
    self.items.append(item)
    return item

def remove_by_source_batch_id(self, batch_id: str) -> bool:
    before = len(self.items)
    self.items = [item for item in self.items if item.source_batch_id != batch_id]
    return len(self.items) != before
```

Do not make text similarity, origin, or timestamp part of shelf deduplication. Do not change `save_person_shelf()` fail-closed/best-effort behavior in this task.

Change `save_person_shelf(...) -> bool` without changing its best-effort policy: return `False` for an invalid key, missing KV API, or caught write exception, and `True` only after `put_kv_data()` completes. Existing callers may ignore the result; reset finalization uses it to decide whether rollback persistence must retry.

- [ ] **Step 4: Add shelf serialization round-trip coverage**

Extend `test_person_shelf_kv_roundtrip()` with a `source_batch_id="batch-a"` item and assert the loaded item retains that value. Pipeline propagation belongs to Task 6 so this task remains independently green.

- [ ] **Step 5: Run focused shelf tests**

Run: `python -m pytest tests/test_v250_foundation.py tests/test_v250_shelf_write.py -q`

Expected: all shelf model and existing write tests pass with no xfail.

- [ ] **Step 6: Commit**

```bash
git add sylanne_alpha/person_shelf.py tests/test_v250_foundation.py tests/test_v250_shelf_write.py
git commit -m "feat: make person shelf writes batch idempotent"
```

---

### Task 4: Add Ordered Strict Buffer Checkpoints

**Files:**
- Modify: `sylanne_alpha/session_state_store.py:231`
- Modify: `sylanne_alpha/state_persistence.py:185,642,689,711`
- Create: `sylanne_alpha/buffer_file_coordinator.py`
- Modify: `sylanne_alpha/llm_request_pipeline.py:1029`
- Modify: `main.py:1354,2425`
- Create: `tests/test_transactional_buffer_persistence.py`

- [ ] **Step 1: Write failing durability and ordering tests**

Use a fake host whose runtime records `save_buffer()` calls and can fail selected calls, plus a fake KV plugin that can fail selected `put_kv_data()` calls. Implement these exact tests:

- `test_strict_checkpoint_attempts_kv_and_file_and_reports_partial_failure`: seed a claimed pending batch; configure only `runtime.save_buffer()` to raise; await `persist_current_buffer()`; assert the result is `False`, KV contains the pending batch, and both KV/file call counters equal one.
- `test_debounced_writer_snapshots_only_after_acquiring_io_lock`: acquire `get_buffer_persist_lock(session_key)` in the test; start `_do_buffer_persist()` as a task; call `buf.ack_flush(batch_id)` before releasing the lock; await the task; assert its written KV and file snapshots both have `pending_flush is None`.
- `test_prepare_then_ack_cannot_be_overwritten_by_older_debounce_snapshot`: persist a pending prepare; queue `_do_buffer_persist()` behind the I/O lock; ack in memory; run the ack checkpoint and the queued debounce writer to completion; assert the last KV/file snapshots both have `pending_flush is None`.
- `test_no_kv_api_treats_atomic_file_as_the_required_available_sink`: remove `put_kv_data` from the plugin surface; await the checkpoint; assert `True` and assert the file snapshot equals `buf.to_dict()`.
- `test_reconcile_selects_highest_revision_and_repairs_stale_sink`: seed KV with revision 8/pending and file with revision 9/no pending; await reconciliation; assert the live buffer and both persisted sinks equal revision 9/no pending.
- `test_reconcile_is_retryable_until_both_sinks_are_read_and_repaired`: make one sink read or repair fail once; assert the session is not marked reconciled, then clear the fault and assert a second call converges both sinks and marks it reconciled.
- `test_idle_flush_waits_for_reconcile_and_never_commits_replaced_buffer_object`: block reconciliation after it reads a higher KV revision, start `_flush_conversation_to_l1()`, then release; assert flush uses the reconciled live buffer object and the file-bootstrap object's pending batch is never summarized or committed.
- `test_file_revision_fence_rejects_lower_and_divergent_equal_revisions`: write revision 9, then attempt revision 8 and a different revision 9; assert neither changes the file and the divergent equal revision fails closed.
- `test_old_file_writer_finishing_after_reset_cannot_restore_pending`: arrange an old revision-8 pending writer and a revision-9 reset writer in both lock-acquisition orders; assert the final file is always revision 9 with no pending.
- `test_restart_before_reset_finalizer_does_not_revive_late_old_snapshot`: write only the synchronous reset snapshot, let the older writer arrive after it, simulate a restart without running the async finalizer, and assert bootstrap restores the reset epoch/no-pending snapshot.
- `test_sdk_filename_collision_keys_share_one_root_lock_and_fail_closed`: use two distinct session keys that the real SDK maps to the same buffer filename, start concurrent writes through the coordinator, and assert they serialize on one root lock; a divergent equal revision fails closed rather than racing the shared `.tmp`/final file.

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m pytest tests/test_transactional_buffer_persistence.py -q`

Expected: failures because current persistence swallows errors and snapshots before any shared I/O lock.

- [ ] **Step 3: Add dedicated lock ownership to SessionStateStore**

Register plain-dict asyncio lock maps so `release_session()`/`reset_all()` clean them:

```python
self.conversation_flush_locks = self._reg("conversation_flush_locks", {})
self.buffer_persist_locks = self._reg("buffer_persist_locks", {})
self.buffer_reconciled_sessions = self._reg("buffer_reconciled_sessions", {})

def get_conversation_flush_lock(self, session_key: str) -> asyncio.Lock:
    return self.conversation_flush_locks.get_or_create(session_key, asyncio.Lock)

def get_buffer_persist_lock(self, session_key: str) -> asyncio.Lock:
    return self.buffer_persist_locks.get_or_create(session_key, asyncio.Lock)
```

Do not reuse `session_locks`: incoming user observation already holds that lock while appending to `ConversationBuffer`; holding it across summary LLM calls would prevent the required “new message remains active during flush” behavior. Do not reuse `conv_sync_locks`: those are keyed by AstrBot UMO and protect ConversationManager history, not Sylanne buffer files.

Create plugin-owned `BufferFileCoordinator` with a module-level runtime-root-keyed `threading.Lock` registry guarded by one short registry lock. Derive the key from the canonical runtime root only (fall back to runtime identity only for test doubles without a root), not from `session_key` or one `AlphaRuntime` instance. The deliberately coarse root lock makes every SDK-normalized file target under that root mutually exclusive, including distinct raw session keys that collide after SDK `safe_filename()`; buffer file writes are low-frequency enough that correctness is worth this serialization. Its synchronous `write(runtime, session_key, snapshot) -> bool` acquires that lock, calls the existing SDK `runtime.load_buffer(session_key)`, compares non-negative integer revisions, returns `False` for a lower incoming revision, raises on divergent equal revisions, returns `True` without rewriting for an identical equal revision, and calls the existing SDK `runtime.save_buffer(session_key, snapshot)` only for a higher revision or when replacing a legacy file with no revision. The coordinator never reimplements path sanitization, temp-file handling, fsync, or `os.replace()`; those remain owned by SylannEngine. Route every plugin-side buffer file write, including synchronous reset, through this coordinator. Direct `runtime.load_buffer()` reads may remain outside it because SDK writes use atomic replace; do not claim reads are lock-coordinated. Do not modify any file under `sylanne_alpha/_engine/**`.

- [ ] **Step 4: Refactor buffer persistence around a lock-held current snapshot**

Introduce an internal result-preserving writer and a current-buffer checkpoint:

```python
async def _persist_buffer_snapshot(
    self, session_key: str, host: SylanneAlphaHost, buf_dict: dict[str, Any]
) -> bool:
    errors: list[Exception] = []
    if self.has_kv_api():
        try:
            await self._p.put_kv_data(self.buffer_kv_key(session_key), buf_dict)
        except Exception as exc:
            errors.append(exc)
            logger.warning("Sylanne buffer KV persist: %s", exc, exc_info=True)
    try:
        file_ok = bool(
            await asyncio.to_thread(
                self._buffer_files.write,
                host.runtime,
                session_key,
                buf_dict,
            )
        )
        if not file_ok:
            errors.append(RuntimeError("stale buffer file revision rejected"))
    except Exception as exc:
        errors.append(exc)
        logger.warning("Sylanne buffer file persist: %s", exc, exc_info=True)
    return not errors

async def persist_current_buffer(self, session_key: str) -> bool:
    lock = self._p._store.get_buffer_persist_lock(session_key)
    async with lock:
        buf = self._p._store.conversation_buffers.get(session_key)
        host = self._p._store.hosts.get(session_key)
        if buf is None or host is None or not hasattr(host, "runtime"):
            return False
        return await self._persist_buffer_snapshot(session_key, host, buf.to_dict())
```

Add `reconcile_buffer_state(session_key) -> bool` with lock order `conversation_flush_lock` then `buffer_persist_lock`. The once-marker check, both reads, live-buffer replacement, and loser repair all occur while holding the conversation flush lock, so idle flush can never retain an object that reconciliation replaces. Independently read KV and file without early-returning on the first source, discard non-dicts, choose the snapshot with the greatest non-negative `revision`, load it through `ConversationBuffer.from_dict()`, and call `_persist_buffer_snapshot()` with the winner to repair the stale sink. If the winning higher revision has no pending while the loser has one, capture the loser's batch ID and, after buffer repair succeeds, remove its inert MemorySystem receipt and persist that cleanup. Mark `buffer_reconciled_sessions` only after all available reads completed without exception and the repair returned `True`; when KV API is unavailable, a successful file read/write is sufficient. Otherwise leave it retryable. When revisions tie, require canonical serialized equality; log and fail closed instead of guessing between divergent same-revision states.

Retain `persist_buffer(session_key, host, buf_dict)` for compatibility, but make it acquire `get_buffer_persist_lock()` and return the boolean from `_persist_buffer_snapshot()`. Existing callers may ignore the new return value.

Instantiate one `BufferFileCoordinator` in `StatePersistence`. Change `_do_buffer_persist()` to acquire the same asyncio lock **before** fetching the live buffer and calling `to_dict()`, then call `_persist_buffer_snapshot()` directly while holding it. This placement is mandatory for in-loop ordering. The lower-level plugin-owned synchronous file lock/revision fence is a second, independent boundary shared with synchronous reset and off-loop writers; neither lock replaces the other. Add a synchronous `persist_current_buffer_file_sync(session_key) -> bool` delegate for reset that snapshots the live buffer and calls the same coordinator.

Add `main.py` delegate:

```python
async def _persist_current_buffer(self, session_key: str) -> bool:
    return await self._state_persistence.persist_current_buffer(session_key)

async def _reconcile_buffer_state(self, session_key: str) -> bool:
    return await self._state_persistence.reconcile_buffer_state(session_key)
```

At the first request for a session, after `p._host(session_key)` exists but before starting idle flush work or scheduling buffer observation, await `_reconcile_buffer_state(session_key)`. In addition, `_flush_conversation_to_l1()` itself must call this gate before taking its own conversation flush lock and return without claim/summary when reconciliation is incomplete; this protects sessions reached first by the already-running global idle loop. A transient failure leaves the once-marker unset so the next request or idle pass retries. This is the production recovery path that makes a higher-revision ack in either KV or file authoritative and repairs the lagging sink.

- [ ] **Step 5: Run persistence tests**

Run: `python -m pytest tests/test_transactional_buffer_persistence.py -q`

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add sylanne_alpha/session_state_store.py sylanne_alpha/state_persistence.py sylanne_alpha/buffer_file_coordinator.py sylanne_alpha/llm_request_pipeline.py main.py tests/test_transactional_buffer_persistence.py
git commit -m "fix: order durable conversation buffer checkpoints"
```

---

### Task 5: Make Main Memory Persistence Report Commit Success

**Files:**
- Modify: `sylanne_alpha/state_persistence.py:1124`
- Modify: `sylanne_alpha/memory_facade.py:40`
- Modify: `main.py:2597`
- Modify: `tests/test_mem02_restore_wiring.py`

- [ ] **Step 1: Write failing result-contract tests**

Add tests alongside the existing MEM-02 guard tests:

- `test_memory_save_returns_true_after_verified_kv_write`: mark a one-item `MemorySystem` hydrated, await the real `StatePersistence.save_sylanne_memory_state()`, assert the result is `True`, and assert the archive contains that item.
- `test_memory_save_returns_false_when_unhydrated_guard_refuses_write`: seed a non-empty archive, pass a distinct unhydrated state, assert the result is `False`, and assert the seeded archive is byte-for-byte unchanged.
- `test_memory_save_propagates_kv_exception`: make `put_kv_data()` raise `OSError("injected")`; assert awaiting the public method raises that `OSError`.
- `test_memory_save_returns_false_when_throat_fence_rejects_stale_state`: reuse the stale-incarnation setup from `test_stale_ref_save_rejected_blocker1`; assert the returned value is `False` and the current occupant archive remains unchanged.
- `test_ensure_memory_hydrated_waits_for_real_merge_before_flush`: seed an archive containing only `flush_commit_receipts=["batch-a"]`, create an unhydrated live MemorySystem, await `ensure_memory_hydrated("s")`, and assert it returns `True`, `_hydrated is True`, and the live object has the receipt.

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m pytest tests/test_mem02_restore_wiring.py -q`

Expected: new boolean assertions fail because every layer currently returns `None`.

- [ ] **Step 3: Thread the boolean through the existing write throat**

Change `_save_sylanne_memory_state_impl()` to `-> bool` and return `False` on `_refuse_unhydrated_overwrite()` or failed v2 backup gate. Return `True` only after `put_kv_data()` completes. If no KV write API exists, return `False`: in-memory cache mutation is not a durable commit and must not authorize buffer ack.

Change `save_sylanne_memory_state()` to `-> bool`:

```python
fut = self._throat.submit(
    session_key,
    lambda: self._save_sylanne_memory_state_impl(session_key, state),
    kind="write",
    state=state if isinstance(state, MemorySystem) else None,
)
if fut is None:
    return False
return bool(await fut)
```

`MemoryWriteThroat._drain()` already forwards the factory result to the future and sets exceptions on failures, so do not modify the throat.

Return the boolean unchanged through `MemoryFacade.save_sylanne_memory_state()` and `main.py::_save_sylanne_memory_state()`. Existing callers that ignore it remain source-compatible.

Add `StatePersistence.ensure_memory_hydrated(session_key) -> bool`. If the live object is already hydrated, return `True`. Otherwise submit `hydrate_memory_system(session_key)` through the existing per-session MemoryWriteThroat (or await it directly only when the throat is unavailable), await completion, re-fetch the live object, and return its `_hydrated` flag. Expose it through `main.py::_ensure_memory_hydrated()`. Transactional flush treats `False` or an exception as a retryable precondition failure and never summarizes/writes against an unhydrated object.

- [ ] **Step 4: Run memory persistence regression tests**

Run: `python -m pytest tests/test_mem02_restore_wiring.py tests/test_memory_write_throat.py tests/test_memory_golden_roundtrip.py -q`

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add sylanne_alpha/state_persistence.py sylanne_alpha/memory_facade.py main.py tests/test_mem02_restore_wiring.py
git commit -m "fix: expose durable memory commit results"
```

---

### Task 6: Wire Claim/Prepare/Process/Commit/Persist/Ack Into The Pipeline

**Files:**
- Modify: `sylanne_alpha/llm_request_pipeline.py:2656,2961`
- Modify: `main.py:1653`
- Modify: `tests/test_v250_shelf_write.py`
- Create: `tests/test_transactional_conversation_flush.py`

- [ ] **Step 1: Build a fault-injectable pipeline fixture and write failing happy-path tests**

The new test module must provide:

- A shared KV dict used across two fake plugin instances to simulate restart.
- A fake runtime with atomic-snapshot semantics and `fail_save_calls: set[int]`; install its fake host into `plugin._store.hosts` before each checkpoint so `persist_current_buffer()` exercises the production lookup path.
- A fake plugin using real `SessionStateStore`, `StatePersistence`, `MemorySystem`, and `LLMRequestPipeline`, with delegates `_persist_current_buffer()` and `_save_sylanne_memory_state()` returning booleans.
- `AsyncMock` summarizer plus `asyncio.Event` gates for the concurrent-append test.
- Authenticated identity helpers copied in full from `tests/test_v250_shelf_write.py` (private and group shapes); do not parse `session_key` as UMO.

Write the normal case first:

```python
@pytest.mark.asyncio
async def test_normal_flush_commits_once_and_acks_both_buffer_sinks(
    flush_harness,
):
    h = flush_harness
    buf = h.seed_buffer(
        "s",
        [("user", "hello", 100.0), ("bot", "hi", 101.0)],
    )
    await h.pipeline._flush_conversation_to_l1("s")
    assert len(h.memory._l1) == 1
    batch_id = h.memory._l1[0].source_batch_id
    assert batch_id
    assert buf.pending_flush is None
    assert buf.messages == []
    assert h.kv_buffers["s"]["pending_flush"] is None
    assert h.file_buffers["s"]["pending_flush"] is None
    assert h.memory.has_flush_commit(batch_id) is False
```

- [ ] **Step 2: Run the happy-path test and verify RED**

Run: `python -m pytest tests/test_transactional_conversation_flush.py::test_normal_flush_commits_once_and_acks_both_buffer_sinks -q`

Expected: fail because production still calls `drain()` and never writes prepare/ack checkpoints.

- [ ] **Step 3: Extract summary processing without changing summary semantics**

Extract the current `msgs -> summary` block from `_flush_conversation_to_l1()` into:

```python
async def _summarize_conversation_messages(
    self, msgs: list[dict[str, Any]]
) -> tuple[str, bool, str]:
    """Return (summary, has_group_context, sanitized_conversation_text)."""
```

Keep all current behavior: role formatting, 40-message/2000-character truncation, prompt wrapping, content-filter fallback, user/bot fallback text, and three compression rounds. Let an exception from the primary summarizer escape so the transaction can retain pending and apply backoff. Keep the existing PersonShelf slow-path secondary summarizer fail-closed; its failure skips only the optional shelf write.

- [ ] **Step 4: Replace destructive drain with the transaction state machine**

Implement `_flush_conversation_to_l1()` with this exact control order:

```python
async def _flush_conversation_to_l1(self, session_key: str) -> None:
    p = self._p
    try:
        reconciled = await p._reconcile_buffer_state(session_key)
    except Exception as exc:
        logger.warning(
            "Sylanne buffer reconcile failed for %s: %s",
            session_key,
            exc,
            exc_info=True,
        )
        return
    if not reconciled:
        return
    lock = p._store.get_conversation_flush_lock(session_key)
    async with lock:
        buf = p._store.conversation_buffers.get(session_key)
        if buf is None:
            return
        now = time.time()
        pending = buf.pending_flush
        if pending is not None and now < pending.next_retry_at:
            return
        if pending is None:
            pending = buf.claim_flush(now=now)
            if pending is None:
                return

        async def retry(exc: BaseException | None = None) -> None:
            if (
                buf.pending_flush is not None
                and buf.pending_flush.batch_id == pending.batch_id
            ):
                buf.mark_flush_failed(pending.batch_id)
                try:
                    await p._persist_current_buffer(session_key)
                except Exception as persist_exc:
                    logger.warning(
                        "Sylanne retry checkpoint failed for %s: %s",
                        session_key,
                        persist_exc,
                        exc_info=True,
                    )
            if exc is not None:
                logger.warning(
                    "Sylanne transactional flush failed for %s: %s",
                    session_key,
                    exc,
                    exc_info=True,
                )

        try:
            prepared = await p._persist_current_buffer(session_key)
        except Exception as exc:
            await retry(exc)
            return
        if not prepared:
            await retry()
            return

        def pending_is_current() -> bool:
            return (
                buf.flush_epoch == pending.flush_epoch
                and buf.pending_flush is not None
                and buf.pending_flush.batch_id == pending.batch_id
            )

        try:
            hydrated = await p._ensure_memory_hydrated(session_key)
        except Exception as exc:
            await retry(exc)
            return
        if not hydrated:
            await retry()
            return

        memory_system = p._memory_system_for_session(session_key)
        receipt_is_durable = memory_system.has_flush_commit(pending.batch_id)
        committed_now = False

        if not receipt_is_durable:
            try:
                summary, has_context, conv_text = (
                    await self._summarize_conversation_messages(
                        list(pending.messages)
                    )
                )
                if not pending_is_current():
                    return

                # Hydration runs before summary, and this second check closes a
                # defensive hydrate/restore race before the first memory mutation.
                if memory_system.has_flush_commit(pending.batch_id):
                    receipt_is_durable = True
                else:
                    await self._commit_pending_main_memory(
                        session_key, pending, summary
                    )
                    if not pending_is_current():
                        return
                    memory_system.record_flush_commit(pending.batch_id)
                    saved = False
                    try:
                        await p._persist_kernel(session_key, p._host(session_key))
                        saved = bool(
                            await p._save_sylanne_memory_state(
                                session_key, memory_system
                            )
                        )
                    finally:
                        if not saved:
                            memory_system.discard_flush_commit(pending.batch_id)
                    if not saved:
                        await retry()
                        return
                    receipt_is_durable = True
                    committed_now = True
            except Exception as exc:
                memory_system.discard_flush_commit(pending.batch_id)
                await retry(exc)
                return

            if committed_now:
                if not pending_is_current():
                    return
                await self._commit_pending_person_shelf(
                    session_key, pending, summary, has_context, conv_text
                )

        if not receipt_is_durable or not pending_is_current():
            return

        buf.ack_flush(pending.batch_id)
        try:
            acked = await p._persist_current_buffer(session_key)
        except Exception as exc:
            acked = False
            logger.warning(
                "Sylanne flush ack checkpoint raised for %s: %s",
                session_key,
                exc,
                exc_info=True,
            )
        if not acked:
            if buf.restore_flush(pending):
                await retry()
            return

        memory_system.discard_flush_commit(pending.batch_id)
        try:
            cleaned = bool(
                await p._save_sylanne_memory_state(session_key, memory_system)
            )
        except Exception:
            cleaned = False
        if not cleaned:
            memory_system.record_flush_commit(pending.batch_id)
```

Split the current commit block into `_commit_pending_main_memory(...)` and `_commit_pending_person_shelf(...)`. The main helper owns `MemorySystem.write_summary()` and optional embedding; the shelf helper owns only the existing authenticated PersonShelf slow/fast path. They must:

- Read only `pending.messages`, never `buf.messages`.
- Pass `source_batch_id=pending.batch_id` to `write_summary()`.
- Construct the current `ShelfItem` with its existing text/origin/time/weight arguments plus `source_batch_id=pending.batch_id`, then call `shelf_bucket.append_idempotent(item)` instead of direct `items.append()`.
- Persist main memory plus its independent receipt before starting the optional PersonShelf path. Receipt recovery may skip a shelf write that was interrupted; PersonShelf remains explicitly best-effort, while main L1 remains exactly-once.
- Check `flush_epoch` again after every awaited embedding/shelf operation and immediately before each synchronous sink mutation. A stale reset epoch returns without further writes.
- Never ack the buffer inside either helper.

The broad outer `except Exception` in the old method must not swallow prepare or main-memory persistence failure and then allow ack. Both a raised persistence exception and a `False` durability result enter the same retry transition. `finally` must remove an in-memory receipt whenever the corresponding memory save was not verified, so an unsaved receipt can never authorize ack.

Do not hold the generic `p._session_lock()` across this method. Synchronous `ConversationBuffer.append()` calls can run while the method awaits the LLM; the dedicated flush lock prevents a second flush attempt without blocking new active messages.

- [ ] **Step 5: Fence reset against an in-flight summary and finalize raced sinks**

Keep `main.py::_on_session_reset()` synchronous, but before `clear_all()` capture the current `pending_batch_id` and authenticated shelf identity. `clear_all()` increments `flush_epoch`, clears active/pending, and immediately invalidates the in-flight task. Immediately write the new higher-revision buffer snapshot through plugin-side `StatePersistence.persist_current_buffer_file_sync()` before returning from the synchronous hook; Task 4's shared `BufferFileCoordinator` lock and on-disk revision fence are mandatory here, so an older async snapshot that arrives later is rejected. This low-frequency write closes both crash-before-debounce and crash-before-finalizer holes for file bootstrap without editing SylannEngine. Preserve the existing recall-boundary/L1/personality semantics, then schedule this finalizer with `safe_ensure_future` and track it in `_background_tasks`:

```python
async def _finalize_transactional_reset(
    self,
    session_key: str,
    reset_epoch: int,
    pending_batch_id: str,
    shelf_identity: dict[str, str] | None,
) -> None:
    lock = self._store.get_conversation_flush_lock(session_key)
    async with lock:
        buf = self._store.conversation_buffers.get(session_key)
        if buf is None or buf.flush_epoch < reset_epoch:
            return
        for attempt in range(6):
            memory_system = self._memory_system_for_session(session_key)
            if pending_batch_id:
                memory_system.remove_by_source_batch_id(pending_batch_id)
                memory_system.discard_flush_commit(pending_batch_id)
            try:
                memory_ok = bool(
                    await self._save_sylanne_memory_state(
                        session_key, memory_system
                    )
                )
            except Exception:
                memory_ok = False
            try:
                shelf_ok = bool(
                    await self._llm_request_pipeline.rollback_person_shelf_batch(
                        shelf_identity, pending_batch_id
                    )
                )
            except Exception:
                shelf_ok = False
            try:
                buffer_ok = bool(
                    await self._persist_current_buffer(session_key)
                )
            except Exception:
                buffer_ok = False
            if memory_ok and shelf_ok and buffer_ok:
                return
            await asyncio.sleep(min(30.0, 0.5 * (2 ** attempt)))
        logger.error(
            "Sylanne reset finalizer exhausted retries for %s batch=%s",
            session_key,
            pending_batch_id,
        )
```

`rollback_person_shelf_batch(identity, batch_id) -> bool` loads the exact `(platform, sender_id)` bucket from the captured authenticated identity, calls `remove_by_source_batch_id`, and returns the truthful `save_person_shelf()` result when an item was removed. Missing identity/batch or no matching item is already converged and returns `True`. The finalizer waits for an old flush to leave its lock, removes only that captured batch (including its source-tagged pending followup), and retries truthful main-memory/shelf/buffer persistence without clearing messages received after reset. Exhaustion is logged as a residual durability failure; tests inject transient failures and require convergence before the retry budget ends.

- [ ] **Step 6: Add the real shelf propagation test and run integration tests**

Extend `tests/test_v250_shelf_write.py` so a seeded pending batch replayed twice through `_flush_conversation_to_l1()` leaves one `ShelfItem`, and assert that item carries the original pending `batch_id` as `source_batch_id`.

Run: `python -m pytest tests/test_transactional_conversation_flush.py tests/test_v250_shelf_write.py tests/test_issue43_reset_ghost_cleanup.py -q`

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add sylanne_alpha/llm_request_pipeline.py main.py tests/test_transactional_conversation_flush.py tests/test_v250_shelf_write.py
git commit -m "fix: commit conversation flushes transactionally"
```

---

### Task 7: Complete The Crash/Fault Injection Matrix And Regression Gate

**Files:**
- Modify: `tests/test_transactional_conversation_flush.py`
- Modify: `tests/test_transactional_buffer_persistence.py`

- [ ] **Step 1: Add every section 7.2 fault case**

Add these named tests; each must assert final state, not only call counts:

- `test_prepare_failure_never_calls_summarizer_and_replay_recovers_messages`: inject failure into both prepare sinks, assert the summarizer was not awaited, serialize the last successful pre-claim active snapshot, restart, and assert the same role/text/timestamp sequence is claimed with the same computed batch ID.
- `test_summary_exception_persists_pending_and_bounded_retry_metadata`: raise `OSError("summary injected")`, assert pending remains, `attempts == 1`, `next_retry_at - failure_time == 30.0`, a call before that time skips the summarizer, and repeated failures cap the delay at 900 seconds.
- `test_memory_persisted_then_ack_file_failure_restarts_to_one_l1_item`: fail only the file write on the ack checkpoint, assert KV memory has one item and the file buffer still contains pending, restart from those persisted structures, replay, and assert one L1 item with the original batch ID.
- `test_memory_persisted_then_ack_kv_failure_restarts_to_one_l1_item`: fail only buffer KV on ack, assert file has no pending while KV has stale pending, explicitly restore from the stale KV copy to exercise future KV-authority compatibility, replay, and assert one L1 item.
- `test_memory_persist_exception_enters_the_same_bounded_retry_transition`: make `_save_sylanne_memory_state` raise, assert the receipt is removed from the live object, pending remains, attempts increments once, retry metadata is checkpointed, and no ack is attempted.
- `test_old_pending_after_l1_l2_removal_is_stopped_by_durable_receipt`: persist one item plus receipt, simulate L2→L3 removal by removing the item from L1/L2, restart with that memory archive and a stale pending buffer, and assert the summarizer/write path is not called while ack converges.
- `test_same_pending_replayed_many_times_has_one_l1_and_one_shelf_item`: enable cross-session mode, preserve the pending batch across three calls, and after each call assert the sets of matching L1/ShelfItem IDs each have cardinality one.
- `test_same_text_at_different_timestamps_creates_two_batch_ids_and_two_memories`: commit text `"same"` at timestamp 100, append the same text at timestamp 200, commit again, and assert two distinct non-empty batch IDs and two L1 entries.
- `test_message_arriving_while_summarizer_waits_stays_in_active_batch`: gate the summarizer with `asyncio.Event`, append `"new"` after the gate signals entry, release it, and assert pending input/summary source excludes `"new"` while active messages equals one `"new"` entry.
- `test_reset_during_summary_cannot_resurrect_old_batch_or_delete_new_message`: gate the summarizer, call synchronous reset while blocked, append one post-reset message, release the summarizer and await the reset finalizer; assert the captured batch ID is absent from L1, receipts, and PersonShelf, persisted buffer contains only the post-reset message, and no old batch ack occurs.
- `test_reset_finalizer_retries_false_and_exception_results_until_all_sinks_converge`: fail memory save with an exception, shelf save with `False`, and buffer save with `False` on their first calls; assert the finalizer retries, removes the source-tagged pending followup, and returns only after all three report success.
- `test_reset_file_revision_survives_old_writer_and_crash_before_finalizer`: block or delay an old pending file writer so it arrives after the synchronous reset write, omit the async finalizer to simulate immediate process death, restart from disk, and assert the old batch is not restored.
- `test_legacy_buffer_memory_item_and_shelf_item_archives_load_together`: remove `pending_flush` from a buffer dict and `source_batch_id` from L1/shelf dicts; load all three and assert active messages survive and both source IDs default to empty strings.

Crash/restart tests must instantiate a second plugin/pipeline from the persisted KV/file dictionaries; do not reuse the first process's `ConversationBuffer` or `MemorySystem` objects. For ack partial failures, verify the stale pending is actually present in the failed sink before restart, then assert the durable receipt causes both summarizer and `write_summary()` to remain uncalled while ack converges. Separately, the memory-save-failure test covers the pre-durable in-process retry path where `write_summary(source_batch_id=...)` returns the existing L1 item.

For `test_message_arriving_while_summarizer_waits_stays_in_active_batch`, start flush as a task, wait until the mocked summarizer signals entry, append `"new"`, release the summarizer, then assert the committed summary batch excludes `"new"` and `buf.messages` contains exactly that new message.

- [ ] **Step 2: Run the fault matrix**

Run: `python -m pytest tests/test_transactional_conversation_flush.py tests/test_transactional_buffer_persistence.py -vv`

Expected: all named matrix tests pass.

- [ ] **Step 3: Run affected regression suites**

Run:

```bash
python -m pytest tests/test_incident_copywriting_cascade_2026_06_15.py tests/test_issue43_reset_ghost_cleanup.py tests/test_wave1_live_wiring.py tests/test_v250_foundation.py tests/test_v250_shelf_write.py tests/test_v250_shelf_recall.py tests/test_mem02_restore_wiring.py tests/test_memory_contract_prd.py tests/test_memory_golden_roundtrip.py -q
```

Expected: all pass.

- [ ] **Step 4: Run repository verification**

```bash
python C:\Users\pidan\.codex\plugins\cache\pidan-local-plugins\2718lab-devkit\0.1.0\skills\astrbot-plugin-dev\scripts\validate_plugin.py G:\Sylanne-next
python -m ruff check main.py sylanne_alpha tests
python -m pytest -q
```

Expected: plugin validator reports 0 errors; ruff exits 0; full pytest exits 0.

- [ ] **Step 5: Perform the adversarial self-check before commit**

Answer all of these from test evidence:

- Can a debounce task capture a pending snapshot before ack and write it after ack? It must be prevented by snapshot-under-lock.
- Can a writer started before synchronous reset finish after reset and replace the cleared file? The path-scoped `threading.Lock` plus on-disk revision fence must reject the lower revision, including when the process crashes before finalizer execution.
- Can main-memory guard rejection return `None` and accidentally authorize ack? It must return `False` through all delegates.
- Can a second flush task process the same pending concurrently? It must block on `conversation_flush_locks`.
- Can an incoming message be appended while summary LLM is awaited? It must remain in active `messages`.
- Can an old archive lacking any new field load without schema-version migration? It must pass field defaults.
- Can identical text at a later timestamp be suppressed? It must produce another batch ID and another memory.
- Can `/reset` leave a live pending batch in memory? It must call `clear_all()`.
- Can `/reset` run while summary/shelf persistence is awaiting and later resurrect the old batch? The epoch check plus lock-held finalizer must remove only the captured batch and preserve post-reset messages.
- Can a durable batch receipt disappear merely because its MemoryItem compressed into L3? It must remain independent until buffer ack succeeds in both sinks.

- [ ] **Step 6: Commit the completed matrix**

```bash
git add tests/test_transactional_conversation_flush.py tests/test_transactional_buffer_persistence.py
git commit -m "test: cover transactional flush crash recovery"
```

Do not push. The grey build acceptance criterion is local commits only.

---

## Red-Team Findings Resolved

- **Receipt lifetime:** accepted. Task 2 adds an independent durable receipt ledger; Task 7 proves a stale pending cannot duplicate after the source item leaves L1/L2.
- **Ack partial failure:** accepted. Task 6 restores live pending and retries ack without re-summary; Task 4 revisions reconcile and repair KV/file after restart.
- **Reset race:** accepted. Task 1 adds `flush_epoch`; Task 6's lock-held finalizer removes only the captured raced batch and preserves post-reset messages.
- **Late file writer after reset:** accepted. Task 4 makes every plugin-side file writer share `BufferFileCoordinator`'s synchronous lock and disk revision fence while leaving vendored SylannEngine untouched; Task 6/7 prove a lower old snapshot cannot replace the synchronous reset snapshot even if finalization never runs before restart.
- **Persistence exceptions:** accepted. Task 6 maps raised exceptions and `False` results to one bounded retry transition and removes unverified in-memory receipts.
- **Batch scope/integrity:** accepted. Task 1 hashes `session_key` plus canonical messages, recomputes IDs on load, and clamps corrupt retry counters before exponentiation.
- **Grey rollback:** accepted. Task 1 writes a legacy `messages = pending + active` projection alongside `active_messages`, so grey5 may replay but cannot silently lose pending material.
- **PersonShelf global RMW:** retained as an explicit non-blocking residual risk. PersonShelf is best-effort and not the main transaction gate; fixing cross-session lost updates requires a separate per-person lock design.
- **Lock-map growth:** retained as an observable lifecycle risk; locks remain plain dicts to avoid eviction while held and are cleaned by existing session release/reset ownership.

## Failure Injection Map

| Design crash/failure point | Injection seam | Required assertion |
|---|---|---|
| Before pending prepare completes | `put_kv_data(buffer_key)` and `runtime.save_buffer()` | summarizer not called; old active or in-memory pending can be reclaimed |
| After pending prepare, before summary | restart from serialized `ConversationBuffer.pending_flush` | same `batch_id`, same messages |
| Summary failure | `_summarizer_llm_call` raises | pending retained; `attempts += 1`; bounded `next_retry_at` |
| After L1 append, before memory persistence | `_save_sylanne_memory_state` raises/returns `False` | pending retained; in-process replay returns existing L1 item |
| After durable memory, before ack | fail first ack `persist_current_buffer` | restart loads one persisted L1 and stale pending; replay remains one L1 |
| Ack KV/file partial failure | fail KV or file independently on ack call | live pending is restored; durable receipt skips re-summary; restart selects the higher revision and repairs the stale sink |
| L1/L2 compressed before stale replay | remove the source item while retaining receipt | stale pending skips summary/write and continues ack |
| Shelf replay | call same pending repeatedly with cross-session mode on | one ShelfItem with matching `source_batch_id` |
| Concurrent new message | block summarizer with `asyncio.Event`, append while blocked | new message stays active and outside committed batch |
| Concurrent reset | reset while summarizer is blocked, then append a new message | old batch absent from all sinks; new active message survives finalizer |
| Old file writer after reset | delay lower-revision writer until after synchronous reset write, restart before finalizer | reset revision remains authoritative; old pending is not restored |
| Old archive | delete new fields from buffer/L1/shelf serialized dicts | all loaders succeed with empty/default fields |

## Compatibility And Residual Risks

- Existing `*.buffer.json` files have no `pending_flush`; they load as active-only. A grey5 file that was already summarized but never cleared can replay once because its old L1 item has no source ID. The first new-protocol commit is stable thereafter.
- `flush_commit_receipts` is a transient durable tombstone ledger, not a permanent history: a receipt is created only with a verified main-memory commit and removed only after both buffer sinks acknowledge. Failed cleanup can leave an inert receipt, but cannot create or suppress a different real batch because batch IDs include original timestamps.
- Keep `MemorySystem.CURRENT_SCHEMA_VERSION == "3.0.0"`. Optional field backfill is already the repository's migration convention; a version bump would unnecessarily route old archives through broader migration code.
- `save_person_shelf()` remains best-effort and swallows KV failure. The protocol guarantees shelf replay is idempotent, but it does not make the optional shelf a gate for main L1 ack. Changing that privacy/storage contract requires a separate design decision.
- PersonShelf load/append/save is not protected by a per-person read-modify-write lock. The per-session flush lock prevents duplicate replays of one session, but two different sessions for the same identity can still race and lose a shelf update; this is pre-existing and outside sections 5/6/7.2.
- `SessionContext.host()` still performs the synchronous file bootstrap because it cannot await KV. The first async request must run revision reconciliation before buffer observation/flush, promote the higher KV/file revision, and repair the loser; tests cover both stale-file and stale-KV directions.
- `conversation_buffers` is an LRU map with capacity 100. Eviction persistence is not currently wired for buffers. The transaction closes the crash replay hole requested here, but high-cardinality buffer eviction is a separate loss mode and should be tracked independently.
- `/reset` remains a synchronous hook. Its higher-revision buffer clear is written immediately through the atomic file primitive; asynchronous finalization then retries main-memory, optional shelf, KV buffer, and receipt cleanup. If the synchronous local file write itself fails and the process crashes before every async retry, recovery can still see the previous snapshot; this all-durable-sinks-unavailable case is logged and cannot be eliminated without making reset fail visibly to the user.
- Do not use summary similarity, embeddings, Chinese tokenization, or normalized text as a dedupe key. Only the deterministic original-message batch ID authorizes idempotent replay.
