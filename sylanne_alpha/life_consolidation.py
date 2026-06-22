"""Phase 2 核心：生活巩固引擎（LifeConsolidation，真·零 LLM）。

夜间深睡期把"当天的生活经历"沉淀成"次日的轻量计划 + 关系摘要"，对应 proposal
§4.4 的夜间深巩固。与对话策略的 ConsolidationEngine（agents/learning/consolidation.py）
**独立命名、独立预算、独立 KV namespace**，不混进对话策略巩固（proposal 明确要求）。

设计纪律（Oracle 审定）：
- 真·零 LLM：纯本地聚合当天 LifeEvent → 次日 LifePlan，无 token 成本。
- 不碰主动发言投递成败（consumed/dropped 是 M8 的反馈维度，本引擎只读事件内容做计划，
  不学投递结果、不调任何 ShareIntent 权重——避免与 M8 双罚 / 与对话 reflection 重叠）。
- 守卫：每会话最小间隔（防 RETIRED 期反复巩固）。
- 持久化：独立 KV key sylanne_life_consolidation_{safe}，仿既有命名风格但独立 namespace。

调用方（AutonomyScheduler RETIRED 分支）走锁舞：锁内 consolidate_sync 取计划快照，
锁外 _write_state 落盘；写 state.plan 前由调用方保证相位仍 RETIRED（唤醒则丢弃）。
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from typing import Any

logger = logging.getLogger("astrbot_plugin_sylanne")

# 同一会话两次巩固的最小间隔（秒）——与对话策略 ConsolidationEngine 一致。
_MIN_INTERVAL = 1800.0
# 次日计划最多保留的锚点活动数（防计划膨胀）。
_MAX_ANCHORS = 5
# 当天事件取样上限（聚合输入，防超长历史拖慢纯计算）。
_MAX_TODAY_EVENTS = 50


class LifeConsolidationEngine:
    """夜间生活巩固：当天 LifeEvent → 次日 LifePlan + 关系摘要。零 LLM。"""

    def __init__(self, plugin: Any) -> None:
        self._p = plugin
        # 每会话上次巩固时间（守卫，避免 RETIRED 期反复巩固）。
        self._last_consolidated: dict[str, float] = {}

    def needs_consolidation(self, session_key: str, now: float) -> bool:
        last = self._last_consolidated.get(session_key, 0.0)
        return (now - last) >= _MIN_INTERVAL

    def consolidate_sync(self, session_key: str, now: float) -> dict | None:
        """夜间巩固的同步部分（零 LLM、零 IO）：当天事件聚合成次日计划 + 关系摘要。

        返回待落盘快照 dict（含 plan_dict + relationship_summary），无可巩固内容返回 None。
        与 KV 落盘拆开：调用方在 session_lock 内只跑这段同步计算，put_kv_data 移到锁外。
        """
        self._last_consolidated[session_key] = now
        sim = getattr(self._p, "_life_simulator", None)
        if sim is None:
            return None
        try:
            state = sim.state
            today_events = self._today_events(state, now)
            if not today_events:
                return None
            plan = self._build_next_day_plan(state, today_events, now)
            summary = self._build_relationship_summary(today_events)
            # 写入 state（计划进 state.plan 供次日 tick 读；摘要进 world 快照）
            state.plan = plan
            try:
                state.world.relationship_snapshot = summary
            except Exception:
                pass
            from sylanne_alpha.life_simulation import _plan_to_dict
            return {
                "plan": _plan_to_dict(plan),
                "relationship_summary": summary,
                "consolidated_at": now,
            }
        except Exception as exc:
            logger.debug("Sylanne life consolidate [%s]: %s", session_key, exc)
            return None

    def _today_events(self, state: Any, now: float) -> list:
        """取"当天"的 LifeEvent（按本地日界，无界历史截最近 N 条）。"""
        events = list(getattr(state, "events", []) or [])
        if not events:
            return []
        # 本地今天 00:00 时间戳
        lt = time.localtime(now)
        today_start = time.mktime(
            (lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1)
        )
        today = [e for e in events if getattr(e, "timestamp", 0.0) >= today_start]
        return today[-_MAX_TODAY_EVENTS:]

    def _build_next_day_plan(self, state: Any, today_events: list, now: float):
        """纯本地：按当天事件的 event_type 频次 + 重要性，聚合成次日锚点活动。

        不调 LLM、不读投递成败——只看"她今天在忙什么类型的事"，延续到明天的锚点。
        读 LifeReflection 产的 next_plan_hint.kind_bias 作偏好输入（单写者规则：本引擎
        仍是 state.plan 唯一所有者，hint 只是众多输入之一，有界不主导）。
        """
        from sylanne_alpha.life_simulation import LifeActivity, LifePlan

        # 反思建议（advisory，有界）：{kind: bounded_bias}。读 world.next_plan_hint。
        kind_bias: dict = {}
        try:
            world = getattr(state, "world", None)
            hint = getattr(world, "next_plan_hint", None) if world else None
            if isinstance(hint, dict):
                kb = hint.get("kind_bias")
                if isinstance(kb, dict):
                    kind_bias = kb
        except Exception:
            kind_bias = {}

        # 按 event_type 聚合重要性权重（importance 累加，取 top N 类）
        type_weight: Counter = Counter()
        type_sample_title: dict[str, str] = {}
        for e in today_events:
            et = str(getattr(e, "event_type", "") or "").strip()
            if not et:
                continue
            imp = float(getattr(e, "importance", 0.0) or 0.0)
            type_weight[et] += max(0.05, imp)  # 至少给点底权重，保证出现过的类型有份
            if et not in type_sample_title:
                txt = str(getattr(e, "text", "") or "")[:40]
                type_sample_title[et] = txt

        # 应用反思偏好：按 kind 给对应 event_type 的权重加 bias（有界，不主导排序）。
        if kind_bias:
            for et in list(type_weight.keys()):
                kind = _event_type_to_kind(et)
                bias = kind_bias.get(kind)
                if bias is not None:
                    try:
                        type_weight[et] += float(bias)
                    except (TypeError, ValueError):
                        pass

        anchors = []
        for et, _w in type_weight.most_common(_MAX_ANCHORS):
            anchors.append(
                LifeActivity(
                    kind=_event_type_to_kind(et),
                    title=type_sample_title.get(et, et),
                    status="planned",
                )
            )

        # 次日日期（本地 now + 1 天）
        tomorrow = time.localtime(now + 86400)
        date_str = time.strftime("%Y-%m-%d", tomorrow)
        tz = ""
        confidence = min(0.7, 0.3 + 0.05 * len(anchors))  # 锚点越多越有据，封顶 0.7
        return LifePlan(
            date=date_str,
            timezone=tz,
            anchors=anchors,
            generated_from=["consolidation"],
            confidence=confidence,
        )

    def _build_relationship_summary(self, today_events: list) -> dict:
        """纯本地：当天事件压成一份轻量关系摘要（情绪基线 + 活跃度），供次日呈现参考。

        只聚合事件自身的情绪增量，不涉及任何用户投递反馈（那是 M8 维度）。
        """
        n = len(today_events)
        val = sum(float(getattr(e, "valence_delta", 0.0) or 0.0) for e in today_events)
        aro = sum(float(getattr(e, "arousal_delta", 0.0) or 0.0) for e in today_events)
        return {
            "event_count": n,
            "valence_avg": round(val / n, 4) if n else 0.0,
            "arousal_avg": round(aro / n, 4) if n else 0.0,
        }

    async def _write_state(self, session_key: str, snapshot: dict) -> None:
        """把巩固快照写入独立 KV key（深睡低频写）。"""
        p = self._p
        if not snapshot or not getattr(p, "_has_kv_api", lambda: False)():
            return
        safe = (
            p._safe_session_key(session_key)
            if hasattr(p, "_safe_session_key")
            else session_key
        )
        try:
            await p.put_kv_data(f"sylanne_life_consolidation_{safe}", snapshot)
        except Exception as exc:
            logger.debug("Sylanne life consolidate write [%s]: %s", session_key, exc)

    def forget_session(self, session_key: str) -> None:
        self._last_consolidated.pop(session_key, None)


def _event_type_to_kind(event_type: str) -> str:
    """把 LifeEventType 映射到 LifeActivity.kind（study/create/rest/game/social/reflect）。"""
    et = event_type.lower()
    mapping = {
        "work": "study",
        "study": "study",
        "research": "study",
        "create": "create",
        "creative": "create",
        "hobby": "create",
        "game": "game",
        "play": "game",
        "rest": "rest",
        "sleep": "rest",
        "social": "social",
        "chat": "social",
        "reflect": "reflect",
        "thought": "reflect",
    }
    for k, v in mapping.items():
        if k in et:
            return v
    return "rest"
