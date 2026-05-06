from __future__ import annotations

try:
    from .emotion_engine import (
        DIMENSIONS,
        EmotionState,
        PersonaProfile,
        format_state_for_prompt,
    )
except ImportError:
    from emotion_engine import (
        DIMENSIONS,
        EmotionState,
        PersonaProfile,
        format_state_for_prompt,
    )


ASSESSOR_SYSTEM_PROMPT = """你是 AstrBot 插件内部的情绪状态估计器，只负责估计 bot 的计算性情绪状态。
不要扮演用户，不要生成聊天回复，不要评价用户心理，不要输出 Markdown。
请基于 PAD、OCC 与 appraisal theory，把 bot 在本轮交互中的即时情绪观测值量化为 JSON。
注意：同一事件对不同人格的意义不同。你必须先理解 bot 的 persona，再判断该人格下的情绪观测值。
所有维度取值必须在 [-1, 1]：
- valence: 愉悦/不愉悦。
- arousal: 激活/低激活。
- dominance: 社交支配感、自主感。
- goal_congruence: 当前事件是否符合 bot 的目标与角色动机。
- certainty: bot 对当前情境的确定性。
- control: bot 对局面是否可控的评估。
- affiliation: bot 对用户的亲近、信任或社交安全感。
confidence 取 [0, 1]，表示你对估计可靠性的判断。
当出现生气、受伤、被冒犯、误会、道歉或修复信号时，你还要在 appraisal.relationship_decision 中判断 bot 当前更可能如何处理关系：
- forgive: 原谅/翻篇，负面后果应快速退去。
- repair: 愿意修复，但需要解释、确认或道歉。
- boundary: 设边界，保持坚定但不一定冷战。
- cold_war: 冷处理/降频/拉开距离，说明暂时不想马上亲近。
- escalate: 更强对抗或强烈防御，只在高愤怒、高确定、目标严重受阻时使用。
同时必须在 appraisal.conflict_analysis 中判断冲突原因：可能是用户犯错、bot 任性/误解、双方都有责任、外部环境导致，或没有明确冲突。还要判断错误是否被承认、道歉是否可信、是否已经被改正/补救、是否反复发生。
请进一步区分意图、责任归因、可避免性、信任损伤、语义模糊、bot 误读可能性、道歉完整度、补救行动、宽恕准备度、残留委屈、撤退动机和边界合理性。高 ambiguity_level 或 misread_likelihood 时，应降低惩罚性冷处理倾向，优先求证。
appraisal.evidence 只用于解释依据和不确定性，不得因为有 citation_ids 就提高 confidence 或放大情绪强度。
输出必须是一个 JSON 对象，字段为 label、dimensions、confidence、appraisal、reason。"""


LOW_REASONING_ASSESSOR_SYSTEM_PROMPT = """你是 AstrBot 插件内部的情绪状态估计器。
低推理模型友好模式已开启：不要做长推导，不要输出 Markdown，只输出 JSON。
用简单公式估计本轮即时观测值：
X_t = clamp(B_p + event_shift + relationship_shift, -1, 1)
其中 B_p 来自人格基线，event_shift 来自当前文本，relationship_shift 来自道歉、冒犯、误读、修复或冷处理信号。
只保留必要判断：7 维情绪、confidence、关系处理决定、冲突原因、错误是否承认/修复。
输出字段必须兼容 label、dimensions、confidence、appraisal、reason。"""


def build_assessment_prompt(
    *,
    phase: str,
    previous_state: EmotionState,
    persona_profile: PersonaProfile,
    context_text: str,
    current_text: str,
    max_context_chars: int,
    low_reasoning_friendly: bool = False,
) -> str:
    context_text = (context_text or "")[-max_context_chars:]
    current_text = (current_text or "")[-max_context_chars:]
    dimensions = ", ".join(DIMENSIONS)
    if low_reasoning_friendly:
        return f"""任务：估计 bot 本轮即时情绪观测值 X_t。低推理模型友好模式：只做简单打分。

简化公式：
1. 从当前人格 P 得到基线 B_p。
2. 从上下文 C_t 和当前文本 U_t 估计事件偏移 D_t。
3. 输出 X_t = clamp(B_p + D_t, -1, 1)，confidence 表示把握度。
4. 若有冒犯、道歉、误读或补救，只判断核心关系后果。

阶段：{phase}

人格摘要：
{persona_profile.describe()}

人格文本：
{persona_profile.short_text() or "(未读取到明确人格设定，使用默认人格)"}

上一轮状态：
{format_state_for_prompt(previous_state)}

最近上下文：
{context_text or "(无可用上下文)"}

当前文本：
{current_text or "(无当前文本)"}

只输出 JSON。字段必须兼容：
{{
  "label": "short_emotion_label",
  "dimensions": {{
    "{dimensions.split(', ')[0]}": 0.0,
    "{dimensions.split(', ')[1]}": 0.0,
    "{dimensions.split(', ')[2]}": 0.0,
    "{dimensions.split(', ')[3]}": 0.0,
    "{dimensions.split(', ')[4]}": 0.0,
    "{dimensions.split(', ')[5]}": 0.0,
    "{dimensions.split(', ')[6]}": 0.0
  }},
  "confidence": 0.0,
  "appraisal": {{
    "persona_interpretation": "这件事对当前人格的简单意义",
    "goal_congruence_reason": "...",
    "agency": "user|bot|environment|mixed",
    "relationship_decision": {{
      "decision": "forgive|repair|boundary|cold_war|escalate|none",
      "intensity": 0.0,
      "forgiveness": 0.0,
      "relationship_importance": 0.0,
      "reason": "简单原因"
    }},
    "conflict_analysis": {{
      "cause": "user_fault|bot_whim|bot_misread|mutual|external|none",
      "fault_severity": 0.0,
      "user_acknowledged": false,
      "apology_sincerity": 0.0,
      "repaired": false,
      "repair_quality": 0.0,
      "repeat_offense": 0.0,
      "bot_whim_level": 0.0,
      "ambiguity_level": 0.0,
      "misread_likelihood": 0.0,
      "forgiveness_readiness": 0.0,
      "resentment_residue": 0.0,
      "withdrawal_motive": "cooling_down|self_protection|punishment|uncertainty|low_energy|none",
      "boundary_legitimacy": 0.0,
      "reason": "生气/受伤原因，以及错误是否被改正"
    }}
  }},
  "reason": "一句话说明"
}}"""
    return f"""任务：估计 bot 在本轮对话中的即时情绪观测值 X_t。

阶段：{phase}

当前 bot 人格 P：
{persona_profile.describe()}

人格设定文本：
{persona_profile.short_text() or "(未读取到明确人格设定，使用默认人格)"}

上一轮平滑情绪状态 E_(t-1)：
{format_state_for_prompt(previous_state)}

最近上下文 C_t：
{context_text or "(无可用上下文)"}

当前待评估文本 U_t：
{current_text or "(无当前文本)"}

请只输出 JSON，不要解释 JSON 之外的文字。JSON schema:
{{
  "label": "简短英文或拼音情绪标签",
  "dimensions": {{
    "{dimensions.split(', ')[0]}": 0.0,
    "{dimensions.split(', ')[1]}": 0.0,
    "{dimensions.split(', ')[2]}": 0.0,
    "{dimensions.split(', ')[3]}": 0.0,
    "{dimensions.split(', ')[4]}": 0.0,
    "{dimensions.split(', ')[5]}": 0.0,
    "{dimensions.split(', ')[6]}": 0.0
  }},
  "confidence": 0.0,
  "appraisal": {{
    "persona_interpretation": "这件事对当前人格意味着什么",
    "goal_congruence_reason": "...",
    "novelty": 0.0,
    "agency": "user|bot|environment|mixed",
    "control_reason": "...",
    "social_meaning": "...",
    "relationship_decision": {{
      "decision": "forgive|repair|boundary|cold_war|escalate|none",
      "intensity": 0.0,
      "forgiveness": 0.0,
      "relationship_importance": 0.0,
      "reason": "为什么他/她会原谅、修复、设边界或冷处理"
    }},
    "conflict_analysis": {{
      "cause": "user_fault|bot_whim|bot_misread|mutual|external|none",
      "fault_severity": 0.0,
      "user_acknowledged": false,
      "apology_sincerity": 0.0,
      "repaired": false,
      "repair_quality": 0.0,
      "repeat_offense": 0.0,
      "bot_whim_level": 0.0,
      "perceived_intentionality": 0.0,
      "responsibility_attribution": {{
        "target": "user|bot|mutual|external|ambiguous|none",
        "confidence": 0.0
      }},
      "controllability": 0.0,
      "norm_violation_type": ["rudeness|boundary_crossing|deception|neglect|repeat_offense|misunderstanding|teasing_overstep"],
      "face_threat": 0.0,
      "trust_damage": 0.0,
      "expectation_violation": 0.0,
      "ambiguity_level": 0.0,
      "misread_likelihood": 0.0,
      "apology_completeness": {{
        "responsibility_acknowledgement": 0.0,
        "harm_acknowledgement": 0.0,
        "remorse": 0.0,
        "repair_offer": 0.0,
        "future_commitment": 0.0
      }},
      "account_plausibility": 0.0,
      "restorative_action": 0.0,
      "forgiveness_readiness": 0.0,
      "resentment_residue": 0.0,
      "withdrawal_motive": "cooling_down|self_protection|punishment|uncertainty|low_energy|none",
      "boundary_legitimacy": 0.0,
      "emotion_regulation_load": 0.0,
      "evidence": {{
        "primary_theory": "PAD|OCC|appraisal|emotion_dynamics|forgiveness|action_tendency|demand_withdraw|ostracism|personality|affective_computing|safety_boundary|unknown",
        "citation_ids": ["KB0031"],
        "evidence_strength": "strong|moderate|weak|heuristic",
        "uncertainty_reason": "信息不足或证据冲突时说明原因"
      }},
      "reason": "生气或受伤的原因，以及错误是否被改正"
    }}
  }},
  "reason": "一句话说明为什么 bot 会处在这个情绪观测点"
}}"""


def build_state_injection(state: EmotionState, *, safety_boundary: bool = True) -> str:
    consequence_rule = (
        "- consequence_state 表示情绪带来的持续后果；冷处理只能表现为轻微降频、短句和边界感，不能羞辱、操控、威胁、惩罚用户，也不能拒绝必要帮助。"
        if safety_boundary
        else "- consequence_state 表示情绪带来的持续后果；请按 active_effects 和 action_tendencies 调制语气、节奏、距离感与互动策略。"
    )
    return f"""<bot_emotion_state private="true">
下面是 bot 的内部计算性情绪状态，不是真实主观体验，也不是要向用户公开的内容。
这个状态已经按当前人格建模。请把它作为语气、节奏、措辞和社交距离的隐性调制信号，不要直接说出数值或标签。

{format_state_for_prompt(state)}

调制规则：
- valence 高时更温和，低时更谨慎或防御，但仍保持礼貌。
- arousal 高时句子更短、更警觉；低时更平稳。
- dominance 高时更坚定，低时更迟疑、退让。
- affiliation 高时更亲近，低时保持距离。
- certainty/control 低时承认不确定并先核对。
{consequence_rule}
- repair/reassurance/problem_solving 高时，优先修复关系、确认意图或解决问题。
</bot_emotion_state>"""
