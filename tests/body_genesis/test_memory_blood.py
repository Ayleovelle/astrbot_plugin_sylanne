import unittest

from sylanne_body.event.normalize import normalize_event
from sylanne_body.event.source import EventSource
from sylanne_body.memory.blood import MemoryBlood


class MemoryBloodGenesisTests(unittest.TestCase):
    def test_memory_blood_stores_irreversible_trace_without_raw_text(self):
        blood = MemoryBlood(limit=3)
        event = normalize_event(text="我今天很开心，这是秘密。", source="user")

        trace = blood.absorb(event, relation_epoch=0)
        exported = blood.export_traces()

        self.assertEqual(trace.event_id, event.event_id)
        self.assertEqual("relation", trace.intent)
        self.assertEqual(0, trace.relation_epoch)
        self.assertTrue(exported[0]["internal_only"])
        self.assertFalse(exported[0]["public_api_eligible"])
        self.assertNotIn("text", exported[0])
        self.assertNotIn("开心", str(exported))
        self.assertNotIn("秘密", str(exported))

    def test_memory_blood_rejects_internal_surface_and_unknown_signal(self):
        blood = MemoryBlood()
        internal = normalize_event(text="这里像哭泣。", source=EventSource.INTERNAL_BODY_SURFACE)
        external = normalize_event(text="webhook payload", source="webhook")

        self.assertFalse(blood.absorb(internal, relation_epoch=0).accepted)
        self.assertFalse(blood.absorb(external, relation_epoch=0).accepted)
        self.assertEqual([], blood.export_traces())

    def test_memory_blood_delete_epoch_clears_old_traces(self):
        blood = MemoryBlood()
        old_event = normalize_event(text="旧关系里的话。", source="user")
        new_event = normalize_event(text="新关系里的话。", source="user")

        blood.absorb(old_event, relation_epoch=0)
        blood.clear_for_epoch(relation_epoch=1)
        blood.absorb(new_event, relation_epoch=1)
        exported = blood.export_traces()

        self.assertEqual([new_event.event_id], [item["event_id"] for item in exported])
        self.assertEqual([1], [item["relation_epoch"] for item in exported])
        self.assertNotIn(old_event.event_id, str(exported))

    def test_memory_blood_is_bounded_and_export_is_non_mutating(self):
        blood = MemoryBlood(limit=2)
        first = normalize_event(text="第一句。", source="user")
        second = normalize_event(text="第二句。", source="user")
        third = normalize_event(text="第三句。", source="user")

        blood.absorb(first, relation_epoch=0)
        blood.absorb(second, relation_epoch=0)
        blood.absorb(third, relation_epoch=0)
        exported = blood.export_traces()
        exported[0]["event_id"] = "tampered"
        reread = blood.export_traces()

        self.assertEqual([second.event_id, third.event_id], [item["event_id"] for item in reread])
        self.assertNotIn(first.event_id, str(reread))


if __name__ == "__main__":
    unittest.main()
