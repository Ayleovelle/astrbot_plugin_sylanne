# AstrBot Sylanne 多 Bot／多 Persona 完全隔离设计

**日期：2026-07-29**

**状态：设计已逐段批准；书面规格待用户审阅**

**定位：** Sylanne 在 AstrBot 中可同时承载多个 Bot 与多个 Persona，但每一句台词、每一份关系、每一段存档都必须属于唯一舞台。本设计沿用现有实验室／视觉小说的档案卡、章节与“当前场景”语言；不新增页面，也不另起后台。

## 1. 目标与非目标

### 目标

系统提供可验证的完全隔离：任一 Bot、Persona、Session 的可变状态、上下文、权限、容量清理和消息投递都不能越过完整父子路径。操作者始终能识别当前场景属于哪个 Bot、哪一版 Persona、哪一个会话；编辑新角色版本也不会回写旧场景。隔离不是“通常分开”，而是每一项读取、写入、推理、展示、清理、重试和发送都带有作用域。

### 非目标

本设计不引入新 Persona 创作器、关系编辑器、跨 Bot 共享记忆或“全局角色”。不猜测多账号的发送主体，不把默认 Bot 当作路由兜底，也不自动把旧数据变成可写资产。它不改变 AstrBot 的原始事件模型，不改变既有页面结构；这里只定义设计契约，不包含代码、排期或实施方案。

## 2. 固定身份与冻结版本

### BotRef

机器人账号绑定来源是 `BotBinding = (platform_id, self_id)`；内部使用的 `BotRef` 是该绑定加身份代次映射出的稳定、不透明标识，不是原始二元组。`platform_id` 是 AstrBot 平台适配器实例，`self_id` 是实际接收事件的机器人账号。同平台不同账号必为不同 Bot；账号字符串相同而平台不同也必为不同 Bot。原始 ID 不进入文件名、KV key 或普通日志。

事件有 `self_id` 时按完整 BotBinding 解析。`self_id` 缺失时，只有适配器提供当前不可变的 `AdapterAccountProof`，证明该实例仅承载一个仍然有效且曾由真实 `self_id` 建立的 BotBinding，才允许带 `identity_quality=single_account_proven` 的回退；“历史上只见过一个账号”本身不构成证明。不存在证明、证明过期或存在多个候选时，本轮只保留 AstrBot 基础回复，不读取、不成长、不持久化 Sylanne 私有状态，也不主动发送。平台账号集合变化会立即使旧证明失效。

### PersonaRevision

Persona 为只读静态档案；PersonaRevision 为可引用、不可变的版本。PersonaSource 由 AstrBot 公共解析器得到的有效 `persona_id`、原始 `prompt`、`begin_dialogs`、tools、skills 和解析来源组成，规范化后计算内容指纹。不得把已经过插件处理的 `request.system_prompt` 或动态请求内容拿来做指纹；原始 Persona 字段不可可靠取得时，本轮对 Sylanne 私有状态 fail-closed。PersonaRevision 的身份由 `BotRef + persona_id + 内容指纹` 共同确定：同一 ID 内容变化产生新修订；不同 ID 即使内容相同也仍是两个独立 Persona。显示名或递增序号不能代替该身份。

有效 Persona 的解析优先级固定为：显式强制绑定、Conversation 绑定、Bot 默认 Persona。AstrBot Persona 只读，运行时禁止调用 `PersonaManager.create_persona`、`update_persona` 或任何旁路覆写。所有 `sylanne_embodiment_*` 输入一律拒绝，不能用于装载、拼接、修订或隐式补丁；命中时本轮停用 Sylanne 私有状态与动态覆盖层，但不阻断 AstrBot 使用其基础请求完成回复。

### SessionRef、RelationRef 与 ResolvedPersonaRef

`TransportSessionBinding = (BotRef, platform_id, canonical_UMO, session_generation)` 表示一个机器人账号下的 AstrBot 传输会话。`SessionRef` 是用持久化 scope secret 对该绑定做 HMAC 得到的不透明、可重算引用；绑定目录持久化其摘要、generation、验证时间和受保护的投递地址。相同绑定跨重启得到相同 SessionRef；UMO／平台归属冲突、secret 不一致或绑定代次不匹配时 fail-closed，绝不按相似字符串认领。只有放进 `SessionScope = (BotRef, PersonaRevisionRef, SessionRef)` 后，它才可用于状态访问。

`RelationRef` 是稳定关系主体引用，只有放进 `RelationScope = (BotRef, PersonaRevisionRef, RelationRef)` 后才有效；主体可为用户、群组或业务对象，但绝不能只用昵称。

每一轮请求、关系写入、后台任务与待投递意图均保存冻结的 `ResolvedPersonaRef`，其中包含完整 PersonaRevision 引用与内容指纹。同一 AstrBot 传输会话可以在不同 Persona 下拥有彼此隔离的 SessionRuntime 切片：A→B 后的新轮次进入 B，已经开始的 A 任务仍只能写回 A；B→A 时重新挂载 A 原有的人格、会话、关系、生活与调度状态。即便源档案不再可用，旧切片也保留可解释的不可变标识，而不静默替换成最新版本。

## 3. BotRuntimeRegistry 与可变状态

`BotRuntimeRegistry` 是唯一运行时归档柜，层级为 **BotRef → PersonaRevision → SessionRuntime／RelationRuntime**。PersonaRuntime 持有人格成长、Genesis 引用、生活模拟、人格级节律和主动调度；SessionRuntime 持有 host、kernel、会话记忆、缓冲、轮次状态、锁与观测历史；RelationRuntime 持有该 Persona 与稳定关系主体之间的关系档案。任何可变状态至少属于 BotRef 与 PersonaRevision，需要会话或关系语义时再增加对应子引用。

共享基础设施仅限单一 WebUI／端口／认证、Provider 注册表、只读配置、编码器与全局资源预算；可学习、排队、调度、记录、删除的对象全部进入对应 BotRuntime。禁止存在“当前全局 Persona”“最后一位用户”“默认 life simulator”“默认会话”等脱离完整 Scope 的单例。

读写接口以完整 Scope 校验，而不是裸 `persona_id` 或 `session_id`。缓存、锁、队列、去重与指标键使用同一作用域；交叉 Scope 的引用直接失败，不复制、不降级、不做近似匹配。每轮请求只解析一次并冻结 `ResolvedPersonaRef`，随后 host 获取、LLM 请求、记忆、关系、后台任务、响应提交和持久化全部携带它，禁止中途重新解析“当前 Persona”。人格级与会话级写入分别使用 Scope 锁和单调 generation／CAS，陈旧任务不得提交。重启恢复只挂载父级一致、指纹匹配的状态；残缺或矛盾状态进入隔离诊断。

每个 TransportSessionBinding 维护单调 `turn_generation` 与当前有效 PersonaRevision。新一轮消息解析出 Persona 后，原子递增 generation 并签发 `TurnDeliveryLease`。所有最终投递——包括反应式回复与主动消息——都必须在发送前验证 lease、当前 Persona 与 generation；一旦 B 的新轮次已开始，迟到的 A 回复只能记为 `superseded`，不得发送，也不得把“已表达”反馈写入 A。若只修改 Persona 配置但尚无新轮次，已开始的 A 轮次仍可按原 lease 完成。

同一传输会话切出 Persona 时，仅暂停该 Persona 面向此会话的新主动投递，不销毁人格级 scheduler 或既有状态；切回后先重新验证目标、冷却、有效期、TurnDeliveryLease 和 BotDeliveryRef，再决定是否恢复。任何 Persona 都不能在另一个 Persona 当前生效的会话里借旧任务抢回发言权。

### 持久化命名与最小快照

需要跨卸载保留的权威数据写入 `StarTools.get_data_dir()` 下的新 `scope-v1` 根目录；AstrBot KV 只可承担可重建索引或缓存，不能成为长期成长状态的唯一副本。持久化路径和逻辑 key 只使用不可反查摘要，例如：

```text
scope-v1/bots/{bot_digest}/catalog
scope-v1/bots/{bot_digest}/personas/{persona_digest}/genesis
scope-v1/bots/{bot_digest}/personas/{persona_digest}/runtime
scope-v1/bots/{bot_digest}/personas/{persona_digest}/sessions/{session_digest}/runtime
scope-v1/bots/{bot_digest}/personas/{persona_digest}/relations/{relation_digest}/runtime
```

`bot_digest` 由持久化 scope secret 对 BotBinding 与身份代次做 HMAC；`persona_digest` 由 `persona_id + PersonaSource 内容指纹` 派生；会话和关系摘要继续包含其完整父级。原始 prompt、UMO、用户 ID、`self_id` 和 Persona ID 不进入路径或普通日志。

最小权威对象分为：

- `BotCatalog`：BotRef、已验证绑定、身份质量、身份代次与更新时间。
- `SessionCatalog`：TransportSessionBinding 摘要、SessionRef、session／turn generation、当前有效 PersonaRevision、验证状态与受保护的投递地址。
- `PersonaGenesisProfile`：PersonaSource 各字段的 hash、五类受限先验、推断模型与 prompt schema 版本、约束和创建时间。
- `PersonaRuntimeSnapshot`：人格成长、受控情感基线、表达、生活模拟、主动调度、generation 与更新时间。
- `SessionRuntimeSnapshot`：SessionScope、host／kernel、记忆、对话缓冲、轮次状态与更新时间。
- `RelationRuntimeSnapshot`：RelationScope、关系状态、来源与更新时间。

Genesis 的结构化输出必须通过严格 schema、枚举与数值范围校验；越界字段裁剪，未知字段拒绝，任何被禁止的记忆、关系或经历字段使该次推断整体无效。

## 4. Genesis、静态 Persona 与临时叙事

LLM Genesis 只可从静态 Persona 推断五类先验：`traits`、`voice`、`boundary`、`proactivity`、`circadian priors`。它可以界定角色怎样说话、何时主动与哪些边界不可越过；绝不能推断、生成、吸收或暗示记忆、关系、共同经历、用户画像、项目或既往事件。`begin_dialogs` 只作为作者给出的表达示例，不是真实发生过的对话。Genesis 结果不是关系事实，不得写入 RelationRuntime 或 SessionRuntime。

同一 `BotRef + PersonaRevision` 的首次推断采用 single-flight 后台任务，不阻塞首条回复。完成前只使用 AstrBot 基础 Persona，不持久化“临时中性出生值”，也不启动该 Persona 的成长写入；失败后按全局 Provider 预算指数退避重试，并在 WebUI 显示受控状态。

AstrBot Persona 是只读底稿，Genesis 是受限先验；两者都不是运行期记忆容器。所有 Sylanne 动态片段——当轮情绪、节律提示、关系摘要、预算提示、待处理意图——统一合并到唯一 `TransientContextSink`。Sink 按完整 Scope 收集、去重、排序、标明来源和生命周期，是动态内容进入模型上下文的唯一入口。

Sink 必须把所有 Sylanne 动态片段合并成一个有预算的 `TextPart(text=...).mark_as_temp()` 临时部件。它绝不修改 `system_prompt`，绝不修改历史消息，绝不回写 Persona，也不把临时状态伪装为用户、助手或系统已发生的发言。临时 API 失败时跳过本轮动态片段，仅保留 AstrBot 基础 Persona；不得退回旧的动态 `system_prompt` 注入。调用结束，临时部件随边界失效；需要持久化的事实必须经过其完整 Scope 的显式写入规则。

## 5. 场景选择、卡片与 `/api/scopes`

现有实验室顶栏以 **Bot → Persona → Session** 连续选择。优先恢复上次仍然有效的完整 Scope；某一级只有一个有效选项时可自动选中，存在多个候选就停在该级等待选择，不能默认挑第一个。上层切换立即清空下层选择、卡片状态、轮询与已打开的观测舱。界面维护单调递增的 `selectionEpoch` 并取消旧请求；响应只有在 epoch 与服务端回显 Scope 均匹配时才能进入页面。

这组选择器只改变 WebUI 的观测作用域，不修改 AstrBot Conversation 或 Bot 默认 Persona。真实消息仍按“显式强制绑定 → Conversation 绑定 → Bot 默认 Persona”解析；WebUI 不提供把成长快照发布回 AstrBot Persona 的入口。

顶栏、卡片和整卡详情均展示易读父子路径，但不暴露裸 `self_id`、UMO 或完整指纹。相同名字以平台、账号别名、修订指纹短码或会话标识区分，不能仅借颜色、位置或昵称暗示。不得出现“观察”“观察者”“旁观”等观察角标；卡片本体以现有 hover／focus 和键盘 Enter／Space 表达可交互。人格详情沿用现有观测舱，分为“基础人格／出生推断／当前成长／更新时间”，只读且不显示完整 prompt。

`GET /api/scopes` 返回选择器需要的最小父子树；实际状态使用完整父子路径，例如：

```text
GET /api/bots/{bot}/personas/{persona}/sessions/{session}/state
GET /api/bots/{bot}/personas/{persona}/sessions/{session}/history
GET /api/bots/{bot}/personas/{persona}/snapshot
```

服务端每次重新验证父子归属，响应回显完整 Scope、scope generation 与解析时间。危险操作另行签发一次性 nonce，绑定 `principal + 完整 Scope + action + expiry`，不能跨 Scope 或跨操作重放；前端 `selectionEpoch` 不进入服务端安全令牌。

不存在的父级或子级返回 **404**；资源存在但不属于请求父级或无权访问返回 **403**；Bot 身份歧义、generation 过期、nonce 不匹配或并发冲突返回 **409**。服务端不得把这些情况折叠为空列表、成功或默认 Scope。独立服务器和 AstrBot Pages 共用完全相同的 Scope 契约与错误语义，只保留认证入口差异。

state、history、memory、life、persona snapshot、export、legacy claim、proactive retry、reset、purge、meltdown 以及所有其他可读取私有状态或产生副作用的 REST 端点都必须使用完整父子路径。SSE／WebSocket 在握手时绑定完整 Scope 与 generation，Scope 失效时服务端关闭订阅。旧的 scope-less 接口只能返回 `410 scope_required`，或在调用者已经提交并通过完整 Scope 校验时作为薄适配层转发；禁止保留“空参数选最活跃会话”“default”“第一个 Bot”等兼容回退。

## 6. 旧数据、容量与公平清理

缺失完整 Scope 的 `legacy-unscoped` 数据只能只读展示；它不进入活跃会话、关系推断、动态上下文或自动投递。旧档可能已经被多个 Bot 混写，系统必须标为可能污染，不能尝试自动拆分。新旧命名空间物理分离并禁止 dual-write。认领必须是显式“复制认领”：操作者选择目标完整 Scope，系统以 migration ID、来源 checksum、操作者与时间戳新建整块副本；原记录保持只读，不移动、不改名、不覆盖。认领先写 staging、校验后再提交 manifest，因而可中断、可重试且不会重复导入。

历史容量使用共享的全插件观测历史预算。配置为 `0` 表示无限，不触发容量删除；未配置时默认 **128 MB**。超限后，每次追加或维护周期最多删除一个已关闭段（closed segment），逐步把全局占用降到上限的 **90%**；没有可删关闭段则停止。任何 Scope 的活动段、各 Scope 最新段，以及人格成长、记忆、关系、Genesis 和待投递意图都不因观测历史容量压力而删除。

历史 manifest 使用独占锁与单调 generation 记账；追加先原子登记新字节，清理以 manifest generation 做 CAS，竞争失败即重算，不按陈旧大小删除。设 `N` 为当前至少拥有一个保留段的 Scope 数，动态软份额为 `global_limit / max(1, N)`。清理器持久化一个按 scope digest 排序的 round-robin cursor：

1. 先取“总占用高于软份额且存在可删关闭段”的 Scope 集合；
2. 从 cursor 之后的第一个候选 Scope 删除其最旧关闭段，并把 cursor 移到该 Scope；
3. 没有超额候选时，删除全局最旧的可删关闭段；
4. 每次追加或维护周期最多执行一次删除，后续周期继续，直到全局占用不高于 90% 水位。

每个 Scope 的活动段和最新段始终受保护。若受保护数据本身已经超过预算，清理器停止并报告 `budget_unsatisfiable`，不得突破保护条件。该轮转规则保证有可删数据的超额 Scope 在至多一个候选轮次内获得清理机会，高频大 Bot 不能长期挤占安静 Bot 的全部历史。每个决策记录完整 Scope、manifest generation、段标识、前后大小、cursor、触发和未完成原因；聚合诊断仅使用不可反查的统计维度。

`legacy-unscoped` 认领入口复用现有设置页，不新增页面。旧 `sylanne_embodiment_*` Persona 不自动删除，由用户在 AstrBot 中手动清理。

## 7. 投递、故障与恢复

当前消息的反应式回复必须经原 event 所属路径返回，因为该路径携带真实账号；发送前仍须通过对应 TurnDeliveryLease。Sylanne 不为反应式回复建立跨重启重试，因而进程崩溃后不会凭旧 event 自动补发。

主动或延迟投递进入持久 outbox。每项保存可序列化的 `BotDeliveryRef`，其中包含 BotRef、PersonaRevision、platform_id、self_id、SessionRef、目标地址、适配器能力、generation、有效期和唯一 `delivery_id`；不能持久化原 event 对象，也不能依赖当前顶栏、最后活跃账号或显示昵称重新选路。状态机为：

```text
pending -> claimed -> dispatching -> sent_confirmed
                   \-> failed_retryable
                   \-> outcome_unknown
pending/claimed    \-> suppressed | expired
```

状态变更与 outbox 落盘原子化，但外部发送不声称与本地事务原子。适配器能力决定恢复语义：

- `account_addressable_idempotent`：适配器接受 `delivery_id` 作为幂等键或可查询可靠 receipt；可安全重试至 `sent_confirmed`。
- `account_addressable_non_idempotent` 或经有效 `AdapterAccountProof` 的单账号通道：发送前先持久化 `dispatching`；崩溃、超时或确认丢失后进入 `outcome_unknown`，绝不自动重试。只有可靠 receipt 对账，或管理员明确接受潜在重复风险并创建新的投递意图，才能继续。
- `unavailable`：不调用外部发送，直接进入 `suppressed` 并保留原因。同一平台存在多个 Bot 而适配器没有账号级投递能力时必为此状态。

被抑制或结果未知的意图在 WebUI 显示“账号级路由不可用”或“投递结果未知”；它们不是可跨 Bot 转发的草稿。任何重试都重新验证 Scope、TurnDeliveryLease、当前 Persona、nonce、ResolvedPersonaRef、BotDeliveryRef、冷却和有效期。

Scope 校验、指纹匹配、快照写入、容量记账、outbox 状态迁移和临时上下文合并在各自本地事务内原子提交，失败不改变兄弟 Scope；外部投递只提供上述适配器能力所能证明的保证。损坏快照保留隔离副本，只允许同一 Scope 干净重建，禁止从兄弟 Scope 或 `default` 恢复。停止时先持久化在途状态并排空安全存档，再取消任务；重启按 outbox 状态恢复，不把 `dispatching` 当作未发送。Genesis 以 PersonaRevision 和 generation 幂等提交，重复计算结果只能有一个胜者。错误卡沿用既有场景语言，不得泄漏其他 Bot 的账号、Persona、会话文本或路由。

## 8. 验收矩阵与阶段边界

“支持多 Bot／多 Persona”只能在下列矩阵全部通过后宣称。每项同时覆盖单元、集成、并发、端到端、重启、取消、部分失败与对抗输入，并断言没有跨域的读、写、提示词、历史、清理或投递残留。

| 范畴 | 必须验收的场景 |
| --- | --- |
| 身份 | 同平台多 self_id、跨平台同 self_id、AdapterAccountProof 有效／失效、缺失／歧义 self_id；TransportSessionBinding 跨重启得到相同 SessionRef，冲突或代次错误 fail-closed。 |
| Persona | 同 ID 内容变化、不同 ID 相同内容、A→B→A 恢复、旧 Session 冻结引用、源档案缺失；PersonaManager `create/update` 调用数恒为零，`sylanne_embodiment_*` 永不作为输入。 |
| 隔离 | Bot／Persona／Session／Relation 交叉读写、同一用户面对不同 Bot、缓存碰撞、锁和队列竞争、重启恢复均不得越过完整路径；reset／purge／meltdown 不改变兄弟 Scope 的任何字节。 |
| 并发 | A 请求处理中启动 B 新轮次后，A 只能写回允许的 A 内部状态，最终投递被旧 TurnDeliveryLease 拦截且不记录“已表达”；陈旧后台任务、前端响应、SSE／WS 订阅均不能进入新 Scope。 |
| 上下文 | Genesis 仅产出五类先验；动态内容只能经唯一 TransientContextSink 的临时 TextPart，Provider 本轮可见但 prompt、contexts、历史和下一轮均不可见，且不能改变 system prompt。 |
| 界面与 API | 顶栏链路、唯一项自动选择、selectionEpoch 乱序回包、整卡路径、无观察角标、全父子路径与 nonce；scope-less REST 返回 410，SSE／WS 绑定 Scope；403／404／409 各自准确；独立服务器与 AstrBot Pages 契约一致。 |
| 旧数据与容量 | 旧数据只读与复制认领；迁移中断、重试、回滚不产生 dual-write 或二次导入；全局预算 0 为无限、默认 128 MB、manifest CAS、round-robin cursor、单次一关闭段到 90%、受保护数据导致的 budget_unsatisfiable 均可确定性验收。 |
| 投递与恢复 | 原 event 回程与 TurnDeliveryLease、经 AdapterAccountProof 的单账号通道、持久 outbox 状态机、幂等适配器安全重试、非幂等适配器 `outcome_unknown` 不自动重试、多账号无账号级路由时 fail-closed；发送前／后崩溃、确认丢失、过期 nonce 与恢复均保持边界。 |

阶段性准入只表示已获完整矩阵保护的 Scope 可以开放；未覆盖组合保持禁用或只读。身份、上下文、API、容量、投递、异常和并发恢复的全矩阵尚未全部通过前，产品、界面、文档与运行日志均不得宣称“已支持多 Bot／多 Persona 完全隔离”。

这份契约的底线是：每一次角色登台都有自己的舞台编号、剧本版本与场景存档；灯光暂落不会留下伪造记忆，幕布再启也绝不会把另一座舞台的台词送错人。
