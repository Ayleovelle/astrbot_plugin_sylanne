# Grey.7 Release Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct the completed grey candidate from `2.5.0-grey.6` to `2.5.0-grey.7`, rebuild the local artifact from a committed tree, and produce a fact-checked grey-test announcement.

**Architecture:** This is a release-identity-only correction: keep runtime behavior unchanged while synchronizing the canonical version across `metadata.yaml`, `main.py`, release contracts, changelog, and active release plans. The package must then be rebuilt from the new clean commit so its embedded manifest points at the corrected source commit.

**Tech Stack:** Python 3.12, pytest, YAML/Markdown release metadata, deterministic ZIP packager.

---

### Task 1: Pin the corrected release identity

**Files:**
- Modify: `tests/test_release_ci_contract.py`
- Modify: `main.py`
- Modify: `metadata.yaml`

- [ ] **Step 1: Change the release contract to `2.5.0-grey.7`**
- [ ] **Step 2: Run `pytest tests/test_release_ci_contract.py -q` and confirm it fails on the old source identity**
- [ ] **Step 3: Synchronize `PLUGIN_VERSION`, `@register` version, metadata version, and metadata short description**
- [ ] **Step 4: Rerun the release contract and confirm it passes**

### Task 2: Correct release-facing documentation

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/superpowers/plans/2026-07-15-v3-shadow-grey-implementation.md`
- Modify: `docs/superpowers/plans/2026-07-22-model-authored-semantic-segmentation-implementation.md`

- [ ] **Step 1: Rename the active changelog entry to grey.7 and describe the semantic segmentation, provider consolidation, and v3 shadow changes actually present**
- [ ] **Step 2: Replace active candidate/package references from grey.6 to grey.7**
- [ ] **Step 3: Run a tracked-file search and confirm no stale grey.6 release identity remains**

### Task 3: Verify, commit, and rebuild

**Files:**
- Test: `tests/test_release_ci_contract.py`
- Test: `tests/test_v3_package_channel.py`
- Run: `scripts/package_plugin.py`

- [ ] **Step 1: Run Ruff and the release/package test suites**
- [ ] **Step 2: Run the 2718lab release self-check and assess every warning**
- [ ] **Step 3: Commit the corrected tracked state locally without staging unrelated untracked files**
- [ ] **Step 4: Build `Sylanne-2.5.0-grey.7.zip` from the committed tree**
- [ ] **Step 5: Verify archive SHA-256, manifest channel/version/commit, payload digest, and size**
- [ ] **Step 6: Deliver a full announcement and a short group-chat announcement; state that G3/G4 still require real grey data**
