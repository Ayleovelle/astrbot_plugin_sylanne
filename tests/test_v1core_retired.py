"""v1 逐轮认知全面退役测试（2026-06-12 拍板：推翻重构，单脑运行）。

退役语义：
- v2core 是无条件运行的唯一认知内核，不再暴露运行时关闭开关。
- v1 逐轮认知已退役并删除：旧 9-agent SelfCore 的 PRE/POST（请求管线）与
  RESPONSE_POST（回复管线）调用点已从源码移除；AssessorAgent 逐轮 LLM 评估随之消失；
  assessment 唯一来源是 v2core 评价（不含 intent 键 → SDK intent=="撒娇"
  硬编码路径断粮）。
- 保留范围：自主生命基础设施（AutonomyScheduler 作息演化/深睡巩固/反思/
  进化档案）不属逐轮认知，照常运行。
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

def test_v2core_switch_is_absent_from_schema() -> None:
    schema = json.loads(Path("_conf_schema.json").read_text(encoding="utf-8"))
    assert "sylanne_enable_v2core" not in schema


def test_v2core_integration_has_no_runtime_disable_helper() -> None:
    import sylanne_alpha.v2core.integration as integration

    assert not hasattr(integration, "v2core_enabled")
    assert "sylanne_enable_v2core" not in inspect.getsource(integration)


def test_v2_speak_continues_to_delivery_without_v1_fallback_language() -> None:
    import sylanne_alpha.v2core.integration as integration

    source = inspect.getsource(integration)
    assert "回退到 v1" not in source
    assert "legacy 的嘴" not in source
    assert "delivery continuation" in source


def test_main_routes_unsuppressed_reply_to_delivery_once() -> None:
    from main import EmotionalStatePlugin

    source = inspect.getsource(EmotionalStatePlugin._on_llm_response_inner)
    assert "suppress_delivery = await apply_v2core_response" in source
    assert "if not suppress_delivery:" in source
    assert source.count(
        "await self._llm_response_pipeline._on_llm_response_inner(event, response)"
    ) == 1


# ---- 两条管线的 v1 逐轮认知调用点已彻底删除（源级证明，仿 repo 既有手法）----

def test_request_pipeline_has_no_v1_run_cycle() -> None:
    """请求管线：SelfCore PRE/POST 的 run_cycle 调用点已删除（不留死闸）。"""
    from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline

    src = inspect.getsource(LLMRequestPipeline._background_observe_request)
    assert "v1_turn_cognition_retired" not in src
    assert "run_cycle" not in src


def test_response_pipeline_has_no_v1_run_cycle() -> None:
    """回复管线：SelfCore RESPONSE_POST 的 run_cycle 调用点已删除。"""
    from sylanne_alpha.llm_response_pipeline import LLMResponsePipeline

    src = inspect.getsource(LLMResponsePipeline._background_observe_response)
    assert "v1_turn_cognition_retired" not in src
    assert "run_cycle" not in src


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
