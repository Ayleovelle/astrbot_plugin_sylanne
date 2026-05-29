# Sylanne WebUI 接口申请与用途说明

更新日期：2026-05-23  
适用范围：`webui_preview.html`、`sylanne_alpha/webui.py`、`sylanne_alpha/webui_server.py`、插件内 AstrBot Web API。

这份文档用于前后端对接。WebUI 只负责展示和交互，不在前端重新推导人格、情绪、记忆或 7 层计算结果；这些数据需要由插件运行时稳定导出。

## 接入路径

WebUI 有两种运行方式：

| 场景 | 页面路径 | API 基址 |
| --- | --- | --- |
| AstrBot 插件内页面 | `/{PLUGIN_NAME}/webui` | `/{PLUGIN_NAME}/api/*` |
| 独立预览服务器 | `http://{host}:{port}/` | `/api/*` |
| 本地静态预览 | `file:///.../webui_preview.html` | 请求失败后走本地 fallback |

前端通过 `apiPath(path)` 自动处理 AstrBot 内页面的 base path。后端不要再额外要求前端手动配置 API 前缀。

## 通用约定

- 返回格式统一为 JSON，除图标资源外。
- 每个主要数据接口必须带 `schema_version`，方便以后升级时兼容。
- 数值状态尽量归一到 `0.0 - 1.0`，时间戳使用 Unix seconds。
- 后端不要返回 embedding 原始向量；只返回 `has_embedding`、`embedding_provider_id` 等摘要字段。
- 前端容忍未知字段，但后端不要删除已约定字段。
- 查询接口失败时，前端会进入离线预览 fallback；生产环境仍应保证接口可用。

## 当前前端轮询

| 接口 | 频率 | 用途 |
| --- | --- | --- |
| `GET /api/state` | 3s | 驱动总览、7 层动画、会话下拉、人格模板、主题色、耗时面板 |
| `GET /api/computation_logs` | 3s | 实时计算日志页 |
| `GET /api/memory_pools` | 5s | 三层记忆池页 |
| `GET /api/settings` | 首次加载/配置页刷新 | 配置页 schema、当前值、provider 下拉 |
| `POST /api/settings` | 点击保存 | 保存配置页改动 |

## 必需接口清单

| 状态 | 方法与路径 | 用途 |
| --- | --- | --- |
| 已接入，需保持契约 | `GET /api/state?session={session}` | WebUI 主状态源，所有实时动画和统计都从这里读 |
| 已接入，需保持契约 | `GET /api/settings` | 配置页读取 `_conf_schema.json` 全量键和值 |
| 已接入，需保持契约 | `POST /api/settings` | 配置页保存，后端负责校验类型和持久化 |
| 已接入，需保持契约 | `GET /api/computation_logs?limit=50` | 计算过程日志，展示 L1-L7 每层算了什么 |
| 已接入，需保持契约 | `GET /api/memory_pools?session={session}&limit=50` | 三层记忆架构展示 |
| 建议补齐 | `GET /logo.png` 或 `GET /assets/logo.png` | WebUI 左上角使用插件图标，避免 AstrBot 内页面相对路径失效 |

## `GET /api/state`

用途：WebUI 的实时状态总线。总览页、7 层脊柱动画、耗时展示、主题色、人格资料、会话选择都依赖这个接口。

查询参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `session` | string | 否 | 指定会话。为空时后端返回当前或第一个可用会话。 |

响应字段：

```json
{
  "schema_version": "sylanne.webui.state.v1",
  "current_session": "platform:group:user",
  "sessions": ["platform:group:user"],
  "emotion": {
    "valence": 0.5,
    "arousal": 0.2,
    "tension": 0.1,
    "trust": 0.6,
    "warmth": 0.5,
    "curiosity": 0.4,
    "expression_drive": 0.3,
    "active_voids": 0,
    "ghost_count": 0
  },
  "gate": {
    "precision": 0.8,
    "mean_surprise": 0.2,
    "history_len": 12,
    "history": [
      {"ts": 1710000000.0, "surprise": 0.2, "route": "fast"}
    ]
  },
  "route_stats": {"fast": 8, "normal": 3, "full": 1, "skip": 0},
  "boundary": {
    "integrity": 0.9,
    "entropy": 0.2,
    "stability": 0.85,
    "phase_transitions": 0
  },
  "expression": {
    "pressure": 0.3,
    "threshold": 0.6,
    "ratio": 0.5,
    "mode": "silent",
    "count": 0
  },
  "timing": {
    "perception_ms": 0.2,
    "gate_ms": 0.03,
    "memory_ms": 2.1,
    "total_ms": 3.2
  },
  "spine": {
    "surprise": 0.2,
    "route": "fast",
    "last_text": "user text preview",
    "sheaf": {},
    "hgt_decision": [0.12, 0.03, 0.01, 0.08],
    "boundary": {},
    "expression": {}
  },
  "persona": {
    "profile": {"name": "Sylanne", "version": "4.0"},
    "traits": {},
    "voice": {},
    "drift": {}
  },
  "theme": {
    "base": "#F3A7C8",
    "source": "emotion",
    "mode": "soft"
  },
  "feedback": {"accepted": 0, "ignored": 0, "rejected": 0},
  "life_simulation": {}
}
```

前端用途映射：

| 字段 | 前端用途 |
| --- | --- |
| `sessions/current_session` | 顶部会话下拉 |
| `emotion` | 主色调变化、情绪条、L7 表达驱动 |
| `gate.history` | L2 惊讶度脑电波式折线 |
| `route_stats` | 路由统计环图 |
| `boundary` | L6 边界稳定动画 |
| `timing` | 耗时面板，必须使用实时数据 |
| `spine` | 7 层动画的当前输入、route、sheaf、HGT、表达状态 |
| `persona` | 人格模板展示，按 bot 实际状态来，不在前端写死 |
| `theme` | 粉色主色 `#F3A7C8` 的情绪派生色 |

## `GET /api/settings`

用途：配置页必须按照包体真实配置键渲染，不手写旧字段。

响应：

```json
{
  "schema": {
    "enabled": {"type": "bool", "default": true, "description": "..."},
    "emotion_provider_id": {
      "type": "string",
      "default": "",
      "_special": "select_provider"
    }
  },
  "values": {
    "enabled": true,
    "emotion_provider_id": "provider-id"
  },
  "providers": [
    {"id": "provider-id", "name": "Provider Name", "type": "llm"},
    {"id": "embedding-id", "name": "Embedding Name", "type": "embedding"}
  ]
}
```

要求：

- `schema` 直接来自 `_conf_schema.json`。
- `values` 必须包含 schema 中每个 key；未配置时使用 schema default。
- `_special: "select_provider"` 的字段前端渲染为下拉选择，并保留手动填写兼容入口。
- `provider_type: "embedding"` 的字段只优先展示 embedding provider。
- `options` 存在时前端渲染为下拉选择。
- `bool/int/float/string` 由前端渲染为对应控件，后端保存时仍要二次校验。

当前 `_conf_schema.json` 共 106 个键，配置接口必须全量覆盖。按用途分组如下：

| 分组 | 键 |
| --- | --- |
| core | `enabled`, `use_llm_assessor`, `emotion_provider_id`, `low_reasoning_friendly_mode`, `low_reasoning_max_context_chars`, `assessment_timing`, `enable_proactive_speech_dispatch`, `enable_proactive_speech_scheduler`, `enable_realtime_chat`, `enable_sticker_reaction`, `enable_low_signal_light_assessment`, `low_signal_max_chars`, `enable_agent_causal_trail`, `runtime_parameter_debug_override_enabled`, `enable_safety_boundary`, `block_deception_manipulation_evasion_actions`, `max_context_chars`, `request_context_max_chars`, `assessor_timeout_seconds`, `provider_id_cache_ttl_seconds`, `passive_load_fresh_seconds`, `assessor_temperature`, `allow_emotion_reset_backdoor`, `enable_psychological_screening`, `enable_shadow_diagnostics` |
| fast assessor | `fast_assessor_enabled`, `fast_assessor_provider_id`, `fast_assessor_max_context_chars`, `fast_assessor_timeout_seconds`, `fast_assessor_temperature` |
| realtime chat | `realtime_chat_style_prompt_enabled`, `realtime_chat_intercept_llm_response`, `realtime_input_completion_llm_gate_enabled`, `realtime_input_completion_probe_delay_seconds`, `realtime_input_completion_max_wait_seconds`, `realtime_user_typing_hold_seconds`, `realtime_empty_input_typing_hold_seconds`, `realtime_chat_dry_run_default`, `realtime_chat_strip_markdown` |
| sticker | `sticker_llm_consistency_check_enabled`, `sticker_default_repo_url`, `sticker_auto_download_enabled`, `sticker_auto_download_repo_url`, `sticker_auto_download_cache_dir`, `sticker_auto_download_timeout_seconds`, `sticker_local_root`, `sticker_allowed_extensions`, `sticker_selected_packs`, `sticker_index_limit`, `sticker_index_cache_ttl_seconds`, `sticker_max_file_bytes`, `sticker_learn_user_images`, `sticker_learned_limit` |
| background queue | `background_post_queue_limit`, `enable_dynamic_background_workers`, `background_post_queue_checkpoint_enabled`, `background_post_checkpoint_debounce_seconds`, `background_post_job_lease_seconds`, `background_post_job_timeout_seconds`, `background_post_retry_max_attempts`, `background_post_retry_base_delay_seconds`, `background_post_retry_max_delay_seconds`, `background_post_dead_letter_limit`, `background_post_diagnostics_warn_lag_count`, `background_post_diagnostics_warn_lag_seconds` |
| agent state | `agent_speaker_relationship_tracking`, `agent_include_speaker_in_assessment`, `agent_identity_profile_limit`, `agent_identity_ttl_seconds`, `agent_trail_limit`, `agent_trail_compaction_enabled`, `agent_trail_low_signal_delta_threshold`, `agent_trail_low_signal_window` |
| state injection | `inject_state`, `state_injection_request_budget_chars`, `state_injection_reserved_chars`, `state_injection_max_added_chars`, `state_injection_max_parts`, `llm_tool_response_max_chars` |
| memory | `enable_sylanne_memory`, `sylanne_memory_idle_commit_delay_seconds`, `sylanne_memory_vector_retrieval_enabled`, `sylanne_memory_embedding_provider_id`, `sylanne_memory_record_embedding_min_interval_seconds`, `sylanne_memory_record_embedding_max_per_flush`, `sylanne_memory_debug_view_enabled`, `allow_sylanne_memory_reset_backdoor` |
| memory write hooks | `humanlike_memory_write_enabled`, `lifelike_learning_memory_write_enabled`, `personality_drift_memory_write_enabled`, `moral_repair_memory_write_enabled`, `fallibility_memory_write_enabled`, `integrated_self_memory_write_enabled` |
| humanlike/lifelike/personality | `humanlike_clinical_like_enabled`, `allow_humanlike_reset_backdoor`, `allow_lifelike_learning_reset_backdoor`, `allow_personality_drift_reset_backdoor` |
| moral/fallibility/integrated self | `enable_moral_repair_state`, `allow_moral_repair_reset_backdoor`, `enable_fallibility_state`, `allow_fallibility_reset_backdoor`, `enable_integrated_self_state`, `allow_relational_self_public_export`, `integrated_self_degradation_profile` |
| benchmark | `benchmark_enable_simulated_time`, `benchmark_time_offset_seconds` |

## `POST /api/settings`

用途：保存配置页改动。

请求 body 为局部更新：

```json
{
  "enabled": true,
  "assessment_timing": "post",
  "sylanne_memory_debug_view_enabled": false
}
```

响应：

```json
{
  "ok": true,
  "updated": ["enabled", "assessment_timing"]
}
```

要求：

- 后端只接受 `_conf_schema.json` 中存在的 key。
- 后端按 schema 类型做二次转换：`bool/int/float/string`。
- 无效 key 忽略；无效 value 不写入，最好在未来加 `errors`。
- 保存后应尽量持久化到 AstrBot 插件配置。

## `GET /api/computation_logs`

用途：替代原来的本地仿真器，展示插件内部每条消息经过 L1-L7 时实际算了什么、输出了什么、耗时多少。

查询参数：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `limit` | int | 50 | 返回最近 N 条，建议后端限制上限 200。 |

响应：

```json
{
  "logs": [
    {
      "ts": 1710000000.0,
      "session": "platform:group:user",
      "text": "用户输入预览",
      "route": "fast",
      "surprise": 0.12,
      "layers": {
        "L1_HDC": {"density": 0.51},
        "L2_Gate": {"surprise": 0.12, "route": "fast"},
        "L3_VoidScar": {"scars": 1, "voids": 0, "coherence": 0.72},
        "L4_Sheaf": {"relation_nodes": 2},
        "L5_HGT": {"decision": [0.12, 0.03, 0.01, 0.08]},
        "L6_Boundary": {"stability": 0.91},
        "L7_Expression": {"drive": 0.21, "should_express": false}
      },
      "assessor": {"valence": 0.3, "arousal": 0.1, "intent": "闲聊"},
      "timing_ns": {
        "perception": 122000,
        "gate": 26000,
        "memory": 2120000,
        "boundary": 91000,
        "expression": 16000
      }
    }
  ],
  "total": 200
}
```

前端会把 `timing_ns` 转换为 ms，并展示每层摘要。后端应保证日志来自真实运行缓冲区，不要再返回前端模拟值。

## `GET /api/memory_pools`

用途：记忆栏目展示 `sylanne_alpha/memory_system.py` 的三层记忆架构。

查询参数：

| 参数 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `session` | string | 当前会话 | 指定会话记忆 |
| `limit` | int | 50 | 每层最多返回 N 条，建议上限 100 |

响应：

```json
{
  "schema_version": "sylanne.webui.memory.v1",
  "architecture": "sylanne_alpha.memory_system.three_layer",
  "session": "platform:group:user",
  "layers": {
    "l1_hot": {
      "label": "L1 Hot Pool",
      "count": 12,
      "capacity": 50,
      "items": []
    },
    "l2_warm": {
      "label": "L2 Warm Pool",
      "count": 24,
      "items": []
    },
    "l3_cold": {
      "label": "L3 Cold Graph",
      "count": 8,
      "edge_count": 14,
      "nodes": [],
      "edges": []
    }
  },
  "summary": {
    "total": 44,
    "l1_count": 12,
    "l2_count": 24,
    "l3_node_count": 8,
    "l3_edge_count": 14,
    "embedded": 10,
    "avg_weight": 0.62,
    "avg_temperature": 0.48
  }
}
```

单条 L1/L2 记忆建议字段：

```json
{
  "id": "memory-id",
  "text": "原始记忆文本",
  "summary": "可选摘要",
  "weight": 0.72,
  "temperature": 0.45,
  "age_ticks": 3,
  "recall_count": 2,
  "created_at": 1710000000.0,
  "has_embedding": true,
  "session_key": "platform:group:user"
}
```

单条 L3 节点建议字段：

```json
{
  "id": "node-id",
  "label": "用户偏好",
  "summary": "用户偏好",
  "type": "preference",
  "temporal_type": "evolving",
  "emotion_weight": 0.3,
  "clarity": 0.82,
  "weight": 0.82,
  "temperature": 0.65,
  "recall_count": 2
}
```

排序要求：

- 后端优先按印象深度排序：`impression_depth > depth > weight > clarity > strength > score`。
- L2/L3 至少应按 `weight/clarity` 降序。
- 前端仍会二次排序，防止旧数据乱序。

## 插件图标资源

当前 WebUI 左上角使用：

```html
<img src="logo.png" alt="Sylanne">
```

在本地 `file://` 预览中可读 `G:/Sylanne_for_astr/logo.png`，但 AstrBot 插件内页面可能因为相对路径变成 `/{PLUGIN_NAME}/logo.png` 或 `/{PLUGIN_NAME}/webui/logo.png` 而 404。

申请后端补齐其中一种稳定方案：

| 方案 | 接口 | 说明 |
| --- | --- | --- |
| 推荐 | `GET /{PLUGIN_NAME}/assets/logo.png` | 返回插件根目录 `logo.png`，`Content-Type: image/png` |
| 兼容 | `GET /{PLUGIN_NAME}/logo.png` | 兼容当前相对路径 |
| 备选 | `GET /api/state` 返回 `theme.logo_url` | 前端读取后动态替换图标地址 |

## 未来可选优化

这些不是当前必须项，但后面如果轮询压力变大，可以申请：

| 接口 | 用途 |
| --- | --- |
| `GET /api/events` SSE | 推送 state/log/memory 增量，替代 3s/5s 轮询 |
| `GET /api/settings/schema` | 单独缓存 schema，减少 settings 响应体 |
| `GET /api/providers` | provider 下拉独立刷新，不必每次拉完整 settings |

## 验收标准

- 本地预览失败时能走 fallback；接入真实插件后不出现空白页。
- `/api/state` 能驱动总览和 7 层动画，动画反映真实状态而不是随机数。
- `/api/computation_logs` 能看到最近消息的 L1-L7 计算摘要和实时耗时。
- `/api/memory_pools` 能看到 L1/L2/L3 三层记忆，列表可滚动并按印象深度排序。
- `/api/settings` 返回 `_conf_schema.json` 全量键，配置页不再出现旧字段或缺字段。
- 插件内页面能正常显示 `logo.png`。
