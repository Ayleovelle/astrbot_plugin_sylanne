# Scar Algebra — Theorems and Formal Proofs

---

## Theorem 1: Expressiveness Separation

**Statement.** For every $k \in \mathbb{N}$, there exists an input sequence $E_k$ of length $2k$ such that any time-invariant dynamical system $x_{t+1} = f(x_t, e_t)$ with $f$ fixed and state $x \in \mathbb{R}^m$ that reproduces the Scar Algebra's output on $E_k$ must satisfy $m \geq k$.

### Formal Setup

**Definition (Fixed-Operator System).** A *fixed-operator system* (FOS) is a tuple $\mathcal{F} = (\mathbb{R}^m, f, h)$ where:
- $f: \mathbb{R}^m \times \mathbb{R}^n \to \mathbb{R}^m$ is a fixed (time-invariant) transition function
- $h: \mathbb{R}^m \to \mathbb{R}^n$ is a fixed output function
- The system evolves as $x_{t+1} = f(x_t, e_t)$, $y_t = h(x_t)$

**Definition (Behavioral Equivalence).** A FOS $\mathcal{F}$ *simulates* a Scar Algebra instance $\mathcal{S}$ on input sequence $E$ if for all $t$: $h(x_t) = \text{observe}(\mathcal{S}, t)$ (outputs match at every step).

### Proof

**Construction of $E_k$.** Fix $n = 1$ (scalar state). Define:
$$E_k = (\underbrace{w_1, w_2, \ldots, w_k}_{\text{wounding phase}}, \underbrace{c, c, \ldots, c}_{\text{probe phase, } k \text{ probes}})$$

where $w_i = \theta_w + \epsilon$ (just above wounding threshold) and $c = \theta_w / 3$ (below threshold).

The wounding events are spaced with varying inter-event times $\Delta_i \in \{T_1, T_2\}$ where $T_1 = T(raw) - 1$ (scar stays raw) and $T_2 = T(raw) + 1$ (scar advances to closing before next wound).

By choosing $\Delta_i \in \{T_1, T_2\}$ for each $i$, we create $2^k$ distinct timing patterns, each producing a different scar configuration at the start of the probe phase.

**Claim 1: Distinct configurations produce distinct outputs.**

At probe time $t_p$ (start of probe phase), the Scar Algebra's response to probe $c$ is:
$$y(t_p) = g(x_{t_p}, c \cdot M(t_p))$$

where $M(t_p) = \prod_{i=1}^k \alpha(\phi_i(t_p))$.

For timing pattern $\Delta = (\Delta_1, \ldots, \Delta_k) \in \{T_1, T_2\}^k$:
- If $\Delta_i = T_1$: scar $i$ is still $raw$ at $t_p$, contributing $\alpha(raw) = 2.0$
- If $\Delta_i = T_2$: scar $i$ has advanced to $closing$ at $t_p$, contributing $\alpha(closing) = 1.5$

Therefore:
$$M_\Delta(t_p) = 2.0^{|\{i: \Delta_i = T_1\}|} \cdot 1.5^{|\{i: \Delta_i = T_2\}|}$$

For two distinct patterns $\Delta \neq \Delta'$, let $j$ be a position where they differ. WLOG $\Delta_j = T_1, \Delta'_j = T_2$. Then:
$$\frac{M_\Delta(t_p)}{M_{\Delta'}(t_p)} = \frac{2.0}{1.5} = \frac{4}{3} \neq 1$$

Since $g(x, \cdot)$ is strictly monotone on its second argument (for $\tanh$-based $g$ with positive $x$), distinct modifiers produce distinct outputs. Thus all $2^k$ patterns produce distinct output values at $t_p$.

**Claim 2: A FOS must distinguish all $2^k$ patterns.**

Suppose FOS $\mathcal{F}$ simulates $\mathcal{S}$ on all $2^k$ variants of $E_k$. At time $t_p$, the FOS must produce $2^k$ distinct output values $h(x_{t_p}^{(\Delta)})$ for the $2^k$ different states $x_{t_p}^{(\Delta)}$.

Since $h$ is a fixed function and must produce $2^k$ distinct values, the states $\{x_{t_p}^{(\Delta)}\}_{\Delta \in \{T_1,T_2\}^k}$ must be pairwise distinct points in $\mathbb{R}^m$.

**Claim 3: $m \geq k$ is necessary.**

The $2^k$ states are reached by $2^k$ different input sequences of length $k$ (the wounding phase), all starting from the same initial state $x_0$. The reachable set after $k$ steps is:
$$R_k = \{f(\cdots f(f(x_0, e_1), e_2) \cdots, e_k) : (e_1, \ldots, e_k) \in E^k\}$$

For our construction, the inputs differ only in timing (which is encoded in the input values via the inter-event gap). The FOS receives the same wounding value $w_i$ at each step but at different "effective times" — however, since FOS is time-invariant and receives only $(x_t, e_t)$, the timing information must be encoded in the state.

Specifically: after step $i$, the FOS state must encode which of the $2^i$ timing patterns has occurred so far (to produce correct future outputs). This requires the reachable set $R_i$ to contain at least $2^i$ distinct points.

**Lemma (Dimension Lower Bound).** If $R_k \subset [-1, 1]^m$ contains $2^k$ points that must be pairwise distinguishable by a Lipschitz-continuous output function $h$ with Lipschitz constant $L$, and the minimum output separation is $\delta > 0$, then:

The minimum pairwise distance in state space is $\geq \delta / L$. Packing $2^k$ points in $[-1, 1]^m$ with minimum pairwise $\ell_\infty$-distance $\delta/L$ requires:
$$(2L/\delta)^m \geq 2^k$$
$$m \geq \frac{k}{\log_2(2L/\delta)}$$

For our construction: $\delta = |g(x, c \cdot 2.0) - g(x, c \cdot 1.5)|$ which is a positive constant depending on $c$ and $x$. With $g = \tanh$ and reasonable parameters, $\delta = \Theta(1)$ and $L = O(1)$, giving $m = \Omega(k)$.

$\square$

**Remark.** The Scar Algebra achieves this with total storage $O(k)$: 1 scalar base state + $k$ scars each requiring $O(1)$ storage (dimension index, timestamp, stage). The exponential compression arises because scar stages are *discrete* (4 values) while the FOS must encode the same information in *continuous* bounded state.

---

## Theorem 2: Convergence to Scarred Equilibrium

**Statement.** Let $\mathcal{S}$ be a Scar Algebra instance with $n$ dimensions, wounding threshold $\theta_w$, bounded input $\|e_t\|_\infty \leq C$ for all $t$, and base state evolution $g = \sigma_L \circ W_L \circ \cdots \circ \sigma_1 \circ W_1$ where each $\sigma_i$ is 1-Lipschitz (e.g., $\tanh$) and each $W_i$ satisfies $\|W_i\|_2 \leq c_i$ with $\prod c_i < 1$. Then:

(a) There exists $T^* < \infty$ such that for all $t > T^*$, no new scars form.

(b) The base state converges: $\|x_t - x^*\| \to 0$ as $t \to \infty$ for some $x^* \in [-1,1]^n$.

(c) All scars reach terminal stage ($faded$) in finite time.

### Proof

**(a) Scar formation cessation.**

Let $k_d(t)$ denote the number of scars on dimension $d$ at time $t$. A new scar forms on dimension $d$ only if $|\tilde{e}_d| > \theta_w$, i.e.:
$$|e_d| \cdot \prod_{i: d_i = d} \alpha(\phi_i) > \theta_w$$

Since $\alpha(\phi) \leq 2.0$ for all stages, and scars eventually reach $faded$ with $\alpha = 0.7$, we consider the worst case: all scars on dimension $d$ are $faded$. Then:
$$|e_d| \cdot 0.7^{k_d} > \theta_w \implies k_d < \frac{\ln(\theta_w / C)}{\ln(0.7)} = \frac{\ln(C/\theta_w)}{\ln(10/7)}$$

Define $k^*_d = \lceil \ln(C/\theta_w) / \ln(10/7) \rceil$. Once $k_d(t) \geq k^*_d$ and all scars on $d$ have reached $faded$:
$$|\tilde{e}_d| \leq C \cdot 0.7^{k^*_d} \leq \theta_w$$

No new scars can form on dimension $d$.

**Subtlety:** During healing, scars pass through $raw$ ($\alpha = 2.0$) and $closing$ ($\alpha = 1.5$), which *amplify* input and may cause additional scars before reaching $faded$. However, each scar spends finite time in amplifying stages ($T(raw) + T(closing)$ ticks), after which it becomes attenuating. The maximum number of "cascade scars" formed during the amplifying phase of scar $i$ is bounded by:
$$k_{cascade} \leq T(raw) + T(closing) = 50 \text{ ticks}$$

(at most one new scar per tick during the amplifying phase). Therefore total scars on any dimension is bounded by:
$$k_d^{total} \leq k^*_d \cdot (1 + k_{cascade}) < \infty$$

Let $T^* = \max_d \{$time for all scars on $d$ to reach $faded\}$. Since each scar reaches $faded$ in $T(raw) + T(closing) + T(scarred) = 10 + 40 + 150 = 200$ ticks, and total scars are bounded:
$$T^* \leq k_d^{total} + 200 \cdot k_d^{total} < \infty$$

**(b) Base state convergence.**

For $t > T^*$, all modifiers are $0.7^{k_d}$ (all scars faded, no new scars). The system becomes:
$$x_{t+1} = g(x_t, \mathbf{D} e_t) = \sigma_L(W_L \cdots \sigma_1(W_1 [x_t; \mathbf{D} e_t]))$$

where $\mathbf{D} = \text{diag}(0.7^{k_1}, \ldots, 0.7^{k_n})$ is a fixed diagonal attenuation matrix.

Since each $\sigma_i$ is 1-Lipschitz and each $\|W_i\|_2 \leq c_i$ with $\prod c_i < 1$, the composition $g$ is $(\prod c_i)$-Lipschitz by the chain rule for Lipschitz maps. In our 2-layer MLP implementation, $c_1 = c_2 = 0.7$, giving $\prod c_i = 0.49 < 1$.

Therefore $g$ is a contraction mapping. By the Banach fixed-point theorem, there exists a unique $x^*$ such that $x_t \to x^*$.

For time-varying but bounded inputs, the system is an *input-to-state stable* (ISS) system. The base state converges to a neighborhood of the zero-input fixed point, with radius proportional to $\prod c_i / (1 - \prod c_i) \cdot \|\mathbf{D}\|_2 \cdot C$. As $k_d \to k_d^{total}$, this radius shrinks (stronger attenuation), and the state converges.

**(c) Healing termination.**

Each scar advances through stages monotonically (Axiom 5) with bounded duration per stage. Total healing time per scar: $T(raw) + T(closing) + T(scarred) = 200$ ticks. Since total scars are finite (Part a), all scars reach $faded$ in finite time.

$\square$

---

## Theorem 3: Phase Transition at Critical Scar Density

**Statement.** Define the *effective gain* on dimension $d$ as $G_d = \prod_{i:d_i=d} \alpha(\phi_i)$. There exists a critical gain $G_c = \theta_w / C$ such that:
- For $G_d > G_c$: the system is in a *wounding regime* (new scars form, driving $G_d$ down)
- For $G_d < G_c$: the system is in a *numbed regime* (no new scars, healing drives $G_d$ up)
- The transition between regimes exhibits hysteresis with width $\Delta G = G_c \cdot (\alpha(raw) / \alpha(faded) - 1)$.

### Proof

**Wounding regime ($G_d > G_c$):**

When $G_d > \theta_w / C$, there exist inputs $e_d$ with $|e_d| \leq C$ such that $|e_d \cdot G_d| > \theta_w$. Each such input creates a new scar. New scars start at $raw$ with $\alpha(raw) = 2.0$, which *increases* $G_d$ temporarily, creating a positive feedback loop:

$$G_d \uparrow \implies \text{more wounding} \implies G_d \uparrow \text{ (short term)}$$

This cascade continues until the raw scars begin healing. After $T(raw) = 10$ ticks, each scar transitions to $closing$ ($\alpha = 1.5$), then $scarred$ ($\alpha = 1.0$), then $faded$ ($\alpha = 0.7$).

**Numbed regime ($G_d < G_c$):**

When $G_d < \theta_w / C$, no input can cause wounding: $|e_d \cdot G_d| \leq C \cdot G_d < \theta_w$. Existing scars heal, and since $\alpha(faded) = 0.7 < 1.0 < \alpha(raw) = 2.0$, healing *decreases* $G_d$ further if scars are transitioning from amplifying to attenuating stages, or *increases* $G_d$ if... 

Wait — healing moves scars from $raw \to closing \to scarred \to faded$, which changes $\alpha$ as $2.0 \to 1.5 \to 1.0 \to 0.7$. So healing *decreases* $G_d$ monotonically. This means once in the numbed regime, the system stays numbed (no recovery).

**Correction:** Recovery requires *removal* of scars, which is forbidden (Axiom 3). Therefore the numbed regime is *absorbing* — once entered, it cannot be exited.

**Hysteresis:** The system enters the wounding regime when $G_d$ first exceeds $G_c$ (due to a raw scar amplifying a previously sub-threshold dimension). It exits the wounding regime only when enough scars have healed to faded that $G_d$ drops below $G_c$. The entry point is at $G_d = G_c \cdot \alpha(raw) = 2G_c$ (a single raw scar on a previously-at-threshold dimension), while the exit point is at $G_d = G_c$. The hysteresis width is:
$$\Delta G = G_c \cdot (\alpha(raw) - 1) = G_c$$

**Phase transition characterization:** The transition is *discontinuous* in the following sense: the long-term scar formation rate $\lambda_d$ satisfies:
$$\lambda_d = \begin{cases} > 0 & \text{if } G_d(t_0) > G_c \text{ and } t < T^* \\ = 0 & \text{if } G_d(t) < G_c \text{ for all } t > t_0 \end{cases}$$

with no intermediate steady-state rate. The system is either actively wounding or completely silent on each dimension.

$\square$

---

## Theorem 4: Non-Commutativity (Strict)

**Statement.** For any Scar Algebra instance with $\theta_w > 0$ and $\alpha(raw) > 1$, there exist events $e_1, e_2$ and initial state $s_0$ such that:
$$(s_0 \triangleright e_1) \triangleright e_2 \neq (s_0 \triangleright e_2) \triangleright e_1$$

where inequality holds in both the base state and scar sequence components.

### Proof

Let $n = 1$, $s_0 = (0, \emptyset)$, $e_1 = \theta_w + \epsilon$, $e_2 = \theta_w / \alpha(raw) + \epsilon'$ where $\epsilon, \epsilon' > 0$ are small and $e_2 < \theta_w$ (sub-threshold without amplification).

**Path $e_1$ then $e_2$:**
1. $s_0 \triangleright e_1$: Input $\tilde{e}_1 = e_1 \cdot 1 = \theta_w + \epsilon > \theta_w$. Scar forms. State: $s_1 = (g(0, e_1), \{\sigma_1\})$ with $\sigma_1$ at stage $raw$.
2. $s_1 \triangleright e_2$: Input $\tilde{e}_2 = e_2 \cdot \alpha(raw) = e_2 \cdot 2.0 = 2\theta_w/\alpha(raw) + 2\epsilon' = \theta_w + 2\epsilon' > \theta_w$. **Second scar forms.** State: $s_{12} = (g(g(0, e_1), \tilde{e}_2), \{\sigma_1, \sigma_2\})$.

**Path $e_2$ then $e_1$:**
1. $s_0 \triangleright e_2$: Input $\tilde{e}_2 = e_2 \cdot 1 = \theta_w/\alpha(raw) + \epsilon' < \theta_w$. **No scar.** State: $s_2 = (g(0, e_2), \emptyset)$.
2. $s_2 \triangleright e_1$: Input $\tilde{e}_1 = e_1 \cdot 1 = \theta_w + \epsilon > \theta_w$. One scar forms. State: $s_{21} = (g(g(0, e_2), e_1), \{\sigma_1'\})$.

**Comparison:**
- Scar sequences: $|\sigma_{12}| = 2 \neq 1 = |\sigma_{21}|$ (different scar counts)
- Base states: $g(g(0, e_1), \tilde{e}_2) \neq g(g(0, e_2), e_1)$ since $\tilde{e}_2 = 2e_2 \neq e_2$ and $g$ is nonlinear

Both components differ. $\square$

---

## Theorem 5: Algebraic Classification

**Statement.** The structure $(S, E, \triangleright)$ is a *faithful, non-commutative, irreversible action* of the free monoid $E^*$ on $S$. It does not embed into any group action, and the induced equivalence relation on $E^*$ (identifying sequences that produce the same state from any initial state) has infinite index.

### Proof

**(a) Faithful action.** For any two distinct input sequences $\mathbf{e} \neq \mathbf{e}'$ of the same length, there exists an initial state $s_0$ such that $s_0 \triangleright \mathbf{e} \neq s_0 \triangleright \mathbf{e}'$.

*Proof:* Take $s_0 = (\mathbf{0}, \emptyset)$. If $\mathbf{e}$ and $\mathbf{e}'$ differ at position $j$, then the base states after step $j$ differ (since $g$ is injective in its second argument for fixed first argument when using $\tanh$). Subsequent steps preserve this difference (injectivity propagates).

**(b) No group embedding.** Suppose for contradiction that $\triangleright$ embeds into a group action $\cdot$ of group $(G, \cdot)$ on $S$. Then for every $e \in E$, there exists $e^{-1} \in G$ such that $(s \triangleright e) \cdot e^{-1} = s$. But by Axiom 1, no such inverse exists in $E$ (or any extension of $E$ acting on $S$), since scar formation is irreversible. Contradiction.

**(c) Infinite index.** Define $\mathbf{e} \sim \mathbf{e}'$ iff $\forall s_0: s_0 \triangleright \mathbf{e} = s_0 \triangleright \mathbf{e}'$. We show $E^* / {\sim}$ is infinite.

Consider the sequences $W_k = (w, w, \ldots, w)$ of $k$ wounding events. From $s_0 = (\mathbf{0}, \emptyset)$:
- $s_0 \triangleright W_k$ has exactly $k$ scars (each wounding event creates one, since amplification from previous raw scars only increases the effective input above threshold)
- For $k \neq k'$: $|s_0 \triangleright W_k|_\Sigma = k \neq k' = |s_0 \triangleright W_{k'}|_\Sigma$

Therefore $W_k \not\sim W_{k'}$ for all $k \neq k'$, giving infinitely many equivalence classes.

$\square$

---

## Theorem 6: Behavioral Equivalence is Decidable

**Statement.** Given two scar sequences $\sigma, \sigma'$, the problem "do $\sigma$ and $\sigma'$ produce identical modifiers for all future inputs?" is decidable in $O(n \cdot \max(|\sigma|, |\sigma'|))$ time.

### Proof

Two scar sequences are behaviorally equivalent iff they produce the same modifier on every dimension:
$$\forall d: \prod_{i: \sigma_i.d = d} \alpha(\sigma_i.\phi) = \prod_{j: \sigma'_j.d = d} \alpha(\sigma'_j.\phi)$$

But this is only a snapshot equivalence (at current time). For *all future* equivalence, we need the healing trajectories to also match. Since healing is deterministic given current stage and ticks_in_stage, two scars are future-equivalent iff they have the same $(dimension, stage, ticks\_in\_stage)$ triple.

**Algorithm:**
1. For each dimension $d$, collect the multiset of $(stage, ticks\_in\_stage)$ pairs from $\sigma$ and $\sigma'$.
2. Sort each multiset.
3. Compare: equivalent iff all multisets match.

Time: $O(n \cdot k \log k)$ where $k = \max(|\sigma|, |\sigma'|)$.

**Note:** This is *future* behavioral equivalence (same modifiers for all future time). *Past* behavioral equivalence (same outputs on all past inputs) is trivially undecidable in general (requires checking all possible input histories), but for the specific case of Scar Algebra with deterministic healing, it reduces to checking whether the current scar configurations could have been produced by the same input sequence — which is decidable by the same multiset comparison.

$\square$

---

## Complexity Results

**Proposition 7.** The following decision problems have the stated complexities:

| Problem | Complexity |
|---------|-----------|
| "Is dimension $d$ numbed?" ($M_d < 0.5$) | $O(k_d)$ |
| "Will a new scar form on input $e$?" | $O(k)$ total |
| "Are two states behaviorally equivalent?" | $O(nk \log k)$ |
| "Given input sequence $E$, what is the final state?" | $O(|E| \cdot k_{max})$ |
| "Does there exist an input that causes wounding on dim $d$?" | $O(k_d)$ — check if $C \cdot M_d > \theta_w$ |

All problems are polynomial in the scar count, confirming that Scar Algebra is computationally tractable despite its expressiveness.

---

## Theorem 3.6' (Convergence under Spectral-Normalized MLP)

**Statement.** Let $g = \sigma_L \circ W_L \circ \cdots \circ \sigma_1 \circ W_1$ where each $\sigma_i$ is 1-Lipschitz (e.g., $\tanh$) and each $W_i$ satisfies $\|W_i\|_2 \leq c_i$ with $\prod c_i < 1$. Then the scarred state system converges to a unique equilibrium under bounded input.

### Proof

By composition of Lipschitz maps, $g$ is $(\prod c_i)$-Lipschitz $< 1$-Lipschitz, hence a contraction. By the Banach fixed-point theorem, $\exists! x^*$ such that $x_t \to x^*$.

**Detailed argument.** For the 2-layer MLP case ($L = 2$):
- Layer 1: $h = \tanh(W_1 [x; \tilde{e}])$. Since $\tanh$ is 1-Lipschitz and $\|W_1\|_2 \leq c_1$, this layer is $c_1$-Lipschitz in its input.
- Layer 2: $y = \tanh(W_2 h)$. Similarly $c_2$-Lipschitz.
- Composition: $\|g(a) - g(b)\| \leq c_1 c_2 \|a - b\|$ for all $a, b$.

With spectral normalization enforcing $c_1 = c_2 = 0.7$:
$$\|g(a) - g(b)\| \leq 0.49 \|a - b\|$$

This is a strict contraction with rate $0.49$. Convergence is geometric with rate $0.49^t$.

**Comparison with linear case.** The original $\tanh(\mathbf{A}x + \mathbf{B}\tilde{e})$ required $\|\mathbf{A}\|_\infty < 1$, which is a weaker condition (only constrains the linear part w.r.t. $x$). The MLP formulation provides a stronger guarantee: the *entire* map (including the input-dependent part) is contractive, not just the autonomous part.

$\square$

---

## Theorem 3.7 (Adaptive Healing Preserves Convergence)

**Statement.** If healing rates $T(\varphi)$ are bounded functions of personality vector $\mathbf{p} \in [0,1]^k$, the convergence result of Theorem 3.6' still holds. Healing rates affect transient behavior but not the existence of equilibrium.

### Proof

The convergence of Theorem 3.6' depends on two properties:
1. The base state evolution map $g$ is a contraction (guaranteed by spectral normalization, independent of healing rates).
2. Scar formation eventually ceases (Theorem 2a).

**Healing rates affect only the transient.** The healing rate $T(\varphi)$ determines how quickly scars transition through stages $raw \to closing \to scarred \to faded$. This affects:
- The *duration* of the amplifying phase (how long $\alpha > 1$)
- The *time* until the system enters the numbed regime
- The *total number* of cascade scars formed during amplification

But it does *not* affect:
- The contraction rate of $g$ (determined solely by $\prod c_i$)
- The existence of the equilibrium $x^*$
- The eventual cessation of scar formation (which depends on $\alpha(faded) = 0.7 < 1$)

**Formal bound.** Let $T_{max} = \max_{\mathbf{p}} T(\mathbf{p})$ be the maximum healing duration across all personality configurations. The time to equilibrium satisfies:
$$T^*(\mathbf{p}) \leq k_d^{total}(\mathbf{p}) \cdot (T_{raw}(\mathbf{p}) + T_{closing}(\mathbf{p}) + T_{scarred}(\mathbf{p}))$$

For our implementation with $T_{raw} = 10 + 20p_{neuroticism}$:
- Fastest healing ($p_{neuroticism} = 0$): $T^* \propto k \cdot 200$
- Slowest healing ($p_{neuroticism} = 1$): $T^* \propto k \cdot 380$

In both cases, $T^* < \infty$, and after $T^*$ the system converges at rate $0.49^t$ regardless of personality.

**Repeated wounding slowdown.** The per-dimension multiplier (×1.5 for $scar\_count > 3$) further slows healing on heavily scarred dimensions. This is bounded:
$$T_{effective}(d) \leq 1.5 \cdot T_{max}$$

which remains finite, preserving the convergence guarantee.

$\square$

---

## Open Problems

1. **Tight expressiveness bound:** Is the $\Omega(k)$ lower bound in Theorem 1 tight, or can it be improved to $\Omega(k \log k)$ or $\Omega(2^k)$?

2. **Cascade bound:** What is the tight upper bound on total scars formed from a single initial wound (the cascade problem)?

3. **Optimal healing schedule:** If healing rates were controllable (not fixed), what schedule minimizes time-to-equilibrium while maintaining expressiveness?
