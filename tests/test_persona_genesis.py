"""Contract tests for the persona-genesis activation path."""

from __future__ import annotations

import importlib
import json
import asyncio
import hashlib
import multiprocessing
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from sylanne_alpha.persona_genesis import (
    PersonaGenesisParseError,
    canonical_persona_genesis_json,
    parse_persona_genesis_profile,
)
from sylanne_alpha.scope_contracts import BotRef, PersonaRevisionRef, SessionRef, SessionScope
from sylanne_alpha.scope_identity import PersonaSource
from sylanne_alpha.scope_repository import (
    RepositoryCorruptionError,
    ScopeRepository,
    StaleScopeWrite,
)
from sylanne_alpha.scope_runtime import PersonaRuntime, ScopeMismatch, ScopeRuntimeRegistry


def _profile() -> dict[str, object]:
    return {
        "traits_prior": {"steadiness": 0.8},
        "voice_prior": {"tone": "warm"},
        "boundary_prior": {"privacy": 1},
        "proactivity_prior": {"initiative": 0.2},
        "circadian_prior": {"dawn": 0.3},
    }


def _persona(index: int = 0) -> PersonaRevisionRef:
    bot = BotRef(token="bot_v1_Genesis", generation=0)
    return PersonaRevisionRef(
        token=f"persona_v1_G{index}",
        bot_ref=bot,
        persona_id_digest=f"{index + 10:064x}",
        source_fingerprint=f"{index + 100:064x}",
        lifecycle_generation=0,
    )


def _source(
    *,
    persona_id: str = "persona-genesis-test",
    prompt: str = "a calm, precise persona",
    begin_dialogs: tuple[str, ...] = (),
) -> PersonaSource:
    return PersonaSource(
        persona_id=persona_id,
        prompt=prompt,
        begin_dialogs=begin_dialogs,
        tools=None,
        skills=None,
        resolution_source="test",
    )


def _persona_for_source(source: PersonaSource, *, index: int = 0) -> PersonaRevisionRef:
    bot = BotRef(token="bot_v1_GenesisOwner", generation=0)
    return PersonaRevisionRef(
        token=f"persona_v1_O{index}",
        bot_ref=bot,
        persona_id_digest=hashlib.sha256(source.persona_id.encode("utf-8")).hexdigest(),
        source_fingerprint=hashlib.sha256(source.canonical_bytes()).hexdigest(),
        lifecycle_generation=0,
    )


def _scope_for_persona(persona: PersonaRevisionRef, *, index: int = 0) -> SessionScope:
    suffix = "" if index == 0 else str(index)
    session = SessionRef(token=f"session_v1_GenesisOwner{suffix}", bot_ref=persona.bot_ref, generation=0)
    return SessionScope(
        bot_ref=persona.bot_ref,
        persona_ref=persona,
        session_ref=session,
        storage_token=f"scope_v1_GenesisOwner{suffix}",
        scope_generation=0,
    )


class _Provider:
    def __init__(
        self,
        *,
        completion_text: str | None = None,
        error: Exception | None = None,
    ) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0
        self.requests: list[tuple[str, int, float]] = []
        self._completion_text = (
            json.dumps(_profile(), separators=(",", ":"))
            if completion_text is None
            else completion_text
        )
        self._error = error

    async def text_chat(
        self,
        *,
        prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> SimpleNamespace:
        self.calls += 1
        self.requests.append((prompt, max_tokens, temperature))
        self.entered.set()
        await self.release.wait()
        if self._error is not None:
            raise self._error
        return SimpleNamespace(completion_text=self._completion_text)


class _ProviderContext:
    def __init__(self, provider: _Provider) -> None:
        self.provider = provider
        self.lookups = 0

    async def get_provider_by_id(self, provider_id: str) -> _Provider | None:
        self.lookups += 1
        return self.provider if provider_id == "genesis" else None

    async def get_all_providers(self) -> list[_Provider]:
        return [self.provider]


def _enabled_config() -> dict[str, object]:
    return {
        "sylanne_alpha_persona_genesis_enabled": True,
        "sylanne_alpha_persona_genesis_paid_opt_in": True,
        "sylanne_alpha_persona_genesis_provider_id": "genesis",
    }


def _profile_json(profile: dict[str, object]) -> str:
    return json.dumps(profile, separators=(",", ":"))


def _parser_boundary_cases() -> list[tuple[str, str, str]]:
    bytes_profile = _profile()
    bytes_raw = _profile_json(bytes_profile)
    exact_bytes = bytes_raw + (" " * (8192 - len(bytes_raw.encode("utf-8"))))

    items_profile = _profile()
    items_profile["traits_prior"] = {f"item{index}": 0 for index in range(32)}
    too_many_items = _profile()
    too_many_items["traits_prior"] = {f"item{index}": 0 for index in range(33)}

    node_profile = _profile()
    node_profile["traits_prior"] = {
        **{f"list{index}": [0, 0, 0] for index in range(29)},
        "last0": 0,
        "last1": 0,
    }
    too_many_nodes = _profile()
    too_many_nodes["traits_prior"] = {
        **node_profile["traits_prior"],
        "last2": 0,
    }

    key_profile = _profile()
    key_profile["traits_prior"] = {"k" * 64: 0}
    too_long_key = _profile()
    too_long_key["traits_prior"] = {"k" * 65: 0}

    string_profile = _profile()
    string_profile["voice_prior"] = {"tone": "v" * 64}
    too_long_string = _profile()
    too_long_string["voice_prior"] = {"tone": "v" * 65}

    return [
        ("bytes", exact_bytes, exact_bytes + " "),
        ("items", _profile_json(items_profile), _profile_json(too_many_items)),
        ("nodes", _profile_json(node_profile), _profile_json(too_many_nodes)),
        ("key", _profile_json(key_profile), _profile_json(too_long_key)),
        ("string", _profile_json(string_profile), _profile_json(too_long_string)),
    ]


def _claim_once_in_child(
    root: str,
    persona: PersonaRevisionRef,
    now_ms: int,
    results: object,
) -> None:
    repository = ScopeRepository(Path(root))
    try:
        lease = repository.claim_persona_genesis(
            persona,
            source_fingerprint=persona.source_fingerprint,
            origin_turn_generation=0,
            now_ms=now_ms,
        )
        results.put(("ok", lease is not None))
    except BaseException as exc:  # pragma: no cover - child errors are asserted by parent.
        results.put(("error", repr(exc)))


def _claim_many_in_child(
    root: str,
    personae: list[PersonaRevisionRef],
    now_ms: int,
    results: object,
    start_gate: object,
    ready: object,
) -> None:
    repository = ScopeRepository(Path(root))
    successful = 0
    try:
        ready.put("ready")
        if not start_gate.wait(20):
            results.put(("error", "start gate timed out"))
            return
        for persona in personae:
            lease = None
            for _ in range(200):
                lease = repository.claim_persona_genesis(
                    persona,
                    source_fingerprint=persona.source_fingerprint,
                    origin_turn_generation=0,
                    now_ms=now_ms,
                )
                if lease is not None:
                    break
                time.sleep(0.005)
            if lease is None:
                continue
            successful += 1
            assert repository.reject_persona_genesis_claim(
                persona,
                lease,
                source_fingerprint=persona.source_fingerprint,
                now_ms=now_ms,
                backoff_ms=0,
            )
        results.put(("ok", successful))
    except BaseException as exc:  # pragma: no cover - child errors are asserted by parent.
        results.put(("error", repr(exc)))


def _hold_provider_slot_in_child(
    root: str,
    ready: object,
    release: object,
    results: object,
) -> None:
    async def hold_slot() -> None:
        repository = ScopeRepository(Path(root))
        with repository.persona_genesis_provider_slot() as acquired:
            ready.put(acquired)
            if acquired:
                await asyncio.get_running_loop().run_in_executor(None, release.wait, 20)
            results.put(("holder", acquired))

    try:
        asyncio.run(hold_slot())
    except BaseException as exc:  # pragma: no cover - child errors are asserted by parent.
        results.put(("error", repr(exc)))


def _try_provider_slot_in_child(root: str, results: object) -> None:
    try:
        repository = ScopeRepository(Path(root))
        with repository.persona_genesis_provider_slot() as acquired:
            results.put(("contender", acquired))
    except BaseException as exc:  # pragma: no cover - child errors are asserted by parent.
        results.put(("error", repr(exc)))


def test_strict_profile_parser_accepts_exact_canonical_five_priors() -> None:
    try:
        module = importlib.import_module("sylanne_alpha.persona_genesis")
    except ModuleNotFoundError:
        module = None

    assert module is not None, "persona genesis parser module must exist"
    parse = getattr(module, "parse_persona_genesis_profile", None)
    assert callable(parse), "strict parser must be exported"

    raw = json.dumps(
        _profile(),
        separators=(",", ":"),
    )

    assert parse(raw) == _profile()
    assert canonical_persona_genesis_json(parse(raw)) == (
        b'{"boundary_prior":{"privacy":1},"circadian_prior":{"dawn":0.3},'
        b'"proactivity_prior":{"initiative":0.2},"traits_prior":'
        b'{"steadiness":0.8},"voice_prior":{"tone":"warm"}}'
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda profile: profile.pop("voice_prior"),
        lambda profile: profile.update({"extra": {}}),
        lambda profile: profile.update({"traits_prior": "0.2"}),
        lambda profile: profile["traits_prior"].update({"boolean": True}),
        lambda profile: profile["traits_prior"].update({"unsafe": "not safe"}),
        lambda profile: profile["traits_prior"].update({"memory": 0.1}),
        lambda profile: profile["traits_prior"].update({"user_profile": 0.1}),
        lambda profile: profile["traits_prior"].update({"life_event": 0.1}),
        lambda profile: profile["traits_prior"].update({"deep": {"a": {"b": {"c": {"d": 0.1}}}}}),
        lambda profile: profile["traits_prior"].update({"long": "x" * 65}),
    ],
)
def test_strict_profile_parser_rejects_closed_shape_and_sensitive_semantics(mutate: object) -> None:
    profile = _profile()
    mutate(profile)

    with pytest.raises(PersonaGenesisParseError):
        parse_persona_genesis_profile(json.dumps(profile, separators=(",", ":")))


@pytest.mark.parametrize("raw", ["[]", "null", '{"traits_prior":NaN}', '{"traits_prior":Infinity}'])
def test_strict_profile_parser_rejects_non_finite_or_non_object_json(raw: str) -> None:
    with pytest.raises(PersonaGenesisParseError):
        parse_persona_genesis_profile(raw)


def test_strict_profile_parser_rejects_duplicate_keys_and_huge_integers() -> None:
    duplicate_root = (
        '{"traits_prior":{"first":0.1},"traits_prior":{"second":0.2},'
        '"voice_prior":{"tone":"warm"},"boundary_prior":{"privacy":1},'
        '"proactivity_prior":{"initiative":0.2},"circadian_prior":{"dawn":0.3}}'
    )
    duplicate_nested = (
        '{"traits_prior":{"nested":{"first":0.1,"first":0.2}},'
        '"voice_prior":{"tone":"warm"},"boundary_prior":{"privacy":1},'
        '"proactivity_prior":{"initiative":0.2},"circadian_prior":{"dawn":0.3}}'
    )
    huge_number = _profile()
    huge_number["traits_prior"] = {"weight": 10**400}

    for duplicate in (duplicate_root, duplicate_nested):
        with pytest.raises(PersonaGenesisParseError):
            parse_persona_genesis_profile(duplicate)
    with pytest.raises(PersonaGenesisParseError):
        parse_persona_genesis_profile(json.dumps(huge_number, separators=(",", ":")))


@pytest.mark.parametrize(
    "forbidden_value",
    ["memory", "user_profile", "life_event", "prior-memory-state"],
)
def test_strict_profile_parser_rejects_forbidden_string_terms_at_any_depth(
    forbidden_value: str,
) -> None:
    profile = _profile()
    profile["traits_prior"] = {"nested": [{"value": forbidden_value}]}

    with pytest.raises(PersonaGenesisParseError):
        parse_persona_genesis_profile(json.dumps(profile, separators=(",", ":")))


@pytest.mark.parametrize(
    ("boundary", "accepted", "rejected"),
    _parser_boundary_cases(),
)
def test_strict_profile_parser_honors_exact_resource_boundaries(
    boundary: str,
    accepted: str,
    rejected: str,
) -> None:
    if boundary == "bytes":
        assert len(accepted.encode("utf-8")) == 8192
        assert len(rejected.encode("utf-8")) == 8193

    assert parse_persona_genesis_profile(accepted)
    with pytest.raises(PersonaGenesisParseError):
        parse_persona_genesis_profile(rejected)


def test_repository_claim_has_one_global_lease_and_activation_is_atomic(tmp_path: object) -> None:
    repository = ScopeRepository(tmp_path)
    active = repository.activate_persona_revision(_persona())

    lease = repository.claim_persona_genesis(
        active,
        source_fingerprint=active.source_fingerprint,
        origin_turn_generation=7,
        now_ms=1_700_000_000_000,
    )

    assert lease is not None
    assert repository.claim_persona_genesis(
        active,
        source_fingerprint=active.source_fingerprint,
        origin_turn_generation=8,
        now_ms=1_700_000_000_001,
    ) is None
    claimed = repository.read_genesis(active)
    assert claimed is not None
    assert claimed.payload["state"] == "claimed"
    assert claimed.payload["attempt"] == 1

    accepted = repository.commit_persona_genesis_activation(
        active,
        lease,
        profile=_profile(),
        source_fingerprint=active.source_fingerprint,
        origin_turn_generation=7,
        now_ms=1_700_000_000_100,
    )

    assert accepted.payload == {
        "state": "active",
        "persona_lifecycle_generation": 0,
        "source_fingerprint": active.source_fingerprint,
        "attempt": 1,
        "accepted_profile": _profile(),
        "initial_runtime": {
            "priors": _profile(),
            "growth_enabled": True,
            "origin_turn_generation": 7,
        },
        "growth_enabled": True,
        "origin_turn_generation": 7,
        "safe_metadata": {"accepted_at_ms": 1_700_000_000_100},
    }
    assert repository.read_genesis(active).generation == accepted.generation
    with pytest.raises(StaleScopeWrite):
        repository.commit_persona_genesis_activation(
            active,
            lease,
            profile=_profile(),
            source_fingerprint=active.source_fingerprint,
            origin_turn_generation=7,
            now_ms=1_700_000_000_101,
        )


def test_repository_global_daily_budget_is_non_refundable(tmp_path: object) -> None:
    repository = ScopeRepository(tmp_path)
    now_ms = 1_700_000_000_000

    for index in range(32):
        active = repository.activate_persona_revision(_persona(index))
        lease = repository.claim_persona_genesis(
            active,
            source_fingerprint=active.source_fingerprint,
            origin_turn_generation=0,
            now_ms=now_ms,
        )
        assert lease is not None
        assert repository.reject_persona_genesis_claim(
            active,
            lease,
            source_fingerprint=active.source_fingerprint,
            now_ms=now_ms + 1,
            backoff_ms=0,
        ) is True

    blocked = repository.activate_persona_revision(_persona(32))
    assert repository.claim_persona_genesis(
        blocked,
        source_fingerprint=blocked.source_fingerprint,
        origin_turn_generation=0,
        now_ms=now_ms + 2,
    ) is None


def test_repository_rejects_malformed_global_day_without_resetting_budget(tmp_path: Path) -> None:
    repository = ScopeRepository(tmp_path)
    active = repository.activate_persona_revision(_persona())
    global_path = tmp_path / "persona-genesis-global.json"
    malformed = {
        "schema_version": "sylanne.persona-genesis.global.v1",
        "day": "nonsense",
        "calls": 32,
        "fence": 32,
        "lease": None,
    }
    repository._atomic_json_replace(global_path, malformed)

    with pytest.raises(RepositoryCorruptionError):
        repository.claim_persona_genesis(
            active,
            source_fingerprint=active.source_fingerprint,
            origin_turn_generation=0,
            now_ms=1_700_000_000_000,
        )
    assert json.loads(global_path.read_text(encoding="utf-8")) == malformed


def test_reactivated_persona_ignores_prior_lifecycle_genesis_in_preflight(
    tmp_path: Path,
) -> None:
    repository = ScopeRepository(tmp_path)
    source = _source()
    initial = repository.activate_persona_revision(_persona_for_source(source))
    now_ms = 1_700_000_000_000
    lease = repository.claim_persona_genesis(
        initial,
        source_fingerprint=initial.source_fingerprint,
        origin_turn_generation=0,
        now_ms=now_ms,
    )
    assert lease is not None
    assert repository.reject_persona_genesis_claim(
        initial,
        lease,
        source_fingerprint=initial.source_fingerprint,
        now_ms=now_ms + 1,
        backoff_ms=0,
    ) is True

    retired = repository.retire_persona_revision(
        initial,
        expected_lifecycle_generation=initial.lifecycle_generation,
        reason="test-reactivate",
    )
    reactivated = repository.activate_persona_revision(initial)
    assert reactivated.lifecycle_generation == retired.lifecycle_generation
    assert repository.persona_genesis_schedule_preflight_nowait(
        reactivated,
        source_fingerprint=reactivated.source_fingerprint,
        now_ms=now_ms + 2,
    ) == "allowed"
    assert repository.persona_genesis_schedule_allowed(
        reactivated,
        source_fingerprint=reactivated.source_fingerprint,
        now_ms=now_ms + 2,
    ) is True


def test_generic_active_genesis_write_is_forbidden(tmp_path: Path) -> None:
    repository = ScopeRepository(tmp_path)
    active = repository.activate_persona_revision(_persona())
    path = repository.genesis_path(active)
    assert not path.exists()

    with pytest.raises(ValueError, match="generic persona genesis writes are forbidden"):
        repository.write_genesis(
            active,
            expected_lifecycle_generation=active.lifecycle_generation,
            expected_generation=0,
            payload={"state": "active"},
        )
    assert not path.exists()


def test_two_processes_allow_only_one_global_genesis_claim(tmp_path: Path) -> None:
    repository = ScopeRepository(tmp_path)
    first = repository.activate_persona_revision(_persona(0))
    second = repository.activate_persona_revision(_persona(1))
    context = multiprocessing.get_context("spawn")
    results = context.Queue()
    now_ms = 1_700_000_000_000
    processes = [
        context.Process(
            target=_claim_once_in_child,
            args=(str(tmp_path), persona, now_ms, results),
        )
        for persona in (first, second)
    ]
    for process in processes:
        process.start()
    outcomes = [results.get(timeout=20) for _ in processes]
    for process in processes:
        process.join(timeout=20)
        assert process.exitcode == 0

    assert sorted(outcomes) == [("ok", False), ("ok", True)]


def test_provider_slot_is_exclusive_across_a_simulated_provider_await(tmp_path: Path) -> None:
    ScopeRepository(tmp_path)
    context = multiprocessing.get_context("spawn")
    holder_ready = context.Queue()
    release = context.Event()
    outcomes = context.Queue()
    holder = context.Process(
        target=_hold_provider_slot_in_child,
        args=(str(tmp_path), holder_ready, release, outcomes),
    )
    holder.start()
    assert holder_ready.get(timeout=20) is True

    contender = context.Process(
        target=_try_provider_slot_in_child,
        args=(str(tmp_path), outcomes),
    )
    contender.start()
    contender.join(timeout=20)
    assert contender.exitcode == 0
    assert outcomes.get(timeout=10) == ("contender", False)

    release.set()
    holder.join(timeout=20)
    assert holder.exitcode == 0
    assert outcomes.get(timeout=10) == ("holder", True)


@pytest.mark.asyncio
async def test_four_owner_restart_preserves_budget_backoff_and_single_provider_slot(
    tmp_path: Path,
) -> None:
    repository = ScopeRepository(tmp_path)
    sources = [
        _source(persona_id=f"persona-{index}", prompt=f"prompt-{index}")
        for index in range(4)
    ]
    personae = [
        repository.activate_persona_revision(
            _persona_for_source(source, index=index)
        )
        for index, source in enumerate(sources)
    ]
    first_provider = _Provider(error=RuntimeError("provider unavailable"))
    first_context = _ProviderContext(first_provider)
    first_task_sets: list[set[object]] = [set() for _ in personae]
    first_owners = [
        _owner(persona, repository, tasks)
        for persona, tasks in zip(personae, first_task_sets, strict=True)
    ]

    first_tasks: list[asyncio.Task[None]] = []
    for index, (owner, source, tasks) in enumerate(
        zip(first_owners, sources, first_task_sets, strict=True),
        start=1,
    ):
        assert owner.schedule(
            source,
            config=_enabled_config(),
            context=first_context,
            origin_turn_generation=index,
        ) is False
        task = next(iter(tasks))
        assert isinstance(task, asyncio.Task)
        first_tasks.append(task)

    await asyncio.wait_for(first_provider.entered.wait(), timeout=1)
    assert first_provider.calls == 1
    assert first_context.lookups == 1
    assert len(first_provider.requests) == 1
    first_provider.release.set()
    await asyncio.gather(*first_tasks)
    assert all(not tasks for tasks in first_task_sets)

    first_states = [repository.read_genesis(persona) for persona in personae]
    backoff_indices = [
        index
        for index, snapshot in enumerate(first_states)
        if snapshot is not None and snapshot.payload["state"] == "backoff"
    ]
    assert len(backoff_indices) == 1
    backoff_index = backoff_indices[0]
    assert all(
        snapshot is None
        for index, snapshot in enumerate(first_states)
        if index != backoff_index
    )
    global_path = tmp_path / "persona-genesis-global.json"
    first_global = json.loads(global_path.read_text(encoding="utf-8"))
    assert first_global["calls"] == 1
    assert first_global["lease"] is None
    backoff_path = repository.genesis_path(personae[backoff_index])
    backoff_bytes = backoff_path.read_bytes()

    restarted = ScopeRepository(tmp_path)
    restarted_global = json.loads(global_path.read_text(encoding="utf-8"))
    assert restarted_global == first_global
    blocked_tasks: set[object] = set()
    blocked_provider = _Provider()
    blocked_context = _ProviderContext(blocked_provider)
    blocked_owner = _owner(
        personae[backoff_index],
        restarted,
        blocked_tasks,
    )
    assert blocked_owner.schedule(
        sources[backoff_index],
        config=_enabled_config(),
        context=blocked_context,
        origin_turn_generation=99,
    ) is False
    assert blocked_tasks == set()
    assert blocked_context.lookups == 0
    assert blocked_provider.calls == 0

    second_provider = _Provider()
    second_context = _ProviderContext(second_provider)
    remaining = [index for index in range(4) if index != backoff_index]
    second_task_sets: list[set[object]] = [set() for _ in remaining]
    second_owners = [
        _owner(personae[index], restarted, tasks)
        for index, tasks in zip(remaining, second_task_sets, strict=True)
    ]
    second_tasks: list[asyncio.Task[None]] = []
    for index, owner, tasks in zip(
        remaining,
        second_owners,
        second_task_sets,
        strict=True,
    ):
        assert owner.schedule(
            sources[index],
            config=_enabled_config(),
            context=second_context,
            origin_turn_generation=100 + index,
        ) is False
        task = next(iter(tasks))
        assert isinstance(task, asyncio.Task)
        second_tasks.append(task)

    await asyncio.wait_for(second_provider.entered.wait(), timeout=1)
    assert second_provider.calls == 1
    assert second_context.lookups == 1
    assert len(second_provider.requests) == 1
    second_provider.release.set()
    await asyncio.gather(*second_tasks)
    assert all(not tasks for tasks in second_task_sets)

    final_states = [restarted.read_genesis(persona) for persona in personae]
    assert sum(
        snapshot is not None and snapshot.payload["state"] == "active"
        for snapshot in final_states
    ) == 1
    assert final_states[backoff_index] is not None
    assert final_states[backoff_index].payload["state"] == "backoff"
    assert backoff_path.read_bytes() == backoff_bytes
    final_global = json.loads(global_path.read_text(encoding="utf-8"))
    assert final_global["calls"] == 2
    assert final_global["lease"] is None


def test_two_process_repositories_cas_daily_budget_at_32(tmp_path: Path) -> None:
    repository = ScopeRepository(tmp_path)
    personae = [repository.activate_persona_revision(_persona(index)) for index in range(33)]
    context = multiprocessing.get_context("spawn")
    results = context.Queue()
    ready = context.Queue()
    start_gate = context.Event()
    now_ms = 1_700_000_000_000
    first = context.Process(
        target=_claim_many_in_child,
        args=(str(tmp_path), personae[:16], now_ms, results, start_gate, ready),
    )
    second = context.Process(
        target=_claim_many_in_child,
        args=(str(tmp_path), personae[16:], now_ms, results, start_gate, ready),
    )
    first.start()
    second.start()
    assert [ready.get(timeout=20), ready.get(timeout=20)] == ["ready", "ready"]
    start_gate.set()
    first.join(timeout=30)
    assert first.exitcode == 0
    second.join(timeout=30)
    assert second.exitcode == 0

    outcomes = [results.get(timeout=10), results.get(timeout=10)]
    assert all(kind == "ok" for kind, _successful in outcomes)
    assert sum(successful for _kind, successful in outcomes) == 32
    global_control = json.loads(
        (tmp_path / "persona-genesis-global.json").read_text(encoding="utf-8")
    )
    assert global_control["calls"] == 32
    assert global_control["lease"] is None


def _owner(persona: PersonaRevisionRef, repository: ScopeRepository, tasks: set[object]):
    owner_cls = getattr(importlib.import_module("sylanne_alpha.persona_genesis"), "PersonaGenesisOwner", None)
    assert callable(owner_cls), "PersonaRuntime must own a PersonaGenesisOwner"
    return owner_cls(persona, repository=repository, background_tasks=tasks)


@pytest.mark.asyncio
async def test_owner_dual_gate_has_zero_lookup_task_or_durable_attempt(tmp_path: Path) -> None:
    repository = ScopeRepository(tmp_path)
    source = _source()
    active = repository.activate_persona_revision(_persona_for_source(source))
    provider = _Provider()
    context = _ProviderContext(provider)
    tasks: set[object] = set()
    owner = _owner(active, repository, tasks)

    assert owner.schedule(
        source,
        config={"sylanne_alpha_persona_genesis_enabled": True},
        context=context,
        origin_turn_generation=4,
    ) is False
    await asyncio.sleep(0)

    assert context.lookups == 0
    assert provider.calls == 0
    assert tasks == set()
    assert repository.read_genesis(active) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["claimed", "backoff"])
async def test_schedule_does_not_create_a_task_for_durable_claim_or_backoff(
    tmp_path: Path,
    state: str,
) -> None:
    repository = ScopeRepository(tmp_path)
    source = _source()
    active = repository.activate_persona_revision(_persona_for_source(source))
    now_ms = repository._now_ms()
    lease = repository.claim_persona_genesis(
        active,
        source_fingerprint=active.source_fingerprint,
        origin_turn_generation=1,
        now_ms=now_ms,
    )
    assert lease is not None
    if state == "backoff":
        assert repository.reject_persona_genesis_claim(
            active,
            lease,
            source_fingerprint=active.source_fingerprint,
            now_ms=now_ms,
            backoff_ms=60_000,
        )

    can_schedule = getattr(repository, "persona_genesis_schedule_allowed", None)
    assert callable(can_schedule), "repository must make the durable scheduling decision"
    assert can_schedule(active, source_fingerprint=active.source_fingerprint) is False
    provider = _Provider()
    context = _ProviderContext(provider)
    tasks: set[object] = set()
    owner = _owner(active, repository, tasks)

    assert owner.schedule(source, config=_enabled_config(), context=context, origin_turn_generation=2) is False
    await asyncio.sleep(0)

    assert context.lookups == 0
    assert provider.calls == 0
    assert tasks == set()


@pytest.mark.asyncio
async def test_owner_same_persona_is_single_flight_and_cancel_releases_claim(tmp_path: Path) -> None:
    repository = ScopeRepository(tmp_path)
    source = _source()
    active = repository.activate_persona_revision(_persona_for_source(source))
    provider = _Provider()
    context = _ProviderContext(provider)
    tasks: set[object] = set()
    owner = _owner(active, repository, tasks)

    assert owner.schedule(source, config=_enabled_config(), context=context, origin_turn_generation=5) is False
    assert owner.schedule(source, config=_enabled_config(), context=context, origin_turn_generation=5) is False
    await asyncio.wait_for(provider.entered.wait(), timeout=1)

    assert context.lookups == 1
    assert provider.calls == 1
    assert len(tasks) == 1
    task = next(iter(tasks))
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0)

    snapshot = repository.read_genesis(active)
    assert snapshot is not None
    assert snapshot.payload["state"] == "backoff"
    assert tasks == set()


@pytest.mark.asyncio
async def test_source_mismatch_is_rejected_before_lookup_budget_or_provider_call(tmp_path: Path) -> None:
    repository = ScopeRepository(tmp_path)
    source = _source()
    active = repository.activate_persona_revision(_persona_for_source(source))
    provider = _Provider()
    context = _ProviderContext(provider)
    tasks: set[object] = set()
    owner = _owner(active, repository, tasks)

    assert owner.schedule(
        _source(prompt="different frozen source"),
        config=_enabled_config(),
        context=context,
        origin_turn_generation=2,
    ) is False
    await asyncio.sleep(0)

    assert context.lookups == 0
    assert provider.calls == 0
    assert tasks == set()
    assert repository.read_genesis(active) is None


@pytest.mark.asyncio
async def test_retired_persona_completion_never_commits_activation(tmp_path: Path) -> None:
    repository = ScopeRepository(tmp_path)
    source = _source()
    active = repository.activate_persona_revision(_persona_for_source(source))
    provider = _Provider()
    context = _ProviderContext(provider)
    tasks: set[object] = set()
    owner = _owner(active, repository, tasks)

    assert owner.schedule(source, config=_enabled_config(), context=context, origin_turn_generation=3) is False
    await asyncio.wait_for(provider.entered.wait(), timeout=1)
    repository.retire_persona_revision(
        active,
        expected_lifecycle_generation=active.lifecycle_generation,
        reason="test-retire",
    )
    provider.release.set()
    await asyncio.gather(*list(tasks), return_exceptions=False)

    raw = json.loads(repository.genesis_path(active).read_text(encoding="utf-8"))
    assert raw["payload"].get("state") != "active"
    assert "accepted_profile" not in raw["payload"]


@pytest.mark.asyncio
@pytest.mark.parametrize("stale_kind", ["policy", "prompt"])
async def test_stale_provider_result_releases_only_global_lease(
    tmp_path: Path,
    stale_kind: str,
) -> None:
    repository = ScopeRepository(tmp_path)
    source = _source()
    active = repository.activate_persona_revision(_persona_for_source(source))
    provider = _Provider()
    context = _ProviderContext(provider)
    tasks: set[object] = set()
    owner = _owner(active, repository, tasks)
    config = _enabled_config()

    assert owner.schedule(source, config=config, context=context, origin_turn_generation=3) is False
    await asyncio.wait_for(provider.entered.wait(), timeout=1)
    before = repository.read_genesis(active)
    assert before is not None
    assert before.payload["state"] == "claimed"
    before_generation = before.generation
    before_payload = before.payload
    if stale_kind == "policy":
        config["sylanne_alpha_persona_genesis_provider_id"] = "changed"
    else:
        object.__setattr__(source, "prompt", "changed-frozen-prompt")
    provider.release.set()
    await asyncio.gather(*list(tasks), return_exceptions=False)

    snapshot = repository.read_genesis(active)
    assert snapshot is not None
    assert snapshot.generation == before_generation
    assert snapshot.payload == before_payload
    assert snapshot.payload["state"] == "claimed"
    assert "accepted_profile" not in snapshot.payload
    global_control = json.loads(
        (tmp_path / "persona-genesis-global.json").read_text(encoding="utf-8")
    )
    assert global_control["lease"] is None


@pytest.mark.asyncio
async def test_stale_provider_exception_releases_only_global_lease(tmp_path: Path) -> None:
    repository = ScopeRepository(tmp_path)
    source = _source()
    active = repository.activate_persona_revision(_persona_for_source(source))
    provider = _Provider(error=RuntimeError("provider failure"))
    context = _ProviderContext(provider)
    tasks: set[object] = set()
    owner = _owner(active, repository, tasks)
    config = _enabled_config()

    assert owner.schedule(source, config=config, context=context, origin_turn_generation=3) is False
    await asyncio.wait_for(provider.entered.wait(), timeout=1)
    before = repository.read_genesis(active)
    assert before is not None
    config["sylanne_alpha_persona_genesis_provider_id"] = "changed"
    provider.release.set()
    await asyncio.gather(*list(tasks), return_exceptions=False)

    snapshot = repository.read_genesis(active)
    assert snapshot is not None
    assert snapshot.generation == before.generation
    assert snapshot.payload == before.payload
    assert snapshot.payload["state"] == "claimed"
    global_control = json.loads(
        (tmp_path / "persona-genesis-global.json").read_text(encoding="utf-8")
    )
    assert global_control["lease"] is None


@pytest.mark.asyncio
async def test_stale_cancellation_releases_only_global_lease(tmp_path: Path) -> None:
    repository = ScopeRepository(tmp_path)
    source = _source()
    active = repository.activate_persona_revision(_persona_for_source(source))
    provider = _Provider()
    context = _ProviderContext(provider)
    tasks: set[object] = set()
    owner = _owner(active, repository, tasks)
    config = _enabled_config()

    assert owner.schedule(source, config=config, context=context, origin_turn_generation=3) is False
    await asyncio.wait_for(provider.entered.wait(), timeout=1)
    before = repository.read_genesis(active)
    assert before is not None
    config["sylanne_alpha_persona_genesis_provider_id"] = "changed"
    task = next(iter(tasks))
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0)

    snapshot = repository.read_genesis(active)
    assert snapshot is not None
    assert snapshot.generation == before.generation
    assert snapshot.payload == before.payload
    assert snapshot.payload["state"] == "claimed"
    global_control = json.loads(
        (tmp_path / "persona-genesis-global.json").read_text(encoding="utf-8")
    )
    assert global_control["lease"] is None


@pytest.mark.asyncio
async def test_retired_persona_cancellation_does_not_write_a_backoff(tmp_path: Path) -> None:
    repository = ScopeRepository(tmp_path)
    source = _source()
    active = repository.activate_persona_revision(_persona_for_source(source))
    provider = _Provider()
    context = _ProviderContext(provider)
    tasks: set[object] = set()
    owner = _owner(active, repository, tasks)

    assert owner.schedule(source, config=_enabled_config(), context=context, origin_turn_generation=3) is False
    await asyncio.wait_for(provider.entered.wait(), timeout=1)
    genesis_path = repository.genesis_path(active)
    before = genesis_path.read_bytes()
    repository.retire_persona_revision(
        active,
        expected_lifecycle_generation=active.lifecycle_generation,
        reason="test-retire-cancel",
    )
    task = next(iter(tasks))
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0)

    assert genesis_path.read_bytes() == before
    global_control = json.loads(
        (tmp_path / "persona-genesis-global.json").read_text(encoding="utf-8")
    )
    assert global_control["lease"] is None


@pytest.mark.asyncio
async def test_schema_failure_still_durably_backs_off_claim(tmp_path: Path) -> None:
    repository = ScopeRepository(tmp_path)
    source = _source()
    active = repository.activate_persona_revision(_persona_for_source(source))
    provider = _Provider(completion_text="{}")
    context = _ProviderContext(provider)
    tasks: set[object] = set()
    owner = _owner(active, repository, tasks)

    assert owner.schedule(source, config=_enabled_config(), context=context, origin_turn_generation=3) is False
    await asyncio.wait_for(provider.entered.wait(), timeout=1)
    provider.release.set()
    await asyncio.gather(*list(tasks), return_exceptions=False)

    snapshot = repository.read_genesis(active)
    assert snapshot is not None
    assert snapshot.payload["state"] == "backoff"
    global_control = json.loads(
        (tmp_path / "persona-genesis-global.json").read_text(encoding="utf-8")
    )
    assert global_control["lease"] is None


@pytest.mark.asyncio
async def test_awaiting_hook_creates_only_persona_control_owner_before_view(tmp_path: Path) -> None:
    from main import EmotionalStatePlugin

    repository = ScopeRepository(tmp_path)
    source = _source(
        prompt="durable-secret-canonical-prompt",
        begin_dialogs=(
            "durable-secret-author-example-one",
            "durable-secret-author-example-two",
        ),
    )
    persona = repository.activate_persona_revision(_persona_for_source(source))
    scope = repository.create_scope(_scope_for_persona(persona), expected_absent=True)
    runtime = PersonaRuntime(persona_ref=persona, genesis_required=True)

    def construct(target: PersonaRuntime) -> bool:
        target.self_core = object()
        target.autonomy_scheduler = object()
        return True

    runtime.persona_services_factory = construct
    registry = ScopeRuntimeRegistry(lambda _scope: runtime, repository=repository)
    provider = _Provider()
    plugin = SimpleNamespace(config=_enabled_config(), context=_ProviderContext(provider))

    ready = EmotionalStatePlugin._schedule_persona_genesis_before_view(
        plugin,
        registry,
        scope,
        source,
        turn_generation=6,
    )

    assert ready is None
    assert registry.persona_count == 1
    assert registry.session_count == 0
    runtime = registry.for_scope(scope)
    assert runtime.self_core is None
    assert runtime.autonomy_scheduler is None
    assert runtime.relation_runtimes == {}
    await asyncio.wait_for(provider.entered.wait(), timeout=1)
    provider.release.set()
    await asyncio.gather(*list(runtime.background_tasks))

    assert provider.calls == 1
    assert len(provider.requests) == 1
    provider_prompt, max_tokens, temperature = provider.requests[0]
    assert source.prompt in provider_prompt
    for begin_dialog in source.begin_dialogs:
        assert begin_dialog in provider_prompt
    assert "author-expression examples only" in provider_prompt
    assert "not real experiences" in provider_prompt
    assert max_tokens == 800
    assert temperature == 0.1
    for durable_path in (
        repository.genesis_path(persona),
        tmp_path / "persona-genesis-global.json",
    ):
        durable = durable_path.read_text(encoding="utf-8")
        assert source.prompt not in durable
        assert source.persona_id not in durable
        for begin_dialog in source.begin_dialogs:
            assert begin_dialog not in durable

    assert EmotionalStatePlugin._schedule_persona_genesis_before_view(
        plugin,
        registry,
        scope,
        source,
        turn_generation=7,
    ) is runtime
    assert registry.session_count == 0


@pytest.mark.parametrize(
    ("gate_key", "gate_value"),
    [
        ("sylanne_alpha_persona_genesis_enabled", False),
        ("sylanne_alpha_persona_genesis_enabled", 1),
        ("sylanne_alpha_persona_genesis_paid_opt_in", "true"),
    ],
)
def test_disabled_genesis_hook_passes_through_without_scheduling(
    tmp_path: Path,
    gate_key: str,
    gate_value: object,
) -> None:
    from main import EmotionalStatePlugin

    repository = ScopeRepository(tmp_path)
    source = _source()
    persona = repository.activate_persona_revision(_persona_for_source(source))
    scope = repository.create_scope(_scope_for_persona(persona), expected_absent=True)
    provider = _Provider()
    context = _ProviderContext(provider)
    config = _enabled_config()
    config[gate_key] = gate_value
    constructed: list[object] = []

    def construct(runtime: object) -> bool:
        constructed.append(runtime)
        runtime.self_core = object()
        runtime.autonomy_scheduler = object()
        return True

    plugin = SimpleNamespace(
        config=config,
        context=context,
        _construct_persona_services=construct,
    )
    runtime = EmotionalStatePlugin._create_persona_runtime(plugin, scope)
    registry = ScopeRuntimeRegistry(lambda _scope: runtime, repository=repository)

    assert EmotionalStatePlugin._schedule_persona_genesis_before_view(
        plugin,
        registry,
        scope,
        source,
        turn_generation=1,
    ) is runtime
    assert constructed == [runtime]
    assert context.lookups == 0
    assert provider.calls == 0
    assert runtime.background_tasks == set()
    assert repository.read_genesis(persona) is None


def test_gate_close_constructs_awaiting_persona_services_once(tmp_path: Path) -> None:
    from main import EmotionalStatePlugin

    repository = ScopeRepository(tmp_path)
    source = _source()
    persona = repository.activate_persona_revision(_persona_for_source(source))
    scope = repository.create_scope(_scope_for_persona(persona), expected_absent=True)
    provider = _Provider()
    context = _ProviderContext(provider)
    config = _enabled_config()
    constructed: list[object] = []

    def construct(runtime: object) -> bool:
        constructed.append(runtime)
        runtime.self_core = object()
        runtime.autonomy_scheduler = object()
        return True

    plugin = SimpleNamespace(
        config=config,
        context=context,
        _construct_persona_services=construct,
    )
    runtime = EmotionalStatePlugin._create_persona_runtime(plugin, scope)
    registry = ScopeRuntimeRegistry(lambda _scope: runtime, repository=repository)

    assert registry.for_scope(scope) is runtime
    assert constructed == []
    config["sylanne_alpha_persona_genesis_paid_opt_in"] = False

    for generation in (2, 3):
        assert EmotionalStatePlugin._schedule_persona_genesis_before_view(
            plugin,
            registry,
            scope,
            source,
            turn_generation=generation,
        ) is runtime

    assert constructed == [runtime]
    assert context.lookups == 0
    assert provider.calls == 0
    assert runtime.background_tasks == set()
    assert repository.read_genesis(persona) is None


def test_origin_turn_has_no_overlay_and_later_turn_uses_only_genesis_sink(tmp_path: Path) -> None:
    from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline

    repository = ScopeRepository(tmp_path)
    source = _source()
    active = repository.activate_persona_revision(_persona_for_source(source))
    lease = repository.claim_persona_genesis(
        active,
        source_fingerprint=active.source_fingerprint,
        origin_turn_generation=9,
        now_ms=1_700_000_000_000,
    )
    assert lease is not None
    repository.commit_persona_genesis_activation(
        active,
        lease,
        profile=_profile(),
        source_fingerprint=active.source_fingerprint,
        origin_turn_generation=9,
        now_ms=1_700_000_000_001,
    )
    owner = _owner(active, repository, set())
    added: list[tuple[object, ...]] = []
    request = SimpleNamespace(prompt="user words", system_prompt="static persona", contexts=[])
    binding = SimpleNamespace(
        persona_runtime=SimpleNamespace(persona_genesis=owner),
        request_runtime_view=SimpleNamespace(resolved=SimpleNamespace(turn_generation=9)),
    )
    plugin = SimpleNamespace(
        config=_enabled_config(),
        _bound_runtime=lambda: binding,
        _add_transient_context=lambda *args: added.append(args) or True,
    )
    pipeline = LLMRequestPipeline(plugin)

    assert pipeline._inject_persona_genesis_overlay(request) is False
    assert added == []
    binding.request_runtime_view.resolved.turn_generation = 10
    assert pipeline._inject_persona_genesis_overlay(request) is True
    assert len(added) == 1
    _request, channel, text, source_name, _priority, lifecycle = added[0]
    assert _request is request
    assert channel == "genesis"
    assert source_name == "persona_genesis"
    assert lifecycle == "turn"
    assert "traits_prior" in text and "voice_prior" in text
    assert request.prompt == "user words"
    assert request.system_prompt == "static persona"
    assert request.contexts == []


def test_persona_service_factory_is_atomic_and_never_claims_false_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import main as main_module
    from main import EmotionalStatePlugin

    class _Core:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

    class _Scheduler:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

    class _FailingPersistence:
        def _wire_memory_eviction_persistence(self, _store: object) -> None:
            raise RuntimeError("wire failed")

    class _WorkingPersistence:
        def _wire_memory_eviction_persistence(self, _store: object) -> None:
            return None

    monkeypatch.setattr(main_module, "SelfCore", _Core)
    monkeypatch.setattr(main_module, "AutonomyScheduler", _Scheduler)
    plugin = SimpleNamespace(_state_persistence=_FailingPersistence())
    runtime = PersonaRuntime(persona_ref=_persona())
    runtime.persona_services_factory = lambda target: EmotionalStatePlugin._construct_persona_services(
        plugin,
        target,
    )

    assert runtime.ensure_persona_services_ready(require_genesis=False) is False
    assert runtime.self_core is None
    assert runtime.autonomy_scheduler is None
    assert runtime.persona_services_ready is False

    plugin._state_persistence = _WorkingPersistence()
    assert runtime.ensure_persona_services_ready(require_genesis=False) is True
    assert isinstance(runtime.self_core, _Core)
    assert isinstance(runtime.autonomy_scheduler, _Scheduler)
    assert runtime.persona_services_ready is True

    empty = PersonaRuntime(persona_ref=_persona(1))
    assert empty.ensure_persona_services_ready(require_genesis=False) is False

    partial = PersonaRuntime(persona_ref=_persona(2))
    partial.self_core = object()
    partial.autonomy_scheduler = object()
    partial.persona_services_factory = lambda _target: False
    assert partial.ensure_persona_services_ready(require_genesis=False) is False
    assert partial.persona_services_ready is False

    lying = PersonaRuntime(persona_ref=_persona(3))
    lying.persona_services_factory = lambda _target: True
    assert lying.ensure_persona_services_ready(require_genesis=False) is False
    assert lying.persona_services_ready is False


def test_persona_genesis_owner_binding_is_exact_and_registry_rejects_sibling_owner(
    tmp_path: Path,
) -> None:
    repository = ScopeRepository(tmp_path)
    source_a = _source(prompt="owner-a")
    source_b = _source(prompt="owner-b")
    persona_a = repository.activate_persona_revision(_persona_for_source(source_a, index=1))
    persona_b = repository.activate_persona_revision(_persona_for_source(source_b, index=2))
    scope = repository.create_scope(_scope_for_persona(persona_a), expected_absent=True)
    runtime = PersonaRuntime(persona_ref=persona_a)
    other_tasks: set[object] = set()
    owner = _owner(persona_b, repository, other_tasks)
    check_binding = getattr(owner, "matches_binding", None)
    assert callable(check_binding), "Genesis owner must expose its narrow binding check"
    assert check_binding(persona_b, repository, other_tasks) is True
    assert check_binding(persona_a, repository, other_tasks) is False
    assert check_binding(persona_b, ScopeRepository(tmp_path / "other"), other_tasks) is False
    assert check_binding(persona_b, repository, set()) is False

    runtime.persona_genesis = owner
    registry = ScopeRuntimeRegistry(lambda _scope: runtime, repository=repository)
    with pytest.raises(ScopeMismatch, match="genesis owner"):
        registry.for_scope(scope)


def test_disabled_genesis_overlay_stops_before_bound_runtime_lookup() -> None:
    from sylanne_alpha.llm_request_pipeline import LLMRequestPipeline

    bound_calls: list[object] = []
    added: list[tuple[object, ...]] = []
    plugin = SimpleNamespace(
        config={
            "sylanne_alpha_persona_genesis_enabled": False,
            "sylanne_alpha_persona_genesis_paid_opt_in": True,
        },
        _bound_runtime=lambda: bound_calls.append(object()) or (_ for _ in ()).throw(
            AssertionError("disabled Genesis must not inspect the bound runtime")
        ),
        _add_transient_context=lambda *args: added.append(args) or True,
    )
    pipeline = LLMRequestPipeline(plugin)

    assert pipeline._inject_persona_genesis_overlay(SimpleNamespace()) is False
    assert bound_calls == []
    assert added == []


def test_replaced_global_lease_cannot_turn_an_expired_claim_into_backoff(tmp_path: Path) -> None:
    repository = ScopeRepository(tmp_path)
    first = repository.activate_persona_revision(_persona(10))
    second = repository.activate_persona_revision(_persona(11))
    now_ms = 1_700_000_000_000
    expired = repository.claim_persona_genesis(
        first,
        source_fingerprint=first.source_fingerprint,
        origin_turn_generation=1,
        now_ms=now_ms,
        lease_ms=1,
    )
    assert expired is not None
    before = repository.read_genesis(first)
    assert before is not None
    replacement = repository.claim_persona_genesis(
        second,
        source_fingerprint=second.source_fingerprint,
        origin_turn_generation=1,
        now_ms=now_ms + 2,
    )
    assert replacement is not None

    assert repository.reject_persona_genesis_claim(
        first,
        expired,
        source_fingerprint=first.source_fingerprint,
        now_ms=now_ms + 2,
    ) is False
    after = repository.read_genesis(first)
    assert after is not None
    assert after.generation == before.generation
    assert after.payload == before.payload
    global_control = json.loads(
        (tmp_path / "persona-genesis-global.json").read_text(encoding="utf-8")
    )
    assert global_control["lease"]["lease_id"] == replacement.lease_id


@pytest.mark.asyncio
async def test_expired_provider_call_does_not_write_backoff_over_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [1_700_000_000_000]
    monkeypatch.setattr(ScopeRepository, "_now_ms", staticmethod(lambda: clock[0]))
    repository = ScopeRepository(tmp_path)
    source = _source()
    active = repository.activate_persona_revision(_persona_for_source(source))
    provider = _Provider()
    context = _ProviderContext(provider)
    tasks: set[object] = set()
    owner = _owner(active, repository, tasks)

    assert owner.schedule(source, config=_enabled_config(), context=context, origin_turn_generation=3) is False
    await asyncio.wait_for(provider.entered.wait(), timeout=1)
    before = repository.read_genesis(active)
    assert before is not None
    clock[0] = before.payload["lease_expires_at_ms"] + 1
    provider.release.set()
    await asyncio.gather(*list(tasks), return_exceptions=False)

    after = repository.read_genesis(active)
    assert after is not None
    assert after.generation == before.generation
    assert after.payload == before.payload
    global_control = json.loads(
        (tmp_path / "persona-genesis-global.json").read_text(encoding="utf-8")
    )
    assert global_control["lease"] is None


@pytest.mark.asyncio
async def test_registry_retire_fences_owner_before_cancel_and_never_writes_backoff(
    tmp_path: Path,
) -> None:
    repository = ScopeRepository(tmp_path)
    source = _source()
    persona = repository.activate_persona_revision(_persona_for_source(source))
    scope = repository.create_scope(_scope_for_persona(persona), expected_absent=True)
    runtime = PersonaRuntime(persona_ref=persona, genesis_required=True)
    registry = ScopeRuntimeRegistry(lambda _scope: runtime, repository=repository)
    runtime = registry.for_scope(scope)
    owner = runtime.persona_genesis
    assert owner is not None
    provider = _Provider()

    assert owner.schedule(
        source,
        config=_enabled_config(),
        context=_ProviderContext(provider),
        origin_turn_generation=4,
    ) is False
    await asyncio.wait_for(provider.entered.wait(), timeout=1)
    task = next(iter(runtime.background_tasks))
    before = repository.read_genesis(persona)
    assert before is not None and before.payload["state"] == "claimed"

    assert registry.retire_persona(scope) is True
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0)

    after = repository.read_genesis(persona)
    assert after is not None
    assert after.generation == before.generation
    assert after.payload == before.payload
    assert owner.is_ready() is False
    assert owner.schedule(
        source,
        config=_enabled_config(),
        context=_ProviderContext(provider),
        origin_turn_generation=5,
    ) is False
    global_control = json.loads(
        (tmp_path / "persona-genesis-global.json").read_text(encoding="utf-8")
    )
    assert global_control["lease"] is None


@pytest.mark.asyncio
async def test_corrupt_genesis_is_quarantined_and_denied_only_for_that_revision(
    tmp_path: Path,
) -> None:
    repository = ScopeRepository(tmp_path)
    source = _source()
    active = repository.activate_persona_revision(_persona_for_source(source))
    now_ms = 1_700_000_000_000
    lease = repository.claim_persona_genesis(
        active,
        source_fingerprint=active.source_fingerprint,
        origin_turn_generation=1,
        now_ms=now_ms,
    )
    assert lease is not None
    assert repository.reject_persona_genesis_claim(
        active,
        lease,
        source_fingerprint=active.source_fingerprint,
        now_ms=now_ms + 1,
    )
    path = repository.genesis_path(active)
    corrupt = json.loads(path.read_text(encoding="utf-8"))
    corrupt["payload"]["extra"] = "must not be silently repaired"
    repository._atomic_json_replace(path, corrupt)

    assert repository.read_genesis(active) is None
    evidence = list((path.parent / "quarantine").glob("genesis.*.corrupt.json"))
    assert len(evidence) == 1
    assert json.loads(evidence[0].read_text(encoding="utf-8"))["payload"]["attempt"] == 1
    assert repository.persona_genesis_schedule_preflight_nowait(
        active,
        source_fingerprint=active.source_fingerprint,
    ) == "blocked"
    assert repository.persona_genesis_schedule_allowed(
        active,
        source_fingerprint=active.source_fingerprint,
    ) is False
    provider = _Provider()
    context = _ProviderContext(provider)
    tasks: set[object] = set()
    owner = _owner(active, repository, tasks)
    for generation in (2, 3):
        assert owner.schedule(
            source,
            config=_enabled_config(),
            context=context,
            origin_turn_generation=generation,
        ) is False
        assert repository.claim_persona_genesis(
            active,
            source_fingerprint=active.source_fingerprint,
            origin_turn_generation=generation,
        ) is None
    await asyncio.sleep(0)
    assert tasks == set()
    assert context.lookups == 0
    assert provider.calls == 0

    retired = repository.retire_persona_revision(
        active,
        expected_lifecycle_generation=active.lifecycle_generation,
        reason="corruption-new-revision",
    )
    assert retired.lifecycle_generation == active.lifecycle_generation + 1
    next_revision = repository.activate_persona_revision(active)
    assert next_revision.lifecycle_generation == retired.lifecycle_generation
    assert repository.persona_genesis_schedule_preflight_nowait(
        next_revision,
        source_fingerprint=next_revision.source_fingerprint,
    ) == "allowed"


class _ResolutionFailureContext:
    def __init__(self, *, unavailable: bool) -> None:
        self.unavailable = unavailable
        self.lookups = 0

    async def get_provider_by_id(self, _provider_id: str) -> object | None:
        self.lookups += 1
        if self.unavailable:
            return None
        raise RuntimeError("resolver unavailable")


class _HangingResolutionContext:
    def __init__(self) -> None:
        self.lookups = 0
        self._never = asyncio.Event()

    async def get_provider_by_id(self, _provider_id: str) -> object | None:
        self.lookups += 1
        await self._never.wait()
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize("unavailable", [False, True])
async def test_resolution_failure_uses_process_local_cooldown_without_claim(
    tmp_path: Path,
    unavailable: bool,
) -> None:
    repository = ScopeRepository(tmp_path)
    source = _source()
    active = repository.activate_persona_revision(_persona_for_source(source))
    context = _ResolutionFailureContext(unavailable=unavailable)
    tasks: set[object] = set()
    owner = _owner(active, repository, tasks)

    assert owner.schedule(source, config=_enabled_config(), context=context, origin_turn_generation=1) is False
    task = next(iter(tasks))
    await asyncio.gather(task, return_exceptions=False)
    assert tasks == set()
    assert context.lookups == 1
    assert repository.read_genesis(active) is None

    assert owner.schedule(source, config=_enabled_config(), context=context, origin_turn_generation=2) is False
    await asyncio.sleep(0)
    assert context.lookups == 1
    assert tasks == set()


@pytest.mark.asyncio
async def test_provider_resolution_timeout_never_claims_and_releases_provider_slot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sylanne_alpha.persona_genesis as persona_genesis

    monkeypatch.setattr(persona_genesis, "_GENESIS_RESOLUTION_TIMEOUT_SECONDS", 0.01)
    repository = ScopeRepository(tmp_path)
    source = _source()
    active = repository.activate_persona_revision(_persona_for_source(source))
    context = _HangingResolutionContext()
    tasks: set[object] = set()
    owner = _owner(active, repository, tasks)

    assert owner.schedule(source, config=_enabled_config(), context=context, origin_turn_generation=1) is False
    task = next(iter(tasks))
    await asyncio.gather(task, return_exceptions=False)

    assert context.lookups == 1
    assert repository.read_genesis(active) is None
    assert not (tmp_path / "persona-genesis-global.json").exists()
    with repository.persona_genesis_provider_slot() as acquired:
        assert acquired is True


@pytest.mark.asyncio
async def test_provider_call_timeout_backs_off_and_releases_slot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sylanne_alpha.persona_genesis as persona_genesis

    monkeypatch.setattr(persona_genesis, "_GENESIS_PROVIDER_TIMEOUT_SECONDS", 0.01)
    repository = ScopeRepository(tmp_path)
    source = _source()
    active = repository.activate_persona_revision(_persona_for_source(source))
    provider = _Provider()
    tasks: set[object] = set()
    owner = _owner(active, repository, tasks)

    assert owner.schedule(
        source,
        config=_enabled_config(),
        context=_ProviderContext(provider),
        origin_turn_generation=1,
    ) is False
    task = next(iter(tasks))
    await asyncio.wait_for(provider.entered.wait(), timeout=1)
    await asyncio.gather(task, return_exceptions=False)

    snapshot = repository.read_genesis(active)
    assert snapshot is not None and snapshot.payload["state"] == "backoff"
    global_control = json.loads(
        (tmp_path / "persona-genesis-global.json").read_text(encoding="utf-8")
    )
    assert global_control["lease"] is None
    with repository.persona_genesis_provider_slot() as acquired:
        assert acquired is True


@pytest.mark.asyncio
async def test_replaced_config_mapping_cancels_old_attempt_without_persona_write(
    tmp_path: Path,
) -> None:
    repository = ScopeRepository(tmp_path)
    source = _source()
    active = repository.activate_persona_revision(_persona_for_source(source))
    provider = _Provider()
    tasks: set[object] = set()
    owner = _owner(active, repository, tasks)
    old_config = _enabled_config()

    assert owner.schedule(
        source,
        config=old_config,
        context=_ProviderContext(provider),
        origin_turn_generation=3,
    ) is False
    task = next(iter(tasks))
    await asyncio.wait_for(provider.entered.wait(), timeout=1)
    before = repository.read_genesis(active)
    assert before is not None and before.payload["state"] == "claimed"

    replacement_config = _enabled_config()
    replacement_config["sylanne_alpha_persona_genesis_provider_id"] = "other-provider"
    assert owner.schedule(
        source,
        config=replacement_config,
        context=_ProviderContext(provider),
        origin_turn_generation=4,
    ) is False
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0)

    after = repository.read_genesis(active)
    assert after is not None
    assert after.generation == before.generation
    assert after.payload == before.payload
    assert tasks == set()
    assert provider.calls == 1
    global_control = json.loads(
        (tmp_path / "persona-genesis-global.json").read_text(encoding="utf-8")
    )
    assert global_control["lease"] is None


def test_utc_daily_budget_does_not_reset_when_clock_rolls_back(tmp_path: Path) -> None:
    repository = ScopeRepository(tmp_path)
    d1 = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    d2 = int(datetime(2026, 1, 2, tzinfo=timezone.utc).timestamp() * 1000)
    d3 = int(datetime(2026, 1, 3, tzinfo=timezone.utc).timestamp() * 1000)

    for index in range(32):
        active = repository.activate_persona_revision(_persona(index + 100))
        lease = repository.claim_persona_genesis(
            active,
            source_fingerprint=active.source_fingerprint,
            origin_turn_generation=0,
            now_ms=d2,
        )
        assert lease is not None
        assert repository.reject_persona_genesis_claim(
            active,
            lease,
            source_fingerprint=active.source_fingerprint,
            now_ms=d2 + 1,
            backoff_ms=0,
        )

    for index, now_ms in enumerate((d1, d2)):
        active = repository.activate_persona_revision(_persona(index + 200))
        assert repository.claim_persona_genesis(
            active,
            source_fingerprint=active.source_fingerprint,
            origin_turn_generation=0,
            now_ms=now_ms,
        ) is None

    next_day = repository.activate_persona_revision(_persona(202))
    assert repository.claim_persona_genesis(
        next_day,
        source_fingerprint=next_day.source_fingerprint,
        origin_turn_generation=0,
        now_ms=d3,
    ) is not None


def _make_constructing_plugin(config: dict[str, object], context: object) -> SimpleNamespace:
    def construct(runtime: PersonaRuntime) -> bool:
        runtime.self_core = object()
        runtime.autonomy_scheduler = object()
        return True

    return SimpleNamespace(
        config=config,
        context=context,
        _construct_persona_services=construct,
    )


@pytest.mark.asyncio
async def test_genesis_creation_mode_latches_baseline_across_gate_flips(tmp_path: Path) -> None:
    from main import EmotionalStatePlugin

    repository = ScopeRepository(tmp_path)
    source = _source()
    persona = repository.activate_persona_revision(_persona_for_source(source))
    scope = repository.create_scope(_scope_for_persona(persona), expected_absent=True)
    provider = _Provider()
    off_config: dict[str, object] = {}
    plugin = _make_constructing_plugin(off_config, _ProviderContext(provider))
    runtime = EmotionalStatePlugin._create_persona_runtime(plugin, scope)
    registry = ScopeRuntimeRegistry(lambda _scope: runtime, repository=repository)
    assert registry.exact_session(scope).scope == scope
    assert runtime.self_core is not None and runtime.autonomy_scheduler is not None
    assert runtime.genesis_baseline_latched is True

    plugin.config = _enabled_config()
    assert EmotionalStatePlugin._schedule_persona_genesis_before_view(
        plugin,
        registry,
        scope,
        source,
        turn_generation=1,
    ) is runtime
    assert provider.calls == 0
    assert runtime.background_tasks == set()

    on_persona = repository.activate_persona_revision(_persona_for_source(_source(prompt="on"), index=9))
    on_scope = repository.create_scope(_scope_for_persona(on_persona, index=9), expected_absent=True)
    on_source = _source(prompt="on")
    on_provider = _Provider()
    on_plugin = _make_constructing_plugin(_enabled_config(), _ProviderContext(on_provider))
    on_runtime = EmotionalStatePlugin._create_persona_runtime(on_plugin, on_scope)
    on_registry = ScopeRuntimeRegistry(lambda _scope: on_runtime, repository=repository)
    assert EmotionalStatePlugin._schedule_persona_genesis_before_view(
        on_plugin,
        on_registry,
        on_scope,
        on_source,
        turn_generation=2,
    ) is None
    await asyncio.wait_for(on_provider.entered.wait(), timeout=1)

    on_plugin.config = {}
    assert EmotionalStatePlugin._schedule_persona_genesis_before_view(
        on_plugin,
        on_registry,
        on_scope,
        on_source,
        turn_generation=3,
    ) is on_runtime
    old_task = next(iter(on_runtime.background_tasks))
    with pytest.raises(asyncio.CancelledError):
        await old_task
    assert on_runtime.genesis_baseline_latched is True

    on_plugin.config = _enabled_config()
    assert EmotionalStatePlugin._schedule_persona_genesis_before_view(
        on_plugin,
        on_registry,
        on_scope,
        on_source,
        turn_generation=4,
    ) is on_runtime
    assert on_provider.calls == 1
    assert on_runtime.background_tasks == set()


class _TerminateShadow:
    def __init__(self) -> None:
        self.begun = False

    def begin_shutdown(self) -> None:
        self.begun = True

    async def terminate(self) -> None:
        return None


class _TerminatePersistence:
    async def terminate(self) -> None:
        return None


async def _noop_async() -> None:
    return None


@pytest.mark.asyncio
async def test_plugin_terminate_synchronously_fences_genesis_and_rejects_new_schedule(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import main as main_module
    from main import EmotionalStatePlugin

    async def stop_webui() -> None:
        return None

    monkeypatch.setattr(main_module, "stop_webui_server", stop_webui)
    repository = ScopeRepository(tmp_path)
    source = _source()
    persona = repository.activate_persona_revision(_persona_for_source(source))
    scope = repository.create_scope(_scope_for_persona(persona), expected_absent=True)
    runtime = PersonaRuntime(persona_ref=persona, genesis_required=True)
    registry = ScopeRuntimeRegistry(lambda _scope: runtime, repository=repository)
    runtime = registry.for_scope(scope)
    owner = runtime.persona_genesis
    assert owner is not None
    provider = _Provider()
    context = _ProviderContext(provider)
    assert owner.schedule(
        source,
        config=_enabled_config(),
        context=context,
        origin_turn_generation=2,
    ) is False
    task = next(iter(runtime.background_tasks))
    await asyncio.wait_for(provider.entered.wait(), timeout=1)
    before = repository.read_genesis(persona)
    assert before is not None and before.payload["state"] == "claimed"

    plugin = SimpleNamespace(
        _v3_shadow=_TerminateShadow(),
        _scope_runtime_registry=registry,
        _background_tasks=[],
        _save_live_scoped_queue_checkpoints=_noop_async,
        _has_kv_api=lambda: False,
        _state_persistence=_TerminatePersistence(),
        config=_enabled_config(),
        context=context,
        _persona_genesis_shutting_down=False,
    )
    await EmotionalStatePlugin.terminate(plugin)

    assert plugin._persona_genesis_shutting_down is True
    assert plugin._v3_shadow.begun is True
    assert task.cancelled()
    assert runtime.background_tasks == set()
    after = repository.read_genesis(persona)
    assert after is not None
    assert after.generation == before.generation
    assert after.payload == before.payload
    with repository.persona_genesis_provider_slot() as acquired:
        assert acquired is True

    other_source = _source(prompt="new-after-shutdown")
    other_persona = repository.activate_persona_revision(_persona_for_source(other_source, index=41))
    other_scope = repository.create_scope(
        _scope_for_persona(other_persona, index=41),
        expected_absent=True,
    )
    assert EmotionalStatePlugin._schedule_persona_genesis_before_view(
        plugin,
        registry,
        other_scope,
        other_source,
        turn_generation=3,
    ) is None
    assert registry.persona_count == 1
    assert provider.calls == 1


def _hold_repository_lock_in_child(root: str, ready: object, release: object) -> None:
    repository = ScopeRepository(Path(root))
    try:
        with repository._repository_lock():
            ready.put(True)
            release.wait(20)
    except BaseException as exc:  # pragma: no cover - child errors are asserted by parent.
        ready.put(repr(exc))


@pytest.mark.asyncio
async def test_nowait_preflight_returns_fast_under_repository_lock_contention(
    tmp_path: Path,
) -> None:
    from main import EmotionalStatePlugin

    repository = ScopeRepository(tmp_path)
    source = _source()
    persona = repository.activate_persona_revision(_persona_for_source(source))
    scope = repository.create_scope(_scope_for_persona(persona), expected_absent=True)
    runtime = PersonaRuntime(persona_ref=persona, genesis_required=True)
    registry = ScopeRuntimeRegistry(lambda _scope: runtime, repository=repository)
    provider = _Provider()
    plugin = SimpleNamespace(config=_enabled_config(), context=_ProviderContext(provider))
    context = multiprocessing.get_context("spawn")
    ready = context.Queue()
    release = context.Event()
    holder = context.Process(
        target=_hold_repository_lock_in_child,
        args=(str(tmp_path), ready, release),
    )
    holder.start()
    assert ready.get(timeout=20) is True
    try:
        started = time.monotonic()
        assert EmotionalStatePlugin._schedule_persona_genesis_before_view(
            plugin,
            registry,
            scope,
            source,
            turn_generation=1,
        ) is None
        assert time.monotonic() - started < 0.5
        assert runtime.background_tasks == set()
        assert provider.calls == 0
    finally:
        release.set()
        holder.join(timeout=20)
        assert holder.exitcode == 0
