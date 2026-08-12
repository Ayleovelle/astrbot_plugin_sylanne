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
import contextvars
from contextlib import asynccontextmanager
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

    __slots__ = ("_d", "_mutation_guard", "_name", "_on_set")

    def __init__(
        self,
        name: str,
        backing: Any,
        *,
        mutation_guard: Any = None,
        on_set: Any = None,
    ) -> None:
        self._name = name
        self._d = backing  # BoundedDict | dict
        self._mutation_guard = mutation_guard
        self._on_set = on_set

    def _allows_mutation(self, key: str) -> bool:
        return not callable(self._mutation_guard) or bool(self._mutation_guard(key))

    # ---- 基本语义存取 ----
    def get(self, key: str, default: V | None = None) -> V | None:
        if not self._allows_mutation(key):
            return default
        return self._d.get(key, default)

    def set(self, key: str, value: V) -> None:
        if not self._allows_mutation(key):
            return
        self._d[key] = value
        if callable(self._on_set):
            self._on_set(self._name, key, value)

    def has(self, key: str) -> bool:
        return self._allows_mutation(key) and key in self._d

    def pop(self, key: str, default: V | None = None) -> V | None:
        if not self._allows_mutation(key):
            return default
        return self._d.pop(key, default)

    def get_or_create(self, key: str, factory: Any) -> V:
        """等价 setdefault，但用 factory 惰性构造，避免每次都建临时对象。"""
        if not self._allows_mutation(key):
            return factory() if callable(factory) else factory
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
        if not self._allows_mutation(key):
            return None  # type: ignore[return-value]
        return self._d[key]

    # ---- 迭代/统计（清理、持久化、扫描用）----
    def keys(self) -> Any:
        return [key for key in self._d.keys() if self._allows_mutation(key)]

    def values(self) -> Any:
        return [
            value
            for key, value in self._d.items()
            if self._allows_mutation(key)
        ]

    def items(self) -> Any:
        return [
            (key, value)
            for key, value in self._d.items()
            if self._allows_mutation(key)
        ]

    def snapshot_items(self) -> list[tuple[str, V]]:
        """返回 items 的快照列表（迭代中需修改容器时用，避免 RuntimeError）。"""
        return list(self.items())

    def clear(self) -> None:
        for key in list(self._d.keys()):
            if self._allows_mutation(key):
                self._d.pop(key, None)

    def _snapshot_items_unchecked(self) -> list[tuple[str, V]]:
        """Store-internal lifecycle view; never expose this as a session API."""

        return list(self._d.items())

    def _values_unchecked(self) -> list[V]:
        """Store-internal lifecycle values; bypasses request leases deliberately."""

        return list(self._d.values())

    def _pop_unchecked(self, key: str, default: V | None = None) -> V | None:
        """Store-internal exact-owner cleanup primitive."""

        return self._d.pop(key, default)

    def _clear_unchecked(self) -> None:
        """Store-internal global lifecycle cleanup primitive."""

        self._d.clear()

    def set_on_evict(self, callback: Any) -> None:
        """挂载/替换底层 BoundedDict 的 LRU 驱逐回调（普通 dict 静默忽略——无驱逐语义）。

        回调签名 fn(key, value)，同步调用（由 BoundedDict.__setitem__ 内部触发）。
        """
        if hasattr(self._d, "_on_evict"):
            self._d._on_evict = callback

    def __len__(self) -> int:
        return len(self.keys())

    def __contains__(self, key: str) -> bool:
        return self.has(key)

    def __repr__(self) -> str:
        return f"SessionMap({self._name!r}, n={len(self)})"


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
        self._task_cleanup_waiters: set[asyncio.Task[Any]] = set()
        self._scope_aware_tokens: set[str] = set()
        self._scope_generations: dict[str, int] = {}
        self._session_generation_binding: contextvars.ContextVar[dict[str, int]] = (
            contextvars.ContextVar(
                f"sylanne-session-store-generation:{id(self)}",
                default={},
            )
        )
        self._generation_tasks: dict[tuple[str, int], set[Any]] = {}

        # ---- 业务核心（真语义）----
        self.hosts: SessionMap = self._reg("hosts", BoundedDict(maxsize=200))
        self.memory_systems: SessionMap = self._reg("memory_systems", BoundedDict(maxsize=100))
        self.conversation_buffers: SessionMap = self._reg("conversation_buffers", BoundedDict(maxsize=100))

        # ---- 流式/分段回复缓冲 ----
        self.unfinished_replies: SessionMap = self._reg("unfinished_replies", BoundedDict(maxsize=200))
        self.stream_buffers: SessionMap = self._reg("stream_buffers", BoundedDict(maxsize=200))
        self.stream_first_sent: SessionMap = self._reg("stream_first_sent", BoundedDict(maxsize=200))
        self.segmented_tasks: SessionMap = self._reg(
            "segmented_tasks",
            BoundedDict(maxsize=200, on_evict=self._cancel_and_drain_tasks),
        )
        # 当前实时回复的逐段送达回执。模型全文只是意图；只有该账本中成功
        # send_message 的前缀才允许进入 AstrBot history / conversation buffer。
        self.segmented_delivery_turns: SessionMap = self._reg(
            "segmented_delivery_turns", BoundedDict(maxsize=200)
        )
        # 碎片防抖缓冲（inline-await 方案B）：按 session_key 存
        # {texts: list[str], start_time: float, latest_seq: int}。
        # 经 _reg 登记，自动纳入 release_session / reset_all 统一清理；
        # 取代旧 plugin._fragment_buffers / _fragment_timers 上帝对象裸 dict（漏清理风险）。
        #
        # 容量与流式运行态一致。驱逐/释放会给原 buffer 写入 cancelled 标记；等待中的
        # CAS 可据此区分“赢家已领取”与“owner 生命周期终止”，两种情况都安全作废。
        self.fragment_buffers: SessionMap = self._reg(
            "fragment_buffers",
            BoundedDict(maxsize=200, on_evict=self._cancel_fragment_buffer),
        )

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
        self.background_post_checkpoint_tasks: SessionMap = self._reg(
            "background_post_checkpoint_tasks",
            BoundedDict(maxsize=200, on_evict=self._cancel_and_drain_tasks),
        )
        # Pipeline 创建的短任务按 session 归属；release/aclose 会先 cancel 再清容器。
        self.background_tasks: SessionMap = self._reg(
            "background_tasks",
            BoundedDict(maxsize=200, on_evict=self._cancel_and_drain_tasks),
        )

        # ---- 主动发言 / outreach ----
        self.pending_outreach_context: SessionMap = self._reg("pending_outreach_context", BoundedDict(maxsize=50))
        # PR-Qzone：说说草稿待 owner 过目队列（独立容器，不与 pending_outreach_context
        # 共用同一 key——两种 pending 语义不同，共用会互相覆盖）。
        self.pending_qzone_draft: SessionMap = self._reg("pending_qzone_draft", BoundedDict(maxsize=50))
        self.proactive_candidate_sessions: SessionMap = self._reg("proactive_candidate_sessions", BoundedDict(maxsize=100))
        # The proactive dispatch feedback and one-shot amnesia cue belong to the
        # exact session owner.  Keeping them as registered SessionMaps makes
        # release_session/reset_all fence both values with the rest of the token.
        self.proactive_dispatch_audit: SessionMap = self._reg(
            "proactive_dispatch_audit", BoundedDict(maxsize=100)
        )
        self.amnesia_pending: SessionMap = self._reg(
            "amnesia_pending", BoundedDict(maxsize=200)
        )
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

        # ---- v2.5.0 slice-1b：已认证身份记录暂存层 + 坍缩集合 ----
        # （design §8 BLOCKER B1，全矩阵扎实版修正）
        # 三个写点（货架写 / profile 软同步 / 出生播种，本 slice 货架写已接线）执行
        # 上下文拿不到 event，故有 event 的路径（on_message）按主判据
        # （`SessionContext.resolve_authenticated_identity`：只用 event 方法
        # get_sender_id/get_message_type/get_group_id/session_id，不碰裸属性、不
        # 解析 session_key、不读 rel_register 钉住值）暂存一条"已认证身份记录"
        # {sender_id, platform, origin_scope, origin_id}；三写点将来只读
        # get_authenticated_identity，读不到即 SKIP。
        # collapsed_shared_sessions：次判据（发言人一致性）坍缩标记——同一
        # session_key 主判据曾判定 per-user 放行，但先后两次 sender_id 不同
        # （发言人翻脸），判定该 session_key 实为共享桶（某平台 unique_session
        # 语义特殊导致主判据误判），此后永久 SKIP，见 stash_authenticated_identity。
        # 两容器都用 BoundedDict 而非普通 dict：key 空间与 hosts 同源（session_key），
        # 存的是纯值/标记，无对象身份语义，不适用 conv_sync_locks 那类"锁被驱逐即
        # 并发失效"的教训；maxsize 与 hosts(200) 对齐，驱逐后果只是"该次 flush/
        # 播种少一次机会，或该 session_key 重新走一遍主判据"，与 §10 已成文接受的
        # "货架饿死倾向"同类代价，非安全洞。
        self.authenticated_senders: SessionMap = self._reg("authenticated_senders", BoundedDict(maxsize=200))
        self.collapsed_shared_sessions: SessionMap = self._reg("collapsed_shared_sessions", BoundedDict(maxsize=200))

        # ---- 锁容器（存 asyncio.Lock，pop 清理但不序列化）----
        self.session_locks: SessionMap = self._reg("session_locks", {})
        self.proactive_scheduler_locks: SessionMap = self._reg("proactive_scheduler_locks", {})
        # ConversationManager 同步专用锁：串行化同一会话"读历史→append→写回"，
        # 防止 safe_ensure_future 后台并发 sync 互相覆盖整表写回（消息丢失/乱序）。
        # 用普通 dict 而非 BoundedDict——锁被 LRU 驱逐会让并发保护静默失效（见 #_session_locks）。
        # 该容器按 UMO 而非 session_key 索引，不能交给 `_reg` 按 session_key
        # 直接 pop。其生命周期由下面的会话所有权 + 租用计数共同管理。
        self.conv_sync_locks: SessionMap = SessionMap("conv_sync_locks", {})
        self._conv_sync_session_umos: dict[str, str] = {}
        self._conv_sync_lock_leases: dict[str, int] = {}

    def _reg(self, name: str, backing: Any) -> SessionMap:
        m: SessionMap = SessionMap(
            name,
            backing,
            mutation_guard=self._allows_session_mutation,
            on_set=self._register_task_value,
        )
        self._maps.append(m)
        return m

    def claim_session(self, session_key: str, generation: int) -> None:
        """Claim an exact validated scope generation and fence its predecessor."""

        self._scope_aware_tokens.add(session_key)
        current = self._scope_generations.get(session_key)
        if current is not None and generation < current:
            raise RuntimeError("session generation cannot move backwards")
        if current != generation:
            self._scope_generations[session_key] = generation
            self._cancel_fragment_buffer(
                session_key,
                self.fragment_buffers.get(session_key),
            )
            self._clear_session_state(session_key)
            if current is not None:
                self._cancel_generation_tasks(session_key, current)
        self._authorize_current_task(session_key, generation)

    def _authorize_current_task(self, session_key: str, generation: int) -> None:
        bindings = dict(self._session_generation_binding.get())
        bindings[session_key] = generation
        self._session_generation_binding.set(bindings)

    def _allows_session_mutation(self, session_key: str) -> bool:
        if session_key not in self._scope_aware_tokens:
            return True
        bindings = self._session_generation_binding.get()
        return bindings.get(session_key) == self._scope_generations.get(session_key)

    def _register_task_value(self, map_name: str, session_key: str, value: Any) -> None:
        if map_name not in {
            "background_tasks",
            "segmented_tasks",
            "background_post_checkpoint_tasks",
        }:
            return
        generation = self._scope_generations.get(session_key)
        if generation is None:
            return
        collection = value if isinstance(value, (set, list, tuple)) else (value,)
        for task in collection:
            if task is None:
                continue
            generation_tasks = self._generation_tasks.setdefault(
                (session_key, generation), set()
            )
            if task in generation_tasks:
                continue
            generation_tasks.add(task)
            callback = getattr(task, "add_done_callback", None)
            if callable(callback):
                callback(
                    lambda done, token=session_key, owner_generation=generation: (
                        self._owned_task_done(token, owner_generation, done)
                    )
                )

    def _owned_task_done(self, session_key: str, generation: int, task: Any) -> None:
        self._consume_task_result(task)
        tasks = self._generation_tasks.get((session_key, generation))
        if tasks is not None:
            tasks.discard(task)
            if not tasks:
                self._generation_tasks.pop((session_key, generation), None)

    def _cancel_generation_tasks(self, session_key: str, generation: int) -> None:
        tasks = tuple(self._generation_tasks.get((session_key, generation), ()))
        self._cancel_and_drain_tasks(
            f"{session_key}:{generation}",
            tasks,
            after_drain=lambda: self._clear_if_generation(session_key, generation),
        )

    def _clear_if_generation(self, session_key: str, generation: int) -> None:
        current = self._scope_generations.get(session_key)
        if current == generation or current is None:
            self._clear_session_state(session_key)

    @staticmethod
    def _cancel_fragment_buffer(_key: str, value: Any) -> None:
        if isinstance(value, dict):
            value["cancelled"] = True

    @staticmethod
    def _cancel_task_collection(_key: str, value: Any) -> None:
        tasks = value if isinstance(value, (set, list, tuple)) else (value,)
        for task in tuple(tasks):
            cancel = getattr(task, "cancel", None)
            if callable(cancel) and not bool(getattr(task, "done", lambda: False)()):
                try:
                    cancel()
                except Exception:
                    pass

    def _cancel_and_drain_tasks(
        self,
        key: str,
        value: Any,
        *,
        after_drain: Any = None,
    ) -> None:
        """Cancel tasks and arrange exception-safe draining for sync eviction."""

        tasks = value if isinstance(value, (set, list, tuple)) else (value,)
        pending: list[Any] = []
        seen: set[int] = set()
        for task in tuple(tasks):
            if task is None:
                continue
            marker = id(task)
            if marker in seen:
                continue
            seen.add(marker)
            if bool(getattr(task, "done", lambda: True)()):
                self._consume_task_result(task)
                continue
            cancel = getattr(task, "cancel", None)
            if not callable(cancel):
                continue
            try:
                cancel()
                pending.append(task)
            except Exception:
                continue
        if not pending:
            if callable(after_drain):
                after_drain()
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            remaining = len(pending)

            def _finish(task: Any) -> None:
                nonlocal remaining
                self._consume_task_result(task)
                remaining -= 1
                if remaining == 0 and callable(after_drain):
                    after_drain()

            for task in pending:
                add_done_callback = getattr(task, "add_done_callback", None)
                if callable(add_done_callback):
                    add_done_callback(_finish)
            return

        async def _drain() -> None:
            await asyncio.gather(*pending, return_exceptions=True)
            if callable(after_drain):
                after_drain()

        waiter = loop.create_task(_drain(), name=f"sylanne-owner-drain:{key}")
        self._task_cleanup_waiters.add(waiter)
        waiter.add_done_callback(self._task_cleanup_waiters.discard)

    @staticmethod
    def _consume_task_result(task: Any) -> None:
        try:
            task.exception()
        except (asyncio.CancelledError, Exception):
            pass

    # ------------------------------------------------------------------
    # 统一清理收口（替代 state_persistence._SESSION_KEYED_CONTAINERS 反射遍历）
    # ------------------------------------------------------------------
    def release_session(
        self,
        session_key: str,
        *,
        expected_generation: int | None = None,
    ) -> None:
        """释放某会话在所有已登记 SessionMap 中的态。漏登记 = 容器不在 = 立即暴露。"""
        if expected_generation is None:
            owned_tasks = self._task_values(
                self.background_tasks.get(session_key, set()),
                self.segmented_tasks.get(session_key),
                self.background_post_checkpoint_tasks.get(session_key),
            )
            should_clear = True
        else:
            owned_tasks = list(
                self._generation_tasks.get((session_key, expected_generation), ())
            )
            should_clear = (
                self._scope_generations.get(session_key) == expected_generation
            )
        self._cancel_and_drain_tasks(
            session_key,
            owned_tasks,
            after_drain=lambda: (
                self._clear_session_state(session_key)
                if expected_generation is None
                else self._clear_if_generation(session_key, expected_generation)
            ),
        )
        if should_clear and expected_generation is not None:
            self._scope_generations.pop(session_key, None)
        if should_clear:
            self._cancel_fragment_buffer(
                session_key,
                self.fragment_buffers.get(session_key),
            )
            conv_sync_umo = self._conv_sync_session_umos.pop(session_key, None)
            self._clear_session_state(session_key)
            if conv_sync_umo is not None:
                self._release_unused_conv_sync_lock(conv_sync_umo)

    def track_background_task(self, session_key: str, task: Any) -> Any:
        """登记 pipeline 短任务，并在完成后自动解除 owner 引用。"""

        if not self._allows_session_mutation(session_key):
            cancel = getattr(task, "cancel", None)
            if callable(cancel):
                cancel()
            callback = getattr(task, "add_done_callback", None)
            if callable(callback):
                callback(self._consume_task_result)
            return task
        tasks = self.background_tasks.get_or_create(session_key, set)
        tasks.add(task)
        self._register_task_value("background_tasks", session_key, task)

        def _discard(done: Any) -> None:
            if session_key not in self._scope_aware_tokens:
                self._consume_task_result(done)
            current = self.background_tasks.get(session_key)
            if isinstance(current, set):
                current.discard(done)
                if not current:
                    self.background_tasks.pop(session_key, None)

        add_done_callback = getattr(task, "add_done_callback", None)
        if callable(add_done_callback):
            add_done_callback(_discard)
        return task

    async def aclose(self) -> None:
        """Cancel/await all owner tasks, then release every registered session state."""

        tasks: list[Any] = []
        owned_tasks = self._task_values(
            *(
                owned
                for task_map in self._task_maps()
                for owned in task_map._values_unchecked()
            )
        )
        for task in owned_tasks:
            if bool(getattr(task, "done", lambda: True)()):
                self._consume_task_result(task)
                continue
            try:
                task.cancel()
            except Exception:
                continue
            tasks.append(task)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for task_map in self._task_maps():
            task_map._clear_unchecked()
        for _session_key, fragment in self.fragment_buffers._snapshot_items_unchecked():
            self._cancel_fragment_buffer(_session_key, fragment)
        self.reset_all()
        while self._task_cleanup_waiters:
            cleanup_waiters = tuple(self._task_cleanup_waiters)
            await asyncio.gather(*cleanup_waiters, return_exceptions=True)

    def reset_all(self) -> None:
        """整体清空所有会话态（供 state_persistence 的全局 reset 用）。"""
        owned_tasks = self._task_values(
            *(
                owned
                for task_map in self._task_maps()
                for owned in task_map._values_unchecked()
            )
        )
        self._cancel_and_drain_tasks(
            "reset-all",
            owned_tasks,
            after_drain=self._clear_all_state,
        )
        for _session_key, fragment in self.fragment_buffers._snapshot_items_unchecked():
            self._cancel_fragment_buffer(_session_key, fragment)
        self._clear_all_state()

    def _clear_session_state(self, session_key: str) -> None:
        for m in self._maps:
            m._pop_unchecked(session_key, None)

    def _clear_all_state(self) -> None:
        for m in self._maps:
            m._clear_unchecked()
        self._conv_sync_session_umos.clear()
        for umo in list(self.conv_sync_locks.keys()):
            self._release_unused_conv_sync_lock(umo)

    def _task_maps(self) -> tuple[SessionMap, SessionMap, SessionMap]:
        return (
            self.background_tasks,
            self.segmented_tasks,
            self.background_post_checkpoint_tasks,
        )

    @staticmethod
    def _task_values(*owned_values: Any) -> list[Any]:
        tasks: list[Any] = []
        seen: set[int] = set()
        for owned in owned_values:
            collection = owned if isinstance(owned, (set, list, tuple)) else (owned,)
            for task in collection:
                if task is None or id(task) in seen:
                    continue
                seen.add(id(task))
                tasks.append(task)
        return tasks

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

    def _release_unused_conv_sync_lock(self, umo: str) -> None:
        """仅在 UMO 已无会话所有者和 holder/waiter 时删除其锁。"""
        if self._conv_sync_lock_leases.get(umo, 0) > 0:
            return
        if umo in self._conv_sync_session_umos.values():
            return
        self.conv_sync_locks.pop(umo, None)

    @asynccontextmanager
    async def lease_conv_sync_lock(self, session_key: str, umo: str) -> Any:
        """租用同一 UMO 的同步锁，并把持有者和等待者都纳入生命周期。"""
        previous_umo = self._conv_sync_session_umos.get(session_key)
        self._conv_sync_session_umos[session_key] = umo
        if previous_umo is not None and previous_umo != umo:
            self._release_unused_conv_sync_lock(previous_umo)

        lock = self.get_conv_sync_lock(umo)
        self._conv_sync_lock_leases[umo] = (
            self._conv_sync_lock_leases.get(umo, 0) + 1
        )
        try:
            async with lock:
                yield lock
        finally:
            remaining = self._conv_sync_lock_leases.get(umo, 1) - 1
            if remaining > 0:
                self._conv_sync_lock_leases[umo] = remaining
            else:
                self._conv_sync_lock_leases.pop(umo, None)
                self._release_unused_conv_sync_lock(umo)

    # ------------------------------------------------------------------
    # v2.5.0 slice-1b：已认证身份记录暂存层专用方法（design 全矩阵扎实版）
    # ------------------------------------------------------------------
    def is_collapsed_shared_session(self, session_key: str) -> bool:
        """该 session_key 是否已被次判据（发言人一致性）坍缩标记为共享桶。

        坍缩是单调、不可逆的：一旦标记，`stash_authenticated_identity` 此后
        永远直接跳过该 session_key，不会因为某次又判定为 per-user 而解除。
        """
        return bool(self.collapsed_shared_sessions.has(session_key))

    def stash_authenticated_identity(
        self, session_key: str, identity: dict[str, str] | None
    ) -> None:
        """on_message 唯一入口：消费主判据结果 `identity`
        （`SessionContext.resolve_authenticated_identity` 的返回值），叠加
        次判据（发言人一致性坍缩）后落地暂存/坍缩决定。

        - 已坍缩的 session_key：直接返回，不再暂存、不解除坍缩标记（单调收紧，
          design §8 B1"塌缩桶路径零写入"前置的持续版本——坍缩只会让状态从
          "放行"降到"SKIP"，永不新增放行路径）。
        - `identity is None`（主判据判定共享桶 / 认不出发言人 / OTHER_MESSAGE）：
          不暂存，也不触发坍缩判定（本来就没有身份可比较，不算"翻脸"）。
        - `identity` 非空且该 session_key 从未暂存过（或已存在同一 sender）：
          正常暂存/覆盖。
        - `identity` 非空且该 session_key 已暂存过、且新旧 `sender_id` 不同
          （发言人翻脸）：判定该 session_key 实为共享桶——弹出旧暂存、打上
          坍缩标记，本次也不暂存。这是防"某平台 unique_session 语义特殊导致
          主判据误判 per-user"的次判据兜底（design open_risks 明确标注的
          物理下限：首条到第二条之间的暂存窗口，非零但受 scope=owner + W0
          净化 + W0b 哨兵三层叠加削弱）。
        """
        if self.is_collapsed_shared_session(session_key):
            return
        if identity is None:
            return
        sender_id = str(identity.get("sender_id", "") or "")
        platform = str(identity.get("platform", "") or "")
        if not sender_id or not platform:
            return
        existing = self.authenticated_senders.get(session_key)
        if existing is not None:
            existing_sender = str(existing.get("sender_id", "") or "")
            if existing_sender and existing_sender != sender_id:
                self.authenticated_senders.pop(session_key, None)
                self.collapsed_shared_sessions.set(session_key, True)
                return
        self.authenticated_senders.set(session_key, dict(identity))

    def get_authenticated_identity(self, session_key: str) -> dict[str, str] | None:
        """三写点读接口（本 slice 货架写已接线，profile 软同步/出生播种留后续
        slice）。读不到即返回 None，调用方语义上必须 SKIP——不得读 rel_register
        钉住值或解析 session_key 兜底出一个值。
        """
        return self.authenticated_senders.get(session_key)

    def get_authenticated_sender(self, session_key: str) -> str | None:
        """便捷读接口：只取身份记录里的 `sender_id` 字段（写点最常用的一个
        字段，且历史调用方/测试沿用这个名字）。读不到记录或字段为空均返回 None。
        """
        rec = self.authenticated_senders.get(session_key)
        if rec is None:
            return None
        sid = str(rec.get("sender_id", "") or "")
        return sid or None

    def set_authenticated_identity(
        self,
        session_key: str,
        *,
        sender_id: str,
        platform: str,
        origin_scope: str = "private",
        origin_id: str = "",
    ) -> None:
        """测试 / 直接注入用：绕过 on_message 主判据直接暂存一条完整身份记录
        （不做次判据坍缩检查——坍缩检测是 `stash_authenticated_identity` 实时
        消费路径专属的行为，直接注入代表"已经过身份解析、可信"的既定状态）。
        生产路径唯一入口是 `stash_authenticated_identity`。sender_id/platform
        任一为空则整体不写（与生产判据"拒绝构造无平台/无发言人身份记录"的
        fail-closed 方向一致）。
        """
        if not sender_id or not platform:
            return
        self.authenticated_senders.set(
            session_key,
            {
                "sender_id": sender_id,
                "platform": platform,
                "origin_scope": origin_scope,
                "origin_id": origin_id,
            },
        )

