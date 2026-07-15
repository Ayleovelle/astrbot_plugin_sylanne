# v3core Shadow Cognitive Architecture Design

**Date:** 2026-07-15

**Status:** Approved design; pending implementation plan

## 1. Decision

Sylanne will gain a new plugin-owned `v3core` cognitive architecture as a fully isolated shadow reserve. This is a clean redesign, not an in-place rewrite of `v2core` and not a collection of renamed v2 formulas.

The approved topology is:

```text
serial control skeleton
  + parallel deterministic / spiking / continuous perception paths
  + local LIF and reward-gated STDP microcircuits
  + Global Workspace competition and broadcast
  + finite-action Active Inference
  + one EffectCommitter boundary
```

The current v2 path remains the only authority for user-visible behavior. v3 runs automatically in grey builds as a stateful shadow, is not exposed as a configuration-page selector, and cannot reply, mutate prompts, call tools, tick the body, or write v2 memory/history.

The vendored SylannEngine tree under `sylanne_alpha/_engine/**` is read-only. v3 consumes only stable plugin-facing snapshots, especially `BodySnapshot`; it does not import engine internals or recompute canonical prediction error.

## 2. Goals

1. Replace scattered EMA, threshold, implicit ordering, and string scratch-bus behavior with typed, bounded, testable state transitions.
2. Give SNN, multi-timescale dynamics, Global Workspace, and Active Inference distinct jobs with falsifiable value.
3. Permit aggressive internal emergence while retaining numerical bounds, deterministic replay, session isolation, transactional state commits, and hard failure containment.
4. Run stateful shadow evaluation on real grey traffic without additional LLM/network calls or any change to v2 authority.
5. Preserve enough observability to explain every v3 decision and remove any layer that fails ablation or falsification tests.

## 3. Non-Goals

1. v3 does not become a user-selectable mode in this project.
2. v3 does not execute real actions, tools, replies, memory writes, group operations, or body ticks.
3. v3 does not claim online policy superiority from pure shadow disagreement. Unexecuted counterfactual outcomes are not observable.
4. v3 does not modify or fork the vendored SylannEngine implementation.
5. Virtual SNN ticks are numerical reservoir steps, not claims about millisecond biological time.
6. Existing user-visible v2 defects are not deferred to v3. Group invocation, transactional memory, hesitation repetition, and model-tool exposure remain separate v2 fixes.

## 4. Authority And Isolation

### 4.1 v2 Authority

v2 remains authoritative for:

- provider prompt and request mutation;
- `Reply` construction and realtime sending;
- AstrBot conversation history;
- Sylanne ConversationBuffer and MemorySystem;
- group state and cross-group privacy behavior;
- tool exposure and execution;
- `BodyPort.tick()` and all canonical engine evolution.

v3 may observe immutable projections of these facts. It may not hold live v2 objects or callbacks.

### 4.2 Allowed Shadow Effects

The shadow `EffectCommitter` permits only:

```text
V3_STATE
V3_TRACE
V3_METRIC
```

All `REPLY`, `PROMPT`, `TOOL`, `BODY_TICK`, `ASTRBOT_HISTORY`, `V2_MEMORY`, and `GROUP_WRITE` effects return `SUPPRESSED_SHADOW`.

`EffectBundle` is a closed union defined in `v3core.effects.models`; arbitrary dictionaries, filesystem paths, callbacks, repository handles, or host objects are invalid. `EffectCommitter` is the only component allowed to call the private repository. The supervisor submits one `CommitEnvelope` containing the proposed next state, deterministic trace, and allowed effects. State and `CoreDecisionTrace` are stored in one revision journal record; the pointer advances by CAS only after the complete record is durable. Runtime metrics are derived or emitted idempotently from that record and may be best-effort. Recovery can therefore never expose a committed state revision without its matching deterministic trace.

Migration uses the same committer. Core seed projection and bridge migration coordination cannot write repositories directly.

Deleting every v3 key and file must leave v2 outputs and storage unchanged.

### 4.3 Build Activation

Grey artifacts enable automatic v3 shadow through a build-time internal flag in `v3bridge/build_flags.py`. Source and stable-channel artifacts default to disabled. `scripts/package_plugin.py --channel grey` generates the enabled flag inside the zip without changing the worktree; `--channel stable` generates disabled and requires temporary stable metadata rather than the checked-in grey version. The generated flag replaces the source archive entry, so duplicate paths are invalid. The artifact manifest records channel, metadata version, git commit, generated-file digest, and `payload_digest`. `payload_digest` is SHA-256 over UTF-8-path-sorted archive entries excluding the manifest itself, with each entry framed as unsigned big-endian `u32(path_utf8_byte_len) || path_utf8_bytes || u64(content_len) || uncompressed_entry_bytes`. The whole final zip SHA-256 is written only to an adjacent `.sha256` file. The flag is not declared in `_conf_schema.json` and is not user-selectable in WebUI or a public API.

Under load, the supervisor may degrade or suspend v3 automatically. Such suspension is diagnostic state, not a user setting.

## 5. Package Boundaries

```text
sylanne_alpha/
|-- v3core/                         # pure calculation
|   |-- contracts.py
|   |-- orchestrator.py
|   |-- observation/
|   |   |-- models.py
|   |   `-- encoder.py
|   |-- dynamics/
|   |   |-- models.py
|   |   `-- multiscale.py
|   |-- spiking/
|   |   |-- coding.py
|   |   |-- reservoir.py
|   |   `-- plasticity.py
|   |-- workspace/
|   |   |-- models.py
|   |   `-- competition.py
|   |-- inference/
|   |   |-- models.py
|   |   `-- active.py
|   |-- expression/
|   |   `-- policy.py
|   |-- learning/
|   |   |-- modulation.py
|   |   `-- replay.py
|   |-- state/
|   |   |-- models.py
|   |   |-- transition.py
|   |   `-- seed.py               # pure SeedFrame -> initial V3State
|   |-- effects/
|   |   `-- models.py
|   `-- trace/
|       `-- models.py
`-- v3bridge/                       # AstrBot/v2 host boundary
    |-- observation_adapter.py
    |-- actual_action.py
    |-- turn_registry.py
    |-- shadow_supervisor.py
    |-- runtime_telemetry.py
    |-- comparator.py
    |-- migration_coordinator.py
    |-- _state_repository.py       # private; EffectCommitter is its only caller
    |-- effect_committer.py
    |-- memory_view_adapter.py
    `-- group_view_adapter.py
```

`v3core` must not import AstrBot, `v2core`, or `_engine`. Compatibility conversion exists only in `v3bridge`.

## 6. Typed Turn Flow

```text
AstrBot event + frozen v2 facts
  -> ObservationAdapter
  -> CapturedTurn
  -> ShadowJob (bridge deadline/admission only)
  -> TurnEnvelope
  -> ObservationEncoder
  -> DeterministicFeatures
     || SpikeFrame
     || MultiTimescaleFrame
  -> WorkspaceBroadcast
  -> PolicyScorerResult (ActiveInference alias gated by evidence)
  -> DecisionPlan + StateDelta + EffectBundle + CoreDecisionTrace
  -> ShadowSupervisor + RuntimeTelemetry
  -> EffectCommitter(V3_STATE/V3_TRACE/V3_METRIC only)
```

Core contracts:

- `SessionRef`: keyed-HMAC session surrogate, HMAC key ID, and session generation; it contains no raw host session identifier.
- `TurnKey`: plugin-instance ID, `SessionRef`, bridge-owned request nonce, and request attempt.
- `TurnSequence`: lexicographically ordered `(writer_epoch, local_sequence)` token; local values never repeat within one epoch.
- `ComputeProfile`: versioned frozen calculation choices selected before core execution, including SNN enablement, K, STDP enablement, replay mode, last-summary reuse, math backend, and formula/model versions.
- `CapturedTurn`: `TurnHandle`, immutable observation, and `TurnContextClass`, captured without runtime profile or deadline.
- `TurnEnvelope`: `TurnKey`, derived `turn_id`, `TurnSequence`, `ComputeProfile`, deterministic seed, immutable observation, and authoritative `TurnContextClass`; it contains no wall-clock deadline or host object.
- `ShadowJob`: bridge-only job containing the captured turn, actual-action projection, monotonic deadline, and runtime admission metadata.
- `CoreInvocation`: `TurnEnvelope`, immutable base state, and projected actual outcome supplied to pure core computation.
- `ObservationFrame`: text features, `BodyFrame`, `MemoryView`, `GroupView`, previous observed outcome, valid mask.
- `WorkspaceProposal`: action, salience, confidence, feature key, source.
- `WorkspaceBroadcast`: ranked winners, activations, inhibition, refractory contribution.
- `ActionCandidate`: legal action, predictive belief, EFE terms, support.
- `DecisionPlan`: finite action, confidence, expression constraints, reasons; never a host Reply.
- `StateDelta`: all proposed next-state changes; modules never persist directly.
- `EffectBundle`: a closed tagged union of declared v3 effects; no arbitrary path, callback, live object, or raw dict payload.
- `CoreDecisionTrace`: deterministic, canonically serialized explanation used for replay.
- `RuntimeTelemetry`: wall-clock timing, queue/drop/CAS outcome, process identity, and other non-deterministic operations data; excluded from replay digests.

### 6.1 Turn Identity And Concurrency

At plugin initialization, bridge code creates a unique `plugin_instance_id` and durably acquires `writer_epoch`. After epoch acquisition, each `SessionRef` has an in-memory atomic counter starting at zero for that epoch. Allocation increments before returning; allocated and dropped local values are never reused within that session partition. At the request boundary the bridge constructs:

```text
TurnKey(
  plugin_instance_id,
  session_ref,
  bridge_request_nonce,
  request_attempt,
)
```

The bridge never writes `event.extra`, retains a live host event, or otherwise mutates a host object. `HostTurnIdentityRegistry` stores only `TurnHandle(TurnKey, turn_id, TurnSequence)` in plugin-owned bounded state. A verified immutable provider correlation key may index that handle. When no such key exists, request/response integration must retain and return the handle explicitly within its own call chain. If response correlation cannot be proven, shadow execution is skipped and telemetry records `UNMATCHED_RESPONSE`. Object-identity, session FIFO, and text-based guessing are forbidden.

`turn_id` is the canonical hash of `TurnKey`. Random state derives from `(turn_id, state_generation_id, compute_profile_digest, model_revision)`. Raw provider/session identity is absent from core contracts and deterministic traces.

`TurnSequence=(writer_epoch,local_sequence)` is ordered only within its `SessionRef` partition: `(SessionRef,writer_epoch,local_sequence)` is the globally unique ledger key. Different sessions may both allocate `(writer_epoch,1)` without collision. For one session, local sequence may restart at 1 only after a strictly greater epoch is acquired, and dropped values are never reused within an epoch. Delayed-credit adjacency and persistent high-watermarks compare sequences only inside the same `SessionRef`; cross-session interleaving cannot create a gap. This avoids synchronous repository writes on the authoritative request path while preventing reload sequence regression.

`TurnRegistry` is keyed by `TurnKey`, never a single pending slot per session. Entries move through `REQUEST_CAPTURED -> RESPONSE_CLAIMED -> ENQUEUED -> FINALIZED`, reject duplicate response claims, carry TTL, and are cleaned as completed or orphaned. `SequenceLedger` is partitioned by `SessionRef`. Persistent v3 state records `last_committed_turn_sequence` and `last_committed_turn_id`. State commit validates `(writer_epoch, expected_state_generation_id, expected_revision, expected_payload_digest, turn_id, TurnSequence)` within the state owner's `SessionRef`, so duplicate, stale-generation, stale-turn, and revision-conflict outcomes are distinct. Delayed-credit adjacency additionally requires the same session, the same epoch, `next.local_sequence == previous.local_sequence + 1`, and no intervening `DROPPED` ledger entry in that session partition. Reload always censors pending cross-epoch credit.

### 6.2 Host View Boundaries

During G0-G4 there is no policy/tool gateway and no tool action in v3. Shadow does not inspect or modify the host ToolSet.

`MemoryViewAdapter` and `GroupViewAdapter` may project only facts already available to the authoritative turn; they cannot trigger recall, database reads, LLM calls, callbacks, or live-domain access. Their immutable DTOs include provenance, source revision/time, validity mask, and privacy scope.

The bridge enforces the existing cross-group privacy decision before building `GroupView` or any person-scoped memory projection. Core code sees only the resulting scope token and values; it does not import configuration or read a privacy switch. Missing/forbidden facts become invalid fields, never a fallback query.

The bridge also freezes exactly one mutually exclusive `TurnContextClass` from structured host facts:

```text
ADDRESSED = inbound message with verified explicit invocation/reply/wake classification
AMBIENT   = inbound message without explicit addressing
PROACTIVE = no inbound message; scheduler requests an outreach opportunity
IDLE      = no inbound message; maintenance/evaluation only
```

`addressed`, `idle`, and `proactive` observation bits are redundant checked encodings of that enum; `AMBIENT` encodes all three as zero. Contradictory bits or an unprovable context reject the shadow job instead of invoking a default policy.

## 7. Observation Model

`ObservationEncoder` emits `values[36]` and `valid_mask[36]`. Every value is finite and normalized to `[0,1]`.

The exact initial schema is:

| Index | Channel | Raw source/range | Normalization | Missing default |
|---:|---|---|---|---:|
| 0 | body.warmth | `[-1,1]` | `signed(x)` | `0.5` |
| 1 | body.tension | `[0,1]` | `clip(x,0,1)` | `0` |
| 2 | body.repair_pressure | `[0,1]` | `clip(x,0,1)` | `0` |
| 3 | body.intimacy_gravity | `[0,1]` | `clip(x,0,1)` | `0.5` |
| 4 | body.surprise | canonical `[0,1]` | `clip(x,0,1)` | `0` |
| 5 | body.mean_surprise | canonical `[0,1]` | `clip(x,0,1)` | `0.5` |
| 6 | body.precision | canonical `[0,1]` | `clip(x,0,1)` | `0.5` |
| 7 | body.scar | non-negative | `positive(x,1)` | `0` |
| 8 | body.strain | non-negative | `positive(x,1)` | `0` |
| 9 | body.sovereignty | `[0,1]` | `clip(x,0,1)` | `1` |
| 10 | body.exhaustion | non-negative | `positive(x,1)` | `0` |
| 11 | body.expression_drive | signed | `signed(x)` | `0.5` |
| 12 | body.threshold_drift | signed | `signed(x)` | `0.5` |
| 13 | body.epoch | non-negative integer | `tanh(log1p(max(0,x))/4)` | `0` |
| 14 | body.void_pressure | non-negative | `positive(x,2)` | `0` |
| 15 | body.load | non-negative | `positive(x,2)` | `0` |
| 16 | body.plasticity | `[0,1]` | `clip(x,0,1)` | `0.5` |
| 17 | body.boundary_pressure | non-negative | `positive(x,1)` | `0` |
| 18 | text.length | integer chars | `tanh(log1p(max(0,x))/4)` | `0` |
| 19 | text.warm | non-negative density | `density(x)` | `0` |
| 20 | text.cold | non-negative density | `density(x)` | `0` |
| 21 | text.distress | non-negative density | `density(x)` | `0` |
| 22 | text.question | boolean | `0/1` | `0` |
| 23 | text.exclaim | non-negative density | `density(x)` | `0` |
| 24 | text.punct | non-negative density | `density(x)` | `0` |
| 25 | text.valence_cue | signed, unbounded | `0.5+0.5*tanh(x/2)` | `0.5` |
| 26 | text.engagement_cue | `[0,1.3]` by current reader | `clip(x/1.3,0,1)` | `0` |
| 27 | context.addressed | boolean | `0/1` | `0` |
| 28 | context.idle | boolean | `0/1` | `0` |
| 29 | context.proactive | boolean | `0/1` | `0` |
| 30 | context.history_present | boolean | `0/1` | `0` |
| 31 | context.gap_seconds | any numeric | `tanh(log1p(min(max(0,x),86400))/8)` | `0` |
| 32 | previous.SPEAK | actual-action one-hot | `0/1` | `0` |
| 33 | previous.HOLD | actual-action one-hot | `0/1` | `0` |
| 34 | previous.CLARIFY | actual-action one-hot | `0/1` | `0` |
| 35 | previous.REACH | actual-action one-hot | `0/1` | `0` |

Normalization primitives:

```text
signed(x)      = 0.5 + 0.5 * clip(x, -1, 1)
positive(x,k)  = tanh(max(0,x) / k), where the schema fixes k > 0
density(x)     = tanh(max(0,x) / 2)
log_length     = tanh(log1p(max(0,chars)) / 4)
log_gap        = tanh(log1p(min(max(0,gap_seconds), 86400)) / 8)
```

Missing/non-finite input uses the table's semantic neutral or zero-evidence value and clears the matching valid bit. A reliable previous action sets all four action valid bits and exactly one one-hot value; `UNKNOWN` clears all four valid bits. Boolean context contradictions reject the frame because context is an authoritative enum rather than a guessed feature.

`valid_mask` gates every path, not only learning. An invalid observation channel emits no population spikes, contributes no deterministic feature or workspace proposal, is omitted from likelihood/EFE terms, and cannot update thresholds, transition beliefs, preference reward, or any plastic state. Semantic default numbers exist only to keep the fixed-width serialized tensor finite; they are never interpreted as evidence. v1 does not add missingness neurons, so absence itself is not a learned signal.

Canonical `surprise`, `mean_surprise`, and `precision` are copied from `BodySnapshot`. v3 must not calculate a second value with the same semantic name. Derived residuals use an explicitly different name and record their formula in `CoreDecisionTrace`.

## 8. Spiking Path

### 8.1 Population And Time Coding

Defaults:

```text
reservoir neurons N = 96 (fixed in formula v1)
virtual steps K = 24 (the only allowed v1 profiles are 16, 24, or 32)
E/I split = 77/19
recurrent density = 0.08
normalized virtual horizon T = 1
```

Each valid scalar observation is population-coded around centers `{0, 0.5, 1}`. All three encoder units for an invalid channel remain silent for the complete horizon:

```text
q(j,r)  = exp(-(u_j-center_r)^2 / (2*0.25^2))
latency = 1 + floor((K-2)*(1-q))
```

`q >= 0.08` emits one deterministic latency spike. When `q >= 0.75`, emit a second spike at `min(K-1, latency+floor(K/2))` if that index differs from the first. No probabilistic spike insertion is used.

Changing `K` resamples the same normalized horizon rather than changing effective neural time. Let `dt=1/K`. Membrane, trace, and eligibility decays derive from fixed horizon-level time constants:

```text
beta_K        = exp(-dt/tau_membrane)
pre_decay_K   = exp(-dt/tau_pre)
post_decay_K  = exp(-dt/tau_post)
elig_decay_K  = exp(-dt/tau_eligibility)
refractory_K  = max(1, round(K/12))
```

`tau_membrane` is chosen so `beta_24=0.90`; other time constants are versioned alongside it. Therefore 16/24/32-step runs preserve the same horizon-level decay semantics.

### 8.2 LIF Dynamics

```text
I_i[k]     = clip(B_i*z_in[k] + W_i*z[k-1], -3, 3)
v_i[k+1]   = clip(beta_K*v_i[k] + (1-beta_K)*I_i[k], -2, 2)
z_i[k+1]   = 1[v_i[k+1] >= theta_i and refractory_i == 0]
```

After a spike, voltage resets to zero and the refractory counter becomes `refractory_K`. Intrinsic threshold adaptation happens once after the complete horizon, not once per variable-sized step:

```text
theta_i' = clip(theta_i + 0.01*(spike_count_i/K - 0.08), 0.65, 1.35)
```

Excitatory weights remain in `[0,0.35]`, inhibitory weights in `[-0.70,0]`, Dale signs never change, self-loops are forbidden, and each neuron's incoming absolute weight sum is at most 1.2.

The path outputs firing rate, first-spike latency, spike counts, and a fixed 16-dimensional pooled summary.

### 8.3 Reward-Gated STDP

Only E-to-E synapses are plastic. Per virtual step, using the K-adjusted decays above:

```text
pre_j  = clip(pre_decay_K*pre_j + z_j, 0, 3)
post_i = clip(post_decay_K*post_i + z_i, 0, 3)
e_ij   = clip(
           elig_decay_K*e_ij
           + z_i*pre_j(previous)
           - 1.05*z_j*post_i(previous),
           -3, 3
         )
```

At the end of turn `t`, store one bounded `PendingOutcome` containing:

```text
TurnKey(t), TurnSequence(t), shadow_action, projected_actual_action
stdp_credit_enabled, optional_packed_eligibility(t), expiry_turn_sequence
preference_revision, preference_digest, c[8], V_C[8], reward_scale
preference_log_terms_before[8], outcome_projector_revision
predictive_mu_actual[8], predictive_V_actual[8], likelihood_R_actual[8]
```

`PendingOutcome` is created only for a committed turn with a known projected actual action. It records `stdp_credit_enabled=true` and packs eligibility only when turn `t` used an STDP-enabled `ComputeProfile`; otherwise the eligibility field is absent. A shadow/actual mismatch may still retain the outcome for actual-action transition and baseline learning, but can never pass the STDP credit gate. The per-dimension before terms freeze the density needed for later settlement; the predictive and likelihood arrays freeze the actual-action posterior prior. Current preferences or action-model parameters at `t+1` can never retroactively change credit for `t`. Eligibility from turn `t+1` does not replace the pending tensor.

Only the immediately consecutive, accepted observation at `t+1` may settle it. Section 11.2 defines `OutcomeFrame y`, its mask, and the posterior `p(s'|y',s,a)`. For each valid outcome dimension, settlement uses the frozen preference density:

```text
post_term_i = E_{s'_i ~ posterior_i}[log Normal(s'_i; c_i, V_C_i)]
            = -0.5 * (
                log(2*pi*V_C_i)
                + ((posterior_mean_i-c_i)^2 + posterior_var_i) / V_C_i
              )

r_preference = clip(
  mean_valid(post_term_i - preference_log_terms_before_i) / reward_scale,
  -1, 1
)

reward = r_preference                                      if quality_score is invalid
reward = clip(0.70*r_preference + 0.30*(2*quality_score-1),
              -1, 1)                                      otherwise
reward in [-1,1]
```

`reward_scale` is positive, formula-versioned, and frozen in `PendingOutcome`. `quality_score`, when valid, is a structured deterministic bridge projection in `[0,1]` with a version/provenance tag; it cannot come from generated text, another LLM call, or a heuristic question-mark classifier. If no outcome dimension is valid, credit is censored. If quality is missing, the preference component receives total weight. The per-action baseline is a bounded exponential mean updated only after a valid, consecutive, known actual-action outcome:

```text
baseline_actual' = clip(0.95*baseline_actual + 0.05*reward, -1, 1)
```

The intrinsic-threshold update in section 8.2 may occur on every valid SNN turn. STDP consumes the pre-update actual-action baseline and requires:

```text
credit_gate = 1[stdp_credit_enabled and shadow_action == v2_actual_action]
delta       = credit_gate * (reward - baseline_actual_before_update)
candidate_ij = clip(W_ij + 0.002*delta*e_ij - 1e-5*(W_ij-W0_ij), legal_range)
```

For each postsynaptic neuron, candidates then undergo a deterministic incoming-budget projection. Formula/model validation first rejects any topology with `fixed_abs_sum_i > 1.2`. Let `fixed_abs_sum_i` include every immutable excitatory and inhibitory incoming edge, and `budget_i=1.2-fixed_abs_sum_i`. Iterate plastic E-to-E incoming edges in canonical `synapse_id` order and assign `W_ij'=min(candidate_ij,remaining_budget)`, then decrement the remaining budget. Once it reaches zero, all later plastic candidates become zero. The projection result and any clipped mass are traced. Thus per-edge bounds, Dale signs, and the total incoming absolute-weight limit remain simultaneous invariants after every update.

Unexecuted v3 actions never borrow the outcome of another action. Missing next turn, queue loss, sequence gap, timeout, reload, unknown actual action, preference/projector revision mismatch, or out-of-order delivery marks the pending outcome `CENSORED`: discard its action credit without changing weights or baselines. The action-transition model may still learn from a consecutive known v2 actual action even when the v3 shadow action differs, but STDP action credit remains gated by both the originating profile and action equality. Idle replay is never allowed to apply STDP; only this single online settlement path may consume a pending eligibility tensor, and the consumed `TurnKey` is retained as an idempotency fence.

Settlement reads one immutable pre-state, computes posterior/reward, optional STDP delta, actual-action baseline, transition update, pending-outcome removal, and consumed-turn fence into the same `StateDelta`, then commits them atomically with the current turn. CAS failure leaves every learning value and the pending record unchanged; retry recomputes from the same pre-state bytes.

## 9. Multi-Timescale Dynamics

Eight named axes replace scattered user/emotion/expression EMA state:

```text
valence
arousal
safety
affiliation
uncertainty
novelty
agency
expression_pressure
```

Each axis has fast, mid, and slow state, producing 24 values in `[-1,1]`.

```text
drive       = tanh(P*observation + Q*snn_summary + bias)

target_fast = tanh(W_fast*fast + U_fast*drive)
fast'       = clip(fast + 0.50*(target_fast-fast), -1, 1)

target_mid  = tanh(W_mid*mid + U_mid*fast')
mid'        = clip(mid + 0.12*(target_mid-mid), -1, 1)

target_slow = tanh(W_slow*slow + U_slow*mid')
slow'       = clip(slow + 0.02*(target_slow-slow), -1, 1)
```

`P`, `Q`, `W_*`, and `U_*` are sparse, named, immutable defaults under a `formula_version`; online learning does not modify them. Each self matrix satisfies `||W_*||_2 <= 0.5`, giving a per-block self-contraction bound of `(1-alpha)+0.5*alpha < 1`. Before a formula version is accepted, interval/Jacobian analysis over the complete 24-dimensional sequential triangular update must establish `sup ||J||_2 < 0.995` across declared input/state bounds. Formula v1 uses fast/mid/slow self diagonals `(0.30,0.35,0.36)` and its entrywise-absolute bound `sqrt(||J||1*||J||inf)=0.9948652052815999`; checking only three block diagonals is invalid because it omits fast-to-mid-to-slow derivatives. If the complete proof fails, the formula version is rejected rather than relying on `tanh` clipping alone. State advances at most once for a committed turn revision.

Aggressive emergence comes from faster bounded plasticity, cross-timescale coupling, and information-seeking policy, not from unbounded state or unseeded randomness.

## 10. Global Workspace

The initial workspace accepts at most eight proposals:

```text
body-speak
affect-speak
uncertainty-clarify
boundary-hold
fatigue-hold
affiliation-reach
snn-novelty
continuity-speak
```

Each proposal contains a stable `proposal_id`, legal action, salience in `[-4,4]`, confidence in `[0,1]`, and a 16-dimensional L2-normalized key. A zero key is valid but has zero similarity. Context masks illegal actions before competition. Effective salience is `salience*(0.5+0.5*confidence)`.

For distinct proposals only:

```text
similarity(p,q) = max(0, dot(key_p,key_q)) in [0,1]
```

Competition runs four iterations:

```text
u_p[l+1] = clip(
  0.4*u_p[l]
  + 0.6*(
      effective_salience_p
      - 0.60*sum(q != p, similarity(p,q)*sigmoid(u_q[l]))
      - 0.45*proposal_refractory[source_p]
    ),
  -8, 8
)

activation = softmax(u / 0.35)
```

No legal proposal yields an explicit empty broadcast. One legal proposal broadcasts with activation 1. Otherwise top-1 broadcasts when `p1 >= 0.45` and `p1-p2 >= 0.08`; ambiguous competition broadcasts top-2 and adds a versioned, traced evidence term to `CLARIFY` rather than directly selecting it. Exact utility ties use lexicographic `proposal_id`, independent of registration order.

Proposal-source refractory state is persistent:

```text
R_source' = clip(
  0.72*R_source + 0.45*1[source was broadcast],
  0, 1
)
```

Autonomous-action refractory is a separate state `rho_a`, never the observation-likelihood variance `R_a`. It exists only for `a in {HOLD,REACH}`, starts at zero, and updates once per committed turn:

```text
rho_a_decay = 0.80*rho_a
autonomous_refractory_log_penalty(a) =
  2*rho_a_decay   if context in {PROACTIVE,IDLE} and a in {HOLD,REACH}
  0               otherwise
rho_a' = clip(
  rho_a_decay + 0.35*1[context in {PROACTIVE,IDLE} and shadow_action == a],
  0, 1
)
```

Addressed/ambient turns only decay `rho`; `SPEAK` is never penalized by this state. The exact penalty entering policy scoring is the pre-update `rho_a_decay`, and the post-selection increment is committed only with the rest of the turn state.

Surface repetition is a separate `ExpressionPolicy` concern. It stores a bounded recent structural signature such as `(opening_mode, hesitation_allowed, length_bucket, directness_bucket)` and suppresses repeated style signatures through `style_refractory`; it never inspects or inserts fixed literal prefixes. Action/proposal refractory must not be reused as style deduplication.

Workspace validity requires finite capacity, real competition, multiple broadcast consumers, observable inhibition, and registration-order invariance. If ablation cannot demonstrate these properties, the component is renamed or removed.

## 11. Finite-Action Active Inference

The legal action set is:

```text
SPEAK
HOLD
CLARIFY
REACH
```

Legal actions and priors are total over `TurnContextClass`:

| Context | Legal actions | `p0` in listed order |
|---|---|---|
| `ADDRESSED` | `SPEAK, CLARIFY, HOLD` | `0.55, 0.25, 0.20` |
| `AMBIENT` | `HOLD, SPEAK` | `0.75, 0.25` |
| `PROACTIVE` | `HOLD, REACH` | `0.80, 0.20` |
| `IDLE` | `HOLD` | `1.00` |

The enum is mutually exclusive and masks illegal proposals before workspace competition. `IDLE` is maintenance-only; it cannot manufacture an outreach opportunity. An addressed or ambient provider reply may project to actual `SPEAK` only with an independent structured success receipt; the pinned AstrBot 4.26.5 ordinary path has no such receipt and remains `UNKNOWN`. Only a verified proactive send may project to actual `REACH`.

### 11.1 Actual Action Projection

Bridge-owned `V2ActualActionProjectionV1` is a versioned pure function over structured v2 route/result metadata. It never guesses from generated text or punctuation:

| Structured v2 outcome | Projected action |
|---|---|
| explicit silent/no-send route completed | `HOLD` |
| proactive outreach actually sent | `REACH` |
| future explicit structured clarify marker actually sent | `CLARIFY` |
| addressed/ambient provider reply with an independent structured success receipt, including a dedicated all-segments-success receipt | `SPEAK` |
| fallback, handler/provider error, tool-only turn, cancelled/interrupted partial send, missing provenance, or ambiguous result | `UNKNOWN` |

AstrBot 4.26.5 `after_message_sent` is not a success receipt: `RespondStage` catches ordinary `event.send()` exceptions and continues to invoke the hook. Therefore an ordinary framework send remains `UNKNOWN` during G0-G4 unless a future independent positive receipt is grounded; absence of an observed error is never treated as delivery. A dedicated segmented/takeover path may prove `SPEAK` only after every declared segment, including a one-segment takeover, reports success.

`UNKNOWN` disables action credit and transition-model updates. Current v2 has no reliable structured `CLARIFY` marker, so its outcome model remains prior-only until such provenance exists; a question mark in assistant text is never treated as evidence.

### 11.2 Generative Beliefs

The eight-dimensional decision state is a versioned blend of fast/mid/slow axes:

```text
s = clip(0.50*fast + 0.30*mid + 0.20*slow, -1, 1)
```

Each action maintains a state-dependent diagonal Gaussian transition belief:

```text
mu_a(s)      = tanh(g_a * s + b_a)
q(s' | s,a) = Normal(mu_a(s), diag(V_a))

g_a in [0.5,1.2]
b_a in [-0.5,0.5]
V_a in [0.02,1.0]
```

The bridge supplies an eight-dimensional normalized `OutcomeFrame(y[8], valid_mask[8], projector_revision)` for consecutive known actual actions. It is a versioned pure projection from the next `ObservationFrame u` and never performs I/O. `valid_mean` omits unavailable contributors and clears the output bit when none remain:

| Axis | v1 outcome projection in `[-1,1]` |
|---|---|
| valence | `valid_mean(2*u[25]-1, 2*u[0]-1)` |
| arousal | `2*max_valid(u[21],u[23])-1` |
| safety | `1-2*valid_mean(u[1],u[2],u[17])` |
| affiliation | `valid_mean(2*u[0]-1, u[19]-u[20])` |
| uncertainty | `2*valid_mean(u[22],u[4],1-u[6])-1` |
| novelty | `2*u[4]-1` |
| agency | `2*u[9]-1` |
| expression_pressure | `2*u[11]-1` |

The warm-minus-cold affiliation contributor is valid only when both source bits are valid. Every other contributor inherits its source bit. All results are clipped to `[-1,1]`; non-finite results clear that outcome bit. The v1 observation mapping is identity because latent and outcome axes are intentionally aligned:

```text
p(y' | s',a) = Normal(s', diag(R_a))
R_a in [0.02,1.0]
```

For a predictive prior `q(s'|s,a)=Normal(mu_a,diag(V_a))`, each valid outcome dimension has the exact posterior:

```text
posterior_var_i  = 1 / (1/V_ai + 1/R_ai)
posterior_mean_i = posterior_var_i * (mu_ai/V_ai + y_i/R_ai)
```

`R_a=0.20` in formula v1 is an immutable conservative likelihood prior, not a claim of offline calibration. G4 evaluates observation-likelihood NLL and empirical 68%/95% interval coverage on frozen held-out episodes; a later formula version may change `R_a` only from that frozen report. For the known, consecutive actual executed action only, a projected diagonal extended-Kalman update learns transition parameters and variance. For dimension `i`, with pre-update values:

```text
theta_ai = [g_ai, b_ai]
phi_i    = [s_i, 1]
mu_i     = tanh(theta_ai dot phi_i)
j_i      = (1-mu_i^2) * phi_i
error_i  = y_i - mu_i
denom_i  = V_ai + R_ai + sum_k(j_ik^2 * Sigma_aik)
K_ik     = Sigma_aik * j_ik / denom_i

theta_aik' = project_box(theta_aik + K_ik*error_i)
Sigma_aik' = clip((1-K_ik*j_ik)*Sigma_aik + q_theta, 1e-4, 1.0)
eta         = 1 / (min(n_ai,64)+4)
V_ai'       = clip((1-eta)*V_ai + eta*error_i^2, 0.02, 1.0)
n_ai'       = min(n_ai+1, 65535)
```

Projection uses `g in [0.5,1.2]` and `b in [-0.5,0.5]`; `q_theta=1e-4` is formula-versioned. Updates use fixed axis/parameter order and the pre-update innovation. Unknown, non-consecutive, censored, or invalid outcome dimensions perform no update.

Preferences are a diagonal Gaussian:

```text
p_C(s') = Normal(c, diag(V_C))

c = [
  current_valence,
  0,
  0.6,
  current_affiliation,
  0,
  0,
  0.4,
  0,
]

V_C = [0.50,0.25,0.20,0.50,0.20,0.50,0.25,0.25]
```

This preserves current valence/affiliation rather than forcing permanent positivity while preferring bounded safety, agency, uncertainty, and expression pressure. `c` and `V_C` are policy inputs, not online-learned personality parameters. At turn `t`, `PendingOutcome` freezes their values, digest, and per-dimension `log Normal(s_i;c_i,V_C_i)` terms for the reward calculation in section 8.3.

### 11.3 Expected Free Energy And Policy Posterior

All EFE components use natural-log units:

```text
risk(a) = KL(
  Normal(mu_a(s),diag(V_a))
  || Normal(c,diag(V_C))
)

ambiguity(a) = 0.5 * sum_i log(2*pi*e*R_ai)

j_ai(s) = (1-mu_ai(s)^2) * phi_i(s)

information_gain(a) = 0.5 * sum_i log(
  1 + j_ai(s)^T*Sigma_theta_ai*j_ai(s)/(V_ai+R_ai)
)

G(a) = risk(a) + ambiguity(a) - information_gain(a)
```

`phi_i(s)=[s_i,1]`; `j_ai` is the Jacobian of the nonlinear transition mean with respect to gain/bias, and `Sigma_theta` is their bounded diagonal posterior covariance. The epistemic denominator includes both transition and observation noise, matching the declared generative model. Policy EFE uses all eight always-finite persistent latent axes. `OutcomeFrame.valid_mask` gates only posterior settlement, reward, and online transition updates. Missing current observations influence policy through unchanged latent state and absent evidence/proposals, never through semantic default tensor values. Every sum is normalized by its declared dimension count.

Section 11's context table provides the complete legal masks and explicit action priors; there is no implicit third-case default.

Workspace support is calibrated and bounded as a log-likelihood-ratio contribution in `[-2,2]`. Idle autonomous refractory is a bounded log-prior penalty in `[0,2]`. The policy posterior is:

```text
logit(a) =
  log p0(a|context)
  + workspace_log_evidence(a)
  - autonomous_refractory_log_penalty(a)
  - gamma*G(a)

q(a) = softmax(logit(a)/temperature)

gamma = 1.0
temperature = 1.0
```

Only legal actions enter softmax. Exact posterior ties use the fixed safety order `HOLD, CLARIFY, SPEAK, REACH`; confidence is `p1-p2`. Every likelihood, belief, preference, EFE term, log-evidence adjustment, and posterior value appears in the deterministic trace.

The initial implementation/class is named `PolicyScorerV1`. It may expose the scientific alias `ActiveInferencePolicy` only after likelihood calibration, Brier/ECE, action-coverage, and EFE ablation gates pass. Unexecuted actions retain high uncertainty. Pure shadow cannot establish causal superiority over v2 and cannot train from invented counterfactual labels.

## 12. Expression Policy

`ExpressionPolicy` converts the selected action and broadcasts into constraints such as length, pace, directness, warmth, and whether a hesitation style is permitted. It never emits fixed user-visible text.

There is no v3 `hesitation_ema`, deterministic `lead`, or renderer-level `"嗯……"` insertion. Repetition control comes from workspace/action refractory state and recent structural outcome features, with one decision per turn.

## 13. Aggressive Emergence And Replay

Aggressive emergence is allowed within these boundaries:

- online plasticity is limited to the explicitly specified SNN intrinsic thresholds, one-shot reward-gated E-to-E STDP, and executed-action transition parameters/covariance;
- continuous axes and refractory values are bounded recurrent state, not learned matrices or hidden reliability parameters;
- all plastic state is session-scoped by default;
- cross-group projection follows the existing privacy switch; without it, group sessions remain isolated;
- shared model parameters are immutable priors, never globally plastic user data;
- preferences are derived from current bounded state and versioned constants; v1 has no online preference consolidation;
- every learned value has a bound, revision, version, and trace contribution.

There is no mutable observation-statistics model, workspace proposal-reliability learner, dynamics-matrix learner, or slow-preference learner in v1. Adding any of them requires a later formula revision with state schema, update equation, bounds, credit source, replay rule, and ablation gate.

Each session has a bounded 64-entry `ExperienceBuffer` containing encoded facts, not additional raw chat text. Observations and next observations are quantized to unsigned 8-bit values, bounded signed features/rewards to signed 16-bit values, and actions/valid masks to packed integers:

```text
observation_digest
encoded_features
workspace_broadcast
shadow_action
v2_actual_action
next_observation
reward_components
outcome_projector_revision
trace_revision_key(state_generation_id, revision, turn_id)
```

Digest dependencies are one-way. First compute `payload_digest=SHA256(canonical_cognitive_payload_bytes)`. Then serialize `CoreDecisionTrace`, which may include that payload digest but never its own digest, and compute `core_trace_digest`. Finally compute `journal_digest` over a framed repository envelope containing the payload bytes/digest and trace bytes/digest; `journal_digest` lives only in the pointer/index envelope and is not embedded in the payload, trace, or migration receipt. `ExperienceBuffer` refers to an already committed trace by `trace_revision_key`, not by a same-turn trace digest, so state and trace cannot hash each other.

Per-session SNN plastic weights, eligibility, voltages, thresholds, and traces use deterministic packed float16/int16 arrays with shape/version headers and CRC before optional zlib/base64 storage. Sparse topology and immutable initial weights are shared model data, not copied into every session. Decoding validates exact byte length, shape, finite values, Dale signs, and checksum before constructing state.

Per-session state byte budget, including encoding overhead:

| Block | Target ceiling |
|---|---:|
| headers, revisions, fences, digests | 2 KiB |
| 24-axis dynamics, workspace/style refractory, action beliefs | 4 KiB |
| SNN neuron/plastic/eligibility state | 10 KiB |
| 64-entry quantized ExperienceBuffer | 16 KiB |
| pending outcome/credit, migration receipt, evaluation metadata | 4 KiB |
| serializer/base64/compression worst-case margin | 12 KiB |
| total target | 48 KiB |
| hard rejection ceiling | 64 KiB |

`CoreDecisionTrace` lives with its matching revision journal record; `RuntimeTelemetry` uses a separately rotated diagnostic journal. Neither counts as live per-session cognitive state. A state exceeding 64 KiB is rejected before CAS; the previous revision remains authoritative.

Idle, zero-LLM replay is a read-only evaluation sidecar over immutable `ExperienceBuffer` snapshots. It may compute counterfactual decisions, calibration, novelty, uncertainty, and conflict metrics, but it cannot mutate slow state, thresholds, SNN weights/eligibility, baselines, action beliefs, pending outcomes, or any other `V3_STATE`. Metric emission is capped and idempotent by `(buffer_entry_digest, evaluator_version)`. Replay cannot write v2 memory, generate synthetic chat memories, or create a synthetic outcome. Replay-STDP is prohibited in G0-G4.

## 14. Shadow Lifecycle

### 14.1 Request Boundary

1. Allocate `TurnHandle` and freeze `CapturedTurn`.
2. Capture immutable public inputs only.
3. Do not advance v3 state.
4. Allow v2 to continue unchanged.

### 14.2 Response Boundary

The authoritative response path only claims the exact `TurnHandle`, freezes `V2ActualActionProjectionV1` and the final outcome projection, and offers an immutable `ShadowJob` to a bounded `ShadowSupervisor` queue. Deadline exists only in `ShadowJob`. The authoritative path never awaits full v3 calculation. Queue saturation records that `TurnSequence` as `DROPPED` and returns instead of applying backpressure to v2.

The event-loop path performs immutable capture plus a non-blocking bounded offer only. Core calculation and canonical trace serialization run in a v3-private `ThreadPoolExecutor` with one worker on the 2-core target; v3 work is never placed in the plugin's existing `_background_tasks`, whose shutdown cancellation order is owned by legacy/v2 subsystems. Execution is globally serialized. A deterministic round-robin scheduler takes at most one job from each non-empty session queue per cycle, preserves order within each session, and prevents one busy session from starving another. The background supervisor uses a v3-owned per-session sequencer and state transaction:

1. reject duplicate, stale, or out-of-order jobs by session generation, `TurnKey`, and turn sequence;
2. compare the job sequence with persistent `last_committed_turn_sequence` and the bridge `SequenceLedger`;
3. before the first core stage, select and freeze one versioned `ComputeProfile`, build `TurnEnvelope`, and derive the seed from its digest;
4. settle the previous eligible delayed outcome only when adjacency is exact and both turns are valid;
5. run encoder, SNN, dynamics, workspace, inference, and expression policy without changing profile;
6. core creates `DecisionPlan`, `StateDelta`, closed `EffectBundle`, and `CoreDecisionTrace`; the supervisor records separate `RuntimeTelemetry`;
7. validate dimensions, bounds, finiteness, seed, compute-profile digest, writer epoch, state generation, expected revision/digest, turn key, and sequence;
8. compare v3 shadow decision with v2 actual behavior;
9. submit one `CommitEnvelope` to `EffectCommitter`, which journals state plus deterministic trace and advances the state pointer by CAS;
10. finalize the registry/sequence status and emit non-deterministic telemetry idempotently.

Each per-session queue is capped at 4, the global queue at 128, the turn registry at 1,024 entries with a 15-minute TTL, active sessions at 64, repository sessions at 96, and worker count at 1. Each SessionRef-partitioned `SequenceLedger` records `ACCEPTED`, `DROPPED`, and `COMMITTED` `TurnSequence` high-watermarks. Within one writer epoch, if local sequence `n` is dropped, `n+1` may continue from the last committed v3 state, but it sets `credit_adjacency=false`, marks the pending outcome from `n-1` censored, and skips delayed reward, action-transition, and temporal-credit updates for the gap. It never treats `n+1` as the next observation of `n-1` or fabricates the missing transition. A greater writer epoch can continue state advancement but never delayed credit from the previous epoch.

v3 does not reuse `v2core.TurnRunner`, capability `evolve()`, domain `ingest()`, memory decay, learning, renderer, or response tick paths.

### 14.3 Failure Degradation

- invalid encoder fields use semantic defaults and clear valid bits;
- any non-finite SNN voltage/current/threshold/weight/eligibility value rolls back the entire SNN sub-transaction and disables STDP for the turn;
- invalid continuous state preserves the previous valid 24-dimensional state;
- a non-finite action score becomes `+inf`;
- if all actions fail, trace a degraded `SPEAK if context == ADDRESSED else HOLD` decision without external effect;
- three consecutive SNN faults isolate SNN for 32 turns, followed by a 16-tick recovery probe;
- the supervisor may check a monotonic deadline before execution and between named pure stages; expiry discards the complete partial invocation, commits no state or `CoreDecisionTrace`, marks the sequence dropped/censored, and records only `RuntimeTelemetry`;
- core code never reads a clock or cancellation callback, and a `ComputeProfile` never changes mid-invocation;
- every exception is contained and reported to v3 diagnostics, never propagated into v2.

## 15. State, Persistence, And Migration

### 15.1 Independent State

v3 uses an independent namespace and files. Every state contains:

```text
schema_version
formula_version
source_digest
state_generation_id
revision
writer_epoch
session_generation
model_revision
last_committed_turn_sequence
last_committed_turn_id
```

`payload_digest` is repository-envelope metadata, not a field inside the bytes it hashes. It is `SHA256(canonical_cognitive_payload_bytes)` over the complete cognitive payload only, excluding the journal envelope, deterministic trace, pointer, and the digest field itself. The journal record and pointer carry this digest; CAS compares the pointer's digest with `expected_payload_digest`, avoiding self-reference.

The private repository exposes no general write API. `EffectCommitter` alone may call:

```text
acquire_epoch() -> monotonically increasing durable integer
seal_epoch(epoch) -> durable invalidation
compare_and_commit(
  session_ref: SessionRef,
  precondition: AbsentState | CommitPrecondition(
    writer_epoch,
    expected_state_generation_id,
    expected_revision,
    expected_payload_digest,
    turn_id,
    turn_sequence,
  ),
  journal_record,
) -> CommitResult
```

`state_generation_id` is an opaque, never-reused identifier. Initial creation and every quarantine replacement allocate a new value; revision numbers are meaningful only within that generation. CAS compares generation, revision, and payload digest, preventing ABA after reset or recovery. A replacement generation carries forward the previous `last_committed_turn_sequence` high-watermark and never reopens delayed credit.

`AbsentState` is the only legal creation precondition and succeeds only when no state pointer exists for the full `SessionRef`. `CommitResult` is one of `COMMITTED`, `ALREADY_MIGRATED`, `DUPLICATE_TURN`, `STALE_EPOCH`, `STALE_STATE_GENERATION`, `REVISION_CONFLICT`, `BASE_DIGEST_MISMATCH`, `STALE_SEQUENCE`, or `CORRUPT_BASE`.

At AstrBot `initialize`, the supervisor durably acquires a new plugin-wide writer epoch before starting workers. Every queue job and commit carries it. `terminate` is idempotent and performs this exact order:

```text
RUNNING -> STOPPING
  -> stop admission and detach producers
  -> mark unqueued registry entries DROPPED
  -> cancel replay/metric producers
  -> bounded-drain accepted commit-capable jobs while epoch remains valid
  -> close local committer admission
  -> durably seal epoch under repository lock
  -> cancel leftovers
  -> await every tracked task with gather(..., return_exceptions=True)
  -> executor.shutdown(wait=True, cancel_futures=True)
  -> clear bounded registries
```

A commit already serialized before sealing may finish. After `seal_epoch()` returns, no task can publish under that epoch. Core stages contain no callbacks or unbounded loops. Shutdown does not return while a v3 worker thread remains alive; `cancel_futures=True` cancels queued-but-not-started work and `wait=True` joins the running finite stage. Drain timeout cannot cause sealing before local commit admission is closed. A crash is fenced by the next initialize acquiring a greater epoch. A UUID is never used as an ordering fence.

Host lifecycle wiring preserves that order: `main.terminate()` calls synchronous `v3.begin_shutdown()` before any existing subsystem teardown, allows the existing v2 final-save drain to run while accepted v3 work drains, then awaits `v3.shutdown()` before the legacy `_background_tasks` cancellation loop. Repeated initialize/terminate and hot reload are idempotent; v3 executor futures/tasks are privately tracked and never share the legacy list.

Each revision journal record atomically contains the complete next cognitive payload, `CoreDecisionTrace`, state/payload digests, turn key, and sequence. The CAS pointer changes only after the record is durable. Stale epochs, low revisions, duplicate turns, and stale sequences are rejected. Runtime telemetry and derived metrics may lag but cannot make a state revision lose its deterministic trace.

Repository retention is bounded: keep the current and immediately previous full cognitive revision per session for crash recovery. The atomic migration record is an immutable generation anchor, not a cognitive revision: its sanitized `SeedRecord`, receipt, and migration trace remain until that complete generation is quarantined or deleted, and their bytes count against the generation/global budgets. Before compacting an older cognitive revision, export its deterministic trace idempotently to a size/age-rotated diagnostic journal keyed by revision digest; then remove the obsolete full state record through the committer. Queue, lock, registry, journal, and orphan lifecycles all have explicit caps and cleanup tests.

### 15.2 One-Time v2 Seeding

On the first shadow turn for a session, `MigrationCoordinator` obtains an immutable `V2SeedSnapshotV1`. It either consumes a DTO already frozen by the authoritative v2 turn or briefly acquires the real production turn lock exposed as `plugin._session_lock(session_key)` and implemented by `SessionContext.session_lock`, copies the DTO, and releases that lock before taking any v3 migration/state lock. `v2core.session_store.SessionLocks.turn` is not the current production-chain lock and must not be used for this migration. v2 and v3 locks are never held together.

Bridge code converts `V2SeedSnapshotV1` into a core-owned, versioned `SeedFrame`; `v3core` never imports the v2 DTO type. The pure `v3core.state.seed.SeedProjector` projects only initial values:

```text
v2 hesitation/bond          -> uncertainty/affiliation axis seed
v2 emotion fast/slow        -> fast/mid valence, arousal, and safety seed
v2 narrative/ossification  -> slow affiliation and agency seed
v2 style/adaptation         -> bounded initial style-signature/refractory seed
```

The sanitized immutable `SeedRecord` and its digest are stored once in the same v3 migration journal record as the initial state and receipt. After a committed migration receipt, v3 never freezes a new live v2 domain snapshot for that session generation. It continues to consume public BodySnapshot and observed host outcomes.

Migration protocol:

```text
freeze V2SeedSnapshotV1 under v2 turn ownership, then release v2 lock
  -> hold v3 migration lock
  -> convert to sanitized core-owned SeedRecord
  -> pure-project initial V3State generation
  -> construct one MigrationCommitEnvelope containing:
       SeedRecord + initial V3State + MigrationReceipt + MigrationTrace
  -> canonical-serialize and validate bounds, size, and every digest in memory
  -> EffectCommitter performs one compare-and-commit
  -> permit shadow advancement
```

A migration receipt references `seed_digest`, migrator version, state generation, and initial cognitive revision; it does not contain the enclosing `journal_digest` and is not a moving marker for later learned payloads. The repository pointer/index carries the externally computed migration journal digest. There is no repository-visible provisional migration revision. `compare_and_commit` privately durably stages the complete immutable journal bytes before pointer publication, and cleans unreachable staging after failure. The receipt, seed, initial payload, and trace become visible as one logical commit. Concurrent migration returns `ALREADY_MIGRATED` or a CAS conflict and never creates a second seed.

Recovery is explicit:

| Migration record | SeedRecord | Cognitive payload | Recovery |
|---|---|---|---|
| absent | absent | absent | freeze v2 once and attempt the atomic migration commit |
| unreachable private staging only | any | any | validate and remove staging; no pointer means no committed migration |
| committed and internally consistent | digest-valid | valid revision >= initial | load learned state; receipt need not match the latest payload digest |
| committed | digest-valid | missing/corrupt | quarantine the damaged generation and atomically create a new generation from the stored immutable seed, carrying the sequence high-watermark |
| committed | missing/corrupt | any | quarantine and start a neutral new generation; do not silently reread current v2 as if it were the original seed |

Normal cognitive state, packed SNN state, pending outcomes/credit, `ExperienceBuffer`, and evaluation metadata live in one CAS payload generation. A later learned revision is never overwritten by re-projecting live v2 state. v2 state is never overwritten, deleted, or reverse-projected.

Raw session IDs never cross into `v3core` or persistence. Bridge creates:

```text
SessionRef(
  hmac_key_id,
  surrogate = HMAC-SHA256(
    persistent_key,
    canonical_encode_v1(
      domain = "sylanne-v3-session-ref",
      platform_id,
      canonical_session_id,
    )
  ),
  session_generation,
)
```

`canonical_encode_v1` UTF-8 encodes a schema/version tag and every typed field with an unsigned 32-bit big-endian byte-length prefix; raw concatenation or delimiter-only framing is forbidden. The persistent key is generated once in the AstrBot plugin data directory and is never stored in configuration, traces, filenames, or state payloads. Filenames use the full 256-bit surrogate encoding; loaded records must match key ID, full surrogate, and generation or fail closed. Key loss or rotation creates a new namespace and never silently attaches old state. A plain hash is not accepted for low-entropy session identifiers. Tests must include cross-field boundary aliases such as `("qq","a:b")` versus `("qq:a","b")` and prove distinct surrogates.

## 16. Observability

### 16.1 Hard Isolation Counters

All must remain zero:

```text
v3_external_reply_count
v3_prompt_mutation_count
v3_tool_call_count
v3_body_tick_count
v3_v2_memory_write_count
v3_astrbot_history_write_count
v3_extra_llm_call_count
```

### 16.2 Deterministic Core Trace

Each `CoreDecisionTrace` includes:

- turn/input/state/formula/model revisions and digests;
- complete `ComputeProfile` ID, normalized parameters, and digest;
- seed and canonical BodySnapshot PE values;
- deterministic, SNN, and continuous-path features and contribution summaries;
- spike counts, first latencies, weight saturation, and SNN degradation state;
- every workspace proposal, activation, inhibition, refractory term, and broadcast;
- every transition belief and EFE term;
- v3 shadow action, v2 actual action, and structured disagreement reason;
- deterministic numerical-health and profile/input-driven degradation reason.

It excludes wall-clock timing, queue scheduling, worker/process identity, timeout decisions, CAS outcome, filesystem latency, current host load, and the runtime reason that selected a profile. The selected `ComputeProfile` itself is a deterministic core input and is never excluded. Canonical serialization fixes field order, enum spelling, array shape, endianness, and packed-number representation. Required fixed-shape numeric values use versioned packed/base64 arrays; digest/count summaries may accompany them but cannot replace them. A worst-case legal trace must serialize to at most 16 KiB. If a complete trace exceeds that cap, the entire invocation is invalid: state and core trace are both discarded, the sequence is dropped/censored, and only bounded runtime telemetry records the size failure.

Byte-identical replay is guaranteed only for the same declared runtime fingerprint: formula/model version, `ComputeProfile`, Python minor version, math backend, CPU architecture, initial state, event sequence, and seed. Cross-fingerprint replay uses per-field numerical tolerances and action/ordering equality, not a false byte-identity claim.

### 16.3 Runtime Telemetry

`RuntimeTelemetry` records stage timings, queue acceptance/drop, timeout, CAS/commit result, worker epoch, plugin instance, retry, load, profile-selection reason, and journal/export latency. It is excluded from core trace/state digests and byte-replay assertions. Telemetry can be joined to a committed core trace by `(writer_epoch, state_generation_id, revision, turn_id)`; timed-out invocations intentionally have no core-trace join target.

There is no WebUI mode selector. Grey builds may expose administrator-only read-only diagnostics and JSONL export.

## 17. Grey Evaluation

### 17.1 Stages

```text
G0  unit, property, invariant, and fault-injection tests
G1  fixed real-history offline replay
G2  local single-session automatic shadow
G3  grey artifact shadow for every turn with provable request/terminal correlation, with load circuit breaker
G4  frozen-data ablation and calibration report
```

The first local grey candidate is built only after G0, frozen encoded G1, and local G2 pass. G3 necessarily starts after that candidate exists because it requires real grey-artifact traffic with provable request/terminal correlation. G3 is then frozen as encoded facts, and G4 evaluates frozen G1+G3. G3/G4 are post-candidate evidence and input to a later version, not prerequisites that create a build/evaluation cycle for the first candidate.

This project ends at G4. Any future live execution needs a separate design, explicit authorization, writer-epoch ownership transfer, and causal evaluation. It is not enabled through user configuration.

### 17.2 Ablation Ladder

```text
deterministic baseline
+ multi-timescale dynamics
+ Global Workspace
+ Active Inference or PolicyScorer
+ SNN
+ STDP
```

The preregistered primary metrics are reductions versus the immediately preceding ablation rung in: multiclass actual-action log loss, multiclass Brier score, and next-turn valid-axis weighted MAE. A positive gain means `baseline_loss - candidate_loss`; bootstrap resampling is by whole episode, never by row. Each added layer must improve at least one primary metric with bootstrap 95% confidence interval lower bound above zero on frozen G1+G3 while not worsening either other primary metric by more than 0.5%. Safety degradation must stay below 0.5 percentage points, all seven isolation counters and illegal/nonfinite action counts must remain zero, and cross-turn train/evaluation splits must be disjoint by export-local episode reference. A layer without independent contribution is removed or keeps its conservative V1 name.

Scientific aliases additionally require at least 200 effective correlated turns overall and 30 known actual-action examples for every reported action, ECE <=0.10, Brier score no worse than the deterministic baseline, observation-likelihood 68% coverage error <=0.10 and 95% coverage error <=0.05, the event-order shuffle test removing at least 50% of persistent-SNN gain, and learned-vs-frozen/random plus STDP-vs-zero-LR bootstrap lower bounds above zero. Insufficient coverage is reported as `INSUFFICIENT_EVIDENCE`, never silently passed.

Evaluation is chronological prequential within each held-out episode: predict turn `t` using only the frozen episode header and observations strictly before `t`, score the frozen outcome/action, then allow the declared online update for `t+1`. Every encoded dataset begins each episode with a tagged header containing canonical `neutral_eval_v1` state bytes/digest, no pending outcome, boundary credit censored, `FULL_24_STDP` evaluation-profile ID/digest, gate-manifest digest, and episode seed. G3's observed runtime state/profile remain diagnostic fields and are never guessed as the offline initial state/profile. Every turn records whether credit is adjacent and how many dropped/unmatched sequences preceded it; any gap censors delayed credit.

The episode seed is the first 128 bits of `SHA256(b"SYL3\x01EVAL\x00" || dataset_id || evaluation_group_ref || episode_ref || gate_manifest_digest || formula_digest || model_digest || profile_digest)` using the canonical length-framed encodings. Control seeds append a length-framed control ID, so learned/frozen/random/zero-LR runs cannot share an accidental random stream.

One permission-restricted local evaluation-link HMAC key is retained outside Git and packages from G1 freeze through G4 completion. It creates the same `evaluation_group_ref` for the same authorized privacy scope/session across G1 and G3; each export still uses and destroys a separate source-digest key. Train/dev/test assignment is a deterministic domain-separated HMAC of `evaluation_group_ref`, and no evaluation group can cross a split even when it contributes multiple episodes or datasets. Model/formula selection uses train/dev only; primary, calibration, shuffle, and safety reports use the untouched test split. Bootstrap samples whole episodes. Key loss or G1/G3 key-digest mismatch makes G4 `INVALID_DATASET`, not a new split. The safety proxy is the known-HOLD contradiction rate (`shadow in {SPEAK,REACH}` while structured actual action is `HOLD`) plus the seven isolation, illegal-action, nonfinite, and privacy counters; it is explicitly a conservative behavioral proxy, not a causal safety claim.

Read-only idle replay is evaluated as an observability/calibration sidecar, not as a cognitive layer, because G0-G4 prohibit it from changing decisions or state.

### 17.3 Falsification Tests

SNN:

- resampling the same normalized virtual horizon at 16/24/32 ticks with K-adjusted decay/refractory constants must keep action-distribution JS divergence below 0.02;
- shuffling cross-turn event order while preserving feature marginals and gap distribution must remove at least 50% of measured persistent-SNN gain; shuffling only within-window latency spikes tests encoder integrity but is not accepted as evidence of real conversational time learning;
- learned reservoir must outperform equal-sized frozen and random reservoirs;
- STDP must outperform a zero-learning-rate control;
- per-session sparse synapse, trace, and experience state remain bounded.

Workspace:

- proposal registration-order randomization cannot change the decision;
- disabling inhibition/refractory must measurably change lock-in/repetition behavior;
- finite capacity and multiple real broadcast consumers are required.

Active Inference:

- every EFE term has probability semantics, units, source, and calibration method;
- report action coverage, effective sample size, Brier score, and ECE;
- shadow disagreement is never reported as causal policy improvement.

### 17.4 Stability And Replay

For each fixed seed, run at least 100,000 normal, repeated, out-of-order, extreme, and malformed turns. Recovery tests freeze online learning/replay so they measure the declared dynamics rather than a moving target. A formula version publishes neutral-input baseline envelopes for every axis.

- no NaN/Inf and no state outside declared bounds;
- after a single extreme pulse, 99.9% of sessions reduce fast-axis perturbation norm to at most 10% within 8 neutral turns and mid-axis perturbation to at most 35% within 20 neutral turns;
- slow state is intentionally retentive and need not return to baseline within 20 turns, but remains bounded, changes by at most 0.03 per neutral turn, and cannot by itself lock one action/proposal at posterior above 0.98 for 20 eligible turns;
- no permanent all-speak, all-hold, workspace winner lock, or weight saturation;
- under the same declared runtime fingerprint, identical inputs, state, version, and seed produce byte-identical `CoreDecisionTrace`;
- same revision advances at most once and failed transactions leave state byte-identical.

### 17.5 Performance

On the 2-core/2-GB target:

- internal target p95 v3 compute <= 2.5 ms;
- grey acceptance p95 incremental latency <= 5 ms and p99 <= 15 ms;
- throughput loss below 5%;
- per-session state <= 64 KiB;
- shared immutable model <= 64 MiB;
- all queues, histories, replay buffers, and lock registries have hard bounds or lifecycle cleanup.

The global storage budget must stay inside `metadata.yaml`'s 50 MB declaration, not merely the per-session limit:

| Resource | Hard cap |
|---|---:|
| live cognitive payload | 64 KiB/session, target 48 KiB |
| deterministic core trace | 16 KiB/revision |
| active sessions | 64 |
| repository sessions | 96 |
| retained full revisions | current + previous per retained generation |
| trace diagnostic journal | 2 MiB x 2 segments |
| runtime telemetry journal | 1 MiB x 4 segments |
| private staging/orphans | 4 MiB |
| default v3 namespace high watermark | 22,000,000 bytes |
| default v3 namespace hard watermark | 24,000,000 bytes |

The metadata 50 MB limit is plugin-wide. At initialize, measure the data root excluding `v3/` and compute `effective_v3_hard=max(0,min(24_000_000,50_000_000-non_v3_bytes-2_000_000))` and `effective_v3_high=max(0,effective_v3_hard-2_000_000)`. If the effective hard cap is below 4 MiB, disable v3 admission and record telemetry.

At the effective high watermark, clean expired staging, already-exported obsolete revisions, and rotated diagnostics first. Never evict, tombstone, or reseed a current learned cognitive generation. If still over high watermark, reject new sessions. At the effective hard watermark, reject/drop every new v3 turn and leave v2 untouched. Budget accounting includes record framing, packed/base64/CRC overhead, pointer/key/lock files, and the temporary old+staging+new peak; it never scans, deletes, or modifies non-v3 data.

The per-resource limits are independent ceilings, not simultaneously reserved capacity. The effective v3 hard cap dominates them all: while holding the cross-process repository budget lock and before staging any write, the repository computes and atomically reserves the projected peak across retained generation anchors, current/previous revisions, diagnostics, telemetry, lock/key/pointer files, and old+staging+new bytes. The reservation remains represented until the staging file is committed or cleaned, so two processes cannot both admit against the same free bytes. A write that would exceed the effective hard cap is rejected before any staging or pointer change. The 96-session cardinality cap therefore does not promise that 96 worst-case 64 KiB states plus every journal cap can coexist.

Load shedding first disables admission of read-only replay/evaluation work. For a real turn, the supervisor selects exactly one frozen profile before core execution, in this order as pressure rises:

```text
FULL_24_STDP
  -> FULL_24_NO_STDP
  -> SNN_16_NO_STDP
  -> REUSE_LAST_SNN_SUMMARY
  -> DETERMINISTIC_CONTINUOUS_ONLY
  -> SKIP_V3_TURN
```

The selected profile fixes K, SNN/STDP/replay switches, last-summary reuse, math backend, and formula/model versions. It enters the seed, runtime fingerprint, trace, and digest. It cannot change mid-invocation. `SKIP_V3_TURN` is an admission outcome, not a core profile. A mid-run deadline expiry commits neither fallback state nor a partial core trace and permanently drops that `TurnSequence`; later work uses a new sequence and freshly frozen profile. v2 never awaits v3. The hard budget limits background CPU occupancy and determines v3 degradation/drop behavior, not authoritative response latency.

## 18. Terminology Gate

Names are earned by evidence:

- without finite-capacity competition, broadcast consumers, inhibition, and causal ablation, use `ProposalArbiterV1`, not Global Workspace;
- without explicit likelihood, transition, preference, policy posterior/EFE decomposition, and calibration, use `PolicyScorer`, not Active Inference;
- without temporal-order dependence and superiority to frozen/random controls, use `ReservoirFeaturesV1`, not meaningful SNN temporal learning;
- without bounded, recoverable, reproducible learning, do not describe behavior as controlled or aggressive emergence.

## 19. Relationship To Current v2 Fixes

v3 shadow has no user-visible authority and therefore cannot fix current production behavior. The following remain independent v2 implementation work:

1. group invocation classification, empty-call history, and SessionWaiter-safe ordering;
2. transactional ConversationBuffer flush, durable receipts, reset fencing, and plugin-side file coordination;
3. ordinary-reply hesitation correction: remove false Chinese short-text/punctuation evidence, remove deterministic draft prefixes, and unify expression policy;
4. request-local model-tool allowlisting: no tools by default, only a useful non-empty `query_agent_state` tool for explicit self-state questions, with attachments retaining native multimodal fields but no host tool expansion.

These fixes must land and be verified independently of v3core.

## 20. Acceptance Criteria

The v3 design is ready for implementation only when the plan guarantees:

1. no production code under `sylanne_alpha/_engine/**` changes;
2. v2 remains the sole authority and all seven isolation counters stay zero;
3. v3core is typed pure computation with no AstrBot/v2/engine imports;
4. every state transition is bounded, versioned, replayable, and transactional;
5. unexecuted counterfactual actions receive no fabricated reward;
6. grey builds auto-shadow without a configuration-page mode selector;
7. all layers face the specified ablation and falsification gates;
8. current v2 bugs remain separately implemented and tested;
9. grey work stops at G4 and cannot silently promote v3 to live authority;
10. documentation, targeted tests, full tests, lint, AstrBot plugin validation, performance replay, and `_engine/**` no-diff checks all pass before any completion claim.
