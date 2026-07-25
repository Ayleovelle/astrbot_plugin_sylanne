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

import importlib.util
import inspect
import json
import logging
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


def test_dead_v1_migration_modules_are_absent() -> None:
    assert importlib.util.find_spec("sylanne_alpha.v2core.migration") is None
    assert importlib.util.find_spec("sylanne_alpha.v2core.session_store") is None


def test_v2core_package_does_not_export_deleted_scaffolding() -> None:
    import sylanne_alpha.v2core as v2core

    assert "migration" not in v2core.__all__
    assert "session_store" not in v2core.__all__


def test_engine_adapter_has_no_unused_facade() -> None:
    import sylanne_alpha.engine_adapter as adapter

    assert not hasattr(adapter, "EngineFacade")
    assert adapter.derive_should_send({"action": "reach_out"}, {"allowed": True})


def test_legacy_snapshot_import_api_is_absent() -> None:
    import sylanne_alpha
    from main import EmotionalStatePlugin

    assert importlib.util.find_spec(
        "sylanne_alpha._engine.sylanne_core.compute.importer"
    ) is None
    assert not hasattr(sylanne_alpha, "import_legacy_body")
    assert not hasattr(EmotionalStatePlugin, "import_sylanne_legacy")


def test_current_runtime_has_no_legacy_constructor_surface() -> None:
    from sylanne_alpha._engine.sylanne_core.compute.host import SylanneAlphaHost
    from sylanne_alpha._engine.sylanne_core.compute.kernel import AlphaKernel
    from sylanne_alpha._engine.sylanne_core.compute.runtime import AlphaRuntime

    assert "legacy" not in inspect.signature(AlphaKernel.boot).parameters
    assert "legacy" not in inspect.signature(AlphaRuntime.load).parameters
    assert "legacy" not in inspect.signature(SylanneAlphaHost).parameters


def test_runtime_restores_only_current_schema(tmp_path: Path) -> None:
    from sylanne_alpha._engine.sylanne_core.compute.body import SCHEMA_VERSION
    from sylanne_alpha._engine.sylanne_core.compute.kernel import AlphaKernel
    from sylanne_alpha._engine.sylanne_core.compute.runtime import AlphaRuntime

    runtime = AlphaRuntime(tmp_path)
    current = AlphaKernel.boot("s")
    current.turns = 7
    current.body.temperature.warmth = 0.73
    runtime.save(current)

    restored = runtime.load("s")
    assert restored.snapshot()["schema_version"] == SCHEMA_VERSION
    assert restored.turns == 7
    assert restored.body.temperature.warmth == 0.73


def test_runtime_ignores_schema_mismatch_without_migrating(
    tmp_path: Path, caplog
) -> None:
    from sylanne_alpha._engine.sylanne_core.compute.runtime import AlphaRuntime

    runtime = AlphaRuntime(tmp_path)
    path = runtime._path("s")
    path.parent.mkdir(parents=True, exist_ok=True)
    original = '{"schema_version":"sylanne.legacy.v1","emotion":{"turns":99}}'
    path.write_text(original, encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="sylanne_core"):
        kernel = runtime.load("s")

    assert kernel.turns == 0
    assert path.read_text(encoding="utf-8") == original
    assert "unsupported snapshot schema" in caplog.text.lower()


def test_runtime_quarantines_malformed_json(tmp_path: Path) -> None:
    from sylanne_alpha._engine.sylanne_core.compute.body import SCHEMA_VERSION
    from sylanne_alpha._engine.sylanne_core.compute.runtime import AlphaRuntime

    runtime = AlphaRuntime(tmp_path)
    path = runtime._path("s")
    path.parent.mkdir(parents=True, exist_ok=True)
    original = "{broken json"
    path.write_text(original, encoding="utf-8")

    kernel = runtime.load("s")
    damaged = path.with_suffix(path.suffix + ".damaged")
    assert kernel.turns == 0
    assert damaged.read_text(encoding="utf-8") == original
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == SCHEMA_VERSION


def test_resonance_is_the_only_computation_backend() -> None:
    from sylanne_alpha._engine.sylanne_core.compute.kernel import AlphaKernel
    from sylanne_alpha._engine.sylanne_core.compute.resonance_integration import (
        ResonanceSpine,
    )

    kernel = AlphaKernel.boot("s")
    source = inspect.getsource(
        importlib.import_module("sylanne_alpha._engine.sylanne_core.compute.kernel")
    )

    assert type(kernel.computation) is ResonanceSpine
    assert importlib.util.find_spec(
        "sylanne_alpha._engine.sylanne_core.compute.computation_spine"
    ) is None
    assert "ComputationSpine" not in source
    assert "except ImportError" not in source


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
    """自主生命基础设施保留：AutonomyScheduler 仍驱动显式自主周期。"""
    from sylanne_alpha.agents.autonomy_scheduler import AutonomyScheduler

    src = inspect.getsource(AutonomyScheduler)
    assert "run_autonomous_cycle" in src
    assert "run_cycle" not in src
    assert "v1_turn_cognition_retired" not in src
