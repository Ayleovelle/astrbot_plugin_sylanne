# 更新日志

本文件用于 AstrBot 插件市场/管理页展示更新内容。更完整的设计说明、公式推导、测试矩阵和维护手册见 `README.md`。

## 2.3.14

发布日期：2026-05-13

### 修复

- 将插件作者显示统一为 `Aylovelle.S.S`，并同步 `metadata.yaml` 与 `main.py @register(...)`。
- 将插件管理页可见的 LLM 工具、指令和钩子说明改为中文，避免发布页继续显示英文描述或“无描述”。
- 补充 README 中的 `logo.png` 排查说明：图标应位于插件根目录，远端仍显示默认图标时优先确认正式插件目录是否已被新包覆盖。
- 将发布 zip 预检上限按 AstrBot 插件市场约束收紧到 `16MB`，并重新生成发布包。

### 验证

- `python -m pytest -q tests/test_package_plugin.py`
- `python -m pytest -q tests/test_remote_smoke_contract.py`
- `python -m pytest -q tests/test_command_tools.py -k "readme_documents_registered_commands or readme_documents_registered_llm_tools or query_agent_state_tool"`
- `python -m pytest -q tests/test_public_api.py -k "main_register_decorator_uses_plugin_name_constant"`
- `node scripts/plugin_zip_preflight.js dist/astrbot_plugin_sylanne.zip astrbot_plugin_sylanne`

## 2.3.13

发布日期：2026-05-13

### 修复

- 修复活跃 Agent 运行期间用户追发消息丢失前文的问题：当上一轮 LLM 尚未产出可用回复时，同会话同说话人的后续消息会注入 `[sylanne_active_agent_followup_merge]`，让主 LLM 把 pending 用户消息和当前消息视为同一个连续意图。
- 合并发生在 `_request_to_text(request)` 之前，因此 `_last_request_text`、主 LLM 临时上下文和预响应情绪评估都能看到同一份合并事实；这不是长上下文重放，只保留短时间内的 pending 用户 turn。
- 将用户碎片完整性语义等待默认上限从 `6.0s` 降到 `4.0s`，并把运行时硬上限从 `20.0s` 降到 `4.0s`，避免把即时聊天延迟耗在死等上。
- 更新 2.3.13 工作流 SVG：加入等待期追发合并，移除误导性的单点模型诊断节点，调整中文字体栈和跨泳道箭头。
- 同步 `metadata.yaml`、`main.py @register(...)`、README 徽章、当前版本说明和远程烟测示例版本为 `2.3.13`。

### 验证

- `python -m pytest -q tests/test_astrbot_lifecycle.py -k "active_agent_followup or realtime_input or interrupted_reply or short_answer"`
- `python -m pytest -q tests/test_config_schema_contract.py`
- `python -m json.tool _conf_schema.json`

## 2.3.12

发布日期：2026-05-13

### 修复

- 修复主动聊天后台调度不会自行结算 `pending` 主动发言反馈的问题。调度器每轮醒来会先把过期未回应记录标为 `unanswered`，并写入生命化学习与轻量情绪反馈。
- 主动聊天候选上下文新增“长时间未聊天”的时间段推测：只能保守猜测用户可能在忙、休息、睡觉或暂时不方便，不能默认被无视，也不能继续施压追问。
- 主动发言 LLM 裁决增加旧话题去重约束：上一条主动发言无人回应、低信号回应或仍在等待时，不要隔几个小时继续抓同一个话题追问；没有新证据时优先沉默，单纯想念只能用低压力短句。
- 新增快速判断 LLM Provider 配置：用户碎片完整性和表情包一致性等短 JSON 判断可走低推理快模型，并使用独立短上下文预算、短超时和低温度；复杂情绪观测与主动话题裁决仍走原判断 LLM。

### 验证

- `python -m pytest -q tests/test_astrbot_lifecycle.py -k "marks_unanswered_before_repeating_topic"`
- `python -m pytest -q tests/test_astrbot_lifecycle.py -k "proactive_scheduler or proactive_cold_reply"`
- `python -m pytest -q tests/test_astrbot_lifecycle.py -k "fast_assessor or sticker_consistency_uses_fast_assessor"`

## 2.3.11

发布日期：2026-05-13

### 修复

- 将 Sylanne 自有 LLM Tool schema 对所有主聊天模型隐藏，`query_agent_state` 保留为兼容注册、命令/API 后端和内部路径，避免 Gemini/哈基米在工具轮次空回或把内部状态 JSON 发给用户。
- 修复用户短答和二次澄清容易被误解的问题：命中上一轮 bot 问题的短答会跳过碎片完整度 gate；“我只是想确认嵌入模型记忆模块”这类澄清会追加复读抑制 guard。
- 降低即时聊天延迟：碎片探测默认等待从 `0.65s` 降到 `0.25s`，语义等待上限从 `20s` 降到 `6s`；表情本地一致性已通过时不再额外调用内部 LLM。
- 记忆 Embedding provider 改为 AstrBot 原生 provider 选择器，并在『记忆设置』Page 增加可点击 provider 卡片，保留手填 ID 兼容。
- 主动聊天调度默认降频：正常约 15 分钟醒来一次，空闲约 30 分钟，同一会话约 1 小时内不重复复查，减少话题结束后的机械打扰。

### 验证

- `python -m pytest -q tests/test_astrbot_lifecycle.py -k "realtime_input or realtime_pending_bot_question or assistant_history_shadow or user_correction or gemini or tool_request or sticker_consistency or proactive_scheduler"`
- `python -m pytest -q tests/test_command_tools.py -k "query_agent_state_tool or llm_tool_json_result or readme_documents_registered_llm_tools or memory_settings_page"`
- `python -m pytest -q tests/test_config_schema_contract.py`

## 2.3.10

发布日期：2026-05-13

### 修复

- 修复即时聊天接管后，用户已经纠正“昨晚十点多睡了/早早起床了”，下一轮 bot 仍复读“你是不是没睡”的问题。
- 被插件接管的上一轮 assistant 回复会补进 `request.contexts`，让主 LLM 直接看到完整前文，而不是只依赖短摘要。
- 近期用户纠正事实会短暂缓存并作为真实 user 上下文补给下一轮，避免“我今天打算改论文”这类后续回复覆盖掉刚才的睡眠事实纠正。

### 验证

- `python -m pytest -q tests/test_astrbot_lifecycle.py -k "sleep_fact_correction or recent_sleep_correction"`
- `python -m pytest -q tests/test_astrbot_lifecycle.py -k "realtime_pending_bot_question or assistant_history_shadow or user_correction or sleep_fact_correction or recent_sleep_correction or realtime_input_fragments"`

## 2.3.9

发布日期：2026-05-13

### 修复

- 降低哈基米/Gemini OpenAI 兼容模型出现 `OpenAI completion has no usable output` 的概率。高风险 Gemini 主聊天请求现在不再向模型暴露 Sylanne 自己的 LLM Tool schema，包括 `query_agent_state`，避免模型进入工具调用后返回空 `content`。
- 外部插件工具仍会保留；非 Gemini 主模型仍保留统一只读入口 `query_agent_state`，11 个细分 Sylanne 工具继续只作为内部兼容方法存在。
- Gemini/哈基米风险模型每轮都会追加一条极短可见输出 guard，即使本轮没有工具上下文，也明确要求模型返回可见自然语言，减少“有 reasoning tokens 但无用户可见文本”的空回。

### 验证

- `python -m pytest -q tests/test_astrbot_lifecycle.py -k "gemini_tool_request_hides_sylanne_tools or only_sylanne_tools_removes or agent_owned_context_for_gemini_risk_models or removed_sylanne_tool_choice"`
- `python -m pytest -q tests/test_astrbot_lifecycle.py -k "gemini or provider or agent_owned_context or tool_request or tool_result or llm_switch"`
- `python -m pytest -q tests/test_command_tools.py -k "query_agent_state_tool or llm_tool_json_result or readme_documents_registered_llm_tools"`

## 2.3.8

发布日期：2026-05-12

### 修复

- 修复即时聊天分条接管后，用户短答没有稳定绑定到上一轮完整问句簇的问题。比如 bot 先问“喝了杯什么呀？这么神奇，一喝就困？”，用户只回“咖啡啊”时，现在会被视为对上一轮问题的回答，而不是被误解成“用户正在新发起冲咖啡/喝咖啡动作”。
- `realtime_assistant_history_shadow` 抽取未闭合问题时，会保留临近短问句和承接短句，避免只留下最后一个问号导致槽位丢失。
- `[sylanne_realtime_pending_bot_question]` 的短答提示更明确：名词或短答优先补全上一轮问题槽位，不要当成孤立新话题或新命令。

### 验证

- `python -m pytest -q tests/test_astrbot_lifecycle.py::AstrBotLifecycleTests::test_short_answer_context_keeps_question_cluster_for_split_reply`
- `python -m pytest -q tests/test_astrbot_lifecycle.py -k "realtime_pending_bot_question or short_answer_context or assistant_history_shadow or low_signal_followup or correction_suppresses"`

## 2.3.7

发布日期：2026-05-12

### 修复

- 修复同一会话切换主 LLM、fallback provider 或手动换模型后，Sylanne 仍沿用旧 provider 判断的问题。主回复请求现在每轮实时读取当前主聊天 provider 来决定上下文归属，不再被 `provider_id_cache_ttl_seconds` 的短缓存误导。
- 修复 `emotion_provider_id` 影响主聊天上下文归属的问题。判断/情绪评估 provider 只用于内部评估调用，不再让主 LLM 请求误进入 `gemini_agent_owned_context`。
- 收窄 Gemini 兼容模式识别规则，避免 `safe-non-gemini-assessor`、`non-gemini-provider` 这类名字被误判成 Gemini。
- 保持 AstrBot Agent 继续拥有长期对话上下文；Sylanne 只补充短状态摘要、短记忆召回和即时聊天投递事实，切模型后不会再因为旧 Gemini 策略跳过这些必要上下文。

### 验证

- `python -m pytest -q tests/test_astrbot_lifecycle.py -k "provider_id_is_cached or llm_switch or context_owner_after_llm_switch or non_gemini_hint or gemini_chat_provider_guard or gemini_emotion_provider"`
- `python -m pytest -q tests/test_astrbot_lifecycle.py -k "gemini or provider or agent_owned_context or realtime_input or realtime_continuity or tool_request"`
- `python -m pytest -q tests/test_command_tools.py -k "query_agent_state_tool or llm_tool_json_result or sylanne_memory"`

## 2.3.6

发布日期：2026-05-12

### 修复

- 修复 `query_agent_state_tool` 的返回值路径。它现在直接把 JSON 字符串返回给 AstrBot 工具循环，而不是走 `event.plain_result(...)`，从而避免 runner 把工具结果误判成“没有返回值，或者已将结果直接发送给用户”。
- 继续保留 2.3.5 的内部工具 JSON 外泄阻断：若别的内部工具结果在缺少元数据时进入最终 `completion_text`，仍会被 `on_llm_response` 识别并阻断用户可见发送。
- 同步 README、工作流图、版本号和发布包，让工具调用、工具返回和发布记录保持一致。

### 验证

- `python -m pytest -q tests/test_command_tools.py -k "query_agent_state_tool or llm_tool_json_result"`
- `python -m pytest -q tests/test_astrbot_lifecycle.py -k "sylanne_tool_json_result or role_tool_result or tool_call_response or intercepts_completion or realtime_intercept"`
- `python -m pytest -q tests`
- `python -m py_compile main.py realtime_chat_input.py`
- `python scripts\package_plugin.py`
- `node scripts\plugin_zip_preflight.js dist\astrbot_plugin_sylanne.zip astrbot_plugin_sylanne`

## 2.3.5

发布日期：2026-05-12

### 修复

- 修复 `query_agent_state` 等 Sylanne 内部工具结果在缺少工具元数据时，可能被当成普通聊天正文发给用户的问题。现在带 `astrbot.*` 内部 `schema_version` 与 `kind` 的工具 JSON 会在 `on_llm_response` 阶段被识别、清空默认发送内容并阻断用户可见发送。
- 保留真正的 Agent 工具循环：带 `tool_calls`、`function_call`、`role=tool/function` 或工具调用 ID 的结构化响应仍直接交给 AstrBot Agent，不会被 Sylanne 清空，也不会消费待回复 epoch。
- 同步 README 与工作流图，突出“用户碎片化输入合并”和“最终自然语言回复才进入即时聊天分条投递”，内部工具 JSON 不进入即时聊天分段。

### 验证

- `python -m pytest -q tests/test_astrbot_lifecycle.py -k "sylanne_tool_json_result or role_tool_result or tool_call_response"`
- `python -m pytest -q tests/test_astrbot_lifecycle.py -k "tool_call_response or intercepts_completion or realtime_intercept or sylanne_tool_json_result"`
- `python -m pytest -q tests/test_command_tools.py -k "query_agent_state_tool or llm_tool_json_result"`
- `python -m pytest -q tests`
- `python -m py_compile main.py realtime_chat_input.py`
- `python scripts\package_plugin.py`
- `node scripts\plugin_zip_preflight.js dist\astrbot_plugin_sylanne.zip astrbot_plugin_sylanne`

## 2.3.4

发布日期：2026-05-12

### 修复

- 将 Sylanne 细分 LLM Tool 对所有主 LLM 隐藏，只保留统一入口 `query_agent_state`。模型仍可通过 `state`、`detail`、`track` 和 `include_runtime` 查询情绪、记忆、群聊氛围、人格漂移、综合自我、运行诊断等状态。
- 请求进入 provider 前会统一剪除历史残留或框架缓存中的细分 Sylanne 工具 schema；如果 `tool_choice/function_call` 指向被隐藏工具，会自动退回 `auto` 或 `none`，不影响外部插件工具。
- 细分工具方法保留为内部兼容方法，不再注册给 AstrBot LLM Tool；插件命令、Python 公共 API、后台评估、主动发言、自有记忆和状态注入流程不受影响。

### 验证

- `python -m pytest -q tests/test_astrbot_lifecycle.py -k "non_gemini_tool_request_hides_detail_tools or gemini_tool_request_keeps or only_sylanne_tools_keeps or removed_sylanne_tool_choice"`
- `python -m pytest -q tests/test_command_tools.py -k "readme_documents_registered_llm_tools or query_agent_state_tool or llm_tool_json_result or simulate_bot_emotion_update"`
- `python -m pytest -q tests`
- `python -m py_compile main.py realtime_chat_input.py`

## 2.3.3

发布日期：2026-05-12

### 修复

- 修复 `2.3.2` 对 Gemini 系模型剪除 Sylanne LLM Tool 时过于激进的问题。现在 Gemini 仍会保留统一只读入口 `query_agent_state`，LLM 可以通过 `state` 和 `detail` 参数查询情绪、记忆、群聊氛围、运行诊断等 Sylanne 状态。
- Gemini 下只隐藏其余 11 个细分 Sylanne 状态工具，减少工具选择 schema 压力；外部插件工具仍照常保留，非 Gemini 模型仍保留完整 12 个 Sylanne LLM Tool。
- 如果 Gemini 的 `tool_choice/function_call` 强制指向被隐藏的细分 Sylanne 工具，会自动退回 `auto`；如果指向 `query_agent_state`，则保持原样。

### 验证

- `python -m pytest -q tests/test_astrbot_lifecycle.py -k "gemini or tool_call_response or tool_request or tool_result"`
- `python -m pytest -q tests/test_command_tools.py -k "readme_documents_registered_llm_tools or llm_tool_json_result or query_agent_state_tool"`
- `python -m pytest -q tests`
- `python -m py_compile main.py realtime_chat_input.py`

## 2.3.2

发布日期：2026-05-12

### 修复

- 修复 Gemini 3.1 flash-lite preview 在工具选择阶段仍可能空输出的问题。Gemini 系模型请求会在进入 provider 前剪除 Sylanne 自己注册的 LLM Tool schema，避免 12 个状态工具每轮都压进工具列表。
- 如果请求里只有 Sylanne 工具，会把工具列表剪空并把 `tool_choice/function_call` 改为 `none`；如果还有其他插件或框架工具，则只保留外部工具，并继续追加极短可见输出 / `tool_calls` 兼容提示。
- 保留 Python 公共 API、聊天命令和非 Gemini 模型的 LLM Tool 行为不变；本修复只影响 Gemini 系主模型的请求前工具 schema。

### 验证

- `python -m pytest -q tests/test_astrbot_lifecycle.py -k "gemini or tool_call_response or tool_request or tool_result"`
- `python -m pytest -q tests/test_command_tools.py -k "readme_documents_registered_llm_tools or llm_tool_json_result or query_agent_state_tool"`
- `python -m pytest -q tests`
- `python -m py_compile main.py realtime_chat_input.py`

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
