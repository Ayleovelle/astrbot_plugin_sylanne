# Sylanne WebUI 后端连接修复记录

更新日期：2026-05-23  
修复范围：WebUI 前端请求层、AstrBot 插件 Page 入口、独立监听 WebUI 兼容。

## 背景

Sylanne WebUI 现在有两条后端连接路线：

1. AstrBot 插件 Page 路线  
   页面位于 `pages/dashboard/index.html`，运行在 AstrBot Dashboard 的插件页面 iframe 中，应优先使用 `window.AstrBotPluginPage.apiGet/apiPost` 调用插件后端。

2. 独立服务器监听路线  
   代码位于 `sylanne_alpha/webui_server.py`，由 `sylanne_webui_enabled / sylanne_webui_host / sylanne_webui_port` 控制，默认端口 `2718`，直接暴露 `/api/state`、`/api/settings`、`/api/computation_logs`、`/api/memory_pools`。

之前 `pages/dashboard/index.html` 处于半迁移状态：同时混用了 bridge、`apiPath()` 和普通 `fetch()`，并且残留了重复的 `catch` 块，导致插件页内联 JS 语法错误。

## 本次修复

### 0. 部署约束

每次上传新包体前，必须先清空服务器上的旧同名插件：

- 删除旧的 `astrbot_plugin_sylanne` 插件目录。
- 删除旧的同名 zip/缓存解压残留。
- 再放入新包体并重启 AstrBot。

如果不先清空旧插件，AstrBot 可能继续加载旧的 `pages/dashboard/index.html`、旧的 `sylanne_alpha/webui.py` 或旧的 `_conf_schema.json`，导致前端看起来没有连上后端。

### 1. 统一 API 请求层

三份入口均已加入同一套请求函数：

- `pluginBridge`
- `pluginBridgeReady`
- `apiPath(path)`
- `splitApiPath(path)`
- `getPluginBridge()`
- `apiFetch(path, options)`
- `resolveAssetPath(path)`

2026-05-23 追加修复：

- 页面显式加载 `/api/plugin/page/bridge-sdk.js`。
- `pluginBridge` 不再在脚本初始化时固定读取一次，而是在每次请求前动态等待 `window.AstrBotPluginPage`。
- `getPluginBridge()` 最多等待 1.5 秒，避免 AstrBot bridge SDK 注入时序晚于内联脚本时永久走 fallback。

请求规则：

| 运行环境 | 行为 |
| --- | --- |
| AstrBot 插件 Page，存在 `window.AstrBotPluginPage` | `apiFetch('/api/state?...')` 转成 `bridge.apiGet('api/state', params)` |
| AstrBot 插件 Page POST | `apiFetch('/api/settings', { method: 'POST', body })` 转成 `bridge.apiPost('api/settings', payload)` |
| 独立监听服务器 `http://host:2718/` | 普通 `fetch('/api/state?...')` |
| AstrBot 兼容路由 `/{PLUGIN_NAME}/webui` 或 `/{PLUGIN_NAME}/dashboard` | 普通 `fetch('/{PLUGIN_NAME}/api/state?...')` |
| 本地 `file://` 预览 | 请求失败后走原有 offline fallback |

### 2. 修复 dashboard JS 语法错误

已把坏掉的 `pages/dashboard/index.html` 机械同步为修好的 `webui_preview.html`。

修复掉的问题：

- 删除重复残留的 `catch` / `return fetch` 块。
- 修复 `Unexpected token 'catch'` 导致的整页脚本不执行。
- 修复 settings 保存/读取处的括号错位。

### 3. 统一业务 API 调用

业务请求现在全部使用原始 API path，不再把 `apiPath()` 的结果传入 `apiFetch()`。

当前调用形式：

```js
apiFetch('/api/settings', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(payload)
});

apiFetch('/api/settings', { cache: 'no-store' });
apiFetch('/api/computation_logs?limit=50', { cache: 'no-store' });
apiFetch(`/api/memory_pools?limit=50&session=${encodeURIComponent(currentSession)}`, { cache: 'no-store' });
apiFetch(`/api/state?session=${encodeURIComponent(currentSession)}`, { cache: 'no-store' });
```

这样 bridge 模式下 endpoint 会保持为：

- `api/settings`
- `api/computation_logs`
- `api/memory_pools`
- `api/state`

对应后端已有注册：

- `/{PLUGIN_NAME}/api/settings`
- `/{PLUGIN_NAME}/api/computation_logs`
- `/{PLUGIN_NAME}/api/memory_pools`
- `/{PLUGIN_NAME}/api/state`

### 4. 修复插件图标路径

WebUI 不再只依赖静态的 `src="logo.png"`，加载时会执行：

```js
const logoImg = document.querySelector('.logo-icon img');
if (logoImg) logoImg.src = resolveAssetPath('/logo.png');
```

路径结果：

| 运行环境 | 图标路径 |
| --- | --- |
| 本地 `file://` | `logo.png` |
| 独立监听服务器 | `/logo.png` |
| `/{PLUGIN_NAME}/webui` 或 `/dashboard` | `/{PLUGIN_NAME}/logo.png` |
| 插件 Page fallback | `/{PLUGIN_NAME}/logo.png` |

后端已经注册了兼容资源路由：

- `/{PLUGIN_NAME}/assets/logo.png`
- `/{PLUGIN_NAME}/logo.png`

### 5. 三份 WebUI 入口保持一致

当前三份内容已同步一致：

- `webui_preview.html`
- `.claude/worktrees/sylanne-kernel-x-body/pages/dashboard/index.html`
- `.claude/worktrees/sylanne-kernel-x-body/sylanne_alpha/webui.py` 中的 `WEBUI_HTML`

后续如果改 WebUI，建议先改 `webui_preview.html`，确认后同步到另外两个入口，避免 dashboard 再次变成半迁移状态。

## 后端路线建议

保留双通道：

| 路线 | 用途 | 是否推荐默认 |
| --- | --- | --- |
| AstrBot 插件 Page + bridge | 插件管理页主入口，路径和鉴权由 AstrBot 处理 | 推荐 |
| 独立 aiohttp 监听 | 本地/局域网调试、独立观测面板 | 可选，默认关闭 |

独立监听路线如果 `host=0.0.0.0`，会暴露到局域网，不走 AstrBot Dashboard 鉴权。建议默认继续关闭，并在配置项 hint 中明确提示安全风险。

## 验证结果

已执行：

```text
webui_preview.html: inline JS syntax OK
pages/dashboard/index.html: inline JS syntax OK
sylanne_alpha/webui.py: inline JS syntax OK
preview == dashboard: true
preview == webui.py: true
```

还需要在真实 AstrBot 页面中验证：

- 插件详情页能打开 `pages/dashboard/index.html`。
- bridge 下 `apiGet('api/state')` 能命中 `/{PLUGIN_NAME}/api/state`。
- 独立监听 `http://host:2718/` 能正常访问同一套 UI 和 `/api/*`。
