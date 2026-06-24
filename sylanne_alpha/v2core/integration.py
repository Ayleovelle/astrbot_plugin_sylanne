"""v2core ↔ 宿主管线桥接（Fable 重做版）—— 双阶段接管。

接线图（每条线都有实测的真实端点，无死信号）：

  on_llm_request（main.py 钩子）
    └→ apply_v2core_request：PERCEPT（只读）
         ├→ 心象片段 → request.system_prompt（她的认知影响她说什么——主动脉）
         ├→ 评价 assessment 暂存 → legacy 请求管线在 host.on_request(assessment=…)
         │   合并入体（consume_pending_assessment；SDK 唯一 assessment 入口，零额外 tick）
         └→ ctx 暂存，response 阶段续用

  on_llm_response（main.py 钩子）
    └→ apply_v2core_response：DELIBERATE+EVOLVE（持会话锁）
         ├→ SILENT：清空 completion_text + D8 强制日志 + 本层补 response tick → True
         │   （跳过 legacy——它的 no-ghost 兜底会把刻意装死复活成兜底文案）
         └→ SPEAK/FALLBACK：写回文本 → False【故意回落】——legacy 分发机条带着
             sanitize（[sylanne_*] 注入防御）、realtime 分段打字节奏、观测/记忆缓冲
             一起跑。v2core 是心智层，分发是 legacy 的嘴；接管心智不没收嘴。
             response tick 归属：realtime 拦截开启时 legacy 的 observe_response 打
             （不重复）；未开启时本层打。全局每轮恰好一拍。

  proactive（外部主动桥轮询 get_speech_decision）
    └→ consult_idle_reach：空闲 PERCEPT+DELIBERATE（零写、零 tick），reach 胜出
        → 抬升 should_speak —— 沉默积累真的能让她主动找你（吃既有冷却/静默闸，
        防连发不造新阀门）。

  terminate（main.py）
    └→ drain_pending_saves + save_all_domains：停机前排干在途落盘 + 终扫——
        修旧版"terminate 反手 cancel 掉最后一轮存档"的反向 bug。

死线守护（铁律④）：域状态总键 sylanne_v2core_domains:{safe} 与旧档格式兼容；
host/body 漂移仍走插件现有文件持久化，不另起炉灶。

开关：sylanne_enable_v2core（**默认开——v2core 是唯一认知内核**）。v2core 即唯一认知
内核（旧 SelfCore PRE/POST/RESPONSE_POST 与 AssessorAgent 逐轮 LLM 评估已退役、删除，
intent=="撒娇" 硬编码路径自然断粮）。flag 置 false = 部署级紧急回退到 v1。
任何异常 → 单轮回落旧管线，不阻断回复。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Any

logger = logging.getLogger("astrbot_plugin_sylanne")

_V2CORE_FLAG = "sylanne_enable_v2core"
_DOMAIN_STATE_KEY_FMT = "sylanne_v2core_domains:{safe}"
_DOMAIN_STATE_VERSION = 1
_PENDING_CTX_TTL = 180.0      # request 阶段暂存 ctx 的有效期（秒）
_QUALITY_TTL_S = 600.0        # 对话质量分滞后反馈时效（秒）：超此视为陈旧/新话题，丢弃不注入

# 落盘任务的模块级强引用锚（防 fire-and-forget task 被 GC 提前回收）
_PENDING_SAVES: set[Any] = set()


def v2core_enabled(plugin: Any) -> bool:
    """v2core 是否启用。默认【开】——v2core 是唯一认知内核（v1 已退役）。

    flag 仅作部署级紧急回退口：显式置 false 才回到 v1 旧管线认知。
    """
    cfg = getattr(plugin, "_config", None) or getattr(plugin, "config", None) or {}
    return bool(cfg.get(_V2CORE_FLAG, True))


def _safe_session_key(session_key: str) -> str:
    return str(session_key).replace("/", "_").replace("\\", "_")


def _kv(plugin: Any) -> Any:
    if hasattr(plugin, "get_kv_data") and hasattr(plugin, "put_kv_data"):
        return plugin
    return None


def _session_lock(plugin: Any, session_key: str) -> Any:
    """取会话锁（与 legacy 请求观测/自驱心跳同一把——S5 串行义务的落点）。

    插件桩没有锁工厂时退化为 null context（测试环境单线程）。
    """
    getter = getattr(plugin, "_session_lock", None)
    if callable(getter):
        try:
            lock = getter(session_key)
            if lock is not None:
                return lock
        except Exception:
            pass
    return contextlib.nullcontext()


# ===========================================================================
# 域状态持久化（键格式与旧档兼容）
# ===========================================================================

async def _load_domains(plugin: Any, session_key: str, domains: dict[str, Any]) -> dict[str, float]:
    """从域状态总键恢复各域（容缺：键不存在/某域缺=空起步，铁律④）。

    返回恢复出的缺陷行为不应期表（behavior_last_fired，{id: ts}），供 _ensure_loaded 灌回 rt——
    陈旧 ts（早于不应期）天然被 select_behavior 忽略，无需迁移/时钟处理（review medium：重启不清零）。
    """
    kv = _kv(plugin)
    if kv is None:
        return {}
    try:
        key = _DOMAIN_STATE_KEY_FMT.format(safe=_safe_session_key(session_key))
        blob = await kv.get_kv_data(key, None)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Sylanne v2core 域状态读取失败 [%s]: %s", session_key, exc)
        return {}
    if not isinstance(blob, dict):
        return {}
    for name, dom in domains.items():
        data = blob.get(name)
        if not isinstance(data, dict):
            continue
        try:
            loader = getattr(dom, "overlay_load_dict" if name == "memory" else "load_dict", None)
            if callable(loader):
                loader(data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Sylanne v2core 域 %r 恢复失败: %s", name, exc)
    blf = blob.get("_behavior_last_fired")
    if isinstance(blf, dict):
        return {str(k): float(v) for k, v in blf.items() if isinstance(v, (int, float))}
    return {}


async def _save_domains(plugin: Any, session_key: str, domains: dict[str, Any],
                        behavior_last_fired: dict[str, float] | None = None) -> None:
    """各域状态落进域总键。memory 域只存重固化影子层（底层 MemorySystem 自有键）。

    behavior_last_fired（缺陷行为不应期表）随域 blob 一同落盘——piggyback 既有 debounce 落盘，
    请求热路径仍零 IO（review medium：不应期 RAM-only 重启即丢，敏感行为长不应期形同虚设）。
    """
    kv = _kv(plugin)
    if kv is None:
        return
    blob: dict[str, Any] = {"_version": _DOMAIN_STATE_VERSION}
    for name, dom in domains.items():
        try:
            dumper = getattr(dom, "overlay_to_dict" if name == "memory" else "to_dict", None)
            if callable(dumper):
                blob[name] = dumper()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Sylanne v2core 域 %r 序列化失败: %s", name, exc)
    if isinstance(behavior_last_fired, dict) and behavior_last_fired:
        blob["_behavior_last_fired"] = {str(k): float(v) for k, v in behavior_last_fired.items()
                                        if isinstance(v, (int, float))}
    try:
        key = _DOMAIN_STATE_KEY_FMT.format(safe=_safe_session_key(session_key))
        await kv.put_kv_data(key, blob)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Sylanne v2core 域状态写入失败 [%s]: %s", session_key, exc)


def _schedule_domain_save(plugin: Any, session_key: str, domains: dict[str, Any],
                          behavior_last_fired: dict[str, float] | None = None) -> None:
    """fire-and-forget 落盘。模块级 _PENDING_SAVES 强引用锚定（防 GC）。

    与旧版的差别：不再挂 plugin._background_tasks——terminate() 对那张表做的是
    cancel（取消在途存档=反向 bug）。停机排干走本模块 drain_pending_saves()。
    """
    coro = _save_domains(plugin, session_key, domains, behavior_last_fired)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        task = loop.create_task(coro)
        _PENDING_SAVES.add(task)
        task.add_done_callback(_PENDING_SAVES.discard)
    else:
        try:
            asyncio.run(coro)
        except Exception:  # noqa: BLE001
            coro.close()


async def drain_pending_saves(timeout: float = 5.0) -> None:
    """停机/卸载前排干在途域状态落盘（main.terminate 在 cancel 后台任务【之前】调用）。"""
    pending = [t for t in _PENDING_SAVES if not t.done()]
    if not pending:
        return
    try:
        await asyncio.wait(pending, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Sylanne v2core drain saves: %s", exc)


async def save_all_domains(plugin: Any) -> None:
    """终扫：把所有活跃会话的域状态同步落盘一遍（terminate 兜底）。"""
    cache = getattr(plugin, "_v2core_runtimes", None)
    if not isinstance(cache, dict):
        return
    for session_key, rt in list(cache.items()):
        domains = rt.get("domains") if isinstance(rt, dict) else None
        if isinstance(domains, dict) and domains:
            try:
                await _save_domains(plugin, session_key, domains,
                                    rt.get("behavior_last_fired") if isinstance(rt, dict) else None)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Sylanne v2core 终扫落盘失败 [%s]: %s", session_key, exc)


# ===========================================================================
# 运行态构建
# ===========================================================================

def _runtime_for(plugin: Any, session_key: str) -> dict[str, Any]:
    """取/建该会话的 v2core 运行态（SelfCore + 领域束 + TurnRunner）。"""
    from sylanne_alpha.v2core.body_port_v2 import CanonicalKernelBodyPort
    from sylanne_alpha.v2core.capabilities.expression import ExpressionCapability
    from sylanne_alpha.v2core.capabilities.ignition import IgnitionArbiter
    from sylanne_alpha.v2core.capabilities.mentalize import (
        AppraisalCapability,
        MentalizeCapability,
    )
    from sylanne_alpha.v2core.capabilities.recall import RecallCapability
    from sylanne_alpha.v2core.capabilities.reconsolidation import ReconsolidationCapability
    from sylanne_alpha.v2core.capabilities.somatic import (
        OutreachCapability,
        SomaticMarkerCapability,
    )
    from sylanne_alpha.v2core.domains.distillation import DistillationDomain
    from sylanne_alpha.v2core.domains.emotion import EmotionLedger
    from sylanne_alpha.v2core.domains.focus import FocusDomain
    from sylanne_alpha.v2core.domains.memory import MemoryDomain
    from sylanne_alpha.v2core.domains.narrative_self import NarrativeSelfDomain
    from sylanne_alpha.v2core.domains.user_model import UserModelDomain
    from sylanne_alpha.v2core.renderer import DefaultRenderer
    from sylanne_alpha.v2core.self_core import SelfCore
    from sylanne_alpha.v2core.turn_runner import TurnRunner

    cache = getattr(plugin, "_v2core_runtimes", None)
    if cache is None:
        cache = {}
        plugin._v2core_runtimes = cache
    rt = cache.get(session_key)
    if rt is not None:
        return rt

    host = plugin._host(session_key)
    bp = CanonicalKernelBodyPort.from_host(host, session_key)
    sc = SelfCore(bp)
    # 注册序即拍内执行序：
    # PERCEPT    — mentalize(预判你) / appraisal(评价你这条消息)
    # DELIBERATE — mentalize(失同步澄清) → somatic(偏置) → recall(吃偏置) →
    #              expression(驱力+风格) → outreach(空闲压力) → ignition(末位仲裁)
    # EVOLVE     — reconsolidation(重固化窗口) → 领域 ingest（TurnRunner 驱动）
    sc.register(MentalizeCapability())
    sc.register(AppraisalCapability())
    sc.register(SomaticMarkerCapability())
    sc.register(RecallCapability())
    sc.register(ExpressionCapability())
    sc.register(OutreachCapability())
    sc.register(IgnitionArbiter())
    sc.register(ReconsolidationCapability())

    domains: dict[str, Any] = {
        "emotion": EmotionLedger(),
        "usermodel": UserModelDomain(),
        "narrative": NarrativeSelfDomain(),
        "distill": DistillationDomain(),
        "focus": FocusDomain(),
    }
    try:
        ms_getter = getattr(plugin, "_memory_system_for_session", None)
        if callable(ms_getter):
            ms = ms_getter(session_key)
            if ms is not None:
                domains["memory"] = MemoryDomain(ms)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Sylanne v2core: memory domain unavailable: %s", exc)

    rt = {
        "runner": TurnRunner(sc, DefaultRenderer()),
        "domains": domains,
        "body_port": bp,
        "pending": None,              # request 阶段暂存的 ctx
        "pending_assessment": None,   # 待 legacy 请求 tick 合并的评价
        "pending_quality": None,      # 待下轮 request tick 注入的对话质量分(float, 滞后反馈)
        "loaded": False,
    }
    cache[session_key] = rt
    return rt


async def _ensure_loaded(plugin: Any, session_key: str, rt: dict[str, Any]) -> None:
    if not rt.get("loaded"):
        rt["behavior_last_fired"] = await _load_domains(plugin, session_key, rt["domains"])
        rt["loaded"] = True


def _is_cron_event(event: Any) -> bool:
    """定时任务（cron）的 LLM 回复是内部总结：v2core 不处理（与 legacy 同判据）——
    否则内部总结文本会污染用户模型/蒸馏的学习流。"""
    pm = getattr(event, "platform_meta", None)
    if pm is not None and str(getattr(pm, "name", "") or "") == "cron":
        return True
    umo = str(getattr(event, "unified_msg_origin", "") or "")
    return umo.startswith("cron")


async def _percept_recall(
    plugin: Any,
    ctx: Any,
    domains: dict[str, Any],
    text: str,
) -> None:
    """PERCEPT 拍召回（T1-6/7）：当轮 prompt 可消费，含 embedding。"""
    memory = domains.get("memory")
    if memory is None or not (text or "").strip():
        return
    try:
        if not memory.intimacy_ok(ctx.body):
            return
        limit = 2
        bias = ctx.scratch.get("somatic_bias")
        approach = float(getattr(bias, "approach_recall", 0.5) or 0.0)
        if approach <= -0.5:
            return
        if approach < 0.0:
            limit = 1
        query_embedding = None
        cfg = getattr(plugin, "_config", None) or getattr(plugin, "config", None) or {}
        enabled = bool(cfg.get("sylanne_alpha_embedding_memory_enabled"))
        provider_id = str(cfg.get("sylanne_alpha_embedding_memory_provider_id") or "")
        if enabled and provider_id:
            get_prov = getattr(plugin, "_get_embedding_provider", None)
            if callable(get_prov):
                try:
                    provider = get_prov(provider_id)
                    if provider:
                        query_embedding = await provider.get_embedding(text[:100])
                except Exception:
                    query_embedding = None
        results = memory.recall(
            text, warmth=ctx.current_warmth, limit=limit, query_embedding=query_embedding
        )
        if results:
            ctx.scratch["recalled"] = results
    except Exception:
        pass


def _user_text(plugin: Any, event: Any) -> str:
    """提取用户文本：message_str 优先，回落 response 管线的链解析。"""
    text = str(getattr(event, "message_str", "") or "")
    if text:
        return text
    try:
        pipe = getattr(plugin, "_llm_response_pipeline", None)
        if pipe is not None and hasattr(pipe, "_text"):
            return str(pipe._text(event) or "")
    except Exception:
        pass
    return ""


# ===========================================================================
# 阶段一：request 钩子（PERCEPT + 心象注入 + 评价暂存）
# ===========================================================================

async def apply_v2core_request(plugin: Any, event: Any, request: Any) -> None:
    """LLM 请求前的认知阶段。只读（不 tick 不写域），任何异常吞掉不阻断请求。"""
    if not v2core_enabled(plugin) or request is None or _is_cron_event(event):
        return
    try:
        session_key = plugin._session_key(event)
        text = _user_text(plugin, event)
        if not text.strip():
            return
        rt = _runtime_for(plugin, session_key)
        await _ensure_loaded(plugin, session_key, rt)

        ctx = rt["runner"].run_percept_stage(
            session_key, event, text, domains=rt["domains"],
        )
        await _percept_recall(plugin, ctx, rt["domains"], text)
        rt["pending"] = {"ctx": ctx, "ts": time.time(), "text": text}
        rt["pending_assessment"] = ctx.scratch.get("assessment") or None

        # Phase 2B / PR-G：关系类型分类（off-path，不阻塞请求）。低频 gated；
        # 经后台任务调 LLM 判关系语域、累积进壳层 store。绝不 inline await、不进 SDK 域。
        try:
            from sylanne_alpha.v2core import rel_register as _relreg
            if _relreg.should_classify(rt, time.time()):
                from sylanne_alpha.infra import safe_ensure_future
                safe_ensure_future(
                    _relreg.classify_and_store(plugin, session_key, event, text),
                    name="rel_register_classify",
                )
        except Exception as _exc:  # noqa: BLE001 - 分类失败绝不影响请求
            logger.debug("Sylanne rel_register dispatch skipped: %s", _exc)

        # 缺陷行为层（Wave 3）：选本轮该点燃的行为（互斥 + 不应期，状态存 rt 跨轮），
        # 命中则塞 ctx.scratch，由 fragment._behavior_line 渲染进 PINNED。零-LLM，吞错不阻断。
        try:
            from sylanne_alpha.v2core.behavior import select_behavior
            _lf = rt.setdefault("behavior_last_fired", {})
            _bsel = select_behavior(ctx.body, ctx.scratch, _lf, time.time())
            if _bsel:
                ctx.scratch["behavior_directive"] = _bsel["directive"]
                rt["last_behavior"] = {"id": _bsel["id"], "activation": _bsel["activation"],
                                       "ts": time.time()}   # 可观测留痕（WebUI 认知核页）
        except Exception as _bx:  # noqa: BLE001
            logger.debug("Sylanne behavior select skipped: %s", _bx)

        # 心象片段 → system prompt（主动脉：认知影响言语）
        from sylanne_alpha.v2core.fragment import build_mind_fragment
        frag = build_mind_fragment(ctx, rt["domains"])
        rt["last_fragment"] = frag   # 可观测留痕（WebUI 认知核页：LLM 看到什么，用户也看到什么）
        if frag:
            appender = getattr(
                getattr(plugin, "_llm_response_pipeline", None),
                "_append_request_prompt_fragment", None,
            )
            if callable(appender):
                appender(request, frag)
            else:
                current = str(getattr(request, "system_prompt", "") or "")
                request.system_prompt = f"{current}\n{frag}".strip()
            logger.debug("Sylanne v2core mind fragment injected: session=%s chars=%d",
                         session_key, len(frag))
    except Exception as exc:  # noqa: BLE001
        logger.error("Sylanne v2core request stage failed（继续旧管线）: %s", exc, exc_info=True)


def consume_pending_assessment(plugin: Any, session_key: str) -> dict[str, Any] | None:
    """legacy 请求管线在 host.on_request 前调用：取走本轮 v2core 评价（合并进 assessment）。

    一次性语义（取走即清），同步零 IO。开关关/无暂存 → None（legacy 行为不变）。
    """
    if not v2core_enabled(plugin):
        return None
    cache = getattr(plugin, "_v2core_runtimes", None)
    rt = cache.get(session_key) if isinstance(cache, dict) else None
    if not isinstance(rt, dict):
        return None
    a = rt.get("pending_assessment")
    rt["pending_assessment"] = None
    return a if isinstance(a, dict) and a else None


def consume_pending_quality(plugin: Any, session_key: str) -> float | None:
    """legacy 请求管线在构造 request tick event 前调用：取走上一轮自评的对话质量分。

    一次性语义（取走即清），同步零 IO。开关关/无暂存/陈旧 → None。注入进 event.values
    ["dialogue_quality"] → kernel.tick 透传 process → _drift_embodiment 自动漂移
    （canonical 滞后反馈：第 N 轮评分第 N+1 轮 request 拍生效）。

    时效（红队 wjqkfgh4i minor）：质量分是【上一轮回复】的滞后反馈，只对紧接的下一轮有意义。
    暂存格式 {"score": float, "ts": float}；若距上轮自评超 _QUALITY_TTL_S（如长间隔 gap、
    新话题），陈旧分丢弃返 None——否则陈旧高质量分注入不相关新话题，且 _drift_embodiment 的
    dt 巨大会放大这次错漂移。裸 float（旧格式/测试直塞）向后兼容，视为不过期。
    """
    if not v2core_enabled(plugin):
        return None
    cache = getattr(plugin, "_v2core_runtimes", None)
    rt = cache.get(session_key) if isinstance(cache, dict) else None
    if not isinstance(rt, dict):
        return None
    q = rt.get("pending_quality")
    rt["pending_quality"] = None
    if q is None:
        return None
    try:
        if isinstance(q, dict):
            ts = float(q.get("ts", 0.0) or 0.0)
            if ts > 0.0 and (time.time() - ts) > _QUALITY_TTL_S:
                return None  # 陈旧分（长间隔/新话题）→ 丢弃，不注入
            return float(q.get("score"))
        return float(q)  # 裸 float 向后兼容
    except (TypeError, ValueError):
        return None


# ===========================================================================
# 阶段二：response 钩子（DELIBERATE+EVOLVE，持锁）
# ===========================================================================

async def apply_v2core_response(plugin: Any, event: Any, response: Any) -> bool:
    """LLM 回复后的裁决阶段。

    返回 True  = 本层已终结本轮（仅 SILENT；跳过 legacy 防 no-ghost 复活装死）。
    返回 False = 回落 legacy 管线（SPEAK/FALLBACK 故意回落——sanitize/分段/观测
                 都在那边；以及开关关/异常的绞杀式回退）。
    """
    if not v2core_enabled(plugin):
        return False
    if response is None or _is_cron_event(event):
        return False
    try:
        from sylanne_alpha.v2core.contracts import ReplyKind

        session_key = plugin._session_key(event)
        draft_raw = str(getattr(response, "completion_text", "") or "")
        draft = draft_raw if draft_raw.strip() else None

        rt = _runtime_for(plugin, session_key)
        await _ensure_loaded(plugin, session_key, rt)

        # legacy realtime 拦截开启 = legacy 的 observe_response 会打 response tick
        cfg = getattr(plugin, "_config", None) or getattr(plugin, "config", None) or {}
        legacy_observes = bool(
            (cfg.get("sylanne_alpha_realtime_chat_enabled") or cfg.get("enable_realtime_chat"))
            and (cfg.get("sylanne_alpha_realtime_intercept_llm_response")
                 or cfg.get("realtime_chat_intercept_llm_response"))
        )

        async with _session_lock(plugin, session_key):
            # 续用 request 阶段的 PERCEPT 产物；缺失/过期则现场补跑（容错路径）
            pending = rt.get("pending")
            rt["pending"] = None
            ctx = None
            if isinstance(pending, dict) and (time.time() - pending.get("ts", 0.0)) < _PENDING_CTX_TTL:
                ctx = pending.get("ctx")
            if ctx is None:
                text = _user_text(plugin, event)
                ctx = rt["runner"].run_percept_stage(
                    session_key, event, text, domains=rt["domains"],
                )

            reply = rt["runner"].run_decision_stage(
                ctx, draft=draft,
                # SPEAK/FALLBACK 且 legacy 会观测 → 不打 tick（全局恰好一拍）；
                # SILENT 轮 legacy 被跳过 → 必须本层打。先裁决再定，由 runner 内部
                # 无法预知，故这里给"legacy 不观测"时恒打；SILENT 的修正见下。
                do_response_tick=not legacy_observes,
            )

            # 裁决留痕（可观测，运行态缓存非域状态）：WebUI 认知核页展示
            # "她最近一轮说/不说是怎么裁决的"。纯采集 ctx 已有产物，零写域。
            try:
                _decision: dict[str, Any] = {
                    "ts": time.time(),
                    "turn": int(getattr(ctx.body, "turns", 0) or 0),
                    "outcome": reply.kind.value,
                    "quality": ctx.scratch.get("quality") or "",
                }
                sil = ctx.scratch.get("silent")
                if isinstance(sil, dict):
                    _decision["silent_reason"] = str(sil.get("reason", "") or "")
                for _it in ctx.intents:
                    if getattr(_it, "source", "") == "ignition":
                        for _k in ("action", "g_speak", "g_hold", "g_reach",
                                   "express_at", "hold_floor", "eff_drive"):
                            if _k in _it.payload:
                                _decision[_k] = _it.payload[_k]
                        break
                rt["last_decision"] = _decision
            except Exception:  # noqa: BLE001
                pass   # 留痕失败绝不阻断回复

            # 对话质量分(float)滞后注入:本轮自评 → rt → 下轮 request tick event.values
            # ["dialogue_quality"] → process → _drift_embodiment 自动漂移(canonical 正道,
            # 替代已退役的 feedback_quality 后门)。仅 SPEAK 轮有质量分(_assess_quality 产)。
            # 带 ts:consume 时查时效,陈旧分(长间隔/新话题)丢弃,防错漂移不相关话题。
            try:
                _qs = ctx.scratch.get("quality_score")
                if isinstance(_qs, (int, float)):
                    rt["pending_quality"] = {"score": float(_qs), "ts": time.time()}
            except Exception:  # noqa: BLE001
                pass

            # Wave 4：重连 reflex_learn（层次1 反应式学习，零 LLM）——v1 清理后断了 caller。
            # 仅【真有回复发出去】的轮才触发：用本轮自评质量(弱信号，防 Goodhart 低权重) +
            # 下一轮续聊间隔(强信号，compute_behavior 自动从 mark_bot_reply 时刻推断)微调可学习
            # 门控偏置。接 agents.SelfCore（plugin._self_core，持进化档案/reflex），非 v2core 运行态。
            #
            # 出站判据（review wiring-correctness high）：SPEAK，或 FALLBACK 且有上游草稿（legacy
            # 真发草稿）。绝不在 SILENT、或 FALLBACK-空草稿（legacy empty_completion 静默丢弃、
            # 没有 bot 回复）上触发——否则 mark_bot_reply 记下幽灵回复，下一轮把用户的新消息误读成
            # "秒回上一条回复"，灌进虚假 +1 续聊奖励。这正是 SILENT 闸的本意，只是闸窄了一格。
            _will_send = (reply.kind is ReplyKind.SPEAK) or (
                reply.kind is ReplyKind.FALLBACK and draft is not None
            )
            if _will_send:
                try:
                    _sc = getattr(plugin, "_self_core", None)
                    if _sc is not None and hasattr(_sc, "reflex_learn"):
                        _q = ctx.scratch.get("quality_score")
                        _sc.reflex_learn(
                            session_key,
                            self_quality=float(_q) if isinstance(_q, (int, float)) else None,
                            behavior=None,
                        )
                except Exception:  # noqa: BLE001
                    pass  # 学习失败绝不阻断回复

            handled: bool
            if reply.kind is ReplyKind.SILENT:
                response.completion_text = ""
                # legacy 被跳过：若上面因 legacy_observes 没打 tick，这轮补打沉默知觉
                if legacy_observes:
                    rt["runner"].response_tick(ctx, reply)
                logger.info(
                    "Sylanne v2core SILENT | session=%s | reason=%s",
                    session_key, str((reply.meta or {}).get("reason", "") or "unspecified"),
                )
                handled = True
            elif reply.kind is ReplyKind.SPEAK and reply.parts:
                response.completion_text = "\n".join(p for p in reply.parts if p.strip())
                handled = False    # 故意回落：legacy 负责 sanitize/分段/观测
            else:  # FALLBACK
                if draft is not None:
                    response.completion_text = (
                        "\n".join(p for p in reply.parts if p.strip()) or draft_raw
                    )
                handled = False    # 上游空草稿：legacy 自己的 no-ghost 兜底接手

        logger.info(
            "Sylanne v2core turn: session=%s kind=%s handled=%s",
            session_key, reply.kind.value, handled,
        )
        _schedule_domain_save(plugin, session_key, rt["domains"], rt.get("behavior_last_fired"))
        return handled
    except Exception as exc:  # noqa: BLE001
        logger.error("Sylanne v2core bridge failed, 回落旧管线: %s", exc, exc_info=True)
        return False


# ===========================================================================
# 空闲触达咨询（主动桥 get_speech_decision 的增强源）
# ===========================================================================

async def merge_idle_reach_into_decision(
    plugin: Any, session_key: str, decision: dict[str, Any]
) -> dict[str, Any]:
    """若 v2core 空闲触达胜出，升格 decision.action=reach_out（live + scheduler 共用）。"""
    try:
        reach = await consult_idle_reach(plugin, session_key)
        decision["v2core_reach"] = reach
        if reach.get("reach") and decision.get("allowed", True):
            decision["action"] = "reach_out"
            decision["reason"] = (
                f"{decision.get('reason', '')}|v2core_reach".lstrip("|")
            )
    except Exception:
        pass
    return decision


async def consult_idle_reach(plugin: Any, session_key: str) -> dict[str, Any]:
    """空闲轮咨询：reach 想不想赢？零写、零 tick、零 LLM——纯读决策。

    消费者：ProactiveScheduler.get_speech_decision（外部主动桥轮询它）。
    返回 {"reach": bool, "g_reach": float, "action": str}；未启用/异常 → reach=False。
    """
    out = {"reach": False, "g_reach": 0.0, "action": "hold"}
    if not v2core_enabled(plugin):
        return out
    try:
        rt = _runtime_for(plugin, session_key)
        await _ensure_loaded(plugin, session_key, rt)
        runner = rt["runner"]
        ctx = runner.run_percept_stage(
            session_key, {"proactive": True}, "", domains=rt["domains"], idle=True,
        )
        ctx.scratch["proactive"] = True
        # 只跑 DELIBERATE（outreach/ignition），不 render、不 EVOLVE、不 tick——零副作用
        runner.run_deliberate_only(ctx)
        for it in ctx.intents:
            if it.source == "ignition":
                action = str(it.payload.get("action", "hold"))
                out["action"] = action
                out["reach"] = action == "reach"
                break
        for it in ctx.intents:
            if it.source == "outreach":
                out["g_reach"] = float(it.payload.get("g_reach", 0.0) or 0.0)
                break
        return out
    except Exception as exc:  # noqa: BLE001
        logger.debug("Sylanne v2core consult_idle_reach [%s]: %s", session_key, exc)
        return out


__all__ = [
    "v2core_enabled",
    "apply_v2core_request",
    "apply_v2core_response",
    "consume_pending_assessment",
    "consult_idle_reach",
    "merge_idle_reach_into_decision",
    "drain_pending_saves",
    "save_all_domains",
]
