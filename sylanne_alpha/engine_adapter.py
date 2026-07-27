"""计算层适配器 —— 把 vendored SylannEngine SDK 的 Surface 翻译成 Sylanne-next
业务层期望的 BodyPort 兼容 surface 契约。

深接入策略：业务层只通过本适配器拿计算结果，不再直穿计算内部。SDK 的 Surface
字段命名与现有不同（needs.expression vs need_expression、boundary.pressure vs
immunity.boundary_pressure 等），本层负责双向翻译，让下游改动最小。

字段映射（已对照 SDK 真实 process 输出核实，非凭文档）：
  SDK state.needs.expression      → body.needs.need_expression
  SDK state.needs.quiet           → body.needs.need_quiet
  SDK state.needs.recovery        → body.needs.need_repair
  SDK state.needs.contact         → body.needs.need_contact (新增)
  SDK state.boundary.pressure     → body.immunity.boundary_pressure
  SDK state.valence.warmth        → body.temperature.warmth
  SDK decision.{action,reason_code,confidence,urgency} → decision.*
  SDK guard.{allowed,reason,risk_score,constraints}    → guard.*
  host_payload.should_send        ← 推导: guard.allowed && action∈SEND_ACTIONS
"""

from __future__ import annotations

from typing import Any

# decision.action 中代表"应该主动发出"的动作集合（用于推导 should_send）。
# 注意：SDK adapter._ACTION_MAP 会把内部 "repair" 输出为 "recover"，故这里用 SDK
# 真实输出的动作名 "recover"（不是 "repair"），否则 repair 意图的 should_send 恒 False。
SEND_ACTIONS = frozenset({"express", "reach_out", "recover"})


def _f(d: Any, *keys: str, default: float = 0.0) -> float:
    """安全地从嵌套 dict 取 float。"""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, {})
    try:
        return float(cur)
    except (TypeError, ValueError):
        return default


def sdk_state_to_body(sdk_state: dict[str, Any]) -> dict[str, Any]:
    """SDK Surface.state → BodyPort body 结构（needs/immunity/temperature）。

    只翻译业务层实际消费的字段（见模块 docstring 映射表）。
    """
    needs = sdk_state.get("needs", {}) if isinstance(sdk_state.get("needs"), dict) else {}
    boundary = sdk_state.get("boundary", {}) if isinstance(sdk_state.get("boundary"), dict) else {}
    valence = sdk_state.get("valence", {}) if isinstance(sdk_state.get("valence"), dict) else {}
    connection = sdk_state.get("connection", {}) if isinstance(sdk_state.get("connection"), dict) else {}
    return {
        "needs": {
            "need_expression": _f(needs, "expression"),
            "need_quiet": _f(needs, "quiet"),
            "need_repair": _f(needs, "recovery"),
            "need_contact": _f(needs, "contact"),
        },
        "immunity": {
            "boundary_pressure": _f(boundary, "pressure"),
            "autonomy": _f(boundary, "autonomy", default=1.0),
            "interruption_budget": _f(boundary, "interruption_budget", default=1.0),
            "cooldown": _f(boundary, "cooldown"),
        },
        "temperature": {
            # SDK 有 valence.warmth 与 connection.warmth 两个；business 的
            # "亲密/熟悉感"语义更贴近 connection.warmth（关系温暖），优先用它，
            # 回退 valence.warmth。
            "warmth": _f(connection, "warmth") or _f(valence, "warmth"),
        },
    }


def derive_should_send(decision: dict[str, Any], guard: dict[str, Any]) -> bool:
    """SDK 无 host_payload.should_send，从 guard.allowed + decision.action 推导。"""
    if not isinstance(guard, dict) or guard.get("allowed") is False:
        return False
    action = str((decision or {}).get("action", "")).strip().lower()
    return action in SEND_ACTIONS


def sdk_surface_to_compat(surface: dict[str, Any]) -> dict[str, Any]:
    """SDK Surface → Sylanne-next 业务层兼容 surface。

    产出含：body(旧结构) / decision / guard / host_payload(含推导的 should_send) /
    schema_version / session_key / turns，覆盖现有 proactive/pipeline 消费契约。
    """
    state = surface.get("state", {}) if isinstance(surface.get("state"), dict) else {}
    decision = surface.get("decision", {}) if isinstance(surface.get("decision"), dict) else {}
    guard = surface.get("guard", {}) if isinstance(surface.get("guard"), dict) else {}
    body = sdk_state_to_body(state)
    reason_code = str(decision.get("reason_code", "life_rhythm") or "life_rhythm")
    host_payload = {
        "should_send": derive_should_send(decision, guard),
        "reason_code": reason_code,
        "action": str(decision.get("action", "")),
        "reason": str(decision.get("reason", "")),
    }
    return {
        "schema_version": surface.get("schema_version", ""),
        "session_key": surface.get("session_id", ""),
        "turns": surface.get("turns", 0),
        "body": body,
        "decision": {
            "action": str(decision.get("action", "")),
            "reason_code": reason_code,
            "confidence": _f(decision, "confidence"),
            "urgency": _f(decision, "urgency"),
        },
        "guard": {
            "allowed": bool(guard.get("allowed", True)),
            "reason": str(guard.get("reason", "")),
            "risk_score": _f(guard, "risk_score"),
            "constraints": list(guard.get("constraints", []) or []),
        },
        "host_payload": host_payload,
        # 透传 SDK 原始 surface 供需要新结构的下游用（WebUI 等）
        "sdk_surface": surface,
    }


