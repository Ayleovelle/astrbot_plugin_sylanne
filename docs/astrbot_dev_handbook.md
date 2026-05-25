# AstrBot 插件开发手册 (Sylanne-Embodiment 专用)

> 基于 AstrBot v4.x 官方文档编译，供 Sylanne-Embodiment 项目开发参考。
> 文档源: https://docs.astrbot.app/dev/
> 编译日期: 2026-05-25

---

## 1. 开发原则

AstrBot 官方要求所有插件遵守以下原则:

- 功能需经过测试
- 需包含良好的注释
- **持久化数据请存储于 `data` 目录下，而非插件自身目录**，防止更新/重装插件时数据被覆盖
- 良好的错误处理机制，不要让插件因一个错误而崩溃
- 在进行提交前，请使用 ruff 工具格式化代码
- **不要使用 `requests` 库**进行网络请求，使用 `aiohttp`、`httpx` 等异步库
- 如果是对某个插件进行功能扩增，请优先给那个插件提交 PR

### 插件命名规范

- 推荐以 `astrbot_plugin_` 开头
- 不能包含空格
- 保持全部字母小写
- 尽量简短

---

## 2. 插件基础结构

### 目录结构

```
astrbot_plugin_xxx/
  main.py                 # 必须，插件入口（类名任意，继承 Star）
  metadata.yaml           # 必须，插件元数据
  _conf_schema.json       # 可选，配置 Schema
  requirements.txt        # 可选，第三方依赖
  logo.png                # 可选，插件 Logo (256x256, 1:1)
```

### metadata.yaml

```yaml
name: astrbot_plugin_sylanne
display_name: "Sylanne Embodiment"
description: "Soulful Sylanne 4.0 情感具身插件"
author: "your_name"
version: "1.0.0"
repo: "https://github.com/xxx/astrbot_plugin_sylanne"
support_platforms:        # 可选，声明支持的平台
  - aiocqhttp
  - telegram
astrbot_version: ">=4.16,<5"  # 可选，声明 AstrBot 版本范围
```

### 最小实例 main.py

```python
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger

class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("helloworld")
    async def helloworld(self, event: AstrMessageEvent):
        '''这是一个 hello world 指令'''
        user_name = event.get_sender_name()
        yield event.plain_result(f"Hello, {user_name}!")

    async def terminate(self):
        '''插件被卸载/停用时调用'''
        pass
```

### 关键规则

- 插件类**必须继承 `Star`**
- 插件入口文件**必须命名为 `main.py`**
- Handler 前两个参数必须为 `self` 和 `event`
- 使用 `from astrbot.api import logger` 而非 `logging` 模块
- `Context` 类用于与 AstrBot Core 交互

---

## 3. 事件监听与消息处理

### 导入

```python
from astrbot.api.event import filter, AstrMessageEvent
```

### AstrMessageEvent 核心属性

| 属性/方法 | 说明 |
|-----------|------|
| `event.message_str` | 纯文本消息字符串 |
| `event.message_obj` | AstrBotMessage 对象 |
| `event.get_sender_name()` | 发送者昵称 |
| `event.get_sender_id()` | 发送者 ID |
| `event.get_group_id()` | 群组 ID（私聊为空） |
| `event.get_platform_name()` | 平台名称 |
| `event.unified_msg_origin` | 会话唯一标识（UMO） |
| `event.stop_event()` | 停止事件传播 |

### AstrBotMessage 结构

```python
class AstrBotMessage:
    type: MessageType       # GROUP_MESSAGE / PRIVATE_MESSAGE
    self_id: str            # 机器人 ID
    session_id: str         # 会话 ID
    message_id: str         # 消息 ID
    group_id: str           # 群组 ID
    sender: MessageMember   # 发送者
    message: List[BaseMessageComponent]  # 消息链
    message_str: str        # 纯文本
    raw_message: object     # 平台原始消息
    timestamp: int          # 时间戳
```

### 指令注册

```python
@filter.command("hello")
async def hello(self, event: AstrMessageEvent):
    '''指令描述（会被解析展示给用户）'''
    yield event.plain_result("Hello!")
```

### 带参指令

```python
@filter.command("add")
async def add(self, event: AstrMessageEvent, a: int, b: int):
    # /add 1 2 -> 结果是: 3
    yield event.plain_result(f"结果是: {a + b}")
```

### 指令组

```python
@filter.command_group("math")
def math(self):
    pass

@math.command("add")
async def add(self, event: AstrMessageEvent, a: int, b: int):
    yield event.plain_result(f"结果是: {a + b}")
```

嵌套指令组使用 `.group()` 而非 `.command_group()`:

```python
@math.group("calc")
def calc():
    pass

@calc.command("add")
async def add(self, event: AstrMessageEvent, a: int, b: int):
    yield event.plain_result(f"结果是: {a + b}")
```

### 指令别名

```python
@filter.command("help", alias={'帮助', 'helpme'})
async def help(self, event: AstrMessageEvent):
    yield event.plain_result("帮助信息")
```

### 事件类型过滤

```python
# 接收所有消息
@filter.event_message_type(filter.EventMessageType.ALL)
async def on_all(self, event: AstrMessageEvent):
    yield event.plain_result("收到消息")

# 仅私聊
@filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
async def on_private(self, event: AstrMessageEvent):
    yield event.plain_result("私聊消息")

# 仅群聊
@filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
async def on_group(self, event: AstrMessageEvent):
    yield event.plain_result("群聊消息")
```

### 平台过滤

```python
@filter.platform_adapter_type(
    filter.PlatformAdapterType.AIOCQHTTP | filter.PlatformAdapterType.QQOFFICIAL
)
async def on_qq(self, event: AstrMessageEvent):
    yield event.plain_result("QQ 平台消息")
```

`PlatformAdapterType` 枚举: `AIOCQHTTP`, `QQOFFICIAL`, `GEWECHAT`, `ALL`

### 管理员权限

```python
@filter.permission_type(filter.PermissionType.ADMIN)
@filter.command("admin_cmd")
async def admin_cmd(self, event: AstrMessageEvent):
    pass
```

### 多过滤器组合（AND 逻辑）

```python
@filter.command("helloworld")
@filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
async def helloworld(self, event: AstrMessageEvent):
    yield event.plain_result("你好！")
```

### 事件钩子

> 事件钩子**不能**与 command/command_group/event_message_type 等一起使用。
> 钩子中**不能使用 yield**，需用 `await event.send()` 发送消息。

```python
# Bot 初始化完成 (v3.4.34+)
@filter.on_astrbot_loaded()
async def on_loaded(self):
    print("AstrBot 初始化完成")

# 等待 LLM 请求时（锁外触发）
@filter.on_waiting_llm_request()
async def on_waiting(self, event: AstrMessageEvent):
    await event.send("正在思考...")

# LLM 请求前（可修改 ProviderRequest）
@filter.on_llm_request()
async def on_req(self, event: AstrMessageEvent, req: ProviderRequest):
    req.system_prompt += "\n自定义提示"

# LLM 响应后（可修改 LLMResponse）
@filter.on_llm_response()
async def on_resp(self, event: AstrMessageEvent, resp: LLMResponse):
    print(resp.completion_text)

# 发送消息前（装饰消息链）
@filter.on_decorating_result()
async def on_decorate(self, event: AstrMessageEvent):
    result = event.get_result()
    chain = result.chain
    chain.append(Plain("!"))

# 发送消息后
@filter.after_message_sent()
async def after_sent(self, event: AstrMessageEvent):
    pass
```

### 优先级

```python
@filter.command("helloworld", priority=1)  # 默认 0，数字越大越先执行
async def helloworld(self, event: AstrMessageEvent):
    yield event.plain_result("Hello!")
```

### 控制事件传播

```python
@filter.command("check")
async def check(self, event: AstrMessageEvent):
    if not self.check():
        yield event.plain_result("检查失败")
        event.stop_event()  # 后续所有 handler 和 LLM 调用都不会执行
```

---

## 4. 消息发送

### 被动消息（yield）

```python
@filter.command("hello")
async def hello(self, event: AstrMessageEvent):
    yield event.plain_result("Hello!")
    yield event.plain_result("你好！")
    yield event.image_result("path/to/image.jpg")
    yield event.image_result("https://example.com/image.jpg")
```

### 主动消息（send_message）

```python
from astrbot.api.event import MessageChain

@filter.command("save")
async def save(self, event: AstrMessageEvent):
    umo = event.unified_msg_origin  # 存储此字符串，后续可用于主动推送
    # ... 稍后在定时任务中:
    chain = MessageChain().message("定时提醒!")
    await self.context.send_message(umo, chain)
```

> `unified_msg_origin` 是会话唯一 ID，AstrBot 据此找到正确的平台和会话。

### 富媒体消息（消息链）

```python
import astrbot.api.message_components as Comp

@filter.command("rich")
async def rich(self, event: AstrMessageEvent):
    chain = [
        Comp.At(qq=event.get_sender_id()),
        Comp.Plain("来看这个图："),
        Comp.Image.fromURL("https://example.com/image.jpg"),
        Comp.Image.fromFileSystem("path/to/image.jpg"),
        Comp.Plain("这是一个图片。")
    ]
    yield event.chain_result(chain)
```

### 其他消息类型

```python
# 文件
Comp.File(file="path/to/file.txt", name="file.txt")

# 语音（仅 wav 格式）
Comp.Record(file="path/to/record.wav", url="path/to/record.wav")

# 视频
Comp.Video.fromFileSystem(path="test.mp4")
Comp.Video.fromURL(url="https://example.com/video.mp4")
```

### 合并转发消息（仅 OneBot v11）

```python
from astrbot.api.message_components import Node, Plain, Image

node = Node(
    uin=905617992,
    name="Soulter",
    content=[Plain("hi"), Image.fromFileSystem("test.jpg")]
)
yield event.chain_result([node])
```

---

## 5. 插件配置

### 配置 Schema 定义

在插件目录下创建 `_conf_schema.json`:

```json
{
  "token": {
    "description": "Bot Token",
    "type": "string"
  },
  "max_retries": {
    "description": "最大重试次数",
    "type": "int",
    "default": 3,
    "hint": "设置为 0 表示不重试"
  },
  "enable_debug": {
    "description": "启用调试模式",
    "type": "bool",
    "default": false
  },
  "nested_config": {
    "description": "嵌套配置示例",
    "type": "object",
    "items": {
      "name": {
        "description": "名称",
        "type": "string"
      },
      "timeout": {
        "description": "超时时间",
        "type": "int",
        "default": 60
      }
    }
  }
}
```

### Schema 字段说明

| 字段 | 必填 | 说明 |
| ---- | ---- | ---- |
| `type` | 是 | 支持: `string`, `text`, `int`, `float`, `bool`, `object`, `list`, `dict`, `template_list`, `file` |
| `description` | 否 | 配置描述 |
| `hint` | 否 | 悬浮提示信息 |
| `obvious_hint` | 否 | 是否醒目显示 hint |
| `default` | 否 | 默认值 |
| `items` | 否 | object 类型的子 Schema |
| `invisible` | 否 | 是否隐藏（不在面板显示） |
| `options` | 否 | 下拉列表可选项，如 `["chat", "agent"]` |
| `editor_mode` | 否 | 启用代码编辑器 (v3.5.10+) |
| `editor_language` | 否 | 代码语言，默认 `json` |
| `editor_theme` | 否 | `vs-light`(默认) 或 `vs-dark` |
| `_special` | 否 | v4.0.0+，支持 `select_provider`, `select_provider_tts`, `select_provider_stt`, `select_persona` |
| `file_types` | 否 | file 类型允许的扩展名列表 (v4.13.0+) |

### file 类型 (v4.13.0+)

```json
{
  "demo_files": {
    "type": "file",
    "description": "上传文件",
    "default": [],
    "file_types": ["pdf", "docx"]
  }
}
```

### 在插件中读取配置

```python
from astrbot.api import AstrBotConfig

class MyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config  # AstrBotConfig 继承自 Dict
        print(self.config["token"])
        # self.config.save_config()  # 保存配置
```

配置文件实体保存在 `data/config/<plugin_name>_config.json`。

### 配置自动更新

发布新版本更新 Schema 时，AstrBot 会自动为缺失的配置项添加默认值、移除不存在的配置项。

---

## 6. 插件页面（WebUI）

> **注意**: 截至 v4.x 文档，AstrBot 尚未提供官方的插件自定义页面 API（plugin-pages）。
> 用户 URL 中的 `plugin-pages.html` 和 `plugin-i18n.html` 页面在当前文档仓库中不存在。

### 当前可用的 WebUI 集成方式

1. **配置面板**: 通过 `_conf_schema.json` 自动生成 WebUI 配置界面
2. **`_special` 字段**: 使用 `select_provider`、`select_persona` 等内置选择器
3. **metadata.yaml 展示**: `display_name`、`support_platforms` 等字段会在 WebUI 插件页展示

### Sylanne 当前方案 vs 推荐方案

| 功能 | Sylanne 当前实现 | 推荐替代 |
| ---- | ---- | ---- |
| WebUI Dashboard | 自建 HTTP Server (`webui_server.py`) | 暂无官方替代，当前方案可保留 |
| 配置管理 | 自定义 config.py | 应迁移到 `_conf_schema.json` |

---

## 7. AI/LLM 接口

### 获取当前会话的聊天模型 ID (v4.5.7+)

```python
umo = event.unified_msg_origin
provider_id = await self.context.get_current_chat_provider_id(umo=umo)
```

### 调用大模型 (v4.5.7+)

```python
llm_resp = await self.context.llm_generate(
    chat_provider_id=provider_id,
    prompt="Hello, world!",
)
print(llm_resp.completion_text)
```

### 定义 Tool（dataclass 方式）

```python
from pydantic import Field
from pydantic.dataclasses import dataclass
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext

@dataclass
class MyTool(FunctionTool[AstrAgentContext]):
    name: str = "my_tool"
    description: str = "工具描述"
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "查询内容",
                },
            },
            "required": ["query"],
        }
    )

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        return f"结果: {kwargs['query']}"
```

### 注册 Tool 到 AstrBot

```python
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # v4.5.1+
        self.context.add_llm_tools(MyTool(), AnotherTool())
```

### 定义 Tool（装饰器方式）

```python
@filter.llm_tool(name="get_weather")
async def get_weather(self, event: AstrMessageEvent, location: str) -> MessageEventResult:
    '''获取天气信息。

    Args:
        location(string): 地点
    '''
    resp = self.get_weather_from_api(location)
    yield event.plain_result("天气信息: " + resp)
```

参数类型支持: `string`, `number`, `object`, `boolean`, `array`, `array[string]` (v4.5.7+)

### 调用 Agent (v4.5.7+)

```python
from astrbot.core.agent.tool import ToolSet

llm_resp = await self.context.tool_loop_agent(
    event=event,
    chat_provider_id=prov_id,
    prompt="执行任务描述",
    tools=ToolSet([MyTool()]),
    max_steps=30,
    tool_call_timeout=60,
)
print(llm_resp.completion_text)
```

### Multi-Agent 模式

将子 Agent 定义为 FunctionTool，在其 `call()` 中递归调用 `tool_loop_agent()`:

```python
@dataclass
class SubAgent(FunctionTool[AstrAgentContext]):
    name: str = "sub_agent"
    description: str = "子智能体"
    # ...

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        ctx = context.context.context
        event = context.context.event
        llm_resp = await ctx.tool_loop_agent(
            event=event,
            chat_provider_id=await ctx.get_current_chat_provider_id(event.unified_msg_origin),
            prompt=kwargs["query"],
            tools=ToolSet([WeatherTool()]),
            max_steps=30,
        )
        return llm_resp.completion_text
```

### 对话管理器

```python
from astrbot.core.conversation_mgr import Conversation

conv_mgr = self.context.conversation_manager
uid = event.unified_msg_origin

# 获取当前对话 ID
curr_cid = await conv_mgr.get_curr_conversation_id(uid)

# 获取对话对象
conversation = await conv_mgr.get_conversation(uid, curr_cid)

# 新建对话
new_cid = await conv_mgr.new_conversation(uid)

# 切换对话
await conv_mgr.switch_conversation(uid, conversation_id)

# 删除对话
await conv_mgr.delete_conversation(uid, conversation_id)

# 获取所有对话
conversations = await conv_mgr.get_conversations(uid)

# 更新对话
await conv_mgr.update_conversation(uid, curr_cid, history=[...], title="新标题")
```

### 添加 LLM 记录到对话

```python
from astrbot.core.agent.message import AssistantMessageSegment, UserMessageSegment, TextPart

user_msg = UserMessageSegment(content=[TextPart(text="hi")])
llm_resp = await self.context.llm_generate(
    chat_provider_id=provider_id,
    contexts=[user_msg],
)
await conv_mgr.add_message_pair(
    cid=curr_cid,
    user_message=user_msg,
    assistant_message=AssistantMessageSegment(
        content=[TextPart(text=llm_resp.completion_text)]
    ),
)
```

### 人格设定管理器

```python
persona_mgr = self.context.persona_manager

# 获取人格
persona = persona_mgr.get_persona("persona_id")

# 获取所有人格
all_personas = persona_mgr.get_all_personas()

# 创建人格
new_persona = persona_mgr.create_persona(
    persona_id="my_persona",
    system_prompt="你是一个...",
    begin_dialogs=["你好", "你好呀！"],  # 偶数条，user/assistant 交替
    tools=None,  # None=全部工具, []=禁用全部
)

# 更新人格
persona_mgr.update_persona("my_persona", system_prompt="新提示词")

# 删除人格
persona_mgr.delete_persona("my_persona")

# 获取默认人格（v3 格式）
default = persona_mgr.get_default_persona_v3(umo=event.unified_msg_origin)
```

---

## 8. 数据持久化（Storage）

### 简单 KV 存储 (v4.9.2+)

AstrBot 提供基于插件维度的 KV 存储，每个插件有独立的存储空间。

```python
class MyPlugin(Star):
    @filter.command("hello")
    async def hello(self, event: AstrMessageEvent):
        # 写入
        await self.put_kv_data("greeted", True)

        # 读取（第二个参数为默认值）
        greeted = await self.get_kv_data("greeted", False)

        # 删除
        await self.delete_kv_data("greeted")
```

### 大文件存储规范

大文件应存储于 `data/plugin_data/{plugin_name}/` 目录下:

```python
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

plugin_data_path = get_astrbot_data_path() / "plugin_data" / self.name
# self.name 在 v4.9.2+ 可用
```

---

## 9. 会话控制

### 基本用法

用于实现多轮对话场景（如成语接龙、问答游戏等）。

```python
import astrbot.api.message_components as Comp
from astrbot.core.utils.session_waiter import session_waiter, SessionController

@filter.command("game")
async def game(self, event: AstrMessageEvent):
    yield event.plain_result("请输入内容~")

    @session_waiter(timeout=60, record_history_chains=False)
    async def waiter(controller: SessionController, event: AstrMessageEvent):
        text = event.message_str

        if text == "退出":
            await event.send(event.plain_result("已退出"))
            controller.stop()
            return

        # 发送回复（不能用 yield）
        result = event.make_result()
        result.chain = [Comp.Plain(f"你说了: {text}")]
        await event.send(result)

        # 保持会话，重置超时
        controller.keep(timeout=60, reset_timeout=True)

    try:
        await waiter(event)
    except TimeoutError:
        yield event.plain_result("超时了！")
    finally:
        event.stop_event()
```

### SessionController API

| 方法 | 说明 |
| ---- | ---- |
| `controller.keep(timeout, reset_timeout=True)` | 保持会话。reset_timeout=True 重置计时器 |
| `controller.stop()` | 立即结束会话 |
| `controller.get_history_chains()` | 获取历史消息链（需 record_history_chains=True） |

### 自定义会话 ID 算子

默认按 `sender_id` 区分会话。可自定义为按群区分:

```python
from astrbot.core.utils.session_waiter import SessionFilter, SessionController

class GroupFilter(SessionFilter):
    def filter(self, event: AstrMessageEvent) -> str:
        return event.get_group_id() if event.get_group_id() else event.unified_msg_origin

await waiter(event, session_filter=GroupFilter())
```

---

## 10. 其他工具

### 文转图（HTML 渲染）

```python
# 简单文转图
@filter.command("image")
async def to_image(self, event: AstrMessageEvent, text: str):
    url = await self.text_to_image(text)
    yield event.image_result(url)
```

### 自定义 HTML 模板渲染

```python
TMPL = '''
<div style="font-size: 32px;">
<h1>Todo List</h1>
<ul>
{% for item in items %}
    <li>{{ item }}</li>
{% endfor %}
</ul>
</div>
'''

@filter.command("todo")
async def todo(self, event: AstrMessageEvent):
    url = await self.html_render(TMPL, {"items": ["吃饭", "睡觉", "写代码"]})
    yield event.image_result(url)
```

渲染选项（Playwright screenshot API）:
- `timeout`: 截图超时
- `type`: "jpeg" 或 "png"
- `quality`: JPEG 质量
- `omit_background`: 透明背景（仅 PNG）
- `full_page`: 截整页（默认 True）
- `scale`: "css" 或 "device"

> 在线编辑器: https://t2i-playground.astrbot.app/

### 获取消息平台实例

```python
from astrbot.api.platform import AiocqhttpAdapter

platform = self.context.get_platform(filter.PlatformAdapterType.AIOCQHTTP)
assert isinstance(platform, AiocqhttpAdapter)
```

### 调用 QQ 协议端 API

```python
if event.get_platform_name() == "aiocqhttp":
    from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
    assert isinstance(event, AiocqhttpMessageEvent)
    client = event.bot
    ret = await client.api.call_action('delete_msg', message_id=event.message_obj.message_id)
```

### 获取所有已加载插件

```python
plugins = self.context.get_all_stars()  # 返回 StarMetadata 列表
```

### 获取所有已加载平台

```python
from astrbot.api.platform import Platform
platforms = self.context.platform_manager.get_insts()  # List[Platform]
```

---

## 11. 发布流程

1. 将插件代码推送到 GitHub 仓库
2. 前往 [AstrBot 插件市场](https://plugins.astrbot.app)
3. 点击右下角 `+` 按钮
4. 填写基本信息、作者信息、仓库信息
5. 点击 `提交到 GitHub`，会导航到 AstrBot 仓库的 Issue 页面
6. 确认信息后点击 `Create` 提交

---

## 12. OpenAPI (v4.18.0+)

AstrBot 提供基于 API Key 的 HTTP API。

### 认证方式

```http
Authorization: Bearer abk_xxx
```

或:

```http
X-API-Key: abk_xxx
```

### Scope 权限

| Scope | 可访问接口 |
| ---- | ---- |
| `chat` | `POST /api/v1/chat`, `GET /api/v1/chat/sessions` |
| `config` | `GET /api/v1/configs` |
| `file` | `POST /api/v1/file` |
| `im` | `POST /api/v1/im/message`, `GET /api/v1/im/bots` |

### 对话接口

```bash
curl -N 'http://localhost:6185/api/v1/chat' \
  -H 'Authorization: Bearer abk_xxx' \
  -H 'Content-Type: application/json' \
  -d '{"message":"Hello","username":"alice"}'
```

支持 SSE 流式返回。`username` 为必填参数。

### message 字段格式

支持纯文本或消息段数组:

```json
{
  "message": [
    { "type": "plain", "text": "请看这个文件" },
    { "type": "file", "attachment_id": "uuid-here" }
  ]
}
```

消息段类型: `plain`, `reply`, `image`, `record`, `file`, `video`

### IM 主动消息

```json
POST /api/v1/im/message
{
  "umo": "webchat:FriendMessage:openapi_probe",
  "message": [
    { "type": "plain", "text": "主动消息" }
  ]
}
```

---

## 13. 平台适配器开发

AstrBot 支持以插件形式接入自定义平台适配器。

### 核心步骤

1. 创建适配器类，继承 `Platform`
2. 使用 `@register_platform_adapter` 装饰器注册
3. 实现 `run()`、`send_by_session()`、`meta()` 方法
4. 创建事件类，继承 `AstrMessageEvent`，实现 `send()` 方法
5. 在 `main.py` 的 `__init__` 中导入适配器模块

```python
from astrbot.api.platform import Platform, AstrBotMessage, MessageMember, PlatformMetadata, MessageType
from astrbot.api.platform import register_platform_adapter

@register_platform_adapter("my_platform", "我的平台适配器", default_config_tmpl={
    "token": "your_token",
})
class MyPlatformAdapter(Platform):
    def __init__(self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue):
        super().__init__(event_queue)
        self.config = platform_config

    async def run(self):
        # 主循环，监听消息
        pass

    async def send_by_session(self, session, message_chain):
        await super().send_by_session(session, message_chain)

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata("my_platform", "我的平台适配器")
```

---

## 14. Sylanne-Embodiment 迁移建议

基于以上 AstrBot 官方 API，以下是 Sylanne 项目当前**应该使用但尚未使用**的接口:

### 14.1 应迁移: KV 存储 API

**当前**: `sylanne_alpha/runtime.py` 使用自定义文件 I/O 持久化状态

**推荐**: 使用 AstrBot 内置 KV 存储

```python
# 替代自定义文件读写
await self.put_kv_data("body_state", state_dict)
state = await self.get_kv_data("body_state", default_state)
```

**优势**: 插件维度隔离、无需管理文件路径、更新/重装不丢数据

### 14.2 应迁移: 会话控制 API (session_waiter)

**当前**: `sylanne_alpha/dialogue.py` 和 main.py 中使用自定义 `_session_key()` 逻辑管理多轮对话状态

**推荐**: 使用 `session_waiter` + `SessionController`

```python
from astrbot.core.utils.session_waiter import session_waiter, SessionController
```

**优势**: 内置超时管理、自动会话隔离、支持自定义 SessionFilter

### 14.3 应迁移: 插件配置 Schema

**当前**: `sylanne_alpha/config.py` 自定义配置管理

**推荐**: 创建 `_conf_schema.json`，让 AstrBot WebUI 自动生成配置界面

```json
{
  "emotion_decay_rate": {
    "type": "float",
    "description": "情感衰减速率",
    "default": 0.05
  },
  "memory_capacity": {
    "type": "int",
    "description": "记忆容量上限",
    "default": 1000
  }
}
```

### 14.4 应迁移: 对话管理器

**当前**: 自定义 ConversationBuffer 管理对话历史

**推荐**: 使用 `self.context.conversation_manager` 的官方 API

```python
conv_mgr = self.context.conversation_manager
# 获取/创建/切换/更新对话
```

### 14.5 应迁移: 人格管理器

**当前**: 通过 `on_llm_request` 钩子注入 system_prompt

**推荐**: 结合使用 `self.context.persona_manager` 管理 Sylanne 人格

### 14.6 可保留: WebUI Dashboard

AstrBot 当前**没有**官方的插件自定义页面 API（plugin-pages 文档不存在）。
因此 `sylanne_alpha/webui_server.py` 的自建 HTTP Server 方案暂时是合理的。

### 14.7 可保留: LLM 钩子用法

Sylanne 当前使用的 `@filter.on_llm_request()` 和 `@filter.on_llm_response()` 钩子是官方推荐的方式，无需迁移。

### 14.8 应考虑: Tool 注册方式

**当前**: 使用 `@filter.llm_tool` 装饰器

**推荐**: 对于复杂工具，考虑使用 dataclass 方式定义 + `self.context.add_llm_tools()` 注册，便于 Multi-Agent 架构扩展。

---

## 附录: API 导入速查

```python
# 核心
from astrbot.api.star import Context, Star
from astrbot.api.event import filter, AstrMessageEvent, MessageChain
from astrbot.api import logger, AstrBotConfig
import astrbot.api.message_components as Comp

# LLM/Agent
from astrbot.api.provider import ProviderRequest, LLMResponse
from astrbot.core.agent.tool import FunctionTool, ToolExecResult, ToolSet
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.agent.message import AssistantMessageSegment, UserMessageSegment, TextPart

# 会话控制
from astrbot.core.utils.session_waiter import session_waiter, SessionController, SessionFilter

# 对话管理
from astrbot.core.conversation_mgr import Conversation

# 平台
from astrbot.api.platform import Platform, AstrBotMessage, MessageMember, PlatformMetadata, MessageType
from astrbot.api.platform import register_platform_adapter

# 路径
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
```
