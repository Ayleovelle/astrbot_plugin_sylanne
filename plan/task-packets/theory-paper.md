## Task Packet

- Scope: Rewrite `docs/theory.md` as a paper-style integrated theory document and add real-data explanatory figures.
- Files to read: `docs/theory.md`, `README.md`, `docs/remote_testing.md`, core engine files, benchmark summaries under `output/remote_emotion_benchmark_official/`, `docs/assets/lifecycle_model_fit_summary.csv`.
- Files allowed to edit: `docs/theory.md`, `README.md`, `scripts/package_plugin.py`, `tests/test_package_plugin.py`, selected documentation tests if needed, `plan/**`, `figures/**`, `docs/assets/theory_*`.
- Required skills: paper-orchestration, evidence-driven-writing, figures-python, auto-subagents.
- Evidence/data inputs: foundational references already listed in `docs/theory.md`; official gpt-5.5 feature matrix; no-emotion control; lifecycle model fit CSV.
- Required artifacts: paper document, figure data, figure script, SVG/PNG outputs, evidence map, coverage review, validation commands.
- Rejection checks: no fabricated citations; no mock data presented as real; no raw remote credentials; no developer-only README section in normal user path; no changes to `sub2api-fork*`.
- Validation commands: figure script, document math tests, package selection tests, remote README contract tests if touched, `git diff --check`.
