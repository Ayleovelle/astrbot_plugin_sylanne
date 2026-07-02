"""Resonance Integration — the default serving spine (kernel.py:48-53).

ResonanceSpine exposes the ComputationSpine interface (process/feedback/express/
to_dict/from_dict/apply_personality). The name is historical: the iterate-to-
convergence "resonance field" it once wrapped is RETIRED (v2.5). The field is now
``DeterministicFusion`` (a single deterministic coherence pass), and the emotion
core is the predictive-coding ``PEL-Core`` (behind ``pel_core_enabled``). The 7
modules each compute once and contribute to a single-pass result; nothing iterates
to a fixed point. The result-dict contract is preserved for API compatibility.

Module mapping (injection index → computation unit):
  0: HDCEncoder (perception)
  1: PredictiveCodingGate (surprise/gating)
  2: VoidScarEngine (emotional core; PEL-Core when enabled)
  3: ScarSheaf (relational propagation)
  4: HGT (decision fusion)
  5: AutopoieticBoundary (self-repair)
  6: PhaseTransitionExpression (expression drive)
"""

from __future__ import annotations

import math
import time
from collections import deque
from typing import TYPE_CHECKING, Any

from .._numeric import _coerce_float
from . import pel_core as _pel_core  # module ref so SEMANTIC_PRIOR stays monkeypatchable
from .autopoiesis import AutopoieticBoundary
from .bounded_dict import BoundedDict
from .deterministic_fusion import create_deterministic_fusion
from .emergence import EmergenceTracker
from .expression_policy import ExpressionPolicy
from .hgt import HeterogeneousGraphTransformer
from .meta_learner import MetaLearner
from .pad_interop import PADProjector, PADVector
from .personality import (
    _REVERSE_LEGACY_MAP,
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
    from ..config import DimensionProfile

_TIMING_WINDOW = 50


class ResonanceSpine:
    """Drop-in replacement for ComputationSpine using resonance field dynamics.

    Same external interface: process(), feedback(), express(), to_dict(), from_dict().
    Internal mechanism: each real module computes its output, injects into the
    resonance field, field iterates until convergence, expression emerges from
    the converged state rather than being computed sequentially.

    The key difference from ComputationSpine: modules don't feed forward into
    each other — they all feed into the shared resonance field and influence
    each other through simplicial coupling dynamics.
    """

    __slots__ = (
        "_profile",
        "_tier",
        "_field",
        "_emergence",
        "_tick_count",
        "_last_process_time",
        "_personality",
        "_last_route",
        "_last_expression_time",
        "_route_counts",
        "_feedback_counts",
        "_timings",
        "_expression_drive",
        "_expression_threshold",
        "_should_express",
        "_last_resonance_meta",
        "_diagnostics_enabled",
        # Real modules
        "_encoder",
        "_gate",
        "_engine",
        "_sheaf",
        "_hgt",
        "_boundary",
        "_expression",
        "_last_hdc_vec",
        "_last_surprise",
        # Expression policy (contextual bandit)
        "_expression_policy",
        # Embodiment drift system (ported from ComputationSpine)
        "_drift_min_interval",
        "_embodiment_traits",
        "_signal_extractor",
        "_oscillation_detector",
        "_drift_attribution",
        "_drift_tick",
        "_last_embodiment_apply",
        "_last_drift_time",
        # Per-relationship personality
        "_relationship_deltas",
        "_last_effective_session",
        "_last_effective_params",
        "_personality_dirty",
        # PAD projector cache
        "_pad_projector_cache",
        # Meta-learner (online hyperparameter adaptation)
        "_meta_learner",
        # PEL-Core enable flag (config-gated; default off)
        "_pel_enabled",
        # PEL-Core D-10: last non-semantic assessor-advisable gate signal
        "_last_assessor_advisable",
    )

    def __init__(self, profile: DimensionProfile | None = None, *, pel_enabled: bool = False):
        if profile is None:
            from ..config import build_profile

            profile = build_profile("lite")
        self._profile = profile
        self._tier = profile.mode
        self._pel_enabled = pel_enabled

        # Resonance field + emergence
        self._field = create_deterministic_fusion(n_modules=7, tier=self._tier)
        self._emergence = EmergenceTracker(window=50)

        # Real computation modules (same as ComputationSpine)
        from .hdc import HDCEncoder

        self._encoder = HDCEncoder(dim=profile.hdc_dim)
        self._gate = PredictiveCodingGate(dim=profile.hdc_dim)
        self._engine = VoidScarEngine(
            n_dims=profile.emotion_dim,
            similarity_fn=self._hdc_similarity,
            scar_mlp_passes=profile.scar_mlp_passes,
            pel_enabled=pel_enabled,
        )
        self._sheaf = ScarSheaf(n0=profile.stalk_dim)
        self._hgt = HeterogeneousGraphTransformer(
            d_model=profile.d_model,
            n_heads=profile.n_heads,
            d_output=profile.d_output,
            n_experts=profile.n_experts,
            top_k_min=profile.top_k_min,
            top_k_max=profile.top_k_max,
            attention_rounds=profile.attention_rounds,
        )
        self._boundary = AutopoieticBoundary(
            identity_dim=profile.identity_dim,
            repair_passes=profile.repair_passes,
        )
        self._expression = PhaseTransitionExpression(order_params=profile.order_params)

        # State
        self._tick_count = 0
        self._last_process_time = 0.0
        self._personality: dict[str, float] = {
            "extraversion": 0.5,
            "neuroticism": 0.5,
            "conscientiousness": 0.5,
            "openness": 0.5,
            "agreeableness": 0.5,
        }
        self._last_route = "resonance"
        self._last_expression_time = 0.0
        self._route_counts: dict[str, int] = {"resonance": 0, "skip": 0}
        self._feedback_counts: dict[str, int] = {
            "accepted": 0,
            "ignored": 0,
            "rejected": 0,
        }
        self._timings: deque[int] = deque(maxlen=_TIMING_WINDOW)
        self._expression_drive = 0.0
        self._expression_threshold = 0.6
        self._should_express = False
        self._last_resonance_meta: dict[str, Any] = {}
        self._diagnostics_enabled = False
        self._last_hdc_vec: bytearray | None = None
        self._last_surprise = 0.0
        # D-10: default True (fail-safe — when in doubt, advise calling the assessor).
        self._last_assessor_advisable = True

        # Expression policy (contextual bandit for expression decisions)
        self._expression_policy = ExpressionPolicy(
            learning_rate=0.05,
            personality_openness=0.5,
        )

        # Embodiment personality drift system (ported from ComputationSpine)
        self._signal_extractor = DriftSignalExtractor()
        self._embodiment_traits: dict[str, TraitMemory] = {
            name: TraitMemory(0.5) for name in EMBODIMENT_TRAITS
        }
        self._oscillation_detector = OscillationDetector()
        self._drift_attribution = DriftAttribution(maxlen=100)
        self._drift_tick = 0
        self._last_embodiment_apply: dict[str, float] = {name: 0.5 for name in EMBODIMENT_TRAITS}
        self._last_drift_time: float = 0.0
        self._drift_min_interval: float = 30.0  # seconds

        # Per-relationship personality deltas
        self._relationship_deltas: BoundedDict = BoundedDict(maxsize=200)
        self._last_effective_session: str = ""
        self._last_effective_params: dict[str, float] = {}
        self._personality_dirty: bool = False

        # PAD projector cache
        self._pad_projector_cache: tuple[int, dict[str, float], PADProjector] | None = None

        # Meta-learner (online hyperparameter adaptation from feedback)
        self._meta_learner = MetaLearner()

    def _hdc_similarity(self, a: bytes, b: bytes) -> float:
        return self._encoder.similarity(a, b)

    def apply_personality(self, personality: dict[str, float]) -> None:
        """Personality modulates ALL dynamics: coupling, modules, field, expression.

        Every tunable parameter in the system derives from personality traits.
        This is the "personality-computation coupling" axiom (A7 in docs/theoretical_spec.md).
        """
        personality = normalize_personality(personality)
        self._personality = dict(personality)
        extraversion = float(personality.get("extraversion", 0.5))
        neuroticism = float(personality.get("neuroticism", 0.5))
        openness = float(personality.get("openness", 0.5))
        conscientiousness = float(personality.get("conscientiousness", 0.5))
        agreeableness = float(personality.get("agreeableness", 0.5))
        patience = float(personality.get("patience", 0.52))
        sovereignty = float(personality.get("sovereignty_guard", 0.68))

        # === Expression threshold ===
        self._expression_threshold = 0.9 - extraversion * 0.6

        # === Coupling dynamics (Kuramoto + Free Energy) ===
        # Openness → stronger coupling (more inter-module influence)
        self._field._coupling.kuramoto._k1 = 0.5 + openness * 1.0
        self._field._coupling.kuramoto._k2 = 0.25 + openness * 0.5
        self._field._coupling.kuramoto._k3 = 0.1 + openness * 0.3
        # Neuroticism → higher precision (more sensitive to prediction errors)
        self._field._coupling.free_energy._precision = 0.5 + neuroticism * 1.5
        # Agreeableness → lower broadcast threshold (easier global ignition)
        self._field._coupling.broadcast._threshold = 0.8 - agreeableness * 0.3

        # === Hebbian plasticity rates ===
        # Openness → faster learning (higher eta)
        self._field._coupling.plasticity._eta = 0.005 + openness * 0.015
        # Conscientiousness → slower decay (more stable connections)
        self._field._coupling.plasticity._lambda_decay = 0.002 - conscientiousness * 0.001

        # === Resonance field parameters ===
        # Neuroticism → less dissipation (emotions linger longer)
        self._field._dissipation = 0.03 - neuroticism * 0.02
        # Openness → weaker residual decay (more receptive to new input)
        self._field._residual_decay = 0.6 + (1.0 - openness) * 0.2
        # Conscientiousness → stronger identity (more consistent personality)
        self._field._identity_inertia = 0.9 + conscientiousness * 0.08
        # Sovereignty → higher identity cap (stronger sense of self)
        self._field._identity_max_norm = self._field._state_dim * (0.5 + sovereignty * 0.5)
        # Patience → more Hopfield attractors (richer emotional memory)
        self._field._max_attractors = max(3, int(5 + patience * 10))
        # Extraversion → stronger Hopfield pull (more habitual expression patterns)
        self._field._hopfield_strength = 0.03 + extraversion * 0.04

        # === Module-level personality (same as ComputationSpine) ===
        self._expression.threshold = 0.9 - extraversion * 0.6
        self._engine.scar_state.wound_threshold = 0.3 + extraversion * 0.6
        # PEL-Core: derive the latent attractor prior pi / W_gen / precisions from
        # personality (no-op unless PEL enabled on the 8-dim core).
        self._engine.scar_state.set_pel_priors(personality)
        self._engine.void_space._detection_threshold = 0.6 - neuroticism * 0.5
        self._engine.void_space.set_cooldown(openness)
        self._gate.precision = 0.3 + neuroticism * 0.5
        self._hgt.derive_params(personality)
        self._sheaf.derive_params(personality)
        self._boundary.set_personality_params(
            repair_rate=0.03 + conscientiousness * 0.04 - neuroticism * 0.02,
            phase_threshold=0.5 + sovereignty * 0.3 - openness * 0.15,
            rotation_angle=0.05 + openness * 0.1,
        )
        self._expression.set_personality_params(
            decay_rate=0.01 + extraversion * 0.03,
            silence_urgency_divisor=5.0 + patience * 15.0,
            refractory=0.01 + (1 - extraversion) * 0.04,
            silence_drop_rate=0.005 + neuroticism * 0.008,
            min_threshold_floor=0.15 + sovereignty * 0.2,
        )

        # === Expression policy: update personality modulation + A7 saddle ===
        # Hard-gate bounds become personality explicit functions. Anchor the
        # trait defaults at 0.5 (NOT derive_params' historical 0.68 for
        # sovereignty): 0.5 is the value that reproduces the legacy 0.95/0.1
        # constants, so deployments whose personality omits these keys keep
        # tick-for-tick identical behaviour.
        self._expression_policy.set_personality(
            openness,
            expression_drive_trait=float(personality.get("expression_drive_trait", 0.5)),
            sovereignty_guard=float(personality.get("sovereignty_guard", 0.5)),
        )

        # === Meta-learner: seed from personality, then override with adapted values ===
        self._meta_learner.init_from_personality(personality)
        meta = self._meta_learner.current_values
        if meta:
            self._expression_threshold = meta["expression_threshold"]
            self._field._dissipation = meta["dissipation"]
            self._field._residual_decay = meta["residual_decay"]
            self._field._hopfield_strength = meta["hopfield_strength"]
            self._field._identity_inertia = meta["identity_inertia"]
            self._field._coupling.kuramoto._k1 = meta["kuramoto_k1"]
            self._field._coupling.broadcast._threshold = meta["broadcast_threshold"]

    def _restore_pel_after_scar(self) -> None:
        """Reconcile a freshly-restored ScarredState with the spine's PEL flag.

        A snapshot that carried a ``"pel"`` sub-key already rebuilt the latent
        core (and marked it active). A legacy snapshot (no ``"pel"``) lands with
        PEL off; if this spine is configured for PEL, re-init the core from the
        current personality (migration-safe, techspec §4 ``data.get`` pattern).
        """
        scar = self._engine.scar_state
        if self._pel_enabled and not scar.pel_active():
            scar._pel_enabled = True
            scar.set_pel_priors(self._personality)

    def set_diagnostics(self, enabled: bool) -> None:
        self._diagnostics_enabled = enabled

    def switch_tier(self, new_tier: str) -> None:
        """Hot-switch computation tier. State is preserved losslessly."""
        if new_tier == self._tier:
            return
        from ..config import build_profile

        new_profile = build_profile(new_tier)  # type: ignore[arg-type]
        self._field.switch_tier(new_tier)
        self._tier = new_tier  # type: ignore[assignment]
        self._profile = new_profile
        # Clear emergence history (dimensions changed, old history is invalid)
        self._emergence = EmergenceTracker(window=50)
        # Re-apply personality to update tier-dependent parameters
        self.apply_personality(self._personality)

    def process(
        self,
        text: str,
        timestamp: float = 0.0,
        assessment: dict[str, Any] | None = None,
        *,
        session_key: str = "",
        dialogue_quality: float | None = None,
        expression_outcome: bool | None = None,
    ) -> dict[str, Any]:
        """Process one input message through the modules and produce a result dict.

        v2.5: the old "modules inject into a shared field that iterates to convergence"
        paradigm is retired — the field is now ``DeterministicFusion`` (a single
        deterministic coherence pass, no loop/attractors), and the emotion core is the
        predictive-coding ``PEL-Core`` (behind ``pel_core_enabled``). The per-tick flow
        is a single pass: HDC perception → PredictiveCodingGate (surprise) → VoidScar
        engine (emotion core, PEL when enabled) → assessor fold → DeterministicFusion
        coherence pass → emergence read → expression decision → embodiment drift. The
        result-dict contract (route/assessment_source literals, key sets, active_channels)
        is preserved.

        Args:
            text: 输入消息文本
            timestamp: 事件时间戳（epoch 秒）
            assessment: 可选的 LLM 评估结果，用于精确语义调制
            session_key: 可选的关系标识符，用于每关系人格覆盖
            dialogue_quality: 可选的上一轮回复质量自评（归一化 [0,1]）。这是滞后反馈——
                对第 N 轮回复的评分，在第 N+1 轮调 process() 时传入。高分强化表达欲、
                拉近关系，低分收敛表达欲（经 canonical 自动漂移通道，无后门）。
            expression_outcome: 可选的 agent 真实表达裁决（True=SPEAK, False=SILENT）。
                这是上一轮 renderer 裁决后的 ground-truth，在第 N+1 轮调 process() 时
                传入（与 dialogue_quality 同款滞后通道）。若提供，会覆盖 result["should_express"]
                中 policy 的猜测值，使 expression_fired 漂移信号反映真实裁决而非策略预测。
        """
        if not text or not text.strip():
            self._route_counts["skip"] = self._route_counts.get("skip", 0) + 1
            self._boundary.self_repair()
            return self._build_result("", timestamp, False)

        # Container guard: process() is a public entry, so a caller may hand in a
        # non-dict assessment — the same malformed shape Fix 1 shows an LLM emits
        # ([] / "x" / 42). Normalize it to None once, here, so every assessment-derived
        # branch below treats it as "no read" instead of AttributeError-ing on
        # assessment.get(...). Field-level None/non-numeric is handled later by _coerce_float.
        if assessment is not None and not isinstance(assessment, dict):
            assessment = None

        # Apply per-relationship personality overlay if session changed or dirty
        if session_key != self._last_effective_session or self._personality_dirty:
            effective = self.effective_personality(session_key)
            if effective != self._last_effective_params:
                self.apply_personality(effective)
                self._last_effective_params = dict(effective)
            self._last_effective_session = session_key
            self._personality_dirty = False

        self._tick_count += 1
        self._route_counts["resonance"] = self._route_counts.get("resonance", 0) + 1
        t0 = time.perf_counter_ns()

        # Compute dt
        if self._last_process_time > 0:
            dt = max(0.1, min(10.0, (timestamp - self._last_process_time) / 60.0))
        else:
            dt = 1.0
        self._last_process_time = timestamp

        # === Module 0: HDC Perception ===
        h = self._encoder.encode_text(text)
        self._last_hdc_vec = h
        hdc_signal = self._hdc_to_field_signal(h)
        self._field.inject(0, hdc_signal)

        # === Module 1: Predictive Coding Gate ===
        surprise = self._gate.surprise(h)
        self._gate.update(h, surprise)
        self._last_surprise = surprise
        gate_signal = [surprise * 0.5] * self._field.state_dim
        self._field.inject(1, gate_signal)

        # === Module 2: VoidScar Engine ===
        ssm_input = self._hdc_to_ssm_input(h, surprise)
        engine_result = self._engine.process(
            event_vec=bytes(h),
            ssm_input=ssm_input,
            surprise=surprise,
            timestamp=timestamp,
        )
        # D-10: non-semantic assessor-advisable gate. Wound hints come from the
        # engine's own coupling wounds / fresh scars this tick (no assessor needed).
        # Asymmetric safety: ANY wound hint => advisable True regardless of surprise.
        #
        # "Low novelty" is ADAPTIVE, not a fixed absolute constant. A tick counts as
        # low-surprise only when its surprise sits below the gate's own running-mean
        # surprise. The realistic spine regime has a high surprise floor (~0.45-0.5);
        # a small fixed threshold (the old 0.25) sat far below that floor, pinning the
        # gate to a constant True and leaving the "low => False" branch dead. Comparing
        # against the running mean keeps the branch live across regimes/corpora — about
        # half the ticks fall below their own recent average and advise skipping, while
        # any wound still forces True. SIGNAL ONLY: no downstream call is skipped here.
        scar_step = engine_result.get("scar")
        new_scars = scar_step.get("new_scars") if isinstance(scar_step, dict) else None
        wound_hint = bool(engine_result.get("coupling_wounds")) or bool(new_scars)
        low_surprise = surprise < self._gate.mean_surprise()
        self._last_assessor_advisable = (not low_surprise) or wound_hint
        if assessment:
            self._apply_assessment_to_engine(assessment)
        emotion = self._engine.observe()
        void_signal = [
            emotion.get("warmth", 0.0),
            emotion.get("arousal", 0.0),
            emotion.get("valence", 0.0),
            emotion.get("tension", 0.0),
            emotion.get("curiosity", 0.0),
            emotion.get("repair_pressure", 0.0),
            emotion.get("expression_drive", 0.0),
            emotion.get("boundary_firmness", 0.0),
        ]
        # Pad to state_dim
        void_signal += [0.0] * (self._field.state_dim - len(void_signal))
        self._field.inject(2, void_signal[: self._field.state_dim])

        # === Module 3: Relational Sheaf ===
        sheaf_result = self._sheaf.tick(0, ssm_input, timestamp=timestamp)
        sheaf_energy = float(
            sheaf_result.get("energy", 0.0) if isinstance(sheaf_result, dict) else 0.0
        )
        sheaf_signal = [sheaf_energy * 0.3] * self._field.state_dim
        self._field.inject(3, sheaf_signal)

        # === Module 4: HGT Decision ===
        hgt_tokens = self._hgt.build_tokens_from_spine(
            scar_state=self._engine.scar_state,
            void_space=self._engine.void_space,
            boundary=self._boundary,
            personality=self._personality,
            surprise=surprise,
            expression=self._expression,
            hdc_features=ssm_input,
        )
        hgt_decision = self._hgt.forward(hgt_tokens, self._personality)
        hgt_signal = list(hgt_decision) + [0.0] * (self._field.state_dim - len(hgt_decision))
        self._field.inject(4, hgt_signal[: self._field.state_dim])

        # === Module 5: Autopoietic Boundary ===
        force = self._emotion_to_boundary_force(emotion)
        boundary_result = self._boundary.perturb(force)
        self._boundary.self_repair()
        stability = self._boundary.stability()
        boundary_signal = [stability - 0.5] * self._field.state_dim
        if boundary_result.get("phase_transition"):
            boundary_signal[0] += 0.5
        self._field.inject(5, boundary_signal)

        # === Module 6: Expression (pre-resonance drive) ===
        drive = self._engine.expression_drive()
        drive = max(0.0, min(1.0, drive + hgt_decision[0] * 0.3))
        expr_signal = [drive * 0.5] * self._field.state_dim
        self._field.inject(6, expr_signal)

        # === RESONATE ===
        resonance_meta = self._field.resonate()
        self._last_resonance_meta = resonance_meta

        # === Emergence tracking + feedback into coupling ===
        emergence = self._emergence.update(
            module_states=self._field.module_states,
            energy=resonance_meta["energy"],
            sync_r=resonance_meta["sync_order"],
            iteration=self._tick_count,
        )
        # Criticality feedback: near-critical → amplify coupling
        if emergence.get("is_critical"):
            self._field._coupling.set_criticality(
                emergence["order_parameters"].get("criticality", 0.0)
            )
        else:
            self._field._coupling.set_criticality(0.0)

        # === Extract expression decision from converged field ===
        self._update_expression(resonance_meta, emergence, dt, hgt_decision)

        elapsed = time.perf_counter_ns() - t0
        self._timings.append(elapsed)

        result = self._build_result(text, timestamp, self._should_express, hgt_decision)
        if dialogue_quality is not None:
            result["dialogue_quality"] = dialogue_quality
            result["_consume_dialogue_quality"] = True  # one-shot bypass of drift rate-limit
        # Ground-truth 覆盖：agent 把上一轮 renderer 真实裁决（SPEAK/SILENT）经此通道
        # 灌入 result["should_express"]，覆盖 policy 猜测，消除假阳性 expression_fired。
        # 与 dialogue_quality 相同的滞后通道（N+1 轮传入上一轮裁决），无破契约。
        if expression_outcome is not None:
            result["should_express"] = bool(expression_outcome)
        self._drift_embodiment(result)
        return result

    def _drift_embodiment(self, result: dict[str, Any]) -> None:
        """从处理结果中提取信号并漂移 Embodiment 人格特质。

        只有当某个特质变化超过 0.01 时才重新应用人格参数。
        有速率限制：两次漂移之间最少间隔 _drift_min_interval 秒。
        """
        # Drift rate limiting: skip if too soon since last drift.
        # Exception: an explicit dialogue_quality feedback bypasses the interval gate
        # so fast-chat turns don't silently drop quality signals. Consume-once: the
        # marker is popped here, and _last_drift_time still advances on a bypass, so
        # repeated fast turns are dt-scaled down rather than blowing the 30s budget.
        timestamp = self._last_process_time
        dt = timestamp - self._last_drift_time
        has_explicit_feedback = result.pop("_consume_dialogue_quality", False)
        if dt < self._drift_min_interval and not has_explicit_feedback:
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
            dt=dt,
        )
        self._drift_tick += 1

        # Check if any trait changed significantly since last apply
        needs_reapply = False
        for name, tm in self._embodiment_traits.items():
            if abs(tm.value - self._last_embodiment_apply.get(name, 0.5)) > 0.01:
                needs_reapply = True
                break
        if needs_reapply:
            self._last_embodiment_apply = {n: t.value for n, t in self._embodiment_traits.items()}
            # Rebuild personality dict with new embodiment values mapped to legacy names
            updated = dict(self._personality)
            for emb_name, tm in self._embodiment_traits.items():
                legacy_name = _REVERSE_LEGACY_MAP.get(emb_name)
                if legacy_name:
                    updated[legacy_name] = tm.value
                updated[emb_name] = tm.value
            self.apply_personality(updated)

    def _hdc_to_field_signal(self, h: bytearray) -> list[float]:
        """Compress HDC vector into field state dimension."""
        dim = self._field.state_dim
        byte_len = len(h)
        chunk_size = max(1, byte_len // dim)
        signal = []
        for i in range(dim):
            chunk = h[i * chunk_size : (i + 1) * chunk_size]
            ones = sum(b.bit_count() for b in chunk)
            total = len(chunk) * 8
            signal.append((ones / max(1, total) - 0.5) * 2.0)
        return signal

    def _hdc_to_ssm_input(self, h: bytearray, surprise: float) -> list[float]:
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

    def _apply_assessment_to_engine(self, assessment: dict[str, Any]) -> None:
        """Drive the emotion core from the LLM's semantic read.

        The SDK cannot judge meaning on its own, so the assessor (external LLM) is
        the only source of real affect. Runs after the main VoidScar step but before
        ``observe()``, so the LLM's read moves *this* tick's emotion output. All
        nudges are gated on the assessor actually reporting non-zero affect — with no
        assessment (e.g. direct spine tests) this method is never reached.
        """
        n = self._engine.scar_state.n_dims
        # assessment may be a caller-supplied dict (public process()/host.on_request
        # entry points) whose fields came back explicitly null from an external LLM —
        # _coerce_float clamps and falls back on None/non-numeric instead of float(None)
        # crashing the whole tick. Same clamp ranges as before; happy path unchanged.
        wound_risk = _coerce_float(assessment.get("wound_risk", 0.0), 0.0, 1.0, 0.0)
        valence = _coerce_float(assessment.get("valence", 0.0), -1.0, 1.0, 0.0)
        arousal = _coerce_float(assessment.get("arousal", 0.0), 0.0, 1.0, 0.0)
        # Confidence scales how much the read drives the core: an unsure LLM nudges
        # gently, a confident one drives hard. Floor keeps a low-confidence read from
        # vanishing entirely. (Trauma/void paths below use raw thresholds — an extreme
        # wound_risk should land even at middling confidence.)
        gain = (0.4 + 0.6 * _coerce_float(assessment.get("confidence", 0.5), 0.0, 1.0, 0.5)) * 0.3

        # Strong hurt: irreversible trauma injection (tension + repair_pressure).
        # Done FIRST: step() re-evolves the whole base through the MLP, so the affect
        # bias below must land afterwards or it would be scrambled by the wound step.
        if wound_risk > 0.7:
            wound_vec = [0.0] * n
            if n > 3:
                wound_vec[3] = wound_risk * 0.8
            if n > 5:
                wound_vec[5] = wound_risk * 0.5
            self._engine.scar_state.step(wound_vec, 0.0, heal=False)

        # Continuous nudge: let mild/moderate semantic affect reach the core, not
        # only the extreme thresholds. observe() returns scar_state.base[d] directly,
        # while step() routes input through a random-seeded MLP that mixes dimensions
        # and does not preserve per-dim sign — so a transient affect read is biased
        # onto the observed base dims directly (the interpretable channel), stamped on
        # top of any wound step so it always shows in this tick's observation.
        # dim order: warmth0 arousal1 valence2 tension3 curiosity4 ...
        # v2.5 redesign (B): when PEL runs the semantic-prior path, the assessor
        # reaches z through the e2 precision-weighted prior (store_pel_affect below),
        # NOT this direct base stamp — collapsing the assessor dual-write into one
        # precision-weighted entry. The fast direct nudge is kept only for the legacy
        # path (PEL off, or SEMANTIC_PRIOR off). Wound injection + void pressure stay
        # live on both paths. (assessor->z fidelity under the e2 path is a ship red-line.)
        direct_affect = not (_pel_core.SEMANTIC_PRIOR and self._engine.scar_state.pel_active())
        if direct_affect:
            base = self._engine.scar_state.base
            if n > 2 and abs(valence) > 1e-6:
                base[2] = max(-1.0, min(1.0, base[2] + valence * gain))
            if n > 1 and arousal > 1e-6:
                base[1] = max(-1.0, min(1.0, base[1] + arousal * gain))
            if n > 0 and valence > 0.0:
                base[0] = max(
                    -1.0, min(1.0, base[0] + valence * gain * 0.67)
                )  # warmth tracks positive valence

        # Negative valence raises void pressure; strong positive valence relieves it.
        if valence < -0.5:
            for void in self._engine.void_space.voids[:2]:
                void.pressure = min(1.0, void.pressure + abs(valence) * 0.2)
        if valence > 0.5:
            for void in self._engine.void_space.voids[:3]:
                void.pressure *= max(0.5, 1.0 - valence * 0.3)

        # ``process()`` already populated VoidScarEngine's observe() cache; the
        # mutations above (scar base + void pressure) happen after that, so the
        # cache must be dropped for the upcoming ``observe()`` to see the LLM read.
        self._engine._cached_observe = None

        # PEL-Core 1-tick deferred fold (D-2): the main VoidScar step already ran
        # this tick *before* the assessor read was available, so stash the affect
        # for the NEXT main tick's x_t = c*a_vec + (1-c)*s*h_t. a_vec mirrors the
        # existing assessor->base mapping (design §3.1); no-op unless PEL is live.
        confidence = _coerce_float(assessment.get("confidence", 0.5), 0.0, 1.0, 0.5)
        a_vec = [
            0.67 * valence,  # 0 warmth tracks positive valence
            arousal,  # 1 arousal
            valence,  # 2 valence
            0.8 * wound_risk,  # 3 tension
            0.0,  # 4 curiosity
            0.5 * wound_risk,  # 5 repair_pressure
            0.0,  # 6 expression_drive
            0.0,  # 7 boundary_firmness
        ]
        self._engine.store_pel_affect(a_vec, confidence)

    def _emotion_to_boundary_force(self, emotion: dict[str, float]) -> list[float]:
        values = (
            emotion.get("warmth", 0.0),
            emotion.get("arousal", 0.0),
            emotion.get("valence", 0.0),
            emotion.get("tension", 0.0),
            emotion.get("curiosity", 0.0),
            emotion.get("repair_pressure", 0.0),
            emotion.get("expression_drive", 0.0),
            emotion.get("boundary_firmness", 0.0),
        )
        return [values[i & 7] * 0.3 for i in range(32)]

    def _update_expression(
        self,
        resonance_meta: dict[str, Any],
        emergence: dict[str, Any],
        dt: float,
        hgt_decision: list[float],
    ) -> None:
        """Expression as bifurcation: escaping an attractor IS the expression event.

        Three independent triggers (OR-gate — any one suffices):
        1. High surprise (predictive coding) — the input was unexpected
        2. Far from attractor (Hopfield) — the field is in novel territory
        3. Explosive sync (Kuramoto ignition) — modules suddenly cohere

        This makes expression a genuine emergent phase transition.
        """
        # Trigger 1: Surprise from predictive coding gate (most reliable signal)
        surprise_drive = self._last_surprise * 1.5

        # Trigger 2: Distance to nearest attractor (Hopfield novelty)
        attractor_dist = resonance_meta.get("near_attractor", float("inf"))
        if attractor_dist == float("inf"):
            novelty_drive = 0.5  # no attractors yet = moderate novelty
        else:
            novelty_drive = min(1.0, attractor_dist * 3.0)

        # Trigger 3: Explosive synchronization (Kuramoto ignition)
        # Use max sync delta from the resonance cycle (not post-hoc query)
        max_sync_delta = resonance_meta.get("max_sync_delta", 0.0)
        ignition_drive = max(0.0, max_sync_delta) * 5.0

        # Module 6 raw energy — normalized by field average to detect RELATIVE activation
        expr_state = self._field.module_states[6]
        raw_magnitude = math.sqrt(sum(x * x for x in expr_state))
        all_magnitudes = [
            math.sqrt(sum(x * x for x in self._field.module_states[i])) for i in range(7)
        ]
        avg_magnitude = sum(all_magnitudes) / 7.0
        # Raw drive = how much module 6 exceeds the average (relative activation)
        raw_drive = max(0.0, raw_magnitude - avg_magnitude) * 2.0

        # Φ modulates meaningfulness (low Φ = noise, high Φ = coherent signal)
        phi = emergence.get("phi", 0.0)
        meaning_gate = 0.3 + phi * 0.7

        # OR-gate: max of independent triggers, gated by meaningfulness
        bifurcation_drive = (
            max(
                surprise_drive,
                novelty_drive * 0.8,
                ignition_drive,
                raw_drive * 0.6,
            )
            * meaning_gate
        )

        # HGT inhibition veto (d_3 > 0.75 = strong "don't speak" signal)
        if hgt_decision[3] > 0.75:
            bifurcation_drive *= 0.2

        self._expression_drive = bifurcation_drive

        # Threshold decays over silence (pressure builds)
        self._expression_threshold = max(0.15, self._expression_threshold - 0.015 * dt)

        # === Expression policy decision (contextual bandit) ===
        # Build context vector for the policy
        ticks_since_expr = self._tick_count  # approximate; reset on expression
        ticks_since_user = 1.0  # we just got a message
        policy_context = [
            self._expression_drive,  # expression_drive
            self._expression_threshold,  # expression_threshold
            emergence.get("phi", 0.0),  # phi
            resonance_meta.get("sync_order", 0.0),  # sync_order
            resonance_meta.get("energy", 0.0),  # energy
            min(1.0, ticks_since_expr / 50.0),  # ticks_since_last_expression (normalized)
            min(1.0, ticks_since_user / 10.0),  # ticks_since_last_user_message (normalized)
            self._expression_policy.recent_accept_rate,  # recent_accept_rate
            self._expression_policy.recent_reject_rate,  # recent_reject_rate
            float(self._personality.get("extraversion", 0.5)),  # personality_extraversion
        ]

        # Ask policy for decision
        should_express, _confidence = self._expression_policy.decide(policy_context)

        # Hard constraints override policy. These bounds are the policy's own
        # personality-derived saddle (A7), read from the single source of truth
        # rather than re-hardcoded here — keeps this override in lockstep with
        # ``decide``'s internal gate. At neutral traits they are 0.95 / 0.1.
        if self._expression_drive > self._expression_policy.force_express_threshold:
            should_express = True
        elif self._expression_drive < self._expression_policy.force_hold_threshold:
            should_express = False

        self._should_express = should_express
        if self._should_express:
            self._expression_threshold = (
                0.9 - float(self._personality.get("extraversion", 0.5)) * 0.6
            )

    def express(self, now: float = 0.0) -> dict[str, Any]:
        if self._should_express:
            self._last_expression_time = now
            self._should_express = False
            return {
                "intensity": min(1.0, self._expression_drive),
                "urgency": min(1.0, self._expression_drive * 1.5),
                "mode": "resonance",
                "ready": True,
                "sync_order": self._last_resonance_meta.get("sync_order", 0.0),
            }
        return {"intensity": 0.0, "urgency": 0.0, "mode": "resonance", "ready": False}

    def topology_summary(self) -> dict[str, Any]:
        """Return topology gate statistics (active channels, sparsity, feedback counts)."""
        topo_gate = self._field._coupling.topology_gate
        if topo_gate is not None:
            return topo_gate.get_topology_summary()
        return {
            "n_active": self._field._complex.total_directed,
            "n_total": self._field._complex.total_directed,
            "sparsity": 0.0,
            "feedback_counts": {},
            "total_updates": 0,
        }

    def expression_policy_summary(self) -> dict[str, Any]:
        """Return diagnostics snapshot of the expression policy."""
        return self._expression_policy.diagnostics()

    def meta_learning_summary(self) -> dict[str, Any]:
        """Return diagnostics snapshot of the meta-learner state."""
        return self._meta_learner.diagnostics()

    def feedback(
        self,
        outcome: str,
        dt: float = 1.0,
        session_key: str = "",
        actual_expressed: bool | None = None,
    ) -> dict[str, float]:
        """Feedback modulates coupling plasticity + real engine state + topology.

        Args:
            outcome: "accepted" | "ignored" | "rejected".
            dt: time step.
            session_key: optional relationship identifier for per-relationship delta.
            actual_expressed: optional ground truth of whether expression actually
                fired downstream (True/False). When the final express/hold decision
                is owned by a layer above this spine (e.g. an external arbiter),
                pass it so the expression policy assigns credit to the action that
                was really executed rather than the one it internally planned.
                ``None`` (default) preserves the original behaviour. This is a pure
                passthrough to the expression policy — the other five feedback-bus
                consumers are untouched.
        """
        if outcome in self._feedback_counts:
            self._feedback_counts[outcome] += 1
        # Inject feedback into embodiment drift (parity with ComputationSpine.feedback).
        # 'ignored' is the real "expression got no response" signal (feedback_ignored ->
        # expression_drive_trait -0.2). ResonanceSpine previously omitted this, so being
        # persistently ignored could never drift expression drive on the resonance
        # channel (SDK backlog gap-1). Mirrors ComputationSpine exactly (no dt = full step).
        signal_key = f"feedback_{outcome}"
        if signal_key in ("feedback_accepted", "feedback_ignored", "feedback_rejected"):
            compute_embodiment_drift(
                self._embodiment_traits,
                {signal_key: 1.0},
                self._drift_tick,
                oscillation_detector=self._oscillation_detector,
                drift_attribution=self._drift_attribution,
            )
        # Real engine feedback (scar healing/deepening)
        self._engine.feedback(outcome, dt)
        # HGT adaptation
        self._hgt.adapt(outcome)
        # Coupling plasticity modulation
        n_weights = len(self._field._coupling.plasticity.weights)
        if outcome == "accepted":
            self._field._coupling.plasticity.update([0.3] * n_weights)
        elif outcome == "rejected":
            self._field._coupling.plasticity.update([0.0] * n_weights)
        elif outcome == "ignored":
            self._field._coupling.plasticity.update([0.05] * n_weights)
        # Topology gate feedback (learn which channels to keep/prune)
        topo_gate = self._field._coupling.topology_gate
        if topo_gate is not None:
            active_channels = topo_gate.get_active_channels()
            self._field._coupling.feedback_topology(outcome, active_channels)
        # Expression policy learning (REINFORCE update from feedback). Pass the
        # true executed action through when supplied (None -> legacy behaviour).
        actual_action = None if actual_expressed is None else int(bool(actual_expressed))
        self._expression_policy.update_from_feedback(outcome, actual_action=actual_action)
        # Meta-learner adaptation (online hyperparameter tuning)
        self._meta_learner.update(outcome)
        meta = self._meta_learner.current_values
        if meta:
            self._expression_threshold = meta["expression_threshold"]
            self._field._dissipation = meta["dissipation"]
            self._field._residual_decay = meta["residual_decay"]
            self._field._hopfield_strength = meta["hopfield_strength"]
            self._field._identity_inertia = meta["identity_inertia"]
            self._field._coupling.kuramoto._k1 = meta["kuramoto_k1"]
            self._field._coupling.broadcast._threshold = meta["broadcast_threshold"]
        # Update per-relationship personality deltas
        if session_key:
            self._update_relationship_delta(session_key, outcome)
        return self._engine.observe()

    def _update_relationship_delta(self, session_key: str, outcome: str) -> None:
        """Update per-relationship personality deltas based on feedback."""
        if session_key not in self._relationship_deltas:
            self._relationship_deltas[session_key] = {}
        delta = self._relationship_deltas[session_key]
        rate = 0.005
        if outcome == "accepted":
            delta["extraversion"] = min(0.1, delta.get("extraversion", 0.0) + rate)
            delta["agreeableness"] = min(0.1, delta.get("agreeableness", 0.0) + rate)
        elif outcome == "rejected":
            delta["extraversion"] = max(-0.1, delta.get("extraversion", 0.0) - rate * 2)
            delta["neuroticism"] = min(0.1, delta.get("neuroticism", 0.0) + rate)
        elif outcome == "ignored":
            delta["extraversion"] = max(-0.1, delta.get("extraversion", 0.0) - rate)
        self._personality_dirty = True

    def _build_result(
        self,
        text: str,
        timestamp: float,
        should_express: bool,
        hgt_decision: list[float] | None = None,
    ) -> dict[str, Any]:
        obs = self._field.observe()
        emotion = (
            self._engine.observe()
            if text
            else {
                "warmth": 0.0,
                "arousal": 0.0,
                "valence": 0.0,
                "tension": 0.0,
                "curiosity": 0.0,
                "repair_pressure": 0.0,
                "expression_drive": 0.0,
                "boundary_firmness": 0.0,
            }
        )
        resonance: dict[str, Any] = {
            "iterations": self._last_resonance_meta.get("iterations", 0),
            "converged": self._last_resonance_meta.get("converged", True),
            "energy": round(obs["total_energy"], 4),
            "sync_order": round(obs["sync_order"], 4),
            "active_channels": obs["active_channels"],
            "plasticity_ratio": round(obs["plasticity_ratio"], 4),
            "phi": round(self._emergence.phi.phi, 4),
        }
        # D-1: surface the PEL free energy as an additive key (present only when the
        # latent core is live, so the legacy path's result shape is unchanged).
        pel_diag = self._engine.scar_state.pel_diagnostics()
        if pel_diag is not None:
            resonance["free_energy"] = round(float(pel_diag["free_energy"]), 4)
        return {
            "tick": self._tick_count,
            "text": text[:120],
            "route": "resonance",
            "surprise": round(self._last_surprise, 4),
            "emotion": {k: round(float(v), 4) for k, v in emotion.items()},
            "recalled": [],
            "holes": [
                {"pressure": v.pressure, "depth": v.depth, "age": v.age}
                for v in self._engine.void_space.voids[:3]
            ],
            "should_express": should_express,
            "expression_state": {
                "drive": round(self._expression_drive, 4),
                "threshold": round(self._expression_threshold, 4),
                "mode": "resonance",
                "policy_confidence": round(self._expression_policy.policy_confidence, 4),
                "exploration_rate": round(self._expression_policy.exploration_rate, 4),
            },
            "boundary_stability": self._boundary.stability(),
            "resonance": resonance,
            "hgt_decision": list(hgt_decision) if hgt_decision else [0.0, 0.0, 0.0, 0.0],
            "assessment_source": "resonance_field",
        }

    def diagnostics(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "tick_count": self._tick_count,
            "last_route": self._last_route,
            "route_counts": dict(self._route_counts),
            "feedback": dict(self._feedback_counts),
            "field": self._field.observe(),
            "engine": self._engine.diagnostics(),
            "boundary": self._boundary.to_dict(),
            "expression": self._expression.state(),
            "emergence": {
                "phi": self._emergence.phi.phi,
                "order": self._emergence.order.order,
                "attractors": self._emergence.landscape.n_attractors,
                "narrative_tension": self._emergence.narrative.tension,
                "memory_depth": self._emergence.narrative.depth,
                "is_critical": self._emergence.order.is_critical,
            },
        }
        # D-10: non-semantic PEL gate signal + surprise + per-dim precisions.
        # SIGNAL ONLY — the SDK produces ``assessor_advisable``; any decision to
        # actually skip an assessor/LLM call is a downstream concern, not wired here.
        pel_diag = self._engine.scar_state.pel_diagnostics()
        if pel_diag is not None:
            out["pel"] = {
                "assessor_advisable": self._last_assessor_advisable,
                "surprise": round(self._last_surprise, 4),
                "free_energy": round(float(pel_diag["free_energy"]), 4),
                "pi_obs": pel_diag["pi_obs"],
                "pi_top": pel_diag["pi_top"],
                "mean_abs_e0": round(float(pel_diag["mean_abs_e0"]), 6),
                "mean_abs_e1": round(float(pel_diag["mean_abs_e1"]), 6),
                # 更脑 v2 production liveness witness (must-fix #4): a downstream
                # monitor windows these on real traffic and alerts if precision goes
                # dead (cross-dim spread collapses) where CI on the corpus stays green.
                "precision_live": pel_diag["precision_live"],
                "pi_obs_pstd": round(float(pel_diag["pi_obs_pstd"]), 6),
                "pi_top_pstd": round(float(pel_diag["pi_top_pstd"]), 6),
                "prod_spread": round(float(pel_diag["prod_spread"]), 6),
                "pi_anchor_drift": round(float(pel_diag["pi_anchor_drift"]), 6),
            }
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "tick_count": self._tick_count,
            "last_process_time": self._last_process_time,
            "personality": dict(self._personality),
            "field": self._field.to_dict(),
            "engine": self._engine.to_dict(),
            "boundary": self._boundary.to_dict(),
            "expression": self._expression.to_dict(),
            "gate": self._gate.to_dict(),
            "hgt_adaptation": self._hgt.to_dict(),
            "sheaf": self._sheaf.to_dict(),
            "route_counts": dict(self._route_counts),
            "feedback_counts": dict(self._feedback_counts),
            "expression_drive": self._expression_drive,
            "expression_threshold": self._expression_threshold,
            "expression_policy": self._expression_policy.to_dict(),
            "embodiment_traits": {
                name: tm.to_dict() for name, tm in self._embodiment_traits.items()
            },
            "relationship_deltas": dict(self._relationship_deltas),
            "drift_tick": self._drift_tick,
            "last_drift_time": self._last_drift_time,
            "drift_min_interval": self._drift_min_interval,
            "meta_learner": self._meta_learner.to_dict(),
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        self._tick_count = data.get("tick_count", 0)
        self._last_process_time = data.get("last_process_time", 0.0)
        if "personality" in data:
            self._personality = dict(data["personality"])
        if "field" in data:
            self._field.from_dict(data["field"])
        if "engine" in data:
            engine_data = data["engine"]
            from .scar_algebra import ScarredState

            if "scar" in engine_data:
                self._engine.scar_state = ScarredState.from_dict(
                    engine_data["scar"], pel_enabled=self._pel_enabled
                )
                self._restore_pel_after_scar()
            if "void" in engine_data:
                self._engine.void_space.from_dict(engine_data["void"])
        if "boundary" in data:
            self._boundary.from_dict(data["boundary"])
        if "expression" in data:
            self._expression.from_dict(data["expression"])
        if "gate" in data:
            self._gate.from_dict(data["gate"])
        if "hgt_adaptation" in data:
            self._hgt.from_dict(data["hgt_adaptation"])
        if "sheaf" in data:
            self._sheaf = ScarSheaf.from_dict(data["sheaf"])
        if "route_counts" in data:
            self._route_counts = dict(data["route_counts"])
        if "feedback_counts" in data:
            self._feedback_counts = dict(data["feedback_counts"])
        self._expression_drive = data.get("expression_drive", 0.0)
        self._expression_threshold = data.get("expression_threshold", 0.6)
        # Restore expression policy
        if "expression_policy" in data:
            self._expression_policy = ExpressionPolicy.from_dict(data["expression_policy"])
        # Restore embodiment traits
        if "embodiment_traits" in data:
            for name, tm_data in data["embodiment_traits"].items():
                if name in self._embodiment_traits and isinstance(tm_data, dict):
                    self._embodiment_traits[name] = TraitMemory.from_dict(tm_data)
        # Restore relationship deltas (reinitialize to avoid stale data)
        if "relationship_deltas" in data:
            self._relationship_deltas = BoundedDict(maxsize=200)
            for key, val in data["relationship_deltas"].items():
                self._relationship_deltas[key] = val
        self._drift_tick = data.get("drift_tick", 0)
        self._last_drift_time = data.get("last_drift_time", 0.0)
        self._drift_min_interval = data.get("drift_min_interval", 30.0)
        # Restore meta-learner
        if "meta_learner" in data:
            self._meta_learner = MetaLearner.from_dict(data["meta_learner"])

    # ------------------------------------------------------------------
    # Public properties for kernel/adapter/prompt_surface compatibility
    # ------------------------------------------------------------------

    @property
    def engine(self) -> VoidScarEngine:
        """Public accessor for the VoidScarEngine (used by kernel and adapter)."""
        return self._engine

    @property
    def expression(self) -> PhaseTransitionExpression:
        """Public accessor for the expression module (used by prompt_surface)."""
        return self._expression

    # ------------------------------------------------------------------
    # Methods ported from ComputationSpine for full compatibility
    # ------------------------------------------------------------------

    def embodiment_bounds(self) -> dict[str, float] | None:
        """Public accessor for embodiment trait bounds (used by kernel personality drift)."""
        return (
            {n: t.value for n, t in self._embodiment_traits.items()}
            if self._embodiment_traits
            else None
        )

    def effective_personality(self, session_key: str = "") -> dict[str, float]:
        """Get personality with per-relationship overlays applied."""
        base = dict(self._personality)
        if not session_key or session_key not in self._relationship_deltas:
            return base
        delta = self._relationship_deltas[session_key]
        for trait, d in delta.items():
            if trait in base:
                base[trait] = max(0.05, min(0.95, base[trait] + d))
        return base

    def apply_social_signals(self, signals: Any) -> None:
        """Apply social field signals (stub for API compatibility)."""
        # ResonanceSpine handles social modulation through coupling dynamics
        pass

    def pad_project(self) -> PADVector:
        """Project current VoidScar state to PAD 3D space."""
        n_dims = self._engine.scar_state.n_dims
        cache = self._pad_projector_cache
        if cache is None or cache[0] != n_dims or cache[1] != self._personality:
            projector = PADProjector(n_dims, self._personality)
            self._pad_projector_cache = (n_dims, dict(self._personality), projector)
        else:
            projector = cache[2]
        internal_state = list(self._engine.scar_state.base)
        return projector.project(internal_state)

    def set_layer_enabled(self, layer: str, enabled: bool) -> None:
        """No-op for ResonanceSpine (all modules always active in resonance)."""
        pass

    def replace_encoder(self, encoder: Any) -> None:
        """Replace the HDC encoder."""
        self._encoder = encoder

    @property
    def last_hdc_sample(self) -> bytearray | None:
        """Last HDC encoded vector."""
        return self._last_hdc_vec
