# Sylanne 三阶段自我调度迭代设计

日期：2026-05-17

## 目标

本轮不继续堆叠新的状态维度，而是把 Sylanne 已有的情绪、拟人状态、生命化学习、记忆、群聊氛围、表达策略、投递事实和理解闭环组织成更稳定的决策链。最终目标是让她在每轮回复前知道“本轮为什么要这样回应”，在长期相处中更自然，但不让旧记忆、关系推断或主动性压过当前用户原文。

## 合并实验版本顺序

### 2.8.0-exp 内部阶段一：自我仲裁层

优先复用 `integrated_self.py`，不新建一个庞大的平行“大脑”。仲裁层只读现有快照和理解闭环状态，输出短 `intent_plan`：

- 当前用户原文优先级。
- 本轮主要目标：回答、澄清、安静、修复、轻触达、工具式完成任务。
- 亲近/克制程度。
- 旧记忆和 shadow context 的可用边界。
- 表达策略建议：是否沿用 `expression_policy`，是否压低情绪化表达。
- 安全与边界约束。

`on_llm_request` 的接入点放在解释候选和 `choose_expression_policy(...)` 之后，早于大规模状态注入。这样能拿到 `current_user_text`、interpretation、session/epoch 和表达姿态，同时不改前置控制流。

第一版不写长期记忆，不改变公共 schema 主版本，只把仲裁计划作为短 prompt fragment 和 runtime diagnostics 暴露。

## 2.8.0-exp 内部阶段二：体验评估回放

体验回放基于 `conversation_event_ledger.py`、integrated self replay bundle 和 runtime diagnostics 做离线诊断。它只回答“刚才这段对话有没有问题”，不直接参与当前回复生成。

第一版输出：

- 是否疑似误解用户原文。
- 是否过度复用旧 shadow / memory。
- 是否该澄清却直接发挥。
- 是否过度主动或语气过重。
- 是否技术任务被情绪化表达干扰。

回放结果只进入 diagnostics/replay，不进主 prompt，不写长期 memory。后续如果要把回放结果转成改进信号，必须另设门控。

## 2.8.0-exp 内部阶段三：长期关系模型候选摘要

长期关系放在最后做，因为它最容易误写长期事实、污染多用户关系、或者让“关系感”覆盖当前边界。第一版只做只读候选摘要，不默认写 memory、不默认进 prompt。

关系候选摘要包括：

- 熟悉度、信任、边界舒适度、修复状态。
- 共同经历和共同语境的来源证据。
- 当前关系推断的置信度和过期风险。
- 多用户/群聊隔离信息。

只有当证据可追溯、用户明确表达、或已有稳定共同语境时，后续版本才考虑写入长期记忆。

## 关键边界

- 当前用户原文永远高于旧记忆、关系推断和体验回放。
- 技术任务默认压低文学化、撒娇化和过度情绪化表达。
- 低信号、高边界、用户纠正时，仲裁层必须偏向澄清或沉默。
- 体验回放不进入主回复热路径。
- 长期关系 2.0 第一版不写库。
- 不引入需要额外 LLM 调用的热路径功能，除非显式配置打开。

## 测试策略

2.8.0-exp 内部阶段一测试：

- `tests/test_integrated_self.py`：仲裁计划契约、优先级和边界。
- `tests/test_expression_policy.py`：表达策略与仲裁建议一致。
- `tests/astrbot_lifecycle_part15.py` 或相邻生命周期分片：prompt 注入顺序和不覆盖用户原文。
- `tests/test_command_tools.py`：runtime diagnostics 暴露仲裁结果。

2.8.0-exp 内部阶段二测试：

- `tests/test_conversation_event_ledger.py`：回放输入和事件 tail。
- `tests/test_integrated_self.py`：replay bundle 诊断输出。
- 生命周期测试：确认回放不注入主 prompt。

2.8.0-exp 内部阶段三测试：

- `tests/test_lifelike_learning_engine.py`：关系候选摘要与共同语境证据。
- `tests/test_memory_engine.py`：默认不写长期关系叙事。
- 群聊相关测试：多用户关系不互相污染。

## 发布切分

- `2.8.0-exp`：一次性合并发布只读自我仲裁层、离线体验评估回放诊断和只读长期关系候选摘要。
- 内部实现仍按三个阶段推进，方便测试和回滚；对外 metadata、README、CHANGELOG、发布包和远程烟测只使用同一个版本号。
- major 版本只留给革命性划世代更新；本轮属于功能迭代，所以推进 minor 到 `2.8.0` 并追加实验后缀 `-exp`。

这三个能力可以连续实现，但每一阶段都必须保持可独立验证、可回滚、测试通过。
