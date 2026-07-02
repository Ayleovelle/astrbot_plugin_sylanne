"""Configuration dataclass for SylanneEngine."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Literal

# ---------------------------------------------------------------------------
# Compute backend auto-detection
# ---------------------------------------------------------------------------


def _detect_backend() -> str:
    """Detect best available compute backend: torch > cupy > numpy > python."""
    try:
        import torch  # noqa: F401

        if torch.cuda.is_available():
            return "torch"
    except ImportError:
        pass
    try:
        import cupy  # noqa: F401

        return "cupy"
    except ImportError:
        pass
    try:
        import numpy  # noqa: F401

        return "numpy"
    except ImportError:
        pass
    return "python"


_DETECTED_BACKEND: str | None = None


def get_backend() -> str:
    """Return cached backend detection result."""
    global _DETECTED_BACKEND
    if _DETECTED_BACKEND is None:
        _DETECTED_BACKEND = _detect_backend()
    return _DETECTED_BACKEND


# ---------------------------------------------------------------------------
# Dimension profiles for lite / pro / max modes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DimensionProfile:
    """Immutable dimension configuration derived from mode selection.

    All layer dimensions are determined by the mode. Downstream layers
    read these values at construction time — no runtime branching needed.
    """

    mode: Literal["lite", "pro", "max"]

    # L1 HDC
    hdc_dim: int

    # L3 VoidScar emotion dimensions
    emotion_dim: int
    scar_mlp_passes: int  # MLP refinement passes per tick

    # L4 Relational Sheaf stalk dimensions
    stalk_dim: int

    # L5 HGT
    d_model: int
    n_heads: int
    d_head: int
    d_output: int
    n_experts: int
    top_k_min: int
    top_k_max: int
    attention_rounds: int  # multi-round cross-attention

    # L6 Autopoiesis
    identity_dim: int
    repair_passes: int  # self-repair iterations per tick

    # L7 Phase Transition
    order_params: int  # number of order parameters (competing drives)

    # Concurrency target (informational, used for tuning)
    concurrency_target: int

    # Effective backend for this profile
    backend: str


_PROFILES: dict[str, dict[str, int | str]] = {
    "lite": {
        "hdc_dim": 2048,
        "emotion_dim": 8,
        "scar_mlp_passes": 1,
        "stalk_dim": 8,
        "d_model": 16,
        "n_heads": 4,
        "d_head": 4,
        "d_output": 4,
        "n_experts": 5,
        "top_k_min": 2,
        "top_k_max": 2,
        "attention_rounds": 1,
        "identity_dim": 32,
        "repair_passes": 1,
        "order_params": 1,
        "concurrency_target": 50,
    },
    "pro": {
        "hdc_dim": 4096,
        "emotion_dim": 16,
        "scar_mlp_passes": 2,
        "stalk_dim": 16,
        "d_model": 32,
        "n_heads": 8,
        "d_head": 4,
        "d_output": 8,
        "n_experts": 16,
        "top_k_min": 2,
        "top_k_max": 4,
        "attention_rounds": 2,
        "identity_dim": 64,
        "repair_passes": 2,
        "order_params": 3,
        "concurrency_target": 25,
    },
    "max": {
        "hdc_dim": 16384,
        "emotion_dim": 128,
        "scar_mlp_passes": 3,
        "stalk_dim": 64,
        "d_model": 128,
        "n_heads": 16,
        "d_head": 8,
        "d_output": 32,
        "n_experts": 32,
        "top_k_min": 4,
        "top_k_max": 8,
        "attention_rounds": 4,
        "identity_dim": 256,
        "repair_passes": 4,
        "order_params": 6,
        "concurrency_target": 50,
    },
}


def build_profile(
    mode: Literal["lite", "pro", "max"],
    force_backend: str | None = None,
) -> DimensionProfile:
    """Build a DimensionProfile for the given mode with auto-detected backend.

    Args:
        mode: Computation tier.
        force_backend: If set, override auto-detection with this backend.
    """
    params = _PROFILES[mode]
    if force_backend is not None:
        backend = force_backend
    elif mode == "max":
        # Only the max GPU tier needs real backend detection (which may import torch).
        backend = get_backend()
    else:
        # lite / pro never use a GPU backend; decide numpy-vs-python WITHOUT importing
        # torch. The eager ``import torch`` in get_backend()/_detect_backend balloons
        # the 2c2g deploy path by ~458 MB RSS for a result both tiers immediately
        # discard below — ``importlib.util.find_spec`` locates the module without
        # importing it, so a stray torch install can no longer inflate the lite path.
        has_numeric = any(
            importlib.util.find_spec(m) is not None for m in ("numpy", "cupy", "torch")
        )
        backend = "numpy" if has_numeric else "python"
    # lite always uses python/numpy regardless of GPU availability
    if mode == "lite":
        backend = "numpy" if backend in ("numpy", "cupy", "torch") else "python"
    # pro uses numpy (GPU not needed)
    elif mode == "pro":
        if backend == "torch" or backend == "cupy":
            backend = "numpy"
    # max uses best available (or forced backend)
    return DimensionProfile(mode=mode, backend=backend, **params)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Main config
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SylanneConfig:
    """Engine configuration options.

    Attributes:
        mode: Computation tier — "lite" (5 sessions), "pro" (25), "max" (50+).
        diagnostics: Include pipeline debug info in Surface output.
        assessor_enabled: Use LLM for semantic assessment. Disable for local-only mode.
        persistence_fsync: fsync after state writes (safer but slower).
        tick_drift_cap: Max personality drift per tick [0, 1].
        locale: Language for internal prompts ("zh" or "en").
        force_backend: Override auto-detected compute backend.
            None = auto-detect, "torch" = force GPU via PyTorch,
            "python" = force pure-Python (useful for testing/debugging).
        training_data_sink: Opt in to writing a local distillation corpus
            (numeric features + assessor affect) for offline student training.
            Default False — collects nothing. This is multi-user data; no raw
            text or PII is ever written and there is no network egress.
        training_data_path: Filename for the corpus under ``<data_dir>/telemetry``.
            Defaults to "distill_corpus.jsonl"; only the basename is used.
        training_data_salt: Local salt for the non-reversible session hash. If
            empty, a per-process random salt is used (cross-run grouping is then
            unstable). Keep it out of the dataset directory.
        pel_core_enabled: Opt in to the PEL-Core predictive-coding emotion core
            (v2.5). Default False — the legacy MLP ``_evolve_base`` runs and
            behaviour is byte-identical to today. When True, the engine's
            8-dim emotion core (lite tier) evolves via the PEL latent
            micro-circuit instead. Additive and snapshot-migration-safe.
        submit_window_seconds: How long a COMPLETED ``submit()`` entry stays
            joinable before it is pruned (default 10s). A duplicate submission
            for the same key inside this window joins the cached result instead
            of recomputing; after it, the same key recomputes. In-flight entries
            are never subject to this window — only completed ones age out.
        submit_max_entries: Cap on COMPLETED ``submit()`` entries kept for
            joining (default 1024); oldest-completed evicted first once
            exceeded. In-flight entries are never capped or evicted by this.
        tick_min_interval_seconds: Absolute per-session minimum interval between
            real ``tick()`` advances (default 45.0s). A ``tick()`` call within
            this interval of the session's last real tick returns the cached
            Surface without advancing state; ``force=True`` bypasses it. See
            ``SylanneEngine.tick`` for the rationale (coalescing several
            co-resident heartbeat loops down to ~one real tick per interval).
    """

    mode: Literal["lite", "pro", "max"] = "lite"
    diagnostics: bool = False
    assessor_enabled: bool = True
    persistence_fsync: bool = True
    tick_drift_cap: float = 0.05
    locale: str = "zh"
    force_backend: str | None = None
    training_data_sink: bool = False
    training_data_path: str | None = None
    training_data_salt: str = ""
    pel_core_enabled: bool = False
    submit_window_seconds: float = 10.0
    submit_max_entries: int = 1024
    tick_min_interval_seconds: float = 45.0

    def __post_init__(self) -> None:
        if self.mode not in ("lite", "pro", "max"):
            raise ValueError("mode must be 'lite', 'pro', or 'max'")
        if not (0.0 <= self.tick_drift_cap <= 1.0):
            raise ValueError("tick_drift_cap must be in [0.0, 1.0]")
        if self.locale not in ("zh", "en"):
            raise ValueError("locale must be 'zh' or 'en'")
        if self.force_backend is not None and self.force_backend not in (
            "torch",
            "cupy",
            "numpy",
            "python",
        ):
            raise ValueError("force_backend must be None, 'torch', 'cupy', 'numpy', or 'python'")
        if self.submit_window_seconds < 0:
            raise ValueError("submit_window_seconds must be >= 0")
        if self.submit_max_entries < 1:
            raise ValueError("submit_max_entries must be >= 1")
        if self.tick_min_interval_seconds < 0:
            raise ValueError("tick_min_interval_seconds must be >= 0")

    def profile(self) -> DimensionProfile:
        """Build the dimension profile for this config's mode."""
        return build_profile(self.mode, force_backend=self.force_backend)
