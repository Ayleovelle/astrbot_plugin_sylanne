# Fuck-U-Code 发酵报告

> powered by Fuck-U-Code；本报告由 `scripts/update_fuck_u_code_report.py` 根据官方 JSON 输出生成。

- 💩 发酵指数：`19.8/100`，官方评价：`😐 微臭青年`（由质量分反向换算，越低越好）
- 官方 JSON overallScore：`80.2/100`
- 扫描规模：`156/240` 个文件已分析，`84` 个文件被跳过
- 问题计数：critical `124`，error `300`，warning `250`
- 原始报告：`output/fuck_u_code/raw-report.json`
- 生成时间：`2026-05-25T17:27:23+00:00`

## 最需要除味的文件

| 💩 发酵 | 质量分 | critical | error | warning | 文件 |
| --- | --- | ---: | ---: | ---: | --- |
| 55.0/100 | 44.6/100 | 8 | 1 | 0 | `sylanne_alpha/llm_request_pipeline.py` |
| 53.0/100 | 46.9/100 | 7 | 2 | 2 | `sylanne_alpha/public_api.py` |
| 48.0/100 | 51.9/100 | 5 | 4 | 2 | `sylanne_alpha/webui_server.py` |
| 48.0/100 | 52.3/100 | 5 | 3 | 1 | `sylanne_alpha/llm_response_pipeline.py` |
| 41.0/100 | 59.2/100 | 3 | 6 | 1 | `sylanne_alpha/realtime_dispatch.py` |
| 36.0/100 | 64.1/100 | 4 | 4 | 1 | `sylanne_alpha/webui_routes.py` |
| 36.0/100 | 64.2/100 | 3 | 4 | 1 | `sylanne_alpha/state_persistence.py` |
| 35.0/100 | 65.0/100 | 4 | 4 | 2 | `sylanne_alpha/kernel.py` |
| 35.0/100 | 65.4/100 | 4 | 3 | 2 | `sylanne_alpha/computation_spine.py` |
| 31.0/100 | 68.9/100 | 3 | 3 | 2 | `sylanne_alpha/workset.py` |
| 31.0/100 | 68.6/100 | 2 | 7 | 2 | `sylanne_alpha/hgt.py` |
| 30.0/100 | 70.3/100 | 1 | 7 | 1 | `experiments/void_scar_experiments.py` |

## 读数说明

README 徽章里的“发酵指数”按 `100 - Fuck-U-Code 质量分` 反向换算，越低越好；四字评价读取官方 Markdown 报告中的“屎山等级”。它不是发布门禁，只是一个让维护者快速闻到坏味道的仓库健康信号。
