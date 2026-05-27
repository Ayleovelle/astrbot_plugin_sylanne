"""工作集（Workset）构建模块。

负责将来自各子系统（对话、记忆、人格、身体状态、评估器、安全守卫、注意力）
的证据碎片聚合为统一的"工作集"数据结构，供 LLM prompt 注入使用。

核心设计：
- 黑板模式（blackboard）：当有多部门证据时，按 fast/slow 路径分组协调
- 碎片模式（fragment）：仅有简单意图碎片时，直接拼接渲染
- 协调策略：fast_path 永远不等待 slow_path（避免阻塞实时响应）
"""

from __future__ import annotations

from typing import Any

WORKSET_SCHEMA_VERSION = "sylanne.alpha.workset.v1"


def build_fragment_workset(
    *,
    session_key: str,
    fragments: list[str] | None = None,
    shadow: dict[str, Any] | None = None,
    memory_matches: list[dict[str, Any]] | None = None,
    max_items: int = 5,
    dialogue: dict[str, Any] | None = None,
    personality: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    assessor: dict[str, Any] | None = None,
    guard: dict[str, Any] | None = None,
    attention: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构建工作集：聚合各子系统证据为统一的 prompt 注入数据结构。

    Args:
        session_key: 会话标识。
        fragments: 当前意图文本碎片列表。
        shadow: 影子连续性数据（上一轮未消费的延续信息）。
        memory_matches: 记忆检索匹配结果列表。
        max_items: 工作集最大条目数。
        dialogue: 对话子系统证据。
        personality: 人格子系统证据。
        body: 身体状态子系统证据。
        assessor: 评估器子系统证据。
        guard: 安全守卫子系统证据。
        attention: 注意力子系统证据。

    Returns:
        工作集字典，包含 items/evidence/coordination/prompt_fragment 等字段。
    """
    # 清洗碎片：去除空白、合并多余空格
    clean_fragments = [
        " ".join(str(fragment).split())
        for fragment in fragments or []
        if str(fragment).strip()
    ]
    current_intent = " ".join(clean_fragments).strip()
    shadow = dict(shadow or {})
    items: list[dict[str, Any]] = []

    # 当前意图权重最高
    if current_intent:
        items.append(
            {"kind": "current_intent", "text": current_intent[:500], "weight": 1.0}
        )
    # 影子连续性：上一轮的延续摘要，权重略低
    if shadow.get("summary"):
        items.append(
            {
                "kind": "shadow_continuity",
                "text": str(shadow["summary"])[:500],
                "weight": 0.85,
            }
        )
    # 记忆匹配：按权重降序排列加入
    for match in sorted(
        memory_matches or [],
        key=lambda item: float(item.get("weight") or 0.0),
        reverse=True,
    ):
        text = str(match.get("text") or "").strip()
        if text:
            items.append(
                {
                    "kind": "memory_match",
                    "id": str(match.get("id") or ""),
                    "text": text[:500],
                    "weight": float(match.get("weight") or 0.0),
                }
            )
    # 去重并截断到 max_items
    items = _dedupe(items)[: max(1, int(max_items))]

    # 影子消费策略：consume_once 表示本轮使用后不再保留
    consume_shadow = bool(shadow.get("consume") and shadow.get("summary"))

    # 收集各部门证据，构建黑板
    evidence = _evidence(
        dialogue=dialogue,
        memory_matches=items,
        personality=personality,
        body=body,
        assessor=assessor,
        guard=guard,
        attention=attention,
    )
    # 协调：决定主导部门和 fast/slow 路径分组
    coordination = _coordination(evidence, attention=attention, guard=guard)

    return {
        "schema_version": WORKSET_SCHEMA_VERSION,
        "session_key": session_key,
        "mode": "blackboard" if evidence else "fragment",
        "current_intent": current_intent,
        "items": items,
        "evidence": evidence,
        "coordination": coordination,
        "shadow": {
            "available": bool(shadow.get("summary")),
            "consumed": consume_shadow,
            "policy": "consume_once" if consume_shadow else "preserve",
        },
        # 根据模式选择渲染方式
        "prompt_fragment": _render_blackboard(evidence, coordination)
        if evidence
        else _render(items),
    }


def _evidence(
    *,
    dialogue: dict[str, Any] | None,
    memory_matches: list[dict[str, Any]],
    personality: dict[str, Any] | None,
    body: dict[str, Any] | None,
    assessor: dict[str, Any] | None,
    guard: dict[str, Any] | None,
    attention: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """收集各部门的证据，标注 fast/slow 路径。

    fast 路径：对话、记忆、身体、守卫、注意力（低延迟，可立即获得）
    slow 路径：人格、评估器（需要 LLM 推理，可能有延迟）
    """
    evidence: list[dict[str, Any]] = []
    for department, payload, path in (
        ("dialogue", dialogue, "fast"),
        (
            "memory",
            {"matches": memory_matches, "count": len(memory_matches)}
            if memory_matches
            else None,
            "fast",
        ),
        ("personality", personality, "slow"),
        ("body", body, "fast"),
        ("assessor", assessor, "slow"),
        ("guard", guard, "fast"),
        ("attention", attention, "fast"),
    ):
        if payload:
            evidence.append(
                {
                    "department": department,
                    "path": path,
                    "summary": _truncate_payload_values(payload),
                }
            )
    return evidence


def _coordination(
    evidence: list[dict[str, Any]],
    *,
    attention: dict[str, Any] | None,
    guard: dict[str, Any] | None,
) -> dict[str, Any]:
    """决定协调策略：主导部门、fast/slow 路径分组。

    优先级：attention 指定 > guard 存在 > 第一个部门 > none。
    核心策略：fast_path_never_waits_for_slow_path（实时性优先）。
    """
    departments = [item["department"] for item in evidence]
    primary = str((attention or {}).get("primary") or "")
    if primary not in departments:
        # guard 存在时优先（安全优先），否则取第一个部门
        primary = (
            "guard"
            if guard and "guard" in departments
            else (departments[0] if departments else "none")
        )
    return {
        "primary_department": primary,
        "fast_path": [
            item["department"] for item in evidence if item["path"] == "fast"
        ],
        "slow_path": [
            item["department"] for item in evidence if item["path"] == "slow"
        ],
        "policy": "fast_path_never_waits_for_slow_path",
    }


def _truncate_payload_values(payload: dict[str, Any]) -> dict[str, Any]:
    """递归截断 payload 中的长文本值，防止工作集过大。

    - 字符串截断到 300 字符
    - 列表截断到前 5 项
    - 跳过敏感/大体积字段（raw/prompt/request/response）
    """
    clean: dict[str, Any] = {}
    for key, value in payload.items():
        if key in {"raw", "raw_text", "raw_dialogue", "prompt", "request", "response"}:
            continue
        if isinstance(value, str):
            clean[key] = value[:300]
        elif isinstance(value, dict):
            clean[key] = _truncate_payload_values(value)
        elif isinstance(value, list):
            clean[key] = [
                _truncate_payload_values(item) if isinstance(item, dict) else item
                for item in value[:5]
            ]
        else:
            clean[key] = value
    return clean


def _render_blackboard(
    evidence: list[dict[str, Any]], coordination: dict[str, Any]
) -> str:
    """将黑板模式的证据渲染为 prompt 文本片段。"""
    if not evidence:
        return "Sylanne blackboard: empty."
    lines = [f"Sylanne blackboard: primary={coordination['primary_department']}"]
    for item in evidence:
        lines.append(f"- {item['department']}[{item['path']}]")
    return "\n".join(lines)


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 kind+text 去重，保留首次出现的条目。"""
    seen: set[str] = set()
    deduped = []
    for item in items:
        key = f"{item['kind']}\0{item.get('text', '')}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _render(items: list[dict[str, Any]]) -> str:
    """将碎片模式的条目渲染为 prompt 文本片段。"""
    if not items:
        return "Sylanne workset: empty."
    lines = ["Sylanne workset:"]
    for item in items:
        lines.append(f"- {item['kind']}: {item['text']}")
    return "\n".join(lines)


__all__ = ["WORKSET_SCHEMA_VERSION", "build_fragment_workset"]
