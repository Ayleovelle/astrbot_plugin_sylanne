# V3 Shadow Grey Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship v3 as an automatically enabled, stateful, zero-LLM shadow in the next local grey artifact while v2 remains the only authority and no remote push occurs.

**Architecture:** `sylanne_alpha.v3core` is synchronous pure computation over frozen DTOs. `sylanne_alpha.v3bridge` owns AstrBot/v2 projection, a private one-worker executor, deadlines, persistence, migration, telemetry, and lifecycle fencing. `main.py` holds one facade and only captures or confirms structured facts; v3 never mutates a request, reply, prompt, tool set, body, v2 memory, or AstrBot history.

**Tech Stack:** Python 3.10-3.13, stdlib dataclasses/enum/hashlib/hmac/struct/zlib/concurrent.futures, `portalocker>=2.10`, pytest, mandatory seeded property loops, ruff, AstrBot v4.26.5.

---

## Execution Rules

- Work in place on `feat/embodiment-2.5.0`; this is the intended grey branch.
- Preserve every unrelated untracked file already present in the checkout.
- Never modify `sylanne_alpha/_engine/**`.
- Never add a v3 selector to `_conf_schema.json`, WebUI, or a public API.
- Never run `git push`, create a PR, create a tag, or publish a release.
- Use one local Conventional Commit after each green task.
- Production code is written only after its named RED test fails for the expected missing behavior.
- v3core must not import AstrBot, v2core, `_engine`, asyncio, clocks, logging, filesystem, or callbacks.
- v3bridge may import host/v2 types but must pass only immutable core DTOs into v3core.

## Verified Baseline

Run before Task 1 and again before packaging:

```powershell
$PY = 'C:\Users\pidan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $PY -m pytest -q
```

Current evidence: `1848 passed, 3 skipped, 3 warnings` in 42.30 seconds. The warnings are pre-existing AstrBot/audioop, deprecated `register_star`, and sandbox pytest-cache permissions.

Record the no-push boundary:

```powershell
git -c safe.directory=G:/Sylanne-next rev-parse refs/remotes/github/main
git -c safe.directory=G:/Sylanne-next status --short --branch
```

## Required Reproducible Spikes

Each spike is a hard precursor to the task that consumes it. Preserve its JSON/JUnit output under ignored `artifacts/v3/evidence/spikes/`; a command that skips, uses synthetic framework source, or exits without the named assertion is not evidence.

```powershell
$PY = 'C:\Users\pidan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'

# A: installed AstrBot v4.26.5 source and real hook order
$env:ASTRBOT_SRC = Split-Path -Parent (& $PY -c "import astrbot,inspect; print(inspect.getfile(astrbot))")
& $PY -m pytest -q tests/integration/test_v3_astrbot_v4265_hook_order.py --junitxml=artifacts/v3/evidence/spikes/A-hook-order.xml

# B: Windows multi-process epoch/CAS/ABA durability
& $PY -m pytest -q tests/test_v3_repository_multiprocess.py tests/test_v3_repository_cas.py --junitxml=artifacts/v3/evidence/spikes/B-windows-cas.xml

# C: scalar core performance, separate from repository fsync
$env:SYLANNE_V3_PERF_GATES = '1'
& $PY -m pytest -q tests/test_v3_scalar_performance.py --junitxml=artifacts/v3/evidence/spikes/C-scalar-performance.xml

# D: worst-case state and complete deterministic trace sizes
& $PY -m pytest -q tests/test_v3_state_budget.py tests/test_v3_trace_replay.py -k "worst_case or hard_cap" --junitxml=artifacts/v3/evidence/spikes/D-size-caps.xml

# E: 50 complete initialize/turn/terminate cycles
& $PY -m pytest -q tests/test_v3_lifecycle.py -k "reload_50" --junitxml=artifacts/v3/evidence/spikes/E-lifecycle-50.xml

# F: grey/stable archive replacement, manifest, and adjacent zip digest
& $PY -m pytest -q tests/test_v3_package_channel.py -k "archive or manifest or digest" --junitxml=artifacts/v3/evidence/spikes/F-archives.xml
```

## Frozen Resource Budget

Create these constants in `sylanne_alpha/v3bridge/limits.py`; tests assert every value and the aggregate worst case.

```python
MAX_ACTIVE_SESSIONS = 64
MAX_REPOSITORY_SESSIONS = 96
MAX_STATE_BYTES = 64 * 1024
TARGET_STATE_BYTES = 48 * 1024
MAX_TRACE_BYTES = 16 * 1024
MAX_GLOBAL_QUEUE = 128
MAX_PER_SESSION_QUEUE = 4
MAX_TURN_REGISTRY = 1024
TURN_REGISTRY_TTL_SECONDS = 15 * 60
WORKER_COUNT = 1
TRACE_SEGMENT_BYTES = 2 * 1024 * 1024
TRACE_SEGMENT_COUNT = 2
TELEMETRY_SEGMENT_BYTES = 1 * 1024 * 1024
TELEMETRY_SEGMENT_COUNT = 4
MAX_STAGING_BYTES = 4 * 1024 * 1024
V3_DEFAULT_BUDGET_BYTES = 24_000_000
NON_V3_RESERVE_BYTES = 2_000_000
DISK_HIGH_WATERMARK_BYTES = 22_000_000
DISK_HARD_WATERMARK_BYTES = 24_000_000
```

The v3 namespace budget is incremental, but the metadata 50 MB cap is plugin-wide. At initialize, measure the plugin data root excluding `v3/` and compute `effective_v3_hard=max(0,min(V3_DEFAULT_BUDGET_BYTES,50_000_000-non_v3_bytes-NON_V3_RESERVE_BYTES))`; `effective_v3_high=max(0,effective_v3_hard-2_000_000)`. If the effective hard cap is below 4 MiB, disable v3 admission and record telemetry. Budget tests include record framing, base64/CRC, pointer/key/lock files, and the temporary old+staging+new peak.

At the high watermark, delete expired staging, exported obsolete revisions, and rotated diagnostics only. Never evict, tombstone, or reseed a current learned cognitive generation. If still above high watermark, reject new sessions; at hard watermark reject every new v3 turn. Neither path scans, deletes, or modifies non-v3 data.

## Frozen Formula Manifest V1

Create `sylanne_alpha/v3core/formula_v1.py` as the single source of formula constants. Canonical JSON over these constants produces `FORMULA_DIGEST`; golden tests lock the digest after the first reviewed implementation.

```python
FORMULA_VERSION = "sylanne.v3.formula.v1"
OBSERVATION_DIM = 36
AXIS_DIM = 8
STATE_DIM = 24
SNN_NEURONS = 96
SNN_EXCITATORY = 77
SNN_INHIBITORY = 19
SNN_DEFAULT_TICKS = 24
SNN_ALLOWED_TICKS = (16, 24, 32)
SNN_SUMMARY_DIM = 16
WORKSPACE_CAPACITY = 8
EXPERIENCE_CAPACITY = 64

TAU_MEMBRANE = -1.0 / (24.0 * log(0.90))
TAU_PRE = -1.0 / (24.0 * log(0.90))
TAU_POST = -1.0 / (24.0 * log(0.90))
TAU_ELIGIBILITY = -1.0 / (24.0 * log(0.95))
```

Observation drive matrix `P` is sparse and uses the following non-zero `(axis, channel, weight)` triples. `bias = -P @ SEMANTIC_DEFAULTS`, so the complete semantic-default frame yields zero drive.

```python
P_TRIPLES = (
    (0, 25, 0.55), (0, 0, 0.45),
    (1, 23, 0.35), (1, 21, 0.35), (1, 4, 0.30),
    (2, 1, -0.40), (2, 2, -0.35), (2, 17, -0.25),
    (3, 0, 0.35), (3, 19, 0.35), (3, 20, -0.25), (3, 26, 0.20),
    (4, 22, 0.30), (4, 4, 0.35), (4, 6, -0.35),
    (5, 4, 0.70), (5, 5, -0.30),
    (6, 9, 0.70), (6, 17, -0.30),
    (7, 11, 0.50), (7, 14, 0.30), (7, 10, -0.20),
)
Q[i, 2*i] = 0.20
Q[i, 2*i+1] = 0.10
```

The self matrices use diagonal values `(0.30, 0.35, 0.36)` for fast/mid/slow. The only off-diagonal couplings are safety and affiliation into valence `+0.06`, uncertainty into arousal `+0.06`, safety into uncertainty `-0.06`, affiliation into agency `+0.05`, and agency into expression pressure `+0.05`; mid uses 5/6 and slow 1/2 of those couplings. `U_fast=0.80I`, `U_mid=0.75I`, `U_slow=0.65I`. Using the complete sequential fast -> mid -> slow 24x24 entrywise-absolute triangular Jacobian, `sqrt(||J||1*||J||inf)=0.9948652052815999`; the formula validator rejects the manifest unless this full bound is `<0.995`. A block-diagonal-only check is invalid.

The recurrent topology is deterministic: for each postsynaptic neuron, rank every non-self presynaptic neuron by `SHA256(b"SYL3\x01REC\x00" + pack(">HH", post, pre))`. The first 58 postsynaptic neurons select 8 inputs and the remaining 38 select 7, producing density approximately 0.08. E-to-E starts at `0.06` and is plastic; every other excitatory edge starts at `0.08`; inhibitory edges start at `-0.12`. Model validation rejects self-loops, Dale violations, or fixed incoming L1 above 1.2. For each population input index `0..107`, rank targets by `SHA256(b"SYL3\x01INPUT\x00" + pack(">HH", input_index, target))`, select the four lowest distinct targets, and assign weight `0.50`.

The 16 SNN summary values are eight six-neuron pool firing rates followed by eight normalized first-latency confidences. Pools are the contiguous ranges `[0:6]`, `[6:12]`, ..., `[42:48]`; the remaining neurons contribute only recurrent context. For pool `p`, `summary[p]=clip(mean(spike_count_i/K),0,1)`. `summary[8+p]=0` when no pool neuron spikes, otherwise `1-min(first_latency_i)/(K-1)`. Missing channels emit no spikes and cannot affect any summary.

Workspace proposal salience is fixed as follows before clipping to `[-4,4]`; confidence is `clip01(0.5 + 0.25*abs(salience))` unless a required input is invalid, in which case the proposal is absent.

```text
body-speak          = 1.2*expression_pressure + 0.5*arousal + 0.3*center(expression_drive)
affect-speak        = 0.9*abs(valence) + 0.7*affiliation + 0.4*safety
uncertainty-clarify = 1.4*uncertainty + 0.4*novelty
boundary-hold       = -1.3*safety - 0.6*agency + 0.5*center(boundary_pressure)
fatigue-hold        = 1.4*center(exhaustion) - 0.4*expression_pressure
affiliation-reach   = 1.1*affiliation + 0.8*expression_pressure + 0.3*novelty
snn-novelty         = 1.2*snn_summary[10] + 0.6*novelty
continuity-speak    = 0.8*center(history_present) + 0.6*center(engagement) + 0.4*affiliation
```

`center(u)=2*u-1` for observation values in `[0,1]`. Each 16-dimensional proposal key has an action basis weight `1.0`, source basis weight `0.75`, and primary-group basis weight `0.50`, then is L2 normalized. The four action bases occupy indexes 0-3 and source bases 4-11 in listed proposal order. Group coordinates are: body-speak 12, affect-speak 12, uncertainty-clarify 13, boundary-hold 14, fatigue-hold 12, affiliation-reach 15, snn-novelty 13, continuity-speak 15. This makes related proposals compete without relying on registration order.

Required evidence bits are fixed: body-speak `{11}`, affect-speak `{}`, uncertainty-clarify `{}`, boundary-hold `{17}`, fatigue-hold `{10}`, affiliation-reach `{}`, snn-novelty requires a valid SNN summary, and continuity-speak `{26,30}`. Empty sets mean persistent bounded state is sufficient.

Expression V1 returns constraints only. HOLD has length 0, pace 0, directness 0.50, warmth 0.50, and no hesitation. SPEAK selects short/medium/long at expression-pressure thresholds `-0.25/0.45`, with `pace=clip01(0.50+0.20*arousal-0.20*center(exhaustion))`, `directness=clip01(0.50+0.25*agency-0.20*uncertainty)`, and `warmth=clip01(0.50+0.25*affiliation+0.15*valence)`. CLARIFY is short with pace 0.45, directness 0.75, warmth `clip01(0.50+0.20*affiliation)`; hesitation is allowed only when uncertainty is above `0.55` and the same style signature was not used in either of the previous two turns. REACH is short below affiliation `0.60`, otherwise medium, with pace 0.40, directness 0.45, and warmth `clip01(0.70+0.20*affiliation)`. No literal opening text is stored or emitted. The style ring holds exactly four structural signatures; when a candidate matches either of the last two, hesitation becomes false and length moves one bucket shorter.

Action belief V1 uses `g=0.85`, `V=0.25`, `R=0.20`, parameter covariance diagonal `(0.10,0.10)`, count 0, baseline 0, `q_theta=1e-4`, and `reward_scale=1.0`. Bias vectors in axis order are:

```python
ACTION_BIAS = {
    "SPEAK": (0.05, 0.05, 0.05, 0.08, -0.05, 0.05, 0.03, 0.08),
    "HOLD": (0.00, -0.05, 0.08, 0.00, -0.05, -0.05, 0.05, -0.08),
    "CLARIFY": (0.00, 0.00, 0.05, 0.02, -0.12, 0.02, 0.02, -0.02),
    "REACH": (0.05, 0.05, 0.03, 0.12, -0.03, 0.08, 0.02, 0.10),
}
```

Settlement computes `r_preference` only when at least one outcome dimension is valid; otherwise credit is censored. If structured `quality_score` is invalid, `reward=r_preference`. Otherwise `reward=clip(0.70*r_preference+0.30*(2*quality_score-1),-1,1)`. No implicit weighted-mean helper or alternative normalization is allowed.

`PREFERENCE_REVISION`, `OUTCOME_PROJECTOR_REVISION`, and `ACTION_MODEL_REVISION` are all `sylanne.v3.formula.v1`. Workspace evidence is `clip(2*(support_a-mean_legal_support),-2,2)`. Autonomous refractory state is `rho_HOLD=rho_REACH=0` initially; each committed turn first applies `rho_decay=0.80*rho`, scores penalty `2*rho_decay` only for HOLD/REACH in PROACTIVE/IDLE, then adds `0.35` to the selected HOLD/REACH state in those contexts and clips to `[0,1]`. ADDRESSED/AMBIENT only decay it. `rho_a` is unrelated to likelihood variance `R_a`.

Rows of every matrix are target axes and columns are source axes. The Jacobian gate constructs the entrywise absolute upper-bound 24x24 block matrix using `|tanh'|<=1`, then proves `||J||2 <= sqrt(||J||1*||J||inf) < 0.995`; no sampled estimate is accepted.

Compute profiles are exact tuples `(snn_enabled,K,stdp_enabled,reuse_last_summary)`:

```python
FULL_24_STDP = (True, 24, True, False)
FULL_24_NO_STDP = (True, 24, False, False)
SNN_16_NO_STDP = (True, 16, False, False)
REUSE_LAST_SNN_SUMMARY = (False, 0, False, True)
DETERMINISTIC_CONTINUOUS_ONLY = (False, 0, False, False)
```

Bridge `LoadSnapshotV1` contains global queue fill ratio, oldest job age milliseconds, recent committed compute p95 over at most 64 samples, and repository admission state. Degrade immediately at `(fill,age_ms,p95_ms)` thresholds `(0.25,25,2.5)`, `(0.50,50,3.5)`, `(0.70,100,5.0)`, `(0.85,200,8.0)`, and `(1.0,500,inf)` for the ladder above through SKIP. Recovery moves at most one level after 32 consecutive snapshots below 80% of the entry thresholds. REUSE without a prior valid summary becomes DETERMINISTIC_CONTINUOUS_ONLY. Repository hard-stop always becomes SKIP and records DROPPED.

## Planned Files

Pure core:

```text
sylanne_alpha/v3core/__init__.py
sylanne_alpha/v3core/canonical.py
sylanne_alpha/v3core/contracts.py
sylanne_alpha/v3core/formula_v1.py
sylanne_alpha/v3core/features.py
sylanne_alpha/v3core/orchestrator.py
sylanne_alpha/v3core/observation/{__init__.py,models.py,encoder.py}
sylanne_alpha/v3core/dynamics/{__init__.py,models.py,multiscale.py}
sylanne_alpha/v3core/spiking/{__init__.py,coding.py,reservoir.py,plasticity.py}
sylanne_alpha/v3core/workspace/{__init__.py,models.py,competition.py}
sylanne_alpha/v3core/inference/{__init__.py,models.py,policy_scorer.py}
sylanne_alpha/v3core/expression/{__init__.py,policy.py}
sylanne_alpha/v3core/learning/{__init__.py,outcomes.py,replay.py}
sylanne_alpha/v3core/state/{__init__.py,models.py,transition.py,seed.py,codec.py}
sylanne_alpha/v3core/effects/{__init__.py,models.py}
sylanne_alpha/v3core/trace/{__init__.py,models.py,canonical.py}
```

Host bridge:

```text
sylanne_alpha/v3bridge/__init__.py
sylanne_alpha/v3bridge/build_flags.py
sylanne_alpha/v3bridge/limits.py
sylanne_alpha/v3bridge/models.py
sylanne_alpha/v3bridge/session_identity.py
sylanne_alpha/v3bridge/observation_adapter.py
sylanne_alpha/v3bridge/memory_view_adapter.py
sylanne_alpha/v3bridge/group_view_adapter.py
sylanne_alpha/v3bridge/actual_action.py
sylanne_alpha/v3bridge/turn_registry.py
sylanne_alpha/v3bridge/profile_selector.py
sylanne_alpha/v3bridge/runtime_telemetry.py
sylanne_alpha/v3bridge/comparator.py
sylanne_alpha/v3bridge/_state_repository.py
sylanne_alpha/v3bridge/effect_committer.py
sylanne_alpha/v3bridge/migration_coordinator.py
sylanne_alpha/v3bridge/shadow_supervisor.py
sylanne_alpha/v3bridge/integration.py
sylanne_alpha/v2core/shadow_snapshot.py
```

Existing integration files:

```text
main.py
sylanne_alpha/llm_request_pipeline.py
sylanne_alpha/llm_response_pipeline.py
sylanne_alpha/v2core/integration.py
sylanne_alpha/proactive_bridge.py
scripts/package_plugin.py
requirements.txt
metadata.yaml
CHANGELOG.md
```

Tests stay flat under `tests/test_v3_*.py`, matching the repository. `tests/fixtures/v3_replay_synthetic_v1.jsonl` is synthetic and tracked; real G1 stays ignored at `artifacts/v3/evidence/g1/real-history-v1.jsonl`. Encoded JSONL is a tagged union. Each `episode_header` contains schema/provenance, random dataset ID, evaluation-group reference, episode reference, split, canonical `neutral_eval_v1` initial-state bytes/digest, boundary-censored pending credit, fixed evaluation-profile ID/digest, gate-manifest digest, and episode seed. Each `turn` contains episode reference/index, 36 normalized values, 36-bit validity mask, context class, actual action, sequence, `credit_adjacency`, dropped/unmatched-gap count, observed profile ID/digest when available, keyed source-record digest, and row digest. Replay always resets to the frozen header state; G3 runtime state is diagnostic and never guessed as an offline initial state.

Seed derivation matches the design exactly. `episode_seed` is the first 128 bits of `SHA256(b"SYL3\x01EVAL\x00" || dataset_id || evaluation_group_ref || episode_ref || gate_manifest_digest || formula_digest || model_digest || profile_digest)` under canonical length framing. A control's episode seed appends only its length-framed control ID to that same episode framing. Per-turn core randomness is separately named `evaluation_turn_seed=first128(SHA256(b"SYL3\x01EVALTURN\x00" || framed(selected_episode_or_control_seed) || framed(episode_turn_index)))`; turn index never changes the episode/control seed itself.

Two keys have separate lifetimes. A permission-restricted ignored `artifacts/v3/evidence/evaluation-link.key` is created once for the evaluation campaign and retained through G4; it length-frames privacy scope/session identity to produce a stable evaluation-group reference and split across G1/G3. Every export uses a separate fresh source-digest key, records only its digest, and destroys it after freeze. State, learning, shuffling, and bootstrap resampling reset/group by episode reference, while train/dev/test exclusion is by stable evaluation-group reference. Raw text, raw IDs, prompts, replies, memory strings, plain source hashes, secrets, and unhashed source paths are forbidden from both tracked and ignored encoded datasets.

## Task 1: Contracts, Formula Manifest, Import Firewall, And Budget

**Files:** Create `sylanne_alpha/v3core/{__init__.py,canonical.py,contracts.py,formula_v1.py}`, `sylanne_alpha/v3core/effects/{__init__.py,models.py}`, `sylanne_alpha/v3core/state/{__init__.py,models.py}`, `sylanne_alpha/v3bridge/{__init__.py,build_flags.py,limits.py,models.py}`, `tests/test_v3_contracts_boundaries.py`.

- [ ] **RED:** Add tests that import the named constants and assert 36/24/96 dimensions, frozen dataclasses, `TurnSequence(writer_epoch, local_sequence)` partitioned by SessionRef, `TurnEnvelope` without deadline/host objects, the closed effect union, the plugin-wide 50 MB cap, dominant effective v3 24 MB admission cap, non-simultaneous individual ceilings, and AST import firewall.

```python
def test_v3core_import_firewall() -> None:
    forbidden = {
        "astrbot", "sylanne_alpha.v2core", "sylanne_alpha._engine", "asyncio", "time", "logging",
        "os", "pathlib", "io", "tempfile", "shutil", "socket", "subprocess", "threading",
        "concurrent.futures", "portalocker",
    }
    for path in Path("sylanne_alpha/v3core").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = imported_module_names(tree)
        assert not any(name == item or name.startswith(item + ".") for name in imports for item in forbidden)
        assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open" for node in ast.walk(tree))
```

- [ ] Run `python -m pytest -q tests/test_v3_contracts_boundaries.py`; expect import failure for missing v3 modules.
- [ ] **GREEN:** Implement the frozen enums/dataclasses, minimal closed effect union, PendingOutcome/V3State models, and exact manifest/budget above. Recursively reject callable, Path/file handle, asyncio primitive, and arbitrary host objects from TurnEnvelope/CoreInvocation/EffectBundle. `build_flags.py` contains only `V3_SHADOW_ENABLED = False` and `BUILD_CHANNEL = "source"`.
- [ ] Run the test plus `python -m ruff check sylanne_alpha/v3core sylanne_alpha/v3bridge tests/test_v3_contracts_boundaries.py`.
- [ ] Commit locally: `git commit -m "feat(v3): freeze core contracts and formula manifest"`.

## Task 2: Hook/Correlation Matrix And Frozen V2 Exporters

**Files:** Create `sylanne_alpha/v2core/shadow_snapshot.py`, `tests/integration/test_v3_astrbot_v4265_hook_order.py`, `tests/test_v3_seed_snapshot.py`. Do not wire production hooks in this task.

- [ ] **RED:** Parameterize ordinary, tool-loop, repeated provider response, streaming, media, SILENT, provider exception, unaddressed group, and proactive turns. Assert one capture/one terminal claim when provable and `UNMATCHED_RESPONSE` otherwise. Assert no `event.set_extra` call is made by v3.

```python
@pytest.mark.parametrize("case,expected", [
    ("ordinary", "UNKNOWN"), ("silent", "HOLD"), ("fallback", "UNKNOWN"), ("tool_loop", "UNKNOWN"),
    ("segmented_success", "SPEAK"),
    ("partial_send", "UNKNOWN"), ("unaddressed_group", "UNMATCHED_RESPONSE"),
])
def test_hook_matrix_uses_only_structured_terminal_evidence(case: str, expected: str) -> None:
    assert run_hook_case(case).actual_action == expected
```

- [ ] Run the real-source matrix with `$env:ASTRBOT_SRC=(Split-Path -Parent (python -c "import astrbot,inspect; print(inspect.getfile(astrbot))")); python -m pytest -q tests/integration/test_v3_astrbot_v4265_hook_order.py`. Pin expected source version/hash in the test and inspect `on_llm_request`, `on_llm_response`, `on_decorating_result`, `after_message_sent`, tool loops, and streaming.
- [ ] **GREEN:** Add frozen `V2TurnObservationSnapshotV1`, `V2SeedSnapshotV1`, and `V2ResponseCandidateV1` plus two seed paths: synchronous `freeze_seed_snapshot_owned(rt)` for callers already holding the real v2 lock, and `await freeze_seed_snapshot_fallback(plugin,session_key)` for migration when no owned DTO exists. The fallback acquires `plugin._session_lock(session_key)`, copies/cleans facts, releases it, and performs no v3 lock/repository work.
- [ ] Freeze the normal request snapshot after assessment dispatch/history/gap/memory/group facts are already available and before final prompt assembly. Exporters accept those facts explicitly; they never reread SocialField, memory, request, or event later. This task proves the hook matrix and DTOs only; Task 13 performs production wiring after registry/supervisor exist.
- [ ] SILENT is terminal HOLD evidence. Only structured `ReplyKind.SPEAK` becomes a candidate; FALLBACK, tool/attachment/partial/cancelled/missing provenance remains UNKNOWN. On pinned AstrBot 4.26.5, ordinary `after_message_sent` is attempt/lifecycle evidence only: `RespondStage` catches `event.send()` failures and still invokes it, so ordinary delivery remains UNKNOWN without an independent structured success receipt. Segmented/takeover delivery requires its own all-segments-success callback (including one-segment takeover), and any failed/cancelled segment stays UNKNOWN. CLARIFY requires a future explicit marker. Proactive REACH requires structured `dispatched=True`.
- [ ] Run both tests and existing `tests/test_v2core_bridge.py`, `tests/test_context_integrity_silent_history.py`, `tests/test_tool_call_pairing.py`.
- [ ] Commit locally: `git commit -m "feat(v3): expose frozen v2 shadow facts"`.

## Task 3: Session Identity, Turn Registry, And Sequence Ledger

**Files:** Create `sylanne_alpha/v3bridge/session_identity.py`, `turn_registry.py`, `actual_action.py`, `tests/test_v3_session_identity.py`, `tests/test_v3_turn_registry.py`.

- [ ] **RED:** Assert length-framed HMAC distinguishes `("qq","a:b")` from `("qq:a","b")`; raw IDs never appear in filenames/state/trace. Assert duplicate response claims, object-identity lookup, FIFO guessing, and stale TTL entries are rejected. Replace Task 2's declarative `_claim_counts` matrix with the real bounded registry and prove one capture/one accepted terminal claim under duplicate callbacks.
- [ ] **RED:** Assert sequences never repeat within one `SessionRef`/epoch, distinct sessions may both allocate `(epoch,1)` without ledger collision, `(new_epoch,1) > (old_epoch,n)` only within the same session, cross-session interleaving does not break adjacency, reload censors pending credit, and same-session DROPPED gaps disable adjacency.
- [ ] **GREEN:** Implement full 256-bit HMAC `SessionRef`, key ID/rotation namespace, bounded registry state machine, `TurnHandle`, per-SessionRef `SequenceLedger`, and in-memory epoch-local per-session atomic allocators. Missing stable `(platform_id, unified_msg_origin, message_id)` yields unmatched telemetry and no job.
- [ ] Run `python -m pytest -q tests/test_v3_session_identity.py tests/test_v3_turn_registry.py`.
- [ ] Commit locally: `git commit -m "feat(v3): add fenced turn identity and registry"`.

## Task 4: Windows Repository Durability And CAS/ABA

**Files:** Create `sylanne_alpha/v3bridge/_state_repository.py`, `tests/test_v3_repository_cas.py`, `tests/test_v3_repository_multiprocess.py`; modify `requirements.txt`.

- [ ] **RED:** Spawn two processes against one `tmp_path`; assert one monotonic epoch winner and one CAS winner. Fault-inject before/after serialize, flush, fsync, close, replace, and pointer publication. Assert old generation/revision cannot hit a replacement generation. Assert repository `payload_digest` hashes canonical cognitive payload bytes only and is unchanged by trace/envelope metadata, so it cannot include itself. Under the cross-process budget lock, two simultaneous commits cannot both reserve the same free bytes or exceed `effective_v3_hard` after old+staging+new overhead.

```python
def test_old_generation_cannot_commit_after_quarantine_aba(tmp_path: Path) -> None:
    repo = StateRepository(tmp_path)
    old = repo.create_generation(session_ref(), epoch=repo.acquire_epoch())
    replacement = repo.quarantine_and_replace(old.pointer, seed_record())
    assert repo.compare_and_commit(old.precondition, next_record()) is CommitResult.STALE_STATE_GENERATION
    assert replacement.pointer.state_generation_id != old.pointer.state_generation_id
```

- [ ] Add `portalocker>=2.10` to `requirements.txt`; do not pin with `==`. Use it only in v3bridge repository lock scope.
- [ ] **GREEN:** Implement durable journal staging as budget-lock usage scan/atomic peak reservation -> write -> flush -> `os.fsync` -> close -> bounded `os.replace` retry for Windows sharing violations -> parent-directory sync where supported -> pointer CAS -> reservation release. Document guarantee as process/OS crash recovery; do not claim storage-device power-loss durability where the platform cannot prove it.
- [ ] Enforce all explicit results: COMMITTED, ALREADY_MIGRATED, DUPLICATE_TURN, STALE_EPOCH, STALE_STATE_GENERATION, REVISION_CONFLICT, BASE_DIGEST_MISMATCH, STALE_SEQUENCE, CORRUPT_BASE. Retain current+previous revision, cap staging, and recover orphan staging without publishing it.
- [ ] Run the repository tests on Windows and Linux when available.
- [ ] Commit locally: `git commit -m "feat(v3): add durable fenced shadow repository"`.

## Task 5: Observation Encoder And Outcome Projection

**Files:** Create `sylanne_alpha/v3core/observation/{__init__.py,models.py,encoder.py}`, `sylanne_alpha/v3bridge/observation_adapter.py`, `memory_view_adapter.py`, `group_view_adapter.py`, `tests/test_v3_observation_encoder.py`, `tests/test_v3_bridge_adapters.py`.

- [ ] **RED:** Assert exactly 36 finite values/bits, every table normalization, UNKNOWN action clearing 32-35, mutually exclusive context, and non-interference when only an invalid default value changes.
- [ ] **RED:** Assert MemoryView/GroupView consume already-authorized facts only and cannot call DB, recall, LLM, callback, or live domain. Cross-group disabled produces invalid facts.
- [ ] **GREEN:** Implement the approved 0..35 schema, valid-mask gates, `TurnContextClass`, semantic defaults, deterministic bridge projections, and 8-axis OutcomeFrame formulas.
- [ ] Run both tests and `tests/test_bodysnapshot_warmth_mapping.py`.
- [ ] Commit locally: `git commit -m "feat(v3): encode immutable shadow observations"`.

## Task 6: Seed, State Codec, And Global Size Gate

**Files:** Modify `sylanne_alpha/v3core/state/{__init__.py,models.py}`; create `sylanne_alpha/v3core/state/{seed.py,codec.py}`, `tests/test_v3_state_seed.py`, `tests/test_v3_state_codec.py`, `tests/test_v3_state_budget.py`.

- [ ] **RED:** Assert pure SeedProjector imports no v2 type, creates 24 bounded values, and neutral missing facts remain neutral. Assert malformed length/shape/CRC/nonfinite/Dale data fails closed.
- [ ] **RED:** Construct worst-case SNN, action beliefs, PendingOutcome, 64 experiences, and headers; assert target <=48 KiB and hard rejection >64 KiB.
- [ ] **GREEN:** Implement canonical packed float16/int16 arrays, unsigned observation bytes, signed reward/features, packed masks/actions, CRC, zlib/base64, shape/version headers, 64-entry FIFO, and state-generation fields.
- [ ] Run all three tests.
- [ ] Commit locally: `git commit -m "feat(v3): add bounded seed and state codec"`.

## Task 7: Multi-Timescale Dynamics

**Files:** Create `sylanne_alpha/v3core/features.py`, `dynamics/{__init__.py,models.py,multiscale.py}`, `tests/test_v3_multiscale_dynamics.py`.

- [ ] **RED:** Assert exact 8x3=24 state, approved formula constants, semantic-default zero drive, invalid channels excluded, same revision advances once, and the manifest Jacobian gate passes.
- [ ] **GREEN:** Implement sparse matrix helpers without NumPy, fast/mid/slow updates, finite/bound checks, and deterministic fallback to previous state.
- [ ] Run `python -m pytest -q tests/test_v3_multiscale_dynamics.py`.
- [ ] Commit locally: `git commit -m "feat(v3): implement bounded multiscale dynamics"`.

## Task 8: Sparse SNN, LIF, And STDP

**Files:** Create `sylanne_alpha/v3core/spiking/{__init__.py,coding.py,reservoir.py,plasticity.py}`, `tests/test_v3_spike_coding.py`, `tests/test_v3_lif_reservoir.py`, `tests/test_v3_stdp_plasticity.py`.

- [ ] **RED:** Assert invalid channels emit no spikes, 36x3 coding, K=16/24/32 decay equivalence, deterministic topology 96=77+19, no self-loop, finite bounds, and 16 summaries.
- [ ] **RED:** Assert only E-to-E plasticity, originating profile/action credit gates, one-shot eligibility settlement, canonical synapse-order budget projection, Dale signs, and incoming L1 <=1.2 after every update.
- [ ] **GREEN:** Implement coding/LIF/threshold/eligibility/STDP exactly from the approved spec and frozen formula manifest. Any nonfinite SNN value rolls back the complete SNN subtransaction.
- [ ] Run all three tests and a fixed 10,000-turn saturation smoke.
- [ ] Commit locally: `git commit -m "feat(v3): add deterministic sparse spiking path"`.

## Task 9: Workspace, PolicyScorerV1, Outcome Learning, Expression

**Files:** Create `workspace/{__init__.py,models.py,competition.py}`, `inference/{__init__.py,models.py,policy_scorer.py}`, `expression/{__init__.py,policy.py}`, `learning/{__init__.py,outcomes.py}`, `state/transition.py`, `tests/test_v3_workspace.py`, `tests/test_v3_policy_scorer.py`, `tests/test_v3_outcome_learning.py`, `tests/test_v3_expression_policy.py`.

- [ ] **RED:** Assert workspace capacity, registration-order invariance, empty/single/top1/top2 paths, exact ties, inhibition, and separate source/style refractory.
- [ ] **RED:** Assert four context masks/priors, closed-form KL/ambiguity/Jacobian information gain with denominator `V+R`, legal-only softmax, fallback order, diagonal posterior, bounded EKF, actual-action-only learning, and exact `rho_HOLD/rho_REACH` initialization, decay, context/action mask, pre-score penalty, post-selection increment, and bounds.
- [ ] **RED:** Assert ExpressionPolicy returns only numeric/bucket constraints, never literal reply text or deterministic hesitation prefixes.
- [ ] **GREEN:** Implement the frozen proposal formulas/keys, competition as `ProposalArbiterV1`, reservoir output as `ReservoirFeaturesV1`, `PolicyScorerV1`, posterior/EKF, preference density, PendingOutcome settlement, baseline, and four-signature expression ring. Do not expose `GlobalWorkspace`, `ActiveInferencePolicy`, or meaningful-temporal-learning aliases before G4 gates pass.
- [ ] Run all four tests.
- [ ] Commit locally: `git commit -m "feat(v3): add workspace policy and expression constraints"`.

## Task 10: Orchestrator, Canonical Trace, Replay, And Scalar Performance Proof

**Files:** Modify `sylanne_alpha/v3core/effects/{__init__.py,models.py}`; create `sylanne_alpha/v3core/trace/{__init__.py,models.py,canonical.py}`, `sylanne_alpha/v3core/learning/replay.py`, `sylanne_alpha/v3core/orchestrator.py`, `tests/test_v3_orchestrator.py`, `tests/test_v3_trace_replay.py`, `tests/test_v3_scalar_performance.py`.

- [ ] **RED:** Assert stage order, immutable ComputeProfile, closed effects, no side effects, deterministic degradation, byte-identical trace under the same fingerprint, and the acyclic digest order payload -> trace -> journal. `ExperienceBuffer` stores a committed revision key, never a same-turn trace digest.
- [ ] **RED:** Assert read-only replay leaves cognitive bytes unchanged and metric identity is `(entry_digest,evaluator_version)`; replay-STDP is impossible.
- [ ] **RED:** Warm up and measure 96 neurons at K=16/24/32 plus dynamics/workspace/policy/trace serialization separately from repository fsync. Record p50/p95/p99; fail the declared target gate only under `SYLANNE_V3_PERF_GATES=1` on the 2-core target.
- [ ] **GREEN:** Implement core orchestration as pure named stages. Every required numeric trace value is preserved using versioned packed/base64 fixed-shape arrays; digests/counts may accompany but never replace required values. Prove the worst-case canonical trace is <=16 KiB. If complete canonical bytes exceed the cap, reject the invocation and commit neither state nor core trace; record only bounded runtime telemetry.
- [ ] Run the three tests and save encoded benchmark JSON with environment fingerprint.
- [ ] Commit locally: `git commit -m "feat(v3): orchestrate deterministic shadow decisions"`.

## Task 11: EffectCommitter, Migration, And Recovery

**Files:** Create `effect_committer.py`, `migration_coordinator.py`, `tests/test_v3_effect_committer.py`, `tests/test_v3_migration.py`.

- [ ] **RED:** Assert every non-v3 effect is `SUPPRESSED_SHADOW`, state+trace share one durable journal record, >64 KiB rejects without pointer change, and only EffectCommitter imports `_state_repository`.
- [ ] **RED:** Assert one atomic SeedRecord+initial state+receipt+trace commit; no visible provisional revision; v2 lock release precedes v3 lock; concurrent migration produces one seed; all five recovery rows; learned state is never reprojected. After at least three learned commits and revision compaction, the immutable generation seed anchor must still exist, count against the budget, and recover a corrupt cognitive payload without rereading v2.
- [ ] **GREEN:** Implement committer and migration coordinator. The concrete v2 lock mapping is `plugin._session_lock(session_key)`, not `v2core.session_store.SessionLocks.turn`.
- [ ] Run both tests plus multiprocess repository tests.
- [ ] Commit locally: `git commit -m "feat(v3): commit and migrate shadow state atomically"`.

## Task 12: Private Executor, Profiles, Supervisor, And Lifecycle Leak Proof

**Files:** Create `profile_selector.py`, `runtime_telemetry.py`, `comparator.py`, `shadow_supervisor.py`, `integration.py`, `tests/test_v3_shadow_supervisor.py`, `tests/test_v3_lifecycle.py`.

- [ ] **RED:** Assert `offer()` is bounded and non-awaiting, every session is serial, one private worker provides fair global round-robin service across non-empty session queues without starvation, profile is frozen before core, deadline checks occur only between stages, timeout leaves no state/trace, and an old epoch cannot publish.
- [ ] **RED:** Assert initialize/terminate idempotence and exact shutdown order: stop admission/detach -> mark unqueued dropped -> cancel replay/metric -> bounded drain -> close committer admission -> seal epoch -> cancel leftovers -> `gather(..., return_exceptions=True)` every tracked task -> `executor.shutdown(wait=True, cancel_futures=True)` -> clear registries.
- [ ] **RED:** Repeat load -> one turn -> shutdown 50 times and compare thread/task/file-handle counts with baseline; zero v3 worker/task/lock/registry leak is required.
- [ ] **GREEN:** Use `ThreadPoolExecutor(max_workers=1, thread_name_prefix="sylanne-v3")`; cross-session execution is deliberately serialized. Do not put v3 futures/tasks into `plugin._background_tasks`. Core stages contain no callbacks or unbounded loops. Shutdown calls `executor.shutdown(wait=True, cancel_futures=True)` after fencing publication and does not return until every v3 worker thread has exited.
- [ ] Run supervisor/lifecycle tests.
- [ ] Commit locally: `git commit -m "feat(v3): supervise shadow work off the event loop"`.

## Task 13: Main And Proactive Host Wiring

**Files:** Modify `main.py`, `llm_request_pipeline.py`, `llm_response_pipeline.py`, `v2core/integration.py`, `proactive_bridge.py`; create `tests/test_v3_main_wiring.py`, `tests/test_v3_grey_isolation.py`.

- [ ] **RED:** Instantiate the real plugin with fake host managers. Assert shadow-disabled and shadow-enabled runs have byte-identical v2 reply/prompt/history/memory/body snapshots and identical tool/LLM call counts.
- [ ] **RED:** Inject queue full, read-only repository, lock timeout, core exception, executor timeout, and duplicate hooks; all seven isolation counters remain zero and v2 completes.
- [ ] **GREEN:** `__init__` creates a facade without IO. `initialize()` acquires epoch before worker start and fail-closes v3 only. `terminate()` calls `begin_shutdown()` first, lets existing v2 save drain, then awaits v3 shutdown before the current generic task cancellation.
- [ ] Request capture occurs after merged text, assessment dispatch, history depth, gap, memory, and authorized group facts are available and before final prompt assembly; all are passed explicitly as immutable facts. SILENT finalizes HOLD. FALLBACK is always UNKNOWN. Ordinary AstrBot 4.26.5 output remains UNKNOWN because `after_message_sent` is not a success receipt; the hook may close lifecycle bookkeeping but cannot settle action credit. Segmented/takeover output has a dedicated all-segments-success callback; partial delivery, a failed segment, or cancellation stays UNKNOWN. Proactive `dispatched=True` confirms REACH. Every ambiguous case is UNKNOWN/skip. Never write v3 identity into `event.extra`.
- [ ] **RED:** Cover FALLBACK after a valid candidate, all-segments success, first-segment failure, second-segment failure, cancellation between segments, and duplicate terminal callbacks; only complete structured delivery may settle SPEAK once.
- [ ] Run the two tests and the existing request/response/history/tool/realtime regression cluster.
- [ ] Commit locally: `git commit -m "feat(v3): wire isolated grey shadow lifecycle"`.

## Task 14: Grey/Stable Artifact Channel Contract

**Files:** Modify `scripts/package_plugin.py`; create `tests/test_v3_package_channel.py`.

- [ ] **RED:** Build both channels, unzip, and import `build_flags.py`; assert grey is true, stable false, source false, each archive contains exactly one `sylanne_alpha/v3bridge/build_flags.py`, and neither `_conf_schema.json` nor UI/API schema contains a v3 selector. Build stable only against a temporary stable metadata copy; stable packaging must reject grey metadata.
- [ ] **GREEN:** Add required `--channel grey|stable`. Generated `sylanne_alpha/v3bridge/build_flags.py` replaces the source archive entry rather than appending a duplicate. `sylanne_build_manifest.json` contains channel, metadata version, git commit, generated-file digest, and `payload_digest`.
- [ ] Define `payload_digest` as SHA-256 over archive entries sorted by UTF-8 path bytes, excluding `sylanne_build_manifest.json`, framed as unsigned big-endian `u32(path_utf8_byte_len) || path_utf8_bytes || u64(content_len) || uncompressed_entry_bytes`. After the final zip is closed, write its whole-file SHA-256 to the adjacent `<archive>.sha256`; never place a whole-zip digest inside the zip. An independent test implementation recomputes both digests.
- [ ] Normalize archive paths to forward-slash UTF-8 NFC, reject case-fold collisions, use one fixed timestamp/permission/compression policy, and make repeated builds from the same tracked tree byte-identical. Stable-channel tests use temporary metadata version `2.5.0` and a test-only output path; the checked-in `2.5.0-grey.6` metadata must be rejected for stable packaging.
- [ ] Refuse packaging if any tracked archive input differs from committed HEAD, grey metadata/channel disagree, stable metadata/channel disagree, generated flag/channel disagree, any v3 source is untracked, duplicate archive paths exist, or `_engine` identity/runtime files enter the archive. Unrelated untracked files outside the archive input set remain untouched and excluded.
- [ ] Run package-channel tests and inspect both archives.
- [ ] Commit locally: `git commit -m "build: add explicit grey shadow artifact channel"`.

## Task 15: Encoded G1 Export And Pre-Candidate Gates

**Files:** Create `tests/test_v3_property_invariants.py`, `tests/test_v3_stability_gate.py`, `tests/test_v3_privacy.py`, `tests/test_v3_performance_gate.py`, `tests/test_v3_encoded_export.py`, `scripts/v3_export.py`, `scripts/v3_replay.py`, `scripts/v3_ablation.py`, `scripts/v3_stability.py`, `tests/fixtures/v3_replay_synthetic_v1.jsonl`, `tests/fixtures/v3_replay_synthetic_v1.manifest.json`, `tests/fixtures/v3_gate_manifest_v1.json`. Real G1 outputs are ignored evidence, not tracked files.

- [ ] **RED/GREEN:** Mandatory seeded property loops cover malformed streams, 36/24/96 shape, finite/bounds, invalid non-interference, Dale/L1, legal action, deterministic trace, and CAS single advance. They use fixed seeds and always run under pytest; do not call `pytest.importorskip`. Hypothesis may add coverage only when installed and may not be the sole implementation of any acceptance property.
- [ ] **RED/GREEN:** Privacy tests prove cross-group-off isolation and scan filename/state/trace/telemetry bytes for raw session IDs and secret markers. Test runtime HMAC key permissions/loss/rotation/framing aliases, evaluation-link key permissions/loss/mismatch, and source-digest key destruction. Neither evaluation key may enter Git or a package.
- [ ] **RED/GREEN:** `v3_export.py` reads local AstrBot history only from an explicitly supplied data directory, performs privacy projection before encoding, and writes no raw content. The manifest fixes schema/formula/model revisions, provenance class, random dataset ID, keyed source-corpus digest, row count, episode/group/split digests, evaluation-link key ID/digest, destroyed source-key digest, exporter commit, and canonical exporter-source digest. The export test rejects raw text/IDs, plain source hashes, digest mismatch, missing/invalid initial-state headers, cross-split evaluation groups, ambiguous gaps, mutable provenance, and any record outside the tagged schema.
- [ ] **RED/GREEN:** `test_v3_main_wiring.py::test_local_g2_shadow` writes a canonical G2 report to `SYLANNE_V3_GATE_REPORT` containing source/build channel, formula/model/runtime fingerprints, accepted/dropped/correlated counts, seven isolation counters, and report digest; the test fails if the requested report is missing or malformed.
- [ ] **RED/GREEN:** With `SYLANNE_V3_LONG_GATES=1`, run 100,000 synthetic normal/repeated/out-of-order/extreme/malformed turns; verify recovery envelopes, no all-speak/all-hold/winner lock/saturation, K JS divergence <0.02, and bounded state. This G0 synthetic gate makes no claim about conversational gain, learned-vs-control superiority, or calibration.
- [ ] **RED/GREEN:** With `SYLANNE_V3_PERF_GATES=1` on the target, require core p95<=2.5ms, event-path incremental p95<=5ms/p99<=15ms, throughput loss<5%, live/shared/disk budgets, and queue/registry caps.
- [ ] Freeze `v3_gate_manifest_v1.json` before G3. It declares `neutral_eval_v1`, `FULL_24_STDP`, the exact domain-separated episode/control seed derivation, chronological prequential evaluation on evaluation-group-disjoint train/dev/test splits, explicit gap/credit censorship, the three primary loss metrics and directions, whole-episode bootstrap with 10,000 resamples, 95% lower-bound >0, <=0.5% non-target regression, ECE<=0.10, observation-likelihood 68%/95% coverage error <=0.10/0.05, ESS>=200 overall, >=30 known examples/action, zero illegal/nonfinite actions and isolation counters, known-HOLD contradiction proxy degradation <0.5 percentage points, >=50% shuffle removal, and `INSUFFICIENT_EVIDENCE` failure semantics. Export and freeze G1, then run fixed real-history replay. Store reports exactly at `artifacts/v3/evidence/g0/stability.json`, `artifacts/v3/evidence/g1/replay.json`, `artifacts/v3/evidence/g1/ablation-preliminary.json`, and `artifacts/v3/evidence/g2/local-shadow.json`; each report embeds gate-manifest, dataset, and runtime-fingerprint digests.
- [ ] Run the mandatory Python-minor matrix exactly: `py -3.10 -m pytest -q tests/test_v3_property_invariants.py tests/test_v3_trace_replay.py`, followed by `py -3.10 scripts/v3_replay.py --dataset tests/fixtures/v3_replay_synthetic_v1.jsonl --report artifacts/v3/evidence/python310.json`; repeat both commands with `py -3.11`, `py -3.12`, and `py -3.13`, changing the report suffix accordingly. Then run `py -3.13 scripts/v3_replay.py --compare-python-reports artifacts/v3/evidence/python310.json artifacts/v3/evidence/python311.json artifacts/v3/evidence/python312.json artifacts/v3/evidence/python313.json --report artifacts/v3/evidence/python-cross-version.json` and require action/order equality plus declared numeric tolerances.
- [ ] After the tooling, synthetic fixture, and gate manifest tests pass, commit them locally before reading real history: `git commit -m "test(v3): add encoded evaluation gates"`. Real exports require no tracked diff, and their manifests must name this committed HEAD and matching exporter-source digest. Any exporter defect starts a RED/GREEN fix commit and a fresh export with a new dataset ID.
- [ ] Run G0/G1/G2 commands:

```powershell
$PY = 'C:\Users\pidan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$env:SYLANNE_V3_LONG_GATES = '1'
& $PY -m pytest -q tests/test_v3_property_invariants.py tests/test_v3_stability_gate.py tests/test_v3_privacy.py
& $PY scripts/v3_stability.py --seed 2718 --turns 100000 --report artifacts/v3/evidence/g0/stability.json
& $PY scripts/v3_export.py --astrbot-data-dir $env:ASTRBOT_DATA_DIR --evaluation-link-key artifacts/v3/evidence/evaluation-link.key --create-evaluation-link-key --output artifacts/v3/evidence/g1/real-history-v1.jsonl --manifest artifacts/v3/evidence/g1/real-history-v1.manifest.json
& $PY scripts/v3_replay.py --dataset artifacts/v3/evidence/g1/real-history-v1.jsonl --manifest artifacts/v3/evidence/g1/real-history-v1.manifest.json --gate-manifest tests/fixtures/v3_gate_manifest_v1.json --report artifacts/v3/evidence/g1/replay.json
& $PY scripts/v3_ablation.py --dataset artifacts/v3/evidence/g1/real-history-v1.jsonl --gate-manifest tests/fixtures/v3_gate_manifest_v1.json --controls learned,frozen,random,zero-lr --bootstrap 10000 --report artifacts/v3/evidence/g1/ablation-preliminary.json
$env:SYLANNE_V3_GATE_REPORT = 'artifacts/v3/evidence/g2/local-shadow.json'
& $PY -m pytest -q tests/test_v3_main_wiring.py -k "local_g2_shadow"
```

- [ ] Preliminary G1 metrics do not earn scientific aliases. Keep `ProposalArbiterV1`, `PolicyScorerV1`, and `ReservoirFeaturesV1` names through the first candidate.

## Task 16: Grey Version, Full Verification, And First Local Candidate

**Files:** Modify `metadata.yaml`, `CHANGELOG.md`; artifact output under ignored `dist/`.

- [ ] Set `metadata.yaml` to `2.5.0-grey.6` and add a concise grey.6 changelog. Keep `astrbot_version >=4.26,<5.0.0`; do not add a v3 config item.
- [ ] Run targeted tests: `python -m pytest -q tests/test_v3_*.py`.
- [ ] Run full tests: `python -m pytest -q`.
- [ ] Run `python -m ruff check sylanne_alpha/v3core sylanne_alpha/v3bridge tests/test_v3_*.py` and pyright on both packages.
- [ ] Run the AstrBot plugin validator on a clean tracked snapshot; require `0 errors` and adjudicate warnings.
- [ ] Require successful G0, frozen encoded G1, and local G2 reports from Task 15. G3/G4 are explicitly post-candidate and do not block this first local artifact.
- [ ] Run the target performance gate and preserve `artifacts/v3/evidence/performance.json`.
- [ ] Run `git diff --exit-code -- sylanne_alpha/_engine` and verify all seven isolation counters are zero.
- [ ] Perform an independent spec-compliance review followed by code-quality/red-team review. Resolve every finding and rerun affected gates. Commit the tracked release state locally: `git commit -m "chore(release): prepare 2.5.0-grey.6"`.
- [ ] With no tracked diff after that commit, build `python scripts/package_plugin.py --channel grey --output dist/astrbot_plugin_sylanne-2.5.0-grey.6.zip`; the manifest commit must equal this committed release HEAD. Unpack and smoke-load initialize/disable/enable/reload/terminate.
- [ ] Verify `dist/astrbot_plugin_sylanne-2.5.0-grey.6.zip.sha256`, independently recompute `payload_digest`, and assert one generated flag entry. If verification exposes a defect, start a RED/GREEN fix, commit it, rerun the full affected gates, and rebuild from the new clean committed HEAD; never retain an artifact whose manifest points before its final source commit.
- [ ] Verify branch status/ahead count and remote ref are unchanged except local commits. Do not push and do not emit any push/PR/release directive.

## Task 17: Post-Candidate G3 Capture And G4 Frozen Evaluation

**Files:** No tracked edits are planned. Read `scripts/v3_export.py`, `scripts/v3_replay.py`, and `scripts/v3_ablation.py`; write ignored evidence only under `artifacts/v3/evidence/g3/` and `artifacts/v3/evidence/g4/`. Any defect found here starts a separate RED/GREEN fix task before evaluation resumes.

- [ ] Run the local grey candidate and collect only turns with provable request/terminal correlation. Freeze encoded G3 without raw content:

```powershell
$PY = 'C:\Users\pidan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $PY scripts/v3_export.py --astrbot-data-dir $env:ASTRBOT_DATA_DIR --evaluation-link-key artifacts/v3/evidence/evaluation-link.key --require-existing-evaluation-link-key --require-build-channel grey --only-provable-correlation --output artifacts/v3/evidence/g3/grey-encoded.jsonl --manifest artifacts/v3/evidence/g3/grey-encoded.manifest.json
& $PY scripts/v3_ablation.py --dataset artifacts/v3/evidence/g1/real-history-v1.jsonl --dataset artifacts/v3/evidence/g3/grey-encoded.jsonl --gate-manifest tests/fixtures/v3_gate_manifest_v1.json --controls learned,frozen,random,zero-lr --shuffle-cross-turn --bootstrap 10000 --report artifacts/v3/evidence/g4/ablation.json
& $PY scripts/v3_replay.py --dataset artifacts/v3/evidence/g3/grey-encoded.jsonl --gate-manifest tests/fixtures/v3_gate_manifest_v1.json --calibration --report artifacts/v3/evidence/g4/calibration.json
& $PY scripts/v3_replay.py --assemble-g4 --gate-manifest tests/fixtures/v3_gate_manifest_v1.json --g1-manifest artifacts/v3/evidence/g1/real-history-v1.manifest.json --g3-manifest artifacts/v3/evidence/g3/grey-encoded.manifest.json --ablation artifacts/v3/evidence/g4/ablation.json --calibration artifacts/v3/evidence/g4/calibration.json --report artifacts/v3/evidence/g4/report.json
```

- [ ] G4 reports action coverage, effective sample size, Brier score, ECE, safety delta, event-order shuffle gain, learned/frozen/random/zero-LR controls, and bootstrap 95% intervals. Every result embeds the frozen G1 and G3 digests and writes `artifacts/v3/evidence/g4/report.json`.
- [ ] G4 assembly fails unless G1/G3 manifests share the same evaluation-link key ID/digest, evaluation groups never cross splits, every episode has a valid neutral initial-state header, and gap/credit censorship is explicit. The local evaluation-link key may be deleted only after the frozen G4 report and final review are complete.
- [ ] Only after the preregistered lower confidence bound is above zero and calibration/safety gates pass may a later version consider scientific aliases. G4 is input to the next version; it never mutates or silently promotes the current grey candidate.
- [ ] Repeat independent spec/code/red-team review over the frozen datasets and reports. Record all accepted, fixed, or rejected findings with reasons in `artifacts/v3/evidence/g4/review.json`.

## First-Candidate Acceptance Evidence

- All v3 targeted tests, all existing tests, ruff, pyright, and AstrBot validator pass.
- G0 synthetic invariants, frozen encoded G1 replay, local G2, latency, throughput, state/shared/disk budgets, and failure-matrix reports exist with digests. G3/G4 are not prerequisites for the first candidate.
- Shadow OFF/ON canary proves byte/count equality for v2 reply, prompt, history, memory, body tick, tools, and LLM calls.
- Seven isolation counters remain zero under normal, queue-full, timeout, repository failure, malformed input, reload, and shutdown.
- Same-fingerprint trace is byte-identical on Python 3.10-3.13; cross-fingerprint action/order equality and tolerances pass.
- Grey zip contains generated `V3_SHADOW_ENABLED=True`; stable-channel test zip and source contain false; the payload/whole-zip digests verify; no config/WebUI selector exists.
- `_engine/**` diff is empty.
- Only local commits exist; no push, tag, PR, or release occurred.

## G4 Completion Evidence

- G3 contains only provably correlated grey turns and is frozen as encoded facts with provenance and digest.
- G4 ablation/calibration reports include both frozen G1 and G3 digests, all preregistered controls, confidence intervals, and safety metrics.
- Final independent spec-compliance, code-quality, and red-team reviews have no unresolved blocker.
