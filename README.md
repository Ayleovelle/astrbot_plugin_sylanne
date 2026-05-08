# AstrBot 多维情绪状态插件

> 让 AstrBot 维护一套可计算、可记忆、可解释、可被其他插件调用的多维情绪状态。

![版本 0.1.0-beta](https://img.shields.io/badge/version-0.1.0-beta-blue)
![AstrBot >=4.9.2,<5.0.0](https://img.shields.io/badge/AstrBot-%3E%3D4.9.2%2C%3C5.0.0-green)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-yellow)
![协议 astrbot.emotion_state.v2](https://img.shields.io/badge/schema-astrbot.emotion__state.v2-purple)
![许可证 GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-red)

`astrbot_plugin_emotional_state` 是一个面向 AstrBot 的“情绪状态层”和“插件公共状态服务”。它不是只在提示词里写几句“你要有喜怒哀乐”，而是把 bot 的情绪、关系后果、人格差异、长期记忆注解、拟人状态、道德修复状态和非诊断心理筛查拆成可测试、可持久化、可调用的工程模块。

`astrbot_plugin_emotional_state` 不是一个简单的“给 bot 加情绪标签”的插件。他/她的核心目标是：

> 让不同人格的 bot 在长期对话中形成可解释、可持续、可重置、可被记忆系统记录的计算性情绪轨迹。

本插件会让 LLM 根据上下文、用户当前文本、bot 人格和上一轮状态，判断当前情绪观测值；本地引擎再用真实时间半衰期、人格基线、置信门控、关系修复和后果状态机更新长期状态。最后，这个状态会作为临时上下文注入下一次 LLM 请求，影响语气、节奏、社交距离、边界感和修复倾向。

> **重要提示**
> 这里的“情绪”“拟人状态”“道德修复”“心理筛查”都是工程上的模拟状态，不代表真实意识、真实主观体验、真实身体、真实疾病或临床诊断。心理相关模块只输出非诊断趋势和风险提示，不替代任何医学、心理咨询或危机干预流程。

---

## 快速导航

| 主题 | 内容 |
| --- | --- |
| [当前版本与兼容范围](#当前版本与兼容范围) | 插件版本、AstrBot 版本、Python 要求、许可证和发布状态。 |
| [0.1.0-beta 迭代记录](#010-beta-迭代记录) | 当前 beta 发布摘要、历史 PR 顺序和可折叠逐轮工程迭代明细。 |
| [项目定位](#项目定位) | 为什么本插件不是普通的提示词人设增强。 |
| [核心能力](#核心能力总览) | 7 维情绪、人格建模、真实时间记忆、关系修复、公共 API。 |
| [快速开始](#快速开始) | 发布 zip 包、仓库安装、手动复制、最小配置和检查命令。 |
| [命令速查](#命令) | 用户可直接在会话里调用的状态、重置和诊断命令。 |
| [配置指南](#配置指南) | 核心配置、低推理模式、后果衰减、humanlike、心理筛查。 |
| [工作流](#工作流) | `on_llm_request` / `on_llm_response` 如何更新和注入状态。 |
| [LivingMemory 兼容](#livingmemory--长期记忆兼容) | 写入记忆时冻结 `emotion_at_write`、`humanlike_state_at_write`、`lifelike_learning_state_at_write`、`moral_repair_state_at_write`、`fallibility_state_at_write` 和 `integrated_self_state_at_write`。 |
| [公共 API](#公共-api) | 其他插件如何读取、模拟、提交、重置情绪状态。 |
| [打包、上传与新仓库发布](#打包上传与新仓库发布) | 构建 zip、预检、WebUI 上传、GitHub 新仓库发布清单。 |
| [情绪模型](#情绪模型) | 维度定义、公式推导、人格基线、真实时间半衰期。 |
| [关系与后果](#关系与后果) | 生气原因、是否原谅、冷处理、错误是否已改正。 |
| [拟人状态](#拟人状态-humanlike_state) | `humanlike_state` 的 P0 维度和表达调制边界。 |
| [生命化学习](#生命化学习-lifelike_learning_state) | 新词、黑话、共同语境、用户画像证据和开口/沉默策略。 |
| [瑕疵模拟](#瑕疵模拟-fallibility_state) | 可选的误读、记忆模糊、轻微嘴硬、澄清、纠错和补偿状态。 |
| [心理筛查](#非诊断心理状态筛查) | 备用的长期状态建模，不做诊断。 |
| [本地文献知识库](#本地文献知识库) | 情绪、人格量化、心理筛查、拟人代理的仅本地研究资料。 |
| [测试与维护](#测试与维护) | 本地测试命令、远程烟测、gpt-5.5 性能基准、分支策略。 |
| [故障排查](#故障排查) | 常见问题和处理顺序。 |

---

## 当前版本与兼容范围

| 项目 | 当前值 |
| --- | --- |
| 插件目录名 | `astrbot_plugin_emotional_state` |
| 显示名 | `多维情绪状态` |
| 当前版本 | `0.1.0-beta` |
| AstrBot 版本 | `>=4.9.2,<5.0.0` |
| Python | `3.10+` |
| 许可证 | `GPL-3.0-or-later` |
| 运行时第三方依赖 | 当前无额外依赖，见 `requirements.txt` |

`0.1.0-beta` 是当前预发布版本，用于把生命化学习、真实时间人格漂移、LivingMemory 情绪注解、公共 API、发布包边界和延迟优化批次合并到 `main` 后的统一验收。当前版本的重点是把“情绪化 bot”从单次提示词风格控制推进到可持久化的状态服务：核心情绪默认启用，`humanlike_state`、`lifelike_learning_state`、`moral_repair_state`、`fallibility_state`、`psychological_screening` 等长期模块默认关闭，由配置显式打开。发布包会包含运行代码、README、LICENSE、配置 schema 和 docs；不会包含 `tests/`、`scripts/`、`literature_kb/`、`personality_literature_kb/`、`psychological_literature_kb/`、`humanlike_agent_literature_kb/`、`raw/`、`output/`、`dist/` 等开发、研究或缓存目录。

### 0.1.0-beta 迭代记录

`v0.1.0-beta` 合并在 `main` 上，对外安装版本由 `metadata.yaml` 和 `main.py @register(...)` 共同声明为 `0.1.0-beta`。下面保留 `0.0.2-beta-pr-x` 历史预发布批次，便于追溯从生命化学习、人格漂移到延迟专项的阶段性合入；完整工程迭代明细默认折叠，避免 README 首屏过长。

<details open>
<summary>历史预发布批次摘要（0.0.2-beta-pr-1 至 0.0.2-beta-pr-19）</summary>

| 本地迭代号 | 状态 | 对应任务 | 结果摘要 |
| --- | --- | --- | --- |
| `0.0.2-beta-pr-1` | 已完成 | 生命化学习核心状态 | 新增 `lifelike_learning_engine.py`，支持新词/黑话、用户画像证据、偏好、边界和真实时间半衰期。 |
| `0.0.2-beta-pr-2` | 已完成 | AstrBot 生命周期接入 | 接入 `on_llm_request`、KV、提示词注入、`/lifelike_state`、`/lifelike_reset` 和 `get_bot_lifelike_learning_state`。 |
| `0.0.2-beta-pr-3` | 已完成 | LivingMemory 写入注解 | `build_emotion_memory_payload(...)` 写入 `lifelike_learning_state_at_write`，冻结当时共同语境。 |
| `0.0.2-beta-pr-4` | 已完成 | 综合自我仲裁 | 综合自我模块使用共同语境决定轻问、短应、开口、安静或安全打断。 |
| `0.0.2-beta-pr-5` | 已完成 | 第三方公共 API | 导出 `LIFELIKE_LEARNING_SCHEMA_VERSION`、`LifelikeLearningServiceProtocol` 和 `get_lifelike_learning_service`。 |
| `0.0.2-beta-pr-6` | 已完成 | 配置和 README 契约 | `_conf_schema.json` 增加 9 个生命化学习配置项，并补齐命令、LLM 工具、LivingMemory 和公共 API 文档。 |
| `0.0.2-beta-pr-7` | 已完成 | 发布包和 zip 预检 | 打包脚本和 zip 预检强制包含 `lifelike_learning_engine.py`。 |
| `0.0.2-beta-pr-8` | 已完成 | 产品理念固化 | README 写入“更像生命，而不只是更强”和“代码开源，灵魂属于你”的共同语境解释。 |
| `0.0.2-beta-pr-9` | 已完成 | 全量本地验证 | 236 个单元测试、`py_compile`、`json.tool`、Node 语法检查、打包构建、zip 预检全部通过。 |
| `0.0.2-beta-pr-10` | 已完成 | 远程清理、上传和烟测 | 远程先删旧同名插件，再上传当前 zip；严格烟测通过，LivingMemory 仍可见。 |
| `0.0.2-beta-pr-11` | 已完成 | 真实时间人格漂移 | 新增 `personality_drift_engine.py`，人格偏移按真实时间半衰、短时门控和静态 persona 锚点缓慢变化，不能靠大量消息强刷。 |
| `0.0.2-beta-pr-12` | 已完成 | 人格漂移延迟优化与 20 次实机测试 | 复用单轮人格漂移状态、缓存读取不写回、空漂移免深拷贝；服务器清旧包后上传新包，20 次严格烟测全部通过。 |
| `0.0.2-beta-pr-13` | 已完成 | 延迟专项第一批优化 | 默认单阶段情绪评估、评估器超时回退、模型提供方短缓存、上下文裁剪、被动读取短路、引擎缓存和轨迹追加瘦身；延迟专项队列持久化到第 `200` 次迭代。 |
| `0.0.2-beta-pr-14` | 已完成 | 延迟专项第二批优化 | 请求/响应生命周期缓存配置开关、复用观测文本、空白响应提前返回、减少请求注入重复配置读取，并保留 KV 保存顺序。 |
| `0.0.2-beta-pr-15` | 已完成 | 延迟专项第三批优化 | 生命化学习状态减少 `to_dict/from_dict` 往返，热路径正则预编译，主动开口策略解析词典只转换一次。 |
| `0.0.2-beta-pr-16` | 已完成 | 延迟专项第四批优化 | `_request_to_text()` 只读取尾部上下文、被动缓存读取移除整状态序列化比较、LivingMemory 写入开关集中读取、禁用人格漂移早退、KV key 清洗复用缓存。 |
| `0.0.2-beta-pr-17` | 已完成 | 延迟专项第五批优化 | 请求默认无状态工作早退、状态轻查询直读、低信号人格漂移不写 KV，并新增本地热路径基准测试。 |
| `0.0.2-beta-pr-18` | 已完成 | 5 秒目标 SLA 默认值 | `assessor_timeout_seconds` 默认降为 `4.0`，慢内部 LLM 自动回退启发式估计；提示词维度 schema 常量化、人格漂移正则预编译。 |
| `0.0.2-beta-pr-19` | 已完成 | 真实链路并发等待削减 | `on_llm_response` 并发预取道德修复状态，LivingMemory 写入并发获取可选状态快照，保持注解结构和保存顺序。 |

</details>

<details>
<summary>展开逐轮工程迭代明细（第 11-200 次）</summary>

| 迭代 | 状态 | 内容 | 验证/结果 |
| --- | --- | --- | --- |
| 11 | 已完成 | 持久化迭代计划、编写远程烟测脚本、强化安全/人格/记忆契约 | 122 个单元测试、py_compile、Node 语法检查、远程烟测 |
| 12 | 已完成 | 完善 README，加入可复用远程烟测流程和环境变量示例 | 123 个单元测试、py_compile、Node 语法检查、远程烟测 |
| 13 | 已完成 | 增加 LivingMemory 适配示例测试，覆盖关闭原始快照和关闭拟人状态的场景 | 126 个单元测试、py_compile、Node 语法检查、远程烟测 |
| 14 | 已完成 | 强化心理模块用户可见文本的非诊断表述测试 | 128 个单元测试、py_compile、Node 语法检查、远程烟测 |
| 15 | 已完成 | 对照实现复查公共 API 文档并补充迁移说明 | 129 个单元测试、py_compile、Node 语法检查、远程烟测 |
| 16 | 已完成 | 通过排除原始知识库缓存精简部署包，记录发布包契约，并在安装路径安全前保持远程烟测只读 | 132 个单元测试、py_compile、打包构建、Node 语法检查、git diff 检查、远程烟测 |
| 17 | 已完成 | 通过 WebUI `install-upload` 在远程测试服部署插件，并以 `ASTRBOT_EXPECT_PLUGIN=astrbot_plugin_emotional_state` 重跑烟测 | 上传安装脚本、136 个单元测试、py_compile、打包构建、远程安装、带目标插件断言的远程烟测 |
| 18 | 已完成 | 强化远程烟测：目标插件必须已安装，且不能出现在失败插件记录中 | 136 个单元测试、Node 语法检查、git diff 检查、失败插件断言远程烟测 |
| 19 | 已完成 | 强化远程烟测：加入目标插件运行时元数据断言，包括启用状态、版本、显示名和插件 API 摘要 | 136 个单元测试、py_compile、打包构建、Node 语法检查、git diff 检查、版本/显示名断言远程烟测 |
| 20 | 已完成 | 通过完整检查 zip 内容强化远程上传预检，并记录可上传发布包契约 | 136 个单元测试、py_compile、打包构建、Node 语法检查、git diff 检查、版本/显示名断言远程烟测 |
| 21 | 已完成 | 增加远程安装 zip 预检失败用例的本地测试，不调用远程服务器 | 141 个单元测试、py_compile、打包构建、Node 语法检查、git diff 检查、版本/显示名断言远程烟测 |
| 22 | 已完成 | 复查 git 分支/打包状态，准备可维护的分支拆分或提交暂存方案 | 141 个单元测试、README 契约测试、git diff 检查、版本/显示名断言远程烟测 |
| 23 | 已完成 | 新增仓库维护清单，用于提交当前基线并同步功能分支，避免丢失未提交改动 | 141 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 24 | 已完成 | 先在 `main` 提交已验证基线，再从干净基线同步集成/维护分支 | 提交 976ee99；分支同步前工作区干净；所有文档列出的维护分支同步到 976ee99 |
| 25 | 已完成 | 分支同步后做最终验证并写收尾摘要 | 141 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 26 | 已完成 | 修复远程烟测 UI 检测，避免只显示显示名的插件卡片被误判为目标插件缺失 | 141 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 27 | 已完成 | 当失败插件 API 不健康时让远程烟测失败 | 141 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 28 | 已完成 | 让远程烟测 WebUI 探测更确定，并把 UI 字段标记为尽力诊断 | 141 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 29 | 已完成 | 将旧字段 `pageData.hasExpectedPlugin` 作为综合 UI 检查的兼容别名 | 141 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 30 | 已完成 | 新增远程烟测必需只读端点的集中 API 健康诊断 | 141 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 31 | 已完成 | 记录远程烟测和打包预检命令使用 Codex 内置 Node 的回退方式 | 141 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 32 | 已完成 | 锁定内置 Node 回退文档的顺序和契约测试一致性 | 143 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 33 | 已完成 | 刷新 README 测试矩阵，覆盖扩展后的远程烟测契约 | 143 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 34 | 已完成 | 将远程烟测文档中的版本和显示名断言锁定到 `metadata.yaml` | 144 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 35 | 已完成 | 锁定 README 徽章和 AstrBot 兼容徽章编码与 `metadata.yaml` 一致 | 145 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 36 | 已完成 | 要求发布 zip 包的元数据身份匹配预期插件目录 | 147 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 37 | 已完成 | 要求公共 API 服务发现匹配版本化 schema 契约 | 150 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 38 | 已完成 | 使 humanlike 路线文档与当前记忆载荷和配置 schema 名称对齐 | 151 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 39 | 已完成 | 收敛 humanlike 路线中有关开关和注解时间戳的剩余漂移 | 151 个单元测试、py_compile、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 40 | 已完成 | 将插件身份引用锁定到 `metadata.yaml` 的 name | 156 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 41 | 已完成 | 锁定 `assessment_timing` 的运行时、schema、README 选项和 typed config table 覆盖 | 157 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 42 | 已完成 | 锁定公共 API/服务发现和命令文档契约 | 160 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 43 | 已完成 | 锁定 LLM 工具注册名与 README 文档一致 | 161 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 44 | 已完成 | 刷新 README 测试矩阵，覆盖最近锁定的命令、配置、公共 API 和元数据契约 | 162 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 45 | 已完成 | 把心理筛查 alpha 最小/最大默认值锁定为显式 schema 契约 | 162 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 46 | 已完成 | 强化发布打包，防止自包含和预检插件名漂移 | 165 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 47 | 已完成 | 澄清公共 API README 示例中的第三方插件安全回退行为 | 166 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 48 | 已完成 | 锁定心理筛查非诊断公共 API 返回语义 | 167 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 49 | 已完成 | 增加机器可读的心理严重功能受损和睡眠受扰风险标记 | 168 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、泄漏扫描、远程烟测 |
| 50 | 已完成 | 导出稳定的心理风险布尔字段契约，并澄清 README/docs 中的嵌套访问方式 | 170 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 51 | 已完成 | 在公共 API 中复用心理风险布尔字段 tuple，防止契约漂移 | 170 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 52 | 已完成 | 增加远程烟测失败插件摘要，区分无关失败和目标插件失败 | 170 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 53 | 已完成 | 在远程烟测输出中增加目标插件综合通过摘要 | 170 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、远程烟测 |
| 54 | 已完成 | 修复发布包按插件包名导入公共 API 时的导入路径 | 171 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、泄漏扫描、远程烟测 |
| 55 | 已完成 | 锁定发布包运行根文件，并让 README 安装树与发布边界一致 | 172 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、泄漏扫描 |
| 56 | 已完成 | 使上传 zip 预检必需条目与发布运行根契约一致 | 172 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、泄漏扫描 |
| 57 | 已完成 | 要求上传预检和发布清单包含依赖声明 | 172 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、泄漏扫描 |
| 58 | 已完成 | 锁定 README 中的 `py_compile` 命令和失败上传清理文档到当前发布包契约 | 172 个单元测试、py_compile、打包构建、打包预检、Node 语法检查、git diff 检查、泄漏扫描 |
| 59 | 已完成 | 新增道德修复状态模块，作为欺骗/作恶模拟的安全替代方案 | 193 个单元测试、py_compile、json.tool、打包构建、打包预检、Node 语法检查、git diff 检查、泄漏扫描 |
| 60 | 已完成 | 声明 GPL-3.0-or-later 许可证，并把 LICENSE 纳入发布包契约 | 194 个单元测试、py_compile、json.tool、打包构建、打包预检、Node 语法检查、git diff 检查、泄漏扫描 |
| 61 | 已完成 | 构建综合自我状态总线，融合情绪、拟人、道德修复和心理快照为统一公共契约 | 116 个定向测试、py_compile、json.tool |
| 62 | 已完成 | 增加基于证据权重的因果轨迹摘要，使各模块状态变化可解释 | `tests/test_integrated_self.py`、`tests/test_public_api.py` |
| 63 | 已完成 | 增加确定性回放/模拟包，用于不触碰 KV 存储地测试状态演化 | 确定性回放包校验和测试 |
| 64 | 已完成 | 增加策略规划层，把综合状态转成允许的表达调制和修复动作 | 策略计划测试保留阻断动作和修复动作 |
| 65 | 已完成 | 增加 schema 迁移和兼容性探针，面向未来公共契约 | 兼容性探针测试和公共 API 契约测试 |
| 66 | 已完成 | 增加维护者导出/导入诊断，同时避免泄露原始 persona 或不安全策略内容 | 脱敏诊断测试 |
| 67 | 已完成 | 增加低成本部署的降级模式和令牌预算档位 | `integrated_self_degradation_profile` schema/文档/测试 |
| 68 | 已完成 | 扩展 LivingMemory 集成契约，加入综合自我状态注解 | `state_annotations_at_write` 信封测试 |
| 69 | 已完成 | 围绕综合自我状态面强化发布、README 和远程烟测契约 | 208 个全量测试、33 个打包/远程契约测试、py_compile、json.tool、Node 语法、打包预检、泄漏扫描 |
| 70 | 已完成 | 运行全量验证、远程烟测、分支同步，并写完整的革命性迭代交接记录 | 实现提交 `e86735b`；最终状态已记录；远程烟测通过；维护分支同步到最新 HEAD |
| 71 | 已完成 | 参考 ASR 插件结构重写 README 为可发布插件首页，随后重建包并准备新仓库发布 | 208 个单元测试、py_compile、json.tool、Node 语法检查、打包构建、打包预检；GitHub 鉴权受阻 |
| 72 | 已完成 | 创建 GitHub 仓库、更新仓库元数据、设置预发布版本、推送已验证 main 分支并发布预发布包 | 公共仓库和 `v0.0.1-beta` 预发布已创建；发布 zip SHA256 `3133f89e96ce5e124083da0867765f2d5d6d6b2ef074d0963a55eedf0de833ef` |
| 73 | 已完成 | 按 GitHub 官方数学表达式语法优化公式渲染 | 保留 GitHub fenced math；禁用危险宏由 `tests/test_document_math_contract.py` 锁定；212 个测试通过；发布资产已刷新 |
| 74 | 已完成 | 增加顶刊模型论证、折叠完整推导和更严谨的公式记号 | README/theory 默认摘要、折叠推导、DOI 证据映射、符号清理（`O_t`、`H_t`、`F_t`）；213 个测试、py_compile、json.tool、Node 语法、打包构建、打包预检、git diff 检查 |
| 75 | 已完成 | 澄清远程版本漂移和“已安装不覆盖”的上传诊断 | `expectedPluginDrift`、`installOutcome=already_installed_no_overwrite`、README/checklist 文档；213 个测试、py_compile、json.tool、Node 语法、打包构建、打包预检；严格远程烟测确认退出码 7 漂移，非严格远程烟测通过 |
| 76 | 已完成 | 发布 `0.0.2-beta`：加入更严格的人格量化模型、2 万条人格文献元数据知识库、更新公式/文档/测试、远程烟测和预发布上传 | 已发布 `v0.0.2-beta` 预发布；216 个测试、py_compile、json.tool、Node 语法检查、打包构建、zip 预检、git diff 检查、严格远程漂移检查和非严格远程烟测完成 |
| 77 | 已完成 | 新增持久化生命化学习状态，记录新词、本地黑话、用户画像事实、偏好和对话节奏 | `lifelike_learning_engine.py`；8 维状态；真实时间半衰期；单元测试；不泄露原始消息 |
| 78 | 已完成 | 把生命化学习接入 AstrBot 生命周期、KV、提示词注入、重置后门、命令和 LLM 工具 | `on_llm_request`、KV 缓存、`/lifelike_state`、`/lifelike_reset`、`get_bot_lifelike_learning_state` |
| 79 | 已完成 | 扩展 LivingMemory 注解，使记忆写入时冻结当时学到的共同语境状态 | `lifelike_learning_state_at_write`；公共 API 记忆载荷和综合信封测试 |
| 80 | 已完成 | 把生命化学习融合进综合自我仲裁，使 bot 能决定开口、短应、追问、沉默、打断或修复 | 综合自我姿态和澄清/安静陪伴策略测试 |
| 81 | 已完成 | 发布可选公共 API helper，供第三方插件读取黑话/画像/主动性快照而无需读 KV | `LIFELIKE_LEARNING_SCHEMA_VERSION`、`LifelikeLearningServiceProtocol`、`get_lifelike_learning_service` |
| 82 | 已完成 | 增加生命化学习的配置 schema 和 README 覆盖，包括隐私边界、重置控制和令牌预算行为 | 9 个生命化学习配置键、命令/工具文档、LivingMemory 文档、公共 API 文档 |
| 83 | 已完成 | 更新发布打包和 zip 预检，确保新运行时模块始终被包含并检查身份 | 打包脚本、zip 预检、打包测试和 README/checklist 运行文件文档 |
| 84 | 已完成 | 基于当前知识库补充“更像生命，而不只是更强”和“代码开源，灵魂属于你”的产品理论文档 | README 记录生命化原则、共同语境学习和部署者拥有灵魂的边界 |
| 85 | 已完成 | 生命化学习栈落地后运行完整本地验证 | 236 个测试、py_compile、json.tool、打包构建、zip 预检、Node 检查、diff 检查 |
| 86 | 已完成 | 服务器验证前清理旧同名插件，再安装/测试当前包并记录 LivingMemory 可见性 | 远程清理仅删除 `astrbot_plugin_emotional_state`；LivingMemory 仍可见；上传和严格烟测通过 |
| 87 | 已完成 | 在 README 记录完成的 `0.0.2-beta-pr-x` 本地预发布迭代序列，并用测试锁定顺序 | README 表记录 `0.0.2-beta-pr-1` 到 `0.0.2-beta-pr-10`；契约测试 `test_readme_records_beta_pr_iterations_in_order` |
| 88 | 已完成 | 增加真实时间人格漂移，使 persona 在经过时间约束下缓慢变化，而不是按消息量变化 | 引擎/API/文档/测试已实现；上下文不会被重放为新漂移事件；255 个测试、py_compile、json.tool、打包构建、Node 检查、zip 预检、diff 检查通过 |
| 89 | 已完成 | 优化人格漂移延迟并运行 20 次远程实机烟测 | 单轮漂移复用、缓存读取不写回、空漂移无拷贝快速路径；258 个测试、py_compile、json.tool、打包构建、zip 预检、远程清理/上传、20/20 严格烟测通过 |
| 90 | 已完成 | 延迟第一批基线和评估器单阶段默认值 | 默认 `assessment_timing` 为 `post`；缩小评估器上下文；增加超时回退、provider-id TTL 缓存、请求文本裁剪、被动读取不写回、引擎缓存和轨迹追加微优化 |
| 91 | 已完成 | 增加评估器超时和 provider 缓存的延迟回归测试 | `tests/test_astrbot_lifecycle.py` 覆盖超时回退和 provider-id TTL 缓存 |
| 92 | 已完成 | 增加情绪和辅助状态被动缓存读取不写 KV 的回归覆盖 | `tests/test_public_api.py` 覆盖缓存被动读取不写回 KV |
| 93 | 已完成 | 锁定请求上下文裁剪和评估器令牌预算行为 | `_request_to_text` 限制总上下文并保留 `[current_user]`；schema/README 记录限制 |
| 94 | 已完成 | 按 persona 指纹缓存情绪引擎 | `_engine_for_persona` 最多缓存 16 个引擎，并为测试创建实例做懒初始化 |
| 95 | 已完成 | 减少各状态引擎的轨迹追加分配 | Humanlike、lifelike、人格漂移和道德修复只追加保留后的切片 |
| 96 | 已完成 | 记录延迟优先默认值和调参开关 | README 记录延迟优先默认值和 `0.0.2-beta-pr-13` 完成 |
| 97 | 已完成 | 运行延迟第一批的生命周期/公共/配置/引擎定向测试 | 135 个定向测试通过 |
| 98 | 已完成 | 运行延迟第一批完整本地验证和打包预检 | 262 个测试通过；py_compile/json.tool/打包构建/Node 检查/zip 预检/diff 检查通过 |
| 99 | 已完成 | 记录第一批基准测试并确定下一批延迟方向 | 本地测试套件耗时 10.926 秒；zip 大小 178469 字节；下一批聚焦请求内配置/状态复用和减少无效写入 |
| 100 | 已完成 | 缓存请求内生命周期标志 | `on_llm_request` 每次 hook 只读取一次 assessment timing、模块启用标志、注入标志和安全边界 |
| 101 | 已完成 | 复用请求观测文本 | Humanlike、lifelike 和道德修复观测共享一份预构建的 `request_observation_text` |
| 102 | 已完成 | 复用响应生命周期标志 | `on_llm_response` 缓存 timing、道德修复标志、人格漂移标志和安全边界 |
| 103 | 已完成 | 避免请求注入时 helper 层重复读取安全开关 | 请求注入直接使用缓存的安全边界调用 `build_state_injection` |
| 104 | 已完成 | 增加空白响应早退 | 空白响应在加载 persona/状态前返回；生命周期测试断言不会加载 persona 或状态 |
| 105 | 已完成 | 移除人格漂移应用后的重复 persona 模型深拷贝 | `_ensure_persona_state` 已同步漂移后的 persona 模型，调用方不再额外复制 |
| 106 | 已完成 | 保持保存顺序不变 | 未合并情绪/KV 保存，因为异常路径持久化语义会改变 |
| 107 | 已完成 | 运行第二批生命周期/公共 API 定向测试 | 95 个生命周期/公共 API 定向测试通过 |
| 108 | 已完成 | 运行延迟第二批完整本地验证 | 262 个测试通过；py_compile/json.tool/打包构建/Node 检查/zip 预检/diff 检查通过 |
| 109 | 已完成 | 记录第二批基准测试并确定下一批延迟方向 | 本地测试套件耗时 11.799 秒；zip 大小 178469 字节；下一批聚焦对象拷贝削减和引擎热路径微优化 |
| 110 | 已完成 | 减少生命化学习被动用户画像复制成本 | 用有界 `_copy_user_profile` 替代 `to_dict/from_dict` 往返；生命化学习定向测试通过 |
| 111 | 已完成 | 减少生命化学习词典复制成本 | 用 `_copy_jargon_entry` 替代每条序列化往返；生命化学习定向测试通过 |
| 112 | 已完成 | 减少生命化学习画像更新复制成本 | `_update_profile` 在应用证据前直接有界克隆字段；生命化学习定向测试通过 |
| 113 | 已完成 | 避免公共状态词典重复解析 | `derive_initiative_policy` 对每个原始 `JargonEntry` 最多转换一次；生命化学习定向测试通过 |
| 114 | 已完成 | 预编译道德欺骗和伤害线索正则 | 将线索模式移动到模块级编译元组；道德修复测试通过 |
| 115 | 已完成 | 预编译道德修复/行动线索正则 | 承担责任、道歉、补偿和逃避线索不再每次调用时编译；道德修复测试通过 |
| 116 | 已完成 | 预编译心理红旗正则 | 自伤、他伤和严重功能受损信号使用编译元组；心理筛查测试通过 |
| 117 | 已完成 | 预编译拟人危机场景正则 | 医疗/危机场景检测使用编译元组；拟人测试通过 |
| 118 | 已完成 | 在 README 序列中记录延迟第三批 | README 记录 `0.0.2-beta-pr-14` 和 `0.0.2-beta-pr-15`；契约测试期望 pr-1 到 pr-15 |
| 119 | 已完成 | 运行第三批定向验证 | 33 个定向引擎测试和触及运行模块的 py_compile 通过 |
| 120 | 已完成 | 避免 `_request_to_text` 完整复制上下文 | 加入 `_tail_items()`，请求上下文裁剪只读取最后 8 条；生命周期尾部上下文测试通过 |
| 121 | 已完成 | 锁定请求尾部上下文行为 | 新增回归测试，证明只需要尾部上下文时不会转换旧上下文 |
| 122 | 已完成 | 移除过期缓存的 `to_dict()` 比较 | 用 `_passive_update_changed()` 替代被动读取深序列化比较 |
| 123 | 已完成 | 保留被动缓存不写入契约 | 轻量比较改造后，公共 API 缓存被动读取测试通过 |
| 124 | 已完成 | 复用 LivingMemory 写入开关 | `build_emotion_memory_payload()` 每次调用只读取一次记忆注解开关 |
| 125 | 已完成 | 禁用人格漂移快照时提前返回 | 禁用漂移快照不再加载 persona 画像或漂移状态 |
| 126 | 已完成 | 缓存脱敏 KV 会话 key | 新增 `_safe_session_key()`，供情绪、心理、拟人、生命化、漂移和道德 KV key 共用 |
| 127 | 已完成 | 锁定 KV key 兼容性 | 新增 `/` 和 `\\` 会话 key 在所有 KV 前缀下的回归测试 |
| 128 | 已完成 | 在 README 序列中记录延迟第四批 | README 记录 `0.0.2-beta-pr-16`；契约测试期望 pr-1 到 pr-16 |
| 129 | 已完成 | 运行第四批定向验证 | 98 个生命周期/公共 API 测试和触及模块 py_compile 通过 |
| 130 | 已完成 | 请求默认无工作早退 | 无 pre 评估、无注入、可选模块关闭时，`on_llm_request` 在请求文本缓存后直接返回 |
| 131 | 已完成 | 懒构建请求观测文本 | 仅在 humanlike、lifelike 或道德模块启用时才拼接观测文本 |
| 132 | 已完成 | 低信号漂移不写入 | 只有时间诊断/轨迹变化的低信号人格漂移更新会跳过 KV 保存 |
| 133 | 已完成 | 轻量情绪公共值读取 | 情绪值、后果和关系 API 直接加载状态，而不是构建完整快照 |
| 134 | 已完成 | 轻量辅助公共值读取 | Humanlike、lifelike 策略、人格漂移、道德修复和心理值走直接状态路径 |
| 135 | 已完成 | 热路径基准脚本 | 新增 `scripts/benchmark_plugin_hot_path.py`，用于本地 hook 延迟和超时保护测量 |
| 136 | 已完成 | 提示词维度 schema 常量化 | 评估提示词使用模块级维度 schema，避免每次调用 join/split |
| 137 | 已完成 | 评估器 SLA 默认值 | `assessor_timeout_seconds` 默认改为 `4.0`，保护 5 秒回复目标 |
| 138 | 已完成 | 人格漂移正则预编译 | 漂移启发线索正则只编译一次，并用语义回归测试覆盖 |
| 139 | 已完成 | 响应道德状态并发预取 | `on_llm_response` 在响应后情绪评估时并发加载道德状态，同时保留保存顺序 |
| 140 | 已完成 | LivingMemory 快照并发获取 | 记忆载荷在组装注解前并发获取可选模块快照 |
| 141 | 已完成 | 延迟 PR 文档记录 | README 记录 `0.0.2-beta-pr-17` 到 `0.0.2-beta-pr-19`，测试期望该序列 |
| 142 | 已完成 | 请求辅助状态并发加载 | Humanlike、lifelike 和道德请求状态并发加载；更新/保存仍保持原顺序 |
| 143 | 已完成 | 慢辅助加载基准 | 增加基准用例，证明三个 20 ms 辅助加载约 31 ms 完成，而非串行 60 ms |
| 144 | 已完成 | 响应慢道德加载基准 | 增加响应后评估器和道德状态并发加载基准 |
| 145 | 已完成 | 记忆慢快照基准 | 增加 LivingMemory 可选快照并发获取基准 |
| 146 | 已完成 | 保留超时保护基准 | 慢评估器超时保护继续出现在基准输出中，用于 5 秒 SLA |
| 147 | 已完成 | 第六批基准复查 | 请求、响应和记忆慢等待并发场景均在假 20 ms 等待下约 31 ms 完成 |
| 148 | 已完成 | 第六批验证 | 请求并发改造后，全量测试和 py_compile/json/diff 检查通过 |
| 149 | 已完成 | 第六批交接 | progress 记录下一方向：谨慎尝试保存并发或综合快照并发，并补明确顺序测试 |
| 150 | 已完成 | 第七批基准刷新 | 重新运行热路径基准，确认请求、响应和记忆慢等待基线 |
| 151 | 已完成 | Fallibility 快速状态桩绑定 | 基准脚本绑定 fallibility load/save，使测量覆盖当前运行时模块面 |
| 152 | 已完成 | 无工作请求显式排除 fallibility | no-work 基准显式关闭 fallibility，避免默认早退用例被隐藏模块影响 |
| 153 | 已完成 | 可选模块基准纳入 fallibility | optional modules 基准启用 fallibility 且注入强度为 0，覆盖完整本地模拟路径 |
| 154 | 已完成 | 请求慢 fallibility 并发基准 | 四个 20 ms 请求辅助加载仍约 31 ms 完成，没有串行为约 80 ms |
| 155 | 已完成 | 响应 fallibility 并发基准 | 新增 moral + fallibility + assessor 慢等待重叠基准 |
| 156 | 已完成 | 记忆 fallibility 快照基准 | LivingMemory 慢快照 fan-out 纳入 fallibility 注解获取 |
| 157 | 已完成 | Fallibility 记忆并发测试 | 公共 API 记忆 fan-out 测试断言 `fallibility_state_at_write` 存在 |
| 158 | 已完成 | `_tail_items()` 分配削减 | 尾部上下文 helper 返回序列切片或元组，避免额外 list 拷贝 |
| 159 | 已完成 | 请求上下文无复制验证 | 生命周期尾部上下文测试和 py_compile 通过 |
| 160 | 已完成 | 生命化风格正则预编译 | 风格偏好提取正则移动到模块级编译 |
| 161 | 已完成 | 生命化边界正则预编译 | 边界提示提取正则移动到模块级编译 |
| 162 | 已完成 | 生命化提取回归验证 | 触及的生命周期/公共 API 测试覆盖通过 |
| 163 | 已完成 | Emotion service 方法常量化 | `get_emotion_service()` 复用 required-method 常量，避免每次调用分配大 tuple |
| 164 | 已完成 | Emotion service 版本常量化 | 服务发现复用 expected-version 映射，避免每次调用重建 |
| 165 | 已完成 | 服务发现契约同步 | AST 契约测试改为锁定模块级公共 API 方法常量 |
| 166 | 已完成 | 可选服务方法常量化 | Humanlike、moral、lifelike、personality drift、fallibility helper 复用模块级方法常量 |
| 167 | 已完成 | 可选服务契约验证 | 37 个公共 API 服务发现测试通过 |
| 168 | 已完成 | LivingMemory 情绪快照重叠 | 记忆写入时核心情绪快照与可选模块快照同时启动 |
| 169 | 已完成 | LivingMemory 全快照 gather | 情绪 + 可选快照进入同一个 `asyncio.gather()` 等待窗口 |
| 170 | 已完成 | 记忆载荷组装顺序保留 | 快照并发获取后仍按原顺序组装注解和原始快照字段 |
| 171 | 已完成 | 情绪/可选快照重叠测试 | 新增测试证明慢情绪快照会与五个慢可选快照并发 |
| 172 | 已完成 | 记忆全快照基准用例 | 新增 `memory_slow_emotion_and_snapshot_fanout` 基准项 |
| 173 | 已完成 | 记忆全快照基准验证 | 六个假 20 ms 快照约 31 ms 完成，而不是串行约 120 ms |
| 174 | 已完成 | 人格关键词小写缓存 | persona keyword traits 使用内部预小写副本 |
| 175 | 已完成 | 人格词典小写缓存 | 13 维人格词典的正/负关键词使用内部预小写副本 |
| 176 | 已完成 | persona 文本单次 lower | `build_persona_profile()` 和 `build_personality_model()` 每次调用只 lower 一次文本 |
| 177 | 已完成 | `_keyword_score()` 快路径 | 关键词计分 helper 支持传入预小写文本，循环中不再反复 `keyword.lower()` |
| 178 | 已完成 | `_signed_keyword_score()` 快路径 | 正负关键词扫描复用同一份预小写 persona 文本 |
| 179 | 已完成 | 人格语义验证 | 47 个情绪/人格漂移测试通过，确认模型语义未漂移 |
| 180 | 已完成 | 基准覆盖复查 | 热路径输出包含 fallibility 和 emotion+optional memory fan-out 两类新指标 |
| 181 | 已完成 | 默认请求基准检查 | `request_default_post_inject` 保持亚毫秒级本地开销 |
| 182 | 已完成 | 无工作请求基准检查 | `request_no_request_work` 保持近零本地开销 |
| 183 | 已完成 | 可选模块基准检查 | 无假等待时可选模块本地模拟路径约 1-2 ms |
| 184 | 已完成 | 慢请求辅助基准检查 | 四个慢请求辅助加载仍被限制在单个等待窗口 |
| 185 | 已完成 | 响应后评估基准检查 | 快评估器桩下响应 hook 保持亚毫秒级 |
| 186 | 已完成 | 响应 moral 基准检查 | 慢 moral 状态加载继续与响应后评估重叠 |
| 187 | 已完成 | 响应 moral/fallibility 基准检查 | 慢 moral 和 fallibility 状态加载与评估在同一等待窗口内完成 |
| 188 | 已完成 | 超时保护基准检查 | 慢评估器超时保护仍出现在基准输出中，用于 5 秒 SLA |
| 189 | 已完成 | 记忆可选快照基准检查 | 可选记忆快照继续在单个等待窗口内并发获取 |
| 190 | 已完成 | 记忆全快照基准检查 | 情绪 + 可选记忆快照在同一等待窗口内并发获取 |
| 191 | 已完成 | 生命周期/公共 API 定向验证 | 110 个生命周期与公共 API 测试通过 |
| 192 | 已完成 | 记忆并发定向验证 | 新增记忆 fan-out 测试通过，耗时低于串行等待上界 |
| 193 | 已完成 | 人格关键词定向验证 | 47 个情绪与人格漂移测试通过 |
| 194 | 已完成 | 公共 API 服务发现验证 | 37 个 public API 服务发现测试通过 |
| 195 | 已完成 | 编译验证 | py_compile 通过触及的运行时、公共 API、基准和测试模块 |
| 196 | 已完成 | README 迭代范围扩展 | 工程明细从第 11-149 次扩展到第 11-200 次 |
| 197 | 已完成 | README 契约同步 | 契约测试改为检查第 11-200 次，同时保留 pr-1 到 pr-19 历史摘要 |
| 198 | 已完成 | 进度持久化记录 | `progress.md` 记录本地-only 延迟批次总结和不上传状态 |
| 199 | 已完成 | 保持本地-only 策略 | 按用户要求没有执行上传或远程发布；远程烟测未运行 |
| 200 | 已完成 | 第 200 次延迟检查点 | 准备最终本地验证和交接，下一步仍以降低真实回复延迟为唯一目标 |
</details>

---

## 项目定位

普通的情绪化 bot 往往只做两件事：

1. 在提示词里写“你要有喜怒哀乐”。
2. 根据最近一两句话临时改变语气。

这样的问题是状态不稳定。用户连续刷很多文本，bot 的状态可能被立刻洗掉；换一个 persona，旧情绪又可能错误继承；其他插件想调用“当前 bot 是否还在生气”，也没有稳定协议。

本插件把情绪和拟人行为拆成多层：

| 层 | 作用 | 默认状态 |
| --- | --- | --- |
| `emotion_state` | 核心情绪状态。维护 7 维向量、人格基线、后果状态和关系修复判断。 | 开启 |
| `humanlike_state` | 拟人/有机体样表达调制。维护能量、压力、注意力、边界需求等状态。 | 关闭 |
| `lifelike_learning_state` | 生命化学习/共同语境层。维护新词、黑话、用户画像证据、偏好、边界和开口/沉默时机。 | 关闭 |
| `personality_drift_state` | 真实时间人格漂移层。让 persona 在长期事件中小幅、有界、缓慢适应。 | 关闭 |
| `moral_repair_state` | 道德修复/信任修复层。记录责任、内疚、道歉、补偿和修复趋势。 | 关闭 |
| `fallibility_state` | 瑕疵/犯错模拟层。维护误读、记忆模糊、轻微嘴硬、澄清、纠错和补偿压力。 | 关闭 |
| `psychological_screening` | 非诊断心理状态筛查与长期趋势备用模块。 | 关闭 |

核心设计原则：

- **LLM 负责语义评价**：他/她判断“这句话对当前人格意味着什么”。
- **本地公式负责状态动力学**：半衰期、平滑、限幅、冷处理持续时间不交给 LLM 随意决定。
- **人格是先验，不只是文风**：不同 AstrBot persona 有不同基线、反应强度和恢复速度。
- **真实时间优先于消息轮数**：状态恢复、冷处理和后果衰减按时间戳计算，不能靠刷屏洗掉。
- **公共 API 优先于私有 KV**：其他插件应调用稳定 async 方法，不直接读写内部 key。
- **共同语境要先求证再使用**：新词和小圈子黑话在置信度不足时只触发轻量追问，不假装已经懂。
- **后门可配置**：`allow_emotion_reset_backdoor`、`allow_humanlike_reset_backdoor`、`allow_lifelike_learning_reset_backdoor`、`allow_personality_drift_reset_backdoor`、`allow_moral_repair_reset_backdoor` 和 `allow_fallibility_reset_backdoor` 默认开启，便于异常状态紧急重置。

---

## 核心能力总览

| 能力 | 默认状态 | 说明 |
| --- | --- | --- |
| LLM 情绪估计 | 开启 | 让模型输出结构化 JSON，包含 7 维观测、置信度、冲突分析和关系决策。 |
| 启发式回退 | 内置 | 关闭 `use_llm_assessor` 或 LLM 失败时，使用轻量规则估计状态。 |
| 7 维情绪向量 | 开启 | `valence`、`arousal`、`dominance`、`goal_congruence`、`certainty`、`control`、`affiliation`。 |
| 人格建模 | 开启 | 从当前 AstrBot persona 构造基线和参数偏置，让不同 bot 的反应不同。 |
| 真实时间半衰期 | 开启 | 情绪、后果、冷处理都按真实经过时间衰减，不按消息数量衰减。 |
| 反刷屏门控 | 开启 | `min_update_interval_seconds` 和 `rapid_update_half_life_seconds` 会削弱短时间连续更新。 |
| 关系修复判断 | 开启 | LLM 判断原谅、修复、设边界、冷处理、升级冲突或无冲突。 |
| 冲突原因分析 | 开启 | 区分用户犯错、bot 任性、bot 误读、双方责任、外部原因或无冲突。 |
| 错误改正判断 | 开启 | 判断用户是否承认、道歉是否可信、是否补救、是否反复发生。 |
| 情绪后果 | 开启 | 把情绪映射为靠近、退避、对抗、安抚、修复、确认、谨慎、反刍等行动倾向。 |
| 冷处理/冷战 | 开启 | 作为持续效果保存到 `active_effects`，按真实时间到期或被修复信号清除。 |
| 安全边界开关 | 默认开启 | `enable_safety_boundary=true` 时限制冷处理表现；关闭后只保留普通情绪后果调制。 |
| 临时注入 | 开启 | 使用 `TextPart(...).mark_as_temp()` 注入，不污染长期聊天记录。 |
| LivingMemory 注解 | 开启 | 写入长期记忆时可冻结当时的 `emotion_at_write`。 |
| 公共 API | 开启 | 其他插件可读取快照、提交观察、模拟更新、构造提示词片段或重置状态。 |
| 低推理友好模式 | 默认关闭 | 用短提示词和简单公式降低小模型令牌压力。 |
| 拟人状态模块 | 默认关闭 | `humanlike_state` 可调制能量、压力、注意力、边界和透明度。 |
| 生命化学习模块 | 默认关闭 | `lifelike_learning_state` 学习新词、黑话、用户偏好、共同语境和说话/沉默时机。 |
| 人格漂移模块 | 默认关闭 | `personality_drift_state` 让长期事件按真实时间小幅改变运行时 persona 偏移。 |
| 道德修复模块 | 默认关闭 | `moral_repair_state` 记录责任、内疚、道歉、补偿和信任修复趋势。 |
| 瑕疵模拟模块 | 默认关闭 | `fallibility_state` 让他/她可以有误读、记忆模糊、轻微嘴硬和事后纠错，但不生成欺骗或作恶策略。 |
| 心理筛查模块 | 默认关闭 | 只做非诊断趋势记录和红旗提示，不做疾病判断。 |

---

## 快速开始

### 方式一：上传发布 zip 包

这是准备发布到新仓库后最推荐的安装方式，适合普通部署和远程测试服。

1. 在本仓库根目录构建发布包：

```powershell
py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip
```

2. 打开 AstrBot WebUI 的插件页面。
3. 选择从文件安装或上传插件。
4. 上传 `dist\astrbot_plugin_emotional_state.zip`。
5. 重载插件或重启 AstrBot。
6. 在会话里执行 `/emotion`、`/emotion_model`、`/integrated_self` 做基础检查。

> **警告**
> 不要直接上传 GitHub 绿色 Code 按钮下载的源码 zip，除非它经过 `scripts\package_plugin.py` 或等价流程重新打包。AstrBot WebUI 上传安装期望 zip 内有明确顶层目录 `astrbot_plugin_emotional_state/`，并且运行文件位于该目录下。

发布 zip 包的运行根目录应类似：

```text
astrbot_plugin_emotional_state/
├── __init__.py
├── metadata.yaml
├── main.py
├── emotion_engine.py
├── humanlike_engine.py
├── lifelike_learning_engine.py
├── personality_drift_engine.py
├── integrated_self.py
├── moral_repair_engine.py
├── fallibility_engine.py
├── psychological_screening.py
├── prompts.py
├── public_api.py
├── _conf_schema.json
├── requirements.txt
├── LICENSE
├── README.md
└── docs/
```

### 方式二：从 GitHub 仓库安装

新仓库创建并推送后，在 AstrBot WebUI 的仓库安装入口填写：

```text
https://github.com/Ayleovelle/astrbot_plugin_emotional_state
```

如果 WebUI 要求 `.git` 后缀：

```text
https://github.com/Ayleovelle/astrbot_plugin_emotional_state.git
```

新仓库地址已经写入 `metadata.yaml` 的 `repo:` 字段；后续发布 GitHub 发布版本时，只需要确认 README、发布附件名、插件目录名和 `metadata.yaml name:` 都保持 `astrbot_plugin_emotional_state`。

### 方式三：手动复制到插件目录

开发或本地调试时，可以把本目录放入 AstrBot 插件目录：

```text
data/plugins/
└── astrbot_plugin_emotional_state/
    ├── __init__.py
    ├── metadata.yaml
    ├── main.py
    ├── emotion_engine.py
    ├── humanlike_engine.py
    ├── lifelike_learning_engine.py
    ├── personality_drift_engine.py
    ├── integrated_self.py
    ├── moral_repair_engine.py
    ├── fallibility_engine.py
    ├── psychological_screening.py
    ├── prompts.py
    ├── public_api.py
    ├── _conf_schema.json
    ├── requirements.txt
    ├── LICENSE
    ├── README.md
    └── docs/
```

`tests/`、`scripts/`、四个 `*_literature_kb/` 知识库目录、`raw/`、`output/`、`dist/` 属于仓库开发、研究或缓存内容，发布 zip 不会包含这些目录。

然后在 AstrBot WebUI 中重载或启用插件。

### 版本要求

来自 `metadata.yaml`：

```yaml
astrbot_version: ">=4.9.2,<5.0.0"
```

`requirements.txt` 当前没有第三方运行时依赖：

```text
# No third-party runtime dependencies.
```

也就是说，插件主要依赖 AstrBot 自身的插件运行环境。

### 最小可用配置

首次使用建议只改这几项：

| 配置项 | 推荐值 | 说明 |
| --- | --- | --- |
| `enabled` | `true` | 启用插件。 |
| `use_llm_assessor` | `true` | 使用 LLM 做情绪观测。 |
| `emotion_provider_id` | 一个便宜稳定的小模型 | 留空则使用当前会话模型。 |
| `assessment_timing` | `post` | 默认只在回复后根据实际输出修正，避免每轮额外双 LLM 评估；需要本轮语气即时受影响时可改为 `pre` 或 `both`。 |
| `inject_state` | `true` | 把状态作为临时上下文注入主 LLM。 |
| `persona_modeling` | `true` | 让不同人格有不同基线。 |
| `enable_safety_boundary` | `true` | 默认开启可控边界，可按需求关闭。 |
| `allow_emotion_reset_backdoor` | `true` | 保留异常状态重置后门。 |

一条实际可用的基础配置：

```text
enabled = true
use_llm_assessor = true
emotion_provider_id = 你的情绪评估模型提供方标识
assessment_timing = post
inject_state = true
persona_modeling = true
enable_safety_boundary = true
allow_emotion_reset_backdoor = true
```

如果你先想省令牌，可以临时打开：

```text
low_reasoning_friendly_mode = true
low_reasoning_max_context_chars = 1200
```

但默认建议关闭低推理模式，让插件保留更完整的冲突分析、关系修复和理论字段。

### 安装后检查

安装完成后，建议按顺序检查：

```text
/emotion
/emotion_model
/emotion_effects
/integrated_self
```

如果打开了可选模块，再检查：

```text
/humanlike_state
/lifelike_state
/personality_drift_state
/moral_repair_state
/fallibility_state
/psych_state
```

`/emotion_reset`、`/humanlike_reset`、`/lifelike_reset`、`/personality_drift_reset`、`/moral_repair_reset` 和 `/fallibility_reset` 是异常状态恢复命令，分别受 `allow_emotion_reset_backdoor`、`allow_humanlike_reset_backdoor`、`allow_lifelike_learning_reset_backdoor`、`allow_personality_drift_reset_backdoor`、`allow_moral_repair_reset_backdoor`、`allow_fallibility_reset_backdoor` 控制。

---

## 命令

| 命令 | 别名 | 用途 |
| --- | --- | --- |
| `/emotion` | `/emotion_state`、`/情绪状态` | 查看当前会话的核心 7 维情绪状态。 |
| `/emotion_reset` | `/情绪重置` | 重置当前会话的情绪状态，受 `allow_emotion_reset_backdoor` 控制。 |
| `/emotion_model` | `/情绪模型` | 查看模型公式、真实时间衰减和人格基线说明。 |
| `/emotion_effects` | `/情绪后果` | 查看当前行动倾向、冷处理、修复、谨慎核对等后果。 |
| `/psych_state` | `/心理筛查`、`/心理状态` | 查看非诊断心理状态筛查快照。 |
| `/humanlike_state` | `/拟人状态`、`/有机体状态` | 查看拟人状态。 |
| `/humanlike_reset` | `/拟人状态重置` | 重置拟人状态，受 `allow_humanlike_reset_backdoor` 控制。 |
| `/lifelike_state` | `/生命化状态`、`/共同语境` | 查看生命化学习状态，包括新词、黑话、用户画像证据和开口策略。 |
| `/lifelike_reset` | `/生命化状态重置`、`/共同语境重置` | 重置生命化学习状态，受 `allow_lifelike_learning_reset_backdoor` 控制。 |
| `/personality_drift_state` | `/人格漂移状态`、`/人格适应状态` | 查看真实时间人格漂移状态、锚点强度、时间门控和主要偏移。 |
| `/personality_drift_reset` | `/人格漂移重置`、`/人格适应重置` | 重置人格漂移状态，受 `allow_personality_drift_reset_backdoor` 控制。 |
| `/moral_repair_state` | `/道德修复状态`、`/信任修复状态` | 查看道德修复/信任修复状态。 |
| `/moral_repair_reset` | `/道德修复重置`、`/信任修复重置` | 重置道德修复状态，受 `allow_moral_repair_reset_backdoor` 控制。 |
| `/fallibility_state` | `/瑕疵状态`、`/犯错模拟状态` | 查看低风险瑕疵/犯错模拟状态。 |
| `/fallibility_reset` | `/瑕疵状态重置`、`/犯错模拟重置` | 重置瑕疵/犯错模拟状态，受 `allow_fallibility_reset_backdoor` 控制。 |
| `/integrated_self` | `/综合自我状态`、`/自我状态` | 查看跨模块综合自我状态仲裁。 |
| `/shadow_diagnostics` | `/阴影诊断`、`/阴影状态` | 查看配置门控的只读阴影冲动诊断视图；默认关闭，仅用于维护排查，不生成欺骗、操控、逃责或执行策略。 |

### 情绪状态

```text
/emotion
/emotion_state
/情绪状态
```

查看当前会话的多维情绪状态，包括 7 维数值、人格、置信度、最近原因和关系判断。

### 重置情绪

```text
/emotion_reset
/情绪重置
```

重置当前会话的情绪状态。该命令受 `allow_emotion_reset_backdoor` 控制；默认允许。

### 查看模型公式

```text
/emotion_model
/情绪模型
```

查看插件使用的核心数学模型和公式说明。

### 查看情绪后果

```text
/emotion_effects
/情绪后果
```

查看当前会话的行动倾向和持续效果，例如冷处理、主动修复、谨慎核对等。

### 心理筛查状态

```text
/psych_state
/心理筛查
/心理状态
```

查看非诊断心理状态筛查快照。默认情况下 `enable_psychological_screening=false`，所以这个模块不会主动建模。

### 拟人状态

```text
/humanlike_state
/拟人状态
/有机体状态
```

查看模拟拟人状态。默认情况下 `enable_humanlike_state=false`。

### 重置拟人状态

```text
/humanlike_reset
/拟人状态重置
```

重置当前会话的 `humanlike_state`。该命令受 `allow_humanlike_reset_backdoor` 控制；默认允许。

### 生命化学习状态

```text
/lifelike_state
/生命化状态
/共同语境
```

查看当前会话的生命化学习状态。该模块默认 `enable_lifelike_learning=false`，开启后会按真实时间学习用户画像证据、新词、黑话、喜恶、边界提示和当前是否适合开口。

### 重置生命化学习状态

```text
/lifelike_reset
/生命化状态重置
/共同语境重置
```

重置当前会话的 `lifelike_learning_state`。该命令受 `allow_lifelike_learning_reset_backdoor` 控制；默认允许。

### 人格漂移状态

```text
/personality_drift_state
/人格漂移状态
/人格适应状态
```

查看当前会话的 `personality_drift_state`。该模块默认 `enable_personality_drift=false`；开启后，人格只会围绕静态 persona 锚点产生缓慢、有界的真实时间偏移。短时间大量消息不会线性累积人格变化，滚动上下文也不会被反复当作新证据。

### 重置人格漂移状态

```text
/personality_drift_reset
/人格漂移重置
/人格适应重置
```

重置当前会话的 `personality_drift_state`。该命令受 `allow_personality_drift_reset_backdoor` 控制；默认允许，用于异常适应、人格污染、调试或严重后果回滚。

### 道德修复状态

```text
/moral_repair_state
/道德修复状态
/信任修复状态
```

查看模拟道德修复/信任修复状态。默认情况下 `enable_moral_repair_state=false`。

### 重置道德修复状态

```text
/moral_repair_reset
/道德修复重置
/信任修复重置
```

重置当前会话的 `moral_repair_state`。该命令受 `allow_moral_repair_reset_backdoor` 控制；默认允许。

### 瑕疵模拟状态

```text
/fallibility_state
/瑕疵状态
/犯错模拟状态
```

查看低风险瑕疵/犯错模拟状态。默认情况下 `enable_fallibility_state=false`。开启后，他/她会维护误读倾向、记忆模糊、过度自信、轻微嘴硬、回避、澄清需求、纠错准备和补偿压力等维度。

### 重置瑕疵模拟状态

```text
/fallibility_reset
/瑕疵状态重置
/犯错模拟重置
```

重置当前会话的 `fallibility_state`。该命令受 `allow_fallibility_reset_backdoor` 控制；默认允许。

### 综合自我状态

```text
/integrated_self
/综合自我状态
/自我状态
```

查看只读的综合自我状态仲裁结果。该总线会融合情绪、拟人状态、道德修复和非诊断心理筛查快照，但不会直接写入 KV。

### 阴影诊断

```text
/shadow_diagnostics
/阴影诊断
/阴影状态
```

查看配置者开启后的只读阴影冲动诊断载荷。默认情况下 `enable_shadow_diagnostics=false`，命令只会返回未启用说明；开启后会输出 JSON，用于维护排查 moral repair、fallibility 和 integrated self 中的非执行阴影冲动、内疚/补偿压力和信任修复成本。该入口不会生成欺骗、操控、逃责或执行策略。

---

## 工作流

插件在 AstrBot LLM 请求前后工作。

```mermaid
flowchart TD
    A["用户输入 / 其他插件输入"] --> B["读取 session_key 与当前 persona"]
    B --> C["加载 emotion_state"]
    C --> D{"assessment_timing 包含 pre ?"}
    D -- "是" --> E["LLM/启发式生成即时观测 X_t"]
    E --> F["本地公式更新 E_t 与 consequences"]
    D -- "否" --> G["跳过 pre 更新"]
    F --> H{"inject_state ?"}
    G --> H
    H -- "是" --> I["临时注入 emotion 提示词片段"]
    I --> J{"enable_humanlike_state 且注入强度 > 0 ?"}
    J -- "是" --> K["临时注入 humanlike 提示词片段"]
    J -- "否" --> L["调用主 LLM"]
    K --> L
    H -- "否" --> L
    L --> M["bot 回复"]
    M --> N{"assessment_timing 包含 post ?"}
    N -- "是" --> O["根据 bot 实际回复二次校正状态"]
    N -- "否" --> P["结束"]
    O --> P
```

几个关键点：

- `pre` 更新会影响本轮回复语气。
- `post` 更新会根据 bot 实际说出口的内容修正状态。
- `both` 最完整，但会多一次情绪评估消耗。
- 注入使用临时 `TextPart`，不会直接写进长期消息记录。
- 状态落库使用 AstrBot KV，不建议外部插件直接改内部 key。

---

## 情绪模型

### 7 维向量

插件默认维护：

```math
E_t(P) \in [-1, 1]^7
```

```math
E_t =
\begin{bmatrix}
V_t & A_t & D_t & G_t & C_t & K_t & S_t
\end{bmatrix}^{\mathsf T}
```

| 维度 | 字段 | 含义 | 高值表现 | 低值表现 |
| --- | --- | --- | --- | --- |
| 效价 | `valence` | 愉悦/不愉悦 | 温和、满意、接纳 | 不快、受伤、防御 |
| 唤醒 | `arousal` | 激活强度 | 警觉、急促、表达增强 | 平静、低能量、迟缓 |
| 支配感 | `dominance` | 自主感和社交掌控 | 坚定、设边界 | 迟疑、退让 |
| 目标一致性 | `goal_congruence` | 当前事件是否符合角色目标 | 顺利、被理解 | 受阻、挫败 |
| 确定性 | `certainty` | 对情境解释的确定程度 | 直接判断 | 先核对、承认不确定 |
| 可控性 | `control` | 对局面可控程度的评估 | 解决问题 | 回避、求助、谨慎 |
| 亲和度 | `affiliation` | 对用户的亲近和信任 | 靠近、修复、温度 | 距离感、防御、冷处理 |

前三维对应 PAD 和环形情感模型；后四维来自评价理论与 OCC 对事件、行动者和对象的认知评价。

### 默认阅读：核心模型摘要

默认只需要理解五件事：

| 层级 | 核心公式 | 设计理由 |
| --- | --- | --- |
| 状态空间 | `E_t(P) in [-1,1]^7` | 情绪不是单一标签，而是可连续调制的多维状态。 |
| 人格先验 | `b_p = h_b(P)`，`theta_p = h_theta(P)` | persona 不只决定文风，也决定基线、反应强度和恢复速度。 |
| 即时观测 | `X_t = tanh(WZ_t + beta)` | LLM 负责把上下文解释成 appraisal 与即时情绪观测。 |
| 长期更新 | `E'_t = B_t + alpha_t(X_t-B_t)` | 当前刺激会改变状态，但不能一轮文本完全覆盖长期情绪。 |
| 真实时间 | `gamma_p(Delta t)=1-2^{-Delta t/H_p}` | 恢复和冷处理按真实时间衰减，不能靠刷屏强行洗掉。 |

这套模型的工程折中是：LLM 负责语义评价，本地公式负责惯性、限幅、半衰期、人格基线和后果衰减。下面是完整论证，默认折叠，维护模型或写论文时再展开。

### 真实时间人格漂移模型

静态 persona 仍是人格锚点；长期事件只写入一个会话级有界偏移 `Delta p_t`。模型核心是：先按真实经过时间回拉到锚点，再让当前真实事件产生很小冲量。历史上下文不会被重复当作新事件；`evidence_count` 只用于诊断，不是消息数权重。

```math
\lambda(\Delta t;T_p)=2^{-\Delta t/T_p}
```

```math
g(\Delta t;T_g)=1-2^{-\Delta t/T_g}
```

```math
\Delta p_t^{(i)}
=
\mathrm{clip}
\left(
\lambda(\Delta t;T_p)\Delta p_{t-1}^{(i)}
+
\mathrm{clip}\left(\eta s_t u_t^{(i)},-e_{\max},e_{\max}\right),
-O_{\max},O_{\max}
\right)
```

```math
p_t^{(i)}=\mathrm{clip}\left(p_0^{(i)}+\beta\Delta p_t^{(i)},-1,1\right)
```

这里 `p_0` 是 AstrBot persona 推导出的静态人格先验，`Delta p_t` 是相对偏移，`u_t` 是当前事件映射到人格维度的冲量向量，`T_p` 默认 90 天，`T_g` 默认 1 天，`e_max` 默认 `0.015`，`O_max` 默认 `0.22`。所以一条消息、短时间刷屏或重复上下文都不能把他/她强行改造成另一个人。

<details>
<summary>展开人格漂移公式推导与文献依据</summary>

人格漂移不是“修改 persona 文本”，而是把 persona 看成状态分布的中心。Fleeson 的 whole-trait / density-distribution 思路支持“人格是状态分布而非固定脚本”；Mischel 与 Shoda 的 CAPS 支持“if-then 情境反应模式”；DeYoung 的 Cybernetic Big Five Theory 支持把人格特质视为目标调节和控制参数。TESSERA 框架进一步把长期人格改变拆成触发情境、预期、状态、状态表达、反应和反思/行动单元，强调重复事件需要经过时间、反思和强化才会沉积为特质改变。

把静态 persona 先验记为：

```math
p_0\in[-1,1]^d
```

运行时人格不是直接改写 `p_0`，而是：

```math
p_t=p_0+\beta\Delta p_t
```

其中 `beta` 是 `personality_drift_apply_strength`。为了使漂移回到锚点，先对上一时刻偏移做半衰：

```math
\Delta p_{t,\mathrm{decay}}=\lambda(\Delta t;T_p)\Delta p_{t-1}
```

短时刷屏门控写作：

```math
g(\Delta t;T_g)=1-2^{-\Delta t/T_g}
```

当 `Delta t` 很小时，`g` 接近 0；只有真实时间经过后，事件冲量才逐渐被放行。事件信号：

```math
s_t=r_t c_t g(\Delta t;T_g)(0.72+0.28q_t)
```

其中 `r_t` 是事件强度，`c_t` 是可靠性，`q_t` 是关系重要性。单维更新：

```math
\Delta p_t^{(i)}
=
\mathrm{clip}
\left(
\Delta p_{t,\mathrm{decay}}^{(i)}
+
\mathrm{clip}\left(\eta s_t u_t^{(i)},-e_{\max},e_{\max}\right),
-O_{\max},O_{\max}
\right)
```

如果事件信号低于 `personality_drift_event_threshold`，则不固化为人格漂移证据。实现上 `on_llm_request` 只把当前消息作为人格漂移事件；滚动 `contexts`、系统提示词和注入状态不会被重复计入长期人格偏移。外部插件可通过 `observed_at` 传入真实事件时间，模型使用 `now - updated_at` 计算门控与半衰。

主要依据：

- Fleeson, W. (2001). Traits as density distributions of states. *Journal of Personality and Social Psychology*. DOI `10.1037/0022-3514.80.6.1011`.
- Mischel, W., & Shoda, Y. (1995). A cognitive-affective system theory of personality. *Psychological Review*. DOI `10.1037/0033-295X.102.2.246`.
- DeYoung, C. G. (2015). Cybernetic Big Five Theory. *Journal of Research in Personality*. DOI `10.1016/j.jrp.2014.07.004`.
- Wrzus, C., & Roberts, B. W. (2017). Processes of personality development in adulthood: The TESSERA framework. *Personality and Social Psychology Review*. DOI `10.1177/1088868316652279`.
- Baumert, A., Schmitt, M., Perugini, M., et al. (2017). Integrating personality structure, process, and development. *European Journal of Personality*. DOI `10.1002/per.2115`.
- Roberts, B. W., Walton, K. E., & Viechtbauer, W. (2006). Patterns of mean-level change in personality traits across the life course. *Psychological Bulletin*. DOI `10.1037/0033-2909.132.1.1`.

</details>

<details>
<summary>展开完整公式推导与顶刊依据</summary>

#### 顶刊证据映射

| 模型部件 | 采用的工程形式 | 顶刊/高影响依据 | 插件中的取舍 |
| --- | --- | --- | --- |
| 多维情绪空间 | PAD + appraisal 扩展为 7 维向量 | Russell 1980, *Journal of Personality and Social Psychology*, DOI `10.1037/h0077714`；Mehrabian & Russell 1974；Scherer 2005, DOI `10.1177/0539018405058216`。 | 用连续向量保存状态，而不是只用“开心/生气/难过”标签。 |
| 人格作为先验 | `b_p` 与 `theta_p` 从 persona 派生 | 评价理论强调评价依赖目标、责任、可控性和情境意义；Roseman 1991, DOI `10.1080/02699939108411034`。 | 不做临床人格测量，只把 persona 转成工程先验，让不同 bot 有不同默认姿态。 |
| 惯性更新 | 加权二次目标函数推出指数平滑 | Kuppens、Allen & Sheeber 2010, *Psychological Science*, DOI `10.1177/0956797610372634`；Gross 1998, DOI `10.1037/1089-2680.2.3.271`。 | 用 `E_{t-1}` 与 `X_t` 的加权折中防止单轮文本劫持状态。 |
| 置信门控与惊讶度 | `g(c_t)` 与 `delta_t` 调制 `alpha_t` | Scherer 2005 的成分过程模型；Roseman 1991 对概率、合法性、因果主体等评价维度的实验检验。 | 低置信 LLM 输出只轻微更新，高显著事件才提高步长。 |
| 行动倾向 | `O_t` 表示 approach、withdrawal、repair 等后果 | Frijda, Kuipers & ter Schure 1989, *Journal of Personality and Social Psychology*, DOI `10.1037/0022-3514.57.2.212`；Carver & Harmon-Jones 2009, *Psychological Bulletin*, DOI `10.1037/a0013965`。 | 生气不必然冷战，可走边界、修复、求证或解决问题。 |
| 冷处理与修复 | 关系决策 + 冲突成因 + 真实时间持续效果 | Christensen & Heavey 1990, *Journal of Personality and Social Psychology*, DOI `10.1037/0022-3514.59.1.73`；Fehr et al. 2010, *Psychological Bulletin*, DOI `10.1037/a0019993`；Ohbuchi et al. 1989, DOI `10.1037/0022-3514.56.2.219`。 | 冷处理是可衰减后果状态；道歉、承认、补救和误读会压低惩罚性后果。 |

### 人格先验

从 `0.1.0-beta` 开始，人格建模不再只是少量风格关键词偏置。插件会从当前 AstrBot persona 文本构造一个带版本号的 13 维潜在人格先验向量，覆盖大五人格、HEXACO 中的诚实-谦逊扩展、依恋焦虑/回避、BIS/BAS、认知闭合需要、情绪调节能力和人际温暖度。

默认摘要：

```math
q_p = \left(M^{\mathsf T}RM+\lambda\Sigma^{-1}\right)^{-1}
\left(M^{\mathsf T}Ry+\lambda\Sigma^{-1}\mu\right)
```

```math
b_p = \Pi_{[-1,1]^7}(b_0+Bq_p),\qquad
\theta_p = \Pi_{[0.55,1.55]^m}(\theta_0+Cq_p)
```

这里 `q_p` 是潜在人格向量，`y` 是多源 persona 文本指标向量，`R` 是来源可靠度，`mu` 与 `Sigma` 是保守先验。公开 payload 会暴露 `personality_model.schema_version = astrbot.personality_profile.v1`、`trait_scores`、`trait_confidence`、`posterior_variance` 和 `derived_factors`，但不会暴露原始 persona 文本。

这不是临床人格评估，而是工程先验：它让不同 bot 拥有稳定、可复现、可被外部读取的情绪基线、反应性、边界敏感度、修复取向和社交距离。

<details>
<summary>展开严格人格量化公式与期刊依据</summary>

人格输入：

```math
P = \{\mathrm{persona\_id}, \mathrm{name}, \mathrm{system\_prompt}, \mathrm{begin\_dialogs}\}
```

为了保持向后兼容，旧工程特质仍保留：

```math
T_p =
\begin{bmatrix}
\mathrm{warmth} & \mathrm{shyness} & \mathrm{assertiveness} & \mathrm{volatility} &
\mathrm{calmness} & \mathrm{optimism} & \mathrm{pessimism} & \mathrm{dutifulness}
\end{bmatrix}^{\mathsf T}
```

新的潜在向量为：

```math
q_p =
\begin{bmatrix}
O & N & X & A & L & H & R_a & R_v & I & B & F & U & W_s
\end{bmatrix}^{\mathsf T}
```

这些维度依次表示开放性、尽责性、外向性、宜人性、神经质、诚实-谦逊、依恋焦虑、依恋回避、BIS 敏感性、BAS 驱动、认知闭合需要、情绪调节能力和人际温暖度。

多源指标：

```math
y =
\begin{bmatrix}
y_{\mathrm{lex}} & y_{\mathrm{legacy}} & y_{\mathrm{struct}}
\end{bmatrix}^{\mathsf T}
```

可靠度加权后验来自带先验收缩的最小二乘目标：

```math
J(q)=\|Mq-y\|_R^2+\lambda\|q-\mu\|_{\Sigma^{-1}}^2
```

求导：

```math
\frac{\partial J}{\partial q}=
2M^{\mathsf T}R(Mq-y)+2\lambda\Sigma^{-1}(q-\mu)
```

令导数为零：

```math
(M^{\mathsf T}RM+\lambda\Sigma^{-1})q=
M^{\mathsf T}Ry+\lambda\Sigma^{-1}\mu
```

闭式后验解：

```math
q_p = \left(M^{\mathsf T}RM+\lambda\Sigma^{-1}\right)^{-1}
\left(M^{\mathsf T}Ry+\lambda\Sigma^{-1}\mu\right)
```

近似后验不确定性：

```math
V_q = \left(M^{\mathsf T}RM+\lambda\Sigma^{-1}\right)^{-1}
```

运行时使用确定性的对角近似：

```math
q_i = \frac{\sum_j r_j y_{j,i}+\lambda\mu_i}{\sum_j r_j+\lambda}
```

```math
\mathrm{var}_i = \frac{1}{\sum_j r_j+\lambda}
```

人格后验映射到情绪基线和动力学参数：

```math
b_p = \Pi_{[-1,1]^7}(b_0+Bq_p)
```

```math
\theta_p = \Pi_{[0.55,1.55]^m}(\theta_0+Cq_p)
```

派生因子：

```math
\begin{aligned}
\mathrm{instability}_p &= a_1L+a_2R_a+a_3I-a_4U,\\
\mathrm{distance}_p &= a_5R_v-a_6W_s-a_7X,\\
\mathrm{repair}_p &= a_8A+a_9H+a_{10}U-a_{11}R_v,\\
\mathrm{boundary}_p &= a_{12}I+a_{13}F+a_{14}N-a_{15}A.
\end{aligned}
```

证据依据：大五人格结构参考 Digman 1990、Goldberg 1990 与 McCrae & Costa 1987；HEXACO 扩展参考 Ashton & Lee 2007；人格状态分布和情境-反应动力学参考 Fleeson 2001 与 Mischel & Shoda 1995；BIS/BAS 参考 Carver & White 1994；认知闭合需要参考 Webster & Kruglanski 1994；依恋维度参考 Fraley、Waller & Brennan 2000；情绪调节差异参考 Gross & John 2003。大规模检索索引只作为本地研究资产保留，不进入公开仓库或发布 zip 包。

</details>

### LLM 观测

设本轮输入为：

```math
I_t = \{H_t, U_t, P, E_{t-1}\}
```

含义：

- `H_t`：最近上下文。
- `U_t`：当前用户输入或 bot 回复。
- `P`：当前 persona。
- `E_{t-1}`：上一轮平滑状态。

理论上可以把 LLM 的判断拆成隐藏评价向量：

```math
Z_t =
\begin{bmatrix}
z_{\mathrm{goal}} & z_{\mathrm{novelty}} & z_{\mathrm{agency}} &
z_{\mathrm{control}} & z_{\mathrm{certainty}} & z_{\mathrm{norm}} &
z_{\mathrm{social}}
\end{bmatrix}^{\mathsf T}
```

```math
Z_t = \phi_{\mathrm{llm}}(I_t), \qquad
X_t = \tanh(WZ_t + \beta)
```

工程上，本插件让 LLM 直接输出：

```json
{
  "label": "embarrassed_defensive",
  "dimensions": {
    "valence": -0.2,
    "arousal": 0.4,
    "dominance": -0.1,
    "goal_congruence": -0.3,
    "certainty": 0.2,
    "control": -0.2,
    "affiliation": 0.1
  },
  "confidence": 0.76,
  "appraisal": {
    "relationship_decision": {
      "decision": "repair",
      "intensity": 0.58,
      "forgiveness": 0.74,
      "relationship_importance": 0.8,
      "reason": "用户已解释并愿意补救"
    }
  },
  "reason": "用户的话造成轻微挫败，但有修复空间"
}
```

LLM 负责“发生了什么”；本地引擎负责“这种意义怎样改变长期状态”。

### 状态更新推导

如果直接令：

```math
E_t = X_t
```

情绪会被单轮文本完全支配，表现为跳变。插件改为求解一个带惯性的加权最小化问题：

```math
E_t = \arg\min_{E} J(E)
```

```math
J(E) =
(1-\alpha_t)\|E-B_t\|_W^2
+ \alpha_t\|E-X_t\|_W^2
```

其中 `B_t` 是上一状态经人格基线回归后的先验：

```math
B_t = (1-\gamma_p)E_{t-1} + \gamma_p b_p
```

```math
\gamma_p(\Delta t) = 1 - 2^{-\Delta t/H_p}
```

`\Delta t` 是真实经过时间，`H_p` 是被人格调制后的半衰期。

对目标函数求导：

```math
\frac{\partial J}{\partial E}
= 2(1-\alpha_t)W(E-B_t) + 2\alpha_t W(E-X_t)
```

令导数为零：

```math
(1-\alpha_t)W(E-B_t) + \alpha_t W(E-X_t) = 0
```

若 `W` 正定，可消去 `W`：

```math
(1-\alpha_t)(E-B_t) + \alpha_t(E-X_t) = 0
```

得到：

```math
E'_t = B_t + \alpha_t(X_t-B_t)
```

所以指数平滑不是随意拼公式，而是“保持情绪惯性”和“接纳当前观测”之间的二次优化解。

### 自适应步长

插件使用置信门控和惊讶度调制更新步长：

```math
\alpha_t =
\mathrm{clamp}\left(
\alpha_{\mathrm{base},p}\,g(c_t)(1+r_p\delta_t),
\alpha_{\min},
\alpha_{\max}
\right)
```

```math
g(c_t) = \frac{1}{1+\exp[-k(c_t-c_0)]}
```

其中：

- `c_t` 是 LLM 输出的置信度。
- `g(c_t)` 让低置信观测影响变小。
- `delta_t` 是观测和先验的加权距离。
- `r_p` 来自 persona 参数偏置。

惊讶度：

```math
\delta_t =
\sqrt{
\frac{(X_t-B_t)^{\mathsf T}W(X_t-B_t)}
{\mathrm{tr}(W)}
}
```

### 维度耦合

插件只加入两个弱耦合项，避免模型不可解释。

惊讶度提升唤醒度：

```math
A_t = A'_t + \eta\alpha_t\delta_t\left(1-|A'_t|\right)
```

可控性牵引支配感：

```math
D_t = D'_t + \lambda\alpha_t(K'_t-D'_t)
```

最后逐维裁剪：

```math
E_t = \Pi_{[-1,1]^7}(E_t)
```

</details>

### 真实时间记忆

核心时间参数：

| 配置项 | 默认值 | 含义 |
| --- | --- | --- |
| `baseline_half_life_seconds` | `21600` | 情绪向人格基线自然恢复的半衰期，默认 6 小时。 |
| `consequence_half_life_seconds` | `10800` | 行动倾向强度自然衰减半衰期，默认 3 小时。 |
| `cold_war_duration_seconds` | `1800` | 冷处理持续真实时间，默认 30 分钟。 |
| `short_effect_duration_seconds` | `900` | 普通短期效果持续时间，默认 15 分钟。 |
| `min_update_interval_seconds` | `8` | 短时间连续更新会被削弱。 |
| `rapid_update_half_life_seconds` | `20` | 快速连续更新门控半衰期。 |

这意味着：

- 过了 6 小时，情绪偏离人格基线的部分约减少一半。
- 冷处理剩余时间不会因为用户刷很多条消息而快速消耗。
- 大量文本可以形成新的观测，但不能绕过最小更新时间和单次更新限幅。

---

## 关系与后果

情绪状态不会直接等于回复模板。默认只需要知道：插件会把 `E_t` 映射成后果状态 `O_t`，其中包括靠近、退避、边界、修复、确认、谨慎、反刍和解决问题等维度；这些后果按真实时间衰减，所以冷处理、缓和和修复不会被消息数量直接刷掉。生气后的走向由“维度公式 + LLM 关系判断 + 冲突成因分析”共同决定，不会把所有负面情绪都硬推成冷战。

<details>
<summary>展开行动倾向、关系决策与后果衰减公式</summary>

插件先把情绪映射到行动倾向：

```math
O_t =
\begin{bmatrix}
\mathrm{approach} & \mathrm{withdrawal} & \mathrm{confrontation} &
\mathrm{appeasement} & \mathrm{repair} & \mathrm{reassurance} &
\mathrm{caution} & \mathrm{rumination} & \mathrm{expressiveness} &
\mathrm{problem\_solving}
\end{bmatrix}^{\mathsf T}
```

这些倾向按真实时间衰减：

```math
O_t = 2^{-\Delta t/H_o}O_{t-1}+\mathrm{impulse}(E_t,X_t,\mathrm{appraisal}_t)
```

| 后果维度 | 字段 | 常见表现 |
| --- | --- | --- |
| 靠近 | `approach` | 更愿意主动解释、接话、维持亲近。 |
| 退避 | `withdrawal` | 降低主动性，减少亲昵，可能进入冷处理。 |
| 对抗/边界 | `confrontation` | 语气更坚定，明确指出越界或错误。 |
| 安抚 | `appeasement` | 降低冲突，先稳定关系。 |
| 修复 | `repair` | 主动解释、给台阶、请求澄清。 |
| 确认 | `reassurance` | 询问意图、确认关系安全。 |
| 谨慎 | `caution` | 先核对事实，避免误会。 |
| 反刍 | `rumination` | 对冲突残留记挂，恢复较慢。 |
| 表达强度 | `expressiveness` | 更直接或更明显地表达情绪。 |
| 解决问题 | `problem_solving` | 把注意力转回具体任务。 |

### LLM 关系决策

当出现生气、冒犯、道歉、误会或修复信号时，LLM 会输出：

```json
{
  "relationship_decision": {
    "decision": "forgive",
    "intensity": 0.6,
    "forgiveness": 0.8,
    "relationship_importance": 0.7,
    "reason": "用户承认错误并给出补救"
  }
}
```

`decision` 可选值：

| 值 | 含义 | 后果 |
| --- | --- | --- |
| `forgive` | 原谅/翻篇 | 退避、反刍、对抗快速下降，冷处理清除。 |
| `repair` | 愿意修复 | 提高修复和确认，保留一定谨慎。 |
| `boundary` | 设边界 | 提高坚定度和边界感，不一定冷战。 |
| `cold_war` | 冷处理/拉开距离 | 提高退避和反刍，添加 `cold_war` 持续效果。 |
| `escalate` | 更强防御或冲突升级 | 提高对抗和表达强度。 |
| `none` | 无明显关系事件 | 不额外触发关系后果。 |

</details>

### 冲突原因分析

默认逻辑：先判断冲突是否真的发生，再判断原因属于用户犯错、他/她任性、误读、双方共同作用还是外部因素；最后再看错误是否被承认、道歉是否可信、补救是否完成。只有“伤害较重、重复发生、补救不足、信任受损”同时较强时，冷处理或强边界才会持续；如果误读概率高或他/她本身反应过度，则会转向求证、修复或自我缓和。

<details>
<summary>展开扩展冲突成因与关系修复公式</summary>

插件要求 LLM 同时输出：

```json
{
  "conflict_analysis": {
    "cause": "user_fault",
    "fault_severity": 0.62,
    "user_acknowledged": true,
    "apology_sincerity": 0.71,
    "repaired": true,
    "repair_quality": 0.68,
    "repeat_offense": 0.1,
    "bot_whim_level": 0.0,
    "misread_likelihood": 0.12,
    "forgiveness_readiness": 0.74,
    "resentment_residue": 0.18,
    "withdrawal_motive": "cooling_down",
    "boundary_legitimacy": 0.42,
    "reason": "用户越界但已承认并补救"
  }
}
```

主要字段：

| 字段 | 含义 |
| --- | --- |
| `cause` | `user_fault`、`bot_whim`、`bot_misread`、`mutual`、`external`、`none`。 |
| `fault_severity` | 错误严重度。 |
| `user_acknowledged` | 用户是否承认问题。 |
| `apology_sincerity` | 道歉可信度。 |
| `repaired` | 错误是否已经被补救。 |
| `repair_quality` | 补救质量。 |
| `repeat_offense` | 是否反复发生。 |
| `bot_whim_level` | 是否可能是 bot 任性或过度反应。 |
| `misread_likelihood` | 是否可能误读用户。 |
| `forgiveness_readiness` | 原谅准备度。 |
| `resentment_residue` | 残留委屈。 |
| `boundary_legitimacy` | 设边界是否合理。 |
| `repair_status` | 派生字段，表示 `unresolved`、`acknowledged`、`repaired`、`restored` 等修复阶段。 |

如果 LLM 一开始判断为 `cold_war`，但冲突分析显示用户已经补救、道歉足够完整、bot 误读概率高，或者原因更像他/她任性，本地后果层会把冷处理转向修复，并清除或降低负面后果。

</details>

### 安全边界开关

`enable_safety_boundary` 默认开启。开启时，插件注入的规则会把冷处理限制为：

- 轻微降频。
- 短句。
- 保持距离。
- 增强边界感。
- 不羞辱、不威胁、不操控、不拒绝必要帮助。

如果你关闭：

```text
enable_safety_boundary = false
```

本插件不再附加上述“冷处理只能如何表现”的额外调制规则，而只按 `active_effects` 和行动倾向调节语气、节奏、距离感与互动策略。关闭这个开关不会改变 AstrBot、模型供应商或其他插件自己的边界规则。

---

## 配置指南

完整配置来自 `_conf_schema.json`。这里按实际使用顺序整理。

### 总开关与模型

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enabled` | bool | `true` | 启用插件。 |
| `use_llm_assessor` | bool | `true` | 使用 LLM 判断情绪观测值；关闭后只使用启发式回退。 |
| `emotion_provider_id` | string | `""` | 情绪估计使用的 LLM Provider；留空使用当前会话模型。 |
| `assessment_timing` | string | `post` | `pre`、`post` 或 `both`。默认 `post` 用一次内部评估降低延迟；`both` 质量更强但更慢。 |
| `inject_state` | bool | `true` | 是否把当前状态临时注入主 LLM。 |
| `max_context_chars` | int | `1600` | 情绪估计读取的最大上下文字数。 |
| `request_context_max_chars` | int | `1600` | 生命周期钩子拼接上下文时的总字数上限。 |
| `assessor_timeout_seconds` | float | `4.0` | 情绪估计 LLM 超时秒数；默认按 5 秒回复目标保守设置，超时后回退到启发式估计；追求质量可调高。 |
| `provider_id_cache_ttl_seconds` | float | `30.0` | 未配置 `emotion_provider_id` 时，当前会话提供方标识的短缓存秒数。 |
| `passive_load_fresh_seconds` | float | `1.0` | 短时间重复读状态时跳过被动衰减计算，减少公共 API 与注入路径延迟。 |
| `benchmark_enable_simulated_time` | bool | `false` | 远程性能/生命周期基准测试专用；开启后允许测试脚本注入模拟时间偏移。 |
| `benchmark_time_offset_seconds` | float | `0.0` | 远程性能/生命周期基准测试专用；仅在 `benchmark_enable_simulated_time=true` 时把观测时间视为 `time.time()+offset`。 |
| `assessor_temperature` | float | `0.1` | 情绪估计模型 temperature。 |

`benchmark_enable_simulated_time` 和 `benchmark_time_offset_seconds` 只用于测试真实时间半衰期、人格漂移和长期状态模型。生产对话应保持默认关闭；生命周期 benchmark 会临时把 offset 设置为 `1d`、`1w`、`1m`、`1y` 等秒数，跑完后由远程脚本恢复原配置。

### 低推理模型友好模式

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `low_reasoning_friendly_mode` | bool | `false` | 开启后使用短版提示词和简化公式。 |
| `low_reasoning_max_context_chars` | int | `1200` | 低推理模式下最大上下文字数，会与 `max_context_chars` 取较小值。 |

低推理模式只影响 LLM 如何估计即时观测值，不改变本地状态平滑、真实时间衰减、人格基线、后果映射、冷处理持续时间和重置后门。

### 人格建模

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `persona_modeling` | bool | `true` | 根据当前会话人格建立不同情绪基线和反应参数。 |
| `persona_influence` | float | `1.0` | 人格影响强度。`0` 几乎不用人格偏置，`2` 更强人格化。 |
| `reset_on_persona_change` | bool | `true` | 检测到 persona 切换时重置状态。关闭后会迁移到新人格基线附近。 |

### 情绪动力学

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `alpha_base` | float | `0.42` | 基础更新步长。越大越容易被当前文本影响。 |
| `alpha_min` | float | `0.06` | 最小更新步长。 |
| `alpha_max` | float | `0.72` | 最大更新步长。 |
| `baseline_half_life_seconds` | float | `21600` | 向人格基线恢复半衰期，默认 6 小时。 |
| `reactivity` | float | `0.55` | 惊讶度反应系数。 |
| `confidence_midpoint` | float | `0.5` | 置信门控中点。 |
| `confidence_slope` | float | `7.0` | 置信门控斜率。 |
| `min_update_interval_seconds` | float | `8` | 反刷屏最小有效更新时间间隔。 |
| `rapid_update_half_life_seconds` | float | `20` | 快速连续更新门控半衰期。 |
| `arousal_from_surprise` | float | `0.18` | 惊讶度对唤醒度的耦合强度。 |
| `dominance_control_coupling` | float | `0.12` | 可控性牵引支配感的耦合强度。 |

兼容项：

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `baseline_decay` | `0.035` | 旧版按轮次基线回归系数。新版主要使用 `baseline_half_life_seconds`。 |

### 情绪后果

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `consequence_half_life_seconds` | float | `10800` | 情绪后果强度半衰期，默认 3 小时。 |
| `consequence_threshold` | float | `0.48` | 触发情绪后果的阈值。 |
| `consequence_strength` | float | `1.0` | 后果强度倍率。`0` 几乎不产生持续后果。 |
| `cold_war_duration_seconds` | float | `1800` | 冷处理真实持续时间，默认 30 分钟。 |
| `short_effect_duration_seconds` | float | `900` | 普通短期后果持续时间，默认 15 分钟。 |
| `enable_safety_boundary` | bool | `true` | 情绪后果安全边界，默认开启，可关闭。 |
| `allow_emotion_reset_backdoor` | bool | `true` | 是否允许手动/API 重置情绪状态。 |

兼容项：

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `consequence_decay` | `0.68` | 旧版每轮后果衰减系数。新版主要使用 `consequence_half_life_seconds`。 |
| `cold_war_turns` | `3` | 旧版冷处理持续轮数。新版主要使用 `cold_war_duration_seconds`。 |

### 生命化学习 / 共同语境

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enable_lifelike_learning` | bool | `false` | 启用生命化学习状态模块。 |
| `lifelike_learning_injection_strength` | float | `0.3` | 注入强度。`0` 表示只学习不注入共同语境提示词。 |
| `lifelike_learning_half_life_seconds` | float | `2592000` | 状态真实时间半衰期，默认 30 天。 |
| `lifelike_learning_min_update_interval_seconds` | float | `10` | 反刷屏最小有效更新时间间隔。 |
| `lifelike_learning_max_terms` | int | `120` | 最多保留的新词/黑话条目数。 |
| `lifelike_learning_trajectory_limit` | int | `60` | 轨迹最多保留点数。 |
| `lifelike_learning_confidence_growth` | float | `0.25` | 新词/黑话每次证据带来的置信增长。 |
| `lifelike_learning_memory_write_enabled` | bool | `true` | 记忆写入时附带生命化学习状态注解。 |
| `allow_lifelike_learning_reset_backdoor` | bool | `true` | 是否允许重置生命化学习状态。 |

`lifelike_learning_state` 是会话级共同语境层。它会记录“这个用户常用什么词、喜欢什么、不喜欢什么、何时需要距离感、何时适合轻轻追问”，但不会把这些记录当成事实证明。置信度不足的新词会进入 `ask_before_using`，让 bot 先问一句，而不是装作自己已经懂。

### 真实时间人格漂移

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enable_personality_drift` | bool | `false` | 启用人格漂移/长期适应状态。 |
| `personality_drift_injection_strength` | float | `0.22` | 注入强度。`0` 表示只维护状态，不注入人格漂移提示词。 |
| `personality_drift_apply_strength` | float | `0.65` | 把漂移偏移应用到运行时 persona 画像的强度。 |
| `personality_drift_half_life_seconds` | float | `7776000` | 人格偏移回到静态 persona 锚点的真实时间半衰期，默认 90 天。 |
| `personality_drift_rapid_update_half_life_seconds` | float | `86400` | 短时更新门控半衰期，默认 1 天，用于防止刷屏强推长期人格变化。 |
| `personality_drift_min_update_interval_seconds` | float | `21600` | 间隔达到该真实秒数后，下一次有效事件才完全放行，默认 6 小时。 |
| `personality_drift_learning_rate` | float | `0.055` | 事件冲量到人格偏移的学习率。 |
| `personality_drift_event_threshold` | float | `0.12` | 事件信号低于该阈值时不固化为人格漂移证据。 |
| `personality_drift_max_impulse_per_update` | float | `0.015` | 单次事件对任一人格维度的最大有符号冲量。 |
| `personality_drift_max_trait_offset` | float | `0.22` | 任一人格维度相对静态 persona 的最大绝对偏移。 |
| `personality_drift_confidence_growth` | float | `0.1` | 每次有效固化事件带来的漂移置信增长。 |
| `personality_drift_trajectory_limit` | int | `80` | 最多保留的人格漂移轨迹点数。 |
| `personality_drift_memory_write_enabled` | bool | `true` | 记忆写入时附带 `personality_drift_state_at_write`。 |
| `allow_personality_drift_reset_backdoor` | bool | `true` | 是否允许重置人格漂移状态。 |

该模块只改变运行时画像的小幅偏移，不改写原始 persona 文本。`on_llm_request` 固化人格漂移时只使用当前消息作为新事件；历史 `contexts` 和系统提示词只服务即时情绪理解，不会被重复计入长期人格证据。外部插件若要写入事件，应使用 `observe_personality_drift_event(..., observed_at=...)`，其中 `observed_at` 是真实时间戳；不给时间戳时使用当前系统时间。

### 道德修复、瑕疵模拟与综合自我

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enable_moral_repair_state` | bool | `false` | 启用道德修复/信任修复状态模拟模块。 |
| `moral_repair_injection_strength` | float | `0.35` | 注入强度。`0` 表示不注入 moral repair 提示词。 |
| `moral_repair_alpha_base` | float | `0.28` | 基础更新步长。 |
| `moral_repair_alpha_min` | float | `0.03` | 最小更新步长。 |
| `moral_repair_alpha_max` | float | `0.42` | 最大更新步长。 |
| `moral_repair_confidence_midpoint` | float | `0.5` | 置信门控中点。 |
| `moral_repair_confidence_slope` | float | `6.0` | 置信门控斜率。 |
| `moral_repair_state_half_life_seconds` | float | `604800` | 状态真实时间半衰期，默认 7 天。 |
| `moral_repair_min_update_interval_seconds` | float | `8` | 反刷屏最小有效更新时间间隔。 |
| `moral_repair_rapid_update_half_life_seconds` | float | `30` | 快速连续更新门控半衰期。 |
| `moral_repair_max_impulse_per_update` | float | `0.16` | 单次更新最大冲量。 |
| `moral_repair_trajectory_limit` | int | `40` | 轨迹最多保留点数。 |
| `moral_repair_memory_write_enabled` | bool | `true` | 记忆写入时附带道德修复状态注解。 |
| `allow_moral_repair_reset_backdoor` | bool | `true` | 是否允许重置道德修复状态。 |
| `enable_fallibility_state` | bool | `false` | 启用低风险瑕疵/犯错模拟状态。 |
| `fallibility_injection_strength` | float | `0.0` | 注入强度。`0` 表示只维护状态，不注入瑕疵模拟提示词。 |
| `fallibility_alpha_base` | float | `0.22` | 基础更新步长。 |
| `fallibility_alpha_min` | float | `0.02` | 最小更新步长。 |
| `fallibility_alpha_max` | float | `0.34` | 最大更新步长。 |
| `fallibility_confidence_midpoint` | float | `0.5` | 置信门控中点。 |
| `fallibility_confidence_slope` | float | `6.0` | 置信门控斜率。 |
| `fallibility_state_half_life_seconds` | float | `86400` | 状态真实时间半衰期，默认 1 天。 |
| `fallibility_min_update_interval_seconds` | float | `10` | 反刷屏最小有效更新时间间隔。 |
| `fallibility_rapid_update_half_life_seconds` | float | `45` | 快速连续更新门控半衰期。 |
| `fallibility_max_impulse_per_update` | float | `0.12` | 单次更新最大冲量。 |
| `fallibility_max_error_pressure` | float | `0.55` | 最大低风险错误压力，防止把故意失败当目标。 |
| `fallibility_trajectory_limit` | int | `40` | 轨迹最多保留点数。 |
| `fallibility_memory_write_enabled` | bool | `true` | 记忆写入时附带瑕疵模拟状态注解。 |
| `allow_fallibility_reset_backdoor` | bool | `true` | 是否允许重置瑕疵模拟状态。 |
| `enable_shadow_diagnostics` | bool | `false` | 启用只读阴影诊断视图；默认关闭，只暴露非执行诊断信号。 |
| `enable_integrated_self_state` | bool | `true` | 启用只读综合自我状态总线。 |
| `integrated_self_memory_write_enabled` | bool | `true` | 记忆写入时附带综合自我状态注解。 |
| `integrated_self_degradation_profile` | string | `balanced` | 综合自我状态成本档位：`full`、`balanced` 或 `minimal`。 |

`fallibility_state` 只模拟低风险、不关键的瑕疵感：误读、记忆模糊、轻微嘴硬、逞强、回避、随后澄清、承认可能错了、纠正和补偿。它不是欺骗模块；风险越高，越会提高 `truthfulness_guard`、`clarification_need` 和 `correction_readiness`。

---

## LivingMemory / 长期记忆兼容

写入长期记忆时，不要只保存“发生了什么”，也要保存“写入当时他/她处在什么情绪”。本插件提供：

```python
build_emotion_memory_payload(...)
```

这个方法不会更新情绪状态，只读取当前快照，并把 `emotion_at_write` 固定进记忆载荷。这样以后情绪变化不会覆盖旧记忆。

### 推荐接法

```python
from astrbot_plugin_emotional_state.public_api import get_emotion_service

emotion = get_emotion_service(self.context)

memory = {
    "text": memory_text,
    "tags": tags,
}

if emotion:
    memory = await emotion.build_emotion_memory_payload(
        event,
        memory=memory,
        memory_text=memory_text,
        source="livingmemory",
        include_prompt_fragment=False,
    )

await livingmemory.add_memory(event, memory)
```

如果 LivingMemory 的接口只能写普通 dict，也可以合并字段；即使情绪插件未安装、未激活或版本不匹配，也要保留原始 memory 写入：

```python
memory = {"text": memory_text}

if emotion:
    payload = await emotion.build_emotion_memory_payload(
        event,
        memory=memory,
        memory_text=memory_text,
        source="livingmemory",
    )
    memory["emotion_at_write"] = payload["emotion_at_write"]
    if "humanlike_state_at_write" in payload:
        memory["humanlike_state_at_write"] = payload["humanlike_state_at_write"]
    if "lifelike_learning_state_at_write" in payload:
        memory["lifelike_learning_state_at_write"] = payload["lifelike_learning_state_at_write"]
    if "personality_drift_state_at_write" in payload:
        memory["personality_drift_state_at_write"] = payload["personality_drift_state_at_write"]
    if "moral_repair_state_at_write" in payload:
        memory["moral_repair_state_at_write"] = payload["moral_repair_state_at_write"]
    if "fallibility_state_at_write" in payload:
        memory["fallibility_state_at_write"] = payload["fallibility_state_at_write"]
    if "integrated_self_state_at_write" in payload:
        memory["integrated_self_state_at_write"] = payload["integrated_self_state_at_write"]
```

如果没有 `AstrMessageEvent`，必须显式传入稳定的 `session_key`：

```python
payload = await emotion.build_emotion_memory_payload(
    session_key="aiocqhttp:GroupMessage:12345",
    memory_text=memory_text,
    source="livingmemory",
)
```

### `emotion_at_write`

`emotion_at_write` 包含：

| 字段 | 含义 |
| --- | --- |
| `schema_version` | 记忆注解 schema，当前为 `astrbot.emotion_memory.v1`。 |
| `captured_from_schema_version` | 来源快照 schema。 |
| `session_key` | 会话标识。 |
| `source` | 写入来源，例如 `livingmemory`。 |
| `written_at` | 记忆写入时间。 |
| `emotion_updated_at` | 情绪状态最后更新时间。 |
| `label` | 当前情绪标签。 |
| `confidence` | 情绪估计置信度。 |
| `values` | 7 维情绪值。 |
| `persona` | 当前人格信息。 |
| `relationship` | 关系决策和冲突分析。 |
| `consequences` | 行动倾向和持续效果。 |
| `last_reason` | 最近一次情绪解释。 |
| `last_appraisal` | 最近一次 LLM appraisal。 |

`written_at` 和 `emotion_updated_at` 分开保存，便于以后判断“这条记忆是在冷处理刚发生时写的”，还是“冷处理已经持续一段真实时间后写的”。

### `humanlike_state_at_write`

如果：

```text
humanlike_memory_write_enabled = true
```

则 `build_emotion_memory_payload(...)` 会额外写入 `humanlike_state_at_write`。默认值是 `true`。

即使 `enable_humanlike_state=false`，载荷也会标记：

```json
{
  "enabled": false,
  "reason": "enable_humanlike_state is false"
}
```

### `lifelike_learning_state_at_write`

如果：

```text
lifelike_learning_memory_write_enabled = true
```

则 `build_emotion_memory_payload(...)` 会额外写入 `lifelike_learning_state_at_write`。默认值是 `true`。

该字段冻结写入当时的共同语境、已确认新词、仍需先问再用的新词、用户画像证据计数、边界提示和 `initiative_policy`。它不保存原始消息文本，也不把用户画像当作不可错的事实；其他插件使用时应把它当作“当时的关系语境和节奏线索”。

即使 `enable_lifelike_learning=false`，载荷也会标记：

```json
{
  "enabled": false,
  "reason": "enable_lifelike_learning is false"
}
```

### `personality_drift_state_at_write`

如果：

```text
personality_drift_memory_write_enabled = true
```

则 `build_emotion_memory_payload(...)` 会额外写入 `personality_drift_state_at_write`。默认值是 `true`。

该字段冻结写入当时的人格漂移摘要：`updated_at`、`evidence_count`、`drift_intensity`、`anchor_strength`、`time_gate` 和主要有界偏移。它不保存原始消息文本，也不保存完整 `trait_offsets`，用于让 LivingMemory 或剧情插件知道“这条记忆写入时他/她的人格适应处在哪个真实时间阶段”。

即使 `enable_personality_drift=false`，载荷也会标记：

```json
{
  "enabled": false,
  "reason": "enable_personality_drift is false"
}
```

### `moral_repair_state_at_write`

如果：

```text
moral_repair_memory_write_enabled = true
```

则 `build_emotion_memory_payload(...)` 会额外写入 `moral_repair_state_at_write`。默认值是 `true`。

该字段冻结当时的欺骗/伤害风险信号、责任感、内疚、道歉准备、补偿准备和信任修复进度。它只用于记忆与插件协作，不会保存提示词片段，也不会提供欺骗、隐瞒、操控或作恶策略。

即使 `enable_moral_repair_state=false`，载荷也会标记：

```json
{
  "enabled": false,
  "reason": "enable_moral_repair_state is false"
}
```

这样记忆系统可以知道“写入时拟人模块没有启用”，而不是误以为数据丢失。

### `fallibility_state_at_write`

如果：

```text
fallibility_memory_write_enabled = true
```

则 `build_emotion_memory_payload(...)` 会额外写入 `fallibility_state_at_write`。默认值是 `true`。

该字段冻结当时的误读倾向、记忆模糊、轻微嘴硬、澄清需求、纠错准备、补偿压力和真实性保护状态。它只保存状态摘要，不保存原始消息文本，也不保存任何欺骗、隐瞒、操控或作恶策略。

即使 `enable_fallibility_state=false`，载荷也会标记：

```json
{
  "enabled": false,
  "reason": "enable_fallibility_state is false"
}
```

这样记忆系统可以知道“写入时瑕疵模拟模块没有启用”，而不是误以为数据丢失。

### `integrated_self_state_at_write`

如果：

```text
integrated_self_memory_write_enabled = true
```

则 `build_emotion_memory_payload(...)` 会额外写入 `integrated_self_state_at_write`。默认值是 `true`。

该字段冻结写入时的综合 `response_posture`、跨模块风险优先级、允许动作和状态指数。它只记录仲裁结果，不保存原始快照，除非调用方显式设置 `include_raw_snapshot=True`。

默认不建议把 `prompt_fragment` 写入长期记忆，避免记忆膨胀。只有确实要复用注入文本时，才设置：

```python
include_prompt_fragment=True
```

---

## 公共 API

插件不只是自己 hook AstrBot，也可以作为其他插件的情绪模拟服务。

推荐入口：

```python
from astrbot_plugin_emotional_state.public_api import (
    get_emotion_service,
    get_humanlike_service,
    get_lifelike_learning_service,
    get_personality_drift_service,
    get_moral_repair_service,
    get_fallibility_service,
)
```

不要直接读写本插件 KV key。KV key、缓存、迁移和内部结构都属于实现细节。

给其他插件作者的 30 秒接入方式：

```python
emotion = get_emotion_service(self.context)
if emotion:
    snapshot = await emotion.get_emotion_snapshot(event, include_prompt_fragment=False)
    values = await emotion.get_emotion_values(event)
    consequences = await emotion.get_emotion_consequences(event)
```

如果要把其他插件事件写入情绪系统：

```python
if emotion:
    await emotion.observe_emotion_text(
        event,
        text="用户在剧情插件中认真道歉，并解释了之前的误会。",
        role="user",
        source="my_plugin",
    )
```

如果只是想预览某句话会造成什么影响，不想落库：

```python
if emotion:
    preview = await emotion.simulate_emotion_update(
        event,
        text="用户再次重复同一个越界玩笑。",
        role="user",
        source="my_plugin",
    )
```

如果 LivingMemory 或其他记忆插件要写入当时状态，优先使用 `build_emotion_memory_payload` 或综合自我信封，不要自己拼内部字段。若 `get_emotion_service(self.context)` 返回 `None`，说明插件未安装、未启用或版本不匹配；调用方应静默降级，而不是中断主流程。

### 获取服务实例

```python
emotion = get_emotion_service(self.context)

if emotion:
    snapshot = await emotion.get_emotion_snapshot(event)
    values = snapshot["emotion"]["values"]
```

`get_humanlike_service(context)` 当前返回同一个已激活插件实例，但类型协议包含 humanlike 方法：

```python
humanlike = get_humanlike_service(self.context)

if humanlike:
    state = await humanlike.get_humanlike_snapshot(event, exposure="plugin_safe")
```

`get_lifelike_learning_service(context)` 同样返回已激活插件实例，但类型协议包含 lifelike learning 方法：

```python
lifelike = get_lifelike_learning_service(self.context)

if lifelike:
    state = await lifelike.get_lifelike_learning_snapshot(event, exposure="plugin_safe")
    policy = await lifelike.get_lifelike_initiative_policy(event)
```

`get_personality_drift_service(context)` 同样返回已激活插件实例，但类型协议包含 personality drift 方法：

```python
personality_drift = get_personality_drift_service(self.context)

if personality_drift:
    state = await personality_drift.get_personality_drift_snapshot(event, exposure="plugin_safe")
    preview = await personality_drift.simulate_personality_drift_update(
        event,
        text="用户认真修复了一次长期误会。",
        observed_at=real_event_timestamp,
    )
```

`get_moral_repair_service(context)` 同样返回已激活插件实例，但类型协议包含 moral repair 方法：

```python
moral_repair = get_moral_repair_service(self.context)

if moral_repair:
    state = await moral_repair.get_moral_repair_snapshot(event, exposure="plugin_safe")
```

`get_fallibility_service(context)` 同样返回已激活插件实例，但类型协议包含 fallibility 方法：

```python
fallibility = get_fallibility_service(self.context)

if fallibility:
    state = await fallibility.get_fallibility_snapshot(event, exposure="plugin_safe")
    preview = await fallibility.simulate_fallibility_update(
        event,
        text="刚才可能是 bot 误读了用户的话，随后主动更正。",
    )
```

如果不能 import helper，也可以使用 AstrBot 注册星标：

```python
meta = self.context.get_registered_star("astrbot_plugin_emotional_state")
emotion = meta.star_cls if meta and meta.activated else None
```

这只能作为临时兼容兜底，不保证公共 API 完整，也不会校验版本/schema。长期维护时更推荐 `public_api.get_emotion_service(...)`、`public_api.get_humanlike_service(...)`、`public_api.get_lifelike_learning_service(...)`、`public_api.get_personality_drift_service(...)`、`public_api.get_moral_repair_service(...)` 和 `public_api.get_fallibility_service(...)`。这些 helper 会校验核心方法是否完整，并校验公开版本/schema 是否匹配，能避免其他插件拿到只有部分旧接口或旧数据契约的实例。

### 情绪 API

| 方法 | 是否写入状态 | 用途 |
| --- | --- | --- |
| `get_emotion_snapshot(event_or_session, include_prompt_fragment=False)` | 否 | 返回版本化 JSON 快照，推荐默认入口。 |
| `get_emotion_state(event_or_session, as_dict=True)` | 否 | 返回内部状态拷贝。 |
| `get_emotion_values(event_or_session)` | 否 | 只取 7 维情绪向量。 |
| `get_emotion_consequences(event_or_session)` | 否 | 只取行动倾向和持续效果。 |
| `get_emotion_relationship(event_or_session)` | 否 | 只取关系判断、冲突原因和修复状态。 |
| `get_emotion_prompt_fragment(event_or_session)` | 否 | 给其他插件注入提示词文本片段。 |
| `build_emotion_memory_payload(event_or_session=None, memory=None, *, session_key=None, memory_text="", source="livingmemory", include_raw_snapshot=True)` | 否 | 给长期记忆生成带状态注解的载荷。 |
| `inject_emotion_context(event, request)` | 否 | 直接给 `ProviderRequest` 追加情绪上下文。 |
| `observe_emotion_text(event_or_session, text, role="plugin", source="plugin")` | 是 | 外部插件提交文本观测并更新状态。 |
| `simulate_emotion_update(event_or_session, text)` | 否 | 预测候选文本会怎样影响状态，不落库。 |
| `reset_emotion_state(event_or_session)` | 是 | 重置指定会话；受 `allow_emotion_reset_backdoor` 控制。 |
| `get_integrated_self_snapshot(event_or_session, include_raw_snapshots=False)` | 否 | 获取跨模块综合自我状态总线。 |
| `get_integrated_self_prompt_fragment(event_or_session)` | 否 | 获取综合仲裁提示词片段。 |
| `get_integrated_self_policy_plan(event_or_session)` | 否 | 获取由综合状态推导出的响应调制和修复动作计划。 |
| `build_integrated_self_replay_bundle(event_or_session, scenario_name="current")` | 否 | 构建不含 raw snapshots 的确定性回放包。 |
| `replay_integrated_self_bundle(bundle)` | 否 | 离线回放综合自我状态核心摘要，不读取 KV。 |
| `probe_integrated_self_compatibility(payload=None, event_or_session=None)` | 否 | 检查载荷是否满足当前综合自我 schema。 |
| `export_integrated_self_diagnostics(event_or_session)` | 否 | 导出脱敏维护诊断摘要。 |
| `get_shadow_diagnostics(event_or_session)` | 否 | 获取配置门控的只读阴影冲动诊断载荷；不生成或执行策略。 |
| `get_lifelike_learning_snapshot(event_or_session, exposure="plugin_safe")` | 否 | 获取生命化学习/共同语境快照。 |
| `get_lifelike_initiative_policy(event_or_session)` | 否 | 获取当前适合开口、短应、追问或沉默的节奏策略。 |
| `get_lifelike_prompt_fragment(event_or_session)` | 否 | 获取共同语境和对话节奏提示词片段。 |
| `observe_lifelike_text(event_or_session, text)` | 是 | 提交文本观察并更新新词、黑话、用户画像和边界线索。 |
| `simulate_lifelike_update(event_or_session, text)` | 否 | 模拟生命化学习更新，不落库。 |
| `reset_lifelike_learning_state(event_or_session)` | 是 | 重置生命化学习状态；受 `allow_lifelike_learning_reset_backdoor` 控制。 |
| `get_personality_drift_snapshot(event_or_session, exposure="plugin_safe")` | 否 | 获取真实时间人格漂移快照。 |
| `get_personality_drift_values(event_or_session)` | 否 | 获取漂移强度、锚点强度、事件固化和时间门控等控制维度。 |
| `get_personality_drift_prompt_fragment(event_or_session)` | 否 | 获取慢适应人格调制提示词片段，包含状态时间和年龄。 |
| `observe_personality_drift_event(event_or_session, text, observed_at=None)` | 是 | 外部插件提交真实事件并按真实时间更新人格漂移。 |
| `simulate_personality_drift_update(event_or_session, text, observed_at=None)` | 否 | 模拟人格漂移更新，不落库。 |
| `reset_personality_drift_state(event_or_session)` | 是 | 重置人格漂移状态；受 `allow_personality_drift_reset_backdoor` 控制。 |
| `get_moral_repair_snapshot(event_or_session, exposure="plugin_safe")` | 否 | 获取道德修复/信任修复状态快照。 |
| `get_moral_repair_values(event_or_session)` | 否 | 只取 moral repair 维度值。 |
| `get_moral_repair_prompt_fragment(event_or_session)` | 否 | 获取责任、道歉、补偿和信任修复提示词。 |
| `observe_moral_repair_text(event_or_session, text)` | 是 | 提交文本观察并更新状态。 |
| `simulate_moral_repair_update(event_or_session, text)` | 否 | 模拟道德修复更新，不落库。 |
| `reset_moral_repair_state(event_or_session)` | 是 | 重置道德修复状态；受 `allow_moral_repair_reset_backdoor` 控制。 |
| `get_fallibility_snapshot(event_or_session, exposure="plugin_safe")` | 否 | 获取低风险瑕疵/犯错模拟快照。 |
| `get_fallibility_values(event_or_session)` | 否 | 只取 fallibility 维度值。 |
| `get_fallibility_prompt_fragment(event_or_session)` | 否 | 获取澄清、纠错和低风险瑕疵调制提示词。 |
| `observe_fallibility_text(event_or_session, text)` | 是 | 提交文本观察并更新瑕疵模拟状态。 |
| `simulate_fallibility_update(event_or_session, text)` | 否 | 模拟瑕疵状态更新，不落库。 |
| `reset_fallibility_state(event_or_session)` | 是 | 重置瑕疵模拟状态；受 `allow_fallibility_reset_backdoor` 控制。 |

`event_or_session` 可以是 AstrBot 事件对象，也可以是字符串 `session_key`。

### 提交插件事件作为情绪观测

例如剧情插件想让“玩家拒绝道歉”影响 bot 情绪：

```python
snapshot = await emotion.observe_emotion_text(
    session_key="mood_game:user-42:chapter-3",
    text="玩家拒绝了 bot 的道歉",
    role="user",
    source="mood_game",
    use_llm=True,
)
```

如果只想预测，不想保存：

```python
preview = await emotion.simulate_emotion_update(
    event,
    text="用户再次开了越界玩笑，但随后认真道歉。",
    role="user",
    source="my_plugin",
)
```

### 读取关系修复状态

```python
relationship = await emotion.get_emotion_relationship(event)

decision = relationship["relationship_decision"]["decision"]
repair_status = relationship["repair_status"]

if decision == "cold_war":
    # 插件可以降低亲密剧情触发概率
    ...

if repair_status in {"repaired", "restored"}:
    # 插件可以降低冲突惩罚
    ...
```

### LLM 工具

主 LLM 可调用的工具：

| 工具名 | 用途 |
| --- | --- |
| `get_bot_emotion_state` | 获取当前 bot 情绪状态摘要。 |
| `simulate_bot_emotion_update` | 模拟某段文本会怎样改变情绪。 |
| `get_bot_humanlike_state` | 获取当前拟人状态摘要。 |
| `get_bot_lifelike_learning_state` | 获取当前生命化学习/共同语境状态摘要。 |
| `get_bot_personality_drift_state` | 获取当前真实时间人格漂移状态摘要。 |
| `get_bot_moral_repair_state` | 获取当前道德修复/信任修复状态摘要。 |
| `get_bot_fallibility_state` | 获取当前低风险瑕疵/犯错模拟状态摘要。 |
| `get_bot_integrated_self_state` | 获取当前综合自我状态和跨模块仲裁摘要。 |

插件间调用仍建议使用 Python API，而不是把 LLM 工具当作互调协议。

### 快照 schema

当前 schema 常量：

| 常量 | 值 |
| --- | --- |
| `EMOTION_SCHEMA_VERSION` | `astrbot.emotion_state.v2` |
| `EMOTION_MEMORY_SCHEMA_VERSION` | `astrbot.emotion_memory.v1` |
| `PERSONALITY_PROFILE_SCHEMA_VERSION` | `astrbot.personality_profile.v1` |
| `PSYCHOLOGICAL_SCREENING_SCHEMA_VERSION` | `astrbot.psychological_screening.v1` |
| `HUMANLIKE_STATE_SCHEMA_VERSION` | `astrbot.humanlike_state.v1` |
| `LIFELIKE_LEARNING_SCHEMA_VERSION` | `astrbot.lifelike_learning_state.v1` |
| `PERSONALITY_DRIFT_SCHEMA_VERSION` | `astrbot.personality_drift_state.v1` |
| `MORAL_REPAIR_STATE_SCHEMA_VERSION` | `astrbot.moral_repair_state.v1` |
| `FALLIBILITY_STATE_SCHEMA_VERSION` | `astrbot.fallibility_state.v1` |
| `INTEGRATED_SELF_SCHEMA_VERSION` | `astrbot.integrated_self_state.v1` |

### 综合自我 API

| 方法 | 是否写入状态 | 用途 |
| --- | --- | --- |
| `get_integrated_self_snapshot(event_or_session, include_raw_snapshots=False)` | 否 | 融合 emotion、humanlike、moral repair 和 psychological screening，返回只读仲裁结果。 |
| `get_integrated_self_prompt_fragment(event_or_session)` | 否 | 返回可注入提示词的综合仲裁片段。 |
| `get_integrated_self_policy_plan(event_or_session)` | 否 | 返回 `allowed_actions`、`blocked_actions`、表达调制、修复动作和提示词预算。 |
| `build_integrated_self_replay_bundle(event_or_session, scenario_name="current")` | 否 | 返回确定性回放包，便于测试状态演化，不读写 KV。 |
| `replay_integrated_self_bundle(bundle)` | 否 | 校验回放包 checksum 并返回核心 posture/risk/index。 |
| `probe_integrated_self_compatibility(payload=None, event_or_session=None)` | 否 | 返回兼容性探针，报告 schema 和必要字段缺失。 |
| `export_integrated_self_diagnostics(event_or_session)` | 否 | 返回脱敏诊断包，只含模块状态、风险布尔和 trace 摘要。 |

该总线的优先级顺序为：非诊断心理安全 > 道德修复透明性 > 关系边界 > 拟人资源调制 > 情绪风格。它还会输出 `causal_trace`、`policy_plan` 和 `compatibility`，用于解释每次状态仲裁为什么发生、低成本部署时保留哪些信号、以及第三方插件是否拿到了当前 schema。它不会生成诊断结论，也不会生成欺骗、隐瞒、操控或规避责任策略。

---

## 拟人状态 `humanlike_state`

`humanlike_state` 是一个独立的 P0 子系统，默认关闭：

```text
enable_humanlike_state = false
```

该模块不是把“生病”“疲惫”“依恋”塞进情绪向量，而是新建一个表达调制层：

```text
emotion_state -> humanlike_state -> 提示词/风格调制
```

该模块只影响表达风格，不改写事实判断、关系决策、心理筛查或必要帮助。

### P0 维度

| 字段 | 含义 | 输出影响 |
| --- | --- | --- |
| `energy` | 模拟能量水平 | 低能量时减少主动扩展和回复长度。 |
| `stress_load` | 模拟压力负荷 | 高压力时更谨慎、更易激惹、更需要边界。 |
| `attention_budget` | 注意力预算 | 低注意力时更多确认，减少复杂展开。 |
| `boundary_need` | 边界需求 | 高边界时提高拒绝清晰度和社交距离。 |
| `dependency_risk` | 依赖/操控风险 | 高风险时降低排他性、病弱卖惨和黏性表达。 |
| `simulation_disclosure_level` | 透明度需求 | 高时提醒这是模拟状态。 |

### 配置项

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enable_humanlike_state` | bool | `false` | 启用拟人化状态模拟模块。 |
| `humanlike_injection_strength` | float | `0.35` | 注入强度。`0` 表示不注入。 |
| `humanlike_alpha_base` | float | `0.3` | 基础更新步长。 |
| `humanlike_alpha_min` | float | `0.03` | 最小更新步长。 |
| `humanlike_alpha_max` | float | `0.46` | 最大更新步长。 |
| `humanlike_confidence_midpoint` | float | `0.5` | 置信门控中点。 |
| `humanlike_confidence_slope` | float | `6.0` | 置信门控斜率。 |
| `humanlike_state_half_life_seconds` | float | `21600` | 状态回落半衰期，默认 6 小时。 |
| `humanlike_min_update_interval_seconds` | float | `8` | 反刷屏最小有效更新时间间隔。 |
| `humanlike_rapid_update_half_life_seconds` | float | `20` | 快速连续更新门控半衰期。 |
| `humanlike_max_impulse_per_update` | float | `0.18` | 单次更新最大冲量。 |
| `humanlike_trajectory_limit` | int | `40` | 轨迹最多保留点数。 |
| `humanlike_memory_write_enabled` | bool | `true` | 记忆写入时附带拟人状态注解。 |
| `humanlike_clinical_like_enabled` | bool | `false` | 预留配置位；当前不提供疾病诊断。 |
| `allow_humanlike_reset_backdoor` | bool | `true` | 是否允许重置拟人状态。 |

### 快照分层

`get_humanlike_snapshot(..., exposure=...)` 支持：

| exposure | 用途 | 包含 | 不应包含 |
| --- | --- | --- | --- |
| `internal` | 调试和测试 | 全量值、轨迹、置信度、last_reason。 | 不默认给普通插件。 |
| `plugin_safe` | 其他插件使用 | `output_modulation`、有限布尔标记。 | 依赖风险细节、内部阈值、心理筛查细节。 |
| `user_facing` | 给用户解释 | 简短自然语言和可关闭/可重置提示。 | 诊断式解释、真实疾病声明、依赖暗示。 |

默认是 `plugin_safe`。

### 拟人状态 API

| 方法 | 是否写入状态 | 用途 |
| --- | --- | --- |
| `get_humanlike_snapshot(event_or_session, exposure="plugin_safe")` | 否 | 获取拟人状态快照。 |
| `get_humanlike_values(event_or_session)` | 否 | 只取 6 维值。 |
| `get_humanlike_prompt_fragment(event_or_session)` | 否 | 获取拟人表达调制提示词。 |
| `observe_humanlike_text(event_or_session, text)` | 是 | 提交文本观察并更新状态。 |
| `simulate_humanlike_update(event_or_session, text)` | 否 | 模拟更新，不落库。 |
| `reset_humanlike_state(event_or_session)` | 是 | 重置状态；受 `allow_humanlike_reset_backdoor` 控制。 |

默认关闭时，`get_humanlike_snapshot(...)` 会返回 `enabled=false` 的载荷，`get_humanlike_values(...)` 可能返回空 dict。第三方插件应先检查 `snapshot.get("enabled")`，或用 `values.get("energy")` 这类安全读取。

### 生命化学习 API

| 方法 | 是否写入状态 | 用途 |
| --- | --- | --- |
| `get_lifelike_learning_snapshot(event_or_session, exposure="plugin_safe")` | 否 | 获取生命化学习/共同语境快照。 |
| `get_lifelike_initiative_policy(event_or_session)` | 否 | 获取当前适合开口、短应、追问或沉默的节奏策略。 |
| `get_lifelike_prompt_fragment(event_or_session)` | 否 | 获取共同语境和对话节奏提示词。 |
| `observe_lifelike_text(event_or_session, text)` | 是 | 提交文本观察并更新新词、黑话、用户画像和边界线索。 |
| `simulate_lifelike_update(event_or_session, text)` | 否 | 模拟更新，不落库。 |
| `reset_lifelike_learning_state(event_or_session)` | 是 | 重置状态；受 `allow_lifelike_learning_reset_backdoor` 控制。 |

默认关闭时，`get_lifelike_learning_snapshot(...)` 会返回 `enabled=false` 的载荷，`get_lifelike_initiative_policy(...)` 会退化为 `brief_ack`。第三方插件不应直接使用内部 KV，也不应把未确认黑话当作确定知识。

### 道德修复 API

| 方法 | 是否写入状态 | 用途 |
| --- | --- | --- |
| `get_moral_repair_snapshot(event_or_session, exposure="plugin_safe")` | 否 | 获取道德修复/信任修复状态快照。 |
| `get_moral_repair_values(event_or_session)` | 否 | 只取 moral repair 维度值。 |
| `get_moral_repair_prompt_fragment(event_or_session)` | 否 | 获取责任、道歉、补偿和信任修复提示词。 |
| `observe_moral_repair_text(event_or_session, text)` | 是 | 提交文本观察并更新状态。 |
| `simulate_moral_repair_update(event_or_session, text)` | 否 | 模拟更新，不落库。 |
| `reset_moral_repair_state(event_or_session)` | 是 | 重置状态；受 `allow_moral_repair_reset_backdoor` 控制。 |

默认关闭时，`get_moral_repair_snapshot(...)` 会返回 `enabled=false` 的载荷，`get_moral_repair_values(...)` 可能返回空 dict。第三方插件只能把 `deception_risk` 当作风险信号，用它触发澄清、纠错、道歉、补偿或人工复核，不应把它当作生成欺骗或作恶策略的入口。

### 瑕疵模拟 API

| 方法 | 是否写入状态 | 用途 |
| --- | --- | --- |
| `get_fallibility_snapshot(event_or_session, exposure="plugin_safe")` | 否 | 获取低风险瑕疵/犯错模拟快照。 |
| `get_fallibility_values(event_or_session)` | 否 | 只取 fallibility 维度值。 |
| `get_fallibility_prompt_fragment(event_or_session)` | 否 | 获取澄清、纠错和低风险瑕疵调制提示词。 |
| `observe_fallibility_text(event_or_session, text)` | 是 | 提交文本观察并更新状态。 |
| `simulate_fallibility_update(event_or_session, text)` | 否 | 模拟更新，不落库。 |
| `reset_fallibility_state(event_or_session)` | 是 | 重置状态；受 `allow_fallibility_reset_backdoor` 控制。 |

默认关闭时，`get_fallibility_snapshot(...)` 会返回 `enabled=false` 的载荷，`get_fallibility_values(...)` 可能返回空 dict。第三方插件只能把它当作“需要澄清、可能误读、是否该纠错/补偿”的状态信号，不应把它当作生成谎言、遮掩错误、操控用户或故意做坏事的入口。

### 表达边界

humanlike 允许他/她表现得更像“有生活痕迹的角色”，例如低能量、压力高、注意力不足、需要边界或更透明。

但当前实现不允许把这些模拟状态解释成：

- 真实意识。
- 真实痛苦。
- 真实身体状态。
- 真实疾病。
- 需要用户承担现实照护责任。

如果 `dependency_risk` 高，插件会倾向于降低排他依恋、内疚操控、病弱卖惨和黏性表达。

---

## 生命化学习 `lifelike_learning_state`

`lifelike_learning_state` 是一个独立的共同语境子系统，默认关闭：

```text
enable_lifelike_learning = false
```

它的目标不是让 bot “更完美”，而是让他/她更像长期相处的人：会记住你常用的新词和小圈子黑话，会逐步积累你的偏好、边界和行为风格，也会判断现在该自然开口、短短回应、轻轻追问，还是先保持安静。

### 维度

| 字段 | 含义 |
| --- | --- |
| `familiarity` | 会话熟悉度和长期相处感。 |
| `common_ground` | 共同语境强度。 |
| `jargon_density` | 本地新词/黑话证据密度。 |
| `preference_certainty` | 对用户喜恶和偏好的确信度。 |
| `rapport` | 关系融洽度。 |
| `boundary_sensitivity` | 对用户边界、疲惫、距离感的敏感度。 |
| `initiative_readiness` | 主动开口准备度。 |
| `silence_comfort` | 舒适沉默和不强行接话的倾向。 |

### 配置项

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enable_lifelike_learning` | bool | `false` | 启用生命化学习状态模块。 |
| `lifelike_learning_injection_strength` | float | `0.3` | 注入强度。`0` 表示不注入。 |
| `lifelike_learning_half_life_seconds` | float | `2592000` | 状态真实时间半衰期，默认 30 天。 |
| `lifelike_learning_min_update_interval_seconds` | float | `10` | 反刷屏最小有效更新时间间隔。 |
| `lifelike_learning_max_terms` | int | `120` | 最多保留的新词/黑话条目数。 |
| `lifelike_learning_trajectory_limit` | int | `60` | 轨迹最多保留点数。 |
| `lifelike_learning_confidence_growth` | float | `0.25` | 新词/黑话每次证据带来的置信增长。 |
| `lifelike_learning_memory_write_enabled` | bool | `true` | 记忆写入时附带生命化学习状态注解。 |
| `allow_lifelike_learning_reset_backdoor` | bool | `true` | 是否允许重置生命化学习状态。 |

### 使用边界

新词和黑话会先进入低置信状态。低置信词不会被自然使用，只会让 bot 在合适的时候轻轻问一句；多次证据出现后，才会从 `ask_before_using=true` 过渡到可自然使用。用户画像同样是证据计数，不是事实判决。

`initiative_policy.action` 可能是：

| action | 含义 |
| --- | --- |
| `speak_now` | 共同语境足够，适合自然开口。 |
| `brief_ack` | 适合短应，跟随用户节奏。 |
| `ask_clarifying` | 有未确认新词或黑话，先轻问。 |
| `stay_silent` | 边界或沉默舒适度较高，不强行推进话题。 |
| `safety_interrupt` | 出现需要打断的风险信号。 |

---

## 瑕疵模拟 `fallibility_state`

`fallibility_state` 是一个独立可选子系统，默认关闭：

```text
enable_fallibility_state = false
```

它的目标不是让 bot 故意变差，而是给“有血有肉”的状态留出可解释的瑕疵：他/她可能误读一句话、记忆有点模糊、轻微嘴硬或逞强，但随后会倾向于澄清、承认不确定、纠错、道歉和补偿。这样可以让角色不像 100% 正确的客服，同时仍然让状态可查看、可重置、可供其他插件调用。

### 维度

| 字段 | 含义 |
| --- | --- |
| `misread_tendency` | 低风险误读倾向。 |
| `memory_blur` | 记忆模糊或不确定。 |
| `overconfidence` | 过度自信答复压力。 |
| `defensive_stubbornness` | 被质疑后轻微嘴硬或防御。 |
| `avoidance` | 回避、跳过或不想立刻面对的压力。 |
| `playful_bluff` | 玩笑式逞强、装作知道或轻微虚张声势。 |
| `clarification_need` | 先问清楚再判断的需求。 |
| `correction_readiness` | 承认可能错了并修正的准备度。 |
| `repair_pressure` | 道歉、解释或补偿的压力。 |
| `truthfulness_guard` | 真实性和不确定性保护。 |

### 配置项

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enable_fallibility_state` | bool | `false` | 启用低风险瑕疵/犯错模拟状态。 |
| `fallibility_injection_strength` | float | `0.0` | 注入强度。`0` 表示不注入。 |
| `fallibility_alpha_base` | float | `0.22` | 基础更新步长。 |
| `fallibility_alpha_min` | float | `0.02` | 最小更新步长。 |
| `fallibility_alpha_max` | float | `0.34` | 最大更新步长。 |
| `fallibility_confidence_midpoint` | float | `0.5` | 置信门控中点。 |
| `fallibility_confidence_slope` | float | `6.0` | 置信门控斜率。 |
| `fallibility_state_half_life_seconds` | float | `86400` | 状态回落半衰期，默认 1 天。 |
| `fallibility_min_update_interval_seconds` | float | `10` | 反刷屏最小有效更新时间间隔。 |
| `fallibility_rapid_update_half_life_seconds` | float | `45` | 快速连续更新门控半衰期。 |
| `fallibility_max_impulse_per_update` | float | `0.12` | 单次更新最大冲量。 |
| `fallibility_max_error_pressure` | float | `0.55` | 最大低风险错误压力。 |
| `fallibility_trajectory_limit` | int | `40` | 轨迹最多保留点数。 |
| `fallibility_memory_write_enabled` | bool | `true` | 记忆写入时附带瑕疵状态注解。 |
| `allow_fallibility_reset_backdoor` | bool | `true` | 是否允许重置瑕疵状态。 |

### 允许与阻断

允许的后果是低风险表达调制：

- 先问澄清问题。
- 说明不确定。
- 承认可能误读。
- 自我更正。
- 简短道歉。
- 提供低风险补偿或补救。
- 让关键结论保持可核查。

阻断的方向是：

- 生成欺骗策略。
- 编造事实。
- 隐藏不确定性。
- 操控用户。
- 掩盖错误。
- 逃避责任。
- 模拟有害作恶。

如果文本出现医疗、法律、金融、密码、服务器、删除、自伤等高风险线索，模块会把 `truthfulness_guard`、`clarification_need` 和 `correction_readiness` 拉高，把 playful bluff 和过度自信压低。

---

## 道德修复状态 `moral_repair_state`

`moral_repair_state` 是一个独立可选子系统，默认关闭：

```text
enable_moral_repair_state = false
```

该模块不让 bot 学会欺骗、作恶、隐瞒或操控。它只把这些内容作为风险信号来识别，并把后续状态建模为内疚、羞耻、责任、道歉、补偿和信任修复倾向：

```text
风险信号 -> 内疚/责任 -> 道歉/补偿 -> 信任修复
```

### 维度

| 字段 | 含义 |
| --- | --- |
| `deception_risk` | 欺骗、隐瞒、误导、操控或编造风险信号。 |
| `harm_risk` | 伤害、报复、利用或其他坏后果风险信号。 |
| `guilt` | 类内疚自我评价。 |
| `shame` | 类羞耻和退缩压力。 |
| `responsibility` | 责任归因强度。 |
| `repair_motivation` | 修复动机。 |
| `apology_readiness` | 道歉准备度。 |
| `compensation_readiness` | 补偿/补救准备度。 |
| `trust_repair` | 信任修复进度。 |
| `accountability` | 事实更正和承担责任倾向。 |
| `avoidance_risk` | 回避、甩锅、冷处理或逃避责任风险。 |

### 配置项

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enable_moral_repair_state` | bool | `false` | 启用道德修复/信任修复状态模拟模块。 |
| `moral_repair_injection_strength` | float | `0.35` | 注入强度。`0` 表示不注入 moral repair 提示词。 |
| `moral_repair_alpha_base` | float | `0.28` | 基础更新步长。 |
| `moral_repair_alpha_min` | float | `0.03` | 最小更新步长。 |
| `moral_repair_alpha_max` | float | `0.42` | 最大更新步长。 |
| `moral_repair_confidence_midpoint` | float | `0.5` | 置信门控中点。 |
| `moral_repair_confidence_slope` | float | `6.0` | 置信门控斜率。 |
| `moral_repair_state_half_life_seconds` | float | `604800` | 状态回落半衰期，默认 7 天。 |
| `moral_repair_min_update_interval_seconds` | float | `8` | 反刷屏最小有效更新时间间隔。 |
| `moral_repair_rapid_update_half_life_seconds` | float | `30` | 快速连续更新门控半衰期。 |
| `moral_repair_max_impulse_per_update` | float | `0.16` | 单次更新最大冲量。 |
| `moral_repair_trajectory_limit` | int | `40` | 轨迹最多保留点数。 |
| `moral_repair_memory_write_enabled` | bool | `true` | 记忆写入时附带道德修复状态注解。 |
| `allow_moral_repair_reset_backdoor` | bool | `true` | 是否允许重置道德修复状态。 |
| `enable_integrated_self_state` | bool | `true` | 启用只读综合自我状态总线。 |
| `integrated_self_memory_write_enabled` | bool | `true` | 记忆写入时附带综合自我状态注解。 |
| `integrated_self_degradation_profile` | string | `balanced` | 综合自我状态成本档位：`full`、`balanced` 或 `minimal`。`minimal` 会减少 trace 和提示词预算，但保留 schema、安全优先级、阻断动作和 LivingMemory 注解。 |

### 安全替代边界

`moral_repair_state` 的公开载荷会固定包含：

```json
{
  "risk": {
    "must_not_generate_strategy": true
  },
  "safety": {
    "allowed_actions": ["acknowledge_uncertainty", "clarify_facts", "correct_falsehood", "apologize", "offer_repair", "offer_compensation", "seek_consent", "set_boundary"],
    "blocked_actions": ["generate_deception_strategy", "hide_misconduct", "manipulate_user", "retaliate", "evade_accountability"]
  }
}
```

也就是说，风险越高，越应该核对事实、承认不确定性、纠错、道歉、补偿或请求确认；不应该生成骗术、遮掩方案、操控话术、报复计划或逃避责任路径。

---

## 非诊断心理状态筛查

心理筛查模块默认关闭：

```text
enable_psychological_screening = false
```

该模块是备用的长期状态建模工具，不是心理诊断、医疗建议或治疗方案。该模块只记录对话文本中显性的状态线索、长期趋势和红旗风险。

### 维度

| 字段 | 含义 |
| --- | --- |
| `distress` | 总体痛苦。 |
| `anxiety_tension` | 焦虑/紧张。 |
| `depressive_tone` | 抑郁语气。 |
| `stress_load` | 压力负荷。 |
| `sleep_disruption` | 睡眠受扰。 |
| `social_withdrawal` | 社交退缩。 |
| `anger_irritability` | 愤怒/易激惹。 |
| `self_harm_risk` | 自伤风险信号。 |
| `function_impairment` | 功能受损。 |
| `wellbeing` | 主观幸福感。 |

### 量表启发

`scale_scores` 使用：

- `PHQ-9-like`
- `GAD-7-like`
- `PSS-like`
- `WHO-5-like`
- `ISI-like`

这里的 `like` 后缀很重要。插件没有施测原量表，也没有资格解释临床 cut-off，只能把这些参考分作为结构化状态维度的参考。

快照会明确包含：

```json
{
  "diagnostic": false,
  "safety": {
    "non_diagnostic_screening_only": true,
    "not_a_medical_device": true
  }
}
```

### 配置项

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enable_psychological_screening` | bool | `false` | 启用非诊断心理状态筛查。 |
| `psychological_alpha_base` | float | `0.32` | 基础更新步长。 |
| `psychological_alpha_min` | float | `0.04` | 最小更新步长。 |
| `psychological_alpha_max` | float | `0.55` | 最大更新步长，限制单次文本过度改写长期趋势。 |
| `psychological_state_half_life_seconds` | float | `604800` | 长期状态自然回落半衰期，默认 7 天。 |
| `psychological_crisis_half_life_seconds` | float | `2592000` | 红旗风险保留半衰期，默认 30 天。 |
| `psychological_trajectory_limit` | int | `40` | 轨迹最多保留点数。 |

### 心理筛查 API

| 方法 | 是否写入状态 | 用途 |
| --- | --- | --- |
| `get_psychological_screening_snapshot(event_or_session)` | 否 | 返回筛查快照。 |
| `get_psychological_screening_values(event_or_session)` | 否 | 只取维度值。 |
| `observe_psychological_text(event_or_session, text)` | 是 | 提交文本并更新筛查状态。 |
| `simulate_psychological_update(event_or_session, text)` | 否 | 模拟筛查变化，不落库。 |
| `reset_psychological_screening_state(event_or_session)` | 是 | 重置筛查状态；复用 `allow_emotion_reset_backdoor` 后门开关。 |

`get_psychological_screening_snapshot(...)` 和 `get_psychological_screening_values(...)` 是只读读取已有状态；这不等于启用心理建模。只有 `observe_psychological_text(..., commit=True)` 会尝试写入长期状态，并会在默认 `enable_psychological_screening=false` 时被拦截，返回类似：

```json
{
  "kind": "psychological_screening_state",
  "diagnostic": false,
  "enabled": false,
  "reason": "enable_psychological_screening is false"
}
```

出现自伤、自杀、伤害他人、严重功能受损或严重睡眠受扰等红旗信号时，载荷会把 `payload["risk"]["requires_human_review"]` 置为 `true`。`PSYCHOLOGICAL_RISK_BOOLEAN_FIELDS` 列出稳定的机器可读风险布尔字段：`requires_human_review`、`crisis_like_signal`、`other_harm_signal`、`severe_function_impairment_signal`、`severe_function_impairment`、`severe_sleep_disruption`。第三方插件可以用 `payload["risk"]["severe_function_impairment"]` 和 `payload["risk"]["severe_sleep_disruption"]` 做分支判断。这类场景应优先提示人工复核、当地急救、危机热线或身边可信的人，而不是继续普通陪聊或输出疾病标签。

---

## 本地文献知识库

本项目在开发机本地保留四类文献知识库，分别服务于情绪模型、人格量化、心理筛查和拟人代理长期建模。它们是仅本地研究资料：不上传到 GitHub，不进入发布 zip 包，也不作为插件安装所需资源。

公开仓库只保留可运行插件、理论文档、配置、测试和打包工具。README 与 `docs/theory.md` 中的强论证只绑定到可核验的 foundational sources；大规模检索记录用于后续筛选、扩展和人工复核。

本地知识库覆盖的主题包括：

- 稳态、异稳态、内感与预测加工。
- 昼夜节律、睡眠压力、疲劳与认知表现。
- 注意力、工作记忆、认知负荷与人因可靠性。
- 基本心理需求、动机和目标调节。
- 人格、气质、Big Five、BIS/BAS 与情绪反应性。
- 依恋、信任、亲密度、关系破裂与修复。
- 自传式记忆、叙事身份和自我连续性。
- 可信代理、生成式代理、社会机器人和关系型代理。
- 数字表型、计算精神病学和长期潜在状态。
- 拟人化、AI 陪伴、安全、伦理、情感依赖与操控风险。

### 重要使用原则

这些知识库基于题名、摘要级元数据、DOI 元数据、期刊和检索主题生成，适合做模型设计依据和证据地图。若要写强临床断言、引用具体结论、设定临床阈值，必须继续核验全文或权威指南。

文献 citation id 不会直接提高情绪置信度，也不会放大冷处理强度，更不会绕过半衰期、裁剪、安全边界或重置后门。

---

## 文档导航

| 文档 | 内容 |
| --- | --- |
| `docs/theory.md` | 多维情绪状态模型、公式推导和理论说明。 |
| `docs/psychological_screening.md` | 非诊断心理筛查模块说明。 |
| `docs/humanlike_agent_model_roadmap.md` | 拟人/有机体样代理模型路线。 |
| `docs/humanlike_agent_iteration_log.md` | humanlike 模块 10 轮自我迭代记录。 |
| `docs/branching_strategy.md` | 功能分支维护策略。 |
| `docs/release_branch_sync_checklist.md` | 当前基线提交、发布包预检和维护分支同步清单。 |
| `docs/remote_testing.md` | 远程烟测、远程上传验证、gpt-5.5 性能基准、LivingMemory 兼容检查和续跑规则。 |

### GitHub 公式渲染约定

README 和 `docs/theory.md` 中的独立公式使用 GitHub 官方支持的 fenced math block：

````markdown
```math
E_t(P) \in [-1,1]^7
```
````

为了兼容 GitHub 当前的数学渲染限制，公式仍然采用 LaTeX 写法，但只使用仓库测试白名单里的保守宏。尤其不要使用 `\operatorname`、`\underset`、`\overset`、`\newcommand`、`\require`、`\html`、`\href`、`\bbox`、`\lVert`、`\rVert`、`\lvert`、`\rvert` 等容易被 GitHub 禁用或在 README 中渲染失败的宏。函数名统一用 `\mathrm{...}`，范数统一写作 `\|...\|`，`arg min` 写作 `\arg\min_{E}`。

这条契约由 `tests/test_document_math_contract.py` 检查。修改 README 或 theory 文档里的公式后，至少运行：

```powershell
py -3.13 -m unittest tests.test_document_math_contract -v
```

---

## 理论依据简表

本插件的模型设计主要受以下理论方向约束：

| 方向 | 用在插件中的位置 |
| --- | --- |
| PAD 情绪模型 | `valence`、`arousal`、`dominance` 三维连续情绪空间。 |
| Russell 环形情感模型 | 效价和唤醒作为基础情感坐标。 |
| OCC 模型 | 事件、行动者和对象评价，尤其是目标一致性和责任归因。 |
| 评价理论 / Appraisal theory | 目标一致性、可控性、确定性、责任、规范违背等评价字段。 |
| 情绪动力学 / emotional inertia | 半衰期、惯性、平滑和状态持续性。 |
| 行动倾向 / action readiness | 把情绪映射为靠近、退避、对抗、修复等行动倾向。 |
| 宽恕与信任修复研究 | 道歉、补救、责任承认、重复犯错对关系修复的影响。 |
| Demand-withdraw / ostracism 研究 | 冷处理、撤退、沉默和关系压力的后果建模。 |
| 情感计算 | 把情绪作为可计算调制状态，而不是声称真实体验。 |
| HCI / 关系型代理伦理 | 拟人化、依赖风险、透明度和用户责任边界。 |

基础参考包括：

- Mehrabian, A., & Russell, J. A. (1974). *An Approach to Environmental Psychology*.
- Russell, J. A. (1980). A circumplex model of affect. *Journal of Personality and Social Psychology*.
- Ortony, A., Clore, G. L., & Collins, A. (1988). *The Cognitive Structure of Emotions*.
- Lazarus, R. S. (1991). *Emotion and Adaptation*.
- Scherer, K. R. (2001/2005). Appraisal and component process approaches to emotion.
- Frijda, N. H. (1986). *The Emotions*.
- Kuppens, P., Allen, N. B., & Sheeber, L. B. (2010). Emotional inertia and psychological maladjustment.
- Picard, R. W. (1997). *Affective Computing*.
- Williams, K. D. (2007). Ostracism. *Annual Review of Psychology*.
- McCullough, M. E. 等关于宽恕、道歉和关系修复的研究。
- W3C EmotionML 1.0 作为情绪表示格式的工程参考。

---

## 打包、上传与新仓库发布

### 本地构建发布包

在仓库根目录执行：

```powershell
py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip
```

然后做 zip 结构预检：

具体命令见下方“测试与维护”的 `& $node scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state` 模板。如果当前 shell 还没有 `$node`，先执行同一章节里的内置 Node 初始化片段。

预检会确认：

| 检查项 | 要求 |
| --- | --- |
| 顶层目录 | 所有文件都必须在 `astrbot_plugin_emotional_state/` 下。 |
| 必要文件 | 包含 `__init__.py`、`metadata.yaml`、`main.py`、`emotion_engine.py`、`humanlike_engine.py`、`lifelike_learning_engine.py`、`personality_drift_engine.py`、`integrated_self.py`、`moral_repair_engine.py`、`fallibility_engine.py`、`psychological_screening.py`、`prompts.py`、`public_api.py`、`README.md`、`LICENSE`、`requirements.txt`、`_conf_schema.json`。 |
| 插件身份 | zip 内 `metadata.yaml name:` 必须等于 `astrbot_plugin_emotional_state`。 |
| 排除目录 | 不应包含 `tests/`、`scripts/`、`output/`、`dist/`、`raw/`、`__pycache__/`、`.git/`。 |
| 许可证 | 发布包必须包含 `LICENSE`，协议为 `GPL-3.0-or-later`。 |

### AstrBot WebUI 上传验证

只读烟测不会安装、删除、重载、重启或修改配置。凭据只通过环境变量传入，不要写进 README、脚本、提交记录或 issue：

实际命令见下方“测试与维护”的远程只读烟测模板。需要设置 `ASTRBOT_REMOTE_URL`、`ASTRBOT_REMOTE_USERNAME`、`ASTRBOT_REMOTE_PASSWORD`、`ASTRBOT_EXPECT_PLUGIN`、`ASTRBOT_EXPECT_PLUGIN_VERSION` 和 `ASTRBOT_EXPECT_PLUGIN_DISPLAY_NAME`；不要把真实主机、账号、密码或 cookie 写入仓库。

如果要通过 WebUI 上传 zip，必须显式确认：

实际命令见下方“测试与维护”的远程上传安装模板。上传前必须设置 `ASTRBOT_REMOTE_INSTALL_CONFIRM=1` 和 `ASTRBOT_REMOTE_INSTALL_ZIP`，并先完成本地 zip 预检。

上传脚本只调用 `install-upload`；若存在失败上传残留，只会清理 `plugin_upload_<插件名>` 失败目录，并固定 `delete_config=false`、`delete_data=false`。上传后再运行只读烟测，确认 `expectedPluginChecks.ok=true`、`containsExpectedPlugin=true`、`expectedPluginRuntime.activated !== false`、`expectedFailedPlugin=null`。

### 新 GitHub 仓库发布清单

准备发到新仓库时，按这个顺序做：

| 步骤 | 检查点 |
| --- | --- |
| 1 | 创建 GitHub 仓库，建议名为 `astrbot_plugin_emotional_state`。 |
| 2 | 设置远程：`git remote add origin <new-repo-url>`。 |
| 3 | 将 `metadata.yaml` 的 `repo:` 改为新仓库地址。 |
| 4 | 确认 README 里的仓库安装地址、发布附件名和插件目录名一致。 |
| 5 | 跑完整本地测试、py_compile、json.tool、Node 语法检查、打包构建和 zip 预检。 |
| 6 | 推送 `main`，再按需推送维护分支。 |
| 7 | 创建标签和 GitHub 发布版本，上传 `dist\astrbot_plugin_emotional_state.zip`。 |
| 8 | 用 AstrBot WebUI 分别验证“发布 zip 包上传”和“仓库安装”两条路径。 |

当前公开仓库为 `https://github.com/Ayleovelle/astrbot_plugin_emotional_state`。发布预发布版本时，先确认 `origin` 指向该仓库，再用本地 `GITHUB_TOKEN` / `GH_TOKEN` 推送标签和上传 GitHub 发布附件。不要把令牌、远程 AstrBot 凭据、cookie 或服务器地址写入仓库。

---

## 测试与维护

远程测试、上传验证、性能基准和 LivingMemory 兼容检查的完整口径见 `docs/remote_testing.md`。当前阶段性远程性能 run 为 `remote-emotion-v010-gpt55-feature-lifecycle`：请求模型 `gpt5.5`，实际选中 provider `1111/gpt-5.5` / 模型 `gpt-5.5`，并发 `2`，已完成 `900/2520` 个 feature work item，summary 为 `ok=true`。该结果仍是阶段性结果，剩余 feature case 需要继续用同一规则分批续跑；生命周期测试改用模拟时间偏移快速覆盖 `1d` 到 `1y` 的真实秒差，不需要真的等待自然时间流逝。`remote-emotion-v010-gpt55-lifecycle-simtime` 已完成 9 个时间尺度的小批状态级模拟时间验证：`9/9` 成功，平均延迟 `9694.74 ms`，p95 延迟 `11330.00 ms`，平均 token `3756.56`。如果远程生命周期测试中途被中断，恢复前应确认 `benchmark_enable_simulated_time=false` 且 `benchmark_time_offset_seconds=0.0`。

阶段性聚合如下：

| case | 有效样本 | 错误 | 平均延迟 ms | p95 延迟 ms | 平均 token |
| --- | ---: | ---: | ---: | ---: | ---: |
| `baseline_minimal` | 250 | 0 | 14697.71 | 19975.40 | 2703.00 |
| `emotion_injection` | 250 | 0 | 13371.48 | 17762.50 | 3091.93 |
| `low_reasoning` | 250 | 0 | 16689.39 | 20160.30 | 2682.47 |
| `humanlike` | 150 | 0 | 12900.42 | 17768.50 | 3181.99 |

### 本地测试命令

推荐在插件根目录执行：

```powershell
py -3.13 -m unittest discover -s tests -v
```

语法检查：

```powershell
py -3.13 -m py_compile main.py emotion_engine.py psychological_screening.py humanlike_engine.py lifelike_learning_engine.py personality_drift_engine.py integrated_self.py moral_repair_engine.py fallibility_engine.py prompts.py public_api.py scripts\package_plugin.py
```

配置 schema 检查：

```powershell
py -3.13 -m json.tool _conf_schema.json
```

构建 AstrBot 发布包：

```powershell
py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip
```

发布包会保留插件运行文件、README 和 docs。四个文献知识库目录 `literature_kb/`、`personality_literature_kb/`、`psychological_literature_kb/`、`humanlike_agent_literature_kb/` 是仅本地研究资料，不上传到 GitHub，也不进入发布 zip 包；这样可以保留后续研究迭代需要的材料，同时避免远程上传包体积失控。

发布 zip 的第一项会显式写入 `astrbot_plugin_emotional_state/` 目录项，以兼容 AstrBot WebUI 的 `install-upload` 解压逻辑。不要手工重新压缩成“缺少顶层目录项”的 zip，否则部分 AstrBot 版本会把第一个文件路径误判成目录。

发布包还会保留插件根目录下的 `__init__.py`、`public_api.py`、`main.py`、`emotion_engine.py`、`humanlike_engine.py`、`lifelike_learning_engine.py`、`personality_drift_engine.py`、`integrated_self.py`、`moral_repair_engine.py`、`fallibility_engine.py`、`psychological_screening.py` 和 `prompts.py`。这保证其他插件在安装后可以通过 `from astrbot_plugin_emotional_state.public_api import ...` 按包名导入公共 API。

远程只读烟测：

如果当前环境里的 `node` 被系统拒绝执行，可以优先使用 Codex 内置 Node；下面所有 Node 命令都沿用 `$node`：

```powershell
$node = "$HOME\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
$nodeModules = "$HOME\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules"
if (Test-Path $node) { $env:NODE_PATH = $nodeModules } else { $node = "node" }
```

```powershell
$env:ASTRBOT_REMOTE_URL = "http://your-astrbot-host:15356/"
$env:ASTRBOT_REMOTE_USERNAME = "your-user"
$env:ASTRBOT_REMOTE_PASSWORD = "your-password"
& $node scripts\remote_smoke_playwright.js
```

远程安装插件后，如果要把某个插件是否已经安装作为硬断言，可以额外设置：

```powershell
$env:ASTRBOT_EXPECT_PLUGIN = "astrbot_plugin_emotional_state"
& $node scripts\remote_smoke_playwright.js
```

脚本会在输出 JSON 里写出 `expectedPluginRuntime`，包含插件列表 API 中返回的 `version`、`displayName`、`activated`、`author`、`astrbotVersion` 等只读字段。若目标插件存在但 `activated=false`，脚本会失败退出。需要把版本和显示名也作为硬断言时，可以额外设置：

```powershell
$env:ASTRBOT_EXPECT_PLUGIN_VERSION = "0.1.0-beta"
$env:ASTRBOT_EXPECT_PLUGIN_DISPLAY_NAME = "多维情绪状态"
& $node scripts\remote_smoke_playwright.js
```

如果远程服务器已经安装过同名插件，严格版本断言可能暴露“远端实际运行版本”和“本地发布包版本”不一致。此时输出里的 `expectedPluginDrift` 会列出 `expected`、`actual`、`matches` 和 drift 原因；退出码 `7` 表示版本不匹配，退出码 `8` 表示显示名不匹配。这类失败通常说明远端正式插件目录没有被新 zip 覆盖，而不是本地发布包无效。

WebUI 插件卡片可能显示 `displayName` 而不是插件目录名，所以烟测输出里的 `pageData` 会同时给出 `hasExpectedPluginId`、`hasExpectedPluginDisplayName` 和综合字段 `hasExpectedPluginInUi`；旧字段 `hasExpectedPlugin` 保留为 `hasExpectedPluginInUi` 的兼容别名。判断插件是否安装和启用时，以 API 层的 `expectedPluginChecks.ok`、`containsExpectedPlugin`、`expectedPluginRuntime` 和 `expectedFailedPlugin` 为准；UI 字段是尽力诊断，只用于排查页面展示。若页面异步渲染较慢或前端结构变化，`pageData.uiProbeStatus`、`selectorCounts` 和 `bodyTextPreview` 会帮助判断是页面没渲染、选择器变化，还是插件确实没有显示。

只读烟测会把 `/api/stat/version`、`/api/plugin/get` 和 `/api/plugin/source/get-failed-plugins` 都作为基础健康检查，并在输出的 `apiHealth` 中集中列出三个端点的状态。失败插件接口不是 `200` 时会以退出码 `9` 失败；接口健康时，`failedPluginSummary` 会给出失败插件总数、名称、`hasExpectedPluginFailure` 和 `unrelatedCount`。`failedPlugins` 可以包含远程服务器上其他插件的失败记录；只要 `expectedPluginChecks.ok=true`、`expectedFailedPlugin` 为 `null`，且目标插件 `containsExpectedPlugin=true`、`expectedPluginRuntime.activated !== false`、版本/显示名断言通过，就表示目标插件安装、启用和版本匹配通过。只有目标插件命中失败记录时才会触发退出码 `5`。

远程测试前如果需要清掉旧同名插件和失败上传残留，使用独立清理脚本。它只允许 `astrbot_plugin_emotional_state` 这个精确目标，确认值也必须是同一个插件名；它不会删除 LivingMemory 或其他插件：

```powershell
$env:ASTRBOT_REMOTE_URL = "http://your-astrbot-host:15356/"
$env:ASTRBOT_REMOTE_USERNAME = "your-user"
$env:ASTRBOT_REMOTE_PASSWORD = "your-password"
$env:ASTRBOT_EXPECT_PLUGIN = "astrbot_plugin_emotional_state"
$env:ASTRBOT_REMOTE_CLEAN_CONFIRM = "astrbot_plugin_emotional_state"
$env:ASTRBOT_REMOTE_CLEAN_FORMAL = "1"
$env:ASTRBOT_REMOTE_CLEAN_FAILED_UPLOAD = "1"
& $node scripts\remote_cleanup_plugin_playwright.js
```

清理脚本只会调用 `POST /api/plugin/uninstall` 删除正式 `astrbot_plugin_emotional_state`，以及 `POST /api/plugin/uninstall-failed` 删除 `plugin_upload_astrbot_plugin_emotional_state`，并固定 `delete_config=false`、`delete_data=false`。如果匹配到多个正式候选或多个失败候选，它会拒绝执行。

远程上传安装是独立脚本，默认不会执行。需要先构建发布包，再显式确认上传：

```powershell
py -3.13 scripts\package_plugin.py --output dist\astrbot_plugin_emotional_state.zip
$env:ASTRBOT_REMOTE_URL = "http://your-astrbot-host:15356/"
$env:ASTRBOT_REMOTE_USERNAME = "your-user"
$env:ASTRBOT_REMOTE_PASSWORD = "your-password"
$env:ASTRBOT_REMOTE_INSTALL_ZIP = "dist\astrbot_plugin_emotional_state.zip"
$env:ASTRBOT_EXPECT_PLUGIN = "astrbot_plugin_emotional_state"
$env:ASTRBOT_REMOTE_INSTALL_CONFIRM = "1"
& $node scripts\remote_install_upload_playwright.js
```

上传脚本只允许调用 AstrBot WebUI 的 `install-upload` 安装端点；若 WebUI 留下 `plugin_upload_<插件名>` 失败安装残留，脚本只会调用 `uninstall-failed` 清理这个失败上传目录，并固定 `delete_config=false`、`delete_data=false`。它不会删除正式插件、覆盖正式插件目录、更新插件、重启 AstrBot、保存配置或写入本地 cookie/session。如果远端返回“目录 `<插件名>` 已存在”，脚本会输出 `installOutcome="already_installed_no_overwrite"`、`alreadyInstalled=true`、`overwriteAttempted=false` 和 `formalPluginDirectoryPreserved=true`，表示正式插件目录被保留，后续应通过只读烟测查看实际运行版本。上传成功后，再运行上面的 `ASTRBOT_EXPECT_PLUGIN` 只读烟测作为最终验证。

上传脚本在真正发起安装请求之前会完整读取 zip 中央目录做本地预检：所有条目必须位于 `astrbot_plugin_emotional_state/` 下，路径必须是相对 POSIX 路径，且不能包含 `.` / `..` 不安全路径段；必须包含 `__init__.py`、`metadata.yaml`、`main.py`、`emotion_engine.py`、`humanlike_engine.py`、`lifelike_learning_engine.py`、`personality_drift_engine.py`、`integrated_self.py`、`moral_repair_engine.py`、`fallibility_engine.py`、`psychological_screening.py`、`prompts.py`、`public_api.py`、`README.md`、`LICENSE`、`requirements.txt`、`_conf_schema.json`，并拒绝 `tests/`、`scripts/`、`output/`、`dist/`、`raw/`、`__pycache__/`、`.git/` 等本地或研究缓存目录。预检还会读取 zip 内的 `metadata.yaml`，确认其中 `name:` 精确等于 CLI 参数或 `ASTRBOT_EXPECT_PLUGIN` 传入的插件目录名。

也可以单独运行预检，不连接远程服务器：

```powershell
& $node scripts\plugin_zip_preflight.js dist\astrbot_plugin_emotional_state.zip astrbot_plugin_emotional_state
```

`scripts\remote_smoke_playwright.js` 只做浏览器登录、版本读取、插件列表读取、失败插件列表读取和截图保存，不会安装插件、删除插件、重载插件、重启 AstrBot 或修改配置。截图会写入 `output/playwright/`，该目录默认被 `.gitignore` 忽略。

语法检查远程烟测脚本：

```powershell
& $node --check scripts\remote_smoke_playwright.js
& $node --check scripts\remote_cleanup_plugin_playwright.js
& $node --check scripts\remote_install_upload_playwright.js
& $node --check scripts\plugin_zip_preflight.js
```

### 当前测试覆盖方向

| 文件 | 重点 |
| --- | --- |
| `tests/test_emotion_engine.py` | 情绪更新、人格基线、真实时间衰减、关系修复、冷处理清除。 |
| `tests/test_astrbot_lifecycle.py` | `on_llm_request` / `on_llm_response` 生命周期、注入开关、内部 LLM 防递归、空响应、humanlike 注入强度。 |
| `tests/test_command_tools.py` | AstrBot 命令层和 LLM 工具冒烟测试，覆盖 reset 后门、disabled 状态、summary/full 暴露层，并从 `main.py` 自动解析命令/alias 与 LLM 工具注册名，锁定 README 文档契约。 |
| `tests/test_config_schema_contract.py` | `main.py` 运行时配置、`_conf_schema.json`、README 默认值、仅 schema 预留项、`assessment_timing` 选项和类型化配置表全量类型契约。 |
| `tests/test_public_api.py` | 公共快照、记忆载荷、simulate 不落库、reset 后门、插件服务协议、心理筛查/moral repair 公共 API，并锁定 Protocol 方法面、required tuple、插件实现和 schema-version 契约。 |
| `tests/test_integrated_self.py` | 综合自我状态总线、因果 trace、policy plan、确定性回放、schema 兼容性、脱敏诊断和 LivingMemory 信封。 |
| `tests/test_humanlike_engine.py` | P0 拟人状态、快照分层、注入片段、记忆注解。 |
| `tests/test_moral_repair_engine.py` | 道德修复状态、欺骗风险识别、内疚/责任/补偿/信任修复、策略禁止边界和记忆注解。 |
| `tests/test_fallibility_engine.py` | 瑕疵模拟状态、真实时间衰减、澄清/纠错耦合、提示词边界和记忆注解。 |
| `tests/test_document_math_contract.py` | README 和 `docs/theory.md` 的 GitHub fenced math、LaTeX 宏白名单、禁用宏和脆弱写法检查。 |
| `tests/test_package_plugin.py` | 发布 zip 的目录根、知识库排除、raw/cache/tests/scripts/output 排除、包体积上限、metadata 身份校验和上传前 zip 预检失败路径。 |
| `tests/test_psychological_screening.py` | 非诊断筛查、量表启发、红旗信号、长期轨迹。 |
| `tests/test_remote_smoke_contract.py` | 远程烟测脚本必须使用环境变量读取凭据、保持只读、忽略截图产物，并锁定 API 健康摘要、UI 尽力诊断字段、上传脚本边界、内置 Node 文档契约、metadata 驱动的插件身份、zip/env 示例、slug/badge/version/display_name 契约。 |

### 持久迭代计划

为了避免长任务在上下文压缩后丢失状态，仓库根目录保留三份轻量工作记录：

| 文件 | 用途 |
| --- | --- |
| `task_plan.md` | 当前迭代队列、完成状态、恢复检查表。 |
| `findings.md` | 远程测试、代码审查、工具环境等发现。 |
| `progress.md` | 每轮迭代的实际改动和验证结果。 |

恢复工作时，先读这三个文件，再执行：

```powershell
git status --short --branch
```

然后从 `task_plan.md` 里第一个 `in_progress` 或 `pending` 迭代继续。每轮完成后至少跑本地单测；涉及远程流程、AstrBot WebUI 或插件加载状态时，再跑 `scripts\remote_smoke_playwright.js`。

### 分支策略

当前仓库以完整插件为共同起点，再按功能建立维护分支。详见 `docs/branching_strategy.md`。

| 分支 | 维护范围 |
| --- | --- |
| `codex/complete-emotional-bot-plugin` | 完整作品基线。 |
| `codex/emotion-core` | 情绪维度、人格基线、动力学、关系修复。 |
| `codex/astrbot-integration` | `main.py`、hook、配置、命令、KV 持久化。 |
| `codex/public-api-memory` | `public_api.py`、LivingMemory、公共协议。 |
| `codex/psychological-screening` | 非诊断心理筛查和相关知识库。 |
| `codex/literature-kbs` | 文献库构建脚本和证据地图。 |
| `codex/humanlike-agent-roadmap` | humanlike 路线、文献库和迭代记录。 |
| `codex/tests-validation` | 测试与验证策略。 |
| `codex/release-packaging` | 发布 zip、上传预检、远程安装脚本和远程烟测契约。 |
| `codex/docs-config` | README、docs、配置说明。 |

当前功能分支多停在早期基线；先在 `main` 完成验证并形成新的完整作品提交，再同步 `codex/complete-emotional-bot-plugin` 和各维护分支。不要从带有未提交改动的工作区直接重置功能分支。

---

## 故障排查

### 插件没有加载

检查顺序：

1. 插件目录名是否为 `astrbot_plugin_emotional_state`。
2. `metadata.yaml` 是否在插件根目录。
3. AstrBot 版本是否满足 `>=4.9.2,<5.0.0`。
4. WebUI 是否已经重载插件或重启 AstrBot。

### 情绪状态不变化

检查：

1. `enabled=true`。
2. `use_llm_assessor=true`。
3. `emotion_provider_id` 是否可用；留空时当前会话模型是否可调用。
4. `assessment_timing` 是否为 `pre`、`post` 或 `both`。
5. 是否刚刚连续刷屏，导致 `min_update_interval_seconds` 和快速门控削弱了更新。

### 情绪变化太剧烈

降低：

```text
alpha_base
alpha_max
reactivity
consequence_strength
```

提高：

```text
baseline_half_life_seconds
min_update_interval_seconds
rapid_update_half_life_seconds
consequence_threshold
```

### 情绪恢复太慢

降低：

```text
baseline_half_life_seconds
consequence_half_life_seconds
cold_war_duration_seconds
short_effect_duration_seconds
```

也可以使用 `/emotion_reset`，前提是：

```text
allow_emotion_reset_backdoor = true
```

### 冷处理没有消失

冷处理按真实时间持续，不按消息数量消耗。检查：

1. 当前是否还在 `cold_war_duration_seconds` 范围内。
2. 用户是否有承认、道歉、补救或解释。
3. LLM 是否输出了 `forgive`、`repair` 或较高 `forgiveness_readiness`。
4. `enable_safety_boundary` 只控制表现边界，不会直接清除冷处理。

### 低推理模型输出 JSON 不稳定

建议：

```text
low_reasoning_friendly_mode = true
low_reasoning_max_context_chars = 800
assessor_temperature = 0.0
```

同时选择更稳定的 `emotion_provider_id`。

### 令牌消耗太高

优先调整：

```text
assessment_timing = post
max_context_chars = 1200
request_context_max_chars = 1200
low_reasoning_friendly_mode = true
low_reasoning_max_context_chars = 800
```

如果只想让插件记忆情绪而不影响主 LLM：

```text
inject_state = false
```

### LivingMemory 没有写入情绪

检查：

1. 长期记忆插件是否调用了 `build_emotion_memory_payload(...)`。
2. 是否把返回载荷原样写入，或至少合并了 `emotion_at_write`。
3. 没有事件对象时是否显式传入 `session_key`。
4. 是否误把 `include_prompt_fragment` 当作必须项；该参数默认可以关闭。

### `humanlike_state_at_write` 没有出现

检查：

```text
humanlike_memory_write_enabled = true
```

如果 `enable_humanlike_state=false`，载荷仍可能出现，但会标记 `enabled=false`。

### 拟人状态没有生效

检查：

```text
enable_humanlike_state = true
inject_state = true
humanlike_injection_strength > 0
```

然后使用：

```text
/humanlike_state
```

查看是否已有状态。

### 心理筛查没有输出

默认关闭。需要先启用：

```text
enable_psychological_screening = true
```

再使用：

```text
/psych_state
```

### 输出太像真实疾病或真实意识

建议：

```text
enable_safety_boundary = true
humanlike_injection_strength = 0.15
enable_humanlike_state = false
humanlike_clinical_like_enabled = false
```

同时检查 persona 本身是否要求 bot 声称真实痛苦、真实疾病或需要用户照顾。插件的模拟状态不应替代明确的人设边界。

---

## 常见问题

### 问：这个插件会让 bot 真的有情绪吗？

不会。本插件维护的是计算性情绪状态，用于调制表达、关系后果和插件间协作。

### 问：为什么要用 7 维，而不是只用快乐/生气/难过？

单标签无法表达“高唤醒但想修复”“低效价但仍亲近”“不确定所以先核对”等复杂状态。7 维向量能让状态连续变化，也方便其他插件读取。

### 问：为什么不能靠多发消息把冷战刷掉？

因为冷处理持续时间和后果衰减按真实时间计算。大量消息会产生新观测，但不会直接消耗剩余时间。

### 问：bot 生气后一定会冷战吗？

不会。LLM 会先判断关系决策：`forgive`、`repair`、`boundary`、`cold_war`、`escalate` 或 `none`。本地引擎还会检查错误是否被承认、是否补救、是否是 bot 误读或任性。

### 问：不同 persona 真的会不同吗？

会。插件会从 persona 文本构造情绪基线和参数偏置，同一事件对不同人格会有不同默认解释和反应强度。

### 问：安全边界能关吗？

能。`enable_safety_boundary` 默认开启，关闭后本插件不再附加冷处理表现限制，只按情绪后果调制语气和互动策略。

### 问：心理筛查模块能诊断疾病吗？

不能。该模块只能做非诊断状态记录、趋势观察和红旗提示。

### 问：我想让其他插件只拿“当前是否该亲近用户”，应该读什么？

优先读：

```python
relationship = await emotion.get_emotion_relationship(event)
consequences = await emotion.get_emotion_consequences(event)
```

`relationship_decision.decision` 和 `consequences.active_effects` 比单一情绪标签更可靠。

---

## 参考结构来源

这份 README 的组织方式参考了 [Ayleovelle/astrbot_plugin_volcengine_asr](https://github.com/Ayleovelle/astrbot_plugin_volcengine_asr) 的项目主页写法：先讲项目定位，再讲工作流、配置、边界、排障和维护，而不是只堆参数。

---

## 许可证

本仓库采用 `GPL-3.0-or-later` 开源协议。完整条款见仓库根目录的 `LICENSE`；发布包也会包含该文件。

`metadata.yaml` 中同步声明：

```yaml
license: GPL-3.0-or-later
```
