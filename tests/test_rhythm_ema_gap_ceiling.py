"""rhythm_ema gap-ceiling hygiene：跨停机/离开的巨大 gap 不得污染节律 EMA。

病（实机复现）：`_rhythm_ema` 是相邻用户消息间隔(秒)的 EMA，但 gap 无上限、`_last_user_ts`
持久化。加载旧数据后第一条消息把"跨停机间隔"(可达数天)当成一次节律 gap 喂进 EMA，
α=0.2 一发就把 EMA 顶到上万(实测 1 万+)，reply_overdue 随之几乎永不触发，T2 静默/召回失灵。
修：0<gap<=_RHYTHM_GAP_CEILING 才计入；load 时把旧污染值夹回上限愈合。
"""

from __future__ import annotations

import asyncio

from sylanne_alpha.v2core.contracts import BodySnapshot
from sylanne_alpha.v2core.domains.user_model import (
    _RHYTHM_GAP_CEILING,
    UserModelDomain,
)
from sylanne_alpha.v2core.renderer import DefaultRenderer
from sylanne_alpha.v2core.self_core import SelfCore
from sylanne_alpha.v2core.turn_runner import TurnRunner


class _FakeBP:
    def observe(self) -> BodySnapshot:
        return BodySnapshot(session_key="s", turns=0, warmth=0.5, surprise=0.2)

    def tick(self, event, assessment=None) -> BodySnapshot:  # noqa: ANN001
        return self.observe()

    def snapshot(self) -> dict:
        return {}

    def learn(self, *a, **k) -> None:  # noqa: ANN002, ANN003
        pass


def _runner() -> tuple[TurnRunner, UserModelDomain]:
    sc = SelfCore(_FakeBP())
    return TurnRunner(sc, DefaultRenderer()), UserModelDomain()


def _feed(runner: TurnRunner, um: UserModelDomain, now: float, text: str = "在吗") -> None:
    event = {"now": now, "phase": "response", "flags": ["response"]}
    asyncio.run(runner.run_turn("s", event, text, domains={"usermodel": um}, draft="在的~"))


def test_offline_gap_does_not_pollute_rhythm() -> None:
    """几轮 30s cadence 学到 ~30s 后，一个跨停机巨 gap 不得把 EMA 顶飞。"""
    runner, um = _runner()
    t = 1000.0
    for _ in range(5):          # 建立 ~30s 的活跃对话节律
        _feed(runner, um, t)
        t += 30.0
    learned = um._rhythm_ema
    assert learned is not None and learned <= 60.0, learned

    # 模拟"插件停机两天后加载旧数据 + 用户回来说话"：一个巨大的跨停机 gap
    t += 2 * 24 * 3600.0        # +2 天
    _feed(runner, um, t)
    # EMA 必须没有被这个离群 gap 拉动（仍是活跃节律量级），且绝不超过上限
    assert um._rhythm_ema is not None
    assert um._rhythm_ema <= _RHYTHM_GAP_CEILING
    assert abs(um._rhythm_ema - learned) < 1e-6, (
        f"离群 gap 污染了节律 EMA：{learned} -> {um._rhythm_ema}"
    )
    # 但 last_user_ts 必须推进（reply_overdue 仍以最近一次为基准）
    assert um._last_user_ts == t

    # 恢复正常对话后继续学得动
    t += 30.0
    _feed(runner, um, t)
    assert um._rhythm_ema is not None and um._rhythm_ema <= _RHYTHM_GAP_CEILING


def test_gap_within_ceiling_still_learns() -> None:
    """上限内(如 20 分钟)的慢节律仍照常学习，不被误杀。"""
    runner, um = _runner()
    t = 1000.0
    slow = 1200.0               # 20 分钟，低于 1 小时上限
    for _ in range(4):
        _feed(runner, um, t)
        t += slow
    assert um._rhythm_ema is not None
    assert 600.0 < um._rhythm_ema <= _RHYTHM_GAP_CEILING


def test_load_resets_polluted_or_corrupt_rhythm_ema() -> None:
    """加载越界(上万)/NaN/inf/负/0 的 rhythm_ema → 置 None 冷启（红队：夹回上限劣于重置）。"""
    for bad in (12345.0, float("nan"), float("inf"), -5.0, 0.0):
        um = UserModelDomain()
        um.load_dict({"rhythm_ema": bad, "last_user_ts": 1000.0})
        assert um._rhythm_ema is None, bad

    # 上限内的正常旧值原样保留，不被动
    um2 = UserModelDomain()
    um2.load_dict({"rhythm_ema": 42.0, "last_user_ts": 1000.0})
    assert um2._rhythm_ema == 42.0

    # 边界：正好等于上限，保留（inclusive）
    um3 = UserModelDomain()
    um3.load_dict({"rhythm_ema": _RHYTHM_GAP_CEILING, "last_user_ts": 1000.0})
    assert um3._rhythm_ema == _RHYTHM_GAP_CEILING


def test_huge_first_gap_leaves_ema_none() -> None:
    """ema 还是 None 时来一个跨停机巨 gap，不得把 ema 初始化成巨值（首轮 init 路径也守）。"""
    runner, um = _runner()
    _feed(runner, um, 1000.0)                    # 建 last_user_ts，ema 仍 None（无前值可算 gap）
    assert um._rhythm_ema is None
    _feed(runner, um, 1000.0 + 5 * 24 * 3600.0)  # 5 天后第一条（跨停机）
    assert um._rhythm_ema is None                # 巨 gap 被拒，ema 不被初始化成巨值
    assert um._last_user_ts == 1000.0 + 5 * 24 * 3600.0


def test_reply_overdue_sane_after_offline_gap() -> None:
    """污染被挡住后，reply_overdue 对正常沉默仍能正确报超期(功能没被节律污染废掉)。"""
    runner, um = _runner()
    t = 1000.0
    for _ in range(5):          # ~30s 节律
        _feed(runner, um, t)
        t += 30.0
    # 巨 gap 一发
    t += 2 * 24 * 3600.0
    _feed(runner, um, t)
    # 距上次消息 90s（3× 的 ~30s 节律）应判超期 > 0
    body = BodySnapshot(session_key="s", turns=0, warmth=0.5, surprise=0.2)
    overdue = um.reply_overdue(body, now=um._last_user_ts + 90.0)
    assert overdue > 0.0, overdue
