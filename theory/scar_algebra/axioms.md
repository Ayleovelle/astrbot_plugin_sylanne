# Scar Algebra — Formal Axiom System

## Definition 1: Scarred State Space

A **Scarred State Space** is a tuple $(S, E, \triangleright, \Sigma)$ where:

- $S = \mathbb{R}^n \times \Sigma^*$ is the state space (base vector × scar sequence)
- $E = \mathbb{R}^n$ is the event space
- $\triangleright: S \times E \to S$ is the state transition operator
- $\Sigma$ is the scar alphabet (set of possible scar types)

A state $s = (\mathbf{x}, \sigma)$ consists of:
- $\mathbf{x} \in \mathbb{R}^n$: the base state vector (observable affect)
- $\sigma = (\sigma_1, \sigma_2, \ldots, \sigma_k) \in \Sigma^*$: the ordered scar sequence (irreversible history)

## Definition 2: Scar

A **scar** $\sigma_i \in \Sigma$ is a tuple $(d_i, \tau_i, \phi_i, m_i)$ where:

- $d_i \in \{1, \ldots, n\}$: the affected dimension
- $\tau_i \in \mathbb{R}_{\geq 0}$: creation timestamp
- $\phi_i \in \{raw, closing, scarred, faded\}$: healing stage (totally ordered: $raw < closing < scarred < faded$)
- $m_i: \mathbb{R} \to \mathbb{R}$: the modifier function, dependent on $\phi_i$

## Definition 3: Modifier Functions

For each healing stage, the modifier function is:

$$m_i(x) = \alpha(\phi_i) \cdot x$$

where:
$$\alpha(\phi) = \begin{cases} 2.0 & \phi = raw \\ 1.5 & \phi = closing \\ 1.0 & \phi = scarred \\ 0.7 & \phi = faded \end{cases}$$

For multiple scars on the same dimension $d$, modifiers compose multiplicatively:

$$M_d(\mathbf{e}) = e_d \cdot \prod_{i: d_i = d} \alpha(\phi_i)$$

## Definition 4: State Transition (The $\triangleright$ Operator)

Given state $s = (\mathbf{x}, \sigma)$ and event $\mathbf{e} \in E$:

$$s \triangleright \mathbf{e} = (\mathbf{x}', \sigma')$$

where:

**Step 1 — Scar-modulated input:**
$$\tilde{e}_d = M_d(\mathbf{e}) = e_d \cdot \prod_{i: d_i = d} \alpha(\phi_i) \quad \forall d \in \{1,\ldots,n\}$$

**Step 2 — Base state evolution:**
$$\mathbf{x}' = g(\mathbf{x}, \tilde{\mathbf{e}})$$

where $g$ is a bounded nonlinear map (e.g., $\tanh(\mathbf{A}\mathbf{x} + \mathbf{B}\tilde{\mathbf{e}})$).

**Step 3 — Scar formation (conditional):**
$$\sigma' = \begin{cases} \sigma \cdot (d^*, t, raw, m_{raw}) & \text{if } \exists d^*: |\tilde{e}_{d^*}| > \theta_w \\ \sigma & \text{otherwise} \end{cases}$$

where $\theta_w$ is the wounding threshold and $\cdot$ denotes sequence concatenation.

**Step 4 — Scar healing (time-driven):**
$$\phi_i \to \text{next}(\phi_i) \quad \text{if } t - \tau_i > T(\phi_i)$$

where $T(raw) < T(closing) < T(scarred)$ and $T(faded) = \infty$ (faded is terminal).

## Axiom 1: Irreversibility

$$\forall s \in S, \forall \mathbf{e} \in E: \nexists \mathbf{e}^{-1} \text{ s.t. } (s \triangleright \mathbf{e}) \triangleright \mathbf{e}^{-1} = s$$

**Proof sketch:** Once $|\tilde{e}_{d^*}| > \theta_w$, a scar is appended to $\sigma$. Since $\sigma$ is append-only and scars have no deletion operation, no subsequent event can restore the previous scar sequence. $\square$

## Axiom 2: Operator Self-Modification

The effective operator $\triangleright_t$ at time $t$ depends on all prior applications:

$$\triangleright_t \neq \triangleright_0 \quad \text{whenever } |\sigma_t| > 0$$

Formally: let $F_\sigma: E \to E$ be the scar-modulation map $F_\sigma(\mathbf{e})_d = M_d(\mathbf{e})$. Then:

$$s \triangleright \mathbf{e} \equiv (\mathbf{x}, \sigma) \triangleright \mathbf{e} = g(\mathbf{x}, F_\sigma(\mathbf{e})) \oplus \text{NewScars}(\tilde{\mathbf{e}})$$

The map $F_\sigma$ changes with each wounding event, therefore $\triangleright$ is not a fixed operator but a family $\{\triangleright_\sigma\}_{\sigma \in \Sigma^*}$ indexed by scar history.

## Axiom 3: Monotonic Scar Accumulation

$$|s \triangleright \mathbf{e}|_\Sigma \geq |s|_\Sigma$$

where $|s|_\Sigma = |\sigma|$ denotes the scar count. Scars can only be added, never removed.

## Axiom 4: Bounded Base State

$$\forall s \in S, \forall \mathbf{e} \in E: \|\mathbf{x}'\|_\infty \leq 1$$

The base state remains bounded regardless of scar accumulation or input magnitude. Scars modify sensitivity, not the state bounds.

## Axiom 5: Healing Monotonicity

$$\phi_i(t_1) \leq \phi_i(t_2) \quad \forall t_1 < t_2$$

Healing stages only advance forward. A faded scar cannot become raw again.

## Axiom 6: Dimensional Saturation

$$\lim_{k \to \infty} \prod_{j=1}^{k} \alpha(faded) = 0$$

As scars accumulate on a single dimension, the effective sensitivity approaches zero (complete numbing). Specifically, $k$ faded scars on dimension $d$ yield modifier $0.7^k \to 0$.

## Key Properties (to be proven in theorems.md)

1. **Expressiveness separation**: There exist input sequences whose state trajectories under Scar Algebra cannot be reproduced by any fixed-operator system with finite state.
2. **Convergence**: Under bounded input, the system converges to a "scarred equilibrium" where base state stabilizes but scar structure continues to evolve.
3. **Phase transition**: There exists a critical scar density beyond which the system's qualitative behavior changes discontinuously.
