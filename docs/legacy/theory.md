# Soulful Yearning Lifelike AstrBot Neural Narrative Engine 理论依据

## 摘要

本文统合 `astrbot_plugin_sylanne` 的理论依据、状态建模方法与工程验证证据。该插件并不把 bot 描述为具有真实意识或真实主观体验，而是把“情绪、关系、记忆、主动聊天与安全边界”定义为一组可计算、可持久化、可测试的叙事状态。模型以 PAD 与 circumplex affect 的连续情绪空间为底座，引入 appraisal theory 对目标一致性、确定性、可控性、责任归因和社交亲近进行语义评价，再用人格先验、真实时间半衰期、置信门控和有界平滑将即时观测转化为长期状态。系统实现上，LLM 负责解释语义，插件本地状态机负责动力学、限幅、衰减、关系后果、记忆召回和安全仲裁。远程 benchmark 显示，gpt-5.5 功能矩阵完成 `2500/2500` 个有效样本且失败请求为 `0`；跨模型生命周期拟合则用于说明长期状态的时间敏感性，但其每模型 `9` 个样本的口径只能作为发布参考趋势，而不能作为强统计结论。本文最后强调：Sylanne 是计算性叙事引擎，不是临床评估系统，也不是意识模拟声明。

## 关键词

情感计算；appraisal theory；情绪动力学；人格先验；长期记忆；关系型代理；AstrBot；LLM 工具编排；非诊断心理筛查

## 1. 引言

聊天 bot 的“像一个人”不能只靠提示词里写几句性格描述。提示词可以规定口吻，却很难保证跨轮一致的情绪惯性、关系后果、记忆取舍和主动聊天时机。用户在即时聊天中还会不断补充碎片信息，例如先说一个反应，再隔几秒补充对象或理由；如果系统只抓最后半句，bot 就会表现出“没听懂前文”的断裂感。Sylanne 的目标不是让模型假装拥有真实情绪，而是把这些断裂点拆成工程状态：哪些由 LLM 判断语义，哪些由本地引擎维持连续性，哪些必须被安全边界拦住。

因此，本文使用“计算性叙事状态”作为核心概念。所谓计算性，是指所有状态都能落到有界数值、版本化 payload、半衰期、阈值、冷却和测试契约；所谓叙事，是指这些状态服务于 bot 在对话中的连续人格、记忆和关系表达。这个定义刻意避开意识化和临床化宣称：插件只调制表达、召回和策略，不声称产生真实主观体验，也不输出医学诊断。

## 2. 理论基础

### 2.1 连续情绪空间

PAD 模型与 Russell 的环形情感模型说明，情绪不必先被离散成“开心、难过、生气”这类标签，也可以被表示为效价、唤醒和支配感等连续维度。Sylanne 将情绪状态写成受人格 `P` 调制的有界向量：

```math
E_t(P) \in [-1,1]^7
```

默认七维为：

```math
E_t =
\begin{bmatrix}
V_t & A_t & D_t & G_t & C_t & K_t & S_t
\end{bmatrix}^{\mathsf T}
```

其中 `V/A/D` 分别表示效价、唤醒和支配感；`G/C/K/S` 分别表示目标一致性、确定性、情境可控性和社交亲近度。前三维给出情绪强度和姿态，后四维把“这件事对 bot 意味着什么”显式化。

### 2.2 Appraisal 语义评价

OCC、Lazarus、Scherer 与 Roseman 的评价理论共同指出，情绪不是事件文本的直接反射，而是事件与目标、责任、控制、规范和关系的组合意义。相同一句话，在“用户撒娇”“用户道歉”“用户攻击”“用户补充事实”四种情境里，对 bot 的意义不同。Sylanne 因此把 LLM 的职责限定为语义评价：读完整上下文、识别当前事件、输出即时观测与 appraisal。

理论上可写成隐藏评价向量：

```math
Z_t =
\begin{bmatrix}
z_{\mathrm{goal}} & z_{\mathrm{agency}} & z_{\mathrm{control}} &
z_{\mathrm{certainty}} & z_{\mathrm{norm}} & z_{\mathrm{social}}
\end{bmatrix}^{\mathsf T}
```

LLM 给出评价后，本地引擎将其映射成有界观测：

```math
X_t = \tanh(WZ_t+\beta)
```

这里的关键不是让 LLM 直接控制长期状态，而是让它只回答“发生了什么、对当前 bot 意味着什么”。状态是否该大幅改变、持续多久、是否进入修复或冷却，由本地动力学决定。

### 2.3 情绪惯性与真实时间

情绪惯性研究说明，上一状态不会被单轮文本完全覆盖；情绪调节研究也提示，恢复速度与个体差异、事件强度和情境控制有关。Sylanne 因此不用消息轮数模拟时间，而使用真实经过时间 `Delta t`：

```math
B_t=(1-\gamma_p)E_{t-1}+\gamma_p b_p
```

```math
\gamma_p(\Delta t)=1-2^{-\Delta t/H_p}
```

`b_p` 是人格调制后的基线，`H_p` 是真实时间半衰期。随后，当前观测只以自适应步长写入长期状态：

```math
E'_t=B_t+\alpha_t(X_t-B_t)
```

这个式子也可以理解为二次优化的闭式解：状态在“保持惯性”和“接纳当前观测”之间折中。`alpha_t` 由置信度、惊讶度、人格反应性和限幅自动推导，而不是暴露给普通配置者手调。

### 2.4 人格先验

同一句话对不同 persona 的意义不同。Sylanne 把 persona 文本转成可靠性加权的潜在人格先验，而不是把 persona 只当作输出口吻。人格向量覆盖 Big Five、HEXACO honesty-humility、依恋焦虑/回避、BIS/BAS、need for closure、情绪调节能力和人际温度：

```math
q_p =
\begin{bmatrix}
O & N & X & A & L & H & R_a & R_v & I & B & F & U & W_s
\end{bmatrix}^{\mathsf T}
```

多源证据包括 persona 词汇线索、旧工程 trait 和结构先验。模型以可靠性加权、先验收缩的目标函数估计 `q_p`：

```math
J(q)=\|Mq-y\|_R^2+\lambda\|q-\mu\|_{\Sigma^{-1}}^2
```

闭式后验为：

```math
q_p =
\left(M^{\mathsf T}RM+\lambda\Sigma^{-1}\right)^{-1}
\left(M^{\mathsf T}Ry+\lambda\Sigma^{-1}\mu\right)
```

运行时采用对角近似以保证轻量和确定性。人格画像只作为工程先验，不是临床人格测量；公开 payload 暴露 trait 分数、置信度、方差和派生因子，不暴露原始 persona 文本。

### 2.5 行动倾向与关系修复

Frijda 的 action tendency / action readiness 研究说明，情绪更像行动准备，而不是固定话术。Carver 与 Harmon-Jones 关于愤怒和趋近动机的研究也提示，负性情绪不必然导致退避。Sylanne 因此把情绪后果单独建模为 `O_t`：靠近、退避、对抗、争辩、安抚、修复、求证、谨慎、反刍、表达强度和问题解决。

```math
O_t =
\begin{bmatrix}
o_{\mathrm{approach}} & o_{\mathrm{withdrawal}} &
o_{\mathrm{confrontation}} & o_{\mathrm{repair}} &
o_{\mathrm{caution}} & o_{\mathrm{problem}}
\end{bmatrix}^{\mathsf T}
```

关系修复并不等于一句“对不起”。宽恕、道歉和信任修复研究强调责任承认、伤害承认、悔意、补偿、未来承诺、重复犯错和误读可能性。插件中的 `moral_repair_engine.py` 与 `emotion_engine.py` 将这些因素拆成结构化字段，让 bot 可以选择澄清、承认误读、降低对抗、提出修复，而不是用一个“生气/原谅”标签跳转。

## 3. 系统方法

### 3.1 LLM 与本地引擎的分工

Sylanne 的工作流可以概括为：主聊天上下文交给 AstrBot Agent，插件只补充短状态、记忆召回和投递事实；内部细分工具对主聊天模型隐藏，由插件和 Agent 层自行编排。这种分工减少了三类问题：第一，Gemini 等模型在工具 schema 复杂时可能空回或触发拦截；第二，内部状态 payload 可能被当作普通消息发给用户；第三，低上下文模型无法同时承载完整历史和所有工具细节。

因此，插件不要求所有主模型都直接理解全部内部工具。主模型负责聊天；Agent 和插件服务负责查询状态、合并碎片、选择记忆和更新本地状态。对于简单判断，系统可以使用低推理、短输出的 LLM 接口；对于复杂 appraisal，则使用原有判断模型或主模型补充。低推理模型的上下文短，所以输入必须是压缩后的当前事实，而不是全量历史。

### 3.2 即时聊天与碎片整合

即时聊天的核心风险是“回复前用户又补了一句”。如果上一轮 LLM 尚未开始输出可用回复，插件应将追发消息合并进同一用户意图，而不是等第一条回复完成后再把第二条当成新话题。若 bot 已经开始分条发送，则用户插话会中断未发片段，并用新的合并上下文发起下一轮。

这条链路解释了用户日志中的问题：用户先问“只有一点点开心嘛”，紧接着补“那我要咬死你了”，系统若只回复第一句或只抓第二句，就会显得上下文被吞。修复后的目标是：在 LLM 回复前合并前文；在回复后用“已发/未发”的事实辅助 Agent 续接；而不是让插件替主模型重写所有上下文。

### 3.3 群聊氛围与主动发言

群聊中 bot 不应把长时间无人回应简单解释成“被无视”。用户可能在忙、休息、写论文或睡觉。`group_atmosphere_engine.py` 使用活跃度、紧张度、玩笑度、支持度、bot 注意力、插话风险和加入适宜度来决定是否开口；`lifelike_learning_engine.py` 则记录共同语境、熟悉词、偏好、节奏和互需信号。主动聊天的目标不是一直抓着旧话题追问，而是在合适时间表达想念、提醒、陪伴或轻轻转话题。

群聊氛围状态可写成：

```math
A^g_t =
\begin{bmatrix}
a_t & r_t & p_t & s_t & b_t & i_t & j_t
\end{bmatrix}^{\mathsf T}
```

其中 `i_t` 是插话风险，`j_t` 是加入适宜度。策略层使用冷却、阈值和真实时间衰减，让 bot 有时短应、有时先听、有时自然加入。

### 3.4 长期记忆、关联召回与遗忘

长期记忆不应把所有历史原文无限塞回 prompt。Ebbinghaus、Tulving、Anderson、Bjork 与 Schacter 等记忆研究共同支持一个分层观点：事件记忆、语义事实、最近使用、检索线索和遗忘机制都影响召回。Sylanne 的 `memory_engine.py` 把记忆写成可检索记录，并使用稀疏关键词、Embedding 相似度、关联边、真实时间新鲜度、深度、置信度和干扰共同打分。

语义召回可简化为：

```math
s_i^*(q)=
\max\left(
s_i(q),
\Pi_{[0,1]}(0.66r_i^v(q)+0.34s_i(q))
\right)
```

召回分数为：

```math
R_i =
\Pi_{[0,1]}\left(
0.42s_i^*(q)+0.24d_i+0.18c_i+0.16f_i(t)-0.22\eta_i
\right)
```

这套设计让“用户说的是插件记忆模块”这类长期指代能被补全，同时避免旧记忆凭深度乱入当前话题。Embedding provider 不可用或维度不匹配时，系统自动退回稀疏检索。

### 3.5 综合自我仲裁

`integrated_self.py` 把情绪、拟人、生命化学习、人格漂移、道德修复、瑕疵模拟、心理筛查和群聊氛围整合为一个 response posture。这个总线不直接生成回复，而是提供“允许的表达调制”和“禁止的危险动作”。例如，非诊断心理风险高时，普通撒娇式陪聊必须让位给人工复核和危机资源提示；瑕疵风险高时，bot 应承认不确定、澄清问题或纠错，而不是编造。

## 4. 安全边界

Sylanne 的安全边界包括四层。

第一，计算性状态边界：所有情绪、人格、记忆、拟人和关系后果都是工程状态，不是主体体验声明。

第二，非诊断边界：`psychological_screening.py` 只能做红旗信号和趋势观察。PHQ-9、GAD-7、PSS、WHO-5、ISI-like 字段用于启发式筛查，不等于施测原量表，也不输出临床 cut-off 或诊断结论。

第三，关系伦理边界：主动聊天、互需模式和亲密表达只能作为风格调制，不能羞辱、威胁、操控用户，也不能拒绝必要帮助。

第四，数据边界：公开 API 与工具结果必须版本化、脱敏、分层。内部状态查询不得把完整 JSON 直接发给用户；工具 schema 对主聊天模型隐藏时，Agent 仍可通过插件服务使用功能。

## 5. 工程验证与数据图表

### 5.1 功能矩阵

正式远程功能矩阵来自 `remote-emotion-v050-gpt55-feature-state-layer-real`。该运行使用 gpt-5.5，10 个功能用例各 250 条有效样本，共 `2500/2500`，失败请求 `0`。关闭情绪对照来自 `remote-emotion-v050-gpt55-noemotion-control-state-layer-c3-250-real`，有效样本 `250/250`，失败请求 `0`。图 1 将各模块相对 `baseline_minimal` 的平均延迟增量和平均 token 增量放在同一张图中。

![功能矩阵中的状态模块增量开销](assets/theory_feature_matrix_overhead.svg)

这张图的解释必须谨慎。远程端到端延迟包含 WebUI、AstrBot、provider、网络和模型排队，不等于纯本地插件耗时；token 增量更适合观察状态注入和提示片段开销。`all_safe_modules` 的平均延迟和 token 增量最高，符合“更多安全模块同时开启会增加上下文与状态处理”的直觉；`integrated_self_full` 平均延迟略低于 baseline，则更可能来自远程采样窗口波动，不能解释成该模块必然加速。

### 5.2 生命周期拟合

跨模型生命周期模拟使用状态级模拟时间覆盖 `1d` 到 `1y`，拟合模型为：

```math
y=\beta_0+\beta_1\mathrm{log}_2(d)
```

其中 `d` 是天数。图 2 展示每个模型的延迟斜率与 token 斜率。

![跨模型生命周期模拟拟合解释](assets/theory_lifecycle_fit_explanation.svg)

该图说明模型之间对长期状态、上下文长度和 provider 调度的敏感性存在差异。例如部分 Gemini 与 Mimo 模型在 token 或延迟斜率上更高。但每个模型只有 9 条生命周期样本，且每个时间尺度只有 1 条，因此它只能作为发布参考拟合，不能替代每尺度 100 次以上的正式统计。

### 5.3 本地测试覆盖

本地测试覆盖情绪更新、真实时间衰减、关系修复、即时聊天输入合并、Agent 工具隐藏、公共 API、LivingMemory 载荷、道德修复、瑕疵模拟、群聊氛围、非诊断心理筛查、打包预检和远程脚本契约。测试不是论文里的实证用户研究，但它证明了工程不只是提示词：每个理论模块都至少有对应的状态结构、公共契约或回归测试。

## 6. 讨论

Sylanne 的价值在于把“像在持续相处”拆成可解释的状态层：情绪向量负责连续姿态，appraisal 负责语义意义，人格先验负责个体差异，后果状态负责行动倾向，记忆层负责长期指代，群聊氛围负责参与时机，综合自我负责安全仲裁。这样做可以减少复读、上下文断裂、工具外泄、单轮情绪跳变和主动聊天误判。

但它也有清晰限制。第一，LLM 的 appraisal 仍可能误读语义，所以插件必须允许澄清和回滚。第二，低推理模型适合短 JSON 判断，不适合全量历史理解；复杂语境仍需要 Agent-owned context。第三，远程 benchmark 反映端到端体验，不等于本地函数耗时。第四，心理筛查只适合风险提示，不能替代专业评估。

## 7. 结论

Sylanne 可以被概括为一个面向 AstrBot 的“神经叙事状态引擎”：它把情绪、人格、记忆、关系修复、主动聊天和安全边界纳入同一套有界、可追踪、可测试的计算框架。它的理论根基来自情感计算、连续情绪模型、认知评价理论、人格心理学、情绪动力学、关系修复、会话分析和记忆理论；它的工程边界则由真实时间衰减、版本化 payload、公共 API、工具隐藏、测试矩阵和远程 benchmark 共同约束。换句话说，它不试图证明 bot 真的“有心”，而是让 bot 在长期对话中更稳定、更少遗忘、更少误读，也更知道什么时候该说、什么时候该听。

## 参考文献

1. Mehrabian, A., & Russell, J. A. (1974). *An Approach to Environmental Psychology*. MIT Press.
2. Mehrabian, A., & Russell, J. A. (1974). The basic emotional impact of environments. *Perceptual and Motor Skills, 38*(1), 283-301. https://doi.org/10.2466/pms.1974.38.1.283
3. Russell, J. A. (1980). A circumplex model of affect. *Journal of Personality and Social Psychology, 39*(6), 1161-1178. https://doi.org/10.1037/h0077714
4. Ortony, A., Clore, G. L., & Collins, A. (1988). *The Cognitive Structure of Emotions*. Cambridge University Press. https://doi.org/10.1017/CBO9780511571299
5. Lazarus, R. S. (1991). *Emotion and Adaptation*. Oxford University Press. https://doi.org/10.1093/oso/9780195069945.001.0001
6. Scherer, K. R., Schorr, A., & Johnstone, T. (Eds.). (2001). *Appraisal Processes in Emotion: Theory, Methods, Research*. Oxford University Press.
7. Scherer, K. R. (2005). What are emotions? And how can they be measured? *Social Science Information, 44*(4), 695-729. https://doi.org/10.1177/0539018405058216
8. Kuppens, P., Allen, N. B., & Sheeber, L. B. (2010). Emotional inertia and psychological maladjustment. *Psychological Science, 21*(7), 984-991. https://doi.org/10.1177/0956797610372634
9. Picard, R. W. (1997). *Affective Computing*. MIT Press.
10. Frijda, N. H. (1987). Emotion, cognitive structure, and action tendency. *Cognition and Emotion, 1*(2), 115-143. https://doi.org/10.1080/02699938708408043
11. Frijda, N. H., Kuipers, P., & ter Schure, E. (1989). Relations among emotion, appraisal, and emotional action readiness. *Journal of Personality and Social Psychology, 57*(2), 212-228. https://doi.org/10.1037/0022-3514.57.2.212
12. Roseman, I. J. (1991). Appraisal determinants of discrete emotions. *Cognition and Emotion, 5*(3), 161-200. https://doi.org/10.1080/02699939108411034
13. Roseman, I. J., Wiest, C., & Swartz, T. S. (1994). Phenomenology, behaviors, and goals differentiate discrete emotions. *Journal of Personality and Social Psychology, 67*(2), 206-221. https://doi.org/10.1037/0022-3514.67.2.206
14. Gross, J. J. (1998). The emerging field of emotion regulation: An integrative review. *Review of General Psychology, 2*(3), 271-299. https://doi.org/10.1037/1089-2680.2.3.271
15. Carver, C. S., & Harmon-Jones, E. (2009). Anger is an approach-related affect: Evidence and implications. *Psychological Bulletin, 135*(2), 183-204. https://doi.org/10.1037/a0013965
16. Christensen, A., & Heavey, C. L. (1990). Gender and social structure in the demand/withdraw pattern of marital conflict. *Journal of Personality and Social Psychology, 59*(1), 73-81. https://doi.org/10.1037/0022-3514.59.1.73
17. Schrodt, P., Witt, P. L., & Shimkowski, J. R. (2014). A meta-analytical review of the demand/withdraw pattern of interaction. *Communication Monographs, 81*(1), 28-58. https://doi.org/10.1080/03637751.2013.813632
18. Williams, K. D., Shore, W. J., & Grahe, J. E. (1998). The silent treatment: Perceptions of its behaviors and associated feelings. *Group Processes & Intergroup Relations, 1*(2), 117-141. https://doi.org/10.1177/1368430298012002
19. Williams, K. D. (2009). Ostracism: A temporal need-threat model. *Advances in Experimental Social Psychology, 41*, 275-314. https://doi.org/10.1016/S0065-2601(08)00406-1
20. McCullough, M. E., Worthington, E. L., Jr., & Rachal, K. C. (1997). Interpersonal forgiving in close relationships. *Journal of Personality and Social Psychology, 73*(2), 321-336. https://doi.org/10.1037/0022-3514.73.2.321
21. Fehr, R., Gelfand, M. J., & Nag, M. (2010). The road to forgiveness: A meta-analytic synthesis of its situational and dispositional correlates. *Psychological Bulletin, 136*(5), 894-914. https://doi.org/10.1037/a0019993
22. Lewicki, R. J., Polin, B., & Lount, R. B., Jr. (2016). An exploration of the structure of effective apologies. *Negotiation and Conflict Management Research, 9*(2), 177-196. https://doi.org/10.1111/ncmr.12073
23. Ohbuchi, K., Kameda, M., & Agarie, N. (1989). Apology as aggression control: Its role in mediating appraisal of and response to harm. *Journal of Personality and Social Psychology, 56*(2), 219-227. https://doi.org/10.1037/0022-3514.56.2.219
24. Digman, J. M. (1990). Personality structure: Emergence of the five-factor model. *Annual Review of Psychology, 41*, 417-440. https://doi.org/10.1146/annurev.ps.41.020190.002221
25. Goldberg, L. R. (1990). An alternative description of personality: The Big-Five factor structure. *Journal of Personality and Social Psychology, 59*(6), 1216-1229. https://doi.org/10.1037/0022-3514.59.6.1216
26. McCrae, R. R., & Costa, P. T. (1987). Validation of the five-factor model of personality across instruments and observers. *Journal of Personality and Social Psychology, 52*(1), 81-90. https://doi.org/10.1037/0022-3514.52.1.81
27. Ashton, M. C., & Lee, K. (2007). Empirical, theoretical, and practical advantages of the HEXACO model of personality structure. *Personality and Social Psychology Review, 11*(2), 150-166. https://doi.org/10.1177/1088868306294907
28. DeYoung, C. G., Quilty, L. C., & Peterson, J. B. (2007). Between facets and domains: 10 aspects of the Big Five. *Journal of Personality and Social Psychology, 93*(5), 880-896. https://doi.org/10.1037/0022-3514.93.5.880
29. DeYoung, C. G. (2015). Cybernetic Big Five Theory. *Journal of Research in Personality, 56*, 33-58. https://doi.org/10.1016/j.jrp.2014.07.004
30. Fleeson, W. (2001). Toward a structure- and process-integrated view of personality: Traits as density distributions of states. *Journal of Personality and Social Psychology, 80*(6), 1011-1027. https://doi.org/10.1037/0022-3514.80.6.1011
31. Mischel, W., & Shoda, Y. (1995). A cognitive-affective system theory of personality. *Psychological Review, 102*(2), 246-268. https://doi.org/10.1037/0033-295X.102.2.246
32. Carver, C. S., & White, T. L. (1994). Behavioral inhibition, behavioral activation, and affective responses to impending reward and punishment. *Journal of Personality and Social Psychology, 67*(2), 319-333. https://doi.org/10.1037/0022-3514.67.2.319
33. Webster, D. M., & Kruglanski, A. W. (1994). Individual differences in need for cognitive closure. *Journal of Personality and Social Psychology, 67*(6), 1049-1062. https://doi.org/10.1037/0022-3514.67.6.1049
34. Fraley, R. C., Waller, N. G., & Brennan, K. A. (2000). An item-response theory analysis of self-report measures of adult attachment. *Journal of Personality and Social Psychology, 78*(2), 350-365. https://doi.org/10.1037/0022-3514.78.2.350
35. Gross, J. J., & John, O. P. (2003). Individual differences in two emotion regulation processes: Implications for affect, relationships, and well-being. *Journal of Personality and Social Psychology, 85*(2), 348-362. https://doi.org/10.1037/0022-3514.85.2.348
36. Sacks, H., Schegloff, E. A., & Jefferson, G. (1974). A simplest systematics for the organization of turn-taking for conversation. *Language, 50*(4), 696-735. https://doi.org/10.2307/412243
37. Clark, H. H., & Brennan, S. E. (1991). Grounding in communication. In L. B. Resnick, J. M. Levine, & S. D. Teasley (Eds.), *Perspectives on Socially Shared Cognition* (pp. 127-149). American Psychological Association.
38. Vinciarelli, A., Pantic, M., & Bourlard, H. (2009). Social signal processing: Survey of an emerging domain. *Image and Vision Computing, 27*(12), 1743-1759. https://doi.org/10.1016/j.imavis.2008.11.007
39. Barsade, S. G. (2002). The ripple effect: Emotional contagion and its influence on group behavior. *Administrative Science Quarterly, 47*(4), 644-675. https://doi.org/10.2307/3094912
40. Kendon, A. (1967). Some functions of gaze-direction in social interaction. *Acta Psychologica, 26*, 22-63. https://doi.org/10.1016/0001-6918(67)90005-4
41. Short, J., Williams, E., & Christie, B. (1976). *The Social Psychology of Telecommunications*. Wiley.
42. Ebbinghaus, H. (1913). *Memory: A Contribution to Experimental Psychology* (H. A. Ruger & C. E. Bussenius, Trans.). Teachers College, Columbia University. Original work published 1885.
43. Tulving, E. (1972). Episodic and semantic memory. In E. Tulving & W. Donaldson (Eds.), *Organization of Memory* (pp. 381-403). Academic Press.
44. Anderson, J. R., & Schooler, L. J. (1991). Reflections of the environment in memory. *Psychological Science, 2*(6), 396-408. https://doi.org/10.1111/j.1467-9280.1991.tb00174.x
45. Anderson, J. R., Bothell, D., Byrne, M. D., Douglass, S., Lebiere, C., & Qin, Y. (2004). An integrated theory of the mind. *Psychological Review, 111*(4), 1036-1060. https://doi.org/10.1037/0033-295X.111.4.1036
46. Bjork, R. A., & Bjork, E. L. (1992). A new theory of disuse and an old theory of stimulus fluctuation. In A. Healy, S. Kosslyn, & R. Shiffrin (Eds.), *From Learning Processes to Cognitive Processes: Essays in Honor of William K. Estes* (Vol. 2, pp. 35-67). Erlbaum.
47. McClelland, J. L., McNaughton, B. L., & O'Reilly, R. C. (1995). Why there are complementary learning systems in the hippocampus and neocortex. *Psychological Review, 102*(3), 419-457. https://doi.org/10.1037/0033-295X.102.3.419
48. Schacter, D. L. (1999). The seven sins of memory: Insights from psychology and cognitive neuroscience. *American Psychologist, 54*(3), 182-203. https://doi.org/10.1037/0003-066X.54.3.182
49. Park, J. S., O'Brien, J. C., Cai, C. J., Morris, M. R., Liang, P., & Bernstein, M. S. (2023). Generative agents: Interactive simulacra of human behavior. *Proceedings of the 36th Annual ACM Symposium on User Interface Software and Technology*. https://doi.org/10.1145/3586183.3606763
50. Karpukhin, V., Oguz, B., Min, S., Lewis, P., Wu, L., Edunov, S., Chen, D., & Yih, W. (2020). Dense passage retrieval for open-domain question answering. *Proceedings of EMNLP 2020*, 6769-6781. https://doi.org/10.18653/v1/2020.emnlp-main.550
51. Reimers, N., & Gurevych, I. (2019). Sentence-BERT: Sentence embeddings using Siamese BERT-networks. *Proceedings of EMNLP-IJCNLP 2019*, 3982-3992. https://doi.org/10.18653/v1/D19-1410
52. Johnson, J., Douze, M., & Jegou, H. (2019). Billion-scale similarity search with GPUs. *IEEE Transactions on Big Data, 7*(3), 535-547. https://doi.org/10.1109/TBDATA.2019.2921572
