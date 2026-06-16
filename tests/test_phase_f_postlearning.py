"""Phase F 测试（Fable 重做版）：learn() 驱动 SDK 后学习(L1) + lexicon 统一观测。

红线③：agent 不重算漂移，只驱动 SDK 的 feedback_quality（DRIFT_SIGNALS 通道）。
SharedUnderstanding 已删（其输出在旧版无任何消费者）；统一观测改由 lexicon 提供，
本文件验证 lexicon 的观测语义（含"提问≠冷漠"修正）。
"""

from __future__ import annotations

import tempfile

from sylanne_alpha._engine.sylanne_core.compute.host import SylanneAlphaHost
from sylanne_alpha.v2core.body_port_v2 import CanonicalKernelBodyPort
from sylanne_alpha.v2core.lexicon import distill_features, read_signals


def _host():
    return SylanneAlphaHost(root=tempfile.mkdtemp(prefix="sylf_"), session_key="u")


def test_learn_drives_sdk_feedback_no_crash() -> None:
    """learn() 真实 host 上不崩（canonical 迁移后 learn 是真实反应反馈占位，本期 no-op）。"""
    bp = CanonicalKernelBodyPort.from_host(_host(), "u")
    bp.tick({"phase": "request", "text": "你好"})
    bp.learn("", actual_expressed=True)
    bp.learn("", actual_expressed=False)


def test_quality_drifts_relational_gravity() -> None:
    """L1（canonical 迁移版）：高质量 dialogue_quality 经 event.values 注入真的让
    relational_gravity 漂移（SDK 在 process 内算，我们只经数值通道驱动）。
    断 relational_gravity 而非 expression_drive_trait：隔离 dialogue_quality 信道，排除
    expression_fired 混淆（红队 wjqkfgh4i major 修复）。now 步进 30s 过 _drift_min_interval。"""
    h = _host()
    bp = CanonicalKernelBodyPort.from_host(h, "u")
    bp.tick({"phase": "request", "text": "测试", "now": 1.0})
    comp = h.kernel.computation
    before = float(comp._embodiment_traits["relational_gravity"].value)
    for i in range(1, 7):
        bp.tick({"phase": "request", "text": "真不错", "now": 1.0 + 30.0 * i,
                 "values": {"dialogue_quality": 0.95}})
    after = float(comp._embodiment_traits["relational_gravity"].value)
    assert after > before, "高质量 dialogue_quality 没经 canonical 通道推 relational_gravity"


def test_lexicon_question_is_engagement_not_cold() -> None:
    """观测修正：问号计入投入（engagement），绝不计入冷漠（cold）。"""
    sig = read_signals("你今天吃饭了吗？？")
    assert sig.question is True
    assert sig.cold == 0.0
    assert sig.engagement_cue > min(1.0, sig.length / 40.0)  # 提问加成生效


def test_lexicon_basic_semantics() -> None:
    sig = read_signals("我好喜欢你呀❤️抱抱！")
    assert sig.warm > 0.0 and sig.valence_cue > 0.0
    sad = read_signals("好累，想哭😭")
    assert sad.distress > 0.0
    assert read_signals("").length == 0


def test_distill_features_dims_stable() -> None:
    """蒸馏特征 8 维、bias 恒 1、维序稳定（旧档权重兼容，铁律④）。"""
    feats = distill_features("我好喜欢你呀❤️")
    assert len(feats) == 8 and feats[0] == 1.0
    assert distill_features("") == [1.0] + [0.0] * 7
