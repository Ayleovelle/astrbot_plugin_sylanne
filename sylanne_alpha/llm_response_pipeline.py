"""LLM 响应管线 —— 拦截 on_llm_response 事件的核心处理模块。

职责：
  1. 拦截 LLM 响应，清理 thinking/draft 块
  2. 实现分段回复：将长回复拆分为多条消息，模拟人类打字节奏
  3. 流式首句快速发送：在流式输出中检测到第一句完成时立即发送
  4. 后台触发记忆写入和状态更新
  5. 控制请求载荷大小并生成状态注入预算

与其他组件的关系：
  - 与 llm_request_pipeline 配对：request 注入上下文，response 处理输出
  - 调用 rhythm_learner 获取自适应分段参数
  - 通过 observe_response 将回复反馈给计算栈

所有方法通过 ``self._p`` 委托访问插件实例属性。
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import random
import re
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from sylanne_alpha.delivery_ledger import SegmentedDeliveryTurn
from sylanne_alpha.llm_request_pipeline import (
    _PROACTIVE_TEMPLATE_PLACEHOLDER,
    _PROACTIVE_TEMPLATE_SIGNATURE,
    _ctx_leading_text,
    _ctx_role,
    sanitize_tool_call_pairing,
)
from sylanne_alpha.utils import ensure_background_tasks_list, safe_ensure_future
from sylanne_alpha.message_dispatch import (
    normalize_completion_text,
    realtime_flags,
    realtime_plan,
    strip_draft_blocks,
)
from sylanne_alpha.proactive_bridge import is_night_fast_reply_exempt
from sylanne_alpha.scope_contracts import TurnDeliveryLease
from sylanne_alpha.scope_delivery import (
    DeliveryClaim,
    DeliveryLeaseRejected,
    DeliveryState,
    ProcessLocalDeliveryTurn,
    ReactiveDeliveryCoordinator,
)
from sylanne_alpha.semantic_segmentation import (
    SEMANTIC_BEAT_NONCE_EXTRA,
    SemanticBeatPart,
    parse_semantic_completion,
    scrub_semantic_marker_candidates,
    semantic_parts_from_visible_line_breaks,
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

try:
    from astrbot.api.message_components import Plain as _RealtimePlainComponent  # type: ignore
except ImportError:
    _RealtimePlainComponent = None  # type: ignore


def _is_non_plain_component(seg: Any) -> bool:
    """M1 安全判定：判 seg 是否为【非 Plain】消息组件（Image/Record 等）。

    astrbot 未安装（测试环境等）时 _RealtimePlainComponent 拿不到——保守返回
    False（不触发放弃接管这条分支），不影响既有单测行为。
    """
    if _RealtimePlainComponent is None:
        return False
    return not isinstance(seg, _RealtimePlainComponent)

# 中国时区常量
_CHINA_TZ = timezone(timedelta(hours=8))
# 序列化后的请求载荷最大字符数，超过则触发裁剪
_MAX_PAYLOAD_SERIALIZED_CHARS = 60000

# T1-02③ 身体驱动打字速度（chars/sec）。基线沿用原恒定默认值，energy/arousal
# 各按 ±4.0 幅度围绕基线摆动，tension 只往下拖（紧张不会打字变快）；
# 最终 clamp 到 [4.5, 11]（card 给定区间），energy=0/arousal=1 时约落在给定
# 示例值 5.5 / 9.5 附近（验证见 tests/test_wave_l1_g4_liveness.py）。
_DEFAULT_CPS = 7.5
_CPS_MIN = 4.5
_CPS_MAX = 11.0
_CPS_ENERGY_WEIGHT = 4.0
_CPS_AROUSAL_WEIGHT = 4.0
_CPS_TENSION_WEIGHT = 1.0

# T1-01 读信时间："看到消息到开始打字"的启动延迟，区别于 T1-02 的段内打字节奏
# （4.2s 硬顶那个是打字本身）。杀的问题：深夜 300 字表白和一句"哦"此前拿到完全
# 相同的 LLM 速度瞬发首段——零思考时间。范围保守：0.8s 底~6s 顶（正常白天场景）。
_THINK_DELAY_FLOOR = 0.8
_THINK_DELAY_CEILING = 6.0
_THINK_READ_CPS = 12.0  # 阅读速度（比打字快），消息越长读得越久
_THINK_READ_CAP = 3.0  # 阅读耗时封顶：消息再长也别把读信时间推爆
_THINK_INTENSITY_WEIGHT = 2.2  # 情绪强度越高回得越快（红队意见：重话该更快回，不是更慢）
_THINK_GAP_WEIGHT = 1.6  # 隔得越久，重新搭话的启动稍慢一点
_THINK_GAP_SATURATE_SECONDS = 3600.0  # 超过 1 小时不再继续加码
_THINK_ENERGY_WEIGHT = 1.2  # 没精神启动慢
_THINK_TENSION_WEIGHT = 0.6  # 紧张一点点拖慢启动（呼应 cps 里 tension 只往下拖）
_THINK_JITTER_MIN = 0.85
_THINK_JITTER_MAX = 1.2

# T1-03 夜间温和版（config: sylanne_alpha_night_rhythm_enabled，默认关）。免打扰
# 时段给读信时间温和放大、打字速度降一档——不是"变冷淡"，只是深夜人有点迷糊。
# 硬顶 _NIGHT_THINK_DELAY_CAP=10s：红队铁律——绝不允许滑向分钟级不理人，夜里
# 一直在是核心安全感，这张卡只加轻微质感。孤独/紧急关键词命中（见 proactive_bridge.
# is_night_fast_reply_exempt）时整层直接豁免，原速回复。
_NIGHT_THINK_DELAY_MULT_MIN = 1.5
_NIGHT_THINK_DELAY_MULT_MAX = 2.5
_NIGHT_THINK_DELAY_CAP = 10.0
_NIGHT_CPS_DELTA = -1.0  # 打字速度降一档，仍会被 clamp 回 [_CPS_MIN, _CPS_MAX]

# T2-02 补刀与改口：一段 SPEAK 分段回复正常发完（未被打断）后，按表达驱动力算一个
# 概率骰子，命中则 20~180s 后追发一句很短的补充/更正。杀的问题：她说完话就再没
# 声了——unfinished_replies/断点残留只会在【下一轮用户消息】里被动带出，从不会
# 自己先开口补一句。默认关闭（sylanne_alpha_afterthought_enabled）。
_AFTERTHOUGHT_DELAY_MIN = 20.0
_AFTERTHOUGHT_DELAY_MAX = 180.0
# 概率 = floor + drive_weight * expression_drive（[0,1] 上的表达驱动力，同 rhythm_learner
# 用的那个 host.kernel.computation.engine.expression_drive()），clamp 到 [floor, ceil]。
_AFTERTHOUGHT_PROB_FLOOR = 0.05
_AFTERTHOUGHT_PROB_CEIL = 0.45
_AFTERTHOUGHT_PROB_DRIVE_WEIGHT = 0.40
# 冷却：同会话至少隔 8 轮"发完一段完整回复"才允许再触发一次，避免刷屏。
_AFTERTHOUGHT_REFRACTORY_EXCHANGES = 8
# 追发首段前的固定小延迟（不用 think_delay 那套读信逻辑——这不是在回一条新消息，
# 是她自己突然想起点什么，不需要"读信"时间）。
_AFTERTHOUGHT_FIRST_DELAY = 0.6


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

    def _active_scope(self) -> Any | None:
        getter = getattr(self._p, "_bound_runtime", None)
        if not callable(getter):
            return None
        try:
            binding = getter()
        except Exception:
            return None
        return getattr(binding, "scope", None) if binding is not None else None

    def _claim_reactive_delivery(
        self,
        event: Any,
        parts: list[dict[str, Any]],
    ) -> tuple[ReactiveDeliveryCoordinator, DeliveryClaim] | None:
        """Seal one scoped reactive turn to its original AstrBot event.

        Registry-free fixture and compatibility callers retain the historical
        ``Context.send_message`` path. A production plugin always owns a scope
        registry; once that capability exists, an incomplete frozen view is a
        fail-closed activation error rather than a reason to fall back.
        """

        registry = getattr(self._p, "_scope_runtime_registry", None)
        if registry is None:
            return None
        is_issued_request_view = getattr(registry, "is_issued_request_view", None)
        binding_getter = getattr(self._p, "_bound_runtime", None)
        if not callable(is_issued_request_view) or not callable(binding_getter):
            raise DeliveryLeaseRejected("scoped reactive delivery runtime is unavailable")

        binding = binding_getter()
        view = getattr(binding, "request_runtime_view", None)
        event_view = self._event_extra(event, "_sylanne_runtime_view_v1", None)
        if event_view is not view:
            raise DeliveryLeaseRejected(
                "reactive delivery event is not sealed to the request view"
            )
        try:
            issued = is_issued_request_view(view)
        except Exception as exc:
            raise DeliveryLeaseRejected(
                "reactive delivery request view could not be verified"
            ) from exc
        if issued is not True:
            raise DeliveryLeaseRejected("reactive delivery request view is not issued")
        resolved = getattr(view, "resolved", None)
        scope = getattr(resolved, "scope", None)
        turn_generation = getattr(resolved, "turn_generation", None)
        if scope is None or turn_generation is None:
            raise DeliveryLeaseRejected("reactive delivery has no frozen request view")

        planned_parts = tuple(str(part.get("text", "")) for part in parts)
        if not planned_parts or any(not text for text in planned_parts):
            raise DeliveryLeaseRejected("reactive delivery requires non-empty planned parts")

        lease = TurnDeliveryLease(
            transport_session_token=scope.session_ref.token,
            resolved_scope_token=scope.storage_token,
            bot_binding_generation=scope.bot_ref.generation,
            persona_lifecycle_generation=scope.persona_ref.lifecycle_generation,
            session_generation=scope.session_ref.generation,
            scope_generation=scope.scope_generation,
            turn_generation=turn_generation,
        )
        coordinator = ReactiveDeliveryCoordinator(
            ProcessLocalDeliveryTurn(planned_parts=planned_parts),
            is_issued_request_view=is_issued_request_view,
        )
        claim = coordinator.claim(view=view, lease=lease, event=event)
        return coordinator, claim

    # ------------------------------------------------------------------
    # Injection defense
    # ------------------------------------------------------------------
    # 匹配 LLM 伪造的 [sylanne_xxx] 系统标签
    _RE_SYLANNE_TAG = re.compile(r"\[sylanne_[^\]]*\]")
    _SEMANTIC_CORRELATION_EXTRA = "_syl_semantic_beat_correlation"
    _PROVIDER_HISTORY_TXN_EXTRA = "_syl_provider_history_txn"
    _DELIVERY_TURN_EXTRA = "_syl_segmented_delivery_turn"

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

    @staticmethod
    def _text_digest(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _event_extra(event: Any, key: str, default: Any = None) -> Any:
        getter = getattr(event, "get_extra", None)
        if not callable(getter):
            return default
        try:
            return getter(key, default)
        except TypeError:
            try:
                value = getter(key)
            except Exception:
                return default
            return default if value is None else value
        except Exception:
            return default

    @staticmethod
    def _request_has_current_message(request: Any) -> bool:
        """Mirror AstrBot runner.reset()'s current-message append predicate."""

        return bool(
            getattr(request, "prompt", None) is not None
            or getattr(request, "image_urls", None)
            or getattr(request, "audio_urls", None)
            or getattr(request, "extra_user_content_parts", None)
        )

    @staticmethod
    def _message_content(message: Any) -> Any:
        if isinstance(message, dict):
            return message.get("content")
        return getattr(message, "content", None)

    @staticmethod
    def _proactive_placeholder_copy(message: Any) -> Any:
        clone = copy.deepcopy(message)
        original_content = LLMResponsePipeline._message_content(message)
        placeholder: Any = _PROACTIVE_TEMPLATE_PLACEHOLDER
        if isinstance(original_content, list) and isinstance(clone, dict):
            placeholder = [{"type": "text", "text": _PROACTIVE_TEMPLATE_PLACEHOLDER}]
        if isinstance(clone, dict):
            clone["content"] = placeholder
        else:
            setattr(clone, "content", placeholder)
        return clone

    def on_agent_begin(self, event: Any, run_context: Any) -> bool:
        """Build a reversible provider-only history view before context processing.

        AstrBot persists ``run_context.messages`` after the agent finishes. Request-time
        edits to ``request.contexts`` therefore write through to the database. This hook
        runs after ``runner.reset()`` has built Message objects, so the provider can see a
        cleaned projection while the original objects remain available for restoration.
        """

        messages = getattr(run_context, "messages", None)
        request = self._event_extra(event, "provider_request", None)
        setter = getattr(event, "set_extra", None)
        if (
            not isinstance(messages, list)
            or not messages
            or request is None
            or not callable(setter)
            or isinstance(
                self._event_extra(event, self._PROVIDER_HISTORY_TXN_EXTRA, None),
                dict,
            )
        ):
            return False

        original_messages = tuple(messages)
        history_end = len(messages) - int(self._request_has_current_message(request))
        history_end = max(0, history_end)
        history = list(messages[:history_end])
        current_tail = list(messages[history_end:])

        projected_history: list[Any] = []
        replacements: list[tuple[Any, Any]] = []
        inner_hidden = 0
        proactive_replaced = 0
        for message in history:
            role = _ctx_role(message)
            leading_text = _ctx_leading_text(self._message_content(message))
            if role == "assistant" and "[inner_context]" in leading_text:
                inner_hidden += 1
                continue
            if role == "user" and leading_text.startswith(
                _PROACTIVE_TEMPLATE_SIGNATURE
            ):
                try:
                    replacement = self._proactive_placeholder_copy(message)
                except Exception:
                    projected_history.append(message)
                    continue
                projected_history.append(replacement)
                replacements.append((replacement, message))
                proactive_replaced += 1
                continue
            projected_history.append(message)

        sanitized = sanitize_tool_call_pairing(projected_history)
        if not isinstance(sanitized, list):
            sanitized = projected_history
        orphan_hidden = len(projected_history) - len(sanitized)
        if not (inner_hidden or proactive_replaced or orphan_hidden):
            return False

        replacement_origins = {id(replacement): original for replacement, original in replacements}
        projected_messages = [*sanitized, *current_tail]
        visible_originals = tuple(
            replacement_origins.get(id(message), message)
            for message in projected_messages
        )
        txn = {
            "request": request,
            "original_messages": original_messages,
            "visible_originals": visible_originals,
            "replacements": tuple(replacements),
        }

        try:
            setter(self._PROVIDER_HISTORY_TXN_EXTRA, txn)
            messages[:] = projected_messages
            conversation = getattr(request, "conversation", None)
            if conversation is not None:
                # AstrBot treats a positive value as authoritative even though the
                # provider view now contains different bytes. Re-estimate this turn.
                conversation.token_usage = 0
        except Exception:
            messages[:] = list(original_messages)
            try:
                setter(self._PROVIDER_HISTORY_TXN_EXTRA, None)
            except Exception:
                pass
            logger.warning("Sylanne provider history projection failed", exc_info=True)
            return False

        logger.info(
            "Sylanne provider history projection: proactive=%d inner=%d orphan=%d",
            proactive_replaced,
            inner_hidden,
            orphan_hidden,
        )
        return True

    def _restore_provider_history(self, event: Any, run_context: Any) -> bool:
        """Restore only projection changes that survived AstrBot context processing."""

        txn = self._event_extra(event, self._PROVIDER_HISTORY_TXN_EXTRA, None)
        if not isinstance(txn, dict):
            return False
        setter = getattr(event, "set_extra", None)
        try:
            messages = getattr(run_context, "messages", None)
            request = self._event_extra(event, "provider_request", None)
            if not isinstance(messages, list) or request is not txn.get("request"):
                return False

            changed = False
            replacements = txn.get("replacements", ())
            replacement_by_id = {
                id(replacement): (replacement, original)
                for replacement, original in replacements
            }
            for index, message in enumerate(messages):
                pair = replacement_by_id.get(id(message))
                if pair is not None and message is pair[0]:
                    messages[index] = pair[1]
                    changed = True

            visible_originals = txn.get("visible_originals", ())
            original_messages = txn.get("original_messages", ())
            if not isinstance(visible_originals, tuple) or not isinstance(
                original_messages, tuple
            ):
                return changed

            # Hidden entries are restored only when the entire pre-agent visible
            # prefix survived by identity and in place. If ContextManager really
            # truncated/compressed anything, fail closed and do not resurrect it.
            if visible_originals and len(messages) >= len(visible_originals):
                prefix_intact = all(
                    messages[index] is original
                    for index, original in enumerate(visible_originals)
                )
                if prefix_intact and len(original_messages) > len(visible_originals):
                    suffix = list(messages[len(visible_originals):])
                    messages[:] = [*original_messages, *suffix]
                    changed = True
            return changed
        finally:
            if callable(setter):
                try:
                    setter(self._PROVIDER_HISTORY_TXN_EXTRA, None)
                except Exception:
                    pass

    def _parse_semantic_response(
        self,
        event: Any,
        *,
        original_text: str,
        sanitized_text: str,
    ) -> tuple[str, tuple[SemanticBeatPart, ...] | None]:
        """Scrub this turn's markers and return only a model-authored valid plan."""

        nonce = str(self._event_extra(event, SEMANTIC_BEAT_NONCE_EXTRA, "") or "")
        if not re.fullmatch(r"[0-9A-F]{6}", nonce):
            cleaned = scrub_semantic_marker_candidates(sanitized_text)
            fallback = semantic_parts_from_visible_line_breaks(cleaned)
            return cleaned, fallback if len(fallback) > 1 else None

        parsed = parse_semantic_completion(sanitized_text, nonce=nonce)
        cleaned = parsed.clean_text
        setter = getattr(event, "set_extra", None)
        if callable(setter):
            correlation = {
                "nonce": nonce,
                "raw_chars": len(original_text),
                "raw_sha256": self._text_digest(original_text),
                "clean_chars": len(cleaned),
                "clean_sha256": self._text_digest(cleaned),
            }
            try:
                setter(self._SEMANTIC_CORRELATION_EXTRA, correlation)
            except Exception:
                pass
        if parsed.accepted:
            return cleaned, parsed.parts
        # A malformed/unscoped hidden marker loses all control authority, but it
        # must not disable the model's still-visible paragraph boundaries.  This
        # fallback never guesses punctuation boundaries and never trusts marker
        # attributes; it only uses the scrubbed visible line structure.
        fallback = semantic_parts_from_visible_line_breaks(cleaned)
        return cleaned, fallback if len(fallback) > 1 else None

    def scrub_owned_semantic_markers(self, event: Any, text: str) -> str:
        """Final send-side guard: no raw semantic control marker may be visible."""

        nonce = str(self._event_extra(event, SEMANTIC_BEAT_NONCE_EXTRA, "") or "")
        if not re.fullmatch(r"[0-9A-F]{6}", nonce):
            return scrub_semantic_marker_candidates(str(text or ""))
        return parse_semantic_completion(str(text or ""), nonce=nonce).clean_text

    @staticmethod
    def _message_text_slots(message: Any) -> tuple[str, list[tuple[Any, str]]] | None:
        content = (
            message.get("content")
            if isinstance(message, dict)
            else getattr(message, "content", None)
        )
        if isinstance(content, str):
            return content, [(message, "content")]
        if not isinstance(content, list):
            return None
        slots: list[tuple[Any, str]] = []
        chunks: list[str] = []
        for part in content:
            if isinstance(part, dict):
                if isinstance(part.get("text"), str):
                    chunks.append(part["text"])
                    slots.append((part, "text"))
                continue
            part_text = getattr(part, "text", None)
            if isinstance(part_text, str):
                chunks.append(part_text)
                slots.append((part, "text"))
        return ("".join(chunks), slots) if slots else None

    @staticmethod
    def _replace_text_slots(slots: list[tuple[Any, str]], cleaned: str) -> bool:
        if not slots:
            return False
        try:
            target, attribute = slots[0]
            if isinstance(target, dict):
                target[attribute] = cleaned
            else:
                setattr(target, attribute, cleaned)
            for target, attribute in slots[1:]:
                if isinstance(target, dict):
                    target[attribute] = ""
                else:
                    setattr(target, attribute, "")
        except Exception:
            return False
        return True

    def on_agent_done(self, event: Any, run_context: Any, response: Any) -> bool:
        """Restore provider-only history and scrub the final assistant before save."""

        history_changed = self._restore_provider_history(event, run_context)
        correlation = self._event_extra(event, self._SEMANTIC_CORRELATION_EXTRA, None)
        if not isinstance(correlation, dict):
            return history_changed
        messages = getattr(run_context, "messages", None)
        if not isinstance(messages, list):
            return history_changed
        for message in reversed(messages):
            if str(getattr(message, "role", "") or "") != "assistant":
                continue
            extracted = self._message_text_slots(message)
            if extracted is None:
                return history_changed
            raw_text, slots = extracted
            if len(raw_text) != correlation.get("raw_chars"):
                return history_changed
            if self._text_digest(raw_text) != correlation.get("raw_sha256"):
                return history_changed
            cleaned = self.scrub_owned_semantic_markers(event, raw_text)
            cleaned = strip_draft_blocks(cleaned)
            cleaned = self._sanitize_response(cleaned)
            if len(cleaned) != correlation.get("clean_chars"):
                return history_changed
            if self._text_digest(cleaned) != correlation.get("clean_sha256"):
                return history_changed
            changed = self._replace_text_slots(slots, cleaned)
            if changed and response is not None:
                try:
                    response.completion_text = cleaned
                except Exception:
                    pass
            return history_changed or changed
        return history_changed

    @staticmethod
    def _rewrite_current_assistant(
        run_context: Any,
        transcript: str,
    ) -> bool:
        """Replace the current turn's assistant message with delivered truth."""

        messages = getattr(run_context, "messages", None)
        if not isinstance(messages, list):
            return False
        for index in range(len(messages) - 1, -1, -1):
            message = messages[index]
            role = _ctx_role(message)
            if role == "user":
                break
            if role != "assistant":
                continue
            if not transcript:
                messages.pop(index)
                return True
            extracted = LLMResponsePipeline._message_text_slots(message)
            if extracted is None:
                # Unknown provider message shape: try the common content field
                # once. If it is immutable, remove the draft fail-closed so an
                # unsent tail can never survive as history.
                try:
                    if isinstance(message, dict):
                        message["content"] = transcript
                    else:
                        setattr(message, "content", transcript)
                    return True
                except Exception:
                    messages.pop(index)
                return False
            _text, slots = extracted
            if LLMResponsePipeline._replace_text_slots(slots, transcript):
                return True
            messages.pop(index)
            return False
        return False

    async def settle_segmented_delivery_history(
        self,
        event: Any,
        run_context: Any,
        response: Any,
    ) -> str | None:
        """Wait for transport, then make delivered bubbles the sole history truth.

        ``None`` means this was not a realtime segmented turn.  A string (including
        the empty string) is the exact successfully delivered transcript.
        """

        turn = self._event_extra(event, self._DELIVERY_TURN_EXTRA, None)
        if not isinstance(turn, SegmentedDeliveryTurn):
            return None
        if self._event_extra(event, "_syl_realtime_takeover", False) is not True:
            return None
        if run_context is None:
            run_context = turn.run_context
        if response is None:
            response = turn.response
        if turn.history_settled:
            return turn.transcript

        task = turn.task
        if task is not None and not task.done():
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.warning(
                    "Sylanne segmented delivery failed before history commit: "
                    "session=%s error=%s",
                    turn.session_key,
                    type(exc).__name__,
                )
        elif task is not None:
            try:
                task.result()
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.warning(
                    "Sylanne segmented delivery failed before history commit: "
                    "session=%s error=%s",
                    turn.session_key,
                    type(exc).__name__,
                )

        transcript = turn.transcript
        changed = self._rewrite_current_assistant(run_context, transcript)
        if not changed:
            logger.warning(
                "Sylanne could not reconcile current assistant history: session=%s",
                turn.session_key,
            )
        elif transcript and response is not None:
            # Non-empty delivered text remains the framework save-gate and trace text.
            # For zero delivery keep the generated completion non-empty: AstrBot then
            # saves the current user message while run_context contains no assistant.
            try:
                response.completion_text = transcript
            except Exception:
                pass

        # The realtime path used to observe the full generated draft immediately.
        # Observe only after transport settles so plugin memory cannot learn unsent
        # tails such as "我想你" that the user never saw.
        if transcript and not turn.observed:
            try:
                await self._background_observe_response(
                    turn.session_key,
                    transcript,
                    skip_conv_sync=True,
                )
                turn.observed = True
            except Exception:
                # Body/memory observation is secondary. A failure here must never
                # roll history back from delivered truth to the provider draft.
                logger.warning(
                    "Sylanne delivered transcript observation failed: session=%s",
                    turn.session_key,
                    exc_info=True,
                )

        self._p._store.unfinished_replies.pop(turn.session_key, None)
        active_turns = getattr(self._p._store, "segmented_delivery_turns", None)
        if active_turns is not None and active_turns.get(turn.session_key) is turn:
            active_turns.pop(turn.session_key, None)
        turn.history_settled = True
        logger.info(
            "Sylanne delivery history committed: session=%s delivered=%d/%d chars=%d",
            turn.session_key,
            len(turn.delivered_parts),
            len(turn.planned_parts),
            len(transcript),
        )
        return transcript

    def bind_segmented_delivery_context(
        self,
        event: Any,
        run_context: Any,
        response: Any,
    ) -> bool:
        """Bind AstrBot history objects while final output ownership is unresolved."""

        turn = self._event_extra(event, self._DELIVERY_TURN_EXTRA, None)
        if not isinstance(turn, SegmentedDeliveryTurn):
            return False
        turn.run_context = run_context
        turn.response = response
        return turn.task is None and turn.status == "planned"

    def has_pending_segmented_candidate(self, event: Any) -> bool:
        """Whether this turn still awaits final-chain output arbitration."""

        turn = self._event_extra(event, self._DELIVERY_TURN_EXTRA, None)
        return (
            isinstance(turn, SegmentedDeliveryTurn)
            and turn.task is None
            and turn.status == "planned"
            and not turn.history_settled
        )

    def activate_segmented_delivery(self, event: Any) -> bool:
        """Commit text ownership and start transport after decorators finalize the chain."""

        turn = self._event_extra(event, self._DELIVERY_TURN_EXTRA, None)
        if not isinstance(turn, SegmentedDeliveryTurn):
            return False
        if turn.task is not None:
            return self._event_extra(event, "_syl_realtime_takeover", False) is True
        if turn.status != "planned":
            return False

        set_extra = getattr(event, "set_extra", None)
        if not callable(set_extra):
            return False
        parts = [dict(part) for part in turn.dispatch_parts]
        if not parts:
            return False
        try:
            reactive_delivery = self._claim_reactive_delivery(event, parts)
        except (AttributeError, TypeError, ValueError, DeliveryLeaseRejected):
            logger.warning(
                "Sylanne scoped reactive delivery lease rejected: session=%s",
                turn.session_key,
                exc_info=True,
            )
            return False

        task: asyncio.Task[Any] | None = None
        background_tasks: list[asyncio.Task[Any]] | None = None
        dispatch_ready = asyncio.Event()

        async def dispatch_after_commit() -> None:
            await dispatch_ready.wait()
            await self._dispatch_segmented_parts(
                turn.origin,
                parts,
                session_key=turn.session_key,
                delivery_turn=turn,
                reactive_delivery=reactive_delivery,
            )

        dispatch_coro = dispatch_after_commit()
        try:
            task = safe_ensure_future(
                dispatch_coro,
                name="dispatch_segmented_parts",
            )
            if task is None:
                raise RuntimeError("dispatch task creation returned no task")
            turn.task = task
            turn.status = "queued"
            background_tasks = ensure_background_tasks_list(self._p)
            background_tasks.append(task)
            task.add_done_callback(
                lambda completed: (
                    self._p._background_tasks.remove(completed)
                    if completed in self._p._background_tasks
                    else None
                )
            )
            self._p._store.segmented_tasks.set(turn.session_key, task)
            task.add_done_callback(
                lambda completed: self._on_segment_dispatch_done_maybe_afterthought(
                    completed,
                    turn.session_key,
                    turn.origin,
                    turn.expression_drive,
                    delivery_turn=turn,
                )
            )
            # Commit ownership only after every cancellation handle is durable.
            # The explicit gate also makes this safe under asyncio eager task
            # factories, where create_task() may run a coroutine immediately.
            set_extra("_syl_realtime_candidate", False)
            set_extra("_syl_realtime_takeover", True)
            if self._event_extra(event, "_syl_realtime_takeover", False) is not True:
                raise RuntimeError("takeover extra did not round-trip")
            dispatch_ready.set()
        except Exception:
            if task is not None:
                try:
                    task.cancel()
                except Exception:
                    pass
            else:
                try:
                    dispatch_coro.close()
                except Exception:
                    pass
            if (
                background_tasks is not None
                and task is not None
            ):
                try:
                    background_tasks.remove(task)
                except (ValueError, TypeError):
                    pass
            registry = getattr(self._p._store, "segmented_tasks", None)
            if registry is not None and task is not None:
                try:
                    if registry.get(turn.session_key) is task:
                        registry.pop(turn.session_key, None)
                except Exception:
                    pass
            turn.task = None
            turn.status = "failed"
            active_turns = getattr(
                self._p._store,
                "segmented_delivery_turns",
                None,
            )
            if active_turns is not None:
                try:
                    if active_turns.get(turn.session_key) is turn:
                        active_turns.pop(turn.session_key, None)
                except Exception:
                    pass
            for key, value in (
                ("_syl_realtime_takeover", False),
                ("_syl_realtime_candidate", False),
                (self._DELIVERY_TURN_EXTRA, None),
            ):
                try:
                    set_extra(key, value)
                except Exception:
                    pass
            logger.warning(
                "Sylanne realtime takeover abandoned (dispatch setup failed): "
                "session=%s",
                turn.session_key,
                exc_info=True,
            )
            return False

        logger.info(
            "Sylanne segmented reply activated: session=%s parts=%d",
            turn.session_key,
            len(parts),
        )
        return True

    async def delegate_segmented_candidate_to_framework(self, event: Any) -> bool:
        """Give a transformed non-text chain sole ownership without sending text."""

        turn = self._event_extra(event, self._DELIVERY_TURN_EXTRA, None)
        if not isinstance(turn, SegmentedDeliveryTurn):
            return False
        if turn.task is not None or turn.status != "planned":
            return False

        try:
            if turn.cleaned_text and not turn.observed:
                await self._background_observe_response(
                    turn.session_key,
                    turn.cleaned_text,
                    skip_conv_sync=True,
                )
                turn.observed = True
        except Exception:
            logger.warning(
                "Sylanne framework-owned transcript observation failed: session=%s",
                turn.session_key,
                exc_info=True,
            )
        finally:
            turn.status = "delegated"
            turn.history_settled = True
            self._p._store.unfinished_replies.pop(turn.session_key, None)
            active_turns = getattr(
                self._p._store,
                "segmented_delivery_turns",
                None,
            )
            if active_turns is not None and active_turns.get(turn.session_key) is turn:
                active_turns.pop(turn.session_key, None)
            set_extra = getattr(event, "set_extra", None)
            if callable(set_extra):
                try:
                    set_extra(self._DELIVERY_TURN_EXTRA, None)
                    set_extra("_syl_realtime_candidate", False)
                    set_extra("_syl_realtime_takeover", False)
                except Exception:
                    pass

        logger.info(
            "Sylanne segmented candidate delegated to final framework chain: session=%s",
            turn.session_key,
        )
        return True

    # ------------------------------------------------------------------
    # T1-02③ 身体驱动打字速度
    # ------------------------------------------------------------------
    @staticmethod
    def _body_signals(host: Any) -> tuple[float, float, float]:
        """读取躯体 energy/arousal/tension 三路信号（0.5/0.5/0.0 为中性默认值）。

        三路信号都已经在 host.kernel 上（response 分段规划这条路径已经拿着 host
        了，不新开管线）：
          - energy = 1 - host.kernel.body.mortality.exhaustion
          - arousal / tension 来自 host.kernel.computation.engine.observe()
            （8 维情感空间的既有输出，同一 engine 上 expression_drive() 已在用）。
        读取路径异常（缺字段/host 结构不符预期）时优雅退回中性默认值，绝不炸管线。
        供 _body_driven_cps（③ 打字速度）与 _think_delay（T1-01 读信时间）共用，
        避免同一 host 被两条独立逻辑各读一遍。
        """
        try:
            exhaustion = float(host.kernel.body.mortality.exhaustion)
            energy = max(0.0, min(1.0, 1.0 - exhaustion))
            emotion = host.kernel.computation.engine.observe()
            arousal = max(0.0, min(1.0, float(emotion.get("arousal", 0.5))))
            tension = max(0.0, min(1.0, float(emotion.get("tension", 0.0))))
        except (AttributeError, TypeError, ValueError, KeyError):
            return 0.5, 0.5, 0.0
        return energy, arousal, tension

    @staticmethod
    def _body_driven_cps(host: Any) -> float:
        """从躯体状态推导打字速度（chars/sec），替代原恒定 7.5。

        没精神（exhaustion 高 → energy 低）打字慢；情绪唤醒（arousal）高打字快；
        张力（tension）高只往下拖一点（紧张不会让人打字变快）。
        """
        energy, arousal, tension = LLMResponsePipeline._body_signals(host)
        cps = (
            _DEFAULT_CPS
            + (energy - 0.5) * _CPS_ENERGY_WEIGHT
            + (arousal - 0.5) * _CPS_AROUSAL_WEIGHT
            - tension * _CPS_TENSION_WEIGHT
        )
        return max(_CPS_MIN, min(_CPS_MAX, cps))

    # ------------------------------------------------------------------
    # T3-01 状态改变消息形状：把 v2core 派发调制器叠到身体基线上
    # ------------------------------------------------------------------
    @staticmethod
    def _apply_dispatch_modulators(
        default_cps: float,
        default_max_part: int,
        dispatch_mods: dict[str, float] | None,
    ) -> tuple[float, int, float]:
        """把 T3-01 派发调制器（cps_mult/max_part_chars_mult/extra_predelay_s）叠加到
        身体基线打字速度/分段长度上，返回 (调制后 cps, 调制后 max_part, 额外 predelay)。

        dispatch_mods 为 None/空 → 原样透传、extra_predelay=0.0（无行为/信号在场时零
        力学变化，card 要求的"no-behavior turns unchanged"）。调制器本身在 behavior.py /
        integration.py 已 clamp 到 [0.7,1.3]/[0,5]，这里只管应用，不重复 clamp 上限，
        但仍把最终 cps 拉回既有身体节奏合法区间 [_CPS_MIN, _CPS_MAX]（防合成后越出打字
        速度物理意义），max_part 拉回 >=8 的安全下限（防极端调制把消息剁成不可读碎片）。
        """
        if not dispatch_mods:
            return default_cps, default_max_part, 0.0
        cps_mult = float(dispatch_mods.get("cps_mult", 1.0) or 1.0)
        max_part_mult = float(dispatch_mods.get("max_part_chars_mult", 1.0) or 1.0)
        extra_predelay = float(dispatch_mods.get("extra_predelay_s", 0.0) or 0.0)
        cps = max(_CPS_MIN, min(_CPS_MAX, default_cps * cps_mult))
        max_part = max(8, int(round(default_max_part * max_part_mult)))
        return cps, max_part, extra_predelay

    # ------------------------------------------------------------------
    # T1-01 读信时间
    # ------------------------------------------------------------------
    @staticmethod
    def _think_delay(
        incoming_text: str,
        *,
        arousal: float,
        tension: float,
        energy: float,
        gap_seconds: float,
        rng: random.Random | None = None,
    ) -> float:
        """算"看到消息到开始打字"的启动延迟（首段专用，不是段内打字节奏）。

        长消息读得久、隔了很久重新搭话慢一点、没精神慢一点、紧张一点点拖慢启动——
        都增加延迟；情绪强度（这里用 arousal 当"turn 的情绪强度"代理——已经是本轮
        真实算出来的量，不是发明的 task 分类）越高回得越快（红队意见：沉重的话该更
        快回，不是更慢），减少延迟。刻意不用任何"任务分类"信号——没这东西。

        所有输入各自 clamp 到合理范围，最后再统一 clamp 到 [floor, ceiling]，
        任何权重组合都不会越出保守区间。
        """
        picker = rng if rng is not None else random
        visible_chars = sum(1 for ch in str(incoming_text or "") if not ch.isspace())
        read_time = min(_THINK_READ_CAP, visible_chars / _THINK_READ_CPS)

        intensity = max(0.0, min(1.0, arousal))
        intensity_adjust = -_THINK_INTENSITY_WEIGHT * intensity

        gap_ratio = max(0.0, min(1.0, gap_seconds / _THINK_GAP_SATURATE_SECONDS))
        gap_adjust = _THINK_GAP_WEIGHT * gap_ratio

        energy_adjust = _THINK_ENERGY_WEIGHT * (1.0 - max(0.0, min(1.0, energy)))
        tension_adjust = _THINK_TENSION_WEIGHT * max(0.0, min(1.0, tension))

        base = (
            _THINK_DELAY_FLOOR
            + read_time
            + intensity_adjust
            + gap_adjust
            + energy_adjust
            + tension_adjust
        )
        jitter = picker.uniform(_THINK_JITTER_MIN, _THINK_JITTER_MAX)
        delay = base * jitter
        return round(max(_THINK_DELAY_FLOOR, min(_THINK_DELAY_CEILING, delay)), 3)

    def _incoming_think_delay(self, event: Any, session_key: str) -> float:
        """T1-01 单一入口：reply 路径（首段延迟）与 stream 抢发路径共用同一计算，
        保证两条路径口径一致（card ③ 要求的"同一个choke point"）。"""
        host = self._p._host(session_key)
        energy, arousal, tension = self._body_signals(host)
        gap_seconds = 0.0
        try:
            prev_now = float(host.kernel.previous_event.get("now") or 0.0)
            if prev_now > 0.0:
                gap_seconds = max(0.0, time.time() - prev_now)
        except (AttributeError, TypeError, ValueError):
            gap_seconds = 0.0
        incoming_text = self._text(event)
        return self._think_delay(
            incoming_text,
            arousal=arousal,
            tension=tension,
            energy=energy,
            gap_seconds=gap_seconds,
        )

    # ------------------------------------------------------------------
    # T1-03 夜间温和版
    # ------------------------------------------------------------------
    def _night_rhythm_active(self, session_key: str, incoming_text: str) -> bool:
        """T1-03①②：本轮是否套用夜间温和版——总开关开 + 当前在免打扰时段 +
        incoming 文本未命中孤独/紧急豁免关键词。任一条件不满足 → False（原样）。

        免打扰时段判定复用 proactive_bridge._in_quiet_hours——它已经实现了"读
        大饼 schedule_settings，读不到则回退 1-7 点默认公式"的完整逻辑，这里
        不重新发明。大饼未安装/未启用桥接都不影响——_in_quiet_hours 本身不依赖
        bridge.available()，纯粹是"现在是不是夜里"的时间判断。
        """
        cfg = self._p._config or {}
        if not bool(cfg.get("sylanne_alpha_night_rhythm_enabled", False)):
            return False
        if is_night_fast_reply_exempt(incoming_text):
            return False
        bridge = getattr(self._p, "_proactive_bridge", None)
        if bridge is None:
            return False
        try:
            sid = bridge._resolve_origin(session_key)
            return bool(bridge._in_quiet_hours(sid))
        except Exception:
            return False

    @staticmethod
    def _apply_night_rhythm(
        cps: float,
        think_delay: float,
        *,
        active: bool,
        rng: random.Random | None = None,
    ) -> tuple[float, float]:
        """T1-03①：夜间温和版最终力学缩放——打字速度降一档、读信+启动延迟温和
        放大（硬顶 _NIGHT_THINK_DELAY_CAP，绝不滑向分钟级不理人）。

        作用在【T3-01 调制 + rhythm_learner 习得节奏 + T1-01 读信延迟】之后的
        最终值上（同 T3-01 extra_predelay 的分层原则：不与更早的层打架，只是
        最后再叠一层温和的夜间质感）。active=False（总开关关/非夜里/命中豁免）
        → 原样透传，零变化。
        """
        if not active:
            return cps, think_delay
        picker = rng if rng is not None else random
        night_cps = max(_CPS_MIN, cps + _NIGHT_CPS_DELTA)
        mult = picker.uniform(_NIGHT_THINK_DELAY_MULT_MIN, _NIGHT_THINK_DELAY_MULT_MAX)
        night_delay = min(_NIGHT_THINK_DELAY_CAP, think_delay * mult)
        return night_cps, night_delay

    # ------------------------------------------------------------------
    # 空回复兜底/静默判定（非拦截分支与拦截分支共用）
    # ------------------------------------------------------------------
    def _resolve_empty_reply(
        self, text: str, session_key: str, *, path: str = "unknown"
    ) -> str | None:
        """判定 completion_text 剥空后该静默还是兜底，两条分支（非拦截 ~365-432 /
        拦截分段发送 ~434-651）完全相同的 ~40 行逻辑此前各内联一份，2026-07-03
        fix/context-integrity 复审 MINOR 抽取合一（行为零变化，纯去重）。

        本层语义是"LLM 已被调用、本该有回复"，所以走到这里的空【永远是意外】
        （模型把答案塞进 thinking / 真没产出），绝不是人格主动装死（那由上游
        表达闸决定，不在这层）。故默认不 ghost：给一句 Sylanne 口吻兜底，
        走和正常回复一样的分段发送路径。区分成因仅供调试留痕（D8）。

        Args:
            text: 剥离 draft/thinking 块【之前】的原始 completion_text——只用来判断
                成因 reason（stripped_to_empty：thinking 包了答案；empty_completion：
                真空，常见于 tool 循环死锁）与日志留痕，不参与兜底文案本身。
            session_key: 会话标识，供兜底文案变体池按 warmth 分桶去重取用。
            path: 调用方分支标签（"intercept" / "non_intercept"），仅用于日志留痕。
                两分支合一成本方法之前，各自内联的日志天然带着"是哪条分支炸的静默"
                这个信息；合一后若不显式传，日志会退化成看不出走的是拦截还是非
                拦截分支，排障时无法区分——round-3 复审补回来（纯日志修复，不影响
                判定逻辑本身）。

        Returns:
            None —— 本轮应保持静默，调用方须把 response.completion_text 清空并 return。
            str —— 应该发送的兜底文案（自定义 sylanne_ghost_fallback_text 优先，否则
                走 EMPTY_REPLY_FALLBACK_VARIANTS 变体池，兜底常量 LAST_RESORT_FALLBACK_TEXT）。
        """
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
                f"Sylanne reply silent: session={session_key} path={path} "
                f"reason={_reason} raw_len={len(text)} "
                f"cfg_no_ghost={_no_ghost} has_custom={_has_custom_fallback}"
            )
            return None
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
            f"path={path} reason={_reason} raw_len={len(text)} "
            f"fallback_len={len(_fallback)}"
        )
        return _fallback

    # ------------------------------------------------------------------
    # Main response handler
    # ------------------------------------------------------------------
    @staticmethod
    def _has_pending_tool_calls(response: Any) -> bool:
        """Return whether this is an intermediate assistant tool-call response."""

        return any(
            bool(getattr(response, field, None))
            for field in ("tools_call_args", "tools_call_name", "tools_call_ids")
        )

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
        # 次要修复②：统一走 realtime_flags（与请求侧同一口径，见该函数 docstring）。
        realtime_enabled, intercept = realtime_flags(cfg)

        if response is None:
            return

        # 工具循环的 assistant 响应不是最终用户回复。AstrBot 会继续执行工具，
        # 再由工具本身或后续最终 assistant 响应决定交付。这里若提前分段直发，
        # 会把 TTS/send_message 等自发送工具的参数或前置文本先发一遍，随后工具
        # 再发一次，形成跨插件双交付。只做安全清理，绝不置接管旗标、调度分段
        # 或把中间步骤写入对话观测；判据只看框架公开的 tool-call 字段，不识别
        # 任何具体插件或工具名。
        if self._has_pending_tool_calls(response):
            text = normalize_completion_text(getattr(response, "completion_text", ""))
            cleaned = strip_draft_blocks(text)
            cleaned = self._sanitize_response(cleaned)
            cleaned, _semantic_parts = self._parse_semantic_response(
                event,
                original_text=text,
                sanitized_text=cleaned,
            )
            if cleaned != text:
                response.completion_text = cleaned
            logger.info(
                "Sylanne segmented delivery skipped for intermediate tool call: "
                "session=%s calls=%d",
                session_key,
                max(
                    len(getattr(response, "tools_call_args", None) or ()),
                    len(getattr(response, "tools_call_name", None) or ()),
                    len(getattr(response, "tools_call_ids", None) or ()),
                ),
            )
            return

        if not realtime_enabled or not intercept:
            # 未启用即时聊天拦截时，仅清理 thinking/draft 块 + 注入防御；
            # 仍须把 bot 回复写入 conversation_buffers（v2core 已 tick，勿再 observe_response）。
            if response is not None:
                text = normalize_completion_text(getattr(response, "completion_text", ""))
                cleaned = strip_draft_blocks(text)
                cleaned = self._sanitize_response(cleaned)
                cleaned, _semantic_parts = self._parse_semantic_response(
                    event,
                    original_text=text,
                    sanitized_text=cleaned,
                )
                # 注：此分支 completion_text 整段直发 AstrBot（不分段）。曾在此加超长截断
                # 兜底，经审查移除——单条长消息不是事故的 86 段轰炸，tagged thinking 已剥；
                # 截断会丢内容、还撞 deliverable 契约"一次给全"，是治 speculative 问题反引入
                # 真 bug。源头的 deliverable_mode（摘逃生舱工具）才是 thrash/泄露的真兜底。
                if not cleaned.strip():
                    # fix/context-integrity CONTRIB：此分支（非拦截，现网 realtime_intercept
                    # 默认关时的常态路径）此前 thinking-only 草稿剥空后直接吞掉——既不发送
                    # 也没有下面 intercept 分支那套 EMPTY_REPLY_FALLBACK 兜底，用户完全收不到
                    # 回复（"已读不回"假象）。这里复用同一份 reason 分治逻辑（_resolve_empty_reply，
                    # 两分支共用一份实现），保持两分支语义一致：stripped_to_empty（thinking
                    # 包了答案）默认兜底一句；empty_completion（completion_text 真空，常见于
                    # tool 循环死锁场景，AstrBot core 已自己塞过提示）继续保持静默——不是人格
                    # 装死，不该硬凑话。
                    _resolved = self._resolve_empty_reply(
                        text, session_key, path="non_intercept"
                    )
                    if _resolved is None:
                        response.completion_text = ""
                        self._v3_settle_empty(session_key, silent=True)
                        return
                    cleaned = _resolved
                    self._v3_settle_empty(session_key, silent=False)
                if cleaned != text:
                    response.completion_text = cleaned
                if cleaned.strip():
                    # fix/context-integrity round-2 BLOCKER：此分支 completion_text 非空
                    # 且事件未被 stop（本文件从未调用 event.stop_event()），AstrBot 框架
                    # 自己的 _save_to_history 会在 on_llm_response 钩子返回后，用
                    # agent_runner.run_context.messages 做一次【全量覆盖写】同一个
                    # conv_mgr.update_conversation(umo, cid, history=...)——框架才是这条
                    # 路径唯一且权威的历史写入者。我们自己的读-改-写（_append_bot_reply_buffer
                    # 内部 _sync_message_to_conv_mgr）若继续跟它并发，两种时序都出问题：
                    # 读在框架写之前→用陈旧快照覆盖掉框架刚写的 tool_calls/多模态/checkpoint
                    # 记录；读在框架写之后→重复 append 出连续两条 assistant 记录（Gemini
                    # turn 结构已知雷区）。故这里显式 skip_conv_sync=True，只留
                    # conversation_buffers/last_bot_texts 这些插件自身状态照常更新。
                    # round-3 纠偏：这个论证同样适用于下面拦截/分段发送分支——round-2
                    # 曾误以为那条分支是"插件唯一历史写入者"而不传 True，源码里那条
                    # 分支在候选登记前同样显式保留了 response.completion_text = cleaned
                    # （供 AstrBot 记录用），事件同样未被 stop，框架一样会保存，故那边
                    # 现在也已改成显式 skip_conv_sync=True（见
                    # _background_observe_response 调用点）。
                    obs_task = safe_ensure_future(
                        self._append_bot_reply_buffer(
                            session_key, cleaned, skip_conv_sync=True
                        ),
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

        # M4b（realtime 完整重做 Model-D，响应侧第二层防御）：本轮若正走框架
        # 原生流式发送（STREAMING_RESULT），彻底放弃接管。钩子触发时
        # event.get_result() 已经是这个类型——框架在 internal.py 里
        # event.set_result(...STREAMING_RESULT...set_async_stream(run_agent(...)))
        # 发生在 run_agent() 生成器真正被消费（从而触发 on_agent_done/
        # on_llm_response）之前。M4a（main.py on_message）已在请求侧尽量提前
        # 强制关流，这里兜第三方 runner / Live Mode 等绕过该时序假设的情况——
        # 不清 completion_text/result_chain、不分段调度，避免与框架自身流式
        # 发送（及请求侧 wrapped_send_streaming 的首句抢发）并行造成双发。
        try:
            _result = event.get_result() if hasattr(event, "get_result") else None
        except Exception:
            _result = None
        if _result is not None and getattr(
            getattr(_result, "result_content_type", None), "name", ""
        ) == "STREAMING_RESULT":
            logger.info(
                "Sylanne realtime takeover abandoned (streaming in flight): "
                f"session={session_key}"
            )
            return

        text = normalize_completion_text(getattr(response, "completion_text", ""))
        cleaned = strip_draft_blocks(text)
        cleaned = self._sanitize_response(cleaned)
        cleaned, semantic_parts = self._parse_semantic_response(
            event,
            original_text=text,
            sanitized_text=cleaned,
        )
        logger.info(
            f"Sylanne on_llm_response: len={len(cleaned)} session={session_key}"
        )

        # M1（issue26 同类根治，迁到 realtime 接管路径）：response.result_chain
        # 若含非 Plain 组件（Image/Record 等，如工具调用产出的图片/语音），
        # 彻底放弃接管——不清 completion_text/result_chain、不分段调度，让框架
        # 原样发送 + 保存，图片/语音保全（main.py::on_decorating_result 侧的
        # 既有 strip_draft_blocks 通用清理仍会对 Plain 段生效）。仅【纯 Plain】
        # 的 result_chain（或压根没有 result_chain，只用 _completion_text 的
        # provider，如 Anthropic）才继续走下面的接管分段。
        _result_chain = getattr(response, "result_chain", None)
        _rc_components = getattr(_result_chain, "chain", None) if _result_chain else None
        if _rc_components and any(
            _is_non_plain_component(seg) for seg in _rc_components
        ):
            logger.info(
                "Sylanne realtime takeover abandoned (result_chain 含非 Plain "
                f"组件/图片语音): session={session_key}"
            )
            return

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
            # fix/context-integrity MINOR：与上面非拦截分支完全相同的 ~40 行判定逻辑
            # 已抽成 _resolve_empty_reply 共用，此处不再内联第二份拷贝。
            _resolved = self._resolve_empty_reply(
                text, session_key, path="intercept"
            )
            if _resolved is None:
                response.completion_text = ""
                self._v3_settle_empty(session_key, silent=True)
                return
            cleaned = _resolved
            self._v3_settle_empty(session_key, silent=False)
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
        host = self._p._host(session_key)
        # T1-02③：默认打字速度从恒定 7.5 改成躯体状态驱动——没精神打字慢，
        # 情绪唤醒高打字快（"手抖打得快"）。host 在这里已经持有，复用而非新开管线。
        default_cps = self._body_driven_cps(host)
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
        # T3-01：状态改变消息形状——v2core 本轮算好的派发调制器（缺陷行为的
        # cps_mult/max_part_chars_mult/extra_predelay_s，合成表达风格 segment_bias/
        # pause_bias），作用在【身体基线】之上（rhythm_learner 之前），让"习得节奏"
        # 这层继续在调制后的基线上学习，两层不互相打架。v2core 关闭/未激活/取不到
        # → 全中性默认（1.0/1.0/0.0），零行为变化。
        dispatch_mods: dict[str, float] | None = None
        try:
            from sylanne_alpha.v2core.integration import consume_dispatch_modulators

            dispatch_mods = consume_dispatch_modulators(
                self._p,
                self._active_scope() or session_key,
            )
        except Exception:
            dispatch_mods = None
        default_cps, default_max_part, extra_predelay = self._apply_dispatch_modulators(
            default_cps, default_max_part, dispatch_mods
        )

        max_part_chars, cps = self._p._rhythm_learner.get_rhythm_params(
            session_key,
            default_max_part=default_max_part,
            default_cps=default_cps,
            expression_drive=expr_drive,
            recent_ignored_rate=recent_ignored,
        )
        # T1-01：首段延迟改用"读信+启动打字"时间，不再是裸 0（零思考时间瞬发）。
        # T3-01：逃避行为的 extra_predelay_s 叠加在 think_delay 之上（拖着不想碰）。
        think_delay = self._incoming_think_delay(event, session_key) + extra_predelay
        # T1-03①②：夜间温和版——免打扰时段打字略慢、读信+启动延迟温和放大（硬顶
        # 10s）；孤独/紧急消息（『睡不着』『在吗』等）整层豁免、原速回复。作为最后
        # 一层叠在 T3-01 调制 + rhythm_learner 习得节奏 + T1-01 读信延迟之上，不与
        # 更早的层打架。总开关关闭时 _night_rhythm_active 恒 False，零变化。
        night_active = self._night_rhythm_active(session_key, self._text(event))
        cps, think_delay = self._apply_night_rhythm(cps, think_delay, active=night_active)
        plan = realtime_plan(
            session_key,
            cleaned,
            max_part_chars=max_part_chars,
            chars_per_second=cps,
            first_delay=think_delay,
            semantic_parts=semantic_parts,
        )
        parts = plan.get("message_parts", [])

        if not parts:
            response.completion_text = cleaned
            return

        # M2/M3 修复（realtime 完整重做 Model-D，send/save 解耦核心）：
        #
        # 旧 hack 在此清空 result_chain/chain 来"压制框架发送"，同时把
        # completion_text 设为 cleaned"保留供历史记录"——但框架落库判据
        # （internal.py:_save_to_history:463-467）与发送判据（tool_loop_agent_
        # runner.py:803-814）读的是【同一个】response 对象：result_chain 档
        # provider（Gemini/OpenAI）清了 result_chain 后 completion_text getter
        # 会跟着塌缩成空（entities.py:434-437，result_chain 为空则读
        # _completion_text，而 setter 此前从未写过它），落库判据看到空
        # completion_text 直接不存——这是 M2 渐进失忆的根因。_completion_text
        # 档 provider（Anthropic）result_chain 本来就是 None，清空是空操作，
        # completion_text 仍非空，框架发送判据的 elif 分支照样用它建链发送——
        # 这是 M3 双发的根因（我们自己又后台分段发一遍）。
        #
        # 现在只设 completion_text，不再碰 result_chain/chain：
        # 1) 保存不受影响——run_context.messages 里的 assistant TextPart 在
        #    on_agent_done 钩子触发【之前】已用原始 completion_text 追加完毕
        #    （tool_loop_agent_runner.py:193-197 早于 :200），这里赋值不会
        #    重写已保存的历史内容；只用于让 :463-467 的落库判据读到非空值、
        #    确保这条 turn 被保存（treat 为一次真实 assistant 回复）。
        # 2) 发送抑制不再靠污染 llm_resp 字段，改在框架自己的装饰钩子
        #    on_decorating_result（main.py）里清空【规范化后的 event.result.chain】。
        #    "存"与"发"能解耦的真正原因是二者读【不同对象】，与 stage 先后无关：
        #    框架发送判据读 event.result.chain（RespondStage），而 _save_to_history
        #    读 llm_response.completion_text + run_context.messages（后者的 assistant
        #    段已在 tool_loop_agent_runner.py:197 提交），从不读 event.result.chain。
        #    故无论 decorate 与 save 谁先跑（真框架里 decorate 随 run_agent 消费先跑、
        #    save 在 run_agent 抽干后才跑，见 internal.py:396），清空 chain 都不影响
        #    落库内容。且与 provider 字段布局无关：result_chain 档和 _completion_text
        #    档到这一步都已统一坍缩成同一种 event.result.chain（各自经 tool_loop_
        #    agent_runner.py:803-814 的 if/elif 转成 MessageChain）。
        # 先保留非空 completion_text 作为 AstrBot 的 turn 保存门，但真正写进
        # run_context.messages 的 assistant 正文会在 on_agent_done 保存前屏障中，
        # 由成功送达账本改写为可见前缀。
        response.completion_text = cleaned
        set_extra = getattr(event, "set_extra", None)
        if not callable(set_extra):
            logger.warning(
                "Sylanne realtime takeover abandoned (event extras unavailable): "
                "session=%s",
                session_key,
            )
            return

        epochs = getattr(self._p._store, "conversation_input_epoch", None)
        current_epoch = int(epochs.get(session_key, 0) or 0) if epochs is not None else 0
        event_epoch = self._event_extra(event, "_syl_input_epoch", current_epoch)
        if not isinstance(event_epoch, int) or isinstance(event_epoch, bool):
            event_epoch = current_epoch
        turn = SegmentedDeliveryTurn(
            session_key=session_key,
            input_epoch=event_epoch,
            planned_parts=tuple(str(part.get("text", "")) for part in parts),
            origin=origin,
            dispatch_parts=tuple(dict(part) for part in parts),
            cleaned_text=cleaned,
            expression_drive=expr_drive,
        )
        active_turns = None
        try:
            set_extra(self._DELIVERY_TURN_EXTRA, turn)
            if self._event_extra(event, self._DELIVERY_TURN_EXTRA, None) is not turn:
                raise RuntimeError("delivery turn extra did not round-trip")
            active_turns = getattr(
                self._p._store, "segmented_delivery_turns", None
            )
            if active_turns is not None:
                active_turns.set(session_key, turn)
            set_extra("_syl_realtime_candidate", True)
            set_extra("_syl_realtime_takeover", False)
        except Exception:
            if active_turns is not None and active_turns.get(session_key) is turn:
                active_turns.pop(session_key, None)
            try:
                set_extra(self._DELIVERY_TURN_EXTRA, None)
                set_extra("_syl_realtime_candidate", False)
                set_extra("_syl_realtime_takeover", False)
            except Exception:
                pass
            logger.warning(
                "Sylanne realtime takeover abandoned (delivery ledger unavailable): "
                "session=%s",
                session_key,
                exc_info=True,
            )
            return

        logger.info(
            "Sylanne segmented reply planned: session=%s parts=%d "
            "(awaiting final-chain arbitration)",
            session_key,
            len(parts),
        )

        # 不在这里观测模型草稿。on_agent_done 只把 run_context/response 绑定到账本；
        # 最终装饰阶段先完成 TTS/图片等 chain 变换，再由
        # 单一仲裁点决定是启动文本 transport，还是把本轮完整交给框架非文本 chain。

    async def _append_bot_reply_buffer(
        self, session_key: str, text: str, *, skip_conv_sync: bool = False
    ) -> None:
        """仅写入对话缓冲 + ConvMgr 同步（不 tick / 不 observe_response）。

        Args:
            skip_conv_sync: fix/context-integrity round-2 BLOCKER 引入，round-3
                纠偏其错误前提。round-2 曾以为"拦截/分段发送分支"是插件的唯一
                历史写入者、默认 False 让它继续同步——这个前提被框架源码推翻：
                AstrBot 的 _save_to_history（on_llm_response 钩子返回后，用
                agent_runner.run_context.messages 对 conv_mgr.update_conversation
                做一次全量覆盖写）只看两个条件——completion_text 是否非空、事件是否
                被 event.stop_event() 终止——完全不区分调用方是拦截分支还是非拦截
                分支。凡是这两个条件成立的 turn，框架都是唯一且权威的历史写入者；
                插件自己的读-改-写（本方法内部对 _sync_message_to_conv_mgr 的调用）
                若在同一 turn 上继续跑，就是两个独立写入者并发写同一份历史，无论谁
                先谁后都会出问题（陈旧快照覆盖掉框架刚写的 tool_calls/多模态/
                checkpoint 记录，或者反过来把同一句话重复 append 成连续两条
                assistant 记录）。

                截至 round-3，本文件内【全部】两个调用点（非拦截分支 ~464 附近、
                拦截/分段发送分支的 _background_observe_response）传的都是 True——
                两条路径的 completion_text 在到达这里之前均保持非空且事件从未被
                stop，框架都会保存。参数默认值仍保留 False 且未整体删除
                skip_conv_sync=False 的分支代码，是为了给【真正会绕开
                on_llm_response 钩子、框架确定不会保存】的路径（例如未来某条完全
                独立于 LLM 响应事件之外的主动消息直发通道）留出口——只要该路径确实
                会调用本方法。目前代码库内没有这样的调用点（_fallback_direct_send /
                proactive_bridge.dispatch 等主动消息路径要么走 bridge.dispatch 触发
                外部插件自己的 LLM 调用、同样会经过本文件的 on_llm_response 钩子，
                要么根本不调用本方法，直接用 _dispatch_segmented_parts 发送，参见
                _fire_afterthought / main.py:_maybe_takeover_segments），所以目前
                conv_mgr 同步这条支路是死代码，只等一个真正符合条件的未来调用点。
                True 时 conversation_buffers/last_bot_texts 等插件自身状态仍照常
                更新，只跳过 conv_mgr 这一步。

                另需注意（已知残留问题，本轮不修）：框架 _save_to_history 落库的是
                【hook 前】的原始 completion_text，插件自己发给用户的是清理后
                （strip_draft_blocks/_sanitize_response）的 cleaned 文本——两者若不
                同签名不一致，是"发送内容≠保存内容"的独立缺陷，留给专门的历史补丁
                工作项处理，不在本卡范围内。
        """
        try:
            from sylanne_alpha.memory_system import ConversationBuffer

            buf = self._p._store.conversation_buffers.get_or_create(
                session_key, lambda: ConversationBuffer(session_key=session_key)
            )
            buf.append("bot", text)
            self._p._store.last_bot_texts.set(session_key, text[:120])
            self._p._schedule_buffer_persist(session_key)
            if not skip_conv_sync and self._p._has_conversation_manager():
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

    async def _background_observe_response(
        self, session_key: str, text: str, *, skip_conv_sync: bool = False
    ) -> None:
        """后台观测 bot 回复：写入对话缓冲、通知社交场域、更新计算栈。

        Args:
            skip_conv_sync: 透传给 _append_bot_reply_buffer——见该方法 docstring。
                拦截/分段发送分支（唯一调用本方法的调用点）自 round-3 起显式传
                True（框架会保存这条 turn）。
        """
        try:
            await self._append_bot_reply_buffer(
                session_key, text, skip_conv_sync=skip_conv_sync
            )
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
            # T1-01②：流式首句抢发此前直接和 LLM 流赛跑（零思考时间瞬发）。现在
            # 补齐同一份 think_delay，用【已经耗掉的流式生成时间】抵扣——LLM 生成
            # 本身就要花时间，只补剩余差额，不重复计时。
            think_delay = self._incoming_think_delay(event, session_key)
            last_user_at = self._p._store.last_user_message_time.get(
                session_key, time.time()
            )
            elapsed = max(0.0, time.time() - last_user_at)
            remaining_delay = max(0.0, think_delay - elapsed)
            task = safe_ensure_future(
                self._send_first_sentence(origin, first_sentence, delay=remaining_delay),
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

    async def _send_first_sentence(
        self, origin: str, text: str, delay: float = 0.0
    ) -> None:
        """通过 context.send_message 发送首句文本。

        T1-01②：delay>0 时先睡够剩余的 think_delay 差额，再发——不再和 LLM 流
        赛跑抢发首句。
        """
        if delay > 0:
            await asyncio.sleep(delay)
        context = self._p.context
        if hasattr(context, "send_message"):
            message = self._astrbot_message(text)
            await context.send_message(origin, message)

    # ------------------------------------------------------------------
    # Segmented dispatch
    # ------------------------------------------------------------------
    async def _dispatch_scoped_reactive_parts(
        self,
        parts: list[dict[str, Any]],
        *,
        session_key: str,
        settle_v3: bool,
        delivery_turn: SegmentedDeliveryTurn | None,
        coordinator: ReactiveDeliveryCoordinator,
        claim: DeliveryClaim,
    ) -> None:
        """Deliver one scoped reply through its sealed original event only."""

        total = len(parts)
        v3_token = self._v3_pending_token(session_key) if settle_v3 else None

        def settle(*, succeeded: bool) -> None:
            if not settle_v3:
                return
            self._v3_settle_segments(
                session_key,
                total,
                succeeded=succeeded,
                token=v3_token,
            )

        async def before_send(index: int, text: str) -> bool:
            if index >= len(parts) or str(parts[index].get("text", "")) != text:
                return False
            if delivery_turn is None:
                delay = float(parts[index].get("delay_before_seconds", 0))
                if delay > 0:
                    await asyncio.sleep(delay)
                return True

            epochs = getattr(self._p._store, "conversation_input_epoch", None)
            current_epoch = (
                int(epochs.get(session_key, 0) or 0)
                if epochs is not None
                else delivery_turn.input_epoch
            )
            if delivery_turn.should_stop(current_epoch):
                return False
            delay = float(parts[index].get("delay_before_seconds", 0))
            if delay > 0 and not await delivery_turn.wait_delay(delay):
                return False
            current_epoch = (
                int(epochs.get(session_key, 0) or 0)
                if epochs is not None
                else delivery_turn.input_epoch
            )
            return not delivery_turn.should_stop(current_epoch)

        def copy_confirmed_parts() -> None:
            if delivery_turn is not None:
                delivery_turn.delivered_parts[:] = list(coordinator.turn.confirmed_parts)

        try:
            snapshot = await coordinator.deliver(
                event=claim.event,
                claim=claim,
                before_send=before_send,
            )
        except asyncio.CancelledError:
            copy_confirmed_parts()
            if delivery_turn is not None:
                delivery_turn.status = "cancelled"
            settle(succeeded=False)
            raise
        except BaseException:
            copy_confirmed_parts()
            if delivery_turn is not None:
                delivery_turn.status = coordinator.state.value
            settle(succeeded=False)
            raise

        copy_confirmed_parts()
        if snapshot.state is DeliveryState.SENT_CONFIRMED:
            if delivery_turn is not None:
                delivery_turn.status = "completed"
            settle(succeeded=True)
            return

        if delivery_turn is not None:
            delivery_turn.status = snapshot.state.value
        settle(succeeded=False)
        logger.info(
            "Sylanne scoped reactive dispatch stopped: session=%s state=%s sent=%d/%d",
            session_key,
            snapshot.state.value,
            snapshot.confirmed_parts,
            total,
        )

    async def _dispatch_segmented_parts(
        self,
        origin: str,
        parts: list[dict[str, Any]],
        session_key: str = "",
        *,
        settle_v3: bool = True,
        delivery_turn: SegmentedDeliveryTurn | None = None,
        reactive_delivery: tuple[ReactiveDeliveryCoordinator, DeliveryClaim] | None = None,
    ) -> None:
        """逐段发送分段回复，每段之间按计划延迟。

        Args:
            origin: 消息发送目标（unified_msg_origin）。
            parts: 分段列表，每段包含 text 和 delay_before_seconds。
            session_key: 会话标识，发送完成后清除 unfinished 标记。
            settle_v3: 这次投递是否算【本轮的】v3 终端证据。默认 True（正常回复）。
                补刀/改口（_fire_afterthought）必须传 False：它复用同一个 session_key，
                却在原轮结束后 20-180s 才发，那时 _pending[session_key] 要么已被本轮
                结算掉、要么已经装着【下一轮】——按 True 走会把下一轮的 handle 认领成
                本次补刀的 SPEAK（带错的 part_count），还把下一轮真正的终端证据挤掉。
                v3 纯观察，对 v2 行为没有任何影响。
        """
        if reactive_delivery is not None:
            coordinator, claim = reactive_delivery
            await self._dispatch_scoped_reactive_parts(
                parts,
                session_key=session_key,
                settle_v3=settle_v3,
                delivery_turn=delivery_turn,
                coordinator=coordinator,
                claim=claim,
            )
            return

        total = len(parts)

        def record_remaining(start_index: int) -> None:
            if not session_key or delivery_turn is not None:
                return
            remaining_text = "".join(
                str(part.get("text", "")) for part in parts[start_index:]
            )
            if remaining_text:
                self._p._store.unfinished_replies.set(session_key, remaining_text)
            else:
                self._p._store.unfinished_replies.pop(session_key, None)

        # Legacy direct callers retain their previous unfinished-reply behavior.
        # Realtime takeover turns use delivery_turn instead: unsent text is a
        # private draft and must never become conversational history.
        record_remaining(0)
        context = self._p.context
        if not hasattr(context, "send_message"):
            if delivery_turn is not None:
                delivery_turn.status = "failed"
            return
        # 栅栏令牌：在【任何 await 之前】同步取本轮的令牌。这条协程可能要跑好几秒
        # （段间 sleep），期间同一 session_key 上可能已经换了下一轮；结算时带着这枚
        # 令牌，v3 就能认出"我要结的那轮已经不在了"而放手，不会错结下一轮。
        v3_token = self._v3_pending_token(session_key) if settle_v3 else None
        sent_count = 0
        interrupted = False
        stop_epoch = delivery_turn.input_epoch if delivery_turn is not None else 0
        try:
            for idx, part in enumerate(parts, 1):
                if delivery_turn is not None:
                    epochs = getattr(
                        self._p._store, "conversation_input_epoch", None
                    )
                    current_epoch = (
                        int(epochs.get(session_key, 0) or 0)
                        if epochs is not None
                        else delivery_turn.input_epoch
                    )
                    stop_epoch = current_epoch
                    if delivery_turn.should_stop(current_epoch):
                        interrupted = True
                        break
                delay = float(part.get("delay_before_seconds", 0))
                if delay > 0:
                    if delivery_turn is None:
                        await asyncio.sleep(delay)
                    elif not await delivery_turn.wait_delay(delay):
                        interrupted = True
                        break
                if delivery_turn is not None:
                    epochs = getattr(
                        self._p._store, "conversation_input_epoch", None
                    )
                    current_epoch = (
                        int(epochs.get(session_key, 0) or 0)
                        if epochs is not None
                        else delivery_turn.input_epoch
                    )
                    stop_epoch = current_epoch
                    if delivery_turn.should_stop(current_epoch):
                        interrupted = True
                        break
                text = str(part.get("text", ""))
                if not text:
                    sent_count = idx
                    record_remaining(sent_count)
                    continue
                logger.info("Sylanne segmented reply part %d/%d", idx, total)
                message = self._astrbot_message(text)
                await context.send_message(origin, message)
                sent_count = idx
                if delivery_turn is not None:
                    delivery_turn.mark_delivered(text)
                # 只有明确收到 send_message 成功返回，才从 unfinished 扣掉该段。
                record_remaining(sent_count)
        except asyncio.CancelledError:
            # Legacy callers keep the old remainder contract. Realtime ledger
            # callers preserve only the successful prefix; cancellation never
            # promotes an unsent tail into the next prompt.
            record_remaining(sent_count)
            if delivery_turn is not None:
                delivery_turn.status = "cancelled"
                self._p._store.unfinished_replies.pop(session_key, None)
            logger.info(
                "Sylanne segmented dispatch cancelled: session=%s sent=%d/%d",
                session_key, sent_count, total,
            )
            # v3 shadow：段间取消 = 投递未完成 → UNKNOWN，绝不结算 SPEAK（design 14.2）。
            if settle_v3:
                self._v3_settle_segments(session_key, total, succeeded=False, token=v3_token)
            raise
        except BaseException:
            # 任意一段 send 失败（首段/次段皆然）：v2 行为完全不变——原样重抛，交给
            # task.exception()/上游。这里只补一条 v3 终端证据：部分投递 → UNKNOWN。
            record_remaining(sent_count)
            if delivery_turn is not None:
                delivery_turn.status = "failed"
            if settle_v3:
                self._v3_settle_segments(session_key, total, succeeded=False, token=v3_token)
            raise
        if interrupted:
            if delivery_turn is not None:
                delivery_turn.status = "interrupted"
                self._p._store.unfinished_replies.pop(session_key, None)
            if settle_v3:
                self._v3_settle_segments(
                    session_key, total, succeeded=False, token=v3_token
                )
            logger.info(
                "Sylanne segmented dispatch interrupted: "
                "session=%s sent=%d/%d turn_epoch=%d current_epoch=%d "
                "explicit_interrupt=%s",
                session_key,
                sent_count,
                total,
                delivery_turn.input_epoch if delivery_turn is not None else 0,
                stop_epoch,
                bool(
                    delivery_turn is not None
                    and delivery_turn.interrupt_requested
                ),
            )
            return
        # 所有段发送成功——清除未完成标记
        if session_key:
            self._p._store.unfinished_replies.pop(session_key, None)
        if delivery_turn is not None:
            delivery_turn.status = "completed"
        # v3 shadow：唯一能证明 SPEAK 的地方——每一段都过了 send_message，无取消无异常。
        if settle_v3:
            self._v3_settle_segments(session_key, total, succeeded=True, token=v3_token)

    def _v3_pending_token(self, session_key: str) -> int | None:
        """取本轮的 v3 栅栏令牌（默认关 / 没捕获过时是 None）。"""

        facade = getattr(self._p, "_v3_shadow", None)
        getter = getattr(facade, "pending_token", None)
        if not callable(getter) or not session_key:
            return None
        try:
            return getter(session_key)
        except Exception:  # noqa: BLE001 - 取不到令牌就退化成"结算当前那轮"
            return None

    def _v3_settle_segments(
        self, session_key: str, total: int, *, succeeded: bool, token: int | None = None
    ) -> None:
        """把分段投递的终端证据交给 v3 shadow（默认关时是空操作）。

        design 14.2：只有【完整结构化投递】才可以结算一次 SPEAK；部分投递、失败段、
        取消一律 UNKNOWN。facade 内部保证不抛，故这里没有 try——它绝不能改 v2 行为。
        """

        facade = getattr(self._p, "_v3_shadow", None)
        if facade is None or not session_key or total < 1:
            return
        facade.settle(
            session_key=session_key,
            route_kind="SEGMENTED_TEXT",
            reply_kind="SPEAK",
            part_count=total,
            all_segments_succeeded=succeeded,
            token=token,
        )

    def _v3_settle_empty(self, session_key: str, *, silent: bool) -> None:
        """空草稿分治的 v3 终端证据（默认关时是空操作）。

        - silent=True：投递管线判定这轮不说话 → SILENT 路由 → HOLD。
        - silent=False：兜底一句 → FALLBACK 路由 → 恒 UNKNOWN（兜底文案不是她的决定）。
          它先于下方分段发送结算，故这轮不会再被结算成 SPEAK——这正是"FALLBACK 在有效
          候选之后仍是 UNKNOWN"的语义。
        """

        facade = getattr(self._p, "_v3_shadow", None)
        if facade is None or not session_key:
            return
        if silent:
            facade.settle(session_key=session_key, route_kind="SILENT", reply_kind="SILENT")
        else:
            facade.settle(
                session_key=session_key,
                route_kind="FALLBACK",
                reply_kind="FALLBACK",
                part_count=1,
            )

    # ------------------------------------------------------------------
    # T2-02 补刀与改口
    # ------------------------------------------------------------------
    @staticmethod
    def _afterthought_probability(expression_drive: float) -> float:
        """表达驱动力 → 触发概率，线性映射后 clamp 到 [floor, ceil]。"""
        drive = max(0.0, min(1.0, expression_drive))
        prob = _AFTERTHOUGHT_PROB_FLOOR + drive * _AFTERTHOUGHT_PROB_DRIVE_WEIGHT
        return max(_AFTERTHOUGHT_PROB_FLOOR, min(_AFTERTHOUGHT_PROB_CEIL, prob))

    @staticmethod
    def _afterthought_roll(probability: float, rng: random.Random | None = None) -> bool:
        picker = rng if rng is not None else random
        return picker.random() < probability

    @staticmethod
    def _afterthought_delay(rng: random.Random | None = None) -> float:
        picker = rng if rng is not None else random
        return picker.uniform(_AFTERTHOUGHT_DELAY_MIN, _AFTERTHOUGHT_DELAY_MAX)

    @staticmethod
    def _afterthought_refractory_ok(exchange_count: int, last_fired_at: int) -> bool:
        """至少隔 _AFTERTHOUGHT_REFRACTORY_EXCHANGES 轮"发完一段完整回复"才放行。"""
        return (exchange_count - last_fired_at) >= _AFTERTHOUGHT_REFRACTORY_EXCHANGES

    def _afterthought_state(self, session_key: str) -> dict[str, int]:
        return self._p._store.afterthought_state.get_or_create(
            session_key, lambda: {"exchange_count": 0, "last_fired_at": -1_000_000}
        )

    def _on_segment_dispatch_done_maybe_afterthought(
        self,
        task: Any,
        session_key: str,
        origin: str,
        expression_drive: float,
        *,
        rng: random.Random | None = None,
        delivery_turn: SegmentedDeliveryTurn | None = None,
    ) -> None:
        """T2-02①：一段 SPEAK 分段回复正常发完（未取消/未炸）后的挂钩。

        config 关闭 → 立即 return，不分配任何 refractory 状态、不骰子（"config off =
        零行为"）。被打断（task.cancelled()）或分段发送本身炸了（task.exception()
        非空）都不算"正常发完"，不触发。
        """
        try:
            if task.cancelled():
                return
            if task.exception() is not None:
                return
        except asyncio.CancelledError:
            return
        if delivery_turn is not None and delivery_turn.status != "completed":
            return
        cfg = self._p._config or {}
        if not bool(cfg.get("sylanne_alpha_afterthought_enabled")):
            return
        state = self._afterthought_state(session_key)
        state["exchange_count"] = int(state.get("exchange_count", 0)) + 1
        if not self._afterthought_refractory_ok(
            state["exchange_count"], int(state.get("last_fired_at", -1_000_000))
        ):
            return
        probability = self._afterthought_probability(expression_drive)
        if not self._afterthought_roll(probability, rng=rng):
            return
        # T2-02③ 继续用 last_user_message_time 作为补刀的独立取消锚。实时分段
        # 现在另有 conversation_input_epoch + delivery ledger 的锁外中断协议；
        # 补刀则是一个已经结算后的新发送任务，用消息时间戳判定更直接，也兼容
        # 未走实时分段的普通轮。醒来后时间前进即说明用户插了话，取消补刀。
        anchor_last_user_at = self._p._store.last_user_message_time.get(
            session_key, 0.0
        )
        delay = self._afterthought_delay(rng=rng)
        afterthought_task = safe_ensure_future(
            self._fire_afterthought(session_key, origin, anchor_last_user_at, delay),
            name="afterthought",
        )
        ensure_background_tasks_list(self._p).append(afterthought_task)
        # 双保险：也挂到 segmented_tasks——llm_request_pipeline 收到下一条真实用户
        # 请求时会自动 cancel 该 slot 里过期的分段任务（既有机制，:1126 附近），
        # 补刀的睡眠/发送因此也能被这条路径兜住，不必只靠时间戳判定单点防线。
        self._p._store.segmented_tasks.set(session_key, afterthought_task)
        afterthought_task.add_done_callback(
            lambda t: (
                self._p._background_tasks.remove(t)
                if t in self._p._background_tasks
                else None
            )
        )

    def _afterthought_content_from_remnants(self, session_key: str) -> str:
        """T2-02②(a)：零额外 LLM 开销的内容来源——现成的 unfinished_replies /
        未消费的中断断点残留（都是"这轮本来还有话没说完"的真实素材）。"""
        remnant = self._p._store.unfinished_replies.get(session_key)
        if remnant and str(remnant).strip():
            text = str(remnant).strip()
            self._p._store.unfinished_replies.pop(session_key, None)
            return text
        bps = getattr(self._p, "_interrupted_reply_breakpoints", {})
        entries = bps.get(session_key) or []
        for entry in reversed(entries):
            if entry.get("consumed"):
                continue
            unsent = entry.get("unsent_parts") or []
            text = "".join(str(p) for p in unsent).strip()
            if text:
                entry["consumed"] = True
                entry["consumed_reason"] = "afterthought"
                return text
        return ""

    async def _afterthought_llm_content(self, session_key: str) -> str:
        """T2-02②(b)：没有现成残留时，走一次极短 prompt 的 cheap LLM 调用
        （复用 assessor provider 链路，不是新开一条昂贵通路）。"""
        last_reply = str(self._p._store.last_bot_texts.get(session_key, "") or "")
        if not last_reply:
            return ""
        prompt = (
            "你是苏思澜，刚才对男友说了这句话：\n"
            f"「{last_reply}」\n"
            "现在突然想再补一条很短的追加或更正，用你平时的口吻，只要一句话，"
            "不用称呼开头，不用解释，不要加引号。"
        )
        caller = getattr(self._p, "_assessor_llm_call", None)
        if not callable(caller):
            return ""
        try:
            raw = await caller(prompt)
        except Exception as e:
            logger.debug(f"Sylanne afterthought llm call skipped: {e}")
            return ""
        text = normalize_completion_text(raw)
        text = strip_draft_blocks(text)
        text = self._sanitize_response(text)
        return text.strip()

    def _afterthought_interrupted(
        self, session_key: str, anchor_last_user_at: float
    ) -> bool:
        """T2-02③：用户在锚定时刻之后是否又发了消息（last_user_message_time 前进）。"""
        current = self._p._store.last_user_message_time.get(session_key, 0.0) or 0.0
        return current > anchor_last_user_at

    async def _fire_afterthought(
        self, session_key: str, origin: str, anchor_last_user_at: float, delay: float
    ) -> None:
        """T2-02①②③④：睡够随机延迟后，若用户没插话就补发一条很短的补刀/改口，
        走和正常回复一样的分段发送路径（④，让 wave-1 的打字节奏照常生效）。"""
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            raise
        if self._afterthought_interrupted(session_key, anchor_last_user_at):
            return
        cfg = self._p._config or {}
        if not bool(cfg.get("sylanne_alpha_afterthought_enabled")):
            return
        content = self._afterthought_content_from_remnants(session_key)
        if not content:
            content = await self._afterthought_llm_content(session_key)
        if not content:
            return
        # LLM 调用可能耗了几秒——发之前再核一次用户没插话
        if self._afterthought_interrupted(session_key, anchor_last_user_at):
            return
        host = self._p._host(session_key)
        cps = self._body_driven_cps(host)
        max_part = int(cfg.get("realtime_chat_max_part_chars", 48))
        plan = realtime_plan(
            session_key,
            content,
            max_part_chars=max_part,
            chars_per_second=cps,
            first_delay=_AFTERTHOUGHT_FIRST_DELAY,
        )
        parts = plan.get("message_parts", [])
        if not parts:
            return
        logger.info(
            f"Sylanne afterthought queued: session={session_key} parts={len(parts)}"
        )
        # settle_v3=False：补刀复用同一 session_key 但发生在本轮结算之后，绝不能
        # 认领这个键上的（下一轮的）待结算捕获。见 _dispatch_segmented_parts 文档。
        await self._dispatch_segmented_parts(
            origin, parts, session_key=session_key, settle_v3=False
        )
        state = self._afterthought_state(session_key)
        state["last_fired_at"] = state.get("exchange_count", 0)

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

    def _add_transient_context(
        self,
        request: Any,
        channel: str,
        text: str,
        source: str,
        priority: int,
    ) -> bool:
        add = getattr(self._p, "_add_transient_context", None)
        if not callable(add):
            return False
        try:
            return bool(add(request, channel, text, source, priority))
        except Exception:
            return False

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

        多轮渐进裁剪：先裁 extra_user_content_parts，再裁 messages。
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
    # State injection budget
    # ------------------------------------------------------------------
    def _state_injection_budget_for_request(
        self, session_key: str, request: Any
    ) -> Any:
        """为请求创建通用状态注入预算对象。"""
        # Access _StateInjectionBudget from the plugin's module to avoid circular import
        import sys

        _mod = sys.modules.get(type(self._p).__module__)
        _StateInjectionBudget = getattr(_mod, "_StateInjectionBudget", None)
        if _StateInjectionBudget is None:
            from main import _StateInjectionBudget

        budget = _StateInjectionBudget(session_key=session_key)
        cfg = self._p.config or {}
        budget.max_added_chars = int(cfg.get("state_injection_max_added_chars", 2400))
        budget.max_parts = int(cfg.get("state_injection_max_parts", 8))
        return budget

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
