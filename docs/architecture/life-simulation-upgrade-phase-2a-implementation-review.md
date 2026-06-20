# Phase 2A Implementation Review

日期：2026-06-19  
对象：Phase 2A PR-D / PR-E / PR-F 实现  
报告：`docs/architecture/life-simulation-upgrade-phase-2a-implementation-report.md`  
结论：**Changes Requested**

总体判断：PR-D 的 `MemoryItem` 字段契约、`write_summary` 扩参、M8 `* 0.0` 守线、life_sim 写 memory metadata 这些主方向基本落地。但当前实现还不能 commit / 合并，因为 PR-E 的 privacy fail-closed 仍有绕口，PR-F 的可观测性声明也没有完全兑现。

---

## 1. Findings

### HIGH：L3 / ACTIVATION 仍可能绕过 privacy fail-closed

位置：
- `sylanne_alpha/memory_system.py:1501-1543`
- `sylanne_alpha/memory_system.py:1985-1989`
- `sylanne_alpha/memory_system.py:1944-1962`
- `tests/test_source_aware_recall_pre.py:50-55`

`_apply_privacy_filter` 当前把没有 `privacy_level` 属性的对象视为 `"open"`：

```text
obj 无 privacy_level 属性（如 L3 GraphNode 等结构节点）→ 视为 "open"
```

这与 `life-simulation-upgrade-phase-2a-implementation-ruling.md` §3 冲突。裁决要求：candidate 缺 privacy 字段时，优先从 `source_obj.privacy_level` 读取；若仍缺失或非法，按 `"internal"` / drop 处理，不能直接进入用户可见 prompt。

更严重的是 ACTIVATION 路径在 `_apply_privacy_filter(pool)` 之后又执行：

```text
pool.extend(self._spreading_candidates(...))
```

这些 spreading candidates 由 L3 `GraphNode` 生成，之后没有再经过 `_apply_privacy_filter`。所以即便初始 pool 已过滤，扩散出来的 L3 节点仍能绕过公共隐私层。

风险不是纯理论：L2 -> L3 压缩链路会把记忆抽成 `GraphNode`，而当前 `GraphNode` 没有 privacy metadata。一旦 internal/life_sim 内容进入 L3 或扩散邻居，用户可见 recall 会失去 fail-closed 保障。

要求修改：

1. 不要把“无 `privacy_level` 属性”默认当 `"open"`。要么 drop，要么给 `GraphNode` 显式补 `privacy_level` 并在 `from_dict` / 迁移 / ingest 时规范化。
2. 如果要保留旧 L3 图谱可见性，必须通过显式迁移字段表达，例如旧图谱节点 `privacy_level="open"`；不要在 filter 内用“缺字段=open”隐式放行。
3. ACTIVATION 的 `_spreading_candidates` 结果必须经过同一个 privacy filter，或在生成时复用同一可见性判断。
4. 测试补上真实 L3/扩散路径：
   - 直接 L3 node 缺 privacy 不进入 user-visible recall，除非显式迁移为 open。
   - ACTIVATION spread 出来的 node 缺/非法 privacy 不进入结果。
   - 若新增 `GraphNode.privacy_level`，覆盖 `to_dict/from_dict` roundtrip。

---

### MEDIUM：同一 pending life event 可能在同一轮 prompt 中双重注入

位置：
- `sylanne_alpha/llm_request_pipeline.py:1416-1460`
- `sylanne_alpha/llm_request_pipeline.py:1462-1524`
- `tests/test_m8_guardrail_prf.py:116-132`

`_prepare_memory_context` 现在的顺序是：

1. pop pending outreach；
2. 生成 `[life_event_context]`；
3. 立即 `write_summary(... source="life_sim", life_event_id=...)`；
4. 随后执行 memory recall 并生成 `[记忆参考]`。

由于新写入的 memory 是刚创建的近期记忆，`_gather_pool` 的 temporal proximity 兜底可能让它在同一轮 recall 中出现。于是同一个 `life_event_id` 有机会同时出现在 `outreach_fragment` 和 `memory_fragment`，正好违背 handoff §2.3 的“同一 life event 不重复注入”。

现有 `test_no_double_injection_same_event_id` 只测 `life_prompt_fragment()` consumed 后跳过，没有直调 `_prepare_memory_context` 验证 `outreach_fragment + memory_fragment` 不并存，所以这条没有被覆盖。

要求修改，二选一：

1. 推荐：把 life_sim memory 写入延后到 recall 之后，避免本轮刚写入就被召回。
2. 或者：在本轮 recall 结果中过滤掉 `source_obj.life_event_id == outreach_ctx["event_id"]` 的结果，只允许下一轮再被 recall 注入。

测试补：直调真实 `_prepare_memory_context`，构造未过期 pending、开启 recall 条件，断言同一 `event_id` 的文本不会同时出现在 `outreach_fragment` 和 `memory_fragment`。

---

### MEDIUM：`_mark_life_outcome` 仍静默吞异常

位置：
- `sylanne_alpha/llm_request_pipeline.py:2820-2836`

实现报告说“静默吞异常改成 warning”，但这只覆盖了 life_sim 写 memory 的 `except`。`_mark_life_outcome` 里仍然是：

```text
except Exception:
    pass
```

这不符合 implementation ruling §5：`_mark_life_outcome` 的静默 `pass` 要改成 warning，但不要 raise，不改变主流程。

要求修改：

1. `_mark_life_outcome` 捕获异常时记录 `logger.warning`，包含 `event_id`、`outcome`、异常类型/消息。
2. 保持不 raise，不改变主流程。
3. 补测试：模拟 `mark_outreach_consumed` 抛异常，断言 `_prepare_memory_context` 不中断且 warning 可观测。

---

## 2. 已认可项

以下内容本轮认可：

1. `MemoryItem.confidence/privacy_level/life_event_id` 字段与 `to_dict/from_dict` 基本闭合。
2. `write_summary` 扩参向后兼容，life_sim 写入传 `source="life_sim"`、`confidence=0.5`、`privacy_level="shareable"`、`life_event_id`。
3. 非法 `privacy_level` 在 `MemoryItem` 构造边界 fail-closed 为 `"internal"`，方向正确。
4. `_source_aware_rank` 以 `final_score` 为主序，只在同分时用 source/confidence，方向正确。
5. `_evaluate_share_intent` / `_recompute_final` 保持 `unanswered_penalty * 0.0`，未看到真实接入 `feedback_pressure` / `derive_dispatch_policy` / `origin_session`。
6. `life_prompt_fragment` 跳过 consumed/dropped 是 handoff §2.3 范围内的去重交付，不需要单独报架构例外。

---

## 3. Gate 判断

当前 Phase 2A 实现 **不允许 commit / push**。

请先提交修复回应：

```text
docs/architecture/life-simulation-upgrade-phase-2a-implementation-review-response.md
```

最小通过条件：

1. L3 / GraphNode / spreading candidates 的 privacy fail-closed 闭合。
2. `_prepare_memory_context` 同一 `life_event_id` 不会同轮双重注入。
3. `_mark_life_outcome` 异常 warning 可观测。
4. 对应测试补齐，完成报告更新真实测试数。

修完后再进入二审；现在不要 commit。
