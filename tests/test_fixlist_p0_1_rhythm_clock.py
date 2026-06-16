"""Phase G fixlist P0-1 测试：scratch['now'] 写者复活节律/超期（REVIEW-v2core-art-grade-fixlist §P0-1）。

病：scratch['now'] 零写者 → UserModel._rhythm_ema 永不更新 / reply_overdue() 恒 0 → 架构 §5.3
"她按你的节律感觉这次沉默超期"整条死。修：TurnRunner 构 ctx 后落 scratch['now']=宿主事件时间戳。
验收走实弹路径（TurnRunner.run_turn），不是部件隔离。
"""

from __future__ import annotations

import asyncio

from sylanne_alpha.v2core.contracts import BodySnapshot
from sylanne_alpha.v2core.domains.user_model import UserModelDomain
from sylanne_alpha.v2core.renderer import DefaultRenderer
from sylanne_alpha.v2core.self_core import SelfCore
from sylanne_alpha.v2core.turn_runner import TurnRunner


class _FakeBP:
    """最小 BodyPort：observe 返回固定 body，tick/learn no-op。"""

    def observe(self) -> BodySnapshot:
        return BodySnapshot(session_key="s", turns=0, warmth=0.5, surprise=0.2)

    def tick(self, event, assessment=None) -> BodySnapshot:  # noqa: ANN001
        return self.observe()

    def snapshot(self) -> dict:
        return {}

    def learn(self, *a, **k) -> None:  # noqa: ANN002, ANN003
        pass


def _runner_with_usermodel() -> tuple[TurnRunner, UserModelDomain]:
    sc = SelfCore(_FakeBP())
    return TurnRunner(sc, DefaultRenderer()), UserModelDomain()


def test_scratch_now_is_set_on_live_path() -> None:
    """实弹路径：run_turn 后 ctx.scratch['now'] 必有值（取自宿主事件时间戳）。"""
    runner, um = _runner_with_usermodel()
    event = {"now": 1000.0, "phase": "response", "flags": ["response"]}
    _reply, ctx = asyncio.run(
        runner.run_turn("s", event, "你好", domains={"usermodel": um}, draft="嗨~")
    )
    assert ctx.scratch.get("now") == 1000.0


def test_rhythm_ema_revives_across_turns() -> None:
    """多轮 mock 时钟喂 → _rhythm_ema 不再恒 None（节律学习复活）。"""
    runner, um = _runner_with_usermodel()
    t = 1000.0
    for _ in range(5):
        event = {"now": t, "phase": "response", "flags": ["response"]}
        asyncio.run(runner.run_turn("s", event, "在吗", domains={"usermodel": um}, draft="在的~"))
        t += 30.0  # 每轮间隔 30s
    assert um._rhythm_ema is not None       # 节律 EMA 真的学到了
    assert um._last_user_ts == 1000.0 + 4 * 30.0


def test_reply_overdue_positive_when_silent_past_rhythm() -> None:
    """学到节律后，沉默超过节律 → reply_overdue() > 0（超期感复活）。"""
    runner, um = _runner_with_usermodel()
    t = 1000.0
    for _ in range(5):
        event = {"now": t, "phase": "response", "flags": ["response"]}
        asyncio.run(runner.run_turn("s", event, "在吗", domains={"usermodel": um}, draft="在的~"))
        t += 20.0
    body = BodySnapshot(session_key="s", turns=5)
    # 距上次发言已过远超 20s 节律
    overdue = um.reply_overdue(body, um._last_user_ts + 200.0)
    assert overdue > 0.0


def test_now_falls_back_to_wallclock_without_event_ts() -> None:
    """宿主事件无时间戳 → 回落 wall clock（不为 0，节律仍能起步）。"""
    runner, um = _runner_with_usermodel()
    _reply, ctx = asyncio.run(
        runner.run_turn("s", {"phase": "response"}, "嗨", domains={"usermodel": um}, draft="嗨~")
    )
    assert ctx.scratch.get("now", 0.0) > 0.0
