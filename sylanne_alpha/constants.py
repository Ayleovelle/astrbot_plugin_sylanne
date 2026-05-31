"""Shared constants for the sylanne_alpha package.

Centralizes values that were previously duplicated across multiple modules.
"""

from __future__ import annotations

from datetime import timedelta, timezone

# 中国标准时间 (UTC+8)
CHINA_TZ = timezone(timedelta(hours=8))

# 序列化后的请求载荷最大字符数，超过则触发裁剪
MAX_PAYLOAD_SERIALIZED_CHARS = 60000

# 单次未完成回复注入的最大字符数，防止 prompt 过长
MAX_UNFINISHED_CONTEXT_CHARS = 2000
