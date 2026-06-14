# Issue #26 研判 — 主动消息进了历史但 QQ 收不到

> 来源:4-agent opus 研判(任务 w71u1nk5a)，三路链路独立收敛同一机制
> 状态:研判完成，未动代码。需 owner 确认运行期配置才能定修法分支。

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
