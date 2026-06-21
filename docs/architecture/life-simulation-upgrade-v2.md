# Sylanne 生活模拟模块升级架构方案 v2（修订版）

日期：2026-06-18
基线：GitHub `main` 合并后 `metadata.yaml` 版本 `2.1.0`（工作树位于 `.clean-sylanne-github/`）
前置文档：`life-simulation-upgrade-proposal.md`（GPT-5.5 撰写，本文件是其评审与修订）
状态：已评审、已确认决策点，进入实施

---

## 0. 与原版（v1）的关系

本文件不是独立新方案，是对 `life-simulation-upgrade-proposal.md`（下称 v1）的**评审 + 修订**：

- v1 的**方向、文献依据、ADR、分阶段骨架**经 2.1.0 基线核对**整体成立**，予以保留。
- v1 的"接入方案"（§7）与"现状判断"（§1.1）存在 **4 个 HIGH 级**与 **7 个 MED 级**精度缺陷（见 §1），会在落地时引发返工。
- 本文件给出**修订版分阶段计划**（§2）与**第一批实施清单**（§3）。

基线核对方法：4 个并行 codegraph/read 探查，覆盖 `life_simulation.py` / `life_agent.py` / `llm_request_pipeline.py` / `proactive_bridge.py` / `proactive_scheduler.py` / `agents/learning/*` / `memory_system.py` / `main.py` / `_conf_schema.json` / `webui_*`，所有结论带 `file:line`。

---

## 1. v1 缺陷评审（按严重度）

### 1.1 🔴 HIGH（不解决就动手会返工）

| ID | 缺陷 | v1 怎么说 | 2.1.0 实际 | 证据 |
|----|------|-----------|-----------|------|
| H1 | `confidence`/`privacy` 字段在 `MemoryItem` 上**不存在** | §4.3/§7.3/§7.5 措辞像"带上 confidence/privacy_level 是顺手的事" | `MemoryItem` 只有 `source`（已用）；`confidence` 只存在于召回态 `RecallResult.confidence="clear/vague/tot"`（分类标签，非写入数值）；`privacy` 全仓零命中。需新建 2 字段 + `from_dict` 迁移 + `write_summary` 扩参 | `memory_system.py:133-155, 241, 841-849` |
| H2 | 召回**完全无** source/privacy 过滤 | §7.5"召回时应优先区分用户事实/模拟生活"像加个标注 | `recall()` 签名无此参数，`_gather_pool` 不读 `item.source`。这是**新能力**（召回链路 source-aware 排序/过滤层），非标注 | `memory_system.py:1241-1247, 1329` |
| H3 | 两条 outreach 路径 gate 不对称（v1 完全没提） | §7.4 只说"桥有最终否决权" | `_life_sim_outreach` 的 5 分钟 fallback（`llm_request_pipeline.py:2651-2707`）**只过 Bridge gate，绕过 ProactiveScheduler 的 cooldown/feedback_pressure/idle/人格下限**；只有 `run_once` 才完整过两套 gate。新增 Bridge gate 若不收口 fallback，生活事件仍能从该路径绕开新 gate 直发 | `proactive_scheduler.py:289-396` vs `llm_request_pipeline.py:2651-2707` |
| H4 | KV 无 tick 级持久化，崩溃丢全部演化 | §6.1/§7.1 措辞像"已有节流保存只需复用" | KV key `sylanne_life_sim_state` 仅 `initialize` 读、`terminate` 写；`simulate_tick` 内零 KV 写。**根本没有节流落盘**，非正常退出丢自开机起全部事件/活动/计数 | `main.py:2398, 2495`；`life_simulation.py` 全文无 `put_kv_data` |

### 1.2 🟡 MED（实现细节需澄清）

| ID | 缺陷 | v1 | 实际 / 处置 |
|----|------|----|-----------|
| M5 | `prompt_surface` 命名过载 | §7.1 想加 `LifeSimulator.prompt_surface()` | 基线已有 2 份 `prompt_surface.py`（顶层死代码 + engine 正本）+ SDK 概念引用。**改用 `life_prompt_fragment()`**，复用现有 `recent_context_for_prompt()` 改名 |
| M6 | RETIRED 是 per-session，life 是全局 | §7.6"consolidation 接入 RETIRED/terminate" | 不成立。另起**全局触发点**（类比 `autonomy_scheduler._global_autonomy`），不寄生 per-session RETIRED |
| M7 | 现有 ReflectionEngine 输出通道不可复用 | §4.4"可复用其预算、锁、低频、零/少 LLM 思路" | 思路可复用，**引擎实例不可复用**：现引擎只写 `_ParamState.reflection_bias`（单 float gate 偏置），prompt 自报"对话策略元认知反思器"。life reflection 需另建 `LifeReflection` Store + 下游消费总线 |
| M8 | `unanswered_penalty` 双重惩罚风险 | §4.6 列为 ShareIntent 新维度 | `ProactiveScheduler.feedback_pressure` 已半实现（数 cold_reply/unanswered）。Bridge gate 若也读 = 双重计数。**单一数据源**：Bridge 复用 `feedback_pressure` |
| M9 | `reason_code` 已是文案层非 gate 层 | §7.4 列为 gate 输入 | `infer_reason_code` 已存在但只构造 motivation 文本，不参与是否发送。第一阶段**只当文案层**，gate 化是后续语义 |
| M10 | `LifeSimulator` 类 docstring 陈旧 | v1 现状审查未抓出 | `life_simulation.py:155-166` 仍写"start()/stop()/5.停止循环"，但 `_loop`/`start`/`stop` 已全删。Phase 0 修正 |
| M11 | `event.shared` 措辞略误导 | §7.3"不再把 event.shared 视为真实送达" | `shared` 在 `_do_outreach` callback 返回即置 True，连"投递给桥"都不等于，只等于"已排队"（v1 §1.1 L45 自己已承认）。真正缺的是 `queued_at/dispatched_at/consumed_at/dropped_at` 四时点 |

### 1.3 🟢 LOW（命名卫生 / 细节）

- L12 `simulate_tick`(公开 wrapper)/`_simulate_tick`(实现) 双方法并存，v1 未区分，实施者可能改错方法体 → `life_simulation.py:229/238`
- L13 `_pending_emotion_delta` 是**死字段**（唯一写入 `:415`，从不读取），非"未保存"
- L14 `_countdown_callback` 已存在（拨动大饼倒计时），`state_dirty_callback` 是新增非复用
- L15 budget 口径：现有 per-session/day，life 应全局/天，复用机制不复用计数器实例
- L16 life consolidation 走零 LLM 还是 LLM 未定，与现有零 LLM `ConsolidationEngine` 范式相反 → **决策：配置开关**，默认关=零 LLM 复用范式，开了走 LLM 独立预算
- L17 `memory_summary_getter` **未被 main.py 接线**（`configure` 有形参但 `main.py:2376-2383` 没传）→ `_build_prompt` 的"最近聊天摘要"恒为空，潜在 bug
- L18 `/api/life/*` 不重复，但需说明与 `/api/state.life_simulation` 字段关系
- L19 `urgency` 字段 `LifeEvent` 已有（`:32`），§4.6 列为新增应改为复用

---

## 2. 修订版分阶段计划

保留 v1 的 Phase 0→4 骨架，按 §1 缺陷重组工作项。**记忆分级一次性做**（H1/H2 不拆）。**consolidation 配置开关**（L16）。

### Phase 0：契约、观测、基线债（零用户行为变化）
- 删除顶层死代码 `sylanne_alpha/prompt_surface.py`（M5 根因，已验无 import）
- 修正 `LifeSimulator` 类 docstring（M10）
- 接线 `memory_summary_getter`（L17）
- 清理 `_pending_emotion_delta` 死字段（L13）
- **新增 tick 后节流 KV 保存**（H4）：`state_dirty_callback` + main 注入节流落盘（60-180s 最多一次，参考 `state_persistence.put_fn` 异步模式）
- 结构化日志 + WebUI"最近生活事件/被 gate 原因/reason code/token"只读面板
- fake-LLM 单测：JSON 解析/冷却/body delta/KV 恢复/provider 未配置零副作用
- 拆 `event.shared`→加 `queued_at`（M11），保留 `shared` 兼容

### Phase 1：结构化事件 + 日计划（核心闭环）
- `LifeEventV2`/`LifeWorldState`/`LifePlan` dataclass + schema_version + 旧态迁移
- `_simulate_tick`（**私有那个**，L12）重构为编排器：`_load_world_context → _advance_activity → _record_event → _evaluate_share_intent → _emit_side_effects`
- `recent_context_for_prompt()` → **`life_prompt_fragment()`**（M5 改名，旧名 alias 兼容）；`life_agent.py` PRE 改调新名
- 引入 `ShareIntent`（复用已有 `urgency`，L19）
- **ShareIntent 评分必须收口两条 outreach 路径**（H3）：`_life_sim_outreach` fallback 与 `run_once` 走同一 gate 决策点
- pending outreach context 扩 `intent_id/reason_code/delivery_mode/expires_at/target_session` + 消费回执
- source 加 `life_reflection`/`user_explicit` 值（零成本）

### Phase 2：反思 + 巩固 + 记忆分级（一次性）
- **H1 一次性**：`MemoryItem` 加 `confidence: float`/`privacy_level: str` + `from_dict` 迁移 + `write_summary` 扩参
- **H2 一次性**：召回链路加 source-aware 排序/过滤层（新能力）
- `LifeReflection` Store（独立于现有 ReflectionEngine，M7）+ **全局触发点**（M6，不寄生 per-session RETIRED）
- `unanswered_penalty` 单一数据源化（M8）：Bridge gate 复用 `feedback_pressure`，不另计数
- `reason_code` 第一阶段定位为"文案层"（M9）
- `LifeConsolidationEngine`（**配置开关**，L16：默认关=零 LLM 复用现有 `ConsolidationEngine` 范式，开了=走 LLM 独立预算）

### Phase 3：项目 + 技能库（长期成长）——同 v1

### Phase 4：WebUI 控制闭环 ——同 v1，新增 `/api/life/*` 并标注与 `/api/state.life_simulation` 关系（L18）

---

## 3. 第一批实施清单（3 个串行 PR）

用户决策：**字段+召回过滤一起做**（H1/H2 一次性）、**PR 范围 = Phase 0 + Phase 1 结构化 + 全部债清理**、**先落档规划**、**直接改 `.clean-sylanne-github/`**。

### PR-A：Phase 0 基线债 + 持久化（零行为变化，风险最低）

| # | 工作 | 锚点 | 验证 |
|---|------|------|------|
| A1 | 删除顶层死代码 `sylanne_alpha/prompt_surface.py` | 已验 grep 零 import | 改后全量 import 无报错 |
| A2 | 修正 `LifeSimulator` 类 docstring（去掉 start/stop/_loop） | `life_simulation.py:155-166` | docstring 与实现一致 |
| A3 | 接线 `memory_summary_getter`（main.py configure 补传参） | `main.py:2376-2383` | `_build_prompt` 记忆摘要非空 |
| A4 | 清理 `_pending_emotion_delta` 死字段 | `life_simulation.py:89,415` | grep 无残留 |
| A5 | **加 tick 后节流 KV 保存** | `life_simulation.py:278-282` 后；main.py 注入 | 崩溃后重启恢复最近事件 |
| A6 | fake-LLM 单测 | 新增 `tests/test_life_sim_persistence.py` | 测试通过 |

### PR-B：Phase 1 结构化 + 观测（核心闭环，无分享策略改动）

| # | 工作 | 锚点 |
|---|------|------|
| B1 | `LifeEventV2`/`LifeWorldState`/`LifePlan` + schema_version | `life_simulation.py` |
| B2 | 旧态迁移（旧 events→V2，source="legacy", confidence=0.5, privacy_level="internal"） | `LifeSimulationState.from_dict` |
| B3 | `_simulate_tick`（私有）重构为编排器 | `life_simulation.py:238` |
| B4 | `recent_context_for_prompt()`→`life_prompt_fragment()`；life_agent.py PRE 改调 | `life_simulation.py:444`；`life_agent.py:76` |
| B5 | source 加 `life_reflection`/`user_explicit` | `memory_system.py:146` |
| B6 | 结构化日志 + WebUI 只读 life status 面板 | `webui_routes.py` |
| B7 | 单测：迁移、活动延续、节律一致性、prompt 长度上限 | `tests/` |

### PR-C：ShareIntent + 双路径收口（最复杂，单独做）

| # | 工作 | 锚点 |
|---|------|------|
| C1 | `ShareIntent` dataclass（复用 `urgency`） | `life_simulation.py:32` |
| C2 | **H3**：统一两条 outreach 路径到同一 gate 评估函数 | `llm_request_pipeline.py:2651-2707` vs `proactive_scheduler.py:289-396` |
| C3 | pending outreach context 扩字段 + 消费回执 | `llm_request_pipeline.py:2625` |
| C4 | 拆 `event.shared`→`queued_at/dispatched_at/consumed_at/dropped_at` | `life_simulation.py:434` |
| C5 | 集成测试：双路径 gate 一致性 | `tests/` |

---

## 4. 工程纪律（贯穿所有 PR）

- 保留 `LifeSimulator` 对外接口，不破坏兼容
- 所有新状态可迁移、可裁剪；旧档向前兼容（`from_dict` 容缺）
- provider 未配置（`provider_id==""`）或 `enabled=false` 时零副作用（`life_simulation.py:240-241` 已保证，新代码不得破坏）
- 生活模拟输出永远是**素材**，不绕过主模型/桥直发（`llm_request_pipeline.py:2713-2714` 纪律）
- 每个 PR 必须带 fake-LLM 测试，不依赖真实 LLM 即可验证状态机/迁移/持久化

## 5. ADR（沿用 v1，补充两条）

- **ADR-005**（新增）：两条 outreach 路径（`_life_sim_outreach` fallback 与 `ProactiveScheduler.run_once`）必须共用同一 gate 评估函数，新增任何分享评分维度（interruptibility/unanswered/relationship_value/expires_at）同时对两路径生效。理由：防止生活事件从 fallback 绕开新 gate 直发（H3）。
- **ADR-006**（新增）：记忆分级改造一次性完成——`MemoryItem` 加 `confidence`/`privacy_level` 字段与召回链路 source-aware 过滤在同一 Phase 落地，避免"加了字段但召回不认"的半成品状态（H1/H2）。
- **ADR-007**（新增）：夜间巩固走配置开关，默认关=零 LLM（复用现有 `ConsolidationEngine` 范式），开了=走 LLM（新建 `LifeConsolidationEngine` 独立预算）。理由：尊重用户成本主权，同时保留升级路径（L16）。
