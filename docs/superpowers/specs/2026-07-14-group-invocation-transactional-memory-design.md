# 群聊显式呼叫与事务式记忆提交设计

日期：2026-07-14

目标版本：下一灰测版本（不推送远端）

## 1. 背景与已证实根因

### 1.1 群聊显式呼叫被错误静默

AstrBot v4.26.5 用 `event.is_at_or_wake_command` 表示 `@bot`、引用 bot、框架唤醒前缀等显式唤醒。当前请求管线却读取不存在的 `event.is_at` / `event.at_bot`，因此真实显式呼叫会被降级为普通群消息，再受 SFPD 相变阈值控制。

即使社交信号正确标为 `is_at_bot=True`，当前相变层在 `effective_threshold == 0` 且 `pressure == 0` 时仍返回 `should_express=False`。显式呼叫因而仍可能静默。

纯 `@bot` 的 `message_str` 为空。AstrBot 内部 Agent 阶段会跳过“无文本、无媒体、无引用、无预建 ProviderRequest”的事件，因此不会创建 LLM 请求。插件配置的群聊触发名字目前只在 LLM 请求已经存在后参与 SFPD，不能反向唤醒 AstrBot 核心。

### 1.2 L1 摘要在崩溃后重放

对话 flush 调用 `ConversationBuffer.drain()` 清空内存消息，生成摘要并写入 L1，但成功后没有立即持久化空 buffer。磁盘 `.buffer.json` 和 KV 中仍可能保留 flush 前的非空快照。

插件重载或进程闪退后，旧 buffer 被恢复；其 `last_activity` 已超过空闲阈值，后台循环会再次总结同一批消息。LLM 每次措辞不同，因此表现为多条语义近似、时间戳不同的 L1。

“跨群记忆总开关”只控制按身份挂靠的 PersonShelf，不关闭当前 session 的主 L1。本设计保持该语义不变。

## 2. 设计目标

1. `@bot + 文字`、引用 bot、AstrBot 唤醒前缀、插件触发名字均作为显式呼叫，必须进入 LLM，不受 SFPD 自主静默阈值影响。
2. 纯 `@bot` 和纯唤醒词可以自然回应，并在 AstrBot 对话历史中留下真实、可识别的事件记录，不伪造“在吗”等用户原话。
3. 普通群聊消息仍由 SFPD 决定是否表达，不把插件变成每句必回。
4. 对话摘要 flush 在任意崩溃点都不丢失、不重复产生 L1，也不通过中文语义相似度误吞真实的新对话。
5. 兼容旧存档；不自动删除现有重复记忆。

## 3. 非目标

- 不改变跨群 PersonShelf 的总开关、scope 或 visibility tier 语义。
- 不用 embedding、LLM 或中文分词做 L1 写入去重。
- 不修改相变表达层的全局数学定义；它继续服务普通群聊的自主表达。
- 不自动合并或删除用户已有 L1 条目。

## 4. 群聊显式呼叫意图层

### 4.1 单一分类器

新增无副作用分类器，将群聊事件归一为以下意图之一：

- `ambient`：普通群消息。
- `direct_at`：消息链含对 bot 的 At。
- `reply_bot`：引用 bot 消息。
- `core_wake`：AstrBot 已设置 `is_at_or_wake_command`。
- `trigger_name`：消息以人格名或配置触发名开头，并满足词边界。
- `empty_call`：上述显式呼叫成立，但没有真实文本、媒体或引用内容。

分类器只使用 AstrBot v4.26.5 已核实的公开成员和 `astrbot.api.message_components`。配置中的多个触发名按英文逗号、中文逗号拆分并去空白；匹配必须从消息开头开始。边界按触发名末字符判断：末字符为 ASCII 单词字符时禁止继续粘连 ASCII 单词字符，但允许后接中文；末字符为中文时允许“小澜你好”这种自然后缀。名字出现在句中只作为注意力信号，不自动升级为显式呼叫。

### 4.2 一次分类，全链消费

消息 handler 只分类一次，将结果写入 event extra。该 handler 的优先级必须高于 AstrBot 内置 `maxsize - 1` 空 @ handler；只有 Sylanne 接管的空呼叫才预建一次请求并阻止后续默认 Agent/内置 handler，未接管时必须 fail-open 回落官方行为。后续请求管线直接读取该 extra，不再从不同裸字段重复推断。

AstrBot v4.26.5 的 session-control handler 与本 handler 都使用 `priority=sys.maxsize`，但内置 handler 在插件 handler 之前注册，框架排序稳定；内置 waiter 命中并 `stop_event()` 后，`StarRequestSubStage` 会立即结束本 stage，因此 Sylanne handler 不会偷走正在等待的下一条消息。本设计把该 4.26.5 注册顺序和短路语义视为显式兼容契约，并用真实 ProcessStage 集成测试固定；不读取私有 waiter 表，也不伪造不存在的公开 guard。

- `trigger_name` 会设置官方 `event.is_at_or_wake_command=True`，使 AstrBot 创建标准请求。
- `direct_at` / `reply_bot` / `core_wake` 保留框架已有唤醒状态。
- 任何非 `ambient` 意图在群聊请求管线中直接放行；只有 `ambient` 调用 `should_express()`。

若 extra 因第三方直接构造 ProviderRequest 而缺失，请求管线保守回退到官方 `is_at_or_wake_command`，不再读取 `is_at` / `at_bot`。

### 4.3 纯呼叫请求与历史契约

纯 `@bot` / 纯唤醒词使用 AstrBot 官方 `event.request_llm(...)` 生成 ProviderRequest，不修改 `event.message_str` 为虚构自然语言。插件必须先按 AstrBot 主 Agent 的 `_get_session_conv` 同等流程取得当前 conversation：读取当前 conversation ID，缺失或失效时创建并重新读取，再把 conversation 显式传给 `request_llm`。只传已废弃的 `session_id` 或遗漏 conversation 都不满足 WebUI 历史持久化契约。

历史中的 user turn 使用规范化事件文本 `（用户仅呼叫了你，没有附带文字）`。这是对真实消息结构的记录，不声称用户说过“在吗”。AstrBot v4.26.5 的公开 `astrbot.api.provider` 未导出 `TextPart`，因此不使用 `astrbot.core.agent.message` 内部类型；回复风格说明由 event extra 传到 `on_llm_request`，再作为本轮瞬态 system context 注入，不进入对话历史。

synthetic 标记必须在即时聊天碎片防抖之前生效。纯触发名的 `event.message_str` 虽非空，也不得进入 fragment merge 或执行 `request.prompt = merged_plain`，否则规范化历史会被触发名覆盖。

事件 extra 标记该轮为 `synthetic_empty_call`：

- AstrBot 对话历史保留规范化 user/assistant 对，满足 WebUI 可追溯性。
- Sylanne 对话 buffer 不写入该 synthetic 轮的 user 或 bot 文本，避免它与后续真实对话混合后进入 L1；`last_bot` 与群聊社交状态仍正常更新。
- 实时聊天接管开启时由 Sylanne 处理；未开启时继续尊重 AstrBot 自带 empty mention 行为。

### 4.4 媒体与引用边界

At + 图片、语音、文件、视频或引用不属于 `empty_call`，不得用占位文本覆盖。它们继续走 AstrBot 的媒体/引用解析和 Sylanne 转述路径。

## 5. 事务式 Conversation Flush

### 5.1 数据模型

`ConversationBuffer` 从单一 `messages` 扩展为：

- `messages`：仍在收集的新消息。
- `pending_flush`：至多一个待提交批次。
- `revision`：每次 buffer 状态变更递增；KV/文件恢复时选择更高 revision 并修复落后 sink。
- `PendingFlush.batch_id`：对 `session_key` 命名空间与规范化 `role/text/ts` 序列计算的稳定 BLAKE2 摘要，避免同一身份的多个群在 PersonShelf 共桶时互相误判同批。
- `PendingFlush.messages`：不可变批次内容。
- `PendingFlush.flush_epoch`：claim 时捕获的会话 flush 世代；reset 会递增世代，使所有旧批次失效。
- `claimed_at`、`attempts`、`next_retry_at`：恢复和退避元数据。

批次 ID 包含原始消息时间戳，因此同一段文字在不同时间再次发生会得到不同 ID；崩溃恢复的同一批则保持相同 ID。

### 5.2 写前日志流程

每个 session 使用独立 `asyncio.Lock` 串行 claim/commit：

1. `claim`：将当前 `messages` 原子移动到 `pending_flush`，新到消息继续进入新的 `messages`。
2. `prepare`：先把含 pending 的同 revision buffer 同步持久化到 KV 和文件。持久化失败则不调用摘要 LLM。
3. `process`：对 pending 生成摘要。
4. `epoch fence`：摘要返回后、每个有副作用的 sink 前复核 `flush_epoch` 与当前 pending；reset 后的旧任务不得提交。
5. `commit memory`：用 `batch_id` 幂等写主 L1，并在 MemorySystem 的独立 commit-receipt ledger 记录该批次；receipt 不依附 L1/L2 条目，不能因 L2→L3 压缩而消失。
6. `persist memory`：主记忆与 receipt 同次持久化成功后，才允许提交可选 PersonShelf 与确认批次；异常和 `False` 都进入同一个失败/退避转移。
7. `ack`：清除 `pending_flush` 并持久化 buffer。KV/文件任一失败时恢复内存 pending，保留 durable receipt，后续重试直接继续 ack，不再调用摘要 LLM 或追加记忆。
8. 两个 buffer sink 都确认无 pending 后，才可移除 receipt 并持久化清理；清理失败只多留无害 receipt，不能重新制造对话。
9. 若 `messages` 已积累且达到 flush 条件，下一轮再 claim，绝不与 pending 混合。

同步文件 bootstrap 后，某 session 的首次异步请求必须同时读取 KV 与文件快照，选择最高 revision，加载后回写修复落后 sink；同 revision 但内容分叉视为损坏并 fail-closed，不凭来源优先级猜测。

所有 `*.buffer.json` 写入（防抖、checkpoint、reconcile 修复和同步 reset）还必须经过同一文件路径级 `threading.Lock` 与磁盘 revision fence。持锁后重新读取当前文件：低 revision 写入直接拒绝，同 revision 内容相异视为损坏并拒绝，只有更高 revision 或完全相同的幂等快照可以原子替换。这样即使 reset 后 finalizer 尚未运行或进程立即崩溃，更早启动但更晚抵达的旧 writer 也不能把已清空的高 revision 快照覆盖回 pending 状态。

### 5.3 幂等提交

`MemoryItem` 增加可选 `source_batch_id`，旧存档缺省为空。`write_summary()` 仅在该字段非空时按批次 ID 查找并返回已有条目；普通直接调用且未提供批次 ID 时保持当前“每次都写”的兼容行为。

MemorySystem 另存可选的 `flush_commit_receipts` 集合。它只覆盖“主记忆已经 durable、buffer ack 尚未双 sink 收敛”的窗口：receipt 存在时重放直接走 ack；ack 双 sink 成功后再清理。这样即使对应 MemoryItem 已被 L2→L3 压缩并从 L2 移除，旧 pending 也不会重新 append。

PersonShelf 条目同样增加可选来源批次 ID。主 L1 和货架是两个独立 sink；任一 sink 重放都只能命中原记录，不能 append 第二份。

### 5.4 崩溃恢复矩阵

| 崩溃点 | 恢复行为 |
|---|---|
| pending 持久化前 | 旧 active 快照仍在，下次重新 claim |
| pending 持久化后、摘要前 | 恢复同一 pending 并重试 |
| 摘要失败 | 保留 pending，按退避时间重试 |
| L1 写入后、记忆持久化前 | pending 重试；未持久化 L1 不构成提交 |
| 记忆持久化后、ack 前 | durable receipt 命中，跳过摘要与写记忆，直接继续 ack |
| ack 的 KV/文件部分失败 | 内存恢复 pending，durable receipt 保留；重试跳过摘要/写记忆并继续 ack，最终双 sink 收敛 |
| reset 与摘要并发 | reset 递增 flush epoch；旧任务在副作用前失败关闭，异步 finalizer 等待 flush 锁后按 batch ID 清除竞态写入并持久化 |

摘要失败采用有上限的指数退避；成功即清零。禁止空闲循环每 10 秒无界重复调用 LLM。

## 6. 兼容与迁移

- `ConversationBuffer.from_dict()` 兼容没有 `pending_flush` 的旧文件。
- `ConversationBuffer.to_dict()` 额外写 `active_messages` 供新协议读取，同时让旧 `messages` 字段投影为 `pending + active`；回滚到 grey5 时旧 reader 最多重放一次，但不会把 pending 当空 buffer 静默丢失。
- `MemoryItem.from_dict()` 和 PersonShelf 兼容没有 `source_batch_id` 的旧条目。
- 升级后若磁盘恰好残留一个 grey5 已总结但未清空的旧 buffer，由于旧 L1 没有 batch ID，最多仍可能再重放一次；首次成功提交后进入新协议，不再重复。系统不根据摘要相似度猜测并删除旧数据。
- WebUI 现有 L1 条目展示和跨 session 聚合不在本次修改范围；已有重复项可由用户人工删除。

## 7. 测试设计

### 7.1 群聊调用矩阵

- `@bot + 文字`：即使表达 pressure 为 0，也进入最终请求处理。
- 引用 bot：进入最终请求处理。
- 纯 `@bot` / 纯唤醒词：生成 ProviderRequest；不修改成虚构原话；历史含规范化事件对；Sylanne L1 buffer 不含该 synthetic user turn。
- 配置触发名位于开头：唤醒；多个中英文逗号分隔名称分别生效。
- 名字仅在句中被讨论：不强制唤醒。
- At + 图片/语音/引用：不判为空呼叫，不覆盖媒体。
- 普通群消息：仍可被 SFPD 静默。

### 7.2 Flush 故障注入矩阵

- 正常 flush：L1 一条、pending 清空、磁盘/KV buffer 为空。
- prepare 持久化失败：摘要 LLM 未调用，消息可恢复。
- 摘要失败：pending 保留并退避。
- L1 持久化成功后模拟 ack 失败：重启重放仍只有一条 L1。
- 对应 L1/L2 已压缩移除后恢复旧 pending：durable receipt 仍阻止二次写入。
- 同一 pending 重放多次：主 L1 与 PersonShelf 各至多一条。
- 不同时间发生完全相同文本：batch ID 不同，允许两条独立记忆。
- flush 进行中收到新消息：新消息留在 active，不被本批吞并或丢失。
- 摘要等待期间执行 reset：旧 batch 不得进入 L1/PersonShelf，reset 后的新消息不得被 finalizer 清除。
- 旧 snapshot writer 晚于 reset 文件写完成：磁盘仍保留 reset 的高 revision；即使在 finalizer 前模拟崩溃并重启，也不得复活旧 pending。
- 旧 buffer / MemoryItem / ShelfItem 存档可正常加载。

## 8. 验收标准

1. 用户报告的四种群聊输入均按显式/普通呼叫契约工作。
2. 通过故障注入证明所有列出的崩溃点最终收敛到单次 L1 效果。
3. 现有普通群聊自主表达、跨群开关、历史持久化和记忆整理测试无回归。
4. AstrBot 插件校验脚本 0 错误，定向测试、全量 pytest、ruff 均通过。
5. 灰测版本只保留本地提交，不 push。
