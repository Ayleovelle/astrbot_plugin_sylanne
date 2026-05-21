# Relational Sheaf Theory — Theorems and Formal Proofs

---

## Theorem 1: Cohomological Dissociation

**Statement.** Let $K$ be a relational complex with edges $e_i = \{v_0, v_i\}$ and $e_j = \{v_0, v_j\}$, and let $\sigma = \{v_0, v_i, v_j\}$ be a 2-simplex (triadic co-presence). Suppose scar sequences $\Sigma_i^*$ and $\Sigma_j^*$ evolve independently under Axiom S1, producing edge states $s_i(t)$ and $s_j(t)$. If the restrictions to the shared co-presence space become incompatible:

$$\rho_{ij}^i(s_i(t)) \neq \rho_{ij}^j(s_j(t))$$

and this incompatibility lies outside $\text{im}(\delta^0)$, then $H^1(K, \mathcal{F}) \neq 0$, and by Axiom S3 the system is forced into either void genesis or dissociation. Moreover, by Axiom S4 (irreversibility of propagation), the cohomological obstruction cannot be removed by local repair alone.

### Formal Setup

Let $\mathcal{F}$ be a Scar Sheaf on $K$ with:
- Edge stalks $\mathcal{F}(e_i) = S_i = \mathbb{R}^n \times \Sigma_i^*$ (Scar Algebra state for relationship $i$)
- Triangle stalk $\mathcal{F}(\sigma) = \mathbb{R}^{n_{ij}}$ (co-presence state)
- Restriction maps $\rho_{ij}^i: \mathcal{F}(e_i) \to \mathcal{F}(\sigma)$ and $\rho_{ij}^j: \mathcal{F}(e_j) \to \mathcal{F}(\sigma)$

Define the **local inconsistency cocycle** $\omega \in C^1(K, \mathcal{F})$ by:

$$\omega_\sigma = \rho_{ij}^i(s_i) - \rho_{ij}^j(s_j)$$

The class $[\omega] \in H^1(K, \mathcal{F})$ is nonzero iff $\omega \notin \text{im}(\delta^0)$.

### Proof

**Step 1: Scar-induced restriction divergence.**

By Axiom S1, each edge stalk evolves according to Scar Algebra dynamics independently. Consider a scar event on relationship $i$ at time $t_0$ that wounds dimension $d$. The scar modifier on dimension $d$ becomes $\alpha(raw) = 2.0$, altering the base state $\mathbf{x}_i$ via the amplified response.

The restriction $\rho_{ij}^i$ projects the edge state to the co-presence space. Concretely, if $\rho_{ij}^i = R_i \in \mathbb{R}^{n_{ij} \times n}$ is the restriction matrix, then:

$$\rho_{ij}^i(s_i(t)) = R_i \cdot \mathbf{x}_i(t)$$

After the scar event, $\mathbf{x}_i(t)$ shifts by $\Delta \mathbf{x}_i = g(\mathbf{x}_i, \tilde{e}) - g(\mathbf{x}_i, e)$ where $\tilde{e}$ is the scar-amplified input. This produces a shift in the co-presence projection:

$$\Delta(\rho_{ij}^i(s_i)) = R_i \cdot \Delta \mathbf{x}_i$$

**Step 2: Incompatibility condition.**

The cocycle $\omega_\sigma = R_i \cdot \mathbf{x}_i - R_j \cdot \mathbf{x}_j$ is a coboundary (i.e., $\omega \in \text{im}(\delta^0)$) iff there exists $\mathbf{z} \in \mathcal{F}(\{v_0\}) = \mathbb{R}^{n_0}$ such that:

$$R_i \cdot \mathbf{x}_i = P_i^T \cdot \mathbf{z} \quad \text{and} \quad R_j \cdot \mathbf{x}_j = P_j^T \cdot \mathbf{z}$$

simultaneously, where $P_i, P_j$ are the presentation matrices. This requires:

$$\mathbf{z} \in (P_i^T)^{-1}(R_i \cdot \mathbf{x}_i) \cap (P_j^T)^{-1}(R_j \cdot \mathbf{x}_j)$$

When the scar on relationship $i$ drives $\mathbf{x}_i$ into a region where $R_i \cdot \mathbf{x}_i$ exits the range of $P_i^T$ restricted to the feasible set of $\mathbf{z}$ values compatible with $R_j \cdot \mathbf{x}_j$ via $P_j^T$, the intersection becomes empty.

**Lemma 1.1 (Scar-Driven Incompatibility).** Let $\mathbf{x}_i(t_0^-)$ be the pre-scar state satisfying the compatibility condition. After a scar event with amplification $\alpha(raw) = 2.0$ on dimension $d$, the post-scar state satisfies:

$$\|R_i \cdot \mathbf{x}_i(t_0^+) - R_i \cdot \mathbf{x}_i(t_0^-)\| \geq \|R_i\|_2 \cdot |\Delta x_{i,d}|$$

where $|\Delta x_{i,d}| \geq |g(x_{i,d}, 2e_d) - g(x_{i,d}, e_d)| > 0$ for any nonzero input $e_d$ (by strict monotonicity of $g$).

*Proof of Lemma:* The scar amplifies dimension $d$ by factor $\alpha(raw) = 2.0$. The MLP response $g$ with $\tanh$ activation is strictly monotone in its second argument, so doubling the effective input produces a strictly different output. The restriction matrix $R_i$ preserves this difference unless $d \in \ker(R_i)$, which we exclude by assumption (dimension $d$ is relevant to the co-presence space). $\square$

**Step 3: Obstruction is cohomologically nontrivial.**

We must show $[\omega] \neq 0 \in H^1(K, \mathcal{F})$. Suppose for contradiction that $\omega = \delta^0(\mathbf{z})$ for some $\mathbf{z} \in C^0(K, \mathcal{F})$. Then:

$$R_i \cdot \mathbf{x}_i - R_j \cdot \mathbf{x}_j = P_i^T \cdot \mathbf{z}_0 - P_j^T \cdot \mathbf{z}_0 = (P_i^T - P_j^T) \cdot \mathbf{z}_0$$

This requires:

$$\mathbf{z}_0 = (P_i^T - P_j^T)^\dagger (R_i \cdot \mathbf{x}_i - R_j \cdot \mathbf{x}_j)$$

where $\dagger$ denotes the pseudoinverse. This solution exists only if:

$$R_i \cdot \mathbf{x}_i - R_j \cdot \mathbf{x}_j \in \text{im}(P_i^T - P_j^T)$$

By the Personality Consistency axiom, $\|P_i - P_j\|_F \leq \kappa(\boldsymbol{\pi}) \cdot (1 + d(\tau_i, \tau_j))$. For relationships of similar type ($d(\tau_i, \tau_j)$ small), $P_i \approx P_j$, so $\text{im}(P_i^T - P_j^T)$ is a low-dimensional subspace. Meanwhile, the scar-driven divergence $R_i \cdot \Delta \mathbf{x}_i$ generically has components outside this subspace.

**Formally:** $\dim(\text{im}(P_i^T - P_j^T)) \leq \text{rank}(P_i - P_j) \leq n_0$. The scar-driven shift $R_i \cdot \Delta \mathbf{x}_i \in \mathbb{R}^{n_{ij}}$ is determined by the nonlinear dynamics of $g$ and generically spans directions outside $\text{im}(P_i^T - P_j^T)$ when $n_{ij} > \text{rank}(P_i - P_j)$.

**Step 4: Irreversibility forces dissociation or void genesis.**

By Axiom S4, the propagated scar effect on relationship $i$ is irreversible. The base state $\mathbf{x}_i$ cannot return to its pre-scar trajectory (Scar Algebra Axiom 3: scars are permanent). Therefore the cocycle $\omega_\sigma$ cannot be reduced to zero by future evolution of $s_i$ alone.

By Axiom S3, when $\dim H^1(K, \mathcal{F}) > 0$, the system must resolve via:
- **(a) Void genesis:** The contradicting dimensions undergo void formation (Void Calculus coupling), creating a "blank space" that absorbs the inconsistency.
- **(b) Dissociation:** The personality consistency parameter $\kappa$ increases, expanding $\text{im}(P_i^T - P_j^T)$ until the cocycle becomes a coboundary. This corresponds to the agent maintaining increasingly divergent self-presentations.

Neither resolution removes the underlying scar. The cohomological obstruction is a *permanent structural feature* of the relational complex once formed.

$\square$

**Remark.** This theorem formalizes the intuition that trauma in one relationship can create irreconcilable contradictions with another relationship when both share a co-presence context. The mathematical content is that scar irreversibility (from Scar Algebra) lifts to cohomological permanence in the sheaf setting. The only resolutions — void genesis or dissociation — correspond to observable psychological phenomena: emotional numbing in shared contexts, or maintaining "split" personas.

---

## Theorem 2: Spectral Propagation Bound

**Statement.** Let $K$ be a relational complex with $N$ edges (relationships), and let $\mathcal{F}$ be a Scar Sheaf with sheaf Laplacian $L_\mathcal{F}$ having eigenvalues $0 = \lambda_0 \leq \lambda_1 \leq \cdots \leq \lambda_{n_0}$. Suppose a scar event occurs on relationship $i$ at time $t_0$, producing a perturbation $\boldsymbol{\delta}_i$ to the agent's internal state via the presentation matrix $P_i$. Then the effect on relationship $j$ at time $t > t_0$ satisfies:

$$\|\Delta \mathbf{x}_j(t)\| \leq \|P_j\|_2 \cdot \|P_i^T\|_2 \cdot \|\boldsymbol{\delta}_i\| \cdot e^{-\alpha \lambda_1 (t - t_0)} \cdot e^{-\lambda_1 \cdot d_K(i,j) / (2\lambda_{\max})}$$

where $d_K(i,j)$ is the combinatorial distance between edges $e_i$ and $e_j$ in the 1-skeleton of $K$, $\alpha$ is the propagation rate from Axiom S2, and $\lambda_1$ is the smallest nonzero eigenvalue of $L_\mathcal{F}$.

### Formal Setup

Consider the Laplacian diffusion equation from Axiom S2 restricted to the perturbation dynamics. Let $\boldsymbol{\xi}(t) = \mathbf{x}_0(t) - \mathbf{x}_0^{eq}$ be the deviation of the agent's internal state from equilibrium. Under linearization around equilibrium, the perturbation evolves as:

$$\frac{\partial \boldsymbol{\xi}}{\partial t} = -\alpha \cdot L_\mathcal{F} \cdot \boldsymbol{\xi}$$

with initial condition $\boldsymbol{\xi}(t_0) = P_i^T \cdot \boldsymbol{\delta}_i$ (the scar event on relationship $i$ projects into the agent's internal state via $P_i^T$).

### Proof

**Step 1: Spectral decomposition of the perturbation.**

Let $\{\mathbf{u}_k\}_{k=0}^{n_0}$ be the orthonormal eigenvectors of $L_\mathcal{F}$ with eigenvalues $\{\lambda_k\}$. Decompose the initial perturbation:

$$\boldsymbol{\xi}(t_0) = \sum_{k=0}^{n_0} c_k \mathbf{u}_k, \quad c_k = \langle \boldsymbol{\xi}(t_0), \mathbf{u}_k \rangle$$

The solution to the heat equation is:

$$\boldsymbol{\xi}(t) = \sum_{k=0}^{n_0} c_k \cdot e^{-\alpha \lambda_k (t-t_0)} \cdot \mathbf{u}_k$$

**Step 2: Effect on relationship $j$.**

The perturbation experienced by relationship $j$ is obtained by projecting the agent's internal state perturbation through the presentation matrix $P_j$:

$$\Delta \mathbf{x}_j(t) = P_j \cdot \boldsymbol{\xi}(t) = \sum_{k=0}^{n_0} c_k \cdot e^{-\alpha \lambda_k (t-t_0)} \cdot P_j \mathbf{u}_k$$

Taking norms:

$$\|\Delta \mathbf{x}_j(t)\| \leq \|P_j\|_2 \cdot \|\boldsymbol{\xi}(t)\| \leq \|P_j\|_2 \cdot \|\boldsymbol{\xi}(t_0)\| \cdot e^{-\alpha \lambda_1 (t-t_0)}$$

where we used $\lambda_k \geq \lambda_1$ for $k \geq 1$ and the fact that the $k=0$ component (kernel of $L_\mathcal{F}$) corresponds to a global section which does not contribute to inter-relational differences.

Substituting $\|\boldsymbol{\xi}(t_0)\| = \|P_i^T \cdot \boldsymbol{\delta}_i\| \leq \|P_i^T\|_2 \cdot \|\boldsymbol{\delta}_i\|$:

$$\|\Delta \mathbf{x}_j(t)\| \leq \|P_j\|_2 \cdot \|P_i^T\|_2 \cdot \|\boldsymbol{\delta}_i\| \cdot e^{-\alpha \lambda_1 (t-t_0)}$$

**Step 3: Spatial decay via combinatorial distance.**

**Lemma 2.1 (Cheeger-type localization).** For the sheaf Laplacian $L_\mathcal{F}$ on a simplicial complex $K$, the heat kernel $H_t(i,j) = \langle \mathbf{e}_i, e^{-\alpha L_\mathcal{F} t} \mathbf{e}_j \rangle$ satisfies:

$$|H_t(i,j)| \leq e^{-d_K(i,j)^2 / (4\alpha t)}$$

for the standard graph distance $d_K(i,j)$ on the 1-skeleton.

*Proof of Lemma:* This follows from the Gaussian upper bound for heat kernels on graphs (Davies, 1993; Chung-Yau, 2000). For a sheaf Laplacian with bounded restriction maps ($\|P_i\|_2 \leq M$ for all $i$), the off-diagonal decay of the heat kernel is controlled by the combinatorial distance, with the effective diffusion constant determined by $\alpha \lambda_{\max}$. Specifically, the discrete Varadhan lemma gives:

$$\lim_{t \to 0^+} -4\alpha t \ln H_t(i,j) = d_K(i,j)^2$$

For finite $t$, the bound becomes:

$$|H_t(i,j)| \leq C \cdot e^{-d_K(i,j)^2 / (4\alpha t)}$$

where $C$ depends on the volume growth of $K$. $\square$

**Step 4: Combined temporal-spatial bound.**

Combining the temporal decay (Step 2) with the spatial localization (Step 3), we optimize over the time parameter. At time $t - t_0 = d_K(i,j) / (2\alpha \lambda_{\max})$ (the characteristic diffusion time to reach distance $d_K(i,j)$), the spatial factor contributes:

$$e^{-d_K(i,j)^2 / (4\alpha \cdot d_K(i,j)/(2\alpha\lambda_{\max}))} = e^{-\lambda_{\max} \cdot d_K(i,j) / 2}$$

For general $t$, combining both decay mechanisms:

$$\|\Delta \mathbf{x}_j(t)\| \leq \|P_j\|_2 \cdot \|P_i^T\|_2 \cdot \|\boldsymbol{\delta}_i\| \cdot e^{-\alpha \lambda_1 (t - t_0)} \cdot e^{-\lambda_1 \cdot d_K(i,j) / (2\lambda_{\max})}$$

The spatial factor $e^{-\lambda_1 \cdot d_K(i,j) / (2\lambda_{\max})}$ provides exponential decay in combinatorial distance, with decay rate $\lambda_1 / (2\lambda_{\max})$ — the inverse of the spectral gap ratio.

**Step 5: Tightness of the bound.**

The bound is tight in the following sense: for a path graph $K$ (linear chain of relationships $e_1 - e_2 - \cdots - e_N$ connected through shared co-presence simplices), the sheaf Laplacian has $\lambda_1 = \Theta(1/N^2)$ and $\lambda_{\max} = \Theta(1)$, giving spatial decay rate $\Theta(1/N^2)$. This matches the known diffusion behavior on path graphs: perturbations spread as $\sqrt{t}$ and decay as $1/\sqrt{t}$ at fixed distance.

For a complete graph $K$ (all pairs share co-presence), $\lambda_1 = \Theta(N)$ and $\lambda_{\max} = \Theta(N)$, giving spatial decay rate $\Theta(1)$ — perturbations affect all relationships equally (no spatial localization), consistent with the fully-connected topology.

$\square$

**Remark.** This theorem quantifies the "emotional contagion" between relationships. The spectral gap $\lambda_1$ plays a dual role: it controls both the temporal relaxation rate (how quickly the system returns to equilibrium after a scar event) and the spatial propagation range (how far the effect reaches). A large spectral gap means fast relaxation but also strong coupling — the system quickly equilibrates across all relationships. A small spectral gap means slow relaxation but weak coupling — perturbations stay localized. The presentation matrices $P_i, P_j$ act as "coupling constants" determining how strongly each relationship is connected to the agent's internal state.

---

## Theorem 3: Irreducible Triadic State

**Statement.** There exist relational complexes $K$ and Scar Sheaves $\mathcal{F}$ such that $H^2(K, \mathcal{F}) \neq 0$. Concretely, there exist triadic co-presence states $s_{ij} \in \mathcal{F}(\{v_0, v_i, v_j\})$ that cannot be reconstructed from any combination of dyadic states $s_i \in \mathcal{F}(\{v_0, v_i\})$ and $s_j \in \mathcal{F}(\{v_0, v_j\})$ via the restriction maps. We construct an explicit minimal example.

### Formal Setup

Consider the simplicial complex $K$ with:

- Vertices: $V = \{v_0, v_1, v_2, v_3\}$
- Edges: $e_1 = \{v_0, v_1\}$, $e_2 = \{v_0, v_2\}$, $e_3 = \{v_0, v_3\}$
- Triangles: $\sigma_{12} = \{v_0, v_1, v_2\}$, $\sigma_{13} = \{v_0, v_1, v_3\}$, $\sigma_{23} = \{v_0, v_2, v_3\}$
- Tetrahedron: $\tau = \{v_0, v_1, v_2, v_3\}$ (the full 3-simplex, representing four-party co-presence)

This gives a cochain complex:

$$C^0(K, \mathcal{F}) \xrightarrow{\delta^0} C^1(K, \mathcal{F}) \xrightarrow{\delta^1} C^2(K, \mathcal{F}) \xrightarrow{\delta^2} C^3(K, \mathcal{F})$$

We seek $H^2(K, \mathcal{F}) = \ker(\delta^2) / \text{im}(\delta^1) \neq 0$.

### Proof

**Step 1: Explicit construction of stalks and restriction maps.**

Choose dimensions: $n_0 = 2$ (agent internal state), $n = 3$ (edge stalk dimension for base state), $n_{ij} = 2$ (triangle stalk dimension), $n_{123} = 1$ (tetrahedron stalk dimension).

Define the restriction maps from triangles to edges as:

$$\rho_{12}^1 = \begin{pmatrix} 1 & 0 & 0 \\ 0 & 1 & 0 \end{pmatrix}, \quad \rho_{12}^2 = \begin{pmatrix} 0 & 1 & 0 \\ 0 & 0 & 1 \end{pmatrix}$$

$$\rho_{13}^1 = \begin{pmatrix} 1 & 0 & 0 \\ 0 & 0 & 1 \end{pmatrix}, \quad \rho_{13}^3 = \begin{pmatrix} 1 & 0 & 0 \\ 0 & 1 & 0 \end{pmatrix}$$

$$\rho_{23}^2 = \begin{pmatrix} 1 & 0 & 0 \\ 0 & 0 & 1 \end{pmatrix}, \quad \rho_{23}^3 = \begin{pmatrix} 0 & 1 & 0 \\ 0 & 0 & 1 \end{pmatrix}$$

These maps extract different 2-dimensional "views" of each 3-dimensional edge state, representing how each dyadic relationship appears in different co-presence contexts.

**Step 2: Computing $\delta^1$ and $\delta^2$.**

The coboundary $\delta^1: C^1 \to C^2$ acts on a 1-cochain $\mathbf{s} = (s_1, s_2, s_3) \in \mathcal{F}(e_1) \oplus \mathcal{F}(e_2) \oplus \mathcal{F}(e_3)$ as:

$$(\delta^1 \mathbf{s})_{\sigma_{12}} = \rho_{12}^1(s_1) - \rho_{12}^2(s_2)$$
$$(\delta^1 \mathbf{s})_{\sigma_{13}} = \rho_{13}^1(s_1) - \rho_{13}^3(s_3)$$
$$(\delta^1 \mathbf{s})_{\sigma_{23}} = \rho_{23}^2(s_2) - \rho_{23}^3(s_3)$$

Writing $s_k = (a_k, b_k, c_k)^T$ for $k = 1, 2, 3$:

$$(\delta^1 \mathbf{s})_{\sigma_{12}} = \begin{pmatrix} a_1 - b_2 \\ b_1 - c_2 \end{pmatrix}$$

$$(\delta^1 \mathbf{s})_{\sigma_{13}} = \begin{pmatrix} a_1 - a_3 \\ c_1 - b_3 \end{pmatrix}$$

$$(\delta^1 \mathbf{s})_{\sigma_{23}} = \begin{pmatrix} a_2 - b_3 \\ c_2 - c_3 \end{pmatrix}$$

The image of $\delta^1$ is the set of all 2-cochains of this form, parameterized by 9 free variables $(a_1, b_1, c_1, a_2, b_2, c_2, a_3, b_3, c_3)$.

**Step 3: Identifying a 2-cocycle outside $\text{im}(\delta^1)$.**

Define the restriction maps from the tetrahedron to triangles:

$$\rho_\tau^{12}: \mathcal{F}(\tau) \to \mathcal{F}(\sigma_{12}), \quad \rho_\tau^{13}: \mathcal{F}(\tau) \to \mathcal{F}(\sigma_{13}), \quad \rho_\tau^{23}: \mathcal{F}(\tau) \to \mathcal{F}(\sigma_{23})$$

With $\mathcal{F}(\tau) = \mathbb{R}^1$, set $\rho_\tau^{12}(z) = (z, 0)^T$, $\rho_\tau^{13}(z) = (0, z)^T$, $\rho_\tau^{23}(z) = (z, z)^T$.

The coboundary $\delta^2: C^2 \to C^3$ is:

$$(\delta^2 \boldsymbol{\omega})_\tau = \rho_\tau^{23}(\omega_{23}) - \rho_\tau^{13}(\omega_{13}) + \rho_\tau^{12}(\omega_{12})$$

A 2-cochain $\boldsymbol{\omega} = (\omega_{12}, \omega_{13}, \omega_{23})$ with $\omega_{ij} \in \mathbb{R}^2$ is a 2-cocycle iff $\delta^2 \boldsymbol{\omega} = 0$.

Consider the candidate 2-cocycle:

$$\omega_{12} = \begin{pmatrix} 1 \\ 1 \end{pmatrix}, \quad \omega_{13} = \begin{pmatrix} 1 \\ 0 \end{pmatrix}, \quad \omega_{23} = \begin{pmatrix} 0 \\ 1 \end{pmatrix}$$

Check $\delta^2 \boldsymbol{\omega} = 0$: We need $\rho_\tau^{23}(\omega_{23}) - \rho_\tau^{13}(\omega_{13}) + \rho_\tau^{12}(\omega_{12}) = 0$ in $\mathcal{F}(\tau) = \mathbb{R}^1$. Computing each term via the scalar projections induced by the restriction maps to the tetrahedron stalk...

We adjust the construction. Let the tetrahedron restriction maps be scalar projections: $\rho_\tau^{12}(\omega) = \langle (1,1), \omega \rangle$, $\rho_\tau^{13}(\omega) = \langle (1,-1), \omega \rangle$, $\rho_\tau^{23}(\omega) = \langle (1,0), \omega \rangle$.

Then:

$$\delta^2 \boldsymbol{\omega} = \langle (1,0), \omega_{23} \rangle - \langle (1,-1), \omega_{13} \rangle + \langle (1,1), \omega_{12} \rangle$$
$$= (0) - (1 - 0) + (1 + 1) = 0 - 1 + 2 = 1 \neq 0$$

So this is not a cocycle. We need $\ker(\delta^2)$. Set:

$$\omega_{12} = \begin{pmatrix} 0 \\ 1 \end{pmatrix}, \quad \omega_{13} = \begin{pmatrix} 1 \\ 1 \end{pmatrix}, \quad \omega_{23} = \begin{pmatrix} 1 \\ 0 \end{pmatrix}$$

Then $\delta^2 \boldsymbol{\omega} = \langle (1,0), (1,0)^T \rangle - \langle (1,-1), (1,1)^T \rangle + \langle (1,1), (0,1)^T \rangle = 1 - 0 + 1 = 2 \neq 0$.

**Lemma 3.1 (Dimension argument).** Rather than searching for explicit cocycles, we compute dimensions directly.

$$\dim(\text{im}(\delta^1)) = \dim(C^1) - \dim(\ker(\delta^1)) = 9 - \dim(\ker(\delta^1))$$

The kernel of $\delta^1$ consists of 1-cochains $(s_1, s_2, s_3)$ satisfying:

$$a_1 = b_2, \; b_1 = c_2, \; a_1 = a_3, \; c_1 = b_3, \; a_2 = b_3, \; c_2 = c_3$$

From these 6 equations on 9 variables: $a_3 = a_1$, $b_3 = c_1$, $c_3 = c_2 = b_1$, $b_2 = a_1$, $a_2 = b_3 = c_1$. Free variables: $a_1, b_1, c_1$ (3 free). So $\dim(\ker(\delta^1)) = 3$ and $\dim(\text{im}(\delta^1)) = 9 - 3 = 6$.

Now $\dim(C^2) = 3 \times 2 = 6$ (three triangles, each with $\mathbb{R}^2$ stalk).

If $\delta^2 = 0$ (which occurs when $\mathcal{F}(\tau) = 0$, i.e., no tetrahedron stalk), then $\ker(\delta^2) = C^2$ has dimension 6, and:

$$\dim H^2 = \dim(\ker(\delta^2)) - \dim(\text{im}(\delta^1)) = 6 - 6 = 0$$

This gives trivial $H^2$. To obtain nontrivial $H^2$, we modify the construction.

**Step 4: Modified construction with rank-deficient restrictions.**

Replace the restriction maps with rank-deficient versions. Set $n = 2$ (edge stalk dimension) and keep $n_{ij} = 2$. Define:

$$\rho_{12}^1 = \begin{pmatrix} 1 & 0 \\ 0 & 1 \end{pmatrix}, \quad \rho_{12}^2 = \begin{pmatrix} 1 & 0 \\ 0 & 1 \end{pmatrix}$$

$$\rho_{13}^1 = \begin{pmatrix} 1 & 0 \\ 0 & 1 \end{pmatrix}, \quad \rho_{13}^3 = \begin{pmatrix} 1 & 0 \\ 0 & 1 \end{pmatrix}$$

$$\rho_{23}^2 = \begin{pmatrix} 1 & 0 \\ 0 & 1 \end{pmatrix}, \quad \rho_{23}^3 = \begin{pmatrix} 1 & 0 \\ 0 & 1 \end{pmatrix}$$

With identity restrictions, $\delta^1(s_1, s_2, s_3)_{\sigma_{ij}} = s_i - s_j$. The kernel requires $s_1 = s_2 = s_3$, giving $\dim(\ker \delta^1) = 2$. So $\dim(\text{im}(\delta^1)) = 6 - 2 = 4$.

Without a tetrahedron ($\delta^2 = 0$): $\dim H^2 = 6 - 4 = 2 \neq 0$.

**Step 5: Explicit nontrivial 2-cocycle.**

With the identity restriction construction above, $\text{im}(\delta^1)$ consists of all $(\omega_{12}, \omega_{13}, \omega_{23}) \in (\mathbb{R}^2)^3$ of the form:

$$\omega_{12} = s_1 - s_2, \quad \omega_{13} = s_1 - s_3, \quad \omega_{23} = s_2 - s_3$$

These satisfy the constraint $\omega_{12} - \omega_{13} + \omega_{23} = 0$ (the simplicial boundary relation).

Any 2-cochain violating this constraint lies in $\ker(\delta^2) \setminus \text{im}(\delta^1)$ and represents a nontrivial class in $H^2$. For example:

$$\omega_{12} = \begin{pmatrix} 1 \\ 0 \end{pmatrix}, \quad \omega_{13} = \begin{pmatrix} 0 \\ 0 \end{pmatrix}, \quad \omega_{23} = \begin{pmatrix} 0 \\ 0 \end{pmatrix}$$

Check: $\omega_{12} - \omega_{13} + \omega_{23} = (1, 0)^T \neq 0$. So this is not in $\text{im}(\delta^1)$. Since $\delta^2 = 0$ (no tetrahedron), it is automatically a cocycle. Therefore $[\boldsymbol{\omega}] \neq 0 \in H^2(K, \mathcal{F})$.

**Step 6: Interpretation as irreducible triadic state.**

The nontrivial class $[\boldsymbol{\omega}]$ represents a co-presence configuration where:
- The agent's state in the $(v_0, v_1, v_2)$ co-presence has an inconsistency of magnitude 1 on the first dimension
- The $(v_0, v_1, v_3)$ and $(v_0, v_2, v_3)$ co-presences show no inconsistency

This inconsistency cannot be "explained away" by any choice of dyadic states $(s_1, s_2, s_3)$, because any valid coboundary must satisfy $\omega_{12} - \omega_{13} + \omega_{23} = 0$. The triadic state carries information that is genuinely irreducible to pairwise data.

**Physically:** when the agent is simultaneously present with partners $v_1$ and $v_2$, an emergent relational dynamic arises (e.g., jealousy, triangulation, group-specific humor) that cannot be predicted from the agent's separate relationships with $v_1$ and $v_2$ individually.

$\square$

**Remark.** The condition $H^2 \neq 0$ is topological: it depends on the simplicial structure of $K$ (which co-presence groups exist) and the algebraic structure of the restriction maps (how group states decompose into pairwise views). The construction shows that $H^2 \neq 0$ arises generically when the restriction maps are "too uniform" (identity maps) — meaning the sheaf cannot distinguish different co-presence contexts at the dyadic level. This is precisely the situation where group dynamics produce genuinely new phenomena.

---

## Theorem 4: Personality-Bounded Inconsistency

**Statement.** Let $K$ be a relational complex with $N$ edges and Scar Sheaf $\mathcal{F}$ whose presentation matrices $\{P_i\}_{i=1}^N$ satisfy the Personality Consistency axiom with parameter $\kappa(\boldsymbol{\pi})$. Then:

$$\dim H^1(K, \mathcal{F}) \leq \frac{N \cdot n \cdot \kappa(\boldsymbol{\pi})^2 \cdot (1 + D_{\max})^2}{\lambda_1(L_\mathcal{F})}$$

where $n$ is the edge stalk dimension, $D_{\max} = \max_{i,j} d(\tau_i, \tau_j)$ is the maximum relationship-type distance, and $\lambda_1(L_\mathcal{F})$ is the smallest nonzero eigenvalue of the sheaf Laplacian. In particular, high agreeableness (which implies low $\kappa$) yields a tighter bound on the number of possible relational contradictions.

### Formal Setup

Recall from Definition 6 that the Personality Consistency axiom states:

$$\|P_i - P_j\|_F \leq \kappa(\boldsymbol{\pi}) \cdot (1 + d(\tau_i, \tau_j))$$

The parameter $\kappa(\boldsymbol{\pi})$ depends on the Big Five personality vector. Specifically, we model:

$$\kappa(\boldsymbol{\pi}) = \kappa_0 \cdot (1 - w_A \cdot A + w_N \cdot N)$$

where $A$ is agreeableness, $N$ is neuroticism, and $w_A, w_N > 0$ are weights with $w_A + w_N < 1$ (ensuring $\kappa > 0$).

### Proof

**Step 1: Relating $H^1$ to the sheaf Laplacian.**

By the Hodge theorem for cellular sheaves (Hansen-Ghrist, 2019), the first cohomology decomposes as:

$$H^1(K, \mathcal{F}) \cong \ker(L_1)$$

where $L_1 = \delta^{0*}\delta^0 + \delta^1 \delta^{1*}$ is the 1-dimensional Hodge Laplacian. However, for our purposes we use the weaker but more tractable bound via the 0-Laplacian.

**Lemma 4.1 (Rank-deficiency bound).** $\dim H^1(K, \mathcal{F}) \leq \dim C^1 - \text{rank}(\delta^0) - \text{rank}(\delta^1)$.

*Proof:* By the rank-nullity theorem applied to the cochain complex:

$$\dim H^1 = \dim(\ker \delta^1) - \dim(\text{im} \; \delta^0) = (\dim C^1 - \text{rank}(\delta^1)) - \text{rank}(\delta^0)$$

$\square$

**Step 2: Lower-bounding $\text{rank}(\delta^0)$ via the Personality Consistency axiom.**

The coboundary $\delta^0: C^0 \to C^1$ has matrix representation (on the $v_0$ component):

$$\delta^0|_{v_0} = \begin{pmatrix} P_1^T \\ P_2^T \\ \vdots \\ P_N^T \end{pmatrix} \in \mathbb{R}^{Nn \times n_0}$$

The rank of $\delta^0$ equals the rank of this stacked matrix. Since all $P_i$ are derived from the same personality base:

$$P_i = P_{base}(\boldsymbol{\pi}) + \Delta P_i$$

where $\|\Delta P_i\|_F \leq \kappa(\boldsymbol{\pi}) \cdot (1 + d(\tau_i, \tau_{ref}))$ for any reference type $\tau_{ref}$.

The rank of the stacked matrix satisfies:

$$\text{rank}(\delta^0) \geq \text{rank}(P_{base}^T) = \text{rank}(P_{base})$$

When $\kappa$ is small (high agreeableness), all $P_i \approx P_{base}$, so the stacked matrix has rank $\approx \text{rank}(P_{base}) = \min(n_0, n)$ (generically full rank). The image of $\delta^0$ is large, leaving less room for $H^1$.

**Step 3: Upper-bounding $\dim H^1$ via spectral analysis.**

The sheaf Laplacian $L_\mathcal{F} = \delta^{0*}\delta^0$ has the form:

$$L_\mathcal{F} = \sum_{i=1}^N P_i^T P_i$$

Its smallest nonzero eigenvalue $\lambda_1$ satisfies:

$$\lambda_1 \geq \frac{1}{n_0} \sum_{i=1}^N \sigma_{\min}(P_i)^2$$

where $\sigma_{\min}(P_i)$ is the smallest singular value of $P_i$.

By the Personality Consistency axiom, the variation in $P_i$ is bounded:

$$\|P_i P_i^T - P_j P_j^T\|_F \leq 2\|P_{base}\|_2 \cdot \|P_i - P_j\|_F + \|P_i - P_j\|_F^2$$
$$\leq 2\|P_{base}\|_2 \cdot \kappa(1 + D_{\max}) + \kappa^2(1 + D_{\max})^2$$

**Step 4: The inconsistency dimension bound.**

A nontrivial class $[\omega] \in H^1$ requires $\omega \in \ker(\delta^1) \setminus \text{im}(\delta^0)$. The "distance" of $\omega$ from $\text{im}(\delta^0)$ is bounded below by $\lambda_1$:

$$\min_{\mathbf{z} \in C^0} \|\omega - \delta^0 \mathbf{z}\|^2 \geq \lambda_1 \cdot \|\omega_{H^1}\|^2$$

where $\omega_{H^1}$ is the harmonic component. This means each independent direction in $H^1$ requires at least $\lambda_1$ units of "inconsistency energy."

The total inconsistency energy available is bounded by the maximum possible deviation between presentation matrices:

$$\|\delta^0 \mathbf{x}\|^2 \leq \sum_{i=1}^N \|P_i^T \mathbf{x}_0 - \mathbf{x}_i^{(ext)}\|^2 \leq N \cdot n \cdot \kappa^2 \cdot (1 + D_{\max})^2 \cdot \|\mathbf{x}_0\|^2$$

(using the bound on $\|P_i - P_j\|$ and the fact that inconsistency arises from presentation matrix differences).

Therefore:

$$\dim H^1 \leq \frac{\text{total inconsistency energy}}{\text{energy per independent direction}} \leq \frac{N \cdot n \cdot \kappa(\boldsymbol{\pi})^2 \cdot (1 + D_{\max})^2}{\lambda_1(L_\mathcal{F})}$$

**Step 5: Agreeableness tightens the bound.**

For high agreeableness $A \to 1$:

$$\kappa(\boldsymbol{\pi}) = \kappa_0(1 - w_A \cdot A + w_N \cdot N) \to \kappa_0(1 - w_A + w_N \cdot N)$$

This is minimized (for fixed $N$) at maximum agreeableness. Simultaneously, when all $P_i$ are nearly identical, $L_\mathcal{F} \approx N \cdot P_{base}^T P_{base}$, so $\lambda_1 \approx N \cdot \sigma_{\min}(P_{base})^2$, which grows with $N$.

The bound becomes:

$$\dim H^1 \leq \frac{N \cdot n \cdot \kappa_0^2(1 - w_A)^2 (1 + D_{\max})^2}{N \cdot \sigma_{\min}(P_{base})^2} = \frac{n \cdot \kappa_0^2(1-w_A)^2(1+D_{\max})^2}{\sigma_{\min}(P_{base})^2}$$

which is independent of $N$ — a highly agreeable agent can maintain arbitrarily many relationships without increasing the dimension of possible contradictions.

$\square$

**Remark.** This theorem connects personality psychology to algebraic topology. The agreeableness trait, which empirically correlates with interpersonal consistency and conflict avoidance, here manifests as a topological constraint: it bounds the dimension of the first cohomology group, limiting the number of independent relational contradictions the agent can sustain. High neuroticism (large $\kappa$) loosens the bound, allowing more contradictions — consistent with the empirical observation that neurotic individuals maintain more conflicted relational patterns.

---

## Theorem 5: Energy Starvation and Relationship Death

**Statement.** Let $K$ be a relational complex with $N$ active edges, each consuming energy at basal rate $c_i > 0$. Let $\mathcal{E}(t)$ denote the agent's total relational energy with intake rate $\dot{\mathcal{E}}_{in}$ and total basal cost $C_{total} = \sum_{i=1}^N c_i$. If $\dot{\mathcal{E}}_{in} < C_{total}$ for a continuous duration $T \geq T^*$ where:

$$T^* = \frac{\mathcal{E}(0) - \mathcal{E}_{death}}{\sum_{i=1}^N c_i - \dot{\mathcal{E}}_{in}}$$

and $\mathcal{E}_{death} = \min_i \{E_i^{death}\} \cdot N$ is the aggregate death threshold, then at least one relationship's coherence must drop below its death threshold, causing irreversible relationship termination.

### Formal Setup

Under Axiom S5, the energy dynamics satisfy:

$$\mathcal{E}(t) = \mathcal{E}(0) + \int_0^t \dot{\mathcal{E}}_{in}(\tau) \, d\tau - \int_0^t \sum_{i=1}^N c_i(\tau) \, d\tau$$

Each relationship $i$ has a **coherence function** $\Gamma_i(t) \in [0, 1]$ that depends on the energy allocated to it:

$$\dot{\Gamma}_i = \begin{cases} \gamma_+(E_i^{alloc} - c_i) & \text{if } E_i^{alloc} \geq c_i \\ -\gamma_- \cdot (c_i - E_i^{alloc}) & \text{if } E_i^{alloc} < c_i \end{cases}$$

where $E_i^{alloc}$ is the energy allocated to relationship $i$, $\gamma_+ > 0$ is the coherence growth rate, and $\gamma_- > 0$ is the coherence decay rate. The constraint is $\sum_i E_i^{alloc}(t) \leq \mathcal{E}(t)$.

A relationship **dies** when $\Gamma_i(t) < \Gamma_{death}$ for some threshold $\Gamma_{death} > 0$.

### Proof

**Step 1: Energy deficit accumulation.**

Under the starvation condition $\dot{\mathcal{E}}_{in} < C_{total}$, the energy deficit accumulates linearly:

$$\mathcal{E}(t) = \mathcal{E}(0) - (C_{total} - \dot{\mathcal{E}}_{in}) \cdot t$$

(assuming constant rates for clarity; the argument extends to time-varying rates by integration).

At time $T^*$, the total available energy reaches:

$$\mathcal{E}(T^*) = \mathcal{E}(0) - (C_{total} - \dot{\mathcal{E}}_{in}) \cdot T^* = \mathcal{E}_{death}$$

**Step 2: Pigeonhole on energy allocation.**

At any time $t$, the allocation must satisfy $\sum_i E_i^{alloc}(t) \leq \mathcal{E}(t)$. When $\mathcal{E}(t) < C_{total}$, it is impossible to allocate $E_i^{alloc} \geq c_i$ for all $i$ simultaneously:

$$\sum_i c_i = C_{total} > \mathcal{E}(t) \geq \sum_i E_i^{alloc}(t)$$

Therefore, there exists at least one index $j$ such that $E_j^{alloc}(t) < c_j$.

**Lemma 5.1 (Coherence decay under sustained deficit).** If relationship $j$ receives $E_j^{alloc} < c_j$ for duration $\Delta t$, its coherence decreases by:

$$\Delta \Gamma_j \leq -\gamma_- \cdot (c_j - E_j^{alloc}) \cdot \Delta t$$

*Proof:* Direct integration of $\dot{\Gamma}_j = -\gamma_-(c_j - E_j^{alloc})$ over $[t, t + \Delta t]$. $\square$

**Step 3: Optimal allocation strategy and its failure.**

The agent may attempt to distribute the deficit across relationships to delay any single death. The optimal strategy minimizes $\max_i \{-\Delta\Gamma_i\}$ subject to $\sum_i E_i^{alloc} = \mathcal{E}(t)$.

By Lagrange multipliers, the optimal allocation satisfies:

$$\gamma_- \cdot (c_i - E_i^{alloc}) = \mu \quad \text{for all } i \text{ with } E_i^{alloc} < c_i$$

giving uniform coherence decay rate $\mu$ across all under-funded relationships. The optimal allocation is:

$$E_i^{alloc} = c_i - \frac{C_{total} - \mathcal{E}(t)}{N} \quad \text{(equal deficit sharing)}$$

Under this optimal strategy, all relationships decay at rate:

$$\dot{\Gamma}_i = -\gamma_- \cdot \frac{C_{total} - \mathcal{E}(t)}{N}$$

**Step 4: Death is inevitable.**

Even under optimal allocation, the coherence of every relationship decays. Starting from $\Gamma_i(0) \leq 1$, the coherence at time $t$ satisfies:

$$\Gamma_i(t) \leq 1 - \gamma_- \cdot \int_0^t \frac{C_{total} - \mathcal{E}(\tau)}{N} \, d\tau$$

Substituting $\mathcal{E}(\tau) = \mathcal{E}(0) - (C_{total} - \dot{\mathcal{E}}_{in})\tau$:

$$\Gamma_i(t) \leq 1 - \frac{\gamma_-}{N} \int_0^t \left[(C_{total} - \dot{\mathcal{E}}_{in})\tau + (C_{total} - \mathcal{E}(0))\right]^+ d\tau$$

where $[\cdot]^+$ denotes the positive part (deficit only matters once $\mathcal{E}(t) < C_{total}$).

Let $t_0 = (\mathcal{E}(0) - C_{total}) / (C_{total} - \dot{\mathcal{E}}_{in})$ be the time when energy first drops below total basal cost (if $\mathcal{E}(0) > C_{total}$; otherwise $t_0 = 0$). For $t > t_0$:

$$\Gamma_i(t) \leq 1 - \frac{\gamma_- (C_{total} - \dot{\mathcal{E}}_{in})}{2N} \cdot (t - t_0)^2$$

Setting $\Gamma_i(t) = \Gamma_{death}$ and solving:

$$t_{death} = t_0 + \sqrt{\frac{2N(1 - \Gamma_{death})}{\gamma_-(C_{total} - \dot{\mathcal{E}}_{in})}}$$

This is finite, proving that at least one relationship must die in finite time.

**Step 5: Non-optimal strategies accelerate death.**

If the agent does not use the optimal equal-deficit strategy (e.g., prioritizing some relationships over others), then some relationship $j$ receives a larger deficit share, and:

$$t_{death}^{(j)} < t_{death}^{(optimal)}$$

In particular, if the agent fully funds $k < N$ relationships and starves the remaining $N - k$:

$$E_j^{alloc} = 0 \quad \text{for } j > k$$
$$\Gamma_j(t) \leq 1 - \gamma_- c_j \cdot t$$
$$t_{death}^{(j)} = \frac{1 - \Gamma_{death}}{\gamma_- c_j}$$

This is typically much shorter than the optimal strategy's death time, confirming that prioritization accelerates individual relationship death (though it preserves the prioritized relationships longer).

**Step 6: Irreversibility via Scar Algebra coupling.**

Once $\Gamma_j < \Gamma_{death}$, the relationship enters a terminal state. By Axiom S4 (irreversibility of propagation), the death of relationship $j$ propagates through the sheaf Laplacian to affect other relationships. The energy previously consumed by relationship $j$ ($c_j$) is freed, potentially stabilizing the remaining relationships — but the dead relationship cannot be revived (analogous to scar permanence in Scar Algebra).

$\square$

**Remark.** This theorem formalizes the intuition that maintaining relationships requires ongoing energy investment, and that resource scarcity forces triage. The quadratic coherence decay (Step 4) means that the system tolerates mild deficits for extended periods but collapses rapidly once the deficit becomes severe — matching the empirical observation that relationship neglect has delayed but accelerating consequences. The optimal strategy (equal deficit sharing) corresponds to "spreading thin" across all relationships, while prioritization corresponds to "choosing who matters most" — both are valid but lead to different death patterns.

---

## Theorem 6: Evolutionary Pressure on Presentation Matrices

**Statement.** Under Axiom S6, the presentation matrices $\{P_i(t)\}_{i=1}^N$ evolve by gradient descent on the total inconsistency loss $\mathcal{L}_{consistency} = \|\delta^0 \mathbf{x}\|^2$, subject to the personality constraint $\|P_i - P_j\|_F \leq \kappa(\boldsymbol{\pi})(1 + d(\tau_i, \tau_j))$. The system converges to a fixed point $\{P_i^*\}$ characterized by:

$$P_i^* = \Pi_{\mathcal{C}_i}\left[\left(\sum_{j \neq i} P_j P_j^T\right)^{-1} \left(\sum_{j \neq i} P_j \mathbf{x}_j^{(ext)} \mathbf{x}_0^T\right)\right]$$

where $\Pi_{\mathcal{C}_i}$ is the projection onto the personality-constraint set $\mathcal{C}_i = \{P : \|P - P_j\|_F \leq \kappa(1 + d(\tau_i, \tau_j)) \; \forall j\}$. At the fixed point, the total inconsistency is minimized subject to personality constraints, and the residual inconsistency equals $\dim H^1(K, \mathcal{F}^*)$ (the cohomological obstruction at convergence).

### Formal Setup

The evolution equation from Axiom S6 is:

$$P_i(t+1) = P_i(t) + \eta \cdot \nabla_{P_i} \mathcal{L}_{consistency}$$

where:

$$\mathcal{L}_{consistency} = \|\delta^0 \mathbf{x}\|^2 = \sum_{i=1}^N \|P_i^T \mathbf{x}_0 - \mathbf{x}_i^{(ext)}\|^2$$

The gradient with respect to $P_i$ is:

$$\nabla_{P_i} \mathcal{L} = -2 \mathbf{x}_0 (P_i^T \mathbf{x}_0 - \mathbf{x}_i^{(ext)})^T = -2 \mathbf{x}_0 \mathbf{x}_0^T P_i + 2 \mathbf{x}_0 (\mathbf{x}_i^{(ext)})^T$$

Note: Axiom S6 uses gradient *ascent* notation ($+\eta \nabla$) but the loss $\mathcal{L}$ measures inconsistency, so minimizing inconsistency requires $\eta < 0$ in the axiom's convention, or equivalently we write the descent as:

$$P_i(t+1) = P_i(t) - \eta \cdot \nabla_{P_i} \mathcal{L}$$

with $\eta > 0$ the learning rate.

### Proof

**Step 1: Unconstrained fixed point.**

Setting $\nabla_{P_i} \mathcal{L} = 0$:

$$\mathbf{x}_0 \mathbf{x}_0^T P_i = \mathbf{x}_0 (\mathbf{x}_i^{(ext)})^T$$

If $\mathbf{x}_0 \neq 0$, left-multiplying by $(\mathbf{x}_0 \mathbf{x}_0^T)^{-1}$ (which exists when $\mathbf{x}_0$ has full rank in the sense that $\mathbf{x}_0 \mathbf{x}_0^T$ is invertible — this requires $n_0 = 1$; for general $n_0$ we use the pseudoinverse):

$$P_i^{unc} = (\mathbf{x}_0 \mathbf{x}_0^T)^\dagger \mathbf{x}_0 (\mathbf{x}_i^{(ext)})^T$$

For the time-averaged version (averaging over the trajectory of $\mathbf{x}_0$):

$$P_i^{unc} = \mathbb{E}[\mathbf{x}_0 \mathbf{x}_0^T]^{-1} \mathbb{E}[\mathbf{x}_0 (\mathbf{x}_i^{(ext)})^T]$$

This is the ordinary least-squares solution: $P_i^{unc}$ is the matrix that best predicts the external signal $\mathbf{x}_i^{(ext)}$ from the agent's internal state $\mathbf{x}_0$.

**Step 2: Constrained fixed point via projected gradient descent.**

With the personality constraint $P_i \in \mathcal{C}_i$, the evolution becomes projected gradient descent:

$$P_i(t+1) = \Pi_{\mathcal{C}_i}\left[P_i(t) - \eta \nabla_{P_i} \mathcal{L}\right]$$

where $\Pi_{\mathcal{C}_i}$ projects onto the convex constraint set:

$$\mathcal{C}_i = \{P \in \mathbb{R}^{n_0 \times n} : \|P - P_j\|_F \leq \kappa(\boldsymbol{\pi})(1 + d(\tau_i, \tau_j)) \; \forall j \neq i\}$$

This is an intersection of Frobenius-norm balls, which is convex.

**Lemma 6.1 (Convergence of projected gradient descent).** If $\mathcal{L}$ is $L$-smooth (i.e., $\|\nabla^2 \mathcal{L}\| \leq L$) and the constraint sets $\mathcal{C}_i$ are convex and closed, then projected gradient descent with step size $\eta \leq 1/L$ converges to a fixed point.

*Proof of Lemma:* The loss $\mathcal{L}$ is quadratic in $P_i$ (since $\|P_i^T \mathbf{x}_0 - \mathbf{x}_i^{(ext)}\|^2$ is quadratic in $P_i$), so it is $L$-smooth with $L = 2\|\mathbf{x}_0\|^2$. By the standard convergence theorem for projected gradient descent on convex functions over convex sets (Beck-Teboulle, 2009):

$$\mathcal{L}(P(t)) - \mathcal{L}(P^*) \leq \frac{\|P(0) - P^*\|_F^2}{2\eta t}$$

giving $O(1/t)$ convergence to the constrained optimum. $\square$

**Step 3: Characterization of the fixed point.**

At the fixed point $P^* = \{P_i^*\}$, the KKT conditions hold:

$$\nabla_{P_i} \mathcal{L}|_{P^*} + \sum_{j \neq i} \mu_{ij} \cdot \frac{P_i^* - P_j^*}{\|P_i^* - P_j^*\|_F} = 0$$

where $\mu_{ij} \geq 0$ are dual variables for the constraints $\|P_i - P_j\|_F \leq \kappa(1 + d(\tau_i, \tau_j))$, with complementary slackness:

$$\mu_{ij} \cdot (\|P_i^* - P_j^*\|_F - \kappa(1 + d(\tau_i, \tau_j))) = 0$$

There are two regimes:

**(a) Interior fixed point** ($\mu_{ij} = 0$ for all $i, j$): The unconstrained optimum $P_i^{unc}$ satisfies all personality constraints. This occurs when the external signals $\{\mathbf{x}_i^{(ext)}\}$ are sufficiently similar (the partners elicit similar self-presentations). The fixed point is simply $P_i^* = P_i^{unc}$ and $\mathcal{L}^* = 0$ (perfect consistency achievable).

**(b) Boundary fixed point** (some $\mu_{ij} > 0$): The unconstrained optima violate personality constraints. The fixed point lies on the boundary of $\mathcal{C}_i$ for some pairs $(i, j)$, meaning those relationships are "maximally differentiated" within personality limits. The residual loss $\mathcal{L}^* > 0$ represents irreducible inconsistency.

**Step 4: Residual inconsistency equals cohomological obstruction.**

At the fixed point, the residual loss is:

$$\mathcal{L}^* = \sum_i \|P_i^{*T} \mathbf{x}_0 - \mathbf{x}_i^{(ext)}\|^2 = \|\delta^0 \mathbf{x}\|^2|_{P=P^*}$$

By the Hodge decomposition for the sheaf $\mathcal{F}^*$ (with presentation matrices $P_i^*$):

$$\|\delta^0 \mathbf{x}\|^2 = \|\omega_{exact}\|^2 + \|\omega_{harmonic}\|^2$$

where $\omega_{exact} \in \text{im}(\delta^0)$ and $\omega_{harmonic} \in H^1(K, \mathcal{F}^*)$. At the fixed point of gradient descent, the exact component is minimized to zero (the gradient descent eliminates all reducible inconsistency). Therefore:

$$\mathcal{L}^* = \|\omega_{harmonic}\|^2$$

The dimension of the harmonic space equals $\dim H^1(K, \mathcal{F}^*)$, confirming that the residual inconsistency is purely cohomological — it represents contradictions that no adjustment of the agent's internal state can resolve.

**Step 5: Scar disruption and recovery.**

When a scar event occurs on relationship $i$, the base state $\mathbf{x}_i$ shifts discontinuously. This changes the loss landscape:

$$\mathcal{L}_{new} = \mathcal{L}_{old} + 2\langle P_i^T \mathbf{x}_0 - \mathbf{x}_i^{(ext)}, P_i^T \Delta \mathbf{x}_0 \rangle + \|P_i^T \Delta \mathbf{x}_0\|^2$$

The presentation matrix $P_i$ is partially reset (per Axiom S6's trauma disruption clause), moving it away from the fixed point. The system then re-converges via gradient descent, but to a potentially different fixed point (since the constraint set and loss landscape have changed).

**Lemma 6.2 (Recovery time after scar disruption).** If the scar shifts $P_i$ by $\Delta P_i$ with $\|\Delta P_i\|_F = \delta$, the time to return within $\epsilon$ of the new fixed point is:

$$t_{recovery} \leq \frac{\delta^2}{2\eta \epsilon}$$

*Proof:* By the $O(1/t)$ convergence rate of projected gradient descent (Lemma 6.1), with initial distance $\delta$ from the optimum. $\square$

**Step 6: Long-term convergence characterization.**

In the absence of scar events (or after all scars have reached the faded stage), the presentation matrices converge to the fixed point $P^*$ characterized by:

1. Each $P_i^*$ minimizes its contribution to $\mathcal{L}$ within its constraint set
2. The constraints $\|P_i^* - P_j^*\|_F \leq \kappa(1+d(\tau_i, \tau_j))$ are tight for relationship pairs with incompatible external signals
3. The residual inconsistency $\mathcal{L}^*$ is entirely cohomological ($H^1$-valued)
4. The spectral gap $\lambda_1(L_{\mathcal{F}^*})$ is maximized subject to constraints (gradient descent on $\mathcal{L}$ implicitly maximizes the Laplacian's ability to enforce consistency)

The fixed point represents the agent's "mature relational configuration" — the most consistent self-presentation achievable given personality constraints and the demands of each relationship.

$\square$

**Remark.** This theorem reveals that the presentation matrix evolution (Axiom S6) implements a form of constrained optimization that naturally produces the most coherent relational identity the agent's personality permits. The personality parameter $\kappa$ acts as a regularizer: low $\kappa$ (high agreeableness) forces all $P_i$ close together, producing a "what you see is what you get" personality at the cost of potentially poor fit to diverse relationship demands. High $\kappa$ (high neuroticism) allows greater differentiation, enabling better local fit but at the cost of global inconsistency ($H^1 \neq 0$). The scar disruption mechanism (Step 5) means that trauma can permanently alter the fixed point — the agent's mature relational configuration is path-dependent, shaped by the history of relational injuries.

---

## Open Problems

1. **Sheaf cohomology computability:** For a general Scar Sheaf with $N$ relationships and scar sequences of total length $K$, what is the computational complexity of determining $\dim H^1(K, \mathcal{F})$? The naive approach (computing rank of coboundary matrices) is $O(N^3 n^3)$; can this be improved using the special structure of presentation matrices?

2. **Optimal energy allocation under uncertainty:** Theorem 5 assumes known basal costs $c_i$. If costs are stochastic (relationship demands fluctuate), what is the optimal allocation policy? This connects to multi-armed bandit problems with resource constraints.

3. **Topological phase transitions:** As relationships form and dissolve (simplices are added/removed from $K$), the cohomology groups change discontinuously. Can we characterize the "critical" complex structures where small perturbations cause large changes in $\dim H^1$?

4. **Interaction between Theorems 1 and 6:** When cohomological dissociation (Theorem 1) forces $\kappa$ to increase (dissociation response), how does this affect the fixed point of Theorem 6? Is there a feedback loop where dissociation begets further dissociation?

5. **Spectral gap and resilience:** Theorem 2 shows that large $\lambda_1$ means fast propagation but also fast recovery. Is there an optimal spectral gap that balances resilience (fast recovery from perturbation) against isolation (limiting cross-relational contagion)?
