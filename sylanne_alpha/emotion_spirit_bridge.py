"""emotion_spirit 适配桥：检测门控地与外部插件 astrbot_plugin_emotion_spirit 对接。

设计范式（仿 proactive_bridge.py 对接「大饼」的鸭子类型做法）：
  - 全程 getattr / 鸭子类型，**绝不硬 import** astrbot_plugin_emotion_spirit
    （它当前未安装；硬 import 会让本插件加载即崩）。
  - 检测门控：只有探测到 emotion_spirit 已注册才激活，否则全部方法是 no-op，
    对 Sylanne 现有行为零影响。
  - emotion_spirit 缺任何方法 / 属性都优雅降级、记 debug、绝不抛到调用方。

用户确认的适配意图（见 MEMORY「emotion_spirit 适配意图」）：
  - 记忆主控交给 emotion_spirit（它的 4 层池 MemoryPool）；
  - 计算引擎主控归我们的 vendored sylanne_core 2.3.x。

🔴 双注入解法（核过 emotion_spirit 真实 API）：
  emotion_spirit 注册 @filter.on_llm_request，会把它自己的 context 前插进
  req.system_prompt。它的注入受实例字段 self._persona_mode 门控——`== "disabled"`
  即早返不注入。适配时把它实例的 persona_mode 设成 "disabled" 让它闭嘴，Sylanne 当
  system_prompt 唯一主、自己经 pull_context() 拉它的 context 合并。

引擎共享（保守、默认关）：
  SDK 已有 SylanneEngine.shared(data_dir, llm) 按 resolved data_dir 去重做单例，
  「谁先 shared(data_dir) 谁是 master」。emotion_spirit 的 data_dir 经核为
  <astrbot_data>/plugin_data/emotion_spirit/sylanne_sessions。理论上让 Sylanne 检测到它
  时在【那个 data_dir】先 init shared()，它后调就拿到我们的实例。但：
    ① 它内嵌的引擎版本未知，与我们 2.3.x 的 SylanneConfig 不一致会抛
       SharedEngineConflictError；
    ② 我们自己生产路径目前并不走 shared()（走 EngineFacade 直接 new）。
  故引擎共享做成「可启用但默认保守」——默认关闭，需本机装上 emotion_spirit 核实其内嵌
  引擎版本后才建议开启。见 align_shared_engine() 的 docstring 与返回的 note 字段。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from astrbot.api import logger  # type: ignore
except ImportError:
    import logging as _logging

    logger = _logging.getLogger("astrbot_plugin_sylanne")  # type: ignore


# 检测名（核过 GitHub）：emotion_spirit 的注册名。
EMOTION_SPIRIT_STAR_NAME = "astrbot_plugin_emotion_spirit"

# emotion_spirit Star 实例上「记忆池 / 公共 API / 提示注入器」可能挂载的属性名候选。
# 它当前未安装、实例属性路径无法本机 grounding，故按多个常见命名探测并优雅降级。
# 装上本机后应核实真实属性名，收窄此表（见返回 note）。
_MEMORY_POOL_ATTRS = ("memory_pool", "_memory_pool", "memorypool", "pool", "_pool")
_PUBLIC_API_ATTRS = ("public_api", "_public_api", "publicapi", "api", "_api")
_PROMPT_INJECTOR_ATTRS = (
    "prompt_injector",
    "_prompt_injector",
    "promptinjector",
    "injector",
    "_injector",
)
# persona_mode 门控字段候选（== "disabled" 即让 emotion_spirit 不注入）。
# emotion_spirit 的真实门控是直接读实例字段 self._persona_mode（核过），故这里直接读写
# 字段、不走 setter——读写同一字段，deactivate 还原才精确。
_PERSONA_MODE_ATTRS = ("_persona_mode", "persona_mode")
_PERSONA_MODE_DISABLED = "disabled"

# 哨兵：区分「接管前该属性不存在」与「存在但值是 None」（红队 m1/m2 修）。
_MISSING = object()


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
    """记忆路由适配层：装了 emotion_spirit 则写读路由它的 MemoryPool，否则走原生 memory_system。

    映射（我们的字段 ↔ emotion_spirit MemoryPool.add(text, raw_weight, phi, tags, source_user)）：
      - importance (我们 [0,1])      → raw_weight
      - confidence / |temperature|   → phi（显著性/精度近似；缺则用 importance 兜底）
      - life_event_id + source       → tags（list，保留去重键与来源）
      - source / 用户标识            → source_user

    recall 映射（它 4 层池 buffer/warm/cold/ghost → 我们 L1/L2/L3 概念）：
      - buffer → L1, warm → L2, cold → L3, ghost → L3(ghost)
      返回归一化的 list[dict]（text/layer/score/source），返回形态未知时尽量容错读取。

    每个外部调用都 try/getattr 防御；emotion_spirit 池缺方法 / 抛错则降级回原生 memory_system，
    绝不让记忆写读因适配失败而中断主流程。
    """

    _POOL_TO_LAYER = {
        "buffer": "L1",
        "warm": "L2",
        "cold": "L3",
        "ghost": "L3",
    }

    def __init__(self, pool: Any, native_memory_system: Any) -> None:
        self._pool = pool
        self._native = native_memory_system

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
        """写一条记忆。路由到 emotion_spirit 池则用映射后的参数调它的 add；否则走原生。

        Returns: {"routed": "emotion_spirit"|"native"|"dropped", "reason": str}
        """
        if self.routes_to_emotion_spirit:
            try:
                raw_weight = _clamp01(importance)
                # phi = 显著性/精度近似，直接取 confidence（[0,1]，默认 0.5）；0.0 是合法值，
                # 不用 `or` 偷换（红队 n1）。
                phi = _clamp01(confidence)
                tag_list = list(tags or [])
                if life_event_id:
                    tag_list.append(f"life_event_id:{life_event_id}")
                if source:
                    tag_list.append(f"source:{source}")
                su = source_user if source_user is not None else source
                self._pool.add(
                    text,
                    raw_weight=raw_weight,
                    phi=phi,
                    tags=tag_list,
                    source_user=su,
                )
                return {"routed": "emotion_spirit", "reason": "ok"}
            except Exception as e:
                logger.debug(
                    "Sylanne emotion_spirit_bridge: MemoryPool.add 失败，降级原生记忆：%s", e
                )
                # fall through to native
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

    def recall(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        """召回。路由到 emotion_spirit 则调它的 recall(query, k) 并归一化；否则走原生。"""
        if self._pool is not None and hasattr(self._pool, "recall"):
            try:
                raw = self._pool.recall(query, k=k)
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
        """把 emotion_spirit recall 的未知返回形态归一成 list[dict]（容错鸭子类型）。"""
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
                pool = str(item.get("pool", "") or "")
                out.append(
                    {
                        "text": str(item.get("text", "") or ""),
                        "layer": self._POOL_TO_LAYER.get(pool, pool or ""),
                        "score": _safe_float(item.get("score", item.get("raw_weight", 0.0))),
                        "source": str(item.get("source_user", "emotion_spirit") or "emotion_spirit"),
                    }
                )
                continue
            # 任意对象：getattr 探测
            pool = str(getattr(item, "pool", "") or "")
            out.append(
                {
                    "text": str(getattr(item, "text", "") or ""),
                    "layer": self._POOL_TO_LAYER.get(pool, pool or ""),
                    "score": _safe_float(
                        getattr(item, "score", getattr(item, "raw_weight", 0.0))
                    ),
                    "source": str(getattr(item, "source_user", "emotion_spirit") or "emotion_spirit"),
                }
            )
        return out


class EmotionSpiritBridge:
    """Sylanne ↔ emotion_spirit 适配桥（检测门控；未装即 no-op）。"""

    # 激活时记下我们改过的 persona_mode 原值，deactivate 时还原（不留痕）。
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
        # StarMetadata.star_cls 是插件实例（与 proactive_bridge 同款约定）
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
            missing.append("memory_pool")
        if _first_attr(plugin, _PUBLIC_API_ATTRS) is None:
            missing.append("public_api")
        if _first_attr(plugin, _PROMPT_INJECTOR_ATTRS) is None:
            missing.append("prompt_injector")
        if missing:
            logger.warning(
                "Sylanne emotion_spirit 桥：探到 emotion_spirit 已装，但未在常见属性名上找到 %s"
                "——实例属性命名可能与预期不同，相关适配将优雅降级。请本机核实 "
                "EmotionSpiritPlugin 的真实属性名后在 emotion_spirit_bridge 收窄候选表。",
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
        装了 → 关它的注入 + 标记激活，返回各动作结果。幂等：重复调用安全。
        全程防御，任何子步骤失败都不抛、记 debug、整体仍尽量激活成功。
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
        # 选定写入目标字段（已存在的门控字段优先，否则 grounded 的 _persona_mode）
        target_attr = ""
        for name in _PERSONA_MODE_ATTRS:
            if hasattr(plugin, name):
                target_attr = name
                break
        if not target_attr:
            target_attr = "_persona_mode"  # emotion_spirit 真实门控字段（grounded）

        # 首次接管：精确记录原值（_MISSING 表示接管前该字段不存在）+ 字段名
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
                    # 接管前没有该字段 → 删掉我们写入的（删不掉则置回中性 "enabled"）
                    try:
                        delattr(plugin, attr)
                    except Exception:
                        setattr(plugin, attr, "enabled")
                else:
                    # 接管前有该字段（含值是 None 的情形）→ 原值写回原字段
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
    # 拉 context 合并（get_emotion_state / get_body_state / build_context）
    # ------------------------------------------------------------------

    def pull_context(self, session_key: str, *, include_trajectory: bool = False) -> dict[str, Any]:
        """从 emotion_spirit 拉情绪/躯体/上下文，供 Sylanne 合进自己的 system_prompt。

        Sylanne 当 system_prompt 唯一主——这里只把 emotion_spirit 的 context **当素材取回**，
        不让它自己注入（注入已被 activate() 关掉）。

        Returns（未装 / 各 API 缺失 → 对应字段为 None，整体不抛）：
          {"emotion_state": dict|None, "body_state": dict|None, "context": str|None}
        """
        out: dict[str, Any] = {"emotion_state": None, "body_state": None, "context": None}
        plugin = self._get_emotion_spirit_plugin()
        if plugin is None:
            return out

        api = _first_attr(plugin, _PUBLIC_API_ATTRS)
        if api is not None:
            out["emotion_state"] = _safe_call(
                getattr(api, "get_emotion_state", None),
                session_key,
                include_trajectory=include_trajectory,
            )
            out["body_state"] = _safe_call(
                getattr(api, "get_body_state", None), session_key
            )

        injector = _first_attr(plugin, _PROMPT_INJECTOR_ATTRS)
        if injector is not None:
            ctx = _safe_call(getattr(injector, "build_context", None), session_key)
            if ctx is not None:
                out["context"] = ctx if isinstance(ctx, str) else str(ctx)
        return out

    # ------------------------------------------------------------------
    # 记忆路由后端
    # ------------------------------------------------------------------

    def memory_backend(self, native_memory_system: Any = None) -> EmotionSpiritMemoryBackend | None:
        """返回记忆路由后端：激活且探到 MemoryPool → 路由它；否则 None（调用方走原生）。

        返回 None 是「未装时零影响」的关键：调用方据此继续用现有原生 memory_system，
        现有读写路径一字不改。
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
    # 引擎共享对齐（保守、默认关；需本机核实内嵌引擎版本才建议开）
    # ------------------------------------------------------------------

    def _emotion_spirit_data_dir(self) -> Path | None:
        """推算 emotion_spirit 的 sylanne_sessions data_dir（核过：plugin_data/emotion_spirit/sylanne_sessions）。

        优先读它实例上可能暴露的 data_dir 属性；否则按已 grounding 的相对路径基于
        astrbot data path 推算。emotion_spirit 未安装（plugin is None）→ None：绝不为一个
        不存在的插件凭空合成路径（否则 align_shared_engine 会在未装时建出真引擎，破 no-op）。
        astrbot 不可用 → None。
        """
        plugin = self._get_emotion_spirit_plugin()
        if plugin is None:
            return None
        # 1) 实例若暴露 data_dir，直接信它（最权威）
        for name in ("data_dir", "_data_dir", "sessions_dir", "_sessions_dir"):
            val = getattr(plugin, name, None)
            if val:
                try:
                    return Path(str(val))
                except Exception:
                    pass
        # 2) 按 grounded 相对路径推算
        try:
            from astrbot.core.utils.astrbot_path import get_astrbot_data_path  # type: ignore

            base = Path(get_astrbot_data_path())
        except Exception:
            return None
        return base / "plugin_data" / "emotion_spirit" / "sylanne_sessions"

    async def align_shared_engine(
        self, llm: Any, *, enabled: bool = False, config: Any = None
    ) -> dict[str, Any]:
        """（保守、默认关）在 emotion_spirit 的 data_dir 上先 init shared()，抢占成 master。

        原理：SDK 的 SylanneEngine.shared(data_dir, llm) 按 resolved data_dir 去重做单例，
        谁先 shared 谁是 master。若 Sylanne 在 emotion_spirit 启动前先 shared 它的 data_dir，
        emotion_spirit 后调 shared 就拿到我们的 2.3.x 实例 → 引擎主控归我们。

        ⚠️ 默认关闭（enabled=False → no-op）。开启前置条件（必须本机核实）：
          - emotion_spirit 内嵌引擎版本未知；与我们 SylanneConfig 不一致会抛
            SharedEngineConflictError（本函数已捕获并降级，但意味着抢占失败）。
          - 需确认 emotion_spirit 确实经 SylanneEngine.shared(同一 data_dir) 取引擎，
            而非自己 new。
          - 时序需保证 Sylanne 这步在 emotion_spirit 引擎初始化之前发生。

        Returns: {"aligned": bool, "reason": str, "data_dir": str|None, "note": str}
        note 永远提示：需本机核实内嵌引擎版本才能开引擎共享。
        """
        note = "需本机装上 emotion_spirit 核实其内嵌引擎版本/取引擎方式，确认无 config 冲突后才建议开启引擎共享。"
        if not enabled:
            return {"aligned": False, "reason": "disabled_by_default", "data_dir": None, "note": note}
        # 检测门控（最关键）：emotion_spirit 没装就没有可对齐的对象 —— 直接 no-op，绝不凭空
        # 在它的 data_dir 上建引擎（否则破「未装零影响」铁律，红队 B1）。
        if self._get_emotion_spirit_plugin() is None:
            return {"aligned": False, "reason": "not_installed", "data_dir": None, "note": note}
        if llm is None or not callable(llm):
            return {"aligned": False, "reason": "no_llm_callable", "data_dir": None, "note": note}
        data_dir = self._emotion_spirit_data_dir()
        if data_dir is None:
            return {"aligned": False, "reason": "data_dir_unresolved", "data_dir": None, "note": note}
        try:
            from sylanne_alpha._engine.sylanne_core import SylanneEngine
        except Exception as e:
            return {
                "aligned": False,
                "reason": f"engine_import_failed:{type(e).__name__}",
                "data_dir": str(data_dir),
                "note": note,
            }
        shared = getattr(SylanneEngine, "shared", None)
        if shared is None or not callable(shared):
            return {
                "aligned": False,
                "reason": "shared_unavailable",
                "data_dir": str(data_dir),
                "note": note,
            }
        try:
            kwargs = {"config": config} if config is not None else {}
            await shared(data_dir, llm, **kwargs)
            return {"aligned": True, "reason": "ok", "data_dir": str(data_dir), "note": note}
        except Exception as e:
            logger.warning(
                "Sylanne emotion_spirit 桥：引擎共享对齐失败（%s）——保守降级，不影响现有引擎。",
                type(e).__name__,
            )
            return {
                "aligned": False,
                "reason": f"error:{type(e).__name__}",
                "data_dir": str(data_dir),
                "note": note,
            }


def _clamp01(v: Any) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.5


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _safe_call(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """调外部插件方法的防御封装：不可调用 / 抛错 → None（记 debug）。"""
    if not callable(fn):
        return None
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        logger.debug("Sylanne emotion_spirit 桥：外部调用失败：%s", e)
        return None


__all__ = [
    "EMOTION_SPIRIT_STAR_NAME",
    "EmotionSpiritBridge",
    "EmotionSpiritMemoryBackend",
]
