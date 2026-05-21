from __future__ import annotations

import asyncio
import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


class SylanneMain4Tests(unittest.TestCase):
    def setUp(self) -> None:
        sys.modules.pop("main", None)

    def test_main_imports_without_astrbot_and_exposes_4_runtime(self):
        main = importlib.import_module("main")

        self.assertEqual(main.PLUGIN_NAME, "astrbot_plugin_sylanne")
        self.assertTrue(hasattr(main, "EmotionalStatePlugin"))
        self.assertTrue(hasattr(main, "get_emotional_state_plugin"))
        self.assertFalse(hasattr(main, "EmotionEngine"))
        self.assertFalse(hasattr(main, "LifelikeLearningEngine"))

    def test_main_drives_full_alpha_lifecycle_without_old_engines(self):
        main = importlib.import_module("main")
        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(context=SimpleNamespace(), config={"sylanne_alpha_root": tmp})

            request_surface = asyncio.run(plugin.observe_request("room:4", text="我来了", confidence=0.7, flags=["safe"], now=1.0))
            response_surface = asyncio.run(plugin.observe_response("room:4", text="我也在", confidence=0.8, flags=["safe"], now=2.0))
            diagnostics = asyncio.run(plugin.sylanne_diagnostics(session_key="room:4"))
            exported = asyncio.run(plugin.export_sylanne_alpha(session_key="room:4"))

        self.assertEqual(request_surface["schema_version"], "sylanne.alpha.body.v1")
        self.assertGreater(response_surface["turns"], request_surface["turns"])
        self.assertIn("body", diagnostics)
        self.assertIn("host_payload", diagnostics)
        self.assertEqual(exported["session_key"], "room:4")
        self.assertIn("vector_summary", diagnostics["diagnostics"])

    def test_main_replies_to_immediate_chat_without_waiting_for_llm_lifecycle(self):
        main = importlib.import_module("main")
        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(context=SimpleNamespace(), config={"sylanne_alpha_root": tmp})

            reply = asyncio.run(plugin.chat_sylanne(session_key="room:chat", text="你在吗", now=1.0))
            diagnostics = asyncio.run(plugin.sylanne_diagnostics(session_key="room:chat"))

        self.assertEqual(reply["schema_version"], "sylanne.alpha.chat.v1")
        self.assertEqual(reply["session_key"], "room:chat")
        self.assertTrue(reply["ok"])
        self.assertTrue(reply["reply_text"])
        self.assertNotIn("Sylanne 在这里", reply["reply_text"])
        self.assertNotIn("身体还热着", reply["reply_text"])
        self.assertNotIn("need_expression", reply["reply_text"])
        self.assertNotRegex(reply["reply_text"], r"\d+\.\d+")
        self.assertIn(reply["action"], {"express", "explore", "wait", "hold", "reach_out", "repair", "withdraw"})
        self.assertGreaterEqual(diagnostics["turns"], 2)
        self.assertEqual(diagnostics["body"]["memory"]["traces"][0]["text"], "你在吗")

    def test_main_restores_3x_visible_commands_as_alpha_surfaces(self):
        main = importlib.import_module("main")
        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(context=SimpleNamespace(), config={"sylanne_alpha_root": tmp})
            asyncio.run(plugin.chat_sylanne(session_key="room:commands", text="共同记忆 4.0", now=1.0))

            surfaces = {
                "emotion": asyncio.run(plugin.emotion(session_key="room:commands")),
                "psych_state": asyncio.run(plugin.psych_state(session_key="room:commands")),
                "humanlike_state": asyncio.run(plugin.humanlike_state(session_key="room:commands")),
                "lifelike_state": asyncio.run(plugin.lifelike_state(session_key="room:commands")),
                "personality_drift_state": asyncio.run(plugin.personality_drift_state(session_key="room:commands")),
                "moral_repair_state": asyncio.run(plugin.moral_repair_state(session_key="room:commands")),
                "integrated_self": asyncio.run(plugin.integrated_self(session_key="room:commands")),
                "shadow_diagnostics": asyncio.run(plugin.shadow_diagnostics(session_key="room:commands")),
                "fallibility_state": asyncio.run(plugin.fallibility_state(session_key="room:commands")),
            }
            memory = asyncio.run(plugin.sylanne_memory(session_key="room:commands", query="共同记忆"))
            reset = asyncio.run(plugin.humanlike_reset(session_key="room:commands"))

        for name, payload in surfaces.items():
            with self.subTest(name=name):
                self.assertEqual(payload["schema_version"], "sylanne.alpha.compat.v1")
                self.assertEqual(payload["session_key"], "room:commands")
                self.assertEqual(payload["slice"], name)
                self.assertIn("summary", payload)
                self.assertIn("values", payload)
        self.assertEqual(memory["schema_version"], "sylanne.alpha.compat.memory.v1")
        self.assertEqual(memory["matches"][0]["text"], "共同记忆 4.0")
        self.assertNotIn("lineage", surfaces["integrated_self"])
        self.assertNotIn("turning_point", surfaces["shadow_diagnostics"])
        self.assertEqual(reset["slice"], "humanlike_state")
        self.assertTrue(reset["reset"])

    def test_main_persists_long_request_to_prompt_injection_chain(self):
        main = importlib.import_module("main")
        request = SimpleNamespace(prompt="base")
        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(context=SimpleNamespace(), config={"sylanne_alpha_root": tmp})
            asyncio.run(plugin.observe_request("room:chain", text="链路记忆", confidence=0.8, flags=["safe", "preference"], now=1.0))
            memory_before = asyncio.run(plugin.query_sylanne_memory(session_key="room:chain", query="链路"))
            injected = asyncio.run(plugin.inject_emotion_context(request=request, session_key="room:chain"))
            restored = main.EmotionalStatePlugin(context=SimpleNamespace(), config={"sylanne_alpha_root": tmp})
            memory_after = asyncio.run(restored.query_sylanne_memory(session_key="room:chain", query="链路"))
            diagnostics = asyncio.run(restored.sylanne_diagnostics(session_key="room:chain"))

        self.assertEqual(memory_before["matches"][0]["text"], "链路记忆")
        self.assertEqual(memory_after["matches"][0]["text"], "链路记忆")
        self.assertIn("[retrieved_conversation_context]", injected["prompt"])
        self.assertLessEqual(len(injected["prompt"]), main.MAX_LLM_REQUEST_PROMPT_CHARS)
        self.assertNotIn("[sylanne_context]", injected["prompt"])
        self.assertNotIn("relationship_phase", injected["prompt"])
        self.assertNotIn("voice_cadence", injected["prompt"])
        self.assertNotIn("posture=", injected["prompt"])
        self.assertNotIn("need_", injected["prompt"])
        self.assertIn("relationship_memory", diagnostics["host_payload"])
        self.assertIn("prompt_context_bus", diagnostics["host_payload"])

    def test_memory_prompt_injection_keeps_current_message_primary_over_old_topic(self):
        main = importlib.import_module("main")
        request = SimpleNamespace(prompt="base")
        query = "现在不要聊毕设了，帮我看这段合并转发里的旅行安排"
        old_topic = "旧话题：我们刚才在聊土木毕设图纸"
        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(context=SimpleNamespace(), config={"sylanne_alpha_root": tmp})
            payload = {
                "schema_version": "sylanne.alpha.compat.memory.v1",
                "session_key": "room:attention",
                "slice": "sylanne_memory",
                "query": query,
                "matches": [{"id": "old-topic", "text": old_topic, "score": 0.8}],
                "count": 1,
            }

            plugin._append_request_prompt_fragment(request, plugin._memory_prompt_fragment(payload))

        self.assertIn("[retrieved_conversation_context]", request.prompt)
        self.assertIn(f"当前用户输入：{query}", request.prompt)
        self.assertIn(old_topic, request.prompt)
        self.assertIn("旧记忆只作旁注", request.prompt)
        self.assertIn("冲突时以当前用户输入为准", request.prompt)
        self.assertIn("不要把旧记忆当成用户的新请求", request.prompt)

    def test_main_injects_current_user_input_anchor_without_memory_recall(self):
        main = importlib.import_module("main")
        event = SimpleNamespace(
            session_id="room:current-anchor",
            unified_msg_origin="aiocqhttp:room:current-anchor",
            message_str="我不是说了吗？你傻得可爱",
        )
        request = SimpleNamespace(prompt="base")
        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(
                context=SimpleNamespace(),
                config={
                    "sylanne_alpha_root": tmp,
                    "sylanne_alpha_realtime_chat_enabled": True,
                },
            )

            asyncio.run(plugin.on_llm_request(event, request))
            pending = list(plugin._background_tasks)
            if pending:
                asyncio.run(asyncio.gather(*pending))

        self.assertIn("我不是说了吗？你傻得可爱", request.prompt)
        self.assertIn("当前用户输入", request.prompt)
        self.assertIn("优先", request.prompt)
        self.assertLessEqual(len(request.prompt), main.MAX_LLM_REQUEST_PROMPT_CHARS)

    def test_main_persists_shadow_memory_as_advisory_signals_without_raw_public_leak(self):
        main = importlib.import_module("main")
        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(context=SimpleNamespace(), config={"sylanne_alpha_root": tmp})

            asyncio.run(plugin.observe_request("room:shadow", text="不是这个意思，你理解错了", confidence=0.9, flags=["safe"], now=1.0))
            asyncio.run(plugin.observe_request("room:shadow", text="接着刚才没说完的地方讲", confidence=0.8, flags=["safe"], now=2.0))
            asyncio.run(plugin.observe_request("room:shadow", text="这个谐音梗只是玩笑，不要当事实", confidence=0.8, flags=["safe", "preference"], now=3.0))
            diagnostics = asyncio.run(plugin.sylanne_diagnostics(session_key="room:shadow"))
            shadow = diagnostics["host_payload"]["shadow_memory"]
            integrated_self = diagnostics["host_payload"]["integrated_self"]
            public_shadow = asyncio.run(plugin.shadow_diagnostics(session_key="room:shadow"))
            exported = asyncio.run(plugin.export_sylanne_alpha(session_key="room:shadow"))
            restored = main.EmotionalStatePlugin(context=SimpleNamespace(), config={"sylanne_alpha_root": tmp})
            restored_shadow = asyncio.run(restored.sylanne_diagnostics(session_key="room:shadow"))["host_payload"]["shadow_memory"]

        self.assertEqual(shadow["kind"], "shadow_memory")
        self.assertTrue(shadow["internal_only"])
        self.assertFalse(shadow["public_api_eligible"])
        self.assertIn("advisory_only", shadow["constraints"])
        self.assertEqual(shadow["signals"]["correction_count"], 1)
        self.assertEqual(shadow["signals"]["followup_count"], 1)
        self.assertEqual(shadow["signals"]["joke_or_bit_count"], 1)
        self.assertEqual(shadow["memory_gate"]["long_term_fact_count"], 0)
        self.assertIn("shadow_memory_advisory", integrated_self["intent_plan"]["lanes"])
        self.assertGreater(integrated_self["state_index"]["repair_pressure"], 0.0)
        self.assertNotIn("不是这个意思", json.dumps(public_shadow, ensure_ascii=False))
        self.assertNotIn("接着刚才", json.dumps(public_shadow, ensure_ascii=False))
        self.assertNotIn("谐音梗", json.dumps(public_shadow, ensure_ascii=False))
        self.assertNotIn("raw_text", json.dumps(public_shadow, ensure_ascii=False))
        self.assertEqual(restored_shadow["signals"], shadow["signals"])
        self.assertIn("shadow", exported["body"]["memory"])

    def test_main_records_interrupted_stream_as_shadow_followup_without_prompt_bloat(self):
        main = importlib.import_module("main")
        request = SimpleNamespace(prompt="base")
        event = SimpleNamespace(
            session_id="room:interrupt-shadow",
            unified_msg_origin="aiocqhttp:room:interrupt-shadow",
            message_str="继续",
        )
        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(
                context=SimpleNamespace(),
                config={
                    "sylanne_alpha_root": tmp,
                    "sylanne_alpha_realtime_chat_enabled": True,
                },
            )
            plugin._unfinished_replies["room:interrupt-shadow"] = "这是一段没有说完的后半句" * 1000

            async def run_hook():
                await plugin.on_llm_request(event, request)
                pending = list(plugin._background_tasks)
                if pending:
                    await asyncio.gather(*pending)
                return await plugin.sylanne_diagnostics(session_key="room:interrupt-shadow")

            diagnostics = asyncio.run(run_hook())

        shadow = diagnostics["host_payload"]["shadow_memory"]
        self.assertLessEqual(len(request.prompt), 12000)
        self.assertIn("上一轮回复没有说完", request.prompt)
        self.assertEqual(shadow["signals"]["interruption_count"], 1)
        self.assertEqual(shadow["signals"]["followup_count"], 1)
        self.assertEqual(shadow["memory_gate"]["long_term_fact_count"], 0)
        self.assertNotIn("这是一段没有说完的后半句", json.dumps(shadow, ensure_ascii=False))

    def test_main_query_and_simulate_are_readonly_across_restore(self):
        main = importlib.import_module("main")
        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(context=SimpleNamespace(), config={"sylanne_alpha_root": tmp})
            asyncio.run(plugin.observe_request("room:readonly", text="只读记忆", confidence=0.7, flags=["safe"], now=1.0))
            before = asyncio.run(plugin.export_sylanne_alpha(session_key="room:readonly"))
            asyncio.run(plugin.query_sylanne_memory(session_key="room:readonly", query="只读"))
            asyncio.run(plugin.simulate_emotion_update(session_key="room:readonly", text="模拟不写入", flags=["hurt"], confidence=1.0))
            after = asyncio.run(plugin.export_sylanne_alpha(session_key="room:readonly"))
            restored = main.EmotionalStatePlugin(context=SimpleNamespace(), config={"sylanne_alpha_root": tmp})
            restored_snapshot = asyncio.run(restored.export_sylanne_alpha(session_key="room:readonly"))

        self.assertEqual(after, before)
        self.assertEqual(restored_snapshot, before)
        self.assertNotIn("模拟不写入", str(restored_snapshot))

    def test_main_query_sylanne_memory_uses_configured_embedding_provider_when_keyword_misses(self):
        main = importlib.import_module("main")
        calls: list[str] = []

        class FakeEmbeddingProvider:
            provider_config = {"id": "embed-a", "provider_type": "embedding"}

            async def get_embedding(self, text):
                calls.append(text)
                return [1.0, 0.0]

        class FakeContext:
            def get_provider_by_id(self, provider_id):
                return FakeEmbeddingProvider() if provider_id == "embed-a" else None

        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(
                context=FakeContext(),
                config={
                    "sylanne_alpha_root": tmp,
                    "sylanne_alpha_embedding_memory_enabled": True,
                    "sylanne_alpha_embedding_memory_provider_id": "embed-a",
                },
            )
            host = plugin._host("room:embedding")
            host.kernel.body.memory["traces"] = [
                {"id": "trace-1", "text": "土木毕设图纸和结构设计", "weight": 0.8, "embedding": [0.9, 0.1]},
            ]
            host.runtime.save(host.kernel)

            result = asyncio.run(plugin.query_sylanne_memory(session_key="room:embedding", query="毕业设计", limit=3))

        self.assertEqual(calls, ["毕业设计"])
        self.assertEqual(result["source"], "embedding")
        self.assertEqual(result["matches"][0]["id"], "trace-1")

    def test_main_query_sylanne_memory_does_not_call_embedding_provider_on_keyword_hit(self):
        main = importlib.import_module("main")
        calls: list[str] = []

        class FakeEmbeddingProvider:
            async def get_embedding(self, text):
                calls.append(text)
                return [1.0, 0.0]

        class FakeContext:
            def get_provider_by_id(self, provider_id):
                return FakeEmbeddingProvider() if provider_id == "embed-a" else None

        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(
                context=FakeContext(),
                config={
                    "sylanne_alpha_root": tmp,
                    "sylanne_alpha_embedding_memory_enabled": True,
                    "sylanne_alpha_embedding_memory_provider_id": "embed-a",
                },
            )
            asyncio.run(plugin.observe_request("room:keyword", text="土木毕设图纸", confidence=0.8, flags=["safe"], now=1.0))

            result = asyncio.run(plugin.query_sylanne_memory(session_key="room:keyword", query="土木", limit=3))

        self.assertEqual(calls, [])
        self.assertEqual(result["source"], "keyword")
        self.assertTrue(result["matches"])

    def test_main_injects_compact_embedding_recall_into_llm_request_prompt(self):
        main = importlib.import_module("main")
        calls: list[str] = []

        class FakeEmbeddingProvider:
            provider_config = {"id": "embed-a", "provider_type": "embedding"}

            async def get_embedding(self, text):
                calls.append(text)
                return [1.0, 0.0]

        class FakeContext:
            def get_provider_by_id(self, provider_id):
                return FakeEmbeddingProvider() if provider_id == "embed-a" else None

        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(
                context=FakeContext(),
                config={
                    "sylanne_alpha_root": tmp,
                    "sylanne_alpha_realtime_chat_enabled": True,
                    "sylanne_alpha_embedding_memory_enabled": True,
                    "sylanne_alpha_embedding_memory_provider_id": "embed-a",
                },
            )
            host = plugin._host("room:inject-embedding")
            host.kernel.body.memory["traces"] = [
                {
                    "id": "trace-secret-id",
                    "text": "土木毕设图纸和结构设计" + "补充" * 1000,
                    "weight": 0.8,
                    "embedding": [0.9, 0.1],
                    "metadata": {"debug": "internal"},
                }
            ]
            host.runtime.save(host.kernel)
            request = SimpleNamespace(prompt="base")
            event = SimpleNamespace(
                session_id="room:inject-embedding",
                unified_msg_origin="aiocqhttp:room:inject-embedding",
                message_str="毕业设计怎么继续",
            )

            async def run_hook():
                await plugin.on_llm_request(event, request)
                pending = list(plugin._background_tasks)
                if pending:
                    await asyncio.gather(*pending)

            asyncio.run(run_hook())

        self.assertEqual(calls, ["毕业设计怎么继续"])
        self.assertIn("[retrieved_conversation_context]", request.prompt)
        self.assertIn("检索到的记忆参考", request.prompt)
        self.assertIn("土木毕设图纸和结构设计", request.prompt)
        self.assertLessEqual(len(request.prompt), 12000)
        self.assertNotIn("trace-secret-id", request.prompt)
        self.assertNotIn("embedding", request.prompt)
        self.assertNotIn("metadata", request.prompt)
        self.assertNotIn("debug", request.prompt)

    def test_main_build_emotion_memory_payload_prompt_fragment_includes_compact_embedding_recall(self):
        main = importlib.import_module("main")

        class FakeEmbeddingProvider:
            async def get_embedding(self, text):
                return [1.0, 0.0]

        class FakeContext:
            def get_provider_by_id(self, provider_id):
                return FakeEmbeddingProvider() if provider_id == "embed-a" else None

        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(
                context=FakeContext(),
                config={
                    "sylanne_alpha_root": tmp,
                    "sylanne_alpha_embedding_memory_enabled": True,
                    "sylanne_alpha_embedding_memory_provider_id": "embed-a",
                },
            )
            host = plugin._host("room:payload-embedding")
            host.kernel.body.memory["traces"] = [
                {"id": "trace-hidden", "text": "毕业设计需要图纸和结构计算", "weight": 0.9, "embedding": [1.0, 0.0]}
            ]
            host.runtime.save(host.kernel)

            payload = asyncio.run(plugin.build_emotion_memory_payload(session_key="room:payload-embedding", query="毕设", limit=2))

        self.assertEqual(payload["source"], "embedding")
        self.assertEqual(payload["matches"][0]["id"], "trace-hidden")
        self.assertIn("检索到的记忆参考", payload["prompt_fragment"])
        self.assertIn("毕业设计需要图纸和结构计算", payload["prompt_fragment"])
        self.assertNotIn("trace-hidden", payload["prompt_fragment"])
        self.assertNotIn("embedding", payload["prompt_fragment"])

    def test_main_session_isolation_and_reset_do_not_cross_write(self):
        main = importlib.import_module("main")
        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(context=SimpleNamespace(), config={"sylanne_alpha_root": tmp})
            asyncio.run(plugin.observe_request("room:a", text="A 的记忆", confidence=0.8, flags=["safe"], now=1.0))
            asyncio.run(plugin.observe_request("room:b", text="B 的记忆", confidence=0.8, flags=["safe"], now=1.0))
            reset_a = asyncio.run(plugin.reset_sylanne(session_key="room:a"))
            memory_a = asyncio.run(plugin.query_sylanne_memory(session_key="room:a", query="记忆"))
            memory_b = asyncio.run(plugin.query_sylanne_memory(session_key="room:b", query="记忆"))

        self.assertEqual(reset_a["turns"], 0)
        self.assertEqual(memory_a["matches"], [])
        self.assertEqual(memory_b["matches"][0]["text"], "B 的记忆")

    def test_main_rebuilds_public_api_facade_on_alpha_runtime(self):
        main = importlib.import_module("main")
        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(context=SimpleNamespace(), config={"sylanne_alpha_root": tmp})

            observed = asyncio.run(plugin.observe_emotion_text("room:api", text="我记得你", confidence=0.8, now=1.0))
            snapshot = asyncio.run(plugin.get_emotion_snapshot(session_key="room:api"))
            state = asyncio.run(plugin.get_emotion_state(session_key="room:api"))
            values = asyncio.run(plugin.get_emotion_values(session_key="room:api"))
            memory_payload = asyncio.run(plugin.build_emotion_memory_payload(session_key="room:api", query="记得"))
            memory_query = asyncio.run(plugin.query_sylanne_memory(session_key="room:api", query="记得"))
            proactive = asyncio.run(plugin.get_proactive_speech_decision(session_key="room:api", now=40.0))
            realtime_plan = asyncio.run(plugin.get_realtime_chat_plan("room:api", "Sylanne 在这里。她会即时回应。"))
            realtime_dispatch = asyncio.run(plugin.request_realtime_chat_dispatch("room:api", "Sylanne 在这里。"))
            request = SimpleNamespace(prompt="base")
            injected = asyncio.run(plugin.inject_emotion_context(None, request, session_key="room:api"))
            simulated = asyncio.run(plugin.simulate_emotion_update(session_key="room:api", text="模拟", flags=["safe"]))

        self.assertEqual(observed["schema_version"], "sylanne.alpha.compat.v1")
        self.assertEqual(snapshot["schema_version"], "sylanne.alpha.compat.v1")
        self.assertEqual(snapshot["slice"], "emotion")
        self.assertIn("warmth", values)
        self.assertEqual(state["values"], values)
        self.assertEqual(memory_payload["schema_version"], "sylanne.alpha.compat.memory.v1")
        self.assertEqual(memory_query["matches"][0]["text"], "我记得你")
        self.assertEqual(proactive["kind"], "proactive_decision")
        self.assertEqual(realtime_plan["schema_version"], "sylanne.alpha.realtime_plan.v1")
        self.assertGreaterEqual(realtime_plan["message_count"], 1)
        self.assertEqual(realtime_dispatch["kind"], "realtime_chat_dispatch")
        self.assertNotIn("Sylanne 4.0 body", injected["prompt"])
        self.assertNotIn("[sylanne_context]", injected["prompt"])
        self.assertNotIn("relationship_phase", injected["prompt"])
        self.assertNotIn("voice_cadence", injected["prompt"])
        self.assertNotIn("posture=", injected["prompt"])
        self.assertNotIn("need_", injected["prompt"])
        self.assertIn("[retrieved_conversation_context]", injected["prompt"])
        self.assertEqual(simulated["schema_version"], "sylanne.alpha.compat.simulation.v1")
        self.assertEqual(asyncio.run(plugin.export_sylanne_alpha(session_key="room:api"))["turns"], snapshot["turns"])

    def test_main_controls_pause_resume_reset_import_export_cooldown_proactive_and_smoke(self):
        main = importlib.import_module("main")
        legacy = {"memory": {"records": [{"id": "old", "text": "旧数据"}], "event_count": 4}}
        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(context=SimpleNamespace(), config={"sylanne_alpha_root": tmp})

            imported = asyncio.run(plugin.import_sylanne_legacy(legacy, session_key="room:legacy"))
            paused = asyncio.run(plugin.pause_sylanne(session_key="room:legacy"))
            resumed = asyncio.run(plugin.resume_sylanne(session_key="room:legacy"))
            cooled = asyncio.run(plugin.cooldown_sylanne(session_key="room:legacy"))
            proactive = asyncio.run(plugin.proactive_sylanne(session_key="room:legacy", now=80.0))
            exported = asyncio.run(plugin.export_sylanne_alpha(session_key="room:legacy"))
            reset = asyncio.run(plugin.reset_sylanne(session_key="room:legacy"))
            smoke = asyncio.run(plugin.sylanne_smoke(session_key="room:smoke"))

        self.assertEqual(imported["body"]["memory"]["traces"][0]["text"], "旧数据")
        self.assertFalse(paused["guard"]["allowed"])
        self.assertTrue(resumed["guard"]["allowed"])
        self.assertIn("host_payload", cooled)
        self.assertEqual(proactive["host_payload"]["kind"], "proactive_dispatch")
        self.assertEqual(exported["session_key"], "room:legacy")
        self.assertEqual(reset["turns"], 0)
        self.assertTrue(smoke["ok"])

    def test_main_proactive_loop_requires_sovereignty_opt_in_and_structured_reason(self):
        main = importlib.import_module("main")
        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(context=SimpleNamespace(), config={"sylanne_alpha_root": tmp})

            blocked = asyncio.run(plugin.proactive_sylanne(session_key="room:proactive", now=10.0))
            asyncio.run(plugin.observe_request("room:proactive", text="我在这里", confidence=0.8, flags=["safe"], now=11.0))
            allowed = asyncio.run(plugin.proactive_sylanne(session_key="room:proactive", now=40.0))

        self.assertFalse(blocked["host_payload"]["should_send"])
        self.assertIn("sovereignty_opt_in_required", blocked["guard"]["flags"])
        self.assertTrue(allowed["host_payload"]["should_send"])
        self.assertEqual(allowed["host_payload"]["kind"], "proactive_dispatch")
        self.assertIn(allowed["decision"]["reason_code"], {"contact_need", "expression_need", "repair_need"})
        self.assertGreater(allowed["host_payload"]["next_check_seconds"], 0)

    def test_main_proactive_loop_respects_cooldown_and_budget(self):
        main = importlib.import_module("main")
        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(context=SimpleNamespace(), config={"sylanne_alpha_root": tmp})

            asyncio.run(plugin.observe_request("room:budget", text="靠近一点", confidence=0.9, flags=["safe"], now=1.0))
            first = asyncio.run(plugin.proactive_sylanne(session_key="room:budget", now=40.0))
            cooldown = asyncio.run(plugin.proactive_sylanne(session_key="room:budget", now=41.0))
            host = plugin._host("room:budget")
            host.kernel.body.immunity.interruption_budget = 0.05
            exhausted = asyncio.run(plugin.proactive_sylanne(session_key="room:budget", now=200.0))

        self.assertTrue(first["host_payload"]["should_send"])
        self.assertLess(first["body"]["immunity"]["interruption_budget"], 1.0)
        self.assertFalse(cooldown["host_payload"]["should_send"])
        self.assertIn("proactive_cooldown", cooldown["guard"]["flags"])
        self.assertFalse(exhausted["host_payload"]["should_send"])
        self.assertIn("budget_exhausted", exhausted["guard"]["flags"])

    def test_main_exposes_readonly_status_observatory_payload_for_webui(self):
        main = importlib.import_module("main")
        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(context=SimpleNamespace(), config={"sylanne_alpha_root": tmp})
            asyncio.run(plugin.chat_sylanne(session_key="room:webui", text="观察一下状态", now=1.0))

            payload = asyncio.run(plugin.sylanne_observatory(session_key="room:webui"))

        self.assertEqual(payload["schema_version"], "sylanne.alpha.observatory.v1")
        self.assertEqual(payload["session_key"], "room:webui")
        self.assertEqual(payload["mode"], "readonly")
        self.assertTrue(payload["read_only"])
        self.assertIn("body_state", payload)
        self.assertIn("memory_state", payload)
        self.assertIn("persona_drift_state", payload)
        self.assertIn("network_space_state", payload)
        self.assertEqual([card["id"] for card in payload["cards"]], ["body", "memory", "drift", "space"])
        self.assertIn("身体感", {card["title"] for card in payload["cards"]})
        self.assertIn("no_raw_conversation_text", payload["constraints"])
        self.assertIn("body", payload)
        self.assertIn("decision", payload)
        self.assertIn("guard", payload)
        self.assertIn("memory", payload)
        self.assertIn("switches", payload)
        self.assertIn("visualization", payload)
        self.assertEqual(payload["visualization"]["token_flow"]["title"], "Token 分段使用")
        self.assertGreaterEqual(len(payload["visualization"]["memory_nodes"]), 1)
        self.assertIn("config_controls", payload)
        control_ids = {control["id"] for control in payload["config_controls"]}
        self.assertIn("sylanne_alpha_realtime_chat_enabled", control_ids)
        self.assertIn("sylanne_alpha_proactive_dispatch_enabled", control_ids)
        self.assertIn("sylanne_alpha_embedding_memory_enabled", control_ids)
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("raw_dialogue", serialized)
        self.assertNotIn("lineage", serialized)
        self.assertNotIn("relationship_time_weight", serialized)
        self.assertNotIn("isolation_key", serialized)
        self.assertNotIn("观察一下状态", serialized)

        main = importlib.import_module("main")

        plugin = main.EmotionalStatePlugin(context=SimpleNamespace(), config={})

        self.assertTrue(callable(main.filter.command("probe")))
        self.assertTrue(callable(main.filter.llm_tool(name="probe")))
        self.assertTrue(callable(plugin.sylanne_status))
        self.assertTrue(callable(plugin.sylanne_proactive))

    def test_main_registers_observatory_status_webui_route(self):
        main = importlib.import_module("main")
        registered = []

        class FakeContext:
            def register_web_api(self, route, handler, methods, desc):
                registered.append((route, handler, tuple(methods), desc))

        plugin = main.EmotionalStatePlugin(context=FakeContext(), config={})

        routes = {(route, methods) for route, _, methods, _ in registered}
        self.assertIn(("/astrbot_plugin_sylanne/observatory-status", ("GET",)), routes)
        self.assertNotIn(("/astrbot_plugin_sylanne/observatory-status", ("POST",)), routes)
        route, handler, methods, desc = registered[0]
        self.assertEqual(route, "/astrbot_plugin_sylanne/observatory-status")
        self.assertEqual(methods, ("GET",))
        self.assertIn("observatory", desc)
        payload = asyncio.run(handler(SimpleNamespace(session_id="room:route")))
        self.assertTrue(payload["read_only"])
        self.assertEqual(payload["session_key"], "room:route")

    def test_observatory_status_static_page_contains_core_cards(self):
        page_root = Path(__file__).resolve().parents[1] / "pages" / "observatory-status"
        index = (page_root / "index.html").read_text(encoding="utf-8")
        app = (page_root / "app.js").read_text(encoding="utf-8")
        style = (page_root / "style.css").read_text(encoding="utf-8")

        self.assertIn('data-card="body"', index)
        self.assertIn('data-card="memory"', index)
        self.assertIn('data-card="drift"', index)
        self.assertIn('data-card="space"', index)
        self.assertIn("身体感", index)
        self.assertIn("记忆", index)
        self.assertIn("人格漂移", index)
        self.assertIn("神经网络空间感", index)
        self.assertIn("/astrbot_plugin_sylanne/observatory-status", app)
        self.assertIn("data-token-flow", index)
        self.assertIn("data-memory-space", index)
        self.assertIn("data-persona-model", index)
        self.assertIn("data-config-controls", index)
        self.assertIn("renderTokenFlow", app)
        self.assertIn("renderMemorySpace", app)
        self.assertIn("renderConfigControls", app)
        self.assertIn("border-radius: 999px", style)
        self.assertNotIn("mermaid", index.lower())
        self.assertNotIn("流程图", index)

    def test_main_sends_immediate_realtime_ack_before_llm_finishes(self):
        main = importlib.import_module("main")
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, message))

        event = SimpleNamespace(
            session_id="room:ack",
            unified_msg_origin="aiocqhttp:room:ack",
            message_str="你在吗",
        )

        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(
                context=FakeContext(),
                config={
                    "sylanne_alpha_root": tmp,
                    "sylanne_alpha_realtime_chat_enabled": True,
                },
            )

            async def slow_observe_request(*args, **kwargs):
                await asyncio.sleep(0.2)
                return {"ok": True}

            plugin.observe_request = slow_observe_request

            async def run_hook():
                await asyncio.wait_for(plugin.on_llm_request(event, None), timeout=0.05)
                pending = list(plugin._background_tasks)
                self.assertGreaterEqual(len(pending), 1)
                await asyncio.gather(*pending)

            asyncio.run(run_hook())

        self.assertEqual(sent, [])

    def test_main_wraps_event_send_streaming_to_dispatch_first_sentence(self):
        main = importlib.import_module("main")
        sent = []
        streamed = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, message))

        async def source_stream():
            yield "第一句还"
            yield "没结束。第二句开始。"

        async def send_streaming(generator, use_fallback=False):
            del use_fallback
            async for item in generator:
                streamed.append(item)

        event = SimpleNamespace(
            session_id="room:wrapped-stream",
            unified_msg_origin="aiocqhttp:room:wrapped-stream",
            message_str="开始",
            send_streaming=send_streaming,
        )

        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(
                context=FakeContext(),
                config={
                    "sylanne_alpha_root": tmp,
                    "sylanne_alpha_realtime_chat_enabled": True,
                    "sylanne_alpha_realtime_intercept_llm_response": True,
                },
            )

            async def run_stream():
                await plugin.on_llm_request(event, None)
                await event.send_streaming(source_stream())
                pending = list(plugin._background_tasks)
                if pending:
                    await asyncio.gather(*pending)

            asyncio.run(run_stream())

        self.assertEqual(sent[-1], ("aiocqhttp:room:wrapped-stream", "第一句还没结束。"))
        self.assertEqual(streamed, ["第一句还", "没结束。第二句开始。"])

    def test_main_dispatches_first_streaming_sentence_before_final_response(self):
        main = importlib.import_module("main")
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, message))

        event = SimpleNamespace(
            session_id="room:stream",
            unified_msg_origin="aiocqhttp:room:stream",
        )

        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(
                context=FakeContext(),
                config={
                    "sylanne_alpha_root": tmp,
                    "sylanne_alpha_realtime_chat_enabled": True,
                    "sylanne_alpha_realtime_intercept_llm_response": True,
                },
            )

            async def run_chunks():
                await plugin.on_llm_stream_chunk(event, SimpleNamespace(delta="第一句还"))
                self.assertFalse(sent)
                await plugin.on_llm_stream_chunk(event, SimpleNamespace(delta="没结束。第二句开始"))
                pending = list(plugin._background_tasks)
                self.assertGreaterEqual(len(pending), 1)
                await asyncio.gather(*pending)

            asyncio.run(run_chunks())

        self.assertEqual(sent, [("aiocqhttp:room:stream", "第一句还没结束。")])

    def test_main_streaming_first_sentence_prevents_final_segmented_duplicate(self):
        main = importlib.import_module("main")
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, message))

        event = SimpleNamespace(
            session_id="room:stream-dedupe",
            unified_msg_origin="aiocqhttp:room:stream-dedupe",
            stopped=False,
            stop_event=lambda: setattr(event, "stopped", True),
        )
        response = SimpleNamespace(completion_text="第一句还没结束。\n第二句随后到。\n第三句最后到。")

        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(
                context=FakeContext(),
                config={
                    "sylanne_alpha_root": tmp,
                    "sylanne_alpha_realtime_chat_enabled": True,
                    "sylanne_alpha_realtime_intercept_llm_response": True,
                },
            )

            async def run_flow():
                await plugin.on_llm_stream_chunk(event, SimpleNamespace(delta="第一句还没结束。第二句"))
                pending = list(plugin._background_tasks)
                self.assertGreaterEqual(len(pending), 1)
                await asyncio.gather(*pending)
                await plugin.on_llm_response(event, response)
                pending = list(plugin._background_tasks)
                if pending:
                    await asyncio.gather(*pending)

            asyncio.run(run_flow())

        messages = [str(message) for _, message in sent]
        self.assertEqual(messages, ["第一句还没结束。"])
        self.assertFalse(event.stopped)
        self.assertEqual(response.completion_text, "第一句还没结束。\n第二句随后到。\n第三句最后到。")

    def test_main_streaming_state_does_not_block_next_round_segmented_reply(self):
        main = importlib.import_module("main")
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, message))

        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(
                context=FakeContext(),
                config={
                    "sylanne_alpha_root": tmp,
                    "sylanne_alpha_realtime_chat_enabled": True,
                    "sylanne_alpha_realtime_intercept_llm_response": True,
                },
            )
            first_event = SimpleNamespace(
                session_id="room:stream-next",
                unified_msg_origin="aiocqhttp:room:stream-next",
                stopped=False,
                stop_event=lambda: setattr(first_event, "stopped", True),
            )
            first_response = SimpleNamespace(completion_text="第一轮首句已发。\n第一轮剩余内容。")
            second_event = SimpleNamespace(
                session_id="room:stream-next",
                unified_msg_origin="aiocqhttp:room:stream-next",
                stopped=False,
                stop_event=lambda: setattr(second_event, "stopped", True),
            )
            second_response = SimpleNamespace(completion_text="第二轮第一段。\n第二轮第二段。")

            async def run_flow():
                await plugin.on_llm_stream_chunk(first_event, SimpleNamespace(delta="第一轮首句已发。"))
                pending = list(plugin._background_tasks)
                if pending:
                    await asyncio.gather(*pending)
                await plugin.on_llm_response(first_event, first_response)
                pending = list(plugin._background_tasks)
                if pending:
                    await asyncio.gather(*pending)
                await plugin.on_llm_response(second_event, second_response)
                pending = list(plugin._background_tasks)
                if pending:
                    await asyncio.gather(*pending)

            asyncio.run(run_flow())

        messages = [str(message) for _, message in sent]
        self.assertEqual(messages, ["第一轮首句已发。", "第二轮第一段。", "第二轮第二段。"])
        self.assertFalse(first_event.stopped)
        self.assertTrue(second_event.stopped)
        self.assertEqual(first_response.completion_text, "第一轮首句已发。\n第一轮剩余内容。")
        self.assertEqual(second_response.completion_text, "")

    def test_main_injects_current_time_context_into_llm_request(self):
        main = importlib.import_module("main")
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, message))

        event = SimpleNamespace(
            session_id="room:time",
            unified_msg_origin="aiocqhttp:room:time",
            message_str="现在几点",
        )
        request = SimpleNamespace(prompt="原始 prompt")

        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(
                context=FakeContext(),
                config={
                    "sylanne_alpha_root": tmp,
                    "sylanne_alpha_realtime_chat_enabled": True,
                },
            )

            async def run_hook():
                await plugin.on_llm_request(event, request)
                pending = list(plugin._background_tasks)
                if pending:
                    await asyncio.gather(*pending)

            asyncio.run(run_hook())

        self.assertIn("当前本地时间", request.prompt)
        self.assertIn("当前日期", request.prompt)
        self.assertIn("星期", request.prompt)
        self.assertIn("时区", request.prompt)
        self.assertIn("[sylanne_relational_time]", request.prompt)
        self.assertIn("time_gap=first_event", request.prompt)
        suffix = request.prompt.split("[sylanne_relational_time]", 1)[1]
        self.assertNotIn("现在几点", suffix.split("\n", 1)[0])

    def test_main_injects_alpha_relational_time_gap_into_next_llm_request(self):
        main = importlib.import_module("main")
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, message))

        event = SimpleNamespace(
            session_id="room:time-gap",
            unified_msg_origin="aiocqhttp:room:time-gap",
            message_str="第二轮",
        )
        request = SimpleNamespace(prompt="原始 prompt")

        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(
                context=FakeContext(),
                config={
                    "sylanne_alpha_root": tmp,
                    "sylanne_alpha_realtime_chat_enabled": True,
                },
            )

            async def run_hook():
                await plugin.observe_request("room:time-gap", text="第一轮", confidence=0.6, flags=["safe"], now=10.0)
                await plugin.on_llm_request(event, request)
                pending = list(plugin._background_tasks)
                if pending:
                    await asyncio.gather(*pending)

            asyncio.run(run_hook())

        self.assertIn("[sylanne_relational_time]", request.prompt)
        self.assertNotIn("time_gap=first_event", request.prompt)
        self.assertIn("day_relation=", request.prompt)

    def test_main_injects_unfinished_stream_context_into_next_llm_request(self):
        main = importlib.import_module("main")
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, message))

        event = SimpleNamespace(
            session_id="room:unfinished",
            unified_msg_origin="aiocqhttp:room:unfinished",
            message_str="新的问题",
        )
        request = SimpleNamespace(prompt="原始 prompt")
        response = SimpleNamespace(completion_text="第一句已经说出。\n第二句还没有说。\n第三句也没说。")

        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(
                context=FakeContext(),
                config={
                    "sylanne_alpha_root": tmp,
                    "sylanne_alpha_realtime_chat_enabled": True,
                    "sylanne_alpha_realtime_intercept_llm_response": True,
                },
            )

            async def run_flow():
                await plugin.on_llm_stream_chunk(event, SimpleNamespace(delta="第一句已经说出。"))
                pending = list(plugin._background_tasks)
                if pending:
                    await asyncio.gather(*pending)
                await plugin.on_llm_response(event, response)
                await plugin.on_llm_request(event, request)
                pending = list(plugin._background_tasks)
                if pending:
                    await asyncio.gather(*pending)

            asyncio.run(run_flow())

        self.assertIn("上一轮回复没有说完", request.prompt)
        self.assertIn("第二句还没有说。", request.prompt)
        self.assertIn("第三句也没说。", request.prompt)
        self.assertNotIn("我接住这个", request.prompt)
        self.assertNotIn("刚才那句我没说完", request.prompt)

    def test_main_caps_llm_request_prompt_context_when_existing_prompt_is_huge(self):
        main = importlib.import_module("main")
        huge = "历史上下文" * 250000
        request = SimpleNamespace(prompt=huge)
        event = SimpleNamespace(
            session_id="room:prompt-cap",
            unified_msg_origin="aiocqhttp:room:prompt-cap",
            message_str="继续",
        )

        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(
                context=SimpleNamespace(),
                config={
                    "sylanne_alpha_root": tmp,
                    "sylanne_alpha_realtime_chat_enabled": True,
                },
            )

            async def run_hook():
                await plugin.on_llm_request(event, request)
                pending = list(plugin._background_tasks)
                if pending:
                    await asyncio.gather(*pending)

            asyncio.run(run_hook())

        self.assertLessEqual(len(request.prompt), 12000)
        self.assertIn("[sylanne_prompt_context_trimmed]", request.prompt)
        self.assertIn("当前本地时间", request.prompt)
        self.assertIn("[sylanne_relational_time]", request.prompt)

    def test_main_preserves_locked_persona_prompt_when_payload_is_capped(self):
        main = importlib.import_module("main")
        locked = "锁死人格区：这里的每个字都不能被 Sylanne 改写、重排或裁剪。" + "原文" * 5000
        huge = "外层运行上下文" * 300000
        request = SimpleNamespace(
            system_prompt=locked,
            prompt="当前输入",
            contexts=[{"role": "user", "content": huge}],
            extra_user_content_parts=[SimpleNamespace(text=huge)],
        )
        plugin = main.EmotionalStatePlugin(
            context=SimpleNamespace(),
            config={"sylanne_alpha_locked_persona_prompt": locked},
        )

        plugin._cap_llm_request_payload(request)

        self.assertEqual(request.system_prompt, locked)
        self.assertEqual(request.prompt, "当前输入")
        serialized = json.dumps(request.__dict__, ensure_ascii=False, default=str)
        self.assertLessEqual(len(serialized), 60000)
        self.assertIn("[sylanne_payload_context_trimmed]", serialized)

    def test_main_caps_full_llm_request_payload_when_contexts_are_huge(self):
        main = importlib.import_module("main")
        huge = "图片上下文" * 300000
        request = SimpleNamespace(
            prompt="原始 prompt",
            contexts=[
                {"role": "user", "content": "第一条关键上下文"},
                {"role": "user", "content": huge},
                SimpleNamespace(role="assistant", content=huge),
                "tail context",
            ],
            extra_user_content_parts=[
                {"type": "text", "text": huge},
                SimpleNamespace(text=huge),
            ],
            messages=[
                {"role": "user", "content": "第一条关键用户消息"},
                {"role": "system", "content": "旧系统上下文"},
                {"role": "user", "content": huge},
                SimpleNamespace(role="assistant", content=huge),
                {"role": "user", "content": "tail context"},
            ],
        )
        event = SimpleNamespace(
            session_id="room:full-payload-cap",
            unified_msg_origin="aiocqhttp:room:full-payload-cap",
            message_str="看图继续",
        )

        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(
                context=SimpleNamespace(),
                config={
                    "sylanne_alpha_root": tmp,
                    "sylanne_alpha_realtime_chat_enabled": True,
                },
            )

            async def run_hook():
                await plugin.on_llm_request(event, request)
                pending = list(plugin._background_tasks)
                if pending:
                    await asyncio.gather(*pending)

            asyncio.run(run_hook())

        serialized = json.dumps(request.__dict__, ensure_ascii=False, default=str)
        self.assertIn("第一条关键上下文", serialized)
        self.assertIn("第一条关键用户消息", serialized)
        self.assertGreaterEqual(len(request.messages), 1)
        self.assertIn("第一条关键上下文", json.dumps(request.contexts, ensure_ascii=False, default=str))
        self.assertIn("第一条关键用户消息", json.dumps(request.messages, ensure_ascii=False, default=str))
        self.assertIn("当前本地时间", request.prompt)

    def test_main_payload_marker_handles_pydantic_like_text_part_without_empty_constructor(self):
        main = importlib.import_module("main")

        class StrictTextPart:
            def __init__(self, text=None):
                if text is None:
                    raise ValueError("text required")
                self.text = text

        plugin = main.EmotionalStatePlugin(context=SimpleNamespace(), config={})
        value = [StrictTextPart("head"), StrictTextPart("middle"), StrictTextPart("tail")]

        trimmed = plugin._trim_payload_list(value, keep_items=2, text_limit=10)

        self.assertEqual(trimmed[0].text, "head")
        self.assertEqual(trimmed[1].text, "[sylanne_payload_context_trimmed]")
        self.assertEqual(trimmed[2].text, "tail")

    def test_claude_mode_does_not_append_textpart_or_system_role_markers(self):
        main = importlib.import_module("main")
        request = SimpleNamespace(
            prompt="hello",
            system_prompt="system",
            extra_user_content_parts=[],
            contexts=[
                {"role": "user", "content": "head"},
                {"role": "user", "content": "middle" * 1000},
                {"role": "assistant", "content": "tail"},
            ],
        )
        plugin = main.EmotionalStatePlugin(context=SimpleNamespace(), config={})
        budget = plugin._state_injection_budget_for_request(
            "s-claude-plain-prompt",
            request,
            model_hint="anthropic/claude-sonnet-4-6",
        )

        plugin._append_temp_text_part(request, "context", source="current_time", budget=budget)
        plugin._normalize_claude_request_payload(request, budget=budget)
        plugin._cap_llm_request_payload(request)

        self.assertEqual(request.extra_user_content_parts, [])
        self.assertIn("[claude_advisory_context]", request.prompt)
        self.assertNotIn("'role': 'system'", str(request.contexts))

    def test_claude_mode_flattens_astrbot_parts_and_sanitizes_message_roles(self):
        main = importlib.import_module("main")
        request = SimpleNamespace(
            prompt="原始输入",
            system_prompt="system",
            extra_user_content_parts=[SimpleNamespace(text="临时旁注")],
            contents=[{"type": "text", "text": "内容块"}],
            messages=[
                {"role": "system", "content": "系统历史"},
                {"role": "tool", "content": "工具结果"},
                {"role": "assistant", "content": "助手历史"},
                SimpleNamespace(role="user", content=[{"type": "text", "text": "用户历史"}]),
            ],
            contexts=[SimpleNamespace(role="system", content="系统上下文")],
        )
        plugin = main.EmotionalStatePlugin(context=SimpleNamespace(), config={})

        plugin._normalize_claude_request_payload(request)

        self.assertEqual(request.extra_user_content_parts, [])
        self.assertEqual(request.contents, [])
        self.assertIn("临时旁注", request.prompt)
        self.assertIn("内容块", request.prompt)
        self.assertEqual([item["role"] for item in request.messages], ["user", "assistant", "user"])
        self.assertIn("系统历史", request.system_prompt)
        self.assertEqual(request.contexts, [])
        self.assertIn("系统上下文", request.system_prompt)

    def test_hajide_compat_mode_prunes_sylanne_tools_and_nested_choices(self):
        main = importlib.import_module("main")
        request = SimpleNamespace(
            prompt="查一下状态",
            tools=[
                {"type": "function", "function": {"name": "query_agent_state"}},
                {"type": "function", "function": {"name": "search_web"}},
            ],
            functions=[{"name": "get_bot_emotion_state"}],
            tool_choice={"type": "function", "function": {"name": "query_agent_state"}},
            function_call={"name": "get_bot_emotion_state"},
            params={
                "extra_body": {
                    "tools": [
                        {"type": "function", "function": {"name": "get_bot_integrated_self_state"}},
                        {"type": "function", "function": {"name": "foreign_lookup"}},
                    ],
                    "tool_choice": {"type": "function", "function": {"name": "get_bot_integrated_self_state"}},
                },
            },
            metadata={
                "tool_choice": {"type": "function", "function": {"name": "get_bot_emotion_state"}},
            },
            provider_settings={
                "function_call": {"name": "query_agent_state"},
            },
        )
        plugin = main.EmotionalStatePlugin(
            context=SimpleNamespace(),
            config={"sylanne_alpha_hajide_compat_mode": True},
        )
        budget = plugin._state_injection_budget_for_request(
            "s-claude-tools",
            request,
            model_hint="anthropic/claude-opus-4-7",
        )

        plugin._normalize_claude_request_payload(request, budget=budget)

        self.assertEqual([item["function"]["name"] for item in request.tools], ["search_web"])
        self.assertEqual(request.functions, [])
        self.assertEqual(request.tool_choice, "auto")
        self.assertEqual(request.function_call, "auto")
        self.assertEqual([item["function"]["name"] for item in request.params["extra_body"]["tools"]], ["foreign_lookup"])
        self.assertEqual(request.params["extra_body"]["tool_choice"], "auto")
        self.assertEqual(request.metadata["tool_choice"], "auto")
        self.assertEqual(request.provider_settings["function_call"], "auto")
        self.assertIn(
            "sylanne_llm_tools",
            {item.get("source") for item in budget.skipped},
        )

    def test_hajide_compat_mode_clears_tool_history_from_messages(self):
        main = importlib.import_module("main")
        request = SimpleNamespace(
            prompt="继续",
            messages=[
                {"role": "tool", "content": "工具结果", "tool_call_id": "call-1"},
                {"role": "assistant", "content": "助手历史", "tool_calls": [{"id": "call-1"}]},
                {"role": "user", "content": "用户历史"},
            ],
            contexts=[{"role": "function", "content": "函数结果"}],
        )
        plugin = main.EmotionalStatePlugin(
            context=SimpleNamespace(),
            config={"sylanne_alpha_hajide_compat_mode": True},
        )

        plugin._normalize_claude_request_payload(request)

        self.assertEqual(request.messages, [{"role": "user", "content": "用户历史"}])
        self.assertEqual(request.contexts, [])

    def test_hajide_compat_mode_disables_func_tool_on_request(self):
        main = importlib.import_module("main")

        class FakeToolSet:
            def empty(self):
                return False

            def names(self):
                return ["query_agent_state"]

        request = SimpleNamespace(
            prompt="查一下状态",
            extra_user_content_parts=[],
            contexts=[],
            func_tool=FakeToolSet(),
            tool_choice="required",
        )
        plugin = main.EmotionalStatePlugin(
            context=SimpleNamespace(),
            config={"sylanne_alpha_hajide_compat_mode": True},
        )
        budget = plugin._state_injection_budget_for_request(
            "s-claude-func-tool",
            request,
            model_hint="anthropic/claude-opus-4-7",
        )

        plugin._normalize_claude_request_payload(request, budget=budget)

        self.assertIsNone(request.func_tool)
        self.assertEqual(request.tool_choice, "auto")
        self.assertIn(
            "sylanne_func_tool",
            {item.get("source") for item in budget.skipped},
        )

    def test_hajide_compat_mode_disables_func_tool_without_names_api(self):
        main = importlib.import_module("main")

        class FakeToolSet:
            funcs = {"query_agent_state": object()}

            def empty(self):
                return False

        request = SimpleNamespace(
            prompt="查一下状态",
            extra_user_content_parts=[],
            contexts=[],
            func_tool=FakeToolSet(),
            tool_choice="required",
        )
        plugin = main.EmotionalStatePlugin(
            context=SimpleNamespace(),
            config={"sylanne_alpha_hajide_compat_mode": True},
        )
        budget = plugin._state_injection_budget_for_request(
            "s-claude-func-tool-fallback",
            request,
            model_hint="哈基德/claude-opus-4-7",
        )

        plugin._normalize_claude_request_payload(request, budget=budget)

        self.assertIsNone(request.func_tool)
        self.assertEqual(request.tool_choice, "auto")
        self.assertEqual(budget.compat_mode, "claude_agent_owned_context")

    def test_hajide_compat_on_llm_request_disables_func_tool_when_agent_owned(self):
        main = importlib.import_module("main")

        class FakeToolSet:
            funcs = {"query_agent_state": object()}

            def empty(self):
                return False

        request = SimpleNamespace(
            prompt="查一下状态",
            extra_user_content_parts=[],
            contexts=[],
            func_tool=FakeToolSet(),
            tool_choice="required",
        )
        event = SimpleNamespace(session_id="room:claude-hook", message_str="查一下状态")
        class FakeContext:
            async def get_current_chat_provider_id(self, **kwargs):
                return "哈基德/claude-opus-4-7"

        plugin = main.EmotionalStatePlugin(
            context=FakeContext(),
            config={
                "sylanne_alpha_hajide_compat_mode": True,
                "sylanne_alpha_realtime_chat_enabled": True,
            },
        )

        asyncio.run(plugin.on_llm_request(event, request))

        self.assertIsNone(request.func_tool)
        self.assertEqual(request.tool_choice, "auto")
        diagnostics = asyncio.run(plugin.get_agent_runtime_diagnostics(event))
        self.assertEqual(diagnostics["state_injection"]["compat_mode"], "claude_agent_owned_context")
        self.assertIn("sylanne_func_tool", {item.get("source") for item in diagnostics["state_injection"]["skipped"]})

    def test_claude_agent_owned_context_skips_all_extra_temp_parts(self):
        main = importlib.import_module("main")
        request = SimpleNamespace(prompt="继续", extra_user_content_parts=[])
        plugin = main.EmotionalStatePlugin(
            context=SimpleNamespace(),
            config={"sylanne_alpha_hajide_compat_mode": True},
        )
        budget = plugin._state_injection_budget_for_request(
            "s-claude-agent-owned",
            request,
            model_hint="anthropic/claude-opus-4-7",
        )
        budget.compat_mode = "claude_agent_owned_context"

        appended = plugin._append_temp_text_part(request, "[sylanne_context]状态", source="state", budget=budget)

        self.assertFalse(appended)
        self.assertEqual(request.extra_user_content_parts, [])
        self.assertEqual(request.prompt, "继续")
        self.assertIn("state", {item.get("source") for item in budget.skipped})

    def test_main_caps_unfinished_reply_context_before_prompt_injection(self):
        main = importlib.import_module("main")
        request = SimpleNamespace(prompt="原始 prompt")
        event = SimpleNamespace(
            session_id="room:unfinished-cap",
            unified_msg_origin="aiocqhttp:room:unfinished-cap",
            message_str="继续",
        )

        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(
                context=SimpleNamespace(),
                config={
                    "sylanne_alpha_root": tmp,
                    "sylanne_alpha_realtime_chat_enabled": True,
                },
            )
            plugin._unfinished_replies["room:unfinished-cap"] = "未完成内容" * 8000

            async def run_hook():
                await plugin.on_llm_request(event, request)
                pending = list(plugin._background_tasks)
                if pending:
                    await asyncio.gather(*pending)

            asyncio.run(run_hook())

        self.assertLessEqual(len(request.prompt), 12000)
        self.assertIn("上一轮回复没有说完", request.prompt)
        self.assertIn("[sylanne_trimmed_fragment]", request.prompt)

    def test_main_local_long_run_smoke_keeps_visible_output_clean_and_state_persistent(self):
        main = importlib.import_module("main")
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, str(message)))

        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(
                context=FakeContext(),
                config={
                    "sylanne_alpha_root": tmp,
                    "sylanne_alpha_realtime_chat_enabled": True,
                    "sylanne_alpha_realtime_intercept_llm_response": True,
                },
            )
            event = SimpleNamespace(
                session_id="room:longrun",
                unified_msg_origin="aiocqhttp:room:longrun",
                message_str="长跑第一轮",
                stopped=False,
                stop_event=lambda: setattr(event, "stopped", True),
            )
            response = SimpleNamespace(completion_text="第一段先说。\n第二段继续。")
            request = SimpleNamespace(prompt="base")

            async def run_flow():
                await plugin.on_llm_request(event, request)
                await plugin.on_llm_response(event, response)
                await plugin.on_llm_response(event, response)
                pending = list(plugin._background_tasks)
                if pending:
                    await asyncio.gather(*pending)
                observatory = await plugin.sylanne_observatory(session_key="room:longrun")
                restored = main.EmotionalStatePlugin(context=FakeContext(), config={"sylanne_alpha_root": tmp})
                memory = await restored.query_sylanne_memory(session_key="room:longrun", query="第一段")
                return observatory, memory

            observatory, memory = asyncio.run(run_flow())

        visible = "\n".join(message for _, message in sent)
        self.assertEqual(response.completion_text, "")
        self.assertTrue(event.stopped)
        self.assertEqual(visible.count("第一段先说。"), 1)
        self.assertNotIn("sylanne_realtime_delivery_status", visible)
        self.assertNotIn("delivery_status=", visible)
        self.assertNotIn("sylanne_realtime_delivery_status", response.completion_text)
        self.assertNotIn("delivery_status=", response.completion_text)
        self.assertTrue(observatory["read_only"])
        self.assertEqual(observatory["cards"][0]["id"], "body")
        self.assertTrue(memory["matches"])

    def test_main_intercepts_llm_response_into_realtime_parts_when_enabled(self):
        main = importlib.import_module("main")
        sent = []

        class FakeContext:
            async def send_message(self, origin, message):
                await asyncio.sleep(0.01)
                sent.append((origin, message))

        event = SimpleNamespace(
            session_id="room:segments",
            unified_msg_origin="aiocqhttp:room:segments",
            platform_name="aiocqhttp",
            stopped=False,
            stop_event=lambda: setattr(event, "stopped", True),
            get_event_origin=lambda: "origin:segments",
        )
        response = SimpleNamespace(completion_text="第一段先说。\n第二段单独说。第三段也要拆开。")

        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(
                context=FakeContext(),
                config={
                    "sylanne_alpha_root": tmp,
                    "sylanne_alpha_realtime_chat_enabled": True,
                    "sylanne_alpha_realtime_intercept_llm_response": True,
                },
            )

            async def run_hook():
                await plugin.on_llm_response(event, response)
                pending = list(plugin._background_tasks)
                self.assertGreaterEqual(len(pending), 1)
                await asyncio.gather(*pending)

            asyncio.run(run_hook())
            diagnostics = asyncio.run(plugin.sylanne_diagnostics(session_key="room:segments"))

        self.assertEqual(response.completion_text, "")
        self.assertTrue(event.stopped)
        self.assertGreaterEqual(len(sent), 2)
        self.assertEqual(sent[0][0], "aiocqhttp:room:segments")
        self.assertIn("第一段先说。", str(sent[0][1]))
        self.assertTrue(all("\n" not in str(message) for _, message in sent))
        self.assertGreaterEqual(diagnostics["turns"], 1)

    def test_main_schedules_response_observation_off_realtime_response_hot_path(self):
        main = importlib.import_module("main")
        sent = []
        observed = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, message))

        event = SimpleNamespace(
            session_id="room:hot-path",
            unified_msg_origin="aiocqhttp:room:hot-path",
            stopped=False,
            stop_event=lambda: setattr(event, "stopped", True),
        )
        response = SimpleNamespace(completion_text="第一段先说。\n第二段继续说。")

        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(
                context=FakeContext(),
                config={
                    "sylanne_alpha_root": tmp,
                    "sylanne_alpha_realtime_chat_enabled": True,
                    "sylanne_alpha_realtime_intercept_llm_response": True,
                },
            )

            async def slow_observe_response(*args, **kwargs):
                await asyncio.sleep(0.2)
                observed.append((args, kwargs))
                return {"ok": True}

            plugin.observe_response = slow_observe_response

            async def run_hook():
                await asyncio.wait_for(plugin.on_llm_response(event, response), timeout=0.05)
                self.assertEqual(response.completion_text, "")
                self.assertTrue(event.stopped)
                self.assertFalse(observed)
                pending = list(plugin._background_tasks)
                self.assertGreaterEqual(len(pending), 2)
                await asyncio.gather(*pending)

            asyncio.run(run_hook())

        self.assertTrue(sent)
        self.assertEqual(sent[0][0], "aiocqhttp:room:hot-path")
        self.assertTrue(observed)

    def test_astrbot_message_prefers_plain_component_chain_for_text(self):
        main = importlib.import_module("main")
        import types

        class Plain:
            def __init__(self, text):
                self.text = text

        class StrictMessageChain:
            def __init__(self):
                self.parts = []

            def message(self, text):
                self.parts.append(("message", text))
                return self

            def append(self, part):
                self.parts.append(part)
                return self

        component_module = types.ModuleType("astrbot.api.message_components")
        component_module.Plain = Plain
        sys.modules["astrbot.api.message_components"] = component_module
        event_module = sys.modules.get("astrbot.api.event")
        old_chain = getattr(event_module, "MessageChain", None) if event_module else None
        if event_module is None:
            event_module = types.ModuleType("astrbot.api.event")
            sys.modules["astrbot.api.event"] = event_module
        event_module.MessageChain = StrictMessageChain
        try:
            message = main.EmotionalStatePlugin(context=SimpleNamespace(), config={})._astrbot_message("不要空发")
        finally:
            sys.modules.pop("astrbot.api.message_components", None)
            if old_chain is not None:
                event_module.MessageChain = old_chain
            else:
                delattr(event_module, "MessageChain")

        self.assertEqual(len(message.parts), 1)
        self.assertIsInstance(message.parts[0], Plain)
        self.assertEqual(message.parts[0].text, "不要空发")

    def test_text_extracts_qq_forward_and_json_link_components_from_message_chain(self):
        main = importlib.import_module("main")
        plugin = main.EmotionalStatePlugin(context=SimpleNamespace(), config={})
        event = SimpleNamespace(
            message_str="",
            message_chain=[
                SimpleNamespace(type="Plain", text="帮我看这个："),
                SimpleNamespace(type="Forward", nodes=[
                    {"sender": "小明", "content": "第一条转发内容"},
                    SimpleNamespace(name="小红", message=[SimpleNamespace(text="第二条转发内容")]),
                ]),
                SimpleNamespace(type="Json", data={"meta": {"news": {"title": "转发连接标题", "desc": "连接摘要"}}, "prompt": "[分享]"}),
            ],
        )

        extracted = plugin._text(event)

        self.assertIn("帮我看这个", extracted)
        self.assertIn("第一条转发内容", extracted)
        self.assertIn("第二条转发内容", extracted)
        self.assertIn("转发连接标题", extracted)
        self.assertIn("连接摘要", extracted)

    def test_dispatch_segmented_parts_keeps_human_delay_and_payload_text(self):
        main = importlib.import_module("main")
        sent = []
        sleeps = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, message))

        async def fake_sleep(delay):
            sleeps.append(delay)

        plugin = main.EmotionalStatePlugin(context=FakeContext(), config={})
        old_sleep = main.asyncio.sleep
        main.asyncio.sleep = fake_sleep
        try:
            asyncio.run(plugin._dispatch_segmented_parts("aiocqhttp:room:send", [{"index": 0, "text": "慢一点。", "delay_before_seconds": 3.2}]))
        finally:
            main.asyncio.sleep = old_sleep

        self.assertEqual(sleeps, [3.2])
        self.assertEqual(sent, [("aiocqhttp:room:send", "慢一点。")])

    def test_main_cancels_stale_segmented_reply_when_new_user_request_arrives(self):
        main = importlib.import_module("main")
        sent = []
        sleeps = []

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, message))

        event = SimpleNamespace(
            session_id="room:stale-segments",
            unified_msg_origin="aiocqhttp:room:stale-segments",
            message_str="新的输入",
            stopped=False,
            stop_event=lambda: setattr(event, "stopped", True),
        )
        response = SimpleNamespace(completion_text="第一段马上发。\n第二段很久后才发。")

        async def fake_sleep(delay):
            sleeps.append(delay)
            await original_sleep(0)

        with tempfile.TemporaryDirectory() as tmp:
            plugin = main.EmotionalStatePlugin(
                context=FakeContext(),
                config={
                    "sylanne_alpha_root": tmp,
                    "sylanne_alpha_realtime_chat_enabled": True,
                    "sylanne_alpha_realtime_intercept_llm_response": True,
                },
            )
            original_sleep = main.asyncio.sleep
            main.asyncio.sleep = fake_sleep
            try:
                async def run_flow():
                    await plugin.on_llm_response(event, response)
                    await original_sleep(0)
                    await plugin.on_llm_request(event, SimpleNamespace(prompt="base"))
                    pending = list(plugin._background_tasks)
                    if pending:
                        await asyncio.gather(*pending, return_exceptions=True)

                asyncio.run(run_flow())
            finally:
                main.asyncio.sleep = original_sleep

        self.assertEqual([message for _, message in sent], ["第一段马上发。"])
        self.assertTrue(sleeps)

    def test_dispatch_segmented_parts_sends_visible_message_chain_when_astrbot_components_exist(self):
        main = importlib.import_module("main")
        import types

        sent = []

        class Plain:
            def __init__(self, text):
                self.text = text

        class RealisticMessageChain:
            def __init__(self):
                self.chain = []

            def message(self, text):
                self.chain.append(("legacy_message", text))
                return self

            def __str__(self):
                return "".join(getattr(part, "text", "") for part in self.chain)

        class FakeContext:
            async def send_message(self, origin, message):
                sent.append((origin, message))

        component_module = types.ModuleType("astrbot.api.message_components")
        component_module.Plain = Plain
        sys.modules["astrbot.api.message_components"] = component_module
        event_module = sys.modules.get("astrbot.api.event")
        old_chain = getattr(event_module, "MessageChain", None) if event_module else None
        if event_module is None:
            event_module = types.ModuleType("astrbot.api.event")
            sys.modules["astrbot.api.event"] = event_module
        event_module.MessageChain = RealisticMessageChain
        try:
            asyncio.run(main.EmotionalStatePlugin(context=FakeContext(), config={})._dispatch_segmented_parts("aiocqhttp:room:visible", [{"index": 0, "text": "不要空发。", "delay_before_seconds": 0.0}]))
        finally:
            sys.modules.pop("astrbot.api.message_components", None)
            if old_chain is not None:
                event_module.MessageChain = old_chain
            else:
                delattr(event_module, "MessageChain")

        self.assertEqual(sent[0][0], "aiocqhttp:room:visible")
        self.assertEqual(str(sent[0][1]), "不要空发。")
        self.assertEqual(sent[0][1].chain[0].text, "不要空发。")

    def test_realtime_plan_prefers_word_boundary_when_splitting_ascii_text(self):
        main = importlib.import_module("main")
        text = "什么 posture steady 还有 contact need has accumulated 这些内部词不该被硬切开"
        plan = asyncio.run(main.EmotionalStatePlugin(context=SimpleNamespace(), config={}).get_realtime_chat_plan("room:words", text))
        parts = [part["text"] for part in plan["message_parts"]]

        self.assertNotIn("cont", parts)
        self.assertNotIn("act need has accumulated", parts)
        self.assertNotIn("posture=", "\n".join(parts))

    def test_realtime_plan_splits_chinese_reply_on_semantic_boundaries(self):
        main = importlib.import_module("main")
        text = "额……等一下，傻瓜！我不是不想说完，只是刚才那句被截断了呢？所以现在要自然接下去，把前面的意思慢慢补完整。"
        plan = asyncio.run(main.EmotionalStatePlugin(context=SimpleNamespace(), config={}).get_realtime_chat_plan("room:semantic", text, max_part_chars=24))
        parts = [part["text"] for part in plan["message_parts"]]

        self.assertGreaterEqual(len(parts), 3)
        self.assertNotIn("呢？", parts)
        self.assertNotIn("啦！", parts)
        self.assertEqual("".join(parts), text)
        self.assertTrue(all(part[-1] in "。！？；，、,.!?;" or len(part) >= 8 for part in parts[:-1]))

    def test_realtime_plan_keeps_urls_and_ascii_tokens_whole_when_possible(self):
        main = importlib.import_module("main")
        text = "先看 https://example.com/path/to/resource?query=one，再看 posture=steady，不要把 contact_need 这种词切碎。"
        plan = asyncio.run(main.EmotionalStatePlugin(context=SimpleNamespace(), config={}).get_realtime_chat_plan("room:url", text, max_part_chars=32))
        parts = [part["text"] for part in plan["message_parts"]]
        joined = "\n".join(parts)

        self.assertIn("https://example.com/path/to/resource?query=one", joined)
        self.assertIn("posture=steady", joined)
        self.assertIn("contact_need", joined)
        self.assertFalse(any(part in {"https://example.com/path/to", "resource?query=one", "posture=", "contact_"} for part in parts))

    def test_realtime_plan_keeps_total_typing_delay_under_human_visible_budget(self):
        main = importlib.import_module("main")
        text = "。".join(["这是一段需要切分发送的长回复" for _ in range(24)])
        plan = asyncio.run(main.EmotionalStatePlugin(context=SimpleNamespace(), config={}).get_realtime_chat_plan("room:delay", text))
        total_delay = sum(float(part["delay_before_seconds"]) for part in plan["message_parts"])

        self.assertGreaterEqual(plan["message_count"], 8)
        self.assertLessEqual(total_delay, 36.0)
        self.assertGreaterEqual(max(part["delay_before_seconds"] for part in plan["message_parts"]), 3.0)
        self.assertGreaterEqual(
            sum(1 for part in plan["message_parts"] if float(part["delay_before_seconds"]) >= 2.4),
            3,
        )

    def test_realtime_plan_filters_draft_notes_before_segmenting(self):
        main = importlib.import_module("main")
        text = "<draft_notes>\n先整理思路，不该发出去。\n</draft_notes>\n在想什么呢傻瓜 🤔"
        plan = asyncio.run(main.EmotionalStatePlugin(context=SimpleNamespace(), config={}).get_realtime_chat_plan("room:draft-notes", text))
        parts = [part["text"] for part in plan["message_parts"]]

        self.assertEqual(parts, ["在想什么呢傻瓜 🤔"])
        self.assertNotIn("draft_notes", "\n".join(parts))

    def test_realtime_plan_filters_thinking_blocks_before_segmenting(self):
        main = importlib.import_module("main")
        text = "<thinking>\ninternal reasoning should not be sent\n</thinking>\n可以了，刚才是在测试。"
        plan = asyncio.run(main.EmotionalStatePlugin(context=SimpleNamespace(), config={}).get_realtime_chat_plan("room:thinking", text))
        parts = [part["text"] for part in plan["message_parts"]]

        self.assertEqual(parts, ["可以了，刚才是在测试。"])
        self.assertNotIn("thinking", "\n".join(parts).lower())
        self.assertNotIn("internal reasoning", "\n".join(parts))

    def test_main_filters_hidden_thinking_from_single_raw_response(self):
        main = importlib.import_module("main")
        event = SimpleNamespace(
            session_id="room:raw-thinking",
            unified_msg_origin="aiocqhttp:room:raw-thinking",
        )
        response = SimpleNamespace(
            completion_text="<thinking>\ninternal reasoning should not be sent\n</thinking>\n好，搞定就好。"
        )
        plugin = main.EmotionalStatePlugin(
            context=SimpleNamespace(send_message=lambda *args, **kwargs: None),
            config={"sylanne_alpha_realtime_chat_enabled": True},
        )

        asyncio.run(plugin.on_llm_response(event, response))

        self.assertEqual(response.completion_text, "好，搞定就好。")
        self.assertNotIn("thinking", response.completion_text.lower())
        self.assertNotIn("internal reasoning", response.completion_text)

    def test_realtime_plan_filters_inline_draft_notes_before_segmenting(self):
        main = importlib.import_module("main")
        text = "<DRAFT_NOTES>这个是模型草稿。</DRAFT_NOTES>\n真正要发的话在这里。"
        plan = asyncio.run(main.EmotionalStatePlugin(context=SimpleNamespace(), config={}).get_realtime_chat_plan("room:inline-draft", text))
        parts = [part["text"] for part in plan["message_parts"]]

        self.assertEqual(parts, ["真正要发的话在这里。"])
        self.assertNotIn("DRAFT_NOTES", "\n".join(parts))

    def test_get_emotional_state_plugin_returns_registered_alpha_plugin(self):
        main = importlib.import_module("main")
        context = SimpleNamespace(star_context={main.PLUGIN_NAME: "plugin"})

        self.assertEqual(main.get_emotional_state_plugin(context), "plugin")


if __name__ == "__main__":
    unittest.main()
