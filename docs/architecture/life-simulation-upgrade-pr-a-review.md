# Sylanne 生活模拟升级 PR-A Review

日期：2026-06-18  
基线：`.clean-sylanne-github/`，`metadata.yaml` 版本 `2.1.0`  
审查对象：`docs/architecture/life-simulation-upgrade-handoff.md` 中标记为已完成的 PR-A  
审查结论：**不建议直接进入 PR-B。PR-A 需要先修复 1 个 High 问题，并处理发布包一致性。**

---

## 0. 结论

PR-A 的方向基本正确：删除顶层死代码、修正 `LifeSimulator` docstring、补 `memory_summary_getter` 接线、删除 `_pending_emotion_delta`、新增 tick 后节流落盘钩子，这些都符合 handoff 的 Phase 0 目标。

但当前实现还没有真正满足 handoff 里的关键契约：

> provider 未配置或 `enabled=false` 时零副作用。

真实集成路径里，`main.py` 会始终给 `LifeSimulator` 注入 `_life_sim_llm_call`。因此即使 life-sim provider 为空，`_simulate_tick()` 仍会先 bump `last_simulation_time` / `simulation_count`，随后才发现 LLM 返回空串。这会导致“没有生成生活事件，但状态已变化并可能落盘”。

这不是文案问题，是状态污染问题。应先修再继续 PR-B。

---

## 1. Findings

### High: provider 未配置时仍会修改 life sim 状态

位置：

- `sylanne_alpha/life_simulation.py:246`
- `sylanne_alpha/life_simulation.py:251-253`
- `main.py:2382-2390`
- `sylanne_alpha/llm_request_pipeline.py:2585-2603`

问题：

`LifeSimulator._simulate_tick()` 当前只检查 `_llm_caller` 是否存在：

```python
if not self._llm_caller:
    return

now = time.time()
self.state.last_simulation_time = now
self.state.simulation_count += 1

prompt = self._build_prompt(now)
response = await self._llm_caller(prompt)
event = self._parse_response(response, now)
```

但在真实插件集成中，`main.py` 总是注入：

```python
llm_caller=pipe._life_sim_llm_call
```

而 `_life_sim_llm_call()` 在 provider id 为空时返回 `""`：

```python
provider_id = str(p._config.get("sylanne_alpha_life_simulation_provider_id") or "")
if not provider_id:
    return ""
```

所以真实路径是：

1. provider 未配置。
2. `_llm_caller` 仍然存在。
3. `_simulate_tick()` 先写 `last_simulation_time` 和 `simulation_count`。
4. `_life_sim_llm_call()` 返回空串。
5. `_parse_response()` 返回 `None`。
6. 没有 event，但状态已被污染。
7. tick 末尾还会触发 `state_dirty_callback`，可能把这个空 tick 落盘。

复现结果：

```text
simulation_count = 1
last_simulation_time > 0 = True
events = 0
```

风险：

- 违背 handoff §7 工程纪律：“provider 未配置或 enabled=false 时零副作用”。
- 会把“未配置 provider 的空运行”计入 life sim 演化次数。
- 会更新 `last_simulation_time`，影响后续 due 判断。
- 会触发节流保存，导致空 tick 状态持久化。
- 现有测试没有覆盖真实集成路径，因为它只测了“不传 `llm_caller`”。

建议：

- 在 `_simulate_tick()` 顶部显式检查：

```python
if not self.enabled:
    return
if not self._llm_caller:
    return
```

- 将 `last_simulation_time` / `simulation_count` 的 bump 移到确认 LLM 有有效响应之后，至少要在空响应时不 bump。
- 补测试：已 configure `llm_caller`，但 caller 返回 `""` 时，`simulation_count`、`last_simulation_time`、`events` 都不变。
- 如果要区分“provider 未配置”和“provider 调用失败”，可以让 `_life_sim_llm_call()` 返回结构化结果；但 PR-A 阶段用空响应不 bump 已足够。

---

### Medium: 发布 zip 与源码树不一致

位置：

- `astrbot_plugin_sylanne.zip`
- zip 内 entry：`sylanne_alpha/prompt_surface.py`
- zip 内 entry：`main.py`
- zip 内 entry：`sylanne_alpha/life_simulation.py`
- zip 内 entry：`sylanne_alpha/llm_request_pipeline.py`

问题：

源码树已经删除顶层 `sylanne_alpha/prompt_surface.py`，但发布包 `astrbot_plugin_sylanne.zip` 仍包含该文件，并且 zip 内核心文件尺寸明显对应旧版本：

```text
sylanne_alpha/prompt_surface.py    present    14002
main.py                            present    91675
sylanne_alpha/life_simulation.py   present    14208
sylanne_alpha/llm_request_pipeline.py present 70231
```

风险：

- 如果 zip 是实际安装/发布物，PR-A 的源码改动不会进入用户安装包。
- 已删除的顶层死代码会被重新带回。
- review 和测试针对源码树通过，也不能证明发布包行为正确。

建议：

- PR-A 合入前重建 `astrbot_plugin_sylanne.zip`。
- 或者明确将 zip 视为生成产物，不纳入本 PR 审查范围，并在发布前单独构建验证。
- 发布验证至少检查：
  - zip 内不包含 `sylanne_alpha/prompt_surface.py`。
  - zip 内 `life_simulation.py` 包含 `state_dirty_callback`。
  - zip 内 `main.py` 包含 `_life_sim_throttled_save`。
  - zip 内 `llm_request_pipeline.py` 包含 `_life_sim_memory_summary`。

---

## 2. 测试缺口

### `_life_sim_memory_summary()` 真实接线未被覆盖

位置：

- `sylanne_alpha/llm_request_pipeline.py:2795`
- `main.py:2388`
- `tests/test_life_sim_persistence.py:152`

现有测试只验证 `LifeSimulator` 直接注入 fake `memory_summary_getter` 后，`_build_prompt()` 会消费摘要。

这能证明 `LifeSimulator` 支持该回调，但不能证明：

- `main.py` 的 configure 接线在真实插件对象上可用。
- `_life_sim_memory_summary()` 能正确从最近活跃 host 取 memory system。
- `mem_sys.get_recent_findings(n=3)` 的返回结构与当前拼接逻辑匹配。
- 摘要能经 pipeline 进入 life sim prompt。

建议补一个 pipeline 级 fake 测试：

1. 构造 fake plugin。
2. 提供 fake `_store.hosts`。
3. 提供 fake `_memory_system_for_session()`。
4. fake memory system 返回 `get_recent_findings(n=3)`。
5. 调用 `_life_sim_memory_summary()`，断言输出包含预期摘要。
6. 再把它注入 `LifeSimulator`，断言 `_build_prompt()` 包含该摘要。

---

## 3. 已验证事项

### 删除顶层 `prompt_surface.py` 的源码引用风险较低

检查结果：

```text
Select-String prompt_surface
```

源码树中只发现 `sylanne_alpha/public_api.py` 注释残留引用，未发现活代码 import 顶层 `sylanne_alpha.prompt_surface`。

注意：

- canonical 文件仍然是 `sylanne_alpha/_engine/sylanne_core/compute/prompt_surface.py`。
- 删除源码树顶层文件本身是合理的。
- 但发布 zip 仍带旧文件，见 Medium finding。

### AST 语法检查通过

命令：

```powershell
python -c "import ast; [ast.parse(open(f, encoding='utf-8').read()) for f in ['sylanne_alpha/life_simulation.py', 'sylanne_alpha/llm_request_pipeline.py', 'main.py']]; print('OK')"
```

结果：

```text
OK
```

---

## 4. 未能完成的验证

pytest 未在当前环境完整跑通，原因是环境问题，不是断言失败：

- `python.exe` 启动失败：`指定的登录会话不存在。可能已被终止。`
- Codex bundled Python 可运行，但未安装 `pytest`。
- `E:\Anaconda\python.exe` 是 Python 2.7.3，无法运行当前 Python 3 代码。
- `py -3` 指向 WindowsApps Python 3.13，但无法创建进程。

因此本 review 不能声称：

- `tests/test_life_sim_persistence.py` 已通过。
- handoff 中的 `51/51` 回归在本机复核通过。

已能确认：

- AST 语法 OK。
- provider 空响应会污染状态的逻辑漏洞可复现。
- zip 与源码树不一致可复现。

---

## 5. 建议处理顺序

1. 修 High：`_simulate_tick()` 增加 `enabled` 防线，并保证空响应不 bump 状态。
2. 补测试：覆盖“已 configure 但 provider 空/返回空串”的零副作用路径。
3. 补 pipeline 级 memory summary 接线测试。
4. 重建或排除 `astrbot_plugin_sylanne.zip`。
5. 用可用 Python 3 + pytest 环境重跑：

```powershell
python -m pytest tests/test_life_sim_persistence.py -v
python -m pytest tests/test_agents_gating.py tests/test_agents_infra.py tests/test_evolution_learning.py tests/test_dream_consolidation.py -q
python -c "import ast; [ast.parse(open(f, encoding='utf-8').read()) for f in ['sylanne_alpha/life_simulation.py', 'sylanne_alpha/llm_request_pipeline.py', 'main.py']]; print('OK')"
```

---

## 6. Review Gate

当前 gate 结论：

```text
PR-A: Needs changes
PR-B: Do not start yet
```

通过条件：

- provider 空 / disabled 均零副作用。
- fake LLM 测试覆盖真实 configure 路径。
- 发布 zip 与源码一致，或明确不作为本 PR 产物。
- pytest 与 AST 检查在 Python 3 环境通过。
