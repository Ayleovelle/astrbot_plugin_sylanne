# Sylanne-Embodiment WebUI 后端 API 桥接文档

## 概述

后端有两种运行模式，共用同一套 API 路径：

| 模式 | 入口 | 认证 | 前端通信方式 |
|------|------|------|-------------|
| 独立模式 | `http://host:2718/` | Bearer token（header） | `fetch('/api' + path)` |
| Pages 模式 | AstrBot Dashboard iframe | AstrBot 统一认证 | `window.AstrBotPluginPage.fetch(fullPath)` |

---

## 桥接层实现

前端通过统一的 `apiFetch(path)` 函数自动适配两种模式：

```javascript
const PLUGIN_PREFIX = '/astrbot_plugin_sylanne';

async function apiFetch(path, opts = {}) {
  if (isPreview) return mockResponse(path);
  if (window.AstrBotPluginPage) {
    const fullPath = PLUGIN_PREFIX + '/api' + path;
    const resp = await window.AstrBotPluginPage.fetch(fullPath, opts);
    return typeof resp === 'string' ? JSON.parse(resp) : resp;
  }
  const tk = localStorage.getItem('sylanne_token') || '';
  const r = await fetch('/api' + path, {
    ...opts,
    headers: {'Authorization': 'Bearer ' + tk, ...(opts.headers || {})}
  });
  if (r.status === 401) throw new Error('UNAUTHORIZED');
  if (!r.ok) throw new Error('HTTP ' + r.status);
  return await r.json();
}
```

---

## 认证

### 独立模式
- Token 在首次启动时自动生成（`secrets.token_urlsafe(32)`），存入 `config["sylanne_webui_token"]`
- 日志中会打印完整 token 供用户复制
- 请求头：`Authorization: Bearer <token>`
- 白名单路径（无需认证）：`/`、`/logo.png`、`/assets/logo.png`
- 认证失败返回：`{"error": "unauthorized"}` + HTTP 401
- 前端通过 `verifyToken(token)` 调用 `/api/state` 验证 token 有效性

### Pages 模式
- 不需要 token，AstrBot Dashboard 已认证
- 检测到 `window.AstrBotPluginPage` 时跳过登录
- Bridge SDK 路径：`<script src="/api/plugin/page/bridge-sdk.js">`

---

## API 端点

### GET /api/state

查询参数：`?session=<session_key>`（可选）

返回结构（后端实际格式）：
```json
{
  "schema_version": "sylanne.webui.state.v1",
  "tick_count": 142,
  "runtime": {"plugin_name": "astrbot_plugin_sylanne", "runtime_id": "...", "instance_id": "0x..."},
  "current_session": "qq:FriendMessage:12345:67890",
  "session_id": "qq:FriendMessage:12345:67890",
  "sessions": ["session1", "session2"],

  "emotion": {
    "warmth": 0.72, "arousal": 0.45, "valence": 0.68, "tension": 0.23,
    "curiosity": 0.81, "repair_pressure": 0.15, "expression_drive": 0.64,
    "boundary_firmness": 0.77, "coherence": 1.0
  },

  "gate": {
    "precision": 0.34, "mean_surprise": 0.34, "history_len": 60,
    "history": [...], "route": "NORMAL"
  },

  "route_stats": {"fast": 42, "normal": 35, "full": 18, "skip": 5},
  "route_distribution": {"FAST": 42, "NORMAL": 35, "FULL": 18, "SKIP": 5},

  "boundary": {
    "integrity": 0.94, "entropy": 0.12, "stability": 0.88,
    "rotation": 37.0, "phase_transitions": 6, "self_repair_rate": 0.88
  },

  "expression": {
    "mode": "responsive", "pressure": 0.45, "threshold": 0.50
  },

  "timing": [
    {"layer": "L1", "avg": "2.1ms", "p95": "4.8ms", "count": 1247},
    {"layer": "L2", "avg": "3.4ms", "p95": "7.2ms", "count": 1247}
  ],

  "feedback": {
    "accepted": 847, "ignored": 377, "rejected": 23,
    "positive": 847, "negative": 23, "neutral": 377
  },

  "personality": {
    "five": {"openness": 0.82, "warmth": 0.75, "intensity": 0.68, "autonomy": 0.71, "resilience": 0.79},
    "six": [{"name": "Curiosity", "value": 0.81, "color": "#B88A9E"}, ...],
    "drift": [{"time": "2024-01-15 03:22", "text": "Warmth axis shifted +0.04"}, ...]
  },

  "spine_layers": [
    {"id": "L1", "name": "HDC Perception", "status": "active", "avg": 2.1, "p50": 1.8, "p99": 8.5, "count": 1247, "desc": "..."},
    ...
  ],

  "layers": {"L1_HDC": {...}, "L5_HGT": {...}},
  "spine": {"surprise": 0.34, "route": "NORMAL", ...},
  "persona": {"profile": {...}, "traits": {...}, "voice": {}, "drift": {}},
  "social_field": {},
  "life_simulation": {},
  "theme": {"base": "#F3A7C8", "source": "emotion", "mode": "soft"}
}
```

前端通过 `adaptState(raw)` 函数将后端数据规范化为渲染函数期望的格式。

---

### GET /api/settings

返回结构：
```json
{
  "schema": {
    "sylanne_persona_name": {"description": "人格名称", "type": "string", "default": "Sylanne"},
    "sylanne_webui_enabled": {"description": "启用 WebUI", "type": "bool", "default": false},
    ...
  },
  "values": {"sylanne_persona_name": "Sylanne", "sylanne_webui_enabled": true, ...},
  "providers": [{"id": "anthropic-claude", "name": "Anthropic Claude", "type": "llm"}, ...]
}
```

前端通过 `schemaToGroups(schema, values)` 将扁平 schema 按 key 前缀分组为配置面板卡片。

---

### POST /api/settings

请求体：扁平 dict，只传要改的 key
```json
{"sylanne_webui_port": 3000, "sylanne_alpha_realtime_chat_enabled": true}
```

返回：
```json
{"ok": true, "updated": ["sylanne_webui_port", "sylanne_alpha_realtime_chat_enabled"]}
```

---

### GET /api/computation_logs

查询参数：`?limit=50&session=<session_key>`

返回：
```json
{
  "logs": [
    {"time": 1716800000.123, "route": "FAST", "session": "...", "text": "..."},
    ...
  ],
  "total": 1247,
  "total_for_session": 89,
  "session": "..."
}
```

`logs[].time` 是 epoch float，前端通过 `formatLogTime()` 格式化显示。
`logs[].text` 是日志消息文本（后端字段名为 `text`，前端兼容 `msg`/`text`/`message`）。

---

### GET /api/memory_pools

查询参数：`?session=<session_key>&limit=50`

返回（三层架构格式）：
```json
{
  "schema_version": "sylanne.webui.memory.v1",
  "architecture": "sylanne_alpha.memory_system.three_layer",
  "session": "...",
  "layers": {
    "l1_hot": {"label": "L1 Hot Pool", "count": 12, "capacity": 50, "items": [...]},
    "l2_warm": {"label": "L2 Warm Pool", "count": 8, "items": [...]},
    "l3_cold": {"label": "L3 Cold Graph", "count": 3, "edge_count": 5, "nodes": [...], "edges": [...]}
  },
  "hot": [...], "warm": [...], "cold": [...],
  "summary": {"total": 23, "l1_count": 12, "l2_count": 8, ...}
}
```

前端通过 `adaptMemoryPools(resp)` 将三层架构格式转换为 `{L1: [...], L2: [...], L3: [...]}` 供渲染。

---

### GET /api/meltdown_nonce

查询参数：`?session=<session_key>`

返回：
```json
{"nonce": "random_hex_32chars"}
```

Nonce 一次性使用，用于 memory_meltdown 请求验证。

---

### POST /api/memory_meltdown

请求体：
```json
{"session": "session_key", "nonce": "之前获取的nonce"}
```

返回：
```json
{"ok": true, "session": "...", "cleared": true}
```

失败（nonce 无效）：`{"ok": false, "error": "invalid_nonce"}` HTTP 403

---

## AstrBot 注册路由（Pages 模式）

通过 `context.register_web_api()` 注册，路径前缀为 `/astrbot_plugin_sylanne/`：

| 路径 | 方法 | 对应独立模式 |
|------|------|-------------|
| `/astrbot_plugin_sylanne/api/state` | GET | `/api/state` |
| `/astrbot_plugin_sylanne/api/settings` | GET/POST | `/api/settings` |
| `/astrbot_plugin_sylanne/api/computation_logs` | GET | `/api/computation_logs` |
| `/astrbot_plugin_sylanne/api/memory_pools` | GET | `/api/memory_pools` |
| `/astrbot_plugin_sylanne/api/meltdown_nonce` | GET | `/api/meltdown_nonce` |
| `/astrbot_plugin_sylanne/api/memory_meltdown` | POST | `/api/memory_meltdown` |
| `/astrbot_plugin_sylanne/api/webui_probe` | GET | 探针 |
| `/astrbot_plugin_sylanne/webui` | GET | `/`（HTML 页面） |
| `/astrbot_plugin_sylanne/dashboard` | GET | `/`（HTML 页面） |

---

## 数据适配层

前端包含以下适配函数，将后端真实数据转换为渲染函数期望的格式：

| 函数 | 作用 |
|------|------|
| `adaptState(raw)` | 规范化 /api/state 返回值（补全缺失字段、统一大小写、兼容新旧格式） |
| `schemaToGroups(schema, values)` | 将扁平 schema 按 key 前缀分组为配置面板卡片数组 |
| `adaptMemoryPools(resp)` | 将三层架构格式转换为 `{L1, L2, L3}` 数组 |
| `adaptMemItem(item)` | 统一记忆条目字段（text/content/summary → content, 计算 age） |
| `formatLogTime(t)` | epoch float → HH:MM:SS.mmm 格式化 |
| `formatAge(ts)` | epoch float → "2m"/"3h"/"7d" 相对时间 |

---

## iframe sandbox 限制（Pages 模式）

- `localStorage` 不可用（origin 为 null）
- `fetch()` 被 CORS 阻止（必须走 bridge）
- 外部字体 `@font-face url()` 可能加载失败（需系统字体 fallback）
- Bridge SDK 必须在应用脚本之前加载

---

## 独立模式 HTTP Server 细节

- 文件：`sylanne_alpha/webui_server.py`
- 优先 aiohttp（异步），不可用时回退 stdlib `http.server`（多线程）
- 线程安全：`_plugin_access_lock` 保护所有访问插件状态的路由
- 速率限制：每 IP 60 秒内最多 60 次请求
- Body 大小限制：1MB
- CORS：`Access-Control-Allow-Origin: http://127.0.0.1:{port}`
- Dashboard HTML 从 `pages/dashboard/index.html` 启动时读取一次
