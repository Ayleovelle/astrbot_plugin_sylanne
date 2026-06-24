# Sylanne 生活模拟升级 PR-B / PR-C 架构 Review

日期：2026-06-18  
对象：`docs/architecture/life-simulation-upgrade-pr-b-c-handoff.md` 及其对应实现改动  
结论：**Changes Requested**

本轮按架构审查口径处理：不替编写侧完成修复，不把本端验证作为放行依据。以下问题需要编写侧自行复现、补测试、修复后再回传 response 文档。

---

## 1. Findings

### HIGH：PR-A 的“空 tick 零副作用”契约被 PR-B world mutation 打穿

位置：
- `sylanne_alpha/life_simulation.py:647-658`
- `sylanne_alpha/life_simulation.py:665-701`
- `tests/test_life_sim_persistence.py:55-111`
- `docs/architecture/life-simulation-upgrade-pr-b-c-handoff.md:34-38`
- `docs/architecture/life-simulation-upgrade-pr-b-c-handoff.md:130`

PR-A 二轮 review 已经把契约收紧为：provider 未配置、provider 返回空串、LLM 返回不可解析内容时，整个 tick 应当是零副作用，至少不得 bump、不得产生 event、不得 dirty save、不得 countdown。

PR-B 把 `_simulate_tick` 改成：

```text
enabled/caller guard -> now -> _load_world_context -> _build_prompt -> LLM -> _parse_response
```

问题在于 `_load_world_context()` 在 LLM 调用与解析之前执行，并会直接修改：
- `state.world.local_date`
- `state.world.phase`
- `state.world.energy`
- `state.world.focus`

当 LLM 返回空串或 invalid JSON 时，代码在 `parsed is None` 分支返回，但 world 已经被改过。这意味着 PR-A 的“空 tick 零副作用”只覆盖了旧状态字段和 callback，没有覆盖 PR-B 新增的 world 状态出口。

现有测试 `test_configured_caller_returning_empty_is_noop` / `test_configured_caller_invalid_json_is_noop` 只断言了 `simulation_count`、`last_simulation_time`、`events`、dirty/countdown，没有保存并比较 `world` 快照，因此没有抓住这个回归。

要求编写侧：
1. 增加复现测试：空串与 invalid JSON 两条路径都必须断言 `state.world` 完全不变。
2. 修复实现：要么把 `_load_world_context` 改成纯计算、不就地写 state；要么先生成 candidate world，只有 `_parse_response` 成功后再 commit 到 `state.world`。
3. 在 response 文档中明确说明 PR-A 零副作用契约已扩展到 PR-B 新增字段。

---

### HIGH：pending outreach 过期只在 fallback 检查，用户主动触发时会消费过期 life context

位置：
- `sylanne_alpha/llm_request_pipeline.py:1414-1425`
- `sylanne_alpha/llm_request_pipeline.py:2647-2658`
- `sylanne_alpha/llm_request_pipeline.py:2664-2676`
- `docs/architecture/life-simulation-upgrade-pr-b-c-handoff.md:75-81`

PR-C handoff 宣称 pending context 有 `expires_at`，并且“过期丢弃”。当前实现只在 5 分钟 fallback 任务里检查过期：

```text
fallback sleep 300s -> still pending -> if now > expires_at -> dropped
```

但是 `_prepare_memory_context()` 在用户下一次发起 LLM 请求时，会直接：

```text
pending_outreach_context.pop(session_key)
_mark_life_outcome(event_id, "consumed")
注入 [life_event_context]
```

这里没有检查 `expires_at`。所以如果 pending 已经过期，但 fallback 尚未执行、被延后、被取消、或 session 在过期后先由用户请求消费，就会把过期的 life event 注入主 prompt，并错误标记为 `consumed_at`。

这会造成两个后果：
- 已过期素材仍进入对话，违背 PR-C 的分享时效边界。
- 四时点状态错误：本应 `dropped_at`，却被标成 `consumed_at`。

要求编写侧：
1. 增加复现测试：构造 `pending_outreach_context` 中 `expires_at < now` 的记录，调用 `_prepare_memory_context()`，预期不注入 outreach fragment，并回写 `dropped_at`。
2. 修复实现：在 `_prepare_memory_context()` pop/消费 pending 前后检查 `expires_at`；过期则 drop，不写 memory，不注入 prompt，不标 consumed。
3. 明确 fallback 与 prompt-consumption 两条路径的过期语义一致。

---

### MEDIUM：`_do_outreach` 用裸 `TypeError` 判断回调签名，会吞掉三参回调内部错误并二次调用

位置：
- `sylanne_alpha/life_simulation.py:1064-1096`
- `tests/test_life_sim_share_intent.py:153-170`

当前兼容逻辑是：

```python
try:
    await cb(reason, event.mood, intent_dict)
except TypeError:
    await cb(reason, event.mood)
```

这只能证明“两参旧回调”能兼容，但它也会把三参回调内部抛出的 `TypeError` 当成“签名不兼容”。结果是：
- 真实 bug 被吞掉。
- 回调可能被二次调用。
- 外层 `except Exception: pass` 进一步让问题静默。

要求编写侧：
1. 改为基于 `inspect.signature` 或显式适配层判断参数数量。
2. 如果三参回调内部抛出 `TypeError`，不得退化二参重试，应按真实异常处理。
3. 增加测试：三参回调内部抛 `TypeError` 时，不应触发二参重试，不应把事件误标为已 outreach。

---

### MEDIUM：PR-B/PR-C handoff 与主 handoff 状态口径冲突

位置：
- `docs/architecture/life-simulation-upgrade-pr-b-c-handoff.md:6`
- `docs/architecture/life-simulation-upgrade-pr-b-c-handoff.md:137`
- `docs/architecture/life-simulation-upgrade-handoff.md:293-300`

PR-B/PR-C handoff 写的是“等 review”“Phase 2 等第一批 review 通过再启动”。但主 handoff 后续又写了 PR-B Approved、PR-C Approved、Phase 2 可启动。

这会误导后续接手人：到底当前是待审、已放行，还是附条件放行？架构文档必须保持单一事实源。

要求编写侧：
1. 在 response 后同步更新主 handoff 与 PR-B/C handoff 状态。
2. 如果本 review 的 HIGH 未修，则不得标 Approved。
3. Phase 2 启动条件应写成明确门槛：PR-B/C review findings 全部 closed。

---

### MEDIUM：zip release preflight 仍停留在 PR-A 范围，未覆盖 PR-B/PR-C 新符号

位置：
- `docs/architecture/life-simulation-upgrade-pr-b-c-handoff.md:170`
- `docs/architecture/life-simulation-upgrade-handoff.md:262-289`
- `astrbot_plugin_sylanne.zip`

PR-B/C handoff 只说 zip 仍旧、发布前需重建，但现有主 handoff 的 zip preflight 只覆盖 PR-A 符号。PR-B/PR-C 新增了结构化 life sim 与 ShareIntent 关键符号，release 检查必须随之扩展。

要求编写侧补充 zip preflight，至少覆盖：
- `ShareIntent`
- `DeliveryMode`
- `life_prompt_fragment`
- `evaluate_outreach_gate`
- `mark_outreach_dispatched`
- `mark_outreach_consumed`
- `mark_outreach_dropped`
- `pending_share_events`
- `/api/life/status`
- `MemorySource`

---

### LOW：PR-B / PR-C 范围边界写法有串味

位置：
- `docs/architecture/life-simulation-upgrade-pr-b-c-handoff.md:25`
- `docs/architecture/life-simulation-upgrade-pr-b-c-handoff.md:38`
- `docs/architecture/life-simulation-upgrade-pr-b-c-handoff.md:86-91`

PR-B 区块把 `queued_at/dispatched_at/consumed_at/dropped_at/share_intent_id` 写入 V2 字段完成项，并说明 `_record_event` 填 `queued_at`；PR-C 又声明四时点是 C4/M11 范围。

这不是直接实现错误，但边界不干净。建议改成：
- PR-B：schema scaffolding，仅保证字段可迁移、可持久化。
- PR-C：启用四时点语义、pending 判定、mark helper 与 pipeline 回写。

---

## 2. 放行条件

PR-B/PR-C 不建议进入 Approved，除非编写侧完成：

1. 修复空/无效 LLM 响应时 world mutation 的副作用。
2. 修复 pending context 在 `_prepare_memory_context` 路径的过期消费问题。
3. 改掉 `_do_outreach` 的裸 `TypeError` 签名兼容策略。
4. 同步主 handoff 与 PR-B/C handoff 状态。
5. 扩展 zip release preflight 到 PR-B/C 新符号。

---

## 3. 给编写侧的复现指令

编写侧自行补充以下最小复现：

```text
case 1:
enabled=true, llm_caller returns ""
before = deepcopy(sim.state.world)
await sim.simulate_tick()
assert sim.state.world == before

case 2:
enabled=true, llm_caller returns invalid JSON
before = deepcopy(sim.state.world)
await sim.simulate_tick()
assert sim.state.world == before

case 3:
pending_outreach_context contains expires_at < now
call _prepare_memory_context(session_key)
assert outreach_fragment == ""
assert event.dropped_at > 0
assert event.consumed_at == 0

case 4:
three-arg outreach callback raises TypeError internally
await simulate_tick()
assert callback was not retried as two-arg fallback
assert event.shared/last_outreach_time/outreach_count are not falsely advanced
```

---

## 4. 架构判断

PR-B/PR-C 的方向是对的：结构化 world、ShareIntent、双路径 scheduler gate 都是在补原提案的核心短板。但当前实现存在两个“契约扩展没跟上”的问题：

- PR-A 的零副作用契约没有扩展到 PR-B 新状态。
- PR-C 的 pending 过期契约没有覆盖用户主动消费路径。

这类问题不属于小文档瑕疵，而是状态机边界问题。修完上述 findings 后，再考虑 Phase 2；在此之前不建议把主 handoff 标成 Approved。
