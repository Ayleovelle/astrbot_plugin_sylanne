# Phase 2A Handoff Review Response

日期：2026-06-18
回应对象：`life-simulation-upgrade-phase-2a-handoff-review.md`
处置：receiving-code-review 纪律逐条核验（非表演性同意）
结论：**8 个 finding 全属实（3 HIGH + 4 MED + 1 LOW），已全部修订进 handoff v2。等架构再次 review。**

---

## 0. 核验总览

这份 review 抓得很准——我原 handoff 的几个判断是"理解了 kickoff 的字面但没吃透精神"：

- M8 我把"单一数据源"理解成"读同一个变量"就 OK，但 kickoff §46 明确是"不得双重惩罚同一信号"——读同源却在两个轴都惩罚，仍是双重。
- privacy fail-open 我自己没意识到"异常退化为不过滤"对隐私是 fail-open，与 kickoff 的"internal 不得进用户可见 prompt"硬约束直接冲突。
- 多会话审计我把"event_id 回写一致"叫成"不误投"，但回写正确≠目标会话正确。

全部接受。已修订 handoff v2（`life-simulation-upgrade-phase-2a-handoff.md`）。

---

## 1. 逐条处置

### HIGH 1：privacy filter 不能 fail-open ✅ 已修（fail-closed）

**核验**：属实。我原写"recall 异常 → 退化为不过滤"，对 H2 是隐私 fail-open——internal 内容可能进用户可见 prompt，违反 kickoff §123-125 硬约束。

**修订**（handoff §1.5）：
- privacy filter **fail-closed**：异常时不得返回 `privacy_level="internal"` 候选
- ranking 异常可降级排序，但 privacy filtering 不得降级为不过滤
- 测试补 `test_privacy_filter_fail_closed_on_exception`（§5.3）

### HIGH 2：M8 双重惩罚 ✅ 已修（采纳 review 方案 1）

**核验**：属实。我让 ShareIntent 读 `feedback_pressure` 评分，同时 scheduler 用它放大 cooldown——同一信号在"评分"和"冷却"两轴都惩罚。我把"单一数据源"误读成"读同一变量"，但 kickoff §46 是禁止"同一 unanswered pressure 在两处重复惩罚"。

**修订**（handoff §1.6 + §2.4 + §5.5）——采纳 review 方案 1：
- 2A 只做**接线占位/观测**，ShareIntent 的 `unanswered_penalty` 不纳入 `final_score`，该项乘子固定 `* 0.0`
- scheduler gate **独占** unanswered 惩罚（feedback_pressure 放大 cooldown）
- 2A 不调 `derive_dispatch_policy`，不接 session-scoped pressure
- 测试改 `test_unanswered_penalty_stays_zero_in_2a` + `test_no_double_counting_unanswered`（断言只有 scheduler 一处惩罚，不固化双重）
- 真正接单一源留 2B（届时二选一：移除 scheduler cooldown 放大 或 ShareIntent 接源）

### HIGH 3：M8 缺 session_key 来源 ✅ 已修（与方案 1 互证）

**核验**：属实。`_evaluate_share_intent(event, emotion_weights, ctx, now)` 无 session_key；若偷接 `_most_recent_host_key` 正好踩多会话漂移。

**修订**：与 HIGH 2 方案 1 互证——既然 2A 不接 feedback_pressure，就不需要 session_key。2A 保持 `unanswered_penalty=0.0`，不引入 `origin_session`（留 2B）。handoff §1.6 已明确"不偷接 `_most_recent_host_key`"。

### MED 4：privacy filter 只改 `_recall_legacy` 漏 ACTIVATION/SHADOW ✅ 已修

**核验**：属实。recall 有 LEGACY/ACTIVATION/SHADOW 三模式，只改 legacy 排序会漏。

**修订**（handoff §1.5 + §5.3）：
- privacy filter 放 `_gather_pool` **之后**的公共层 `_apply_privacy_filter(pool, visibility)`，三模式都经过
- source-aware ranking 可按模式分别处理，但 internal 过滤必须共享
- 测试补 `test_privacy_filter_covers_activation_mode`（§5.3）

### MED 5：重复注入缺去重键 ✅ 已修（`life_event_id` 结构化）

**核验**：属实。靠文本匹配会误伤同义改写，需结构化去重键。

**修订**（handoff §1.4 + §2.3 + §5.5b）：
- life_sim 写 memory 时持久化 `life_event_id: str`（取 LifeEvent.event_id），dialogue 条目为空
- `life_prompt_fragment` 跳过 `consumed_at > 0` / `dropped_at > 0` 的事件（只渲染未消费近期事件）
- recall 召回的是 memory 持久化版本，与 fragment 不同表征，不并存
- 测试补 `test_no_double_injection_same_event_id` + `test_life_event_id_persisted_on_life_sim_memory`

### MED 6：多会话审计测试名 ✅ 已修（document drift risk）

**核验**：属实。event_id 回写正确≠目标会话正确，叫"不误投"夸大。

**修订**（handoff §3 + §5.6）：
- 测试改名 `test_document_current_multi_session_drift_risk`
- 仅断言"回写 event_id 一致"+"选的是最后活跃会话（可能非来源）"，**不断言**"不误投"
- 明确漂移风险已知存在，2A 不修（留 2B 随 `origin_session`）

### MED 7：preflight 占位符 + grep 不足 ✅ 已修（固定符号名）

**核验**：属实。留"待实现后填"无法证明真实接线，`grep -c > 0` 可能命中注释/测试。

**修订**（handoff §6）：
- 固定生产符号名：`_apply_privacy_filter` / `_source_aware_rank` / `life_event_id`
- preflight 检查生产文件（`sylanne_alpha/*.py`，**不扫 tests/docs**）的函数定义/签名片段
- 关键签名用 `grep -A2 "def write_summary"` 确认含新参数（防只在注释出现）
- `unanswered_penalty` 确认在 `_SHARE_WEIGHTS` 但 `_recompute_final` 实际乘 0
- 不留占位符

### LOW 8：漏列 `MemoryItem.to_dict()` ✅ 已补

**核验**：属实。状态出口章节漏了持久化出口。

**修订**（handoff §1.7 新增）：
- `to_dict()` 加 `confidence`/`privacy_level` 输出
- 旧档 roundtrip：无字段 → from_dict 默认 → to_dict 含新字段（向前兼容）
- clamp 在 `from_dict`/`write_summary` 写入前，`to_dict` 不 clamp（保留原值，防越界传播）

---

## 2. 已认可项（review §2，不重复）

范围守界、H1/H2 同阶段闭合、life_sim confidence=0.5 不反灌、privacy 默认 "open"——这些 review 已认可，handoff v2 保留不动。

---

## 3. 改动清单（本轮文档修订）

| 文件 | 修订 |
|------|------|
| `life-simulation-upgrade-phase-2a-handoff.md` | HIGH1/2/3、MED4/5/6/7、LOW8 全部修订进 v2；顶部加 v2 修订摘要；测试矩阵补 5 条（fail-closed/activation 覆盖/unanswered 零贡献/去重/漂移审计名） |

**未改代码**——仍按裁决"先 handoff 过 review 再实现"。

---

## 4. 反思

这轮 review 教训：
1. **"单一数据源"≠"读同一变量"**：精神是不重复惩罚，不是不重复计数。读 review 要看裁决精神不看字面。
2. **fail-open/fail-closed 是隐私契约的默认姿态问题**：异常路径的默认行为本身就是设计决策，不能随手写"退化为不过滤"。
3. **测试名不能夸大覆盖**：叫"不误投"但只能证回写一致，是过度声称（和前两轮 TypeError "按真实处理" 同病）。

下一轮（若 review 再有 finding）我会继续这纪律。实现阶段会沿用：表述精确、测试直调、preflight 固定符号。

---

## 5. Gate 提议

```text
Phase 2A handoff review findings：全部修订进 v2
建议：架构再次 review handoff v2，通过后允许进入 PR-D/E/F 实现
```
