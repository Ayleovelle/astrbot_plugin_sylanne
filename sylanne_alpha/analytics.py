"""Sylanne-Embodiment: 分析与报告模块。

提供周报自动生成等统计分析功能。

Item 69: 周报自动生成
- 统计过去 7 天的对话轮数、活跃会话数、新记忆条数
- 人格漂移幅度（各维度 delta 绝对值之和）
- 伤痕活跃度（新增伤痕数）
"""

from __future__ import annotations

import time
from typing import Any


def generate_weekly_report(plugin: Any) -> dict[str, Any]:
    """生成过去 7 天的周报统计。

    统计项：
    - total_turns: 总对话轮数
    - active_sessions: 活跃会话数
    - new_memories: 新记忆条数
    - personality_drift_magnitude: 人格漂移幅度（各维度 delta 绝对值之和）
    - scar_activity: 伤痕活跃度（新增伤痕数）

    Args:
        plugin: 插件实例，通过其属性访问各子系统状态。

    Returns:
        结构化 dict，包含各统计项和元数据。
    """
    now = time.time()
    seven_days_ago = now - 7 * 86400

    # --- 总对话轮数 & 活跃会话数 ---
    total_turns = 0
    active_sessions = 0
    hosts = getattr(plugin, "_hosts", {}) or {}
    if isinstance(hosts, dict):
        for session_key, host in hosts.items():
            try:
                tick_count = getattr(host.kernel.computation, "_tick_count", 0)
                if tick_count > 0:
                    active_sessions += 1
                    total_turns += tick_count
            except Exception:
                continue

    # --- 新记忆条数 ---
    new_memories = 0
    mem_getter = getattr(plugin, "_memory_system_for_session", None)
    if callable(mem_getter) and isinstance(hosts, dict):
        for session_key in hosts:
            try:
                mem_sys = mem_getter(session_key)
                if mem_sys is None:
                    continue
                # L1 items with created_at in the last 7 days
                for item in list(getattr(mem_sys, "_l1", []) or []):
                    created_at = float(
                        getattr(item, "created_at", 0)
                        or (item.get("created_at", 0) if isinstance(item, dict) else 0)
                    )
                    if created_at >= seven_days_ago:
                        new_memories += 1
                # L2 items with created_at in the last 7 days
                for item in list(getattr(mem_sys, "_l2", []) or []):
                    created_at = float(
                        getattr(item, "created_at", 0)
                        or (item.get("created_at", 0) if isinstance(item, dict) else 0)
                    )
                    if created_at >= seven_days_ago:
                        new_memories += 1
            except Exception:
                continue

    # --- 人格漂移幅度 ---
    personality_drift_magnitude = 0.0
    for session_key, host in (hosts.items() if isinstance(hosts, dict) else []):
        try:
            kernel = host.kernel
            personality = getattr(kernel, "personality", None)
            if personality is None:
                continue
            if callable(personality):
                personality = personality()
            if not isinstance(personality, dict):
                continue
            drift_data = personality.get("drift", {})
            if isinstance(drift_data, dict):
                deltas = drift_data.get("deltas", {})
                if isinstance(deltas, dict):
                    personality_drift_magnitude += sum(
                        abs(float(v)) for v in deltas.values()
                    )
                history = drift_data.get("history", [])
                if isinstance(history, list):
                    for entry in history:
                        entry_time = float(entry.get("time", 0) or 0)
                        if entry_time >= seven_days_ago:
                            delta_val = float(entry.get("delta", 0) or 0)
                            personality_drift_magnitude += abs(delta_val)
        except Exception:
            continue
    personality_drift_magnitude = round(personality_drift_magnitude, 4)

    # --- 伤痕活跃度（新增伤痕数）---
    scar_activity = 0
    for session_key, host in (hosts.items() if isinstance(hosts, dict) else []):
        try:
            comp = host.kernel.computation
            engine = comp.engine
            scar_state = getattr(engine, "scar_state", None)
            scars = getattr(scar_state, "scars", []) or []
            for scar in scars:
                scar_time = float(
                    getattr(scar, "created_at", 0)
                    or (scar.get("created_at", 0) if isinstance(scar, dict) else 0)
                )
                if scar_time >= seven_days_ago:
                    scar_activity += 1
        except Exception:
            continue

    return {
        "schema_version": "sylanne.analytics.weekly.v1",
        "generated_at": now,
        "period_start": seven_days_ago,
        "period_end": now,
        "total_turns": total_turns,
        "active_sessions": active_sessions,
        "new_memories": new_memories,
        "personality_drift_magnitude": personality_drift_magnitude,
        "scar_activity": scar_activity,
    }
