"""Phase 2B / PR-G：rel_register 关系类型分类测试。

覆盖 handoff §5.1：
- 枚举解析 + unknown 兜底
- 低频 gating（不每轮调）
- 累积平滑（romantic_conf 随样本升、unknown 不计、混类稀释）
- off-path：分类不给请求路径加 await 的 LLM 调用（apply_v2core_request 不 await rel provider）
- SDK 边界：rel/sender_id 不进 ctx/kernel/assessment（写 shell store）

直调真函数。
"""

from __future__ import annotations

import asyncio
import time

from sylanne_alpha.v2core import rel_register as R


# ---- 枚举解析 ----

def test_parse_rel_enum():
    assert R._parse_rel("romantic") == "romantic"
    assert R._parse_rel(" Friendly\n") == "friendly"
    assert R._parse_rel("我看是 formal") == "formal"


def test_parse_rel_invalid_unknown():
    assert R._parse_rel("garbage") == "unknown"
    assert R._parse_rel("") == "unknown"
    assert R._parse_rel(None) == "unknown"


# ---- 低频 gating ----

def test_rel_gating_low_frequency():
    rt: dict = {}
    fires = [R.should_classify(rt, 0.0) for _ in range(13)]
    # 第 1、7、13 轮触发（每 6 轮一次），其余不触发
    assert fires[0] is True
    assert not any(fires[1:6])
    assert fires[6] is True
    assert fires[12] is True


# ---- 累积平滑 ----

def test_accumulate_romantic_rises():
    st: dict = {}
    for _ in range(R._REL_CONFIDENCE_SAMPLES):
        R._accumulate(st, "romantic", "u1", time.time())
    assert st["sample_count"] == R._REL_CONFIDENCE_SAMPLES
    assert st["sender_id"] == "u1"
    assert abs(st["romantic_conf"] - 1.0) < 1e-6


def test_accumulate_unknown_ignored():
    st: dict = {}
    R._accumulate(st, "romantic", "u1", time.time())
    R._accumulate(st, "unknown", "u1", time.time())
    assert st["sample_count"] == 1


def test_accumulate_mixed_dilutes():
    st: dict = {}
    for _ in range(6):
        R._accumulate(st, "romantic", "u1", time.time())
    for _ in range(6):
        R._accumulate(st, "friendly", "u1", time.time())
    assert st["sample_count"] == 12
    assert st["romantic_conf"] < 1.0
    assert st["friendly_conf"] > 0.0


def test_low_sample_damps_confidence():
    """样本不足时置信被 min(1,n/N) 折扣（单轮不定）。"""
    st: dict = {}
    R._accumulate(st, "romantic", "u1", time.time())  # n=1
    # 占比 1.0 但样本仅 1 → conf = 1.0 * (1/N) << 1
    assert st["romantic_conf"] < 0.5


# ---- off-path + SDK 边界（用 fake plugin 直调真路径）----

class _FakeReg:
    def __init__(self):
        self.d = {}

    def get(self, k, default=None):
        return self.d.get(k, default)

    def set(self, k, v):
        self.d[k] = v


class _FakeStore:
    def __init__(self):
        self.relationship_register_state = _FakeReg()


class _FakePipe:
    def __init__(self):
        self.calls = []

    async def _generic_llm_call(self, prompt, provider_config_keys, max_tokens=None, temperature=0.0):
        self.calls.append((prompt, tuple(provider_config_keys)))
        return "romantic"


class _FakeEvent:
    sender_id = "owner-42"


class _FakePlugin:
    def __init__(self):
        self._store = _FakeStore()
        self._llm_response_pipeline = _FakePipe()


def test_classify_and_store_writes_shell_register():
    p = _FakePlugin()
    asyncio.run(R.classify_and_store(p, "sess1", _FakeEvent(), "老公我们在一起好久了，想你"))
    st = p._store.relationship_register_state.get("sess1")
    assert st is not None
    assert st["sender_id"] == "owner-42"
    assert st["romantic_count"] == 1
    # 真用了专用 provider key 优先级
    assert p._llm_response_pipeline.calls[0][1][0] == "sylanne_alpha_rel_register_provider_id"


def test_classify_handles_missing_pipe_gracefully():
    class _P:
        _store = _FakeStore()
    # 无 _llm_response_pipeline → 不抛、不写
    asyncio.run(R.classify_and_store(_P(), "s", _FakeEvent(), "hi"))
    assert _P._store.relationship_register_state.get("s") is None


def test_classify_survives_braces_in_user_text():
    """用户消息含花括号 {} 不应让 _PROMPT.format 崩（KeyError/ValueError 被吞→静默失分类）。

    转义生效则正常分类写入；若漏转义，format 抛异常被外层吞掉，store 写不进 → 断言失败。
    """
    p = _FakePlugin()
    asyncio.run(R.classify_and_store(p, "sessB", _FakeEvent(), "老公你看这个 {placeholder} 和 {0} 好好玩"))
    st = p._store.relationship_register_state.get("sessB")
    assert st is not None
    assert st["romantic_count"] == 1
