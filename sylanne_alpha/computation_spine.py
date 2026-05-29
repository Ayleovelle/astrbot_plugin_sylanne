"""Sylanne-Embodiment 计算核心层：统一计算脊柱（Computation Spine）。

本模块是 7 层计算管线的总调度器，负责将所有子系统串联为一条完整的信息处理流水线：
  L1 Perception(HDC) → L2 Gate(PredictiveCoding) → L3 VoidScarEngine →
  L4 RelationalSheaf → L5 HGT → L6 Boundary(Autopoiesis) → L7 Express(PhaseTransition)

在整个架构中的位置：最顶层编排模块，对外暴露 process() / feedback() / express() 三个主入口。
所有人格参数通过 apply_personality() 向下分发到各子系统。
"""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import TYPE_CHECKING, Any

from .autopoiesis import AutopoieticBoundary
from .bounded_dict import BoundedDict
from .hdc import HDCEncoder
from .hgt import HeterogeneousGraphTransformer
from .personality import (
    EMBODIMENT_TRAITS,
    DriftAttribution,
    DriftSignalExtractor,
    OscillationDetector,
    TraitMemory,
    compute_embodiment_drift,
    normalize_personality,
)
from .phase_transition import PhaseTransitionExpression
from .predictive_coding import PredictiveCodingGate
from .relational_sheaf import ScarSheaf
from .void_scar_engine import VoidScarEngine

if TYPE_CHECKING:
    from .social_field import SocialSignals

logger = logging.getLogger("astrbot_plugin_sylanne")

_TIMING_WINDOW = 50
# 单层执行超时告警阈值（纳秒），200ms
_LAYER_TIMEOUT_NS = 200_000_000


class CircuitBreaker:
    """计算层异常隔离与自愈断路器。

    当某层连续失败达到阈值时进入 open 状态，在冷却期内直接返回上次成功结果（fallback）。
    冷却期结束后进入 half-open 状态，允许一次尝试：成功则关闭，失败则重新打开。
    """

    __slots__ = ("_failures", "_threshold", "_cooldown", "_open_since", "_last_good_result")

    def __init__(self, threshold: int = 3, cooldown: float = 60.0):
        self._failures: int = 0
        self._threshold: int = threshold
        self._cooldown: float = cooldown
        self._open_since: float = 0.0
        self._last_good_result: Any = None

    def is_open(self) -> bool:
        if self._failures >= self._threshold:
            if time.time() - self._open_since < self._cooldown:
                return True
            # half-open: cooldown expired, allow one retry
            # 设为 threshold-1 使单次失败即可重新打开
            self._failures = self._threshold - 1
        return False

    def record_success(self, result: Any) -> None:
        """记录成功执行，重置失败计数并缓存结果。"""
        self._failures = 0
        self._last_good_result = result

    def record_failure(self) -> None:
        """记录失败，达到阈值时打开断路器。"""
        self._failures += 1
        if self._failures >= self._threshold:
            self._open_since = time.time()

    def fallback(self) -> Any:
        """返回上次成功的缓存结果。"""
        return self._last_good_result


# ---------------------------------------------------------------------------
# Item 75: 计算层插件注册表（简化版）
# ---------------------------------------------------------------------------


class LayerRegistry:
    """计算层注册表：支持第三方注册自定义层。"""

    _custom_layers: dict[str, callable] = {}

    @classmethod
    def register(cls, name: str, layer_fn: callable):
        """注册自定义计算层。layer_fn 签名: (input_data, config) -> output_data"""
        cls._custom_layers[name] = layer_fn

    @classmethod
    def get_custom_layers(cls) -> dict[str, callable]:
        return dict(cls._custom_layers)

    @classmethod
    def has_custom(cls, name: str) -> bool:
        return name in cls._custom_layers


class ComputationSpine:
    """Sylanne-Embodiment 的统一计算管线。

    整合所有计算模块为 7 层流水线，对外暴露三个主入口：
      - process(text): 处理一条消息通过全栈
      - feedback(outcome): 注入表达结果反馈
      - express(): 触发表达输出

    内部状态管理：
      - 人格参数通过 apply_personality() 向下分发
      - 每关系人格覆盖（relationship_deltas）
      - Embodiment 人格漂移系统（信号提取 → 特质记忆 → 振荡检测）
      - 全状态可序列化（to_dict/from_dict）
    """

    __slots__ = (
        "encoder",
        "gate",
        "engine",
        "sheaf",
        "boundary",
        "expression",
        "hgt",
        "_tick_count",
        "_last_route",
        "_last_expression_time",
        "_timings",
        "_last_process_time",
        "_personality",
        "_last_assessment",
        "_last_hdc_vec",
        "_social_field_params",
        "_route_counts",
        "_feedback_counts",
        "_signal_extractor",
        "_embodiment_traits",
        "_oscillation_detector",
        "_drift_tick",
        "_last_embodiment_apply",
        "_last_drift_time",
        "_drift_min_interval",
        "_relationship_deltas",
        "_last_effective_session",
        "_last_effective_params",
        "_personality_dirty",
        "_diagnostics_enabled",
        "_circuit_breakers",
        "_layer_enabled",
        "_result_cache",
        "_drift_attribution",
        "_parallel_eligible",
    )

    def __init__(self, plugin: Any = None):
        hdc_dim = getattr(plugin, '_cfg_int', lambda k, d: d)('sylanne_alpha_hdc_dimension', 2048)
        self.encoder = HDCEncoder(dim=hdc_dim)
        self.gate = PredictiveCodingGate(dim=hdc_dim)
        self.engine = VoidScarEngine(n_dims=8, similarity_fn=self._hdc_similarity)
        self.sheaf = ScarSheaf(n0=8)
        self.boundary = AutopoieticBoundary(identity_dim=32)
        self.expression = PhaseTransitionExpression()
        self.hgt = HeterogeneousGraphTransformer(d_model=16, n_heads=4, d_output=4)
        self._tick_count = 0
        self._last_route = "fast"
        self._last_expression_time = 0.0
        self._last_process_time = 0.0
        self._personality: dict[str, float] = {
            "extraversion": 0.5,
            "neuroticism": 0.5,
            "conscientiousness": 0.5,
            "openness": 0.5,
            "agreeableness": 0.5,
        }
        self._last_assessment: dict[str, Any] | None = None
        self._last_hdc_vec: bytearray | None = None
        self._social_field_params: dict[str, float] = {}
        self._route_counts: dict[str, int] = {
            "fast": 0,
            "normal": 0,
            "full": 0,
            "skip": 0,
        }
        self._feedback_counts: dict[str, int] = {
            "accepted": 0,
            "ignored": 0,
            "rejected": 0,
        }
        self._timings: dict[str, deque] = {
            "perception": deque(maxlen=_TIMING_WINDOW),
            "gate": deque(maxlen=_TIMING_WINDOW),
            "void_scar": deque(maxlen=_TIMING_WINDOW),
            "sheaf": deque(maxlen=_TIMING_WINDOW),
            "hgt": deque(maxlen=_TIMING_WINDOW),
            "boundary": deque(maxlen=_TIMING_WINDOW),
            "expression": deque(maxlen=_TIMING_WINDOW),
        }
        # Embodiment personality drift system
        self._signal_extractor = DriftSignalExtractor()
        self._embodiment_traits: dict[str, TraitMemory] = {
            name: TraitMemory(0.5) for name in EMBODIMENT_TRAITS
        }
        self._oscillation_detector = OscillationDetector()
        self._drift_attribution = DriftAttribution(maxlen=100)
        self._drift_tick = 0
        self._last_embodiment_apply: dict[str, float] = {
            name: 0.5 for name in EMBODIMENT_TRAITS
        }
        # Drift rate limiting
        self._last_drift_time: float = 0.0
        self._drift_min_interval: float = 30.0  # seconds

        # Per-relationship personality deltas (session_key -> {trait: delta})
        self._relationship_deltas: BoundedDict = BoundedDict(maxsize=200)

        # P6: Cache per-relationship personality to avoid double apply_personality
        self._last_effective_session: str = ""
        self._last_effective_params: dict[str, float] = {}
        self._personality_dirty: bool = False

        # Diagnostics toggle — skip expensive _l1_hdc_payload when WebUI isn't polling
        self._diagnostics_enabled: bool = True

        # Circuit breakers for each computation layer (异常隔离与自愈)
        self._circuit_breakers: dict[str, CircuitBreaker] = {
            "perception": CircuitBreaker(threshold=3, cooldown=60.0),
            "gate": CircuitBreaker(threshold=3, cooldown=60.0),
            "void_scar": CircuitBreaker(threshold=3, cooldown=60.0),
            "sheaf": CircuitBreaker(threshold=3, cooldown=60.0),
            "hgt": CircuitBreaker(threshold=3, cooldown=60.0),
            "boundary": CircuitBreaker(threshold=3, cooldown=60.0),
            "expression": CircuitBreaker(threshold=3, cooldown=60.0),
        }

        # 计算栈层级开关（Item 57）：可动态禁用某层以降低计算开销或调试
        self._layer_enabled: dict[str, bool] = {
            "perception": True,
            "gate": True,
            "void_scar": True,
            "sheaf": True,
            "hgt": True,
            "boundary": True,
            "expression": True,
        }

        # 计算结果缓存（Item 20）：相同文本短时间内命中缓存，避免重复计算
        self._result_cache: BoundedDict = BoundedDict(maxsize=50, ttl=30)

        # Item 11: 流水线并行化标记。
        # L1-L2 与 L4 理论上可并行，但 L4 依赖 L3 输出，且 process() 为同步方法，
        # 无法使用 asyncio.gather。此标记供未来 async 重构时识别可并行段。
        # 当前语义：在 normal/full path 中 L4(sheaf) 和 L5(hgt) 可与 L6(boundary)
        # 并行执行（它们之间无数据依赖），但需要 async 化后才能实现。
        self._parallel_eligible: bool = False

    def set_layer_enabled(self, layer: str, enabled: bool) -> None:
        """启用或禁用指定的计算层。

        禁用的层在 process() 中将被跳过，使用默认值代替。
        可用于调试、性能优化或特定场景下的简化计算。

        Args:
            layer: 层名称，可选 "perception"/"gate"/"void_scar"/"sheaf"/"hgt"/"boundary"/"expression"。
            enabled: True 启用，False 禁用。
        """
        if layer in self._layer_enabled:
            self._layer_enabled[layer] = enabled

    def set_diagnostics(self, enabled: bool) -> None:
        """启用/禁用诊断数据生成（_l1_hdc_payload 等昂贵调用）。

        当 WebUI 未主动轮询 /api/computation_logs 时可关闭以节省 CPU。
        """
        self._diagnostics_enabled = enabled

    def replace_encoder(self, encoder: HDCEncoder) -> None:
        """替换 HDC 编码器（用于测试或自定义维度）。"""
        self.encoder = encoder

    def apply_personality(self, personality: dict[str, float]) -> None:
        """从人格向量派生所有子系统的计算参数。

        接受 Big Five 传统名称和 Embodiment Five 新名称。
        将语义人格维度映射为内部阈值：
          - extraversion → 表达阈值（外向者更低）、伤痕创伤阈值（外向者更高）
          - neuroticism → 虚空检测阈值（神经质者更低）、愈合速率（神经质者更慢）
          - conscientiousness → 表达阈值、门控路由阈值
          - openness → 虚空创生冷却、边界旋转角度
          - agreeableness → 边界渗透性、关系层析耦合

        这是"人格驱动全参数"设计核心的实现入口。
        """
        personality = normalize_personality(personality)
        self._personality = dict(personality)
        extraversion = float(personality.get("extraversion", 0.5))
        neuroticism = float(personality.get("neuroticism", 0.5))

        # Expression threshold: extraverts have lower threshold (speak more easily)
        # Range: 0.3 (very extraverted) to 0.9 (very introverted)
        self.expression.threshold = 0.9 - extraversion * 0.6

        # Scar wound threshold: extraverts wound less easily (higher threshold)
        # Range: 0.3 (very introverted, wounds easily) to 0.9 (very extraverted)
        self.engine.scar_state.wound_threshold = 0.3 + extraversion * 0.6

        # Void detection threshold: neurotic = lower threshold (detects absence easily)
        # Range: 0.1 (very neurotic) to 0.6 (very stable)
        self.engine.void_space._detection_threshold = 0.6 - neuroticism * 0.5

        # Void creation cooldown: derived from openness
        self.engine.void_space.set_cooldown(float(personality.get("openness", 0.5)))

        # Gate sensitivity: neurotic = lower thresholds (everything feels surprising)
        self.gate.precision = 0.3 + neuroticism * 0.5

        # Healing rates derived from personality:
        # High neuroticism → slower healing (T values larger)
        # T_raw = 10 + neuroticism * 20 → range [10, 30]
        # T_closing = 40 + neuroticism * 60 → range [40, 100]
        # T_scarred = 150 + neuroticism * 100 → range [150, 250]
        # (resilience = 1 - neuroticism; high resilience → fast healing)
        t_raw = int(10 + neuroticism * 20)
        t_closing = int(40 + neuroticism * 60)
        t_scarred = int(150 + neuroticism * 100)
        self.engine.scar_state.set_healing_rates(
            t_raw, t_closing, t_scarred, neuroticism
        )

        # HGT: derive all transformer parameters from personality
        self.hgt.derive_params(personality)

        # Relational Sheaf: derive presentation matrices from personality
        self.sheaf.derive_params(personality)

        # Social field parameters (for L7 group modulation)
        openness = float(personality.get("openness", 0.5))
        agreeableness = float(personality.get("agreeableness", 0.5))
        conscientiousness = float(personality.get("conscientiousness", 0.5))
        patience = float(personality.get("patience", 0.52))
        sovereignty = float(personality.get("sovereignty_guard", 0.68))

        # Session scar cap: high sovereignty = more protected (lower cap)
        self.engine.scar_state.set_session_cap(sovereignty)

        # Personality detection floor for void space (used by Phi coupling)
        perception_acuity = neuroticism  # legacy mapping
        personality_base = 0.6 - perception_acuity * 0.5
        self.engine._personality_detection_floor = max(0.1, personality_base - 0.15)

        # Boundary: set initial integrity from agreeableness (agreeable = more permeable)
        self.boundary.boundary_integrity = 1.0 - agreeableness * 0.08

        self._social_field_params = {
            "group_threshold_boost": 0.7 - extraversion * 0.6,
            "topic_weight": 0.2 + openness * 0.5,
            "sheaf_coupling": 0.1 + agreeableness * 0.4,
            "void_coupling": 0.1 + neuroticism * 0.4,
            "continuation_tau": 30.0 + patience * 180.0,
            "refractory_boost": sovereignty * 0.05,
            "noise_sensitivity": 0.3 + extraversion * 0.4 - neuroticism * 0.2,
        }
        self.expression.set_social_params(self._social_field_params)

        # --- Void-Scar coupling parameters ---
        coupling_rate = 0.15 + neuroticism * 0.35
        pressure_threshold = 15.0 - neuroticism * 8.0 + patience * 3.0
        void_drive_weight = 0.3 + neuroticism * 0.4
        social_drive_weight = 0.2 + extraversion * 0.3
        accepted_decay = 0.6 + agreeableness * 0.2
        ignored_deepening = 0.03 + neuroticism * 0.05
        self.engine.set_personality_params(
            coupling_rate=coupling_rate,
            pressure_threshold=pressure_threshold,
            void_drive_weight=void_drive_weight,
            social_drive_weight=social_drive_weight,
            accepted_decay=accepted_decay,
            ignored_deepening=ignored_deepening,
        )

        # --- Void space thresholds ---
        self.engine.void_space.set_personality_params(
            contract_threshold=0.5 + openness * 0.2,
            split_threshold=0.2 + (1 - neuroticism) * 0.2,
            merge_threshold=0.6 + conscientiousness * 0.2,
            pressure_cap=60.0 + sovereignty * 60.0,
        )

        # --- Phase transition dynamics ---
        self.expression.set_personality_params(
            decay_rate=0.01 + extraversion * 0.03,
            silence_urgency_divisor=5.0 + patience * 15.0,
            refractory=0.01 + (1 - extraversion) * 0.04,
            silence_drop_rate=0.005 + neuroticism * 0.008,
            min_threshold_floor=0.15 + sovereignty * 0.2,
        )

        # --- Autopoiesis boundary ---
        self.boundary.set_personality_params(
            repair_rate=0.03 + conscientiousness * 0.04 - neuroticism * 0.02,
            phase_threshold=0.5 + sovereignty * 0.3 - openness * 0.15,
            rotation_angle=0.05 + openness * 0.1,
        )

        # --- Predictive coding gate routes ---
        self.gate.set_route_thresholds(
            fast_threshold=0.10 + conscientiousness * 0.10,
            full_threshold=0.35 + (1 - openness) * 0.15 + (1 - neuroticism) * 0.10,
        )

        # NOTE: RhythmLearner and SocialFieldCollector are NOT owned by
        # ComputationSpine. Their set_personality_params() should be called
        # from the host level (main.py) when personality is available.

    def effective_personality(self, session_key: str = "") -> dict[str, float]:
        """获取应用了每关系覆盖后的有效人格。

        每个关系可以在每个维度上偏移人格最多 +/-0.1。
        如果 session_key 为空或未知，返回基础人格。
        """
        base = dict(self._personality)
        if not session_key or session_key not in self._relationship_deltas:
            return base
        delta = self._relationship_deltas[session_key]
        for trait, d in delta.items():
            if trait in base:
                base[trait] = max(0.05, min(0.95, base[trait] + d))
        return base

    def apply_assessment(self, assessment: dict[str, Any]) -> None:
        """应用 LLM 评估结果来调制虚空-伤痕状态。

        当 LLM 评估器在超时窗口内返回时调用，提供精确的语义判断来修正 HDC 粗路径。

        调制逻辑：
          - 高 wound_risk → 向伤痕状态注入创伤事件
          - 负 valence → 加深活跃虚空的压力
          - 正 valence → 减少虚空压力（治愈效果）
          - 特定 intent（如"撒娇"/"生气"）→ 直接调制基向量

        Args:
            assessment: 包含 valence, arousal, intent, wound_risk 等键的字典
        """
        self._last_assessment = assessment
        wound_risk = float(assessment.get("wound_risk") or 0.0)
        valence = float(assessment.get("valence") or 0.0)
        arousal = float(assessment.get("arousal") or 0.0)
        intent = str(assessment.get("intent", ""))

        # High wound risk → inject a wound event into scar state
        if wound_risk > 0.7:
            wound_vec = [0.0] * self.engine.scar_state.n_dims
            # Wound on dimension 3 (tension-related) and 5 (repair pressure)
            wound_vec[3] = wound_risk * 0.8
            wound_vec[5] = wound_risk * 0.5
            self.engine.scar_state.step(wound_vec, 0.0, heal=False)

        # Negative valence → deepen active voids (increase pressure)
        if valence < -0.5:
            for void in self.engine.void_space.voids[:2]:
                void.pressure = min(1.0, void.pressure + abs(valence) * 0.2)

        # Positive valence → reduce void pressure (healing effect)
        if valence > 0.5:
            for void in self.engine.void_space.voids[:3]:
                void.pressure *= max(0.5, 1.0 - valence * 0.3)

        # Intent-specific adjustments via scar base vector modulation
        if intent == "撒娇":
            # Coquettish intent → soften base state (reduce tension dims)
            if len(self.engine.scar_state.base) > 3:
                self.engine.scar_state.base[3] *= 0.85  # tension dim
            if len(self.engine.scar_state.base) > 0:
                self.engine.scar_state.base[0] = min(
                    1.0, self.engine.scar_state.base[0] + 0.1
                )  # warmth dim
        elif intent == "生气":
            # Anger → raise tension in base state
            if len(self.engine.scar_state.base) > 3:
                self.engine.scar_state.base[3] = min(
                    1.0, self.engine.scar_state.base[3] + 0.2
                )

        # Arousal modulates expression drive accumulation rate
        if arousal > 0.7:
            self.expression.accumulate(arousal * 0.2, dt=0.5)

    def apply_social_signals(self, signals: SocialSignals | None) -> None:
        """应用社交场信号到 L7 表达层和 L3 虚空-伤痕引擎。"""
        self.expression.apply_social_signals(signals)
        if signals and signals.is_group:
            self.engine.social_void.group_activity = signals.group_noise_level
            self.engine.social_void.topic_boundary = 1.0 - signals.topic_relevance

    def process(
        self,
        text: str,
        timestamp: float = 0.0,
        assessment: dict[str, Any] | None = None,
        *,
        session_key: str = "",
    ) -> dict[str, Any]:
        """主入口：处理一条消息通过完整的 7 层计算栈。

        流程：
          L1: HDC 编码文本 → 高维二进制超向量
          L2: 预测编码门控 → 计算惊讶度，决定路由（fast/normal/full）
          L3: 虚空-伤痕引擎 → 情感状态演化
          L3.5: LLM 评估调制（可选）→ 精确语义判断修正粗路径
          L4: 关系层析 → 跨关系传播
          L5: HGT 决策融合 → 4 维决策向量
          L6: 自创生边界 → 扰动/相变/自修复
          L7: 相变表达 → 是否应该说话

        Args:
            text: 输入消息文本
            timestamp: 事件时间戳（epoch 秒）
            assessment: 可选的 LLM 评估结果，用于精确语义调制
            session_key: 可选的关系标识符，用于每关系人格覆盖
        """
        # 结果缓存层（Item 20）：相同文本+相同评估短时间内直接返回缓存
        # assessment 不同意味着 LLM 给出了新评估，必须重新计算
        assess_sig = hash(tuple(sorted(assessment.items()))) if assessment else 0
        cache_key = (text, session_key or "", assess_sig)
        cached = self._result_cache.get(cache_key)
        if cached is not None:
            return cached

        # Apply per-relationship personality overlay if session changed or dirty
        if session_key != self._last_effective_session or self._personality_dirty:
            effective = self.effective_personality(session_key)
            if effective != self._last_effective_params:
                self.apply_personality(effective)
                self._last_effective_params = dict(effective)
            self._last_effective_session = session_key
            self._personality_dirty = False
        # Empty string handling: skip computation, self-repair only
        if not text or not text.strip():
            self.boundary.self_repair()
            self.expression.silence_lowers_threshold(dt=1.0)
            result = self._build_result(
                "", timestamp, 0.0, "skip", self.engine.observe(), [], [], False
            )
            result["hgt_decision"] = [0.0, 0.0, 0.0, 0.0]
            result["assessment_source"] = "none"
            return result

        self._tick_count += 1

        # Compute real time delta (in minutes, clamped)
        if self._last_process_time > 0:
            dt = max(0.1, min(10.0, (timestamp - self._last_process_time) / 60.0))
        else:
            dt = 1.0
        self._last_process_time = timestamp

        # Layer 1: Perception -- HDC encode
        t0 = time.perf_counter_ns()
        if not self._layer_enabled.get("perception", True):
            h = self._last_hdc_vec or bytearray(self.encoder.dim // 8)
            logger.debug("Layer perception DISABLED — using default")
        else:
            cb = self._circuit_breakers["perception"]
            if cb.is_open():
                h = cb.fallback() or bytearray(self.encoder.dim // 8)
                logger.warning("Layer perception circuit OPEN — using fallback")
            else:
                try:
                    h = self.encoder.encode_text(text)
                    cb.record_success(h)
                except Exception as exc:
                    cb.record_failure()
                    h = cb.fallback() or bytearray(self.encoder.dim // 8)
                    logger.error("Layer perception failed: %s — using fallback", exc)
        self._last_hdc_vec = h
        _elapsed = time.perf_counter_ns() - t0
        self._timings["perception"].append(_elapsed)
        if _elapsed > _LAYER_TIMEOUT_NS:
            logger.warning("Layer perception took %.1fms (>200ms)", _elapsed / 1e6)

        # Layer 2: Predictive Coding Gate -- compute surprise, decide route
        t0 = time.perf_counter_ns()
        if not self._layer_enabled.get("gate", True):
            surprise = 0.0
            route = "fast"
            l1_payload = {"ones_ratio": 0.0, "total_bits": 0, "sample_bits": [], "prediction_similarity": 0.0, "flip_ratio": 0.0}
            logger.debug("Layer gate DISABLED — using defaults")
        else:
            cb = self._circuit_breakers["gate"]
            if cb.is_open():
                _gate_fallback = cb.fallback() or {"surprise": 0.0, "route": "fast"}
                surprise = _gate_fallback["surprise"]
                route = _gate_fallback["route"]
                l1_payload = {"ones_ratio": 0.0, "total_bits": 0, "sample_bits": [], "prediction_similarity": 0.0, "flip_ratio": 0.0}
                logger.warning("Layer gate circuit OPEN — using fallback")
            else:
                try:
                    surprise = self.gate.surprise(h)
                    if self._diagnostics_enabled:
                        l1_payload = self._l1_hdc_payload(text, h, surprise)
                    else:
                        l1_payload = {
                            "ones_ratio": 0.0,
                            "total_bits": 0,
                            "sample_bits": [],
                            "prediction_similarity": 0.0,
                            "flip_ratio": 0.0,
                        }
                    route = self.gate.route(surprise)
                    self.gate.update(h, surprise)
                    cb.record_success({"surprise": surprise, "route": route})
                except Exception as exc:
                    cb.record_failure()
                    _gate_fallback = cb.fallback() or {"surprise": 0.0, "route": "fast"}
                    surprise = _gate_fallback["surprise"]
                    route = _gate_fallback["route"]
                    l1_payload = {"ones_ratio": 0.0, "total_bits": 0, "sample_bits": [], "prediction_similarity": 0.0, "flip_ratio": 0.0}
                    logger.error("Layer gate failed: %s — using fallback", exc)
        self._last_route = route
        if route in self._route_counts:
            self._route_counts[route] += 1
        _elapsed = time.perf_counter_ns() - t0
        self._timings["gate"].append(_elapsed)
        if _elapsed > _LAYER_TIMEOUT_NS:
            logger.warning("Layer gate took %.1fms (>200ms)", _elapsed / 1e6)

        # Layer 3+4: Void-Scar Engine (replaces SSM + TopologicalMemory)
        t0 = time.perf_counter_ns()
        if not self._layer_enabled.get("void_scar", True):
            ssm_input = [0.0] * 8
            emotion = self.engine.observe()
            recalled = []
            holes = []
            logger.debug("Layer void_scar DISABLED — using defaults")
        else:
            cb = self._circuit_breakers["void_scar"]
            if cb.is_open():
                _vs_fallback = cb.fallback() or {}
                ssm_input = [0.0] * 8
                emotion = _vs_fallback.get("emotion", self.engine.observe())
                recalled = _vs_fallback.get("recalled", [])
                holes = _vs_fallback.get("holes", [])
                logger.warning("Layer void_scar circuit OPEN — using fallback")
            else:
                try:
                    ssm_input = self._hdc_to_ssm_input(h, surprise)
                    self.engine.process(
                        event_vec=bytes(h),
                        ssm_input=ssm_input,
                        surprise=surprise,
                        timestamp=timestamp,
                    )
                    emotion = self.engine.observe()
                    recalled = [
                        {"boundary_size": len(v.boundary), "pressure": v.pressure, "depth": v.depth}
                        for v in self.engine.void_space.voids[:3]
                    ]
                    holes = [
                        {"pressure": v.pressure, "depth": v.depth, "age": v.age}
                        for v in self.engine.void_space.voids
                    ]
                    cb.record_success({"emotion": emotion, "recalled": recalled, "holes": holes})
                except Exception as exc:
                    cb.record_failure()
                    _vs_fallback = cb.fallback() or {}
                    ssm_input = [0.0] * 8
                    emotion = _vs_fallback.get("emotion", self.engine.observe())
                    recalled = _vs_fallback.get("recalled", [])
                    holes = _vs_fallback.get("holes", [])
                    logger.error("Layer void_scar failed: %s — using fallback", exc)
        _elapsed = time.perf_counter_ns() - t0
        self._timings["void_scar"].append(_elapsed)
        if _elapsed > _LAYER_TIMEOUT_NS:
            logger.warning("Layer void_scar took %.1fms (>200ms)", _elapsed / 1e6)

        # Layer 3.5: LLM Assessment modulation (if available this tick)
        assessment_source = "hdc_only"
        if assessment:
            self.apply_assessment(assessment)
            assessment_source = "llm_assessed"
            # Re-observe after assessment modulation
            emotion = self.engine.observe()
        l3_payload = self._l3_void_scar_payload(emotion)

        # Layer 4: Relational Sheaf — cross-relational propagation
        t0 = time.perf_counter_ns()
        if not self._layer_enabled.get("sheaf", True):
            sheaf_result = {}
            logger.debug("Layer sheaf DISABLED — using defaults")
        else:
            cb = self._circuit_breakers["sheaf"]
            if cb.is_open():
                sheaf_result = cb.fallback() or {}
                logger.warning("Layer sheaf circuit OPEN — using fallback")
            else:
                try:
                    sheaf_result = self.sheaf.tick(0, ssm_input, timestamp=timestamp)
                    cb.record_success(sheaf_result)
                except Exception as exc:
                    cb.record_failure()
                    sheaf_result = cb.fallback() or {}
                    logger.error("Layer sheaf failed: %s — using fallback", exc)
        _elapsed = time.perf_counter_ns() - t0
        self._timings["sheaf"].append(_elapsed)
        if _elapsed > _LAYER_TIMEOUT_NS:
            logger.warning("Layer sheaf took %.1fms (>200ms)", _elapsed / 1e6)
        l4_payload = self._l4_sheaf_payload(sheaf_result)

        # Layer 5: Heterogeneous Graph Transformer — decision fusion
        t0 = time.perf_counter_ns()
        if not self._layer_enabled.get("hgt", True):
            hgt_decision = [0.0, 0.0, 0.0, 0.0]
            logger.debug("Layer hgt DISABLED — using defaults")
        else:
            cb = self._circuit_breakers["hgt"]
            if cb.is_open():
                hgt_decision = cb.fallback() or [0.0, 0.0, 0.0, 0.0]
                logger.warning("Layer hgt circuit OPEN — using fallback")
            else:
                try:
                    hdc_features = ssm_input  # 复用 L3 已计算的 8 维压缩（避免重复调用 _hdc_to_ssm_input）
                    hgt_tokens = self.hgt.build_tokens_from_spine(
                        scar_state=self.engine.scar_state,
                        void_space=self.engine.void_space,
                        boundary=self.boundary,
                        personality=self._personality,
                        surprise=surprise,
                        expression=self.expression,
                        hdc_features=hdc_features,
                    )
                    hgt_decision = self.hgt.forward(hgt_tokens, self._personality)
                    cb.record_success(hgt_decision)
                except Exception as exc:
                    cb.record_failure()
                    hgt_decision = cb.fallback() or [0.0, 0.0, 0.0, 0.0]
                    logger.error("Layer hgt failed: %s — using fallback", exc)
        _elapsed = time.perf_counter_ns() - t0
        self._timings["hgt"].append(_elapsed)
        if _elapsed > _LAYER_TIMEOUT_NS:
            logger.warning("Layer hgt took %.1fms (>200ms)", _elapsed / 1e6)

        # Fast path: skip heavy computation
        if route == "fast":
            t0 = time.perf_counter_ns()
            if not self._layer_enabled.get("expression", True):
                should_express_fast = False
            else:
                drive = self.engine.expression_drive()
                # Apply HGT d_0 (expression drive correction)
                drive = max(0.0, min(1.0, drive + hgt_decision[0] * 0.3))
                self.expression.accumulate(drive, dt=1.0)
            _elapsed = time.perf_counter_ns() - t0
            self._timings["expression"].append(_elapsed)
            if _elapsed > _LAYER_TIMEOUT_NS:
                logger.warning("Layer expression(fast) took %.1fms (>200ms)", _elapsed / 1e6)
            # Fast path still perturbs boundary lightly (10% force)
            if self._layer_enabled.get("boundary", True):
                fast_force = self._emotion_to_boundary_force(emotion)
                self.boundary.perturb([f * 0.1 for f in fast_force])
            self.boundary.self_repair()
            # HGT d_3 inhibition can veto expression
            if self._layer_enabled.get("expression", True):
                should_express_fast = (
                    self.expression.should_express() and hgt_decision[3] < 0.5
                )
            else:
                should_express_fast = False
            if should_express_fast:
                self._last_expression_time = timestamp
            result = self._build_result(
                text, timestamp, surprise, route, emotion, [], [], should_express_fast
            )
            result["hgt_decision"] = hgt_decision
            result["assessment_source"] = assessment_source
            result["sheaf"] = sheaf_result
            result["layers"] = {
                "L1_HDC": l1_payload,
                "L2_Gate": {
                    "surprise": surprise,
                    "route": route,
                    "mean_surprise": self.gate.mean_surprise(),
                },
                "L3_VoidScar": l3_payload,
                "L4_Sheaf": l4_payload,
                "L5_HGT": self._l5_payload(hgt_decision),
                "L6_Boundary": self.boundary.to_dict(),
                "L7_Expression": self.expression.state(),
            }
            self._drift_embodiment(result)
            self._result_cache[cache_key] = result
            return result

        # Normal/Full path: boundary + expression
        # Layer 5: Autopoietic Boundary
        t0 = time.perf_counter_ns()
        boundary_result = {}
        if not self._layer_enabled.get("boundary", True):
            self.boundary.self_repair()
            logger.debug("Layer boundary DISABLED — using defaults")
        else:
            force = self._emotion_to_boundary_force(emotion)
            if route == "full":
                sensitivity_mod = 1.0 + hgt_decision[1] * 0.5
                force = [f * sensitivity_mod for f in force]
                boundary_result = self.boundary.perturb(force)
            elif route == "normal":
                boundary_result = self.boundary.perturb([f * 0.3 for f in force])
            self.boundary.self_repair()
        _elapsed = time.perf_counter_ns() - t0
        self._timings["boundary"].append(_elapsed)
        if _elapsed > _LAYER_TIMEOUT_NS:
            logger.warning("Layer boundary took %.1fms (>200ms)", _elapsed / 1e6)

        # Layer 6: Phase Transition Expression
        t0 = time.perf_counter_ns()
        if not self._layer_enabled.get("expression", True):
            should_express = False
            logger.debug("Layer expression DISABLED — using defaults")
        else:
            drive = self.engine.expression_drive()
            # Apply HGT d_0 (expression drive correction)
            drive = max(0.0, min(1.0, drive + hgt_decision[0] * 0.3))
            if boundary_result.get("phase_transition"):
                drive = min(1.0, drive + 0.4)  # Phase transition boosts expression drive
            self.expression.accumulate(drive, dt=1.0)
            self.expression.silence_lowers_threshold(dt=dt)

            # HGT d_2 influences urgency (stored in expression state)
            # HGT d_3 inhibition can veto expression
            should_express = self.expression.should_express() and hgt_decision[3] < 0.5

            # Record expression time for feedback timeout detection
            if should_express:
                self._last_expression_time = timestamp
        _elapsed = time.perf_counter_ns() - t0
        self._timings["expression"].append(_elapsed)
        if _elapsed > _LAYER_TIMEOUT_NS:
            logger.warning("Layer expression took %.1fms (>200ms)", _elapsed / 1e6)

        result = self._build_result(
            text, timestamp, surprise, route, emotion, recalled, holes, should_express
        )
        result["hgt_decision"] = hgt_decision
        result["assessment_source"] = assessment_source
        result["sheaf"] = sheaf_result
        result["layers"] = {
            "L1_HDC": l1_payload,
            "L2_Gate": {
                "surprise": surprise,
                "route": route,
                "mean_surprise": self.gate.mean_surprise(),
            },
            "L3_VoidScar": l3_payload,
            "L4_Sheaf": l4_payload,
            "L5_HGT": self._l5_payload(hgt_decision),
            "L6_Boundary": self.boundary.to_dict(),
            "L7_Expression": self.expression.state(),
        }
        self._drift_embodiment(result)
        self._result_cache[cache_key] = result
        return result

    def _drift_embodiment(self, result: dict[str, Any]) -> None:
        """从处理结果中提取信号并漂移 Embodiment 人格特质。

        只有当某个特质变化超过 0.01 时才重新应用人格参数。
        有速率限制：两次漂移之间最少间隔 _drift_min_interval 秒。
        """
        # Drift rate limiting: skip if too soon since last drift
        timestamp = self._last_process_time
        if timestamp - self._last_drift_time < self._drift_min_interval:
            self._drift_tick += 1
            return
        self._last_drift_time = timestamp

        signals = self._signal_extractor.extract(result)
        if not signals:
            self._drift_tick += 1
            return
        compute_embodiment_drift(
            self._embodiment_traits,
            signals,
            self._drift_tick,
            oscillation_detector=self._oscillation_detector,
            drift_attribution=self._drift_attribution,
        )
        self._drift_tick += 1

        # Check if any trait changed significantly since last apply
        needs_reapply = False
        for name, tm in self._embodiment_traits.items():
            if abs(tm.value - self._last_embodiment_apply.get(name, 0.5)) > 0.01:
                needs_reapply = True
                break
        if needs_reapply:
            self._last_embodiment_apply = {
                n: t.value for n, t in self._embodiment_traits.items()
            }
            # Rebuild personality dict with new embodiment values mapped to legacy names
            from .personality import _REVERSE_LEGACY_MAP

            updated = dict(self._personality)
            for emb_name, tm in self._embodiment_traits.items():
                legacy_name = _REVERSE_LEGACY_MAP.get(emb_name)
                if legacy_name:
                    updated[legacy_name] = tm.value
                updated[emb_name] = tm.value
            self.apply_personality(updated)

    def _l5_payload(self, hgt_decision: list[float]) -> dict[str, Any]:
        attn = self.hgt._last_attention_weights
        experts = self.hgt._last_active_experts
        gates = self.hgt._last_gate_values
        return {
            "attention": [list(row) for row in attn] if attn else [],
            "experts": {
                "active": list(experts) if experts else [],
                "gates": list(gates) if gates else [],
                "names": ["defense", "curiosity", "social", "silence", "repair"],
            },
            "decision": list(hgt_decision),
            "adaptation": {
                "router_bias": list(self.hgt._router_adapt.bias)
                if hasattr(self.hgt, "_router_adapt")
                else [],
                "attention_drift": [],
                "plasticity": getattr(self.hgt, "_plasticity", 0.5),
            },
        }

    def express(self, now: float = 0.0) -> dict[str, Any]:
        """如果准备好则触发表达。"""
        if self.expression.should_express():
            self._last_expression_time = now
            return self.expression.express(now=now)
        return {"intensity": 0.0, "urgency": 0.0, "mode": "hint", "ready": False}

    def feedback(
        self, outcome: str, dt: float = 1.0, session_key: str = ""
    ) -> dict[str, float]:
        """注入表达结果反馈到虚空-伤痕引擎。

        同时更新：HGT 适应、Embodiment 人格漂移、每关系人格 delta。

        Args:
            outcome: "accepted" | "ignored" | "rejected"
            dt: 时间步长
            session_key: 可选的关系标识符，用于每关系 delta 更新

        Returns:
            反馈注入后的更新观测值
        """
        if outcome in self._feedback_counts:
            self._feedback_counts[outcome] += 1
        self.hgt.adapt(outcome)

        # Inject feedback signal into embodiment drift
        signal_key = f"feedback_{outcome}"
        if signal_key in ("feedback_accepted", "feedback_ignored", "feedback_rejected"):
            signals = {signal_key: 1.0}
            compute_embodiment_drift(
                self._embodiment_traits,
                signals,
                self._drift_tick,
                oscillation_detector=self._oscillation_detector,
                drift_attribution=self._drift_attribution,
            )

        # Update per-relationship personality delta
        if session_key:
            self._update_relationship_delta(session_key, outcome)

        return self.engine.feedback(outcome, dt)

    def _update_relationship_delta(self, session_key: str, outcome: str) -> None:
        """根据反馈结果更新每关系人格 delta。

        Delta 演化极慢（rate=0.005），每维度上限 +/-0.1：
          - accepted: 对此人稍微更外向、更随和
          - rejected: 对此人更内向、更神经质
          - ignored: 对此人稍微更内向
        """
        if session_key not in self._relationship_deltas:
            self._relationship_deltas[session_key] = {
                name: 0.0 for name in self._personality
            }
        delta = self._relationship_deltas[session_key]
        rate = 0.005  # very slow evolution
        if outcome == "accepted":
            delta["extraversion"] = min(0.1, delta.get("extraversion", 0.0) + rate)
            delta["agreeableness"] = min(0.1, delta.get("agreeableness", 0.0) + rate)
        elif outcome == "rejected":
            delta["extraversion"] = max(-0.1, delta.get("extraversion", 0.0) - rate * 2)
            delta["neuroticism"] = min(0.1, delta.get("neuroticism", 0.0) + rate)
        elif outcome == "ignored":
            delta["extraversion"] = max(-0.1, delta.get("extraversion", 0.0) - rate)
        # Mark dirty so next process() re-applies effective personality
        self._personality_dirty = True

    def diagnostics(self) -> dict[str, Any]:
        """完整诊断快照（用于调试和 UI 展示）。"""
        return {
            "tick_count": self._tick_count,
            "last_route": self._last_route,
            "route_counts": dict(self._route_counts),
            "feedback": dict(self._feedback_counts),
            "gate": self.gate.to_dict(),
            "engine": self.engine.diagnostics(),
            "emotion": self.engine.observe(),
            "boundary": self.boundary.to_dict(),
            "expression": self.expression.state(),
            "timing_stats": self.timing_stats(),
        }

    def timing_stats(self) -> dict[str, dict[str, float]]:
        """返回每层的 p50/p99 耗时统计（纳秒）。"""
        stats: dict[str, dict[str, float]] = {}
        for layer, samples in self._timings.items():
            if not samples:
                stats[layer] = {"p50_ns": 0.0, "p99_ns": 0.0, "count": 0}
                continue
            sorted_samples = sorted(samples)
            n = len(sorted_samples)
            p50_idx = max(0, int(n * 0.5) - 1)
            p99_idx = max(0, int(n * 0.99) - 1)
            stats[layer] = {
                "p50_ns": float(sorted_samples[p50_idx]),
                "p99_ns": float(sorted_samples[p99_idx]),
                "count": n,
            }
        return stats

    def to_dict(self) -> dict[str, Any]:
        """序列化完整状态用于持久化。"""
        return {
            "tick_count": self._tick_count,
            "last_process_time": self._last_process_time,
            "engine": self.engine.to_dict(),
            "boundary": self.boundary.to_dict(),
            "expression": self.expression.to_dict(),
            "gate": self.gate.to_dict(),
            "route_counts": dict(self._route_counts),
            "feedback_counts": dict(self._feedback_counts),
            "hgt_adaptation": self.hgt.to_dict(),
            "personality": dict(self._personality),
            "sheaf": self.sheaf.to_dict(),
            "embodiment_traits": {
                name: tm.to_dict() for name, tm in self._embodiment_traits.items()
            },
            "drift_tick": self._drift_tick,
            "last_drift_time": self._last_drift_time,
            "drift_min_interval": self._drift_min_interval,
            "relationship_deltas": dict(self._relationship_deltas),
        }

    def from_dict(self, data: dict[str, Any]):
        """从持久化状态恢复。"""
        self._tick_count = int(data.get("tick_count", 0))
        self._last_process_time = float(data.get("last_process_time", 0.0))
        if "engine" in data:
            # Rebuild engine from persisted scar/void state
            engine_data = data["engine"]
            from .scar_algebra import ScarredState

            if "scar" in engine_data:
                self.engine.scar_state = ScarredState.from_dict(engine_data["scar"])
            if "void" in engine_data:
                self.engine.void_space.from_dict(engine_data["void"])
            if "social_void" in engine_data:
                self.engine.social_void.from_dict(engine_data["social_void"])
            self.engine._coherence = engine_data.get("coherence", 1.0)
            self.engine._tick = engine_data.get("tick", 0)
        if "boundary" in data:
            self.boundary.from_dict(data["boundary"])
        if "expression" in data:
            self.expression.from_dict(data["expression"])
        if "gate" in data:
            self.gate.from_dict(data["gate"])
        if "route_counts" in data:
            for k, v in data["route_counts"].items():
                if k in self._route_counts:
                    self._route_counts[k] = int(v)
        if "feedback_counts" in data:
            for k, v in data["feedback_counts"].items():
                if k in self._feedback_counts:
                    self._feedback_counts[k] = int(v)
        if "hgt_adaptation" in data:
            self.hgt.from_dict(data["hgt_adaptation"])
        if "personality" in data:
            self._personality = dict(data["personality"])
        if "sheaf" in data:
            self.sheaf = ScarSheaf.from_dict(data["sheaf"])
        if "embodiment_traits" in data:
            for name, tm_data in data["embodiment_traits"].items():
                if name in self._embodiment_traits and isinstance(tm_data, dict):
                    self._embodiment_traits[name] = TraitMemory.from_dict(tm_data)
            self._last_embodiment_apply = {
                n: t.value for n, t in self._embodiment_traits.items()
            }
        if "drift_tick" in data:
            self._drift_tick = int(data["drift_tick"])
        self._last_drift_time = float(data.get("last_drift_time", 0.0))
        self._drift_min_interval = float(data.get("drift_min_interval", 30.0))
        if "relationship_deltas" in data:
            rd = BoundedDict(maxsize=200)
            for k, v in data["relationship_deltas"].items():
                rd[k] = v
            self._relationship_deltas = rd
        # Note: personality-derived parameters (thresholds, rates, etc.) are NOT
        # re-applied here. They will be re-derived on the next kernel.tick() call
        # when apply_personality() runs. This avoids overwriting restored state.

    @property
    def last_hdc_sample(self) -> list[int]:
        """返回最近一次 HDC 编码的前 64 位（0/1 列表，用于可视化）。"""
        if self._last_hdc_vec is None:
            return []
        h = self._last_hdc_vec
        bits: list[int] = []
        for byte_val in h[:8]:  # 8 bytes = 64 bits
            for bit_pos in range(8):
                bits.append((byte_val >> (7 - bit_pos)) & 1)
        return bits

    def _hdc_similarity(self, a: bytes, b: bytes) -> float:
        """基于 HDC 的相似度函数（供 VoidScarEngine 使用）。"""
        return self.encoder.similarity(bytearray(a), bytearray(b))

    def _hdc_to_ssm_input(self, h: bytearray, surprise: float) -> list[float]:
        """将 HDC bytearray 压缩为 8 维 SSM 输入。

        将超向量分为 8 个等长块，计算每块的 1-bit 密度，
        然后居中（-0.5）并乘以 2*surprise 作为缩放因子。
        """
        byte_dim = len(h)
        chunk_size = max(1, byte_dim // 8)
        result = []
        for i in range(8):
            chunk = h[i * chunk_size : (i + 1) * chunk_size]
            ones = sum(b.bit_count() for b in chunk)
            total_bits = len(chunk) * 8
            density = ones / max(1, total_bits)
            result.append((density - 0.5) * 2.0 * surprise)
        return result

    def _l1_hdc_payload(
        self, text: str, h: bytearray, surprise: float
    ) -> dict[str, Any]:
        """L1 层诊断数据：基于实际 HDC 向量的可序列化信息。"""
        ones = sum(b.bit_count() for b in h)
        total_bits = max(1, len(h) * 8)
        prediction = getattr(self.gate, "_prediction", None)
        flip_ratio = float(surprise)
        prediction_similarity = max(0.0, min(1.0, 1.0 - float(surprise)))
        if isinstance(prediction, (bytearray, bytes)):
            compared_bits = max(1, min(len(prediction), len(h)) * 8)
            xor_count = sum((a ^ b).bit_count() for a, b in zip(prediction, h))
            flip_ratio = xor_count / compared_bits
            prediction_similarity = 1.0 - flip_ratio
        sample_bits: list[int] = []
        for byte in h[:128]:
            for bit in range(8):
                sample_bits.append(1 if byte & (1 << (7 - bit)) else 0)
        return {
            "source": "encoder.encode_text",
            "input_text": text[:120],
            "vector_dim": self.encoder.dim,
            "byte_len": len(h),
            "density": round(ones / total_bits, 4),
            "flip_ratio": round(max(0.0, min(1.0, flip_ratio)), 4),
            "prediction_similarity": round(
                max(0.0, min(1.0, prediction_similarity)), 4
            ),
            "sample_bits": sample_bits[:1024],
            "sample_rows": 16,
            "sample_cols": 64,
        }

    def _l3_void_scar_payload(self, emotion: dict[str, float]) -> dict[str, Any]:
        """L3 层诊断数据：虚空/伤痕状态的可序列化信息。"""
        scar_objects = list(getattr(self.engine.scar_state, "scars", []) or [])
        void_objects = list(getattr(self.engine.void_space, "voids", []) or [])
        ghost_objects = list(getattr(self.engine.void_space, "ghosts", []) or [])
        scars = []
        for scar in scar_objects[:8]:
            item = scar.to_dict() if hasattr(scar, "to_dict") else {}
            dim = int(item.get("dimension", getattr(scar, "dimension", 0)) or 0)
            item["dimension"] = dim
            item["weight"] = round(float(self.engine.scar_state.scar_density(dim)), 4)
            scars.append(item)
        voids = []
        for idx, void in enumerate(void_objects[:8]):
            item = void.to_dict() if hasattr(void, "to_dict") else {}
            item["concept"] = f"void_{idx}"
            item["boundary_count"] = int(
                item.get("boundary_count", len(getattr(void, "boundary", []) or []))
                or 0
            )
            item["depth"] = round(
                float(item.get("depth", getattr(void, "depth", 0.0)) or 0.0), 4
            )
            item["pressure"] = round(
                float(item.get("pressure", getattr(void, "pressure", 0.0)) or 0.0), 4
            )
            item["age"] = int(item.get("age", getattr(void, "age", 0)) or 0)
            item["beta"] = round(
                float(item.get("beta", getattr(void, "beta", 0.0)) or 0.0), 4
            )
            voids.append(item)
        return {
            "source": "void_scar_engine",
            "scars": scars,
            "voids": voids,
            "scar_count": len(scar_objects),
            "void_count": len(void_objects),
            "coherence": round(float(getattr(self.engine, "_coherence", 1.0)), 4),
            "active_voids": int(emotion.get("active_voids", 0) or 0),
            "ghost_count": len(ghost_objects),
            "void_pressure": round(float(emotion.get("void_pressure", 0.0) or 0.0), 4),
        }

    def _l4_sheaf_payload(self, sheaf_result: dict[str, Any]) -> dict[str, Any]:
        """L4 层诊断数据：关系层析传播的可序列化信息。"""
        sheaf_result = sheaf_result if isinstance(sheaf_result, dict) else {}
        prop = sheaf_result.get("propagation", {})
        prop = prop if isinstance(prop, dict) else {}
        return {
            "source": "relational_sheaf.tick",
            "tick": int(sheaf_result.get("tick", 0) or 0),
            "propagated": bool(prop.get("propagated", False)),
            "reason": str(prop.get("reason", "")),
            "source_relationship": prop.get("source"),
            "affected_dims": list(prop.get("affected_dims", []) or [])[:16],
            "propagated_to": list(prop.get("propagated_to", []) or [])[:16],
            "energy": round(float(sheaf_result.get("energy", 0.0) or 0.0), 4),
            "dissociation_pressure": round(
                float(sheaf_result.get("dissociation_pressure", 0.0) or 0.0), 4
            ),
            "decay_factor": round(float(prop.get("decay_factor", 0.0) or 0.0), 4),
        }

    def _emotion_to_boundary_force(self, emotion: dict[str, float]) -> list[float]:
        """将 8 维情感状态映射为 32 维边界力向量（平铺 + 缩放）。"""
        # Map 8 emotion dims to 32-dim boundary space (tile + scale)
        values = [
            emotion.get("warmth", 0.0),
            emotion.get("arousal", 0.0),
            emotion.get("valence", 0.0),
            emotion.get("tension", 0.0),
            emotion.get("curiosity", 0.0),
            emotion.get("repair_pressure", 0.0),
            emotion.get("expression_drive", 0.0),
            emotion.get("boundary_firmness", 0.0),
        ]
        force = []
        for i in range(32):
            force.append(values[i % 8] * 0.3)
        return force

    def _build_result(
        self,
        text: str,
        timestamp: float,
        surprise: float,
        route: str,
        emotion: dict[str, float],
        recalled: list[dict],
        holes: list[dict],
        should_express: bool,
    ) -> dict[str, Any]:
        return {
            "tick": self._tick_count,
            "text": text[:120],
            "route": route,
            "surprise": round(surprise, 4),
            "emotion": {k: round(v, 4) for k, v in emotion.items()},
            "recalled": recalled,
            "holes": holes,
            "should_express": should_express,
            "expression_state": self.expression.state(),
            "boundary_stability": self.boundary.stability(),
        }
