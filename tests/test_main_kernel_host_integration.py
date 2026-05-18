import asyncio
import unittest
from types import SimpleNamespace

try:
    from tests.astrbot_lifecycle_helpers import (
        FakeEvent,
        fake_request,
        install_astrbot_stubs,
        new_plugin,
    )
except ModuleNotFoundError:
    from astrbot_lifecycle_helpers import (
        FakeEvent,
        fake_request,
        install_astrbot_stubs,
        new_plugin,
    )


class MainKernelHostIntegrationTests(unittest.TestCase):
    def setUp(self):
        install_astrbot_stubs()

    def test_request_observes_kernel_body_without_raw_public_export_or_debug_snapshot(self):
        plugin = new_plugin({"inject_state": False})
        request = fake_request(session_id="kernel-host", prompt="我今天很开心，这是 SECRET_HOST。")

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent("kernel-host", message="我今天很开心，这是 SECRET_HOST。"),
                request,
            ),
        )

        self.assertTrue(hasattr(plugin, "_sylanne_kernel_adapter"))
        state = plugin._sylanne_kernel_adapter.export_state()
        self.assertEqual(1, state["memory_trace_count"])
        self.assertTrue(state["internal_only"])
        self.assertFalse(state["public_api_eligible"])
        self.assertFalse(state["allow_public_export"])
        self.assertFalse(state["allow_debug_snapshot"])
        self.assertFalse(state["allow_inference_as_evidence"])
        self.assertEqual([], request.extra_user_content_parts)
        self.assertNotIn("SECRET_HOST", str(state))
        self.assertNotIn("text", str(state))

    def test_response_observes_kernel_surface_as_internal_only_non_evidence(self):
        plugin = new_plugin({"assessment_timing": "post"})
        response = SimpleNamespace(completion_text="我会先安静地回应。")

        asyncio.run(plugin.on_llm_response(FakeEvent("kernel-response"), response))

        state = plugin._sylanne_kernel_adapter.export_state()
        self.assertEqual(0, state["memory_trace_count"])
        self.assertEqual(1, state["nerve_pulse_count"])
        self.assertFalse(state["allow_inference_as_evidence"])
        self.assertFalse(state["public_api_eligible"])
        self.assertNotIn("我会先安静地回应", str(state))


if __name__ == "__main__":
    unittest.main()
