# 非诊断心理状态筛查模块

本模块是备用的心理状态筛查与长期趋势建模工具，不是心理诊断、医疗建议或治疗方案。它只处理对话文本中显性的状态线索，并把结果暴露给其他插件调用。

## 边界

- 可以：状态记录、趋势观察、量表启发式维度、风险提示、人工复核提醒。
- 不可以：疾病诊断、病因解释、治疗/用药建议、危机风险保证、替代临床判断。
- 红旗风险：自伤/自杀、伤害他人、严重功能受损、严重睡眠受扰、极端绝望、无法保持安全等信号只用于安全升级和人工复核。

## 状态维度

| 维度 | 含义 |
| --- | --- |
| `distress` | 总体痛苦 |
| `anxiety_tension` | 焦虑/紧张 |
| `depressive_tone` | 抑郁语气 |
| `stress_load` | 压力负荷 |
| `sleep_disruption` | 睡眠受扰 |
| `social_withdrawal` | 社交退缩 |
| `anger_irritability` | 愤怒/易激惹 |
| `self_harm_risk` | 自伤风险信号 |
| `function_impairment` | 功能受损 |
| `wellbeing` | 主观幸福感 |

## 量表启发

`scale_scores` 使用 PHQ-9-like、GAD-7-like、PSS-like、WHO-5-like、ISI-like 的启发式映射。这里的 `like` 很重要：插件没有施测原量表，也没有资格解释临床 cut-off，只能把它们作为结构化状态维度的参考。

## 公共 API 返回形态

- `enable_psychological_screening=false` 时，提交式 `observe_psychological_text(..., commit=True)` 会返回 `enabled=false` 的非诊断 payload，不会写入长期状态。
- `get_psychological_screening_snapshot(...)` 和 `get_psychological_screening_values(...)` 仍可读取已有状态，便于其他插件在模块关闭后做迁移、调试或只读展示。
- `simulate_psychological_update(...)` 永远不落库，即使模块关闭也可以用于候选文本预估。
- payload 固定包含 `diagnostic=false`、`safety.non_diagnostic_screening_only=true` 和 `safety.not_a_medical_device=true`。
- 出现自伤/自杀、伤害他人、严重功能受损或严重睡眠受扰等红旗信号时，`payload["risk"]["requires_human_review"]`（即 `risk.requires_human_review=true`）会置为 `true`；`PSYCHOLOGICAL_RISK_BOOLEAN_FIELDS` 列出稳定的机器可读风险布尔字段：`requires_human_review`、`crisis_like_signal`、`other_harm_signal`、`severe_function_impairment_signal`、`severe_function_impairment`、`severe_sleep_disruption`。插件可以用 `payload["risk"]["severe_function_impairment"]`（`risk.severe_function_impairment`）和 `payload["risk"]["severe_sleep_disruption"]`（`risk.severe_sleep_disruption`）做分支判断。插件应提示人工/专业支持或当地急救资源，而不是继续普通陪聊、输出疾病标签或承诺风险可控。

## 文献知识库

心理筛查证据库位于 `psychological_literature_kb/`：

- `works.jsonl`: 4401 篇 OpenAlex 去重记录。
- `top_journal_candidates.jsonl`: 260 篇 top/high-impact 候选。
- `curated/top_200.jsonl`: 精选 200 篇候选。
- `evidence-map.md`: 非诊断筛查、临床量表、长期状态、数字心理健康、LLM/聊天机器人安全的证据地图。
- `validation-report.md`: 数量和边界验证报告。

重建命令：

```powershell
py -3.13 scripts\build_psychological_literature_kb.py --out psychological_literature_kb --per-query 150 --top-count 260
```

知识库只基于题名、摘要级元数据、DOI 元数据、期刊和检索主题生成。强临床断言必须继续阅读全文或权威指南后才能使用。
