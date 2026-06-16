"""Sylanne-Core: Affective computation engine SDK.

Text in, structured emotional state out.

Quick start::

    from sylanne_core import SylanneEngine, SylanneConfig

    engine = SylanneEngine(data_dir="./data", llm=my_llm_fn)
    await engine.start()
    surface = await engine.process("user_123", "你好")
    print(surface["decision"]["action"])  # "express", "listen", "hold", etc.
    await engine.shutdown()
"""

from __future__ import annotations

from ._sharing import SharedEngineConflictError
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
    "SharedEngineConflictError",
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
]
__version__ = "2.0.0"
