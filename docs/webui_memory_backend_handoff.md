# Sylanne WebUI Memory Backend Handoff

更新时间：2026-05-23

## 本轮修复范围

- 总览页“系统状态监控”改为只展示 8 个表象体征：
  - 活跃度、正负价、紧张度、好奇度、自愈压力、表达驱动、身份边界、内部和平度。
  - Void/Ghost/敏感度/8 维偏移等内部计算指标不再放在总览，继续由计算脊柱、日志或专门图层承载。
- `/api/memory_pools?session=default` 改为总览模式：
  - 聚合已知真实 session 的记忆池。
  - 响应新增 `mode: "overview"` 与 `sessions`。
- 非 default session 不再因为尚未进入 live host/cache 就被回退到 default：
  - `requested` session 会进入候选。
  - 后端会扫描 `sylanne_alpha_root/*.alpha.json` 作为已知 session。
- 三层 `MemorySystem` 空时，会从旧 `body.memory.traces` 热启动：
  - 避免升级/覆盖安装后 WebUI 看起来“记忆池清空”。
  - 热启动结果写回 `body.memory["_memory_system"]`，并随 `.alpha.json` 保存。
- `.alpha.json` 现在会保留 `memory._memory_system`：
  - `AlphaBodyState.from_dict()` 恢复 `_memory_system`。
  - `AlphaBodyState.to_dict()` 持久化 `_memory_system`。

## 接口行为

### GET `/api/memory_pools`

请求：

```text
/api/memory_pools?session=default&limit=50
/api/memory_pools?session=<真实会话>&limit=50
```

响应关键字段：

```json
{
  "schema_version": "sylanne.webui.memory.v1",
  "architecture": "sylanne_alpha.memory_system.three_layer",
  "session": "default",
  "mode": "overview",
  "sessions": ["default", "..."],
  "layers": {
    "l1_hot": { "items": [] },
    "l2_warm": { "items": [] },
    "l3_cold": { "nodes": [], "edges": [] }
  },
  "hot": [],
  "warm": [],
  "cold": [],
  "summary": {
    "total": 0,
    "l1_count": 0,
    "l2_count": 0,
    "l3_node_count": 0,
    "l3_edge_count": 0,
    "legacy_trace_count": 0,
    "embedded": 0,
    "avg_weight": 0,
    "avg_temperature": 0.5
  }
}
```

说明：

- `session=default` 是总览，不代表只读空 default 会话。
- `session=<真实会话>` 是单会话模式，响应 `mode: "session"`。
- 前端应优先读 `layers.l1_hot.items`、`layers.l2_warm.items`、`layers.l3_cold.nodes`。
- `hot/warm/cold` 是兼容字段。
- 记忆排序由前端 `sortMemoriesByDepth()` 按印象深度/weight 排序。

## 真实数据来源优先级

单个 session 的来源顺序：

1. live `_sylanne_memory_cache` 中有内容的 `MemorySystem`。
2. live `_memory_systems` 中有内容的 `MemorySystem`。
3. AstrBot KV：`sylanne:memory:<safe_session>`。
4. `.alpha.json` 中的 `body.memory._memory_system`。
5. 如果三层为空，则 fallback 到 `.alpha.json` 的 `body.memory.traces`。

注意：空的 live `MemorySystem("default")` 不再抢在 KV / `.alpha.json` 前面返回。

## 修改文件

- `main.py`
  - `_webui_memory_pools_handler`
  - `_known_webui_sessions`
  - `_load_sylanne_memory_state`
  - `_save_sylanne_memory_state`
  - `_host`
  - 新增 `_memory_system_has_content`
  - 新增 `_hydrate_memory_system_from_body_traces`
- `sylanne_alpha/body.py`
  - `AlphaBodyState.from_dict`
  - `AlphaBodyState.to_dict`
- `sylanne_alpha/webui_server.py`
  - `_known_sessions`
  - `_build_memory_pools`
  - `_build_memory_pools_sync`
  - 新增 memory payload 聚合 helper
- `pages/dashboard/index.html`
  - 总览状态指标收窄为 8 项表象体征
- `sylanne_alpha/webui.py`
  - 同步 dashboard fallback HTML
- `G:\Sylanne_for_astr\webui_preview.html`
  - 同步本地预览 HTML

## 本地验证

已通过：

```powershell
python -m py_compile main.py sylanne_alpha\webui.py sylanne_alpha\webui_server.py sylanne_alpha\memory_system.py sylanne_alpha\body.py sylanne_alpha\runtime.py
python -m pytest -q tests\test_sylanne_alpha_kernel.py tests\test_memory_system.py
node <inline JS parse check>
```

结果：

- `88 passed`
- dashboard / preview 内联 JS parse OK
- legacy traces 热启动与 default 总览聚合内联测试 OK

## 后续建议

- 如果要让 `default` 在状态页也成为完整总览，需要另外定义 `/api/state?session=default` 的聚合语义；本轮只保证记忆池 default 总览是真实聚合。
- 如果后端未来新增长期图记忆抽取，继续写入 `MemorySystem._l3_nodes/_l3_edges` 即可，WebUI 已按三层结构读取。
