"""配置辅助模块。

提供类型安全的配置读取工具函数（bool_setting / int_setting）以及
alpha_switches 聚合函数，将分散的配置项整合为结构化的功能开关字典，
供运行时各子系统查询当前启用状态。
"""

from __future__ import annotations

from typing import Any

CONFIG_SCHEMA_VERSION = "sylanne.alpha.config.v1"


def bool_setting(config: dict[str, Any], name: str, default: bool = False) -> bool:
    """从配置字典中读取布尔值，兼容字符串形式（"true"/"1"/"yes" 等）。

    Args:
        config: 配置字典。
        name: 配置键名。
        default: 键不存在时的默认值。

    Returns:
        解析后的布尔值。
    """
    value = config.get(name, default)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
    return bool(value)


def int_setting(
    config: dict[str, Any],
    name: str,
    default: int,
    *,
    minimum: int = 0,
    maximum: int = 32,
) -> int:
    """从配置字典中读取整数值，并钳位到 [minimum, maximum] 范围。

    Args:
        config: 配置字典。
        name: 配置键名。
        default: 键不存在或解析失败时的默认值。
        minimum: 允许的最小值。
        maximum: 允许的最大值。

    Returns:
        钳位后的整数值。
    """
    try:
        value = int(config.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def alpha_switches(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """将分散的配置项聚合为结构化的功能开关字典。

    返回值按子系统分组（realtime_chat / proactive_dispatch / embedding_memory /
    assessor_llm / fast_assessor / background_workers / safety），每组包含
    该子系统的启用状态和关键参数。

    Args:
        config: 原始配置字典，None 时使用空字典。

    Returns:
        结构化的功能开关字典，包含 schema_version 字段。
    """
    config = dict(config or {})
    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "realtime_chat": {
            "enabled": bool_setting(config, "sylanne_alpha_realtime_chat_enabled"),
            "intercept_llm_response": bool_setting(
                config, "sylanne_alpha_realtime_intercept_llm_response"
            ),
        },
        "proactive_dispatch": {
            "enabled": bool_setting(config, "sylanne_alpha_proactive_dispatch_enabled"),
            "scheduler_enabled": bool_setting(
                config, "sylanne_alpha_proactive_scheduler_enabled"
            ),
        },
        "embedding_memory": {
            "enabled": bool_setting(config, "sylanne_alpha_embedding_memory_enabled"),
            "provider_id": str(
                config.get("sylanne_alpha_embedding_memory_provider_id") or ""
            ),
            "top_k": int_setting(
                config, "sylanne_alpha_embedding_memory_top_k", 5, minimum=1, maximum=20
            ),
        },
        "assessor_llm": {
            "enabled": bool_setting(config, "sylanne_alpha_assessor_llm_enabled"),
            "provider_id": str(config.get("sylanne_alpha_assessor_provider_id") or ""),
        },
        "fast_assessor": {
            "enabled": bool_setting(
                config, "sylanne_alpha_fast_assessor_enabled", True
            ),
            "provider_id": str(
                config.get("sylanne_alpha_fast_assessor_provider_id") or ""
            ),
        },
        "background_workers": {
            "enabled": bool_setting(config, "sylanne_alpha_background_workers_enabled"),
            "max_workers": int_setting(
                config, "sylanne_alpha_background_max_workers", 1, minimum=1, maximum=8
            ),
            "checkpoint_enabled": bool_setting(
                config, "sylanne_alpha_background_checkpoint_enabled", True
            ),
        },
        # 安全策略：关系推断和原始对话数据默认禁止对外导出
        "safety": {
            "relational_public_export": "blocked",
            "raw_dialogue_export": "blocked",
        },
    }


# ---------------------------------------------------------------------------
# Item 90: 轻量级边缘运行模式
# ---------------------------------------------------------------------------


class EdgeModeConfig:
    """边缘运行模式：低资源设备适配。"""

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        # 边缘模式下的参数
        self.hdc_dimension = 1024  # 降维
        self.enabled_layers = {"perception", "void_scar", "expression"}  # 只保留 3 层核心
        self.memory_max_items = 200  # 记忆上限降低
        self.disable_webui = False  # 可选关闭 WebUI
        self.disable_proactive = True  # 关闭主动发言

    def apply_to_spine(self, spine: Any) -> None:
        """将边缘模式配置应用到计算栈。"""
        if not self.enabled:
            return
        all_layers = {"perception", "gate", "void_scar", "sheaf", "hgt", "boundary", "expression"}
        for layer in all_layers:
            spine.set_layer_enabled(layer, layer in self.enabled_layers)

    @classmethod
    def from_config(cls, plugin: Any) -> "EdgeModeConfig":
        enabled = getattr(plugin, "_cfg_bool", lambda k, d: d)(
            "sylanne_alpha_edge_mode", False
        )
        return cls(enabled=enabled)


__all__ = [
    "CONFIG_SCHEMA_VERSION",
    "EdgeModeConfig",
    "alpha_switches",
    "bool_setting",
    "int_setting",
]
