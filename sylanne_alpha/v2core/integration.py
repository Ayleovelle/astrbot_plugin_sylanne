"""v2core ↔ 宿主管线桥接（Fable 重做版）—— 双阶段接管。

接线图（每条线都有实测的真实端点，无死信号）：

  on_llm_request（main.py 钩子）
    └→ apply_v2core_request：PERCEPT（只读）
         ├→ 心象片段 → request.system_prompt（她的认知影响她说什么——主动脉）
         ├→ 评价 assessment 暂存 → 请求管线在 host.on_request(assessment=…)
         │   合并入体（consume_pending_assessment；SDK 唯一 assessment 入口，零额外 tick）
         └→ ctx 暂存，response 阶段续用

  on_llm_response（main.py 钩子）
    └→ apply_v2core_response：DELIBERATE+EVOLVE（持会话锁）
         ├→ SILENT：清空 completion_text + D8 强制日志 + 本层补 response tick → True
         │   （抑制物理投递，防 no-ghost 兜底把刻意装死复活成文案）
         └→ SPEAK/FALLBACK：写回文本 → False，进入 delivery continuation：
             LLMResponsePipeline 继续 sanitize（[sylanne_*] 注入防御）、realtime 分段
             打字节奏、观测/记忆缓冲。v2core 决定说什么，投递管线负责只发送一次。
             response tick 归属：realtime 拦截开启时投递管线的 observe_response 打
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

v2core 是无条件运行的唯一逐轮认知内核；旧响应式 Agent 编排与逐轮 LLM 评价
已退役、删除，intent=="撒娇" 硬编码路径自然断粮。
任何异常 → 单轮继续下游投递管线，不阻断回复。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import random
import time
from typing import Any

from sylanne_alpha.scope_contracts import ResolvedScope, SessionScope
from sylanne_alpha.scope_runtime import ScopeMismatch, ScopeUnavailable

logger = logging.getLogger("astrbot_plugin_sylanne")

_DOMAIN_STATE_KEY_FMT = "sylanne_v2core_domains:{safe}"
_DOMAIN_STATE_VERSION = 1
_PENDING_CTX_TTL = 180.0      # request 阶段暂存 ctx 的有效期（秒）
_QUALITY_TTL_S = 600.0        # 对话质量分滞后反馈时效（秒）：超此视为陈旧/新话题，丢弃不注入
_DISPATCH_MOD_TTL = 30.0      # T3-01 派发调制器时效（秒）：同轮 response 处理内消费，
                              # 留量级余裕防跨轮陈旧值误用（rt 是跨轮持久字典）
_LAST_SILENT_TTL_S = 7200.0   # T2-01③ 认账留痕时效（秒）：超此不再喂给下一轮心象
_WINDDOWN_MIN_S = 15 * 60.0   # T2-03⑤ 收尾窗口下限（15 分钟，卡片给定量级）
_WINDDOWN_MAX_S = 45 * 60.0   # T2-03⑤ 收尾窗口上限（45 分钟）
_WINDDOWN_DEFAULT_S = 30 * 60.0  # 无法从 life_sim 读到活动时长时的默认窗口
_WINDDOWN_HOLD_BIAS = 0.30    # 窗口内叠加进 g_hold 的固定偏置（独立于 T2-01① 的语境食粮）
_NIGHT_WAKE_GAP_S = 3600.0    # T1-03③ 夜间"首条消息"判定：距上次请求超过此值才算重新搭话
_NIGHT_WAKE_CUE_PROB = 0.25   # T1-03③ 命中"首条夜间消息"时，附加"刚被叫醒"线索的概率

# Narrow compatibility anchor for old test/plugin stubs which do not expose a
# scoped registry.  Production tasks belong to PersonaRuntime instead.
_PENDING_SAVES: set[Any] = set()


def _safe_session_key(session_key: str) -> str:
    return str(session_key).replace("/", "_").replace("\\", "_")


def _kv(plugin: Any) -> Any:
    if hasattr(plugin, "get_kv_data") and hasattr(plugin, "put_kv_data"):
        return plugin
    return None


def _frozen_scope(event: Any) -> SessionScope | None:
    getter = getattr(event, "get_extra", None)
    if not callable(getter):
        return None
    try:
        resolved = getter("_sylanne_resolved_scope_v1")
    except Exception:
        return None
    if (
        type(resolved) is not ResolvedScope
        or resolved.private_scope_enabled is not True
        or type(resolved.scope) is not SessionScope
    ):
        return None
    return resolved.scope


def _requires_frozen_scope(plugin: Any) -> bool:
    """Main plugin owns a registry; its active V2 path never permits raw keys."""

    return getattr(plugin, "_scope_runtime_registry", None) is not None


def _runtime_context_for_event(
    plugin: Any, event: Any
) -> tuple[SessionScope | None, str, dict[str, Any]] | None:
    """Return exact scoped state, or the named legacy reader for narrow stubs."""

    scope = _frozen_scope(event)
    if scope is not None:
        return scope, scope.storage_token, _runtime_for_scope(plugin, scope)
    if _requires_frozen_scope(plugin):
        return None
    session_key = plugin._session_key(event)
    if not isinstance(session_key, str) or not session_key:
        return None
    return None, session_key, _legacy_runtime_for_raw_session(plugin, session_key)


def _session_lock(plugin: Any, session_key: str) -> Any:
    """取会话锁（与请求观测/自驱心跳同一把——S5 串行义务的落点）。

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
        # math.isfinite：丢弃 NaN/±inf——NaN 会让不应期比较恒 False(门常开)、+inf 永久压制，
        # 损坏的持久化 ts 不得废掉门控（sourcery review）。
        return {str(k): float(v) for k, v in blf.items()
                if isinstance(v, (int, float)) and math.isfinite(v)}
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
        # 写路径同样滤掉非有限 ts，存下来的不应期表保证全是有限值（与读路径对称）。
        blob["_behavior_last_fired"] = {str(k): float(v) for k, v in behavior_last_fired.items()
                                        if isinstance(v, (int, float)) and math.isfinite(v)}
    try:
        key = _DOMAIN_STATE_KEY_FMT.format(safe=_safe_session_key(session_key))
        await kv.put_kv_data(key, blob)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Sylanne v2core 域状态写入失败 [%s]: %s", session_key, exc)


async def _save_scoped_domains(
    plugin: Any,
    scope: SessionScope,
    domains: dict[str, Any],
    behavior_last_fired: dict[str, float] | None = None,
) -> None:
    """Persist only while this exact scope generation is still live.

    The per-storage-token lock provides write ordering across generations.  An old
    callback that resumes after a replacement generation has been installed sees
    ``is_live_session == False`` and cannot overwrite its successor's snapshot.
    """

    registry = getattr(plugin, "_scope_runtime_registry", None)
    if registry is None or not registry.is_live_session(scope):
        return
    try:
        persona_runtime = registry.for_scope(scope)
    except ScopeMismatch:
        return
    lock = persona_runtime.v2core_save_locks.get(scope.storage_token)
    if lock is None:
        lock = asyncio.Lock()
        persona_runtime.v2core_save_locks[scope.storage_token] = lock
    async with lock:
        if not registry.is_live_session(scope):
            return
        await _save_domains(
            plugin,
            scope.storage_token,
            domains,
            behavior_last_fired,
        )


def _pending_save_bucket(plugin: Any, scope: SessionScope | None) -> set[Any] | None:
    if scope is None:
        return None if _requires_frozen_scope(plugin) else _PENDING_SAVES
    registry = getattr(plugin, "_scope_runtime_registry", None)
    if registry is None or not registry.is_live_session(scope):
        return None
    try:
        return registry.for_scope(scope).v2core_pending_saves
    except ScopeMismatch:
        return None


def _schedule_domain_save(
    plugin: Any,
    scope_or_session: SessionScope | str,
    domains: dict[str, Any],
    behavior_last_fired: dict[str, float] | None = None,
) -> None:
    """Fire-and-forget persistence owned by an exact Persona runtime.

    Raw session keys are retained only for narrow registry-free compatibility
    stubs.  A real plugin without a frozen SessionScope deliberately schedules
    nothing rather than guessing an owner.
    """

    scope = scope_or_session if type(scope_or_session) is SessionScope else None
    if scope is None:
        if _requires_frozen_scope(plugin) or not isinstance(scope_or_session, str):
            return
        session_key = scope_or_session
        coro = _save_domains(plugin, session_key, domains, behavior_last_fired)
    else:
        session_key = scope.storage_token
        coro = _save_scoped_domains(plugin, scope, domains, behavior_last_fired)
    bucket = _pending_save_bucket(plugin, scope)
    if bucket is None:
        coro.close()
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        task = loop.create_task(coro)
        bucket.add(task)
        task.add_done_callback(bucket.discard)
        if scope is not None:
            registry = getattr(plugin, "_scope_runtime_registry", None)
            if registry is None or not registry.track_session_task(scope, task):
                task.cancel()
    else:
        try:
            asyncio.run(coro)
        except Exception:  # noqa: BLE001
            coro.close()


async def drain_pending_saves(plugin: Any | None = None, timeout: float = 5.0) -> None:
    """停机/卸载前排干在途域状态落盘（main.terminate 在 cancel 后台任务【之前】调用）。"""
    scoped_plugin = plugin is not None and _requires_frozen_scope(plugin)
    if scoped_plugin:
        pending = [
            task
            for runtime in plugin._scope_runtime_registry.live_persona_runtimes()
            for task in runtime.v2core_pending_saves
            if not task.done()
        ]
    else:
        pending = [t for t in _PENDING_SAVES if not t.done()]
    if not pending:
        return
    try:
        await asyncio.wait(pending, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Sylanne v2core drain saves: %s", exc)


async def save_all_domains(plugin: Any) -> None:
    """终扫：把所有活跃会话的域状态同步落盘一遍（terminate 兜底）。"""
    registry = getattr(plugin, "_scope_runtime_registry", None)
    if registry is not None:
        for persona_runtime in registry.live_persona_runtimes():
            for rt in list(persona_runtime.v2core_runtimes.values()):
                if not isinstance(rt, dict):
                    continue
                scope = rt.get("scope")
                domains = rt.get("domains")
                if (
                    type(scope) is not SessionScope
                    or not isinstance(domains, dict)
                    or not domains
                    or not registry.is_live_session(scope)
                ):
                    continue
                try:
                    await _save_scoped_domains(
                        plugin,
                        scope,
                        domains,
                        rt.get("behavior_last_fired"),
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Sylanne v2core scoped 终扫落盘失败 [%s]: %s", scope.storage_token, exc)
        return
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

def _runtime_for_scope(plugin: Any, scope: SessionScope) -> dict[str, Any]:
    """Build/read V2 state from the exact frozen ``scope.storage_token``."""

    if type(scope) is not SessionScope:
        raise ScopeUnavailable("v2core requires a frozen SessionScope")
    registry = getattr(plugin, "_scope_runtime_registry", None)
    if registry is None:
        raise ScopeUnavailable("scoped v2core registry is unavailable")
    # This rejects an old scope generation before it can reuse a same-token V2
    # cache entry from a newer session incarnation.
    registry.exact_session(scope)
    persona_runtime = registry.for_scope(scope)
    return _build_runtime(
        plugin,
        scope.storage_token,
        persona_runtime.v2core_runtimes,
        scope=scope,
    )


def runtime_for(plugin: Any, scope: SessionScope) -> dict[str, Any]:
    """Public exact-scope V2 runtime lookup used by scoped callers/tests."""

    return _runtime_for_scope(plugin, scope)


def _legacy_runtime_for_raw_session(plugin: Any, session_key: str) -> dict[str, Any]:
    """Explicit compatibility reader for test stubs without a scope registry."""

    cache = getattr(plugin, "_v2core_runtimes", None)
    if cache is None:
        cache = {}
        plugin._v2core_runtimes = cache
    return _build_runtime(plugin, session_key, cache, scope=None)


def _runtime_from_scope_or_legacy(
    plugin: Any, scope_or_session: SessionScope | str
) -> dict[str, Any] | None:
    """Resolve an explicit scope, or a named registry-free compatibility reader."""

    if type(scope_or_session) is SessionScope:
        try:
            return _runtime_for_scope(plugin, scope_or_session)
        except ScopeMismatch:
            return None
    if _requires_frozen_scope(plugin) or not isinstance(scope_or_session, str):
        return None
    return _legacy_runtime_for_raw_session(plugin, scope_or_session)


def _runtime_cache_key(storage_token: str, scope: SessionScope | None) -> str:
    """Keep same-token replacement generations as independent V2 runtimes."""

    if scope is None:
        return storage_token
    return f"{storage_token}\x1f{scope.scope_generation}"


def _build_runtime(
    plugin: Any,
    storage_token: str,
    cache: dict[str, dict[str, Any]],
    *,
    scope: SessionScope | None,
) -> dict[str, Any]:
    """Construct one V2 bundle; caller already selected its only legal cache."""
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
    from sylanne_alpha.v2core.domains.adaptation import AdaptationDomain
    from sylanne_alpha.v2core.domains.distillation import DistillationDomain
    from sylanne_alpha.v2core.domains.emotion import EmotionLedger
    from sylanne_alpha.v2core.domains.focus import FocusDomain
    from sylanne_alpha.v2core.domains.memory import MemoryDomain
    from sylanne_alpha.v2core.domains.narrative_self import NarrativeSelfDomain
    from sylanne_alpha.v2core.domains.user_model import UserModelDomain
    from sylanne_alpha.v2core.renderer import DefaultRenderer
    from sylanne_alpha.v2core.self_core import SelfCore
    from sylanne_alpha.v2core.turn_runner import TurnRunner

    cache_key = _runtime_cache_key(storage_token, scope)
    rt = cache.get(cache_key)
    if rt is not None:
        return rt

    if scope is None:
        host = plugin._host(storage_token)
    else:
        host_getter = getattr(plugin, "_host_for_scope", None)
        if not callable(host_getter):
            raise ScopeUnavailable("scoped host reader is unavailable")
        host = host_getter(scope)
    bp = CanonicalKernelBodyPort.from_host(host, storage_token)
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
        # Wave 6 地基（PR-A）：进 dict 即随 _save/_load_domains 自动持久化（blob 子键
        # 'adaptation'，不撞 _version/_behavior_last_fired）；学习/注入随 PR-B/C/D 落地。
        "adaptation": AdaptationDomain(),
    }
    try:
        ms_getter = (
            getattr(plugin, "_memory_system_for_scope", None)
            if scope is not None
            else getattr(plugin, "_memory_system_for_session", None)
        )
        if callable(ms_getter):
            ms = ms_getter(scope) if scope is not None else ms_getter(storage_token)
            if ms is not None:
                domains["memory"] = MemoryDomain(ms)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Sylanne v2core: memory domain unavailable: %s", exc)

    rt = {
        "runner": TurnRunner(sc, DefaultRenderer()),
        "domains": domains,
        "body_port": bp,
        "pending": None,              # request 阶段暂存的 ctx
        "pending_assessment": None,   # 待请求 tick 合并的评价
        "pending_quality": None,      # 待下轮 request tick 注入的对话质量分(float, 滞后反馈)
        "loaded": False,
        "storage_token": storage_token,
        "scope_generation": scope.scope_generation if scope is not None else None,
        "scope": scope,
    }
    cache[cache_key] = rt
    return rt


async def _ensure_loaded(plugin: Any, session_key: str, rt: dict[str, Any]) -> None:
    if not rt.get("loaded"):
        rt["behavior_last_fired"] = await _load_domains(plugin, session_key, rt["domains"])
        rt["loaded"] = True


def _is_cron_event(event: Any) -> bool:
    """定时任务（cron）的 LLM 回复是内部总结：v2core 不处理（与请求管线同判据）——
    否则内部总结文本会污染用户模型/蒸馏的学习流。"""
    pm = getattr(event, "platform_meta", None)
    if pm is not None and str(getattr(pm, "name", "") or "") == "cron":
        return True
    umo = str(getattr(event, "unified_msg_origin", "") or "")
    return umo.startswith("cron")


# leg-2a：与 llm_request_pipeline._MIN_HISTORY_TURNS_FOR_ANCHOR 对齐。此处独立定义避免
# integration ← pipeline 的循环导入（pipeline 已 import 本模块的 peek_percept_recalled_texts）。
_MIN_HISTORY_TURNS_FOR_ANCHOR = 2


def _history_present(request: Any) -> bool:
    """req.contexts 是否有 ≥阈值 条带非空文本的真实 user/assistant 轮（leg-2a）。

    PERCEPT 跑在 Step 0（早于请求管线清洗），看到的是原始 contexts——泄漏注入会让计数
    略偏高，即偏向"历史在场"、少压制，是安全方向（只在明显薄历史时才压幽灵）。
    """
    contexts = getattr(request, "contexts", None)
    if not isinstance(contexts, list):
        return False
    n = 0
    for m in contexts:
        if isinstance(m, dict) and m.get("role") in ("user", "assistant"):
            content = m.get("content")
            if isinstance(content, str):
                if content.strip():
                    n += 1
            elif isinstance(content, list):
                if any(
                    isinstance(b, dict) and b.get("type") == "text"
                    and str(b.get("text") or "").strip()
                    for b in content
                ):
                    n += 1
        if n >= _MIN_HISTORY_TURNS_FOR_ANCHOR:
            return True
    return False


async def _percept_recall(
    plugin: Any,
    ctx: Any,
    domains: dict[str, Any],
    text: str,
    history_present: bool = True,
) -> None:
    """PERCEPT 拍召回（T1-6/7）：当轮 prompt 可消费，含 embedding。"""
    memory = domains.get("memory")
    if memory is None or not (text or "").strip():
        return
    try:
        # #29：PERCEPT 召回门控同样吃 memory.intimacy_threshold 进化偏置（与 DELIBERATE
        # 召回同源，gate 一致）。ctx 由 run_percept_stage 注入了 scratch["evo_delta"]。
        if not memory.intimacy_ok(ctx.body, bias=ctx.evo_bias("memory", "intimacy_threshold")):
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
                        # 热路径（PERCEPT，LLM 调用前）：embedding provider 若挂起会卡死整条
                        # 召回 → 用户消息无回复。超时兜底，挂起→TimeoutError→下面 except→无
                        # embedding 降级召回，绝不让一个慢 provider 堵死回复。
                        query_embedding = await asyncio.wait_for(
                            provider.get_embedding(text[:100]), timeout=5.0
                        )
                except Exception:
                    query_embedding = None
        results = memory.recall(
            text, warmth=ctx.current_warmth, limit=limit,
            query_embedding=query_embedding, history_present=history_present,
        )
        if results:
            ctx.scratch["recalled"] = results
    except Exception:
        pass


def peek_percept_recalled_texts(
    plugin: Any, scope_or_session: SessionScope | str
) -> set[str]:
    """只读窥视本轮 PERCEPT 已召回的记忆原文集合（不新建/不触发 v2core 运行态）。

    供请求管线 [记忆参考] 格式化前做同轮跨路径去重：PERCEPT
    （_percept_recall，本模块）与 llm_request_pipeline._prepare_memory_context
    两条召回路径在同一轮都会跑，同一条记忆可能被两边都命中，重复注入进同一个 prompt。

    只 peek 已存在的 `plugin._v2core_runtimes` 缓存条目——绝不调用 `_runtime_for`
    新建（本轮 PERCEPT 未跑时缓存不存在，返回空集，请求管线行为不变）。
    任何环节异常一律返回空集（fail-open：宁可不去重，也不能因为这个旁路影响
    请求管线的记忆注入主路径）。
    """
    try:
        if type(scope_or_session) is SessionScope:
            registry = getattr(plugin, "_scope_runtime_registry", None)
            if registry is None or not registry.is_live_session(scope_or_session):
                return set()
            cache = registry.for_scope(scope_or_session).v2core_runtimes
            rt = cache.get(
                _runtime_cache_key(
                    scope_or_session.storage_token,
                    scope_or_session,
                )
            )
        else:
            if _requires_frozen_scope(plugin) or not isinstance(scope_or_session, str):
                return set()
            cache = getattr(plugin, "_v2core_runtimes", None)
            rt = cache.get(scope_or_session) if isinstance(cache, dict) else None
        if not isinstance(rt, dict):
            return set()
        pending = rt.get("pending")
        if not isinstance(pending, dict):
            return set()
        ctx = pending.get("ctx")
        scratch = getattr(ctx, "scratch", None) if ctx is not None else None
        recalled = scratch.get("recalled") if isinstance(scratch, dict) else None
        if not isinstance(recalled, list):
            return set()
        out: set[str] = set()
        for r in recalled:
            if isinstance(r, dict):
                t = str(r.get("text") or "").strip()
                if t:
                    out.add(t)
        return out
    except Exception:
        return set()


def _evo_provider(plugin: Any, session_key: str):
    """构造本会话的进化偏置 provider：callable(agent, key) -> float（#29 输出侧接通）。

    背后是 agents.SelfCore.evo_delta（plugin._self_core，持 EvolutionStore：反射 delta +
    反思 reflection_bias，自带 ±0.20 总 cap）。注入 ctx.scratch["evo_delta"]，live 门控
    （IgnitionArbiter / MemoryDomain.intimacy_ok）经 ctx.evo_bias 读取并二次钳位。

    _self_core 缺失（未装/旧路径）或读取异常 → 返回 None / 0.0：门控落回纯人格基线，
    零行为变化（绝不因学习层缺位而阻断或改写回复）。
    """
    sc = getattr(plugin, "_self_core", None)
    if sc is None or not hasattr(sc, "evo_delta"):
        return None

    def _get(agent: str, key: str) -> float:
        try:
            return float(sc.evo_delta(session_key, agent, key))
        except Exception:  # noqa: BLE001
            return 0.0

    return _get


def _apply_v2core_feature_flags(ctx: Any, plugin: Any) -> None:
    """T2-01/T2-03 特性开关经 ctx.scratch 注入（与 evo_delta provider 同款模式）：
    v2core 能力/领域是纯函数，不知道"我在插件里"，只读 scratch 里的布尔值——
    保持 ignition.py / behavior.py 等模块零宿主依赖。默认关＝对应能力恒读到
    False，行为与关闭该模块前完全一致（零变化）。
    """
    cfg = getattr(plugin, "_config", None) or getattr(plugin, "config", None) or {}
    ctx.scratch["deliberate_silence_enabled"] = bool(
        cfg.get("sylanne_alpha_deliberate_silence_enabled", False)
    )
    ctx.scratch["winddown_enabled"] = bool(
        cfg.get("sylanne_alpha_winddown_enabled", False)
    )
    ctx.scratch["night_rhythm_enabled"] = bool(
        cfg.get("sylanne_alpha_night_rhythm_enabled", False)
    )


def _apply_burst_cue_scratch(event: Any, ctx: Any) -> None:
    """T2-04②：连发合并线索——llm_request_pipeline 碎片防抖 winner 在合并 N>=2 条
    碎片时，往 event 上打了一个瞬态属性 `_sylanne_burst_count`（不跨轮持久化，下一
    轮 event 是新对象自动失效）。这里转成 scratch 键供 fragment 渲染一句"挑要紧的
    接"提示，防止 LLM 逐句逐点公式化回应。始终开（T2-04 属 always-on 增强，不经
    feature flag 门控），无标记/异常值 → 不设键，行为与本能力不存在时一致。
    """
    try:
        burst_n = int(getattr(event, "_sylanne_burst_count", 0) or 0)
    except (TypeError, ValueError):
        return
    if burst_n >= 2:
        ctx.scratch["burst_cue"] = True


def _apply_winddown_window_scratch(ctx: Any, rt: dict[str, Any]) -> None:
    """T2-03⑤：收尾窗口生效期——不管本轮是否刚点燃 winddown，只要还在窗口内就把临时
    hold 偏置 + 派发预延迟喂进 scratch（ignition.context_hold_food 之外的独立加项 +
    _compose_dispatch_modulators 的 extra_predelay，见二者读取处）。窗口外/关闭 →
    键不出现，两处消费者的 .get(..., 0.0) 天然回落中性。

    两个调用点都要跑（request 阶段的正常 ctx，与 response 阶段 pending 过期后现场
    补跑的 ctx）——否则 pending TTL（180s）过期时重建的 ctx 会漏挂这份偏置，窗口内
    却读到中性值（红队 finding：单点注入在慢响应场景下会失效）。
    """
    try:
        _until = rt.get("winddown_until")
        if isinstance(_until, (int, float)) and time.time() < float(_until):
            ctx.scratch["winddown_active"] = True
            ctx.scratch["winddown_hold_bias"] = _WINDDOWN_HOLD_BIAS
    except Exception:  # noqa: BLE001
        pass


def _apply_night_texture_scratch(
    plugin: Any, session_key: str, ctx: Any, rt: dict[str, Any], text: str, now: float,
) -> None:
    """T1-03①③：免打扰时段给心象加一句"深夜话少"的软纹理线索；距上次请求超过
    _NIGHT_WAKE_GAP_S 的首条夜间消息，小概率再叠一句"刚被叫醒"。

    豁免（②）：incoming 文本命中孤独/紧急关键词时，本函数整体跳过——不产生任何
    scratch 键，本轮心象与"总开关关闭"时完全一致（红队铁律：这类消息不能被
    "深夜该少说话"误伤）。只更新 rt 里的时间戳（供下一条非豁免消息算 gap），
    不写任何 cue。

    调用前提：ctx.scratch["night_rhythm_enabled"] 已为真（调用方保证）。
    """
    from sylanne_alpha.proactive_bridge import is_night_fast_reply_exempt

    prev_time = rt.get("night_last_request_time")
    rt["night_last_request_time"] = now
    if is_night_fast_reply_exempt(text):
        return
    bridge = getattr(plugin, "_proactive_bridge", None)
    if bridge is None:
        return
    try:
        sid = bridge._resolve_origin(session_key)
        in_quiet = bool(bridge._in_quiet_hours(sid))
    except Exception:
        in_quiet = False
    if not in_quiet:
        return
    ctx.scratch["night_texture_cue"] = True
    gap = 0.0
    if isinstance(prev_time, (int, float)) and prev_time > 0.0:
        gap = now - float(prev_time)
    if gap > _NIGHT_WAKE_GAP_S and random.random() < _NIGHT_WAKE_CUE_PROB:
        ctx.scratch["night_wake_cue"] = True


def _hash_text(text: str) -> str:
    """T2-01③：认账留痕只存文本指纹，不存原文（rt 是跨轮 RAM 态，没必要多留一份原文）。"""
    import hashlib
    return hashlib.sha256((text or "").encode("utf-8", "ignore")).hexdigest()[:12]


def _maybe_soften_silence(plugin: Any, ctx: Any) -> tuple[Any, str]:
    """T2-01②：DeliberateSilence 作第二沉默源，把"彻底装死"软化成极简回应。

    只在【被问】（有本轮用户文本）时考虑——空闲/主动轮的静默语义不动。复用
    realtime_dispatch.DeliberateSilence（此前零调用方，见其模块内 review 记录）：
    读同一份 body 快照的 warmth/tension/void_pressure，与 IgnitionArbiter 的 hold
    决策各自独立、互不覆盖对方判据——它只决定"这次沉默要不要留一个极简音"。

    返回 (minimal_reply_or_None, ds_reason)：
    - should_be_silent=False → (None, "")：DeliberateSilence 不掺和，保留原判据的
      SILENT，last_silent 仍会用 ignition 自己的 reason 留痕。
    - should_be_silent=True 但 get_minimal_response 为 None（如"digesting"，故意
      彻底沉默）→ (None, reason)：不软化，但把更贴切的理由回传供留痕/下轮心象。
    - 两者都命中 → (Reply.speak(minimal, mode="minimal_silence"), reason)。
    """
    if not (ctx.text or "").strip():
        return None, ""
    ds_factory = getattr(getattr(plugin, "_realtime_dispatch", None), "deliberate_silence", None)
    if not callable(ds_factory):
        return None, ""
    try:
        ds = ds_factory()
        body = ctx.body
        should, reason = ds.should_be_silent(
            float(body.warmth), float(body.tension), float(body.void_pressure)
        )
        if not should:
            return None, ""
        minimal = ds.get_minimal_response(reason)
        if not minimal:
            return None, reason
        from sylanne_alpha.v2core.contracts import Reply
        return Reply.speak(minimal, mode="minimal_silence", silent_reason=reason), reason
    except Exception:  # noqa: BLE001
        return None, ""


def _start_winddown_window(
    plugin: Any, session_key: str, rt: dict[str, Any], sim: Any, now: float,
) -> None:
    """T2-03⑤⑥：behavior.py 选中 winddown 那一刻——开收尾窗口 + 排定窗口结束后的
    返场触达。窗口时长（分钟级，15–45min）优先取 life_sim 当前活动 event_type 估算
    的典型时长（见 LifeSimulator.current_activity_duration_min），读不到（无事件/
    类型未知）→ 默认 30min（卡片"if available"的诚实兜底）。
    """
    duration_s = _WINDDOWN_DEFAULT_S
    if sim is not None:
        try:
            dur_min = sim.current_activity_duration_min()
            if dur_min is not None:
                duration_s = max(_WINDDOWN_MIN_S, min(_WINDDOWN_MAX_S, float(dur_min) * 60.0))
        except Exception:  # noqa: BLE001
            pass
    rt["winddown_until"] = now + duration_s
    rt["winddown_return_notified"] = False   # 新窗口开了，允许下次窗口结束再提醒一次

    scope = rt.get("scope")
    if type(scope) is SessionScope:
        registry = getattr(plugin, "_scope_runtime_registry", None)
        if registry is None or not registry.is_live_session(scope):
            return
        coro = _winddown_return_after(plugin, scope, duration_s)
        try:
            task = asyncio.get_running_loop().create_task(coro)
        except RuntimeError:
            coro.close()
            return
        registry.track_session_task(scope, task)
        return

    scheduler = getattr(getattr(plugin, "_realtime_dispatch", None), "schedule_background_task", None)
    if callable(scheduler):
        coro = _winddown_return_after(plugin, session_key, duration_s)
        try:
            scheduler(coro, label="winddown_return")
        except Exception:  # noqa: BLE001
            # MINOR 修复（红队 finding）：调度失败（如 ensure_future 抛异常）时 coro
            # 从未被 await 过——不 close 会在 GC 时炸出 "coroutine was never awaited"
            # RuntimeWarning。窗口本身仍生效，返场退化到 ⑥ 的 fragment 兜底。
            coro.close()


async def _winddown_return_after(
    plugin: Any,
    scope_or_session: SessionScope | str,
    delay_s: float,
) -> None:
    """T2-03⑥：收尾窗口结束后尝试主动"回来接着聊"。

    background-task 模式（realtime_dispatch.schedule_background_task 同款：异常吞掉、
    完成即从 plugin._background_tasks 摘除；main.terminate() 停机时会 cancel 该表，
    这里的 asyncio.sleep 天然可被取消——不留悬挂任务）。复用既有主动桥
    （available/should_dispatch_now/dispatch），吃它全部 quiet_hours/min_interval
    冷却与"大饼未装"静默降级——不新开一套触达阀门（红队命门：别造第二个主动通道）。
    桥不可用/被冷却压住 → 直接放弃，下一条真实消息走 apply_v2core_request 里的
    ⑥ 退化路径（winddown_return_cue）兜底。
    """
    try:
        await asyncio.sleep(max(0.0, delay_s))
    except asyncio.CancelledError:
        raise
    scope = scope_or_session if type(scope_or_session) is SessionScope else None
    if scope is not None:
        registry = getattr(plugin, "_scope_runtime_registry", None)
        if registry is None or not registry.is_live_session(scope):
            return
        binder = getattr(plugin, "_bind_runtime_for_scope", None)
        if not callable(binder):
            return
        session_key = scope.storage_token
    else:
        if _requires_frozen_scope(plugin) or not isinstance(scope_or_session, str):
            return
        session_key = scope_or_session

    async def _dispatch_return() -> None:
        bridge = getattr(plugin, "_proactive_bridge", None)
        if bridge is None or not bridge.available():
            return
        allowed, _reason = bridge.should_dispatch_now(session_key)
        if not allowed:
            return
        motivation = bridge.build_motivation_text(
            "忙完手头的事，回来接着聊", "松了口气，想起来刚才聊到哪了",
            reason_code="life_rhythm", session_key=session_key,
        )
        await bridge.dispatch(session_key, motivation)

    try:
        if scope is None:
            await _dispatch_return()
        else:
            with binder(scope):
                await _dispatch_return()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Sylanne T2-03 winddown 返场触达失败 [%s]: %s", session_key, exc)


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
    if request is None or _is_cron_event(event):
        return
    try:
        runtime_context = _runtime_context_for_event(plugin, event)
        if runtime_context is None:
            return
        scope, session_key, rt = runtime_context
        text = _user_text(plugin, event)
        if not text.strip():
            return
        await _ensure_loaded(plugin, session_key, rt)

        ctx = rt["runner"].run_percept_stage(
            session_key, event, text, domains=rt["domains"],
            evo_delta=_evo_provider(plugin, session_key),
        )
        _apply_v2core_feature_flags(ctx, plugin)
        # leg-2a：历史缺失/病态轮压制 PERCEPT 侧零相关近期召回（幽灵）——与请求管线同门，
        # 覆盖无条件运行的 v2core 主注入路径。
        await _percept_recall(
            plugin, ctx, rt["domains"], text,
            history_present=_history_present(request),
        )
        rt["pending"] = {"ctx": ctx, "ts": time.time(), "text": text}
        rt["pending_assessment"] = ctx.scratch.get("assessment") or None

        # T2-04②：连发合并线索。始终开（T2-04 属 always-on 增强，不经 feature flag 门控）。
        _apply_burst_cue_scratch(event, ctx)

        # T2-01③：事后认账——上一轮若装死/软化沉默过，本轮心象带一句"刚才看到了
        # 没说话"的线索（一次性：不管本轮是否真的用上，用过就清；TTL 兜底防陈旧
        # 线索赖在 rt 里跨会话空窗期）。两个开关任一打开都可能产生过 last_silent
        # 留痕（deliberate_silence 直接命中 / winddown 窗口内被迫 hold），故都读；
        # 都关时 rt 里即便意外有残留也不会被消费，行为与两功能都不存在时一致。
        if ctx.scratch.get("deliberate_silence_enabled") or ctx.scratch.get("winddown_enabled"):
            try:
                _ls = rt.get("last_silent")
                if isinstance(_ls, dict):
                    _age = time.time() - float(_ls.get("ts", 0.0) or 0.0)
                    if 0.0 <= _age <= _LAST_SILENT_TTL_S:
                        ctx.scratch["last_silent_cue"] = str(_ls.get("reason", "") or "")
                    rt["last_silent"] = None
            except Exception:  # noqa: BLE001
                pass

        # T2-03⑥ 退化路径：收尾窗口已经过去、还没通知过 → 给下一轮心象一次性"刚忙完"
        # 提示。不管上面后台返场触达（_winddown_return_after）有没有真的送达都会触发
        # ——桥不可用/被冷却压住时，这是唯一的兜底（卡片原话："退化成下一条消息带
        # 刚忙完线索"）；桥若已经先一步主动发了消息，这条线索也只是让下一句更自然，
        # 无害。一次性：notified 置真后不再重复。
        if ctx.scratch.get("winddown_enabled"):
            try:
                _wu = rt.get("winddown_until")
                if (isinstance(_wu, (int, float)) and time.time() >= float(_wu)
                        and not rt.get("winddown_return_notified")):
                    ctx.scratch["winddown_return_cue"] = True
                    rt["winddown_return_notified"] = True
            except Exception:  # noqa: BLE001
                pass

        # T1-03①③ 夜间温和版：免打扰时段给心象加"深夜话少"软纹理线索（+小概率
        # "刚被叫醒"）。孤独/紧急关键词豁免整段效果，与 response 阶段的延迟/cps
        # 豁免（llm_response_pipeline._night_rhythm_active）共用同一份判定口径。
        if ctx.scratch.get("night_rhythm_enabled"):
            try:
                _apply_night_texture_scratch(plugin, session_key, ctx, rt, text, time.time())
            except Exception as _nx:  # noqa: BLE001
                logger.debug("Sylanne night rhythm cue skipped: %s", _nx)

        # Phase 2B / PR-G：关系类型分类（off-path，不阻塞请求）。低频 gated；
        # 经后台任务调 LLM 判关系语域、累积进壳层 store。绝不 inline await、不进 SDK 域。
        if not _requires_frozen_scope(plugin):
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

        # 生活底色（Wave 5）+ T2-03 去忙收尾信号：两者都读同一个 _life_simulator，
        # 合并一次取用（life_sim_signals 必须在下面 select_behavior 之前就绪，behavior.py
        # 的 winddown 激活读它）。只读、零阻断；未装/未开 → 两个 scratch 键都不出现。
        _sim = None
        try:
            _sim = getattr(plugin, "_life_simulator", None)
            if _sim is not None and getattr(_sim, "enabled", False):
                _cue = _sim.undertone_cue()
                if _cue:
                    ctx.scratch["life_cue"] = _cue
                if ctx.scratch.get("winddown_enabled"):
                    ctx.scratch["life_sim_signals"] = {
                        "phase": _sim.state.world.phase,
                        "energy": float(_sim.state.world.energy),
                        "focus": float(_sim.state.world.focus),
                        "interruptibility": float(_sim.interruptibility()),
                    }
        except Exception as _lx:  # noqa: BLE001
            logger.debug("Sylanne life cue / winddown signals skipped: %s", _lx)
            _sim = None

        # 缺陷行为层（Wave 3）+ T2-03④ 去忙收尾：选本轮该点燃的行为（互斥 + 不应期，
        # 状态存 rt 跨轮），命中则塞 ctx.scratch，由 fragment._behavior_line 渲染进
        # PINNED。零-LLM，吞错不阻断。
        try:
            from sylanne_alpha.v2core.behavior import select_behavior
            _lf = rt.setdefault("behavior_last_fired", {})
            _now = time.time()   # 一次取时：选择器写入不应期 ts 与下方留痕 ts 一致（sourcery review）
            _bsel = select_behavior(ctx.body, ctx.scratch, _lf, _now)
            if _bsel:
                ctx.scratch["behavior_directive"] = _bsel["directive"]
                # T3-01：本轮点燃行为的派发力学调制，塞 scratch 供 apply_v2core_response
                # 读出后经 rt 转手给投递路径（llm_response_pipeline 没有 ctx）。
                ctx.scratch["behavior_modulators"] = _bsel.get("modulators") or {}
                rt["last_behavior"] = {"id": _bsel["id"], "activation": _bsel["activation"],
                                       "ts": _now}   # 可观测留痕（WebUI 认知核页）
                if _bsel["id"] == "winddown":
                    _start_winddown_window(plugin, session_key, rt, _sim, _now)
        except Exception as _bx:  # noqa: BLE001
            logger.debug("Sylanne behavior select skipped: %s", _bx)

        _apply_winddown_window_scratch(ctx, rt)

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

        # emotion_spirit 状态消费（Design B：只读、观察式背景；未装/未开/未激活 → no-op，
        # 零行为变化）。注入在心象片段之后，复用同一 appender。三条腿（persona 重申/拉状态/
        # 渲染）都在 bridge 内自查 live presence + active，同源门控（红队 lifecycle）。独立
        # try 包裹：emotion_spirit 侧任何失败都不波及上面的心象片段注入与主请求。
        try:
            es_bridge = getattr(plugin, "_emotion_spirit_bridge", None)
            es_on = bool((getattr(plugin, "config", None) or {}).get(
                "sylanne_alpha_emotion_spirit_bridge_enabled", False))
            if es_bridge is not None and es_on and not es_bridge.is_active():
                # 懒激活：emotion_spirit 晚于本插件加载/中途安装时，initialize 的一次性激活
                # 会扑空——这里按请求兜底重试（未装时 activate 是廉价 no-op，返回 not_installed）。
                es_bridge.activate()
            if es_bridge is not None and es_on and es_bridge.is_active():
                es_bridge.reassert_persona_disabled()   # 自愈中途被改回 'auto' 的双注入
                # emotion_spirit 按 sender_id 给信号做键（main.py:1069 get_sender_id），不是我们
                # 的 unified_msg_origin session_key；用它的键查，否则永远 miss（红队 contract）。
                es_skey = session_key
                try:
                    _sid = event.get_sender_id()
                    if _sid:
                        es_skey = str(_sid)
                except Exception:  # noqa: BLE001
                    pass
                es_block = await es_bridge.consume_state_block(es_skey)
                if es_block:
                    appender = getattr(
                        getattr(plugin, "_llm_response_pipeline", None),
                        "_append_request_prompt_fragment", None,
                    )
                    if callable(appender):
                        appender(request, es_block)
                    else:
                        current = str(getattr(request, "system_prompt", "") or "")
                        request.system_prompt = f"{current}\n{es_block}".strip()
                    logger.debug(
                        "Sylanne emotion_spirit state injected: session=%s chars=%d",
                        es_skey, len(es_block))
            elif es_bridge is not None and not es_on and es_bridge.is_active():
                # 用户中途把桥配置关掉 → 还原 emotion_spirit 自己的 persona 注入（不留痕，
                # 红队 lifecycle：flag-off 不还原会把它一直静音）。
                es_bridge.deactivate()
        except Exception as _esx:  # noqa: BLE001 - emotion_spirit 消费失败绝不阻断请求
            logger.debug("Sylanne emotion_spirit consume skipped: %s", _esx)
    except Exception as exc:  # noqa: BLE001
        logger.error("Sylanne v2core request stage failed（继续请求管线）: %s", exc, exc_info=True)


def consume_pending_assessment(
    plugin: Any, scope_or_session: SessionScope | str
) -> dict[str, Any] | None:
    """请求管线在 host.on_request 前调用：取走本轮 v2core 评价（合并进 assessment）。

    一次性语义（取走即清），同步零 IO。无暂存 → None（请求管线行为不变）。
    """
    rt = _runtime_from_scope_or_legacy(plugin, scope_or_session)
    if not isinstance(rt, dict):
        return None
    a = rt.get("pending_assessment")
    rt["pending_assessment"] = None
    return a if isinstance(a, dict) and a else None


def consume_pending_quality(
    plugin: Any, scope_or_session: SessionScope | str
) -> float | None:
    """请求管线在构造 request tick event 前调用：取走上一轮自评的对话质量分。

    一次性语义（取走即清），同步零 IO。无暂存/陈旧 → None。注入进 event.values
    ["dialogue_quality"] → kernel.tick 透传 process → _drift_embodiment 自动漂移
    （canonical 滞后反馈：第 N 轮评分第 N+1 轮 request 拍生效）。

    时效（红队 wjqkfgh4i minor）：质量分是【上一轮回复】的滞后反馈，只对紧接的下一轮有意义。
    暂存格式 {"score": float, "ts": float}；若距上轮自评超 _QUALITY_TTL_S（如长间隔 gap、
    新话题），陈旧分丢弃返 None——否则陈旧高质量分注入不相关新话题，且 _drift_embodiment 的
    dt 巨大会放大这次错漂移。裸 float（旧格式/测试直塞）向后兼容，视为不过期。
    """
    rt = _runtime_from_scope_or_legacy(plugin, scope_or_session)
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


def _compose_dispatch_modulators(ctx: Any) -> dict[str, float]:
    """T3-01：把本轮"状态该怎么改消息形状"的两路信号合成一份派发调制器。

    两路信号：
      1) 行为层（behavior.py）挂在点燃指令上的 cps_mult/max_part_chars_mult/
         extra_predelay_s——文本已经在说"回得短/脱口而出/拖着不碰"，力学同向落地。
      2) 表达风格（ExpressionCapability.perceive 挂的 scratch["express"]）里的
         segment_bias/pause_bias——此前只喂 fragment._style_line 的文本提示（"想多
         说几句"/"说话带停顿"），从未真的改过派发参数（review kill：flattened into
         prompt words）。这里复用 fragment 已经在用的同一对阈值（1.5 / 0.8），保证
         "嘴上说" 和 "手上做" 在同一信号上触发——不另开独立随机源（红队命门）。
    最终对乘法调制器 clamp 到 [0.7,1.3]、predelay clamp 到 [0,5]（同 behavior.py
    的安全区间，防合成后越界）。零信号 → 全中性默认（1.0/1.0/0.0）。
    """
    behavior_mods = ctx.scratch.get("behavior_modulators")
    if not isinstance(behavior_mods, dict):
        behavior_mods = {}
    cps_mult = float(behavior_mods.get("cps_mult", 1.0) or 1.0)
    max_part_mult = float(behavior_mods.get("max_part_chars_mult", 1.0) or 1.0)
    extra_predelay = float(behavior_mods.get("extra_predelay_s", 0.0) or 0.0)

    express = ctx.scratch.get("express")
    if isinstance(express, dict):
        try:
            segment_bias = float(express.get("segment_bias", 0.0) or 0.0)
            pause_bias = float(express.get("pause_bias", 0.0) or 0.0)
        except (TypeError, ValueError):
            segment_bias = pause_bias = 0.0
        if segment_bias > 1.5:      # 同 fragment._style_line "想多说几句" 阈值
            max_part_mult *= 0.9    # 更碎一点：想说的更多，倾向拆成更多条而不是一条更长
        if pause_bias > 0.8:        # 同 fragment._style_line "说话带停顿" 阈值
            extra_predelay += min(1.5, (pause_bias - 0.8) * 1.5)

    # T2-03⑤：收尾窗口内——即便本轮没被压成 hold/极简回应，正常说话也该慢半拍
    # （"delayed reply" 是卡片给的两条腿之一）。同源读 winddown_hold_bias（与
    # ignition 的 g_hold 加项同一个 scratch 值），不另开一路计算（防公式分叉）。
    winddown_bias = float(ctx.scratch.get("winddown_hold_bias", 0.0) or 0.0)
    if winddown_bias > 0.0:
        extra_predelay += min(2.5, winddown_bias * 5.0)

    return {
        "cps_mult": max(0.7, min(1.3, cps_mult)),
        "max_part_chars_mult": max(0.7, min(1.3, max_part_mult)),
        "extra_predelay_s": max(0.0, min(5.0, extra_predelay)),
    }


def consume_dispatch_modulators(
    plugin: Any, scope_or_session: SessionScope | str
) -> dict[str, float] | None:
    """投递管线（llm_response_pipeline，没有 ctx）取走本轮 T3-01 派发调制器。

    一次性语义（取走即清，同 consume_pending_quality）。无暂存/陈旧
    （> _DISPATCH_MOD_TTL，防跨轮串味——rt 是跨轮持久字典）→ None，调用方按中性
    默认（1.0/1.0/0.0）处理，零力学变化。
    """
    rt = _runtime_from_scope_or_legacy(plugin, scope_or_session)
    if not isinstance(rt, dict):
        return None
    mods = rt.get("turn_dispatch_modulators")
    rt["turn_dispatch_modulators"] = None
    if not isinstance(mods, dict):
        return None
    try:
        ts = float(mods.get("ts", 0.0) or 0.0)
        if ts <= 0.0 or (time.time() - ts) > _DISPATCH_MOD_TTL:
            return None
        return {
            "cps_mult": float(mods.get("cps_mult", 1.0) or 1.0),
            "max_part_chars_mult": float(mods.get("max_part_chars_mult", 1.0) or 1.0),
            "extra_predelay_s": float(mods.get("extra_predelay_s", 0.0) or 0.0),
        }
    except (TypeError, ValueError):
        return None


# ===========================================================================
# 阶段二：response 钩子（DELIBERATE+EVOLVE，持锁）
# ===========================================================================

def _v3_settle_v2core_reply(plugin: Any, session_key: str, kind: Any, reply_kind_enum: Any) -> None:
    """把 v2core 的权威 ReplyKind 决策交给 v3 shadow（默认关时是空操作）。

    只处理终局的两类：SILENT（这轮不说话，不会再有投递证据）与 FALLBACK（兜底文案，
    v2 投影恒 UNKNOWN）。SPEAK 留给真投递面结算，绝不在此提前认领。facade 内部保证
    不抛，故这里没有 try——v3 绝不能改 v2 的回复路径。
    """

    facade = getattr(plugin, "_v3_shadow", None)
    if facade is None or not session_key:
        return
    if kind is reply_kind_enum.SILENT:
        facade.settle(session_key=session_key, route_kind="SILENT", reply_kind="SILENT")
    elif kind is reply_kind_enum.FALLBACK:
        facade.settle(
            session_key=session_key,
            route_kind="FALLBACK",
            reply_kind="FALLBACK",
            part_count=1,
        )


async def apply_v2core_response(plugin: Any, event: Any, response: Any) -> bool:
    """LLM 回复后的裁决阶段，返回是否抑制后续物理投递。

    返回 True  = 仅 SILENT；本层终结本轮，防 no-ghost 兜底复活装死。
    返回 False = delivery continuation；SPEAK/FALLBACK 继续进入唯一的
                 LLMResponsePipeline，完成 sanitize、分段、投递与观测。
    """
    if response is None or _is_cron_event(event):
        return False
    try:
        from sylanne_alpha.message_dispatch import normalize_completion_text
        from sylanne_alpha.v2core.contracts import ReplyKind

        runtime_context = _runtime_context_for_event(plugin, event)
        if runtime_context is None:
            return False
        scope, session_key, rt = runtime_context
        # T3 防护：completion_text 可能是 content-parts 列表/repr（provider tool 轮产物），
        # 在这第一道读边界就归一为纯文本——既不漏进正文，也防写回 AstrBot 历史被 repr 污染。
        draft_raw = normalize_completion_text(getattr(response, "completion_text", ""))
        draft = draft_raw if draft_raw.strip() else None

        # T3-01 防陈旧串味：先重置成中性，再往下走。若本轮后续步骤（_ensure_loaded/
        # percept 补跑/decision stage）中途抛异常触发下面的兜底 `except → return False`
        # 继续投递管线时会 consume_dispatch_modulators——这里先清空，保证
        # 拿到的要么是本轮真算出来的调制器，要么是 None（中性），绝不是上一轮的陈旧值。
        rt["turn_dispatch_modulators"] = None
        await _ensure_loaded(plugin, session_key, rt)

        # realtime 投递接管开启时，投递管线的 observe_response 会打 response tick
        cfg = getattr(plugin, "_config", None) or getattr(plugin, "config", None) or {}
        delivery_observes_response = bool(
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
                    evo_delta=_evo_provider(plugin, session_key),
                )
                _apply_v2core_feature_flags(ctx, plugin)
                _apply_winddown_window_scratch(ctx, rt)

            # T3-01：本轮派发调制器（行为力学 + 表达风格力学合成），供投递路径
            # 取走。每轮都重写（哪怕是 {}/中性）——覆盖上一轮陈旧值，不留串味风险。
            try:
                rt["turn_dispatch_modulators"] = {
                    **_compose_dispatch_modulators(ctx),
                    "ts": time.time(),
                }
            except Exception:  # noqa: BLE001 - 调制器合成失败绝不阻断裁决/回复
                rt["turn_dispatch_modulators"] = None

            reply = rt["runner"].run_decision_stage(
                ctx, draft=draft,
                # SPEAK/FALLBACK 且投递管线会观测 → 不打 tick（全局恰好一拍）；
                # SILENT 轮抑制投递 → 必须本层打。先裁决再定，由 runner 内部
                # 无法预知，故这里给"投递管线不观测"时恒打；SILENT 的修正见下。
                do_response_tick=not delivery_observes_response,
            )

            # T2-01②③ + T2-03⑤：SILENT 落地前——DeliberateSilence 第二沉默源尝试软化
            # （绝对沉默像掉线，极简回应才像心情）+ 事后认账留痕（不管软化与否，只要
            # 本轮真是"该说而没细说"就记下来，供下一轮心象自然带出）。两个触发源都会
            # 进这块：deliberate_silence_enabled 直接开，或本轮仍在 winddown 收尾窗口内
            # （winddown_active）——忙线期间被迫的 hold 同样不该读成"掉线"。两开关都
            # 关闭/都不在窗口内时两个 scratch 键都是 False，本块整体 no-op。
            if reply.kind is ReplyKind.SILENT and (
                ctx.scratch.get("deliberate_silence_enabled") or ctx.scratch.get("winddown_active")
            ):
                try:
                    sil0 = ctx.scratch.get("silent")
                    base_reason = ""
                    if isinstance(sil0, dict):
                        base_reason = str(sil0.get("reason", "") or "")
                    elif isinstance(sil0, str):
                        base_reason = sil0
                    minimal_reply, ds_reason = _maybe_soften_silence(plugin, ctx)
                    final_reason = ds_reason or base_reason or "unspecified"
                    rt["last_silent"] = {
                        "ts": time.time(),
                        "reason": final_reason,
                        "ignored_text_hash": _hash_text(ctx.text or ""),
                    }
                    if minimal_reply is not None:
                        reply = minimal_reply
                except Exception:  # noqa: BLE001
                    pass   # 软化/留痕失败绝不阻断裁决——原 SILENT 照旧生效

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
            # 出站判据（review wiring-correctness high）：SPEAK，或 FALLBACK 且有上游草稿
            # （投递管线真发草稿）。绝不在 SILENT、或 FALLBACK-空草稿（投递管线会将
            # empty_completion 静默丢弃、
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

            # v3 shadow 响应边界（design 14.2；plan Task 13）：这里是 v2 唯一带真 ReplyKind
            # 的权威决策面，且已过 DeliberateSilence 软化（reply 可能在上面被改写），故只能在
            # 这个点读。SILENT → HOLD（这轮到此为止，不会再有投递证据）；FALLBACK → 恒 UNKNOWN。
            # SPEAK 【故意不结算】：SPEAK 要由真投递（分段全成功）证明，这里继续投递管线，
            # 让 _dispatch_segmented_parts 那条终端证据来结算。默认关时 settle 是空操作。
            _v3_settle_v2core_reply(plugin, session_key, reply.kind, ReplyKind)

            suppress_delivery: bool
            if reply.kind is ReplyKind.SILENT:
                response.completion_text = ""
                # 投递被抑制：若上面因投递管线负责观测而没打 tick，这轮补打沉默知觉
                if delivery_observes_response:
                    rt["runner"].response_tick(ctx, reply)
                logger.info(
                    "Sylanne v2core SILENT | session=%s | reason=%s",
                    session_key, str((reply.meta or {}).get("reason", "") or "unspecified"),
                )
                suppress_delivery = True
            elif reply.kind is ReplyKind.SPEAK and reply.parts:
                response.completion_text = "\n".join(p for p in reply.parts if p.strip())
                suppress_delivery = False
            else:  # FALLBACK
                if draft is not None:
                    response.completion_text = (
                        "\n".join(p for p in reply.parts if p.strip()) or draft_raw
                    )
                suppress_delivery = False

        logger.info(
            "Sylanne v2core turn: session=%s kind=%s suppress_delivery=%s",
            session_key, reply.kind.value, suppress_delivery,
        )
        _schedule_domain_save(
            plugin,
            scope if scope is not None else session_key,
            rt["domains"],
            rt.get("behavior_last_fired"),
        )
        return suppress_delivery
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Sylanne v2core decision failed; continuing delivery pipeline: %s",
            exc,
            exc_info=True,
        )
        return False


# ===========================================================================
# 空闲触达咨询（主动桥 get_speech_decision 的增强源）
# ===========================================================================

async def merge_idle_reach_into_decision(
    plugin: Any, scope_or_session: SessionScope | str, decision: dict[str, Any]
) -> dict[str, Any]:
    """若 v2core 空闲触达胜出，升格 decision.action=reach_out（live + scheduler 共用）。"""
    try:
        reach = await consult_idle_reach(plugin, scope_or_session)
        decision["v2core_reach"] = reach
        if reach.get("reach") and decision.get("allowed", True):
            decision["action"] = "reach_out"
            decision["reason"] = (
                f"{decision.get('reason', '')}|v2core_reach".lstrip("|")
            )
    except Exception:
        pass
    return decision


async def consult_idle_reach(
    plugin: Any, scope_or_session: SessionScope | str
) -> dict[str, Any]:
    """空闲轮咨询：reach 想不想赢？零写、零 tick、零 LLM——纯读决策。

    消费者：ProactiveScheduler.get_speech_decision（外部主动桥轮询它）。
    返回 {"reach": bool, "g_reach": float, "action": str}；异常 → reach=False。
    """
    out = {"reach": False, "g_reach": 0.0, "action": "hold"}
    try:
        rt = _runtime_from_scope_or_legacy(plugin, scope_or_session)
        if rt is None:
            return out
        session_key = (
            scope_or_session.storage_token
            if type(scope_or_session) is SessionScope
            else scope_or_session
        )
        await _ensure_loaded(plugin, session_key, rt)
        # T2-03⑤ MAJOR 修复（红队 finding）：忙线窗口内不该一边"要去忙了"一边又高频
        # 主动找你——旧实现想通过 _apply_winddown_window_scratch 把 winddown_hold_bias
        # 也塞进这条空闲咨询的 g_hold，指望"压一压"reach 倾向；但 ignition 的空闲分支
        # 是 min-cost 选择器，那里 g_hold 是"hold 的代价"，加偏置反而推高 hold 代价、
        # argmin 更容易滑向 reach——方向做反了（她在收尾窗口内反而更爱主动戳你）。
        # 窗口内的真实语义是"没有主动意图"，这里直接说出来、压根不咨询 deliberate，
        # 不再指望数值博弈把方向掰回来。
        _until = rt.get("winddown_until")
        if isinstance(_until, (int, float)) and time.time() < float(_until):
            logger.debug(
                "Sylanne v2core consult_idle_reach [%s]: 收尾窗口内，主动意图直接抑制",
                session_key,
            )
            return out
        runner = rt["runner"]
        ctx = runner.run_percept_stage(
            session_key, {"proactive": True}, "", domains=rt["domains"], idle=True,
            evo_delta=_evo_provider(plugin, session_key),
        )
        ctx.scratch["proactive"] = True
        _apply_v2core_feature_flags(ctx, plugin)
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
    "apply_v2core_request",
    "apply_v2core_response",
    "consume_pending_assessment",
    "consult_idle_reach",
    "merge_idle_reach_into_decision",
    "drain_pending_saves",
    "save_all_domains",
]
