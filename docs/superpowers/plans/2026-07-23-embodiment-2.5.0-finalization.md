# Embodiment 2.5.0 Finalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the checked-in `2.5.0-grey.7` candidate into an organization-facing `Sylanne-Embodiment 2.5.0` stable candidate, rebuild and verify the stable artifact, and update Draft PR #65 without merging or publishing.

**Architecture:** The checked-in source identity becomes stable while the existing dual-channel packager remains intact. Stable builds use checked-in metadata and generate `V3_SHADOW_ENABLED=False`; grey coverage is preserved through temporary metadata overrides. Public documentation and metadata use the 2718 Labs organization voice, while historical grey records remain unchanged.

**Tech Stack:** Python 3.10–3.13, pytest, Ruff, AstrBot plugin metadata, deterministic ZIP packaging, GitHub Actions, GitHub CLI.

---

## Scope boundary

This plan finishes the approved release-finalization work only. The monitoring-page frontend/backend disconnection shown in the user screenshot is a separate bug-fix phase and starts only after Task 8 completes.

## File map

- Modify: `tests/integration/test_v3_astrbot_v4265_hook_order.py` — keep pure hook simulations runnable without AstrBot installed.
- Modify: `tests/test_release_ci_contract.py` — make checked-in `2.5.0` the stable identity baseline.
- Modify: `tests/test_v3_package_channel.py` — preserve both channels while using temporary grey metadata.
- Modify: `metadata.yaml` — stable version and 2718lab organization metadata.
- Modify: `main.py` — stable runtime identity and neutral fallback registration text.
- Modify: `CHANGELOG.md` — add the official 2.5.0 entry while retaining all grey history.
- Modify: `README.md` — replace personal narrative with organization-level product documentation.
- Modify: `docs/superpowers/specs/2026-07-23-embodiment-2.5.0-finalization-design.md` — align the machine author field with the 2718lab convention.
- Modify: `astrbot_plugin_sylanne.zip` — tracked stable installation artifact generated from a clean source commit.
- Create locally, ignored: `dist/astrbot_plugin_sylanne-2.5.0.zip` and checksum sidecar.
- External metadata only: Draft PR #65 title/body; no merge, tag, release, or deployment.

### Task 1: Keep CI tests collectable without AstrBot installed

**Files:**
- Modify: `tests/integration/test_v3_astrbot_v4265_hook_order.py:3-9,38-42,182-205,296`
- Test: `tests/integration/test_v3_astrbot_v4265_hook_order.py`

- [ ] **Step 1: Reproduce the collection failure in an environment without AstrBot**

Run:

```powershell
$env:TEMP='D:\bun\tmp\codex\sylanne-v3-grey-takeover\ci-optional-astrbot'
$env:TMP=$env:TEMP
$env:TMPDIR=$env:TEMP
& 'D:\bun\tmp\codex\sylanne-v3-grey-takeover\venv-py312\Scripts\python.exe' -m pytest tests/integration/test_v3_astrbot_v4265_hook_order.py -q -p no:cacheprovider
```

Expected before the fix: collection exits with code 2 and `ModuleNotFoundError: No module named 'astrbot'`.

- [ ] **Step 2: Make only the pinned-source checks depend on AstrBot**

Replace the unconditional import with:

```python
try:
    import astrbot
except ModuleNotFoundError as exc:
    if exc.name != "astrbot":
        raise
    astrbot = None  # type: ignore[assignment]

import pytest
```

Change `_astrbot_root()` to fail clearly only when a source-reading test reaches it:

```python
def _astrbot_root() -> Path:
    configured = os.environ.get("ASTRBOT_SRC")
    if configured:
        root = Path(configured)
    else:
        assert astrbot is not None, "AstrBot source is unavailable"
        root = Path(astrbot.__file__).resolve().parent
    assert root.is_dir(), f"ASTRBOT_SRC is not a directory: {root}"
    return root
```

Start the pinned-source probe with:

```python
def _pinned_astrbot_source_present() -> bool:
    if astrbot is None:
        return False
    if getattr(astrbot, "__version__", None) != ASTRBOT_VERSION:
        return False
```

Add `@_requires_pinned_astrbot` immediately above:

```python
def test_after_message_sent_is_attempt_evidence_not_send_success() -> None:
```

Keep the 13-case hook matrix and `test_real_plugin_lock_delegates_to_session_context_production_lock` unmarked so they still execute.

- [ ] **Step 3: Verify the optional-dependency behavior**

Run the Step 1 command again.

Expected without AstrBot:

```text
14 passed, 3 skipped
```

- [ ] **Step 4: Lint and commit the isolated CI fix**

Run:

```powershell
ruff check tests/integration/test_v3_astrbot_v4265_hook_order.py
git add -- tests/integration/test_v3_astrbot_v4265_hook_order.py
git commit -m "test(ci): keep hook simulations runnable without AstrBot"
```

Expected: Ruff prints `All checks passed!`; the commit contains only the integration test.

### Task 2: Change the release-contract tests to a stable checked-in baseline

**Files:**
- Modify: `tests/test_release_ci_contract.py:18-32,204-290`
- Modify: `tests/test_v3_package_channel.py:54-66,120-128,227-301,389-590`
- Test: both files above

- [ ] **Step 1: Rewrite the release identity expectations**

Use these constants and defaults:

```python
GREY_OVERRIDE_VERSION = "2.5.0-grey.7"
EXPECTED_STABLE_VERSION = "2.5.0"


def _main_source(
    *,
    plugin_version: str = EXPECTED_STABLE_VERSION,
    register_version: str = EXPECTED_STABLE_VERSION,
    extra_module_source: str = "",
) -> bytes:
```

Rename the checked-in identity test to:

```python
def test_checked_in_release_identity_is_stable_and_consistent() -> None:
    metadata_version = package_plugin._read_metadata_version((ROOT / "metadata.yaml").read_bytes())
    main_tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))

    assert metadata_version == EXPECTED_STABLE_VERSION
    assert _module_string_assignment(main_tree, "PLUGIN_VERSION") == metadata_version
    assert _register_version(main_tree) == metadata_version
```

Use `EXPECTED_STABLE_VERSION` as the valid side of the metadata/plugin/register drift tests and `GREY_OVERRIDE_VERSION` as the mismatching side. In the second-module-write parametrization, use stable `2.5.0` strings so the extra write is the only reason for rejection.

Replace the synthetic stable override test with a grey override test:

```python
def test_grey_override_rewrites_all_packaged_release_identities(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir()
    checked_in_metadata = plugin_root / "metadata.yaml"
    checked_in_metadata.write_text(f'version: "{EXPECTED_STABLE_VERSION}"\n', encoding="utf-8")
    main = plugin_root / "main.py"
    main.write_bytes(_main_source())
    override = tmp_path / "grey-metadata.yaml"
    override.write_text(f'version: "{GREY_OVERRIDE_VERSION}"\n', encoding="utf-8")

    tracked = {checked_in_metadata.resolve(), main.resolve()}
    monkeypatch.setattr(package_plugin, "ROOT", plugin_root)
    monkeypatch.setattr(package_plugin, "_tracked_files", lambda: tracked)
    monkeypatch.setattr(package_plugin, "_paths_differing_from_head", lambda: set())
    monkeypatch.setattr(package_plugin, "_head_commit", lambda: "0" * 40)

    archive = package_plugin.build_package(
        tmp_path / "plugin.zip",
        channel="grey",
        metadata_override=override,
    )
```

Keep its existing ZIP reads, but assert the three packaged identities equal `GREY_OVERRIDE_VERSION`.

- [ ] **Step 2: Invert the package-channel fixtures without deleting grey coverage**

Replace `_stable_metadata` with:

```python
def _grey_metadata(tmp_path: Path) -> Path:
    """A temporary metadata copy whose version is a grey release version."""
    source = (package_plugin.ROOT / "metadata.yaml").read_text(encoding="utf-8")
    patched = re.sub(
        r'(?m)^version:\s*.*$',
        'version: "2.5.0-grey.7"',
        source,
        count=1,
    )
    assert 'version: "2.5.0-grey.7"' in patched
    target = tmp_path / "metadata.yaml"
    target.write_text(patched, encoding="utf-8")
    return target
```

Use:

```python
@pytest.fixture(scope="module")
def grey_archive(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("grey")
    return _build(root, "grey", metadata=_grey_metadata(root))


@pytest.fixture(scope="module")
def stable_archive(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _build(tmp_path_factory.mktemp("stable"), "stable")
```

Replace the channel agreement tests with:

```python
def test_grey_packaging_rejects_checked_in_stable_metadata(tmp_path: Path) -> None:
    version = package_plugin._read_metadata_version(
        (package_plugin.ROOT / "metadata.yaml").read_bytes()
    )
    assert version == "2.5.0"
    with pytest.raises(RuntimeError, match="grey"):
        _build(tmp_path, "grey")


def test_stable_packaging_rejects_grey_metadata(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="stable"):
        _build(tmp_path, "stable", metadata=_grey_metadata(tmp_path))
```

Make the temporary-version test read `grey_archive` and assert `2.5.0-grey.7`. Make the manifest primary contract read `stable_archive` and assert:

```python
assert manifest["channel"] == "stable"
assert manifest["metadata_version"] == "2.5.0"
```

For channel-neutral tests that currently call `_build(..., "grey")` without metadata, use checked-in `stable`. This applies to deterministic repeated builds, HEAD cleanliness/refusal, duplicate/case-fold refusal, v3 untracked-source refusal, engine runtime-file refusal, and the untracked-probe test. For the generated-flag mismatch test, request stable but inject:

```python
b'V3_SHADOW_ENABLED: bool = True\nBUILD_CHANNEL: str = "grey"\n'
```

For the dirty-override test, request grey with `metadata=_grey_metadata(tmp_path)`. Keep all dual-channel parametrized tests.

- [ ] **Step 3: Run the new tests to prove the current grey source fails**

Run:

```powershell
& 'D:\bun\tmp\codex\sylanne-v3-grey-takeover\venv-py312\Scripts\python.exe' -m pytest tests/test_release_ci_contract.py::test_checked_in_release_identity_is_stable_and_consistent tests/test_v3_package_channel.py::test_grey_packaging_rejects_checked_in_stable_metadata -q -p no:cacheprovider
```

Expected before Task 3: both tests fail because checked-in metadata is still `2.5.0-grey.7`.

### Task 3: Set the official 2.5.0 source identity and changelog

**Files:**
- Modify: `metadata.yaml:1-8`
- Modify: `main.py:1-8,241,1180-1186`
- Modify: `CHANGELOG.md:5`
- Modify: `docs/superpowers/specs/2026-07-23-embodiment-2.5.0-finalization-design.md`
- Test: `tests/test_release_ci_contract.py`

- [ ] **Step 1: Replace the public metadata**

Use:

```yaml
desc: "面向 AstrBot 的长期记忆、关系状态建模与即时聊天插件，提供情感状态计算、认知编排、生活模拟、主动消息及 WebUI 观测能力；高风险可选功能默认关闭。"
short_desc: "Sylanne-Embodiment 2.5.0 — 长期记忆、关系状态建模与即时聊天"
version: "2.5.0"
author: 2718lab
```

Keep `name`, `display_name`, `license`, compatibility fields, and the current `Ayleovelle/astrbot_plugin_sylanne` repository URL.

- [ ] **Step 2: Replace all active main-module release identity fields**

Use:

```python
PLUGIN_VERSION = "2.5.0"
```

Use these `@register` values:

```python
@register(
    "astrbot_plugin_sylanne",
    "2718 Labs",
    "Long-term memory, relational state modelling, and real-time chat for AstrBot.",
    "2.5.0",
    "https://github.com/Ayleovelle/astrbot_plugin_sylanne",
)
```

In the module docstring, replace “情感身体运行时” with “长期对话状态与行为运行时”. Do not change `source_channel`; it already derives stable from the version.

- [ ] **Step 3: Add the stable changelog entry above grey.7**

Insert:

```markdown
## [Embodiment-2.5.0] - 2026-07-23

本版本将 2.5.0 grey 系列中完成验证的改动收口到 stable 通道。grey.1 至 grey.7 的测试与修订记录保留在下方历史条目中。

### 新增

- 跨群记忆、QQ 空间说说和即时聊天接管作为可选能力提供，默认保持关闭，由部署者按需逐项启用。
- 回复分段支持由主回复模型标注语义边界，不额外发起独立 LLM 请求；标记异常或结构化内容不适合分段时回退为整段发送。
- 常用 LLM 配置收口为聊天模型、共享辅助文本模型和 Embedding 模型，独立 Provider 保留为高级覆盖。

### 修复

- 修复中文长期记忆整理低命中、AstrBot 4.26 事件钩子参数兼容、覆盖安装热重载，以及部分第三方 Agent 对话历史缺失等问题。
- 完善分段发送的取消、发送失败与历史保存回退，避免未发送正文丢失或会话记录不完整。

### 发布边界

- 安装包使用 `stable` 构建通道，版本身份统一为 `2.5.0`。
- v3 影子认知路径在 stable 包中保持关闭，不参与用户请求或状态写入。
- v3 的 G3/G4 结论仍需真实灰测数据，本版本不声明 v3 已具备稳定版启用条件。
```

Do not edit any existing grey changelog entry.

- [ ] **Step 4: Verify the identity test turns green**

Run:

```powershell
& 'D:\bun\tmp\codex\sylanne-v3-grey-takeover\venv-py312\Scripts\python.exe' -m pytest tests/test_release_ci_contract.py::test_checked_in_release_identity_is_stable_and_consistent -q -p no:cacheprovider
```

Expected: `1 passed`.

### Task 4: Replace personal README copy with the 2718 Labs public surface

**Files:**
- Modify: `README.md:1-132,447-493,589-646`
- Test: documentation searches and release links

- [ ] **Step 1: Replace the README opening**

Add `# Sylanne-Embodiment`, change the Socialify description to “面向 AstrBot 的长期记忆、关系状态建模与即时聊天插件”, and change the version badge to stable `2.5.0`. Remove the Moe Counter.

Replace the existing declaration, audience section, mascot introduction, and complete “写在前面的话” with:

```markdown
> `astrbot_plugin_sylanne` 是面向 AstrBot 的长期记忆、关系状态建模与即时聊天插件，提供情感状态计算、认知编排、生活模拟、主动消息和 WebUI 观测能力。

## 项目概览

Sylanne-Embodiment 将对话事件映射为可持久化的记忆、关系与表达状态，并通过 AstrBot 的 LLM 请求与响应钩子参与上下文构建、回复调度和状态更新。底层采用 **Scar Algebra（伤痕代数）**、**Void Calculus（空洞微积分）** 和 **Relational Sheaf Theory（关系层论）** 等形式化模型。

项目适用于需要长期对话状态、关系建模、可配置即时聊天体验，或希望研究 agent 状态计算与记忆机制的 AstrBot 部署和开发场景。

> [!IMPORTANT]
> 文档中的“情绪”“人格”“伤痕”“空洞”等均为软件状态模型术语，不代表真实意识、主观体验或医学意义上的心理状态。跨群记忆、QQ 空间说说和即时聊天接管等高风险可选能力默认关闭，应按部署需要逐项启用并验证。
```

- [ ] **Step 2: Replace the personal “core ideas” surface**

Replace `## 核心理念` through the block immediately before `## 认知架构总览` with:

```markdown
## 设计目标

### 可持久化的关系状态

系统将长期对话中的事件、关系变化和未完成表达编码为可持久化状态。状态更新由明确的算子和边界约束完成，重启后从持久化数据恢复。

### 参数化的行为调度

人格参数、关系状态、上下文信号和安全门控共同影响表达阈值、主动交互、记忆召回与回复节奏。各项能力均通过配置和运行时边界控制。

### 可审计的反馈闭环

事件输入、状态更新、行为决策与反馈结果形成可追踪闭环。关键状态、路由与门控结果可通过日志和 WebUI 观测。

### 分层适应

系统包含本地反应式更新、低频反思与持久化巩固路径。涉及 LLM 的后台能力需要显式配置 Provider；未配置时保持关闭或降级。

## 主要能力

- **长期记忆**：分层保存、召回和整理对话信息，并提供跨重启持久化。
- **关系状态建模**：按会话与身份维护有界状态；跨群能力默认关闭并受隐私门控。
- **语义分段**：由主回复模型标注自然边界，异常时安全回退为整段发送。
- **即时聊天调度**：支持分段发送、打字节奏、中断恢复与历史保存解耦，默认关闭。
- **主动交互与生活模拟**：使用独立开关和 Provider 路由，默认关闭。
- **QQ 空间发布**：包含内容净化、频率限制和审核档位，默认关闭。
- **用户控制**：暂停、重置、退出和敏感能力授权由硬门控保护。
- **WebUI 观测**：展示运行状态、记忆、关系和调度信息，便于部署诊断。
```

- [ ] **Step 3: Update version highlights, installation, and configuration**

Replace the 2.3.0 highlights with:

```markdown
## Embodiment-2.5.0 版本要点

- **模型原生智能分段**：由同一次主回复模型标注语义边界，不新增独立 LLM 请求，并在异常标记或结构化内容场景回退为整段发送。
- **LLM 配置收口**：常用模型配置集中到聊天模型、共享辅助文本模型和 Embedding 模型；独立 Provider 作为高级覆盖保留。
- **可选能力默认关闭**：跨群记忆、QQ 空间说说和即时聊天接管由部署者逐项启用。
- **stable 构建边界**：正式安装包不激活 v3 影子路径；相关 G3/G4 结论仍需真实灰测数据。

完整变更与 grey 修订过程见 [CHANGELOG.md](CHANGELOG.md)。未来发布 tag 为 `Embodiment-2.5.0`。
```

Use this quick start:

```markdown
1. 从 [Embodiment-2.5.0 Release](https://github.com/Ayleovelle/astrbot_plugin_sylanne/releases/tag/Embodiment-2.5.0) 下载 `astrbot_plugin_sylanne-2.5.0.zip`。
2. 若使用通用文件名 `astrbot_plugin_sylanne.zip`，确认包内 `metadata.yaml` 的版本为 `2.5.0`。
3. 在 AstrBot 管理面板上传并启用插件。
4. 保持高风险可选能力的默认关闭状态，先验证基础聊天与历史记录。
5. 按部署需要逐项启用即时聊天、跨群记忆、生活模拟或 QQ 空间能力，并观察日志与 WebUI 状态。
```

Rename the configuration section to `### 常用配置`, state that `_conf_schema.json` is the complete source of truth, and document these real defaults: v2core `true`; WebUI `false`; shared auxiliary Provider empty; embedding disabled; realtime disabled; interception disabled; life simulation disabled; cross-session mode `off`; QZone disabled.

Replace the absolute latency claim with:

```markdown
> 计算层、agent 编排和反应式学习主要在本地执行；生活模拟和反思等功能会调用配置的 LLM Provider。实际延迟与资源占用取决于模型、平台适配器、部署环境和启用功能，建议在生产环境逐项开启并监测。
```

- [ ] **Step 4: Standardize research, contribution, and footer text**

Replace the novelty paragraph with:

```markdown
> **相关工作：** Mopgar（2026.03）和 Hu & Rong（2026.05）讨论了后果表征与 agent 躯体化问题。本项目将形式化状态算子、缺席动力学与关系拓扑组合到同一插件架构；具体定义、假设与实验边界见 `theory/` 目录与论文。
```

Use `项目交流与反馈：QQ群 **176427647**。`

Rename `星星记录表` to `Star History`, use `欢迎通过 Star、Issue 和 Pull Request 关注或参与项目维护。`, keep the chart, and replace the footer with:

```html
<p align="center"><sub>Maintained by 2718 Labs.</sub></p>
```

- [ ] **Step 5: Prove personal and stale active copy is gone**

Run:

```powershell
git grep -n -E "2\.5\.0-grey\.7|写在前面的话|寄不出去|她在收|给孩子点一颗星|Made with|无可感知的额外延迟|据我们所知还没有人做过" -- README.md metadata.yaml main.py
```

Expected: no matches and exit code 1.

Run:

```powershell
git grep -n -E "version-2\.5\.0|Embodiment-2\.5\.0|astrbot_plugin_sylanne-2\.5\.0\.zip|Maintained by 2718 Labs" -- README.md CHANGELOG.md
```

Expected: matches for the stable badge, release/tag, package, changelog, and organization footer.

### Task 5: Commit a clean stable source tree and run the package contracts

**Files:**
- Stage the text/test files from Tasks 2–4 plus the corrected design spec.
- Do not stage `astrbot_plugin_sylanne.zip` yet.

- [ ] **Step 1: Check the exact source commit scope**

Run:

```powershell
git status --short
git diff --check
git diff --stat
```

Expected tracked changes: release tests, metadata, main, changelog, README, and the design spec only. Existing untracked workspace files remain unstaged.

- [ ] **Step 2: Run pre-package validation that does not require a clean source tree**

Run:

```powershell
ruff check main.py tests/test_release_ci_contract.py tests/test_v3_package_channel.py
& 'D:\bun\tmp\codex\sylanne-v3-grey-takeover\venv-py312\Scripts\python.exe' -m pytest tests/test_release_ci_contract.py -q -p no:cacheprovider
```

Expected: Ruff passes; all release contract tests pass.

- [ ] **Step 3: Commit the source identity**

Run:

```powershell
git add -- metadata.yaml main.py CHANGELOG.md README.md tests/test_release_ci_contract.py tests/test_v3_package_channel.py
git add -f -- docs/superpowers/specs/2026-07-23-embodiment-2.5.0-finalization-design.md docs/superpowers/plans/2026-07-23-embodiment-2.5.0-finalization.md
git commit -m "chore(release): prepare Embodiment 2.5.0"
```

Expected: one source commit; tracked worktree is clean.

- [ ] **Step 4: Run the clean-tree package-channel tests**

Run:

```powershell
$env:TEMP='D:\bun\tmp\codex\sylanne-v3-grey-takeover\pytest-stable-package'
$env:TMP=$env:TEMP
$env:TMPDIR=$env:TEMP
$env:PYTHONPYCACHEPREFIX='D:\bun\tmp\codex\sylanne-v3-grey-takeover\pycache-stable-package'
& 'D:\bun\tmp\codex\sylanne-v3-grey-takeover\venv-py312\Scripts\python.exe' -m pytest tests/test_v3_package_channel.py -q -p no:cacheprovider
```

Expected: `38 passed`.

### Task 6: Build, verify, and commit the stable artifact

**Files:**
- Create ignored: `dist/astrbot_plugin_sylanne-2.5.0.zip`
- Create ignored: `dist/astrbot_plugin_sylanne-2.5.0.zip.sha256`
- Modify generated binary: `astrbot_plugin_sylanne.zip`

- [ ] **Step 1: Build from the clean source commit**

Run:

```powershell
$env:TEMP='D:\bun\tmp\codex\sylanne-v3-grey-takeover\stable-build'
$env:TMP=$env:TEMP
$env:TMPDIR=$env:TEMP
& 'D:\bun\tmp\codex\sylanne-v3-grey-takeover\venv-py312\Scripts\python.exe' scripts/package_plugin.py --channel stable --output dist/astrbot_plugin_sylanne-2.5.0.zip
```

Expected: the ZIP and adjacent SHA-256 sidecar are created.

- [ ] **Step 2: Verify manifest, identity, flags, contents, and checksum independently**

Run:

```powershell
tar.exe -xOf 'dist\astrbot_plugin_sylanne-2.5.0.zip' 'astrbot_plugin_sylanne/sylanne_build_manifest.json'
tar.exe -xOf 'dist\astrbot_plugin_sylanne-2.5.0.zip' 'astrbot_plugin_sylanne/metadata.yaml' | Select-String -Pattern '^version:'
tar.exe -xOf 'dist\astrbot_plugin_sylanne-2.5.0.zip' 'astrbot_plugin_sylanne/main.py' | Select-String -Pattern 'PLUGIN_VERSION|^@register' -Context 0,6
tar.exe -xOf 'dist\astrbot_plugin_sylanne-2.5.0.zip' 'astrbot_plugin_sylanne/sylanne_alpha/v3bridge/build_flags.py'
Get-FileHash -Algorithm SHA256 -LiteralPath 'dist\astrbot_plugin_sylanne-2.5.0.zip'
```

Expected:

- manifest `channel` is `stable`;
- manifest `metadata_version` is `2.5.0`;
- manifest commit equals the clean source commit;
- metadata, `PLUGIN_VERSION`, and `@register` all equal `2.5.0`;
- generated flags are `V3_SHADOW_ENABLED=False` and `BUILD_CHANNEL="stable"`;
- computed ZIP SHA equals the sidecar;
- ZIP remains below the 16 MB market limit.

- [ ] **Step 3: Refresh the tracked generic package and commit it separately**

Run:

```powershell
Copy-Item -LiteralPath 'G:\Sylanne-next\dist\astrbot_plugin_sylanne-2.5.0.zip' -Destination 'G:\Sylanne-next\astrbot_plugin_sylanne.zip' -Force
git add -- astrbot_plugin_sylanne.zip
git commit -m "build(release): refresh stable 2.5.0 package"
```

Expected: only the tracked generic ZIP is committed. The manifest intentionally references the preceding clean source commit, avoiding a self-referential artifact commit.

### Task 7: Run release-quality verification and adversarial review

**Files:**
- Read all changed files and generated artifact.
- Modify only if verification or red-team findings are accepted.

- [ ] **Step 1: Run the focused release and CI regression**

Run:

```powershell
& 'D:\bun\tmp\codex\sylanne-v3-grey-takeover\venv-py312\Scripts\python.exe' -m pytest tests/test_release_ci_contract.py tests/test_package_plugin.py tests/test_v3_package_channel.py tests/integration/test_v3_astrbot_v4265_hook_order.py -q -p no:cacheprovider
```

Expected baseline after the planned changes: `72 passed, 3 skipped` (the exact count may increase if existing parametrization changes, but no failure is allowed).

- [ ] **Step 2: Run the full repository suite**

Run:

```powershell
$env:TEMP='D:\bun\tmp\codex\sylanne-v3-grey-takeover\pytest-stable-full'
$env:TMP=$env:TEMP
$env:TMPDIR=$env:TEMP
$env:PYTHONPYCACHEPREFIX='D:\bun\tmp\codex\sylanne-v3-grey-takeover\pycache-stable-full'
& 'D:\bun\tmp\codex\sylanne-v3-grey-takeover\venv-py312\Scripts\python.exe' -m pytest tests -q -p no:cacheprovider
```

Expected: no failures. Record the actual pass/skip count; do not reuse the previous grey.7 count.

- [ ] **Step 3: Run lint and both 2718lab release validators**

Run:

```powershell
ruff check .
& 'D:\bun\tmp\codex\sylanne-v3-grey-takeover\venv-py312\Scripts\python.exe' 'C:\Users\pidan\.codex\plugins\cache\pidan-local-plugins\2718lab-devkit\0.1.0\skills\astrbot-plugin-dev\scripts\validate_plugin.py' 'G:\Sylanne-next'
& 'D:\bun\tmp\codex\sylanne-v3-grey-takeover\venv-py312\Scripts\python.exe' 'C:\Users\pidan\.codex\plugins\cache\pidan-local-plugins\2718lab-devkit\0.1.0\skills\oss-repo-ops\scripts\check_release.py' 'G:\Sylanne-next'
git diff --check github/main...HEAD
```

Expected: Ruff and diff checks pass; both 2718lab validators report zero errors. Review every warning manually.

- [ ] **Step 4: Dispatch an independent red-team and verification pass**

The red-team must answer:

1. Can any active public field still report grey.7?
2. Can the stable ZIP activate v3?
3. Can merging the Draft accidentally publish before explicit approval?
4. Can README users be instructed to enable a high-risk option by default?
5. Are any historical grey records incorrectly rewritten?
6. Does the package manifest point to the exact clean source commit?
7. Are secrets, local files, or ignored workspace artifacts included?
8. Can the optional AstrBot import hide a broken AstrBot transitive dependency?
9. Does the organization rename break the current repository update URL?

Resolve every accepted finding, rerun affected commands, and report any remaining item as `【红队-遗留】`.

### Task 8: Push and update Draft PR #65 without publishing

**Files:**
- No new repository files unless verification fixes are required.
- External: remote feature branch and PR metadata only.

- [ ] **Step 1: Confirm final local and remote scope**

Run:

```powershell
git status --short --branch
git log --oneline github/main..HEAD
gh pr view 65 --repo Ayleovelle/astrbot_plugin_sylanne --json state,isDraft,baseRefName,headRefName,url
```

Expected: tracked worktree clean; base `main`; head `feat/embodiment-2.5.0`; PR state `OPEN`; `isDraft=true`.

- [ ] **Step 2: Push the feature branch only**

Run:

```powershell
git push github feat/embodiment-2.5.0
```

Do not push a tag and do not push to `main`.

- [ ] **Step 3: Update the Draft PR title and body**

Set the title to:

```text
release: prepare Sylanne-Embodiment 2.5.0
```

The body must include:

- stable version and artifact SHA-256/payload digest;
- actual focused/full test counts from Task 7;
- `V3_SHADOW_ENABLED=False`;
- G3/G4 remain pending real grey data;
- merge will trigger `release.yml` and therefore requires separate explicit approval;
- this task created no tag, GitHub Release, deployment, or merge.

- [ ] **Step 4: Re-verify the remote safety boundary**

Run:

```powershell
gh pr view 65 --repo Ayleovelle/astrbot_plugin_sylanne --json title,state,isDraft,url,baseRefName,headRefName,headRefOid,mergeStateStatus
```

Expected: PR remains `OPEN` and Draft. Stop without merging, tagging, releasing, or deploying.

## Follow-up phase

After Task 8, start a separate systematic-debugging workflow for the monitoring UI screenshot. It must map every displayed frontend field to its backend response source, reproduce missing/defaulted values, add contract tests, and then repair data wiring. Do not bundle that bug fix into the release-finalization commits above.
