"""v2core 地基阶段回归测试。

验证绞杀式重写新骨架的核心机制（不接真实业务，用桩能力验证编排纪律）：
- 三拍顺序 Percept→Deliberate→Evolve。
- 能力槽注册表驱动：加能力 = register 一行，turn() 主体不变。
- budget_ms 时钟：DELIBERATE 超预算跳过后续能力（热路径硬保证）。
- 写集中在 EVOLVE 拍。
- 单个能力异常不拖垮整轮。
- 意图融合 fuse()。
- BodySnapshot 只读 + trait 安全读。
"""

from __future__ import annotations

import asyncio
import time

from sylanne_alpha.v2core.contracts import (
    BeatContext,
    BodySnapshot,
    Intent,
    Phase,
)
from sylanne_alpha.v2core.self_core import SelfCore


# --- 测试桩 ---------------------------------------------------------------

class FakeBody:
    """BodyPort 桩：返回固定快照。"""

    def __init__(self, **kw):
        self._snap = BodySnapshot(session_key="s", turns=1, **kw)

    def observe(self) -> BodySnapshot:
        return self._snap

    def tick(self, event, assessment=None) -> BodySnapshot:
        return self._snap

    def snapshot(self) -> dict:
        return {}


class RecordingCap:
    """记录各拍被调用顺序的桩能力。"""

    def __init__(self, name, phases, log):
        self.name = name
        self.phases = phases
        self._log = log

    def perceive(self, ctx):
        self._log.append((self.name, "perceive"))
        return Intent(source=self.name, affect={"warmth": 0.1}, priority=1.0, confidence=0.8)

    def deliberate(self, ctx):
        self._log.append((self.name, "deliberate"))
        return Intent(source=self.name, payload={"said": self.name})

    def evolve(self, ctx):
        self._log.append((self.name, "evolve"))


def _run(coro):
    return asyncio.run(coro)


# --- 三拍顺序 -------------------------------------------------------------

def test_three_beat_order():
    log = []
    sc = SelfCore(FakeBody())
    sc.register(RecordingCap("a", (Phase.PERCEPT, Phase.DELIBERATE, Phase.EVOLVE), log))
    _run(sc.turn("s", object(), "hi"))
    assert log == [("a", "perceive"), ("a", "deliberate"), ("a", "evolve")]


def test_phase_groups_all_caps_before_next_phase():
    """所有能力的 perceive 跑完，才进 deliberate（拍是屏障）。"""
    log = []
    sc = SelfCore(FakeBody())
    sc.register(RecordingCap("a", (Phase.PERCEPT, Phase.DELIBERATE), log))
    sc.register(RecordingCap("b", (Phase.PERCEPT, Phase.DELIBERATE), log))
    _run(sc.turn("s", object(), "hi"))
    # 两个 perceive 都在两个 deliberate 之前
    assert log.index(("a", "perceive")) < log.index(("a", "deliberate"))
    assert log.index(("b", "perceive")) < log.index(("a", "deliberate"))


# --- 注册表驱动扩展 -------------------------------------------------------

def test_register_one_line_adds_capability():
    log = []
    sc = SelfCore(FakeBody())
    assert sc.capabilities() == []
    sc.register(RecordingCap("empathy", (Phase.DELIBERATE,), log))
    assert len(sc.capabilities()) == 1
    _run(sc.turn("s", object(), "hi"))
    assert ("empathy", "deliberate") in log


def test_capability_only_runs_its_phases():
    log = []
    sc = SelfCore(FakeBody())
    sc.register(RecordingCap("p_only", (Phase.PERCEPT,), log))
    _run(sc.turn("s", object(), "hi"))
    assert log == [("p_only", "perceive")]  # 没有 deliberate/evolve


# --- 预算时钟 -------------------------------------------------------------

def test_budget_skips_later_deliberate():
    """DELIBERATE 拍预算耗尽后跳过后续能力。"""
    log = []

    class SlowCap:
        name = "slow"
        phases = (Phase.DELIBERATE,)
        def deliberate(self, ctx):
            log.append("slow")
            time.sleep(0.01)  # 10ms，吃光 5ms 预算
            return None

    class LaterCap:
        name = "later"
        phases = (Phase.DELIBERATE,)
        def deliberate(self, ctx):
            log.append("later")
            return None

    sc = SelfCore(FakeBody(), default_budget_ms=5.0)
    sc.register(SlowCap())
    sc.register(LaterCap())
    _run(sc.turn("s", object(), "hi"))
    assert "slow" in log
    assert "later" not in log  # 预算耗尽被跳过


def test_perceive_not_budget_limited():
    """PERCEPT 不受预算限制（纯算术、并发安全）。"""
    log = []

    class SlowPerceive:
        name = "sp"
        phases = (Phase.PERCEPT,)
        def perceive(self, ctx):
            time.sleep(0.01)
            log.append("sp")
            return None

    class P2:
        name = "p2"
        phases = (Phase.PERCEPT,)
        def perceive(self, ctx):
            log.append("p2")
            return None

    sc = SelfCore(FakeBody(), default_budget_ms=5.0)
    sc.register(SlowPerceive())
    sc.register(P2())
    _run(sc.turn("s", object(), "hi"))
    assert log == ["sp", "p2"]  # 都跑了，没因预算跳过


# --- 异常隔离 -------------------------------------------------------------

def test_one_cap_exception_does_not_break_turn():
    log = []

    class Bomb:
        name = "bomb"
        phases = (Phase.PERCEPT, Phase.DELIBERATE, Phase.EVOLVE)
        def perceive(self, ctx): raise ValueError("boom")
        def deliberate(self, ctx): raise ValueError("boom")
        def evolve(self, ctx): raise ValueError("boom")

    sc = SelfCore(FakeBody())
    sc.register(Bomb())
    sc.register(RecordingCap("ok", (Phase.PERCEPT, Phase.DELIBERATE, Phase.EVOLVE), log))
    ctx = _run(sc.turn("s", object(), "hi"))  # 不抛
    assert ("ok", "evolve") in log  # 正常能力仍跑完


# --- 意图融合 -------------------------------------------------------------

def test_fuse_intents():
    intents = [
        Intent(source="a", affect={"warmth": 0.2}, priority=1.0, confidence=0.8, flags=("x",)),
        Intent(source="b", affect={"warmth": 0.4}, priority=1.0, confidence=0.4, flags=("y",),
               payload={"k": "v"}),
    ]
    out = SelfCore.fuse(intents)
    assert set(out["flags"]) == {"x", "y"}
    assert abs(out["confidence"] - 0.6) < 1e-9  # (0.8+0.4)/2
    assert abs(out["affect"]["warmth"] - 0.6) < 1e-9
    assert out["carried"]["b"] == {"k": "v"}


def test_fuse_empty():
    out = SelfCore.fuse([])
    assert out["confidence"] is None
    assert out["affect"] == {}
    assert out["carried"] == {}


# --- BodySnapshot -----------------------------------------------------------

def test_bodysnapshot_frozen():
    snap = BodySnapshot(session_key="s", turns=1, warmth=0.5)
    import dataclasses
    try:
        snap.warmth = 0.9  # type: ignore
        assert False, "应不可变"
    except dataclasses.FrozenInstanceError:
        pass


def test_bodysnapshot_trait_safe():
    snap = BodySnapshot(session_key="s", turns=1, personality={"perception_acuity": 0.8})
    assert snap.trait("perception_acuity") == 0.8
    assert snap.trait("missing", 0.3) == 0.3  # 缺失给默认


def test_unknown_phase_register_rejected():
    sc = SelfCore(FakeBody())

    class BadCap:
        name = "bad"
        phases = ("not_a_phase",)  # type: ignore
        def perceive(self, ctx): return None

    try:
        sc.register(BadCap())
        assert False, "应拒绝未知相位"
    except ValueError:
        pass
