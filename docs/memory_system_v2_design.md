# Sylanne 三层记忆系统 v2 设计文档

更新日期：2026-05-23

## 核心变更（相对 v1）

| 维度 | v1（当前） | v2（本文档） |
|------|-----------|-------------|
| 写入时机 | 每条消息写原文到 L1 | 会话结束时写摘要到 L1 |
| L1 内容 | 原始消息碎片 | 对话摘要（双方） |
| embedding 触发 | main assessor 返回 memorable=1 | 同上，但基于摘要而非单条消息 |
| L2 下沉条件 | L1 溢出 + 有 embedding | 12h 定时整理匹配 |
| L2→L3 条件 | weight 低于阈值 | 30 天未被提起 |
| 召回后行为 | 温度漂移 | 文本重写（添油加醋）+ 温度漂移 |
| 提取（注入 prompt） | 有但依赖 embedding（实际为空） | 三层并行查询，分层表达 |

---

## 写入流程

### 触发条件（二选一，先到先触发）

1. **会话静默 1 分钟**：最后一条消息后 60s 无新消息 → 判定会话结束
2. **对话超过 20 轮**：连续对话轮次（用户+bot 各算一轮）达到 20 → 强制中间摘录

### 写入步骤

```
触发条件满足
    ↓
收集本轮对话原文（用户 + bot，从上次摘录点到现在）
    ↓
调用 LLM 生成摘要（后台，不阻塞）
    prompt: "将以下对话压缩为一段简短摘要，保留关键事实、情绪和承诺："
    ↓
摘要写入 L1（一条 MemoryItem，text=摘要）
    ↓
main assessor 判断摘要是否值得 embedding（m=1?）
    ↓ 是
调用 embedding provider → 存入该条目的 embedding 字段
```

### 对话暂存

对话进行中，原文暂存在内存 buffer（不写入 MemorySystem）：

```python
self._conversation_buffers: dict[str, list[dict]] = {}
# 每条消息 append: {"role": "user"|"bot", "text": "...", "ts": float}
```

摘录完成后清空 buffer（或保留最近 4h 的作为下次比对基础）。

### 20 轮保底机制

```python
# 在 on_llm_response 里计数
self._turn_counts[session_key] = self._turn_counts.get(session_key, 0) + 1
if self._turn_counts[session_key] >= 20:
    await self._flush_conversation_to_l1(session_key)
    self._turn_counts[session_key] = 0
```

---

## 12h 定时整理

### 触发

后台定时任务，每 12 小时执行一次（或插件启动时检查上次执行时间）。

### 流程

```
收集过去 12h 内所有对话原文
    ↓
LLM 生成 12h 总摘要
    ↓
和 L1 现有条目比对（关键词重叠 / embedding 相似度）
    ↓
匹配的条目：
  - 如果没有 embedding → 生成 embedding
  - 标记为"已确认"，可下沉到 L2
    ↓
不匹配的条目（L1 中超过 4h 且未被 12h 摘要确认的）：
  - 清空（认为不重要）
    ↓
已确认 + 有 embedding 的条目 → 移入 L2
```

### 配置

```python
MEMORY_CONSOLIDATION_INTERVAL_HOURS = 12
MEMORY_CONSOLIDATION_KEEP_RECENT_HOURS = 4  # 保留最近 4h 不清
```

---

## 召回流程（三层并行）

### 触发

每条用户消息进来时，在注入 prompt 前执行召回。

### 查询

```
用户消息 text
    ↓
并行查三层：
  L1: 关键词匹配（摘要文本 vs 当前消息）
      score = keyword_overlap × item.weight × 1.0
  
  L2: embedding 相似度（如果有 query embedding）
      score = cosine_sim × item.weight × 0.7 × mood_alignment
  
  L3: 实体关联（从消息提取实体 → 图遍历 1-2 跳）
      score = edge_weight × clarity × 0.4
    ↓
合并所有结果 → 按 score 降序 → 取 top-3
    ↓
注入 prompt（分层表达）
```

### 注入格式

```
[记忆参考]
近期：你们刚聊过关于地平线6的话题，你说想买但没钱
相关：之前有一次聊到过游戏，你提到喜欢开放世界
认知：这个人喜欢赛车游戏，对价格比较敏感
```

- L1 命中 → "近期：..."
- L2 命中 → "相关：..."
- L3 命中 → "认知：..."
- clarity < 0.7 的 L3 结果用不确定语气："好像提过..."

---

## 召回后重写（Reconsolidation v2）

### 触发

L2 条目被召回时。

### 流程

```
L2 条目被召回
    ↓
获取当前情绪状态（warmth, tension, valence）
    ↓
LLM 重写摘要（后台，不阻塞当前回复）
    prompt: "基于当前心情（warmth={w}, tension={t}），
            轻微改写这段记忆，让它带上当前的情绪色彩：
            原文：{original_text}
            改写后（保持事实不变，只调整语气和侧重）："
    ↓
重写结果覆盖原条目 text
    ↓
weight += 0.03
temperature 漂移
age_ticks 部分重置
```

### 约束

- 重写不改变事实（"喜欢猫"不会变成"不喜欢猫"）
- 只调整语气和侧重（开心时回忆变温暖，紧张时回忆变尖锐）
- 每条记忆最多重写 20 次（freeze_after_recalls = 20）
- 重写是后台异步的，不阻塞当前回复

---

## L2 → L3 压缩

### 触发条件

L2 条目 **30 天未被召回**（`age_ticks` 对应的实际时间超过 30 天）。

注意：不再用 weight 阈值，改用时间。因为 weight 会被召回加回来，但"30 天没人提起"是更准确的"已经模糊了"信号。

### 流程

```
L2 条目 30 天未被召回
    ↓
LLM 实体抽取（同 v1）
    ↓
三元组写入 L3 GraphRAG
    ↓
删除 L2 原文
```

### 时间计算

```python
# 每条消息 tick_decay 时 age_ticks += 1
# 假设平均每天 100 条消息 → 30 天 ≈ 3000 ticks
L2_COMPRESSION_AGE_TICKS = 3000  # 可配置
```

---

## 数据结构变更

### L1 MemoryItem（摘要，非原文）

```python
MemoryItem = {
    id: str,
    text: str,           # 对话摘要（不是单条消息）
    weight: float,       # 初始 1.0
    temperature: float,  # 写入时的情绪温度
    age_ticks: int,      # 自上次被召回以来的 tick 数
    embedding: list[float] | None,
    created_at: float,
    source_turns: int,   # 本摘要覆盖了多少轮对话
    confirmed: bool,     # 是否被 12h 整理确认过
}
```

### 对话暂存 Buffer

```python
ConversationBuffer = {
    session_key: str,
    messages: [
        {"role": "user", "text": "...", "ts": 1234567890.0},
        {"role": "bot", "text": "...", "ts": 1234567891.0},
    ],
    last_activity: float,  # 最后一条消息的时间戳
    turn_count: int,       # 当前轮次计数
    last_flush_ts: float,  # 上次摘录的时间戳
}
```

---

## 定时任务

| 任务 | 频率 | 触发方式 |
|------|------|---------|
| 会话结束检测 | 每 10s 检查一次 | asyncio 定时器 |
| 12h 整理 | 每 12h | asyncio 定时器 / 插件启动时补跑 |
| L2→L3 压缩检查 | 每 1h | asyncio 定时器 |
| L3 clarity 衰减 | 每条消息 tick | 同步 |

---

## LLM 调用预算

| 操作 | 模型 | 频率 | 预估 token/次 |
|------|------|------|--------------|
| 对话摘要 | main assessor provider | 每次会话结束 | ~200 input + ~100 output |
| memorable 判断 | main assessor provider | 每次摘要后 | ~50 input + ~10 output |
| 12h 总摘要 | main assessor provider | 每 12h | ~500 input + ~200 output |
| 召回重写 | main assessor provider | 每次 L2 被召回 | ~100 input + ~80 output |
| L3 实体抽取 | main assessor provider | L2 条目过期时 | ~200 input + ~100 output |

日均（假设 10 次会话，每次 ~15 轮）：
- 摘要：10 次 × 300 token = 3000 token
- memorable：10 次 × 60 token = 600 token
- 12h 整理：2 次 × 700 token = 1400 token
- 召回重写：~5 次 × 180 token = 900 token
- **日均总计：~6000 token**（约 ¥0.01-0.05，取决于模型）

---

## 人格调制（继承 v1）

| 人格维度 | 影响 |
|---------|------|
| Conscientiousness | 12h 整理的严格程度（高 C → 保留更多） |
| Neuroticism | 负面记忆的 30 天阈值延长（高 N → 负面记忆更难忘） |
| Openness | 重写幅度（高 O → 重写更大胆） |
| Agreeableness | 召回偏置（高 A → 正面记忆更容易浮现） |

---

## 与现有代码的关系

### 保留

- `MemorySystem` 类的基本结构（L1/L2/L3 三层）
- `recall()` 方法的三层并行查询
- `to_dict()` / `from_dict()` 序列化
- GraphRAG 的节点/边结构

### 需要新增

- `ConversationBuffer` 暂存管理
- 会话结束检测定时器（10s 轮询）
- `flush_to_l1()` 摘要生成 + 写入
- 12h 定时整理任务
- 召回后重写逻辑
- 30 天未提起 → L3 压缩逻辑

### 需要删除/替换

- 每条消息直接 `write()` 到 L1 的逻辑
- `_overflow_to_l2()` 的 L1 满溢出机制（改为 12h 整理下沉）
- 基于 weight 阈值的 `compress_check()`（改为 30 天时间阈值）

---

## 验收标准

1. 对话中不写记忆，会话结束后 L1 出现摘要
2. 20 轮保底：长对话中途也会产生摘要
3. 12h 后 L2 有内容（被确认 + 有 embedding 的摘要下沉）
4. 召回时三层都能返回结果，prompt 里能看到 `[记忆参考]`
5. L2 被召回的条目文本会被轻微改写
6. 30 天未提起的 L2 条目被压缩到 L3
7. WebUI 记忆池页面能看到三层都有数据
