# Phase 2A Implementation Review Response

日期：2026-06-19
对象：`docs/architecture/life-simulation-upgrade-phase-2a-implementation-review.md`
修订文件：`memory_system.py` / `life_simulation.py` / `llm_request_pipeline.py`
结论：三条 finding 已全部修复，全量回归 655 passed / 2 skipped / 0 failed，待二审。

---

## 1. HIGH：L3 / ACTIVATION privacy fail-closed 绕口 —— 已修

修复（按 review §40-44 四点）：

1. **不再"无属性=open"隐式放行**：`_apply_privacy_filter` 改为缺 `privacy_level` 属性的对象一律 fail-closed **drop**（memory_system.py `_apply_privacy_filter`）。
2. **GraphNode 显式持隐私字段**：`GraphNode` 新增 `privacy_level: str = "open"`（:389）+ `__post_init__` 规范化（:391）+ `to_dict`/`from_dict` 序列化与迁移。旧图谱无字段 → 显式迁移为 `"open"`（基线可见，行为不变）；非法值 → `__post_init__` fail-closed 降 `internal`。这正是 review §43 要求的"用显式迁移字段表达旧 L3 可见性"，不再隐式放行。
3. **扩散结果必经同一 filter**：`_recall_activation` 在 `_spreading_candidates` + `_apply_emotion_bypass`（两条 filter 之后追加候选的暗路）之后，对最终 `wide` 再过一道 `_apply_privacy_filter`。首道在扩散前摘 internal（不让其作扩散种子），第二道兜住扩散/情感旁路补回的 internal/缺隐私节点。
4. **额外修复 L3 边片段泄露**：发现一条 review 未点名但同源的泄露——`_recall_l3_candidates` 把邻居 label 拼进本节点 text（`拿铁: 拿铁 相关 内部秘密节点`），公共 filter 只看候选 obj 级别、看不到被拼进 text 的邻居。已在边片段组装时跳过任一端为 internal 的边。

测试（review §45-48）：

- `test_graphnode_open_kept_internal_dropped` / `test_attrless_object_failclosed_dropped`
- `test_graphnode_privacy_level_roundtrip` / `test_graphnode_legacy_archive_migrates_to_open` / `test_graphnode_illegal_privacy_failclosed`
- `test_activation_spread_internal_node_not_in_results`（真实扩散路径）/ `test_wide_refilter_drops_internal_from_spreading`
- 原 `_Node`（裸对象视 open）测试已按新 fail-closed 语义改写。

---

## 2. MEDIUM：同轮双重注入 —— 已修

采纳 review 推荐方案①：把 life_sim 写 memory **延后到本轮 recall 之后**执行（llm_request_pipeline.py:1419 记延迟参数、:1514 recall 后无条件补写）。本轮 outreach 注入时该 memory 尚未写入，recall 取不到，避免同一 `life_event_id` 同时进 `outreach_fragment` 与 `memory_fragment`；下一轮才进 recall，且彼时 `life_prompt_fragment` 已按 consumed 跳过。写入仍独立于 recall 是否触发（recall 被 skip 时 memory 照写）。

测试：`test_no_double_injection_same_round_prepare_memory_context`（直调真实 `_prepare_memory_context`，开启 recall，断言同 event 文本不同时出现在两 fragment）+ `test_deferred_write_carries_metadata`（延后写入仍带 source/privacy/confidence/life_event_id）。

---

## 3. MEDIUM：`_mark_life_outcome` 静默吞异常 —— 已修

`_mark_life_outcome` 的 `except Exception: pass` 改为 `logger.warning`，含 `event_id` / `outcome` / 异常类型与消息（llm_request_pipeline.py:2850）；不 raise、不改主流程。

测试：`test_mark_life_outcome_exception_warns_not_raises`（模拟 `mark_outreach_consumed` 抛异常，断言 `_prepare_memory_context` 不中断 + warning 可观测）+ `test_mark_life_outcome_warns_directly`。

---

## 4. 额外根因修复：回调 arity 缓存 id-reuse

二审修复期间，新测试触发了 `_CALLBACK_ARITY_CACHE` 的潜在 bug：它以 `id(cb)` 为键，函数被 GC 后地址可复用，新 callable 命中旧条目拿到错误 arity（跨测试污染，也是生产环境潜在正确性隐患）。已改为以 callable 的 `__code__` 对象为键（dict 持强引用使其存活，天然无 id 复用；bound method 取 `__func__.__code__`）。这是根因修复非测试洗牌。`test_case4b_two_arg_callback_still_supported` 在任意顺序下稳定通过。

---

## 5. 验证（真实数据）

- 全量回归：**655 passed, 2 skipped, 0 failed**（py3.13.14 + pytest 9.0.3）。较一审 645 增 10 个二审修复测试。
- 三个生产文件 AST 解析 OK。
- 新符号核对：`MemoryItem.privacy_level`(:209) / `GraphNode.privacy_level`(:389) + 各自 `__post_init__`；`_apply_privacy_filter` 在 activation 路径两次调用；延后写入 `_deferred_life_sim_write`(:1419/1514)；`_mark_life_outcome` warning(:2850)；`_callback_cache_key`(:310)。
- 既有图谱/扩散套件（test_memory_recall_stage2_spreading 等）全绿，GraphNode 加字段未破坏序列化。

---

## 6. 仍守的边界

- 未新增 LLM；life_sim 未写 user_fact；未接 feedback_pressure / derive_dispatch_policy / origin_session；未改 1.4.0 死树。
- 多会话漂移仍仅审计未修（origin_session 留 2B）。
- 完成报告（`...-implementation-report.md`）将同步更新真实测试数为 655。
