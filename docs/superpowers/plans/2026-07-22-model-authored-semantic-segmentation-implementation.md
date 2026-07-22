# Model-Authored Semantic Segmentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace normal-path punctuation/newline segmentation with same-call, model-authored semantic beat markers while keeping visible text and AstrBot history clean.

**Architecture:** A focused `semantic_segmentation` module owns nonce generation, the prompt contract, marker parsing, exact-text validation, and pause classes. Existing request/response hooks carry the turn-scoped contract; `realtime_plan` consumes only a validated semantic plan and retains deterministic splitting solely for exceptional oversize safety.

**Tech Stack:** Python 3.10–3.13, AstrBot v4.26.5 hooks, pytest, Ruff, Pyright.

---

**Shared-worktree rule:** Task workers must not commit or push. The root integration agent will stage the reviewed files in the final `2.5.0-grey.6` candidate commit after the full repository gate passes.

### Task 1: Pure semantic marker contract

**Files:**
- Create: `sylanne_alpha/semantic_segmentation.py`
- Create: `tests/test_semantic_segmentation.py`

- [ ] **Step 1: Write failing parser tests**

```python
from sylanne_alpha.semantic_segmentation import (
    PauseClass,
    build_marker,
    parse_semantic_completion,
)


def test_parser_preserves_visible_text_exactly() -> None:
    nonce = "A7K3Q2"
    raw = "愿望啊……\n" + build_marker(nonce, PauseClass.NORMAL) + "其实愿望很多。"
    plan = parse_semantic_completion(raw, nonce=nonce)

    assert plan.accepted is True
    assert plan.clean_text == "愿望啊……\n其实愿望很多。"
    assert "".join(part.text for part in plan.parts) == plan.clean_text
    assert [part.pause_before for part in plan.parts] == [None, PauseClass.NORMAL]


def test_wrong_nonce_is_never_interpreted_as_control_text() -> None:
    raw = '原文<syl-beat nonce="OTHER1" pause="deep"/>保留'
    plan = parse_semantic_completion(raw, nonce="A7K3Q2")
    assert plan.accepted is True
    assert plan.clean_text == raw
    assert len(plan.parts) == 1


def test_malformed_owned_marker_falls_back_clean_without_leak() -> None:
    raw = '前半<syl-beat nonce="A7K3Q2" pause="unknown"/>后半'
    plan = parse_semantic_completion(raw, nonce="A7K3Q2")
    assert plan.accepted is False
    assert plan.clean_text == "前半后半"
    assert plan.parts == ()
    assert plan.rejection_reason == "UNKNOWN_PAUSE"
```

- [ ] **Step 2: Run RED**

Run:

```powershell
python -m pytest tests/test_semantic_segmentation.py -q
```

Expected: collection fails because `sylanne_alpha.semantic_segmentation` does not exist.

- [ ] **Step 3: Implement immutable types and exact parser**

```python
class PauseClass(str, Enum):
    SOFT = "soft"
    NORMAL = "normal"
    DEEP = "deep"


@dataclass(frozen=True, slots=True)
class SemanticBeatPart:
    text: str
    pause_before: PauseClass | None


@dataclass(frozen=True, slots=True)
class SemanticBeatPlan:
    clean_text: str
    parts: tuple[SemanticBeatPart, ...]
    accepted: bool
    rejection_reason: str | None = None


def build_marker(nonce: str, pause: PauseClass) -> str:
    return f'<syl-beat nonce="{nonce}" pause="{pause.value}"/>'
```

Use one escaped, nonce-specific regex. Strip every syntactically owned marker before returning a rejected plan. Accept zero markers as one exact part. Reject more than five markers, empty visible parts, unknown pauses, back-to-back markers, and owned markers inside protected Markdown code/table/URL regions. Do not call `_split_text` from this module.

- [ ] **Step 4: Add the complete validation matrix**

Cover all three pause classes, CRLF/newline conservation, whitespace-only parts, six-part maximum, code fence, inline code, URL, table row, marker-like user text, malformed XML, and a 10,000-character input bound.

- [ ] **Step 5: Run GREEN and static checks**

```powershell
python -m pytest tests/test_semantic_segmentation.py -q
ruff check sylanne_alpha/semantic_segmentation.py tests/test_semantic_segmentation.py
pyright sylanne_alpha/semantic_segmentation.py
```

Expected: all tests pass; Ruff and Pyright report zero errors.

### Task 2: Request-side contract and nonce lifecycle

**Files:**
- Modify: `sylanne_alpha/semantic_segmentation.py`
- Modify: `sylanne_alpha/llm_request_pipeline.py`
- Modify: `tests/test_v250_realtime_send_save_decoupling.py`

- [ ] **Step 1: Write failing request tests**

Test these exact conditions:

```python
assert contract_injected(realtime=True, intercept=True, streaming=False)
assert not contract_injected(realtime=False, intercept=True, streaming=False)
assert not contract_injected(realtime=True, intercept=False, streaming=False)
assert not contract_injected(realtime=True, intercept=True, streaming=True)
```

The positive case must assert that event extras contain one six-character nonce and the system prompt contains the three exact markers, the zero-to-five rule, “do not rewrite”, and “do not put markers in structured content”. It must not contain a provider ID or request a second LLM call.

- [ ] **Step 2: Run RED and record the missing-contract assertion**

```powershell
python -m pytest tests/test_v250_realtime_send_save_decoupling.py -k semantic_beat -q
```

- [ ] **Step 3: Add a bounded contract builder**

```python
SEMANTIC_BEAT_NONCE_EXTRA = "_syl_semantic_beat_nonce"


def new_semantic_nonce() -> str:
    return secrets.token_hex(3).upper()


def semantic_beat_system_contract(nonce: str) -> str:
    markers = ", ".join(build_marker(nonce, pause) for pause in PauseClass)
    return (
        "\n[即时聊天语义节拍]\n"
        f"可在自然语义边界插入 0 到 5 个隐藏标记：{markers}。"
        "标记只控制发送节拍；不要改写正文，不要解释标记，不要把标记放进代码、URL、表格。"
    )
```

Inject only after `realtime_flags(cfg)` confirms both switches and after streaming has been disabled for the takeover path. Store the nonce with `event.set_extra`; if extras are unavailable, skip the contract rather than emitting uncorrelatable markers.

- [ ] **Step 4: Run focused and existing request regressions**

```powershell
python -m pytest tests/test_v250_realtime_send_save_decoupling.py tests/test_incident_copywriting_cascade_2026_06_15.py -q
```

Expected: semantic tests and existing realtime guards pass.

### Task 3: Response parsing and ordinary fallback

**Files:**
- Modify: `sylanne_alpha/llm_response_pipeline.py`
- Modify: `sylanne_alpha/message_dispatch.py`
- Replace: `tests/test_message_dispatch_natural_segmentation.py`
- Modify: `tests/test_incident_copywriting_cascade_2026_06_15.py`

- [ ] **Step 1: Replace the heuristic RED test with a model-plan test**

The real wish reply fixture must include model-authored markers at the five approved beat boundaries. Assert exact clean-text conservation and five message parts. Add an invalid-marker case that asserts one clean message rather than nine newline-derived messages.

```python
plan = realtime_plan(
    "2300184498",
    parsed.clean_text,
    semantic_parts=parsed.parts,
    rng=random.Random(7),
)
assert [item["text"] for item in plan["message_parts"]] == expected_five_parts
assert "".join(item["text"] for item in plan["message_parts"]) == parsed.clean_text
```

- [ ] **Step 2: Run RED**

Expected: `realtime_plan()` rejects the new `semantic_parts` argument.

- [ ] **Step 3: Extend `realtime_plan` without semantic inference**

```python
def realtime_plan(
    session_key: str,
    text: str,
    *,
    semantic_parts: Sequence[SemanticBeatPart] | None = None,
    oversize_safety_chars: int = 1200,
    ...,
) -> dict[str, Any]:
    if semantic_parts is not None:
        parts = [part.text for part in semantic_parts]
        pause_classes = [part.pause_before for part in semantic_parts]
    elif len(visible) <= oversize_safety_chars:
        parts = [visible] if visible else []
        pause_classes = [None] * len(parts)
    else:
        parts = _split_text(visible, max_part_chars=max_part_chars)
        pause_classes = [None] * len(parts)
```

Pass explicit pause classes into `_message_parts`. Map `soft`, `normal`, and `deep` to bounded multipliers/ranges; retain body-driven characters-per-second and small seeded jitter. Disable the random distracted pause when any explicit semantic pause is present.

- [ ] **Step 4: Parse before planning**

In the response hook, read the nonce from event extras. If present, parse the sanitized completion and pass accepted parts to `realtime_plan`. If parsing rejects, log only the reason and use one clean part for ordinary output. If no nonce exists, preserve current behavior for rollout compatibility until Task 6 flips the normal fallback.

- [ ] **Step 5: Run focused GREEN**

```powershell
python -m pytest tests/test_message_dispatch_natural_segmentation.py tests/test_incident_copywriting_cascade_2026_06_15.py -q
```

### Task 4: History and outbound marker scrub

**Files:**
- Modify: `main.py`
- Modify: `sylanne_alpha/llm_response_pipeline.py`
- Modify: `tests/test_v3_main_wiring.py`
- Modify: `tests/test_v250_realtime_send_save_decoupling.py`

- [ ] **Step 1: Write three independent leak-guard tests**

1. `OnLLMResponse` sets clean `completion_text` and stores a bounded raw/clean correlation extra.
2. `OnAgentDone` replaces only the final assistant `TextPart` whose text exactly equals the correlated raw completion.
3. `OnDecoratingResult` strips an exact owned marker from Plain output even when the earlier hook was bypassed.

Also assert that nonmatching assistant content, reasoning parts, images, records, and other messages are untouched.

- [ ] **Step 2: Run RED**

Expected: `_FakeFilter` has no `on_agent_done`, and no handler scrubs `run_context.messages`.

- [ ] **Step 3: Add the verified AstrBot v4.26.5 hook**

```python
class _FakeFilter:
    def on_agent_done(self, *args, **kwargs):
        def decorator(func):
            return func
        return decorator


@filter.on_agent_done()
async def on_agent_done(self, event: Any, run_context: Any, response: Any) -> None:
    self._llm_response_pipeline.scrub_semantic_markers_from_history(
        event, run_context, response
    )
```

The scrub method must require an exact raw-text correlation before mutation. Support both `Message.content: str` and `list[ContentPart]`; mutate only text-bearing assistant content. Always remove the event correlation extra after use.

- [ ] **Step 4: Run GREEN under fallback stubs and AstrBot 4.26.5**

```powershell
python -m pytest tests/test_v3_main_wiring.py tests/test_v250_realtime_send_save_decoupling.py -q
```

Run once with the Python 3.12 environment containing AstrBot 4.26.5 and once with the repository fallback import path.

### Task 5: Exact remainder and interruption behavior

**Files:**
- Modify: `sylanne_alpha/llm_response_pipeline.py`
- Modify: `sylanne_alpha/realtime_dispatch.py`
- Modify: `tests/test_v250_realtime_send_save_decoupling.py`

- [ ] **Step 1: Write a failing interruption test**

Use parts containing internal newlines and repeated phrases. Interrupt after part two. Assert that `unfinished_replies` equals the exact concatenation of parts three onward and contains no marker.

- [ ] **Step 2: Run RED**

Expected: the current `startswith`/`strip` remainder logic loses or normalizes content.

- [ ] **Step 3: Store the semantic remainder directly**

Derive remainder from the validated part sequence rather than searching the clean string. Keep the existing task cancellation and session-key guards.

- [ ] **Step 4: Run the realtime delivery suite**

```powershell
python -m pytest tests/test_v250_realtime_send_save_decoupling.py tests/test_message_dispatch_natural_segmentation.py -q
```

### Task 6: Rollout flip, observability, and full verification

**Files:**
- Modify: `sylanne_alpha/llm_response_pipeline.py`
- Modify: `sylanne_alpha/message_dispatch.py`
- Modify: `docs/superpowers/plans/2026-07-15-v3-shadow-grey-implementation.md`

- [ ] **Step 1: Add structured reason/count assertions**

Tests must assert accepted/rejected plan logs contain part counts and reason enums but never reply text or raw marker-bearing content.

- [ ] **Step 2: Make ordinary no-plan fallback a single message**

After all leak/history tests pass, remove normal-path newline/punctuation splitting. Keep `_split_text` reachable only when the hard anti-flood threshold is exceeded or an explicit legacy compatibility path is requested.

- [ ] **Step 3: Run focused verification**

```powershell
python -m pytest tests/test_semantic_segmentation.py tests/test_message_dispatch_natural_segmentation.py tests/test_v250_realtime_send_save_decoupling.py tests/test_incident_copywriting_cascade_2026_06_15.py tests/test_v3_main_wiring.py -q
ruff check main.py sylanne_alpha/semantic_segmentation.py sylanne_alpha/message_dispatch.py sylanne_alpha/llm_request_pipeline.py sylanne_alpha/llm_response_pipeline.py tests/test_semantic_segmentation.py tests/test_message_dispatch_natural_segmentation.py
pyright main.py sylanne_alpha/semantic_segmentation.py sylanne_alpha/message_dispatch.py sylanne_alpha/llm_request_pipeline.py sylanne_alpha/llm_response_pipeline.py
git diff --check
```

- [ ] **Step 4: Run integration verification**

Run the full v3 shards, Python 3.10–3.13 matrix, exact AstrBot 4.26.5 import/integration smoke, and local G2. Confirm `v3_extra_llm_call_count == 0` and all isolation counters remain zero.

- [ ] **Step 5: Red-team review**

Require an independent reviewer to test marker injection, prompt-injection attempts, malformed/unbounded output, plugin hot-unload timing, stream bypass, history contamination, repeated text, cancellation, and rollback. Resolve every P0/P1 before integration staging.
