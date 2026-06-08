"""计算层适配器 —— 把 vendored SylannEngine SDK 的 Surface 翻译成 Sylanne-next
业务层期望的契约（兼容 surface 结构）。

深接入策略：业务层只通过本适配器拿计算结果，不再直穿计算内部。SDK 的 Surface
字段命名与现有不同（needs.expression vs need_expression、boundary.pressure vs
immunity.boundary_pressure 等），本层负责双向翻译，让下游改动最小。

字段映射（已对照 SDK 真实 process 输出核实，非凭文档）：
  SDK state.needs.expression      → body.needs.need_expression
  SDK state.needs.quiet           → body.needs.need_quiet
  SDK state.needs.recovery        → body.needs.need_repair
  SDK state.needs.contact         → body.needs.need_contact (新增)
  SDK state.boundary.pressure     → body.immunity.boundary_pressure
  SDK state.valence.warmth        → body.temperature.warmth
  SDK decision.{action,reason_code,confidence,urgency} → decision.*
  SDK guard.{allowed,reason,risk_score,constraints}    → guard.*
  host_payload.should_send        ← 推导: guard.allowed && action∈SEND_ACTIONS
"""

from __future__ import annotations

from typing import Any

try:
    from astrbot.api import logger  # type: ignore
except ImportError:
    import logging as _logging

    logger = _logging.getLogger("astrbot_plugin_sylanne")  # type: ignore

# decision.action 中代表"应该主动发出"的动作集合（用于推导 should_send）。
# 注意：SDK adapter._ACTION_MAP 会把内部 "repair" 输出为 "recover"，故这里用 SDK
# 真实输出的动作名 "recover"（不是 "repair"），否则 repair 意图的 should_send 恒 False。
SEND_ACTIONS = frozenset({"express", "reach_out", "recover"})


def _f(d: Any, *keys: str, default: float = 0.0) -> float:
    """安全地从嵌套 dict 取 float。"""
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, {})
    try:
        return float(cur)
    except (TypeError, ValueError):
        return default


def sdk_state_to_body(sdk_state: dict[str, Any]) -> dict[str, Any]:
    """SDK Surface.state → 旧 body 结构（needs/immunity/temperature）。

    只翻译业务层实际消费的字段（见模块 docstring 映射表）。
    """
    needs = sdk_state.get("needs", {}) if isinstance(sdk_state.get("needs"), dict) else {}
    boundary = sdk_state.get("boundary", {}) if isinstance(sdk_state.get("boundary"), dict) else {}
    valence = sdk_state.get("valence", {}) if isinstance(sdk_state.get("valence"), dict) else {}
    connection = sdk_state.get("connection", {}) if isinstance(sdk_state.get("connection"), dict) else {}
    return {
        "needs": {
            "need_expression": _f(needs, "expression"),
            "need_quiet": _f(needs, "quiet"),
            "need_repair": _f(needs, "recovery"),
            "need_contact": _f(needs, "contact"),
        },
        "immunity": {
            "boundary_pressure": _f(boundary, "pressure"),
            "autonomy": _f(boundary, "autonomy", default=1.0),
            "interruption_budget": _f(boundary, "interruption_budget", default=1.0),
            "cooldown": _f(boundary, "cooldown"),
        },
        "temperature": {
            # SDK 有 valence.warmth 与 connection.warmth 两个；business 的
            # "亲密/熟悉感"语义更贴近 connection.warmth（关系温暖），优先用它，
            # 回退 valence.warmth。
            "warmth": _f(connection, "warmth") or _f(valence, "warmth"),
        },
    }


def derive_should_send(decision: dict[str, Any], guard: dict[str, Any]) -> bool:
    """SDK 无 host_payload.should_send，从 guard.allowed + decision.action 推导。"""
    if not isinstance(guard, dict) or guard.get("allowed") is False:
        return False
    action = str((decision or {}).get("action", "")).strip().lower()
    return action in SEND_ACTIONS


def sdk_surface_to_compat(surface: dict[str, Any]) -> dict[str, Any]:
    """SDK Surface → Sylanne-next 业务层兼容 surface。

    产出含：body(旧结构) / decision / guard / host_payload(含推导的 should_send) /
    schema_version / session_key / turns，覆盖现有 proactive/pipeline 消费契约。
    """
    state = surface.get("state", {}) if isinstance(surface.get("state"), dict) else {}
    decision = surface.get("decision", {}) if isinstance(surface.get("decision"), dict) else {}
    guard = surface.get("guard", {}) if isinstance(surface.get("guard"), dict) else {}
    body = sdk_state_to_body(state)
    reason_code = str(decision.get("reason_code", "life_rhythm") or "life_rhythm")
    host_payload = {
        "should_send": derive_should_send(decision, guard),
        "reason_code": reason_code,
        "action": str(decision.get("action", "")),
        "reason": str(decision.get("reason", "")),
    }
    return {
        "schema_version": surface.get("schema_version", ""),
        "session_key": surface.get("session_id", ""),
        "turns": surface.get("turns", 0),
        "body": body,
        "decision": {
            "action": str(decision.get("action", "")),
            "reason_code": reason_code,
            "confidence": _f(decision, "confidence"),
            "urgency": _f(decision, "urgency"),
        },
        "guard": {
            "allowed": bool(guard.get("allowed", True)),
            "reason": str(guard.get("reason", "")),
            "risk_score": _f(guard, "risk_score"),
            "constraints": list(guard.get("constraints", []) or []),
        },
        "host_payload": host_payload,
        # 透传 SDK 原始 surface 供需要新结构的下游用（WebUI 等）
        "sdk_surface": surface,
    }


class EngineFacade:
    """业务层访问计算的唯一入口。内部持 vendored SylannEngine，对外只给兼容 surface。

    生命周期：构造 → await start() → await process(...) → await shutdown()。
    懒初始化 SDK，避免无 event loop 时构造失败。
    """

    def __init__(self, data_dir: str, llm: Any, *, mode: str = "lite",
                 force_backend: str = "python", assessor_enabled: bool = False) -> None:
        self._data_dir = data_dir
        self._llm = llm
        self._mode = mode
        self._force_backend = force_backend
        self._assessor_enabled = assessor_enabled
        self._engine: Any = None
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        from sylanne_alpha._engine.sylanne_core import SylanneEngine, SylanneConfig

        cfg = SylanneConfig(
            mode=self._mode,
            force_backend=self._force_backend,
            assessor_enabled=self._assessor_enabled,
        )
        self._engine = SylanneEngine(data_dir=self._data_dir, llm=self._llm, config=cfg)
        await self._engine.start()
        self._started = True

    @property
    def available(self) -> bool:
        return self._started and self._engine is not None

    async def process(self, session_key: str, text: str, *, confidence: float | None = None,
                      flags: list[str] | None = None, now: float | None = None,
                      values: dict[str, float] | None = None) -> dict[str, Any]:
        """处理一条消息，返回业务层兼容 surface。引擎未就绪时抛 RuntimeError。"""
        if not self.available:
            raise RuntimeError("EngineFacade not started")
        surface = await self._engine.process(
            session_key, text, confidence=confidence, flags=flags, now=now, values=values
        )
        return sdk_surface_to_compat(surface)

    async def state(self, session_key: str) -> dict[str, Any]:
        """取当前状态的兼容 surface（不推进 tick）。"""
        if not self.available:
            raise RuntimeError("EngineFacade not started")
        surface = await self._engine.state(session_key)
        return sdk_surface_to_compat(surface)

    async def reset(self, session_key: str) -> None:
        if self.available:
            await self._engine.reset(session_key)

    async def shutdown(self) -> None:
        if self._engine is not None:
            try:
                await self._engine.shutdown()
            finally:
                self._started = False


