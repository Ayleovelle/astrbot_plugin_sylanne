"""序列化/反序列化编解码器模块。

提供 Sylanne 身体状态向量的紧凑二进制编码方案，用于高效存储和传输：
- 事件包 (event packet): 7 字节，编码一次交互事件的标志位/置信度/时间/重复次数
- 状态包 (state packet): 30 字节 (1+29)，将 29 维状态向量量化为 uint8
- 增量包 (delta packet): 变长，仅编码非零的状态变化轴

编码策略：
- 浮点值 [0,1] → uint8 [0,255]，精度约 0.004
- 增量值 [-0.08, 0.08] → int8 [-127, 127]，精度约 0.0006
- 事件标志位打包为 16-bit 位域
"""

from __future__ import annotations

from collections.abc import Mapping

from .vector import EVENT_AXES, STATE_AXES
from .vector import clamp as _clamp

# 二进制包的 schema 版本号，用于前向兼容检查
CODEC_SCHEMA_VERSION = 1

# 事件标志位→位偏移映射，用于将布尔标志打包进 16-bit 位域
EVENT_FLAG_BITS = {
    "has_text": 0,
    "idle": 1,
    "safe": 2,
    "hurt": 3,
    "boundary": 4,
    "repair": 5,
}

# 增量值的最大绝对值限制，超出此范围的增量会被截断
DELTA_LIMIT = 0.08


def _u8(value: float) -> int:
    """将 [0,1] 浮点值量化为 uint8 [0,255]。"""
    return int(round(_clamp(value) * 255))


def _from_u8(value: int) -> float:
    """将 uint8 [0,255] 反量化为 [0,1] 浮点值。"""
    return float(value) / 255.0


def _require_schema(packet: bytes, minimum_length: int) -> None:
    """校验二进制包的 schema 版本和最小长度。"""
    if len(packet) < minimum_length:
        raise ValueError("Binary packet is truncated.")
    if packet[0] != CODEC_SCHEMA_VERSION:
        raise ValueError(f"Unsupported binary packet schema: {packet[0]}")


def encode_event_packet(event: Mapping[str, float]) -> bytes:
    """将事件向量编码为 7 字节二进制包。

    包结构: [schema(1)] [flags_lo(1)] [flags_hi(1)] [confidence(1)] [elapsed_lo(1)] [elapsed_hi(1)] [repetition(1)]

    Args:
        event: 事件向量字典

    Returns:
        7 字节的 bytes 对象
    """
    flags = 0
    for axis, bit in EVENT_FLAG_BITS.items():
        if float(event.get(axis, 0.0)) > 0.0:
            flags |= 1 << bit
    elapsed = max(0, min(65535, int(round(float(event.get("elapsed", 0.0))))))
    repetition = max(0, min(255, int(round(float(event.get("repetition", 0.0))))))
    return bytes(
        (
            CODEC_SCHEMA_VERSION,
            flags & 0xFF,
            (flags >> 8) & 0xFF,
            _u8(float(event.get("confidence", 0.0))),
            elapsed & 0xFF,
            (elapsed >> 8) & 0xFF,
            repetition,
        )
    )


def decode_event_packet(packet: bytes) -> dict[str, float]:
    _require_schema(packet, 7)
    flags = packet[1] | (packet[2] << 8)
    elapsed = packet[4] | (packet[5] << 8)
    event = {axis: 0.0 for axis in EVENT_AXES}
    for axis, bit in EVENT_FLAG_BITS.items():
        event[axis] = 1.0 if flags & (1 << bit) else 0.0
    event["confidence"] = _from_u8(packet[3])
    event["elapsed"] = float(elapsed)
    event["repetition"] = float(packet[6])
    return event


def encode_state_packet(state: Mapping[str, float]) -> bytes:
    return bytes(
        [
            CODEC_SCHEMA_VERSION,
            *(_u8(float(state.get(axis, 0.0))) for axis in STATE_AXES),
        ]
    )


def decode_state_packet(packet: bytes) -> dict[str, float]:
    _require_schema(packet, 1 + len(STATE_AXES))
    return {axis: _from_u8(packet[index + 1]) for index, axis in enumerate(STATE_AXES)}


def encode_delta_packet(delta: Mapping[str, float]) -> bytes:
    pairs: list[int] = []
    for axis_index, axis in enumerate(STATE_AXES):
        value = max(-DELTA_LIMIT, min(DELTA_LIMIT, float(delta.get(axis, 0.0))))
        if value == 0.0:
            continue
        quantized = int(round(value / DELTA_LIMIT * 127))
        if quantized == 0:
            continue
        pairs.extend((axis_index, quantized & 0xFF))
    if len(pairs) // 2 > 255:
        raise ValueError("Delta packet contains too many axes.")
    return bytes([CODEC_SCHEMA_VERSION, len(pairs) // 2, *pairs])


def decode_delta_packet(packet: bytes) -> dict[str, float]:
    _require_schema(packet, 2)
    count = packet[1]
    expected_length = 2 + count * 2
    if len(packet) < expected_length:
        raise ValueError("Binary delta packet is truncated.")
    delta: dict[str, float] = {}
    for offset in range(2, expected_length, 2):
        axis_index = packet[offset]
        if axis_index >= len(STATE_AXES):
            raise ValueError(f"Unknown delta axis index: {axis_index}")
        raw = packet[offset + 1]
        signed = raw - 256 if raw >= 128 else raw
        delta[STATE_AXES[axis_index]] = signed / 127.0 * DELTA_LIMIT
    return delta
