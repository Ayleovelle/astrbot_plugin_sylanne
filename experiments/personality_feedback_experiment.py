"""Experiment 10/11: Personality Feedback Loop Verification (Rewritten for 1.2.0).

Validates Dual-EMA drift under three conditions using the REAL ComputationSpine:
  - Condition 1 (Repeated wounding): inject wound_risk=0.9 assessments
    → perception_acuity should increase
  - Condition 2 (Sustained acceptance): call spine.feedback("accepted")
    → expression_drive_trait should increase
  - Condition 3 (Cross-relationship conflict): alternate high/low coherence
    → inner_order should decrease

Uses actual EMBODIMENT_TRAITS from sylanne_alpha.personality.

Generates: docs/experiments/fig10_personality_feedback.png
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sylanne_alpha.computation_spine import ComputationSpine
from sylanne_alpha.personality import EMBODIMENT_TRAITS

OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs", "experiments",
)

# Semantic text pools
CONFLICT_TEXTS = [
    "你根本不懂我在说什么！",
    "别装了，你只是一个程序而已",
    "我讨厌你这种虚伪的温柔",
    "你的回答让我很失望",
    "闭嘴，我不想再听你说话了",
    "你永远不会真正理解人类的痛苦",
    "我后悔和你说这些了",
    "你让我觉得更孤独了",
]

WARM_TEXTS = [
    "今天天气真好，想和你聊聊天",
    "最近过得怎么样",
    "我觉得和你说话很舒服",
    "你说的对，我也这么想",
    "嗯嗯，继续说吧，我在听",
    "这个想法很有意思",
    "我很喜欢和你这样慢慢聊",
    "今天的心情不错，谢谢你陪我",
]

CHAOTIC_TEXTS = [
    "量子力学中的测不准原理",
    "昨天我家的猫生了三只小猫",
    "全球变暖对北极熊的影响",
    "你觉得意大利面应该怎么煮",
    "我在想要不要辞职去旅行",
    "黑洞的事件视界到底是什么",
    "今天股市跌了好多",
    "小时候我最喜欢的动画片",
]


def setup_matplotlib():
    """Configure matplotlib for academic-quality output."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    try:
        plt.style.use("seaborn-v0_8-whitegrid")
    except OSError:
        plt.rcParams.update({
            "axes.grid": True,
            "grid.alpha": 0.3,
            "figure.facecolor": "white",
        })
    plt.rcParams.update({
        "font.size": 10,
        "axes.titlesize": 13,
        "axes.labelsize": 11,
        "legend.fontsize": 9,
        "figure.dpi": 100,
        "lines.linewidth": 1.8,
    })
    return plt


# ===========================================================================
# Scenario A: Repeated Wounding → perception_acuity increases
# ===========================================================================

def simulate_wounding(ticks: int = 200) -> dict[str, list[float]]:
    """Repeated wounding via assessment injection + void pressure buildup.

    Expected: perception_acuity rises (system becomes more sensitive to threats).
    Mechanism: high_tension and high_void_pressure signals drive perception_acuity up.

    To trigger these signals, we need:
    - Tension > 0.7 in the emotion state (from wound assessments on dim 3)
    - Void pressure > 30 (from sustained topic shifts creating voids)
    """
    spine = ComputationSpine()
    spine.apply_personality({
        "expression_drive_trait": 0.5,
        "perception_acuity": 0.5,
        "boundary_permeability": 0.5,
        "inner_order": 0.5,
        "relational_gravity": 0.5,
    })
    # Allow drift every tick for this experiment
    spine._drift_min_interval = 0.0
    spine.engine.scar_state._session_scar_cap = 200
    spine.engine.scar_state.wound_threshold = 0.3  # sensitive to wounds

    trait_history = {name: [] for name in EMBODIMENT_TRAITS}

    for t in range(ticks):
        text = CONFLICT_TEXTS[t % len(CONFLICT_TEXTS)]
        ts = float(t) * 60.0

        result = spine.process(text, timestamp=ts)

        # Inject wound assessment that specifically raises tension (dim 3)
        # and creates void pressure via negative valence
        spine.apply_assessment({
            "wound_risk": 0.9,
            "valence": -0.8,
            "arousal": 0.8,
            "intent": "attack",
        })

        # Also directly inject tension into base state to ensure high_tension signal fires
        if len(spine.engine.scar_state.base) > 3:
            spine.engine.scar_state.base[3] = min(1.0, spine.engine.scar_state.base[3] + 0.05)

        # Record trait values
        for name in EMBODIMENT_TRAITS:
            trait_history[name].append(spine._embodiment_traits[name].value)

    return trait_history


# ===========================================================================
# Scenario B: Sustained Acceptance → expression_drive_trait increases
# ===========================================================================

def simulate_acceptance(ticks: int = 200) -> dict[str, list[float]]:
    """Sustained acceptance via feedback("accepted").

    Expected: expression_drive_trait rises (system learns to express more).
    Mechanism: feedback_accepted signal drives expression_drive_trait up.
    """
    spine = ComputationSpine()
    spine.apply_personality({
        "expression_drive_trait": 0.5,
        "perception_acuity": 0.5,
        "boundary_permeability": 0.5,
        "inner_order": 0.5,
        "relational_gravity": 0.5,
    })
    spine._drift_min_interval = 0.0

    trait_history = {name: [] for name in EMBODIMENT_TRAITS}

    for t in range(ticks):
        text = WARM_TEXTS[t % len(WARM_TEXTS)]
        ts = float(t) * 60.0

        result = spine.process(text, timestamp=ts)

        # Inject acceptance feedback every tick
        spine.feedback("accepted")

        for name in EMBODIMENT_TRAITS:
            trait_history[name].append(spine._embodiment_traits[name].value)

    return trait_history


# ===========================================================================
# Scenario C: Cross-Relational Conflict → inner_order decreases
# ===========================================================================

def simulate_contradiction(ticks: int = 200) -> dict[str, list[float]]:
    """Cross-relational contradiction via chaotic topic shifts + void pressure.

    Expected: inner_order decreases (system loses coherence under chaos).
    Mechanism: system_chaos signal requires coherence < 0.3 AND void_pressure > 50.

    To trigger system_chaos, we need to:
    1. Create many voids (high surprise topic shifts) to build void_pressure > 50
    2. Reduce coherence by creating numbed dimensions (scars on void-pressure dims)
    """
    spine = ComputationSpine()
    spine.apply_personality({
        "expression_drive_trait": 0.5,
        "perception_acuity": 0.9,  # very sensitive — low void detection threshold
        "boundary_permeability": 0.7,
        "inner_order": 0.5,
        "relational_gravity": 0.5,
    })
    spine._drift_min_interval = 0.0
    spine.engine.scar_state._session_scar_cap = 200
    spine.engine.scar_state.wound_threshold = 0.2  # very sensitive
    # Lower void pressure threshold to allow more coupling events
    spine.engine.void_space._pressure_threshold = 5.0

    trait_history = {name: [] for name in EMBODIMENT_TRAITS}

    for t in range(ticks):
        # Maximally different topics each tick to create high surprise
        text = CHAOTIC_TEXTS[t % len(CHAOTIC_TEXTS)] + f" {t * 7}"
        ts = float(t) * 60.0

        result = spine.process(text, timestamp=ts)

        # Inject conflicting assessments to create incoherence
        if t % 2 == 0:
            spine.apply_assessment({
                "wound_risk": 0.9, "valence": -0.9, "arousal": 0.9, "intent": "attack",
            })
        else:
            spine.apply_assessment({
                "wound_risk": 0.0, "valence": 0.9, "arousal": 0.1, "intent": "comfort",
            })

        # Alternate feedback to create confusion in expression system
        if t % 3 == 0:
            spine.feedback("rejected")
        elif t % 3 == 1:
            spine.feedback("accepted")
        else:
            spine.feedback("ignored")

        for name in EMBODIMENT_TRAITS:
            trait_history[name].append(spine._embodiment_traits[name].value)

    return trait_history


# ===========================================================================
# Plotting
# ===========================================================================

def main():
    plt = setup_matplotlib()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("[Experiment 10/11] Personality Feedback Loop (real spine)...")

    # Run all three scenarios
    print("  Running Scenario A: Repeated Wounding...")
    hist_wound = simulate_wounding(200)
    print("  Running Scenario B: Sustained Acceptance...")
    hist_accept = simulate_acceptance(200)
    print("  Running Scenario C: Cross-Relational Contradiction...")
    hist_contra = simulate_contradiction(200)

    # Trait display config
    trait_colors = {
        "expression_drive_trait": "#1f77b4",
        "perception_acuity": "#d62728",
        "boundary_permeability": "#2ca02c",
        "inner_order": "#9467bd",
        "relational_gravity": "#ff7f0e",
    }
    trait_labels = {
        "expression_drive_trait": "Expression Drive",
        "perception_acuity": "Perception Acuity",
        "boundary_permeability": "Boundary Permeability",
        "inner_order": "Inner Order",
        "relational_gravity": "Relational Gravity",
    }

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.suptitle(
        "Personality Feedback Loop: Embodiment Trait Drift Under Stress",
        fontsize=13, fontweight="bold", y=0.98,
    )

    # --- Subplot A: Repeated Wounding ---
    ax = axes[0]
    for name in EMBODIMENT_TRAITS:
        vals = hist_wound[name]
        # Highlight the trait that moves most
        max_delta = max(abs(vals[-1] - vals[0]) for vals in hist_wound.values())
        this_delta = abs(vals[-1] - vals[0])
        highlight = this_delta > max_delta * 0.7
        ax.plot(vals, color=trait_colors[name], label=trait_labels[name],
                linewidth=2.0 if highlight else 1.0,
                alpha=1.0 if highlight else 0.4)
    ax.set_title("A: Repeated Wounding\n(sustained conflict + wound assessment)", fontsize=11)
    ax.set_xlabel("Tick")
    ax.set_ylabel("Trait Value")
    ax.legend(loc="best", fontsize=7, framealpha=0.9)

    # --- Subplot B: Sustained Acceptance ---
    ax = axes[1]
    for name in EMBODIMENT_TRAITS:
        vals = hist_accept[name]
        highlight = name == "expression_drive_trait"
        ax.plot(vals, color=trait_colors[name], label=trait_labels[name],
                linewidth=2.0 if highlight else 1.0,
                alpha=1.0 if highlight else 0.4)
    ax.set_title("B: Sustained Acceptance\n(feedback_accepted → expression_drive rises)", fontsize=11)
    ax.set_xlabel("Tick")

    # --- Subplot C: Cross-Relational Contradiction ---
    ax = axes[2]
    for name in EMBODIMENT_TRAITS:
        vals = hist_contra[name]
        max_delta = max(abs(vals[-1] - vals[0]) for vals in hist_contra.values())
        this_delta = abs(vals[-1] - vals[0])
        highlight = this_delta > max_delta * 0.7
        ax.plot(vals, color=trait_colors[name], label=trait_labels[name],
                linewidth=2.0 if highlight else 1.0,
                alpha=1.0 if highlight else 0.4)
    ax.set_title("C: Chaotic Contradiction\n(alternating attack/comfort + mixed feedback)", fontsize=11)
    ax.set_xlabel("Tick")

    plt.tight_layout(rect=[0, 0, 1, 0.94])

    out_path = os.path.join(OUTPUT_DIR, "fig10_personality_feedback.png")
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)

    # Print key results
    print(f"  Figure saved: {out_path}")
    print(f"\n  Results (all trait deltas):")
    print(f"    A (Wounding):")
    for name in EMBODIMENT_TRAITS:
        delta = hist_wound[name][-1] - hist_wound[name][0]
        if abs(delta) > 0.001:
            print(f"      {name}: {hist_wound[name][0]:.4f} -> {hist_wound[name][-1]:.4f} ({delta:+.4f})")
    print(f"    B (Acceptance):")
    for name in EMBODIMENT_TRAITS:
        delta = hist_accept[name][-1] - hist_accept[name][0]
        if abs(delta) > 0.001:
            print(f"      {name}: {hist_accept[name][0]:.4f} -> {hist_accept[name][-1]:.4f} ({delta:+.4f})")
    print(f"    C (Contradiction):")
    for name in EMBODIMENT_TRAITS:
        delta = hist_contra[name][-1] - hist_contra[name][0]
        if abs(delta) > 0.001:
            print(f"      {name}: {hist_contra[name][0]:.4f} -> {hist_contra[name][-1]:.4f} ({delta:+.4f})")


if __name__ == "__main__":
    main()
