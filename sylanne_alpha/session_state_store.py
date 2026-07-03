"""会话态集中存储模块（SessionStateStore）。

把原先散落在主插件上帝对象上的 ~34 个 session-keyed 容器物理收拢到本模块，
解决两个根本问题：
1. 清理链脆弱——原 `state_persistence._SESSION_KEYED_CONTAINERS` 是手抄的字符串
   元组 + 反射 getattr 遍历清理，新增容器无强制登记机制，漏登记即静默内存泄漏
   （实测曾漏 3 个无界裸 dict）。本模块用 register 结构性登记 + release_session
   统一清理，漏登记 = 容器不存在 = 立即暴露，而非静默泄漏。
2. 耦合——业务模块直穿 `plugin._xxx[session_key]` 抓上帝对象私有态。本模块提供
   语义访问边界，模块经 store 存取，为后续 P3 agent 化提供清晰边界。

分层语义设计：
- SessionMap[V]：运行态缓冲的统一泛型封装（绝大多数容器同形态：按 session_key
  存取一个值）。包 BoundedDict（LRU/TTL）或普通 dict，暴露语义方法，避免 34 套
  手写方法 / 方法爆炸。嵌套可变值（list/dict）经 ref() 返回受控引用处理 append/pop。
- 真语义容器（_hosts / _session_locks / _memory_systems）：在 store 上有专用语义
  方法（host 工厂、lock 取用清理、memory 取用），精心设计。

清理收口：所有经 register 登记的 SessionMap 都会被 release_session 统一 pop。
"""

from __future__ import annotations

import asyncio
import collections
from typing import TYPE_CHECKING, Any, Generic, Iterator, TypeVar

from sylanne_alpha.infra import BoundedDict

if TYPE_CHECKING:
    from sylanne_alpha.host import SylanneAlphaHost
    from sylanne_alpha.memory_system import MemorySystem

V = TypeVar("V")


class SessionMap(Generic[V]):
    """按 session_key 存取单值的运行态容器的统一语义封装。

    内部委托给 BoundedDict（带 LRU/TTL）或普通 dict。所有访问点经语义方法，
    不直接触碰内部字典。经 store.register 登记后纳入 release_session 统一清理。
    """

    __slots__ = ("_d", "_name")

    def __init__(self, name: str, backing: Any) -> None:
        self._name = name
        self._d = backing  # BoundedDict | dict

    # ---- 基本语义存取 ----
    def get(self, key: str, default: V | None = None) -> V | None:
        return self._d.get(key, default)

    def set(self, key: str, value: V) -> None:
        self._d[key] = value

    def has(self, key: str) -> bool:
        return key in self._d

    def pop(self, key: str, default: V | None = None) -> V | None:
        return self._d.pop(key, default)

    def get_or_create(self, key: str, factory: Any) -> V:
        """等价 setdefault，但用 factory 惰性构造，避免每次都建临时对象。"""
        if key in self._d:
            return self._d[key]
        value = factory() if callable(factory) else factory
        self._d[key] = value
        return value

    def ref(self, key: str) -> V:
        """返回 key 对应的可变值引用（用于 x[k].append / x[k].pop 等嵌套二级操作）。

        调用方须保证 key 已存在（先 get_or_create）。返回的是内部引用，
        对其 append/pop/字段赋值会就地反映到容器内。
        """
        return self._d[key]

    # ---- 迭代/统计（清理、持久化、扫描用）----
    def keys(self) -> Any:
        return self._d.keys()

    def values(self) -> Any:
        return self._d.values()

    def items(self) -> Any:
        return self._d.items()

    def snapshot_items(self) -> list[tuple[str, V]]:
        """返回 items 的快照列表（迭代中需修改容器时用，避免 RuntimeError）。"""
        return list(self._d.items())

    def clear(self) -> None:
        self._d.clear()

    def set_on_evict(self, callback: Any) -> None:
        """挂载/替换底层 BoundedDict 的 LRU 驱逐回调（普通 dict 静默忽略——无驱逐语义）。

        回调签名 fn(key, value)，同步调用（由 BoundedDict.__setitem__ 内部触发）。
        """
        if hasattr(self._d, "_on_evict"):
            self._d._on_evict = callback

    def __len__(self) -> int:
        return len(self._d)

    def __contains__(self, key: str) -> bool:
        return key in self._d

    def __repr__(self) -> str:
        return f"SessionMap({self._name!r}, n={len(self._d)})"


class SessionStateStore:
    """集中持有所有 session-keyed 会话态。

    容器分两类：
    - 运行态缓冲（多数）：SessionMap 封装，全部 register 入清理列表。
    - 真语义容器（_hosts/_session_locks/_memory_systems）：SessionMap 封装 +
      store 上的专用语义方法。

    清理：release_session(key) 遍历所有已 register 的 SessionMap 统一 pop。
    """

    def __init__(self) -> None:
        # 登记表：所有需按 session_key 清理的 SessionMap（register 自动追加）
        self._maps: list[SessionMap] = []

        # ---- 业务核心（真语义）----
        self.hosts: SessionMap = self._reg("hosts", BoundedDict(maxsize=200))
        self.memory_systems: SessionMap = self._reg("memory_systems", BoundedDict(maxsize=100))
        self.conversation_buffers: SessionMap = self._reg("conversation_buffers", BoundedDict(maxsize=100))

        # ---- 流式/分段回复缓冲 ----
        self.unfinished_replies: SessionMap = self._reg("unfinished_replies", BoundedDict(maxsize=200))
        self.stream_buffers: SessionMap = self._reg("stream_buffers", BoundedDict(maxsize=200))
        self.stream_first_sent: SessionMap = self._reg("stream_first_sent", BoundedDict(maxsize=200))
        self.segmented_tasks: SessionMap = self._reg("segmented_tasks", BoundedDict(maxsize=200))
        # 碎片防抖缓冲（inline-await 方案B）：按 session_key 存
        # {texts: list[str], start_time: float, latest_seq: int}。
        # 经 _reg 登记，自动纳入 release_session / reset_all 统一清理；
        # 取代旧 plugin._fragment_buffers / _fragment_timers 上帝对象裸 dict（漏清理风险）。
        #
        # 用普通 dict 而非 BoundedDict：LRU 驱逐与 winner pop 都返回 None，二者无法在
        # 段B 区分——一旦因 >maxsize 并发会话被驱逐，该会话碎片会被误判为 loser 而
        # stop_event() 静默丢失用户消息。改普通 dict 后 `get→None` 唯一含义是
        # "已被 winner pop"，loser 语义无歧义。buf 生命周期极短（≤max_wait，winner pop
        # 即清），孤儿仅在 winner 协程被取消时短暂残留，由 release_session 兜底清理。
        self.fragment_buffers: SessionMap = self._reg("fragment_buffers", {})

        # ---- 请求/响应诊断缓存 ----
        self.last_request_budgets: SessionMap = self._reg("last_request_budgets", BoundedDict(maxsize=200))
        self.last_understanding_closed_loop: SessionMap = self._reg("last_understanding_closed_loop", BoundedDict(maxsize=200))
        self.last_bot_expression_time: SessionMap = self._reg("last_bot_expression_time", BoundedDict(maxsize=200))
        self.last_user_texts: SessionMap = self._reg("last_user_texts", BoundedDict(maxsize=200))
        self.last_bot_texts: SessionMap = self._reg("last_bot_texts", BoundedDict(maxsize=200))
        self.conversation_input_epoch: SessionMap = self._reg("conversation_input_epoch", BoundedDict(maxsize=200))
        self.last_request_text: SessionMap = self._reg("last_request_text", BoundedDict(maxsize=200))
        self.user_message_withdrawals: SessionMap = self._reg("user_message_withdrawals", BoundedDict(maxsize=200))

        # ---- 后台投递队列全家桶 ----
        self.background_post_queues: SessionMap = self._reg("background_post_queues", BoundedDict(maxsize=200))
        self.background_post_dead_letters: SessionMap = self._reg("background_post_dead_letters", BoundedDict(maxsize=200))
        self.background_post_sequence: SessionMap = self._reg("background_post_sequence", BoundedDict(maxsize=200))
        self.background_post_latest_enqueued: SessionMap = self._reg("background_post_latest_enqueued", BoundedDict(maxsize=200))
        self.background_post_last_committed: SessionMap = self._reg("background_post_last_committed", BoundedDict(maxsize=200))
        self.background_post_active: SessionMap = self._reg("background_post_active", BoundedDict(maxsize=200))
        self.background_post_worker_state: SessionMap = self._reg("background_post_worker_state", BoundedDict(maxsize=200))
        self.background_post_checkpoint_tasks: SessionMap = self._reg("background_post_checkpoint_tasks", {})

        # ---- 主动发言 / outreach ----
        self.pending_outreach_context: SessionMap = self._reg("pending_outreach_context", BoundedDict(maxsize=50))
        self.proactive_candidate_sessions: SessionMap = self._reg("proactive_candidate_sessions", BoundedDict(maxsize=100))
        self.session_origins: SessionMap = self._reg("session_origins", {})
        # ---- Phase 2B：关系类型层（PR-G 写 / PR-H 读）----
        # 壳层关系层累积态：{session_key: {sender_id, romantic_conf, friendly_conf,
        #   formal_conf, sample_count, updated_at, last_active}}。rel_register 分类按类累积，
        #   is_romantic(PR-H) 据此 + 身份门控判亲密。plain dict（不随 LRU 驱逐），真持久化走
        #   独立 KV key sylanne_relationship_state（仿 sylanne_life_sim_state，PR-H 接 restore/save）。
        self.relationship_register_state: SessionMap = self._reg("relationship_register_state", {})
        # 手动覆盖（/bond·/unbond 写，owner-gated）：{session_key: bool}（True 亲密/False 非亲密）。
        self.intimacy_override: SessionMap = self._reg("intimacy_override", {})

        # ---- T4-02：变体池 recent-N 去重历史 ----
        # {session_key: {recent_key: [最近选过的变体...]}}——variant_pool.choose 的 state
        # 参数直接就是内层 dict（按模板家族 recent_key 分列，如 "empty_reply_fallback"）。
        self.variant_recent: SessionMap = self._reg("variant_recent", BoundedDict(maxsize=200))

        # ---- T2-02：补刀/改口 refractory 计数（仅会话内，不落 KV，重启清零）----
        # {session_key: {"exchange_count": int, "last_fired_at": int}}——
        # exchange_count 每次 SPEAK 分段回复正常发完 +1，last_fired_at 记录上次真正
        # 触发补刀时的 exchange_count，两者差 >= 8 才允许再骰一次。
        self.afterthought_state: SessionMap = self._reg("afterthought_state", BoundedDict(maxsize=200))

        # ---- 其他运行态 ----
        self.last_user_message_time: SessionMap = self._reg("last_user_message_time", BoundedDict(maxsize=200))
        # 短 gap 慢变信号比较用：上一轮注入的 {warmth,tension}（2.1.0 从 kernel slot 挪来——
        # SDK 整树同步会冲掉 kernel._last_injected_state slot，故改存 agent 层，解耦 SDK 依赖）。
        self.last_injected_states: SessionMap = self._reg("last_injected_states", BoundedDict(maxsize=200))
        self.sylanne_memory_cache: SessionMap = self._reg("sylanne_memory_cache", BoundedDict(maxsize=200))
        self.conversation_pending_response_epochs: SessionMap = self._reg("conversation_pending_response_epochs", BoundedDict(maxsize=200))
        self.group_atmosphere_injection_snapshot_cache: SessionMap = self._reg("group_atmosphere_injection_snapshot_cache", BoundedDict(maxsize=200))
        self.realtime_ordinary_history_backfills: SessionMap = self._reg("realtime_ordinary_history_backfills", BoundedDict(maxsize=200))
        self.realtime_chat_active_dispatches: SessionMap = self._reg("realtime_chat_active_dispatches", BoundedDict(maxsize=200))

        # ---- 锁容器（存 asyncio.Lock，pop 清理但不序列化）----
        self.session_locks: SessionMap = self._reg("session_locks", {})
        self.proactive_scheduler_locks: SessionMap = self._reg("proactive_scheduler_locks", {})
        # ConversationManager 同步专用锁：串行化同一会话"读历史→append→写回"，
        # 防止 safe_ensure_future 后台并发 sync 互相覆盖整表写回（消息丢失/乱序）。
        # 用普通 dict 而非 BoundedDict——锁被 LRU 驱逐会让并发保护静默失效（见 #_session_locks）。
        self.conv_sync_locks: SessionMap = self._reg("conv_sync_locks", {})

    def _reg(self, name: str, backing: Any) -> SessionMap:
        m: SessionMap = SessionMap(name, backing)
        self._maps.append(m)
        return m

    # ------------------------------------------------------------------
    # 统一清理收口（替代 state_persistence._SESSION_KEYED_CONTAINERS 反射遍历）
    # ------------------------------------------------------------------
    def release_session(self, session_key: str) -> None:
        """释放某会话在所有已登记 SessionMap 中的态。漏登记 = 容器不在 = 立即暴露。"""
        for m in self._maps:
            m.pop(session_key, None)

    def reset_all(self) -> None:
        """整体清空所有会话态（供 state_persistence 的全局 reset 用）。"""
        for m in self._maps:
            m.clear()

    # ------------------------------------------------------------------
    # 真语义容器的专用方法
    # ------------------------------------------------------------------
    def get_host(self, session_key: str) -> SylanneAlphaHost | None:
        return self.hosts.get(session_key)

    def set_host(self, session_key: str, host: SylanneAlphaHost) -> None:
        self.hosts.set(session_key, host)

    def get_session_lock(self, session_key: str) -> asyncio.Lock:
        """取（或惰性建）某会话的 asyncio.Lock。"""
        return self.session_locks.get_or_create(session_key, asyncio.Lock)

    def get_conv_sync_lock(self, session_key: str) -> asyncio.Lock:
        """取（或惰性建）某会话的 ConversationManager 同步锁。

        与 get_session_lock 分离，避免与通用 session 锁互相阻塞。锁实例跨多次 sync
        调用持久存在（挂在 store 上），从而真正串行化同一会话的并发写回。
        """
        return self.conv_sync_locks.get_or_create(session_key, asyncio.Lock)

