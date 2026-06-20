# PR-A Review Response 二次审查回应

日期：2026-06-18
回应对象：`life-simulation-upgrade-pr-a-review-response-review.md`（二审）
处置人：实施方（receiving-code-review 纪律逐条核验）

---

## 结论

二审的 HIGH 发现**完全属实**，是上一轮修复的遗漏。已修并补测。**Gate 通过**。

---

## 逐条处置

### High：provider 空 / 解析失败时仍拨动主动发言倒计时 — ✅ 已修

**核验**：属实，是我上一轮修复的遗漏。
- `_simulate_tick` 的 `_countdown_callback`（`life_simulation.py:290-296` 原位置）在 `if event:` 外部
- 真实集成 `main.py:2389` 注入 `countdown_callback=self._life_sim_adjust_countdown`
- `_life_sim_adjust_countdown`（`main.py:~2432`）在桥接开启时调 `bridge.adjust_countdown(session_key)`
- `proactive_bridge.py:530-538` 的 `adjust_countdown` 有**真实副作用**：`set_override` 写大饼 session override + `_schedule_next_chat_and_save` 重排调度并保存

复现确认：provider 空 / invalid JSON → `countdown_calls=1, simulation_count=0, events=0`。空 tick 仍在改写主动发言调度。

**根因**：上一轮我把 `state_dirty_callback` 移入 `if event:`，但遗漏了 `_countdown_callback`——它原本（baseline）就在 `if event:` 外，注释写"即使没 outreach，内在节律变化也应影响下一次主动发言时机"。但空 tick 没有"内在节律变化"（没 event → 没 body 演化），所以注释意图本就应限于有 event 的路径。我上一轮没把它一起收口，是疏漏。

**修复**（`life_simulation.py:_simulate_tick`）：
- `_countdown_callback` 与 `_state_dirty_callback` **一并移入 `if event:` 块内**（在 `_do_outreach` 之后）
- 两个 callback 统一由 `if event:` 门控，空 tick 两者都不触发
- 顺序保持 countdown → dirty（先作用于变化，再持久化）

**补测**（`tests/test_life_sim_persistence.py`）：
- 强化 `test_configured_caller_returning_empty_is_noop`：加 `countdown_callback` 断言空 tick 不被调用
- 新增 `test_configured_caller_invalid_json_is_noop`：LLM 返回非 JSON → None event → 不 bump/event/dirty/countdown
- 新增 `test_countdown_fires_on_successful_event`：正向路径（有效 event）countdown 与 dirty 都触发（门控正确性回归）

---

### Low：release zip 校验清单工具链描述不准确 — ✅ 已修

**核验**：属实。
- `Test-Path scripts/plugin_zip_preflight.js` 返回 False
- `.gitignore:78` 明确忽略 `scripts/plugin_zip_preflight.js`（即未跟踪）

**处置**：
- response doc 改为"如存在本地 release 脚本也未入库，当前仓库未跟踪任何 preflight 脚本"
- handoff §11 的 PowerShell 脚本补齐了全部 PR-A 符号检查（原只查 prompt_surface），并标注"仅跑片段 1 不充分"

---

## 测试与验证

二审环境无法跑 pytest，已在可用环境（WindowsApps Python 3.13 + pytest）复核：
- `tests/test_life_sim_persistence.py`：**15 passed**（原 13 + 新增 invalid JSON + 成功路径 countdown 回归）
- 回归 `test_agents_gating.py test_agents_infra.py test_evolution_learning.py test_dream_consolidation.py`：**51 passed**
- AST：**OK**

空 tick 现在的三条出口（provider 空 / LLM 空响应 / invalid JSON）均验证为零副作用：不 bump 计数/时间、不产 event、不触发 dirty save、不拨 countdown。

---

## Gate

```text
PR-A: Approved（二审 HIGH 已修 + 测试覆盖 + doc 不准确已更正）
PR-B: 可启动
```

---

## 反思

两轮 review 各抓到一个我遗漏的副作用出口（dirty save → countdown）。共同模式：**契约"零副作用"要求逐个审查所有 callback 出口，而非只挑显而易见的那个**。后续 PR（尤其 PR-C 的 ShareIntent 双路径收口）我会沿用此纪律：列出 tick 的全部副作用出口（bump / event / countdown / dirty / outreach / body delta），逐个验证空 tick 时不触发。
