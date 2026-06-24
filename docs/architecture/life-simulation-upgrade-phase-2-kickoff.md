# Sylanne 生活模拟升级 Phase 2 Kickoff

日期：2026-06-18  
裁决对象：`life-simulation-upgrade-pr-b-c-review-response-review-response.md` 与主 handoff §12  
Gate：**Approved to Start Phase 2**

本文件不是实现计划，也不是替编写侧写任务拆解。它是架构侧开工令：规定 Phase 2 可以启动的前提、首批范围、禁止混入项、以及编写侧必须先交付的状态出口/消费路径清单。

---

## 1. Gate 裁决

PR-A / PR-B / PR-C 第一批范围已闭合，可以启动 Phase 2。

依据：

- 二审剩余 MED1 已改成可观测 warning，而非静默吞 outreach callback 异常。
- zip preflight 已补 `pending_share_events`。
- pending 过期复现测试已改为直调 `_prepare_memory_context` 真实路径。
- 主 handoff §12 已同步为最终 Approved，并明确 Phase 2 可启动。

架构侧接受该 Gate，但 Phase 2 必须按下列边界启动。

---

## 2. Phase 2 首批范围

Phase 2 首批建议命名为 **Phase 2A：Memory Contract + ShareIntent Feedback**。

允许进入 2A 的事项：

1. **H1：MemoryItem 增加 `confidence: float` / `privacy_level: str`**
   - `MemoryItem` 持久化字段。
   - `from_dict` 旧档迁移。
   - `write_summary` 扩参。
   - life_sim 写 memory 时显式传 `source="life_sim"`、`confidence`、`privacy_level`。

2. **H2：召回链路 source-aware / privacy-aware 过滤与排序**
   - `recall()` 或其内部 pool/ranking 层必须识别 `source`、`confidence`、`privacy_level`。
   - 用户事实优先级不得被 life_sim 自造内容污染。
   - `privacy_level="internal"` 默认不得进入用户可见 prompt。

3. **M8：`unanswered_penalty` 单一数据源**
   - ShareIntent 的 `unanswered_penalty` 不另起计数。
   - 只复用 scheduler/bridge 已有 `feedback_pressure` 或其单一等价来源。
   - 不得同时在 scheduler gate 与 ShareIntent 内部重复惩罚同一 unanswered 信号。

4. **已知风险清理：`_most_recent_host_key` 多会话漂移审计**
   - 至少完成设计/风险判定。
   - 如果本阶段改动会扩大 session 目标选择影响，必须同时修。

---

## 3. 暂不进入 2A 的事项

以下不允许混进 2A，除非先单独写新的设计/实施 handoff 并过 review：

1. **M6 / M7：LifeReflection Store + 全局触发点**
   - 这是独立状态机，不应和 H1/H2 同 PR 混做。
   - 建议放入 Phase 2B。

2. **L16：LifeConsolidationEngine**
   - 夜间巩固涉及预算、触发、持久化、LLM 开关。
   - 建议放入 Phase 2C 或 2B 后半，不得与 memory schema 首批混写。

3. **Phase 3：LifeProject / LifeSkill**
   - 不进入 Phase 2。

---

## 4. 编写侧开工前必须先列的清单

编写侧在写代码前，必须先在 handoff 或 plan 中列出：

### 4.1 新增状态出口

至少覆盖：

- `MemoryItem.confidence`
- `MemoryItem.privacy_level`
- `write_summary(..., confidence=?, privacy_level=?)`
- life_sim pending context 写 memory 的字段来源
- recall ranking/filter 中新增的 score / filter state
- ShareIntent `unanswered_penalty`

每个状态出口必须说明：

- 默认值是什么。
- 旧档如何迁移。
- 空/异常路径是否会写入。
- 是否会进入用户可见 prompt。

### 4.2 新增消费路径

至少覆盖：

- `_prepare_memory_context()` 写入 life_sim memory 后，后续 recall 如何消费。
- 对话 prompt 召回如何区分 `user_fact` / `life_sim` / `life_reflection`。
- `life_prompt_fragment()` 与 memory recall 是否可能重复注入同一 life event。
- ShareIntent 如何读取 feedback pressure。

每条消费路径必须说明：

- 是否用户可见。
- 是否受 `privacy_level` 过滤。
- 是否受 confidence 排序或阈值影响。
- 是否有过期、去重、或降权策略。

---

## 5. Phase 2A Review 必查项

下一轮 review 不只看测试通过，还必须逐项检查：

1. **旧档迁移**
   - 无 `confidence/privacy_level` 的旧 memory item 能读。
   - 默认值不把旧 life_sim 内容误升为用户事实。

2. **用户事实保护**
   - life_sim 不得生成 `privacy_level="user_fact"`。
   - recall 时 `user_fact` 与 `life_sim` 必须可区分。

3. **内部内容不外泄**
   - `privacy_level="internal"` 不得进入用户可见 prompt。
   - 测试必须直调真实 prompt/recall 路径，而不是复刻过滤逻辑。

4. **source-aware 排序可解释**
   - 排序/过滤规则必须能通过测试看出差异。
   - 不能只加字段不使用。

5. **unanswered 单一数据源**
   - 只能有一个来源负责 unanswered pressure。
   - 禁止 scheduler 与 ShareIntent 双重累计同一信号。

6. **zip preflight 同步**
   - 新增符号必须同步到 release preflight。
   - 清单不得手抄遗漏，要求用脚本或 grep 核对。

---

## 6. 推荐 PR 切分

推荐三段，但 H1/H2 必须在同一阶段闭合，不允许只加字段不接 recall。

### PR-D：Memory Contract

目标：
- `MemoryItem` 增加 `confidence/privacy_level`。
- `from_dict` 与 `to_dict` 迁移。
- `write_summary` 扩参。
- life_sim 写 memory 带字段。

不得单独标 Approved，除非 PR-E 同时就绪或同一 PR 内完成 recall 使用。

### PR-E：Source-Aware Recall

目标：
- recall 过滤/排序真正消费 `source/confidence/privacy_level`。
- prompt 注入路径验证用户事实保护与 internal 不外泄。

### PR-F：ShareIntent Feedback Pressure

目标：
- `unanswered_penalty` 接单一 feedback pressure。
- 不新增重复计数器。
- 补测试证明不会双重惩罚。

---

## 7. 启动命令

给编写侧的下一步不是直接写代码，而是先产出：

```text
docs/architecture/life-simulation-upgrade-phase-2a-handoff.md
```

该 handoff 必须包含：

- 2A 范围确认。
- 新增状态出口清单。
- 新增消费路径清单。
- PR-D/E/F 切分或合并理由。
- 测试矩阵。
- release preflight 增量清单。

架构侧 review 通过后，再允许进入实现。
