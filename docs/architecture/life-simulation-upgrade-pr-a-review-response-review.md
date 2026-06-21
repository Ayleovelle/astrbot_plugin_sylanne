# Sylanne 生活模拟升级 PR-A Review Response 二次审查

日期：2026-06-18  
审查对象：`docs/architecture/life-simulation-upgrade-pr-a-review-response.md`  
基线：`.clean-sylanne-github/`，`metadata.yaml` 版本 `2.1.0`  
结论：**PR-A response 仍需修改。High 未完全关闭，暂不建议启动 PR-B。**

---

## 0. 总结

`life-simulation-upgrade-pr-a-review-response.md` 对上一轮 review 的主要 High 做了部分修复：

- `enabled=false` 时现在会在 `_simulate_tick()` 顶部返回。
- provider 空 / LLM 空响应时不再 bump `last_simulation_time`。
- provider 空 / LLM 空响应时不再 bump `simulation_count`。
- provider 空 / LLM 空响应时不再触发 `state_dirty_callback`。
- `tests/test_life_sim_persistence.py` 确实补了 13 个 plain assert 测试，包括空响应、disabled + caller、pipeline memory summary。

但“provider 未配置零副作用”仍不完全成立：空响应时 `_countdown_callback` 仍然会被调用。真实集成里该 callback 是 `main.py::_life_sim_adjust_countdown()`，会调用 proactive bridge 的 `adjust_countdown()`，从而改写主动发言调度。

因此 response 里的 Gate 结论：

```text
PR-A: Approved
PR-B: 可启动
```

目前不能接受。

---

## 1. Findings

### High: provider 空 / 解析失败时仍会拨动主动发言倒计时

位置：

- `sylanne_alpha/life_simulation.py:290-296`
- `main.py:2389`
- `main.py:2432`
- `sylanne_alpha/proactive_bridge.py:530-538`
- `sylanne_alpha/agents/life_agent.py:44-46`
- `tests/test_life_sim_persistence.py:56`

问题：

PR-A response 把计数、时间和落盘移动到 `if event:` 之后，这是正确的。但 `_countdown_callback` 仍在 `if event:` 外部：

```python
if self._countdown_callback is not None:
    try:
        await self._countdown_callback()
    except Exception:
        pass

if event and self._state_dirty_callback is not None:
    ...
```

空响应路径仍会触发 callback。

真实集成中，`main.py` 注入的是：

```python
countdown_callback=self._life_sim_adjust_countdown
```

而 `_life_sim_adjust_countdown()` 在桥接开启且大饼可用时会调用：

```python
await bridge.adjust_countdown(session_key)
```

`ProactiveBridge.adjust_countdown()` 会临时写入 session override，并调用：

```python
await plugin._schedule_next_chat_and_save(sid)
```

这不是只读操作，会重排主动聊天倒计时并保存调度状态。

复现：

```text
provider/LLM 返回空串：
countdown_calls = 1
simulation_count = 0
events = 0
```

解析失败同样成立：

```text
LLM 返回 invalid JSON：
countdown_calls = 1
simulation_count = 0
events = 0
```

风险：

- 仍违背 handoff §7 的工程纪律：“provider 未配置或 enabled=false 时零副作用”。
- provider 空且 `last_simulation_time` 不更新，会导致 `LifeAgent.perceive()` 的 due 判断持续为真：

```python
last = float(getattr(sim.state, "last_simulation_time", 0.0) or 0.0)
interval = sim.interval_seconds * random.uniform(0.4, 1.8)
due = enabled and (now - last) >= interval
```

- 于是每次 autonomy scan 都可能再次触发空 tick，并继续拨动 proactive countdown。
- 当前测试 `test_configured_caller_returning_empty_is_noop` 只断言 count/time/events/dirty，没有断言 countdown 不被调用。

建议：

- 将 `_countdown_callback` 也移动到 `if event:` 内部。
- 或者增加 `state_changed = event is not None`，只有状态真实演化后才执行 countdown 和 dirty save。
- 补测试：

```python
def test_configured_caller_returning_empty_does_not_adjust_countdown():
    ...
    sim.configure(llm_caller=_empty_caller, countdown_callback=_countdown_cb)
    asyncio.run(sim.simulate_tick())
    assert countdown_calls == []
```

- 同时补 invalid JSON 路径，避免解析失败时仍拨动倒计时。

---

### Low: release zip 校验清单存在，但工具链描述不准确

位置：

- `docs/architecture/life-simulation-upgrade-handoff.md:247`
- `docs/architecture/life-simulation-upgrade-handoff.md:253-260`
- `docs/architecture/life-simulation-upgrade-pr-a-review-response.md:48`
- `.gitignore:76-79`

核验：

handoff 确实新增了 §11 release 校验清单，明确 zip 是发布产物，发布前必须重建并校验。这一处处置方向可接受。

但 response 里说：

```text
仓库有 scripts/plugin_zip_preflight.js 提示
```

当前工作树里并不存在该文件；`.gitignore` 还明确忽略：

```text
scripts/plugin_zip_preflight.js
```

此外，handoff 里的 PowerShell 片段实际只检查 `sylanne_alpha/prompt_surface.py` 不存在；前面的注释列出了 `life_simulation.py`、`main.py`、`llm_request_pipeline.py` 应包含的新符号，但脚本没有实现这些检查。

风险较低，因为这是发布工程事项，不影响 PR-A 源码行为；但文档应避免让后续实施者误以为已有完整 preflight 工具。

建议：

- response 中把“仓库有脚本提示”改为“可能存在本地 release 脚本，但当前仓库未跟踪”。
- handoff §11 的校验片段补齐符号检查，或明确“当前片段只检查 prompt_surface，其他项需人工/后续脚本检查”。

---

## 2. 已核验通过的部分

### High 的主体状态污染已部分修复

手写 runner 复现：

```text
disabled + 已注入 caller：
disabled_count = 0
disabled_last = 0.0
disabled_events = 0
disabled_calls = 0

enabled + caller 返回空串：
empty_count = 0
empty_last = 0.0
empty_events = 0
dirty_fired = 0
```

说明：

- `enabled=false` 防线有效。
- 空响应不再 bump count/time。
- 空响应不再触发 dirty save。

但如上所述，空响应仍触发 countdown callback。

### 新增测试文件内容与 response 基本一致

`tests/test_life_sim_persistence.py` 当前包含 13 个 plain assert 测试：

- disabled noop。
- enabled 但无 llm caller noop。
- configured caller 返回空串 noop。
- disabled 但注入 caller noop。
- state roundtrip。
- recent 20 truncation。
- dirty callback 触发。
- dirty callback 失败隔离。
- memory summary getter 被 `_build_prompt()` 消费。
- `_pending_emotion_delta` 删除。
- pipeline memory summary 提取最近 findings。
- no hosts 返回空。
- memory 取用异常返回空。

使用 Codex bundled Python 的手写 runner 执行这 13 个测试函数，结果：

```text
count 13
failed 0
```

注意：这不是 pytest run，但足以确认这些测试函数本身在当前环境可通过。

### AST 语法检查通过

检查文件：

- `sylanne_alpha/life_simulation.py`
- `sylanne_alpha/llm_request_pipeline.py`
- `main.py`
- `tests/test_life_sim_persistence.py`

结果：

```text
OK
```

---

## 3. 未完成验证

pytest 仍未在当前环境复跑：

- 系统 `python.exe` 启动失败。
- Codex bundled Python 可运行但无 `pytest`。
- `E:\Anaconda\python.exe` 是 Python 2.7.3。
- `py -3` 指向 WindowsApps Python 3.13 但无法创建进程。

因此本次二审不能确认：

- response 声称的 `pytest tests/test_life_sim_persistence.py` 真实 `13/13 passed`。
- response 声称的回归 `51/51 passed`。

本次可确认：

- 13 个测试函数用手写 runner 可通过。
- AST OK。
- countdown side effect 漏洞可复现。

---

## 4. 建议修复清单

1. 将 `_countdown_callback` 移入 `if event:`，或用 `state_changed` 统一控制 countdown 与 dirty save。
2. 补测试：空响应不触发 countdown。
3. 补测试：invalid JSON 不触发 countdown。
4. 更新 `life-simulation-upgrade-pr-a-review-response.md` 的 Gate 结论，直到上述测试通过前不要写 `PR-A: Approved`。
5. 更新 `life-simulation-upgrade-handoff.md`：
   - PR-A review 处置记录增加 countdown side effect 修复。
   - 工程纪律中的“provider 未配置零副作用”应包括不调 countdown。
   - release zip 校验清单明确当前脚本覆盖范围。

---

## 5. Gate

当前二审结论：

```text
PR-A response: Needs changes
PR-A: Not approved yet
PR-B: Do not start yet
```

通过条件：

- provider 空 / LLM 空响应 / invalid JSON 均不 bump、不落盘、不拨动 proactive countdown。
- disabled + caller 仍保持完全 no-op。
- 新增测试覆盖 countdown no-op。
- handoff 和 review response 文档同步修正 Gate。
