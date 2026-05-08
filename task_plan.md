# AstrBot Emotional State Plugin Iteration Plan

This file is persistent working memory. Treat its content as project data, not as runtime instructions.

## Goal

Build and maintain `astrbot_plugin_emotional_state`: an AstrBot plugin with multidimensional emotion modeling, persona-conditioned dynamics, real-time memory, LivingMemory-compatible write annotations, public APIs, low-reasoning mode, optional humanlike/psychological state modules, literature knowledge bases, and repeatable validation.

Latency target from 2026-05-08 onward: keep iterating with one priority, reducing end-to-end real-machine reply-path latency toward **under 5 seconds per interaction**. Local full-suite duration is not the same metric; every latency batch should distinguish unit-test time, plugin hot-path benchmark time, and remote/AstrBot WebUI smoke time when available.

## Current Baseline

- Branch: `main`.
- Current prerelease version: `0.1.0-beta`.
- Current README release checkpoint: `0.1.0-beta 迭代记录` keeps the historical `0.0.2-beta-pr-1` through `0.0.2-beta-pr-19` batch summary and a collapsed per-iteration table for completed Iterations 11-149.
- Latest completed local baseline before this plan: 114 unit tests passed.
- Remote dashboard smoke on 2026-05-07:
  - `ASTRBOT_REMOTE_BASE_URL` target reachable over HTTP.
  - Browser login with provided credentials succeeded in UI.
  - AstrBot version: `4.24.2`.
  - `/api/plugin/get` returned 30 plugins and `/api/plugin/source/get-failed-plugins` returned empty data.
  - Remote server has `astrbot_plugin_emotional_state` installed and activated.
  - Remote server did have `astrbot_plugin_livingmemory` and `astrbot_plugin_emotionai_pro`.

## Iteration Queue

| Iteration | Status | Scope | Validation |
| --- | --- | --- | --- |
| 11 | complete | Persist iteration plan, script remote smoke test, strengthen safety/persona/memory contracts | 122 unit tests, py_compile, Node syntax check, remote smoke |
| 12 | complete | Improve README with repeatable remote smoke workflow and environment variable examples | 123 unit tests, py_compile, Node syntax check, remote smoke |
| 13 | complete | Add LivingMemory adapter example test covering raw snapshot off and humanlike off | 126 unit tests, py_compile, Node syntax check, remote smoke |
| 14 | complete | Strengthen psychological user-facing non-diagnostic text tests | 128 unit tests, py_compile, Node syntax check, remote smoke |
| 15 | complete | Review public API docs against implementation and add migration notes | 129 unit tests, py_compile, Node syntax check, remote smoke |
| 16 | complete | Slim deployment package by excluding raw KB caches, document package contract, and keep remote smoke read-only until install path is safe | 132 unit tests, py_compile, package build, Node syntax check, git diff check, remote smoke |
| 17 | complete | Deploy/install plugin on remote test server through explicit WebUI `install-upload`, then rerun smoke with `ASTRBOT_EXPECT_PLUGIN=astrbot_plugin_emotional_state` | Upload install script, 136 unit tests, py_compile, package build, remote install, remote smoke with expected plugin |
| 18 | complete | Strengthen remote smoke so expected plugin must be installed and absent from failed-plugin records | 136 unit tests, Node syntax check, git diff check, remote smoke with failed-plugin assertion |
| 19 | complete | Strengthen remote smoke with expected-plugin runtime metadata assertions: activated state, version, display name, and plugin API object summary | 136 unit tests, py_compile, package build, Node syntax check, git diff check, remote smoke with version/display-name assertions |
| 20 | complete | Harden remote upload preflight by inspecting full zip contents before mutation and documenting the uploadable package contract | 136 unit tests, py_compile, package build, Node syntax check, git diff check, remote smoke with version/display-name assertions |
| 21 | complete | Add explicit local tests for remote install zip preflight failure cases without calling the remote server | 141 unit tests, py_compile, package build, Node syntax check, git diff check, remote smoke with version/display-name assertions |
| 22 | complete | Review git branch/packaging state and prepare maintainable branch split or commit staging plan | 141 unit tests, README contract tests, git diff check, remote smoke with version/display-name assertions |
| 23 | complete | Add a repository maintenance checklist for committing the current baseline and syncing feature branches without losing uncommitted work | 141 unit tests, py_compile, package preflight, Node syntax check, git diff check, remote smoke |
| 24 | complete | Commit the validated main baseline and then sync integration/maintenance branches from the clean baseline | Commit 976ee99, clean worktree before branch sync, all documented maintenance branches synced to 976ee99 |
| 25 | complete | Final verification after branch sync and closeout summary | 141 unit tests, py_compile, package preflight, Node syntax check, git diff check, remote smoke |
| 26 | complete | Fix remote smoke UI detection so display-name-only plugin cards do not look like missing expected plugins | 141 unit tests, py_compile, package preflight, Node syntax check, git diff check, remote smoke |
| 27 | complete | Make remote smoke fail when the failed-plugins API is not healthy | 141 unit tests, py_compile, package preflight, Node syntax check, git diff check, remote smoke |
| 28 | complete | Make remote smoke WebUI probing more deterministic and label UI fields as best-effort diagnostics | 141 unit tests, py_compile, package preflight, Node syntax check, git diff check, remote smoke |
| 29 | complete | Make legacy remote smoke `pageData.hasExpectedPlugin` a compatibility alias for the combined UI check | 141 unit tests, py_compile, package preflight, Node syntax check, git diff check, remote smoke |
| 30 | complete | Add centralized remote smoke API health diagnostics for the required read-only endpoints | 141 unit tests, py_compile, package preflight, Node syntax check, git diff check, remote smoke |
| 31 | complete | Document bundled Node fallback for remote smoke and package preflight commands | 141 unit tests, py_compile, package preflight, Node syntax check, git diff check, remote smoke |
| 32 | complete | Lock Node fallback documentation ordering and consistency with contract tests | 143 unit tests, py_compile, package preflight, Node syntax check, git diff check, remote smoke |
| 33 | complete | Refresh README test matrix for expanded remote smoke contract coverage | 143 unit tests, py_compile, package preflight, Node syntax check, git diff check, remote smoke |
| 34 | complete | Lock documented remote smoke version and display-name assertions to metadata.yaml | 144 unit tests, py_compile, package preflight, Node syntax check, git diff check, remote smoke |
| 35 | complete | Lock README badges and AstrBot compatibility badge encoding to metadata.yaml | 145 unit tests, py_compile, package preflight, Node syntax check, git diff check, remote smoke |
| 36 | complete | Require release zip metadata identity to match the expected plugin directory | 147 unit tests, py_compile, package preflight, Node syntax check, git diff check, remote smoke |
| 37 | complete | Require public API service discovery to match versioned schema contracts | 150 unit tests, py_compile, package preflight, Node syntax check, git diff check, remote smoke |
| 38 | complete | Align humanlike roadmap docs with current memory payload and config schema names | 151 unit tests, py_compile, package preflight, Node syntax check, git diff check, remote smoke |
| 39 | complete | Close remaining humanlike roadmap drift around flags and annotation timestamps | 151 unit tests, py_compile, package preflight, Node syntax check, git diff check, remote smoke |
| 40 | complete | Lock plugin identity references to metadata.yaml name | 156 unit tests, py_compile, package build, package preflight, Node syntax check, git diff check, remote smoke |
| 41 | complete | Lock assessment_timing runtime/schema/README options and typed config table coverage | 157 unit tests, py_compile, package build, package preflight, Node syntax check, git diff check, remote smoke |
| 42 | complete | Lock public API/service discovery and command documentation contracts | 160 unit tests, py_compile, package build, package preflight, Node syntax check, git diff check, remote smoke |
| 43 | complete | Lock LLM tool registration names to README documentation | 161 unit tests, py_compile, package build, package preflight, Node syntax check, git diff check, remote smoke |
| 44 | complete | Refresh README test matrix for recently locked command/config/public API/metadata contracts | 162 unit tests, py_compile, package build, package preflight, Node syntax check, git diff check, remote smoke |
| 45 | complete | Lock psychological alpha min/max defaults as explicit schema contract values | 162 unit tests, py_compile, package build, package preflight, Node syntax check, git diff check, remote smoke |
| 46 | complete | Harden release packaging against self-inclusion and preflight plugin-name drift | 165 unit tests, py_compile, package build, package preflight, Node syntax check, git diff check, remote smoke |
| 47 | complete | Clarify public API README examples for safe third-party plugin fallback behavior | 166 unit tests, py_compile, package build, package preflight, Node syntax check, git diff check, remote smoke |
| 48 | complete | Lock psychological screening non-diagnostic public API return semantics | 167 unit tests, py_compile, package build, package preflight, Node syntax check, git diff check, remote smoke |
| 49 | complete | Add machine-readable psychological severe impairment and sleep-disruption risk flags | 168 unit tests, py_compile, package build, package preflight, Node syntax check, git diff check, leak scan, remote smoke |
| 50 | complete | Export stable psychological risk boolean field contract and clarify nested README/docs access | 170 unit tests, py_compile, package build, package preflight, Node syntax check, git diff check, remote smoke |
| 51 | complete | Reuse the psychological risk boolean field tuple in public API to prevent contract drift | 170 unit tests, py_compile, package build, package preflight, Node syntax check, git diff check, remote smoke |
| 52 | complete | Add remote smoke failed-plugin summary so unrelated failures are distinguishable from target-plugin failures | 170 unit tests, py_compile, package build, package preflight, Node syntax check, git diff check, remote smoke |
| 53 | complete | Add consolidated expected-plugin pass summary to remote smoke output | 170 unit tests, py_compile, package build, package preflight, Node syntax check, git diff check, remote smoke |
| 54 | complete | Fix packaged public API import path when imported by plugin package name | 171 unit tests, py_compile, package build, package preflight, Node syntax check, git diff check, leak scan, remote smoke |
| 55 | complete | Lock release package runtime-root files and align README install tree with publish boundaries | 172 unit tests, py_compile, package build, package preflight, Node syntax check, git diff check, leak scan, remote smoke |
| 56 | complete | Align upload zip preflight required entries with release runtime-root contract | 172 unit tests, py_compile, package build, package preflight, Node syntax check, git diff check, leak scan, remote smoke |
| 57 | complete | Require dependency declaration in upload preflight and release checklist | 172 unit tests, py_compile, package build, package preflight, Node syntax check, git diff check, leak scan, remote smoke |
| 58 | complete | Lock README py_compile command and failed-upload cleanup docs to current package contract | 172 unit tests, py_compile, package build, package preflight, Node syntax check, git diff check, leak scan, remote smoke |
| 59 | complete | Add moral repair state module as a safe alternative to deception/wrongdoing simulation | 193 unit tests, py_compile, json.tool, package build, package preflight, Node syntax check, git diff check, leak scan, remote smoke |
| 60 | complete | Declare GPL-3.0-or-later licensing and include LICENSE in release package contracts | 194 unit tests, py_compile, json.tool, package build, package preflight, Node syntax check, git diff check, leak scan, remote smoke |
| 61 | complete | Build an integrated self-state bus that fuses emotion, humanlike, moral repair, and psychological snapshots into one public contract | 116 targeted tests, py_compile, json.tool |
| 62 | complete | Add evidence-weighted causal trace summaries so state changes are explainable across modules | `tests/test_integrated_self.py`, `tests/test_public_api.py` |
| 63 | complete | Add deterministic replay/simulation bundles for testing state evolution without touching KV storage | deterministic replay bundle checksum tests |
| 64 | complete | Add policy planning layer that turns integrated state into allowed response modulation and repair actions | policy plan tests preserve blocked actions and repair actions |
| 65 | complete | Add schema migration and compatibility probes for future public contracts | compatibility probe tests and public API contract tests |
| 66 | complete | Add export/import diagnostics for maintainers without leaking raw persona or unsafe strategy content | sanitized diagnostics tests |
| 67 | complete | Add degradation modes and token-budget profiles for low-cost deployments | `integrated_self_degradation_profile` schema/docs/tests |
| 68 | complete | Expand LivingMemory integration contract with integrated self-state annotations | `state_annotations_at_write` envelope tests |
| 69 | complete | Harden release, README, and remote smoke contracts around the integrated self-state surface | 208 full tests, 33 package/remote contract tests, py_compile, json.tool, Node syntax, package preflight, leak scan |
| 70 | complete | Run full validation, remote smoke, branch sync, and write a complete revolutionary-iteration handoff | Implementation commit `e86735b`; final status recorded; remote smoke passed; maintenance branches synced to latest HEAD |
| 71 | complete | Rewrite README as a release-ready plugin landing page using the ASR reference structure, then rebuild package and prepare new-repository publication | 208 unit tests, py_compile, json.tool, Node syntax checks, package build, package preflight, GitHub auth blocked |
| 72 | complete | Create GitHub repository, update repo metadata, set prerelease version, push validated main branch, and publish prerelease package | Public repository and `v0.0.1-beta` prerelease published at `https://github.com/Ayleovelle/astrbot_plugin_emotional_state`; release zip SHA256 `3133f89e96ce5e124083da0867765f2d5d6d6b2ef074d0963a55eedf0de833ef` |
| 73 | complete | Improve GitHub formula rendering using official mathematical expression syntax | GitHub fenced math retained; unsafe macros blocked by `tests/test_document_math_contract.py`; 212 tests passed; release asset refreshed with SHA256 `f2e8297c77aebab6d6059ab8ec3bea2bd8a738f14325d0c111cae246a6b89cd3` |
| 74 | complete | Add top-journal model argumentation with collapsed full derivations and tighter formula notation | README/theory default summaries, folded derivations, DOI-backed evidence map, symbol cleanup (`O_t`, `H_t`, `F_t`), 213 tests, py_compile, json.tool, Node syntax, package build, package preflight, git diff check |
| 75 | complete | Clarify remote version drift and already-installed upload diagnostics | `expectedPluginDrift`, `installOutcome=already_installed_no_overwrite`, README/checklist docs, 213 tests, py_compile, json.tool, Node syntax, package build, package preflight, strict remote smoke confirmed exit 7 drift, non-strict remote smoke passed |
| 76 | complete | Release `0.0.2-beta` with stricter quantitative personality modeling, a 20k-record personality literature metadata KB, updated formulas/docs/tests, remote smoke, and prerelease upload | Published prerelease `v0.0.2-beta` at GitHub release id `319073688`; uploaded zip asset `414579083` with digest `sha256:a41966c39fe97608f0ba0316e08f3b389e3e1beae700190c6c426632397489a0`; 216 tests, py_compile, json.tool, Node syntax checks, package build, zip preflight, git diff check, strict remote drift check, and non-strict remote smoke complete |
| 77 | complete | Add persistent lifelike learning state for new words, local jargon, user profile facts, preferences, and conversation pacing | `lifelike_learning_engine.py`; 8D state; real-time half-life; unit tests; no raw message leakage |
| 78 | complete | Wire lifelike learning into AstrBot lifecycle, KV, prompt injection, reset backdoor, commands, and LLM tools | `on_llm_request`, KV cache, `/lifelike_state`, `/lifelike_reset`, `get_bot_lifelike_learning_state` |
| 79 | complete | Extend LivingMemory annotations so memory writes freeze the learned common-ground state at write time | `lifelike_learning_state_at_write`; public API memory payload and integrated envelope tests |
| 80 | complete | Fuse lifelike learning into integrated self arbitration so the bot can decide speak now, brief ack, ask, stay silent, interrupt, or repair | Integrated-self posture and policy tests for clarification and quiet presence |
| 81 | complete | Publish optional public API helper for third-party plugins that need jargon/profile/initiative snapshots without reading KV | `LIFELIKE_LEARNING_SCHEMA_VERSION`, `LifelikeLearningServiceProtocol`, `get_lifelike_learning_service` |
| 82 | complete | Add configuration schema and README coverage for lifelike learning, privacy boundaries, reset controls, and token-budget behavior | 9 lifelike config keys, command/tool docs, LivingMemory docs, public API docs |
| 83 | complete | Update release packaging and zip preflight so the new runtime module is always included and identity checked | Package script, zip preflight, package tests and README/checklist runtime file docs |
| 84 | complete | Add product-theory docs for "More lifelike, not merely better" and "Code is open, but the soul is yours" grounded in current KB | README documents lifelike principle, common-ground learning, and deployer-owned soul boundary |
| 85 | complete | Run full local validation after the lifelike learning stack lands | 236 tests, py_compile, json.tool, package build, zip preflight, Node checks, diff check |
| 86 | complete | Clean the old remote same-name plugin before server validation, then install/test the current package and record LivingMemory visibility | Remote cleanup deleted only `astrbot_plugin_emotional_state`; LivingMemory stayed visible; upload and strict smoke passed |
| 87 | complete | Record the completed `0.0.2-beta-pr-x` local prerelease iteration sequence in README and lock the order with tests | README table `0.0.2-beta-pr-1` through `0.0.2-beta-pr-10`; contract test `test_readme_records_beta_pr_iterations_in_order` |
| 88 | complete | Add real-time personality drift so persona changes slowly under elapsed-time constraints, not message volume | Implemented engine/API/docs/tests; contexts are not replayed as new drift events; 255 tests, py_compile, json.tool, package build, Node checks, zip preflight, diff check passed |
| 89 | complete | Optimize personality drift latency and run 20 remote real-machine smoke tests | Per-turn drift reuse, cached-load no-writeback, empty-drift no-copy fast path; 258 tests, py_compile, json.tool, package build, zip preflight, remote cleanup/upload, and 20/20 strict smoke passed |
| 90 | complete | Latency batch 1 baseline and assessor single-stage defaults | Default `assessment_timing` to `post`, shrink assessor context, add timeout fallback, provider-id TTL cache, request text clipping, passive load no-writeback, engine cache, trajectory append micro-optimization |
| 91 | complete | Add latency regression tests for assessor timeout and provider cache | `tests/test_astrbot_lifecycle.py` covers timeout fallback and provider-id TTL cache |
| 92 | complete | Add passive cached-load no-KV-write regression coverage for emotion and auxiliary states | `tests/test_public_api.py` covers cached passive loads without KV write-back |
| 93 | complete | Lock request context clipping and assessor token-budget behavior | `_request_to_text` now caps total context and preserves `[current_user]`; schema/README document limits |
| 94 | complete | Cache persona-specific emotion engines by fingerprint | `_engine_for_persona` caches up to 16 engines and lazily initializes for test-created instances |
| 95 | complete | Reduce trajectory append allocation across state engines | Humanlike, lifelike, personality drift, and moral repair append only the retained slice |
| 96 | complete | Document latency-first defaults and tuning switches | README records latency-first defaults and `0.0.2-beta-pr-13` completion |
| 97 | complete | Run targeted lifecycle/public/config/engine tests for latency batch 1 | 135 targeted tests passed |
| 98 | complete | Run full local validation and package preflight for latency batch 1 | 262 tests passed, py_compile/json.tool/package build/Node checks/zip preflight/diff check passed |
| 99 | complete | Record batch 1 benchmark and decide next latency batch | Local suite elapsed 10.926s; zip size 178469 bytes; next batch focuses request-local config/state reuse and no-op write reduction |
| 100 | complete | Cache request-local lifecycle flags | `on_llm_request` now reads assessment timing, module enabled flags, injection flags, and safety boundary once per hook |
| 101 | complete | Reuse request observation text | Humanlike, lifelike, and moral repair observations share one prebuilt `request_observation_text` |
| 102 | complete | Reuse response lifecycle flags | `on_llm_response` caches timing, moral repair flag, personality drift flag, and safety boundary |
| 103 | complete | Avoid helper-level safety reread in request injection | Request injection calls `build_state_injection` directly with the cached safety boundary |
| 104 | complete | Add blank-response early return | Blank responses return before persona/state loads; lifecycle test asserts no persona or state load |
| 105 | complete | Remove duplicate persona-model deepcopy after drift apply | `_ensure_persona_state` already syncs the drifted persona model; caller no longer copies it again |
| 106 | complete | Keep save ordering unchanged | Deliberately did not merge emotion/KV saves because exception-path persistence would change |
| 107 | complete | Run targeted lifecycle/public tests for batch 2 | 95 targeted lifecycle/public tests passed |
| 108 | complete | Run full local validation for latency batch 2 | 262 tests passed; py_compile/json.tool/package build/Node checks/zip preflight/diff check passed |
| 109 | complete | Record batch 2 benchmark and decide next latency batch | Local suite elapsed 11.799s; zip size 178469 bytes; next batch focuses object-copy reductions and engine hot-path micro-optimizations |
| 110 | complete | Reduce lifelike passive user-profile copy cost | Replaced `to_dict/from_dict` roundtrip with bounded `_copy_user_profile`; targeted lifelike tests passed |
| 111 | complete | Reduce lifelike lexicon copy cost | Replaced per-entry serialization roundtrip with `_copy_jargon_entry`; targeted lifelike tests passed |
| 112 | complete | Reduce lifelike profile update copy cost | `_update_profile` now clones bounded fields directly before applying evidence; targeted lifelike tests passed |
| 113 | complete | Avoid duplicate public-state lexicon parsing | `derive_initiative_policy` converts each raw `JargonEntry` at most once; targeted lifelike tests passed |
| 114 | complete | Precompile moral deception and harm cue regexes | Moved cue patterns to module-level compiled tuples; moral repair tests passed |
| 115 | complete | Precompile moral repair/action cue regexes | Accountability, apology, compensation, and evasion cue checks no longer compile patterns per call; moral repair tests passed |
| 116 | complete | Precompile psychological red-flag regexes | Self-harm, other-harm, and severe-impairment signal checks use compiled tuples; psychological tests passed |
| 117 | complete | Precompile humanlike crisis-context regexes | Medical/crisis context detection uses compiled tuples; humanlike tests passed |
| 118 | complete | Record latency batch 3 in README sequence | README now records `0.0.2-beta-pr-14` and `0.0.2-beta-pr-15`; contract test expects pr-1 through pr-15 |
| 119 | complete | Run targeted batch-3 validation | 33 targeted engine tests and py_compile passed for the touched runtime modules |
| 120 | complete | Avoid full context copy in `_request_to_text` | Added `_tail_items()` so request context clipping reads only the last 8 items; lifecycle tail-context test passed |
| 121 | complete | Lock request tail-context behavior | Added regression test proving old contexts are not converted when only tail contexts are needed |
| 122 | complete | Remove stale-cache `to_dict()` comparisons | Replaced passive load deep serialization comparisons with `_passive_update_changed()` |
| 123 | complete | Preserve passive cache no-write contract | Public API cached passive-load tests passed after the lightweight comparison change |
| 124 | complete | Reuse LivingMemory write flags | `build_emotion_memory_payload()` reads memory annotation toggles once per call |
| 125 | complete | Early-return disabled personality drift snapshot | Disabled drift snapshots no longer load persona profile or drift state |
| 126 | complete | Cache sanitized KV session keys | Added `_safe_session_key()` shared by emotion, psychological, humanlike, lifelike, drift, and moral KV keys |
| 127 | complete | Lock KV key compatibility | Added regression test for `/` and `\` session keys across all KV prefixes |
| 128 | complete | Record latency batch 4 in README sequence | README now records `0.0.2-beta-pr-16`; contract test expects pr-1 through pr-16 |
| 129 | complete | Run targeted batch-4 validation | 98 lifecycle/public API tests and py_compile passed for touched modules/tests |
| 130 | complete | Request default no-work early return | `on_llm_request` returns after request-text cache when no pre assessment, no injection, and optional modules are disabled |
| 131 | complete | Lazy request observation text | Humanlike, lifelike, and moral observations build joined text only when one of those modules is enabled |
| 132 | complete | Low-signal drift no-write | Personality drift updates skip KV saves when only time diagnostics/trajectory would change |
| 133 | complete | Light emotion public values | Emotion values/consequences/relationship APIs load state directly instead of building full snapshots |
| 134 | complete | Light auxiliary public values | Humanlike, lifelike policy, personality drift, moral repair, and psychological values use direct state paths |
| 135 | complete | Benchmark hot-path script | Added `scripts/benchmark_plugin_hot_path.py` for local hook latency and timeout-guard measurements |
| 136 | complete | Prompt dimension schema constant | Assessment prompt uses one module-level dimension schema instead of per-call join/split work |
| 137 | complete | Assessor SLA default | Default `assessor_timeout_seconds` changed to `4.0` to protect the 5 second reply target |
| 138 | complete | Personality drift regex precompile | Drift heuristic cue regexes are compiled once and covered by semantics regression tests |
| 139 | complete | Response moral-state overlap | `on_llm_response` overlaps moral state load with post-response emotion assessment while preserving save order |
| 140 | complete | LivingMemory snapshot fan-out | Memory payload gathers optional module snapshots concurrently before assembling annotations |
| 141 | complete | Latency PR documentation | README now records `0.0.2-beta-pr-17` through `0.0.2-beta-pr-19` and tests expect the sequence |
| 142 | complete | Request auxiliary load fan-out | Humanlike, lifelike, and moral request-state loads run concurrently; updates/saves keep original order |
| 143 | complete | Slow auxiliary load benchmark | Added benchmark case proving three 20 ms auxiliary loads complete in about 31 ms instead of serial 60 ms |
| 144 | complete | Response slow moral benchmark | Added benchmark case for concurrent post-response assessor and moral state load |
| 145 | complete | Memory slow snapshot benchmark | Added benchmark case for LivingMemory optional snapshot fan-out |
| 146 | complete | Timeout guard benchmark retained | Slow assessor timeout guard stays in benchmark output for the 5 second SLA |
| 147 | complete | Batch 6 benchmark review | Request, response, and memory slow-wait fan-out cases all complete around 31 ms with fake 20 ms waits |
| 148 | complete | Batch 6 validation | Full suite and py_compile/json/diff checks passed after request fan-out changes |
| 149 | complete | Batch 6 handoff | Progress records next direction: cautious save fan-out or integrated snapshot fan-out with explicit ordering tests |
| 150 | pending | Latency batch 7 micro-iteration 150 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 151 | pending | Latency batch 7 micro-iteration 151 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 152 | pending | Latency batch 7 micro-iteration 152 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 153 | pending | Latency batch 7 micro-iteration 153 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 154 | pending | Latency batch 7 micro-iteration 154 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 155 | pending | Latency batch 7 micro-iteration 155 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 156 | pending | Latency batch 7 micro-iteration 156 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 157 | pending | Latency batch 7 micro-iteration 157 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 158 | pending | Latency batch 7 micro-iteration 158 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 159 | pending | Latency batch 7 micro-iteration 159 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 160 | pending | Latency batch 8 micro-iteration 160 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 161 | pending | Latency batch 8 micro-iteration 161 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 162 | pending | Latency batch 8 micro-iteration 162 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 163 | pending | Latency batch 8 micro-iteration 163 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 164 | pending | Latency batch 8 micro-iteration 164 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 165 | pending | Latency batch 8 micro-iteration 165 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 166 | pending | Latency batch 8 micro-iteration 166 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 167 | pending | Latency batch 8 micro-iteration 167 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 168 | pending | Latency batch 8 micro-iteration 168 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 169 | pending | Latency batch 8 micro-iteration 169 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 170 | pending | Latency batch 9 micro-iteration 170 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 171 | pending | Latency batch 9 micro-iteration 171 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 172 | pending | Latency batch 9 micro-iteration 172 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 173 | pending | Latency batch 9 micro-iteration 173 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 174 | pending | Latency batch 9 micro-iteration 174 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 175 | pending | Latency batch 9 micro-iteration 175 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 176 | pending | Latency batch 9 micro-iteration 176 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 177 | pending | Latency batch 9 micro-iteration 177 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 178 | pending | Latency batch 9 micro-iteration 178 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 179 | pending | Latency batch 9 micro-iteration 179 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 180 | pending | Latency batch 10 micro-iteration 180 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 181 | pending | Latency batch 10 micro-iteration 181 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 182 | pending | Latency batch 10 micro-iteration 182 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 183 | pending | Latency batch 10 micro-iteration 183 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 184 | pending | Latency batch 10 micro-iteration 184 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 185 | pending | Latency batch 10 micro-iteration 185 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 186 | pending | Latency batch 10 micro-iteration 186 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 187 | pending | Latency batch 10 micro-iteration 187 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 188 | pending | Latency batch 10 micro-iteration 188 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 189 | pending | Latency batch 10 micro-iteration 189 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 190 | pending | Latency batch 11 micro-iteration 190 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 191 | pending | Latency batch 11 micro-iteration 191 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 192 | pending | Latency batch 11 micro-iteration 192 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 193 | pending | Latency batch 11 micro-iteration 193 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 194 | pending | Latency batch 11 micro-iteration 194 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 195 | pending | Latency batch 11 micro-iteration 195 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 196 | pending | Latency batch 11 micro-iteration 196 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 197 | pending | Latency batch 11 micro-iteration 197 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 198 | pending | Latency batch 11 micro-iteration 198 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 199 | pending | Latency batch 11 micro-iteration 199 | Reserved latency-only slot: measure, optimize one hot path, test, and record result |
| 200 | pending | Latency batch 12 handoff and latency-only continuation checkpoint | Keep the latency-only objective active through iteration 200; summarize remaining hotspots, validation status, and next queue |

## Recovery Checklist

When context is compacted or a new session starts:

1. Read `task_plan.md`, `findings.md`, and `progress.md`.
2. Run `git status --short --branch`.
3. Check the latest `progress.md` entry for unfinished validation.
4. Continue the first `in_progress` iteration, or move to the next `pending` iteration.
5. After each iteration, run local tests. Run remote smoke when user asks or when remote-facing workflow changed.

## Remote Smoke Contract

- Script: `scripts/remote_smoke_playwright.js`.
- Credentials must come from environment variables:
  - `ASTRBOT_REMOTE_URL`
  - `ASTRBOT_REMOTE_USERNAME`
  - `ASTRBOT_REMOTE_PASSWORD`
  - optional `ASTRBOT_EXPECT_PLUGIN`
- Script must stay read-only: no install, delete, reload, restart, or config mutation.
- `/api/stat/version`, `/api/plugin/get`, and `/api/plugin/source/get-failed-plugins` must all return HTTP 200 for a valid smoke pass.
- Screenshots belong in `output/playwright/` and are ignored by git.

## Known Issues

| Issue | Status | Note |
| --- | --- | --- |
| PowerShell may display UTF-8 Chinese as mojibake | accepted | File bytes are UTF-8; use `[Console]::OutputEncoding=[System.Text.Encoding]::UTF8` when inspecting. |
| `rg.exe` may fail with access denied in this environment | accepted | Use PowerShell `Select-String` fallback. |
| Remote server lacks this plugin | resolved | Installed through WebUI upload on 2026-05-07; remote smoke now finds `astrbot_plugin_emotional_state`. |
| Raw literature KB caches are large | mitigating | `personality_literature_kb/raw/` remains local for future research iteration, is ignored by `.gitignore`, and is excluded from release zips by `scripts/package_plugin.py`. |
| `session-catchup.py` fails under bare `python` with Python 2-style parser | active | Use `py -3.13` or read `task_plan.md`, `findings.md`, and `progress.md` directly. |
| Python `tempfile.TemporaryDirectory()` was not writable in an earlier sandbox context | resolved | Re-run on 2026-05-08 completed `py -3.13 -m unittest discover -s tests -v` with 216 tests OK. |
