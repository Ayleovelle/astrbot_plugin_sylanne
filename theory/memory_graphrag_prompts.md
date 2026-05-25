# L3 GraphRAG 压缩层：提示词与抽取逻辑设计

## 概述

当 L2 温池中的记忆片段权重衰减至 0.15 以下时，系统将 5-10 条片段批量送入 LLM 进行实体/关系抽取。抽取的三元组存入 L3 冷池图结构，原始文本随即删除。

本文档定义：
1. 实体抽取提示词模板
2. 输出 JSON Schema
3. 实体合并算法
4. 图查询（召回）提示词
5. 清晰度衰减机制
6. 完整示例场景

---

## 1. 实体抽取提示词

### 设计原则

- 最小 token 消耗（运行在后台 assessor，成本敏感）
- 对残缺/模糊片段鲁棒
- 中文优先，兼容英文混合输入
- 输出严格 JSON，无多余解释

### 提示词模板

```
[SYSTEM]
你是记忆压缩器。从对话片段中抽取实体和关系，输出JSON。

规则：
- 实体类型：person/topic/event/preference/boundary/emotion
- 关系必须连接两个已抽取的实体
- emotion_weight：-1(极负面)到1(极正面)
- clarity：0(极模糊/推测)到1(明确陈述)
- 片段残缺时降低clarity，不要编造信息
- 同一实体多次出现只抽取一次，取最高clarity
- temporal_type 必填：
  permanent = 不会变的事实（名字、性别、家庭关系）
  evolving = 会随时间改变的（年级、工作、住址、感情状态）
  episodic = 一次性事件（某天做了什么、某次对话内容）
- evolving 类型必须附带 valid_from（推断生效时间，格式 YYYY-MM 或 YYYY）
- 无法判断时间类型时默认 episodic

[USER]
压缩以下记忆片段为图结构：

{fragments}

输出格式：
{"entities":[...],"relations":[...]}
```

### 输出 JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["entities", "relations"],
  "properties": {
    "entities": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "label", "type", "clarity", "temporal_type"],
        "properties": {
          "id": {
            "type": "string",
            "description": "短标识符，如 e1, e2..."
          },
          "label": {
            "type": "string",
            "description": "实体名称，中文优先"
          },
          "type": {
            "type": "string",
            "enum": ["person", "topic", "event", "preference", "boundary", "emotion"]
          },
          "temporal_type": {
            "type": "string",
            "enum": ["permanent", "evolving", "episodic"],
            "description": "permanent=不变事实, evolving=会变, episodic=一次性"
          },
          "valid_from": {
            "type": "string",
            "description": "evolving类型必填，格式YYYY-MM或YYYY"
          },
          "clarity": {
            "type": "number",
            "minimum": 0,
            "maximum": 1
          }
        }
      }
    },
    "relations": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["source", "target", "relation", "emotion_weight", "clarity", "temporal_type"],
        "properties": {
          "source": { "type": "string" },
          "target": { "type": "string" },
          "relation": {
            "type": "string",
            "description": "关系谓词，如 喜欢/讨厌/参与/设定/触发"
          },
          "temporal_type": {
            "type": "string",
            "enum": ["permanent", "evolving", "episodic"]
          },
          "valid_from": {
            "type": "string",
            "description": "evolving类型必填"
          },
          "emotion_weight": {
            "type": "number",
            "minimum": -1,
            "maximum": 1
          },
          "clarity": {
            "type": "number",
            "minimum": 0,
            "maximum": 1
          }
        }
      }
    }
  }
}
```

---

## 2. 时间类型与衰减策略

### temporal_type 语义

| 类型 | 含义 | 示例 | clarity 衰减率 |
| --- | --- | --- | --- |
| `permanent` | 不随时间改变的事实 | 名字、性别、家庭关系、出生地 | 标准衰减 `*0.998` |
| `evolving` | 会随时间改变的状态 | 年级、工作、住址、感情状态、年龄 | 加速衰减 `*0.993` |
| `episodic` | 一次性事件 | 某天吃了什么、某次对话内容 | 标准衰减 `*0.998` |

### evolving 类型的特殊处理

```python
def evolving_clarity_decay(node: GraphNode, current_date: str) -> float:
    """evolving 类型的 clarity 随时间距离加速衰减。
    
    距离 valid_from 越远，越可能已经过时。
    """
    base_decay = 0.993  # 比标准 0.998 更快
    
    if node.valid_from:
        months_elapsed = months_between(node.valid_from, current_date)
        # 超过12个月的 evolving 信息，衰减加倍
        if months_elapsed > 12:
            return base_decay ** 2  # 0.986
        # 超过6个月，轻微加速
        if months_elapsed > 6:
            return base_decay * 0.997  # ~0.990
    
    return base_decay
```

### 召回时的确认机制

当 evolving 类型节点的 clarity 低于 0.4 时，系统不应断言该信息，而应生成确认性表达：

```python
def format_evolving_recall(node: GraphNode) -> str:
    """低 clarity 的 evolving 节点生成确认式表达而非断言。"""
    if node.clarity >= 0.6:
        return f"{node.label}"  # 直接使用
    elif node.clarity >= 0.4:
        return f"{node.label}（可能已变）"  # 标记不确定
    else:
        return f"之前提到过{node.label}，不确定现在是否还是"  # 主动确认
```

---

## 3. 实体合并算法

### 模糊匹配规则

```python
def fuzzy_match_entity(new_entity: dict, existing_nodes: list[dict]) -> dict | None:
    """在已有图中查找与新实体匹配的节点。
    
    匹配策略（按优先级）：
    1. label 完全相同 且 type 相同 → 确定匹配
    2. label 包含关系（子串）且 type 相同 → 可能匹配，需 clarity > 0.5
    3. label 编辑距离 <= 2 且 type 相同 → 可能匹配（处理错别字）
    """
    for node in existing_nodes:
        if node["label"] == new_entity["label"] and node["type"] == new_entity["type"]:
            return node
    
    for node in existing_nodes:
        if node["type"] != new_entity["type"]:
            continue
        # 子串匹配：「小明」匹配「小明同学」
        if (new_entity["label"] in node["label"] or node["label"] in new_entity["label"]):
            if new_entity["clarity"] > 0.5:
                return node
        # 编辑距离（适用于短标签）
        if len(node["label"]) <= 6 and edit_distance(node["label"], new_entity["label"]) <= 2:
            return node
    
    return None
```

### 节点合并

```python
def merge_entity(existing: GraphNode, new_data: dict) -> GraphNode:
    """合并同一实体的新旧信息。"""
    # clarity 取较高值（新信息更清晰则更新）
    existing.clarity = max(existing.clarity, new_data["clarity"])
    
    # temporal_type 升级规则：
    # episodic 可被升级为 evolving 或 permanent（更多信息确认了持久性）
    # evolving 可被升级为 permanent（确认不会变）
    # 但 permanent 不会降级
    TEMPORAL_RANK = {"episodic": 0, "evolving": 1, "permanent": 2}
    new_rank = TEMPORAL_RANK[new_data["temporal_type"]]
    old_rank = TEMPORAL_RANK[existing.temporal_type]
    if new_rank > old_rank and new_data["clarity"] >= 0.7:
        existing.temporal_type = new_data["temporal_type"]
    
    # valid_from 取最新值（evolving 类型）
    if new_data.get("valid_from") and existing.temporal_type == "evolving":
        existing.valid_from = new_data["valid_from"]
    
    # 刷新 last_seen 时间戳
    existing.last_seen = current_tick()
    
    return existing
```

### 关系合并

```python
def merge_relation(existing: GraphEdge, new_data: dict) -> GraphEdge:
    """合并同一对实体间的同名关系。"""
    # emotion_weight 取加权平均（新数据权重略高）
    alpha = 0.6  # 新数据权重
    existing.emotion_weight = (
        alpha * new_data["emotion_weight"] +
        (1 - alpha) * existing.emotion_weight
    )
    
    # clarity 取最大值
    existing.clarity = max(existing.clarity, new_data["clarity"])
    
    # temporal_type 同节点规则
    TEMPORAL_RANK = {"episodic": 0, "evolving": 1, "permanent": 2}
    if TEMPORAL_RANK[new_data["temporal_type"]] > TEMPORAL_RANK[existing.temporal_type]:
        if new_data["clarity"] >= 0.7:
            existing.temporal_type = new_data["temporal_type"]
    
    existing.last_seen = current_tick()
    return existing


def handle_contradiction(existing: GraphEdge, new_data: dict) -> GraphEdge:
    """处理矛盾关系（emotion_weight 符号相反）。
    
    人可以是矛盾的。保留两条边，但降低 clarity。
    """
    # 如果新旧 emotion_weight 符号相反且差距大于 0.5
    if (existing.emotion_weight * new_data["emotion_weight"] < 0 and
        abs(existing.emotion_weight - new_data["emotion_weight"]) > 0.5):
        # 降低旧边 clarity（不再确定）
        existing.clarity *= 0.7
        # 创建新边（矛盾共存）
        new_edge = GraphEdge(
            source=existing.source,
            target=existing.target,
            relation=new_data["relation"],
            emotion_weight=new_data["emotion_weight"],
            clarity=new_data["clarity"] * 0.8,  # 新边也降低（矛盾本身降低确定性）
            temporal_type=new_data["temporal_type"],
            valid_from=new_data.get("valid_from"),
            contradiction_of=existing.id,
        )
        return new_edge
    
    # 差距不大，正常合并
    return merge_relation(existing, new_data)
```

### 完整合并流程

```python
def ingest_extraction_batch(graph: MemoryGraph, extraction: dict) -> MergeReport:
    """将一次 LLM 抽取结果合并入图。"""
    report = MergeReport()
    id_map = {}  # 临时ID → 图中实际节点ID
    
    # Phase 1: 合并实体
    for entity in extraction["entities"]:
        match = fuzzy_match_entity(entity, graph.nodes)
        if match:
            merge_entity(match, entity)
            id_map[entity["id"]] = match.id
            report.merged_entities += 1
        else:
            new_node = graph.add_node(entity)
            id_map[entity["id"]] = new_node.id
            report.new_entities += 1
    
    # Phase 2: 合并关系
    for rel in extraction["relations"]:
        source_id = id_map.get(rel["source"])
        target_id = id_map.get(rel["target"])
        if not source_id or not target_id:
            report.dropped_relations += 1
            continue
        
        existing_edge = graph.find_edge(source_id, target_id, rel["relation"])
        if existing_edge:
            handle_contradiction(existing_edge, rel)
            report.merged_relations += 1
        else:
            graph.add_edge(source_id, target_id, rel)
            report.new_relations += 1
    
    return report
```

---

## 4. 图查询提示词（召回）

### 查询流程

```text
当前消息 → 实体提取(轻量) → 图匹配 → 1-2跳遍历 → 自然语言格式化
```

### 轻量实体提取提示词（用于查询时）

```text
[SYSTEM]
从用户消息中提取关键实体名称，用于记忆检索。只输出JSON数组。

[USER]
消息：{current_message}

输出：["实体1", "实体2", ...]
```

### 图遍历算法

```python
def query_graph(
    graph: MemoryGraph,
    message: str,
    extracted_entities: list[str],
    max_hops: int = 2,
    max_results: int = 15,
) -> list[RecallResult]:
    """从当前消息实体出发，遍历图获取相关记忆。"""
    
    # Step 1: 精确匹配 + 模糊匹配找到种子节点
    seed_nodes = []
    for entity_label in extracted_entities:
        # 精确匹配
        exact = graph.find_node_by_label(entity_label)
        if exact:
            seed_nodes.append((exact, 1.0))  # 匹配置信度
            continue
        # 模糊匹配
        fuzzy = graph.fuzzy_find(entity_label, threshold=0.7)
        for node, score in fuzzy:
            seed_nodes.append((node, score))
    
    if not seed_nodes:
        return []
    
    # Step 2: BFS 遍历 1-2 跳
    visited = set()
    results = []
    
    for seed, match_score in seed_nodes:
        _bfs_collect(graph, seed, match_score, max_hops, visited, results)
    
    # Step 3: 按相关性排序
    results.sort(key=lambda r: r.relevance_score, reverse=True)
    return results[:max_results]


def _bfs_collect(
    graph: MemoryGraph,
    start: GraphNode,
    match_score: float,
    max_hops: int,
    visited: set,
    results: list,
):
    """BFS 收集节点，距离越远 relevance 越低。"""
    queue = [(start, 0)]  # (node, hop_distance)
    
    while queue:
        node, dist = queue.pop(0)
        if node.id in visited or dist > max_hops:
            continue
        visited.add(node.id)
        
        # 计算相关性：匹配分 * 距离衰减 * clarity
        relevance = match_score * (0.7 ** dist) * node.clarity
        
        if relevance > 0.05:  # 过滤噪声
            results.append(RecallResult(
                node=node,
                hop_distance=dist,
                relevance_score=relevance,
            ))
        
        # 扩展邻居
        for edge in graph.edges_of(node.id):
            neighbor = graph.get_node(edge.other_end(node.id))
            if neighbor and neighbor.id not in visited:
                queue.append((neighbor, dist + 1))
```

### 召回结果格式化

将图查询结果转为自然语言，附带 clarity 标记：

```python
def format_recall_for_prompt(results: list[RecallResult]) -> str:
    """将 L3 召回结果格式化为可注入 prompt 的文本。"""
    if not results:
        return ""
    
    lines = ["[长期记忆参考]"]
    
    for r in results:
        node = r.node
        clarity_marker = _clarity_marker(node.clarity, node.temporal_type)
        
        # 格式化节点本身
        if node.type == "preference":
            lines.append(f"- {clarity_marker}{node.label}")
        elif node.type == "boundary":
            lines.append(f"- {clarity_marker}[边界] {node.label}")
        elif node.type == "person":
            # 收集该人物的关系边
            edges = [e for e in r.connected_edges if e.clarity > 0.2]
            if edges:
                edge_strs = [f"{e.relation}({_format_target(e)})" for e in edges[:3]]
                lines.append(f"- {clarity_marker}{node.label}：{'，'.join(edge_strs)}")
            else:
                lines.append(f"- {clarity_marker}{node.label}")
        else:
            lines.append(f"- {clarity_marker}{node.label}")
    
    return "\n".join(lines)


def _clarity_marker(clarity: float, temporal_type: str) -> str:
    """根据 clarity 和时间类型生成标记。"""
    # evolving 类型额外标记
    evolving_flag = "⟳" if temporal_type == "evolving" else ""
    
    if clarity >= 0.8:
        return evolving_flag  # 高确信无需标记
    elif clarity >= 0.5:
        return f"[约]{evolving_flag}"  # 中等确信
    elif clarity >= 0.3:
        return f"[模糊]{evolving_flag}"  # 低确信
    else:
        return f"[极模糊]{evolving_flag}"  # 极低确信，接近GC阈值
```

---

## 5. Clarity 衰减与生命周期

### 衰减公式

```python
def tick_clarity_decay(graph: MemoryGraph, current_date: str):
    """每 tick 执行一次 clarity 衰减。"""
    for node in graph.all_nodes():
        if node.temporal_type == "evolving":
            decay_rate = evolving_clarity_decay(node, current_date)
        else:
            decay_rate = 0.998  # 标准衰减
        
        node.clarity *= decay_rate
    
    for edge in graph.all_edges():
        if edge.temporal_type == "evolving":
            decay_rate = evolving_clarity_decay(edge, current_date)
        else:
            decay_rate = 0.998
        
        edge.clarity *= decay_rate


def on_recall_reinforce(node_or_edge):
    """被召回时强化 clarity。"""
    node_or_edge.clarity = min(1.0, node_or_edge.clarity + 0.05)
    node_or_edge.last_recalled = current_tick()
```

### 垃圾回收

```python
GC_THRESHOLD = 0.1

def garbage_collect(graph: MemoryGraph) -> GCReport:
    """清理 clarity 低于阈值的节点和边。"""
    report = GCReport()
    
    # 先清理边（避免悬挂引用）
    for edge in list(graph.all_edges()):
        if edge.clarity < GC_THRESHOLD:
            graph.remove_edge(edge.id)
            report.edges_removed += 1
    
    # 再清理孤立节点
    for node in list(graph.all_nodes()):
        if node.clarity < GC_THRESHOLD:
            # permanent 类型有保护：阈值降为 0.05
            if node.temporal_type == "permanent" and node.clarity >= 0.05:
                continue
            graph.remove_node(node.id)
            report.nodes_removed += 1
    
    return report
```

### 生命周期总结

```text
新抽取 (clarity=0.6~1.0)
    │
    ▼ 每tick * decay_rate
衰减中 (clarity 逐渐降低)
    │
    ├─ 被召回 → clarity += 0.05 (强化)
    │
    ▼ clarity < 0.1
垃圾回收 (节点/边删除)
```

permanent 类型的完整生命周期约 1150 tick 无召回才会被 GC（`0.998^1150 ≈ 0.1`）。
evolving 类型约 330 tick（`0.993^330 ≈ 0.1`），且超过 12 个月的更快。

---

## 6. 完整示例场景

### 场景 1：日常偏好记忆压缩

**输入片段（L2 衰减至 < 0.15 的批次）：**

```json
[
  "用户说喜欢抹茶味的东西",
  "用户提到在学计算机，大三",
  "用户说周末经常去图书馆",
  "用户叫小雨，女生",
  "聊到最近在看《三体》",
  "用户说不太喜欢太甜的饮料",
  "提到室友叫阿琳"
]
```

**LLM 抽取结果：**

```json
{
  "entities": [
    {"id": "e1", "label": "小雨", "type": "person", "temporal_type": "permanent", "clarity": 0.95},
    {"id": "e2", "label": "抹茶", "type": "preference", "temporal_type": "permanent", "clarity": 0.85},
    {"id": "e3", "label": "计算机专业大三", "type": "topic", "temporal_type": "evolving", "valid_from": "2025-09", "clarity": 0.9},
    {"id": "e4", "label": "图书馆", "type": "preference", "temporal_type": "evolving", "valid_from": "2025", "clarity": 0.7},
    {"id": "e5", "label": "《三体》", "type": "topic", "temporal_type": "episodic", "clarity": 0.75},
    {"id": "e6", "label": "太甜饮料", "type": "preference", "temporal_type": "permanent", "clarity": 0.8},
    {"id": "e7", "label": "阿琳", "type": "person", "temporal_type": "evolving", "valid_from": "2025", "clarity": 0.65}
  ],
  "relations": [
    {"source": "e1", "target": "e2", "relation": "喜欢", "emotion_weight": 0.7, "clarity": 0.85, "temporal_type": "permanent"},
    {"source": "e1", "target": "e3", "relation": "正在学", "emotion_weight": 0.3, "clarity": 0.9, "temporal_type": "evolving", "valid_from": "2025-09"},
    {"source": "e1", "target": "e4", "relation": "周末常去", "emotion_weight": 0.4, "clarity": 0.7, "temporal_type": "evolving", "valid_from": "2025"},
    {"source": "e1", "target": "e5", "relation": "在看", "emotion_weight": 0.5, "clarity": 0.75, "temporal_type": "episodic"},
    {"source": "e1", "target": "e6", "relation": "不喜欢", "emotion_weight": -0.5, "clarity": 0.8, "temporal_type": "permanent"},
    {"source": "e1", "target": "e7", "relation": "室友", "emotion_weight": 0.3, "clarity": 0.65, "temporal_type": "evolving", "valid_from": "2025"}
  ]
}
```

**合并后图状态（假设图中已有「小雨」节点）：**

- `小雨` 节点 clarity 从 0.8 → 0.95（取 max）
- 新增 `抹茶`、`计算机专业大三`、`图书馆`、`《三体》`、`太甜饮料`、`阿琳` 节点
- 新增 6 条关系边

**6 个月后召回效果：**

- `计算机专业大三`（evolving, valid_from 2025-09）clarity 已从 0.9 衰减至约 0.55
- 召回时输出：`[约]⟳计算机专业大三` — 系统不会断言"你是大三的"，而是作为参考

---

### 场景 2：情感/冲突记忆压缩

**输入片段：**

```json
[
  "用户说'别再提那件事了'",
  "用户表达了对被忽视的愤怒",
  "用户说前任叫阿轩，分手了",
  "用户说'我不想被当成情绪垃圾桶'",
  "用户提到和妈妈吵架了",
  "用户说需要独处的时间"
]
```

**LLM 抽取结果：**

```json
{
  "entities": [
    {"id": "e1", "label": "小雨", "type": "person", "temporal_type": "permanent", "clarity": 0.95},
    {"id": "e2", "label": "那件事", "type": "event", "temporal_type": "episodic", "clarity": 0.3},
    {"id": "e3", "label": "被忽视", "type": "emotion", "temporal_type": "episodic", "clarity": 0.85},
    {"id": "e4", "label": "阿轩", "type": "person", "temporal_type": "permanent", "clarity": 0.9},
    {"id": "e5", "label": "不要被当情绪垃圾桶", "type": "boundary", "temporal_type": "permanent", "clarity": 0.95},
    {"id": "e6", "label": "和妈妈吵架", "type": "event", "temporal_type": "episodic", "clarity": 0.8},
    {"id": "e7", "label": "妈妈", "type": "person", "temporal_type": "permanent", "clarity": 0.85},
    {"id": "e8", "label": "需要独处时间", "type": "boundary", "temporal_type": "permanent", "clarity": 0.9}
  ],
  "relations": [
    {"source": "e1", "target": "e2", "relation": "不想提起", "emotion_weight": -0.8, "clarity": 0.75, "temporal_type": "episodic"},
    {"source": "e1", "target": "e3", "relation": "感受到", "emotion_weight": -0.7, "clarity": 0.85, "temporal_type": "episodic"},
    {"source": "e1", "target": "e4", "relation": "前任", "emotion_weight": -0.4, "clarity": 0.9, "temporal_type": "permanent"},
    {"source": "e1", "target": "e5", "relation": "设定边界", "emotion_weight": 0.0, "clarity": 0.95, "temporal_type": "permanent"},
    {"source": "e1", "target": "e7", "relation": "吵架", "emotion_weight": -0.6, "clarity": 0.8, "temporal_type": "episodic"},
    {"source": "e1", "target": "e8", "relation": "需要", "emotion_weight": 0.2, "clarity": 0.9, "temporal_type": "permanent"}
  ]
}
```

**关键设计点：**

- `那件事` clarity 仅 0.3 — 片段本身就模糊，LLM 不编造具体内容
- `不要被当情绪垃圾桶` 和 `需要独处时间` 标记为 boundary + permanent — 这些是核心边界，衰减最慢
- `和妈妈吵架` 标记为 episodic — 一次性事件，不代表长期关系状态
- `前任` 关系标记为 permanent — 这个事实不会改变

---

### 场景 3：从 L3 召回（不同 clarity 级别）

**当前消息：** "今天又去图书馆了，看了一下午书"

**轻量实体提取结果：** `["图书馆"]`

**图遍历结果（1-2 跳）：**

| 节点 | 跳数 | clarity | temporal_type | relevance |
| --- | --- | --- | --- | --- |
| 图书馆 | 0 | 0.52 | evolving | 0.52 |
| 小雨→图书馆「周末常去」 | 0 | 0.48 | evolving | 0.48 |
| 小雨 | 1 | 0.95 | permanent | 0.67 |
| 小雨→计算机专业大三「正在学」 | 1 | 0.42 | evolving | 0.29 |
| 小雨→《三体》「在看」 | 1 | 0.15 | episodic | 0.11 |
| 阿琳 | 2 | 0.35 | evolving | 0.17 |

**格式化输出（注入 prompt）：**

```text
[长期记忆参考]
- [约]⟳周末经常去图书馆
- ⟳小雨：正在学(计算机专业大三，可能已变)
- [模糊]⟳阿琳是室友
```

**注意：**

- `《三体》`（episodic, clarity 0.15）接近 GC 阈值，relevance 0.11 低于输出门槛，不显示
- `计算机专业大三`（evolving, clarity 0.42）标记为"可能已变"
- `图书馆`（evolving, clarity 0.52）标记 `[约]⟳`
- 高 clarity 的 permanent 节点（如小雨本人）不需要标记

---

## 7. 实现备注

### Token 预算

| 操作 | 预估 token | 频率 |
| --- | --- | --- |
| 实体抽取（7 片段） | ~300 input + ~200 output | 每 50-100 tick 一次 |
| 轻量实体提取（查询） | ~50 input + ~30 output | 每条消息 |
| 总月成本（活跃用户） | ~2000 token/天 | — |

### 与现有架构的接口

```python
# 在 assessor_async.py 的 main assessor 中触发
class AsyncAssessor:
    async def assess_main(self, ...):
        # ... 现有逻辑 ...
        
        # 检查 L2 温池是否有待压缩批次
        decayed_batch = memory_pool.drain_below_threshold(0.15)
        if len(decayed_batch) >= 5:
            extraction = await self._extract_graph(decayed_batch, llm_caller)
            graph.ingest_extraction_batch(extraction)


# 在 embedding_memory.py 的 recall 流程中注入 L3 结果
def recall_with_embedding_assist(*, query, records, ...):
    # ... 现有 keyword + embedding 逻辑 ...
    
    # L3 GraphRAG 补充
    l3_results = graph.query(message=query, extracted_entities=extract_entities(query))
    l3_text = format_recall_for_prompt(l3_results)
    # 注入到最终 prompt context
```

### 安全约束

- L3 图数据标记 `internal_only: true`，不通过公开 API 暴露
- boundary 类型节点的 `emotion_weight` 不对外展示（避免泄露用户情绪边界细节）
- 所有原始文本在抽取完成后立即删除，图中只保留结构化标签
- evolving 类型节点在 clarity < 0.4 时，系统不得断言其内容为事实
