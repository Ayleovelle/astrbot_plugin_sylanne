"""Background post queue logic extracted from main.py.

Provides BackgroundPostJob (data class) and BackgroundPostQueue (manager)
that encapsulate the adaptive-worker, checkpoint, and drain logic for
Sylanne's background emotion-assessment pipeline.
"""

from __future__ import annotations

import asyncio
import collections
import logging
from typing import Any

logger = logging.getLogger("astrbot_plugin_sylanne")

# ---------------------------------------------------------------------------
# Helper -- mirrors _safe_ensure_future from main.py
# ---------------------------------------------------------------------------


def _safe_ensure_future(coro: Any, name: str = "task") -> asyncio.Task[Any]:
    """Wrap a coroutine in ensure_future with exception logging."""

    async def _wrapper() -> None:
        try:
            await coro
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Background task '{name}' failed: {e}", exc_info=True)

    return asyncio.ensure_future(_wrapper())


# ---------------------------------------------------------------------------
# BackgroundPostJob -- value object for a single queued assessment job
# ---------------------------------------------------------------------------


class BackgroundPostJob:
    """A single background post-response assessment job."""

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

    def to_dict(self) -> dict[str, Any]:
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
# BackgroundPostQueue -- manager class delegating to plugin instance
# ---------------------------------------------------------------------------


class BackgroundPostQueue:
    """Encapsulates background post queue operations.

    Delegates state access to the plugin instance via ``self._p``.
    """

    def __init__(self, plugin: Any) -> None:
        self._p = plugin

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _observed_now(self) -> float:
        return self._p._observed_now()

    def checkpoint_kv_key(self, session_key: str) -> str:
        """Return the KV storage key for a session's checkpoint."""
        safe = session_key.replace("/", "_").replace("\\", "_")
        return f"sylanne:bg_post_checkpoint:{safe}"

    def job_to_dict(self, job: Any) -> dict[str, Any]:
        """Serialize a job to a plain dict."""
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
    # Adaptive worker decision
    # ------------------------------------------------------------------

    def adaptive_worker_decision(
        self, session_key: str = "", *, commit_scale: bool = False
    ) -> dict[str, Any]:
        """Compute desired worker count based on queue depth and resource pressure."""
        cfg = self._p.config or {}
        dynamic_enabled = bool(cfg.get("enable_dynamic_background_workers"))
        queue = self._p._background_post_queues.get(session_key, collections.deque())
        queue_depth = len(queue)
        active = self._p._background_post_active
        global_active_other = sum(len(v) for k, v in active.items() if k != session_key)
        global_cap = 6
        now = self._observed_now()
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
            scale_interval = 5.0
            if commit_scale:
                if not state_entry:
                    desired = 2
                    worker_state[session_key] = {
                        "last_scale_at": now,
                        "current_level": desired,
                        "committed": True,
                    }
                    reasons.append("worker_scale_initial")
                elif now - last_scale_at < scale_interval:
                    desired = current_level
                    reasons.append("worker_scale_cooldown")
                else:
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
        """Return the committed max worker count for a session."""
        decision = self.adaptive_worker_decision(session_key, commit_scale=True)
        return max(1, decision.get("desired_workers", 1))

    # ------------------------------------------------------------------
    # Recover expired active jobs
    # ------------------------------------------------------------------

    def recover_expired_active(self, session_key: str) -> int:
        """Move expired leased jobs back to the pending queue."""
        active = self._p._background_post_active.get(session_key, {})
        queue = self._p._background_post_queues.setdefault(
            session_key, collections.deque()
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
            job.leased_at = 0.0
            job.lease_until = 0.0
            queue.append(job)
            recovered += 1
        queue_list = sorted(queue, key=lambda j: j.sequence)
        queue.clear()
        queue.extend(queue_list)
        return recovered

    # ------------------------------------------------------------------
    # Schedule checkpoint (debounced)
    # ------------------------------------------------------------------

    def schedule_checkpoint(self, session_key: str) -> None:
        """Schedule a debounced checkpoint save for the given session."""
        checkpoint_tasks = self._p._background_post_checkpoint_tasks
        debounce = float(
            (self._p.config or {}).get(
                "background_post_checkpoint_debounce_seconds", 0.75
            )
        )
        for existing in list(checkpoint_tasks):
            if (
                not existing.done()
                and getattr(existing, "_checkpoint_session", None) == session_key
            ):
                return

        async def _debounced_save() -> None:
            await asyncio.sleep(debounce)
            await self.save_checkpoint(session_key)

        task = _safe_ensure_future(_debounced_save(), name="checkpoint_debounced_save")
        task._checkpoint_session = session_key  # type: ignore[attr-defined]
        checkpoint_tasks.add(task)
        task.add_done_callback(lambda t: checkpoint_tasks.discard(t))

    # ------------------------------------------------------------------
    # Drain assessments
    # ------------------------------------------------------------------

    async def drain_assessments(self, session_key: str) -> None:
        """Process all pending jobs in the queue for a session."""
        queue = self._p._background_post_queues.get(session_key)
        if not queue:
            return
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
                committed = self._p._background_post_last_committed
                committed[session_key] = job.sequence
            except Exception as e:
                logger.warning(f"Sylanne background post observe: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # Save checkpoint
    # ------------------------------------------------------------------

    async def save_checkpoint(self, session_key: str) -> None:
        """Persist queue state to KV storage."""
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
        if not queue and not dead_letters:
            if delete_fn and callable(delete_fn):
                await delete_fn(kv_key)
            return
        jobs = [self.job_to_dict(j) for j in queue]
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
    # Recover queue from KV checkpoint
    # ------------------------------------------------------------------

    async def recover_queue(self, session_key: str) -> bool:
        """Restore queue state from KV storage after restart."""
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
        queue: collections.deque[BackgroundPostJob] = collections.deque()
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
        dead_queue: collections.deque[BackgroundPostJob] = collections.deque()
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
        return True
