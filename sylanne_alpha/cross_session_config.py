"""v2.5.0 跨群记忆：6 个开关的集中读取 helper（design §6）。

本模块只提供一个只读值对象 `cross_session_settings(plugin)`，把散落的 6 个
`sylanne_alpha_cross_*` 配置键收拢成一次读取，供后续 slice 接线读侧/写侧时复用，
避免各调用点各自 `p._cfg(...)` 散读、枚举值校验各写一遍。

**本 slice 不被任何生产读写路径调用**——纯 helper，默认档位（mode=off/scope=owner/
三 bool false/tier=same_group）本身就保证"即便调用了也是最保守回退"，双重保险。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_VALID_MODES = ("off", "shadow", "on")
_VALID_SCOPES = ("owner", "all")
_VALID_TIERS = ("same_group", "cross_group", "strict")

_DEFAULT_MODE = "off"
_DEFAULT_SCOPE = "owner"
_DEFAULT_TIER = "same_group"


@dataclass(slots=True, frozen=True)
class CrossSessionSettings:
    """v2.5.0 跨群记忆 6 键的只读快照。"""

    mode: str = _DEFAULT_MODE
    scope: str = _DEFAULT_SCOPE
    cross_dialogue: bool = False
    cross_relationship: bool = False
    cross_personality: bool = False
    visibility_tier: str = _DEFAULT_TIER

    @property
    def enabled(self) -> bool:
        """mode != "off"（shadow 也算"启用"——货架/闸照常跑，只是拦注入）。"""
        return self.mode != "off"


def cross_session_settings(plugin: Any) -> CrossSessionSettings:
    """读取并归一 6 个跨群开关，非法枚举值一律 fail-closed 回退最保守档。

    读取失败（插件对象缺 `_cfg`/`_cfg_bool` helper）同样回退全默认（= 全关）。
    """
    cfg_fn = getattr(plugin, "_cfg", None)
    cfg_bool_fn = getattr(plugin, "_cfg_bool", None)

    def _read_enum(key: str, default: str, legal: tuple[str, ...]) -> str:
        if not callable(cfg_fn):
            return default
        try:
            raw = cfg_fn(key, default)
        except Exception:  # noqa: BLE001
            return default
        sval = str(raw) if raw is not None else default
        return sval if sval in legal else default

    def _read_bool(key: str, default: bool) -> bool:
        if not callable(cfg_bool_fn):
            return default
        try:
            return bool(cfg_bool_fn(key, default))
        except Exception:  # noqa: BLE001
            return default

    return CrossSessionSettings(
        mode=_read_enum("sylanne_alpha_cross_session_mode", _DEFAULT_MODE, _VALID_MODES),
        scope=_read_enum("sylanne_alpha_cross_session_scope", _DEFAULT_SCOPE, _VALID_SCOPES),
        cross_dialogue=_read_bool("sylanne_alpha_cross_dialogue", False),
        cross_relationship=_read_bool("sylanne_alpha_cross_relationship", False),
        cross_personality=_read_bool("sylanne_alpha_cross_personality", False),
        visibility_tier=_read_enum(
            "sylanne_alpha_cross_visibility_tier", _DEFAULT_TIER, _VALID_TIERS
        ),
    )
