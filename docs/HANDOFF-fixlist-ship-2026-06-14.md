# Handoff — 跳话题 / Live Path 修复全量交付

> 生成时间：2026-06-14  
> 基线：**552 passed**（生成时）→ 当前 **599 passed**  
> Git：已提交并推送（feat/sdk-deep-integration-v2，PR#27）  
> 前置阅读：[HANDOFF-self-review-2026-06-14.md](./HANDOFF-self-review-2026-06-14.md)（审前判断材料，本文件是**修后交付说明**）

---

## 0. 一句话

用户发低信息消息（如「😋」）时模型跳回旧告白/旧话题，根因是 **三条独立路径**（A turn 结构 / B 历史密度 / C live 断链）。本次把 A+B+C 的可落地项全部修完；架构级死链（HostSink、SelfCore.fuse 等）**刻意未动**。

---

## 1. 三条故障路径（读 bug 前先认这个）

```
用户发「😋」时模型跑偏的三条独立路径：

路径 A — Turn 结构硬故障
  inner_context 以 role=assistant append 到 contexts 末尾
  → Gemini/OpenAI 把末尾当「模型已开口」续写，无视当前 user turn
  修复：默认模式并入 system_prompt（不持久化）

路径 B — 历史高密度竞争（turn 修复够不着）
  conversation.history 整段进 contexts，旧告白长文仍在
  低信息当前 turn 在注意力竞争中输给浓历史
  修复：FocusDomain 话头锚定 + history_dilution 软截断

路径 C — Live 基础设施断链（与 A/B 正交）
  非 realtime 无 buffer / 15min 记忆门控 / Recall 在 response 等
  → 用户觉得「她应该记得/接续」但管线根本没喂进去
  修复：Wave 1–3（见 §3）
```

---

## 2. Bug 清单：现象 → 复现 → 修法 → 后果

### 2.1 路径 A — 注入位 / Turn 结构

| ID | Bug | 怎么复现 | 怎么修的 | 修完后果 |
|---|---|---|---|---|
| **A1** | Gemini 默认模式把 `[inner_context]` 当 **assistant 消息** append 到 `contexts` 末尾，破坏「末尾必须是 user turn」 | 1. provider 走默认 compat（非 Claude advisory）<br>2. 历史里有一段长 assistant 告白<br>3. 当前 user 发 `😋`<br>4. 观察模型续写告白而非回应当前 emoji | `llm_request_pipeline._assemble_final_prompt` **else 分支**：`inject_parts` 拼进 `request.system_prompt`，**不再** append assistant 到 contexts | contexts 末尾保持真实 user turn；Gemini `_prepare_conversation` 末尾为 UserContent |
| **A2** | 注入日志 `chars` 系统性低估（不含标签开销） | 开 INFO 日志看 `[Sylanne] injection(system_prompt)` 的 chars，与 `len(inject_text)` 手工对比 | 日志改为 `chars={len(inject_text)}` | 监控数值可信 |
| **A3** | `_INJECTION_SLOTS` 含死槽 `("focus",2,220)` | grep `raw_fragments` 无 focus 键 | 删死槽；话头上提为 FocusDomain | 无功能变化，去死码 |

**自动化守卫**

```bash
python -m pytest tests/test_injection_position_gemini.py -q
```

核心断言：`contexts[-1].role == "user"`；注入内容在 `system_prompt`；`'你是苏思澜'` 与 unfinished 片段未被覆盖。

**机制订正（易误解）**

- `system_prompt` **不持久化**的原因：`ProviderRequest.system_prompt` **不写入** `conversation.history`，每轮新建为空——**不是**仅靠 skip 首条 system 消息。

---

### 2.2 路径 B — 历史密度 / 话头

| ID | Bug | 怎么复现 | 怎么修的 | 修完后果 |
|---|---|---|---|---|
| **B1** | `_MIN_MEANINGFUL=3` 误杀二字实义词（「加班」「开会」「好饿」）→ 话头不立 → 发 `😋` 时钉到**更旧**话头，**反效果** | `python -c "from sylanne_alpha.v2core.domains.focus import is_substantive; print(is_substantive('加班'))"` → 修前 `False` | `_MIN_MEANINGFUL = 2` | 二字话题可立话头；`test_focus_domain` 覆盖 |
| **B2** | 心象缺「对象」：只有情绪/对你/自我，低信息消息时情感无着落，注意力被 contexts 浓历史吸走 | 实义话题 → 用户发 emoji/短应答 → 模型拐回更早长文 | 新建 **FocusDomain** + `fragment.build_mind_fragment` 的 `focus_line`（低信息当前轮才钉锚） | system_prompt 心象层多一行「话头:…」；**不**占 contexts 末尾位 |
| **B3** | 完整 history 里旧长文密度压过当前 turn（turn 结构修了也仍会漂） | 同 A1 现场 + 即使 injection 正确仍被旧告白带跑 | 新建 `history_dilution.py`：低信息当前消息时对**较早** contexts 长文软截断（tail 保留） | 降低旧文语义密度；与 FocusDomain **双保险** |
| **B4** | FocusDomain docstring 错误归因「affect 有 referent 无」 | 读 `focus.py` 模块 docstring | 重写为路径 A/B 双路径说明 | 文档诚实 |

**自动化守卫**

```bash
python -m pytest tests/test_focus_domain.py tests/test_wave3_remaining.py::test_dilute_only_on_low_info_message -q
```

**诚实残留**

- `_GIST_MAX=40` 可能截残句——设计取舍，非 bug。
- 历史稀释是**软截断**，不是语义摘要；极长单条仍可能占满 tail 窗口。

---

### 2.3 路径 C — Live 断链 / 基础设施（深审 Tier0–2）

| ID | Bug | 怎么复现 | 怎么修的 | 修完后果 |
|---|---|---|---|---|
| **C1 T0-1** | stdlib WebUI `/api/settings` **明文**返回 API key（aiohttp 路径有掩码，stdlib 无） | `aiohttp` 未安装 → 打开配置页 → 看 network 响应 | `webui_server.py` stdlib GET settings 对齐 `_is_sensitive_key` → `********` | 回退路径不再泄露密钥 |
| **C2 T0-2** | `mark_dirty()` 零调用 → `_persist_kernel` KV 增量路径 **no-op** | `rg "mark_dirty\(" --glob "*.py"` 仅定义无调用（修前） | 记忆/unfinished 更新前 `mark_dirty("memory"|"session")`；`persist_kernel` 无 dirty 时仍写**文件** snapshot | KV 增量重新生效；文件刷盘不依赖 dirty |
| **C3 T0-3** | 再巩固 LLM rewrite 后只 `_persist_kernel`（no-op）+ **无** `_save_sylanne_memory_state` | rewrite 后 5s 内杀进程 → 专用 memory KV 可能是旧文本 | rewrite 末尾补 `await _save_sylanne_memory_state` | 缩短 memory KV 丢失窗口 |
| **C4 T1-3** | 非 realtime / 非 intercept：`llm_response_pipeline` early return **不写** `conversation_buffers` | `realtime_enabled=false` 或 `intercept=false` → 聊几轮 → buffer 无 bot 条目 | early return 路径异步 `_append_bot_reply_buffer`（只写 buffer，不 double tick） | bot 回复进 buffer + ConvMgr 同步 |
| **C5 T1-5** | legacy 记忆注入需 `gap≥900s` **且** realtime → 连聊永远无 `[记忆参考]` | 两条消息间隔 <15min → 无 memory_fragment | v2core 开时 `_MEMORY_GAP_SKIP=120`；非 realtime 也可走 legacy 召回 | 连聊场景更可能注入记忆 |
| **C6 T1-6/7** | v2core Recall 在 **response DELIBERATE** → 当轮 prompt **吃不到** recalled | 开 v2core → 当轮心象无「记忆线索」 | PERCEPT 拍 `_percept_recall` → `scratch["recalled"]` → `fragment` 的 `memory_line` | 当轮 system_prompt 可带记忆线索 |
| **C7 T1-8/9** | `consult_idle_reach` 只接 scheduler API，**live** `proactive_sylanne` 不走；`request_dispatch` 空桩 | grep live 链 vs `get_speech_decision` | `merge_idle_reach_into_decision` 共用；实现 `request_dispatch`；bridge 在 `reach_out` 时压倒计时 | 主动触达决策源对齐；dry_run 可测 |
| **C8 T1-11** | 短 gap 合并上轮 `_last_assessment` → 评估漂移 | 快速连发 → intent/情绪标签粘上一轮 | 短 gap 且无 fast 评估时清空 `last_assessment` | 减少 stale 评估污染 |
| **C9 T1-12** | 再巩固 async 与下一轮 recall **竞态** | 召回触 rewrite 的同时下轮 recall 读旧文本 | 同会话 `asyncio.Lock` 串行 `_reconsolidation_rewrite` | 降低 rewrite/recall 交叉 |
| **C10 T1-13** | memory meltdown 只清内存，**不删** KV / v2core 缓存 | WebUI 熔毁 → 重启后旧 KV 复活 | `purge_session_after_meltdown` 删 memory/kernel KV + v2core runtime 缓存 | 熔毁后状态真正清空 |
| **C11 T1-14** | LLM 工具可传 `detail=full` 泄漏内部 prompt/快照 | 工具调用 `detail=full` | 所有 `get_bot_*_state_tool` / `query_agent_state` 经 `_clamp_llm_tool_detail` | LLM 面强制 summary |
| **C12 T1-1/2** | v2core PERCEPT 在碎片合并 **之前**跑 → 心象与最终 user 文本不一致；群聊 SFPD 静默时心象已注入但无 tick | 碎片防抖 / 群聊静默场景 | PERCEPT 挪到 `_process_llm_request_final` 开头（合并+SFPD 之后） | 心象文本与是否应答一致 |
| **C13 T2** | WebUI 监控 `Number(x)\|\|default` 把 **0** 偷换成默认（integrity=0 显示成完好） | 后端 `boundary.integrity=0` → 监控页显示 1.0 | `adaptState` + `updateMonitor` 用 `num()` 显式判空 | 边界破损状态可见 |
| **C14 T2** | `emotion_reset` / `humanlike_reset` 后门默认 **开** | 无配置时调用 reset 命令成功 | 默认改 **关**（`allow_*_backdoor` default False） | 生产更安全；需显式开配置才能重置 |
| **C15 T2** | 主动链 `_last_message_times` 与 `_store.last_user_message_time` **双源分裂** | scheduler 仪式缺席判定与 pipeline gap 不一致 | `on_message` 双写；scheduler 读 store fallback | 沉默时长数据源对齐 |
| **C16 T2** | `request_bot_proactive_speech_dispatch_tool` 裸 `json.dumps`  bypass 消毒 | 看工具返回值无 `note` 字段 | 改 `_tool_json` 出口 | 与其他 state 工具一致 |
| **C17 T2** | `scratch["proactive"]` 无写者（死读） | grep 仅 `_is_idle` 读 | `run_percept_stage` 在 `event.proactive` 时写入 | 主动 consult 路径 idle 判定完整 |
| **C18 T2** | v2core terminate 落盘失败仅 `debug` | 模拟 save 异常 | 升为 `warning` + exc_info | 运维可看见丢状态风险 |
| **C19 T2** | EVOLVE 未挂 `memory.tick_decay` | 域衰减与 legacy 不一致 | `turn_runner` EVOLVE 末调 `mem.tick_decay()` | 记忆衰减在 v2core 路径推进 |
| **C20 T2** | `_assess_quality` 在 turn_runner **调两次** | grep 同函数连续两次 | 去掉 render 后冗余那次 | 质量信号不重复 |

**自动化守卫（Live 接线）**

```bash
python -m pytest tests/test_wave1_live_wiring.py tests/test_wave3_remaining.py tests/test_wave2_tier_remaining.py -q
python -m pytest tests/test_focus_domain.py tests/test_injection_position_gemini.py -q
```

---

## 3. 主要改动文件地图

| 区域 | 文件 | 作用 |
|---|---|---|
| 注入 / 请求管线 | `sylanne_alpha/llm_request_pipeline.py` | system_prompt 注入、PERCEPT 时序、稀释、记忆门控、mark_dirty、再巩固锁 |
| 响应管线 | `sylanne_alpha/llm_response_pipeline.py` | 非 intercept bot buffer |
| 话头域 | `sylanne_alpha/v2core/domains/focus.py` | FocusDomain |
| 心象 | `sylanne_alpha/v2core/fragment.py` | focus_line + memory_line + `_SEP_OVERHEAD` |
| 桥接 | `sylanne_alpha/v2core/integration.py` | focus 注册、PERCEPT recall、reach merge |
| 历史稀释 | `sylanne_alpha/history_dilution.py` | 路径 B contexts 侧防御 |
| 回合 | `sylanne_alpha/v2core/turn_runner.py` | tick_decay、proactive scratch、去重 _assess_quality |
| 持久化 | `sylanne_alpha/state_persistence.py` | persist_kernel 文件路径、meltdown purge、后门默认 |
| 主动 | `sylanne_alpha/proactive_scheduler.py` + `proactive_bridge.py` + `public_api.py` | dispatch、reach、工具消毒 |
| 宿主 | `main.py` | on_message 双写时间戳、stream chunk 兼容装饰器 |
| WebUI | `UI/index.html` + `webui_server.py` / `webui_routes.py` | num() 监控、settings 掩码、meltdown |
| 测试 | `tests/test_*focus*`, `test_injection_position_gemini`, `test_wave{1,2,3}_*` | 回归守卫 |

---

## 4. 验证命令（接手人第一步）

```powershell
Set-Location g:\Sylanne-next
python -m pytest tests/ -q --tb=no
# 预期：552 passed

# 分项
python -m pytest tests/test_injection_position_gemini.py tests/test_focus_domain.py -q
python -m pytest tests/test_wave1_live_wiring.py tests/test_wave3_remaining.py tests/test_wave2_tier_remaining.py -q
```

**实机冒烟建议（无自动化）**

1. **A 路径**：Gemini + 历史长告白 + 发 `😋` → 应回应 emoji 语境，不应续写告白；DevTools 看 contexts 末条 role=user。  
2. **B 路径**：「早饭好吃吗」→ `😋` → 回复应围绕早饭（心象含话头；极长 history 时旧文应被压缩后缀「较早对话已压缩…」）。  
3. **C 路径**：关 realtime 聊几轮 → 检查 buffer 有 bot 条目；开 v2core 短 gap 连聊 → 心象或 inner 层可见记忆线索。  
4. **安全**：stdlib WebUI 配置页不应明文 key；`emotion_reset` 默认应拒绝。

---

## 5. 修完的系统性后果（必须知情）

| 变化 | 含义 |
|---|---|
| inner_context 进 system_prompt | 每轮 ephemeral，**不**进 history；依赖 v2core 域状态跨轮，不靠假 assistant 消息 |
| history 稀释 | 低信息消息时会**改**较早 contexts 文本（加压缩后缀）；最近 tail 保留 |
| PERCEPT 后移 | 群聊 SFPD 静默轮**不再**提前注入心象（与 tick 一致） |
| mark_dirty + 文件 persist | 漂移/记忆变更开始**更常**落盘；行为从「几乎只 host 5s flush」变为「KV 增量也走」 |
| reach 接 live 链 | 空闲触达更可能升格 `reach_out`；bridge 倒计时会被压短 |
| 记忆门控 120s（v2core 开） | 连聊更频繁走 legacy 召回 + PERCEPT 召回，**token 压力上升**——需实机观察 |
| 后门默认关 | 旧脚本若依赖默认 reset 会失败，需在配置显式 `allow_emotion_reset_backdoor: true` |

---

## 6. 明确未做 / 留待下一程

### 6.1 架构退役级（大改，本次刻意不碰）

| 项 | 说明 |
|---|---|
| **HostSink 实弹接线** | `renderer.HostSink` 存在但 live 路径未实例化；SILENT/分段仍 mostly legacy |
| **SelfCore.fuse / Intent.affect 全链** | grep 仍可能零 live 消费者；P0-3 语义已改道 assessment 入 request tick |
| **InvertedIndex** | `memory_system.py` 定义，全仓无调用 |
| **session_store / migration** | v2core 模块在，live 未接线 |
| **碎片防抖 ↔ v2core 双向回写** | PERCEPT 时序已修，但未做「合并后文本回写 ctx」精细同步 |
| **v1 层 HostSink / 旧 agent 栈** | 与 v2core 双轨并存，未清理 |

### 6.2 需要配置/实机标定（代码已留接口）

| 项 | 说明 |
|---|---|
| **embedding PERCEPT 召回** | `_percept_recall` 已支持 `sylanne_alpha_embedding_memory_enabled` + provider_id；默认关键词召回 |
| **history 稀释参数** | `_DEFAULT_MAX_OLD_CHARS=200`、`_DEFAULT_KEEP_TAIL_MSGS=4` 未实机 θ 标定 |
| **FocusDomain 实机 A/B** | 自动化只有 fixture 级断言，无「旧告白 + 😋」端到端 LLM 裁判 |

### 6.3 审查争议 / 未再调查

| 项 | 说明 |
|---|---|
| **tool loop 单轮 system_prompt 叠加** | 红队判幻觉；**未**在真实 AstrBot tool loop 下再取证 |
| **hajide 分支日志缺 unfinished 键** | 低优先级，可随下次 pipeline 清理 |
| **swap_dirty 失败丢脏集** | 若 mark_dirty 全量启用，KV 写失败仍无重试——设计债 |

### 6.4 工程债

- 全部改动 **未 commit**；`v2core/` 等大目录在 git 里长期是 untracked/modified 混合态，提交前需 `git status` 逐项审。  
- 无 CHANGELOG 条目；若 ship 建议写 release note 强调「注入位 + 三路漂移 + live 接线」。  
- WebUI 实机截图在 `_webui_test/`，**未**覆盖本次 monitor num() 修复。

---

## 7. 建议提交顺序（若下一步要 commit）

```
Commit 1 — 路径 A + 测试：pipeline 注入位 + test_injection_position_gemini
Commit 2 — 路径 B：focus.py + fragment + history_dilution + tests
Commit 3 — 路径 C Wave1–3：integration / pipeline 时序 / proactive / persistence / webui
Commit 4 — T2 收口：UI num()、后门默认、test_wave2_tier_remaining
```

或单 commit 亦可，但 review 负担大。

---

## 8. 红队仍有效的判断（勿删）

1. **Turn 结构修复是必要非充分**——B 路径必须 FocusDomain + 稀释，不能只 ship A。  
2. **FocusDomain 不是 turn 修复替代品**——三者正交。  
3. **540+ 绿 ≠ 实机不跳话题**——LLM 层仍可能漂，只是机制性硬故障已去。

---

## 9. 联系人话

若实机仍跳话题，按 **A → B → C** 顺序排查：

1. contexts 末尾是否 user？（A）  
2. system_prompt 是否有话头行 / 旧文是否被压缩？（B）  
3. v2core 是否开、buffer 是否有 bot、gap 是否过门控？（C）

仍漂且 A/B/C 都确认正常 → 进入 **LLM/prompt 语义层** 或 **history 衰减策略** 产品决策，不是再改 injection 槽位能解决的。
