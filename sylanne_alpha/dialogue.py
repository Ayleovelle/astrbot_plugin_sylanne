"""Sylanne-Embodiment: 对话分段与中断检测模块。

负责将连续的用户消息流切分为语义段落（segment），
并检测话题转换、消息续接、撤回等对话动力学信号。

核心功能：
- 对话分段：判断新消息是"续接上文"还是"开启新话题"
- 中断检测：识别用户在机器人回复过程中的打断行为
- 动作建议：如检测到打断，建议取消正在进行的实时派发

与其他组件的关系：
- 被 body.py 在每条用户消息到达时调用
- 输出的 segment_id 用于关联同一话题的多条消息
- interruption 信息供实时派发系统决定是否取消当前回复
"""

from __future__ import annotations

import hashlib
from typing import Any

DIALOGUE_SCHEMA_VERSION = "sylanne.alpha.dialogue.v1"

# 话题转换标记词：出现这些词时判定为新话题
_TOPIC_SHIFT_MARKERS = ("换个话题", "另外", "对了", "服务器", "卡死", "报错", "bug")
# 续接标记词：出现这些词时判定为延续上一段
_CONTINUATION_MARKERS = ("还有", "而且", "然后", "就是", "也", "继续")


def segment_dialogue(
    *,
    session_key: str,
    text: str = "",
    now: float = 0.0,
    previous: dict[str, Any] | None = None,
    flags: list[str] | None = None,
    reply_in_progress: bool = False,
) -> dict[str, Any]:
    """对一条用户消息进行对话分段分析。

    参数:
        session_key: 会话标识
        text: 用户消息文本
        now: 消息时间戳
        previous: 上一条分段结果（用于判断续接）
        flags: 外部标记（如 "withdrawal" 表示撤回）
        reply_in_progress: 机器人是否正在回复中

    返回:
        包含 segment_id、relation、interruption、actions 等的分析结果
    """
    flags = list(flags or [])
    normalized = " ".join(str(text or "").split())
    previous_id = str((previous or {}).get("segment_id") or "")
    relation = _relation(normalized, previous=previous, flags=flags)
    # 续接时复用上一段的 segment_id，否则生成新 id
    segment_id = (
        previous_id
        if previous_id and relation == "continuation"
        else _segment_id(session_key, normalized, now)
    )
    interruption = _interruption(relation, reply_in_progress=reply_in_progress)
    # 如果检测到打断且机器人正在回复，建议取消实时派发
    actions = (
        ["cancel_realtime_dispatch"]
        if interruption["detected"] and reply_in_progress
        else []
    )
    return {
        "schema_version": DIALOGUE_SCHEMA_VERSION,
        "session_key": session_key,
        "segment_id": segment_id,
        "relation": relation,
        "message_time": now,
        "features": {
            "chars": len(normalized),
            "short_fragment": len(normalized) <= 24,
            "topic_shift": relation == "topic_shift",
            "withdrawal": relation == "withdrawal",
        },
        "interruption": interruption,
        "actions": actions,
        "text_preview": normalized[:80],
    }


def _relation(text: str, *, previous: dict[str, Any] | None, flags: list[str]) -> str:
    """判断当前消息与上文的关系类型。

    返回值：
    - "withdrawal": 消息撤回
    - "topic_shift": 话题转换
    - "continuation": 续接上文（短消息或含续接标记词）
    - "new_segment": 新的独立段落
    """
    if "withdrawal" in flags:
        return "withdrawal"
    if any(marker in text for marker in _TOPIC_SHIFT_MARKERS):
        return "topic_shift"
    if previous and (
        len(text) <= 24 or any(marker in text for marker in _CONTINUATION_MARKERS)
    ):
        return "continuation"
    return "new_segment"


def _interruption(relation: str, *, reply_in_progress: bool) -> dict[str, Any]:
    """判断是否构成中断事件。"""
    if relation == "withdrawal":
        return {"detected": True, "reason": "message_withdrawal"}
    if reply_in_progress and relation == "topic_shift":
        return {"detected": True, "reason": "user_topic_shift_during_reply"}
    return {"detected": False, "reason": "none"}


def _segment_id(session_key: str, text: str, now: float) -> str:
    """生成确定性的段落 ID（blake2s 哈希）。"""
    seed = f"{session_key}\0{text}\0{now:.3f}".encode("utf-8")
    return "seg-" + hashlib.blake2s(seed, digest_size=6).hexdigest()


__all__ = ["DIALOGUE_SCHEMA_VERSION", "segment_dialogue"]
