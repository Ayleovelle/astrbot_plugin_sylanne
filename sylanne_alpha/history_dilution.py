"""对话历史密度稀释 —— 路径 B 的 contexts 侧防御（Wave 3）。

当用户发低信息延续（表情/短应答）时，完整 conversation.history 里旧长文
（告白、长篇倾诉）会在注意力竞争中压过当前 turn。FocusDomain 在心象层钉锚；
本模块在 contexts 层对【较早】高密度 assistant/user 消息做软截断，降低语义密度，
不删最近几轮（保留即时语境）。

纪律：纯字符串裁剪，零 LLM；仅在低信息当前消息时出手（与 FocusDomain 同判据）。
"""

from __future__ import annotations

from typing import Any

# 单条旧消息软上限（字符）；最近 tail 轮保持原样
_DEFAULT_MAX_OLD_CHARS = 200
_DEFAULT_KEEP_TAIL_MSGS = 4


def _msg_text(msg: Any) -> str:
    if isinstance(msg, dict):
        return str(msg.get("content") or msg.get("text") or "")
    return str(getattr(msg, "content", None) or getattr(msg, "text", "") or "")


def _msg_role(msg: Any) -> str:
    if isinstance(msg, dict):
        return str(msg.get("role") or "")
    return str(getattr(msg, "role", "") or "")


def dilute_dense_contexts(
    contexts: list[Any] | None,
    current_text: str,
    *,
    max_old_chars: int = _DEFAULT_MAX_OLD_CHARS,
    keep_tail_turns: int = _DEFAULT_KEEP_TAIL_MSGS,
) -> list[Any] | None:
    """低信息当前消息时，截断较早 contexts 中的过长条目。"""
    if not isinstance(contexts, list) or not contexts:
        return contexts
    try:
        from sylanne_alpha.v2core.domains.focus import is_substantive
    except Exception:
        return contexts
    if is_substantive(current_text):
        return contexts

    keep_tail_msgs = max(2, min(len(contexts), int(keep_tail_turns)))
    split_at = max(0, len(contexts) - keep_tail_msgs)
    out: list[Any] = []
    changed = False
    for i, msg in enumerate(contexts):
        text = _msg_text(msg)
        role = _msg_role(msg)
        if i < split_at and role in ("user", "assistant") and len(text) >= max_old_chars:
            clipped = text[:max_old_chars].rstrip() + "…（较早对话已压缩，接着最近话题聊）"
            if isinstance(msg, dict):
                new_msg = dict(msg)
                if "content" in new_msg:
                    new_msg["content"] = clipped
                else:
                    new_msg["text"] = clipped
                out.append(new_msg)
            else:
                try:
                    setattr(msg, "content", clipped)
                except Exception:
                    pass
                out.append(msg)
            changed = True
        else:
            out.append(msg)
    if changed:
        return out
    return contexts


__all__ = ["dilute_dense_contexts"]
