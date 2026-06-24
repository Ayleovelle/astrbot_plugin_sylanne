# Sylanne 生活模拟升级 Phase 2C Handoff（草案 v0 · 待 review）

日期：2026-06-22
范围：**M8 反馈单一数据源（含前置数据源补建）+ rel_register 真机阈值标定 + is_romantic 消费方接入（召回/主动/人设）+ 可选后续项**
前置：`phase-2-kickoff.md`、`phase-2a-implementation-ruling.md`、`phase-2b-handoff.md`（PR-G/H/I 已实现并 commit `19c1f63`）
基线：`feat/life-sim-phase-2b`
状态：**草案 v0。本文件不含实现，只列问题陈述/状态出口/消费路径/测试矩阵/preflight。须过 review 方可实现。**

> 本草案由 2B 收尾时的代码现场勘查产出，核心目的是把 2B handoff 第 51/210 行
> "本批不做/待标定" 的遗留项，连同勘查中发现的一个真问题（M8 数据源缺失），
> 整理成可独立 review 的下一阶段输入。**未经 review 不得实现任何一项。**

---

## 0. 为什么需要本阶段（2B 收尾勘查结论）

2B（PR-G/H/I）把"亲密会话路由"的**判定 + 路由 + 持久化**做完了，但留下三类未收口工作：

1. **M8 未真正落实**——2A 把 `unanswered_penalty` 中性化为 guardrail（`* 0.0`），注释明写"真实接 scheduler.feedback_pressure 留到 2B"。2B 做了 origin_session（前置之一），但 **M8 本身没做，且勘查发现它缺一个根本前置**（见 §1）。
2. **rel_register 阈值仅有解析依据、缺真机实测**——2B 收尾已把 `0.6/5/6` 从"拍脑袋"升级为"解析推导保守值"（见 rel_register.py / relationship_layer.py 标定注释），但 handoff §7 要求的"实测友好语料误判占比 p 后微调"仍未做（需真机批量 LLM）。
3. **is_romantic 只有 1 个消费方**——2B 只接了 life-sim 路由（PR-I）。handoff §3.2 留了"召回/主动/人设可调同一 API"，且附带一条**硬红线**（自证循环），未接。

---

## 1. M8：发现的真问题——"单一数据源"的源是干涸的（核心）

### 1.1 问题陈述

M8（kickoff §43）要求：ShareIntent 的 `unanswered_penalty` 不另起计数，只复用 scheduler 已有的 `feedback_pressure` 单一来源，避免双重惩罚。

2A guardrail 现状（已勘查，行号基于当前 `feat/life-sim-phase-2b`）：
- `life_simulation.py:1113`：`+ w["unanswered_penalty"] * 0.0` —— ShareIntent 侧惩罚被中性化。
- `life_simulation.py:1109-1112` 注释：scheduler gate 独占 unanswered 惩罚，真实接 `feedback_pressure` 留到 2B。
- `proactive_scheduler.py:82-92`：`feedback_pressure` 由 `_proactive_dispatch_audit[session_key]` 里 `feedback_status ∈ {cold_reply, unanswered}` 的计数派生。

**勘查发现（关键）**：`_proactive_dispatch_audit`
- 在 `proactive_scheduler.py:83` **只被读**（`getattr(self._p, "_proactive_dispatch_audit", None) or {}`）。
- 全仓库（`sylanne_alpha/*.py` + `main.py`）**没有任何写入点，main.py 也未初始化它**。
- 结论：`feedback_pressure` **当前恒为 0**。M8 期望复用的"单一数据源"实际上没有生产者。

### 1.2 推论：M8 不是接线，是补建数据源 + 再接线

落实 M8 必须先回答一组**新设计决策**（这正是不能盲做、需 review 的原因）：

1. **unanswered 的判定**：一次主动 outreach 投出后，多久没收到用户回复算 unanswered？cold_reply 的判据是什么（回了但冷淡——怎么量化"冷淡"）？
2. **记录载体**：`_proactive_dispatch_audit` 的结构、容量上限（BoundedDict？）、是否持久化（跨重启是否保留反馈历史）？
3. **关联 origin_session**：2B 的 `LifeEvent.origin_session` 已回填投递目标会话；audit 按 session_key 记，须与 origin_session 对齐——投给 A 的没回应，压力应加在 A 的 cooldown 上，不能串到 B。
4. **写入触发点**：谁在何时写 audit？（用户回复事件钩子？下一轮 outreach 决策前回扫？）这决定了反馈闭环的时延与正确性。
5. **接线后撤除 guardrail 的方式**：单一数据源建立后，`unanswered_penalty * 0.0` 是保持（scheduler gate 独占）还是改接 `feedback_pressure`？**必须二选一，禁止两侧同时非零**（双重惩罚正是 M8 要防的）。

### 1.3 建议的 M8 实现切分（待 review 后细化）

- **PR-J1：unanswered 检测 + audit 生产者**——定义判定规则、建 audit 写入点、关联 origin_session、BoundedDict 持久化决策。
- **PR-J2：单一数据源接线**——确认 `feedback_pressure` 为唯一源；ShareIntent 侧维持 `* 0.0`（不重新激活乘子）；测试钉死"unanswered 恰好被惩罚一次"。

### 1.4 M8 测试矩阵（草案）

| 测试 | 断言 |
|------|------|
| `test_unanswered_detected_after_timeout` | outreach 投出后超时无回复 → audit 记 unanswered |
| `test_feedback_pressure_nonzero_after_unanswered` | audit 有 unanswered → `feedback_pressure > 0`（源不再干涸） |
| `test_pressure_scoped_to_origin_session` | A 未回应只抬 A 的 cooldown，不影响 B（origin_session 隔离） |
| `test_no_double_penalty` | unanswered 只在 scheduler gate 生效；ShareIntent `unanswered_penalty` 仍 `* 0.0`（核心，防 M8 双罚） |
| `test_audit_persists_restart`（若决定持久化） | 反馈历史跨重启存活 |

---

## 2. rel_register 真机阈值标定（deferred 项落实）

### 2.1 现状

2B 收尾已完成**解析标定**（rel_register.py 标定注释）：conf 累积 n 大时 → 友好误判占比 p；"友好不误升"要求阈值 > p；纯浪漫 N=8 下 n=5 → 0.625。取 `0.6 + 最小样本 5` 是压在文献"高频爱称友好语料误判 20-35%"之上的保守值。**值不需要改，已有依据。**

### 2.2 待做：真机实测 p

handoff §7 要求实测确认。标定协议（草案）：

1. **构建标注语料**：两组各 N 条真实风格中文消息——
   - 组 A「高频爱称的友好语料」（朋友间随意"亲爱的/宝贝"banter，无排他性/关系性指涉）。
   - 组 B「真浪漫语料」（含称呼 + 排他性宣称 + 关系性指涉）。
2. **跑真分类器**：每条过 `rel_register` 的 `_PROMPT` + 真 provider（deepseek/同配置），记 `_parse_rel` 结果。
3. **量误判率**：p = 组 A 中被判 romantic 的占比；recall = 组 B 中被正确判 romantic 的占比。
4. **判定**：若 p < 0.6 且 recall 可接受 → 确认现值；若 p 逼近/超 0.6 → 上调阈值至 p 之上，或加严 `_PROMPT` 判据。
5. **环境**：需运行中 AstrBot 宿主 + provider + token 预算（lab 环境，仿 2B 真机验证流程）。

### 2.3 为什么本阶段才做

真机批量 LLM 跑不在纯代码环境内可完成（无宿主/烧 token）。本协议交由有 lab 访问权的执行侧按 2B 真机验证同款流程跑。**在跑出 p 之前，现值（解析保守）为准，不阻塞其他工作。**

---

## 3. is_romantic 消费方接入（带自证红线）

### 3.1 硬红线（不可违反，2B handoff §3.2 / 红队 v6 F2 / v7 F5）

> **is_romantic 只许门控「路由 / 召回」，禁用于任何改变 Sylanne 自身表达亲密语域的生成。**
> 含间接路径：recall/persona 经回灌 system prompt 间接改输出语域也禁止。
> 违反 → 自证循环（她因为"判定亲密"而表现更亲密 → 又强化判定）。

接任何消费方前，必须先论证该接入点**不**把 is_romantic 的结果回灌进"她怎么说话"的生成侧。

### 3.2 候选消费方（各须独立设计 + review）

1. **记忆召回差异化**：亲密会话召回更私人的记忆碎片。
   - 红线检查：召回的碎片若进 system prompt 影响她语域 → **触红线**。需限定为"召回什么内容"而非"用什么语气说"，且需论证边界。**风险最高，建议最后做或暂缓。**
2. **主动发言门控**：is_romantic 作为 outreach 的额外 gate（非亲密会话降低主动频率）。
   - 这与 PR-I 路由同源（路由侧），**红线风险低**——它管"投不投/投谁"，不管"怎么说"。建议优先。
3. **人设/persona 注入**：按亲密度调 persona。
   - 红线检查：persona 直接决定她语域 → **几乎必然触红线**。除非有强隔离设计，否则**建议暂缓/否决**。

### 3.3 建议优先级

主动发言门控（低风险，路由侧）> 记忆召回（中高风险，需边界设计）> persona（高风险，倾向否决）。每项独立 PR + 独立 red-team review。

---

## 4. 可选后续项（低优先，按需立项）

| 项 | 来源 | 状态 | 备注 |
|----|------|------|------|
| relational_sheaf 类型枚举激活 | 2B handoff §51 | 可选 | 死枚举从未通电（rel_register 已用 LLM 分类替代其职能，激活收益待评估） |
| owner 私聊 UMO 直投 | 2B handoff §114/212 | 可选 | 解"只在群互动、无 1:1 的 owner 主动私推静默"；受平台未邀私信策略约束 |
| reactive 过滤 | 2B handoff §51 | 明确本批外 | 被动回应侧的 is_romantic 应用，红线风险需单独评估 |

---

## 5. 本阶段建议执行顺序

1. **M8（PR-J1 + J2）**——依赖代码、问题明确（数据源缺失），review 后可实现。
2. **rel_register 真机标定**——需 lab 环境，独立于代码改动，可并行交执行侧。
3. **主动发言门控接 is_romantic**——红线风险最低的消费方。
4. 记忆召回 / persona / 可选项——逐项独立 review，persona 倾向否决。

---

## 6. 启动门槛

本草案须过一轮架构 review。review 关注点：
- M8 §1.2 的五个设计决策是否拍板（尤其 unanswered 判定规则 + 是否持久化 audit）。
- is_romantic 消费方 §3 的红线论证是否充分（每个接入点单独过）。
- 真机标定 §2.2 协议是否可由执行侧落地。

**review 通过后，按 M8 → 标定 → 消费方逐项实现，每项同批合入 review。**
