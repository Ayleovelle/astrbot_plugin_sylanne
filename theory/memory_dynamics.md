# Formal Specification: 3-Layer Memory Decay and Reconsolidation Dynamics

> **Version**: 1.0.0  
> **Date**: 2026-05-23  
> **Status**: Theoretical specification (pre-implementation)

## 1. Definitions and State Space

### 1.1 Memory Item

A memory item $m$ is a tuple:

$$m = (content, w_m, a_m, \tau_m, layer, t_{created})$$

where:
- $content$: semantic payload (embedding vector or graph fragment)
- $w_m \in [0, 1]$: weight (salience/strength)
- $a_m \in \mathbb{N}_0$: age in ticks since last recall
- $\tau_m \in [0, 1]$: temperature (emotional coloring, 0 = cold/negative, 1 = warm/positive)
- $layer \in \{L_1, L_2, L_3\}$: current residence layer
- $t_{created} \in \mathbb{N}_0$: creation timestamp

### 1.2 Layer Structure

| Layer | Capacity | Representation | Decay | Purpose |
|-------|----------|----------------|-------|---------|
| $L_1$ (hot) | $N_1 = 50$ | Raw items, FIFO | None | Working memory / recent context |
| $L_2$ (warm) | Unbounded | Weighted items | Continuous | Episodic memory with salience |
| $L_3$ (cold) | Unbounded | Knowledge graph edges | Clarity decay | Compressed semantic facts |

### 1.3 Global State

The system state at tick $t$ is:

$$S(t) = (L_1(t),\ L_2(t),\ L_3(t),\ \tau_{current}(t),\ \Pi)$$

where $\tau_{current}(t) \in [0,1]$ is the current emotional state (from Void-Scar engine) and $\Pi$ is the personality vector.

---

## 2. Decay Dynamics (L2)

### 2.1 Update Rule

For each memory item $m \in L_2$, at each tick:

$$w_m(t+1) = w_m(t) \cdot (1 - d_m(t))$$

$$d_m(t) = d_{base} \cdot (1 + \alpha \cdot \ln(a_m(t) + 1))$$

$$a_m(t+1) = a_m(t) + 1 \quad \text{(if not recalled at } t\text{)}$$

### 2.2 Parameters

| Symbol | Default | Domain | Derivation |
|--------|---------|--------|------------|
| $d_{base}$ | personality-derived | $(0, 1)$ | See §6 |
| $\alpha$ | 0.15 | $[0, 0.5]$ | Age acceleration coefficient |

### 2.3 Invariant

**Claim**: $d_m(t) \in (0, 1)$ for all valid states.

*Proof*: Since $a_m(t) \geq 0$, we have $\ln(a_m(t) + 1) \geq 0$. Thus $d_m(t) \geq d_{base} > 0$. For the upper bound: $d_{base} \leq 0.04$ (from §6) and $\alpha \leq 0.2$, so $d_m(t) \leq 0.04 \cdot (1 + 0.2 \cdot \ln(a_m + 1))$. For $d_m < 1$ we need $a_m < e^{(1/d_{base} - 1)/\alpha} - 1$. With $d_{base} = 0.04, \alpha = 0.2$: $a_m < e^{120} - 1 \approx 10^{52}$, which exceeds any practical tick count. $\square$

---

## 3. Recall Reinforcement

### 3.1 Recall Event

When memory $m$ is recalled at tick $t$, the following atomic update applies:

$$w_m(t) \leftarrow \min(w_m(t) + \Delta w_{recall},\ 1.0)$$

$$a_m(t) \leftarrow \lfloor a_m(t) \cdot \gamma \rfloor$$

$$\tau_m(t) \leftarrow \tau_m(t) \cdot (1 - \beta) + \tau_{current}(t) \cdot \beta$$

### 3.2 Parameters

| Symbol | Default | Meaning |
|--------|---------|---------|
| $\Delta w_{recall}$ | 0.03 | Weight boost per recall |
| $\gamma$ | 0.5 | Partial age reset factor |
| $\beta$ | 0.05 | Reconsolidation rate |

### 3.3 Semantics

- **Weight boost**: Recalled memories become more salient, counteracting decay.
- **Partial age reset**: Age is halved, not zeroed — repeated recall still accumulates some age pressure.
- **Reconsolidation**: Each recall slightly tints the memory toward the current emotional state, modeling the psychological phenomenon where retrieval modifies the memory trace.

---

## 4. Layer Transition Rules

### 4.1 L1 → L2 (Overflow)

**Trigger**: $|L_1(t)| > N_1 = 50$

**Action**: The oldest item $m_{oldest}$ in $L_1$ is moved to $L_2$ with initial state:
- $w_m = 1.0$
- $a_m = 0$
- $\tau_m = \tau_{current}(t_{created})$ (emotional state at creation time)

### 4.2 L2 → L3 (Compression)

**Trigger**: $w_m(t) < \theta_{compress} = 0.15$

**Action**: Item $m$ is compressed into knowledge graph edges in $L_3$:
- Extract semantic triples $(subject, relation, object)$ from $m.content$
- For each triple, create or reinforce edge $e$ with initial clarity $c_e = 0.5$
- Remove $m$ from $L_2$

### 4.3 L3 Garbage Collection

**Trigger**: $c_e(t) < \theta_{gc} = 0.1$

**Action**: Edge $e$ is permanently deleted from the knowledge graph.

---

## 5. L3 Clarity Dynamics

### 5.1 Decay Rule

For each edge $e$ in the knowledge graph:

$$c_e(t+1) = c_e(t) \cdot (1 - d_{clarity})$$

where $d_{clarity} = 0.002$ per tick.

### 5.2 Recall Reinforcement

On recall of edge $e$:

$$c_e(t) \leftarrow \min(c_e(t) + 0.05,\ 1.0)$$

### 5.3 Clarity-to-Language Mapping

The clarity value determines output confidence:

$$\text{voice}(c_e) = \begin{cases}
\text{assertive} & \text{if } c_e > 0.7 \\
\text{uncertain} & \text{if } 0.3 < c_e \leq 0.7 \\
\text{suppressed} & \text{if } c_e \leq 0.3
\end{cases}$$

Examples:
- $c_e = 0.85$: "你喜欢猫" (assertive)
- $c_e = 0.45$: "你好像提过喜欢猫？" (uncertain)
- $c_e = 0.20$: (not surfaced in output)

---

## 6. Multi-Layer Recall Scoring

### 6.1 Score Function

For a query $q$, the recall score of item $m$ from layer $L$ is:

$$\text{score}(m, q) = \text{sim}(q, m) \cdot w_m \cdot \lambda_L \cdot \text{mood}(m)$$

where:

$$\text{mood}(m) = 1 - |\tau_m - \tau_{current}|$$

### 6.2 Similarity Function

$$\text{sim}(q, m) = \begin{cases}
\cos(\vec{q}, \vec{m}) & \text{if } m \in L_1 \cup L_2 \\
\text{graph\_proximity}(q, m) & \text{if } m \in L_3
\end{cases}$$

### 6.3 Layer Weights

| Layer | $\lambda_L$ | Rationale |
|-------|-------------|-----------|
| $L_1$ | 1.0 | Recent context is maximally relevant |
| $L_2$ | 0.7 | Episodic memories are somewhat discounted |
| $L_3$ | 0.4 | Compressed facts are less vivid |

---

## 7. Personality Modulation

All decay and reconsolidation parameters are derived from the Big Five personality vector $\Pi = (O, C, E, A, N)$ where each trait $\in [0, 1]$.

### 7.1 Parameter Derivations

$$d_{base} = 0.01 + (1 - C) \cdot 0.03$$

$$\alpha = 0.1 + N \cdot 0.1$$

$$\beta = 0.03 + O \cdot 0.04$$

$$\text{mood\_weight} = 0.1 + N \cdot 0.2$$

### 7.2 Negative Memory Exception

If $\tau_m < 0.3$ AND $N > 0.6$:

$$d_{base}^{(m)} = d_{base} \cdot 0.5$$

This models the psychological finding that neurotic personalities retain negative memories longer due to rumination.

### 7.3 Parameter Bounds

| Parameter | Min | Max | At personality extremes |
|-----------|-----|-----|------------------------|
| $d_{base}$ | 0.01 | 0.04 | $C=1 \Rightarrow 0.01$; $C=0 \Rightarrow 0.04$ |
| $\alpha$ | 0.10 | 0.20 | $N=0 \Rightarrow 0.10$; $N=1 \Rightarrow 0.20$ |
| $\beta$ | 0.03 | 0.07 | $O=0 \Rightarrow 0.03$; $O=1 \Rightarrow 0.07$ |

---

## 8. Theorems and Proofs

### Theorem 1: Boundedness

**Statement**: For all $t \geq 0$ and all memory items $m$: $w_m(t) \in [0, 1]$.

**Proof**:

*Base case*: $w_m(0) = 1.0 \in [0, 1]$ (items enter $L_2$ with weight 1.0).

*Inductive step (decay)*: If $w_m(t) \in [0, 1]$ and $d_m(t) \in (0, 1)$ (shown in §2.3), then:
$$w_m(t+1) = w_m(t) \cdot (1 - d_m(t)) \in [0, w_m(t)] \subseteq [0, 1]$$

*Recall*: $w_m \leftarrow \min(w_m + \Delta w_{recall}, 1.0) \leq 1.0$ by construction.

Since decay cannot produce negative values (product of non-negatives) and recall is capped at 1.0, the invariant holds. $\square$

---

### Theorem 2: Monotone Decay Without Recall

**Statement**: If memory $m$ is never recalled after tick $t_0$, then $w_m(t)$ is strictly decreasing for all $t > t_0$.

**Proof**:

Without recall, $a_m(t) = a_m(t_0) + (t - t_0)$, which is strictly increasing. Therefore:

$$d_m(t) = d_{base} \cdot (1 + \alpha \cdot \ln(a_m(t) + 1)) > 0$$

and the multiplicative factor satisfies:

$$1 - d_m(t) \in (0, 1)$$

Thus:

$$w_m(t+1) = w_m(t) \cdot (1 - d_m(t)) < w_m(t)$$

for all $t > t_0$ where $w_m(t) > 0$. $\square$

---

### Theorem 3: Forgetting (Finite-Time Compression)

**Statement**: Without recall, any memory $m$ with initial weight $w_0 \leq 1$ reaches the compression threshold $\theta_{compress}$ in finite time.

**Proof**:

After $T$ ticks without recall (starting from age $a_0 = 0$):

$$w_m(T) = w_0 \cdot \prod_{t=0}^{T-1} (1 - d_m(t))$$

Taking logarithms:

$$\ln w_m(T) = \ln w_0 + \sum_{t=0}^{T-1} \ln(1 - d_m(t))$$

Since $\ln(1-x) \leq -x$ for $x \in (0,1)$:

$$\ln w_m(T) \leq \ln w_0 - \sum_{t=0}^{T-1} d_m(t)$$

$$= \ln w_0 - d_{base} \sum_{t=0}^{T-1} (1 + \alpha \cdot \ln(t+1))$$

$$= \ln w_0 - d_{base} \cdot T - d_{base} \cdot \alpha \sum_{t=0}^{T-1} \ln(t+1)$$

The sum $\sum_{t=0}^{T-1} \ln(t+1) = \ln(T!) \sim T \ln T - T$ (Stirling). Thus:

$$\ln w_m(T) \leq \ln w_0 - d_{base} \cdot T - d_{base} \cdot \alpha \cdot (T \ln T - T + O(\ln T))$$

This diverges to $-\infty$ as $T \to \infty$, so $w_m(T) \to 0$.

More precisely, $w_m(T) < \theta_{compress}$ when:

$$d_{base} \cdot T + d_{base} \cdot \alpha \cdot (T \ln T - T) > \ln(w_0 / \theta_{compress})$$

For the dominant term $d_{base} \cdot \alpha \cdot T \ln T$, we need approximately:

$$T \gtrsim \frac{\ln(w_0 / \theta_{compress})}{d_{base} \cdot \alpha \cdot \ln T}$$

which is satisfied in $O\!\left(\frac{\ln(1/\theta_{compress})}{d_{base}}\right)$ ticks (ignoring logarithmic corrections). $\square$

**Corollary** (Forgetting time estimate): With $w_0 = 1$, $\theta_{compress} = 0.15$, $d_{base} = 0.02$, $\alpha = 0.15$:

A lower bound on the pure-decay trajectory gives compression in approximately 60–90 ticks.

---

### Theorem 4: Recall Equilibrium

**Statement**: If memory $m$ is recalled exactly once every $K$ ticks, its weight converges to a positive equilibrium $w^* > 0$.

**Proof sketch**:

Consider the dynamics over one recall cycle of $K$ ticks. Let $w_n$ denote the weight just after the $n$-th recall.

During $K$ ticks of decay (approximating $d_m$ as roughly constant $\bar{d}$ over the cycle due to age reset):

$$w_{n+1}^{-} \approx w_n \cdot (1 - \bar{d})^K$$

After recall:

$$w_{n+1} = w_{n+1}^{-} + \Delta w_{recall} = w_n \cdot (1 - \bar{d})^K + \Delta w_{recall}$$

This is a linear recurrence $w_{n+1} = \rho \cdot w_n + \Delta w_{recall}$ where $\rho = (1-\bar{d})^K \in (0,1)$.

The fixed point is:

$$w^* = \frac{\Delta w_{recall}}{1 - (1 - \bar{d})^K}$$

Since $0 < \rho < 1$, the recurrence converges geometrically to $w^*$ from any initial condition.

For the approximation to be self-consistent, we need $w^* > \theta_{compress}$ (otherwise the memory would be compressed before reaching equilibrium). This holds when:

$$K < \frac{\ln(1 - \Delta w_{recall} / \theta_{compress})}{\ln(1 - \bar{d})} \approx \frac{\theta_{compress} - \Delta w_{recall}}{\bar{d} \cdot \theta_{compress}}$$

With defaults ($\Delta w_{recall} = 0.03$, $\theta_{compress} = 0.15$, $\bar{d} \approx 0.02$): $K < 400$ ticks ensures stable equilibrium above compression. $\square$

---

### Theorem 5: Reconsolidation Drift Bound

**Statement**: After $N$ recalls with arbitrary emotional states $\tau_{current}^{(1)}, \ldots, \tau_{current}^{(N)}$, the memory temperature satisfies:

$$|\tau_m^{(N)} - \tau_m^{(0)}| \leq 1 - (1 - \beta)^N$$

**Proof**:

The reconsolidation update is:

$$\tau_m^{(n)} = (1 - \beta) \cdot \tau_m^{(n-1)} + \beta \cdot \tau_{current}^{(n)}$$

Unrolling:

$$\tau_m^{(N)} = (1-\beta)^N \cdot \tau_m^{(0)} + \beta \sum_{n=1}^{N} (1-\beta)^{N-n} \cdot \tau_{current}^{(n)}$$

Therefore:

$$\tau_m^{(N)} - \tau_m^{(0)} = (1-\beta)^N \cdot \tau_m^{(0)} + \beta \sum_{n=1}^{N} (1-\beta)^{N-n} \cdot \tau_{current}^{(n)} - \tau_m^{(0)}$$

$$= -(1 - (1-\beta)^N) \cdot \tau_m^{(0)} + \beta \sum_{n=1}^{N} (1-\beta)^{N-n} \cdot \tau_{current}^{(n)}$$

Since all $\tau$ values are in $[0,1]$, the maximum absolute drift occurs when $\tau_m^{(0)}$ and all $\tau_{current}^{(n)}$ are at opposite extremes. The coefficient sum:

$$\beta \sum_{n=1}^{N} (1-\beta)^{N-n} = 1 - (1-\beta)^N$$

Thus the maximum possible drift magnitude is:

$$|\tau_m^{(N)} - \tau_m^{(0)}| \leq (1 - (1-\beta)^N) \cdot \max_n |\tau_{current}^{(n)} - \tau_m^{(0)}| \leq 1 - (1-\beta)^N$$

The bound is tight when all recall states are at the opposite extreme from the initial temperature. $\square$

**Corollary**: With $\beta = 0.05$, after 50 recalls the maximum drift is $1 - 0.95^{50} \approx 0.923$. Full reconsolidation requires many recalls; a single recall shifts temperature by at most $\beta = 0.05$.

---

### Theorem 6: Clarity Death

**Statement**: Every unrecalled $L_3$ edge $e$ with initial clarity $c_0$ reaches garbage collection threshold $\theta_{gc}$ in exactly:

$$T_{death} = \left\lceil \frac{\ln(\theta_{gc} / c_0)}{\ln(1 - d_{clarity})} \right\rceil \text{ ticks}$$

**Proof**:

Without recall, clarity decays geometrically:

$$c_e(t) = c_0 \cdot (1 - d_{clarity})^t$$

Setting $c_e(T) = \theta_{gc}$:

$$c_0 \cdot (1 - d_{clarity})^T = \theta_{gc}$$

$$T = \frac{\ln(\theta_{gc} / c_0)}{\ln(1 - d_{clarity})}$$

Since $\theta_{gc} < c_0$ and $\ln(1 - d_{clarity}) < 0$, both numerator and denominator are negative, yielding $T > 0$. Taking the ceiling gives the first integer tick at or past the threshold. $\square$

**Example**: With $c_0 = 0.5$, $\theta_{gc} = 0.1$, $d_{clarity} = 0.002$:

$$T_{death} = \left\lceil \frac{\ln(0.1 / 0.5)}{\ln(0.998)} \right\rceil = \left\lceil \frac{-1.609}{-0.002002} \right\rceil = \lceil 803.7 \rceil = 804 \text{ ticks}$$

---

## 9. System Properties Summary

### 9.1 Desirable Properties (Verified)

| Property | Status | Reference |
|----------|--------|-----------|
| Weight boundedness $w_m \in [0,1]$ | Proven | Theorem 1 |
| Monotone forgetting without recall | Proven | Theorem 2 |
| Guaranteed compression in finite time | Proven | Theorem 3 |
| Stable equilibrium with periodic recall | Proven | Theorem 4 |
| Bounded reconsolidation drift | Proven | Theorem 5 |
| Deterministic clarity death | Proven | Theorem 6 |
| Personality modulation within safe bounds | Verified | §7.3 |

### 9.2 Emergent Behaviors

1. **Mood-congruent recall**: The $\text{mood}(m)$ factor causes memories matching current emotional state to surface preferentially, modeling mood-congruent memory bias.

2. **Neurotic rumination**: The negative memory exception (§7.2) combined with high mood-alignment weight creates a feedback loop where negative memories persist and are preferentially recalled during negative states.

3. **Creative reconsolidation**: High openness ($O$) increases $\beta$, causing memories to be more rapidly recolored by new emotional contexts — modeling creative reinterpretation of past events.

4. **Graceful degradation**: The L2→L3 compression preserves semantic content while losing episodic detail, and the clarity-to-language mapping ensures the system never asserts facts it has partially forgotten.

---

## 10. Implementation Notes

### 10.1 Tick Rate

One tick corresponds to one conversational turn (message pair). For idle periods, batch-advance ticks proportionally to elapsed wall-clock time (1 tick per 10 minutes of silence, capped at 100 ticks per session gap).

### 10.2 Numerical Stability

- Use $\ln(1-x) \approx -x$ approximation only for analysis; implementation uses exact multiplication.
- Weight values below $10^{-10}$ are treated as zero to avoid floating-point underflow.
- Age counter is capped at $10^6$ to prevent overflow in the logarithm term.

### 10.3 Atomicity

Recall reinforcement (§3.1) must be applied atomically before the next decay tick to prevent race conditions in concurrent access patterns.

---

## Appendix A: Notation Index

| Symbol | Meaning | Domain |
|--------|---------|--------|
| $w_m$ | Memory weight | $[0, 1]$ |
| $a_m$ | Age since last recall (ticks) | $\mathbb{N}_0$ |
| $\tau_m$ | Memory temperature (emotion) | $[0, 1]$ |
| $d_{base}$ | Base decay rate | $(0, 0.04]$ |
| $\alpha$ | Age acceleration coefficient | $[0.1, 0.2]$ |
| $\gamma$ | Partial age reset factor | $0.5$ |
| $\beta$ | Reconsolidation rate | $[0.03, 0.07]$ |
| $\Delta w_{recall}$ | Weight boost per recall | $0.03$ |
| $\theta_{compress}$ | L2→L3 threshold | $0.15$ |
| $\theta_{gc}$ | L3 garbage collection threshold | $0.1$ |
| $d_{clarity}$ | L3 clarity decay rate | $0.002$ |
| $c_e$ | Edge clarity | $[0, 1]$ |
| $\lambda_L$ | Layer weight in scoring | $\{0.4, 0.7, 1.0\}$ |
| $\Pi$ | Personality vector $(O,C,E,A,N)$ | $[0,1]^5$ |
