# Phase 2A Handoff v2 架构 Review

日期：2026-06-18  
对象：`docs/architecture/life-simulation-upgrade-phase-2a-handoff.md`（v2）  
前置 review：`docs/architecture/life-simulation-upgrade-phase-2a-handoff-review.md`  
结论：**Changes Requested（小修，但不允许进实现）**

总体判断：v2 已经吸收了上一轮大部分裁决，尤其是 privacy filter 放公共层、M8 正文不偷接 `_most_recent_host_key`、多会话测试改为 document drift risk、`life_event_id` 去重键和 preflight 固定符号名，这些方向是对的。

但当前文档仍有几处互相矛盾或 fail-open 的残留语句。它们不是文字洁癖问题，而是会直接误导实现侧把 Phase 2A 做成上一轮已经否决的方案。

---

## 1. Findings

### HIGH：未知 `privacy_level` 不能兜底为 `"open"`

位置：
- `docs/architecture/life-simulation-upgrade-phase-2a-handoff.md:51-57`
- `docs/architecture/life-simulation-upgrade-phase-2a-handoff.md:72-77`

v2 已经把 recall filter 异常路径改成 fail-closed，这是正确修复。但 `MemoryItem.privacy_level` 的写入/迁移规则仍写着：

```text
write_summary(privacy_level=None) -> "open"; 未知字符串 -> "open" 兜底
```

缺字段旧档迁移为 `"open"` 可以接受，因为这是历史 dialogue 记忆的基线行为；但未知/非法字符串不能也变成 `"open"`。这会让 typo、脏数据或异常输入绕过 `internal` 过滤语义，本质仍是 privacy fail-open。

要求修改：

1. `None` / 缺字段：仅旧档迁移或旧调用缺省时可用 `"open"`。
2. 未知字符串：必须 fail-closed，推荐拒绝写入、降为不可见态，或规范化为 `"internal"`/`"invalid"` 后不进入用户可见 prompt。
3. 测试矩阵补一条：非法 `privacy_level` 不得进入用户可见 recall/prompt。

---

### HIGH：M8 范围与 PR-F 仍自相矛盾

位置：
- `docs/architecture/life-simulation-upgrade-phase-2a-handoff.md:21-25`
- `docs/architecture/life-simulation-upgrade-phase-2a-handoff.md:79-87`
- `docs/architecture/life-simulation-upgrade-phase-2a-handoff.md:134-139`
- `docs/architecture/life-simulation-upgrade-phase-2a-handoff.md:158-162`

v2 正文已经写清楚：2A 不读取 `feedback_pressure`，`ShareIntent.unanswered_penalty` 对 `final_score` 贡献恒为 0，scheduler gate 独占 unanswered 惩罚。这是上一轮 review 推荐的正确边界。

但范围确认和 PR 切分里仍写着：

```text
M8：unanswered_penalty 单一数据源（复用 feedback_pressure）
PR-F：ShareIntent Feedback —— unanswered_penalty 接单一 feedback_pressure
```

这会让实现侧按 PR-F 标题和范围行去真实接入 `feedback_pressure`，重新打开双重惩罚和 session drift 风险。

要求修改：

1. Phase 2A 范围行改为：`M8 Guardrail / unanswered_penalty remains non-consuming in 2A`。
2. PR-F 改名为 `M8 Guardrail` 或 `ShareIntent No-Double-Penalty Guard`。
3. PR-F 交付物只能是字段保留、评分贡献为 0、测试证明没有双重消费；真实接入 `feedback_pressure` 必须移到 2B，且与 `origin_session` / 目标会话设计一起做。

---

### MEDIUM：H2 实现位置仍把 privacy 放回 `_recall_legacy`

位置：
- `docs/architecture/life-simulation-upgrade-phase-2a-handoff.md:72-77`
- `docs/architecture/life-simulation-upgrade-phase-2a-handoff.md:111-119`
- `docs/architecture/life-simulation-upgrade-phase-2a-handoff.md:246`

v2 §1.5 正确要求 `_apply_privacy_filter(pool, visibility)` 放在 `_gather_pool` 后的公共层，覆盖 LEGACY / ACTIVATION / SHADOW。

但 §2.2 又写：

```text
实现位置：_recall_legacy 排序层加 source/privacy 权重
```

§7 也写：

```text
过滤层加在 _recall_legacy 排序前
```

这会把上一轮 MED4 重新留成实现歧义。privacy filter 不能是 legacy 私有逻辑；legacy 可以消费 source-aware ranking，但 internal 可见性过滤必须是公共候选层/公共结果层。

要求修改：

1. §2.2 和 §7 改成：privacy filter 仅在 `_apply_privacy_filter` 公共层执行。
2. `_recall_legacy` 只允许做 source/confidence 排序消费，不承担 internal 过滤的唯一责任。
3. 保留 activation/shadow 覆盖测试为必测项。

---

### MEDIUM：`life_event_id` 持久化出口没有闭合到 `to_dict()`

位置：
- `docs/architecture/life-simulation-upgrade-phase-2a-handoff.md:67-69`
- `docs/architecture/life-simulation-upgrade-phase-2a-handoff.md:91-95`
- `docs/architecture/life-simulation-upgrade-phase-2a-handoff.md:222-229`

v2 已经接受 `life_event_id` 作为结构化去重键，这个方向正确。但 `MemoryItem.to_dict()` 状态出口只列了 `confidence` / `privacy_level`，没有明确 `life_event_id` 也要序列化。preflight 只检查 `MemoryItem` 含字段，也没有检查 `to_dict()` 输出该键。

这会留下一个危险半成品：内存态有去重键，但 roundtrip / 重启后丢失，导致 fragment 与 recall 的同事件去重不能稳定成立。

要求修改：

1. §1.7 明确 `MemoryItem.to_dict()` 输出 `life_event_id`。
2. `from_dict` 迁移规则明确：旧档无字段 -> 空字符串或 `None`，dialogue 条目为空。
3. preflight 加检查：`MemoryItem.to_dict()` 输出含 `life_event_id` 键。
4. 测试 `test_life_event_id_persisted_on_life_sim_memory` 必须覆盖 roundtrip，不只检查写入时字段存在。

---

### LOW：`source="life_reflection"` 只能作为保留值，不得引入行为

位置：
- `docs/architecture/life-simulation-upgrade-phase-2a-handoff.md:111-118`

`source="life_reflection"` 写成“2A 只占位，2B 真用”可以接受，但需要更硬一点：2A 不得新增 LifeReflection Store、触发点、反思写入或 evidence 生成。若实现侧只是让 recall/ranking 对未知或未来 source 做兼容 passthrough，可以保留；否则就越过 Phase 2A 边界。

要求修改：补一句“2A 仅保留 source 枚举/兼容排序，不新增 life_reflection 生产者与语义消费”。

---

## 2. 已闭合项

以下上一轮 finding 在 v2 中基本闭合：

1. recall filter 异常路径改为 fail-closed，方向正确；但未知 privacy 字符串仍需修。
2. M8 正文选择“不接 `feedback_pressure`”，方向正确；但范围行和 PR-F 仍需修。
3. 明确不偷接 `_most_recent_host_key`，多会话漂移只审计不修。
4. 增加 `_apply_privacy_filter` 公共层设计，方向正确；但后文实现位置需统一。
5. `life_event_id` 作为结构化去重键，方向正确；但 `to_dict`/roundtrip/preflight 需闭合。
6. release preflight 不再留“待实现后填”的占位，符号名已固定。
7. `MemoryItem.to_dict()` 已补为状态出口，但字段列表不完整。

---

## 3. Gate 判断

当前 Phase 2A handoff v2 **仍不允许进入实现**。

编写侧下一轮只需要做小修，不需要重写整份 handoff。必须提交：

```text
docs/architecture/life-simulation-upgrade-phase-2a-handoff-v2-response.md
```

最小可批准条件：

1. 非法 `privacy_level` fail-closed。
2. 2A 范围与 PR-F 全文统一为“不接 `feedback_pressure`，只做 M8 guardrail”。
3. privacy filter 的实现位置全文统一为公共层 `_apply_privacy_filter`，覆盖三种 recall mode。
4. `life_event_id` 明确进入 `to_dict` / `from_dict` / preflight / roundtrip 测试。
5. `life_reflection` 明确只是保留值，不新增生产者或行为。

修完以上 5 条后，Phase 2A 可以进入 **Approved to Implement**；否则继续 Changes Requested。
