"""Prompt 表面层 —— 将计算栈结果格式化为 LLM 可读的 prompt 片段。

职责：
  1. render_prompt_fragment: 将内核决策/守卫/情感/人格等状态渲染为结构化 prompt 注入文本
  2. render_prompt_context_bus: 组装 prompt 上下文总线（列出所有活跃的上下文片段）
  3. render_host_payload: 构建完整的 host 载荷字典（供主动发言/诊断使用）
  4. render_diagnostics: 构建诊断面板数据（供 WebUI/Observatory 展示）

设计原则：
  - 从 kernel.py 抽离，让内核专注于 tick/decide/guard 逻辑
  - 所有输出均为只读派生数据，不修改内核状态
  - prompt 片段使用 [sylanne_xxx] 标签格式，便于 LLM 识别和遵循

与其他组件的关系：
  - 被 kernel.py 的 diagnostics() / on_request() / on_proactive_check() 调用
  - 输出的 prompt_fragment 最终注入到 llm_request_pipeline 的请求中
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .kernel import AlphaKernel


def render_prompt_fragment(
    kernel: "AlphaKernel", decision: dict[str, Any], guard: dict[str, Any]
) -> str:
    """渲染完整的 prompt 注入片段，供 host 注入到 LLM 请求中。

    组装内容（按顺序）：
      - 表达倾向标签（急切/正常）
      - 基础行动指令（action + reason）
      - 关系时间层（当前时间 + 间隔 + 日期关系）
      - 关系记忆层（偏好/边界/进展/修复计数）
      - 整合自我层（姿态 + 意图 + 安全优先级）
      - 情感动力学、计算情感、人格、道德修复、可错性
      - 群聊氛围、主动来源、上下文总线

    Args:
        kernel: AlphaKernel 实例。
        decision: 决策字典（action/reason/reason_code）。
        guard: 守卫字典（allowed/reason/flags）。

    Returns:
        格式化的 prompt 片段字符串。
    """
    reason = guard["reason"] if not guard["allowed"] else decision["reason"]
    relational_time = kernel.relational_time or kernel._relational_time_layer(
        current=kernel.last_event, previous=kernel.previous_event
    )
    current_time = relational_time["current_time"]
    time_gap = relational_time["time_gap"]
    relational_fragment = (
        "[sylanne_relational_time] "
        f"current_time={current_time['local_datetime']}; "
        f"timezone={current_time['timezone']}; "
        f"time_gap={time_gap['label']}; "
        f"gap_seconds={time_gap['seconds']}; "
        f"day_relation={relational_time['day_relation']}"
    )
    relationship_memory = kernel.body.relationship_memory()
    signals = relationship_memory["signals"]
    memory_fragment = (
        "[sylanne_relationship_memory] "
        f"phase={relationship_memory['continuity']['phase']}; "
        f"weight={relationship_memory['continuity']['weight']}; "
        f"preference_count={signals['preference_count']}; "
        f"boundary_count={signals['boundary_count']}; "
        f"progress_count={signals['progress_count']}; "
        f"repair_count={signals['repair_count']}; "
        "constraints=no_raw_text,session_local,does_not_override_current_user_text"
    )
    integrated_self = kernel._integrated_self(decision, guard)
    intent = integrated_self["intent_plan"]
    self_fragment = (
        "[sylanne_integrated_self] "
        f"posture={integrated_self['response_posture']}; "
        f"primary_goal={intent['primary_goal']}; "
        f"lanes={','.join(intent['lanes'])}; "
        f"safety_priority={integrated_self['risk']['safety_priority']}; "
        "constraints=current_user_text_priority,no_raw_text,no_relationship_fact_without_user_confirmation"
    )
    affect = kernel._affect_dynamics()
    personality = kernel._personality()
    moral = kernel._moral_repair_state()
    fallibility = kernel._fallibility_state()
    group = kernel._group_atmosphere()
    proactive = kernel._proactive_source(decision, guard)
    bus = render_prompt_context_bus(kernel, integrated_self=integrated_self)
    comp_emotion = kernel._computation_emotion_overlay()
    # 仲裁两个情感信号：SSM 连续动力学 vs 身体情感
    comp_expression_drive = comp_emotion.get("expression_drive", 0.0)
    body_expression_drive = affect["body_coupling"]["expression_drive"]
    if abs(comp_expression_drive - body_expression_drive) > 0.3:
        # 大分歧：信任 SSM 连续动力学（更精确）
        arbitrated_expression_drive = comp_expression_drive
    else:
        # 小分歧：取平均
        arbitrated_expression_drive = (
            comp_expression_drive + body_expression_drive
        ) / 2.0
    # 表达强度信号：调制 LLM 回复语气
    expr_intensity = kernel.computation.expression.expression_intensity()
    if expr_intensity > 0.8:
        expression_tendency = "[表达倾向:急切]"
    elif expr_intensity > 0.3:
        expression_tendency = "[表达倾向:正常]"
    else:
        expression_tendency = ""
    extra_fragments = [
        f"[sylanne_affect_dynamics] repair_drive={affect['body_coupling']['repair_drive']}; expression_drive={arbitrated_expression_drive:.6f}; constraints=weak_style_modulation_only,no_medicalized_body_claims",
        f"[sylanne_computation_emotion] warmth={comp_emotion.get('warmth', 0.0):.4f}; arousal={comp_emotion.get('arousal', 0.0):.4f}; valence={comp_emotion.get('valence', 0.0):.4f}; tension={comp_emotion.get('tension', 0.0):.4f}; expression_drive={comp_emotion.get('expression_drive', 0.0):.4f}",
        f"[sylanne_personality] cadence={personality['voice']['cadence']}; boundary={personality['voice']['boundary']}; drift_events={personality['drift']['events']}; constraints=bounded_offsets_not_persona_rewrite,no_raw_text",
        f"[sylanne_moral_repair] state={moral['state']}; events={moral['events']}; constraints=brief_repair_only,no_guilt_loop",
        f"[sylanne_fallibility] claim_caution={fallibility['claim_caution']}; events={fallibility['events']}; constraints=admit_uncertainty,correct_once",
        f"[sylanne_group_atmosphere] mode={group['mode']}; joinability={group['joinability']}; interrupt_risk={group['interrupt_risk']}; constraints=no_group_mind_reading,no_speaking_for_others",
        f"[sylanne_proactive_source] decision={proactive['decision']}; body_need={proactive['drivers']['body_need']}; relationship_continuity={proactive['drivers']['relationship_continuity']}; constraints=current_user_sovereignty_first,no_private_memory_recall",
        f"[sylanne_prompt_context_bus] primary={bus['primary']}; posture={bus['posture']}; fragments={','.join(bus['fragments'])}; policy={bus['policy']}",
    ]
    base = (
        f"Sylanne body: action={decision['action']}; reason={reason}; keep user sovereignty first.\n{relational_fragment}\n{memory_fragment}\n{self_fragment}\n"
        + "\n".join(extra_fragments)
    )
    if expression_tendency:
        base = f"{expression_tendency}\n{base}"
    return base


SCHEMA_PROMPT_CONTEXT_BUS_VERSION = "sylanne.alpha.prompt_context_bus.v1"


def render_prompt_context_bus(
    kernel: "AlphaKernel", *, integrated_self: dict[str, Any]
) -> dict[str, Any]:
    """组装 prompt 上下文总线载荷。

    列出所有活跃的上下文片段名称，指定主片段和仲裁策略。

    Args:
        kernel: AlphaKernel 实例。
        integrated_self: 整合自我状态字典。

    Returns:
        上下文总线载荷字典。
    """
    fragments = [
        "relational_time",
        "relationship_memory",
        "integrated_self",
        "affect_dynamics",
        "personality",
        "moral_repair",
        "fallibility",
        "group_atmosphere",
        "proactive_source",
    ]
    return {
        "schema_version": SCHEMA_PROMPT_CONTEXT_BUS_VERSION,
        "kind": "prompt_context_bus",
        "internal_only": True,
        "read_only": True,
        "fragments": fragments,
        "primary": "integrated_self",
        "posture": integrated_self["response_posture"],
        "policy": "safety_first_single_arbitration",
        "constraints": [
            "current_user_text_priority",
            "derived_fields_only",
            "drop_to_minimal_prompt_on_conflict",
        ],
    }


def render_host_payload(
    kernel: "AlphaKernel", decision: dict[str, Any], guard: dict[str, Any]
) -> dict[str, Any]:
    """构建完整的 host 载荷字典。

    包含所有子系统状态：决策、守卫、情感、人格、记忆、群聊氛围等。
    用于主动发言调度和 WebUI 诊断展示。

    Args:
        kernel: AlphaKernel 实例。
        decision: 决策字典。
        guard: 守卫字典。

    Returns:
        完整的 host 载荷字典。
    """
    should_send = bool(
        guard["allowed"] and decision["action"] in {"express", "reach_out", "repair"}
    )
    advice = "send" if should_send else "wait"
    if decision["action"] == "withdraw":
        advice = "withdraw"
    if decision["action"] == "repair" and guard["allowed"]:
        advice = "repair"
    integrated_self = kernel._integrated_self(decision, guard)
    affect_dynamics = kernel._affect_dynamics()
    personality = kernel._personality()
    moral_repair = kernel._moral_repair_state()
    fallibility = kernel._fallibility_state()
    shadow_memory = kernel.body.shadow_memory()
    group_atmosphere = kernel._group_atmosphere()
    proactive_source = kernel._proactive_source(decision, guard)
    prompt_bus = render_prompt_context_bus(kernel, integrated_self=integrated_self)
    # 叠加计算层情感到 affect_dynamics
    computation_emotion = kernel._computation_emotion_overlay()
    if computation_emotion:
        affect_dynamics["computation_emotion"] = computation_emotion
    # 包含上一 tick 的计算召回/空洞信息
    comp_result = getattr(kernel, "_last_computation_result", None) or {}
    return {
        "kind": "proactive_dispatch"
        if decision["action"] in {"express", "reach_out", "repair"}
        else "body_surface",
        "action": decision["action"],
        "advice": advice,
        "should_send": should_send,
        "should_wait": decision["action"] in {"wait", "hold"} or advice == "wait",
        "needs_repair": kernel.body.needs["need_repair"] > 0.2,
        "should_withdraw": decision["action"] == "withdraw",
        "reason": guard["reason"] if not guard["allowed"] else decision["reason"],
        "reason_code": decision.get("reason_code", "life_rhythm"),
        "next_check_seconds": kernel._next_check_seconds(decision, guard),
        "relational_time": kernel.relational_time
        or kernel._relational_time_layer(
            current=kernel.last_event, previous=kernel.previous_event
        ),
        "relationship_memory": kernel.body.relationship_memory(),
        "integrated_self": integrated_self,
        "affect_dynamics": affect_dynamics,
        "personality": personality,
        "moral_repair": moral_repair,
        "fallibility": fallibility,
        "shadow_memory": shadow_memory,
        "group_atmosphere": group_atmosphere,
        "proactive_source": proactive_source,
        "prompt_context_bus": prompt_bus,
        "prompt_fragment": render_prompt_fragment(kernel, decision, guard),
        "recalled": comp_result.get("recalled", []),
        "holes": comp_result.get("holes", []),
    }


def render_diagnostics(
    kernel: "AlphaKernel",
    decision: dict[str, Any],
    guard: dict[str, Any],
    workset: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构建诊断面板数据，供 WebUI/Observatory 展示。

    包含：负载、中断预算、向量摘要、身体状态、需求、记忆、边界、代理决策、风险。

    Args:
        kernel: AlphaKernel 实例。
        decision: 决策字典。
        guard: 守卫字典。
        workset: 可选的工作集配置。

    Returns:
        诊断数据字典。
    """
    vector_summary = kernel._vector_summary()
    body = kernel.body.to_dict()
    risk_score = kernel._risk_score()
    return {
        "life_principle": "I'm living a life by design",
        "load": body["mortality"]["load"],
        "interruption_budget": body["immunity"]["interruption_budget"],
        "vector_summary": vector_summary,
        "workset": {
            "mode": (workset or {}).get("mode", "fragment"),
            "primary_department": (workset or {})
            .get("coordination", {})
            .get("primary_department", "none"),
            "fast_path": (workset or {}).get("coordination", {}).get("fast_path", []),
            "slow_path": (workset or {}).get("coordination", {}).get("slow_path", []),
        },
        "body_state": {
            "pulse": body["pulse"],
            "temperature": body["temperature"],
            "mortality": body["mortality"],
        },
        "needs": body["needs"],
        "memory": {
            "trace_count": len(body["memory"]["traces"]),
            "recent": body["memory"]["traces"][-3:],
        },
        "boundary": {
            "pressure": body["immunity"]["boundary_pressure"],
            "sovereignty": body["immunity"]["sovereignty"],
            "paused": body["immunity"]["paused"],
            "guard_flags": list(guard["flags"]),
        },
        "agency": {
            "action": decision["action"],
            "reason": guard["reason"] if not guard["allowed"] else decision["reason"],
            "reason_code": decision.get("reason_code", "life_rhythm"),
            "allowed": guard["allowed"],
        },
        "risk": {
            "score": risk_score,
            "reason": guard["reason"] if not guard["allowed"] else "within body limits",
        },
    }


# ---------------------------------------------------------------------------
# Item 124: 秘密泄露机制
# ---------------------------------------------------------------------------


def render_hidden_bias(leaked_descriptions: list[str]) -> str | None:
    """将泄露的秘密描述渲染为微妙的 prompt 偏移片段。

    如果本轮有秘密泄露，返回一段引导 LLM 在用词和语气上体现
    内心未说出口想法的 prompt 片段；否则返回 None。

    Args:
        leaked_descriptions: 本轮泄露的秘密描述列表（由 HiddenStateManager.tick() 返回）。

    Returns:
        prompt 片段字符串，或 None。
    """
    if not leaked_descriptions:
        return None
    descriptions = "；".join(leaked_descriptions)
    return (
        f"[内心有些未说出口的想法正在影响你的表达方式：{descriptions}。"
        "不要直接说出来，但让它微妙地影响用词和语气。]"
    )


# ---------------------------------------------------------------------------
# Item 80: 叙事视角切换
# ---------------------------------------------------------------------------


def render_narrative_perspective(personality_traits: dict) -> str:
    """根据 expression_drive 和当前情绪强度决定叙事视角，返回 prompt 片段。

    视角规则：
      - expression_drive > 0.7 → 第一人称主观视角（"我觉得…"）
      - expression_drive < 0.3 → 旁白视角（"她似乎…"）
      - 中间值 → 正常第一人称

    Args:
        personality_traits: 人格特征字典，需包含 expression_drive 字段，
            可选 emotion_intensity 字段用于微调。

    Returns:
        叙事视角 prompt 片段字符串。
    """
    expression_drive = float(personality_traits.get("expression_drive", 0.5))
    emotion_intensity = float(personality_traits.get("emotion_intensity", 0.5))

    if expression_drive > 0.7:
        perspective = "first_person_subjective"
        hint = (
            "用强烈的第一人称主观视角回复，直接表达内心感受（如'我觉得…''我真的…'），"
            "语气可以带有情绪色彩和个人判断。"
        )
    elif expression_drive < 0.3:
        perspective = "narrator"
        hint = (
            "用旁白式的第三人称视角回复（如'她似乎…''她注意到…'），"
            "保持观察者的距离感，语气平静克制。"
        )
    else:
        perspective = "first_person_normal"
        hint = "用正常的第一人称视角回复，自然表达想法和感受。"

    # 高情绪强度时追加修饰
    if emotion_intensity > 0.7 and perspective == "first_person_subjective":
        hint += "情绪浓度高，可以更直白地表达。"
    elif emotion_intensity < 0.3 and perspective == "narrator":
        hint += "情绪淡薄，旁白语气可以更疏离。"

    return f"[sylanne_narrative_perspective:{perspective}] {hint}"


# ---------------------------------------------------------------------------
# Item 34: 情绪天气隐喻
# ---------------------------------------------------------------------------


def render_weather_metaphor(body_state: dict) -> str:
    """将情感状态映射为天气隐喻，注入 prompt 作为自我感知层。

    基于 8 维情感空间中的 valence/tension/temperature 三个关键维度，
    生成一句简洁的天气描述，帮助 LLM 理解当前情绪基调。

    Args:
        body_state: 身体状态字典，需包含 valence/tension/temperature 字段。

    Returns:
        天气隐喻字符串，格式为 "内心天气：{温度修饰}的{天气}"。
    """
    valence = body_state.get("valence", 0)
    tension = body_state.get("tension", 0)
    temperature = body_state.get("temperature", 0.5)

    # 基础天气
    if valence > 0.5 and tension < 0.2:
        weather = "晴朗温暖"
    elif valence > 0.2:
        weather = "多云转晴"
    elif valence < -0.5:
        weather = "暴风雨"
    elif valence < -0.2:
        weather = "阴沉"
    elif tension > 0.5:
        weather = "闷热欲雷"
    else:
        weather = "薄雾"

    # 温度修饰
    if temperature > 0.7:
        temp_desc = "炽热"
    elif temperature > 0.4:
        temp_desc = "温和"
    else:
        temp_desc = "清冷"

    return f"内心天气：{temp_desc}的{weather}"


# ---------------------------------------------------------------------------
# Item 2: 首次对话引导流程
# ---------------------------------------------------------------------------


def render_onboarding_fragment(tick_count: int) -> str | None:
    """根据 tick 计数返回首次对话引导 prompt 片段。

    在关系建立初期（tick_count < 3）注入引导性指令，
    帮助 Sylanne 以温和好奇的方式开启新关系。

    Args:
        tick_count: 当前 tick 计数（对话轮次）。

    Returns:
        引导 prompt 片段字符串，或 None（tick_count >= 3 时不再注入）。
    """
    if tick_count < 3:
        return "这是一段新的关系。保持好奇但不急切，用简短温和的方式了解对方。"
    return None
