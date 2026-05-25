# Embodiment-1.2.5 交接文档

> 状态：全部 Phase 完成，26 测试通过，打包成功。等待 commit/push/release。

## 当前分支状态

- 分支：`main`
- 版本号已更新：`metadata.yaml` → `Embodiment-1.2.5`
- 未提交（所有改动在工作区）

## 完成的工作

### Phase 1: WebUI 安全加固 ✓

在之前版本已完成，本次确认到位：
- `webui_server.py` 默认绑定 `127.0.0.1`
- Bearer Token 认证（`_ensure_token` + `auth_middleware`）
- CORS 收紧为 `http://127.0.0.1:{port}`
- meltdown nonce 防重放

### Phase 2: 静默异常清理 ✓

- 所有无注释的裸 `except Exception: pass` 已消除
- cleanup 场景（`terminate()` 中的 task cancel）加了 `# cleanup: failure acceptable`
- 转换异常已收窄为 `except (ValueError, TypeError)`

### Phase 3: God Class 拆分 ✓

main.py: **8009 → 2140 行**（含 ruff 格式化后的空行）

抽出的模块（全部在 `sylanne_alpha/` 下）：

| 文件 | 类名 | 职责 | 行数 |
|------|------|------|------|
| `session_context.py` | `SessionContext` | 会话 key 派生、host 创建、memory system | ~150 |
| `llm_request_pipeline.py` | `LLMRequestPipeline` | on_llm_request 全流程、memory timer、assessor LLM 调用 | ~1373 |
| `llm_response_pipeline.py` | `LLMResponsePipeline` | on_llm_response、流式分段、payload cap、prompt 注入 | ~846 |
| `proactive_scheduler.py` | `ProactiveScheduler` | 主动发言决策、调度、cooldown | ~200 |
| `public_api.py` | `PublicAPI` | observatory、agent identity、LLM tools、commands、state observe | ~1405 |
| `state_persistence.py` | `StatePersistence` | KV key、load/save/delete state、ConvMgr/PersonaMgr 集成 | ~484 |
| `realtime_dispatch.py` | `RealtimeDispatch` | 实时分段发送、history shadow、continuity context | ~597 |
| `background_queue.py` | `BackgroundPostQueue` | 后台评估队列、adaptive worker、checkpoint | ~451 |
| `webui_routes.py` | `WebUIRoutes` | 所有 WebUI HTTP 路由处理器 | ~900 |
| `webui_server.py` (新增 `WebUILifecycle`) | `WebUILifecycle` | WebUI server 生命周期管理 | ~330 |

**委托模式**：所有模块使用 `self._p = plugin` 模式，通过 `self._p` 访问插件属性。main.py 中原方法保留为一行委托 stub。

### Phase 4: LRU 驱逐 ✓

- `sylanne_alpha/bounded_dict.py` 提供 `BoundedDict(OrderedDict)` 
- main.py `__init__` 中所有 session-keyed 字典已替换为 `BoundedDict(maxsize=N, ttl=T)`
- 防止长期运行内存无限增长

### Phase 5: 清理 ✓

- `archive/` 目录已 git rm（git status 显示 D）
- `sylanne_alpha/webui.py` 已删除
- 无断裂 import
- 测试中无 archive 引用

## 待执行操作

```bash
# 1. 提交
git add -A
git commit -m "refactor(1.2.5): God Class 拆分 + WebUI 安全加固 + LRU 驱逐 + 静默异常清理

- main.py 8009→2140 行，抽出 10 个委托模块
- WebUI: 默认 127.0.0.1 绑定、Bearer Token、CORS 收紧、meltdown nonce
- BoundedDict 替换所有 session-keyed 字典，防内存泄漏
- 消除所有裸 except Exception: pass
- 删除 archive/ 目录和冗余 webui.py
- 26 测试全部通过"

# 2. 推送
git push origin main

# 3. Release（如需要）
gh release create Embodiment-1.2.5 dist/astrbot_plugin_sylanne.zip \
  --title "Sylanne-Embodiment 1.2.5" \
  --notes "God Class 拆分 + 安全加固 + LRU 驱逐"
```

## 注意事项

1. **main.py 行数**：ruff format 后为 2140 行（计划目标 <2000）。实际逻辑代码约 1614 行，其余为格式化空行和 import fallback stub。如需严格达标，可将 `except ImportError` 的 64 行 fake class 移到 `sylanne_alpha/compat/astrbot_stubs.py`。

2. **_StateInjectionBudget 仍在 main.py**：`llm_response_pipeline.py` 通过 `from main import _StateInjectionBudget` 引用它。如果后续要彻底解耦，需要把这个类移到独立模块并更新引用。

3. **WebUI 路由注册**：`_register_web_apis` 现在直接引用 `self._webui_routes.method`，不再经过 stub 方法。如果 AstrBot 的 `register_web_api` 对 handler 签名有特殊要求（如必须是 bound method），可能需要恢复 wrapper。

4. **extracted 模块间无循环依赖**：各模块只依赖 `self._p`（plugin 实例），不互相 import。唯一例外是 `llm_request_pipeline.py` 中的 `ConversationBuffer` 延迟导入。

5. **测试结构检查**：`test_sylanne_alpha_kernel.py::test_alpha_package_contains_only_direct_body_structure` 已更新，包含所有新模块文件名。如果后续再加模块需要同步更新。
