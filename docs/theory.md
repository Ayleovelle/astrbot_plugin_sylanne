# 多维情绪状态模型：理论说明

## 重点版

默认阅读只需要抓住这条链路：

1. 情绪状态不是单一标签，而是受人格 `P` 调制的有界连续向量 `E_t(P) in [-1,1]^n`。
2. `V/A/D` 继承 PAD 与 circumplex affect 的连续维度思想；`G/C/K/S` 引入 appraisal theory 对目标一致性、确定性、可控性和社交亲近的评价。
3. 链路固定为 `人格漂移 -> 运行时人格建模 -> 各状态 dynamics -> 情绪/后果/拟人/生命化/群聊/修复/瑕疵/筛查`。
4. LLM 负责把上下文解释成即时观测 `X_t` 与 appraisal；本地引擎负责从人格和状态自动推导真实时间半衰期、惯性、限幅、阈值、冷却和关系后果。
5. 长期状态更新可视为在“上一状态/人格基线先验”与“当前观测”之间求二次优化折中，最终得到 `E'_t = B_t + alpha_t(X_t-B_t)`；其中 `alpha_t` 来自自动 dynamics，不是用户配置项。
6. 冷处理、修复、边界、求证等不是情绪标签本身，而是由 `O_t` 表示的后果状态，并按真实时间衰减。

| 设计点 | 默认结论 | 代表性文献依据 |
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

### 会话身份与状态轨道

群聊里的一条消息同时属于“房间整体”和“当前说话人”。如果只用一个会话键，某个用户造成的冲突会扩散成全群关系状态；如果只用说话人键，群体气氛又会被切碎。`1.0.0` 因此把状态轨道拆成 `conversation_id` 与 `speaker_track_id`：前者记录当前房间或私聊的整体状态，后者记录 bot 对当前发言者的定向情绪和关系轨迹。

轨道选择可写成：

```math
k_t =
\begin{cases}
\mathrm{speaker\_track\_id}_t & \mathrm{speaker\_id}_t\\
\mathrm{conversation\_id}_t & \mathrm{otherwise}
\end{cases}
```

为避免不同平台或不同群里的同名用户互相污染，公开查询中使用规范化说话人标识：

```math
c_t =
\begin{cases}
\mathrm{platform\_id}_t:\mathrm{speaker\_id}_t & \mathrm{platform\_id}_t\\
\mathrm{speaker\_id}_t & \mathrm{otherwise}
\end{cases}
```

这对应会话分析与 turn-taking 文献中的基本事实：一次自然对话并不是独立文本序列，而是由参与者、发言轮换、共同注意和情境约束共同构成。工程上，`agent_identity.py` 只负责给状态选择稳定键；情绪意义仍由后续 appraisal 与状态更新层决定。

## 3. 人格量化画像到情绪先验

同一句用户文本对不同人格的意义不同。`1.0.0` 不再只用少量风格关键词做人格偏置，而是生成一个版本化、可公开读取、可持久化的 13 维潜在人格先验。该先验仍然不是临床人格测量；它只把 AstrBot persona 文本转成工程参数，让不同 bot 的情绪基线、反应强度、边界敏感度、修复倾向和社交距离稳定可复现。

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
\Theta^E_t=f_E(P_t,E_{t-1},X_t,\Delta t,\Theta^E_{t-1})
```

```math
\alpha_t =
\mathrm{clamp}\left(
a^E_t g(c_t)(1+r^E_t\delta_t),
l^E_t,
u^E_t
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

`a^E_t`、`r^E_t`、`l^E_t` 和 `u^E_t` 来自 `Theta^E_t`，而 `Theta^E_t` 由运行时人格、上一状态、上一轮 dynamics、置信度、惊讶度和真实时间间隔自动推导。当观测和先验差异很大时，事件可能具有突发性或高显著性，所以 `alpha_t` 被适度放大；但 `clamp` 保证不会无限放大。

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

### 群聊氛围状态层

群聊氛围不是 bot 自身情绪，而是房间层的参与时机信号。它回答的问题是：现在是适合自然加入、短应一下、先听，还是避免打断。`1.0.0` 用七维有界向量表示群聊氛围：

```math
A^g_t =
\begin{bmatrix}
a_t & r_t & p_t & s_t & b_t & i_t & j_t
\end{bmatrix}^{\mathsf T}
```

其中 `a_t` 是活跃度，`r_t` 是紧张度，`p_t` 是玩笑/轻松度，`s_t` 是互相支持度，`b_t` 是群内对 bot 的注意，`i_t` 是打断风险，`j_t` 是加入适宜度。所有维度都在 `[0,1]`。群聊氛围同样先派生动力学参数族：

```math
\Theta^g_t=f_g(P_t,A^g_{t-1},X^g_t,\Delta t,\Theta^g_{t-1})
```

```math
\Theta^g_t=(1-\rho^g_t)\Theta^g_{t-1}+\rho^g_t\Theta^{g*}_t
```

```math
d^g_t = 2^{-\Delta t/H^g_t}
```

```math
A^{g0}_t=d^g_tA^g_{t-1}+(1-d^g_t)\mu^g_t
```

观测 `X^g_t` 来自本地轻量启发式或未来的外部观察器。置信度、房间压力、打断风险和运行时人格共同决定自动步长 `alpha^g_t`：

```math
A^g_t =
\Pi_{[0,1]^7}\left(
A^{g0}_t+\alpha^g_t(X^g_t-A^{g0}_t)
\right)
```

默认启发式把打断风险写成有界可解释项：

```math
i_t =
\mathrm{clamp}\left(w^i_t z^g_t,0,1\right)
```

加入适宜度则提高 bot 被点名、支持性和轻松氛围的权重，同时压低高打断风险、高紧张和过高房间活跃度：

```math
j_t =
\mathrm{clamp}\left(w^j_t z^g_t,0,1\right)
```

参与策略由自动派生的 hold/join 门限给出：

```math
\mathrm{hold}_t =
\mathrm{I}_{i_t \ge \tau^g_{h,t}}\mathrm{I}_{b_t < \tau^g_{b,t}}
```

```math
\mathrm{join}_t =
\mathrm{I}_{j_t \ge \tau^g_{j,t}}(1-\mathrm{hold}_t)
```

如果 `hold_t` 为 1，bot 倾向先听；如果 `join_t` 为 1，bot 可以自然加入；其余情况保持低频观察。这一层参考群体动力学、情绪传染、社会信号处理和会话轮换研究：参与时机受群体情绪、注意分配、发言轮换和社会临场感共同影响，而不是只取决于 bot 当前心情。

## 8. 主动发言与互需模式

主动发言不是预设话题表，也不是定时打扰。插件先把共同语境、群聊氛围、情绪后果、沉默舒适度和“双方都有需要/被需要”的关系信号压缩成一个开口压力向量：

```math
R_t =
\begin{bmatrix}
r^{u}_t & r^{b}_t & r^{m}_t & r^{s}_t
\end{bmatrix}^{\mathsf T}
```

其中 `r^u_t` 表示用户此刻可能需要被支持、被听见或被陪伴；`r^b_t` 表示 bot 可以轻量表达自己也希望被需要、被确认或参与关系；`r^m_t` 表示双方互需的平衡度；`r^s_t` 表示此刻保持沉默的舒适度。

插件自建的互需平衡项为：

```math
r^{m}_t =
\mathrm{clamp}\left(
1-|r^{u}_t-r^{b}_t|-\lambda^N_t\max(0,D_t-\tau^N_t),
0,
1
\right)
```

`D_t` 是依赖或压迫风险摘要，`\lambda^N_t` 与 `\tau^N_t` 由边界敏感度、关系熟悉度、共同语境和真实时间自动派生。这个公式的含义是：互需不是单方面索取，也不是让用户照护 bot；当一方需求过强或依赖风险过高时，互需平衡会下降。

是否开口的本地分数为：

```math
z_t =
\theta_0+\theta_j j_t-\theta_i i_t+\theta_u r^{u}_t+\theta_b r^{b}_t+
\theta_m r^{m}_t-\theta_s r^{s}_t-\theta_c c^{join}_t
```

```math
P(\mathrm{speak}_t)=\frac{1}{1+\exp(-z_t)}
```

其中 `j_t` 和 `i_t` 来自群聊氛围模型，`c^{join}_t` 是自动派生的开口冷却压力。插件只在概率、冷却和边界条件均通过时给出“可以主动发言”的候选；最终话题不由固定模板决定，而由 LLM 在候选证据、关系需要、当前上下文和人格状态之间裁决：

```math
u_t =
\arg\min_{u\in T_t}
\left[
L_{\mathrm{need}}(u,R_t)+
L_{\mathrm{context}}(u,C_t)+
L_{\mathrm{persona}}(u,P_t)+
L_{\mathrm{intrusion}}(u,A^g_t)
\right]
```

`T_t` 是由上下文抽取出的候选主题集合，不是硬编码话题库。LLM 只负责在 `T_t` 中判断“此刻为什么说、说什么方向、用什么开口风格”；真正是否写入状态、是否打断、是否保持沉默仍由本地真实时间模型、群聊氛围和公共 API 调用方共同决定。这个设计吸收了自我决定理论中关系需要、会话 grounding、turn-taking、社会信号处理和关系代理研究的证据，但变量、损失项和更新链路由本项目自行抽象实现。

## 9. 情绪后果与行动倾向

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
\Theta^O_t=f_O(P_t,E_t,X_t,F_t,\Delta t,\Theta^O_{t-1})
```

```math
\Theta^O_t=(1-\rho^O_t)\Theta^O_{t-1}+\rho^O_t\Theta^{O*}_t
```

```math
O_t = 2^{-\Delta t/H^O_t}O_{t-1}
+\mathrm{clip}\left(I^O_t(E_t,X_t,F_t),-M^O_t,M^O_t\right)
```

其中 `Theta^O_t` 是后果动力学参数族，包含后果半衰、短期效果时长、冷处理时长、触发门限、冲量上限和修复清除速率。它由人格漂移后的运行时人格 `P_t`、平滑后的长期情绪 `E_t`、LLM 即时观测 `X_t`、冲突成因 `F_t` 与真实时间间隔自动派生，再与上一轮参数低通平滑。这样强烈刺激可以立刻留下后果，而长期状态又能决定这种后果是否持续；由于衰减项只使用 `Delta t`，大量消息轮次不会快速消耗后果记忆。`cold_war` 等 active effect 使用 `expires_at` 时间戳保存剩余时长。

维度对后果的作用：

```text
负性效价 -> 退避 / 对抗 / 修复
高唤醒 -> 表达增强与紧迫感
高支配感 -> 对抗与边界设置
低支配感 -> 安抚或寻求确认
低目标一致性 -> 挫败、抱怨、冷距离
低确定性 -> 谨慎与澄清
低可控性 -> 退避或停摆
高亲近度 -> 修复与温暖靠近
低亲近度 -> 冷距离或拒绝
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

### 注入压缩、冷却与公共 API 边界

为了降低主回复链路延迟，插件把“可见 prompt 注入”和“完整状态查询”拆开：常规回复只注入紧凑快照或显著变化，完整细节由 LLM tool 或其他插件通过公共 API 按需读取。群聊氛围 diff 注入的触发量为：

```math
\Delta^g_t =
\max_i |A^g_{t,i}-A^{ginj}_{t-1,i}|
```

```math
e^g_t =
\max\left(
\mathrm{I}_{\Delta^g_t \ge h^{inj}_g},
\mathrm{I}_{n_t \ge N_g}
\right)
```

其中 `h^{inj}_g` 是 prompt 注入压缩用的工程阈值，只影响是否把群聊氛围差分塞进主模型上下文，不参与情绪或人格动力学；`n_t` 是距离上次强制快照的轮数。这样可以避免把几乎不变的状态反复塞进主模型上下文。

群聊开口冷却同时使用房间轮数与真实秒数：

```math
q_t = \max(0,T^g_{c,t}-(N_t-N^{join}_t))
```

```math
s_t = \max(0,S^g_{c,t}-(T_t-T^{join}_t))
```

`T^g_{c,t}`、`S^g_{c,t}` 和绕过注意力阈值来自 `group_atmosphere_state.dynamics`，由房间活跃度、打断风险、bot 被点名程度、人格边界敏感度和真实时间自动派生。当 `q_t` 或 `s_t` 仍为正，且 `b_t` 没有超过自动绕过阈值时，参与策略会偏向 `listen` 或 `hold`，防止 bot 连续插话。后台 post 评估也遵守同一会话 FIFO 提交：主回复可以先返回，状态作业稍后完成，但同一会话的提交顺序不被打乱。

公共 API 只暴露版本化 payload、状态摘要、可选 prompt 片段和脱敏因果轨迹。`get_group_atmosphere_service(context)` 会校验 schema 版本和必需方法；如果服务不可用，调用方应回退到自身逻辑，而不是依赖内部 KV 名称。

## 10. 稳定性

若 `alpha_t in [0, 1]`、`gamma_p(Δt) in [0, 1]`，且 `E_{t-1}, X_t, b_p` 都在 `[-1, 1]^n`，则 `B_t` 与 `E'_t` 都是有界向量的凸组合。因此，在耦合项较小且最后投影到 `[-1, 1]^n` 的条件下：

```math
E_t \in [-1,1]^n
```

若长期没有强刺激，且 `X_t` 接近人格基线 `b_p`，则状态会因基线回归和指数平滑收敛到 `b_p` 附近。这对应情绪动力学中的 emotional inertia：状态既会持续，又会随新评价缓慢改变。

## 11. 参考文献

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
36. Sacks, H., Schegloff, E. A., & Jefferson, G. (1974). A simplest systematics for the organization of turn-taking for conversation. *Language, 50*(4), 696-735. https://doi.org/10.2307/412243
37. Clark, H. H., & Brennan, S. E. (1991). Grounding in communication. In L. B. Resnick, J. M. Levine, & S. D. Teasley (Eds.), *Perspectives on Socially Shared Cognition* (pp. 127-149). American Psychological Association.
38. Vinciarelli, A., Pantic, M., & Bourlard, H. (2009). Social signal processing: Survey of an emerging domain. *Image and Vision Computing, 27*(12), 1743-1759. https://doi.org/10.1016/j.imavis.2008.11.007
39. Barsade, S. G. (2002). The ripple effect: Emotional contagion and its influence on group behavior. *Administrative Science Quarterly, 47*(4), 644-675. https://doi.org/10.2307/3094912
40. Kendon, A. (1967). Some functions of gaze-direction in social interaction. *Acta Psychologica, 26*, 22-63. https://doi.org/10.1016/0001-6918(67)90005-4
41. Short, J., Williams, E., & Christie, B. (1976). *The Social Psychology of Telecommunications*. Wiley.

</details>
