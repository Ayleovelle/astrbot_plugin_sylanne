# MoE-HGT 公理系统

## 公理 HGT-MoE-1: Expert Specialization Emergence

情境 experts 的特化不是硬编码的，而是通过 personality-derived 初始化 + BCM 适应涌现的。

**形式化**:
设 E = {E₀, E₁, E₂, E₃, E₄} 为情境专家集合，R(x) 为 router 函数。
- 初始状态: R(x) 由人格语义决定偏好分布
- 稳态: lim_{t→∞} R(x_context) 可能偏离初始语义标签
- 约束: ∀t, Σᵢ gate_i(x) = 1 (概率归一化)

**含义**: Expert 命名（defense, curiosity, social, silence, repair）是初始语义提示，
不是硬约束。长期使用后 expert 可能发展出与初始语义不同的特化模式。

---

## 公理 HGT-MoE-2: Plasticity-Stability Tradeoff

适应速率由人格的 openness-conscientiousness 轴调制。

**形式化**:
plasticity = clamp(0.3 + O×0.5 - C×0.3, [0.05, 0.85])

其中 O = openness, C = conscientiousness。

**含义**:
- 高开放性个体: 快速适应新模式，但可能丢失已学习的偏好
- 高尽责性个体: 保持决策一致性，但适应新情境较慢
- 最小可塑性 0.05: 即使极端人格也保证基本适应能力（生物学约束）

---

## 公理 HGT-MoE-3: Hebbian Convergence

Oja 规则保证 attention prior drift 收敛到输入分布的主成分方向。
BCM 的滑动阈值保证 router 不会坍缩到单一 expert。

**形式化**:

Oja attention drift:
  Δw_ij = η·y_ij·(x_ij - y_ij·w_ij), bounded ∈ [-0.3, 0.3]
  全局衰减: w_ij ← 0.999·w_ij

BCM router bias:
  θ_M(i) = EMA(gate_i²), 滑动修改阈值
  Δbias_i = η·gate_i·(gate_i - θ_M(i)), bounded ∈ [-1.0, 1.0]
  全局衰减: bias_i ← 0.998·bias_i

**收敛保证**:
1. Oja 规则的自归一化特性 + 硬边界 → drift 有界
2. BCM 滑动阈值 → 防止 winner-take-all 坍缩
3. 全局衰减 → 长期不活跃的适应自然消退（可逆性）

**不可适应区域**:
- intra-type mask（对角线）永远为 -∞，不参与适应
- 基础参数（由人格 SHA-256 派生）不可修改
