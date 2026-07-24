# V1Core Complete Removal Design

**Status:** Proposed for user review  
**Date:** 2026-07-24  
**Scope:** Runtime cognition, frozen computation fallback, old core snapshots, and dead compatibility scaffolding

## Context

The repository already removed the old nine-agent PRE/POST/RESPONSE_POST cognition calls, but it still exposes a `sylanne_enable_v2core` switch whose false branch is documented as a v1 rollback. It also retains dead reactive-agent APIs, an unused v1-to-v2 migrator, a legacy snapshot import tool, and a frozen `ComputationSpine` fallback behind `AlphaKernel`.

At the same time, several live components are incorrectly called "legacy" even though they are not v1 cognition:

- `AlphaKernel` plus `ResonanceSpine` owns embodied state behind the v2 `BodyPort`.
- `LLMResponsePipeline` owns sanitization, semantic segmentation, physical message delivery, AstrBot history, and actual-delivery observation.
- v3 owns an isolated codec and shadow-state protocol whose version names do not denote v1core.

Deleting those live responsibilities by filename or by the word `legacy` would break v2/v3 rather than remove v1.

## Considered Approaches

### A. Remove only the public switch

Delete `sylanne_enable_v2core` from the configuration schema and force the existing flag helper to return true. This is low risk, but it leaves dead v1 APIs, old snapshot import, and the frozen computation fallback in the package. It does not satisfy complete removal.

### B. Remove rollback and migrations, retain frozen computation fallback

Make v2 mandatory, delete old core migration/import code, and leave `ComputationSpine` as an import-time fallback if `ResonanceSpine` fails. This reduces compatibility surface but still preserves a second, untested body backend and permits silent architectural rollback. It also does not satisfy complete removal.

### C. Complete removal with live-capability extraction (selected)

Make v2 mandatory, delete all v1 rollback and old-core state readers, reduce the agent framework to autonomous life scheduling, and make `ResonanceSpine` the only embodied backend. Retain delivery and body capabilities that v2/v3 actively consume, but give them explicit v2-era ownership and remove all control flow describing them as a v1 fallback.

This is the selected design because the user explicitly required v1core to be completely removed.

## Runtime Architecture

### Cognition authority

`DefaultRenderer.render()` remains the only producer of `Reply`. `apply_v2core_request()` and `apply_v2core_response()` become unconditional runtime stages; no configuration value can bypass them. `ReplyKind.SILENT` suppresses physical delivery, while `SPEAK` and `FALLBACK` continue into the delivery layer.

The delivery continuation is not a cognitive fallback. Its contract is:

1. sanitize the v2 completion;
2. validate model-authored semantic beats;
3. dispatch the resulting message chain;
4. record actual delivery outcome;
5. update AstrBot history and observers exactly once;
6. settle v2/v3 with delivered, unknown, or cancelled evidence.

Comments, variables, and tests must call this a delivery continuation, not a return to v1 or legacy cognition.

### Embodied state

`CanonicalKernelBodyPort` continues to expose `observe()`, `tick()`, and `snapshot()` to v2. `AlphaKernel` remains the host of identity and embodied state, but it constructs `ResonanceSpine` directly. Import failure is fatal and visible; it must not silently instantiate `ComputationSpine`.

The frozen `ComputationSpine` implementation and modules proven exclusive to it are deleted. Modules shared by `ResonanceSpine` remain even when their comments historically mention `ComputationSpine`.

### Autonomy

The old reactive agent phases `PRE`, `POST`, and `RESPONSE_POST`, along with `AgentIntent`, `compose_inputs()`, and dead `run_cycle()` paths, are deleted. The remaining autonomy API supports only `AUTONOMOUS` execution for `LifeAgent` and `AutonomyScheduler`. Life prompt material continues through the existing life-simulation read model rather than a PRE intent.

### v3 boundary

v3 remains isolated behind immutable DTOs and its effect committer. Its codec revisions, `V2SeedSnapshotV1`, `PolicyScorerV1`, and formula/profile identifiers are v2/v3 protocol names, not v1core. They remain unless separately proven unreachable.

This retirement does not promote v3 shadow output to live reply authority. Promotion requires a separate design because current v3 deliberately suppresses reply, prompt, tool, body, history, and memory effects.

## Configuration And Persistence

The following behavior is removed:

- `sylanne_enable_v2core` in `_conf_schema.json`, README, defaults, and runtime branches;
- any false-path behavior that skips v2 request or response processing;
- `v2core/migration.py`, its unused `SessionStore` support, and their tests;
- `import_sylanne_legacy` and the old core snapshot importer;
- loading a frozen computation backend as an import fallback.

Old v1core snapshots are not imported, translated, or used as a rollback source. Startup uses current v2 domain state and current Resonance body state only. An old-only core snapshot is ignored with a concise warning and no automatic mutation.

Current memory-system normalization is retained. `memory_legacy_formats.py` migrates user memory records into the current memory system and is not a v1 cognitive-core snapshot reader. Removing user memory compatibility is outside this retirement and would require a separate destructive-data decision.

v3 codec recovery is also retained because it upgrades v3 state to the current v3 schema and does not re-enable v1 cognition.

## WebUI Read Model

`/api/state` exposes embodied Resonance telemetry with schema `sylanne.webui.state.v2` and route keys such as `RESONANCE` and `SKIP`. `/api/v2core_state` remains the cognition/reply-authority projection. The UI must not show FAST/NORMAL/FULL counters from the deleted computation backend.

No WebUI setting may reintroduce a v1 or v2-disable switch. If v2 initialization fails, the UI reports an unavailable cognition core rather than presenting a rollback control.

## Failure Behavior

- Failure to import or initialize `ResonanceSpine` fails plugin initialization with a stack trace.
- Failure inside v2 request/response processing is observable and fail-closed; it cannot route to v1 cognition.
- Delivery failures preserve unsent text and settle actual outcome as unknown/cancelled according to the existing exactly-once contract.
- Encountering old v1core-only state never invokes a migration path.
- v3 failures remain isolated and cannot change live v2 reply or delivery.

## Deletion And Migration Order

1. Add invariant tests that v2 cannot be disabled and v1 rollback symbols are absent.
2. Remove the public toggle and all false branches.
3. Rename response continuation semantics from v1/legacy fallback to v2 delivery ownership.
4. Reduce the agent framework to AUTONOMOUS-only execution.
5. Delete unused v1 migrator, SessionStore, EngineFacade, and old snapshot import surface.
6. Make Resonance mandatory, then delete the frozen computation implementation and exclusive dependencies.
7. Remove obsolete docs, tests, exports, package entries, and generated artifacts.
8. Run focused architecture tests, the full Python suite, frontend tests/build, Ruff, 2718lab validators, and package reproducibility checks.

## Acceptance Criteria

- Repository search finds no `sylanne_enable_v2core`, v1 rollback text, v1core migration entry point, or runtime `ComputationSpine` fallback.
- No request or response path can bypass v2 cognition.
- `ResonanceSpine` is the only constructed computation backend.
- Old v1core-only snapshots are never read or migrated.
- Autonomous life scheduling still initializes, ticks, and terminates cleanly.
- Semantic segmentation rejects punctuation-only beats and falls back to one complete message.
- AstrBot Page WebUI uses the official bridge; standalone WebUI keeps its own token flow.
- WebUI reports live Resonance route/session data and no deleted FAST/NORMAL/FULL projection.
- v2/v3 isolation, exactly-once settlement, persistence, delivery, and package tests pass.

## Non-Goals

- Promoting v3 shadow decisions to live reply authority.
- Deleting current user-memory compatibility formats.
- Replacing `AlphaKernel` or the v2 `BodyPort` with a new body implementation.
- Changing AstrBot message delivery semantics beyond renaming ownership and preserving the existing contract.
