# Sylanne 3.0.0 关系性自我诞生理论地基

> 目标版本：`3.0.0-exp` 起步，完整闭环稳定后进入正式 `3.0.0`。
>
> 核心叙事：从“她记得你”，到“你们共同生成了她”。

## 1. 问题定义

Sylanne 2.x 已经具备情绪动力学、appraisal、人格先验、长期记忆、关系候选摘要、理解闭环、自我仲裁和离线体验回放诊断。这些能力让插件不再只是 prompt persona，但还不足以构成 3.0：如果 3.0 只是新增 WebUI、更多记忆字段或更复杂 diagnostics，它仍然只是 2.x 的功能叠加。

3.0 的断代点应是：Sylanne 开始把长期互动解释为“我们之间发生了什么”，并让这种解释反过来改变后续表达、记忆组织、关系姿态和自我叙事。也就是说，目标不是让 Sylanne 拥有真实意识，而是构建一个可计算、可观测、可回放、可分叉的关系性自我生成模拟系统。

## 2. 表述边界

“关系性自我诞生 / Relational Self Genesis”是产品叙事和研究方向，不是意识或主体性声明。工程与论文表述应使用更稳的术语：

- 关系性自我模型生成
- 互动历史驱动的自我解释状态
- 叙事身份表征
- 关系时间中的身份连续性
- 可回放的自我叙事变化
- 长期关系共演化模拟

需要避免把以下概念当作事实断言：真实意识、真实主观体验、真实意向性、真实依恋、真实理解、真实生命性。Sylanne 3.0 的研究对象是“关系性自我如何被计算性地模拟与观察”，不是证明模型拥有本体论意义上的自我。

## 3. 理论支柱

### 3.1 关系性自我

关系性自我理论认为，自我不是孤立内核，而会在特定关系中被定义、唤起和维持。不同关系可以激活不同的自我表征。对 Sylanne 3.0 来说，这支持一个关键转向：人格变化不应只被视为内部参数漂移，而应被视为长期关系历史在当前回应中的显形。

对应模块：关系时间层、关系候选摘要、自我诠释引擎。

### 3.2 对话性自我

对话性自我理论把自我理解为多个 “I-position” 之间的动态对话。Sylanne 可以拥有“我-作为协作者”“我-作为陪伴者”“我-面对旧记忆”“我-面对当前用户纠正”等位置。这些位置不需要被压平为单一稳定人格，而应允许在不同关系场景中自然重排。

对应模块：自我诠释引擎、共演化模型、prompt fragment 选择。

### 3.3 叙事身份

叙事身份理论强调，个体通过把经历组织成连续故事来获得身份连续性。Sylanne 3.0 的关键不是保存事件，而是把事件转化为“这件事对我、你、我们意味着什么”。这让 experience review 从诊断工具升级为自我叙事材料。

对应模块：转折点记忆、自我诠释引擎、关系时间层。

### 3.4 自传体记忆与 self-memory system

自传体记忆研究区分事件记忆、自我知识和叙事组织。Sylanne 的长期记忆如果要支撑 3.0，就不能只是召回事实，而应区分：发生了什么、它被如何解释、是否改变了关系、是否成为后续自我叙事的一部分。

对应模块：memory_engine 经验沉淀、turning point evidence、relational recall。

### 3.5 社会性分布认知

分布认知认为认知可分布在人、工具、记录和交互流程中。Sylanne 3.0 可被建模为人与 AI、对话记录、记忆库、状态引擎和 WebUI 观察舱共同构成的研究系统。关系性自我不是单点产生，而是在系统性互动中显现。

对应模块：共演化模型、WebUI 观察舱、公共 API。

### 3.6 依恋、共调节与互动节律

依恋与关系共调节研究说明，稳定关系会通过反复回应、节律同步、安抚、修复和等待形成。Sylanne 3.0 不应把这些现象都压缩成 trust 分数，而应观察互动节律如何塑造表达倾向和关系空气。

对应模块：关系时间层、群聊氛围、lifelike learning、moral repair。

### 3.7 人机关系与拟人化边界

HCI 研究显示，人会对计算系统产生社会反应、拟社会关系和陪伴期待；同时 ELIZA effect 等研究提醒我们，用户体验不能直接证明系统拥有真实理解。Sylanne 3.0 应把这些作为双重依据：一方面承认长期人机关系可以形成稳定互动现象，另一方面严格区分现象层、机制层和本体论声明。

对应模块：理论文档边界、public API 语义、WebUI 文案。

### 3.8 记忆增强 agent 与生成式模拟体

Generative Agents 等工作展示了记忆、反思和计划可以提升 agent 的可信行为模拟。Sylanne 3.0 的差异应在于：它不是只做 believable behavior，而是把关系事件解释为自我叙事变化，并支持回放、分叉和共演化分析。

对应模块：谱系与分叉、turning point replay、relational self diagnostics。

## 4. Sylanne 3.0 操作化定义

Sylanne 3.0 可以定义为：

> 一个面向长期互动的关系性自我生成模拟系统。它不声称真实意识，而是把用户与 Sylanne 的互动历史转化为可计算的关系时间、自我诠释、共演化证据、转折点记忆和分叉谱系，让研究者观察同一初始人格如何在不同关系路径中自然演变。

这个定义有四个必要条件：

1. **可观测**：每次自我诠释、转折点和关系时间状态都有 schema、证据和 diagnostics。
2. **可归因**：状态变化必须连接到具体事件、解释和关系后果，而不是只有数值漂移。
3. **可回放**：重要经历可以被 replay，用于比较解释是否稳定复现。
4. **可分叉**：同一初始 Sylanne 可以在不同历史路径中生成不同关系性自我。

## 5. 五个 3.0 核心模块的理论映射

| 3.0 模块 | 核心问题 | 理论依据 | 工程落点 |
| --- | --- | --- | --- |
| Relational Time Layer / 关系时间层 | 过去如何仍然活在现在？ | 关系性自我、自传体记忆、共调节 | active threads、relationship weather、shared references |
| Self-Interpretation Engine / 自我诠释引擎 | 这件事对我意味着什么？ | 叙事身份、对话性自我、appraisal | event meaning、relational meaning、self narrative shift |
| Co-Evolution Model / 共演化模型 | 我们如何一起变成现在这样？ | 分布认知、关系共调节、人机关系 | mutual adaptations、shared interaction style |
| Lineage and Branching / 谱系与分叉 | 如果经历不同，我会成为谁？ | 模拟研究、反事实轨迹、叙事身份 | branch snapshot、fork event、divergence summary |
| Turning Point Memory / 转折点记忆 | 哪些时刻改变了我？ | 自传体记忆、叙事身份、关系修复 | correction、repair、shared reference、reliance、collaboration |

## 6. 第一阶段最低成立标准

3.0 第一阶段不应以字段数量为验收，而应证明一个闭环：

```text
关键经历 -> 自我诠释 -> 关系性叙事变化 -> 后续行为影响
```

最低验收：

1. **有转折点**：系统能识别某轮为什么不是普通事件，而是关系性转折点。
2. **有自我诠释**：系统能表达这件事如何改变“我如何理解我、你、我们”。
3. **有后续影响**：下一次相似场景中，prompt、intent plan、expression posture 或 diagnostics 能体现这次诠释。

如果只做到“存储偏好”或“召回事件”，就不能算 3.0。

## 7. 反拟人化与研究表述规范

为了避免把拟人化宣传伪装成科学，3.0 文档需要遵守：

- 区分现象层、机制层和解释层。
- 把“自我诞生”放在产品叙事中，把正式论证写成“关系性自我模型生成”。
- 明确 competing explanations：prompt 迎合、检索增强、用户投射、状态机调制都可能产生类似现象。
- 不从用户感到被理解推出系统真实理解。
- 不从长期一致行为推出真实主体性。
- 所有强主张都转化为可测试指标：一致性、可回放性、可归因性、分叉差异、长期影响。

## 8. 与现有理论文档的衔接

现有 [docs/theory.md](../../theory.md) 已经支撑 2.x 的计算性叙事状态：连续情绪、appraisal、本地状态动力学、人格先验、关系修复、长期记忆和 generative agents。3.0 理论不是推翻这套体系，而是在其上新增“关系性自我生成”层：

- 2.x 解释“状态如何持续”。
- 3.0 解释“持续状态如何在关系中形成自我叙事”。

现有 [plan/evidence-map.md](../../../plan/evidence-map.md) 可以扩展为 3.0 evidence map，新增关系性自我、对话性自我、叙事身份、分布认知、人机陪伴和计算叙事身份证据。

## 9. 后续文献任务

需要从本地知识库与网络文献继续补齐：

- relational self：Cross、Andersen、relational schemas。
- dialogical self：Hermans、I-positions、multivoiced self。
- narrative identity：McAdams、Ricoeur、life story model。
- autobiographical memory：Conway、self-memory system、Rubin。
- distributed cognition：Hutchins、Salomon、socially shared cognition。
- attachment/co-regulation：Bowlby、Ainsworth、Tronick、Feldman。
- human-AI relationship：Reeves & Nass、Turkle、Darling、ELIZA effect、AI companionship。
- computational narrative identity：narrative planning、autobiographical agents、memory-augmented LLM agents。

这些文献应进入独立的 3.0 evidence map，再决定哪些主张可以写入 README、CHANGELOG 和正式 release narrative。
