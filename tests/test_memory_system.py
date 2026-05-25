"""
Comprehensive unit tests for the 3-layer memory system v2.

Tests cover ConversationBuffer, write_summary, 12h consolidation,
recall (L1/L2/L3), reconsolidation v2, 30-day compression,
serialization, personality derivation, and tick decay.
"""

import math
import time
import unittest
from unittest.mock import patch

from sylanne_alpha.memory_system import (
    ConversationBuffer,
    GraphEdge,
    GraphNode,
    MemoryItem,
    MemoryResult,
    MemorySystem,
    REWRITE_FREEZE_AFTER,
    L2_COMPRESSION_AGE_TICKS,
)


def _embed(val: float = 0.1, dim: int = 8) -> list[float]:
    return [val] * dim


def _make_system(**kwargs) -> MemorySystem:
    return MemorySystem(**kwargs)


# ===========================================================================
# ConversationBuffer
# ===========================================================================

class TestConversationBuffer(unittest.TestCase):

    def test_append_user_message(self):
        buf = ConversationBuffer(session_key="s1")
        buf.append("user", "hello", ts=1000.0)
        self.assertEqual(len(buf.messages), 1)
        self.assertEqual(buf.messages[0]["role"], "user")
        self.assertEqual(buf.messages[0]["text"], "hello")

    def test_append_bot_increments_turn_count(self):
        buf = ConversationBuffer(session_key="s1")
        buf.append("user", "hi", ts=1.0)
        self.assertEqual(buf.turn_count, 0)
        buf.append("bot", "hello", ts=2.0)
        self.assertEqual(buf.turn_count, 1)

    def test_user_messages_do_not_increment_turn_count(self):
        buf = ConversationBuffer(session_key="s1")
        buf.append("user", "a", ts=1.0)
        buf.append("user", "b", ts=2.0)
        self.assertEqual(buf.turn_count, 0)

    def test_should_flush_empty_returns_empty(self):
        buf = ConversationBuffer(session_key="s1")
        self.assertEqual(buf.should_flush(), "")

    def test_should_flush_idle_after_timeout(self):
        buf = ConversationBuffer(session_key="s1")
        buf.append("user", "hi", ts=time.time() - 120)
        result = buf.should_flush(idle_seconds=60.0)
        self.assertEqual(result, "idle")

    def test_should_flush_max_turns(self):
        buf = ConversationBuffer(session_key="s1")
        for i in range(20):
            buf.append("bot", f"msg {i}", ts=time.time())
        result = buf.should_flush(idle_seconds=9999, max_turns=20)
        self.assertEqual(result, "max_turns")

    def test_should_flush_not_ready(self):
        buf = ConversationBuffer(session_key="s1")
        buf.append("bot", "hi", ts=time.time())
        result = buf.should_flush(idle_seconds=9999, max_turns=20)
        self.assertEqual(result, "")

    def test_drain_returns_messages_and_resets(self):
        buf = ConversationBuffer(session_key="s1")
        buf.append("user", "a", ts=1.0)
        buf.append("bot", "b", ts=2.0)
        msgs = buf.drain()
        self.assertEqual(len(msgs), 2)
        self.assertEqual(buf.turn_count, 0)
        self.assertEqual(len(buf.messages), 0)

    def test_to_dict_from_dict_roundtrip(self):
        buf = ConversationBuffer(session_key="s1")
        buf.append("user", "hello", ts=100.0)
        buf.append("bot", "hi", ts=101.0)
        data = buf.to_dict()
        buf2 = ConversationBuffer.from_dict(data)
        self.assertEqual(buf2.session_key, "s1")
        self.assertEqual(len(buf2.messages), 2)
        self.assertEqual(buf2.turn_count, 1)
        self.assertAlmostEqual(buf2.last_activity, 101.0)


# ===========================================================================
# MemorySystem.write_summary
# ===========================================================================

class TestWriteSummary(unittest.TestCase):

    def test_creates_memory_item_with_correct_fields(self):
        ms = _make_system()
        item = ms.write_summary("test summary", source_turns=5, embedding=_embed(), temperature=0.3)
        self.assertEqual(item.text, "test summary")
        self.assertEqual(item.source_turns, 5)
        self.assertFalse(item.confirmed)
        self.assertEqual(item.rewrite_count, 0)
        self.assertEqual(item.recall_count, 0)
        self.assertAlmostEqual(item.weight, 1.0)

    def test_item_added_to_l1(self):
        ms = _make_system()
        ms.write_summary("hello", source_turns=3)
        self.assertEqual(len(ms._l1), 1)
        self.assertEqual(ms._l1[0].text, "hello")

    def test_l1_capacity_respected(self):
        ms = _make_system()
        for i in range(70):
            ms.write_summary(f"msg {i}", source_turns=1)
        self.assertEqual(len(ms._l1), 60)

    def test_write_backward_compat(self):
        ms = _make_system()
        ms.write("compat test", embedding=_embed(), temperature=0.5)
        self.assertEqual(len(ms._l1), 1)
        self.assertEqual(ms._l1[0].text, "compat test")
        self.assertEqual(ms._l1[0].source_turns, 1)


# ===========================================================================
# 12h Consolidation flow
# ===========================================================================

class TestConsolidationFlow(unittest.TestCase):

    def test_mark_confirmed(self):
        ms = _make_system()
        item = ms.write_summary("x", source_turns=2, embedding=_embed())
        self.assertFalse(item.confirmed)
        ms.mark_confirmed([item.id])
        self.assertTrue(item.confirmed)

    def test_consolidation_candidates_requires_confirmed(self):
        ms = _make_system()
        # Not confirmed
        a = ms.write_summary("a", source_turns=1, embedding=_embed())
        # Confirmed, no embedding (still eligible — embedding not required)
        b = ms.write_summary("b", source_turns=1)
        ms.mark_confirmed([b.id])
        # Confirmed, has embedding
        c = ms.write_summary("c", source_turns=1, embedding=_embed())
        ms.mark_confirmed([c.id])
        candidates = ms.consolidation_candidates()
        ids = [item.id for item in candidates]
        self.assertNotIn(a.id, ids)
        self.assertIn(b.id, ids)
        self.assertIn(c.id, ids)

    def test_consolidation_candidates_only_confirmed(self):
        ms = _make_system()
        item = ms.write_summary("recent", source_turns=1, embedding=_embed())
        # Not confirmed → not a candidate
        candidates = ms.consolidation_candidates()
        self.assertEqual(len(candidates), 0)
        # Confirm → now a candidate
        ms.mark_confirmed([item.id])
        candidates = ms.consolidation_candidates()
        self.assertEqual(len(candidates), 1)

    def test_sink_to_l2_moves_items(self):
        ms = _make_system()
        item = ms.write_summary("sink me", source_turns=2, embedding=_embed())
        ms.mark_confirmed([item.id])
        ms.sink_to_l2([item.id])
        self.assertEqual(len(ms._l2), 1)
        self.assertEqual(ms._l2[0].text, "sink me")
        # Should be removed from L1
        l1_ids = [i.id for i in ms._l1]
        self.assertNotIn(item.id, l1_ids)

    def test_clear_unconfirmed_removes_old_unconfirmed(self):
        ms = _make_system()
        # Create old unconfirmed item
        with patch("time.time", return_value=1000.0):
            ms.write_summary("old unconfirmed", source_turns=1)
        # Create recent unconfirmed item
        with patch("time.time", return_value=time.time()):
            ms.write_summary("recent unconfirmed", source_turns=1)
        removed = ms.clear_unconfirmed(keep_recent_hours=4)
        self.assertEqual(removed, 1)

    def test_clear_unconfirmed_keeps_confirmed(self):
        ms = _make_system()
        with patch("time.time", return_value=1000.0):
            item = ms.write_summary("old confirmed", source_turns=1)
        ms.mark_confirmed([item.id])
        removed = ms.clear_unconfirmed(keep_recent_hours=4)
        self.assertEqual(removed, 0)
        self.assertEqual(len(ms._l1), 1)

    def test_needs_consolidation_true_initially(self):
        ms = _make_system()
        ms.write_summary("something", source_turns=1)
        self.assertTrue(ms.needs_consolidation())

    def test_needs_consolidation_false_after_mark_done(self):
        ms = _make_system()
        ms.mark_consolidation_done()
        # Just marked done, no time has passed, L1 not full → False
        self.assertFalse(ms.needs_consolidation())

    def test_needs_consolidation_true_when_l1_full(self):
        ms = _make_system()
        ms.mark_consolidation_done()
        for i in range(60):
            ms.write_summary(f"msg {i}", source_turns=1)
        self.assertTrue(ms.needs_consolidation())


# ===========================================================================
# Recall
# ===========================================================================

class TestRecallL1Keyword(unittest.TestCase):

    def test_keyword_match_returns_result(self):
        ms = _make_system()
        ms.write("I love cats", embedding=_embed(), temperature=0.5)
        ms.write("dogs are great", embedding=_embed(), temperature=0.0)
        results = ms.recall("cats", query_embedding=_embed(), current_warmth=0.0)
        texts = [r.text for r in results]
        self.assertIn("I love cats", texts)

    def test_l1_results_have_layer_tag(self):
        ms = _make_system()
        ms.write("test message", embedding=_embed(), temperature=0.0)
        results = ms.recall("test", query_embedding=_embed(), current_warmth=0.0)
        l1_results = [r for r in results if r.layer == "L1"]
        self.assertGreater(len(l1_results), 0)


class TestRecallL2Embedding(unittest.TestCase):

    def _setup_l2(self):
        ms = _make_system()
        for i in range(5):
            item = ms.write_summary(
                f"l2 item {i}", source_turns=1,
                embedding=[0.1 * (i + 1), 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.9],
            )
            ms.mark_confirmed([item.id])
        ms.sink_to_l2([item.id for item in ms._l1])
        return ms

    def test_l2_recall_by_embedding(self):
        ms = self._setup_l2()
        query_emb = [0.3, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.9]
        results = ms.recall("", query_embedding=query_emb, current_warmth=0.0)
        l2_results = [r for r in results if r.layer == "L2"]
        self.assertGreater(len(l2_results), 0)

    def test_l2_results_have_relevance_score(self):
        ms = self._setup_l2()
        results = ms.recall("", query_embedding=_embed(0.1), current_warmth=0.0)
        l2_results = [r for r in results if r.layer == "L2"]
        for r in l2_results:
            self.assertGreaterEqual(r.relevance, 0.0)
            self.assertLessEqual(r.relevance, 1.0)


class TestRecallL3Graph(unittest.TestCase):

    def test_l3_recall_finds_related_entity(self):
        ms = _make_system()
        triples = [
            ("Alice", "likes", "cats", 0.8, 1.0),
            ("Alice", "lives_in", "Tokyo", 0.3, 1.0),
        ]
        ms.ingest_graph_triples(triples)
        results = ms.recall("Alice", query_embedding=_embed(), current_warmth=0.0)
        l3_results = [r for r in results if r.layer == "L3"]
        self.assertGreater(len(l3_results), 0)

    def test_l3_results_have_clarity(self):
        ms = _make_system()
        triples = [("Bob", "plays", "guitar", 0.5, 0.9)]
        ms.ingest_graph_triples(triples)
        results = ms.recall("Bob", query_embedding=_embed(), current_warmth=0.0)
        l3_results = [r for r in results if r.layer == "L3"]
        for r in l3_results:
            self.assertGreater(r.clarity, 0.0)
            self.assertLessEqual(r.clarity, 1.0)


class TestGetRecalledL2Items(unittest.TestCase):

    def test_returns_items_hit_during_recall(self):
        ms = _make_system()
        item = ms.write_summary("target", source_turns=1, embedding=_embed(0.5))
        ms.mark_confirmed([item.id])
        ms.sink_to_l2([item.id])
        ms.recall("target", query_embedding=_embed(0.5), current_warmth=0.0)
        recalled = ms.get_recalled_l2_items()
        self.assertEqual(len(recalled), 1)
        self.assertEqual(recalled[0].text, "target")


class TestFormatRecallInjection(unittest.TestCase):

    def test_produces_layered_format(self):
        ms = _make_system()
        results = [
            MemoryResult(text="recent thing", layer="L1", weight=1.0, relevance=0.9, clarity=1.0, temperature=0.0, final_score=0.9),
            MemoryResult(text="related thing", layer="L2", weight=0.8, relevance=0.7, clarity=1.0, temperature=0.0, final_score=0.7),
            MemoryResult(text="graph thing", layer="L3", weight=0.5, relevance=0.5, clarity=0.8, temperature=0.0, final_score=0.4),
        ]
        output = ms.format_recall_injection(results)
        self.assertIn("[记忆参考]", output)
        self.assertIn("近期", output)
        self.assertIn("相关", output)
        self.assertIn("认知", output)

    def test_empty_results_returns_empty_string(self):
        ms = _make_system()
        self.assertEqual(ms.format_recall_injection([]), "")


# ===========================================================================
# Reconsolidation v2
# ===========================================================================

class TestReconsolidation(unittest.TestCase):

    def _make_l2_item(self, ms: MemorySystem, text: str = "test") -> MemoryItem:
        item = ms.write_summary(text, source_turns=1, embedding=_embed())
        ms.mark_confirmed([item.id])
        ms.sink_to_l2([item.id])
        return ms._l2[-1]

    def test_rewrite_item_updates_text(self):
        ms = _make_system()
        item = self._make_l2_item(ms, "original")
        result = ms.rewrite_item(item.id, "rewritten")
        self.assertTrue(result)
        self.assertEqual(item.text, "rewritten")

    def test_rewrite_item_increments_rewrite_count(self):
        ms = _make_system()
        item = self._make_l2_item(ms, "original")
        ms.rewrite_item(item.id, "v2")
        self.assertEqual(item.rewrite_count, 1)
        ms.rewrite_item(item.id, "v3")
        self.assertEqual(item.rewrite_count, 2)

    def test_rewrite_item_frozen_after_limit(self):
        ms = _make_system()
        item = self._make_l2_item(ms, "original")
        item.rewrite_count = REWRITE_FREEZE_AFTER
        result = ms.rewrite_item(item.id, "should fail")
        self.assertFalse(result)
        self.assertEqual(item.text, "original")

    def test_rewrite_item_nonexistent_returns_false(self):
        ms = _make_system()
        result = ms.rewrite_item("nonexistent_id", "text")
        self.assertFalse(result)


# ===========================================================================
# 30-day compression
# ===========================================================================

class TestCompression30Day(unittest.TestCase):

    def _make_l2_item(self, ms: MemorySystem, text: str = "test", age: int = 0) -> MemoryItem:
        item = ms.write_summary(text, source_turns=1, embedding=_embed())
        ms.mark_confirmed([item.id])
        ms.sink_to_l2([item.id])
        ms._l2[-1].age_ticks = age
        return ms._l2[-1]

    def test_compress_check_returns_old_items(self):
        ms = _make_system()
        self._make_l2_item(ms, "old", age=L2_COMPRESSION_AGE_TICKS + 100)
        candidates = ms.compress_check()
        self.assertEqual(len(candidates), 1)

    def test_compress_check_returns_empty_for_fresh(self):
        ms = _make_system()
        self._make_l2_item(ms, "fresh", age=10)
        candidates = ms.compress_check()
        self.assertEqual(len(candidates), 0)

    def test_compress_check_batch_limit_10(self):
        ms = _make_system()
        for i in range(15):
            self._make_l2_item(ms, f"item {i}", age=L2_COMPRESSION_AGE_TICKS + i)
        candidates = ms.compress_check()
        self.assertLessEqual(len(candidates), 10)

    def test_remove_compressed(self):
        ms = _make_system()
        item = self._make_l2_item(ms, "to remove", age=L2_COMPRESSION_AGE_TICKS + 1)
        ms.remove_compressed([item.id])
        self.assertEqual(len(ms._l2), 0)


# ===========================================================================
# Serialization
# ===========================================================================

class TestSerialization(unittest.TestCase):

    def test_empty_system_roundtrip(self):
        ms = _make_system()
        data = ms.to_dict()
        ms2 = _make_system()
        ms2.from_dict(data)
        self.assertEqual(len(ms2._l1), 0)
        self.assertEqual(len(ms2._l2), 0)

    def test_l1_preserved(self):
        ms = _make_system()
        ms.write_summary("hello", source_turns=3, embedding=_embed(), temperature=0.5)
        data = ms.to_dict()
        ms2 = _make_system()
        ms2.from_dict(data)
        self.assertEqual(len(ms2._l1), 1)
        self.assertEqual(ms2._l1[0].text, "hello")
        self.assertEqual(ms2._l1[0].source_turns, 3)
        self.assertAlmostEqual(ms2._l1[0].temperature, 0.5)

    def test_l2_preserved_with_weights(self):
        ms = _make_system()
        item = ms.write_summary("sink", source_turns=1, embedding=_embed())
        ms.mark_confirmed([item.id])
        ms.sink_to_l2([item.id])
        ms._l2[0].weight = 0.75
        data = ms.to_dict()
        ms2 = _make_system()
        ms2.from_dict(data)
        self.assertEqual(len(ms2._l2), 1)
        self.assertAlmostEqual(ms2._l2[0].weight, 0.75)

    def test_l3_graph_preserved(self):
        ms = _make_system()
        ms.ingest_graph_triples([("Alice", "likes", "cats", 0.8, 0.9)])
        data = ms.to_dict()
        ms2 = _make_system()
        ms2.from_dict(data)
        self.assertEqual(len(ms2._l3_nodes), len(ms._l3_nodes))
        self.assertEqual(len(ms2._l3_edges), len(ms._l3_edges))

    def test_version_field(self):
        ms = _make_system()
        data = ms.to_dict()
        self.assertEqual(data["version"], "2.0.0")

    def test_v1_data_backward_compat(self):
        v1_data = {
            "tick": 5,
            "params": {"base_decay": 0.02, "age_coeff": 0.15, "recall_boost": 0.03,
                       "age_reset_factor": 0.5, "reconsolidation_rate": 0.05,
                       "compression_threshold": 0.15, "mood_weight": 0.2,
                       "positive_recall_bias": 1.0, "negative_decay_mult": 1.0,
                       "neuroticism": 0.5},
            "l1": [{"id": "abc", "text": "old", "weight": 1.0, "temperature": 0.0,
                    "age_ticks": 0, "embedding": None, "created_at": 1000.0}],
            "l2": [],
            "l3_nodes": {},
            "l3_edges": [],
        }
        ms = _make_system()
        ms.from_dict(v1_data)
        self.assertEqual(len(ms._l1), 1)
        self.assertEqual(ms._l1[0].source_turns, 1)
        self.assertFalse(ms._l1[0].confirmed)
        self.assertEqual(ms._l1[0].rewrite_count, 0)

    def test_embeddings_preserved(self):
        ms = _make_system()
        emb = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
        ms.write_summary("with emb", source_turns=1, embedding=emb)
        data = ms.to_dict()
        ms2 = _make_system()
        ms2.from_dict(data)
        self.assertEqual(ms2._l1[0].embedding, emb)


# ===========================================================================
# Personality derivation
# ===========================================================================

class TestPersonalityDerivation(unittest.TestCase):

    def test_high_conscientiousness_lowers_base_decay(self):
        ms = _make_system(conscientiousness=1.0)
        self.assertAlmostEqual(ms._params["base_decay"], 0.01)

    def test_low_conscientiousness_raises_base_decay(self):
        ms = _make_system(conscientiousness=0.0)
        self.assertAlmostEqual(ms._params["base_decay"], 0.04)

    def test_high_openness_raises_compression_threshold(self):
        ms = _make_system(openness=1.0)
        self.assertAlmostEqual(ms._params["compression_threshold"], 0.25)

    def test_high_agreeableness_raises_positive_recall_bias(self):
        ms = _make_system(agreeableness=1.0)
        self.assertAlmostEqual(ms._params["positive_recall_bias"], 1.3)

    def test_high_neuroticism_lowers_negative_decay_mult(self):
        ms = _make_system(neuroticism=1.0)
        self.assertAlmostEqual(ms._params["negative_decay_mult"], 0.5)


# ===========================================================================
# Tick decay
# ===========================================================================

class TestTickDecayL2(unittest.TestCase):

    def _setup_l2(self, **kwargs):
        ms = _make_system(**kwargs)
        for i in range(5):
            item = ms.write_summary(f"item {i}", source_turns=1, embedding=_embed())
            ms.mark_confirmed([item.id])
        ms.sink_to_l2([item.id for item in ms._l1])
        return ms

    def test_single_tick_reduces_weight(self):
        ms = self._setup_l2()
        initial = ms._l2[0].weight
        ms.tick_decay()
        self.assertLess(ms._l2[0].weight, initial)

    def test_multiple_ticks_monotonically_decrease(self):
        ms = self._setup_l2()
        weights = [ms._l2[0].weight]
        for _ in range(10):
            ms.tick_decay()
            weights.append(ms._l2[0].weight)
        for i in range(1, len(weights)):
            self.assertLess(weights[i], weights[i - 1])

    def test_weight_never_goes_negative(self):
        ms = self._setup_l2()
        for _ in range(500):
            ms.tick_decay()
        for item in ms._l2:
            self.assertGreaterEqual(item.weight, 0.0)

    def test_age_ticks_increment(self):
        ms = self._setup_l2()
        initial_age = ms._l2[0].age_ticks
        ms.tick_decay()
        self.assertEqual(ms._l2[0].age_ticks, initial_age + 1)


class TestTickDecayL3(unittest.TestCase):

    def test_clarity_decreases_on_tick(self):
        ms = _make_system()
        ms.ingest_graph_triples([("Dave", "knows", "Python", 0.5, 1.0)])
        node = list(ms._l3_nodes.values())[0]
        initial = node.clarity
        ms.tick_decay()
        self.assertLess(node.clarity, initial)

    def test_clarity_decay_rate_0_998(self):
        ms = _make_system()
        ms.ingest_graph_triples([("Eve", "likes", "music", 0.3, 1.0)])
        node = list(ms._l3_nodes.values())[0]
        node.clarity = 1.0
        ms.tick_decay()
        self.assertAlmostEqual(node.clarity, 0.998, places=4)

    def test_edge_clarity_decays(self):
        ms = _make_system()
        ms.ingest_graph_triples([("Frank", "teaches", "art", 0.4, 1.0)])
        edge = ms._l3_edges[0]
        initial = edge.clarity
        ms.tick_decay()
        self.assertLess(edge.clarity, initial)

    def test_permanent_node_no_decay(self):
        ms = _make_system()
        ms.ingest_graph_triples([("Kai", "name_is", "Kai", 0.0, 1.0)])
        node = list(ms._l3_nodes.values())[0]
        node.temporal_type = "permanent"
        node.clarity = 1.0
        for _ in range(100):
            ms.tick_decay()
        self.assertAlmostEqual(node.clarity, 1.0, places=5)


class TestGarbageCollection(unittest.TestCase):

    def test_low_clarity_nodes_removed(self):
        ms = _make_system()
        ms.ingest_graph_triples([
            ("Old", "knew", "something", 0.1, 0.05),
            ("Fresh", "knows", "everything", 0.5, 0.9),
        ])
        for node in ms._l3_nodes.values():
            if node.label == "Old":
                node.clarity = 0.01
        ms.tick_decay()
        remaining = {n.label for n in ms._l3_nodes.values()}
        self.assertNotIn("Old", remaining)
        self.assertIn("Fresh", remaining)

    def test_edges_removed_with_dead_nodes(self):
        ms = _make_system()
        ms.ingest_graph_triples([("Stale", "connected_to", "Active", 0.1, 1.0)])
        for node in ms._l3_nodes.values():
            if node.label == "Stale":
                node.clarity = 0.01
        ms.tick_decay()
        stale_ids = {n.id for n in ms._l3_nodes.values() if n.label == "Stale"}
        for edge in ms._l3_edges:
            self.assertNotIn(edge.source, stale_ids)


if __name__ == "__main__":
    unittest.main()

