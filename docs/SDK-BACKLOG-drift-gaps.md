# SDK Backlog — agent 层修不动、需回推远端 SylannEngine 的缺口

> 背景:把"对话质量自我进化漂移"从 vendored 焊死的 `feedback_quality` 后门迁成 canonical 正道时,
> opus team 核查发现三处 agent 层无杠杆、必须在远端 SDK 修的缺口。本仓库遵守"SDK 不手改"——只记备忘。
> 生成:2026-06-14｜核查任务 wdjxyayf1(全 opus,5 agent)

---

## 缺口 1 — sustained_silence 经 canonical 通道永不触发(硬回归)

- **现象**:旧后门下 agent 主动喂 `sustained_silence` 能让 `expression_drive_trait` 缓降(−0.1);迁 canonical 后该漂移永久不发生。
- **根因**(两处叠加,都在 SDK):
  - `DriftSignalExtractor.extract` 只从 `result["route"]=="skip"` 连续≥3 次派生 sustained_silence(`personality.py:269-272`)
  - 但 `ResonanceSpine._build_result` 把 `route` 恒写死 `"resonance"`(`resonance_integration.py:838`),skip 只进内部 `_route_counts` 统计、从不进 result
  - 叠加:SILENT 轮空文本在 `process` 早返回(`resonance_integration.py:370-373`),连 `_drift_embodiment` 都不进
- **语义错配**:SDK 的 skip 指"空输入";agent 要的是"对一条真实(非空)消息装死不回",此时 route 仍是 resonance。
- **远端建议修法**:extractor 改从"窗口内连续 `should_express==False` ≥3"派生 sustained_silence;或让 SILENT/装死轮 result 写 `route="skip"` 且不在空文本处早返回漏掉漂移。
- **agent 不做的近似**:静默轮注入低 dialogue_quality 借 `dialogue_quality_low` 下推——混淆"低质量"与"沉默"、丢 3 连续门、量级 −0.15≠−0.1、漏 relational_gravity。**不做,记差异。**

## 缺口 2 — expression_fired 反映 spine 策略猜测,非 agent 真实开口(语义漂移)

- **现象**:迁 canonical 后 `expression_fired` ← `result["should_express"]`(`personality.py:241-245`),而 should_express 是 expression_policy 对【用户消息】的 contextual-bandit 决策(`resonance_integration.py:685-696`),发生在 LLM 出草稿/renderer 裁决之前。
- **断层**:agent 真实裁决 = `reply.kind is SPEAK`(renderer 看 draft 可用性+deliberate);spine 的 should_express 看场共振+policy。输入不同、时点不同、决策者不同。renderer 判 SILENT 而 request 拍 should_express=True 时产生假阳。
- **为何 agent 修不动**:`_embodiment_traits` 只被 `_drift_embodiment` 写(`resonance_integration.py:520`);`feedback()` 六家总线全不碰它(`:736-795`)。agent 真实裁决只能经 `feedback(actual_expressed)` 进 expression_policy 的 REINFORCE(调策略权重),**永不漂 `_embodiment_traits`**。
- **远端建议修法**:SDK 开 tick 通道让 agent 把真实裁决灌进 `result["should_express"]`(覆盖策略猜测);或新增一个"ground-truth 表达结果"漂移信号键,agent 经 event.values 喂真实 SPEAK/SILENT。
- **本期接受**:expression_fired 用 spine 自动派生(每轮 request 拍那次有效),视为已知近似。

## 缺口 3 — 漂移 30s 限频对反馈信号过钝 + 快聊哑火(红队 wjqkfgh4i 补充)

- **现象**:`_drift_min_interval=30.0`(`resonance_integration.py:203`),同一 turn 的 request+response 两拍间隔秒级 <30s → response 拍 `_drift_embodiment` 被 skip。旧后门直调 feedback_quality 不过限频、能 loop 累积。
- **快聊哑火后果(红队补)**:dialogue_quality 滞后注入下一轮 request 拍,但若下一轮距上轮 <30s(快聊高频),`consume_pending_quality` 已把质量分取出即清,而本轮 `_drift_embodiment` 因 dt<30 被 skip → **质量分被清掉了却零漂移,该轮质量反馈静默丢失**。生产快聊场景相邻轮多数 <30s,故 dialogue_quality 信道在高频对话中大部分哑火。
- **影响**:dialogue_quality 实际只在间隔 >30s 的轮次生效(慢聊/隔段时间回);快聊下基本不漂。agent 层无杠杆(限频在 SDK,且 consume 在 request tick 前、agent 不知道 drift 会否被 skip)。
- **远端建议**:对 dialogue_quality 这类显式反馈信号豁免限频,或调小 `_drift_min_interval`。**本期接受,不在本仓动。** agent 侧已做时效(_QUALITY_TTL_S=600s)防陈旧串话,但解不了快聊哑火(那是 SDK 限频)。

---

## 本期 agent 层能闭环的(已实现,见迁移)

- **dialogue_quality 数值滞后注入**:self_score 三维均值(float)→ `rt["pending_quality"]` → 下轮 request tick `event.values["dialogue_quality"]` → kernel.tick 透传 process → `_drift_embodiment` 自动漂移(高质量 expr+0.25 & relational_gravity+0.15;低质量 expr−0.15)。这是质量自我进化的真闭环。
- `feedback_quality` 死 no-op 清理;`shared()` await bug 修复。
