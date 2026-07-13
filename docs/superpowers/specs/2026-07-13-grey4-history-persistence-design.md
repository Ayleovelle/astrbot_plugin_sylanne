# Grey.4 Conversation History Persistence Design

## Status

Approved on 2026-07-13. The user accepted the recommended awaited, atomic turn fallback after the grey.3 diagnosis and requested a grey.4 release.

## Goal

Ensure every normal third-party Agent response that reaches Sylanne is persisted to AstrBot's `conversations` history as one ordered `[user, assistant]` turn, while preserving the internal Agent's single authoritative framework write and SILENT/error behavior.

## Considered Approaches

1. Set `skip_conv_sync=False` for third-party responses. Rejected: bot sync is currently scheduled before the response-finally user backfill and can persist `[assistant, user]`.
2. Keep independent user and bot writes but await both. Rejected: two read-modify-write cycles expose partial turns and add another lost-update boundary.
3. Add one awaited atomic turn fallback. Selected: when AstrBot will not persist the turn, append user and optional assistant entries under one UMO-keyed lock and perform one ConversationManager update.

## Architecture

`StatePersistence` gains `sync_turn_to_conv_mgr(session_key, user_text, assistant_text) -> bool`. It resolves `session_key` to the AstrBot UMO before taking the lock, builds serializable message dictionaries, appends the complete turn to one history snapshot, and writes once. Existing single-message sync reuses the same entry-list primitive and also locks by UMO.

The response-finally convergence point becomes `_backfill_turn_if_framework_skips`. It first preserves the current internal-runner predicate: when AstrBot will save, the plugin performs zero ConversationManager writes. Otherwise it writes user-only for SILENT/error/stopped responses, or `[user, assistant]` for a normal non-empty assistant response. The event once-guard is consumed only after `sync_turn_to_conv_mgr` reports a successful database update.

The response pipeline continues using `skip_conv_sync=True`; it only updates Sylanne's private `ConversationBuffer`. This keeps bot delivery/observation separate from authoritative AstrBot history persistence.

## Invariants

- Internal Agent normal turn: plugin writes zero entries; framework saves exactly one full turn.
- Third-party Agent normal text turn: plugin performs one awaited update containing `[user, assistant]`.
- SILENT/error/stopped turn: fallback contains only `[user]`.
- Corrupt history or database failure: no overwrite and no consumed once-guard.
- Different Sylanne session keys mapped to the same UMO share the same lock.
- The fallback never writes `[assistant, user]` and never creates two separate database updates for one turn.

## Error Handling

ConversationManager absence returns `False`. Invalid history remains fail-closed. Database/API exceptions are logged and return `False`; callers do not mark the turn complete, allowing a later same-event fallback hook to retry. Existing internal framework-save behavior remains unchanged.

## Tests

Add a focused grey.4 regression suite using the production `StatePersistence` and main convergence methods with a ConversationManager-compatible test database shape. Tests cover internal zero-write, third-party atomic pair, SILENT user-only, one-update ordering, failed-write guard behavior, and two session keys sharing one UMO lock. Re-run the existing history/realtime suites and the AstrBot v4.26.5 SQLite matrix.

## Release

Bump metadata to `2.5.0-grey.4`, add a CHANGELOG entry, correct README installation guidance, regenerate the versioned package and both generic package paths from the same tracked source, run the AstrBot plugin and release validators, then push the current `feat/embodiment-2.5.0` branch.

## Out Of Scope

Grey.4 does not change AstrBot's WebUI rule that hides `webchat` rows, persist non-text third-party media payloads, or reorder third-party turns that genuinely complete and are delivered out of input order.
