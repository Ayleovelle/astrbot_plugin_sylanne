# Sylanne-Embodiment Preview Branch

> 本分支 (`Sylanne-Embodiment-preview`) 是 Embodiment 1.4.0+ 的开发分支。所有新功能和修复先在这里验证，稳定后由维护者手动合并到 `main`。

## 当前开发状态

**基于 1.3.0 的增量改动：**

### 注入系统重写（核心）

- 优先级预算分配：5 槽位（感知/迷失/生活/记忆/未完）按优先级竞争 token 预算
- 动态预算：根据对话间隔自动调整总预算（15min 内 1200 / 2h 内 2400 / 更久 3600）
- 三模式注入：default（`_no_save` contexts）/ claude_advisory（system_prompt）/ hajide（跳过）
- 200ms 后台计算等待窗口：等 observe 任务完成再注入，避免过时数据
- 短间隔变化检测：delta > 0.15 才注入慢变信号，避免重复注入

### AstrBot 手册全量合规修复

- **历史污染根治**：全项目零 `request.prompt` 写入，所有临时注入走 `system_prompt`
- **realtime_dispatch**：5 处 prompt 污染修复
- **_normalize_claude_request_payload**：哈基德模式不再清空全部 contexts，只过滤不兼容条目
- **安全加固**：config_export 敏感字段脱敏，config_import 拒绝安全字段覆盖
- **资源泄漏**：terminate() 取消所有 background tasks / checkpoint tasks / scheduler
- **事件循环阻塞**：LRU 驱逐改为 fire-and-forget async persist，文件 IO 全部 to_thread
- **数据路径迁移**：`data/sylanne_alpha/` → `data/plugin_data/astrbot_plugin_sylanne/`（自动迁移）
- **会话删除回调**：注册 `register_on_session_deleted`，释放内存 + 清理 KV 存储
- **性能优化**：scar O(n²) → O(n) 预计算、L3 ColdGraph 索引、_relationship_deltas 加 maxsize
- **速率限制**：主动发言硬下限由 extraversion 驱动（人格驱动全参数原则）

### 新增模块

| 模块 | 职责 |
|------|------|
| `analytics.py` | 运行时分析与指标收集 |
| `dialogue_intelligence.py` | 对话智能（意图识别、话题追踪） |
| `i18n.py` | 国际化支持 |
| `infra.py` | 基础设施（BoundedDict、路径解析、异步工具） |
| `inner_self.py` | 内在自我模型 |
| `multi_device.py` | 多设备会话同步 |
| `relationship_dynamics.py` | 关系动力学（仪式、阶段、修复） |
| `prompts/` | Prompt 模板管理 |
| `strategy_plugins/` | 策略插件系统 |

### 潜在影响

- **数据路径变更**：旧数据会自动迁移，但如果有外部脚本直接读 `data/sylanne_alpha/` 需要更新路径
- **system_prompt 注入**：如果其他插件也写 system_prompt，可能需要注意拼接顺序（AstrBot 框架保证追加语义）
- **terminate 行为变更**：现在会主动取消所有后台任务，热重载时可能看到 CancelledError 日志（正常）
- **BoundedDict 驱逐**：超过 200 条关系 delta 缓存时会 LRU 驱逐，极端多关系场景下可能丢失最旧的 delta

## 开发约定

- 不直接 push 到 main
- 合并由维护者手动执行
- commit message 用中文，格式：`类型(范围): 描述`
- 人格驱动全参数：任何新增的 cap/clamp/threshold 必须是人格函数

## 与 main 的差异

```
main:     Embodiment 1.3.0（稳定发布）
preview:  Embodiment 1.4.0（开发中，含全量合规修复 + 新模块）
```
