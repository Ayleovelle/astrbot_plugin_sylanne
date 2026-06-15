"""交付/纠正任务的【结构化】识别 + 工具门控（2026-06-15 文案改写事故 P0-3）。

事故根因 L1+L2：用户让"同义改写一句话"（交付型、无需工具），模型却把它当成
"去调查用户到底要啥"，钻进 execute_python 连调 6 次翻历史/SQLite，一次出错后把
整段英文推理草稿当正文吐出，86 段群发。

这里【不靠关键词表】（"改写/换掉"那种一换措辞/语种就失效、还跟 v2core「不产 intent
标签」的设计相悖），而是用对话的【结构信号】判定"用户正在反复纠正同一份产出"这个
高置信场景，命中时：
  ① 摘掉代码执行逃生舱工具（execute_python/ipython/shell），让它进不了 thrash 循环
     —— 保留 TTS/搜索/发消息等正常工具（选择性，非一刀切 func_tool=None）；
  ② 注入交付契约，覆盖底层人设的"不是接活办任务"取向，让她直接给可粘贴的成品。

保守默认：拿不准一律不动（保留全部工具 + 不注契约）。只在高置信时硬闸。
"""

from __future__ import annotations

import time
from typing import Any

# 代码执行逃生舱：Sylanne 是对话人格不是编码 agent，这几个工具是 thrash 温床。
# 仅在【高置信纠正链】时摘除本轮，不影响别的轮次/别的会话（func_tool 每请求新建）。
_ESCAPE_HATCH_TOOLS = (
    "astrbot_execute_python",
    "astrbot_execute_ipython",
    "astrbot_execute_shell",
)

# 交付契约：命中纠正链时追加到 system_prompt 末尾（最后说的最重，压住人设的反任务取向）。
_DELIVERABLE_CONTRACT = (
    "[本轮任务模式]你已经为同一件事改了好几版、对方在反复纠正——这说明他要的是一份"
    "能直接用的成品，不是陪聊。这一轮请：直接给出修改后的成品本身，一次给全；不要再去"
    "翻历史/查工具/调查他到底想要啥（要什么他已经说清了）；不要加人设包装、寒暄、"
    "解释你怎么想的；做不到或不确定就直接说，别硬猜。成品该是什么样就什么样。"
)


def has_attachment(event: Any) -> bool:
    """结构判定：本轮消息是否带图片/文件等非文本附件。"""
    msg_obj = getattr(event, "message_obj", None)
    chain = getattr(msg_obj, "message", None) or [] if msg_obj else []
    for seg in chain:
        t = getattr(seg, "type", None)
        if t is None and isinstance(seg, dict):
            t = seg.get("type")
        if t in ("image", "file", "video", "record"):
            return True
    return False
# __APPEND__


def in_correction_loop(buffer: Any) -> bool:
    """结构判定：是否处于"反复纠正同一产出"的高置信场景（不看内容）。

    调用时机：on_llm_request（当前这一轮【就是】用户的新消息，但它此刻【还没】写进
    buffer——buf.append("user") 在后台任务里、晚于本钩子执行）。所以不能要求"buffer
    末条是 user"（那只会看到上一版 bot 回复）。当前是用户轮是【隐含前提】，无需再判。

    信号组合（全要满足）：
      ① 最近窗口里 bot 至少出过 2 版产出（用户在迭代纠正，不是一次性闲聊）；
      ② 近端轮次密集（相邻间隔中位数 < 150s，是活着的来回，不是隔天翻旧账）。
    任一不满足 → False（保守：当普通对话）。
    """
    msgs = getattr(buffer, "messages", None) or []
    if len(msgs) < 3:
        return False
    recent = msgs[-6:]
    bot_versions = sum(1 for m in recent if m.get("role") == "bot")
    if bot_versions < 2:
        return False
    gaps = [
        float(recent[i]["ts"]) - float(recent[i - 1]["ts"])
        for i in range(1, len(recent))
        if recent[i].get("ts") and recent[i - 1].get("ts")
    ]
    if not gaps:
        return False
    gaps.sort()
    median_gap = gaps[len(gaps) // 2]
    return median_gap < 150.0


def detect(event: Any, buffer: Any) -> dict[str, Any]:
    """汇总结构信号，给出是否进入交付模式 + 是否摘逃生舱工具。

    高置信 = 纠正链 且 本轮无附件（带图通常是新任务/要 vision，别误闸）。
    """
    attach = has_attachment(event)
    loop = in_correction_loop(buffer)
    deliverable = loop and not attach
    return {
        "deliverable": deliverable,
        "in_correction_loop": loop,
        "has_attachment": attach,
    }


def gate_tools(request: Any) -> list[str]:
    """从本请求的 func_tool 里选择性摘除代码执行逃生舱工具。返回被摘掉的名字。

    func_tool 每请求新建（get_full_tool_set/_plugin_tool_fix），remove_tool 只改本
    请求副本，不污染全局 registry、不影响别的会话。保留 TTS/搜索/发消息等。
    """
    removed: list[str] = []
    func_tool = getattr(request, "func_tool", None)
    if func_tool is None:
        return removed
    names = getattr(func_tool, "names", None)
    have = set(names()) if callable(names) else set()
    for name in _ESCAPE_HATCH_TOOLS:
        if name in have and hasattr(func_tool, "remove_tool"):
            func_tool.remove_tool(name)
            removed.append(name)
    return removed


def inject_contract(request: Any) -> bool:
    """把交付契约追加到 system_prompt 末尾（最后说的最重）。已含则跳过。返回是否注入。"""
    current = str(getattr(request, "system_prompt", "") or "")
    if "[本轮任务模式]" in current:
        return False
    request.system_prompt = (current + "\n" + _DELIVERABLE_CONTRACT).strip()
    return True


def apply(event: Any, request: Any, buffer: Any) -> dict[str, Any]:
    """事故 P0-3 总入口：检测→命中则摘逃生舱工具+注交付契约。返回处置摘要（可观测/测试）。"""
    sig = detect(event, buffer)
    if not sig["deliverable"]:
        return {**sig, "gated_tools": [], "contract_injected": False}
    removed = gate_tools(request)
    injected = inject_contract(request)
    return {**sig, "gated_tools": removed, "contract_injected": injected}


__all__ = [
    "apply", "detect", "gate_tools", "inject_contract",
    "in_correction_loop", "has_attachment",
]
