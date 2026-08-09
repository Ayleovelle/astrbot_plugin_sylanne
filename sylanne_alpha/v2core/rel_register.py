"""Phase 2B / PR-G：关系类型分类（rel_register）。

壳层模块（非 SDK 内部）。在 v2core percept 钩子里 off-path 后台跑一个低频 gated LLM
分类，判用户对 Sylanne 的关系语域（romantic/friendly/formal），多轮累积进
plugin._store.relationship_register_state。PR-H 的 is_romantic 据此 + 身份门控判亲密。

关键纪律：
- 只读认知阶段产出，**不进 SDK kernel/tick/assessment**——只写壳层 store。
- off-path：经 safe_ensure_future 后台跑，绝不 inline await、不阻塞请求路径。
- 分类按用户语域判类型（称呼/排他性/关系性指涉），非情绪强度。
"""

from __future__ import annotations

import re
import time
from typing import Any

from sylanne_alpha.provider_routing import (
    ProviderFeature,
    call_text_provider_once,
    resolve_text_provider,
)

try:
    from astrbot.api import logger  # type: ignore
except Exception:  # pragma: no cover - 测试环境无 astrbot
    import logging

    logger = logging.getLogger("astrbot_plugin_sylanne")

_REL_TYPES = ("romantic", "friendly", "formal")
# 累积平滑：置信 = 某类占比 × min(1, sample_count / _REL_CONFIDENCE_SAMPLES)。
# 样本不足时折扣，单轮分类不足以判定（多轮稳定才算数）。
#
# 标定依据（解析推导，handoff §7 待 review 的占位由此收敛为有据值）：
#   设某友好用户被系统性误判 romantic 的占比为 p（相关误差，累积不抵消、会被固化）。
#   n 大时 conf → (romantic_count/n) × 1 → p。故"友好不误升"要求阈值 > p。
#   纯浪漫用户 ratio=1，conf = min(1, n/_REL_CONFIDENCE_SAMPLES)；N=8 时 n=5 → 0.625。
#   配 _ROMANTIC_THRESHOLD=0.6 + _MIN_SAMPLE=5：浪漫用户第 5 个有效样本即晋升，
#   而友好用户需 p>0.6（>60% 轮次被误判）才误升。文献"高频爱称友好语料"误判率
#   约 20-35%，0.6 保守压在其上。N=8 给出"5 样本即可达阈、8 样本满折扣"的平滑窗。
#   ⚠ 真机标定（实测 p 后微调阈值）仍 deferred —— 协议见 phase-2c handoff 草案。
_REL_CONFIDENCE_SAMPLES = 8
# 低频 gating：每 N 轮分类一次（省 token；消费方 is_romantic 多轮滞后，稀疏够用）。
# N=6 配 _MIN_SAMPLE=5 → 约 30 轮对话才够样本自动晋升，符合"多轮滞后可接受"契约。
_REL_GATING_EVERY = 6

_PROMPT = (
    "判断下面这段用户消息，反映用户对“苏思澜”的关系类型，只看关系语域，不看情绪强度。\n"
    "判据：称呼（如老公/宝贝）、排他性宣称（如在一起/我们）、关系性指涉。\n"
    "仅用爱称（亲爱的/亲）不足以判 romantic——需与排他性或关系性指涉共现。\n"
    "只输出一个词：romantic / friendly / formal。\n\n"
    "消息：{text}"
)


def _parse_rel(raw: Any) -> str:
    """把模型输出规范化为 _REL_TYPES 之一，非法/缺→unknown。

    按词边界匹配（非子串）：避免 "informal" 含 "formal"、"unromantic" 含
    "romantic" 的子串误判。提取字母词成 set，精确判类型。
    """
    if not raw:
        return "unknown"
    words = set(re.findall(r"[a-z]+", str(raw).strip().lower()))
    for t in _REL_TYPES:
        if t in words:
            return t
    return "unknown"


def should_classify(rt: dict, now: float) -> bool:
    """低频 gating：每 _REL_GATING_EVERY 轮触发一次（首轮即触发）。

    rt 是 per-session 运行态字典；用其中的轮计数器判定（无则从 0 起）。
    """
    n = int(rt.get("rel_turn", 0))
    rt["rel_turn"] = n + 1
    return n % _REL_GATING_EVERY == 0


def _accumulate(st: dict, label: str, sender_id: str, now: float) -> None:
    """把一次分类结果累积进 register_state 的单会话条目（就地修改 st）。

    unknown 不计入样本。conf = 该类计数/样本数 × min(1, 样本数/N)。
    """
    if label not in _REL_TYPES:
        return  # unknown 不更新累积
    # 总是更新为最新认证 sender_id（非"保留首个"）：session_key 是平台会话标识，
    # 若同一会话换人登录，身份门控必须跟到新身份——保留旧 sender_id 反而会把前任
    # owner 的亲密门控错套在新登录者上（安全洞）。认证 sender_id 不可伪造，更新安全。
    if sender_id:
        st["sender_id"] = sender_id
    st["sample_count"] = int(st.get("sample_count", 0)) + 1
    key = f"{label}_count"
    st[key] = int(st.get(key, 0)) + 1
    n = st["sample_count"]
    factor = min(1.0, n / float(_REL_CONFIDENCE_SAMPLES))
    for t in _REL_TYPES:
        cnt = int(st.get(f"{t}_count", 0))
        st[f"{t}_conf"] = round((cnt / n) * factor, 6) if n else 0.0
    st["updated_at"] = now
    st["last_active"] = now


async def classify_and_store(
    plugin: Any, session_key: str, event: Any, text: str
) -> None:
    """off-path 后台任务：调 LLM 分类关系语域，结果累积写壳层 store。

    任何异常吞掉（后台任务，绝不影响主流程）。不碰 SDK 内部。
    """
    try:
        store = getattr(plugin, "_store", None)
        reg = getattr(store, "relationship_register_state", None)
        context = getattr(plugin, "context", None) or getattr(plugin, "_context", None)
        config = getattr(plugin, "config", None) or getattr(plugin, "_config", None) or {}
        if reg is None or context is None or not text.strip():
            return
        resolved = await resolve_text_provider(
            feature=ProviderFeature.RELATIONSHIP,
            config=config,
            context=context,
            umo=str(getattr(event, "unified_msg_origin", "") or "") or None,
        )
        if resolved.provider is None:
            return
        prompt = _PROMPT.format(text=text[:300])
        response = await call_text_provider_once(
            resolved.provider,
            prompt=prompt,
            max_tokens=8,
            temperature=0.0,
        )
        raw = getattr(response, "completion_text", response)
        label = _parse_rel(raw)
        if label == "unknown":
            return
        # 认证 sender_id：复用 relationship_layer 的唯一解析器（含 user_id 回落），
        # 不在此另起重复逻辑——否则两处会随平台事件形态变化而漂移。
        from sylanne_alpha.relationship_layer import _event_sender_id
        sender_id = _event_sender_id(event)
        st = reg.get(session_key) or {}
        _accumulate(st, label, sender_id, time.time())
        reg.set(session_key, st)
        # PR-H 解耦：累积写入后派发独立节流落盘（off-path，节流压成稀疏写）。
        try:
            from sylanne_alpha import relationship_layer as _rl
            _rl.request_persist(plugin)
        except Exception:
            pass  # cleanup: persist dispatch failure acceptable (terminate 兜底)
    except Exception as exc:  # noqa: BLE001 - 后台任务不外抛
        logger.debug("Sylanne rel_register classify failed (ignored): %s", exc)
