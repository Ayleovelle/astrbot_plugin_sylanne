"""Phase 2 核心：生活反思引擎（LifeReflection，低频 LLM）。

白天/入睡前对 Sylanne 自己的生活跑一次低频 LLM 反思，产出"跨天叙事弧"洞察
+ 次日计划建议（next_plan_hint），喂给 LifeConsolidation 作输入。对应 proposal §4.4
的白天轻反思。**活在生活模拟域**，与对话策略的 learning/ReflectionEngine 彻底隔离
（proposal 明确要求"不混进对话策略 reflection，避免互相污染"）。

与 LifeConsolidation 的分工（Oracle 审定，单写者规则）：
- LifeReflection：DROWSY 低频 LLM，读当天 LifeEvent + 计划完成率 → 产叙事 insight
  + next_plan_hint。**只写 hint，绝不写 state.plan。**
- LifeConsolidation：RETIRED 零 LLM，读 hint 作输入之一 → 生成 state.plan。**唯一计划所有者。**
- 相位天然错开：DROWSY(反思) 先于 RETIRED(巩固) 在同一扫描周期触发，hint 就绪。

防自证循环（Oracle 审定）：
- 输入只用原始 LifeEvent + activity.status（不读已 hint 化的状态，避免 LLM-on-LLM）。
- hint 每日重生（不累积），kind_bias 有界 clamp（±_KIND_BIAS_CAP）。
- **不读 consumed_at/dropped_at**（那是 M8 投递维度），不调任何 ShareIntent 权重。

token 闸（仿 learning/reflection.py，独立预算，不共用对话反思配额）：
1. 间隔闸：同会话两次反思最小间隔。
2. 日预算池：每会话每日 N 次，超额跳过；自持 dict（不碰 SelfCore.reflection_meta）。
3. 输入压缩：事件摘要 ≤ _INPUT_CAP 字符。
锁舞：持锁取快照 → 释放锁跑 LLM（带 timeout）→ 重持锁校验唤醒 → 写 hint。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import Counter
from typing import Any

logger = logging.getLogger("astrbot_plugin_sylanne")

_REFLECT_TIMEOUT = 8.0
_INPUT_CAP = 1200
_MIN_INTERVAL = 1800.0
# 次日计划建议里 kind_bias 的硬上界（防自证循环放大）。
_KIND_BIAS_CAP = 0.10
# 反思输入取当天事件上限。
_MAX_TODAY_EVENTS = 50

_PROMPT = (
    "你在帮一个虚构角色复盘她今天的生活，输出一句跨天叙事观察 + 次日活动倾向建议。\n"
    "只看活动类型分布和完成情况，不评价好坏，不煽情。\n"
    "今日生活概况：\n{summary}\n\n"
    "请输出 JSON：{{\"arc\": \"一句叙事观察(≤40字)\", "
    "\"kind_bias\": {{\"活动类型\": 微调值}}}}\n"
    "kind_bias 的值在 -0.1~0.1 之间，正=次日多安排该类，负=少安排。"
    "活动类型用 study/create/game/rest/social/reflect。只输出 JSON。"
)


class LifeReflectionEngine:
    """生活反思：当天生活 → 叙事弧 + 次日计划建议。低频 LLM。"""

    def __init__(self, plugin: Any) -> None:
        self._p = plugin
        # 自持预算元数据（不碰 SelfCore.reflection_meta，与对话反思隔离）。
        # {session_key: {"daily": [yyyymmdd, count], "last_reflected": float}}
        self._meta: dict[str, dict] = {}

    def _budget(self) -> int:
        try:
            return max(0, int((self._p.config or {}).get(
                "sylanne_alpha_life_reflection_daily_budget", 1)))
        except Exception:
            return 1

    def _today(self, now: float) -> str:
        return time.strftime("%Y%m%d", time.localtime(now))

    def _has_budget(self, session_key: str, now: float) -> bool:
        budget = self._budget()
        if budget <= 0:
            return False
        rec = self._meta.get(session_key, {}).get("daily")
        if not rec or rec[0] != self._today(now):
            return True
        return rec[1] < budget

    def _consume_budget(self, session_key: str, now: float) -> None:
        meta = self._meta.setdefault(session_key, {})
        today = self._today(now)
        rec = meta.get("daily")
        if not rec or rec[0] != today:
            meta["daily"] = [today, 1]
        else:
            rec[1] += 1

    def _interval_ok(self, session_key: str, now: float) -> bool:
        last = float(self._meta.get(session_key, {}).get("last_reflected", 0.0) or 0.0)
        return (now - last) >= _MIN_INTERVAL

    def forget_session(self, session_key: str) -> None:
        self._meta.pop(session_key, None)

    async def maybe_reflect(self, session_key: str, now: float) -> bool:
        """DROWSY 首拍调用。间隔+预算闸全过才跑一次反思。返回是否真反思了。"""
        if not self._interval_ok(session_key, now):
            return False
        if not self._has_budget(session_key, now):
            logger.debug("Sylanne life reflection budget exhausted [%s]", session_key)
            return False
        try:
            return await self._reflect_locked(session_key, now)
        except Exception as exc:
            logger.debug("Sylanne life reflection [%s]: %s", session_key, exc)
            return False

    async def _reflect_locked(self, session_key: str, now: float) -> bool:
        p = self._p
        sim = getattr(p, "_life_simulator", None)
        if sim is None:
            return False
        lock = p._session_lock(session_key)
        # ① 持锁取只读快照（同步、零 LLM）
        async with lock:
            today_events = self._today_events(sim.state, now)
            if len(today_events) < 3:
                return False  # 生活太少不值得反思（未占预算、未烧 LLM）
            summary = self._build_summary(sim.state, today_events)
            user_ts_before = self._user_ts(session_key)
        # ②【预算闸】调 LLM 前就扣预算 + 记时（同 learning/reflection：token 已花必计）
        self._consume_budget(session_key, now)
        self._meta.setdefault(session_key, {})["last_reflected"] = now
        # ③ 锁外跑 LLM（带 timeout 降级），唤醒可在此期间发生
        raw = await self._call_llm(_PROMPT.format(summary=summary[:_INPUT_CAP]))
        if not raw:
            return False
        hint = self._parse(raw)
        if not hint:
            return False
        # ④ 重持锁校验唤醒优先，未被唤醒才写 hint
        async with lock:
            if self._user_ts(session_key) != user_ts_before:
                logger.debug("Sylanne life reflection discarded (new msg) [%s]", session_key)
                return False
            # 单写者：只写 world.next_plan_hint（每日重生，不累积），绝不碰 state.plan
            try:
                sim.state.world.next_plan_hint = hint
            except Exception:
                return False
        logger.info("Sylanne life reflection applied [%s]: arc=%s", session_key, hint.get("arc", ""))
        return True

    def _today_events(self, state: Any, now: float) -> list:
        events = list(getattr(state, "events", []) or [])
        if not events:
            return []
        lt = time.localtime(now)
        today_start = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
        today = [e for e in events if getattr(e, "timestamp", 0.0) >= today_start]
        return today[-_MAX_TODAY_EVENTS:]

    def _build_summary(self, state: Any, today_events: list) -> str:
        """把当天事件 + 计划完成率压成叙事 prompt 输入（不读投递成败）。"""
        # 活动类型分布
        type_count: Counter = Counter()
        for e in today_events:
            et = str(getattr(e, "event_type", "") or "").strip()
            if et:
                type_count[et] += 1
        dist = "、".join(f"{k}×{v}" for k, v in type_count.most_common(6)) or "无明确类型"
        # 计划完成率（activity.status —— 巩固没读的新信号，反思价值核心）
        plan = getattr(state, "plan", None)
        done = skipped = planned = 0
        if plan is not None:
            for a in list(getattr(plan, "anchors", []) or []):
                st = str(getattr(a, "status", "") or "")
                if st == "done":
                    done += 1
                elif st == "skipped":
                    skipped += 1
                elif st == "planned":
                    planned += 1
        completion = (
            f"昨日计划：完成{done}/跳过{skipped}/未动{planned}"
            if (done or skipped or planned)
            else "昨日无计划记录"
        )
        return f"活动分布：{dist}\n事件数：{len(today_events)}\n{completion}"

    def _user_ts(self, session_key: str) -> float:
        try:
            return float(self._p._store.last_user_message_time.get(session_key, 0.0) or 0.0)
        except Exception:
            return 0.0

    async def _call_llm(self, prompt: str) -> str:
        try:
            call = self._p._main_assessor_llm_call
            return await asyncio.wait_for(call(prompt), timeout=_REFLECT_TIMEOUT)
        except Exception as exc:
            logger.debug("Sylanne life reflection LLM degraded: %s", exc)
            return ""

    def _parse(self, raw: str) -> dict:
        """解析 LLM 输出的 hint JSON。kind_bias 有界 clamp，arc 截断。"""
        try:
            s = raw.strip()
            i, j = s.find("{"), s.rfind("}")
            if i < 0 or j <= i:
                return {}
            data = json.loads(s[i:j + 1])
            if not isinstance(data, dict):
                return {}
            arc = str(data.get("arc", "") or "")[:40]
            raw_bias = data.get("kind_bias")
            kind_bias: dict[str, float] = {}
            allow = {"study", "create", "game", "rest", "social", "reflect"}
            if isinstance(raw_bias, dict):
                for k, v in raw_bias.items():
                    if str(k) not in allow:
                        continue
                    try:
                        fv = float(v)
                    except (TypeError, ValueError):
                        continue
                    # 有界 clamp（防自证循环放大）
                    kind_bias[str(k)] = max(-_KIND_BIAS_CAP, min(_KIND_BIAS_CAP, fv))
            if not arc and not kind_bias:
                return {}
            return {"arc": arc, "kind_bias": kind_bias}
        except Exception as exc:
            logger.debug("Sylanne life reflection parse: %s", exc)
            return {}
