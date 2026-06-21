# Phase 2A Implementation Review Response Review

Date: 2026-06-19
Target: `docs/architecture/life-simulation-upgrade-phase-2a-implementation-review-response.md`
Scope: second review of first-review fixes for PR-D / PR-E / PR-F
Gate: **Changes Requested**. Do not commit yet.

---

## 1. Review Result

The first-review fixes are mostly correct, but the L3 privacy closure is still incomplete.

This review supersedes the short-lived local approval draft: after the independent second pass, I verified that L2 -> L3 compression is a real production path, not a future-only edge. An `internal` L2 memory can still be converted into default-open GraphNode / GraphEdge data and later become user-visible through recall.

Required before approval:

1. Block internal source memories from entering user-visible L3 ingestion, or implement equivalent graph-level privacy propagation with tests.
2. Prevent internal graph nodes from acting as spreading bridges in user-visible ACTIVATION recall.
3. Fix the stale implementation-report wording that still describes the old fail-open behavior.

Do not commit until these are fixed and responded to.

---

## 2. Findings

### BLOCKER: L2 -> L3 Compression Still Can Fail-Open Internal Memory

Files:

- `sylanne_alpha/llm_request_pipeline.py`
- `sylanne_alpha/memory_system.py`

Evidence:

- `llm_request_pipeline._compress_memories()` builds an extraction prompt from `items[:10]` and calls `memory_system.ingest_graph_triples(triples)`.
- `MemorySystem.ingest_graph_triples()` does not read any `privacy_level` from dict triples and has no caller-provided source privacy.
- `_find_or_create_node()` creates `GraphNode(...)` without passing `privacy_level`, so every new L3 node falls back to the dataclass default `"open"`.
- `compress_check()` selects aged L2 items without excluding `privacy_level="internal"`.

Why this blocks approval:

If an internal L2 memory ever reaches the 30-day compression path, the LLM-extracted entities become open L3 graph data. That bypasses the memory-layer `internal` filter because the source object has changed from `MemoryItem(internal)` to `GraphNode(open)`. This violates the Phase 2A hard rule that internal content must not enter user-visible prompt/recall.

Required fix boundary:

- Minimum acceptable fix for Phase 2A: internal L2 items must not be sent into `_compress_memories()` / `ingest_graph_triples()` for user-visible L3. Filter them in `compress_check()` or before prompt construction, and only remove compressed IDs for the actually processed visible items.
- If they choose propagation instead, it must be graph-complete: `ingest_graph_triples()` must accept effective source privacy, `_find_or_create_node()` must receive it, and edge/relation leakage must be handled. Because `GraphEdge` currently has no privacy field, simple node-only propagation is not enough for internal triples whose endpoints already exist as open nodes.
- Direct dict triples with explicit `privacy_level="internal"` must also fail closed: either skip the triple or store it in a graph representation that cannot become user-visible.

Required tests:

- An aged `MemoryItem(privacy_level="internal")` is not compressed into L3 and is not removed as compressed.
- `_compress_memories()` with mixed visible/internal items only sends visible item text to extraction and removes only visible compressed IDs.
- A direct `ingest_graph_triples([{"privacy_level": "internal", ...}])` cannot create user-visible L3 recall output.

### MEDIUM: Internal L3 Nodes Can Still Act As Spreading Bridges

File: `sylanne_alpha/memory_system.py`

Evidence:

- `_recall_activation()` now applies a second privacy filter after `_spreading_candidates()`, so internal nodes themselves do not survive into final `wide`.
- However `_spread_activation()` can still emit an internal node into the intermediate `spread` map.
- The second-hop loop iterates `for sid, sact in list(spread.items())`, so an internal first-hop node can continue propagating activation to a visible second-hop node.

Why this matters:

This is not direct text leakage, but it violates the intended fail-closed graph semantics: internal nodes should not participate in a user-visible recall chain as seeds, results, or bridges.

Required fix boundary:

- Treat `privacy_level="internal"` graph nodes as non-traversable in user-visible spreading.
- Defensively check both the source node and neighbor node inside `_spread_activation()` / `_emit()`, not only the final `wide` list.
- Keep the existing final second privacy filter; it remains a good defense-in-depth layer.

Required test:

- Build `open A -> internal B -> open C`; recall/query that seeds A must not return C through B as a spreading result.

### P3: Implementation Report Still Contains Old Fail-Open Wording

File: `docs/architecture/life-simulation-upgrade-phase-2a-implementation-report.md`

The PR-E section still says:

> `GraphNode 等无属性结构节点→视 open 不误杀`

That is now false and contradicts the second-round code. The current intended behavior is:

- `GraphNode`: explicit `privacy_level`, legacy graph archives migrate to `"open"`.
- Objects without `privacy_level`: fail-closed drop.
- Illegal privacy strings: normalize to `internal`.

Required cleanup: replace that sentence with the current behavior.

---

## 3. Accepted Fixes

These parts of the implementation are accepted and should be kept:

1. `GraphNode` now has `privacy_level`, `__post_init__`, `to_dict`, and `from_dict` migration.
2. `_apply_privacy_filter` drops attrless candidates and returns empty on whole-filter failure.
3. `_recall_activation` performs a second final privacy filter after spreading and emotion bypass.
4. `_recall_l3_candidates` skips edge text when either endpoint is internal.
5. `_prepare_memory_context` defers life_sim memory write until after recall, closing same-round double injection.
6. `_mark_life_outcome` logs warning with event/outcome context and does not raise.
7. `_CALLBACK_ARITY_CACHE` using `__code__` for normal functions / bound methods is accepted as a real correctness fix.

---

## 4. Notes For The Fixing Side

Do not solve the blocker by relying on final recall filtering alone. The problem is that internal information can be transformed into open graph structure before recall ever sees it.

The safest Phase 2A implementation is conservative:

- visible memory may compress into L3;
- internal memory does not compress into user-visible L3;
- if graph privacy is extended later, it needs node and edge/relation semantics, not only GraphNode defaults.

I did not rerun tests per owner instruction. The reported `655 passed / 2 skipped` is accepted as the previous state, but the next response must include targeted regression tests for the two privacy findings above.

---

## 5. Final Gate

**Changes Requested.**

No commit yet. After the fixing side responds, run a third review specifically over:

- internal L2 compression into L3,
- direct internal triple ingestion,
- internal-node spreading bridge,
- stale report wording.
