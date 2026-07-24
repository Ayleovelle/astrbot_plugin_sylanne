"""fix/context-integrity 组：跑题内容 CONTRIB 回归。

- (c-i) _STOPWORDS 扩展多字虚词：jieba 整词命中的常见虚词/代词短语不应再
  漏网挤占召回索引槽位（旧实现只覆盖单字，"可以"/"这样"这类整词穿透）。
- (c-ii) v2core PERCEPT 召回与 legacy [记忆参考] 同轮跨路径去重：v2core
  两条路径都会各自召回一次，同一条记忆命中两边会在同一个 prompt 里重复注入。
"""

from __future__ import annotations

import asyncio

from sylanne_alpha.memory_system import _STOPWORDS_MULTI, _tokenize
from sylanne_alpha.v2core.integration import peek_percept_recalled_texts


# ---------------------------------------------------------------------------
# (c-i) 多字虚词 stopwords
# ---------------------------------------------------------------------------

def test_stopwords_multi_contains_curated_function_words():
    """扩展表非空、都是多字（单字表已在别处覆盖，不应重复收录单字）。"""
    assert len(_STOPWORDS_MULTI) >= 20
    assert all(len(w) >= 2 for w in _STOPWORDS_MULTI)


def test_tokenize_filters_multi_char_function_words():
    """jieba 整词命中的虚词（如"可以"/"这样"/"如果"）不应残留在 token 集合里。"""
    tokens = _tokenize("如果你觉得这样也可以，那就这样吧")
    for fw in ("如果", "觉得", "这样", "可以"):
        assert fw not in tokens, f"{fw!r} 应被多字 stopwords 过滤"


def test_tokenize_keeps_substantive_words():
    """过滤虚词不应连带误伤实义词。"""
    tokens = _tokenize("我们去日本旅行，吃了拉面")
    assert "日本" in tokens or "旅行" in tokens
    assert "拉面" in tokens


# ---------------------------------------------------------------------------
# (c-ii) v2core PERCEPT ↔ legacy 同轮去重：peek_percept_recalled_texts
# ---------------------------------------------------------------------------

def test_peek_percept_recalled_texts_empty_when_no_runtime_cache():
    """v2core 未开启/本轮 PERCEPT 未跑：缓存不存在，返回空集（legacy 行为不变）。"""
    class _Plugin:
        pass

    out = peek_percept_recalled_texts(_Plugin(), "any_session")
    assert out == set()


def test_peek_percept_recalled_texts_empty_when_cache_not_dict():
    class _Plugin:
        _v2core_runtimes = "not-a-dict"

    out = peek_percept_recalled_texts(_Plugin(), "s1")
    assert out == set()


def test_peek_percept_recalled_texts_reads_pending_ctx_scratch():
    """构造与 integration._runtime_for 同形的缓存条目，验证能正确抽出文本集合。"""

    class _Ctx:
        def __init__(self, scratch):
            self.scratch = scratch

    ctx = _Ctx({"recalled": [
        {"text": "我们聊过去日本旅行的计划", "confidence": "clear"},
        {"text": "你说你喜欢喝拿铁", "confidence": "clear"},
        {"not_text": "缺 text 键的脏数据，应被安全跳过"},
    ]})

    class _Plugin:
        _v2core_runtimes = {
            "s1": {"pending": {"ctx": ctx}},
        }

    out = peek_percept_recalled_texts(_Plugin(), "s1")
    assert out == {"我们聊过去日本旅行的计划", "你说你喜欢喝拿铁"}
    # 别的 session 不应互相污染
    assert peek_percept_recalled_texts(_Plugin(), "s2") == set()


def test_prepare_memory_context_dedups_against_percept_recall():
    """端到端：legacy _prepare_memory_context 应跳过已被本轮 PERCEPT
    召回过的原文，不重复注入同一条记忆；已退役的 false 配置值不会关闭去重。
    """
    from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline
    from sylanne_alpha.memory_system import MemorySystem
    from sylanne_alpha.session_state_store import SessionStateStore

    shared_text = "我们聊过去日本旅行的计划"
    ms = MemorySystem()
    ms.write_summary(shared_text, source_turns=2, temperature=0.4, importance=0.8)

    store = SessionStateStore()

    class _FakeHostKernelBody:
        def observe_shadow_signal(self, *a, **k):
            pass

    class _FakeKernel:
        body = _FakeHostKernelBody()
        class computation:
            class engine:
                @staticmethod
                def observe():
                    return {"warmth": 0.0}

    class _FakeHost:
        kernel = _FakeKernel()

    class _FakePlugin:
        _store = store
        config = {"sylanne_enable_v2core": True}
        _config = {}

        def _host(self, session_key):
            return _FakeHost()

        def _memory_system_for_session(self, session_key):
            return ms

    pipe = LLMRequestPipeline.__new__(LLMRequestPipeline)
    pipe._p = _FakePlugin()

    async def _persist_kernel(session_key, host):
        return None

    pipe._persist_kernel = _persist_kernel

    class _Ctx:
        def __init__(self, scratch):
            self.scratch = scratch

    ctx = _Ctx({"recalled": [{"text": shared_text, "confidence": "clear"}]})
    pipe._p._v2core_runtimes = {"s1": {"pending": {"ctx": ctx}}}

    unfinished, outreach, memory_fragment = asyncio.run(
        pipe._prepare_memory_context(
            "s1", "日本旅行", gap_seconds=99999.0, realtime_enabled=True,
        )
    )
    assert shared_text not in memory_fragment

    # 已退役的 false 配置值必须被忽略，同轮去重仍然生效。
    pipe._p.config = {"sylanne_enable_v2core": False}
    pipe._p._v2core_runtimes = {"s1": {"pending": {"ctx": ctx}}}
    _, _, memory_fragment2 = asyncio.run(
        pipe._prepare_memory_context(
            "s1", "日本旅行", gap_seconds=99999.0, realtime_enabled=True,
        )
    )
    assert shared_text not in memory_fragment2
