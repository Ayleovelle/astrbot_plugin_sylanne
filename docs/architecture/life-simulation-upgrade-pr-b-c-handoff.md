# Sylanne 生活模拟升级 PR-B / PR-C Handoff

日期：2026-06-18
基线：`.clean-sylanne-github/`（`metadata.yaml` 2.1.0）
前置：`life-simulation-upgrade-handoff.md`（§0/§12 已更新），`life-simulation-upgrade-v2.md`（规划）
状态：**PR-B/PR-C review findings 已全部修复并通过复现测试（见 `life-simulation-upgrade-pr-b-c-review-response.md`）。主 handoff Gate 已同步为 Approved。**

---

## 0. 一句话

PR-A 的零副作用契约先过两轮 review 闭合（dirty save → countdown）。PR-B 给生活模拟加了结构化世界模型（相位/能量/计划/编排器/结构化 prompt 片段）。PR-C 把 `wants_to_share: bool` 升级为 `ShareIntent` 评分，并闭合了提案最严重的盲点 H3——两条 outreach 路径现在走同一 scheduler gate。

全量 **88/88 测试通过**（17 persistence + 9 structured + 11 share_intent + 51 回归），AST 全 OK。

---

## 1. PR-B 完成项（Phase 1 结构化 + 观测）

### B1：V2 dataclass + 常量（`life_simulation.py:18-308`）
- `SCHEMA_VERSION = 2`
- `LifeSource`（LEGACY/PLANNED_TICK/USER_INTERACTION/REFLECTION/CONSOLIDATION）
- `LifePrivacy`（INTERNAL/SHAREABLE/USER_FACT）—— life sim 永不自造 USER_FACT（v2 ADR-002）
- `LifePhase`（MORNING/AFTERNOON/EVENING/NIGHT/SLEEP）+ `_phase_for_hour()` 规则化
- `LifeEvent` **schema scaffolding**：v1 字段 + V2 增量字段（含 queued_at/dispatched_at/consumed_at/dropped_at/share_intent_id 占位）。**PR-B 只保证字段可迁移、可持久化；四时点语义/启用/pending 判定/mark helper 归 PR-C（C4）**——边界划分见 review LOW6
- `LifeActivity` / `LifePlan` / `LifeWorldState` 新 dataclass

### B2：序列化 helper + 迁移（`life_simulation.py:310-460`）
- `_event_to_dict` / `_event_from_dict` / `_world_to_dict` / `_world_from_dict` / `_plan_to_dict` / `_plan_from_dict`
- `LifeSimulationState` 新增 `world: LifeWorldState` + `plan: LifePlan | None`
- 旧档迁移：无 source → `LEGACY`，confidence 默认 0.5，privacy_level 兜底 INTERNAL，无 world/plan → 默认/None
- **修复 v1 to_dict 漏存 event_type 缺陷**（提案 §1.2 L82，测试已从"记录现状"改为断言修复）

### B3：`_simulate_tick` 编排器（`life_simulation.py:559-595`）
- **改私有那个**（`:559` `_simulate_tick`），公开 `simulate_tick`（`:555`）保留 wrapper（L12 纪律）
- 拆成：`_load_world_context → LLM → _parse_response → _record_event → _emit_side_effects → _log_tick`
- `_load_world_context`（`:599`）：相位/能量规则化更新（夜间低能量，朝目标回归），零 LLM
- `_record_event`（`:717`）：填 V2 字段（source=PLANNED_TICK / importance 规则评分 / privacy_level 默认 SHAREABLE / queued_at）
- `_parse_response`（`:771`）返回 `(LifeEvent, emotion_weights)` tuple
- `_build_prompt`（`:802`）接受 ctx，注入节律约束（夜间/低能量提示"活动应偏安静"）

### B4：`life_prompt_fragment`（M5 改名，`life_simulation.py:955`）
- 结构化 `[life_world]` 片段（节律/当前活动/最近事件/关系边界）
- `max_budget` 硬上限（默认 800，超限截尾）—— v2 §6.2 prompt 预算稳定
- 隐私过滤：USER_FACT 事件不进用户可见片段
- `recent_context_for_prompt` 保留为 alias（`proactive_bridge.py:283` 未改，降低风险）
- `agents/life_agent.py:76` PRE 改调新名

### B5：`MemorySource` 常量（`memory_system.py:42`）
- `MemorySource`（DIALOGUE/INTERACTION/USER_EXPLICIT/LIFE_SIM/LIFE_REFLECTION）
- 开放字符串字段，新取值零 schema 改动

### B6：`/api/life/status` WebUI 路由（`webui_server.py:282`）
- 只读观测面板：节律/当前活动/最近事件/来源隐私分布/prompt fragment 预览
- 路由注册 `webui_server.py:1318`

### B7：测试（`tests/test_life_sim_structured.py`，9 测试）

---

## 2. PR-C 完成项（ShareIntent + 双路径收口，最复杂）

### C1：`ShareIntent` 评分（`life_simulation.py:308-372`）
- `DeliveryMode`（SILENT/NEXT_REPLY/BRIDGE/DIRECT）
- `_SHARE_WEIGHTS`（v2 §4.6 决策公式）
- `_score_to_delivery()` 阈值映射（< 0.25 silent / < 0.55 next_reply / < 0.78 bridge / >= 0.78 direct）
- `_evaluate_share_intent()`（`life_simulation.py` `LifeSimulator` 内）：规则化评分（content_value=importance / relationship_value 受 warmth 调制 / urgency 复用 L19 / interruptibility 据相位 / cooldown_penalty / privacy_risk），零 LLM
- `LifeSimulator._share_intents: dict[intent_id, ShareIntent]` store

### C2 / H3：双路径 gate 收口（提案盲点，已修）⭐
- `ProactiveScheduler.evaluate_outreach_gate(session_key) -> (allowed, reason)`（`proactive_scheduler.py:213`）
  - session_key-only 封装 `dispatch_blocked_reason`（cooldown/quiet/feedback/人格下限）
  - **不**跑 `derive_should_send` / 不取 surface / 不跑 hesitation（后者仍是 Bridge 职责，ADR）
- `_life_sim_outreach` 5min fallback（`llm_request_pipeline.py:2635` `_fallback_direct_send`）改为：
  1. **先过 `scheduler.evaluate_outreach_gate`**（H3 闭合）→ blocked 则存回 pending 不直发
  2. 再过 Bridge `should_dispatch_now`（quiet_hours/min_interval）+ hesitation
  3. 都过才 `bridge.dispatch`；失败存回 pending
- 结果：两条路径（`request_dispatch` 与 `_life_sim_outreach` fallback）现在走同一 scheduler gate 口径，生活事件不再能从 fallback 绕开 cooldown 直发

### C3：pending context 扩字段 + 消费回执（`llm_request_pipeline.py:2605`）
- pending 字段从 `{reason, mood}` 扩到 `{reason, mood, intent_id, event_id, delivery_mode, reason_code, expires_at, target_session, queued_at}`
- `expires_at` 过期丢弃（默认 30min）
- `_mark_life_outcome(event_id, outcome)`（`:2810`）：pipeline 回写 LifeEvent 投递时点
- `_prepare_memory_context` 消费 pending 时回写 `consumed_at`（`:1416`）

### C4：投递四时点（M11，`life_simulation.py`）
- `event.shared` 保留兼容，但判定改用 `queued_at`/`dispatched_at`/`consumed_at`/`dropped_at`
- `pending_share_events()` 改语义：`wants_to_share AND queued>0 AND consumed==0 AND dropped==0`
- `mark_outreach_dispatched/consumed/dropped(event_id, now)` helper
- `share_intent_id` 字段持久化（`_event_to_dict`/`_event_from_dict` 已含）
- delivery_mode=SILENT（score<0.25）直接跳过 outreach，只留 journal

### C5：测试（`tests/test_life_sim_share_intent.py`，11 测试）
- 评分阈值映射 / SILENT 跳过 outreach / intent 存储与挂载
- 四时点 pending 语义 / mark helper 回写 / share_intent_id roundtrip
- 三参 + 两参回调签名兼容（旧回调 TypeError 退化）
- H3 gate 双向：cooldown_active 阻塞 / clear 放行 / pipeline `_mark_life_outcome` 回写

---

## 3. 改动文件清单（PR-B + PR-C）

| 文件 | PR | 关键行 |
|------|----|--------|
| `sylanne_alpha/life_simulation.py` | B+C | dataclass `:18-308`；helper `:310-460`；编排器 `_simulate_tick:559`；`_evaluate_share_intent` / `_do_outreach` / `mark_outreach_*`；`life_prompt_fragment:955` |
| `sylanne_alpha/llm_request_pipeline.py` | C | `_life_sim_outreach:2605`（扩字段+H3+回写）；`_mark_life_outcome:2810`；`_prepare_memory_context:1416`（消费回写） |
| `sylanne_alpha/proactive_scheduler.py` | C | `evaluate_outreach_gate:213` |
| `sylanne_alpha/agents/life_agent.py` | B | `:76` PRE 改调 `life_prompt_fragment` |
| `sylanne_alpha/memory_system.py` | B | `MemorySource:42` 常量类 |
| `sylanne_alpha/webui_server.py` | B | `handle_life_status:282` + 路由 `:1318` |
| `tests/test_life_sim_structured.py` | B | 9 测试 |
| `tests/test_life_sim_share_intent.py` | C | 11 测试 |
| `tests/test_life_sim_persistence.py` | B | 更新 roundtrip（修复 event_type 断言）+ V2 迁移测试 |

---

## 4. 实施中踩到的坑（供 review 参考）

1. **重复 `_parse_response` 定义**（B3）：我新增返回 tuple 的版本后，旧版（返回 LifeEvent）仍在 `_build_prompt` 后，Python 后定义覆盖 → orchestrator 解包失败（TypeError: cannot unpack LifeEvent）。**已修**：删旧版。
2. **`memory_system.py` 换行被吞**（B5）：一次 edit 把 `LEGACY = "legacy"` 和 `SHADOW = "shadow"` 合并到一行。**已修**：恢复 + 加 `MemorySource` 类。
3. **`_store.hosts` 经 SessionStateStore 访问**（C5）：`dispatch_blocked_reason:203` 用 `self._p._store.hosts.get(sk)`（非直接 `self._p._hosts`），`candidates = self._p._store.proactive_candidate_sessions`（非 `_proactive_candidate_sessions`）。fake plugin 必须提供 `_store` 含 `hosts` + `proactive_candidate_sessions`。**已修**：测试 fake 补 `_store`。
4. **`_countdown_callback` 遗漏收口**（上一轮 review）：两轮 review 各抓一个空 tick 副作用出口（dirty → countdown）。共同模式：**"零副作用"契约需逐个审查所有 callback 出口**。PR-C 沿用此纪律列了 tick 的全部出口。

---

## 5. 工程纪律验证（贯穿 PR-A/B/C）

- ✅ 保留 `LifeSimulator` 对外接口（`simulate_tick`/`configure`/`to_dict`/`from_dict` 不破坏）
- ✅ 新状态可迁移、可裁剪；旧档向前兼容（`from_dict` 容缺）
- ✅ provider 未配置 / enabled=false 时零副作用（**含不拨 countdown**，二审 HIGH）
- ✅ 生活模拟输出永远是素材（pending context / proactive bridge），不绕过主模型直发
- ✅ 每个 PR 带 fake-LLM 测试（88 个，不依赖真实 LLM）
- ✅ H3：两条 outreach 路径走同一 scheduler gate 口径

---

## 6. 仍未做（Phase 2 范畴，等第一批 review 通过再启动）

| ID | 内容 | 锚点 |
|----|------|------|
| H1 | `MemoryItem` 加 `confidence: float` / `privacy_level: str` + `from_dict` 迁移 + `write_summary` 扩参 | `memory_system.py:133-155, 841-849` |
| H2 | 召回链路 source-aware 排序/过滤层（**新能力**，非标注） | `memory_system.py:1241-1247, 1329` |
| M6 | `LifeReflection` Store + **全局触发点**（不寄生 per-session RETIRED） | 类比 `autonomy_scheduler._global_autonomy:147` |
| M7 | life reflection 输出通道另建（现有 ReflectionEngine 只写 gate 偏置 float） | `reflection.py:181-182` |
| M8 | `unanswered_penalty` 单一数据源（Bridge 复用 `feedback_pressure`，不另计数） | `proactive_scheduler.py:81-92` |
| L16 | `LifeConsolidationEngine`（配置开关：默认关=零 LLM，开了走 LLM） | `consolidation.py:24-145` |

Phase 3：项目/技能库（`LifeProject` / `LifeSkill`，v2 §4.5）。

---

## 7. 测试与验证命令

```powershell
python -m pytest tests/test_life_sim_persistence.py tests/test_life_sim_structured.py tests/test_life_sim_share_intent.py -v
python -m pytest tests/test_agents_gating.py tests/test_agents_infra.py tests/test_evolution_learning.py tests/test_dream_consolidation.py -q
python -c "import ast; [ast.parse(open(f, encoding='utf-8').read()) for f in ['sylanne_alpha/life_simulation.py', 'sylanne_alpha/llm_request_pipeline.py', 'sylanne_alpha/proactive_scheduler.py', 'sylanne_alpha/memory_system.py', 'sylanne_alpha/agents/life_agent.py', 'sylanne_alpha/webui_server.py']]; print('AST OK')"
```

预期：life 测试 37/37 + 回归 51/51 = 88/88，AST OK。

---

## 8. 给 reviewer 的建议关注点

1. **H3 gate 收口是否真的对称**：`_life_sim_outreach` fallback（`llm_request_pipeline.py:2635`）的 `evaluate_outreach_gate` 调用，与 `request_dispatch`（`proactive_scheduler.py:289`）的 `dispatch_blocked_reason` 是否同一口径。`evaluate_outreach_gate` 是 session_key-only 封装，`force=False, dry_run=True`。
2. **ShareIntent 评分是否合理**：`_evaluate_share_intent` + `_recompute_final`（`life_simulation.py`）。PR-C 用规则评分（零 LLM），Phase 2 可接 scheduler.feedback_pressure 做 unanswered_penalty。
3. **delivery_mode=SILENT 是否会过度压制**：score<0.25 跳过 outreach。cooldown_penalty 高时（刚 outreach 过）容易触发——这是有意的（v2 ADR-004：少而准），但需观察是否导致长期不分享。
4. **回调签名兼容**：`_do_outreach` 三参回调 + TypeError 退化两参（`life_simulation.py`）。main.py 注入 `pipe._life_sim_outreach`，新签名 `(reason, mood, intent=None)` 已就位，兼容路径是给外部回调兜底。
5. **zip release 校验**：PR-A/B/C 都改了源码，发布 zip（git 跟踪的 `astrbot_plugin_sylanne.zip`）仍是旧的，发布前需重建（见 `handoff §11`）。
