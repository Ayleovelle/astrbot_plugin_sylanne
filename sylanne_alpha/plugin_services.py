"""PluginServices —— 只读服务容器，供各子模块共享插件级依赖。

将原先通过 ``self._p.xxx`` 散落访问的只读服务集中到一个轻量数据类中，
使依赖关系显式化，便于测试时注入 mock，也为后续进一步解耦做准备。

设计决策：
  - 不使用 frozen=True：config 字典本身可变（运行时热更新），冻结会阻止赋值。
  - 使用 slots=True：减少实例内存开销，属性访问更快。
  - 类型全部标注为 Any：避免循环导入（实际类型分布在 astrbot、sylanne_alpha 等包中）。
  - 可调用字段（put_kv_data 等）使用 Optional[Callable]：部分宿主环境不提供 KV 存储。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass(slots=True)
class PluginServices:
    """各子模块共享的只读插件服务引用。

    Attributes:
        config: 插件配置字典，运行时可能被热更新（所有模块读取）。
        logger: 日志记录器实例（多数模块使用模块级 logger，此处为备用注入点）。
        context: AstrBot 平台上下文对象，提供平台 API 访问。
        rhythm_learner: 节奏学习器，提供自适应分段/打字节奏参数。
        social_field: 社交场域引擎，管理群聊上下文和回复决策。
        put_kv_data: 持久化 KV 写入回调（async callable）。
        get_kv_data: 持久化 KV 读取回调（async callable）。
        delete_kv_data: 持久化 KV 删除回调（async callable）。
        session_key_fn: 从事件对象派生 session_key 的回调。
        host_fn: 获取指定 session 的 Host 实例的回调。
        schedule_buffer_persist_fn: 调度防抖 buffer 持久化的回调。
        has_conversation_manager_fn: 检查 ConversationManager 是否可用。
        sync_message_to_conv_mgr_fn: 将消息同步到 ConversationManager（async）。
        observe_response_fn: 观测 bot 回复的回调（async）。
        astrbot_message_fn: 构建 AstrBot 消息对象的回调。
        observed_now_fn: 获取当前观测时间的回调（支持模拟时间）。
        runtime_state: 会话运行态的显式 owner；未注入时由显式 pipeline 独占创建。
    """

    config: dict = field(default_factory=dict)
    logger: Any = None
    context: Any = None
    rhythm_learner: Any = None
    social_field: Any = None
    put_kv_data: Optional[Callable[..., Any]] = None
    get_kv_data: Optional[Callable[..., Any]] = None
    delete_kv_data: Optional[Callable[..., Any]] = None
    # Phase 4 callbacks: replace self._p method calls
    session_key_fn: Optional[Callable[..., str]] = None
    host_fn: Optional[Callable[..., Any]] = None
    schedule_buffer_persist_fn: Optional[Callable[..., None]] = None
    has_conversation_manager_fn: Optional[Callable[[], bool]] = None
    sync_message_to_conv_mgr_fn: Optional[Callable[..., Any]] = None
    observe_response_fn: Optional[Callable[..., Any]] = None
    astrbot_message_fn: Optional[Callable[[str], Any]] = None
    observed_now_fn: Optional[Callable[[], float]] = None
    assess_emotion_fn: Optional[Callable[..., Any]] = None
    save_state_fn: Optional[Callable[..., Any]] = None
    state_persistence: Any = None
    runtime_state: Any = None
    authenticated_identity_fn: Optional[Callable[[str], Any]] = None
    extract_first_sentence_fn: Optional[Callable[[str], str]] = None
    send_first_sentence_fn: Optional[Callable[[str, str], Any]] = None
    max_hosts: int = 20
