# Phase 2A Implementation Ruling

日期：2026-06-19  
对象：`docs/architecture/life-simulation-upgrade-phase-2a-handoff.md`（v3）  
结论：**Approved to Implement（D -> E -> F 一口气实现，统一回报）**

本裁决只回答实现侧两个待确认点，并补充边界纪律。执行侧可以开工。

---

## 1. 命名裁决

采用 handoff 钦定命名：`MemoryItem.confidence: float`。**不要改成 `confidence_score`**。

理由：

1. handoff / ADR / preflight / `to_dict` 键都已经固定为 `confidence`，实现层不要再制造文档与代码不一致。
2. 现有 `MemoryResult.confidence: str` 确实同名，但它是召回结果的清晰度分级（`clear` / `vague` / `tot`），而 `MemoryItem.confidence: float` 是记忆条目元数据置信分。二者在不同 dataclass 上，短期可接受。
3. 若未来要清理命名，应另开兼容迁移，把 `MemoryResult.confidence` 改为 `recall_confidence_label` 之类；不要在 Phase 2A 扩大 blast radius。

实现要求：

- `MemoryItem.__post_init__` / `from_dict` / `write_summary` 内部可以用局部变量名 `memory_confidence`、`confidence_value` 避免阅读歧义。
- 注释必须写清：`MemoryItem.confidence` 是 float metadata；`MemoryResult.confidence` 是 recall label。
- preflight 继续检查 `MemoryItem` 的 `confidence` 字段和 `to_dict()["confidence"]`。

---

## 2. 实现顺序裁决

同意按 **PR-D -> PR-E -> PR-F** 一口气实现后统一跑全测、统一提交完成报告。

但报告必须按三块列清：

1. **PR-D Memory Contract**：字段、规范化、迁移、roundtrip、`write_summary` 扩参。
2. **PR-E Source-Aware Recall**：公共 privacy filter、source-aware rank、三模式覆盖。
3. **PR-F M8 Guardrail**：`unanswered_penalty` 不消费、`* 0.0` 保持、life_sim 写 memory metadata、异常 warning。

D/E 可以一起回报，因为 kickoff 要求 H1/H2 同阶段闭合；F 是 guardrail，不得变成真实接 `feedback_pressure`。

---

## 3. Fail-Closed 边界

实现侧提出“比 handoff 更 fail-closed”的方向批准，但必须区分旧档迁移与运行时异常：

1. **旧档缺字段 / 旧调用缺参**：仍迁移为 `privacy_level="open"`。这是历史 dialogue memory 的兼容基线，不得把旧记忆整体变成不可见。
2. **未知/非法 `privacy_level` 字符串**：规范化为 `"internal"` 并 `logger.warning`，不得兜底为 `"open"`。
3. **candidate dict 缺 privacy 字段**：优先从 `source_obj.privacy_level` 读取；若仍缺失或非法，按 `"internal"` / drop 处理。不要让缺字段候选直接进入用户可见 prompt。
4. **`_apply_privacy_filter` 异常**：返回空结果并 warning，绝不返回未过滤池。
5. **`_source_aware_rank` 异常**：可以保留“已经过 privacy filter 的顺序”作为降级；不能绕过 privacy filter。

换句话说：旧数据兼容在 `from_dict` / `write_summary(None)` 边界完成；进入 recall 公共层后，未知状态一律按不可见处理。

---

## 4. PR-E 排序纪律

`_source_aware_rank` 只做 tiebreaker / 稳定排序增强，不得推翻现有 LEGACY 主序。

要求：

- `final_score` 或当前 relevance 主序保持第一优先级。
- `source` 优先级只在同分或近似同分时生效：`user_fact` > `dialogue/open` > `life_sim`；`life_reflection` 仅保留兼容，不新增语义生产者。
- `confidence` 只做同 source / 同 relevance 下的 tiebreaker。
- 不新增 LLM、不新增全局状态、不修改 LifeReflection / Project / Skill 线。

---

## 5. PR-F 守线

必须保持：

- `_evaluate_share_intent` 与 `_recompute_final` 中 `unanswered_penalty` 贡献为 `* 0.0`。
- 不读取 `feedback_pressure`。
- 不调用 `derive_dispatch_policy`。
- 不引入 `session_key` / `origin_session`。
- 不改 scheduler unanswered 惩罚逻辑。

可以顺手改：

- life_sim 写 memory 时补 `privacy_level="shareable"`、`confidence=0.5`、`life_event_id=event_id`。
- `_mark_life_outcome` 的静默 `except Exception: pass` 改为 warning，但不要 raise，不要改变主流程。
- 更新误导性注释：真实接 `feedback_pressure` 必须留到 Phase 2B，并与 `origin_session` / 目标会话正确性一起设计。

---

## 6. 完成报告要求

完成报告必须取代自夸式回应，写真实状态：

- 改了哪些文件。
- D/E/F 各自完成点。
- 跑了哪些测试，给出真实数量与结果。
- 未跑或失败项必须写原因。
- 明确声明：没有新增 LLM；life_sim 没有写 `user_fact`；没有接 `feedback_pressure`；没有改 dead root / 1.4.0 旧线。

以上条件满足后，进入代码 review；不需要再为命名开会。
