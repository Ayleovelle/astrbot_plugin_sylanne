"""交付/纠正任务的【结构化】识别 + 工具门控（2026-06-15 文案改写事故 P0-3）。

事故根因 L1+L2：用户让"同义改写一句话"（交付型、无需工具），模型却把它当成
"去调查用户到底要啥"，钻进 execute_python 连调 6 次翻历史/SQLite，一次出错后把
整段英文推理草稿当正文吐出，86 段群发。

这里分两层结构信号，不靠易碎关键词表：
  ① 纯文本轮摘掉代码执行逃生舱工具（execute_python/ipython/shell），让它进不了
     thrash 循环；同时摘掉会绕过统一投递链、自己直发且无返回值的批量搜索工具。
     保留 TTS、返回结果给模型的搜索和发消息等正常工具，附件轮全部放行。
  ② 只有结构上确认"用户正在反复纠正同一份产出"时才注入交付契约，覆盖底层人设的
     "不是接活办任务"取向，让她直接给可粘贴的成品。

保守默认：宽门控只减少高风险工具；拿不准是否为纠正链时绝不注入契约。
"""

from __future__ import annotations

import time
from typing import Any

# 逃生舱/调查类工具：Sylanne 是对话人格不是编码 agent，这些是 thrash 温床。
# 代码执行三件套 + query_agent_state（她自己的内省工具，正是"跑去调查用户想要啥"
# 的对口入口，M4 审查补入）。仅本请求摘除，不影响别会话（func_tool 每请求新建）。
_ESCAPE_HATCH_TOOLS = (
    "astrbot_execute_python",
    "astrbot_execute_ipython",
    "astrbot_execute_shell",
    "query_agent_state",
)

# 工具自己 event.send、成功时无返回值；平台 timeout 后无法判断是否实际送达，既不能
# 安全重试，也不能让 LLM 获得检索结果。纯文本轮在请求前摘除，附件轮沿用既有放行规则。
_DIRECT_SEND_TOOLS = (
    "anysearch_batch_search",
)

# 交付契约：命中"反复纠正成品"时追加到 system_prompt 末尾。
# 关键（B1 审查）：绝不要求"去人设/别寒暄"——那会压平苏思澜（用户全局红线）。契约只管
# "确保把成品交全、别再跑去调查"，语气仍是她自己的。是"用你的语气把活干完"，不是"别做你"。
_DELIVERABLE_CONTRACT = (
    "[本轮提示]你已经为同一件事改了好几版、对方还在纠正——他要的是一份能直接拿去用的"
    "成品。这一轮：把改好的成品本身一次给全（别只给半截或只解释思路）；要什么他已经说清了，"
    "别再翻历史/查工具/反复猜他想要啥。语气还是你平时的样子，该傲娇该吐槽随你——只是别忘了"
    "把东西给齐。真做不到或拿不准就直说，别硬凑。"
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


def _avg_len_by_role(recent: list, role: str) -> float:
    vals = [len(str(m.get("text", ""))) for m in recent if m.get("role") == role]
    return sum(vals) / len(vals) if vals else 0.0


def in_correction_loop(buffer: Any) -> bool:
    """结构判定：是否在"反复纠正同一份成品"（高置信，内容无关，刻意保守）。

    调用时机：on_llm_request（当前用户消息此刻【还没】写进 buffer——append 在后台任务里
    晚于本钩子；当前是用户轮为隐含前提，不判 buffer 末条角色）。

    关键教训（B1 审查）：不能用"对话节奏"当信号——快节奏短句来回是亲密闲聊的【常态】，
    不是纠正特征。拿节奏当信号会在日常快聊里误命中、把契约糊上去压平人格（用户全局红线）；
    反过来用户慢慢看完每版再回复又会漏命中。两头都错。

    改用【交付形态的非对称信号】（内容无关，跨语种稳）：
      ① 近端窗口里 bot 出过 ≥2 版产出（在迭代，不是一次性闲聊）；
      ② bot 近端回复明显【长于】user 近端消息（avg_bot ≥ 2×avg_user 且 avg_bot ≥ 60 字）
         —— "用户短句纠正、bot 反复掏长成品"正是交付返工的形状；闲聊两边都短，不触发。
    不再看相邻间隔（去掉 150s 上限，修慢节奏漏命中）。任一不满足 → False。
    """
    msgs = getattr(buffer, "messages", None) or []
    if len(msgs) < 3:
        return False
    recent = msgs[-6:]
    bot_versions = sum(1 for m in recent if m.get("role") == "bot")
    if bot_versions < 2:
        return False
    avg_bot = _avg_len_by_role(recent, "bot")
    avg_user = _avg_len_by_role(recent, "user")
    # bot 反复产出长内容、user 在用短句纠正 → 交付返工形态。闲聊两边都短 → avg_bot 不够长。
    return avg_bot >= 60.0 and avg_bot >= 2.0 * max(avg_user, 1.0)


def detect(event: Any, buffer: Any) -> dict[str, Any]:
    """汇总结构信号，分别给出两个独立判定（粒度不同，刻意分开）：

    - should_gate（摘逃生舱工具，【宽】）：本轮无图片/文件附件即摘。Sylanne 是对话
      人格、正常聊天几乎用不到 execute_python/shell；带附件才可能要处理工具，故只放过
      带附件的轮。这是结构兜底，把 thrash 温床从绝大多数纯聊天轮直接移除。
    - should_contract（注交付契约，【窄】）：仅纠正链（反复纠正同一产出）且无附件。
      契约会压人设取向、改变她说话方式，只在高置信交付场景才动，避免日常闲聊也被框住。
    """
    attach = has_attachment(event)
    loop = in_correction_loop(buffer)
    return {
        "should_gate": not attach,
        "should_contract": loop and not attach,
        "in_correction_loop": loop,
        "has_attachment": attach,
        # 兼容旧字段名（测试/可观测）：deliverable == 进入交付契约模式
        "deliverable": loop and not attach,
    }


def gate_tools(request: Any) -> list[str]:
    """从本请求的 func_tool 摘除逃生舱与 direct-send 工具。返回被摘掉的名字。

    func_tool 每请求新建（get_full_tool_set/_plugin_tool_fix），remove_tool 只改本
    请求副本，不污染全局 registry、不影响别的会话。保留 TTS、返回值搜索和发消息等。
    """
    removed: list[str] = []
    func_tool = getattr(request, "func_tool", None)
    if func_tool is None:
        return removed
    names = getattr(func_tool, "names", None)
    have = set(names()) if callable(names) else set()
    for name in (*_ESCAPE_HATCH_TOOLS, *_DIRECT_SEND_TOOLS):
        if name in have and hasattr(func_tool, "remove_tool"):
            func_tool.remove_tool(name)
            removed.append(name)
    return removed


def inject_contract(request: Any) -> bool:
    """把交付契约追加到 system_prompt 末尾（最后说的最重）。已含则跳过。返回是否注入。"""
    current = str(getattr(request, "system_prompt", "") or "")
    if "[本轮提示]" in current:
        return False
    request.system_prompt = (current + "\n" + _DELIVERABLE_CONTRACT).strip()
    return True


def apply(event: Any, request: Any, buffer: Any) -> dict[str, Any]:
    """事故 P0-3 总入口：宽门控摘逃生舱工具 + 窄注交付契约。返回处置摘要（可观测/测试）。"""
    sig = detect(event, buffer)
    removed = gate_tools(request) if sig["should_gate"] else []
    injected = inject_contract(request) if sig["should_contract"] else False
    return {**sig, "gated_tools": removed, "contract_injected": injected}


__all__ = [
    "apply", "detect", "gate_tools", "inject_contract",
    "in_correction_loop", "has_attachment",
]
