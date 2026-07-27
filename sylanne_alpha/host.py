"""会话宿主模块（CP3：已切换为 SDK 共振场计算芯）。

本模块原先自带 SylanneAlphaHost + AlphaKernel。
深接入后，计算实现统一为 vendored SylannEngine 的 ResonanceSpine。
本文件现为转发层：

- SylanneAlphaHostEvent: 直接复用 SDK 的事件类（业务层造的 event 才能被 SDK host
  的 _event() 通过 isinstance 识别，否则掉进 dict 分支报错）。
- SylanneAlphaHost: 包装 SDK 的 SylanneAlphaHost，默认注入 lite 档纯 python
  DimensionProfile（现有调用 SylanneAlphaHost(root=, session_key=) 不传 profile，
  这里补默认），使每个会话的 kernel.computation 为 ResonanceSpine。

接口（on_request/on_response/on_chat/on_proactive_check/diagnostics/snapshot）
与 SDK host 完全一致——二者本就同源同构。

最彻底终态：业务层全部经 EngineFacade 读 Surface 后，本转发层连同旧计算模块一并删除。
"""

from __future__ import annotations

from typing import Any

from sylanne_alpha._engine.sylanne_core.compute.host import (
    SylanneAlphaHost as _SDKHost,
)
from sylanne_alpha._engine.sylanne_core.compute.host import (
    SylanneAlphaHostEvent as SylanneAlphaHostEvent,  # 重导出供业务层使用
)
from sylanne_alpha._engine.sylanne_core.config import DimensionProfile, build_profile

# lite 档纯 python DimensionProfile，模块级缓存（无状态，可共享）
_LITE_PROFILE: DimensionProfile | None = None


def _lite_profile() -> DimensionProfile:
    global _LITE_PROFILE
    if _LITE_PROFILE is None:
        _LITE_PROFILE = build_profile("lite", force_backend="python")
    return _LITE_PROFILE


class SylanneAlphaHost(_SDKHost):
    """SDK 共振场宿主的薄子类：profile 缺省时注入 lite 档纯 python。

    继承 SDK 的 SylanneAlphaHost（kernel.computation=ResonanceSpine），保持其
    全部接口与 isinstance/类型注解可用性。现有调用 SylanneAlphaHost(root=,
    session_key=) 不传 profile，这里在 __post_init__ 前补默认 lite profile。

    注：父类是 @dataclass(slots=True)，本子类不新增字段，故 slots 兼容。
    """

    def __post_init__(self) -> None:
        if self.profile is None:
            self.profile = _lite_profile()
        super().__post_init__()


__all__ = ["SylanneAlphaHost", "SylanneAlphaHostEvent"]
