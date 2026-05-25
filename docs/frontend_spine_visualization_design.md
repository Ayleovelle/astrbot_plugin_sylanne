# 七层计算神经脊可视化 — 前端设计文档

## 背景

WebUI 的七层计算可视化面板（pane-spine）因 bug 过多暂时雪藏。本文档记录重新设计的方案，供前端开发者实现。

## 核心原则

1. **数据是事件驱动的，不是实时流** — 后端只在收到消息时产生一次计算输出，两条消息之间没有新数据
2. **没有新数据时保持上次有效值** — 不要用零值覆盖
3. **物理动画和数据面板分离** — L6 膜振动、L7 气泡等物理动画持续 60fps，数据面板只在 tick 变化时重绘
4. **后端提供 tick_count** — 前端通过比较 tick 判断是否有新计算

## 数据流架构

```
后端 /api/state (每3秒poll)
    ├── tick_count: 计算栈执行次数
    ├── layers: {
    │     L1_HDC: { sample_bits, density, flip_ratio, prediction_similarity, vector_dim }
    │     L2_Gate: { surprise, route, mean_surprise }
    │     L3_VoidScar: { emotion观测值, void/scar统计 }
    │     L4_Sheaf: { propagation, energy, dissociation, affected_dims }
    │     L5_HGT: { attention[7x7], experts{active,gates,names}, decision[4], adaptation }
    │     L6_Boundary: { boundary_integrity, internal_entropy, stability, phase_transitions }
    │     L7_Expression: { pressure, threshold, mode, silence_duration }
    │   }
    ├── emotion: { warmth, arousal, valence, tension, curiosity, ... }
    └── feedback: { accepted, ignored, rejected }

前端状态管理:
    let _lastTick = -1;
    let _canvasDirty = false;
    
    syncServerState() {
      if (data.tick_count > _lastTick) {
        _lastTick = data.tick_count;
        更新 sysState.layers;
        _canvasDirty = true;
      }
    }
    
    draw() {
      if (isPhysicsTab) { 物理动画(); }
      if (_canvasDirty) { 数据面板重绘(); _canvasDirty = false; }
    }
```

## 各层可视化方案

### L1 HDC 感知编码

**左侧：** 消息列表（IN/OUT），点击选中
**中间：** HDC sample_bits 网格（32×64 = 2048 bit），选中消息的 bits
**右侧：** 编码指标（density, flip_ratio, prediction_similarity）

**交互：** 点击左侧消息 → 中间显示该消息的 bits → 右侧显示该消息的指标
**注意：** 用户手动选中后不自动切换（`_l1UserSelected` flag，30s 超时重置）

### L2 预测编码门控

**主体：** surprise 历史曲线（最近 60 个采样点）
**标注：** 当前 route（Fast/Normal/Full）+ 阈值虚线
**底部：** 路由分布统计（fast N / normal N / full N）

**不需要物理动画。** 只在 tick 变化时追加一个点到曲线。

### L3 Void-Scar 耦合引擎

**左侧：** 八维情绪状态条形图（温暖/唤醒/正负价/紧张/好奇/修复/表达/边界）
**右侧：** Void/Scar/Ghost 统计 + 总压力 + 相干度
**底部：** 耦合事件日志（最近 5 条）

**动态比例尺：** 当所有值 < 0.1 时自动放大（标注 "×N"）

### L4 关系层切

**左侧：** 传播管线动画（3 个节点：输入→传播→输出）
**中间：** 受影响维度条形图（8 维，中文名：温暖/唤醒/正负价/紧张/好奇/修复/表达/边界）
**右侧：** 关系能量 / 解离压力 / 传播衰减 / 传播状态

### L5 MoE-HGT 决策融合

**主体：** 7×7 attention 热力图（行列标签：scar/void/boundary/personality/surprise/expression/context）
**右侧：** Expert 激活状态（5 个 expert 的 gate 值条形图）
**底部：** 4 维决策向量（d0 表达驱动 / d1 边界灵敏 / d2 紧急度 / d3 抑制）

**等待状态：** 如果 attention 为空，显示"等待首次消息处理"

### L6 自创生边界（物理动画）

**主体：** 32 点圆形膜 + 弹簧物理（Hooke's law + damping）
**数据驱动：** 
- `boundary_integrity` → 膜的基础半径
- `internal_entropy` → 膜的抖动幅度
- `phase_transitions` → 触发一次凹陷动画

**物理动画持续运行（60fps）。** 数据变化时更新物理参数，不重置动画状态。

**底部遥测：** 完整性 / 稳定性 / 熵 数值显示

### L7 相变表达（物理动画）

**主体：** 试管液面动画（液面 = pressure / threshold）
**数据驱动：**
- `pressure` → 液面高度
- `threshold` → 虚线标记
- `mode` → 颜色（silent=蓝, hint=黄, normal=橙, urgent=红）

**物理动画：** 气泡粒子从底部上升，速度 = pressure 大小

## 反馈计数

使用中文标签 + 颜色：
```html
<span style="color:var(--green)">接受 N</span>
<span style="color:var(--text-muted)">忽略 N</span>
<span style="color:var(--red)">拒绝 N</span>
```

## 会话选择

使用 `localStorage.getItem('sylanne_webui_session')` 记住上次选择。切换时 reset `_lastTick = -1`。

## 已知约束

- 单 HTML 文件（~5600 行），无模块化
- Canvas 2D API 不解析 CSS 变量 — 必须用 `getComputedStyle` 先读取
- `sysState` 是全局共享状态，160+ 处读取
- LocalSimulator（离线预览）直接写 sysState，不能用 Proxy 包装
- 无自动化测试覆盖前端

## 人格雷达图（未来面板）

**位置：** 新 tab 或嵌入主面板
**内容：**
- 5 维雷达图（Embodiment 五维当前值）
- 每个维度旁边显示漂移方向箭头（↑/↓/→）
- 漂移事件日志（最近 10 条）：`[时间] 信号 → 维度 ±值`
- 自然语言摘要："她最近变得更敏感了"

**数据来源：** 后端 `/api/state` 需要新增 `personality` 字段：
```json
{
  "embodiment_traits": {
    "expression_drive_trait": 0.62,
    "perception_acuity": 0.71,
    "boundary_permeability": 0.48,
    "inner_order": 0.55,
    "relational_gravity": 0.53
  },
  "drift_events": [
    {"tick": 142, "signal": "feedback_accepted", "trait": "expression_drive_trait", "delta": 0.002}
  ]
}
```
