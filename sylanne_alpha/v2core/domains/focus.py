"""FocusDomain —— 话语焦点领域 agent（"此刻我们在聊什么"的连续表征）。

为什么要有这个域（两条独立漂移路径里的 B，非 turn 结构补丁）：

路径 A（已修，见 llm_request_pipeline 默认分支）：inner_context 以 role=assistant
append 到 contexts 末尾 → 破坏「末尾应是 user turn」→ 模型续写假 assistant。
修复：并入 system_prompt，不持久化。

路径 B（本域防御）：conversation.history 仍保留完整高密度旧文（告白长文等）。
用户发低信息「😋」时，纯注意力竞争下历史语义密度常赢——与 turn 结构无关。
心象片段原先只有情绪/对你/自我/表达倾向，缺【对象】；本域补「话头」，在低信息
消息时钉锚「接着刚才那茬」，不抢 contexts 末尾位。

本域把"对象"补回认知层，与 emotion / memory / narrative 同级：持续维护当前【话头】
（最近一条实义用户消息的要点），经永远在场的心象片段(system_prompt)注入。关键纪律：
- 表情 / 短应答（"😋""嗯""哈哈"）【不夺话头】——它们是上一条话题的延续，不是新话题。
- 仅当【当前消息本身】是低信息延续时，才钉住话头喂给 LLM（"顺着刚才那茬接"）；
  当前是实义新消息时不钉——新话题该由它自己当话头，绝不拿旧话头压住它（防反向漂移）。
这样出手只发生在"低信息消息 + 旧浓 context"这一个真正会漂移的时刻，外科手术式精准。

铁律：①独占状态、写仅 EVOLVE；③只读；④load_dict 容缺向前兼容（旧档无此域=空起步）。
零-LLM、零 IO、零数字（话头是文本要点，非数值，不经 verbal 标定层）。
"""

from __future__ import annotations

from collections import deque
from typing import Any, Deque

from sylanne_alpha.v2core.contracts import BeatContext, Phase

_GIST_MAX = 40          # 话头要点最大字符（防把整段长消息当话头注入）
_RECENT_MAXLEN = 6      # 最近实义话头滚动窗（供"一直在聊"vs"刚提到"措辞，FIFO）
_MIN_MEANINGFUL = 2     # 实义判定：二字中文词（加班/开会/好饿）也是话头

# 纯应答/语气词全集（整条等于其一 → 非实义，不夺话头）。多字优先。
_ACK_WORDS: frozenset = frozenset({
    "嗯", "嗯嗯", "嗯呢", "哦", "哦哦", "噢", "啊", "呵", "呵呵", "哈", "哈哈",
    "哈哈哈", "嘿", "嘿嘿", "好", "好的", "好滴", "好吧", "行", "行吧", "可以",
    "知道了", "收到", "懂了", "ok", "okk", "okay", "嗯嗯嗯", "唔", "诶", "欸",
})


def _meaningful_chars(text: str) -> int:
    """有效字符数：CJK 或字母数字才算（标点 / 表情 / 空白不算）。"""
    n = 0
    for ch in text:
        if ch.isalnum() or "一" <= ch <= "鿿":
            n += 1
    return n


def is_substantive(text: str) -> bool:
    """这条消息是否携带话题（够格当新话头）。

    非实义：纯表情/标点（有效字符=0）、整条是应答语气词、有效字符过少。
    这些都视作上一话题的延续，不另起话头。判据是显式小词表 + 长度下界，不做
    脆弱的逐字过滤（避免重蹈"关键词抽取"那种治标的脆性）。
    """
    t = (text or "").strip()
    if not t:
        return False
    if t.lower() in _ACK_WORDS:
        return False
    return _meaningful_chars(t) >= _MIN_MEANINGFUL


class FocusDomain:
    """话语焦点领域 agent。读：prompt_line（喂心象）；写仅 EVOLVE（ingest）。"""

    name = "focus"

    __slots__ = ("_current", "_recent", "_turn")

    def __init__(self) -> None:
        self._current: str = ""                       # 当前话头（最近一条实义消息要点）
        self._recent: Deque[str] = deque(maxlen=_RECENT_MAXLEN)
        self._turn: int = 0                           # 话头确立时的轮次（可观测/调试）

    # ---- 读接口（PERCEPT/REQUEST 阶段，纯只读）----

    @property
    def current(self) -> str:
        return self._current

    @property
    def recent_topics(self) -> tuple[str, ...]:
        """最近实义话头滚动窗（只读，供测试/观测）。"""
        return tuple(self._recent)

    def prompt_line(self, current_text: str = "") -> str:
        """心象片段"话头"行。仅在【当前消息低信息】且有存量话头时出手钉锚。

        当前是实义新消息 → 返回空串：新话题由它自己承载，不拿旧话头压它（防反向漂移）。
        当前是表情/短应答 → 钉住话头，明确告诉她这是延续、别拐回更早或更浓的旧话题
        （直击"😋 被一段久远告白带跑"的根因）。
        """
        if not self._current:
            return ""
        if is_substantive(current_text):
            return ""
        return (
            f"话头:你这条接的还是刚才「{self._current}」那茬，"
            "顺着它回应，别拐回更早或情绪更浓的旧话题"
        )

    # ---- 写接口（仅 EVOLVE，单一写者）----

    def ingest(self, ctx: BeatContext) -> None:
        """EVOLVE 唯一写：实义消息立/换话头；非实义（表情/应答）保留旧话头。"""
        if ctx.phase is not Phase.EVOLVE:
            return
        text = (ctx.text or "").strip()
        if not is_substantive(text):
            return                                    # 表情/应答不夺话头（核心纪律）
        gist = text[:_GIST_MAX]
        if gist != self._current:
            self._current = gist
            if not (self._recent and self._recent[-1] == gist):
                self._recent.append(gist)
        try:
            self._turn = int(getattr(ctx.body, "turns", 0) or 0)
        except (TypeError, ValueError):
            self._turn = 0

    # ---- 持久化（铁律④：旧档无此域=空起步；新字段容缺）----

    def to_dict(self) -> dict[str, Any]:
        return {
            "current": self._current,
            "recent": list(self._recent),
            "turn": self._turn,
        }

    def load_dict(self, data: dict[str, Any]) -> None:
        if not data:
            return
        cur = data.get("current")
        if isinstance(cur, str):
            self._current = cur[:_GIST_MAX]
        recent = data.get("recent")
        if isinstance(recent, list):
            self._recent = deque(
                (str(x)[:_GIST_MAX] for x in recent if isinstance(x, str)),
                maxlen=_RECENT_MAXLEN,
            )
        try:
            self._turn = int(data.get("turn", 0) or 0)
        except (TypeError, ValueError):
            self._turn = 0


__all__ = ["FocusDomain", "is_substantive"]
