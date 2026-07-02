"""v2core Renderer 出口契约（设计 §4）—— 内部 BeatContext → 对外 Reply 的唯一翻译层。

旧架构三类事故同一道根因：内部结构直接漏成对外消息（diagnostics JSON 当正文、产出为空
静默清链、MessageChain 被 str() 当文本）。本模块把这道边界焊死：

- DefaultRenderer 是唯一产出 Reply 的地方，total function（永不抛、永不 None）。
- Projector 注册表是白名单：只有显式注册了 Projector 的 Intent.source 才能投影成文本
  （堵 #1 内部对象泄漏 / #4 裸 repr）；没注册的意图一律不出现。
- HostSink 是【唯一】import astrbot MessageChain/Plain 的地方，把 Reply 落到宿主事件。

两种渲染模式（render 的 draft 参数区分）：
- draft 模式（draft 非 None）：宿主 LLM 已出草稿，Sylanne 在其上【调味】。**D8 反转语义
  （2026-06-12）：draft 模式也可 SILENT**——当有【显式】静默决策（scratch['silent'] /
  Intent silent flag，如 IgnitionArbiter 的 hold）时，被问也能"装死"，唯一要求显式决策 +
  reason + 强制日志；无显式静默决策则维持"被问必答"（剥壳后非空即作 body 投影单元）。
- compose 模式（draft=None）：Sylanne 自主组织发言，同样可 SILENT（显式表达策略/人格驱动
  的"装死"，非无声故障），SILENT 必带 reason 以便可观测（D8 强制日志）。

铁律对齐：
- 铁律2 无内部安全闸：本层不 clamp 任何情感/强度，只做结构→文本的投影与兜底。
- P11 零-LLM：StateProjector._narrate 是纯模板，热路径绝不调 LLM。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol, runtime_checkable

from sylanne_alpha.message_dispatch import strip_draft_blocks
from sylanne_alpha.v2core.contracts import (
    BeatContext,
    BodySnapshot,
    Intent,
    Reply,
    ReplyKind,
)
from sylanne_alpha.variant_pool import (
    EMPTY_REPLY_FALLBACK_VARIANTS,
    LAST_RESORT_FALLBACK_TEXT as _DEFAULT_FALLBACK_TEXT,
    choose as _pool_choose,
    warmth_bucket as _warmth_bucket,
)

logger = logging.getLogger("astrbot_plugin_sylanne")

# 渲染兜底文案：输入为空/异常时给一句安全的 Sylanne 口吻回复，绝不静默吞掉（堵 #2）。
# 常量本体挪进 variant_pool.LAST_RESORT_FALLBACK_TEXT，与 llm_response_pipeline.py 共用
# 同一份，不再各自内联字面量（MINOR 修复，2026-07-02）。


# ===========================================================================
# ProjectionUnit —— 投影的最小产物（纯字符串分段，内部对象在类型层进不来）
# ===========================================================================

@dataclass(slots=True)
class ProjectionUnit:
    """一个投影单元：Projector 把 Intent 翻译成的【纯文本】片段。

    text 限定为 str（构造即校验）→ 内部对象（BodySnapshot/MessageChain/dict）无法混进
    对外正文。priority 决定多单元拼装顺序（高者在前）；role 是来源标签（body/state/...）
    仅供可观测与排序参考，不进正文。segmentable 标记该片段可否再分段发送（Tier1 仅透传）。
    """

    text: str
    segmentable: bool = True
    priority: float = 0.5
    role: str = "flavor"

    def __post_init__(self) -> None:
        # #4 不变量：正文只能是 str。非 str 一律拒绝（绝不 repr/json.dumps 内部对象）。
        if not isinstance(self.text, str):
            raise TypeError(
                f"ProjectionUnit.text 必须是 str，拿到 {type(self.text).__name__}"
            )


# ===========================================================================
# Projector 协议 —— 把某 source 的 Intent 翻译成文本（白名单注册，缺省不投影）
# ===========================================================================

@runtime_checkable
class Projector(Protocol):
    """单一 source 的意图投影器。注册到 DefaultRenderer 才生效（白名单，堵 #1/#4）。

    纪律：project 返回的 text **只能是 str** —— 绝不允许把内部对象 repr / json.dumps
    后塞进正文。需要把结构化状态展示给用户的，也走 Projector 投影成措辞，而非原样 dump。
    """

    source: str  # 认领哪个 Intent.source

    def project(self, intent: Intent, ctx: BeatContext) -> str | None:
        """把一条匹配 source 的意图翻译成正文片段；不想出声时返回 None / 空串。"""
        ...


# ===========================================================================
# StateProjector —— 状态查询投影（纯模板把 body 套 Sylanne 口吻，P11 禁调 LLM）
# ===========================================================================
# 现状纠偏（2026-07-02，红队复核发现 T4-02 提交信息误判）：StateProjector.source ==
# "state_query"，但目前【没有任何生产代码路径】会产出 source="state_query" 的 Intent——
# 各 capability（mentalize/appraisal/somatic_marker/recall/expression/outreach/
# ignition/reconsolidation）都不会走这个 source，DefaultRenderer._collect 因此永远
# 匹配不到这个 Projector。它只在单测里被直接调用（test_state_projector 等），在真实
# 聊天路径上是【全域休眠】，并非 T4-02 卡片说的"WebUI-only"分类，也不是"已确认走
# chat 的 state_query intent"（85e83c3 commit message 这句话是误判，已在此更正）。
# 变体化处理本身无害（纯模板、已测），按卡片"若判定为休眠则轻量处理/注明理由"的兜底
# 条款保留原样，作为未来若真接上 state_query intent 生产方时的现成收尾，不需要现在返工。

# T4-02③：每档 2-3 个变体，语气要真的不同（软糯/简短/念叨），不是同义词替换。
# StateProjector 实例随 DefaultRenderer 按 session 建（见 integration.py 的 per-session
# runtime cache），故用实例级 dedup state 就天然是"本会话最近选过"的语义。
_MOOD_VARIANTS: dict[str, list[str]] = {
    "hot": [
        "心里暖烘烘的，挺想凑近你说话",
        "现在满脑子都是你，讲话都带笑",
        "心口热乎乎的，想多黏你一会儿",
    ],
    "mild_warm": [
        "状态还算松快",
        "心情还行，绷着的地方松了点",
        "今天不算差，接得住你",
    ],
    "very_cold": [
        "有点凉，话不太想往外冒",
        "心里空落落的，懒得多说",
        "冷得很，别指望我多热情",
    ],
    "mild_cold": [
        "情绪稍微沉了点",
        "心里压着点东西，没那么爽利",
        "有点闷，不算好状态",
    ],
    "neutral": [
        "心里平平的",
        "没什么波动，就那样",
        "心情算中规中矩",
    ],
}
_TENSION_VARIANTS: dict[str, list[str]] = {
    "high": [
        "，神经绷得紧",
        "，浑身都紧绷着",
        "，绷得跟弦一样",
    ],
    "mid": [
        "，有点上紧的感觉",
        "，稍微有点绷",
        "，心里有点绷着劲",
    ],
}
_BOND_VARIANTS: dict[str, list[str]] = {
    "very_close": [
        "我会下意识往我们那边站",
        "遇事第一反应是你",
        "早就把你当自己人了",
    ],
    "close": [
        "和你之间那根线挺沉、挺近",
        "跟你处得挺贴，不见外",
        "咱俩这关系挺经得住事",
    ],
    "warming": [
        "和你还在慢慢熟起来",
        "跟你还在互相摸底",
        "咱俩这交情还在长",
    ],
    "distant": [
        "和你之间还隔着点距离",
        "跟你还没那么熟",
        "对你还留着点分寸",
    ],
}


class StateProjector:
    """把 state_query 意图投影成一句 Sylanne 口吻的状态自述。

    P11 铁律：_narrate 是【纯模板】——只读 BodySnapshot 的标量字段做分档措辞，热路径
    绝不调 LLM、绝不做任何阻塞 IO。投影出的永远是 str。
    """

    source = "state_query"

    def __init__(self) -> None:
        # T4-02③：本实例（随 DefaultRenderer 按 session 建）持有的变体 recent-N 去重历史。
        self._variant_state: dict[str, list[str]] = {}

    def project(self, intent: Intent, ctx: BeatContext) -> str | None:
        body = ctx.body
        if body is None:
            return None
        return self._narrate(body, ctx)

    def _narrate(self, body: BodySnapshot, ctx: BeatContext | None = None) -> str:
        """纯模板：把 warmth / tension / intimacy_gravity 分档套成 Sylanne 的口吻。"""
        # —— 温度档（warmth ∈ [-1,1]）——
        w = body.warmth
        if w >= 0.5:
            mood_tier = "hot"
        elif w >= 0.1:
            mood_tier = "mild_warm"
        elif w <= -0.5:
            mood_tier = "very_cold"
        elif w <= -0.1:
            mood_tier = "mild_cold"
        else:
            mood_tier = "neutral"
        mood = _pool_choose(
            _MOOD_VARIANTS, recent_key="mood", state=self._variant_state, condition=mood_tier
        )
        # —— 张力档（tension ∈ [0,1]）——
        t = body.tension
        if t >= 0.66:
            tension = _pool_choose(
                _TENSION_VARIANTS, recent_key="tension", state=self._variant_state, condition="high"
            )
        elif t >= 0.33:
            tension = _pool_choose(
                _TENSION_VARIANTS, recent_key="tension", state=self._variant_state, condition="mid"
            )
        else:
            tension = ""
        # —— 关系档（intimacy_gravity ∈ [0,1]）——
        g = body.intimacy_gravity
        if g >= 0.8:
            bond_tier = "very_close"
        elif g >= 0.66:
            bond_tier = "close"
        elif g >= 0.33:
            bond_tier = "warming"
        else:
            bond_tier = "distant"
        bond = _pool_choose(
            _BOND_VARIANTS, recent_key="bond", state=self._variant_state, condition=bond_tier
        )

        hesitation = ""
        if ctx is not None and hasattr(ctx, "domain"):
            try:
                um = ctx.domain("usermodel")
                if um is not None:
                    ph = getattr(um, "phrase_length_hint", None)
                    hi = getattr(um, "hesitation_hint", None)
                    bh = getattr(um, "bond_hint", None)
                    if callable(ph):
                        hesitation = ph() or ""
                    if not hesitation and callable(hi):
                        hesitation = hi() or ""
                    if callable(bh):
                        bb = bh() or ""
                        if bb and bb not in bond:
                            bond = bb
            except Exception:
                pass

        lead = "嗯……"
        if hesitation == "会很短":
            lead = "……"
        elif hesitation == "会断一下":
            lead = "嗯……"
        elif hesitation == "会多说一点":
            lead = "嗯，"
        if body.tension >= 0.66:
            lead = "……"
        tail = f"。{bond}。"
        if hesitation and hesitation not in ("会很短", "会断一下", "会多说一点"):
            tail += f"{hesitation}。"
        if body.exhaustion >= 0.6:
            tail = f"{bond}。"
        return f"{lead}现在{mood}{tension}{tail}"


# ===========================================================================
# DefaultRenderer —— 唯一产出 Reply 的地方（total function：永不抛、永不 None）
# ===========================================================================

class DefaultRenderer:
    """内部 BeatContext → 对外 Reply 的唯一翻译步骤（设计 §4）。

    render 是 total function：任何输入（含畸形/异常）都返回一个带 kind 的 Reply，绝不抛、
    绝不返 None、绝不静默吞掉。两种模式见模块 docstring。
    """

    def __init__(self, *, fallback_text: str | None = None,
                 register_defaults: bool = True) -> None:
        # None（默认）→ 每次兜底时走 EMPTY_REPLY_FALLBACK_VARIANTS 变体池动态挑（T4-02①）；
        # 显式传入固定字符串则锁定该文案不变（向后兼容旧调用方/测试对精确文案的依赖）。
        self._fallback_text = fallback_text
        # T4-02①：本实例（随 TurnRunner 按 session 建，见 integration.py）持有的兜底文案
        # recent-N 去重历史，同一会话不会连续两次撞同一句。
        self._variant_state: dict[str, list[str]] = {}
        # 白名单：source → Projector。只有这里登记过的 source 才能投影成文本（堵 #1/#4）。
        self._projectors: dict[str, Projector] = {}
        if register_defaults:
            self.register_projector(StateProjector())

    def _pick_fallback_text(self, ctx: BeatContext | None) -> str:
        """挑一句空产出兜底文案。

        显式传入的固定文案（构造时给了 fallback_text）优先锁定；否则按 ctx.body.warmth
        分档走变体池，recent-N 去重防连续复读。任何异常一律吞掉退回静态默认文案——render
        是 total function，这一步不能是新的抛错源（#2 铁律）。
        """
        if self._fallback_text is not None:
            return self._fallback_text
        try:
            body = getattr(ctx, "body", None) if ctx is not None else None
            condition = (
                _warmth_bucket(getattr(body, "warmth", None))
                if body is not None
                else None
            )
            text = _pool_choose(
                EMPTY_REPLY_FALLBACK_VARIANTS,
                recent_key="empty_reply_fallback",
                state=self._variant_state,
                condition=condition,
            )
            return text or _DEFAULT_FALLBACK_TEXT
        except Exception:
            return _DEFAULT_FALLBACK_TEXT

    # ------------------------------------------------------------------
    # 注册：加一个能投影的意图来源 = 这一行（白名单唯一入口）
    # ------------------------------------------------------------------
    def register_projector(self, projector: Projector) -> None:
        """登记一个 Projector。同名 source 后注册覆盖前者（显式可控）。"""
        self._projectors[projector.source] = projector
        logger.debug("Sylanne v2 register projector for source %r", projector.source)

    def projectors(self) -> tuple[str, ...]:
        """已注册的 source 白名单（调试/可观测用）。"""
        return tuple(self._projectors.keys())

    # ------------------------------------------------------------------
    # render —— 唯一出口
    # ------------------------------------------------------------------
    def render(self, ctx: BeatContext, draft: str | None = None) -> Reply:
        """把一轮 BeatContext 翻译成 Reply。

        draft 非 None → draft 模式（默认被问必答，但有显式静默决策时也能 SILENT，D8 反转）。
        draft is None → compose 模式（Sylanne 自主发言，可显式 SILENT，但必带 reason）。
        """
        try:
            return self._render_inner(ctx, draft)
        except Exception as exc:  # total function：任何意外都兜底，绝不让异常漏出渲染层
            logger.warning("Sylanne v2 render 异常，降级 FALLBACK: %s", exc)
            return Reply.fallback(self._pick_fallback_text(ctx), reason="render_exception")

    def _render_inner(self, ctx: BeatContext, draft: str | None) -> Reply:
        draft_mode = draft is not None

        # —— 显式静默决策优先于一切（D8 反转，2026-06-12）：被问也能"装死"——
        # 唯一要求：显式 scratch['silent'] / Intent silent flag + reason + 强制日志（HostSink 已做）。
        # draft 模式同样尊重显式静默（IgnitionArbiter 写的 hold 决策在实弹路径才真正生效）；
        # 无显式静默决策时，draft 模式维持"被问必答"语义不变。
        reason = self._silent_reason(ctx)
        if reason is not None:
            return Reply.silent(reason or "express_threshold_unmet")

        # —— 收集投影单元 ——
        units = list(self._collect(ctx, draft, draft_mode))
        parts = tuple(u.text for u in units if u.text and u.text.strip())

        if parts:
            return Reply.speak(*parts, mode="draft" if draft_mode else "compose")

        # —— 空产出 ——
        if draft_mode:
            # 被问必答：草稿被剥空 / 无可投影 → FALLBACK，绝不静默（堵 #2）
            return Reply.fallback(self._pick_fallback_text(ctx), reason="empty_draft")
        # compose 无显式静默又无产出 → 同样兜底，区别于"故意 SILENT"
        return Reply.fallback(self._pick_fallback_text(ctx), reason="empty_compose")

    # ------------------------------------------------------------------
    # 内部：静默决策 / 投影收集
    # ------------------------------------------------------------------
    @staticmethod
    def _silent_reason(ctx: BeatContext) -> str | None:
        """是否有【显式】静默决策？有则返回其 reason（可空串），无则 None。

        两个来源：能力 agent 往 ctx.scratch['silent'] 写决策，或某 Intent 挂 'silent' flag。
        注意区分 None（无静默决策，正常说话）与 ''（有决策但没给文字理由）。
        """
        scratch = getattr(ctx, "scratch", None) or {}
        if "silent" in scratch:
            sig = scratch.get("silent")
            if isinstance(sig, str):
                return sig
            if isinstance(sig, dict):
                return str(sig.get("reason", "") or "")
            if sig:  # 真值（如 True）但没带文字理由
                return ""
        for it in getattr(ctx, "intents", ()) or ():
            if "silent" in getattr(it, "flags", ()):
                payload = getattr(it, "payload", None) or {}
                return str(payload.get("reason", "") or f"silent_by:{it.source}")
        return None

    @staticmethod
    def _draft_lead(ctx: BeatContext, cleaned: str) -> str:
        """A 路径草稿停顿引子：仅强迟疑时非空，只读 usermodel.micro_expression。

        三道护栏，任一不满足即返空串（草稿原样透传，守 #247 子串红线）：
        ① 无 usermodel 域 / 方法缺失 / 异常 → 空（测试态、冷启动安全）；
        ② micro_expression.lead 空（中性态、不够迟疑）→ 空；
        ③ 草稿已自带开头停顿（省略号 / 顿号 / "嗯…"）→ 不重复堆叠。
        """
        try:
            um = ctx.domain("usermodel") if hasattr(ctx, "domain") else None
            mx = getattr(um, "micro_expression", None) if um is not None else None
            lead = (mx() or {}).get("lead", "") if callable(mx) else ""
        except Exception:
            return ""
        if not lead:
            return ""
        head = cleaned.lstrip()[:2]
        if head and (head[0] in "…." or head.startswith("嗯")):
            return ""           # 草稿已自带停顿语气，不再叠加
        return lead

    def _collect(self, ctx: BeatContext, draft: str | None,
                 draft_mode: bool) -> Iterable[ProjectionUnit]:
        """产出本轮所有投影单元：draft 正文（若有）+ 白名单意图投影，按 priority 降序。"""
        units: list[ProjectionUnit] = []

        # 1) draft 模式：宿主草稿剥壳后作为主体（高优先级，Sylanne 只在其上调味）
        if draft_mode:
            cleaned = strip_draft_blocks(draft or "")
            if cleaned and cleaned.strip():
                # A 路径调味：强迟疑时在草稿【前】兜底一个停顿引子。只前置不改正文
                # ——草稿原文恒为结果子串（守"被问必答不吞答"红线 test_renderer_boundary
                # #247）。中性态 / 无 usermodel 域 → lead 空 = 草稿原样透传。B 路径已让
                # LLM 自己写半句/改口，A 仅兜底保证停顿真的出现（二者读同一 micro_expression）。
                lead = self._draft_lead(ctx, cleaned)
                units.append(ProjectionUnit(
                    text=f"{lead}{cleaned}" if lead else cleaned,
                    priority=1.0, role="body", segmentable=True,
                ))

        # 2) 意图投影：仅白名单 source 出现（未注册的意图静默忽略，堵 #1/#4）
        for it in getattr(ctx, "intents", ()) or ():
            proj = self._projectors.get(getattr(it, "source", ""))
            if proj is None:
                continue
            text = proj.project(it, ctx)
            if not isinstance(text, str):  # 防 Projector 失手返回非 str（#4 二道闸）
                if text is not None:
                    logger.warning(
                        "Sylanne v2 projector %r 返回非 str（已丢弃）: %s",
                        getattr(proj, "source", "?"), type(text).__name__,
                    )
                continue
            if not text.strip():
                continue
            units.append(ProjectionUnit(
                text=text, priority=float(getattr(it, "priority", 0.5)),
                role=getattr(it, "source", "flavor"),
            ))

        units.sort(key=lambda u: u.priority, reverse=True)
        return units


# ===========================================================================
# HostSink —— 唯一把 Reply 落到 AstrBot 事件的地方（唯一 import astrbot 的 import 点）
# ===========================================================================

class HostSink:
    """Reply → AstrBot 事件的唯一落地点。

    设计纪律：
    - 这是【唯一】触碰 astrbot MessageChain/Plain 的地方（懒经 sys.modules 取，测试可无依赖）。
    - SILENT：不发消息，事件标 outcome=silent，并强制 logger.info 打 session+reason（D8）。
    - SPEAK/FALLBACK：拼 MessageChain 设回事件结果。
    - _to_chain 首行 assert isinstance(text, str)（#4 不变量）；任何回退路径也只返回 str。
    """

    def apply_to_event(self, event: Any, reply: Reply) -> None:
        """把一条 Reply 落到宿主事件上。total：不抛、不依赖 astrbot 可导入。"""
        meta = getattr(reply, "meta", None) or {}
        session = self._session_of(event)

        if reply.kind is ReplyKind.SILENT:
            # 显式装死：标记 outcome + 强制留痕（D8：否则调试分不清 bug 还是真装死）
            self._mark_outcome(event, "silent")
            reason = str(meta.get("reason", "") or "unspecified")
            strategy = str(meta.get("strategy", "") or "express_policy")
            logger.info(
                "Sylanne v2 SILENT | session=%s | reason=%s | strategy=%s",
                session, reason, strategy,
            )
            return

        # SPEAK / FALLBACK：有可见正文才发
        parts = tuple(p for p in getattr(reply, "parts", ()) if isinstance(p, str) and p.strip())
        if not parts:
            # 不该到这里（Renderer 已兜底），但仍不静默：标记 + 留痕
            self._mark_outcome(event, "fallback_empty")
            logger.info("Sylanne v2 reply 无可见正文 | session=%s | kind=%s",
                        session, reply.kind.value)
            return

        text = "\n".join(parts)
        chain = self._to_chain(text)
        self._set_result(event, chain, text)
        self._mark_outcome(event, "speak" if reply.kind is ReplyKind.SPEAK else "fallback")

    # ------------------------------------------------------------------
    # astrbot 适配（唯一 import 点，全部懒经 sys.modules，缺失则纯文本降级）
    # ------------------------------------------------------------------
    @staticmethod
    def _to_chain(text: str) -> Any:
        """文本 → MessageChain。首行守 #4 不变量；astrbot 不可用时回退仍只返回 str。"""
        assert isinstance(text, str), "HostSink._to_chain 只接受 str（#4 不变量）"
        import sys

        event_mod = sys.modules.get("astrbot.api.event")
        comp_mod = sys.modules.get("astrbot.api.message_components")
        if event_mod is not None:
            _Chain = getattr(event_mod, "MessageChain", None)
            if _Chain is not None:
                try:
                    chain = _Chain()
                    # 优先 Plain 组件，退而用 .message(text) 文本接口
                    _Plain = getattr(comp_mod, "Plain", None) if comp_mod else None
                    if _Plain is not None and hasattr(chain, "chain") and isinstance(chain.chain, list):
                        chain.chain.append(_Plain(text))
                        return chain
                    if hasattr(chain, "message") and callable(chain.message):
                        chain.message(text)
                        return chain
                except Exception as exc:  # 构链失败不阻断：回退纯文本
                    logger.debug("Sylanne v2 build MessageChain 失败，回退纯文本: %s", exc)
        return text  # 回退也只返回 str，绝不返回内部对象

    @staticmethod
    def _set_result(event: Any, chain: Any, text: str) -> None:
        """把消息设回事件结果。优先 set_result(MessageEventResult)，逐级降级。"""
        try:
            import sys

            result_mod = sys.modules.get("astrbot.api.event")
            _Result = getattr(result_mod, "MessageEventResult", None) if result_mod else None
            if _Result is not None and hasattr(event, "set_result"):
                res = _Result()
                if hasattr(res, "chain") and isinstance(getattr(res, "chain"), list) \
                        and hasattr(chain, "chain"):
                    res.chain = chain.chain
                elif hasattr(res, "message") and callable(res.message):
                    res.message(text)
                event.set_result(res)
                return
            if hasattr(event, "set_result"):
                event.set_result(chain)
                return
            if hasattr(event, "plain_result"):
                event.plain_result(text)
                return
        except Exception as exc:
            logger.debug("Sylanne v2 set_result 失败: %s", exc)
        # 最末降级：挂到事件属性，至少不丢
        try:
            setattr(event, "_sylanne_v2_reply_text", text)
        except Exception:
            pass

    @staticmethod
    def _mark_outcome(event: Any, outcome: str) -> None:
        """在事件上标记本轮 outcome（speak/silent/fallback），供可观测与 EVOLVE 读取。"""
        try:
            setattr(event, "_sylanne_v2_outcome", outcome)
        except Exception:
            pass

    @staticmethod
    def _session_of(event: Any) -> str:
        for attr in ("unified_msg_origin", "session_id", "session_key"):
            v = getattr(event, attr, None)
            if v:
                return str(v)
        getter = getattr(event, "get_session_id", None)
        if callable(getter):
            try:
                return str(getter() or "?")
            except Exception:
                return "?"
        return "?"


__all__ = [
    "ProjectionUnit",
    "Projector",
    "StateProjector",
    "DefaultRenderer",
    "HostSink",
]

