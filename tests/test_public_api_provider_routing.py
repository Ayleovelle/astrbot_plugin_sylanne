"""PublicAPI integration contracts for the central provider router."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from sylanne_alpha.public_api import PublicAPI


class _EmbeddingProvider:
    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id
        self.calls: list[str] = []

    async def get_embedding(self, text: str) -> list[float]:
        self.calls.append(text)
        return [0.25, 0.75]


class _TextProvider:
    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id


class _Context:
    def __init__(self, *, embeddings=(), texts=()) -> None:
        self.embeddings = {p.provider_id: p for p in embeddings}
        self.texts = {p.provider_id: p for p in texts}
        self.embedding_inventory_calls = 0
        self.lookup_calls: list[str] = []

    def get_all_embedding_providers(self):
        self.embedding_inventory_calls += 1
        return list(self.embeddings.values())

    def get_all_providers(self):
        return list(self.texts.values())

    def get_provider_by_id(self, provider_id):
        self.lookup_calls.append(provider_id)
        return self.texts.get(provider_id) or self.embeddings.get(provider_id)

    def get_using_provider(self, umo=None):
        return next(iter(self.texts.values()), None)


class _Memory:
    def __init__(self) -> None:
        self.last_recall = None

    def recall(self, **kwargs):
        self.last_recall = dict(kwargs)
        return []


class _Plugin:
    def __init__(self, config, context) -> None:
        self.config = dict(config)
        self._config = self.config
        self.context = context
        self.memory = _Memory()
        self.assessor_calls: list[dict] = []

    def _host(self, session_key):
        engine = SimpleNamespace(observe=lambda: {"warmth": 0.1})
        computation = SimpleNamespace(engine=engine)
        return SimpleNamespace(kernel=SimpleNamespace(computation=computation))

    def _memory_system_for_session(self, session_key):
        return self.memory

    async def _call_internal_assessor_llm(self, **kwargs):
        self.assessor_calls.append(dict(kwargs))
        return SimpleNamespace(
            completion_text=json.dumps(
                {"dimensions": {"valence": 0.8}, "confidence": 0.9, "label": "joy"}
            )
        )


def test_query_memory_auto_selects_the_only_embedding_provider() -> None:
    embedding = _EmbeddingProvider("emb-only")
    context = _Context(embeddings=(embedding,))
    plugin = _Plugin(
        {
            "sylanne_alpha_embedding_memory_enabled": True,
            "sylanne_alpha_embedding_memory_provider_id": "",
        },
        context,
    )

    asyncio.run(
        PublicAPI(plugin).query_sylanne_memory(
            session_key="qq:friend:1", query="昨晚聊了什么", limit=3
        )
    )

    assert context.embedding_inventory_calls == 1
    assert embedding.calls == ["昨晚聊了什么"]
    assert plugin.memory.last_recall["query_embedding"] == [0.25, 0.75]


def test_query_memory_multiple_embedding_providers_fail_closed() -> None:
    first = _EmbeddingProvider("emb-1")
    second = _EmbeddingProvider("emb-2")
    context = _Context(embeddings=(first, second))
    plugin = _Plugin(
        {
            "sylanne_alpha_embedding_memory_enabled": True,
            "sylanne_alpha_embedding_memory_provider_id": "",
        },
        context,
    )

    asyncio.run(
        PublicAPI(plugin).query_sylanne_memory(
            session_key="qq:friend:1", query="昨晚聊了什么", limit=3
        )
    )

    assert context.embedding_inventory_calls == 1
    assert first.calls == []
    assert second.calls == []
    assert plugin.memory.last_recall["query_embedding"] is None


def test_embedding_enable_gate_prevents_even_provider_inventory_lookup() -> None:
    embedding = _EmbeddingProvider("emb-only")
    context = _Context(embeddings=(embedding,))
    plugin = _Plugin(
        {
            "sylanne_alpha_embedding_memory_enabled": False,
            "sylanne_alpha_embedding_memory_provider_id": "emb-only",
        },
        context,
    )

    asyncio.run(
        PublicAPI(plugin).query_sylanne_memory(
            session_key="qq:friend:1", query="昨晚聊了什么", limit=3
        )
    )

    assert context.embedding_inventory_calls == 0
    assert embedding.calls == []


def test_assessor_uses_aux_provider_only_when_real_gate_is_enabled() -> None:
    aux = _TextProvider("aux")
    context = _Context(texts=(aux,))
    plugin = _Plugin(
        {
            "enable_low_signal_light_assessment": False,
            "sylanne_alpha_assessor_llm_enabled": True,
            "sylanne_alpha_aux_provider_id": "aux",
        },
        context,
    )
    event = SimpleNamespace(unified_msg_origin="qq:friend:1")

    result = asyncio.run(
        PublicAPI(plugin)._assess_emotion(
            text="今天终于把这件困扰很久的事情处理好了", event=event
        )
    )

    assert result.source == "llm"
    assert result.label == "joy"
    assert len(plugin.assessor_calls) == 1
    assert plugin.assessor_calls[0]["provider_id"] == "aux"


def test_deprecated_fast_boolean_cannot_enable_assessor_call() -> None:
    aux = _TextProvider("aux")
    context = _Context(texts=(aux,))
    plugin = _Plugin(
        {
            "enable_low_signal_light_assessment": False,
            "sylanne_alpha_assessor_llm_enabled": False,
            "sylanne_alpha_fast_assessor_enabled": True,
            "sylanne_alpha_aux_provider_id": "aux",
        },
        context,
    )

    result = asyncio.run(
        PublicAPI(plugin)._assess_emotion(
            text="今天终于把这件困扰很久的事情处理好了",
            event=SimpleNamespace(unified_msg_origin="qq:friend:1"),
        )
    )

    assert result.source == "heuristic"
    assert plugin.assessor_calls == []
