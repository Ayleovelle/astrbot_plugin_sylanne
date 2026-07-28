# Sylanne Observatory Interactions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the AstrBot plugin's standalone login and native Pages connection paths, replace the rejected radial login transition with the approved center-spine choreography, add coherent visual-novel-style interaction feedback, and provide click-to-expand observation chambers backed by durable real history.

**Architecture:** Keep the existing Vue design system and both existing serving modes. The frontend uses one deterministic arrival state machine, one small global feedback channel, the existing accessible `Modal.vue`, and per-session observation caches. The backend captures a privacy-safe numeric projection only after `AlphaRuntime.save_snapshot()` has atomically succeeded, stores append-only JSONL segments under the plugin data root, applies one-segment-at-a-time global retention, and exposes one shared read/query implementation through AstrBot native Pages, aiohttp, and stdlib routes.

**Tech Stack:** Python 3.10+, AstrBot plugin APIs, JSONL/atomic JSON manifest, Vue 3.5, Pinia 3, Vue Router 5, TypeScript 6, Vite 8, Vitest 4, pytest.

---

## Task 1: Preserve the completed 2.5.0 entry-path fixes

**Files:**

- Modify: `sylanne_alpha/webui_routes.py`
- Modify: `tests/test_webui_contract.py`
- Modify: `webui-src/src/api/client.ts`
- Modify: `webui-src/src/api/client.test.ts`
- Modify: `webui-src/src/components/BootScreen.vue`
- Modify: `webui-src/src/components/shell/TopBar.vue`
- Modify: `webui-src/src/composables/useBoot.ts`
- Create: `webui-src/src/composables/useBoot.test.ts`
- Create: `webui-src/topBarMarkup.test.ts`

- [ ] **Step 1: Run the focused regression tests that describe the fixed entry contracts**

```powershell
$taskTmp='D:\bun\tmp\codex\Sylanne-next'
$env:TEMP=$taskTmp; $env:TMP=$taskTmp; $env:TMPDIR=$taskTmp
Set-Location 'D:\bun\tmp\codex\Sylanne-next\worktree\webui-src'
pnpm vitest run src/api/client.test.ts src/composables/useBoot.test.ts topBarMarkup.test.ts
Set-Location '..'
python -m pytest tests/test_webui_contract.py -q
```

Expected: AstrBot bridge requests preserve `/api/state` and `/api/settings` paths, standalone requests resolve from `/`, native Pages state can serialize byte-like values, the boot verification has a bounded timeout, and logout remains deterministic in standalone mode.

- [ ] **Step 2: Review the diff and stage only the stable entry-path files**

```powershell
git diff --check -- sylanne_alpha/webui_routes.py tests/test_webui_contract.py webui-src/src/api/client.ts webui-src/src/api/client.test.ts webui-src/src/components/BootScreen.vue webui-src/src/components/shell/TopBar.vue webui-src/src/composables/useBoot.ts webui-src/src/composables/useBoot.test.ts webui-src/topBarMarkup.test.ts
git add sylanne_alpha/webui_routes.py tests/test_webui_contract.py webui-src/src/api/client.ts webui-src/src/api/client.test.ts webui-src/src/components/BootScreen.vue webui-src/src/components/shell/TopBar.vue webui-src/src/composables/useBoot.ts webui-src/src/composables/useBoot.test.ts webui-src/topBarMarkup.test.ts
git commit -m "fix: stabilize AstrBot web ui entry"
```

Do not stage `UI/index.html`, `pages/dashboard/index.html`, `VoidVeil.vue`, or the old radial-transition tests in this checkpoint.

## Task 2: Replace the radial veil with the approved center-spine arrival

**Files:**

- Create: `webui-src/src/motion/arrival.ts`
- Create: `webui-src/src/motion/arrival.test.ts`
- Create: `webui-src/arrivalChoreography.test.ts`
- Modify: `webui-src/src/App.vue`
- Modify: `webui-src/src/views/LoginView.vue`
- Modify: `webui-src/src/components/shell/DashboardLayout.vue`
- Modify: `webui-src/src/components/shell/SpineNav.vue`
- Delete: `webui-src/src/components/VoidVeil.vue`
- Delete: `webui-src/voidVeilMarkup.test.ts`

- [ ] **Step 1: Write failing pure timing tests**

```ts
import { describe, expect, it } from 'vitest'
import {
  ARRIVAL_CONTENT_MS,
  ARRIVAL_LINE_MS,
  ARRIVAL_NODE_FADE_MS,
  arrivalNodeDelay,
} from './arrival'

describe('arrival choreography', () => {
  it('lets a linear 1200ms spine reach each node before it appears', () => {
    expect(ARRIVAL_LINE_MS).toBe(1200)
    expect(ARRIVAL_NODE_FADE_MS).toBe(250)
    expect([16, 25, 34, 43, 52, 61, 70, 79].map(arrivalNodeDelay)).toEqual([
      192, 300, 408, 516, 624, 732, 840, 948,
    ])
  })

  it('starts both bars and all cards together after the spine completes', () => {
    expect(ARRIVAL_CONTENT_MS).toBe(1200)
  })
})
```

- [ ] **Step 2: Add the smallest shared timing module**

```ts
export const ARRIVAL_LINE_MS = 1200
export const ARRIVAL_NODE_FADE_MS = 250
export const ARRIVAL_CONTENT_MS = ARRIVAL_LINE_MS
export const ARRIVAL_CONTENT_DURATION_MS = 600
export const ARRIVAL_CLEANUP_MS = 1900

export function arrivalNodeDelay(topPercent: number): number {
  return Math.round((topPercent / 100) * ARRIVAL_LINE_MS)
}
```

- [ ] **Step 3: Write a failing source-contract test for the no-circle requirement**

The test must assert all of the following:

```ts
expect(appSource).not.toContain('VoidVeil')
expect(loginSource).not.toContain('useVoidTransition')
expect(loginSource).not.toContain("start('revealing')")
expect(loginSource).toContain('boot.requestArrival()')
expect(layoutSource).toContain('1200ms linear')
expect(layoutSource).not.toMatch(/nth-child\([^)]*\).*animation-delay/s)
expect(spineSource).toContain('arrivalNodeDelay')
```

- [ ] **Step 4: Remove the veil and simplify login success**

`LoginView.vue` keeps the existing specimen animation and success confirmation, but the success handoff becomes:

```ts
await waitForSuccessConfirmation()
boot.requestArrival()
await router.replace({ name: 'monitor' })
```

There must be no `expanding`, `revealing`, `veilSolid`, radial mask, clip-path circle, or second route transition.

- [ ] **Step 5: Implement a two-stage dashboard arrival**

Use `spine`, `content`, and `idle` phases:

```ts
arrivalPhase.value = 'spine'
contentTimer = window.setTimeout(() => {
  arrivalPhase.value = 'content'
}, ARRIVAL_CONTENT_MS)
cleanupTimer = window.setTimeout(() => {
  arrivalPhase.value = 'idle'
}, ARRIVAL_CLEANUP_MS)
```

CSS requirements:

- The center line grows top-to-bottom with `1200ms linear`.
- Each route node receives `--arrival-delay: ${arrivalNodeDelay(node.top)}ms`.
- The active handle uses the same formula as its route node and cannot appear early.
- At `1200ms`, the top bar moves down from the top edge, the footer moves up from the bottom edge, left cards move from the center toward the left, and right cards move from the center toward the right.
- All cards begin together; there are no `nth-child` delays.
- `prefers-reduced-motion: reduce` skips the JavaScript wait and immediately shows the final state.

- [ ] **Step 6: Run focused tests and commit**

```powershell
Set-Location 'D:\bun\tmp\codex\Sylanne-next\worktree\webui-src'
pnpm vitest run src/motion/arrival.test.ts arrivalChoreography.test.ts src/composables/useVoidTransition.test.ts
pnpm build
Set-Location '..'
git diff --check
git add webui-src/src/App.vue webui-src/src/views/LoginView.vue webui-src/src/components/shell/DashboardLayout.vue webui-src/src/components/shell/SpineNav.vue webui-src/src/motion/arrival.ts webui-src/src/motion/arrival.test.ts webui-src/arrivalChoreography.test.ts webui-src/src/components/VoidVeil.vue webui-src/voidVeilMarkup.test.ts
git commit -m "fix: sequence dashboard arrival from the spine"
```

## Task 3: Add one coherent interaction-feedback channel

**Files:**

- Create: `webui-src/src/composables/useInteractionFeedback.ts`
- Create: `webui-src/src/composables/useInteractionFeedback.test.ts`
- Modify: `webui-src/src/components/shell/AppFooter.vue`
- Modify: `webui-src/src/components/shell/TopBar.vue`
- Modify: `webui-src/src/stores/live.ts`
- Modify: `webui-src/src/views/ConfigView.vue`
- Modify: `webui-src/src/views/LifeView.vue`
- Modify: `webui-src/src/views/MemoryView.vue`
- Modify: `webui-src/src/composables/useI18n.ts`

- [ ] **Step 1: Write failing feedback queue tests**

Cover replacement, expiry, sticky connection errors, and teardown:

```ts
const feedback = createInteractionFeedback({ defaultTtlMs: 1800 })
feedback.show('状态已同步')
feedback.show('会话已切换 · 1432192649')
expect(feedback.current.value?.text).toBe('会话已切换 · 1432192649')
feedback.clear()
expect(feedback.current.value).toBeNull()
```

- [ ] **Step 2: Implement a dependency-free global feedback state**

The public surface is:

```ts
export type FeedbackTone = 'neutral' | 'success' | 'warning' | 'error'

export interface InteractionFeedback {
  text: string
  tone: FeedbackTone
  sticky: boolean
}

export function useInteractionFeedback(): {
  current: Readonly<Ref<InteractionFeedback | null>>
  show(text: string, tone?: FeedbackTone, options?: { ttlMs?: number; sticky?: boolean }): void
  clear(): void
}
```

The latest message replaces the previous one. Non-sticky messages fade after about `1800ms`. A reconnect success replaces the sticky offline warning, then expires normally.

- [ ] **Step 3: Render feedback in the existing footer**

Use the existing center slot and preserve runtime/session/schema information:

```vue
<Transition name="footer-narration" mode="out-in">
  <span v-if="feedback.current.value" :key="feedback.current.value.text" aria-live="polite">
    {{ feedback.current.value.text }}
  </span>
  <span v-else>schema state.v2</span>
</Transition>
```

Do not add a toast, dialog, HUD panel, or new visual material.

- [ ] **Step 4: Connect real operations**

- Session selection: `会话已切换 · {session}`.
- Successful live refresh: `状态已同步`, rate-limited so the 5-second poll does not narrate continuously.
- Lost connection: sticky `连接已中断，正在重试`.
- Reconnected: `连接已恢复`.
- Successful save/control/delete: the existing action-specific success text.
- Failure: a short, human-readable error summary while preserving the existing inline field error.

- [ ] **Step 5: Run focused tests and commit**

```powershell
Set-Location 'D:\bun\tmp\codex\Sylanne-next\worktree\webui-src'
pnpm vitest run src/composables/useInteractionFeedback.test.ts
pnpm build
Set-Location '..'
git diff --check
git add webui-src/src/composables/useInteractionFeedback.ts webui-src/src/composables/useInteractionFeedback.test.ts webui-src/src/components/shell/AppFooter.vue webui-src/src/components/shell/TopBar.vue webui-src/src/stores/live.ts webui-src/src/views/ConfigView.vue webui-src/src/views/LifeView.vue webui-src/src/views/MemoryView.vue webui-src/src/composables/useI18n.ts
git commit -m "feat: narrate dashboard interactions"
```

## Task 4: Build durable, bounded observation-history storage

**Files:**

- Create: `sylanne_alpha/observation_history.py`
- Create: `tests/test_observation_history.py`
- Modify: `_conf_schema.json`
- Modify: `sylanne_alpha/_engine/sylanne_core/compute/runtime.py`
- Modify: `sylanne_alpha/session_context.py`
- Modify: `main.py`

- [ ] **Step 1: Write failing storage tests**

Tests must cover:

1. A successful `AlphaRuntime.save_snapshot()` appends one observation.
2. A failed `os.replace()` appends nothing.
3. An unchanged numeric projection is de-duplicated; changing one projected value appends.
4. No stored row contains `last_event`, `previous_event`, chat text, prompt text, memory contents, or token material.
5. Restart reconstructs state from a valid manifest.
6. A missing or corrupt manifest is rebuilt by scanning segment files.
7. A truncated/corrupt JSONL row is skipped and reported as `partial=true`.
8. `max_bytes=0` never deletes a segment.
9. A positive global limit deletes at most one oldest closed segment per append and never deletes an active segment.
10. Repeated appends eventually lower storage to the `90%` target.
11. Multiple sessions share one global budget.

- [ ] **Step 2: Define the privacy-safe projection**

The stored row is deliberately smaller than `kernel.snapshot()`:

```python
{
    "schema_version": "sylanne.observation.sample.v1",
    "captured_at_ms": 1785206840394,
    "session": "1432192649",
    "turns": 227,
    "groups": {
        "emotion": {
            "warmth": 0.12,
            "arousal": 0.07,
            "valence": 0.18,
            "tension": 0.09,
            "curiosity": 0.31,
            "repair_pressure": 0.04,
            "expression_drive": 0.21,
            "boundary_firmness": 0.76,
        },
        "boundary": {"integrity": 0.96, "entropy": 0.0, "stability": 0.96},
        "timing": {"total_ms": 3.82},
        "routing": {"resonance": 7, "skip": 4},
        "gate": {"surprise": 0.54, "threshold": 0.50, "route": "RESONANCE"},
        "expression": {"pressure": 0.0, "threshold": 0.6, "mode": "silent"},
        "feedback": {"accepted": 0, "ignored": 0, "rejected": 0},
    },
}
```

All extraction is allow-listed and defensive. The digest used for de-duplication excludes `captured_at_ms` but includes the session and all projected values.

- [ ] **Step 3: Implement the segmented store**

`ObservationHistoryStore` owns one re-entrant lock covering append, manifest replacement, query, and cleanup:

```python
class ObservationHistoryStore:
    def __init__(
        self,
        root: Path,
        max_bytes_provider: Callable[[], int],
        *,
        segment_bytes: int = 1_048_576,
    ) -> None:
        self._root = root
        self._max_bytes_provider = max_bytes_provider
        self._segment_bytes = segment_bytes
        self._lock = threading.RLock()

    def append_snapshot(
        self,
        session_key: str,
        snapshot: dict[str, Any],
        *,
        captured_at_ms: int | None = None,
    ) -> bool:
        with self._lock:
            row = project_observation(session_key, snapshot, captured_at_ms)
            return self._append_projected_row(row)

    def query(
        self,
        session_key: str,
        *,
        group: str,
        from_ms: int | None,
        to_ms: int | None,
        max_points: int,
    ) -> dict[str, Any]:
        with self._lock:
            rows, partial = self._read_rows(session_key, group, from_ms, to_ms)
            return self._build_query_response(rows, group, max_points, partial)
```

Storage rules:

- Root: `<sylanne data root>/observation-history`.
- Segment: append-only JSONL, rolled near `1 MiB`.
- Manifest: `manifest.json`, replaced atomically after segment fsync.
- Session identity: a SHA-256-derived directory/key prevents unsafe filenames; the row retains the original session string for collision checking.
- Default global limit: `134_217_728` bytes (`128 MiB`).
- `0`: unlimited.
- Over limit: delete no more than one oldest closed segment during one append/maintenance pass; continue on later passes until usage is at or below `90%`.
- Never delete the current active segment or the newest sample.
- Store failures only log a warning and never fail the kernel save.

- [ ] **Step 4: Hook capture after atomic snapshot success**

Add an optional sink to `AlphaRuntime`:

```python
def set_observation_sink(
    self,
    sink: Callable[[str, dict[str, Any]], None] | None,
) -> None:
    self._observation_sink = sink
```

Call it only after `os.replace(tmp, path)` succeeds:

```python
os.replace(tmp, path)
if self._observation_sink is not None:
    try:
        self._observation_sink(session_key, snapshot)
    except Exception:
        logger.warning("Observation history append failed", exc_info=True)
```

Bind the sink whenever `session_context.py` creates a host, and also bind existing hosts during plugin initialization/hot reload. This capture point covers normal host flushes, async persistence, sync persistence, and reset paths without depending on the WebUI being open.

- [ ] **Step 5: Add the AstrBot configuration**

Add this schema entry:

```json
"sylanne_webui_history_storage_limit_mb": {
  "description": "观测历史存储上限（MiB，0 表示不设上限）",
  "type": "int",
  "default": 128,
  "hint": "记录长期保留；超过上限后按最旧已封闭分段逐步清理。"
}
```

Clamp negative values to the default. Convert MiB to bytes only inside the provider passed to the store, so live settings updates do not require rebuilding hosts.

- [ ] **Step 6: Run focused Python tests and commit**

```powershell
$taskTmp='D:\bun\tmp\codex\Sylanne-next'
$env:TEMP=$taskTmp; $env:TMP=$taskTmp; $env:TMPDIR=$taskTmp
Set-Location 'D:\bun\tmp\codex\Sylanne-next\worktree'
python -m pytest tests/test_observation_history.py -q
python -m pytest tests/test_state_persistence.py -q
git diff --check
git add _conf_schema.json main.py sylanne_alpha/observation_history.py sylanne_alpha/_engine/sylanne_core/compute/runtime.py sylanne_alpha/session_context.py tests/test_observation_history.py
git commit -m "feat: persist durable observation history"
```

## Task 5: Expose one mirrored history-query contract

**Files:**

- Modify: `sylanne_alpha/observation_history.py`
- Modify: `sylanne_alpha/webui_routes.py`
- Modify: `sylanne_alpha/webui_server.py`
- Modify: `main.py`
- Modify: `tests/test_observation_history.py`
- Modify: `tests/test_webui_contract.py`
- Modify: `webui-src/src/api/client.ts`
- Modify: `webui-src/src/api/client.test.ts`
- Modify: `webui-src/src/api/types.ts`

- [ ] **Step 1: Write failing query and route tests**

Test this shared endpoint in all serving modes:

```text
GET /api/observation_history
  ?session=1432192649
  &group=emotion
  &from_ms=1785200000000
  &to_ms=1785209999999
  &max_points=240
```

The response contract is:

```json
{
  "schema_version": "sylanne.observation.history.v1",
  "session": "1432192649",
  "group": "emotion",
  "points": [
    {
      "from_ms": 1785206840394,
      "to_ms": 1785206840394,
      "first": {"warmth": 0.12},
      "last": {"warmth": 0.12},
      "min": {"warmth": 0.12},
      "max": {"warmth": 0.12}
    }
  ],
  "sample_count": 1,
  "downsampled": false,
  "partial": false,
  "storage": {
    "used_bytes": 4096,
    "limit_bytes": 134217728,
    "oldest_ms": 1785206840394,
    "segment_count": 1
  }
}
```

Tests must verify:

- `session` and a known `group` are required.
- `max_points` is clamped to `1..1000`.
- `from_ms <= to_ms`.
- Long ranges use deterministic time buckets.
- Every bucket preserves first, last, min, and max for every numeric field.
- An unknown session returns an empty successful response.
- Corrupt rows set `partial=true` without breaking valid results.
- Native Pages, aiohttp, and stdlib call the same query implementation.

- [ ] **Step 2: Register the native AstrBot Pages route**

Add:

```python
(f"/{P}/api/observation_history", "observation_history_handler", ["GET"])
```

`WebUIRoutes.observation_history_handler()` reads `astrbot.api.web.request.query`, validates through the shared query parser, and returns a JSON-serializable dictionary. It must not use the standalone server address.

- [ ] **Step 3: Mirror the endpoint in both standalone servers**

Add an aiohttp handler and:

```python
app.router.add_get("/api/observation_history", handle_observation_history)
```

Add the same path to the stdlib `do_GET()` switch. Both wrappers call the same query builder; neither duplicates downsampling logic.

- [ ] **Step 4: Add frontend types and a bridge-safe client**

```ts
export interface ObservationHistoryPoint {
  from_ms: number
  to_ms: number
  first: Record<string, number>
  last: Record<string, number>
  min: Record<string, number>
  max: Record<string, number>
}

export interface ObservationHistoryResponse {
  schema_version?: string
  session?: string
  group?: string
  points?: ObservationHistoryPoint[]
  sample_count?: number
  downsampled?: boolean
  partial?: boolean
  storage?: {
    used_bytes?: number
    limit_bytes?: number | null
    oldest_ms?: number | null
    segment_count?: number
  }
}
```

The request must remain relative:

```ts
apiFetch<ObservationHistoryResponse>(
  `/api/observation_history?${new URLSearchParams(params)}`,
  { signal },
)
```

`client.test.ts` must prove the request works through `window.AstrBotPluginPage` and through standalone `fetch`.

- [ ] **Step 5: Run contract tests and commit**

```powershell
$taskTmp='D:\bun\tmp\codex\Sylanne-next'
$env:TEMP=$taskTmp; $env:TMP=$taskTmp; $env:TMPDIR=$taskTmp
Set-Location 'D:\bun\tmp\codex\Sylanne-next\worktree'
python -m pytest tests/test_observation_history.py tests/test_webui_contract.py -q
Set-Location 'webui-src'
pnpm vitest run src/api/client.test.ts
Set-Location '..'
git diff --check
git add main.py sylanne_alpha/observation_history.py sylanne_alpha/webui_routes.py sylanne_alpha/webui_server.py tests/test_observation_history.py tests/test_webui_contract.py webui-src/src/api/client.ts webui-src/src/api/client.test.ts webui-src/src/api/types.ts
git commit -m "feat: expose observation history to AstrBot pages"
```

## Task 6: Make live state session-safe and prepare real chart data

**Files:**

- Create: `webui-src/src/views/monitorObservation.ts`
- Create: `webui-src/src/views/monitorObservation.test.ts`
- Modify: `webui-src/src/stores/live.ts`
- Create: `webui-src/src/stores/live.test.ts`
- Modify: `webui-src/src/stores/session.ts`
- Create: `webui-src/src/stores/session.test.ts`

- [ ] **Step 1: Write the session-race regression**

The test starts request A, switches to B, resolves B, then resolves A. B must remain visible:

```ts
const requestA = deferred<StateResponse>()
const requestB = deferred<StateResponse>()
mockedApiFetch
  .mockReturnValueOnce(requestA.promise)
  .mockReturnValueOnce(requestB.promise)

const a = live.fetchNow('A')
const b = live.fetchNow('B')
requestB.resolve({ current_session: 'B', emotion: { warmth: 0.8 } })
await b
requestA.resolve({ current_session: 'A', emotion: { warmth: 0.1 } })
await a

expect(live.state.current_session).toBe('B')
expect(live.state.emotion?.warmth).toBe(0.8)
```

- [ ] **Step 2: Replace the single global inflight guard**

Use a monotonically increasing request generation and `AbortController`:

```ts
let requestGeneration = 0
let activeController: AbortController | null = null

async function fetchNow(sessionId: string): Promise<void> {
  const generation = ++requestGeneration
  activeController?.abort()
  const controller = new AbortController()
  activeController = controller
  const response = await fetchState(sessionId, controller.signal)
  if (generation !== requestGeneration || sessionId !== session.currentId) return
  state.value = response
}
```

Aborts are not shown as errors. Real failures preserve the last usable state and trigger the sticky retry feedback.

- [ ] **Step 3: Keep per-session history caches**

The live store keeps history responses and current points keyed by session and group. Switching sessions never reuses another session's samples, and switching back can immediately show its cached history while a fresh request runs.

- [ ] **Step 4: Implement pure chart-data normalization**

`monitorObservation.ts` contains no Vue state or DOM access:

```ts
export function normalizeHistory(
  response: ObservationHistoryResponse,
  live: StateResponse,
  group: ObservationGroup,
): ObservationSeries

export function describeObservation(
  series: ObservationSeries,
  locale: 'zh' | 'en',
): ObservationNarrative
```

Tests cover timestamp de-duplication, server bucket envelopes, current-state tail merging, empty history, route/status values, and all seven groups.

- [ ] **Step 5: Preserve a valid session selection**

`session.setSessions()` keeps the current id if it remains valid; otherwise it selects the first available session and cancels the prior live/history request.

- [ ] **Step 6: Run tests and commit**

```powershell
Set-Location 'D:\bun\tmp\codex\Sylanne-next\worktree\webui-src'
pnpm vitest run src/stores/live.test.ts src/stores/session.test.ts src/views/monitorObservation.test.ts
pnpm build
Set-Location '..'
git diff --check
git add webui-src/src/stores/live.ts webui-src/src/stores/live.test.ts webui-src/src/stores/session.ts webui-src/src/stores/session.test.ts webui-src/src/views/monitorObservation.ts webui-src/src/views/monitorObservation.test.ts
git commit -m "fix: isolate live observations by session"
```

## Task 7: Add the click-to-expand Observation Chamber

**Files:**

- Create: `webui-src/src/components/monitor/ObservationTrendChart.vue`
- Create: `webui-src/src/components/monitor/ObservationChamber.vue`
- Create: `webui-src/src/components/monitor/observationChamberMotion.ts`
- Create: `webui-src/src/components/monitor/observationChamberMotion.test.ts`
- Create: `webui-src/observationChamberMarkup.test.ts`
- Modify: `webui-src/src/views/MonitorView.vue`
- Modify: `webui-src/src/components/Modal.vue`
- Modify: `webui-src/src/composables/useI18n.ts`

- [ ] **Step 1: Write failing geometry and accessibility tests**

The pure geometry test verifies that a trigger rectangle maps into the centered dialog rectangle:

```ts
expect(morphFromRect(trigger, dialog)).toEqual({
  translateX: -412,
  translateY: 168,
  scaleX: 0.41,
  scaleY: 0.28,
})
```

The source-contract test verifies:

- Each of the seven monitor cards supplies a real `button` in `Card.vue`'s `#action` slot.
- Buttons have `aria-expanded` and `aria-controls`.
- Exactly one `ObservationChamber`/`Modal` is mounted.
- The dialog has a labelled title, Escape close, backdrop close, focus trap, and trigger focus restoration through existing `Modal.vue`.
- No fake chart is rendered when there are no samples.

- [ ] **Step 2: Keep generic cards generic**

Do not make `Card.vue` itself clickable. Each observation card adds an explicit action button:

```vue
<template #action>
  <button
    class="observation-open"
    type="button"
    :aria-expanded="activeGroup === 'emotion'"
    aria-controls="observation-chamber"
    @click="openObservation('emotion', $event.currentTarget)"
  >
    {{ t('observation.open') }}
  </button>
</template>
```

- [ ] **Step 3: Reuse the existing accessible modal**

Extend `Modal.vue` only enough to expose a panel ref/class and accept origin motion variables. Preserve its existing Teleport, focus trap, initial focus, Escape/backdrop close, `role="dialog"`, `aria-modal`, responsive max height, and focus return.

On open:

1. Capture the trigger rectangle.
2. Mount the dialog invisibly.
3. Measure the target rectangle.
4. Apply the initial translate/scale from `morphFromRect()`.
5. Animate to identity with the existing muted rose easing.

On close, reverse the same transform and return focus to the trigger. Under reduced motion, skip geometry animation.

- [ ] **Step 4: Render only real trend data**

`ObservationTrendChart.vue` draws the normalized server/live series and exposes an accessible text summary with `role="img"` and an `aria-label`. When there are no persistent samples, show `从现在开始记录`; do not synthesize a line or random points.

- [ ] **Step 5: Show the complete detail contract**

The chamber displays:

- current readings;
- short metric explanation;
- real historical trend;
- related state;
- latest sample time;
- sample count;
- current storage use;
- configured limit or `无限制`;
- earliest retained record time;
- partial-history warning when corrupt rows were skipped.

Switching route or session closes the chamber before changing data.

- [ ] **Step 6: Match the approved visual direction**

Use existing CSS variables for background, card, border, radius, type, and dusty-rose accents. The desktop panel is approximately `72vw × min(72vh, content)`. Mobile is nearly full-screen with the existing safe margin. The backdrop keeps the dashboard legible with only a small contrast reduction and at most `2px` blur.

- [ ] **Step 7: Run tests and commit**

```powershell
Set-Location 'D:\bun\tmp\codex\Sylanne-next\worktree\webui-src'
pnpm vitest run src/components/monitor/observationChamberMotion.test.ts observationChamberMarkup.test.ts src/views/monitorObservation.test.ts
pnpm build
Set-Location '..'
git diff --check
git add webui-src/src/components/monitor/ObservationTrendChart.vue webui-src/src/components/monitor/ObservationChamber.vue webui-src/src/components/monitor/observationChamberMotion.ts webui-src/src/components/monitor/observationChamberMotion.test.ts webui-src/observationChamberMarkup.test.ts webui-src/src/views/MonitorView.vue webui-src/src/components/Modal.vue webui-src/src/composables/useI18n.ts
git commit -m "feat: expand monitor cards into observation chambers"
```

## Task 8: Polish interaction states without changing the design language

**Files:**

- Modify: `webui-src/src/styles/base.css`
- Modify: `webui-src/src/components/Card.vue`
- Modify: `webui-src/src/components/shell/TopBar.vue`
- Modify: `webui-src/src/views/LoginView.vue`
- Modify: `webui-src/src/views/MonitorView.vue`
- Modify: `webui-src/src/views/ConfigView.vue`
- Modify: `webui-src/src/views/LifeView.vue`
- Modify: `webui-src/src/views/MemoryView.vue`
- Create: `webui-src/interactionContracts.test.ts`

- [ ] **Step 1: Add failing source contracts**

Assert that:

- actionable controls have `:focus-visible`;
- card hover movement is at most `3px`;
- login keeps button dimensions during pending state;
- connection status includes text as well as color;
- destructive operations retain their existing confirmation;
- reduced motion disables translation, spring, morph, and staged waits;
- native Pages never renders standalone logout;
- no new palette token, neon glow, particle layer, anime portrait, or game HUD is introduced.

- [ ] **Step 2: Apply the restrained interaction language**

Use:

- `translateY(-2px)` for actionable card hover;
- existing dusty-rose border/focus tokens;
- a short pressed-state displacement;
- disabled/loading states that do not resize controls;
- old-data-preserving skeleton/loading behavior;
- textual empty states instead of decorative animation.

- [ ] **Step 3: Verify desktop, mobile, light, dark, keyboard, and reduced-motion source behavior**

```powershell
Set-Location 'D:\bun\tmp\codex\Sylanne-next\worktree\webui-src'
pnpm vitest run interactionContracts.test.ts
pnpm test
pnpm build
```

- [ ] **Step 4: Commit the polish**

```powershell
Set-Location 'D:\bun\tmp\codex\Sylanne-next\worktree'
git diff --check
git add webui-src/src/styles/base.css webui-src/src/components/Card.vue webui-src/src/components/shell/TopBar.vue webui-src/src/views/LoginView.vue webui-src/src/views/MonitorView.vue webui-src/src/views/ConfigView.vue webui-src/src/views/LifeView.vue webui-src/src/views/MemoryView.vue webui-src/interactionContracts.test.ts
git commit -m "feat: refine observatory interaction states"
```

## Task 9: Build both plugin surfaces and perform Browser visual QA

**Files:**

- Modify (generated): `UI/index.html`
- Modify (generated): `pages/dashboard/index.html`
- Preserve evidence under: `D:\bun\tmp\codex\Sylanne-next\evidence`

- [ ] **Step 1: Run the complete automated verification**

```powershell
$taskTmp='D:\bun\tmp\codex\Sylanne-next'
$env:TEMP=$taskTmp; $env:TMP=$taskTmp; $env:TMPDIR=$taskTmp
Set-Location 'D:\bun\tmp\codex\Sylanne-next\worktree\webui-src'
pnpm test
pnpm build
Set-Location '..'
python -m pytest tests/test_observation_history.py tests/test_webui_contract.py tests/test_state_persistence.py -q
python -m ruff check main.py sylanne_alpha/observation_history.py sylanne_alpha/webui_routes.py sylanne_alpha/webui_server.py sylanne_alpha/session_context.py tests/test_observation_history.py tests/test_webui_contract.py
git diff --check
```

The production build must generate the same current source state into both `UI/index.html` and `pages/dashboard/index.html`.

- [ ] **Step 2: Start the standalone plugin WebUI with all temp paths on D**

Run the repository's normal development/start command with `TEMP`, `TMP`, and `TMPDIR` set to `D:\bun\tmp\codex\Sylanne-next`. Keep logs and screenshots under `D:\bun\tmp\codex\Sylanne-next\evidence`.

- [ ] **Step 3: Use the user's installed Browser for standalone QA**

Verify at desktop and mobile widths:

- login button is present on every reload;
- pending, error, success, and logout states work;
- login success contains no circle/radial reveal;
- the line is first, nodes follow its head, and all content begins after line completion;
- top bar moves down, footer moves up, and cards move outward;
- all seven chambers open, show real/empty-history truthfully, close by button/Escape/backdrop, and restore focus;
- session switching never flashes another session's data;
- light, dark, keyboard, and reduced-motion states remain usable.

- [ ] **Step 4: Use the same Browser for AstrBot native Pages QA**

Open the plugin through the AstrBot Pages host, not through a standalone or repository-hosting URL. Verify:

- `window.AstrBotPluginPage` bridge requests reach the plugin routes;
- state and observation-history endpoints resolve under the host prefix;
- host authentication does not show standalone login/logout;
- the host sidebar and page chrome do not replay or clip the plugin arrival;
- reloading and switching sessions do not intermittently hide controls.

- [ ] **Step 5: Perform Product Design visual comparison**

At the same viewport and state, compare:

1. `docs/superpowers/specs/assets/sylanne-conservative-visual-novel-direction.png`
2. the implementation screenshot;
3. `docs/superpowers/specs/assets/sylanne-observation-chamber-expanded.png`
4. the expanded implementation screenshot.

Use one combined visual inspection pass and record a fidelity ledger covering at least:

- unchanged palette/material;
- unchanged information architecture;
- correct spine/node timing;
- correct bar/card directions;
- correct chamber size/origin/focus;
- absence of radial shapes;
- mobile and dark-mode legibility.

Fix visible spacing, crop, radius, weight, or motion mismatches and compare again.

- [ ] **Step 6: Stage generated assets and commit the verified result**

```powershell
Set-Location 'D:\bun\tmp\codex\Sylanne-next\worktree'
git add UI/index.html pages/dashboard/index.html
git commit -m "build: refresh AstrBot dashboard assets"
git status --short
```

Expected final status: only intentionally preserved Browser evidence/cache paths remain untracked; no source or generated build is unstaged.
