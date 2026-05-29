# Sylanne WebUI 后端文件清单

## 后端需要对接的文件

| 文件路径 | 用途 |
|---------|------|
| `main.py` | 插件主入口，所有 `register_web_api` 路由注册和 handler 实现 |
| `sylanne_alpha/webui_server.py` | 独立 aiohttp 服务器（端口 2718），serve HTML + API |
| `sylanne_alpha/webui.py` | `WEBUI_HTML` 内联字符串（独立服务器 fallback 用） |
| `sylanne_alpha/memory_system.py` | 三层记忆系统，`/api/memory_pools` 的数据源 |
| `sylanne_alpha/computation_spine.py` | 7 层计算栈，`/api/state` 的数据源 |
| `_conf_schema.json` | 配置 schema，`/api/settings` 的数据源 |
| `pages/dashboard/index.html` | WebUI 前端页面（AstrBot 插件 Page 入口） |
| `logo.png` | 插件图标 |

## 已注册的后端路由（main.py）

```python
# AstrBot register_web_api 路由
f"/{PLUGIN_NAME}/api/state"              # GET  → _webui_state_get_handler
f"/{PLUGIN_NAME}/api/settings"           # GET  → _webui_settings_get_handler
f"/{PLUGIN_NAME}/api/settings"           # POST → _webui_settings_post_handler
f"/{PLUGIN_NAME}/api/computation_logs"   # GET  → _webui_computation_logs_handler
f"/{PLUGIN_NAME}/api/memory_pools"       # GET  → _webui_memory_pools_handler
f"/{PLUGIN_NAME}/assets/logo.png"        # GET  → _webui_logo_handler
f"/{PLUGIN_NAME}/logo.png"              # GET  → _webui_logo_handler
f"/{PLUGIN_NAME}/dashboard"             # GET  → _webui_dashboard_handler
```

其中 `PLUGIN_NAME = "astrbot_plugin_sylanne"`。

## 前端请求约定

前端统一使用 `apiFetch(path, options)` 函数：

```js
apiFetch('/api/state?session=xxx')           // GET
apiFetch('/api/settings')                     // GET
apiFetch('/api/settings', { method: 'POST', body: JSON.stringify(payload) })  // POST
apiFetch('/api/computation_logs?limit=50')   // GET
apiFetch('/api/memory_pools?limit=50&session=xxx')  // GET
```

`apiFetch` 内部逻辑：
- 有 `window.AstrBotPluginPage` bridge → `bridge.apiGet('api/state', params)` / `bridge.apiPost('api/settings', body)`
- 无 bridge（独立服务器/本地预览）→ 普通 `fetch(apiPath(path), options)`

## 数据源映射

| API 端点 | 数据来自 |
|---------|---------|
| `/api/state` | `host.kernel.computation.engine.observe()` + `.gate.to_dict()` + `.boundary.to_dict()` + `.expression.state()` + `.timing_stats()` + `._last_computation_result` |
| `/api/settings` GET | `_conf_schema.json` + `self._config` |
| `/api/settings` POST | 写入 `self._config`，持久化 |
| `/api/computation_logs` | `self._computation_logs`（deque, maxlen=200） |
| `/api/memory_pools` | `self._memory_system._l1` / `._l2` / `._l3_nodes` / `._l3_edges` |

## 独立服务器（webui_server.py）

配置项：
- `sylanne_webui_enabled`: bool, 默认 false
- `sylanne_webui_host`: string, 默认 "0.0.0.0"
- `sylanne_webui_port`: int, 默认 2718

路由（aiohttp）：
```
GET /                    → serve dashboard HTML
GET /api/state           → same as main.py handler
GET /api/settings        → same
POST /api/settings       → same
GET /api/computation_logs → same
GET /api/memory_pools    → same
GET /assets/logo.png     → serve logo.png
GET /logo.png            → serve logo.png
```

启动方式：在 `on_llm_request` 首次触发时 `asyncio.ensure_future(start_webui_server(...))`。

## 响应格式参考

详见 `G:\Sylanne_for_astr\docs\webui_api_requests.md`。

## 三份入口文件同步规则

1. 先改 `G:\Sylanne_for_astr\webui_preview.html`（主开发文件）
2. 同步到 `pages/dashboard/index.html`（AstrBot 插件 Page）
3. 同步到 `sylanne_alpha/webui.py` 的 `WEBUI_HTML`（独立服务器 fallback）

三份内容必须一致。

## 打包

打包命令：
```bash
cd g:\Sylanne_for_astr\.claude\worktrees\sylanne-kernel-x-body
python scripts/package_plugin.py --output dist/astrbot_plugin_sylanne.zip
```

输出位置：`g:\Sylanne_for_astr\.claude\worktrees\sylanne-kernel-x-body\dist\astrbot_plugin_sylanne.zip`

打包脚本会自动包含 `pages/dashboard/index.html`、`sylanne_alpha/`、`main.py`、`_conf_schema.json`、`logo.png` 等。`dist/` 目录在 `.gitignore` 里，不会被提交。
