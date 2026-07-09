# 记忆 Phase 1 设计：单写咽喉 + 化身栅栏（MEM-03 / MEM-04）

状态：设计经两轮红队（NEEDS_REVISION→修订→再攻）收敛，**PR-1 已绿灯可实现**；PR-2/3/4 带红队 must-fix 清单待做。回滚地板仍 = Phase-0 构建。

本文是实现契约。所有 file:line 对照 `feat/next-gen` 合入 PR #55 后的 HEAD（ece093f）。

## 0. 问题与核心洞察

Phase 0 止住了重启清零，但留下三条并发/竞态遗留（当时文档化 deferred，非红线在线丢失）：

- **F2**：v2→v3 CRC 备份门是无锁 read-check-write，同一 session 两条并发首写可覆盖 v2 回滚快照。
- **F3**：删除会话时 persist→cleanup 无序 + 陈旧引用可把已删记忆写回。
- 相关：LRU 驱逐落盘、WebUI 读路径顺手写活体、quarantine 侧车游离写。

**红队一轮打出的核心洞察（v1 设计致命伤）**：单纯的 per-session FIFO 写队列只序列化「执行顺序」，不隔离「陈旧引用血统」——一次 LLM 请求处理里攥着旧 `MemorySystem` 引用跨多秒 await，期间会话被删，请求结束时旧对象的落盘排在删除 op 之后，FIFO 老老实实先删再把整份已删记忆写回，**排序反而保证了复活**。

结论：需要**两个正交原语**，缺一不可：

- **MemoryWriteThroat（咽喉）**：序列化「执行顺序」——根治 F2 与执行序竞态。
- **化身栅栏（incarnation fence）**：强制「对象血统」——根治 F3 全部复活臂。

## 1. MemoryWriteThroat（MEM-03 之一）

新模块 `sylanne_alpha/memory_write_throat.py`，`class MemoryWriteThroat`，实例挂 `StatePersistence.__init__`（state_persistence.py:172-193）。

- 内部 `_queues: dict[str, deque]` + `_drainers: dict[str, asyncio.Task]` + `_epochs: dict[str, int]`——**全部普通实例 dict，绝不注册进 `session_state_store._maps`**（`release_session` 会 pop 所有登记容器 session_state_store.py:222-225；pending delete op / 墓碑被 pop = fail-open。沿用 conv_sync_locks「锁类容器不得驱逐」原则 :206-212）。
- **双路径 submit**（红队 MAJOR-5 的行为定义，非「断言了事」）：
  - on-loop：`get_running_loop()` == 绑定 loop → 同步 `_enqueue(op)` + 返回 `loop.create_future()`。
  - off-loop（今天就真实存在：webui_server.py ThreadingHTTPServer 工作线程 :1925/1998/2264/2294 同步调 accessor）：`get_running_loop()` 抛 → `self._loop.call_soon_threadsafe(self._enqueue, op)`，fire-and-forget（跨线程 Future 不安全）。**绝不用线程本地 `asyncio.get_event_loop()`**（py≥3.10 工作线程抛 RuntimeError；webui_server.py:2313 现有该坏模式）。
  - token 捕获放 `_enqueue` 内部（恒在 loop 上跑）→ on/off-loop 捕获与入队原子统一。
  - loop 句柄双保险绑定：构造时 best-effort + `main.py:2474 initialize()` 里 `throat.bind_loop(get_running_loop())` 权威绑定。未绑定=fail-closed 丢弃 + log（等价今日 `coro.close()`，不新增 fail-open）。
- **公开壳 / 私有 `_impl` 硬规则 + 防自死锁**（红队 MAJOR-6）：每个收编方法拆 `public shell（submit[+await]）` / `_xxx_impl（真逻辑，只准 op 内部调）`。`submit()` 断言当前 task 不是本 session drainer；**并禁止 op spawn-and-await 子任务再 submit 同队列**（红队 MINOR-6 补丁）。已知两条内部边改 `_impl`：`_cleanup_kv_for_session:1561`→delete、`purge_session_after_meltdown:1423`→delete。
- **单 drainer 生命周期**：per-session 惰性创建；逐 op try/except（异常 `set_exception` 到 caller Future——pipeline llm_request_pipeline.py:2163 依赖 save 异常传播）；空闲自毁（pop 自身队列/drainer 条目，**`_epochs` 永不随之删**）；**空检查与 pop 之间无 await（原子自毁）**；下次 submit 检测缺失/`done()` 即重建。

## 2. 化身栅栏（MEM-03 之二，补齐 v1 缺失核心件）

- **纪元表**：`throat._epochs: dict[str, int]`，只为「发生过删除/purge 的会话」建条目，进程内即可（陈旧 Python 引用不可能跨进程存活；跨重启保护由 §4 索引负责）。
- **实例印章**：每个 `MemorySystem` 活体带运行时属性 `_incarnation_epoch`——**绝不序列化、绝不进 `to_dict()`**（PR-1 附断言）。盖章点：① `memory_system_for_session` 懒创建（session_context.py:793-799，同步读 `current_epoch(sk)`，无 await）；② load 的 store 准入（§3 臂⑦）；③ bump-and-restamp。未盖章对象按 epoch==0 处理：epoch==0 会话放行，epoch>0 会话拒写（fail-closed）。
- **bump 时机**：三个删除类公开壳在**提交瞬间同步** `bump_epoch(sk)`——`_on_session_deleted`（:1480，紧跟 :1511 release）、`delete_sylanne_memory_state` 壳（:1391）、`purge_session_after_meltdown` 壳（:1419）。bump 在 submit 时而非执行时：让「delete 入队后、执行前」提交的任何旧血统 op 立即失效。私有 `_impl` 不 bump。
- **bump-and-restamp**（推演必需补丁）：bump 后立刻检查 store 当前占位者，存在则用新纪元重新盖章。理由：meltdown/purge_data 是「原地清空活体 + `_hydrated=True` latch、活体继续当占位者」语义（7729753），只 bump 不 restamp 会让用户 meltdown 后继续聊天的新记忆因旧章被永久拒写（比复活更糟）。语义 = 「凡不是此刻占位者的引用全部出局」。
- **验章**：所有 op 在 `_enqueue` 捕获 `token = epochs.get(sk,0)`；save 类额外携带 state 对象、执行前验 `state._incarnation_epoch == epochs[sk]`；hydrate/quarantine 类验 `token == epochs[sk]`；delete/purge 自身豁免（定义 bump，幂等）。失败=丢弃 op + `logger.warning` + 计数器（暴露 admin），**绝不降级执行**。
- **占位者权威兜底**（红队 MINOR-5，PR-1 必带）：验章失败时若 `state is memory_map.get(sk)`（执行时），restamp-and-allow 而非拒——占位者自身永不出局，杜绝「off-loop 懒创建盖旧章→新记忆永久静默拒写」的 fail-closed 数据丢失。真陈旧引用仍被拒（被拒的 save/load 不能再占 store）。
- 与 `_hydrated` latch（7729753）：latch 挡「未删 KV 期间的合并」，栅栏挡「血统伪造」，互补不互替，都保留。

## 3. 八条写臂（全收编/栅栏化，无一游离）

① `save_sylanne_memory_state`（:926-967，store 写回 :950-952 移入 op 且置于验章后）；② `_persist_memory_kv_only`（:225-255，驱逐回调 :219-223 同步 off-loop submit，顺手修好今日线程侧驱逐落盘被 `coro.close()` 静默丢的暗病）；③ `hydrate_memory_system`（:1269-1389，`_schedule_memory_hydration` 改 `throat.submit_hydrate`）；④ `delete_sylanne_memory_state`（primary-first + 有界重试）；⑤ `purge_session_after_meltdown`（复合 op，含 kernel/域键/**kernel 文件清扫**）；⑥ `_on_session_deleted`/`_cleanup_kv_for_session`（并进单 delete op，废除死 persist 步）；⑦ **load 的 store 写回**（:1207/1227/1253 三处，抽同步无 await 临界区 `_admit_loaded_state(sk, state, token)`：验 token + 队列无 pending delete，失败返游离展示副本不落 store）；⑧ **`_persist_memory_quarantine` 侧车写**（:1080-1113，hydrate 内联串行 / load 带 token op，删除后到达即弃，兼修 get→merge→put 并发丢条目）。

不属写臂但相关：llm_request_pipeline.py 四处 `body.memory["_memory_system"]` 写是 kernel-blob 死重（PR-5 删）；四处 meltdown/purge 原地清空 + latch 是内存操作，经 bump-and-restamp 兼容。

## 4. WAL 废弃 → 单键全局 pending-delete 索引

**废 WAL**：陈旧 delete intent 盲重放是跨版本定时炸弹（崩溃留 intent→回滚 Phase-0→回滚期积累合法新记忆→再升级重放抹掉，违红线1）；per-session 惰性恢复对「被删=永无活动」的会话永不触发；AstrBot KV **无键枚举 API**（只有 get/put/delete by key），per-session 侧车键永远扫不到。

**换**：单键 `sylanne_memory_pending_deletes`（登记进 `MEMORY_KV_KEYS_MANIFEST`）：`{"version":1,"entries":{safe:{"epoch":int,"ts":float}}}`。delete/purge op 首步 put 登记、全键删成后摘除。恢复点 = `main.py:2474 initialize()`（真实存在、有 running loop、已在做 life_sim 恢复），启动扫描，被删会话无需后续活动即被扫到。

**三重防「陈旧重放毁数据」**：(1) 键删失败改**原地有界重试**（≤3 次退避），废除盲重放；(2) 删除顺序固定 primary→backup_v2→quarantine→非记忆键→摘索引；(3) 重放守卫：扫到 entry 先读 primary，**缺失/空才补删侧车摘 entry；primary 非空绝不重放**（保留 entry + `log.error` 交管理员经 admin purge 决断，fail-closed 偏向不毁数据）。任何成功 save op 顺手摘本 session 陈旧 entry（进程内镜像判存在才碰 KV）。

**红队 must-fix（PR-4，本节漏洞）**：
- 索引**必须被 hydrate/admit 消费**：进程内镜像于 initialize 扫描时载入；hydrate/admit 在存在未决 entry 时**保持 fail-closed（不补水→`_refuse_unhydrated_overwrite` 挡写→entry 不被自动摘）**，交管理员决断。否则「重试耗尽/崩溃窗口B + 重启」会让 bot 主动重服务已擦除记忆、且首次 post-复活 save 摘掉 entry 销毁唯一证据。
- 索引是**全局键、drainer 是 per-session**→「单写者」假设为假：所有索引改动**串行到一把全局 `asyncio.Lock`**（或专用 index-writer 队列），防丢更新致侧车残留永久不可见。

## 5. 存储解耦（PR-5）

删 llm_request_pipeline.py:2158-2159/2221-2224/2344-2345/2481-2482 四处 `body.memory["_memory_system"]` 写 + `mark_dirty("memory")`（紧邻 persist/save 保留）。安全依据：`AlphaBodyState.from_dict` 白名单本就丢弃该键，从未在快照往返幸存，KV 已是唯一持久面。诚实标注：load 第 4 级回退的进程内残值随之死亡，此后仅旧 kernel 文件残档可达（1/2/3/5 级 + alpha.json 救援全保留）。

## 6. MEM-04 门面 + admin（PR-6/7）

新 `sylanne_alpha/memory_facade.py`，`MemoryFacade(plugin)`；main.py 四委托（:768/2046/2051/2058）改转发 facade 同名方法，**签名逐字不变**，内部转 StatePersistence（写走咽喉）+ SessionContext（同步 accessor）。`MemorySystem.recall/write_summary` 不搬家（v2core/domains/memory.py:62 positional 调用不动）。

admin（只读优先）：`inspect`（逐键存在性/字节/version/backup CRC/`_hydrated`/`_incarnation_epoch` vs epoch/队深/拒写计数）、`quarantine_view`（现状只写不读的缺口）、`pending_deletes`、`export_blob`、`list_sessions`（best-effort）。变更类：`flush`（补 consolidate/sink handler 不存盘空档）、`purge`（管理员对 pending-delete 残留决断出口）。WebUI 三只读端点排最后，避让任务 #11 前端在途。

## 7. 迁移安全 / 冻结面 / fail-closed

- **格式零变化**：不改 to_dict/from_dict，`_incarnation_epoch` 绝不序列化（PR-1 断言）。v3 blob 双向可读，惰性逐字段 from_dict 教条有效。
- **回滚地板不抬升** = Phase-0；唯一新 KV 残留是单键索引（Phase-0 无读者=惰性孤儿，再升级重放守卫保证回滚期数据安全）。
- **冻结面门禁断言**（每 PR）：positional recall（v2core/domains/memory.py:44-62）、write_summary/memory_backend（emotion_spirit_bridge.py:218-231/558）、`memory_system_for_session` 同步契约（内部加盖章一行、签名不变）、四委托签名、protocols.py:73、load/delete/purge 公开签名、WebUI 响应形状、public_api/大饼零触碰。
- **fail-closed 总纲**：验章失败/loop 未绑定/准入失败/pending-delete 歧义=一律不写/不落 store/不重放；`_refuse_unhydrated_overwrite`（:847-894）与备份门（:969-1078）逐字保留——全设计无一处新 fail-open。

## 8. 分期（7 个独立可 revert PR）

1. **PR-1（绿灯，可开工）** 咽喉骨架 + 栅栏原语 + F2。双路径 submit + loop 双绑定 + shell/_impl + re-entrancy（含 spawn-and-await 禁令）+ 单 drainer 容错/原子自毁/重建 + `_epochs`/盖章/验章（**含占位者权威兜底**）+ 懒创建盖章 + 收编 save/`_persist_memory_kv_only`（store 写回移入 op 后）。**栅栏在 PR-1 生产惰性**（无 bump 调用方发布），唯一活行为变化 = 两条 v3 首写序列化（闭合 F2）+ off-loop 驱逐落盘从静默丢改为执行（fail-safe，仍受守卫）。测试：F2 双并发首写→backup 恰写一次 CRC 自洽；手动 bump 后 stale 印章 save 被拒且 store 未被重占；stdlib 线程 off-loop submit 真入队执行；**drainer 异常经 Future 传播**；**原子自毁/重建**；`to_dict` 无化身键；golden round-trip 全绿。
2. **PR-2** 删除臂 + 三壳 bump-and-restamp + hydrate 收编 + token 验证；**并入红队 must-fix：kernel 文件(.alpha.json)清扫折进 delete op（闭合第 4 条 salvage 复活臂）**。测试：删除→立即重建+hydrate；stale-ref save 全链复现被拒（BLOCKER-1）；meltdown 后继续聊天照常落盘（restamp）；purge→delete 无自死锁；stdlib 线程 meltdown 真达咽喉执行。
3. **PR-3** 第三臂（load 准入栅栏 `_admit_loaded_state`）+ quarantine 收编；**并入 must-fix：admit 消费持久 pending-delete 索引镜像、未决 entry 时 fail-closed**。
4. **PR-4** pending-delete 索引 + initialize 扫描 + **全局 Lock 串行索引改动** + save op 顺手摘陈旧 entry + 三重重放守卫。测试：entry+primary 已删→冷启补删；entry+primary 非空（模拟回滚期新数据）→绝不重放数据原样（BLOCKER-2 反例负测试）。
5. **PR-5** 存储解耦。 6. **PR-6** facade 提升。 7. **PR-7** admin 只读端点（避让 #11）。

## 9. 诚实遗留（非红线在线丢失，文档化）

- 崩溃窗口 A/B 残留明文（delete op 开跑前进程死 / 索引已写 primary 未删）：admin inspect 可见 + 手动 purge 补删；与 Phase-0 现状等价或更窄，是留存残留非数据毁损，红线1/3 压过留存义务；根治需同步删除回调里做异步 KV 写，AstrBot 架构做不到。
- pending-delete 歧义 entry（primary 非空）不自动决断，交管理员——自动化需 blob 级写时间戳=格式变更，收益不抵。
- **红队 MINOR-3 待并 PR-2**：`sylanne_v2core_domains:{safe}`（reconsolidation overlay，legacy 键含原始记忆 TEXT，v2core/domains/memory.py:159-171）**不在 delete op 键删清单**——meltdown 已删（purge:1424-1450），但普通会话删除漏删=删后明文残留。PR-2 delete op 非记忆键步补上。
- load 第 4 级回退进程内残值随 PR-5 死亡（仅旧 kernel 文件可达）：文档 + 基线测试。
- `list_sessions` 进程内 best-effort；`_epochs` 表进程内永生（每删过会话一 int，量级微不足道，墓碑不驱逐是刻意 fail-closed）。
- MEM-13 拆包 + WebUI 三实现 canonical 化后置：facade/throat 模块边界即切割缝，等 #11 与在途 worktree 落地。

---

方法论溯源：本设计经 pontia 式设计→红队→修订→再红队两轮收敛，见 [[redline-premerge-adversarial-gate]]。冻结消费面依据见 consumers-contract 审计与 [[memory-redesign-proposal]]。
