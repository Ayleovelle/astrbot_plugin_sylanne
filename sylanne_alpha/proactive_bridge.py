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

import random
import time
from typing import Any

try:
    from astrbot.api import logger  # type: ignore
except ImportError:
    import logging as _logging

    logger = _logging.getLogger("astrbot_plugin_sylanne")  # type: ignore


PROACTIVE_CHAT_STAR_NAME = "astrbot_plugin_proactive_chat"


class ProactiveBridge:
    """Sylanne → 大饼 主动发言桥接器。"""

    def __init__(self, plugin: Any) -> None:
        self._p = plugin
        # 每会话上次桥接触发时间（用于间隔节流，复用大饼的 min_interval 公式）
        self._last_bridge_dispatch: dict[str, float] = {}
        # 待 Sylanne 接管分段的 origin 集合：dispatch 时标记，on_decorating_result 钩子消费。
        # key = 大饼实际发送用的 origin（unified_msg_origin）
        self._pending_segment_takeover: set[str] = set()

    def forget_session(self, session_key: str) -> None:
        """释放某会话在桥接层的残留态（CP8-P6：会话删除/驱逐时清理，防无界增长）。

        session_key 经 _resolve_origin 转 origin 后才是 _last_bridge_dispatch 的键，
        故两种键都尝试清除（origin 解析可能因映射已被清而回退，双清更稳妥）。
        """
        self._last_bridge_dispatch.pop(session_key, None)
        try:
            origin = self._resolve_origin(session_key)
            self._last_bridge_dispatch.pop(origin, None)
            self._pending_segment_takeover.discard(origin)
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

        # 备份原 override，注入素材，触发，恢复
        prev: dict[str, Any] = {}
        try:
            prev = mgr.get_override(sid) or {}
        except Exception:
            prev = {}
        patched = {**prev, "proactive_prompt": motivation_text}
        # 分段接管：关掉大饼自己的分段，并登记接管标记，由 on_decorating_result 钩子消费
        takeover = self._segment_takeover_enabled()
        if takeover:
            prev_seg = prev.get("segmented_reply_settings", {})
            patched["segmented_reply_settings"] = {
                **(prev_seg if isinstance(prev_seg, dict) else {}),
                "enable": False,
            }
            self._pending_segment_takeover.add(sid)
        try:
            await mgr.set_override(sid, patched)
            await check_and_chat(sid)
            # 记录触发时间，供 min_interval 节流闸门使用
            self._last_bridge_dispatch[sid] = time.time()
            return {"dispatched": True, "reason": "ok"}
        except Exception as e:
            logger.warning(f"Sylanne proactive_bridge dispatch failed: {e}", exc_info=True)
            return {"dispatched": False, "reason": f"error:{type(e).__name__}"}
        finally:
            # 用完即清：有原值写回，无则删除
            try:
                if prev:
                    await mgr.set_override(sid, prev)
                else:
                    await mgr.delete_override(sid)
            except Exception as e:
                logger.warning(
                    f"Sylanne proactive_bridge override restore failed: {e}"
                )
            # 防御性清理：钩子正常会消费掉标记，万一未触发则在此移除，避免误伤后续消息
            self._pending_segment_takeover.discard(sid)

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

    def hesitation_plan(self, body: dict[str, Any]) -> dict[str, Any]:
        """根据犹豫强度产出本次主动发言的犹豫计划。

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
        # 踌躇词试探：中高犹豫时偶尔加
        filler = ""
        if h > 0.4 and random.random() < (h * 0.6):
            filler = random.choice(["那个……", "嗯…", "在吗？我", "诶，", "…话说，"])
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

        # 4) 压掉 random（min=max=target）→ 调大饼重排 → 恢复
        mgr = getattr(plugin, "session_override_manager", None)
        prev: dict[str, Any] = {}
        if mgr is not None:
            try:
                prev = mgr.get_override(sid) or {}
            except Exception:
                prev = {}
        try:
            if mgr is not None:
                sched_patch = dict(prev)
                sched_patch["schedule_settings"] = {
                    **(prev.get("schedule_settings", {}) if isinstance(prev.get("schedule_settings"), dict) else {}),
                    "min_interval_minutes": int(round(target)),
                    "max_interval_minutes": int(round(target)),
                }
                await mgr.set_override(sid, sched_patch)
            await plugin._schedule_next_chat_and_save(sid)
            return {"adjusted": True, "reason": "ok", "target_minutes": round(target, 2)}
        except Exception as e:
            logger.warning(f"Sylanne adjust_countdown failed: {e}", exc_info=True)
            return {"adjusted": False, "reason": f"error:{type(e).__name__}", "target_minutes": None}
        finally:
            if mgr is not None:
                try:
                    if prev:
                        await mgr.set_override(sid, prev)
                    else:
                        await mgr.delete_override(sid)
                except Exception as e:
                    logger.warning(f"Sylanne adjust_countdown override restore failed: {e}")
