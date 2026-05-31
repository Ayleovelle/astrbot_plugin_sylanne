"""主动发言调度器 —— 根据沉默时长和人格驱动决定是否主动说话。

职责：
  1. 策略派生：根据配置和反馈历史计算调度策略（冷却时间、反馈压力）
  2. 阻塞判断：检查是否满足主动发言条件（空闲时间、冷却期）
  3. 调度循环：定期扫描候选会话，触发主动发言
  4. 话题判断：决定主动发言的内容方向
  5. 仪式缺席检测：检查用户是否在仪式时间窗口内缺席

设计原则：
  - 人格驱动：表达欲、void_pressure 等计算栈参数影响发言决策
  - 反馈学习：若用户对主动发言冷淡/不回复，增加冷却时间
  - 安全优先：用户活跃时不打断，冷却期内不重复

与其他组件的关系：
  - 被 public_api.py 的 proactive_sylanne() 调用
  - 使用 compat.proactive_decision() 从 host 诊断数据生成决策
  - 通过 host.on_proactive_check() 与计算栈交互

所有方法通过 ``self._p`` 委托访问插件实例属性。
"""

from __future__ import annotations

import asyncio
import collections
import time
from typing import Any

try:
    from astrbot.api import logger  # type: ignore
except ImportError:
    import logging as _logging

    logger = _logging.getLogger("astrbot_plugin_sylanne")  # type: ignore


class ProactiveScheduler:
    """主动发言调度器，封装 Sylanne 插件的主动发言逻辑。

    核心流程：
      定时扫描 → 策略评估 → 阻塞检查 → 构建请求 → 触发发言

    与其他组件的关系：
      - 持有插件实例引用 (self._p)
      - 使用 compat.proactive_decision 做决策
      - 通过 host.on_proactive_check 与计算栈交互
    """

    def __init__(self, plugin: Any) -> None:
        self._p = plugin
        # 仪式注册表：session_key → {ritual_name: (start_hour, end_hour)}
        # 初始为空，后续可通过对话学习填充
        self._ritual_registry: dict[str, dict[str, tuple[int, int]]] = {}
        # 每会话最后消息时间追踪
        self._last_message_times: dict[str, float] = {}
        # Item 6: 主动发言反馈历史（限制最近 200 条防止无界增长）
        self._feedback_history: collections.deque = collections.deque(maxlen=200)

    # ------------------------------------------------------------------
    # Policy & feedback
    # ------------------------------------------------------------------

    def derive_dispatch_policy(
        self, decision: Any = None, *, session_key: str = "", **kwargs: Any
    ) -> dict[str, Any]:
        """派生调度策略：根据配置和历史反馈计算冷却时间和反馈压力。

        Args:
            decision: 可选的决策上下文。
            session_key: 会话标识。

        Returns:
            策略字典，包含 should_dispatch、cooldown_seconds、feedback_pressure。
        """
        cfg = self._p.config or {}
        cooldown = float(cfg.get("proactive_speech_dispatch_cooldown_seconds", 1800.0))
        # 根据历史反馈计算压力：冷淡/未回复越多，冷却时间越长
        feedback_pressure = 0.0
        audit = getattr(self._p, "_proactive_dispatch_audit", None) or {}
        history = audit.get(session_key)
        if history:
            cold_count = sum(
                1
                for entry in history
                if entry.get("feedback_status") in ("cold_reply", "unanswered")
            )
            feedback_pressure = min(1.0, cold_count * 0.3)
            cooldown = cooldown * (1.0 + feedback_pressure)
        return {
            "should_dispatch": bool(cfg.get("enable_proactive_speech_dispatch")),
            "reason": "policy",
            "cooldown_seconds": cooldown,
            "feedback_pressure": feedback_pressure,
        }

    def observe_dispatch_feedback(self, session_key: str = "", **kwargs: Any) -> None:
        pass

    def record_feedback(self, session_key: str, timestamp: float, rating: str) -> None:
        """记录用户对主动发言的反馈。

        Args:
            session_key: 会话标识。
            timestamp: 主动发言的时间戳（用于关联具体哪条发言）。
            rating: "positive" 或 "negative"。
        """
        self._feedback_history.append({
            "session_key": session_key,
            "timestamp": timestamp,
            "rating": rating,
            "recorded_at": time.time(),
        })

    def should_exit_after_idle(self, session_key: str = "", **kwargs: Any) -> bool:
        return True

    # ------------------------------------------------------------------
    # Dispatch building & blocking
    # ------------------------------------------------------------------

    def build_dispatch_request(
        self,
        decision: Any = None,
        *,
        event_or_session: Any = None,
        session_key: str = "",
        candidate_context: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """构建主动发言调度请求。

        Args:
            decision: 决策上下文（可能包含话题判断结果）。
            session_key: 目标会话标识。

        Returns:
            调度请求字典，包含 message_text、quiet_gate、realtime_chat_plan。
        """
        cfg = self._p.config or {}
        topic_judgement = {}
        if isinstance(decision, dict):
            topic_judgement = decision.get("topic_judgement", {})
        message_text = topic_judgement.get("draft_message", "")
        min_idle = float(cfg.get("proactive_speech_min_idle_seconds", 300.0))
        return {
            "requested": True,
            "session_key": session_key,
            "message_text": message_text,
            "quiet_gate": {"min_idle_seconds": min_idle},
            "realtime_chat_plan": {"message_count": 1},
        }

    def dispatch_blocked_reason(
        self,
        decision: Any = None,
        dispatch: Any = None,
        *,
        event_or_session: Any = None,
        dry_run: bool = False,
        force: bool = False,
        **kwargs: Any,
    ) -> str:
        """检查主动发言是否被阻塞，返回阻塞原因。

        阻塞条件：
          - 调度功能未启用
          - 用户最近有活动（静默期未满）
          - 冷却期未结束

        Returns:
            阻塞原因字符串，空字符串表示可以发言。
        """
        if force:
            return ""
        cfg = self._p.config or {}
        if not cfg.get("enable_proactive_speech_dispatch"):
            return "dispatch_disabled"
        now = (
            self._p._observed_now()
            if callable(self._p._observed_now)
            else self._p._observed_now
        )
        candidates = self._p._proactive_candidate_sessions
        sk = ""
        if event_or_session is not None:
            sk = str(getattr(event_or_session, "unified_msg_origin", "") or "")
        candidate = candidates.get(sk, {})
        last_seen = candidate.get("last_seen_at", 0.0)
        min_idle = float(
            (dispatch or {}).get("quiet_gate", {}).get("min_idle_seconds", 300.0)
        )
        if last_seen and (now - last_seen) < min_idle:
            return "recent_user_activity_quiet_period"
        last_sent = (getattr(self._p, "_proactive_dispatch_last_sent", None) or {}).get(
            sk, 0.0
        )
        cooldown = float(cfg.get("proactive_speech_dispatch_cooldown_seconds", 1800.0))
        # 人格驱动硬下限：expression_drive 高→下限低（最低60s），低→下限高（最高300s）
        host = self._p._hosts.get(sk)
        _expression_drive = 0.5
        if host and hasattr(host.kernel, "_personality"):
            _p = host.kernel._personality() if callable(getattr(host.kernel, "_personality", None)) else {}
            _expression_drive = float((_p or {}).get("expression_drive_trait", (_p or {}).get("extraversion", 0.5)))
        _hard_floor = max(60.0, 300.0 - _expression_drive * 240.0)
        cooldown = max(cooldown, _hard_floor)
        if last_sent and (now - last_sent) < cooldown:
            return "cooldown_active"
        return ""

    # ------------------------------------------------------------------
    # Scheduler state & loop
    # ------------------------------------------------------------------

    def ensure_state(self) -> None:
        """确保调度器所需的运行时状态容器已初始化。"""
        # All attributes are now initialized in EmotionalStatePlugin.__init__
        pass

    async def run_once(self) -> dict[str, Any]:
        """执行一次调度扫描：遍历所有候选会话，尝试触发主动发言。

        Returns:
            扫描结果字典，包含 checked（检查数）和 dispatched（发送数）。
        """
        self.ensure_state()
        candidates = dict(self._p._proactive_candidate_sessions)
        checked = 0
        dispatched = 0
        for sk, info in candidates.items():
            checked += 1
            dispatch_fn = getattr(self._p, "request_proactive_speech_dispatch", None)
            if dispatch_fn and callable(dispatch_fn):
                event = (
                    info.get("event")
                    or type("_E", (), {"unified_msg_origin": sk, "session_id": sk})()
                )
                result = await dispatch_fn(event, dry_run=False)
                if result.get("dispatched"):
                    dispatched += 1
        return {"checked": checked, "dispatched": dispatched}

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    async def get_speech_decision(
        self,
        event_or_session: Any = None,
        *,
        session_key: str = "",
        now: float = 0.0,
        candidate_context: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """获取主动发言决策：通过计算栈诊断数据判断是否应该说话。

        Returns:
            决策字典，包含 should_speak、reason 等字段。
        """
        from sylanne_alpha.compat import proactive_decision

        sk = (
            session_key
            or (
                str(getattr(event_or_session, "unified_msg_origin", ""))
                if event_or_session
                else ""
            )
            or "default"
        )
        host = self._p._host(sk)
        surface = host.diagnostics()
        return proactive_decision(surface)

    async def request_dispatch(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {}

    async def judge_topic(self, session_key: str = "", **kwargs: Any) -> dict[str, Any]:
        return {"topic": "", "confidence": 0.0, "should_speak": False}

    # ------------------------------------------------------------------
    # 仪式缺席检测（Item 154）
    # ------------------------------------------------------------------

    def register_ritual(
        self, session_key: str, ritual_name: str, start_hour: int, end_hour: int
    ) -> None:
        """注册一个仪式时间窗口。

        仪式是用户与 Sylanne 之间形成的习惯性互动模式，
        例如每晚 22:00-23:00 的"晚安"仪式。

        Args:
            session_key: 会话标识。
            ritual_name: 仪式名称（如 "晚安"、"早安"）。
            start_hour: 仪式窗口开始小时（0-23）。
            end_hour: 仪式窗口结束小时（0-23）。
        """
        if session_key not in self._ritual_registry:
            self._ritual_registry[session_key] = {}
        self._ritual_registry[session_key][ritual_name] = (start_hour, end_hour)

    def unregister_ritual(self, session_key: str, ritual_name: str) -> None:
        """移除一个已注册的仪式。

        Args:
            session_key: 会话标识。
            ritual_name: 仪式名称。
        """
        if session_key in self._ritual_registry:
            self._ritual_registry[session_key].pop(ritual_name, None)

    def record_message_time(self, session_key: str, ts: float | None = None) -> None:
        """记录用户最后一次发消息的时间。

        Args:
            session_key: 会话标识。
            ts: 时间戳，默认为当前时间。
        """
        self._last_message_times[session_key] = ts if ts is not None else time.time()

    def check_ritual_absence(self, session_key: str, now: float | None = None) -> str | None:
        """检查是否到了仪式时间但用户未出现。

        判断逻辑：
        1. 当前时间在某个已注册仪式的时间窗口内
        2. 用户在该窗口内超过 30 分钟未发消息

        Args:
            session_key: 会话标识。
            now: 当前时间戳，默认为 time.time()。

        Returns:
            缺席的仪式名，或 None（无缺席）。
        """
        if now is None:
            now = time.time()

        rituals = self._ritual_registry.get(session_key)
        if not rituals:
            return None

        current_hour = time.localtime(now).tm_hour
        last_msg = self._last_message_times.get(session_key, 0.0)
        silence_seconds = now - last_msg

        # 30 分钟未发消息才算缺席
        absence_threshold = 30 * 60

        for ritual_name, (start_hour, end_hour) in rituals.items():
            # 判断当前小时是否在仪式窗口内（支持跨午夜）
            if start_hour <= end_hour:
                in_window = start_hour <= current_hour <= end_hour
            else:
                in_window = current_hour >= start_hour or current_hour <= end_hour

            if in_window and silence_seconds >= absence_threshold:
                return ritual_name

        return None
