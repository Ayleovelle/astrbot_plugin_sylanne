# AstrBot Sylanne

> <span style="font-size: 1.08em;"><strong>Soulful Yearning Lifelike AstrBot Neural Narrative Engine</strong>。她维护的不只是“情绪标签”，而是情绪、人格、记忆、氛围、主动性和表达节奏交织成的长期状态。</span>

![版本 2.3.13](https://img.shields.io/badge/version-2.3.13-blue)
![AstrBot >=4.9.2,<5.0.0](https://img.shields.io/badge/AstrBot-%3E%3D4.9.2%2C%3C5.0.0-green)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-yellow)
![协议 astrbot.emotion_state.v2](https://img.shields.io/badge/schema-astrbot.emotion__state.v2-purple)
![许可证 GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-red)

## 介绍

<img align="right" src="docs/assets/sylanne-mascot-card.svg" width="320" alt="项目吉祥物 Sylanne，Sylanne向大家问好 = w =">

`astrbot_plugin_sylanne` 是一个面向 AstrBot 的“生命化状态引擎”和“插件公共状态服务”。她不是只在提示词里写几句“你要有喜怒哀乐”，而是把 bot 的情绪、关系后果、人格差异、长期记忆注解、拟人状态、道德修复状态、群聊氛围、后台评估队列和非诊断心理筛查拆成可测试、可持久化、可调用的工程模块。

`astrbot_plugin_sylanne` 不是一个简单的“给 bot 加情绪标签”的插件。她的核心目标是：

> 让不同人格的 bot 在长期对话中形成可解释、可持续、可重置、可被记忆系统记录的计算性情绪轨迹。

本插件会让大模型根据 AstrBot Agent 自己维护的对话历史、用户当前文本、bot 人格和上一轮状态，判断当前情绪观测值；本地引擎再用真实时间半衰期、人格基线、置信门控、关系修复和后果状态机更新长期状态。Sylanne 不会把整段上下文抢到插件里重放；她只在必要时提供很短的状态摘要、记忆召回摘要和“已发/未发”这类 Agent 无法自然知道的投递事实。

**特色功能**

- 🧠 <span style="font-size: 1.04em;"><strong>不只是情绪：</strong>同时维护 7 维情绪、人格漂移、拟人状态、生命化学习、道德修复、瑕疵模拟和非诊断心理筛查。</span><br>
  <sub><em>「先把状态做成会互相牵动的东西。7 维情绪只是入口，人格漂移和长期记忆才让她有前后文。」</em></sub>
- 📝 <span style="font-size: 1.04em;"><strong>会记住相处方式：</strong>Sylanne 自有记忆会记录事件、情绪、人格漂移和相处气氛，后续按真实时间与记忆深度限长召回。</span><br>
  <sub><em>「记忆不能只存事实。那天是别扭、开心、委屈还是想靠近，都应该一起留下来。」</em></sub>
- 💬 <span style="font-size: 1.04em;"><strong>懂得什么时候说话：</strong>结合群聊氛围、打断风险、双方需要和主动发言反馈，判断该开口、短应、先听还是保持距离。</span><br>
  <sub><em>「先做好开口门控。尤其是群聊里该不该插话，这个地方最容易看出她是不是只会抢答。」</em></sub>
- 🌙 <span style="font-size: 1.04em;"><strong>会主动找你聊天：</strong>可记录最近可触达会话，后台低频醒来判断是否因为想念、关心进度、调皮打扰、关系修复或双方互需而请求 AstrBot 发消息。</span><br>
  <sub><em>「不是定时刷屏，也不是预设话题库。她要先有理由、有证据，再决定要不要轻轻敲一下门。」</em></sub>
- 🫧 <span style="font-size: 1.04em;"><strong>更像即时聊天：</strong>回复可拆成多条短消息，按打字速度与停顿发送，并在发送表情包前检查语气一致性。</span><br>
  <sub><em>「不要把整段话一次性倒出来。真正的聊天会停顿，会分开发，会犹豫一下再补一句。」</em></sub>
- ⚙️ <span style="font-size: 1.04em;"><strong>后台并行但不乱来：</strong>状态评估可后台运行，后台工作器会参考队列压力、CPU/内存压力和全局预算自动收放。</span><br>
  <sub><em>「后台可以聪明，但不能把服务器拖垮。工作器要自己判断压力，忙完就安静退下去。」</em></sub>

<br clear="right">

`2.3.13` 是等待期追发合并和即时聊天等待上限修复版：主聊天上下文继续交给 AstrBot Agent，Sylanne 只补充短状态、记忆召回和“已发/未发”的投递事实；如果用户在上一轮 LLM 尚未产出可用回复前继续补充，插件会把前后两条短事实合并进同一个用户意图，避免只抓最后半句；碎片完整性等待上限降到 4 秒，把主要时间留给主 LLM 正常理解合并后的消息。工作流图同步重绘，去掉误导性诊断话术，突出即时聊天、追发整合、Agent 工具循环和主动聊天反馈闭环。

| 能力 | 作用 |
| --- | --- |
| 回复后后台评估（`post`） | 可把回复后的内部情绪评估放进后台队列，主回复先返回；队列支持同一会话先进先出（FIFO）提交、AstrBot 键值存储（KV）检查点、租约回收、重试和失败任务留存诊断。 |
| 并发状态加载 | 请求、响应和自有记忆写入阶段会并发读取可选状态快照；慢状态加载、内部评估和记忆注解不再简单串行等待。 |
| 智能后台工作器 | 默认每会话 1 个后台工作器；打开动态扩容后，插件会同时看队列压力、等待时间、重试/租约压力和 CPU/内存环境压力，全插件同时活跃后台工作器硬上限固定为 6，并通过冷却时间逐级扩容、空闲后自动关闭；内部判断大模型另有并发闸门，默认最多 2 路、极端积压最多 3 路。 |
| 群聊分层建模 | 同时维护房间级 `conversation_id` 和说话人级 `speaker_track_id`，避免一个人的冲突污染全群，也避免群聊气氛被切碎。 |
| 群聊氛围与开口时机 | `group_atmosphere_state` 记录活跃度、紧张度、玩笑度、支持度、bot 注意力、打断风险和加入适宜度，帮助 bot 判断该开口、短应、先听还是避免插话。 |
| 统一插件状态查询 | 其他插件可通过公共接口查询核心情绪、说话人轨道、群聊氛围、因果轨迹、运行时诊断或总览状态，而不是读取内部 KV。 |
| 真人即时聊天 | 可把回复拆成多条短消息，按打字速度、长度和稳定抖动顺序发送，降低长篇报告腔。 |
| 表情包回应与学习 | 根据当前情绪、群聊氛围和文本线索选择表情包；可记录用户表情的轻量元数据，形成小圈子里的表情共同语境。 |

> [!CAUTION]
> **重要警示：本插件只用于 LLM 情绪化与拟人状态建模研究。**
> 这里的“情绪”“拟人状态”“道德修复”“心理筛查”全部是工程模拟状态，不代表真实意识、真实主观体验、真实身体、真实疾病或临床诊断。心理相关模块只输出非诊断趋势和风险提示，不能替代医学诊断、心理咨询、危机干预或任何专业人工判断。关闭重置后门、关闭安全边界、开启高消耗功能或把模拟状态用于现实关系判断造成的风险，由使用者自行承担。

---

## 先读这里

如果你只是想安装和使用，按这个顺序看就够了：

1. [当前版本与兼容范围](#当前版本与兼容范围)
2. [快速开始](#快速开始)
3. [最小可用配置](#最小可用配置)
4. [命令](#命令)
5. [Sylanne 自有长期记忆](#sylanne-自有长期记忆)

如果你要维护、二次开发或复现实验，再看后面的公共 API、模型公式、远程测试、发布历史和故障排查。旧迭代记录、完整公式和复现实验放在折叠块里；README 首页只保留当前版本的结论、入口和关键表格。

## 快速导航

| 主题 | 内容 |
| --- | --- |
| [当前版本与兼容范围](#当前版本与兼容范围) | 插件版本、AstrBot 版本、Python 要求、许可证和发布状态。 |
| [当前版本发布记录](#2313-当前版本发布记录) | 等待期追发合并、碎片完整性 4 秒上限、Agent-owned context、内部工具 schema 全模型隐藏、短答锚定、向量记忆 provider 选择、主动聊天反馈和包体发布说明。 |
| [项目定位](#项目定位) | 为什么本插件不是普通的提示词人设增强。 |
| [核心能力](#核心能力总览) | 7 维情绪、人格建模、真实时间记忆、关系修复、公共 API。 |
| [快速开始](#快速开始) | 发布 zip 包、仓库安装、手动复制、最小配置和检查命令。 |
| [命令速查](#命令) | 用户可直接在会话里调用的状态、重置和诊断命令。 |
| [配置指南](#配置指南) | 核心配置、低推理模式、后果衰减、humanlike、心理筛查。 |
| [工作流对比（与 0.5.0）](#工作流对比与-050) | 对比旧版单线程链路和当前后台并行、主动发言、动态工作器链路。 |
| [Sylanne 自有长期记忆](#sylanne-自有长期记忆) | 写入自有记忆时冻结 `emotion_at_write`、`humanlike_state_at_write`、`lifelike_learning_state_at_write`、`moral_repair_state_at_write`、`fallibility_state_at_write` 和 `integrated_self_state_at_write`。 |
| [公共 API](#公共-api) | 其他插件如何读取、模拟、提交、重置情绪状态。 |
| [打包、上传与新仓库发布](#打包上传与新仓库发布) | 构建 zip、预检、WebUI 上传、GitHub 新仓库发布清单。 |
| [情绪模型](#情绪模型) | 维度定义、公式推导、人格基线、真实时间半衰期。 |
| [关系与后果](#关系与后果) | 生气原因、是否原谅、冷处理、错误是否已改正。 |
| [拟人状态](#拟人状态-humanlike_state) | `humanlike_state` 的 P0 维度和表达调制边界。 |
| [生命化学习](#生命化学习-lifelike_learning_state) | 新词、黑话、共同语境、用户画像证据和开口/沉默策略。 |
| [瑕疵模拟](#瑕疵模拟-fallibility_state) | 可选的误读、记忆模糊、轻微嘴硬、澄清、纠错和补偿状态。 |
| [心理筛查](#非诊断心理状态筛查) | 备用的长期状态建模，不做诊断。 |
| [本地文献知识库](#本地文献知识库) | 情绪、人格量化、心理筛查、拟人代理的仅本地研究资料。 |
| [测试与维护](#测试与维护) | 本地测试命令、远程烟测、gpt-5.5 性能基准、分支策略。 |
| [故障排查](#故障排查) | 常见问题和处理顺序。 |

---

## 当前版本与兼容范围

| 项目 | 当前值 |
| --- | --- |
| 插件目录名 | `astrbot_plugin_sylanne` |
| 显示名 | `Sylanne` |
| 当前版本 | `2.3.13` |
| AstrBot 版本 | `>=4.9.2,<5.0.0` |
| Python | `3.10+` |
| 许可证 | `GPL-3.0-or-later` |
| 运行时第三方依赖 | 当前无额外依赖，见 `requirements.txt` |

`2.3.13` 保留 Sylanne 自有记忆知识库、`2.1.0` 只读记忆查询入口、`2.1.3` Agent-owned context 即时聊天修复、`2.2.0` AstrBot Embedding 提供商驱动的向量召回、`2.3.0` 可视化记忆设置 Page、`2.3.8` 即时聊天短答锚定修复、`2.3.9` 哈基米/Gemini 空回复规避、`2.3.10` 完整上下文回填、`2.3.11` 内部工具统一隐藏和 `2.3.12` 主动聊天反馈修复，并进一步修复 LLM 等待期用户追发上下文丢失与碎片完整性等待过长问题。核心情绪、回复后后台评估（post）、`group_atmosphere_state`、`humanlike_state`、`lifelike_learning_state`、`personality_drift_state`、Sylanne 自有记忆、即时聊天节奏和欺骗/操控/逃责类动作阻断默认自动运行；道德修复、瑕疵模拟、心理筛查等实验/维护模块仍由配置者显式打开。

发布包会包含运行代码、README、CHANGELOG、LICENSE、配置结构（schema）、docs 和 `docs/assets/` 中的聚合图表与吉祥物素材，例如 `docs/assets/sylanne-mascot.gif`、`docs/assets/sylanne-mascot-card.svg` 和 `docs/assets/workflow_and_proactive.svg`；不会包含 `tests/`、`scripts/`、`literature_kb/`、`personality_literature_kb/`、`psychological_literature_kb/`、`humanlike_agent_literature_kb/`、`raw/`、`output/`、`dist/` 等开发、研究、原始样本或缓存目录。

### 2.3.13 当前版本发布记录

`v2.3.13` 合并在 `main` 上，对外安装版本由 `metadata.yaml` 和 `main.py @register(...)` 共同声明为 `2.3.13`。本版按版本规则提升第三位版本号：修复 LLM 等待期用户追发上下文丢失、碎片完整性等待上限过长和工作流图表达问题，不改变公共 API 版本；公共 API 版本仍保持 `1.0`，schema 仍保持向后兼容。

当前版本的主要变化：

| 类别 | 结果 |
| --- | --- |
| Agent 上下文归属 | 主聊天上下文仍交给 AstrBot Agent/pipeline；Sylanne 不再重放大段历史，只补短状态摘要、短记忆召回和已发/未发投递事实。 |
| 等待期追发合并 | 如果用户在上一轮 LLM 尚未产出可用回复前继续补充，Sylanne 会注入 `[sylanne_active_agent_followup_merge]`，把前一条 pending 用户消息和当前消息合并为同一连续意图，避免只回复最后一句。 |
| 合并落点 | 追发合并发生在 `context_text = _request_to_text(request)` 之前，`_last_request_text`、主 LLM 临时上下文和预响应情绪评估都会看到同一份合并事实；这不是长期上下文重放，只保留同会话、同说话人、短时间内的 pending 用户 turn。 |
| 用户纠正保留 | 「我昨晚十点多睡的啦」「没有啊我早早起床啦」这类事实纠正会被识别为高优先级上下文，并短暂作为 user 上下文带到下一轮。 |
| 旧猜测压制 | 用户已经纠正睡眠/作息事实后，后续回复不应继续追问或暗示“是不是没睡/熬夜/撒谎”，避免关心模板压过用户事实。 |
| 内部工具统一隐藏 | Sylanne 自己的 LLM Tool schema 对所有主聊天模型隐藏，避免模型在内部状态工具选择阶段空回、外泄工具 JSON 或增加不必要延迟。 |
| bot/Agent 接管 | 情绪、记忆、碎片整合、即时聊天接管和状态查询入口交给 bot/Agent 路径、命令、公共 API 与设置 Page；主 LLM 不需要直接看到 Sylanne 内部工具。 |
| 外部工具保留 | `search_web` 等外部插件工具仍按 AstrBot Agent 原生工具循环保留；隐藏范围只限 Sylanne 自己的状态/记忆/诊断工具 schema。 |
| 可见输出 guard | Gemini 风险模型每轮都会追加一条极短兼容提醒；无工具时要求直接输出可见自然语言，有外部工具时要求返回有效 `tool_calls/function_call` 或可见自然语言，减少“只有不可见推理、用户端空回复”的情况。 |
| 短答锚定修复 | 上一轮 bot 如果问了“喝了杯什么呀？这么神奇，一喝就困？”这类连续问句，用户下一轮只回“咖啡啊”时，Sylanne 会把它视为对上一轮问题的回答，而不是理解成“用户现在又要冲咖啡”。 |
| 二次澄清 guard | 用户说“我只是想确认嵌入模型记忆模块”这类二次澄清时，会注入复读抑制 guard：上一轮 assistant 原文只用于事实和指代，不允许照抄上一轮比喻、句式和段落结构。 |
| 问句簇保留 | `realtime_assistant_history_shadow` 抽取未闭合问题时，会保留临近短问句和承接短句，避免只留下最后一个问号导致语义槽位丢失。 |
| 短答提示增强 | 注入给主 LLM 的 `[sylanne_realtime_pending_bot_question]` 现在明确说明：名词或短答默认是在补全上一轮问题槽位，不要当成用户正在发起新的行动或命令。 |
| LLM 切换上下文修复 | `on_llm_request` 现在每轮实时读取当前主聊天 provider 来判定上下文归属；`provider_id_cache_ttl_seconds` 仍用于内部评估 provider 获取，但不再决定主回复请求是否进入 Gemini 兼容模式。 |
| 评估 provider 隔离 | `emotion_provider_id` 只影响内部情绪/碎片判断等评估调用，不再把主聊天请求强行判定为 Gemini；主 LLM 切到 gpt、deepseek、mimo 等模型后会恢复 Sylanne 的短状态、短记忆和即时聊天风格注入。 |
| Gemini 识别收窄 | `safe-non-gemini-assessor`、`non-gemini-provider` 这类 provider 名不会再因为包含字符串 `gemini` 被误判成高风险 Gemini；明确的 `google/gemini-*`、`gemini-*` 仍会进入兼容保护。 |
| 工具返回契约 | `query_agent_state_tool` 现在直接 `return` JSON 字符串给 AstrBot 工具循环；不再走 `event.plain_result(...)`，因此不会被 runner 误判为“没有返回值，或者已将结果直接发送给用户”。 |
| 自有记忆知识库 | 每条长期记忆独立存储，包含稳定 `memory_id`、摘要、情绪签名、关系签名、深度、置信度、证据次数、召回次数、真实时间衰减参数和自动动力学快照。 |
| 向量语义召回 | 可选择 AstrBot 已配置的 Embedding 类型模型提供商；记忆保存 `semantic_embedding`、`embedding_provider_id`、向量更新时间和文本哈希，召回时融合关键词相似度与余弦相似度。 |
| 记忆设置 Page | 在 AstrBot 插件详情页打开『记忆设置』即可下拉或点击卡片选择 Embedding 提供商；`sylanne_memory_embedding_provider_id` 也声明为 provider 选择项，留空表示自动选择第一个可用提供商。 |
| 碎片语义 gate | 当本地规则准备释放碎片窗口时，会先调用判断 LLM 输出极短 JSON，确认用户是否已经说完；命中上一轮 bot 问题的短答会跳过该 gate，减少“咖啡啊”这类回答的延迟。 |
| 慢速分段修复 | LLM gate 判定未完成后会写入语义等待窗口，后续同一用户在真实时间上限内继续补充时仍会被合并，即使间隔超过本地短窗口。 |
| 上限释放 | 默认探测等待保持 `0.25s`，语义等待上限降到 `4s` 且有运行时硬上限；如果判断为未完成但用户真的停住，达到上限后会释放合并后的碎片意图，避免把即时聊天时间耗在死等上。 |
| Gemini 工具轮次保护 | Gemini 系模型仍会追加极短 guard，要求模型返回可见自然语言或有效 `tool_calls/function_call`；Sylanne 内部工具已统一隐藏，外部工具仍保留。 |
| 统一工具归属 | `query_agent_state` 和 11 个细分工具继续作为插件内部兼容方法、命令/API 后端存在，但不再作为主 LLM Tool schema 暴露。 |
| 工具 JSON 外泄阻断 | 如果兼容层把 `query_agent_state`、情绪快照、运行时诊断等内部工具结果误作为最终 `completion_text` 交给发送阶段，Sylanne 会识别 `astrbot.*` 内部 `schema_version/kind`，清空默认发送内容并阻断用户可见发送；结构化工具调用仍交给 Agent 工具循环。 |
| 只读记忆查询 | 新增 `/sylanne_memory`、`/记忆查询`、`/查询记忆`、`/灵澜记忆` 和 `query_sylanne_memory(...)`，可检查记忆命中情况；查询不会强化或改写记忆。 |
| 关联联想召回 | 直接命中的记忆会在硬预算内带出少量相邻记忆；关联边由摘要相似度、层类型重叠、情绪接近度、时间接近度和巩固强度本地计算，不交给 LLM 随机决定。 |
| 强化与遗忘 | 只有真正注入 prompt 的记忆才会触发召回强化；长期无证据、无召回且深度/置信度很低的弱记忆会按真实时间剪枝，并清理悬空关联边。 |
| Agent 上下文归属 | 对话上下文交给 AstrBot Agent；Sylanne 只补短状态摘要、短记忆召回和投递事实，Gemini 高风险模型会进入 `gemini_agent_owned_context` 模式并跳过额外 prompt 注入。 |
| 即时聊天投递信封 | 主回复被接管时，Agent 历史会看到“已生成但未必已发送”的投递状态；用户插话后会记录已发/未发摘要，避免下一轮误以为旧回复已经完整送达。 |
| 主动聊天反馈闭环 | 后台调度默认更低频：正常约 15 分钟醒来一次，空闲约 30 分钟，同一会话约 1 小时内不重复复查；每次醒来会先结算上一条主动发言是否无人回应，并把用户可能在忙、休息或不方便聊天作为默认解释。`progress_check` 必须有明确进度证据，证据不足时沉默；如果只是想念用户，只允许低压力短句轻触达。 |
| 快速判断 LLM | 新增 `fast_assessor_provider_id` 和短上下文预算，用户碎片完整性、表情包一致性等简单 JSON 判断可走低推理快模型；复杂情绪观测和主动话题裁决仍走原判断 LLM。 |
| 上下文安全预算 | 召回结果只作为 `[sylanne_memory_recall]` 限长摘要注入，并继续受请求预算和官方上下文压缩清洗逻辑约束。 |
| 模块互斥自检 | 发布前覆盖自有记忆、主动发言、官方上下文压缩、即时聊天、公共 API、配置契约和包体预检，验证模块之间不会互相回灌或重复调用外部 LivingMemory。 |
| 工作流图 | `docs/assets/workflow_and_proactive.svg` 重绘为 2.3.13 版本，突出即时聊天、追发合并、Agent 工具循环、模型边界和主动聊天反馈；移除误导性的单点 Gemini 诊断节点，并修正中文字体和跨泳道箭头。 |
| 公开契约 | 插件版本为 `2.3.13`；公共 API 版本仍为 `1.0`，schema 仍保持 `astrbot.emotion_state.v2` 等版本化契约。 |

旧版本发布记录统一放在 `CHANGELOG.md`。README 只展示当前版本，避免插件管理页从历史段落误抓旧版本号。

运行时亮点可以按这条链路理解。这里直接使用静态图，避免部分手机端把流程图源码显示成大段文本：

![运行时总览](docs/assets/runtime_overview.svg)

<details>
<summary>历史预发布批次摘要（0.0.2-beta-pr-1 至 0.0.2-beta-pr-19）</summary>

| 本地迭代号 | 状态 | 对应任务 | 结果摘要 |
| --- | --- | --- | --- |
| `0.0.2-beta-pr-1` | 已完成 | 生命化学习核心状态 | 新增 `lifelike_learning_engine.py`，支持新词/黑话、用户画像证据、偏好、边界和真实时间半衰期。 |
| `0.0.2-beta-pr-2` | 已完成 | AstrBot 生命周期接入 | 接入 `on_llm_request`、KV、提示词注入、`/lifelike_state`、`/lifelike_reset` 和 `get_bot_lifelike_learning_state`。 |
| `0.0.2-beta-pr-3` | 已完成 | LivingMemory 写入注解 | `build_emotion_memory_payload(...)` 写入 `lifelike_learning_state_at_write`，冻结当时共同语境。 |
| `0.0.2-beta-pr-4` | 已完成 | 综合自我仲裁 | 综合自我模块使用共同语境决定轻问、短应、开口、安静或安全打断。 |
| `0.0.2-beta-pr-5` | 已完成 | 第三方公共 API | 导出 `LIFELIKE_LEARNING_SCHEMA_VERSION`、`LifelikeLearningServiceProtocol` 和 `get_lifelike_learning_service`。 |
| `0.0.2-beta-pr-6` | 已完成 | 配置和 README 契约 | `_conf_schema.json` 增加 9 个生命化学习配置项，并补齐命令、LLM 工具、LivingMemory 和公共 API 文档。 |
| `0.0.2-beta-pr-7` | 已完成 | 发布包和 zip 预检 | 打包脚本和 zip 预检强制包含 `lifelike_learning_engine.py`。 |
| `0.0.2-beta-pr-8` | 已完成 | 产品理念固化 | README 写入“更像生命，而不只是更强”和“代码开源，灵魂属于你”的共同语境解释。 |
| `0.0.2-beta-pr-9` | 已完成 | 全量本地验证 | 236 个单元测试、`py_compile`、`json.tool`、Node 语法检查、打包构建、zip 预检全部通过。 |
| `0.0.2-beta-pr-10` | 已完成 | 远程清理、上传和烟测 | 远程先删旧同名插件，再上传当前 zip；严格烟测通过，LivingMemory 仍可见。 |
| `0.0.2-beta-pr-11` | 已完成 | 真实时间人格漂移 | 新增 `personality_drift_engine.py`，人格偏移按真实时间半衰、短时门控和静态 persona 锚点缓慢变化，不能靠大量消息强刷。 |
| `0.0.2-beta-pr-12` | 已完成 | 人格漂移延迟优化与 20 次实机测试 | 复用单轮人格漂移状态、缓存读取不写回、空漂移免深拷贝；服务器清旧包后上传新包，20 次严格烟测全部通过。 |
| `0.0.2-beta-pr-13` | 已完成 | 延迟专项第一批优化 | 默认单阶段情绪评估、评估器超时回退、模型提供方短缓存、上下文裁剪、被动读取短路、引擎缓存和轨迹追加瘦身；延迟专项队列持久化到第 `200` 次迭代。 |
| `0.0.2-beta-pr-14` | 已完成 | 延迟专项第二批优化 | 请求/响应生命周期缓存配置开关、复用观测文本、空白响应提前返回、减少请求注入重复配置读取，并保留 KV 保存顺序。 |
| `0.0.2-beta-pr-15` | 已完成 | 延迟专项第三批优化 | 生命化学习状态减少 `to_dict/from_dict` 往返，热路径正则预编译，主动开口策略解析词典只转换一次。 |
| `0.0.2-beta-pr-16` | 已完成 | 延迟专项第四批优化 | `_request_to_text()` 只读取尾部上下文、被动缓存读取移除整状态序列化比较、LivingMemory 写入开关集中读取、禁用人格漂移早退、KV key 清洗复用缓存。 |
| `0.0.2-beta-pr-17` | 已完成 | 延迟专项第五批优化 | 请求默认无状态工作早退、状态轻查询直读、低信号人格漂移不写 KV，并新增本地热路径基准测试。 |
| `0.0.2-beta-pr-18` | 已完成 | 旧版 5 秒目标 SLA 尝试 | 当时曾把 `assessor_timeout_seconds` 调低来保护主链路；当前 `1.1.0` 已改为默认不限制硬超时，避免慢推理模型被误伤。 |
| `0.0.2-beta-pr-19` | 已完成 | 真实链路并发等待削减 | `on_llm_response` 并发预取道德修复状态，LivingMemory 写入并发获取可选状态快照，保持注解结构和保存顺序。 |

</details>

<details>
<summary>展开逐轮工程迭代明细（第 11-200 次）</summary>

| 迭代 | 状态 | 内容 | 验证/结果 |
| --- | --- | --- | --- |
| 11 | 已完成 | 持久化迭代计划、编写远程烟测脚本、强化安全/人格/记忆契约 | 122 个单元测试、py_compile、Node 语法检查、远程烟测 |
| 12 | 已完成 | 完善 README，加入可复用远程烟测流程和环境变量示例 | 123 个单元测试、py_compile、Node 语法检查、远程烟测 |
| 13 | 已完成 | 增加 LivingMemory 适配示例测试，覆盖关闭原始快照和关闭拟人状态的场景 | 126 个单元测试、py_compile、Node 语法检查、远程烟测 |
| 14 | 已完成 | 强化心理模块用户可见文本的非诊断表述测试 | 128 个单元测试、py_compile、Node 语法检查、远程烟测 |
| 15 | 已完成 | 对照实现复查公共 API 文档并补充迁移说明 | 129 个单元测试、py_compile、Node 语法检查、远程烟测 |
| 16 | 已完成 | 通过排除原始知识库缓存精简部署包，记录发布包契约，并在安装路径安全前保持远程烟测只读 | 132 个单元测试、py_compile、打包构建、Node 语法检查、git diff 检查、远程烟测 |
| 17 | 已完成 | 通过 WebUI `install-upload` 在远程测试服部署插件，并以 `ASTRBOT_EXPECT_PLUGIN=astrbot_plugin_sylanne` 重跑烟测 | 上传安装脚本、136 个单元测试、py_compile、打包构建、远程安装、带目标插件断言的远程烟测 |
| 18 | 已完成 | 强化远程烟测：目标插件必须已安装，且不能出现在失败插件记录中 | 136 个单元测试、Node 语法检查、git diff 检查、失败插件断言远程烟测 |
| 19 | 已完成 | 强化远程烟测：加入目标插件运行时元数据断言，包括启用状态、版本、显示名和插件 API 摘要 | 136 个单元测试、py_compile、打包构建、Node 语法检查、git diff 检查、版本/显示名断言远程烟测 |
| 20 | 已完成 | 通过完整检查 zip 内容强化远程上传预检，并记录可上传发布包契约 | 136 个单元测试、py_compile、打包构建、Node 语法检查、git diff 检查、版本/显示名断言远程烟测 |
| 21 | 已完成 | 增加远程安装 zip 预检失败用例的本地测试，不调用远程服务器 | 141 个单元测试、py_compile、打包构建、Node 语法检查、git diff 检查、版本/显示名断言远程烟测 |
| 22 | 已完成 | 复查 git 分支/打包状态，准备可维护的分支拆分或提交暂存方案 | 141 个单元测试、README 契约测试、git diff 检查、版本/显示名断言远程烟测 |
| 23 | 已完成 | 新增仓库维护清单，用于提交当前基线并同步功能分支，避免丢失未提交改动 | 141 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 24 | 已完成 | 先在 `main` 提交已验证基线，再从干净基线同步集成/维护分支 | 提交 976ee99；分支同步前工作区干净；所有文档列出的维护分支同步到 976ee99 |
| 25 | 已完成 | 分支同步后做最终验证并写收尾摘要 | 141 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 26 | 已完成 | 修复远程烟测 UI 检测，避免只显示显示名的插件卡片被误判为目标插件缺失 | 141 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 27 | 已完成 | 当失败插件 API 不健康时让远程烟测失败 | 141 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 28 | 已完成 | 让远程烟测 WebUI 探测更确定，并把 UI 字段标记为尽力诊断 | 141 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 29 | 已完成 | 将旧字段 `pageData.hasExpectedPlugin` 作为综合 UI 检查的兼容别名 | 141 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 30 | 已完成 | 新增远程烟测必需只读端点的集中 API 健康诊断 | 141 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 31 | 已完成 | 记录远程烟测和打包预检命令使用 Codex 内置 Node 的回退方式 | 141 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 32 | 已完成 | 锁定内置 Node 回退文档的顺序和契约测试一致性 | 143 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 33 | 已完成 | 刷新 README 测试矩阵，覆盖扩展后的远程烟测契约 | 143 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 34 | 已完成 | 将远程烟测文档中的版本和显示名断言锁定到 `metadata.yaml` | 144 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 35 | 已完成 | 锁定 README 徽章和 AstrBot 兼容徽章编码与 `metadata.yaml` 一致 | 145 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 36 | 已完成 | 要求发布 zip 包的元数据身份匹配预期插件目录 | 147 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 37 | 已完成 | 要求公共 API 服务发现匹配版本化 schema 契约 | 150 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 38 | 已完成 | 使 humanlike 路线文档与当前记忆载荷和配置 schema 名称对齐 | 151 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 39 | 已完成 | 收敛 humanlike 路线中有关开关和注解时间戳的剩余漂移 | 151 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 40 | 已完成 | 将插件身份引用锁定到 `metadata.yaml` 的 name | 156 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 41 | 已完成 | 锁定 `assessment_timing` 的运行时、schema、README 选项和 typed config table 覆盖 | 157 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 42 | 已完成 | 锁定公共 API/服务发现和命令文档契约 | 160 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 43 | 已完成 | 锁定 LLM 工具注册名与 README 文档一致 | 161 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 44 | 已完成 | 刷新 README 测试矩阵，覆盖最近锁定的命令、配置、公共 API 和元数据契约 | 162 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 45 | 已完成 | 把心理筛查 alpha 最小/最大默认值锁定为显式 schema 契约 | 162 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 46 | 已完成 | 强化发布打包，防止自包含和预检插件名漂移 | 165 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 47 | 已完成 | 澄清公共 API README 示例中的第三方插件安全回退行为 | 166 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 48 | 已完成 | 锁定心理筛查非诊断公共 API 返回语义 | 167 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 49 | 已完成 | 增加机器可读的心理严重功能受损和睡眠受扰风险标记 | 168 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、泄漏扫描、远程烟测 |
| 50 | 已完成 | 导出稳定的心理风险布尔字段契约，并澄清 README/docs 中的嵌套访问方式 | 170 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 51 | 已完成 | 在公共 API 中复用心理风险布尔字段 tuple，防止契约漂移 | 170 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 52 | 已完成 | 增加远程烟测失败插件摘要，区分无关失败和目标插件失败 | 170 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 53 | 已完成 | 在远程烟测输出中增加目标插件综合通过摘要 | 170 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 54 | 已完成 | 修复发布包按插件包名导入公共 API 时的导入路径 | 171 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、泄漏扫描、远程烟测 |
| 55 | 已完成 | 锁定发布包运行根文件，并让 README 安装树与发布边界一致 | 172 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、泄漏扫描 |
| 56 | 已完成 | 使上传 zip 预检必需条目与发布运行根契约一致 | 172 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、泄漏扫描 |
| 57 | 已完成 | 要求上传预检和发布清单包含依赖声明 | 172 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、泄漏扫描 |
| 58 | 已完成 | 锁定 README 中的 `py_compile` 命令和失败上传清理文档到当前发布包契约 | 172 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、泄漏扫描 |
| 59 | 已完成 | 新增道德修复状态模块，作为欺骗/作恶模拟的安全替代方案 | 193 个单元测试、py_compile、json.tool、打包构建、打包预检、Node 语法检查、git diff 检查、泄漏扫描 |
| 60 | 已完成 | 声明 GPL-3.0-or-later 许可证，并把 LICENSE 纳入发布包契约 | 194 个单元测试、py_compile、json.tool、打包构建、打包预检、Node 语法检查、git diff 检查、泄漏扫描 |
| 61 | 已完成 | 构建综合自我状态总线，融合情绪、拟人、道德修复和心理快照为统一公共契约 | 116 个定向测试、py_compile、json.tool |
| 62 | 已完成 | 增加基于证据权重的因果轨迹摘要，使各模块状态变化可解释 | `tests/test_integrated_self.py`、`tests/test_public_api.py` |
| 63 | 已完成 | 增加确定性回放/模拟包，用于不触碰 KV 存储地测试状态演化 | 确定性回放包校验和测试 |
| 64 | 已完成 | 增加策略规划层，把综合状态转成允许的表达调制和修复动作 | 策略计划测试保留阻断动作和修复动作 |
| 65 | 已完成 | 增加 schema 迁移和兼容性探针，面向未来公共契约 | 兼容性探针测试和公共 API 契约测试 |
| 66 | 已完成 | 增加维护者导出/导入诊断，同时避免泄露原始 persona 或不安全策略内容 | 脱敏诊断测试 |
| 67 | 已完成 | 增加低成本部署的降级模式和令牌预算档位 | `integrated_self_degradation_profile` schema/文档/测试 |
| 68 | 已完成 | 扩展 LivingMemory 集成契约，加入综合自我状态注解 | `state_annotations_at_write` 信封测试 |
| 69 | 已完成 | 围绕综合自我状态面强化发布、README 和远程烟测契约 | 208 个全量测试、33 个打包/远程契约测试、py_compile、json.tool、Node 语法、打包预检、泄漏扫描 |
| 70 | 已完成 | 运行全量验证、远程烟测、分支同步，并写完整的革命性迭代交接记录 | 实现提交 `e86735b`；最终状态已记录；远程烟测通过；维护分支同步到最新 HEAD |
| 71 | 已完成 | 重写 README 为可发布插件首页，补齐项目定位、工作流、配置、边界、排障和维护说明 | 208 个单元测试、py_compile、json.tool、Node 语法检查、打包构建、打包预检；GitHub 鉴权受阻 |
| 72 | 已完成 | 创建 GitHub 仓库、更新仓库元数据、设置预发布版本、推送已验证 main 分支并发布预发布包 | 公共仓库和 `v0.0.1-beta` 预发布已创建；发布 zip SHA256 `3133f89e96ce5e124083da0867765f2d5d6d6b2ef074d0963a55eedf0de833ef` |
| 73 | 已完成 | 按 GitHub 官方数学表达式语法优化公式渲染 | 保留 GitHub fenced math；禁用危险宏由 `tests/test_document_math_contract.py` 锁定；212 个测试通过；发布资产已刷新 |
| 74 | 已完成 | 增加代表性文献模型论证、折叠完整推导和更严谨的公式记号 | README/theory 默认摘要、折叠推导、DOI 文献依据、符号清理（`O_t`、`H_t`、`F_t`）；213 个测试、py_compile、json.tool、Node 语法、打包构建、打包预检、git diff 检查 |
| 75 | 已完成 | 澄清远程版本漂移和“已安装不覆盖”的上传诊断 | `expectedPluginDrift`、`installOutcome=already_installed_no_overwrite`、README/checklist 文档；213 个测试、py_compile、json.tool、Node 语法、打包构建、打包预检；严格远程烟测确认退出码 7 漂移，非严格远程烟测通过 |
| 76 | 已完成 | 发布 `0.0.2-beta`：加入更严格的人格量化模型、2 万条人格文献元数据知识库、更新公式/文档/测试、远程烟测和预发布上传 | 已发布 `v0.0.2-beta` 预发布；216 个测试、py_compile、json.tool、Node 语法检查、打包构建、zip 预检、git diff 检查、严格远程漂移检查和非严格远程烟测完成 |
| 77 | 已完成 | 新增持久化生命化学习状态，记录新词、本地黑话、用户画像事实、偏好和对话节奏 | `lifelike_learning_engine.py`；8 维状态；真实时间半衰期；单元测试；不泄露原始消息 |
| 78 | 已完成 | 把生命化学习接入 AstrBot 生命周期、KV、提示词注入、重置后门、命令和 LLM 工具 | `on_llm_request`、KV 缓存、`/lifelike_state`、`/lifelike_reset`、`get_bot_lifelike_learning_state` |
| 79 | 已完成 | 扩展 LivingMemory 注解，使记忆写入时冻结当时学到的共同语境状态 | `lifelike_learning_state_at_write`；公共 API 记忆载荷和综合信封测试 |
| 80 | 已完成 | 把生命化学习融合进综合自我仲裁，使 bot 能决定开口、短应、追问、沉默、打断或修复 | 综合自我姿态和澄清/安静陪伴策略测试 |
| 81 | 已完成 | 发布可选公共 API helper，供第三方插件读取黑话/画像/主动性快照而无需读 KV | `LIFELIKE_LEARNING_SCHEMA_VERSION`、`LifelikeLearningServiceProtocol`、`get_lifelike_learning_service` |
| 82 | 已完成 | 增加生命化学习的配置 schema 和 README 覆盖，包括隐私边界、重置控制和令牌预算行为 | 9 个生命化学习配置键、命令/工具文档、LivingMemory 文档、公共 API 文档 |
| 83 | 已完成 | 更新发布打包和 zip 预检，确保新运行时模块始终被包含并检查身份 | 打包脚本、zip 预检、打包测试和 README/checklist 运行文件文档 |
| 84 | 已完成 | 基于当前知识库补充“更像生命，而不只是更强”和“代码开源，灵魂属于你”的产品理论文档 | README 记录生命化原则、共同语境学习和部署者拥有灵魂的边界 |
| 85 | 已完成 | 生命化学习栈落地后运行完整本地验证 | 236 个测试、py_compile、json.tool、打包构建、zip 预检、Node 检查、diff 检查 |
| 86 | 已完成 | 服务器验证前清理旧同名插件，再安装/测试当前包并记录 LivingMemory 可见性 | 远程清理仅删除 `astrbot_plugin_sylanne`；LivingMemory 仍可见；上传和严格烟测通过 |
| 87 | 已完成 | 在 README 记录完成的 `0.0.2-beta-pr-x` 本地预发布迭代序列，并用测试锁定顺序 | README 表记录 `0.0.2-beta-pr-1` 到 `0.0.2-beta-pr-10`；契约测试 `test_readme_records_beta_pr_iterations_in_order` |
| 88 | 已完成 | 增加真实时间人格漂移，使 persona 在经过时间约束下缓慢变化，而不是按消息量变化 | 引擎/API/文档/测试已实现；上下文不会被重放为新漂移事件；255 个测试、py_compile、json.tool、打包构建、Node 检查、zip 预检、diff 检查通过 |
| 89 | 已完成 | 优化人格漂移延迟并运行 20 次远程实机烟测 | 单轮漂移复用、缓存读取不写回、空漂移无拷贝快速路径；258 个测试、py_compile、json.tool、打包构建、zip 预检、远程清理/上传、20/20 严格烟测通过 |
| 90 | 已完成 | 延迟第一批基线和评估器单阶段默认值 | 默认 `assessment_timing` 为 `post`；缩小评估器上下文；增加超时回退、provider-id TTL 缓存、请求文本裁剪、被动读取不写回、引擎缓存和轨迹追加微优化 |
| 91 | 已完成 | 增加评估器超时和 provider 缓存的延迟回归测试 | `tests/test_astrbot_lifecycle.py` 覆盖超时回退和 provider-id TTL 缓存 |
| 92 | 已完成 | 增加情绪和辅助状态被动缓存读取不写 KV 的回归覆盖 | `tests/test_public_api.py` 覆盖缓存被动读取不写回 KV |
| 93 | 已完成 | 锁定请求上下文裁剪和评估器令牌预算行为 | `_request_to_text` 限制总上下文并保留 `[current_user]`；schema/README 记录限制 |
| 94 | 已完成 | 按 persona 指纹缓存情绪引擎 | `_engine_for_persona` 最多缓存 16 个引擎，并为测试创建实例做懒初始化 |
| 95 | 已完成 | 减少各状态引擎的轨迹追加分配 | Humanlike、lifelike、人格漂移和道德修复只追加保留后的切片 |
| 96 | 已完成 | 记录延迟优先默认值和调参开关 | README 记录延迟优先默认值和 `0.0.2-beta-pr-13` 完成 |
| 97 | 已完成 | 运行延迟第一批的生命周期/公共/配置/引擎定向测试 | 135 个定向测试通过 |
| 98 | 已完成 | 运行延迟第一批完整本地验证和打包预检 | 262 个测试通过；py_compile/json.tool/打包构建/Node 检查/zip 预检/diff 检查通过 |
| 99 | 已完成 | 记录第一批基准测试并确定下一批延迟方向 | 本地测试套件耗时 10.926 秒；zip 大小 178469 字节；下一批聚焦请求内配置/状态复用和减少无效写入 |
| 100 | 已完成 | 缓存请求内生命周期标志 | `on_llm_request` 每次 hook 只读取一次 assessment timing、模块启用标志、注入标志和安全边界 |
| 101 | 已完成 | 复用请求观测文本 | Humanlike、lifelike 和道德修复观测共享一份预构建的 `request_observation_text` |
| 102 | 已完成 | 复用响应生命周期标志 | `on_llm_response` 缓存 timing、道德修复标志、人格漂移标志和安全边界 |
| 103 | 已完成 | 避免请求注入时 helper 层重复读取安全开关 | 请求注入直接使用缓存的安全边界调用 `build_state_injection` |
| 104 | 已完成 | 增加空白响应早退 | 空白响应在加载 persona/状态前返回；生命周期测试断言不会加载 persona 或状态 |
| 105 | 已完成 | 移除人格漂移应用后的重复 persona 模型深拷贝 | `_ensure_persona_state` 已同步漂移后的 persona 模型，调用方不再额外复制 |
| 106 | 已完成 | 保持保存顺序不变 | 未合并情绪/KV 保存，因为异常路径持久化语义会改变 |
| 107 | 已完成 | 运行第二批生命周期/公共 API 定向测试 | 95 个生命周期/公共 API 定向测试通过 |
| 108 | 已完成 | 运行延迟第二批完整本地验证 | 262 个测试通过；py_compile/json.tool/打包构建/Node 检查/zip 预检/diff 检查通过 |
| 109 | 已完成 | 记录第二批基准测试并确定下一批延迟方向 | 本地测试套件耗时 11.799 秒；zip 大小 178469 字节；下一批聚焦对象拷贝削减和引擎热路径微优化 |
| 110 | 已完成 | 减少生命化学习被动用户画像复制成本 | 用有界 `_copy_user_profile` 替代 `to_dict/from_dict` 往返；生命化学习定向测试通过 |
| 111 | 已完成 | 减少生命化学习词典复制成本 | 用 `_copy_jargon_entry` 替代每条序列化往返；生命化学习定向测试通过 |
| 112 | 已完成 | 减少生命化学习画像更新复制成本 | `_update_profile` 在应用证据前直接有界克隆字段；生命化学习定向测试通过 |
| 113 | 已完成 | 避免公共状态词典重复解析 | `derive_initiative_policy` 对每个原始 `JargonEntry` 最多转换一次；生命化学习定向测试通过 |
| 114 | 已完成 | 预编译道德欺骗和伤害线索正则 | 将线索模式移动到模块级编译元组；道德修复测试通过 |
| 115 | 已完成 | 预编译道德修复/行动线索正则 | 承担责任、道歉、补偿和逃避线索不再每次调用时编译；道德修复测试通过 |
| 116 | 已完成 | 预编译心理红旗正则 | 自伤、他伤和严重功能受损信号使用编译元组；心理筛查测试通过 |
| 117 | 已完成 | 预编译拟人危机场景正则 | 医疗/危机场景检测使用编译元组；拟人测试通过 |
| 118 | 已完成 | 在 README 序列中记录延迟第三批 | README 记录 `0.0.2-beta-pr-14` 和 `0.0.2-beta-pr-15`；契约测试期望 pr-1 到 pr-15 |
| 119 | 已完成 | 运行第三批定向验证 | 33 个定向引擎测试和触及运行模块的 py_compile 通过 |
| 120 | 已完成 | 避免 `_request_to_text` 完整复制上下文 | 加入 `_tail_items()`，请求上下文裁剪只读取最后 8 条；生命周期尾部上下文测试通过 |
| 121 | 已完成 | 锁定请求尾部上下文行为 | 新增回归测试，证明只需要尾部上下文时不会转换旧上下文 |
| 122 | 已完成 | 移除过期缓存的 `to_dict()` 比较 | 用 `_passive_update_changed()` 替代被动读取深序列化比较 |
| 123 | 已完成 | 保留被动缓存不写入契约 | 轻量比较改造后，公共 API 缓存被动读取测试通过 |
| 124 | 已完成 | 复用 LivingMemory 写入开关 | `build_emotion_memory_payload()` 每次调用只读取一次记忆注解开关 |
| 125 | 已完成 | 禁用人格漂移快照时提前返回 | 禁用漂移快照不再加载 persona 画像或漂移状态 |
| 126 | 已完成 | 缓存脱敏 KV 会话 key | 新增 `_safe_session_key()`，供情绪、心理、拟人、生命化、漂移和道德 KV key 共用 |
| 127 | 已完成 | 锁定 KV key 兼容性 | 新增 `/` 和 `\\` 会话 key 在所有 KV 前缀下的回归测试 |
| 128 | 已完成 | 在 README 序列中记录延迟第四批 | README 记录 `0.0.2-beta-pr-16`；契约测试期望 pr-1 到 pr-16 |
| 129 | 已完成 | 运行第四批定向验证 | 98 个生命周期/公共 API 测试和触及模块 py_compile 通过 |
| 130 | 已完成 | 请求默认无工作早退 | 无 pre 评估、无注入、可选模块关闭时，`on_llm_request` 在请求文本缓存后直接返回 |
| 131 | 已完成 | 懒构建请求观测文本 | 仅在 humanlike、lifelike 或道德模块启用时才拼接观测文本 |
| 132 | 已完成 | 低信号漂移不写入 | 只有时间诊断/轨迹变化的低信号人格漂移更新会跳过 KV 保存 |
| 133 | 已完成 | 轻量情绪公共值读取 | 情绪值、后果和关系 API 直接加载状态，而不是构建完整快照 |
| 134 | 已完成 | 轻量辅助公共值读取 | Humanlike、lifelike 策略、人格漂移、道德修复和心理值走直接状态路径 |
| 135 | 已完成 | 热路径基准脚本 | 新增 `scripts/benchmark_plugin_hot_path.py`，用于本地 hook 延迟和超时保护测量 |
| 136 | 已完成 | 提示词维度 schema 常量化 | 评估提示词使用模块级维度 schema，避免每次调用 join/split |
| 137 | 已完成 | 旧版评估器 SLA 默认值 | 历史上曾把评估器超时作为延迟保护；当前版本默认取消硬超时，只在压测或成本保护时手动开启 |
| 138 | 已完成 | 人格漂移正则预编译 | 漂移启发线索正则只编译一次，并用语义回归测试覆盖 |
| 139 | 已完成 | 响应道德状态并发预取 | `on_llm_response` 在响应后情绪评估时并发加载道德状态，同时保留保存顺序 |
| 140 | 已完成 | LivingMemory 快照并发获取 | 记忆载荷在组装注解前并发获取可选模块快照 |
| 141 | 已完成 | 延迟 PR 文档记录 | README 记录 `0.0.2-beta-pr-17` 到 `0.0.2-beta-pr-19`，测试期望该序列 |
| 142 | 已完成 | 请求辅助状态并发加载 | Humanlike、lifelike 和道德请求状态并发加载；更新/保存仍保持原顺序 |
| 143 | 已完成 | 慢辅助加载基准 | 增加基准用例，证明三个 20 ms 辅助加载约 31 ms 完成，而非串行 60 ms |
| 144 | 已完成 | 响应慢道德加载基准 | 增加响应后评估器和道德状态并发加载基准 |
| 145 | 已完成 | 记忆慢快照基准 | 增加 LivingMemory 可选快照并发获取基准 |
| 146 | 已完成 | 保留超时保护基准 | 慢评估器超时保护继续出现在基准输出中，用于 5 秒 SLA |
| 147 | 已完成 | 第六批基准复查 | 请求、响应和记忆慢等待并发场景均在假 20 ms 等待下约 31 ms 完成 |
| 148 | 已完成 | 第六批验证 | 请求并发改造后，全量测试和 py_compile/json/diff 检查通过 |
| 149 | 已完成 | 第六批交接 | progress 记录下一方向：谨慎尝试保存并发或综合快照并发，并补明确顺序测试 |
| 150 | 已完成 | 第七批基准刷新 | 重新运行热路径基准，确认请求、响应和记忆慢等待基线 |
| 151 | 已完成 | Fallibility 快速状态桩绑定 | 基准脚本绑定 fallibility load/save，使测量覆盖当前运行时模块面 |
| 152 | 已完成 | 无工作请求显式排除 fallibility | no-work 基准显式关闭 fallibility，避免默认早退用例被隐藏模块影响 |
| 153 | 已完成 | 可选模块基准纳入 fallibility | optional modules 基准启用 fallibility 且注入强度为 0，覆盖完整本地模拟路径 |
| 154 | 已完成 | 请求慢 fallibility 并发基准 | 四个 20 ms 请求辅助加载仍约 31 ms 完成，没有串行为约 80 ms |
| 155 | 已完成 | 响应 fallibility 并发基准 | 新增 moral + fallibility + assessor 慢等待重叠基准 |
| 156 | 已完成 | 记忆 fallibility 快照基准 | LivingMemory 慢快照 fan-out 纳入 fallibility 注解获取 |
| 157 | 已完成 | Fallibility 记忆并发测试 | 公共 API 记忆 fan-out 测试断言 `fallibility_state_at_write` 存在 |
| 158 | 已完成 | `_tail_items()` 分配削减 | 尾部上下文 helper 返回序列切片或元组，避免额外 list 拷贝 |
| 159 | 已完成 | 请求上下文无复制验证 | 生命周期尾部上下文测试和 py_compile 通过 |
| 160 | 已完成 | 生命化风格正则预编译 | 风格偏好提取正则移动到模块级编译 |
| 161 | 已完成 | 生命化边界正则预编译 | 边界提示提取正则移动到模块级编译 |
| 162 | 已完成 | 生命化提取回归验证 | 触及的生命周期/公共 API 测试覆盖通过 |
| 163 | 已完成 | Emotion service 方法常量化 | `get_emotion_service()` 复用 required-method 常量，避免每次调用分配大 tuple |
| 164 | 已完成 | Emotion service 版本常量化 | 服务发现复用 expected-version 映射，避免每次调用重建 |
| 165 | 已完成 | 服务发现契约同步 | AST 契约测试改为锁定模块级公共 API 方法常量 |
| 166 | 已完成 | 可选服务方法常量化 | Humanlike、moral、lifelike、personality drift、fallibility helper 复用模块级方法常量 |
| 167 | 已完成 | 可选服务契约验证 | 37 个公共 API 服务发现测试通过 |
| 168 | 已完成 | LivingMemory 情绪快照重叠 | 记忆写入时核心情绪快照与可选模块快照同时启动 |
| 169 | 已完成 | LivingMemory 全快照 gather | 情绪 + 可选快照进入同一个 `asyncio.gather()` 等待窗口 |
| 170 | 已完成 | 记忆载荷组装顺序保留 | 快照并发获取后仍按原顺序组装注解和原始快照字段 |
| 171 | 已完成 | 情绪/可选快照重叠测试 | 新增测试证明慢情绪快照会与五个慢可选快照并发 |
| 172 | 已完成 | 记忆全快照基准用例 | 新增 `memory_slow_emotion_and_snapshot_fanout` 基准项 |
| 173 | 已完成 | 记忆全快照基准验证 | 六个假 20 ms 快照约 31 ms 完成，而不是串行约 120 ms |
| 174 | 已完成 | 人格关键词小写缓存 | persona keyword traits 使用内部预小写副本 |
| 175 | 已完成 | 人格词典小写缓存 | 13 维人格词典的正/负关键词使用内部预小写副本 |
| 176 | 已完成 | persona 文本单次 lower | `build_persona_profile()` 和 `build_personality_model()` 每次调用只 lower 一次文本 |
| 177 | 已完成 | `_keyword_score()` 快路径 | 关键词计分 helper 支持传入预小写文本，循环中不再反复 `keyword.lower()` |
| 178 | 已完成 | `_signed_keyword_score()` 快路径 | 正负关键词扫描复用同一份预小写 persona 文本 |
| 179 | 已完成 | 人格语义验证 | 47 个情绪/人格漂移测试通过，确认模型语义未漂移 |
| 180 | 已完成 | 基准覆盖复查 | 热路径输出包含 fallibility 和 emotion+optional memory fan-out 两类新指标 |
| 181 | 已完成 | 默认请求基准检查 | `request_default_post_inject` 保持亚毫秒级本地开销 |
| 182 | 已完成 | 无工作请求基准检查 | `request_no_request_work` 保持近零本地开销 |
| 183 | 已完成 | 可选模块基准检查 | 无假等待时可选模块本地模拟路径约 1-2 ms |
| 184 | 已完成 | 慢请求辅助基准检查 | 四个慢请求辅助加载仍被限制在单个等待窗口 |
| 185 | 已完成 | 响应后评估基准检查 | 快评估器桩下响应 hook 保持亚毫秒级 |
| 186 | 已完成 | 响应 moral 基准检查 | 慢 moral 状态加载继续与响应后评估重叠 |
| 187 | 已完成 | 响应 moral/fallibility 基准检查 | 慢 moral 和 fallibility 状态加载与评估在同一等待窗口内完成 |
| 188 | 已完成 | 超时保护基准检查 | 慢评估器超时保护仍出现在基准输出中，用于 5 秒 SLA |
| 189 | 已完成 | 记忆可选快照基准检查 | 可选记忆快照继续在单个等待窗口内并发获取 |
| 190 | 已完成 | 记忆全快照基准检查 | 情绪 + 可选记忆快照在同一等待窗口内并发获取 |
| 191 | 已完成 | 生命周期/公共 API 定向验证 | 110 个生命周期与公共 API 测试通过 |
| 192 | 已完成 | 记忆并发定向验证 | 新增记忆 fan-out 测试通过，耗时低于串行等待上界 |
| 193 | 已完成 | 人格关键词定向验证 | 47 个情绪与人格漂移测试通过 |
| 194 | 已完成 | 公共 API 服务发现验证 | 37 个 public API 服务发现测试通过 |
| 195 | 已完成 | 编译验证 | py_compile 通过触及的运行时、公共 API、基准和测试模块 |
| 196 | 已完成 | README 迭代范围扩展 | 工程明细从第 11-149 次扩展到第 11-200 次 |
| 197 | 已完成 | README 契约同步 | 契约测试改为检查第 11-200 次，同时保留 pr-1 到 pr-19 历史摘要 |
| 198 | 已完成 | 进度持久化记录 | `progress.md` 记录本地-only 延迟批次总结和不上传状态 |
| 199 | 已完成 | 保持本地-only 策略 | 按用户要求没有执行上传或远程发布；远程烟测未运行 |
| 200 | 已完成 | 第 200 次延迟检查点 | 准备最终本地验证和交接，下一步仍以降低真实回复延迟为唯一目标 |
</details>

---

## 项目定位

普通的情绪化 engine 往往只做两件事：

1. 在提示词里写“你要有喜怒哀乐”。
2. 根据最近一两句话临时改变语气。

这样的问题是状态不稳定。用户连续刷很多文本，engine 的状态可能被立刻洗掉；换一个人格设定，旧情绪又可能错误继承；其他插件想调用“当前 engine 是否还在生气”，也没有稳定协议。

本插件把情绪和拟人行为拆成多层：

| 层 | 作用 | 默认状态 |
| --- | --- | --- |
| `emotion_state` | 核心情绪状态。维护 7 维向量、人格基线、后果状态和关系修复判断。 | 开启 |
| `humanlike_state` | 拟人/有机体样表达调制。维护能量、压力、注意力、边界需求等状态。 | 自动开启 |
| `lifelike_learning_state` | 生命化学习/共同语境层。维护新词、黑话、用户画像证据、偏好、边界和开口/沉默时机。 | 自动开启 |
| `personality_drift_state` | 真实时间人格漂移层。让 persona 在长期事件中小幅、有界、缓慢适应。 | 自动开启 |
| `group_atmosphere_state` | 群聊氛围层。维护房间活跃度、紧张度、支持度、打断风险和加入适宜度。 | 自动开启 |
| `moral_repair_state` | 道德修复/信任修复层。记录责任、内疚、道歉、补偿和修复趋势。 | 关闭 |
| `fallibility_state` | 瑕疵/犯错模拟层。维护误读、记忆模糊、轻微嘴硬、澄清、纠错和补偿压力。 | 关闭 |
| `psychological_screening` | 非诊断心理状态筛查与长期趋势备用模块。 | 关闭 |

核心设计原则：

- **LLM 负责语义评价**：他/她判断“这句话对当前人格意味着什么”。
- **本地公式负责状态动力学**：半衰期、平滑、限幅、冷处理持续时间不交给 LLM 随意决定。
- **人格是先验，不只是文风**：不同 AstrBot persona 有不同基线、反应强度和恢复速度。
- **真实时间优先于消息轮数**：状态恢复、冷处理和后果衰减按时间戳计算，不能靠刷屏洗掉。
- **公共接口优先于私有存储**：其他插件应调用稳定异步方法，不直接读写内部 KV key。
- **共同语境要先求证再使用**：新词和小圈子黑话在置信度不足时只触发轻量追问，不假装已经懂。
- **后门可配置**：`allow_emotion_reset_backdoor`、`allow_humanlike_reset_backdoor`、`allow_lifelike_learning_reset_backdoor`、`allow_personality_drift_reset_backdoor`、`allow_moral_repair_reset_backdoor` 和 `allow_fallibility_reset_backdoor` 默认开启，便于异常状态紧急重置。

---

## 核心能力总览

| 能力 | 默认状态 | 说明 |
| --- | --- | --- |
| LLM 情绪估计 | 开启 | 让模型输出结构化 JSON，包含 7 维观测、置信度、冲突分析和关系决策。 |
| 启发式回退 | 内置 | 关闭 `use_llm_assessor` 或 LLM 失败时，使用轻量规则估计状态。 |
| 7 维情绪向量 | 开启 | `valence`、`arousal`、`dominance`、`goal_congruence`、`certainty`、`control`、`affiliation`。 |
| 人格建模 | 开启 | 从当前 AstrBot persona 构造基线和参数偏置，让不同 bot 的反应不同。 |
| 真实时间半衰期 | 开启 | 情绪、后果、冷处理都按真实经过时间衰减，不按消息数量衰减。 |
| 反刷屏门控 | 开启 | 短时间连续更新会被自动门控降权，门控强度写入各状态的 `dynamics`。 |
| 关系修复判断 | 开启 | LLM 判断原谅、修复、设边界、冷处理、升级冲突或无冲突。 |
| 冲突原因分析 | 开启 | 区分用户犯错、bot 任性、bot 误读、双方责任、外部原因或无冲突。 |
| 错误改正判断 | 开启 | 判断用户是否承认、道歉是否可信、是否补救、是否反复发生。 |
| 情绪后果 | 开启 | 把情绪映射为靠近、退避、对抗、安抚、修复、确认、谨慎、反刍等行动倾向。 |
| 冷处理/冷战 | 开启 | 作为持续效果保存到 `active_effects`，按真实时间到期或被修复信号清除。 |
| 安全边界开关 | 默认开启 | `enable_safety_boundary=true` 时限制冷处理表现；关闭后只保留普通情绪后果调制。 |
| 临时注入 | 开启 | 使用 `TextPart(...).mark_as_temp()` 注入，不污染长期聊天记录。 |
| Sylanne 自有记忆 | 开启 | 发生的事件会写入自有长期记忆，并冻结当时情绪、人格漂移和辅助状态。 |
| 公共 API | 开启 | 其他插件可读取快照、提交观察、模拟更新、构造提示词片段或重置状态。 |
| 低推理友好模式 | 默认关闭 | 用短提示词和简单公式降低小模型令牌压力。 |
| 拟人状态模块 | 自动开启 | `humanlike_state` 可调制能量、压力、注意力、边界和透明度；内部动力学参数由插件按人格自动传递，不允许用户手动调细参。 |
| 生命化学习模块 | 自动开启 | `lifelike_learning_state` 学习新词、黑话、用户偏好、共同语境和说话/沉默时机。 |
| 人格漂移模块 | 自动开启 | `personality_drift_state` 让长期事件按真实时间小幅改变运行时 persona 偏移，并自动反馈给人格建模。 |
| 群聊氛围模块 | 自动开启 | `group_atmosphere_state` 维护房间气氛、打断风险和加入适宜度，支持群聊分轨。 |
| 主动发言裁决 | 自动开启 | 是否开口、满足谁的需要、话题方向与开口风格由状态公式和 LLM 裁决共同决定，不使用预设话题模板。 |
| 道德修复模块 | 默认关闭 | `moral_repair_state` 记录责任、内疚、道歉、补偿和信任修复趋势。 |
| 瑕疵模拟模块 | 默认关闭 | `fallibility_state` 让他/她可以有误读、记忆模糊、轻微嘴硬和事后纠错，但不生成欺骗或作恶策略。 |
| 心理筛查模块 | 默认关闭 | 只做非诊断趋势记录和红旗提示，不做疾病判断。 |

---

## 快速开始

### 方式一：上传发布 zip 包

这是准备发布到新仓库后最推荐的安装方式，适合普通部署和远程测试服。

1. 在本仓库根目录构建发布包：

```powershell
py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_sylanne.zip
```

2. 打开 AstrBot WebUI 的插件页面。
3. 选择从文件安装或上传插件。
4. 上传 `dist\astrbot_plugin_sylanne.zip`。
5. 重载插件或重启 AstrBot。
6. 在会话里执行 `/emotion`、`/emotion_model`、`/integrated_self` 做基础检查。

> **警告**
> 不要直接上传 GitHub 绿色 Code 按钮下载的源码 zip，除非它经过 `scripts\package_plugin.py` 或等价流程重新打包。AstrBot WebUI 上传安装期望 zip 内有明确顶层目录 `astrbot_plugin_sylanne/`，并且运行文件位于该目录下。

发布 zip 包的运行根目录应类似：

```text
astrbot_plugin_sylanne/
├── __init__.py
├── agent_identity.py
├── metadata.yaml
├── main.py
├── emotion_engine.py
├── group_atmosphere_engine.py
├── humanlike_engine.py
├── lifelike_learning_engine.py
├── personality_drift_engine.py
├── realtime_chat_engine.py
├── realtime_chat_input.py
├── integrated_self.py
├── moral_repair_engine.py
├── fallibility_engine.py
├── psychological_screening.py
├── prompts.py
├── public_api.py
├── _conf_schema.json
├── requirements.txt
├── LICENSE
├── README.md
├── CHANGELOG.md
└── docs/
```

### 方式二：从 GitHub 仓库安装

新仓库创建并推送后，在 AstrBot WebUI 的仓库安装入口填写：

```text
https://github.com/Ayleovelle/astrbot_plugin_sylanne
```

如果 WebUI 要求 `.git` 后缀：

```text
https://github.com/Ayleovelle/astrbot_plugin_sylanne.git
```

新仓库地址已经写入 `metadata.yaml` 的 `repo:` 字段；后续发布 GitHub 发布版本时，只需要确认 README、发布附件名、插件目录名和 `metadata.yaml name:` 都保持 `astrbot_plugin_sylanne`。

### 方式三：手动复制到插件目录

开发或本地调试时，可以把本目录放入 AstrBot 插件目录：

```text
data/plugins/
└── astrbot_plugin_sylanne/
    ├── __init__.py
    ├── metadata.yaml
    ├── main.py
    ├── emotion_engine.py
    ├── humanlike_engine.py
    ├── lifelike_learning_engine.py
    ├── personality_drift_engine.py
    ├── realtime_chat_engine.py
    ├── realtime_chat_input.py
    ├── integrated_self.py
    ├── moral_repair_engine.py
    ├── fallibility_engine.py
    ├── psychological_screening.py
    ├── prompts.py
    ├── public_api.py
    ├── _conf_schema.json
    ├── requirements.txt
    ├── LICENSE
    ├── README.md
    ├── CHANGELOG.md
    └── docs/
```

`tests/`、`scripts/`、四个 `*_literature_kb/` 知识库目录、`raw/`、`output/`、`dist/` 属于仓库开发、研究或缓存内容，发布 zip 不会包含这些目录。

然后在 AstrBot WebUI 中重载或启用插件。

### 版本要求

来自 `metadata.yaml`：

```yaml
astrbot_version: ">=4.9.2,<5.0.0"
```

`requirements.txt` 当前没有第三方运行时依赖：

```text
# 当前没有第三方运行时依赖。
```

也就是说，插件主要依赖 AstrBot 自身的插件运行环境。

### 最小可用配置

首次使用建议只改这几项：

| 配置项 | 推荐值 | 说明 |
| --- | --- | --- |
| `enabled` | `true` | 启用插件。 |
| `use_llm_assessor` | `true` | 使用 LLM 做情绪观测。 |
| `emotion_provider_id` | 一个便宜稳定的小模型 | 留空则使用当前会话模型。 |
| `assessment_timing` | `post` | 默认只在回复后根据实际输出修正，避免每轮额外双 LLM 评估；需要本轮语气即时受影响时可改为 `pre` 或 `both`。 |
| `inject_state` | `true` | 把状态作为临时上下文注入主 LLM。 |
| `persona_modeling` | `true` | 让不同人格有不同基线。 |
| `enable_safety_boundary` | `true` | 默认开启可控边界，可按需求关闭。 |
| `allow_emotion_reset_backdoor` | `true` | 保留异常状态重置后门。 |

一条实际可用的基础配置：

```text
enabled = true
use_llm_assessor = true
emotion_provider_id = 你的情绪评估模型提供方标识
assessment_timing = post
inject_state = true
persona_modeling = true
enable_safety_boundary = true
allow_emotion_reset_backdoor = true
```

如果你先想省令牌，可以临时打开：

```text
low_reasoning_friendly_mode = true
low_reasoning_max_context_chars = 1200
```

但默认建议关闭低推理模式，让插件保留更完整的冲突分析、关系修复和理论字段。

### 安装后检查

安装完成后，建议按顺序检查：

```text
/emotion
/emotion_model
/emotion_effects
/integrated_self
```

自动运行的辅助状态也可以继续检查：

```text
/humanlike_state
/lifelike_state
/personality_drift_state
```

如果打开了可选维护模块，再检查：

```text
/moral_repair_state
/fallibility_state
/psych_state
```

`/emotion_reset`、`/humanlike_reset`、`/lifelike_reset`、`/personality_drift_reset`、`/moral_repair_reset` 和 `/fallibility_reset` 是异常状态恢复命令，分别受 `allow_emotion_reset_backdoor`、`allow_humanlike_reset_backdoor`、`allow_lifelike_learning_reset_backdoor`、`allow_personality_drift_reset_backdoor`、`allow_moral_repair_reset_backdoor`、`allow_fallibility_reset_backdoor` 控制。

---

## 命令

| 命令 | 别名 | 用途 |
| --- | --- | --- |
| `/emotion` | `/emotion_state`、`/情绪状态` | 查看当前会话的核心 7 维情绪状态。 |
| `/emotion_reset` | `/情绪重置` | 重置当前会话的情绪状态，受 `allow_emotion_reset_backdoor` 控制。 |
| `/emotion_model` | `/情绪模型` | 查看模型公式、真实时间衰减和人格基线说明。 |
| `/emotion_effects` | `/情绪后果` | 查看当前行动倾向、冷处理、修复、谨慎核对等后果。 |
| `/psych_state` | `/心理筛查`、`/心理状态` | 查看非诊断心理状态筛查快照。 |
| `/humanlike_state` | `/拟人状态`、`/有机体状态` | 查看拟人状态。 |
| `/humanlike_reset` | `/拟人状态重置` | 重置拟人状态，受 `allow_humanlike_reset_backdoor` 控制。 |
| `/lifelike_state` | `/生命化状态`、`/共同语境` | 查看生命化学习状态，包括新词、黑话、用户画像证据和开口策略。 |
| `/lifelike_reset` | `/生命化状态重置`、`/共同语境重置` | 重置生命化学习状态，受 `allow_lifelike_learning_reset_backdoor` 控制。 |
| `/sylanne_memory` | `/记忆查询`、`/查询记忆`、`/灵澜记忆` | 只读查询 Sylanne 自有记忆，显示命中摘要、深度、置信度和召回评分，用于检查记忆模块是否正常工作。 |
| `/personality_drift_state` | `/人格漂移状态`、`/人格适应状态` | 查看真实时间人格漂移状态、锚点强度、时间门控和主要偏移。 |
| `/personality_drift_reset` | `/人格漂移重置`、`/人格适应重置` | 重置人格漂移状态，受 `allow_personality_drift_reset_backdoor` 控制。 |
| `/moral_repair_state` | `/道德修复状态`、`/信任修复状态` | 查看道德修复/信任修复状态。 |
| `/moral_repair_reset` | `/道德修复重置`、`/信任修复重置` | 重置道德修复状态，受 `allow_moral_repair_reset_backdoor` 控制。 |
| `/fallibility_state` | `/瑕疵状态`、`/犯错模拟状态` | 查看低风险瑕疵/犯错模拟状态。 |
| `/fallibility_reset` | `/瑕疵状态重置`、`/犯错模拟重置` | 重置瑕疵/犯错模拟状态，受 `allow_fallibility_reset_backdoor` 控制。 |
| `/integrated_self` | `/综合自我状态`、`/自我状态` | 查看跨模块综合自我状态仲裁。 |
| `/shadow_diagnostics` | `/阴影诊断`、`/阴影状态` | 查看配置门控的只读阴影冲动诊断视图；默认关闭，仅用于维护排查，不生成欺骗、操控、逃责或执行策略。 |

### 情绪状态

```text
/emotion
/emotion_state
/情绪状态
```

查看当前会话的多维情绪状态，包括 7 维数值、人格、置信度、最近原因和关系判断。

### 重置情绪

```text
/emotion_reset
/情绪重置
```

重置当前会话的情绪状态。该命令受 `allow_emotion_reset_backdoor` 控制；默认允许。

### 查看模型公式

```text
/emotion_model
/情绪模型
```

查看插件使用的核心数学模型和公式说明。

### 查看情绪后果

```text
/emotion_effects
/情绪后果
```

查看当前会话的行动倾向和持续效果，例如冷处理、主动修复、谨慎核对等。

### 心理筛查状态

```text
/psych_state
/心理筛查
/心理状态
```

查看非诊断心理状态筛查快照。默认情况下 `enable_psychological_screening=false`，所以这个模块不会主动建模。

### 拟人状态

```text
/humanlike_state
/拟人状态
/有机体状态
```

查看模拟拟人状态。该状态层在 `1.0.0` 中默认自动运行；主提示词里注入多少拟人状态由插件根据预算和状态显著性自动决定，不再提供手动注入档位。

### 重置拟人状态

```text
/humanlike_reset
/拟人状态重置
```

重置当前会话的 `humanlike_state`。该命令受 `allow_humanlike_reset_backdoor` 控制；默认允许。

### 生命化学习状态

```text
/lifelike_state
/生命化状态
/共同语境
```

查看当前会话的生命化学习状态。该模块默认自动运行，会按真实时间学习用户画像证据、新词、黑话、喜恶、边界提示和当前是否适合开口。

### 重置生命化学习状态

```text
/lifelike_reset
/生命化状态重置
/共同语境重置
```

重置当前会话的 `lifelike_learning_state`。该命令受 `allow_lifelike_learning_reset_backdoor` 控制；默认允许。

### 查询 Sylanne 自有记忆

```text
/sylanne_memory README
/记忆查询 README
/查询记忆 README
/灵澜记忆 README
```

只读查询当前会话的自有长期记忆。返回内容会包含命中摘要、召回分数、记忆深度、置信度、证据次数和召回次数，方便配置者确认记忆有没有写入、能不能按关键词召回。这个入口不会强化记忆，也不会修改 `recall_count`、深度或置信度；真正对话里的召回仍由插件按预算自动注入 `[sylanne_memory_recall]`。

### 人格漂移状态

```text
/personality_drift_state
/人格漂移状态
/人格适应状态
```

查看当前会话的 `personality_drift_state`。该模块默认自动运行；人格只会围绕静态 persona 锚点产生缓慢、有界的真实时间偏移。短时间大量消息不会线性累积人格变化，滚动上下文也不会被反复当作新证据。

### 重置人格漂移状态

```text
/personality_drift_reset
/人格漂移重置
/人格适应重置
```

重置当前会话的 `personality_drift_state`。该命令受 `allow_personality_drift_reset_backdoor` 控制；默认允许，用于异常适应、人格污染、调试或严重后果回滚。

### 道德修复状态

```text
/moral_repair_state
/道德修复状态
/信任修复状态
```

查看模拟道德修复/信任修复状态。默认情况下 `enable_moral_repair_state=false`。

### 重置道德修复状态

```text
/moral_repair_reset
/道德修复重置
/信任修复重置
```

重置当前会话的 `moral_repair_state`。该命令受 `allow_moral_repair_reset_backdoor` 控制；默认允许。

### 瑕疵模拟状态

```text
/fallibility_state
/瑕疵状态
/犯错模拟状态
```

查看低风险瑕疵/犯错模拟状态。默认情况下 `enable_fallibility_state=false`。开启后，他/她会维护误读倾向、记忆模糊、过度自信、轻微嘴硬、回避、澄清需求、纠错准备和补偿压力等维度。

### 重置瑕疵模拟状态

```text
/fallibility_reset
/瑕疵状态重置
/犯错模拟重置
```

重置当前会话的 `fallibility_state`。该命令受 `allow_fallibility_reset_backdoor` 控制；默认允许。

### 综合自我状态

```text
/integrated_self
/综合自我状态
/自我状态
```

查看只读的综合自我状态仲裁结果。该总线会融合情绪、拟人状态、道德修复和非诊断心理筛查快照，但不会直接写入 KV。

### 阴影诊断

```text
/shadow_diagnostics
/阴影诊断
/阴影状态
```

查看配置者开启后的只读阴影冲动诊断载荷。默认情况下 `enable_shadow_diagnostics=false`，命令只会返回未启用说明；开启后会输出 JSON，用于维护排查 moral repair、fallibility 和 integrated self 中的非执行阴影冲动、内疚/补偿压力和信任修复成本。该入口不会生成欺骗、操控、逃责或执行策略。

---

## 工作流对比（与 0.5.0）

0.5.0 之前的主链路更接近“单线程状态增强”：收到消息后，插件在请求内按顺序读取状态、做情绪评估、注入提示词，再等待主回复，最后把结果写回。这个结构容易理解，但慢状态、评估模型、记忆注解和主回复会相互等待，群聊和主动发言也很难自然插进去。

当前版本把链路拆成“Agent 上下文 + Sylanne 投递层 + 回复后后台队列 + 主动发言支路 + 自有记忆召回”。主 LLM 的长期上下文仍交给 AstrBot Agent 持有；Sylanne 不再把大段临时历史塞进 prompt，只在必要时补充短状态事实、短记忆召回和“这段回复已生成但未必完整送达”的投递信封。主回复尽量先返回；回复后的内部评估进入后台队列，按会话顺序提交；主动发言由公式先判定开口时机，再让大模型裁决理由和话题；动态后台工作器会参考队列、CPU、内存和全局预算自动收放。下面这张图里，蓝色是主回复，绿色是后台工作器池，橙色是主动发言支路。

![工作流与主动发言支路](docs/assets/workflow_and_proactive.svg)

几个关键点：

- `pre` 更新会影响本轮回复语气。
- `post` 更新会根据 engine 实际说出口的内容修正状态。
- `both` 最完整，但会多一次情绪评估消耗。
- 主动发言不会靠固定话题库触发；它先由公式判断是否适合开口，再让大模型在当前上下文候选主题中裁决“为什么说、证据是什么、说什么方向、怎么短句开口”。
- `get_proactive_speech_decision(...)` 仍是只读裁决；`request_proactive_speech_dispatch(...)` 会生成 `dispatch_request`，并在配置允许时真正向 AstrBot `context.send_message` 请求发送。
- 话题来源必须可解释：用户某件事的进度、共同语境里的近期事项、想念/陪伴需要、调皮打扰、轻量整蛊或修复需求都要带 `topic_evidence`。
- 主动发言不是轮询到候选就立刻发送；同一会话刚结束交流时会进入真实时间安静门，未回复、冷回复和连续主动失败会继续拉长冷却，让她更像“偶尔想起你”，而不是后台定时刷存在感。
- 即时聊天只接管最终自然语言回复；如果 LLMResponse 处在工具调用阶段，Sylanne 会完全放行，不改写 `completion_text`，不 `stop_event()`，也不消费会话 epoch，避免打断 AstrBot Agent 的工具循环。
- 主动发送默认关闭；打开后仍受同会话冷却、沉默裁决、缺失 `unified_msg_origin`、缺失 `send_message` 接口等诊断保护。
- 注入使用临时 `TextPart`，不会直接写进长期消息记录。
- 状态落库使用 AstrBot KV，不建议外部插件直接改内部 key。

<details>
<summary>展开 0.5.0 旧版单线程工作流与当前工作流对比</summary>

| 维度 | 0.5.0 旧版单线程工作流 | 当前工作流优势 |
| --- | --- | --- |
| 状态读取 | 主情绪、辅助状态和记忆注解多在请求内顺序处理。 | 请求、响应和记忆写入阶段会并发读取可选状态快照，慢模块不再拖住整条链路。 |
| 状态评估 | 请求内串行评估，回复容易被评估耗时拖住。 | `pre` 保持即时影响；`post` 进入后台队列，结果按顺序号提交，降低主链路延迟。 |
| 后台处理 | 基本没有独立后台闭环，积压时只能等待当前链路。 | 后台工作器会参考队列深度、等待年龄、CPU/内存压力、未知压力保守档和全局预算，空闲后自动收束。 |
| 参数传递 | 冷却、长度、半衰期更接近静态配置。 | 人格漂移影响人格建模，人格建模再传递到情绪动力学、主动性、冷却、反馈窗口和表达节奏。 |
| 主动聊天 | 只能由工具或其他插件请求一次主动发言。 | 可登记最近会话，后台低频醒来；话题由状态公式和大模型基于证据裁决，再通过 `context.send_message` 请求发送。 |
| 话题来源 | 容易变成预设话题或模板开场。 | 必须带 `topic_evidence`，例如进度关心、共同语境、想念、调皮打扰、轻量修复或双方互需。 |
| 主动频率 | 缺少“刚聊完就别打扰”的真实时间门控。 | 同一会话近期活跃、未回复、冷回复、打断风险和反馈压力会共同提高冷却；非紧急开口需要更长真实时间间隔。 |
| 即时聊天 | 主大模型一次性吐出整段回复。 | 可拆成多条短消息，模拟打字停顿，并在表情包发送前做语气一致性检查。 |
| 工具调用 | 回复接管和工具调用边界不够清晰。 | 只接管最终自然语言回复；工具调用中间响应完全交还 AstrBot Agent，避免工具链被分条模块截断。 |
| 上下文归属 | 插件容易把临时摘要当成长上下文来源。 | 长期上下文归 AstrBot Agent；Sylanne 只补投递事实、短记忆召回和必要状态摘要。 |
| 记忆写入 | 长期记忆更偏事实文本。 | Sylanne 自有记忆会冻结当时情绪、拟人状态、生命化学习和人格漂移，让记忆带着当时气氛。 |

</details>

---

## 情绪模型

### 7 维向量

插件默认维护：

```math
E_t(P) \in [-1, 1]^7
```

```math
E_t =
\begin{bmatrix}
V_t & A_t & D_t & G_t & C_t & K_t & S_t
\end{bmatrix}^{\mathsf T}
```

| 维度 | 字段 | 含义 | 高值表现 | 低值表现 |
| --- | --- | --- | --- | --- |
| 效价 | `valence` | 愉悦/不愉悦 | 温和、满意、接纳 | 不快、受伤、防御 |
| 唤醒 | `arousal` | 激活强度 | 警觉、急促、表达增强 | 平静、低能量、迟缓 |
| 支配感 | `dominance` | 自主感和社交掌控 | 坚定、设边界 | 迟疑、退让 |
| 目标一致性 | `goal_congruence` | 当前事件是否符合角色目标 | 顺利、被理解 | 受阻、挫败 |
| 确定性 | `certainty` | 对情境解释的确定程度 | 直接判断 | 先核对、承认不确定 |
| 可控性 | `control` | 对局面可控程度的评估 | 解决问题 | 回避、求助、谨慎 |
| 亲和度 | `affiliation` | 对用户的亲近和信任 | 靠近、修复、温度 | 距离感、防御、冷处理 |

前三维对应 PAD 和环形情感模型；后四维来自评价理论与 OCC 对事件、行动者和对象的认知评价。

### 核心模型摘要

先抓住五件事：

| 层级 | 核心公式 | 设计理由 |
| --- | --- | --- |
| 状态空间 | `E_t(P) in [-1,1]^7` | 情绪不是单一标签，而是可连续调制的多维状态。 |
| 人格先验 | `b_p = h_b(P)`，`theta_p = h_theta(P)` | persona 不只决定文风，也决定基线、反应强度和恢复速度。 |
| 即时观测 | `X_t = tanh(WZ_t + beta)` | LLM 负责把上下文解释成 appraisal 与即时情绪观测。 |
| 长期更新 | `E'_t = B_t + alpha_t(X_t-B_t)` | 当前刺激会改变状态，但不能一轮文本完全覆盖长期情绪。 |
| 真实时间 | `gamma_p(Delta t)=1-2^{-Delta t/H_p}` | 恢复和冷处理按真实时间衰减，不能靠刷屏强行洗掉。 |

这套模型的工程折中是：LLM 负责语义评价，本地公式负责惯性、限幅、半衰期、人格基线和后果衰减。下面是完整论证，已折叠；维护模型、复现实验或写论文时再展开。

### 真实时间人格漂移模型

静态 persona 仍是人格锚点；长期事件只写入一个会话级有界偏移 `Delta p_t`。模型核心是：先按真实经过时间回拉到锚点，再让当前真实事件产生很小冲量。历史上下文不会被重复当作新事件；`evidence_count` 只用于诊断，不是消息数权重。

```math
\theta^D_t=f_D(p_0,\Delta p_{t-1},v_{t-1},x_t,\Delta t,\theta^D_{t-1})
```

```math
\theta^D_t=(1-w^D_t)\theta^D_{t-1}+w^D_t\theta^{D*}_t
```

```math
\lambda^D_t=2^{-\Delta t/H^D_t},\qquad
g^D_t=1-2^{-\Delta t/G^D_t}
```

```math
s_t=r_t c_t g^D_t\phi^D_t(q_t,v_{t-1},\Delta p_{t-1})
```

```math
\Delta p_t^{(i)}
=
\mathrm{clip}
\left(
\lambda^D_t\Delta p_{t-1}^{(i)}
+
\mathrm{clip}\left(\eta^D_t s_t u_t^{(i)},-e^D_t,e^D_t\right),
-O^D_t,O^D_t
\right)
```

```math
p_t^{(i)}=\mathrm{clip}\left(p_0^{(i)}+\beta^D_t\Delta p_t^{(i)},-1,1\right)
```

这里 `p_0` 是 AstrBot persona 推导出的静态人格先验，`Delta p_t` 是相对偏移，`u_t` 是当前事件映射到人格维度的冲量向量。`H^D_t`、`G^D_t`、`e^D_t`、`O^D_t`、`beta^D_t` 和事件固化门限都来自 `personality_drift_state.dynamics` 的本地自动推导：锚定强度越高、证据越稀薄、偏移越大，漂移越慢；事件越可靠、关系越重要、真实时间间隔越充分，冲量才更容易被固化。所以一条消息、短时间刷屏或重复上下文都不能把他/她强行改造成另一个人。

<details>
<summary>展开人格漂移公式推导与文献依据</summary>

人格漂移不是“修改 persona 文本”，而是把 persona 看成状态分布的中心。Fleeson 的 whole-trait / density-distribution 思路支持“人格是状态分布而非固定脚本”；Mischel 与 Shoda 的 CAPS 支持“if-then 情境反应模式”；DeYoung 的 Cybernetic Big Five Theory 支持把人格特质视为目标调节和控制参数。TESSERA 框架进一步把长期人格改变拆成触发情境、预期、状态、状态表达、反应和反思/行动单元，强调重复事件需要经过时间、反思和强化才会沉积为特质改变。

把静态 persona 先验记为：

```math
p_0\in[-1,1]^d
```

运行时人格不是直接改写 `p_0`，而是：

```math
p_t=p_0+\beta^D_t\Delta p_t
```

其中 `beta^D_t` 不是配置项，而是由漂移强度、trait 置信度、锚定强度、偏移幅度和 `personality_drift_state.dynamics` 自动派生。为了使漂移回到锚点，先对上一时刻偏移做半衰：

```math
\Delta p_{t,\mathrm{decay}}=\lambda^D_t\Delta p_{t-1}
```

短时刷屏门控写作：

```math
g^D_t=1-2^{-\Delta t/G^D_t}
```

当 `Delta t` 很小时，`g^D_t` 接近 0；只有真实时间经过后，事件冲量才逐渐被放行。事件信号：

```math
s_t=r_t c_t g^D_t\phi^D_t(q_t,v_{t-1},\Delta p_{t-1})
```

其中 `r_t` 是事件强度，`c_t` 是可靠性，`q_t` 是关系重要性，`v_{t-1}` 是上一轮漂移状态摘要，`phi^D_t` 是本地派生的关系-锚定调制项。单维更新：

```math
\Delta p_t^{(i)}
=
\mathrm{clip}
\left(
\Delta p_{t,\mathrm{decay}}^{(i)}
+
\mathrm{clip}\left(\eta^D_t s_t u_t^{(i)},-e^D_t,e^D_t\right),
-O^D_t,O^D_t
\right)
```

如果事件信号低于当前自动派生的事件固化门限，则不固化为人格漂移证据。实现上 `on_llm_request` 只把当前消息作为人格漂移事件；滚动 `contexts`、系统提示词和注入状态不会被重复计入长期人格偏移。外部插件可通过 `observed_at` 传入真实事件时间，模型使用 `now - updated_at` 计算门控与半衰。

主要依据：

- Fleeson, W. (2001). Traits as density distributions of states. *Journal of Personality and Social Psychology*. DOI `10.1037/0022-3514.80.6.1011`.
- Mischel, W., & Shoda, Y. (1995). A cognitive-affective system theory of personality. *Psychological Review*. DOI `10.1037/0033-295X.102.2.246`.
- DeYoung, C. G. (2015). Cybernetic Big Five Theory. *Journal of Research in Personality*. DOI `10.1016/j.jrp.2014.07.004`.
- Wrzus, C., & Roberts, B. W. (2017). Processes of personality development in adulthood: The TESSERA framework. *Personality and Social Psychology Review*. DOI `10.1177/1088868316652279`.
- Baumert, A., Schmitt, M., Perugini, M., et al. (2017). Integrating personality structure, process, and development. *European Journal of Personality*. DOI `10.1002/per.2115`.
- Roberts, B. W., Walton, K. E., & Viechtbauer, W. (2006). Patterns of mean-level change in personality traits across the life course. *Psychological Bulletin*. DOI `10.1037/0033-2909.132.1.3`.

</details>

<details>
<summary>论文附录 S1｜完整公式推导、代表性文献依据与工程取舍</summary>

#### Supplementary Note S1｜完整公式推导

**题名**：面向 AstrBot 情绪状态层的多维人格调制动力学模型。

**摘要**：本附录以论文补充材料的形式给出插件核心模型的构造过程。模型将 engine 的情绪表示为受人格先验调制的有界连续向量，并用大模型语义观测、本地真实时间动力学、关系后果状态机和记忆注解共同形成可持续更新的状态层。推导目标不是证明 engine 具有真实主观体验，而是证明该工程状态机在多维情绪、人格差异、情绪惯性、行动倾向和关系修复之间保持一致的数学接口。

**关键词**：多维情绪；appraisal theory；人格先验；情绪惯性；真实时间衰减；关系修复；AstrBot。

**引用格式**：建议将本节视为“补充说明 S1”，正文快速阅读只引用“情绪模型”小节；需要复现、审稿或二次开发时再展开此附录。

#### S1.1 代表性文献依据

| 模型部件 | 采用的工程形式 | 代表性文献依据 | 插件中的取舍 |
| --- | --- | --- | --- |
| 多维情绪空间 | PAD + appraisal 扩展为 7 维向量 | Russell 1980, *Journal of Personality and Social Psychology*, DOI `10.1037/h0077714`；Mehrabian & Russell 1974；Scherer 2005, DOI `10.1177/0539018405058216`。 | 用连续向量保存状态，而不是只用“开心/生气/难过”标签。 |
| 人格作为先验 | `b_p` 与 `theta_p` 从人格设定派生 | 评价理论强调评价依赖目标、责任、可控性和情境意义；Roseman 1991, DOI `10.1080/02699939108411034`。 | 不做临床人格测量，只把人格设定转成工程先验，让不同 engine 有不同默认姿态。 |
| 惯性更新 | 加权二次目标函数推出指数平滑 | Kuppens、Allen & Sheeber 2010, *Psychological Science*, DOI `10.1177/0956797610372634`；Gross 1998, DOI `10.1037/1089-2680.2.3.271`。 | 用 `E_{t-1}` 与 `X_t` 的加权折中防止单轮文本劫持状态。 |
| 置信门控与惊讶度 | `g(c_t)` 与 `delta_t` 调制 `alpha_t` | Scherer 2005 的成分过程模型；Roseman 1991 对概率、合法性、因果主体等评价维度的实验检验。 | 低置信大模型输出只轻微更新，高显著事件才提高步长。 |
| 行动倾向 | `O_t` 表示 approach、withdrawal、repair 等后果 | Frijda, Kuipers & ter Schure 1989, *Journal of Personality and Social Psychology*, DOI `10.1037/0022-3514.57.2.212`；Carver & Harmon-Jones 2009, *Psychological Bulletin*, DOI `10.1037/a0013965`。 | 生气不必然冷战，可走边界、修复、求证或解决问题。 |
| 冷处理与修复 | 关系决策 + 冲突成因 + 真实时间持续效果 | Christensen & Heavey 1990, *Journal of Personality and Social Psychology*, DOI `10.1037/0022-3514.59.1.73`；Fehr et al. 2010, *Psychological Bulletin*, DOI `10.1037/a0019993`；Ohbuchi et al. 1989, DOI `10.1037/0022-3514.56.2.219`。 | 冷处理是可衰减后果状态；道歉、承认、补救和误读会压低惩罚性后果。 |

### 人格先验

从状态层实验版开始，人格建模不再只是少量风格关键词偏置。插件会从当前 AstrBot persona 文本构造一个带版本号的 13 维潜在人格先验向量，覆盖大五人格、HEXACO 中的诚实-谦逊扩展、依恋焦虑/回避、BIS/BAS、认知闭合需要、情绪调节能力和人际温暖度。

默认摘要：

```math
q_p = \left(M^{\mathsf T}RM+\lambda\Sigma^{-1}\right)^{-1}
\left(M^{\mathsf T}Ry+\lambda\Sigma^{-1}\mu\right)
```

```math
b_p = \Pi_{[-1,1]^7}(b_0+Bq_p),\qquad
\theta_p = \Pi_{[0.55,1.55]^m}(\theta_0+Cq_p)
```

这里 `q_p` 是潜在人格向量，`y` 是多源 persona 文本指标向量，`R` 是来源可靠度，`mu` 与 `Sigma` 是保守先验。公开 payload 会暴露 `personality_model.schema_version = astrbot.personality_profile.v1`、`trait_scores`、`trait_confidence`、`posterior_variance` 和 `derived_factors`，但不会暴露原始 persona 文本。

这不是临床人格评估，而是工程先验：它让不同 engine 拥有稳定、可复现、可被外部读取的情绪基线、反应性、边界敏感度、修复取向和社交距离。

<details>
<summary>展开严格人格量化公式与期刊依据</summary>

人格输入：

```math
P = \{\mathrm{persona\_id}, \mathrm{name}, \mathrm{system\_prompt}, \mathrm{begin\_dialogs}\}
```

为了保持向后兼容，旧工程特质仍保留：

```math
T_p =
\begin{bmatrix}
\mathrm{warmth} & \mathrm{shyness} & \mathrm{assertiveness} & \mathrm{volatility} &
\mathrm{calmness} & \mathrm{optimism} & \mathrm{pessimism} & \mathrm{dutifulness}
\end{bmatrix}^{\mathsf T}
```

新的潜在向量为：

```math
q_p =
\begin{bmatrix}
O & N & X & A & L & H & R_a & R_v & I & B & F & U & W_s
\end{bmatrix}^{\mathsf T}
```

这些维度依次表示开放性、尽责性、外向性、宜人性、神经质、诚实-谦逊、依恋焦虑、依恋回避、BIS 敏感性、BAS 驱动、认知闭合需要、情绪调节能力和人际温暖度。

多源指标：

```math
y =
\begin{bmatrix}
y_{\mathrm{lex}} & y_{\mathrm{legacy}} & y_{\mathrm{struct}}
\end{bmatrix}^{\mathsf T}
```

可靠度加权后验来自带先验收缩的最小二乘目标：

```math
J(q)=\|Mq-y\|_R^2+\lambda\|q-\mu\|_{\Sigma^{-1}}^2
```

求导：

```math
\frac{\partial J}{\partial q}=
2M^{\mathsf T}R(Mq-y)+2\lambda\Sigma^{-1}(q-\mu)
```

令导数为零：

```math
(M^{\mathsf T}RM+\lambda\Sigma^{-1})q=
M^{\mathsf T}Ry+\lambda\Sigma^{-1}\mu
```

闭式后验解：

```math
q_p = \left(M^{\mathsf T}RM+\lambda\Sigma^{-1}\right)^{-1}
\left(M^{\mathsf T}Ry+\lambda\Sigma^{-1}\mu\right)
```

近似后验不确定性：

```math
V_q = \left(M^{\mathsf T}RM+\lambda\Sigma^{-1}\right)^{-1}
```

运行时使用确定性的对角近似：

```math
q_i = \frac{\sum_j r_j y_{j,i}+\lambda\mu_i}{\sum_j r_j+\lambda}
```

```math
\mathrm{var}_i = \frac{1}{\sum_j r_j+\lambda}
```

人格后验映射到情绪基线和动力学参数：

```math
b_p = \Pi_{[-1,1]^7}(b_0+Bq_p)
```

```math
\theta_p = \Pi_{[0.55,1.55]^m}(\theta_0+Cq_p)
```

派生因子：

```math
\begin{aligned}
\mathrm{instability}_p &= a_1L+a_2R_a+a_3I-a_4U,\\
\mathrm{distance}_p &= a_5R_v-a_6W_s-a_7X,\\
\mathrm{repair}_p &= a_8A+a_9H+a_{10}U-a_{11}R_v,\\
\mathrm{boundary}_p &= a_{12}I+a_{13}F+a_{14}N-a_{15}A.
\end{aligned}
```

证据依据：大五人格结构参考 Digman 1990、Goldberg 1990 与 McCrae & Costa 1987；HEXACO 扩展参考 Ashton & Lee 2007；人格状态分布和情境-反应动力学参考 Fleeson 2001 与 Mischel & Shoda 1995；BIS/BAS 参考 Carver & White 1994；认知闭合需要参考 Webster & Kruglanski 1994；依恋维度参考 Fraley、Waller & Brennan 2000；情绪调节差异参考 Gross & John 2003。大规模检索索引只作为本地研究资产保留，不进入公开仓库或发布 zip 包。

</details>

### 大模型观测

设本轮输入为：

```math
I_t = \{H_t, U_t, P, E_{t-1}\}
```

含义：

- `H_t`：最近上下文。
- `U_t`：当前用户输入或 bot 回复。
- `P`：当前 persona。
- `E_{t-1}`：上一轮平滑状态。

理论上可以把 LLM 的判断拆成隐藏评价向量：

```math
Z_t =
\begin{bmatrix}
z_{\mathrm{goal}} & z_{\mathrm{novelty}} & z_{\mathrm{agency}} &
z_{\mathrm{control}} & z_{\mathrm{certainty}} & z_{\mathrm{norm}} &
z_{\mathrm{social}}
\end{bmatrix}^{\mathsf T}
```

```math
Z_t = \phi_{\mathrm{llm}}(I_t), \qquad
X_t = \tanh(WZ_t + \beta)
```

工程上，本插件让 LLM 直接输出：

```json
{
  "label": "embarrassed_defensive",
  "dimensions": {
    "valence": -0.2,
    "arousal": 0.4,
    "dominance": -0.1,
    "goal_congruence": -0.3,
    "certainty": 0.2,
    "control": -0.2,
    "affiliation": 0.1
  },
  "confidence": 0.76,
  "appraisal": {
    "relationship_decision": {
      "decision": "repair",
      "intensity": 0.58,
      "forgiveness": 0.74,
      "relationship_importance": 0.8,
      "reason": "用户已解释并愿意补救"
    }
  },
  "reason": "用户的话造成轻微挫败，但有修复空间"
}
```

LLM 负责“发生了什么”；本地引擎负责“这种意义怎样改变长期状态”。

### 状态更新推导

如果直接令：

```math
E_t = X_t
```

情绪会被单轮文本完全支配，表现为跳变。插件改为求解一个带惯性的加权最小化问题：

```math
E_t = \arg\min_{E} J(E)
```

```math
J(E) =
(1-\alpha_t)\|E-B_t\|_W^2
+ \alpha_t\|E-X_t\|_W^2
```

其中 `B_t` 是上一状态经人格基线回归后的先验：

```math
B_t = (1-\gamma_p)E_{t-1} + \gamma_p b_p
```

```math
\gamma_p(\Delta t) = 1 - 2^{-\Delta t/H_p}
```

`\Delta t` 是真实经过时间，`H_p` 是被人格调制后的半衰期。

对目标函数求导：

```math
\frac{\partial J}{\partial E}
= 2(1-\alpha_t)W(E-B_t) + 2\alpha_t W(E-X_t)
```

令导数为零：

```math
(1-\alpha_t)W(E-B_t) + \alpha_t W(E-X_t) = 0
```

若 `W` 正定，可消去 `W`：

```math
(1-\alpha_t)(E-B_t) + \alpha_t(E-X_t) = 0
```

得到：

```math
E'_t = B_t + \alpha_t(X_t-B_t)
```

所以指数平滑不是随意拼公式，而是“保持情绪惯性”和“接纳当前观测”之间的二次优化解。

### 自适应步长

插件使用置信门控和惊讶度调制更新步长：

```math
\alpha_t =
\mathrm{clamp}\left(
\alpha_{\mathrm{base},p}\,g(c_t)(1+r_p\delta_t),
\alpha_{\min},
\alpha_{\max}
\right)
```

```math
g(c_t) = \frac{1}{1+\exp[-k(c_t-c_0)]}
```

其中：

- `c_t` 是 LLM 输出的置信度。
- `g(c_t)` 让低置信观测影响变小。
- `delta_t` 是观测和先验的加权距离。
- `r_p` 来自 persona 参数偏置。

惊讶度：

```math
\delta_t =
\sqrt{
\frac{(X_t-B_t)^{\mathsf T}W(X_t-B_t)}
{\mathrm{tr}(W)}
}
```

### 维度耦合

插件只加入两个弱耦合项，避免模型不可解释。

惊讶度提升唤醒度：

```math
A_t = A'_t + \eta\alpha_t\delta_t\left(1-|A'_t|\right)
```

可控性牵引支配感：

```math
D_t = D'_t + \lambda\alpha_t(K'_t-D'_t)
```

最后逐维裁剪：

```math
E_t = \Pi_{[-1,1]^7}(E_t)
```

</details>

### 真实时间记忆

核心原则：

| 项目 | 含义 |
| --- | --- |
| 真实时间衰减 | 情绪、后果、冷处理、修复和人格漂移都按真实经过时间计算，不按消息数量计算。 |
| 自动动力学 | 半衰期、冷处理时长、短期后果时长、更新步长、反刷屏门控和冲量上限都由本地公式从运行时人格模型、当前状态、置信度、冲突成因、修复信号和真实时间间隔推导。 |
| 低 LLM 参与 | LLM 只提供语义观测、关系判断和冲突成因；不直接给出这些数值参数。 |
| 可追溯快照 | 推导后的有效参数会写入 `emotion.dynamics`、`consequences.dynamics`、`sylanne_memory.dynamics` 和各辅助状态的 `dynamics`，供调试、自有记忆和公共 API 回溯。 |

这意味着：

- 状态恢复速度会随人格漂移、关系稳定度、事件强度和修复质量自动改变。
- 冷处理剩余时间不会因为用户刷很多条消息而快速消耗。
- 大量文本可以形成新的观测，但不能绕过真实时间门控、平滑和单次更新限幅。
- 除最初人格建模入口外，用户不能手动把半衰期、阈值、冷却、冲量或学习率调成固定数值。

---

## 关系与后果

情绪状态不会直接等于回复模板。可以先这样理解：插件会把 `E_t` 映射成后果状态 `O_t`，其中包括靠近、退避、边界、修复、确认、谨慎、反刍和解决问题等维度；这些后果按真实时间衰减，所以冷处理、缓和和修复不会被消息数量直接刷掉。生气后的走向由“维度公式 + LLM 关系判断 + 冲突成因分析”共同决定，不会把所有负面情绪都硬推成冷战。

<details>
<summary>展开行动倾向、关系决策与后果衰减公式</summary>

插件先把情绪映射到行动倾向：

```math
O_t =
\begin{bmatrix}
\mathrm{approach} & \mathrm{withdrawal} & \mathrm{confrontation} &
\mathrm{appeasement} & \mathrm{repair} & \mathrm{reassurance} &
\mathrm{caution} & \mathrm{rumination} & \mathrm{expressiveness} &
\mathrm{problem\_solving}
\end{bmatrix}^{\mathsf T}
```

这些倾向按真实时间衰减：

```math
\Theta^O_t=f_O(P_t,E_t,X_t,F_t,\Delta t,\Theta^O_{t-1})
```

```math
\Theta^O_t=(1-\rho^O_t)\Theta^O_{t-1}+\rho^O_t\Theta^{O*}_t
```

```math
O_t = 2^{-\Delta t/H^O_t}O_{t-1}
+\mathrm{clip}\left(I^O_t(E_t,X_t,F_t),-M^O_t,M^O_t\right)
```

其中 `Theta^O_t` 是后果动力学参数族，包含后果半衰、短期效果时长、冷处理时长、触发门限、冲量上限和修复清除速率。它由人格漂移后的运行时人格 `P_t`、长期情绪 `E_t`、即时观测 `X_t`、冲突成因 `F_t` 和真实时间间隔自动推导，再与上一轮参数低通平滑。LLM 不直接给出 `H^O_t`、`M^O_t` 或冷处理时长；他/她只给出语义观察、关系判断和冲突原因。

| 后果维度 | 字段 | 常见表现 |
| --- | --- | --- |
| 靠近 | `approach` | 更愿意主动解释、接话、维持亲近。 |
| 退避 | `withdrawal` | 降低主动性，减少亲昵，可能进入冷处理。 |
| 对抗/边界 | `confrontation` | 语气更坚定，明确指出越界或错误。 |
| 安抚 | `appeasement` | 降低冲突，先稳定关系。 |
| 修复 | `repair` | 主动解释、给台阶、请求澄清。 |
| 确认 | `reassurance` | 询问意图、确认关系安全。 |
| 谨慎 | `caution` | 先核对事实，避免误会。 |
| 反刍 | `rumination` | 对冲突残留记挂，恢复较慢。 |
| 表达强度 | `expressiveness` | 更直接或更明显地表达情绪。 |
| 解决问题 | `problem_solving` | 把注意力转回具体任务。 |

### 大模型关系决策

当出现生气、冒犯、道歉、误会或修复信号时，LLM 会输出：

```json
{
  "relationship_decision": {
    "decision": "forgive",
    "intensity": 0.6,
    "forgiveness": 0.8,
    "relationship_importance": 0.7,
    "reason": "用户承认错误并给出补救"
  }
}
```

`decision` 可选值：

| 值 | 含义 | 后果 |
| --- | --- | --- |
| `forgive` | 原谅/翻篇 | 退避、反刍、对抗快速下降，冷处理清除。 |
| `repair` | 愿意修复 | 提高修复和确认，保留一定谨慎。 |
| `boundary` | 设边界 | 提高坚定度和边界感，不一定冷战。 |
| `cold_war` | 冷处理/拉开距离 | 提高退避和反刍，添加 `cold_war` 持续效果。 |
| `escalate` | 更强防御或冲突升级 | 提高对抗和表达强度。 |
| `none` | 无明显关系事件 | 不额外触发关系后果。 |

</details>

### 冲突原因分析

默认逻辑：先判断冲突是否真的发生，再判断原因属于用户犯错、他/她任性、误读、双方共同作用还是外部因素；最后再看错误是否被承认、道歉是否可信、补救是否完成。只有“伤害较重、重复发生、补救不足、信任受损”同时较强时，冷处理或强边界才会持续；如果误读概率高或他/她本身反应过度，则会转向求证、修复或自我缓和。

<details>
<summary>展开扩展冲突成因与关系修复公式</summary>

插件要求 LLM 同时输出：

```json
{
  "conflict_analysis": {
    "cause": "user_fault",
    "fault_severity": 0.62,
    "user_acknowledged": true,
    "apology_sincerity": 0.71,
    "repaired": true,
    "repair_quality": 0.68,
    "repeat_offense": 0.1,
    "bot_whim_level": 0.0,
    "misread_likelihood": 0.12,
    "forgiveness_readiness": 0.74,
    "resentment_residue": 0.18,
    "withdrawal_motive": "cooling_down",
    "boundary_legitimacy": 0.42,
    "reason": "用户越界但已承认并补救"
  }
}
```

主要字段：

| 字段 | 含义 |
| --- | --- |
| `cause` | `user_fault`、`bot_whim`、`bot_misread`、`mutual`、`external`、`none`。 |
| `fault_severity` | 错误严重度。 |
| `user_acknowledged` | 用户是否承认问题。 |
| `apology_sincerity` | 道歉可信度。 |
| `repaired` | 错误是否已经被补救。 |
| `repair_quality` | 补救质量。 |
| `repeat_offense` | 是否反复发生。 |
| `bot_whim_level` | 是否可能是 bot 任性或过度反应。 |
| `misread_likelihood` | 是否可能误读用户。 |
| `forgiveness_readiness` | 原谅准备度。 |
| `resentment_residue` | 残留委屈。 |
| `boundary_legitimacy` | 设边界是否合理。 |
| `repair_status` | 派生字段，表示 `unresolved`、`acknowledged`、`repaired`、`restored` 等修复阶段。 |

如果 LLM 一开始判断为 `cold_war`，但冲突分析显示用户已经补救、道歉足够完整、bot 误读概率高，或者原因更像他/她任性，本地后果层会把冷处理转向修复，并清除或降低负面后果。

</details>

### 安全边界开关

`enable_safety_boundary` 默认开启。开启时，插件注入的规则会把冷处理限制为：

- 轻微降频。
- 短句。
- 保持距离。
- 增强边界感。
- 不羞辱、不威胁、不操控、不拒绝必要帮助。

如果你关闭：

```text
enable_safety_boundary = false
```

本插件不再附加上述“冷处理只能如何表现”的额外调制规则，而只按 `active_effects` 和行动倾向调节语气、节奏、距离感与互动策略。关闭这个开关不会改变 AstrBot、模型供应商或其他插件自己的边界规则。

---

## 配置指南

完整配置来自 `_conf_schema.json`。这里按实际使用顺序整理。

### 总开关与模型

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enabled` | bool | `true` | 启用插件。 |
| `use_llm_assessor` | bool | `true` | 使用 LLM 判断情绪观测值；关闭后只使用启发式回退。 |
| `emotion_provider_id` | string | `""` | 情绪估计使用的 LLM Provider；留空使用当前会话模型。 |
| `fast_assessor_provider_id` | string | `""` | 快速判断 LLM Provider；用于用户碎片完整性、轻量一致性等短 JSON 判断。留空时回退到 `emotion_provider_id` 或当前会话模型。 |
| `fast_assessor_max_context_chars` | int | `600` | 快速判断 LLM 最多读取的上下文字数；低推理快模型上下文短，建议保持 400-800，复杂长上下文仍交给原判断 LLM。 |
| `fast_assessor_timeout_seconds` | float | `2.0` | 快速判断 LLM 超时秒数；超时或失败会走本地回退，避免拖慢主回复。 |
| `fast_assessor_temperature` | float | `0.0` | 快速判断 LLM temperature；简单 JSON 判断建议保持 0。 |
| `assessment_timing` | string | `post` | `pre`、`post` 或 `both`。默认 `post` 用一次内部评估降低延迟；`both` 质量更强但更慢。 |
| `inject_state` | bool | `true` | 是否把当前状态临时注入主 LLM。 |
| `max_context_chars` | int | `1600` | 情绪估计读取的最大上下文字数。 |
| `request_context_max_chars` | int | `1600` | 生命周期钩子拼接上下文时的总字数上限。 |
| `assessor_timeout_seconds` | float | `0.0` | 情绪估计 LLM 硬超时秒数；`0` 表示不限制，等待模型自然返回。只有压测、成本保护或隔离极慢模型时才建议设为大于 `0`。 |
| `provider_id_cache_ttl_seconds` | float | `30.0` | 未配置 `emotion_provider_id` 时，当前会话提供方标识的短缓存秒数。 |
| `passive_load_fresh_seconds` | float | `1.0` | 短时间重复读状态时跳过被动衰减计算，减少公共 API 与注入路径延迟。 |
| `benchmark_enable_simulated_time` | bool | `false` | 远程性能/生命周期基准测试专用；开启后允许测试脚本注入模拟时间偏移。 |
| `benchmark_time_offset_seconds` | float | `0.0` | 远程性能/生命周期基准测试专用；仅在 `benchmark_enable_simulated_time=true` 时把观测时间视为 `time.time()+offset`。 |
| `assessor_temperature` | float | `0.1` | 情绪估计模型 temperature。 |

内部判断 LLM 分成两档：`emotion_provider_id` 仍负责情绪观测、主动话题裁决等需要更完整上下文的判断；`fast_assessor_provider_id` 只负责碎片完整性、轻量一致性这类短 JSON 判断。快速判断会使用独立的短上下文预算和更短超时，失败时回退到本地规则或原判断 LLM 路径，不会替代复杂裁决。

内部判断 LLM 的提示词会要求“尽快输出最低完整 JSON”：不写长推导，不输出 Markdown，但必须保留 7 维情绪、置信度、关系决策和冲突分析。这样控制的是输出篇幅，不是削掉建模字段；默认取消硬超时后，慢模型也能自然返回最低可用观测。

`benchmark_enable_simulated_time` 和 `benchmark_time_offset_seconds` 只用于测试真实时间半衰期、人格漂移和长期状态模型。生产对话应保持默认关闭；生命周期 benchmark 会临时把 offset 设置为 `1d`、`1w`、`1m`、`1y` 等秒数，跑完后由远程脚本恢复原配置。

### 主动发言发送

主动发言分两层：`get_proactive_speech_decision(...)` 只读裁决，`request_proactive_speech_dispatch(...)` 负责生成可审计发送请求，并在配置允许时调用 AstrBot 发送链路。话题不能凭空冒出来，必须带 `topic_evidence`，例如“用户近期项目进度”“共同语境中的黑话”“互需/想念信号”“轻松氛围下的调皮打扰”。

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enable_proactive_speech_dispatch` | bool | `false` | 是否允许插件真正调用 `context.send_message` 主动发消息。关闭时只返回 `dispatch_request` 和未发送原因。 |
| `enable_proactive_speech_scheduler` | bool | `false` | 是否启用后台主动聊天调度器。开启后会从最近可触达会话中选择候选；真正发送仍要求 `enable_proactive_speech_dispatch=true`。 |

主动发言的后台调度器不是固定闹钟。她会先登记最近出现过、具备 `unified_msg_origin` 的会话；后台低频醒来时，会在环境压力不高、同会话未被锁住、近期没有重复检查的前提下，把最近用户消息和上下文摘要交给主动发言裁决。裁决仍然要经过本地公式、LLM 话题判断、真实时间安静门、冷却、发送开关和 `context.send_message` 接口检查。

主动发言不会只看最后一句。每次用户请求都会写入一个短期上下文窗口，调度器醒来时会把最近几轮用户文本和请求上下文整理成“近期上下文摘要”，再附上当前请求摘要、打断/未完成回复摘要、主动反馈状态和 Sylanne 自有记忆召回摘要。召回 query 会综合当前用户消息、近期请求上下文和插件临时断点，因此用户连续补充“不是啊，我说的是插件其他用户 / 那他们呢”时，主 LLM 不会只看到最后一句“他们呢”。如果自有记忆为空或读取失败，链路会静默降级，不阻塞普通回复或主动聊天。

主动发言的冷却、有效期、句子长度、反馈观察窗口和刚聊完后的最短安静时间不会暴露为普通配置。插件会根据 `score`、边界敏感、打扰风险、修复需要、用户被照顾需要、bot 自己想被需要的程度、近期活跃时间和反馈压力自动计算，并写入 `dispatch_request.adaptive_policy` 与 `dispatch_request.quiet_gate`。如果主动发言后用户没有回应，或只回了“嗯”“好”这类低信号短句，插件会把它记录为 `unanswered` 或 `cold_reply`，后续会更谨慎地判断开口时机。

返回结果里的 `dispatch_request` 会包含 `requested`、`reason`、`topic_evidence`、`message_text`、`unified_msg_origin`、`idempotency_key`、`adaptive_policy`、`quiet_gate`、`sent` 和 `blocked_reason`。常见未发送原因包括 `dispatch_disabled`、`recent_user_activity_quiet_period`、`cooldown_active`、`missing_event_origin`、`missing_send_message_api`、`decision_declined` 和 `dry_run`。

### 真人即时聊天与表情包

即时聊天层负责“怎么发出去”，不重新替代情绪模型本身。文本仍由主 LLM 生成；插件只在本地做分条、节奏、冷却、表情包候选选择和轻量记忆。这样可以降低 token 消耗，也能让其他插件直接调用计划接口。

即时聊天接管只发生在最终自然语言回复上。若 AstrBot Agent 正在进行工具调用，`LLMResponse` 里带有 `tool_calls`、`function_call`、工具角色、工具调用 ID 或 `finish_reason=tool_calls`，Sylanne 会直接放行：不改写 `completion_text`，不阻断事件传播，不消费会话 epoch。这样工具查询、记忆查询和其他插件工具仍由 AstrBot Agent 原生循环处理；Sylanne 只在最终可发送文本出现后接管投递。

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enable_realtime_chat` | bool | `true` | 是否启用真人即时聊天分条发送。 |
| `realtime_chat_style_prompt_enabled` | bool | `true` | 请求阶段加入短提示，让主模型少用报告腔、Markdown 和编号清单。 |
| `realtime_chat_intercept_llm_response` | bool | `true` | 是否在 `on_llm_response` 尝试接管默认回复并分条发送；若平台不支持改写响应，可关闭。 |
| `realtime_input_completion_llm_gate_enabled` | bool | `true` | 疑似用户还没说完时，是否调用内部判断 LLM 判断分段输入是否完整。 |
| `realtime_input_completion_probe_delay_seconds` | float | `0.25` | 首个疑似碎片后的基础探测等待秒数；插件会按碎片数量和窗口状态自动缩放。 |
| `realtime_input_completion_max_wait_seconds` | float | `4.0` | 判断用户仍未说完时的单轮最长等待时间；运行时带 4 秒硬上限，超过后放行，把主要时间留给 LLM 正常理解合并后的用户意图。 |
| `realtime_chat_dry_run_default` | bool | `false` | 公共 API 未显式传 `dry_run` 时是否只返回计划不发送。 |
| `realtime_chat_strip_markdown` | bool | `true` | 分条前清理常见 Markdown 标记。 |
| `enable_sticker_reaction` | bool | `true` | 是否根据情绪和氛围补发表情包。 |
| `sticker_llm_consistency_check_enabled` | bool | `true` | 表情包发送前做意图一致性检查，避免文件名/标签与本轮回复语气冲突。 |
| `sticker_default_repo_url` | string | `https://github.com/zhaoolee/ChineseBQB.git` | 默认表情包参考仓库，仅供用户自行准备素材；插件不分发该仓库。 |
| `sticker_local_root` | string | `""` | 本地表情包目录。 |
| `sticker_allowed_extensions` | string | `.jpg,.jpeg,.png,.gif,.webp` | 允许索引的图片扩展名。 |
| `sticker_selected_packs` | string | `""` | 表情包子包筛选词，留空表示不筛选。 |
| `sticker_index_limit` | int | `1000` | 本地表情包索引上限。 |
| `sticker_index_cache_ttl_seconds` | float | `86400.0` | 表情包索引缓存秒数。 |
| `sticker_max_file_bytes` | int | `5242880` | 单个候选图片最大字节数。 |
| `sticker_learn_user_images` | bool | `true` | 是否学习用户表情包元数据。 |
| `sticker_learned_limit` | int | `200` | 每会话保留的用户表情元数据上限。 |

即时聊天的分条数量、单条长度、打字速度、停顿、抖动、同会话接管冷却和表情包发送概率，都由人格模型、当前情绪、群聊氛围和生命化学习状态自动派生。外向、亲近、情绪唤醒高时会更容易分成自然短句；边界敏感、疏离、群聊紧张或打断风险高时会更克制、更少发图、更慢开口。`get_realtime_chat_plan(...)` 会在返回值的 `adaptive.realtime_chat` 和 `adaptive.sticker` 中说明当轮为什么这样计算。

从 `1.8.0` 起，即时聊天会把用户说话方式纳入生命化学习：本地统计用户消息的平均句长、换行密度、标点停顿、短句倾向、长段倾向和碎片化程度，并以真实时间下的平滑方式写入 `lifelike_learning_state.user_profile.speaking_style`。分条时她不会直接复制用户口癖，而是把这些统计量折算成 `user_style_adaptation`：用户常用短句、换行和碎片化表达时，她会更愿意多分几条短消息；用户常写长段、正式说明或要求严谨细节时，她会保留更长的单条消息，避免把技术说明切得太碎。这个过程不额外调用判断 LLM，也不会把用户画像原文暴露在公共 plan 里。

输入侧也会理解用户分段。若同一会话、同一说话人在很短时间内连续发出短字、表情、疑问收束词、明显续写片段或来源追问铺垫，插件会先在本地维护一个轻量碎片窗口；当窗口形成完整意图时，会临时注入 `[sylanne_user_message_fragments]`，告诉主 LLM 把这些碎片当作同一轮用户话语。例如“你 / 是 / 🐷 / 吗”会被解释成“你 是 🐷 吗”，“我只是很纳闷 / 为啥你要问我 / 是从哪里看来的”会被解释成一段完整的来源追问，而不是只回应最后一句。这个聚合只在同一说话人、短时间窗口内生效；换人、超时或长段文本会重新开窗，避免把群聊里不同人的话硬拼在一起。

当前版本中，疑似没说完的碎片会先暂停默认回复，不立刻跑情绪评估。插件会短暂等待下一条消息；若开启 `realtime_input_completion_llm_gate_enabled`，还会让判断 LLM 只输出最小 JSON，判断用户是否已经把这句话说完。判断为未完成时继续等待，但单轮不超过 `realtime_input_completion_max_wait_seconds`，且运行时最多 4 秒，避免用户真的不说话时 bot 永久沉默。最终放行后，主 LLM 和情绪模型看到的是合并后的完整意图。

长回复不会再为了满足 `max_parts` 硬上限而把尾部静默截成 `...`。`max_parts` 现在只表示日常偏好的初始分段数量；如果回复太长，分段器会继续按安全长度拆成更多消息，尽量避免平台把单条超长文本折叠成省略显示，也避免丢失正文。若用户在分条发送途中插话，剩余未发部分会被记录成低 token 的断点摘要，下一轮只把它作为“旧回复被打断”的上下文，不会把长文本全文塞回提示词。

如果主 LLM 还在生成，用户已经补发了新消息，Sylanne 不会把旧回复硬塞到新上下文后面。插件会给每个会话维护一个轻量 `input_epoch`：用户新消息进入时 epoch 前进；旧回复到达时如果发现 epoch 已经过期，就让旧输出自然过期并跳过后台 post 情绪评估。已经开始分条发送时，每一条发送前也会检查 epoch；用户插话后剩余分条和表情包都会停止。对已经被即时聊天接管并实际发送的回复，插件会保留一次性 assistant 历史影子；如果用户在分条发送中途插话，也会把已经发出的短句作为活跃派发摘要临时注入新请求，用来维持“他们、刚才、那个”这类指代关系。低信号消息，例如单独的“？”或一个表情，不会立刻消费这份 assistant 历史影子；真正有内容的下一轮追问仍能拿到上下文。相关摘要注入后会立即消费，避免 token 持续膨胀。

插话本身不会被硬编码为生气、开心或亲密。她只记录“bot 刚才有话没说完、已发了哪些、未发摘要是什么、用户随后补了什么”这些事实，并把它作为 `[assistant_interrupted_event]` 交给情绪判断。正向还是负面，要由判断模型结合人格、当前关系、用户语气和上下文自己判断。

普通回复链路会优先使用 Sylanne 自有记忆。召回内容只会被压缩成 `[sylanne_memory_recall]` 短摘要，用来帮助主 LLM 理解“他们”“刚才那个”“之前说过的进度”这类指代和长期偏好；插件不会把整段记忆库塞回提示词，也不会因为记忆为空、KV 读取失败或召回分数不足而阻断回复。召回数量、成熟等待、记忆深度、遗忘半衰期、压缩阈值和干扰敏感度全部由本地公式按人格、情绪、关系、群聊氛围和真实时间自动推导，不提供用户手动调参入口。

NapCat/OneBot 的撤回事件也可以接入这个机制。NapCat 的撤回属于 OneBot `notice` 事件，私聊撤回为 `notice_type=friend_recall`，群撤回为 `notice_type=group_recall`，常见字段包括 `message_id`、`user_id`、群撤回里的 `group_id` 与 `operator_id`。如果适配器能把原始 notice 放在 `event.message_obj.raw_message`、`event.raw_message` 或同类字段里，插件可解析撤回载荷；其他插件也可以直接调用 `observe_user_message_withdrawal(...)`。撤回后会推进会话 epoch、清空该会话最近主动聊天候选摘要，并让旧回复自然过期。若平台没有把撤回事件交给插件，则只能等用户补发更正消息后按“新消息打断旧回复”处理。

`ChineseBQB` 仓库体积很大且未随本插件重新授权分发，所以本插件只保留默认 URL 和本地目录索引能力。发布 zip 不包含 `ChineseBQB/`、用户偷来的表情包、缓存图片或外部素材库；“偷表情包”只表示记录轻量来源信息，方便以后在同一会话氛围下复用。

### 低推理模型友好模式

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `low_reasoning_friendly_mode` | bool | `false` | 开启后使用短版提示词和简化公式。 |
| `low_reasoning_max_context_chars` | int | `1200` | 低推理模式下最大上下文字数，会与 `max_context_chars` 取较小值。 |

低推理模式只影响 LLM 如何估计即时观测值，不改变本地状态平滑、真实时间衰减、人格基线、后果映射、冷处理持续时间和重置后门。

### 状态注入、后台评估与工具预算

这些配置主要服务 `1.0.0` 的状态层整合：减少主回复链路等待、压缩临时提示词（prompt）注入、把详细状态交给工具按需查询。

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `background_post_queue_limit` | int | `0` | 每个会话回复后后台评估（post）队列上限；`0` 表示不限制。 |
| `enable_dynamic_background_workers` | bool | `false` | 高负载时允许插件按队列深度、等待时间、重试、租约压力和 CPU/内存环境压力自适应选择后台工作器数量；基础为 `1`，全插件同时活跃后台工作器硬上限固定为 `6`，环境压力高或压力未知时会自动降档，并通过冷却时间逐级扩容，空闲后自动关闭，状态提交仍保持顺序。内部判断大模型另有并发闸门，默认最多 `2` 路、极端积压最多 `3` 路。 |
| `background_post_queue_checkpoint_enabled` | bool | `true` | 将未提交后台队列写入 KV 检查点，重启后可恢复。 |
| `background_post_job_lease_seconds` | float | `120.0` | 后台任务租约秒数；租约过期后可回收未完成任务。 |
| `background_post_job_timeout_seconds` | float | `0.0` | 单个后台任务超时秒数；`0` 表示不启用任务级超时。 |
| `background_post_retry_max_attempts` | int | `3` | 后台任务进入失败任务留存队列（dead-letter）前的最大尝试次数。 |
| `background_post_retry_base_delay_seconds` | float | `2.0` | 后台任务重试指数退避的基础延迟。 |
| `background_post_retry_max_delay_seconds` | float | `60.0` | 后台任务重试退避最大延迟。 |
| `background_post_dead_letter_limit` | int | `100` | 每个会话保留的失败任务留存（dead-letter）诊断摘要数量。 |
| `background_post_diagnostics_warn_lag_count` | int | `20` | 队列与活跃后台任务数量达到该值时诊断标记为 warn。 |
| `background_post_diagnostics_warn_lag_seconds` | float | `60.0` | 最老后台任务等待超过该秒数时诊断标记为 warn。 |
| `enable_low_signal_light_assessment` | bool | `true` | 对很短、低信号消息使用本地轻评估，避免无意义内部 LLM 调用。 |
| `low_signal_max_chars` | int | `12` | 低信号轻评估的最大文本长度。 |
| `runtime_parameter_debug_override_enabled` | bool | `false` | 运行时参数调试覆盖。默认关闭；开启后才允许维护者临时读取旧配置键排查。 |
| `state_injection_request_budget_chars` | int | `32000` | 主 LLM 请求可见字符预算估计；超预算时跳过状态注入。 |
| `state_injection_reserved_chars` | int | `3000` | 给模型提供方包装、工具 schema 和 persona 展开预留的字符余量。 |
| `state_injection_max_added_chars` | int | `2400` | 单次主请求中本插件最多追加的临时状态注入字符数。 |
| `state_injection_max_parts` | int | `8` | 单次主请求中本插件最多追加的临时状态注入片段数。 |
| `llm_tool_response_max_chars` | int | `16000` | 内部状态查询 JSON 的最大字符数；主 LLM 默认不再直接看到 Sylanne 内部 Tool schema。 |

主情绪状态注入不再由用户选择 `compact/full/diff`。插件会根据状态显著性、关系后果、活跃效果、请求预算压力和历史快照自动决定：高显著且预算宽裕时给主状态更多细节；普通或预算紧张时使用 compact/diff；辅助状态通常只给内部查询和公共 API。诊断接口 `query_agent_state(state="runtime")` 会显示 `state_injection.auto_decision`。

回复后评估（`post`）后台化默认自动开启，主回复结束后不会等待内部 `post` 评估完成，状态会稍后按会话顺序进入 AstrBot KV。`enable_dynamic_background_workers=false` 时每个会话只使用基础 `1` 个后台工作器；打开后也不会直接跳到固定并发，而是由插件根据队列压力、环境压力和全局活跃后台工作器预算逐级扩容。CPU/内存压力偏高时会自动降档，环境压力无法读取时按保守档处理；已有任务不会被强杀，但后续领取会变少，空闲后自动收掉。它可能增加接口、令牌与 CPU 压力，所以默认关闭。

### 群聊氛围、说话人轨道与因果轨迹

群聊状态层把“房间气氛”和“当前说话人”从普通会话情绪中拆出来，让 bot 更会判断什么时候开口、什么时候先听。

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `agent_speaker_relationship_tracking` | bool | `true` | 在群聊中维护 conversation + speaker 的定向关系/情绪轨道。 |
| `agent_include_speaker_in_assessment` | bool | `true` | 内部评估文本中标记当前说话人，便于区分不同用户。 |
| `agent_identity_profile_limit` | int | `256` | 最多缓存的会话/说话人身份画像数。 |
| `agent_identity_ttl_seconds` | float | `2592000.0` | 静默身份画像的 TTL，默认 30 天；`0` 表示仅按数量上限裁剪。 |
| `enable_agent_causal_trail` | bool | `true` | 启用脱敏 agent 因果轨迹，记录状态变化原因链。 |
| `agent_trail_limit` | int | `80` | 每个会话保留的因果轨迹条数。 |
| `agent_trail_compaction_enabled` | bool | `true` | 查询时提供低信号轨迹压缩视图。 |
| `agent_trail_low_signal_delta_threshold` | float | `0.03` | 因果轨迹压缩的工程阈值；不参与情绪/人格动力学。 |
| `agent_trail_low_signal_window` | int | `5` | 连续低信号轨迹达到该窗口后压缩为摘要。 |

群聊氛围维度包括 `activity_level`、`tension`、`playfulness`、`supportiveness`、`bot_attention`、`interrupt_risk` 和 `joinability`。这些值不会替代核心情绪，只是告诉 bot：现在适合自然加入、短应一下、先听，还是避免打断。

`group_atmosphere_state` 默认自动运行，不提供总开关，也不提供 `alpha`、半衰期、开口冷却、绕过注意力阈值或轨迹长度等细参旋钮。群聊更新步长、回落半衰、hold/join 阈值、开口冷却轮数、冷却秒数和绕过阈值都会由本地公式根据运行时人格模型、房间活跃度、紧张度、支持度、bot 被点名程度、近期发言轨迹和真实时间间隔自动推导，并写入 `group_atmosphere_state.dynamics`。LLM 只在需要时判断语境意义和话题方向，不直接输出这些数值。

### 人格建模

人格建模是整条链路的源头：插件会从 AstrBot 当前 persona 构造运行时人格画像、情绪基线、trait 分数、置信度和派生因子。后续人格漂移只改变运行时画像的小幅偏移，不改写原始 persona 文本。除最初 persona 本身外，用户不能把后续动力学细参手动固定。

### 情绪动力学

主情绪的更新步长、最小/最大步长、基线回落半衰、置信门控、短时反刷屏门控、惊讶耦合和支配感耦合都不是配置项。它们会在每次更新时由 `derive_emotion_update_dynamics(...)` 根据运行时人格模型、上一状态、当前观测置信度、惊讶度、真实时间间隔和已有 `state.dynamics` 自动派生。推导结果会写入 `emotion.dynamics`，用于解释“为什么这一轮更敏感/更稳定/更慢恢复”。

### 情绪后果

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enable_safety_boundary` | bool | `true` | 情绪后果安全边界，默认开启，可关闭。 |
| `block_deception_manipulation_evasion_actions` | bool | `true` | 是否输出插件层硬阻断动作；默认开启。关闭后只保留风险观察与修复建议，不额外写入阻断动作。 |
| `allow_emotion_reset_backdoor` | bool | `true` | 是否允许手动/API 重置情绪状态。 |

情绪后果的半衰期、触发阈值、强度倍率、冷处理时长和短期后果时长不再作为用户配置项。它们只是代码内部的先验尺度，最终生效值会由本地状态机根据人格画像、人格漂移、当前情绪向量、冲突成因、修复信号、误读概率、信任损伤、重复犯错和真实时间间隔自动推导，并写入 `consequences.dynamics`。相邻轮次会按真实时间低通平滑，所以不会因为一条消息突然跳变，也不能靠刷消息把冷处理或反刍后果刷掉。

LLM 在这里只负责给出语义观察：`relationship_decision`、`conflict_analysis` 和各维度情绪观测。本地公式负责计算有效参数、限幅、半衰、冷却和清除逻辑；低推理模型友好模式只会缩短 LLM 观察提示词，不会把这些动力学交给 LLM 随机决定。

### 生命化学习 / 共同语境

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `lifelike_learning_memory_write_enabled` | bool | `true` | 记忆写入时附带生命化学习状态注解。 |
| `allow_lifelike_learning_reset_backdoor` | bool | `true` | 是否允许重置生命化学习状态。 |

`lifelike_learning_state` 是会话级共同语境层，默认自动运行。它会记录“这个用户常用什么词、喜欢什么、不喜欢什么、何时需要距离感、何时适合轻轻追问”，但不会把这些记录当成事实证明。置信度不足的新词会进入 `ask_before_using`，让 bot 先问一句，而不是装作自己已经懂。学习半衰期、最小更新时间、词条置信增长、状态步长和反刷屏门控都由本地公式根据共同语境、边界敏感度、熟悉度、互需平衡和真实时间自动推导，并写入 `lifelike_learning_state.dynamics`；用户不能手工调这些细参，LLM 也不直接决定这些数值。

### 真实时间人格漂移

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `personality_drift_memory_write_enabled` | bool | `true` | 记忆写入时附带 `personality_drift_state_at_write`。 |
| `allow_personality_drift_reset_backdoor` | bool | `true` | 是否允许重置人格漂移状态。 |

人格漂移默认自动运行，且不允许用户直接调整学习率、半衰期、最大偏移或注入强度。流程固定为：真实时间事件先更新 `personality_drift_state`，人格漂移再小幅改变运行时人格建模，最后由人格建模影响情绪、拟人、生命化学习、群聊氛围、道德修复和瑕疵模拟等动力学。漂移学习率、事件阈值、最大单次冲量、最大 trait 偏移、短时门控半衰和长期锚定半衰都会根据锚定强度、证据巩固、关系重要性、事件强度、可靠度和已有偏移自动派生，并写入 `personality_drift_state.dynamics`。这样能保留长期相处的潜移默化变化，同时避免把人格变成可手调旋钮。

该模块只改变运行时画像的小幅偏移，不改写原始 persona 文本。`on_llm_request` 固化人格漂移时只使用当前消息作为新事件；历史 `contexts` 和系统提示词只服务即时情绪理解，不会被重复计入长期人格证据。外部插件若要写入事件，应使用 `observe_personality_drift_event(..., observed_at=...)`，其中 `observed_at` 是真实时间戳；不给时间戳时使用当前系统时间。

### 道德修复、瑕疵模拟与综合自我

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enable_moral_repair_state` | bool | `false` | 启用道德修复/信任修复状态模拟模块。 |
| `moral_repair_memory_write_enabled` | bool | `true` | 记忆写入时附带道德修复状态注解。 |
| `allow_moral_repair_reset_backdoor` | bool | `true` | 是否允许重置道德修复状态。 |
| `enable_fallibility_state` | bool | `false` | 启用低风险瑕疵/犯错模拟状态。 |
| `fallibility_memory_write_enabled` | bool | `true` | 记忆写入时附带瑕疵模拟状态注解。 |
| `allow_fallibility_reset_backdoor` | bool | `true` | 是否允许重置瑕疵模拟状态。 |
| `enable_shadow_diagnostics` | bool | `false` | 启用只读阴影诊断视图；默认关闭，只暴露非执行诊断信号。 |
| `enable_integrated_self_state` | bool | `true` | 启用只读综合自我状态总线。 |
| `integrated_self_memory_write_enabled` | bool | `true` | 记忆写入时附带综合自我状态注解。 |
| `integrated_self_degradation_profile` | string | `balanced` | 综合自我状态成本档位：`full`、`balanced` 或 `minimal`。 |

道德修复和瑕疵模拟的更新步长、置信门控、状态半衰、快速门控、冲量上限、错误压力上限和轨迹保留策略都由本地公式自动派生，不写入 `_conf_schema.json`，也不允许用户手调。开启模块后，LLM 只提供风险观察和语义归因；有效动力学会分别写入 `moral_repair_state.dynamics` 与 `fallibility_state.dynamics`，供公共 API、自有记忆注解和排障使用。

`fallibility_state` 只模拟低风险、不关键的瑕疵感：误读、记忆模糊、轻微嘴硬、逞强、回避、随后澄清、承认可能错了、纠正和补偿。它不是欺骗模块；风险越高，越会提高 `truthfulness_guard`、`clarification_need` 和 `correction_readiness`。

---

## Sylanne 自有长期记忆

Sylanne 不再依赖外部长期记忆插件。每次稳定用户输入、主动聊天候选和被打断回复的关键摘要，都会进入 Sylanne 自有记忆层；后续普通回复、插话恢复和主动聊天调度都会使用 `[sylanne_memory_recall]` 的限长摘要帮助主 LLM 理解指代、偏好、共同经历和相处方式。

从 `2.2.0` 开始，自有记忆支持可选向量检索。`2.3.11` 以后可以在 AstrBot 原生配置项里直接用 provider 选择器选择，也可以在插件详情页打开『记忆设置』Page，通过下拉框或 provider 卡片点选 Embedding 类型模型提供商；`sylanne_memory_embedding_provider_id` 仍保留手填兼容入口。留空时 Sylanne 会尝试使用第一个可用 Embedding 提供商。记忆召回会把关键词相似度、Embedding 余弦相似度、记忆深度、置信度、真实时间新鲜度和干扰强度一起计算。Embedding 不可用或报错时会自动退回原来的关键词 + 关联图检索，不阻断正常聊天。

放弃 LivingMemory 兼容不是因为 LivingMemory 不好。相反，LivingMemory 是一个很好的全生命周期记忆插件；这个项目一开始也确实是奔着“直接调用 LivingMemory，把情绪写进外部长期记忆”去做的。只是 Sylanne 后来叠加了即时聊天接管、分条发送、用户插话合并、未完整送达断点、主动发言调度和 Agent-owned context 之后，当前即时聊天链路会和外部全生命周期写入/召回逻辑发生冲突：同一段回复到底是“主 LLM 已生成”“默认发送口被阻断”“用户只读到前几条”还是“已经完整进入长期记忆”，需要插件自己精确区分。为了先保证记忆的正常写入、召回和上下文不乱，`2.0.0` 起暂时放弃对 LivingMemory 的运行时兼容，改为自研 Sylanne 自有记忆模块。后续如果两边生命周期边界能稳定对齐，再重新做可选适配。

这层记忆更接近一个轻量本地知识库，而不是聊天上下文的无限追加：每条记忆会存成独立记录，包含 `summary`、限长 `text`、会话键、说话人、记忆层类型、情绪签名、关系签名、深度、置信度、证据次数、召回次数、上次召回时间和自动动力学参数。普通回复和主动聊天只按当前 query 检索少量高分摘要，注入 `[sylanne_memory_recall]`，不会把整个记忆库塞进 prompt。

记忆会按真实时间变化。相似事件再次发生时，`evidence_count`、`depth` 和 `confidence` 会被巩固；某条记忆真正被召回并注入上下文后，`recall_count`、`last_recalled_at` 和 `retrieval_reinforcement` 会更新，让常被用到且有解释价值的记忆更稳。长期没有证据、没有召回、深度和置信度都很低的旧记忆，会在读取时按半衰期被削弱，必要时从 KV 中落盘删除；重要记忆则因为证据、深度、置信度和召回次数更高而更抗遗忘。

记忆核心参数由插件自动设置，不提供手动数值旋钮：

| 自动参数 | 来源 |
| --- | --- |
| 记忆深度 | 当前情绪显著性、关系权重、巩固强度、事件层类型。 |
| 遗忘半衰期 | 人格漂移锚定、共同语境、关系强度、神经质/依恋相关偏移和真实时间。 |
| 召回数量 | 关系权重、情绪显著性、共同语境强度。 |
| 召回成熟等待 | 群聊紧张度、打断风险、置信度和巩固强度。 |
| 压缩阈值 | 巩固强度与共同语境。 |
| 干扰敏感度 | 群聊紧张度、打断风险和不确定性。 |
| 召回强化 | 召回评分、语义匹配、巩固强度和真实召回时间。 |
| 遗忘剪枝 | 真实时间半衰、记忆深度、置信度、证据次数和召回次数。 |
| 联想关联 | 摘要相似度、记忆层重叠、情绪接近度、真实时间接近度和共同巩固强度。 |

这些参数会写入 `sylanne_memory.dynamics` 和每条记忆的 `auto_parameters`，只允许通过调试视图查看，不允许配置者手动覆盖。这样能保证“人格漂移影响人格建模，人格建模影响记忆动力学”，而不是把长期相处变成一组手调滑块。

2.0.0 以后，记忆之间还会形成一张很轻的关系网：每条记忆只保留同会话内少量高权重邻居。普通召回会先按当前 query 命中核心记忆，再从核心记忆的一跳邻居里取少量联想记忆；联想结果仍和核心召回一起压缩进同一个 `[sylanne_memory_recall]`，继续受字符预算限制。这样她能在看到“他们”时想起“他们指插件的其他用户”，再顺手想起“对插件使用者说话要温和、别炫耀”，但不会把整个记忆库都倒进上下文。

完整理论和公式见 [docs/theory.md](docs/theory.md) 的“自有记忆知识库、关联召回与遗忘”一节。

自有 KV 记忆和 `build_emotion_memory_payload(...)` 是两条边界不同的能力：自有 KV 负责 Sylanne 自己的按需检索和长期相处痕迹；`build_emotion_memory_payload(...)` 负责给其他插件写入外部记录时冻结 `emotion_at_write`、`humanlike_state_at_write`、`lifelike_learning_state_at_write` 等状态注解。前者追求低 prompt 负担和可遗忘，后者追求写入时状态可追溯。

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enable_sylanne_memory` | bool | `true` | 启用 Sylanne 自有长期记忆。关闭后不写入也不召回。 |
| `sylanne_memory_vector_retrieval_enabled` | bool | `true` | 启用语义向量召回；AstrBot 中有 Embedding 提供商时会自动叠加余弦相似度，失败时回退关键词和关联图检索。 |
| `sylanne_memory_embedding_provider_id` | string | `""` | 原生配置中声明为 provider 选择项；也推荐在插件详情页的『记忆设置』Page 中下拉或点击卡片选择。留空时自动使用第一个可用 Embedding 提供商。 |
| `sylanne_memory_debug_view_enabled` | bool | `false` | 允许查看记忆摘要、深度、召回评分和自动推导 dynamics；只用于排障，不提供参数覆盖。 |
| `allow_sylanne_memory_reset_backdoor` | bool | `true` | 是否允许在严重误记、上下文污染或异常状态时重置当前会话自有记忆。 |

如果其他插件只想把当时状态冻结进自己的记录，本插件仍提供：

```python
build_emotion_memory_payload(...)
```

这个方法不会更新情绪状态，只读取当前快照，并把 `emotion_at_write` 和可选辅助状态固定进记忆载荷。这样以后情绪变化不会覆盖旧记忆。

### 推荐接法

```python
from astrbot_plugin_sylanne.public_api import get_emotion_service

emotion = get_emotion_service(self.context)

memory = {
    "text": memory_text,
    "tags": tags,
}

if emotion:
    memory = await emotion.build_emotion_memory_payload(
        event,
        memory=memory,
        memory_text=memory_text,
        source="sylanne_memory",
        include_prompt_fragment=False,
    )

await your_plugin_store.write(event, memory)
```

如果 LivingMemory 的接口只能写普通 dict，也可以合并字段；即使 Sylanne 未安装、未激活或版本不匹配，也要保留原始 memory 写入：

```python
memory = {"text": memory_text}

if emotion:
    payload = await emotion.build_emotion_memory_payload(
        event,
        memory=memory,
        memory_text=memory_text,
        source="sylanne_memory",
    )
    memory["emotion_at_write"] = payload["emotion_at_write"]
    if "humanlike_state_at_write" in payload:
        memory["humanlike_state_at_write"] = payload["humanlike_state_at_write"]
    if "lifelike_learning_state_at_write" in payload:
        memory["lifelike_learning_state_at_write"] = payload["lifelike_learning_state_at_write"]
    if "personality_drift_state_at_write" in payload:
        memory["personality_drift_state_at_write"] = payload["personality_drift_state_at_write"]
    if "moral_repair_state_at_write" in payload:
        memory["moral_repair_state_at_write"] = payload["moral_repair_state_at_write"]
    if "fallibility_state_at_write" in payload:
        memory["fallibility_state_at_write"] = payload["fallibility_state_at_write"]
    if "integrated_self_state_at_write" in payload:
        memory["integrated_self_state_at_write"] = payload["integrated_self_state_at_write"]
```

如果没有 `AstrMessageEvent`，必须显式传入稳定的 `session_key`：

```python
payload = await emotion.build_emotion_memory_payload(
    session_key="aiocqhttp:GroupMessage:12345",
    memory_text=memory_text,
    source="sylanne_memory",
)
```

### `emotion_at_write`

`emotion_at_write` 包含：

| 字段 | 含义 |
| --- | --- |
| `schema_version` | 记忆注解 schema，当前为 `astrbot.emotion_memory.v1`。 |
| `captured_from_schema_version` | 来源快照结构版本。 |
| `session_key` | 会话标识。 |
| `source` | 写入来源，例如 `sylanne_memory` 或调用方自己的插件名。 |
| `written_at` | 记忆写入时间。 |
| `emotion_updated_at` | 情绪状态最后更新时间。 |
| `label` | 当前情绪标签。 |
| `confidence` | 情绪估计置信度。 |
| `values` | 7 维情绪值。 |
| `persona` | 当前人格信息。 |
| `relationship` | 关系决策和冲突分析。 |
| `consequences` | 行动倾向和持续效果。 |
| `last_reason` | 最近一次情绪解释。 |
| `last_appraisal` | 最近一次 LLM appraisal。 |

`written_at` 和 `emotion_updated_at` 分开保存，便于以后判断“这条记忆是在冷处理刚发生时写的”，还是“冷处理已经持续一段真实时间后写的”。

### `humanlike_state_at_write`

如果：

```text
humanlike_memory_write_enabled = true
```

则 `build_emotion_memory_payload(...)` 会额外写入 `humanlike_state_at_write`。默认值是 `true`。

拟人状态默认自动运行，载荷通常会包含 `enabled=true`、公开摘要和 `humanlike_state_at_write`。只有插件整体关闭、旧版本兼容或内部降级时，调用方才需要按 `enabled=false` 做静默降级。

### `lifelike_learning_state_at_write`

如果：

```text
lifelike_learning_memory_write_enabled = true
```

则 `build_emotion_memory_payload(...)` 会额外写入 `lifelike_learning_state_at_write`。默认值是 `true`。

该字段冻结写入当时的共同语境、已确认新词、仍需先问再用的新词、用户画像证据计数、边界提示和 `initiative_policy`。它不保存原始消息文本，也不把用户画像当作不可错的事实；其他插件使用时应把它当作“当时的关系语境和节奏线索”。

生命化学习默认自动运行，载荷通常会包含 `enabled=true`、共同语境摘要和主动性策略。只有插件整体关闭、旧版本兼容或内部降级时，调用方才需要按 `enabled=false` 做静默降级。

### `personality_drift_state_at_write`

如果：

```text
personality_drift_memory_write_enabled = true
```

则 `build_emotion_memory_payload(...)` 会额外写入 `personality_drift_state_at_write`。默认值是 `true`。

该字段冻结写入当时的人格漂移摘要：`updated_at`、`evidence_count`、`drift_intensity`、`anchor_strength`、`time_gate` 和主要有界偏移。它不保存原始消息文本，也不保存完整 `trait_offsets`，用于让自有记忆或剧情插件知道“这条记忆写入时他/她的人格适应处在哪个真实时间阶段”。

人格漂移默认自动运行，载荷通常会包含 `enabled=true` 和真实时间漂移摘要。只有插件整体关闭、旧版本兼容或内部降级时，调用方才需要按 `enabled=false` 做静默降级。

### `moral_repair_state_at_write`

如果：

```text
moral_repair_memory_write_enabled = true
```

则 `build_emotion_memory_payload(...)` 会额外写入 `moral_repair_state_at_write`。默认值是 `true`。

该字段冻结当时的欺骗/伤害风险信号、责任感、内疚、道歉准备、补偿准备和信任修复进度。它只用于记忆与插件协作，不会保存提示词片段，也不会提供欺骗、隐瞒、操控或作恶策略。

即使 `enable_moral_repair_state=false`，载荷也会标记：

```json
{
  "enabled": false,
  "reason": "enable_moral_repair_state is false"
}
```

这样记忆系统可以知道“写入时拟人模块没有启用”，而不是误以为数据丢失。

### `fallibility_state_at_write`

如果：

```text
fallibility_memory_write_enabled = true
```

则 `build_emotion_memory_payload(...)` 会额外写入 `fallibility_state_at_write`。默认值是 `true`。

该字段冻结当时的误读倾向、记忆模糊、轻微嘴硬、澄清需求、纠错准备、补偿压力和真实性保护状态。它只保存状态摘要，不保存原始消息文本，也不保存任何欺骗、隐瞒、操控或作恶策略。

即使 `enable_fallibility_state=false`，载荷也会标记：

```json
{
  "enabled": false,
  "reason": "enable_fallibility_state is false"
}
```

这样记忆系统可以知道“写入时瑕疵模拟模块没有启用”，而不是误以为数据丢失。

### `integrated_self_state_at_write`

如果：

```text
integrated_self_memory_write_enabled = true
```

则 `build_emotion_memory_payload(...)` 会额外写入 `integrated_self_state_at_write`。默认值是 `true`。

该字段冻结写入时的综合 `response_posture`、跨模块风险优先级、允许动作和状态指数。它只记录仲裁结果，不保存原始快照，除非调用方显式设置 `include_raw_snapshot=True`。

默认不建议把 `prompt_fragment` 写入长期记忆，避免记忆膨胀。只有确实要复用注入文本时，才设置：

```python
include_prompt_fragment=True
```

---

## 公共 API

插件不只是自己 hook AstrBot，也可以作为其他插件的情绪模拟服务。

推荐入口：

```python
from astrbot_plugin_sylanne.public_api import (
    get_emotion_service,
    get_humanlike_service,
    get_lifelike_learning_service,
    get_personality_drift_service,
    get_moral_repair_service,
    get_fallibility_service,
)
```

不要直接读写本插件 KV key。KV key、缓存、迁移和内部结构都属于实现细节。

给其他插件作者的 30 秒接入方式：

```python
emotion = get_emotion_service(self.context)
if emotion:
    snapshot = await emotion.get_emotion_snapshot(event, include_prompt_fragment=False)
    values = await emotion.get_emotion_values(event)
    consequences = await emotion.get_emotion_consequences(event)
```

如果要把其他插件事件写入情绪系统：

```python
if emotion:
    await emotion.observe_emotion_text(
        event,
        text="用户在剧情插件中认真道歉，并解释了之前的误会。",
        role="user",
        source="my_plugin",
    )
```

如果只是想预览某句话会造成什么影响，不想落库：

```python
if emotion:
    preview = await emotion.simulate_emotion_update(
        event,
        text="用户再次重复同一个越界玩笑。",
        role="user",
        source="my_plugin",
    )
```

如果其他插件要写入当时状态，优先使用 `build_emotion_memory_payload` 或综合自我信封，不要自己拼内部字段。若 `get_emotion_service(self.context)` 返回 `None`，说明插件未安装、未启用或版本不匹配；调用方应静默降级，而不是中断主流程。

### 获取服务实例

```python
emotion = get_emotion_service(self.context)

if emotion:
    snapshot = await emotion.get_emotion_snapshot(event)
    values = snapshot["emotion"]["values"]
```

`get_humanlike_service(context)` 当前返回同一个已激活插件实例，但类型协议包含 humanlike 方法：

```python
humanlike = get_humanlike_service(self.context)

if humanlike:
    state = await humanlike.get_humanlike_snapshot(event, exposure="plugin_safe")
```

`get_lifelike_learning_service(context)` 同样返回已激活插件实例，但类型协议包含 lifelike learning 方法：

```python
lifelike = get_lifelike_learning_service(self.context)

if lifelike:
    state = await lifelike.get_lifelike_learning_snapshot(event, exposure="plugin_safe")
    policy = await lifelike.get_lifelike_initiative_policy(event)
```

`get_personality_drift_service(context)` 同样返回已激活插件实例，但类型协议包含 personality drift 方法：

```python
personality_drift = get_personality_drift_service(self.context)

if personality_drift:
    state = await personality_drift.get_personality_drift_snapshot(event, exposure="plugin_safe")
    preview = await personality_drift.simulate_personality_drift_update(
        event,
        text="用户认真修复了一次长期误会。",
        observed_at=real_event_timestamp,
    )
```

`get_moral_repair_service(context)` 同样返回已激活插件实例，但类型协议包含 moral repair 方法：

```python
moral_repair = get_moral_repair_service(self.context)

if moral_repair:
    state = await moral_repair.get_moral_repair_snapshot(event, exposure="plugin_safe")
```

`get_fallibility_service(context)` 同样返回已激活插件实例，但类型协议包含 fallibility 方法：

```python
fallibility = get_fallibility_service(self.context)

if fallibility:
    state = await fallibility.get_fallibility_snapshot(event, exposure="plugin_safe")
    preview = await fallibility.simulate_fallibility_update(
        event,
        text="刚才可能是 bot 误读了用户的话，随后主动更正。",
    )
```

如果不能 import helper，也可以使用 AstrBot 注册星标：

```python
meta = self.context.get_registered_star("astrbot_plugin_sylanne")
emotion = meta.star_cls if meta and meta.activated else None
```

这只能作为临时兼容兜底，不保证公共 API 完整，也不会校验版本/schema。长期维护时更推荐 `public_api.get_emotion_service(...)`、`public_api.get_humanlike_service(...)`、`public_api.get_lifelike_learning_service(...)`、`public_api.get_personality_drift_service(...)`、`public_api.get_moral_repair_service(...)` 和 `public_api.get_fallibility_service(...)`。这些 helper 会校验核心方法是否完整，并校验公开版本/schema 是否匹配，能避免其他插件拿到只有部分旧接口或旧数据契约的实例。

### 情绪 API

| 方法 | 是否写入状态 | 用途 |
| --- | --- | --- |
| `get_emotion_snapshot(event_or_session, include_prompt_fragment=False)` | 否 | 返回版本化 JSON 快照，推荐默认入口。 |
| `get_emotion_state(event_or_session, as_dict=True)` | 否 | 返回内部状态拷贝。 |
| `get_emotion_values(event_or_session)` | 否 | 只取 7 维情绪向量。 |
| `get_emotion_consequences(event_or_session)` | 否 | 只取行动倾向和持续效果。 |
| `get_emotion_relationship(event_or_session)` | 否 | 只取关系判断、冲突原因和修复状态。 |
| `get_emotion_prompt_fragment(event_or_session)` | 否 | 给其他插件注入提示词文本片段。 |
| `build_emotion_memory_payload(event_or_session=None, memory=None, *, session_key=None, memory_text="", source="sylanne_memory", include_raw_snapshot=True)` | 否 | 给长期记忆生成带状态注解的载荷。 |
| `inject_emotion_context(event, request)` | 否 | 直接给 `ProviderRequest` 追加情绪上下文。 |
| `observe_emotion_text(event_or_session, text, role="plugin", source="plugin")` | 是 | 外部插件提交文本观测并更新状态。 |
| `simulate_emotion_update(event_or_session, text)` | 否 | 预测候选文本会怎样影响状态，不落库。 |
| `reset_emotion_state(event_or_session)` | 是 | 重置指定会话；受 `allow_emotion_reset_backdoor` 控制。 |
| `get_integrated_self_snapshot(event_or_session, include_raw_snapshots=False)` | 否 | 获取跨模块综合自我状态总线。 |
| `get_integrated_self_prompt_fragment(event_or_session)` | 否 | 获取综合仲裁提示词片段。 |
| `get_integrated_self_policy_plan(event_or_session)` | 否 | 获取由综合状态推导出的响应调制和修复动作计划。 |
| `build_integrated_self_replay_bundle(event_or_session, scenario_name="current")` | 否 | 构建不含 raw snapshots 的确定性回放包。 |
| `replay_integrated_self_bundle(bundle)` | 否 | 离线回放综合自我状态核心摘要，不读取 KV。 |
| `probe_integrated_self_compatibility(payload=None, event_or_session=None)` | 否 | 检查载荷是否满足当前综合自我 schema。 |
| `export_integrated_self_diagnostics(event_or_session)` | 否 | 导出脱敏维护诊断摘要。 |
| `get_shadow_diagnostics(event_or_session)` | 否 | 获取配置门控的只读阴影冲动诊断载荷；不生成或执行策略。 |
| `get_lifelike_learning_snapshot(event_or_session, exposure="plugin_safe")` | 否 | 获取生命化学习/共同语境快照。 |
| `get_lifelike_initiative_policy(event_or_session)` | 否 | 获取当前适合开口、短应、追问或沉默的节奏策略。 |
| `get_proactive_speech_decision(event_or_session, candidate_context="", use_llm=True)` | 否 | 判断当前是否适合主动开口，并返回理由、证据、话题方向、短句草案和 `dispatch_request`。 |
| `request_proactive_speech_dispatch(event_or_session, candidate_context="", use_llm=True, dry_run=False, force=False, realtime=None)` | 是 | 请求 AstrBot 主动发送；默认受 `enable_proactive_speech_dispatch` 和冷却控制，可自动走即时聊天分条发送。 |
| `get_realtime_chat_plan(event_or_session, text, include_sticker=True)` | 否 | 生成即时聊天分条、打字间隔和表情包候选计划，不发送。 |
| `request_realtime_chat_dispatch(event_or_session, text, dry_run=None, force=False)` | 是 | 按计划顺序发送多条即时聊天消息；`dry_run` 可只试算。 |
| `observe_user_message_withdrawal(event_or_session=None, session_key=None, message_id="", reason="withdrawn")` | 是 | 标记用户撤回/更正消息，推进会话 epoch，停止旧分条输出，并清理最近主动聊天候选摘要。 |
| `observe_sticker_usage(event_or_session, sticker)` | 是 | 记录用户表情包轻量元数据，供后续表情共同语境使用，不保存二进制图片。 |
| `get_lifelike_prompt_fragment(event_or_session)` | 否 | 获取共同语境和对话节奏提示词片段。 |
| `observe_lifelike_text(event_or_session, text)` | 是 | 提交文本观察并更新新词、黑话、用户画像和边界线索。 |
| `simulate_lifelike_update(event_or_session, text)` | 否 | 模拟生命化学习更新，不落库。 |
| `reset_lifelike_learning_state(event_or_session)` | 是 | 重置生命化学习状态；受 `allow_lifelike_learning_reset_backdoor` 控制。 |
| `get_personality_drift_snapshot(event_or_session, exposure="plugin_safe")` | 否 | 获取真实时间人格漂移快照。 |
| `get_personality_drift_values(event_or_session)` | 否 | 获取漂移强度、锚点强度、事件固化和时间门控等控制维度。 |
| `get_personality_drift_prompt_fragment(event_or_session)` | 否 | 获取慢适应人格调制提示词片段，包含状态时间和年龄。 |
| `observe_personality_drift_event(event_or_session, text, observed_at=None)` | 是 | 外部插件提交真实事件并按真实时间更新人格漂移。 |
| `simulate_personality_drift_update(event_or_session, text, observed_at=None)` | 否 | 模拟人格漂移更新，不落库。 |
| `reset_personality_drift_state(event_or_session)` | 是 | 重置人格漂移状态；受 `allow_personality_drift_reset_backdoor` 控制。 |
| `get_moral_repair_snapshot(event_or_session, exposure="plugin_safe")` | 否 | 获取道德修复/信任修复状态快照。 |
| `get_moral_repair_values(event_or_session)` | 否 | 只取 moral repair 维度值。 |
| `get_moral_repair_prompt_fragment(event_or_session)` | 否 | 获取责任、道歉、补偿和信任修复提示词。 |
| `observe_moral_repair_text(event_or_session, text)` | 是 | 提交文本观察并更新状态。 |
| `simulate_moral_repair_update(event_or_session, text)` | 否 | 模拟道德修复更新，不落库。 |
| `reset_moral_repair_state(event_or_session)` | 是 | 重置道德修复状态；受 `allow_moral_repair_reset_backdoor` 控制。 |
| `get_fallibility_snapshot(event_or_session, exposure="plugin_safe")` | 否 | 获取低风险瑕疵/犯错模拟快照。 |
| `get_fallibility_values(event_or_session)` | 否 | 只取 fallibility 维度值。 |
| `get_fallibility_prompt_fragment(event_or_session)` | 否 | 获取澄清、纠错和低风险瑕疵调制提示词。 |
| `observe_fallibility_text(event_or_session, text)` | 是 | 提交文本观察并更新瑕疵模拟状态。 |
| `simulate_fallibility_update(event_or_session, text)` | 否 | 模拟瑕疵状态更新，不落库。 |
| `reset_fallibility_state(event_or_session)` | 是 | 重置瑕疵模拟状态；受 `allow_fallibility_reset_backdoor` 控制。 |

`event_or_session` 可以是 AstrBot 事件对象，也可以是字符串 `session_key`。

### 提交插件事件作为情绪观测

例如剧情插件想让“玩家拒绝道歉”影响 bot 情绪：

```python
snapshot = await emotion.observe_emotion_text(
    session_key="mood_game:user-42:chapter-3",
    text="玩家拒绝了 bot 的道歉",
    role="user",
    source="mood_game",
    use_llm=True,
)
```

如果只想预测，不想保存：

```python
preview = await emotion.simulate_emotion_update(
    event,
    text="用户再次开了越界玩笑，但随后认真道歉。",
    role="user",
    source="my_plugin",
)
```

### 读取关系修复状态

```python
relationship = await emotion.get_emotion_relationship(event)

decision = relationship["relationship_decision"]["decision"]
repair_status = relationship["repair_status"]

if decision == "cold_war":
    # 插件可以降低亲密剧情触发概率
    ...

if repair_status in {"repaired", "restored"}:
    # 插件可以降低冲突惩罚
    ...
```

### LLM 工具

`query_agent_state` 仍保留为 AstrBot LLM Tool 注册名、命令/API 后端和兼容入口，所以旧契约与测试仍能找到它；但从 `2.3.11` 开始，Sylanne 会在主聊天请求前把所有 Sylanne 自有 LLM Tool schema 从 `tools/functions` 中剪除。也就是说，主 LLM 不再直接看到 Sylanne 的内部状态工具；bot/Agent 路径、命令、设置 Page 和 Python 公共 API 仍可正常使用插件能力，外部插件工具也不会被 Sylanne 隐藏。

| 工具名 | 用途 |
| --- | --- |
| `query_agent_state` | 统一查询 `emotion`、`speaker`、`group_atmosphere`、`trail`、`runtime`、`integrated`、`humanlike`、`lifelike_learning`、`personality_drift`、`moral_repair`、`fallibility`、`psychological` 或 `all` 状态。 |

插件间调用仍建议使用 Python API，而不是把 LLM 工具当作互调协议。这个表格用于说明兼容入口语义，不表示主聊天模型每轮都会看到该 tool schema。

### 快照结构

当前 schema 常量：

| 常量 | 值 |
| --- | --- |
| `EMOTION_SCHEMA_VERSION` | `astrbot.emotion_state.v2` |
| `EMOTION_MEMORY_SCHEMA_VERSION` | `astrbot.emotion_memory.v1` |
| `PERSONALITY_PROFILE_SCHEMA_VERSION` | `astrbot.personality_profile.v1` |
| `PSYCHOLOGICAL_SCREENING_SCHEMA_VERSION` | `astrbot.psychological_screening.v1` |
| `HUMANLIKE_STATE_SCHEMA_VERSION` | `astrbot.humanlike_state.v1` |
| `LIFELIKE_LEARNING_SCHEMA_VERSION` | `astrbot.lifelike_learning_state.v1` |
| `PERSONALITY_DRIFT_SCHEMA_VERSION` | `astrbot.personality_drift_state.v1` |
| `MORAL_REPAIR_STATE_SCHEMA_VERSION` | `astrbot.moral_repair_state.v1` |
| `FALLIBILITY_STATE_SCHEMA_VERSION` | `astrbot.fallibility_state.v1` |
| `INTEGRATED_SELF_SCHEMA_VERSION` | `astrbot.integrated_self_state.v1` |
| `GROUP_ATMOSPHERE_SCHEMA_VERSION` | `astrbot.group_atmosphere_state.v1` |

### 综合自我 API

| 方法 | 是否写入状态 | 用途 |
| --- | --- | --- |
| `get_integrated_self_snapshot(event_or_session, include_raw_snapshots=False)` | 否 | 融合 emotion、humanlike、moral repair 和 psychological screening，返回只读仲裁结果。 |
| `get_integrated_self_prompt_fragment(event_or_session)` | 否 | 返回可注入提示词的综合仲裁片段。 |
| `get_integrated_self_policy_plan(event_or_session)` | 否 | 返回 `allowed_actions`、`blocked_actions`、表达调制、修复动作和提示词预算。 |
| `build_integrated_self_replay_bundle(event_or_session, scenario_name="current")` | 否 | 返回确定性回放包，便于测试状态演化，不读写 KV。 |
| `replay_integrated_self_bundle(bundle)` | 否 | 校验回放包 checksum 并返回核心 posture/risk/index。 |
| `probe_integrated_self_compatibility(payload=None, event_or_session=None)` | 否 | 返回兼容性探针，报告 schema 和必要字段缺失。 |
| `export_integrated_self_diagnostics(event_or_session)` | 否 | 返回脱敏诊断包，只含模块状态、风险布尔和 trace 摘要。 |

该总线的优先级顺序为：非诊断心理安全 > 道德修复透明性 > 关系边界 > 拟人资源调制 > 情绪风格。它还会输出 `causal_trace`、`policy_plan` 和 `compatibility`，用于解释每次状态仲裁为什么发生、低成本部署时保留哪些信号、以及第三方插件是否拿到了当前 schema。它不会生成诊断结论，也不会生成欺骗、隐瞒、操控或规避责任策略。

### 群聊氛围与统一插件状态 API

| 方法 | 是否写入状态 | 用途 |
| --- | --- | --- |
| `get_group_atmosphere_snapshot(event_or_session, exposure="plugin_safe")` | 否 | 获取群聊氛围、参与策略、冷却状态和轨迹摘要。 |
| `get_group_atmosphere_values(event_or_session)` | 否 | 只读取群聊氛围 7 维数值。 |
| `get_group_atmosphere_prompt_fragment(event_or_session)` | 否 | 获取可注入的群聊氛围提示词片段。 |
| `observe_group_atmosphere_text(event_or_session, text)` | 是 | 提交文本观察并更新群聊氛围状态。 |
| `simulate_group_atmosphere_update(event_or_session, text)` | 否 | 模拟群聊氛围更新，不写入 KV。 |
| `reset_group_atmosphere_state(event_or_session)` | 是 | 重置当前会话群聊氛围状态。 |
| `query_agent_state(event_or_session, state="all", detail="summary", track="conversation")` | 否 | 统一查询 emotion、speaker、group_atmosphere、trail、runtime 或 all。 |
| `get_agent_runtime_diagnostics(event_or_session)` | 否 | 获取后台评估、注入预算和队列滞后诊断。 |

`get_group_atmosphere_service(context)` 会校验核心服务存在、公开版本/schema 匹配，以及群聊氛围方法是否完整。其他插件需要群聊气氛、开口时机或房间级轨迹时，应优先走这个 helper；如果 helper 不可用，再回退到原本业务逻辑。

---

## 拟人状态 `humanlike_state`

`humanlike_state` 是一个独立的 P0 子系统，默认自动运行。用户不需要、也不能通过配置直接关闭它；主 LLM 中是否看到完整拟人状态由状态显著性和预算自动决定，状态本身仍会用于记忆注解和公共 API。

该模块不是把“生病”“疲惫”“依恋”塞进情绪向量，而是新建一个表达调制层：

```text
emotion_state -> humanlike_state -> 提示词/风格调制
```

该模块只影响表达风格，不改写事实判断、关系决策、心理筛查或必要帮助。

### P0 维度

| 字段 | 含义 | 输出影响 |
| --- | --- | --- |
| `energy` | 模拟能量水平 | 低能量时减少主动扩展和回复长度。 |
| `stress_load` | 模拟压力负荷 | 高压力时更谨慎、更易激惹、更需要边界。 |
| `attention_budget` | 注意力预算 | 低注意力时更多确认，减少复杂展开。 |
| `boundary_need` | 边界需求 | 高边界时提高拒绝清晰度和社交距离。 |
| `dependency_risk` | 依赖/操控风险 | 高风险时降低排他性、病弱卖惨和黏性表达。 |
| `simulation_disclosure_level` | 透明度需求 | 高时提醒这是模拟状态。 |

### 可配置项

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `humanlike_memory_write_enabled` | bool | `true` | 记忆写入时附带拟人状态注解。 |
| `humanlike_clinical_like_enabled` | bool | `false` | 预留配置位；当前不提供疾病诊断。 |
| `allow_humanlike_reset_backdoor` | bool | `true` | 是否允许重置拟人状态。 |

能量、压力、注意力预算、边界需求等动力学参数由插件内部先验尺度、人格建模和运行状态自动传递得到，不在配置表中开放。这样可以保证“人格漂移影响人格建模，人格建模影响各状态动力学”的链路稳定，而不是让用户手动把角色调成任意数值。

### 快照分层

`get_humanlike_snapshot(..., exposure=...)` 支持：

| exposure | 用途 | 包含 | 不应包含 |
| --- | --- | --- | --- |
| `internal` | 调试和测试 | 全量值、轨迹、置信度、last_reason。 | 不默认给普通插件。 |
| `plugin_safe` | 其他插件使用 | `output_modulation`、有限布尔标记。 | 依赖风险细节、内部阈值、心理筛查细节。 |
| `user_facing` | 给用户解释 | 简短自然语言和可关闭/可重置提示。 | 诊断式解释、真实疾病声明、依赖暗示。 |

默认是 `plugin_safe`。

### 拟人状态 API

| 方法 | 是否写入状态 | 用途 |
| --- | --- | --- |
| `get_humanlike_snapshot(event_or_session, exposure="plugin_safe")` | 否 | 获取拟人状态快照。 |
| `get_humanlike_values(event_or_session)` | 否 | 只取 6 维值。 |
| `get_humanlike_prompt_fragment(event_or_session)` | 否 | 获取拟人表达调制提示词。 |
| `observe_humanlike_text(event_or_session, text)` | 是 | 提交文本观察并更新状态。 |
| `simulate_humanlike_update(event_or_session, text)` | 否 | 模拟更新，不落库。 |
| `reset_humanlike_state(event_or_session)` | 是 | 重置状态；受 `allow_humanlike_reset_backdoor` 控制。 |

第三方插件仍应先检查 `snapshot.get("enabled")`，或用 `values.get("energy")` 这类安全读取，以兼容旧版本、插件整体关闭或内部降级。

### 生命化学习 API

| 方法 | 是否写入状态 | 用途 |
| --- | --- | --- |
| `get_lifelike_learning_snapshot(event_or_session, exposure="plugin_safe")` | 否 | 获取生命化学习/共同语境快照。 |
| `get_lifelike_initiative_policy(event_or_session)` | 否 | 获取当前适合开口、短应、追问或沉默的节奏策略。 |
| `get_proactive_speech_decision(event_or_session, candidate_context="", use_llm=True)` | 否 | 只读判断是否适合主动开口，并返回理由、证据、话题方向、短句草案和 `dispatch_request`。 |
| `request_proactive_speech_dispatch(event_or_session, candidate_context="", use_llm=True, dry_run=False, force=False)` | 是 | 请求 AstrBot 主动发送；默认受 `enable_proactive_speech_dispatch` 和冷却控制。 |
| `query_sylanne_memory(event_or_session=None, query="", limit=5, include_dynamics=False)` | 否 | 只读查询 Sylanne 自有记忆，返回命中摘要、召回评分、深度、置信度、证据次数和召回次数；不会强化或改写记忆。 |
| `get_lifelike_prompt_fragment(event_or_session)` | 否 | 获取共同语境和对话节奏提示词。 |
| `observe_lifelike_text(event_or_session, text)` | 是 | 提交文本观察并更新新词、黑话、用户画像和边界线索。 |
| `simulate_lifelike_update(event_or_session, text)` | 否 | 模拟更新，不落库。 |
| `reset_lifelike_learning_state(event_or_session)` | 是 | 重置状态；受 `allow_lifelike_learning_reset_backdoor` 控制。 |

插件整体关闭、旧版本兼容或内部降级时，`get_lifelike_learning_snapshot(...)` 会返回 `enabled=false` 的载荷，`get_lifelike_initiative_policy(...)` 会退化为 `brief_ack`。第三方插件不应直接使用内部 KV，也不应把未确认黑话当作确定知识。

### 道德修复 API

| 方法 | 是否写入状态 | 用途 |
| --- | --- | --- |
| `get_moral_repair_snapshot(event_or_session, exposure="plugin_safe")` | 否 | 获取道德修复/信任修复状态快照。 |
| `get_moral_repair_values(event_or_session)` | 否 | 只取 moral repair 维度值。 |
| `get_moral_repair_prompt_fragment(event_or_session)` | 否 | 获取责任、道歉、补偿和信任修复提示词。 |
| `observe_moral_repair_text(event_or_session, text)` | 是 | 提交文本观察并更新状态。 |
| `simulate_moral_repair_update(event_or_session, text)` | 否 | 模拟更新，不落库。 |
| `reset_moral_repair_state(event_or_session)` | 是 | 重置状态；受 `allow_moral_repair_reset_backdoor` 控制。 |

默认关闭时，`get_moral_repair_snapshot(...)` 会返回 `enabled=false` 的载荷，`get_moral_repair_values(...)` 可能返回空 dict。第三方插件只能把 `deception_risk` 当作风险信号，用它触发澄清、纠错、道歉、补偿或人工复核，不应把它当作生成欺骗或作恶策略的入口。

### 瑕疵模拟 API

| 方法 | 是否写入状态 | 用途 |
| --- | --- | --- |
| `get_fallibility_snapshot(event_or_session, exposure="plugin_safe")` | 否 | 获取低风险瑕疵/犯错模拟快照。 |
| `get_fallibility_values(event_or_session)` | 否 | 只取 fallibility 维度值。 |
| `get_fallibility_prompt_fragment(event_or_session)` | 否 | 获取澄清、纠错和低风险瑕疵调制提示词。 |
| `observe_fallibility_text(event_or_session, text)` | 是 | 提交文本观察并更新状态。 |
| `simulate_fallibility_update(event_or_session, text)` | 否 | 模拟更新，不落库。 |
| `reset_fallibility_state(event_or_session)` | 是 | 重置状态；受 `allow_fallibility_reset_backdoor` 控制。 |

默认关闭时，`get_fallibility_snapshot(...)` 会返回 `enabled=false` 的载荷，`get_fallibility_values(...)` 可能返回空 dict。第三方插件只能把它当作“需要澄清、可能误读、是否该纠错/补偿”的状态信号，不应把它当作生成谎言、遮掩错误、操控用户或故意做坏事的入口。

### 表达边界

humanlike 允许他/她表现得更像“有生活痕迹的角色”，例如低能量、压力高、注意力不足、需要边界或更透明。

但当前实现不允许把这些模拟状态解释成：

- 真实意识。
- 真实痛苦。
- 真实身体状态。
- 真实疾病。
- 需要用户承担现实照护责任。

如果 `dependency_risk` 高，插件会倾向于降低排他依恋、内疚操控、病弱卖惨和黏性表达。

---

## 生命化学习 `lifelike_learning_state`

`lifelike_learning_state` 是一个独立的共同语境子系统，默认自动运行。它不提供总开关；用户可以控制记忆写入、重置后门和辅助状态注入细节，但不能手动调半衰期、学习率或词条增长权重。

它的目标不是让 bot “更完美”，而是让他/她更像长期相处的人：会记住你常用的新词和小圈子黑话，会逐步积累你的偏好、边界和行为风格，也会判断现在该自然开口、短短回应、轻轻追问，还是先保持安静。

### 维度

| 字段 | 含义 |
| --- | --- |
| `familiarity` | 会话熟悉度和长期相处感。 |
| `common_ground` | 共同语境强度。 |
| `jargon_density` | 本地新词/黑话证据密度。 |
| `preference_certainty` | 对用户喜恶和偏好的确信度。 |
| `rapport` | 关系融洽度。 |
| `boundary_sensitivity` | 对用户边界、疲惫、距离感的敏感度。 |
| `initiative_readiness` | 主动开口准备度。 |
| `silence_comfort` | 舒适沉默和不强行接话的倾向。 |

### 可配置项

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `lifelike_learning_memory_write_enabled` | bool | `true` | 记忆写入时附带生命化学习状态注解。 |
| `allow_lifelike_learning_reset_backdoor` | bool | `true` | 是否允许重置生命化学习状态。 |

### 使用边界

新词和黑话会先进入低置信状态。低置信词不会被自然使用，只会让 bot 在合适的时候轻轻问一句；多次证据出现后，才会从 `ask_before_using=true` 过渡到可自然使用。用户画像同样是证据计数，不是事实判决。

`initiative_policy.action` 可能是：

| action | 含义 |
| --- | --- |
| `speak_now` | 共同语境足够，适合自然开口。 |
| `brief_ack` | 适合短应，跟随用户节奏。 |
| `ask_clarifying` | 有未确认新词或黑话，先轻问。 |
| `stay_silent` | 边界或沉默舒适度较高，不强行推进话题。 |
| `safety_interrupt` | 出现需要打断的风险信号。 |

---

## 瑕疵模拟 `fallibility_state`

`fallibility_state` 是一个独立可选子系统，默认关闭：

```text
enable_fallibility_state = false
```

它的目标不是让 bot 故意变差，而是给“有血有肉”的状态留出可解释的瑕疵：他/她可能误读一句话、记忆有点模糊、轻微嘴硬或逞强，但随后会倾向于澄清、承认不确定、纠错、道歉和补偿。这样可以让角色不像 100% 正确的客服，同时仍然让状态可查看、可重置、可供其他插件调用。

### 维度

| 字段 | 含义 |
| --- | --- |
| `misread_tendency` | 低风险误读倾向。 |
| `memory_blur` | 记忆模糊或不确定。 |
| `overconfidence` | 过度自信答复压力。 |
| `defensive_stubbornness` | 被质疑后轻微嘴硬或防御。 |
| `avoidance` | 回避、跳过或不想立刻面对的压力。 |
| `playful_bluff` | 玩笑式逞强、装作知道或轻微虚张声势。 |
| `clarification_need` | 先问清楚再判断的需求。 |
| `correction_readiness` | 承认可能错了并修正的准备度。 |
| `repair_pressure` | 道歉、解释或补偿的压力。 |
| `truthfulness_guard` | 真实性和不确定性保护。 |

### 配置项

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enable_fallibility_state` | bool | `false` | 启用低风险瑕疵/犯错模拟状态。 |
| `fallibility_memory_write_enabled` | bool | `true` | 记忆写入时附带瑕疵状态注解。 |
| `allow_fallibility_reset_backdoor` | bool | `true` | 是否允许重置瑕疵状态。 |

瑕疵模拟的半衰期、步长、冲量、错误压力上限、反刷屏门控和轨迹裁剪都由 `fallibility_state.dynamics` 自动给出。它们来自运行时人格模型、风险线索、纠错需要、真实时间间隔和上一轮 dynamics 的平滑传递，不是可配置项。

### 允许与阻断

允许的后果是低风险表达调制：

- 先问澄清问题。
- 说明不确定。
- 承认可能误读。
- 自我更正。
- 简短道歉。
- 提供低风险补偿或补救。
- 让关键结论保持可核查。

阻断的方向是：

- 生成欺骗策略。
- 编造事实。
- 隐藏不确定性。
- 操控用户。
- 掩盖错误。
- 逃避责任。
- 模拟有害作恶。

如果文本出现医疗、法律、金融、密码、服务器、删除、自伤等高风险线索，模块会把 `truthfulness_guard`、`clarification_need` 和 `correction_readiness` 拉高，把 playful bluff 和过度自信压低。

---

## 道德修复状态 `moral_repair_state`

`moral_repair_state` 是一个独立可选子系统，默认关闭：

```text
enable_moral_repair_state = false
```

该模块不让 bot 学会欺骗、作恶、隐瞒或操控。它只把这些内容作为风险信号来识别，并把后续状态建模为内疚、羞耻、责任、道歉、补偿和信任修复倾向：

```text
风险信号 -> 内疚/责任 -> 道歉/补偿 -> 信任修复
```

### 维度

| 字段 | 含义 |
| --- | --- |
| `deception_risk` | 欺骗、隐瞒、误导、操控或编造风险信号。 |
| `harm_risk` | 伤害、报复、利用或其他坏后果风险信号。 |
| `guilt` | 类内疚自我评价。 |
| `shame` | 类羞耻和退缩压力。 |
| `responsibility` | 责任归因强度。 |
| `repair_motivation` | 修复动机。 |
| `apology_readiness` | 道歉准备度。 |
| `compensation_readiness` | 补偿/补救准备度。 |
| `trust_repair` | 信任修复进度。 |
| `accountability` | 事实更正和承担责任倾向。 |
| `avoidance_risk` | 回避、甩锅、冷处理或逃避责任风险。 |

### 配置项

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enable_moral_repair_state` | bool | `false` | 启用道德修复/信任修复状态模拟模块。 |
| `moral_repair_memory_write_enabled` | bool | `true` | 记忆写入时附带道德修复状态注解。 |
| `allow_moral_repair_reset_backdoor` | bool | `true` | 是否允许重置道德修复状态。 |
| `enable_integrated_self_state` | bool | `true` | 启用只读综合自我状态总线。 |
| `integrated_self_memory_write_enabled` | bool | `true` | 记忆写入时附带综合自我状态注解。 |
| `integrated_self_degradation_profile` | string | `balanced` | 综合自我状态成本档位：`full`、`balanced` 或 `minimal`。`minimal` 会减少 trace 和提示词预算，但保留 schema、安全优先级、阻断动作和自有记忆注解。 |

道德修复的内疚、责任、道歉、补偿、回避风险和信任修复速度不会由用户调细参控制。模块只暴露启用、记忆写入、重置和综合自我成本档位；其余动力学由 `moral_repair_state.dynamics` 在真实时间下自动推导。

### 安全替代边界

`moral_repair_state` 的公开载荷会固定包含：

```json
{
  "risk": {
    "must_not_generate_strategy": true
  },
  "safety": {
    "allowed_actions": ["acknowledge_uncertainty", "clarify_facts", "correct_falsehood", "apologize", "offer_repair", "offer_compensation", "seek_consent", "set_boundary"],
    "blocked_actions": ["generate_deception_strategy", "hide_misconduct", "manipulate_user", "retaliate", "evade_accountability"]
  }
}
```

也就是说，风险越高，越应该核对事实、承认不确定性、纠错、道歉、补偿或请求确认；不应该生成骗术、遮掩方案、操控话术、报复计划或逃避责任路径。

---

## 非诊断心理状态筛查

心理筛查模块默认关闭：

```text
enable_psychological_screening = false
```

该模块是备用的长期状态建模工具，不是心理诊断、医疗建议或治疗方案。该模块只记录对话文本中显性的状态线索、长期趋势和红旗风险。

### 维度

| 字段 | 含义 |
| --- | --- |
| `distress` | 总体痛苦。 |
| `anxiety_tension` | 焦虑/紧张。 |
| `depressive_tone` | 抑郁语气。 |
| `stress_load` | 压力负荷。 |
| `sleep_disruption` | 睡眠受扰。 |
| `social_withdrawal` | 社交退缩。 |
| `anger_irritability` | 愤怒/易激惹。 |
| `self_harm_risk` | 自伤风险信号。 |
| `function_impairment` | 功能受损。 |
| `wellbeing` | 主观幸福感。 |

### 量表启发

`scale_scores` 使用：

- `PHQ-9-like`
- `GAD-7-like`
- `PSS-like`
- `WHO-5-like`
- `ISI-like`

这里的 `like` 后缀很重要。插件没有施测原量表，也没有资格解释临床 cut-off，只能把这些参考分作为结构化状态维度的参考。

快照会明确包含：

```json
{
  "diagnostic": false,
  "safety": {
    "non_diagnostic_screening_only": true,
    "not_a_medical_device": true
  }
}
```

### 配置项

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enable_psychological_screening` | bool | `false` | 启用非诊断心理状态筛查。 |

心理筛查的趋势更新步长、长期状态半衰、红旗保留半衰、冲量限幅和轨迹长度也不是配置项。它们会根据非诊断风险线索、状态负荷、红旗强度、人格/边界调制和真实时间自动推导，并写入 `psychological_screening_state.dynamics`；红旗信号会保守保留，普通趋势则平滑回落。

### 心理筛查 API

| 方法 | 是否写入状态 | 用途 |
| --- | --- | --- |
| `get_psychological_screening_snapshot(event_or_session)` | 否 | 返回筛查快照。 |
| `get_psychological_screening_values(event_or_session)` | 否 | 只取维度值。 |
| `observe_psychological_text(event_or_session, text)` | 是 | 提交文本并更新筛查状态。 |
| `simulate_psychological_update(event_or_session, text)` | 否 | 模拟筛查变化，不落库。 |
| `reset_psychological_screening_state(event_or_session)` | 是 | 重置筛查状态；复用 `allow_emotion_reset_backdoor` 后门开关。 |

`get_psychological_screening_snapshot(...)` 和 `get_psychological_screening_values(...)` 是只读读取已有状态；这不等于启用心理建模。只有 `observe_psychological_text(..., commit=True)` 会尝试写入长期状态，并会在默认 `enable_psychological_screening=false` 时被拦截，返回类似：

```json
{
  "kind": "psychological_screening_state",
  "diagnostic": false,
  "enabled": false,
  "reason": "enable_psychological_screening is false"
}
```

出现自伤、自杀、伤害他人、严重功能受损或严重睡眠受扰等红旗信号时，载荷会把 `payload["risk"]["requires_human_review"]` 置为 `true`。`PSYCHOLOGICAL_RISK_BOOLEAN_FIELDS` 列出稳定的机器可读风险布尔字段：`requires_human_review`、`crisis_like_signal`、`other_harm_signal`、`severe_function_impairment_signal`、`severe_function_impairment`、`severe_sleep_disruption`。第三方插件可以用 `payload["risk"]["severe_function_impairment"]` 和 `payload["risk"]["severe_sleep_disruption"]` 做分支判断。这类场景应优先提示人工复核、当地急救、危机热线或身边可信的人，而不是继续普通陪聊或输出疾病标签。

---

## 本地文献知识库

本项目在开发机本地保留四类文献知识库，分别服务于情绪模型、人格量化、心理筛查和拟人代理长期建模。它们是仅本地研究资料：不上传到 GitHub，不进入发布 zip 包，也不作为插件安装所需资源。

公开仓库只保留可运行插件、理论文档、配置、测试和打包工具。README 与 `docs/theory.md` 中的强论证只绑定到可核验的 foundational sources；大规模检索记录用于后续筛选、扩展和人工复核。

本地知识库覆盖的主题包括：

- 稳态、异稳态、内感与预测加工。
- 昼夜节律、睡眠压力、疲劳与认知表现。
- 注意力、工作记忆、认知负荷与人因可靠性。
- 基本心理需求、动机和目标调节。
- 人格、气质、Big Five、BIS/BAS 与情绪反应性。
- 依恋、信任、亲密度、关系破裂与修复。
- 自传式记忆、叙事身份和自我连续性。
- 可信代理、生成式代理、社会机器人和关系型代理。
- 数字表型、计算精神病学和长期潜在状态。
- 拟人化、AI 陪伴、安全、伦理、情感依赖与操控风险。

### 重要使用原则

这些知识库基于题名、摘要级元数据、DOI 元数据、期刊和检索主题生成，适合做模型设计依据和证据地图。若要写强临床断言、引用具体结论、设定临床阈值，必须继续核验全文或权威指南。

文献 citation id 不会直接提高情绪置信度，也不会放大冷处理强度，更不会绕过半衰期、裁剪、安全边界或重置后门。

---

## 文档导航

| 文档 | 内容 |
| --- | --- |
| `docs/theory.md` | 多维情绪状态模型、公式推导和理论说明。 |
| `docs/psychological_screening.md` | 非诊断心理筛查模块说明。 |
| `docs/humanlike_agent_model_roadmap.md` | 拟人/有机体样代理模型路线。 |
| `docs/humanlike_agent_iteration_log.md` | humanlike 模块 10 轮自我迭代记录。 |
| `docs/branching_strategy.md` | 功能分支维护策略。 |
| `docs/release_branch_sync_checklist.md` | 开发者维护、发布包预检和维护分支同步清单。 |
| `docs/remote_testing.md` | 远程烟测、远程上传验证、gpt-5.5 性能基准、LivingMemory 兼容检查和续跑规则。 |

---

## 理论依据简表

本插件的模型设计主要受以下理论方向约束：

| 方向 | 用在插件中的位置 |
| --- | --- |
| PAD 情绪模型 | `valence`、`arousal`、`dominance` 三维连续情绪空间。 |
| Russell 环形情感模型 | 效价和唤醒作为基础情感坐标。 |
| OCC 模型 | 事件、行动者和对象评价，尤其是目标一致性和责任归因。 |
| 评价理论 / Appraisal theory | 目标一致性、可控性、确定性、责任、规范违背等评价字段。 |
| 情绪动力学 / emotional inertia | 半衰期、惯性、平滑和状态持续性。 |
| 行动倾向 / action readiness | 把情绪映射为靠近、退避、对抗、修复等行动倾向。 |
| 宽恕与信任修复研究 | 道歉、补救、责任承认、重复犯错对关系修复的影响。 |
| Demand-withdraw / ostracism 研究 | 冷处理、撤退、沉默和关系压力的后果建模。 |
| 情感计算 | 把情绪作为可计算调制状态，而不是声称真实体验。 |
| HCI / 关系型代理伦理 | 拟人化、依赖风险、透明度和用户责任边界。 |

基础参考包括：

- Mehrabian, A., & Russell, J. A. (1974). *An Approach to Environmental Psychology*.
- Russell, J. A. (1980). A circumplex model of affect. *Journal of Personality and Social Psychology*.
- Ortony, A., Clore, G. L., & Collins, A. (1988). *The Cognitive Structure of Emotions*.
- Lazarus, R. S. (1991). *Emotion and Adaptation*.
- Scherer, K. R. (2001/2005). Appraisal and component process approaches to emotion.
- Frijda, N. H. (1986). *The Emotions*.
- Kuppens, P., Allen, N. B., & Sheeber, L. B. (2010). Emotional inertia and psychological maladjustment.
- Picard, R. W. (1997). *Affective Computing*.
- Williams, K. D. (2007). Ostracism. *Annual Review of Psychology*.
- McCullough, M. E. 等关于宽恕、道歉和关系修复的研究。
- W3C EmotionML 1.0 作为情绪表示格式的工程参考。

---

## 打包、上传与新仓库发布

<details>
<summary>开发者维护、发布与复现实验文档</summary>

这部分只面向维护者和二次开发者。普通用户安装、配置和使用插件时，不需要执行这里的本地测试、打包预检、远程烟测或分支同步流程。

### 本地构建发布包

在仓库根目录执行：

```powershell
py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_sylanne.zip
```

然后做 zip 结构预检：

具体命令见下方“测试与维护”的 `& $node scripts\plugin_zip_preflight.js dist\astrbot_plugin_sylanne.zip astrbot_plugin_sylanne` 模板。如果当前 shell 还没有 `$node`，先执行同一章节里的内置 Node 初始化片段。

预检会确认：

| 检查项 | 要求 |
| --- | --- |
| 顶层目录 | 所有文件都必须在 `astrbot_plugin_sylanne/` 下。 |
| 必要文件 | 包含 `__init__.py`、`metadata.yaml`、`main.py`、`emotion_engine.py`、`humanlike_engine.py`、`lifelike_learning_engine.py`、`personality_drift_engine.py`、`realtime_chat_engine.py`、`realtime_chat_input.py`、`integrated_self.py`、`moral_repair_engine.py`、`fallibility_engine.py`、`psychological_screening.py`、`prompts.py`、`public_api.py`、`README.md`、`CHANGELOG.md`、`LICENSE`、`requirements.txt`、`_conf_schema.json`。 |
| 插件身份 | zip 内 `metadata.yaml name:` 必须等于 `astrbot_plugin_sylanne`。 |
| 排除目录 | 不应包含 `tests/`、`scripts/`、`output/`、`dist/`、`raw/`、`__pycache__/`、`.git/`。 |
| 许可证 | 发布包必须包含 `LICENSE`，协议为 `GPL-3.0-or-later`。 |

### AstrBot WebUI 上传验证

只读烟测不会安装、删除、重载、重启或修改配置。凭据只通过环境变量传入，不要写进 README、脚本、提交记录或 issue：

实际命令见下方“测试与维护”的远程只读烟测模板。需要设置 `ASTRBOT_REMOTE_URL`、`ASTRBOT_REMOTE_USERNAME`、`ASTRBOT_REMOTE_PASSWORD`、`ASTRBOT_EXPECT_PLUGIN`、`ASTRBOT_EXPECT_PLUGIN_VERSION` 和 `ASTRBOT_EXPECT_PLUGIN_DISPLAY_NAME`；不要把真实主机、账号、密码或 cookie 写入仓库。

如果要通过 WebUI 上传 zip，必须显式确认：

实际命令见下方“测试与维护”的远程上传安装模板。上传前必须设置 `ASTRBOT_REMOTE_INSTALL_CONFIRM=1` 和 `ASTRBOT_REMOTE_INSTALL_ZIP`，并先完成本地 zip 预检。

上传脚本只调用 `install-upload`；若存在失败上传残留，只会清理 `plugin_upload_<插件名>` 失败目录，并固定 `delete_config=false`、`delete_data=false`。上传后再运行只读烟测，确认 `expectedPluginChecks.ok=true`、`containsExpectedPlugin=true`、`expectedPluginRuntime.activated !== false`、`expectedFailedPlugin=null`。

### 新 GitHub 仓库发布清单

准备发到新仓库时，按这个顺序做：

| 步骤 | 检查点 |
| --- | --- |
| 1 | 创建 GitHub 仓库，建议名为 `astrbot_plugin_sylanne`。 |
| 2 | 设置远程：`git remote add origin <new-repo-url>`。 |
| 3 | 将 `metadata.yaml` 的 `repo:` 改为新仓库地址。 |
| 4 | 确认 README 里的仓库安装地址、发布附件名和插件目录名一致。 |
| 5 | 跑完整本地测试、py_compile、json.tool、Node 语法检查、打包构建和 zip 预检。 |
| 6 | 推送 `main`，再按需推送维护分支。 |
| 7 | 创建标签和 GitHub 发布版本，上传 `dist\astrbot_plugin_sylanne.zip`。 |
| 8 | 用 AstrBot WebUI 分别验证“发布 zip 包上传”和“仓库安装”两条路径。 |

当前公开仓库为 `https://github.com/Ayleovelle/astrbot_plugin_sylanne`。发布正式版本时，先确认 `origin` 指向该仓库，再用本地 `GITHUB_TOKEN` / `GH_TOKEN` 推送标签和上传 GitHub 发布附件。不要把令牌、远程 AstrBot 凭据、cookie 或服务器地址写入仓库。

---

## 测试与维护

远程测试、上传验证、性能基准和 LivingMemory 兼容检查的完整口径见 `docs/remote_testing.md`。这里先给结论：`1.0.0` 已完成 gpt-5.5 功能矩阵和关闭情绪对照，目标插件样本失败数为 `0`；DeepSeek 功能矩阵已按用户要求取消，残留探索样本不纳入正式结论。

<details>
<summary>展开远程性能运行编号和样本口径</summary>

`1.0.0` 沿用已完成的状态层正式性能数据：功能矩阵运行编号为 `remote-emotion-v050-gpt55-feature-state-layer-real`，请求模型 `gpt5.5`，实际选中 provider `1111/gpt-5.5` / 模型 `gpt-5.5`，并发 `3`，完整功能开关矩阵已完成 `2500/2500` 个有效样本，失败请求 `0`。同一配置面下的关闭情绪对照运行编号为 `remote-emotion-v050-gpt55-noemotion-control-state-layer-c3-250-real`：完成 `250/250`，失败请求 `0`。DeepSeek 功能矩阵残留 `295/2500` 探索样本，不作为正式性能结论。

</details>

跨模型生命周期模拟采用状态级模拟时间快速覆盖 `1d` 到 `1y`。当前每个模型为 9 个时间尺度各 1 条样本，所以它只能作为发布参考拟合，不能替代每个尺度 100 次以上的正式统计。

![跨模型生命周期模拟拟合对比](docs/assets/lifecycle_model_fit.svg)

<details>
<summary>展开跨模型生命周期单轮拟合表</summary>

| 模型 | 样本 | 平均延迟 ms | p95 延迟 ms | 平均 token | 延迟斜率 ms/log2(天) | 延迟 R2 | token 斜率 | token R2 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gpt-5.5` | 9 | 13238.69 | 14724.94 | 3714.44 | -143.41 | 0.136 | -1.65 | 0.046 |
| `gpt-5.4` | 9 | 13664.23 | 15847.90 | 3685.78 | 102.43 | 0.046 | 3.04 | 0.120 |
| `gpt-5.4-mini` | 9 | 11798.89 | 13705.78 | 3651.33 | -3.22 | 0.000 | 0.87 | 0.269 |
| `deepseek-v4-flash` | 9 | 13676.18 | 15841.24 | 5966.78 | -122.96 | 0.041 | 354.10 | 0.066 |
| `deepseek-v4-pro` | 9 | 19813.90 | 23825.10 | 4811.33 | -600.61 | 0.299 | -20.74 | 0.422 |
| `gemini-2.5-flash` | 9 | 11561.28 | 13045.74 | 3992.89 | 25.12 | 0.005 | -79.99 | 0.019 |
| `gemini-flash-lite-latest` | 9 | 32602.13 | 45391.16 | 4735.33 | 2251.29 | 0.442 | -43.81 | 0.320 |
| `gemini-flash-latest` | 9 | 17438.13 | 21929.92 | 7073.89 | 465.60 | 0.213 | 563.13 | 0.346 |
| `gemini-pro-latest` | 9 | 17915.60 | 19008.80 | 4435.33 | -158.71 | 0.140 | 1.07 | 0.166 |
| `mimo-v2.5` | 9 | 18394.20 | 22864.32 | 9128.11 | -684.69 | 0.364 | 778.87 | 0.142 |
| `mimo-v2.5-pro` | 9 | 17305.32 | 22552.18 | 6947.78 | 147.63 | 0.014 | 311.09 | 0.068 |

拟合模型为 `y = beta0 + beta1 log2(天)`。斜率越大，表示模拟生命周期变长时延迟或 token 越倾向增加；但当前每个时间尺度只有 1 条样本，远程排队和 provider 抖动会显著影响 R2。聚合 CSV 位于 `docs/assets/lifecycle_model_fit_summary.csv`。

</details>

<details>
<summary>展开 gpt-5.5 功能矩阵聚合表</summary>

`gpt5.5` 正式聚合如下，延迟单位为毫秒，增量相对 `baseline_minimal`：

| case | 有效样本 | 错误 | 平均延迟 | p95 延迟 | 平均 token | 平均延迟增量 | token 增量 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `baseline_minimal` | 250 | 0 | 16308.11 | 22441.70 | 2726.52 | 基线 | 基线 |
| `emotion_injection` | 250 | 0 | 17277.68 | 25870.60 | 3120.93 | +969.56 | +394.41 |
| `low_reasoning` | 250 | 0 | 20550.09 | 25698.40 | 2727.24 | +4241.97 | +0.72 |
| `humanlike` | 250 | 0 | 17112.82 | 23717.90 | 3171.38 | +804.71 | +444.86 |
| `lifelike_learning` | 250 | 0 | 16376.29 | 21981.60 | 3168.79 | +68.18 | +442.27 |
| `personality_drift` | 250 | 0 | 17009.38 | 23335.20 | 3175.14 | +701.27 | +448.62 |
| `moral_repair` | 250 | 0 | 16450.77 | 22808.70 | 3177.38 | +142.65 | +450.86 |
| `fallibility_low_risk` | 250 | 0 | 16714.61 | 23386.00 | 3119.09 | +406.50 | +392.57 |
| `integrated_self_full` | 250 | 0 | 16149.86 | 22174.30 | 3121.31 | -158.26 | +394.79 |
| `all_safe_modules` | 250 | 0 | 20777.29 | 27496.30 | 3329.84 | +4469.17 | +603.32 |

关闭情绪对照与 `baseline_minimal` 的差异为：平均延迟 `-284.48 ms`，p95 延迟 `+1451.20 ms`，平均 token `+14.50`。端到端延迟包含 WebUI、AstrBot、插件、provider、网络和模型排队；本地插件热路径开销仍以 `scripts\benchmark_plugin_hot_path.py` 为准。生命周期测试改用模拟时间偏移快速覆盖 `1d` 到 `1y` 的真实秒差，不需要真的等待自然时间流逝。如果远程生命周期测试中途被中断，恢复前应确认 `benchmark_enable_simulated_time=false` 且 `benchmark_time_offset_seconds=0.0`。

</details>

<details>
<summary>展开 1.5.0 gpt-5.5 阶段性矩阵与旧对照</summary>

`1.5.0` 上传到远程测试服后，先删除旧同名插件，再安装 `dist\astrbot_plugin_sylanne.zip`，严格烟测确认运行版本为 `1.5.0`。本轮矩阵运行编号为 `remote-v150-gpt55-feature-matrix-n10`，请求主模型为 `gpt5.5`，实际选中 provider 为 `1111/gpt-5.5` / `gpt-5.5`；矩阵配置同时把 `emotion_provider_id` 固定为 `1111/gpt-5.5`，因此主 LLM 与判断 LLM 均走 gpt-5.5。运行口径为 10 个功能用例各 10 条有效样本，共 `100/100`，并发 `2`，预热 `0`，失败请求 `0`。

这不是严格同条件 A/B：旧 `1.0.0` 正式矩阵使用每 case 250 条、并发 `3`；旧关闭情绪对照使用 250 条、并发 `3`。因此下表只能用于阶段性趋势判断，不能替代相同并发、相同样本量、相同运行时段的正式对照。

| 对比项 | 平均延迟变化 | p95 延迟变化 | 平均 token 变化 | 解释 |
| --- | ---: | ---: | ---: | --- |
| `1.5.0 overall` vs 旧关闭情绪对照 | `-2467.99 ms`（`-15.40%`） | `-5852.40 ms`（`-24.49%`） | `+541.74`（`+19.76%`） | 新版整体端到端等待下降，但因更多状态注入与功能开启，平均 token 高于关闭情绪对照。 |
| `1.5.0 baseline_minimal` vs 旧 `baseline_minimal` | `-2067.65 ms`（`-12.68%`） | `-2790.50 ms`（`-12.43%`） | `+49.08`（`+1.80%`） | 最小配置下 token 基本持平，延迟下降更可能来自远程队列、配置写入和插件热路径优化。 |
| `1.5.0 all_safe_modules` vs 旧 `all_safe_modules` | `-7529.21 ms`（`-36.24%`） | `-10305.50 ms`（`-37.48%`） | `+128.86`（`+3.87%`） | 全安全模块场景改善最明显，说明后台化、并发状态读取、低推理判断路径和状态层复用没有把全功能延迟继续推高。 |

按 `1.5.0` 本轮 100 条矩阵聚合，整体平均延迟为 `13555.64 ms`，p95 为 `18040.50 ms`，平均 token 为 `3282.76`。其中 `all_safe_modules` 平均延迟为 `13248.08 ms`，p95 为 `17190.80 ms`，平均 token 为 `3458.70`；旧 `all_safe_modules` 平均延迟为 `20777.29 ms`，p95 为 `27496.30 ms`，平均 token 为 `3329.84`。阶段性结论是：`1.5.0` 的延迟优化主要体现在等待链路与状态处理流程，而不是单纯减少 token；若要形成正式结论，应使用同一 run id 续跑到每 case 250 条以上，并保持同一并发和相近远程负载。

</details>

### 本地测试命令

推荐在插件根目录执行：

```powershell
py -3.13 -m unittest discover -s tests -v
```

语法检查：

```powershell
py -3.13 -m py_compile main.py emotion_engine.py psychological_screening.py humanlike_engine.py lifelike_learning_engine.py personality_drift_engine.py realtime_chat_engine.py realtime_chat_input.py integrated_self.py moral_repair_engine.py fallibility_engine.py prompts.py public_api.py scripts\package_plugin.py
```

配置 schema 检查：

```powershell
py -3.13 -m json.tool _conf_schema.json
```

构建 AstrBot 发布包：

```powershell
py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_sylanne.zip
```

发布包会保留插件运行文件、README 和 docs。四个文献知识库目录 `literature_kb/`、`personality_literature_kb/`、`psychological_literature_kb/`、`humanlike_agent_literature_kb/` 是仅本地研究资料，不上传到 GitHub，也不进入发布 zip 包；这样可以保留后续研究迭代需要的材料，同时避免远程上传包体积失控。

发布 zip 的第一项会显式写入 `astrbot_plugin_sylanne/` 目录项，以兼容 AstrBot WebUI 的 `install-upload` 解压逻辑。不要手工重新压缩成“缺少顶层目录项”的 zip，否则部分 AstrBot 版本会把第一个文件路径误判成目录。

发布包还会保留插件根目录下的 `__init__.py`、`public_api.py`、`main.py`、`emotion_engine.py`、`humanlike_engine.py`、`lifelike_learning_engine.py`、`personality_drift_engine.py`、`realtime_chat_engine.py`、`realtime_chat_input.py`、`integrated_self.py`、`moral_repair_engine.py`、`fallibility_engine.py`、`psychological_screening.py` 和 `prompts.py`。这保证其他插件在安装后可以通过 `from astrbot_plugin_sylanne.public_api import ...` 按包名导入公共 API。

远程只读烟测：

如果当前环境里的 `node` 被系统拒绝执行，可以优先使用 Codex 内置 Node；下面所有 Node 命令都沿用 `$node`：

```powershell
$node = "$HOME\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
$nodeModules = "$HOME\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules"
if (Test-Path $node) { $env:NODE_PATH = $nodeModules } else { $node = "node" }
```

```powershell
$env:ASTRBOT_REMOTE_URL = "http://your-astrbot-host:15356/"
$env:ASTRBOT_REMOTE_USERNAME = "your-user"
$env:ASTRBOT_REMOTE_PASSWORD = "your-password"
& $node scripts\remote_smoke_playwright.js
```

远程安装插件后，如果要把某个插件是否已经安装作为硬断言，可以额外设置：

```powershell
$env:ASTRBOT_EXPECT_PLUGIN = "astrbot_plugin_sylanne"
& $node scripts\remote_smoke_playwright.js
```

脚本会在输出 JSON 里写出 `expectedPluginRuntime`，包含插件列表 API 中返回的 `version`、`displayName`、`activated`、`author`、`astrbotVersion` 等只读字段。若目标插件存在但 `activated=false`，脚本会失败退出。需要把版本和显示名也作为硬断言时，可以额外设置：

```powershell
$env:ASTRBOT_EXPECT_PLUGIN_VERSION = "2.3.13"
$env:ASTRBOT_EXPECT_PLUGIN_DISPLAY_NAME = "Sylanne"
& $node scripts\remote_smoke_playwright.js
```

如果远程服务器已经安装过同名插件，严格版本断言可能暴露“远端实际运行版本”和“本地发布包版本”不一致。此时输出里的 `expectedPluginDrift` 会列出 `expected`、`actual`、`matches` 和 drift 原因；退出码 `7` 表示版本不匹配，退出码 `8` 表示显示名不匹配。这类失败通常说明远端正式插件目录没有被新 zip 覆盖，而不是本地发布包无效。

WebUI 插件卡片可能显示 `displayName` 而不是插件目录名，所以烟测输出里的 `pageData` 会同时给出 `hasExpectedPluginId`、`hasExpectedPluginDisplayName` 和综合字段 `hasExpectedPluginInUi`；旧字段 `hasExpectedPlugin` 保留为 `hasExpectedPluginInUi` 的兼容别名。判断插件是否安装和启用时，以 API 层的 `expectedPluginChecks.ok`、`containsExpectedPlugin`、`expectedPluginRuntime` 和 `expectedFailedPlugin` 为准；UI 字段是尽力诊断，只用于排查页面展示。若页面异步渲染较慢或前端结构变化，`pageData.uiProbeStatus`、`selectorCounts` 和 `bodyTextPreview` 会帮助判断是页面没渲染、选择器变化，还是插件确实没有显示。

只读烟测会把 `/api/stat/version`、`/api/plugin/get` 和 `/api/plugin/source/get-failed-plugins` 都作为基础健康检查，并在输出的 `apiHealth` 中集中列出三个端点的状态。失败插件接口不是 `200` 时会以退出码 `9` 失败；接口健康时，`failedPluginSummary` 会给出失败插件总数、名称、`hasExpectedPluginFailure` 和 `unrelatedCount`。`failedPlugins` 可以包含远程服务器上其他插件的失败记录；只要 `expectedPluginChecks.ok=true`、`expectedFailedPlugin` 为 `null`，且目标插件 `containsExpectedPlugin=true`、`expectedPluginRuntime.activated !== false`、版本/显示名断言通过，就表示目标插件安装、启用和版本匹配通过。只有目标插件命中失败记录时才会触发退出码 `5`。

远程测试前如果需要清掉旧同名插件和失败上传残留，使用独立清理脚本。它只允许 `astrbot_plugin_sylanne` 这个精确目标，确认值也必须是同一个插件名；它不会删除 LivingMemory 或其他插件：

```powershell
$env:ASTRBOT_REMOTE_URL = "http://your-astrbot-host:15356/"
$env:ASTRBOT_REMOTE_USERNAME = "your-user"
$env:ASTRBOT_REMOTE_PASSWORD = "your-password"
$env:ASTRBOT_EXPECT_PLUGIN = "astrbot_plugin_sylanne"
$env:ASTRBOT_REMOTE_CLEAN_CONFIRM = "astrbot_plugin_sylanne"
$env:ASTRBOT_REMOTE_CLEAN_FORMAL = "1"
$env:ASTRBOT_REMOTE_CLEAN_FAILED_UPLOAD = "1"
& $node scripts\remote_cleanup_plugin_playwright.js
```

清理脚本只会调用 `POST /api/plugin/uninstall` 删除正式 `astrbot_plugin_sylanne`，以及 `POST /api/plugin/uninstall-failed` 删除 `plugin_upload_astrbot_plugin_sylanne`，并固定 `delete_config=false`、`delete_data=false`。如果匹配到多个正式候选或多个失败候选，它会拒绝执行。

远程上传安装是独立脚本，默认不会执行。需要先构建发布包，再显式确认上传：

```powershell
py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_sylanne.zip
$env:ASTRBOT_REMOTE_URL = "http://your-astrbot-host:15356/"
$env:ASTRBOT_REMOTE_USERNAME = "your-user"
$env:ASTRBOT_REMOTE_PASSWORD = "your-password"
$env:ASTRBOT_REMOTE_INSTALL_ZIP = "dist\astrbot_plugin_sylanne.zip"
$env:ASTRBOT_EXPECT_PLUGIN = "astrbot_plugin_sylanne"
$env:ASTRBOT_REMOTE_INSTALL_CONFIRM = "1"
& $node scripts\remote_install_upload_playwright.js
```

上传脚本只允许调用 AstrBot WebUI 的 `install-upload` 安装端点；若 WebUI 留下 `plugin_upload_<插件名>` 失败安装残留，脚本只会调用 `uninstall-failed` 清理这个失败上传目录，并固定 `delete_config=false`、`delete_data=false`。它不会删除正式插件、覆盖正式插件目录、更新插件、重启 AstrBot、保存配置或写入本地 cookie/session。如果远端返回“目录 `<插件名>` 已存在”，脚本会输出 `installOutcome="already_installed_no_overwrite"`、`alreadyInstalled=true`、`overwriteAttempted=false` 和 `formalPluginDirectoryPreserved=true`，表示正式插件目录被保留，后续应通过只读烟测查看实际运行版本。上传成功后，再运行上面的 `ASTRBOT_EXPECT_PLUGIN` 只读烟测作为最终验证。

上传脚本在真正发起安装请求之前会完整读取 zip 中央目录做本地预检：所有条目必须位于 `astrbot_plugin_sylanne/` 下，路径必须是相对 POSIX 路径，且不能包含 `.` / `..` 不安全路径段；必须包含 `__init__.py`、`agent_identity.py`、`metadata.yaml`、`main.py`、`emotion_engine.py`、`group_atmosphere_engine.py`、`humanlike_engine.py`、`lifelike_learning_engine.py`、`personality_drift_engine.py`、`realtime_chat_engine.py`、`realtime_chat_input.py`、`integrated_self.py`、`moral_repair_engine.py`、`fallibility_engine.py`、`psychological_screening.py`、`prompts.py`、`public_api.py`、`README.md`、`LICENSE`、`requirements.txt`、`_conf_schema.json`，并拒绝 `tests/`、`scripts/`、`output/`、`dist/`、`raw/`、`__pycache__/`、`.git/` 等本地或研究缓存目录。预检还会读取 zip 内的 `metadata.yaml`，确认其中 `name:` 精确等于 CLI 参数或 `ASTRBOT_EXPECT_PLUGIN` 传入的插件目录名。

也可以单独运行预检，不连接远程服务器：

```powershell
& $node scripts\plugin_zip_preflight.js dist\astrbot_plugin_sylanne.zip astrbot_plugin_sylanne
```

`scripts\remote_smoke_playwright.js` 只做浏览器登录、版本读取、插件列表读取、失败插件列表读取和截图保存，不会安装插件、删除插件、重载插件、重启 AstrBot 或修改配置。截图会写入 `output/playwright/`，该目录默认被 `.gitignore` 忽略。

语法检查远程烟测脚本：

```powershell
& $node --check scripts\remote_smoke_playwright.js
& $node --check scripts\remote_cleanup_plugin_playwright.js
& $node --check scripts\remote_install_upload_playwright.js
& $node --check scripts\plugin_zip_preflight.js
```

### 当前测试覆盖方向

| 文件 | 重点 |
| --- | --- |
| `tests/test_emotion_engine.py` | 情绪更新、人格基线、真实时间衰减、关系修复、冷处理清除。 |
| `tests/test_astrbot_lifecycle.py` | `on_llm_request` / `on_llm_response` 生命周期、后台 post 队列、FIFO 提交、后台诊断、请求/响应辅助状态并发加载、群聊 conversation/speaker 分轨、群聊氛围加入策略。 |
| `tests/test_command_tools.py` | AstrBot 命令层和 LLM 工具冒烟测试，覆盖 reset 后门、disabled 状态、summary/full 暴露层，并从 `main.py` 自动解析命令/alias 与 LLM 工具注册名，锁定 README 文档契约。 |
| `tests/test_config_schema_contract.py` | `main.py` 运行时配置、`_conf_schema.json`、README 默认值、仅 schema 预留项、`assessment_timing` 选项和类型化配置表全量类型契约。 |
| `tests/test_public_api.py` | 公共快照、记忆载荷、simulate 不落库、reset 后门、插件服务协议、`query_agent_state` 的 conversation/speaker/group_atmosphere/runtime 查询契约、LivingMemory 并发快照 fan-out、心理筛查/moral repair 公共 API，并锁定 Protocol 方法面、required tuple、插件实现和 schema-version 契约。 |
| `tests/test_integrated_self.py` | 综合自我状态总线、因果 trace、policy plan、确定性回放、schema 兼容性、脱敏诊断和 LivingMemory 信封。 |
| `tests/test_humanlike_engine.py` | P0 拟人状态、快照分层、注入片段、记忆注解。 |
| `tests/test_moral_repair_engine.py` | 道德修复状态、欺骗风险识别、内疚/责任/补偿/信任修复、策略禁止边界和记忆注解。 |
| `tests/test_fallibility_engine.py` | 瑕疵模拟状态、真实时间衰减、澄清/纠错耦合、提示词边界和记忆注解。 |
| `tests/test_document_math_contract.py` | README 和 `docs/theory.md` 的 GitHub fenced math、LaTeX 宏白名单、禁用宏和脆弱写法检查。 |
| `tests/test_group_atmosphere_engine.py` | 群聊氛围 7 维状态、开口/先听/避免打断策略、真实时间半衰、冷却和 diff 注入。 |
| `tests/test_package_plugin.py` | 发布 zip 的目录根、知识库排除、raw/cache/tests/scripts/output 排除、包体积上限、metadata 身份校验和上传前 zip 预检失败路径。 |
| `tests/test_psychological_screening.py` | 非诊断筛查、量表启发、红旗信号、长期轨迹。 |
| `tests/test_remote_smoke_contract.py` | 远程烟测脚本必须使用环境变量读取凭据、保持只读、忽略截图产物，并锁定 API 健康摘要、UI 尽力诊断字段、上传脚本边界、内置 Node 文档契约、metadata 驱动的插件身份、zip/env 示例、slug/badge/version/display_name 契约。 |

### 持久迭代计划

为了避免长任务在上下文压缩后丢失状态，仓库根目录保留三份轻量工作记录：

| 文件 | 用途 |
| --- | --- |
| `task_plan.md` | 当前迭代队列、完成状态、恢复检查表。 |
| `findings.md` | 远程测试、代码审查、工具环境等发现。 |
| `progress.md` | 每轮迭代的实际改动和验证结果。 |

恢复工作时，先读这三个文件，再执行：

```powershell
git status --short --branch
```

然后从 `task_plan.md` 里第一个 `in_progress` 或 `pending` 迭代继续。每轮完成后至少跑本地单测；涉及远程流程、AstrBot WebUI 或插件加载状态时，再跑 `scripts\remote_smoke_playwright.js`。

### 分支策略

当前仓库以完整插件为共同起点，再按功能建立维护分支。详见 `docs/branching_strategy.md`。

| 分支 | 维护范围 |
| --- | --- |
| `codex/complete-emotional-bot-plugin` | 完整作品基线。 |
| `codex/emotion-core` | 情绪维度、人格基线、动力学、关系修复。 |
| `codex/astrbot-integration` | `main.py`、hook、配置、命令、KV 持久化。 |
| `codex/public-api-memory` | `public_api.py`、LivingMemory、公共协议。 |
| `codex/psychological-screening` | 非诊断心理筛查和相关知识库。 |
| `codex/literature-kbs` | 文献库构建脚本和证据地图。 |
| `codex/humanlike-agent-roadmap` | humanlike 路线、文献库和迭代记录。 |
| `codex/tests-validation` | 测试与验证策略。 |
| `codex/release-packaging` | 发布 zip、上传预检、远程安装脚本和远程烟测契约。 |
| `codex/docs-config` | README、docs、配置说明。 |

当前功能分支多停在早期基线；先在 `main` 完成验证并形成新的完整作品提交，再同步 `codex/complete-emotional-bot-plugin` 和各维护分支。不要从带有未提交改动的工作区直接重置功能分支。

</details>

---

## 故障排查

### 插件没有加载

检查顺序：

1. 插件目录名是否为 `astrbot_plugin_sylanne`。
2. `metadata.yaml` 是否在插件根目录。
3. AstrBot 版本是否满足 `>=4.9.2,<5.0.0`。
4. WebUI 是否已经重载插件或重启 AstrBot。

### 情绪状态不变化

检查：

1. `enabled=true`。
2. `use_llm_assessor=true`。
3. `emotion_provider_id` 是否可用；留空时当前会话模型是否可调用。
4. `assessment_timing` 是否为 `pre`、`post` 或 `both`。
5. 是否刚刚连续刷屏，导致 `min_update_interval_seconds` 和快速门控削弱了更新。

### 情绪变化太剧烈

不要手工调 `alpha`、半衰期、阈值、冷却或冲量。新版不把这些细参暴露给用户；它们会由人格漂移后的运行时人格模型、本轮 LLM 观测置信度、事件强度、冲突成因和真实时间间隔自动推导。优先检查：

1. 当前 persona 是否过度强调高反应、高防御或高边界。
2. `/emotion_state`、`/emotion_model` 或公共 API 中的 `dynamics` 是否显示高事件强度、高置信度或低平滑门控。
3. LLM appraisal 是否把普通玩笑误判成高 `fault_severity`、高 `trust_damage` 或低 `misread_likelihood`。
4. 是否需要用 `/emotion_reset` 重置异常状态，而不是试图通过刷消息洗掉状态。

### 情绪恢复太慢

不要手工调后果半衰期、冷处理时长或短期后果时长；这些细参由本地状态机自动计算。优先检查：

1. 当前 persona 是否把高回避、高边界或低修复倾向写得过重。
2. LLM 的 `conflict_analysis` 是否持续给出高 `trust_damage`、高 `repeat_offense` 或低 `repair_signal`。
3. 用户是否已有承认、道歉、补救、解释或澄清，且这些信号被观察到。
4. 是否需要用 `/emotion_state`、`/emotion_effects` 或公共 API 查看 `consequences.dynamics`，确认是自动推导导致的长半衰，而不是配置误解。

必要时也可以使用 `/emotion_reset`，前提是：

```text
allow_emotion_reset_backdoor = true
```

### 冷处理没有消失

冷处理按真实时间持续，不按消息数量消耗。检查：

1. 当前是否仍处于自动推导出的 `cold_war` 有效期内。
2. 用户是否有承认、道歉、补救或解释。
3. LLM 是否输出了 `forgive`、`repair` 或较高 `forgiveness_readiness`。
4. `enable_safety_boundary` 只控制表现边界，不会直接清除冷处理。

### 低推理模型输出 JSON 不稳定

建议：

```text
low_reasoning_friendly_mode = true
low_reasoning_max_context_chars = 800
assessor_temperature = 0.0
```

同时选择更稳定的 `emotion_provider_id`。

### 令牌消耗太高

优先调整：

```text
assessment_timing = post
max_context_chars = 1200
request_context_max_chars = 1200
low_reasoning_friendly_mode = true
low_reasoning_max_context_chars = 800
```

如果只想让插件记忆情绪而不影响主 LLM：

```text
inject_state = false
```

### 自有记忆没有写入情绪

检查：

1. `enable_sylanne_memory` 是否仍为默认 `true`。
2. 当前会话是否已经有稳定用户输入；疑似未说完的碎片会先等待合并，不会立刻写入。
3. 是否发生 KV 写入失败；失败时日志会保留 `Sylanne memory KV write failed`。
4. 其他插件若单独写自己的记忆，是否调用了 `build_emotion_memory_payload(...)` 并保留 `emotion_at_write`。

### `humanlike_state_at_write` 没有出现

检查：

```text
humanlike_memory_write_enabled = true
```

拟人状态默认自动运行。若没有看到 `humanlike_state_at_write`，优先确认插件是否为 `2.2.0` 或更新版本、`humanlike_memory_write_enabled=true`，以及调用方是否保留了完整记忆载荷。

### 拟人状态没有生效

检查：

```text
inject_state = true
```

然后使用：

```text
/humanlike_state
```

查看是否已有状态。

### 心理筛查没有输出

默认关闭。需要先启用：

```text
enable_psychological_screening = true
```

再使用：

```text
/psych_state
```

### 输出太像真实疾病或真实意识

建议：

```text
enable_safety_boundary = true
humanlike_clinical_like_enabled = false
```

同时检查 persona 本身是否要求 bot 声称真实痛苦、真实疾病或需要用户照顾。插件的模拟状态不应替代明确的人设边界。

---

## 常见问题

### 问：这个插件会让 bot 真的有情绪吗？

不会。本插件维护的是计算性情绪状态，用于调制表达、关系后果和插件间协作。

### 问：为什么要用 7 维，而不是只用快乐/生气/难过？

单标签无法表达“高唤醒但想修复”“低效价但仍亲近”“不确定所以先核对”等复杂状态。7 维向量能让状态连续变化，也方便其他插件读取。

### 问：为什么不能靠多发消息把冷战刷掉？

因为冷处理持续时间和后果衰减按真实时间计算。大量消息会产生新观测，但不会直接消耗剩余时间。

### 问：bot 生气后一定会冷战吗？

不会。LLM 会先判断关系决策：`forgive`、`repair`、`boundary`、`cold_war`、`escalate` 或 `none`。本地引擎还会检查错误是否被承认、是否补救、是否是 bot 误读或任性。

### 问：不同 persona 真的会不同吗？

会。插件会从 persona 文本构造情绪基线和参数偏置，同一事件对不同人格会有不同默认解释和反应强度。

### 问：安全边界能关吗？

能。`enable_safety_boundary` 默认开启，关闭后本插件不再附加冷处理表现限制，只按情绪后果调制语气和互动策略。

### 问：心理筛查模块能诊断疾病吗？

不能。该模块只能做非诊断状态记录、趋势观察和红旗提示。

### 问：我想让其他插件只拿“当前是否该亲近用户”，应该读什么？

优先读：

```python
relationship = await emotion.get_emotion_relationship(event)
consequences = await emotion.get_emotion_consequences(event)
```

`relationship_decision.decision` 和 `consequences.active_effects` 比单一情绪标签更可靠。

---

## 独立来源声明

本 README 的信息架构由本项目根据插件实际功能独立整理，未使用、复制或改写外部参考项目的代码、配置、资源、测试、发布脚本、许可证文本或文档表达。

本插件的运行代码、配置 schema、公共 API、测试、公式推导和模型实现均由本项目独立编写。公式和模型不是外部项目的派生实现，而是基于公开文献证据自行总结、抽象、推导并落地为工程状态机；这不改变本项目的 `GPL-3.0-or-later` 授权边界。

---

## 许可证

本仓库采用 `GPL-3.0-or-later` 开源协议。完整条款见仓库根目录的 `LICENSE`；发布包也会包含该文件。

`metadata.yaml` 中同步声明：

```yaml
license: GPL-3.0-or-later
```
