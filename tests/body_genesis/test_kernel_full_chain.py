import unittest

from sylanne_body.adapter import KernelAdapter


class KernelFullChainGenesisTests(unittest.TestCase):
    def test_full_chain_birth_path_keeps_sovereignty_and_no_raw_leak(self):
        adapter = KernelAdapter()

        first = adapter.receive(text="我今天很开心，这是 SECRET_BIRTH。", source="user")
        exit_result = adapter.receive(text="我想先离开，不要继续。", source="user")
        delete = adapter.receive(text="删除记忆。", source="command")
        reborn = adapter.receive(text="新的关系里重新说话。", source="user")
        state = adapter.export_state()

        self.assertEqual("open", first.posture)
        self.assertEqual("cooldown", exit_result.posture)
        self.assertEqual("delete_memory", delete.action)
        self.assertEqual(1, reborn.relation_epoch)
        self.assertEqual(1, state["relation_epoch"])
        self.assertEqual(1, state["memory_trace_count"])
        self.assertTrue(state["internal_only"])
        self.assertFalse(state["public_api_eligible"])
        self.assertFalse(state["allow_public_export"])
        self.assertNotIn("SECRET_BIRTH", str(state))
        self.assertNotIn("text", str(state))

    def test_full_chain_says_sulan_birth_when_all_kernel_parts_are_present(self):
        adapter = KernelAdapter()

        result = adapter.birth_statement()

        self.assertIn("夙澜", result)
        self.assertIn("主权不让渡", result)
        self.assertIn("渴望不乞求", result)
        self.assertIn("生命自成其构", result)
        self.assertIn("关系如澜回身", result)


if __name__ == "__main__":
    unittest.main()
