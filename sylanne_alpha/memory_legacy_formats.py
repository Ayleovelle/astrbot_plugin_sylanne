"""MEM-01：记忆历史格式的只读、最小化解析与归一化工具。

背景（红队审计 finding）：`state_persistence.py::load_sylanne_memory_state` 的
legacy 分支曾经 `from memory_engine import SylanneMemoryState`——`memory_engine`
模块早已从仓库移除（3.x 引擎已归档到 `archive/3x_engines/memory_engine.py`，见
26d7423），这条 import 必炸 ImportError，被外层 `except Exception` 静默吞掉，
效果等价于"遇到旧版存档直接放弃、当没有记忆"。但 CHANGELOG 证明发布过的历史
版本确实把这个格式写进过用户的 KV 存储（`python -m py_compile ... memory_engine.py`
一路出现到 2.2.0），线上仍可能存在这种格式的真实存量归档。

本模块从 `archive/3x_engines/memory_engine.py`（commit 26d7423）里只挑出
**反序列化**必需的最小子集（不含召回/衰减/embedding 匹配等业务逻辑——那些
本来就不该复活，旧格式的记录只做一次性"读出为通用记忆条目"的迁移读取），
重新实现为一个独立、零依赖 sylanne_core/memory_system 的小模块，供
state_persistence.py 在遇到旧格式时读取，而不是维持一个必炸的死 import。

对外主入口：
  - `is_legacy_sylanne_memory_state(data)`  — 格式嗅探
  - `legacy_state_to_v3_dict(data)`         — 旧格式 -> 当前 MemorySystem.to_dict() 同形状的 dict
  - `normalize_memory_blob(data)`           — 任意已知记忆 blob 形状 -> 当前 dict 形状的统一入口
  - `salvage_memory_system_from_alpha_json(path)` — 绕过 kernel 恢复白名单，直接读裸 .alpha.json
    文件里 body.memory['_memory_system'] 的原始存档（AlphaBodyState.from_dict 只认
    relationship/shadow 两个子键，会静默丢弃 _memory_system/traces——这是【读取】层面的
    补救，不改动 body.py 本身的恢复白名单，风险面最小）。
  - `quarantine_kv_key(safe)`               — quarantine 侧车 KV 键名（与其余 KV 键同一命名习惯）

全程只读、fail-closed：任何解析失败都归为"这条/这份不认识"，从不抛异常到调用方，
从不能把一份看不懂的旧存档误判成"合法的空"。
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any

logger = logging.getLogger("astrbot_plugin_sylanne")

# 旧版 SylanneMemoryState.to_dict() 写入的 schema_version 字面量（3.x 引擎，
# archive/3x_engines/memory_engine.py 原文 PUBLIC_MEMORY_STORE_SCHEMA_VERSION）。
LEGACY_SCHEMA_VERSION = "astrbot.sylanne_memory_state.v1"

# 当前 MemorySystem 序列化的顶层键形状（v2/v3 通用，MEM-01 刻意保持不变）。
_MEMORY_SYSTEM_SHAPE_KEYS = frozenset({"l1", "l2", "l3_nodes", "l3_edges"})


# ---------------------------------------------------------------------------
# 最小数值/文本清洗辅助（独立实现，不依赖 memory_system.py，保持本模块零耦合）
# ---------------------------------------------------------------------------


def _num(value: Any, default: float = 0.0) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return f if math.isfinite(f) else default


def _clamp01(value: Any, default: float = 0.5) -> float:
    return max(0.0, min(1.0, _num(value, default)))


def _clamp_signed(value: Any, default: float = 0.0) -> float:
    return max(-1.0, min(1.0, _num(value, default)))


def _text(value: Any, limit: int = 500) -> str:
    if value is None:
        return ""
    return str(value)[:limit]


def _clean_embedding(raw: Any) -> list[float] | None:
    if not isinstance(raw, (list, tuple)):
        return None
    out: list[float] = []
    for item in raw[:4096]:
        try:
            f = float(item)
        except (TypeError, ValueError):
            continue
        if math.isfinite(f):
            out.append(f)
    return out or None


# ---------------------------------------------------------------------------
# 格式嗅探
# ---------------------------------------------------------------------------


def is_legacy_sylanne_memory_state(data: Any) -> bool:
    """判断是否是旧版 SylanneMemoryState（3.x 引擎）KV 归档。

    识别信号（任一命中即可，容忍字段部分缺失的真实脏数据）：
      - 顶层 schema_version == LEGACY_SCHEMA_VERSION
      - 或存在非空的 "records" 列表（且不具备当前 MemorySystem 的 l1/l2/l3 形状——
        避免把当前格式误判为旧格式；虽然二者字段名不冲突，双重确认更稳妥）。
    """
    if not isinstance(data, dict):
        return False
    if _MEMORY_SYSTEM_SHAPE_KEYS.issubset(data.keys()):
        return False  # 已经是当前 MemorySystem 形状，不是旧格式
    if data.get("schema_version") == LEGACY_SCHEMA_VERSION:
        return True
    records = data.get("records")
    return isinstance(records, list) and len(records) > 0


# ---------------------------------------------------------------------------
# 旧版 MemoryRecord -> 当前 MemoryItem 字典（尽力语义映射，非逐字段复刻）
# ---------------------------------------------------------------------------


def _legacy_record_to_memory_item_dict(record: Any) -> dict[str, Any] | None:
    """把一条旧版 MemoryRecord dict 转换为当前 MemoryItem.from_dict 能接受的字典。

    返回 None 表示这条记录连最基本的文本内容都没有（text 和 summary 都为空），
    判定为不可救、由调用方 quarantine。

    映射是"尽力而为的语义近似"而非逐字段复刻——旧引擎的 depth/confidence/
    emotional_signature 等概念与当前 weight/temperature/importance 不是一一
    对应，这里选择合理的、偏保守的映射（不夸大重要性、不引入不存在的高权重），
    宁可后续被自然衰减淘汰，也不要污染进当前的高权重记忆。
    """
    if not isinstance(record, dict):
        return None
    text = _text(record.get("text") or record.get("summary") or "", 500)
    if not text.strip():
        return None

    emotional_signature = record.get("emotional_signature")
    temperature = 0.0
    if isinstance(emotional_signature, dict) and emotional_signature:
        vals = [_clamp_signed(v) for v in emotional_signature.values()]
        temperature = _clamp_signed(sum(vals) / len(vals) if vals else 0.0)

    depth = _clamp01(record.get("depth"), 0.5)
    confidence = _clamp01(record.get("confidence"), 0.5)
    # weight 下限 0.05：避免一转换进来就因为 weight≈0 被下一次 GC 立刻清掉——
    # 旧记录既然值得迁移，至少给它一次在新系统里被自然评估/衰减的机会。
    weight = max(0.05, depth)
    importance = _clamp01((depth + confidence) / 2.0, 0.5)

    return {
        "id": _text(record.get("memory_id") or "", 40) or None,
        "text": text,
        "weight": weight,
        "temperature": temperature,
        "age_ticks": 0,
        "embedding": _clean_embedding(record.get("semantic_embedding")),
        "created_at": _num(record.get("created_at"), 0.0),
        "source_turns": max(1, int(_num(record.get("evidence_count"), 1))),
        "confirmed": True,  # 旧格式里能落到 records 的都已经是"确认过"的记忆
        "recall_count": max(0, int(_num(record.get("recall_count"), 0))),
        "last_recalled_tick": 0,
        "rewrite_count": 0,
        "source": "dialogue",
        "importance": importance,
        "last_recalled_ts": _num(record.get("last_recalled_at"), 0.0),
        "actr_acc": 1.0,
        "confidence": confidence,
        "privacy_level": "open",  # 旧 dialogue 记忆基线，行为等价于当前 dialogue 默认值
        "life_event_id": "",
    }


def legacy_state_to_v3_dict(data: dict) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """把旧版 SylanneMemoryState dict 转换成当前 MemorySystem.to_dict() 同形状的 dict。

    Returns:
        (v3_shaped_dict, quarantined_raw_records)
        v3_shaped_dict 可以直接喂给 `MemorySystem.create_from_dict()`——转换出的
        条目全部放进 L2（旧格式的 records 本来就代表"已巩固"的记忆，语义上更贴近
        L2 而非未确认的 L1）。quarantined_raw_records 是无法救回的原始记录（供
        调用方写入 quarantine 侧车 KV）。
    """
    records = data.get("records") if isinstance(data, dict) else None
    records = records if isinstance(records, list) else []

    l2_items: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []
    for rec in records:
        converted = _legacy_record_to_memory_item_dict(rec)
        if converted is None:
            quarantined.append(rec if isinstance(rec, dict) else {"_raw": repr(rec)})
            continue
        if not converted.get("id"):
            # 旧记录缺 memory_id：让 MemoryItem 自己在 write_summary 路径生成 id
            # 不适用（这里走的是 from_dict 直接构造），用确定性占位，避免 None 进 JSON。
            import hashlib

            digest = hashlib.sha1(
                f"{converted['text']}|{converted['created_at']}".encode(
                    "utf-8", errors="ignore"
                )
            ).hexdigest()[:12]
            converted["id"] = digest
        l2_items.append(converted)

    v3_dict: dict[str, Any] = {
        "version": "3.0.0",
        "tick": 0,
        "last_consolidation_ts": _num(data.get("updated_at"), 0.0) if isinstance(data, dict) else 0.0,
        "params": {},
        "l1": [],
        "l2": l2_items,
        "l3_nodes": {},
        "l3_edges": [],
        "pending_followups": [],
        # 迁移审计标记：不是 MemorySystem 认识的字段，MemorySystem.from_dict 会
        # 忽略它（纯 additive .get() 兼容），但供人工排查/日志使用。
        "_migrated_from": LEGACY_SCHEMA_VERSION,
    }
    return v3_dict, quarantined


# ---------------------------------------------------------------------------
# 统一归一化入口（供 state_persistence.py 调用，替代分散的 key-subset 嗅探）
# ---------------------------------------------------------------------------


def normalize_memory_blob(
    data: Any,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], str]:
    """把任意已知形状的记忆 blob 归一化成当前 MemorySystem.to_dict() 形状。

    覆盖：当前 v2/v3 MemorySystem 形状（原样直通）、旧版 SylanneMemoryState
    （records 结构）。不认识的形状返回 (None, [], "unknown")——调用方应视为
    "这份数据我读不懂"而不是"这份数据是空的"，两者对上层告警/降级路径的语义
    完全不同。

    Returns:
        (normalized_dict_or_None, quarantined_raw_items, detected_format)
        detected_format ∈ {"memory_system", "legacy_sylanne_memory_state", "unknown"}
    """
    if not isinstance(data, dict):
        return None, [], "unknown"
    if _MEMORY_SYSTEM_SHAPE_KEYS.issubset(data.keys()):
        return data, [], "memory_system"
    if is_legacy_sylanne_memory_state(data):
        v3_dict, quarantined = legacy_state_to_v3_dict(data)
        return v3_dict, quarantined, "legacy_sylanne_memory_state"
    return None, [], "unknown"


# ---------------------------------------------------------------------------
# .alpha.json 原始文件救援读取（绕过 kernel 恢复白名单）
# ---------------------------------------------------------------------------


def quarantine_kv_key(safe_session_key: str) -> str:
    """quarantine 侧车 KV 键名，与其余记忆 KV 键同一命名习惯（不带冒号变体统一用冒号，
    与 `sylanne_memory_state:{safe}` 对齐，便于运维按前缀扫描/清理）。
    """
    return f"sylanne_memory_quarantine:{safe_session_key}"


def salvage_memory_system_from_alpha_json(path: str | Path) -> dict[str, Any] | None:
    """绕过 kernel 的 AlphaBodyState.from_dict 白名单，直接从 .alpha.json 原始文件
    的 body.memory['_memory_system'] 里救出记忆存档。

    背景：`AlphaBodyState.from_dict`（sylanne_core/compute/body.py）恢复 `memory`
    字段时只认 `relationship`/`shadow` 两个子键，其余子键（包括 `_memory_system`/
    `traces`）会被静默丢弃；当前 schema 的 `AlphaKernel.restore()` 也遵循这条白名单。
    schema 不匹配的快照不会再导入，原文件保持不动供这条只读救援路径检查。
    这意味着一旦 KV 主路径丢失，唯一还留着的"body 文件里的记忆救援副本"在下一次
    kernel 重建时就会被这个白名单悄悄吃掉——必须绕开 kernel 的反序列化，直接读
    裸 JSON 文件本身。

    本函数只读文件、只做字典探测，不触碰/不修改 kernel 恢复逻辑本身（那是 body.py
    的既有契约，超出 MEM-01 的改动范围）。

    Returns:
        body.memory['_memory_system'] 原始 dict（未做任何格式转换，调用方应再经
        `normalize_memory_blob` / `MemorySystem.create_from_dict` 处理），文件不
        存在、JSON 损坏、或找不到该字段时返回 None。
    """
    p = Path(path)
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError as e:
        logger.debug("Sylanne memory salvage: 读取 %s 失败：%s", p, e)
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as e:
        logger.debug("Sylanne memory salvage: %s JSON 解析失败：%s", p, e)
        return None
    if not isinstance(data, dict):
        return None
    body = data.get("body")
    if not isinstance(body, dict):
        return None
    memory = body.get("memory")
    if not isinstance(memory, dict):
        return None
    mem_sys = memory.get("_memory_system")
    return mem_sys if isinstance(mem_sys, dict) else None


__all__ = [
    "LEGACY_SCHEMA_VERSION",
    "is_legacy_sylanne_memory_state",
    "legacy_state_to_v3_dict",
    "normalize_memory_blob",
    "quarantine_kv_key",
    "salvage_memory_system_from_alpha_json",
]
