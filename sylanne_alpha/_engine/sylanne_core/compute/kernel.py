"""计算核心调度器模块。

AlphaKernel 是 Sylanne-Embodiment 的中枢调度器，驱动 7 层计算管线：
1. 身体状态演化（body.apply）
2. 人格漂移（personality drift）
3. 道德修复层（moral repair）
4. 可错性层（fallibility）
5. 关系时间层（relational time）
6. 决策层（_decide）
7. 守卫层（_guard）

核心职责：
- tick(): 接收事件，驱动完整管线，返回 surface（对外可见的状态快照）
- surface(): 生成当前状态的完整对外表示
- snapshot(): 生成可持久化的完整内部状态
- _integrated_self(): 生成自我整合仲裁结果（决定 response posture/allowed actions）

与其他组件的关系：
- SylanneAlphaHost 持有一个 AlphaKernel 实例
- ComputationSpine 负责 Void-Scar Engine / HDC / HGT 等底层计算
- prompt_surface 模块负责将 kernel 状态渲染为 prompt fragment
- personality 模块负责人格特质的初始化和漂移
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from .attention import focus_information_flood
from .body import SCHEMA_VERSION, AlphaBodyState
from .computation_spine import ComputationSpine
from .hot_pool import HotPool
from .importer import import_legacy_body
from .personality import drift_sylanne_traits, initial_personality
from .prompt_surface import (
    render_diagnostics,
    render_host_payload,
    render_prompt_context_bus,
    render_prompt_fragment,
)
from .workset import build_fragment_workset

try:
    from .resonance_integration import ResonanceSpine

    _DEFAULT_SPINE: type = ResonanceSpine
except ImportError:
    ResonanceSpine = ComputationSpine  # type: ignore[assignment, misc]
    _DEFAULT_SPINE = ComputationSpine

if TYPE_CHECKING:
    from ..config import DimensionProfile
    from ..telemetry import DistillationSink

logger = logging.getLogger("sylanne_core")

# 各 alpha 层的 schema 版本标识，用于前向兼容检查
SCHEMA_RELATIONAL_TIME_VERSION = "sylanne.alpha.relational_time.v1"
SCHEMA_INTEGRATED_SELF_VERSION = "sylanne.alpha.integrated_self.v1"
SCHEMA_AFFECT_DYNAMICS_VERSION = "sylanne.alpha.affect_dynamics.v1"
SCHEMA_MORAL_REPAIR_VERSION = "sylanne.alpha.moral_repair.v1"
SCHEMA_FALLIBILITY_VERSION = "sylanne.alpha.fallibility.v1"
SCHEMA_GROUP_ATMOSPHERE_VERSION = "sylanne.alpha.group_atmosphere.v1"
SCHEMA_PROACTIVE_SOURCE_VERSION = "sylanne.alpha.proactive_source.v1"


def _as_dict(val: Any) -> dict[str, Any]:
    return dict(val) if isinstance(val, dict) else {}


def _safe_int(val: Any, default: int = 0) -> int:
    try:
        return max(0, int(float(val)))
    except (TypeError, ValueError, OverflowError):
        return default


@dataclass(slots=True)
class AlphaKernelEvent:
    """Kernel 层事件数据类。

    由 host 层的 SylanneAlphaHostEvent 转换而来，
    包含 kernel tick 所需的全部输入信息。
    """

    text: str = ""
    values: dict[str, float] = field(default_factory=dict)
    confidence: float = 0.0
    flags: list[str] = field(default_factory=list)
    now: float = 0.0
    event_time: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AlphaKernel:
    """Sylanne-Embodiment 计算核心调度器。

    持有身体状态、人格、道德修复、可错性等全部内部状态，
    通过 tick() 方法驱动完整的 7 层计算管线。

    生命周期：
    - boot(): 从零或旧版数据创建新 kernel
    - restore(): 从持久化快照恢复 kernel
    - tick(): 接收事件，驱动管线，返回 surface
    - snapshot(): 导出可持久化的完整状态
    """

    session_key: str
    body: AlphaBodyState = field(default_factory=AlphaBodyState)
    audit: dict[str, Any] = field(default_factory=dict)
    turns: int = 0
    last_event: dict[str, Any] = field(default_factory=dict)
    previous_event: dict[str, Any] = field(default_factory=dict)
    relational_time: dict[str, Any] = field(default_factory=dict)
    last_decision: dict[str, Any] = field(default_factory=dict)
    last_guard: dict[str, Any] = field(default_factory=dict)
    personality: dict[str, Any] = field(default_factory=dict)
    moral_repair: dict[str, Any] = field(default_factory=dict)
    fallibility: dict[str, Any] = field(default_factory=dict)
    computation: ComputationSpine | ResonanceSpine = field(default_factory=_DEFAULT_SPINE)
    hot_pool: HotPool = field(default_factory=HotPool)
    _last_computation_result: dict[str, Any] = field(default_factory=dict)
    _cached_vector_summary: dict[str, float] | None = field(default=None, repr=False)
    # Unresolved emotional pressure (allostatic threshold bias for proactive reach-out).
    # Asymmetric-leak scalar: spikes on a hurtful/negative read, leaks slowly, clears
    # when soothed or after a successful reach-out. Lowers reach_out's need_contact
    # threshold so a bruised exchange brings her back sooner than flat silence would —
    # but never bypasses _guard (opt-in/cooldown/budget/sovereignty all stay in front).
    _affect_debt: float = 0.0
    # Optional distillation corpus sink (runtime-only; never serialized). Attached
    # by the host after load when SylanneConfig.training_data_sink is on; otherwise
    # stays None so the per-tick guard is a single None check (zero cost when off).
    _telemetry_sink: DistillationSink | None = field(default=None, repr=False, compare=False)

    @classmethod
    def boot(
        cls,
        session_key: str,
        legacy: dict[str, Any] | None = None,
        profile: DimensionProfile | None = None,
        *,
        pel_enabled: bool = False,
    ) -> AlphaKernel:
        """从零创建或从旧版数据迁移创建 kernel。"""
        if legacy is None:
            kernel = cls(session_key=session_key)
        else:
            body, audit, turns = import_legacy_body(legacy)
            kernel = cls(session_key=session_key, body=body, audit=audit, turns=turns)
        if profile is not None:
            kernel.computation = _DEFAULT_SPINE(profile=profile, pel_enabled=pel_enabled)
            kernel.hot_pool = HotPool(n_dims=profile.emotion_dim, mode=profile.mode)
        return kernel

    @classmethod
    def restore(
        cls,
        snapshot: dict[str, Any],
        profile: DimensionProfile | None = None,
        *,
        pel_enabled: bool = False,
    ) -> AlphaKernel:
        """从持久化快照恢复 kernel，对每个字段做类型安全的反序列化。"""
        kernel = cls(
            session_key=str(snapshot.get("session_key") or "default"),
            body=AlphaBodyState.from_dict(_as_dict(snapshot.get("body"))),
            audit=_as_dict(snapshot.get("audit")),
            turns=_safe_int(snapshot.get("turns")),
            last_event=_as_dict(snapshot.get("last_event")),
            previous_event=_as_dict(snapshot.get("previous_event")),
            relational_time=_as_dict(snapshot.get("relational_time")),
            last_decision=_as_dict(snapshot.get("last_decision")),
            last_guard=_as_dict(snapshot.get("last_guard")),
            personality=_as_dict(snapshot.get("personality")),
            moral_repair=_as_dict(snapshot.get("moral_repair")),
            fallibility=_as_dict(snapshot.get("fallibility")),
        )
        if profile is not None:
            kernel.computation = _DEFAULT_SPINE(profile=profile, pel_enabled=pel_enabled)
            kernel.hot_pool = HotPool(n_dims=profile.emotion_dim, mode=profile.mode)
        if "computation" in snapshot and isinstance(snapshot["computation"], dict):
            kernel.computation.from_dict(snapshot["computation"])
        if "hot_pool" in snapshot and isinstance(snapshot["hot_pool"], dict):
            mode = profile.mode if profile else "lite"
            n_dims = profile.emotion_dim if profile else 16
            kernel.hot_pool = HotPool.from_dict(snapshot["hot_pool"], n_dims=n_dims, mode=mode)
        if "_last_computation_result" in snapshot and isinstance(
            snapshot["_last_computation_result"], dict
        ):
            kernel._last_computation_result = snapshot["_last_computation_result"]
        try:
            kernel._affect_debt = max(0.0, min(1.0, float(snapshot.get("_affect_debt", 0.0))))
        except (TypeError, ValueError):
            kernel._affect_debt = 0.0
        return kernel

    def tick(
        self,
        event: AlphaKernelEvent | dict[str, Any] | None = None,
        assessment: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """驱动完整的 7 层计算管线。

        执行顺序：
        1. body.apply() — 身体状态向量演化
        2. computation.process() — Void-Scar Engine / HDC / HGT 计算
        3. _evolve_alpha_layers() — 人格漂移 + 道德修复 + 可错性
        4. 更新 relational_time — 关系时间层
        5. _decide() — 基于需求的行动决策
        6. _guard() — 安全守卫（主权/预算/风险检查）
        7. surface() — 生成对外可见的状态快照

        Args:
            event: 输入事件（AlphaKernelEvent 或原始字典）
            assessment: 可选的 LLM assessor 评估结果

        Returns:
            包含 state/decision/guard/surface 的结果字典
        """
        self._cached_vector_summary = None
        event = self._event(event)
        try:
            return self._tick_inner(event, assessment)
        except Exception:
            logger.warning("tick failed, returning fallback", exc_info=True)
            return {
                "state": self.body,
                "decision": self.last_decision or self._decide(),
                "guard": self.last_guard or self._guard(self.last_decision or self._decide()),
                "surface": self.surface(),
            }

    def _tick_inner(
        self,
        event: AlphaKernelEvent,
        assessment: dict[str, Any] | None,
    ) -> dict[str, Any]:
        # Container guard for the public host.on_request(assessment=...) boundary: a
        # non-dict assessment would AttributeError in _update_affect_debt (its except
        # catches only TypeError/ValueError) and in the spine. Normalize once so all
        # downstream consumers treat a malformed container as "no assessment".
        if assessment is not None and not isinstance(assessment, dict):
            assessment = None
        self.body.apply(
            text=event.text,
            flags=event.flags,
            confidence=event.confidence,
            now=event.now,
        )
        personality = self._personality()
        if personality:
            self.computation.apply_personality(personality.get("traits", personality))
            self.hot_pool.apply_personality(personality.get("traits", personality))
        # Hot pool: amplify event during cascade, then tick
        event_dict = {
            "confidence": event.confidence,
            "flags": list(event.flags),
            "values": dict(event.values),
        }
        self.hot_pool.amplify_event(event_dict)
        # dialogue_quality 走 values 通道（"额外数值信号"）→ 透传给 spine 的 canonical
        # 漂移入参。滞后反馈：上一轮回复的自评在本轮 process 时随 values 一并进来。
        # values 是不可信输入，非数字（str/list/dict）时安全回退为 None，不让一条坏值掀翻整个 tick。
        _dq_raw = event.values.get("dialogue_quality")
        _dq: float | None = None
        if _dq_raw is not None:
            try:
                _dq = float(_dq_raw)
            except (ValueError, TypeError):
                logger.warning("ignoring non-numeric dialogue_quality: %r", _dq_raw)
        self._last_computation_result = self.computation.process(
            event.text,
            event.now,
            assessment=assessment,
            dialogue_quality=_dq,
        )
        # Emotional debt is updated from this tick's read before _decide reads the
        # reach_out threshold — a bruising exchange brings her back sooner than flat
        # silence. Only biases the threshold; _guard still gates every outward action.
        self._update_affect_debt(assessment)
        collapse_record = self.hot_pool.tick(body=self.body, spine=self.computation)
        if collapse_record is not None:
            self._apply_collapse(collapse_record)
        self._evolve_alpha_layers(event)
        self.turns += 1
        previous = dict(self.last_event)
        self.previous_event = previous
        self.last_event = {
            "text": event.text,
            "confidence": event.confidence,
            "flags": list(event.flags),
            "now": event.now,
            "event_time": dict(event.event_time),
            "values": dict(event.values),
        }
        self.relational_time = self._relational_time_layer(
            current=self.last_event, previous=previous
        )
        self.last_decision = self._decide()
        self.last_guard = self._guard(self.last_decision)
        # Distillation corpus capture (par1): assessed ticks only, numeric-only,
        # never the raw text. A None sink is a single is-check — zero cost when off.
        if self._telemetry_sink is not None and assessment is not None:
            self._capture_telemetry(assessment)
        return {
            "state": self.body,
            "decision": self.last_decision,
            "guard": self.last_guard,
            "surface": self.surface(),
        }

    def _apply_collapse(self, record: Any) -> None:
        """Apply personality collapse deltas from hot pool phase transition."""
        traits = self._personality()
        if not traits:
            return
        trait_dict = traits.get("traits", traits)
        pre_snapshot = dict(trait_dict)
        for trait, delta in record.trait_deltas.items():
            if trait in trait_dict:
                trait_dict[trait] = max(0.05, min(0.95, trait_dict[trait] + delta))
        record.pre_collapse_traits = pre_snapshot
        record.post_collapse_traits = dict(trait_dict)
        self.computation.apply_personality(trait_dict)

    def surface(self) -> dict[str, Any]:
        """生成当前状态的完整对外表示（供 WebUI / prompt injection 使用）。"""
        decision = self.last_decision or self._decide()
        guard = self.last_guard or self._guard(decision)
        workset = self._workset(decision, guard)
        return {
            "schema_version": SCHEMA_VERSION,
            "session_key": self.session_key,
            "turns": self.turns,
            "body": self.body.to_dict(),
            "decision": decision,
            "guard": guard,
            "workset": workset,
            "host_payload": self._host_payload(decision, guard),
            "diagnostics": self._diagnostics(decision, guard, workset),
            "hot_pool": self.hot_pool.diagnostics(),
        }

    def snapshot(self) -> dict[str, Any]:
        """导出可持久化的完整内部状态（供 AlphaRuntime 序列化到磁盘）。"""
        return {
            "schema_version": SCHEMA_VERSION,
            "session_key": self.session_key,
            "turns": self.turns,
            "body": self.body.to_dict(),
            "audit": self.audit,
            "last_event": self.last_event,
            "previous_event": self.previous_event,
            "relational_time": self.relational_time,
            "last_decision": self.last_decision,
            "last_guard": self.last_guard,
            "personality": self._personality(),
            "moral_repair": self._moral_repair_state(),
            "fallibility": self._fallibility_state(),
            "computation": self.computation.to_dict(),
            "hot_pool": self.hot_pool.to_dict(),
            "_last_computation_result": self._last_computation_result,
            "_affect_debt": self._affect_debt,
        }

    def _diagnostics(
        self,
        decision: dict[str, Any],
        guard: dict[str, Any],
        workset: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return render_diagnostics(self, decision, guard, workset)

    def _workset(self, decision: dict[str, Any], guard: dict[str, Any]) -> dict[str, Any]:
        vector_summary = self._vector_summary()
        primary = "guard" if not guard["allowed"] else decision.get("reason_code", "body")
        if primary not in {
            "body",
            "guard",
            "assessor",
            "dialogue",
            "personality",
            "attention",
        }:
            primary = "body"
        interests = self._interests()
        flood = focus_information_flood(
            [
                {
                    "speaker": self.last_event.get("speaker") or self.session_key,
                    "text": self.last_event.get("text", ""),
                    "flags": self.last_event.get("flags", []),
                    "confidence": self.last_event.get("confidence", 0.0),
                    "now": self.last_event.get("now", 0.0),
                }
            ],
            interests=interests,
        )
        return build_fragment_workset(
            session_key=self.session_key,
            fragments=[str(self.last_event.get("text") or "")],
            memory_matches=[],
            dialogue={
                "flags": list(self.last_event.get("flags", [])),
                "confidence": self.last_event.get("confidence", 0.0),
            },
            personality={
                "plasticity": vector_summary["plasticity"],
                "drift_policy": "slow",
            },
            body=vector_summary,
            assessor={
                "lane": "local",
                "suggestion": decision["action"],
                "confidence": decision["confidence"],
            },
            guard=guard,
            attention={
                "primary": primary,
                "weights": {
                    "body": vector_summary["need"],
                    "guard": guard["risk_score"],
                },
                "pressure": flood["pressure"],
                "flood_policy": flood["policy"],
                "interests": flood["interests"],
            },
        )

    def _interests(self) -> dict[str, float]:
        vector = self._vector_summary()
        return {
            "记忆": max(0.2, vector["plasticity"]),
            "边界": max(0.2, vector["risk"]),
            "身体": max(0.2, vector["need"]),
            "attention": max(0.2, vector["plasticity"]),
            "Sylanne": 0.5,
        }

    def _evolve_alpha_layers(self, event: AlphaKernelEvent) -> None:
        """演化 alpha 层：人格漂移 + 道德修复状态 + 可错性状态。

        人格漂移受 Embodiment 计算脊柱的约束（如果可用）。
        道德修复和可错性根据事件标志和置信度更新计数器和约束。
        """
        # Drift Sylanne traits (fast, text-based) with Embodiment bounds from computation spine
        embodiment = (
            self.computation.embodiment_bounds()
            if hasattr(self.computation, "embodiment_bounds")
            else None
        )
        self.personality = drift_sylanne_traits(
            self._personality(),
            event={"text": event.text, "confidence": event.confidence},
            embodiment=embodiment,
        )
        flags = set(event.flags)
        repair_events = int(self.moral_repair.get("events") or 0)
        if "repair" in flags:
            repair_events += 1
        mr = self._moral_repair_state()
        mr["state"] = "repairing" if repair_events else "stable"
        mr["events"] = repair_events
        mr["repair_need"] = round(self.body.needs["need_repair"], 6)
        self.moral_repair = mr

        fallibility_events = int(self.fallibility.get("events") or 0)
        if "fallibility" in flags or event.confidence < 0.45:
            fallibility_events += 1
        fb = self._fallibility_state()
        fb["events"] = fallibility_events
        fb["claim_caution"] = round(
            max(0.0, min(1.0, (1.0 - event.confidence) + fallibility_events * 0.12)),
            6,
        )
        self.fallibility = fb

    def _personality(self) -> dict[str, Any]:
        if not self.personality:
            self.personality = initial_personality(self.session_key)
        return dict(self.personality)

    def _moral_repair_state(self) -> dict[str, Any]:
        if not self.moral_repair:
            self.moral_repair = {
                "schema_version": SCHEMA_MORAL_REPAIR_VERSION,
                "kind": "moral_repair_state",
                "internal_only": True,
                "read_only": True,
                "state": "stable",
                "events": 0,
                "repair_need": round(self.body.needs["need_repair"], 6),
                "constraints": [
                    "brief_repair_only",
                    "no_guilt_loop",
                    "current_user_text_priority",
                ],
            }
        return dict(self.moral_repair)

    def _fallibility_state(self) -> dict[str, Any]:
        if not self.fallibility:
            self.fallibility = {
                "schema_version": SCHEMA_FALLIBILITY_VERSION,
                "kind": "fallibility_state",
                "internal_only": True,
                "read_only": True,
                "events": 0,
                "claim_caution": 0.0,
                "constraints": [
                    "admit_uncertainty",
                    "correct_once",
                    "no_performative_self_blame",
                ],
            }
        return dict(self.fallibility)

    def _affect_dynamics(self) -> dict[str, Any]:
        body = self.body
        repair_drive = max(
            body.needs["need_repair"],
            body.wound.repair,
            body.wound.open * 0.5,
        )
        expression_drive = max(body.needs["need_expression"], body.temperature.warmth * 0.3)
        return {
            "schema_version": SCHEMA_AFFECT_DYNAMICS_VERSION,
            "kind": "affect_body_coupling",
            "internal_only": True,
            "read_only": True,
            "body_coupling": {
                "repair_drive": round(repair_drive, 6),
                "expression_drive": round(expression_drive, 6),
                "quiet_drive": round(
                    max(
                        body.needs["need_quiet"],
                        body.immunity.boundary_pressure,
                    ),
                    6,
                ),
            },
            "constraints": [
                "weak_style_modulation_only",
                "no_medicalized_body_claims",
                "no_relationship_diagnosis",
            ],
        }

    def _group_atmosphere(self) -> dict[str, Any]:
        flags = set(self.last_event.get("flags", []))
        raw_values = self.last_event.get("values")
        values: dict[str, Any] = dict(raw_values) if isinstance(raw_values, dict) else {}
        heat = max(float(values.get("group_heat") or 0.0), 0.4 if "group" in flags else 0.0)
        interrupt_risk = max(heat * 0.6, self.body.immunity.boundary_pressure)
        return {
            "schema_version": SCHEMA_GROUP_ATMOSPHERE_VERSION,
            "kind": "group_atmosphere",
            "internal_only": True,
            "read_only": True,
            "mode": "group" if "group" in flags else "direct",
            "heat": round(min(1.0, heat), 6),
            "joinability": round(max(0.0, 1.0 - interrupt_risk), 6),
            "interrupt_risk": round(min(1.0, interrupt_risk), 6),
            "constraints": [
                "timing_signal_only",
                "no_group_mind_reading",
                "no_speaking_for_others",
            ],
        }

    def _proactive_source(self, decision: dict[str, Any], guard: dict[str, Any]) -> dict[str, Any]:
        relationship = self.body.relationship_memory()["continuity"]
        drivers = {
            "body_need": round(
                max(
                    self.body.needs["need_contact"],
                    self.body.needs["need_expression"],
                    self.body.needs["need_repair"],
                ),
                6,
            ),
            "relationship_continuity": relationship["weight"],
            "plasticity": round(self.body.nerve.plasticity, 6),
            "interruption_budget": round(self.body.immunity.interruption_budget, 6),
        }
        eligible = bool(
            "proactive" in self.last_event.get("flags", [])
            and guard["allowed"]
            and self.body.immunity.interruption_budget > 0.1
        )
        return {
            "schema_version": SCHEMA_PROACTIVE_SOURCE_VERSION,
            "kind": "proactive_source",
            "internal_only": True,
            "read_only": True,
            "drivers": drivers,
            "decision": "eligible" if eligible else "blocked",
            "reason": decision.get("reason_code", "life_rhythm")
            if eligible
            else guard.get("reason", "not_requested"),
            "constraints": [
                "current_user_sovereignty_first",
                "no_private_memory_recall",
                "cooldown_and_budget_required",
            ],
        }

    def _prompt_context_bus(self, *, integrated_self: dict[str, Any]) -> dict[str, Any]:
        return render_prompt_context_bus(self, integrated_self=integrated_self)

    def _computation_emotion_overlay(self) -> dict[str, float]:
        """Get emotion state from the computation spine's SSM.

        Returns the engine-observed emotion vector which provides a more
        continuous, dynamically-evolved emotion signal than the body's
        discrete state_vector.
        """
        return self.computation.engine.observe()

    def _host_payload(self, decision: dict[str, Any], guard: dict[str, Any]) -> dict[str, Any]:
        return render_host_payload(self, decision, guard)

    def _prompt_fragment(self, decision: dict[str, Any], guard: dict[str, Any]) -> str:
        return render_prompt_fragment(self, decision, guard)

    def _integrated_self(self, decision: dict[str, Any], guard: dict[str, Any]) -> dict[str, Any]:
        """生成自我整合仲裁结果。

        综合 body 状态、guard 结果、关系记忆、影子记忆，
        决定当前的 response_posture（姿态）、allowed_actions、blocked_actions、
        intent_plan（意图计划）等，供 prompt injection 使用。
        """
        vector = self._vector_summary()
        risk_score = max(float(guard.get("risk_score") or 0.0), vector["risk"])
        flags = set(self.last_event.get("flags", []))
        relationship_memory = self.body.relationship_memory()
        shadow_memory = self.body.shadow_memory()
        primary_goal = "answer_current_request"
        if not guard["allowed"] or risk_score >= 0.8 or self.body.immunity.boundary_pressure > 0.75:
            primary_goal = "boundary_guard"
        elif decision["action"] == "repair" or self.body.needs["need_repair"] > 0.2:
            primary_goal = "repair"
        elif "tool" in flags or "task" in flags:
            primary_goal = "tool_task"
        elif decision["confidence"] < 0.45 or self.last_event.get("confidence", 0.0) < 0.35:
            primary_goal = "clarify"
        elif decision["action"] in {"express", "reach_out"}:
            primary_goal = "respond"

        posture = "steady"
        if primary_goal == "boundary_guard":
            posture = "boundary_guarded"
        elif primary_goal == "tool_task":
            posture = "task_focused"
        elif primary_goal == "repair":
            posture = "repair_oriented"
        elif primary_goal == "clarify":
            posture = "careful_clarifying"

        allowed_actions = ["answer_current_request"]
        if primary_goal == "tool_task":
            allowed_actions.append("use_tools")
        if primary_goal == "clarify":
            allowed_actions.append("ask_clarifying_question")
        if primary_goal == "repair":
            allowed_actions.append("repair")
        if guard["allowed"] and risk_score < 0.8:
            allowed_actions.append(decision["action"])
        allowed_actions = list(
            dict.fromkeys(
                action for action in allowed_actions if action not in {"wait", "hold", "withdraw"}
            )
        )

        blocked_actions = [
            "unrequested_relationship_narration",
            "relationship_fact_claim",
            "override_current_user_text",
        ]
        if risk_score >= 0.8 or not guard["allowed"] or self.body.immunity.boundary_pressure > 0.75:
            blocked_actions.extend(["reach_out", "proactive_speech", "relationship_escalation"])
        if "proactive" not in flags:
            blocked_actions.append("unrequested_proactive_speech")
        blocked_actions = list(dict.fromkeys(blocked_actions))

        lanes = ["current_request_first"]
        if primary_goal == "boundary_guard":
            lanes.insert(0, "boundary_first")
        if primary_goal == "repair":
            lanes.append("repair_first")
        if primary_goal == "tool_task":
            lanes.append("tool_task")
        if relationship_memory["continuity"]["event_count"] > 0:
            lanes.append("relationship_memory_advisory")
        if sum(int(value) for value in shadow_memory["signals"].values()) > 0:
            lanes.append("shadow_memory_advisory")

        return {
            "schema_version": SCHEMA_INTEGRATED_SELF_VERSION,
            "kind": "integrated_self_arbitration",
            "internal_only": True,
            "read_only": True,
            "public_api_eligible": False,
            "response_posture": posture,
            "state_index": {
                "need": vector["need"],
                "risk": vector["risk"],
                "plasticity": vector["plasticity"],
                "boundary_need": round(
                    max(
                        self.body.immunity.boundary_pressure,
                        1.0 - self.body.immunity.sovereignty,
                    ),
                    6,
                ),
                "truthfulness_guard": round(
                    max(
                        risk_score,
                        1.0 - float(self.last_event.get("confidence", 0.0) or 0.0),
                    ),
                    6,
                ),
                "relationship_signal_weight": relationship_memory["continuity"]["weight"],
                "repair_pressure": shadow_memory["state_index"]["repair_pressure"],
                "shadow_risk_impulse": shadow_memory["state_index"]["risk_impulse"],
            },
            "allowed_actions": allowed_actions,
            "blocked_actions": blocked_actions,
            "intent_plan": {
                "primary_goal": primary_goal,
                "lanes": lanes,
                "current_user_text_priority": True,
            },
            "risk": {
                "score": round(risk_score, 6),
                "safety_priority": round(max(risk_score, 1.0 - self.body.immunity.sovereignty), 6),
            },
            "constraints": [
                "current_user_text_priority",
                "no_raw_text",
                "relationship_memory_is_advisory",
                "no_relationship_fact_without_user_confirmation",
            ],
        }

    def _relational_time_layer(
        self, *, current: dict[str, Any], previous: dict[str, Any]
    ) -> dict[str, Any]:
        """关系时间层：计算两次事件之间的时间间隔和日期关系。

        生成人类可读的时间标签（刚刚/刚才/隔了一阵/隔天/隔了很久）
        和跨天判断，供 prompt context 使用。
        """
        current_time = self._event_time_payload(current)
        previous_time = self._event_time_payload(previous) if previous else {}
        gap_seconds = self._gap_seconds(current_time, previous_time)
        return {
            "schema_version": SCHEMA_RELATIONAL_TIME_VERSION,
            "kind": "relational_time_layer",
            "internal_only": True,
            "read_only": True,
            "current_time": current_time,
            "time_gap": {
                "seconds": gap_seconds,
                "label": self._gap_label(gap_seconds, bool(previous)),
            },
            "day_relation": self._day_relation(current_time, previous_time),
            "constraints": [
                "internal_prompt_context_only",
                "no_raw_text",
                "does_not_override_current_user_text",
            ],
        }

    def _event_time_payload(self, event: dict[str, Any]) -> dict[str, Any]:
        raw_et = event.get("event_time")
        event_time: dict[str, Any] = dict(raw_et) if isinstance(raw_et, dict) else {}
        local_datetime = str(event_time.get("local_datetime") or event_time.get("local_time") or "")
        timezone = str(event_time.get("timezone") or event_time.get("tz") or "local")
        epoch = float(event_time.get("epoch") or event.get("now") or 0.0)
        return {
            "local_datetime": local_datetime,
            "timezone": timezone,
            "epoch": round(epoch, 6),
        }

    def _gap_seconds(self, current_time: dict[str, Any], previous_time: dict[str, Any]) -> float:
        if not previous_time:
            return 0.0
        current_epoch = float(current_time.get("epoch") or 0.0)
        previous_epoch = float(previous_time.get("epoch") or 0.0)
        if current_epoch and previous_epoch:
            return round(max(0.0, current_epoch - previous_epoch), 6)
        return 0.0

    def _gap_label(self, seconds: float, has_previous: bool) -> str:
        if not has_previous:
            return "first_event"
        if seconds < 900:
            return "刚刚"
        if seconds < 7200:
            return "刚才"
        if seconds < 86400:
            return "隔了一阵"
        if seconds < 259200:
            return "隔天"
        return "隔了很久"

    def _day_relation(self, current_time: dict[str, Any], previous_time: dict[str, Any]) -> str:
        if not previous_time:
            return "first_event"
        current_date = self._local_date(str(current_time.get("local_datetime") or ""))
        previous_date = self._local_date(str(previous_time.get("local_datetime") or ""))
        if not current_date or not previous_date:
            return "unknown"
        return "same_day" if current_date == previous_date else "cross_day"

    def _local_date(self, value: str) -> str:
        if not value:
            return ""
        try:
            return datetime.fromisoformat(value).date().isoformat()
        except ValueError:
            return value[:10] if len(value) >= 10 else ""

    def _vector_summary(self) -> dict[str, float]:
        """从 29 维状态向量中提取 4 个关键摘要指标（单次 tick 内缓存）。

        - vitality: 生命力（节律 + 循环）
        - need: 最大需求强度
        - risk: 最大风险指标（边界压力/耗竭/开放伤口）
        - plasticity: 可塑性
        """
        if self._cached_vector_summary is not None:
            return self._cached_vector_summary
        vector = self.body.state_vector()
        summary = {
            "vitality": round(
                min(1.0, vector["pulse.rhythm"] + vector["bloodflow.circulation"] * 0.2),
                6,
            ),
            "need": round(
                max(
                    vector["needs.need_contact"],
                    vector["needs.need_expression"],
                    vector["needs.need_repair"],
                ),
                6,
            ),
            "risk": round(
                max(
                    vector["immunity.boundary_pressure"],
                    vector["mortality.exhaustion"],
                    vector["wound.open"],
                ),
                6,
            ),
            "plasticity": vector["nerve.plasticity"],
        }
        self._cached_vector_summary = summary
        return summary

    def _trait_view(self) -> dict[str, Any]:
        """Effective Big-Five traits for this session (handles the optional
        ``{"traits": {...}}`` wrapper). Per-relationship and drifts over time, so
        affect-driven timing is her temperament, not a global knob."""
        p = self._personality()
        if not isinstance(p, dict):
            return {}
        inner = p.get("traits", p)
        return inner if isinstance(inner, dict) else {}

    def _update_affect_debt(self, assessment: dict[str, Any] | None) -> None:
        """Accumulate unresolved emotional pressure (allostatic threshold bias).

        Asymmetric leak, paced by personality so the behaviour emerges from her
        traits rather than a hardcoded knob: a bruising read spikes it fast, calm
        leaks it slowly, being soothed clears it. Reads ONLY the raw assessment
        (valence/wound_risk); with no assessment (idle / proactive checks) it merely
        leaks. Never touches ``body.needs`` or ``_guard`` — it only biases the
        reach_out threshold in ``_decide``; the safety gates stay fully in front.
        """
        t = self._trait_view()
        neuro = max(0.0, min(1.0, float(t.get("neuroticism", 0.5))))
        leak = max(0.02, min(0.14, 0.08 - 0.05 * (neuro - 0.5)))  # high neuroticism holds longer
        debt = self._affect_debt * (1.0 - leak)
        if assessment:
            try:
                valence = max(-1.0, min(1.0, float(assessment.get("valence", 0.0))))
                wound = max(0.0, min(1.0, float(assessment.get("wound_risk", 0.0))))
            except (TypeError, ValueError):
                valence, wound = 0.0, 0.0
            raw = max(0.0, -valence) * 0.6 + wound * 0.4  # unresolved negative pressure [0,1]
            if raw > debt:
                alpha_up = max(0.3, min(0.9, 0.6 + 0.3 * (neuro - 0.5)))  # reactive spike
                debt += alpha_up * (raw - debt)
            if valence > 0.5:  # being soothed discharges
                debt *= max(0.0, 1.0 - (valence - 0.5) * 2.0)
        self._affect_debt = max(0.0, min(1.0, debt))

    def _reach_threshold(self, *, proactive: bool) -> float:
        """need_contact threshold for reach_out, lowered by unresolved emotional debt.

        Extraversion (plus a little anxious neuroticism) makes her come back sooner
        after a bruise. At ``affect_debt == 0`` this returns the original literals
        (0.1 proactive / 0.2 reactive) exactly, so behaviour is unchanged absent
        any emotional charge.
        """
        t = self._trait_view()
        extra = max(0.0, min(1.0, float(t.get("extraversion", 0.5))))
        neuro = max(0.0, min(1.0, float(t.get("neuroticism", 0.5))))
        aggr = max(0.04, min(0.24, 0.12 + 0.10 * (extra - 0.5) + 0.06 * (neuro - 0.5)))
        pull = aggr * self._affect_debt
        if proactive:
            return max(0.04, 0.1 - pull)
        return max(0.08, 0.2 - pull)

    def discharge_affect_debt(self) -> None:
        """Spend emotional debt after a successful reach-out, so it cannot keep
        re-firing each time cooldown recovers (the delayed-talkative hole). How much
        lingers is set by agreeableness: an agreeable read is soothed by acting, a
        guarded one stays a little sulky even after reaching out."""
        t = self._trait_view()
        agree = max(0.0, min(1.0, float(t.get("agreeableness", 0.5))))
        keep = max(0.1, min(0.6, 0.3 - 0.2 * (agree - 0.5)))
        self._affect_debt *= keep

    def set_telemetry(self, sink: DistillationSink | None) -> None:
        """Attach (or detach) the distillation corpus sink. Runtime-only — the
        sink is never part of snapshot()/restore()."""
        self._telemetry_sink = sink

    def _capture_telemetry(self, assessment: dict[str, Any]) -> None:
        """Append one numeric training tuple (features + assessor affect) for the
        distillation corpus. Pulls only numeric fields by explicit key — never the
        raw message text (``result['text']``) or assessor free-text flags. Any
        failure is logged at debug and never disrupts the tick."""
        sink = self._telemetry_sink
        if sink is None or not sink.enabled:
            return
        try:
            result = self._last_computation_result
            raw_emotion = result.get("emotion")
            emotion = raw_emotion if isinstance(raw_emotion, dict) else {}
            raw_resonance = result.get("resonance")
            resonance = raw_resonance if isinstance(raw_resonance, dict) else {}
            needs = self.body.needs
            imm = self.body.immunity

            def _f(value: Any) -> float:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return 0.0

            row: dict[str, Any] = {
                "tick": self.turns,
                "f_warmth": _f(emotion.get("warmth")),
                "f_arousal": _f(emotion.get("arousal")),
                "f_valence": _f(emotion.get("valence")),
                "f_tension": _f(emotion.get("tension")),
                "f_curiosity": _f(emotion.get("curiosity")),
                "f_repair_pressure": _f(emotion.get("repair_pressure")),
                "f_expression_drive": _f(emotion.get("expression_drive")),
                "f_boundary_firmness": _f(emotion.get("boundary_firmness")),
                "f_coherence": _f(emotion.get("coherence")),
                "f_void_pressure": _f(emotion.get("void_pressure")),
                "f_active_voids": _f(emotion.get("active_voids")),
                "f_surprise": _f(result.get("surprise")),
                "f_boundary_stability": _f(result.get("boundary_stability")),
                "f_resonance_energy": _f(resonance.get("energy")),
                "f_sync_order": _f(resonance.get("sync_order")),
                "f_phi": _f(resonance.get("phi")),
                "f_plasticity_ratio": _f(resonance.get("plasticity_ratio")),
                "f_need_contact": _f(needs.get("need_contact")),
                "f_need_quiet": _f(needs.get("need_quiet")),
                "f_need_repair": _f(needs.get("need_repair")),
                "f_need_expression": _f(needs.get("need_expression")),
                "f_boundary_pressure": _f(imm.boundary_pressure),
                "f_sovereignty": _f(imm.sovereignty),
                "f_interruption_budget": _f(imm.interruption_budget),
                "f_cooldown": _f(imm.cooldown),
                "f_affect_debt": _f(self._affect_debt),
                "a_valence": _f(assessment.get("valence")),
                "a_arousal": _f(assessment.get("arousal")),
                "a_wound_risk": _f(assessment.get("wound_risk")),
                "a_confidence": _f(assessment.get("confidence")),
                "decision_action": str(self.last_decision.get("action", "")),
            }
            sink.record_tick(session_key=self.session_key, row=row)
        except Exception:
            logger.debug("telemetry capture skipped", exc_info=True)

    def _decide(self) -> dict[str, Any]:
        """基于身体需求的行动决策。

        优先级从高到低：
        repair > withdraw > reach_out > express > explore > wait
        """
        needs = self.body.needs
        proactive = "proactive" in self.last_event.get("flags", [])
        action = "wait"
        reason = "life rhythm is holding"
        reason_code = "life_rhythm"
        if needs["need_repair"] > 0.2:
            action = "repair"
            reason = "wound asks for repair"
            reason_code = "repair_need"
        elif self.body.immunity.boundary_pressure > 0.75 or needs["need_quiet"] > 0.6:
            action = "withdraw"
            reason = "boundary asks for distance"
            reason_code = "boundary_pressure"
        elif (
            (proactive and needs["need_contact"] >= self._reach_threshold(proactive=True))
            or needs["need_contact"] > self._reach_threshold(proactive=False)
        ) and self.body.muscle.fatigue < 0.8:
            action = "reach_out"
            reason = "contact need has accumulated"
            reason_code = "contact_need"
        elif needs["need_expression"] > 0.2:
            action = "express"
            reason = "expression need is alive"
            reason_code = "expression_need"
        elif self.body.nerve.plasticity > 0.3:
            action = "explore"
            reason = "plastic trace seeks shape"
            reason_code = "plastic_trace"
        return {
            "action": action,
            "reason": reason,
            "reason_code": reason_code,
            "confidence": round(min(1.0, 0.35 + self.body.nerve.plasticity), 6),
        }

    def _risk_score(self) -> float:
        return round(
            max(
                self.body.immunity.boundary_pressure,
                self.body.mortality.exhaustion,
                self.body.wound.open,
                1.0 - self.body.immunity.sovereignty,
            ),
            6,
        )

    def _guard(self, decision: dict[str, Any]) -> dict[str, Any]:
        """安全守卫层：检查是否允许执行 decision 中的行动。

        阻止条件（任一满足即 allowed=False）：
        - 用户暂停 (paused)
        - 主权过低 (sovereignty < 0.5)
        - 主动发言未获 opt-in
        - 冷却中
        - 中断预算耗尽
        - 风险过高 (risk > 0.85)
        - 边界免疫过高 (boundary_pressure > 0.85)
        - 耗竭过高 (exhaustion > 0.8)
        """
        flags: list[str] = []
        allowed = True
        reason = decision["reason"]
        risk_score = self._risk_score()
        outward = decision["action"] in {"reach_out", "express", "repair", "explore"}
        proactive = "proactive" in self.last_event.get("flags", [])
        if self.body.immunity.paused:
            allowed = False
            reason = "user pause is active"
            flags.append("user_pause")
        if self.body.immunity.sovereignty < 0.5:
            allowed = False
            reason = "user sovereignty is too low for outward action"
            flags.append("sovereignty_low")
        if outward and proactive and not self._has_sovereignty_opt_in():
            allowed = False
            reason = "proactive speech requires recent user opt-in"
            flags.append("sovereignty_opt_in_required")
        if outward and proactive and self.body.immunity.cooldown > 0.0:
            allowed = False
            reason = "proactive rhythm is cooling down"
            flags.append("proactive_cooldown")
        if outward and self.body.immunity.interruption_budget <= 0.1:
            allowed = False
            reason = "interruption budget exhausted"
            flags.append("budget_exhausted")
        if outward and risk_score > 0.85:
            allowed = False
            reason = "body risk blocks outward action"
            flags.append("risk_high")
        if outward and self.body.immunity.boundary_pressure > 0.85:
            allowed = False
            reason = "boundary immunity blocks outward action"
            flags.append("boundary_immunity")
        if self.body.mortality.exhaustion > 0.8:
            allowed = False
            reason = "body exhaustion requires recovery"
            flags.append("exhaustion")
        return {
            "allowed": allowed,
            "reason": reason,
            "flags": flags,
            "risk_score": risk_score,
        }

    def _has_sovereignty_opt_in(self) -> bool:
        """Check whether the user has actively opted in to proactive contact.

        Requirements for opt-in:
        1. At least 2 recent texts (showing ongoing engagement, not just one message)
        2. The most recent event must be within the last 5 minutes (not stale)
        3. The user's last message must not contain rejection signals
        """
        # Require at least 2 recent texts (ongoing engagement)
        if len(self.body._recent_texts) < 2:
            return False

        # Check recency: last USER-initiated event must be within 5 minutes.
        # Note: self.last_event is already updated to the current tick's event,
        # so we use previous_event to check the last real user interaction time.
        # Use logical timestamps (event "now") for consistency with tests/simulations.
        prev_now = float(self.previous_event.get("now") or 0.0)
        prev_text = str(self.previous_event.get("text") or "")
        if prev_now <= 0.0 or not prev_text:
            return False

        current_now = float(self.last_event.get("now") or 0.0)
        elapsed = current_now - prev_now
        if elapsed > 300.0:
            return False

        # Check rejection signals in the most recent text
        rejection_signals = ("别烦我", "不想聊", "安静", "别说了", "闭嘴")
        if self.body._recent_texts:
            last_text = self.body._recent_texts[-1]
            for signal in rejection_signals:
                if signal in last_text:
                    return False

        return True

    def _next_check_seconds(self, decision: dict[str, Any], guard: dict[str, Any]) -> int:
        if "proactive_cooldown" in guard["flags"]:
            return 120
        if not guard["allowed"]:
            return 300
        if decision["action"] in {"reach_out", "express", "repair"}:
            return 900
        return 180

    def _event(self, event: AlphaKernelEvent | dict[str, Any] | None) -> AlphaKernelEvent:
        if isinstance(event, AlphaKernelEvent):
            return event
        payload = event or {}
        confidence = float(payload.get("confidence") or 0.0)
        if not math.isfinite(confidence):
            confidence = 0.0
        now = float(payload.get("now") or 0.0)
        if not math.isfinite(now):
            now = 0.0
        return AlphaKernelEvent(
            text=str(payload.get("text") or ""),
            values=dict(payload.get("values") or {}),
            confidence=confidence,
            flags=list(payload.get("flags") or []),
            now=now,
            event_time=_as_dict(payload.get("event_time")),
        )
