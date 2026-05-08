# 远程测试与性能基准文档

本文记录 `astrbot_plugin_emotional_state` 的远程验证方法、当前阶段性实测结果、LivingMemory 兼容检查口径，以及继续跑完完整矩阵时的注意事项。

## 测试边界

远程测试分为三类：

| 类型 | 目的 | 是否会调用模型 |
| --- | --- | --- |
| 远程只读烟测 | 登录 AstrBot WebUI，检查插件列表、目标插件状态、失败插件摘要和基础 API 健康。 | 否 |
| 远程上传/安装验证 | 上传发布 zip，确认目标插件被安装、启用，且不会误删 LivingMemory。 | 否 |
| 远程性能基准 | 通过 ChatUI SSE `/api/chat/send` 发送短消息，统计延迟、TTFT、token 和各功能开关的增量。 | 是 |

凭据必须通过环境变量传入。不要把服务器地址、用户名、密码、token 写进仓库文件或测试产物。

## 当前实测结论

截至 `2026-05-08T15:45:33Z`，官方远程性能 run 的阶段性结果如下：

| 项目 | 值 |
| --- | --- |
| run id | `remote-emotion-v010-gpt55-feature-lifecycle` |
| AstrBot 远程端口 | `15356` |
| 插件版本 | `0.1.0-beta` |
| 请求模型 | `gpt5.5` |
| 实际选中 provider | `1111/gpt-5.5` |
| 实际模型名 | `gpt-5.5` |
| 并发 | `2` |
| 样本间隔 | `1000 ms` |
| feature 总工作量 | `2520` 条，含预热 |
| 已完成有效样本 | `900` 条 |
| 当前状态 | 阶段性完成，未跑完整矩阵；summary 为 `ok=true` |

模型确认口径：

- `summary.json` 中 `requested_model=gpt5.5`。
- `summary.json` 中 `selected_provider.provider_id=1111/gpt-5.5`。
- `summary.json` 中 `selected_provider.model_name=gpt-5.5`。
- 最近成功样本的 `provider_id` 和 `model_name` 也均为 `1111/gpt-5.5` / `gpt-5.5`。

## 阶段性性能结果

下表为 `output/remote_emotion_benchmark_official/remote-emotion-v010-gpt55-feature-lifecycle/summary.json` 的阶段性聚合结果。延迟单位为毫秒。

| case | 有效样本 | 错误 | 平均延迟 | p50 延迟 | p95 延迟 | 平均 token | 平均延迟增量 | 平均 token 增量 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `baseline_minimal` | 250 | 0 | 14697.71 | 14410.10 | 19975.40 | 2703.00 | 基线 | 基线 |
| `emotion_injection` | 250 | 0 | 13371.48 | 13789.30 | 17762.50 | 3091.93 | -1326.24 | +388.93 |
| `low_reasoning` | 250 | 0 | 16689.39 | 16834.40 | 20160.30 | 2682.47 | +1991.67 | -20.53 |
| `humanlike` | 150 | 0 | 12900.42 | 13287.10 | 17768.50 | 3181.99 | -1797.30 | +478.99 |

解释：

- `emotion_injection` 和 `humanlike` 的平均延迟低于 baseline，不能简单理解为功能必然加速；远程模型排队、服务端负载和时间窗口会影响端到端延迟。
- token 增量更适合评价功能开销。当前阶段中 `emotion_injection` 约增加 `388.93` token，`humanlike` 约增加 `478.99` token。
- `low_reasoning` 当前平均 token 略低于 baseline，但端到端延迟更高。这说明低推理友好模式减少提示词成本不等于一定降低远程模型排队时间。
- 2 并发下 provider 级 token 差分会被并发请求污染，因此脚本自动关闭 provider token fallback，优先使用 SSE `agent_stats`。

## 已完成的远程安装与兼容检查

远程安装前执行过同名插件清理：

- 只删除 `astrbot_plugin_emotional_state`。
- `delete_config=false`。
- `delete_data=false`。
- 未触碰 LivingMemory 插件。

远程严格烟测确认：

- AstrBot 版本：`4.24.2`。
- 目标插件：`astrbot_plugin_emotional_state`。
- 目标版本：`0.1.0-beta`。
- 显示名：`多维情绪状态`。
- 启用状态：`true`。
- 目标插件未出现在失败插件列表中。

远程 LivingMemory 可见性：

- `astrbot_plugin_livingmemory` 版本 `2.2.10` 可见。
- `astrbot_plugin_lmem_control` 版本 `0.0.1` 可见。

LivingMemory 字段级兼容性由本地公共 API 测试证明，远程黑盒测试只证明共存和不误删。因为当前没有确认可用的 LivingMemory 远程数据读取 API，所以不要声称已经远程读取并验证了字段落库。

字段级兼容性覆盖：

- `emotion_at_write`
- `humanlike_state_at_write`
- `lifelike_learning_state_at_write`
- `personality_drift_state_at_write`
- `moral_repair_state_at_write`
- `fallibility_state_at_write`
- `integrated_self_state_at_write`
- `state_annotations_at_write`

## 复现远程只读烟测

```powershell
$node = "$HOME\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
$nodeModules = "$HOME\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules"
if (Test-Path $node) { $env:NODE_PATH = $nodeModules } else { $node = "node" }

$env:ASTRBOT_REMOTE_URL = "http://your-astrbot-host:15356/"
$env:ASTRBOT_REMOTE_USERNAME = "your-user"
$env:ASTRBOT_REMOTE_PASSWORD = "your-password"
$env:ASTRBOT_EXPECT_PLUGIN = "astrbot_plugin_emotional_state"
$env:ASTRBOT_EXPECT_VERSION = "0.1.0-beta"

& $node scripts\remote_smoke_playwright.js
```

## 复现远程性能基准

先构建并上传当前发布包，再运行性能脚本。真实调用默认关闭，必须显式设置确认变量。

```powershell
$node = "$HOME\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
$nodeModules = "$HOME\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules"
if (Test-Path $node) { $env:NODE_PATH = $nodeModules } else { $node = "node" }

$env:ASTRBOT_REMOTE_URL = "http://your-astrbot-host:15356/"
$env:ASTRBOT_REMOTE_USERNAME = "your-user"
$env:ASTRBOT_REMOTE_PASSWORD = "your-password"
$env:ASTRBOT_BENCHMARK_RUN_ID = "remote-emotion-v010-gpt55-feature-lifecycle"
$env:ASTRBOT_BENCHMARK_MODE = "features"
$env:ASTRBOT_BENCHMARK_MODEL = "gpt5.5"
$env:ASTRBOT_BENCHMARK_CONCURRENCY = "2"
$env:ASTRBOT_BENCHMARK_MAX_SAMPLES = "50"
$env:ASTRBOT_BENCHMARK_SLEEP_MS = "1000"
$env:ASTRBOT_BENCHMARK_DRY_RUN = "0"
$env:ASTRBOT_BENCHMARK_CONFIRM = "RUN_REMOTE_EMOTION_BENCHMARK"
$env:ASTRBOT_BENCHMARK_TOKEN_FALLBACK = "1"
$env:ASTRBOT_REMOTE_ARTIFACT_DIR = "output\remote_emotion_benchmark_official"

& $node scripts\remote_emotion_benchmark_playwright.js
```

连续小批次续跑：

```powershell
$env:ASTRBOT_BENCHMARK_BATCHES = "3"
$env:ASTRBOT_BENCHMARK_TARGET_COMPLETED = "900"
& $node scripts\run_remote_emotion_benchmark_batches.js
```

## 数据隔离与续跑规则

性能脚本使用以下规则避免旧数据污染：

- 每条样本新建一个远程 session。
- 每条样本结束后删除对应 session。
- `samples.jsonl` 按 `sample_key` 去重，summary 只保留最新的非 `skipped` 记录。
- 只有最新记录为 `ok` 的 `sample_key` 会被视为已完成。
- 旧失败样本会被续跑重试，不会被永久计入失败。
- 同一个 `RUN_ID` 和相同 `run_hash` 用于断点续跑；改动矩阵、mode 或模型会生成不同 `run_hash`。

2 并发实现边界：

- `ASTRBOT_BENCHMARK_CONCURRENCY` 最高允许 `2`。
- 两个 worker 页面共享同一个 Playwright browser context，避免第二个 worker 未授权。
- 配置写入使用互斥锁。
- work queue 会按相同配置分块，防止不同 feature case 并发互相踩配置。

## 完整 feature 矩阵

默认 feature 顺序：

1. `baseline_minimal`
2. `emotion_injection`
3. `low_reasoning`
4. `humanlike`
5. `lifelike_learning`
6. `personality_drift`
7. `moral_repair`
8. `fallibility_low_risk`
9. `integrated_self_full`
10. `all_safe_modules`

每个 case 默认 `250` 条有效样本，并带 `2` 条预热。完整 feature run 共有 `2520` 个 work item。

当前已完成：

- `baseline_minimal`：250/250
- `emotion_injection`：250/250
- `low_reasoning`：250/250
- `humanlike`：150/250

仍待完成：

- `humanlike` 剩余 100 条
- `lifelike_learning`
- `personality_drift`
- `moral_repair`
- `fallibility_low_risk`
- `integrated_self_full`
- `all_safe_modules`

## 生命周期测试计划

生命周期测试应使用单独 run id。自 `2026-05-09` 起，生命周期测试不再只把“经过 1 天/1 年”写进 prompt，而是由 benchmark 脚本临时写入测试专用配置：

- `benchmark_enable_simulated_time=true`
- `benchmark_time_offset_seconds=<当前时间尺度对应秒数>`

插件生产默认仍然使用真实 `time.time()`；只有测试脚本显式打开该配置时，hook 才会把观测时间视为 `time.time()+offset`。因此生命周期测试可以快速覆盖 1 天到 1 年的真实秒差，同时仍然走情绪半衰期、人格漂移、生命化学习、道德修复和瑕疵状态自己的真实时间公式。

推荐使用新的 run id，避免旧的“文案型时间”样本和新的“状态型时间”样本混在一起：

```powershell
$env:ASTRBOT_BENCHMARK_RUN_ID = "remote-emotion-v010-gpt55-lifecycle-simtime"
$env:ASTRBOT_BENCHMARK_MODE = "lifecycle"
$env:ASTRBOT_BENCHMARK_LIFECYCLE_ITERATIONS = "100"
$env:ASTRBOT_BENCHMARK_MAX_SAMPLES = "25"
```

默认生命周期时间尺度：

| 时间尺度 | 用途 |
| --- | --- |
| `1d` | 1 天状态延续 |
| `1w` | 1 周状态延续 |
| `1m` | 1 月状态延续 |
| `2m` | 2 月状态延续 |
| `3m` | 3 月状态延续 |
| `4m` | 4 月状态延续 |
| `5m` | 5 月状态延续 |
| `6m` | 6 月状态延续 |
| `1y` | 1 年状态延续 |

生命周期模拟采用缩写身份 `SY` 和 `AL`，只用于长周期伴随关系负载测试；测试文档和样本提示不包含隐私画像细节。

### 生命周期模拟时间小批实测

`remote-emotion-v010-gpt55-lifecycle-simtime` 已完成一轮 9 个时间尺度的小批实测，用于确认脚本会把真实秒差写入插件状态时间，而不是只改 prompt 文案。

| 项目 | 值 |
| --- | --- |
| run id | `remote-emotion-v010-gpt55-lifecycle-simtime` |
| mode | `lifecycle` |
| 请求模型 | `gpt5.5` |
| 实际选中 provider | `1111/gpt-5.5` |
| 实际模型名 | `gpt-5.5` |
| 并发 | `2` |
| 本轮有效样本 | `9/9` |
| 错误 | `0` |
| 平均延迟 | `9694.74 ms` |
| p95 延迟 | `11330.00 ms` |
| 平均 TTFT | `7822.18 ms` |
| 平均 token | `3756.56` |
| token 来源 | `agent_stats` |

各时间尺度单样本结果如下。该表只能证明模拟时间链路可用，不能替代后续每个尺度 `100` 次的正式统计。

| 时间尺度 | 平均延迟 ms | 平均 TTFT ms | token |
| --- | ---: | ---: | ---: |
| `1d` | 9080.90 | 7231.30 | 3708 |
| `1w` | 9558.80 | 8054.00 | 3759 |
| `1m` | 9684.40 | 7139.50 | 3755 |
| `2m` | 9298.00 | 7086.70 | 3763 |
| `3m` | 10040.00 | 7622.00 | 3762 |
| `4m` | 10304.20 | 7783.30 | 3781 |
| `5m` | 11330.00 | 9584.20 | 3805 |
| `6m` | 9100.70 | 7840.80 | 3753 |
| `1y` | 8855.70 | 8057.80 | 3723 |

如果生命周期测试中途被手动中断，必须先在远程配置页或脚本恢复阶段确认：

- `benchmark_enable_simulated_time=false`
- `benchmark_time_offset_seconds=0.0`

这两个配置只服务于 benchmark。生产对话不应常开模拟时间，否则情绪半衰期、人格漂移和长期学习会被人为加速。

## 常见失败与处理

| 现象 | 可能原因 | 处理 |
| --- | --- | --- |
| 第二个 worker `401 未授权` | worker 页面没有共享登录态 | 使用共享 browser context；当前脚本已修复。 |
| `Failed to create remote chat session: 0` | 服务器重启、网络波动或 session API 短时不可达 | 保持同一 run id 续跑，失败样本会重试。 |
| token 来源为 `unavailable` | SSE 未返回 `agent_stats`，并发下 provider delta 被禁用 | 保留样本但不计 token 均值；优先检查 SSE `agent_stats`。 |
| p95 突然升高 | provider 排队或远程服务负载变化 | 不单看单批结果，至少按 case 聚合后再判断。 |
| summary 中 prewarm 有 token source 但 sample_count 为 0 | 预热样本不计入有效样本 | 正常现象。 |

## 结果解读原则

- 远程端到端延迟包含 WebUI、AstrBot、插件、provider、网络和模型排队，不等于插件本地开销。
- 本地插件热路径开销应以 `scripts/benchmark_plugin_hot_path.py` 为准。
- token 增量更适合判断提示词注入、状态注解和模块开启成本。
- 远程性能结果需要和同一时间窗口内的 baseline 对照，不要跨天直接比较。
- 未完成完整矩阵前，只能称为阶段性结果。
