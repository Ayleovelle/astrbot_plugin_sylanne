# PR-B / PR-C Review Response 二审回应

日期：2026-06-18
回应对象：`life-simulation-upgrade-pr-b-c-review-response-review.md`
处置：receiving-code-review 纪律逐条核验
结论：**3 个 finding 全属实（2 MED + 1 LOW），已全部修复并验证。Gate 提议改最终 Approved。**

---

## 0. 核验

二审找的是我"实现对了但 response/测试过度声称"的问题——这类很难自己发现，reviewer 抓得准。

- MED 1：我把 `except Exception: pass` 写成 response 说"按真实异常处理"，实际仍是静默吞 → **属实**
- MED 2：zip preflight 漏 `pending_share_events`（上一轮 review 清单明确列了）→ **属实**
- LOW 3：case3 测试复刻逻辑而非直调 `_prepare_memory_context`，会跟实现一起假绿 → **属实**

全部接受。修复后 **96/96 通过**（原 95 + 新增 warning 可观测测试）。

---

## 1. 逐条处置

### MED 1：TypeError 处置仍静默吞，response 过度声称 ✅ 已修（采纳方案 1）

**核验**：属实。response 写"按真实异常处理"，实际 `except Exception: pass` 仍静默吞。reviewer 的方案 1 合理（outreach 是旁路副作用不阻断 tick，但必须可观测）。

**修复**（`life_simulation.py:_do_outreach`）：
- `except Exception as e:` 改为记录 `logger.warning("life_sim outreach callback failed (not retried, not advanced): %s: %s", ...)`
- 保留不阻断 tick（旁路副作用的契约），但异常可观测
- docstring 注释更新为准确表述："内部异常不再退化重试，但会被下方 except 兜住（旁路副作用不阻断 tick）"

**新增测试**：`test_case4_warning_logged_on_callback_failure`——断言回调失败时 warning 日志含 "outreach callback failed"
**改测试名**：`test_case4_internal_typeerror_not_swallowed` → `test_case4_internal_typeerror_no_retry_no_advance`（准确表述：不重试、不推进状态，而非"不吞"）

### MED 2：zip preflight 漏 `pending_share_events` ✅ 已修

**核验**：属实。上一轮 review §110-120 清单明确列了 `pending_share_events`，我漏了。

**修复**：`handoff.md §11` 补 `$ls -match "pending_share_events"      # PR-C4 四时点语义核心读口（二审 MED2 补）`

### LOW 3：pending 过期测试直调真实函数 ✅ 已修

**核验**：属实。原测试复刻了 `_prepare_memory_context` 里那段逻辑，没调真实函数——实现被改坏时测试会一起假绿。

**修复**（`tests/test_life_sim_review_repro.py`）：
- `test_case3_expired_pending_consumed_as_dropped` 改为**直调真实** `_prepare_memory_context("s1", "", gap_seconds=0, realtime_enabled=False)`
- 用 `message_text=""` + `realtime_enabled=False` 绕开记忆召回重依赖，让 fake 只需最小 `_store` + `life_sim`
- `test_case3b_fresh_pending_consumed_normally` 同样直调真实函数

现在断言 `outreach_fragment == ""` / `dropped_at > 0` / `consumed_at == 0` 都基于真实函数行为，实现被改坏时测试会真实失败。

---

## 2. 改动清单（本轮修复）

| 文件 | 修复 |
|------|------|
| `sylanne_alpha/life_simulation.py` | MED1：`_do_outreach` 的 `except Exception` 加 `logger.warning` |
| `tests/test_life_sim_review_repro.py` | MED1：测试名改准确 + 新增 warning 可观测测试；LOW3：case3 直调真实 `_prepare_memory_context` |
| `docs/architecture/life-simulation-upgrade-handoff.md` | MED2：§11 zip preflight 补 `pending_share_events` |

---

## 3. 验证

```powershell
python -m pytest tests/test_life_sim_persistence.py tests/test_life_sim_structured.py tests/test_life_sim_share_intent.py tests/test_life_sim_review_repro.py tests/test_agents_gating.py tests/test_agents_infra.py tests/test_evolution_learning.py tests/test_dream_consolidation.py -q
```
结果：**96 passed**（17+9+11+8+51）。AST 全 OK。

---

## 4. 反思

这两轮 PR-B/C review 的共同教训：
1. **实现对了 ≠ response 可以夸大**。`except Exception: pass` 是静默吞，不是"按真实异常处理"。表述要精确。
2. **复刻逻辑的测试是假测试**。直调真实函数才能防实现被改坏。后续新测试一律直调，不复制逻辑。
3. **清单项要逐条核对**。上一轮 review 列了 10 个 preflight 符号，我漏了 1 个——这种清单核对应该用 grep 一次性验证而非手抄。

Phase 2 我会沿用：表述精确、测试直调真实路径、清单核对用脚本。

---

## 5. Gate 提议

```text
PR-B/C review response 二审 findings：全部 closed
PR-B: Approved（最终）
PR-C: Approved（最终）
Phase 2：可启动（二审 findings 全部 closed）
```
