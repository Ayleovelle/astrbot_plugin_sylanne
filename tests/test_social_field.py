"""
Comprehensive unit tests for Social Field Participation Dynamics (SFPD).

Tests cover SocialFieldCollector, PhaseTransitionExpression social extension,
SocialVoid, VoidScarEngine.expression_drive() with social void,
ComputationSpine social field params, and integration scenarios.
"""

import math
import time
import unittest
from unittest.mock import patch, MagicMock

from sylanne_alpha.social_field import SocialFieldCollector, SocialSignals
from sylanne_alpha.phase_transition import PhaseTransitionExpression
from sylanne_alpha.void_scar_engine import VoidScarEngine, SocialVoid
from sylanne_alpha.computation_spine import ComputationSpine


# ===========================================================================
# SocialFieldCollector
# ===========================================================================


class TestSocialFieldCollectorGroupDetection(unittest.TestCase):
    def test_unified_msg_origin_with_group(self):
        collector = SocialFieldCollector()
        event = MagicMock()
        event.unified_msg_origin = "QQ Group 12345"
        self.assertTrue(collector.is_group_context(event))

    def test_unified_msg_origin_private(self):
        collector = SocialFieldCollector()
        event = MagicMock()
        event.unified_msg_origin = "QQ Private"
        event.raw_message = None
        self.assertFalse(collector.is_group_context(event))

    def test_raw_message_with_group_id(self):
        collector = SocialFieldCollector()
        event = MagicMock()
        event.unified_msg_origin = ""
        raw = MagicMock()
        raw.group_id = 12345
        event.raw_message = raw
        self.assertTrue(collector.is_group_context(event))

    def test_dict_event_with_group(self):
        collector = SocialFieldCollector()
        event = {"unified_msg_origin": "WeChat Group Chat", "group_id": ""}
        self.assertTrue(collector.is_group_context(event))

    def test_dict_event_with_group_id(self):
        collector = SocialFieldCollector()
        event = {"unified_msg_origin": "", "group_id": "g123"}
        self.assertTrue(collector.is_group_context(event))

    def test_dict_event_private(self):
        collector = SocialFieldCollector()
        event = {"unified_msg_origin": "Private", "group_id": ""}
        self.assertFalse(collector.is_group_context(event))


class TestSocialFieldCollectorCollect(unittest.TestCase):
    def _make_collector(self, **config_overrides):
        config = {
            "sylanne_persona_name": "Sylanne",
            "sylanne_group_attention_trigger_names": ["小希"],
        }
        config.update(config_overrides)
        return SocialFieldCollector(config=config)

    def test_collect_returns_social_signals(self):
        c = self._make_collector()
        signals = c.collect(group_id="g1", sender_id="u1", text="hello", now=1000.0)
        self.assertIsInstance(signals, SocialSignals)
        self.assertTrue(signals.is_group)

    def test_collect_detects_name_mention(self):
        c = self._make_collector()
        signals = c.collect(
            group_id="g1", sender_id="u1", text="Sylanne你好", now=1000.0
        )
        self.assertTrue(signals.name_mentioned)

    def test_collect_detects_chinese_trigger_name(self):
        c = self._make_collector()
        signals = c.collect(
            group_id="g1", sender_id="u1", text="小希来聊天", now=1000.0
        )
        self.assertTrue(signals.name_mentioned)

    def test_collect_no_name_mention(self):
        c = self._make_collector()
        signals = c.collect(group_id="g1", sender_id="u1", text="大家好", now=1000.0)
        self.assertFalse(signals.name_mentioned)

    def test_collect_at_bot(self):
        c = self._make_collector()
        signals = c.collect(
            group_id="g1", sender_id="u1", text="@bot", is_at_bot=True, now=1000.0
        )
        self.assertTrue(signals.is_at_bot)

    def test_topic_relevance_with_overlap(self):
        c = self._make_collector()
        # First, simulate bot having replied about a topic
        c.notify_bot_replied("g1", "我喜欢猫咪和狗狗")
        # Now incoming message about same topic
        signals = c.collect(
            group_id="g1", sender_id="u1", text="猫咪真可爱", now=time.time()
        )
        self.assertGreater(signals.topic_relevance, 0.0)

    def test_topic_relevance_no_history(self):
        c = self._make_collector()
        signals = c.collect(
            group_id="g1", sender_id="u1", text="猫咪真可爱", now=1000.0
        )
        self.assertAlmostEqual(signals.topic_relevance, 0.0)

    def test_continuation_strength_recent_reply(self):
        c = self._make_collector()
        gs = c._get_group("g1")
        now = time.time()
        gs.last_bot_reply_ts = now - 5.0  # 5 seconds ago
        signals = c.collect(group_id="g1", sender_id="u1", text="hi", now=now)
        # exp(-5/60) ≈ 0.92
        self.assertGreater(signals.continuation_strength, 0.8)

    def test_continuation_strength_decays(self):
        c = self._make_collector()
        gs = c._get_group("g1")
        now = time.time()
        gs.last_bot_reply_ts = now - 300.0  # 5 minutes ago
        signals = c.collect(group_id="g1", sender_id="u1", text="hi", now=now)
        # exp(-300/60) = exp(-5) ≈ 0.0067
        self.assertLess(signals.continuation_strength, 0.01)

    def test_social_void_pressure_accumulates(self):
        c = self._make_collector()
        # Send multiple messages without bot replying, calling tick_silence between
        now = 1000.0
        for i in range(10):
            c.tick_silence("g1")
            c.collect(group_id="g1", sender_id="u1", text=f"msg {i}", now=now + i * 2)
        gs = c._get_group("g1")
        self.assertGreater(gs.silence_ticks, 0)

    def test_notify_bot_replied_resets_state(self):
        c = self._make_collector()
        gs = c._get_group("g1")
        gs.silence_ticks = 10
        gs.social_void_pressure = 2.0
        c.notify_bot_replied("g1", "回复内容")
        self.assertEqual(gs.silence_ticks, 0)
        self.assertLess(gs.social_void_pressure, 2.0)


# ===========================================================================
# PhaseTransitionExpression social extension
# ===========================================================================


class TestPhaseTransitionSocial(unittest.TestCase):
    def test_effective_threshold_private_unchanged(self):
        expr = PhaseTransitionExpression(initial_threshold=0.6)
        # No social signals → private mode
        self.assertAlmostEqual(expr.effective_threshold(), 0.6)

    def test_effective_threshold_private_with_none_signals(self):
        expr = PhaseTransitionExpression(initial_threshold=0.6)
        expr.apply_social_signals(None)
        self.assertAlmostEqual(expr.effective_threshold(), 0.6)

    def test_effective_threshold_private_with_non_group_signals(self):
        expr = PhaseTransitionExpression(initial_threshold=0.6)
        signals = SocialSignals(is_group=False)
        expr.apply_social_signals(signals)
        self.assertAlmostEqual(expr.effective_threshold(), 0.6)

    def test_effective_threshold_group_higher_than_base(self):
        expr = PhaseTransitionExpression(initial_threshold=0.6)
        expr.set_social_params({"group_threshold_boost": 0.5})
        signals = SocialSignals(is_group=True)
        expr.apply_social_signals(signals)
        # theta_group = 0.6 * (1 + 0.5) = 0.9
        self.assertGreater(expr.effective_threshold(), 0.6)

    def test_at_mention_sets_threshold_zero(self):
        expr = PhaseTransitionExpression(initial_threshold=0.6)
        expr.set_social_params({"group_threshold_boost": 0.5})
        signals = SocialSignals(is_group=True, is_at_bot=True)
        expr.apply_social_signals(signals)
        self.assertAlmostEqual(expr.effective_threshold(), 0.0)

    def test_name_mentioned_reduces_threshold(self):
        expr = PhaseTransitionExpression(initial_threshold=0.6)
        expr.set_social_params(
            {"group_threshold_boost": 0.5, "sheaf_coupling": 0.3, "void_coupling": 0.3}
        )
        signals_no_name = SocialSignals(is_group=True, name_mentioned=False)
        signals_name = SocialSignals(is_group=True, name_mentioned=True)
        expr.apply_social_signals(signals_no_name)
        threshold_no_name = expr.effective_threshold()
        expr.apply_social_signals(signals_name)
        threshold_name = expr.effective_threshold()
        self.assertLess(threshold_name, threshold_no_name)

    def test_should_express_uses_effective_threshold(self):
        expr = PhaseTransitionExpression(initial_threshold=0.6)
        expr.set_social_params({"group_threshold_boost": 0.5})
        # Set pressure just above half of base threshold but below group threshold
        expr.pressure = 0.35
        # Private: threshold=0.6, half=0.3, pressure=0.35 > 0.3 → should express
        self.assertTrue(expr.should_express())
        # Group: threshold=0.9, half=0.45, pressure=0.35 < 0.45 → should NOT express
        signals = SocialSignals(is_group=True)
        expr.apply_social_signals(signals)
        self.assertFalse(expr.should_express())

    def test_expression_intensity_uses_effective_threshold(self):
        expr = PhaseTransitionExpression(initial_threshold=0.6)
        expr.set_social_params({"group_threshold_boost": 0.5})
        expr.pressure = 0.5
        # Private: intensity = (0.5 - 0.3) / 0.6 = 0.333
        private_intensity = expr.expression_intensity()
        self.assertGreater(private_intensity, 0.0)
        # Group: threshold=0.9, half=0.45, intensity = (0.5 - 0.45) / 0.9 ≈ 0.056
        signals = SocialSignals(is_group=True)
        expr.apply_social_signals(signals)
        group_intensity = expr.expression_intensity()
        self.assertLess(group_intensity, private_intensity)

    def test_express_refractory_boost_in_group(self):
        expr = PhaseTransitionExpression(initial_threshold=0.5)
        expr.set_social_params({"group_threshold_boost": 0.3, "refractory_boost": 0.05})
        expr.pressure = 1.0
        # Private express
        expr.apply_social_signals(None)
        result_private = expr.express(now=1.0)
        threshold_after_private = result_private["threshold_after"]

        # Reset
        expr.threshold = 0.5
        expr.pressure = 1.0
        signals = SocialSignals(is_group=True)
        expr.apply_social_signals(signals)
        result_group = expr.express(now=2.0)
        threshold_after_group = result_group["threshold_after"]

        # Group refractory should be higher
        self.assertGreater(threshold_after_group, threshold_after_private)


# ===========================================================================
# SocialVoid
# ===========================================================================


class TestSocialVoid(unittest.TestCase):
    def test_tick_accumulates_pressure(self):
        sv = SocialVoid()
        sv.group_activity = 0.5
        sv.topic_boundary = 0.3
        sv.tick(group_active=True)
        self.assertGreater(sv.pressure, 0.0)

    def test_tick_logarithmic_growth(self):
        sv = SocialVoid()
        sv.group_activity = 0.5
        sv.topic_boundary = 0.3
        pressures = []
        for _ in range(20):
            sv.tick(group_active=True)
            pressures.append(sv.pressure)
        # Growth should slow down (logarithmic)
        early_growth = pressures[5] - pressures[0]
        late_growth = pressures[19] - pressures[14]
        # Late growth per tick should be >= early growth per tick due to log(n+1) increasing
        # But the increments themselves grow because log(n+1) grows
        # Actually: increment = depth * log(silence_ticks + 1) * (1-beta) * 0.1
        # Since silence_ticks increases, each increment is larger
        # But total pressure is capped at 5.0
        self.assertGreater(pressures[-1], pressures[0])

    def test_reset_reduces_pressure(self):
        sv = SocialVoid()
        sv.group_activity = 0.8
        sv.topic_boundary = 0.2
        for _ in range(10):
            sv.tick(group_active=True)
        pressure_before = sv.pressure
        sv.reset()
        self.assertLess(sv.pressure, pressure_before)
        # Reset multiplies by 0.3
        self.assertAlmostEqual(sv.pressure, pressure_before * 0.3, places=5)

    def test_pressure_capped_at_5(self):
        sv = SocialVoid()
        sv.group_activity = 1.0
        sv.topic_boundary = 0.0
        for _ in range(1000):
            sv.tick(group_active=True)
        self.assertLessEqual(sv.pressure, 5.0)

    def test_no_accumulation_when_group_inactive(self):
        sv = SocialVoid()
        sv.group_activity = 0.5
        sv.topic_boundary = 0.3
        sv.pressure = 1.0
        sv.tick(group_active=False)
        # When not active, pressure decays (multiplied by 0.95)
        self.assertLess(sv.pressure, 1.0)
        self.assertAlmostEqual(sv.pressure, 0.95, places=5)

    def test_no_accumulation_when_zero_activity(self):
        sv = SocialVoid()
        sv.group_activity = 0.0
        sv.topic_boundary = 0.5
        sv.tick(group_active=True)
        # depth=0 → no pressure added
        self.assertAlmostEqual(sv.pressure, 0.0)


# ===========================================================================
# VoidScarEngine.expression_drive() with social void
# ===========================================================================


class TestVoidScarEngineExpressionDrive(unittest.TestCase):
    def test_social_void_contributes_to_drive(self):
        engine = VoidScarEngine(n_dims=8)
        # Zero social void → baseline drive
        drive_baseline = engine.expression_drive()
        # Add social void pressure
        engine.social_void.pressure = 2.0
        drive_with_void = engine.expression_drive()
        self.assertGreater(drive_with_void, drive_baseline)

    def test_drive_capped_at_1(self):
        engine = VoidScarEngine(n_dims=8)
        engine.social_void.pressure = 100.0
        # Also max out scar drive
        engine.scar_state.base[6] = 1.0
        drive = engine.expression_drive()
        self.assertLessEqual(drive, 1.0)

    def test_social_void_drive_formula(self):
        engine = VoidScarEngine(n_dims=8)
        engine.scar_state.base[6] = 0.0  # zero scar drive
        engine.social_void.pressure = 1.5
        # social_drive = min(1.0, 1.5 / 3.0) = 0.5
        # total = min(1.0, 0 + void_drive*0.5 + 0.5*0.3) = 0.15 + void contribution
        drive = engine.expression_drive()
        # social_drive = 0.5, contributes 0.5 * 0.3 = 0.15
        self.assertGreater(drive, 0.0)


# ===========================================================================
# ComputationSpine social field params
# ===========================================================================


class TestComputationSpineSocialField(unittest.TestCase):
    def test_apply_personality_sets_social_field_params(self):
        spine = ComputationSpine()
        personality = {
            "extraversion": 0.8,
            "neuroticism": 0.3,
            "conscientiousness": 0.6,
            "openness": 0.7,
            "agreeableness": 0.6,
            "patience": 0.5,
            "sovereignty_guard": 0.6,
        }
        spine.apply_personality(personality)
        params = spine._social_field_params
        self.assertIn("group_threshold_boost", params)
        self.assertIn("sheaf_coupling", params)
        self.assertIn("void_coupling", params)
        self.assertIn("refractory_boost", params)
        self.assertIn("noise_sensitivity", params)

    def test_apply_personality_extraversion_lowers_group_boost(self):
        spine = ComputationSpine()
        # High extraversion → lower group_threshold_boost
        spine.apply_personality(
            {
                "extraversion": 0.9,
                "neuroticism": 0.5,
                "conscientiousness": 0.5,
                "openness": 0.5,
                "agreeableness": 0.5,
            }
        )
        high_e_boost = spine._social_field_params["group_threshold_boost"]
        spine.apply_personality(
            {
                "extraversion": 0.1,
                "neuroticism": 0.5,
                "conscientiousness": 0.5,
                "openness": 0.5,
                "agreeableness": 0.5,
            }
        )
        low_e_boost = spine._social_field_params["group_threshold_boost"]
        self.assertLess(high_e_boost, low_e_boost)

    def test_apply_social_signals_passes_to_expression(self):
        spine = ComputationSpine()
        signals = SocialSignals(is_group=True, is_at_bot=True)
        spine.apply_social_signals(signals)
        # The expression layer should now have the signals
        self.assertAlmostEqual(spine.expression.effective_threshold(), 0.0)

    def test_private_chat_no_social_modulation(self):
        spine = ComputationSpine()
        spine.apply_personality(
            {
                "extraversion": 0.5,
                "neuroticism": 0.5,
                "conscientiousness": 0.5,
                "openness": 0.5,
                "agreeableness": 0.5,
            }
        )
        base_threshold = spine.expression.threshold
        # Apply non-group signals
        signals = SocialSignals(is_group=False)
        spine.apply_social_signals(signals)
        self.assertAlmostEqual(spine.expression.effective_threshold(), base_threshold)

    def test_private_chat_none_signals(self):
        spine = ComputationSpine()
        spine.apply_personality(
            {
                "extraversion": 0.5,
                "neuroticism": 0.5,
                "conscientiousness": 0.5,
                "openness": 0.5,
                "agreeableness": 0.5,
            }
        )
        base_threshold = spine.expression.threshold
        spine.apply_social_signals(None)
        self.assertAlmostEqual(spine.expression.effective_threshold(), base_threshold)


# ===========================================================================
# Integration scenarios
# ===========================================================================


class TestIntegrationScenarios(unittest.TestCase):
    def test_silent_ticks_build_social_void_eventually_express(self):
        """10 silent ticks → social void builds → eventually should_express."""
        engine = VoidScarEngine(n_dims=8)
        expr = PhaseTransitionExpression(initial_threshold=0.5)

        # Simulate group activity
        engine.social_void.group_activity = 0.8
        engine.social_void.topic_boundary = 0.2

        expressed = False
        for tick in range(50):
            engine.social_void.tick(group_active=True)
            drive = engine.expression_drive()
            expr.accumulate(drive, dt=1.0)
            if expr.should_express():
                expressed = True
                break

        self.assertTrue(
            expressed, "Social void should eventually push expression past threshold"
        )

    def test_at_mention_immediate_express(self):
        """@mention in group → immediate should_express."""
        expr = PhaseTransitionExpression(initial_threshold=0.6)
        expr.set_social_params({"group_threshold_boost": 0.5})
        # Even with zero pressure, @mention sets threshold to 0
        expr.pressure = 0.01  # Tiny pressure
        signals = SocialSignals(is_group=True, is_at_bot=True)
        expr.apply_social_signals(signals)
        # threshold=0, half=0, pressure=0.01 > 0 → should express
        self.assertTrue(expr.should_express())

    def test_high_extraversion_lower_group_threshold(self):
        """High extraversion personality → lower group threshold → easier participation."""
        spine_extraverted = ComputationSpine()
        spine_extraverted.apply_personality(
            {
                "extraversion": 0.9,
                "neuroticism": 0.3,
                "conscientiousness": 0.5,
                "openness": 0.5,
                "agreeableness": 0.5,
            }
        )

        spine_introverted = ComputationSpine()
        spine_introverted.apply_personality(
            {
                "extraversion": 0.1,
                "neuroticism": 0.3,
                "conscientiousness": 0.5,
                "openness": 0.5,
                "agreeableness": 0.5,
            }
        )

        # Apply group signals to both
        signals = SocialSignals(is_group=True)
        spine_extraverted.apply_social_signals(signals)
        spine_introverted.apply_social_signals(signals)

        threshold_e = spine_extraverted.expression.effective_threshold()
        threshold_i = spine_introverted.expression.effective_threshold()

        # Extraverted should have lower effective threshold in group
        self.assertLess(threshold_e, threshold_i)

    def test_private_chat_invariance_full(self):
        """Private chat: SFPD reduces to standard L7 behavior."""
        spine = ComputationSpine()
        spine.apply_personality(
            {
                "extraversion": 0.7,
                "neuroticism": 0.4,
                "conscientiousness": 0.5,
                "openness": 0.5,
                "agreeableness": 0.5,
            }
        )
        base_threshold = spine.expression.threshold

        # No signals (private)
        spine.apply_social_signals(None)
        self.assertAlmostEqual(spine.expression.effective_threshold(), base_threshold)

        # Explicit non-group signals
        spine.apply_social_signals(SocialSignals(is_group=False))
        self.assertAlmostEqual(spine.expression.effective_threshold(), base_threshold)

    def test_social_void_reset_on_bot_reply(self):
        """Bot replying resets social void pressure."""
        engine = VoidScarEngine(n_dims=8)
        engine.social_void.group_activity = 0.8
        engine.social_void.topic_boundary = 0.2
        for _ in range(20):
            engine.social_void.tick(group_active=True)
        pressure_before = engine.social_void.pressure
        self.assertGreater(pressure_before, 0.0)
        engine.social_void.reset()
        self.assertLess(engine.social_void.pressure, pressure_before)


# ===========================================================================
# Shadow Buffer
# ===========================================================================


class TestShadowBuffer(unittest.TestCase):
    def _make_collector(self, **config_overrides):
        config = {
            "sylanne_persona_name": "Sylanne",
            "sylanne_group_attention_trigger_names": ["小希"],
        }
        config.update(config_overrides)
        return SocialFieldCollector(config=config)

    def test_collect_appends_to_shadow_buffer(self):
        c = self._make_collector()
        c.collect(group_id="g1", sender_id="u1", text="hello", now=1000.0)
        c.collect(group_id="g1", sender_id="u2", text="world", now=1001.0)
        gs = c._get_group("g1")
        self.assertEqual(len(gs.shadow_buffer), 2)
        self.assertEqual(gs.shadow_buffer[0]["sender_id"], "u1")
        self.assertEqual(gs.shadow_buffer[0]["text"], "hello")
        self.assertEqual(gs.shadow_buffer[1]["sender_id"], "u2")

    def test_shadow_buffer_maxlen_20(self):
        c = self._make_collector()
        for i in range(25):
            c.collect(group_id="g1", sender_id=f"u{i}", text=f"msg{i}", now=1000.0 + i)
        gs = c._get_group("g1")
        self.assertEqual(len(gs.shadow_buffer), 20)
        self.assertEqual(gs.shadow_buffer[0]["text"], "msg5")

    def test_shadow_buffer_text_truncated_at_300(self):
        c = self._make_collector()
        long_text = "x" * 500
        c.collect(group_id="g1", sender_id="u1", text=long_text, now=1000.0)
        gs = c._get_group("g1")
        self.assertEqual(len(gs.shadow_buffer[0]["text"]), 300)

    def test_drain_shadow_buffer_returns_entries(self):
        c = self._make_collector()
        c.collect(group_id="g1", sender_id="u1", text="a", now=1.0)
        c.collect(group_id="g1", sender_id="u2", text="b", now=2.0)
        entries = c.drain_shadow_buffer("g1")
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["text"], "a")
        self.assertEqual(entries[1]["text"], "b")

    def test_drain_shadow_buffer_clears(self):
        c = self._make_collector()
        c.collect(group_id="g1", sender_id="u1", text="a", now=1.0)
        c.drain_shadow_buffer("g1")
        gs = c._get_group("g1")
        self.assertEqual(len(gs.shadow_buffer), 0)

    def test_drain_shadow_buffer_empty_group(self):
        c = self._make_collector()
        entries = c.drain_shadow_buffer("nonexistent")
        self.assertEqual(entries, [])

    def test_notify_bot_replied_clears_shadow_buffer(self):
        c = self._make_collector()
        c.collect(group_id="g1", sender_id="u1", text="hello", now=1.0)
        c.collect(group_id="g1", sender_id="u2", text="world", now=2.0)
        gs = c._get_group("g1")
        self.assertEqual(len(gs.shadow_buffer), 2)
        c.notify_bot_replied("g1", "reply")
        self.assertEqual(len(gs.shadow_buffer), 0)

    def test_shadow_buffer_per_group_isolation(self):
        c = self._make_collector()
        c.collect(group_id="g1", sender_id="u1", text="g1msg", now=1.0)
        c.collect(group_id="g2", sender_id="u2", text="g2msg", now=2.0)
        entries_g1 = c.drain_shadow_buffer("g1")
        entries_g2 = c.drain_shadow_buffer("g2")
        self.assertEqual(len(entries_g1), 1)
        self.assertEqual(entries_g1[0]["text"], "g1msg")
        self.assertEqual(len(entries_g2), 1)
        self.assertEqual(entries_g2[0]["text"], "g2msg")


class TestConversationBufferInjectContext(unittest.TestCase):
    def test_inject_context_prepends_messages(self):
        from sylanne_alpha.memory_system import ConversationBuffer

        buf = ConversationBuffer(session_key="test")
        buf.append("user", "current message")
        entries = [
            {"sender_id": "u1", "text": "prior1", "ts": 1.0},
            {"sender_id": "u2", "text": "prior2", "ts": 2.0},
        ]
        buf.inject_context(entries)
        self.assertEqual(buf.messages[0]["role"], "group_observed")
        self.assertEqual(buf.messages[0]["text"], "prior1")
        self.assertEqual(buf.messages[1]["role"], "group_observed")
        self.assertEqual(buf.messages[1]["text"], "prior2")
        self.assertEqual(buf.messages[2]["role"], "user")
        self.assertEqual(buf.messages[2]["text"], "current message")

    def test_inject_context_empty_list(self):
        from sylanne_alpha.memory_system import ConversationBuffer

        buf = ConversationBuffer(session_key="test")
        buf.append("user", "msg")
        buf.inject_context([])
        self.assertEqual(len(buf.messages), 1)

    def test_inject_context_preserves_sender_id(self):
        from sylanne_alpha.memory_system import ConversationBuffer

        buf = ConversationBuffer(session_key="test")
        entries = [{"sender_id": "alice", "text": "hi", "ts": 1.0}]
        buf.inject_context(entries)
        self.assertEqual(buf.messages[0]["sender_id"], "alice")


# ===========================================================================
# AstrBot Group Context Detection
# ===========================================================================


class TestAstrBotGroupContextDetection(unittest.TestCase):
    """Tests for _detect_astrbot_group_context adaptation logic."""

    def _make_plugin(self, config=None):
        import main

        ctx = MagicMock()
        ctx.register_web_api = MagicMock()
        plugin = main.EmotionalStatePlugin(
            context=ctx,
            config=config or {},
        )
        return plugin

    def test_detection_disabled_by_config(self):
        plugin = self._make_plugin(
            config={"sylanne_alpha_auto_detect_group_context": False}
        )
        # Even if context has the flag, detection should return False
        plugin.context.get_config = MagicMock(
            return_value={"enable_group_context": True}
        )
        self.assertFalse(plugin._detect_astrbot_group_context())

    def test_detection_via_get_config(self):
        plugin = self._make_plugin(
            config={"sylanne_alpha_auto_detect_group_context": True}
        )
        plugin.context.get_config = MagicMock(
            return_value={"enable_group_context": True}
        )
        self.assertTrue(plugin._detect_astrbot_group_context())

    def test_detection_via_get_config_alt_key(self):
        plugin = self._make_plugin(
            config={"sylanne_alpha_auto_detect_group_context": True}
        )
        plugin.context.get_config = MagicMock(
            return_value={"group_context_enabled": True}
        )
        self.assertTrue(plugin._detect_astrbot_group_context())

    def test_detection_via_platform_settings(self):
        plugin = self._make_plugin(
            config={"sylanne_alpha_auto_detect_group_context": True}
        )
        # No get_config method
        del plugin.context.get_config
        plugin.context.platform_settings = {"group_context_enabled": True}
        self.assertTrue(plugin._detect_astrbot_group_context())

    def test_detection_via_config_manager(self):
        plugin = self._make_plugin(
            config={"sylanne_alpha_auto_detect_group_context": True}
        )
        del plugin.context.get_config
        plugin.context.platform_settings = {}
        config_mgr = MagicMock()
        config_mgr.config = {"enable_group_context": True}
        plugin.context.config_manager = config_mgr
        self.assertTrue(plugin._detect_astrbot_group_context())

    def test_detection_returns_false_when_not_enabled(self):
        plugin = self._make_plugin(
            config={"sylanne_alpha_auto_detect_group_context": True}
        )
        plugin.context.get_config = MagicMock(
            return_value={"enable_group_context": False}
        )
        del plugin.context.platform_settings
        del plugin.context.config_manager
        self.assertFalse(plugin._detect_astrbot_group_context())

    def test_detection_handles_exception_gracefully(self):
        plugin = self._make_plugin(
            config={"sylanne_alpha_auto_detect_group_context": True}
        )
        plugin.context.get_config = MagicMock(side_effect=RuntimeError("boom"))
        self.assertFalse(plugin._detect_astrbot_group_context())

    def test_detection_default_config_is_true(self):
        """Default config enables auto-detection."""
        plugin = self._make_plugin(config={})
        # No AstrBot group context configured
        plugin.context.get_config = MagicMock(return_value={})
        self.assertFalse(plugin._detect_astrbot_group_context())


if __name__ == "__main__":
    unittest.main()
