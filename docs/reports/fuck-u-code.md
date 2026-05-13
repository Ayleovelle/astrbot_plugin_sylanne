# Fuck-U-Code 发酵报告

> powered by Fuck-U-Code；本报告由 `scripts/update_fuck_u_code_report.py` 根据官方 JSON 输出生成。

- 💩 发酵指数：`19.8/100`，官方评价：`😐 微臭青年`（由质量分反向换算，越低越好）
- 官方 JSON overallScore：`80.2/100`
- 扫描规模：`72/875` 个文件已分析，`802` 个文件被跳过
- 问题计数：critical `55`，error `155`，warning `182`
- 原始报告：`output/fuck_u_code/raw-report.json`
- 生成时间：`2026-05-13T21:53:26+00:00`

## 最需要除味的文件

| 💩 发酵 | 质量分 | critical | error | warning | 文件 |
| --- | --- | ---: | ---: | ---: | --- |
| 43.0/100 | 57.3/100 | 3 | 5 | 2 | `scripts/remote_emotion_benchmark_playwright.js` |
| 37.0/100 | 63.4/100 | 5 | 2 | 2 | `emotion_engine.py` |
| 30.0/100 | 70.3/100 | 4 | 3 | 2 | `memory_engine.py` |
| 26.0/100 | 73.6/100 | 2 | 4 | 2 | `personality_drift_engine.py` |
| 26.0/100 | 73.5/100 | 2 | 3 | 3 | `lifelike_learning_engine.py` |
| 26.0/100 | 74.4/100 | 1 | 4 | 4 | `figures/theory/build_theory_figures.py` |
| 25.0/100 | 75.3/100 | 2 | 3 | 1 | `tests/test_emotion_engine.py` |
| 24.0/100 | 76.3/100 | 2 | 3 | 4 | `fallibility_engine.py` |
| 24.0/100 | 76.1/100 | 2 | 2 | 3 | `tests/test_command_tools.py` |
| 23.0/100 | 76.9/100 | 1 | 3 | 3 | `tests/test_integrated_self.py` |
| 23.0/100 | 77.0/100 | 0 | 3 | 7 | `tests/test_package_plugin.py` |
| 22.0/100 | 77.6/100 | 2 | 2 | 3 | `tests/public_api_memory_part07.py` |

## 读数说明

README 徽章里的“发酵指数”按 `100 - Fuck-U-Code 质量分` 反向换算，越低越好；四字评价读取官方 Markdown 报告中的“屎山等级”。它不是发布门禁，只是一个让维护者快速闻到坏味道的仓库健康信号。
