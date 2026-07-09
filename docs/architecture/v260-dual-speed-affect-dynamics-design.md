# v2.6.0 设计：统一双速情感动力学（Unified Dual-Speed Affect Dynamics）

状态：设计经**两轮对抗评审**（fable 数学攻击 9 条 + opus 仓库攻击 8 条，合计 17 修，账本见 §10）收敛，用户批准**单版本节奏**落地。**本文是实现契约。**

- 日期：2026-07-09
- 当前基线：`merge-ng-to-main` / `metadata.yaml:5` 版本 `2.4.0`
- 目标版本：`Sylanne-Embodiment 2.6.0`
- 前置核查存档：memory `v260-predesign-ground-findings` / `v260-dynamics-design-v1`。所有 file:line 对照本分支 HEAD。

---

## 0. 执行摘要

### 0.1 一句话

把当前**并列且大半断线**的 8 个情绪状态存储收编成**单一情绪核 E**：用**墙钟惰性衰减**给它时间维度，用**双速更新**（快通道 = 每轮 appraisal，慢通道 = poignancy 触发反思）给它动力学，再用**确定性输出合同**保证它真的到达 LLM。所有心理学参数是人格函数（人格驱动全参数）；慢通道输出反哺快通道物理规律，构成闭环。

### 0.2 为什么（三条地基断链，前置核查实测）

| 断链 | 现状证据 | 本设计如何修 |
|---|---|---|
| warmth 死链 | `body_port_v2.py:92` VoidScar warmth 实测 ≈0.005，被绕过 | E 收编 8 维为唯一真源；warmth **继承**已生效的 temperature 信道（:96-102）为输入，非删；行为标定验收门（§7） |
| 无真实 idle 时钟 | `phase_transition.py:150` 是 tick 计数；`personality.py:269` sustained_silence 因 route 硬编码不可达；`void_calculus.py:21` SilenceTexture 全死代码 | 墙钟 Δt_wall 惰性衰减 + 沉默 appraisal，喂回 phase_transition 既有消费点（§2.3） |
| self_score 失准驱动不可逆漂移 | `turn_runner.py:220-262` 门 0.7 vs 真机好回复 0.4-0.5；喂 `personality.py:82-86` 的 `dialogue_quality_high`(+expr/relational)/`_low`(−) 双向门。门虽双向，但 0.7 失准致好回复卡 0.3-0.7 死区、正向漂移几乎不触发 → 有效漂移偏保守/失活 | 漂移改 q_dc 直流分量门 + 锚回弹，均衡点 = 体验积分而非随机游走（§4.2） |

### 0.3 关键决策

- **收编而非叠加**。8 个 store + 两条确认死链 + 一条 workaround，本身就是并列架构失败的证据。E 成为 affect 唯一真源；scar/void 作为一等公民保留（对 Sentipolis 的差异化 = 论文 baseline）。
- **单版本节奏**。不切三个发布："影子先行 → 接管 → 权威切换"降级为 2.6.0 开发期内的**三道验收关口，不是三次发版**。理由：不上线不会污染用户；但影子并跑（抓死链）与漂移可回滚快照（运行时保险）作为**手段**原样保留。
- **`DeterministicFusion` 退役推 2.7**。它现为接口器官：脊柱按 `ResonanceField` 形状长成，`apply_personality`（`resonance_integration.py:228-300`）从它派生 15+ 下游参数。拔它是器官移植，blast radius 过大，2.6.0 不动。
- **不新增每轮 LLM 调用**。a_k 由现有异步 assessor 的三标量 + 意图**确定性投影**得到；慢通道复用生活模拟已有的反思预算通道。

---

## 1. 现状判断（收编对象清单）

前置核查确认 8 个 affect-adjacent 状态存储。逐一给出 2.6.0 去向，无一悬空：

| # | 存储 | 位置 | 2.6.0 去向 |
|---|---|---|---|
| 1 | VoidScarEngine / ScarredState（8 维 base + wound_threshold/healing_rate） | `void_scar_engine.py:69` / `scar_algebra.py:113` | **E 的物理承载**：E 读它的 8 维 base；wound→scar 迁慢通道算子（§4.2a） |
| 2 | DeterministicFusion 场 | `deterministic_fusion.py:86` | 保留至 2.7；`sync_order`/`energy` 继续喂表达决策 |
| 3 | HotPool 温度 | `hot_pool.py:693`（×0.9/tick 衰减） | 温度 → arousal appraisal 输入；tick 衰减由墙钟衰减取代 |
| 4 | 人格/embodiment traits | `personality.py` / `resonance_integration.py:228-300` | **动力学参数源**：所有 λ/G/Θ/Φ_eq 派生自此（§8） |
| 5 | 每会话人格 delta | `resonance_integration.py:899-913` | 不动（身份门控关系层，另线） |
| 6 | BodySnapshot | `contracts.py:42-77` / `body_port_v2.py:80-149` | warmth 维接 E；量纲 [0,1]→[−1,1] 转换层（§7 关口 B） |
| 7 | ShadowMemory | `shadow_memory.py:70-120` | 不动（internal_only advisory） |
| 8 | ExpressionPolicy/MetaLearner 调参态 | `resonance_integration.py:196-223` | 不动 |

唯一确认注入路径：`fragment.py` `build_mind_fragment()` → `integration.py:809-826` `system_prompt` 追加，符合"只进 system_prompt"铁律。§6 的输出合同即建在这条路径上。

---

## 2. 核心状态 E 与衰减律

### 2.1 状态

```
E ∈ [0,1]^8   维序沿用 VoidScar base：
              [warmth, arousal, valence, tension, curiosity,
               repair_pressure, expression_drive, boundary_firmness]
持久化三元组: (E, last_ts, ver)
```

- `ver`：单调递增版本号，防并发丢更新（§3.4）。
- 载入：随 `host.load` **异步预取**进内存态；热读路径纯数学、零 KV IO（KV `put_kv_data/get_kv_data` 是 async，框架红线要求 IO 移出 session 锁）。

### 2.2 惰性衰减（墙钟）

无后台 ticker。任何读 E 的调用点，先按真实流逝时间结算闭式解：

```
E(t) = E_eq + (E₀ − E_eq) ⊙ exp(−λ ⊙ Δt_wall)

E_eq = Φ_eq(T, R) ∈ [0.15, 0.85]^8      人格 T + 关系 R 决定的常驻基线
                                          值域强制内收 → 均衡永不在角落（反吸收态①）
λ_i  = ln2 / h_i
h_i  = h_base_i · g_i(T) · min(1 + σ·scarload_i, 3)
                                          半衰期是人格函数；活跃伤痕使维度粘滞
                                          σ·scarload 封顶 ×3（反吸收态②）
scarload_i 由 healing_rate(T) 自愈衰减（反吸收态③）
```

三条"反吸收态"约束是 fable 攻击 #3 的解药。该攻击给出的棘轮链共 5 环：吵架日 → ① scar 巩固 → ② 半衰期变长 → ③ 情绪一致召回专挑吵架记忆 → ④ 传染续命 → ⑤ 再巩固。斩环分工必须完整交代，因为单靠本节三条不够：

- **本节三条斩衰减/均衡/粘滞侧**：粘滞封顶斩 ②（半衰期不再无界变长）；E_eq 值域内收斩 ② 的均衡落点（均衡永不落角落）；scarload 自愈斩 ① 的累积（伤痕不再只进不出）。
- **③④ 召回-传染子环由 §5 单独斩**：α > δ 令相关性主导召回，每轮传染 nudge 封顶。
- **⑤ 这条闭合环靠一个关键结构事实断掉：情绪传染只 nudge E，不喂 p_k/π**。传染续命不会重新累积 poignancy、不会重触发 scar 巩固——⑤ 在数学上根本连不回 ①。

三处协同才是完整解。

### 2.3 沉默 appraisal（替代死掉的 idle 时钟）

读态时若 `Δt_wall > τ₁(T, R)`，在读取点合成一次沉默 appraisal（人格化：repair_pressure↑、warmth 微降等）。关键约束：**必须继续喂 `phase_transition` 的既有消费点**——不能只改计数器语义（opus 攻击 #6）：

- `express()` urgency = `silence_duration/_silence_urgency_divisor`（`phase_transition.py:242`）；
- `silence_lowers_threshold`（`phase_transition.py:272-275`）；
- `should_express`（`phase_transition.py:222`）；
- `_silence_urgency_divisor = 5.0 + patience·15.0` 是人格函数（在 `apply_personality` 内计算，`resonance_integration.py:275`；`phase_transition` 只经 `set_personality_params`（:163/169）消费，不自算），保留。

`void_calculus.py:21` 的 `SilenceTexture`（WAITING/DIGESTING/DISTANT/CONTENT）此前全死；本设计激活它作为沉默 appraisal 的分类器，喂真实 Δt_wall。

---

## 3. 快通道（每轮一次，零新增 LLM）

### 3.1 appraisal 投影 a_k

现有 assessor 真实出参只有 `{v∈[−1,1], a∈[0,1], w∈[0,1], i:str}`（`assessor_async.py:206/261-285`；注意 `w=wound_risk`，非 warmth）。8 维 appraisal 由**确定性投影**得到，不改调用数：

```
记 v⁺=max(v,0), v⁻=max(−v,0)。a_k ∈ [−1,1]^8：

a_valence   = v
a_arousal   = a − 0.3                                   0.3 = 中性点
a_warmth    = 0.5·v⁺·(1−w) − 0.4·w·v⁻ + δ_warmth(i)     仅增量通道，系数刻意小
a_tension   = 0.7·w + 0.3·v⁻·a − 0.2·v⁺·(1−w) + δ_tension(i)
a_repair    = 0.6·w·v⁻ + δ_repair(i)
a_curiosity = 0.2·a·v⁺ + δ_curiosity(i)                 线性部分弱，主靠意图
a_expr      = 0.5·a·(0.5+0.5·v) + δ_expr(i)             连续化现 arousal>0.7 阶跃
a_boundary  = 0.3·w·(1−v⁺) + δ_boundary(i)

投影末端统一 clamp：a_k ← clip(a_k, −1, 1)（执笔期存疑 2）。
理由：线性 + 意图偏置叠加可越界，如 a_tension 在 w=1,v=−1,a=1,意图=生气 时达 1.4。
clamp 作用于 appraisal 增量、不作用于状态 E，故不影响 §3.3 饱和更新的有界性。
```

线性部分秩仅 3，curiosity/boundary 几乎全靠意图偏置——**影子期必须监控这两维方差，接近零 = warmth 0.005 同款死链前兆**，触发升级路径（fast prompt JSON 从 4 键扩 8 键，调用数不变）。

系数全进 config 作先验，影子期用真对话标定。此投影的本质，是把 `computation_spine.py:541-580` `_inject_assessment` 的手写阶跃规则（w>0.7 才打伤痕、intent 只精确匹配"撒娇"/"生气"两词）连续化、可标定化。

### 3.2 意图归一化 + 偏置 δ_intent

`i` 是自由字符串（截 20 字），精确匹配两词会漏九成意图。前置归一化器把自由串收进约 8 个规范类；未识别落零偏置**且必落日志**（影子期看 unmatched 分布回扩别名表）：

```
撒娇/亲昵   → warmth+0.3  tension−0.2 expr+0.1
生气/指责   → tension+0.4 warmth−0.2  boundary+0.2
道歉/求和   → repair−0.4  warmth+0.2  tension−0.2
提问/求助   → curiosity+0.3 expr+0.1
分享/报喜   → curiosity+0.2 warmth+0.15 expr+0.2
冷淡/敷衍   → warmth−0.15 expr−0.2
越界/施压   → boundary+0.4 tension+0.2
未识别      → 0（落日志，计数器暴露 admin）
```

主评估白回传的 `subtext`/`avoidance`（`assessor_async.py:274-279`）是宝（回避→boundary、潜台词→repair），但为字符串，留给 8 键扩字段那次一起吃，2.6.0 不贪。

### 3.3 饱和快更新

v0 用 clamp，被 fable 攻击 #1 证死：密聊冲击流入（~2.0/h）比衰减回拉（λ·range≈0.2/h）大一个数量级，clamp 会把 E 钉死在角落。改饱和式：

```
E ← E + G(T)⊙[a_k]₊⊙(1 − E) − G(T)⊙[a_k]₋⊙E
其中 [a]₊ = max(a,0)、[a]₋ = max(−a,0)，均为非负幅度；正向项加、负向项减。
```

符号裁决（执笔期存疑 1）：`[·]₋` 取非负幅度约定（同 §3.1 的 `v⁻`），故负向必须用**减号**——负 appraisal 拉低 E，且 E→0 时降幅 →0（`⊙E` 因子）。验收断言：负 appraisal 使对应维单调下降、近下界处降幅趋零。离边界越近增量越小。**诚实性质声明**（修正 v0 的错误声明）：对话内允许情绪顶满——激烈聊天本该顶满，拟人不是 bug；散场后靠 §2.2 衰减指数回 E_eq。E_eq 内收 + scar 封顶 + 自愈 ⇒ 不存在回不来的状态。人格增益 `G(T)` 在投影之后乘（神经质→tension 增益↑，外向→expression_drive 增益↑）。

### 3.4 并发（assessor 异步回写竞态）

assessor 是异步的，快更新回写 E 发生在回复之后。用户秒回时下一轮已读旧 `(E,ts)`，read-modify-write 竞态致 a_k 丢失或衰减重复结算（2c2g 单进程不豁免 async 交错）。**(E, ts, ver) 按会话串行化 / CAS**：回写前校验 ver，不匹配则重新结算衰减后再合入。

---

## 4. 慢通道（poignancy 触发反思）

### 4.1 累积与触发

```
p_k = ‖w_p ⊙ a_k‖₁                     本轮情感冲击强度
π   ← (1 − μ(T))·π + p_k                漏桶累积；漏率 μ 挂人格
触发: π ≥ Θ(T)  且  距上次反思 ≥ τ_refl(T)   墙钟冷却
```

墙钟冷却是 fable 攻击 #4 的解药：π 按轮累积，200 轮/日的高频日会频繁触发，致双速退化单速并烧预算。冷却按墙钟而非轮数。

**失败语义（记忆红线，不准 fail-open）**：反思**预算前扣**（尊重深睡零 LLM 先例的预算纪律）；预算被拒或 LLM 失败时 **π 保留、幂等重试**——绝不 `π←0` 丢弃 poignancy。v0 的"触发后 π←0"在失败路径上是 fail-open，已废。

### 4.2 触发内容

触发后并行做两件事，**成功后才 `π←0` 并落快照**：

**(a) 伤痕巩固**。现有 VoidScar wound→scar 逻辑整体迁为慢通道算子（`computation_spine.py:546-552` 的 w>0.7 注入搬来）；scarload 反哺 §2.2 的 λ 粘滞。

**(b) 人格漂移**。v0 用纯 self_score z-score，被 fable 攻击 #2 证死——自适应均值会把持续好体验归一化吃掉（E[q̂]≈0 ⇒ T*≈T_anchor，从失控换成死寂）。改双分量：

```
T ← T + η·q_dc·u − ρ·(T − T_anchor)      仅在漂移显著性门通过时执行

u    = 漂移方向（本次累积体验指向的 trait 方向单位向量）
q_dc = EMA_slow(s) − s_ref               直流分量：相对一次性标定基准的持续偏移 → 幅度
z    = (s − μ_EMA)/max(σ_EMA, σ_min)     截 ±2；故 z_gate ∈ (0,2) 必约束，典型 1.0
均衡点: T* = T_anchor + (η/ρ)·E[q_dc·u]   漂移 = 持续体验的积分
```

`z_gate` 硬约束（执笔期存疑 3）：`z` 截断到 ±2，若配 `z_gate ≥ 2` 则 `|z|≥z_gate` 永不成立、漂移步静默失活。config 载入须断言 `0 < z_gate < 2`。

**漂移显著性门 = z**。反思事件恒做伤痕巩固；漂移步**仅当 `n≥20` 且 `|z|≥z_gate` 才执行**——这次体验相对基线足够离群才漂。门不过（冷启动 `n<20`：EMA 统计量不可靠、σ→0 会让 z 爆；或 `|z|<z_gate`）则**跳过漂移步，伤痕巩固不受影响**。故 §8 "n<20 关闭漂移" = 关闭漂移步这一子步，非关闭整个反思事件。分工明确不重叠：`z` 只当门（是否漂），`q_dc·u` 定漂移的方向与幅度（漂多少）。

`s` 仍取 self_score（`dialogue.py:189`），但**不再用其绝对 0.7 门**——0.7 vs 真机 0.4-0.5 的失准问题被"相对基准 s_ref"绕过。周漂移速度 `‖ΔT‖` 落日志（自家 mini stability index）。T 写盘带**版本环形缓冲，可回滚**——不可逆漂移属红线（§7 关口 A）。

---

## 5. 记忆情感耦合

```
写入: m.e = 写入时 E 快照 ∈ [0,1]^8,  m.p = p_k
召回打分: score = α·relevance + β·recency + γ·importance + δ·cos(E_now, m.e)   约束 α > δ
情绪传染: 高情绪记忆被召回时  E ← E + κ(T)·(m.e − E)，每轮总 nudge 封顶
```

`m.e` 取值裁决（执笔期存疑 4）：**定死为写入时 E 状态快照，非 a_k**。理由：a_k∈[−1,1]^8 是含负的瞬时 appraisal 增量，若入 `cos(E_now, m.e)` 则跨量纲比较、入传染 `E←E+κ(m.e−E)` 会把 E 拉向负值域越界。E 快照与 E 同空间 [0,1]^8，两处均自洽——召回比的是"当时的情绪状态"与"现在"的相似度，语义也对。

- emotion 因子插进既有拟人多因子召回设计预留的 emotion 槽（见 memory `memory-recall-humanlike-redesign`）。
- `α > δ` 硬约束防"情绪劫持召回"：mood-congruent 回路有意保留（拟人），但相关性仍主导；配合 §2.2 衰减律三件套防走死（斩棘轮 ③④ 环）。
- `κ`、`μ` 是人格函数。fable 攻击 #7 指出 v0 把它们写成裸常数，违背人格驱动全参数，已修。

---

## 6. 输出合同（反死链核心）

E 算得再对，到不了 prompt 就是下一条 warmth 死链。本节把"E → LLM 可见文本"定成确定性合同。

### 6.1 确定性词表映射

```
label = LUT(quantize(E_key4维, 3级)) + 强度副词
```

- 人设情绪词表手工策划约 24 词 + 强度副词：确定性、可审计、**零语料依赖**——绕开 Sentipolis KNN 要标注锚点语料的死结。
- **滞回带 θ_h**（fable 攻击 #6）：跨格且越过边界余量才换词，格内绝不换。防 E 在量化边界（如 valence 0.33）逐轮抖动，致语义相反词来回翻跳。

### 6.2 fragment 保底预算

现状情绪行是 STATE 档，salience = `_SAL_EMOTION_BASE(1.0) + warmth`（`fragment.py:49/143/304-315`），**低于 memory 的 3.0（`fragment.py:47`），预算紧时先于记忆被驱逐**——与设计目标正相反（opus 攻击 #7）。

修：情绪行升 **PINNED 档或独立 floor 预算约 60 字符**，改 `_pack_within_budget`（`fragment.py:241-290`）。注入仍只进 `system_prompt`（`integration.py:809-826`）。

### 6.3 不变量测试（防死链回归）

- 跨格 ⇒ fragment 文本必变；同格 ⇒ label 必不变（滞回带下良定）。影子期（关口 A/T2）对影子 fragment buffer 断言即可。
- E 设值 ⇒ `request.system_prompt` 端到端断言，专防"算了但没到 prompt"这类死链。**此条 = 关口 B/T3 接管后生效**——影子期 E 不进生产 `request.system_prompt`，故不能在 T2 断言生产对象。
- 60 字符保底、3 级量化是**表示层结构常数，豁免人格函数化**。这是 fable 攻击 #7 的边界：否则 420 预算也得挂人格，无穷退化。理由在此明示。

---

## 7. 收编映射 / 迁移安全 / fail-closed

单版本节奏内三道验收关口（**关口非发版**，见 §0.3）：

### 关口 A — 影子期（强制；opus 攻击 #3：不可逆漂移是红线）

E 全链路计算 + 落日志 + WebUI 可视，**不写 body、不进 prompt、不落盘漂移**，与旧路径并跑比对 N 轮。监控两项：curiosity/boundary 两维方差（§3.1 死链前兆）、warmth 行为标定。

### 关口 B — 接管期

过验收后 E 接管 fragment 情绪行 + BodySnapshot warmth 维（量纲 [0,1]→[−1,1] 转换层）。warmth **继承** `body_port_v2.py:96-102` 已生效的 temperature 映射为输入，**不删**——opus 攻击 #5 认定 :96-102 是实机修出来的活信道，非死代码。清理 `webui_server.py:3838` / `webui_routes.py:539` 两处 0.45 兜底。记忆情感标签 + 召回因子 + 传染小步开。

### 关口 C — 权威期

E 成唯一真源；VoidScar wound→scar 迁慢通道算子；漂移换 q_dc 门（带回滚快照）。**`DeterministicFusion` 退役移出 2.6.0 → 2.7**：`apply_personality` 派生的 `_field._coupling.broadcast._threshold` / `_field._dissipation` / `_field._residual_decay` + meta_learner 覆写 + A7 公理链（`resonance_integration.py:228-300`）需逐个找到新宿主才准动刀。

### 冻结面 / 验收门

- **对外集成面冻结**：大饼桥 / public_api / 事件钩子对外零变化（第 5 铁律）。
- **迁移安全**：不改 `to_dict/from_dict` 格式；老 VoidScar 存档平滑迁移（`DeterministicFusion.from_dict` 已示范惰性字段兼容）。
- **warmth 行为标定验收门**：复用 7 级温度词双裁判方法（见 memory `warmth-mapping-behavioral-calibration`）——warmth 读数必须随情境真实单调变化，才算修复；否则只是把 0.45 常数换成 Φ_eq 常数，同类死链换名（fable 攻击 #8）。
- **fail-closed 总纲**：漂移写盘失败、验章失败、预算拒绝——一律偏向不写/保留/重试，**绝不降级执行或丢弃**。

---

## 8. 参数表（全部人格函数，人格驱动全参数）

| 参数 | 含义 | 人格依赖 | 冷启动 |
|---|---|---|---|
| `Φ_eq(T,R)` | 情绪常驻基线 | 全 8 维 f(traits, 关系相位) | 值域 [0.15,0.85] |
| `h_base_i·g_i(T)` | 半衰期 | 高神经质→tension 半衰期长 | — |
| `σ·scarload` | 伤痕粘滞 | healing_rate(T) 自愈 | 封顶 ×3 |
| `G(T)` | 快更新增益 | 神经质→tension↑，外向→expr↑ | — |
| `μ(T)` | poignancy 漏率 | 神经质→漏得慢→更易积成反思 | — |
| `Θ(T)` | 反思阈值 | — | — |
| `τ_refl(T)` | 反思墙钟冷却 | — | — |
| `τ₁(T,R)` | 沉默 appraisal 阈 | patience 相关 | — |
| `κ(T)` | 情绪传染系数 | — | 每轮封顶 |
| `η, ρ` | 漂移步长 / 锚回弹 | — | — |
| `u` | 漂移方向（trait 方向单位向量） | 本次体验指向 | — |
| `z_gate` | 漂移显著性门阈 | — | 硬约束 0<z_gate<2；n<20 或 \|z\|<z_gate ⇒ 跳过漂移步 |
| `s_ref, σ_min` | 漂移基准 / 方差地板 | 一次性标定 | — |
| `θ_h` | LUT 滞回带 | — | 表示层常数 |
| 60 字符 floor / 3 级量化 | 表示层 | **豁免**（§6.3 明示理由） | — |

---

## 9. 每轮工作流

```
0 载入   host.load 异步预取 (E, ts, ver) 进内存态
1 读态   纯数学结算衰减(Δt_wall)；Δt>τ₁ ⇒ 合成沉默 appraisal + 喂 phase_transition 消费点
2 召回   emotion 因子参与打分(α>δ)；高情绪记忆 nudge E(κ 封顶)
3 注入   组 fragment(情绪行 PINNED 保底) → system_prompt → LLM 出回复
4 回写   assessor 回 (v,a,w,i) → 确定性投影 a_k → 饱和快更新 → 持久化(串行/CAS)
5 累积   π 漏桶累积；记忆写入带 (m.e, m.p)
6 慢速   π≥Θ 且过墙钟冷却 ⇒ 预算前扣 ⇒ 伤痕巩固 + 漂移(q_dc 门) + π←0 + 快照
         失败 ⇒ π 保留、幂等重试（不 fail-open）
主动路径  调度器惰性读同一个 E；urgency = f(Δt_wall, expression_drive)；quiet_hours 链不动
```

闭环收束：慢通道输出（伤痕巩固改 λ 粘滞、人格漂移改 Φ_eq/G/Θ）**重写快通道物理规律**——她经历的事，真的改变她情绪流动的方式。

---

## 10. 红队账本（17 修，供未来的我追溯每个旋钮的来历）

**fable 数学攻击（9）**：① clamp→饱和更新（稳定性硬伤）；② 纯 z-score 漂移自毁→q_dc 双分量；③ 反吸收态三件套（自愈/封顶/E_eq 内收）；④ 墙钟冷却 + 失败保留 π；⑤ (E,ts,ver) 串行/CAS；⑥ LUT 滞回带 + 测试改跨格语义；⑦ κ/μ 挂人格，结构常数豁免明示；⑧ warmth 需行为标定门（否则换名死链）；⑨ 过度工程→单版本 + 影子先行。

**opus 仓库攻击（8）**：① assessor 仅 3 标量 → 确定性投影，8 键扩字段留后期；② E 收编 VoidScar 8 维（禁双真源），量纲统一；③ 影子先行强制 + 可回滚快照（不可逆漂移红线）；④ 2.6.0c blast radius → DeterministicFusion 退役推 2.7；⑤ warmth :96-102 是活信道，继承非删 + 清 webui 两处兜底；⑥ 沉默换墙钟须喂 phase_transition 老消费点；⑦ fragment 情绪行会先被驱逐 → PINNED 保底；⑧ KV 异步 → host.load 预取，热读零 IO。

---

## 11. 实现排序（单版本内）

依赖顺序经 opus 攻击 #7 校验：无 a 阶段隐藏耦合到 c。

1. **T1 · E 核 + 衰减 + 投影**（关口 A 影子）：新增 E 状态模块、墙钟惰性衰减、a_k 确定性投影 + 意图归一化器（带 unmatched 日志）、(E,ts,ver) 持久化 + host.load 预取。纯计算 + 落日志，不接 body/prompt。
2. **T2 · 输出合同 + 不变量测试**（关口 A 影子）：LUT 词表 + 滞回带、fragment PINNED 保底改 `_pack_within_budget`。此时仍影子——不变量测试只对**影子 fragment buffer** 断言跨格/同格（§6.3 前两条）；`request.system_prompt` 端到端断言留到 T3（接管后 E 才真进 prompt，影子期它不进）。
3. **T3 · warmth 行为标定 + 接管**（关口 B）：7 级温度词双裁判验收；过门后 E 接管 fragment 情绪行 + BodySnapshot warmth（继承 temperature 映射）；清 webui 两处 0.45。
4. **T4 · 记忆情感耦合**（关口 B）：写入 (m.e,m.p)、召回 emotion 因子(α>δ)、传染 κ 封顶。
5. **T5 · 慢通道 + 漂移**（关口 C）：poignancy 漏桶 + 墙钟冷却 + 失败保留、伤痕巩固迁慢通道算子、q_dc 漂移门 + 回滚快照。
6. **T6 · 权威切换**：E 成唯一真源，退旧读路径。（DeterministicFusion 退役 = 2.7，不在本表。）

流程纪律：每个 Tn 独立分支 + PR 合进 next-gen（合并天花板，绝不进 main）；红线段（漂移/记忆写）合并前跑对抗闸专猎 fail-open（见 memory `redline-premerge-adversarial-gate`）；用户亲自实机验收前不 push（见 memory `push-only-after-user-verification`）。

---

## 12. 待核验（论文对标，非设计前提）

设计从第一性原理 + 截止前可靠文献（PAD/Mehrabian、WASABI/ALMA 衰减情绪、OCC/Scherer appraisal）直接推导，**不依赖下列论文成立**。以下仅为 scar_void 论文对标 baseline 与参数定标，需亲手核验后再引用：

- Sentipolis（arXiv 2601.18027，自称 ACL Findings 2026）：存在性 + "150% 情感连续性"指标操作化定义 + KNN 是否随论文带标注锚点语料。
- CTEM/Auri（自称 CHI 2026）：venue + 是否伴侣 IM agent + 行为清单是否每轮额外 LLM 调用（决定 2c2g 可行性）。
- ICLR 2026 动态组合 persona vectors + Agent Stability Index。

CTEM 行为清单（把主动对话升级成"她自己有生活"）是 2.6.0 之后的独立方向；本设计的墙钟 idle 时钟为其铺好地基。

---

## 附：执笔期存疑裁决记录（已裁决）

fable 执笔位逐条核对公式与声明时逮出 4 处真缺陷；主循环全部裁为 **CONFIRMED 并已修入正文**（对应 §3.3 / §3.1 / §4.2+§8 / §5）。原疑点记录于此，追溯用，勿删：

1. **§3.3 饱和更新第三项的符号约定疑似与 §3.1 冲突**。§3.1 定义 `v⁻ = max(−v, 0)`（非负）；若 `[a_k]₋` 沿用同一约定（非负），则 `E ← E + G⊙[a_k]₊⊙(1−E) + G⊙[a_k]₋⊙E` 的第三项为正加项，负 appraisal 反而抬升 E，与"双向饱和、离边界越近增量越小"的意图相反。若 `[a_k]₋ := min(a_k, 0)`（保留负号）则公式自洽。公式按冻结原样保留；请裁决明示 `[·]₋` 的符号约定，并建议实现时以"负 appraisal 使 E 下降、且 E→0 时降幅→0"为验收断言。
2. **§3.1 声明 `a_k ∈ [−1,1]^8`，但 a_tension 极值可越界**。取 w=1、v=−1、a=1、意图=生气/指责（δ_tension+0.4）：a_tension = 0.7 + 0.3 + 0.4 = 1.4 > 1。需裁决是否在投影末端统一 clamp 到 [−1,1]（clamp 不影响饱和更新稳定性，但契约需明示），或接受声明值域为近似。
3. **§4.2 `z` 截 ±2 与 `z_gate` 可达性存在隐含约束**：若配置 `z_gate ≥ 2`，漂移门永不通过，漂移步静默失活。§8 参数表未标注 `z_gate < 2` 约束，建议 config 校验加断言。
4. **§5 `m.e = a_k（或 E 快照）` 的二义未决且量纲不同**：a_k ∈ [−1,1]^8 而 E ∈ [0,1]^8。若 m.e 取 a_k，则召回项 `cos(E_now, m.e)` 跨量纲比较、传染项 `E ← E + κ·(m.e − E)` 会把 E 拉向负值域；若取 E 快照则自洽。T4 开工前需定死取哪个（或定义统一转换层）。
