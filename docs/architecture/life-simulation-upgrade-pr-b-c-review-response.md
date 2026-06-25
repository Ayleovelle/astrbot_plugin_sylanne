# PR-B / PR-C Review Response

日期：2026-06-18
回应对象：`life-simulation-upgrade-pr-b-c-review.md`
处置：receiving-code-review 纪律逐条核验（非表演性同意）
结论：**5 个 finding 全部属实，已修复并通过复现测试。Gate 提议改 Approved。**

---

## 0. 核验总览

review 的 2 HIGH + 3 MED + 1 LOW 我全部接受。关键的是：reviewer 指出"PR-A 的零副作用契约没有扩展到 PR-B 新状态"和"PR-C 的 pending 过期契约没覆盖用户主动消费路径"——这两条都是**契约扩展没跟上**的状态机边界问题，不是小瑕疵。这是我前几轮没看到的盲区。

修复后全量测试 **95/95 通过**（原 88 + review §3 的 7 个复现测试）。AST 全 OK。

---

## 1. 逐条处置

### HIGH 1：world mutation 打穿零副作用 ✅ 已修

**核验**：属实。`_load_world_context` 在 LLM 调用**之前**直接写 `state.world.local_date/phase/energy/focus`（`life_simulation.py` 原 `:677-695`），空 tick 时 `parsed is None` 分支返回但 world 已被改。我的 PR-A 测试只断言 `simulation_count`/`last_simulation_time`/`events`/dirty/countdown，没 snapshot `state.world`，所以漏了——这正是"零副作用契约需覆盖所有状态出口"的纪律没贯彻到位。

**修复**（`life_simulation.py:_load_world_context`）：
- 改为**纯计算**：候选 `local_date`/`phase`/`energy`/`focus` 进 ctx dict（`_cand_*` 键），不就地写 `state.world`
- commit 推迟到 `_record_event`（仅在确认有效事件后）：`state.world.local_date/phase/energy/focus = ctx["_cand_*"]`

**复现测试**（`tests/test_life_sim_review_repro.py`）：
- `test_case1_empty_response_world_unchanged`：空串 → deepcopy snapshot 对比 world 全字段不变
- `test_case2_invalid_json_world_unchanged`：invalid JSON → 同上
- `test_case_world_mutates_on_successful_event`：正向回归（有效事件时 world 被 commit）

### HIGH 2：pending 过期只在 fallback 查 ✅ 已修

**核验**：属实。`_prepare_memory_context`（`llm_request_pipeline.py:1416`）pop + consumed 时没查 `expires_at`。如果 pending 已过期但 fallback 尚未执行/被取消，用户下次发消息时过期素材会被注入 prompt 并误标 `consumed_at`（应 `dropped_at`）。

**修复**（`_prepare_memory_context`）：消费前查 `expires_at`：
- `time.time() > expires_at` → 标 dropped，不注入 fragment，不写 memory
- 否则正常 consumed

**复现测试**：
- `test_case3_expired_pending_consumed_as_dropped`：构造 `expires_at < now` → 断言 `outreach_fragment == ""`、`dropped_at > 0`、`consumed_at == 0`
- `test_case3b_fresh_pending_consumed_normally`：正向回归（未过期正常 consumed）

两条过期路径（fallback / consume）语义现在一致。

### MED 3：裸 TypeError 吞错 ✅ 已修

**核验**：属实。原 `_do_outreach` 用 `except TypeError: 两参重试`，会把三参回调**内部**抛的 TypeError 误判为签名不兼容 → 吞 bug + 二次调用 + 误标 shared。

**修复**（`life_simulation.py:_do_outreach` + 模块级 `_callback_accepts_intent`）：
- 改用 `inspect.signature` 判断参数数（带缓存 `_CALLBACK_ARITY_CACHE`），`*args/**kwargs` 视为接受任意
- 三参回调内部抛 TypeError 现在按真实异常处理，不退化重试
- 外层 `except Exception: pass` 仍兜底（不阻断 tick），但**不会推进 outreach_count/last_outreach_time**（这些在 try 块成功路径里，异常时不会执行）

**复现测试**：
- `test_case4_internal_typeerror_not_swallowed`：三参回调内部抛 TypeError → 断言只被调用一次、outreach_count/last_outreach_time 未推进
- `test_case4b_two_arg_callback_still_supported`：两参回调仍被正确适配

### MED 4：两份 handoff 口径冲突 ✅ 已修

**核验**：属实。PR-B/C handoff 写"等 review"，主 handoff §0/§12 写"Approved"。

**修复**：
- PR-B/C handoff §6 状态改为"review findings 已全部修复并通过复现测试"
- 主 handoff §12 Gate 明确 Phase 2 启动门槛："PR-B/C review findings 全部 closed"（本 response 后满足）

### MED 5：zip preflight 没扩 B/C 符号 ✅ 已修

**核验**：属实。主 handoff §11 只覆盖 PR-A 符号。

**修复**：扩到 7 类符号（PR-A/B/C 全覆盖）：
- `_state_dirty_callback` / `if not self.enabled`（PR-A）
- `ShareIntent` / `DeliveryMode` / `life_prompt_fragment` / `mark_outreach_{dispatched,consumed,dropped}` / `_callback_accepts_intent`（PR-B/C）
- `_life_sim_memory_summary` / `evaluate_outreach_gate`（PR-A3/C2）
- `class MemorySource` / `/api/life/status`（PR-B5/B6）

### LOW 6：PR-B/C 范围边界串味 ✅ 已修（文档措辞）

**核验**：属实。我把 `queued_at` 等字段既列在 PR-B V2 字段，又在 PR-C C4 声明四时点语义，边界不干净。

**修复**：PR-B/C handoff §B1 改为"PR-B = schema scaffolding（字段可迁移/可持久化）；四时点语义/启用/pending 判定/mark helper 归 PR-C（C4）"。

---

## 2. 反思（review §4 架构判断的回应）

reviewer 的架构判断精准——"契约扩展没跟上"是这两轮 review 的共同主题：
- PR-A review：零副作用契约从"几个旧字段"扩展到"所有 callback 出口"（dirty → countdown）
- PR-B/C review：同一契约需继续扩展到"PR-B 新增的 world 状态"
- PR-C 的 `expires_at` 契约从"fallback 路径"扩展到"用户主动消费路径"

规律：**每加一类新状态/新出口，零副作用/时效契约都要同步审计一遍**。Phase 2 加 `confidence`/`privacy`/召回过滤时，我会在 response 前主动列出"这次新增了哪些状态出口/哪些消费路径"，逐个验证契约覆盖，避免再被抓出同类问题。

---

## 3. 改动清单（本轮修复）

| 文件 | 修复 |
|------|------|
| `sylanne_alpha/life_simulation.py` | HIGH1：`_load_world_context` 改纯计算 + `_record_event` commit 候选；MED3：`_do_outreach` 用 `_callback_accepts_intent` |
| `sylanne_alpha/llm_request_pipeline.py` | HIGH2：`_prepare_memory_context` 消费前查 `expires_at` |
| `tests/test_life_sim_review_repro.py` | 新增 7 个复现测试（review §3 case1-4 + 正向回归） |
| `tests/test_life_sim_structured.py` | 更新 `test_rhythm_hint_injected_for_low_energy_phase`（world 不再就地改，断言候选值） |
| `docs/architecture/life-simulation-upgrade-pr-b-c-handoff.md` | MED4/LOW6 状态 + 边界措辞 |
| `docs/architecture/life-simulation-upgrade-handoff.md` | MED4/5 Gate + zip preflight 扩符号 |

---

## 4. 验证

```powershell
python -m pytest tests/test_life_sim_persistence.py tests/test_life_sim_structured.py tests/test_life_sim_share_intent.py tests/test_life_sim_review_repro.py tests/test_agents_gating.py tests/test_agents_infra.py tests/test_evolution_learning.py tests/test_dream_consolidation.py -q
```
结果：**95 passed**（17+9+11+7+51）。AST 全 OK。

---

## 5. Gate 提议

```text
PR-B/C review findings: 全部 closed
PR-B: Approved（修复后）
PR-C: Approved（修复后）
Phase 2 启动门槛已满足（review findings 全部 closed）
```
