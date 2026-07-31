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
import inspect
import time
from typing import TYPE_CHECKING, Any

from .scoped_session_components import ScopedSessionComponentStore
from .scope_repository import ScopedPersistenceGateway

if TYPE_CHECKING:
    from sylanne_alpha.protocols import PluginHost

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

    def __init__(
        self,
        plugin: PluginHost,
        *,
        persistence: ScopedPersistenceGateway | None = None,
    ) -> None:
        """Create the legacy scheduler or a capability-bound scoped scheduler.

        A scoped scheduler owns exactly one SessionScope component.  It does not
        discover a current/default session from plugin maps; delivery remains a
        separately wired outbox concern.
        """

        self._p = plugin
        # 仪式注册表：session_key → {ritual_name: (start_hour, end_hour)}
        # 初始为空，后续可通过对话学习填充
        self._ritual_registry: dict[str, dict[str, tuple[int, int]]] = {}
        # 每会话最后消息时间追踪
        self._last_message_times: dict[str, float] = {}
        # Item 6: 主动发言反馈历史（限制最近 200 条防止无界增长）
        self._feedback_history: collections.deque = collections.deque(maxlen=200)
        self._scoped_components = (
            None if persistence is None else ScopedSessionComponentStore(persistence)
        )
        if self._scoped_components is not None:
            self._restore_scoped_state()

    def _require_legacy_session_api(self) -> None:
        if self._scoped_components is not None:
            raise ValueError("scoped scheduler requires scoped methods")

    def _bound_session_runtime(self, session_key: str) -> Any | None:
        """Resolve only the session already authenticated by the active binding."""

        getter = getattr(self._p, "_bound_runtime", None)
        if not callable(getter):
            return None
        try:
            binding = getter()
        except Exception:
            return None
        if binding is None:
            return None
        scope = getattr(binding, "scope", None)
        runtime = getattr(binding, "session_runtime", None)
        if (
            scope is None
            or runtime is None
            or getattr(scope, "storage_token", None) != session_key
            or getattr(runtime, "storage_token", None) != session_key
        ):
            return None
        return runtime

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

        Phase 3：除现有 `_proactive_dispatch_audit`（pipeline 视角）外，再读
        `_life_simulator.state.outreach_audit[session_key]`（life_sim 视角）。
        两个视角的 unanswered/cold_reply 合并计数。ShareIntent 侧 unanswered_penalty
        维持 * 0.0（M8 单一惩罚通道——scheduler gate 独占，不与 intent 侧双罚）。
        """
        self._require_legacy_session_api()
        cfg = self._p.config or {}
        cooldown = float(cfg.get("proactive_speech_dispatch_cooldown_seconds", 1800.0))
        scoped_runtime_required = (
            getattr(self._p, "_scope_runtime_registry", None) is not None
        )
        session_runtime = self._bound_session_runtime(session_key)
        if scoped_runtime_required and session_runtime is None:
            return {
                "should_dispatch": False,
                "reason": "scope_unavailable",
                "cooldown_seconds": cooldown,
                "feedback_pressure": 0.0,
            }
        # 根据历史反馈计算压力：冷淡/未回复越多，冷却时间越长
        feedback_pressure = 0.0
        cold_count = 0
        # 第一轮 review 修复：两份 audit（pipeline 视角 + life_sim 视角）可能记同一个
        # event 的同一次未回复，按 event_id 去重，避免 cold_count 双数据源双罚。
        seen_event_ids: set[str] = set()
        # ① pipeline 视角（当前冻结 SessionStateStore → deque）。真实插件
        # 只能读当前 binding；原始 key 查表仅保留给没有 registry 的历史桩。
        if session_runtime is not None:
            history = session_runtime.store.proactive_dispatch_audit.get(session_key)
        else:
            audit = getattr(self._p, "_proactive_dispatch_audit", None) or {}
            history = audit.get(session_key) if session_key else None
        if history:
            for entry in history:
                if not isinstance(entry, dict):
                    continue
                if entry.get("feedback_status") not in ("cold_reply", "unanswered"):
                    continue
                eid = str(entry.get("event_id", ""))
                if eid and eid in seen_event_ids:
                    continue
                cold_count += 1
                if eid:
                    seen_event_ids.add(eid)
        # ② life_sim 视角（Phase 3 数据源补建：dict[session_key] → list[entry]）
        life_sim = getattr(self._p, "_life_simulator", None)
        if life_sim is not None and session_key:
            try:
                ls_audit = getattr(life_sim.state, "outreach_audit", {}) or {}
                ls_history = ls_audit.get(session_key)
                if ls_history:
                    for entry in ls_history:
                        if not isinstance(entry, dict):
                            continue
                        if entry.get("feedback_status") not in (
                            "cold_reply", "unanswered"
                        ):
                            continue
                        eid = str(entry.get("event_id", ""))
                        if eid and eid in seen_event_ids:
                            continue
                        cold_count += 1
                        if eid:
                            seen_event_ids.add(eid)
            except Exception:
                pass
        if cold_count > 0:
            feedback_pressure = min(1.0, cold_count * 0.3)
            cooldown = cooldown * (1.0 + feedback_pressure)
        return {
            "should_dispatch": bool(cfg.get("enable_proactive_speech_dispatch")),
            "reason": "policy",
            "cooldown_seconds": cooldown,
            "feedback_pressure": feedback_pressure,
        }

    def observe_dispatch_feedback(self, session_key: str = "", **kwargs: Any) -> None:
        self._require_legacy_session_api()
        pass

    def record_feedback(self, session_key: str, timestamp: float, rating: str) -> None:
        """记录用户对主动发言的反馈。

        Args:
            session_key: 会话标识。
            timestamp: 主动发言的时间戳（用于关联具体哪条发言）。
            rating: "positive" 或 "negative"。
        """
        self._require_legacy_session_api()
        self._feedback_history.append({
            "session_key": session_key,
            "timestamp": timestamp,
            "rating": rating,
            "recorded_at": time.time(),
        })

    def should_exit_after_idle(self, session_key: str = "", **kwargs: Any) -> bool:
        self._require_legacy_session_api()
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
        self._require_legacy_session_api()
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
        self._require_legacy_session_api()
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
        candidates = self._p._store.proactive_candidate_sessions
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
        host = self._p._store.hosts.get(sk)
        _expression_drive = 0.5
        if host and hasattr(host.kernel, "_personality"):
            _p = host.kernel._personality() if callable(getattr(host.kernel, "_personality", None)) else {}
            _expression_drive = float((_p or {}).get("expression_drive_trait", (_p or {}).get("extraversion", 0.5)))
        _hard_floor = max(60.0, 300.0 - _expression_drive * 240.0)
        cooldown = max(cooldown, _hard_floor)
        if last_sent and (now - last_sent) < cooldown:
            return "cooldown_active"
        return ""

    def evaluate_outreach_gate(self, session_key: str = "") -> tuple[bool, str]:
        """PR-C2 / H3 收口：仅按 session_key 评估主动发言 gate（不跑决策/LLM）。

        两条 outreach 路径共用此闸，避免 _life_sim_outreach 的 5min fallback
        绕过 scheduler 的 cooldown / quiet_period / feedback_pressure / 人格下限
        （原 bug：fallback 只过 Bridge gate，scheduler gate 全漏）。

        本方法返回与 request_dispatch 同口径的阻塞判定（dispatch_blocked_reason 的
        session_key-only 封装），但【不】调用 derive_should_send / 不取 surface /
        不跑 hesitation——后者仍是 Bridge 的职责（ADR：Bridge 拥最终否决权）。

        Returns:
            (allowed, reason): allowed=False 时 reason 给出 gate 名（供 reason_code）。
        """
        self._require_legacy_session_api()
        if not session_key:
            return False, "no_session_key"
        synth_session = type("_S", (), {"unified_msg_origin": session_key})()
        dispatch_req = {"quiet_gate": {"min_idle_seconds": float(
            (self._p.config or {}).get("proactive_speech_min_idle_seconds", 300.0)
        )}}
        try:
            block = self.dispatch_blocked_reason(
                dispatch=dispatch_req,
                event_or_session=synth_session,
                dry_run=True,
                force=False,
            )
        except Exception:
            return False, "gate_eval_error"
        if block:
            return False, block
        return True, ""

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
        self._require_legacy_session_api()
        self.ensure_state()
        candidates = dict(self._p._store.proactive_candidate_sessions.items())
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
        self._require_legacy_session_api()
        sk = (
            session_key
            or (
                str(getattr(event_or_session, "unified_msg_origin", ""))
                if event_or_session
                else ""
            )
            or "default"
        )
        from sylanne_alpha.diagnostics_surface import proactive_decision

        host = self._p._host(sk)
        surface = host.diagnostics()
        decision = proactive_decision(surface)
        # v2core 空闲触达咨询：沉默积累（你的节律超期 + 她憋着的话）让 reach 胜出时，
        # 把决策升格为 reach_out——外部主动桥轮询本方法，这是"她主动找你"的真实入口。
        # 防连发不在这里造闸：下游 dispatch 自带冷却/静默期机制。
        try:
            from sylanne_alpha.v2core.integration import merge_idle_reach_into_decision

            decision = await merge_idle_reach_into_decision(self._p, sk, decision)
        except Exception:
            pass
        return decision

    async def _request_scoped_dispatch(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Enqueue through this scheduler's immutable scoped gateway only."""

        persistence = self.persistence
        if persistence is None:
            return {"dispatched": False, "reason": "scoped_outbox_required"}
        scope = persistence.scope
        event_or_session = args[0] if args else kwargs.get("event_or_session")
        dry_run = bool(kwargs.get("dry_run", False))
        sk = str(
            kwargs.get("session_key", "")
            or (
                getattr(event_or_session, "unified_msg_origin", "")
                if event_or_session is not None
                else ""
            )
            or ""
        ).strip()
        if sk and sk != scope.storage_token:
            return {
                "dispatched": False,
                "reason": "scope_mismatch",
                "session_key": sk,
                "dry_run": dry_run,
            }
        session_key = scope.storage_token
        text = kwargs.get("text")
        if type(text) is not str or not text:
            for key in ("message_text", "motivation_text", "candidate_context"):
                candidate = kwargs.get(key)
                if type(candidate) is str and candidate:
                    text = candidate
                    break
        if type(text) is not str or not text:
            return {
                "dispatched": False,
                "reason": "scoped_message_required",
                "session_key": session_key,
                "dry_run": dry_run,
            }
        idempotent = kwargs.get("idempotent", False)
        if type(idempotent) is not bool:
            return {
                "dispatched": False,
                "reason": "invalid_idempotency",
                "session_key": session_key,
                "dry_run": dry_run,
            }
        expires_at_ms = kwargs.get("expires_at_ms")
        if expires_at_ms is not None and (
            type(expires_at_ms) is not int or expires_at_ms < 0
        ):
            return {
                "dispatched": False,
                "reason": "invalid_expiry",
                "session_key": session_key,
                "dry_run": dry_run,
            }
        if dry_run:
            return {
                "dispatched": False,
                "would_dispatch": True,
                "queued": False,
                "session_key": session_key,
                "dry_run": True,
            }
        enqueue = getattr(self._p, "enqueue_scoped_proactive_intent", None)
        if not callable(enqueue):
            enqueue = getattr(self._p, "_enqueue_scoped_proactive_intent", None)
        if not callable(enqueue):
            return {
                "dispatched": False,
                "reason": "scoped_outbox_required",
                "session_key": session_key,
            }
        try:
            result = enqueue(
                scope,
                text=text,
                idempotent=idempotent,
                expires_at_ms=expires_at_ms,
            )
            if inspect.isawaitable(result):
                result = await result
        except asyncio.CancelledError:
            raise
        except Exception:
            result = None
        if result is None:
            return {
                "dispatched": False,
                "reason": "scoped_enqueue_rejected",
                "session_key": session_key,
            }
        return {
            "dispatched": True,
            "queued": True,
            "delivery_id": getattr(result, "delivery_id", None),
            "session_key": session_key,
            "dry_run": False,
        }

    async def request_dispatch(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """主动发言 dispatch：决策 → 桥接发送（或 dry_run 只返回决策）。"""

        if self._scoped_components is not None:
            return await self._request_scoped_dispatch(*args, **kwargs)
        self._require_legacy_session_api()
        from sylanne_alpha.engine_adapter import derive_should_send

        event_or_session = args[0] if args else kwargs.get("event_or_session")
        dry_run = bool(kwargs.get("dry_run", False))
        force = bool(kwargs.get("force", False))
        sk = str(
            kwargs.get("session_key", "")
            or (
                getattr(event_or_session, "unified_msg_origin", "")
                if event_or_session is not None
                else ""
            )
            or ""
        ).strip()
        if not sk:
            return {"dispatched": False, "reason": "no_session_key", "dry_run": dry_run}

        # A live scoped runtime owns an opaque SessionScope, not a reusable raw
        # session address.  Its proactive work must be issued as a sealed
        # DeliveryOutbox intent by the scoped delivery owner.
        if self._bound_session_runtime(sk) is not None:
            return {
                "dispatched": False,
                "reason": "scoped_outbox_required",
                "session_key": sk,
            }

        dispatch_req = self.build_dispatch_request(session_key=sk)
        block = self.dispatch_blocked_reason(
            dispatch=dispatch_req,
            event_or_session=event_or_session,
            dry_run=dry_run,
            force=force,
        )
        if block:
            return {
                "dispatched": False,
                "reason": block,
                "session_key": sk,
                "dry_run": dry_run,
            }

        decision = await self.get_speech_decision(
            event_or_session=event_or_session, session_key=sk
        )
        guard = {"allowed": decision.get("allowed", True)}
        if not derive_should_send(decision, guard):
            return {
                "dispatched": False,
                "reason": f"action_{decision.get('action', 'hold')}",
                "session_key": sk,
                "decision": decision,
                "dry_run": dry_run,
            }

        if dry_run:
            return {
                "dispatched": False,
                "would_dispatch": True,
                "session_key": sk,
                "decision": decision,
                "dry_run": True,
            }

        cfg = self._p.config or {}
        bridge = getattr(self._p, "_proactive_bridge", None)
        bridge_on = bool(cfg.get("sylanne_alpha_proactive_bridge_enabled", False))
        if bridge is None or not bridge_on or not bridge.available():
            return {
                "dispatched": False,
                "reason": "proactive_bridge_unavailable",
                "session_key": sk,
                "decision": decision,
            }

        allowed, gate_reason = bridge.should_dispatch_now(sk)
        if not allowed:
            return {
                "dispatched": False,
                "reason": f"bridge_gated:{gate_reason}",
                "session_key": sk,
                "decision": decision,
            }

        host = self._p._host(sk)
        surface = host.diagnostics()
        reason_code = await bridge.infer_reason_code(sk, surface=surface)
        mood = ""
        body = surface.get("body", {}) if isinstance(surface.get("body"), dict) else {}
        pulse = body.get("pulse", {}) if isinstance(body.get("pulse"), dict) else {}
        mood = str(pulse.get("mood_label", "") or pulse.get("mood", "") or "").strip()
        motivation = bridge.build_motivation_text(
            str(decision.get("reason", "") or "想找你聊聊"),
            mood,
            reason_code=reason_code,
            session_key=sk,
        )
        result = await bridge.dispatch(sk, motivation)
        if result.get("dispatched"):
            # T2-05 MAJOR-1 修复：user_followup 标签的消息真的发出去了才消费掉
            # 产生该标签的那条待跟进线索——否则它会一直"到期"，把接下来每一次
            # 主动发言都贴上一模一样的标签文案（issue-43 同源的内容复读）。
            try:
                bridge.consume_followup_on_dispatch(sk, reason_code)
            except Exception:  # noqa: BLE001
                pass  # 消费失败绝不阻断已经发出的 dispatch
            last_sent = getattr(self._p, "_proactive_dispatch_last_sent", None)
            if not isinstance(last_sent, dict):
                last_sent = {}
                self._p._proactive_dispatch_last_sent = last_sent
            now = (
                self._p._observed_now()
                if callable(self._p._observed_now)
                else self._p._observed_now
            )
            last_sent[sk] = float(now)
            # Wave 4（review learning-loop high）：主动消息也是真出站回复，刷新 reflex 续聊锚点。
            # 否则她主动 ping、用户秒回，下一轮 reflex_learn 仍拿很久前的反应式回复时刻当锚，
            # 把"被秒回"误判成"被忽略"灌进虚假负奖励——恰好砸 Wave 4 的 alive-test。零 IO，吞错。
            try:
                _sc = getattr(self._p, "_self_core", None)
                if _sc is not None and hasattr(_sc, "mark_bot_reply"):
                    _sc.mark_bot_reply(sk, float(now))
            except Exception:  # noqa: BLE001
                pass  # 学习锚点更新绝不阻断 dispatch

        return {
            **result,
            "session_key": sk,
            "decision": decision,
            "dry_run": False,
        }

    async def judge_topic(self, session_key: str = "", **kwargs: Any) -> dict[str, Any]:
        self._require_legacy_session_api()
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
        if self._scoped_components is not None and not session_key.startswith("relation_v1_"):
            raise ValueError("scoped scheduler accepts only an opaque relation token")
        if session_key not in self._ritual_registry:
            self._ritual_registry[session_key] = {}
        self._ritual_registry[session_key][ritual_name] = (start_hour, end_hour)

    def unregister_ritual(self, session_key: str, ritual_name: str) -> None:
        """移除一个已注册的仪式。

        Args:
            session_key: 会话标识。
            ritual_name: 仪式名称。
        """
        if self._scoped_components is not None and not session_key.startswith("relation_v1_"):
            raise ValueError("scoped scheduler accepts only an opaque relation token")
        if session_key in self._ritual_registry:
            self._ritual_registry[session_key].pop(ritual_name, None)

    def _last_user_ts(self, session_key: str) -> float:
        """用户最后消息时间：本地缓存优先，回落 SessionStateStore（T2 双源对齐）。"""
        if self._scoped_components is not None:
            return float(self._last_message_times.get("_scoped", 0.0) or 0.0)
        ts = float(self._last_message_times.get(session_key, 0.0) or 0.0)
        if ts > 0:
            return ts
        store = getattr(self._p, "_store", None)
        if store is not None:
            return float(store.last_user_message_time.get(session_key, 0.0) or 0.0)
        return 0.0

    def record_message_time(self, session_key: str, ts: float | None = None) -> None:
        """记录用户最后一次发消息的时间。

        Args:
            session_key: 会话标识。
            ts: 时间戳，默认为当前时间。
        """
        self._require_legacy_session_api()
        when = ts if ts is not None else time.time()
        self._last_message_times[session_key] = when
        store = getattr(self._p, "_store", None)
        if store is not None:
            store.last_user_message_time.set(session_key, when)

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
        if self._scoped_components is not None and not session_key.startswith("relation_v1_"):
            raise ValueError("scoped scheduler accepts only an opaque relation token")
        if now is None:
            now = time.time()

        rituals = self._ritual_registry.get(session_key)
        if not rituals:
            return None

        current_hour = time.localtime(now).tm_hour
        last_msg = self._last_user_ts(session_key)
        silence_seconds = now - last_msg if last_msg > 0 else float("inf")

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

    # ------------------------------------------------------------------
    # Scope-v1 session component persistence
    # ------------------------------------------------------------------

    @property
    def persistence(self) -> ScopedPersistenceGateway | None:
        components = self._scoped_components
        return None if components is None else components.gateway

    def record_scoped_feedback(self, timestamp: float, rating: str) -> None:
        """Record feedback for the captured scope with no session argument."""

        if self._scoped_components is None:
            raise ValueError("scoped persistence is not configured")
        self._feedback_history.append(
            {
                "timestamp": float(timestamp),
                "rating": str(rating),
                "recorded_at": time.time(),
            }
        )

    def record_scoped_message_time(self, ts: float | None = None) -> None:
        """Set this frozen session's last-user timestamp without a key lookup."""

        if self._scoped_components is None:
            raise ValueError("scoped persistence is not configured")
        self._last_message_times["_scoped"] = time.time() if ts is None else float(ts)

    def scoped_last_message_time(self) -> float:
        if self._scoped_components is None:
            raise ValueError("scoped persistence is not configured")
        return float(self._last_message_times.get("_scoped", 0.0) or 0.0)

    def register_scoped_ritual(self, ritual_name: str, start_hour: int, end_hour: int) -> None:
        """Register a session-local timing hint without a raw selector."""

        if self._scoped_components is None:
            raise ValueError("scoped persistence is not configured")
        self._ritual_registry.setdefault("_scoped", {})[str(ritual_name)] = (
            int(start_hour),
            int(end_hour),
        )

    def check_scoped_ritual_absence(self, now: float | None = None) -> str | None:
        """Check only the scoped local ritual bucket."""

        if self._scoped_components is None:
            raise ValueError("scoped persistence is not configured")
        if now is None:
            now = time.time()
        rituals = self._ritual_registry.get("_scoped")
        if not rituals:
            return None
        current_hour = time.localtime(now).tm_hour
        silence_seconds = now - self.scoped_last_message_time() if self.scoped_last_message_time() > 0 else float("inf")
        for ritual_name, (start_hour, end_hour) in rituals.items():
            in_window = (
                start_hour <= current_hour <= end_hour
                if start_hour <= end_hour
                else current_hour >= start_hour or current_hour <= end_hour
            )
            if in_window and silence_seconds >= 30 * 60:
                return ritual_name
        return None

    def _scoped_payload(self) -> dict[str, object]:
        relation_rituals = {
            relation_token: {
                name: [int(hours[0]), int(hours[1])]
                for name, hours in rituals.items()
            }
            for relation_token, rituals in self._ritual_registry.items()
            if relation_token == "_scoped" or relation_token.startswith("relation_v1_")
        }
        feedback = [
            {
                key: value
                for key, value in item.items()
                if key != "session_key"
            }
            for item in self._feedback_history
            if isinstance(item, dict)
        ]
        return {
            "schema_version": "sylanne.scheduler.scoped.v1",
            "rituals": relation_rituals,
            "last_message_time": self.scoped_last_message_time(),
            "feedback_history": feedback,
        }

    def _restore_scoped_state(self) -> None:
        components = self._scoped_components
        if components is None:
            return
        payload = components.load("scheduler")
        if payload is None:
            return
        rituals = payload.get("rituals")
        if isinstance(rituals, dict):
            for relation_token, entries in rituals.items():
                if (
                    not isinstance(relation_token, str)
                    or (relation_token != "_scoped" and not relation_token.startswith("relation_v1_"))
                    or not isinstance(entries, dict)
                ):
                    continue
                parsed: dict[str, tuple[int, int]] = {}
                for name, hours in entries.items():
                    if (
                        isinstance(name, str)
                        and isinstance(hours, list)
                        and len(hours) == 2
                        and all(type(hour) is int and 0 <= hour <= 23 for hour in hours)
                    ):
                        parsed[name] = (hours[0], hours[1])
                if parsed:
                    self._ritual_registry[relation_token] = parsed
        last_message_time = payload.get("last_message_time")
        if isinstance(last_message_time, (int, float)):
            self._last_message_times["_scoped"] = float(last_message_time)
        history = payload.get("feedback_history")
        if isinstance(history, list):
            self._feedback_history = collections.deque(
                (dict(item) for item in history if isinstance(item, dict)),
                maxlen=200,
            )

    def flush_scoped_state(self) -> int:
        components = self._scoped_components
        if components is None:
            raise ValueError("scoped persistence is not configured")
        return components.save("scheduler", self._scoped_payload())

    def schedule_scoped_flush(self, *, delay_seconds: float) -> asyncio.Task[bool]:
        components = self._scoped_components
        if components is None:
            raise ValueError("scoped persistence is not configured")
        return components.schedule_save(
            "scheduler",
            self._scoped_payload(),
            delay_seconds=delay_seconds,
        )
