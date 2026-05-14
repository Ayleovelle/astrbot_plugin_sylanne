import unittest

from memory_engine import (
    MemoryRecord,
    SylanneMemoryState,
    apply_memory_time_decay,
    build_memory_prompt_fragment,
    derive_memory_dynamics,
    observe_memory_event,
    recall_memory,
    reinforce_recalled_memories,
)


class SylanneMemoryEngineTests(unittest.TestCase):
    def test_memory_dynamics_are_derived_without_user_tunable_parameters(self):
        emotion = {
            "emotion": {
                "label": "hurt",
                "confidence": 0.82,
                "values": {
                    "valence": -0.55,
                    "arousal": 0.72,
                    "affiliation": -0.38,
                    "certainty": 0.64,
                },
            },
            "relationship": {
                "decision": "boundary",
                "conflict_analysis": {"cause": "user_fault"},
            },
        }
        personality = {
            "trait_offsets": {
                "neuroticism": 0.42,
                "agreeableness": -0.2,
                "attachment_anxiety": 0.38,
                "emotion_regulation_capacity": -0.24,
            },
            "values": {
                "drift_intensity": 0.44,
                "anchor_strength": 0.76,
                "relationship_sensitivity": 0.55,
            },
        }
        lifelike = {
            "values": {
                "rapport": 0.74,
                "common_ground": 0.66,
                "preference_confidence": 0.51,
                "boundary_sensitivity": 0.58,
            },
        }

        dynamics = derive_memory_dynamics(
            emotion_snapshot=emotion,
            personality_drift_snapshot=personality,
            lifelike_snapshot=lifelike,
            group_atmosphere_snapshot={},
            now=1000.0,
        )

        self.assertGreater(dynamics.salience_bias, 0.55)
        self.assertGreater(dynamics.relationship_weight, 0.65)
        self.assertGreater(dynamics.consolidation_gain, 0.45)
        self.assertGreater(dynamics.decay_half_life_seconds, 86400.0)
        self.assertGreaterEqual(dynamics.recall_limit, 2)
        self.assertLessEqual(dynamics.recall_limit, 5)
        self.assertGreaterEqual(dynamics.recall_maturation_seconds, 0.0)
        self.assertLessEqual(dynamics.recall_maturation_seconds, 12.0)
        self.assertIn("auto_derived", dynamics.notes)

    def test_observe_memory_event_consolidates_and_recall_decays_with_real_time(self):
        state = SylanneMemoryState.initial(now=0.0)
        state = observe_memory_event(
            state,
            text="用户解释过：他们指插件的其他用户，不是恋爱对象。",
            session_key="s-memory",
            speaker_id="u1",
            emotion_snapshot={
                "emotion": {
                    "label": "guarded",
                    "confidence": 0.86,
                    "values": {"valence": -0.4, "arousal": 0.66, "affiliation": -0.2},
                },
                "relationship": {"decision": "clarify"},
            },
            lifelike_snapshot={
                "values": {"rapport": 0.7, "common_ground": 0.62},
            },
            now=10.0,
        )

        self.assertEqual(len(state.records), 1)
        record = state.records[0]
        self.assertGreater(record.depth, 0.45)
        self.assertIn("episodic", record.layers)
        self.assertIn("relationship", record.layers)
        self.assertEqual(record.auto_parameters["recall_limit"], state.dynamics.recall_limit)
        self.assertEqual(
            record.auto_parameters["recall_maturation_seconds"],
            state.dynamics.to_dict()["recall_maturation_seconds"],
        )

        fresh = recall_memory(
            state,
            query="那你有什么想对他们说的吗",
            now=60.0,
        )
        old = recall_memory(
            state,
            query="那你有什么想对他们说的吗",
            now=60.0 + state.dynamics.decay_half_life_seconds * 4,
        )

        self.assertEqual(len(fresh), 1)
        self.assertEqual(len(old), 1)
        self.assertGreater(fresh[0].score, old[0].score)
        self.assertGreater(fresh[0].score, 0.2)

    def test_prompt_fragment_is_bounded_and_marks_first_party_memory(self):
        state = SylanneMemoryState.initial(now=0.0)
        state.records.append(
            MemoryRecord(
                text="用户说过 README 要尽量中文，不要像炫耀。",
                summary="README 要中文、克制，不要炫耀。",
                session_key="s-doc",
                speaker_id="u1",
                created_at=10.0,
                updated_at=10.0,
                depth=0.82,
                confidence=0.74,
                layers={"episodic": 0.7, "semantic": 0.6, "relationship": 0.4},
            ),
        )

        fragment = build_memory_prompt_fragment(
            recall_memory(state, query="README 怎么写", now=20.0),
            session_key="s-doc",
            max_chars=220,
        )

        self.assertIn("sylanne_memory_recall", fragment)
        self.assertIn("README 要中文", fragment)
        self.assertLessEqual(len(fragment), 220)

    def test_memory_prompt_fragment_includes_astrbot_event_time(self):
        state = SylanneMemoryState.initial(now=0.0)
        state = observe_memory_event(
            state,
            text="user said the thesis still needs late-night editing",
            session_key="s-time-memory",
            speaker_id="u1",
            now=1778700459.0,
            event_time={
                "epoch": 1778700459.0,
                "local_time": "2026-05-14 03:27:39 +08:00",
                "timezone": "Asia/Shanghai",
            },
        )

        fragment = build_memory_prompt_fragment(
            recall_memory(
                state,
                query="thesis editing",
                now=1778700460.0,
            ),
            session_key="s-time-memory",
            max_chars=360,
        )

        self.assertIn("2026-05-14 03:27:39 +08:00", fragment)
        self.assertIn("Asia/Shanghai", fragment)

    def test_recalled_memory_is_reinforced_after_use(self):
        state = SylanneMemoryState.initial(now=0.0)
        state.records.append(
            MemoryRecord(
                text="用户说过插件文档页不要再显示旧版本。",
                summary="插件文档页不要再显示旧版本。",
                session_key="s-version",
                speaker_id="u1",
                created_at=10.0,
                updated_at=10.0,
                depth=0.42,
                confidence=0.46,
                layers={"semantic": 0.6},
            ),
        )

        items = recall_memory(state, query="为什么文档还是旧版本", now=20.0)
        reinforced = reinforce_recalled_memories(
            state,
            items,
            query="为什么文档还是旧版本",
            now=20.0,
        )
        record = reinforced.records[0]

        self.assertEqual(record.recall_count, 1)
        self.assertEqual(record.last_recalled_at, 20.0)
        self.assertGreater(record.depth, 0.42)
        self.assertGreater(record.confidence, 0.46)
        self.assertIn("retrieval_reinforcement", record.auto_parameters)

    def test_recall_can_associate_neighbor_memories_with_hard_budget(self):
        state = SylanneMemoryState.initial(now=0.0)
        state.dynamics.recall_limit = 1
        state.dynamics.associative_recall_limit = 2
        state.records.extend(
            [
                MemoryRecord(
                    memory_id="core-them",
                    text="用户解释过：他们指插件的其他用户，不是恋爱对象。",
                    summary="他们指插件的其他用户。",
                    session_key="s-assoc",
                    created_at=10.0,
                    updated_at=10.0,
                    depth=0.86,
                    confidence=0.82,
                    layers={"episodic": 0.8, "relationship": 0.7},
                    associations={
                        "tone-soft": 0.86,
                        "readme-cn": 0.74,
                        "overflow": 0.72,
                    },
                ),
                MemoryRecord(
                    memory_id="tone-soft",
                    text="用户希望 Sylanne 对插件使用者说话时温和一点，别炫耀。",
                    summary="对插件使用者说话要温和、别炫耀。",
                    session_key="s-assoc",
                    created_at=12.0,
                    updated_at=12.0,
                    depth=0.70,
                    confidence=0.72,
                    layers={"semantic": 0.7, "relationship": 0.5},
                ),
                MemoryRecord(
                    memory_id="readme-cn",
                    text="用户反复要求 README 能用中文就用中文。",
                    summary="README 要尽量中文。",
                    session_key="s-assoc",
                    created_at=14.0,
                    updated_at=14.0,
                    depth=0.68,
                    confidence=0.70,
                    layers={"semantic": 0.8},
                ),
                MemoryRecord(
                    memory_id="overflow",
                    text="这条也有关联，但不应该超过联想预算。",
                    summary="超过预算的关联记忆。",
                    session_key="s-assoc",
                    created_at=16.0,
                    updated_at=16.0,
                    depth=0.66,
                    confidence=0.68,
                    layers={"semantic": 0.5},
                ),
            ],
        )

        items = recall_memory(state, query="那你想对他们说什么", now=20.0, limit=1)
        summaries = [item.record.summary for item in items]

        self.assertLessEqual(len(items), 3)
        self.assertIn("他们指插件的其他用户。", summaries)
        self.assertIn("对插件使用者说话要温和、别炫耀。", summaries)
        self.assertNotIn("README 要尽量中文。", summaries)
        self.assertNotIn("超过预算的关联记忆。", summaries)
        associative = [item for item in items if "associative_recall" in item.reasons]
        self.assertEqual(len(associative), 1)

    def test_associated_recall_must_match_current_context(self):
        state = SylanneMemoryState.initial(now=0.0)
        state.dynamics.recall_limit = 1
        state.dynamics.associative_recall_limit = 1
        state.records.extend(
            [
                MemoryRecord(
                    memory_id="thesis-night",
                    text="用户凌晨说论文还没修完，需要继续熬夜奋战。",
                    summary="用户正在熬夜修论文。",
                    session_key="s-context-gate",
                    created_at=10.0,
                    updated_at=10.0,
                    depth=0.86,
                    confidence=0.82,
                    layers={"episodic": 0.8, "semantic": 0.7},
                    associations={"drink-order": 0.98},
                ),
                MemoryRecord(
                    memory_id="drink-order",
                    text="用户之前排队买蜜雪冰城，偏好少冰和甜一点的饮料。",
                    summary="用户喜欢蜜雪饮料少冰甜一点。",
                    session_key="s-context-gate",
                    created_at=11.0,
                    updated_at=11.0,
                    depth=0.74,
                    confidence=0.78,
                    layers={"episodic": 0.7},
                ),
            ],
        )

        items = recall_memory(
            state,
            query="当前用户消息：我论文还没修完捏 / 得 / 熬夜奋战了",
            now=20.0,
            limit=1,
        )

        memory_ids = [item.record.memory_id for item in items]
        self.assertIn("thesis-night", memory_ids)
        self.assertNotIn("drink-order", memory_ids)

    def test_associated_recall_ignores_generic_context_overlap(self):
        state = SylanneMemoryState.initial(now=0.0)
        state.dynamics.recall_limit = 1
        state.dynamics.associative_recall_limit = 1
        state.records.extend(
            [
                MemoryRecord(
                    memory_id="paper-deadline",
                    text="The user is revising a thesis deadline overnight.",
                    summary="thesis deadline overnight revision",
                    session_key="s-generic-context",
                    created_at=10.0,
                    updated_at=10.0,
                    depth=0.86,
                    confidence=0.82,
                    associations={"cafeteria-drink": 0.98},
                ),
                MemoryRecord(
                    memory_id="cafeteria-drink",
                    text="The user previously liked a cafeteria drink with more sugar.",
                    summary="user previously liked cafeteria drink",
                    session_key="s-generic-context",
                    created_at=11.0,
                    updated_at=11.0,
                    depth=0.74,
                    confidence=0.78,
                ),
            ],
        )

        items = recall_memory(
            state,
            query="thesis deadline overnight revision",
            now=20.0,
            limit=1,
        )

        memory_ids = [item.record.memory_id for item in items]
        self.assertIn("paper-deadline", memory_ids)
        self.assertNotIn("cafeteria-drink", memory_ids)

    def test_recall_can_use_embedding_vector_when_sparse_words_do_not_match(self):
        state = SylanneMemoryState.initial(now=0.0)
        state.records.extend(
            [
                MemoryRecord(
                    memory_id="dense-hit",
                    text="alpha beta gamma",
                    summary="alpha beta gamma",
                    session_key="s-vector",
                    created_at=10.0,
                    updated_at=10.0,
                    depth=0.52,
                    confidence=0.64,
                    semantic_embedding=[1.0, 0.0, 0.0],
                    embedding_provider_id="embed-a",
                    embedding_updated_at=10.0,
                    embedding_text_hash="hash-a",
                ),
                MemoryRecord(
                    memory_id="dense-miss",
                    text="delta epsilon zeta",
                    summary="delta epsilon zeta",
                    session_key="s-vector",
                    created_at=11.0,
                    updated_at=11.0,
                    depth=0.88,
                    confidence=0.90,
                    semantic_embedding=[0.0, 1.0, 0.0],
                    embedding_provider_id="embed-a",
                    embedding_updated_at=11.0,
                    embedding_text_hash="hash-b",
                ),
            ],
        )

        items = recall_memory(
            state,
            query="unrelated natural language query",
            now=20.0,
            limit=1,
            query_embedding=[1.0, 0.0, 0.0],
            embedding_provider_id="embed-a",
        )

        self.assertEqual([item.record.memory_id for item in items], ["dense-hit"])
        self.assertIn("vector_match", items[0].reasons)

    def test_memory_record_persists_embedding_metadata(self):
        record = MemoryRecord(
            memory_id="dense-persist",
            text="record text",
            summary="record summary",
            session_key="s-vector",
            semantic_embedding=[0.2, 0.4, 0.8],
            embedding_provider_id="embed-a",
            embedding_updated_at=123.0,
            embedding_text_hash="hash-a",
        )

        restored = MemoryRecord.from_dict(record.to_dict())

        self.assertIsNotNone(restored)
        self.assertEqual(restored.semantic_embedding, [0.2, 0.4, 0.8])
        self.assertEqual(restored.embedding_provider_id, "embed-a")
        self.assertEqual(restored.embedding_updated_at, 123.0)
        self.assertEqual(restored.embedding_text_hash, "hash-a")

    def test_stale_weak_memory_is_forgotten_by_real_time_decay(self):
        state = SylanneMemoryState.initial(now=0.0)
        state.dynamics.decay_half_life_seconds = 10.0
        state.records.append(
            MemoryRecord(
                text="一次很弱的临时噪声。",
                summary="临时噪声。",
                session_key="s-forget",
                speaker_id="u1",
                created_at=0.0,
                updated_at=0.0,
                depth=0.06,
                confidence=0.08,
                layers={"episodic": 0.1},
                auto_parameters={"decay_half_life_seconds": 10.0},
            ),
        )
        state.records.append(
            MemoryRecord(
                text="用户明确说过 README 要中文。",
                summary="README 要中文。",
                session_key="s-forget",
                speaker_id="u1",
                created_at=0.0,
                updated_at=0.0,
                depth=0.74,
                confidence=0.70,
                evidence_count=3,
                layers={"semantic": 0.8},
                auto_parameters={"decay_half_life_seconds": 10.0},
            ),
        )

        decayed = apply_memory_time_decay(state, now=120.0)

        self.assertEqual(len(decayed.records), 1)
        self.assertEqual(decayed.records[0].summary, "README 要中文。")
        self.assertIn("forgotten=1", decayed.dynamics.notes)

    def test_compaction_scores_all_records_not_only_last_one(self):
        state = SylanneMemoryState.initial(now=0.0)
        state.dynamics.decay_half_life_seconds = 1000.0
        for index in range(5):
            state.records.append(
                MemoryRecord(
                    memory_id=f"m-{index}",
                    text=f"长期记忆 {index}",
                    summary=f"长期记忆 {index}",
                    session_key="s-compact",
                    created_at=float(index),
                    updated_at=float(index),
                    depth=0.10 + index * 0.18,
                    confidence=0.20 + index * 0.12,
                    evidence_count=2,
                    auto_parameters={"decay_half_life_seconds": 1000.0},
                    associations={"m-4": 0.5} if index == 0 else {},
                ),
            )

        compacted = apply_memory_time_decay(state, now=20.0, hard_limit=3)
        summaries = [record.summary for record in compacted.records]

        self.assertEqual(len(compacted.records), 3)
        self.assertEqual(summaries, ["长期记忆 4", "长期记忆 3", "长期记忆 2"])
        self.assertEqual(compacted.records[-1].associations, {})


if __name__ == "__main__":
    unittest.main()
