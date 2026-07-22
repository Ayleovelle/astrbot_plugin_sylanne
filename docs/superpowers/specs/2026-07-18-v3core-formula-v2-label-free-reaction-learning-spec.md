# v3core Formula v2: 免标签反应学习通道 (Label-Free Reaction Learning) 设计规格

**Date:** 2026-07-18

**Status:** 设计规格（可直接 TDD 实现）；方向已由用户拍板，本文件不再做方向裁决

**Parent design:** `2026-07-15-v3core-shadow-cognitive-architecture-design.md`（下称"母规格"）

**Formula lineage:** 母规格 formula v1 → SNN 删除（代码注释已自称 formula v2，但
`FORMULA_VERSION` 常量至今仍是 `"sylanne.v3.formula.v1"`）→ 本规格完成正式的
v2 版本升格：`FORMULA_VERSION = "sylanne.v3.formula.v2"`，digest 有意变更。

---

## 0. 问题陈述（代码级事实，非复述）

以下每条都在当前 `feat/embodiment-2.5.0` 分支真码里核实过：

1. **动作标签饥荒。** 母规格 §11.1：AstrBot 4.26.5 普通回复路径没有独立成功回执，
   `V2ActualActionProjectionV1` 恒产出 `UNKNOWN`。`orchestrator.py` 在
   `actual_action is None` 时构造的 `PendingOutcome` 不带冻结数组
   （`projected_actual_action=None`，六个 per-axis 数组全空）。
2. **结算整体被标签闸死。** `orchestrator.py` 的结算前置段
   （`pending is not None and _is_adjacent(...) and len(pending.predictive_mu_actual) == AXIS_DIM`）
   在数组为空时直接跳过 `settle_with`。也就是说：动作 UNKNOWN 的 turn，t+1 什么都
   不学——EKF 不学、baseline 不学、连"用户反应好不好"这个已经算出来的
   `OutcomeFrame` 都被整帧扔掉。
3. **评估机器同样饿死。** `scripts/v3_replay.py` 三个主指标全部吃标签：
   `log_loss`/`brier` 直接需要 `actual_action`；`axis_mae` 读的
   `pending.predictive_mu_actual` 只在有标签时存在（`pending_mu` 为空则
   `axis_abs_error=()`，分母为零返回 `None`）。
4. **离线真实历史当前只填 3/36 通道。** `scripts/v3_export.py::_project_messages`
   只写 channel 13/18/30，且 `actual_action="UNKNOWN"` 硬编码——因此现有 G1 数据上
   三个主指标全部为 `None`，G1–G4 的证据产出是**零**，不是"少"。
   （附带发现一个数据缺陷：当前消息长度被写进 channel 13——那是 body.epoch 的
   语义槽位，恰好共用 `_log_length` 归一化才没炸；Slice D 修。）
5. **但免标签信号的原料在活流量上是齐的。** `v3bridge/observation_adapter.py`
   的 `_DIRECT_CHANNELS` 映射了 24 个快照字段 + 13/18/22/30 共 ~30 个通道，
   其中包括 channel 25 (`text_valence_cue`)、26 (`text_engagement_cue`)、
   31 (`gap_seconds`)；`project_outcome` 已经在每个 turn 无条件把 t+1 帧投影成
   8 轴 `OutcomeFrame`。也就是说：G2/G3 活影子流量上，"用户下一轮反应"
   的每个分量都已经被算出来了，只是被标签闸拦在结算之外。

**通道命题：** 用户在 t+1 的下一条消息，是对 t 轮 v2 实际交互（回或不回、回了什么）
的真实因果后果。它的特征（语气、投入度、长短、间隔）**不需要知道 bot 在 t 轮选了哪
个动作**就能读出。所以它可以在动作 UNKNOWN 时喂给偏好层和世界模型层——绕开动作
信用，不绕开因果。

---

## 1. 信号定义：`ReactionSignalV1`

### 1.1 输入

t+1 轮的核内已有量，不新增任何 I/O：

- t+1 的 `ObservationFrame u'`（36 维 + valid_mask）——即用户这条消息本身的特征帧；
- t+1 的 `OutcomeFrame y'`（8 轴 + valid_mask）——`project_outcome(u')`，已在算；
- t+1 的 `TurnContextClass`；
- 状态里的用户长度基线（§3.1 新增字段）；
- 桥侧新增的一个结算事实 `ReactionFacts(same_sender: bool | None)`（§1.4）。

只读 `u'` 的四个通道：18 (text.length)、25 (text.valence_cue)、
26 (text.engagement_cue)、31 (gap_seconds)。`y'` 的 8 轴全部按位复用为学习目标。

### 1.2 合成公式（精确到常量）

新 formula 常量（进 manifest 的 `labelfree` 块，§4.3）：

```text
REACT_W_VALENCE        = 0.5
REACT_W_ENGAGEMENT     = 0.3
REACT_W_LENGTH         = 0.2
REACT_LEN_GAIN         = 3.0
REACT_GAP_ATTEN_LO     = 0.62    # 归一化 u31 空间；反解 ≈ 330 s (~5.5 min)
REACT_GAP_ATTEN_HI     = 0.78    # 反解 ≈ 4270 s (~71 min)
REACT_WARMUP_COUNT     = 5       # 长度项生效前需要的长度样本数
LF_REACTION_CONTEXTS   = ("ADDRESSED", "AMBIENT")   # t+1 必须是真实入站消息
LF_ELIGIBLE_ORIGIN_CONTEXTS = ("ADDRESSED", "AMBIENT", "PROACTIVE")  # t 轮资格
```

纯函数 `reaction_signal(u', mask', context', lf_state, same_sender) -> ReactionResult`：

```text
若 context' not in LF_REACTION_CONTEXTS      -> INVALID (reason=NOT_INBOUND)
若 same_sender is False                       -> INVALID (reason=SENDER_MISMATCH)

terms = []
若 bit25 有效: terms += (REACT_W_VALENCE,    2*u'[25] - 1)
若 bit26 有效: terms += (REACT_W_ENGAGEMENT, 2*u'[26] - 1)
若 bit18 有效 且 lf_state.reaction_count >= REACT_WARMUP_COUNT:
    terms += (REACT_W_LENGTH,
              clip(REACT_LEN_GAIN * (u'[18] - lf_state.len_baseline), -1, 1))

若 terms 中不含来源为 {25,26} 的任一项        -> INVALID (reason=NO_TONE_EVIDENCE)

r_raw  = sum(w_i * t_i) / sum(w_i)            # 只对在场项归一
a_gap  = 1.0                                  若 bit31 无效
       = 1 - clip((u'[31]-REACT_GAP_ATTEN_LO)
                  /(REACT_GAP_ATTEN_HI-REACT_GAP_ATTEN_LO), 0, 1)   否则
若 a_gap == 0.0                               -> INVALID (reason=STALE_REACTION)

r_react = clip(r_raw, -1, 1) * a_gap          # 保证 in [-1,1]、有限
```

### 1.3 信号 vs 噪声——逐条

- **"很久才回可能是睡了不是不满"**：latency 在 v2 里**不做证据、只做衰减器**。
  gap ≤ ~5.5 分钟满权重，≥ ~71 分钟权重清零并整条 CENSOR。长间隔回复既不奖也不罚。
  拒绝把 latency 直接当满意度的理由：混杂因子（睡眠/上班/换设备）不可在核内区分，
  任何符号化使用都是编造证据。gap 缺失（离线数据）时衰减器取中性 1.0 并如实记录——
  这是已声明的噪声敞口，由 §6 的置换门兜底。
- **长度基线**：长消息=投入的假设只在"相对该用户自己的基线"下使用
  （`u'[18] - len_baseline`），且前 `REACT_WARMUP_COUNT` 个样本内长度项无效。
  基线是行为统计不是信用，更新不受 a_gap/censor 影响（§3.1）。
- **语气项是主证据**：valence/engagement 至少一个在场才有效。这两个通道来自
  v2core lexicon 的确定性读数——它们的词表质量是整条通道的天花板，§8 里如实计价。
- **群聊他人插话**：t+1 的发言者可能不是 t 轮的对话者。桥在结算事实里冻结
  `same_sender`（HMAC surrogate 相等性比较，身份不进核、不进持久化），
  `False` 直接 INVALID；私聊桥恒置 `True`；桥无法判定时 `None` = 放行
  （群聊 None 属于已声明噪声，进覆盖率计数器）。

### 1.4 契约变更

`CoreInvocation` 增加一个可选字段 `reaction_facts: ReactionFacts | None`
（frozen dataclass，仅 `same_sender: bool | None`）。它描述的是**本次入站消息相对上
一轮**的关系，由桥在响应边界与 `projected_actual_outcome` 一起冻结。观测张量维持
36 维不动——不为它开新通道，避免 OBSERVATION_DIM 波及全域。

确定性义务：`same_sender` 参与状态演化，因此它是确定性核输入的一部分——
必须进 `CoreDecisionTrace`（新增 `reaction_same_sender` 字段）并随 Slice D 的
数据集 turn 行一起导出（三值：true/false/null），否则离线重放无法逐位复现
在线结算。它是布尔关系事实，不携带任何身份信息，隐私面不扩大。

---

## 2. 信用分配：结算机制改造

### 2.1 原则

turn N 的交互，拿 turn N+1 的反应当延迟信号——**完全复用现有 PendingOutcome 的
邻接/删失骨架，只拆掉标签闸**。一次结算点、一次原子提交、同一套 CAS 语义。

### 2.2 PendingOutcome 变更

新增一个字段（其余不动）：

```python
label_free_eligible: bool = False   # 在 t 轮冻结：context_t ∈ LF_ELIGIBLE_ORIGIN_CONTEXTS
```

冻结在 t 轮的理由：反应资格取决于 t 轮的性质（IDLE 轮没有可被反应的交互），
t+1 不得回头猜。`ADDRESSED/AMBIENT/PROACTIVE` 有资格（对沉默的反应也是偏好证据；
proactive 已发出的消息更是）；`IDLE` 无 **L1 反应信用**资格。这个位只门控 L1；
它不门控相邻转移的 L2，也不门控 t+1 当前入站事实驱动的长度基线更新。

### 2.3 orchestrator 结算前置段改写

```text
pending 存在 且 _is_adjacent(pending.sequence, envelope.sequence):
    # 路径 A：标签结算（现状不变，一字不改语义）
    若 len(pending.predictive_mu_actual) == AXIS_DIM:
        settlement = settle_with(base, outcome_frame, quality_score)
    # 路径 B：免标签结算（新增；每个相邻 turn 必调；不看动作标签）
    lf = settle_label_free(
        base, frame, outcome_frame, context, reaction_facts,
        l1_eligible=pending.label_free_eligible,
    )
pending 不存在或不相邻：双路径都 CENSORED（与 v1 完全同规则）
```

路径 B 在**每一个相邻 turn**都调用。`pending.label_free_eligible` 只决定 L1 是否可以
消费有效 `r_react`：为假时 L1 保持不动并报告 `NOT_ELIGIBLE`。L2 仍对至少一个有效
outcome 轴执行 pre-update 预测与 EKF；长度基线仍只按 §3.4 自己的当前轮事实门
（入站 context、bit18 有效、`same_sender != False`）更新。换言之，origin=`IDLE`
只表示“这轮没有可获 L1 信用的交互”，绝不表示“下一相邻观测不得进入 L2/基线”。

两条路径读同一个 pending、同一个 `outcome_frame`，写**不相交的状态字段**
（A→`action_beliefs`；B→`label_free`），产物进同一个 `StateDelta`，与本轮其余状态
一起单次 CAS 提交。提交失败两者一起回滚重算——继承母规格 §8.3 的原子性原文。

### 2.4 邻接与删失（"掉一轮怎么办"）

逐字继承 v1 规则，免标签路径无任何放宽：

- 掉队/丢弃/超时/重载/epoch 变更/乱序 → `_is_adjacent` 为假 → 双路径 CENSORED；
  绝不把 n+1 当 n-1 的下一观测，绝不编造缺失转移。
- 免标签路径额外的删失原因（§1.2 的 INVALID reasons）逐条进 trace：
  `NOT_INBOUND / SENDER_MISMATCH / NO_TONE_EVIDENCE / STALE_REACTION`。
- pending 每轮被新 pending 覆盖（现状行为），天然只有相邻一次结算机会。

---

## 3. 学到哪一层：两个学习器，更新律逐条

结论：**偏好层 + 一个动作边缘世界模型头，动力学矩阵一根手指都不碰。**
`P/W_*/U_*` 不学的理由是硬的：它们受 §9 的 Jacobian 收缩证明
（`sup||J||_2 < 0.995`）保护，任何在线可变都要求逐步重证收缩性——那是另一个
formula 大版本的工作量，不是这条通道该背的。

母规格 §13 明文：新增任何学习器必须配齐
"state schema、update equation、bounds、credit source、replay rule、ablation gate"。
下面两个学习器逐项对表。

### 3.1 状态 schema 新增（STATE_SCHEMA_VERSION 1→2）

```python
@dataclass(frozen=True, slots=True)
class LabelFreeState:
    pref_offset: tuple      # [8] float, 存储校验界 = quantization_safe_bounds((-0.30, 0.30))
    marginal_theta: tuple   # [16] = 8 轴 × [g, b]；界复用 ACTION_G_BOUNDS / ACTION_B_BOUNDS
    marginal_sigma: tuple   # [16] 对角协方差；界复用 ACTION_SIGMA_BOUNDS
    marginal_count: int     # 0..ACTION_COUNT_CAP (65535)
    len_baseline: float     # [0,1]，初值 LEN_BASELINE_INIT = 0.60
    reaction_count: int     # 0..65535，计"有效长度样本"个数

V3State 增字段: label_free: LabelFreeState | None = None   # None ⇒ 全先验
```

新常量：

```text
PREF_OFFSET_BOUNDS = (-0.30, 0.30)
PREF_ETA           = 0.05
LEN_BASELINE_ETA   = 0.10
LEN_BASELINE_INIT  = 0.60
MARGINAL_INITIAL_G = 0.85 ;  MARGINAL_INITIAL_B = 0.0
MARGINAL_INITIAL_V = 0.25 ;  MARGINAL_INITIAL_R = 0.20   # 复用 ACTION_INITIAL_V/R 数值
MARGINAL_SIGMA_INIT = (0.10, 0.10) ;  MARGINAL_Q_THETA = 1e-4  # 复用 ACTION_Q_THETA 数值
```

注意 float16 网格：`float16(0.30) = 0.300048828125 > 0.30`，所以 offset 的存储校验界
必须过 `quantization_safe_bounds`——这正是 a16 教训的既有机制，直接复用。
字节代价：8+16+16 个 f16 + 2 个整数 ≈ 90 B，对 48 KiB 目标无感。

codec：`STATE_CODEC_VERSION 3→4`，读支持 (1,2,3,4)；旧 blob 解码时
`label_free=None`、`pending.label_free_eligible=False`——迁移即缺省，无重写。

### 3.2 学习器 L1：`PreferenceOffsetLearnerV1`（偏好层）

**语义**：把 §11.2 的偏好均值 `c` 从纯常量+状态拷贝，升格为
"版本化基座 + 有界习得残差"：

```text
base_c_i(s) = s_i                    若 i ∈ PREFERENCE_C_STATE_AXES (0,3)
            = PREFERENCE_C_CONSTANT_i 否则
c_i(s)      = clip(base_c_i(s) + pref_offset_i, -1, 1)      # V_C 不变
```

`preferences()` 的两个消费点同步改签名：`score_policy`（EFE risk）与
`freeze_actual_prediction`（标签路径的冻结偏好）。`settle_with` 用的是 pending 里
**冻结**的 c/V_C，语义自动保持"t 轮的奖励按 t 轮生效的偏好计"。

**更新律**（在 `settle_label_free` 内，仅当 r_react 有效）：

```text
s_dec    = decision_state(base.latent_axes)          # 与 EKF 结算侧同一个 s
对每个 outcome bit i 有效的轴：
    target_i = clip(y'_i - base_c_i(s_dec), -0.30, 0.30)   若 r_react >= 0
             = 0.0                                           若 r_react <  0
    eta_i    = PREF_ETA * |r_react|                          # ∈ [0, 0.05]
    off_i'   = (1 - eta_i) * off_i + eta_i * target_i
bit 无效的轴：off_i' = off_i
```

**有界性/不发散（证明一句话说完）**：`off'` 是 `[-0.30, 0.30]` 内两点的凸组合，
故恒在界内；`eta_i < 1` 恒成立，映射对 off 是压缩的，不动点 = 反应加权的
`(y' - base_c)` 均值，无发散模式。负反应**不做反向目标**（把 c 推离 y' 在有界盒里
会撞墙抖振，且惩罚的是噪声），而是衰减回 v1 先验锚点——这是刻意的不对称，写死。

**信用来源**：相邻、有资格、reaction 有效的 t+1 入站反应；所有删失规则见 §2.4。

**replay 规则**：与 v1 EKF 完全一致——只有这一个在线结算点可以更新；
`learning/replay.py` 的只读边界扩展一行措辞把 `label_free` 列入禁改清单。

**速度的诚实预期**：`eta_eff ≈ 0.05 × E|r| ≈ 0.015`/有效反应轮。offset 走到目标的
63% 需要 ~67 个有效反应轮；按活流量 40–70% 的反应有效率折算，**可见的偏好漂移需要
100–150 个真实 turn**。这不是 bug，是慢时标设计；评估门据此设最小证据底线（§6）。

### 3.3 学习器 L2：`MarginalOutcomePredictorV1`（动作边缘世界模型）

**语义**：与 §11.2 的 per-action 转移信念同构，但**不条件化动作**：

```text
mu_m_i(s) = tanh(gm_i * s_i + bm_i)
```

它回答"当前状态下，下一轮 8 轴结果长什么样（对动作取边缘）"。这正是动作
UNKNOWN 时唯一诚实可学的世界模型。

**更新律**：逐字复用 `ekf_transition_update` 的数学（同一 Jacobian、同一
box-projection、同一 `Sigma` 更新、同一 count 语义），参数换成
`(gm, bm, sigma_m)`，噪声换成 `MARGINAL_V/MARGINAL_R`。实现上抽出共享私有函数，
不复制粘贴两份 EKF。

**门控**：相邻 + `OutcomeFrame` 至少 1 轴有效。不要求 reaction 有效、不要求
origin 资格、不要求动作已知——它是转移统计，不是反应信用。有标签的 turn 也更新
（与 per-action EKF 双写不冲突：参数不相交，而且这正好构成 §6 的对照——
动作条件化必须在有标签子集上打赢边缘模型，才证明标签有信息量）。

这里的“origin 资格”专指 `pending.label_free_eligible`。实现不得在调用
`settle_label_free` 之前用该位短路路径 B，也不得在函数内部用该位跳过 L2；即使
origin=`IDLE`，只要转移相邻且至少一轴有效，L2 仍执行 pre-update 预测和 EKF 更新。

**v2 里 L2 不接策略。** `score_policy` 不读它。理由：它对四个候选动作给同一个
预测，接进 EFE 只会加常数；它在 v2 的职责是**证据生成器**（免标签可打分的预测头）
和 formula v3 的候选先验（比如把 per-action EKF 向边缘模型收缩）。这一条写死，
防止"顺手接一下"造成不可归因的策略漂移。

**有界性**：全部继承 v1 EKF 的界（g/b/sigma box + clip），无新增证明义务。

### 3.4 长度基线（行为统计，非学习器）

```text
若 context' ∈ LF_REACTION_CONTEXTS 且 bit18 有效 且 same_sender ≠ False:
    len_baseline'   = clip((1-LEN_BASELINE_ETA)*len_baseline + LEN_BASELINE_ETA*u'[18], 0, 1)
    reaction_count' = min(reaction_count + 1, 65535)
```

不受 r_react 有效性影响（基线要在 warmup 期就开始积累）。
也不受 `pending.label_free_eligible` 影响：它统计的是 t+1 当前入站消息自身的长度事实，
不是给 t 轮分配反应信用。因而 origin=`IDLE` 时，只要路径 B 因相邻而被调用且上面的
当前轮事实门成立，基线与 `reaction_count` 仍照常更新。

---

## 4. 与现有核的关系

### 4.1 共存矩阵（谁读谁写，一张表钉死)

| 参数/状态 | 写者 | 读者 | v2 变化 |
|---|---|---|---|
| `action_beliefs` (per-action EKF θ/Σ/baseline/count) | 标签结算路径 A | `score_policy`、`freeze_actual_prediction` | **不变** |
| `label_free.pref_offset` | 免标签路径 B (L1；pending eligibility 门控) | `preferences()` → EFE risk、冻结偏好 | 新增 |
| `label_free.marginal_*` | 免标签路径 B (L2；任意相邻 turn，独立于 pending eligibility) | 仅 trace/评估 | 新增，不接策略 |
| `label_free.len_baseline/reaction_count` | 免标签路径 B（任意相邻 turn，按当前入站事实门更新） | `reaction_signal` | 新增 |
| `P/W_*/U_*`、`V_C`、`V_a`、`R_a` | 无人 | 各处 | 维持不可变先验 |

**不打架的三条硬保证**（各配测试）：

1. **参数不相交**：路径 A 与 B 写的状态字段集合交集为空——同轮双路径都触发时
   （相邻 + 有标签 + 有反应），两者独立计算、一次提交。
2. **动作不可见性**：`settle_label_free` 的函数签名里**没有** `pending.action`、
   `pending.projected_actual_action`、`shadow_action` 任何一个；属性测试断言其输出
   对这三者的任意取值不变（§7 Slice C 的 RED 主菜）。
3. **奖励非平稳性已声明**：L1 漂移会缓慢改变标签路径的奖励定义（经 `preferences()`
   进入未来 turn 的冻结偏好）。逐轮语义由 pending 冻结保住（t 轮奖励永远按 t 轮偏好
   计，不可追溯）；跨轮漂移由 baseline EMA 吸收。STDP 已删，reward 的消费面只剩
   baseline EMA 与 trace，敞口小且有界。

### 4.2 认识论上的分工

- per-action EKF：继续吃标签，学"动作 a 之后世界怎么变"。饿就饿着——不喂假标签。
- L2：吃所有相邻 turn，学"世界怎么变（不问动作）"。
- L1：吃有效反应 turn，学"这个用户对什么样的结果反应好"。

### 4.3 FORMULA_DIGEST / 各类版本位

全部**有意**变更，逐项列出防漏：

| 工件 | 变更 |
|---|---|
| `FORMULA_VERSION` | → `"sylanne.v3.formula.v2"`（连带 `PREFERENCE_REVISION` 等别名；SNN 删除注释里的"formula v2"自此与常量一致） |
| `FORMULA_MANIFEST` | 新增 `labelfree` 块（§1.2/§3.1 全部常量 + 更新律公式字符串）；`FORMULA_DIGEST` 变，Task 1 golden test 有意更新 |
| `STATE_SCHEMA_VERSION` | 1 → 2 |
| `STATE_CODEC_VERSION` | 3 → 4，读支持 (1,2,3,4) |
| `TRACE_SCHEMA_VERSION` | +1；trace 新增 `r_react / reaction_valid / lf_censor_reason / pref_offset_after[8] / marginal_mu[8]`（≈ 数百字节，16 KiB 帽核实无虞，加测试） |
| 评估初始态 | `neutral_eval_v1` → `neutral_eval_v2`（新字段全先验）；episode seed 已含 formula_digest，v2 数据集天然与 v1 隔离 |
| 稳定性门 | `scripts/v3_stability.py` 的界断言扩到新字段；中性输入下 reaction 恒无效 ⇒ offset 恒 0 ⇒ v1 各轴包络不变（加断言钉死） |

### 4.4 性能与隔离

L1+L2 每次结算 O(8) 级浮点操作，对 2.5 ms p95 预算无感。七个隔离计数器、
效果白名单、`EffectCommitter` 单口——一个都不碰。通道整体活在影子内，
用户可见面零变化；删光 v3 键仍然对 v2 零影响。

---

## 5. 默认关/影子约束下，这条通道到底能学到什么（讲透）

分三层，每层的措辞就是允许对外宣称的上限：

1. **能学（因果干净）**：`r_react` 是用户对 **v2 实际执行的交互**的真实反应。
   它归因的对象是 `(状态, 该用户)`，不是任何动作选择。所以 L1 学到的
   "该用户的反应加权结果分布"、L2 学到的"状态→下轮结果的边缘转移"，
   都是从真实执行轨迹上学的真东西——影子身份不折损这两类知识的效度。
2. **能学但打折（归因给 v2）**：per-action EKF 在偶发有标签的 turn 上学到的是
   **v2 策略下**的动作后果。v3 若日后执行，自身策略不同会产生分布偏移。
   这个折扣 v1 已声明，v2 不加重也不减轻。
3. **学不到（影子的硬墙）**：**"我的影子决策比 v2 好"**。v3 在 t 轮选了
   CLARIFY 而 v2 实际 SPEAK，t+1 的用户反应是对 SPEAK 的反应——它对
   CLARIFY 的反事实结果零信息。免标签通道**没有**在这堵墙上开洞：
   它刻意不把 r_react 与 shadow_action 关联（§4.1 保证 2 就是防这个）。
   母规格 §3.3"影子分歧不得宣称因果优越"原样有效。

与上轮"主动推理在纯影子里认识论空转"的判词对齐：那条批评打的是
**动作信用**在影子里无处着地。本通道不重蹈，因为它学的两样东西
（用户偏好密度、边缘世界模型）的验证不依赖 v3 的动作被执行——
预测下一轮、拟合反应加权分布，这两件事在纯观测数据上就能对错分明。
空转的部分依然空转（并将继续空转到有执行授权为止），本规格不假装治好它。

---

## 6. 可证伪：LF 消融门（关键性质：一个标签都不吃）

### 6.1 指标定义

全部 prequential（预测先于更新）、按 episode 整体 bootstrap（复用 §17.2 协议）、
在冻结数据集上跑：

**LF-1（L2 世界模型门）** — 免标签 axis-MAE：

```text
每个相邻结算 turn，更新前计算 |y'_i - mu_m_i(s_dec)|，对有效轴聚合
（口径与现有 axis_mae 相同：每个轴观测一单位权重）。
对照组：frozen（gm/bm 恒为先验，等效零学习率）。
门：learner 相对 frozen 的 MAE 改善，episode-bootstrap 95% CI 下界 > 0。
附报（不做门）：carry-forward 基线（预测 y'(t+1)=y'(t)，双侧有效轴上）——
  打不赢就如实印出来，这个基线在慢变轴上非常强，输了不丢人，瞒了才丢人。
```

**LF-2（L1 偏好门）** — 反应加权偏好 NLL：

```text
对每个 r_react > 0 的已结算 turn：
  nll_t = mean_valid_i [ -log Normal(y'_i ; c_i(pre-update), V_C_i) ] , 权重 w_t = r_react
对照组：pref_offset 恒 0（= v1 偏好）。
门：加权 NLL 改善 bootstrap 95% CI 下界 > 0，且 LF-4 置换通过。
```

**LF-3（互不干扰门）**：

```text
在含标签数据（合成 + 未来任何有回执子集）上，label-free ON vs OFF：
  log_loss / brier / axis_mae 回归 ≤ 0.5%（复用 v3_ablation 现有回归口径）；
  known-HOLD 矛盾率恶化 < 0.5 pp；七个隔离计数器恒零。
外加 §4.1 保证 2 的动作不可见性属性测试（这条在单测层，不等数据）。
```

**LF-4（置换对照，反循环论证的主闸）**：

```text
把 r_react 序列在 episode 内按种子置换（种子 = §17.2 的 episode seed +
length-framed control ID "LF_PERMUTE"，学与不学的流严格分离），重跑 LF-2。
门：置换后 LF-2 的增益消失 ≥ 50%。
含义：若置换杀不掉增益，说明 offset 学到的只是结果分布的边缘漂移而非
"反应条件化"的偏好——L1 判负，pref_offset 永冻为 0，L2 可独立存活。
```

**证据底线**：LF-2/LF-4 要求 ≥ 150 个 reaction-valid 已结算 turn 且 ≥ 3 个
episode，不足则输出 `INSUFFICIENT_EVIDENCE`（复用母规格的既有语义，绝不静默通过）。
另设覆盖率计数器（reaction-valid / adjacent / settled 三级漏斗）随 G3 遥测上报——
如果活流量上漏斗顶端就干涸，要让它自己招供。

### 6.2 相对 G1–G4 的关键优势（以及诚实的边界）

| | 现有主指标 (G1–G4) | LF 指标 |
|---|---|---|
| 需要 actual action | 是（三个全要） | **否（零个）** |
| 在当前真实数据上可打分 | 否（全 None） | LF-1 可（任何相邻对）；LF-2 需语气通道 |
| 在活 G3 流量上可打分 | 仅当未来有回执 | 是（通道 25/26/31 活流量已填） |
| 证明的是什么 | 动作预测/校准 | 世界模型预测 + 偏好密度适配 |

必须直说的坑：**LF-2 有部分循环性**——r_react 与 y' 的 valence 轴共享 u25。
它证明的是"学到的密度比手写先验更贴合反应加权的经验分布"，是密度估计命题，
不是策略改进命题。这个循环由 LF-4 置换门约束（真信号才有反应条件化结构），
且措辞上限已在 §5 钉死。另外 LF-2 在**当前**离线导出上同样不可打分
（3/36 通道没有 u25/u26），要靠 Slice D 的导出器增强或 G3 活数据——
这条依赖不藏在脚注里，就写在这。

---

## 7. 落地切片（4 片，每片 RED→GREEN 独立可验，顺序依赖 A→B→C→D）

### Slice A — formula v2 常量 + 反应信号纯函数

- **改**：`formula_v1.py`（版本串升 v2、`labelfree` manifest 块、新常量）;
  新建 `v3core/learning/reaction.py`（`reaction_signal` + `ReactionResult` DTO，纯 stdlib）。
- **RED**（新 `tests/test_v3_reaction_signal.py` + 既有 golden 更新）：
  r_react 有界/有限/确定性；四个 INVALID reason 逐个触发；gap 衰减对 u31 单调不增、
  端点值精确；gap 缺失 → 衰减 1.0；warmup 内长度项不进合成；只含长度项 → INVALID；
  权重重归一正确（单项/双项/三项）；函数签名无任何 Action 类型入参（AST 级断言可选）；
  `FORMULA_DIGEST` golden 更新且 `validate_formula_manifest` 扩展项通过。
- **GREEN**：以上全绿 + 全量既有测试绿（digest golden 是唯一预期红转绿点）。

### Slice B — 状态 schema v2 + codec v4

- **改**：`state/models.py`（`LabelFreeState`、`V3State.label_free`、
  `PendingOutcome.label_free_eligible`、schema 2）；`state/codec.py`（v4 段、读 1–4）。
- **RED**（扩 `test_v3_state_codec.py` / `test_v3_state_budget.py`）：
  新 DTO 逐字段界校验拒错；`quantization_safe_bounds(PREF_OFFSET_BOUNDS)` 存储界
  接受 `float16(0.30)`；encode/decode 逐位往返；v3 旧 blob 解码 → `label_free=None`、
  `eligible=False`；最坏尺寸仍 < 64 KiB（有意用满 ring/buffer 的最坏状态重测）。
- **GREEN**：全绿；bridge/仓库层零改动（payload 就是字节，CAS 无感知）。

### Slice C — 双路径结算 + 更新律 + orchestrator/trace 接线

- **改**：新建 `v3core/learning/label_free.py`
  （`settle_label_free` → `LabelFreeSettlement`；L1/L2 更新律；与
  `ekf_transition_update` 共享抽出的对角 EKF 私有核）；
  `inference/policy_scorer.py`（`preferences(s, offset)`、`score_policy` 读
  `pre_state.label_free`）；`learning/outcomes.py`（`freeze_actual_prediction`
  传 offset）；`orchestrator.py`（§2.3 前置段、pending 冻结 eligibility、
  trace 新字段）；`contracts.py`（`ReactionFacts`）；`trace/models.py`（schema +1）；
  `v3bridge`（`same_sender` 冻结：surrogate 相等性，私聊恒 True）。
- **RED**（扩 `test_v3_outcome_learning.py` / `test_v3_orchestrator.py` /
  `test_v3_policy_scorer.py` / `test_v3_property_invariants.py` /
  `test_v3_trace_replay.py`）：
  UNKNOWN 动作 + 有效反应 → `label_free` 前进而 `action_beliefs` 不动
  （**这就是补上的那个洞，本片的验收主句**）；有标签 + 有反应 → 双路径同轮各自
  正确且单次提交；动作不可见性属性测试（对 pending.action/actual/shadow 任意扰动，
  L1/L2 输出逐位不变）；邻接断裂/资格缺失/reason 逐条删失；offset 凸组合有界性
  属性测试（随机序列 10^4 步恒在界内）；负反应衰减向 0；`preferences` 输出
  clip 到 [-1,1] 且 offset=0 时与 v1 逐位一致（回归锚）；trace 字节确定性重放 +
  16 KiB 帽；`v3_stability.py` 扩界后 100k-turn 门重跑（中性输入下 v1 包络不变）。
- **GREEN**：全绿 + 性能门（新增算量 O(8)，p95 预算复测过）。

### Slice D — 证据机器：replay/ablation/exporter

- **改**：`scripts/v3_replay.py`（prequential marginal-MAE、偏好加权 NLL、
  frozen/carry-forward 对照、置换控制流、覆盖率漏斗计数）；
  `scripts/v3_ablation.py`（LF-1..LF-4 门 + INSUFFICIENT_EVIDENCE 路径）；
  `scripts/v3_export.py`（用 v2core lexicon 纯读数在**弃文前**离线导出通道
  19–26 的派生密度值——文本本身依旧一个字节不出库；修 channel-13 误植；
  gap 离线不可得如实置无效并写进 manifest；turn 行新增
  `reaction_same_sender` 三值字段，见 §1.4 的确定性义务）。
- **RED**：合成语料**植入已知反应结构**（例如"高 valence 反应恒跟随高 y'_3"），
  断言 L1 恢复植入偏好方向、LF-2 过门、LF-4 置换后增益坍缩；frozen 对照在同语料
  上不动；无信号语料 → 两门如实不过 / 证据不足如实上报；导出器单测：派生通道
  数值等于 lexicon 直算、无任何原文/标识符字节落盘、privacy clamp 生效、
  channel 13 恢复 body.epoch 语义。
- **GREEN**：全绿；对现存 3/36 旧数据集跑一遍 LF 报告，预期输出
  `INSUFFICIENT_EVIDENCE`——这个"如实报饿"本身就是验收项。

每片一个 PR，走既有 per-wave 流程；命名先按 §18 术语门执行保守名
（`ReactionSignalV1` / `PreferenceOffsetLearnerV1` / `MarginalOutcomePredictorV1`），
"偏好学习/自我进化"字样等 LF 门通过后才准出现在对外文案里。

---

## 8. 诚实总评

这条通道能不能把"自我进化证据为零"变成非零？**能，但只在它真正主张的那一格里，
而且有两个前置条件。** 它把可打分面从"必须有动作回执"（当前真实覆盖率≈0）换到
"必须有相邻用户反应"（活流量上结构性存在），所以 LF-1 几乎立刻就能在真数据上出
非零证据——那是世界模型预测质量的证据。LF-2 出的则是"偏好密度贴合了这个用户的
反应分布"的证据，带着已声明的部分循环性，靠置换门撑腰。两个前置条件：一是语气
通道的 lexicon 读数得有起码的信噪比（词表烂则 LF-4 会把它杀掉，通道如实判负而
不是假装成功）；二是数据量——按 §3.2 的速率算，偏好可见漂移要 100–150 个真实
turn，证据底线设在那里，不到就是 INSUFFICIENT_EVIDENCE。而它换不来的东西也要说
死：**"v3 的决策更好"的证据依然是零，且在影子模式下将永远是零**——这不是这条
通道的失败，是影子的定义；任何把 LF 门的绿灯宣传成策略优越性的措辞，都该被 §18
术语门当场打回。一句话：这不是换个更诚实的饿法，是把餐桌从没有食物的房间挪到了
有食物的房间——但桌上摆的是偏好和世界模型，不是动作信用，谁也别谎报菜单。
