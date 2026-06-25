"""AdaptationDomain —— 自我进化适应领域 agent（慢变："越聊越像你 / 记得哪招管用"）。

承接 self-evolution-expansion.md（Wave 6）。一个领域、四个子结构（同写节奏、同持久化
blob、同跨域读，拆开只多 plumbing 不多隔离）：

- StyleMirror（_style_target）：口吻向你收敛的目标（镜像 UserModel 观测到的你的风格）。
- TopicAffinity（_topics）：LRU 话题亲和图（爱聊什么，不是全量历史）。
- ExpressionPrefs（_expr）：从交互学到的表达偏好连续量（话密度/正式度/直接度）。
- CopingTable（_coping）：对你低落时四种安抚策略的学到的有效度。

铁律：①独占状态、写仅 EVOLVE（ingest）；③只读 BodySnapshot；④load_dict 容缺向前兼容
（旧档无此域=空起步，新字段缺省=保持初值）。零-LLM、零 IO。

—— 落地分期（4 个 phase-PR）——
本文件是 PR-A【地基】：只交付可持久化的领域骨架（状态 + to_dict/load_dict），进 integration
的 domains dict 后即随 _save_domains/_load_domains 自动持久化。学习写入（ingest）、心象注入
（prompt_line + fragment 接缝）、coping/facets、life 双向分别随 PR-B/C/D 落地——届时再补
对应方法，不在地基里放恒空 stub。

落地前已逐行核验、就地修正设计文档的硬伤（见 memory wave6-adaptation-grounding）：
ExpressionPrefs 的 emoji 维【砍掉】（lexicon 无干净源）；风格三轴键用 UserModel 真实键
'len'/'punct'/'warmth'（非文档误写的 'length'）。
"""

from __future__ import annotations

import math
from typing import Any

# —— ExpressionPrefs ——（emoji 维砍掉：TextSignals 无 emoji_density 等干净源，warm 词表混
# emoji 是脏代理）。其余三维从 lexicon 现有字段干净导出（PR-B 实装观测）。
_EXPR_PREFS = ("verbosity", "formality", "directness")
_EXPR_PREF_INIT = 0.5            # 每维中性先验

# —— CopingTable ——（ESConv-8 里取 4 种，覆盖 沉默陪伴/轻探/共情认同/自我袒露 的实用跨度）
_COPING_STRATEGIES = ("accompany_silence", "gentle_probe",
                      "affirm_empathize", "self_disclose")
_COPING_INIT = 0.5              # 均匀有效度先验：稀疏 distress 事件前也有合理的 day-one 行为

# —— TopicAffinity ——
_TOPIC_CAP = 24                 # LRU 上限：偏好图而非全量历史
_TOPIC_KEY_MAX = 40             # 话题键最大字符（与 FocusDomain 话头 _GIST_MAX 同标）


def _is_num(v: Any) -> bool:
    """是不是真【有限】数值。排除 bool（int 子类，会污染数值字段）；排除 nan/inf。

    int 恒有限（且巨整数喂 math.isfinite 会 OverflowError），故 int 直接放行；只对
    float 验有限性。用于 expr/coping/style_target 的"采纳 vs 保持先验"门控。
    """
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return True
    return isinstance(v, float) and math.isfinite(v)


def _num(v: Any, default: float = 0.0) -> float:
    """容缺转 float：bool / 不可解析 / 非有限（nan/inf）/ 巨整数溢出一律回落 default。

    回落非有限是关键：_load_topics/_load_pending 随后对结果做 int()，int(nan) 抛
    ValueError、int(inf) 抛 OverflowError——脏档（手改/JSON NaN 往返）会废掉整条 load_dict。
    """
    if isinstance(v, bool):
        return default
    try:
        x = float(v)
    except (TypeError, ValueError, OverflowError):
        return default
    return x if math.isfinite(x) else default


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


class AdaptationDomain:
    """适应领域 agent。PR-A：写仅持久化骨架；学习/注入随后续 PR。"""

    name = "adaptation"

    __slots__ = (
        "_style_target",        # dict[str,float]：口吻收敛目标（镜像你的风格，真值非[0,1]）
        "_topics",              # dict[str,dict]：{topic: {aff,last_turn,raised_turn}} LRU
        "_expr",                # dict[str,float] over _EXPR_PREFS（[0,1]）
        "_coping",              # dict[str,float] over _COPING_STRATEGIES（[0,1] 有效度）
        "_coping_pending",      # list[dict]：{strategy,base_distress,turn} 待延迟归因
        "_last_proactive_topic",  # str：上轮主动提起的话题（warm-up 状态）
    )

    def __init__(self) -> None:
        # 风格目标初值留空：尚未学到你的风格（首条消息前 = 无收敛）。PR-B 的收敛在 bond
        # 闸开后才动它，照 UserModel._style_sketch 的真实键 'len'/'punct'/'warmth' 惰性初始化。
        self._style_target: dict[str, float] = {}
        self._topics: dict[str, dict] = {}
        self._expr: dict[str, float] = {k: _EXPR_PREF_INIT for k in _EXPR_PREFS}
        self._coping: dict[str, float] = {s: _COPING_INIT for s in _COPING_STRATEGIES}
        self._coping_pending: list[dict] = []
        self._last_proactive_topic: str = ""

    # ---- 持久化（铁律④：旧档无此域=空起步；缺字段/脏类型保持初值）----

    def to_dict(self) -> dict[str, Any]:
        return {
            "style_target": dict(self._style_target),
            "topics": {k: dict(v) for k, v in self._topics.items()},
            "expr": dict(self._expr),
            "coping": dict(self._coping),
            "coping_pending": [dict(p) for p in self._coping_pending],
            "last_proactive_topic": self._last_proactive_topic,
        }

    def load_dict(self, data: dict[str, Any]) -> None:
        if not isinstance(data, dict):   # 非 dict（list/str/None 脏档）→ 空起步不崩
            return

        st = data.get("style_target")
        if isinstance(st, dict):
            # 真值非 [0,1]（镜像 style_sketch 的原尺度），不 clamp，只过滤非数值。
            self._style_target = {
                str(k)[:_TOPIC_KEY_MAX]: _num(v)
                for k, v in st.items() if _is_num(v)
            }

        tp = data.get("topics")
        if isinstance(tp, dict):
            self._topics = self._load_topics(tp)

        ex = data.get("expr")
        if isinstance(ex, dict):
            for k in _EXPR_PREFS:
                if _is_num(ex.get(k)):
                    self._expr[k] = _clamp01(_num(ex[k], _EXPR_PREF_INIT))

        cp = data.get("coping")
        if isinstance(cp, dict):
            for k in _COPING_STRATEGIES:
                if _is_num(cp.get(k)):
                    self._coping[k] = _clamp01(_num(cp[k], _COPING_INIT))

        pend = data.get("coping_pending")
        if isinstance(pend, list):
            self._coping_pending = self._load_pending(pend)

        lpt = data.get("last_proactive_topic")
        if isinstance(lpt, str):
            self._last_proactive_topic = lpt[:_TOPIC_KEY_MAX]

    @staticmethod
    def _load_topics(tp: dict) -> dict[str, dict]:
        clean: dict[str, dict] = {}
        for k, v in tp.items():
            if not isinstance(v, dict):
                continue
            clean[str(k)[:_TOPIC_KEY_MAX]] = {
                "aff": _clamp01(_num(v.get("aff"))),
                "last_turn": int(_num(v.get("last_turn"))),
                "raised_turn": int(_num(v.get("raised_turn"))),
            }
        # LRU：超容时留 last_turn 最新的一批（旧档异常膨胀也不爆容）。
        if len(clean) > _TOPIC_CAP:
            kept = sorted(clean.items(), key=lambda kv: kv[1]["last_turn"],
                          reverse=True)[:_TOPIC_CAP]
            clean = dict(kept)
        return clean

    @staticmethod
    def _load_pending(pend: list) -> list[dict]:
        clean: list[dict] = []
        for p in pend:
            if not isinstance(p, dict):
                continue
            strat = p.get("strategy")
            if strat in _COPING_STRATEGIES:
                clean.append({
                    "strategy": strat,
                    "base_distress": _num(p.get("base_distress")),
                    "turn": int(_num(p.get("turn"))),
                })
        return clean


__all__ = ["AdaptationDomain"]
