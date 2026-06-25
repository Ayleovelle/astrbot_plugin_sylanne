# Phase 2A Implementation Review Response (Round 3)

日期：2026-06-19
对象：`docs/architecture/life-simulation-upgrade-phase-2a-implementation-review-response-review.md`
修订文件：`memory_system.py` / `llm_request_pipeline.py`（write 路径无改动；report 文案修正）
结论：BLOCKER + MEDIUM + P3 全修，全量回归 659 passed / 2 skipped / 0 failed，待三审。

Plato 这两条抓得对：上一轮我只补了"internal 节点不进结果 / 二次 filter"，但没堵住源头——internal 信息在进 recall 之前就被压缩/扩散洗成 open 图结构。这一轮按 reviewer 指定的保守边界从源头闭环。

---

## 1. BLOCKER：L2→L3 压缩 fail-open internal —— 已修

采纳 reviewer 列的第一种可接受边界（保守，不靠末端召回过滤）：

- **`compress_check()` 排除 internal**（memory_system.py）：返回压缩候选时过滤掉 `privacy_level=="internal"` 的 L2 条目。internal L2 永不进入 `_compress_memories()` / `ingest_graph_triples()`，留在 L2 作 internal `MemoryItem` 继续受 `_apply_privacy_filter` 保护。
  - 因 `compress_check` 是唯一压缩入口，`_compress_memories` 只会收到 visible 条目，其 `remove_compressed([items[:10] id])` 也只移除实际处理的 visible ID——满足 reviewer "only remove compressed IDs for the actually processed visible items"。
- **`ingest_graph_triples()` 防御性跳过显式 internal triple**：dict triple 带 `privacy_level=="internal"` 时直接 `continue` + warning，不创建节点/边。覆盖"直接 ingest internal triple"路径。

为什么不选 propagation：reviewer 指出 `GraphEdge` 无隐私字段，端点已是 open 节点时纯节点级 propagation 不够。Phase 2A 取保守边界（internal 不进可见 L3），把图级隐私语义留给后续阶段。

测试：

- `test_compress_check_excludes_internal_l2`：老 internal L2 不进压缩候选，open 的进。
- `test_ingest_internal_triple_not_user_visible`：直接 ingest internal triple → 图谱无该实体、recall 取不到。
- `test_ingest_open_triple_still_works`：正向回归，普通 triple 仍正常进 L3。

---

## 2. MEDIUM：internal 节点作扩散桥 —— 已修

在 `_spread_activation()` 内对源节点和邻居节点都做隐私判定（不止末端 `wide`）：

- `_emit()`：邻居为 internal → 不纳入 `spread`（不接收激活）。internal 节点既不进 spread 结果，下一跳也不会作为 src 出现（第二跳只遍历 `spread.items()`，internal 从未进入）。
- 第一跳种子循环：internal 种子不作扩散源。
- 保留末端二次 `_apply_privacy_filter` 作 defense-in-depth。

效果：`open A → internal B → open C` 链，A 扩散时 B 因 internal 不接收激活、不进 spread，C 无法经 B 到达。

测试：`test_internal_node_not_spreading_bridge`（直测 `_spread_activation`，断言 internal B 与下游 C 均不在 spread 结果）。

---

## 3. P3：report 旧 fail-open 文案 —— 已修

`...-implementation-report.md` PR-E 节那句"GraphNode 等无属性结构节点→视 open 不误杀"已改为当前行为：MemoryItem/GraphNode 均显式持 `privacy_level`，旧图谱迁移 open、非法归一 internal、无该属性对象 fail-closed drop。

---

## 4. 验证（真实数据）

- 全量回归：**659 passed, 2 skipped, 0 failed**（py3.13.14 + pytest 9.0.3）。较二审 655 增 4 个三审针对性测试。
- 两个生产文件 AST OK。
- 既有图谱/压缩/扩散套件全绿。

---

## 5. 仍守边界

- 未新增 LLM；life_sim 未写 user_fact；未接 feedback_pressure / derive_dispatch_policy / origin_session；未改 1.4.0 死树。
- 未改 life_sim 写 memory 路径（上一轮延后写入逻辑不动）。
- 多会话漂移仍仅审计未修（origin_session 留 2B）。
- 完成报告测试数将同步更新为 659。
