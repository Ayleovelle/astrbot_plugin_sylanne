# Phase 2B 亲密判定 — 决策备忘（暂停待定）

日期：2026-06-21
状态：**暂停。用户重新思考方向。** 本文件存五轮 review 的定论 + 证据，供恢复时直接决策，无需重推。

## 待决问题
life-sim 主动私推（"想你"/生活分享）该投给哪个会话？用户常态多会话并存（含同事/工作会话），现状 `_most_recent_host_key`（最近活跃）会把私推误投给同事。需要判定"哪个会话是亲密关系"。要求：身份中立（不锁性别）、不破坏 2A 重构、不碰 SDK 内部 `_engine/sylanne_core`。

## 五轮 review 定论（核心结论）
**SDK 现有能力下，没有任何信号能可靠自动区分"亲密伴侣" vs "情绪化同事"。** 逐一被实证否决（全 file:line）：
- **warmth**（v3）：瞬时情绪。暖聊同事升、冷战男友降。tracks 对话基调非关系类型。
- **relationship_memory().phase**（v4，body.py:510）：实为冲突量。驱动它的 preference/progress 标记全不在 VALID_FLAGS（base.py:25）、生产从没 emit；只有 boundary（冲突）能进计数器 → 和睦男友永远 low_signal，高冲突同事反而 active_continuity。
- **assessor 现有字段**：valence/arousal/wound_risk/memorable 全是情绪强度或可记性，同事吐槽 deadline 与男友坦白恐惧向量无法区分。
- **pd（新抽 personal_disclosure_depth）**（v5）：只测**用户单向**表露深度。但亲密（Reis&Shaver）是**双向**的（自我表露+伴侣回应+相互理解）。同事倾诉离婚 = pd 极高却非伴侣。EMA 怎么调都救不了——区分变量（关系类型）不在信号里。

**根因**：关系"类型"是双向/累积的社会事实，SDK 只暴露单向情感/认知维度，无双向互惠信号。

## 候选方向（恢复时择一）
1. **/bond 手动权威 + pd 仅参考**（推荐）：用户手动标亲密会话，绝不误判，身份中立。代价：新会话要手动一次。最简最准、贴单伴侣现实。
2. **pd + 互惠信号才自动**：要求 pd 持续高 + 双向互惠（Sylanne 也表露+持续双向节奏）。更接近真亲密，但要再造互惠信号、标定更难、工程更大。
3. **LLM 直接分类关系类型 + 多轮累积 + /bond 纠错**（文献新发现，2026-06-21 补）：不从情感标量反推，而让 LLM 直接读累积对话判关系类型（恋人/亲密/朋友/同事/陌生）。文献撑：《Are they lovers or friends?》(arxiv 2510.19028) 英 75-80%/韩 58-69%；中文很可能落韩文偏低带(58-69%)，有误判→/bond 当权威纠错覆盖（不取代）。骑现有主线 assessor LLM 调用多输出一个关系类型字段，多轮平滑+置信度累积。比 pd 单标量更对路（关系类型本就该整体判，非单向深度反推）。代价：分类 prompt+平滑+置信，比方向1大；中文准确率有限故必须配人工纠错。
4. **其他**：用户另想方向。

## 关于"文献能不能做"的定论修正（2026-06-21）

> **最终采纳（2026-06-21，用户坚持自动检测）：方向3 LLM 关系类型分类。** 第三次审计实证：现有信号全塌成"温暖强度"无法区分类型；加新 LLM 分类字段 rel_register（romantic/friendly/formal）可行——类型不在标量里、在 LLM 对文本的整体判断里，骑现有主线 assessor 调用（非新增）。单轮中文约 58-69%，靠多轮累积+置信平滑+/bond 纠错压残差。代码里真有死的类型枚举 relational_sheaf（INTIMATE/FRIENDLY/FORMAL）从没通电，可选激活。handoff 据此写 v7。
早先"SDK 无信号、做不出来"的结论**对单标量路径成立、对整体方法过窄**。文献对"区分关系类型"的真答案是双向多因子/整体分类，不是单情感标量累积：
- warmth/relationship_memory/pd 全栽，是因为都取**单因子/单向**。
- 存在成熟子领域：dyadic interpersonal relation classification（对话→关系类型）；LLM 直接分类恋人/朋友达 75-80%(英)。
- 故方向3可行，但中文准确率限制 + 需人工纠错是硬现实。Sources: arxiv 2510.19028；ar5iv 2012.02553；researchgate 318966795。

## 不论选哪个，已查实的工程约束（v5 review）
- pd 抽取：加在壳层 `assessor_async.py:212 _build_main_prompt`（主线 LLM 本就调，非新增调用）；**禁止**走 `AgentIntent.affect`（会经 self_core.py:316-327 漏进 SDK kernel values+assessment，破边界）→ 须壳层直写 relationship_layer。
- 持久化：`_reg` 只给 cleanup 不给落盘（session_origins 纯内存重启丢，已实证）；须仿 `sylanne_life_sim_state` 的 KV blob 自接（initialize 恢复 + throttled/terminate 存）。
- 路由：`_most_recent_host_key`（llm_request_pipeline.py:647）是共享 helper、4 调用方（:2667/:2898/:2917/:2937）→ 只能新加 `_intimate` 版，不改原函数。
- 冷启动死区：「无亲密会话→不投」会让单伴侣部署在 /bond 前完全静默 → 需 /bond 引导文档化，或单 host 时保留 last-active 兜底。
- `/bond` 指令：repo 无现成 `@filter.command` 先例（main.py:2179 是测试委托非装饰器），要新建首例。
- 亲密层经 `v2core/body_port` from_host 读，不调 body_port_for_session（那条会 import _engine）。
- LifeEvent.origin_session 走 `_event_from_dict`(:394)/`_event_to_dict`(:361)，非 LifeEvent.from_dict。

## 已定且不变的上游裁决
- M8 拆出 2B 单开阶段（坐在缺失的反馈基础设施上）。
- 亲密度做成壳层可复用层、经 port 读、不碰 SDK 内部。

handoff 现处 v5（docs/architecture/life-simulation-upgrade-phase-2b-handoff.md），方向定后据此收敛。
参见 [[phase2b-scope-m8-carved-origin-session]]、[[relationship-layer-reuse-relationship-memory]]。
