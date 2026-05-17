# Sylanne Self-Arbitration Roadmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Sylanne's combined experimental self-scheduling release: read-only self-arbitration, offline experience review diagnostics, and read-only relationship candidate summaries.

**Versioning:** Ship all three features under one feature-iteration version with an experimental suffix, `2.8.0-exp`. Do not split these into `2.8.0`, `2.9.0`, and `3.0.0`; major version changes are reserved for revolutionary generation changes, minor version changes for feature iterations, and patch version changes for bug fixes or optimizations.

**Architecture:** Extend `integrated_self.py` as the read-only assembly layer instead of adding a parallel brain. Wire only short, bounded prompt fragments into `main.py`, keep replay and relationship summaries diagnostics/API-only, and make current user text outrank memory, shadow context, replay output, and relationship inference.

**Tech Stack:** Python 3.10+, existing AstrBot plugin lifecycle hooks in `main.py`, stdlib dict/list/dataclass-style payloads, pytest/unittest test suite, existing packaging preflight.

---

## Release strategy

Ship self-arbitration, offline experience review diagnostics, and read-only relationship candidate summary together as one combined release version. The internal task order remains staged for safety, but metadata, docs, package, commit, and release notes use one version number.

---

## Task 1: 2.8.0-exp integrated self-arbitration contract

**Files:**
- Modify: `integrated_self.py`
- Test: `tests/test_integrated_self.py`

- [ ] Add failing tests for `build_self_arbitration_intent_plan(...)` covering:
  - current user text priority is first;
  - technical/workflow requests choose tool-like task completion and suppress emotional expression;
  - low-signal or high-boundary turns prefer clarification/minimal silence;
  - memory/shadow context is advisory and bounded.
- [ ] Implement a compact read-only intent plan builder in `integrated_self.py`.
- [ ] Attach `intent_plan` to the existing snapshot payload without changing the public schema major version.
- [ ] Add `intent_plan` to diagnostics and prompt fragment using a short bounded block.
- [ ] Verify `tests/test_integrated_self.py` passes.

---

## Task 2: 2.8.0-exp request hook wiring and diagnostics

**Files:**
- Modify: `main.py`
- Test: `tests/astrbot_lifecycle_part15.py`
- Test: `tests/test_command_tools.py`
- Test: `tests/test_expression_policy.py`

- [ ] Add failing lifecycle test proving arbitration prompt is appended after interpretation/expression policy decisions and never replaces raw user text.
- [ ] Add failing runtime diagnostics test proving `understanding_closed_loop.intent_plan` is exposed read-only.
- [ ] Thread the current user text, interpretation candidates, expression policy, lifecycle audit, and integrated self snapshot into the arbitration builder.
- [ ] Inject only the compact intent fragment; do not add extra LLM calls.
- [ ] Keep default/neutral plans diagnostic-only if they would add noisy prompt text.
- [ ] Verify focused lifecycle, diagnostics, and expression-policy tests pass.

---

## Task 3: 2.8.0-exp offline experience replay diagnostics

**Files:**
- Modify: `integrated_self.py`
- Modify: `main.py`
- Test: `tests/test_integrated_self.py`
- Test: `tests/test_conversation_event_ledger.py`
- Test: lifecycle shard near `tests/astrbot_lifecycle_part15.py`

- [ ] Add failing tests for an offline `experience_review` result that flags likely misunderstanding, overused memory/shadow context, missed clarification, overactive tone, and emotional interference with technical work.
- [ ] Reuse sanitized replay bundle, closed-loop diagnostics, and ledger tail inputs.
- [ ] Expose review only through diagnostics/API payloads.
- [ ] Add lifecycle test proving replay review is not injected into the main prompt.
- [ ] Verify focused replay and lifecycle tests pass.

---

## Task 4: 2.8.0-exp read-only relationship candidate summary

**Files:**
- Modify: `lifelike_learning_engine.py`
- Modify: `integrated_self.py`
- Modify: `memory_engine.py` only for tests/guarding if needed; avoid default writes.
- Test: `tests/test_lifelike_learning_engine.py`
- Test: `tests/test_memory_engine.py`
- Test: group/lifecycle tests if a group isolation surface is touched.

- [ ] Add failing tests for relationship candidate summary fields: familiarity, trust, boundary comfort, repair state, evidence, confidence, expiry risk, and group/user isolation.
- [ ] Implement read-only candidate summary from existing lifelike/common-ground and relationship evidence.
- [ ] Add guard tests proving no long-term relationship narrative is written by default.
- [ ] Expose the summary through diagnostics/API only; do not default-inject into prompt.
- [ ] Verify focused lifelike, memory, and group isolation tests pass.

---

## Task 5: release docs, packaging, and full verification

**Files:**
- Modify: `metadata.yaml`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/release_branch_sync_checklist.md`
- Modify: `scripts/package_plugin.py` only if new root modules are created.
- Update: `dist/astrbot_plugin_sylanne.zip`

- [ ] Update version metadata and docs for the final completed release stage.
- [ ] Run focused test shards after each stage.
- [ ] Run full `python -m pytest -q`.
- [ ] Build package zip and run plugin zip preflight.
- [ ] Check git diff for whitespace issues.
- [ ] Commit and push after user requests commit, following project preference.
