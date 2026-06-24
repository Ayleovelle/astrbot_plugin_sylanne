# Phase 2A Handoff 架构 Review

日期：2026-06-18  
对象：`docs/architecture/life-simulation-upgrade-phase-2a-handoff.md`  
结论：**Changes Requested**

总体判断：Phase 2A 范围边界基本守住了，没有把 M6/M7/L16/项目库混进来；PR-D/E/F 的大切分也合理。但当前 handoff 还不能放实现，因为 H2 隐私契约、M8 单一压力契约、多会话目标语义、去重键与 release preflight 都没有收紧。

---

## 1. Findings

### HIGH：隐私过滤不能 fail-open

位置：
- `docs/architecture/life-simulation-upgrade-phase-2a-handoff.md:61-66`
- `docs/architecture/life-simulation-upgrade-phase-2-kickoff.md:38-41`
- `docs/architecture/life-simulation-upgrade-phase-2-kickoff.md:123-125`

handoff 写道：`recall 内部异常 → 退化为不过滤（与基线行为一致，不阻断召回）`。

这对 H2 来说是隐私 fail-open。一旦 privacy filter 异常，`privacy_level="internal"` 的内容可能进入用户可见 prompt，直接违反 kickoff 的硬约束：internal 默认不得进入用户可见 prompt。

要求修改：

1. privacy filter 必须 fail-closed：过滤层异常时，至少不得返回 `privacy_level="internal"` 的候选。
2. 如果 source-aware ranking 异常，可以降级排序；但 privacy filtering 不得降级为不过滤。
3. 测试矩阵补一条：模拟 privacy filter/ranking 异常时，internal 内容仍不进入用户可见 recall/prompt。

---

### HIGH：M8 仍把同一 unanswered 信号双重惩罚

位置：
- `docs/architecture/life-simulation-upgrade-phase-2a-handoff.md:68-73`
- `docs/architecture/life-simulation-upgrade-phase-2a-handoff.md:106-110`
- `docs/architecture/life-simulation-upgrade-phase-2a-handoff.md:166-170`
- `docs/architecture/life-simulation-upgrade-phase-2-kickoff.md:43-46`

handoff 说 ShareIntent 读取 `scheduler.derive_dispatch_policy(session_key)["feedback_pressure"]`，同时承认 scheduler gate 已用同一个 `feedback_pressure` 放大 cooldown，然后解释为“两个轴，非重复计数”。

这不符合 kickoff 的 M8 裁决。M8 不是只禁止“重复计数器”，而是禁止同一个 unanswered pressure 在 scheduler gate 与 ShareIntent 评分里重复惩罚。单一数据源不等于可以多处消费。

要求修改，二选一：

1. **推荐**：Phase 2A 只做 `unanswered_penalty` 接线占位/观测，不把它纳入 `final_score`，保持权重为 0；scheduler gate 继续独占 unanswered 惩罚。
2. 如果坚持 ShareIntent 消费 `feedback_pressure`，则 scheduler gate 必须不再用同一 pressure 放大 cooldown；二者只能有一个实际惩罚出口。

测试矩阵必须改掉 `scheduler cooldown 已放大 + ShareIntent 评分降权` 这条断言，因为它正是在固化双重惩罚。

---

### HIGH：M8 缺少 session_key 来源设计，可能扩大 `_most_recent_host_key` 漂移

位置：
- `docs/architecture/life-simulation-upgrade-phase-2a-handoff.md:68-73`
- `docs/architecture/life-simulation-upgrade-phase-2a-handoff.md:106-110`
- `docs/architecture/life-simulation-upgrade-phase-2a-handoff.md:114-121`
- `sylanne_alpha/life_simulation.py:808-832`
- `sylanne_alpha/life_simulation.py:1043-1104`
- `sylanne_alpha/llm_request_pipeline.py:647-663`

`ShareIntent.unanswered_penalty` 计划读取 `derive_dispatch_policy(session_key)`，但 `LifeSimulator` 当前是全局 simulator，`_evaluate_share_intent(event, emotion_weights, ctx, now)` 没有 session_key。handoff 没定义 session_key 从哪里来。

如果实现侧为了接线直接复用 `_most_recent_host_key()`，就会把 M8 绑定到“最近活跃会话”，正好踩中 handoff 自己承认的多会话漂移风险。

要求修改：

1. 明确 2A 是否接入 session_key。
2. 如果 2A 不新增 `LifeEvent.origin_session`，则 M8 不得读取 session-scoped feedback pressure，只能保持 `unanswered_penalty=0.0` 或读取全局只读观测值。
3. 如果 2A 要读取 session pressure，则必须先定义目标 session 的来源，并把多会话目标正确性纳入本阶段，而不能只“审计可选”。

---

### MEDIUM：source/privacy 过滤只写 `_recall_legacy`，可能漏掉 ACTIVATION / SHADOW 模式

位置：
- `docs/architecture/life-simulation-upgrade-phase-2a-handoff.md:61-66`
- `docs/architecture/life-simulation-upgrade-phase-2a-handoff.md:89-97`
- `sylanne_alpha/memory_system.py:31-41`
- `sylanne_alpha/memory_system.py:1257-1298`
- `sylanne_alpha/memory_system.py:1475-1536`
- `sylanne_alpha/memory_system.py:1796-1868`

handoff 说实现位置是 `_recall_legacy` 排序层加 source/privacy 权重。但当前 recall 有 `LEGACY` / `ACTIVATION` / `SHADOW` 三种模式。`ACTIVATION` 同样从 `_gather_pool` 取候选，并独立生成 `MemoryResult`。如果只改 legacy 排序，activation 模式可能绕过 internal 过滤。

要求修改：

1. privacy filter 应该放在公共候选层或公共结果层，例如 `_gather_pool` 后的 `_apply_privacy_filter(pool, visibility="user_prompt")`，让 LEGACY / ACTIVATION / SHADOW 都经过。
2. source-aware ranking 可按模式分别处理，但 internal 隐私过滤必须共享。
3. 测试矩阵补：`SYLANNE_RECALL_MODE=activation` 或显式 activation 模式下，internal 仍不进入 recall 结果。

---

### MEDIUM：重复注入风险没有具体去重键

位置：
- `docs/architecture/life-simulation-upgrade-phase-2a-handoff.md:56-59`
- `docs/architecture/life-simulation-upgrade-phase-2a-handoff.md:99-104`
- `docs/architecture/life-simulation-upgrade-phase-2a-handoff.md:154-158`

handoff 说会审计 `life_prompt_fragment()` 与 memory recall 是否重复注入同一 life event，但没有给 memory item 持久化 `event_id` 或其他去重键。只说从 `outreach_ctx` 取 `event_id` 关联，却没有明确写到哪里。

没有去重键，就很难可靠证明“同一 life event 不被 fragment 和 recall 双重注入”。靠文本匹配会误伤，也会漏掉同义改写。

要求修改：

1. 明确 life_sim 写 memory 时是否把 `event_id` 作为 metadata 保存。
2. 如果 `MemoryItem` 不加 metadata，则至少定义可测试的去重策略，例如写入 memory 后 `life_prompt_fragment` 跳过 `consumed_at > 0` 的事件。
3. 测试矩阵补一条明确的同事件去重测试，而不只是“不过度过滤”。

---

### MEDIUM：多会话审计测试不能证明目标会话没错投

位置：
- `docs/architecture/life-simulation-upgrade-phase-2a-handoff.md:114-121`
- `docs/architecture/life-simulation-upgrade-phase-2a-handoff.md:172-176`

handoff 承认 `_most_recent_host_key` 会把 A 会话事件投给 B，但测试只计划断言 event_id 回写一致。event_id 回写正确不等于目标会话正确；这无法覆盖“错投到另一个 session”的风险。

要求修改：

1. 如果本阶段只做审计，不修，则测试名称和断言要改为“document current drift risk”，不要叫“不误投”。
2. 如果要证明不误投，就必须有目标 session 来源，例如 `origin_session` 或 pending context 的 `target_session`，并断言发送/写入发生在该 session。

---

### MEDIUM：release preflight 仍有占位符，且 `grep -c > 0` 不足以证明真实接线

位置：
- `docs/architecture/life-simulation-upgrade-phase-2a-handoff.md:180-194`

preflight 写了“待实现后填具体函数名，如 `_apply_privacy_filter` / `_source_aware_rank`”，并要求 `grep -c > 0`。这不足以防止符号只出现在注释、测试或文档里，也不能证明 `write_summary` 签名、privacy filter、ShareIntent 接线进入发布包。

要求修改：

1. 在 handoff 阶段先固定预期生产符号名，不要留“待实现后填”。
2. preflight 至少要检查生产文件中的函数定义或签名片段，例如：
   - `def write_summary(` 且包含 `confidence` / `privacy_level`
   - `def _apply_privacy_filter`
   - `def _source_aware_rank`
   - `unanswered_penalty` 不只是 dataclass 字段，还出现在 `_recompute_final` 或明确不出现在评分中
3. 明确 preflight 只读 zip 内生产文件，不扫 tests/docs。

---

### LOW：状态出口章节漏列 `MemoryItem.to_dict()`

位置：
- `docs/architecture/life-simulation-upgrade-phase-2a-handoff.md:31-60`
- `docs/architecture/life-simulation-upgrade-phase-2-kickoff.md:145-151`

handoff 的 PR 切分里提到 `MemoryItem` 加字段与迁移，但状态出口章节没有显式列 `MemoryItem.to_dict()`。这是持久化出口，必须列明，否则容易出现“读得到但存不回 zip/KV”的半成品。

要求修改：在新增状态出口里补 `MemoryItem.to_dict()`，说明字段如何序列化、旧档如何 roundtrip、异常值是否在写入前 clamp。

---

## 2. 已认可项

以下内容本轮认可：

1. 范围没有偷塞 M6/M7/L16/项目库。
2. H1/H2 同阶段闭合的原则正确，PR-D/E 可以分开 review 但不得单独 Approved。
3. life_sim memory 默认 `confidence=0.5`，不从 ShareIntent final_score 反灌，这个方向正确。
4. `privacy_level` 默认 `"open"` 用于旧 dialogue 记忆，避免旧档行为大面积变更，这个选择可以接受。

---

## 3. Gate 判断

当前 Phase 2A handoff **不允许进入实现**。

编写侧需要先提交：

```text
docs/architecture/life-simulation-upgrade-phase-2a-handoff-response.md
```

必须逐条回应以上 findings，尤其要先解决：

1. privacy filter fail-closed。
2. M8 单一 pressure 只能有一个实际惩罚出口。
3. session_key 来源不能靠 `_most_recent_host_key` 偷接。
4. privacy filter 覆盖 LEGACY / ACTIVATION / SHADOW。
5. life event 去重键或明确去重策略。
6. preflight 固定生产符号，不留占位。
