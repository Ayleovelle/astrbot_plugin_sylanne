# Grey.4 Conversation History Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist complete third-party Agent turns without duplicating internal Agent history, then package and push `2.5.0-grey.4`.

**Architecture:** Keep AstrBot's internal `_save_to_history` as the sole writer when its predicate is satisfied. Otherwise, call one awaited `StatePersistence.sync_turn_to_conv_mgr` operation that locks by resolved UMO and appends user plus optional assistant in one update.

**Tech Stack:** Python 3.13, asyncio, AstrBot v4.26.5 ConversationManager, pytest, ruff, zip packaging.

---

### Task 1: Lock the Third-Party Regression in Tests

**Files:**
- Create: `tests/test_grey4_third_party_history_fallback.py`
- Read: `main.py:1786`, `main.py:2225`, `main.py:2312`
- Read: `sylanne_alpha/state_persistence.py:2432`

- [ ] **Step 1: Write failing tests**

Define a ConversationManager-compatible fake that returns JSON-string history and counts updates. Bind the production framework predicate and fallback method to a minimal plugin host. Assert:

```python
assert roles(history) == ["user", "assistant"]
assert conv_mgr.update_count == 1
assert event.get_extra("_syl_turn_backfilled") is True
```

Also assert internal requests produce zero plugin updates, empty assistant responses produce `["user"]`, failed updates do not consume the guard, and two session keys mapped to one UMO do not lose either turn.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest -q -p no:cacheprovider tests/test_grey4_third_party_history_fallback.py
```

Expected: failures because `_backfill_turn_if_framework_skips` and `sync_turn_to_conv_mgr` do not exist and current behavior only writes user.

### Task 2: Add Atomic UMO-Keyed Turn Persistence

**Files:**
- Modify: `sylanne_alpha/state_persistence.py:2432`
- Test: `tests/test_grey4_third_party_history_fallback.py`

- [ ] **Step 1: Implement the shared entry-list primitive**

Add helpers with these responsibilities:

```python
def _resolve_conv_umo(self, session_key: str) -> str: ...
def _conv_history_entry(role: str, text: str) -> dict[str, Any]: ...
async def _do_sync_entries_to_conv_mgr(
    self, conv_mgr: Any, umo: str, entries: list[dict[str, Any]]
) -> bool: ...
```

The primitive must parse history fail-closed, preserve the existing assistant idempotence check, append all entries to one snapshot, sanitize tool pairing once, call `update_conversation` once, and return `True` only after that call succeeds.

- [ ] **Step 2: Add the public turn operation**

```python
async def sync_turn_to_conv_mgr(
    self, session_key: str, user_text: str, assistant_text: str = ""
) -> bool:
    entries = [self._conv_history_entry("user", user_text)]
    if assistant_text:
        entries.append(self._conv_history_entry("assistant", assistant_text))
    return await self._sync_entries_with_umo_lock(session_key, entries)
```

Resolve UMO before `get_conv_sync_lock(umo)`. Refactor `sync_message_to_conv_mgr` to reuse the same path and return `bool`.

- [ ] **Step 3: Run focused state tests**

Run the new test file plus `tests/test_conv_mgr_sync_race.py`. Expected: persistence-unit tests pass; main fallback tests may still fail until Task 3.

### Task 3: Converge Framework-Skip Turns in Main

**Files:**
- Modify: `main.py:1541`
- Modify: `main.py:1786`
- Modify: `main.py:2219`
- Modify: `main.py:2312`
- Test: `tests/test_grey4_third_party_history_fallback.py`
- Test: `tests/test_user_backfill_on_silent.py`
- Test: `tests/test_err_turn_user_backfill.py`

- [ ] **Step 1: Add the state-persistence delegate**

```python
async def _sync_turn_to_conv_mgr(
    self, session_key: str, user_text: str, assistant_text: str = ""
) -> bool:
    return await self._state_persistence.sync_turn_to_conv_mgr(
        session_key, user_text, assistant_text
    )
```

- [ ] **Step 2: Replace user-only convergence with turn convergence**

Implement `_backfill_turn_if_framework_skips(event, response)` so it:

```python
if self._framework_will_persist_this_turn(event, response):
    return
user_text = self._text(event)
assistant_text = normalized assistant completion only for a non-stopped assistant response
saved = await self._sync_turn_to_conv_mgr(session_key, user_text, assistant_text)
if saved:
    event.set_extra("_syl_turn_backfilled", True)
```

Retain `_backfill_user_if_framework_skips` as a compatibility wrapper. Route both response-finally and after-message-sent callers through the new method.

- [ ] **Step 3: Verify GREEN**

Run all four affected history/realtime test files. Expected: all pass; the new third-party case contains one ordered pair while existing internal/SILENT assertions remain unchanged.

### Task 4: Grey.4 Release Metadata and Packaging

**Files:**
- Modify: `metadata.yaml`
- Modify: `CHANGELOG.md`
- Modify: `README.md:467`
- Modify: `astrbot_plugin_sylanne.zip` via `scripts/package_plugin.py`
- Create: `dist/astrbot_plugin_sylanne-2.5.0-grey.4.zip`
- Replace locally: `dist/astrbot_plugin_sylanne.zip`

- [ ] **Step 1: Update release text**

Set metadata version and short description to `2.5.0-grey.4`. Add a CHANGELOG section describing third-party Agent user-only/empty history, atomic turn fallback, UMO locking, and corrected package guidance. Change README installation to the grey.4 Release asset/versioned package and state that generic packages must report the same metadata version.

- [ ] **Step 2: Build all package names from one source**

```powershell
python scripts/package_plugin.py --output dist/astrbot_plugin_sylanne-2.5.0-grey.4.zip
python scripts/package_plugin.py --output dist/astrbot_plugin_sylanne.zip
python scripts/package_plugin.py --output astrbot_plugin_sylanne.zip
```

Verify all three archives contain metadata version `2.5.0-grey.4` and identical plugin source hashes.

### Task 5: Verification, Review, and Push

**Files:**
- Verify all modified files and generated archives.

- [ ] **Step 1: Run functional verification**

Run the affected tests, full pytest suite, ruff, py_compile, AstrBot v4.26.5 real SQLite matrix, package preflight, `validate_plugin.py`, and `check_release.py`. Every command must exit zero except explicitly reviewed release-validator warnings caused by prerelease version policy.

- [ ] **Step 2: Run adversarial review**

Review internal double-write, third-party pair ordering, SILENT/error user-only behavior, failed-write retry guard, same-UMO concurrency, archive version drift, and stale generic packages. Resolve every blocker before release.

- [ ] **Step 3: Commit and push**

Stage only grey.4 files, commit with a scoped message, push `feat/embodiment-2.5.0` to the `github` remote, and report the commit and package SHA-256.
