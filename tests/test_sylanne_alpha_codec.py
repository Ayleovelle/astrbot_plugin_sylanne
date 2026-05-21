import unittest

from sylanne_alpha.codec import (
    CODEC_SCHEMA_VERSION,
    decode_delta_packet,
    decode_event_packet,
    decode_state_packet,
    encode_delta_packet,
    encode_event_packet,
    encode_state_packet,
)
from sylanne_alpha.body import AlphaBodyState


class SylanneAlphaCodecTests(unittest.TestCase):
    def test_event_packet_uses_fixed_binary_fields_and_roundtrips_hot_axes(self):
        body = AlphaBodyState()
        event = body.event_vector(text="你好", flags=["safe", "repair"], confidence=0.73, elapsed=7.0, repetition=3)

        packet = encode_event_packet(event)
        restored = decode_event_packet(packet)

        self.assertIsInstance(packet, bytes)
        self.assertEqual(packet[0], CODEC_SCHEMA_VERSION)
        self.assertLessEqual(len(packet), 8)
        self.assertEqual(restored["has_text"], 1.0)
        self.assertEqual(restored["safe"], 1.0)
        self.assertEqual(restored["repair"], 1.0)
        self.assertAlmostEqual(restored["confidence"], event["confidence"], delta=1 / 255)
        self.assertEqual(restored["elapsed"], 7.0)
        self.assertEqual(restored["repetition"], 3.0)

    def test_state_packet_is_compact_and_preserves_state_order(self):
        body = AlphaBodyState()
        body.apply(text="靠近", flags=["safe"], confidence=0.8, now=1.0)
        state = body.state_vector()

        packet = encode_state_packet(state)
        restored = decode_state_packet(packet)

        self.assertIsInstance(packet, bytes)
        self.assertEqual(packet[0], CODEC_SCHEMA_VERSION)
        self.assertLessEqual(len(packet), 40)
        self.assertEqual(set(restored), set(state))
        self.assertAlmostEqual(restored["bloodflow.warmth"], state["bloodflow.warmth"], delta=1 / 255)
        self.assertAlmostEqual(restored["pulse.rhythm"], state["pulse.rhythm"], delta=1 / 255)

    def test_delta_packet_sends_only_non_zero_axes_with_signed_quantization(self):
        delta = {
            "bloodflow.warmth": 0.04,
            "wound.open": -0.08,
            "needs.need_contact": 0.0,
        }

        packet = encode_delta_packet(delta)
        restored = decode_delta_packet(packet)

        self.assertEqual(packet[0], CODEC_SCHEMA_VERSION)
        self.assertEqual((len(packet) - 2) % 2, 0)
        self.assertLess(len(packet), 10)
        self.assertIn("bloodflow.warmth", restored)
        self.assertIn("wound.open", restored)
        self.assertNotIn("needs.need_contact", restored)
        self.assertAlmostEqual(restored["bloodflow.warmth"], 0.04, delta=0.001)
        self.assertAlmostEqual(restored["wound.open"], -0.08, delta=0.001)

    def test_codec_rejects_unknown_schema_without_io_or_recovery_side_effects(self):
        with self.assertRaises(ValueError):
            decode_event_packet(bytes([CODEC_SCHEMA_VERSION + 1, 0, 0, 0, 0, 0, 0]))
        with self.assertRaises(ValueError):
            decode_state_packet(bytes([CODEC_SCHEMA_VERSION + 1]))
        with self.assertRaises(ValueError):
            decode_delta_packet(bytes([CODEC_SCHEMA_VERSION + 1, 0]))


if __name__ == "__main__":
    unittest.main()
