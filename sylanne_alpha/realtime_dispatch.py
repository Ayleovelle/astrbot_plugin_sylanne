"""即时聊天调度 —— 处理分段回复、实时上下文注入和中断恢复。

职责：
  1. 分段发送：将长回复拆分为多条消息，按延迟逐条发送
  2. 中断处理：用户打断时记录断点，下轮可续接
  3. 历史影子：记录已发送的实时回复，供后续请求参考
  4. 上下文注入：将实时聊天状态注入到 LLM 请求的 system_prompt 中（不持久化）
  5. 群聊氛围注入：将群聊情绪状态格式化为 system_prompt 片段

设计原则：
  - 模拟人类对话节奏：分段发送 + 打字延迟
  - 中断友好：用户随时可以打断，未发送部分被保存
  - 上下文连续性：通过 shadow/backfill 机制保持对话连贯

与其他组件的关系：
  - 被 llm_response_pipeline 调用执行分段发送
  - 被 llm_request_pipeline 调用注入实时上下文
  - 与 rhythm_learner 配合调整发送节奏
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    pass  # plugin type is dynamic (Star subclass)

_CHINA_TZ = timezone(timedelta(hours=8))


class RealtimeDispatch:
    """即时聊天调度器，处理分段发送、中断恢复和上下文注入。

    核心流程：
      LLM 回复 → 分段规划 → 逐段发送（带延迟）→ 中断检测 → 断点记录

    与其他组件的关系：
      - 持有插件实例引用 (self._p)
      - 被 llm_response_pipeline 调用执行发送
      - 被 llm_request_pipeline 调用注入上下文
    """

    def __init__(self, plugin: Any) -> None:
        self._p = plugin

    # ------------------------------------------------------------------
    # Segmented dispatch helpers
    # ------------------------------------------------------------------

    def extract_first_sentence(self, text: str) -> str:
        """从文本中提取第一个完整句子。

        以中英文句末标点或换行符为分隔。连续标点视为同一句。
        """
        delimiters = "。！？!?；;"
        for i, ch in enumerate(text):
            if ch in delimiters and i > 0:
                if i + 1 < len(text) and text[i + 1] in delimiters:
                    continue
                return text[: i + 1]
            if ch == "\n" and i > 0:
                return text[:i]
        return ""

    async def send_first_sentence(self, origin: str, text: str) -> None:
        """发送首句文本到指定会话。"""
        context = self._p.context
        if hasattr(context, "send_message"):
            message = self._p._astrbot_message(text)
            await context.send_message(origin, message)

    async def dispatch_segmented_parts(
        self, origin: str, parts: list[dict[str, Any]], session_key: str = ""
    ) -> None:
        """逐段发送分段回复，每段之间按计划延迟。

        Args:
            origin: 消息发送目标。
            parts: 分段列表，每段包含 text 和 delay_before_seconds。
            session_key: 会话标识，发送完成后清除 unfinished 标记。
        """
        context = self._p.context
        if not hasattr(context, "send_message"):
            return
        total = len(parts)
        for idx, part in enumerate(parts, 1):
            delay = float(part.get("delay_before_seconds", 0))
            if delay > 0:
                await asyncio.sleep(delay)
            text = str(part.get("text", ""))
            if not text:
                continue
            self._p.logger.info(
                f"Sylanne segmented reply part {idx}/{total}: {text[:60]}"
            )
            message = self._p._astrbot_message(text)
            await context.send_message(origin, message)
        # All parts sent successfully — clear unfinished marker
        if session_key:
            self._p._unfinished_replies.pop(session_key, None)

    # ------------------------------------------------------------------
    # Realtime chat plan delivery
    # ------------------------------------------------------------------

    async def send_realtime_chat_plan(
        self,
        event: Any,
        plan: dict[str, Any],
        *,
        source: str = "",
        record_history_shadow: bool = False,
    ) -> dict[str, Any]:
        """执行实时聊天计划：逐段发送消息，处理中断和媒体。

        支持用户中断检测：每段发送前检查 input_epoch 是否已更新。
        中断时记录断点，未发送部分可在下轮续接。

        Args:
            event: AstrBot 事件对象。
            plan: 聊天计划字典，包含 message_parts、media_parts 等。
            source: 来源标识（如 "proactive"、"response"）。
            record_history_shadow: 是否记录历史影子供后续参考。

        Returns:
            执行结果字典，包含 message_count、interrupted_reason 等。
        """
        p = self._p
        session_key = plan.get("session_key") or p._session_key(event)
        plan_epoch = plan.get("input_epoch", 0)
        parts = plan.get("message_parts", [])
        media_parts = plan.get("media_parts", [])
        message_count = 0
        media_count = 0
        media_results: list[dict[str, Any]] = []
        interrupted_reason = ""
        epochs = p._conversation_input_epoch

        for part in parts:
            if plan_epoch and epochs.get(session_key, 0) > plan_epoch:
                interrupted_reason = "user_interrupted"
                break
            text = part.get("text", "")
            delay = part.get("delay_before_seconds", 0.0)
            if delay > 0 and message_count > 0:
                try:
                    await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    interrupted_reason = "user_interrupted"
                    break
            if plan_epoch and epochs.get(session_key, 0) > plan_epoch:
                interrupted_reason = "user_interrupted"
                break
            send_fn = getattr(p, "_send_segmented_reply", None)
            if send_fn and callable(send_fn):
                await send_fn(event, text, source=source)
            else:
                reply_fn = getattr(p, "_reply", None)
                if reply_fn and callable(reply_fn):
                    await reply_fn(event, text)
                else:
                    context = getattr(p, "context", None)
                    if context and hasattr(context, "send_message"):
                        origin = str(
                            getattr(event, "unified_msg_origin", "") or session_key
                        )
                        msg = p._build_astrbot_message_chain(text)
                        await context.send_message(origin, msg)
            message_count += 1

        for media in media_parts:
            kind = media.get("kind", "")
            value = media.get("value", "")
            try:
                context = getattr(p, "context", None)
                if context and hasattr(context, "send_message"):
                    import sys

                    event_mod = sys.modules.get("astrbot.api.event")
                    if event_mod:
                        _Chain = getattr(event_mod, "MessageChain", None)
                        if _Chain:
                            chain = _Chain()
                            media_fn = getattr(chain, kind, None)
                            if media_fn and callable(media_fn):
                                media_fn(value)
                                origin = str(
                                    getattr(event, "unified_msg_origin", "")
                                    or session_key
                                )
                                await context.send_message(origin, chain)
                                media_count += 1
                                media_results.append(
                                    {"kind": kind, "value": value, "sent": True}
                                )
                                continue
                    media_results.append(
                        {
                            "kind": kind,
                            "value": value,
                            "blocked_reason": "missing_local_media_file",
                        }
                    )
                else:
                    media_results.append(
                        {
                            "kind": kind,
                            "value": value,
                            "blocked_reason": "missing_local_media_file",
                        }
                    )
            except (FileNotFoundError, OSError):
                media_results.append(
                    {
                        "kind": kind,
                        "value": value,
                        "blocked_reason": "missing_local_media_file",
                    }
                )

        if interrupted_reason:
            sent_parts = [pt.get("text", "") for pt in parts[:message_count]]
            unsent_parts = [pt.get("text", "") for pt in parts[message_count:]]
            self.record_interrupted_reply_breakpoint(
                session_key,
                full_text=plan.get("full_text", ""),
                sent_parts=sent_parts,
                unsent_parts=unsent_parts,
                input_epoch=plan_epoch,
                reason=interrupted_reason,
            )
            dispatches = getattr(p, "_realtime_chat_active_dispatches", None)
            if dispatches is None:
                dispatches = {}
                p._realtime_chat_active_dispatches = dispatches
            dispatches[session_key] = [
                {
                    "sent_parts": sent_parts,
                    "unsent_parts": unsent_parts,
                    "interrupted_reason": interrupted_reason,
                }
            ]

        if record_history_shadow and message_count > 0:
            full_text = plan.get("full_text", "")
            if not full_text:
                full_text = " ".join(pt.get("text", "") for pt in parts[:message_count])
            self.record_realtime_ordinary_history_backfill(
                session_key,
                role="assistant",
                content=full_text,
                input_epoch=plan_epoch,
                source=source,
            )

        result: dict[str, Any] = {
            "message_count": message_count,
            "interrupted_reason": interrupted_reason,
        }
        if media_parts:
            result["media_count"] = media_count
            result["media_results"] = media_results
        return result

    # ------------------------------------------------------------------
    # Recording helpers
    # ------------------------------------------------------------------

    def record_realtime_assistant_history_shadow(
        self,
        session_key: str,
        *,
        full_text: str = "",
        input_epoch: int = 0,
        message_parts: list[dict[str, Any]] | None = None,
        source: str = "",
        event_time: dict[str, Any] | None = None,
        delivery_status: str = "",
    ) -> None:
        """记录实时助手回复的历史影子，供后续请求注入上下文。"""
        p = self._p
        if not hasattr(p, "_realtime_assistant_history_shadows"):
            p._realtime_assistant_history_shadows: dict[str, list[dict[str, Any]]] = {}
        shadows = p._realtime_assistant_history_shadows.setdefault(session_key, [])
        entry: dict[str, Any] = {
            "full_text": full_text,
            "input_epoch": input_epoch,
            "message_parts": message_parts or [],
            "source": source,
        }
        if event_time:
            entry["event_time"] = event_time
        if delivery_status:
            entry["delivery_status"] = delivery_status
        shadows.append(entry)

    def record_interrupted_reply_breakpoint(
        self,
        session_key: str,
        *,
        full_text: str = "",
        sent_parts: list[str] | None = None,
        unsent_parts: list[str] | None = None,
        input_epoch: int = 0,
        reason: str = "",
        event_time: dict[str, Any] | None = None,
        source: str = "",
    ) -> None:
        """记录被中断的回复断点，包含已发送和未发送部分。"""
        p = self._p
        if not hasattr(p, "_interrupted_reply_breakpoints"):
            p._interrupted_reply_breakpoints: dict[str, list[dict[str, Any]]] = {}
        bps = p._interrupted_reply_breakpoints.setdefault(session_key, [])
        entry: dict[str, Any] = {
            "full_text": full_text,
            "sent_parts": sent_parts or [],
            "unsent_parts": unsent_parts or [],
            "input_epoch": input_epoch,
            "reason": reason,
        }
        if event_time:
            entry["event_time"] = event_time
        bps.append(entry)

    def realtime_delivery_context_kv_key(self, session_key: str) -> str:
        return f"sylanne:realtime_delivery_context:{session_key}"

    def record_realtime_ordinary_history_backfill(
        self,
        session_key: str,
        *,
        role: str = "",
        content: str = "",
        input_epoch: int = 0,
        source: str = "",
        delivery_status: str = "",
    ) -> None:
        p = self._p
        if not hasattr(p, "_realtime_ordinary_history_backfills"):
            p._realtime_ordinary_history_backfills: dict[str, list[dict[str, Any]]] = {}
        entries = p._realtime_ordinary_history_backfills.setdefault(session_key, [])
        entries.append(
            {
                "role": role,
                "content": content,
                "input_epoch": input_epoch,
                "source": source,
            }
        )

    def record_active_agent_pending_user_turn(
        self,
        session_key: str,
        identity: Any = None,
        *,
        input_epoch: int = 0,
        text: str = "",
        observed_at: float = 0.0,
    ) -> None:
        p = self._p
        if not hasattr(p, "_active_agent_pending_user_turns"):
            p._active_agent_pending_user_turns: dict[str, list[dict[str, Any]]] = {}
        turns = p._active_agent_pending_user_turns.setdefault(session_key, [])
        turns.append(
            {
                "input_epoch": input_epoch,
                "text": text,
                "observed_at": observed_at,
                "identity": identity,
            }
        )

    # ------------------------------------------------------------------
    # Cache trimming
    # ------------------------------------------------------------------

    _TRIM_MAX_UNCONSUMED = 100

    def _trim_consumed(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Trim a shadow/breakpoint list: keep at most the last _TRIM_MAX_UNCONSUMED
        unconsumed entries, discard all consumed entries.

        Mutates and returns the list in-place (replaces contents).
        """
        unconsumed = [e for e in entries if not e.get("consumed")]
        if len(unconsumed) > self._TRIM_MAX_UNCONSUMED:
            unconsumed = unconsumed[-self._TRIM_MAX_UNCONSUMED:]
        entries[:] = unconsumed
        return entries

    # ------------------------------------------------------------------
    # Cache accessors
    # ------------------------------------------------------------------

    def realtime_assistant_history_shadow_cache(
        self,
    ) -> dict[str, list[dict[str, Any]]]:
        p = self._p
        if not hasattr(p, "_realtime_assistant_history_shadows"):
            p._realtime_assistant_history_shadows: dict[str, list[dict[str, Any]]] = {}
        return p._realtime_assistant_history_shadows

    def realtime_ordinary_history_backfill_cache(
        self,
    ) -> dict[str, list[dict[str, Any]]]:
        p = self._p
        if not hasattr(p, "_realtime_ordinary_history_backfills"):
            p._realtime_ordinary_history_backfills: dict[str, list[dict[str, Any]]] = {}
        return p._realtime_ordinary_history_backfills

    # ------------------------------------------------------------------
    # Context injection (append_*_if_any)
    # ------------------------------------------------------------------

    def append_realtime_assistant_history_shadow_if_any(
        self,
        request: Any,
        session_key: str,
        *,
        budget: Any = None,
        current_user_text: str = "",
    ) -> bool:
        """若有未消费的历史影子，注入到请求 prompt 中。

        Returns:
            是否成功注入。
        """
        cache = self.realtime_assistant_history_shadow_cache()
        shadows = cache.get(session_key, [])
        if not shadows:
            return False
        last = shadows[-1]
        if last.get("consumed"):
            return False
        contexts = getattr(request, "contexts", []) or []
        for ctx in contexts:
            if isinstance(ctx, dict):
                ctx_content = str(ctx.get("content") or "")
                if "[sylanne_realtime_assistant_history]" in ctx_content:
                    last["consumed"] = True
                    last["consumed_reason"] = "official_context_compression_summary"
                    self._trim_consumed(shadows)
                    return False
        full_text = last.get("full_text", "")
        event_time = last.get("event_time", {})
        event_time_line = ""
        if event_time:
            event_time_line = (
                f"\nevent_local_time="
                f"{event_time.get('event_local_time', event_time.get('local_datetime', ''))}"
                f"\ntimezone={event_time.get('timezone', '')}"
            )
        _sys = str(getattr(request, "system_prompt", "") or "")
        request.system_prompt = (
            _sys
            + "\n[sylanne_realtime_assistant_history]"
            + event_time_line
            + "\n"
            + full_text
        )
        last["consumed"] = True
        last["consumed_reason"] = "injected"
        self._trim_consumed(shadows)
        return True

    def append_interrupted_reply_breakpoint_if_any(
        self,
        request: Any,
        session_key: str,
        *,
        budget: Any = None,
    ) -> bool:
        """若有未消费的中断断点，注入到请求 prompt 中。"""
        bps = getattr(self._p, "_interrupted_reply_breakpoints", {})
        entries = bps.get(session_key, [])
        if not entries:
            return False
        last = entries[-1]
        if last.get("consumed"):
            return False
        full_text = last.get("full_text", "")
        event_time = last.get("event_time", {})
        event_time_line = ""
        if event_time:
            event_time_line = (
                f"\nevent_local_time="
                f"{event_time.get('event_local_time', event_time.get('local_datetime', ''))}"
                f"\ntimezone={event_time.get('timezone', '')}"
            )
        _sys = str(getattr(request, "system_prompt", "") or "")
        request.system_prompt = (
            _sys
            + "\n[sylanne_interrupted_reply_breakpoint]"
            + event_time_line
            + "\n"
            + full_text
        )
        last["consumed"] = True
        self._trim_consumed(entries)
        return True

    def build_realtime_delivery_envelope_text(
        self,
        text: str,
        *,
        session_key: str = "",
        input_epoch: int = 0,
        message_parts: list[dict[str, Any]] | None = None,
        event_time: dict[str, Any] | None = None,
    ) -> str:
        lines = ["[sylanne_realtime_delivery_envelope]"]
        if event_time:
            lines.append(
                f"event_local_time="
                f"{event_time.get('event_local_time', event_time.get('local_datetime', ''))}"
            )
            lines.append(f"timezone={event_time.get('timezone', '')}")
        lines.append(f"text={text}")
        lines.append(
            "note=realtime segmented delivery disabled or removed in alpha host"
        )
        return "\n".join(lines)

    def start_realtime_chat_active_dispatch(
        self,
        session_key: str,
        *,
        input_epoch: int = 0,
        full_text: str = "",
        source: str = "",
        event_time: dict[str, Any] | None = None,
    ) -> None:
        p = self._p
        if not hasattr(p, "_realtime_chat_active_dispatches"):
            p._realtime_chat_active_dispatches: dict[str, list[dict[str, Any]]] = {}
        dispatches = p._realtime_chat_active_dispatches.setdefault(session_key, [])
        entry: dict[str, Any] = {
            "input_epoch": input_epoch,
            "full_text": full_text,
            "source": source,
        }
        if event_time:
            entry["event_time"] = event_time
        dispatches.append(entry)

    def append_realtime_chat_active_dispatch_if_any(
        self,
        request: Any,
        session_key: str,
        *,
        budget: Any = None,
    ) -> bool:
        dispatches = getattr(self._p, "_realtime_chat_active_dispatches", {})
        entries = dispatches.get(session_key, [])
        if not entries:
            return False
        last = entries[-1]
        if last.get("consumed"):
            return False
        full_text = last.get("full_text", "")
        event_time = last.get("event_time", {})
        event_time_line = ""
        if event_time:
            event_time_line = (
                f"\ntrigger_event_local_time="
                f"{event_time.get('event_local_time', event_time.get('local_datetime', ''))}"
                f"\ntrigger_timezone={event_time.get('timezone', '')}"
            )
        _sys = str(getattr(request, "system_prompt", "") or "")
        request.system_prompt = (
            _sys
            + "\n[sylanne_realtime_chat_active_dispatch]"
            + event_time_line
            + "\n"
            + full_text
        )
        last["consumed"] = True
        self._trim_consumed(entries)
        return True

    def append_realtime_continuity_context_if_any(
        self,
        request: Any,
        session_key: str,
        *,
        budget: Any = None,
        current_user_text: str = "",
    ) -> bool:
        cache = self.realtime_assistant_history_shadow_cache()
        shadows = cache.get(session_key, [])
        if not shadows:
            return False
        last = shadows[-1]
        full_text = last.get("full_text", "")
        if not full_text:
            return False
        if "？" in full_text or "?" in full_text:
            _sys = str(getattr(request, "system_prompt", "") or "")
            injection = (
                "[sylanne_realtime_pending_bot_question]\n"
                + "上一轮 bot 刚提出了一个未闭合问题："
                + full_text
                + "\n"
                + "current_user_short_answer="
                + current_user_text
            )
            request.system_prompt = _sys + "\n" + injection
            return True
        return False

    def append_realtime_ordinary_history_backfills_if_any(
        self, request: Any, session_key: str = "", **kwargs: Any
    ) -> bool:
        backfills = getattr(self._p, "_realtime_ordinary_history_backfills", {})
        entries = backfills.get(session_key, [])
        if not entries:
            return False
        current = str(getattr(request, "system_prompt", "") or "")
        parts = []
        for entry in entries:
            if isinstance(entry, dict):
                parts.append(str(entry.get("content", "")))
            else:
                parts.append(str(entry))
        if parts:
            request.system_prompt = f"{current}\n[sylanne_backfill_context]\n" + "\n".join(
                parts
            )
        backfills[session_key] = []
        return True

    # ------------------------------------------------------------------
    # Release / cleanup
    # ------------------------------------------------------------------

    async def release_realtime_temporary_context_after_background_post(
        self,
        session_key: str,
        *,
        input_epoch: int = 0,
        reason: str = "",
    ) -> None:
        cache = self.realtime_assistant_history_shadow_cache()
        shadows = cache.get(session_key, [])
        for shadow in shadows:
            if shadow.get("input_epoch") == input_epoch and not shadow.get("consumed"):
                shadow["consumed"] = True
                shadow["consumed_reason"] = reason
                break
        self._trim_consumed(shadows)
        backfills = self.realtime_ordinary_history_backfill_cache()
        backfills.pop(session_key, None)

    def release_realtime_temporary_context_after_background_post_in_memory(
        self,
        session_key: str,
        *,
        input_epoch: int | None = 0,
        reason: str = "",
    ) -> bool:
        if input_epoch is None:
            return False
        cache = self.realtime_assistant_history_shadow_cache()
        shadows = cache.get(session_key, [])
        changed = False
        for shadow in shadows:
            if shadow.get("input_epoch") == input_epoch and not shadow.get("consumed"):
                shadow["consumed"] = True
                shadow["consumed_reason"] = reason
                changed = True
                break
        if changed:
            self._trim_consumed(shadows)
            backfills = self.realtime_ordinary_history_backfill_cache()
            if session_key in backfills:
                backfills[session_key] = [
                    e
                    for e in backfills[session_key]
                    if e.get("input_epoch", 0) > input_epoch
                ]
                if not backfills[session_key]:
                    del backfills[session_key]
        return changed

    # ------------------------------------------------------------------
    # Realtime input/response helpers
    # ------------------------------------------------------------------

    def build_realtime_input_completion_prompt(
        self, session_key: str = "", text: str = "", **kwargs: Any
    ) -> str:
        return text

    def extract_realtime_response_media_parts(self, response: Any = None) -> list[Any]:
        return []

    def build_group_atmosphere_injection_for_session(
        self, session_key: str = "", state: Any = None, **kwargs: Any
    ) -> str:
        """将群聊氛围状态格式化为 XML 标签注入文本。

        支持 diff 模式：若状态变化小于阈值，返回简短的 "无变化" 标记。
        """
        p = self._p
        if state is None:
            return ""
        cache = getattr(p, "_group_atmosphere_injection_snapshot_cache", {})
        previous = cache.get(session_key)
        cfg = p.config or {}
        diff_mode = str(cfg.get("state_injection_compact_mode", "")).lower() == "diff"
        values = getattr(state, "values", {}) if state else {}
        if diff_mode and previous is not None:
            threshold = float(
                cfg.get("group_atmosphere_injection_diff_threshold", 0.08)
            )
            prev_values = previous.get("values", {})
            max_delta = (
                max(abs(values.get(k, 0) - prev_values.get(k, 0)) for k in values)
                if values
                else 0
            )
            if max_delta < threshold:
                return '<bot_group_atmosphere detail="diff">No material room-mood change since last injection.</bot_group_atmosphere>'
        snapshot = {"values": dict(values)}
        cache[session_key] = snapshot
        if not hasattr(p, "_group_atmosphere_injection_snapshot_cache"):
            p._group_atmosphere_injection_snapshot_cache = {}
        p._group_atmosphere_injection_snapshot_cache[session_key] = snapshot
        lines = ["<bot_group_atmosphere>"]
        for k, v in values.items():
            lines.append(f"  {k}={v:.2f}" if isinstance(v, float) else f"  {k}={v}")
        lines.append("</bot_group_atmosphere>")
        return "\n".join(lines)

    def context_item_to_text(self, item: Any) -> str:
        if isinstance(item, dict):
            return str(item.get("content", "") or item.get("text", ""))
        if hasattr(item, "text"):
            return str(item.text)
        if hasattr(item, "content"):
            return str(item.content)
        return str(item)

    def conversation_time_payload(
        self, session_key_or_timestamp: Any = "", *, event: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        """构建对话时间载荷：本地时间、日期、时区信息。"""
        ts = None
        if (
            isinstance(session_key_or_timestamp, (int, float))
            and session_key_or_timestamp > 1000000000
        ):
            ts = datetime.fromtimestamp(session_key_or_timestamp, tz=_CHINA_TZ)
        elif event is not None and hasattr(event, "timestamp") and event.timestamp:
            ts = datetime.fromtimestamp(event.timestamp, tz=_CHINA_TZ)
        if ts is None:
            ts = datetime.now(_CHINA_TZ)
        offset_str = ts.strftime("%z")
        offset_formatted = (
            f"{offset_str[:3]}:{offset_str[3:]}" if len(offset_str) == 5 else offset_str
        )
        return {
            "local_time": ts.strftime("%H:%M:%S"),
            "local_date": ts.strftime("%Y-%m-%d"),
            "local_datetime": f"{ts.strftime('%Y-%m-%d %H:%M:%S')} {offset_formatted}",
            "timezone": "Asia/Shanghai",
            "event_local_time": f"{ts.strftime('%Y-%m-%d %H:%M:%S')} {offset_formatted}",
        }

    def napcat_recall_payload(self, event: Any = None) -> dict[str, Any]:
        """从 NapCat 消息撤回事件中提取载荷信息。"""
        raw = None
        if event:
            msg_obj = getattr(event, "message_obj", None)
            if msg_obj:
                raw = getattr(msg_obj, "raw_message", None)
            if not raw:
                raw = getattr(event, "raw_message", None)
        if not raw or not isinstance(raw, dict):
            return {}
        return {
            "notice_type": str(raw.get("notice_type", "")),
            "message_id": str(raw.get("message_id", "")),
            "group_id": str(raw.get("group_id", "")),
            "user_id": str(raw.get("user_id", "")),
            "operator_id": str(raw.get("operator_id", "")),
        }

    async def observe_stickers_background(
        self, event: Any = None, stickers: Any = None, **kwargs: Any
    ) -> None:
        pass

    def extract_sticker_observations_from_event(
        self, event: Any = None
    ) -> list[dict[str, Any]]:
        return []

    def fast_assessor_max_context_chars(self) -> int:
        p = self._p
        return p._cfg_int("fast_assessor_max_context_chars", 240)

    def discard_conversation_pending_response_epoch(
        self, session_key: str, epoch: int = 0
    ) -> None:
        p = self._p
        epochs = p._conversation_pending_response_epochs
        if epochs and session_key in epochs:
            del epochs[session_key]

    def conversation_reply_is_stale(self, session_key: str, reply_epoch: int) -> bool:
        """判断回复是否已过期（用户在回复生成期间发送了新消息）。"""
        p = self._p
        epochs = p._conversation_input_epoch
        current = epochs.get(session_key, 0)
        return reply_epoch < current

    # ------------------------------------------------------------------
    # Item 145: 主动沉默引擎
    # ------------------------------------------------------------------

    def deliberate_silence(self) -> "DeliberateSilence":
        """获取主动沉默决策器实例（懒初始化）。"""
        if not hasattr(self, "_deliberate_silence"):
            self._deliberate_silence = DeliberateSilence()
        return self._deliberate_silence

    # ------------------------------------------------------------------
    # Background task scheduling
    # ------------------------------------------------------------------

    def schedule_background_task(self, coro: Any, *, label: str = "") -> Any:
        """调度后台异步任务，自动处理异常和清理。

        Args:
            coro: 要执行的协程。
            label: 任务标签（用于错误日志）。

        Returns:
            创建的 asyncio.Task 对象。
        """
        p = self._p

        async def _wrapper() -> None:
            try:
                await coro
            except asyncio.CancelledError:
                pass
            except Exception as e:
                import logging

                logging.getLogger("astrbot_plugin_sylanne").error(
                    f"Background task '{label or 'background_task'}' failed: {e}",
                    exc_info=True,
                )

        task = asyncio.ensure_future(_wrapper())
        p._background_tasks.add(task)
        task.add_done_callback(
            lambda t: p._background_tasks.discard(t)
        )
        return task

    def ensure_runtime_state_containers(self) -> None:
        """确保运行时状态容器已初始化。"""
        p = self._p
        if not hasattr(p, "_sylanne_memory_pending_observations"):
            p._sylanne_memory_pending_observations: dict[str, Any] = {}
        if not hasattr(p, "_sylanne_memory_idle_generation"):
            p._sylanne_memory_idle_generation: dict[str, int] = {}

    def build_astrbot_message_chain(self, text: str = "", **kwargs: Any) -> Any:
        """构建 AstrBot MessageChain 消息对象。"""
        import sys

        p = self._p
        event_mod = sys.modules.get("astrbot.api.event")
        if event_mod:
            _Chain = getattr(event_mod, "MessageChain", None)
            if _Chain:
                chain = _Chain()
                if hasattr(chain, "message") and callable(chain.message):
                    chain.message(text)
                    return chain
        return p._astrbot_message(text)

    async def on_waiting_llm_request(self, event: Any, **kwargs: Any) -> None:
        pass

    # ------------------------------------------------------------------
    # Item 7: 对话中断恢复提示
    # ------------------------------------------------------------------

    def _build_resumption_hint(
        self, session_key: str, last_time: float, now: float
    ) -> str | None:
        """构建对话中断恢复提示。

        当距上次对话超过 2 小时时，生成恢复提示帮助 LLM 自然地重新衔接对话。
        优先从 session_context 的 offline_buffer 取最近想法作为恢复素材。

        Args:
            session_key: 会话标识。
            last_time: 上次对话的 Unix 时间戳。
            now: 当前 Unix 时间戳。

        Returns:
            恢复提示字符串，不需要恢复时返回 None。
        """
        gap_seconds = now - last_time
        if gap_seconds <= 7200:
            return None

        gap_hours = int(gap_seconds / 3600)
        p = self._p

        # 尝试从 offline_buffer 获取离线期间的想法
        offline_thought = ""
        session_ctx = getattr(p, "_session_context", None)
        if session_ctx is not None and hasattr(session_ctx, "offline_buffer_for_session"):
            buf = session_ctx.offline_buffer_for_session(session_key)
            if buf and hasattr(buf, "peek_latest"):
                latest = buf.peek_latest()
                if latest:
                    offline_thought = str(latest)[:100]
            elif buf and hasattr(buf, "drain_summary"):
                # peek not available, try summary without draining
                items = getattr(buf, "_items", None) or getattr(buf, "items", None)
                if items and isinstance(items, list) and items:
                    offline_thought = str(items[-1])[:100]

        if offline_thought:
            return (
                f"[对话恢复] 距上次对话已过{gap_hours}小时。"
                f"离线期间的想法：{offline_thought}。"
                f"可以自然地提及这段时间的感受或想法来衔接对话。"
            )
        else:
            return (
                f"[对话恢复] 距上次对话已过{gap_hours}小时。"
                f"可以自然地问候或提及时间间隔来重新衔接对话。"
            )


class DeliberateSilence:
    """主动沉默决策：某些情况下故意不回复或延迟回复。"""

    def __init__(self):
        self._silence_reason: str | None = None

    def should_be_silent(
        self, valence: float, tension: float, void_pressure: float
    ) -> tuple[bool, str]:
        """判断是否应该主动沉默。返回 (是否沉默, 原因)。"""
        if tension > 0.7 and valence < -0.3:
            return True, "hurt"  # 受伤但不想表达
        if void_pressure > 3.0 and valence > 0:
            return True, "digesting"  # 在消化
        if tension < -0.5:
            return True, "content"  # 满足无需言语
        return False, ""

    def get_minimal_response(self, reason: str) -> str | None:
        """沉默时的极简回复（可选）。"""
        responses = {
            "hurt": "……",
            "digesting": None,  # 完全不回复
            "content": "嗯。",
        }
        return responses.get(reason)


# ---------------------------------------------------------------------------
# Item 121: 对话呼吸节奏引擎
# ---------------------------------------------------------------------------


class BreathingRhythmController:
    """根据情绪张力和话题密度动态调整回复长短交替模式。

    模拟人类对话中的"呼吸感"——紧张时长短交替加快，
    平静时节奏舒缓，情绪渐强时回复渐长，收尾时渐短。

    四种呼吸模式：
    - calm: 短-中-短（平静对话）
    - intense: 长-短-长-短（高张力交替）
    - building: 渐长（情绪积累）
    - winding: 渐短（对话收尾）

    使用方式：
    每次生成回复前调用 next_length_factor() 获取长度倍率，
    将基础回复长度乘以该倍率得到目标长度。
    """

    PATTERNS: dict[str, list[float]] = {
        "calm": [0.8, 1.0, 0.6],           # 短-中-短
        "intense": [1.2, 0.5, 1.5, 0.4],   # 长-短-长-短
        "building": [0.6, 0.8, 1.0, 1.2],  # 渐长
        "winding": [1.2, 1.0, 0.8, 0.6],   # 渐短
    }

    def __init__(self) -> None:
        self._current_pattern: str = "calm"
        self._pattern_index: int = 0

    def select_pattern(self, tension: float, valence: float) -> str:
        """根据情绪张力和效价选择呼吸模式。

        Args:
            tension: 情绪张力 [0, 1]，越高越紧张。
            valence: 情绪效价 [-1, 1]，正值=积极，负值=消极。

        Returns:
            模式名称：calm / intense / building / winding。
        """
        if tension > 0.6:
            return "intense"
        elif tension > 0.3 and valence < 0:
            return "building"
        elif valence > 0.5:
            return "winding"
        return "calm"

    def next_length_factor(self, tension: float, valence: float) -> float:
        """返回下一条回复的长度倍率。

        根据当前情绪状态选择模式，若模式切换则重置索引。
        按模式序列循环返回倍率值。

        Args:
            tension: 情绪张力 [0, 1]。
            valence: 情绪效价 [-1, 1]。

        Returns:
            长度倍率，范围约 [0.4, 1.5]。
            < 1.0 表示应缩短回复，> 1.0 表示应加长回复。
        """
        pattern_name = self.select_pattern(tension, valence)
        if pattern_name != self._current_pattern:
            self._current_pattern = pattern_name
            self._pattern_index = 0
        pattern = self.PATTERNS[self._current_pattern]
        factor = pattern[self._pattern_index % len(pattern)]
        self._pattern_index += 1
        return factor
