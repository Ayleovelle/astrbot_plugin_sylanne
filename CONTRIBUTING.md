<!-- markdownlint-disable MD029 -->
# 🤝 为 Sylanne 做出贡献

感谢你有兴趣为 **Sylanne** 做出贡献！无论是修复 Bug、添加新功能、改进文档，还是对她的计算模型与自我进化提出设计想法，每一次参与都让这个项目变得更好。

为了营造一个开放和友善的社区环境，本项目采用 [行为准则](CODE_OF_CONDUCT.md)。请在参与贡献前确保你已阅读并同意遵守它。

> Sylanne 是一个偏研究性的拟人对话引擎（不可逆关系计算 + 多智能体自我进化）。如果你想动计算层或进化层，强烈建议先开 Issue 聊一聊设计——这部分逻辑相互耦合，贸然改动容易引入难察觉的回归。

## 📄 提交 Issue

请在提交前先**搜索现有 Issue**，确认没有重复，并尽量**更新到最新版本**复现。

- 🐛 [**报告 Bug**](https://github.com/Ayleovelle/astrbot_plugin_sylanne/issues/new?template=bug_report.yml) — 遇到异常行为、报错、崩溃。
- ✨ [**功能建议**](https://github.com/Ayleovelle/astrbot_plugin_sylanne/issues/new?template=feature_request.yml) — 你希望她多会一种本事。
- 💡 [**设计建议**](https://github.com/Ayleovelle/astrbot_plugin_sylanne/issues/new?template=design.yml) — 对计算模型 / 人格系统 / 自我进化 / 交互设计的想法。
- 📚 [**文档改进**](https://github.com/Ayleovelle/astrbot_plugin_sylanne/issues/new?template=docs.yml) — README、配置说明、公式讲解的错误或缺失。
- 💬 [**开放讨论**](https://github.com/Ayleovelle/astrbot_plugin_sylanne/issues/new?template=discussion.yml) — 现象观察、理论疑问、用法心得，随便聊。

## 💻 代码贡献

欢迎直接用代码改进项目！**新功能请先通过 Issue 讨论。**

### 开发环境准备

0. 确认你要做的功能 / 修的问题没有与最新进度重复。
1. Fork 本仓库到你的 GitHub 账号。
2. 克隆你的 Fork 到本地：

    ```bash
    git clone https://github.com/your-username/astrbot_plugin_sylanne.git
    ```

3. 确保已安装 Python 3.10–3.13。
4. AstrBot 环境通常已包含大部分依赖，并会自动安装插件所需的额外依赖；如确实缺失请查看 `requirements.txt`。

### 代码风格

- **格式化与检查**：使用 `ruff`。Windows 开发者可直接运行插件根目录的 `run_ruff.bat`（一键 format + check --fix + 统计）。
- **CI 红线**：PR 必须通过 `ruff check --select=E9,F63,F7,F82`（语法/未定义名等致命错误零容忍）。
- **类型注解**：尽量为函数和类加 Type Hints。
- **测试**：改动计算层 / 进化层 / 编排逻辑时，请补充或更新 `tests/` 下的单测；本仓库有完整的 pytest 套件与实机冒烟脚本，提交前请确保全绿。

### 提交 Pull Request

1. **创建分支**：从最新开发分支（通常是 `feat/X` 或 `dev/X`）切出功能分支。

    ```bash
    git checkout -b feat/your-feature-name   # 或 fix/your-bug-fix
    ```

2. **提交更改**：用**简体中文**写清晰、描述性的提交信息，推荐遵循 [Conventional Commits](https://www.conventionalcommits.org/)：

    - `feat` 新功能 / `fix` 修复 / `docs` 文档 / `style` 格式 / `refactor` 重构 / `perf` 性能 / `test` 测试 / `chore` 杂务

3. **推送并发起 PR**：指向最新开发分支，参照模板用简体中文说明改了什么、为什么。涉及 WebUI 等视觉改动请附截图。
4. **代码审查**：维护者会 review，有修改建议请及时响应。

> [!TIP]
> 动计算层 / 进化层前先和维护者聊一聊，能大幅提高 PR 被合并的概率，也能帮你少踩耦合的坑 :)

## 📝 文档贡献

文档和代码同样重要。`README.md` / `CHANGELOG.md` 或其他文档里的错别字、表述不清、过时内容，欢迎直接提 PR 修正。

---

## ❤️ 特别感谢

- [@Soulter](https://github.com/Soulter)：感谢他维护 AstrBot 这个平台，让这一切有了生长的土壤。
- [@DBJD-CR](https://github.com/DBJD-CR)：本仓库的工程化与美化骨架（README 排版、社区文件、Issue 模板、自动化工作流）大量借鉴了他的[插件模板](https://github.com/DBJD-CR/astrbot_plugin_helloworld)——原来仓库也能这么漂亮么（）。Sylanne 的主动发言也搭配他的 [Proactive_Chat](https://github.com/DBJD-CR/astrbot_plugin_proactive_chat) 食用更佳。

🤖 以及陪我把伤痕代数、空洞微积分和一整套会做梦的脑子抠出来的 AI 朋友们：

- Claude Opus 4.8 / 4.7 / 4.6
- Claude Sonnet 4.6
- Claude Haiku 4.5
- GPT-5.5 / 5.4
- DeepSeek V4p
- GLM-5.1
- Kimi K2.6


