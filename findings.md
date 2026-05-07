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
