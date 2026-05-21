from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sylanne_alpha import AlphaKernel, AlphaKernelEvent
from sylanne_alpha.body import AlphaBodyState
from sylanne_alpha.runtime import AlphaRuntime


class SylanneAlphaKernelTests(unittest.TestCase):
    def test_alpha_package_contains_only_direct_body_structure(self):
        alpha_root = Path(__file__).resolve().parents[1] / "sylanne_alpha"
        modules = {path.name for path in alpha_root.glob("*.py")}

        self.assertEqual(
            modules,
            {
                "__init__.py",
                "assessor.py",
                "assessor_async.py",
                "attention.py",
                "autopoiesis.py",
                "body.py",
                "codec.py",
                "computation_spine.py",
                "config.py",
                "dialogue.py",
                "embedding_memory.py",
                "hdc.py",
                "hgt.py",
                "host.py",
                "importer.py",
                "kernel.py",
                "life_simulation.py",
                "multi_user.py",
                "personality.py",
                "phase_transition.py",
                "predictive_coding.py",
                "prompt_surface.py",
                "rhythm_learner.py",
                "runtime.py",
                "scar_algebra.py",
                "shadow_memory.py",
                "vector.py",
                "void_calculus.py",
                "void_scar_engine.py",
                "webui.py",
                "webui_server.py",
                "workers.py",
                "workset.py",
            },
        )

    def test_body_state_vector_projects_back_to_named_organs(self):
        body = AlphaBodyState()

        before = body.state_vector()
        body.apply(text="靠近", flags=["safe"], confidence=0.7, now=1.0)
        after = body.state_vector()

        self.assertEqual(len(before), len(after))
        self.assertGreater(after["pulse.beat"], before["pulse.beat"])
        self.assertAlmostEqual(after["nerve.plasticity"], body.to_dict()["nerve"]["plasticity"])
        self.assertAlmostEqual(after["needs.need_expression"], body.to_dict()["needs"]["need_expression"])

    def test_body_vector_event_drives_batchable_linear_update(self):
        body = AlphaBodyState()

        event = body.event_vector(text="重复", flags=["hurt", "boundary"], confidence=0.4, elapsed=2.0, repetition=2)
        delta = body.vector_delta(event)
        body.apply_vector_delta(delta, now=2.0)

        snapshot = body.to_dict()
        self.assertGreater(snapshot["pulse"]["beat"], 0.0)
        self.assertGreater(snapshot["wound"]["open"], 0.0)
        self.assertGreater(snapshot["immunity"]["boundary_pressure"], 0.0)
        self.assertGreater(snapshot["nerve"]["plasticity"], 0.0)

    def test_kernel_relational_time_layer_exposes_current_time_without_previous_event(self):
        kernel = AlphaKernel.boot(session_key="time")

        surface = kernel.tick(
            AlphaKernelEvent(
                text="现在几点",
                flags=["safe"],
                confidence=0.6,
                now=1779148800.0,
                event_time={"local_datetime": "2026-05-19T00:00:00+08:00", "timezone": "Asia/Shanghai"},
            )
        )["surface"]

        relational_time = surface["host_payload"]["relational_time"]
        fragment = surface["host_payload"]["prompt_fragment"]
        self.assertEqual(relational_time["schema_version"], "sylanne.alpha.relational_time.v1")
        self.assertEqual(relational_time["current_time"]["local_datetime"], "2026-05-19T00:00:00+08:00")
        self.assertEqual(relational_time["current_time"]["timezone"], "Asia/Shanghai")
        self.assertEqual(relational_time["time_gap"]["label"], "first_event")
        self.assertEqual(relational_time["day_relation"], "first_event")
        self.assertIn("[sylanne_relational_time]", fragment)
        self.assertIn("current_time=2026-05-19T00:00:00+08:00", fragment)
        self.assertNotIn("现在几点", fragment)

    def test_kernel_relational_time_layer_tracks_gap_label_and_same_day(self):
        kernel = AlphaKernel.boot(session_key="time")
        kernel.tick(
            AlphaKernelEvent(
                text="早一点的消息",
                flags=["safe"],
                confidence=0.6,
                now=1779148800.0,
                event_time={"local_datetime": "2026-05-19T00:00:00+08:00", "timezone": "Asia/Shanghai"},
            )
        )

        surface = kernel.tick(
            AlphaKernelEvent(
                text="过一会儿再说",
                flags=["safe"],
                confidence=0.6,
                now=1779149100.0,
                event_time={"local_datetime": "2026-05-19T00:05:00+08:00", "timezone": "Asia/Shanghai"},
            )
        )["surface"]

        relational_time = surface["host_payload"]["relational_time"]
        self.assertEqual(relational_time["time_gap"]["seconds"], 300.0)
        self.assertEqual(relational_time["time_gap"]["label"], "刚刚")
        self.assertEqual(relational_time["day_relation"], "same_day")
        self.assertIn("time_gap=刚刚", surface["host_payload"]["prompt_fragment"])
        self.assertIn("day_relation=same_day", surface["host_payload"]["prompt_fragment"])

    def test_kernel_relational_time_layer_uses_event_timezone_for_cross_day(self):
        kernel = AlphaKernel.boot(session_key="time")
        kernel.tick(
            AlphaKernelEvent(
                text="昨晚",
                flags=["safe"],
                confidence=0.6,
                now=1779191700.0,
                event_time={"local_datetime": "2026-05-19T23:55:00+08:00", "timezone": "Asia/Shanghai"},
            )
        )

        surface = kernel.tick(
            AlphaKernelEvent(
                text="今天",
                flags=["safe"],
                confidence=0.6,
                now=1779192300.0,
                event_time={"local_datetime": "2026-05-20T00:05:00+08:00", "timezone": "Asia/Shanghai"},
            )
        )["surface"]

        relational_time = surface["host_payload"]["relational_time"]
        self.assertEqual(relational_time["current_time"]["timezone"], "Asia/Shanghai")
        self.assertEqual(relational_time["time_gap"]["seconds"], 600.0)
        self.assertEqual(relational_time["time_gap"]["label"], "刚刚")
        self.assertEqual(relational_time["day_relation"], "cross_day")

    def test_kernel_relational_time_layer_falls_back_to_epoch_when_local_time_missing(self):
        kernel = AlphaKernel.boot(session_key="time")
        kernel.tick(AlphaKernelEvent(text="第一轮", flags=["safe"], confidence=0.6, now=10.0))

        surface = kernel.tick(AlphaKernelEvent(text="第二轮", flags=["safe"], confidence=0.6, now=3710.0))["surface"]

        relational_time = surface["host_payload"]["relational_time"]
        self.assertEqual(relational_time["time_gap"]["seconds"], 3700.0)
        self.assertEqual(relational_time["time_gap"]["label"], "刚才")
        self.assertEqual(relational_time["day_relation"], "unknown")

    def test_kernel_relationship_memory_accumulates_structured_signals_without_prompt_raw_text(self):
        kernel = AlphaKernel.boot(session_key="memory")
        kernel.tick(AlphaKernelEvent(text="我喜欢慢一点解释", flags=["safe", "preference"], confidence=0.8, now=1.0))
        kernel.tick(AlphaKernelEvent(text="不要把我的私事往外说", flags=["safe", "boundary"], confidence=0.9, now=2.0))
        surface = kernel.tick(AlphaKernelEvent(text="这个项目我们继续推进", flags=["safe", "progress"], confidence=0.7, now=3.0))["surface"]

        relationship_memory = surface["host_payload"]["relationship_memory"]
        fragment = surface["host_payload"]["prompt_fragment"]
        self.assertEqual(relationship_memory["schema_version"], "sylanne.alpha.relationship_memory.v1")
        self.assertEqual(relationship_memory["signals"]["preference_count"], 1)
        self.assertEqual(relationship_memory["signals"]["boundary_count"], 1)
        self.assertEqual(relationship_memory["signals"]["progress_count"], 1)
        self.assertGreater(relationship_memory["continuity"]["weight"], 0.0)
        self.assertIn("[sylanne_relationship_memory]", fragment)
        self.assertIn("preference_count=1", fragment)
        self.assertIn("boundary_count=1", fragment)
        self.assertNotIn("慢一点解释", fragment)
        self.assertNotIn("私事", fragment)
        self.assertNotIn("继续推进", fragment)

    def test_kernel_alpha_life_layers_cover_drift_repair_fallibility_group_and_prompt_bus(self):
        kernel = AlphaKernel.boot(session_key="life")
        kernel.tick(AlphaKernelEvent(text="我喜欢你更直接一点", flags=["safe", "preference"], confidence=0.9, now=1.0))
        surface = kernel.tick(
            AlphaKernelEvent(
                text="刚才误会了，我修正一下；群里先慢一点",
                flags=["safe", "repair", "fallibility", "group"],
                confidence=0.8,
                now=2.0,
                values={"group_heat": 0.7},
            )
        )["surface"]

        host_payload = surface["host_payload"]
        fragment = host_payload["prompt_fragment"]
        self.assertEqual(host_payload["affect_dynamics"]["schema_version"], "sylanne.alpha.affect_dynamics.v1")
        self.assertGreater(host_payload["affect_dynamics"]["body_coupling"]["repair_drive"], 0.0)
        self.assertEqual(host_payload["personality"]["schema_version"], "sylanne.alpha.personality.v1")
        self.assertGreaterEqual(host_payload["personality"]["drift"]["events"], 2)
        self.assertEqual(host_payload["moral_repair"]["schema_version"], "sylanne.alpha.moral_repair.v1")
        self.assertEqual(host_payload["moral_repair"]["state"], "repairing")
        self.assertEqual(host_payload["fallibility"]["schema_version"], "sylanne.alpha.fallibility.v1")
        self.assertGreater(host_payload["fallibility"]["claim_caution"], 0.0)
        self.assertEqual(host_payload["group_atmosphere"]["schema_version"], "sylanne.alpha.group_atmosphere.v1")
        self.assertEqual(host_payload["group_atmosphere"]["mode"], "group")
        self.assertEqual(host_payload["prompt_context_bus"]["schema_version"], "sylanne.alpha.prompt_context_bus.v1")
        self.assertIn("integrated_self", host_payload["prompt_context_bus"]["fragments"])
        self.assertIn("[sylanne_prompt_context_bus]", fragment)
        self.assertIn("[sylanne_moral_repair]", fragment)
        self.assertIn("[sylanne_fallibility]", fragment)
        self.assertIn("[sylanne_group_atmosphere]", fragment)
        self.assertNotIn("我喜欢你更直接", fragment)
        self.assertNotIn("刚才误会", fragment)

        restored = AlphaKernel.restore(kernel.snapshot())
        restored_payload = restored.surface()["host_payload"]
        self.assertEqual(restored_payload["personality"]["drift"]["events"], host_payload["personality"]["drift"]["events"])
        self.assertEqual(restored_payload["moral_repair"]["events"], host_payload["moral_repair"]["events"])

    def test_kernel_proactive_source_is_body_relation_and_sovereignty_driven(self):
        kernel = AlphaKernel.boot(session_key="proactive-source")
        kernel.body.needs["need_contact"] = 0.5
        kernel.body.nerve.plasticity = 0.4
        kernel.body.immunity.interruption_budget = 0.8
        kernel.tick(AlphaKernelEvent(text="可以之后主动提醒我", flags=["safe", "preference"], confidence=0.9, now=1.0))
        surface = kernel.tick(AlphaKernelEvent(flags=["proactive"], confidence=0.7, now=2.0))["surface"]

        source = surface["host_payload"]["proactive_source"]
        self.assertEqual(source["schema_version"], "sylanne.alpha.proactive_source.v1")
        self.assertGreater(source["drivers"]["body_need"], 0.0)
        self.assertGreater(source["drivers"]["relationship_continuity"], 0.0)
        self.assertIn(source["decision"], {"eligible", "blocked"})
        self.assertIn("current_user_sovereignty_first", source["constraints"])
        self.assertNotIn("可以之后主动提醒我", surface["host_payload"]["prompt_fragment"])

    def test_kernel_integrated_self_arbitrates_posture_and_prompt_without_raw_text(self):
        kernel = AlphaKernel.boot(session_key="self")
        surface = kernel.tick(
            AlphaKernelEvent(
                text="帮我跑测试并修这个技术问题",
                flags=["safe", "task", "tool"],
                confidence=0.9,
                now=1.0,
                event_time={"local_datetime": "2026-05-19T10:00:00+08:00", "timezone": "Asia/Shanghai"},
            )
        )["surface"]

        integrated_self = surface["host_payload"]["integrated_self"]
        fragment = surface["host_payload"]["prompt_fragment"]
        self.assertEqual(integrated_self["schema_version"], "sylanne.alpha.integrated_self.v1")
        self.assertEqual(integrated_self["intent_plan"]["primary_goal"], "tool_task")
        self.assertEqual(integrated_self["response_posture"], "task_focused")
        self.assertIn("answer_current_request", integrated_self["allowed_actions"])
        self.assertIn("unrequested_relationship_narration", integrated_self["blocked_actions"])
        self.assertIn("current_user_text_priority", integrated_self["constraints"])
        self.assertIn("[sylanne_integrated_self]", fragment)
        self.assertIn("primary_goal=tool_task", fragment)
        self.assertNotIn("帮我跑测试", fragment)
        self.assertNotIn("我们关系", fragment)
        self.assertNotIn("你一直", fragment)

    def test_kernel_integrated_self_blocks_outward_actions_under_boundary_risk(self):
        kernel = AlphaKernel.boot(session_key="self-risk")
        kernel.body.needs["need_contact"] = 0.9
        kernel.body.immunity.boundary_pressure = 0.92
        kernel.body.immunity.sovereignty = 0.4
        kernel.last_event = {"flags": ["proactive"], "text": ""}

        surface = kernel.surface()
        integrated_self = surface["host_payload"]["integrated_self"]

        self.assertEqual(integrated_self["response_posture"], "boundary_guarded")
        self.assertIn("reach_out", integrated_self["blocked_actions"])
        self.assertIn("proactive_speech", integrated_self["blocked_actions"])
        self.assertNotIn("reach_out", integrated_self["allowed_actions"])
        self.assertGreaterEqual(integrated_self["risk"]["safety_priority"], 0.8)
        self.assertIn("boundary_first", integrated_self["intent_plan"]["lanes"])

    def test_kernel_relationship_memory_persists_through_snapshot_restore(self):
        kernel = AlphaKernel.boot(session_key="memory")
        kernel.tick(AlphaKernelEvent(text="我不喜欢突然打断", flags=["safe", "preference", "boundary"], confidence=0.8, now=1.0))

        restored = AlphaKernel.restore(kernel.snapshot())
        surface = restored.surface()

        relationship_memory = surface["host_payload"]["relationship_memory"]
        self.assertEqual(relationship_memory["signals"]["preference_count"], 1)
        self.assertEqual(relationship_memory["signals"]["boundary_count"], 1)
        self.assertIn("relationship", restored.snapshot()["body"]["memory"])

        workset = surface["workset"]
        self.assertEqual(workset["schema_version"], "sylanne.alpha.workset.v1")
        self.assertEqual(workset["mode"], "blackboard")
        departments = [item["department"] for item in workset["evidence"]]
        self.assertIn("body", departments)
        self.assertIn("guard", departments)
        self.assertIn("attention", departments)
        self.assertIn(workset["coordination"]["primary_department"], departments)
        self.assertIn("pressure", workset["evidence"][-1]["summary"])
        self.assertIn("interests", workset["evidence"][-1]["summary"])
        self.assertIn("workset", surface["diagnostics"])
        self.assertNotIn("raw_fragments", workset)

    def test_body_vector_schema_invariants_and_batch_simulation(self):
        body = AlphaBodyState()
        batch = [
            body.event_vector(text="第一轮", flags=["safe"], confidence=0.6, elapsed=1.0),
            body.event_vector(text="第二轮", flags=["hurt"], confidence=0.4, elapsed=2.0),
            body.event_vector(flags=["idle"], elapsed=3.0),
        ]

        simulated = body.simulate_vectors(batch)

        self.assertEqual(set(simulated), set(body.state_vector()))
        self.assertTrue(all(0.0 <= value <= 1.0 for axis, value in simulated.items() if axis != "pulse.beat"))
        self.assertGreater(simulated["pulse.beat"], 0.0)

    def test_decision_and_guard_are_vector_risk_sovereignty_driven(self):
        kernel = AlphaKernel.boot(session_key="risk")
        kernel.body.needs["need_contact"] = 0.9
        kernel.body.wound.open = 0.9
        kernel.body.immunity.boundary_pressure = 0.9
        kernel.body.immunity.sovereignty = 0.2
        kernel.last_event = {"flags": ["proactive"]}

        decision = kernel._decide()
        guard = kernel._guard(decision)

        self.assertIn("risk_score", guard)
        self.assertFalse(guard["allowed"])
        self.assertIn("sovereignty_low", guard["flags"])

    def test_memory_recall_compresses_decays_and_uses_text_similarity_fallback(self):
        body = AlphaBodyState()
        for index in range(60):
            body.apply(text=f"共同记忆 {index}", flags=["safe"], confidence=0.5, now=float(index + 1))

        recalled = body.recall_memory("共同记忆 59", limit=3)
        body.decay_memory(0.5)
        body.compress_memory(limit=20)

        self.assertLessEqual(len(body.to_dict()["memory"]["traces"]), 20)
        self.assertLess(body.to_dict()["memory"]["traces"][-1]["weight"], recalled[0]["weight"])
        self.assertEqual(recalled[0]["text"], "共同记忆 59")

    def test_legacy_import_maps_relationship_repair_and_malformed_records(self):
        legacy = {
            "emotion": {"values": {"hurt": 0.6}},
            "relationship": {"values": {"closeness": 0.8, "boundary": 0.4}},
            "repair": {"records": [{"id": "r1", "text": "修复过一次", "weight": 0.7}]},
            "memory": {"records": [{"id": "m1", "text": "旧记忆"}, "bad", {"summary": "无 id 摘要"}]},
        }

        kernel = AlphaKernel.boot(session_key="full-import", legacy=legacy)
        snapshot = kernel.snapshot()

        self.assertGreater(snapshot["body"]["needs"]["need_repair"], 0.0)
        self.assertGreater(snapshot["body"]["bloodflow"]["warmth"], 0.4)
        self.assertTrue(any(trace["id"] == "r1" for trace in snapshot["body"]["memory"]["traces"]))
        self.assertIn("relationship", snapshot["audit"]["legacy_payloads"])
        self.assertIn("repair", snapshot["audit"]["legacy_payloads"])

    def test_runtime_recovers_damaged_snapshot_and_exports_all_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AlphaRuntime(Path(tmp))
            kernel = AlphaKernel.boot(session_key="ok")
            kernel.tick(AlphaKernelEvent(text="正常", flags=["safe"], now=1.0))
            runtime.save(kernel)
            damaged_path = Path(tmp) / "broken.alpha.json"
            damaged_path.write_text("{broken", encoding="utf-8")

            recovered = runtime.load("broken")
            exported = runtime.export_all()

        self.assertEqual(recovered.snapshot()["turns"], 0)
        self.assertIn("ok", exported["sessions"])
        self.assertIn("broken", exported["recovered"])

    def test_kernel_boot_tick_surface_snapshot_and_restore(self):
        kernel = AlphaKernel.boot(session_key="room:one")

        result = kernel.tick(AlphaKernelEvent(text="我还在这里", flags=["safe"], confidence=0.6, now=10.0))
        snapshot = kernel.snapshot()
        restored = AlphaKernel.restore(snapshot)

        self.assertEqual(result["surface"]["schema_version"], "sylanne.alpha.body.v1")
        self.assertEqual(snapshot["session_key"], "room:one")
        self.assertEqual(restored.snapshot(), snapshot)
        self.assertGreater(snapshot["body"]["pulse"]["beat"], 0.0)
        self.assertGreater(snapshot["body"]["nerve"]["plasticity"], 0.0)
        self.assertIn(result["decision"]["action"], {"express", "explore", "wait", "hold", "reach_out", "repair", "withdraw"})

    def test_nonhuman_body_tracks_organs_needs_wounds_and_immunity(self):
        kernel = AlphaKernel.boot(session_key="body")

        kernel.tick(AlphaKernelEvent(text="靠近", flags=["boundary", "hurt"], confidence=0.4, now=1.0))
        body = kernel.snapshot()["body"]

        self.assertEqual(set(body), {"pulse", "bloodflow", "nerve", "muscle", "temperature", "wound", "immunity", "mortality", "needs", "memory"})
        self.assertGreater(body["wound"]["sensitivity"], 0.0)
        self.assertGreater(body["immunity"]["boundary_pressure"], 0.0)
        self.assertIn("need_repair", body["needs"])

    def test_idle_time_accumulates_contact_need_but_respects_sovereignty(self):
        kernel = AlphaKernel.boot(session_key="idle")
        for now in (1.0, 2.0, 3.0, 4.0):
            kernel.tick(AlphaKernelEvent(flags=["idle"], now=now))

        before_pause = kernel.surface()
        kernel.tick(AlphaKernelEvent(flags=["pause", "idle"], now=5.0))
        after_pause = kernel.surface()

        self.assertGreater(before_pause["body"]["needs"]["need_contact"], 0.0)
        self.assertEqual(after_pause["guard"]["allowed"], False)
        self.assertIn("user_pause", after_pause["guard"]["flags"])
        self.assertEqual(after_pause["host_payload"]["should_send"], False)

    def test_legacy_payload_migrates_into_body_memory_and_audit(self):
        legacy = {
            "emotion": {"values": {"certainty": 0.7, "arousal": 0.2, "affiliation": 0.8}, "confidence": 0.6},
            "lifelike": {"values": {"rapport": 0.9, "common_ground": 0.7}, "flags": ["safe"]},
            "memory": {"records": [{"id": "m1", "text": "旧记忆不能丢"}], "event_count": 3},
        }

        kernel = AlphaKernel.boot(session_key="migrated", legacy=legacy)
        snapshot = kernel.snapshot()

        self.assertEqual(snapshot["schema_version"], "sylanne.alpha.body.v1")
        self.assertEqual(snapshot["body"]["memory"]["traces"][0]["text"], "旧记忆不能丢")
        self.assertEqual(snapshot["audit"]["legacy_payloads"]["memory"]["records"][0]["id"], "m1")

    def test_runtime_persists_and_restores_kernel_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AlphaRuntime(Path(tmp))
            kernel = AlphaKernel.boot(session_key="persist")
            kernel.tick(AlphaKernelEvent(text="留下痕迹", flags=["safe"], now=1.0))

            runtime.save(kernel)
            restored = runtime.load("persist")

        self.assertEqual(restored.snapshot(), kernel.snapshot())

    def test_runtime_loads_legacy_snapshot_when_alpha_file_is_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AlphaRuntime(Path(tmp))
            legacy = {"memory": {"records": [{"id": "old", "text": "从旧数据醒来"}]}}
            restored = runtime.load("legacy", legacy=legacy)

        self.assertEqual(restored.snapshot()["body"]["memory"]["traces"][0]["id"], "old")


if __name__ == "__main__":
    unittest.main()
