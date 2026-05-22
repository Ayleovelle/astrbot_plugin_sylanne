# Progress

## 2026-05-13

- Stage: S1/S3/S4 combined theory redraft with evidence and figures.
- Loaded skills: auto-subagents, using-research-writing, paper-orchestration, evidence-driven-writing, figures-python, XiaoJu.
- Started read-only subagents for theory mapping and benchmark-data discovery.
- Confirmed real data sources: official gpt-5.5 feature matrix, no-emotion control and lifecycle model fit summary.

### Capability-use audit

- Required skills: paper-orchestration, evidence-driven-writing, figures-python, auto-subagents.
- Skills actually used: paper-orchestration, evidence-driven-writing, figures-python, auto-subagents, XiaoJu.
- Inputs consumed: `docs/theory.md`, `README.md`, `docs/remote_testing.md`, official remote benchmark summaries, lifecycle fit CSV, subagent reports.
- Inputs not used and why: synthetic/mock paper data under `output/paper/**`, because it is explicitly not real benchmark evidence.
- Artifacts produced: `docs/theory.md`; `docs/assets/theory_feature_matrix_overhead.svg`; `docs/assets/theory_feature_matrix_overhead.png`; `docs/assets/theory_lifecycle_fit_explanation.svg`; `docs/assets/theory_lifecycle_fit_explanation.png`; `figures/theory/build_theory_figures.py`; `figures/data/*.csv`; README developer-folding update.
- Verification run: figure script; `python -m unittest tests.test_document_math_contract -v`; `python -m unittest tests.test_package_plugin tests.test_remote_smoke_contract -v`; `python -m unittest discover -s tests -v`; `python -m py_compile figures\theory\build_theory_figures.py scripts\package_plugin.py`; `git diff --check`.
- Remaining risk: lifecycle fit has low sample count and must be labeled cautiously; remote end-to-end latency is not pure local plugin cost.
