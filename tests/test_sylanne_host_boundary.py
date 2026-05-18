from __future__ import annotations

import asyncio
import unittest

try:
    from tests.test_command_tools import bind_async, install_astrbot_stubs, new_plugin
    from tests.astrbot_lifecycle_helpers import FakeEvent, fake_request
except ModuleNotFoundError:
    from test_command_tools import bind_async, install_astrbot_stubs, new_plugin
    from astrbot_lifecycle_helpers import FakeEvent, fake_request


class SylanneHostBoundaryTests(unittest.TestCase):
    def setUp(self):
        install_astrbot_stubs()

    def _request_text_parts(self, request):
        return [part.text for part in request.extra_user_content_parts]

    def test_auxiliary_prompt_injections_are_delegated_to_kernel_adapter_boundary(self):
        plugin = new_plugin(
            {
                "assessment_timing": "post",
                "inject_state": True,
                "agent_speaker_relationship_tracking": True,
                "humanlike_state_enabled": True,
                "lifelike_learning_enabled": True,
                "enable_moral_repair_state": True,
                "enable_fallibility_state": True,
                "enable_group_atmosphere": True,
            },
        )
        calls = []

        async def fake_persona(self, event, request):
            return None

        def fake_append_auxiliary_state(
            self,
            request,
            state_name,
            full_builder,
            *,
            source,
            injection_decision,
            injection_budget,
            fallback_source=None,
            after_append=None,
        ):
            calls.append(
                {
                    "state_name": state_name,
                    "source": source,
                    "fallback_source": fallback_source,
                    "has_after_append": after_append is not None,
                },
            )
            appended = self._append_temp_text_part(
                request,
                f'<bot_auxiliary_state private="true" name="{state_name}" detail="kernel-adapter-boundary">hosted</bot_auxiliary_state>',
                source=source,
                budget=injection_budget,
            )
            if appended and after_append is not None:
                after_append()
            return appended

        bind_async(plugin, "_persona_profile", fake_persona)
        plugin._append_auxiliary_state = fake_append_auxiliary_state.__get__(plugin)
        request = fake_request(
            session_id="group-kernel-boundary",
            prompt="Alice says sorry and wants us to keep learning",
        )

        asyncio.run(
            plugin.on_llm_request(
                FakeEvent(
                    "group-kernel-boundary",
                    message="Alice says sorry and wants us to keep learning",
                    sender_id="user-a",
                    sender_name="Alice",
                ),
                request,
            ),
        )

        sources = {call["source"] for call in calls}
        self.assertGreaterEqual(
            sources,
            {
                "humanlike",
                "lifelike_learning",
                "moral_repair",
                "fallibility",
                "personality_drift",
                "group_atmosphere",
            },
        )
        self.assertIn(
            {
                "state_name": "group_atmosphere",
                "source": "group_atmosphere",
                "fallback_source": "group_atmosphere.compact_fallback",
                "has_after_append": True,
            },
            calls,
        )
        joined = "\n".join(self._request_text_parts(request))
        self.assertIn('name="humanlike" detail="kernel-adapter-boundary"', joined)
        self.assertIn('name="group_atmosphere" detail="kernel-adapter-boundary"', joined)


if __name__ == "__main__":
    unittest.main()
