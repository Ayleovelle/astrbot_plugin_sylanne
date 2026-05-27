"""旧版数据导入器模块。

将 Sylanne 3.x 时代的多模块状态（emotion/lifelike/memory/relationship/repair）
迁移为 Sylanne-Embodiment 统一的 AlphaBodyState 身体向量。

迁移策略：
- 若 data 中已包含 "body" 字段，说明已是 4.0 格式，直接反序列化
- 否则从 3.x 各子模块的 values/dynamics 字段中提取数值，
  通过启发式映射填充 29 维身体向量的初始值
- 同时保留原始 legacy payload 作为审计快照
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .body import AlphaBodyState
from .vector import clamp as _clamp


def import_legacy_body(
    data: Mapping[str, Any] | None,
) -> tuple[AlphaBodyState, dict[str, Any], int]:
    """将旧版 3.x 持久化数据迁移为 AlphaBodyState。

    Args:
        data: 旧版持久化字典，可能包含 emotion/lifelike/memory/relationship/repair 子模块

    Returns:
        三元组 (body, audit, turns):
        - body: 迁移后的 AlphaBodyState 实例
        - audit: 审计信息字典（保留原始 legacy payload 或已有 audit）
        - turns: 历史对话轮次数
    """
    body = AlphaBodyState()
    if not isinstance(data, Mapping):
        return body, {}, 0

    # 快速路径：已经是当前格式，直接反序列化
    if isinstance(data.get("body"), Mapping):
        body = AlphaBodyState.from_dict(dict(data["body"]))
        return (
            body,
            _audit_from_snapshot(data),
            max(0, int(_number(data.get("turns"), 0))),
        )

    # 慢路径：从 3.x 多模块结构中提取数据并映射到身体向量
    emotion = _mapping(data.get("emotion") or data.get("emotion_state"))
    lifelike = _mapping(data.get("lifelike") or data.get("lifelike_learning"))
    memory = _mapping(data.get("memory") or data.get("memory_state"))
    relationship = _mapping(
        data.get("relationship")
        or data.get("relation")
        or data.get("relational")
        or data.get("relationship_state")
    )
    repair = _mapping(
        data.get("repair") or data.get("repair_state") or data.get("moral_repair")
    )
    # 合并各子模块的 values 和 dynamics 字段为统一查找表
    values = dict(_mapping(emotion.get("values")))
    values.update(_mapping(lifelike.get("values")))
    values.update(_mapping(relationship.get("values")))
    dynamics = dict(_mapping(emotion.get("dynamics")))
    dynamics.update(_mapping(lifelike.get("dynamics")))
    dynamics.update(_mapping(relationship.get("dynamics")))
    records = memory.get("records") if isinstance(memory.get("records"), list) else []
    repair_records = (
        repair.get("records") if isinstance(repair.get("records"), list) else []
    )

    # 启发式映射：将旧版 dynamics/values 数值投影到当前身体向量各轴
    # pulse.beat 用历史轮次数近似（越多轮次，心跳累积越高）
    body.pulse.beat = max(
        0.0, _number(dynamics.get("pulse"), _number(data.get("turns"), 0.0))
    )
    body.pulse.last_tick = _number(
        emotion.get("updated_at"), _number(lifelike.get("updated_at"), 0.0)
    )
    body.needs["need_contact"] = _clamp(
        _number(dynamics.get("need_contact"), min(len(records), 10) / 10.0)
    )
    body.needs["need_quiet"] = _clamp(
        _number(dynamics.get("need_quiet"), _number(values.get("arousal"), 0.0) * 0.3)
    )
    body.needs["need_repair"] = _clamp(
        _number(dynamics.get("need_repair"), _number(values.get("hurt"), 0.0))
    )
    body.needs["need_expression"] = _clamp(
        _number(dynamics.get("need_expression"), 0.15 if records else 0.0)
    )
    body.nerve.plasticity = _clamp(
        _number(dynamics.get("plasticity"), min(len(records), 12) / 12.0)
    )
    body.nerve.sensitivity = _clamp(
        _number(
            dynamics.get("trace_strength"),
            _number(values.get("boundary_sensitivity"), 0.0),
        )
    )
    body.nerve.repetition = max(0, int(_number(dynamics.get("repetition"), 0)))
    body.bloodflow.warmth = _clamp(
        _number(
            values.get("closeness"),
            _number(values.get("rapport"), _number(values.get("affiliation"), 0.4)),
        )
    )
    body.bloodflow.memory_flow = _clamp(len(records) / 20.0)
    body.temperature.warmth = _clamp(
        _number(values.get("trust"), _number(values.get("rapport"), 0.45))
    )
    body.temperature.volatility = _clamp(_number(values.get("arousal"), 0.0))
    body.immunity.boundary_pressure = _clamp(
        _number(
            values.get("boundary_sensitivity"), _number(values.get("boundary"), 0.0)
        )
    )
    body.mortality.load = _clamp(
        _number(dynamics.get("load"), _number(values.get("arousal"), 0.0) * 0.25)
    )
    # 记忆迁移：将旧版 records 转为 body.memory.traces 格式
    body.memory = {
        "traces": _memory_traces(records, body.temperature.warmth)
        + _memory_traces(repair_records, body.temperature.warmth)
    }

    # 计算历史轮次数（取各子模块中最大值）
    turns = max(
        0,
        int(
            _number(
                emotion.get("turns"),
                _number(
                    lifelike.get("turns"),
                    _number(memory.get("event_count"), len(records)),
                ),
            ),
        ),
    )
    return (
        body,
        {
            # 保留原始 3.x 数据作为审计快照，便于回溯迁移问题
            "legacy_payloads": {
                "emotion": deepcopy(dict(emotion)),
                "lifelike": deepcopy(dict(lifelike)),
                "memory": deepcopy(dict(memory)),
                "relationship": deepcopy(dict(relationship)),
                "repair": deepcopy(dict(repair)),
            }
        },
        turns,
    )


def _audit_from_snapshot(data: Mapping[str, Any]) -> dict[str, Any]:
    """从已有快照中提取审计信息。"""
    audit = data.get("audit")
    return dict(audit) if isinstance(audit, Mapping) else {}


def _memory_traces(records: list[Any], temperature: float) -> list[dict[str, Any]]:
    """将旧版 memory records 转换为当前 traces 格式。

    只保留最近 50 条记录，每条截断到 500 字符。
    """
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
    """安全地将任意值转为 Mapping，非 Mapping 返回空字典。"""
    return value if isinstance(value, Mapping) else {}


def _number(value: Any, default: float = 0.0) -> float:
    """安全地将任意值转为 float，转换失败返回默认值。"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)
