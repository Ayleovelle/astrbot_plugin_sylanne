# PR-A Review 回应

日期：2026-06-18
回应对象：`life-simulation-upgrade-pr-a-review.md`
处置人：实施方（基于 receiving-code-review 纪律逐条核验，非表演性同意）

---

## 结论

评审的 **HIGH 发现属实**，是真实 bug（实为 PR-A 的 `state_dirty_callback` 放大了一个预存基线缺陷）。已修复并补测。MED（zip）判定为 release 产物，纳入发布校验。测试缺口已补。**Gate 通过，PR-A 可合入，PR-B 可启动**。

---

## 逐条处置

### High：provider 未配置时仍会修改 life sim 状态 — ✅ 已修

**核验**：属实。
- `_simulate_tick:248` 原只查 `_llm_caller` 是否 None
- 真实集成里 `main.py:2376-2383` **始终**注入 `pipe._life_sim_llm_call`
- `_life_sim_llm_call:2591-2592` 在 `provider_id==""` 时返回 `""`
- 于是 enabled=true + provider="" → bump `last_simulation_time`/`simulation_count` → 空 event → 状态污染 → 我新增的 `state_dirty_callback` 还把污染**落盘**
- 原测试 `test_enabled_but_no_llm_caller_is_noop` 用 `llm_caller=None`，**没覆盖真实路径**，是测试缺口

**根因**：原 `_simulate_tick` 的 bump 早于 LLM 调用是**预存基线行为**（`life_simulation.py:251-253` 在 PR-A 前就在）。PR-A 新增的 `state_dirty_callback` 放大了它的危害（污染被持久化）。

**修复**（`life_simulation.py:_simulate_tick`）：
1. 顶部加 `if not self.enabled: return` 防线（契约：enabled=false 零副作用）
2. `last_simulation_time`/`simulation_count` 的 bump 移入 `if event:` 块内（空响应零 bump）
3. `state_dirty_callback` 改为 `if event and ...`（空 tick 不触发持久化）

**补测**（`tests/test_life_sim_persistence.py`）：
- `test_configured_caller_returning_empty_is_noop`：已 configure caller 返回 ""→ 计数/时间/event/dirty 全不变
- `test_disabled_simulator_with_llm_caller_is_noop`：enabled=false 即使注入 caller 也不调 LLM

**关于 hammer 风险的取舍**：bump 推迟到 event 后，provider 空且 enabled=true 时 `due` 会保持 true，每 30s 心跳触发一次 instant 空返回。这是**可接受的**：空返回无网络开销（`_life_sim_llm_call` 同步检查 provider_id 即返回），且是用户可观测的误配置信号。Phase 1 若需更精细的退避可再加 provider-ready 检测，PR-A 阶段不为零行为变化范围之外。

---

### Medium：发布 zip 与源码树不一致 — 📦 标注为 release 产物

**核验**：属实。
- zip 内含旧 `prompt_surface.py`（14002B）、旧 main.py（91675B）、旧 life_simulation.py（14208B）、旧 llm_request_pipeline.py（70231B）
- 但 `astrbot_plugin_sylanne.zip` **被 git 跟踪**（`git ls-files` 命中），`.gitignore:4` 只忽略不同名的 `Sylanne-embodiment.zip`

**处置**：采纳评审自己给的备选方案——"视为生成产物，不纳入本 PR 审查范围，发布前单独构建验证"。理由：
- zip 是打包产物，重建需走 release 工程流程（`.gitignore:78` 忽略 `scripts/plugin_zip_preflight.js`，当前仓库未跟踪任何 preflight 脚本；如存在本地 release 脚本也未入库）
- PR-A 的代码正确性独立成立（源码树 + 测试 + AST 验证）
- 已在 `handoff.md §11` 写入 release 校验清单，发布前必跑

未在 PR-A 重建 zip。若需要，可作为独立 release 工程任务。

---

### §2 测试缺口：pipeline 级 memory summary — ✅ 已补

**核验**：属实。原 `test_memory_summary_getter_is_consumed_by_build_prompt` 只测 LifeSimulator 直接注入 fake getter，未验证 `_life_sim_memory_summary()` 真实从 pipeline 取 memory_system 的路径。

**补测**（`tests/test_life_sim_persistence.py`）：
- `test_pipeline_memory_summary_extracts_recent_findings`：fake plugin + fake `_store.hosts` + fake `_memory_system_for_session()`，验证 n=3 截断、拼接格式
- `test_pipeline_memory_summary_no_hosts_returns_empty`：无活跃 host 返回空
- `test_pipeline_memory_summary_exception_returns_empty`：memory 取用异常降级为空串不阻断

---

## §4 评审环境无法跑 pytest — 已在本机复核

评审方 Python 环境问题导致无法复核 `13/13` / `51/51`。已在可用环境（WindowsApps Python 3.13 + pytest）重跑确认：
- `tests/test_life_sim_persistence.py`：**13 passed**
- 回归 `test_agents_gating.py test_agents_infra.py test_evolution_learning.py test_dream_consolidation.py`：**51 passed**
- AST：**OK**

---

## Gate

```text
PR-A: Approved（HIGH 已修 + 测试缺口已补 + zip 转为 release 校验项）
PR-B: 可启动
```
