# Plan: L5 MoE-HGT 升级 — 三层混合架构 + Hebbian 慢适应

## Context

当前 L5 HGT 存在严重简化：单层、multi-head 声明但未实现（4 heads 但实际单头计算）、K/V 投影派生但未使用、mean-pool 丢失 per-token 信息、d_2 未消费、无残差/归一化。升级为完整的 MoE-Transformer 混合架构，融合类型专家（A）、情境专家（B）、真正的 multi-head attention（C），并引入基于 Hebbian 规则的慢适应机制。

---

## 文献基础

### MoE 路由与稀疏激活

- **Switch Transformer** (Fedus et al., 2021, [arXiv:2101.03961](https://arxiv.org/abs/2101.03961)): 证明 top-1 routing 在大规模下有效，router 为简单线性投影 + softmax。负载均衡损失 `L = α·N·Σ(f_i·P_i)` 防止 expert 坍缩。
- **GShard** (Lepikhin et al., 2020, [arXiv:2006.16668](https://arxiv.org/abs/2006.16668)): top-2 routing，第二 expert 随机选择以分散负载。
- **Fine-Grained MoE Scaling Laws** (Ludziejewski et al., 2024, [arXiv:2402.07871](https://arxiv.org/abs/2402.07871)): 更多更小的 experts 在固定计算预算下持续提升性能。

### 异构图 + MoE

- **HER: Homogeneous Expert Routing for HGT** (2024, [arXiv:2511.07603](https://arxiv.org/abs/2511.07603)): 在 HGT 上加 MoE 层。关键发现：**类型无关的 expert 路由优于类型绑定路由**。通过随机 mask type embedding 迫使 expert 按语义内容而非节点类型特化。
- **HOPE: Heterogeneous-aware Orthogonal Prototype Experts** (2025, [arXiv:2601.05537](https://arxiv.org/abs/2601.05537)): 用可学习原型做路由，expert 正交化鼓励多样特化。允许 expert 使用遵循自然长尾分布。

### Hebbian 可塑性 + Transformer

- **Hebbian & Gradient-Based Plasticity in Transformers** (2024, [arXiv:2510.21908](https://arxiv.org/abs/2510.21908)): 在 Transformer 中加入 Hebbian 可塑性规则实现推理时适应。Hebbian 规则 `ΔW = η·y·xᵀ` 在 copying、regression、few-shot 任务上持续优于静态权重。关键结论：**当关联是短期且线性可分时，静态权重足够；当需要长期记忆和快速适应时，可塑性必要**。
- **Hebbian Fast Weights in Vision Transformers** (2025, [arXiv:2605.02920](https://arxiv.org/abs/2605.02920)): 在 ViT 中用 Hebbian fast weights 实现 few-shot 适应，无需外部训练。

### MoE 在线适应（无反向传播）

- **Continuous Rerouting** (2025, [arXiv:2510.14853](https://arxiv.org/abs/2510.14853)): 在推理时通过自监督优化 MoE 路由决策。**无需外部数据**，仅基于已生成序列的上下文做 rerouting。证明 MoE routing 可以在 test-time 持续改进。
- **PA-MoE: Plasticity-Aware MoE** (2025, [arXiv:2504.09906](https://arxiv.org/abs/2504.09906)): 通过噪声注入促进选择性遗忘过时知识，赋予网络增强的适应能力。平衡记忆保持与选择性遗忘。
- **PE-MAMoE: Plasticity-Enhanced Multi-Agent MoE** (2026, [arXiv:2604.09028](https://arxiv.org/abs/2604.09028)): 在 MoE 中引入可塑性增强机制，用于动态目标适应。

### Oja 规则与在线 PCA

- **Oja's Rule** (1982): `Δw = η·y·(x - y·w)`，稳定化 Hebbian 规则，收敛到输入分布的第一主成分。权重自动归一化。
- **OjaKV** (2024): 将 Oja 规则应用于 Transformer 的 KV cache 在线压缩，证明 Oja 规则可以在推理时有意义地适应投影基。
- **BCM Theory** (Bienenstock-Cooper-Munro, 1982): 引入滑动修改阈值 `θ_M = E[y²]`，产生选择性神经元。`φ(y, θ_M) = y·(y - θ_M)` — 超过阈值为 LTP（增强），低于为 LTD（抑制）。

---

## 架构设计

### 总体流程

```
输入: 7 typed tokens × 16-dim
  (scar, void, boundary, personality, surprise, expression, context)

┌─────────────────────────────────────────────────────────────────┐
│ Stage 1: Type-Expert Encoding                                    │
│                                                                 │
│  7 个 type-specific Expert FFN (16 → 24 → 16, SiLU activation) │
│  每个 token 由其对应类型的 expert 处理                            │
│  + Residual connection + RMSNorm                                │
│                                                                 │
│  理论依据: HER 论文证明 type-specific 预处理有效，              │
│  但最终路由应 type-agnostic                                      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Stage 2: True Multi-Head Cross-Attention                         │
│                                                                 │
│  4 heads, d_head = 4, d_model = 16                              │
│  Per-type Q/K/V projections (真正使用全部三个投影)               │
│  Personality-derived attention prior (7×7 bias, 可适应)          │
│  Intra-type mask (same-type attention = -∞)                     │
│  + Residual + RMSNorm                                           │
│                                                                 │
│  理论依据: 标准 Transformer 架构 + HGT 的 type-specific         │
│  投影 + 项目已有的 intra-type mask 公理                          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Stage 3: Situation-Expert MoE FFN                                │
│                                                                 │
│  Router: mean-pooled 16-dim → 5-dim softmax (top-2 gating)     │
│  5 Situation Experts (16 → 24 → 16, SiLU):                     │
│    E₀ 防御 (defense)    — 高 scar/boundary 活跃时主导           │
│    E₁ 好奇 (curiosity)  — 高 surprise/openness 时主导           │
│    E₂ 社交 (social)     — group context/sheaf 耦合时主导        │
│    E₃ 沉默 (silence)    — 高 inhibition/void 时主导             │
│    E₄ 修复 (repair)     — repair_pressure 高时主导              │
│                                                                 │
│  Output = gate₁·Expert_i(x) + gate₂·Expert_j(x)  (top-2)      │
│  + Residual + RMSNorm                                           │
│                                                                 │
│  理论依据: Switch Transformer 的 sparse routing +               │
│  HER 的 type-agnostic routing（router 看语义不看类型）+         │
│  PA-MoE 的 plasticity-aware 设计                                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Decision Head                                                    │
│                                                                 │
│  Mean-pool 7 tokens → 16-dim                                    │
│  Project: 16 → 4 (tanh/sigmoid activation)                      │
│  Output: [d₀ drive, d₁ boundary, d₂ urgency, d₃ inhibition]   │
│                                                                 │
│  d₀: 表达驱动修正 (tanh, ×0.3 加到 drive)                      │
│  d₁: 边界敏感度修正 (tanh, ×0.5 乘到 boundary force)           │
│  d₂: 紧迫度信号 (tanh, 调制 expression urgency)                │
│  d₃: 抑制信号 (sigmoid×3, >0.5 否决表达)                       │
└─────────────────────────────────────────────────────────────────┘
```

### 参数规模与计算量

| 组件 | 参数量 | FLOPs/forward |
|------|--------|---------------|
| Type-Expert FFN ×7 (16→24→16) | 7×(16×24+24×16) = 5,376 | 7×768 = 5,376 |
| RMSNorm₁ (16-dim) | 16 | 112 |
| Q/K/V per-type ×7 (4 heads, 4×4 each) | 7×3×(4×4×4) = 1,344 | 7×3×64 = 1,344 |
| Attention scores (7×7×4 heads) | — | 7×7×4×4 = 784 |
| Attention × V | — | 7×7×4×4 = 784 |
| Output proj (16→16) | 256 | 256 |
| Attention prior (7×7) | 49 | 49 (add) |
| RMSNorm₂ | 16 | 112 |
| Router (16→5) | 80 | 80 |
| Situation-Expert FFN ×2 active (16→24→16) | 5×768=3,840 (存储) | 2×768 = 1,536 |
| RMSNorm₃ | 16 | 112 |
| Decision proj (16→4) | 64 | 64 |
| **Total** | **~11,057 存储** | **~10,609 FLOPs** |

### 1c1g 服务器可行性分析

**纯 Python 估算:**
- 10,609 FLOPs × ~80ns/op (Python loop) ≈ **0.85 ms**
- 当前 HGT: ~3,880 FLOPs × 80ns ≈ 0.31 ms
- 增量: +0.54 ms，仍在 10ms 总预算内

**优化后 (flat array + 内联循环):**
- 当前代码已用 `_matmul_vec_flat` 优化，实测 ~0.2-0.4 ms
- 新架构预估: **0.6-1.2 ms**（可接受，留有余量）

**内存:**
- 11,057 floats × 8 bytes = ~88 KB（Python 对象开销 ×3 ≈ 264 KB）
- 1GB RAM 中完全可忽略

---

## Hebbian 慢适应机制

### 理论基础

基于三篇关键论文的融合设计：

1. **Oja's Rule** 用于 attention prior 适应（在线 PCA 特性保证权重稳定）
2. **BCM 滑动阈值** 用于 router bias 适应（产生选择性，防止所有 expert 均匀激活）
3. **Continuous Rerouting** 的自监督思想（用 feedback outcome 作为信号源）

### 适应组件

#### 1. Router Bias 适应（BCM 启发）

```python
class RouterAdaptation:
    """BCM-inspired router bias adaptation.
    
    滑动阈值 θ_M 防止 expert 坍缩到单一模式。
    """
    def __init__(self, n_experts: int = 5):
        self.bias = [0.0] * n_experts          # 路由偏置
        self.activity_ema = [0.2] * n_experts  # 滑动活跃度 (BCM θ_M)
        self.plasticity = 0.5                   # 由人格调制
    
    def adapt(self, outcome: str, active_experts: list[int], gate_values: list[float]):
        """BCM 规则: φ(y, θ) = y·(y - θ)
        
        outcome="accepted": 活跃 expert 的 gate 超过其 θ_M → 增强 (LTP)
        outcome="rejected": 活跃 expert 的 gate 低于其 θ_M → 抑制 (LTD)
        """
        eta = 0.008 * self.plasticity
        
        for idx in active_experts:
            y = gate_values[idx]
            theta = self.activity_ema[idx]
            
            if outcome == "accepted":
                # BCM: y·(y - θ) > 0 when y > θ → LTP
                delta = eta * y * (y - theta)
            elif outcome == "rejected":
                # 反向 BCM: 抑制当前活跃 expert
                delta = -eta * y * max(0.1, y)
            else:  # ignored
                delta = -eta * 0.3 * y
            
            self.bias[idx] += delta
            # 更新滑动阈值 (EMA of y²)
            self.activity_ema[idx] = 0.99 * theta + 0.01 * (y * y)
        
        # 衰减防止极化 (PA-MoE 的 selective forgetting)
        for i in range(len(self.bias)):
            self.bias[i] *= 0.998
```

#### 2. Attention Prior 适应（Oja 规则启发）

```python
class AttentionPriorAdaptation:
    """Oja-inspired attention prior adaptation.
    
    Oja's rule: Δw = η·y·(x - y·w)
    应用于 attention prior: 强化被接受表达中活跃的 type-pair 连接。
    自动归一化防止权重爆炸。
    """
    def __init__(self, n_types: int = 7):
        self.drift = [[0.0]*n_types for _ in range(n_types)]  # 7×7 delta
        self.plasticity = 0.5
    
    def adapt(self, outcome: str, attention_weights: list[list[float]]):
        """
        attention_weights: 7×7 矩阵，当前 forward 的注意力分布
        """
        eta = 0.005 * self.plasticity
        
        for i in range(7):
            for j in range(7):
                if i == j:
                    continue  # intra-type mask 不可适应
                w = self.drift[i][j]
                y = attention_weights[i][j]  # 当前注意力强度
                
                if outcome == "accepted":
                    # Oja: Δw = η·y·(x - y·w), x=1 for active pairs
                    x = 1.0 if y > 0.15 else 0.0
                    delta = eta * y * (x - y * w)
                elif outcome == "rejected":
                    # 反向: 削弱活跃连接
                    delta = -eta * y * 0.5
                else:
                    delta = 0.0
                
                self.drift[i][j] = max(-0.3, min(0.3, w + delta))
        
        # 全局衰减 (Oja 的自归一化特性)
        for i in range(7):
            for j in range(7):
                self.drift[i][j] *= 0.999
```

#### 3. 人格调制适应速率

```python
def derive_plasticity(personality: dict) -> float:
    """从人格 traits 派生适应速率。
    
    理论依据:
    - 高开放性 (O): 更愿意尝试新模式 → 高可塑性
    - 高尽责性 (C): 偏好稳定一致 → 低可塑性  
    - 高神经质 (N): 对负面反馈更敏感 → rejected 时适应更快
    """
    O = personality.get("openness", 0.5)
    C = personality.get("conscientiousness", 0.5)
    N = personality.get("neuroticism", 0.5)
    
    base_plasticity = 0.3 + O * 0.5 - C * 0.3  # [0.0, 0.8]
    return max(0.05, min(0.85, base_plasticity))
```

#### 4. 适应的边界条件

- **drift 上限**: attention prior drift 每个元素 ∈ [-0.3, 0.3]（不超过基础值的 30%）
- **router bias 上限**: 每个 bias ∈ [-1.0, 1.0]
- **衰减**: 每 tick 乘 0.998/0.999，确保长期不活跃的适应自然消退
- **不可适应区域**: intra-type mask（对角线）永远为 -∞，不参与适应
- **最小可塑性**: 即使极端人格也保证 plasticity ≥ 0.05（完全不适应违反生物学）

---

## 与现有公理系统的兼容性

### 满足的约束

1. **Separation of Concerns** (integration.md): HGT 仍然只做"是否行动"的决策融合，不改变子系统内部状态
2. **Anti-oversmoothing**: intra-type mask 保留，same-type tokens 不互相注意
3. **Personality-derived base**: 所有基础参数仍由人格 SHA-256 派生，适应只是 delta
4. **Bounded output**: decision vector 仍为 4-dim，tanh/sigmoid 保证有界
5. **Performance budget**: 预估 0.6-1.2ms，在 10ms 总预算内

### 新增公理

**公理 HGT-MoE-1 (Expert Specialization Emergence)**:
情境 experts 的特化不是硬编码的，而是通过 personality-derived 初始化 + BCM 适应涌现的。初始 router 权重由人格语义决定偏好，但长期使用后 expert 可能发展出与初始语义不同的特化。

**公理 HGT-MoE-2 (Plasticity-Stability Tradeoff)**:
适应速率由人格的 openness-conscientiousness 轴调制。这实现了 PA-MoE 论文中的"记忆保持与选择性遗忘的平衡"——高尽责性个体保持决策一致性，高开放性个体快速适应新模式。

**公理 HGT-MoE-3 (Hebbian Convergence)**:
Oja 规则保证 attention prior drift 收敛到输入分布的主成分方向。BCM 的滑动阈值保证 router 不会坍缩到单一 expert。两者结合确保适应是稳定的、有界的、可逆的。

---

## 实现文件清单

| 文件 | 改动 |
|------|------|
| `sylanne_alpha/hgt.py` | 完全重写为 MoE-HGT 三层架构 + 适应机制 |
| `sylanne_alpha/computation_spine.py` | `feedback()` 传递 outcome 给 HGT adapt；`to_dict()`/`from_dict()` 持久化适应状态 |
| `tests/test_sylanne_alpha_kernel.py` | 新增 MoE routing、attention、adaptation 测试 |
| `theory/social_field_dynamics/axioms.md` | 新增 HGT-MoE 公理 |

## 接口兼容性

对外接口完全不变：
- `HeterogeneousGraphTransformer(d_model=16, n_heads=4, d_output=4)`
- `derive_params(personality)` — 派生基础参数 + 设置 plasticity
- `forward(tokens) → list[float]` — 返回 4-dim decision
- `build_tokens_from_spine(...)` — 输入不变
- 新增: `adapt(outcome: str, attention_snapshot: list)` — Hebbian 适应
- 新增: `adaptation_state() → dict` — 当前适应状态（用于 WebUI 展示）
- 新增: `to_dict()` / `from_dict(data)` — 持久化

---

## 验证

1. 现有 82 tests 全部通过（接口兼容）
2. 新增测试:
   - `test_type_expert_independence`: 每个 type expert 只处理对应 token
   - `test_multihead_attention_splits`: 4 heads 真正独立计算
   - `test_kv_projection_used`: K/V 投影参与 attention 计算
   - `test_moe_router_top2`: router 选择 top-2 experts
   - `test_moe_sparse_activation`: 只有 2/5 experts 被激活
   - `test_residual_connection`: 输出 = input + layer(input)
   - `test_bcm_adaptation_ltp`: repeated accepted → active expert bias 增加
   - `test_bcm_adaptation_ltd`: repeated rejected → active expert bias 减少
   - `test_bcm_sliding_threshold`: 活跃度阈值随使用滑动
   - `test_oja_attention_convergence`: attention drift 有界且收敛
   - `test_plasticity_personality_modulation`: 高 O 低 C → 快适应
   - `test_adaptation_decay`: 长期不活跃 → drift 自然消退
   - `test_to_dict_from_dict_adaptation`: 适应状态正确持久化
3. 性能基准: `forward()` < 1.5ms (纯 Python, 1 core)
4. 内存: < 300KB total (含 Python 对象开销)

---

## 实验项目交接文档: Sylanne-core-exp

### 项目定位

`Sylanne-core-exp` 是 Sylanne-Embodiment 的**实验分支**，专注于 L5 MoE-HGT 架构升级。不在主仓库实施，避免影响生产稳定性。实验成功后合并回主仓库。

### 仓库初始化

```bash
mkdir Sylanne-core-exp && cd Sylanne-core-exp
git init

# 从主仓库复制核心计算模块（只需要这些）
cp -r ../Sylanne-embodiment/sylanne_alpha/hgt.py ./src/hgt_moe.py
cp -r ../Sylanne-embodiment/sylanne_alpha/computation_spine.py ./src/computation_spine.py
cp -r ../Sylanne-embodiment/sylanne_alpha/hdc.py ./src/hdc.py
cp -r ../Sylanne-embodiment/sylanne_alpha/predictive_coding.py ./src/predictive_coding.py
cp -r ../Sylanne-embodiment/sylanne_alpha/void_scar_engine.py ./src/void_scar_engine.py
cp -r ../Sylanne-embodiment/sylanne_alpha/scar_algebra.py ./src/scar_algebra.py
cp -r ../Sylanne-embodiment/sylanne_alpha/void_calculus.py ./src/void_calculus.py
cp -r ../Sylanne-embodiment/sylanne_alpha/relational_sheaf.py ./src/relational_sheaf.py
cp -r ../Sylanne-embodiment/sylanne_alpha/autopoiesis.py ./src/autopoiesis.py
cp -r ../Sylanne-embodiment/sylanne_alpha/phase_transition.py ./src/phase_transition.py
cp -r ../Sylanne-embodiment/sylanne_alpha/personality.py ./src/personality.py
cp -r ../Sylanne-embodiment/sylanne_alpha/social_field.py ./src/social_field.py
```

### 目录结构

```
Sylanne-core-exp/
├── src/
│   ├── __init__.py
│   ├── hgt_moe.py          # 新 MoE-HGT 实现（本实验核心）
│   ├── computation_spine.py # 修改版 spine（集成 MoE-HGT）
│   ├── hdc.py              # HDC 编码器（不修改）
│   ├── predictive_coding.py # 预测编码门控（不修改）
│   ├── void_scar_engine.py  # Void-Scar 引擎（不修改）
│   ├── scar_algebra.py      # 伤痕代数（不修改）
│   ├── void_calculus.py     # 空洞微积分（不修改）
│   ├── relational_sheaf.py  # 关系层论（不修改）
│   ├── autopoiesis.py       # 自创生边界（不修改）
│   ├── phase_transition.py  # 相变表达（不修改）
│   ├── personality.py       # 人格系统（不修改）
│   └── social_field.py      # 社会场（不修改）
├── tests/
│   ├── test_moe_hgt.py      # MoE-HGT 单元测试
│   ├── test_adaptation.py   # Hebbian 适应测试
│   ├── test_integration.py  # 与 spine 集成测试
│   └── bench_performance.py # 性能基准测试
├── theory/
│   └── moe_hgt_axioms.md    # 新增公理文档
├── notebooks/
│   └── adaptation_viz.ipynb # 适应过程可视化
├── CLAUDE.md                # Claude Code 项目文档
├── requirements.txt         # Python 依赖
└── README.md                # 实验说明
```

### 环境要求

```
# requirements.txt
pytest>=7.0
numpy>=1.24        # 可选，用于性能优化路径
matplotlib>=3.7    # 可选，用于 notebook 可视化
```

**Python 版本**: 3.10+
**硬件约束**: 1 core, 1 GB RAM（目标部署环境）
**无 GPU 依赖**: 纯 CPU 计算

### CLAUDE.md 内容

```markdown
# Sylanne-core-exp

## 项目概述
L5 MoE-HGT 实验：将 Sylanne-Embodiment 的异构图 Transformer 升级为
三层混合 MoE 架构 + Hebbian 慢适应。

## 关键约束
- 纯 Python 实现（numpy 可选优化）
- 单次 forward() < 1.5ms (1 core)
- 内存 < 300KB
- 所有基础参数由人格 SHA-256 确定性派生
- 适应是增量 delta，不改变基础参数
- intra-type mask 不可违反（公理约束）

## 测试
python -m pytest tests/ -v

## 性能基准
python tests/bench_performance.py

## 核心文件
- src/hgt_moe.py — MoE-HGT 实现（本实验唯一新文件）
- src/computation_spine.py — 集成层（最小修改）

## 公理系统
- theory/moe_hgt_axioms.md — 新增 3 条公理

## 合并回主仓库
实验成功后，将 src/hgt_moe.py 内容替换
Sylanne-embodiment/sylanne_alpha/hgt.py，
并更新 computation_spine.py 的 feedback 传递逻辑。
```

### MCP 配置

```json
// .vscode/mcp.json
{
  "servers": {
    "CodeGraph": {
      "type": "stdio",
      "command": "codegraph",
      "args": ["serve", "--mcp"]
    }
  }
}
```

### Claude Code Settings

```json
// .claude/settings.local.json
{
  "permissions": {
    "allow": [
      "Bash(python -m pytest*)",
      "Bash(python tests/bench_performance.py*)",
      "Bash(python -c *import*)"
    ]
  }
}
```

### 开发工作流

1. **实现 MoE-HGT**: 在 `src/hgt_moe.py` 中从零实现三层架构
2. **单元测试**: 每个组件独立测试（type-expert、attention、router、adaptation）
3. **集成测试**: 接入 computation_spine，验证 decision vector 输出合理
4. **性能基准**: 确保 < 1.5ms/forward on 1 core
5. **适应实验**: 模拟 1000 次 feedback 循环，验证 BCM/Oja 收敛性
6. **可视化**: notebook 中绘制 router bias 漂移、attention prior 演化
7. **合并**: 通过所有测试后，替换主仓库 hgt.py

### 关键技能要求

| 技能 | 用途 |
|------|------|
| Python 纯数值计算 | 手写矩阵运算、softmax、RMSNorm |
| Transformer 架构 | Multi-head attention、residual、normalization |
| MoE 路由机制 | Top-k gating、load balancing、sparse activation |
| Hebbian 学习理论 | Oja's rule、BCM theory、competitive learning |
| 性能优化 | flat array storage、避免 Python 对象开销 |
| 确定性参数派生 | SHA-256 → 伪随机矩阵生成 |

### 从主仓库继承的接口契约

```python
class HeterogeneousGraphTransformer:
    """接口必须与主仓库完全兼容。"""
    
    def __init__(self, d_model: int = 16, n_heads: int = 4, d_output: int = 4):
        ...
    
    def derive_params(self, personality: dict[str, float]) -> None:
        """从 Big Five 人格 traits 派生所有参数。
        
        personality keys: extraversion, neuroticism, conscientiousness,
                         openness, agreeableness (all float 0-1)
        """
        ...
    
    def forward(self, tokens: list[tuple[str, list[float]]]) -> list[float]:
        """前向传播。
        
        Args:
            tokens: [(type_name, 16-dim vector), ...] 共 7 个
        Returns:
            4-dim decision vector [d0, d1, d2, d3]
        """
        ...
    
    def build_tokens_from_spine(
        self, *, scar_state, void_space, boundary,
        personality: dict, surprise: float, expression,
        hdc_features: list[float]
    ) -> list[tuple[str, list[float]]]:
        """从 spine 子系统构建 7 个 typed tokens。"""
        ...
    
    # === 新增接口 ===
    
    def adapt(self, outcome: str, attention_snapshot: list[list[float]] | None = None) -> None:
        """Hebbian 慢适应。outcome: "accepted"|"ignored"|"rejected" """
        ...
    
    def adaptation_state(self) -> dict[str, Any]:
        """返回当前适应状态（用于 WebUI/诊断）。"""
        ...
    
    def to_dict(self) -> dict[str, Any]:
        """序列化适应状态用于持久化。"""
        ...
    
    def from_dict(self, data: dict[str, Any]) -> None:
        """从持久化数据恢复适应状态。"""
        ...
```

### TOKEN_TYPES 定义（不可修改）

```python
TOKEN_TYPES = ("scar", "void", "boundary", "personality", "surprise", "expression", "context")
```

7 个 token 类型对应 7 层计算栈的信号源。顺序和命名是公理级约束。

### 与主仓库的差异追踪

实验完成后需要合并的改动：

| 主仓库文件 | 实验文件 | 改动类型 |
|-----------|---------|---------|
| `sylanne_alpha/hgt.py` | `src/hgt_moe.py` | 完全替换 |
| `sylanne_alpha/computation_spine.py` | `src/computation_spine.py` | 增量修改（feedback 传递 + to_dict/from_dict） |
| `tests/test_sylanne_alpha_kernel.py` | `tests/test_moe_hgt.py` | 新增测试合并 |
| `theory/` | `theory/moe_hgt_axioms.md` | 新增文件 |

### 实验成功标准

1. **功能正确**: 所有 82 个主仓库测试通过（接口兼容）
2. **性能达标**: forward() p99 < 1.5ms on 1c1g
3. **适应有效**: 1000 次 "accepted" feedback 后，router bias 向活跃 expert 偏移 > 0.1
4. **适应稳定**: 10000 次随机 feedback 后，所有 bias/drift 保持在边界内
5. **Expert 特化**: 不同情境下 router 选择不同的 top-2 experts（entropy > 1.0）
6. **决策质量**: 与旧 HGT 对比，decision vector 在极端输入下更合理（无 NaN/Inf）
