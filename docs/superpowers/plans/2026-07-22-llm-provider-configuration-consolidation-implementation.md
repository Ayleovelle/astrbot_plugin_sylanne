# LLM Provider Configuration Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce normal setup to zero required provider choices and one optional shared auxiliary text model while preserving old explicit provider behavior.

**Architecture:** A central provider router owns feature-specific overrides, legacy aliases, shared auxiliary inheritance, current/default chat fallback, multimodal discovery, and embedding-type separation. The existing Vue settings page renders one Model Strategy card and moves specialized overrides behind a local advanced toggle using existing components and tokens.

**Tech Stack:** Python 3.10–3.13, AstrBot v4.26.5 provider APIs, Vue 3, TypeScript, Vite, pytest, Node test runner/Vitest if added through the existing pnpm lockfile, Ruff, Pyright.

---

**Shared-worktree rule:** Task workers must not commit or push. The root integration agent stages the reviewed files only after backend, frontend, browser, and migration gates pass.

### Task 1: Central text-provider router

**Files:**
- Create: `sylanne_alpha/provider_routing.py`
- Create: `tests/test_provider_routing.py`

- [ ] **Step 1: Write failing precedence tests**

```python
@pytest.mark.parametrize(
    ("feature", "config", "expected"),
    [
        ("life", {"sylanne_alpha_life_simulation_provider_id": "life"}, "life"),
        ("life", {"sylanne_alpha_aux_provider_id": "aux"}, "aux"),
        ("relationship", {"emotion_provider_id": "legacy"}, "legacy"),
        (
            "qzone",
            {
                "sylanne_alpha_life_simulation_provider_id": "life",
                "sylanne_alpha_aux_provider_id": "aux",
            },
            "life",
        ),
    ],
)
async def test_text_provider_precedence(feature, config, expected, fake_context):
    resolved = await resolve_text_provider(
        feature=feature,
        config=config,
        context=fake_context,
        umo="qq:friend:1",
    )
    assert resolved.provider_id == expected
```

Add explicit tests for missing/deleted overrides, manual IDs, current-conversation fallback, background default fallback, disabled assessor behavior, and a provider lookup exception.

- [ ] **Step 2: Run RED**

```powershell
python -m pytest tests/test_provider_routing.py -q
```

Expected: module import fails.

- [ ] **Step 3: Implement typed routing results**

```python
class ProviderFeature(str, Enum):
    ASSESSOR = "assessor"
    MAIN_ASSESSOR = "main_assessor"
    LIFE = "life"
    RELATIONSHIP = "relationship"
    QZONE = "qzone"
    TRANSCRIPTION = "transcription"


@dataclass(frozen=True, slots=True)
class ProviderResolution:
    provider: Any | None
    provider_id: str
    mode: str
    reason: str
    explicit_invalid: bool = False
```

Encode feature key chains as immutable tuples. A nonblank explicit override that no longer exists returns `explicit_invalid=True` and does not silently change models. Only blank/inherited paths may fall through to auxiliary/current/default.

- [ ] **Step 4: Run GREEN and static checks**

```powershell
python -m pytest tests/test_provider_routing.py -q
ruff check sylanne_alpha/provider_routing.py tests/test_provider_routing.py
pyright sylanne_alpha/provider_routing.py
```

### Task 2: Embedding and transcription capability routing

**Files:**
- Modify: `sylanne_alpha/provider_routing.py`
- Modify: `tests/test_provider_routing.py`

- [ ] **Step 1: Write failing zero/one/many embedding tests**

```python
assert (await resolve_embedding_provider(config={}, context=no_embeddings)).mode == "unavailable"
assert (await resolve_embedding_provider(config={}, context=one_embedding)).mode == "auto"
assert (await resolve_embedding_provider(config={}, context=two_embeddings)).mode == "selection_required"
assert (await resolve_embedding_provider(
    config={"sylanne_alpha_embedding_memory_provider_id": "emb-2"},
    context=two_embeddings,
)).provider_id == "emb-2"
```

Assert that a chat provider with the same ID is never returned as an embedding provider.

- [ ] **Step 2: Write failing transcription discovery tests**

Cover explicit valid override, explicit invalid override, automatic multimodal match, auxiliary provider accepted only when capability-compatible, and no compatible provider.

- [ ] **Step 3: Implement using verified AstrBot provider inventories**

Use `get_all_embedding_providers()` for embeddings. Use `get_all_providers()` plus the repository's existing multimodal detection logic for transcription; do not replace it with a model-name guess in the router.

- [ ] **Step 4: Run GREEN**

```powershell
python -m pytest tests/test_provider_routing.py -q
```

### Task 3: Integrate existing consumers without enabling new work

**Files:**
- Modify: `sylanne_alpha/llm_request_pipeline.py`
- Modify: `sylanne_alpha/life_simulation.py`
- Modify: `sylanne_alpha/v2core/rel_register.py`
- Modify: `sylanne_alpha/qzone_share.py`
- Modify: `sylanne_alpha/public_api.py`
- Modify: `tests/test_assessor_max_tokens.py`
- Modify: `tests/test_lifesim_routing_pri.py`
- Modify: `tests/test_qzone_share.py`
- Modify: `tests/test_webui_contract.py`

- [ ] **Step 1: Add consumer-level RED tests**

Prove these behaviors before editing production:

- an actually disabled assessor remains disabled even when an auxiliary provider exists;
- either dead advertised boolean key by itself does not enable LLM work;
- the legacy fast-assessor **provider** page key is honored when the real `sylanne_alpha_assessor_llm_enabled` switch is enabled;
- blank life provider uses auxiliary, then default;
- Qzone preserves `qzone -> life -> main -> legacy -> auxiliary -> default`;
- relationship classification uses explicit/legacy before auxiliary;
- relationship classification no longer depends on the nonexistent response-pipeline `_generic_llm_call` attribute;
- public API reports the same resolution mode the runtime uses.

- [ ] **Step 2: Run RED**

```powershell
python -m pytest tests/test_assessor_max_tokens.py tests/test_lifesim_routing_pri.py tests/test_qzone_share.py tests/test_webui_contract.py -q
```

- [ ] **Step 3: Replace duplicated lookup loops with router calls**

Do not change prompt text, temperature, token limits, retry counts, scheduling, or enable switches. Pass `persist=False` for internal direct provider calls where the existing provider supports the verified AstrBot v4.26.5 passthrough.

- [ ] **Step 4: Run GREEN plus life/Qzone regressions**

```powershell
python -m pytest tests/test_provider_routing.py tests/test_assessor_max_tokens.py tests/test_lifesim_routing_pri.py tests/test_lifesim_qzone_wiring.py tests/test_qzone_share.py -q
```

### Task 4: Canonical schema and derived settings metadata

**Files:**
- Modify: `_conf_schema.json`
- Modify: `sylanne_alpha/webui_routes.py`
- Modify: `webui-src/src/api/types.ts`
- Modify: `tests/test_webui_contract.py`

- [ ] **Step 1: Write failing schema/API contract tests**

Assert:

```python
assert schema["sylanne_alpha_aux_provider_id"]["_special"] == "select_provider"
assert schema["sylanne_alpha_aux_provider_id"]["ui_tier"] == "primary"
assert schema["sylanne_alpha_assessor_llm_enabled"]["default"] is False
assert schema["sylanne_alpha_life_simulation_provider_id"]["ui_tier"] == "advanced_provider"
assert schema["sylanne_alpha_fast_assessor_provider_id"]["ui_tier"] == "advanced_provider"
assert schema["sylanne_alpha_fast_assessor_enabled"]["invisible"] is True
assert schema["sylanne_alpha_main_assessor_enabled"]["invisible"] is True
assert response["model_routing"]["advanced_override_count"] == 2
```

Also assert `_conf_schema.json` remains strict JSON and every entry retains `description`, `type`, and `default`.

- [ ] **Step 2: Run RED**

```powershell
python -m pytest tests/test_webui_contract.py -k model_routing -q
```

- [ ] **Step 3: Add schema metadata and routing payload**

Add `sylanne_alpha_aux_provider_id` with blank default and a clear inheritance hint. Add the real `sylanne_alpha_assessor_llm_enabled` gate to the schema with its existing false default. Mark specialized provider rows—including the backward-compatible fast-assessor provider key—with `ui_tier: advanced_provider`; hide only the two dead advertised boolean rows while keeping old stored keys readable. Mark the embedding provider as Model-Strategy-owned so it does not duplicate in normal groups. Do not reinterpret either dead boolean as permission to start LLM work, and do not delete stored keys.

Extend TypeScript types:

```typescript
export interface SettingsSchemaEntry {
  description?: string
  type?: string
  default?: unknown
  invisible?: boolean
  options?: string[]
  ui_tier?: 'primary' | 'advanced_provider'
}

export interface ModelRoutingState {
  chat?: { mode?: string }
  auxiliary?: { mode?: string; provider_id?: string }
  transcription?: { mode?: string }
  embedding?: { mode?: string; provider_id?: string }
  advanced_override_count?: number
}
```

- [ ] **Step 4: Run schema and API GREEN**

```powershell
python -m pytest tests/test_webui_contract.py -q
python -c "import json; json.load(open('_conf_schema.json', encoding='utf-8'))"
```

### Task 5: Pure frontend model-routing view model

**Files:**
- Create: `webui-src/src/config/modelRouting.ts`
- Create: `webui-src/src/config/modelRouting.test.ts`
- Modify: `webui-src/package.json`
- Modify: `webui-src/pnpm-lock.yaml`

- [ ] **Step 1: Add the smallest existing-package-manager test runner**

Use pnpm because the repository owns `pnpm-lock.yaml`. Add Vitest only if it is not already resolvable from the lockfile; do not use npm or create a second lockfile. Add:

```json
"scripts": {
  "test": "vitest run",
  "build": "vue-tsc -b && vite build"
}
```

- [ ] **Step 2: Write failing pure view-model tests**

```typescript
it('shows zero required provider choices in automatic mode', () => {
  const vm = buildModelRoutingViewModel(responseWithNoOverrides)
  expect(vm.auxiliary.value).toBe('')
  expect(vm.auxiliary.label).toBe('跟随当前聊天模型')
  expect(vm.advancedOverrideCount).toBe(0)
})

it('keeps legacy overrides visible as an active count', () => {
  const vm = buildModelRoutingViewModel(responseWithLifeAndQzoneOverrides)
  expect(vm.advancedOverrideCount).toBe(2)
})

it('requires embedding choice only when automatic selection is ambiguous', () => {
  const vm = buildModelRoutingViewModel(responseWithTwoEmbeddings)
  expect(vm.embedding.mode).toBe('selection_required')
})
```

- [ ] **Step 3: Run RED**

```powershell
pnpm test -- modelRouting.test.ts
```

- [ ] **Step 4: Implement the pure typed adapter**

The adapter accepts `SettingsResponse`, returns display rows/options/status labels, and contains no Vue refs or API calls. It must prepend explicit empty-value inheritance/automatic options and filter embedding providers by provider type.

- [ ] **Step 5: Run GREEN**

```powershell
pnpm test -- modelRouting.test.ts
pnpm run build
```

### Task 6: Model Strategy card in the existing Config page

**Files:**
- Modify: `webui-src/src/views/ConfigView.vue`
- Modify: `webui-src/src/composables/useI18n.ts`
- Modify: `webui-src/src/config/modelRouting.test.ts`

- [ ] **Step 1: Write component-contract RED assertions**

The frontend tests must assert the normal groups exclude keys with `ui_tier === 'advanced_provider'`, the strategy card exposes one auxiliary selector, the advanced toggle reveals only specialized overrides, and dirty tracking writes only touched canonical/override keys. Keep this lightweight: test the pure partition/payload helpers from `modelRouting.ts` and use an SFC source contract for the one-card/one-selector wiring; do not add a second component-test framework.

- [ ] **Step 2: Run RED**

```powershell
pnpm test
```

- [ ] **Step 3: Implement with existing components and tokens**

Keep the two-pane page. Insert a `Card` titled from `config.model_strategy` at the top of the right pane. Reuse `Select`, `Toggle`, `Badge`, existing `.config-row`, and spacing/radius tokens. Do not add a new route, icon family, palette, or nested card grid.

Required visible states:

- chat model: read-only “跟随 AstrBot 当前会话”;
- auxiliary: inheritance option plus provider choices/manual entry;
- image understanding: read-only automatic status;
- embedding: disabled/auto/selection-required/explicit;
- advanced toggle and active override badge;
- save success and error behavior unchanged.

- [ ] **Step 4: Run frontend GREEN**

```powershell
pnpm test
pnpm run build
```

Expected: unit tests, `vue-tsc`, and Vite build all pass.

### Task 7: Browser, migration, and repository verification

**Files:**
- Modify only files required by defects found during this task's QA.

- [ ] **Step 1: Run backend verification**

```powershell
python -m pytest tests/test_provider_routing.py tests/test_webui_contract.py tests/test_assessor_max_tokens.py tests/test_lifesim_routing_pri.py tests/test_lifesim_qzone_wiring.py tests/test_qzone_share.py -q
ruff check sylanne_alpha/provider_routing.py sylanne_alpha/llm_request_pipeline.py sylanne_alpha/life_simulation.py sylanne_alpha/v2core/rel_register.py sylanne_alpha/qzone_share.py sylanne_alpha/public_api.py sylanne_alpha/webui_routes.py tests/test_provider_routing.py tests/test_webui_contract.py
pyright sylanne_alpha/provider_routing.py sylanne_alpha/llm_request_pipeline.py sylanne_alpha/life_simulation.py sylanne_alpha/v2core/rel_register.py sylanne_alpha/qzone_share.py sylanne_alpha/public_api.py sylanne_alpha/webui_routes.py
git diff --check
```

- [ ] **Step 2: Run AstrBot plugin validation**

```powershell
python C:\Users\pidan\.codex\plugins\cache\pidan-local-plugins\2718lab-devkit\0.1.0\skills\astrbot-plugin-dev\scripts\validate_plugin.py G:\Sylanne-next
```

Expected: zero errors; classify validator warnings that originate only from unrelated worktrees separately.

- [ ] **Step 3: Verify the real page in the in-app browser**

Use the existing WebUI dev/build flow. Verify desktop and mobile widths for automatic mode, one shared auxiliary provider, two active legacy overrides, embedding selection-required, manual provider ID, save success, and save error. Exercise the actual selectors/toggle/save path.

- [ ] **Step 4: Capture and inspect visual evidence**

Capture the existing source page before the UI edit and the final page at the same viewport. Inspect both images with `view_image`. Record at least five comparisons: two-pane geometry, card order, row alignment, control width/typography, advanced disclosure, and responsive collapse. Fix every material mismatch from the existing design system.

- [ ] **Step 5: Red-team and rollback review**

Independently test deleted provider IDs, manual unknown IDs, mixed old/new configs, disabled assessors, no default provider, provider lookup exceptions, multiple embeddings, capability misdetection, dirty-key saves, secret masking, and rollback to old row visibility. Resolve every P0/P1 before staging.
