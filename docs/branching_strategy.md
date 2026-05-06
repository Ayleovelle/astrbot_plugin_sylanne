# 分支维护策略

当前仓库以完整插件基线作为共同起点，再按功能建立维护分支。所有功能分支初始指向同一个完整作品提交，后续维护时按职责在对应分支上开发，再合并回集成分支。

## 集成分支

| 分支 | 用途 |
| --- | --- |
| `codex/complete-emotional-bot-plugin` | 完整作品基线，包含情绪引擎、公共 API、心理筛查、文献库、humanlike 路线和测试 |

## 功能维护分支

| 分支 | 维护范围 |
| --- | --- |
| `codex/emotion-core` | `emotion_engine.py`、`prompts.py`、情绪维度、人格基线、真实时间半衰期、关系修复与冷处理后果 |
| `codex/astrbot-integration` | `main.py`、AstrBot hook、配置读取、KV 持久化、命令与注入流程 |
| `codex/public-api-memory` | `public_api.py`、插件互调协议、livingmemory 兼容、`emotion_at_write` payload |
| `codex/psychological-screening` | `psychological_screening.py`、非诊断心理筛查、心理筛查文档与知识库 |
| `codex/literature-kbs` | `literature_kb/`、`psychological_literature_kb/`、文献库构建脚本与证据地图 |
| `codex/humanlike-agent-roadmap` | `humanlike_agent_literature_kb/`、humanlike 模型路线、10 轮迭代记录与后续 humanlike 状态设计 |
| `codex/tests-validation` | `tests/`、验证命令、回归测试与测试策略 |
| `codex/docs-config` | `README.md`、`docs/`、`_conf_schema.json`、安装与维护说明 |

## 使用建议

1. 新功能或修复先切到对应功能分支。
2. 分支内完成测试后合并回 `codex/complete-emotional-bot-plugin`。
3. 涉及跨模块行为时，同时更新 `tests/` 和对应文档。
4. 不要在功能分支里删除其他模块文件；分支按职责维护，不按文件裁剪项目。
