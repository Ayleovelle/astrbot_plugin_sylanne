# 发布与分支同步清单

这份清单用于保护当前插件基线，避免功能、文档和发布包被拆散到未整理的分支里。

## 版本号规则

- 第一位版本号用于代码重构级或划世代级更新。
- 第二位版本号用于新增功能或较大功能整合。
- 第三位版本号用于 bug 修复和小范围兼容修正。
- 实验版本在版本号后追加 `exp` 后缀；实验能力稳定后，再按实际影响级别并入正式版本号。

## 提交前检查

1. 确认当前工作分支是 `main`。
2. 确认生成物已经被忽略：
   - `dist/`,
   - `output/`,
   - `__pycache__/`,
   - `*.py[cod]`,
   - `.pytest_cache/`,
   - 仅本地使用的文献知识库路径和知识库构建辅助文件。
3. 运行本地验证。优先使用 Codex 内置 Node；如果不存在，再回退到 `PATH` 中的 `node`：

```powershell
$node = "$HOME\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
$nodeModules = "$HOME\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules"
if (Test-Path $node) { $env:NODE_PATH = $nodeModules } else { $node = "node" }

py -3.13 -m unittest discover -s tests -v
py -3.13 -m py_compile main.py emotion_engine.py humanlike_engine.py lifelike_learning_engine.py personality_drift_engine.py realtime_chat_engine.py realtime_chat_input.py integrated_self.py moral_repair_engine.py fallibility_engine.py psychological_screening.py public_api.py prompts.py scripts\package_plugin.py
py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_sylanne.zip
& $node --check scripts\remote_smoke_playwright.js
& $node --check scripts\remote_cleanup_plugin_playwright.js
& $node --check scripts\remote_install_upload_playwright.js
& $node --check scripts\plugin_zip_preflight.js
& $node scripts\plugin_zip_preflight.js dist\astrbot_plugin_sylanne.zip astrbot_plugin_sylanne
git diff --check
```

4. 当远程验证环境可用时，运行远程只读烟测：

```powershell
$env:ASTRBOT_EXPECT_PLUGIN = "astrbot_plugin_sylanne"
$env:ASTRBOT_EXPECT_PLUGIN_VERSION = "2.4.3"
$env:ASTRBOT_EXPECT_PLUGIN_DISPLAY_NAME = "Sylanne"
& $node scripts\remote_smoke_playwright.js
```

需要一起查看 `expectedPluginChecks.ok`、`expectedFailedPlugin`、`failedPluginSummary.hasExpectedPluginFailure`、`containsExpectedPlugin`、`expectedPluginRuntime`、`expectedPluginVersionMatches`、`expectedPluginDisplayNameMatches` 和 `expectedPluginDrift`。远程 `failedPlugins` 里可能有无关插件失败；只有目标插件出现在失败记录里，才算目标插件失败，对应退出码 `5`。退出码 `7` 表示目标插件存在，但运行时版本与 `ASTRBOT_EXPECT_PLUGIN_VERSION` 不一致；退出码 `8` 表示运行时显示名与 `ASTRBOT_EXPECT_PLUGIN_DISPLAY_NAME` 不一致。

不要把真实凭据或服务器地址写入将被提交的文件。

## 提交顺序

先在 `main` 上提交完整且已验证的基线。提交内容包括：

- 核心运行时文件，
- 测试，
- 脚本，
- 文档，
- `CHANGELOG.md`，
- `LICENSE` 和 GPL 元数据，
- 持久化计划文件。

不要提交生成的 `dist/` 或 `output/` 产物。

## 分支同步顺序

当 `main` 保持干净后：

1. 将 `codex/complete-emotional-bot-plugin` 移动或合并到新的 `main` 基线。
2. 从干净基线同步维护分支：
   - `codex/emotion-core`,
   - `codex/astrbot-integration`,
   - `codex/public-api-memory`,
   - `codex/psychological-screening`,
   - `codex/literature-kbs`,
   - `codex/humanlike-agent-roadmap`,
   - `codex/tests-validation`,
   - `codex/release-packaging`,
   - `codex/docs-config`.
3. 每个分支都要完整到足以运行测试。不要为了让分支“更小”而删除无关模块。
4. 未来功能开发先放到对应维护分支，再合并回集成分支和 `main`。

## 远程上传规则

只有满足以下条件后，才运行 `scripts\remote_install_upload_playwright.js`：

- 发布包预检通过；
- 预检确认 zip 内包含运行时根文件 `__init__.py`、`main.py`、`emotion_engine.py`、`humanlike_engine.py`、`lifelike_learning_engine.py`、`personality_drift_engine.py`、`realtime_chat_engine.py`、`realtime_chat_input.py`、`integrated_self.py`、`moral_repair_engine.py`、`fallibility_engine.py`、`psychological_screening.py`、`prompts.py` 和 `public_api.py`；
- 预检确认 zip 内包含依赖声明 `requirements.txt`；
- 预检确认 zip 内包含 `CHANGELOG.md`，避免 AstrBot 更新日志页显示空状态；
- 预检确认 zip 内包含 `LICENSE`，且 `metadata.yaml` 声明 `license: GPL-3.0-or-later`；
- 预检确认 zip 内 `metadata.yaml` 的 `name:` 与 `ASTRBOT_EXPECT_PLUGIN` 匹配；
- zip 使用相对 POSIX 路径，且不包含不安全的 `.` / `..` 路径段；
- 任何 `uninstall-failed` 调用都只针对临时的 `plugin_upload_<plugin>` 失败上传目录，并且使用 `delete_config=false`、`delete_data=false`；
- `installOutcome="already_installed_no_overwrite"` 且 `overwriteAttempted=false` 只视为诊断成功：这表示正式插件目录已经存在且未被覆盖，因此严格版本烟测仍可能报告漂移；
- 已显式设置 `ASTRBOT_REMOTE_INSTALL_CONFIRM=1`；
- 目标服务器确实要接收一次新上传。

普通重复验证使用 `scripts\remote_smoke_playwright.js`。

## 远程清理规则

只有在破坏性重装测试前，才运行 `scripts\remote_cleanup_plugin_playwright.js`，并且必须使用：

```powershell
$env:ASTRBOT_EXPECT_PLUGIN = "astrbot_plugin_sylanne"
$env:ASTRBOT_REMOTE_CLEAN_CONFIRM = "astrbot_plugin_sylanne"
$env:ASTRBOT_REMOTE_CLEAN_FORMAL = "1"
$env:ASTRBOT_REMOTE_CLEAN_FAILED_UPLOAD = "1"
& $node scripts\remote_cleanup_plugin_playwright.js
```

清理脚本只允许操作 `astrbot_plugin_sylanne`。它只能删除精确匹配的正式插件记录，以及精确匹配的失败上传目录 `plugin_upload_astrbot_plugin_sylanne`，并始终使用 `delete_config=false` 和 `delete_data=false`。它不得删除 LivingMemory 或任何无关插件。
