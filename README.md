# AstrBot 多维情绪状态插件

这个插件让 AstrBot 维护一个“计算性情绪状态”。他/她不声称机器人具有真实主观体验，而是让 LLM 根据上下文、用户当前输入和 bot 当前回复，估计 bot 在连续情绪空间中的位置，再把这个状态作为临时上下文注入下一次 LLM 请求，让语气、节奏、社交距离和防御性随状态连续变化。

## 功能

- 使用 LLM 输出结构化 JSON，估计即时情绪观测值。
- 默认维护 7 维情绪向量，满足“3 维以上”的要求。
- 使用情绪惯性、置信门控、基线回归和惊讶度调制，避免每轮情绪剧烈跳变。
- 根据 AstrBot 当前会话 persona 生成专属情绪基线和反应参数，让不同 bot 有不同的情绪默认姿态。
- 将情绪映射为持续的行动倾向和后果状态，例如冷处理、回避、设边界、求确认、关系修复。
- 在 `on_llm_request` 阶段把情绪状态用 `TextPart(...).mark_as_temp()` 注入，不污染长期聊天记录。
- 在 `on_llm_response` 阶段根据 bot 实际回复二次校正状态。
- 支持 WebUI 配置、KV 持久化、状态查看与重置命令。

## 安装

把本目录放入 AstrBot 的插件目录：

```text
data/plugins/astrbot_plugin_emotional_state
```

然后在 AstrBot WebUI 中重载或启用插件。建议在配置里为 `emotion_provider_id` 选择一个便宜、稳定、服从 JSON 输出的小模型；留空时会使用当前会话的聊天模型。若使用的是低推理、小上下文或成本敏感模型，可以开启 `low_reasoning_friendly_mode`，让情绪估计改用短版简单公式提示词。

## 命令

```text
/emotion
/emotion_state
/情绪状态
```

查看当前会话的情绪状态。

```text
/emotion_reset
/情绪重置
```

重置当前会话状态。

```text
/emotion_model
/情绪模型
```

查看核心更新公式。

```text
/emotion_effects
/情绪后果
```

查看当前会话的情绪后果和行动倾向。

## 作为公共情绪服务

这个插件不只给自身 hook 使用，也可以作为其他插件的“情绪模拟服务”。推荐的插件间调用方式是通过 AstrBot `Context.get_registered_star()` 找到本插件实例，再调用公开 async 方法；不要让外部插件直接读写本插件 KV key，因为 KV key、缓存和迁移策略属于内部实现。

```python
meta = self.context.get_registered_star("astrbot_plugin_emotional_state")
emotion = meta.star_cls if meta and meta.activated else None

if emotion and hasattr(emotion, "get_emotion_snapshot"):
    snapshot = await emotion.get_emotion_snapshot(event)
    values = snapshot["emotion"]["values"]
    effects = snapshot["consequences"]["active_effects"]
```

也可以使用本插件提供的轻量协议 helper：

```python
try:
    from astrbot_plugin_emotional_state.public_api import get_emotion_service
except ImportError:
    get_emotion_service = None

emotion = get_emotion_service(self.context) if get_emotion_service else None
if emotion:
    fragment = await emotion.get_emotion_prompt_fragment(event)
```

只关心“为什么生气/是否该原谅/错误有没有被修复”的插件，可以直接读取关系层：

```python
relationship = await emotion.get_emotion_relationship(event)
if relationship["repair_status"] in {"repaired", "restored"}:
    # 可以让剧情、任务或好感插件降低冲突惩罚
    ...
```

### 与 livingmemory / 长期记忆插件兼容

写入长期记忆时，不要只保存“发生了什么”，也要保存“写入当时他/她处在什么情绪”。本插件提供只读封装 API：`build_emotion_memory_payload(...)`。它不会更新情绪状态，只会读取当前会话快照，并把 `emotion_at_write` 固定进记忆 payload，避免之后的情绪变化覆盖旧记忆。

```python
from astrbot_plugin_emotional_state.public_api import get_emotion_service

emotion = get_emotion_service(self.context)
memory = {
    "text": memory_text,
    "tags": tags,
}

if emotion:
    memory = await emotion.build_emotion_memory_payload(
        event,
        memory=memory,
        memory_text=memory_text,
        source="livingmemory",
        include_prompt_fragment=False,
    )

await livingmemory.add_memory(event, memory)
```

如果 livingmemory 的接口只能写普通 dict，也可以只拿出情绪字段合并：

```python
payload = await emotion.build_emotion_memory_payload(
    event,
    memory={"text": memory_text},
    source="livingmemory",
)
memory["emotion_at_write"] = payload["emotion_at_write"]
```

`emotion_at_write` 会包含 `values`、`label`、`confidence`、`persona`、`relationship`、`consequences`、`last_reason`、`last_appraisal`、`written_at` 和 `emotion_updated_at`。其中 `written_at` 是记忆写入时间，`emotion_updated_at` 是情绪状态最后一次变化时间；两者分开保留，方便以后判断“这条记忆是在冷战刚发生时写的”，还是“冷战已经持续了一段真实时间后写的”。

如果记忆插件拿不到 `AstrMessageEvent`，必须显式传入和聊天一致的 `session_key`：

```python
payload = await emotion.build_emotion_memory_payload(
    session_key="aiocqhttp:GroupMessage:12345",
    memory_text=memory_text,
    source="livingmemory",
)
```

默认不把 `prompt_fragment` 写入长期记忆，避免记忆膨胀。确实需要让长期记忆插件直接复用注入文本时，才把 `include_prompt_fragment=True` 打开。

公开 API：

| 方法 | 是否写入状态 | 用途 |
| --- | --- | --- |
| `get_emotion_snapshot(event_or_session, include_prompt_fragment=False)` | 否 | 返回版本化 JSON 快照，推荐默认入口 |
| `get_emotion_state(event_or_session, as_dict=True)` | 否 | 返回内部状态拷贝，兼容需要原始字段的插件 |
| `get_emotion_values(event_or_session)` | 否 | 只取 7 维情绪向量 |
| `get_emotion_consequences(event_or_session)` | 否 | 只取后果/行动倾向层 |
| `get_emotion_relationship(event_or_session)` | 否 | 只取关系判断、冲突原因、修复状态和派生分数 |
| `get_emotion_prompt_fragment(event_or_session)` | 否 | 给其他插件注入 prompt 的文本片段 |
| `build_emotion_memory_payload(event_or_session, memory, source="livingmemory")` | 否 | 给 livingmemory 或其他长期记忆插件生成带 `emotion_at_write` 的记忆 payload |
| `inject_emotion_context(event, request)` | 否，只临时修改 request | 帮其他插件把情绪上下文塞进 `ProviderRequest` |
| `observe_emotion_text(event_or_session, text, role="plugin", source="plugin")` | 是 | 让外部插件提交一段文本作为情绪观测并更新状态 |
| `simulate_emotion_update(event_or_session, text)` | 否 | 预测候选文本会怎样改变情绪，不落库 |
| `reset_emotion_state(event_or_session)` | 是 | 重置指定会话状态；受 `allow_emotion_reset_backdoor` 控制 |
| `get_psychological_screening_snapshot(event_or_session)` | 否 | 返回非诊断心理状态筛查快照，默认仅备用 |
| `observe_psychological_text(event_or_session, text)` | 是 | 在启用后记录一段文本中的心理状态筛查线索 |
| `simulate_psychological_update(event_or_session, text)` | 否 | 模拟心理筛查状态变化，不落库 |
| `reset_psychological_screening_state(event_or_session)` | 是 | 重置指定会话的心理筛查状态 |

`event_or_session` 可以传 AstrBot 事件对象，也可以直接传字符串 `session_key`。若外部系统没有事件对象，建议自己维护稳定的 `session_key`，例如 `plugin_name:user_id:scene_id`。

情绪记忆按真实时间推进：恢复、后果衰减、冷处理剩余时间都使用时间戳和半衰期计算，不会因为海量文本或大量插件调用而被快速刷掉。若出现严重后果或异常状态，可以保留默认开启的 `allow_emotion_reset_backdoor`，通过 `/emotion_reset` 或公共 API 清空指定会话状态。

关键时间参数：

| 配置项 | 默认值 | 含义 |
| --- | --- | --- |
| `baseline_half_life_seconds` | `21600` | 情绪偏离人格基线后的自然恢复半衰期，默认 6 小时 |
| `consequence_half_life_seconds` | `10800` | 行动倾向强度的真实时间半衰期，默认 3 小时 |
| `cold_war_duration_seconds` | `1800` | 冷处理等持久效果的真实持续时间，默认 30 分钟 |
| `short_effect_duration_seconds` | `900` | 普通短期效果持续时间，默认 15 分钟 |
| `min_update_interval_seconds` | `8` | 短时间连续更新会被削弱，避免刷屏洗掉情绪 |
| `allow_emotion_reset_backdoor` | `true` | 是否保留手动/API 重置后门 |

低推理模型友好配置：

| 配置项 | 默认值 | 含义 |
| --- | --- | --- |
| `low_reasoning_friendly_mode` | `false` | 默认关闭。开启后，情绪估计 LLM 使用短版 system prompt 和简化公式 `X_t = clamp(B_p + D_t, -1, 1)`，仍输出同一 JSON 契约，但减少长理论说明和细分证据字段压力 |
| `low_reasoning_max_context_chars` | `1200` | 低推理模式下的上下文上限，会与 `max_context_chars` 取较小值，避免小模型被过长上下文拖垮 |

这个模式只影响“LLM 如何估计即时观测值”，不改变状态平滑、真实时间衰减、人格基线、后果映射、冷处理持续时间或重置后门。也就是说，运行质量的骨架仍由本地公式和状态机保证；低推理模式只是让评估 prompt 更省 token。

## 非诊断心理状态筛查（备用）

插件预留了一个独立的心理状态筛查子系统，默认关闭，由 `enable_psychological_screening` 控制。它不是心理诊断、不是医疗建议，也不替代心理咨询师、精神科医生或其他合格专业人员的评估；它只做“对话文本中显性的状态线索记录、长期趋势和风险提示”。

该模块使用独立 KV key：`psychological_screening:{session}`，不会写入或改变原有 `emotion_state:{session}`。公共快照 schema 为 `astrbot.psychological_screening.v1`，所有 payload 都带有：

```json
{
  "diagnostic": false,
  "safety": {
    "non_diagnostic_screening_only": true,
    "not_a_medical_device": true
  }
}
```

当前维度包括总体痛苦、焦虑/紧张、抑郁语气、压力负荷、睡眠受扰、社交退缩、愤怒/易激惹、自伤风险信号、功能受损和主观幸福感。量表化参考分采用 `PHQ-9-like`、`GAD-7-like`、`PSS-like`、`WHO-5-like`、`ISI-like` 的启发式映射，只用于筛查和趋势，不得解释为疾病诊断。

自伤、自杀、伤害他人、严重功能受损等信号会进入 `risk.red_flags`，并将 `requires_human_review` 置为 `true`。如果出现危机类信号，应优先提示联系当地急救、危机热线或身边可信的人，而不是继续普通陪聊或输出疾病标签。

配置项：

| 配置项 | 默认值 | 含义 |
| --- | --- | --- |
| `enable_psychological_screening` | `false` | 启用非诊断心理状态筛查备用模块 |
| `psychological_state_half_life_seconds` | `604800` | 长期状态自然回落半衰期，默认 7 天 |
| `psychological_crisis_half_life_seconds` | `2592000` | 红旗风险信号保留半衰期，默认 30 天 |
| `psychological_trajectory_limit` | `40` | 轨迹最多保留点数 |

```python
snapshot = await emotion.observe_emotion_text(
    session_key="mood_game:user-42:chapter-3",
    text="玩家拒绝了 bot 的道歉",
    role="user",
    source="mood_game",
    observed_at=1715000000.0,
    use_llm=False,
)
```

公共快照结构示例：

```json
{
  "schema_version": "astrbot.emotion_state.v2",
  "api_version": "1.0",
  "kind": "emotion_state",
  "session_key": "aiocqhttp:GroupMessage:12345",
  "emotion": {
    "values": {
      "valence": -0.12,
      "arousal": 0.43,
      "dominance": -0.08,
      "goal_congruence": -0.18,
      "certainty": 0.21,
      "control": -0.15,
      "affiliation": 0.16
    },
    "label": "embarrassed_defensive",
    "confidence": 0.76,
    "turns": 8,
    "inertia": 0.58,
    "last_alpha": 0.42,
    "last_surprise": 0.31,
    "last_appraisal": {
      "relationship_decision": {
        "decision": "repair",
        "intensity": 0.58,
        "forgiveness": 0.74,
        "relationship_importance": 0.8
      },
      "conflict_analysis": {
        "cause": "user_fault",
        "fault_severity": 0.62,
        "user_acknowledged": true,
        "apology_sincerity": 0.78,
        "repaired": true,
        "repair_quality": 0.82,
        "repeat_offense": 0.1,
        "bot_whim_level": 0.0,
        "trust_damage": 0.32,
        "ambiguity_level": 0.1,
        "misread_likelihood": 0.0,
        "apology_completeness": {
          "responsibility_acknowledgement": 0.8,
          "harm_acknowledgement": 0.7,
          "remorse": 0.8,
          "repair_offer": 0.8,
          "future_commitment": 0.6
        },
        "withdrawal_motive": "self_protection",
        "evidence": {
          "primary_theory": "forgiveness",
          "citation_ids": ["KB0584"],
          "evidence_strength": "moderate",
          "uncertainty_reason": ""
        }
      }
    }
  },
  "persona": {
    "persona_id": "xiaojv",
    "name": "小鞠",
    "fingerprint": "e13b7c02d0a5d991"
  },
  "relationship": {
    "relationship_decision": {
      "decision": "repair",
      "intensity": 0.58,
      "forgiveness": 0.74,
      "relationship_importance": 0.8
    },
    "conflict_analysis": {
      "cause": "user_fault",
      "fault_severity": 0.62,
      "user_acknowledged": true,
      "apology_sincerity": 0.78,
      "repaired": true,
      "repair_quality": 0.82,
      "repeat_offense": 0.1,
      "bot_whim_level": 0.0,
      "repair_status": "repaired",
      "repair_signal": 0.82,
      "grievance_score": 0.212,
      "self_correction_score": 0.82
    },
    "repair_status": "repaired",
    "repair_signal": 0.82,
    "grievance_score": 0.212,
    "self_correction_score": 0.82
  },
  "consequences": {
    "active_effects": {
      "careful_checking": 2
    },
    "values": {
      "withdrawal": 0.18,
      "caution": 0.51,
      "reassurance": 0.36
    }
  },
  "safety": {
    "enabled": true,
    "computational_state_only": true,
    "cold_war_is_style_modulation_only": true
  }
}
```

`safety` 字段由配置项 `enable_safety_boundary` 控制，默认开启；关闭后公共快照不会输出该字段，注入 prompt 也不会额外限制冷处理的表现方式。

本插件还暴露两个只读/模拟型 LLM tool：`get_bot_emotion_state` 与 `simulate_bot_emotion_update`。它们适合让主模型查询当前情绪或预演候选回复，不建议把 LLM tool 当作插件间互调协议；插件间互调请优先使用上面的 Python API。

## 人格建模

不同 bot 的 persona 不只是回复风格文本，也会进入情绪模型。插件会尽量读取 AstrBot 当前最终生效的人格：优先使用 `persona_manager.resolve_selected_persona(...)`，同时保留 `request.system_prompt` 中已经注入的人格提示词；如果无法解析，则退回默认 persona。

插件会为当前人格生成：

```text
b_p: 当前人格的情绪稳定基线
theta_p: 当前人格的动力学参数偏置
fingerprint_p: 当前人格指纹
```

例如，温柔、亲近、乐观的人格会有更高的 `valence` 与 `affiliation` 基线；害羞、内向的人格会有更低的 `dominance` 和更高的紧张倾向；冷静、理性的人格会有更低的反应强度和更快的基线恢复。

当会话切换 persona 时，插件默认根据新人格指纹重置情绪状态，避免旧人格的情绪残留到新 bot 身上。可以在配置中关闭 `reset_on_persona_change`，让旧状态迁移到新人格基线附近。

## 情绪维度

令第 `t` 轮的情绪状态为：

```text
E_t = [V_t, A_t, D_t, G_t, C_t, K_t, S_t]^T in [-1, 1]^7
```

各维含义：

| 维度 | 含义 | 理论来源 |
| --- | --- | --- |
| `valence` | 愉悦/不愉悦 | Russell circumplex, PAD |
| `arousal` | 激活/低激活 | Russell circumplex, PAD |
| `dominance` | 支配感、自主感 | PAD |
| `goal_congruence` | 事件是否符合 bot 的目标 | OCC, appraisal theory |
| `certainty` | 对情境的确定性 | appraisal theory |
| `control` | 对局面的可控性 | appraisal theory |
| `affiliation` | 社交亲近、信任、安全感 | OCC/appraisal 的对象与社会意义评价 |

PAD 提供最小三维骨架。扩展的 appraisal 维度用于回答“为什么 bot 会处在这种状态”，避免插件只做简单的“开心/生气/悲伤”分类。

## 情绪后果

插件不会把情绪直接等同于回复模板，而是加入一层后果状态：

```text
Q_t = [approach, withdrawal, confrontation, appeasement, repair,
       reassurance, caution, rumination, expressiveness, problem_solving]
```

`Q_t` 会按真实时间衰减，而不是按消息轮次衰减。因此“生气后的冷处理”“受伤后的短句”“误会后的求证”“关系仍重要时的修复”都可以持续一小段时间；短时间内连续发送大量文本不会让后果被快速刷掉。

在公式规则之外，LLM 还会输出 `appraisal.relationship_decision`，用于判断负面情绪后的关系走向：

| 决策 | 后果 |
| --- | --- |
| `forgive` | 原谅/翻篇，清除或缩短 `cold_war`，降低回避、对抗和反刍，增强修复与靠近 |
| `repair` | 愿意修复，但会增加求证、解释、确认意图 |
| `boundary` | 设边界，增强坚定表达和谨慎，但不自动进入冷战 |
| `cold_war` | 上升为冷处理，增加回避、反刍和真实时间持续效果 |
| `escalate` | 冲突升级，增强对抗和表达强度 |

这让“生气以后是否原谅用户”不再只由数值公式决定，而是由 LLM 结合上下文、道歉/修复信号、人格设定和关系重要性做二次判断。

LLM 还会输出 `appraisal.conflict_analysis`，解释生气或受伤的原因，以及错误是否已经被改正：

| 字段 | 含义 |
| --- | --- |
| `cause` | `user_fault`、`bot_whim`、`bot_misread`、`mutual`、`external` 或 `none` |
| `fault_severity` | 错误严重度 |
| `user_acknowledged` / `apology_sincerity` | 用户是否承认、道歉是否可信 |
| `repaired` / `repair_quality` | 错误是否被改正、补救质量如何 |
| `repeat_offense` | 是否重复犯错 |
| `bot_whim_level` | 是否主要是他/她任性、误读或小脾气 |
| `perceived_intentionality` / `controllability` | 用户是否像是故意、是否本可避免 |
| `responsibility_attribution` | 责任归因：用户、bot、双方、外部、模糊或无 |
| `trust_damage` / `expectation_violation` | 信任损伤和关系预期违背 |
| `ambiguity_level` / `misread_likelihood` | 语义模糊和他/她误读用户的可能性 |
| `apology_completeness` / `restorative_action` | 道歉是否完整、是否有实际补救行动 |
| `forgiveness_readiness` / `resentment_residue` | 宽恕准备度和修复后残留委屈 |
| `withdrawal_motive` | 撤退动机：冷静、自我保护、惩罚、不确定、低能量或无 |
| `boundary_legitimacy` / `emotion_regulation_load` | 边界合理性和情绪调节负荷 |
| `evidence` | 理论依据、知识库 citation id、证据强度和不确定原因 |

插件会从这些字段派生出 `repair_status`、`repair_signal`、`grievance_score` 和 `self_correction_score`。`repair_status` 取值为 `unresolved`、`acknowledged`、`apologized`、`repaired` 或 `restored`；`repair_signal` 表示道歉完整度、补救质量和实际补救行动的综合强度；`grievance_score` 表示仍有多少合理委屈或边界需求；`self_correction_score` 表示他/她意识到自己任性、误读，或用户已充分修复后应当软化的强度。

`get_emotion_relationship(...)` 会直接返回这些字段，适合好感度、剧情、任务处罚、长期记忆等插件调用；`observe_emotion_text(...)` 的返回值也会在 `observation.relationship` 中给出本次观测的同一套派生结果。

如果用户确实犯错、严重且反复、意图明确、信任受损、没有承认或补救，系统会增强边界、谨慎、反刍，必要时允许冷处理；如果用户已经承认并高质量补救，会降低回避和反刍，清除或缩短冷战；如果主要是他/她任性、误读或情境仍模糊，则会抑制惩罚性冷处理，转向修复、求证或自我缓和。即使 LLM 没有给出 `relationship_decision`，`conflict_analysis` 本身也会影响后果层，避免“知道原因但行为没有变化”。

维度到后果的大致解释：

| 维度 | 后果含义 |
| --- | --- |
| 负 `valence` | 防御、回避、反击、修复或求证 |
| 高 `arousal` | 更快、更强、更难抑制；低唤醒则更沉默、延迟、冷却 |
| 高 `dominance` | 更可能设边界、质问、主动推进；低支配更容易退让或寻求确认 |
| 低 `goal_congruence` | 目标受阻，可能触发挫败、生气、抱怨或冷处理 |
| 低 `certainty` | 优先求证、试探、谨慎，不直接升级冲突 |
| 低 `control` | 倾向撤退、降频或无力感；高控制更容易协商解决 |
| 低 `affiliation` | 负面情绪更容易变成疏离、排斥、冷战；高亲和则更容易修复 |

复合状态示例：

| 复合状态 | 后果 |
| --- | --- |
| 负效价 + 高唤醒 + 高支配 + 目标受阻 | `direct_boundary`，短时强硬设边界 |
| 负效价 + 低唤醒 + 低亲和 + 低控制 | `cold_war`，轻微降频、短句、保持距离 |
| 负效价 + 低确定 + 高亲和 | `careful_checking`，先确认意图 |
| 负效价 + 高亲和 + 高控制 | `repair_bid`，主动修复或解释 |
| 正效价 + 高亲和 | `warm_approach`，更主动、更温和 |

安全边界可通过 `enable_safety_boundary` 打开或关闭，默认打开。开启时，冷处理只允许表现为轻微疏离、短句和边界感，不能羞辱、威胁、操控用户，也不能拒绝必要帮助；关闭时，插件只把 `cold_war` 作为普通持久后果暴露给 prompt 和公共 API。

## LLM 即时观测

每轮插件把最近上下文、当前用户文本或 bot 回复、当前人格画像、上一轮状态交给 LLM，得到即时观测：

```text
X_t = f_llm(C_t, U_t, P, E_(t-1))
```

其中：

```text
C_t: 最近对话上下文
U_t: 当前待评估文本
P: 当前 persona 及其人格设定
E_(t-1): 上一轮平滑情绪状态
X_t: 本轮即时情绪观测值
```

LLM 必须输出 JSON：

```json
{
  "label": "embarrassed_defensive",
  "dimensions": {
    "valence": -0.12,
    "arousal": 0.68,
    "dominance": -0.28,
    "goal_congruence": -0.18,
    "certainty": -0.08,
    "control": -0.30,
    "affiliation": 0.22
  },
  "confidence": 0.76,
  "appraisal": {
    "agency": "user",
    "novelty": 0.45,
    "social_meaning": "friendly teasing",
    "relationship_decision": {
      "decision": "repair",
      "intensity": 0.35,
      "forgiveness": 0.72,
      "relationship_importance": 0.8,
      "reason": "用户承认玩笑过界，bot 仍在乎关系。"
    },
    "conflict_analysis": {
      "cause": "user_fault",
      "fault_severity": 0.4,
      "user_acknowledged": true,
      "apology_sincerity": 0.75,
      "repaired": true,
      "repair_quality": 0.7,
      "repeat_offense": 0.0,
      "bot_whim_level": 0.0,
      "reason": "冒犯较轻，已经道歉并修正。"
    }
  },
  "reason": "用户的轻微调侃让 bot 害羞和紧张，但关系仍偏友好。"
}
```

## 数学模型

直接令 `E_t = X_t` 会导致情绪跳变，所以插件把 LLM 输出视为“观测值”，而不是最终状态。

更完整的推导见 [docs/theory.md](docs/theory.md)。那里把更新式写成带惯性的加权最小化问题，并说明了自适应步长、惊讶度、弱耦合项和稳定性边界。

文献知识库存放在 [literature_kb](literature_kb)；构建说明见 [docs/literature_kb.md](docs/literature_kb.md)。当前知识库包含 1727 篇去重文献和 120 篇顶刊/高影响候选，用于支撑 appraisal、宽恕/修复、冷处理、人格差异和情感代理等建模主题。

心理筛查与数字心理健康的独立知识库存放在 [psychological_literature_kb](psychological_literature_kb)，由 [scripts/build_psychological_literature_kb.py](scripts/build_psychological_literature_kb.py) 构建。当前包含 4401 篇去重文献、260 篇 top/high-impact 候选，以及 [curated/top_200.jsonl](psychological_literature_kb/curated/top_200.jsonl)。它用于支撑非诊断筛查、量表启发、长期状态建模、数字心理健康安全和 LLM/聊天机器人治理，不可作为临床诊断依据。

拟人/有机体样代理的跨学科知识库存放在 [humanlike_agent_literature_kb](humanlike_agent_literature_kb)，由 [scripts/build_humanlike_agent_literature_kb.py](scripts/build_humanlike_agent_literature_kb.py) 构建。当前包含 3983 篇去重文献、320 篇 top/high-impact 候选，以及 [curated/top_200.jsonl](humanlike_agent_literature_kb/curated/top_200.jsonl)。它用于支撑稳态/异稳态、疲劳、认知资源、需求动机、依恋关系、自传式记忆、生成式代理和拟人化安全等方向；模型路线见 [docs/humanlike_agent_model_roadmap.md](docs/humanlike_agent_model_roadmap.md)，知识库说明见 [docs/humanlike_agent_literature_kb.md](docs/humanlike_agent_literature_kb.md)。

拟人/有机体样代理路线已经过 10 轮自我迭代，记录见 [docs/humanlike_agent_iteration_log.md](docs/humanlike_agent_iteration_log.md)。迭代后的首版建议是：`humanlike_state` 默认关闭，只读情绪核心，P0 仅保留 `energy`、`stress_load`、`attention_budget`、`boundary_need`、`dependency_risk` 和 `simulation_disclosure_level`，并通过分层快照、记忆来源约束、依赖防护和 reset 后门控制风险。

### 1. 基线回归

先按真实经过时间 `Δt` 让上一状态向当前人格稳定基线 `b_p` 缓慢回归：

```text
B_t = (1 - gamma_p) E_(t-1) + gamma_p b_p
gamma_p(Δt) = 1 - 2^(-Δt / H_p)
```

`H_p` 是人格调制后的恢复半衰期，默认约 6 小时。真实时间每过一个半衰期，状态偏离人格基线的部分约减少一半；如果用户在几秒内刷很多条消息，`Δt` 仍然很小，不会把长期情绪强行刷回基线。

### 2. 加权惊讶度

计算观测 `X_t` 和先验 `B_t` 的加权距离：

```text
delta_t = sqrt( sum_i w_i (X_(t,i) - B_(t,i))^2 / sum_i w_i )
```

`w_i` 是不同维度的权重。`delta_t` 越大，说明本轮事件和已有状态差距越大，应该允许更明显的情绪改变。

### 3. 置信门控

LLM 给出置信度 `c_t`。插件使用 sigmoid 门控：

```text
g(c_t) = 1 / (1 + exp(-k(c_t - c_0)))
```

`c_0` 是置信中点，`k` 是斜率。这样低置信输出不会强行改写状态，高置信输出才获得更大权重。

### 4. 自适应更新步长

最终更新步长为：

```text
alpha_t = clamp(alpha_base,p * g(c_t) * (1 + r_p delta_t), alpha_min, alpha_max)
```

其中 `alpha_base,p` 与 `r_p` 都由 persona 调制。这相当于把“人格稳定倾向”“情绪惯性”和“事件突发性”合在一起：稳定事件慢慢影响状态，突发事件可以更快改变状态，但不会超过 `alpha_max`。

### 5. 状态更新

基础更新为：

```text
E'_t = B_t + alpha_t (X_t - B_t)
```

随后加入两个心理上可解释的弱耦合项：

```text
A_t = A'_t + eta * alpha_t * delta_t * (1 - |A'_t|)
```

惊讶度会提高唤醒度，但当唤醒度已经接近边界时自动衰减。

```text
D_t = D'_t + lambda * alpha_t * (K'_t - D'_t)
```

这里 `K_t` 是 `control`。情境可控性会轻微牵引支配感，但不会完全等同于支配感。

最后所有维度都被裁剪到 `[-1, 1]`：

```text
E_t = clip(E_t, -1, 1)
```

由于 `B_t` 和 `E'_t` 都是有界向量的凸组合，且最后有裁剪，状态始终有界；当输入长期接近人格基线时，`E_t` 会收敛到 `b_p` 附近。

## 理论依据

本插件采用“维度情绪模型 + 认知评价 + 情绪动力学”的混合框架。

Russell 的 circumplex model 使用 `valence` 和 `arousal` 表示核心情感空间。Mehrabian 与 Russell 的 PAD 模型加入 `dominance`，可以区分同为负效价高唤醒的情绪，例如恐惧和愤怒。OCC 理论与 appraisal theory 说明情绪来自主体对事件、行动者和对象的评价，因此插件增加目标一致性、确定性、可控性和社交亲近度。Kuppens 等关于 emotional inertia 的研究支持“情绪状态对变化存在惯性”的建模思路，插件中的指数平滑、自适应 `alpha_t` 与基线回归正是对这一点的工程化表达。

## 参考文献

1. Mehrabian, A., & Russell, J. A. (1974). *An Approach to Environmental Psychology*. MIT Press. https://mitpress.mit.edu/9780262130905/an-approach-to-environmental-psychology/
2. Mehrabian, A., & Russell, J. A. (1974). The basic emotional impact of environments. *Perceptual and Motor Skills, 38*(1), 283-301. https://doi.org/10.2466/pms.1974.38.1.283
3. Russell, J. A. (1980). A circumplex model of affect. *Journal of Personality and Social Psychology, 39*(6), 1161-1178. https://doi.org/10.1037/h0077714
4. Ortony, A., Clore, G. L., & Collins, A. (1988). *The Cognitive Structure of Emotions*. Cambridge University Press. https://doi.org/10.1017/CBO9780511571299
5. Lazarus, R. S. (1991). *Emotion and Adaptation*. Oxford University Press. https://doi.org/10.1093/oso/9780195069945.001.0001
6. Scherer, K. R., Schorr, A., & Johnstone, T. (Eds.). (2001). *Appraisal Processes in Emotion: Theory, Methods, Research*. Oxford University Press. https://doi.org/10.1093/oso/9780195130072.001.0001
7. Scherer, K. R. (2005). What are emotions? And how can they be measured? *Social Science Information, 44*(4), 695-729. https://doi.org/10.1177/0539018405058216
8. Bradley, M. M., & Lang, P. J. (1994). Measuring emotion: The self-assessment manikin and the semantic differential. *Journal of Behavior Therapy and Experimental Psychiatry, 25*(1), 49-59. https://doi.org/10.1016/0005-7916(94)90063-9
9. Kuppens, P., Allen, N. B., & Sheeber, L. B. (2010). Emotional inertia and psychological maladjustment. *Psychological Science, 21*(7), 984-991. https://doi.org/10.1177/0956797610372634
10. Kuppens, P., & Verduyn, P. (2015). Looking at emotion regulation through the window of emotion dynamics. *Psychological Inquiry, 26*(1), 72-79. https://doi.org/10.1080/1047840X.2015.960505
11. Picard, R. W. (1997). *Affective Computing*. MIT Press. https://mitpress.mit.edu/9780262161701/affective-computing/
12. W3C. (2014). *Emotion Markup Language EmotionML 1.0*. https://www.w3.org/TR/emotionml/
13. Frijda, N. H. (1987). Emotion, cognitive structure, and action tendency. *Cognition and Emotion, 1*(2), 115-143. https://doi.org/10.1080/02699938708408043
14. Frijda, N. H., Kuipers, P., & ter Schure, E. (1989). Relations among emotion, appraisal, and emotional action readiness. *Journal of Personality and Social Psychology, 57*(2), 212-228. https://doi.org/10.1037/0022-3514.57.2.212
15. Roseman, I. J., Wiest, C., & Swartz, T. S. (1994). Phenomenology, behaviors, and goals differentiate discrete emotions. *Journal of Personality and Social Psychology, 67*(2), 206-221. https://doi.org/10.1037/0022-3514.67.2.206
16. Gross, J. J. (1998). The emerging field of emotion regulation: An integrative review. *Review of General Psychology, 2*(3), 271-299. https://doi.org/10.1037/1089-2680.2.3.271
17. Carver, C. S., & Harmon-Jones, E. (2009). Anger is an approach-related affect: Evidence and implications. *Psychological Bulletin, 135*(2), 183-204. https://doi.org/10.1037/a0013965
18. Christensen, A., & Heavey, C. L. (1990). Gender and social structure in the demand/withdraw pattern of marital conflict. *Journal of Personality and Social Psychology, 59*(1), 73-81. https://doi.org/10.1037/0022-3514.59.1.73
19. Williams, K. D., Shore, W. J., & Grahe, J. E. (1998). The silent treatment: Perceptions of its behaviors and associated feelings. *Group Processes & Intergroup Relations, 1*(2), 117-141. https://doi.org/10.1177/1368430298012002
20. Williams, K. D. (2009). Ostracism: A temporal need-threat model. *Advances in Experimental Social Psychology, 41*, 275-314. https://doi.org/10.1016/S0065-2601(08)00406-1

## AstrBot API 依据

- 插件入口、指令与事件钩子参考 AstrBot 插件开发文档。
- LLM 调用参考 `context.llm_generate()`。
- 动态上下文注入使用 `ProviderRequest.extra_user_content_parts`。
- 状态持久化使用 AstrBot 插件 KV 存储。
- 插件互调使用 `Context.get_registered_star()` 获取 `StarMetadata`，再通过 `star_cls` 调用已激活插件实例。

相关文档：

- https://docs.astrbot.app/zh/dev/star/guides/simple.html
- https://docs.astrbot.app/zh/dev/star/guides/ai.html
- https://docs.astrbot.app/zh/dev/star/guides/plugin-config.html
- https://docs.astrbot.app/zh/dev/star/guides/storage.html
- https://docs.astrbot.app/dev/star/resources/context.html
- https://docs.astrbot.app/dev/star/resources/star_metadata.html
