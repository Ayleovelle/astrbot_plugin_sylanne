# Sylanne Embodiment WebUI — 前端交接文档

## 概述

单文件 SPA（`index.html`），包含登录流程和仪表盘，无页面跳转。设计语言：Atompunk × Cassette Futurism × Bio-tech（明日方舟莱茵生命风格）。

**核心布局理念**：中心脊柱线（`left:50%`）贯穿全程，内容面板分列两侧。

---

## 文件结构

```
UI/
├── index.html              # 唯一入口，全部 CSS/JS 内联
├── assets/
│   ├── sylanne-logo.svg    # SVG logo（脊柱+脉冲+弧线+数据条）
│   ├── sylanne-pet.webp    # 角色 spritesheet（1536×1872, 8col×12row, 192×156/帧）
│   ├── pet-frames/         # 已切好的 79 帧（未启用）
│   └── pet-contact-sheet.png  # 帧总览图（调试用）
└── HANDOFF.md              # 本文档
```

---

## 设计规范

| 项目 | 值 |
|------|-----|
| 功能色 | `--accent: #B88A9E` |
| 氛围色 | `--glow: rgba(208,173,199,0.08)` / `--atmosphere: #D0ADC7` |
| 标题字体 | Rajdhani 500/700 |
| 数据字体 | JetBrains Mono 400/700 |
| 字体加载 | `display=block`（防止 swap 导致布局跳动） |
| 禁用字体 | Inter, Roboto, 系统无衬线 |
| 暗色背景 | `#1a1a1a` |
| 亮色背景 | `#f0ece4` |

### 颜色规则
- `--accent` 用于交互元素（按钮、高亮、脊柱线、节点）
- `--glow/atmosphere` 仅用于背景氛围（卡片微光、hover 光晕）
- 不要用 `#D0ADC7` 做前景文字或按钮色

---

## DOM 结构

```
body
├── .fixed-spine#fixedSpine        ← 永久存在的中心脊柱线
│   ├── .spine-line                ← 竖线本体
│   └── .spine-node ×6            ← 导航节点（data-page 属性）
│
├── #loginSection                  ← 登录区域（认证后隐藏）
│   ├── #networkCanvas             ← 粒子连线背景动画
│   ├── .deco-tl / .deco-bl       ← 角落装饰文字
│   ├── #p1 .phase.active         ← Boot Sequence（1.2s 后消失）
│   ├── #p3 .phase                ← 登录表单
│   └── #p4 .phase                ← 验证动画（圆环+勾/叉）
│
├── #dashboardSection              ← 仪表盘（初始 display:none）
│   └── .app-layout
│       ├── .app-header            ← 顶栏（session ID、主题/语言切换、状态点）
│       ├── .content-viewport      ← 垂直滑动视口
│       │   └── .content-slider    ← translateY 切页
│       │       ├── [data-page="monitor"]     ← 监控页
│       │       ├── [data-page="spine"]       ← 计算脊柱页（L1-L7 可视化）
│       │       ├── [data-page="config"]      ← 配置页（对应 _conf_schema.json）
│       │       ├── [data-page="logs"]        ← 日志页
│       │       ├── [data-page="memory"]      ← 记忆页
│       │       └── [data-page="personality"] ← 人格页
│       └── .app-footer            ← 底栏
│
└── .meltdown-modal#meltdownModal  ← 记忆熔毁确认弹窗
```

---

## 页面切换机制

- 6 个页面垂直堆叠，每页 `height:100%`
- 切换通过 `navigateTo(page)` → `contentSlider.style.transform = translateY(-${idx * 100}%)`
- 脊柱节点点击触发导航，当前页节点高亮（`.active`）
- 每页分为 `.page-left` 和 `.page-right` 两栏，脊柱线在中间

---

## 登录 → 仪表盘过渡

1. Boot Sequence 显示 1.2s
2. 淡入登录表单（canvas 背景降低透明度）
3. 用户输入 token → `doLogin()` → 验证动画
4. 验证成功后：
   - 脊柱线 `clip-path` 动画从上到下展开（`.active` 类）
   - loginSection 隐藏
   - dashboardSection 显示（先加 `.awaiting-entrance` 隐藏卡片）
   - 200ms 后节点出现 + header/footer 滑入 + 卡片从中心弹出
5. 整个过程脊柱线 DOM 不销毁不重建

### 跳过登录
有 token 或 `window.AstrBotPluginPage` 时直接调用 `skipLoginShowDashboard()`。

---

## i18n 系统

- `data-lang` 属性控制（`zh` / `en`）
- HTML 中用 hex entities 写中文（`&#x76D1;&#x63A7;`），JS 中只用英文
- `t('key')` 函数返回当前语言的字符串
- 切换按钮在 header 右侧

---

## 关键 JS 函数

| 函数 | 作用 |
|------|------|
| `initNetworkCanvas()` | 启动登录背景粒子动画 |
| `doLogin()` | 发起认证请求 |
| `transitionToDashboard()` | 登录成功后的过渡动画序列 |
| `skipLoginShowDashboard()` | 有 token 时跳过登录 |
| `navigateTo(page)` | 页面切换（垂直滑动） |
| `startDashboard()` | 渲染所有页面卡片内容 |
| `toggleTheme()` | 暗/亮模式切换 |
| `toggleLang()` | 中/英切换 |
| `openMeltdown()` / `confirmMeltdown()` | 记忆熔毁流程（5秒倒计时可取消） |
| `showToast(msg)` | 实验室风格消息提示 |

---

## 配置页

配置项从 `_conf_schema.json` 映射而来。每个配置组渲染为一张卡片，字段类型支持：
- `text` → input
- `number` → input[type=number]（隐藏了原生 spinner）
- `bool` → toggle switch
- `select` → 自定义 accordion 下拉（非浮动，展开时下方内容下推）
- `provider` → 带手动输入的 provider 选择器

保存按钮触发 toast 提示。

---

## Provider 选择器

accordion 风格（不是浮动 dropdown）：
1. 点击按钮展开选项列表（`max-height` 过渡）
2. 选项包含名称 + model ID 小字
3. 底部有"手动输入"选项，展开后显示 input
4. 选中后折叠，按钮文字更新

**为什么不用浮动下拉**：卡片有 `backdrop-filter` 会创建 stacking context，导致 `position:absolute/fixed` 的菜单被裁切。

---

## Meltdown 确认

1. 弹出模态框，生成 4 位随机验证码
2. 用户输入验证码后点击确认
3. 按钮进入 5 秒倒计时状态（显示剩余秒数）
4. 倒计时期间可点击取消（abort）
5. 倒计时结束执行操作

---

## 验证动画（登录）

- SVG 圆环：`stroke-dasharray` 从缺口到闭合
- 闭合方式：尾端追上前端（非均匀缩小）
- 圆环持续旋转，内部 ✓/✗ 图标保持正向（`counter-rotate`）
- 成功：圆环闭合 → 显示 ✓ → 1.2s 后过渡到仪表盘
- 失败：显示 ✗ → 抖动 → 返回登录表单

---

## 计算脊柱页（Spine）可视化

每层（L1-L7）有独立的静态可视化，展示上一次计算结果：
- L1 Sensory: 输入信号网格
- L2 Affect: 情感向量雷达图
- L3 Cognitive: 认知处理流
- L4 Social: 社交场域图
- L5 Predictive: 预测编码误差
- L6 Integration: 整合热力图
- L7 Expression: 输出生成

**重要**：这些可视化是数据驱动的静态展示，不是无限循环动画。

---

## 后端对接要点

### API 端点（需要实现）

```
POST /api/login          ← body: { token }，返回 { ok, session_id }
GET  /api/status         ← 返回运行状态、层级数据
GET  /api/logs           ← 返回日志列表
GET  /api/memory         ← 返回记忆池数据
POST /api/config         ← 保存配置
POST /api/meltdown       ← 执行记忆熔毁
GET  /api/personality    ← 返回人格参数
```

### 当前 mock 行为

- `doLogin()`: preview 模式下任意 token 都通过
- `startDashboard()`: 用硬编码假数据渲染卡片
- 状态点（`#statusDot`）: 固定绿色

### 接入时需要替换的位置

搜索 `isPreview` 和 `// TODO` 找到所有 mock 分支。preview 模式（`file://` 或无 hostname）用于本地预览，生产环境应走真实 API。

---

## 主题系统

- localStorage key: `sylanne_theme`
- `<head>` 内有 inline script 在 CSS 渲染前读取并设置 `data-theme`，防止闪烁
- CSS 变量在 `:root` 和 `[data-theme="light"]` 中定义
- 切换时 `body` 有 `transition:background .4s ease,color .4s ease`

---

## 已知限制 / 未完成

1. **宠物系统**：帧已切好（`assets/pet-frames/`，79帧，192×156），代码已移除。如需恢复，spritesheet 实际是 8col×12row 而非 8×4。
2. **实时数据**：所有数据目前是 mock，需要 WebSocket 或轮询接入。
3. **移动端适配**：基本响应式但未精细调优。
4. **无障碍**：基础 semantic HTML，未做 ARIA 标注。

---

## 注意事项

- **JS 中不要写中文字符串**——会因编码问题乱码。中文一律用 HTML hex entities 或 i18n 系统。
- **不要给卡片加 `backdrop-filter`**——会破坏内部元素的 stacking context。
- **动画不要无限循环**——脊柱页可视化是静态快照，不是实时动画。
- **字体只用 Rajdhani + JetBrains Mono**——其他字体会破坏设计语言。
