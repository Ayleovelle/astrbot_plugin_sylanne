# Handoff — 本会话改动全量自审报告

> 生成时间:2026-06-14｜来源:5 路并行审查 + 红队 workflow(woa73r4o4)
> 状态:**代码已按本报告落地（M1–M6/S1–S3 + Wave1–3 + T2 收口）**；已提交并推送（feat/sdk-deep-integration-v2，PR#27），当前 599 passed。

---

## 〇、被审对象(本会话动过的全部)

| # | 文件 | 改动 | git 状态 |
|---|---|---|---|
| 1 | `sylanne_alpha/llm_request_pipeline.py` | `_assemble_final_prompt` 默认/非 Claude `else` 分支:`[inner_context]` 从 append 成 `role=assistant` 改为**并入 `system_prompt`** | 已追踪 `M` |
| 2 | `sylanne_alpha/llm_request_pipeline.py` | `_INJECTION_SLOTS` 删掉死的 `("focus",2,220)` 槽 | 已追踪 `M` |
| 3 | `sylanne_alpha/v2core/domains/focus.py` | **新建** FocusDomain 话头域 | 未追踪 `??` |
| 4 | `sylanne_alpha/v2core/fragment.py` | `build_mind_fragment` 加 `focus_line`,剥出受截区间 | 未追踪 `??` |
| 5 | `sylanne_alpha/v2core/integration.py` | `_runtime_for` 注册 `"focus": FocusDomain()` | 未追踪 `??` |
| 6 | `tests/test_focus_domain.py` / `tests/test_injection_position_gemini.py` | **新建** | 未追踪 `??` |

注:`v2core/` 整个目录是未提交状态(上一程遗留),3/4/5 无法 git diff,审查靠读全文。

---

## 一、扎实的部分(5 路 + 红队一致确认)

注入位修复(改动 1)**方向正确、是真根因修复**,无人反对:

- `else` 分支并入 `system_prompt` 实现正确:`inject_parts` 拼接、空守卫、unfinished 标签都对(`pipeline:1683-1705`)
- `request.system_prompt` 为 None/空时三层兜底 `str(getattr(...,'') or '')`,不抛异常
- advisory(Claude)、hajide 两分支**确实没被波及**——只动了 else
- 总量仍受 `_compute_injection_budget` 控制(最大 3600 字符),换注入点不改变量
- 删 focus 死槽正确:`raw_fragments` 本就没有 focus 键,是死码
- `system_prompt` 不持久化结论成立(机制订正见三-4)
- FocusDomain 铁律合规:写仅 EVOLVE、单一写者、`load_dict` 容缺向前兼容、持久化自动接入

---

## 二、红队三个最重要的判断

### 1. 撤销了一个 blocker —— 那是幻觉

第 5 路审查报 **blocker**:"tool loop 内 `_assemble_final_prompt` 被多次触发,同一 req 的 `system_prompt` 单轮内叠加重复注入"。

**红队坐实这是幻觉,应撤销。** 证据:`OnLLMRequestEvent` 每条用户消息只在 `internal.py:258` 触发一次,tool loop 内部不重触发;`ProviderRequest` 每轮全新构造(`entities.py:112` `system_prompt: str = ""`)。单轮内多次进入的路径不存在。

> ⚠️ 诚实补充:这是唯一 blocker 级发现,且第 5 路与红队**直接冲突**。红队判它幻觉,但红队也可能错。动手前建议再亲自核一次 `OnLLMRequestEvent` 在 tool loop 下的触发次数——取证,非修改。已把分歧如实交出,未擅自再开调查。

### 2. turn 结构是"必要非充分"—— 最重要的发现

红队对思想实验的回答,直接呼应"记忆/注入方式不对劲":

**修了 turn 结构,低信息消息 + 浓历史的漂移仍会发生。**

- 机制:`astr_main_agent.py:1405` 每轮把**完整** `conversation.history` 塞进 contexts,高密度情感历史(旧告白长文)不被清空
- 发"😋",模型同时看到当前 user turn(低信息)和 contexts 里的高密度历史——纯注意力竞争,**历史语义密度赢**
- 这条路径**和 turn 结构完全无关**,turn 结构修复对它无效
- turn 结构修复只解决"模型把注入内容当自己续写"的**机制性硬故障**;历史密度竞争是**独立软性漂移路径**

**根治还差什么**(红队方向,未实现):
- 给 history 加时间衰减/语义稀释(越老权重越低),或
- 给当前消息做显式锚定(FocusDomain 的 `prompt_line` 正在做这件事),或
- 两者结合

### 3. FocusDomain 终审:**留,但有核心契约缺陷必须修**

- 第 2 路说"建立在被推翻的 referent 假说上,候删" —— 红队判**过强、未坐实**
- FocusDomain 针对的正是第 2 点那条**独立软性漂移路径**(历史密度竞争),turn 结构修复覆盖不到,留存理由**独立成立**
- 但当前实现有核心契约缺陷(见 M1),不修就是带已知错误 ship

---

## 三、逐项清单(证据 / 推理 / 修法)

### 【必须改】不改不能 ship

**M1. `focus.py:30` `_MIN_MEANINGFUL` 3 → 2**
- 证据:`is_substantive("加班")` → `_meaningful_chars=2 < 3` → 返回 `False`
- 推理:两字中文词("加班""开会""好饿")几乎全是实义话题,却被判非实义 → 话头不立 → 用户随后发"😋"时反而钉到**更旧**的话头,制造反效果。FocusDomain 核心契约**部分失效**
- 修法:`_MIN_MEANINGFUL = 2`;或把二字实义词单独豁免

**M2. `focus.py:4-8` docstring 根因描述重写**
- 证据:docstring 写"affect 有 referent 无 = 跳话题根因",但真根因已确认是 turn 结构
- 推理:错误归因误导后人,违背"诚实修正"
- 修法:区分两条路径——"turn 结构漂移(已修)"vs"历史高密度内容竞争(FocusDomain 防御此路径)",删掉单一归因

**M3. `pipeline:1699` 日志 `chars` 低估**
- 证据:`chars={sum(len(v) for v in trimmed.values()) + len(unfinished_final)}`,实际 `inject_text` 含 `_format_inner_context` 标签(`[inner_context]`/`[感知]`),多 30-80 字符
- 推理:监控系统性低估注入量
- 修法:`chars={len(inject_text)}`

**M4. `test_injection_position_gemini.py:104` 补断言**
- 证据:传了 `unfinished_fragment='未说完的半句话'` 但没断言它进 system_prompt
- 修法:追加 `assert '未说完的半句话' in req.system_prompt`

**M5. `test_injection_position_gemini.py:90` 补断言**
- 证据:只断言 `'亲近感高' in ...`,没验原内容保留——拼接若 bug 成覆盖测试仍过
- 修法:追加 `assert '你是苏思澜' in req.system_prompt`

**M6. `test_injection_position_gemini.py:28-34` stub 注释纠错**
- 证据:注释写"忠实复刻默认分支语义",但默认分支直接写 system_prompt、**不调此 stub**(只 advisory 调),stub 成死代码
- 修法:改注释"仅对 claude_advisory 路径有效,默认模式不调此 stub"

### 【建议改】可本次带上,不阻塞 ship

- **S1. `test_focus_domain.py:81`** 去私有属性耦合(`assert list(d._recent)`)——加 `recent_topics` 只读属性,或只断言 `d.current`
- **S2. `fragment.py:100`** 魔数 `+9` 提成命名常量 `_SEP_OVERHEAD = 9` 或注释说明
- **S3. `pipeline:1692`** 加注释"此处 system_prompt 已含 v2core 心象片段,勿改成直接赋值"

### 【可不改】审查员提了但红队撤销或确认无影响

- 第 5 路 blocker"tool loop 单轮叠加"—— 红队坐实幻觉(见二-1 复核建议)
- hajide 分支日志漏报 unfinished 键(`pipeline:1647-1652`)—— 影响小,可随 M3 带上
- `focus.py` CJK 扩展区漏检 —— 常用字全在范围内,聊天场景几乎不触发
- `focus.py:107` `_GIST_MAX=40` 可能截残句 —— 设计决策非 bug,实测够用

---

## 四、红队点名"仍可能是幻觉"的审查结论(供判断审查可信度)

1. 第 5 路 blocker"tool loop 叠加"——幻觉
2. 第 2 路"FocusDomain 候删"——结论过强,历史密度竞争是独立路径,候删缺实机依据
3. 第 4 路 nit 说某测试"实际测冷启动"——分析偏差,`_ctx` 默认 `phase=EVOLVE`,ingest 确实写了话头,测试逻辑正确

---

## 五、机制订正(红队对"system_prompt 不持久化"的精确化)

之前我说"`internal.py:473-476` skip 首条 system 消息所以不持久化"。红队订正:那段 skip 针对的是 **messages 层**;真正原因是 **`req.system_prompt` 字段根本不写入 `conversation.history`**(`astr_main_agent.py:1405` 只恢复 contexts 字段),每轮 `ProviderRequest()` 初始化为空字符串。结论不变(不持久化),但根因表述要修正,别让后人误解 skip 路径。

---

## 六、收口与待决策

- 注入位那一刀(改动 1)是**真根因修复,扎实**
- 红队"必要非充分"拷问点破:**历史高密度内容竞争是另一条没堵的根**,turn 结构够不着它。FocusDomain 恰好冲这条去,该留(改 docstring),但需先修 M1 才靠得住
- **比所有清单项都大的待决策**:是否再往"历史密度稀释/衰减"那条根下一刀。这是新功能不是修补,留给用户定

**当前状态:Wave 0–3 与深审 Tier0–2 可落地项已全部实现。** 仍有意留作架构退役/大改:`HostSink` 实弹接线、`SelfCore.fuse` 全链、embedding 召回 PERCEPT、碎片防抖双向回写。若要 `git commit` 说一声即可。
