"""LLM 响应管线 —— 拦截 on_llm_response 事件的核心处理模块。

职责：
  1. 拦截 LLM 响应，清理 thinking/draft 块
  2. 实现分段回复：将长回复拆分为多条消息，模拟人类打字节奏
  3. 流式首句快速发送：在流式输出中检测到第一句完成时立即发送
  4. 后台触发记忆写入和状态更新
  5. Claude/哈基德兼容性处理：规范化请求格式、裁剪工具列表

与其他组件的关系：
  - 与 llm_request_pipeline 配对：request 注入上下文，response 处理输出
  - 调用 rhythm_learner 获取自适应分段参数
  - 通过 observe_response 将回复反馈给计算栈

所有方法通过 ``self._p`` 委托访问插件实例属性。
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any


from sylanne_alpha.utils import ensure_background_tasks_list, safe_ensure_future
from sylanne_alpha.message_dispatch import (
    normalize_completion_text,
    realtime_plan,
    strip_draft_blocks,
)
from sylanne_alpha.variant_pool import (
    EMPTY_REPLY_FALLBACK_VARIANTS,
    LAST_RESORT_FALLBACK_TEXT,
    choose as _pool_choose,
    warmth_bucket as _warmth_bucket,
)

if TYPE_CHECKING:
    from sylanne_alpha.protocols import PluginHost

try:
    from astrbot.api import logger  # type: ignore
except ImportError:
    import logging as _logging

    logger = _logging.getLogger("astrbot_plugin_sylanne")  # type: ignore

# 中国时区常量
_CHINA_TZ = timezone(timedelta(hours=8))
# 序列化后的请求载荷最大字符数，超过则触发裁剪
_MAX_PAYLOAD_SERIALIZED_CHARS = 60000


class LLMResponsePipeline:
    """LLM 响应处理管线，封装 Sylanne 插件的响应拦截逻辑。

    核心流程：
      LLM 返回 → 清理 draft 块 → 检测首句已发送 → 分段拆分 → 后台调度发送

    与其他组件的关系：
      - 持有插件实例引用 (self._p)
      - 使用 compat.realtime_plan 做分段规划
      - 使用 rhythm_learner 获取自适应节奏参数
      - 调用 observe_response 反馈给计算栈
    """

    def __init__(self, plugin: PluginHost) -> None:
        self._p = plugin

    # ------------------------------------------------------------------
    # Injection defense
    # ------------------------------------------------------------------
    # 匹配 LLM 伪造的 [sylanne_xxx] 系统标签
    _RE_SYLANNE_TAG = re.compile(r"\[sylanne_[^\]]*\]")

    def _sanitize_response(self, text: str) -> str:
        """过滤 LLM 返回中伪造的 [sylanne_*] 系统标签。

        防止 LLM 在回复中注入形如 [sylanne_xxx] 的标签来伪造系统指令。
        """
        cleaned = self._RE_SYLANNE_TAG.sub("", text)
        if cleaned != text:
            logger.warning(
                "Sanitized %d injected [sylanne_*] tag(s) from LLM response",
                len(self._RE_SYLANNE_TAG.findall(text)),
            )
        return cleaned

    # ------------------------------------------------------------------
    # Main response handler
    # ------------------------------------------------------------------
    async def _on_llm_response_inner(self, event: Any, response: Any) -> None:
        """LLM 响应拦截的主入口。

        处理流程：
          1. 清理 thinking/draft 块
          2. 若首句已通过流式发送，存储剩余部分为 unfinished
          3. 否则进行分段规划，后台调度逐段发送
          4. 启动后台观测任务记录回复

        Args:
            event: AstrBot 事件对象。
            response: LLM 响应对象，包含 completion_text。
        """
        # 流式/分段缓冲已迁入 _store（CP8-P2）
        ensure_background_tasks_list(self._p)
        session_key = self._p._session_key(event)
        cfg = self._p._config or {}
        realtime_enabled = bool(
            cfg.get("sylanne_alpha_realtime_chat_enabled")
            or cfg.get("enable_realtime_chat")
        )
        intercept = bool(
            cfg.get("sylanne_alpha_realtime_intercept_llm_response")
            or cfg.get("realtime_chat_intercept_llm_response")
        )

        if not realtime_enabled or not intercept:
            # 未启用即时聊天拦截时，仅清理 thinking/draft 块 + 注入防御；
            # 仍须把 bot 回复写入 conversation_buffers（v2core 已 tick，勿再 observe_response）。
            if response is not None:
                text = normalize_completion_text(getattr(response, "completion_text", ""))
                cleaned = strip_draft_blocks(text)
                cleaned = self._sanitize_response(cleaned)
                # 注：此分支 completion_text 整段直发 AstrBot（不分段）。曾在此加超长截断
                # 兜底，经审查移除——单条长消息不是事故的 86 段轰炸，tagged thinking 已剥；
                # 截断会丢内容、还撞 deliverable 契约"一次给全"，是治 speculative 问题反引入
                # 真 bug。源头的 deliverable_mode（摘逃生舱工具）才是 thrash/泄露的真兜底。
                if cleaned != text:
                    response.completion_text = cleaned
                if cleaned.strip():
                    obs_task = safe_ensure_future(
                        self._append_bot_reply_buffer(session_key, cleaned),
                        name="append_bot_reply_buffer",
                    )
                    ensure_background_tasks_list(self._p).append(obs_task)
                    obs_task.add_done_callback(
                        lambda t: (
                            self._p._background_tasks.remove(t)
                            if t in self._p._background_tasks
                            else None
                        )
                    )
            return

        if response is None:
            return

        text = normalize_completion_text(getattr(response, "completion_text", ""))
        cleaned = strip_draft_blocks(text)
        cleaned = self._sanitize_response(cleaned)
        logger.info(
            f"Sylanne on_llm_response: len={len(cleaned)} session={session_key}"
        )

        # 定时任务（cron）的 LLM 回复是内部总结，不应发送给用户
        _platform = ""
        _pm = getattr(event, "platform_meta", None)
        if _pm:
            _platform = str(getattr(_pm, "name", "") or "")
        if not _platform:
            _umo = str(getattr(event, "unified_msg_origin", "") or "")
            if _umo.startswith("cron"):
                _platform = "cron"
        if _platform == "cron":
            response.completion_text = ""
            return

        if not cleaned.strip():
            # 修复 #2（ghost 空回复）——本层语义是"LLM 已被调用、本该有回复"，所以这里的空
            # 【永远是意外】（模型把答案塞进 thinking / 真没产出），绝不是人格主动装死
            # （那由上游表达闸决定，不在这层）。故默认不 ghost：给一句 Sylanne 口吻兜底，
            # 走和正常回复一样的分段发送路径。区分成因仅供调试留痕（D8）。
            _reason = "stripped_to_empty" if text.strip() else "empty_completion"
            _cfg = self._p._config or {}
            _no_ghost = bool(_cfg.get("sylanne_no_ghost_reply", True))
            # 按 reason 分治（2026-06-13 治日志蹦兜底）：
            # - stripped_to_empty（thinking 包答案）：原 06:11 真 ghost bug，仍兜底防"已读不回"。
            # - empty_completion（completion_text 真空）：常见于 AstrBot tool 循环死锁——AstrBot
            #   core 已自己塞过 [SYSTEM NOTICE] 重复调用警告，再蹦 Sylanne 兜底文案是雪上加霜，
            #   且语气解释式（"我想说点什么…再给我一秒"）反而让人觉得是说明书不是她。静默更对。
            # config 显式开 ghost（_no_ghost=False）依然全静默；config 设了自定义兜底文案则继续走兜底。
            _has_custom_fallback = bool(str(_cfg.get("sylanne_ghost_fallback_text") or "").strip())
            _silent_this = (not _no_ghost) or (
                _reason == "empty_completion" and not _has_custom_fallback
            )
            if _silent_this:
                logger.info(
                    f"Sylanne reply silent: session={session_key} "
                    f"reason={_reason} raw_len={len(text)} "
                    f"cfg_no_ghost={_no_ghost} has_custom={_has_custom_fallback}"
                )
                response.completion_text = ""
                return
            # 走到这里：stripped_to_empty 默认兜底 / 用户显式配了自定义兜底文案
            # T4-02①：用户自定义文案（config 通道）优先级最高，锁定不变；否则走
            # EMPTY_REPLY_FALLBACK_VARIANTS 变体池（同 renderer.py 共用一份），按上一轮
            # 缓存的 warmth 分挑语气（此处是同步热路径，拿不到实时 body，last_injected_states
            # 是本轮 request 阶段刚写入的近期快照，足够便宜、足够新——不为此发额外异步取值），
            # recent-N 去重存 _store.variant_recent（按 session 隔离，随 release_session 清理）。
            _custom_fallback = str(_cfg.get("sylanne_ghost_fallback_text") or "").strip()
            if _custom_fallback:
                _fallback = _custom_fallback
            else:
                _prev_state = self._p._store.last_injected_states.get(session_key) or {}
                _fallback = _pool_choose(
                    EMPTY_REPLY_FALLBACK_VARIANTS,
                    recent_key="empty_reply_fallback",
                    state=self._p._store.variant_recent.get_or_create(session_key, dict),
                    condition=_warmth_bucket(_prev_state.get("warmth")),
                ) or LAST_RESORT_FALLBACK_TEXT
            logger.info(
                f"Sylanne empty reply -> fallback (no ghost): session={session_key} "
                f"reason={_reason} raw_len={len(text)} fallback_len={len(_fallback)}"
            )
            cleaned = _fallback
            # 落入下方正常分段发送流程（不 return）

        # 检查首句是否已通过流式发送
        first_sent = self._p._store.stream_first_sent.pop(session_key, "")
        if first_sent:
            # 首句已发送——不重复发送，存储剩余部分供下轮续接
            remainder = cleaned
            if remainder.startswith(first_sent):
                remainder = remainder[len(first_sent) :].strip()
            elif first_sent.rstrip("。！？!?.") in remainder:
                stripped = first_sent.rstrip("。！？!?.")
                idx = remainder.find(stripped)
                end_idx = idx + len(stripped)
                if end_idx < len(remainder):
                    remainder = remainder[end_idx:].strip()
                else:
                    remainder = ""
            if remainder:
                self._p._store.unfinished_replies.set(session_key, remainder)
            # Don't modify completion_text, don't stop event
            return

        # 分段规划并调度发送
        origin = str(getattr(event, "unified_msg_origin", "") or "")
        cfg = self._p._config or {}
        default_max_part = int(cfg.get("realtime_chat_max_part_chars", 48))
        default_cps = 7.5  # 默认每秒字符数（模拟打字速度）
        host = self._p._host(session_key)
        expr_drive = host.kernel.computation.engine.expression_drive()
        # 计算"最近被忽略"信号，用于调整节奏。T1-04③修复：原实现取
        # last_bot_expression_time.values()（跨所有会话的单值池），A 会话的节奏会被
        # B/C 会话是否被忽略污染。last_bot_expression_time/last_user_message_time
        # 都是按 session_key 存的单值（非历史序列），改为只看本会话自己的信号：
        # 若本会话上次表达之后用户还没再开口，且已经过去够久，视为"正在被忽略"，
        # 沉默越久信号越强（600s 封顶到 1.0）。
        recent_ignored = 0.0
        last_expr_at = self._p._store.last_bot_expression_time.get(session_key, 0.0)
        last_user_at = self._p._store.last_user_message_time.get(session_key, 0.0)
        if last_expr_at > 0 and last_user_at < last_expr_at:
            now = time.time()
            silence = now - last_expr_at
            if silence > 300.0:
                recent_ignored = min(1.0, (silence - 300.0) / 300.0)
        max_part_chars, cps = self._p._rhythm_learner.get_rhythm_params(
            session_key,
            default_max_part=default_max_part,
            default_cps=default_cps,
            expression_drive=expr_drive,
            recent_ignored_rate=recent_ignored,
        )
        plan = realtime_plan(
            session_key, cleaned, max_part_chars=max_part_chars, chars_per_second=cps
        )
        parts = plan.get("message_parts", [])

        if not parts:
            response.completion_text = cleaned
            return

        # 保留 completion_text 供 AstrBot 上下文历史记录使用。
        # 清空 result_chain 防止 AstrBot 发送完整消息（由分段调度代替）。
        response.completion_text = cleaned
        if hasattr(response, "result_chain"):
            response.result_chain = None
        if hasattr(response, "chain"):
            response.chain = None

        # 多段回复时存储未发送部分，供下轮续接
        if len(parts) > 1:
            sent_first = parts[0]["text"]
            rest = cleaned
            if rest.startswith(sent_first):
                rest = rest[len(sent_first) :].strip()
            self._p._store.unfinished_replies.set(session_key, rest)

        # 后台调度分段发送
        logger.info(
            f"Sylanne segmented reply queued: session={session_key} parts={len(parts)}"
        )
        task = safe_ensure_future(
            self._dispatch_segmented_parts(origin, parts, session_key=session_key),
            name="dispatch_segmented_parts",
        )
        ensure_background_tasks_list(self._p).append(task)
        task.add_done_callback(
            lambda t: (
                self._p._background_tasks.remove(t)
                if t in self._p._background_tasks
                else None
            )
        )
        self._p._store.segmented_tasks.set(session_key, task)

        # 将观测任务从热路径移出，后台异步执行
        obs_task = safe_ensure_future(
            self._background_observe_response(session_key, cleaned),
            name="background_observe_response",
        )
        ensure_background_tasks_list(self._p).append(obs_task)
        obs_task.add_done_callback(
            lambda t: (
                self._p._background_tasks.remove(t)
                if t in self._p._background_tasks
                else None
            )
        )

    async def _append_bot_reply_buffer(self, session_key: str, text: str) -> None:
        """仅写入对话缓冲 + ConvMgr 同步（不 tick / 不 observe_response）。"""
        try:
            from sylanne_alpha.memory_system import ConversationBuffer

            buf = self._p._store.conversation_buffers.get_or_create(
                session_key, lambda: ConversationBuffer(session_key=session_key)
            )
            buf.append("bot", text)
            self._p._store.last_bot_texts.set(session_key, text[:120])
            self._p._schedule_buffer_persist(session_key)
            if self._p._has_conversation_manager():
                safe_ensure_future(
                    self._p._sync_message_to_conv_mgr(session_key, "bot", text),
                    name="conv_mgr_sync_bot",
                )
            if hasattr(
                self._p, "_social_field"
            ) and self._p._social_field.is_group_context_by_key(session_key):
                try:
                    host = self._p._host(session_key)
                    host.kernel.computation.engine.social_void.reset()
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Sylanne append_bot_reply_buffer: {e}", exc_info=True)

    async def _background_observe_response(self, session_key: str, text: str) -> None:
        """后台观测 bot 回复：写入对话缓冲、通知社交场域、更新计算栈。"""
        try:
            await self._append_bot_reply_buffer(session_key, text)
            await self._p.observe_response(
                session_key,
                text=text[:500],
                confidence=0.7,
                flags=["safe"],
                now=time.time(),
            )
        except Exception as e:
            logger.warning(f"Sylanne observe_response: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # on_llm_stream_chunk hook -- dispatch first sentence early
    # ------------------------------------------------------------------
    async def on_llm_stream_chunk(self, event: Any, chunk: Any) -> None:
        """流式输出钩子：在流式生成过程中检测首句完成并提前发送。

        通过累积 delta 到 buffer，检测到完整首句后立即发送给用户，
        减少用户感知的首次响应延迟。

        Args:
            event: AstrBot 事件对象。
            chunk: 流式输出的增量块。
        """
        session_key = self._p._session_key(event)
        intercept = bool(
            self._p._config.get("sylanne_alpha_realtime_intercept_llm_response")
        )
        if not intercept:
            return

        delta = str(getattr(chunk, "delta", "") or "")
        if not delta:
            return

        buffer = self._p._store.stream_buffers.get(session_key, "") + delta
        self._p._store.stream_buffers.set(session_key, buffer)

        # 抢发首句前先取【可见前缀】：剥已闭合隐藏块 + 在未闭合 thinking 处截断，
        # 杜绝把思维链碎片当正文抢发（2026-06-13 流式 thinking 泄漏 bug 根治）。
        visible = self._visible_stream_prefix(buffer)

        # Check if we have a complete first sentence
        first_sentence = self._extract_first_sentence(visible)
        if first_sentence and not self._p._store.stream_first_sent.has(session_key):
            self._p._store.stream_first_sent.set(session_key, first_sentence)
            self._p._store.stream_buffers.pop(session_key, None)
            origin = str(getattr(event, "unified_msg_origin", "") or "")
            task = safe_ensure_future(
                self._send_first_sentence(origin, first_sentence),
                name="send_first_sentence",
            )
            ensure_background_tasks_list(self._p).append(task)
            task.add_done_callback(
                lambda t: (
                    self._p._background_tasks.remove(t)
                    if t in self._p._background_tasks
                    else None
                )
            )

    # 流式隐藏标签（与 strip_draft_blocks 同源；抢发侧需流式增量版本）
    _STREAM_HIDDEN_TAGS = ("draft_notes", "thinking", "think")

    def _visible_stream_prefix(self, buffer: str) -> str:
        """流式抢发安全的"可见前缀"：剥掉已闭合的隐藏块，并在遇到【未闭合】的隐藏
        open 标签处截断——标签之后的内容尚未确定是不是思维链，绝不能抢发。

        修复（2026-06-13 用户诊断）：旧版 _extract_first_sentence 直接吃裸 buffer，
        模型流式【先吐 thinking】时，buffer 第一个句末标点落在 thinking 段里 →
        抢发了思维链碎片（泄漏 thinking 给用户）+ 存进 stream_first_sent 污染 remainder
        匹配，连锁触发 on_llm_response 的 stripped_to_empty 兜底。

        策略：
        1) 先用 (?is)<tag ...>.*?</tag> 去掉所有已闭合隐藏块（含跨行）；
        2) 扫剩余文本，遇到未闭合的隐藏 open 标签 → 在此截断（其后是 pending 思维链）；
        3) buffer 末尾若是半截标签（如 "<thi" / "<thinking"），一并切掉防误判。
        纯函数式，零状态。返回可安全用于抢发首句判定的可见前缀（可能为空）。
        """
        if not buffer:
            return ""
        tag_alt = "|".join(self._STREAM_HIDDEN_TAGS)
        # 1) 去掉已闭合隐藏块（非贪婪，含跨行 DOTALL + 大小写无关）
        cleaned = re.sub(rf"(?is)<(?:{tag_alt})[^>]*>.*?</(?:{tag_alt})>", "", buffer)
        # 2) 未闭合隐藏 open 标签 → 此处及之后全是 pending，截断
        m = re.search(rf"(?i)<(?:{tag_alt})(?:\s[^>]*)?>", cleaned)
        if m:
            cleaned = cleaned[: m.start()]
        # 3) 末尾半截标签（流式把 "<thinking>" 切在两个 chunk 间）→ 切掉，下个 chunk 再判
        m2 = re.search(r"<[a-zA-Z/]*$", cleaned)
        if m2:
            cleaned = cleaned[: m2.start()]
        return cleaned

    # 流式抢发首句的长度软上限：模型久不吐句末标点时，别把超长一坨当"首句"直发
    # （path5：流式首句不经分段 cap）。到阈值则在安全软边界（逗号/空格）切，没有就硬切。
    _STREAM_FIRST_SENT_MAX = 60

    def _extract_first_sentence(self, text: str) -> str:
        """从缓冲文本中提取第一个完整句子。

        以中英文句末标点或换行符为分隔。连续标点（如 "！？"）视为同一句。

        超长软切（M5 审查后收窄）：只在缓冲【含 CJK 或已出现过中文软标点】时，超过
        _STREAM_FIRST_SENT_MAX 仍无句末标点才在软边界切。**纯拉丁 run-on 保持旧的保守
        return ''（不抢发）**——否则会把模型先吐的无标签英文 CoT 当首句直发，重开
        "无标签英文思维链流式泄漏"那条在案信道（见 memory: thinking-leak-untagged-cot）。
        """
        delimiters = "。！？!?；;"
        for i, ch in enumerate(text):
            if ch in delimiters and i > 0:
                # Check if next char is not also a delimiter (e.g. "！？")
                if i + 1 < len(text) and text[i + 1] in delimiters:
                    continue
                return text[: i + 1]
            if ch == "\n" and i > 0:
                return text[:i]
        # 无句末标点但已超长 → 仅当含中文/中文软标点才软切；纯拉丁 run-on 不抢发（防 CoT 泄漏）
        if len(text) >= self._STREAM_FIRST_SENT_MAX:
            has_cjk = any("一" <= c <= "鿿" for c in text)
            has_cn_soft = any(c in "，、：" for c in text)
            if not (has_cjk or has_cn_soft):
                return ""  # 纯英文未断句：保守等待，绝不把英文 CoT 当首句直发
            window = text[: self._STREAM_FIRST_SENT_MAX]
            for j in range(len(window) - 1, self._STREAM_FIRST_SENT_MAX // 2 - 1, -1):
                if window[j] in "，、,：: ":
                    return text[: j + 1].rstrip()  # n3：去尾随空格
            return window.rstrip()  # 连软边界都没有 → 硬切窗口
        return ""

    async def _send_first_sentence(self, origin: str, text: str) -> None:
        """通过 context.send_message 发送首句文本。"""
        context = self._p.context
        if hasattr(context, "send_message"):
            message = self._astrbot_message(text)
            await context.send_message(origin, message)

    # ------------------------------------------------------------------
    # Segmented dispatch
    # ------------------------------------------------------------------
    async def _dispatch_segmented_parts(
        self, origin: str, parts: list[dict[str, Any]], session_key: str = ""
    ) -> None:
        """逐段发送分段回复，每段之间按计划延迟。

        Args:
            origin: 消息发送目标（unified_msg_origin）。
            parts: 分段列表，每段包含 text 和 delay_before_seconds。
            session_key: 会话标识，发送完成后清除 unfinished 标记。
        """
        context = self._p.context
        if not hasattr(context, "send_message"):
            return
        total = len(parts)
        try:
            for idx, part in enumerate(parts, 1):
                delay = float(part.get("delay_before_seconds", 0))
                if delay > 0:
                    await asyncio.sleep(delay)
                text = str(part.get("text", ""))
                if not text:
                    continue
                logger.info(
                    f"Sylanne segmented reply part {idx}/{total}: {text[:60]}"
                )
                message = self._astrbot_message(text)
                await context.send_message(origin, message)
                # 每发送一段，更新 unfinished 为剩余未发内容（消除竞态）
                if session_key and idx < total:
                    remaining_text = "".join(
                        str(p.get("text", "")) for p in parts[idx:]
                    )
                    if remaining_text:
                        self._p._store.unfinished_replies.set(session_key, remaining_text)
                    else:
                        self._p._store.unfinished_replies.pop(session_key, None)
        except asyncio.CancelledError:
            # 新请求 cancel 旧分段任务（llm_request_pipeline 主动 cancel segmented_tasks）：
            # 不静默吞——留痕已发到第几段，unfinished 保留剩余供续接/下轮判断，然后重抛。
            sent = locals().get("idx", 0)
            logger.info(
                "Sylanne segmented dispatch cancelled: session=%s sent=%d/%d "
                "(剩余留在 unfinished 供续接)",
                session_key, sent, total,
            )
            raise
        # 所有段发送成功——清除未完成标记
        if session_key:
            self._p._store.unfinished_replies.pop(session_key, None)

    # ------------------------------------------------------------------
    # Memory prompt fragment
    # ------------------------------------------------------------------
    # 记忆注入硬上限（字符数）
    _MEMORY_INJECT_MAX_CHARS: int = 4000

    def _memory_prompt_fragment(self, payload: dict[str, Any]) -> str:
        """将记忆查询结果格式化为 prompt 注入片段。

        Args:
            payload: 记忆查询返回的载荷，包含 matches 列表。

        Returns:
            格式化的 prompt 片段字符串，无匹配时返回空字符串。
            硬截断到 _MEMORY_INJECT_MAX_CHARS 字符以防止 prompt 膨胀。
        """
        matches = payload.get("matches", [])
        _query = str(payload.get("query") or "")
        if not matches:
            return ""
        lines = [
            "[M:ref/pri=current]",
        ]
        for match in matches[:3]:
            text = str(match.get("text") or "")[:120]
            lines.append(f">{text}")
        fragment = "\n".join(line for line in lines if line)
        # 硬截断：防止记忆注入超长导致 prompt 膨胀
        if len(fragment) > self._MEMORY_INJECT_MAX_CHARS:
            fragment = fragment[: self._MEMORY_INJECT_MAX_CHARS]
            logger.warning(
                "Memory injection truncated to %d chars (hard cap)",
                self._MEMORY_INJECT_MAX_CHARS,
            )
        return fragment

    def _append_request_prompt_fragment(self, request: Any, fragment: str) -> None:
        if not fragment:
            return
        current = str(getattr(request, "system_prompt", "") or "")
        request.system_prompt = f"{current}\n{fragment}".strip()

    # ------------------------------------------------------------------
    # Time context
    # ------------------------------------------------------------------
    def _time_context_fragment(self, session_key: str) -> str:
        """生成时间上下文片段：当前时间 + 距上次对话的间隔标签。"""
        now = datetime.now(_CHINA_TZ)
        weekday_names = ["一", "二", "三", "四", "五", "六", "日"]
        _weekday = weekday_names[now.weekday()]
        time_str = now.strftime("%H:%M")
        date_str = now.strftime("%m-%d")

        host = self._p._host(session_key)
        kernel = host.kernel
        last_event = kernel.last_event or {}
        has_previous = bool(last_event.get("now") or last_event.get("text"))
        if has_previous:
            last_now = float(last_event.get("now") or 0.0)
            gap_seconds = max(0.0, time.time() - last_now) if last_now else 0.0
            gap_label = self._gap_label_from_seconds(gap_seconds, True)
        else:
            gap_label = "首次"

        return f"[T:{date_str}-W{now.weekday()}-{time_str}/gap:{gap_label}]"

    def _gap_label_from_seconds(self, seconds: float, has_previous: bool) -> str:
        """将时间间隔（秒）转换为自然语言标签。"""
        if not has_previous:
            return "first_event"
        if seconds < 900:
            return "刚刚"
        if seconds < 7200:
            return "刚才"
        if seconds < 86400:
            return "隔了一阵"
        if seconds < 259200:
            return "隔天"
        return "隔了很久"

    def _event_time(self, now: float = 0.0) -> dict[str, Any]:
        ts = datetime.now(_CHINA_TZ)
        return {
            "local_datetime": ts.isoformat(),
            "timezone": "Asia/Shanghai",
            "epoch": now or time.time(),
        }

    # ------------------------------------------------------------------
    # Payload capping
    # ------------------------------------------------------------------
    def _cap_llm_request_payload(self, request: Any) -> None:
        """裁剪 LLM 请求载荷，确保序列化后不超过最大字符限制。

        多轮渐进裁剪：先裁 extra_user_content_parts，再裁 contexts 和 messages。
        """
        locked = self._p._config.get("sylanne_alpha_locked_persona_prompt")
        _locked_system = str(locked) if locked else None

        _system_prompt = getattr(request, "system_prompt", None)
        _prompt = getattr(request, "prompt", None)

        for pass_num in range(5):
            try:
                serialized = json.dumps(
                    request.__dict__, ensure_ascii=False, default=str
                )
            except (TypeError, ValueError):
                break
            if len(serialized) <= _MAX_PAYLOAD_SERIALIZED_CHARS:
                break

            text_limit = max(200, 5000 // (pass_num + 1))

            extra = getattr(request, "extra_user_content_parts", None)
            if isinstance(extra, list) and extra:
                request.extra_user_content_parts = self._trim_payload_list(
                    extra, keep_items=1, text_limit=text_limit
                )

            if pass_num >= 2:
                keep = max(4, 8 - pass_num * 2)
                contexts = getattr(request, "contexts", None)
                if isinstance(contexts, list) and contexts:
                    request.contexts = self._trim_payload_list(
                        contexts, keep_items=keep, text_limit=text_limit
                    )
                messages = getattr(request, "messages", None)
                if isinstance(messages, list) and messages:
                    filtered = [m for m in messages if not isinstance(m, str)]
                    request.messages = self._trim_payload_list(
                        filtered, keep_items=keep, text_limit=text_limit
                    )

    def _trim_payload_list(
        self, items: list, keep_items: int = 2, text_limit: int = 5000
    ) -> list:
        if not items:
            return items
        if len(items) <= keep_items:
            # Just cap text length
            return [self._cap_item_text(item, text_limit) for item in items]

        # Strategy: keep first `keep_items` items + 1 marker replacing the rest
        kept = [
            self._cap_item_text(items[i], text_limit)
            for i in range(min(keep_items, len(items)))
        ]
        # Always keep the last item if it's different from what we already kept
        tail = self._cap_item_text(items[-1], text_limit)
        marker = self._make_trim_marker(items)

        # If keep_items >= 2, result = kept[:-1] + [marker] + [tail]
        # If keep_items == 1, result = [kept[0], marker]  (tail is sacrificed)
        if keep_items >= 2:
            result = [kept[0], marker, tail]
            if keep_items > 2 and len(kept) > 1:
                result = kept[:-1] + [marker, tail]
        else:
            # keep_items == 1: just head + marker
            result = [kept[0], marker]

        return result

    def _cap_item_text(self, item: Any, limit: int) -> Any:
        if isinstance(item, dict):
            # Check both "content" and "text" keys
            for key in ("content", "text"):
                val = item.get(key, "")
                if isinstance(val, str) and len(val) > limit:
                    item = dict(item)
                    item[key] = val[:limit] + "\n[sylanne_payload_context_trimmed]"
            return item
        if hasattr(item, "text"):
            text = str(getattr(item, "text", "") or "")
            if len(text) > limit:
                try:
                    item.text = text[:limit] + "\n[sylanne_payload_context_trimmed]"
                except (AttributeError, TypeError):
                    pass
            return item
        if hasattr(item, "content"):
            content = str(getattr(item, "content", "") or "")
            if len(content) > limit:
                try:
                    item.content = (
                        content[:limit] + "\n[sylanne_payload_context_trimmed]"
                    )
                except (AttributeError, TypeError):
                    pass
            return item
        return item

    def _make_trim_marker(self, items: list) -> Any:
        """Create a trim marker matching the type of items in the list."""
        sample = items[1] if len(items) > 1 else items[0]
        if isinstance(sample, dict):
            role = sample.get("role", "user")
            return {"role": role, "content": "[sylanne_payload_context_trimmed]"}
        if hasattr(sample, "text"):
            # Try to create same type
            try:
                marker = type(sample)(text="[sylanne_payload_context_trimmed]")
                return marker
            except (TypeError, ValueError):
                return SimpleNamespace(text="[sylanne_payload_context_trimmed]")
        return {"role": "user", "content": "[sylanne_payload_context_trimmed]"}

    # ------------------------------------------------------------------
    # Claude/hajide compat stubs (minimal implementation)
    # ------------------------------------------------------------------
    def _state_injection_budget_for_request(
        self, session_key: str, request: Any, model_hint: str = ""
    ) -> Any:
        """为请求创建状态注入预算对象。

        根据模型类型决定兼容模式：
          - claude_agent_owned_context: 哈基德模式，跳过额外注入
          - claude_advisory: Claude 建议模式，以 advisory 标记注入
          - 默认：正常注入到 extra_user_content_parts
        """
        # Access _StateInjectionBudget from the plugin's module to avoid circular import
        import sys

        _mod = sys.modules.get(type(self._p).__module__)
        _StateInjectionBudget = getattr(_mod, "_StateInjectionBudget", None)
        if _StateInjectionBudget is None:
            from main import _StateInjectionBudget

        budget = _StateInjectionBudget(session_key=session_key, model_hint=model_hint)
        cfg = self._p.config or {}
        budget.max_added_chars = int(cfg.get("state_injection_max_added_chars", 2400))
        budget.max_parts = int(cfg.get("state_injection_max_parts", 8))
        hajide = bool(cfg.get("sylanne_alpha_hajide_compat_mode"))
        is_claude = (
            "claude" in model_hint.lower()
            or "anthropic" in model_hint.lower()
            or "哈基德" in model_hint
        )
        if hajide and is_claude:
            budget.compat_mode = "claude_agent_owned_context"
        elif is_claude:
            budget.compat_mode = "claude_advisory"
        return budget

    def _append_temp_text_part(
        self,
        request: Any,
        text: str,
        source: str = "",
        budget: Any | None = None,
    ) -> bool:
        if budget and budget.compat_mode == "claude_agent_owned_context":
            budget.skipped.append(
                {"source": source, "reason": "claude_agent_owned_context"}
            )
            return False
        if budget and budget.compat_mode == "claude_advisory":
            # Claude advisory: 注入到 system_prompt（不持久化）
            # 手册明确：request.prompt 会持久化，system_prompt 不会
            current_sys = str(getattr(request, "system_prompt", "") or "")
            if "[claude_advisory_context]" not in current_sys:
                request.system_prompt = f"{current_sys}\n[claude_advisory_context]\n{text}".strip()
            else:
                request.system_prompt = f"{current_sys}\n{text}".strip()
            if budget:
                budget.injected.append({"source": source})
            return True
        # Normal mode: 也注入到 system_prompt 避免历史污染
        current_sys = str(getattr(request, "system_prompt", "") or "")
        request.system_prompt = f"{current_sys}\n{text}".strip()
        if budget:
            budget.injected.append({"source": source})
        return True

    def _normalize_claude_request_payload(
        self, request: Any, budget: Any | None = None
    ) -> None:
        """规范化请求格式以兼容 Claude/哈基德模式。

        处理内容：
          - 将 extra_user_content_parts 展平到 prompt
          - 将 system role 的 contexts 合并到 system_prompt
          - 清理非标准 role 的 messages
          - 哈基德模式下裁剪 Sylanne 工具
        """
        hajide = bool(self._p._config.get("sylanne_alpha_hajide_compat_mode"))

        # extra_user_content_parts: 仅哈基德模式展平到 system_prompt
        # 普通模式保留原样，尊重其他插件的持久化语义
        if hajide:
            extra = getattr(request, "extra_user_content_parts", None)
            if isinstance(extra, list) and extra:
                texts = []
                for part in extra:
                    if hasattr(part, "text"):
                        texts.append(str(part.text))
                    elif isinstance(part, dict) and "text" in part:
                        texts.append(str(part["text"]))
                if texts:
                    current = str(getattr(request, "system_prompt", "") or "")
                    request.system_prompt = f"{current}\n" + "\n".join(texts) if current else "\n".join(texts)
                request.extra_user_content_parts = []

            # contents: 仅哈基德模式展平
            contents = getattr(request, "contents", None)
            if isinstance(contents, list) and contents:
                texts = []
                for item in contents:
                    if isinstance(item, dict) and "text" in item:
                        texts.append(str(item["text"]))
                    elif hasattr(item, "text"):
                        texts.append(str(item.text))
                if texts:
                    current = str(getattr(request, "system_prompt", "") or "")
                    request.system_prompt = f"{current}\n" + "\n".join(texts) if current else "\n".join(texts)
                request.contents = []

        # Flatten contexts with system role into system_prompt
        contexts = getattr(request, "contexts", None)
        if isinstance(contexts, list) and contexts:
            system_parts = []
            remaining = []
            for ctx in contexts:
                role = (
                    ctx.get("role", "")
                    if isinstance(ctx, dict)
                    else str(getattr(ctx, "role", ""))
                )
                content = (
                    ctx.get("content", "")
                    if isinstance(ctx, dict)
                    else str(getattr(ctx, "content", ""))
                )
                if role == "system":
                    system_parts.append(content)
                elif hajide and role in ("tool", "function"):
                    continue
                elif hajide and role == "assistant" and (
                    ctx.get("tool_calls")
                    if isinstance(ctx, dict)
                    else getattr(ctx, "tool_calls", None)
                ):
                    # 对称处理：hajide 下删除 tool 响应消息时，同时移除带 tool_calls
                    # 的 assistant，否则会留下孤儿 tool_calls 触发严格 provider 400
                    # （与下方 messages 清洗 :760-761 对齐，fixes #18）
                    continue
                else:
                    remaining.append(ctx)
            if system_parts:
                sys_prompt = str(getattr(request, "system_prompt", "") or "")
                request.system_prompt = (
                    f"{sys_prompt}\n" + "\n".join(system_parts)
                    if sys_prompt
                    else "\n".join(system_parts)
                )
            request.contexts = remaining

        # Sanitize messages
        messages = getattr(request, "messages", None)
        if isinstance(messages, list) and messages:
            clean = []
            for msg in messages:
                if isinstance(msg, dict):
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if hajide:
                        # In hajide mode, skip tool/function messages and assistant with tool_calls
                        if role in ("tool", "function"):
                            continue
                        if role == "assistant" and "tool_calls" in msg:
                            continue
                    # Convert system to system_prompt
                    if role == "system":
                        sys_prompt = str(getattr(request, "system_prompt", "") or "")
                        request.system_prompt = (
                            f"{sys_prompt}\n{content}" if sys_prompt else content
                        )
                        continue
                    # Normalize content
                    if isinstance(content, list):
                        text_parts = [
                            str(p.get("text", ""))
                            if isinstance(p, dict)
                            else str(getattr(p, "text", ""))
                            for p in content
                        ]
                        content = "\n".join(text_parts)
                    # Map non-standard roles to user
                    mapped_role = role if role in ("user", "assistant") else "user"
                    clean.append({"role": mapped_role, "content": content})
                elif hasattr(msg, "role"):
                    role = str(getattr(msg, "role", ""))
                    content = getattr(msg, "content", "")
                    if hajide and role in ("tool", "function"):
                        continue
                    if isinstance(content, list):
                        text_parts = [
                            str(p.get("text", ""))
                            if isinstance(p, dict)
                            else str(getattr(p, "text", ""))
                            for p in content
                        ]
                        content = "\n".join(text_parts)
                    mapped_role = role if role in ("user", "assistant") else "user"
                    clean.append({"role": mapped_role, "content": str(content)})
            request.messages = clean

        # Hajide mode: prune sylanne tools
        if hajide:
            self._prune_hajide_tools(request, budget)

    def _prune_hajide_tools(self, request: Any, budget: Any | None = None) -> None:
        """哈基德兼容模式：从请求中移除 Sylanne 专用工具。

        防止 Claude 模型尝试调用不存在的 Sylanne 内部工具。
        """
        _SYLANNE_TOOL_PREFIXES = (
            "query_agent_state",
            "get_bot_emotion",
            "get_bot_integrated",
            "get_bot_humanlike",
            "get_bot_lifelike",
            "get_bot_personality",
        )

        def _is_sylanne_tool(name: str) -> bool:
            return any(name.startswith(prefix) for prefix in _SYLANNE_TOOL_PREFIXES)

        # Prune tools list
        tools = getattr(request, "tools", None)
        if isinstance(tools, list):
            request.tools = [
                t
                for t in tools
                if not (
                    isinstance(t, dict)
                    and _is_sylanne_tool(t.get("function", {}).get("name", ""))
                )
            ]
            if budget:
                budget.skipped.append(
                    {"source": "sylanne_llm_tools", "reason": "hajide_compat"}
                )

        # Prune functions list
        functions = getattr(request, "functions", None)
        if isinstance(functions, list):
            request.functions = [
                f
                for f in functions
                if not (isinstance(f, dict) and _is_sylanne_tool(f.get("name", "")))
            ]

        # Reset tool_choice if it pointed to a pruned tool
        tool_choice = getattr(request, "tool_choice", None)
        if isinstance(tool_choice, dict):
            name = (
                tool_choice.get("function", {}).get("name", "")
                if isinstance(tool_choice.get("function"), dict)
                else ""
            )
            if _is_sylanne_tool(name):
                request.tool_choice = "auto"
        elif tool_choice == "required":
            request.tool_choice = "auto"

        # Reset function_call
        function_call = getattr(request, "function_call", None)
        if isinstance(function_call, dict):
            request.function_call = "auto"

        # Handle nested params.extra_body
        params = getattr(request, "params", None)
        if isinstance(params, dict) and "extra_body" in params:
            extra_body = params["extra_body"]
            if isinstance(extra_body, dict):
                if "tools" in extra_body and isinstance(extra_body["tools"], list):
                    extra_body["tools"] = [
                        t
                        for t in extra_body["tools"]
                        if not (
                            isinstance(t, dict)
                            and _is_sylanne_tool(t.get("function", {}).get("name", ""))
                        )
                    ]
                if "tool_choice" in extra_body and isinstance(
                    extra_body["tool_choice"], dict
                ):
                    extra_body["tool_choice"] = "auto"

        # Handle metadata.tool_choice
        metadata = getattr(request, "metadata", None)
        if isinstance(metadata, dict) and "tool_choice" in metadata:
            if isinstance(metadata["tool_choice"], dict):
                metadata["tool_choice"] = "auto"

        # Handle provider_settings.function_call
        provider_settings = getattr(request, "provider_settings", None)
        if isinstance(provider_settings, dict) and "function_call" in provider_settings:
            if isinstance(provider_settings["function_call"], dict):
                provider_settings["function_call"] = "auto"

        # Disable func_tool
        func_tool = getattr(request, "func_tool", None)
        if func_tool is not None:
            # Check if it has sylanne tools
            names = []
            if hasattr(func_tool, "names"):
                names = func_tool.names()
            elif hasattr(func_tool, "funcs") and isinstance(func_tool.funcs, dict):
                names = list(func_tool.funcs.keys())
            if names and any(_is_sylanne_tool(n) for n in names):
                request.func_tool = None
                if hasattr(request, "tool_choice"):
                    request.tool_choice = "auto"
                if budget:
                    budget.skipped.append(
                        {"source": "sylanne_func_tool", "reason": "hajide_compat"}
                    )

    # ------------------------------------------------------------------
    # Text extraction from event
    # ------------------------------------------------------------------
    def _text(self, event: Any) -> str:
        """从事件中提取文本内容，支持转发消息和 JSON 链接卡片。"""
        parts: list[str] = []
        message_str = str(getattr(event, "message_str", "") or "")
        if message_str:
            parts.append(message_str)

        chain = getattr(event, "message_chain", None)
        if isinstance(chain, list):
            for component in chain:
                comp_type = str(getattr(component, "type", "") or "")
                if comp_type == "Plain":
                    text = str(getattr(component, "text", "") or "")
                    if text and text not in parts:
                        parts.append(text)
                elif comp_type == "Forward":
                    nodes = getattr(component, "nodes", [])
                    if isinstance(nodes, list):
                        for node in nodes:
                            if isinstance(node, dict):
                                content = node.get("content", "")
                                if content:
                                    parts.append(str(content))
                            elif hasattr(node, "message"):
                                msg_list = getattr(node, "message", [])
                                if isinstance(msg_list, list):
                                    for m in msg_list:
                                        t = str(getattr(m, "text", "") or "")
                                        if t:
                                            parts.append(t)
                elif comp_type == "Json":
                    data = getattr(component, "data", None)
                    if isinstance(data, dict):
                        meta = data.get("meta", {})
                        if isinstance(meta, dict):
                            news = meta.get("news", {})
                            if isinstance(news, dict):
                                title = str(news.get("title", "") or "")
                                desc = str(news.get("desc", "") or "")
                                if title:
                                    parts.append(title)
                                if desc:
                                    parts.append(desc)

        return " ".join(parts) if parts else ""

    # ------------------------------------------------------------------
    # Sensitive topic tagging (Item 74)
    # ------------------------------------------------------------------

    # 敏感话题关键词分类
    _SENSITIVE_KEYWORDS: dict[str, list[str]] = {
        "health": ["病", "药", "医院", "诊断", "手术", "癌", "抑郁", "焦虑"],
        "finance": ["贷款", "欠款", "破产", "债务", "催收", "逾期", "高利贷"],
        "legal": ["律师", "起诉", "判决", "法院", "拘留", "逮捕", "刑事"],
    }

    def _tag_sensitive(self, text: str) -> tuple[str, bool]:
        """检查文本是否包含敏感话题关键词。

        敏感类别：健康（病/药/医院/诊断）、财务（贷款/欠款/破产）、法律（律师/起诉/判决）。
        如果包含任一关键词，返回 (text, True)，标记该记忆条目为 sensitive，
        不参与跨会话召回。

        Args:
            text: 待检查的文本内容。

        Returns:
            (text, is_sensitive) 元组。text 原样返回，is_sensitive 表示是否命中敏感词。
        """
        if not text:
            return (text, False)
        for _category, keywords in self._SENSITIVE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text:
                    return (text, True)
        return (text, False)

    # ------------------------------------------------------------------
    # Item 1: 对话情绪回顾摘要
    # ------------------------------------------------------------------

    def _generate_session_summary(self, session_key: str) -> str | None:
        """生成对话情绪回顾摘要。

        检查该 session 最后一条消息时间，如果距今 > 30min，生成情绪弧线摘要。
        摘要格式："本次对话从[情绪A]开始，经历了[事件]，以[情绪B]结束"

        通过 body_state 的 valence 变化来推断情绪弧线。调用方负责存入记忆。

        Args:
            session_key: 会话标识。

        Returns:
            摘要字符串，不满足条件时返回 None。
        """
        p = self._p
        import time as _time

        # 获取对话缓冲区
        buf = p._store.conversation_buffers.get(session_key)
        if not buf or not buf.messages:
            return None

        # 检查最后一条消息时间
        last_msg = buf.messages[-1] if buf.messages else None
        if not last_msg:
            return None
        last_ts = float(last_msg.get("ts", 0) or last_msg.get("timestamp", 0) or 0)
        if last_ts <= 0:
            return None
        if _time.time() - last_ts <= 1800:  # 30 min
            return None

        # 从 host 获取 body_state 的 valence 历史
        try:
            host = p._host(session_key)
            body = host.kernel.body
        except Exception:
            return None

        # 推断情绪弧线：从 traces 中提取 valence 变化
        traces = body.memory.get("traces", [])
        if len(traces) < 2:
            return None

        def _valence_label(v: float) -> str:
            if v > 0.5:
                return "愉悦"
            elif v > 0.2:
                return "轻松"
            elif v > -0.2:
                return "平静"
            elif v > -0.5:
                return "低落"
            else:
                return "沉重"

        # 取首尾 trace 的 valence
        first_trace = traces[0] if traces else {}
        last_trace = traces[-1] if traces else {}
        first_valence = float(first_trace.get("valence", 0) or 0)
        last_valence = float(last_trace.get("valence", 0) or 0)

        start_emotion = _valence_label(first_valence)
        end_emotion = _valence_label(last_valence)

        # 检测中间是否有显著变化（找极值点）
        mid_event = ""
        if len(traces) >= 3:
            valences = [float(t.get("valence", 0) or 0) for t in traces]
            max_v = max(valences)
            min_v = min(valences)
            if max_v - min_v > 0.4:
                peak_idx = valences.index(max_v)
                trough_idx = valences.index(min_v)
                if peak_idx < trough_idx:
                    mid_event = "情绪高点后回落"
                else:
                    mid_event = "经历低谷后回升"

        if mid_event:
            summary = f"本次对话从{start_emotion}开始，{mid_event}，以{end_emotion}结束"
        else:
            summary = f"本次对话从{start_emotion}开始，以{end_emotion}结束"

        return summary

    # ------------------------------------------------------------------
    # AstrBot message building
    # ------------------------------------------------------------------
    def _astrbot_message(self, text: str) -> Any:
        """构建适用于 context.send_message 的消息对象。

        优先使用 AstrBot 的 MessageChain + Plain 组件，不可用时回退为纯文本。
        """
        import sys

        comp_mod = sys.modules.get("astrbot.api.message_components")
        event_mod = sys.modules.get("astrbot.api.event")
        if comp_mod and event_mod:
            _Plain = getattr(comp_mod, "Plain", None)
            _Chain = getattr(event_mod, "MessageChain", None)
            if _Plain and _Chain:
                chain = _Chain()
                part = _Plain(text)
                # Support both .chain and .parts attributes
                if hasattr(chain, "chain") and isinstance(chain.chain, list):
                    chain.chain.append(part)
                elif hasattr(chain, "parts") and isinstance(chain.parts, list):
                    chain.parts.append(part)
                else:
                    # Try append method
                    if hasattr(chain, "append"):
                        chain.append(part)
                return chain
        # Fallback: just return the text string
        return text
