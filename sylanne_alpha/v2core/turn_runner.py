"""v2core 整轮编排（Fable 重做版）—— 两阶段 turn，对齐宿主的两个钩子。

本架构把三拍映射到宿主的真实生命周期（这是对旧版"全挤在 response 阶段"的修正）：

  request 阶段（LLM 调用前）          response 阶段（LLM 草稿已出）
  ┌─────────────────────────┐        ┌──────────────────────────────────────┐
  │ PERCEPT（只读）          │  ───→  │ DELIBERATE → render → EVOLVE →        │
  │ · 读 body / 领域         │        │ 领域 ingest → (response tick) → learn │
  │ · 评价/读心/信号         │        │                                      │
  │ · 心象片段 → prompt      │        │ 裁决草稿：speak / 装死 / 兜底          │
  │ · assessment → 请求tick  │        │ 她听见自己说的话（response tick）      │
  └─────────────────────────┘        └──────────────────────────────────────┘

入体通道（与旧版的本质区别，全部走 SDK 既有语义，零额外 tick）：
- 评价 assessment：经 integration 暂存，由 legacy 请求管线在它本来就要打的
  host.on_request(assessment=…) 里合并入体——不再有"空文本补一拍"的统计污染。
- 行动知觉：response tick 喂【最终回复文本】（或静默轮的空文本+silent flag），
  她从自己的言语/沉默里学习。是否由本层打这一拍由 integration 决定
  （legacy realtime 分发分支自带 observe_response 时不重复打，全局恰好一拍）。
- L1 漂移：learn() → feedback_quality（DRIFT_SIGNALS 通道，实证 expression_fired/
  sustained_silence 在表）。

并发纪律：response 阶段（含 tick）必须在 plugin._session_lock(session_key) 持有下
运行——由 integration 负责拿锁，本模块不自行加锁（避免双重加锁死锁）。
"""

from __future__ import annotations

import time
from typing import Any

from sylanne_alpha.v2core.contracts import BeatContext, Reply
from sylanne_alpha.v2core.renderer import DefaultRenderer


def _event_now(event: Any) -> float:
    """从宿主事件取本轮时间戳（秒）；取不到回落 wall clock。"""
    if isinstance(event, dict):
        v = event.get("now")
    else:
        v = getattr(event, "now", None)
    try:
        f = float(v)
        if f > 0.0:
            return f
    except (TypeError, ValueError):
        pass
    return time.time()


def _event_proactive(event: Any) -> bool:
    """本轮事件是否主动触达——对象属性 + dict 键双形态探测（对齐 _event_now）。

    旧实现只用 getattr，对 dict 形态事件（如 integration 主动轮传 {"proactive": True}）
    恒读到 False，靠调用方手补 scratch 兜底——是雷。这里统一双形态探测，根上修。
    """
    if event is None:
        return False
    if isinstance(event, dict):
        return bool(event.get("proactive", False))
    return bool(getattr(event, "proactive", False))


class TurnRunner:
    """两阶段编排器。组合 SelfCore（拍调度）+ Renderer（出口契约）+ 领域 ingest。"""

    def __init__(self, self_core: Any, renderer: DefaultRenderer | None = None) -> None:
        self._sc = self_core
        self._renderer = renderer or DefaultRenderer()

    # ------------------------------------------------------------------
    # 阶段一：PERCEPT（request 钩子，只读，无锁需求）
    # ------------------------------------------------------------------
    def run_percept_stage(
        self, session_key: str, event: Any, text: str, *,
        domains: dict[str, Any] | None = None,
        groups: Any = None,
        now: float | None = None,
        idle: bool = False,
    ) -> BeatContext:
        """跑 PERCEPT 拍，返回 ctx（供 integration 暂存到 response 阶段续用）。

        全程只读（observe + 领域读接口），不 tick、不写领域——天然并发安全。
        """
        ctx = self._sc.make_context(
            session_key, event, text, domains=domains or {}, groups=groups,
            now=now if now is not None else _event_now(event),
        )
        if idle:
            ctx.scratch["idle"] = True
        ev = getattr(ctx, "event", None)
        if _event_proactive(ev):
            ctx.scratch["proactive"] = True
        self._sc.run_percept(ctx)
        return ctx

    # ------------------------------------------------------------------
    # 阶段二：DELIBERATE + render + EVOLVE（response 钩子，须持会话锁）
    # ------------------------------------------------------------------
    def run_decision_stage(
        self, ctx: BeatContext, *,
        draft: str | None,
        do_response_tick: bool,
        refresh_body: bool = True,
    ) -> Reply:
        """裁决草稿 + 学习 + （按需）response tick。调用方必须持有会话锁。

        refresh_body：percept 与本阶段之间隔了 legacy 的 request tick（body 已变），
        默认重读快照让 DELIBERATE 吃到最新身体。
        """
        if refresh_body:
            try:
                self._sc.refresh_body(ctx)
            except Exception:
                pass

        self._sc.run_deliberate(ctx)

        reply = self._renderer.render(ctx, draft=draft)
        ctx.scratch["render_outcome"] = reply.kind   # 消费者：EmotionLedger.ingest（P15）
        ctx.scratch["reply"] = reply                 # observability：无逻辑消费者，调试/工具用

        # EVOLVE：能力 evolve 钩子 → 领域 ingest（单一写相位语义内）
        self._sc.run_evolve(ctx)
        for name, dom in (ctx.domains or {}).items():
            ingest = getattr(dom, "ingest", None)
            if callable(ingest):
                try:
                    ingest(ctx)
                except Exception as exc:
                    self._log(f"domain {name!r} ingest failed: {exc}")
        # 记忆衰减：每轮 EVOLVE 推进一步（与 legacy 每消息 tick_decay 对齐）
        mem = (ctx.domains or {}).get("memory")
        if mem is not None and hasattr(mem, "tick_decay"):
            try:
                mem.tick_decay()
            except Exception as exc:
                self._log(f"memory tick_decay failed: {exc}")

        # CP8-P4 质量自评（写 scratch["quality"]，_drive_learning 消费）须在 learn 前
        self._assess_quality(ctx, reply)
        # L1 漂移先于 tick：learn 直驱 computation，靠紧随的 tick CoW 快照落盘
        self._drive_learning(ctx, reply)

        if do_response_tick:
            self.response_tick(ctx, reply)

        return reply

    def run_deliberate_only(self, ctx: BeatContext) -> None:
        """只跑 DELIBERATE 拍（零写、零 tick）。消费者：integration.consult_idle_reach。"""
        self._sc.run_deliberate(ctx)

    # ------------------------------------------------------------------
    # 便捷入口：一次跑完两阶段（测试 / 空闲轮 / compose 场景）
    # ------------------------------------------------------------------
    async def run_turn(
        self,
        session_key: str,
        event: Any,
        text: str,
        *,
        domains: dict[str, Any] | None = None,
        groups: Any = None,
        draft: str | None = None,
        budget_ms: float | None = None,
        now: float | None = None,
        idle: bool = False,
        do_response_tick: bool = True,
    ) -> tuple[Reply, BeatContext]:
        """单调用跑完整 turn。生产实弹路径走两阶段入口；本入口供测试/空闲轮。"""
        ctx = self.run_percept_stage(
            session_key, event, text, domains=domains, groups=groups,
            now=now, idle=idle,
        )
        if budget_ms is not None:
            ctx.budget_ms = budget_ms
        reply = self.run_decision_stage(
            ctx, draft=draft, do_response_tick=do_response_tick, refresh_body=False,
        )
        return reply, ctx

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def response_tick(self, ctx: BeatContext, reply: Reply) -> None:
        """行动知觉：她听见自己刚说的话（或自己的沉默）。

        response tick 走 host.on_response（含落盘链）。SILENT 轮喂空文本 + silent flag
        ——"我没说话"也是要被身体感知的行动结果。任何异常吞掉（绝不阻断回复）。
        """
        from sylanne_alpha.v2core.contracts import ReplyKind

        bp = getattr(self._sc, "_body", None)
        tick = getattr(bp, "tick", None)
        if not callable(tick):
            return
        if reply.kind is ReplyKind.SPEAK:
            text = "\n".join(reply.parts)
            flags = ["response", "safe"]
        elif reply.kind is ReplyKind.SILENT:
            text = ""
            flags = ["response", "silent"]
        else:  # FALLBACK
            text = "\n".join(reply.parts)
            flags = ["response", "fallback"]
        event = {"phase": "response", "text": text[:500], "flags": flags,
                 "confidence": 0.7, "now": float(ctx.scratch.get("now", 0.0) or time.time())}
        try:
            tick(event)
        except Exception as exc:
            self._log(f"response tick failed: {exc}")

    @staticmethod
    def _assess_quality(ctx: BeatContext, reply: Reply) -> None:
        """CP8-P4 对话质量自评 → scratch["quality"]（review F3：接活死读）。

        v1 退役交接：旧 DialogueAgent 在 RESPONSE_POST 用 self_score 三维均值发
        dialogue_quality_high/low（DRIFT_SIGNALS 真实在表：质量高→表达欲+关系引力涨）。
        v2core 启用即退役 v1 逐轮路径，这条"她从自己回复的质量里学"的闭环断粮——
        本方法在 render 之后用同一把尺（self_score 零-LLM 启发式 + 同阈值 0.7/0.35，
        保守防自评噪声驱动激进漂移）补上。消费者：_drive_learning → learn(quality_signal)
        → feedback_quality（DRIFT_SIGNALS 通道）。
        已有外部预置 scratch["quality"]（如测试/将来更强判定源）→ 不覆盖。
        """
        from sylanne_alpha.v2core.contracts import ReplyKind

        if isinstance(ctx.scratch.get("quality"), str):
            return                       # 外部预置优先
        if reply.kind is not ReplyKind.SPEAK:
            return                       # 质量自评只对真实说出的话有意义
        user_text = (ctx.text or "").strip()
        bot_text = "\n".join(p for p in reply.parts if p.strip())
        if not user_text or not bot_text:
            return                       # 空闲/主动轮无 user_text：没有可评的对话对
        try:
            from sylanne_alpha.dialogue import self_score

            score = self_score(user_text, bot_text)
            quality = (float(score.get("coherence", 0.0))
                       + float(score.get("emotion_match", 0.0))
                       + float(score.get("info_density", 0.0))) / 3.0
        except Exception:
            return                       # 自评失败绝不阻断 turn（弱信号，丢了无妨）
        # 字符串标签仅 WebUI 留痕用；阈值对齐 SDK 漂移门控 0.7/0.3
        # （personality._DIALOGUE_QUALITY_HIGH/LOW），避免 (0.3,0.35] 区间标 low 但 SDK 不漂的
        # 展示↔真实打架（红队 wjqkfgh4i minor 修复）。真正驱动漂移的是下方 float quality_score。
        if quality >= 0.7:
            ctx.scratch["quality"] = "dialogue_quality_high"
        elif quality <= 0.3:
            ctx.scratch["quality"] = "dialogue_quality_low"
        # canonical 数值通道（迁移 2026-06-14）：保留 float 质量分，供 integration 落
        # rt["pending_quality"]，下轮 request tick 经 event.values["dialogue_quality"] 注入
        # → process(dialogue_quality=) → _drift_embodiment 自动漂移。
        ctx.scratch["quality_score"] = float(quality)

    def _drive_learning(self, ctx: BeatContext, reply: Reply) -> None:
        """表达结果信号的归属（canonical 迁移 2026-06-14，核查任务 wdjxyayf1）。

        迁移后 L1 embodiment 漂移的唯一发生地是 process 内部（_drift_embodiment）：
          - expression_fired ← process 自派生 result["should_express"]（response_tick 喂回复文本，
            自动派生，无需此处 learn 驱动）
          - dialogue_quality ← _assess_quality 的 float 经 rt["pending_quality"] 下轮注入
          - sustained_silence ← canonical 不可达，记 SDK backlog（缺口1），不在此 hack
        故本方法不再经 learn 传 expression_fired/sustained_silence（旧 feedback_quality 通道已退役）。
        learn() 现仅为真实用户反应反馈占位；保留调用以备将来真实反应判定源接入（届时传 actual_expressed）。
        """
        from sylanne_alpha.v2core.contracts import ReplyKind

        bp = getattr(self._sc, "_body", None)
        learn = getattr(bp, "learn", None)
        if not callable(learn):
            return
        spoke = reply.kind is ReplyKind.SPEAK
        # 不再传表达结果 outcome（已无漂移通道）；保留 actual_expressed 供未来真实反应接入。
        # outcome 占位用中性 "" —— learn 当前对其无副作用（仅占位）。
        try:
            learn("", actual_expressed=spoke)
        except Exception as exc:
            self._log(f"learn drive failed: {exc}")

    def _log(self, msg: str) -> None:
        import logging
        logging.getLogger("astrbot_plugin_sylanne").warning("Sylanne v2 turn_runner: %s", msg)


__all__ = ["TurnRunner"]
