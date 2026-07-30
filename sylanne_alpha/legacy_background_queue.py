"""Registry-free legacy background queue compatibility.

提供 BackgroundPostJob（任务值对象）和 BackgroundPostQueue（队列管理器），
封装 Sylanne 后台情感评估管线的自适应工作者调度、检查点持久化、
排空处理、重试和死信队列逻辑。

设计要点：
- 每个 session 独立队列，互不干扰
- 自适应工作者数量：根据队列深度和资源压力动态调整
- 租约机制：防止任务被重复处理
- 检查点：防抖持久化到 KV 存储，支持重启恢复
- 死信队列：多次重试失败的任务进入死信，不阻塞正常流程
"""

from __future__ import annotations

import asyncio
import collections
import inspect
import logging
import math
from typing import TYPE_CHECKING, Any, Callable

from sylanne_alpha.utils import safe_ensure_future

if TYPE_CHECKING:
    from sylanne_alpha.protocols import PluginHost
    from sylanne_alpha.scope_repository import ScopedPersistenceGateway

logger = logging.getLogger("astrbot_plugin_sylanne")


# ---------------------------------------------------------------------------
# BackgroundPostJob -- 单个排队评估任务的值对象
# ---------------------------------------------------------------------------


class BackgroundPostJob:
    """单个后台回复后评估任务。

    使用 __slots__ 优化内存占用（队列中可能同时存在数百个任务）。
    包含任务元数据（序号、入队时间）和重试状态（尝试次数、错误信息、死信时间）。
    """

    __slots__ = (
        "event",
        "identity",
        "reply_text",
        "context_key",
        "sequence",
        "enqueued_at",
        "attempts",
        "next_retry_at",
        "last_error_type",
        "last_error_message",
        "last_failed_at",
        "dead_lettered_at",
        "leased_at",
        "lease_until",
        "_retries",
    )

    def __init__(
        self,
        event: Any,
        identity: str,
        reply_text: str,
        context_key: str,
        sequence: int,
        enqueued_at: float,
    ):
        """初始化评估任务。

        Args:
            event: 触发评估的原始事件对象。
            identity: 发言者身份标识。
            reply_text: 待评估的回复文本。
            context_key: 上下文键（用于关联对话上下文）。
            sequence: 单调递增的序号，用于排序和去重。
            enqueued_at: 入队时间戳。
        """
        self.event = event
        self.identity = identity
        self.reply_text = reply_text
        self.context_key = context_key
        self.sequence = sequence
        self.enqueued_at = enqueued_at
        self.attempts = 0
        self.next_retry_at = 0.0
        self.last_error_type = ""
        self.last_error_message = ""
        self.last_failed_at = 0.0
        self.dead_lettered_at = 0.0
        self.leased_at = 0.0
        self.lease_until = 0.0
        self._retries = 0  # drain 内部的轻量重试计数（区别于 attempts）

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典，用于检查点持久化。"""
        return {
            "reply_text": self.reply_text,
            "context_key": self.context_key,
            "sequence": self.sequence,
            "enqueued_at": self.enqueued_at,
            "attempts": self.attempts,
            "next_retry_at": self.next_retry_at,
            "last_error_type": self.last_error_type,
            "last_error_message": self.last_error_message,
            "last_failed_at": self.last_failed_at,
            "dead_lettered_at": self.dead_lettered_at,
        }


# ---------------------------------------------------------------------------
# BackgroundPostQueue -- 队列管理器，委托插件实例进行状态访问
# ---------------------------------------------------------------------------


class BackgroundPostQueue:
    """后台评估队列管理器。

    封装队列操作逻辑，通过 self._p 委托访问插件实例的状态。
    负责自适应工作者调度、租约过期回收、检查点持久化、排空处理和队列恢复。
    """

    def __init__(self, plugin: PluginHost, *, owner_persona_ref: Any = None) -> None:
        """初始化队列管理器。

        Args:
            plugin: Sylanne 插件实例。
        """
        self._p = plugin
        self._owner_persona_ref = owner_persona_ref

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _observed_now(self) -> float:
        """获取当前观测时间（支持基准测试时间偏移）。"""
        return self._p._observed_now()

    def _scope_for_session(self, session_key: str) -> Any | None:
        """Return the exact live scope for a queue operation, if scope mode is on.

        A queue is constructed per PersonaRuntime, but callbacks may outlive the
        request ContextVar that created them.  In scoped mode a raw token alone is
        therefore never authority to read, recover, or persist queue state.
        """

        registry = getattr(self._p, "_scope_runtime_registry", None)
        if registry is None:
            return None
        getter = getattr(self._p, "_bound_runtime", None)
        if not callable(getter):
            return None
        try:
            binding = getter()
        except Exception:
            return None
        if binding is None:
            return None
        if getattr(binding.persona_runtime, "background_queue", None) is not self:
            return None
        if (
            self._owner_persona_ref is not None
            and binding.persona_runtime.persona_ref != self._owner_persona_ref
        ):
            return None
        scope = binding.scope
        if scope.storage_token != session_key:
            return None
        return scope if registry.is_live_session(scope) else None

    def _requires_scope(self) -> bool:
        return getattr(self._p, "_scope_runtime_registry", None) is not None

    def _may_access_session(self, session_key: str) -> bool:
        return not self._requires_scope() or self._scope_for_session(session_key) is not None

    def checkpoint_kv_key(self, session_key: str) -> str:
        """生成指定 session 的检查点 KV 存储键。

        Args:
            session_key: 会话标识。

        Returns:
            格式为 "sylanne:bg_post_checkpoint:{safe_key}" 的 KV 键。
        """
        safe = session_key.replace("/", "_").replace("\\", "_")
        return f"sylanne:bg_post_checkpoint:{safe}"

    def job_to_dict(self, job: Any) -> dict[str, Any]:
        """将任务对象序列化为字典（兼容不同来源的 job 对象）。

        Args:
            job: 任务对象（BackgroundPostJob 或兼容对象）。

        Returns:
            序列化后的字典。
        """
        return {
            "reply_text": getattr(job, "reply_text", ""),
            "context_key": getattr(job, "context_key", ""),
            "sequence": getattr(job, "sequence", 0),
            "enqueued_at": getattr(job, "enqueued_at", 0.0),
            "attempts": getattr(job, "attempts", 0),
            "next_retry_at": getattr(job, "next_retry_at", 0.0),
            "last_error_type": getattr(job, "last_error_type", ""),
            "last_error_message": getattr(job, "last_error_message", ""),
            "last_failed_at": getattr(job, "last_failed_at", 0.0),
            "dead_lettered_at": getattr(job, "dead_lettered_at", 0.0),
        }

    # ------------------------------------------------------------------
    # 自适应工作者决策
    # ------------------------------------------------------------------

    def adaptive_worker_decision(
        self, session_key: str = "", *, commit_scale: bool = False
    ) -> dict[str, Any]:
        """计算期望的工作者数量，基于队列深度和资源压力。

        决策逻辑：
        1. 根据队列深度映射到目标工作者数（1~6 阶梯）
        2. 受环境资源压力上限约束
        3. 动态扩缩容有冷却间隔（5秒），防止频繁抖动
        4. 全局工作者预算限制（跨 session 总计不超过 6）

        Args:
            session_key: 会话标识。
            commit_scale: 是否提交扩缩容决策（True 时更新状态）。

        Returns:
            决策结果字典，包含 desired_workers/dispatch_workers/reasons 等。
        """
        if not self._may_access_session(session_key):
            return {
                "desired_workers": 0,
                "dynamic_extra_workers": 0,
                "reasons": ["scope_unavailable"],
                "idle_workers_close_automatically": True,
                "queue_target_workers": 0,
                "target_workers": 0,
                "dispatch_workers": 0,
                "global_worker_cap": 6,
                "global_active_other_workers": 0,
                "resource_pressure": {"level": "unknown", "reason": "scope_unavailable"},
                "scale_state": {"committed": False},
            }
        cfg = self._p.config or {}
        dynamic_enabled = bool(cfg.get("enable_dynamic_background_workers"))
        queue = self._p._store.background_post_queues.get(session_key, collections.deque())
        queue_depth = len(queue)
        active = self._p._store.background_post_active
        global_active_other = sum(len(v) for k, v in active.items() if k != session_key)
        global_cap = 6
        now = self._observed_now()
        # 获取资源压力评估（CPU/内存负载）
        resource_pressure_fn = getattr(
            self._p, "_background_post_resource_pressure", None
        )
        resource_pressure = (
            resource_pressure_fn()
            if resource_pressure_fn and callable(resource_pressure_fn)
            else {
                "level": "normal",
                "worker_cap": global_cap,
                "cpu_load_ratio": 0.0,
                "memory_load_ratio": 0.0,
                "reason": "stable",
            }
        )
        env_cap = resource_pressure.get("worker_cap", global_cap)
        env_level = resource_pressure.get("level", "normal")
        # 队列深度 → 目标工作者数的阶梯映射
        if queue_depth <= 1:
            queue_target = 1
        elif queue_depth <= 2:
            queue_target = 2
        elif queue_depth <= 5:
            queue_target = 3
        elif queue_depth <= 10:
            queue_target = 4
        elif queue_depth <= 20:
            queue_target = 5
        else:
            queue_target = 6
        target_workers = min(queue_target, env_cap)
        reasons: list[str] = []
        if not dynamic_enabled:
            reasons.append("dynamic_scale_disabled")
            desired = 1
            dynamic_extra = 0
        else:
            worker_state = self._p._store.background_post_worker_state
            state_entry = worker_state.get(session_key, {})
            last_scale_at = state_entry.get("last_scale_at", 0.0)
            current_level = state_entry.get("current_level", 1)
            scale_interval = 5.0  # 扩缩容冷却间隔（秒）
            if commit_scale:
                if not state_entry:
                    # 首次扩容：直接设为 2
                    desired = 2
                    worker_state.set(session_key, {
                        "last_scale_at": now,
                        "current_level": desired,
                        "committed": True,
                    })
                    reasons.append("worker_scale_initial")
                elif now - last_scale_at < scale_interval:
                    # 冷却期内：保持当前水平
                    desired = current_level
                    reasons.append("worker_scale_cooldown")
                else:
                    # 逐步扩容：每次 +1，不超过目标
                    desired = min(current_level + 1, target_workers, env_cap)
                    worker_state.set(session_key, {
                        "last_scale_at": now,
                        "current_level": desired,
                        "committed": True,
                    })
                    reasons.append("worker_scale_step_up")
            else:
                desired = state_entry.get("current_level", 2) if state_entry else 2
            desired = min(desired, target_workers, env_cap)
            dynamic_extra = max(0, desired - 1)
            if env_level == "high":
                reasons.append("environment_pressure_high")
            elif env_level == "unknown":
                reasons.append("environment_pressure_unknown")
        dispatch_workers = desired if dynamic_enabled else 1
        # 全局预算检查：其他 session 已占用的工作者不能超过总上限
        if global_active_other >= global_cap:
            dispatch_workers = 0
            reasons.append("global_worker_budget_exhausted")
        else:
            dispatch_workers = min(dispatch_workers, global_cap - global_active_other)
        scale_state: dict[str, Any] = {
            "committed": commit_scale and dynamic_enabled,
            "scale_interval_seconds": 5.0,
        }
        if commit_scale and dynamic_enabled:
            ws = self._p._store.background_post_worker_state.get(session_key, {})
            scale_state.update(ws)
        return {
            "desired_workers": desired if dynamic_enabled else 1,
            "dynamic_extra_workers": dynamic_extra if dynamic_enabled else 0,
            "reasons": reasons,
            "idle_workers_close_automatically": True,
            "queue_target_workers": queue_target,
            "target_workers": target_workers,
            "dispatch_workers": dispatch_workers,
            "global_worker_cap": global_cap,
            "global_active_other_workers": global_active_other,
            "resource_pressure": resource_pressure,
            "scale_state": scale_state,
        }

    def max_workers(self, session_key: str = "") -> int:
        """返回指定 session 提交后的最大工作者数。

        Args:
            session_key: 会话标识。

        Returns:
            至少为 1 的工作者数量。
        """
        decision = self.adaptive_worker_decision(session_key, commit_scale=True)
        return max(1, decision.get("desired_workers", 1))

    def _check_backpressure(self, queue: collections.deque, session_key: str) -> None:
        """当队列长度超过 maxlen 的 80% 时记录背压告警。

        Args:
            queue: 待检查的队列。
            session_key: 会话标识（用于日志）。
        """
        if queue.maxlen and len(queue) >= queue.maxlen * 0.8:
            logger.warning(
                "Background post queue backpressure: %d/%d (%.0f%%) for session %s",
                len(queue),
                queue.maxlen,
                len(queue) / queue.maxlen * 100,
                session_key,
            )

    # ------------------------------------------------------------------
    # 回收过期租约的活跃任务
    # ------------------------------------------------------------------

    def recover_expired_active(self, session_key: str) -> int:
        """将租约过期的活跃任务回收到待处理队列。

        当工作者崩溃或超时未完成时，其持有的任务租约会过期，
        此方法将这些任务重新放回队列等待重新处理。

        Args:
            session_key: 会话标识。

        Returns:
            回收的任务数量。
        """
        if not self._may_access_session(session_key):
            return 0
        active = self._p._store.background_post_active.get(session_key, {})
        queue = self._p._store.background_post_queues.get_or_create(
            session_key, lambda: collections.deque(maxlen=500)
        )
        now = self._observed_now()
        recovered = 0
        expired_seqs = [
            seq
            for seq, job in active.items()
            if getattr(job, "lease_until", 0) and job.lease_until < now
        ]
        for seq in sorted(expired_seqs):
            job = active.pop(seq)
            # 清除租约信息，使任务可被重新 lease
            job.leased_at = 0.0
            job.lease_until = 0.0
            if queue.maxlen and len(queue) >= queue.maxlen:
                logger.warning(
                    "Background post queue full (maxlen=%d) for session %s, "
                    "dropping oldest job",
                    queue.maxlen,
                    session_key,
                )
            queue.append(job)
            recovered += 1
        # 按序号重新排序，保证处理顺序
        queue_list = sorted(queue, key=lambda j: j.sequence)
        queue.clear()
        queue.extend(queue_list)
        self._check_backpressure(queue, session_key)
        return recovered

    # ------------------------------------------------------------------
    # 调度检查点（防抖）
    # ------------------------------------------------------------------

    def schedule_checkpoint(self, session_key: str) -> None:
        """调度一次防抖的检查点保存。

        多次快速调用只会触发一次实际保存（debounce），
        避免高频入队时产生过多 IO 操作。

        Args:
            session_key: 会话标识。
        """
        scope = self._scope_for_session(session_key)
        if self._requires_scope() and scope is None:
            return
        checkpoint_tasks = self._p._store.background_post_checkpoint_tasks
        debounce = float(
            (self._p.config or {}).get(
                "background_post_checkpoint_debounce_seconds", 0.75
            )
        )
        # O(1) dict lookup instead of iterating the full set
        existing = checkpoint_tasks.get(session_key)
        if existing is not None and not existing.done():
            return

        async def _debounced_save() -> None:
            await asyncio.sleep(debounce)
            if scope is not None:
                registry = getattr(self._p, "_scope_runtime_registry", None)
                if registry is None or not registry.is_live_session(scope):
                    return
            await self.save_checkpoint(session_key)

        task = safe_ensure_future(_debounced_save(), name="checkpoint_debounced_save")
        if task is None:
            return
        if scope is not None:
            registry = getattr(self._p, "_scope_runtime_registry", None)
            if registry is None or not registry.track_session_task(scope, task):
                task.cancel()
                return
        checkpoint_tasks.set(session_key, task)

        def _on_done(t: asyncio.Task) -> None:
            if checkpoint_tasks.get(session_key) is t:
                checkpoint_tasks.pop(session_key, None)

        task.add_done_callback(_on_done)

    # ------------------------------------------------------------------
    # 排空评估队列
    # ------------------------------------------------------------------

    async def drain_assessments(self, session_key: str) -> None:
        """处理指定 session 队列中所有待处理的评估任务。

        逐个取出任务执行情感评估，成功后保存状态并更新已提交序号。
        失败的任务允许一次轻量重试（_retries），超过后丢弃并记录警告。

        Args:
            session_key: 会话标识。
        """
        if not self._may_access_session(session_key):
            return
        queue = self._p._store.background_post_queues.get(session_key)
        if not queue:
            return
        retry_jobs: list[BackgroundPostJob] = []
        while queue:
            if not self._may_access_session(session_key):
                return
            job = queue.popleft()
            try:
                assess_fn = getattr(self._p, "_assess_emotion", None)
                if assess_fn and callable(assess_fn):
                    observation = await assess_fn(
                        session_key=session_key,
                        event=job.event,
                        phase="post_response",
                        context_text=job.context_key,
                        current_text=job.reply_text,
                    )
                else:
                    observation = None
                save_fn = getattr(self._p, "_save_state", None)
                if save_fn and callable(save_fn) and observation:
                    await save_fn(session_key, observation)
                # 更新已提交序号水位线
                self._p._store.background_post_last_committed.set(session_key, job.sequence)
            except Exception as exc:
                retries = job._retries
                if retries < 1:
                    # 允许一次轻量重试
                    job._retries = retries + 1
                    retry_jobs.append(job)
                    logger.debug(f"Sylanne assess retry queued: {exc}")
                else:
                    logger.warning(f"Sylanne assess failed after retry: {exc}")
                continue
        # 将需要重试的任务放回队列末尾
        for job in retry_jobs:
            queue.append(job)
        if retry_jobs:
            self._check_backpressure(queue, session_key)

    # ------------------------------------------------------------------
    # 保存检查点
    # ------------------------------------------------------------------

    async def save_checkpoint(self, session_key: str) -> None:
        """将队列状态持久化到 KV 存储。

        保存内容包括：待处理队列、死信队列、最新入队序号、最后提交序号。
        队列为空时删除 KV 条目以节省存储。

        Args:
            session_key: 会话标识。
        """
        if not self._may_access_session(session_key):
            return
        put_fn = getattr(self._p, "put_kv_data", None)
        delete_fn = getattr(self._p, "delete_kv_data", None)
        if not put_fn or not callable(put_fn):
            return
        queue = self._p._store.background_post_queues.get(session_key, collections.deque())
        dead_letters = self._p._store.background_post_dead_letters.get(
            session_key, collections.deque()
        )
        latest = self._p._store.background_post_latest_enqueued.get(session_key, 0)
        committed = self._p._store.background_post_last_committed.get(session_key, 0)
        kv_key = self.checkpoint_kv_key(session_key)
        # 队列和死信都为空时，删除 KV 条目
        if not queue and not dead_letters:
            if delete_fn and callable(delete_fn):
                if not self._may_access_session(session_key):
                    return
                await delete_fn(kv_key)
            return
        jobs = [self.job_to_dict(j) for j in queue]
        # 死信序列化时剥离大文本字段，只保留元数据
        dead: list[dict[str, Any]] = []
        for j in dead_letters:
            d = self.job_to_dict(j)
            d.pop("reply_text", None)
            d.pop("context_key", None)
            d.pop("response_text", None)
            d.pop("request_context_text", None)
            dead.append(d)
        checkpoint = {
            "schema_version": "astrbot.background_post_queue.v2",
            "session_key": session_key,
            "latest_enqueued": latest,
            "last_committed": committed,
            "jobs": jobs,
            "dead_letters": dead,
        }
        # A release/recreation can race the async KV boundary.  Re-check the
        # exact runtime before the write; stale callbacks then become no-ops.
        if not self._may_access_session(session_key):
            return
        await put_fn(kv_key, checkpoint)

    # ------------------------------------------------------------------
    # 从 KV 检查点恢复队列
    # ------------------------------------------------------------------

    async def recover_queue(self, session_key: str) -> bool:
        """从 KV 存储恢复队列状态（用于重启后恢复）。

        恢复内容：待处理队列、死信队列、序号水位线。
        恢复后的任务 event 为 None（原始事件对象不可序列化），
        但 reply_text/context_key 等评估所需数据完整保留。

        Args:
            session_key: 会话标识。

        Returns:
            True 表示成功恢复，False 表示无数据或恢复失败。
        """
        if not self._may_access_session(session_key):
            return False
        get_fn = getattr(self._p, "get_kv_data", None)
        if not get_fn or not callable(get_fn):
            return False
        kv_key = self.checkpoint_kv_key(session_key)
        try:
            checkpoint = await get_fn(kv_key, None)
        except Exception:
            return False
        if not checkpoint:
            return False

        jobs_data = checkpoint.get("jobs", [])
        dead_data = checkpoint.get("dead_letters", [])
        queue: collections.deque[BackgroundPostJob] = collections.deque(maxlen=500)
        for jd in jobs_data:
            job = BackgroundPostJob(
                event=None,
                identity="",
                reply_text=jd.get("reply_text", ""),
                context_key=jd.get("context_key", ""),
                sequence=jd.get("sequence", 0),
                enqueued_at=jd.get("enqueued_at", 0.0),
            )
            job.attempts = jd.get("attempts", 0)
            job.next_retry_at = jd.get("next_retry_at", 0.0)
            job.last_error_type = jd.get("last_error_type", "")
            job.last_error_message = jd.get("last_error_message", "")
            job.last_failed_at = jd.get("last_failed_at", 0.0)
            job.dead_lettered_at = jd.get("dead_lettered_at", 0.0)
            job.leased_at = 0.0
            job.lease_until = 0.0
            queue.append(job)
        dead_queue: collections.deque[BackgroundPostJob] = collections.deque(maxlen=500)
        for dd in dead_data:
            job = BackgroundPostJob(
                event=None,
                identity="",
                reply_text=dd.get("reply_text", ""),
                context_key=dd.get("context_key", ""),
                sequence=dd.get("sequence", 0),
                enqueued_at=dd.get("enqueued_at", 0.0),
            )
            job.attempts = dd.get("attempts", 0)
            job.last_error_type = dd.get("last_error_type", "")
            job.last_failed_at = dd.get("last_failed_at", 0.0)
            job.dead_lettered_at = dd.get("dead_lettered_at", 0.0)
            job.leased_at = 0.0
            job.lease_until = 0.0
            dead_queue.append(job)
        # Re-check after IO: a callback from a released/recreated generation must
        # never repopulate the replacement scope's queue maps.
        if not self._may_access_session(session_key):
            return False
        # 恢复到 store 的状态容器中
        self._p._store.background_post_queues.set(session_key, queue)
        self._p._store.background_post_dead_letters.set(session_key, dead_queue)
        self._p._store.background_post_sequence.set(session_key, checkpoint.get(
            "latest_enqueued", 0
        ))
        self._p._store.background_post_latest_enqueued.set(session_key, checkpoint.get(
            "latest_enqueued", 0
        ))
        self._p._store.background_post_last_committed.set(session_key, checkpoint.get(
            "last_committed", 0
        ))
        self._p._background_post_recovered_sessions.add(session_key)
        self._check_backpressure(queue, session_key)
        return True


# ---------------------------------------------------------------------------
# ScopedBackgroundPostQueue -- inactive scope-v1 persistence path
# ---------------------------------------------------------------------------


class ScopedBackgroundPostQueue:
    """Scope-v1 queue state bound permanently to one persistence capability.

    This deliberately does not share the legacy ``BackgroundPostQueue`` API:
    callers never provide a session key and no legacy KV/checkpoint path is
    available.  Every read and write goes through the one captured, frozen
    ``ScopedPersistenceGateway``.
    """

    _COMPONENT = "background-queue"
    _SCHEMA_VERSION = "sylanne.scoped-background-queue.v1"
    _MAX_JOBS = 500

    def __init__(self, persistence: ScopedPersistenceGateway) -> None:
        if type(persistence) is not self._gateway_type():
            raise ValueError("persistence must be a ScopedPersistenceGateway")
        self._persistence = persistence
        self._generation = 0
        self._queue: collections.deque[BackgroundPostJob] = collections.deque(
            maxlen=self._MAX_JOBS
        )
        self._active: dict[int, BackgroundPostJob] = {}
        self._dead_letters: collections.deque[BackgroundPostJob] = collections.deque(
            maxlen=self._MAX_JOBS
        )
        self._latest_enqueued = 0
        self._last_committed = 0

    @staticmethod
    def _gateway_type() -> type:
        """Load scope-v1 support only when the inactive scoped path is used."""

        from sylanne_alpha.scope_repository import ScopedPersistenceGateway

        return ScopedPersistenceGateway

    @property
    def persistence(self) -> ScopedPersistenceGateway:
        """The only capability this queue may use for durable state."""

        return self._persistence

    @property
    def pending_count(self) -> int:
        return len(self._queue)

    @property
    def active_count(self) -> int:
        return len(self._active)

    def _ensure_live(self) -> None:
        """Fence local work to the exact frozen scope generation."""

        self._persistence.repository.validate_session_scope(self._persistence.scope)

    @staticmethod
    def _require_time(value: object, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name} must be a finite number")
        result = float(value)
        if not math.isfinite(result):
            raise ValueError(f"{name} must be a finite number")
        return result

    @staticmethod
    def _require_non_negative_int(value: object, name: str) -> int:
        if type(value) is not int or value < 0:
            raise ValueError(f"{name} must be a non-negative int")
        return value

    @classmethod
    def _serialize_job(cls, job: BackgroundPostJob) -> dict[str, object]:
        """Persist only queue mechanics and assessment text, never identity/event."""

        return {
            "reply_text": job.reply_text,
            "context_key": job.context_key,
            "sequence": job.sequence,
            "enqueued_at": job.enqueued_at,
            "attempts": job.attempts,
            "next_retry_at": job.next_retry_at,
            "last_error_type": job.last_error_type,
            "last_error_message": job.last_error_message,
            "last_failed_at": job.last_failed_at,
            "dead_lettered_at": job.dead_lettered_at,
        }

    @classmethod
    def _deserialize_job(cls, payload: object) -> BackgroundPostJob:
        if type(payload) is not dict:
            raise ValueError("background queue job must be an exact dict")
        reply_text = payload.get("reply_text")
        context_key = payload.get("context_key")
        if type(reply_text) is not str or type(context_key) is not str:
            raise ValueError("background queue job text must be str")
        job = BackgroundPostJob(
            event=None,
            identity="",
            reply_text=reply_text,
            context_key=context_key,
            sequence=cls._require_non_negative_int(payload.get("sequence"), "sequence"),
            enqueued_at=cls._require_time(payload.get("enqueued_at"), "enqueued_at"),
        )
        job.attempts = cls._require_non_negative_int(payload.get("attempts"), "attempts")
        job.next_retry_at = cls._require_time(payload.get("next_retry_at"), "next_retry_at")
        last_error_type = payload.get("last_error_type")
        last_error_message = payload.get("last_error_message")
        if type(last_error_type) is not str or type(last_error_message) is not str:
            raise ValueError("background queue error metadata must be str")
        job.last_error_type = last_error_type
        job.last_error_message = last_error_message
        job.last_failed_at = cls._require_time(
            payload.get("last_failed_at"), "last_failed_at"
        )
        job.dead_lettered_at = cls._require_time(
            payload.get("dead_lettered_at"), "dead_lettered_at"
        )
        return job

    def _checkpoint_payload(self) -> dict[str, object]:
        return {
            "schema_version": self._SCHEMA_VERSION,
            "latest_enqueued": self._latest_enqueued,
            "last_committed": self._last_committed,
            "jobs": [self._serialize_job(job) for job in self._queue],
            # A process restart has no valid worker lease.  Recovery folds these
            # jobs back into the pending queue after it validates the snapshot.
            "active_jobs": [self._serialize_job(job) for job in self._active.values()],
            "dead_letters": [
                self._serialize_job(job) for job in self._dead_letters
            ],
        }

    def enqueue(self, job: BackgroundPostJob) -> bool:
        """Add one in-memory job to this captured scope's queue."""

        self._ensure_live()
        if type(job) is not BackgroundPostJob:
            raise ValueError("job must be a BackgroundPostJob")
        if len(self._queue) >= self._MAX_JOBS:
            return False
        self._queue.append(job)
        self._latest_enqueued = max(self._latest_enqueued, job.sequence)
        return True

    def recover_expired_active(self, *, now: float) -> int:
        """Return only this scope's expired leases to its local pending queue."""

        self._ensure_live()
        observed_now = self._require_time(now, "now")
        expired = [
            sequence
            for sequence, job in self._active.items()
            if job.lease_until and job.lease_until < observed_now
        ]
        for sequence in sorted(expired):
            job = self._active.pop(sequence)
            job.leased_at = 0.0
            job.lease_until = 0.0
            if len(self._queue) < self._MAX_JOBS:
                self._queue.append(job)
        self._queue = collections.deque(
            sorted(self._queue, key=lambda job: job.sequence), maxlen=self._MAX_JOBS
        )
        return len(expired)

    def lease_next(self, *, now: float, lease_seconds: float) -> BackgroundPostJob | None:
        """Lease the next due job without consulting any current-session lookup."""

        self._ensure_live()
        observed_now = self._require_time(now, "now")
        duration = self._require_time(lease_seconds, "lease_seconds")
        if duration <= 0.0:
            raise ValueError("lease_seconds must be positive")
        self.recover_expired_active(now=observed_now)
        if not self._queue or self._queue[0].next_retry_at > observed_now:
            return None
        job = self._queue.popleft()
        job.leased_at = observed_now
        job.lease_until = observed_now + duration
        self._active[job.sequence] = job
        return job

    def complete(self, job_or_sequence: BackgroundPostJob | int) -> bool:
        """Acknowledge one active job from the captured scope only."""

        self._ensure_live()
        if type(job_or_sequence) is BackgroundPostJob:
            sequence = job_or_sequence.sequence
            expected_job: BackgroundPostJob | None = job_or_sequence
        else:
            sequence = self._require_non_negative_int(job_or_sequence, "sequence")
            expected_job = None
        active = self._active.get(sequence)
        if active is None or (expected_job is not None and active is not expected_job):
            return False
        self._active.pop(sequence)
        active.leased_at = 0.0
        active.lease_until = 0.0
        self._last_committed = max(self._last_committed, sequence)
        return True

    async def drain(
        self,
        processor: Callable[[BackgroundPostJob], object],
        *,
        now: float,
        lease_seconds: float = 30.0,
    ) -> int:
        """Process due jobs through a caller-supplied worker bound to this scope."""

        if not callable(processor):
            raise ValueError("processor must be callable")
        observed_now = self._require_time(now, "now")
        processed = 0
        while True:
            job = self.lease_next(now=observed_now, lease_seconds=lease_seconds)
            if job is None:
                return processed
            outcome = processor(job)
            if inspect.isawaitable(outcome):
                outcome = await outcome
            if outcome is False:
                return processed
            if not self.complete(job):
                return processed
            processed += 1

    async def _save_with_gateway(
        self,
        gateway: ScopedPersistenceGateway,
        *,
        expected_generation: int,
        payload: dict[str, object],
    ) -> bool:
        """Save through exactly the gateway and CAS state captured by the caller."""

        gateway.repository.validate_session_scope(gateway.scope)
        next_generation = gateway.save(
            self._COMPONENT,
            expected_generation=expected_generation,
            payload=payload,
        )
        if gateway is self._persistence and self._generation == expected_generation:
            self._generation = next_generation
        return True

    async def save_checkpoint(self) -> bool:
        """CAS-save this queue's checkpoint to its exact scope component."""

        return await self._save_with_gateway(
            self._persistence,
            expected_generation=self._generation,
            payload=self._checkpoint_payload(),
        )

    def schedule_checkpoint(self, *, delay_seconds: float) -> asyncio.Task[bool]:
        """Schedule a checkpoint that cannot follow a scope reset or replacement."""

        delay = self._require_time(delay_seconds, "delay_seconds")
        if delay < 0.0:
            raise ValueError("delay_seconds must be non-negative")
        gateway = self._persistence
        generation = self._generation
        payload = self._checkpoint_payload()

        async def _delayed_checkpoint() -> bool:
            await asyncio.sleep(delay)
            # Keep the legacy module import-independent: this scoped-only
            # dependency is resolved only when delayed scoped work actually
            # runs, but bind its exact exception type before entering the
            # operation so unrelated failures cannot be misclassified.
            from sylanne_alpha.scope_repository import StaleScopeWrite

            try:
                return await self._save_with_gateway(
                    gateway,
                    expected_generation=generation,
                    payload=payload,
                )
            except StaleScopeWrite:
                # Delayed work is intentionally discarded instead of finding a
                # replacement session/scope to write into.
                return False

        return asyncio.create_task(
            _delayed_checkpoint(),
            name="scoped_background_queue_checkpoint",
        )

    async def recover_queue(self) -> bool:
        """Recover only the checkpoint owned by this frozen scope capability."""

        self._ensure_live()
        snapshot = self._persistence.load(self._COMPONENT)
        if snapshot is None:
            return False
        payload = snapshot.payload
        if payload.get("schema_version") != self._SCHEMA_VERSION:
            return False
        jobs_data = payload.get("jobs")
        active_data = payload.get("active_jobs")
        dead_data = payload.get("dead_letters")
        try:
            if (
                type(jobs_data) is not list
                or type(active_data) is not list
                or type(dead_data) is not list
            ):
                return False
            if (
                len(jobs_data) + len(active_data) > self._MAX_JOBS
                or len(dead_data) > self._MAX_JOBS
            ):
                return False
            recovered_jobs = [self._deserialize_job(job) for job in jobs_data]
            # Leases cannot survive a restart.  They become pending only after
            # the exact frozen component has been read and validated.
            recovered_jobs.extend(self._deserialize_job(job) for job in active_data)
            recovered_dead = [self._deserialize_job(job) for job in dead_data]
            latest = self._require_non_negative_int(
                payload.get("latest_enqueued"), "latest_enqueued"
            )
            committed = self._require_non_negative_int(
                payload.get("last_committed"), "last_committed"
            )
        except ValueError:
            return False
        self._ensure_live()
        self._queue = collections.deque(
            sorted(recovered_jobs, key=lambda job: job.sequence), maxlen=self._MAX_JOBS
        )
        self._active = {}
        self._dead_letters = collections.deque(recovered_dead, maxlen=self._MAX_JOBS)
        self._latest_enqueued = max(
            [latest, *(job.sequence for job in recovered_jobs)]
        )
        self._last_committed = committed
        self._generation = snapshot.generation
        return True
