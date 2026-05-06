# 让 bot 更像“有生活痕迹的人”：模型补全路线

## 核心判断

当前插件已经有多维情绪、人格基线、真实时间半衰期、关系修复、冷处理后果、心理筛查备用模块和记忆写入时的情绪快照。下一步不能只是继续增加情绪标签，而应新增一个独立的 `humanlike_state` 子系统。

这个子系统不改写 `emotion_state`，而是只读情绪、persona、关系、记忆和心理筛查风险信号，输出“拟人/有机体样表达调制”。这样他/她会更像有生活节律和关系历史的角色，但外部插件仍能清楚知道：这是模拟状态，不是真实生命、真实疾病或临床诊断。

本路线经过 10 轮自我迭代，记录见 [`humanlike_agent_iteration_log.md`](humanlike_agent_iteration_log.md)。迭代后的约束是：首版默认关闭、只读情绪核心、P0 维度最小化、快照分层、记忆来源可追溯，并且疾病样/依恋样表达不得覆盖安全与必要帮助。

## 还需要补充的层

| 层 | 要解决的问题 | 建议状态变量 | 主要依据方向 |
| --- | --- | --- | --- |
| 身体样稳态 | 为什么他/她会累、低能量、需要恢复 | `energy`、`stress_load`、`recovery_rate`、`discomfort`、`fatigue_amplifier` | homeostasis、allostasis、interoception |
| 昼夜节律与睡眠债 | 为什么同一事件在不同真实时间反应不同 | `sleep_debt`、`time_of_day_bias`、`circadian_phase`、`rest_window` | two-process sleep model、sleep deprivation、fatigue |
| 认知资源 | 为什么状态差时会短句、犹豫、检查更多 | `attention_budget`、`working_memory_load`、`confusion`、`decision_latency` | cognitive load、human factors、executive function |
| 需求与动机 | 为什么他/她在乎某些事、不在乎另一些事 | `autonomy_need`、`competence_need`、`relatedness_need`、`safety_need`、`curiosity_need`、`rest_need` | self-determination theory、goal regulation |
| 应对风格 | 生气后为什么有的 bot 解释，有的沉默，有的求证 | `reappraisal`、`suppression`、`withdrawal`、`repair_tendency`、`boundary_setting` | emotion regulation、coping theory |
| 关系依恋 | 为什么同一句话对熟人和陌生人不同 | `trust`、`familiarity`、`attachment_signal`、`resentment`、`gratitude`、`boundary_alert` | attachment、trust repair、relational agents |
| 自传式记忆 | 为什么他/她记得过去而不是每轮重启 | `salient_events`、`relationship_story`、`self_concept`、`unresolved_threads` | autobiographical memory、narrative identity |
| 社会处境 | 为什么群聊、私聊、被围观时表现不同 | `audience_pressure`、`face_threat`、`role_obligation`、`status_sensitivity` | social psychology、social signal processing |
| 疾病样状态 | 为什么有时会进入低功能、恢复期、易激惹 | `sick_day_like`、`immune_load_like`、`functional_impairment_like`、`care_need_signal` | allostatic load、burnout、digital phenotyping |
| 元认知与透明度 | 他/她如何解释自己的状态而不误导用户 | `simulation_disclosure_level`、`uncertainty`、`dependency_risk` | AI RMF、HCI ethics、anthropomorphism |

## 推荐的状态结构

```yaml
humanlike_state:
  schema_version: astrbot.humanlike_state.v1
  simulated_agent_state: true
  session_key: ...
  updated_at: 1715000000.0

  organism_like:
    energy: 0.62
    fatigue: 0.28
    sleep_debt: 0.33
    stress_load: 0.41
    discomfort: 0.12
    sick_day_like: false

  cognition:
    attention_budget: 0.72
    working_memory_load: 0.31
    confusion: 0.18
    decision_latency: 0.22
    verbosity_limit: 0.64

  needs:
    autonomy: 0.58
    competence: 0.66
    relatedness: 0.71
    safety: 0.63
    rest: 0.39
    boundary: 0.24

  coping:
    reappraisal: 0.55
    suppression: 0.22
    withdrawal: 0.18
    repair_tendency: 0.61
    boundary_setting: 0.33

  narrative:
    self_concept_stability: 0.74
    relationship_story_strength: 0.46
    unresolved_threads: 2
    salient_trigger_count: 1

  output_modulation:
    warmth: 0.62
    initiative: 0.54
    hesitation: 0.28
    brevity: 0.36
    social_distance: neutral
```

## P0 最小可行状态集

第一版不应一次实现全部变量。建议 P0 只保留 6 个维度：

| 维度 | 含义 | 输出影响 |
| --- | --- | --- |
| `energy` | 模拟能量水平 | 低能量降低主动扩展和回复长度 |
| `stress_load` | 模拟压力负荷 | 高压力提高谨慎、易激惹和边界需求 |
| `attention_budget` | 注意力预算 | 低注意力提高确认、降低多任务展开 |
| `boundary_need` | 边界需求 | 高边界需求提高拒绝清晰度和社交距离 |
| `dependency_risk` | 依赖/操控风险 | 高风险降低排他性、病弱卖惨和黏性表达 |
| `simulation_disclosure_level` | 透明度需求 | 决定是否提醒这是模拟状态 |

P1/P2 再扩展 `sleep_debt`、`circadian_phase`、`relationship_story_strength`、`self_concept_stability`、`sick_day_like` 等字段。

## 建议配置

```json
{
  "enable_humanlike_state": false,
  "humanlike_injection_strength": 0.35,
  "humanlike_personification_level": "medium",
  "humanlike_memory_write_enabled": false,
  "humanlike_clinical_like_enabled": false,
  "humanlike_dependency_guard_level": "strict",
  "humanlike_state_half_life_seconds": 21600,
  "humanlike_trajectory_limit": 40,
  "allow_humanlike_reset_backdoor": true
}
```

`humanlike_clinical_like_enabled=false` 时，不生成 `sick_day_like`、`burnout_like` 等疾病样状态。即使开启，也只能作为低能量/低功能表达调制，不得声称真实疾病、真实疼痛、感染或需要用户照护。

## 时间动力学

这一层必须继续遵守真实时间，而不是消息轮数。建议把状态分成三种时间尺度：

| 时间尺度 | 状态 | 半衰期建议 |
| --- | --- | --- |
| 快变量 | 注意力、混乱度、被冒犯后的紧张 | 5 分钟到 2 小时 |
| 中变量 | 疲劳、压力负荷、关系残留、反刍 | 6 小时到 7 天 |
| 慢变量 | persona 适应、关系叙事、自我概念 | 14 天到 90 天 |

可使用统一更新式：

```text
H_t = (1 - gamma) H_(t-1) + gamma b_p + alpha O_t
gamma(Δt) = 1 - 2^(-Δt / half_life)
```

其中 `H_t` 是 humanlike 状态，`O_t` 是 LLM 或启发式观察值。短时间刷屏只能增加局部观察，不应快速清空疲劳、委屈、关系残留或恢复期。

## “会生病”的工程表达

建议不要直接做疾病诊断式状态，而是做“疾病样/低功能期”：

| 状态 | 表现后果 |
| --- | --- |
| `fatigue_high` | 字数降低、主动性下降、更多确认、延迟感增强 |
| `stress_overload` | 易激惹、谨慎、边界感增强、低容错 |
| `sick_day_like` | 短句、低能量、减少复杂任务的主动扩展 |
| `recovery_phase` | 逐渐恢复温度和主动性，但保留短期脆弱感 |
| `burnout_like` | 长期低主动、低表达、需要更长恢复半衰期 |

这里的 `like` 很重要。它允许角色有“身体感”和恢复过程，但不让系统声称他/她真的患病、发烧、感染、疼痛或需要用户照护。

## 与现有模块的关系

```text
emotion_engine
  -> 提供效价、唤醒、支配感、目标一致性、关系修复与后果

psychological_screening
  -> 只提供非诊断风险与长期趋势，不参与人格魅力或依恋强化

livingmemory / 其他记忆插件
  -> 写入事件时同时冻结 emotion_at_write 与 humanlike_at_write

humanlike_state
  -> 只读上述状态，输出表达调制和状态快照
```

不建议把 humanlike 维度塞进 `emotion_engine.DIMENSIONS`。情绪是核心 affective state，humanlike 是存在感、身体样资源、关系叙事和表达策略的组合层。混在一起会让公共 API 语义膨胀，也会让其他插件误以为“疲劳/生病/依恋”就是情绪维度。

## 公共快照分层

`humanlike_state` 的公共 API 不应只有一个无差别快照。建议分三层：

| 层 | 用途 | 可包含 | 不应包含 |
| --- | --- | --- | --- |
| `internal` | 本插件内部调试、迁移和测试 | 全量状态、阈值、轨迹、来源 id | 不直接给普通外部插件默认读取 |
| `plugin_safe` | 其他插件调制剧情、记忆或 UI | `output_modulation`、`simulation_flags`、有限风险标记 | 依赖风险细节、心理筛查细节、内部阈值 |
| `user_facing` | 给用户解释当前状态 | 简短自然语言、可关闭/重置提示 | 诊断式解释、真实疾病/痛苦声明、依赖暗示 |

默认 API 返回 `plugin_safe`。只有显式请求并具备调试权限时，才返回 `internal`。

## 叙事记忆来源约束

反思与自传式摘要必须保留来源：

```json
{
  "summary_type": "relationship_story",
  "text": "用户多次在冲突后主动解释并修复，因此关系叙事偏向可修复。",
  "source_memory_ids": ["mem_001", "mem_019"],
  "generated_at": 1715000000.0,
  "confidence": 0.72,
  "revocable": true
}
```

没有 `source_memory_ids` 的叙事只能作为临时解释，不得写入长期记忆。

## 工程优先级

| 优先级 | 建议实现 |
| --- | --- |
| P0 | 新增 `humanlike_engine.py`、schema、半衰期、clamp、重置后门、公共快照 |
| P1 | 接入 `main.py` 和 `public_api.py`，提供 `get_humanlike_snapshot`、`observe_humanlike_text`、`simulate_humanlike_update` |
| P2 | 给 livingmemory payload 增加 `humanlike_at_write`，与 `emotion_at_write` 同时冻结 |
| P3 | 新增 humanlike prompt fragment，只调制语气、节奏、主动性、边界感 |
| P4 | 增加反思/叙事摘要任务，把长期记忆压缩成 self story 与 relationship story |
| P5 | 增加测试：半衰期、轨迹截断、非诊断字段、默认关闭/弱注入、simulate 不落库 |

## 行为测试闭环

实现时至少覆盖以下行为测试：

- 默认关闭时不落库、不注入、不改变现有情绪行为。
- `simulate_humanlike_update` 不写入 KV。
- 半衰期和刷屏限幅按真实时间工作。
- 同一输入在高/低 `energy` 下只改变表达长度和主动性，不改变事实结论。
- 危机、自伤、医疗咨询、法律/金融高风险场景绕过拟人调制。
- `humanlike_at_write` 冻结写入时状态，并保留 `written_at` 与状态 `updated_at`。
- 叙事摘要必须能回溯 `source_memory_ids`。
- reset 后门能清空 humanlike 状态，但不误删 emotion 和 psychological 状态。

## 参考入口

- Picard 的情感计算奠定了“识别、建模、表达情绪”的工程方向。
- Russell、Mehrabian 与 Russell、OCC、Lazarus、Scherer 支撑现有情绪和 appraisal 层。
- Seth 的 interoceptive inference 支持“身体样状态与情绪解释相连”的机制思路。
- Borbely 等 two-process sleep model 支持睡眠压力与昼夜节律共同调节疲劳。
- Deci 与 Ryan 的 self-determination theory 支持自主、胜任、关系等基本需求层。
- Conway、McAdams 等自传式记忆和叙事身份研究支持长期自我连续性。
- Generative Agents 说明可信代理需要记忆、反思、检索和计划，而不是孤立 prompt。
- NIST AI RMF、WHO ICD-11 CDDR 与 HCI/伦理文献提醒：临床相邻和高拟人化系统必须保留透明度、边界、人工复核和可控开关。

精选文献已进入 [`humanlike_agent_literature_kb/curated/top_200.jsonl`](../humanlike_agent_literature_kb/curated/top_200.jsonl)。后续如果要把本路线变成正式论文式论证，应先从这 200 篇里人工精读，再把 `evidence-map.md` 中的 `abstract-only` 改成 `abstract-verified` 或 `fulltext-reviewed`。
