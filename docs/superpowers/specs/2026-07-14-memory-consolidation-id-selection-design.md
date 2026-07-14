# L1 to L2 Consolidation Selection Design

## Problem

The 12-hour consolidation path asks an LLM for keywords, then compares the full
LLM response with each L1 summary using whitespace-only `split()`. Chinese
summaries commonly contain no spaces, so an entire sentence becomes one token
and almost never intersects with the returned keywords. Scheduled consolidation
therefore confirms few entries, leaving L1-capacity overflow as the effective
promotion path.

## Decision

Replace fuzzy keyword matching with explicit item selection:

1. Present each L1 candidate to the assessor with a stable, request-local numeric
   index.
2. Ask for a JSON array containing only the indexes worth retaining.
3. Parse the response defensively, accepting a bare array or an object containing
   a `selected` array, including a fenced JSON payload.
4. Keep only integer indexes that are present in the current request and map them
   directly to the corresponding memory IDs.
5. Treat malformed, empty, duplicated, boolean, negative, or out-of-range values
   as unselected. Do not fall back to fuzzy keyword matching.

Indexes are request-local rather than persisted identifiers. The prompt still
wraps memory text as untrusted data and explicitly tells the assessor to ignore
instructions inside it.

## Data Flow

```text
L1 snapshot -> numbered assessor prompt -> validated index set -> memory IDs
-> mark_confirmed -> optional embedding -> sink_to_l2 -> persist
```

If the assessor returns no valid selection, no item is promoted and no L1 entry
is deleted by that run. The scheduler records the completed attempt once, at its
existing ownership boundary.

## Tests

Regression coverage will prove that:

- a Chinese summary is promoted when its index is selected;
- English and mixed-language summaries use the same direct mapping;
- fenced JSON and object-form responses are accepted;
- duplicates are de-duplicated;
- booleans, malformed JSON, and out-of-range indexes cannot select memories;
- unselected recent L1 entries remain intact;
- existing embedding and persistence behavior remains unchanged.

## Scope

This change is limited to 12-hour semantic consolidation selection and its tests.
Recall tokenization, manual WebUI sinking, L2/L3 compression, and memory scoring
are out of scope.
