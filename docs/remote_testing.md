# 远程测试与性能基准文档

本文记录 `astrbot_plugin_emotional_state` 的远程验证方法、`1.0.0` 状态层实测结果、LivingMemory 兼容检查口径，以及后续复现实验时的数据隔离规则。

## 测试边界

远程测试分为三类：

| 类型 | 目的 | 是否会调用模型 |
| --- | --- | --- |
| 远程只读烟测 | 登录 AstrBot WebUI，检查插件列表、目标插件状态、失败插件摘要和基础 API 健康。 | 否 |
| 远程上传/安装验证 | 上传发布 zip，确认目标插件被安装、启用，且不会误删 LivingMemory。 | 否 |
| 远程性能基准 | 通过 ChatUI SSE `/api/chat/send` 发送短消息，统计延迟、TTFT、token 和各功能开关的增量。 | 是 |

凭据必须通过环境变量传入。不要把服务器地址、用户名、密码、token 写进仓库文件或测试产物。

## 当前实测结论

截至 `2026-05-09T13:15:49Z`，`1.0.0` 沿用的状态层官方远程性能数据已经完成两组正式口径：`gpt5.5` 完整功能开关矩阵，以及同一模型、同一状态层配置面下的关闭情绪对照。DeepSeek 相关功能矩阵已按用户要求取消，不再继续跑，也不纳入正式结论。

| 项目 | 值 |
| --- | --- |
| 功能矩阵运行编号 | `remote-emotion-v050-gpt55-feature-state-layer-real` |
| 关闭情绪对照运行编号 | `remote-emotion-v050-gpt55-noemotion-control-state-layer-c3-250-real` |
| 插件版本 | `1.0.0` |
| 请求模型 | `gpt5.5` |
| 实际选中 provider | `1111/gpt-5.5` |
| 实际模型名 | `gpt-5.5` |
| 并发 | `3` |
| 样本间隔 | `1000 ms` |
| 功能矩阵有效样本 | `2500/2500` |
| 功能矩阵失败请求 | `0` |
| 关闭情绪对照有效样本 | `250/250` |
| 关闭情绪对照失败请求 | `0` |
| token 口径 | SSE `agent_stats`，provider fallback 关闭 |
| 当前状态 | `gpt5.5` 正式矩阵与关闭情绪对照均完成 |

模型确认口径：

- 功能矩阵与关闭情绪对照两个正式 `summary.json` 均为 `requested_model=gpt5.5`。
- 两个正式 `summary.json` 的 `selected_provider.provider_id=1111/gpt-5.5`。
- 两个正式 `summary.json` 的 `selected_provider.model_name=gpt-5.5`。
- 原始 benchmark 产物位于被 `.gitignore` 忽略的 `output/remote_emotion_benchmark_official/` 下；README 和本文只记录聚合结果，不记录远程服务器地址或凭据。

## gpt-5.5 正式功能矩阵

下表为 `output/remote_emotion_benchmark_official/remote-emotion-v050-gpt55-feature-state-layer-real/summary.json` 的正式聚合结果。延迟单位为毫秒，增量相对 `baseline_minimal` 计算。

| case | 有效样本 | 错误 | 平均延迟 | p50 延迟 | p95 延迟 | 平均 TTFT | 平均 token | 平均延迟增量 | p95 增量 | token 增量 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `baseline_minimal` | 250 | 0 | 16308.11 | 16440.20 | 22441.70 | 12565.41 | 2726.52 | 基线 | 基线 | 基线 |
| `emotion_injection` | 250 | 0 | 17277.68 | 17195.90 | 25870.60 | 13601.02 | 3120.93 | +969.56 | +3428.90 | +394.41 |
| `low_reasoning` | 250 | 0 | 20550.09 | 20288.60 | 25698.40 | 12579.65 | 2727.24 | +4241.97 | +3256.70 | +0.72 |
| `humanlike` | 250 | 0 | 17112.82 | 17466.30 | 23717.90 | 13313.04 | 3171.38 | +804.71 | +1276.20 | +444.86 |
| `lifelike_learning` | 250 | 0 | 16376.29 | 16857.30 | 21981.60 | 13064.36 | 3168.79 | +68.18 | -460.10 | +442.27 |
| `personality_drift` | 250 | 0 | 17009.38 | 17620.50 | 23335.20 | 13210.54 | 3175.14 | +701.27 | +893.50 | +448.62 |
| `moral_repair` | 250 | 0 | 16450.77 | 16295.70 | 22808.70 | 12585.68 | 3177.38 | +142.65 | +367.00 | +450.86 |
| `fallibility_low_risk` | 250 | 0 | 16714.61 | 16624.60 | 23386.00 | 12930.12 | 3119.09 | +406.50 | +944.30 | +392.57 |
| `integrated_self_full` | 250 | 0 | 16149.86 | 15956.10 | 22174.30 | 12649.54 | 3121.31 | -158.26 | -267.40 | +394.79 |
| `all_safe_modules` | 250 | 0 | 20777.29 | 20351.20 | 27496.30 | 13309.28 | 3329.84 | +4469.17 | +5054.60 | +603.32 |

解释：

- `all_safe_modules` 是当前完整安全模块组合下的最高开销点，平均延迟比 baseline 高 `4469.17 ms`，平均 token 高 `603.32`。
- `low_reasoning` 的 token 与 baseline 基本持平，但端到端延迟反而更高，说明远程模型排队、provider 调度和采样窗口会影响延迟，不能只用 prompt 长度解释。
- `integrated_self_full` 平均延迟略低于 baseline，但 token 仍增加 `394.79`。这类负延迟增量应理解为远程端到端波动，不代表功能具备必然加速效果。
- token 增量更适合评价提示词注入和状态注解开销；端到端延迟则必须结合时间窗口、远程负载和 p95 一起看。

## 关闭情绪对照

关闭情绪对照使用当前状态层配置面，仅把顶层 `enabled=false`，用于估计插件状态层参与主回复路径时的残余差异。

| case | 有效样本 | 错误 | 平均延迟 | p50 延迟 | p95 延迟 | 平均 TTFT | 平均 token |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `no_emotion_control` | 250 | 0 | 16023.63 | 15507.10 | 23892.90 | 12334.33 | 2741.02 |

与 `baseline_minimal` 对比：

| 对比项 | 差值 |
| --- | ---: |
| 平均延迟 | -284.48 ms |
| p95 延迟 | +1451.20 ms |
| 平均 token | +14.50 |

该对照显示：在这组远程样本里，顶层关闭插件与 `baseline_minimal` 的平均延迟差异小于 0.3 秒，但 p95 更高。这个结果更像远程排队/时间窗波动，而不是稳定的本地插件开销；本地热路径仍应以 `scripts/benchmark_plugin_hot_path.py` 为准。

## DeepSeek 取消说明

`remote-emotion-v050-deepseek-v4-flash-feature-state-layer-c3-2500-real` 是已中止的探索性残留：`summary.json` 为 `ok=false`，只完成 `295/2500` 条有效样本，并出现 `1` 个失败请求。用户已经明确取消 DeepSeek 后续测试，因此：

- 不继续跑 DeepSeek 功能矩阵。
- 不把该目录写成正式对照。
- 不用它论证不同推理能力模型对插件延迟或 token 的影响。
- 后续若重新开启跨模型对比，必须用新的 run id 和新的确认记录，避免把这段残留混入正式数据。

## 已完成的远程安装与兼容检查

远程安装前执行过同名插件清理：

- 只删除 `astrbot_plugin_emotional_state`。
- `delete_config=false`。
- `delete_data=false`。
- 未触碰 LivingMemory 插件。

远程严格烟测确认：

- AstrBot 版本：`4.24.2`。
- 目标插件：`astrbot_plugin_emotional_state`。
- 目标版本：`1.0.0`。
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
$env:ASTRBOT_EXPECT_PLUGIN_VERSION = "1.0.0"

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
$env:ASTRBOT_BENCHMARK_RUN_ID = "remote-emotion-v050-gpt55-feature-state-layer-real"
$env:ASTRBOT_BENCHMARK_MODE = "features"
$env:ASTRBOT_BENCHMARK_MODEL = "gpt5.5"
$env:ASTRBOT_BENCHMARK_CONCURRENCY = "3"
$env:ASTRBOT_BENCHMARK_MAX_SAMPLES = "50"
$env:ASTRBOT_BENCHMARK_SLEEP_MS = "1000"
$env:ASTRBOT_BENCHMARK_DRY_RUN = "0"
$env:ASTRBOT_BENCHMARK_CONFIRM = "RUN_REMOTE_EMOTION_BENCHMARK"
$env:ASTRBOT_BENCHMARK_TOKEN_FALLBACK = "0"
$env:ASTRBOT_REMOTE_ARTIFACT_DIR = "output\remote_emotion_benchmark_official"

& $node scripts\remote_emotion_benchmark_playwright.js
```

连续小批次续跑：

```powershell
$env:ASTRBOT_BENCHMARK_BATCHES = "3"
$env:ASTRBOT_BENCHMARK_TARGET_COMPLETED = "2500"
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

并发实现边界：

- `scripts\remote_emotion_benchmark_playwright.js` 当前把 `ASTRBOT_BENCHMARK_CONCURRENCY` 上限钳制为 `3`。
- 多个 worker 页面共享同一个 Playwright browser context，避免额外 worker 未授权。
- 配置写入使用互斥锁。
- 工作队列会按相同配置分块，防止不同功能用例并发互相踩配置。

## 状态层并发与后台能力验证边界

远程性能基准里的“并发”是 ChatUI 样本并发，用来观察端到端延迟、TTFT、token 和远程稳定性；它不等同于完整证明插件内部所有后台/并发机制。

`1.0.0` 的后台处理、多线程/并发状态读取和群聊分层主要由本地单元测试锁定：

| 能力 | 主要验证位置 | 远程口径 |
| --- | --- | --- |
| 后台 post 评估 | `tests/test_astrbot_lifecycle.py` 覆盖后台队列、同会话 FIFO、检查点恢复、租约、重试、dead-letter 和诊断。 | 远程只观察开启相关功能后的端到端稳定性，不读取内部队列。 |
| 并发状态读取 | `tests/test_astrbot_lifecycle.py` 与 `tests/test_public_api.py` 覆盖请求辅助状态、响应后评估、道德/瑕疵状态、LivingMemory 可选快照 fan-out。 | 远程性能数据只反映整体延迟，不把每个内部 await 单独拆账。 |
| 群聊分轨 | `tests/test_astrbot_lifecycle.py` 覆盖 `conversation_id` 与 `speaker_track_id` 的分离和当前说话人注入。 | 远程烟测只确认插件加载和端到端可用，不模拟完整多人群聊。 |
| 群聊氛围 | `tests/test_group_atmosphere_engine.py` 与生命周期测试覆盖 `activity/tension/playfulness/supportiveness/bot_attention/interrupt_risk/joinability`、开口冷却和 diff 注入。 | 远程基准可作为稳定性参考，不替代理论维度与策略测试。 |

因此，README 和本文中的远程结果应解读为“已安装、可运行、端到端性能可观测”；内部后台队列、并发 fan-out、群聊状态分轨和加入策略的正确性，以本地测试为主。

## 完整功能矩阵

默认功能用例顺序：

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

每个用例默认 `250` 条有效样本，并带 `2` 条预热。完整功能矩阵运行共有 `2520` 个工作项。

当前正式 `gpt5.5` 运行已完成全部 10 个用例，每个用例 `250/250`，失败请求为 `0`。`remote-emotion-v050-gpt55-feature-state-layer-fullmatrix` 是试运行目录，没有 `summary.json`，不得用于报告。

## 跨模型生命周期单轮拟合

跨模型生命周期测试使用状态级模拟时间覆盖 `1d`、`1w`、`1m`、`2m`、`3m`、`4m`、`5m`、`6m`、`1y`。当前每个模型每个时间尺度只有 `1` 条样本，因此本节是发布参考拟合，不是正式大样本统计。

| 模型 | 样本 | 平均延迟 ms | p95 延迟 ms | 平均 token | 延迟斜率 ms/log2(天) | 延迟 R2 | token 斜率 | token R2 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-5.5` | 9 | 13238.69 | 14724.94 | 3714.44 | -143.41 | 0.136 | -1.65 | 0.046 |
| `gpt-5.4` | 9 | 13664.23 | 15847.90 | 3685.78 | 102.43 | 0.046 | 3.04 | 0.120 |
| `gpt-5.4-mini` | 9 | 11798.89 | 13705.78 | 3651.33 | -3.22 | 0.000 | 0.87 | 0.269 |
| `deepseek-v4-flash` | 9 | 13676.18 | 15841.24 | 5966.78 | -122.96 | 0.041 | 354.10 | 0.066 |
| `deepseek-v4-pro` | 9 | 19813.90 | 23825.10 | 4811.33 | -600.61 | 0.299 | -20.74 | 0.422 |
| `gemini-2.5-flash` | 9 | 11561.28 | 13045.74 | 3992.89 | 25.12 | 0.005 | -79.99 | 0.019 |
| `gemini-flash-lite-latest` | 9 | 32602.13 | 45391.16 | 4735.33 | 2251.29 | 0.442 | -43.81 | 0.320 |
| `gemini-flash-latest` | 9 | 17438.13 | 21929.92 | 7073.89 | 465.60 | 0.213 | 563.13 | 0.346 |
| `gemini-pro-latest` | 9 | 17915.60 | 19008.80 | 4435.33 | -158.71 | 0.140 | 1.07 | 0.166 |
| `mimo-v2.5` | 9 | 18394.20 | 22864.32 | 9128.11 | -684.69 | 0.364 | 778.87 | 0.142 |
| `mimo-v2.5-pro` | 9 | 17305.32 | 22552.18 | 6947.78 | 147.63 | 0.014 | 311.09 | 0.068 |

拟合模型为 `y = beta0 + beta1 log2(天)`。图表见 `docs/assets/lifecycle_model_fit.svg`，聚合 CSV 见 `docs/assets/lifecycle_model_fit_summary.csv`。原始样本仍保留在被忽略的 `output/remote_emotion_benchmark_models/`，不进入发布包。

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
- 未完成完整矩阵前，只能称为阶段性结果；当前 `gpt5.5` 状态层功能矩阵已经完成，可以作为正式 `gpt5.5` 结论。
