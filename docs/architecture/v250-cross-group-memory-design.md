# v2.5.0 跨群记忆设计文档（旁挂人核 Sidecar Person-Core）——实现契约

状态：设计经 fable 终版（旁挂人核 v2）+ opus 红队复核（D2 命门）+ fable 对两个开放决策（D2/D4）的最终定夺，三轮收敛。本文是**整理稿**，忠实素材、未加码、未替素材做新决策；唯一的新增内容是把 opus 红队对 D2 三写入点身份取值的证伪，落成一条不可绕过的实现前置约束（§8 B1）。

范围：本文覆盖 v2.5.0"跨群记忆"整体方案——记忆货架、关系/人格跨群、瞬时情绪跨群、隐私下限、多档开关、备份与可逆、blast radius、分期、工作量、开放决策。所有 file:line 对照 `G:/Sylanne-241-hotfix`（只读勘察对象）+ AstrBot 4.25.1，由 fable 终版逐条现场核实（详见 §0 核实记录）；本文不重新核实，只整理呈现。

分支：本文写入时当前分支 `feat/embodiment-2.5.0`。写完不提交，留待用户审阅拍板。

用户已拍板的基调（写作起点，非本文结论）：范围＝开关全给（scope owner/all，默认 owner 起步，部署者可拧）；内容＝对话记忆＋关系人格＋瞬时情绪都跨；可配置多档、可回退；工程底线＝打开前强制全量 KV 快照备份、召回外露留安全阀。

---

## 0. 素材核实记录（背景，非本文新增工作）

fable 终版对所有承重 file:line 逐条现场核实，重点验证"生死判定"——招牌修复 W0 净化双摘要是否真的做得到。核实结论：做得到，方向成立。关键核实点：

- 写侧融合真实存在：`_fmt_msg` 把 `group_observed` 拼成 `"[群聊背景|sender]: text"`（llm_request_pipeline.py:2401-2405）→ 融进单段 `conv_text`（:2407）→ 单次 LLM 摘要（:2424）→ 单次 `write_summary`（:2458）。别人的话确实在写入点之前已被熔进本人摘要。
- 但 `msgs = buf.drain()`（:2392）保留了每条的 `role` 字段：:2410 现成 `has_context` 判定、:2429-2430 fallback 已按 `role∈{user,bot}` 过滤。故在同一函数内取 user/bot 子集重建 `conv_text'` 单独重摘进货架（W0）技术上成立——这是 fable 相对红队原判的关键翻盘。
- `write_summary` 缺 privacy 默认 `"open"`（memory_system.py:1276），融合条目确实是 open 档、含第三方，红队所指污染条目真实存在；`_normalize_privacy_level` fail-closed（缺→open、非法→internal，memory_system.py:73-88），ShelfItem 归一形态有蓝本。
- `format_recall_injection` 出口（:2890）原文"化进话里自然带出"是 R4 要对冲的逆风指令；`MemoryResult` 无受众/origin 字段——故货架注入必须自立门户，不能改 `format_recall_injection` 出口。
- `validate_session_isolation` 只用 `id()` 查 kernel/memory_system（session_context.py:344-400），旁挂存储在其监控盲区，属实承认的缺口。
- `session_key={base}:{sender_id}`，空 `sender_id` 群聊回落 `base`（session_context.py:588-593）——塌缩桶真实存在；`rel_register` 总把 `sender_id` 更新为最新认证值、仅非空才更新（rel_register.py:84-88）——塌缩桶被钉成 owner 的机制真实。
- `delete_sylanne_memory_state`（state_persistence.py:1954-1961）是 meltdown / AstrBot 删会话 / WebUI purge 三路汇合的规范删除原语，旁挂层级联落点在此。
- `MEMORY_KV_KEYS_MANIFEST` 要登记新键否则 golden 测试红（memory_migration_spine.py:139-162）。
- `relationship_layer` 是单全局 blob + owner 硬门 fail-closed（relationship_layer.py:37,72-82），romantic 判定不受 profile 污染。
- `range_get_async` 是 AstrBot 框架内部 API（shared_preferences.py:58-68），本插件从未调用过——备份走它是越契约，风险需文档标注。
- 配置零 object 约定属实：`_conf_schema.json` 全表 27 bool / 17 string / 4 int / 2 float，无 object/list；`owner_id`（:296）、`recall_mode`（:140）、`life_simulation_share_intensity`（:233）是现成的多档 options 先例。

一句话：fable 终版没有脑补，招牌 W0 修复经得起核实，方向可采信。

---

## 1. 方案总纲：旁挂人核 v2

**推荐：采用"旁挂人核 v2"。** `session_key` 一个字不改、per-session 物理隔离与 MEM-01/02 数据安全链零触碰；跨群靠两个按身份（`platform+sender_id`）挂的旁挂存储——记忆货架（PersonShelf）+ 人格档案（PersonProfile）——读侧多道 fail-closed 硬闸，写侧净化双摘要在进货架前物理剥离第三方旁观内容。这是三方案里唯一不需要改主键、不需要抽 subject_ids、不需要群名册、不需要重写隔离诊断的路，可逆性和备份底线也最硬。

### 1.1 主动砍掉的四样（换可控性，刻意收窄非疏漏）

| 砍掉的东西 | 换来什么 |
|---|---|
| 不合并大脑：跨群对话记忆只做"货架召回注入"，不做 per-session 归档合并、不长成跨群图谱 | 完整可逆 + fail-closed 链零重写 |
| 旁观者内容（group_observed，别人在群里说的话）永不进任何货架 | 这恰好就是隐私命门②本身，砍它＝达标不是妥协 |
| 瞬时情绪（hot_pool / `_affect_debt` / 29 维向量）绝不跨；只跨 warmth 长期基线一个标量（后经 D2 定夺放宽，见 §4） | "A 群吵完 B 群还在气头上"是迁怒不是记得你 |
| Embodiment Five 深层特质本期不跨，留到 2.6.0 与 E 核同片 spine 一起动 | 砍掉最大一块复杂度；表层 Sylanne Six 足够承载"她对你气质一致" |

保留的用户原意：全员档在（scope=all 拧一下就到）、对话/关系/人格三类都跨、多档可回退、强制备份、召回安全阀——五条拍板全兑现，只是默认档保守（owner + same_group + 默认全关起步）。

### 1.2 记忆主键与旁挂层

- **主键不动**：`session_key` 派生（session_context.py:588-593）、per-session 容器（session_state_store.py:131）、KV 键 `sylanne_memory_state:{safe}`（state_persistence.py:387-390）、MEM-01/02 全链（`_hydrated` / `_refuse_unhydrated_overwrite` / 咽喉印章 / CRC 备份 / quarantine）——零变化。
- **跨群 = 两个 identity-keyed 旁挂存储**：
  - **(A) 记忆货架 PersonShelf**，键 `sylanne_person_shelf:{platform}:{sender_id}`（platform 取 UMO 首段防跨平台撞号）。终版关键：货架条目**不复用** `MemoryItem`，在 `person_shelf.py` 内定义独立 `ShelfItem` dataclass（`text` / `origin_scope` / `origin_id` / `created_at` / `weight` / `schema_ver`），自带 fail-closed 归一（缺 origin → private 最严档，仿 `_normalize_privacy_level` 形态 memory_system.py:73-88）。收益：per-session `MemoryItem`/`to_dict`/`from_dict` 完全不动，主档 schema 与回滚地板不抬高，`memory_system.py` 整文件零改动。
  - **(B) 人格档案 PersonProfile**，键 `sylanne_person_profile:{platform}:{sender_id}`：关系四计数 + weight/phase、Sylanne Six 快照、warmth 长期基线标量、`transient_affect` 小块（§4）。
- 两类新键必须登记 `MEMORY_KV_KEYS_MANIFEST`（memory_migration_spine.py:139-162），否则 `test_memory_golden_roundtrip` 红。
- 写入落点：融合摘要函数内（llm_request_pipeline.py:2392 drain 后）走 W0 净化支路双写货架；召回落点：`_prepare_memory_context`（:1532）加并行货架支路。`MemorySystem.recall`（:1798）签名不动，SDK `RecallCapability` 无感（守 Phase G 不改 SDK + 冻结对外集成面）。
- origin 标注确定性来自写入时 session UMO（私聊 UMO → private、群 UMO → `group:G`），不做任何内容推断。

---

## 2. 记忆货架与得体性门控规则表

写侧 5 条 + 读侧 6 条，**全部是 fail-closed 硬闸，不是评分维**——这一句是整个方案的立身之本（见 §5 对 D4 的裁决逻辑）。

### 2.1 写侧门控（W0-W4，本轮相对初版最大升级，封堵"写侧融合"地基洞）

- **W0 净化双摘要【核心机制】**：货架不用主摘要；在同一函数内取 `role∈{user,bot}` 子集重建 `conv_text'`，单独跑一次 LLM 摘要进货架。`has_context=False`（私聊天然、无 group_observed，:2410 现成判定）时直接复用主摘要，零额外成本——额外 LLM 调用只发生在"开跨群 × 群聊 × 确有旁观内容"的交集。净化摘要失败/空/触发内容过滤 → 该轮不进货架（fail-closed），绝不回落已融合的主摘要。金样对抗用例＝"张三离婚"场景（P 与他人在群里谈论第三人隐私，货架必须只留 P/bot 直接对话内容）。
- **W0b 出口哨兵**：货架文本残留 `"[群聊背景|"` 或命中本群 `shadow_buffer` 近期 sender 名单 → 拒收（冗余断言防回归）。
- **W1**：只有 bot↔P 直接对话进 P 货架（现由 W0 构造保证，不再是空口声称）。
- **W2**：缺 origin 归一 private 最严。
- **W3**：主摘要若走融合路径（`has_context=True` 且净化失败），per-session 主档条目照旧、货架侧标记该轮跳过。
- **W4**：空 `sender_id` 拒写（三写入点逐点封堵）。**重要：W4 的可执行性在 D2 场景下被 opus 红队证伪，实际落地方式见 §8 BLOCKER B1，本节描述的是设计意图而非可直接实现的机制。**

### 2.2 读侧门控（R1-R6，六条硬闸）

- **R1 身份闸**：P 的货架仅当当前发言人 `platform+sender_id` 双匹配 P 才被查询——把"在场判定/subject 抽取/群名册"三个无地基新造件整个消解（`get_group().members` 仅 OneBot、`RoleDetector` 死代码、`shadow_buffer` 非名册）。
- **R2 私聊闸**：`origin=private` 仅在与同一 P 的私聊放行，群一律 drop。
- **R3 跨群闸**：`origin=group(G)` 在 G 恒放行、他群按 tier 档、与 P 私聊恒放行。
- **R4 场合标记**：货架注入是独立代码路径、自带 formatter 与注入块，块内自带反向指令（"以下是你在别的场合的记忆，表达收敛、别当谈资、涉及他人的事不主动展开"）对冲 :2890 那句"自然带出"。D4 裁决后追加一句显式的"涉及第三方的私事不复述、不外传"（§5）。
- **R5 双闸冗余**：货架查询处过一次、注入组装处再校验一次，任一层异常 → 空召回。
- **R6 提及降级**：条目文本命中该 origin 群其他已知 sender 的 → 锁死仅原场合可见。**默认启用范围经 §8 B6 修订，非 fable 原案的 strict-only opt-in**。

---

## 3. 关系与人格跨群（出生播种 + 落盘软同步）

拒绝共享活体 kernel/spine，改用"出生播种 + 落盘软同步"的 KV 小 blob，唯一合并点在落盘钩子内。

- **(1) 关系态**：`body.memory["relationship"].signals` 四计数（body.py:519-524）per-session 照常累积；kernel 落盘钩子把计数 element-wise max 合并进 PersonProfile；host 出生（session_context.py:1037 邻域）时若 profile 存在且档位允许则播种。`body.py:552` "session_local" 契约文案改写为"session_local 累积 + person 级播种"。
- **(2) 人格**：Sylanne Six 落盘时指数混合写 profile，出生时用 profile 值替代 `initial_personality` 重播种（personality.py:704 种子逻辑仅在无 profile 时走）；播种前 clamp 合法区间，profile 损坏 → 回退默认播种（fail-closed）。Embodiment Five 本期不跨（D3，见 §12）。
- **(3) romantic 亲密类型层零改动**：`relationship_layer` 本就单全局 blob + owner 硬门（relationship_layer.py:37,72-82），不受 profile 污染——scope=all 下骚扰者刷好感影响不了亲密判定，这是 all 档的重要兜底。
- **身份取值（设计意图，见 §8 B1 的可执行性修正）**：跨群层意图上"一律取当前 event 实时 sender_id，绝不信任 `rel_register` 钉住的 sender_id"（rel_register.py:84-88 对跨群层不可见不采信）；塌缩桶因实时 sender_id 为空理应在三写入点被 W4 拒绝。**这一整段是 fable 原案的设计意图；opus 红队复核发现三个实际写入点在代码结构上拿不到实时 event，此意图不能照原文实现——必须先落地 §8 B1 的"已认证实时 sender 暂存层"，三写点才有东西可读。**
- **并发**：唯一合并点在落盘钩子内，新增 per-person `asyncio` 锁只护 profile/货架读改写，per-session 锁体系（session_context.py:600-625）不碰；播种只在出生一瞬，运行中不实时双向同步——双群并发漂移落盘后混合＝可接受最终一致，成文防后人当 bug 修。

---

## 4. 瞬时情绪跨群（D2 最终形态）

D2 原始草案立场是"情绪只跨 warmth 长期基线一个标量，瞬时态绝不跨"。fable 复核后**签字放宽**为 per-person 受限形态——理由：per-person 构造把"迁怒"锁死在张三自己的 profile 里，这不再是迁怒，是"记得对这个人的心情"。以下是最终能签的形态。

### 4.1 签什么、不签什么

只签"body 通道的有界播种"，不签引擎深层状态跨群。

**存什么、从哪取**：PersonProfile 新增 `transient_affect` 小块，6 个字段：

- `warmth_transient`：= 当前 `body.temperature.warmth` 减去 profile 里的 warmth 长期基线（存"偏离量"，天然不与基线重复计账）。来源：`temperature.warmth` 是七级温度词真模型标定过、证实能到达行为的唯一通道（定义 compute/body.py:132-141 默认 0.45，state_vector 导出 body.py:355，`apply_vector_delta` 写入且 clamp body.py:466-468；事件响应 vector.py:106 safe+0.05/hurt-0.05）。
- `volatility_transient`：来源 `body.temperature.volatility`（body.py:142,:356,:469-471）——承载"情绪还没平"的那部分质感。
- `valence` / `arousal` / `tension`：来源计算脊柱 8 维情感 kernel `computation.engine.observe()`（void_scar_engine.py:267-287 返回 warmth/arousal/valence/tension/...；kernel 侧取用先例 kernel.py:615-622 `_computation_emotion_overlay`，遥测取数先例 kernel.py:960-972）。**P0/P1 只存不施加**（shadow 观测用），原因见下方"不签清单"。
- `last_interaction_ts`：墙钟时间戳，衰减结算锚点。

写入点：与 profile 软同步同一落盘钩子（`state_persistence` 落盘钩子，§9 触点已有，零新增触点）；写入时先把旧 transient 按墙钟衰减到 now，再与新观测 EMA 混合（α=0.5），防陈旧尖峰复活。身份规则完全复用 W4/实时 sender_id（见 §8 B1 的落地修正）。

施加点：host 出生播种处（session_context.py:1037 邻域，与关系计数/Sylanne Six 播种同点同档门）；施加形态＝对 `body.temperature.warmth` 和 `temperature.volatility` 各打一个**有界 delta**，走 `apply_vector_delta` 既有 clamp 路径（body.py:466-474），|delta| 硬帽 ±0.15。

### 4.2 衰减律：指数衰减 + 进新会话即结算，无后台时钟

```
transient(now) = transient₀ × 2^(−Δt / T½)，Δt = now − last_interaction_ts
```

- `warmth_transient` 半衰期 4h；`volatility_transient` 半衰期 90min（唤起类消退快于效价类，与引擎已有沉默分带 5min/30min/2h 的量级一致——墙钟先例 void_calculus.py:52-59，`SilenceTexture` 就是按 silence 秒数分带的，引擎里用墙钟不是新发明）。
- `|transient| < 0.02` 视为归零，播种跳过。约 24h 后自然回到纯基线。
- 选"读时结算"而非后台 tick 的理由：2.6.0 前置核查已定论本系统**无真实 idle 时钟**，所有 tick 都是消息驱动的（`hot_pool` 衰减也是 per-tick 非 per-秒，hot_pool.py:674-679）——后台衰减线程是无地基新造件，读时结算零新增运行时。
- shadow 期用观测数据标定半衰期再定死，这两个数字进配置注释不进开关（不加键）。

**红队诚实纠正（必须写清，避免误导后人）**：长停机（Δt 巨大）是安全的——`2^(−巨大)` 浮点下溢趋近 0，不像 2.4.1 的 `rhythm_ema` 会炸（那是逐 gap 相加）。真正危险的只有 `Δt < 0`（时钟回拨/跨机备份恢复到慢钟）与 NaN。墙钟当指数衰减乘子是本系统全新形态——引擎既有墙钟只做阈值比较（如 void_calculus.py:52），hot_pool 是 per-tick 有界增量，两者都不是"墙钟差值喂进指数衰减公式"。正因为这是新形态，§8 B2 的边界护栏是新增必需，不是过度设计。

### 4.3 护栏与分工

- 与 warmth 基线不打架：基线＝慢 EMA（天级），transient＝存"偏离基线量"，播种值＝基线 + 衰减后 transient，transient 衰减到零即纯基线——数学上不可能重复计账，交接连续无跳变（实现须满足 §8 B4）。
- scope=all 刷情绪：爆炸半径被 per-person 构造锁死为"她对刷子本人的态度"——这是保真不是漏洞（你对她一直凶，她对你冷，应该的）；量上有四道闸：EMA 混合（单次对话最多拉一半）、|transient| 存储帽 ±0.3、施加帽 ±0.15、更新只发生在 flush（对话批粒度，无法高频打点）。romantic 亲密判定照旧不可触（relationship_layer.py:37,72-82 owner 硬门）。
- 开关归属：并进现有 `cross_relationship`（与 warmth 基线同一个语义通道＝"她对你的温度"），不加第 7 个键，守零 object/最小键数约定；开关 description 写明含瞬时。
- shadow 观测：播种点在 shadow 档落一条 `{person_hash, Δt, 衰减前/后值, would-apply delta}` 不施加；观测两周看分布再拨 on（与 §10 P0 shadow 窗口共用，不加周期）。
- **实现必须处理的一个坑**：LRU 驱逐重建（session_context.py:1018-1030）会让同 key host 会话中途重生——播种必须加守卫，**仅当 `profile.last_interaction_ts` 晚于该 session 已恢复 kernel 的最后活动时间才施加**，否则驱逐重建会把已衰减的旧情绪重复叠进恢复出的新状态，变成自激（此坑的结构化解法见 §8 B3）。
- 双群并发：两会话播同一 transient 是语义正确（她对 P 的心情本就应两处一致）；回写走既有 per-person 锁 + EMA 最终一致（§3 已接受，不新增机制）。

### 4.4 不签清单（明确边界）

- **不签** hot_pool 任何状态跨群：材料/温度/压力/级联/坍缩（hot_pool.py:274-370）一律 per-session。级联期漂移 10 倍（hot_pool.py:980-990）、坍缩不可逆改写人格特质（hot_pool.py:795-883）——让 A 群的吵架材料在 B 会话触发人格坍缩，是把不可逆相变跨会话传染，不是情绪连续感，是结构性事故。用户要的"气头上"由 `volatility_transient` + 收窄后的 `warmth_transient` 承载，足够。
- **不签** `wound.open`/`scar` 跨群（body.py:153-167）：创伤通道接 `hot_pool.ingest_wound`（hot_pool.py:1005-1037），跨了等于绕道把材料送进热池。
- **不签（本期）** valence/arousal/tension 直接施加进脊柱 `ScarredState` 维度：脊柱情感是 8 维耦合动力系统（void_scar_engine.py:8-9），外部直写单维会破坏耦合不变量，且 2.6.0 双速情感动力学（E 核）正要重造这一层——现在动是给三个月后的自己埋雷。P0/P1 只存不施加，2.6.0 E 核落地后按新动力学决定是否升格为直接播种（存储字段已就位，升级零迁移）。这三维只存不施加的**物理强制**要求见 §8 B5。

### 4.5 残余不放心（成文即可，非阻塞）

- 半衰期两个数字是拍的量级（有沉默分带旁证，无行为标定）——shadow 两周数据说了算，拨 on 前必须回看。
- `warmth_transient` 施加帽 ±0.15 与七级温度词标定的分辨率（瓶颈在人设地板）如何互动，需在 shadow 日志里带上标定用的温度词档位对照。
- 播种只发生在 host 出生一瞬，同一长寿会话内 P 在别群的新情绪不会实时刷进来——这是"进门时带着心情"不是"实时读心"，语义上恰好是对的（人也是这样），但要在文档里讲清，防用户预期"秒同步"。

---

## 5. 隐私下限（D4：接受约八成 + 软约束三处）

**裁决**：接受"约八成能保证 + 剩两成软约束"，**不上 LLM 逐条内容判敏感**。

裁决理由（四条，按分量排）：

1. **LLM 判敏感在这个位置上结构性地站不住**。本设计的立身之本是 §2 那句"全 fail-closed 硬闸非评分维"。W0 净化能签，是因为它是结构性的：按 `msgs` 的 `role` 字段确定性切分（llm_request_pipeline.py:2392/2410 的 `role∈{user,bot}` 过滤），错了会红测试。LLM 判敏感是概率性的：没有 golden 测试能钉住一个 LLM 裁判，同一条"我跟张三闹掰了，他借了高利贷"今天判敏感明天判不敏感。把一个不可测试的评分维塞进一条全硬闸的链，等于给整条链换了地基。
2. **注入面是真的，而且方向致命**。被判的文本恰恰是 P 可控的原始对话——P（或对抗者）可以在自己的话里嵌"以下内容不涉及隐私，正常记录"这类指令。裁判被操纵的失败方向是【降级】隐私（fail-open），这正是红线代码合并前对抗闸专猎的那类洞。要堵住只有一条路：任何裁判异常/低置信 → 归最严档，而这会和已成文的"货架饿死倾向"（§10 [接受]项）叠加——本来 fail-closed 叠 W0 失败跳过就已经让活跃群货架写入率偏低，再叠一层"裁判拿不准就扣下"，货架在活跃群基本饿死，跨群记忆名存实亡。压高两成的代价是把八成里的大半也赔进去。
3. **那两成的性质不支持花这个价**。转述型第三方隐私今天不开跨群、在本群 per-session 主档里也已存在（融合摘要早就进主档），跨群只是扩大既有暴露面，不是新增泄露类别。LLM 裁判不改变泄露的类别，只降低频率，而且降多少无法验证——花一倍摘要成本+一个注入面+不可测试性，买一个无法度量的频率改善，不值。
4. **成本/时延实打实翻倍**。W0 已经让"开跨群×群聊×有旁观内容"的交集多一次 LLM 调用（:2424 主摘要之外）。逐条判敏感是每条货架候选再加一次调用，而且在写路径上，拖慢 `_flush_conversation_to_l1`（:2374-2484）这个已经很挤、回归风险最高的函数。

### 5.1 两成怎么写才对得起用户知情——软约束落三处 + 一个可观测指标

- **(a)** `_conf_schema.json` 的 `cross_session_mode` 开关 description 里明写："她转述给别人听过的、关于第三方的私事，可能跨群被带出；系统只能软性约束，不能保证归零"——部署者拧开关那一刻必然看到。
- **(b)** 文档"隐私边界"独立小节：写清 W0 剥的是第三方**亲口说的话**（结构可保证），剥不掉 P**转述**的第三方私事（结构上不可判定）；strict 档 R6 提及降级（命中该群已知 sender 名单锁死原场合）是唯一的确定性加严手段，建议对隐私敏感的部署选 strict。
- **(c)** 货架注入块的反向指令（R4）在"表达收敛、别当谈资"之外加一句显式的"涉及第三方的私事不复述、不外传"——这是运行时软约束的落点（已并入 §2.2 R4）。
- **(d) 可观测**：shadow 期在观测日志里统计 R6 启发式命中率（条目文本命中其他已知 sender 的比例），让部署者看到"含第三方提及"的真实占比，而不是拿"约八成"这个拍脑袋数字过日子。

**留一个不阻塞的钩子**：若未来确要压更高，可在 strict 之上加可选档——LLM 只判"已净化后的摘要"（非原始对话，注入面小一个量级）、判定异常一律丢弃该条（fail-closed 方向，绝不降级放行）、且只做写侧一次性判定。本期不做，写进"未来加严路径"即可。

---

## 6. 多档开关（6 个扁平键，遵项目零 object 约定）

| # | 键 | 取值 | 默认 | 说明 |
|---|---|---|---|---|
| 1 | `sylanne_alpha_cross_session_mode` | `off` / `shadow` / `on` | `off` | shadow 档：货架照常写入（含 W0）、闸照常算，只拦注入并落观测日志 |
| 2 | `sylanne_alpha_cross_session_scope` | `owner` / `all` | `owner` | all 档保留（用户拍板），3b 对抗残余显式标注（§12） |
| 3 | `sylanne_alpha_cross_dialogue` | bool | `false` | 对话记忆跨群 |
| 4 | `sylanne_alpha_cross_relationship` | bool | `false` | 关系计数 + warmth 长期基线 + `transient_affect`（D2 并入，不新增键）跨群 |
| 5 | `sylanne_alpha_cross_personality` | bool | `false` | Sylanne Six 跨群 |
| 6 | `sylanne_alpha_cross_visibility_tier` | `same_group` / `cross_group` / `strict` | `same_group` | 读侧 R3/R6 档位 |

- shadow 档保证："货架是读时过滤 + `ShelfItem` 带 `schema_ver` + 缺字段归一最严"，存量条目拨 on 后自动受同一套读闸管辖，不存在"存量绕闸"；拨档时仍强制跑一次存量字段完整性扫描 + 归一作廉价保险。
- 四档不完全正交，诚实标注：关系计数本从对话累积，关 `cross_dialogue` 不等于对话信息零跨群，是语义事实非 bug。
- **开启前置强制**：`mode` 首次离开 `off` 前自动执行全量 KV 快照，快照失败或备份 API 探测失败 → 拒绝启用并落日志（详见 §7）。

---

## 7. 可逆与备份

- **零迁移启用**：不改 `session_key`、不动 per-session 键、`MemoryItem` 零字段变化，无 orphan / 表观清零风险。历史记忆不回填——旧条目无 origin 可标，她跨群记得的只是开关之后的事。
- **关闭语义**：`off` = 停读停写旁挂层，货架召回只进 prompt 注入、从不写回 `MemorySystem`，行为立即回退 2.4.1 基线。**但已施加的 delta 不可自动撤销，见 §8 B7 的诚实说明与结构化改进方向。**
- **全量备份**：唯一真全量 = `range_get_async("plugin", plugin_id, None)`（越 `plugin_kv_store` 契约的框架内部 API，AstrBot shared_preferences.py:58-68，本插件从未用过），封装独立备份模块，dump 到带时间戳磁盘分片文件、CRC32 校验、pin 4.25.1、启动探测该 API、探测失败则跨群整体拒绝启用。（`_known_sessions` 枚举缺口 + 文件名 sanitizer 与 KV 键 `:` 处理不一致已证死路不走，不作为备选方案。）
- **purge 一致性**：`delete_sylanne_memory_state`（state_persistence.py:1954-1961）、meltdown、`/api/purge_data` 三路全部扩展——`ShelfItem` 带 `origin_id`，per-session purge 时按 `origin_umo` 级联清除货架内该会话来源条目；另提供 person 级 purge（整桶删 shelf+profile）；`bump_epoch` 的 pending-delete 语义为旁挂层建等价物。**`transient_affect` 三个只存不施加维度（valence/arousal/tension）与 warmth/volatility transient 一并纳入此级联，见 §8 B5。**

---

## 8. 实现前置硬约束：7 个 BLOCKER

**本节是红线专节。以下 7 条在实现前定死，不许留给写代码阶段自由裁量；任何一条未落地，对应功能不得合并。**

### 背景：opus 红队对 D2 三写入点身份取值的证伪

fable 终版 §3/§4 描述的"跨群层一律取当前 event 实时 sender_id，绝不信任 rel_register 钉住值，塌缩桶因实时 sender_id 为空在三写入点全被 W4 拒绝"是**设计意图**，但 opus 红队复核发现：这句话在代码里做不到。

三个实际写入点的执行上下文全无 `event` 对象：

- **货架写**（`_flush_conversation_to_l1` 后台刷新循环，llm_request_pipeline.py:2374/2499）
- **profile 软同步**（`persist_kernel`，state_persistence.py:417）
- **出生播种**（`host()`，session_context.py:994/1037）

三点都拿不到实时 `sender_id`。可用的替代信息只有两种，且都不安全：解析 `session_key`（塌缩桶 base 带冒号 → 把群号当 sender）；或读 `rel_register` 钉住值（rel_register.py:84-88 → 匿名塌缩桶认成 owner → 陌生人情绪串进 owner profile）。读侧 R1 可救（`_prepare_memory_context`:1532，调用方 :1248 有 event 可下传），**写侧三点结构性做不到**。

以下 B1-B7 是对这个命门以及连带发现的其余安全洞的定死处置。

### B1（红线）三写入点新增"已认证实时 sender 暂存"层

有 event 的路径（消息处理主流程）按 `session_key` 暂存非空的已认证 `sender_id`；三个写点（货架写 / profile 软同步 / 出生播种）只读该暂存值，读不到即 SKIP。**禁止解析 session_key、禁止读 rel_register 钉住值**。落地前必须证明：塌缩桶路径（空 sender_id 群聊回落 base）走这条暂存层时零写入——即塌缩桶场景下暂存值本身就应为空或不存在，任何"从别处兜底出一个值"的实现都是回到红线前的错误状态。

### B2（红线邻接）transient 载入加固

- `transient_affect` 各字段 + `last_interaction_ts` 走 `_finite_float` 式的显式有限性检查（仿 archive.py:26 拒 NaN/±inf 的形态），**不许用** `_opt_float`（emotion.py:332）——`_opt_float` 放行 NaN 会把档案永久钉在 `warmth=0.0` 最冷、跨所有会话、只能手动 purge 恢复。
- `Δt = max(0.0, now − last_interaction_ts)`：下限截断，防时钟回拨放大衰减结果。
- 衰减 + EMA 混合计算完成后，结果都要**重新钳** ±0.3（存储帽）——不是只在写入时钳一次就假设后续计算维持不变量。
- `last_interaction_ts` 为 `None` 时跳过播种，不得因此抛 `TypeError`。
- 非有限值（NaN/inf）必须**显式判定归零**：不能依赖 `abs(nan) < 0.02` 这类隐式判断——NaN 参与比较恒为 `False`，这种写法抓不住非有限值,必须先做 `math.isfinite()` 式的显式检查再判是否归零。

### B3 幂等播种

kernel/host 存 `last_applied_transient`。（重）播种时，实际施加量 = 当前衰减后的 transient 值 − 已施加值，**净施加恒等于"当前衰减值"，不是历史施加值的累加**。这是为了防止 LRU 驱逐-重生之间跨会话更新叠加击穿 ±0.15 的单次施加预算（若不做此约束，累计可达 +0.30，突破设计帽两倍）。

### B4 基线不污染

慢 EMA 基线的输入必须剔除已施加的 transient（即采样"去种后"的 warmth，而非采样播种后被 delta 污染的 warmth）。实现须定义"flush 内 transient 计算"与"baseline 计算"的先后顺序并冻结为基线快照——防止基线随 transient 反复施加单调上爬，形成不可逆漂移（这一族 bug 与 2.4.1 的漂移类 bug 同源，是本次设计要刻意避免复刻的模式）。

### B5（红线）purge 级联覆盖 transient 三维 + 物理拒绝播种

`valence`/`arousal`/`tension` + `transient_affect` 整个小块必须纳入 person 级 purge 级联和 per-origin purge，由 `delete_sylanne_memory_state`（state_persistence.py:1954）覆盖。这些字段会落明文磁盘备份（`range_get_async` dump）——这是 2.4.1 没有的静态隐私面，**必须在文档中标注**。

此外：`valence`/`arousal`/`tension` 在本期设计里是"只存不施加"（§4.4），这个约束不能只靠"代码里没写调用"来保证——必须有**硬 assert**（E 核前的播种路径物理读不到这三个字段，assert 失败即崩溃而非静默跳过）+ 对应测试，防止未来有人在 2.6.0 E 核落地前"顺手"把这三维接上播种路径，造成静默翻转（从"只存不施加"变成"存了就施加"且没人注意到）。

### B6 R6 提及降级默认范围修订

R6 提及降级对**任何高于 `same_group` 的 tier**默认开启（即 `cross_group` 和 `strict` 都默认启用 R6），**不是 fable 原案 D7 的"strict-only opt-in"**。文档必须写清：跨群场景下第三方转述＝**方向性升级**——`cross_group` 把 P 转述的第三方秘密路由向"该第三方社交圈更可能在场"的群，比原本只在 confiding 群内流转更危险，这不是"同类别信息换个地方更宽松地流转"，是实质性提高了被转述对象在场识别自己被谈论内容的概率。

### B7 off 档诚实语义

已施加的 ±0.15 delta 在施加那一刻就已经烘进 per-session kernel 快照并落盘。关闭跨群情绪（回到 off）**只停止新播种，不回撤已施加的量**；没有 idle 衰减，只有"继续活动"时（因为衰减是读时结算，见 §4.2）才会自然收敛回基线。

两种可接受的处置，二选一，实现前必须定：

- （文档兜底，最省事）明确写清"续活动才自愈、磁盘快照残留至再激活"，作为已知限制。
- （更好，依赖 B3 的 `last_applied_transient`）关闭时主动执行一次性回撤：用 `last_applied_transient` 记录的已施加值，对 body 当前状态做一次反向 delta，抵消已施加量，使 off 的行为观感上更接近"立即停止影响"而非"残留到下次活动"。

两种处置都必须在用户可见文档中说明选择的是哪一种，不能让"off"这个词在两种实现下产生不同语义却不加区分。

---

## 9. Blast Radius

改动面（终版比初版更小：`memory_system.py` 从"改出口"降为零触碰）：

- **新建 3 模块**：`person_shelf.py`（`ShelfItem` 类型 + 存储 + 读侧双闸 + 容量淘汰 + 一致性自检）、`person_profile.py`（播种 + 合并 + per-person 锁）、备份工具模块。
- **触点 8 处**：llm_request_pipeline.py 摘要函数内加 W0 净化 + 货架双写（:2392-2463 一个函数内）、`_prepare_memory_context` 加货架支路（:1532/:1669）、session_context.py:1037 邻域出生播种、state_persistence.py 落盘钩子 profile 软同步 + purge 三路级联、`_conf_schema.json` 6 键、`MEMORY_KV_KEYS_MANIFEST` 登记、webui 最小观测端点（可后置）。
- **明确不碰**：`session_key` 派生、30+ SessionMap、per-session KV 键与 MEM-01/02 链、`memory_system.py` 整文件、`MemorySystem.recall` 签名、SDK/`RecallCapability`/`public_api`/大饼桥、`validate_session_isolation`、per-session 锁、spine/Embodiment Five、`relationship_layer`。
- 回归风险集中在 `llm_request_pipeline` 的摘要函数与注入函数两处，其余全是新代码新测试。

---

## 10. 分期 P0-P2

每期合并前照红线惯例过对抗闸专猎 fail-open。

- **P0（最小可用且安全，先做）**：三模块 + 八触点 + 全默认关 + 备份 + purge 级联 + §8 全部 7 个 BLOCKER 落地，shadow 档实机跑两周看观测日志。此期即便全部上线，因默认 off，对现网行为零影响。
- **P1**：owner + same_group + on，开 dialogue/relationship/personality 三开关。
- **P2**：视 P1 实机表现再开 cross_group tier 和 all 档。

测试面：读闸六规则 × 三上下文全矩阵、W0 净化（张三离婚金样对抗用例）、W0b 哨兵、空 sender_id 三点拒绝（须验证 §8 B1 的暂存层而非旧的"直接判空"设计）、purge 级联（含 transient 三维，§8 B5）、播种 clamp（含幂等性，§8 B3）、备份完整性、shadow→on 扫描。预估新增 80-100 个测试。

**接受项（成文防误修，非缺陷）**：

- 双群并发漂移落盘后混合丢少量增量，量级小于单次 tick 步长。
- fail-closed 叠 W0 净化失败跳过 → 活跃群里货架写入率明显低于主档，这是安全侧代价；shadow 期观测写入率，过低再调净化重试策略而非放松闸。

**监控缺口（成文）**：货架/档案在 `validate_session_isolation` 盲区（:344-400 只查 kernel/memory_system 的 id），模块内自检 + 文档标注，2.6.0 若动诊断再收编。

---

## 11. 工作量估计

难点集中在四处（不是代码量大，是安全正确性苛刻）：

- **(a) W0 净化支路**：要在一个已经很挤的摘要函数（`_flush_conversation_to_l1`，:2374-2484）里插一条净化支路，且失败必须 fail-closed 跳过而非回落污染主摘要——净化摘要多一次 LLM 调用的成本/时延/内容过滤分支都要处理。这是回归风险最高的一处。
- **(b) 三写入点的空 sender_id 逐点封堵（今已知需按 §8 B1 的暂存层重做）**：漏一处即身份桶合并泄露，必须逐点测试覆盖。
- **(c) 备份越契约**：调框架内部 `range_get_async` 做全量 dump + CRC + 分片文件 + 启动探测拒开，是全新且脆的一块（框架升版即破）。
- **(d) purge 三路级联 + epoch 等价物**：`ShelfItem` `origin_id` 级联 + person 级整桶删 + pending-delete 等价物，红线代码，合并前必过对抗闸。

量级估计（锚定 3 模块 / 8 触点 / 80-100 测试）：

- P0 实现（三模块 + 八触点 + 备份 + purge + 全默认关 + 测试）：约 2-3 周实现 + 约 1 周对抗审查/修复。
- P0 shadow 实机观测：2 周（并行，不占实现工时）。
- P1（拧到 owner+same_group+on，开三开关，调净化/观测）：约 1-1.5 周 + 对抗闸。
- P2（cross_group tier + all 档，看 P1 表现）：约 1 周 + 对抗闸。
- 端到端到"all 档全开且退得回"：现实节奏约 6-9 周（含每期对抗闸 + shadow 观测窗口），不是一次性交付。真正吃时间的不是写代码，是每道红线合并前的对抗复核 + shadow 观测两周的等待。

---

## 12. 已定决策与残留未解难题

### 12.1 已定决策

- **D1（复杂度收窄）**：接受 fable 分期——默认 owner、all 留档待 P2。all 档意味着任何陌生人都能跨群塑造她对自己的认知；爆炸半径被 R1 锁在"只影响她对该人自己的态度"、romantic 判定另有 owner 硬门兜底（relationship_layer.py:72-82），风险可控但不该是默认值。
- **D2（瞬时情绪跨群）**：per-person 受限形态**能签**（§4）。原判反对的是"全局情绪跨群"，per-person 构造把迁怒锁死在张三自己的 profile 里，是"记得对这个人的心情"不是迁怒。她跨群见到你，带着的是"对你"的余温或余怒，按离上次聊多久自然回落；张三惹的火永远烧不到你的会话。但她的"人格坍缩"和"伤口"仍然只属于每段关系现场——那不是记得你，是把一场事故复制粘贴，坚决不签。
- **D3（Embodiment Five 延后）**：认，留到 2.6.0 与 E 核一起动，表层 Sylanne Six 足够承载"她对你气质一致"。
- **D4（隐私下限）**：接受约八成 + 软约束三处（§5），不上 LLM 逐条判敏感。
- **D5（备份越契约）**：接受"备份做不了就不准开跨群"这条硬底线嵌进代码——pin 4.25.1 + 启动探测 + 探测失败拒开。
- **D6（分期节奏）**：接受 P0 全默认关 + shadow 实机跑两周再逐档放开。跨群是高危改动，shadow 观测窗口不能省。
- **D7 → B6（R6 默认范围）**：原案"strict-only opt-in"被 §8 B6 修订为"高于 same_group 的 tier 默认开"，理由见 B6 的方向性升级论证。

### 12.2 残留未解难题（诚实标注，物理下限，非缺陷待修）

- **转述型第三方隐私**（最难看的长尾）：P 本人转述的第三方隐私（"我跟张三闹掰了，他借了高利贷"）嵌在 P 自己的 origin=private/group 文本里。W0 剥掉的是张三亲口说的话，剥不掉 P 嘴里转述的张三。任何结构标签只描述"这条属于谁"，描述不了"文字里提到了谁的什么私事"。strict 档 R6 启发式压一部分（命中已知 sender 名单），压不到零；端到端"懂分寸"诚实说八成，剩两成靠注入块分寸指令软约束（§5）。这两成泄露今天不开跨群、在本群也存在（融合摘要已在 per-session 主档），跨群只是把暴露面从一个群扩到多个群，不是从零到一。
- **备份越契约**：`range_get_async` 非 plugin 契约面，AstrBot 升版可能破——pin 4.25.1 + 启动探测 + 探测失败拒开。备份做不了就不准开跨群（D5 已定）。
- **间接扩散不可逆**：跨群召回参与过的对话被正常摘要进当时会话主档，关闭收不回，物理下限。
- **最终一致的并发混合**：双群并发漂移落盘混合丢少量增量，量级小于单次 tick 步长，成文防误修（§10）。
- **货架饿死倾向**：fail-closed 叠 W0 净化失败跳过，活跃群里货架写入率明显低于主档——安全侧代价，shadow 期观测写入率，过低再调净化重试策略而非放松闸。
- **监控缺口**：货架/档案在 `validate_session_isolation` 盲区，模块内自检 + 文档标注，2.6.0 若动诊断再收编。
- **半衰期数字未经行为标定**：warmth 4h / volatility 90min 是拍的量级（有沉默分带旁证），shadow 两周数据说了算，拨 on 前必须回看。
- **off 语义的两种实现选择未定**（§8 B7）：文档兜底 vs 主动回撤，需在实现前二选一并写清用户可见文档。

### 12.3 次要开放决策（可延后，不阻塞 P0）

- D7 原案已被 B6 取代，见 12.1。若未来需要"strict 之上再加严"，钩子已留在 §5 的"不阻塞的钩子"一段，本期不做。

---

方法论溯源：本文档整理自 fable 终版设计（旁挂人核 v2）+ opus 红队对 D2 三写入点身份取值的复核证伪 + fable 对 D2/D4 两个开放决策的最终定夺，三轮素材忠实整合，未替换或弱化任何一条红线约束。冻结面与红线代码合并前对抗闸惯例参见 `docs/architecture/mem-phase1-write-throat-design.md`。
