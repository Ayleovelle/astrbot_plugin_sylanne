# Sylanne 3.0.0-exp1 第一阶段实施计划：Self-Interpretation Engine

> 目标：不要先做 WebUI，也不要把 3.0 退化成长期记忆 2.0。第一阶段只实现一个最小但真正 3.0 的闭环：关键经历能够生成 Sylanne 对“我、你、我们”的自我诠释，并让这条诠释通过 diagnostics 与轻量后续倾向影响下一轮。

## 0. 核心验收

第一阶段必须证明：

```text
关键经历 -> 自我诠释 -> 转折点候选 -> 后续倾向 -> diagnostics/API 可见
```

不以字段数量、记忆条数、WebUI 面板数量作为验收。

## 1. 版本与范围

- 目标版本：`3.0.0-exp1`，暂不升正式 `3.0.0`。
- 3.0 实验版本按阶段编号推进：`3.0.0-exp1`、`3.0.0-exp2`、`3.0.0-exp3`、`3.0.0-exp4`、`3.0.0-exp5`；每个 `-expN` 对应一个清晰研究阶段，不再用笼统的 `3.0.0-exp` 覆盖所有实验阶段。
- 第一阶段名称：Self-Interpretation Engine + Turning Point Candidate。
- 不做：WebUI、长期关系数据库、全量关系史持久化、大规模 embedding 检索、人格分叉运行器、自动长期人格改写。
- 做：只读自我诠释、转折点候选、受限 prompt 影响、runtime diagnostics 暴露、测试闭环。

## 1.1 3.0 阶段路线

完整 3.0 迭代路线固定为：

1. `3.0.0-exp1`：Self-Interpretation Engine / 自我诠释引擎，证明关键经历 -> 自我诠释 -> 转折点候选 -> 后续倾向的最小闭环。
2. `3.0.0-exp2`：Relational Time Layer / 关系时间层，追踪 active threads、relationship weather、shared references、互动节律与沉默/修复轨迹。
3. `3.0.0-exp3`：Co-Evolution Model / 共演化模型，观察用户与 Sylanne 如何互相塑造表达方式、协作习惯和关系气候。
4. `3.0.0-exp4`：Turning Point Memory + Replay / 转折点记忆与回放，将真正改变 Sylanne 的关键时刻变成可回放、可比较、可验证的研究对象。
5. `3.0.0-exp5`：Lineage / Branching / WebUI 观察舱，让同一初始 Sylanne 在不同关系历史中自然分叉，并用 WebUI 作为观察舱呈现关系时间线、自我诠释变化、转折点和分叉谱系。
6. `3.0.0`：稳定收尾版；当 exp1-exp5 的闭环、测试、文案和法律/API 边界稳定后，摘掉 `-expN`。

每完成一个阶段，应提交阶段成果、推送到 GitHub、打包并发布对应 GitHub release，然后继续下一阶段迭代；推送和 release 发布默认执行，不需要再次确认。历史重写、强推、删除远端资源、发布到意外仓库/分支、或可能泄露秘密/敏感数据的操作仍需单独确认。

## 2. 新增 schema

在 [integrated_self.py](../../integrated_self.py) 中新增公共 schema 常量：

```python
PUBLIC_SELF_INTERPRETATION_SCHEMA_VERSION = "astrbot.self_interpretation.v1"
PUBLIC_RELATIONAL_TURNING_POINT_SCHEMA_VERSION = "astrbot.relational_turning_point.v1"
```

新增 `self_interpretation` 结构：

```python
{
    "schema_version": PUBLIC_SELF_INTERPRETATION_SCHEMA_VERSION,
    "kind": "self_interpretation",
    "read_only": True,
    "prompt_eligible": False,
    "event_meaning": "...",
    "relational_meaning": "...",
    "self_narrative_shift": "...",
    "future_tendency": "...",
    "confidence": 0.0,
    "evidence": [...],
    "turning_point_candidate": {...} | {},
}
```

新增 `relational_turning_point` 结构：

```python
{
    "schema_version": PUBLIC_RELATIONAL_TURNING_POINT_SCHEMA_VERSION,
    "kind": "relational_turning_point",
    "read_only": True,
    "type": "correction | preference | repair | shared_reference | collaboration | reliance | silence | none",
    "why_it_matters": "...",
    "expected_long_tail": "...",
    "replayable": True,
    "confidence": 0.0,
    "evidence": [...],
}
```

注意：第一阶段只输出候选，不默认写入长期记忆。

## 3. 核心函数

在 [integrated_self.py](../../integrated_self.py) 新增：

```python
def build_self_interpretation(
    *,
    current_user_text: str,
    assistant_text: str = "",
    intent_plan: dict[str, Any] | None = None,
    expression_policy: dict[str, Any] | None = None,
    experience_review: dict[str, Any] | None = None,
    relationship_candidate_summary: dict[str, Any] | None = None,
    ledger_tail: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ...
```

实现原则：

- 不增加热路径 LLM 调用。
- 先用规则 + 已有 evidence 生成解释。
- 只使用短摘录，不保存大段原文。
- 结果必须包含 evidence。
- 默认 `prompt_eligible=False`。
- 只有高置信转折点才允许在后续短 prompt 片段中出现。

## 4. 转折点识别规则

第一阶段只识别少数高价值关系事件：

| 类型 | 触发线索 | 关系性解释方向 |
| --- | --- | --- |
| correction | “不对”“不是”“以后不要”“应该”“记住” | 用户在塑造协作规范，Sylanne 重新理解协作信任来源。 |
| preference | “我希望”“以后”“默认”“更喜欢” | 用户给出长期互动偏好，Sylanne 形成关系性习惯。 |
| repair | “没事”“原谅”“刚才误会”“修复” | 关系张力被重新解释，影响未来澄清与靠近方式。 |
| shared_reference | 反复出现的内部玩笑、共同称呼、共同典故 | 互动历史开始形成只属于此关系的符号。 |
| collaboration | “提交”“测试”“发布”“计划”“修 bug”且有成功/失败反馈 | 技术协作成为关系时间的一部分。 |
| reliance | “陪我”“你还在吗”“别走”“靠你了” | 关系中出现依赖/陪伴信号。 |
| silence | 长时间停顿后延续、用户强调留白/不用回复 | 沉默被解释为关系节律，而非单纯低互动。 |

必须保留 `none`：普通闲聊、低置信输入、无 evidence 的推断不生成转折点。

## 5. 接入 integrated self snapshot

扩展 `build_integrated_self_snapshot(...)`：

- 接收可选 `assistant_text`、`ledger_tail`、`relationship_candidate_summary`。
- 构建 `self_interpretation`。
- 将 `payload["self_interpretation"]` 写入 snapshot。
- `build_integrated_self_diagnostics(...)` 暴露该字段。

注意：不要把完整 raw text 放进 diagnostics，只放短 evidence excerpt。

## 6. 接入 main.py 理解闭环

在 [main.py](../../main.py) 中：

1. `on_llm_request(...)`
   - 继续写入 `current_user_text`、`expression_policy`、`intent_plan`、`relationship_candidate_summary`。
   - 不在 request 阶段强行生成最终 self_interpretation，因为 assistant_text 尚未存在。
   - 可生成 request-side preliminary interpretation，但第一阶段优先保持简单。

2. `on_llm_response(...)`
   - `_record_experience_review(...)` 之后，调用 `build_self_interpretation(...)`。
   - 将结果写入 `_understanding_closed_loop_state()[session_key]["self_interpretation"]`。

3. `_understanding_closed_loop_diagnostics(...)`
   - 增加默认字段：`self_interpretation`。

4. prompt 影响
   - 第一阶段只在下一轮 request 时，如果上一轮 `self_interpretation.turning_point_candidate.confidence >= 0.7`，追加极短片段：

```text
[sylanne_relational_self]
recent_interpretation=...; future_tendency=...
```

必须保证：

- 不覆盖当前用户原文。
- 不把旧解释当事实。
- 不写长期记忆。
- 不超过短文本预算。

## 7. 法律审查、内部运转与 API 封闭策略

第一阶段默认 **不新增对外 Public API**，也不允许其他插件开发者调取这些数据。所有 `self_interpretation` 与 `relational_turning_point` 结果只能作为 Sylanne 插件内部运转状态使用；即使进入 diagnostics，也必须限定为本插件内部调试/维护视图，不作为稳定对外接口承诺。

硬边界：

- 这些数据只能服务 Sylanne 内部状态机、prompt 调制和本地研究诊断。
- 不向第三方插件、外部开发者、公共 API、LLM tool schema、远程服务或跨插件调用入口暴露。
- 不把字段加入 `public_api.py` 的稳定 API 契约。
- 不在 README 中宣传这些字段可被其他开发者调用。
- 不提供根据用户、群聊、关系状态批量查询这些推断的接口。
- 不提供 webhook、export、dump、download、list-all 形式的外部导出能力。

法律审查原则：

- 不对外暴露可能被解读为心理诊断、关系操控、依恋判断、人格判定、亲密关系评估或用户脆弱性画像的稳定 API。
- 不对外暴露完整 raw conversation、长文本证据、私人关系叙事、用户画像推断或可跨会话拼接的敏感关系轨迹。
- 不把 `self_interpretation`、`turning_point_candidate`、`reliance`、`repair`、`silence` 等字段包装成可供第三方自动决策的公共能力。
- 不承诺这些字段代表真实心理状态、真实依恋、真实理解或真实主体性。
- 对外 release 文案只描述“本地模拟研究内部状态”“插件内部只读诊断”“可观测关系性自我模型”，不宣传可判断用户心理或操控关系。

第一阶段允许的可见性：

- Sylanne 内部 runtime state：允许。
- 本地维护用 runtime diagnostics：允许，但必须脱敏、短摘录、非稳定 API。
- public API / 第三方开发者 API：不允许。
- 外部工具调用 schema：不允许。
- release zip 内可直接调用的公开函数：不允许。

如果后续确实需要开放任何相关接口，必须先做独立法律/合规/API 审查，并满足：

1. 字段脱敏，只保留短 evidence excerpt 或枚举型摘要。
2. 默认关闭，且不能面向第三方插件开发者作为稳定能力。
3. 文档明确 `diagnostic=false`、`research_simulation_only=true`、`not_psychological_assessment=true`。
4. 测试覆盖不泄漏 raw text、不跨 speaker/group 混淆、不把候选推断写作事实。
5. release note 明确该能力不是用户画像 API，也不是心理/关系评估 API。

结论：第一阶段计划中“diagnostics 可见”仅指 Sylanne 内部本地维护视图可见，不等于新增公开 Public API，也不允许其他开发者调取。

## 8. 测试计划

### 8.1 integrated_self 单元测试

新增到 [tests/test_integrated_self.py](../../tests/test_integrated_self.py)：

1. `test_self_interpretation_detects_correction_turning_point`
   - 输入“不是这样，以后提交说明要中文详细一些”。
   - 期望 type=`correction` 或 `preference`，包含 self_narrative_shift。

2. `test_self_interpretation_detects_collaboration_turning_point`
   - 输入发布/测试/提交反馈。
   - 期望 relational_meaning 表达“技术协作是关系时间的一部分”。

3. `test_self_interpretation_ignores_low_signal_smalltalk`
   - 输入普通闲聊。
   - 期望 type=`none` 或空 candidate，prompt_eligible=False。

4. `test_self_interpretation_evidence_is_bounded`
   - 长文本输入。
   - 期望 evidence excerpt 被截断，不泄漏大段原文。

### 8.2 lifecycle hook 测试

新增到 [tests/astrbot_lifecycle_part15.py](../../tests/astrbot_lifecycle_part15.py)：

1. 响应后记录 `self_interpretation`。
2. 下一轮 request 在高置信转折点后注入 `[sylanne_relational_self]`。
3. 原始 `request.prompt` 不被覆盖。

### 8.3 runtime diagnostics 测试

扩展 [tests/test_command_tools.py](../../tests/test_command_tools.py)：

- `understanding_closed_loop` 暴露 `self_interpretation`。
- 默认值稳定为空 dict。
- 不包含长 raw text。

### 8.4 public API 回归

扩展 [tests/public_api_memory_part01.py](../../tests/public_api_memory_part01.py) 或相关 integrated self public API 测试：

- integrated self diagnostics schema 向后兼容。
- 新字段存在但不破坏旧字段。

## 9. 防止退化成长期记忆 2.0

第一阶段必须遵守：

- 不把所有事件写入长期存储。
- 不做“有用就记”。
- 不保存完整对话原文。
- 不做大规模召回。
- 不把 self_interpretation 直接提升为事实。
- 不把 turning point candidate 默认写进 memory_engine。

写入对象不是“内容”，而是“自我解释变化”。

## 10. 验证命令

至少运行：

```bash
python -m pytest tests/test_integrated_self.py
python -m pytest tests/astrbot_lifecycle_part15.py -k relational_self
python -m pytest tests/test_command_tools.py -k runtime_diagnostics
python -m pytest tests/public_api_memory_part01.py -k integrated_self
python -m pytest
```

## 11. 完成标准

第一阶段完成时应能回答：

1. 这轮发生了什么？
2. Sylanne 如何解释这件事对“我们”的意义？
3. 它是否是转折点？
4. 它将怎样轻微影响后续互动？
5. 这些判断的 evidence 是什么？
6. 为什么这不是简单长期记忆？
