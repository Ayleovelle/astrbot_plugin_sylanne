"""Sylanne-Embodiment computation layer: Unified Computation Spine.

Integrates all computation modules into a single 7-layer pipeline:
  Perception(HDC) → Gate(PredictiveCoding) → VoidScarEngine →
  RelationalSheaf → HGT → Boundary(Autopoiesis) → Express(PhaseTransition)
"""

from __future__ import annotations

import time
from collections import deque
from typing import TYPE_CHECKING, Any

from .autopoiesis import AutopoieticBoundary
from .hdc import HDCEncoder
from .hgt import HeterogeneousGraphTransformer
from .personality import (
    EMBODIMENT_TRAITS,
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

_TIMING_WINDOW = 50


class ComputationSpine:
    """Unified computation pipeline for Sylanne-Embodiment."""

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
    )

    def __init__(self):
        self.encoder = HDCEncoder(dim=2048)
        self.gate = PredictiveCodingGate(dim=2048)
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
        self._drift_tick = 0
        self._last_embodiment_apply: dict[str, float] = {
            name: 0.5 for name in EMBODIMENT_TRAITS
        }
        # Drift rate limiting
        self._last_drift_time: float = 0.0
        self._drift_min_interval: float = 30.0  # seconds

        # Per-relationship personality deltas (session_key -> {trait: delta})
        self._relationship_deltas: dict[str, dict[str, float]] = {}

    def replace_encoder(self, encoder: HDCEncoder) -> None:
        """Replace the HDC encoder."""
        self.encoder = encoder

    def apply_personality(self, personality: dict[str, float]) -> None:
        """Derive computation parameters from personality vector.

        Accepts BOTH legacy Big Five names and new Embodiment Five names.
        Maps semantic personality dimensions to internal thresholds:
        - extraversion/expression_drive_trait → scar wound threshold
        - neuroticism/perception_acuity → void detection threshold
        - neuroticism/perception_acuity → healing rates
        - conscientiousness/inner_order → expression threshold
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
        """Get personality with per-relationship overlay applied.

        Each relationship can shift personality by at most +/-0.1 per dimension.
        If session_key is empty or unknown, returns the base personality.
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
        """Apply LLM assessment result to modulate Void-Scar state.

        Called when the LLM assessor returns within the timeout window,
        providing precise semantic judgment to refine the HDC coarse path.

        Args:
            assessment: Dict with keys like valence, arousal, intent, wound_risk.
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
        """Apply social field signals to L7 and L3."""
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
        """Main entry point: process one message through the full stack.

        Args:
            text: Input message text.
            timestamp: Event timestamp (epoch seconds).
            assessment: Optional LLM assessment result. If provided, used to
                        modulate Void-Scar state for precise semantic judgment.
                        If None, only HDC coarse path is used.
            session_key: Optional relationship identifier. When provided, applies
                         per-relationship personality overlay for this tick.
        """
        # Apply per-relationship personality overlay if session_key provided
        _personality_restored = False
        _saved_personality: dict[str, float] | None = None
        if session_key:
            effective = self.effective_personality(session_key)
            if effective != self._personality:
                _saved_personality = dict(self._personality)
                _personality_restored = True
                self.apply_personality(effective)
        # Empty string handling: skip computation, self-repair only
        if not text or not text.strip():
            self.boundary.self_repair()
            self.expression.silence_lowers_threshold(dt=1.0)
            result = self._build_result(
                "", timestamp, 0.0, "skip", self.engine.observe(), [], [], False
            )
            result["hgt_decision"] = [0.0, 0.0, 0.0, 0.0]
            result["assessment_source"] = "none"
            if _personality_restored and _saved_personality is not None:
                self.apply_personality(_saved_personality)
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
        self._last_hdc_vec = h
        self._timings["perception"].append(time.perf_counter_ns() - t0)

        # Layer 2: Predictive Coding Gate -- compute surprise, decide route
        t0 = time.perf_counter_ns()
        surprise = self.gate.surprise(h)
        l1_payload = self._l1_hdc_payload(text, h, surprise)
        route = self.gate.route(surprise)
        self.gate.update(h, surprise)
        self._last_route = route
        if route in self._route_counts:
            self._route_counts[route] += 1
        self._timings["gate"].append(time.perf_counter_ns() - t0)

        # Layer 3+4: Void-Scar Engine (replaces SSM + TopologicalMemory)
        t0 = time.perf_counter_ns()
        ssm_input = self._hdc_to_ssm_input(h, surprise)
        self.engine.process(
            event_vec=bytes(h),
            ssm_input=ssm_input,
            surprise=surprise,
            timestamp=timestamp,
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
        l3_payload = self._l3_void_scar_payload(emotion)

        # Layer 4: Relational Sheaf — cross-relational propagation
        t0 = time.perf_counter_ns()
        sheaf_result = self.sheaf.tick(0, ssm_input, timestamp=timestamp)
        self._timings["sheaf"].append(time.perf_counter_ns() - t0)
        l4_payload = self._l4_sheaf_payload(sheaf_result)

        # Layer 5: Heterogeneous Graph Transformer — decision fusion
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
            # Fast path still perturbs boundary lightly (10% force)
            fast_force = self._emotion_to_boundary_force(emotion)
            self.boundary.perturb([f * 0.1 for f in fast_force])
            self.boundary.self_repair()
            # HGT d_3 inhibition can veto expression
            should_express_fast = (
                self.expression.should_express() and hgt_decision[3] < 0.5
            )
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
            if _personality_restored and _saved_personality is not None:
                self.apply_personality(_saved_personality)
            return result

        # Normal/Full path: boundary + expression
        # Layer 5: Autopoietic Boundary
        t0 = time.perf_counter_ns()
        boundary_result = {}
        force = self._emotion_to_boundary_force(emotion)
        if route == "full":
            sensitivity_mod = 1.0 + hgt_decision[1] * 0.5
            force = [f * sensitivity_mod for f in force]
            boundary_result = self.boundary.perturb(force)
        elif route == "normal":
            boundary_result = self.boundary.perturb([f * 0.3 for f in force])
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
        if _personality_restored and _saved_personality is not None:
            self.apply_personality(_saved_personality)
        return result

    def _drift_embodiment(self, result: dict[str, Any]) -> None:
        """Extract signals from result and drift Embodiment traits.

        Only re-applies personality if any trait changed by > 0.01.
        Rate-limited: minimum interval between drift events.
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
        """Trigger expression if ready."""
        if self.expression.should_express():
            self._last_expression_time = now
            return self.expression.express(now=now)
        return {"intensity": 0.0, "urgency": 0.0, "mode": "hint", "ready": False}

    def feedback(
        self, outcome: str, dt: float = 1.0, session_key: str = ""
    ) -> dict[str, float]:
        """Inject expression outcome back into the Void-Scar engine.

        Args:
            outcome: "accepted" | "ignored" | "rejected"
            dt: time delta
            session_key: Optional relationship identifier for per-relationship delta update.

        Returns:
            The updated observation after feedback injection.
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
            )

        # Update per-relationship personality delta
        if session_key:
            self._update_relationship_delta(session_key, outcome)

        return self.engine.feedback(outcome, dt)

    def _update_relationship_delta(self, session_key: str, outcome: str) -> None:
        """Update per-relationship personality delta based on feedback outcome.

        Deltas evolve slowly (rate=0.005) and are capped at +/-0.1 per dimension.
        - accepted: slightly more extraverted and agreeable with this person
        - rejected: less extraverted, more neurotic with this person
        - ignored: slightly less extraverted with this person
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

    def diagnostics(self) -> dict[str, Any]:
        """Full diagnostic snapshot."""
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
        """Restore from persisted state."""
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
            self._relationship_deltas = data["relationship_deltas"]
        # Note: personality-derived parameters (thresholds, rates, etc.) are NOT
        # re-applied here. They will be re-derived on the next kernel.tick() call
        # when apply_personality() runs. This avoids overwriting restored state.

    @property
    def last_hdc_sample(self) -> list[int]:
        """Return first 64 bits of the last HDC encoding as 0/1 list."""
        if self._last_hdc_vec is None:
            return []
        h = self._last_hdc_vec
        bits: list[int] = []
        for byte_val in h[:8]:  # 8 bytes = 64 bits
            for bit_pos in range(8):
                bits.append((byte_val >> (7 - bit_pos)) & 1)
        return bits

    def _hdc_similarity(self, a: bytes, b: bytes) -> float:
        """HDC-based similarity for the VoidScarEngine."""
        return self.encoder.similarity(bytearray(a), bytearray(b))

    def _hdc_to_ssm_input(self, h: bytearray, surprise: float) -> list[float]:
        """Compress HDC bytearray to 8-dim SSM input."""
        byte_dim = len(h)
        chunk_size = max(1, byte_dim // 8)
        result = []
        for i in range(8):
            chunk = h[i * chunk_size : (i + 1) * chunk_size]
            ones = sum(bin(b).count("1") for b in chunk)
            total_bits = len(chunk) * 8
            density = ones / max(1, total_bits)
            result.append((density - 0.5) * 2.0 * surprise)
        return result

    def _l1_hdc_payload(
        self, text: str, h: bytearray, surprise: float
    ) -> dict[str, Any]:
        """Serializable Layer 1 diagnostics backed by the actual HDC vector."""
        ones = sum(bin(byte).count("1") for byte in h)
        total_bits = max(1, len(h) * 8)
        prediction = getattr(self.gate, "_prediction", None)
        flip_ratio = float(surprise)
        prediction_similarity = max(0.0, min(1.0, 1.0 - float(surprise)))
        if isinstance(prediction, (bytearray, bytes)):
            compared_bits = max(1, min(len(prediction), len(h)) * 8)
            xor_count = sum(bin(a ^ b).count("1") for a, b in zip(prediction, h))
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
        """Serializable Layer 3 diagnostics for Void/Scar state."""
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
        """Serializable Layer 4 diagnostics for relational sheaf propagation."""
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
