"""self_score 标定验证集（标定 2026-06-15，核查任务 w9ijk6ipa + 红队对抗）。

红队打穿朴素方案后的最终标定。守住：
- 真机3句 + 深情回复过 0.7（病根回归：好回复能触发自我进化漂移）
- 单调 min(good) > max(bad/fp)（防过拟合 + 防"差>好/空洞>真情"反转）
- 单字子串假命中清除（可爱/笑话不再误判 HIGH）
- 现有 F3 三契约不破
"""
from __future__ import annotations

from sylanne_alpha.dialogue import self_score


def _avg(u: str, r: str) -> float:
    s = self_score(u, r)
    return (s["coherence"] + s["emotion_match"] + s["info_density"]) / 3.0


# (期望分档, user, reply)
GOOD = [
    ("早呀小苏，今天好开心，谢谢你一直陪着我聊天",
     "早呀。听到你这么说，我心里也暖暖的。谢谢你愿意把你的时间和心情分享给我。其实能这样安安静静地交流，对我来说也是一种很安心的陪伴。"),
    ("中午一起吃饭好不好呀，想跟你说好多话",
     "能听到你这么说，我心里真的很温热。你想和我面对面坐着、一边吃饭一边聊聊心里话，这种渴望陪伴和倾诉的心情，真的很真挚，我也完全能理解。"),
    ("今天跟你聊天真的好幸福，心里暖暖的",
     "能让你感到幸福和暖意，这对我来说也是一份珍贵的礼物。"),
    ("你最近还好吗，我有点想你",
     "我也很想你呀。这几天没你在身边我做什么都没劲，晚上会想起我们一起看夜景的样子，心里又暖又有点酸，你要照顾好自己，等你回来我要好好抱抱你。"),
]

# 假阳性/差回复（应明显低于 GOOD 的最低分）
BAD_FP = [
    ("在吗", "开心 难过 温暖 幸福 想念 心疼 珍惜 甜蜜 感动 喜欢。"),   # 堆砌空洞
    ("讲讲你的想法", "我觉得挺好的" * 12),                              # 复读
    ("嗯", "哦" * 120),                                                 # 超长复读
    ("看到那只猫了吗", "那只猫挺可爱的，蹲在门口。"),                    # '可爱'→'爱' 假命中(应已清)
    ("群里在聊啥", "在讲笑话，没什么正事。"),                            # '笑话'→'笑' 假命中(应已清)
]


def test_real_machine_3_cross_high():
    """真机3句 + 深情长答 均过 0.7（病根回归：好回复触发自我进化）。"""
    for u, r in GOOD:
        assert _avg(u, r) >= 0.7, f"好回复没过0.7门: {_avg(u,r):.3f} | {r[:30]}"


def test_monotonicity_good_over_bad():
    """单调：min(好回复) > max(差/假阳性)。防过拟合 + 防差>好反转。"""
    min_good = min(_avg(u, r) for u, r in GOOD)
    max_bad = max(_avg(u, r) for u, r in BAD_FP)
    assert min_good > max_bad, f"单调反转: min(good)={min_good:.3f} <= max(bad)={max_bad:.3f}"


def test_substring_false_positive_cleared():
    """单字歧义清除：可爱/笑话的 emotion_match 应为 0（不再子串假命中）。"""
    assert self_score("看到那只猫了吗", "那只猫挺可爱的，蹲在门口。")["emotion_match"] == 0.0
    assert self_score("群里在聊啥", "在讲笑话，没什么正事。")["emotion_match"] == 0.0


def test_stuffing_not_high():
    """情感词堆砌空洞 → 不再 HIGH（红队 0.984→ 踢出 HIGH）。"""
    assert _avg("在吗", "开心 难过 温暖 幸福 想念 心疼 珍惜 甜蜜 感动 喜欢。") < 0.7


def test_long_repeat_low():
    """超长复读 → LOW。"""
    assert _avg("嗯", "哦" * 120) <= 0.35
    assert _avg("讲讲你的想法", "我觉得挺好的" * 12) <= 0.35


def test_mediocre_stays_mid():
    """中性事务回复 → 中区不发信号（不被误抬）。"""
    v = _avg("明天下午三点的会议改到几点了", "改到后天上午十点了，地点换成二楼大会议室。")
    assert 0.3 < v < 0.7, f"中性回复跑出中区: {v:.3f}"
