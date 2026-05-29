# Sylanne-Embodiment 工作区交接文档

更新时间：2026-05-23 23:30

## 当前工作区

```
g:\Sylanne_for_astr\.claude\worktrees\sylanne-kernel-x-body\
```

分支：`worktree-sylanne-kernel-x-body`（未推送到 main）

## 版本状态

- **GitHub main 分支**：Embodiment-1.1.5（上次推送）
- **本地工作区**：大量未提交改动（记忆系统 v1、WebUI 对接、前端修复、API 端点等）
- **最新包体**：`dist/astrbot_plugin_sylanne.zip`（419KB，本地测试用）

## 核心文件清单

### 插件运行时

| 文件 | 职责 | 状态 |
|------|------|------|
| `main.py` | 插件主入口，所有 hook/API/调度 | 大量改动，未提交 |
| `sylanne_alpha/computation_spine.py` | 7 层计算栈 | 已加 `_last_hdc_vec` + `last_hdc_sample` |
| `sylanne_alpha/memory_system.py` | 三层记忆系统 v1 实现 | 完成，106 测试通过 |
| `sylanne_alpha/void_scar_engine.py` | Void-Scar 引擎 | 已改 `observe()` 返回命名维度 |
| `sylanne_alpha/relational_sheaf.py` | 关系层论 | 完成 |
| `sylanne_alpha/rhythm_learner.py` | 节奏学习 | 完成 |
| `sylanne_alpha/assessor_async.py` | 异步 LLM assessor | 已加 `m` 字段（memorable） |
| `sylanne_alpha/webui_server.py` | 独立 WebUI 服务器 | 大量改动（含 stdlib fallback） |
| `sylanne_alpha/body.py` | Body 状态 | 已加 `_memory_system` 持久化 |
| `sylanne_alpha/embedding_memory.py` | 旧记忆召回（legacy） | 标记为 legacy |
| `_conf_schema.json` | 配置 schema | 已加 WebUI 配置项 |

### WebUI

| 文件 | 职责 | 状态 |
|------|------|------|
| `pages/dashboard/index.html` | AstrBot 插件页面入口（唯一 HTML） | 最新版，5100+ 行 |
| `sylanne_alpha/webui.py` | `WEBUI_HTML` 内联（独立服务器 fallback） | 旧版，需同步 |
| `G:\Sylanne_for_astr\webui_preview.html` | 本地预览开发文件 | 可能和 dashboard 不同步 |

**注意**：独立服务器 (`webui_server.py`) 直接读 `pages/dashboard/index.html`，不再用 `WEBUI_HTML`。所以只需维护一份 HTML。

### 理论文档

| 文件 | 内容 |
|------|------|
| `theory/scar_algebra/` | 伤痕代数公理+定理 |
| `theory/void_calculus/` | 空洞微积分公理+定理 |
| `theory/relational_sheaf/` | 关系层论公理+定理 |
| `theory/memory_architecture.md` | 记忆系统 v1 架构设计 |
| `theory/memory_dynamics.md` | 记忆衰减数学规范 |
| `theory/memory_graphrag_prompts.md` | GraphRAG 压缩 prompt |

### 设计文档（待实现）

| 文件 | 内容 | 状态 |
|------|------|------|
| `docs/memory_system_v2_design.md` | 记忆系统 v2 完整设计 | **待确认后实现** |
| `docs/webui_api_requests.md` | WebUI API 契约 | 已实现 |
| `docs/webui_backend_files.md` | 后端文件清单 | 参考用 |
| `docs/webui_backend_connection_fix.md` | 连接修复记录 | 已完成 |
| `docs/webui_memory_backend_handoff.md` | 记忆后端交接 | 已完成 |

### 测试

| 文件 | 覆盖 | 状态 |
|------|------|------|
| `tests/test_memory_system.py` | 三层记忆 62 个测试 | 全部通过 |
| `tests/test_sylanne_alpha_kernel.py` | 内核+模块列表 | 全部通过 |
| `tests/test_sylanne_alpha_host.py` | Host 生命周期 | 全部通过 |
| `tests/test_rhythm_learner.py` | 节奏学习 | 全部通过 |

## 已注册的后端 API

| 方法 | 路由 | Handler |
|------|------|---------|
| GET | `/{PLUGIN_NAME}/api/state` | `_webui_state_handler` |
| GET | `/{PLUGIN_NAME}/api/settings` | `_webui_settings_get_handler` |
| POST | `/{PLUGIN_NAME}/api/settings` | `_webui_settings_post_handler` |
| GET | `/{PLUGIN_NAME}/api/computation_logs` | `_webui_computation_logs_handler` |
| GET | `/{PLUGIN_NAME}/api/memory_pools` | `_webui_memory_pools_handler` |
| POST | `/{PLUGIN_NAME}/api/memory_meltdown` | `_webui_memory_meltdown_handler` |
| GET | `/{PLUGIN_NAME}/assets/logo.png` | `_webui_logo_handler` |
| GET | `/{PLUGIN_NAME}/logo.png` | `_webui_logo_handler` |
| GET | `/{PLUGIN_NAME}/dashboard` | `_webui_dashboard_handler` |

## 已知问题

### 高优先级

1. **记忆系统 v1 设计有缺陷**：每条消息写原文到 L1，没有摘要，embedding 从未成功存储，L2/L3 永远为空。需要按 v2 设计重写。
2. **前端 sample_bits**：后端已提供，前端绑定已修，但需要验证实际效果。
3. **独立 WebUI 服务器**：`ensure_future` 在 `__init__` 里不被调度。已改为在 `on_llm_request` 首次触发时启动，但用户反馈仍连不上（可能是防火墙/Docker 端口映射问题）。

### 中优先级

4. **assessor 延迟**：远程 API 3-4s，前台 fast assessor 2s timeout 永远超时。已改为 fallback 到上一轮后台结果。
5. **main assessor 没跑**：之前限制只在 full 路由时跑，已改为每条消息都跑。但用户未确认是否生效。
6. **`webui_preview.html` 和 `pages/dashboard/index.html` 可能不同步**：隔壁 agent 改了 preview，我改了 dashboard。需要确认哪个是最新的。

### 低优先级

7. **`sylanne_alpha/webui.py` 的 `WEBUI_HTML` 是旧版**：独立服务器已不用它（直接读文件），但作为 fallback 存在。
8. **20+ 处 bare `except: pass`**：不影响功能但会吞错误。
9. **旧 `embedding_memory.py` 仍被 public API facade 引用**：标记为 legacy 但未删除。

## 待办事项

### 立即

- [ ] 确认 main assessor 是否在跑（看日志有没有 assessment 结果）
- [ ] 确认 WebUI 前端修复效果（sample_bits、路由统计、timing）
- [ ] 决定是否推送当前状态到 main

### 记忆系统 v2（确认设计后）

- [ ] 实现 `ConversationBuffer` 暂存
- [ ] 实现会话结束检测（1min 无消息）
- [ ] 实现 20 轮保底摘录
- [ ] 实现 LLM 摘要生成
- [ ] 实现 12h 定时整理
- [ ] 实现召回后重写（reconsolidation v2）
- [ ] 实现 30 天未提起 → L3 压缩
- [ ] 更新测试

### WebUI

- [ ] 验证 AstrBot bridge 数据流通
- [ ] 独立服务器端口问题排查
- [ ] 三份 HTML 同步确认

## 打包命令

```bash
cd g:\Sylanne_for_astr\.claude\worktrees\sylanne-kernel-x-body
python scripts/package_plugin.py --output dist/astrbot_plugin_sylanne.zip
```

## 推送命令（确认后执行）

```bash
git add -A
git commit -m "feat: Embodiment-1.2.0 — 三层记忆系统 + WebUI 对接 + 前端修复"
git push origin worktree-sylanne-kernel-x-body:main --force
gh release create Embodiment-1.2.0 dist/astrbot_plugin_sylanne.zip --title "Sylanne-Embodiment 1.2.0" --notes "..."
```
