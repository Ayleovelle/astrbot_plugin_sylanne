# 更新日志

本文件用于 AstrBot 插件市场/管理页展示更新内容。更完整的设计说明、公式推导、测试矩阵和维护手册见 `README.md`。

## 1.8.4

发布日期：2026-05-11

### 修复

- 修复用户连续分段输入时，bot 可能抢答前半句、导致主 LLM 误读上下文的问题；疑似未说完的短碎片会先等待合并，最多等待 20 秒后放行。
- 情绪评估会等到合并后的用户意图再执行，避免“我！/就！/是！”这类碎片分别污染情绪轨迹。
- 用户纠正上一轮误会或追问来源时，会注入纠正上下文并抑制上一轮 assistant 历史影子，避免旧误会继续压过当前澄清。
- bot 回复被用户插话打断时，会记录为中性打断事件，包含已发/未发摘要；正向还是负面由后续情绪判断模型结合人格、关系和语境自行判断，不在代码里硬编码。

### 验证

- `python -m pytest -q tests/test_realtime_chat_input.py tests/test_astrbot_lifecycle.py`：121 项通过，5 个 subtests 通过。

## 1.8.3

发布日期：2026-05-11

### 修复

- 修复 `1.8.2` 中只依赖 `stop_event()` 阻断默认发送仍可能导致整段主回复先发、随后插件又分条发送的重复发送问题。
- 实时分条接管时，插件会把完整主回复保存到内部 `_sylanne_intercepted_completion_text`，用于分条发送、post 情绪评估、历史影子和下一轮上下文；同时清空 `response.completion_text`，让 AstrBot 默认发送口不再发送整段原文。
- 过期回复、乱序旧回复和用户插话打断也会走同一套双缓冲逻辑：内部保留原文，默认发送口清空。
- 重做即时聊天输入侧：同一用户短时间连续发送的短字、表情和疑问收束词会聚合成一轮用户意图，避免主 LLM 只理解最后一条。
- 低信号跟进（如单独 `?`、表情、短应答）不会立即消费一次性 assistant 历史影子，真正有内容的后续追问仍能拿到上一轮上下文。
- 主动聊天调度器改用近期上下文窗口摘要；若检测到 LivingMemory 的只读检索接口，会追加限长记忆摘要，失败时静默降级。

### 验证

- 新增/更新回归测试，确认接管后 `response.completion_text` 为空，但内部保留原文。
- 新增输入碎片聚合、低信号不消费上下文、主动聊天近期窗口和 LivingMemory 召回摘要回归测试。
- `python -m pytest -q tests/test_astrbot_lifecycle.py`：101 项通过，5 个 subtests 通过。
- `python -m py_compile main.py tests/test_astrbot_lifecycle.py realtime_chat_engine.py` 通过。

## 1.8.2

发布日期：2026-05-11

### 修复

- 修复即时聊天分条接管主回复时可能触发 AstrBot “消息为空，跳过发送阶段”的问题：主回复文本会在插件内部保留为上下文，插件尝试通过 `stop_event()` 阻断默认发送并接管分条发送。
- 修复用户在分条发送前或发送中插话后，下一轮 LLM 可能不知道上一轮话还没说完的问题；已发送短句和未发送摘要会作为短上下文注入下一轮请求。
- 修复过期回复、乱序回复和撤回打断时的旧回复处理：旧回复不再被清空，而是记录为低 token 的对话断点。
- 强制二次拆分过长分条，避免 LLM 计划里出现“看似分段、实际长篇”的破碎长消息。
- 未知平台或 WebUI/dashboard 流式响应不再被插件重放，避免浏览器端重复发送。

### 文档

- README 顶部吉祥物说明移动到图片下方，减少 GitHub/手机端排版错位。

### 验证

- `python -m pytest -q tests/test_astrbot_lifecycle.py`：101 项通过，5 个 subtests 通过。
- `python -m pytest -q tests/test_package_plugin.py tests/test_remote_smoke_contract.py`：38 项通过，379 个 subtests 通过。
- `python -m py_compile main.py tests/test_astrbot_lifecycle.py realtime_chat_engine.py` 通过。
- `node scripts/plugin_zip_preflight.js dist/astrbot_plugin_sylanne.zip astrbot_plugin_sylanne` 通过。
- 远程短烟测通过：AstrBot `4.24.2`，`Sylanne 1.8.2` 激活，失败插件为空，LivingMemory 未被删除。

## 1.8.1

发布日期：2026-05-11

### 修复

- 修复即时聊天分条发送后，`completion_text` 被接管导致上一轮 assistant 回复可能没有进入 AstrBot 普通 LLM 历史，从而在用户继续追问“他们、刚才、那个”等指代时发生上下文丢失的问题。
- 分条发送完成后会保留一次性 assistant 历史影子；用户在分条发送中途插话时，会把已发送短句作为活跃派发摘要临时注入下一轮请求。
- 相关摘要注入后立即消费，避免 token 持续膨胀。

### 验证

- `python -m pytest -q tests/test_astrbot_lifecycle.py`：95 项通过，5 个 subtests 通过。
- `python -m json.tool _conf_schema.json` 通过。
- `python -m py_compile main.py tests/test_astrbot_lifecycle.py` 通过。

## 1.8.0

发布日期：2026-05-11

### 新增

- 即时聊天新增用户说话节奏学习：生命化学习会记录平均句长、换行密度、标点停顿、短句倾向、长段倾向和碎片化程度。
- 分条策略会读取 `lifelike_learning_state.user_profile.speaking_style`，自动决定更短碎还是更完整的消息节奏。

### 优化

- 长回复不再为了满足 `max_parts` 偏好而把尾部静默截成 `...`；过长内容会继续拆成更多安全长度的消息。
- 用户插话后的旧回复只写入低 token 断点摘要，下一轮不会把旧长文全文塞回提示词。
- `get_realtime_chat_plan(...)` 只暴露派生后的 `user_style_adaptation` 数值，不暴露用户画像原文。

### 验证

- 新增用户说话风格学习、分条自适应、长回复不省略、插话断点低 token 注入相关测试。
- `python -m py_compile main.py realtime_chat_engine.py lifelike_learning_engine.py` 通过。
- `python -m pytest tests/test_astrbot_lifecycle.py -q`：92 项通过，5 个 subtests 通过。

## 1.7.1

发布日期：2026-05-11

### 修复

- 修正 `block_deception_manipulation_evasion_actions` 的默认契约：配置 schema、运行时 fallback、README 和测试现在统一为默认开启阻断。
- 默认情况下，道德修复、瑕疵模拟、综合自我和阴影诊断会输出 `blocked_actions`、`not_allowed`、`refuse` 等插件层硬阻断信号。
- 显式设置 `block_deception_manipulation_evasion_actions=false` 时，仍保留只观察风险、透明修复和不额外阻断的维护路径。

### 验证

- 更新 schema 默认值、命令层阴影诊断、公共 API 和提示词片段相关测试。

## 1.7.0

发布日期：2026-05-11

### 新增

- 新增后台主动聊天调度器 `enable_proactive_speech_scheduler`：可登记最近可触达会话，并在低频后台调度中由状态公式和 LLM 判断是否应该请求 AstrBot 主动发送消息。
- 新增用户插话中断机制：每个会话维护 `input_epoch`，旧 LLM 回复过期后不再发送，也不进入回复后情绪评估。
- 新增分条发送中途过期检查：即时聊天拆分后的每条消息发送前都会检查用户是否已经插话。
- 新增 NapCat/OneBot 撤回接入：公共 API `observe_user_message_withdrawal(...)` 可解析 `friend_recall` / `group_recall` notice，并让旧输出自然过期。

### 优化

- 主动聊天不使用固定话题库；话题、理由和开口方式由情绪、群聊氛围、双方需要、上下文证据和 LLM 裁决共同决定。
- 主动聊天默认仍不发送，必须同时开启调度器和发送执行开关，便于配置者分阶段验证。
- README 增补主动聊天闭环、用户插话、撤回处理和版本号规则说明。

### 验证

- 新增主动聊天调度、epoch 打断、分条发送中断、NapCat 撤回解析和公共 API 契约测试。
- 发布包继续排除本地知识库、输出目录、测试目录、脚本目录和外部表情包素材库。

## 1.6.0

发布日期：2026-05-10

### 新增

- 动态后台 worker 新增 CPU/内存环境压力守卫，高压时自动降档，环境压力未知时进入保守档。
- 新增全局后台 worker 预算：全插件同时活跃后台任务硬上限固定为 6，避免多会话积压叠加撑爆服务器。
- 新增 worker 平滑扩容状态：队列暴涨时通过冷却时间逐级升档，每轮最多升 1 档。
- runtime 诊断新增环境压力等级、CPU/内存比例、资源 cap、全局活跃 worker、可领取槽位和扩容冷却字段。

### 优化

- 只读 runtime 诊断不再推进 worker 扩容状态，只有真正领取后台任务时才提交档位变化。
- 动态 worker 文档、配置说明和手机端静态流程图同步展示环境守卫、全局预算和平滑扩容。
- 重新打包发布包，继续排除知识库、输出目录、测试目录、脚本目录和外部表情包素材库。

### 验证

- 新增环境压力降档、未知压力保守档、全局 worker 预算、平滑扩容和只读诊断不提交状态的单元测试。
- `py -3.13 -m unittest tests.test_package_plugin tests.test_config_schema_contract tests.test_astrbot_lifecycle tests.test_command_tools tests.test_public_api -v`：236 项通过。
- `dist/astrbot_plugin_sylanne.zip` 包含运行时必要文件，不包含本地知识库和输出目录。

## 1.5.0

发布日期：2026-05-10

### 新增

- 新增真人即时聊天表达层：回复可拆成多条短消息，并按模拟打字速度顺序发送。
- 新增 `get_realtime_chat_plan(...)`、`request_realtime_chat_dispatch(...)` 和 `observe_sticker_usage(...)` 公共 API。
- 新增默认回复接管：`on_llm_response` 可在 AstrBot 支持响应改写时接管默认回复，再用 `context.send_message(...)` 发送分条消息；已发送分条会保留一次性 assistant 历史影子，避免下一轮代词指代断裂。
- 新增表情包氛围回应：根据情绪、群聊氛围和文本线索选择本地表情包候选。
- 新增用户表情学习：只记录 URL、路径、file_id、标签和兴趣分等轻量元数据，不保存图片二进制。

### 优化

- 主动发言发送可自动接入即时聊天计划，让关心、想念、调皮打扰等主动消息也能分条发送。
- 请求阶段可注入短风格提示，降低长篇报告腔和 Markdown 清单腔。
- 发布边界继续排除知识库、测试目录、脚本目录、输出缓存和外部表情包素材库。

### 验证

- 新增即时聊天分条、dry-run、顺序发送、响应接管和表情元数据学习测试。
- 发布包新增 `realtime_chat_engine.py`，并继续通过 zip 根目录和必要文件契约检查。

## 1.2.0

发布日期：2026-05-10

### 新增

- 新增主动发言发送执行层：`request_proactive_speech_dispatch(...)` 可在配置允许、同会话冷却通过、会话目标明确时调用 AstrBot `context.send_message(...)` 请求主动发送。
- `get_proactive_speech_decision(...)` 保持只读裁决，同时返回 `dispatch_request`，方便调度器、群聊插件或第三方插件审计后决定是否发送。
- 新增 LLM 工具 `request_bot_proactive_speech_dispatch`，默认 `dry_run=true`，先返回理由、话题证据、短句草案、发送结果和阻断诊断。
- 新增主动发言配置：`enable_proactive_speech_dispatch`、`proactive_speech_dispatch_cooldown_seconds`、`proactive_speech_dispatch_ttl_seconds`、`proactive_speech_max_chars`。
- 主动话题新增进度关心、想念、调皮打扰、轻量整蛊和修复等模式；每次主动开口都需要带 `topic_evidence`。

### 优化

- 更新工作流图，补充“裁决、生成 dispatch_request、冷却检查、发送执行、审计写入”支路。
- 真正发送主动消息后，会把当次主动话语写入生命化学习轨迹，避免主动行为脱离长期情绪和共同语境。
- README 和远程烟测文档同步到 `1.2.0`。

### 验证

- `py -3.13 -m unittest discover -s tests -v`：391 项通过。
- Python 编译、配置 JSON、SVG XML、zip 打包和插件包预检均通过。
- 发布包不包含本地知识库、测试目录、脚本目录、原始输出或缓存目录。

## 1.1.0

### 新增与优化

- 后台 post 评估进入队列，支持同一会话 FIFO 提交、检查点、租约、重试和失败任务留存。
- 状态读取并发化，覆盖请求、响应和 LivingMemory 写入阶段。
- 智能后台 worker 支持按队列压力扩缩，最大 6 个，总体仍保持有序提交。
- 群聊分层建模同时维护房间级轨道和说话人级轨道。
- `assessor_timeout_seconds` 默认取消硬超时，避免慢推理模型被误伤。

## 1.0.0

### 首个正式基线

- 建立多维情绪状态、人格建模、真实时间半衰期、情绪后果、生命化学习、人格漂移、拟人状态、道德修复、瑕疵模拟、群聊氛围和非诊断心理筛查的主线架构。
- 提供公共 API，允许其他插件读取、模拟、提交、重置状态。
- LivingMemory 写入时可冻结当时的情绪、拟人、生命化学习、道德修复、瑕疵和综合自我状态。
- 发布 GPL-3.0-or-later 开源版本。
