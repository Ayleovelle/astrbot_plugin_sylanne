# Sylanne-Embodiment 1.3.x Backlog

> 160 个改进项，按领域分组。工作量标记：S(<2h) M(2-5h) L(5-10h) XL(>10h)

---

## 对话质量与用户体验

1. `[M]` 对话情绪回顾摘要 — `llm_response_pipeline.py` 新增 `_generate_session_summary()`，会话结束时自动生成情绪弧线摘要存入 L1 记忆
2. `[S]` 首次对话引导流程 — `prompt_surface.py` 新增 `render_onboarding_fragment()`，tick_count < 5 时注入引导性 prompt 片段
3. `[M]` 用户偏好自动提取 — `llm_request_pipeline.py` 新增 `_extract_preferences()` 钩子，从对话中提取称呼/禁区/风格写入 per-relationship overlay
4. `[L]` 多模态情绪感知 — `llm_request_pipeline._transcribe_non_text()` 扩展：图片调 vision LLM 返回 valence/arousal 标签注入 L1
5. `[M]` 对话节奏可视化 — WebUI 新增 Rhythm 面板：展示 rhythm_learner 的用户画像
6. `[S]` 主动发言反馈按钮 — WebUI Monitor 面板加 👍/👎 按钮，调用 `/api/proactive_feedback`
7. `[M]` 对话中断恢复提示 — `realtime_dispatch.py` 新增 `_build_resumption_hint()`，>2h 回来时注入断点摘要
8. `[S]` 记忆召回可解释性 — `/api/memory_pools` 返回值新增 `recall_reason` 字段
9. `[M]` 语音消息节奏适配 — `rhythm_learner.py` 新增 `observe_voice_message()`，按时长计入画像
10. `[S]` 配置预设模板 — `webui_routes.py` 新增 `/api/config_presets`，提供温柔型/锋利型/沉默型一键应用

## 架构与性能

11. `[L]` 计算栈流水线并行化 — L1-L2 和 L4 用 `asyncio.gather` 并行执行
12. `[M]` 增量状态持久化 — dirty-flag 机制，只序列化变化的子系统
13. `[L]` 记忆系统向量索引 — L2 层新增 HNSW 近似最近邻索引，1000+ 条时 <1ms 召回
14. `[M]` Protocol 类型覆盖扩展 — 新增 `PluginLLMAccess` 和 `PluginLifecycle` Protocol
15. `[S]` 计算栈层级超时保护 — 每层加 200ms 超时，超时返回缓存结果
16. `[M]` WebUI WebSocket 推送 — 新增 `/ws/state` 端点替代 polling
17. `[L]` 插件热升级零停机 — 新代码加载→迁移引用→切换→旧代码 GC
18. `[M]` 记忆系统分片存储 — L2/L3 按 session_key 分文件存储
19. `[S]` HDC 编码器维度可配置 — 允许低配设备降到 1024 维
20. `[M]` 计算栈结果缓存层 — 相同输入 TTL 内直接返回缓存结果

## 安全与防御性编程

21. `[M]` 人格漂移速率限制器 — 单次 tick 内所有特质变化总量不超过 0.05
22. `[S]` 记忆注入长度硬上限 — 4000 字符硬截断
23. `[M]` 伤痕代数数值稳定性审计 — exp clamp(-500,500) + epsilon 防零除
24. `[S]` WebUI CSRF 防护 — POST/DELETE 端点要求 X-CSRF-Token header
25. `[M]` 会话隔离审计 — 断言不同 session_key 的 host/memory 无交叉引用
26. `[S]` 配置值边界校验 — 所有 `_cfg_float/_cfg_int` 加 min/max 校验，非法值回退 default
27. `[M]` 虚空压力上溢保护 — 所有 pressure 累加后加 `min(pressure, MAX_PRESSURE)` 硬顶
28. `[S]` LLM 响应注入防御 — 过滤 LLM 返回中的 `[sylanne_` 伪造标签
29. `[M]` 持久化数据完整性校验 — save 时写入 CRC32，load 时验证，损坏回退上一快照
30. `[S]` 背压队列溢出告警 — 队列 >80% maxlen 时 WebUI 推送告警

## 情感差异化与深度

31. `[L]` 梦境生成系统 — 离线 >6h 时 LLM 生成碎片梦境叙事，醒来可分享
32. `[M]` 伤痕可视化地图 — WebUI 力导向图展示伤痕网络（节点=伤痕，边=耦合，颜色=温度）
33. `[L]` 关系纪念日系统 — 追踪首次对话/重要事件日期，到期触发纪念性主动发言
34. `[M]` 情绪天气隐喻 — 8 维情感→天气描述注入 prompt 自我感知层
35. `[XL]` 关系考古学 — 定期从 L3 冷记忆发掘被遗忘的关系模式，生成考古报告
36. `[M]` 沉默质感分类 — 等待型/消化型/疏离型/满足型四种，影响主动发言方向
37. `[L]` 情感共振检测 — L5.5 层检测用户-Sylanne 情绪同步/反相模式
38. `[M]` 伤痕愈合仪式 — repair_count 达标时触发特殊主动发言 + 状态转 healed
39. `[S]` 人格季节性漂移 — 根据真实日期微调 Embodiment Five
40. `[M]` 关系温度计 — WebUI 液柱动画展示关系温度

## 测试与可观测性

41. `[L]` 端到端集成测试框架 — pytest + asyncio mock 覆盖 5 个核心场景
42. `[M]` 计算栈回归测试快照 — 已知输入的输出 JSON 对比
43. `[S]` 人格漂移单元测试 — 极端信号不越界、Dual-EMA 收敛、legacy 映射
44. `[M]` WebUI API 契约测试 — aiohttp test_client 验证所有端点 schema
45. `[S]` 性能基准测试 — timeit 测 p50/p95/p99，CI 回归阈值
46. `[M]` 持久化 round-trip 测试 — to_dict()→from_dict() 完全可逆
47. `[S]` WebUI /health 健康检查端点 — 返回 status/uptime/sessions/memory_mb
48. `[M]` Prometheus 指标导出 — /metrics 端点输出 spine_duration/pool_size/drift_total
49. `[S]` 错误率仪表盘 — Logs 面板新增每分钟 ERROR/WARN 计数折线图
50. `[M]` 记忆系统压力测试 — 10000 条写入 + 并发召回，验证无死锁/OOM

## 跨领域

51. `[L]` 多语言 prompt 模板系统 — prompts/zh.yaml + prompts/en.yaml，运行时按配置加载
52. `[M]` 关系层析可视化 — WebUI Sheaf 面板展示单纯复形拓扑
53. `[S]` 配置导出/导入 — /api/config_export + /api/config_import
54. `[M]` 生命模拟事件类型扩展 — 结构化类型 + 情绪权重 + 分享倾向
55. `[L]` 离线模式降级 — LLM 不可达时纯计算栈规则回复
56. `[M]` 群聊角色感知 — 识别话题发起者/附和者/潜水者，影响回复策略
57. `[S]` 计算栈层级开关 — per-layer enable/disable 配置
58. `[M]` 对话缓冲区压缩 — >20 轮旧对话 LLM 压缩为摘要
59. `[L]` 插件间事件总线 — emit_event/on_event API
60. `[M]` 自动诊断报告 — /api/diagnostic_report 一键生成健康度+统计+异常列表

## 用户教育与生态

61. `[M]` 交互式人格调参向导 — WebUI 分步引导用户微调 5 大人格轴，实时预览风格变化
62. `[S]` 内置术语词典悬浮卡片 — WebUI 对 Sylanne 专有概念添加 hover tooltip
63. `[M]` 新手 30 天成长日志 — 每日生成"今天的 Sylanne 变化"摘要，展示漂移/记忆曲线
64. `[L]` AstrBot 事件钩子双向桥接 — 订阅 AstrBot 事件注入计算栈，广播 Sylanne 内部事件
65. `[M]` 插件间记忆共享协议 — JSON-RPC 2.0 接口让其他插件读写指定 namespace
66. `[S]` AstrBot 管理面板状态卡片 — astrbot_widget.json + /api/widget-state
67. `[L]` 对话质量仪表盘 — 聚合 assessor 评分/延迟/深度/共振，ECharts 趋势图
68. `[M]` 人格漂移归因分析 — drift_attribution() 记录触发事件链，输出因果图 JSON
69. `[S]` 周报自动生成 — 每周汇总对话/记忆/漂移/伤痕/相变，Markdown 周报
70. `[M]` 记忆衰减曲线可视化 — decay_curve(memory_id) 接口 + Ebbinghaus 风格图

## 隐私与数据主权

71. `[M]` 本地差分隐私噪声层 — 发送 LLM 前对 PII 注入可逆 ε-差分隐私噪声
72. `[S]` 数据导出与彻底删除 — export_user_data + purge_user_data（GDPR 式擦除）
73. `[M]` 端到端加密记忆存储 — AES-256 加密落盘，密钥由用户口令派生
74. `[S]` 敏感话题自动脱敏标记 — 健康/财务/法律片段打 [SENSITIVE] 标签，不参与跨会话召回

## 可扩展性

75. `[L]` 计算层插件注册表 — LayerRegistry 模式，第三方通过 entry_points 注册自定义层
76. `[M]` 回复策略热插拔 — strategy_plugins/ 目录 + ReplyStrategy 抽象基类
77. `[S]` 自定义评分维度扩展点 — assessor 维度从硬编码改为 config 动态加载

## 对话策略

78. `[M]` 苏格拉底式追问模式 — 检测模糊观点时切换反问/引导式回复
79. `[S]` 回复长度自适应控制器 — 统计用户近 20 条平均长度，动态调整 max_tokens 倍率
80. `[M]` 叙事视角切换 — 第一人称/第三人称/旁白视角，由 narrative_distance 参数驱动

## 错误恢复与自愈

81. `[M]` LLM 降级链 — 主模型→备用→本地小模型→模板回复
82. `[S]` 计算层异常隔离与自愈 — circuit_breaker（3 次异常熔断 60s）
83. `[M]` 状态一致性自检守护线程 — 每 5 分钟校验参数/索引/权重，异常自动回滚

## 社区与分享

84. `[M]` 人格配置分享市场 — .sylanne-profile 文件导出/导入
85. `[S]` 匿名对话片段投稿 — 脱敏后投稿到公共语料池
86. `[L]` 多实例协作对话 — 两个 Sylanne 实例 WebSocket 互联，辩论/互补模式

## 无障碍与国际化

87. `[M]` 完整 i18n 框架 — locale/{lang}.json，首批 zh-CN/en-US/ja-JP
88. `[S]` WebUI ARIA 无障碍增强 — aria-label/aria-live/role + 键盘导航
89. `[S]` 情感状态语音描述 — /api/accessibility/emotion-audio-desc 供 TTS 朗读
90. `[L]` 轻量级边缘运行模式 — edge_mode：3 层核心 + 暴力搜索 + 128d embedding，树莓派可运行

## 对话策略动态化（续）

91. `[M]` 对话模式动态切换引擎 — ModeRouter 自动切换 comfort/playful/serious/curious 四种模板
92. `[L]` 用户情绪危机检测管线 — CrisisDetector 三级预警（关注/警告/危机）
93. `[M]` 关系修复策略模块 — repair_strategy.py，连续冲突超阈值时生成修复提案
94. `[S]` 对话质量自评打分器 — 每轮结束 self_score() 从连贯性/情感匹配/信息密度三维度打分
95. `[M]` 记忆遗忘曲线精细化 — Ebbinghaus 变体，rehearsal_count/emotional_weight/recency 三因子
96. `[S]` 时区感知与作息推断 — infer_active_hours() 拟合用户活跃窗口，避免深夜打扰
97. `[L]` 能量管理模型 — EnergyPool 模拟认知负荷/情感消耗/恢复周期
98. `[M]` 好奇心驱动行为生成器 — curiosity_drive 维度，信息熵低时触发探索性提问
99. `[S]` 模式切换过渡动画语义 — transition_templates 字典避免人格割裂感
100. `[M]` 冲突事件溯源日志 — conflict_trace() 记录每次张力升高的触发链

## 多设备与上下文管理

101. `[L]` 多设备会话状态同步协议 — CRDT StateVector + merge_conflict_resolver
102. `[M]` 上下文窗口滑动压缩策略 — WindowManager 按重要性分层压缩
103. `[S]` 设备切换感知问候 — 检测 device_fingerprint 变化时生成适配问候
104. `[M]` 表情包/媒体情绪理解接口 — MediaEmotionTag 协议返回 (emotion, intensity, irony_probability)
105. `[L]` 用户画像长期演化追踪 — ProfileEvolution 每周快照兴趣向量/情感基线/互动模式
106. `[M]` 对话上下文重要性标注 — importance_tagger() 打 ephemeral/notable/landmark 三级标签
107. `[S]` 离线消息队列与重连摘要 — offline_buffer + "你不在的时候我想到了…"式摘要
108. `[M]` 跨设备偏好继承与覆盖 — device_overrides 层级
109. `[S]` 上下文窗口耗尽预警 — 剩余 token <20% 时主动提示用户
110. `[M]` 媒体情绪与文本情绪融合 — multimodal_fusion() 加权融合处理反讽

## 插件生态与自我演化

111. `[L]` 插件市场元数据规范 v2 — compatibility_matrix/resource_budget/personality_impact
112. `[M]` WebUI 主题系统重构 — /api/theme 端点，light/dark/auto 三模式
113. `[S]` 插件沙箱资源预算 — cpu_ms_limit/memory_mb_limit/io_ops_limit 软限制
114. `[M]` 对话质量趋势仪表盘 — /api/quality-trend 聚合 self_score 历史
115. `[L]` 自我演化日志与回滚 — EvolutionJournal + rollback_to(checkpoint_id)
116. `[M]` 学习驱动的知识图谱扩展 — knowledge_frontier() 识别理解薄弱领域
117. `[S]` 插件冲突检测器 — detect_conflicts() 检查 hook 优先级/状态竞争
118. `[M]` 人格漂移可视化 API — GET /personality/drift-map 返回漂移轨迹 JSON
119. `[S]` 自评分数异常自动复盘 — 连续 3 轮 <0.4 时触发 introspection_hook
120. `[M]` 插件热卸载与状态清理 — unload_plugin() 清理 hook/定时器/共享状态

## 呼吸感 / 秘密状态 / 关系年龄

121. `[M]` 对话呼吸节奏引擎 — BreathingRhythmController 动态调整回复长短交替模式
122. `[S]` 呼吸节奏的快慢时钟 — tempo_clock 追踪每分钟交互次数滑动窗口
123. `[L]` 秘密状态层 — hidden_state.py 维护用户不可见但影响行为的内部状态
124. `[M]` 秘密泄露机制 — 按 leak_probability 产生微妙行为偏移
125. `[M]` 关系年龄计算器 — relationship_age 属性 + infant/young/mature/deep 四阶段
126. `[L]` 关系年龄行为分化 — 不同阶段调整 boundary_permeability/expression_drive
127. `[S]` 新关系的"试探"模式 — probing_mode 嵌入轻量试探快速建立画像
128. `[M]` 秘密状态的自我觉察 — 超过 TTL 80% 时隐晦暗示秘密存在
129. `[S]` 对话呼吸的"屏息"检测 — 用户停顿超正常 2 倍时标记，下次语气更轻柔
130. `[M]` 关系年龄的"加速器" — 高强度互动加速关系年龄推进

## 矛盾检测 / 对话重力 / 情绪传染

131. `[L]` 自我矛盾检测引擎 — contradiction_detector.py 对比当前意图与历史立场
132. `[M]` 矛盾自我修正策略 — 低级静默调整/中级自然过渡/高级主动承认
133. `[S]` 矛盾容忍度的人格关联 — inner_order 高→容忍度低→更快修正
134. `[L]` 话题重力场 — topic_gravity.py 维护话题引力图，高 mass 话题"拉回"对话
135. `[M]` 重力场的衰减与强化 — 时间半衰期衰减 + 被拉回后 mass 增加
136. `[M]` 情绪传染方向性模型 — influence_ratio 计算谁影响谁更多
137. `[S]` 情绪传染的抵抗力 — 强情绪状态时不容易被轻微波动改变
138. `[M]` 话题重力可视化 — /api/topic-gravity + 力导向图面板
139. `[S]` "故意矛盾"豁免 — 调皮/玩梗/反讽标记为 playful_inconsistency
140. `[M]` 情绪传染的延迟效应 — 1-3 轮渗透期，突然变化需更长渗透

## 第一印象 / 关系弹性 / 沉默 / 记忆温度

141. `[L]` 第一印象锚定系统 — first_impression 永久影响 set_point 偏移
142. `[M]` 第一印象的"修正难度" — 前 7 天不衰减，30 天后稳定残留 15-25%
143. `[L]` 关系弹性模型 — relational_resilience.py 计算关系能承受的冲击强度
144. `[M]` 关系弹性的修复与硬化 — 成功修复→弹性增加；未修复→永久脆化
145. `[M]` 主动沉默引擎 — deliberate_silence 决策：受伤/消化/给空间时主动延迟
146. `[S]` 沉默的语义类型 — thinking/hurt/respectful/dramatic 四种，不同破冰方式
147. `[M]` 记忆温度系统 — hot(24h)/warm(7d)/cold(30d+) 三级温度
148. `[S]` 记忆温度的使用差异 — hot 直接引用/warm 间接提及/cold 模糊回忆
149. `[M]` 记忆的"突然升温" — cold 记忆与当前强关联时骤升到 hot
150. `[S]` 沉默后的"破冰"模板 — 根据沉默类型选择破冰方式

## 风格镜像 / 仪式 / 情绪惯性 / 自我叙事 / 边界协商

151. `[L]` 对话风格镜像引擎 — style_mirror.py 分析用户语言风格，输出 mirror_vector
152. `[M]` 反镜像的策略性使用 — 用户低落时明快风格提振，过于兴奋时沉稳锚定
153. `[M]` 关系仪式注册表 — rituals 字典记录固定问候/告别/特定时间互动
154. `[S]` 仪式的"缺席感" — 仪式时间用户未出现时产生 ritual_absence 事件
155. `[M]` 情绪惯性模型 — 情绪"质量"随持续时间增加，单次事件须超阈值才能改变方向
156. `[S]` 情绪惯性的"突破"事件 — impulse 突破 inertia 时情绪变化更剧烈
157. `[L]` 自我叙事引擎 — self_narrative.py 维护"我是谁"的内部叙事
158. `[M]` 自我叙事的冲突与重写 — 新经历与叙事矛盾时触发重写，expression_drive 波动
159. `[L]` 动态边界协商系统 — boundary_negotiation.py 通过对话信号动态协商边界
160. `[M]` 边界的"试探-退回"循环 — 轻微试探→正面反应微调/负面反应退回
