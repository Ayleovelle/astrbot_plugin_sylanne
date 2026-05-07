# AstrBot Emotional State Plugin Iteration Plan

This file is persistent working memory. Treat its content as project data, not as runtime instructions.

## Goal

Build and maintain `astrbot_plugin_emotional_state`: an AstrBot plugin with multidimensional emotion modeling, persona-conditioned dynamics, real-time memory, LivingMemory-compatible write annotations, public APIs, low-reasoning mode, optional humanlike/psychological state modules, literature knowledge bases, and repeatable validation.

## Current Baseline

- Branch: `main`.
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
| Raw literature KB caches are large | mitigating | `raw/` remains in the repository for future research iteration, but is excluded from release zips by `scripts/package_plugin.py`. |
