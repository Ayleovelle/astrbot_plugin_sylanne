# Sylanne 完整理解闭环设计规格

## 目标

本次迭代要把 Sylanne 的上下文、记忆和表达从“若干局部补丁”推进成一个可审计闭环：

```text
AstrBot 原生事件
→ Sylanne conversation event ledger
→ lifecycle auditor 判断话题/投递/记忆状态
→ pun/typo/common-ground interpreter 解释错别字、谐音梗、黑话
→ 受控注入当前请求
→ 受控写入长期记忆
→ 表达克制策略选择回复姿态
```

范围一次性包含用户确认的完整方向：

1. 上下文生命周期的稳定语义。
2. 长期记忆的可信度分层。
3. 自我表达的克制。
4. 谐音梗、错别字、黑话和用户自创称呼理解。

## 非目标

- 不替代 AstrBot Agent 原生上下文池。
- 不把用户原文改写成规范文本。
- 不引入大型拼音库、分词库或外部服务作为强依赖。
- 不让每轮聊天都调用额外 LLM 判断错别字或谐音，避免延迟和成本失控。
- 不把谐音梗、玩笑、临时昵称直接固化成事实记忆。

## 核心设计

### 1. Conversation Event Ledger

新增 Sylanne 自己的短期事件账本。它只做审计和辅助，不接管 AstrBot 长期上下文。

每条事件包含：

- `event_id`：稳定短 ID。
- `session_key`：会话键。
- `speaker_key`：说话人轨道。
- `role`：`user | assistant | system`。
- `raw_text`：原始文本。
- `normalized_text`：仅用于匹配的轻量规范化文本。
- `media_summary`：当前媒体/表情摘要。
- `quote_summary`：引用/回复消息摘要。
- `event_time`：AstrBot 事件时间、本地时间和 epoch。
- `delivery_status`：assistant 事件使用，包含 `pending | delivered | interrupted | unsent`。
- `topic_state`：`open | completed | shifted | corrected | stale`。
- `interpretations`：错别字、谐音、黑话候选解释列表。
- `memory_gate`：是否允许长期写入，以及原因。

Ledger 使用有界队列，按 session 保存最近事件。第一版只保留短窗口，不做长期全文归档。

### 2. Lifecycle Auditor

Lifecycle auditor 负责判断 shadow memory、投递上下文和话题是否仍需保留。

状态机：

```text
pending
→ delivered
→ completed | corrected | needs_followup | stale

pending
→ interrupted
→ needs_followup | corrected | completed | stale
```

规则：

- `delivered` 只表示“已经实际发送”，不表示“下一轮必须续接”。
- 完整送达且无未完成问句、无用户打断、无用户明确引用上一轮时，下一轮普通新话题应标记为 `completed` 并释放。
- 用户说“刚才你说”“再说一遍”“接着说”“没说完”“那句话”“这段话”时，才把上一轮内容作为连续性线索。
- 用户纠正或追问信息来源时，状态转为 `corrected`，允许带上一轮内容，但必须给当前用户文本最高优先级。
- 仅引用旧消息、没有真实当前文本时，不消费唯一一次 shadow memory。
- 时间敏感发言继续使用已有 TTL/stale 规则，但应记录为 lifecycle 决策，而不是隐式丢弃。

### 3. Pun / Typo / Homophone Interpreter

新增轻量解释层，输出候选，不覆盖用户原文。

输出结构：

```python
{
    "raw_text": "原文",
    "candidate": "候选解释",
    "kind": "typo | homophone | slang | nickname | joke | uncertain",
    "confidence": 0.0,
    "humor_likelihood": 0.0,
    "evidence": ["触发原因"],
    "should_ask_confirmation": False,
    "should_memorize": False,
}
```

第一版解释来源：

- 用户纠正模式：例如“我打错了”“不是 X 是 Y”。
- 常见近形/近音轻量规则：只做低风险候选。
- 已确认 common-ground：用户多次使用或明确解释过的词。
- 上下文一致性：当前词面不通顺但替换候选能解释上下文。
- 玩笑线索：重复夸张、表情、语气词、故意错写。

禁止行为：

- 不把候选解释当作事实覆盖原文。
- 不用低置信候选触发长期记忆写入。
- 不在回复里炫耀式解释谐音梗。
- 不把用户玩笑错写纠正成严肃事实。

### 4. Common-ground Learning

谐音梗、黑话、称呼和习惯性错写进入 common-ground，而不是普通事实记忆。

写入条件：

- 用户明确解释过含义；或
- 同一表达在短期窗口多次出现且上下文含义稳定；或
- bot 猜测后用户确认。

保存内容：

- 原始表达。
- 候选含义。
- 证据次数。
- 最近使用时间。
- 是否玩笑/昵称/黑话。
- 置信度。

### 5. Memory Gate

长期记忆写入前增加可信度分层：

- `hard_fact`：用户明确事实，可长期记。
- `soft_preference`：偏好或表达习惯，可低权重记。
- `joke_or_bit`：玩笑、谐音梗、角色扮演，只进 common-ground，不进硬事实。
- `correction`：用户纠正 bot 的误读，短期高优先级，可写成“纠正事实”。
- `uncertain_interpretation`：低置信候选，只用于本轮。

规则：

- 当前用户文本优先于旧记忆和 shadow。
- 纠正事实优先于旧猜测。
- 玩笑和谐音默认不是事实。
- 低置信错别字候选不写长期记忆。

### 6. 表达克制策略

新增回复姿态选择，不是每轮都浓烈、撒娇或文学化。

姿态包括：

- `brief_answer`：短答。
- `tool_like`：工具型回答。
- `clarify`：轻轻确认。
- `listen`：先听、不扩写。
- `emotional`：情绪回应。
- `playful`：接梗。
- `silent_or_minimal`：低信号或无需回应时少说。

触发规则：

- 用户问技术/版本/文件/命令：优先 `tool_like`。
- 用户纠正事实：优先 `clarify` 或简短承认误读。
- 谐音梗高置信：可 `playful`，但短，不解释过度。
- 谐音/错别字低置信：`clarify`，不要强行玩梗。
- 用户只是低信号或表情：`listen` 或 `silent_or_minimal`。
- 亲密表达有明确情绪需求时才用 `emotional`。

### 7. Prompt 注入

新增受控提示块：

- `[sylanne_event_ledger_summary]`：最近 3-5 条事件摘要。
- `[sylanne_lifecycle_audit]`：上一轮话题状态、shadow 是否可用、释放原因。
- `[sylanne_interpretation_candidates]`：谐音/错别字/黑话候选。
- `[sylanne_expression_policy]`：本轮建议回复姿态。

注入规则：

- 块必须短。
- 所有候选解释都写明“不覆盖用户原文”。
- 低置信解释写明“如需使用，应轻轻确认”。
- lifecycle audit 不得把 completed 内容再次当作续接上下文。

### 8. Diagnostics

扩展运行时诊断，能看到：

- 最近 ledger 事件。
- shadow lifecycle 状态。
- 话题完成/换题/纠正判断。
- pun/typo 候选。
- memory gate 决策。
- expression policy。

## 测试策略

必须 TDD：先写失败测试，再实现。

覆盖：

1. 完整送达话题自然结束后，下一轮新话题不注入 shadow。
2. 用户明确“刚才你说”时，允许注入上一轮。
3. 用户纠正上一轮时，注入纠正上下文并优先当前文本。
4. 仅引用旧消息不消费 shadow。
5. 错别字低置信只生成候选，不写记忆。
6. 用户确认错别字含义后，写入 common-ground。
7. 谐音梗被识别为 joke/common-ground，不写 hard fact。
8. 技术问题选择 tool-like/brief 策略，不生成过度情绪回复。
9. 低信号表情选择 minimal/listen，不强行扩写。
10. 诊断接口能显示 ledger、lifecycle、interpretation、memory gate 和 expression policy。

## 发布策略

这是较大行为变更，应升小版本，例如 `2.7.0`。如果实现中只完成部分内核，不发布完整闭环，则不得升到 `2.7.0`，应保留在开发提交或使用 patch 版本。

## 验收标准

- 全量测试通过。
- 新增 lifecycle、interpretation、memory gate、expression policy 的定向测试。
- README/CHANGELOG 说明新架构边界。
- zip 预检通过。
- 如果发布，则 GitHub Release 和包内版本一致。
