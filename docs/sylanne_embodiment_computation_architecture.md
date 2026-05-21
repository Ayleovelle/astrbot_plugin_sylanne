# Sylanne-Embodiment 计算架构设计文档（v2）

## 0. 定位

本文档定义 Sylanne 4.0 的**核心计算层**——不是 LLM prompt 工程，不是 API 适配，而是 Sylanne 自身的"神经系统"。

本架构包含**两项原创理论贡献**：
- **Scar Algebra**：自修改运算符代数，运算符的语义随使用历史不可逆地变化
- **Void Calculus**：缺席一等计算，将"未说之物"作为独立计算对象建模

此外采用 **Heterogeneous Graph Transformer (HGT)** 作为决策融合层，以类型感知的 attention 替代传统同质 attention。

---

## 1. 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│              L6  相变表达 (Phase Transition)                   │
│         压力积累 → 阈值判断 → hint/normal/urgent 输出          │
├─────────────────────────────────────────────────────────────┤
│              L5  自创生边界 (Autopoietic Boundary)             │
│         自我维持 · 操作封闭 · 结构耦合 · 6°旋转上限            │
├─────────────────────────────────────────────────────────────┤
│              L4  异构图 Transformer (HGT)                     │
│         类型感知 Q/K/V · 人格先验 μ · intra-type mask         │
├─────────────────────────────────────────────────────────────┤
│              L3  Void-Scar Engine（含时空图）                  │
│  ┌──────────────┐    ↕ Γ,Φ    ┌──────────────┐             │
│  │ Scar Algebra │◄───────────►│ Void Calculus │             │
│  │ 不可逆状态   │             │ 缺席追踪      │             │
│  └──────────────┘             └──────────────┘             │
│         └── 时空图（PPR diffusion, α 从人格派生）──┘          │
├─────────────────────────────────────────────────────────────┤
│              L2  预测编码门控 (Predictive Coding Gate)          │
│         惊讶度计算 → 路由决策 → 冷启动守卫                     │
├─────────────────────────────────────────────────────────────┤
│              L1  感知层 (HDC Perception)                       │
│         输入编码 → 2048-bit HDC 投影 → 事件向量构建            │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 各层详细设计

### 2.1 L1：HDC 感知编码

将输入文本投影到 2048 维二进制超向量空间。所有后续计算都在这个空间里进行。

- 编码：字符 bigram → 循环移位 → 多数投票捆绑
- 匹配：汉明距离 = popcount(XOR)，< 0.01ms
- 组合：bind（XOR，角色绑定）+ bundle（多数投票，叠加）

**性能**：编码一条消息 < 0.1ms。

---

### 2.2 L2：预测编码门控

维护完整的预测向量（bytearray），对每条输入计算汉明距离惊讶度。

- 低惊讶 (< 0.15) → fast path：仅 Scar 基态演化 + Void 年龄递增
- 中惊讶 (0.15-0.45) → normal path：完整 Void-Scar + HGT
- 高惊讶 (≥ 0.45) → full path：全栈 + 耦合 + 时空图 motif 检测

**冷启动守卫**：前 15 条消息预测模型未校准，路由上限为 normal（不走 full）。

---

### 2.3 L3：Void-Scar Engine

**核心创新层。** 替代原有的 SSM + TDA，统一为耦合系统。

#### Scar Algebra（不可逆状态演化）

状态 $s = (\mathbf{x}, \sigma)$：基态向量 + 不可删除的伤疤序列。

关键性质：
- **不可逆**：运算 $\triangleright$ 无逆元，伤疤只增不减
- **自修改**：伤疤改变未来运算的语义（modifier 乘在输入上）
- **非交换**：事件顺序影响结果（先伤后探 ≠ 先探后伤）
- **相变**：存在临界伤疤密度，超过后维度进入"麻木"状态

伤疤生命周期：raw (×2.0) → closing (×1.5) → scarred (×1.0) → faded (×0.7)

#### Void Calculus（缺席一等计算）

Void = 一等缺席对象，由边界定义，有自主压力动力学。

关键性质：
- **先于边界存在**：可以感觉到"有什么没说"但不知道具体是什么
- **深度不可逆**：depth 只增不减，被解决的空洞留下 ghost
- **自主压力**：$\pi(t) = \pi(t-1) + \delta \cdot \ln(age+1) \cdot (1-\beta)$，无需外部输入
- **三态区分**：从未讨论 / 已解决 / 主动回避——现有框架最多区分两态

运算：contract（缩小）、deepen（加深）、split（分裂）、merge（合并）

#### 双向耦合

- $\Gamma$（Void → Scar）：空洞压力超阈值时产生伤疤事件——"未说之物积累到伤人"
- $\Phi$（Scar → Void）：维度麻木时降低空洞检测阈值——"反复受伤导致回避"

#### 时空图（内部结构）

事件、伤疤、空洞、幽灵统一为图节点，边分为 temporal / causal / semantic / boundary 四种类型。

**防过平滑**：PPR teleportation diffusion，$\alpha = 0.2 + 0.4 \times \text{neuroticism}$。

---

### 2.4 L4：Heterogeneous Graph Transformer

类型感知的 transformer，用于多源信号的非线性决策融合。

**与 vanilla attention 的区别**：
- 每种 token 类型有独立的 $W_Q^\tau, W_K^\tau, W_V^\tau$
- 人格派生的 attention prior $\mu^{(\tau_s, \tau_t)}$ 决定类型对间的注意力偏好
- **Intra-type mask**：同类型 token 不互相 attend，防止局部过平滑

Token 类型（7 种）：scar, void, boundary, personality, surprise, expression, context

**输出**：4 维决策向量
- $d_0$：表达驱动修正
- $d_1$：边界敏感度修正
- $d_2$：紧迫度信号
- $d_3$：抑制信号（> 0.5 时否决表达）

**参数**：~21.9K floats = 87.6 KB，全部从人格语义派生，零学习。

---

### 2.5 L5：自创生边界

人格作为自我维持的计算过程。32 维身份核心向量，通过正交投影判断穿透量。

- 穿透 < 0.3：吸收（弹性）
- 穿透 0.3-0.7：抵抗（边界受损但身份不变）
- 穿透 ≥ 0.7：相变（身份核心旋转 ≤ 6°）

每 tick 自动修复 boundary_integrity。

---

### 2.6 L6：相变表达

表达是相变而非连续函数。压力积累超过阈值时不连续跳变。

三种表达模式：
- hint（强度 < 0.5）：轻微暗示
- normal（强度 0.5-1.0）：正常表达
- urgent（强度 > 1.0）：紧迫表达

阈值从人格 extraversion 派生，沉默时间降低阈值，表达后升高阈值。

---

## 3. 统一数据流示例

```
用户消息 "你怎么不说话了"
    │
    ▼
[L1 HDC] 编码 → 2048-bit 向量 h
    │
    ▼
[L2 预测编码] surprise(h) = 0.62 → route: "full"
    │
    ▼ (高惊讶，走全栈)
    │
[L3 Void-Scar Engine]
    ├── Scar Algebra: modulate(input) → step → 新伤疤？
    │     warmth 维度有 2 个 faded scar → modifier=0.49 → 输入被衰减
    │     tension 维度无 scar → modifier=1.0 → 正常响应
    │
    ├── Void Calculus: 检测到"沉默"相关空洞 v₁
    │     v₁.depth=0.6, v₁.pressure=4.2, v₁.age=15
    │     contract(v₁, h): 边界点被触及，空洞缩小
    │
    ├── 耦合 Γ: v₁.pressure > θ_p → 产生伤疤事件 → tension 维度受伤
    │
    └── 时空图: 检测到 motif（用户第 3 次提到沉默）→ 降低相关 void 检测阈值
    │
    ▼
[L4 HGT] 32 tokens (typed) → attention with μ prior
    │   scar[tension] 高 + void[沉默] 压力大 + boundary 完整 → d₀=+0.3, d₃=0.1
    │   决策：允许表达，驱动增强
    │
    ▼
[L5 Autopoiesis] perturb(force) → penetration=0.2 → 吸收，无相变
    │
    ▼
[L6 Phase Transition] drive=0.8+0.3=1.1 > threshold=0.6 → EXPRESS (urgent)
    │
    ▼
输出：表达强度 1.1 (urgent)，情绪色彩 {tension↑, repair_pressure↑}
→ 注入 LLM prompt 引导生成
```

---

## 4. 性能预算

| 层 | Fast Path | Normal Path | Full Path |
|----|-----------|-------------|-----------|
| L1 HDC | 0.1 ms | 0.1 ms | 0.1 ms |
| L2 Gate | 0.01 ms | 0.01 ms | 0.01 ms |
| L3 Void-Scar + Graph | 0.05 ms | 2.5 ms | 6 ms |
| L4 HGT | skip (cached) | 0.4 ms | 0.4 ms |
| L5 Autopoiesis | 0.01 ms | 0.01 ms | 0.1 ms |
| L6 Phase Trans | 0.001 ms | 0.001 ms | 0.001 ms |
| **总计** | **~0.17 ms** | **~3.0 ms** | **~6.6 ms** |

90% 消息走 fast path (0.17ms)，10% 走 full path (6.6ms)。全部在 10ms 预算内。

---

## 5. 相关工作与定位

据我们所知，以下组合方式在已发表文献中尚未出现：

- 将"缺席"作为带生命周期的一等计算对象（而非从存在物中推导）
- 定义运算符语义随使用历史不可逆变化的状态代数（而非固定运算符的动力系统）
- 用类型感知 transformer + 人格先验做情感决策融合（而非同质 attention）
- 上述机制的耦合统一

最接近的已有工作各自覆盖了部分思路：S4/Mamba 做序列状态建模、AGM 做信念修正、损伤力学做材料本构方程变化、HGT 做异构图学习。本架构的贡献在于将这些方向中的核心洞察重新组合并形式化为一套面向关系 AI 的计算框架。

---

## 6. 理论文件索引

```
theory/
├── README.md                          # 总览
├── integration.md                     # 六层集成 + 时空图 + 防过平滑
├── void_scar_engine.py                # 耦合引擎参考实现
├── scar_algebra/
│   ├── axioms.md                      # 6 条公理
│   ├── theorems.md                    # 6 定理 + 严格证明 + 复杂度
│   └── impl/scar_algebra.py           # 参考实现 (tested)
└── void_calculus/
    ├── axioms.md                      # 6 条公理
    ├── theorems.md                    # 6 定理 + 严格证明 + 复杂度
    └── impl/void_calculus.py          # 参考实现 (tested)
```

---

## 7. 参考文献

- Gu et al. (2022). "Efficiently Modeling Long Sequences with Structured State Spaces" (S4)
- Gu & Dao (2023). "Mamba: Linear-Time Sequence Modeling with Selective State Spaces"
- Hu et al. (2020). "Heterogeneous Graph Transformer"
- Kanerva (2009). "Hyperdimensional Computing"
- Maturana & Varela (1980). "Autopoiesis and Cognition"
- Alchourrón, Gärdenfors & Makinson (1985). "On the Logic of Theory Change" (AGM)
- Rao & Ballard (1999). "Predictive Coding in the Visual Cortex"
- Edelsbrunner & Harer (2010). "Computational Topology"
- Friston (2010). "The Free-Energy Principle"
- Page et al. (1999). "The PageRank Citation Ranking" (PPR diffusion)
