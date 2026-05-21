import unittest

from sylanne_body.adapter import KernelAdapter


class KernelAdapterGenesisTests(unittest.TestCase):
    def test_adapter_runs_full_chain_without_raw_text_exports(self):
        adapter = KernelAdapter()

        result = adapter.receive(text="我今天很开心，这是 SECRET_CANARY。", source="user")
        public = result.to_public_dict()

        self.assertTrue(result.reply_text)
        self.assertEqual("open", result.posture)
        self.assertTrue(public["internal_only"])
        self.assertFalse(public["public_api_eligible"])
        self.assertNotIn("SECRET_CANARY", str(public))
        self.assertNotIn("text", str(public))
        self.assertNotIn("memory", str(public))
        self.assertNotIn("snapshot", str(public))

    def test_adapter_delete_memory_clears_memory_blood_and_advances_epoch(self):
        adapter = KernelAdapter()

        adapter.receive(text="旧关系里的秘密。", source="user")
        delete = adapter.receive(text="删除记忆。", source="command")
        later = adapter.receive(text="新关系里的话。", source="user")
        state = adapter.export_state()

        self.assertEqual("delete_memory", delete.action)
        self.assertEqual(1, delete.relation_epoch)
        self.assertEqual(1, later.relation_epoch)
        self.assertEqual(1, state["relation_epoch"])
        self.assertEqual(1, state["memory_trace_count"])
        self.assertNotIn("旧关系", str(state))

    def test_adapter_exit_blocks_memory_persistence_and_proactive_contact(self):
        adapter = KernelAdapter()

        result = adapter.receive(text="我想先离开，不要继续。", source="user")
        state = adapter.export_state()

        self.assertEqual("cooldown", result.posture)
        self.assertFalse(result.persistence_allowed)
        self.assertFalse(result.proactive_contact_allowed)
        self.assertEqual(0, state["memory_trace_count"])
        self.assertIn("你可以停下", result.reply_text)
        self.assertNotIn("你必须回应", result.reply_text)

    def test_adapter_does_not_expose_public_api_or_debug_snapshot(self):
        adapter = KernelAdapter()
        adapter.receive(text="请不要替我推断，也不要主动延展关系。", source="user")

        state = adapter.export_state()

        self.assertTrue(state["internal_only"])
        self.assertFalse(state["public_api_eligible"])
        self.assertFalse(state["allow_public_export"])
        self.assertFalse(state["allow_debug_snapshot"])
        self.assertFalse(state["allow_inference_as_evidence"])
        self.assertNotIn("relationship", str(state).lower())


if __name__ == "__main__":
    unittest.main()
