# Embodiment-1.2.5 交接文档

> 状态：已提交并推送至 GitHub。commit `7c512c7`。

## 版本定位

架构治理版本，无新功能。专注代码健康度：God Class 拆分、安全加固、内存管理、异常清理。

## 完成的工作

### Phase 1: WebUI 安全加固

- `webui_server.py` 默认绑定 `127.0.0.1`（不再暴露公网）
- Bearer Token 认证（`_ensure_token` + `auth_middleware`）
- CORS 收紧为 `http://127.0.0.1:{port}`
- Meltdown nonce 防重放
- 全新登录页：品牌动画 + 输入聚焦脉冲 + 错误抖动 + 淡出过渡

### Phase 2: 静默异常清理

- 所有无注释的裸 `except Exception: pass` 已消除
- cleanup 场景加 `# cleanup: failure acceptable` 注释
- 转换异常收窄为 `except (ValueError, TypeError)`

### Phase 3: God Class 拆分

**main.py: 8009 → 2140 行**

抽出 10 个委托模块（全部在 `sylanne_alpha/` 下）：

| 文件 | 类名 | 职责 | 行数 |
|------|------|------|------|
| `session_context.py` | `SessionContext` | 会话 key 派生、host 创建、memory system | ~150 |
| `llm_request_pipeline.py` | `LLMRequestPipeline` | on_llm_request 全流程、memory timer、assessor LLM 调用 | ~1373 |
| `llm_response_pipeline.py` | `LLMResponsePipeline` | on_llm_response、流式分段、payload cap、prompt 注入 | ~846 |
| `proactive_scheduler.py` | `ProactiveScheduler` | 主动发言决策、调度、cooldown | ~200 |
| `public_api.py` | `PublicAPI` | observatory、agent identity、LLM tools、commands | ~1405 |
| `state_persistence.py` | `StatePersistence` | KV key、load/save/delete state、ConvMgr/PersonaMgr 集成 | ~484 |
| `realtime_dispatch.py` | `RealtimeDispatch` | 实时分段发送、history shadow、continuity context | ~597 |
| `background_queue.py` | `BackgroundPostQueue` | 后台评估队列、adaptive worker、checkpoint | ~451 |
| `webui_routes.py` | `WebUIRoutes` | 所有 WebUI HTTP 路由处理器 | ~900 |
| `webui_server.py` (`WebUILifecycle`) | `WebUILifecycle` | WebUI server 生命周期管理 | ~330 |

**委托模式**：所有模块使用 `self._p = plugin`，通过 `self._p` 访问插件属性。main.py 中原方法保留为一行委托 stub。

### Phase 4: LRU 驱逐

- `sylanne_alpha/bounded_dict.py` 提供 `BoundedDict(OrderedDict)`
- 所有 session-keyed 字典替换为 `BoundedDict(maxsize=N, ttl=T)`
- 默认 50 会话上限，防止长期运行内存无限增长

### Phase 5: 清理

- `archive/` 目录已删除（旧 3.x 引擎、开发笔记、论文草稿、body draft）
- `sylanne_alpha/webui.py` 已删除
- 无断裂 import，26 项核心测试通过

## 技术注意事项

1. **main.py 行数**：ruff format 后为 2140 行（计划目标 <2000）。实际逻辑代码约 1614 行，其余为格式化空行和 import fallback stub。如需严格达标，可将 `except ImportError` 的 64 行 fake class 移到 `sylanne_alpha/compat/astrbot_stubs.py`。

2. **_StateInjectionBudget 仍在 main.py**：`llm_response_pipeline.py` 通过 `from main import _StateInjectionBudget` 引用它。后续要彻底解耦需移到独立模块。

3. **WebUI 路由注册**：`_register_web_apis` 直接引用 `self._webui_routes.method`，不再经过 stub。如果 AstrBot 的 `register_web_api` 对 handler 签名有特殊要求，可能需要恢复 wrapper。

4. **模块间无循环依赖**：各模块只依赖 `self._p`（plugin 实例），不互相 import。唯一例外是 `llm_request_pipeline.py` 中的 `ConversationBuffer` 延迟导入。

5. **测试结构检查**：`test_sylanne_alpha_kernel.py::test_alpha_package_contains_only_direct_body_structure` 已更新包含所有新模块。后续加模块需同步更新。

6. **旧测试报错**：`tests/body_genesis/`、`tests/test_*_engine.py` 等引用已删除的 `sylanne_body`/`archive` 模块，收集时会报 ImportError。这些是 3.x/body_draft 时代的遗留测试，对应代码已删除，测试本身也应清理。

## 下个版本可做的事

- 清理遗留测试文件（引用已删除模块的）
- 七层神经脊 Canvas 可视化
- 人格雷达图 + 漂移事件日志
- `_StateInjectionBudget` 移出 main.py
- Fragment debounce 阻止 LLM 调用（AstrBot 框架层面限制）
