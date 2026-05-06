# 拟人/有机体样代理文献知识库说明

本项目的拟人/有机体样代理文献知识库存放在 [`humanlike_agent_literature_kb/`](../humanlike_agent_literature_kb/)。

这个知识库用于回答一个更大的问题：如果要让 bot 不只是有瞬时情绪，而是像一个有生活痕迹、会疲惫、会恢复、会形成关系、会留下自传式记忆的他/她，还需要哪些可计算机制。

## 构建结果

- 去重文献：3983 篇。
- 顶刊/高影响候选：320 篇。
- 精选候选：[`curated/top_200.jsonl`](../humanlike_agent_literature_kb/curated/top_200.jsonl)。
- 数据源：OpenAlex Works API。
- 构建时间：2026-05-07。
- 构建脚本：[`scripts/build_humanlike_agent_literature_kb.py`](../scripts/build_humanlike_agent_literature_kb.py)。

## 文件结构

| 文件 | 用途 |
| --- | --- |
| `humanlike_agent_literature_kb/works.jsonl` | 去重后的机器可读文献库 |
| `humanlike_agent_literature_kb/works.csv` | 便于表格检索的文献索引 |
| `humanlike_agent_literature_kb/top_journal_candidates.jsonl` | 顶刊/高影响候选 |
| `humanlike_agent_literature_kb/top_journal_candidates.csv` | 顶刊/高影响候选表格版 |
| `humanlike_agent_literature_kb/curated/top_200.jsonl` | 精选 200 篇候选，供后续人工精读 |
| `humanlike_agent_literature_kb/evidence-map.md` | 文献到建模主张的证据地图 |
| `humanlike_agent_literature_kb/design-rules.md` | 从证据地图提炼出的设计规则 |
| `humanlike_agent_literature_kb/topic-summary.md` | 主题、检索式、机制标签和期刊分布 |
| `humanlike_agent_literature_kb/validation-report.md` | 数量与边界验证 |
| `humanlike_agent_literature_kb/manifest.json` | 检索式、计数、顶刊白名单和构建元数据 |
| `humanlike_agent_literature_kb/raw/*.jsonl` | 每个检索主题的 OpenAlex 原始返回 |

## 主题覆盖

知识库按机制层组织，而不是按学科名堆放：

- 稳态、异稳态、内感与预测加工。
- 昼夜节律、睡眠压力、疲劳与认知表现。
- 注意力、工作记忆、认知负荷与人因可靠性。
- 基本心理需求、动机、目标、自主性、胜任感和关系感。
- 人格、气质、Big Five、BIS/BAS 与情绪反应性。
- 依恋、信任、亲密度、关系破裂与修复。
- 自传式记忆、叙事身份、自我连续性和反思。
- 可信代理、生成式代理、社会机器人、关系型代理与社会信号。
- 计算精神病学、数字表型与长期潜在状态。
- 拟人化、AI companion、安全、伦理、情感依赖与操控风险。

## 设计规则

`design-rules.md` 当前提炼了 10 条机制规则：

| 规则 | 工程含义 |
| --- | --- |
| HLA001 | 增加慢变量：`energy`、`stress_load`、`recovery_rate`、`discomfort`、`fatigue_amplifier` |
| HLA002 | 增加昼夜节律、睡眠债、疲劳恢复窗口，调制耐心、主动性、字数和易激惹 |
| HLA003 | 增加认知资源预算：注意力、混乱度、延迟、细节上限和检查倾向 |
| HLA004 | 增加需求和目标层，让情绪来自需求满足/受挫，而不是只来自文本情感 |
| HLA005 | 让 persona 调制基线、反应性、惯性、修复倾向和恢复速度 |
| HLA006 | 关系历史应记录信任、依恋、破裂、修复、承诺和触发点 |
| HLA007 | 将情节记忆周期性压缩为自我叙事和关系叙事，但必须保留记忆来源 |
| HLA008 | 新建 humanlike 表达调制层，只读情绪、人格、记忆和资源状态 |
| HLA009 | 临床相邻内容只能做维度化、长期化、非诊断的筛查/路由 |
| HLA010 | 拟人程度越高，越需要可配置人设强度、依赖防护、重置后门和审计日志 |

## 使用原则

这个知识库只支持“模拟代理设计”，不支持以下断言：

- bot 有真实意识、真实痛苦、真实身体或真实疾病。
- bot 的“生病”状态可以替代医学概念。
- 用户需要对 bot 的痛苦、疾病、孤独或依赖承担现实责任。
- 文献 citation id 可以直接提高情绪置信度、扩大冷处理后果或绕过配置边界。

推荐把知识库用于三个位置：

1. 公式设计：为状态变量、半衰期、阈值和耦合项提供机制依据。
2. 公共 API：为其他插件解释 `humanlike_state` 的字段含义和限制。
3. 文档与测试：为“为什么要加这一层”和“这一层不能做什么”提供可追溯证据。

## 证据等级

当前知识库主要是 OpenAlex 元数据和摘要级检索结果，应按证据等级使用：

| 等级 | 含义 | 可用于 |
| --- | --- | --- |
| `abstract-only` | 只读到题名、摘要索引、DOI 元数据和主题召回 | 设计假设、候选文献池、弱证据说明 |
| `abstract-verified` | 人工核对摘要、来源、DOI 与主题相关性 | 文档中的一般理论依据 |
| `fulltext-reviewed` | 人工阅读全文并记录可用结论 | 公式权重、强断言、论文式论证 |

`design-rules.md` 当前默认属于 `abstract-only` 到 `abstract-verified` 之间的候选规则。后续每条 HLA 规则应绑定 3-5 篇核心文献，并显式标注证据等级。

## 纳入与排除标准

纳入优先级：

- 能转成状态变量、半衰期、阈值、关系记忆、表达调制或测试约束。
- 来自高影响期刊/会议、综述、meta-analysis、经典理论或长期交互研究。
- 能说明拟人化、依恋、依赖、医疗化或安全边界。

排除或降权：

- 只讨论营销式 AI companion，没有可验证学术来源。
- 只使用短期 demo，无法支撑长期记忆、关系或恢复模型。
- 临床结论无法迁移到模拟代理，或容易被误用为疾病诊断。
- 与 bot 机制无关，只是被关键词误召回。

## 与 10 轮迭代的关系

10 轮迭代记录见 [`docs/humanlike_agent_iteration_log.md`](humanlike_agent_iteration_log.md)。其中第 10 轮明确要求：文献库后续不能只保留“主题支持”，必须逐条建立“设计规则 -> 核心文献 -> 证据等级 -> 可实现字段 -> 风险限制”的映射。

## 复跑命令

```powershell
py -3.13 scripts\build_humanlike_agent_literature_kb.py --out humanlike_agent_literature_kb --per-query 150 --top-count 320 --mailto codex@example.com
```

脚本支持断点缓存。若网络中断，已完成的 `raw/*.jsonl` 会被复用；若缓存文件损坏，脚本会自动重新拉取对应主题。
