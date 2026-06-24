# Phase 2A Implementation Round 3 Review

Date: 2026-06-20
Target: `docs/architecture/life-simulation-upgrade-phase-2a-implementation-review-response-review-response.md`
Scope: third review of privacy closure fixes after the Round 2 `Changes Requested`
Gate: **Approved to Commit**. Do not push without owner approval.

---

## 1. Review Result

No blocking findings remain.

The Round 2 BLOCKER and MEDIUM findings are closed under the conservative Phase 2A boundary:

1. `internal` L2 memories do not enter the production L2 -> L3 compression path.
2. Explicit `internal` graph triples are fail-closed at ingest.
3. `internal` L3 nodes no longer act as ACTIVATION spreading seeds, results, or bridges.
4. The stale implementation report wording about attrless objects being treated as `open` has been corrected.

I did not rerun tests per owner instruction. I reviewed the implementation and accept the fixing side's reported result: `659 passed / 2 skipped / 0 failed`.

---

## 2. Closed Findings

### 2.1 BLOCKER: L2 -> L3 Compression Could Wash Internal Memory Into Open Graph

Status: **Closed**

Evidence:

- Production maintenance calls `memory_system.compress_check()` before scheduling `_compress_memories(...)`.
- `compress_check()` now excludes aged L2 items whose normalized `privacy_level` is `"internal"`.
- Therefore `_compress_memories()` receives only visible compression candidates on the current production path.
- `remove_compressed([item.id for item in items[:10]])` removes only the already-filtered candidates that were actually passed into the compression task.
- `ingest_graph_triples()` defensively skips dict triples with explicit `privacy_level="internal"` and logs a warning.

Accepted boundary:

- Phase 2A intentionally does not introduce graph-level privacy propagation, because `GraphEdge` has no privacy field and node-only propagation cannot protect relation leaks when endpoints already exist as open nodes.
- The conservative rule is therefore: internal memory does not enter user-visible L3 at all.

Targeted coverage reviewed:

- `test_compress_check_excludes_internal_l2`
- `test_ingest_internal_triple_not_user_visible`
- `test_ingest_open_triple_still_works`

### 2.2 MEDIUM: Internal L3 Nodes Could Act As Spreading Bridges

Status: **Closed**

Evidence:

- `_spread_activation()` skips an internal neighbor before adding it to `spread`.
- First-hop internal seeds are skipped and never used as spreading sources.
- Because second-hop traversal iterates `spread.items()`, an internal first-hop node cannot become a bridge to an open second-hop node.
- The final second `_apply_privacy_filter()` after spreading remains in place as defense-in-depth.

Targeted coverage reviewed:

- `test_internal_node_not_spreading_bridge`

### 2.3 P3: Stale Fail-Open Report Wording

Status: **Closed**

Evidence:

- `life-simulation-upgrade-phase-2a-implementation-report.md` now says MemoryItem / GraphNode explicitly hold `privacy_level`, legacy graph archives migrate to `"open"`, illegal values normalize to `internal`, and objects without `privacy_level` fail-closed drop.
- The old "attrless structural nodes are treated as open" wording is gone from the active implementation report.

---

## 3. Non-Blocking Discipline Note

`_compress_memories(session_key, items)` itself still trusts its caller and does not re-filter `items` for `privacy_level="internal"` before prompt construction.

This is not a commit blocker for Phase 2A because:

- the current production caller obtains `items` from `compress_check()`;
- `compress_check()` is now the privacy gate and excludes internal L2 items;
- the previous review allowed the minimum fix boundary to be either filtering in `compress_check()` or filtering before prompt construction.

However, this is now a standing rule:

- Do not add any new `_compress_memories(...)` caller unless it goes through `compress_check()` or performs the same internal filter at the call site.
- If `_compress_memories()` becomes a public-ish API, job entrypoint, command, or test helper used outside the maintenance path, move the same filter into `_compress_memories()` as sink-side defense.
- Phase 2B graph privacy work must decide node + edge/relation visibility together; do not implement node-only privacy propagation and call it complete.

---

## 4. Accepted Existing Fixes

These previously accepted Phase 2A fixes remain accepted:

1. `MemoryItem` fields and normalization: `confidence`, `privacy_level`, `life_event_id`.
2. `GraphNode.privacy_level` roundtrip and legacy migration.
3. `_apply_privacy_filter` fail-closed behavior for attrless objects and whole-filter exceptions.
4. ACTIVATION final `wide` re-filter after spreading / emotion bypass.
5. L3 edge-fragment neighbor-label privacy guard.
6. Deferred life_sim memory write after current-round recall.
7. `_mark_life_outcome` warning instead of silent swallow.
8. `_CALLBACK_ARITY_CACHE` using `__code__` for ordinary functions and bound methods.

---

## 5. Final Gate

**Approved to Commit.**

Allowed in the commit:

- implementation fixes in `sylanne_alpha/memory_system.py` and `sylanne_alpha/llm_request_pipeline.py`;
- all Phase 2A targeted tests;
- implementation report updates;
- Round 2 / Round 3 review-response documents;
- this Round 3 review document.

Do not push until the owner explicitly approves push.
