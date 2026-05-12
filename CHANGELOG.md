# 更新日志

本文件用于 AstrBot 插件市场/管理页展示更新内容。更完整的设计说明、公式推导、测试矩阵和维护手册见 `README.md`。

## 2.3.1

发布日期：2026-05-12

### 修复

- 修复用户把一句话拆成多条慢速碎片发送时，主 LLM 可能提前逐条回复的问题。现在疑似碎片即使已经触发本地放行，也会先经过输入完整度 LLM gate；判断为未完成时继续合并，不把半句话交给主回复。
- 修复“我！/不！/是！/老！/年/人！！！”这类带强调和语义悬念的分段会被感叹号误判为完整句的问题。
- 修复 LLM gate 判断不可用时的立即放行风险：多片段窗口会保守等待到语义窗口稳定后再释放，避免本地规则误抢答。
- 修复 gate 判定未完成但用户停止输入时可能长期沉默的问题：达到 `realtime_input_completion_max_wait_seconds` 后会释放合并后的碎片意图。
- 修复 Gemini/OpenAI 兼容模型在工具调用阶段更容易出现空输出的问题：Gemini 请求统一进入 Agent-owned context；若本轮带工具定义、工具选择或工具结果，只追加一条极短可见输出/tool_calls 兼容提示，其他状态、记忆和即时聊天风格提示全部跳过。

### 验证

- `python -m pytest -q tests/test_astrbot_lifecycle.py -k "realtime_input"`
- `python -m pytest -q tests/test_astrbot_lifecycle.py -k "gemini or tool_call_response or tool_request or tool_result"`
- `python -m pytest -q tests/test_realtime_chat_input.py tests/test_astrbot_lifecycle.py tests/test_command_tools.py -k "realtime_input or realtime_chat or memory_settings"`
- `python -m pytest -q tests/test_public_api.py -k "on_llm_request or realtime or public_service_versions"`
- `python -m pytest -q tests`
- `python -m py_compile main.py realtime_chat_input.py`

## 2.3.0

发布日期：2026-05-12

### 新增

- 新增插件详情页『记忆设置』Page，可直接下拉选择 AstrBot 当前可用的 Embedding 类型模型提供商，不再要求用户手写 provider ID。
- Page 后端新增 `/{plugin}/memory-settings` GET/POST 接口，只保存 `sylanne_memory_embedding_provider_id`，旧配置、手填 ID 和留空自动选择保持兼容。

### 打包

- 发布包纳入 `pages/memory-settings/` 静态资源，并把 `memory_engine.py` 与记忆设置 Page 文件加入 zip 预检硬约束，避免包体遗漏核心记忆模块或页面入口。

### 验证

- `python -m pytest -q tests/test_command_tools.py -k "init_registers_memory_settings_page_apis or memory_settings_page_lists"`
- `python -m pytest -q tests/test_package_plugin.py -k "package_file_selection_excludes_local_artifacts or package_zip_has_astrbot_plugin_root"`

## 2.2.0

发布日期：2026-05-12

### 新增

- Sylanne 自有记忆加入可选向量检索。配置 `sylanne_memory_embedding_provider_id` 后会调用 AstrBot 中对应的 Embedding 类型模型提供商；留空时尝试使用第一个可用 Embedding 提供商。
- 记忆记录新增 `semantic_embedding`、`embedding_provider_id`、`embedding_updated_at` 和 `embedding_text_hash`，召回时融合关键词相似度、Embedding 余弦相似度、记忆深度、置信度、真实时间新鲜度和干扰强度。
- 向量生成失败、provider 不存在、维度不一致或未配置 Embedding 时自动回退原有关键词 + 关联图检索，不阻断普通聊天。

### 文档

- README 增加向量记忆配置说明，工作流 SVG 增加“Embedding 向量 + 关键词 + 关联图”链路。
- `docs/theory.md` 补充向量召回公式，说明稀疏相似度与密集语义相似度的保守融合，并加入 Sentence-BERT 与大规模相似度检索参考文献。

### 验证

- `python -m pytest -q tests/test_memory_engine.py -k "embedding or vector"`
- `python -m pytest -q tests/test_astrbot_lifecycle.py -k "configured_embedding_provider"`
- `python -m pytest -q tests/test_config_schema_contract.py`

## 2.1.3

发布日期：2026-05-12

### 修复

- 修复即时聊天接管可能拦截 AstrBot Agent 工具调用中间响应的问题。带 `tool_calls`、`function_call`、工具角色或工具调用 ID 的 LLMResponse 会完全放行，不改写 `completion_text`，不阻断事件传播，也不消费会话 epoch。
- 修复主动发言频率过高的问题。新增真实时间安静门，刚聊完的同一会话不会立刻被主动打扰；未回复、冷回复和反馈压力会继续拉长冷却。

### 文档

- 更新工作流 SVG：明确上下文和工具调用归 AstrBot Agent，Sylanne 只接管最终自然语言投递、短状态事实、自有记忆召回和后台顺序提交。
- README 增加暂时放弃 LivingMemory 运行时兼容的原因说明：LivingMemory 本身很好，但当前即时聊天接管、分条投递、插话断点和 Agent-owned context 的生命周期边界存在冲突，因此先使用 Sylanne 自有记忆模块。

### 验证

- `python -m pytest -q tests`
- `python -m py_compile main.py lifelike_learning_engine.py realtime_chat_input.py realtime_chat_engine.py public_api.py tests\test_astrbot_lifecycle.py tests\test_public_api.py`
- `node scripts\plugin_zip_preflight.js dist\astrbot_plugin_sylanne.zip astrbot_plugin_sylanne`

## 2.1.2

发布日期：2026-05-12

### 修复

- 修复即时聊天被用户插话后，主 LLM 可能误以为上一段回复已经完整说完的问题。现在主回复会留在 AstrBot Agent 历史里，并附带投递状态信封，说明“已生成但由 Sylanne 分条接管，不等于已经全部送达用户”。
- 修复用户插话断点信息过弱的问题。断点会记录已发条数、未发条数、已发摘要和未发开头，下一轮可知道自己话说到哪里。
- 修复 Gemini/OpenAI 兼容高风险模型下额外状态注入过多的问题。高风险模型会进入 `gemini_agent_owned_context` 模式，把上下文交给 Agent，跳过 Sylanne 临时 prompt 注入。
- 修复主动聊天过于频繁、话题结束后仍硬问进度的问题。`progress_check` 必须有近期任务、期限、未完成事项或用户要求跟进等明确证据；无证据时会沉默或降级为低压力调皮打扰。

### 文档

- README 顶部介绍移除吉祥物素材工程说明，改为说明 Agent-owned context 与即时聊天投递状态。

### 验证

- `python -m pytest -q tests/test_astrbot_lifecycle.py -k "agent_owned_context_for_gemini or intercepts_completion_and_schedules_realtime_send or preserves_result_chain_images or intercepts_even_when_realtime_send_cooldown_is_active or realtime_intercept_preserves_assistant_context or realtime_intercept_skips_shadow or realtime_chat_plan_stops_remaining_parts"`
- `python -m pytest -q tests/test_lifelike_learning_engine.py -k "proactive"`
- `python -m pytest -q tests/test_public_api.py -k "proactive_progress_check_without_evidence or proactive_dispatch_policy_extends_cooldown or proactive_speech_decision_uses_llm"`

## 2.1.1

发布日期：2026-05-12

### 修复

- 修复即时聊天接管主回复时，AstrBot 核心日志只显示空 `Prepare to send`、不方便确认插件是否已经接管和分条发送的问题。
- 新增即时聊天接管链路的 `INFO` 级中文日志：接管主回复、准备分条发送、逐条发送、媒体/表情发送、完成发送或被用户插话打断都会留下可读记录。
- 保持默认发送口阻断逻辑不变，避免整段主回复和分条消息重复发送。

### 验证

- `python -m pytest -q tests/test_astrbot_lifecycle.py -k "visible_realtime_logs or realtime_chat or realtime_intercept"`
- `python -m py_compile main.py tests\test_astrbot_lifecycle.py`
- `git diff --check`

## 2.1.0

发布日期：2026-05-12

### 新增

- 新增只读记忆查询命令：`/sylanne_memory`、`/记忆查询`、`/查询记忆`、`/灵澜记忆`，用于查看当前会话命中的记忆摘要、召回分数、记忆深度、置信度、证据次数和召回次数。
- 新增公共 API：`query_sylanne_memory(...)`，其他插件可只读检查 Sylanne 自有记忆；查询不会强化记忆，也不会改写 `recall_count`、深度或置信度。

### 修复

- 修复即时聊天分段接管后 Agent 原生历史可能缺失的问题，避免用户追问、纠正或插话时上下文被旧影子覆盖。
- 修复短答场景的锚定问题：例如用户只回复 `IP` 时，会更稳地绑定上一轮 bot 未闭合的选择问题。
- 增加 Gemini/OpenAI 兼容保护：当模型出现“有推理 token 但可见输出为空”的高风险行为时，插件会尽量降低额外注入负担并追加可见输出约束。

### 文档

- README 增补记忆查询命令、公共 API 表格、远程烟测版本号和当前版本说明。
- 记录发包规则：以后涉及代码变动的上传都需要同步发布插件 zip 包体。

### 验证

- `python -m pytest -q tests/test_command_tools.py -k "readme_documents_registered_commands or sylanne_memory_query"`
- `python -m pytest -q tests/test_public_api.py -k "public_service_contract or get_emotion_service_returns or query_sylanne_memory"`
- `python -m pytest -q tests/test_package_plugin.py tests/test_config_schema_contract.py -k "package or zip_preflight or schema"`
- `python -m py_compile main.py public_api.py memory_engine.py realtime_chat_input.py realtime_chat_engine.py scripts\package_plugin.py`
- `git diff --check`

## 2.0.0

发布日期：2026-05-12

### 新增

- 将 Sylanne 自有长期记忆升级为轻量本地知识库层：每条记忆拥有稳定 `memory_id`、摘要、情绪签名、关系签名、深度、置信度、证据次数、召回次数和自动动力学参数。
- 新增记忆关联图：写入时为同会话近邻记忆建立少量关联边；召回核心记忆时，可在硬预算内自动联想少量相邻记忆，帮助理解长期指代和共同经历。
- 新增真实时间召回强化与遗忘剪枝：真正注入 prompt 的记忆会提高深度和置信度；长期无证据、无召回且强度很低的弱记忆会按半衰期剪枝，并清理悬空关联边。

### 修复

- 修复“是为了 / 让你更好地去 / 记住呀”这类目的从句分段时，bot 可能在中途抢答或迟迟不合并的问题。
- 保持 `use_llm_assessor` 判断用户已经说完时立即放行，不再继续等待最大 20 秒输入窗口。

### 文档

- 在 `docs/theory.md` 补充自有记忆知识库、关联召回、检索强化和遗忘公式推导，并加入 Ebbinghaus、Tulving、ACT-R、Bjork、Schacter、Generative Agents 与检索系统相关参考文献。
- README 当前展示区更新为 `2.0.0`，旧版本明细继续保留在本文件中。

### 验证

- 发布前覆盖自有记忆、关联召回、即时聊天输入碎片、主动发言、官方上下文压缩、公共 API、配置契约、包体预检和 Python 编译检查。
- 发布包内 `metadata.yaml`、`main.py`、`README.md` 和 `CHANGELOG.md` 均指向 `2.0.0`。

## 1.8.6

发布日期：2026-05-12

### 修复

- 修复插件文档页可能抓取 README 顶部历史发布记录、从而误显示旧版本的问题；README 当前展示区只保留当前版本，旧版本明细保留在本文件中。
- 同步 `metadata.yaml`、`main.py @register(...)`、README 徽章、远程烟测期望版本和发布包内文档为 `1.8.6`。
- 保留上一版的即时聊天图片/表情包发送、官方自动上下文压缩兼容和自有记忆模块打包修复。

### 验证

- `python -m pytest -q tests/test_package_plugin.py -k "package or zip_preflight"`
- `python -m py_compile main.py realtime_chat_engine.py realtime_chat_input.py memory_engine.py public_api.py scripts\package_plugin.py`
- 发布包内 `metadata.yaml`、`main.py` 和 `README.md` 均指向 `1.8.6`。

## 1.8.5

发布日期：2026-05-12

### 修复

- 修复即时聊天分段接管时 `result_chain` / `message_chain` 中图片段可能被文本分段吞掉的问题，避免图片、表情包或混合消息发送失败。
- 修复 URL-only 表情包降级成纯文本链接的问题；可用 AstrBot URL 图片组件时会优先按图片发送。
- 兼容 AstrBot 官方自动上下文压缩：清洗压缩摘要中的 Sylanne 内部块，避免记忆召回、实时历史影子和官方摘要重复回灌。
- 若官方压缩摘要已经包含实时历史影子，本地 shadow 会标记为已消费，不再重复注入下一轮提示词。
- 修复发布包缺少 `memory_engine.py` 的问题，确保自有记忆模块随 `dist/astrbot_plugin_sylanne.zip` 一起安装。

### 验证

- `python -m pytest -q tests/test_package_plugin.py -k "package or zip_preflight"`
- `python -m pytest -q tests/test_astrbot_lifecycle.py tests/test_command_tools.py tests/test_public_api.py -k "realtime or sticker or image or proactive or memory or context_compression"`
- `python -m py_compile main.py realtime_chat_engine.py realtime_chat_input.py memory_engine.py public_api.py scripts\package_plugin.py`

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
