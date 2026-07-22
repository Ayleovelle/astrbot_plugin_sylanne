# Sylanne-Embodiment 2.5.0 定板设计

日期：2026-07-23

## 目标

将当前 `2.5.0-grey.7` 灰测候选收口为组织级正式候选 `Sylanne-Embodiment 2.5.0`：

- 统一源码、元数据、README、CHANGELOG、测试与包体的正式版本身份。
- 将公共文案从个人化、拟人化叙事改为 2718 Labs 的工程化表达。
- 生成 stable 通道安装包，并确保 v3 影子路径在正式包中保持关闭。
- 修复阻塞 PR 验证的测试环境兼容问题。
- 更新现有 Draft PR，但不转 Ready、不合并、不创建 Tag 或 GitHub Release。

## 方案比较

### 方案 A：只改版本号

仅将 `grey.7` 改为 `2.5.0` 并重新打包。

优点是改动最小；缺点是 README 与 metadata 仍保留个人经历、情书式叙事和不可验证的宣传语，不符合 2718 Labs 的组织级发布标准。

### 方案 B：只清理 README 顶部

除版本身份外，删除“写在前面的话”和顶部个人化介绍。

优点是能消除最明显的个人化内容；缺点是 README 下部仍存在过时版本摘要、绝对性能声明、不准确的“完整配置参考”和个人化页脚，公开界面仍不统一。

### 方案 C：公共发布面完整标准化（采用）

统一正式版身份，并标准化 README、metadata、CHANGELOG、包体、测试与 PR；保留历史 grey 记录和内部设计文档原貌。

该方案改动范围略大，但能形成一致、可验证、可维护的组织级发布面，符合“未来由 2718 Labs 维护”的方向。

## 正式版身份

| 项目 | 定板值 |
| --- | --- |
| 产品版本 | `2.5.0` |
| 产品线名称 | `Sylanne-Embodiment 2.5.0` |
| Tag（未来合并发布时） | `Embodiment-2.5.0` |
| Release 包名 | `astrbot_plugin_sylanne-2.5.0.zip` |
| 仓库根通用包 | `astrbot_plugin_sylanne.zip` |
| 构建通道 | `stable` |
| stable 包内 v3 影子开关 | `False` |
| 维护主体 | `2718 Labs` |

当前仓库仍位于 `Ayleovelle/astrbot_plugin_sylanne`。本次不迁移仓库、不批量改写 URL；仓库迁移到 2718 Labs 后再单独更新链接。

## README 标准化

### 删除

- 完整删除“写在前面的话”及其中的个人经历、文学引用、模型评价、情书和寄信叙事。
- 删除“燃烧”“留疤”“她在收信”等角色宣言式宣传。
- 删除 Moe Counter 等与工程文档无关的装饰。
- 删除无法复现的绝对声明，例如“无可感知的额外延迟”和“据我们所知还没有人做过”。

### 替换

- 添加规范 H1 标题。
- Socialify 描述改为“面向 AstrBot 的长期记忆、关系状态建模与即时聊天插件”。
- 顶部简介改为功能、适用场景和工程边界说明。
- 明确“人格、情绪、伤痕”等词是状态模型术语，不代表意识或主观体验。
- “完整配置参考”改为“常用配置”，并指向 `_conf_schema.json`。
- 版本要点更新为 2.5.0，详细变更继续由 CHANGELOG 承载。
- 快速开始先验证基础聊天，再逐项启用高风险可选能力。
- Star CTA 与页脚改为克制的组织口吻，维护主体写作 `2718 Labs`。

### 保留

- 可验证的功能列表、架构图、配置说明、安全边界和开发文档。
- Scar Algebra、Void Calculus 等技术名词，但去掉将其描述成真实意识或主观体验的暗示。

## 元数据与变更记录

- `metadata.yaml`：
  - `version` 改为 `2.5.0`。
  - `author` 改为 `2718 Labs`。
  - `desc` 与 `short_desc` 改为中性功能描述。
  - `repo` 暂时保持当前可用地址。
- `main.py`：
  - `PLUGIN_VERSION` 与 `@register` 版本统一为 `2.5.0`。
- `CHANGELOG.md`：
  - 顶部新增 `[Embodiment-2.5.0]` 正式条目。
  - 保留 grey.1 至 grey.7 历史记录，不覆盖、不重写。
  - 明确 stable 包不激活 v3 影子路径，G3/G4 仍需真实数据。

## 测试与 CI

- 将发布契约测试的 checked-in 基线从 grey 身份切换为 stable `2.5.0`。
- 保留 grey 通道、临时 metadata override、错误身份和历史负例测试。
- 反转包体测试夹具：
  - stable 包直接使用 checked-in `2.5.0`。
  - grey 包使用临时 grey metadata override。
- 修复 PR CI 在未安装 AstrBot 时的测试收集失败：只有确实依赖 AstrBot 4.26.5 源码的测试跳过，其余模拟测试继续执行。
- 至少通过发布/包体契约、相关 CI 回归、Ruff 和 diff 完整性检查。

## 包体流程

1. 完成源码身份、README、metadata、CHANGELOG 与测试调整。
2. 提交干净的 source commit。
3. 从该 commit 构建：

   `python scripts/package_plugin.py --channel stable --output dist/astrbot_plugin_sylanne-2.5.0.zip`

4. 独立验证：
   - manifest `channel=stable`
   - `metadata_version=2.5.0`
   - `BUILD_CHANNEL=stable`
   - `V3_SHADOW_ENABLED=False`
   - 包内三处发布身份一致
   - manifest commit、payload digest 和 ZIP SHA-256
5. 用已验证包覆盖受跟踪的根 `astrbot_plugin_sylanne.zip`，单独提交包体。

## PR 与发布边界

- PR #65 继续保持 Draft。
- PR 标题更新为 `release: prepare Sylanne-Embodiment 2.5.0`。
- PR 正文只声明正式候选已准备，不宣称 v3 已 stable-ready。
- 本任务不合并、不转 Ready、不创建 Tag、不创建 GitHub Release、不部署。
- `release.yml` 会在 stable metadata 合入 `main` 后自动发布，因此未来合并必须再次取得明确授权。

## 非目标

- 不迁移 GitHub 仓库或修改当前可用仓库 URL。
- 不批量改写历史 grey CHANGELOG、设计文档、测试名称或实验记录。
- 不在 stable 包中启用 v3 影子路径。
- 不以本次定板声称 G3/G4 已完成或个性化收益已被真实数据证明。
