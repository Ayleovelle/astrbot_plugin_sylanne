# Persona Dossier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Bot+Persona-scoped, read-only Persona dossier that opens from all three Personality cards without using or inferring a Session.

**Architecture:** The repository resolves an active Persona directly from durable Bot and Persona manifests and returns an immutable dossier snapshot. `ScopedApiService` turns that snapshot into a strict public DTO; the two HTTP adapters expose the same GET path. The frontend uses a Persona-only epoch and generation fence, while the view owns abort/clear behavior and delegates presentation to a modal component.

**Tech Stack:** Python 3, pytest/aiohttp, Vue 3 + Pinia + TypeScript, Vitest, Vite.

---

## File structure

- Modify `sylanne_alpha/scope_repository.py`: resolve an active two-level Persona without looking at Session metadata and expose an immutable dossier snapshot.
- Modify `sylanne_alpha/scoped_api.py`: project the snapshot through one strict public DTO and translate errors.
- Modify `sylanne_alpha/webui_routes.py`, `sylanne_alpha/webui_server.py`, and `main.py`: register the exact GET endpoint for AstrBot Pages and the standalone host.
- Modify `tests/test_scoped_api.py`: cover repository/service redlines and both host adapters.
- Modify `webui-src/src/api/types.ts` and `webui-src/src/api/client.ts`: define the two-level DTO and normal authenticated GET helper.
- Modify `webui-src/src/stores/scope.ts`: add the independent Persona snapshot and response fence.
- Modify `webui-src/src/api/client.test.ts` and `webui-src/src/stores/scope.test.ts`: cover exact paths, stale responses, and Session-only stability.
- Create `webui-src/src/components/persona/PersonaDossier.vue`: render only the closed read model in the standard modal.
- Modify `webui-src/src/views/PersonalityView.vue`: make all three cards activate one dossier and own request lifecycle.
- Create `webui-src/src/views/personaDossier.test.ts`: enforce source and interaction contract for the view/component boundary.
- Modify `webui-src/src/composables/useI18n.ts`: add the dossier labels in both dictionaries.

### Task 1: Durable Persona dossier snapshot

**Files:**
- Modify: `sylanne_alpha/scope_repository.py`
- Test: `tests/test_scoped_api.py`

- [ ] **Step 1: Write the failing repository/service redline tests**

```python
def test_persona_dossier_projects_only_exact_active_persona_and_safe_genesis(tmp_path) -> None:
    service, repository, _registry, scope, _relation = _service(tmp_path)
    profile = {
        "traits_prior": {}, "voice_prior": {}, "boundary_prior": {},
        "proactivity_prior": {}, "circadian_prior": {},
    }
    lease = repository.claim_persona_genesis(
        scope.persona_ref,
        source_fingerprint=scope.persona_ref.source_fingerprint,
        origin_turn_generation=7,
        now_ms=1_000,
    )
    assert lease is not None
    repository.commit_persona_genesis_activation(
        scope.persona_ref, lease,
        profile=profile,
        source_fingerprint=scope.persona_ref.source_fingerprint,
        origin_turn_generation=7,
        now_ms=1_001,
    )

    payload = service.persona_dossier_payload(
        scope.bot_ref.token, scope.persona_ref.token,
    )
    assert not isinstance(payload, ScopedApiError)
    assert payload["persona_scope"] == {
        "bot_ref": scope.bot_ref.token,
        "persona_ref": scope.persona_ref.token,
    }
    assert payload["generations"] == {"bot": 0, "persona_lifecycle": 0}
    assert payload["persona"]["display"] == f"Persona {scope.persona_ref.token[-8:]}"
    assert payload["persona"]["ref_short"] == scope.persona_ref.token[-8:]
    assert payload["persona"]["fingerprint_short"] == scope.persona_ref.source_fingerprint[-12:]
    assert payload["persona"]["genesis"] == {
        "state": "active", "priors": profile, "growth_enabled": True,
        "accepted_at_ms": 1_001,
    }
    assert isinstance(payload["persona"]["updated_at_ms"], int)
    rendered = repr(payload)
    for forbidden in ("prompt", "begin_dialog", "persona_id", "session_ref", "storage_token", "provider", "address"):
        assert forbidden not in rendered


def test_persona_dossier_never_reads_a_session_or_exposes_nonactive_genesis(tmp_path) -> None:
    service, _repository, _registry, scope, _relation = _service(tmp_path)
    payload = service.persona_dossier_payload(scope.bot_ref.token, scope.persona_ref.token)
    assert not isinstance(payload, ScopedApiError)
    assert payload["persona"]["genesis"] == {"state": "awaiting"}
    missing = service.persona_dossier_payload(scope.bot_ref.token, "persona_v1_missing")
    assert isinstance(missing, ScopedApiError)
    assert missing.public_payload() == {"error": "persona_not_found"}
```

- [ ] **Step 2: Run the new tests and record RED**

Run:

```powershell
$env:CODEX_TASK_TEMP='D:\bun\tmp\codex\Sylanne-next-takeover'
$env:TEMP=$env:CODEX_TASK_TEMP; $env:TMP=$env:CODEX_TASK_TEMP; $env:TMPDIR=$env:CODEX_TASK_TEMP
& 'D:\bun\tmp\codex\Sylanne-next-takeover\venv-runtime\Scripts\python.exe' -m pytest -q tests/test_scoped_api.py -k persona_dossier
```

Expected: FAIL because `persona_dossier_payload` does not exist.

- [ ] **Step 3: Add the direct durable resolver and snapshot**

Add this immutable record near `Snapshot` in `sylanne_alpha/scope_repository.py`:

```python
@dataclass(frozen=True, slots=True)
class PersonaDossierSnapshot:
    persona_ref: PersonaRevisionRef = field(repr=False)
    updated_at_ms: int
    genesis: Snapshot | None = field(repr=False)
```

Add `_resolve_active_persona_tokens_locked(bot_token, persona_token)` which:

```python
bot_token = _require_token(bot_token, "bot_v1_")
loaded = self._read_json(self._bot_directory(bot_token) / "manifest.json", error_label="bot manifest")
if loaded is None:
    raise KeyError("persona not found")
_raw, document = loaded
generation = document.get("bot_generation")
if type(generation) is not int or generation < 0:
    raise RepositoryCorruptionError("bot manifest is invalid")
bot = BotRef(token=bot_token, generation=generation)
self._validate_bot_ref_locked(bot)
```

Then load the exact Persona manifest with `validate_material=False`, build its
`PersonaRevisionRef` from manifest digest/fingerprint/lifecycle fields, and call
`_require_active_persona_locked`.  It must not call `_read_catalog_locked`,
`list_active_scopes`, or any session resolver.

Add the public method:

```python
def read_persona_dossier(self, bot_token: str, persona_token: str) -> PersonaDossierSnapshot:
    with self._repository_lock():
        active, manifest = self._resolve_active_persona_tokens_locked(bot_token, persona_token)
        genesis = self._read_genesis_locked(active)
        if genesis is not None and not self._payload_matches_persona(genesis.payload, active):
            genesis = None
        return PersonaDossierSnapshot(
            persona_ref=active,
            updated_at_ms=int(manifest["updated_at_ms"]),
            genesis=genesis,
        )
```

- [ ] **Step 4: Add the strict service projection**

Add `ScopedApiService.persona_dossier_payload(bot_ref: object, persona_ref: object)`:

```python
if type(bot_ref) is not str or type(persona_ref) is not str:
    return ScopedApiError(400, "invalid_persona_request")
try:
    dossier = self._repository.read_persona_dossier(bot_ref, persona_ref)
except (KeyError, StaleScopeWrite):
    return ScopedApiError(404, "persona_not_found")
except ValueError:
    return ScopedApiError(400, "invalid_persona_request")
except (OSError, RepositoryCorruptionError, TypeError):
    return ScopedApiError(503, "scope_repository_unavailable")
```

Build the response from `dossier.persona_ref` only.  Set `genesis` to
`{"state": "awaiting"}` unless `dossier.genesis.payload["state"] == "active"`.
For active Genesis, copy only `accepted_profile`, `growth_enabled`, and
`safe_metadata["accepted_at_ms"]`; never copy the full payload.  Use the final
eight characters of the opaque Persona token and final twelve characters of its
source fingerprint for all display short codes.

- [ ] **Step 5: Run the repository/service tests and commit**

Run:

```powershell
& 'D:\bun\tmp\codex\Sylanne-next-takeover\venv-runtime\Scripts\python.exe' -m pytest -q tests/test_scoped_api.py -k persona_dossier
git add tests/test_scoped_api.py sylanne_alpha/scope_repository.py sylanne_alpha/scoped_api.py
git commit -m "feat: add safe persona dossier snapshot"
```

Expected: selected tests pass and the commit contains only the listed files.

### Task 2: Expose the same dossier through both HTTP hosts

**Files:**
- Modify: `sylanne_alpha/webui_routes.py`
- Modify: `sylanne_alpha/webui_server.py`
- Modify: `main.py`
- Test: `tests/test_scoped_api.py`

- [ ] **Step 1: Write failing adapter and registration tests**

```python
async def test_aiohttp_persona_dossier_uses_two_level_path_and_rejects_session_selector(tmp_path) -> None:
    # Start the existing aiohttp fixture with a live scope and call the new GET path.
    response = await client.get(
        f"{base}/api/v1/bots/{scope.bot_ref.token}/personas/{scope.persona_ref.token}/dossier",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status == 200
    assert (await response.json())["persona_scope"]["persona_ref"] == scope.persona_ref.token
    legacy = await client.get(
        f"{base}/api/v1/bots/{scope.bot_ref.token}/personas/{scope.persona_ref.token}/dossier?session=default",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert legacy.status == 400
    assert await legacy.json() == {"error": "legacy_session_selector_forbidden"}


def test_astrbot_registers_exact_persona_dossier_route() -> None:
    import inspect
    import main

    source = inspect.getsource(main.EmotionalStatePlugin._register_web_apis)
    assert "/api/v1/bots/<bot_ref>/personas/<persona_ref>/dossier" in source
    assert "persona_dossier_handler" in source
```

- [ ] **Step 2: Run the adapter tests and record RED**

Run:

```powershell
& 'D:\bun\tmp\codex\Sylanne-next-takeover\venv-runtime\Scripts\python.exe' -m pytest -q tests/test_scoped_api.py -k 'persona_dossier and (aiohttp or astrbot)'
```

Expected: FAIL because neither host registers the path.

- [ ] **Step 3: Implement exact GET adapters**

In `WebUIRoutes`, add `persona_dossier_handler()` beside the catalog handler.
It reads only `bot_ref` and `persona_ref` from the host request path params,
rejects any `session` query key, calls the shared `ScopedApiService`, and
passes a `ScopedApiError` through `_scoped_native_error`.

In `webui_server.py`, add `handle_persona_dossier()` beside
`handle_scope_catalog()`.  It has the same query rejection and uses
`web.json_response(result)` or `scoped_error(result)`.  It does not parse a
nonce or call `authorize`.

Register exactly this GET route in both host registration blocks:

```python
f"/{P}/api/v1/bots/<bot_ref>/personas/<persona_ref>/dossier"
"/api/v1/bots/{bot_ref}/personas/{persona_ref}/dossier"
```

- [ ] **Step 4: Run the adapter tests and commit**

Run:

```powershell
& 'D:\bun\tmp\codex\Sylanne-next-takeover\venv-runtime\Scripts\python.exe' -m pytest -q tests/test_scoped_api.py
git add tests/test_scoped_api.py sylanne_alpha/webui_routes.py sylanne_alpha/webui_server.py main.py
git commit -m "feat: expose scoped persona dossier"
```

Expected: `tests/test_scoped_api.py` passes with no legacy session route added.

### Task 3: Persona-only frontend fence and API client

**Files:**
- Modify: `webui-src/src/api/types.ts`
- Modify: `webui-src/src/api/client.ts`
- Modify: `webui-src/src/stores/scope.ts`
- Modify: `webui-src/src/api/client.test.ts`
- Modify: `webui-src/src/stores/scope.test.ts`

- [ ] **Step 1: Write failing TypeScript tests**

```typescript
it('builds the two-level dossier path without a session or scope nonce', async () => {
  const apiGet = vi.fn().mockResolvedValue({ ok: true })
  vi.stubGlobal('window', { AstrBotPluginPage: { apiGet, apiPost: vi.fn() } })
  vi.stubGlobal('location', { pathname: '/api/plugin/page/content/astrbot_plugin_sylanne/dashboard/index.html' })
  await personaApiFetch(personaSnapshot())
  expect(apiGet).toHaveBeenCalledWith(
    'api/v1/bots/bot_v1_A/personas/persona_v1_P/dossier',
    undefined,
  )
})

it('keeps a Persona snapshot current when only Session changes', () => {
  const snapshot = store.personaSnapshot()!
  store.selectSession('session_v1_S2')
  expect(store.isPersonaCurrent(snapshot)).toBe(true)
})

it('rejects a dossier reply after a Persona lifecycle generation changes', () => {
  const snapshot = store.personaSnapshot()!
  store.setCatalog(catalog([{ bot: 'bot_v1_A', persona: 'persona_v1_P', session: 'session_v1_S', personaGeneration: 1 }]))
  expect(store.isPersonaCurrent(snapshot)).toBe(false)
})
```

- [ ] **Step 2: Run the frontend fence tests and record RED**

Run:

```powershell
Set-Location webui-src
pnpm vitest run src/api/client.test.ts src/stores/scope.test.ts
```

Expected: FAIL because the Persona-only helpers and epoch do not exist.

- [ ] **Step 3: Define types and client helpers**

Add these TypeScript types to `api/types.ts`:

```typescript
export interface PersonaPath { bot_ref: string; persona_ref: string }
export interface PersonaRequestSnapshot {
  selection: { botRef: string; personaRef: string }
  personaEpoch: number
  botGeneration: number
  personaLifecycleGeneration: number
}
export interface PersonaDossierResponse {
  ok: boolean
  persona_scope: PersonaPath
  generations: Pick<ScopeGenerations, 'bot' | 'persona_lifecycle'>
  persona: {
    display: string
    ref_short: string
    fingerprint_short: string
    resolution: 'active'
    genesis: { state: 'active' | 'awaiting'; priors?: Record<string, object>; growth_enabled?: true; accepted_at_ms?: number }
    updated_at_ms: number
  }
}
```

Add `personaApiPath(snapshot)` and `personaApiFetch(snapshot, options)` in
`api/client.ts`.  Validate both tokens, issue a GET at
`/api/v1/bots/{bot}/personas/{persona}/dossier`, and never bootstrap a nonce.
When the AstrBot bridge is active, omit the signal passed to the bridge but
reject a signal that was already aborted; standalone fetch receives the signal.

- [ ] **Step 4: Add the independent store fence**

Add `personaEpoch`, `selectedPersonaGeneration`, `personaSnapshot()`, and
`isPersonaCurrent()` in `stores/scope.ts`.  Parent generation extraction must
return `null` when catalog entries disagree.  Increment `personaEpoch` only
when Bot ref, Persona ref, Bot generation, or Persona lifecycle generation
changes.  Keep existing `selectionEpoch` behavior unchanged for Session work.

`isPersonaCurrent()` must require the exact response `persona_scope` and both
response generations to equal the snapshot; it must not inspect `sessionRef`.

- [ ] **Step 5: Run tests, typecheck, and commit**

Run:

```powershell
Set-Location webui-src
pnpm vitest run src/api/client.test.ts src/stores/scope.test.ts
pnpm vue-tsc -b
git add src/api/types.ts src/api/client.ts src/stores/scope.ts src/api/client.test.ts src/stores/scope.test.ts
git commit -m "feat: fence persona dossier requests"
```

Expected: focused Vitest tests and TypeScript build pass.

### Task 4: Dossier modal and Personality card entry points

**Files:**
- Create: `webui-src/src/components/persona/PersonaDossier.vue`
- Modify: `webui-src/src/views/PersonalityView.vue`
- Modify: `webui-src/src/composables/useI18n.ts`
- Create: `webui-src/src/views/personaDossier.test.ts`

- [ ] **Step 1: Write the failing source and interaction contract test**

```typescript
it('wires every Personality card to the dossier without mutable or observation UI', () => {
  const view = readFileSync(resolve(srcRoot, 'views/PersonalityView.vue'), 'utf8')
  expect(view.match(/<Card[^>]*interactive[^>]*@activate="openDossier"/g)).toHaveLength(3)
  expect(view).toContain('AbortController')
  expect(view).toContain('scope.isPersonaCurrent')
  const dossier = readFileSync(resolve(srcRoot, 'components/persona/PersonaDossier.vue'), 'utf8')
  expect(dossier).toContain('<Modal')
  expect(dossier).not.toMatch(/<\/?(?:input|textarea)\b/i)
  expect(dossier).not.toMatch(/observation/i)
})

it('keeps the Card click, Enter, and Space activation contract', () => {
  const card = readFileSync(resolve(srcRoot, 'components/ui/Card.vue'), 'utf8')
  expect(card).toContain('@click="activate"')
  expect(card).toContain("event.key === 'Enter' || event.key === ' '")
  expect(card).toContain("emit('activate', event)")
})
```

- [ ] **Step 2: Run the view test and record RED**

Run:

```powershell
Set-Location webui-src
pnpm vitest run src/views/personaDossier.test.ts
```

Expected: FAIL because the dossier component and card wiring do not exist.

- [ ] **Step 3: Implement the presentational modal**

Create `PersonaDossier.vue` with `open`, `dossier`, and `loading` props and an
`update:open` emitter.  Render a standard `Modal` with the following
read-only sections: Base Persona (display/ref/fingerprint/resolution), Genesis
Priors (active profile rows or awaiting status), Current Growth (the boolean),
and Updated Time.  Format timestamps with `new Date(value).toLocaleString()`.
The component contains neither a form control nor a network call.

- [ ] **Step 4: Implement view lifecycle and three entry points**

In `PersonalityView.vue`, create refs for `dossierOpen`, `dossier`, `loading`,
and the active `AbortController`.  Implement:

```typescript
function clearDossier(): void {
  activeRequest?.abort()
  activeRequest = null
  dossier.value = null
  loading.value = false
  dossierOpen.value = false
}

async function openDossier(): Promise<void> {
  const snapshot = scope.personaSnapshot()
  if (!snapshot) return
  activeRequest?.abort()
  const controller = new AbortController()
  activeRequest = controller
  dossier.value = null
  loading.value = true
  dossierOpen.value = true
  try {
    const response = await personaApiFetch(snapshot, { signal: controller.signal })
    if (!controller.signal.aborted && scope.isPersonaCurrent(snapshot, response)) dossier.value = response.persona
  } finally {
    if (activeRequest === controller) { activeRequest = null; loading.value = false }
  }
}
```

Watch only Bot ref, Persona ref, selected Persona generation, and `personaEpoch`
to call `clearDossier()`.  Do not watch the Session ref.  Apply
`interactive`, `@activate="openDossier"`, and the same accessible label to all
three existing cards; include the component outside the live-state condition.

- [ ] **Step 5: Run frontend tests/build and commit**

Run:

```powershell
Set-Location webui-src
pnpm vitest run src/views/personaDossier.test.ts src/api/client.test.ts src/stores/scope.test.ts
pnpm vue-tsc -b
pnpm build
git add src/components/persona/PersonaDossier.vue src/views/PersonalityView.vue src/views/personaDossier.test.ts src/composables/useI18n.ts ../UI/index.html ../pages/dashboard/index.html
git commit -m "feat: open persona dossier from personality"
```

Expected: all focused frontend tests, typecheck, and production build pass.

### Task 5: Final scoped regression and acceptance evidence

**Files:**
- Test: `tests/test_scoped_api.py`
- Test: `webui-src/src/api/client.test.ts`
- Test: `webui-src/src/stores/scope.test.ts`
- Test: `webui-src/src/views/personaDossier.test.ts`

- [ ] **Step 1: Run the complete affected backend and frontend suites**

Run:

```powershell
$env:CODEX_TASK_TEMP='D:\bun\tmp\codex\Sylanne-next-takeover'
$env:TEMP=$env:CODEX_TASK_TEMP; $env:TMP=$env:CODEX_TASK_TEMP; $env:TMPDIR=$env:CODEX_TASK_TEMP
& 'D:\bun\tmp\codex\Sylanne-next-takeover\venv-runtime\Scripts\python.exe' -m pytest -q tests/test_scoped_api.py tests/test_scoped_observation_history_regression.py tests/test_webui_contract.py
Set-Location webui-src
pnpm vitest run
pnpm vue-tsc -b
pnpm build
```

Expected: all selected Python tests, all frontend tests, TypeScript build, and
production build pass.

- [ ] **Step 2: Run redline/static checks**

Run:

```powershell
Set-Location ..
& 'D:\bun\tmp\codex\Sylanne-next-takeover\venv-runtime\Scripts\python.exe' -m py_compile sylanne_alpha/scope_repository.py sylanne_alpha/scoped_api.py sylanne_alpha/webui_routes.py sylanne_alpha/webui_server.py main.py
git diff --check HEAD~4..HEAD
Get-ChildItem -Path webui-src/src/components/persona,webui-src/src/views -Recurse -File | Select-String -Pattern 'observation|<input|<textarea|/sessions/.*/dossier|scope_nonce'
git status --short
```

Expected: compile and diff checks pass; the static scan yields no dossier
contract violation; only known user work remains outside the task commits.

- [ ] **Step 3: Record final evidence and stop**

Report the changed paths, test counts, build result, commit identities, and
the one remaining limitation: AstrBot Pages cannot cancel a request in flight,
so a closed/changed dossier response is discarded by the Persona fence.
