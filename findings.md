# Findings

This file stores durable discoveries from implementation, review, and remote testing.

## 2026-05-07 Remote Dashboard

- Root HTTP endpoint returned `200` and served `AstrBot - 仪表盘`.
- Browser login succeeded through the UI and reached `#/dashboard/default`.
- AstrBot reported `version=4.24.2` and `dashboard_version=v4.24.2`.
- Installed plugin API returned 29 plugins.
- Failed plugin API returned `{}`.
- `astrbot_plugin_emotional_state` was not present on the remote server.
- `astrbot_plugin_livingmemory` was present, useful for later compatibility tests after deployment.
- A direct API login attempt from a subagent failed because the API call shape likely did not match the UI login request; browser UI flow is the accepted remote-smoke source of truth.

## 2026-05-07 Remote Install Upload

- AstrBot WebUI upload route was confirmed from upstream source as `POST /api/plugin/install-upload`.
- Multipart field name is `file`; optional form field is `ignore_version_check`.
- The remote upload installer requires the zip to start with an explicit plugin directory entry. A zip whose first entry is `astrbot_plugin_emotional_state/README.md` can fail with `NotADirectoryError`.
- `scripts/package_plugin.py` now writes `astrbot_plugin_emotional_state/` as the first zip entry.
- First fixed upload installed `astrbot_plugin_emotional_state` successfully on the remote server.
- Re-uploading an already installed plugin returns an error message that the directory already exists and can leave a `plugin_upload_astrbot_plugin_emotional_state` failed-plugin record.
- `scripts/remote_install_upload_playwright.js` treats the already-installed case as idempotent success when the target plugin is present, and cleans only the matching failed upload record.
- Final remote smoke with `ASTRBOT_EXPECT_PLUGIN=astrbot_plugin_emotional_state` passed:
  - plugin API count: 30,
  - target plugin present,
  - failed plugin data: `{}`,
  - LivingMemory present.
- Remote runtime metadata for `astrbot_plugin_emotional_state` from `/api/plugin/get`:
  - `activated=true`,
  - `version=1.0.0`,
  - `display_name=多维情绪状态`,
  - `author=pidan`,
  - `astrbot_version=>=4.9.2,<5.0.0`.
- `scripts/remote_smoke_playwright.js` now exposes `expectedPluginRuntime` and can hard-fail on inactive target plugins, version mismatch, or display-name mismatch without mutating the remote server.
- `scripts/remote_install_upload_playwright.js` now inspects the zip central directory before any upload mutation:
  - all entries must stay under the plugin root directory,
  - entries must be relative POSIX paths,
  - parent traversal is rejected,
  - required runtime files must be present,
  - `tests/`, `scripts/`, `output/`, `dist/`, `raw/`, `__pycache__/`, and `.git/` are rejected.
- Zip preflight logic lives in `scripts/plugin_zip_preflight.js` and is exercised locally by `tests/test_package_plugin.py` with valid and invalid temporary zip archives. This gives failure-path coverage without mutating the remote server.
- Remote WebUI may display a plugin's `display_name` instead of its package directory name. `scripts/remote_smoke_playwright.js` now reports `pageData.hasExpectedPluginId`, `pageData.hasExpectedPluginDisplayName`, and `pageData.hasExpectedPluginInUi` so UI card checks do not contradict the API-level plugin detection.
- `scripts/remote_smoke_playwright.js` now treats `/api/plugin/source/get-failed-plugins` as a required health endpoint. Non-200 responses set exit code `9`, because otherwise `expectedFailedPlugin=null` could falsely imply there are no failed plugin records.
- The WebUI plugin list is an asynchronous, best-effort diagnostic layer in remote smoke. The authoritative checks remain `/api/stat/version`, `/api/plugin/get`, `/api/plugin/source/get-failed-plugins`, `containsExpectedPlugin`, `expectedPluginRuntime`, and `expectedFailedPlugin`.
- `scripts/remote_smoke_playwright.js` now waits for extension-page readiness by looking for expected plugin id/displayName text, `.extension-title-row`, extension-like nodes, or plugin-like nodes. If this probe times out, it records `pageData.uiProbeStatus="best_effort_timeout"` without weakening API-level hard assertions.
- Latest remote smoke after the UI probe change returned `pageData.uiProbeStatus="ready"`, `selectorCounts.extensionTitleRows=30`, `hasExpectedPluginDisplayName=true`, and `hasExpectedPluginInUi=true`; this confirms the plugin is visible in the rendered WebUI under its display name while API checks remain the source of truth.
- Legacy `pageData.hasExpectedPlugin` should be read as a compatibility alias for `pageData.hasExpectedPluginInUi`, not as an ID-only check. Consumers that need the package directory text specifically should read `pageData.hasExpectedPluginId`.
- Remote smoke now reports `apiHealth.statVersion`, `apiHealth.pluginGet`, and `apiHealth.failedPlugins` so endpoint status failures are visible in one place before reading the plugin summary or UI probe diagnostics.
- In this Windows workspace, bare `node` may fail with access denied, while Codex bundled Node works. README and the release checklist now define `$node` with a Codex bundled Node fallback and set `NODE_PATH` for Playwright-dependent scripts.
- Contract tests now require the README and release checklist to share the same three-line `$node` fallback snippet and define it before the first documented Node/Playwright command.
- README's test coverage matrix now reflects the expanded remote smoke contract: credentials by environment, read-only behavior, ignored screenshots, API health summary, UI best-effort diagnostics, upload-script boundaries, and bundled Node documentation.
- Remote smoke documentation now has contract coverage tying `ASTRBOT_EXPECT_PLUGIN_VERSION` and `ASTRBOT_EXPECT_PLUGIN_DISPLAY_NAME` examples to `metadata.yaml` `version` and `display_name`, preventing release docs from drifting when metadata changes.
- README badge documentation now has contract coverage tying the visible plugin version badge and `astrbot_version` compatibility badge to `metadata.yaml`. Shields badge URLs must encode `>`, `=`, `<`, and `,` as `%3E`, `%3D`, `%3C`, and `%2C`.
- Upload zip preflight should validate identity at three levels: filename, explicit root directory, and zip-internal `metadata.yaml` `name:`. A package whose `metadata.yaml` names a different plugin must fail locally before `remote_install_upload_playwright.js` can call AstrBot's install-upload endpoint.
- Public service discovery should reject objects that only mimic the method surface but advertise old or missing public API/schema versions. Other plugins should use `get_emotion_service(...)` and `get_humanlike_service(...)` so method completeness and schema compatibility are checked together.
- The current LivingMemory-compatible humanlike memory annotation name is `humanlike_state_at_write`, not the earlier roadmap placeholder `humanlike_at_write`. `humanlike_memory_write_enabled` defaults to `true`; early fields such as `humanlike_personification_level` and `humanlike_dependency_guard_level` remain non-schema ideas unless later implemented with docs and tests.
- Humanlike public snapshots use `flags`, not `simulation_flags`. Humanlike memory annotations expose the source state timestamp as `humanlike_updated_at`; `updated_at` remains a snapshot/state field, not an annotation field.
- Plugin identity has multiple externally visible surfaces: `metadata.yaml name`, `main.PLUGIN_NAME`, `public_api.PLUGIN_NAME`, `scripts/package_plugin.py` `PLUGIN_NAME`, release zip root, README install/smoke commands, and release checklist commands. These should be tested together so future renames cannot split package identity from remote validation commands.
- `assessment_timing` is a three-surface contract: runtime accepted values in `main.py`, schema `options`, and README configuration text must stay aligned. Otherwise a documented value can silently fall back to `both`.
- README typed configuration tables are the maintainers' practical source of truth for new config keys. Schema keys should appear there with the same type unless they are explicitly legacy compatibility fields.

## 2026-05-07 Branch Maintenance

- Existing feature branches are present:
  - `codex/complete-emotional-bot-plugin`,
  - `codex/emotion-core`,
  - `codex/astrbot-integration`,
  - `codex/public-api-memory`,
  - `codex/psychological-screening`,
  - `codex/literature-kbs`,
  - `codex/humanlike-agent-roadmap`,
  - `codex/tests-validation`,
  - `codex/docs-config`.
- Most feature branches point to the early baseline commit `e640a36`; `codex/humanlike-agent-roadmap` points to `9a59dd8`; `main` points to `4010a12` plus current uncommitted Iteration 11-22 changes.
- Added `codex/release-packaging` to the documented strategy as a maintenance branch for release zips, upload preflight, remote install scripts, and remote smoke contracts.
- Do not reset or move feature branches from the current dirty working tree. Recommended order is: finish validation on `main`, commit the complete baseline, then sync `codex/complete-emotional-bot-plugin` and feature branches from a clean state.
- Main baseline commit `976ee99` was created after validation.
- Maintenance branches were synced to `976ee99` from a clean worktree:
  - `codex/complete-emotional-bot-plugin`,
  - `codex/emotion-core`,
  - `codex/astrbot-integration`,
  - `codex/public-api-memory`,
  - `codex/psychological-screening`,
  - `codex/literature-kbs`,
  - `codex/humanlike-agent-roadmap`,
  - `codex/tests-validation`,
  - `codex/release-packaging`,
  - `codex/docs-config`.
- Maintenance branches were later synced to `b2bddf3` after the branch-sync status commit.
- Final Iteration 25 validation passed after branch sync; after committing the final status entry, branches should be synced one last time to the final HEAD.

## 2026-05-07 Review Findings

- `build_emotion_memory_payload` used a shallow copy of `snapshot`; nested relationship/consequence/appraisal fields could be mutated after payload creation. Fixed by deep-copying the snapshot before freezing memory payload fields.
- `main.get_emotional_state_plugin` previously accepted any object with `get_emotion_snapshot`; it now checks the same core public API surface expected by other plugin integrations.
- Safety boundary behavior was tested at prompt helper level, but not through public plugin methods. Added public-entry tests.
- Full assessment prompt retained `他/她`; added a contract test so future prompt edits do not regress to one fixed pronoun.

## Tooling Notes

- `npx` is not available in the local PATH.
- Bundled Node path used for Playwright API:
  `C:\Users\pidan\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe`
- Bundled Node modules path:
  `C:\Users\pidan\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules`
- Local Edge executable exists at:
  `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`
