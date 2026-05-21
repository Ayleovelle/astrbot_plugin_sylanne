from __future__ import annotations

from collections.abc import Mapping

from .vector import EVENT_AXES, STATE_AXES, clamp as _clamp


CODEC_SCHEMA_VERSION = 1
EVENT_FLAG_BITS = {
    "has_text": 0,
    "idle": 1,
    "safe": 2,
    "hurt": 3,
    "boundary": 4,
    "repair": 5,
}
DELTA_LIMIT = 0.08


def _u8(value: float) -> int:
    return int(round(_clamp(value) * 255))


def _from_u8(value: int) -> float:
    return float(value) / 255.0


def _require_schema(packet: bytes, minimum_length: int) -> None:
    if len(packet) < minimum_length:
        raise ValueError("Binary packet is truncated.")
    if packet[0] != CODEC_SCHEMA_VERSION:
        raise ValueError(f"Unsupported binary packet schema: {packet[0]}")


def encode_event_packet(event: Mapping[str, float]) -> bytes:
    flags = 0
    for axis, bit in EVENT_FLAG_BITS.items():
        if float(event.get(axis, 0.0)) > 0.0:
            flags |= 1 << bit
    elapsed = max(0, min(65535, int(round(float(event.get("elapsed", 0.0))))))
    repetition = max(0, min(255, int(round(float(event.get("repetition", 0.0))))))
    return bytes((
        CODEC_SCHEMA_VERSION,
        flags & 0xff,
        (flags >> 8) & 0xff,
        _u8(float(event.get("confidence", 0.0))),
        elapsed & 0xff,
        (elapsed >> 8) & 0xff,
        repetition,
    ))


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
    return bytes([CODEC_SCHEMA_VERSION, *(_u8(float(state.get(axis, 0.0))) for axis in STATE_AXES)])


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
        pairs.extend((axis_index, quantized & 0xff))
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
