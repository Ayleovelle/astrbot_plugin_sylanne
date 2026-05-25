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
    clean_fragments = [
        " ".join(str(fragment).split())
        for fragment in fragments or []
        if str(fragment).strip()
    ]
    current_intent = " ".join(clean_fragments).strip()
    shadow = dict(shadow or {})
    items: list[dict[str, Any]] = []
    if current_intent:
        items.append(
            {"kind": "current_intent", "text": current_intent[:500], "weight": 1.0}
        )
    if shadow.get("summary"):
        items.append(
            {
                "kind": "shadow_continuity",
                "text": str(shadow["summary"])[:500],
                "weight": 0.85,
            }
        )
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
    items = _dedupe(items)[: max(1, int(max_items))]
    consume_shadow = bool(shadow.get("consume") and shadow.get("summary"))
    evidence = _evidence(
        dialogue=dialogue,
        memory_matches=items,
        personality=personality,
        body=body,
        assessor=assessor,
        guard=guard,
        attention=attention,
    )
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
    departments = [item["department"] for item in evidence]
    primary = str((attention or {}).get("primary") or "")
    if primary not in departments:
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
    if not evidence:
        return "Sylanne blackboard: empty."
    lines = [f"Sylanne blackboard: primary={coordination['primary_department']}"]
    for item in evidence:
        lines.append(f"- {item['department']}[{item['path']}]")
    return "\n".join(lines)


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
    if not items:
        return "Sylanne workset: empty."
    lines = ["Sylanne workset:"]
    for item in items:
        lines.append(f"- {item['kind']}: {item['text']}")
    return "\n".join(lines)


__all__ = ["WORKSET_SCHEMA_VERSION", "build_fragment_workset"]
