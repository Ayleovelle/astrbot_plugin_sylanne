from __future__ import annotations

from typing import Any


_TECHNICAL_MARKERS = (
    "提交", "commit", "release", "版本", "测试", "报错", "修复", "文件", "代码", "打包", "github", "git",
)


def choose_expression_policy(
    *,
    current_user_text: str,
    interpretation_candidates: list[dict[str, Any]],
    is_user_correction: bool,
    is_low_signal: bool,
) -> dict[str, Any]:
    text = str(current_user_text or "").lower()
    reasons: list[str] = []
    if is_low_signal:
        return {"posture": "silent_or_minimal", "verbosity": "minimal", "reasons": ["low_signal_turn"]}
    if is_user_correction:
        return {"posture": "clarify", "verbosity": "brief", "reasons": ["user_correction_priority"]}
    if any(float(item.get("confidence") or 0.0) < 0.55 for item in interpretation_candidates):
        return {"posture": "clarify", "verbosity": "brief", "reasons": ["low_confidence_interpretation"]}
    if any(marker in text for marker in _TECHNICAL_MARKERS):
        reasons.append("technical_or_workflow_request")
        return {"posture": "tool_like", "verbosity": "brief", "reasons": reasons}
    if any(str(item.get("kind") or "") in {"homophone", "joke", "slang"} for item in interpretation_candidates):
        return {"posture": "playful", "verbosity": "short", "reasons": ["high_confidence_playful_interpretation"]}
    return {"posture": "brief_answer", "verbosity": "normal", "reasons": ["default_conversational_turn"]}


def build_expression_policy_prompt(policy: dict[str, Any]) -> str:
    posture = str(policy.get("posture") or "brief_answer")
    verbosity = str(policy.get("verbosity") or "normal")
    reasons = ",".join(str(item) for item in policy.get("reasons") or [])
    lines = [
        "[sylanne_expression_policy]",
        f"posture={posture}; verbosity={verbosity}; reasons={reasons}",
        "当前用户原文优先；按姿态选择回复长度和语气，不要每轮都浓烈、撒娇或文学化。",
    ]
    if posture == "clarify":
        lines.append("解释候选不确定时，轻轻确认；不要强行玩梗，也不要把候选当事实。")
    if posture == "tool_like":
        lines.append("本轮优先完成任务，短句说明结果；不要过度情绪化。")
    if posture == "silent_or_minimal":
        lines.append("低信号轮次保持克制，可以短应或先听，不要扩写旧话题。")
    return "\n".join(lines)
