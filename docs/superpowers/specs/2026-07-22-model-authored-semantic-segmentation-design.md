# Model-Authored Semantic Segmentation Design

**Date:** 2026-07-22
**Status:** Approved direction; implementation pending
**Scope:** Realtime intercepted text replies only

## 1. Problem

The current realtime dispatcher treats model-authored newlines and local punctuation/length rules as message boundaries. A real 200-character reply from session `2300184498` therefore became nine separate sends. The pauses and boundaries were mechanically valid but semantically unnatural: setup, elaboration, reversal, and emotional landing were split without understanding their relationship.

The required behavior is not a larger state machine. The response model must understand the complete reply and author its own conversational beats. Local code may validate, schedule, and fail safely, but it must not decide the semantic grouping in the normal path.

## 2. Goals

- Let the same model that writes the reply choose semantic/emotional message boundaries.
- Let the model classify the pause before each following beat as `soft`, `normal`, or `deep`.
- Add no second LLM call and no new model/provider configuration.
- Preserve the visible response exactly after removing plugin-owned control markers.
- Keep control markers out of both outbound messages and AstrBot conversation history.
- Prefer one intact message when a plan is missing or invalid; use deterministic splitting only as an anti-flood safety fallback for exceptional oversized output.
- Preserve interruption, unfinished-reply, non-text result-chain, cron, and streaming safety behavior.

## 3. Non-goals

- The local runtime will not infer semantic boundaries from punctuation, keywords, length bands, or dialogue-state transitions in the normal path.
- The planner will not rewrite, summarize, reorder, or delete response text.
- The feature will not add a planner provider, structured-output dependency, tool call, or persistent model-specific state.
- Markdown-heavy deliverables, code blocks, tables, URLs, and non-Plain result chains will not be aggressively fragmented.

## 4. Model-authored beat contract

When realtime chat and response interception are both enabled, the request pipeline appends a compact system-level contract. The contract gives the model three exact marker strings containing a per-turn nonce, for example:

```text
<syl-beat nonce="A7K3Q2" pause="soft"/>
<syl-beat nonce="A7K3Q2" pause="normal"/>
<syl-beat nonce="A7K3Q2" pause="deep"/>
```

The model may insert zero to five markers into its reply. It chooses zero markers when the reply is naturally one message. It inserts markers only between complete conversational beats and never inside a code span/fence, URL, table row, or protected structured token.

The nonce makes the markers plugin-owned and turn-scoped. A literal marker-like string from user content cannot be stripped unless it exactly contains the nonce generated for that turn.

The contract explicitly says:

1. Write the response normally first; markers are invisible delivery controls.
2. Do not change wording to accommodate markers.
3. Prefer fewer complete beats over many short bubbles.
4. Use `deep` only for an intentional reveal, reversal, hesitation, or emotional landing.
5. Never explain or quote the marker contract.

The model remains the only semantic planner. Local code merely parses the exact marker grammar.

## 5. Parse and validation contract

The response pipeline receives the raw completion and the turn-scoped nonce. Parsing produces:

```python
SemanticBeatPlan(
    clean_text: str,
    parts: tuple[SemanticBeatPart, ...],
    accepted: bool,
    rejection_reason: str | None,
)
```

Each `SemanticBeatPart` contains the exact text slice and the pause class that precedes it. Validation requires:

- only the three exact nonce-bound marker forms;
- at most six non-empty visible parts;
- no marker inside protected structured regions;
- removing all exact markers yields `clean_text` byte-for-byte;
- concatenating all accepted part texts yields `clean_text` byte-for-byte;
- every delivered part contains at least one non-whitespace character.

No validator rule selects a boundary. It only accepts or rejects boundaries authored by the model.

On rejection, the pipeline first strips every exact turn-owned marker so control text cannot leak. It then sends `clean_text` as one message. Only output beyond a separate hard anti-flood threshold may reuse the existing deterministic splitter, capped by the existing maximum-part safety limit.

## 6. Pause scheduling

The model supplies a semantic pause class, not seconds. The existing body/rhythm layer maps the class to a bounded delay while retaining modest jitter:

- `soft`: continuity; short pause;
- `normal`: next complete thought; ordinary typing pause;
- `deep`: reveal, reversal, or emotional landing; longer bounded pause.

Body-driven typing speed, incoming-message think delay, night rhythm, cancellation, and interruption remain active. The random “distracted pause” must not override an explicit semantic class. Numeric ranges remain implementation details covered by deterministic tests.

## 7. AstrBot lifecycle and history cleanliness

AstrBot v4.26.5 provides the required order and public hooks:

1. The runner appends the original assistant `TextPart` to `run_context.messages`.
2. `OnLLMResponse` runs.
3. `OnAgentDone(event, run_context, response)` runs.
4. The same `run_context.messages` is persisted.
5. The decorated result is sent.

Sylanne uses three independent scrub points:

- **OnLLMResponse:** parse markers, set `response.completion_text` to clean text, create the beat plan, and store a bounded raw/clean correlation record in event extras.
- **OnAgentDone:** find the final assistant text only when it exactly matches the correlated raw completion, then replace it with clean text before history persistence. Other reasoning, tool, image, and audio parts are untouched.
- **OnDecoratingResult:** strip any exact turn-owned marker still present in outgoing Plain components as a final leak guard.

The contract is injected only on the already non-streaming realtime-intercept path. If streaming is in flight, semantic markers are never requested and takeover is abandoned as today.

## 8. Integration with existing dispatch

`realtime_plan` accepts an optional validated semantic plan. When present, it skips `_split_text` and builds message parts directly from the model-authored slices. When absent, normal short output is a single message; exceptional oversized output uses the safety splitter.

The unfinished-reply buffer is derived from the exact remaining semantic slices, not by lossy `strip()`/substring reconstruction. Cancelling a segmented task therefore leaves a clean, correctly ordered remainder.

Non-Plain result chains, cron replies, empty-reply handling, first-sentence streaming takeover, history ownership, and response observation retain their existing guards.

## 9. Observability and privacy

Log only:

- whether a semantic plan was accepted;
- part count and pause-class counts;
- rejection reason enum;
- fallback kind (`single` or `oversize_safety`).

Do not log reply text or raw marker-bearing completions. The existing v3 isolation counter `v3_extra_llm_call_count` must remain zero.

## 10. Test and acceptance matrix

- Exact marker removal and byte-for-byte text conservation.
- Zero-marker one-message reply.
- All three pause classes and deterministic delay mapping.
- Wrong nonce, unknown pause, malformed tag, too many parts, empty part, and marker-in-structure rejection.
- Invalid-plan fallback sends one clean message for ordinary-length replies.
- Oversized invalid output uses only the capped safety splitter.
- OnLLMResponse, OnAgentDone, and OnDecoratingResult each prevent leakage independently.
- Conversation history contains clean text only.
- The supplied 2026-07-22 wish reply can be model-planned into approximately five complete beats without local semantic grouping.
- Non-Plain result chains and active streaming remain untouched.
- Interrupted delivery stores and resumes the exact clean remainder.
- AstrBot 4.26.5 integration and existing realtime regression suites pass.

## 11. Rollout

The feature follows the existing realtime/intercept switches and needs no new default-visible setting. A temporary internal diagnostic flag may log acceptance/rejection counts during grey rollout, but it must not create another user-facing model choice. Rollback is removal of the request contract and optional-plan argument; the anti-flood safety path remains available.
