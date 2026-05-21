# Integration: Void-Scar Unified Computation Model

## Overview

Void Calculus and Scar Algebra are not independent theories — they form a coupled system where each theory's dynamics feed into the other. This document defines the formal integration.

## The Coupled System

$$\mathcal{C} = (S_{scar}, V_{void}, \Gamma, \Phi)$$

where:
- $S_{scar}$: Scar Algebra state space
- $V_{void}$: Void Calculus void set
- $\Gamma: V \to E$: void-to-scar coupling (void pressure generates wounding events)
- $\Phi: S \to V$: scar-to-void coupling (scarred dimensions lower void detection thresholds)

## Coupling $\Gamma$: Voids Wound the State

When void pressure exceeds threshold:

$$\pi_v > \theta_p \implies s \triangleright \Gamma(v)$$

where $\Gamma(v) = \pi_v \cdot \text{project}(\hat{B}_v, \mathbb{R}^n)$ maps the void's boundary centroid into the scar algebra's event space.

**Interpretation:** Unspoken things accumulate pressure that eventually wounds. The longer something is avoided, the more it hurts when (or even without being) addressed.

## Coupling $\Phi$: Scars Create Voids

When a dimension $d$ accumulates scars beyond a critical density:

$$|\{i : d_i = d\}| > \theta_{void} \implies \text{genesis}(v_{new})$$

with $B_{v_{new}}$ initialized from recent events on dimension $d$.

**Interpretation:** Repeated wounding in one area creates avoidance — the system learns to not go there, manifesting as a new void.

## Resonance as Emergent Property

Rather than implementing Kuramoto coupling as a separate mechanism, resonance emerges from the Void-Scar coupling:

- **Synchronization** = void pressure and scar sensitivity are aligned (the system "knows" what hurts and avoids it coherently)
- **Desynchronization** = void pressure builds on dimensions where scars have numbed sensitivity (the system can't feel what it's avoiding)

The global coherence measure:

$$r = 1 - \frac{\sum_v \pi_v \cdot \mathbb{1}[M_{d_v} < 0.5]}{\sum_v \pi_v + \epsilon}$$

where $M_{d_v}$ is the scar modifier on the void's primary dimension. When $r \to 1$, the system is coherent (voids and scars are aligned). When $r \to 0$, the system is dissociated (pressure builds in numbed areas — a computational analogue of dissociation).

## Computation Pipeline (Six-Layer Architecture)

```
Input → [L1] HDC Perception → [L2] Predictive Coding Gate
                                         ↓
                              ┌─── [L3] Void-Scar Engine ───┐
                              │                              │
                              │   Void Calculus:             │
                              │   - detect avoidance         │
                              │   - update voids             │
                              │   - compute pressure         │
                              │         ↕ Γ,Φ               │
                              │   Scar Algebra:              │
                              │   - modulate input           │
                              │   - evolve state             │
                              │   - form/heal scars          │
                              │                              │
                              └──────────────────────────────┘
                                         ↓
                              [L4] Tiny Attention (decision fusion)
                                         ↓
                              [L5] Autopoiesis (boundary check)
                                         ↓
                              [L6] Phase Transition (expression)
```

The original six-layer stack is preserved, but with redefined responsibilities:

| Layer | Original Role | New Role |
|-------|--------------|----------|
| L1 HDC | Perception encoding | Unchanged |
| L2 Predictive Coding | Surprise routing | Unchanged |
| L3 SSM + TDA | Linear state + hole detection | **Void-Scar Engine** (irreversible state + first-class absence) |
| L4 Tiny Attention | Cross-layer fusion | **Multi-source decision fusion** (narrowed scope) |
| L5 Autopoiesis | Identity boundary | Unchanged |
| L6 Phase Transition | Expression trigger | Unchanged |

## Layer 4: Heterogeneous Graph Transformer (HGT) — Decision Fusion

### Why vanilla attention is insufficient

The Void-Scar coupling ($\Gamma$, $\Phi$) handles information flow *within* the engine (between void and scar subsystems). But the **expression decision** requires combining signals from *all* layers simultaneously:

- Scar state (8-dim emotion observation)
- Void pressure distribution (which voids are critical)
- Autopoiesis boundary integrity (is it safe to express?)
- Surprise history (is this a volatile moment?)
- Personality vector (how expressive is this character?)
- Coherence $r$ (is the system internally consistent?)

These signals are **heterogeneous** — they have different types, different semantics, and different interaction patterns. Standard attention treats all token pairs identically via a single dot-product compatibility function. But "scar influencing expression" and "void influencing boundary" are fundamentally different relationships that should use different transformations.

### Architecture: Typed Transformer

We adopt the Heterogeneous Graph Transformer (HGT, Hu et al. 2020) pattern within the standard transformer framework.

**Type system.** Each token has a type $\tau(i) \in \mathcal{T}$:

$$\mathcal{T} = \{\text{scar, void, boundary, personality, surprise, expression, context}\}$$

**Type-specific projections.** Instead of shared $W_Q, W_K, W_V$, each type gets its own:

$$Q_i = W_Q^{\tau(i)} \cdot z_i, \quad K_j = W_K^{\tau(j)} \cdot z_j, \quad V_j = W_V^{\tau(j)} \cdot z_j$$

**Attention with personality-derived type prior:**

$$a_{ij} = \frac{Q_i \cdot K_j^\top}{\sqrt{d_k}} + \mu^{\tau(i), \tau(j)}$$

$$\text{Attn}(i) = \text{softmax}_j(a_{ij}) \cdot V_j$$

where $\mu \in \mathbb{R}^{|\mathcal{T}| \times |\mathcal{T}|}$ is the **personality-derived attention prior matrix** — a learned bias that determines how strongly each type pair attends to each other, conditioned on the current personality vector.

### Personality-Derived Prior $\mu$

The prior matrix is generated from the personality vector each tick:

$$\mu^{(\tau_s, \tau_t)} = \sum_{p \in \text{personality}} w_p^{(\tau_s, \tau_t)} \cdot \text{personality}[p]$$

Concrete mappings:

| Source → Target | Personality Driver | Interpretation |
|----------------|-------------------|----------------|
| scar → expression | extraversion | Extraverts let wounds drive speech |
| void → boundary | neuroticism | Anxious types let absence trigger vigilance |
| surprise → scar | neuroticism | Anxious types are more easily wounded by surprise |
| personality → expression | extraversion | Extraverts' personality directly drives expression |
| context → void | conscientiousness | Conscientious types track context-void relationships |
| boundary → expression | agreeableness | Agreeable types let boundary state gate expression |
| void → expression | openness | Open types let the unsaid drive speech |

The $w_p^{(\tau_s, \tau_t)}$ coefficients are fixed (hand-designed from the semantic meaning of each type pair). Only the personality values change over time (via drift), making $\mu$ a living, evolving attention bias.

### Why this is still a transformer

The architecture preserves all transformer properties:

- **Q/K/V projections** ✓ (type-specific, but still linear projections)
- **Scaled dot-product attention** ✓ (with additive bias)
- **Softmax normalization** ✓
- **Multi-head** ✓ (2 heads, each with independent type projections)
- **Residual connection** ✓
- **Single forward pass** ✓ (no iterative inference)

The only additions are: (1) type-specific weight matrices, (2) personality-derived bias. Both are standard in the HGT literature and do not change the computational pattern.

### Parameters

| Component | Count | Size |
|-----------|-------|------|
| $W_Q^{\tau}$ (7 types × 32×32) | 7 | 7168 floats |
| $W_K^{\tau}$ (7 types × 32×32) | 7 | 7168 floats |
| $W_V^{\tau}$ (7 types × 32×32) | 7 | 7168 floats |
| $W_{proj}$ (32 → 4) | 1 | 128 floats |
| $w_p$ coefficients (7×7×5 personality dims) | 1 | 245 floats |
| **Total** | | **~21.9K floats = 87.6 KB** |

Negligible in the 1 GB budget. 7× more parameters than vanilla attention but still a micro-network.

### Complexity

$$O(T^2 \cdot d_k) = O(32^2 \cdot 32) = 32768 \text{ FLOPs} \approx 0.5 \text{ ms}$$

Same as vanilla attention — the type-specific projections don't change the attention computation complexity, only the projection step (which is O(T × d) and dominated by the O(T² × d) attention).

**Optional sparsity:** Type pairs with $\mu < -2.0$ can be masked (attention score forced to $-\infty$), reducing effective T² to only relevant type pairs. With 7 types and ~15 relevant pairs out of 49, this gives ~3× speedup on the attention matrix computation.

### Token Composition (unchanged)

```
Tokens = [
    scar_obs[0..7],          # 8 tokens, type=scar
    void_summary[0..3],      # 4 tokens, type=void
    coherence,               # 1 token,  type=boundary
    boundary_integrity,      # 1 token,  type=boundary
    surprise_recent[0..2],   # 3 tokens, type=surprise
    personality[0..4],       # 5 tokens, type=personality
    expression_state[0..1],  # 2 tokens, type=expression
    context[0..5],           # 6 tokens, type=context
    padding[0..1],           # 2 tokens, type=context (masked)
]
```

### Output

The attention output is projected to a **decision vector** $\mathbf{d} \in \mathbb{R}^4$:

$$\mathbf{d} = W_{proj} \cdot \text{mean}(\text{Attn}(\mathbf{Z}))$$

where:
- $d_0$: expression drive modifier ($\in [-0.5, 0.5]$, added to Void-Scar drive)
- $d_1$: boundary sensitivity modifier (fed to autopoiesis)
- $d_2$: urgency signal (modulates phase transition threshold)
- $d_3$: suppress signal ($> 0.5$ vetoes expression regardless of pressure)

This gives the HGT layer a **typed gating** role: it can boost, attenuate, or veto the expression decision based on type-aware multi-source context, with personality determining which signal relationships matter most.

## Interface Between Layers

**L2 → L3 (Gate → Void-Scar Engine):**
- HDC vector $\mathbf{h}_t$
- Surprise value $s_t$
- Route decision (fast/normal/full)

**L3 → L4 (Void-Scar Engine → Tiny Attention):**
- Scar observation (8 floats)
- Top-4 void summaries (4 × 4 floats)
- Coherence $r$ (1 float)

**L4 → L5 (Tiny Attention → Autopoiesis):**
- Boundary sensitivity modifier $d_1$
- Scar base state $\mathbf{x}_t$ (passed through)

**L4 → L6 (Tiny Attention → Phase Transition):**
- Modified expression drive: $\text{drive}_{final} = \text{drive}_{VS} + d_0$
- Urgency modifier $d_2$
- Suppress signal $d_3$

**L5 → L6 (Autopoiesis → Phase Transition):**
- Boundary integrity (sovereignty guard input)
- Phase transition flag (if boundary was breached)

## Fast Path Behavior

On fast path (low surprise):
- L3 Void-Scar: Scar base evolution only (no formation check), void age increment only
- L4 Tiny Attention: **skip** (use cached decision vector from last full computation)
- L5 Autopoiesis: self-repair only
- L6 Phase Transition: accumulate with cached drive

On normal path:
- L3 Void-Scar: Full scar step + void contraction/deepening, no coupling
- L4 Tiny Attention: **run** (fresh decision)
- L5 Autopoiesis: self-repair
- L6 Phase Transition: accumulate with fresh drive

On full path (high surprise):
- L3 Void-Scar: Full step + coupling ($\Gamma$, $\Phi$) active
- L4 Tiny Attention: **run** with full token set
- L5 Autopoiesis: perturb + self-repair
- L6 Phase Transition: full evaluation with sovereignty guard

## Performance Budget (Updated)

| Layer | Fast Path | Normal Path | Full Path |
|-------|-----------|-------------|-----------|
| L1 HDC | 0.1 ms | 0.1 ms | 0.1 ms |
| L2 Gate | 0.01 ms | 0.01 ms | 0.01 ms |
| L3 Void-Scar | 0.05 ms | 2 ms | 5 ms |
| L4 Attention | skip (0) | 0.5 ms | 0.5 ms |
| L5 Autopoiesis | 0.01 ms | 0.01 ms | 0.1 ms |
| L6 Phase Trans | 0.001 ms | 0.001 ms | 0.001 ms |
| **Total** | **~0.17 ms** | **~2.6 ms** | **~5.7 ms** |

All within the 10 ms budget. Fast path is even faster than before (Void-Scar's fast path is cheaper than SSM's full step because it skips scar formation and void detection).

## Spatiotemporal Graph (L3 Internal Structure)

### Motivation

The Void-Scar Engine processes events sequentially, but relational dynamics have structure across multiple time scales and semantic regions. A spatiotemporal graph unifies Void and Scar into a single topological object:

- **Void** = a hole in the graph (disconnected region, missing edges)
- **Scar** = a severed edge (connection that existed but was broken)
- **Temporal patterns** = motifs in the graph (recurring subgraph structures)
- **Causal chains** = directed paths (event A → scar B → void C deepening)

### Graph Definition

$$\mathcal{G}_t = (N_t, E_t, \tau_N, \tau_E)$$

where:
- $N_t$: node set (events, scars, voids, ghosts)
- $E_t$: edge set (typed connections)
- $\tau_N: N \to \{\text{event, scar, void, ghost}\}$: node type function
- $\tau_E: E \to \{\text{temporal, causal, semantic, boundary}\}$: edge type function

**Node types:**

| Type | Created when | Carries |
|------|-------------|---------|
| event | Each message | HDC vector, timestamp, surprise |
| scar | Wounding occurs | dimension, stage, modifier |
| void | Avoidance detected | boundary set, depth, pressure |
| ghost | Void dies | depth, age_at_death |

**Edge types:**

| Type | Connects | Meaning |
|------|----------|---------|
| temporal | event → event | Time-adjacent (within session) |
| causal | event → scar, void → scar | "This caused that" |
| semantic | event ↔ event | HDC similarity > $\theta_{sem}$ |
| boundary | void ↔ event | Event is on void's boundary |

### Anti-Oversmoothing: Teleportation Diffusion

Message passing on the spatiotemporal graph uses **Personalized PageRank (PPR) diffusion** to prevent local oversmoothing:

$$\mathbf{h}_i^{(l+1)} = (1 - \alpha) \cdot \text{Aggregate}\left(\left\{\mathbf{h}_j^{(l)} : j \in \mathcal{N}(i)\right\}\right) + \alpha \cdot \mathbf{h}_i^{(0)}$$

where:
- $\mathbf{h}_i^{(0)}$ is the original node feature (HDC encoding for events, scar/void state for others)
- $\alpha \in (0, 1)$ is the teleportation rate — probability of "jumping back" to the original representation
- $\text{Aggregate}$ is type-aware: different edge types use different aggregation weights

**Why this prevents oversmoothing:** At each propagation step, $\alpha$ fraction of the representation is the *original* node identity. Even after $L$ rounds:

$$\mathbf{h}_i^{(L)} = \alpha \sum_{l=0}^{L-1} (1-\alpha)^l \cdot \text{Prop}^l(\mathbf{h}_i^{(0)}) + (1-\alpha)^L \cdot \text{Prop}^L(\mathbf{h}_i^{(0)})$$

The geometric decay ensures that local identity is always preserved with weight $\geq \alpha$, regardless of propagation depth.

**Personality-driven $\alpha$:**

$$\alpha = 0.2 + 0.4 \cdot \text{neuroticism}$$

- High neuroticism ($\alpha \to 0.6$): each event retains strong individual identity, resists contextual blending — the system "remembers every slight distinctly"
- Low neuroticism ($\alpha \to 0.2$): events blend more into context, the system has a "smoother" memory — less reactive to individual events

### Anti-Oversmoothing: Intra-Type Mask (HGT Layer)

In the HGT (Layer 4), same-type tokens are **blocked from attending to each other**:

$$\text{mask}(i, j) = \begin{cases} -\infty & \text{if } \tau(i) = \tau(j) \wedge i \neq j \\ 0 & \text{otherwise} \end{cases}$$

**Rationale:**
- Scar-to-scar relationships are already computed inside the Scar Algebra (modifier multiplication, dimensional coupling)
- Void-to-void relationships are already computed inside the Void Calculus (merge/split operations)
- The HGT's job is **cross-type fusion only** — how scars relate to voids, how voids relate to expression, how personality modulates boundary

This eliminates intra-type smoothing by construction. The 8 scar tokens remain maximally distinct (each represents a unique dimension), and the 4 void tokens remain maximally distinct (each represents a unique absence).

**Effective attention matrix structure:**

```
         scar  void  bnd  pers  surp  expr  ctx
scar   [  ×     ✓     ✓    ✓     ✓     ✓    ✓  ]
void   [  ✓     ×     ✓    ✓     ✓     ✓    ✓  ]
bnd    [  ✓     ✓     ×    ✓     ✓     ✓    ✓  ]
pers   [  ✓     ✓     ✓    ×     ✓     ✓    ✓  ]
surp   [  ✓     ✓     ✓    ✓     ×     ✓    ✓  ]
expr   [  ✓     ✓     ✓    ✓     ✓     ×    ✓  ]
ctx    [  ✓     ✓     ✓    ✓     ✓     ✓    ×  ]
```

(× = masked, ✓ = allowed)

This reduces effective attention pairs from $32^2 = 1024$ to approximately $1024 - (8^2 + 4^2 + 2^2 + 3^2 + 5^2 + 2^2 + 6^2) = 1024 - 158 = 866$, a 15% reduction in compute with a major gain in representation quality.

### Graph Pruning Strategy

The spatiotemporal graph grows with each event. Pruning maintains bounded size:

**Node budget:** $|N_t| \leq 200$ (configurable from personality: conscientiousness scales this)

**Pruning priority** (lowest priority removed first):

1. Event nodes with no causal edges and age > 100 ticks (routine events that caused nothing)
2. Ghost nodes with depth < 0.1 (insignificant resolved voids)
3. Event nodes with low semantic connectivity (isolated points, not part of any pattern)
4. Oldest temporal edges (keep only last 50 temporal connections)

**Never pruned:**
- Active void nodes (alive voids are always relevant)
- Active scar nodes (scars are permanent by axiom)
- Event nodes that are causal parents of active scars/voids (provenance)

### Integration with Void-Scar Engine

The spatiotemporal graph is **internal to L3**, not a separate layer:

```
L3 Void-Scar Engine:
├── Scar Algebra (state evolution)
├── Void Calculus (absence tracking)
├── Coupling (Γ, Φ)
└── Spatiotemporal Graph (structural memory)
    ├── Node/edge storage
    ├── PPR diffusion (pattern detection)
    └── Motif detection (periodic patterns)
```

**How the graph feeds back into Void-Scar:**
- Motif detection → if a temporal pattern repeats 3+ times, lower void detection threshold for that pattern (the system "expects" avoidance here)
- Causal chain length → long causal chains (event → scar → void → deeper scar) increase coherence penalty (the system is in a destructive spiral)
- Semantic clustering → dense clusters with no inter-cluster edges suggest potential void genesis between clusters

### Performance Impact

| Operation | Cost | When |
|-----------|------|------|
| Add node + edges | O(degree) ≈ O(5) | Every event |
| PPR diffusion (2 rounds) | O(|E| × d) ≈ O(500 × 32) | Normal/full path only |
| Motif detection (cached) | O(|N|²) ≈ O(40000) | Every 10 ticks, cached |
| Pruning | O(|N| log |N|) | When budget exceeded |

**Updated performance budget:**

| Layer | Fast Path | Normal Path | Full Path |
|-------|-----------|-------------|-----------|
| L1 HDC | 0.1 ms | 0.1 ms | 0.1 ms |
| L2 Gate | 0.01 ms | 0.01 ms | 0.01 ms |
| L3 Void-Scar + Graph | 0.05 ms | 2.5 ms | 6 ms |
| L4 HGT | skip (0) | 0.4 ms | 0.4 ms |
| L5 Autopoiesis | 0.01 ms | 0.01 ms | 0.1 ms |
| L6 Phase Trans | 0.001 ms | 0.001 ms | 0.001 ms |
| **Total** | **~0.17 ms** | **~3.0 ms** | **~6.6 ms** |

Still within the 10 ms budget. The graph adds ~0.5 ms on normal path and ~1 ms on full path.

## Theoretical Significance

This integration demonstrates that:

1. Irreversible state dynamics (Scar) and first-class absence (Void) are not independent phenomena but coupled aspects of relational computation
2. "Resonance" (coherence between what hurts and what's avoided) emerges from the coupling without requiring a separate synchronization mechanism
3. Dissociation (numbed areas accumulating unprocessed pressure) is a natural failure mode with a precise mathematical characterization
4. The HGT serves as a **typed non-linear decision gate** with intra-type masking that prevents oversmoothing by construction
5. The spatiotemporal graph unifies Void and Scar into a single topological object where voids are holes and scars are severed edges
6. Teleportation diffusion ($\alpha$ from personality) preserves node identity across propagation rounds, solving local oversmoothing while allowing cross-event pattern detection
7. The architecture cleanly separates concerns: Void-Scar handles *what the system feels*, HGT handles *whether to act on it*, Autopoiesis handles *whether it's safe*, Phase Transition handles *how*
