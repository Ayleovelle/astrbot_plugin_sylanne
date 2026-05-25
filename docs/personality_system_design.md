# Sylanne-Embodiment 双向人格系统设计文档

## 0. 理论基础与文献支撑

本设计的每个核心机制都有对应的学术文献支撑：

### 不可逆后果与躯体性

| 机制 | 文献 | 核心论点 |
|------|------|----------|
| 不可逆伤痕改变未来感知 | [Mopgar (2026.03) — Teaching Agents to Feel the Weight of Irreversible Consequences](http://arxiv.org/abs/2603.14531v1) | 提出 Emotional Cost Functions：agent 需要"定性痛苦状态"作为不可逆后果的叙事表征，持续影响未来决策 |
| Agent 需要"躯体"来接收后果 | [Hu & Rong (2026.05) — Some[Body] Must Receive That Pain](https://arxiv.org/abs/2605.16872) | 论证 AI agent 需要一个持续存在的"身体"来承载后果，否则问责无从谈起。Sylanne 的 Scar Algebra 正是这个"身体" |
| 物理躯体性允许开放式演化 | [The Contingencies of Physical Embodiment (2024)](https://arxiv.org/html/2510.07117v2) | 基于海德格尔现象学：being-in-the-world + being-toward-death 是开放式行为的最小条件 |

### MoE 路由可靠性

| 机制 | 文献 | 核心论点 |
|------|------|----------|
| 路由质量直接影响事实准确性 | [When Are Experts Misrouted? (2025)](https://arxiv.org/html/2605.07260v1) | 对 MoE 路由进行反事实分析，证明错误路由是幻觉的直接原因 |
| MoE 在长尾知识上更脆弱 | [Counterfactual Routing to Mitigate MoE Hallucinations (2025)](https://arxiv.org/abs/2604.14246) | 稀疏 MoE 在长尾知识上特别脆弱，提出反事实路由缓解方案 |
| MoE 整体可靠性评估 | [MoE-RBench — Towards Building Reliable MoE (ICML 2024)](https://arxiv.org/abs/2406.11353) | 首个 MoE 可靠性基准，证明配置得当时 MoE ≥ Dense |
| 负载均衡影响训练稳定性 | [Routing-Replay-Guided Load Balancing (2025)](https://arxiv.org/html/2605.08639v1) | 历史负载预测在剧烈波动下失效，需要 replay-guided 方法 |

### 人格动力学与稳态调节

| 机制 | 文献 | 核心论点 |
|------|------|----------|
| 人格驱动 agent 行为一致性 | [Structured Personality Control and Adaptation (2025)](https://arxiv.org/abs/2601.10025) | 演化的、人格感知的 LLM 支持连贯的上下文敏感交互 |
| 动态人格模拟（双系统架构） | [Evolving Agents — Interactive Simulation of Dynamic Personalities (2024)](https://arxiv.org/abs/2404.02718) | 提出 Personality + Behavior 双系统架构，含 Cognition/Emotion/Character Growth |
| 人格作为持续自主性的组织原则 | [Persistently Autonomous Embodied Agent with Personalities (2026)](https://arxiv.org/abs/2603.00117) | 人格特质提供内在组织原则，类似基因型偏置塑造行为倾向 |
| 显式状态动力学防止人格漂移 | [Controlling Long-Horizon Behavior with Explicit State Dynamics (2025)](https://arxiv.org/abs/2601.16087) | LLM agent 在长交互中出现突变，需要显式时间结构治理 agent 级状态 |
| 稳态调节作为 RL 框架 | [Linking Homeostasis to Reinforcement Learning (2025)](https://arxiv.org/abs/2507.04998) | 生物 agent 通过学习的预测控制优化内部状态，稳态调节是核心 |
| 稳态神经网络适应概念漂移 | [Homeostatic Neural Networks Adapt to Concept Shift (2022)](https://arxiv.org/html/2205.08645v2) | 引入人工稳态调节，使网络在保持稳定的同时适应分布变化 |
| 稳态调节可能在网络中引入不稳定 | [Stability of Neuronal Networks with Homeostatic Regulation (2015)](https://pmc.ncbi.nlm.nih.gov/articles/PMC4495932/) | 警告：对单神经元稳定的稳态控制可能在循环网络中引入振荡——需要振荡检测机制 |

### 我们的设计如何对应文献

| 我们的机制 | 对应文献概念 | 创新点 |
|-----------|-------------|--------|
| Dual-EMA 防冲击 | EWMA 波动率模型 + 稳态调节 | 将金融风控的双时间常数 EMA 应用于人格稳定性 |
| Embodiment 五维 | Big Five → 计算参数映射 | 不是标签，是真正驱动 26+ 计算参数的函数 |
| 计算栈驱动漂移 | Evolving Agents 的 Character Growth | 不依赖 LLM 叙事，用形式化信号（scar count, void pressure）驱动 |
| 主权免疫系统 | Safe Learning Under Irreversible Dynamics | 在不可逆系统中加入"求助"机制（保护性解离） |
| 振荡检测 | Stability of Neuronal Networks | 直接回应稳态调节可能引入振荡的警告 |
| 不可逆伤痕 + 可恢复压力 | Mopgar 的 Emotional Cost Functions | 区分"记忆"（永久 ghost）和"急性痛"（可恢复 pressure） |

## 1. 设计哲学

Sylanne 的人格不是配置文件里的静态数字。它是一个活的、会呼吸的动力系统：

- 事件塑造人格，人格塑造对事件的感知
- 单次冲击留下痕迹但不改变骨架
- 持续模式才能重塑深层结构
- 越老的人格越稳定，但永远不会完全固化

## 2. 双层 Trait 架构

### 2.1 Embodiment 五维（深层结构）

| 维度 | 代码名 | 语义 | 驱动什么 |
|------|--------|------|----------|
| 表达驱力 | `expression_drive_trait` | 她有多想说话、多想被看见 | 表达阈值、社交压力权重、refractory |
| 感知锐度 | `perception_acuity` | 她对伤害/缺席的敏感程度 | 检测阈值、coupling rate、healing 速率 |
| 边界通透 | `boundary_permeability` | 她多容易接纳新事物、允许改变 | void 创建冷却、split 阈值、rotation angle |
| 内在秩序 | `inner_order` | 她维持一致性和自我修复的能力 | merge 阈值、repair rate、route 精度 |
| 关系引力 | `relational_gravity` | 她多容易被他人的节奏拉动 | boundary integrity、blend rate、accepted decay |

**特性：**
- 漂移慢（base_rate = 0.003/tick）
- 由计算栈 observation 驱动
- 有惯性（越老越难改）
- 有稳态回拉（偏离 set_point 越远阻力越大）
- 硬限制 [0.05, 0.95]

### 2.2 Sylanne 六维（表层表达）

| 维度 | 代码名 | 语义 | 影响什么 |
|------|--------|------|----------|
| 温度偏置 | `warmth_bias` | 当下的温暖程度 | prompt 语气温度 |
| 锋利度 | `edge` | 当下的尖锐程度 | 措辞选择 |
| 好奇心 | `curiosity` | 当下的探索欲 | 提问倾向 |
| 耐心 | `patience` | 当下的等待意愿 | 回复节奏 |
| 亲密引力 | `intimacy_gravity` | 当下的靠近欲望 | 主动发起频率 |
| 主权守卫 | `sovereignty_guard` | 当下的边界强度 | 拒绝/暂停倾向 |

**特性：**
- 漂移快（rate = 0.02/tick）
- 由文本信号 + Embodiment 五维约束范围驱动
- Embodiment 五维为每个 Sylanne 维度设定 [min, max] 可漂移区间
- 可以在区间内自由波动，但不能超出骨架约束

### 2.3 双向耦合

```
Embodiment 五维 ──约束范围──→ Sylanne 六维
                                    │
                                    │ 持续撞击边界 20+ tick
                                    ↓
Embodiment 五维 ←──缓慢反馈──── Sylanne 六维
```

**约束方向（快，每 tick）：** Embodiment 决定 Sylanne 的活动范围。高 `relational_gravity` 意味着 `warmth_bias` 的下限更高（她很难变冷）。

**反馈方向（极慢，rate = 0.0003）：** 如果 Sylanne Traits 持续 20+ tick 撞击约束边界，说明表面行为在试图突破深层结构。这会缓慢改变 Embodiment 五维。模拟"行为塑造性格"。

## 3. 漂移信号源

### 3.1 计算栈 → Embodiment 五维

每个 Embodiment 维度由 2-3 个计算栈信号驱动：

#### expression_drive_trait（表达驱力）

| 信号 | 条件 | 方向 | 权重 |
|------|------|------|------|
| feedback_accepted | 表达被接纳 | ↑ | +0.4 |
| feedback_ignored | 表达被忽略 | ↓ | -0.2 |
| feedback_rejected | 表达被拒绝 | ↓ | -0.6 |
| expression_fired | 成功触发表达 | ↑ | +0.3 |
| sustained_silence | 连续 skip 路由 | ↓ | -0.1 |

#### perception_acuity（感知锐度）

| 信号 | 条件 | 方向 | 权重 |
|------|------|------|------|
| high_tension | tension > 0.7 | ↑ | +0.5 |
| low_coherence | coherence < 0.4 | ↑ | +0.4 |
| high_void_pressure | void_pressure > 30 | ↑ | +0.3 |
| sustained_positive_valence | valence > 0.3 连续 5+ tick | ↓ | -0.3 |
| boundary_stable | stability > 0.9 | ↓ | -0.2 |

#### boundary_permeability（边界通透）

| 信号 | 条件 | 方向 | 权重 |
|------|------|------|------|
| high_surprise_positive | surprise > 0.6 且 valence ≥ 0 | ↑ | +0.4 |
| new_void_created | void genesis 触发 | ↑ | +0.3 |
| sustained_low_surprise | surprise < 0.2 连续 10+ tick | ↓ | -0.2 |
| high_surprise_negative | surprise > 0.6 且 valence < -0.3 | ↓ | -0.3 |

#### inner_order（内在秩序）

| 信号 | 条件 | 方向 | 权重 |
|------|------|------|------|
| high_coherence | coherence > 0.8 | ↑ | +0.2 |
| full_route_used | route = "full" | ↑ | +0.1 |
| boundary_self_repair | integrity 回升 | ↑ | +0.15 |
| system_chaos | coherence < 0.3 且 void_pressure > 50 | ↓ | -0.3 |

#### relational_gravity（关系引力）

| 信号 | 条件 | 方向 | 权重 |
|------|------|------|------|
| repair_executed | 修复行为触发 | ↑ | +0.3 |
| boundary_breached | penetration > phase_threshold | ↓ | -0.5 |
| relaxed_positive | valence > 0.2 且 tension < 0.3 | ↑ | +0.2 |
| feedback_rejected | 表达被拒绝 | ↓ | -0.3 |

### 3.2 文本 + Embodiment → Sylanne 六维

Sylanne Traits 的漂移来源：
1. 文本关键词（现有 `_event_direction` 逻辑，保留）
2. Embodiment 五维约束的"引力"（trait 被拉向约束区间中心）

## 4. 漂移动力学

### 4.1 核心公式

```
Δtrait = base_rate × signal_magnitude × inertia × homeostatic × asymmetric_resistance
```

其中：
- `base_rate` = 0.003（Embodiment）或 0.02（Sylanne）
- `signal_magnitude` = sqrt(raw_signal)，压缩极端值
- `inertia` = 1 / (1 + log(1 + tick_count / 500))
- `homeostatic` = 1 - |current - set_point| × 0.3
- `asymmetric_resistance` = 0.5 when approaching extremes (< 0.3 or > 0.7)

### 4.2 Dual-EMA 防冲击机制

每个 Embodiment 维度维护两个指数移动平均：

- **fast_ema**（τ=50 tick）：捕捉近期趋势
- **slow_ema**（τ=500 tick）：捕捉长期基线

**规则：**
- fast 和 slow 方向一致 → 全力漂移（持续信号，真实变化）
- fast 和 slow 方向不一致 → 只用 slow 的 50%（短期冲击，抵抗）

**效果：**
- 单次恶意事件：fast 跳动，slow 不动 → 方向不一致 → 漂移被抑制 → 自然恢复
- 持续 50+ tick 同方向：fast 和 slow 对齐 → 全力漂移 → 永久改变

### 4.3 Set Point 演化

每个 trait 的 set_point（稳态吸引子）本身也会极缓慢移动：

```
set_point += 0.0004 × (current_value - set_point)
```

τ ≈ 5000 tick。意味着真正持久的变化（500+ tick 维持）最终会被接受为"新常态"，稳态回拉力不再试图恢复到旧值。

### 4.4 惯性递增

```
inertia(tick) = 1 / (1 + log(1 + tick / 500))

tick 0:     1.00（完全可塑）
tick 500:   0.59
tick 2000:  0.40
tick 10000: 0.25
```

永远不会到 0。人格始终可以改变，只是越来越需要更强的信号。

## 5. 安全机制

### 5.1 主权免疫系统

当 `sovereignty_guard > 0.6` 时：
- 单 session 最多形成 3 个新 scar
- 单 session 最多创建 2 个新 void
- 超出后自动提高 wound_threshold 到 0.95（保护性解离）

### 5.2 保护性解离（Circuit Breaker）

触发条件：5 个 scar 在 10 tick 内形成 且 coherence < 0.3

效果：
- wound_threshold 临时提高到 0.95（几乎不可伤害）
- void 创建完全冻结
- 持续 30 tick 后逐渐恢复

### 5.3 振荡检测

10 tick 内方向翻转 ≥ 6 次 → 冻结该 trait 20 tick。防止信号噪声导致人格抖动。

### 5.4 多样性守卫

所有 trait 离 0.5 的平均距离 < 0.08 时（"人格死亡"），注入微小确定性扰动，防止收敛到无特征状态。

### 5.5 Numbed-count 路径限制

void_scar_engine.py 中的 numbed-count 检测阈值覆盖必须受人格约束：
```
effective_threshold = max(personality_derived_threshold, 0.4 - numbed_count * 0.03)
```
永远不低于人格设定的地板值。

## 6. 时间感知

### 6.1 Healing 基于真实时间

```python
effective_healing_ticks = message_ticks + floor(elapsed_minutes / 5)
```

沉默期间 scar 也在愈合（每 5 分钟等效 1 tick）。这意味着：
- 频繁聊天：healing 主要由消息驱动
- 长期沉默：healing 由时间驱动（伤口会自己好）

### 6.2 Void 压力基于真实时间

```python
pressure += depth × log(age_minutes + 1) × (1 - beta)
```

一个沉默了一周的 void 比沉默了 5 秒的 void 压力大得多。

### 6.3 漂移速率限制

最多每 30 秒计算一次有效漂移。10 条消息在 1 分钟内只算 2 次漂移事件。防止刷消息操纵人格。

## 7. 前端展示

### 7.1 WebUI 人格面板

**雷达图：** 5 维 Embodiment 当前值 + 漂移方向箭头（↑↓或→表示稳定）

**人格事件日志：**
```
[14:32] 连续被接纳 → 表达驱力 ↑0.002
[14:28] 高张力持续 → 感知锐度 ↑0.001
[14:15] 边界稳定 → 感知锐度 ↓0.001
```

**健康状态：**
- 多样性指数（离 0.5 的平均距离）
- 惯性系数（当前可塑性）
- 是否处于保护性解离
- 振荡检测状态

### 7.2 自然语言摘要

不显示数字，显示描述：
- "她最近变得更敏感了，小事也会在意"（perception_acuity ↑）
- "她越来越愿意主动开口"（expression_drive_trait ↑）
- "她的边界变得更坚固了"（boundary_permeability ↓）

## 8. 实现路径

### Phase 1：统一 Trait 系统
- 重命名 Big Five → Embodiment 五维
- 确保 `apply_personality()` 读新名字
- 确保 `drift_personality()` 写新名字
- 建立 Sylanne ↔ Embodiment 约束映射

### Phase 2：计算栈驱动漂移
- 实现 `DriftSignalExtractor`（从 computation result 提取信号）
- 实现 `compute_embodiment_drift()`（Dual-EMA + 稳态 + 惯性）
- 在 `kernel.tick()` 中调用

### Phase 3：安全机制
- 主权免疫（session scar cap）
- 保护性解离（circuit breaker）
- 振荡检测
- 时间感知 healing

### Phase 4：前端
- 人格雷达图
- 漂移事件日志
- 自然语言摘要
