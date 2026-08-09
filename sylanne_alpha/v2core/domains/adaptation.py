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
PR-A【地基】：可持久化骨架（四子结构状态 + to_dict/load_dict），进 domains dict 自动持久化。
PR-B【口吻镜像+话题亲和，本批】：StyleMirror（_style_target 向你的风格 bond 闸收敛/敌意背离）
+ TopicAffinity（_topics 亲和 EMA+衰减+LRU）的 ingest 学习，prompt_line 出风格漂移/话题提示
两类轻线索，经 fragment 接进心象（STATE 档）。
PR-C：ExpressionPrefs（学习+过滤 drive 三bit）+ CopingTable（coping 指令 PINNED）+ 可改信念 facets。
PR-D：life 双向（interest_hint 反哺 life-sim，复用 top_topics/select_proactive_topic）+ WebUI 观测。

落地前已逐行核验、就地修正设计文档的硬伤（见 memory wave6-adaptation-grounding）：
ExpressionPrefs 的 emoji 维【砍掉】（lexicon 无干净源）；风格三轴键用 UserModel 真实键
'len'/'punct'/'warmth'（非文档误写的 'length'）。
"""

from __future__ import annotations

import logging
import math
from typing import Any

from sylanne_alpha.v2core.contracts import BeatContext, Phase
from sylanne_alpha.v2core.domains.focus import is_substantive

_log = logging.getLogger(__name__)

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

# —— StyleMirror（PR-B）—— [CAT / Giles：关系条件化趋同；陌生人不趋同，敌意背离]
_STYLE_DIMS = ("len", "punct", "warmth")   # 镜像 UserModel._style_sketch 的【真实键】（'len' 非 'length'）
_STYLE_CONVERGE_RATE = 0.03     # 显式收敛步长；LLM 已隐式 accommodate ~0.01-0.02，合计落在 CAT 0.04-0.05 经验带，勿调高
_STYLE_BOND_FLOOR = 0.15        # bond 低于此不收敛（陌生人不趋同，CAT 核心）
_STYLE_DIVERGE_RATE = 0.02      # 敌意（defensiveness 高）时背离步长
_DEFENSIVE_GATE = 0.25          # defensiveness ≥ 此判敌意 → 背离
_STYLE_HINT = "和你聊久了，用词节奏在不知不觉往你那边靠"

# —— TopicAffinity 学习（PR-B）—— [EVOLVCONV：偏好图非全量历史]
_TOPIC_AFFINITY_ALPHA = 0.20    # 亲和 EMA 步长（话题喜好按对话速度漂，比风格快、比反射慢）
_TOPIC_DECAY = 0.98             # 每 EVOLVE 全表乘性衰减（没碰的话题降温——偏好是活的不是账本）
_TOPIC_PROACTIVE_FLOOR = 0.35   # 主动提起话题的最低亲和
_TOPIC_HINT_MAX = 12            # 话题提示只用够短、像主题词的话头（长句 gist 不当话题报，FocusDomain 不给主题词级粒度）


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
    """适应领域 agent。PR-B：StyleMirror + TopicAffinity 学习（ingest）+ 心象注入（prompt_line）。"""

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

    # ---- 写接口（仅 EVOLVE，单一写者；纯算术、零 LLM、零 IO）----

    def ingest(self, ctx: BeatContext) -> None:
        """EVOLVE 唯一写：①口吻向你收敛（bond 闸、敌意背离）；②话题亲和 EMA+衰减+LRU。

        跨域只读 usermodel(bond/style_sketch/defensiveness) 与 focus(current)——读不写，
        符合铁律①单一写者。任一子步自带容错，单步异常不拖垮另一步、不抛出（TurnRunner
        的 EVOLVE 循环会吞异常并静默，故 ingest 自身必须稳）。
        """
        if ctx.phase is not Phase.EVOLVE:
            return
        try:
            turn = int(getattr(ctx.body, "turns", 0) or 0)
        except (TypeError, ValueError):
            turn = 0
        # 两子步各自隔离：一步崩不拖垮另一步、ingest 整体不抛（TurnRunner 只静默 log）。
        try:
            self._ingest_style(ctx)
        except Exception:
            _log.debug("adaptation style ingest skipped", exc_info=True)
        try:
            self._ingest_topics(ctx, turn)
        except Exception:
            _log.debug("adaptation topic ingest skipped", exc_info=True)

    def _ingest_style(self, ctx: BeatContext) -> None:
        """StyleMirror：bond≥floor 且不敌意 → 口吻向你的风格收敛；敌意 → 背离；否则不动。"""
        um = ctx.domain("usermodel")
        if um is None:
            return
        try:
            bond = float(um.bond())
            sketch = um.style_sketch()
            defensiveness = float(um.expectation().get("defensiveness", 0.0) or 0.0)
        except (AttributeError, TypeError, ValueError):
            return
        if not isinstance(sketch, dict) or not sketch:
            return  # 还没观测到你的风格（首条消息前）→ 不动
        if bond >= _STYLE_BOND_FLOOR and defensiveness < _DEFENSIVE_GATE:
            rate = _STYLE_CONVERGE_RATE
        elif defensiveness >= _DEFENSIVE_GATE:
            rate = -_STYLE_DIVERGE_RATE  # 敌意 → 背离
        else:
            return  # bond 不够且不敌意 → 陌生人不趋同
        for d in _STYLE_DIMS:
            v = sketch.get(d)
            if not _is_num(v):
                continue
            cur = self._style_target.get(d, float(v))  # 惰性初始化为首次观测值
            new_val = cur + rate * (float(v) - cur)
            if d in ("len", "punct"):
                new_val = max(0.0, new_val)  # 长度/标点密度物理非负，持续背离不得跌破 0（gemini review）
            self._style_target[d] = new_val

    def _ingest_topics(self, ctx: BeatContext, turn: int) -> None:
        """TopicAffinity：当前实义话头亲和 EMA 上涨（投入/唤起加权）；全表衰减；LRU 封顶。

        每条记录做形状守卫：畸形/非数值条目被跳过而非中断整批（防部分迁移/损坏，sourcery review）。
        """
        for rec in self._topics.values():  # 全表降温（没碰的话题冷却）
            if isinstance(rec, dict) and _is_num(rec.get("aff")):
                rec["aff"] = _clamp01(float(rec["aff"]) * _TOPIC_DECAY)
        focus = ctx.domain("focus")
        topic = ""
        if focus is not None:
            try:
                topic = (focus.current or "").strip()
            except (AttributeError, TypeError):
                topic = ""
        if topic and is_substantive(topic):
            weight = _clamp01(0.5 + 0.5 * self._engagement(ctx) + 0.3 * self._arousal(ctx))
            key = topic[:_TOPIC_KEY_MAX]
            rec = self._topics.get(key)
            if not isinstance(rec, dict) or not _is_num(rec.get("aff")):  # 新建或修复畸形
                rec = {"aff": 0.0, "last_turn": turn, "raised_turn": turn}
                self._topics[key] = rec
            aff = float(rec["aff"])
            rec["aff"] = _clamp01(aff + _TOPIC_AFFINITY_ALPHA * weight * (1.0 - aff))
            rec["last_turn"] = turn
        if len(self._topics) > _TOPIC_CAP:  # LRU：留 last_turn 最新的一批
            keep = sorted(self._topics.items(),
                          key=lambda kv: self._rec_num(kv[1], "last_turn"), reverse=True)[:_TOPIC_CAP]
            self._topics = dict(keep)

    @staticmethod
    def _rec_num(rec: Any, field: str) -> float:
        """安全取话题记录字段数值（畸形/非数值 → 0.0），供排序/筛选不被坏记录绊倒。"""
        if isinstance(rec, dict):
            v = rec.get(field)
            if _is_num(v):
                return float(v)
        return 0.0

    @staticmethod
    def _engagement(ctx: BeatContext) -> float:
        sig = ctx.scratch.get("signals")
        try:
            return _clamp01(float(getattr(sig, "engagement_cue", 0.0) or 0.0))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _arousal(ctx: BeatContext) -> float:
        a = ctx.scratch.get("assessment")  # AppraisalCapability 仅在有用户文本轮写（mentalize.py）
        if not isinstance(a, dict):
            return 0.0
        try:
            return _clamp01(float(a.get("arousal", 0.0) or 0.0))
        except (TypeError, ValueError):
            return 0.0

    # ---- 读接口（PERCEPT/REQUEST，纯只读）----

    def select_proactive_topic(self) -> str:
        """最高亲和且过 floor 的话题（供心象话题提示 + PR-D 主动/兴趣）。无则空串。"""
        cands = [(self._rec_num(v, "aff"), k) for k, v in self._topics.items()]
        cands = [(a, k) for a, k in cands if a >= _TOPIC_PROACTIVE_FLOOR]
        if not cands:
            return ""
        cands.sort(reverse=True)
        return cands[0][1]

    def top_topics(self, limit: int = 3) -> list[str]:
        """亲和降序的话题（观测/测试/PR-D 兴趣 hint）。"""
        ranked = sorted(self._topics.items(),
                        key=lambda kv: self._rec_num(kv[1], "aff"), reverse=True)
        return [k for k, _ in ranked[:max(0, limit)]]

    def prompt_line(self, current_text: str = "", bond: float = 0.0) -> str:
        """心象「适应层」行（纯模板、零数字、零 LLM）。PR-B 出两类轻提示：

        - 风格漂移：bond 过 floor 且已学到你的风格 → 一句"用词往你靠"。
        - 话题亲和：当前消息低信息（无话可接）且有够短、过 floor 的高亲和话题 → 轻轻往那带。
        coping 指令 + user_distress 参数随 PR-C 补（届时改签名 + fragment 调用）。
        """
        bits: list[str] = []
        try:
            if bond >= _STYLE_BOND_FLOOR and self._style_target:
                bits.append(_STYLE_HINT)
            if current_text and not is_substantive(current_text):
                topic = self.select_proactive_topic()
                if topic and len(topic) <= _TOPIC_HINT_MAX:
                    bits.append(f"你常爱聊「{topic}」，接得上的话可以自然往那带一带")
        except Exception:
            _log.debug("adaptation prompt_line failed", exc_info=True)
            return ""
        return "；".join(bits)

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
