"""梦境巩固（2.2.0-a，REM 的诚实对应物·零 LLM 段）—— 深睡时把白天收进自传。

理论根基与诚实边界（设计文档 §一）：
- Stickgold (2005)：睡眠依赖巩固——白天编码的情节在睡眠中被选择性重放、整合。
- Walker & van der Helm (2009)：REM 优先巩固高情绪记忆。
- 我们不模拟神经重放。本模块的对应物是：深睡拍（AutonomyScheduler RETIRED，
  零 LLM 红线，consolidation.py 模块 docstring 钉死）把当日 v2core 长出的东西
  ——高失配锚点的厚度、最热的"我们的说法"、与Ta的合拍程度、情绪基线——压成
  一枚"梦:"锚点写进叙事自我。她睡一觉，白天就长进了自传。
- LLM 版梦境纪要（更丰富的反思整合）属于 DROWSY 反思拍（那里有既有 token 三道闸），
  列为 2.2.0-a2，本模块不调 LLM、不碰网络、不阻塞。

接线（全部既有器官）：
- 入口：ConsolidationEngine.consolidate_sync（会话锁内、同步、零 IO）
- 写：NarrativeSelfDomain.register_dream（域自己的写接口，单一写者不破）
- 守卫：自上次梦以来没有新经历（anchor_total 无增量）→ 无梦（没有素材的夜晚
  不值得伪造一个梦）；ConsolidationEngine 自带 1800s 间隔闸防 RETIRED 期重复。
- 落盘：调用方（consolidation）经 integration._schedule_domain_save 既有通道。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("astrbot_plugin_sylanne")


def weave_dream_note(domains: dict[str, Any]) -> str:
    """把四域的"今天"编成一句梦记（零 LLM 纯模板；与 verbal.py 同哲学：零数字）。

    取材全走域公开只读接口；任何一块缺失只丢那一片素材。返回不含"梦:"前缀
    （register_dream 统一加），可为空串（调用方据守卫决定是否成梦）。
    """
    bits: list[str] = []

    um = domains.get("usermodel")
    if um is not None:
        try:
            memes = um.memes(1) if hasattr(um, "memes") else []
            if memes:
                bits.append(f"心里常念「{memes[0]}」")
        except Exception:
            pass
        try:
            sync = float(um.synchrony()) if hasattr(um, "synchrony") else 0.5
            if sync >= 0.65:
                bits.append("和Ta越来越合拍")
            elif sync <= 0.35:
                bits.append("总觉得和Ta错频")
        except Exception:
            pass

    emo = domains.get("emotion")
    if emo is not None:
        try:
            slow = (emo.to_dict() or {}).get("slow_ema")
            if slow is not None:
                slow = float(slow)
                if slow >= 0.15:
                    bits.append("心底是暖的")
                elif slow <= -0.15:
                    bits.append("心底发着凉")
        except Exception:
            pass

    return "·".join(bits[:2])


def weave_and_register_dream(plugin: Any, session_key: str) -> bool:
    """深睡织梦总入口（同步、零 LLM、零 IO；落盘由调用方走既有通道）。

    v2core 未启用 / 会话没跑过 / 无 narrative 域 / 无新经历 → False（无梦，静默）。
    成梦 → True，调用方负责 fire-and-forget 落盘。
    """
    runtimes = getattr(plugin, "_v2core_runtimes", None)
    rt = runtimes.get(session_key) if isinstance(runtimes, dict) else None
    domains = rt.get("domains") if isinstance(rt, dict) else None
    if not isinstance(domains, dict):
        return False
    nar = domains.get("narrative")
    if nar is None or not hasattr(nar, "register_dream"):
        return False
    note = weave_dream_note(domains)
    try:
        made = bool(nar.register_dream(note))
    except Exception as exc:  # noqa: BLE001
        logger.debug("Sylanne dream weave [%s]: %s", session_key, exc)
        return False
    if made:
        logger.info("Sylanne 梦境巩固 [%s]: 梦:%s", session_key, note or "（无言的一夜）")
    return made


__all__ = ["weave_dream_note", "weave_and_register_dream"]
