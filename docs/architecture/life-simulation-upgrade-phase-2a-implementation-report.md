# Phase 2A 实现完成报告

日期：2026-06-19
对象：`docs/architecture/life-simulation-upgrade-phase-2a-handoff.md`（v3）
前置裁决：`life-simulation-upgrade-phase-2a-implementation-ruling.md`（Approved to Implement）
结论：PR-D / PR-E / PR-F 已实现并通过全量回归，待代码 review。

本报告陈述真实状态，取代任何自夸式回应。

---

## 0. 改了哪些文件

生产代码（仅 `.clean-sylanne-github/sylanne_alpha/`，未碰根目录 1.4.0 死树）：

- `memory_system.py`：PR-D 字段契约 + PR-E 召回过滤/排序
- `life_simulation.py`：PR-F M8 守线注释 + `life_prompt_fragment` 去重跳过
- `llm_request_pipeline.py`：PR-F life_sim 写 memory 补 metadata + 静默吞异常改 warning

测试（新增 3 文件）：

- `tests/test_memory_contract_prd.py`（14）
- `tests/test_source_aware_recall_pre.py`（13）
- `tests/test_m8_guardrail_prf.py`（9）

---

## 1. PR-D Memory Contract

完成点：

- `MemoryItem` 新增 `confidence: float = 0.5` / `privacy_level: str = "open"` / `life_event_id: str = ""`（memory_system.py:206/209/211，锚在 dataclass 区段）。
- 新增模块级 `_normalize_privacy_level()` + 合法集 `_LEGAL_PRIVACY_LEVELS={open,internal,shareable,user_fact}`：None/空串→基线 `open`（旧 dialogue 兼容）；未知/非法字符串→fail-closed `internal` + `logger.warning`，绝不兜底 open。
- 新增 `MemoryItem.__post_init__` 单点规范化 chokepoint：clamp confidence 到 [0,1]（非数字→回退 0.5）、privacy fail-closed 归一、life_event_id 兜 str。覆盖直接构造 / write_summary / from_dict 全路径。
- `to_dict()` 输出三键（:247-249）；`from_dict()` 缺字段迁移传原值交 `__post_init__`（故意不预 `float()`，防旧档脏字符串当场抛错绕过兜底）。
- `write_summary()` 扩参 `confidence/privacy_level/life_event_id`（:933-935），旧调用方不传走基线默认，向后兼容。
- 命名撞车处理（裁决 §1）：保留 `MemoryItem.confidence: float`，与 `MemoryResult.confidence: str`(recall label) 不同类、注释写清；召回侧只从 `obj.confidence` 读 float。preflight 锚 MemoryItem 区段，不再被 MemoryResult:257 假命中。

---

## 2. PR-E Source-Aware Recall

完成点：

- 新增公共层 `_apply_privacy_filter(pool, visibility)`（memory_system.py:1501）：放在 `_gather_pool` 之后、选宽/扩散之前。隐私级从 `c["obj"]` 读（MemoryItem 与 GraphNode 均显式持 `privacy_level`，经各自 `__post_init__` 规范化）；旧图谱档迁移为 `"open"`，非法值归一 `internal`；**无 `privacy_level` 属性的对象 fail-closed drop**（不再"视 open"）；internal 在 user_visible 下剔除。
- 三模式覆盖：`_recall_legacy`（:1622）与 `_recall_activation`（:1903 后）两处 `_gather_pool` 之后都接同一函数；SHADOW 以 legacy 为返回，天然覆盖。实测三模式 internal 均不进结果。
- 新增 `_source_aware_rank(results)`（:1555）：`final_score` 主序第一优先级（与原 `results.sort` 一致，保 LEGACY 行为），仅同分时按 source 优先级（user_fact > dialogue/open > life_sim > life_reflection）+ confidence(float) tiebreaker。仅在 legacy 路径应用（activation 有自身 ACT-R 排序，裁决允许 rank per-mode）。
- Fail-closed 边界（裁决 §3）：单候选异常→丢弃；filter 整体异常→返回空（空召回优于泄露），绝不返回未过滤池；rank 异常→降级 final_score 排序（此时 internal 已前置摘除，安全）。两个异常域彻底拆开，解决 handoff §1.5:82 自相矛盾。

## 3. PR-F M8 Guardrail

完成点（守线，不接 feedback_pressure）：

- `_SHARE_WEIGHTS["unanswered_penalty"]` 保持 -0.20（life_simulation.py:261）；`_recompute_final`（:865）与 `_evaluate_share_intent`（:1108）保持 `* 0.0`，未引入非零乘子。实测改字段值/拉满不影响 final_score → 该信号在 ShareIntent 侧未消费，无双重惩罚。
- 未加 session_key、未调 `derive_dispatch_policy`、未读 feedback_pressure、未碰 `_most_recent_host_key`、未加 origin_session。scheduler gate 独占 unanswered 惩罚。
- life_sim 写 memory（llm_request_pipeline.py:1443）补传 `confidence=0.5`、`privacy_level="shareable"`、`life_event_id=outreach_ctx.get("event_id","")`；`except Exception: pass` 改为 `logger.warning`（不 raise、不改主流程）。
- 误导注释更新：两处评分公式 + docstring 写明"真实接 feedback_pressure 留 Phase 2B，随 origin_session 设计"。
- 去重（handoff §2.3 / MED-5）：`life_prompt_fragment` 新增跳过 `consumed_at>0 or dropped_at>0` 的事件——已消费事件改由 recall 注入 memory 持久化版本（带 life_event_id），二者不重复注入。

## 4. 测试与验证（真实数据）

- 新增测试全过：一审 36（PR-D 14 + PR-E 13 + PR-F 9）+ 二审修复 10（GraphNode 隐私迁移/roundtrip/非法 fail-closed、裸对象 drop、扩散节点过滤、wide 二次过滤、双重注入去重、延后写 metadata、`_mark_life_outcome` warning）。
- 全量回归：**659 passed, 2 skipped**（py3.13.14 + pytest 9.0.3）。基线 PR-A/B/C 为 96 passed，本次为含全部既有套件的全量，零失败——recall 链 + GraphNode 加字段未碰坏任何既有 memory_recall（26 项）/ 图谱扩散 / life_sim 测试。
- 二审修复详见 `life-simulation-upgrade-phase-2a-implementation-review-response.md`（L3/ACTIVATION fail-closed、同轮去重、warning、回调 arity 缓存 id-reuse 根因修复）；三审修复详见 `...-review-response-review-response.md`（L2→L3 压缩 internal 不入图、直接 internal triple 跳过、internal 不作扩散桥）。
- AST：三个生产文件 `ast.parse` 均 OK。
- Preflight 符号核对（生产文件 grep，非 tests/docs）：`def _apply_privacy_filter(`、`def _source_aware_rank(` 真有定义；`write_summary` 三新参进签名（非注释）；`to_dict` 含三键；confidence 锚 MemoryItem 区段（不被 MemoryResult:257 假命中）；`unanswered_penalty` 在 `_SHARE_WEIGHTS` 且两处 `* 0.0`；life_sim 写入含 shareable/life_event_id。
- 无未跑项；无失败项。

## 5. 合规声明

- 未新增任何 LLM 调用：confidence 是规则中性值、privacy 是字符串标签、过滤/排序是规则——全程零 LLM。
- life_sim 未写 `user_fact`：写入固定 `privacy_level="shareable"`；`__post_init__` 与 `_normalize_privacy_level` 均不会把内容升为 user_fact。
- 未接 `feedback_pressure`、未调 `derive_dispatch_policy`、未引入 session_key/origin_session。
- 未改根目录 1.4.0 死树，仅改 `.clean-sylanne-github/sylanne_alpha/`。
- 主动偏离声明：handoff §1.5 两句 fail-open（候选缺字段默认 open、异常退化到不过滤）按裁决 §3 落地为 fail-closed（从 obj 读隐私 + 入口归一、异常返回空），代码层堵死前两轮 review 点名的隐患。

## 6. 待 review 项 / 已知边界

- `_source_aware_rank` 仅在 legacy 应用；ACTIVATION 自有 ACT-R 排序，若 2B 启用 activation 需对齐 source 优先级（privacy filter 已三模式覆盖，不受影响）。
- 多会话漂移仅审计未修（裁决/MED-6）：`test_document_current_multi_session_drift_risk` 只断"选最后活跃会话 + 回写一致"，不断"不误投"。origin_session 修复留 2B。
- `source="life_reflection"` 仅保留枚举/兼容排序，未新增生产者或语义消费。

