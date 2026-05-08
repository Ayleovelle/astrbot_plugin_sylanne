# Release And Branch Sync Checklist

This checklist protects the current plugin baseline from being split across dirty branches.

## Before Committing

1. Confirm the working branch is `main`.
2. Confirm generated artifacts are ignored:
   - `dist/`,
   - `output/`,
   - `__pycache__/`,
   - `*.py[cod]`,
   - `.pytest_cache/`,
   - local-only literature KB paths and KB build helpers.
3. Run local validation. Use Codex bundled Node when it exists; otherwise fall back to `node` from `PATH`:

```powershell
$node = "$HOME\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
$nodeModules = "$HOME\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules"
if (Test-Path $node) { $env:NODE_PATH = $nodeModules } else { $node = "node" }

py -3.13 -m unittest discover -s tests -v
py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py lifelike_learning_engine.py personality_drift_engine.py integrated_self.py moral_repair_engine.py fallibility_engine.py psychological_screening.py public_api.py prompts.py scripts\package_plugin.py
py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip
& $node --check scripts\remote_smoke_playwright.js
& $node --check scripts\remote_cleanup_plugin_playwright.js
& $node --check scripts\remote_install_upload_playwright.js
& $node --check scripts\plugin_zip_preflight.js
& $node scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state
git diff --check
```

4. Run remote read-only smoke when remote validation is available:

```powershell
$env:ASTRBOT_EXPECT_PLUGIN = "astrbot_plugin_emotional_state"
$env:ASTRBOT_EXPECT_PLUGIN_VERSION = "0.1.0-beta"
$env:ASTRBOT_EXPECT_PLUGIN_DISPLAY_NAME = "多维情绪状态"
& $node scripts\remote_smoke_playwright.js
```

Read `expectedPluginChecks.ok`, `expectedFailedPlugin`, `failedPluginSummary.hasExpectedPluginFailure`, `containsExpectedPlugin`, `expectedPluginRuntime`, `expectedPluginVersionMatches`, `expectedPluginDisplayNameMatches`, and `expectedPluginDrift` together. Remote `failedPlugins` may contain unrelated plugin failures; only the expected plugin in failed records is a target-plugin failure and exit code `5`. Exit code `7` means the expected plugin exists but its runtime version differs from `ASTRBOT_EXPECT_PLUGIN_VERSION`; exit code `8` means the runtime display name differs from `ASTRBOT_EXPECT_PLUGIN_DISPLAY_NAME`.

Do not put real credentials or server addresses in committed files.

## Commit Order

Commit the full validated baseline on `main` first. Include:

- core runtime files,
- tests,
- scripts,
- docs,
- `LICENSE` and GPL metadata,
- persistent planning files.

Do not commit generated `dist/` or `output/` artifacts.

## Branch Sync Order

After `main` is clean:

1. Move or merge `codex/complete-emotional-bot-plugin` to the new `main` baseline.
2. Sync maintenance branches from the clean baseline:
   - `codex/emotion-core`,
   - `codex/astrbot-integration`,
   - `codex/public-api-memory`,
   - `codex/psychological-screening`,
   - `codex/literature-kbs`,
   - `codex/humanlike-agent-roadmap`,
   - `codex/tests-validation`,
   - `codex/release-packaging`,
   - `codex/docs-config`.
3. Keep branches complete enough to run tests. Do not delete unrelated modules to make a branch "smaller".
4. For future feature work, develop on the relevant maintenance branch, then merge back to the integration branch and `main`.

## Remote Upload Rule

Only run `scripts\remote_install_upload_playwright.js` after:

- the package preflight passes,
- the preflight confirms the zip contains the runtime root files `__init__.py`, `main.py`, `emotion_engine.py`, `humanlike_engine.py`, `lifelike_learning_engine.py`, `personality_drift_engine.py`, `integrated_self.py`, `moral_repair_engine.py`, `fallibility_engine.py`, `psychological_screening.py`, `prompts.py`, and `public_api.py`,
- the preflight confirms the zip contains the dependency declaration `requirements.txt`,
- the preflight confirms the zip contains `LICENSE` and `metadata.yaml` declares `license: GPL-3.0-or-later`,
- the preflight confirms zip `metadata.yaml` `name:` matches `ASTRBOT_EXPECT_PLUGIN`,
- the zip uses relative POSIX paths and contains no unsafe `.` / `..` path segments,
- any `uninstall-failed` call is only for the temporary `plugin_upload_<plugin>` failed-upload directory, with `delete_config=false` and `delete_data=false`,
- `installOutcome="already_installed_no_overwrite"` with `overwriteAttempted=false` is treated as diagnostic success only: it means the formal plugin directory already existed and was not overwritten, so strict version smoke may still report drift,
- `ASTRBOT_REMOTE_INSTALL_CONFIRM=1` is explicitly set,
- the target server is intended to receive a new upload.

Use `scripts\remote_smoke_playwright.js` for ordinary repeated validation.

## Remote Cleanup Rule

Only run `scripts\remote_cleanup_plugin_playwright.js` immediately before a destructive reinstall test, and only with:

```powershell
$env:ASTRBOT_EXPECT_PLUGIN = "astrbot_plugin_emotional_state"
$env:ASTRBOT_REMOTE_CLEAN_CONFIRM = "astrbot_plugin_emotional_state"
$env:ASTRBOT_REMOTE_CLEAN_FORMAL = "1"
$env:ASTRBOT_REMOTE_CLEAN_FAILED_UPLOAD = "1"
& $node scripts\remote_cleanup_plugin_playwright.js
```

The cleanup script is allowlisted to `astrbot_plugin_emotional_state`. It may delete only the exact formal plugin record and the exact failed-upload directory `plugin_upload_astrbot_plugin_emotional_state`, always with `delete_config=false` and `delete_data=false`. It must not delete LivingMemory or unrelated plugins.
