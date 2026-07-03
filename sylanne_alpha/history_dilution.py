"""对话历史密度稀释 —— 墓碑：本模块已停用，永久不得再对 contexts 做原地变形。

历史背景（Wave 3 / 2026-06-14）：当用户发低信息延续（表情/短应答）时，完整
conversation.history 里旧长文（告白、长篇倾诉）会在注意力竞争中压过当前 turn。
本模块曾在 contexts 层对【较早】高密度 assistant/user 消息做软截断——把消息
在 200 字处硬切、拼接"…（较早对话已压缩，接着最近话题聊）"，意图仅降低当次
请求里的语义密度。

为什么必须废止（fix/context-integrity，2026-07）：AstrBot 的
run_context.messages 是直接从 req.contexts 构建的，_save_to_history 会把这份
被截断的 contexts 原样写回会话 DB（见
astrbot/core/agent/runner/tool_loop_agent_runner.py 与
astrbot/core/agent/run_context 的落库逻辑）。也就是说 req.contexts /
req.prompt 是「写穿透」到持久化历史的层，不是一次性、请求级的草稿。
dilute_dense_contexts 对 contexts 的原地截断因此不是「这一轮临时降噪」，
而是**永久、不可逆地腰斩数据库里保存的旧对话**，且每次低信息消息触发一次、
逐日复利——用户的告白/长文字面上被吃掉，无法恢复。

原始意图（低信息延续时别被旧浓文本带跑话题）已经由 FocusDomain 满足，且是
更安全的实现：FocusDomain（sylanne_alpha/v2core/domains/focus.py）在低信息
消息时把「话头」钉入心象片段，经 build_mind_fragment 并入 system_prompt
（sylanne_alpha/v2core/fragment.py），只影响本次请求的提示词组装，从不写回
request.contexts，因此不会被持久化层写穿透——降低了旧文本的注意力竞争，
却不删用户/助手说过的任何一个字。

本函数保留为**永久 no-op**：原样返回 contexts（同一对象，不拷贝、不改写），
仅用于兼容旧调用点/旧测试的导入路径。任何人想「恢复」截断行为前，请先重读
上面这段——写穿透持久化是这里唯一且致命的理由，不是性能或格式问题。
"""

from __future__ import annotations

from typing import Any

# 以下常量仅为向后兼容旧签名保留，不再参与任何截断逻辑。
_DEFAULT_MAX_OLD_CHARS = 200
_DEFAULT_KEEP_TAIL_MSGS = 4


def dilute_dense_contexts(
    contexts: list[Any] | None,
    current_text: str,
    *,
    max_old_chars: int = _DEFAULT_MAX_OLD_CHARS,
    keep_tail_turns: int = _DEFAULT_KEEP_TAIL_MSGS,
) -> list[Any] | None:
    """永久 no-op：原样返回 contexts，绝不截断/改写任何条目。

    见模块顶部墓碑说明——req.contexts 会被 AstrBot 写穿透持久化到会话 DB，
    原地截断等于永久腰斩用户历史，因此本函数不再做任何变形。
    参数（max_old_chars/keep_tail_turns）仅为兼容旧调用签名保留，不生效。
    """
    return contexts


__all__ = ["dilute_dense_contexts"]
