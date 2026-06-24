# Sylanne 生活模拟升级 Phase 2B Handoff（首批：LLM 关系类型分类 · 亲密路由）

日期：2026-06-21
范围：**壳层关系层（LLM 分类 rel_register + 多轮累积 + /bond 纠错）+ life-sim 主动私推亲密路由**
前置：`phase-2-kickoff.md`、`phase-2a-implementation-ruling.md`、`phase-2b-intimacy-decision-memo.md`、三次 SDK 审计 + 文献
基线：`feat/life-sim`（2A 已合入）
状态：**草案 v7（v1-v6 六轮 review 迭代；用户定方向3=LLM 类型分类）。本文件不含实现，只列状态出口/消费路径/测试矩阵/preflight。**

> 关键裁决（用户 2026-06-21）：
> - M8 拆出 2B 单开阶段。
> - 亲密判定 = **LLM 直接分类关系类型**（不从情感标量累积）。骑现有主线 assessor 调用多输出 `rel_register: romantic|friendly|formal`，多轮累积 + 置信平滑，`/bond` 手动纠错覆盖兜 residual。
> - 第三次审计实证：现有信号全塌成"温暖强度"无法区分类型（warmth/pd/cadence/intimacy_gravity 全是强度）；类型不在标量、在 LLM 对文本整体判断里——这是 lovers-vs-friends 文献的真做法（75-80%，中文 58-69%）。
> - 关系层壳层、经 body_port 读、不碰 SDK 内部 `_engine/sylanne_core`。

---

## 0. 为什么是类型分类、不是强度累积（六轮定论）

前六轮全量"温暖投入度"标量（warmth v3 / relationship_memory=冲突量 v4 / pd 单向 v5 / sylanne_pd v6），全栽于同一处：**强度区分不了"暖同事"和"伴侣"**。一个又暖又频繁又掏心窝的好友把所有强度闸顶满，和伴侣一模一样。

类型 ≠ 强度。区分伴侣的是**浪漫语域**：称呼（老公/宝贝/想你）、排他性宣称（在一起/我们）、关系性指涉——同事 pd 再高也不用这套语域。这是类型信号。而 SDK 现有 lexicon（v2core/lexicon.py:25）把"爱你/想你"和"谢谢/辛苦了"塌进同一个 warm 桶，丢了类型；死的 relational_sheaf 类型枚举从没通电。

**解法**：让已在跑的主线 assessor LLM 直接分类 `rel_register`（文献做法）。类型藏在 LLM 对整段文本的判断里，不在任何标量。多轮累积一个稳定的 register 判断，远比单轮 benchmark 准；`/bond` 兜 residual 错判。

**残差诚实声明**：单轮分类中文约 58-69%、非 100%。残差靠三层压，但**分清各自管什么**（v7 review F2 修正）：
- **多轮累积+置信平滑**：只消**随机**per-turn 噪声（模型温度/上下文抖动）。**不消**"同一用户同一写作风格的系统性误判"——那种相关误差会被累积**固化**而非抵消（如随意用"亲爱的"的朋友，每轮都被判 romantic）。所以累积**不是**残差主兜底。
- **高阈值（真正兜底）**：`romantic_conf` 阈值必须**高于**"高频用爱称的友好语料"上实测的 romantic 误判占比，**不是简单 >0.5**。这是压住系统性误判的关键，阈值须按实测标定、非拍脑袋"偏高"。
- **/bond·/unbond 纠错**：用户随时翻转，兜住前两层漏的。
是"自动为主+人工兜底"，不假装满分。

## 0bis. 防对抗性注入：身份门控（v8 新增，核心安全）

**威胁**：别的用户从别的 sender_id 狂刷亲密称呼/排他性宣称，把 rel_register 刷成 romantic、累积过阈，**强行制造关系** → 苏思澜把私人生活分享推给冒充者（违排他性人设 + 隐私泄露）。

**根因规律（七轮总结）**：任何**内容**信号（warmth/pd/register/称呼/排他性文字）都可伪造，携带不了"这是不是真男友"——**只有身份不可伪造**。

**防御 = rel_register 自动晋升必须身份门控**：
- owner 身份锚 `sylanne_alpha_owner_id`（主人 sender_id）**只来自显式配置**。**不做首次 /bond 自动确权（TOFU）**——v8 review 实证 TOFU 是抢注 fail-open 洞（攻击者抢先 /bond 自封主+置 override 永久亲密）。owner_id 空 → 全禁自动晋升**且 /bond 拒绝**（提示去配置里设 owner），真·全程 fail-closed。
- `is_romantic` 自动晋升**仅对 session 的 authenticated sender_id == owner_id 生效**；非 owner 会话恒非亲密 → 陌生人刷称呼永远晋升不了。
- **sender_id 数据源（关键）**：写入时把认证 sender_id 显式存进 `register_state`（assessor 写路径有 event）；`is_romantic` 比较存下的 sender_id == owner_id，**不从 session_key 反解析**（UMO base 含冒号、易 fail-open）。取不到 sender_id → fail-closed 非亲密。
- **私聊投递闸（关键，v8 Q3；卡点 v8b H1）**：亲密 outreach **只投私聊(1:1) origin**，且闸**前移到目标选择/pending 存入之前**——`_most_recent_intimate_host_key` 排除群 session_key，群/空则不存 pending 不投。不能只在 dispatch 拦：life event 有两条投递路径（bridge 派发 + line 1420 reactive pending 注入），dispatch 闸盖不到 reactive 那条，群 pending 会被注入进群回复广播全群。
- `/bond`·`/unbond` 仅 owner 可用（owner_id 已配时 sender_id==owner 放行）。
- 效果：身份（配置 owner）携带排他性、不可伪造（平台认证 sender_id）；内容分类只在 owner 自己的多会话间细分。注入、抢注、群广播三路全断。

---

## 1. 范围与边界

**本批做**：assessor 加 rel_register 分类 + 关系层（多轮累积 register + 置信平滑 + is_romantic API + /bond 覆盖 + 真持久化）+ life-sim 路由改投亲密单目标 + origin_session 回填。

**本批不做**：M8（已拆）；其他消费方（召回/主动/人设，留接口）；激活 relational_sheaf 类型枚举（可选、留后续）；reactive 过滤。

**契约纪律（硬约束）**：
- **不碰 SDK 内部** `_engine/sylanne_core/`；只经 body_port `from_host` 读（不调 body_port_for_session）。
- rel_register 在 **v2core percept 阶段**（`run_percept_stage`，integration.py:374，event 在手）产出 + 壳层直写关系层；**绝不进 SDK tick/assessment**（v2core percept 是只读认知，不 tick 不写域，integration.py:363）。
- 关系层内聚单模块；LifeSimulator 接口冻结；投递选择全在 pipeline 层。
- 测试直调真函数；只改 `.clean-sylanne-github/`；`/bond` @filter.command 注册 main.py（repo 无现成 @filter.command，新建首例；`_FakeFilter.command` shim 已存在 main.py:54、无需新增）→ 编辑边界含 main.py + preflight 查注册。

---

## 2. 新增状态出口

### 2.0 `owner_id`（主人身份锚，防注入，config）
- 来源：**仅** 配置 `sylanne_alpha_owner_id`（主人 sender_id）。**不做 TOFU 自动确权**（v8 review：抢注 fail-open）
- 默认值：`""`（未配）；空 → **所有会话自动晋升禁用 且 /bond 拒绝**（提示配置 owner）——全程 fail-closed
- sender_id 取用 robust accessor（public_api.py:614：sender_id||user_id 再 event.get_sender_id()），非 session_context:510 裸 getattr
- 进用户可见 prompt：否

### 2.1 `rel_register`（关系类型分类，v2core percept 钩子 off-path gated 调用）
- **产出点**：`apply_v2core_request`（integration.py:362，async，`run_percept_stage` 调用点 :374 所在的钩子；**非** sync 的 run_percept_stage 本身）内，新增**低频 gated** 关系类型分类。**必须 off-path 后台 dispatch**（`safe_ensure_future`，完成时回写 register_state）——percept 在入站请求关键路径(`await apply_v2core_request` @ llm_request_pipeline.py:1093，在生成回复前)，绝不能 inline await 分类 LLM、否则阻塞每轮回复 + 违反 percept "不阻断请求"不变量(integration.py:363)。消费方 is_romantic 在 outreach 时读、多轮滞后，异步回写完全够用
- **这是新增 LLM 调用**——八轮验出默认 v2core 下 assess_main 不每轮跑、percept 偏零 LLM，"搭现有主线零成本"前提不成立；经 `plugin._llm_response_pipeline._generic_llm_call`（专用 provider key、small max_tokens），不走死的 assessor 路径
- 输出 `rel: romantic|friendly|formal|unknown` + 分类指令：**"按用户对苏思澜的称呼/排他性宣称/关系性指涉判，非情绪强度。仅爱称（亲爱的/亲）不足判 romantic——需与排他性或关系性指涉共现"**（v7 F1：堵"亲爱的"banter 中文误判）
- **壳层直写**：后台任务完成时把 rel + 认证 sender_id（robust accessor public_api.py:614）写 `plugin._store.relationship_register_state`（shell SessionStateStore map，**非** ctx.domains/ctx.scratch）。percept 只读不 tick(integration.py:363)，rel/sender_id 绝不进 kernel/assessment
- 缺/失败/未触发→不更新累积（unknown）；进用户可见 prompt：否

### 2.2 `relationship_register_state`（关系层累积态，store 新增，真持久化）
- 结构：`dict[session_key, {sender_id: str, romantic_conf: float, friendly_conf, formal_conf, sample_count, updated_at, last_active}]`（**含 sender_id**：percept 阶段写入时存认证 sender_id，供 outreach 无 event 时身份门控比较，v8b H3 修——写入点在 percept 而非死的 assessor 路径）
- 累积：每次 rel_register 分类按类加权累积（romantic→romantic_conf↑），置信 = 该类占比 × min(1, sample_count/N)（多轮平滑，单轮不定）
- 挂载：`_reg("relationship_register_state", {})` + **真持久化**（仿 sylanne_life_sim_state KV：initialize 恢复 + throttled/terminate 存；`_reg` 本身只 cleanup）
- 缺/异常→空/非亲密（fail-closed）；进用户可见 prompt：否

### 2.3 `intimacy_override`（手动覆盖，store 新增，真持久化）
- `dict[session_key, bool]`（True 亲密/False 非亲密/缺=自动）；`/bond`·`/unbond` 写；同 2.2 持久化（独立 KV key `sylanne_relationship_state`，**不折进 sylanne_life_sim_state**）
- **作用域**：per session_key（当前会话）；群会话与私聊各自独立
- **时效**：永久直到 `/unbond` 反转（非衰减）。⚠️ 已知风险：忘了的 /bond 会把某会话永钉 romantic、即使累积后判它非亲密（override 优先）→ `/unbond` 回执须提醒"已取消手动标记，恢复自动判定"
- **回执**：`/bond`→"嗯…那这边算我们自己人了"（人设口吻，确认已标亲密）；`/unbond`→"行吧，当我没说，恢复自动了"。回执文案 review 可调
- 进用户可见 prompt：否（仅指令回执给用户看）

### 2.4 `LifeEvent.origin_session: str`（路由元数据）
- 投递时回填（非生成时）；默认 `""`；`_event_from_dict`(:394，非 LifeEvent.from_dict)/`_event_to_dict`(:361) 迁移；单目标→单 str
- 进用户可见 prompt：否

---

## 3. 新增消费路径

### 3.1 rel_register → 关系层累积
- 每次 main-lane 出 rel_register → 关系层按类累积置信（EMA/计数加权）
- 同事：register 多判 friendly/formal → romantic_conf 不涨；伴侣：多判 romantic → romantic_conf 累积过阈
- 用户可见：否

### 3.2 `is_romantic(session_key) -> bool`（关系层读 API）
- ① 有 override → 用覆盖（优先）；② 否则 `romantic_conf ≥ 阈 AND sample_count ≥ 最小样本`
- **身份门控（v8，仅作用于自动晋升②，v8b Q2）**：仅 `register_state[session].sender_id == owner_id` 才允许②自动晋升（用**存下的** sender_id，不反解析 session_key）；非 owner 会话②恒非亲密；owner_id 空或 sender_id 缺 → fail-closed 非亲密。①override 不另加身份门控——它只能由 owner-gated `/bond` 写入，写入时已带身份；忘记的 /bond 跨 owner 变更仍存活，由 `/unbond` 处理（§2.3）
- **阈值锚定（v7 F2）**：阈值须 > 实测"高频爱称友好语料"上的 romantic 误判占比，非简单 >0.5；标定项须给实测数字、不写"偏高"
- fail-closed：取不到/样本不足 → 非亲密
- 可复用：本批 life-sim 调；后续召回/主动/人设可调同一 API。**契约：is_romantic 只许门控路由/召回，禁用于任何改变 Sylanne 自身表达亲密语域的生成**（不止"表露"——含 recall/persona 经回灌间接改输出语域；否则自证循环，红队 v6 F2 / v7 F5）

### 3.3 `_life_sim_outreach` 投递目标：last-active → 亲密单目标
- **新加 `_most_recent_intimate_host_key()`**（不改共享 `_most_recent_host_key`@:647，它有 **5** 调用方：:2667/:2898/:2917/:2937 + main.py:2428，全保留 last-active）。**此 helper 直接排除群 session_key**（`social_field.is_group_context_by_key(session_key)`，:301）——只在 is_romantic 真**且私聊**的会话里选
- `_life_sim_outreach`(:2667) 改调新 helper；**私聊闸前移到目标选择 + pending 存入之前**（v8b H1）：best_key 为空/群 → 直接 return，**不执行 :2689 的 `pending_outreach_context.set`**。否则群 best_key 的 pending 会在下轮经 :1420 reactive 注入进群回复、广播全群（dispatch 闸盖不到这条 reactive 路径）
- 空（无亲密私聊会话）→ 不投、不存 pending；单 host 兜底仅当 host==owner 私聊
- **路由可达性（v7 F4）**：helper 遍历 live host，亲密会话 host 被 LRU 驱逐期间够不到（状态不丢、驱逐期不可投）
- **已知限制（v8b Q4）**：只在群里跟 Sylanne 互动、无 1:1 会话的 owner，主动私推会静默（不广播进群是正确取舍）。可选后续：给 owner 构造私聊 UMO 直投，受平台是否允许未邀私信约束
- 过期/去重沿用 2A

### 3.4 `/bond`·`/unbond`（main.py 注册）
- **仅 owner 可用**：owner_id 已配 → 仅 sender_id==owner_id 放行；**owner_id 空 → 拒绝并提示去配置设 owner_id（不自动确权，无 TOFU，v8 Q2/Q4）**
- 写 `intimacy_override`；纠错（owner 自己的会话：register 没累积时手动标亲密；误判 /unbond）
- 编辑边界含 main.py；preflight 查 @filter.command（新建首例，_FakeFilter.command shim 已存在 :54）

### 3.5 与 reactive 隔离
- 只改 `_life_sim_outreach` 投递目标；被动回应/privacy/召回不受影响

---

## 4. PR 切分

- **PR-G：rel_register 分类**（`apply_v2core_request`（integration.py:362 async 钩子）内新增低频 gated 关系类型分类，**off-path `safe_ensure_future` 后台跑**、完成回写 register_state 含认证 sender_id；只读认知不写 SDK 域、不阻塞请求）
- **PR-H：关系层**（relationship_layer.py + register_state/override store + owner_id 配置 + 真持久化 + is_romantic API + /bond owner-gate 含 main.py）
- **PR-I：life-sim 路由**（LifeEvent.origin_session + _most_recent_intimate_host_key 排除群 + 私聊闸前移到 pending 存入前 + 单 host=owner 私聊兜底）

依赖：G → H（需 G 的 rel_register）→ I（需 H 的 API）。同阶段合入 review。

---

## 5. 测试矩阵（直调真函数，py3.13 实跑）

### 5.1 rel_register 分类（PR-G）
| 测试 | 断言 |
|------|------|
| `test_percept_produces_rel_register` | run_percept_stage 触发时产出 rel ∈ {romantic,friendly,formal,unknown} |
| `test_rel_gating_low_frequency` | gating 生效：非触发轮不调分类（不每轮烧 token） |
| `test_rel_classification_off_path` | **分类不给请求路径加 await 的 LLM 调用**——`apply_v2core_request` 不 await rel provider，分类经后台任务（A1 防回归，核心） |
| `test_rel_register_enum_validated` | 非法/缺→unknown，不更新累积 |
| `test_rel_and_senderid_not_in_sdk` | rel/sender_id **不**进 SDK tick/assessment/kernel（percept 只读边界防回归，核心） |
| `test_senderid_captured_authenticated` | 写入 register_state 的 sender_id 来自认证 event（robust accessor），非 session_key 反解析 |

### 5.2 关系层 / 类型分类（PR-H）— 核心
| 测试 | 断言 |
|------|------|
| `test_romantic_accumulates_intimate` | 多轮 romantic + 样本足 → is_romantic 真 |
| `test_friendly_not_intimate` | 多轮 friendly（暖同事）→ romantic_conf 不过阈 → **非亲密**（六轮核心防回归） |
| `test_injection_nonowner_never_intimate` | **非 owner sender_id 狂刷 romantic 称呼/排他性 → 恒非亲密**（防注入，0bis 核心） |
| `test_no_owner_all_autopromote_disabled` | owner_id 空 → 任何会话自动晋升禁用 **且 /bond 拒绝**（全程 fail-closed，v8 Q2/Q4 无 TOFU） |
| `test_bond_owner_gated` | owner_id 已配：非 owner /bond 被拒；owner_id 空：任何 /bond 被拒（提示配置） |
| `test_group_origin_not_delivered` | owner 在群里是 romantic → 亲密 outreach **不投群 origin**（防广播泄露，v8 Q3） |
| `test_single_host_fallback_owner_private_only` | 单 host 是陌生人/群 → 兜底**不投**；仅 owner 私聊才兜底 |
| `test_is_romantic_uses_stored_sender_id` | 门控比较用 register_state 存的 sender_id，不反解析 session_key |
| `test_single_romantic_turn_insufficient` | 单轮 romantic 但样本不足 → 非亲密（多轮平滑，防单轮误判） |
| `test_override_wins` | /bond·/unbond 覆盖优先 |
| `test_register_state_persists_restart` | 累积态+override 真落盘、重启存活（v4-v6 持久化缺陷防回归） |
| `test_intimate_survives_host_eviction` | 持久态不随 host LRU 驱逐丢 |
| `test_is_romantic_fail_closed` | 取不到/样本不足 → 非亲密 |

### 5.3 路由 + 隔离（PR-I）
| 测试 | 断言 |
|------|------|
| `test_origin_session_roundtrip` | _event_from_dict/_event_to_dict 存活；旧档→"" |
| `test_outreach_targets_intimate_single` | 投亲密单目标 + 回填 origin_session |
| `test_outreach_single_host_fallback` | 仅一个 host（单用户）→ 兜底投它（无死区） |
| `test_outreach_skips_non_intimate_multi` | 多 host 都非亲密 → 不投 |
| `test_most_recent_host_key_unchanged` | 共享 helper 行为不变（**5** 个调用方含 main.py:2428 防回归） |
| `test_reactive_unaffected` | 非亲密会话被动回应正常 |
| `test_bond_command_reaches_store` | /bond 端到端写 store（含 main.py 路径） |

### 5.4 回归
| 测试 | 断言 |
|------|------|
| 全量回归 | ≥ 659 + 新增数，零失败 |
| SDK 内部不动 | `_engine/sylanne_core/` git diff 空 |

---

## 6. Release Preflight 增量（grep 生产文件，含 main.py）

- **PR-G**：`apply_v2core_request`（integration.py:362）内有 rel_register 分类 + **off-path dispatch**（grep `safe_ensure_future`，确认不 inline await rel provider）+ gating 低频触发；后台回写 register_state 含 rel + 认证 sender_id；**grep 确认 rel/sender_id 不进 SDK tick/assessment/ctx.domains**（percept 只读）
- **PR-H**：`relationship_layer.py` 存在；`def is_romantic(`；`sylanne_alpha_owner_id` 配置字段（_conf_schema 新增）；`relationship_register_state`（含 sender_id 字段）/`intimacy_override` 在 store `_reg` + **独立 KV key `sylanne_relationship_state` 的 restore/save 路径**（仿 sylanne_life_sim_state 三点位，自有 key、不折进 life_sim.to_dict）；`/bond` @filter.command 在 main.py + owner-gate（owner_id 空则拒）
- **PR-I**：`LifeEvent` 含 origin_session；`_event_from_dict`（非 LifeEvent.from_dict）迁移；`def _most_recent_intimate_host_key(`（**排除群 session_key**）；`_life_sim_outreach` 调它 + **群/空 best_key 不执行 pending set**（私聊闸前移）；`_most_recent_host_key` 函数体未改（diff）
- **边界**：`_engine/sylanne_core/` 零改动（git diff）

核对：生产文件（`sylanne_alpha/*.py`+`main.py`）`grep -c`>0，不扫 tests/docs；签名 `grep -A2`。

---

## 7. 启动门槛

架构 review 通过后，编写侧按 PR-G→H→I 实施，同批合入 review。

**v8 相对 v1-v7 的关键收敛**：
1. M8 拆出；亲密判定 = **LLM 关系类型分类 rel_register**（非强度累积）——七轮强度信号全栽于"区分不了暖同事 vs 伴侣"，类型分类是文献真做法
2. rel_register = **v2core percept 钩子（apply_v2core_request）新增低频 gated 分类，off-path 后台跑不阻塞请求**（八轮验出"搭现有主线零成本"前提不成立 + 终审 A1：percept 在请求关键路径，分类必须后台 dispatch）；多轮累积+置信平滑压单轮中文 58-69% 残差；/bond 纠错兜底
3. rel/sender_id 在 percept 只读阶段产出+壳层直写，**不进 SDK tick/assessment**，守 SDK 边界；关系层经 body_port from_host 读、不碰 _engine
4. 真持久化独立 KV `sylanne_relationship_state` 仿 sylanne_life_sim_state（修 v4-v6 纯内存缺陷）
5. **身份门控防注入（v8）**：owner_id 仅配置（无 TOFU 抢注）；自动晋升②仅 sender_id==owner；陌生人刷称呼晋升不了
6. **私聊投递闸前移到目标选择/pending 存入前（v8b H1）**：`_most_recent_intimate_host_key` 排除群、群/空不存 pending——堵住 bridge + reactive(line 1420) 两条投递路径，防群广播泄露
7. is_romantic 契约：只门控路由/召回、**禁门控 Sylanne 表达亲密语域生成**（防自证循环 v6/v7）；新 helper 不改共享 `_most_recent_host_key`（5 调用方）
8. /bond owner-gate（空 owner 拒，无 TOFU）纳入 main.py 编辑边界 + preflight；reactive/privacy 隔离

**待 review 标定项**：rel_register 分类 prompt 措辞（中文称呼/排他性判据）、gating 频率（每 N 轮/realtime）、romantic_conf 阈值 + 最小样本数（须 > 实测友好语料误判占比）、累积公式。

**已知限制**：只在群里跟 Sylanne 互动、无 1:1 的 owner，主动私推会静默（v8b Q4，不广播进群是正确取舍）。

最终全量回归 > 659 + 新增测试数。本 handoff 须再过一轮 review 通过后方可实现。
