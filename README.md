# Sylanne-Embodiment

面向 AstrBot 的长期记忆、关系状态、主动交互和即时聊天插件，由 2718 Labs 维护。

![version](https://img.shields.io/badge/version-Embodiment--2.5.0-blue)
![license](https://img.shields.io/badge/license-AGPL--3.0--or--later-red)
![astrbot](https://img.shields.io/badge/AstrBot-%3E%3D4.26%2C%3C5.0.0-green)

- 当前版本：`Embodiment-2.5.0`
- AstrBot：`>=4.26,<5.0.0`
- Python：`3.10-3.13`
- 许可证：AGPL-3.0-or-later

> “情绪”“人格”“伤痕”“空洞”等词在本项目中表示软件状态或产品概念，不表示真实意识、医学状态或生物学结论。

## 功能

- 长期记忆：按会话保存、召回和整理信息，支持跨重启恢复。
- 关系状态：为不同会话和身份维护有界状态；跨群能力默认关闭。
- 语义分段：由本轮主模型标注节拍边界，不增加额外模型请求。
- 即时聊天：支持分段发送、发送节奏、中断处理与历史保存解耦。
- 主动交互：生活模拟、主动消息和 QQ 空间能力均使用独立开关。
- 用户控制：暂停、重置、退出和敏感能力授权由硬门控处理。
- WebUI：提供配置、实时运行状态和诊断入口。

高风险可选能力默认关闭。部署时应先验证基础聊天和历史记录，再按需启用即时聊天、跨群记忆、主动消息或 QQ 空间能力。

## 关键运行契约

### 对话历史

插件只把真实用户输入和最终助手回复保存到 AstrBot 对话历史。人格、记忆、状态和调度信息通过本轮 `system_prompt` 提供，不写入长期聊天记录。

请求阶段不会永久改写 AstrBot 已加载的 `request.contexts`。需要过滤旧内部标记或修复工具配对时，插件为当前 Provider 构造临时视图，并在 AstrBot 保存历史前恢复原始对象。临时视图发生变化后会按实际消息重新计算 token 数。只有框架明确跳过保存时，插件才补写本轮真实消息。

### 语义分段

主回复模型可以在输出中生成带本轮 nonce 的隐藏边界。插件按以下规则处理：

1. 存在合法边界时按边界发送多条消息。
2. 没有 marker 时，模型正文中的显式换行作为备用边界。
3. 代码块、表格和列表保持为完整结构。
4. 只有标点的片段并入相邻文本，并保留对应停顿。
5. marker 异常、越界或位于保护区域时，移除 marker 后整条发送。
6. 超长内容仍按平台长度限制做安全切分。

隐藏 marker 不进入用户可见文本，也不进入最终历史。

### 发送所有权

`on_llm_response` 只准备投递计划，不直接发送正文。装饰阶段的最终结果为纯文本时，插件认领并分段发送；结果已被 TTS 或其他插件转换为语音、图片或文件时，插件放弃文本计划，由 AstrBot 发送最终组件。同一轮只有一个最终发送者。

### 状态持久化

- 当前 Embodiment schema 可以直接恢复。
- 损坏的 JSON 状态文件会隔离为 `.damaged` 文件。
- 用户记忆格式兼容由记忆模块处理。
- 旧状态机核心快照不会自动转换为 Embodiment 核心状态；插件保留原文件并从新状态启动。

## 版本谱系

| 代际 | 版本形式 | 说明 |
| --- | --- | --- |
| 旧状态机 | `v3.0.10` 及同代版本 | 重构前的状态机实现。 |
| Embodiment | `Embodiment-x.x.x` | 当前架构；本版本为 `Embodiment-2.5.0`。 |

从旧状态机版本升级前应备份 AstrBot 数据目录。旧核心快照保持原样，当前 schema 和用户记忆的兼容由对应模块分别处理。

## 安装

1. 从 Releases 下载版本化 ZIP。
2. 在 AstrBot 管理面板上传 ZIP 并启用插件。
3. 确认包内 `metadata.yaml` 的版本为 `2.5.0`。
4. 先验证普通对话、连续多轮上下文和重启后的历史恢复。
5. 再逐项启用可选能力。

本地调试也可以把插件目录放入 `AstrBot/data/plugins/`，然后在 WebUI 中重载插件。

## 常用配置

完整字段、类型和默认值以 [`_conf_schema.json`](_conf_schema.json) 为准。配置页默认只展示常用路由；功能专用 Provider 位于高级覆盖区。

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `sylanne_webui_enabled` | `false` | 启用 WebUI。 |
| `sylanne_alpha_aux_provider_id` | 空 | 共享辅助文本模型 Provider。 |
| `sylanne_alpha_embedding_memory_enabled` | `false` | 启用 Embedding 辅助召回。 |
| `sylanne_alpha_realtime_chat_enabled` | `false` | 启用即时聊天调度。 |
| `sylanne_alpha_realtime_intercept_llm_response` | `false` | 允许即时聊天接管模型回复。 |
| `sylanne_alpha_life_simulation_enabled` | `false` | 启用生活模拟。 |
| `sylanne_alpha_cross_session_mode` | `off` | 跨会话记忆总开关。 |
| `sylanne_alpha_qzone_enabled` | `false` | 启用 QQ 空间功能。 |

前台即时判断由本地 v2core 完成，不需要单独配置 LLM Provider。后台生活、关系和内容生成功能只有在启用对应能力并配置可用 Provider 后才会调用模型。

## 代码结构

```text
main.py                                AstrBot 插件入口和钩子注册
sylanne_alpha/llm_request_pipeline.py  请求构建、临时历史视图和状态注入
sylanne_alpha/llm_response_pipeline.py 回复处理、分段和保存边界
sylanne_alpha/semantic_segmentation.py 语义边界解析与安全回退
sylanne_alpha/message_dispatch.py      消息归一化与发送
sylanne_alpha/state_persistence.py     状态和必要的历史补写
sylanne_alpha/memory_system.py         长期记忆
sylanne_alpha/life_simulation.py       生活模拟
sylanne_alpha/realtime_dispatch.py     即时聊天调度
sylanne_alpha/v2core/                  逐轮认知编排和状态域
sylanne_alpha/agents/                  自主生命周期与进化档案
sylanne_alpha/_engine/                 Resonance 身体计算后端
tests/                                 回归测试
```

## 开发与验证

开发约束见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。常用命令：

```powershell
python -m pytest
python -m ruff check .
python -m compileall -q main.py sylanne_alpha
```

完整历史变更见 [`CHANGELOG.md`](CHANGELOG.md)。

本项目由 2718 Labs 维护，并按 [AGPL-3.0-or-later](LICENSE) 发布。
