"""Wave-L1/G4：T1-02（打碎节拍器）接线测试。

覆盖三个独立效应，均在 sylanne_alpha/message_dispatch.py 的分段延迟规划里：
- ① 逐段延迟抖动（uniform(0.6,1.4)，预算 scale 之后叠加，仍吃既有 4.2s 硬顶）。
- ② 走神停顿（整条回复 5% 概率选一个非首段，越过 4.2s 硬顶冲到 5~9s）。
- ③ 身体驱动打字速度（llm_response_pipeline._body_driven_cps：低 energy 更慢、
  高 arousal 更快，clamp 到 [4.5, 11]）。

抖动/走神都吃 rng 参数（对齐 variant_pool.choose 的既有约定），测试传
random.Random(seed) 进来复现，不依赖裸 random 模块全局状态。
"""

from __future__ import annotations

import random
import types

from sylanne_alpha.llm_response_pipeline import LLMResponsePipeline
from sylanne_alpha.message_dispatch import (
    _DISTRACTED_PAUSE_MAX,
    _DISTRACTED_PAUSE_MIN,
    _DISTRACTED_PAUSE_PROBABILITY,
    _JITTER_MAX,
    _JITTER_MIN,
    _message_parts,
    realtime_plan,
)


# ---------------------------------------------------------------------------
# ① 逐段延迟抖动
# ---------------------------------------------------------------------------


class TestSegmentJitter:
    def test_jitter_within_bounds_seeded(self) -> None:
        """种子固定：抖动后每段延迟仍在 [0, 4.2] 内（未触发走神时）。"""
        parts = [f"第{i}段内容不算短" for i in range(6)]
        for seed in range(20):
            rng = random.Random(seed)
            message_parts = _message_parts(parts, chars_per_second=7.5, rng=rng)
            for mp in message_parts:
                assert 0.0 <= mp["delay_before_seconds"] <= 9.0 + 1e-6
                # 非走神段严格不超过既有硬顶 4.2s（走神段允许越顶，见下方测试单独断言）
            # 首段延迟恒为 0（分段发送时首段不等待）
            assert message_parts[0]["delay_before_seconds"] == 0.0

    def test_jitter_changes_delay_vs_unjittered_scale(self) -> None:
        """同一份 parts，不同种子应产生不同的非首段延迟（证明抖动确实生效，不是死值）。"""
        parts = ["今天天气不错呀", "我们出去走走吧", "记得带伞哦下午可能下雨"]
        delays_by_seed = set()
        for seed in range(30):
            rng = random.Random(seed)
            message_parts = _message_parts(parts, chars_per_second=7.5, rng=rng)
            delays_by_seed.add(tuple(mp["delay_before_seconds"] for mp in message_parts))
        # 30 个种子里应该看到不止一种延迟组合（抖动在起作用，不是恒定节拍）
        assert len(delays_by_seed) > 1

    def test_jitter_constants_match_card_spec(self) -> None:
        """±40% 抖动幅度：uniform(0.6, 1.4)。"""
        assert _JITTER_MIN == 0.6
        assert _JITTER_MAX == 1.4

    def test_budget_approximately_respected(self) -> None:
        """budget scale 之后叠加抖动：总和仍有算式上界（非走神段硬顶 4.2 未破）。

        走神段是刻意允许越顶的例外（见 TestDistractedPause），因此这里只钉死
        "至多一段可能是走神、其余段各自不超 4.2" 这条不依赖具体随机结果的恒定不等式。
        """
        long_parts = [f"第{i}行内容稍微长一点让分段更明显一些呀。" for i in range(11)]
        for seed in range(40):
            rng = random.Random(seed)
            message_parts = _message_parts(long_parts, chars_per_second=7.5, rng=rng)
            delays = [mp["delay_before_seconds"] for mp in message_parts]
            worst_case = max(0, len(delays) - 1) * 4.2 + _DISTRACTED_PAUSE_MAX
            assert sum(delays) <= worst_case + 0.1

    def test_no_rng_falls_back_to_global_random(self) -> None:
        """不传 rng 时走全局 random 模块，不炸（生产默认路径）。"""
        plan = realtime_plan("s", "第一段话。第二段话稍微长一点。第三段话也不短。")
        assert plan["message_parts"]
        for mp in plan["message_parts"]:
            assert mp["delay_before_seconds"] >= 0.0


# ---------------------------------------------------------------------------
# ② 走神停顿
# ---------------------------------------------------------------------------


class TestDistractedPause:
    def test_distraction_probability_constant(self) -> None:
        assert _DISTRACTED_PAUSE_PROBABILITY == 0.05
        assert _DISTRACTED_PAUSE_MIN == 5.0
        assert _DISTRACTED_PAUSE_MAX == 9.0

    def test_distracted_pause_triggers_on_low_roll(self) -> None:
        """种子命中 picker.random() < 0.05 分支时，恰好一个非首段越过 4.2s 硬顶。"""
        parts = ["第一段", "第二段内容长一些", "第三段也补一点内容", "第四段收尾啦"]

        class _ForcedDistractionRng(random.Random):
            def random(self) -> float:  # noqa: D401 - 恒命中走神骰子
                return 0.0

        rng = _ForcedDistractionRng()
        rng.seed(1)
        message_parts = _message_parts(parts, chars_per_second=7.5, rng=rng)
        over_cap = [
            mp for mp in message_parts[1:] if mp["delay_before_seconds"] > 4.2
        ]
        assert len(over_cap) == 1, "命中走神骰子应恰好一段越顶"
        assert (
            _DISTRACTED_PAUSE_MIN
            <= over_cap[0]["delay_before_seconds"]
            <= _DISTRACTED_PAUSE_MAX
        )
        # 首段恒不参与走神（card 要求"非首段"）
        assert message_parts[0]["delay_before_seconds"] <= 4.2

    def test_no_distraction_on_high_roll(self) -> None:
        """种子恒不命中走神骰子时，所有段延迟都不超过既有 4.2s 硬顶。"""

        class _NeverDistractionRng(random.Random):
            def random(self) -> float:  # noqa: D401 - 恒不命中走神骰子
                return 0.99

        parts = ["第一段", "第二段内容长一些", "第三段也补一点内容"]
        rng = _NeverDistractionRng()
        rng.seed(1)
        message_parts = _message_parts(parts, chars_per_second=7.5, rng=rng)
        for mp in message_parts:
            assert mp["delay_before_seconds"] <= 4.2 + 1e-9

    def test_distraction_never_picks_first_segment(self) -> None:
        """走神必须是非首段：即使强制命中骰子，首段延迟仍恒为 0。"""

        class _ForcedDistractionRng(random.Random):
            def random(self) -> float:
                return 0.0

        parts = ["第一段", "第二段"]
        for seed in range(10):
            rng = _ForcedDistractionRng()
            rng.seed(seed)
            message_parts = _message_parts(parts, chars_per_second=7.5, rng=rng)
            assert message_parts[0]["delay_before_seconds"] == 0.0


# ---------------------------------------------------------------------------
# ③ 身体驱动打字速度（cps）
# ---------------------------------------------------------------------------


class _FakeEngine:
    def __init__(self, arousal: float, tension: float) -> None:
        self._obs = {"arousal": arousal, "tension": tension}

    def observe(self) -> dict:
        return self._obs


class _FakeComputation:
    def __init__(self, arousal: float, tension: float) -> None:
        self.engine = _FakeEngine(arousal, tension)


class _FakeMortality:
    def __init__(self, exhaustion: float) -> None:
        self.exhaustion = exhaustion


class _FakeBody:
    def __init__(self, exhaustion: float) -> None:
        self.mortality = _FakeMortality(exhaustion)


class _FakeKernel:
    def __init__(self, exhaustion: float, arousal: float, tension: float) -> None:
        self.body = _FakeBody(exhaustion)
        self.computation = _FakeComputation(arousal, tension)


class _FakeHost:
    def __init__(self, exhaustion: float = 0.5, arousal: float = 0.5, tension: float = 0.0) -> None:
        self.kernel = _FakeKernel(exhaustion, arousal, tension)


class TestBodyDrivenCps:
    def test_neutral_body_state_is_baseline(self) -> None:
        """energy=0.5, arousal=0.5, tension=0 → 落回原恒定基线 7.5。"""
        host = _FakeHost(exhaustion=0.5, arousal=0.5, tension=0.0)
        cps = LLMResponsePipeline._body_driven_cps(host)
        assert abs(cps - 7.5) < 1e-9

    def test_low_energy_slows_down(self) -> None:
        """exhaustion=1.0（energy=0）→ 慢，接近 card 给的示例值 5.5。"""
        host = _FakeHost(exhaustion=1.0, arousal=0.5, tension=0.0)
        cps = LLMResponsePipeline._body_driven_cps(host)
        assert abs(cps - 5.5) < 1e-9

    def test_high_arousal_speeds_up(self) -> None:
        """arousal=1.0 → 快，接近 card 给的示例值 9.5。"""
        host = _FakeHost(exhaustion=0.5, arousal=1.0, tension=0.0)
        cps = LLMResponsePipeline._body_driven_cps(host)
        assert abs(cps - 9.5) < 1e-9

    def test_clamp_lower_bound(self) -> None:
        """极端低 energy + 高 tension 同时拖慢：仍不低于 4.5 硬底。"""
        host = _FakeHost(exhaustion=1.0, arousal=0.0, tension=1.0)
        cps = LLMResponsePipeline._body_driven_cps(host)
        assert cps >= 4.5
        assert cps <= 11.0

    def test_clamp_upper_bound(self) -> None:
        """极端高 energy + 高 arousal：仍不超过 11 硬顶。"""
        host = _FakeHost(exhaustion=0.0, arousal=1.0, tension=0.0)
        cps = LLMResponsePipeline._body_driven_cps(host)
        assert cps <= 11.0

    def test_malformed_host_falls_back_to_default(self) -> None:
        """host 结构不符预期（缺字段）时优雅退回默认 7.5，不炸分段管线。"""
        broken_host = types.SimpleNamespace(kernel=types.SimpleNamespace())
        cps = LLMResponsePipeline._body_driven_cps(broken_host)
        assert cps == 7.5
