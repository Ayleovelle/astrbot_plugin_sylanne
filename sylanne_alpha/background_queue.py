"""后台评估队列模块。

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
import logging
from typing import Any

from sylanne_alpha.utils import safe_ensure_future

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

    def __init__(self, plugin: Any) -> None:
        """初始化队列管理器。

        Args:
            plugin: Sylanne 插件实例。
        """
        self._p = plugin

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _observed_now(self) -> float:
        """获取当前观测时间（支持基准测试时间偏移）。"""
        return self._p._observed_now()

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
        cfg = self._p.config or {}
        dynamic_enabled = bool(cfg.get("enable_dynamic_background_workers"))
        queue = self._p._background_post_queues.get(session_key, collections.deque())
        queue_depth = len(queue)
        active = self._p._background_post_active
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
            worker_state = self._p._background_post_worker_state
            state_entry = worker_state.get(session_key, {})
            last_scale_at = state_entry.get("last_scale_at", 0.0)
            current_level = state_entry.get("current_level", 1)
            scale_interval = 5.0  # 扩缩容冷却间隔（秒）
            if commit_scale:
                if not state_entry:
                    # 首次扩容：直接设为 2
                    desired = 2
                    worker_state[session_key] = {
                        "last_scale_at": now,
                        "current_level": desired,
                        "committed": True,
                    }
                    reasons.append("worker_scale_initial")
                elif now - last_scale_at < scale_interval:
                    # 冷却期内：保持当前水平
                    desired = current_level
                    reasons.append("worker_scale_cooldown")
                else:
                    # 逐步扩容：每次 +1，不超过目标
                    desired = min(current_level + 1, target_workers, env_cap)
                    worker_state[session_key] = {
                        "last_scale_at": now,
                        "current_level": desired,
                        "committed": True,
                    }
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
            ws = self._p._background_post_worker_state.get(session_key, {})
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
        active = self._p._background_post_active.get(session_key, {})
        queue = self._p._background_post_queues.setdefault(
            session_key, collections.deque(maxlen=500)
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
        checkpoint_tasks = self._p._background_post_checkpoint_tasks
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
            await self.save_checkpoint(session_key)

        task = safe_ensure_future(_debounced_save(), name="checkpoint_debounced_save")
        checkpoint_tasks[session_key] = task

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
        queue = self._p._background_post_queues.get(session_key)
        if not queue:
            return
        retry_jobs: list[BackgroundPostJob] = []
        while queue:
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
                committed = self._p._background_post_last_committed
                committed[session_key] = job.sequence
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
        put_fn = getattr(self._p, "put_kv_data", None)
        delete_fn = getattr(self._p, "delete_kv_data", None)
        if not put_fn or not callable(put_fn):
            return
        queue = self._p._background_post_queues.get(session_key, collections.deque())
        dead_letters = self._p._background_post_dead_letters.get(
            session_key, collections.deque()
        )
        latest = self._p._background_post_latest_enqueued.get(session_key, 0)
        committed = self._p._background_post_last_committed.get(session_key, 0)
        kv_key = self.checkpoint_kv_key(session_key)
        # 队列和死信都为空时，删除 KV 条目
        if not queue and not dead_letters:
            if delete_fn and callable(delete_fn):
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
        # 恢复到插件实例的状态字典中
        self._p._background_post_queues[session_key] = queue
        self._p._background_post_dead_letters[session_key] = dead_queue
        self._p._background_post_sequence[session_key] = checkpoint.get(
            "latest_enqueued", 0
        )
        self._p._background_post_latest_enqueued[session_key] = checkpoint.get(
            "latest_enqueued", 0
        )
        self._p._background_post_last_committed[session_key] = checkpoint.get(
            "last_committed", 0
        )
        self._p._background_post_recovered_sessions.add(session_key)
        self._check_backpressure(queue, session_key)
        return True
