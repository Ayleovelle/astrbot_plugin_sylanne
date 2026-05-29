# Sylanne WebUI 部署打通日志

## 固定规则

- 每次上传新包体前，必须清空服务器旧的同名插件目录和旧包体残留。
- 不允许只覆盖 zip 后直接重启，因为 AstrBot 可能继续读取旧解压目录。
- 目标是页面显示真实后端数据，不接受前端 fallback 演示数据作为完成。

## 2026-05-23 / 第 1 轮

### 本地修复

- 统一 `apiFetch()`：AstrBot 插件 Page 走 `window.AstrBotPluginPage.apiGet/apiPost`，独立监听和兼容路由走普通 `fetch()`。
- 修复 `pages/dashboard/index.html` 的重复 `catch` 残留和 settings 请求括号错位。
- 三份入口保持同步：
  - `webui_preview.html`
  - `pages/dashboard/index.html`
  - `sylanne_alpha/webui.py`
- 追加 bridge 时序修复：
  - 显式加载 `/api/plugin/page/bridge-sdk.js`
  - 请求前动态等待 `window.AstrBotPluginPage`
  - `ready()` 最多等待 1.5 秒，失败才 fallback

### 本地验证

- 三份入口内联 JS 语法检查通过。
- `main.py`、`sylanne_alpha/webui.py`、`sylanne_alpha/webui_server.py` 编译通过。

### 待执行

- 打包 zip。
- 连接服务器。
- 停止/清空旧同名插件。
- 上传新包。
- 重启 AstrBot。
- 验证 AstrBot 插件 Page 与 `154.36.178.27:2718` 独立监听页面都显示真实数据。

## 2026-05-23 / 第 2 轮

### 本地包体修复

- 目标目录固定为 `G:\Sylanne_for_astr\.claude\worktrees\sylanne-kernel-x-body`，不使用根目录旧 3.x 工作树打包。
- 新增根包入口 `__init__.py`，避免 zip 缺少 `astrbot_plugin_sylanne/__init__.py`。
- 新增 `requirements.txt`，声明独立 WebUI 监听需要的 `aiohttp>=3.9`。
- 更新 `scripts/package_plugin.py`，确保根 `__init__.py` 与 `requirements.txt` 会进入包体。
- 更新 `scripts/plugin_zip_preflight.js`，把旧 3.x 必需文件清单改为 4.0 alpha 包体契约：
  - `main.py`
  - `_conf_schema.json`
  - `pages/dashboard/index.html`
  - `sylanne_alpha/webui.py`
  - `sylanne_alpha/webui_server.py`
  - `sylanne_alpha/memory_system.py`
  - `sylanne_alpha/compat/__init__.py`

### 本地验证

- `python -m py_compile main.py sylanne_alpha\webui.py sylanne_alpha\webui_server.py sylanne_alpha\memory_system.py` 通过。
- `node --check scripts\plugin_zip_preflight.js` 通过。
- `python scripts\package_plugin.py --output dist\astrbot_plugin_sylanne.zip` 成功。
- `node scripts\plugin_zip_preflight.js dist\astrbot_plugin_sylanne.zip astrbot_plugin_sylanne` 成功，包体大小 `396974` 字节，zip 条目 `49` 个。

### 下一步

- 连接服务器并只读确认 AstrBot 根目录、插件目录、进程管理方式。
- 部署前必须先清空旧同名插件目录、旧上传目录、旧 zip 残留。
- 上传并解压新包后重启 AstrBot。
- 验证插件 Page 与 `http://154.36.178.27:2718/` 均读取真实 API 数据。
