# Data Manifest

| Figure | Data file | Real/mock | Source | Script | Outputs |
| --- | --- | --- | --- | --- | --- |
| Figure 1 功能矩阵模块开销 | `figures/data/theory_feature_matrix.csv` | real remote benchmark aggregation | `output/remote_emotion_benchmark_official/remote-emotion-v050-gpt55-feature-state-layer-real/summary.json`; `output/remote_emotion_benchmark_official/remote-emotion-v050-gpt55-noemotion-control-state-layer-c3-250-real/summary.json` | `figures/theory/build_theory_figures.py` | `docs/assets/theory_feature_matrix_overhead.svg`; `docs/assets/theory_feature_matrix_overhead.png` |
| Figure 2 生命周期拟合解释 | `figures/data/theory_lifecycle_fit.csv` | real remote benchmark aggregation | `docs/assets/lifecycle_model_fit_summary.csv` | `figures/theory/build_theory_figures.py` | `docs/assets/theory_lifecycle_fit_explanation.svg`; `docs/assets/theory_lifecycle_fit_explanation.png` |

## Notes

- Figure 1 uses official gpt-5.5 feature matrix data with `2500/2500` valid feature samples and `0` failed requests, plus the official no-emotion control run.
- Figure 2 uses the already aggregated lifecycle fit CSV. Each model has `9` lifecycle samples, so it is an explanatory fit, not a high-power statistical test.
- Synthetic or mock data under `output/paper/**` is intentionally excluded.
