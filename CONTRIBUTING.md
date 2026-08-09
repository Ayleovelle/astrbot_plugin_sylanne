# 贡献指南

本项目由 2718 Labs 维护，接受缺陷修复、功能改进、测试和文档更新。提交前请阅读 [行为准则](CODE_OF_CONDUCT.md)。

## 工程原则

项目采用最小充分工程原则：实现需求所需的最小闭环，用与风险相称的测试证明行为，不把“可以更完整”当成扩大范围的理由。

- 优先处理历史或数据丢失、插件崩溃、无回复、权限或隐私边界错误、安装失败和主要流程回归。
- 界面细节、低概率且无稳定复现的边缘问题、纯理论风险和无直接收益的重构默认不阻塞交付。
- 不为单一调用点提前增加通用框架、适配层或配置项。
- 不在功能改动中夹带全仓格式化、无关重命名或架构改写。
- 当目标行为、受影响回归和必要静态检查通过后停止，不重复执行等价验证。

严重问题必须有复现、根因、回归测试和修复后证据；低影响问题应进入后续清单，而不是拖住当前交付。

## 报告问题

提交 Issue 前请搜索现有记录，并尽量在最新版本复现。缺陷报告至少包含：

1. Sylanne、AstrBot、Python 和操作系统版本。
2. 平台适配器，例如 QQ、Telegram、微信或 Discord。
3. 相关配置，敏感值必须脱敏。
4. 最小复现步骤。
5. 预期行为、实际行为和必要日志。

功能建议应说明用户场景、最小可用行为和不包含的范围。涉及权限、隐私、数据迁移或公开网络访问时，要单独说明风险边界。

## 开发环境

1. Fork 并克隆仓库。
2. 使用 Python 3.10-3.13。
3. 将插件目录放入 AstrBot 的 `data/plugins/`，或通过 AstrBot WebUI 安装本地 ZIP。
4. AstrBot 会安装 `requirements.txt` 中的插件依赖；不要把 `astrbot` 本身加入依赖。

## 代码与测试

- AstrBot API 只从 `astrbot.api.*` 导入。
- 持久化数据只写 AstrBot 提供的插件数据目录。
- 异步路径不得使用阻塞网络请求或未受控后台任务。
- 修改行为时补充最小回归测试，并运行受影响的旧测试。
- 代码检查使用 Ruff；不要在同一仓库混入 Black、Flake8 或 isort。
- 注释说明约束和原因，不复述代码，也不把软件行为描述成生物学或医学结论。

常用命令：

```powershell
python -m pytest tests/path_to_affected_test.py -q
python -m pytest
python -m ruff check .
python -m compileall -q main.py sylanne_alpha
```

## Pull Request

PR 应保持单一目标，并说明问题、方案、验证证据和已知限制。涉及 WebUI 视觉行为时附截图；涉及配置或持久化格式时同步更新 schema 和升级说明。

提交前确认：

- [ ] 已在 AstrBot `data/plugins/` 环境中完成必要实测。
- [ ] `_conf_schema.json` 可以解析，新增或删除字段已同步文档和前端。
- [ ] 未混入 NoneBot、Koishi、Telebot 等其他框架 API。

提交信息使用 Conventional Commits，例如 `fix:`、`feat:`、`docs:`、`refactor:`、`test:`。未经仓库维护者授权，不要打 tag、发布 Release、提交插件市场或合并 PR。
