# Progress

## 2026-05-07 Iteration 11

- Created persistent planning files: `task_plan.md`, `findings.md`, `progress.md`.
- Added `.gitignore` so browser screenshots and Python cache files do not become accidental commits.
- Added `scripts/remote_smoke_playwright.js` for repeatable, read-only remote dashboard smoke tests.
- Hardened `build_emotion_memory_payload` with deep copy semantics.
- Hardened `main.get_emotional_state_plugin` to require the full core emotion service API.
- Added unit tests for:
  - nested memory payload freeze behavior,
  - `他/她` prompt contract,
  - safety boundary config through emotion and humanlike public prompt fragments,
  - main helper public API contract.

Validation complete:

- `py -3.13 -m unittest discover -s tests -v`: 122 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts/build_literature_kb.py scripts/build_humanlike_agent_literature_kb.py scripts/build_psychological_literature_kb.py`: passed.
- Bundled Node `--check scripts/remote_smoke_playwright.js`: passed.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke via bundled Node and Playwright: passed.
  - Login succeeded.
  - Extension route loaded.
  - AstrBot version `4.24.2`.
  - Plugin API returned 29 plugins.
  - Failed plugins data was `{}`.
  - `astrbot_plugin_emotional_state` is still not installed on the remote server.

Next iteration:

- Iteration 12 starts with README documentation for repeatable remote smoke testing and recovery workflow.

## 2026-05-07 Iteration 12

- Documented remote read-only smoke testing in README.
- Documented persistent iteration files and context-recovery flow in README.
- Added README contract coverage to `tests/test_remote_smoke_contract.py`.

Validation complete:

- `py -3.13 -m unittest discover -s tests -v`: 123 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts/build_literature_kb.py scripts/build_humanlike_agent_literature_kb.py scripts/build_psychological_literature_kb.py`: passed.
- Bundled Node `--check scripts/remote_smoke_playwright.js`: passed.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke via bundled Node and Playwright: passed.
  - Login succeeded.
  - Extension route loaded.
  - AstrBot version `4.24.2`.
  - Plugin API returned 29 plugins.
  - Failed plugins data was `{}`.

Next iteration:

- Iteration 13 adds a LivingMemory-shaped compatibility test for raw snapshot off, humanlike annotation off, and memory text fallback.

## 2026-05-07 Iteration 13

- Added LivingMemory-shaped compatibility coverage in `tests/test_public_api.py`.
- Covered `include_raw_snapshot=False` while preserving `emotion_at_write`.
- Covered `humanlike_memory_write_enabled=False` without weakening the main emotion memory payload.
- Covered `memory_text` fallback and explicit override precedence.

Validation complete:

- `py -3.13 -m unittest discover -s tests -v`: 126 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts/build_literature_kb.py scripts/build_humanlike_agent_literature_kb.py scripts/build_psychological_literature_kb.py`: passed.
- Bundled Node `--check scripts/remote_smoke_playwright.js`: passed.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke via bundled Node and Playwright: passed.

Next iteration:

- Iteration 14 strengthens non-diagnostic psychological user-facing output tests.

## 2026-05-07 Iteration 14

- Added tests for user-facing psychological screening text.
- Locked the non-diagnostic wording, professional-evaluation boundary, human-review language, and crisis support wording.
- Added negative assertions against diagnosis/treatment-style wording.

Validation complete:

- `py -3.13 -m unittest discover -s tests -v`: 128 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts/build_literature_kb.py scripts/build_humanlike_agent_literature_kb.py scripts/build_psychological_literature_kb.py`: passed.
- Bundled Node `--check scripts/remote_smoke_playwright.js`: passed.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke via bundled Node and Playwright: passed.

Next iteration:

- Iteration 15 reviews README/public API documentation against implementation and adds migration notes if needed.

## 2026-05-07 Iteration 15

- Added README guidance recommending `public_api.get_emotion_service(...)` and `get_humanlike_service(...)` for method-complete service discovery.
- Added a README/API contract test that checks `public_api.py` protocol methods are documented.

Validation complete:

- `py -3.13 -m unittest discover -s tests -v`: 129 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts/build_literature_kb.py scripts/build_humanlike_agent_literature_kb.py scripts/build_psychological_literature_kb.py`: passed.
- Bundled Node `--check scripts/remote_smoke_playwright.js`: passed.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke via bundled Node and Playwright: passed.
  - Login succeeded.
  - Extension route loaded.
  - AstrBot version `4.24.2`.
  - Plugin API returned 29 plugins.
  - Failed plugins data was `{}`.

Current blocker for remote plugin-runtime validation:

- Remote server still does not have `astrbot_plugin_emotional_state` installed. Next remote validation with `ASTRBOT_EXPECT_PLUGIN=astrbot_plugin_emotional_state` should happen after deployment.

## 2026-05-07 Remote Smoke Before Iteration 16

- Ran `scripts\remote_smoke_playwright.js` with credentials supplied through environment variables only.
- Result: remote dashboard login passed, extension page loaded, AstrBot version was `4.24.2`.
- Plugin API returned 29 plugins, failed plugin data was `{}`.
- `astrbot_plugin_livingmemory` was present.
- `astrbot_plugin_emotional_state` was still not installed on the remote server, so runtime plugin validation remains blocked until a safe install path is used.

## 2026-05-07 Iteration 16

Status: complete.

- Started from context recovery using `task_plan.md`, `findings.md`, `progress.md`, `git status`, and session catchup.
- Subagent read-only review recommended package slimming before remote install because the current release zip included large raw literature caches.
- Updated `scripts/package_plugin.py` so `raw/` KB build caches stay in the repository but are excluded from release zips.
- Expanded `tests/test_package_plugin.py` to verify:
  - release zip paths are rooted under `astrbot_plugin_emotional_state/`,
  - paths are relative POSIX zip paths,
  - runtime docs and finished KB artifacts remain included,
  - raw caches, tests, scripts, output, local planning files, and git metadata stay excluded,
  - release zip size remains below a remote-upload-friendly upper bound.
- Updated README to document release packaging and the difference between finished KB artifacts and `raw/` research cache files.
- Updated remote smoke README contract tests to require the packaging docs and the "after remote install" expected-plugin wording.

Validation complete:

- `py -3.13 -m unittest tests.test_package_plugin tests.test_remote_smoke_contract -v`: 8 tests passed.
- `py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip`: passed; generated zip size was 10,128,064 bytes.
- `py -3.13 -m unittest discover -s tests -v`: 132 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check scripts\remote_smoke_playwright.js`: passed.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke via bundled Node and Playwright: passed.
  - Login succeeded.
  - Extension route loaded.
  - AstrBot version `4.24.2`.
  - Plugin API returned 29 plugins.
  - Failed plugin data was `{}`.
  - `astrbot_plugin_livingmemory` was present.

## 2026-05-07 Iteration 18

Status: complete.

- Strengthened `scripts\remote_smoke_playwright.js` so `ASTRBOT_EXPECT_PLUGIN` now checks two conditions:
  - target plugin appears in `/api/plugin/get`,
  - target plugin is not present in `/api/plugin/source/get-failed-plugins`.
- Added contract coverage requiring `expectedFailedPlugin` handling and exit code `5` for expected-plugin failed-load detection.

Validation complete:

- `py -3.13 -m unittest tests.test_remote_smoke_contract -v`: 8 tests passed.
- Bundled Node `--check scripts\remote_smoke_playwright.js`: passed.
- `py -3.13 -m unittest discover -s tests -v`: 136 tests passed.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with `ASTRBOT_EXPECT_PLUGIN=astrbot_plugin_emotional_state`: passed.
  - Plugin API returned 30 plugins.
  - Target plugin was present.
  - `expectedFailedPlugin` was `null`.
  - Failed plugin data was `{}`.
  - `astrbot_plugin_emotional_state` was installed and loadable on the remote server.

Next iteration:

- Iteration 17 is remote install/runtime validation after a safe authorized install path is available.

## 2026-05-07 Iteration 17

Status: complete.

- Started remote install/runtime validation after Iteration 16 produced a smaller release zip.
- Initial browser inspection loaded the installed-plugin page without mutations and captured plugin API requests: /api/plugin/get, /api/plugin/source/get-failed-plugins, /api/plugin/source/get, /api/plugin/market_list.
- Official AstrBot route inspection found POST /api/plugin/install-upload with multipart field file and optional ignore_version_check.
- First remote upload attempt failed because the generated zip lacked an explicit first directory entry; AstrBot's upload installer interpreted `astrbot_plugin_emotional_state/README.md` as the update root and raised `NotADirectoryError`.
- Updated `scripts/package_plugin.py` to write `astrbot_plugin_emotional_state/` as the first zip entry.
- Added `tests/test_package_plugin.py` coverage for the explicit first directory entry.
- Rebuilt `dist\astrbot_plugin_emotional_state.zip`; generated zip size was 10,128,541 bytes.
- Remote upload install then succeeded and `astrbot_plugin_emotional_state` appeared in `/api/plugin/get`.
- Added `scripts/remote_install_upload_playwright.js` as a separate explicit install script:
  - requires `ASTRBOT_REMOTE_URL`, `ASTRBOT_REMOTE_USERNAME`, `ASTRBOT_REMOTE_PASSWORD`,
  - requires `ASTRBOT_REMOTE_INSTALL_ZIP`,
  - requires `ASTRBOT_EXPECT_PLUGIN`,
  - requires `ASTRBOT_REMOTE_INSTALL_CONFIRM=1`,
  - checks zip size and first zip entry before upload,
  - only calls `install-upload`, plus `uninstall-failed` only to clean the matching already-installed failed upload record.
- Updated README with the explicit remote install workflow and kept `remote_smoke_playwright.js` read-only.
- Added remote install contract tests for confirmation, no hardcoded credentials/IP, no persisted sessions, and endpoint allowlist.

Validation complete:

- `py -3.13 -m unittest tests.test_package_plugin tests.test_remote_smoke_contract -v`: 12 tests passed after install-script contract additions.
- Bundled Node `--check scripts\remote_smoke_playwright.js`: passed.
- Bundled Node `--check scripts\remote_install_upload_playwright.js`: passed.
- `py -3.13 -m unittest discover -s tests -v`: 136 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- `git diff --check`: passed, with CRLF conversion warnings only.
- `scripts\remote_install_upload_playwright.js`: passed against the test server; repeated upload was treated as idempotent already-installed success and cleaned the matching failed upload record.
- `scripts\remote_smoke_playwright.js` with `ASTRBOT_EXPECT_PLUGIN=astrbot_plugin_emotional_state`: passed.
  - Login succeeded.
  - Extension route loaded.
  - AstrBot version `4.24.2`.
  - Plugin API returned 30 plugins.
  - `astrbot_plugin_emotional_state` was present.
  - Failed plugin data was `{}`.
  - `astrbot_plugin_livingmemory` was present.

- Official AstrBot route inspection found POST /api/plugin/install-upload with multipart field file and optional ignore_version_check.

- First remote upload attempt failed: AstrBot install-upload returned NotADirectoryError because the zip did not include an explicit first directory entry before astrbot_plugin_emotional_state/README.md. Failed plugin record appeared as plugin_upload_astrbot_plugin_emotional_state.

## 2026-05-07 Iteration 19

Status: complete.

- Ran remote smoke before continuing iteration:
  - login succeeded,
  - AstrBot version was `4.24.2`,
  - plugin API returned 30 plugins,
  - `astrbot_plugin_emotional_state` was present,
  - failed plugin data was `{}`.
- Strengthened `scripts\remote_smoke_playwright.js` so `ASTRBOT_EXPECT_PLUGIN` resolves the real plugin object from `/api/plugin/get`, not just the names list.
- Added `expectedPluginRuntime` to the smoke output with plugin runtime metadata:
  - name,
  - displayName,
  - version,
  - activated,
  - reserved,
  - author,
  - desc,
  - repo,
  - astrbotVersion,
  - installedAt.
- Added optional hard assertions:
  - `ASTRBOT_EXPECT_PLUGIN_VERSION` exits with code `7` on mismatch,
  - `ASTRBOT_EXPECT_PLUGIN_DISPLAY_NAME` exits with code `8` on mismatch,
  - activated target plugin explicitly set to `false` exits with code `6`.
- Updated README with the runtime-metadata smoke workflow.
- Updated `tests/test_remote_smoke_contract.py` to lock the new environment-variable and exit-code contract.
- Corrected the stale Iteration 18 progress line that said the plugin was still not installed.
- Updated `task_plan.md` and `findings.md` so future context recovery starts from the installed-and-activated remote state.

Validation complete:

- `py -3.13 -m unittest tests.test_remote_smoke_contract -v`: 8 tests passed.
- Bundled Node `--check scripts\remote_smoke_playwright.js`: passed.
- Bundled Node `--check scripts\remote_install_upload_playwright.js`: passed.
- `py -3.13 -m unittest discover -s tests -v`: 136 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- `py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip`: passed.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with `ASTRBOT_EXPECT_PLUGIN=astrbot_plugin_emotional_state`, `ASTRBOT_EXPECT_PLUGIN_VERSION=1.0.0`, and `ASTRBOT_EXPECT_PLUGIN_DISPLAY_NAME=多维情绪状态`: passed.
  - `expectedPluginRuntime.activated=true`,
  - version matched,
  - display name matched,
  - failed plugin data was `{}`.

Next iteration:

- Iteration 20 hardens the remote upload preflight by inspecting full zip contents before any upload mutation.

## 2026-05-07 Iteration 20

Status: complete.

- Hardened `scripts\remote_install_upload_playwright.js` before upload mutation:
  - added central-directory inspection,
  - required all entries to live under `astrbot_plugin_emotional_state/`,
  - rejected absolute paths, Windows backslashes, and parent traversal,
  - required `metadata.yaml`, `main.py`, `README.md`, and `_conf_schema.json`,
  - rejected `tests/`, `scripts/`, `output/`, `dist/`, `raw/`, `__pycache__/`, and `.git/`.
- Updated README to document the uploadable package preflight contract.
- Clarified that `scripts\remote_smoke_playwright.js` is the read-only script, avoiding ambiguity near the upload-script section.
- Updated `tests/test_remote_smoke_contract.py` to lock central-directory preflight checks and forbidden path checks.

Validation complete:

- `py -3.13 -m unittest tests.test_package_plugin tests.test_remote_smoke_contract -v`: 12 tests passed.
- Bundled Node `--check scripts\remote_install_upload_playwright.js`: passed.
- Bundled Node `--check scripts\remote_smoke_playwright.js`: passed.
- `py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip`: passed.
- `py -3.13 -m unittest discover -s tests -v`: 136 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with version/display-name assertions: passed.

Next iteration:

- Iteration 21 adds local unit coverage for remote install zip preflight failure cases without calling the remote server.

## 2026-05-07 Iteration 21

Status: complete.

- Extracted upload zip preflight logic into `scripts\plugin_zip_preflight.js`.
- Updated `scripts\remote_install_upload_playwright.js` to call the shared preflight module before any remote upload mutation.
- Added CLI usage for local preflight:
  - `node scripts\plugin_zip_preflight.js <zip> <plugin_name>`.
- Added local unit coverage in `tests/test_package_plugin.py`:
  - packaged plugin zip is accepted,
  - missing explicit root directory entry is rejected,
  - excluded `raw/` and `tests/` segments are rejected,
  - missing required runtime file is rejected,
  - parent traversal entries are rejected.
- Updated README to document standalone zip preflight and Node syntax check for the new script.
- Updated remote smoke contract tests so the upload script must call shared preflight, while central-directory assertions live in the shared preflight script.

Validation complete:

- `py -3.13 -m unittest tests.test_package_plugin -v`: 9 tests passed.
- `py -3.13 -m unittest tests.test_package_plugin tests.test_remote_smoke_contract -v`: 17 tests passed.
- Bundled Node `--check scripts\plugin_zip_preflight.js`: passed.
- Bundled Node `--check scripts\remote_install_upload_playwright.js`: passed.
- Bundled Node `--check scripts\remote_smoke_playwright.js`: passed.
- `py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip`: passed.
- `py -3.13 -m unittest discover -s tests -v`: 141 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with version/display-name assertions: passed.

Next iteration:

- Iteration 22 reviews git branch/packaging state and prepares a maintainable branch split or commit staging plan.

## 2026-05-07 Iteration 22

Status: complete.

- Reviewed existing branches:
  - `main` is ahead of the original feature-branch baseline,
  - most `codex/*` maintenance branches still point to early baseline commit `e640a36`,
  - `codex/humanlike-agent-roadmap` points to `9a59dd8`,
  - current Iteration 11-22 changes remain uncommitted on `main`.
- Used a read-only subagent to independently inspect branch strategy and risks.
- Updated `docs\branching_strategy.md`:
  - added `codex/release-packaging` as the maintenance branch for packaging, upload preflight, install upload, and remote smoke contracts,
  - recorded the current dirty-worktree risk,
  - documented the safe sync order: validate main, commit baseline, sync integration branch, then sync feature branches.
- Updated README branch table with `codex/release-packaging` and the warning not to reset feature branches from a dirty worktree.

Validation complete:

- `py -3.13 -m unittest tests.test_remote_smoke_contract -v`: 8 tests passed.
- `py -3.13 -m unittest discover -s tests -v`: 141 tests passed.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with version/display-name assertions: passed.

Next iteration:

- Iteration 23 adds a repository maintenance checklist for committing the current baseline and syncing feature branches without losing uncommitted work.

## 2026-05-07 Iteration 23

Status: complete.

- Added `docs\release_branch_sync_checklist.md` with:
  - pre-commit validation commands,
  - remote read-only smoke workflow,
  - commit contents and artifact exclusions,
  - safe branch sync order,
  - remote upload guardrails.
- Updated README to link the new checklist in the documentation map.
- Updated `docs\branching_strategy.md` to point to the checklist for executable sync steps.

Validation complete:

- `py -3.13 -m unittest tests.test_remote_smoke_contract tests.test_package_plugin -v`: 17 tests passed.
- Bundled Node `--check scripts\remote_smoke_playwright.js`: passed.
- Bundled Node `--check scripts\remote_install_upload_playwright.js`: passed.
- Bundled Node `--check scripts\plugin_zip_preflight.js`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 48 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- `py -3.13 -m unittest discover -s tests -v`: 141 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Remote smoke with version/display-name assertions: passed.

Next iteration:

- Iteration 24 commits the validated main baseline, then syncs integration/maintenance branches from the clean baseline.

## 2026-05-07 Iteration 24

Status: complete.

- Staged the validated Iteration 11-23 baseline explicitly:
  - core runtime files,
  - README and docs,
  - persistent planning files,
  - packaging and remote validation scripts,
  - unit/contract tests.
- Confirmed staged files excluded generated `dist/` and `output/` artifacts.
- Created commit:
  - `976ee99 Add remote validation and packaging safeguards`.
- Confirmed clean worktree after commit.
- Synced maintenance branches to `976ee99`:
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

Validation complete:

- Branch sync happened only after the worktree was clean.

Next iteration:

- Iteration 25 performs final verification after branch sync and records closeout status.

## 2026-05-07 Iteration 25

Status: complete.

- Ran final verification after branch sync.
- Confirmed `main` worktree was clean before final verification.
- Final local validation passed:
  - `py -3.13 -m unittest discover -s tests -v`: 141 tests passed,
  - `py -3.13 -m py_compile ...`: passed,
  - bundled Node `--check` for all remote/package scripts: passed,
  - bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 48 entries,
  - `git diff --check`: passed.
- Final remote smoke with version/display-name assertions passed:
  - AstrBot version `4.24.2`,
  - plugin API returned 30 plugins,
  - `astrbot_plugin_emotional_state` present,
  - `expectedPluginRuntime.activated=true`,
  - version `1.0.0` matched,
  - display name `多维情绪状态` matched,
  - failed plugin data was `{}`.

Closeout status:

- Current completed iteration range: 11-25.
- Latest validated baseline commit before this final status entry: `b2bddf3`.
- All documented maintenance branches were synced to `b2bddf3`; after committing this final status entry, sync branches again to the new HEAD.

## 2026-05-07 Iteration 26

Status: complete.

- Fixed a misleading remote smoke UI field:
  - WebUI plugin cards display `displayName` such as `多维情绪状态`, not necessarily the plugin package id `astrbot_plugin_emotional_state`.
  - `pageData.hasExpectedPlugin` previously remained `false` even when the target plugin was shown in the UI by display name.
- Updated `scripts\remote_smoke_playwright.js` to report:
  - `pageData.hasExpectedPluginId`,
  - `pageData.hasExpectedPluginDisplayName`,
  - `pageData.hasExpectedPluginInUi`.
- Kept API-level assertions as the authoritative install/load checks:
  - `containsExpectedPlugin`,
  - `expectedPluginRuntime`,
  - `expectedFailedPlugin`.
- Updated README to explain the distinction between API detection and UI display-name checks.
- Updated remote smoke contract tests to lock the new UI fields.

Validation complete:

- `py -3.13 -m unittest tests.test_remote_smoke_contract -v`: 8 tests passed.
- Bundled Node `--check scripts\remote_smoke_playwright.js`: passed.
- `py -3.13 -m unittest discover -s tests -v`: 141 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check scripts\remote_install_upload_playwright.js`: passed.
- Bundled Node `--check scripts\plugin_zip_preflight.js`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 49 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with version/display-name assertions: passed.
  - `pageData.hasExpectedPluginId=false`,
  - `pageData.hasExpectedPluginDisplayName=true`,
  - `pageData.hasExpectedPluginInUi=true`,
  - API-level plugin detection and failed-plugin checks still passed.

## 2026-05-07 Iteration 27

Status: complete.

- Hardened `scripts\remote_smoke_playwright.js` so `/api/plugin/source/get-failed-plugins` must return HTTP 200.
- Added exit code `9` for failed-plugin health endpoint failure.
- Updated README to document the required failed-plugin endpoint and exit code `9`.
- Updated `tests/test_remote_smoke_contract.py` to lock:
  - `failedPlugins.status !== 200`,
  - `process.exitCode = 9`,
  - README documentation for `/api/plugin/source/get-failed-plugins` and exit code `9`.
- Updated `task_plan.md` remote smoke contract with the three required health endpoints.

Validation complete:

- `py -3.13 -m unittest tests.test_remote_smoke_contract -v`: 8 tests passed.
- Bundled Node `--check scripts\remote_smoke_playwright.js`: passed.
- `py -3.13 -m unittest discover -s tests -v`: 141 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check scripts\remote_install_upload_playwright.js`: passed.
- Bundled Node `--check scripts\plugin_zip_preflight.js`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 48 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with version/display-name assertions: passed; failed-plugin endpoint was healthy and `failedPlugins={}`.

Note for next iteration:

- The latest remote smoke passed API-level checks, but the UI page snapshot returned empty `pluginTitles` and `hasExpectedPluginInUi=false`. Next iteration should make extension-page loading/waiting more deterministic or clearly mark UI fields as best-effort.

## 2026-05-07 Iteration 28

Status: complete.

- Made the remote smoke WebUI probe more deterministic:
  - added `waitForExtensionUi(...)`,
  - waited for expected plugin id/displayName text or extension/plugin-like DOM nodes,
  - reported `pageData.uiProbeStatus` as `ready` or `best_effort_timeout`.
- Added diagnostic UI fields:
  - `pageData.selectorCounts`,
  - `pageData.bodyTextPreview`.
- Kept API-level checks authoritative:
  - `/api/stat/version`,
  - `/api/plugin/get`,
  - `/api/plugin/source/get-failed-plugins`,
  - `containsExpectedPlugin`,
  - `expectedPluginRuntime`,
  - `expectedFailedPlugin`.
- Updated README to state that UI fields are best-effort diagnostics only.
- Updated `tests\test_remote_smoke_contract.py` to lock the new UI probe contract.

Validation complete:

- `py -3.13 -m unittest tests.test_remote_smoke_contract -v`: 8 tests passed.
- Bundled Node `--check scripts\remote_smoke_playwright.js`: passed.
- `py -3.13 -m unittest discover -s tests -v`: 141 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check scripts\remote_install_upload_playwright.js`: passed.
- Bundled Node `--check scripts\plugin_zip_preflight.js`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 48 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with version/display-name assertions: passed.
  - AstrBot version `4.24.2`.
  - Plugin API returned 30 plugins.
  - `astrbot_plugin_emotional_state` was present and activated.
  - Version `1.0.0` matched.
  - Display name `多维情绪状态` matched.
  - Failed plugin data was `{}`.

## 2026-05-07 Iteration 40

Status: complete.

- Added metadata-driven plugin identity contract coverage:
  - README and release checklist `ASTRBOT_EXPECT_PLUGIN` examples must equal `metadata.yaml` `name`,
  - README/checklist package build and zip preflight commands must use `dist\<metadata name>.zip`,
  - README/checklist plugin slug references must match `metadata.yaml` `name`, with the documented external README reference explicitly allowlisted,
  - `scripts\package_plugin.py` `PLUGIN_NAME` must equal `metadata.yaml` `name`,
  - package zip root tests now derive the expected root from `metadata.yaml`,
  - `main.PLUGIN_NAME` and `public_api.PLUGIN_NAME` must equal `metadata.yaml` `name`,
  - `main.py` must keep `@register(...)` bound to `PLUGIN_NAME`,
  - public API tests now assert service discovery queries the metadata-derived plugin name.
- Adjusted contract test logic to allow README to document both smoke and install examples while still requiring every `ASTRBOT_EXPECT_PLUGIN` value to match metadata.

Validation complete:

- `py -3.13 -m unittest tests.test_remote_smoke_contract tests.test_package_plugin tests.test_public_api -v`: 73 tests passed.
- `py -3.13 -m unittest discover -s tests -v`: 156 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check` for `scripts\remote_smoke_playwright.js`, `scripts\remote_install_upload_playwright.js`, and `scripts\plugin_zip_preflight.js`: passed.
- `py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 49 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with metadata-matched plugin name/version/display-name assertions: passed.
  - AstrBot version `4.24.2`.
  - Plugin API returned 30 plugins.
  - `astrbot_plugin_emotional_state` was present and activated.
  - Version `1.0.0` matched.
  - Display name `多维情绪状态` matched.
  - Failed plugin data was `{}`.

## 2026-05-07 Iteration 41

Status: complete.

- Added runtime-derived config contract coverage for `assessment_timing`:
  - the test now extracts accepted timing options from `main.py` `_assessment_timing()`,
  - `_conf_schema.json` `assessment_timing.options` must match the runtime accepted set,
  - README must document the `assessment_timing` typed row and each accepted option.
- Added README typed config table coverage:
  - every schema key must appear in a typed README config row,
  - only legacy compatibility keys `baseline_decay`, `consequence_decay`, and `cold_war_turns` may stay outside the typed rows,
  - README row types must match schema types.

Validation complete:

- `py -3.13 -m unittest tests.test_config_schema_contract -v`: 11 tests passed.
- `py -3.13 -m unittest discover -s tests -v`: 157 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check` for `scripts\remote_smoke_playwright.js`, `scripts\remote_install_upload_playwright.js`, and `scripts\plugin_zip_preflight.js`: passed.
- `py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 49 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with metadata-matched plugin name/version/display-name assertions: passed.
  - AstrBot version `4.24.2`.
  - Plugin API returned 30 plugins.
  - `astrbot_plugin_emotional_state` was present and activated.
  - Version `1.0.0` matched.
  - Display name `多维情绪状态` matched.
  - Failed plugin data was `{}`.

## 2026-05-07 Iteration 42

Status: complete.

- Added public API service-surface contract tests:
  - `EmotionServiceProtocol` methods must match `main.py` `_REQUIRED_EMOTION_SERVICE_METHODS`,
  - `EmotionServiceProtocol` methods must match `public_api.get_emotion_service(...)` required methods,
  - `HumanlikeStateServiceProtocol` direct methods must match `public_api.get_humanlike_service(...)` required methods,
  - every required public method must exist on `EmotionalStatePlugin`,
  - plugin class schema/version attributes must cover the protocol version attributes.
- Added command documentation contract coverage:
  - `tests\test_command_tools.py` now parses `@filter.command(...)` names and aliases from `main.py`,
  - README must document each command and alias as a slash command.

Validation complete:

- `py -3.13 -m unittest tests.test_command_tools tests.test_public_api tests.test_remote_smoke_contract -v`: 73 tests passed.
- `py -3.13 -m unittest discover -s tests -v`: 160 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check` for `scripts\remote_smoke_playwright.js`, `scripts\remote_install_upload_playwright.js`, and `scripts\plugin_zip_preflight.js`: passed.
- `py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 49 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with metadata-matched plugin name/version/display-name assertions: passed.
  - AstrBot version `4.24.2`.
  - Plugin API returned 30 plugins.
  - `astrbot_plugin_emotional_state` was present and activated.
  - Version `1.0.0` matched.
  - Display name `多维情绪状态` matched.
  - Failed plugin data was `{}`.

## 2026-05-07 Iteration 43

Status: complete.

- Added LLM tool registration documentation contract coverage:
  - `tests\test_command_tools.py` now parses `@filter.llm_tool(name=...)` values from `main.py`,
  - the registered tool set must remain `get_bot_emotion_state`, `simulate_bot_emotion_update`, and `get_bot_humanlike_state`,
  - README's LLM tool table must document each registered tool name.

Validation complete:

- `py -3.13 -m unittest tests.test_command_tools -v`: 11 tests passed.
- `py -3.13 -m unittest discover -s tests -v`: 161 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check` for `scripts\remote_smoke_playwright.js`, `scripts\remote_install_upload_playwright.js`, and `scripts\plugin_zip_preflight.js`: passed.
- `py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 49 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with metadata-matched plugin name/version/display-name assertions: passed.
  - AstrBot version `4.24.2`.
  - Plugin API returned 30 plugins.
  - `astrbot_plugin_emotional_state` was present and activated.
  - Version `1.0.0` matched.
  - Display name `多维情绪状态` matched.
  - Failed plugin data was `{}`.

## 2026-05-07 Iteration 48

Status: complete.

- Clarified psychological screening public API semantics:
  - `get_psychological_screening_snapshot(...)` and `get_psychological_screening_values(...)` are read-only and may read existing state even when modeling is disabled.
  - `observe_psychological_text(..., commit=True)` is blocked by default `enable_psychological_screening=false` and returns an `enabled=false` non-diagnostic payload.
  - `reset_psychological_screening_state(...)` reuses `allow_emotion_reset_backdoor`.
- Expanded `docs\psychological_screening.md` with public API return-shape and non-diagnostic safety notes.
- Added tests for public payload structure, scale reference non-diagnostic flags, docs contract coverage, and disabled psychological commit not loading or saving state.

Validation complete:

- `py -3.13 -m unittest tests.test_psychological_screening -v`: 10 tests passed.
- `py -3.13 -m unittest tests.test_public_api.PublicApiTests tests.test_public_api.MemoryPayloadPublicApiTests.test_psychological_observe_is_disabled_by_default_for_commits -v`: 21 tests passed.
- `py -3.13 -m unittest discover -s tests -v`: 167 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check` for `scripts\remote_smoke_playwright.js`, `scripts\remote_install_upload_playwright.js`, and `scripts\plugin_zip_preflight.js`: passed.
- `py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 49 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with metadata-matched plugin name/version/display-name assertions: passed.
  - AstrBot version `4.24.2`.
  - Plugin API returned 30 plugins.
  - `astrbot_plugin_emotional_state` was present and activated.
  - Version `1.0.0` matched.
  - Display name `多维情绪状态` matched.
  - Failed plugin data was `{}`.

## 2026-05-07 Iteration 47

Status: complete.

- Hardened README public API examples for third-party plugin authors:
  - LivingMemory dict-merge example now keeps the original memory when the emotion service is unavailable or version-mismatched.
  - Direct AstrBot star lookup is documented as a temporary fallback that does not validate API completeness or schema versions.
  - `build_emotion_memory_payload(...)` table signature now names the important keyword arguments: `session_key`, `memory_text`, `source`, and `include_raw_snapshot`.
  - Humanlike API docs now warn that disabled mode returns `enabled=false` and values may be empty.
- Added README contract coverage for these safe fallback notes.

Validation complete:

- `py -3.13 -m unittest tests.test_remote_smoke_contract -v`: 16 tests passed.
- `py -3.13 -m unittest discover -s tests -v`: 166 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check` for `scripts\remote_smoke_playwright.js`, `scripts\remote_install_upload_playwright.js`, and `scripts\plugin_zip_preflight.js`: passed.
- `py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 49 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with metadata-matched plugin name/version/display-name assertions: passed.
  - AstrBot version `4.24.2`.
  - Plugin API returned 30 plugins.
  - `astrbot_plugin_emotional_state` was present and activated.
  - Version `1.0.0` matched.
  - Display name `多维情绪状态` matched.
  - Failed plugin data was `{}`.

## 2026-05-07 Iteration 46

Status: complete.

- Hardened release packaging:
  - `scripts\package_plugin.py` now collects files before opening the output zip and excludes the requested output path, preventing self-inclusion when output is placed under an included directory such as `docs\`.
  - `scripts\plugin_zip_preflight.js` now accepts `ASTRBOT_EXPECT_PLUGIN` as a fallback when the CLI plugin-name argument is omitted.
  - zip preflight now rejects unsafe `.` / `..` path segments in plugin-relative entries.
- Added package/preflight tests for self-inclusion prevention, environment fallback, and unsafe dot path segments.
- Updated README and the release branch checklist to document the stricter path contract.

Validation complete:

- `py -3.13 -m unittest tests.test_package_plugin -v`: 15 tests passed.
- `py -3.13 -m unittest discover -s tests -v`: 165 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check` for `scripts\remote_smoke_playwright.js`, `scripts\remote_install_upload_playwright.js`, and `scripts\plugin_zip_preflight.js`: passed.
- `py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 49 entries.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip` with `ASTRBOT_EXPECT_PLUGIN=astrbot_plugin_emotional_state`: passed, 49 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with metadata-matched plugin name/version/display-name assertions: passed.
  - AstrBot version `4.24.2`.
  - Plugin API returned 30 plugins.
  - `astrbot_plugin_emotional_state` was present and activated.
  - Version `1.0.0` matched.
  - Display name `多维情绪状态` matched.
  - Failed plugin data was `{}`.

## 2026-05-07 Iteration 45

Status: complete.

- Confirmed `psychological_alpha_min` and `psychological_alpha_max` are already present in runtime config, `_conf_schema.json`, and README.
- Added them to the explicit core schema default/type contract so future edits cannot quietly drift those psychological screening update bounds.

Validation complete:

- `py -3.13 -m unittest tests.test_config_schema_contract -v`: 11 tests passed.
- `py -3.13 -m unittest discover -s tests -v`: 162 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check` for `scripts\remote_smoke_playwright.js`, `scripts\remote_install_upload_playwright.js`, and `scripts\plugin_zip_preflight.js`: passed.
- `py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 49 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with metadata-matched plugin name/version/display-name assertions: passed.
  - AstrBot version `4.24.2`.
  - Plugin API returned 30 plugins.
  - `astrbot_plugin_emotional_state` was present and activated.
  - Version `1.0.0` matched.
  - Display name `多维情绪状态` matched.
  - Failed plugin data was `{}`.

## 2026-05-07 Iteration 44

Status: complete.

- Refreshed README's current test coverage matrix so it documents the contracts added in iterations 40-43:
  - command/alias parsing and LLM tool registration-name documentation,
  - `assessment_timing` runtime/schema/README options and typed config table coverage,
  - public API Protocol/required tuple/plugin implementation/schema-version consistency,
  - metadata-driven plugin identity, zip/env examples, slug/badge/version/display_name documentation.
- Added `tests\test_remote_smoke_contract.py` coverage to keep that matrix from drifting back to generic wording.

Validation complete:

- `py -3.13 -m unittest tests.test_remote_smoke_contract -v`: 15 tests passed.
- `py -3.13 -m unittest discover -s tests -v`: 162 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check` for `scripts\remote_smoke_playwright.js`, `scripts\remote_install_upload_playwright.js`, and `scripts\plugin_zip_preflight.js`: passed.
- `py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 49 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with metadata-matched plugin name/version/display-name assertions: passed.
  - AstrBot version `4.24.2`.
  - Plugin API returned 30 plugins.
  - `astrbot_plugin_emotional_state` was present and activated.
  - Version `1.0.0` matched.
  - Display name `多维情绪状态` matched.
  - Failed plugin data was `{}`.

## 2026-05-07 Iteration 39

Status: complete.

- Closed remaining humanlike roadmap/iteration-log drift:
  - replaced non-schema `daily_recovery_window` and `max_impulse_per_hour` with current humanlike timing/impulse config names,
  - replaced `simulation_flags` with current public payload field `flags`,
  - clarified that `humanlike_state_at_write` records source state time as `humanlike_updated_at`.
- Added config schema contract coverage so README/roadmap/iteration docs do not drift back to those stale names.
- Added public API payload assertions for `humanlike_state_at_write["humanlike_updated_at"]`.

Validation complete:

- `py -3.13 -m unittest tests.test_config_schema_contract tests.test_public_api tests.test_humanlike_engine -v`: 61 tests passed.
- `py -3.13 -m unittest discover -s tests -v`: 151 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check` for `scripts\remote_smoke_playwright.js`, `scripts\remote_install_upload_playwright.js`, and `scripts\plugin_zip_preflight.js`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 49 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with metadata-matched version/display-name assertions: passed.
  - AstrBot version `4.24.2`.
  - Plugin API returned 30 plugins.
  - `astrbot_plugin_emotional_state` was present and activated.
  - Version `1.0.0` matched.
  - Display name `多维情绪状态` matched.
  - Failed plugin data was `{}`.

## 2026-05-07 Iteration 49

Status: complete.

- Added machine-readable psychological risk booleans for third-party plugin branching:
  - `risk.severe_function_impairment`,
  - `risk.severe_sleep_disruption`.
- Kept the existing `risk.severe_function_impairment_signal` field for backwards compatibility.
- Updated README and `docs\psychological_screening.md` so public API docs mention severe sleep disruption and the new boolean risk flags.
- Strengthened tests at both the core payload and public API snapshot layers.
- Incorporated read-only subagent review findings:
  - synchronized the red-flag summary in `docs\psychological_screening.md`,
  - locked `snapshot["risk"]["severe_sleep_disruption"]` in `tests\test_public_api.py`.

Validation complete:

- `py -3.13 -m unittest tests.test_psychological_screening -v`: 11 tests passed.
- `py -3.13 -m unittest tests.test_public_api -v`: 49 tests passed.
- `py -3.13 -m unittest discover -s tests -v`: 168 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check` for `scripts\remote_smoke_playwright.js`, `scripts\remote_install_upload_playwright.js`, and `scripts\plugin_zip_preflight.js`: passed.
- `py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 49 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Leak scan for the remote host/password in tracked diffs excluding `output` and `dist`: passed.
- Remote smoke with metadata-matched plugin name/version/display-name assertions: passed.
  - AstrBot version `4.24.2`.
  - Plugin API returned 30 plugins.
  - `astrbot_plugin_emotional_state` was present and activated.
  - Version `1.0.0` matched.
  - Display name `多维情绪状态` matched.
  - `astrbot_plugin_livingmemory` was present.
  - Failed plugin data was `{}`.

## 2026-05-07 Iteration 51

Status: complete.

- Removed the duplicated hardcoded psychological risk field tuple from `public_api.py`.
- `public_api.PSYCHOLOGICAL_RISK_BOOLEAN_FIELDS` now directly aliases `psychological_screening.PUBLIC_RISK_BOOLEAN_FIELDS`, so the runtime payload contract and public API export cannot drift independently.
- Strengthened `tests\test_public_api.py` with an identity assertion for the shared tuple.
- Incorporated read-only subagent review feedback on the constant drift risk.

Validation complete:

- `py -3.13 -m unittest tests.test_public_api tests.test_psychological_screening -v`: 62 tests passed.
- `py -3.13 -m unittest discover -s tests -v`: 170 tests passed.
- `py -3.13 -m py_compile public_api.py psychological_screening.py main.py`: passed.
- Bundled Node `--check` for `scripts\remote_smoke_playwright.js`, `scripts\remote_install_upload_playwright.js`, and `scripts\plugin_zip_preflight.js`: passed.
- `py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 49 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with metadata-matched plugin name/version/display-name assertions: passed for `astrbot_plugin_emotional_state`.
  - AstrBot version `4.24.2`.
  - Plugin API returned 30 plugins.
  - `astrbot_plugin_emotional_state` was present and activated.
  - Version `1.0.0` matched.
  - Display name `多维情绪状态` matched.
  - `astrbot_plugin_livingmemory` was present.
  - Remote server reported one unrelated failed-plugin record for `plugin_upload_astrbot_plugin_volcengine_asr` because that directory already exists.

## 2026-05-07 Iteration 52

Status: complete.

- Added `failedPluginSummary` to `scripts\remote_smoke_playwright.js`:
  - total failed-plugin count and names,
  - `hasExpectedPluginFailure`,
  - `expectedPluginFailureKey`,
  - `unrelatedCount`.
- Kept failure semantics unchanged:
  - failed-plugin endpoint failure exits `9`,
  - only the expected plugin appearing in failed-plugin records exits `5`,
  - unrelated failed-plugin records stay diagnostic.
- Updated README and `docs\release_branch_sync_checklist.md` so remote smoke results are interpreted from `expectedFailedPlugin`, `failedPluginSummary`, `containsExpectedPlugin`, `expectedPluginRuntime`, and version/display-name matches together.
- Strengthened remote smoke contract tests for the new output fields and wording.
- Incorporated read-only subagent review feedback on the ambiguity between remote server failed-plugin state and target-plugin failure.

Validation complete:

- `py -3.13 -m unittest tests.test_remote_smoke_contract -v`: 16 tests passed.
- `py -3.13 -m unittest discover -s tests -v`: 170 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check` for `scripts\remote_smoke_playwright.js`, `scripts\remote_install_upload_playwright.js`, and `scripts\plugin_zip_preflight.js`: passed.
- `py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 49 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with metadata-matched plugin name/version/display-name assertions: passed.
  - AstrBot version `4.24.2`.
  - Plugin API returned 30 plugins.
  - `astrbot_plugin_emotional_state` was present and activated.
  - Version `1.0.0` matched.
  - Display name `多维情绪状态` matched.
  - `failedPluginSummary.count=0`.
  - `failedPluginSummary.hasExpectedPluginFailure=false`.
  - `failedPluginSummary.unrelatedCount=0`.

## 2026-05-07 Iteration 53

Status: complete.

- Added `expectedPluginChecks` to `scripts\remote_smoke_playwright.js`.
- `expectedPluginChecks.ok` now summarizes the target plugin's API-level pass state across:
  - found in `/api/plugin/get`,
  - absent from expected failed-plugin records,
  - not deactivated,
  - version match when `ASTRBOT_EXPECT_PLUGIN_VERSION` is set,
  - display-name match when `ASTRBOT_EXPECT_PLUGIN_DISPLAY_NAME` is set.
- Kept detailed fields (`containsExpectedPlugin`, `expectedPluginRuntime`, `expectedFailedPlugin`, version/display-name matches, `failedPluginSummary`) for diagnostics.
- Updated README and `docs\release_branch_sync_checklist.md` so humans and automation can prefer `expectedPluginChecks.ok` while still reading detailed diagnostics.
- Strengthened remote smoke contract tests for the new summary fields.

Validation complete:

- `py -3.13 -m unittest tests.test_remote_smoke_contract -v`: 16 tests passed.
- `py -3.13 -m unittest discover -s tests -v`: 170 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check` for `scripts\remote_smoke_playwright.js`, `scripts\remote_install_upload_playwright.js`, and `scripts\plugin_zip_preflight.js`: passed.
- `py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 49 entries.
- Remote smoke with metadata-matched plugin name/version/display-name assertions: passed.
  - AstrBot version `4.24.2`.
  - Plugin API returned 30 plugins.
  - `expectedPluginChecks.ok=true`.
  - `expectedPluginChecks.found=true`.
  - `expectedPluginChecks.notFailed=true`.
  - `expectedPluginChecks.activated=true`.
  - `expectedPluginChecks.versionMatches=true`.
  - `expectedPluginChecks.displayNameMatches=true`.
  - `failedPluginSummary.count=0`.

## 2026-05-07 Iteration 50

Status: complete.

- Exported a stable psychological risk boolean field contract:
  - `psychological_screening.PUBLIC_RISK_BOOLEAN_FIELDS`,
  - `public_api.PSYCHOLOGICAL_RISK_BOOLEAN_FIELDS`.
- Refactored public psychological risk construction through `public_risk_payload(...)` so the payload and exported field list stay aligned.
- Clarified README and `docs\psychological_screening.md` so third-party plugins read nested fields such as `payload["risk"]["requires_human_review"]` instead of treating risk flags as top-level payload keys.
- Added contract tests for:
  - the exported public API constant,
  - all declared risk boolean fields being present and boolean in public payloads,
  - README/docs wording for nested risk access.
- Incorporated read-only subagent review feedback on the README nested field ambiguity.

Validation complete:

- `py -3.13 -m unittest tests.test_psychological_screening tests.test_public_api -v`: 62 tests passed.
- `py -3.13 -m unittest discover -s tests -v`: 170 tests passed.
- `py -3.13 -m py_compile psychological_screening.py public_api.py main.py`: passed.
- Bundled Node `--check` for `scripts\remote_smoke_playwright.js`, `scripts\remote_install_upload_playwright.js`, and `scripts\plugin_zip_preflight.js`: passed.
- `py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 49 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with metadata-matched plugin name/version/display-name assertions: passed.
  - AstrBot version `4.24.2`.
  - Plugin API returned 30 plugins.
  - `astrbot_plugin_emotional_state` was present and activated.
  - Version `1.0.0` matched.
  - Display name `多维情绪状态` matched.
  - `astrbot_plugin_livingmemory` was present.
  - Failed plugin data was `{}`.

## 2026-05-07 Iteration 38

Status: complete.

- Aligned `docs\humanlike_agent_model_roadmap.md` with the current implementation:
  - `humanlike_state_at_write` is the current memory payload key,
  - `humanlike_memory_write_enabled` defaults to `true`,
  - roadmap config examples now use existing schema keys.
- Updated `docs\humanlike_agent_iteration_log.md` so early proposed fields are clearly marked as not part of the current schema.
- Added `tests\test_config_schema_contract.py` coverage to prevent README/roadmap drift back to:
  - `humanlike_at_write`,
  - `humanlike_personification_level`,
  - `humanlike_dependency_guard_level`,
  - `dependency_guard_level` as current roadmap/README config.

Validation complete:

- `py -3.13 -m unittest tests.test_config_schema_contract tests.test_public_api tests.test_remote_smoke_contract -v`: 67 tests passed.
- `py -3.13 -m unittest discover -s tests -v`: 151 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check` for `scripts\remote_smoke_playwright.js`, `scripts\remote_install_upload_playwright.js`, and `scripts\plugin_zip_preflight.js`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 49 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with metadata-matched version/display-name assertions: passed.
  - AstrBot version `4.24.2`.
  - Plugin API returned 30 plugins.
  - `astrbot_plugin_emotional_state` was present and activated.
  - Version `1.0.0` matched.
  - Display name `多维情绪状态` matched.
  - Failed plugin data was `{}`.

## 2026-05-07 Iteration 37

Status: complete.

- Strengthened `public_api.get_emotion_service(...)` so service discovery requires:
  - complete core async method surface,
  - `emotion_api_version == "1.0"`,
  - `emotion_schema_version == "astrbot.emotion_state.v2"`,
  - `emotion_memory_schema_version == "astrbot.emotion_memory.v1"`,
  - `psychological_screening_schema_version == "astrbot.psychological_screening.v1"`.
- Strengthened `public_api.get_humanlike_service(...)` so humanlike discovery also requires `humanlike_state_schema_version == "astrbot.humanlike_state.v1"`.
- Applied the same emotion version/schema check to `main.get_emotional_state_plugin(...)`.
- Added public API tests for wrong public versions and wrong humanlike schema versions.
- Updated README and contract tests so integration docs say helpers check both method completeness and versioned schema compatibility.

Validation complete:

- `py -3.13 -m unittest tests.test_public_api tests.test_remote_smoke_contract -v`: 57 tests passed.
- `py -3.13 -m py_compile main.py public_api.py`: passed.
- `py -3.13 -m unittest discover -s tests -v`: 150 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check` for `scripts\remote_smoke_playwright.js`, `scripts\remote_install_upload_playwright.js`, and `scripts\plugin_zip_preflight.js`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 49 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with metadata-matched version/display-name assertions: passed.
  - AstrBot version `4.24.2`.
  - Plugin API returned 30 plugins.
  - `astrbot_plugin_emotional_state` was present and activated.
  - Version `1.0.0` matched.
  - Display name `多维情绪状态` matched.
  - Failed plugin data was `{}`.

## 2026-05-07 Iteration 36

Status: complete.

- Strengthened `scripts\plugin_zip_preflight.js` so uploadable zips must pass a metadata identity check:
  - filename still must end with `<expectedPlugin>.zip`,
  - first zip entry still must be the explicit `<expectedPlugin>/` directory,
  - all entries still must stay under that directory,
  - zip-internal `<expectedPlugin>/metadata.yaml` must contain `name: <expectedPlugin>`.
- Added zip-entry content reading for stored and deflated entries so the preflight can inspect `metadata.yaml` before any remote upload mutation.
- Added package preflight tests for metadata `name` mismatch and missing `name:`.
- Updated README, release checklist, and remote contract tests to document and lock the metadata identity check.

Validation complete:

- `py -3.13 -m unittest tests.test_package_plugin tests.test_remote_smoke_contract -v`: 23 tests passed.
- Bundled Node `--check scripts\plugin_zip_preflight.js`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 49 entries.
- `py -3.13 -m unittest discover -s tests -v`: 147 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check` for `scripts\remote_smoke_playwright.js`, `scripts\remote_install_upload_playwright.js`, and `scripts\plugin_zip_preflight.js`: passed.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with metadata-matched version/display-name assertions: passed.
  - AstrBot version `4.24.2`.
  - Plugin API returned 30 plugins.
  - `astrbot_plugin_emotional_state` was present and activated.
  - Version `1.0.0` matched.
  - Display name `多维情绪状态` matched.
  - Failed plugin data was `{}`.
  - `pageData.uiProbeStatus="ready"`.
  - `pageData.selectorCounts.extensionTitleRows=30`.
  - `pageData.hasExpectedPluginDisplayName=true`.
  - `pageData.hasExpectedPluginInUi=true`.

## 2026-05-07 Iteration 29

Status: complete.

- Removed a misleading remote smoke UI compatibility edge:
  - `pageData.hasExpectedPluginId` remains the exact plugin-directory/id text check,
  - `pageData.hasExpectedPluginDisplayName` remains the display-name text check,
  - `pageData.hasExpectedPluginInUi` remains the combined UI diagnostic,
  - legacy `pageData.hasExpectedPlugin` now aliases `hasExpectedPluginInUi`.
- Updated README to document the legacy alias explicitly.
- Updated the remote smoke contract test to lock `hasExpectedPlugin: hasExpectedPluginInUi`.

Validation complete:

- `py -3.13 -m unittest tests.test_remote_smoke_contract -v`: 8 tests passed.
- Bundled Node `--check scripts\remote_smoke_playwright.js`: passed.
- `py -3.13 -m unittest discover -s tests -v`: 141 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check scripts\remote_install_upload_playwright.js`: passed.
- Bundled Node `--check scripts\plugin_zip_preflight.js`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 48 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with version/display-name assertions: passed.
  - `pageData.hasExpectedPlugin=true`.
  - `pageData.hasExpectedPluginId=false`.
  - `pageData.hasExpectedPluginDisplayName=true`.
  - `pageData.hasExpectedPluginInUi=true`.
  - API-level install, activation, version, display-name, and failed-plugin checks all passed.

## 2026-05-07 Iteration 30

Status: complete.

- Added centralized remote smoke API health diagnostics:
  - `apiHealth.statVersion` for `/api/stat/version`,
  - `apiHealth.pluginGet` for `/api/plugin/get`,
  - `apiHealth.failedPlugins` for `/api/plugin/source/get-failed-plugins`.
- Kept existing hard failure semantics:
  - version/plugin API failures still set exit code `1`,
  - failed-plugin endpoint failure still sets exit code `9`,
  - expected plugin/runtime failures keep their existing exit codes.
- Updated README to document the `apiHealth` summary.
- Updated remote smoke contract tests to lock the new fields.

Validation complete:

- `py -3.13 -m unittest tests.test_remote_smoke_contract -v`: 8 tests passed.
- Bundled Node `--check scripts\remote_smoke_playwright.js`: passed.
- `py -3.13 -m unittest discover -s tests -v`: 141 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check scripts\remote_install_upload_playwright.js`: passed.
- Bundled Node `--check scripts\plugin_zip_preflight.js`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 48 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with version/display-name assertions: passed.
  - `apiHealth.statVersion.ok=true`.
  - `apiHealth.pluginGet.ok=true`.
  - `apiHealth.failedPlugins.ok=true`.
  - API-level plugin detection and UI best-effort diagnostics passed.

## 2026-05-07 Iteration 31

Status: complete.

- Updated README remote smoke/install/preflight examples to use a `$node` variable:
  - prefer Codex bundled Node at `$HOME\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe`,
  - set `NODE_PATH` to the bundled `node_modules`,
  - fall back to `node` from `PATH` if the bundled executable is missing.
- Updated `docs\release_branch_sync_checklist.md` with the same Node fallback and converted Node commands to `& $node ...`.
- Added remote smoke contract coverage so docs keep the bundled Node fallback and do not regress to bare `node` examples in the release checklist.

Validation complete:

- `py -3.13 -m unittest tests.test_remote_smoke_contract -v`: 9 tests passed.
- Bundled Node `--check scripts\remote_smoke_playwright.js`: passed.
- `py -3.13 -m unittest tests.test_remote_smoke_contract tests.test_package_plugin -v`: 18 tests passed.
- `py -3.13 -m unittest discover -s tests -v`: 142 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- `py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip`: passed.
- Bundled Node `--check scripts\remote_install_upload_playwright.js`: passed.
- Bundled Node `--check scripts\plugin_zip_preflight.js`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 49 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with bundled Node and version/display-name assertions: passed.

## 2026-05-07 Iteration 32

Status: complete.

- Strengthened documentation contract tests for bundled Node usage:
  - README and `docs\release_branch_sync_checklist.md` must share the exact same three-line `$node` fallback snippet,
  - the fallback must appear before the first documented Node/Playwright command,
  - README must not regress to bare `node scripts\remote_smoke_playwright.js` or `node --check scripts\remote_smoke_playwright.js` commands.

Validation complete:

- `py -3.13 -m unittest tests.test_remote_smoke_contract -v`: 10 tests passed.
- Bundled Node `--check scripts\remote_smoke_playwright.js`: passed.
- `py -3.13 -m unittest discover -s tests -v`: 143 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check scripts\remote_install_upload_playwright.js`: passed.
- Bundled Node `--check scripts\plugin_zip_preflight.js`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 49 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with bundled Node and version/display-name assertions: passed.

## 2026-05-07 Iteration 33

Status: complete.

- Updated README's test coverage matrix for `tests/test_remote_smoke_contract.py`.
- The matrix now documents the expanded contract coverage:
  - environment-only remote credentials,
  - read-only remote smoke behavior,
  - ignored screenshot artifacts,
  - API health summary,
  - UI best-effort fields,
  - upload-script boundaries,
  - bundled Node documentation contract.
- Added README contract assertions for the refreshed matrix wording.

Validation complete:

- `py -3.13 -m unittest tests.test_remote_smoke_contract -v`: 10 tests passed.
- Bundled Node `--check scripts\remote_smoke_playwright.js`: passed.
- `py -3.13 -m unittest discover -s tests -v`: 143 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check scripts\remote_install_upload_playwright.js`: passed.
- Bundled Node `--check scripts\plugin_zip_preflight.js`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 49 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with bundled Node and version/display-name assertions: passed.

## 2026-05-07 Iteration 34

Status: complete.

- Added a remote smoke documentation contract tying version/display-name assertions to `metadata.yaml`.
- `tests\test_remote_smoke_contract.py` now reads:
  - `metadata.yaml` `version`,
  - `metadata.yaml` `display_name`.
- README and `docs\release_branch_sync_checklist.md` must document matching:
  - `ASTRBOT_EXPECT_PLUGIN_VERSION`,
  - `ASTRBOT_EXPECT_PLUGIN_DISPLAY_NAME`.

Validation complete:

- `py -3.13 -m unittest tests.test_remote_smoke_contract -v`: 11 tests passed.
- Bundled Node `--check scripts\remote_smoke_playwright.js`: passed.
- `py -3.13 -m unittest discover -s tests -v`: 144 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check scripts\remote_install_upload_playwright.js`: passed.
- Bundled Node `--check scripts\plugin_zip_preflight.js`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 49 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with metadata-matched version/display-name assertions: passed.

## 2026-05-07 Iteration 35

Status: complete.

- Added README badge/compatibility contract coverage in `tests\test_remote_smoke_contract.py`.
- The new test reads `metadata.yaml` `version` and `astrbot_version`, then verifies:
  - README visible version badge text,
  - README version badge URL,
  - README visible AstrBot compatibility badge text,
  - README AstrBot compatibility badge URL,
  - README metadata example for `astrbot_version`.
- Fixed the local test expectation so the Shields URL encoding for `astrbot_version` includes `=` as `%3D`.

Validation complete:

- `py -3.13 -m unittest tests.test_remote_smoke_contract -v`: 12 tests passed.
- `py -3.13 -m unittest discover -s tests -v`: 145 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check` for `scripts\remote_smoke_playwright.js`, `scripts\remote_install_upload_playwright.js`, and `scripts\plugin_zip_preflight.js`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 49 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Remote smoke with metadata-matched version/display-name assertions: passed.
  - AstrBot version `4.24.2`.
  - Plugin API returned 30 plugins.
  - `astrbot_plugin_emotional_state` was present and activated.
  - Version `1.0.0` matched.
  - Display name `多维情绪状态` matched.
  - Failed plugin data was `{}`.

## 2026-05-07 Iteration 54

Status: complete.

- Fixed packaged public API imports when third-party plugins import by package name:
  - `public_api.py` now prefers relative import of `psychological_screening.PUBLIC_RISK_BOOLEAN_FIELDS`,
  - keeps the top-level import fallback for direct local test/import compatibility.
- Added a release-package regression test that:
  - builds the plugin zip,
  - extracts it under the metadata plugin directory,
  - removes the repository root from `sys.path`,
  - imports `astrbot_plugin_emotional_state.public_api` by package name.

Validation complete:

- `py -3.13 -m unittest tests.test_public_api -v`: 51 tests passed.
- `py -3.13 -m py_compile public_api.py psychological_screening.py main.py`: passed.
- `py -3.13 -m unittest discover -s tests -v`: 171 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check` for `scripts\remote_smoke_playwright.js`, `scripts\remote_install_upload_playwright.js`, and `scripts\plugin_zip_preflight.js`: passed.
- `py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 49 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Leak scan for remote address/password in this iteration's diff: passed.
- Remote smoke with expected plugin version/display-name assertions: passed.

## 2026-05-07 Iteration 55

Status: complete.

- Tightened release packaging contracts:
  - the release zip must include root runtime modules needed for package-name imports,
  - README install tree now represents runtime/plugin install contents instead of repository-only development files,
  - README explicitly says `tests/`, `scripts/`, `raw/`, `output/`, and `dist/` are excluded from release zips.

Validation complete:

- `py -3.13 -m unittest tests.test_package_plugin -v`: 16 tests passed.
- `py -3.13 -m unittest tests.test_remote_smoke_contract -v`: 16 tests passed.
- `py -3.13 -m unittest discover -s tests -v`: 172 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check` for `scripts\remote_smoke_playwright.js`, `scripts\remote_install_upload_playwright.js`, and `scripts\plugin_zip_preflight.js`: passed.
- `py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 49 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Leak scan for remote address/password in this iteration's diff: passed.
- Remote smoke with expected plugin version/display-name assertions: passed.

## 2026-05-07 Iteration 56

Status: complete.

- Aligned upload zip preflight with the release package runtime-root contract:
  - `scripts/plugin_zip_preflight.js` now requires `__init__.py`, `public_api.py`, and the root runtime modules,
  - preflight fixture zips include the same required runtime files,
  - missing required-entry tests cover `__init__.py`, `public_api.py`, and `_conf_schema.json`,
  - README preflight documentation lists the full required entry set.

Validation complete:

- `py -3.13 -m unittest tests.test_package_plugin -v`: 16 tests passed.
- `py -3.13 -m unittest tests.test_remote_smoke_contract -v`: 16 tests passed.
- `py -3.13 -m unittest discover -s tests -v`: 172 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check` for `scripts\remote_smoke_playwright.js`, `scripts\remote_install_upload_playwright.js`, and `scripts\plugin_zip_preflight.js`: passed.
- `py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 49 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Leak scan for remote address/password in this iteration's diff: passed.
- Remote smoke with expected plugin version/display-name assertions: passed.

## 2026-05-07 Iteration 57

Status: complete.

- Tightened dependency-declaration release checks:
  - upload zip preflight now requires `requirements.txt`,
  - preflight fixture zips include `requirements.txt`,
  - missing required-entry tests cover `requirements.txt`,
  - README and release checklist document the dependency declaration as part of the upload contract.

Validation complete:

- `py -3.13 -m unittest tests.test_package_plugin -v`: 16 tests passed.
- `py -3.13 -m unittest tests.test_remote_smoke_contract -v`: 16 tests passed.
- `py -3.13 -m unittest discover -s tests -v`: 172 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py psychological_screening.py public_api.py prompts.py scripts\build_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\build_psychological_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check` for `scripts\remote_smoke_playwright.js`, `scripts\remote_install_upload_playwright.js`, and `scripts\plugin_zip_preflight.js`: passed.
- `py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 49 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Leak scan for remote address/password in this iteration's diff: passed.
- Remote smoke with expected plugin version/display-name assertions: passed.

## 2026-05-07 Iteration 58

Status: complete.

- Tightened documentation/test consistency around the current package contract:
  - README local `py_compile` command now includes `scripts\package_plugin.py`,
  - remote install contract test now asserts `requirements.txt` is in the preflight required-entry set,
  - README and release checklist now describe `uninstall-failed` as failed-upload residue cleanup only,
  - tests lock `delete_config=false` and `delete_data=false` for that cleanup path,
  - repository working memory and contract tests no longer store real remote host/password literals.

Validation complete:

- `py -3.13 -m unittest tests.test_remote_smoke_contract.RemoteSmokeContractTests.test_remote_install_script_requires_explicit_confirmation tests.test_remote_smoke_contract.RemoteSmokeContractTests.test_remote_install_script_only_allows_upload_install_mutation -v`: 2 tests passed.
- `py -3.13 -m unittest tests.test_remote_smoke_contract -v`: 16 tests passed.
- `py -3.13 -m unittest discover -s tests -v`: 172 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py psychological_screening.py humanlike_engine.py prompts.py public_api.py scripts\build_literature_kb.py scripts\build_psychological_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\package_plugin.py`: passed.
- Bundled Node `--check` for `scripts\remote_smoke_playwright.js`, `scripts\remote_install_upload_playwright.js`, and `scripts\plugin_zip_preflight.js`: passed.
- `py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 49 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Leak scan for remote address/password in this iteration's diff: passed.
- Remote smoke with expected plugin version/display-name assertions: passed.

## 2026-05-07 Iteration 59

Status: complete.

- Added a safe moral repair subsystem instead of implementing deception or wrongdoing strategy generation:
  - new `moral_repair_engine.py` with deception/harm risk signals, guilt, shame, responsibility, apology readiness, compensation readiness, trust repair, accountability, avoidance risk, time-based decay, rapid-update gating, prompt fragments, memory annotations, and public payload boundaries,
  - plugin lifecycle integration updates moral repair state from request/response text when enabled and injects repair-oriented prompt context when configured,
  - public API helper `get_moral_repair_service(...)`, schema constant, plugin methods, commands, and LLM tool are documented and contract-tested,
  - LivingMemory-shaped payload can include `moral_repair_state_at_write`,
  - release package and upload preflight now require `moral_repair_engine.py`.

Validation complete:

- `py -3.13 -m unittest tests.test_package_plugin tests.test_remote_smoke_contract -v`: 32 tests passed.
- `py -3.13 -m unittest tests.test_command_tools tests.test_public_api tests.test_moral_repair_engine tests.test_config_schema_contract -v`: 94 tests passed.
- `py -3.13 -m unittest discover -s tests -v`: 193 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py moral_repair_engine.py psychological_screening.py prompts.py public_api.py scripts\build_literature_kb.py scripts\build_psychological_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\package_plugin.py`: passed.
- `py -3.13 -m json.tool _conf_schema.json`: passed.
- Bundled Node `--check` for `scripts\remote_smoke_playwright.js`, `scripts\remote_install_upload_playwright.js`, and `scripts\plugin_zip_preflight.js`: passed.
- `py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 50 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Leak scan for remote address/password in the repository excluding generated/runtime directories: passed.
- Remote read-only smoke with expected plugin version/display-name assertions: passed. The target plugin was installed, activated, version-matched, display-name-matched, and absent from failed-plugin records.

## 2026-05-07 Iteration 60

Status: complete.

- Declared the project license as `GPL-3.0-or-later`:
  - added the standard GPLv3 `LICENSE` file,
  - added `license: GPL-3.0-or-later` to `metadata.yaml`,
  - updated README license section and install tree,
  - included `LICENSE` in release package collection and upload zip preflight required entries,
  - updated release checklist and contract tests so license metadata and package contents stay aligned.

Validation complete:

- `py -3.13 -m unittest tests.test_package_plugin tests.test_remote_smoke_contract -v`: 33 tests passed.
- `py -3.13 -m unittest discover -s tests -v`: 194 tests passed.
- `py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py moral_repair_engine.py psychological_screening.py prompts.py public_api.py scripts\build_literature_kb.py scripts\build_psychological_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\package_plugin.py`: passed.
- `py -3.13 -m json.tool _conf_schema.json`: passed.
- Bundled Node `--check` for `scripts\plugin_zip_preflight.js`, `scripts\remote_smoke_playwright.js`, and `scripts\remote_install_upload_playwright.js`: passed.
- `py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 51 entries.
- Zip inspection confirmed `astrbot_plugin_emotional_state/LICENSE` and `astrbot_plugin_emotional_state/metadata.yaml`.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Leak scan for remote address/password in the repository excluding generated/runtime directories: passed.
- Remote read-only smoke with expected plugin version/display-name assertions: passed.

## 2026-05-07 Revolutionary Iterations 61-70

Status: planned.

- Added the 10-step revolutionary iteration queue to `task_plan.md` before implementation so automatic context compaction can recover the intended sequence.
- Current focus:
  - Iteration 61: integrated self-state bus and public contract.
  - Iterations 62-70: causal traces, replay bundles, policy planning, migrations, export/import diagnostics, degradation modes, LivingMemory expansion, release contracts, and final validation/branch sync.
- Subagents started for read-only review:
  - code/model direction review,
  - test/package/remote contract review.

## 2026-05-07 Iterations 61-68

Status: complete.

- Iteration 61 added the read-only integrated self-state bus:
  - `integrated_self.py` fuses emotion, humanlike, moral repair, and non-diagnostic psychological screening snapshots.
  - `main.py` exposes `get_integrated_self_snapshot`, `get_integrated_self_prompt_fragment`, `/integrated_self`, and `get_bot_integrated_self_state`.
  - Memory writes can include `integrated_self_state_at_write`; optional module write switches are respected so disabled annotations do not trigger unwanted state loads.
- Iteration 62 added evidence-weighted causal trace summaries:
  - trace items include module, signal, evidence weight, captured timestamp, real-time lag, summary, and flags.
  - persona fingerprint, relationship decisions, active effects, moral repair pressure, humanlike boundary signals, and psychological red flags are explainable.
- Iteration 63 added deterministic replay bundles:
  - `build_integrated_self_replay_bundle` and `replay_integrated_self_bundle` produce checksum-verified sanitized bundles without KV access.
- Iteration 64 added policy planning:
  - `policy_plan` maps integrated state to allowed actions, blocked actions, response modulation, repair actions, and prompt budget.
- Iteration 65 added compatibility probes:
  - `probe_integrated_self_compatibility` reports schema mismatch and missing required fields instead of silently accepting partial contracts.
- Iteration 66 added sanitized diagnostics:
  - `export_integrated_self_diagnostics` exposes module status, risk booleans, state index, and trace summary while excluding raw snapshots, prompt fragments, persona text, message text, and unsafe strategy content.
- Iteration 67 added degradation modes:
  - new config `integrated_self_degradation_profile` accepts `full`, `balanced`, and `minimal`.
  - `minimal` reduces trace/prompt budget but preserves schema, safety priority, blocked actions, crisis signals, moral repair transparency, and relationship boundary signals.
- Iteration 68 expanded LivingMemory integration:
  - memory payloads now include a sanitized `state_annotations_at_write` envelope by default.
  - the envelope includes only state annotations such as `emotion_at_write`, `humanlike_state_at_write`, `moral_repair_state_at_write`, and `integrated_self_state_at_write`; it excludes raw snapshots.

Validation so far:

- `py -3.13 -m unittest tests.test_integrated_self tests.test_public_api tests.test_config_schema_contract tests.test_command_tools tests.test_remote_smoke_contract -v`: 116 tests passed.
- `py -3.13 -m py_compile main.py integrated_self.py public_api.py`: passed.
- `py -3.13 -m json.tool _conf_schema.json`: passed.

## 2026-05-07 Iteration 69

Status: complete.

- Hardened release/docs/API contracts around the integrated self-state surface:
  - README now documents new integrated self public API methods: policy plan, deterministic replay bundle, replay result, compatibility probe, and sanitized diagnostics.
  - README documents `integrated_self_degradation_profile` with `full`, `balanced`, and `minimal`.
  - README test matrix now includes `tests/test_integrated_self.py`.
  - Public API Protocol/service discovery now requires the new integrated self methods, keeping third-party plugin discovery versioned and complete.
- Packaging and remote-smoke contracts remain aligned with `integrated_self.py`, GPL metadata, runtime root files, and upload preflight required entries.

Validation complete:

- `py -3.13 -m unittest discover -s tests -v`: 208 tests passed.
- `py -3.13 -m unittest tests.test_package_plugin tests.test_remote_smoke_contract -v`: 33 tests passed when run sequentially. A prior parallel run against full discovery caused a Windows temp zip race on `docs\astrbot_plugin_emotional_state.zip`; rerun passed.
- `py -3.13 -m py_compile main.py emotion_engine.py psychological_screening.py humanlike_engine.py integrated_self.py moral_repair_engine.py prompts.py public_api.py scripts\build_literature_kb.py scripts\build_psychological_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\package_plugin.py`: passed.
- `py -3.13 -m json.tool _conf_schema.json`: passed.
- Bundled Node `--check` for `scripts\plugin_zip_preflight.js`, `scripts\remote_smoke_playwright.js`, and `scripts\remote_install_upload_playwright.js`: passed.
- `py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip`: passed.
- Bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed, 52 entries.
- `git diff --check`: passed, with CRLF conversion warnings only.
- Leak scan for the remote host/password in repository files excluding generated/runtime directories: passed.

## 2026-05-07 Iteration 70

Status: complete.

- Remote read-only smoke passed:
  - browser login succeeded,
  - AstrBot version `4.24.2`,
  - `/api/stat/version`, `/api/plugin/get`, and `/api/plugin/source/get-failed-plugins` returned HTTP 200,
  - remote plugin count was 30,
  - `astrbot_plugin_emotional_state` was installed, activated, version `1.0.0`, display name `多维情绪状态`,
  - failed plugin summary was empty,
  - WebUI plugin list showed the target plugin by display name,
  - remote `astrbot_plugin_livingmemory` was present.

- Main implementation commit created: `e86735b Add integrated self-state bus`.
- Final status commit records the completed iteration plan and progress log.
- Maintenance branches synced to the validated baseline:
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

Revolutionary Iterations 61-70 are complete.

## 2026-05-07 README Release Preparation

Status: complete.

- User requested a detailed release-ready README on `main`, using `Ayleovelle/astrbot_plugin_volcengine_asr` as the structural reference.
- Read the reference README from GitHub and compared it with the current local README.
- Subagent review concluded the local README already has the technical depth, but should behave more like a plugin release page: installation, minimal configuration, command table, public API, package/upload, remote verification, and release checklist should appear before the long theory sections.
- Checked repository publication prerequisites:
  - current branch is `main`,
  - no `origin` remote is configured,
  - `gh` CLI is not installed,
  - `GITHUB_TOKEN` and `GH_TOKEN` are not present.
- Planned change: keep the contract-tested API/config/remote-smoke strings, but reorganize and extend README for first-time installers and future repository release.
- Reworked `README.md` into a more release-oriented landing page:
  - added current version/compatibility/license summary,
  - changed quick start to Release zip, GitHub repository install, and manual-copy paths,
  - added command quick-reference table,
  - added a 30-second public API integration section for other plugins,
  - added package/upload/new GitHub repository publication checklist,
  - preserved the existing remote smoke, config, command, public API, and package contract text.
- Targeted README/config/command contract validation passed:
  - `py -3.13 -m unittest tests.test_remote_smoke_contract tests.test_config_schema_contract tests.test_command_tools -v`.
- Full local validation passed:
  - `py -3.13 -m unittest discover -s tests -v`: 208 tests passed.
  - `py -3.13 -m py_compile main.py emotion_engine.py psychological_screening.py humanlike_engine.py integrated_self.py moral_repair_engine.py prompts.py public_api.py scripts\build_literature_kb.py scripts\build_psychological_literature_kb.py scripts\build_humanlike_agent_literature_kb.py scripts\package_plugin.py`: passed.
  - `py -3.13 -m json.tool _conf_schema.json`: passed.
  - bundled Node `--check` for `scripts\plugin_zip_preflight.js`, `scripts\remote_smoke_playwright.js`, and `scripts\remote_install_upload_playwright.js`: passed.
  - `py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip`: passed.
  - bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed with 52 entries.
  - `git diff --check`: passed with CRLF conversion warnings only.
- GitHub repository creation status:
  - no `origin` remote is configured,
  - `gh` CLI is not installed,
  - `GITHUB_TOKEN` and `GH_TOKEN` are not present,
  - therefore remote repository creation is blocked until GitHub authentication is provided or an empty repository is created manually.

## 2026-05-07 GitHub Repository Creation Attempt

Status: in progress.

- User set `GITHUB_TOKEN` in the Windows User environment; the current shell process still did not inherit `$env:GITHUB_TOKEN`, but `[Environment]::GetEnvironmentVariable("GITHUB_TOKEN", "User")` returned a token without printing it.
- GitHub API `/user` succeeded and identified the account as `Ayleovelle`.
- Existing repository check for `Ayleovelle/astrbot_plugin_emotional_state` returned not found.
- Repository creation via `POST https://api.github.com/user/repos` failed with:
  - HTTP 403,
  - `Resource not accessible by personal access token`.
- Interpretation: the token is valid enough to read account identity, but does not have permission to create repositories. Next step requires either a token with repository creation permission or a manually created empty GitHub repository URL.
- User updated the token and retry succeeded:
  - created `Ayleovelle/astrbot_plugin_emotional_state`,
  - repository URL: `https://github.com/Ayleovelle/astrbot_plugin_emotional_state`,
  - clone URL: `https://github.com/Ayleovelle/astrbot_plugin_emotional_state.git`.
- Updated `metadata.yaml repo` and README repository install examples to the real GitHub URL.
- Validation after repository URL update:
  - `py -3.13 -m unittest tests.test_remote_smoke_contract tests.test_config_schema_contract tests.test_package_plugin -v`: 44 tests passed.
  - `py -3.13 -m py_compile main.py emotion_engine.py psychological_screening.py humanlike_engine.py integrated_self.py moral_repair_engine.py prompts.py public_api.py scripts\package_plugin.py`: passed.
  - `py -3.13 -m json.tool _conf_schema.json`: passed.
  - `git diff --check`: passed with CRLF conversion warnings only.
  - `py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip`: passed.
  - bundled Node `scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state`: passed with 52 entries.
- User clarified the initial repository release version should be `0.0.1-beta`, a prerelease version.
- Updated `metadata.yaml`, README badge/current-version text, README remote smoke example, and `docs/release_branch_sync_checklist.md` to `0.0.1-beta`.
- Re-ran version contract validation and rebuilt `dist\astrbot_plugin_emotional_state.zip`; zip preflight passed with 52 entries.

