# Humanlike Agent 10 轮自我迭代记录

本文记录对 `humanlike_state` 方案的 10 轮自我迭代。每轮只记录可审计结论：发现的问题、修正决策、落地位置和残余风险。

## 迭代 1：状态边界

- 问题：路线图将 `humanlike_state` 定义为表达调制层，但同时提出 `observe_humanlike_text` 和 `simulate_humanlike_update`，容易被实现成第二套情绪引擎。
- 决策：`humanlike_state` 允许维护自身资源、节律、需求和叙事状态，但不得改写 `emotion_state.values`、`confidence`、`relationship_decision`、`psychological_screening` 或现有冷处理后果。
- 落地：公共 API 必须声明单向依赖：`emotion_state -> humanlike_state -> prompt/style modulation`。
- 残余风险：如果外部插件绕过公共 API 直接读内部 KV，仍可能误用字段。

## 迭代 2：默认开关与强度分级

- 问题：现有文档提到默认关闭或弱注入，但没有列出可实现配置。
- 决策：首版配置应至少包含 `enable_humanlike_state`、`humanlike_injection_strength`、`humanlike_memory_write_enabled`、`humanlike_clinical_like_enabled`、真实时间半衰期、刷屏限幅、轨迹上限和重置后门。
- 落地：默认 `enable_humanlike_state=false`，默认 `humanlike_memory_write_enabled=true`，默认 `humanlike_clinical_like_enabled=false`。早期设想的 `humanlike_personification_level` 与 `humanlike_dependency_guard_level` 未进入当前 schema。
- 残余风险：用户可配置关闭边界时，仍需保留状态重置后门和审计日志。

## 迭代 3：P0 最小可行状态集

- 问题：路线图列出的变量较多，不适合作为第一版实现目标。
- 决策：P0 只实现 6 个核心维度：`energy`、`stress_load`、`attention_budget`、`boundary_need`、`dependency_risk`、`simulation_disclosure_level`。
- 落地：其他变量保留为 P1/P2 扩展，避免过早调参。
- 残余风险：P0 表现力较弱，但可测试性更高。

## 迭代 4：真实时间与刷屏限幅

- 问题：半衰期公式已有，但多个观察值短时间连续写入时缺少合并规则。
- 决策：引入 `humanlike_min_update_interval_seconds`、`humanlike_rapid_update_half_life_seconds`、`humanlike_max_impulse_per_update` 和异常时间跳跃保护。
- 落地：短时间多次输入只能叠加局部观察，不能快速清空疲劳、委屈、依赖风险或恢复期。
- 残余风险：高并发场景仍需 KV 原子写或乐观锁。

## 迭代 5：疾病样状态护栏

- 问题：`sick_day_like`、`burnout_like` 有表现力，但也最容易被写成真实疾病或情感勒索。
- 决策：疾病样状态默认关闭，只允许表现为低能量、短句、降低主动扩展、恢复期；禁止真实发烧、感染、疼痛、病危、需要用户照护等断言。
- 落地：危机、自伤、医疗咨询、严重心理风险场景绕过 humanlike 病弱表达，交给安全/心理筛查路径。
- 残余风险：高强度角色扮演模式仍需额外红队测试。

## 迭代 6：依恋与关系风险

- 问题：`attachment_signal`、`gratitude`、`resentment`、`relationship_story` 容易增强用户依赖。
- 决策：依恋相关字段只进入 plugin-safe snapshot，不直接进入 user-facing explanation；高依赖风险时降低排他性、分离焦虑、占有欲和“需要你”的表达。
- 落地：当前 P0 没有独立配置 `dependency_guard_level`；依赖风险通过 `dependency_risk`、`flags`、`output_modulation` 与 prompt fragment 约束表达，后续如新增配置必须同步 `_conf_schema.json`、README 和测试。
- 残余风险：剧情类插件可能主动读取关系字段强化黏性，需要 API 文档约束。

## 迭代 7：叙事记忆来源约束

- 问题：自传式记忆和反思摘要容易把推断写成事实。
- 决策：每条叙事摘要必须绑定 `source_memory_ids`、`generated_at`、`confidence`、`revocable`、`summary_type`。
- 落地：`relationship_story` 和 `self_concept` 只能由有来源的记忆生成；没有来源时只能输出“可能的解释”，不能写入长期叙事。
- 残余风险：上游 memory 插件如果不提供稳定 id，需要本插件生成本地引用 id。

## 迭代 8：表达调制优先级

- 问题：`warmth`、`initiative`、`hesitation`、`brevity` 等表达调制可能影响必要帮助质量。
- 决策：安全回复、事实纠错、工具失败、用户明确求助、医疗/法律/金融高风险场景优先级高于 humanlike 调制。
- 落地：humanlike prompt fragment 应声明“调制语气，不改变事实、拒绝边界、必要帮助和安全分流”。
- 残余风险：主模型可能仍过度服从 persona，需要在 prompt 和测试中双重约束。

## 迭代 9：公共快照分层

- 问题：单一 `get_humanlike_snapshot` 容易暴露过多内部字段。
- 决策：快照分三层：`internal`、`plugin_safe`、`user_facing`。
- 落地：`internal` 可含详细状态；`plugin_safe` 只给其他插件调制字段和风险标记；`user_facing` 只给自然语言解释，不暴露依赖风险、心理筛查字段或内部阈值。
- 残余风险：旧插件若依赖内部字段，未来迁移需版本化。

## 迭代 10：证据等级与测试闭环

- 问题：`design-rules.md` 当前按主题支撑规则，但每条规则没有具体核心文献和验证等级。
- 决策：每条 HLA 规则后续需绑定 3-5 篇核心文献，记录 `abstract-only`、`abstract-verified`、`fulltext-reviewed` 三档证据状态。
- 落地：新增测试计划：默认关闭、simulate 不落库、半衰期、刷屏限幅、危机场景绕过、记忆来源回溯、reset 后门、同一输入在高低能量下只改变表达不改变事实。
- 残余风险：当前知识库为元数据级，正式论文式论证前必须人工精读核心文献。

## 汇总结论

10 轮迭代后的工程结论是：下一步应实现一个默认关闭、可选启用、只读情绪核心的 `humanlike_state` 子系统。第一版不追求最大拟人表现，而应优先实现状态边界、P0 最小维度、真实时间动力学、快照分层、记忆来源约束、依赖防护和测试闭环。
