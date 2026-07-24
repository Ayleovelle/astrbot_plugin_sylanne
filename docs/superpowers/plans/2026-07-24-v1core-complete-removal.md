# V1Core Complete Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove every v1 cognition rollback, frozen computation fallback, old-core migration path, and dead reactive-agent API while preserving the live v2 delivery, Resonance body, autonomous life, and isolated v3 contracts.

**Architecture:** v2 becomes an unconditional request/response stage and `ResonanceSpine` becomes the only embodied computation backend. Current-schema state restoration remains supported, but schema-mismatched v1/3.x state is ignored rather than migrated; autonomy is reduced to an explicit AUTONOMOUS-only worker contract.

**Tech Stack:** Python 3.11+, pytest, Ruff, AstrBot v4.26.5 APIs, Vue 3/Vite/Vitest, 2718lab validators

---

### Task 1: Make v2 Cognition Unconditional

**Files:**
- Modify: `_conf_schema.json`
- Modify: `sylanne_alpha/v2core/integration.py`
- Modify: `main.py`
- Modify: `sylanne_alpha/llm_request_pipeline.py`
- Modify: `README.md`
- Modify: `tests/test_v1core_retired.py`
- Modify: `tests/test_v2core_bridge.py`
- Modify: tests that assert a v2-disabled branch

- [ ] **Step 1: Replace rollback tests with absence/invariance tests**

```python
def test_v2core_switch_is_absent_from_schema() -> None:
    schema = json.loads(Path("_conf_schema.json").read_text(encoding="utf-8"))
    assert "sylanne_enable_v2core" not in schema


def test_v2core_integration_has_no_runtime_disable_helper() -> None:
    import sylanne_alpha.v2core.integration as integration
    assert not hasattr(integration, "v2core_enabled")
    assert "sylanne_enable_v2core" not in inspect.getsource(integration)
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python -m pytest tests/test_v1core_retired.py tests/test_v2core_bridge.py -q`  
Expected: failures showing the schema key and `v2core_enabled` still exist.

- [ ] **Step 3: Remove the flag and all false branches**

Delete `_V2CORE_FLAG`, `v2core_enabled()`, and its export. In each integration entry point remove only the disable predicate, preserving unrelated guards such as cron events and missing requests:

```python
if request is None or _is_cron_event(event):
    return False
```

Remove v2 checks from `main.py` bridge/seed initialization and from request-pipeline state capture. Remove the configuration item and all README text promising a v1 rollback.

- [ ] **Step 4: Update branch-specific tests**

Tests that previously set `sylanne_enable_v2core=False` must either remove that irrelevant fixture key or assert the new invariant: the key is ignored and v2 still executes. No replacement kill switch is introduced.

- [ ] **Step 5: Run the v2/request/response suites and verify GREEN**

Run: `python -m pytest tests/test_v1core_retired.py tests/test_v2core_bridge.py tests/test_context_integrity_fixes.py tests/test_quality_drift_canonical.py tests/test_user_backfill_on_silent.py tests/test_err_turn_user_backfill.py -q`  
Expected: all selected tests pass and no source reference to `sylanne_enable_v2core` remains.

### Task 2: Make Delivery a v2 Continuation, Not a v1 Fallback

**Files:**
- Modify: `sylanne_alpha/v2core/integration.py`
- Modify: `main.py`
- Modify: `sylanne_alpha/llm_response_pipeline.py`
- Modify: `tests/test_v1core_retired.py`
- Test: `tests/test_v2core_bridge.py`
- Test: `tests/test_realtime_dispatch.py`

- [ ] **Step 1: Add a source contract rejecting v1 fallback semantics**

```python
def test_v2_speak_continues_to_delivery_without_v1_fallback_language() -> None:
    source = inspect.getsource(importlib.import_module("sylanne_alpha.v2core.integration"))
    assert "回退到 v1" not in source
    assert "legacy 的嘴" not in source
    assert "delivery continuation" in source
```

- [ ] **Step 2: Run the source contract and verify RED**

Run: `python -m pytest tests/test_v1core_retired.py -q`  
Expected: failure on the current module docstring/comments.

- [ ] **Step 3: Rename ownership without changing delivery behavior**

Document `apply_v2core_response()` as returning whether physical delivery must be suppressed. Keep the boolean wire contract for blast-radius control, but rename local `handled` variables to `suppress_delivery` and describe SPEAK/FALLBACK as continuing into `LLMResponsePipeline` for sanitization, segmentation, dispatch, history, and actual-outcome observation.

Do not move or duplicate delivery logic. `SILENT` remains the only path that suppresses downstream delivery.

- [ ] **Step 4: Run delivery and exactly-once settlement tests**

Run: `python -m pytest tests/test_v2core_bridge.py tests/test_realtime_dispatch.py tests/test_semantic_segmentation.py tests/test_context_integrity_silent_history.py -q`  
Expected: all tests pass; SPEAK, FALLBACK, SILENT, cancellation, and partial delivery retain their prior observable behavior.

### Task 3: Remove Dead v1 Migration and Facade Scaffolding

**Files:**
- Delete: `sylanne_alpha/v2core/migration.py`
- Delete: `sylanne_alpha/v2core/session_store.py`
- Delete: `tests/test_migration_v2.py`
- Modify: `sylanne_alpha/engine_adapter.py`
- Modify: `sylanne_alpha/memory_migration_spine.py`
- Modify: `tests/test_engine_adapter.py`
- Modify: `tests/test_v1core_retired.py`

- [ ] **Step 1: Add absence tests for unused migration/facade APIs**

```python
def test_dead_v1_migration_modules_are_absent() -> None:
    assert importlib.util.find_spec("sylanne_alpha.v2core.migration") is None
    assert importlib.util.find_spec("sylanne_alpha.v2core.session_store") is None


def test_engine_adapter_has_no_unused_facade() -> None:
    import sylanne_alpha.engine_adapter as adapter
    assert not hasattr(adapter, "EngineFacade")
    assert adapter.derive_should_send({"action": "reach_out"}, {"allowed": True})
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/test_v1core_retired.py tests/test_engine_adapter.py tests/test_migration_v2.py -q`  
Expected: absence assertions fail while old migration tests still import deleted candidates.

- [ ] **Step 3: Delete unreachable migration storage**

Delete `migration.py`, `session_store.py`, and `test_migration_v2.py`. Rewrite `memory_migration_spine.py` comments so they describe only the current memory normalization path and do not reserve a future StateMigrator hook.

- [ ] **Step 4: Remove only `EngineFacade`, retain live pure adapters**

Keep `SEND_ACTIONS`, `derive_should_send()`, `sdk_state_to_body()`, and `sdk_surface_to_compat()` because active proactive code/tests consume them. Delete the uninstantiated `EngineFacade` class and lifecycle imports/comments.

- [ ] **Step 5: Run focused adapter/memory tests**

Run: `python -m pytest tests/test_engine_adapter.py tests/test_mem02_restore_wiring.py tests/test_memory_golden_roundtrip.py -q`  
Expected: all current memory behavior and proactive send derivation pass without migration/facade classes.

### Task 4: Reject Old Core Snapshots While Preserving Current Restore

**Files:**
- Delete: `sylanne_alpha/_engine/sylanne_core/compute/importer.py`
- Modify: `sylanne_alpha/_engine/sylanne_core/compute/kernel.py`
- Modify: `sylanne_alpha/_engine/sylanne_core/compute/runtime.py`
- Modify: `sylanne_alpha/_engine/sylanne_core/compute/host.py`
- Modify: `sylanne_alpha/__init__.py`
- Modify: `main.py`
- Modify: snapshot/runtime tests

- [ ] **Step 1: Add runtime tests for current restore and old-state rejection**

```python
def test_runtime_restores_only_current_schema(tmp_path: Path) -> None:
    runtime = AlphaRuntime(tmp_path)
    current = AlphaKernel.boot("s")
    runtime.save(current)
    assert runtime.load("s").snapshot()["schema_version"] == SCHEMA_VERSION


def test_runtime_ignores_schema_mismatch_without_migrating(tmp_path: Path, caplog) -> None:
    path = tmp_path / "s.alpha.json"
    original = '{"schema_version":"sylanne.legacy.v1","emotion":{"turns":99}}'
    path.write_text(original, encoding="utf-8")
    kernel = AlphaRuntime(tmp_path).load("s")
    assert kernel.turns == 0
    assert path.read_text(encoding="utf-8") == original
    assert "unsupported snapshot schema" in caplog.text
```

- [ ] **Step 2: Run the runtime tests and verify RED**

Run: `python -m pytest tests -q -k "runtime and (restore or schema or legacy)"`  
Expected: the mismatched snapshot is currently migrated through `import_legacy_body()`.

- [ ] **Step 3: Remove legacy parameters and importer calls**

Change `AlphaKernel.boot()` to accept only current construction parameters and always create a fresh body. `AlphaRuntime.load(session_key)` restores only when `data["schema_version"] == SCHEMA_VERSION`; otherwise it logs a warning and returns a fresh boot without writing or renaming the source file.

Remove `legacy` from `SylanneAlphaHost`, `AlphaRuntime.load()`, and all constructors. Delete `main.py::import_sylanne_legacy`, `importer.py`, and the public `import_legacy_body` export.

- [ ] **Step 4: Preserve current snapshot recovery behavior**

Malformed JSON may still be quarantined as `.damaged` according to the existing corruption contract. Current-schema snapshots must still call `AlphaKernel.restore()` and restore Resonance computation state, hot pool, personality, and affect debt.

- [ ] **Step 5: Run persistence and recovery suites**

Run: `python -m pytest tests/test_memory_golden_roundtrip.py tests/test_mem02_restore_wiring.py tests/test_fixlist_p0_7_persistence.py tests/test_vendored_sdk_sync.py -q`  
Expected: current persistence passes; tests explicitly requiring 3.x import are removed or rewritten to assert rejection.

### Task 5: Make ResonanceSpine the Only Body Backend

**Files:**
- Delete: `sylanne_alpha/_engine/sylanne_core/compute/computation_spine.py`
- Modify: `sylanne_alpha/_engine/sylanne_core/compute/kernel.py`
- Modify: `sylanne_alpha/host.py`
- Modify: `sylanne_alpha/llm_request_pipeline.py`
- Modify: `sylanne_alpha/session_context.py`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `tests/test_v1core_retired.py`
- Modify: engine tests that mention fallback backend

- [ ] **Step 1: Add Resonance-only architecture tests**

```python
def test_resonance_is_the_only_computation_backend() -> None:
    kernel = AlphaKernel.boot("s")
    assert type(kernel.computation) is ResonanceSpine
    source = inspect.getsource(importlib.import_module(
        "sylanne_alpha._engine.sylanne_core.compute.kernel"
    ))
    assert "ComputationSpine" not in source
    assert "except ImportError" not in source
```

- [ ] **Step 2: Run the architecture test and verify RED**

Run: `python -m pytest tests/test_v1core_retired.py -q`  
Expected: source still imports and falls back to `ComputationSpine`.

- [ ] **Step 3: Replace fallback construction with a direct type**

```python
from .resonance_integration import ResonanceSpine

@dataclass(slots=True)
class AlphaKernel:
    computation: ResonanceSpine = field(default_factory=ResonanceSpine)
```

Use `ResonanceSpine(...)` directly for profile-aware boot/restore. Delete `computation_spine.py`; retain HDC, HGT, boundary, predictive gate, autopoiesis, and other modules that `ResonanceSpine` imports.

- [ ] **Step 4: Remove obsolete compatibility probes and docs**

Where live code currently probes both `.gate`/`._gate`, `.boundary`/`._boundary`, or public/hidden sheaf solely for the deleted backend, use the Resonance attribute directly. Update README/CHANGELOG claims so there is no frozen fallback promise.

- [ ] **Step 5: Run engine/body/WebUI suites**

Run: `python -m pytest tests/test_vendored_sdk_sync.py tests/test_fixlist_p0_3_affect_to_body.py tests/test_fixlist_p0_4_postlearning_pipe.py tests/test_webui_contract.py -q`  
Expected: Resonance behavior, BodyPort snapshots, and WebUI telemetry all pass.

### Task 6: Reduce the Agent Framework to AUTONOMOUS Only

**Files:**
- Delete: `sylanne_alpha/agents/event_bus.py`
- Modify: `sylanne_alpha/agents/base.py`
- Modify: `sylanne_alpha/agents/life_agent.py`
- Modify: `sylanne_alpha/agents/self_core.py`
- Modify: `sylanne_alpha/agents/autonomy_scheduler.py`
- Modify: `sylanne_alpha/agents/__init__.py`
- Modify: `main.py`
- Rewrite: `tests/test_agents_infra.py`
- Modify: `tests/test_v1core_retired.py`

- [ ] **Step 1: Replace reactive-agent tests with autonomy tests**

```python
def test_agent_package_exports_only_autonomous_contract() -> None:
    import sylanne_alpha.agents as agents
    for retired in ("PRE", "POST", "RESPONSE_POST", "AgentIntent", "EventBus", "ComposedInputs"):
        assert not hasattr(agents, retired)
    assert agents.AUTONOMOUS == "autonomous"


def test_autonomy_scheduler_calls_explicit_autonomous_cycle() -> None:
    source = inspect.getsource(AutonomyScheduler)
    assert "run_autonomous_cycle" in source
    assert "run_cycle" not in source
```

- [ ] **Step 2: Run autonomy tests and verify RED**

Run: `python -m pytest tests/test_agents_infra.py tests/test_v1core_retired.py -q`  
Expected: retired symbols and generic `run_cycle()` still exist.

- [ ] **Step 3: Simplify the worker contract**

Keep `SKIP`, `RULE`, `LLM`, `AUTONOMOUS`, and `CognitiveAgent` only as required by `LifeAgent`. Remove `VALID_FLAGS`, reactive phase constants, `AgentIntent`, EventBus coupling, and `emit()`.

`LifeAgent` has only `phases = (AUTONOMOUS,)`; delete its PRE gate and `life_context` intent return. Its autonomous `act()` continues to call `LifeSimulator.simulate_tick()` and returns `None`.

- [ ] **Step 4: Narrow SelfCore and scheduler calls**

Replace generic `run_cycle(session_key, surface, phase=...)` with `run_autonomous_cycle(session_key, surface)`. Delete `ComposedInputs`, `compose_inputs()`, and LLM-budget logic that only arbitrated multiple reactive agents. Keep evolution/reflex/behavior methods consumed by v2 integration.

Construct `LifeAgent(self)` without a bus in `main.py`, and update `AutonomyScheduler` to call only `run_autonomous_cycle()`.

- [ ] **Step 5: Run autonomy/life/v2 integration suites**

Run: `python -m pytest tests/test_agents_infra.py tests/test_v1core_retired.py tests/test_wave4_reflex_reconnect.py tests/test_wave6_adaptation_foundation.py tests/test_wave_l2_t1_03_night_rhythm.py -q`  
Expected: autonomous ticks, evolution state, reflex learning, start/stop, and v2 adaptation pass.

### Task 7: Final Cleanup, Verification, and Packaging

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: architecture/source-contract tests
- Rebuild: `UI/index.html`
- Generate: `pages/dashboard/index.html`
- Rebuild: `astrbot_plugin_sylanne.zip`
- Rebuild: `astrbot_plugin_sylanne.zip.sha256`

- [ ] **Step 1: Run repository absence scans**

Run: `git grep -n -I -E "sylanne_enable_v2core|回退.*v1|legacy 的嘴|class ComputationSpine|class StateMigrator|class SessionRegistryStore|class EngineFacade|import_sylanne_legacy|AgentIntent|RESPONSE_POST" -- . ':!docs/superpowers/**'`  
Expected: no live-code/config/runtime matches; historical design docs may retain explanatory references.

- [ ] **Step 2: Run format, lint, and full focused matrix**

Run: `python -m ruff check main.py sylanne_alpha tests`  
Run: `python -m pytest tests/test_semantic_segmentation.py tests/test_v1core_retired.py tests/test_v2core_bridge.py tests/test_webui_contract.py tests/test_webui_life_api.py tests/test_v3_contracts_boundaries.py tests/test_v3_effect_committer.py tests/test_v3_grey_isolation.py -q`  
Expected: zero Ruff errors and all focused tests pass.

- [ ] **Step 3: Run the complete backend and frontend suites**

Run: `python -m pytest tests -q`  
Run: `npm.cmd test` from `webui-src`  
Run: `npm.cmd run build` from `webui-src`  
Expected: Python and Vitest suites pass; Vue typecheck/Vite build succeeds; `UI/index.html` and `pages/dashboard/index.html` have identical SHA-256 hashes.

- [ ] **Step 4: Run 2718lab validators**

Run: `python C:/Users/pidan/.codex/plugins/cache/pidan-local-plugins/2718lab-devkit/0.1.0/skills/astrbot-plugin-dev/scripts/validate_plugin.py G:/Sylanne-next`  
Run: `python C:/Users/pidan/.codex/plugins/cache/pidan-local-plugins/2718lab-devkit/0.1.0/skills/python-engineering/scripts/validate_project.py G:/Sylanne-next`  
Expected: zero errors; each warning is explicitly reviewed.

- [ ] **Step 5: Browser-check the delivered WebUI**

Use the Playwright CLI against the local Vite server. Verify login behavior in standalone mode, nonblank monitor/cognition views, no console errors, no overlaps at desktop/mobile widths, and capture screenshots under `D:/bun/tmp/codex/sylanne-next-handoff/playwright/`.

- [ ] **Step 6: Independently review and rebuild the package**

Run a code-review pass focused on authority bypass, state loss, exactly-once delivery, v3 isolation, and package omissions. Rebuild the ZIP only from the final verified source, confirm `pages/dashboard/index.html` is included, and regenerate its SHA-256 sidecar atomically.
