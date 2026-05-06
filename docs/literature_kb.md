# 文献知识库说明

本项目的情绪模型文献知识库存放在 [`literature_kb/`](../literature_kb/)。

## 构建结果

- 去重文献：1727 篇。
- 顶刊/高影响候选：120 篇。
- 数据源：OpenAlex Works API。
- 构建时间：2026-05-07。
- 构建脚本：[`scripts/build_literature_kb.py`](../scripts/build_literature_kb.py)。

## 文件结构

| 文件 | 用途 |
| --- | --- |
| `literature_kb/works.jsonl` | 去重后的机器可读文献库 |
| `literature_kb/works.csv` | 便于表格检索的文献索引 |
| `literature_kb/top_journal_candidates.jsonl` | 顶刊/高影响候选 |
| `literature_kb/top_journal_candidates.csv` | 顶刊/高影响候选表格版 |
| `literature_kb/evidence-map.md` | 证据-论点映射草稿 |
| `literature_kb/topic-summary.md` | 主题、检索式和期刊分布 |
| `literature_kb/manifest.json` | 检索式、计数、顶刊白名单和构建元数据 |
| `literature_kb/raw/*.jsonl` | 每个检索主题的 OpenAlex 原始返回 |

## 主题覆盖

知识库按以下主题检索和归档：

- appraisal 与 action tendency。
- 人格差异与情绪动力学。
- 愤怒、归责、意图和冒犯。
- 宽恕、道歉、补救和信任修复。
- 回避、冷处理、沉默、排斥和 demand-withdraw。
- 情感计算、可信代理、对话机器人和 LLM agent。

## 使用原则

`evidence-map.md` 是基于标题、摘要索引、DOI 元数据、期刊和检索主题生成的证据地图。它适合做模型设计依据，但不是全文精读结果。若某个公式权重、阈值或论文段落需要强断言，应继续读取对应全文或至少核验摘要。

插件中的 `appraisal.conflict_analysis.evidence` 只记录解释依据：

```json
{
  "primary_theory": "appraisal",
  "citation_ids": ["KB0031"],
  "evidence_strength": "moderate",
  "uncertainty_reason": "上下文不足，意图归因不稳定"
}
```

这些字段不会直接提高情绪置信度，也不会绕过半衰期、clamp、安全边界或重置后门。文献增强的目标是提高可解释性和约束力，不是给更强烈的情绪后果背书。

## 复跑命令

```powershell
py -3.13 scripts\build_literature_kb.py --out literature_kb --per-query 120 --top-count 120 --mailto codex@example.com
```

脚本支持断点缓存。若网络中断，已完成的 `raw/*.jsonl` 会被复用；若缓存文件损坏，脚本会自动重新拉取对应主题。
