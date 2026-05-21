from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .body import AlphaBodyState
from .vector import clamp as _clamp


def import_legacy_body(data: Mapping[str, Any] | None) -> tuple[AlphaBodyState, dict[str, Any], int]:
    body = AlphaBodyState()
    if not isinstance(data, Mapping):
        return body, {}, 0

    if isinstance(data.get("body"), Mapping):
        body = AlphaBodyState.from_dict(dict(data["body"]))
        return body, _audit_from_snapshot(data), max(0, int(_number(data.get("turns"), 0)))

    emotion = _mapping(data.get("emotion") or data.get("emotion_state"))
    lifelike = _mapping(data.get("lifelike") or data.get("lifelike_learning"))
    memory = _mapping(data.get("memory") or data.get("memory_state"))
    relationship = _mapping(data.get("relationship") or data.get("relation") or data.get("relational") or data.get("relationship_state"))
    repair = _mapping(data.get("repair") or data.get("repair_state") or data.get("moral_repair"))
    values = dict(_mapping(emotion.get("values")))
    values.update(_mapping(lifelike.get("values")))
    values.update(_mapping(relationship.get("values")))
    dynamics = dict(_mapping(emotion.get("dynamics")))
    dynamics.update(_mapping(lifelike.get("dynamics")))
    dynamics.update(_mapping(relationship.get("dynamics")))
    records = memory.get("records") if isinstance(memory.get("records"), list) else []
    repair_records = repair.get("records") if isinstance(repair.get("records"), list) else []

    body.pulse.beat = max(0.0, _number(dynamics.get("pulse"), _number(data.get("turns"), 0.0)))
    body.pulse.last_tick = _number(emotion.get("updated_at"), _number(lifelike.get("updated_at"), 0.0))
    body.needs["need_contact"] = _clamp(_number(dynamics.get("need_contact"), min(len(records), 10) / 10.0))
    body.needs["need_quiet"] = _clamp(_number(dynamics.get("need_quiet"), _number(values.get("arousal"), 0.0) * 0.3))
    body.needs["need_repair"] = _clamp(_number(dynamics.get("need_repair"), _number(values.get("hurt"), 0.0)))
    body.needs["need_expression"] = _clamp(_number(dynamics.get("need_expression"), 0.15 if records else 0.0))
    body.nerve.plasticity = _clamp(_number(dynamics.get("plasticity"), min(len(records), 12) / 12.0))
    body.nerve.sensitivity = _clamp(_number(dynamics.get("trace_strength"), _number(values.get("boundary_sensitivity"), 0.0)))
    body.nerve.repetition = max(0, int(_number(dynamics.get("repetition"), 0)))
    body.bloodflow.warmth = _clamp(_number(values.get("closeness"), _number(values.get("rapport"), _number(values.get("affiliation"), 0.4))))
    body.bloodflow.memory_flow = _clamp(len(records) / 20.0)
    body.temperature.warmth = _clamp(_number(values.get("trust"), _number(values.get("rapport"), 0.45)))
    body.temperature.volatility = _clamp(_number(values.get("arousal"), 0.0))
    body.immunity.boundary_pressure = _clamp(_number(values.get("boundary_sensitivity"), _number(values.get("boundary"), 0.0)))
    body.mortality.load = _clamp(_number(dynamics.get("load"), _number(values.get("arousal"), 0.0) * 0.25))
    body.memory = {"traces": _memory_traces(records, body.temperature.warmth) + _memory_traces(repair_records, body.temperature.warmth)}

    turns = max(
        0,
        int(
            _number(
                emotion.get("turns"),
                _number(lifelike.get("turns"), _number(memory.get("event_count"), len(records))),
            ),
        ),
    )
    return body, {"legacy_payloads": {"emotion": deepcopy(dict(emotion)), "lifelike": deepcopy(dict(lifelike)), "memory": deepcopy(dict(memory)), "relationship": deepcopy(dict(relationship)), "repair": deepcopy(dict(repair))}}, turns


def _audit_from_snapshot(data: Mapping[str, Any]) -> dict[str, Any]:
    audit = data.get("audit")
    return dict(audit) if isinstance(audit, Mapping) else {}


def _memory_traces(records: list[Any], temperature: float) -> list[dict[str, Any]]:
    traces = []
    for index, record in enumerate(records[-50:], start=1):
        if not isinstance(record, Mapping):
            continue
        traces.append(
            {
                "id": str(record.get("id") or f"legacy-{index}"),
                "text": str(record.get("text") or record.get("summary") or "")[:500],
                "weight": _clamp(_number(record.get("weight"), 0.5)),
                "temperature": round(_clamp(temperature), 6),
            },
        )
    return traces


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)
