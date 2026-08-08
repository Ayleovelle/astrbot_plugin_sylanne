"""Bridge AstrBot active-runner follow-ups to Sylanne delivery epochs.

AstrBot 与 Sylanne 对“工具执行期间又来一条消息”的默认理解不同：
AstrBot 会先尝试把它塞进正在运行的工具轮；Sylanne 的 delivery epoch 则会把
每条新消息都当作新一轮，并让旧 epoch 的回复失效。本模块只负责协调这两个
生命周期，不能提前替 AstrBot 消费 follow-up，也不能让真正的新一轮漏掉中断。
"""

from __future__ import annotations

import logging
import time
from typing import Any

try:
    from astrbot.api import logger
except ImportError:  # pragma: no cover - standalone import fallback
    logger = logging.getLogger("astrbot_plugin_sylanne")


def event_extra(event: Any, key: str, default: Any = None) -> Any:
    """Read both AstrBot's one-argument API and permissive test doubles."""

    get_extra = getattr(event, "get_extra", None)
    if not callable(get_extra):
        return default
    try:
        value = get_extra(key)
    except TypeError:
        try:
            value = get_extra(key, default)
        except Exception:
            return default
    except Exception:
        return default
    return default if value is None else value


def register_inbound_event_once(plugin: Any, event: Any) -> bool:
    """Claim one adapter event; return False for a duplicate delivery."""

    if bool(event_extra(event, "_syl_inbound_registered", False)):
        return False

    set_extra = getattr(event, "set_extra", None)
    duplicate = False
    key = ""
    seen: Any = None
    registered_new = False
    try:
        umo = str(getattr(event, "unified_msg_origin", "") or "")
        mid = getattr(getattr(event, "message_obj", None), "message_id", None)
        key = (
            umo + "\x00" + mid
            if umo and isinstance(mid, str) and mid.strip()
            else ""
        )
        seen = getattr(plugin, "_inbound_seen", None)
        if key and seen is not None and callable(set_extra):
            duplicate = key in seen
            if not duplicate:
                seen[key] = time.time()
                registered_new = True
    except Exception:
        logger.warning(
            "Sylanne inbound epoch registration failed open",
            exc_info=True,
        )

    if callable(set_extra):
        try:
            set_extra("_syl_inbound_duplicate", duplicate)
            set_extra("_syl_inbound_registered", True)
        except Exception:
            if registered_new and not bool(
                event_extra(event, "_syl_inbound_registered", False)
            ):
                try:
                    seen.pop(key, None)
                except Exception:
                    pass
    return not duplicate


def active_follow_up_target(event: Any) -> tuple[bool, str]:
    """只读判断该消息能否交给当前 runner，绝不在这里真正入队。

    真正入队仍由 AstrBot ``try_capture_follow_up`` 完成。若插件在这里直接调用
    它，框架稍后还会再调用一次，同一句话就会进入工具轮两遍。
    """

    try:
        from astrbot.core.pipeline.process_stage.follow_up import (
            _ACTIVE_AGENT_RUNNERS,
        )

        sender_getter = getattr(event, "get_sender_id", None)
        sender_id = str(sender_getter() or "") if callable(sender_getter) else ""
        umo = str(getattr(event, "unified_msg_origin", "") or "")
        if not sender_id or not umo:
            return False, ""

        # AstrBot 只在 AgentRequestSubStage 中调用 try_capture_follow_up；普通
        # 群聊噪音不会走到那里。若这里仍把它标成 deferred，后面也等不到
        # on_waiting_llm_request 来结算，旧回复便永远不会被它中断。
        if not bool(getattr(event, "is_at_or_wake_command", False)):
            return False, ""

        runner = _ACTIVE_AGENT_RUNNERS.get(umo)
        if runner is None:
            return False, ""
        done = getattr(runner, "done", None)
        if callable(done) and done():
            return False, ""

        run_context = getattr(runner, "run_context", None)
        runner_event = getattr(getattr(run_context, "context", None), "event", None)
        active_sender_getter = getattr(runner_event, "get_sender_id", None)
        active_sender_id = (
            str(active_sender_getter() or "")
            if callable(active_sender_getter)
            else ""
        )
        if not active_sender_id or active_sender_id != sender_id:
            return False, ""
        if bool(event_extra(runner_event, "agent_stop_requested", False)):
            return False, ""

        target_mid = getattr(
            getattr(runner_event, "message_obj", None),
            "message_id",
            None,
        )
        return True, str(target_mid) if target_mid is not None else ""
    except Exception:
        # Framework internals are only a compatibility hint. Immediate epoch
        # advancement is safer than accidentally hiding a genuine new turn.
        return False, ""


def commit_inbound_delivery_epoch(
    plugin: Any,
    event: Any,
    session_key: str,
    *,
    reason: str,
) -> int:
    """Commit one inbound turn and interrupt an older segmented delivery."""

    if bool(event_extra(event, "_syl_input_epoch_committed", False)):
        value = event_extra(event, "_syl_input_epoch", 0)
        return int(value) if isinstance(value, int) and not isinstance(value, bool) else 0

    epochs = getattr(plugin._store, "conversation_input_epoch", None)
    input_epoch = 0
    if epochs is not None:
        try:
            input_epoch = int(epochs.get(session_key, 0) or 0) + 1
            epochs.set(session_key, input_epoch)
        except Exception:
            logger.warning(
                "Sylanne inbound epoch advance failed: session=%s",
                session_key,
                exc_info=True,
            )
            input_epoch = 0

    set_extra = getattr(event, "set_extra", None)
    if callable(set_extra):
        try:
            set_extra("_syl_input_epoch", input_epoch)
            set_extra("_syl_input_epoch_committed", True)
            set_extra("_syl_follow_up_deferred", False)
        except Exception:
            pass

    active_turns = getattr(plugin._store, "segmented_delivery_turns", None)
    if active_turns is None:
        return input_epoch
    try:
        turn = active_turns.get(session_key)
        interrupt = getattr(turn, "interrupt", None)
        if callable(interrupt):
            interrupt()
            logger.info(
                "Sylanne confirmed older reply interruption: "
                "session=%s epoch=%d reason=%s",
                session_key,
                input_epoch,
                reason,
            )
    except Exception:
        logger.warning(
            "Sylanne active delivery interrupt failed: session=%s",
            session_key,
            exc_info=True,
        )
    return input_epoch


def advance_inbound_delivery_epoch(plugin: Any, event: Any, session_key: str) -> None:
    """Immediately commit a real inbound message."""

    if register_inbound_event_once(plugin, event):
        commit_inbound_delivery_epoch(
            plugin,
            event,
            session_key,
            reason="new_inbound",
        )


def register_or_defer_inbound_delivery_epoch(
    plugin: Any,
    event: Any,
    session_key: str,
) -> None:
    """先让 AstrBot 判断补话归属，再决定是否推进 delivery epoch。

    这里只做“暂缓”，不是认定消息已经合并：

    * AstrBot 吃掉补话时，当前工具轮沿用原 epoch，最终答案仍能发送；
    * AstrBot 没吃掉时，会继续进入 ``on_waiting_llm_request``，由那个钩子
      把本事件提交为新 epoch，并按原语义中断旧回复。
    """

    if not register_inbound_event_once(plugin, event):
        return

    is_follow_up, target_run_id = active_follow_up_target(event)
    if not is_follow_up:
        commit_inbound_delivery_epoch(
            plugin,
            event,
            session_key,
            reason="new_inbound",
        )
        return

    epochs = getattr(plugin._store, "conversation_input_epoch", None)
    current_epoch = 0
    if epochs is not None:
        try:
            current_epoch = int(epochs.get(session_key, 0) or 0)
        except Exception:
            current_epoch = 0

    set_extra = getattr(event, "set_extra", None)
    if callable(set_extra):
        try:
            set_extra("_syl_input_epoch", current_epoch)
            set_extra("_syl_input_epoch_committed", False)
            set_extra("_syl_follow_up_deferred", True)
            set_extra("_syl_follow_up_target_run_id", target_run_id)
            if not bool(event_extra(event, "_syl_follow_up_deferred", False)):
                raise RuntimeError("follow-up marker did not round-trip")
        except Exception:
            commit_inbound_delivery_epoch(
                plugin,
                event,
                session_key,
                reason="follow_up_marker_failed",
            )
            return
    else:
        commit_inbound_delivery_epoch(
            plugin,
            event,
            session_key,
            reason="follow_up_marker_unavailable",
        )
        return

    logger.info(
        "Sylanne inbound deferred to AstrBot follow-up arbitration: "
        "session=%s target_run_id=%s epoch=%d",
        session_key,
        target_run_id or "unknown",
        current_epoch,
    )


__all__ = [
    "active_follow_up_target",
    "advance_inbound_delivery_epoch",
    "commit_inbound_delivery_epoch",
    "event_extra",
    "register_inbound_event_once",
    "register_or_defer_inbound_delivery_epoch",
]
