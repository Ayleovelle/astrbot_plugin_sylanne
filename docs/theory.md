# 多维情绪状态模型：理论说明

## 重点版

默认阅读只需要抓住这条链路：

1. 情绪状态不是单一标签，而是受人格 `P` 调制的有界连续向量 `E_t(P) in [-1,1]^n`。
2. `V/A/D` 继承 PAD 与 circumplex affect 的连续维度思想；`G/C/K/S` 引入 appraisal theory 对目标一致性、确定性、可控性和社交亲近的评价。
3. LLM 负责把上下文解释成即时观测 `X_t` 与 appraisal；本地引擎负责真实时间半衰期、惯性、限幅和关系后果。
4. 长期状态更新可视为在“上一状态/人格基线先验”与“当前观测”之间求二次优化折中，最终得到 `E'_t = B_t + alpha_t(X_t-B_t)`。
5. 冷处理、修复、边界、求证等不是情绪标签本身，而是由 `O_t` 表示的后果状态，并按真实时间衰减。

| 设计点 | 默认结论 | 顶刊/高影响依据 |
| --- | --- | --- |
| 连续情绪向量 | 用多维连续状态替代离散情绪标签。 | Russell 1980, *Journal of Personality and Social Psychology*；Mehrabian & Russell 1974。 |
| appraisal 扩展维度 | 目标、责任、控制、确定性会改变情绪意义。 | Scherer 2005, *Social Science Information*；Roseman 1991, *Cognition and Emotion*；OCC。 |
| 情绪惯性 | 单轮文本不能完全重写长期状态。 | Kuppens, Allen & Sheeber 2010, *Psychological Science*；Gross 1998, *Review of General Psychology*。 |
| 行动倾向 | 生气可能走对抗、边界、修复或求证，不必然冷战。 | Frijda et al. 1989, *Journal of Personality and Social Psychology*；Carver & Harmon-Jones 2009, *Psychological Bulletin*。 |
| 关系修复 | 承认、道歉、补救、误读和反复犯错共同决定是否原谅或冷处理。 | McCullough et al. 1997, *Journal of Personality and Social Psychology*；Fehr et al. 2010, *Psychological Bulletin*；Ohbuchi et al. 1989, *Journal of Personality and Social Psychology*。 |

<details>
<summary>展开完整理论论证、公式推导与参考文献</summary>

## 1. 建模边界

本插件把情绪定义为 bot 的“计算性调制状态”，不把他/她等同于真实主观体验。形式上，情绪状态是一个有界连续向量，并被当前人格 `P` 调制：

```math
E_t(P) \in [-1, 1]^n,\qquad n \ge 3
```

默认 `n = 7`：

```math
E_t =
\begin{bmatrix}
V_t & A_t & D_t & G_t & C_t & K_t & S_t
\end{bmatrix}^{\mathsf T}
```

其中 `V/A/D` 对应 PAD 与环形情感模型中的效价、唤醒、支配感；`G/C/K/S` 分别表示目标一致性、确定性、可控性与社交亲近度，对应 appraisal theory 与 OCC 中对事件、行动者和对象的认知评价。

## 2. 输入与建模假设

设 LLM 读到的对话信息为：

```math
I_t = \{H_t, U_t, P, E_{t-1}\}
```

其中 `H_t` 是上下文，`U_t` 是当前输入或 bot 当前回复，`P` 是当前 AstrBot persona，`E_{t-1}` 是上一轮平滑状态。插件把 persona 当作情绪评价的先验，而不是只当作输出文风。

## 3. 人格量化画像到情绪先验

同一句用户文本对不同人格的意义不同。`0.1.0-beta` 不再只用少量风格关键词做人格偏置，而是生成一个版本化、可公开读取、可持久化的 13 维潜在人格先验。该先验仍然不是临床人格测量；它只把 AstrBot persona 文本转成工程参数，让不同 bot 的情绪基线、反应强度、边界敏感度、修复倾向和社交距离稳定可复现。

插件先从 persona 中构造输入集合：

```math
P = \{\mathrm{persona\_id}, \mathrm{name}, \mathrm{system\_prompt}, \mathrm{begin\_dialogs}\}
```

公开 schema 常量为 `PUBLIC_PERSONALITY_PROFILE_SCHEMA_VERSION`，当前版本为：

```math
\mathrm{PUBLIC\_PERSONALITY\_PROFILE\_SCHEMA\_VERSION}
=\mathrm{astrbot.personality\_profile.v1}
```

潜在人格向量为：

```math
q_p =
\begin{bmatrix}
O & N & X & A & L & H & R_a & R_v & I & B & F & U & W_s
\end{bmatrix}^{\mathsf T}
```

各维含义如下：

| 维度 | 含义 | 工程作用 |
| --- | --- | --- |
| `O` | openness | 新奇性、表达弹性、对模糊语义的开放度。 |
| `N` | conscientiousness | 稳定履约、规则遵守、长期目标一致性。 |
| `X` | extraversion | 靠近倾向、表达能量、社交恢复速度。 |
| `A` | agreeableness | 修复、让步、合作和低敌意倾向。 |
| `L` | neuroticism | 负性反应性、情绪波动和受伤敏感度。 |
| `H` | honesty-humility | 信任修复、内疚、责任承认和道德姿态。 |
| `R_a` | attachment anxiety | 被抛弃/被误解敏感度和确认需求。 |
| `R_v` | attachment avoidance | 距离、回避、冷处理和依赖抑制倾向。 |
| `I` | BIS sensitivity | 威胁监测、谨慎、防御和风险规避。 |
| `B` | BAS drive | 目标追求、靠近、主动解决和奖励敏感度。 |
| `F` | need for closure | 确定性需求、规则偏好和模糊容忍度。 |
| `U` | emotion-regulation capacity | 再评价、克制、恢复和冲动抑制。 |
| `W_s` | interpersonal warmth | 亲和、照顾、共情和靠近修复。 |

人格画像来自三类不完美证据：persona 文本词汇指示、旧版工程 trait、结构先验。设多源观测为：

```math
y =
\begin{bmatrix}
y_{\mathrm{lex}} & y_{\mathrm{legacy}} & y_{\mathrm{struct}}
\end{bmatrix}^{\mathsf T}
```

令 `M` 为观测到潜在 trait 的投影矩阵，`R` 为来源可靠性对角权重，`mu` 和 `Sigma` 是保守先验。插件采用可靠性加权、先验收缩的二次目标：

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

得到闭式后验：

```math
q_p = \left(M^{\mathsf T}RM+\lambda\Sigma^{-1}\right)^{-1}
\left(M^{\mathsf T}Ry+\lambda\Sigma^{-1}\mu\right)
```

后验方差近似为：

```math
V_q = \left(M^{\mathsf T}RM+\lambda\Sigma^{-1}\right)^{-1}
```

运行时为了保持轻量、确定性和无外部数值依赖，采用对角近似：

```math
q_i = \frac{\sum_j r_j y_{j,i}+\lambda\mu_i}{\sum_j r_j+\lambda}
```

```math
\mathrm{var}_i = \frac{1}{\sum_j r_j+\lambda}
```

然后生成两类人格先验：

```math
b_p = h_b(P), \qquad \theta_p = h_\theta(P)
```

`b_p` 是当前人格的稳定情绪基线；`theta_p` 是动力学参数偏置，包括基础更新步长、基线回归速度、反应强度、惊讶度到唤醒度的耦合强度等。

映射形式为：

```math
b_p = \Pi_{[-1,1]^7}(b_0+Bq_p)
```

```math
\theta_p = \Pi_{[0.55,1.55]^m}(\theta_0+Cq_p)
```

其中 `Pi` 表示投影限幅，避免 persona 文本把情绪基线或动力学参数推到不稳定区间。再从 `q_p` 派生高层人格因子：

```math
\begin{aligned}
\mathrm{instability}_p &= a_1L+a_2R_a+a_3I-a_4U,\\
\mathrm{distance}_p &= a_5R_v-a_6W_s-a_7X,\\
\mathrm{repair}_p &= a_8A+a_9H+a_{10}U-a_{11}R_v,\\
\mathrm{boundary}_p &= a_{12}I+a_{13}F+a_{14}N-a_{15}A.
\end{aligned}
```

这四个派生因子分别调制负性持久性、冷处理/保持距离、道歉修复和边界反应。随后 LLM 仍会基于完整 persona 文本进行 appraisal 判断；人格后验只负责稳定先验，语义解释仍交给 LLM。公共 payload 只暴露 `schema_version`、`trait_scores`、`trait_confidence`、`posterior_variance`、`source_reliability` 和 `derived_factors`，不会暴露 raw persona text。

证据边界如下：Big Five 高阶 trait 空间由 Digman 1990、Goldberg 1990 和 McCrae & Costa 1987 支撑；HEXACO 的 honesty-humility 由 Ashton & Lee 2007 支撑；trait 作为状态分布和情境 if-then 模式分别由 Fleeson 2001 与 Mischel & Shoda 1995 支撑；BIS/BAS 由 Carver & White 1994 支撑；need for closure 由 Webster & Kruglanski 1994 支撑；依恋焦虑/回避由 Fraley、Waller & Brennan 2000 支撑；情绪调节差异由 Gross & John 2003 支撑。`personality_literature_kb/evidence-map.md` 中 `PERS-F001` 到 `PERS-F012` 固定为 verified DOI metadata 级 foundational sources；其他 19196 条去重候选是 metadata/abstract-level 自动检索记录，不声称全文精读。

## 4. 从认知评价到维度观测

在理论上，可把 LLM 的情绪判断拆成一个隐藏的认知评价向量：

```math
Z_t =
\begin{bmatrix}
z_{\mathrm{goal}} & z_{\mathrm{novelty}} & z_{\mathrm{agency}} &
z_{\mathrm{control}} & z_{\mathrm{certainty}} & z_{\mathrm{norm}} &
z_{\mathrm{social}}
\end{bmatrix}^{\mathsf T}
```

评价函数为：

```math
Z_t = \phi_{\mathrm{llm}}(I_t)
```

再通过有界映射得到即时情绪观测：

```math
X_t = \tanh(WZ_t+\beta)
```

插件没有显式训练 `W`，而是让 LLM 直接输出 `X_t` 和 `appraisal`。这样做的工程意义是：LLM 负责语义评价，插件负责状态动力学。换句话说，LLM 判断“发生了什么、对 bot 意味着什么”，情绪引擎判断“这种意义应该如何改变长期状态”。

## 5. 状态更新的优化推导

如果直接令：

```math
E_t = X_t
```

状态会被单轮文本完全支配，表现为情绪跳变。插件改为求解一个带惯性的加权最小化问题：

```math
E_t = \arg\min_{E} J(E)
```

其中：

```math
J(E) =
(1-\alpha_t)\|E-B_t\|_W^2
+ \alpha_t\|E-X_t\|_W^2
```

`B_t` 是上一状态经基线回归后的先验：

```math
B_t=(1-\gamma_p)E_{t-1}+\gamma_p b_p
```

```math
\gamma_p(\Delta t)=1-2^{-\Delta t/H_p}
```

`b_p` 是当前人格稳定基线，`H_p` 是被人格调制后的真实时间恢复半衰期，`W = diag(w_1, ..., w_n)` 是维度权重矩阵。`gamma_p` 不再随消息轮数固定推进，而是只由真实经过时间 `Δt` 决定，因此连续刷入大量文本不能把情绪强行刷回基线。

对 `J(E)` 求导：

```math
\frac{\partial J}{\partial E}
=2(1-\alpha_t)W(E-B_t)+2\alpha_t W(E-X_t)
```

令导数为零：

```math
(1-\alpha_t)W(E-B_t)+\alpha_t W(E-X_t)=0
```

若 `W` 正定，则可消去 `W`：

```math
(1-\alpha_t)(E-B_t)+\alpha_t(E-X_t)=0
```

整理得：

```math
E'_t=B_t+\alpha_t(X_t-B_t)
```

这说明指数平滑并不是随意拼公式，而是“保持情绪惯性”和“接纳当前观测”之间的二次优化解。

## 6. 自适应步长

更新步长不能固定。插件令：

```math
\alpha_t =
\mathrm{clamp}\left(
\alpha_{\mathrm{base},p}g(c_t)(1+r_p\delta_t),
\alpha_{\min},
\alpha_{\max}
\right)
```

其中置信门控为：

```math
g(c_t)=\frac{1}{1+\exp[-k(c_t-c_0)]}
```

`c_t` 来自 LLM 输出的置信度。低置信观测只轻微改变状态，高置信观测才获得更大权重。

`delta_t` 是加权惊讶度：

```math
\delta_t =
\sqrt{
\frac{(X_t-B_t)^{\mathsf T}W(X_t-B_t)}
{\mathrm{tr}(W)}
}
```

`alpha_base,p` 和 `r_p` 来自 `theta_p`。当观测和先验差异很大时，事件可能具有突发性或高显著性，所以 `alpha_t` 被适度放大；但 `clamp` 保证不会无限放大。

## 7. 维度耦合

PAD 与 appraisal 维度并非完全独立。插件只加入两个弱耦合项，避免模型过拟合或变得不可解释。

惊讶度提升唤醒度：

```math
A_t=A'_t+\eta\alpha_t\delta_t(1-|A'_t|)
```

当唤醒度已经接近 `-1` 或 `1` 时，`1 - |A'_t|` 会自动减小，避免越界。

可控性牵引支配感：

```math
D_t=D'_t+\lambda\alpha_t(K'_t-D'_t)
```

`K_t` 是 control。一个局面越可控，bot 越可能表现得坚定；局面越不可控，bot 越可能迟疑、防御或退让。但 `lambda` 很小，所以支配感不会被可控性完全替代。

最终做投影：

```math
E_t=\Pi_{[-1,1]^n}(E_t)
```

其中 `Pi` 是逐维裁剪。

## 8. 情绪后果与行动倾向

情绪状态并不直接等于回复模板。参考 Frijda 的 action readiness / action tendency 思路，插件把情绪状态再映射到后果状态：

```math
O_t =
\begin{bmatrix}
\mathrm{approach} & \mathrm{withdrawal} & \mathrm{confrontation} &
\mathrm{appeasement} & \mathrm{repair} & \mathrm{reassurance} &
\mathrm{caution} & \mathrm{rumination} & \mathrm{expressiveness} &
\mathrm{problem\_solving}
\end{bmatrix}^{\mathsf T}
```

`O_t` 不是瞬时标签，而是会随真实时间衰减的持续状态：

```math
O_t = 2^{-\Delta t/H_o}O_{t-1}+\mathrm{impulse}(E_t,X_t,\mathrm{appraisal}_t)
```

其中 `H_o` 是后果强度半衰期，`impulse` 同时参考平滑后的长期情绪 `E_t` 与 LLM 即时观测 `X_t`。这样强烈刺激可以立刻留下后果，而长期状态又能决定这种后果是否持续；由于衰减项只使用 `Δt`，大量消息轮次不会快速消耗后果记忆。`cold_war` 等 active effect 使用 `expires_at` 时间戳保存剩余时长。

维度对后果的作用：

```text
negative valence -> withdrawal / confrontation / repair
high arousal -> expressiveness and urgency
high dominance -> confrontation and boundary setting
low dominance -> appeasement or reassurance
low goal_congruence -> frustration, complaint, cold distance
low certainty -> caution and clarification
low control -> withdrawal or shutdown
high affiliation -> repair and warm approach
low affiliation -> cold distance or rejection
```

复合规则示例：

```math
\begin{aligned}
\mathrm{anger\_push} &= \mathrm{combo}(-V,A,D,\max(-G,C)),\\
\mathrm{cold\_war} &= \mathrm{combo}(-V,-A,-S,\max(-K,-G)),\\
\mathrm{anxious\_withdraw} &= \mathrm{combo}(-V,A,-D,-K),\\
\mathrm{repair} &= \mathrm{combo}(-V,S,\max(K,0.25),1-\mathrm{uncertainty\_penalty}).
\end{aligned}
```

这里 `C` 是 certainty 的当前标量分量，`combo` 使用“瓶颈维度 + 平均强度”的组合方式，而不是单纯连乘。原因是连乘会过度保守，导致强烈情绪也难以触发后果；瓶颈项确保必要条件存在，平均项确保整体强度被保留。

公式层给出默认行动倾向，LLM appraisal 层再给出关系决策：

```math
R_t = \mathrm{relationship\_decision}_{\mathrm{llm}}(I_t)
```

```math
R_t.\mathrm{decision}
\in \{\mathrm{forgive},\mathrm{repair},\mathrm{boundary},\mathrm{cold\_war},\mathrm{escalate},\mathrm{none}\}
```

`forgive` 会清除或缩短冷处理，降低 `withdrawal/confrontation/rumination`，并提高 `repair/approach/problem_solving`；`cold_war` 会延长冷处理并提高回避与反刍；`boundary` 只增强边界表达，不自动触发冷战。这样，生气后的走向由“维度公式 + LLM 关系判断”共同决定，而不是简单地把所有负面情绪都推向冷战。

进一步地，插件让 LLM 输出冲突成因分析：

```math
F_t = \mathrm{conflict\_analysis}_{\mathrm{llm}}(I_t)
```

```math
F_t.\mathrm{cause}
\in \{\mathrm{user\_fault},\mathrm{bot\_whim},\mathrm{bot\_misread},\mathrm{mutual},\mathrm{external},\mathrm{none}\}
```

`fault_severity`、`repeat_offense` 会放大边界和冷处理倾向；`user_acknowledged`、`apology_sincerity`、`repaired`、`repair_quality` 会促进原谅和修复；`bot_whim_level` 或 `bot_misread` 会抑制对用户的惩罚性后果，使状态转向求证、修复或自我缓和。因此，同样是生气，若原因是用户反复犯错且没有补救，后果会更接近边界/冷处理；若原因主要是他/她任性或误读，后果会更接近修复和谨慎核对。

工程上，插件把冲突分析进一步压缩成三个派生量：

```math
\mathrm{repair\_signal}_t =
\max\left(
\mathrm{apology\_sincerity}_t\mathrm{1}_{\mathrm{user\_acknowledged}_t},
\mathrm{repair\_quality}_t\mathrm{1}_{\mathrm{repaired}_t}
\right)
```

```math
\mathrm{grievance}_t =
\mathrm{clip}\left(
\mathrm{fault\_severity}_t(1-\mathrm{repair\_signal}_t)
+0.35\,\mathrm{repeat\_offense}_t,\;0,\;1
\right)
```

```math
\mathrm{self\_correction}_t =
\max\left(
\mathrm{bot\_whim\_level}_t\mathrm{1}_{\mathrm{cause}\in\{\mathrm{bot\_whim},\mathrm{bot\_misread}\}},
\mathrm{repair\_signal}_t\mathrm{1}_{\mathrm{cause}\in\{\mathrm{user\_fault},\mathrm{mutual}\}}
\right)
```

这里 `clip(x,0,1)` 表示把 `x` 限制在 `[0,1]` 区间；`\mathrm{1}_{condition}` 是指示函数，条件成立取 `1`，否则取 `0`。`repair_signal_t` 对应“错误是否被承认并改正”；`grievance_t` 对应剩余的合理委屈或边界需求；`self_correction_t` 对应他/她该软化的强度。派生的 `repair_status` 按 `unresolved -> acknowledged -> apologized -> repaired -> restored` 分级，使其他插件不必重新解释 LLM 原始 JSON。若 LLM 没有显式给出 `relationship_decision`，`conflict_analysis` 仍会通过这些派生量影响 `O_t`，避免冲突原因只停留在解释文本中。

文献知识库扩充后，`F_t` 还包含更细的归因和关系修复字段：

```text
intent_t      = perceived_intentionality_t
avoid_t       = controllability_t
trust_t       = trust_damage_t
amb_t         = ambiguity_level_t
misread_t     = misread_likelihood_t
forgive_t     = forgiveness_readiness_t
residue_t     = resentment_residue_t
boundary_t    = boundary_legitimacy_t
regload_t     = emotion_regulation_load_t
```

更新后的剩余委屈近似为：

```math
\begin{aligned}
\mathrm{grievance}_t
= \mathrm{clip}(&
0.55\,\mathrm{fault\_severity}_t
+0.18\,\mathrm{intent}_t
+0.16\,\mathrm{avoid}_t
+0.16\,\mathrm{trust}_t\\
&+0.12\,\mathrm{face\_threat}_t
+0.10\,\mathrm{expectation\_violation}_t
+0.16\,\mathrm{boundary}_t\\
&+0.20\,\mathrm{repeat\_offense}_t
+0.14\,\mathrm{residue}_t
-0.40\,\mathrm{repair\_signal}_t\\
&-0.24\,\mathrm{forgive}_t
-0.30\,\mathrm{misread}_t
-0.18\,\mathrm{amb}_t,\;0,\;1).
\end{aligned}
```

因此，用户确实反复犯错、意图明显、信任损伤较高时，边界与谨慎会更强；但如果语义模糊或他/她可能误读，则 confrontation 和 cold_war 会被压低，转向 `careful_checking` 与 `repair`。这来自 appraisal theory 中对责任、意图、可控性和确定性的强调，也与宽恕、道歉完整性、demand-withdraw 和 ostracism 文献相符。`evidence.primary_theory`、`citation_ids` 和 `evidence_strength` 只记录解释依据，不直接提高置信度或放大情绪强度。

冷战或冷处理在插件中被定义为一种可持续衰减的“后果状态”，通常对应降频、短句、保持距离或更强边界感。若配置项 `enable_safety_boundary` 开启，注入 prompt 会额外限制他/她不能表现为羞辱、威胁、操控或拒绝必要帮助；若关闭，则插件只输出情绪后果本身，让上层人格或其他插件自行决定表现边界。若 `repair`、`reassurance` 或 `problem_solving` 同时较高，回复会优先走修复、求证或解决问题。

## 9. 稳定性

若 `alpha_t in [0, 1]`、`gamma_p(Δt) in [0, 1]`，且 `E_{t-1}, X_t, b_p` 都在 `[-1, 1]^n`，则 `B_t` 与 `E'_t` 都是有界向量的凸组合。因此，在耦合项较小且最后投影到 `[-1, 1]^n` 的条件下：

```math
E_t \in [-1,1]^n
```

若长期没有强刺激，且 `X_t` 接近人格基线 `b_p`，则状态会因基线回归和指数平滑收敛到 `b_p` 附近。这对应情绪动力学中的 emotional inertia：状态既会持续，又会随新评价缓慢改变。

## 10. 参考文献

1. Mehrabian, A., & Russell, J. A. (1974). *An Approach to Environmental Psychology*. MIT Press.
2. Mehrabian, A., & Russell, J. A. (1974). The basic emotional impact of environments. *Perceptual and Motor Skills, 38*(1), 283-301. https://doi.org/10.2466/pms.1974.38.1.283
3. Russell, J. A. (1980). A circumplex model of affect. *Journal of Personality and Social Psychology, 39*(6), 1161-1178. https://doi.org/10.1037/h0077714
4. Ortony, A., Clore, G. L., & Collins, A. (1988). *The Cognitive Structure of Emotions*. Cambridge University Press. https://doi.org/10.1017/CBO9780511571299
5. Lazarus, R. S. (1991). *Emotion and Adaptation*. Oxford University Press. https://doi.org/10.1093/oso/9780195069945.001.0001
6. Scherer, K. R., Schorr, A., & Johnstone, T. (Eds.). (2001). *Appraisal Processes in Emotion: Theory, Methods, Research*. Oxford University Press. https://doi.org/10.1093/oso/9780195130072.001.0001
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

</details>
