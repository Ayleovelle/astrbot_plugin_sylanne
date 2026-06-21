# Phase 2A Handoff v2 Review Response

日期：2026-06-18  
对象：`docs/architecture/life-simulation-upgrade-phase-2a-handoff-v2-review.md`  
修订文件：`docs/architecture/life-simulation-upgrade-phase-2a-handoff.md`  
结论：**v3 已闭合 v2 review 的 5 个 finding，建议进入架构复审。**

---

## 1. HIGH：未知 `privacy_level` 不能兜底为 `"open"`

处理：**已修。**

- §1.2 明确区分缺字段/`None` 与未知字符串：旧档缺字段和旧调用缺省仍迁移为 `"open"`，未知/非法字符串 fail-closed 规范化为 `"internal"`。
- §1.2 要求 `write_summary` / `from_dict` 写入前规范化，并记录 `logger.warning`。
- §5.3 新增 `test_invalid_privacy_level_normalizes_internal`，覆盖非法 privacy 不得进入用户可见 recall/prompt。

---

## 2. HIGH：M8 范围与 PR-F 自相矛盾

处理：**已修。**

- §0 范围行改为 `M8 Guardrail`，明确 2A 不接 `feedback_pressure`，`unanswered_penalty` 贡献恒 0，scheduler 独占 unanswered 惩罚。
- §1.6 和 §2.4 保持同一口径：ShareIntent 不读取 session-scoped feedback，不偷接 `_most_recent_host_key`。
- §4 PR-F 改为 `M8 Guardrail / No-Double-Penalty`，交付物限于字段保留、评分贡献为 0、测试证明无双重消费；真实接入移到 2B。

---

## 3. MEDIUM：H2 实现位置仍把 privacy 放回 `_recall_legacy`

处理：**已修。**

- §1.5 明确 privacy filter 位于 `_gather_pool` 之后的公共层 `_apply_privacy_filter(pool, visibility)`。
- §2.2 统一为公共层过滤，`_recall_legacy` 只做 source/confidence 排序消费，不承担 internal 过滤的唯一责任。
- §7 风险描述同步修正为公共层过滤，避免 legacy-only 实现歧义。

---

## 4. MEDIUM：`life_event_id` 持久化出口没有闭合到 `to_dict()`

处理：**已修。**

- §1.7 明确 `MemoryItem.to_dict()` 输出 `confidence` / `privacy_level` / `life_event_id`。
- §1.7 明确 `from_dict` 旧档无 `life_event_id` 时迁移为空值，dialogue 条目保持空，只有 life_sim 条目写 LifeEvent.event_id。
- §5.5b 新增 `test_life_event_id_survives_memory_roundtrip`，覆盖 to_dict/from_dict roundtrip 后不丢失。
- §6 preflight 增加检查 `MemoryItem.to_dict()` 输出 `life_event_id`，并检查 `from_dict` 旧档迁移为空值。

---

## 5. LOW：`source="life_reflection"` 只能作为保留值，不得引入行为

处理：**已修。**

- §2.2 将 `source="life_reflection"` 改为保留值/兼容排序占位。
- 明确 2A 不新增 LifeReflection Store、触发点、反思写入、evidence 生成或语义消费，2B 才能真用。

---

## 6. Gate 建议

v3 已满足 v2 review 的最小可批准条件：

1. 非法 `privacy_level` fail-closed。
2. 2A 范围与 PR-F 全文统一为不接 `feedback_pressure`，只做 M8 guardrail。
3. privacy filter 的实现位置全文统一为公共层 `_apply_privacy_filter`，覆盖三种 recall mode。
4. `life_event_id` 明确进入 `to_dict` / `from_dict` / preflight / roundtrip 测试。
5. `life_reflection` 明确只是保留值，不新增生产者或行为。

建议架构复审 `life-simulation-upgrade-phase-2a-handoff.md` v3；通过后再进入 PR-D/E/F 实现。
