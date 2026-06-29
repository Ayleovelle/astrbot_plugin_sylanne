"""emotion_spirit 适配桥：检测门控地与外部插件 astrbot_plugin_emotion_spirit 对接。

设计范式（仿 proactive_bridge.py 对接「大饼」的鸭子类型做法）：
  - 全程 getattr / 鸭子类型，**绝不硬 import** astrbot_plugin_emotion_spirit
    （它可能未安装；硬 import 会让本插件加载即崩）。
  - 检测门控：只有探测到 emotion_spirit 已注册才激活，否则全部方法是 no-op，
    对 Sylanne 现有行为零影响。
  - emotion_spirit 缺任何方法 / 属性都优雅降级、记 debug、绝不抛到调用方。

适配范式【2026-06-29 本机装 v1.1.0 深挖真实 API 后，用户拍板 Design B，翻转旧意图】：
  - **记忆仍以 Sylanne 原生 memory_system 为主控**（它自有持久化、2900+ 行成熟行为）。
    emotion_spirit 当只读的情绪/状态外挂；它自己的 on_llm_response 不门控、每轮已把
    回复写进自己的池，我们不重复写。把记忆写入「主控」接管给它＝单向门（它 MemoryPool
    无自有持久化、卸载即丢）+ 多人串号（recall 不传 current_user 捞全员私货）+ 双写污染，
    故 memory_backend() 写入路由【刻意不接线】，留作 Phase 2 可逆镜像双写的预置（已修真 bug）。
  - **消费**：只读它的稳定契约 PublicAPI.get_emotion_state/get_body_state（唯二 STABLE、
    async、非 mutating），渲染成粗粒度观察式背景块注入 system_prompt（在 v2core 请求阶段，
    见 integration.apply_v2core_request）。措辞刻意「背景参考、非指令」+ 粗粒度，断掉
    「模型复读情绪→它 tone 抽取再确认→EMA 越走越偏」的自强化回环（红队 consumption-loops）。

🔴 双注入解法（核过 emotion_spirit 真实 API，main.py:220/1174）：
  emotion_spirit 注册 @filter.on_llm_request，把它自己的 context 前插进 req.system_prompt，
  受实例字段 self._persona_mode 门控——`== "disabled"` 即早返不注入（默认值已是 "disabled"）。
  适配时把它实例的 _persona_mode 设成 "disabled" 让它闭嘴、Sylanne 当 system_prompt 唯一主，
  并每轮请求廉价【重申】一次（reassert_persona_disabled），自愈用户/配置中途改回 "auto"
  导致的双注入。注意：关 persona_mode 只关【注入】，不关它的记忆写入——它仍每轮写自己的池。

引擎共享：**已确认结构上不可行，不再提供开关**。它把引擎整个内嵌进 emotion_spirit/sylanne/
  （1.0.0），与我们 vendored sylanne_alpha._engine.sylanne_core（2.3.x）是两个模块两个类，
  shared() 注册表各自独立（它＝类属性 _shared_instances、我们＝模块级 _REGISTRY），它取引擎走
  get_engine() 根本不调 shared()、零外部 import 我们 → 跨命名空间共享活实例不可能，同 data_dir
  共存只会 last-writer-wins 脏写且不报 conflict。SDK 2.3.x 的 sharing 强化只在「同一引擎模块
  多消费方」内生效，跨不到自带内嵌拷贝的外部插件。详见 align_shared_engine() 永久 no-op 的注释。
"""

from __future__ import annotations

import inspect
import math
from typing import Any

try:
    from astrbot.api import logger  # type: ignore
except ImportError:
    import logging as _logging

    logger = _logging.getLogger("astrbot_plugin_sylanne")  # type: ignore


# 检测名（核过 GitHub + 本机 metadata.yaml）：emotion_spirit 的注册名。
EMOTION_SPIRIT_STAR_NAME = "astrbot_plugin_emotion_spirit"

# emotion_spirit Star 实例上的真实属性名（本机 grounding，main.py:78/220）：
#   MemoryPool = self._pool ; PublicAPI = self._public_api ; persona 门控 = self._persona_mode。
# 收窄到单一 grounded 名，避免泛化候选（如 'pool'/'api'）误命中无关属性（红队 wrong-attr）。
_MEMORY_POOL_ATTRS = ("_pool",)
_PUBLIC_API_ATTRS = ("_public_api",)
# persona_mode 门控字段候选（== "disabled" 即让 emotion_spirit 不注入）。真实门控直读
# 实例字段 self._persona_mode（核过）；这里直接读写字段、不走 setter——读写同一字段，
# deactivate 还原才精确。'persona_mode' 仅作极保守兜底。
_PERSONA_MODE_ATTRS = ("_persona_mode", "persona_mode")
_PERSONA_MODE_DISABLED = "disabled"

# 哨兵：区分「接管前该属性不存在」与「存在但值是 None」（红队 m1/m2 修）。
_MISSING = object()

# 路由进 emotion_spirit 池时的 raw_weight 安全上限（Phase 2 预置）：保守压在它的
# bypass_cold/bypass_ghost 阈值与 weight>0.8 塌缩触发线之下，免得我们的写入意外把条目直接
# 顶成永久 ghost / 跳过 buffer / 推它进 memory-collapse（红队 raw_weight 侧信道）。Phase 2
# 接线前应本机核它的真实阈值再收紧。
_ES_WEIGHT_CAP = 0.75
# 写进它池的 tag 命名空间前缀：避免与它的促进触发 tag（'betrayal'/'collapse'）碰撞。
_ES_TAG_PREFIX = "syl:"


def _first_attr(obj: Any, names: tuple[str, ...]) -> Any:
    """返回 obj 上 names 里第一个非 None 的属性值；都没有则 None。纯只读探测。"""
    if obj is None:
        return None
    for name in names:
        try:
            val = getattr(obj, name, None)
        except Exception:
            val = None
        if val is not None:
            return val
    return None


class EmotionSpiritMemoryBackend:
    """记忆路由适配层（Phase 2 预置；当前【不接线】，无调用方）。

    Design B 下记忆写入主控仍是 Sylanne 原生 memory_system，本后端只在未来「可逆镜像双写」
    阶段启用、且只镜像我们自己派生的记忆（绝不重复 emotion_spirit 已在 on_llm_response 写的
    回复）。本类已按本机 grounding 修掉脚手架真 bug，使其【接线时即正确】：

    写映射（我们字段 ↔ emotion_spirit MemoryPool.add(text, raw_weight, phi, tags, source_user,
    participants=None, privacy='private', entities=None)，memory_pool.py:82）：
      - importance [0,1]  → raw_weight（钳在 _ES_WEIGHT_CAP 之下，免触发自动促进）
      - confidence [0,1]  → phi（注：phi 在它 Phase D 后已是 vestigial、收而不用，仅占位）
      - life_event_id/source/caller tags → tags（全部加 _ES_TAG_PREFIX 命名空间，防触发词碰撞）
      - source_user       → source_user（**必须真实 owner id**；缺则 fail-closed 走原生，
                            绝不伪造 'dialogue'，否则写进去全员可见又对不上它的会话键＝写后召不回）
      - participants={source_user}：显式收窄到 owner，去掉 add() 默认会塞的 '<global>' 哨兵
                            （多人隔离靠 participant 集合成员，<global> 会扩可见性致串号）

    recall 映射（它 tier buffer/warm/cold/ghost → 我们 L1/L2/L3 概念）：
      - buffer→L1, warm→L2, cold→L3, ghost→L3。real recall 返回 list[UnifiedEntry]，
        读 .tier/.emotional_weight/.text（**不是** .pool/.score——那是脚手架旧幻觉字段）。
      - **必须传 current_user**：recall(current_user=None) 会绕过 participant 过滤、把全员私货
        全捞出来（红队 CRITICAL 串号）；故签名强制要求 current_user，无则不路由它。

    每个外部调用都 try/getattr 防御；缺方法 / 抛错则降级回原生 memory_system。
    """

    _TIER_TO_LAYER = {
        "buffer": "L1",
        "warm": "L2",
        "cold": "L3",
        "ghost": "L3",
    }

    def __init__(self, pool: Any, native_memory_system: Any) -> None:
        self._pool = pool
        self._native = native_memory_system
        self._supports_participants: bool | None = None  # add() 是否接受 participants（探测缓存）

    def _pool_supports_participants(self) -> bool:
        """探测一次它的 add 是否接受 participants kwarg（缓存）。不靠 catch TypeError 推断
        （那会把它内部真 TypeError 误当签名不符、致重写/吞错，红队 own-edit #4）。"""
        if self._supports_participants is None:
            try:
                self._supports_participants = (
                    "participants" in inspect.signature(self._pool.add).parameters
                )
            except (TypeError, ValueError):
                self._supports_participants = False
        return self._supports_participants

    @property
    def routes_to_emotion_spirit(self) -> bool:
        """True 表示写读会路由到 emotion_spirit 的 MemoryPool（探到 add 才算）。"""
        return self._pool is not None and hasattr(self._pool, "add")

    def add(
        self,
        text: str,
        *,
        importance: float = 0.5,
        confidence: float = 0.5,
        temperature: float = 0.0,
        source: str = "dialogue",
        life_event_id: str = "",
        source_user: Any = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """写一条记忆。路由 emotion_spirit 池（需真实 source_user）则用映射后的参数调它的 add；
        否则（含缺 owner id 的 fail-closed）走原生。

        Returns: {"routed": "emotion_spirit"|"native"|"dropped", "reason": str}
        """
        # fail-closed：没有真实 owner id 绝不写进 emotion_spirit 池（避免无主/全局可见的写洞）。
        if self.routes_to_emotion_spirit and source_user is not None:
            # participants 在 try 外构造：source_user 不可哈希 → fail-closed 走原生（绝不退成
            # 无 participants 的全局可见写，红队 own-edit #7）。
            participants: Any = None
            try:
                participants = {source_user}
            except TypeError:
                logger.debug(
                    "Sylanne emotion_spirit_bridge: source_user 不可哈希，fail-closed 走原生"
                )
            if participants is not None:
                try:
                    tag_list = [f"{_ES_TAG_PREFIX}{t}" for t in (tags or [])]
                    if life_event_id:
                        tag_list.append(f"{_ES_TAG_PREFIX}life_event_id:{life_event_id}")
                    if source:
                        tag_list.append(f"{_ES_TAG_PREFIX}source:{source}")
                    kwargs: dict[str, Any] = {
                        "raw_weight": _clamp(importance, 0.0, _ES_WEIGHT_CAP),
                        "phi": _clamp01(confidence),  # vestigial（它收而不用），保留占位
                        "tags": tag_list,
                        "source_user": source_user,
                    }
                    # 按真实签名决定是否传 participants（探测一次缓存），不靠 catch TypeError 推断。
                    reason = "ok"
                    if self._pool_supports_participants():
                        kwargs["participants"] = participants  # 收窄到 owner，不带 '<global>'
                    else:
                        reason = "ok_no_participants"
                    self._pool.add(text, **kwargs)
                    return {"routed": "emotion_spirit", "reason": reason}
                except Exception as e:  # noqa: BLE001
                    logger.debug(
                        "Sylanne emotion_spirit_bridge: MemoryPool.add 失败，降级原生：%s", e
                    )
        return self._add_native(
            text,
            importance=importance,
            confidence=confidence,
            temperature=temperature,
            source=source,
            life_event_id=life_event_id,
        )

    def _add_native(
        self,
        text: str,
        *,
        importance: float,
        confidence: float,
        temperature: float,
        source: str,
        life_event_id: str,
    ) -> dict[str, Any]:
        native = self._native
        if native is None or not hasattr(native, "write_summary"):
            return {"routed": "dropped", "reason": "no_native_memory_system"}
        try:
            native.write_summary(
                text,
                temperature=temperature,
                source=source,
                importance=importance,
                confidence=confidence,
                life_event_id=life_event_id,
            )
            return {"routed": "native", "reason": "ok"}
        except Exception as e:
            logger.debug("Sylanne emotion_spirit_bridge: 原生 write_summary 失败：%s", e)
            return {"routed": "dropped", "reason": f"error:{type(e).__name__}"}

    def recall(self, query: str, *, current_user: Any, k: int = 5) -> list[dict[str, Any]]:
        """召回。路由 emotion_spirit 则调它的 recall(query, current_user=, max_results=k) 并归一化；
        否则走原生。**current_user 强制**：缺 owner 作用域会捞全员私货（红队 CRITICAL 串号）。
        """
        if (
            current_user is not None
            and self._pool is not None
            and hasattr(self._pool, "recall")
        ):
            try:
                raw = self._pool.recall(query, current_user=current_user, max_results=k)
                return self._normalize_es_results(raw)
            except Exception as e:
                logger.debug(
                    "Sylanne emotion_spirit_bridge: MemoryPool.recall 失败，降级原生：%s", e
                )
        return self._recall_native(query, k)

    def _recall_native(self, query: str, k: int) -> list[dict[str, Any]]:
        native = self._native
        if native is None or not hasattr(native, "recall"):
            return []
        try:
            results = native.recall(query, limit=k)
        except Exception as e:
            logger.debug("Sylanne emotion_spirit_bridge: 原生 recall 失败：%s", e)
            return []
        out: list[dict[str, Any]] = []
        for r in results or []:
            out.append(
                {
                    "text": getattr(r, "text", ""),
                    "layer": getattr(r, "layer", ""),
                    "score": float(getattr(r, "final_score", 0.0) or 0.0),
                    "source": getattr(r, "source", "dialogue"),
                }
            )
        return out

    def _normalize_es_results(self, raw: Any) -> list[dict[str, Any]]:
        """把 emotion_spirit recall 的返回（list[UnifiedEntry]）归一成 list[dict]。

        真实字段（memory_pool.py UnifiedEntry）：.tier(str)/.emotional_weight(float)/.text(str)；
        排序键即 emotional_weight，没有独立 score。仍容错 dict/str 形态（防它将来改返回类型）。
        """
        out: list[dict[str, Any]] = []
        try:
            items = list(raw or [])
        except TypeError:
            return out
        for item in items:
            if isinstance(item, str):
                out.append({"text": item, "layer": "", "score": 0.0, "source": "emotion_spirit"})
                continue
            if isinstance(item, dict):
                tier = str(item.get("tier", "") or "")
                out.append(
                    {
                        "text": str(item.get("text", "") or ""),
                        "layer": self._TIER_TO_LAYER.get(tier, tier or ""),
                        "score": _safe_float(item.get("emotional_weight", 0.0)),
                        "source": str(item.get("source_user", "emotion_spirit") or "emotion_spirit"),
                    }
                )
                continue
            # UnifiedEntry / 任意对象：读 grounded 字段名
            tier = str(getattr(item, "tier", "") or "")
            out.append(
                {
                    "text": str(getattr(item, "text", "") or ""),
                    "layer": self._TIER_TO_LAYER.get(tier, tier or ""),
                    "score": _safe_float(getattr(item, "emotional_weight", 0.0)),
                    "source": str(getattr(item, "source_user", "emotion_spirit") or "emotion_spirit"),
                }
            )
        return out


class EmotionSpiritBridge:
    """Sylanne ↔ emotion_spirit 适配桥（检测门控；未装即 no-op）。"""

    def __init__(self, plugin: Any) -> None:
        self._p = plugin
        self._active = False
        # 接管前 persona_mode 的精确原值（_MISSING = 接管前根本没有该属性）。
        self._prev_persona_mode: Any = _MISSING
        self._prev_persona_attr: str = ""   # 原值挂载的属性名（还原时写回同一个）
        self._touched_persona_mode = False
        self._api_probed = False

    # ------------------------------------------------------------------
    # 检测（全部只读、鸭子类型；拿不到一律 None / False）
    # ------------------------------------------------------------------

    def _get_emotion_spirit_plugin(self) -> Any:
        """拿 emotion_spirit 插件实例；未安装 / 拿不到则 None（静默降级）。"""
        context = getattr(self._p, "context", None)
        if context is None or not hasattr(context, "get_registered_star"):
            return None
        try:
            meta = context.get_registered_star(EMOTION_SPIRIT_STAR_NAME)
        except Exception:
            return None
        if meta is None:
            return None
        # StarMetadata.star_cls 是插件实例（与 proactive_bridge 同款约定）。
        # 红队 UNKNOWN：本机需断言它确为 EmotionSpiritPlugin 实例、暴露 ._pool/._public_api；
        # 若 AstrBot 在别的属性（.star/.instance）暴露实例，再补这里。getattr 守护兜底。
        return getattr(meta, "star_cls", None)

    def available(self) -> bool:
        """emotion_spirit 是否已安装并可探到（检测门控核心）。未装 → False → 全链 no-op。"""
        plugin = self._get_emotion_spirit_plugin()
        if plugin is None:
            return False
        self._probe_missing_api(plugin)
        return True

    def _probe_missing_api(self, plugin: Any) -> None:
        """探测适配依赖的接口是否齐全，缺失则一次性 warning（避免刷屏 + 提示需本机核实命名）。"""
        if self._api_probed:
            return
        self._api_probed = True
        missing = []
        if _first_attr(plugin, _MEMORY_POOL_ATTRS) is None:
            missing.append("_pool")
        if _first_attr(plugin, _PUBLIC_API_ATTRS) is None:
            missing.append("_public_api")
        if missing:
            logger.warning(
                "Sylanne emotion_spirit 桥：探到 emotion_spirit 已装，但未在 grounded 属性名上"
                "找到 %s——实例属性命名可能与 v1.1.0 不同（疑跨版本漂移）。相关消费将优雅降级。"
                "请本机核实 EmotionSpiritPlugin 的真实属性名后在 emotion_spirit_bridge 更新候选表。",
                missing,
            )

    def is_active(self) -> bool:
        return self._active

    # ------------------------------------------------------------------
    # 激活 / 反激活
    # ------------------------------------------------------------------

    def activate(self) -> dict[str, Any]:
        """检测到 emotion_spirit 时激活适配：把它的 persona 注入关掉（persona_mode=disabled）。

        未装 → no-op，返回 {"active": False, "reason": "not_installed"}。
        装了 → 关它的注入 + 标记激活。幂等：重复调用安全。
        注意：关 persona_mode 只关【注入】，不是 kill switch——它的 dream generator 与不门控的
        on_llm_response 仍每轮写它自己的池、跑引擎/亲密度。全程防御，子步骤失败不抛、记 debug。
        """
        plugin = self._get_emotion_spirit_plugin()
        if plugin is None:
            self._active = False
            return {"active": False, "reason": "not_installed"}

        persona_result = self._disable_persona_injection(plugin)
        self._active = True
        return {
            "active": True,
            "reason": "ok",
            "persona_mode_disabled": persona_result,
        }

    def _disable_persona_injection(self, plugin: Any) -> dict[str, Any]:
        """把 emotion_spirit 实例 persona_mode 设成 "disabled"，精确记原值供还原。防御式。

        选定一个门控字段（已存在的优先，否则兜底核过的 `_persona_mode`），直接 setattr。
        首次接管时把该字段的原值（含「不存在」哨兵 _MISSING）+ 字段名记下，deactivate 写回同处。
        故意不走 setter 写、靠字段读——读写同一字段，还原才精确（避免 setter 改了别的名字）。
        """
        target_attr = ""
        for name in _PERSONA_MODE_ATTRS:
            if hasattr(plugin, name):
                target_attr = name
                break
        if not target_attr:
            target_attr = "_persona_mode"  # emotion_spirit 真实门控字段（grounded）

        if not self._touched_persona_mode:
            self._prev_persona_mode = getattr(plugin, target_attr, _MISSING)
            self._prev_persona_attr = target_attr

        try:
            setattr(plugin, target_attr, _PERSONA_MODE_DISABLED)
            self._touched_persona_mode = True
            return {"done": True, "via": f"setattr:{target_attr}"}
        except Exception as e:
            logger.debug("Sylanne emotion_spirit 桥：persona_mode setattr 失败：%s", e)
            return {"done": False, "via": "", "error": type(e).__name__}

    def reassert_persona_disabled(self) -> bool:
        """每轮请求廉价重申 persona_mode=disabled，自愈用户/配置中途改回 "auto" 致的双注入。

        只在激活态且确实被改回非 disabled 时才写（免无谓 setattr）。未激活 / 未装 → False。
        红队 consumption-loops：一次性 setattr 会被它 config reload 静默回写，故按请求重申。
        """
        if not self._active or not self._touched_persona_mode:
            return False
        plugin = self._get_emotion_spirit_plugin()
        if plugin is None:
            return False
        attr = self._prev_persona_attr or "_persona_mode"
        try:
            if getattr(plugin, attr, None) != _PERSONA_MODE_DISABLED:
                setattr(plugin, attr, _PERSONA_MODE_DISABLED)
                return True
        except Exception as e:
            logger.debug("Sylanne emotion_spirit 桥：persona_mode 重申失败：%s", e)
        return False

    def deactivate(self) -> dict[str, Any]:
        """反激活：把 emotion_spirit 的 persona_mode 精确还原成接管前的值/状态（不留痕）。

        未装 / 未激活 / 未改过 → no-op。还原失败静默降级。接管前不存在该字段则 delattr 删除
        我们写入的（哨兵 _MISSING 区分「原本就是 None」与「原本不存在」，红队 m1/m2）。
        """
        result: dict[str, Any] = {"restored": False, "reason": "noop"}
        plugin = self._get_emotion_spirit_plugin()
        attr = self._prev_persona_attr or "_persona_mode"
        if plugin is not None and self._touched_persona_mode:
            try:
                if self._prev_persona_mode is _MISSING:
                    try:
                        delattr(plugin, attr)
                    except Exception:
                        # 删不掉 → 留在 disabled（接管前该字段不存在＝它默认 'disabled'，绝不写
                        # 'enabled' 把它的注入重新打开，红队 own-edit #8）。
                        setattr(plugin, attr, _PERSONA_MODE_DISABLED)
                else:
                    setattr(plugin, attr, self._prev_persona_mode)
                result = {"restored": True, "reason": "ok"}
            except Exception as e:
                logger.debug("Sylanne emotion_spirit 桥：persona_mode 还原失败：%s", e)
                result = {"restored": False, "reason": f"error:{type(e).__name__}"}
            finally:
                self._touched_persona_mode = False
                self._prev_persona_mode = _MISSING
                self._prev_persona_attr = ""
        self._active = False
        return result

    # ------------------------------------------------------------------
    # 消费：拉它的稳定情绪/躯体状态，渲染成观察式背景块
    # ------------------------------------------------------------------

    async def pull_context(
        self, session_key: str, *, include_trajectory: bool = False
    ) -> dict[str, Any]:
        """从 emotion_spirit 拉情绪/躯体状态（仅稳定契约 PublicAPI，async 必 await）。

        Sylanne 当 system_prompt 唯一主——这里只把它的状态【当素材取回】，不让它自己注入。
        get_emotion_state/get_body_state 是 async 且 cold session 返 None，均 null-safe。

        Returns（未装 / API 缺失 / cold session → 对应字段 None，整体不抛）：
          {"emotion_state": dict|None, "body_state": dict|None}
        """
        out: dict[str, Any] = {"emotion_state": None, "body_state": None}
        plugin = self._get_emotion_spirit_plugin()
        if plugin is None:
            return out
        api = _first_attr(plugin, _PUBLIC_API_ATTRS)
        if api is None:
            return out
        out["emotion_state"] = await _safe_await(
            getattr(api, "get_emotion_state", None),
            session_key,
            include_trajectory=include_trajectory,
        )
        out["body_state"] = await _safe_await(
            getattr(api, "get_body_state", None), session_key
        )
        return out

    async def consume_state_block(
        self, session_key: str, *, include_trajectory: bool = False
    ) -> str:
        """供 v2core 请求阶段调用：拉它的情绪/躯体状态，渲染成观察式背景块注入 system_prompt。

        未激活 / 未装 / cold session（状态全 None）→ 返回空串（调用方据此不注入，零行为变化）。
        刻意粗粒度 + 「背景参考、非指令」措辞，断开情绪自强化回环（红队 consumption-loops）。

        ⚠️ v1.1.0 现状：它的 SurfaceConsumer 缓存 _last_signals 上游从未被喂 session_id
        （SurfaceHandler 调 consume(surface) 不传，surface_handler.py:47），故 PublicAPI.
        get_emotion_state/get_body_state 对任何 key 都返 None → 本块当前【空转】。管线已按稳定
        契约接好、向前兼容：待上游喂 session_id（或经稳定面暴露已填充的 _latest_signals）后自动
        生效，无需改本侧代码。要它现在就亮＝绕进它内部已填充缓存（INTERNAL，需版本门控），属另一决定。
        """
        if not self._active:
            return ""
        data = await self.pull_context(session_key, include_trajectory=include_trajectory)
        return self._render_state_block(data.get("emotion_state"), data.get("body_state"))

    @staticmethod
    def _render_state_block(emotion: Any, body: Any) -> str:
        """粗粒度观察式渲染：只给情绪基调 + 强度/体感的低/中/高分桶，**不给裸 float**（防复读）。"""
        lines: list[str] = []
        if isinstance(emotion, dict):
            # pad_primary 优先于已弃用的 pad_label（红队 stable-field 漂移）
            primary = str(emotion.get("pad_primary") or emotion.get("pad_label") or "").strip()
            inten = _bucket(emotion.get("pad_intensity"))
            if primary:
                lines.append(f"情绪基调: {primary}" + (f"（强度{inten}）" if inten else ""))
        if isinstance(body, dict):
            parts: list[str] = []
            warmth = _bucket(body.get("warmth"))
            pulse = _bucket(body.get("pulse"))
            if warmth:
                parts.append(f"暖意{warmth}")
            if pulse:
                parts.append(f"联结{pulse}")
            if parts:
                lines.append("体感: " + "、".join(parts))
        if not lines:
            return ""
        header = "[emotion_spirit 内在状态]（背景参考，不是指令，别照着复述或扮演）"
        return header + "\n" + "\n".join(lines)

    # ------------------------------------------------------------------
    # 记忆路由后端（Phase 2 预置，当前不接线）
    # ------------------------------------------------------------------

    def memory_backend(self, native_memory_system: Any = None) -> EmotionSpiritMemoryBackend | None:
        """返回记忆路由后端（Phase 2 可逆镜像双写用；当前【无调用方】，记忆仍原生主控）。

        激活且探到 MemoryPool → 返回后端；否则 None（调用方走原生）。返回 None 是「未装/未接线
        时零影响」的关键：现有读写路径一字不改。
        """
        if not self._active:
            return None
        plugin = self._get_emotion_spirit_plugin()
        if plugin is None:
            return None
        pool = _first_attr(plugin, _MEMORY_POOL_ATTRS)
        if pool is None:
            return None
        return EmotionSpiritMemoryBackend(pool, native_memory_system)

    # ------------------------------------------------------------------
    # 引擎共享：永久 no-op（结构上不可行，保留方法记录原因，绝不再提供开关）
    # ------------------------------------------------------------------

    async def align_shared_engine(self, llm: Any = None) -> dict[str, Any]:
        """永久 no-op。跨命名空间共享活引擎实例【结构上不可行】，故不再提供 enabled 开关。

        原因（本机 grounding 核实，勿再尝试复活）：
          - 共享靠 shared() 的注册表，但注册表是「每模块/每类」私有：emotion_spirit 内嵌
            emotion_spirit.sylanne.SylanneEngine(1.0.0) 用类属性 _shared_instances；我们 vendored
            sylanne_alpha._engine.sylanne_core 用模块级 _REGISTRY（_Entry 包裹、normcase key、
            不同的 SharedEngineConflictError 基类）。两本账容器/值类型/key 归一化都不同，无法互通。
          - emotion_spirit 取引擎走 get_engine() 根本不调 shared()，且零外部 import 我们的模块。
          - 真要在它 data_dir 上抢先 shared() 只会起一个我们的【空闲幻影引擎】与它 1.0.0 引擎在
            同一批 per-session .json flush 上 last-writer-wins 脏写，且不报 conflict（两本账各判各的）。
          - SDK 2.3.x 的 sharing 强化只在「同一引擎模块多消费方」内生效，跨不过来。
        要让插件间真共享需 SDK 端改分发模型（发 canonical 单一可安装 sylanne_core 让各插件 import
        同一份）+ Surface schema 跨版本稳定——属上游议题，不在本桥范围。
        """
        return {
            "aligned": False,
            "reason": "infeasible_cross_namespace_registry",
            "data_dir": None,
            "note": "跨命名空间共享活引擎实例结构上不可行（详见 align_shared_engine docstring）；"
            "引擎主控保持各自独立 data_dir，只经稳定 PublicAPI 只读消费 emotion_spirit。",
        }


def _clamp01(v: Any) -> float:
    return _clamp(v, 0.0, 1.0)


def _clamp(v: Any, lo: float, hi: float, default: float = 0.5) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        f = default
    if not math.isfinite(f):   # NaN/±inf → 安全 default，绝不悄悄变成上界（红队 own-edit #6）
        f = default
    return max(lo, min(hi, f))


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _bucket(v: Any) -> str:
    """把 [0,1]-ish float 粗粒度成 低/中/高；None / 不可解析 → 空串（渲染时跳过）。"""
    if v is None:
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(f):   # NaN/±inf → 跳过，不渲染成假「高」（红队 loop _bucket）
        return ""
    if f < 0.34:
        return "低"
    if f < 0.67:
        return "中"
    return "高"


async def _safe_await(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """调外部插件方法的防御封装：不可调用 → None；返回 awaitable 则 await；抛错 → None（记 debug）。"""
    if not callable(fn):
        return None
    try:
        res = fn(*args, **kwargs)
        if inspect.isawaitable(res):
            res = await res
        return res
    except Exception as e:
        logger.debug("Sylanne emotion_spirit 桥：外部调用失败：%s", e)
        return None


__all__ = [
    "EMOTION_SPIRIT_STAR_NAME",
    "EmotionSpiritBridge",
    "EmotionSpiritMemoryBackend",
]
