# Group Invocation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Also use `test-driven-development` for every behavior change.

**Goal:** Make every explicit group invocation enter the normal AstrBot LLM/history path exactly once, while ordinary group chatter remains subject to SFPD silence and synthetic empty-call text never enters Sylanne L1 material.

**Architecture:** A pure classifier produces one event-scoped invocation record from public AstrBot event/component APIs. A dedicated maximum-priority message handler runs before AstrBot's built-in empty-mention waiter, creates the one exceptional ProviderRequest only for an empty call that Sylanne owns, and binds it to the current AstrBot `Conversation`. The existing request pipeline consumes the cached intent, bypasses SFPD only for explicit calls, and injects empty-call guidance through transient `system_prompt` text.

**Tech Stack:** Python 3.10+, asyncio, AstrBot v4.26.5 public event/component APIs, pytest, `types.MethodType`, `unittest.mock.AsyncMock`.

---

## Grounded Constraints

- `EmotionalStatePlugin.on_message(self, event, *args, **kwargs)` currently runs at default priority. AstrBot's built-in `handle_empty_mention` runs at `priority=sys.maxsize - 1`, yields its own request, waits, and finally calls `stop_event()`. The new classifier/capture handler must therefore use `priority=sys.maxsize` (larger runs first); changing only the existing default-priority handler cannot fix pure `@`.
- AstrBot v4.26.5 also registers its session-control handler at `priority=sys.maxsize` before plugin handlers. Python's handler sort is stable, and `StarRequestSubStage` breaks immediately after that built-in handler stops the event, so an active `session_waiter` consumes the next message before `on_group_invocation` can run. This exact 4.26.5 registration-order/ProcessStage contract is the supported guard; do not inspect private waiter registries or invent a public waiter API that does not exist.
- The capture handler must be an async generator. When it owns an empty call it calls public `event.should_call_llm(True)` to disable the later default Agent chain, yields exactly one `event.request_llm(...)`, then stops plugin propagation in `finally` so the lower-priority built-in handler cannot create a second request. `stop_event()` alone is insufficient because ProcessStage's default-Agent condition does not consult it. Empty direct/core calls are owned only when realtime takeover is fully enabled; otherwise they yield nothing and preserve AstrBot's built-in empty-mention behavior. A configured trigger-only call is the explicit exception: AstrBot's built-in empty-mention handler does not own plugin names, so Sylanne always owns that normalized request.
- Public `event.request_llm(prompt, ..., conversation=Conversation)` records into the supplied conversation. A prebuilt request with `conversation=None` is not automatically rebound to the current conversation/history.
- Resolve the current conversation by mirroring AstrBot v4.26.5 `astrbot.core.astr_main_agent._get_session_conv`, using only the public manager exposed by `self.context.conversation_manager`:
  1. `cid = await manager.get_curr_conversation_id(event.unified_msg_origin)`;
  2. if missing, `cid = await manager.new_conversation(umo, event.get_platform_id())`;
  3. `conversation = await manager.get_conversation(umo, cid)`;
  4. if still missing, create once more and fetch once more;
  5. if still missing, raise `RuntimeError` and fail open to the later AstrBot core path (do not stop the event). A custom trigger already has the official wake flag, so the default Agent path can still create a conversation-bound request even though the specialized normalized request failed.
- Do not import `TextPart` from a provider/internal module. The public provider surface does not export it. Carry the synthetic marker through event extra and add the one-turn instruction in the existing `on_llm_request` pipeline by appending to `request.system_prompt`, which AstrBot does not persist as user history.
- `event.is_at_or_wake_command` is the official fallback when an event-scoped classification is absent. Do not read the nonexistent `event.is_at` or `event.at_bot` fields.
- Never prebuild a request for At + image/record/file/video or quote payloads: doing so would bypass AstrBot's normal attachment/quoted-message assembly. Those turns keep their message chain and use the core-built ProviderRequest.

## Task 1: Pure Invocation Classifier

**Files:**
- Create: `sylanne_alpha/group_invocation.py`
- Create: `tests/test_group_invocation.py`

- [ ] **Step 1: Write RED tests for the complete classification matrix**

Add tests named:

- `test_direct_at_targets_bot_and_not_other_members`
- `test_reply_bot_uses_reply_sender_id`
- `test_official_wake_falls_back_to_core_wake`
- `test_trigger_names_split_ascii_and_chinese_commas`
- `test_trigger_name_requires_start_boundary`
- `test_cjk_trigger_allows_natural_suffix_without_separator`
- `test_ascii_trigger_allows_cjk_suffix_but_rejects_ascii_word_continuation`
- `test_mixed_trigger_uses_its_final_character_for_boundary`
- `test_name_discussed_mid_sentence_stays_ambient`
- `test_pure_at_and_pure_trigger_are_empty_calls`
- `test_at_with_image_record_file_video_or_reply_is_not_empty`

Use real public component classes via `pytest.importorskip("astrbot.api.message_components")`, following `tests/test_v250_realtime_send_save_decoupling.py`. The event fake should expose `message_obj.message`, `message_str`, `is_at_or_wake_command`, `get_self_id()`, `get_extra()`, and `set_extra()`.

- [ ] **Step 2: Verify RED**

Run: `pytest -q tests/test_group_invocation.py`

Expected: collection fails because `sylanne_alpha.group_invocation` does not exist.

- [ ] **Step 3: Implement the side-effect-free classifier**

Create these public symbols:

- `GROUP_INVOCATION_EXTRA = "_sylanne_group_invocation"`
- `SYNTHETIC_EMPTY_CALL_EXTRA = "_sylanne_synthetic_empty_call"`
- `EMPTY_CALL_HISTORY_TEXT = "（用户仅呼叫了你，没有附带文字）"`
- frozen `GroupInvocation(kind, source, trigger_name="")`
- `parse_trigger_names(config: dict | None) -> tuple[str, ...]`
- `classify_group_invocation(event: Any, config: dict | None) -> GroupInvocation`
- `get_cached_group_invocation(event: Any) -> GroupInvocation | None`

`kind` is one of `ambient/direct_at/reply_bot/core_wake/trigger_name/empty_call`; `source` preserves the explicit source when `kind == "empty_call"`. Parse `sylanne_persona_name` plus `sylanne_group_attention_trigger_names`, split strings on both `,` and `，`, strip, casefold, and deduplicate in order. Trigger-name matching ignores leading whitespace and requires the name at the start. Boundary behavior follows the trigger's final character: when it ends in ASCII `[A-Za-z0-9_]`, the next character must not be another ASCII word character (so `Sylanne你好` is valid and `Sylannefoo` is not); when it ends in CJK, a natural suffix such as `小澜你好` is valid without an artificial space. Apply the same rule to mixed names such as `小澜AI`. A name discussed away from the start remains ambient.

Inspect only `Comp.At`, `Comp.Reply`, `Comp.Image`, `Comp.Record`, `Comp.File`, `Comp.Video` and public event members. A direct At must target `event.get_self_id()`; a reply must have `sender_id == event.get_self_id()`. A Reply or any media component is payload, so it prevents `empty_call` even when text is empty.

- [ ] **Step 4: Verify GREEN and commit**

Run: `pytest -q tests/test_group_invocation.py`

Commit:

```text
git add sylanne_alpha/group_invocation.py tests/test_group_invocation.py
git commit -m "feat(group): classify explicit invocations once"
```

## Task 2: Priority Capture and Conversation-Bound Empty Requests

**Files:**
- Modify: `main.py`
- Modify: `tests/test_group_invocation.py`

- [ ] **Step 1: Write RED tests for handler ordering, ownership, and conversation binding**

Add tests named:

- `test_invocation_handler_priority_precedes_builtin_empty_mention`
- `test_realtime_off_leaves_empty_at_for_builtin_handler`
- `test_realtime_takeover_yields_one_request_then_stops_event`
- `test_owned_empty_call_disables_default_llm_chain`
- `test_empty_request_binds_existing_current_conversation`
- `test_empty_request_creates_missing_current_conversation`
- `test_stale_current_conversation_retries_create_and_fetch_once`
- `test_conversation_resolution_failure_fails_open_without_stopping`
- `test_trigger_only_yields_normalized_request_without_realtime_takeover`
- `test_trigger_name_sets_official_wake_flag_without_prebuilding_media_request`
- `test_process_stage_owned_empty_call_runs_one_provider_request_and_saves_one_history_pair`
- `test_active_session_waiter_is_not_stolen_by_invocation_handler` (drive the real v4.26.5 `StarRequestSubStage` with a registered active waiter; assert the built-in max-priority handler stops the stage before the Sylanne handler is invoked; this upgrade tripwire must not use `pytest.importorskip` or otherwise report a silent skip in the release verification environment)

Reuse the `types.MethodType` minimal-plugin pattern from `tests/test_v250_foundation.py` and the `get_extra/set_extra` event fake pattern from `tests/test_err_turn_user_backfill.py`. Drive the async-generator handler with `async for` so the test proves there is one yielded ProviderRequest, and resume it to completion so `stop_event()` is observed. The fake conversation manager must assert the exact public call sequence listed under Grounded Constraints.

- [ ] **Step 2: Verify RED**

Run: `pytest -q tests/test_group_invocation.py -k "priority or realtime or conversation or trigger_name_sets"`

- [ ] **Step 3: Add the dedicated early handler and resolver**

In `EmotionalStatePlugin`, add:

- `_get_or_create_event_conversation(self, event: Any) -> Any`, implementing the exact grounded manager sequence above;
- `on_group_invocation(self, event: Any, *args: Any, **kwargs: Any)`, decorated with `@filter.event_message_type(filter.EventMessageType.ALL, priority=sys.maxsize)`.

The handler must:

1. return immediately outside group context;
2. classify once and store the `GroupInvocation` through `event.set_extra(GROUP_INVOCATION_EXTRA, invocation)`;
3. set `event.is_at_or_wake_command = True` for `trigger_name`/trigger-sourced empty calls;
4. leave non-empty calls to AstrBot's normal request builder;
5. for an empty direct/core call, own it only when both values returned by `realtime_flags(self.config)` are true; an empty configured `trigger_name` is plugin-defined (not AstrBot's built-in empty mention) and is always owned so it can receive the normalized history prompt;
6. resolve the current `Conversation`, set `SYNTHETIC_EMPTY_CALL_EXTRA`, call `event.should_call_llm(True)`, and yield `event.request_llm(prompt=EMPTY_CALL_HISTORY_TEXT, conversation=conversation)`;
7. call `event.stop_event()` in `finally` after the owned request is consumed. The former flag prevents the later default Agent stage; the stop prevents the lower-priority built-in handler.

Do not add an in-handler waiter probe. The handler is intentionally unreachable for a message already consumed by the earlier-registered v4.26.5 session-control handler. Keep the real ProcessStage integration test as the upgrade tripwire: if AstrBot changes registration or break semantics, the test must fail before release rather than silently stealing waiter input.

Do not turn the existing `on_message` coroutine into an async generator; its current tests call it as a coroutine. Keep its tempo/identity/liveness behavior unchanged.

- [ ] **Step 4: Verify GREEN and neighboring handlers**

Run:

```text
pytest -q tests/test_group_invocation.py
pytest -q tests/test_v250_foundation.py tests/test_v250_realtime_send_save_decoupling.py
```

- [ ] **Step 5: Commit**

```text
git add main.py tests/test_group_invocation.py
git commit -m "feat(group): capture empty invocations before AstrBot waiter"
```

## Task 3: Intent-Aware SFPD and Synthetic History Hygiene

**Files:**
- Modify: `sylanne_alpha/llm_request_pipeline.py`
- Modify: `sylanne_alpha/llm_response_pipeline.py`
- Modify: `tests/test_group_invocation.py`

- [ ] **Step 1: Write RED request-pipeline tests**

Add tests named:

- `test_direct_at_bypasses_zero_pressure_sfpd`
- `test_reply_bot_bypasses_zero_pressure_sfpd`
- `test_core_wake_without_cached_intent_uses_official_fallback`
- `test_ambient_group_message_can_still_be_silenced`
- `test_mid_sentence_name_remains_attention_only_and_can_be_silenced`
- `test_empty_call_adds_transient_system_context_without_changing_prompt`
- `test_realtime_trigger_only_skips_fragment_prompt_rewrite`
- `test_synthetic_empty_call_does_not_append_user_or_bot_to_memory_buffer`
- `test_at_media_keeps_core_request_prompt_and_attachments_untouched`

Construct `LLMRequestPipeline` with the same minimal `_p`/fake host style used in `tests/test_v250_realtime_send_save_decoupling.py`. Stub `expression.should_express()` to return `False` and `_process_llm_request_final()` with `AsyncMock` to distinguish bypass from early return. For the hygiene test, call `_clean_incoming_message()` with a marked event and assert `_background_observe_request()` is not scheduled/called.

- [ ] **Step 2: Verify RED**

Run: `pytest -q tests/test_group_invocation.py -k "sfpd or transient or synthetic or attachments"`

- [ ] **Step 3: Consume the cached intent in `_on_llm_request_inner`**

At `LLMRequestPipeline._on_llm_request_inner(self, event, request)`:

- read the cached classification once;
- when absent, fall back only to `bool(event.is_at_or_wake_command)`;
- continue collecting/applying social signals for explicit calls, passing `is_at_bot=True` for the social state;
- set `_should_respond=True` for every explicit intent and call `host.kernel.computation.expression.should_express()` only for `ambient`;
- preserve the current observe-and-return path for a silenced ambient message;
- remove all reads of `event.is_at` and `event.at_bot`.
- read `SYNTHETIC_EMPTY_CALL_EXTRA` before the realtime fragment-debounce block and exclude synthetic calls from that block. In particular, never execute `request.prompt = merged_plain` for trigger-only synthetic input; the prebuilt `EMPTY_CALL_HISTORY_TEXT` must reach AstrBot history unchanged.

Do not modify `PhaseTransition.should_express()` or its zero-pressure mathematics.

- [ ] **Step 4: Add one-turn empty-call context and exclude the synthetic user material**

In the existing request pipeline, when `SYNTHETIC_EMPTY_CALL_EXTRA` is set:

- append a concise `[本轮事件]` instruction to `request.system_prompt` telling the model the user only called it and supplied no text; never put this instruction in `request.prompt`, `request.contexts`, or `extra_user_content_parts`;
- leave the normalized `request.prompt == EMPTY_CALL_HISTORY_TEXT` unchanged so AstrBot persists a truthful user/assistant pair;
- in `_clean_incoming_message(...)`, skip scheduling `_background_observe_request` for the synthetic turn, so `ConversationBuffer.append("user", ...)` at `_background_observe_request` cannot receive the normalized structural text.

In `LLMResponsePipeline`, carry the same marker through both the intercepted and non-intercepted response paths. Extend `_append_bot_reply_buffer(...)` with a keyword-only `skip_memory_buffer: bool = False`; when true, skip only `ConversationBuffer.append("bot", text)` and its buffer-persist schedule, while preserving `last_bot_texts`, social-field reply notification/reset, and AstrBot's own history save. Both response paths pass `skip_memory_buffer=True` for a synthetic empty call.

Do not mutate `event.message_str` to invented speech. Do not clear media/reply components or overwrite request attachment fields.

- [ ] **Step 5: Verify GREEN and silent-history regressions**

Run:

```text
pytest -q tests/test_group_invocation.py
pytest -q tests/test_inbound_dup_gate.py tests/test_context_integrity_silent_history.py tests/test_user_backfill_on_silent.py tests/test_err_turn_user_backfill.py tests/test_v250_realtime_send_save_decoupling.py
pytest -q tests/test_fixlist_p0_2_silent_reachable.py tests/test_phase_b_ignition.py
```

- [ ] **Step 6: Commit**

```text
git add sylanne_alpha/llm_request_pipeline.py sylanne_alpha/llm_response_pipeline.py tests/test_group_invocation.py
git commit -m "fix(group): bypass SFPD for explicit calls"
```

## Task 4: Share Trigger Parsing and Run End-to-End Verification

**Files:**
- Modify: `sylanne_alpha/social_field.py`
- Modify: `tests/test_group_invocation.py`

- [ ] **Step 1: Write a RED consistency test**

Add `test_social_field_and_invocation_classifier_share_parsed_names`. Configure `sylanne_group_attention_trigger_names` with `"小澜, 澜澜，Sylanne"`; assert all three names become social attention signals, while only start-boundary matches become explicit invocation intents.

- [ ] **Step 2: Reuse `parse_trigger_names` in `SocialFieldCollector.configure(self, config)`**

Replace the current behavior that stores a comma-separated string as one literal name. Keep `collect(...)` substring matching unchanged: a mid-sentence name is still a soft `name_mentioned` attention signal, just not an explicit invocation.

- [ ] **Step 3: Run focused, neighboring, full, lint, and plugin validation**

```text
pytest -q tests/test_group_invocation.py
pytest -q tests/test_v250_profile_crossgroup.py tests/test_v250_shelf_recall.py tests/test_v250_shelf_write.py
pytest -q -p no:cacheprovider
ruff check .
python C:/Users/pidan/.codex/plugins/cache/pidan-local-plugins/2718lab-devkit/0.1.0/skills/astrbot-plugin-dev/scripts/validate_plugin.py .
```

Expected final evidence: the group invocation matrix passes, the full suite passes, Ruff reports no errors, and the AstrBot validator reports `0` errors.

- [ ] **Step 4: Commit**

```text
git add sylanne_alpha/social_field.py tests/test_group_invocation.py
git commit -m "fix(group): share configured trigger names"
```

## Red-Team Self-Review

- **Double request:** owned empty calls set `should_call_llm(True)` before yielding and stop plugin propagation after their yielded request is consumed; realtime-off calls do neither and remain AstrBot-owned.
- **Lost history:** every owned request receives a real current `Conversation`; resolver failure fails open instead of issuing a historyless request.
- **Attachment regression:** media/reply turns never use a plugin-prebuilt ProviderRequest, so AstrBot remains the sole attachment/quote parser.
- **False wake:** configured names require a start boundary for explicit invocation; mid-sentence mentions remain only soft SFPD attention.
- **Chinese wake:** CJK trigger names accept natural suffixes without spaces; ASCII names allow a CJK suffix but reject continuation inside an ASCII word.
- **Global behavior change:** explicit-call bypass is local to `LLMRequestPipeline`; `PhaseTransition` remains untouched and ambient group messages can still be silent.
- **Synthetic memory pollution:** the truthful normalized prompt and reply are persisted by AstrBot, but the event marker prevents both sides of that structural turn from entering Sylanne's ConversationBuffer while retaining last-reply/social state.
- **Red-team response:** the first review's CJK-boundary and bot-only-buffer blockers are accepted and mapped to Task 1/Task 3 tests. The final review's SessionWaiter blocker is resolved by making AstrBot v4.26.5's earlier registration, stable equal-priority sort, and immediate `StarRequestSubStage` break an explicit compatibility contract covered by Task 2's real ProcessStage integration test.
