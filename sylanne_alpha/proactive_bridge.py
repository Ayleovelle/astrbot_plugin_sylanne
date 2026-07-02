"""主动发言桥接：把 Sylanne 的主动发言意图 + 生活素材交给大饼插件执行发送。

设计（用户确认的适配策略）：
  - 大饼（astrbot_plugin_proactive_chat）全接管"发送"，Sylanne 打辅助。
  - Sylanne 决定"何时主动" + 提供"生活素材"，大饼用它成熟的链路生成并发送。

素材注入通道（已验证，满足"不改大饼 + 不污染全局"）：
  大饼官方会话级配置接口 session_override_manager.set_override(sid, {"proactive_prompt": ...})
  - proactive_prompt 在大饼 ALLOWED_ROOT_KEYS 白名单内
  - _sanitize_patch 只校验顶层键名，不过滤文本值
  - _get_session_config → get_effective 会把 override 合并进生效配置
  - override 只写单会话的 session_overrides.json，不碰全局/persona/history

时序：set_override（写素材）→ await check_and_chat（大饼全程 await 生成+发送）
      → 恢复原 override（有原值写回，无则删除），用完即清不留痕。

大饼未安装/接口缺失时静默降级，不影响 Sylanne 其余功能。
"""

from __future__ import annotations

import asyncio
import random
import time
from typing import Any

from sylanne_alpha.variant_pool import choose

try:
    from astrbot.api import logger  # type: ignore
except ImportError:
    import logging as _logging

    logger = _logging.getLogger("astrbot_plugin_sylanne")  # type: ignore


PROACTIVE_CHAT_STAR_NAME = "astrbot_plugin_proactive_chat"

# T4-02②：踌躇词试探。10+ 变体，语气有软有窘有转折，去掉了"在吗？我"这种陌生人register
# （对男朋友讲这句会显得突兀/生分，见 T4-02 卡片）。
_HESITATION_FILLERS: tuple[str, ...] = (
    "那个……",
    "嗯…",
    "诶，",
    "…话说，",
    "唔，",
    "啊对了…",
    "呃，",
    "怎么说呢…",
    "话说回来…",
    "对了，",
    "唉…",
    "算了还是说吧，",
)


class ProactiveBridge:
    """Sylanne → 大饼 主动发言桥接器。"""

    # issue#43 Wave2：崩溃中断的 dispatch 在此 KV 键留下「干净 override 基线」sidecar，
    # 启动时精确还原（含用户自配 proactive_prompt），绝不按 key/value 盲删大饼配置。
    _BASELINE_KV = "sylanne_proactive_inflight_baseline"
    # dispatch 唯一会改的 override 键集合：sidecar 只存这些键的干净基线、恢复也只 RMW 这些
    # 键，永不波及 schedule_settings / tts_settings 等其它（用户或 adjust 拥有的）键。
    _DISPATCH_OWNED_KEYS = ("proactive_prompt", "segmented_reply_settings")

    def __init__(self, plugin: Any) -> None:
        self._p = plugin
        # 每会话上次桥接触发时间（用于间隔节流，复用大饼的 min_interval 公式）
        self._last_bridge_dispatch: dict[str, float] = {}
        # 待 Sylanne 接管分段的 origin 集合：dispatch 时标记，on_decorating_result 钩子消费。
        # key = 大饼实际发送用的 origin（unified_msg_origin）
        self._pending_segment_takeover: set[str] = set()
        # issue#43 Wave2：per-sid 锁序列化 dispatch∥adjust_countdown 对同一 sid override 的
        # 读改写（治残留竞态②）；键 = resolved origin。短临界区——锁【不跨】check_and_chat /
        # _schedule_next_chat_and_save 的外部 LLM 调用（不重蹈 3.0 跨边界长持锁）。
        self._sid_locks: dict[str, asyncio.Lock] = {}
        # 串行化 sidecar KV dict 的跨 sid 读改写（短持，不跨外部调用）。
        self._baseline_kv_lock = asyncio.Lock()
        # issue#43 Wave2 修订（验证红队 finding）：同方法并发去重。锁不跨 LLM 窗口，故同一
        # sid 上第二个 dispatch/adjust 进来时第一个仍在飞——它会把对方的临时注入误当「干净
        # 基线」snapshot 回去造成残留复读。in-flight 闸保证同 sid 同方法只有一个在飞。
        self._inflight_dispatch: set[str] = set()
        self._inflight_adjust: set[str] = set()
        # T4-02②：踌躇词变体池 recent-N 去重历史（按 session_key 分列，forget_session 清理）。
        self._filler_recent: dict[str, list[str]] = {}

    def forget_session(self, session_key: str) -> None:
        """释放某会话在桥接层的残留态（CP8-P6：会话删除/驱逐时清理，防无界增长）。

        session_key 经 _resolve_origin 转 origin 后才是 _last_bridge_dispatch 的键，
        故两种键都尝试清除（origin 解析可能因映射已被清而回退，双清更稳妥）。
        """
        self._last_bridge_dispatch.pop(session_key, None)
        self._filler_recent.pop(session_key, None)
        try:
            origin = self._resolve_origin(session_key)
            self._last_bridge_dispatch.pop(origin, None)
            self._filler_recent.pop(origin, None)
            self._pending_segment_takeover.discard(origin)
            # issue#43 Wave2：只清【未被持有】的锁——若该 sid 正有 dispatch/adjust 在飞，
            # 删了它后续 _lock_for 会 setdefault 一把新锁，与在飞 task 失去互斥（红队 nit）。
            lk = self._sid_locks.get(origin)
            if lk is not None and not lk.locked() and origin not in self._inflight_dispatch \
                    and origin not in self._inflight_adjust:
                self._sid_locks.pop(origin, None)
        except Exception:
            pass

    def _get_proactive_plugin(self) -> Any:
        """拿大饼插件实例；未安装/拿不到则返回 None（静默降级）。"""
        context = getattr(self._p, "context", None)
        if context is None or not hasattr(context, "get_registered_star"):
            return None
        try:
            meta = context.get_registered_star(PROACTIVE_CHAT_STAR_NAME)
        except Exception:
            return None
        if meta is None:
            return None
        # StarMetadata.star_cls 是插件实例
        return getattr(meta, "star_cls", None)

    def _resolve_origin(self, session_key: str) -> str:
        """把 Sylanne 的 session_key 转成大饼可用的 unified_msg_origin。

        Sylanne 的 session_key 基础形态即标准 UMO，但可能带 ::agent:/::speaker:
        后缀（内部多发言人追踪用）。优先用 _store.session_origins 映射
        （收消息时由 request pipeline 写入 session_key→UMO），回退剥后缀。
        """
        umo = ""
        store = getattr(self._p, "_store", None)
        origins = getattr(store, "session_origins", None)
        if origins is not None:
            try:
                umo = origins.get(session_key, "") or ""
            except Exception:
                umo = ""
        if umo:
            return str(umo)
        # 回退：剥掉 Sylanne 内部后缀
        return str(session_key).split("::", 1)[0]

    def _segment_takeover_enabled(self) -> bool:
        """是否启用"Sylanne 接管大饼主动消息的分段发送"。"""
        cfg = getattr(self._p, "config", None) or {}
        return bool(cfg.get("sylanne_alpha_proactive_segment_takeover", False))

    def claim_segment_takeover(self, origin: str) -> bool:
        """on_decorating_result 钩子调用：若该 origin 被登记为待接管，认领并清除标记。

        返回 True 表示这条主动消息由 Sylanne 接管分段（钩子应清空 chain 阻止大饼发送，
        并自行连发分段）。一次性消费，避免误伤后续正常消息。
        """
        if origin in self._pending_segment_takeover:
            self._pending_segment_takeover.discard(origin)
            return True
        return False

    # 桥接依赖的大饼接口清单（含私有方法）。大饼升级若改了内部实现，这里探测得到。
    _REQUIRED_API = (
        "check_and_chat",
        "session_override_manager",
        "_get_session_config",
        "_schedule_next_chat_and_save",
    )

    def available(self) -> bool:
        """大饼是否可用（已安装且暴露所需接口）。

        CP8-P6：核心接口（check_and_chat + session_override_manager）齐才算可用；
        但桥接还依赖若干私有方法（_get_session_config/_schedule_next_chat_and_save），
        大饼升级改内部实现会让这些静默失效——故 probe_missing 一次性 warning 告警，
        让用户能发现"主动发言已废"而非毫无察觉。
        """
        plugin = self._get_proactive_plugin()
        core_ok = bool(
            plugin is not None
            and hasattr(plugin, "check_and_chat")
            and getattr(plugin, "session_override_manager", None) is not None
        )
        if core_ok:
            self._probe_missing_api(plugin)
        return core_ok

    def _probe_missing_api(self, plugin: Any) -> None:
        """探测桥接依赖的大饼接口是否齐全，缺失则一次性 warning（避免刷屏）。"""
        if getattr(self, "_api_probed", False):
            return
        self._api_probed = True
        missing = [name for name in self._REQUIRED_API if not hasattr(plugin, name)]
        if missing:
            logger.warning(
                "Sylanne 主动发言桥接：大饼(astrbot_plugin_proactive_chat)缺失接口 %s"
                "——大饼可能已升级改了内部实现，部分主动发言功能将静默降级。"
                "请检查大饼版本或在 issue 反馈。",
                missing,
            )

    # ------------------------------------------------------------------
    # 时间闸门：复用大饼的时间公式（quiet_hours + min_interval 节流）
    # Sylanne 驱动"想说话"，大饼公式当闸门——免打扰时段/太频繁时压住。
    # ------------------------------------------------------------------

    def _daping_schedule_conf(self, sid: str) -> dict[str, Any]:
        """读大饼该会话的 schedule_settings（含 quiet_hours/min_interval）。

        读不到时返回大饼默认值（quiet 1-7、min 30 分钟），保持与大饼一致。
        """
        defaults = {"quiet_hours": "1-7", "min_interval_minutes": 30}
        plugin = self._get_proactive_plugin()
        if plugin is None or not hasattr(plugin, "_get_session_config"):
            return defaults
        try:
            cfg = plugin._get_session_config(sid)
            sched = (cfg or {}).get("schedule_settings", {}) if isinstance(cfg, dict) else {}
            return {**defaults, **(sched if isinstance(sched, dict) else {})}
        except Exception:
            return defaults

    def _in_quiet_hours(self, sid: str) -> bool:
        """复用大饼 is_quiet_time 公式判断免打扰时段；不可用时回退本地实现。"""
        quiet_str = str(self._daping_schedule_conf(sid).get("quiet_hours", "1-7"))
        plugin = self._get_proactive_plugin()
        tz = getattr(plugin, "timezone", None) if plugin is not None else None
        try:
            from astrbot.api import logger as _  # noqa: F401  (确保在插件环境)
            from utils.time_utils import is_quiet_time  # type: ignore

            return bool(is_quiet_time(quiet_str, tz))
        except Exception:
            # 回退：内联同款公式（与大饼 is_quiet_time 一致，支持跨天）
            try:
                start_str, end_str = quiet_str.split("-")
                start_h, end_h = int(start_str), int(end_str)
                from datetime import datetime

                hour = (datetime.now(tz) if tz else datetime.now()).hour
                if start_h <= end_h:
                    return start_h <= hour < end_h
                return hour >= start_h or hour < end_h
            except (ValueError, TypeError):
                return False

    def should_dispatch_now(self, session_key: str) -> tuple[bool, str]:
        """Sylanne 侧闸门：是否允许现在触发桥接。

        两道复用大饼公式的闸门（check_and_chat 内部还会再过一次 quiet，这里前置
        是为了免打扰/太频繁时连素材都不生成、不浪费触发）：
          1. quiet_hours：免打扰时段直接压住
          2. min_interval 节流：距上次桥接触发不足 min_interval_minutes 则压住
        Returns: (allowed, reason)
        """
        sid = self._resolve_origin(session_key)
        if self._in_quiet_hours(sid):
            return False, "quiet_hours"
        conf = self._daping_schedule_conf(sid)
        try:
            min_gap = float(conf.get("min_interval_minutes", 30)) * 60.0
        except (TypeError, ValueError):
            min_gap = 1800.0
        last = self._last_bridge_dispatch.get(sid, 0.0)
        if last and (time.time() - last) < min_gap:
            return False, "min_interval_throttle"
        return True, "ok"

    async def infer_reason_code(
        self, session_key: str, *, surface: dict[str, Any] | None = None
    ) -> str:
        """查计算栈深层状态 + 仪式缺席，推断主动发言的缘由码。

        触发源整合（任一命中即返回对应 reason_code，优先级：仪式 > 计算栈 > 默认）：
          - ritual：到了习惯互动时间但用户缺席
          - void / scar / ...：计算栈 proactive_sylanne 给出的 reason_code
          - life_rhythm：默认（纯生活节律驱动）
        全程异常静默，失败回退 life_rhythm。

        Args:
            surface: 可选的预计算 proactive_sylanne 结果。传入则复用（避免重复
                tick/save），不传则内部自行调用。ritual 优先级始终先于 surface。
        """
        p = self._p
        # 1) 仪式缺席（proactive_scheduler.check_ritual_absence）——优先级最高，不依赖 surface
        sched = getattr(p, "_proactive_scheduler", None)
        if sched is not None and hasattr(sched, "check_ritual_absence"):
            try:
                ritual = sched.check_ritual_absence(session_key)
                if ritual:
                    return "ritual"
            except Exception:
                pass
        # 2) 计算栈深层缘由（proactive_sylanne → decision.reason_code）
        try:
            res = surface
            if res is None:
                getter = getattr(p, "proactive_sylanne", None)
                if callable(getter):
                    res = await getter(session_key=session_key)
            decision = res.get("decision", {}) if isinstance(res, dict) else {}
            rc = str(decision.get("reason_code", "") or "").strip()
            if rc:
                return rc
        except Exception:
            pass
        return "life_rhythm"

    def build_motivation_text(
        self, reason: str, mood: str, *, reason_code: str = "", session_key: str = ""
    ) -> str:
        """构造带 Sylanne 人设语气的素材动机文本，作为大饼的 proactive_prompt。

        组成：人设语气提示 + 触发缘由(reason_code) + 具体生活事件/心情 + 近期生活上下文。
        让大饼生成的主动发言反映"Sylanne 此刻的状态 + 为什么想说"。
        """
        p = self._p
        # 人设名（轻量，不强行覆盖大饼 persona，只作语气锚点）
        cfg = getattr(p, "config", None) or {}
        persona_name = str(cfg.get("sylanne_persona_name") or "Sylanne").strip() or "Sylanne"

        # 触发缘由 → 自然语言动机
        reason_phrase = {
            "void": "心里有一处空落落的，很想找ta说说话",
            "scar": "有件没说完的事一直搁在心上",
            "ritual": "到了你俩平时会聊两句的时间，ta却没出现",
            "life_rhythm": "刚好想起ta了",
        }.get(str(reason_code or "").lower(), "")

        # 近期生活上下文（复用 life_simulation 现成方法）
        life_ctx = ""
        sim = getattr(p, "_life_simulator", None)
        if sim is not None and hasattr(sim, "recent_context_for_prompt"):
            try:
                life_ctx = str(sim.recent_context_for_prompt(limit=2) or "").strip()
            except Exception:
                life_ctx = ""

        clean_reason = str(reason or "").replace("[life_event]", "").strip()
        parts = [
            f"（你是{persona_name}。现在是你主动开口找对方，不是回复。",
            f"你此刻的心情：{mood}。" if mood else "",
            f"起因：{clean_reason}。" if clean_reason else "",
            f"{reason_phrase}。" if reason_phrase else "",
            f"\n{life_ctx}" if life_ctx else "",
            "用你一贯含蓄、偶尔会顿一下的语气，自然地起个话头——别太用力，别像在汇报，"
            "就像真的想起了什么想跟ta分享。）",
        ]
        return "".join(pt for pt in parts if pt)

    async def dispatch(self, session_key: str, motivation_text: str) -> dict[str, Any]:
        """触发一次大饼主动发言，注入 motivation_text 作为 proactive_prompt。

        Returns:
            {"dispatched": bool, "reason": str} —— reason 说明成功或降级原因。
        """
        plugin = self._get_proactive_plugin()
        if plugin is None:
            return {"dispatched": False, "reason": "proactive_chat_not_installed"}
        mgr = getattr(plugin, "session_override_manager", None)
        check_and_chat = getattr(plugin, "check_and_chat", None)
        if mgr is None or not callable(check_and_chat):
            return {"dispatched": False, "reason": "proactive_chat_api_missing"}

        sid = self._resolve_origin(session_key)
        if not sid:
            return {"dispatched": False, "reason": "no_valid_origin"}

        # issue#43 Wave2：三段式。锁【不跨】check_and_chat（不在锁内 await 外部 LLM，
        # 规避 3.0 式跨边界长持锁）；注入前把干净基线存进 sidecar，崩溃后由
        # recover_inflight_baselines 在启动时精确还原用户配置——绝不盲删 proactive_prompt。
        takeover = self._segment_takeover_enabled()
        # dispatch 拥有键的干净基线（复审 CLUSTER A）：优先复用已存的 sidecar——上次 dispatch 没
        # 还原干净时 live override 可能是脏残留，sidecar 里那份才是真基线（anti-latching）。
        baseline_owned: dict[str, Any] = {}

        # 三段式，全程 try/finally：段3 还原 + in-flight 清理都在 finally——无论正常/异常/
        # CancelledError 都【尝试】把 override 还原干净；还原成功才清 sidecar，失败/被取消则保留
        # sidecar 让启动 recover 修复。复审 CLUSTER A：原来段3 在 finally 外 + sidecar 无条件清，
        # restore 瞬时失败 / 取消会把用户 pp 永久毁掉、breadcrumb 也丢 = 重现 issue#43 复读。
        dispatched = False
        reason = "ok"
        i_own = False
        try:
            # 段1（短锁）：in-flight 去重 → 定干净基线（存/复用 sidecar）→ 写注入态。
            async with self._lock_for(sid):
                if sid in self._inflight_dispatch:
                    # 已有 dispatch 在飞：第二个不再注入（否则把对方素材误当基线 → 残留复读）
                    return {"dispatched": False, "reason": "dispatch_in_flight"}
                self._inflight_dispatch.add(sid)
                i_own = True
                try:
                    live = mgr.get_override(sid) or {}
                except Exception:
                    live = {}
                if not isinstance(live, dict):
                    live = {}
                existing = await self._peek_inflight_baseline(sid)
                if existing is not None:
                    # 上次 dispatch 留下未还原的干净基线 → 它才是真基线，不被脏 live 覆盖
                    baseline_owned = existing
                else:
                    baseline_owned = {
                        k: live[k] for k in self._DISPATCH_OWNED_KEYS if k in live
                    }
                    await self._save_inflight_baseline(sid, baseline_owned)
                patched = {**live, "proactive_prompt": motivation_text}
                # 分段接管：关掉大饼自己的分段，并登记接管标记，由 on_decorating_result 钩子消费
                if takeover:
                    prev_seg = live.get("segmented_reply_settings", {})
                    patched["segmented_reply_settings"] = {
                        **(prev_seg if isinstance(prev_seg, dict) else {}),
                        "enable": False,
                    }
                    self._pending_segment_takeover.add(sid)
                try:
                    await mgr.set_override(sid, patched)
                except Exception as e:
                    logger.warning(
                        f"Sylanne proactive_bridge set_override failed: {e}", exc_info=True
                    )
                    return {"dispatched": False, "reason": f"error:{type(e).__name__}"}

            # 段2（无锁）：触发大饼生成 + 发送。外部 LLM 调用绝不在锁内 await。
            try:
                await check_and_chat(sid)
                # 仅【发送成功】才计入 min_interval 节流（复审 nit：失败的发送不该压住后续
                # 30min 重试；并发触发由 in-flight 闸挡，不靠这个时间戳，故无需在 await 前抢记）。
                self._last_bridge_dispatch[sid] = time.time()
                dispatched = True
            except Exception as e:
                reason = f"error:{type(e).__name__}"
                logger.warning(f"Sylanne proactive_bridge dispatch failed: {e}", exc_info=True)
            return {"dispatched": dispatched, "reason": reason}
        finally:
            if i_own:
                # 段3（在 finally）：RMW 把 owned 键还原成干净基线，保留并发 adjust 的 schedule。
                # 还原成功才清 sidecar；失败/取消则保留 sidecar 让 recover 在重启时修。
                try:
                    async with self._lock_for(sid):
                        restored = await self._restore_dispatch_keys(mgr, sid, baseline_owned)
                        if restored:
                            await self._clear_inflight_baseline(sid)
                except BaseException:
                    # 取消/异常打断还原 await：保留 sidecar（不清），交给启动 recover 修复。
                    pass
                self._inflight_dispatch.discard(sid)
                self._pending_segment_takeover.discard(sid)

    def _lock_for(self, sid: str) -> asyncio.Lock:
        """per-sid 锁（懒建，键 = resolved origin）。setdefault 单步原子、无 await，防两
        task 各建一把锁导致序列化失效（issue#43 Wave2 死锁红队 finding）。"""
        return self._sid_locks.setdefault(sid, asyncio.Lock())

    async def _restore_dispatch_keys(
        self, mgr: Any, sid: str, baseline: dict[str, Any]
    ) -> bool:
        """RMW 还原 dispatch 拥有的键（proactive_prompt / segmented_reply_settings）到 baseline，
        保留当前 override 的其它键（如并发 adjust 写的 schedule_settings）。baseline 有该键则恢复
        其值，无则删除桥接注入的；整体空了就 delete_override。

        返回是否真正持久化成功——失败（瞬时 set_override 异常等）时返回 False，调用方据此保留
        sidecar 让启动 recover 修复，绝不在还原失败时清掉 breadcrumb（复审 CLUSTER A）。"""
        try:
            cur = dict(mgr.get_override(sid) or {})
        except Exception as e:
            # get_override 垮了就不知道 override 里还有哪些键——强行用 cur={} 重写只剩 dispatch-owned
            # 键 = 抹掉并发 adjust 写的 schedule_settings 等（静默丢配置，gemini PR#46）。中止并返回
            # False：sidecar 保留、下次启动 recover 再修，绝不在读失败时破坏 RMW 的"保留其它键"。
            logger.warning(f"Sylanne proactive_bridge get_override failed, skip restore: {e}")
            return False
        for key in self._DISPATCH_OWNED_KEYS:
            if key in baseline:
                cur[key] = baseline[key]
            else:
                cur.pop(key, None)
        try:
            if cur:
                await mgr.set_override(sid, cur)
            else:
                await mgr.delete_override(sid)
            return True
        except Exception as e:
            logger.warning(f"Sylanne proactive_bridge override restore failed: {e}")
            return False

    async def _restore_schedule_keys(
        self, mgr: Any, sid: str, baseline: dict[str, Any]
    ) -> None:
        """RMW 还原 adjust_countdown 注入的 schedule_settings 到 baseline，保留其它键
        （如并发 dispatch 写的 proactive_prompt）；整体空了就 delete_override。"""
        try:
            cur = dict(mgr.get_override(sid) or {})
        except Exception as e:
            # 同 _restore_dispatch_keys：读失败用 cur={} 重写会抹掉并发 dispatch 写的 proactive_prompt。
            # 中止、不写——保留 override 全部键，下次 adjust/recover 再修（gemini PR#46）。
            logger.warning(f"Sylanne adjust_countdown get_override failed, skip restore: {e}")
            return
        if "schedule_settings" in baseline:
            cur["schedule_settings"] = baseline["schedule_settings"]
        else:
            cur.pop("schedule_settings", None)
        try:
            if cur:
                await mgr.set_override(sid, cur)
            else:
                await mgr.delete_override(sid)
        except Exception as e:
            logger.warning(f"Sylanne adjust_countdown override restore failed: {e}")

    async def _save_inflight_baseline(self, sid: str, baseline: dict[str, Any]) -> None:
        """注入前把 sid 的干净 override 基线写进 Sylanne 自己的 KV（含用户自配
        proactive_prompt / segmented），供崩溃后精确还原。无 KV 能力则静默降级（退回旧的
        靠 finally 还原语义）。跨 sid 的 sidecar dict 读改写由 _baseline_kv_lock 串行化。"""
        p = self._p
        if not (hasattr(p, "_has_kv_api") and p._has_kv_api()):
            return
        try:
            async with self._baseline_kv_lock:
                data = await self._load_inflight_baselines()
                data[sid] = dict(baseline)
                await p.put_kv_data(self._BASELINE_KV, data)
        except Exception:
            pass

    async def _clear_inflight_baseline(self, sid: str) -> None:
        """dispatch 正常收尾时清掉该 sid 的 sidecar 基线（不再算崩溃残留）。"""
        p = self._p
        if not (hasattr(p, "_has_kv_api") and p._has_kv_api()):
            return
        try:
            async with self._baseline_kv_lock:
                data = await self._load_inflight_baselines()
                if sid in data:
                    data.pop(sid, None)
                    await p.put_kv_data(self._BASELINE_KV, data)
        except Exception:
            pass

    async def _load_inflight_baselines(self) -> dict[str, Any]:
        """读 sidecar dict（{sid: 基线}）；无则空。调用方须持 _baseline_kv_lock 做 RMW。"""
        p = self._p
        try:
            data = await p.get_kv_data(self._BASELINE_KV, None)
        except Exception:
            return {}
        return dict(data) if isinstance(data, dict) else {}

    async def _peek_inflight_baseline(self, sid: str) -> dict[str, Any] | None:
        """读 sidecar 里 sid 的干净基线（dict）；无 / 无 KV → None。供 dispatch 段1 anti-latching：
        上次 dispatch 留下未还原的基线说明 live override 可能脏，应以这份为准（复审 CLUSTER A）。"""
        p = self._p
        if not (hasattr(p, "_has_kv_api") and p._has_kv_api()):
            return None
        try:
            async with self._baseline_kv_lock:
                data = await self._load_inflight_baselines()
        except Exception:
            return None
        entry = data.get(sid)
        return dict(entry) if isinstance(entry, dict) else None

    async def recover_inflight_baselines(self) -> int:
        """启动时还原崩溃中断的桥接基线（issue#43 Wave2 provenance 恢复）。

        sidecar 里残留的 {sid: dispatch 拥有键的干净基线} 来自「set_override(注入) 后、还原
        前」进程崩溃的 dispatch。逐 sid 把 override 里 dispatch 拥有的键（proactive_prompt /
        segmented_reply_settings）RMW 还原成基线值（基线没有该键则删该键），schedule_settings
        等其它键一律不动，再清空 sidecar。无残留 / 无 KV / 大饼不可用则 no-op。绝不盲删整条
        override、绝不波及非 dispatch 拥有的键。返回还原的 sid 数。
        """
        p = self._p
        if not (hasattr(p, "_has_kv_api") and p._has_kv_api()):
            return 0
        plugin = self._get_proactive_plugin()
        mgr = getattr(plugin, "session_override_manager", None) if plugin else None
        if mgr is None:
            return 0
        # 短锁内只【快照】sidecar（不再先清空整个 sidecar——复审 CLUSTER A：原来 put({}) 在
        # 逐 sid 还原之前，任一 set_override 失败就永久丢掉那条 breadcrumb）。外部 set_override
        # 写在锁外（守 _baseline_kv_lock 「不跨外部调用」契约）。
        async with self._baseline_kv_lock:
            data = await self._load_inflight_baselines()
        if not data:
            return 0
        recovered = 0
        for sid, baseline in list(data.items()):
            if not isinstance(baseline, dict):
                baseline = {}
            # 每 sid 的 RMW 走 per-sid 锁（防 init 顺序重排撞 live dispatch）；仅还原【成功】才清
            # 该 sid 的 sidecar，失败则保留 breadcrumb 下次启动再修。
            async with self._lock_for(sid):
                if await self._restore_dispatch_keys(mgr, sid, baseline):
                    await self._clear_inflight_baseline(sid)
                    recovered += 1
        return recovered

    # ------------------------------------------------------------------
    # 犹豫：人类粗糙的迟疑感。不是 bug，是"我在乎要不要说"的痕迹。
    # 强度由计算栈状态为主（怕打扰/想安静→犹豫强，想表达→犹豫弱），
    # 亲密度（body.warmth）调制（熟悉了→更自然，生疏→更迟疑）。
    # ------------------------------------------------------------------

    def _hesitation_enabled(self) -> bool:
        cfg = getattr(self._p, "config", None) or {}
        return bool(cfg.get("sylanne_alpha_proactive_hesitation", False))

    @staticmethod
    def compute_hesitation(body: dict[str, Any]) -> float:
        """从 surface.body 计算犹豫强度 [0,1]。

        boundary_pressure(怕打扰)/need_quiet(想安静) 推高犹豫；
        need_expression(想表达) 压低；warmth(熟悉/亲近) 压低（亲密度调制）。
        """
        def _f(d: dict, *keys: str) -> float:
            cur: Any = d
            for k in keys:
                cur = cur.get(k, {}) if isinstance(cur, dict) else 0.0
            try:
                return float(cur)
            except (TypeError, ValueError):
                return 0.0

        boundary = _f(body, "immunity", "boundary_pressure")
        need_quiet = _f(body, "needs", "need_quiet")
        need_expr = _f(body, "needs", "need_expression")
        warmth = _f(body, "temperature", "warmth")
        if warmth == 0.0:
            warmth = _f(body, "warmth")  # 兼容 body 顶层 warmth
        raw = max(boundary, need_quiet) - need_expr - warmth * 0.5
        return max(0.0, min(1.0, raw))

    def hesitation_plan(
        self, body: dict[str, Any], *, session_key: str | None = None
    ) -> dict[str, Any]:
        """根据犹豫强度产出本次主动发言的犹豫计划。

        Args:
            session_key: 用于踌躇词变体池 recent-N 去重（同一会话不连续撞同一个试探词）；
                拿不到时退回全局去重（跨会话共享一份历史，仍好过完全无状态）。

        Returns:
            {
              "hesitation": float,            # 强度
              "pre_delay_seconds": float,     # 发前迟疑停顿
              "withdraw": bool,               # 最后一刻是否收回（不发）
              "filler": str,                  # 踌躇词试探（空表示不加）
            }
        """
        h = self.compute_hesitation(body)
        # 发前迟疑：强度越高停越久（0 ~ ~45s），带随机抖动
        pre_delay = round(h * random.uniform(2.0, 45.0), 2) if h > 0.05 else 0.0
        # 最后一刻收回：高犹豫时才可能放弃，概率 = h^2 * 0.5（最高约 50%）
        withdraw = random.random() < (h * h * 0.5)
        # 踌躇词试探：中高犹豫时偶尔加（T4-02②：变体池挑，recent-N 去重防连续复读）
        filler = ""
        if h > 0.4 and random.random() < (h * 0.6):
            filler = choose(
                _HESITATION_FILLERS,
                recent_key=session_key or "_global",
                state=self._filler_recent,
            )
        return {
            "hesitation": round(h, 4),
            "pre_delay_seconds": pre_delay,
            "withdraw": bool(withdraw),
            "filler": filler,
        }

    def apply_segment_hesitation(
        self, parts: list[dict[str, Any]], body: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """连发中欲言又止：按犹豫强度，给分段插入更长的中途停顿、或半句收住留「……」。

        不改变段数语义，只调 delay 和在某段尾部追加省略号，模拟"发着发着顿了一下"。
        强度低时基本原样返回。
        """
        if not parts:
            return parts
        h = self.compute_hesitation(body)
        if h <= 0.2:
            return parts
        out = [dict(p) for p in parts]
        # 1) 中途加长停顿：在第 2 段及以后随机挑一处，把 delay 拉长
        if len(out) >= 2 and random.random() < h:
            idx = random.randint(1, len(out) - 1)
            base = float(out[idx].get("delay_before_seconds", 0.0))
            out[idx]["delay_before_seconds"] = round(base + h * random.uniform(1.5, 6.0), 3)
        # 2) 欲言又止：中高犹豫时，给某一段尾部追加「……」（半句收住的感觉）
        if h > 0.45 and random.random() < (h * 0.5):
            idx = random.randint(0, len(out) - 1)
            txt = str(out[idx].get("text", "")).rstrip()
            if txt and not txt.endswith(("…", "。", "？", "！", "~")):
                out[idx]["text"] = txt + "……"
        return out

    # ------------------------------------------------------------------
    # 拨动大饼倒计时：Sylanne 内在节律 → 大饼下一次主动发言的时间
    # 复用大饼自己的 _schedule_next_chat_and_save 重排（半官方，有 web_admin 外调先例）。
    # ------------------------------------------------------------------

    @staticmethod
    def _urge_to_minutes(urge: float, quiet: float, lo_min: float, hi_min: float) -> float:
        """把"想说话冲动 vs 想安静"映射到目标倒计时（分钟）。

        urge 高 → 接近 lo_min（早点发）；quiet 高 → 接近 hi_min（拖后）。
        net∈[0,1]：1 表示最想说，0 表示最想安静。线性插值后 clamp 在大饼区间内。
        """
        net = max(0.0, min(1.0, urge - quiet))
        # net=1 → lo_min, net=0 → hi_min
        target = hi_min - net * (hi_min - lo_min)
        return max(lo_min, min(hi_min, target))

    async def adjust_countdown(self, session_key: str) -> dict[str, Any]:
        """根据 Sylanne 当前状态拨动大饼该会话的下一次主动发言倒计时。

        流程（复用 proactive_sylanne 决策，尊重既有 guard 安全阀）：
          1. proactive_sylanne 取 surface + decision；guard 不允许则不拨
          2. 从 surface.body 算 urge=max(need_expression, need_repair) 与 quiet
          3. 映射到 target 分钟（clamp 在大饼 min~max_interval_minutes 之间）
          4. set_override 把 min=max=target（压掉 random）→ 调大饼 _schedule_next_chat_and_save
             重排 → 恢复原 schedule_settings override
        Returns: {"adjusted": bool, "reason": str, "target_minutes": float|None}
        """
        plugin = self._get_proactive_plugin()
        if plugin is None or not hasattr(plugin, "_schedule_next_chat_and_save"):
            return {"adjusted": False, "reason": "proactive_chat_unavailable", "target_minutes": None}

        # 1) 决策 + guard
        getter = getattr(self._p, "proactive_sylanne", None)
        if not callable(getter):
            return {"adjusted": False, "reason": "no_decision_source", "target_minutes": None}
        try:
            surface = await getter(session_key=session_key)
        except Exception as e:
            return {"adjusted": False, "reason": f"decision_error:{type(e).__name__}", "target_minutes": None}
        if not isinstance(surface, dict):
            return {"adjusted": False, "reason": "bad_surface", "target_minutes": None}
        guard = surface.get("guard", {}) if isinstance(surface.get("guard"), dict) else {}
        if guard and guard.get("allowed") is False:
            return {"adjusted": False, "reason": "guard_blocked", "target_minutes": None}

        # 2) 算 urge / quiet（容错取值）
        body = surface.get("body", {}) if isinstance(surface.get("body"), dict) else {}
        needs = body.get("needs", {}) if isinstance(body.get("needs"), dict) else {}
        immunity = body.get("immunity", {}) if isinstance(body.get("immunity"), dict) else {}
        def _f(v: Any) -> float:
            try:
                return float(v)
            except (TypeError, ValueError):
                return 0.0
        urge = max(_f(needs.get("need_expression")), _f(needs.get("need_repair")))
        quiet = max(_f(needs.get("need_quiet")), _f(immunity.get("boundary_pressure")))

        # 3) 目标分钟（clamp 大饼区间）
        sid = self._resolve_origin(session_key)
        conf = self._daping_schedule_conf(sid)
        try:
            lo_min = float(conf.get("min_interval_minutes", 30))
            hi_min = float(conf.get("max_interval_minutes", 900))
        except (TypeError, ValueError):
            lo_min, hi_min = 30.0, 900.0
        if hi_min < lo_min:
            hi_min = lo_min
        decision = surface.get("decision", {}) if isinstance(surface.get("decision"), dict) else {}
        if str(decision.get("action", "")).strip().lower() == "reach_out":
            target = lo_min
        else:
            target = self._urge_to_minutes(urge, quiet, lo_min, hi_min)

        # 4) 压掉 random（min=max=target）→ 调大饼重排 → 还原。issue#43 Wave2：三段式，
        #    锁【不跨】_schedule_next_chat_and_save；RMW 只还原自己的 schedule_settings，
        #    保留并发 dispatch 写的 proactive_prompt（adjust 不碰 pp，故不需 sidecar）。
        mgr = getattr(plugin, "session_override_manager", None)
        prev: dict[str, Any] = {}
        result: dict[str, Any] = {"adjusted": False, "reason": "ok", "target_minutes": None}
        i_own = False
        try:
            # 段1（短锁）：in-flight 去重 → 读基线 → 写 schedule 注入态。
            if mgr is not None:
                async with self._lock_for(sid):
                    if sid in self._inflight_adjust:
                        # 已有 adjust 在飞：第二个不再注入（否则把对方临时 schedule 误当基线 → 残留）
                        return {
                            "adjusted": False,
                            "reason": "adjust_in_flight",
                            "target_minutes": None,
                        }
                    self._inflight_adjust.add(sid)
                    i_own = True
                    try:
                        prev = mgr.get_override(sid) or {}
                    except Exception:
                        prev = {}
                    if not isinstance(prev, dict):
                        prev = {}
                    prev_sched = prev.get("schedule_settings", {})
                    sched_patch = dict(prev)
                    sched_patch["schedule_settings"] = {
                        **(prev_sched if isinstance(prev_sched, dict) else {}),
                        "min_interval_minutes": int(round(target)),
                        "max_interval_minutes": int(round(target)),
                    }
                    try:
                        await mgr.set_override(sid, sched_patch)
                    except Exception as e:
                        logger.warning(
                            f"Sylanne adjust_countdown set_override failed: {e}", exc_info=True
                        )
                        return {
                            "adjusted": False,
                            "reason": f"error:{type(e).__name__}",
                            "target_minutes": None,
                        }

            # 段2（无锁）：调大饼重排倒计时。绝不在锁内 await。
            try:
                await plugin._schedule_next_chat_and_save(sid)
                result = {"adjusted": True, "reason": "ok", "target_minutes": round(target, 2)}
            except Exception as e:
                logger.warning(f"Sylanne adjust_countdown failed: {e}", exc_info=True)
                result = {
                    "adjusted": False,
                    "reason": f"error:{type(e).__name__}",
                    "target_minutes": None,
                }

            return result
        finally:
            if i_own:
                # 段3（在 finally）：RMW 还原 schedule_settings 到基线——无论正常/异常/CancelledError
                # 都尝试还原；取消打断 await 也吞掉（adjust 无 sidecar，残留仅 timing，下次 adjust
                # 会再修，复审 CLUSTER A）。
                if mgr is not None:
                    try:
                        async with self._lock_for(sid):
                            await self._restore_schedule_keys(mgr, sid, prev)
                    except BaseException:
                        pass
                self._inflight_adjust.discard(sid)
