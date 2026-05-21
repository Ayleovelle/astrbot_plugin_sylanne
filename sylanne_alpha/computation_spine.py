"""Sylanne-Embodiment computation layer: Unified Computation Spine.

Integrates all computation modules into a single pipeline:
  Perception(HDC) → Gate(PredictiveCoding) → VoidScarEngine →
  Boundary(Autopoiesis) → Express(PhaseTransition)
"""
from __future__ import annotations

import time
from collections import deque
from typing import Any

from .hdc import HDCEncoder
from .hgt import HeterogeneousGraphTransformer
from .predictive_coding import PredictiveCodingGate
from .void_scar_engine import VoidScarEngine
from .autopoiesis import AutopoieticBoundary
from .phase_transition import PhaseTransitionExpression

_TIMING_WINDOW = 50


class ComputationSpine:
    """Unified computation pipeline for Sylanne-Embodiment."""

    __slots__ = (
        "encoder", "gate", "engine", "boundary", "expression", "hgt",
        "_tick_count", "_last_route", "_last_expression_time", "_timings",
        "_last_process_time", "_personality", "_last_assessment",
    )

    def __init__(self):
        self.encoder = HDCEncoder(dim=2048)
        self.gate = PredictiveCodingGate(dim=2048)
        self.engine = VoidScarEngine(n_dims=8, similarity_fn=self._hdc_similarity)
        self.boundary = AutopoieticBoundary(identity_dim=32)
        self.expression = PhaseTransitionExpression()
        self.hgt = HeterogeneousGraphTransformer(d_model=16, n_heads=4, d_output=4)
        self._tick_count = 0
        self._last_route = "fast"
        self._last_expression_time = 0.0
        self._last_process_time = 0.0
        self._personality: dict[str, float] = {
            "extraversion": 0.5, "neuroticism": 0.5,
            "conscientiousness": 0.5, "openness": 0.5, "agreeableness": 0.5,
        }
        self._last_assessment: dict[str, Any] | None = None
        self._timings: dict[str, deque] = {
            "perception": deque(maxlen=_TIMING_WINDOW),
            "gate": deque(maxlen=_TIMING_WINDOW),
            "void_scar": deque(maxlen=_TIMING_WINDOW),
            "hgt": deque(maxlen=_TIMING_WINDOW),
            "boundary": deque(maxlen=_TIMING_WINDOW),
            "expression": deque(maxlen=_TIMING_WINDOW),
        }

    def replace_encoder(self, encoder: HDCEncoder) -> None:
        """Replace the HDC encoder."""
        self.encoder = encoder

    def apply_personality(self, personality: dict[str, float]) -> None:
        """Derive computation parameters from personality vector.

        Maps semantic personality dimensions to internal thresholds:
        - extraversion → scar wound threshold (extraverts wound less easily)
        - neuroticism → void detection threshold (neurotic = detects absence easily)
        - neuroticism → healing rates (high neuroticism = slower healing)
        - conscientiousness → expression threshold
        """
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
        self.engine.scar_state.set_healing_rates(t_raw, t_closing, t_scarred)

        # HGT: derive all transformer parameters from personality
        self.hgt.derive_params(personality)

    def apply_assessment(self, assessment: dict[str, Any]) -> None:
        """Apply LLM assessment result to modulate Void-Scar state.

        Called when the LLM assessor returns within the timeout window,
        providing precise semantic judgment to refine the HDC coarse path.

        Args:
            assessment: Dict with keys like valence, arousal, intent, wound_risk.
        """
        self._last_assessment = assessment
        wound_risk = float(assessment.get("wound_risk", 0.0))
        valence = float(assessment.get("valence", 0.0))
        arousal = float(assessment.get("arousal", 0.0))
        intent = str(assessment.get("intent", ""))

        # High wound risk → inject a wound event into scar state
        if wound_risk > 0.7:
            wound_vec = [0.0] * self.engine.scar_state.n_dims
            # Wound on dimension 3 (tension-related) and 5 (repair pressure)
            wound_vec[3] = wound_risk * 0.8
            wound_vec[5] = wound_risk * 0.5
            self.engine.scar_state.step(wound_vec, 0.0)

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
                self.engine.scar_state.base[0] = min(1.0, self.engine.scar_state.base[0] + 0.1)  # warmth dim
        elif intent == "生气":
            # Anger → raise tension in base state
            if len(self.engine.scar_state.base) > 3:
                self.engine.scar_state.base[3] = min(1.0, self.engine.scar_state.base[3] + 0.2)

        # Arousal modulates expression drive accumulation rate
        if arousal > 0.7:
            self.expression.accumulate(arousal * 0.2, dt=0.5)

    def process(self, text: str, timestamp: float = 0.0, assessment: dict[str, Any] | None = None) -> dict[str, Any]:
        """Main entry point: process one message through the full stack.

        Args:
            text: Input message text.
            timestamp: Event timestamp (epoch seconds).
            assessment: Optional LLM assessment result. If provided, used to
                        modulate Void-Scar state for precise semantic judgment.
                        If None, only HDC coarse path is used.
        """
        # Empty string handling: skip computation, self-repair only
        if not text or not text.strip():
            self.boundary.self_repair()
            self.expression.silence_lowers_threshold(dt=1.0)
            result = self._build_result("", timestamp, 0.0, "skip", self.engine.observe(), [], [], False)
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
        h = self.encoder.encode_text(text)
        self._timings["perception"].append(time.perf_counter_ns() - t0)

        # Layer 2: Predictive Coding Gate -- compute surprise, decide route
        t0 = time.perf_counter_ns()
        surprise = self.gate.surprise(h)
        route = self.gate.route(surprise)
        self.gate.update(h, surprise)
        self._last_route = route
        self._timings["gate"].append(time.perf_counter_ns() - t0)

        # Layer 3+4: Void-Scar Engine (replaces SSM + TopologicalMemory)
        t0 = time.perf_counter_ns()
        ssm_input = self._hdc_to_ssm_input(h, surprise)
        self.engine.process(
            event_vec=bytes(h), ssm_input=ssm_input,
            surprise=surprise, timestamp=timestamp,
        )
        emotion = self.engine.observe()
        # Void boundaries serve as "recalled" context (related memory)
        recalled = [
            {"boundary_size": len(v.boundary), "pressure": v.pressure, "depth": v.depth}
            for v in self.engine.void_space.voids[:3]
        ]
        holes = [
            {"pressure": v.pressure, "depth": v.depth, "age": v.age}
            for v in self.engine.void_space.voids
        ]
        self._timings["void_scar"].append(time.perf_counter_ns() - t0)

        # Layer 3.5: LLM Assessment modulation (if available this tick)
        assessment_source = "hdc_only"
        if assessment:
            self.apply_assessment(assessment)
            assessment_source = "llm_assessed"
            # Re-observe after assessment modulation
            emotion = self.engine.observe()

        # Layer 4.5: Heterogeneous Graph Transformer — decision fusion
        t0 = time.perf_counter_ns()
        hdc_features = self._hdc_to_ssm_input(h, surprise)  # Reuse 8-dim compression
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
        self._timings["hgt"].append(time.perf_counter_ns() - t0)

        # Fast path: skip heavy computation
        if route == "fast":
            t0 = time.perf_counter_ns()
            drive = self.engine.expression_drive()
            # Apply HGT d_0 (expression drive correction)
            drive = max(0.0, min(1.0, drive + hgt_decision[0] * 0.3))
            self.expression.accumulate(drive, dt=1.0)
            self._timings["expression"].append(time.perf_counter_ns() - t0)
            self.boundary.self_repair()
            # HGT d_3 inhibition can veto expression
            should_express_fast = self.expression.should_express() and hgt_decision[3] < 0.5
            if should_express_fast:
                self._last_expression_time = timestamp
            result = self._build_result(text, timestamp, surprise, route, emotion, [], [], should_express_fast)
            result["hgt_decision"] = hgt_decision
            result["assessment_source"] = assessment_source
            return result

        # Normal/Full path: boundary + expression
        # Layer 5: Autopoietic Boundary (full path only)
        t0 = time.perf_counter_ns()
        boundary_result = {}
        if route == "full":
            force = self._emotion_to_boundary_force(emotion)
            # Apply HGT d_1 (boundary sensitivity correction)
            sensitivity_mod = 1.0 + hgt_decision[1] * 0.5
            force = [f * sensitivity_mod for f in force]
            boundary_result = self.boundary.perturb(force)
        self.boundary.self_repair()
        self._timings["boundary"].append(time.perf_counter_ns() - t0)

        # Layer 6: Phase Transition Expression
        t0 = time.perf_counter_ns()
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
        self._timings["expression"].append(time.perf_counter_ns() - t0)

        result = self._build_result(text, timestamp, surprise, route, emotion, recalled, holes, should_express)
        result["hgt_decision"] = hgt_decision
        result["assessment_source"] = assessment_source
        return result

    def express(self, now: float = 0.0) -> dict[str, Any]:
        """Trigger expression if ready."""
        if self.expression.should_express():
            self._last_expression_time = now
            return self.expression.express(now=now)
        return {"intensity": 0.0, "urgency": 0.0, "mode": "hint", "ready": False}

    def feedback(self, outcome: str, dt: float = 1.0) -> dict[str, float]:
        """Inject expression outcome back into the Void-Scar engine.

        Args:
            outcome: "accepted" | "ignored" | "rejected"
            dt: time delta

        Returns:
            The updated observation after feedback injection.
        """
        return self.engine.feedback(outcome, dt)

    def diagnostics(self) -> dict[str, Any]:
        """Full diagnostic snapshot."""
        return {
            "tick_count": self._tick_count,
            "last_route": self._last_route,
            "gate": self.gate.to_dict(),
            "engine": self.engine.diagnostics(),
            "emotion": self.engine.observe(),
            "boundary": self.boundary.to_dict(),
            "expression": self.expression.state(),
            "timing_stats": self.timing_stats(),
        }

    def timing_stats(self) -> dict[str, dict[str, float]]:
        """Return p50/p99 timing stats per layer in nanoseconds."""
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
        """Serialize full state for persistence."""
        return {
            "tick_count": self._tick_count,
            "engine": self.engine.to_dict(),
            "boundary": self.boundary.to_dict(),
            "expression": self.expression.to_dict(),
            "gate": self.gate.to_dict(),
        }

    def from_dict(self, data: dict[str, Any]):
        """Restore from persisted state."""
        self._tick_count = int(data.get("tick_count", 0))
        if "engine" in data:
            # Rebuild engine from persisted scar/void state
            engine_data = data["engine"]
            from .scar_algebra import ScarredState
            if "scar" in engine_data:
                self.engine.scar_state = ScarredState.from_dict(engine_data["scar"])
            if "void" in engine_data:
                # VoidSpace doesn't have from_dict, restore tick only
                self.engine.void_space._tick = engine_data["void"].get("tick", 0)
            self.engine._coherence = engine_data.get("coherence", 1.0)
            self.engine._tick = engine_data.get("tick", 0)
        if "boundary" in data:
            self.boundary.from_dict(data["boundary"])
        if "expression" in data:
            self.expression.from_dict(data["expression"])
        if "gate" in data:
            self.gate.from_dict(data["gate"])

    def _hdc_similarity(self, a: bytes, b: bytes) -> float:
        """HDC-based similarity for the VoidScarEngine."""
        return self.encoder.similarity(bytearray(a), bytearray(b))

    def _hdc_to_ssm_input(self, h: bytearray, surprise: float) -> list[float]:
        """Compress HDC bytearray to 8-dim SSM input."""
        byte_dim = len(h)
        chunk_size = max(1, byte_dim // 8)
        result = []
        for i in range(8):
            chunk = h[i * chunk_size:(i + 1) * chunk_size]
            ones = sum(bin(b).count('1') for b in chunk)
            total_bits = len(chunk) * 8
            density = ones / max(1, total_bits)
            result.append((density - 0.5) * 2.0 * surprise)
        return result

    def _emotion_to_boundary_force(self, emotion: dict[str, float]) -> list[float]:
        """Convert emotion state to a force vector for the autopoietic boundary."""
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
        self, text: str, timestamp: float, surprise: float, route: str,
        emotion: dict[str, float], recalled: list[dict], holes: list[dict],
        should_express: bool,
    ) -> dict[str, Any]:
        return {
            "tick": self._tick_count,
            "route": route,
            "surprise": round(surprise, 4),
            "emotion": {k: round(v, 4) for k, v in emotion.items()},
            "recalled": recalled,
            "holes": holes,
            "should_express": should_express,
            "expression_state": self.expression.state(),
            "boundary_stability": self.boundary.stability(),
        }
