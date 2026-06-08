"""Sylanne-Core: Affective computation engine SDK.

Text in, structured emotional state out. Designed as an AstrBot plugin dependency.

Quick start (standalone)::

    from sylanne_core import SylanneEngine, SylanneConfig

    engine = SylanneEngine(data_dir="./data", llm=my_llm_fn)
    await engine.start()
    surface = await engine.process("user_123", "你好")
    print(surface["decision"]["action"])  # "express", "listen", "hold", etc.
    await engine.shutdown()

Quick start (AstrBot plugin)::

    from sylanne_core import get_engine
    engine = get_engine()  # pre-configured by SylannEngine plugin
    surface = await engine.process(session_id, text)
"""

from __future__ import annotations

from .algebra import blend, compose, decay, distance, drift, normalize, project, threshold
from .bridge import layer0_to_interchange, state_to_pad, surface_to_layer0
from .compute.hot_pool import HotPool, Influence, InfluenceType
from .compute.pad_interop import PADProjector, PADVector
from .config import DimensionProfile, SylanneConfig, build_profile
from .contagion import ContagionEvent, ContagionGraph, GroupDynamics, InfluenceFilter
from .engine import SylanneEngine
from .expression import (
    BlendShapeProfile,
    MotorCommand,
    PADToBlendShape,
    PADToMotor,
    PADToProsody,
    PADToTextStyle,
    ProsodyParams,
    TextStyle,
)
from .schema import SYLANNE_SCHEMA
from .schema import validate as validate_schema
from .standard import EmotionVector, SylanneCore, SylanneState, SylanneStimulus
from .types import EngineStatus, HealthStatus, PADOutput, Surface

__all__ = [
    # Engine & config
    "SylanneEngine",
    "SylanneConfig",
    "SylanneCore",
    "SylanneStimulus",
    "SylanneState",
    "EmotionVector",
    "DimensionProfile",
    "build_profile",
    # Hot pool
    "HotPool",
    "Influence",
    "InfluenceType",
    # PAD interop
    "PADVector",
    "PADProjector",
    "PADOutput",
    # Schema
    "SYLANNE_SCHEMA",
    "validate_schema",
    # Types
    "Surface",
    "EngineStatus",
    "HealthStatus",
    # Bridge
    "state_to_pad",
    "surface_to_layer0",
    "layer0_to_interchange",
    # Algebra
    "blend",
    "decay",
    "project",
    "threshold",
    "normalize",
    "distance",
    "drift",
    "compose",
    # Contagion
    "ContagionGraph",
    "ContagionEvent",
    "GroupDynamics",
    "InfluenceFilter",
    # Expression
    "PADToBlendShape",
    "PADToMotor",
    "PADToTextStyle",
    "PADToProsody",
    "BlendShapeProfile",
    "MotorCommand",
    "TextStyle",
    "ProsodyParams",
    # Shared engine
    "get_engine",
]
__version__ = "2.0.0"

_shared_engine: SylanneEngine | None = None


def get_engine() -> SylanneEngine:
    """获取插件版共享引擎实例。

    插件版由 SylannEngine 前置插件创建并配置 LLM，
    下游插件直接调用此函数获取即可，无需自行配置。
    SDK 版用户请自行实例化 SylanneEngine。
    """
    if _shared_engine is None:
        raise RuntimeError(
            "SylannEngine 尚未初始化。请确认前置插件已安装并正常启动。\n"
            "AstrBot WebUI → 插件 → 从 Git 仓库安装 → "
            "https://github.com/Ayleovelle/SylannEngine.git"
        )
    return _shared_engine
