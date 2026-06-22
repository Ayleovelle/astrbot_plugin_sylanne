"""Phase 2B / PR-H：壳层关系层（is_romantic 判定 + 身份门控 + /bond + 持久化）。

壳层模块（非 SDK 内部）。读 PR-G 累积的 relationship_register_state + intimacy_override，
经身份门控（owner sender_id）判会话是否亲密，供 life-sim 路由（PR-I）等消费方调用。

身份门控（防对抗性注入，handoff 0bis）：
- 内容信号（rel_register）可伪造，只有身份不可伪造 → 自动晋升仅对 owner 会话生效。
- owner_id 仅来自配置 sylanne_alpha_owner_id（无 TOFU 抢注）；空 → 全禁自动晋升 + /bond 拒绝。

判定优先级（handoff §3.2）：
  ① intimacy_override 存在 → 用覆盖（owner-gated /bond 写入，写时已带身份，不再门控）
  ② 否则自动晋升：仅当 register_state[session].sender_id == owner_id
     且 romantic_conf ≥ 阈 且 sample_count ≥ 最小样本

契约：is_romantic 只许门控路由/召回，禁用于改变 Sylanne 自身表达亲密语域的生成（防自证循环）。
"""

from __future__ import annotations

from typing import Any

try:
    from astrbot.api import logger  # type: ignore
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger("astrbot_plugin_sylanne")

# 标定依据（解析推导，与 rel_register._accumulate 配套；handoff §7 占位收敛为有据值）：
# conf 累积 n 大时 → 友好误判占比 p；"友好不误升"要求阈值 > p。纯浪漫 ratio=1、
# N=8 下 n=5 → conf=0.625。取 0.6 + 最小样本 5：浪漫第 5 有效样本即晋升，友好需
# p>0.6（>60% 轮被误判）才误升；文献高频爱称友好语料误判 ~20-35%，0.6 保守压其上。
# ⚠ 真机实测 p 后微调仍 deferred（协议见 phase-2c handoff 草案）。
_ROMANTIC_THRESHOLD = 0.6
_MIN_SAMPLE = 5

_KV_KEY = "sylanne_relationship_state"


def _owner_id(plugin: Any) -> str:
    cfg = getattr(plugin, "config", None) or {}
    return str(cfg.get("sylanne_alpha_owner_id", "") or "")


def _event_sender_id(event: Any) -> str:
    """robust accessor：sender_id → user_id → get_sender_id()。

    AstrBot 部分平台事件把发送者 ID 存在 user_id（非 sender_id）；漏 user_id 回落
    会让这些平台上 owner 认证失败 → 身份门控 fail-closed 误判 + /bond 被错拒。
    本函数是 sender_id 解析的唯一来源（rel_register 等调用方复用，禁止另起重复逻辑）。
    """
    sid = str(getattr(event, "sender_id", "") or getattr(event, "user_id", "") or "")
    if not sid and hasattr(event, "get_sender_id"):
        try:
            sid = str(event.get_sender_id() or "")
        except Exception:
            sid = ""
    return sid


def is_romantic(plugin: Any, session_key: str) -> bool:
    """该会话是否亲密（供 life-sim 路由等消费方调用）。fail-closed。"""
    try:
        store = getattr(plugin, "_store", None)
        if store is None:
            return False
        # ① 手动覆盖优先（owner-gated /bond 写入，写时已带身份）
        ov = store.intimacy_override.get(session_key)
        if ov is not None:
            return bool(ov)
        # ② 自动晋升：身份门控（仅 owner 会话）
        owner = _owner_id(plugin)
        if not owner:
            return False  # 未配 owner → 全禁自动晋升（fail-closed）
        st = store.relationship_register_state.get(session_key)
        if not st:
            return False
        if str(st.get("sender_id", "")) != owner:
            return False  # 身份门控：非 owner 会话恒非亲密（防注入）
        if int(st.get("sample_count", 0)) < _MIN_SAMPLE:
            return False
        return float(st.get("romantic_conf", 0.0)) >= _ROMANTIC_THRESHOLD
    except Exception as exc:  # noqa: BLE001
        logger.debug("Sylanne is_romantic failed (fail-closed): %s", exc)
        return False


# ---- 持久化（独立 KV key，仿 sylanne_life_sim_state，不折进 life_sim）----

def request_persist(plugin: Any) -> None:
    """关系层状态写入后的单一落盘派发入口（off-path，绝不阻塞调用方）。

    rel_register 累积 / /bond / /unbond 三个写入点统一调它。经 safe_ensure_future
    把 plugin._rel_state_throttled_save 丢后台跑（独立节流，与 life_sim 解耦）。
    无该方法（老宿主/测试桩）或派发失败都静默——落盘有 terminate 兜底，不能因它崩主流程。
    """
    try:
        saver = getattr(plugin, "_rel_state_throttled_save", None)
        if saver is None:
            return
        from sylanne_alpha.infra import safe_ensure_future
        safe_ensure_future(saver(), name="rel_state_save")
    except Exception as exc:  # noqa: BLE001 - 落盘派发绝不影响主流程
        logger.debug("Sylanne relationship persist dispatch skipped: %s", exc)


def snapshot(plugin: Any) -> dict:
    """序列化关系层状态（register_state + override）供 KV 落盘。"""
    store = getattr(plugin, "_store", None)
    if store is None:
        return {}
    reg = {}
    ovr = {}
    try:
        reg = {k: v for k, v in store.relationship_register_state.snapshot_items()}
    except Exception:
        pass
    try:
        ovr = {k: bool(v) for k, v in store.intimacy_override.snapshot_items()}
    except Exception:
        pass
    return {"register_state": reg, "override": ovr}


def restore(plugin: Any, data: dict) -> None:
    """从 KV blob 恢复关系层状态（initialize 时调）。"""
    if not isinstance(data, dict):
        return
    store = getattr(plugin, "_store", None)
    if store is None:
        return
    # 中间层也做 isinstance：旧档迁移/损坏时 register_state/override 可能非 dict，
    # 直接 .items() 会抛 AttributeError 中断整个恢复流程。
    reg_state = data.get("register_state")
    if isinstance(reg_state, dict):
        for sk, st in reg_state.items():
            if isinstance(st, dict):
                store.relationship_register_state.set(sk, st)
    override_state = data.get("override")
    if isinstance(override_state, dict):
        for sk, ov in override_state.items():
            store.intimacy_override.set(sk, bool(ov))


# ---- /bond·/unbond（owner-gated，无 TOFU）----

async def bond_command(plugin: Any, event: Any):
    """标当前会话为亲密。仅 owner 可用；owner_id 空则拒（不自动确权）。"""
    owner = _owner_id(plugin)
    if not owner:
        yield "还没设置主人身份呢（配置里填 sylanne_alpha_owner_id），不然谁来都说自己是我对象，哼。"
        return
    sid = _event_sender_id(event)
    if sid != owner:
        yield "你又不是我对象，凑什么热闹。"
        return
    sk = plugin._session_key(event) if hasattr(plugin, "_session_key") else ""
    if not sk:
        yield "唔…这会儿没认出是哪个窗口，等下再跟我说嘛。"
        return
    plugin._store.intimacy_override.set(sk, True)
    request_persist(plugin)
    yield "嗯…那这边算我们自己人了，别到处说。"


async def unbond_command(plugin: Any, event: Any):
    """取消当前会话的亲密标记，恢复自动判定。仅 owner 可用。"""
    owner = _owner_id(plugin)
    if not owner:
        yield "都没设主人，解除个什么。"
        return
    sid = _event_sender_id(event)
    if sid != owner:
        yield "这跟你没关系吧。"
        return
    sk = plugin._session_key(event) if hasattr(plugin, "_session_key") else ""
    if not sk:
        yield "唔…这会儿没认出是哪个窗口，等下再跟我说嘛。"
        return
    # 删 override（而非置 False）：handoff §2.3 要求 /unbond = 恢复自动判定。
    # 置 False 会让 override 永久压住自动信号（override 优先），自动累积再也翻不回来，
    # 与"恢复自动"语义相悖。删 key → is_romantic 回落到身份门控的自动晋升路径。
    plugin._store.intimacy_override.pop(sk, None)
    request_persist(plugin)
    yield "哦…那就当我没说过，以后还是看你怎么待我吧，笨蛋。"
