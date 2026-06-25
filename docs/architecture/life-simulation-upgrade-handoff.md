# Sylanne 生活模拟升级 — 交接文档（Handoff）

日期：2026-06-18
基线：`metadata.yaml` 版本 `2.1.0`（工作树 `.clean-sylanne-github/`，远端 main 合并后快照）
规划文档：`docs/architecture/life-simulation-upgrade-v2.md`（修订版，含缺陷评审）
原版提案：`docs/architecture/life-simulation-upgrade-proposal.md`（GPT-5.5 撰写，已评审）

---

## 0. 一句话状态

评审了 GPT-5.5 提案（发现 4 HIGH + 7 MED 缺陷），产出修订版规划 v2，**PR-A（Phase 0 基线债 + 持久化）+ PR-B（Phase 1 结构化 + 观测）+ PR-C（ShareIntent + 双路径收口）均已完成并测试通过**。第一批落地范围（Phase 0 + Phase 1 结构化 + 全部债清理）已闭合。下一步是 Phase 2（记忆字段 + 召回过滤 + 反思巩固）。

**PR-A review 处置记录**（`life-simulation-upgrade-pr-a-review.md` + `life-simulation-upgrade-pr-a-review-response-review.md`）：
- HIGH（provider 空→状态污染）：**已修**。`_simulate_tick` 加 `enabled` 防线，`last_simulation_time`/`simulation_count` 的 bump 推迟到 event 确认后。
- **二审 HIGH（空 tick 仍拨 countdown）**：**已修**。`_countdown_callback` 一并移入 `if event:` 块内，与 dirty save 统一由 event 门控。
- MED（zip 与源码不一致）：**标注为 release 产物**（见 §11 release 校验清单）。
- 测试缺口（pipeline memory summary）：**已补**。

**PR-B 完成记录**（Phase 1 结构化 + 观测）：LifeEvent V2 增量字段 + LifeWorldState/LifePlan/LifeActivity + 常量类；旧档迁移；`_simulate_tick` 编排器重构；`life_prompt_fragment`（结构化 + 长度上限 + 隐私过滤）+ alias；`memory_system` MemorySource 常量；`/api/life/status` WebUI 路由。

**PR-C 完成记录**（ShareIntent + 双路径收口，最复杂）：
- C1：`ShareIntent` dataclass + `DeliveryMode` 常量 + `_evaluate_share_intent`（规则化评分，零 LLM，复用 `urgency` L19）+ final_score → delivery_mode 阈值映射。
- C2 **H3 收口（提案盲点，已修）**：`ProactiveScheduler.evaluate_outreach_gate(session_key)` 新增；`_life_sim_outreach` 5min fallback 在过 Bridge gate **之前**先过 scheduler gate（cooldown/quiet/feedback/人格下限）。两条 outreach 路径（`request_dispatch` 与 `_life_sim_outreach` fallback）现在走同一口径 scheduler gate，生活事件不再能从 fallback 绕开 cooldown 直发。
- C3：pending outreach context 扩字段（intent_id/reason_code/delivery_mode/expires_at/target_session/queued_at）+ 消费回执（`_prepare_memory_context` pop 时回写 consumed_at）。
- C4：拆 `event.shared` → 四时点（queued_at/dispatched_at/consumed_at/dropped_at，M11）；`pending_share_events` 用四时点语义；新增 `mark_outreach_dispatched/consumed/dropped` helper。
- delivery_mode=SILENT（score<0.25）直接跳过 outreach，只留 journal（v2 §4.6）。
- C5：新增 `tests/test_life_sim_share_intent.py`（11 测试：评分映射/SILENT 跳过/intent 存储/四时点语义/mark helper/roundtrip/三参+两参回调兼容/H3 gate 双向）。
- 全量测试 **88/88 通过**（17 persistence + 9 structured + 11 share_intent + 51 回归），AST OK。

**仍未做（Phase 2 范畴）**：H1（MemoryItem 加 confidence/privacy 字段）、H2（召回链路 source-aware 过滤）、`LifeReflection` Store（独立引擎，M7）+ 全局触发点（M6）、`unanswered_penalty` 单一数据源（M8）。Phase 3：项目/技能库。

---

## 1. 已锁定的决策（不要再问）

| 决策点 | 结论 |
|--------|------|
| 代码基线 | 远端 `main`（PR 合并后）= `.clean-sylanne-github/` 是真基线 2.1.0；**本地工作树 `G:\Sylanne-next\sylanne_alpha\` 是旧 1.4.0，不要看它** |
| 工作目录 | 直接改 `.clean-sylanne-github/`（改完用户自己同步回远端） |
| 记忆分级范围 | 字段 + 召回过滤**一次性做完**（H1/H2 不拆 2a/2b） |
| 第一批 PR 范围 | Phase 0 + Phase 1 结构化 + 全部 LOW/MED 债清理 |
| consolidation LLM | **配置开关**：默认关=零 LLM（复用现有 `ConsolidationEngine` 范式），开了走 LLM（新建 `LifeConsolidationEngine` 独立预算） |
| 实施方式 | 3 个串行 PR：A→B→C，每个可独立验证/回滚 |

---

## 2. 缺陷清单（评审结论，详见 v2 文档 §1）

### 🔴 HIGH（已纳入 PR 计划）
- **H1**：`MemoryItem` 无 `confidence`/`privacy` 字段 → `memory_system.py:133-155, 841-849`
- **H2**：召回 `recall()` 无 source/privacy 过滤 → `memory_system.py:1241-1247`（新能力，非标注）
- **H3**：两条 outreach 路径 gate 不对称——`_life_sim_outreach` 5min fallback 绕过 ProactiveScheduler gate → `llm_request_pipeline.py:2651-2707` vs `proactive_scheduler.py:289-396`
- **H4**：KV 无 tick 级持久化，崩溃丢全部演化 → **PR-A 已修**

### 🟡 MED
- **M5** `prompt_surface` 命名过载（3 处）→ **PR-A 已删顶层死代码**；Phase 1 用 `life_prompt_fragment()` 改名
- **M6** RETIRED 是 per-session，life 是全局 → Phase 2 另起全局触发点
- **M7** 现有 ReflectionEngine 输出通道不可复用（只写 gate 偏置 float）→ Phase 2 另建 LifeReflection Store
- **M8** `unanswered_penalty` 双重惩罚风险 → Phase 2 单一数据源（Bridge 复用 `feedback_pressure`）
- **M9** `reason_code` 已是文案层非 gate 层 → 第一阶段只当文案
- **M10** LifeSimulator docstring 陈旧 → **PR-A 已修**
- **M11** `event.shared` 措辞 → PR-C 拆 `queued_at/dispatched_at/consumed_at/dropped_at`

### 🟢 LOW
- **L12** `simulate_tick`(公开)/`_simulate_tick`(实现) 双方法 → Phase 1 注意改私有那个
- **L13** `_pending_emotion_delta` 死字段 → **PR-A 已删**
- **L14** `_countdown_callback` 已存在，`state_dirty_callback` 是新增 → **PR-A 已加**
- **L15** budget 口径 per-session vs 全局
- **L16** consolidation LLM → **已决策：配置开关**
- **L17** `memory_summary_getter` 未接线 → **PR-A 已修**
- **L18** `/api/life/*` 与 `/api/state.life_simulation` 关系
- **L19** `urgency` 字段已有 → Phase 1 复用

---

## 3. ✅ PR-A 已完成（不要重做）

**改动 6 个文件，零用户可见行为变化；已过 code review 并修复：**

| 项 | 文件 | 变更摘要 |
|----|------|---------|
| A1 | `sylanne_alpha/prompt_surface.py` | **删除**（顶层死代码，已验 grep 零 import） |
| A2 | `sylanne_alpha/life_simulation.py:155-169` | `LifeSimulator` docstring 改为反映 AutonomyScheduler 驱动（去掉 start/stop/_loop） |
| A3 | `sylanne_alpha/llm_request_pipeline.py`（加 `_life_sim_memory_summary`）+ `main.py:2376-2383`（configure 补传参） | 修 L17 latent bug：`_build_prompt` 的记忆摘要原恒为空 |
| A4 | `sylanne_alpha/life_simulation.py:89,419` | 删 `_pending_emotion_delta` 死字段 |
| A5 | `sylanne_alpha/life_simulation.py`（`configure` 加 `state_dirty_callback` + tick 末尾触发）+ `main.py`（`_life_sim_throttled_save` 节流 90s + 常量 `_LIFE_SIM_SAVE_MIN_GAP_SECONDS`） | 修 H4：tick 后节流落盘 KV，崩溃不丢 |
| A6 | `tests/test_life_sim_persistence.py` | 新增 13 个 fake-LLM 单测 |

**PR-A review HIGH 修复**（`_simulate_tick` 状态污染）：
- 加 `if not self.enabled: return` 防线
- `last_simulation_time`/`simulation_count` 的 bump 移到 `if event:` 块内（空响应零副作用）
- `state_dirty_callback` 改为仅在有 event 时触发（空 tick 不落盘）
- 补 2 个真实路径测试：`test_configured_caller_returning_empty_is_noop`、`test_disabled_simulator_with_llm_caller_is_noop`

**验证结果**：
- 新测试 `13/13 通过`（含 KV roundtrip、零副作用三种路径、dirty callback 触发/失败隔离、memory_summary 消费、pipeline 级取 memory、死字段移除）
- 回归 `tests/test_agents_gating.py test_agents_infra.py test_evolution_learning.py test_dream_consolidation.py` 共 `51/51 通过`
- AST 语法 OK

**已知捕获的基线缺陷**（测试已记录现状，Phase 1 修）：
- `to_dict/from_dict` 不保存 `event_type`（提案 §1.2 L82）→ `test_state_roundtrip_preserves_events_and_activity` 断言记录

---

## 4. ⏭️ PR-B 待办（Phase 1 结构化 + 观测，无分享策略改动）

目标：生活有连续性。**注意 L12：改私有 `_simulate_tick`，公开 `simulate_tick` 是 wrapper 保留。**

### B1. V2 dataclass（`life_simulation.py`）
- 新增 `LifeEventV2`（字段：event_id/timestamp/source/activity_id/project_id/event_type/summary/private_thought/mood/valence_delta/arousal_delta/importance/novelty/confidence/privacy_level/caused_by/followups/share_intent_id）
- 新增 `LifeWorldState`（schema_version/local_date/phase/energy/focus/mood_baseline/current_activity_id/active_plan_id/active_project_ids/habits/relationship_snapshot/last_tick_at）
- 新增 `LifePlan`（plan_id/date/timezone/anchors/flexible_slots/commitments/generated_from/confidence）
- 加 `SCHEMA_VERSION` 常量

### B2. 旧态迁移（`LifeSimulationState.from_dict`）
- 读旧格式时生成最小 `LifeWorldState`
- 旧 events → `LifeEventV2`：`source="legacy_life_sim"`, `confidence=0.5`, `privacy_level="internal"`
- 顺便修 `event_type` 序列化缺失（PR-A 测试已记录此缺陷）

### B3. 编排器重构（`life_simulation.py:238` `_simulate_tick`）
**改私有那个，公开 `simulate_tick`（`:229`）保留为 wrapper。**
- 拆成：`_load_world_context() → _advance_activity() → _record_event() → _evaluate_share_intent() → _emit_side_effects()`

### B4. 改名（M5，避免 `prompt_surface` 过载）
- `recent_context_for_prompt()` → **`life_prompt_fragment()`**（`life_simulation.py:~444`）
- 旧名保留为 alias 兼容（或直接改调用点）
- `agents/life_agent.py:76` PRE 阶段改调新名

### B5. source 新值（零成本）
- `memory_system.py:146` `MemoryItem.source` 已是开放字符串，加 `life_reflection`/`user_explicit` 取值（无需 schema 改动）

### B6. 结构化日志 + WebUI 只读面板
- `_simulate_tick` 加结构化日志：tick 次、LLM 成败、parse 成功率、event_type 分布、wants_to_share、outreach queued/consumed/dispatched/gated/expired
- `webui_routes.py`/`webui_server.py` 加只读 life status（最近事件、被 gate 原因、reason code、token 预算）
- 现状：只有 `/api/state.life_simulation` 字段（`webui_routes.py:369`），无 `/api/life/*` 专用路由

### B7. 单测
- 迁移（旧 events→V2）
- 活动延续（同活动能持续/暂停/完成）
- 节律一致性（不出现凌晨高能活动）
- prompt fragment 长度上限

---

## 5. ⏭️ PR-C 待办（ShareIntent + 双路径收口，最复杂）

### C1. `ShareIntent` dataclass
- 字段见 v2 文档；**复用已有 `urgency`**（`life_simulation.py:32`，L19）

### C2. 🔴 H3 核心：统一两条 outreach 路径
- `_life_sim_outreach` 的 5min fallback（`llm_request_pipeline.py:2651-2707`）与 `ProactiveScheduler.run_once`（`proactive_scheduler.py:289-396`）收口到**同一个 gate 评估函数**
- 新增评分维度（interruptibility/unanswered/relationship_value/expires_at）同时对两路径生效
- **关键纪律**：Bridge 仍拥有最终否决权，生活模拟不绕过 Bridge 直发（`llm_request_pipeline.py:2713-2714`）

### C3. pending outreach context 扩字段 + 消费回执
- 现 pending 字段仅 `{reason, mood}`（`llm_request_pipeline.py:2625-2628`）
- 扩 `intent_id/reason_code/delivery_mode/expires_at/target_session`
- 现消费是 `.pop()` 无回写（`:1416`）→ 加消费回执

### C4. 拆 `event.shared`（M11）
- → `queued_at/dispatched_at/consumed_at/dropped_at` 四时点
- 写入点 `life_simulation.py:434`；读取点 `:101,129,442`

### C5. 集成测试
- 双路径 gate 一致性
- Bridge gate 拒绝时不直发

---

## 6. 关键 file:line 锚点速查

| 符号/位置 | 文件:行 |
|-----------|---------|
| `LifeSimulator` 类 | `life_simulation.py:154` |
| `simulate_tick`（公开 wrapper） | `life_simulation.py:229` |
| `_simulate_tick`（实现，编排器改这个） | `life_simulation.py:238` |
| `_countdown_callback` 触发点 | `life_simulation.py:278-282` |
| `state_dirty_callback` 触发点（PR-A 新增） | `life_simulation.py:283-290` |
| `recent_context_for_prompt`（待改名） | `life_simulation.py:~444` |
| `LifeSimulationState.to_dict/from_dict` | `life_simulation.py:91-132` |
| `LifeAgent.act` PRE 调 recent_context | `agents/life_agent.py:76` |
| `LifeAgent.act` AUTONOMOUS 调 simulate_tick | `agents/life_agent.py:64-72` |
| `_life_sim_llm_call` | `llm_request_pipeline.py:2585` |
| `_life_sim_outreach`（5min fallback） | `llm_request_pipeline.py:2605-2742` |
| `_life_sim_outreach` 5min fallback gate 漏洞（H3） | `llm_request_pipeline.py:2651-2707` |
| `_life_sim_body_delta` | `llm_request_pipeline.py:~2820`（PR-A 后行号偏移） |
| `_life_sim_memory_summary`（PR-A 新增） | `llm_request_pipeline.py:~2795` |
| `_most_recent_host_key`（4 处回调共用） | `llm_request_pipeline.py:647-663` |
| pending outreach context 注册（BoundedDict 50） | `session_state_store.py:164` |
| pending 消费 `.pop()` 无回写 | `llm_request_pipeline.py:1416` |
| `MemoryItem` 字段（无 confidence/privacy） | `memory_system.py:133-155` |
| `MemoryItem.source`（已用 life_sim） | `memory_system.py:146` |
| `write_summary` 签名（无 confidence/privacy） | `memory_system.py:841-849` |
| `recall()`（无 source filter） | `memory_system.py:1241-1247` |
| `ProactiveBridge` 类 | `proactive_bridge.py` |
| Bridge gate：quiet_hours/min_interval/hesitation | `proactive_bridge.py:173-217, 368-418` |
| `infer_reason_code`（文案层，非 gate） | `proactive_bridge.py:219-257` |
| `ProactiveScheduler.request_dispatch`（完整过两套 gate） | `proactive_scheduler.py:289-396` |
| `feedback_pressure`（unanswered 半实现） | `proactive_scheduler.py:81-92` |
| `AutonomyScheduler._global_autonomy`（全局触发范例） | `agents/autonomy_scheduler.py:147-158` |
| `ReflectionEngine`（对话策略反思器，勿混） | `agents/learning/reflection.py:43-225` |
| `ConsolidationEngine`（零 LLM，per-session RETIRED） | `agents/learning/consolidation.py:24-145` |
| life sim KV 读写 | `main.py:2398`（读）/ `main.py:~2497`（写 terminate） |
| `_start_life_simulator` configure 注入 | `main.py:2376-2383` |
| `_life_sim_throttled_save`（PR-A 新增） | `main.py:~2435` |
| KV key 名（全局单一） | `"sylanne_life_sim_state"` |

---

## 7. 工程纪律（贯穿所有 PR）

- 保留 `LifeSimulator` 对外接口，不破坏兼容
- 新状态可迁移、可裁剪；旧档向前兼容（`from_dict` 容缺）
- **provider 未配置（`provider_id==""`）或 `enabled=false` 时零副作用**（`life_simulation.py:240-241`，新代码不得破坏）——包括：不 bump 计数/时间、不产 event、不触发 dirty save、**不拨动 countdown**（后者会改写大饼 session override + 重排主动发言调度）。空 tick 的所有副作用出口（countdown + dirty）统一由 `if event:` 门控。
- 生活模拟输出永远是**素材**，不绕过主模型/桥直发（`llm_request_pipeline.py:2713-2714`）
- 每个 PR 必须带 fake-LLM 测试，不依赖真实 LLM

---

## 8. 测试命令

```powershell
# PR-A 新测试
python -m pytest tests/test_life_sim_persistence.py -v

# 回归（agents/learning）
python -m pytest tests/test_agents_gating.py tests/test_agents_infra.py tests/test_evolution_learning.py tests/test_dream_consolidation.py -q

# AST 语法检查（改后必跑）
python -c "import ast; [ast.parse(open(f, encoding='utf-8').read()) for f in ['sylanne_alpha/life_simulation.py', 'sylanne_alpha/llm_request_pipeline.py', 'main.py']]; print('OK')"
```

**注意**：`tests/` 下有 `manual_*.py`（手动 e2e）和 `test_*.py`（单测）。`glob` 工具对 `.clean-sylanne-github/` 带点目录有遍历缺陷，**用 bash `Test-Path`/`Get-ChildItem` 或 grep 工具**，不要信 glob 的"No files found"。

---

## 9. 已发现的潜在风险（实施时留意）

1. **codegraph 对 `.clean-sylanne-github` 索引不可靠**：codegraph 读的是主工作树 `G:\Sylanne-next`（1.4.0）的索引，查 `.clean-sylanne-github` 文件时会警告并可能返回错版本源码。**对同名文件（如 `life_simulation.py`）直接用 Read 工具读 `.clean-sylanne-github/` 路径，不要信 codegraph 的源码块**。
2. **`_most_recent_host_key` 多会话漂移**（提案 §7.8）：4 个 life-sim 回调共用它决定目标 session。Phase 2 处理。
3. **`_feedback_history` 可能是死代码**：`ProactiveScheduler` 有 `_feedback_history`（`proactive_scheduler.py:60-61`）但 `derive_dispatch_policy` 实际读 `_proactive_dispatch_audit`。Phase 2 做 unanswered 单一数据源时留意。
4. **`_engine/sylanne_core/compute/prompt_surface.py` 是 canonical**（kernel 用它），顶层那个已删。

---

## 10. 原版提案的"可直接采纳"部分

GPT-5.5 提案的以下部分**经验证准确，可直接用**：
- §2 文献依据（Generative Agents / Voyager / Reflexion / ReAct / 睡眠巩固 / Horvitz mixed-initiative / ACT-R-Soar）
- §3 设计目标 + 非目标
- §4.1-4.8 目标架构（dataclass 设计，注意 §4.3 `confidence`/`privacy` 字段需新建）
- §5 数据流 mermaid
- §9 测试策略
- §10 风险与边界
- §14 ADR-001~004（+ v2 新增 ADR-005~007）

---

## 11. Release 校验清单（PR-A 引入，发布前必跑）

`astrbot_plugin_sylanne.zip` 是 git 跟踪的**发布产物**（非 `.gitignore`；`.gitignore:4` 只忽略不同名的 `Sylanne-embodiment.zip`，`.gitignore:78` 忽略未跟踪的 `scripts/plugin_zip_preflight.js`）。PR-A 改的是源码树，发布 zip 仍是旧版（含已删的顶层 `prompt_surface.py`）。**发布前需重建 zip 并校验**：

```powershell
# 重建后（具体打包命令见仓库 release 流程）校验 zip 内：
Add-Type -AssemblyName System.IO.Compression.FileSystem
$z = [System.IO.Compression.ZipFile]::OpenRead("astrbot_plugin_sylanne.zip")

# 1. 不含已删的顶层死代码（PR-A1）
$z.Entries | Where-Object { $_.FullName -eq "sylanne_alpha/prompt_surface.py" }
# 期望：空（不存在）

# 2. life_simulation.py 含 PR-A5 节流钩子 + review 防线 + PR-B/C 新符号
$ls = (New-Object System.IO.StreamReader($z.GetEntry("sylanne_alpha/life_simulation.py").Open())).ReadToEnd()
$ls -match "_state_dirty_callback"     # PR-A5
$ls -match "if not self.enabled"        # PR-A review 防线
$ls -match "ShareIntent"                # PR-C1
$ls -match "DeliveryMode"               # PR-C1
$ls -match "life_prompt_fragment"       # PR-B4
$ls -match "mark_outreach_dispatched"   # PR-C4
$ls -match "mark_outreach_consumed"     # PR-C4
$ls -match "mark_outreach_dropped"      # PR-C4
$ls -match "pending_share_events"       # PR-C4 四时点语义核心读口（二审 MED2 补）
$ls -match "_callback_accepts_intent"   # PR-B/C review MED3

# 3. main.py 含节流落盘方法（PR-A5）
$mp = (New-Object System.IO.StreamReader($z.GetEntry("main.py").Open())).ReadToEnd()
$mp -match "_life_sim_throttled_save"   # PR-A5

# 4. llm_request_pipeline.py 含 memory summary getter（PR-A3）+ H3 收口（PR-C2）
$lp = (New-Object System.IO.StreamReader($z.GetEntry("sylanne_alpha/llm_request_pipeline.py").Open())).ReadToEnd()
$lp -match "_life_sim_memory_summary"   # PR-A3
$lp -match "evaluate_outreach_gate"     # PR-C2 H3 收口

# 5. proactive_scheduler.py 含 evaluate_outreach_gate（PR-C2）
$ps = (New-Object System.IO.StreamReader($z.GetEntry("sylanne_alpha/proactive_scheduler.py").Open())).ReadToEnd()
$ps -match "evaluate_outreach_gate"      # PR-C2

# 6. memory_system.py 含 MemorySource 常量（PR-B5）
$ms = (New-Object System.IO.StreamReader($z.GetEntry("sylanne_alpha/memory_system.py").Open())).ReadToEnd()
$ms -match "class MemorySource"          # PR-B5

# 7. webui_server.py 含 /api/life/status 路由（PR-B6）
$wu = (New-Object System.IO.StreamReader($z.GetEntry("sylanne_alpha/webui_server.py").Open())).ReadToEnd()
$wu -match "/api/life/status"            # PR-B6

$z.Dispose()
```

> 注：脚本覆盖 PR-A/B/C 全部关键符号。任一为 False 则 zip 是旧的，需重建。zip 不纳入 PR 代码审查范围（属发布工程），但发布前必须重建。

---

## 12. Gate 结论

```text
PR-A: Approved（最终；review HIGH 已修 + zip 转 release 校验）
PR-B: Approved（最终；HIGH1 world mutation 纯计算化 + MED3 TypeError→inspect + 二审 MED1 可观测日志）
PR-C: Approved（最终；H3 双路径收口 + HIGH2 消费路径过期 + 二审 MED2 preflight 补全）
第一批范围（Phase 0 + Phase 1 结构化 + 全部债清理）：闭合（96/96 测试通过，两轮 review findings 全 closed）
Phase 2（记忆字段 + 召回过滤 + 反思巩固）：可启动
```

**第一批关键缺陷全部闭合**：
- H1/H2（记忆 confidence/privacy + 召回过滤）→ Phase 2
- **H3（双路径 gate 不对称）→ PR-C 已修**
- H4（崩溃丢演化）→ PR-A 已修
- **PR-B review HIGH1（world mutation 打穿零副作用）→ 已修**
- **PR-C review HIGH2（pending 过期只在 fallback 查）→ 已修**
- **二审 MED1（outreach 异常静默吞）→ 已修**（加 warning 日志，可观测）
- **二审 MED2（preflight 漏 pending_share_events）→ 已修**
- **二审 LOW3（测试复刻逻辑非直调）→ 已修**（case3 直调真实 _prepare_memory_context）

**契约扩展纪律 + 表述精确纪律**（三轮 review 共同主题）：
1. 每加新状态/出口，零副作用/时效契约同步审计
2. 实现对了 ≠ response 可夸大（`except: pass` 是静默吞不是"真实处理"）
3. 测试直调真实函数，不复刻逻辑（防一起假绿）
4. 清单核对用脚本，不手抄
