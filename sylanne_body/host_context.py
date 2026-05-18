from __future__ import annotations

from collections.abc import Callable
from typing import Any


def build_interpretation_candidates_context(
    candidates: list[dict[str, Any]],
    *,
    memory_gate_classifier: Callable[[dict[str, Any]], dict[str, Any]],
    head_one_line: Callable[[str, int], str],
) -> str:
    if not candidates:
        return ""
    lines = [
        "[sylanne_interpretation_candidates]",
        "以下是错别字、谐音、黑话或昵称的候选解释；不覆盖用户原文，不确定时应轻轻确认。",
    ]
    for item in candidates[:3]:
        gate = memory_gate_classifier(item)
        lines.append(
            "raw_text={raw}; candidate={candidate}; kind={kind}; confidence={confidence}; humor={humor}; memory_layer={layer}".format(
                raw=head_one_line(str(item.get("raw_text") or ""), 60),
                candidate=head_one_line(str(item.get("candidate") or ""), 60),
                kind=str(item.get("kind") or "uncertain"),
                confidence=item.get("confidence"),
                humor=item.get("humor_likelihood"),
                layer=str(gate.get("layer") or "uncertain_interpretation"),
            ),
        )
    return "\n".join(lines)
