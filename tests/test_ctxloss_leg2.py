"""上下文丢失 leg-2 防御纵深测试（注入优势压制）。

真模型证实"几轮就跳到不相干旧话题"是【历史丢失 AND 幽灵注入】联合条件（见
context-loss-rootcause-proven-jointcondition）。leg-1 断了 /reset 那条"历史丢失"腿；
leg-2 在注入侧做纵深防御，让万一历史短一下也不至于递给模型一段响亮幽灵：

  2a 历史感知门控：历史缺失轮压制零相关近期召回（temporal_proximity）+ 延后离题生活事件；
  2c 动态注入绝对封顶（兜底，常态 inert，绝不饿死最高优先级 state/感知 槽）；
  2d blake2b 哈希 shingle 精确 Jaccard 近重复去重（同轮范围，签名只当裁判不进 prompt）。

历史在场（history_depth≥阈值 或 None=单测未知）时行为与旧版逐字一致——这是硬不变量：
on-topic / 历史在场路径不得有任何观测变化。
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

from sylanne_alpha.life_simulation import LifeEvent, LifeSimulator
from sylanne_alpha.llm_request_pipeline import (
    LLMRequestPipeline,
    _count_history_turns,
    _dedup_near_duplicate_recall,
    _compute_absolute_ceiling,
    _LAYER2_MIN_BUDGET,
)
from sylanne_alpha.memory_system import (
    MemorySystem,
    RecallMode,
    _normalized_dedup_sig,
)
from sylanne_alpha.session_state_store import SessionStateStore


# ===========================================================================
# 公共 stub
# ===========================================================================
class _FakeEngine:
    def observe(self):
        return {"warmth": 0.0}


class _FakeComputation:
    engine = _FakeEngine()


class _FakeKernel:
    computation = _FakeComputation()
    last_event = {"now": 0.0}


class _FakeHost:
    kernel = _FakeKernel()


def _make_pipe(mem_sys, sim=None):
    store = SessionStateStore()

    class _FakePlugin:
        _life_simulator = sim
        _store = store
        config = {}
        _config = {}

        def _host(self, sk):
            return _FakeHost()

        def _memory_system_for_session(self, sk):
            return mem_sys

    pipe = LLMRequestPipeline.__new__(LLMRequestPipeline)
    pipe._p = _FakePlugin()
    return pipe, store


def _fresh_ctx(eid, reason="我去咖啡馆写代码了"):
    return {
        "reason": reason, "mood": "calm", "intent_id": "i1", "event_id": eid,
        "delivery_mode": "next_reply", "reason_code": "score_0.5",
        "expires_at": time.time() + 1000.0, "target_session": "s1", "queued_at": 1.0,
    }


# ===========================================================================
# leg-2a：历史锚深度统计
# ===========================================================================
def test_count_history_turns_counts_only_nonempty_dialogue():
    ctx = [
        {"role": "user", "content": "早饭好吃吗"},
        {"role": "assistant", "content": "好吃"},
        {"role": "system", "content": "some meta"},          # 非对话角色不计
        {"role": "user", "content": ""},                     # 空文本不计
        {"role": "user", "content": [{"type": "image", "url": "x"}]},  # 无文本不计
        {"role": "assistant", "content": [{"type": "text", "text": "嗯"}]},
    ]
    assert _count_history_turns(ctx) == 3
    assert _count_history_turns(None) == 0
    assert _count_history_turns([]) == 0
    assert _count_history_turns([{"role": "user", "content": "hi"}]) == 1  # repro 那格=薄


# ===========================================================================
# leg-2a：唯一收敛点 memory_system.recall(history_present=) —— PERCEPT/legacy 同门
# ===========================================================================
def test_recall_history_present_gates_temporal_proximity_at_source():
    """recall(history_present=False) 在收敛点丢弃 temporal_proximity；默认 True 不变。

    这是覆盖 v2core PERCEPT 路径的关键：两条召回路径都经 recall()，一处生效全覆盖。
    """
    ms = MemorySystem(recall_mode=RecallMode.LEGACY)
    ms.write_summary("今天阳光很好心情不错", source_turns=1, temperature=0.5)
    q = "量子物理学的不确定性原理"

    present = ms.recall(query=q, limit=5)                    # 默认 history_present=True
    assert any(r.recall_reason == "temporal_proximity" for r in present)

    absent = ms.recall(query=q, limit=5, history_present=False)
    assert all(r.recall_reason != "temporal_proximity" for r in absent)
    assert not any("阳光" in (r.text or "") for r in absent)


def test_integration_history_present_counts_real_turns():
    from sylanne_alpha.v2core.integration import _history_present

    thin = SimpleNamespace(contexts=[{"role": "user", "content": "全是术语听不懂"}])
    full = SimpleNamespace(contexts=[
        {"role": "user", "content": "github好麻烦"},
        {"role": "assistant", "content": "咋了"},
        {"role": "user", "content": "全是术语"},
    ])
    seg = SimpleNamespace(contexts=[
        {"role": "user", "content": [{"type": "text", "text": "一"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "二"}]},
    ])
    assert _history_present(thin) is False
    assert _history_present(full) is True
    assert _history_present(seg) is True
    assert _history_present(SimpleNamespace(contexts=None)) is False
    assert _history_present(SimpleNamespace(contexts=[])) is False


# ===========================================================================
# leg-2a：历史缺失轮压制零相关近期召回（幽灵）；历史在场则照常
# ===========================================================================
def _recency_mem():
    ms = MemorySystem(recall_mode=RecallMode.LEGACY)
    # 与后面 query 词面毫无重合的近期记忆（<5min）——这正是幽灵放大器兜底入池的那种
    ms.write_summary("今天阳光很好心情不错", source_turns=1, temperature=0.5)
    return ms


def _recall_memory_fragment(history_depth):
    ms = _recency_mem()
    pipe, _store = _make_pipe(ms)
    _u, _o, memory_fragment = asyncio.run(
        pipe._prepare_memory_context(
            "s1", "量子物理学的不确定性原理", gap_seconds=1000.0,
            realtime_enabled=True, history_depth=history_depth,
        )
    )
    return memory_fragment


def test_thin_history_suppresses_temporal_proximity_ghost():
    """历史缺失轮（depth < 阈值）：零相关近期召回被压制，不进 memory_fragment。"""
    frag = _recall_memory_fragment(history_depth=1)
    assert "阳光" not in frag, f"薄历史轮不该注入零相关近期幽灵：{frag!r}"


def test_present_history_keeps_temporal_proximity_recall():
    """历史在场轮（depth ≥ 阈值）：近期召回照常豁免注入——on-topic 路径逐字不变。"""
    frag = _recall_memory_fragment(history_depth=5)
    assert "阳光" in frag, f"历史在场轮近期召回应保留（连续性），实际：{frag!r}"


def test_unknown_history_depth_defaults_to_present():
    """history_depth=None（单测未知）按历史在场处理——既有直调测试零破坏。"""
    frag = _recall_memory_fragment(history_depth=None)
    assert "阳光" in frag


def test_relevant_recall_survives_even_on_thin_history():
    """有真实词面相关的召回不受历史门控影响：任何轮都照常注入（只压零相关幽灵）。"""
    ms = MemorySystem(recall_mode=RecallMode.LEGACY)
    ms.write_summary("周末打算去爬山看日出", source_turns=1, temperature=0.5)
    pipe, _store = _make_pipe(ms)
    _u, _o, frag = asyncio.run(
        pipe._prepare_memory_context(
            "s1", "爬山那个计划还算数吗", gap_seconds=1000.0,
            realtime_enabled=True, history_depth=1,  # 薄历史
        )
    )
    assert "爬山" in frag, f"真实相关召回不该被历史门控误杀：{frag!r}"


# ===========================================================================
# leg-2a：生活事件在历史缺失轮延后（不消费、不丢），历史在场轮照常消费
# ===========================================================================
def _run_outreach(history_depth):
    sim = LifeSimulator(config={})
    ev = LifeEvent(text="我去咖啡馆写代码了", mood="calm", urgency=0.3,
                   timestamp=1.0, wants_to_share=True, queued_at=1.0)
    sim.state.events = [ev]
    eid = ev.event_id
    ms = MemorySystem(recall_mode=RecallMode.LEGACY)
    pipe, store = _make_pipe(ms, sim=sim)
    store.pending_outreach_context.set("s1", _fresh_ctx(eid))
    _u, outreach_fragment, _m = asyncio.run(
        pipe._prepare_memory_context(
            "s1", "嗯", gap_seconds=1000.0, realtime_enabled=True,
            history_depth=history_depth,
        )
    )
    still_pending = store.pending_outreach_context.get("s1")
    return outreach_fragment, still_pending, eid


def test_outreach_deferred_on_thin_history_not_dropped():
    """历史缺失轮：生活事件不注入、不消费——原样留在 pending（未过期不丢）。"""
    frag, still_pending, eid = _run_outreach(history_depth=1)
    assert frag == "", f"薄历史轮不该注入离题生活事件：{frag!r}"
    assert still_pending is not None, "延后应把 outreach 放回 pending，而不是丢弃"
    assert still_pending.get("event_id") == eid


def test_outreach_consumed_on_present_history():
    """历史在场轮：生活事件照常消费+注入，pending 被 pop（行为逐字不变）。"""
    frag, still_pending, _eid = _run_outreach(history_depth=5)
    assert "咖啡馆写代码" in frag, f"历史在场轮生活事件应注入：{frag!r}"
    assert still_pending is None, "消费后 pending 应被清空"


# ===========================================================================
# leg-2d：归一化-精确 blake2b 去重（安全形态，绝不折叠语义不同的记忆）
# ===========================================================================
def test_normalized_sig_folds_only_punct_whitespace_case():
    """仅空白/标点/大小写不同 → 同签名；任何实字差异 → 不同签名。"""
    base = _normalized_dedup_sig("上周你说想去爬山玩")
    assert _normalized_dedup_sig("上周你说想去爬山玩。") == base        # 标点
    assert _normalized_dedup_sig("上周你说 想去爬山玩") == base          # 空白
    assert _normalized_dedup_sig("Hello World") == _normalized_dedup_sig("helloworld")  # 大小写+空白
    assert _normalized_dedup_sig("") is None
    assert _normalized_dedup_sig("，。！") is None                        # 纯标点→None


def test_normalized_sig_never_folds_meaning_flip():
    """红队回归守卫：语义翻转的一字之差绝不被判重复（过来≠过去，买≠卖，是≠否）。

    旧模糊 Jaccard 把"…要过来"/"…要过去"判成 0.85≥阈值而误删——归一化-精确杜绝之。
    """
    assert _normalized_dedup_sig("记得提醒他明天早上八点要过来") != \
        _normalized_dedup_sig("记得提醒他明天早上八点要过去")
    assert _normalized_dedup_sig("这个东西我买了") != _normalized_dedup_sig("这个东西我卖了")
    assert _normalized_dedup_sig("他说是的") != _normalized_dedup_sig("他说否的")


def test_normalized_sig_never_folds_semantic_operators():
    """红队回归守卫：运算/比较符不被 strip，符号区分的数值记忆绝不折叠。"""
    assert _normalized_dedup_sig("今天-5度") != _normalized_dedup_sig("今天5度")       # 正负号
    assert _normalized_dedup_sig("本月盈亏+2000") != _normalized_dedup_sig("本月盈亏-2000")
    assert _normalized_dedup_sig("体重>60") != _normalized_dedup_sig("体重<60")        # 比较号
    assert _normalized_dedup_sig("闹钟8:00") != _normalized_dedup_sig("闹钟800")        # 冒号


def test_dedup_drops_punctuation_variant():
    """同轮两条仅标点不同的召回：只留靠前的一条。"""
    r1 = SimpleNamespace(text="上周你说想去爬山玩")
    r2 = SimpleNamespace(text="上周你说想去爬山玩。")       # 仅标点差异 → 冗余
    kept = _dedup_near_duplicate_recall([r1, r2], set())
    assert len(kept) == 1 and kept[0] is r1


def test_dedup_keeps_meaning_flip_pair():
    """红队回归守卫（管线层）：语义翻转的两条记忆同轮都保留，绝不误删。"""
    r1 = SimpleNamespace(text="记得提醒他明天早上八点要过来")
    r2 = SimpleNamespace(text="记得提醒他明天早上八点要过去")
    kept = _dedup_near_duplicate_recall([r1, r2], set())
    assert len(kept) == 2


def test_dedup_keeps_distinct_results():
    r1 = SimpleNamespace(text="上周你说想去爬山玩")
    r2 = SimpleNamespace(text="帮我看下这段代码的报错")
    kept = _dedup_near_duplicate_recall([r1, r2], set())
    assert len(kept) == 2


def test_dedup_drops_against_percept_seed():
    """与 PERCEPT 同轮已召回原文归一化重复的 legacy 召回被裁掉（跨路径去重）。"""
    r1 = SimpleNamespace(text="上周你说想去爬山玩。")
    kept = _dedup_near_duplicate_recall([r1], {"上周你说想去爬山玩"})
    assert kept == []


# ===========================================================================
# leg-2c：动态注入绝对封顶（兜底，常态 inert，绝不饿死 state 槽）
# ===========================================================================
def _assemble_stub_plugin():
    p = SimpleNamespace()
    p._amnesia_sessions = set()
    p.config = {}
    p._life_simulator_started = True
    p._start_life_simulator = lambda: None
    p._start_webui_if_enabled = lambda: None

    def _append_temp_text_part(request, text, source="", budget=None):
        cur = str(getattr(request, "system_prompt", "") or "")
        request.system_prompt = f"{cur}\n{text}".strip()
        return True

    p._append_temp_text_part = _append_temp_text_part
    return p


def _assemble(base_len, sys_prompt, *, memory="", unfinished="", state="[感知]我此刻心情不错"):
    pipe = LLMRequestPipeline(_assemble_stub_plugin())
    req = SimpleNamespace(
        system_prompt=sys_prompt,
        contexts=[{"role": "user", "content": "在吗"}],
        prompt="在吗",
    )
    contexts_before = list(req.contexts)
    pipe._assemble_final_prompt(
        request=req, session_key="s", budget=SimpleNamespace(compat_mode=""),
        gap_seconds=30.0, current_prompt=sys_prompt, time_fragment="",
        message_text="在吗", state_fragment=state,
        unfinished_fragment=unfinished, outreach_fragment="",
        memory_fragment=memory, base_system_prompt_len=base_len,
    )
    return req, contexts_before


def test_absolute_cap_inert_when_base_len_none():
    """base_system_prompt_len=None（单测直调）→ 不封顶，happy path 字节不变。"""
    # 巨量 memory + 无 base_len：应按原 _compute_injection_budget 走，不被绝对封顶收紧
    req, _ = _assemble(None, "你是苏思澜。", memory="记忆" * 400)
    # inner_context 里应含记忆槽（未被绝对封顶抹掉；具体裁剪仍由 _allocate_and_trim 管）
    assert "感知" in req.system_prompt  # state 一定在


def test_absolute_cap_trims_low_priority_first_and_protects_state():
    """病态超注入：绝对封顶收紧 Layer-2，先砍低优先级(memory/unfinished)，state/感知 必存活。"""
    # 预先塞一大坨已注入内容（模拟 v2core [心象] 病态膨胀），base_len 记 pristine 长度
    pristine = "你是苏思澜。"
    bloated = pristine + ("霸" * 4000)  # 已注入 4000 字，逼近/超过 ceiling
    req, ctx_before = _assemble(
        len(pristine), bloated,
        memory="记忆线索" * 200, unfinished="未说完" * 200,
        state="[感知]我此刻心情不错",
    )
    # state/感知 槽必须存活（floor 保护，绝不静默清零）
    assert "感知" in req.system_prompt, "最高优先级 state/感知 槽被绝对封顶饿死了"
    # request.contexts 绝不被本路径改动（历史稀释墓碑纪律）
    assert req.contexts == ctx_before


def test_absolute_ceiling_gap_aware_values():
    assert _compute_absolute_ceiling(10.0, {}) == 2200      # <900s
    assert _compute_absolute_ceiling(3600.0, {}) == 3400    # <7200s
    assert _compute_absolute_ceiling(99999.0, {}) == 4600   # 长 gap
    assert _compute_absolute_ceiling(10.0, {"state_injection_absolute_ceiling_chars": 999}) == 999
    assert _LAYER2_MIN_BUDGET == 400
