"""v1 逐轮认知全面退役测试（2026-06-12 拍板：推翻重构，单脑运行）。

退役语义：
- sylanne_enable_v2core 默认【开】（缺省键=开）——v2core 是唯一认知内核。
- 启用即退役 v1 逐轮认知：旧 9-agent SelfCore 的 PRE/POST（请求管线）与
  RESPONSE_POST（回复管线）不再运行；AssessorAgent 逐轮 LLM 评估随之消失；
  assessment 唯一来源是 v2core 评价（不含 intent 键 → SDK intent=="撒娇"
  硬编码路径断粮）。
- 保留范围：自主生命基础设施（AutonomyScheduler 作息演化/深睡巩固/反思/
  进化档案）不属逐轮认知，照常运行。
- flag 显式置 false = 部署级紧急回退 v1（绞杀式安全口，非缝补）。
"""

from __future__ import annotations

import inspect

from sylanne_alpha.v2core.integration import v1_turn_cognition_retired, v2core_enabled


class _P:
    def __init__(self, cfg: dict | None = None) -> None:
        self._config = cfg if cfg is not None else {}


# ---- 默认语义 ----

def test_v2core_default_on() -> None:
    """缺省键 = 开（v2core 是唯一认知内核，不再是灰度旁路）。"""
    assert v2core_enabled(_P({})) is True
    assert v2core_enabled(_P(None)) is True


def test_explicit_false_is_emergency_rollback() -> None:
    assert v2core_enabled(_P({"sylanne_enable_v2core": False})) is False
    assert v1_turn_cognition_retired(_P({"sylanne_enable_v2core": False})) is False


def test_retirement_follows_v2core() -> None:
    assert v1_turn_cognition_retired(_P({})) is True
    assert v1_turn_cognition_retired(_P({"sylanne_enable_v2core": True})) is True


def test_schema_default_flipped() -> None:
    """部署 schema 的默认值同步为 true（真退役，不是只改代码缺省）。"""
    import json
    from pathlib import Path

    schema = json.loads(Path("_conf_schema.json").read_text(encoding="utf-8"))
    assert schema["sylanne_enable_v2core"]["default"] is True


# ---- 两条管线的退役闸真的存在且包住了 v1 调用点（源级证明，仿 repo 既有手法）----

def test_request_pipeline_gates_v1_pre_post() -> None:
    """请求管线：SelfCore PRE/POST 必须被 v1_turn_cognition_retired 闸住。"""
    from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline

    src = inspect.getsource(LLMRequestPipeline._background_observe_request)
    assert "v1_turn_cognition_retired" in src, "请求管线没有退役闸"
    # 闸必须真的决定 sc 是否为 None（PRE/POST 共用 sc 变量，sc=None 即两段全死）
    assert "None if _v1_retired" in src, "退役闸没有接到 SelfCore 调用点"
    # 退役闸必须出现在 run_cycle 之前（先判退役再谈编排）
    assert src.index("v1_turn_cognition_retired") < src.index("run_cycle")


def test_response_pipeline_gates_v1_response_post() -> None:
    """回复管线：SelfCore RESPONSE_POST 必须被退役闸闸住。"""
    from sylanne_alpha.llm_response_pipeline import LLMResponsePipeline

    src = inspect.getsource(LLMResponsePipeline._background_observe_response)
    assert "v1_turn_cognition_retired" in src, "回复管线没有退役闸"
    assert "None if _v1_retired" in src, "退役闸没有接到 RESPONSE_POST 调用点"


def test_v2_assessment_has_no_intent_key() -> None:
    """退役后唯一评价来源不含 intent 键——SDK intent=='撒娇' 硬编码路径断粮。"""
    from sylanne_alpha.v2core.capabilities.mentalize import AppraisalCapability
    from sylanne_alpha.v2core.contracts import BeatContext, BodySnapshot, Phase

    ctx = BeatContext(session_key="s", event=None,
                      body=BodySnapshot(session_key="s", turns=1, surprise=0.5),
                      text="人家想你了嘛~")
    ctx.phase = Phase.PERCEPT
    AppraisalCapability().perceive(ctx)
    a = ctx.scratch["assessment"]
    assert "intent" not in a
    assert set(a) <= {"valence", "arousal", "wound_risk"}


def test_autonomy_infrastructure_not_retired() -> None:
    """自主生命基础设施保留：AutonomyScheduler 仍然驱动 run_cycle(AUTONOMOUS)
    （作息/巩固/反思不属逐轮认知，退役范围之外）。"""
    from sylanne_alpha.agents.autonomy_scheduler import AutonomyScheduler

    src = inspect.getsource(AutonomyScheduler)
    assert "run_cycle" in src        # 自主演化仍在
    assert "v1_turn_cognition_retired" not in src   # 不被退役闸误伤
