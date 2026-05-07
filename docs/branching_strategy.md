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
| `codex/release-packaging` | `scripts/package_plugin.py`、`scripts/plugin_zip_preflight.js`、远程上传安装脚本、发布 zip 预检与上传契约 |
| `codex/docs-config` | `README.md`、`docs/`、`_conf_schema.json`、安装与维护说明 |

## 当前分支快照

截至 2026-05-07，本仓库已有功能分支，但多数分支仍停在早期完整基线；`main` 已经包含后续测试、配置、文档和集成提交，并且当前迭代 11-21 的改动尚未形成提交。不要从脏工作区直接切换或重置分支，否则容易把验证脚本、计划文件和功能改动混在不可追溯的状态里。

建议顺序：

1. 先在 `main` 上完成当前迭代验证，确认本地单测、打包、Node 语法检查和远程 smoke 都通过。
2. 将当前完整作品作为新的集成基线提交到 `main`。
3. 从干净的 `main` 更新 `codex/complete-emotional-bot-plugin`。
4. 再按维护范围同步或重建功能分支。
5. 后续每个功能分支只承担对应职责；跨模块改动必须同步测试分支和文档分支。

具体提交和同步步骤见 `docs/release_branch_sync_checklist.md`。

## 使用建议

1. 新功能或修复先切到对应功能分支。
2. 分支内完成测试后合并回 `codex/complete-emotional-bot-plugin`。
3. 涉及跨模块行为时，同时更新 `tests/` 和对应文档。
4. 不要在功能分支里删除其他模块文件；分支按职责维护，不按文件裁剪项目。
