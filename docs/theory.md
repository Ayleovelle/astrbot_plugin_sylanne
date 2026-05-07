# 多维情绪状态模型：理论说明

## 1. 建模边界

本插件把情绪定义为 bot 的“计算性调制状态”，不把他/她等同于真实主观体验。形式上，情绪状态是一个有界连续向量，并被当前人格 `P` 调制：

```math
E_t(P) \in [-1, 1]^n,\qquad n \ge 3
```

默认 `n = 7`：

```math
E_t =
\begin{bmatrix}
V_t & A_t & D_t & G_t & Q_t & K_t & S_t
\end{bmatrix}^{\mathsf T}
```

其中 `V/A/D` 对应 PAD 与环形情感模型中的效价、唤醒、支配感；`G/Q/K/S` 分别表示目标一致性、确定性、可控性与社交亲近度，对应 appraisal theory 与 OCC 中对事件、行动者和对象的认知评价。

## 2. 从认知评价到维度观测

设 LLM 读到的对话信息为：

```math
I_t = \{C_t, U_t, P, E_{t-1}\}
```

其中 `C_t` 是上下文，`U_t` 是当前输入或 bot 当前回复，`P` 是当前 AstrBot persona，`E_(t-1)` 是上一轮平滑状态。插件把 persona 当作情绪评价的先验，而不是只当作输出文风。

## 3. 人格画像到情绪先验

同一句用户文本对不同人格的意义不同。插件先从 persona 中构造画像：

```math
P = \{\mathrm{persona\_id}, \mathrm{name}, \mathrm{system\_prompt}, \mathrm{begin\_dialogs}\}
```

再生成两类人格先验：

```math
b_p = h_b(P), \qquad \theta_p = h_\theta(P)
```

`b_p` 是当前人格的稳定情绪基线；`theta_p` 是动力学参数偏置，包括基础更新步长、基线回归速度、反应强度、惊讶度到唤醒度的耦合强度等。

工程实现上，插件使用确定性的 trait extractor 从 persona 文本中估计若干人格特征：

```math
T_p =
\begin{bmatrix}
\mathrm{warmth} & \mathrm{shyness} & \mathrm{assertiveness} & \mathrm{volatility} &
\mathrm{calmness} & \mathrm{optimism} & \mathrm{pessimism} & \mathrm{dutifulness}
\end{bmatrix}^{\mathsf T}
```

然后把这些特征映射到 `b_p` 与 `theta_p`。例如：

```math
\begin{aligned}
\mathrm{affiliation}_b
&= \mathrm{affiliation}_0 + a_1\mathrm{warmth} + a_2\mathrm{optimism} - a_3\mathrm{pessimism},\\
\mathrm{dominance}_b
&= \mathrm{dominance}_0 + a_4\mathrm{assertiveness} - a_5\mathrm{shyness},\\
\mathrm{reactivity}_p
&= \mathrm{reactivity}_0\left(1+a_6\mathrm{volatility}+a_7\mathrm{shyness}-a_8\mathrm{calmness}\right).
\end{aligned}
```

这种设计的目的不是给人格做临床心理测量，而是在工程上让不同 bot 拥有不同的情绪“默认姿态”和“受刺激后的变化方式”。随后 LLM 仍会基于完整 persona 文本进行 appraisal 判断，因此 deterministic trait 只负责稳定先验，语义解释仍交给 LLM。

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
E_t = \underset{E}{\arg\min}\;J(E)
```

其中：

```math
J(E) =
(1-\alpha_t)\lVert E-B_t\rVert_W^2
+ \alpha_t\lVert E-X_t\rVert_W^2
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
\operatorname{clamp}\left(
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
{\operatorname{tr}(W)}
}
```

`alpha_base,p` 和 `r_p` 来自 `theta_p`。当观测和先验差异很大时，事件可能具有突发性或高显著性，所以 `alpha_t` 被适度放大；但 `clamp` 保证不会无限放大。

## 7. 维度耦合

PAD 与 appraisal 维度并非完全独立。插件只加入两个弱耦合项，避免模型过拟合或变得不可解释。

惊讶度提升唤醒度：

```math
A_t=A'_t+\eta\alpha_t\delta_t(1-\lvert A'_t\rvert)
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
Q_t =
\begin{bmatrix}
\mathrm{approach} & \mathrm{withdrawal} & \mathrm{confrontation} &
\mathrm{appeasement} & \mathrm{repair} & \mathrm{reassurance} &
\mathrm{caution} & \mathrm{rumination} & \mathrm{expressiveness} &
\mathrm{problem\_solving}
\end{bmatrix}^{\mathsf T}
```

`Q_t` 不是瞬时标签，而是会随真实时间衰减的持续状态：

```math
Q_t = 2^{-\Delta t/H_q}Q_{t-1}+\operatorname{impulse}(E_t,X_t,\mathrm{appraisal}_t)
```

其中 `H_q` 是后果强度半衰期，`impulse` 同时参考平滑后的长期情绪 `E_t` 与 LLM 即时观测 `X_t`。这样强烈刺激可以立刻留下后果，而长期状态又能决定这种后果是否持续；由于衰减项只使用 `Δt`，大量消息轮次不会快速消耗后果记忆。`cold_war` 等 active effect 使用 `expires_at` 时间戳保存剩余时长。

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
\mathrm{anger\_push} &= \operatorname{combo}(-V,A,D,\max(-G,C)),\\
\mathrm{cold\_war} &= \operatorname{combo}(-V,-A,-S,\max(-K,-G)),\\
\mathrm{anxious\_withdraw} &= \operatorname{combo}(-V,A,-D,-K),\\
\mathrm{repair} &= \operatorname{combo}(-V,S,\max(K,0.25),1-\mathrm{uncertainty\_penalty}).
\end{aligned}
```

这里 `combo` 使用“瓶颈维度 + 平均强度”的组合方式，而不是单纯连乘。原因是连乘会过度保守，导致强烈情绪也难以触发后果；瓶颈项确保必要条件存在，平均项确保整体强度被保留。

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
C_t = \mathrm{conflict\_analysis}_{\mathrm{llm}}(I_t)
```

```math
C_t.\mathrm{cause}
\in \{\mathrm{user\_fault},\mathrm{bot\_whim},\mathrm{bot\_misread},\mathrm{mutual},\mathrm{external},\mathrm{none}\}
```

`fault_severity`、`repeat_offense` 会放大边界和冷处理倾向；`user_acknowledged`、`apology_sincerity`、`repaired`、`repair_quality` 会促进原谅和修复；`bot_whim_level` 或 `bot_misread` 会抑制对用户的惩罚性后果，使状态转向求证、修复或自我缓和。因此，同样是生气，若原因是用户反复犯错且没有补救，后果会更接近边界/冷处理；若原因主要是他/她任性或误读，后果会更接近修复和谨慎核对。

工程上，插件把冲突分析进一步压缩成三个派生量：

```math
\mathrm{repair\_signal}_t =
\max\left(
\mathrm{apology\_sincerity}_t\mathbf 1[\mathrm{user\_acknowledged}_t],
\mathrm{repair\_quality}_t\mathbf 1[\mathrm{repaired}_t]
\right)
```

```math
\mathrm{grievance}_t =
\operatorname{clip}\left(
\mathrm{fault\_severity}_t(1-\mathrm{repair\_signal}_t)
+0.35\,\mathrm{repeat\_offense}_t,\;0,\;1
\right)
```

```math
\mathrm{self\_correction}_t =
\max\left(
\mathrm{bot\_whim\_level}_t\mathbf 1[\mathrm{cause}\in\{\mathrm{bot\_whim},\mathrm{bot\_misread}\}],
\mathrm{repair\_signal}_t\mathbf 1[\mathrm{cause}\in\{\mathrm{user\_fault},\mathrm{mutual}\}]
\right)
```

`repair_signal_t` 对应“错误是否被承认并改正”；`grievance_t` 对应剩余的合理委屈或边界需求；`self_correction_t` 对应他/她该软化的强度。派生的 `repair_status` 按 `unresolved -> acknowledged -> apologized -> repaired -> restored` 分级，使其他插件不必重新解释 LLM 原始 JSON。若 LLM 没有显式给出 `relationship_decision`，`conflict_analysis` 仍会通过这些派生量影响 `Q_t`，避免冲突原因只停留在解释文本中。

文献知识库扩充后，`C_t` 还包含更细的归因和关系修复字段：

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
= \operatorname{clip}(&
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

若 `alpha_t in [0, 1]`、`gamma_p(Δt) in [0, 1]`，且 `E_(t-1), X_t, b_p` 都在 `[-1, 1]^n`，则 `B_t` 与 `E'_t` 都是有界向量的凸组合。因此，在耦合项较小且最后投影到 `[-1, 1]^n` 的条件下：

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
