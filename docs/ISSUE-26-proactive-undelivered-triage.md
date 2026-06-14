# Issue #26 研判 — 主动消息进了历史但 QQ 收不到

> 来源:4-agent opus 研判(任务 w71u1nk5a)，三路链路独立收敛同一机制
> 状态:研判完成，未动代码。需 owner 确认运行期配置才能定修法分支。
> **更新(深挖):clone 大饼 DBJD-CR/astrbot_plugin_proactive_chat 源码逐行走完发送链，见文末"深挖结论"——浮现一个比开关假设更硬的设计级结构冲突。**

## 一句话根因

不是"Sylanne 调不动 TTS"(owner 初判方向沾边但机制反了)。真卡点:**分段接管(segment_takeover)模式下，Sylanne 清空大饼出站 chain 阻止大饼发送，改由自己裸 `context.send_message` 连发——而这条自发链路只提取 Plain 文本、会静默失败、无日志**。

## 根因机制(情形 A，与症状高度吻合)

1. Sylanne 不直接发平台，调大饼 `check_and_chat` 生成+发送(`proactive_scheduler.py:378` → `proactive_bridge.py:336-337`)
2. 接管开启时，dispatch 登记 origin 进 `_pending_segment_takeover` + 关大饼自带分段(`proactive_bridge.py:327-334`)
3. 大饼生成正文、**写进对话历史**(所以"历史能看到、webui 显示未回复"是真成功)
4. `on_decorating_result` 钩子(`main.py:1211`)→ `_maybe_takeover_segments`，`claim_segment_takeover(origin)` 命中 → **切片清空出站 chain**(`main.py:1271-1276`)→ 大饼见空链 return 不发平台 ← **断点在此**
5. 本该由 `_dispatch_segmented_parts` 用 `context.send_message` 自己连发(`llm_response_pipeline.py:461-498`)，但三个静默点导致啥都没发：
   - 只提 Plain 文本(`main.py:1267-1270`)；大饼开 TTS、若 TTS 先把 chain 转 Record 语音，提取得空串 → `main.py:1277-1279` 空文本直接 `return True` 静默不发
   - `_astrbot_message` 缺 `astrbot.api.message_components/event` 在 sys.modules 时回退裸 str(`llm_response_pipeline.py:1220`)，`send_message(origin, 裸str)` 在 aiocqhttp/napcat 上很可能投不出且不报错
   - 后台任务 done_callback 只移除 task、不取 `t.exception()`、不记日志(`main.py:1299-1305`)← "无报错日志"的直接来源

**对照**:大饼自发的 origin 不在 `_pending_segment_takeover`，claim 返回 False，chain 不清，走大饼原生带 TTS pipeline → 正常到 QQ。症状非对称性来源。

## 情形 B(只开桥接、没开接管，schema 默认)

发送 100% 在大饼 `check_and_chat` 内，断点不在本仓。唯一可疑我方输入是 `_resolve_origin`(`proactive_bridge.py:76-94`)：`_store.session_origins` 缺失/过期时回退 `split("::")[0]`，可能给出大饼"能写历史却投不到平台"的 umo。需大饼日志佐证。

## TTS 假说：基本排除

全仓搜 Record/tts/voice/text_to_speech 零命中，Sylanne 从不构造语音组件。接管路绕开含 TTS 的整条大饼 pipeline；不开接管时与大饼同走一条 TTS 路，不可能只吞 Sylanne 的。

## 修法

**首选(可能不用改代码)**：关掉 `sylanne_alpha_proactive_segment_takeover`。chain 不被清，送达交还大饼原生 pipeline(TTS+到达 QQ 一起恢复)，Sylanne 保留"决定何时+注入素材"辅助定位，与 owner 适配预期一致。

**若保留接管(本仓改，不碰 SDK)**：
- (a) `main.py:1299-1305` done_callback 加失败日志(取 `t.exception()` + logger.error)——先干掉"无报错"盲区
- (b) `_astrbot_message`(`llm_response_pipeline.py:1204-1221`)回退裸 str 前校验 message_components/event 在 sys.modules，缺了告警而非静默发裸 str
- (c) `main.py:1277-1279` 空文本静默 return 改记 warning
- (d) 接管路不接 TTS，与"开了大饼 TTS"冲突，需 owner 拍板接管时还要不要语音

## 动手前需 owner 确认

1. **关键**:实配 `sylanne_alpha_proactive_segment_takeover` 是不是 true(定走 A/B 哪条)
2. 复现:临时关 takeover(或关大饼 TTS)能否恢复收到。关接管恢复→坐实 A；关 TTS 才恢复→再看 TTS(代码上讲不通，优先信前者)
3. 完整主动消息日志，特别看有无 `Sylanne proactive segment takeover: N parts for ...`(`main.py:1306-1308`)——有它证明接管认领了

## 是否本次会话能顺带修

**独立任务**。本次会话改的是计算层/记忆/会话态批次，与主动发言送达链(proactive_bridge / main.py 接管钩子 / llm_response_pipeline 送达)无关。最低成本止血(关 takeover 开关)甚至不用改代码。强烈建议先做 A/B 判定再动代码，否则盲修。

## 诚实未知项

- 无法从本仓确认 owner 实配是否开接管
- 无法确认运行时那两个 astrbot 模块一定在 sys.modules
- 未读大饼源码，无法确认 check_and_chat 一定经 ResultDecorateStage 且 origin 一致
- 引用纠偏:`_dispatch_segmented_parts` 真身在 `llm_response_pipeline.py:461`(研判3 曾误引 realtime_dispatch.py，机制结论不受影响)

---

## 深挖结论（clone 大饼源码逐行走完发送链，2026-06-15）

大饼源码本机/本仓都没装，从 GitHub `DBJD-CR/astrbot_plugin_proactive_chat` 经 gh api 取源码（直连 443 不通，clone 失败，改 gh api）。逐行走完 `check_and_chat → _send_proactive_message → _send_chain_with_hooks → _trigger_decorating_hooks` 全链，三个新坐实的事实：

### 事实 1：check_and_chat 是同步 await 跑完发送，不是投队列
`chat_flow.py:150 check_and_chat` → `:268 await _send_proactive_message`。**推翻了之前"dispatch 的 finally 在 pipeline 跑完前 discard 标记"的时序竞态嫌疑**——check_and_chat 同步 await 到发送完成，钩子在其内触发，finally 的 discard 是兜底不是竞态。

### 事实 2：大饼自己手动触发 decorating hooks（Sylanne 钩子确实会跑）
`message_sender.py:162 _trigger_decorating_hooks`：211 构造 `AstrBotMessageEvent(session_id=target_id)` → 224 取 `OnDecoratingResultEvent` handlers → 232 `await handler.handler(event)`。Sylanne 的 `on_decorating_result` 就在这被调。

### 事实 3（最硬，设计级结构冲突）：TTS 发的是纯 Record 语音 chain，无 Plain 文本段
`message_sender.py:373 _send_proactive_message`：
- `enable_tts` **默认 True**（391 `tts_conf.get("enable_tts", True)`）
- TTS 成功 → `_send_chain_with_hooks(session_id, [Record(file=audio_path)])`（398）——**chain 里只有 Record 语音，没有 Plain**
- `_send_chain_with_hooks`（311）→ 313 先 `_trigger_decorating_hooks` 触发 Sylanne 钩子

而 Sylanne `_maybe_takeover_segments`（main.py:1267-1270）**只提取 Plain 段文本**：
```
text = "".join(seg.text for seg in chain if isinstance(seg, Plain) and seg.text)
```
TTS 的 chain 是 `[Record语音]` → 提取 Plain 得 `text=""` → 清空 chain（1274）→ 空文本 `return True`（1278-1279，静默拦截）。

**结论：只要"接管开 + TTS 开 + TTS 成功"三者同时，Sylanne 接管会把语音 chain 清空、自己又因无 Plain 文本不发 → 语音被吞、文本也没有 → QQ 收不到，且无报错。** 这是设计级冲突，不依赖 origin 是否匹配（只要 claim 命中就触发）。owner 不复现＝没开接管（默认 false），不碰这段。

### 仍需 19 点那次完整日志才能二选一
图 1 日志只截了一段，缺关键信息。两个互斥分支：
- **分支 A（claim 命中）**：上述结构冲突，语音被吞。但图 1 **没有** `Sylanne proactive segment takeover: N parts` 那行（main.py:1306）→ 似乎 claim 没命中。
- **分支 B（claim 未命中，origin 不一致）**：Sylanne 不接管，大饼自己 `_send_chain_with_hooks` 发语音。图 5 证明 18:31 语音能到 QQ → napcat 能发语音。那 19 点这条为何丢？可能 `get_audio` 返回空/异常（408 except 记 error）→ is_tts_sent=False → 走文本分段 → 文本那次若 claim 命中则被 Sylanne 吞。

origin 一致性链（已走到）：Sylanne `check_and_chat(sid)`，sid=`_resolve_origin(session_key)`；大饼 `_parse_session_id(sid)→target_id`（session_parser.py:15，按 `:type:` 锚拆 platform/type/target）→ event.unified_msg_origin = `{platform_meta.id}:{message_type枚举}:{target_id}`。**潜在不一致点：message_type 段——原 sid 的 type 字符串 vs MessageType 枚举 str 化，若不等则 unified_msg_origin≠sid → claim False。** 这要原始 sid 格式才能定。

### 区分分支需 owner 提供（按优先级）
1. **19 点那次的完整日志**（从 `[主动流意图]` 到发送结束整段），特别看：有无 `Sylanne proactive segment takeover` 行、有无 `手动TTS` 之后的成功/异常行、有无 send_message 相关。
2. 临时**关 enable_tts**（大饼会话配置 tts_settings.enable_tts=false）看是否恢复收到——若恢复，坐实事实 3 的 TTS-接管结构冲突。
3. 临时**关 segment_takeover** 看是否恢复——若恢复，坐实接管路是卡点。

### 修法（深挖后更新，分优先级）
- **止血（不改代码）**：关 `sylanne_alpha_proactive_segment_takeover` 或大饼 `enable_tts` 二选一，断开三者同时的条件。
- **根治（本仓 agent 层，不碰 SDK）**：`_maybe_takeover_segments`（main.py:1263-1279）增加 **非 Plain（Record/Image 等）chain 的处理**——检测到 chain 含非文本组件（如 TTS Record）时，**不接管**（return False 让大饼原样发语音），或接管后**保留并转发原 Record**而非只提 Plain。当前"只提 Plain + 无条件清空 chain"是把语音/图片消息一律吞掉的设计缺陷。

### origin 一致性验死（2026-06-15 续）
- `MessageSession.__str__` = `f"{platform_id}:{message_type.value}:{session_id}"`；MessageType.value = `"FriendMessage"`/`"GroupMessage"`。
- 大饼 `_parse_session_id` 的 `known_types = ["FriendMessage","GroupMessage",...]` **与 MessageType.value 完全一致**。
- 推论：只要 Sylanne 登记的 sid 是标准 UMO（`platform:FriendMessage:target`），大饼拆 `:FriendMessage:` → 拼回 unified_msg_origin == sid → **claim 应命中 → 走分支 A（TTS 语音被接管吞）**。

### 但图 1 无 takeover 日志 = 反证，最后变数锁定在 _resolve_origin
claim 应命中却无 takeover 行，唯一剩的变数：**Sylanne 登记的 sid ≠ 标准 UMO**。看 `_resolve_origin`（proactive_bridge.py:76-94）：
- 优先 `_store.session_origins[session_key]`（用户**收消息**时 request pipeline 写入）
- 回退 `session_key.split("::")[0]`

**主动消息是定时/自驱触发，不是用户收消息驱动**——若该 session 在本次主动前没有近期用户消息写入 session_origins，或 session_key 带内部后缀且映射缺失 → 回退 split，产出的 sid 可能 ≠ 大饼/平台实际 UMO。则：
- Sylanne 登记 sid_A 进 _pending_segment_takeover
- 大饼用同一 sid_A 调 check_and_chat，但其 `_trigger_decorating_hooks` 构造 event 的 unified_msg_origin 若经平台归一化得 sid_B ≠ sid_A → **claim(sid_B) 未命中 → 分支 B**

这就把"无 takeover 日志"和"接管开着"统一了：**接管开了，但因 origin 解析在主动场景下与平台实际 UMO 错位，claim 没命中，Sylanne 没接管，大饼自己发 TTS 语音——而这条语音为何没到 QQ（19点那条），仍需该次完整日志看 get_audio/send_message 结果。**

### 静态分析到此为止（诚实边界）
两个分支都代码自洽，纯静态分不出唯一解，因为决定性变数是**运行期的 session_origins 映射内容 + 19 点那次完整日志**，本仓/本机都没有。已把因果链收敛到最小未知集（上面两项），交 owner 补。这是静态深挖能到的底。

### session_origins 写入时机定了 → 主流场景指向分支 A
`session_origins` 在 `llm_request_pipeline.py:911-915` 写入：**用户发消息触发 LLM 请求时** `set(session_key, event.unified_msg_origin)`（真实 UMO）。

故：
- **用户聊过的 session（主动消息的常态——Sylanne 是"隔段时间主动找聊过的人"）→ session_origins 有映射 → `_resolve_origin` 返回真实 UMO → 与大饼 `_trigger_decorating_hooks` 拼出的 unified_msg_origin 一致 → claim 命中 → 分支 A：TTS 语音 chain 被 Sylanne「只提 Plain」的接管逻辑吞掉。** 这与"接管开 + TTS 开"完全吻合，是最可能真相。
- 例外（→ 分支 B，回退 split）：bot 重启后该 session 未再发消息（session_origins 是内存 SessionMap，重启清空），或 session_key 带 `::agent:` 后缀且映射缺失。

### 最终结论（深挖收口）
**最可能根因（分支 A，无需更多日志即可高置信）**：报告人开了 segment_takeover + 大饼 enable_tts（默认）。Sylanne 主动找聊过的人 → claim 命中 → 接管 `_maybe_takeover_segments` 拿到的是 TTS 的 `[Record语音]` chain → 只提 Plain 得空 → 清空 chain（语音没了）+ 空文本静默 return（Sylanne 也不发）→ QQ 收不到、历史已写（大饼生成在发送前）、无报错。

**唯一与该结论冲突的证据**：图 1 缺 `Sylanne proactive segment takeover` info 日志。两种解释：(a) 图 1 截的是该次发送之前的日志段；(b) 该 session 恰好命中分支 B 的例外。**要彻底坐实，仍需 19 点那次从 dispatch 到发送的完整日志。**

**根治（本仓 agent 层，main.py:1263-1279）**：`_maybe_takeover_segments` 接管前检测 chain 是否含非 Plain 组件（Record/Image）——含则**不接管**（return False，让大饼原样发语音/图片），仅对纯 Plain 文本 chain 接管分段。当前"无条件清空 chain + 只提 Plain"会把一切非文本消息吞掉，这是设计缺陷的本质，比关开关更根本。**止血**：关 segment_takeover 或大饼 enable_tts 任一。
