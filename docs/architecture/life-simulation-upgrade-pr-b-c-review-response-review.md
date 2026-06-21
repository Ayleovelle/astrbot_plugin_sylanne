# PR-B / PR-C Review Response 二审

日期：2026-06-18  
对象：`docs/architecture/life-simulation-upgrade-pr-b-c-review-response.md`  
结论：**Changes Requested（小范围）**

本轮只做架构审查与静态核对，不替编写侧跑测试。总体判断：两个 HIGH 的实现方向已经对上，`world` mutation 与 pending 过期消费路径基本闭合；但 response 仍有两个未完全关单点，不能直接把 Gate 改成 Approved。

---

## 1. Findings

### MEDIUM：`TypeError` 处置仍然静默吞异常，response 对“按真实异常处理”的表述过度

位置：
- `docs/architecture/life-simulation-upgrade-pr-b-c-review-response.md:47-57`
- `sylanne_alpha/life_simulation.py:1123-1157`
- `tests/test_life_sim_review_repro.py:181-209`

编写侧已修掉原来最危险的部分：三参回调内部抛 `TypeError` 时，不会再退化成两参重试，也不会推进 `outreach_count` / `last_outreach_time`。这点认可。

但 response 写的是“三参回调内部抛 TypeError 现在按真实异常处理”，测试名也叫 `test_case4_internal_typeerror_not_swallowed`。实际实现仍然是：

```python
try:
    ...
    await cb(reason, event.mood, intent_dict)
    ...
except Exception:
    pass
```

也就是说，内部 `TypeError` 仍被 `_do_outreach` 静默吞掉。它没有被重试，也没有污染 outreach 状态，但并没有“按真实异常处理”，也不是“不吞”。这会让真实回调 bug 在运行期不可观测，只能靠状态没推进间接推断。

要求编写侧二选一：
1. 如果架构允许 outreach callback 失败不阻断 tick：保留兜底，但至少记录 `logger.exception` / `logger.warning`，并把 response 与测试名改成“不退化重试、不推进状态”，不要宣称“不吞”。
2. 如果 review 原意是内部异常必须真实暴露：则不能 `except Exception: pass`，需要向上抛出或进入明确的错误通道。

当前建议采用方案 1：outreach 是旁路副作用，不应阻断 tick，但必须可观测。

---

### MEDIUM：zip preflight 仍漏掉 `pending_share_events`

位置：
- `docs/architecture/life-simulation-upgrade-pr-b-c-review-response.md:68-76`
- `docs/architecture/life-simulation-upgrade-handoff.md:273-304`
- `docs/architecture/life-simulation-upgrade-pr-b-c-review.md:110-120`

上一轮 review 明确要求 PR-B/C zip preflight 至少覆盖：

```text
ShareIntent
DeliveryMode
life_prompt_fragment
evaluate_outreach_gate
mark_outreach_dispatched
mark_outreach_consumed
mark_outreach_dropped
pending_share_events
/api/life/status
MemorySource
```

response 与主 handoff 已补了大部分符号，但漏了 `pending_share_events`。这是 PR-C 四时点语义的核心读口，必须纳入 release preflight，否则 zip 可能包含旧的 pending 判定逻辑而不被发布检查发现。

要求编写侧：
1. 在 `docs/architecture/life-simulation-upgrade-handoff.md` §11 zip preflight 中加入：

```powershell
$ls -match "pending_share_events"      # PR-C4
```

2. 在 `life-simulation-upgrade-pr-b-c-review-response.md` 的 MED 5 修复清单中补上 `pending_share_events`。

---

### LOW：pending 过期复现测试没有直接调用 `_prepare_memory_context`

位置：
- `tests/test_life_sim_review_repro.py:81-135`
- `tests/test_life_sim_review_repro.py:138-175`
- `sylanne_alpha/llm_request_pipeline.py:1383-1450`

实现本身已经在 `_prepare_memory_context` 的真实路径加入了 `expires_at` 检查，这点静态核对通过。

但 response 宣称 `test_case3_expired_pending_consumed_as_dropped` 复现了 `_prepare_memory_context` 消费路径；实际测试里是“直接复刻该段逻辑”，没有调用 `_prepare_memory_context()`。这类测试会跟实现代码一起复制粘贴地变绿，无法防止未来真实函数被改坏。

这不阻塞本轮架构方向，但建议编写侧补一个轻量 fake plugin，直接调用：

```python
await pipe._prepare_memory_context("s1", "msg", gap_seconds=9999, realtime_enabled=True)
```

并断言返回的 `outreach_fragment == ""`、事件 `dropped_at > 0`、`consumed_at == 0`。

---

## 2. 已认可的关闭项

以下项本轮静态核对后可以认为已关闭：

1. **HIGH1 world mutation**：`_load_world_context` 已改为候选值纯计算，`_record_event` 只在有效事件后 commit 到 `state.world`。
2. **HIGH2 pending 过期消费**：`_prepare_memory_context` 已在消费前检查 `expires_at`，过期时 drop，不注入 prompt，不写 memory，不标 consumed。
3. **MED4 handoff 状态冲突**：主 handoff 与 PR-B/C handoff 已同步为 review findings closed / Gate Approved 的叙述。是否最终 Approved 仍取决于本二审 findings 关闭。
4. **LOW6 PR-B/C 范围边界**：PR-B schema scaffolding 与 PR-C 四时点语义的边界已重新表述。

---

## 3. Gate 判断

当前不建议直接标最终 Approved。建议 Gate 改为：

```text
PR-B/C review response: Changes Requested（剩余 2 MED + 1 LOW）
Phase 2: 暂缓，等二审 findings closed 后再启动
```

关闭条件：

1. `_do_outreach` 回调异常至少可观测，或文档/测试改成准确表述。
2. zip preflight 补 `pending_share_events`。
3. pending 过期测试最好直打 `_prepare_memory_context`，至少不要在 response 中声称已经覆盖真实函数路径。
