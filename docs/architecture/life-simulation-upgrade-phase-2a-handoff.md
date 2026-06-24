# Sylanne 生活模拟升级 Phase 2A Handoff

日期：2026-06-18
范围：**Memory Contract + ShareIntent Feedback（Phase 2A）**
前置：`life-simulation-upgrade-phase-2-kickoff.md`（裁决 Approved to Start Phase 2）
状态：**v3（v2 review 小修闭合）——已逐条闭合 `phase-2a-handoff-review.md` 的 8 个 finding，以及 `phase-2a-handoff-v2-review.md` 的 5 个 finding。等架构再次 review。本文件不含实现，只列状态出口/消费路径/测试矩阵/preflight 增量。**

> v3 修订摘要（对齐 review findings）：
> - HIGH1：privacy filter 改 **fail-closed**（异常时不得返回 internal）
> - HIGH2+3：M8 采纳 review 方案 1——2A **不接 feedback_pressure**，ShareIntent 该项权重贡献恒 0，scheduler 独占 unanswered 惩罚；不偷接 session_key
> - MED4：privacy filter 放公共候选层（`_apply_privacy_filter`），覆盖 LEGACY/ACTIVATION/SHADOW
> - MED5：life_sim 写 memory 持久化 `life_event_id` 作为去重键（不用文本匹配）
> - MED6：多会话审计测试改名 "document current drift risk"，不断言"不误投"
> - MED7：preflight 固定生产符号名（`_apply_privacy_filter` / `_source_aware_rank` / `life_event_id`），不留占位
> - LOW8：补 `MemoryItem.to_dict()` 出口（§1.7）
> - v2 review HIGH1：未知/非法 `privacy_level` 规范化为 `"internal"`，不可 fail-open
> - v2 review HIGH2：M8 全文统一为 2A guardrail，不接 `feedback_pressure`
> - v2 review MED3：privacy filter 全文统一在 `_apply_privacy_filter` 公共层
> - v2 review MED4：`life_event_id` 闭合到 `to_dict` / `from_dict` / preflight / roundtrip 测试
> - v2 review LOW5：`source="life_reflection"` 仅保留值，不新增生产者或语义消费

---

## 0. 范围确认（对齐 kickoff §2/§3）

**2A 允许**：
- **H1**：`MemoryItem` 加 `confidence: float` / `privacy_level: str` + `from_dict` 迁移 + `write_summary` 扩参 + life_sim 写 memory 带字段
- **H2**：召回链路 source-aware / privacy-aware 过滤排序
- **M8 Guardrail**：`unanswered_penalty` 在 2A 不消费（不接 `feedback_pressure`，贡献恒 0；scheduler 独占）— 真实接入留 2B
- **多会话漂移审计**：`_most_recent_host_key` 风险判定

**2A 禁止混入**（留给 2B/2C）：
- M6/M7 LifeReflection Store + 全局触发点
- L16 LifeConsolidationEngine
- Phase 3 LifeProject / LifeSkill

**契约纪律（三轮 review 教训）**：
- 新状态/出口全列清单，逐个说明默认值/迁移/空路径/可见性
- 测试直调真实函数，不复刻逻辑
- 零副作用/隐私契约同步审计
- preflight 用 grep 核对，不手抄

---

## 1. 新增状态出口（kickoff §4.1）

每个出口必须说明：默认值 / 旧档迁移 / 空·异常路径 / 是否进用户可见 prompt。

### 1.1 `MemoryItem.confidence: float`
- **默认值**：`0.5`（中性；与 v2 §4.3 迁移一致）
- **取值范围**：`[0, 1]`，写入时 clamp
- **旧档迁移**：`from_dict` 无该字段 → 0.5（与 PR-B 的 life_sim 事件迁移 confidence=0.5 对齐）
- **空/异常路径**：`write_summary(confidence=None)` → 默认 0.5；非法值（负/超1）→ clamp 到 [0,1]
- **进用户可见 prompt**：间接（recall 排序权重之一），不直接显示

### 1.2 `MemoryItem.privacy_level: str`
- **默认值**：`"open"`（与 `MemorySource` 配套；区分于 life_sim 的 `"internal"`/`"shareable"`）
  - **注意**：默认 `"open"` 不是 `"internal"`——旧 dialogue 记忆应保持可召回可注入（行为不变），只有显式 life_sim/internal 内容才降权/过滤
- **取值集（合法）**：`"open"` / `"internal"` / `"shareable"` / `"user_fact"`（与 life_sim 的 `LifePrivacy` 对齐，但 memory 层多一个 `"open"` 基线）
- **迁移规则（区分缺字段 vs 未知字符串，v3 HIGH1）**：
  - **缺字段（旧档）/ `write_summary(privacy_level=None)`**：`"open"`（旧 dialogue 基线，行为零变化）
  - **未知/非法字符串（typo/脏数据/异常）**：**fail-closed** → 规范化为 `"internal"`（不可见态），拒绝当作 `"open"` 放行。这样 typo/异常输入不会绕过 internal 过滤语义
- **写入前规范化（`write_summary`/`from_dict`）**：未知值 → `"internal"`，并记录 `logger.warning`（可观测）
- **进用户可见 prompt**：`"internal"`（含规范化来的非法值）默认不进；`"user_fact"` 强保护；`"open"`/`"shareable"` 正常

### 1.3 `write_summary(..., confidence=?, privacy_level=?)` 扩参
- **签名变更**：加两个 kwarg（默认 None，向后兼容所有现有调用）
- **旧调用方**：`write_summary(text, source_turns=1, source="dialogue")` 不传新参 → confidence=0.5, privacy_level="open"
- **life_sim 调用点**（`llm_request_pipeline.py:~1433`）：写 life_sim memory 时显式传 `source="life_sim"`, `confidence=0.5`, `privacy_level="shareable"`
  - **注意**：当前 life_sim 写的 `temperature=0.3`，confidence/privacy 是新增维度，不冲突

### 1.4 life_sim pending context → memory 的字段来源
- 已在 PR-C 扩展 pending context（intent_id/reason_code/delivery_mode/expires_at/target_session/queued_at）
- 2A 新增：`_prepare_memory_context` 写 memory 时，从 `outreach_ctx` 取 `event_id` 关联，写 `source="life_sim"` + `confidence=0.5` + `privacy_level="shareable"` + **`life_event_id`（去重键，MED5）**
- **关键**：`confidence` 不从 ShareIntent.final_score 透传（避免循环：ShareIntent 读 memory，memory 又写 ShareIntent 分数）。固定 0.5 是 life_sim 自造内容的合理中性值
- **`life_event_id` 去重键**：仅 life_sim 来源条目填该字段（取 LifeEvent.event_id），dialogue 条目为空。供 `life_prompt_fragment` 与 recall 去重用（§2.3）

### 1.5 recall ranking/filter 新增 score / filter state
- **新增内部状态**：recall 路径在 candidate dict 里加 `source`/`confidence`/`privacy_level` 字段（`_gather_pool` 产出，公共过滤/排序层消费）
- **过滤规则**：`privacy_level=="internal"` 默认不进用户可见 prompt 召回（H2 核心）；`confidence` 作为 ranking tiebreaker
- **默认值**：candidate dict 缺字段 → source="dialogue", confidence=0.5, privacy_level="open"
- **空/异常路径（fail-closed，HIGH1 修复）**：privacy filter **异常时必须 fail-closed**——不得返回 `privacy_level="internal"` 的候选（即使 ranking 异常可降级，privacy 过滤不得降级为不过滤）；其他异常退化为基线排序
- **进用户可见 prompt**：是（这就是过滤的目的）
- **覆盖范围（MED4 修复）**：privacy filter 放在 `_gather_pool` **之后**的公共层（`_apply_privacy_filter(pool, visibility)`），LEGACY / ACTIVATION / SHADOW 三模式都经过，不得只在 `_recall_legacy` 改

### 1.6 `ShareIntent.unanswered_penalty`
- **当前**：`_evaluate_share_intent` 里 `unanswered_penalty=0.0`（占位，未接数据源）
- **2A 改动（HIGH2/3 修复：采纳 review 方案 1）**：**2A 只做接线占位/观测，不纳入 `final_score`，权重保持 0**。
  - scheduler gate 继续独占 unanswered 惩罚（feedback_pressure 放大 cooldown）
  - ShareIntent 的 `_SHARE_WEIGHTS["unanswered_penalty"]` 保持 -0.20（文档保留），但 `_evaluate_share_intent`/`_recompute_final` 里该项乘子固定 `* 0.0`（与现状一致，不接入数据源）
  - **不读取 session-scoped feedback_pressure**（`_evaluate_share_intent` 无 session_key，且 2A 不引入 `origin_session`；偷接 `_most_recent_host_key` 会扩大漂移——HIGH3）
  - 真正接单一数据源留待 Phase 2B（届时随 `origin_session` 一起设计目标会话正确性）
- **默认值**：0.0（不惩罚）
- **空/异常路径**：不接数据源故无异常路径
- **进用户可见 prompt**：否（仅影响 ShareIntent.final_score，且 2A 内该项贡献恒为 0）
- **双重惩罚验证（M8）**：2A 验证"scheduler gate 已放大 cooldown + ShareIntent 评分里该项贡献为 0"，无双重惩罚；待 2B 接单一源时移除 scheduler 的 cooldown 放大或 ShareIntent 的该项（二选一，不能同时保留）

### 1.7 `MemoryItem.to_dict()`（LOW8 + v2 MED4 补：持久化出口）
- **序列化字段**：`confidence` / `privacy_level` / `life_event_id` 加入 `to_dict()` 输出（与 `source`/`importance` 同级）
- **`life_event_id` 默认/迁移**：`from_dict` 旧档无字段 → `""`；dialogue 条目保持空字符串，只有 life_sim 来源条目写 LifeEvent.event_id
- **旧档 roundtrip**：旧 dict 无这三字段 → `from_dict` 用默认（0.5 / "open" / 空 `life_event_id`）→ 再 `to_dict` 时含新字段（向前兼容，旧档升级后持久化新字段）
- **异常值 clamp（写入前）**：`to_dict` 不做 clamp（保留原值），`from_dict` 和 `write_summary` 负责写入前 clamp 到 [0,1] / 合法 privacy 字符串 / 规范化 `life_event_id` 空值；这样旧档若含越界值，`from_dict` 读入时已 clamp，不会持久化传播越界值
- **进用户可见 prompt**：否（仅元数据，不直接显示）

---

## 2. 新增消费路径（kickoff §4.2）

每条说明：是否用户可见 / 受 privacy 过滤 / 受 confidence 影响 / 过期·去重·降权。

### 2.1 `_prepare_memory_context` 写 life_sim memory → 后续 recall 消费
- **写入**：life_sim 事件被 pending 消费时，写 memory 带 source/confidence/privacy
- **消费**：下次 recall 时，这些条目作为 candidate 进 pool
- **用户可见**：是（通过 `[life_event_context]` fragment 或后续召回注入）
- **受 privacy 过滤**：是——life_sim 写 `privacy_level="shareable"`（非 internal），可召回；若未来有 internal 内容则不进可见 prompt
- **受 confidence 影响**：ranking tiebreaker（confidence 高的同分优先）
- **去重/降权**：source="life_sim" 的条目在排序时对 user_fact 同分情况降权（用户事实优先）

### 2.2 对话 prompt 召回区分 user_fact / life_sim / life_reflection
- **用户可见**：是
- **过滤规则**（H2 核心）：
  - `privacy_level="internal"` → 不进用户可见 prompt（强过滤）
  - `privacy_level="user_fact"` → 可召回，排序权重最高
  - `source="life_sim"` → 可召回，但同分时排在 user_fact 之后（软降权）
  - `source="life_reflection"` → 保留值/兼容排序占位；2A 不新增 LifeReflection Store、触发点、反思写入、evidence 生成或语义消费，2B 才能真用
- **实现位置（v3 MED3 统一）**：privacy filter 仅在 `_apply_privacy_filter(pool, visibility)` 公共层执行（`_gather_pool` 之后，`_recall_*` 之前），覆盖 LEGACY/ACTIVATION/SHADOW 三模式。`_recall_legacy` 只做 source/confidence 排序消费，不承担 internal 过滤的唯一责任
- **过期/去重**：不在 2A 新增（沿用现有 recency/weight 机制）

### 2.3 `life_prompt_fragment()` 与 memory recall 是否重复注入同一 life event
- **风险审计**：life_sim 事件有两条注入路径——
  - ① `life_prompt_fragment()` 直接渲染最近 events（PR-B 已做，过滤 user_fact）
  - ② 事件写 memory 后被 recall 注入
- **2A 去重键设计（MED5 修复）**：life_sim 写 memory 时**显式保存 `event_id` 作为 metadata**——
  - 方案：`write_summary` 写 life_sim memory 时，在 MemoryItem 持久化一个 `life_event_id: str` 字段（仅 life_sim 来源条目用，dialogue 条目为空）
  - 这样 `life_prompt_fragment` 可跳过 `consumed_at > 0` 的事件（已消费），recall 注入的是 memory 持久化版本，二者不重复
  - 文本匹配会误伤同义改写，故**必须用 `life_event_id` 结构化去重键**，不用文本匹配
- **去重策略（实现侧明确）**：
  - `life_prompt_fragment` 渲染时跳过 `consumed_at > 0` 或 `dropped_at > 0` 的事件（只渲染未消费的近期事件）
  - recall 召回的 life_sim memory 不受此影响（它是 memory 持久化版本，与 fragment 是不同表征）
  - 若同一 event_id 同时在 fragment 候选与 recall 结果中：fragment 已跳过 consumed，不会并存
- **测试**：补一条 `test_no_double_injection_same_event_id`（构造 event，先 consumed，断言 fragment 不含 + recall 含；未 consumed 时 fragment 含 + recall 不含，因未写入 memory）

### 2.4 ShareIntent feedback pressure（2A 不接，保持观测占位）
- **2A 决策（HIGH2/3 修复）**：ShareIntent **不读取 feedback_pressure**（无 session_key，且偷接 `_most_recent_host_key` 会扩大漂移）。该项权重贡献恒为 0，scheduler gate 独占 unanswered 惩罚。
- **单一数据源验证（M8）**：2A 验证"只有 scheduler 一处惩罚 unanswered"，无双重计数；真正接单一源留 2B（随 `origin_session` 设计）
- **禁止**：不新增独立 unanswered 计数器；不复用疑似死代码 `_feedback_history`（:61）；2A 不调 `derive_dispatch_policy`
- **用户可见**：否

---

## 3. 多会话漂移审计（kickoff §2.4）

`_most_recent_host_key`（`llm_request_pipeline.py:647`）4 个调用点：`:2646` outreach、`:2872` emotion、`:2891` body_delta、`:2911` memory_summary。

- **风险**：单用户多会话（多 IM 平台账号）时，A 会话触发情绪可能错投给 B（B 最后说话）
- **2A 判定**：**仅审计 + 文档化漂移风险，不修**（避免引入 `origin_session` 扩大状态机复杂度，留 2B）
- **测试（MED6 修复）**：测试名改为 **"document current drift risk"**，断言"event_id 回写一致"（这只能证明回写正确，**不能**证明目标会话正确——漂移风险已知存在，2A 不修）。不叫"不误投"
- **2A 不改 life_sim 回调的目标会话选择**（不接 origin_session，不修 `_most_recent_host_key`）

---

## 4. PR 切分（对齐 kickoff §6）

kickoff 要求 H1/H2 必须同阶段闭合（不允许只加字段不接 recall）。2A 采用：

- **PR-D：Memory Contract**（H1 字段层）—— `MemoryItem` 加字段 + 迁移 + `write_summary` 扩参 + life_sim 写带字段
- **PR-E：Source-Aware Recall**（H2 消费层）—— recall 过滤排序真正消费 source/confidence/privacy + prompt 注入验证
- **PR-F：M8 Guardrail / No-Double-Penalty**（v3 HIGH2 改名）—— `unanswered_penalty` **保持非消费**：字段保留 + 评分贡献为 0 + 测试证明无双重消费。**真实接 `feedback_pressure` 禁止在 2A 做**，移到 2B 与 `origin_session` 一起设计

**切分理由**：D 和 E 必须同批合入 review（kickoff §6 纪律），但分两个 PR 便于 review 聚焦（D 看字段/迁移，E 看过滤逻辑）。F 独立（ShareIntent guardrail，仅守边界不接源，可单独 review）。实施顺序 D→E→F，合入 review 一次性（D+E 闭合 + F 并行）。

---

## 5. 测试矩阵（kickoff §5 必查项）

全部测试**直调真实函数**（不复刻逻辑，二轮 review LOW3 教训）。

### 5.1 旧档迁移
| 测试 | 断言 |
|------|------|
| `test_old_memory_item_no_confidence_privacy_loads_defaults` | from_dict 旧档 → confidence=0.5, privacy_level="open"，text/weight 不变 |
| `test_old_life_sim_memory_not_upgraded_to_user_fact` | 旧 life_sim 条目迁移后 privacy != "user_fact"（防误升） |
| `test_invalid_confidence_clamped` | confidence=-0.5/2.0 → clamp 到 [0,1] |

### 5.2 用户事实保护
| 测试 | 断言 |
|------|------|
| `test_life_sim_never_writes_user_fact` | 直调 `_prepare_memory_context` + life_sim pending → 写入的 memory privacy_level != "user_fact" |
| `test_recall_distinguishes_user_fact_and_life_sim` | 同分时 user_fact 排在 life_sim 前 |

### 5.3 内部内容不外泄
| 测试 | 断言 |
|------|------|
| `test_internal_privacy_not_in_user_prompt` | 直调真实 recall + prompt 注入路径，privacy_level="internal" 的条目不出现在返回 fragment |
| `test_life_sim_shareable_still_recallable` | 正向回归：life_sim shareable 仍可召回（不过度过滤） |
| `test_privacy_filter_fail_closed_on_exception`（HIGH1 补） | 模拟 privacy filter/ranking 异常，internal 内容仍不进入用户可见 recall/prompt（fail-closed） |
| `test_invalid_privacy_level_normalizes_internal`（v2 HIGH1 补） | 非法 privacy_level 经 from_dict/write_summary 后规范化为 internal，不进入用户可见 recall/prompt |
| `test_privacy_filter_covers_activation_mode`（MED4 补） | `RecallMode.ACTIVATION`（或 SHADOW）下，internal 仍被过滤（公共层覆盖三模式） |

### 5.4 source-aware 排序可解释
| 测试 | 断言 |
|------|------|
| `test_source_aware_ranking_visible_in_results` | 构造 user_fact + life_sim 同分，recall 结果顺序可观测差异 |
| `test_confidence_tiebreaker` | 同 source 同 relevance，confidence 高的排前 |

### 5.5 unanswered 单一数据源（HIGH2 修复后）
| 测试 | 断言 |
|------|------|
| `test_unanswered_penalty_stays_zero_in_2a` | ShareIntent.unanswered_penalty 恒为 0.0（2A 不接数据源） |
| `test_no_double_counting_unanswered` | 只有 scheduler gate 用 feedback_pressure 放大 cooldown；ShareIntent 评分里 unanswered 项贡献为 0（不固化双重惩罚） |

### 5.5b 去重（MED5 补）
| 测试 | 断言 |
|------|------|
| `test_no_double_injection_same_event_id` | 同一 life event：consumed 后 fragment 不含 + recall 含（已写 memory）；未 consumed 时 fragment 含 + recall 不含（未写 memory） |
| `test_life_event_id_persisted_on_life_sim_memory` | life_sim 写的 MemoryItem 持久化 `life_event_id` 字段，dialogue 条目该字段为空 |
| `test_life_event_id_survives_memory_roundtrip`（v2 MED4 补） | life_sim MemoryItem 经 to_dict/from_dict roundtrip 后 `life_event_id` 不丢失，旧档缺字段迁移为空值 |

### 5.6 零副作用 / 多会话（MED6 修复）
| 测试 | 断言 |
|------|------|
| `test_empty_recall_returns_empty_no_side_effect` | recall 空 query 不写状态 |
| `test_document_current_multi_session_drift_risk`（改名，MED6） | **文档化漂移风险**：多 host 场景 `_most_recent_host_key` 选的是最后活跃会话（不一定是事件来源会话）；仅断言"回写 event_id 一致"，**不**断言"不误投"（漂移已知存在，2A 不修） |

---

## 6. Release Preflight 增量（kickoff §5.6，固定符号名 + grep 核对，不手抄）

**2A 固定的生产符号名**（实现时按这些命名，preflight 检查函数定义/签名片段，不只查字符串出现）：

**PR-D（memory contract）** — `memory_system.py`：
- `MemoryItem` 含字段 `confidence` 与 `privacy_level`（grep `"confidence:"` 与 `"privacy_level:"` 在 dataclass 定义附近）
- `def write_summary(` 签名含 `confidence` 与 `privacy_level`（grep `write_summary` + `privacy_level` 同区域）
- `MemoryItem.to_dict()` 输出含 `confidence`、`privacy_level`、`life_event_id` 键

**PR-E（source-aware recall）** — `memory_system.py`：
- `def _apply_privacy_filter(`（公共过滤层，`_gather_pool` 之后，三模式共用）
- `def _source_aware_rank(`（ranking 层，含 source/confidence 权重）
- `MemoryItem` 含 `life_event_id` 字段（life_sim 去重键，dialogue 条目为空），`from_dict` 旧档迁移为空值

**PR-F（ShareIntent feedback，2A 占位）** — `life_simulation.py`：
- `unanswered_penalty` 仍是 ShareIntent 字段，但 `_evaluate_share_intent` / `_recompute_final` 里该项乘子固定 `* 0.0`（grep 确认：`unanswered_penalty` 出现在 `_SHARE_WEIGHTS` 但 `_recompute_final` 实际乘 0）
- `proactive_scheduler.py` 的 `derive_dispatch_policy` 不改（PR-C 已用，2A 不动）

**核对方式（MED7 修复）**：
- 用 `grep -c` 在 zip 内**生产文件**（`sylanne_alpha/*.py`）核对符号计数 > 0，**不扫 tests/docs**
- 关键签名用 `grep -A2 "def write_summary"` 确认含新参数（防只在注释出现）
- 不留"待实现后填"占位符

---

## 7. 风险与边界（2A 不碰）

- **不在 2A 改**：`LifeEvent.origin_session`（多会话精确路由，留 2B）、LifeReflection Store、ConsolidationEngine LLM 开关、项目/技能库
- **2A 不引入新 LLM 调用**：confidence 是规则值（life_sim 固定 0.5），privacy 是字符串标签，recall 过滤是规则——全部零 LLM
- **召回性能**：隐私过滤在 `_gather_pool` 后公共层，candidate pool 不放大；source-aware ranking 在 `_recall_legacy` 排序前（不额外扫描）。若 recall 变慢需在测试矩阵加 perf 断言（2A 先不加，观测）

---

## 8. 启动门槛

架构 review 通过本文件后，编写侧按 PR-D→E→F 实施，D+E 同批合入 review，F 独立。每 PR 带对应测试矩阵子集。最终全量回归预期 > 96 + 新增测试数。
