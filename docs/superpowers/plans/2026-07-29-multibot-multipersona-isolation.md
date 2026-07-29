# Multi-Bot / Multi-Persona Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every Sylanne runtime read, write, request overlay, history record, WebUI view, and delivery belong to one verified `Bot → PersonaRevision → Session` scope, while preserving the existing laboratory / visual-novel design language.

**Architecture:** Introduce one authoritative scope contract in front of the existing V2 runtime and V3 shadow path. AstrBot remains the read-only source of the effective Persona; Sylanne freezes that Persona revision for a turn, owns all mutable state below the frozen scope, emits dynamic context once through a temporary `TextPart`, and fails closed whenever Bot identity, parentage, or delivery account is ambiguous. The backend API and both WebUI hosts share one scoped service contract, so the frontend cannot recreate a cross-Bot fallback.

**Tech Stack:** Python 3.10–3.13, AstrBot 4.26.7 public plugin APIs, asyncio, dataclasses, HMAC-SHA256, atomic JSON/CAS persistence, pytest/pytest-asyncio, Vue 3, Pinia, TypeScript, Vitest, Vite, pnpm, agent-browser.

---

## Approved source and execution rules

- Design source: `docs/superpowers/specs/2026-07-29-multibot-multipersona-isolation-design.md`.
- This remains one release plan because identity, persistence, delivery, API, and UI share a single fail-closed cutover boundary. Shipping any track against the old raw `session_key` contract would recreate the isolation defect.
- Use one implementation writer at a time. Route ordinary bounded work to Terra High and non-trivial runtime/API/persistence work to Terra Max. Main Sol reviews every commit and owns the final acceptance decision.
- Do not alter unrelated untracked files. Stage only paths named by the active task.
- Use this PowerShell prefix for every command that may create temporary files:

```powershell
$env:TEMP='D:\bun\tmp\codex\Sylanne-next\temp'
$env:TMP=$env:TEMP
$env:TMPDIR=$env:TEMP
$env:PYTHONPATH='G:\Sylanne-next'
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
Set-Location 'G:\Sylanne-next'
```

- After the workstation restart, the WindowsApps `python.exe` launcher executes the installed Store Python 3.13.14 at `C:\Users\pidan\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\python.exe`; pytest 9.0.3 and ruff 0.15.20 are available. `E:\Anaconda\python.exe` also exists but is not the active PowerShell command. `pyright` is not installed in the active interpreter yet, so install the pinned project-compatible Pyright package in the task-scoped environment before Task 16 and record its version in the gate evidence.
- `pnpm build` rewrites tracked `UI/index.html` and `pages/dashboard/index.html`. Run it only in Task 16 and review those generated diffs.
- `.codegraph/` exists. Query CodeGraph before raw repository searches; when its index is stale for a target, record that fact and read only the affected raw files.

## Locked file structure

| Path | Responsibility |
|---|---|
| `sylanne_alpha/scope_contracts.py` | Immutable `BotRef`, Persona, Session, relation, resolved-turn, API echo, generation, and lease contracts. |
| `sylanne_alpha/scope_identity.py` | Bot binding validation, fail-closed account proof, HMAC derivation, Persona source canonicalization, and opaque storage tokens. |
| `sylanne_alpha/scope_repository.py` | `scope-v1` root, catalogs, atomic JSON commits, CAS generations, locks, and same-scope corruption quarantine. |
| `sylanne_alpha/session_catalog.py` | Bot-owned persisted transport-session binding, monotonic turn generation, frozen effective Persona, and protected delivery-intent issuer. |
| `sylanne_alpha/scope_runtime.py` | `Bot → PersonaRevision → Session/Relation` runtime ownership, frozen-scope lookup, and lifecycle release. |
| `sylanne_alpha/scoped_host_runtime.py` | AlphaKernel load/save adapter whose only backing store is the full-scope CAS repository. |
| `sylanne_alpha/persona_genesis.py` | Background single-flight LLM inference of the five allowed initial priors. |
| `sylanne_alpha/transient_context.py` | The only dynamic request-context sink; at most one Sylanne-tagged temporary `TextPart` per request. |
| `sylanne_alpha/scope_delivery.py` | Reactive turn leases plus the durable proactive delivery outbox and capability boundary. |
| `sylanne_alpha/scope_api.py` | Shared parent-path resolution, API errors, nonce scope, response echo, and stream generation checks. |
| `sylanne_alpha/legacy_scope_claim.py` | Read-only `legacy-unscoped` inventory and explicit copy-claim transaction. |
| `webui-src/src/stores/scope.ts` | Bot → Persona → Session catalog, selection persistence, and `selectionEpoch`. |
| `webui-src/src/components/persona/PersonaDossier.vue` | Focused read-only Persona modal that reuses the existing chamber tokens and motion. |

Existing `sylanne_alpha/v3bridge/*` remains a shadow implementation. It may consume an opaque scoped storage token, but it must not become the owner of `scope-v1`, delivery, or migration state.

## Frozen contracts

The implementation uses these names consistently:

```python
BotBinding = tuple[str, str]  # (platform_id, self_id), adapter boundary only
BotRefToken = str            # "bot_v1_<base64url>"
PersonaRefToken = str        # "persona_v1_<base64url>"
SessionRefToken = str        # "session_v1_<base64url>"
RelationRefToken = str       # "relation_v1_<base64url>"

# Persisted state key:
ScopeStorageToken = str      # HMAC(bot_ref, persona_ref, session_ref), no raw IDs
```

API response scope echo:

```json
{
  "scope": {
    "bot_ref": "bot_v1_...",
    "persona_ref": "persona_v1_...",
    "session_ref": "session_v1_..."
  },
  "scope_generation": 7,
  "resolved_at_ms": 1785260000000
}
```

Private API path:

```text
/api/bots/{bot_ref}/personas/{persona_ref}/sessions/{session_ref}/{resource}
```

AstrBot Pages route registration uses Flask-style `<bot_ref>` parameters; standalone aiohttp uses `{bot_ref}`. Both adapters call the same `ScopeApiService`.

### Task 1: Lock the AstrBot 4.26.7 compatibility boundary

**Files:**
- Create: `tests/integration/test_scope_astrbot_v4267_contract.py`
- Modify: `metadata.yaml`

- [ ] **Step 1: Write the failing compatibility test**

```python
from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

PLUGIN_NAME = "astrbot_plugin_sylanne"


def test_scope_runtime_uses_verified_astrbot_4267_contracts() -> None:
    astrbot = pytest.importorskip("astrbot")
    if getattr(astrbot, "__version__", "") != "4.26.7":
        pytest.skip("exact AstrBot 4.26.7 contract probe")

    from astrbot.api.star import StarTools
    from astrbot.core.agent.message import TextPart
    from astrbot.core.persona_mgr import PersonaManager
    from astrbot.core.platform.astr_message_event import AstrMessageEvent
    from astrbot.core.star.context import Context

    assert callable(StarTools.get_data_dir)
    assert list(inspect.signature(AstrMessageEvent.get_self_id).parameters) == ["self"]
    assert list(
        inspect.signature(PersonaManager.resolve_selected_persona).parameters
    ) == [
        "self",
        "umo",
        "conversation_persona_id",
        "platform_name",
        "provider_settings",
    ]
    assert list(inspect.signature(Context.register_web_api).parameters) == [
        "self",
        "route",
        "view_handler",
        "methods",
        "desc",
    ]

    part = TextPart(text="[sylanne_runtime_overlay]\nquiet")
    assert part.mark_as_temp() is part
    assert part._no_save is True

    async def view_handler(**path_params):
        return path_params

    fake_context = SimpleNamespace(registered_web_apis=[])
    Context.register_web_api(
        fake_context,
        f"/{PLUGIN_NAME}/api/bots/<bot_ref>",
        view_handler,
        ["GET"],
        "scope probe",
    )
    assert fake_context.registered_web_apis == [
        (
            f"/{PLUGIN_NAME}/api/bots/<bot_ref>",
            view_handler,
            ["GET"],
            "scope probe",
        )
    ]

    metadata = Path(__file__).parents[2] / "metadata.yaml"
    assert 'tested_astrbot_version: "4.26.7"' in metadata.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run the test and verify the current version declaration fails**

Run:

```powershell
python -m pytest tests/integration/test_scope_astrbot_v4267_contract.py -q
```

Expected: FAIL because the project metadata still allows an unverified AstrBot range rather than documenting the exact tested baseline, or SKIP when the environment is not 4.26.7. A SKIP is not an acceptance result.

- [ ] **Step 3: Record the verified baseline without narrowing supported installs**

Keep the existing compatibility range and add the tested baseline:

```yaml
astrbot_version: ">=4.26,<5.0.0"
tested_astrbot_version: "4.26.7"
```

Do not import `TextPart` from `astrbot.api.provider`; 4.26.7 does not export it there. Do not invent `send_message(..., self_id=...)`; neither `event.send` nor `Context.send_message` accepts that argument.

- [ ] **Step 4: Run the compatibility test in the real AstrBot environment**

Run:

```powershell
$env:PYTHONPATH='E:\AstrBot\backend\app;G:\Sylanne-next'
python -m pytest tests/integration/test_scope_astrbot_v4267_contract.py -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit the compatibility gate**

```powershell
git add metadata.yaml tests/integration/test_scope_astrbot_v4267_contract.py
git commit -m "test: lock scoped runtime AstrBot contracts"
```

### Task 2: Define opaque scope identities and Persona revisions

**Files:**
- Create: `sylanne_alpha/scope_contracts.py`
- Create: `sylanne_alpha/scope_identity.py`
- Create: `tests/test_scope_contracts.py`
- Create: `tests/test_scope_identity.py`
- Modify: `sylanne_alpha/v3bridge/session_identity.py`

- [ ] **Step 1: Write failing immutable-contract tests**

```python
from dataclasses import FrozenInstanceError

import pytest

from sylanne_alpha.scope_contracts import (
    BotRef,
    PersonaRevisionRef,
    SessionRef,
    SessionScope,
)


def test_scope_contracts_are_opaque_immutable_and_parented() -> None:
    bot = BotRef(token="bot_v1_A", generation=2)
    persona = PersonaRevisionRef(
        token="persona_v1_P",
        bot_ref=bot,
        persona_id_digest="f" * 64,
        source_fingerprint="a" * 64,
        lifecycle_generation=0,
    )
    session = SessionRef(token="session_v1_S", bot_ref=bot, generation=5)
    scope = SessionScope(
        bot_ref=bot,
        persona_ref=persona,
        session_ref=session,
        storage_token="scope_v1_X",
        scope_generation=3,
    )

    assert scope.storage_components() == (
        "bot_v1_A",
        "persona_v1_P",
        "session_v1_S",
    )
    with pytest.raises(FrozenInstanceError):
        scope.session_ref = session  # type: ignore[misc]


def test_scope_rejects_a_child_from_another_bot() -> None:
    bot_a = BotRef(token="bot_v1_A", generation=0)
    bot_b = BotRef(token="bot_v1_B", generation=0)
    persona_b = PersonaRevisionRef(
        token="persona_v1_PB",
        bot_ref=bot_b,
        persona_id_digest="b" * 64,
        source_fingerprint="c" * 64,
        lifecycle_generation=0,
    )
    session_a = SessionRef(token="session_v1_SA", bot_ref=bot_a, generation=0)

    with pytest.raises(ValueError, match="persona does not belong to bot"):
        SessionScope(
            bot_ref=bot_a,
            persona_ref=persona_b,
            session_ref=session_a,
            storage_token="scope_v1_X",
            scope_generation=0,
        )
```

- [ ] **Step 2: Run the contract tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_scope_contracts.py -q
```

Expected: FAIL with `ModuleNotFoundError: sylanne_alpha.scope_contracts`.

- [ ] **Step 3: Implement the immutable contract module**

Add these exact central types; later modules import them instead of redefining strings:

```python
from __future__ import annotations

from dataclasses import dataclass, field


def _require_token(value: str, prefix: str) -> None:
    if type(value) is not str or not value.startswith(prefix) or len(value) <= len(prefix):
        raise ValueError(f"invalid {prefix} token")


@dataclass(frozen=True, slots=True)
class BotRef:
    token: str
    generation: int

    def __post_init__(self) -> None:
        _require_token(self.token, "bot_v1_")
        if type(self.generation) is not int or self.generation < 0:
            raise ValueError("invalid bot generation")


@dataclass(frozen=True, slots=True)
class PersonaRevisionRef:
    token: str
    bot_ref: BotRef
    persona_id_digest: str
    source_fingerprint: str
    lifecycle_generation: int

    def __post_init__(self) -> None:
        _require_token(self.token, "persona_v1_")
        if len(self.persona_id_digest) != 64 or len(self.source_fingerprint) != 64:
            raise ValueError("invalid persona digest")
        if type(self.lifecycle_generation) is not int or self.lifecycle_generation < 0:
            raise ValueError("invalid persona lifecycle generation")


@dataclass(frozen=True, slots=True)
class SessionRef:
    token: str
    bot_ref: BotRef
    generation: int

    def __post_init__(self) -> None:
        _require_token(self.token, "session_v1_")
        if type(self.generation) is not int or self.generation < 0:
            raise ValueError("invalid session generation")


@dataclass(frozen=True, slots=True)
class SessionScope:
    bot_ref: BotRef
    persona_ref: PersonaRevisionRef
    session_ref: SessionRef
    storage_token: str
    scope_generation: int

    def __post_init__(self) -> None:
        if self.persona_ref.bot_ref != self.bot_ref:
            raise ValueError("persona does not belong to bot")
        if self.session_ref.bot_ref != self.bot_ref:
            raise ValueError("session does not belong to bot")
        _require_token(self.storage_token, "scope_v1_")
        if type(self.scope_generation) is not int or self.scope_generation < 0:
            raise ValueError("invalid scope generation")

    def storage_components(self) -> tuple[str, str, str]:
        return (
            self.bot_ref.token,
            self.persona_ref.token,
            self.session_ref.token,
        )
```

Complete the contract file with these immutable values:

```python
@dataclass(frozen=True, slots=True)
class PersonaScope:
    bot_ref: BotRef
    persona_ref: PersonaRevisionRef

    def __post_init__(self) -> None:
        if self.persona_ref.bot_ref != self.bot_ref:
            raise ValueError("persona does not belong to bot")


@dataclass(frozen=True, slots=True)
class RelationRef:
    token: str
    bot_ref: BotRef

    def __post_init__(self) -> None:
        _require_token(self.token, "relation_v1_")


@dataclass(frozen=True, slots=True)
class RelationScope:
    bot_ref: BotRef
    persona_ref: PersonaRevisionRef
    relation_ref: RelationRef
    relation_generation: int

    def __post_init__(self) -> None:
        if self.persona_ref.bot_ref != self.bot_ref:
            raise ValueError("persona does not belong to bot")
        if self.relation_ref.bot_ref != self.bot_ref:
            raise ValueError("relation does not belong to bot")
        if type(self.relation_generation) is not int or self.relation_generation < 0:
            raise ValueError("invalid relation generation")


@dataclass(frozen=True, slots=True)
class ResolvedTransportScope:
    bot_ref: BotRef
    session_ref: SessionRef
    identity_quality: str
    private_scope_enabled: bool
    disabled_reason: str | None


@dataclass(frozen=True, slots=True)
class ResolvedScope:
    scope: SessionScope | None
    persona_source: object | None
    identity_quality: str | None
    resolution_source: str | None
    resolved_at_ms: int
    private_scope_enabled: bool
    disabled_reason: str | None
    turn_generation: int | None

    @classmethod
    def disabled(cls, reason: str, *, resolved_at_ms: int) -> "ResolvedScope":
        return cls(None, None, None, None, resolved_at_ms, False, reason, None)


@dataclass(frozen=True, slots=True)
class ScopeDiagnosticEcho:
    bot_ref: str
    persona_ref: str
    session_ref: str
    scope_generation: int
    resolved_at_ms: int


@dataclass(frozen=True, slots=True)
class ScopeApiPathEcho:
    bot_ref: str
    persona_ref: str
    session_ref: str


@dataclass(frozen=True, slots=True)
class ScopeApiEcho:
    scope: ScopeApiPathEcho
    scope_generation: int
    resolved_at_ms: int


@dataclass(frozen=True, slots=True)
class PersonaApiPathEcho:
    bot_ref: str
    persona_ref: str


@dataclass(frozen=True, slots=True)
class PersonaApiEcho:
    scope: PersonaApiPathEcho
    scope_generation: int
    resolved_at_ms: int


@dataclass(frozen=True, slots=True)
class TurnDeliveryLease:
    transport_session_token: str
    resolved_scope_token: str
    session_generation: int
    scope_generation: int
    turn_generation: int

    def __post_init__(self) -> None:
        _require_token(self.transport_session_token, "session_v1_")
        _require_token(self.resolved_scope_token, "scope_v1_")
        if min(
            self.session_generation,
            self.scope_generation,
            self.turn_generation,
        ) < 0:
            raise ValueError("invalid delivery generation")


@dataclass(frozen=True, slots=True)
class ProactiveDeliveryLease:
    transport_session_token: str
    resolved_scope_token: str
    expected_persona_token: str
    persona_lifecycle_generation: int
    session_generation: int
    scope_generation: int
    expected_turn_generation: int
    expires_at_ms: int

    def __post_init__(self) -> None:
        _require_token(self.transport_session_token, "session_v1_")
        _require_token(self.resolved_scope_token, "scope_v1_")
        _require_token(self.expected_persona_token, "persona_v1_")
        if min(
            self.persona_lifecycle_generation,
            self.session_generation,
            self.scope_generation,
            self.expected_turn_generation,
            self.expires_at_ms,
        ) < 0:
            raise ValueError("invalid proactive delivery lease")


@dataclass(frozen=True, slots=True, repr=False)
class BotDeliveryRef:
    token: str
    delivery_id: str
    bot_ref: BotRef
    persona_ref: PersonaRevisionRef
    session_ref: SessionRef
    platform_id: str = field(repr=False)
    self_id: str = field(repr=False)
    target_address: str = field(repr=False)
    adapter_capability: str = field(repr=False)

    def __post_init__(self) -> None:
        _require_token(self.token, "delivery_v1_")
        if self.persona_ref.bot_ref != self.bot_ref:
            raise ValueError("delivery persona does not belong to bot")
        if self.session_ref.bot_ref != self.bot_ref:
            raise ValueError("delivery session does not belong to bot")


@dataclass(frozen=True, slots=True, repr=False)
class ProactiveIntentDraft:
    delivery_ref: BotDeliveryRef
    lease: ProactiveDeliveryLease
    text: str = field(repr=False)
    idempotent: bool
    issuer_mac: str = field(repr=False)
```

`ResolvedScope` never contains raw prompt text or raw IDs. `persona_source` is typed as `PersonaSource | None` under `TYPE_CHECKING` to avoid a runtime import cycle. `ScopeDiagnosticEcho` is the flat, opaque record used only in bounded diagnostics; Session resources serialize the nested `ScopeApiEcho`, and Persona-level resources serialize `PersonaApiEcho` with `scope_generation=persona_ref.lifecycle_generation`. Public serializers never call `dataclasses.asdict()` on the diagnostic type.

- [ ] **Step 4: Write the failing identity tests**

```python
from sylanne_alpha.scope_identity import (
    BotBinding,
    PersonaSource,
    ScopeIdentityKey,
)


def test_bot_and_session_refs_include_self_id_and_bot_parent() -> None:
    key = ScopeIdentityKey(key_id="scope-key", secret=b"k" * 32)
    bot_a = key.bot_ref(BotBinding("adapter", "10001"), generation=0)
    bot_b = key.bot_ref(BotBinding("adapter", "10002"), generation=0)
    session_a = key.session_ref(
        bot_a,
        platform_id="adapter",
        canonical_umo="adapter:GroupMessage:42",
        generation=0,
    )
    session_b = key.session_ref(
        bot_b,
        platform_id="adapter",
        canonical_umo="adapter:GroupMessage:42",
        generation=0,
    )

    assert bot_a != bot_b
    assert session_a != session_b


def test_cross_platform_same_self_id_and_session_generation_do_not_alias() -> None:
    key = ScopeIdentityKey(key_id="scope-key", secret=b"k" * 32)
    qq = key.bot_ref(BotBinding("qq-adapter", "10001"), generation=0)
    tg = key.bot_ref(BotBinding("telegram-adapter", "10001"), generation=0)
    session_v0 = key.session_ref(
        qq,
        platform_id="qq-adapter",
        canonical_umo="qq-adapter:FriendMessage:42",
        generation=0,
    )
    session_v1 = key.session_ref(
        qq,
        platform_id="qq-adapter",
        canonical_umo="qq-adapter:FriendMessage:42",
        generation=1,
    )

    assert qq != tg
    assert session_v0 != session_v1
    assert key.session_ref(
        qq,
        platform_id="qq-adapter",
        canonical_umo="qq-adapter:FriendMessage:42",
        generation=0,
    ) == session_v0


def test_persona_revision_preserves_none_vs_empty_tool_semantics() -> None:
    key = ScopeIdentityKey(key_id="scope-key", secret=b"k" * 32)
    bot = key.bot_ref(BotBinding("adapter", "10001"), generation=0)
    all_tools = PersonaSource("guide", "prompt", (), None, None, "default")
    no_tools = PersonaSource("guide", "prompt", (), (), (), "default")

    assert key.persona_revision(
        bot,
        all_tools,
        lifecycle_generation=0,
    ) != key.persona_revision(
        bot,
        no_tools,
        lifecycle_generation=0,
    )


def test_persona_revision_changes_for_content_or_persona_id() -> None:
    key = ScopeIdentityKey(key_id="scope-key", secret=b"k" * 32)
    bot = key.bot_ref(BotBinding("adapter", "10001"), generation=0)
    base = PersonaSource("guide", "prompt A", (), None, None, "default")
    changed = PersonaSource("guide", "prompt B", (), None, None, "default")
    renamed = PersonaSource("guide-2", "prompt A", (), None, None, "default")

    assert key.persona_revision(
        bot,
        base,
        lifecycle_generation=0,
    ) != key.persona_revision(
        bot,
        changed,
        lifecycle_generation=0,
    )
    assert key.persona_revision(
        bot,
        base,
        lifecycle_generation=0,
    ) != key.persona_revision(
        bot,
        renamed,
        lifecycle_generation=0,
    )


def test_persona_lifecycle_generation_fences_recreation_without_changing_identity() -> None:
    key = ScopeIdentityKey(key_id="scope-key", secret=b"k" * 32)
    bot = key.bot_ref(BotBinding("adapter", "10001"), generation=0)
    source = PersonaSource("guide", "prompt A", (), None, None, "default")

    original = key.persona_revision(bot, source, lifecycle_generation=0)
    recreated = key.persona_revision(bot, source, lifecycle_generation=1)

    assert original.token == recreated.token
    assert original != recreated


def test_same_sender_has_a_distinct_relation_ref_for_each_bot() -> None:
    key = ScopeIdentityKey(key_id="scope-key", secret=b"k" * 32)
    bot_a = key.bot_ref(BotBinding("adapter", "10001"), generation=0)
    bot_b = key.bot_ref(BotBinding("adapter", "10002"), generation=0)

    relation_a = key.relation_ref(
        bot_a,
        platform_realm="qq",
        subject_kind="user",
        authenticated_subject_id="42",
    )
    relation_b = key.relation_ref(
        bot_b,
        platform_realm="qq",
        subject_kind="user",
        authenticated_subject_id="42",
    )

    assert relation_a != relation_b


def test_embodiment_persona_is_rejected() -> None:
    key = ScopeIdentityKey(key_id="scope-key", secret=b"k" * 32)
    bot = key.bot_ref(BotBinding("adapter", "10001"), generation=0)
    source = PersonaSource(
        "sylanne_embodiment_session",
        "prompt",
        (),
        None,
        None,
        "conversation",
    )

    try:
        key.persona_revision(bot, source, lifecycle_generation=0)
    except ValueError as exc:
        assert str(exc) == "managed embodiment persona is forbidden"
    else:
        raise AssertionError("embodiment persona was accepted")
```

- [ ] **Step 5: Run the identity tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_scope_identity.py -q
```

Expected: FAIL because `scope_identity.py` does not exist.

- [ ] **Step 6: Implement domain-separated HMAC identity derivation**

```python
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass, field
from typing import Protocol

from sylanne_alpha.scope_contracts import (
    BotRef,
    PersonaRevisionRef,
    RelationRef,
    SessionRef,
)

_BOT_DOMAIN = b"sylanne.scope.bot.v1\x00"
_PERSONA_DOMAIN = b"sylanne.scope.persona.v1\x00"
_SESSION_DOMAIN = b"sylanne.scope.session.v1\x00"
_RELATION_DOMAIN = b"sylanne.scope.relation.v1\x00"


def _token(prefix: str, digest: bytes) -> str:
    encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return prefix + encoded


def _frame(value: str) -> bytes:
    encoded = value.encode("utf-8")
    if not encoded or len(encoded) > 4096:
        raise ValueError("invalid identity component")
    return len(encoded).to_bytes(4, "big") + encoded


@dataclass(frozen=True, slots=True, repr=False)
class BotBinding:
    platform_id: str
    self_id: str

    def __post_init__(self) -> None:
        _frame(self.platform_id)
        _frame(self.self_id)


@dataclass(frozen=True, slots=True, repr=False)
class PersonaSource:
    persona_id: str
    prompt: str
    begin_dialogs: tuple[str, ...]
    tools: tuple[str, ...] | None
    skills: tuple[str, ...] | None
    resolution_source: str

    def canonical_bytes(self) -> bytes:
        payload = {
            "begin_dialogs": list(self.begin_dialogs),
            "persona_id": self.persona_id,
            "prompt": self.prompt,
            "resolution_source": self.resolution_source,
            "skills": None if self.skills is None else sorted(self.skills),
            "tools": None if self.tools is None else sorted(self.tools),
        }
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class ScopeIdentityKey:
    key_id: str
    secret: bytes = field(repr=False)

    def __post_init__(self) -> None:
        _frame(self.key_id)
        if type(self.secret) is not bytes or len(self.secret) < 32:
            raise ValueError("scope secret must contain at least 32 bytes")

    def _digest(self, domain: bytes, *values: str) -> bytes:
        payload = domain + _frame(self.key_id) + b"".join(_frame(value) for value in values)
        return hmac.new(self.secret, payload, hashlib.sha256).digest()

    def bot_ref(self, binding: BotBinding, *, generation: int) -> BotRef:
        digest = self._digest(
            _BOT_DOMAIN,
            binding.platform_id,
            binding.self_id,
            str(generation),
        )
        return BotRef(_token("bot_v1_", digest), generation)

    def persona_revision(
        self,
        bot_ref: BotRef,
        source: PersonaSource,
        *,
        lifecycle_generation: int,
    ) -> PersonaRevisionRef:
        if source.persona_id.startswith("sylanne_embodiment_"):
            raise ValueError("managed embodiment persona is forbidden")
        if type(lifecycle_generation) is not int or lifecycle_generation < 0:
            raise ValueError("invalid persona lifecycle generation")
        source_fingerprint = hashlib.sha256(source.canonical_bytes()).hexdigest()
        persona_id_digest = hashlib.sha256(source.persona_id.encode("utf-8")).hexdigest()
        digest = self._digest(
            _PERSONA_DOMAIN,
            bot_ref.token,
            persona_id_digest,
            source_fingerprint,
        )
        return PersonaRevisionRef(
            token=_token("persona_v1_", digest),
            bot_ref=bot_ref,
            persona_id_digest=persona_id_digest,
            source_fingerprint=source_fingerprint,
            lifecycle_generation=lifecycle_generation,
        )

    def session_ref(
        self,
        bot_ref: BotRef,
        *,
        platform_id: str,
        canonical_umo: str,
        generation: int,
    ) -> SessionRef:
        digest = self._digest(
            _SESSION_DOMAIN,
            bot_ref.token,
            platform_id,
            canonical_umo,
            str(generation),
        )
        return SessionRef(_token("session_v1_", digest), bot_ref, generation)

    def scope_token(
        self,
        bot_ref: BotRef,
        persona_ref: PersonaRevisionRef,
        session_ref: SessionRef,
    ) -> str:
        if persona_ref.bot_ref != bot_ref or session_ref.bot_ref != bot_ref:
            raise ValueError("scope parent mismatch")
        digest = self._digest(
            b"sylanne.scope.storage.v1\x00",
            bot_ref.token,
            persona_ref.token,
            session_ref.token,
        )
        return _token("scope_v1_", digest)

    def relation_ref(
        self,
        bot_ref: BotRef,
        *,
        platform_realm: str,
        subject_kind: str,
        authenticated_subject_id: str,
    ) -> RelationRef:
        digest = self._digest(
            _RELATION_DOMAIN,
            bot_ref.token,
            platform_realm,
            subject_kind,
            authenticated_subject_id,
        )
        return RelationRef(_token("relation_v1_", digest), bot_ref)
```

The Persona token is the stable identity of `(BotRef, persona_id, source_fingerprint)` and deliberately excludes `lifecycle_generation`. The repository, not callers, owns that lifecycle counter. Resolution first derives a generation-0 candidate, then `ScopeRepository.activate_persona_revision(candidate)` returns the authoritative generation from the Persona manifest; the candidate generation is never trusted for an existing Persona.

Add the account-proof boundary:

```python
@dataclass(frozen=True, slots=True)
class AdapterAccountProof:
    platform_id: str
    bot_ref: BotRef
    proof_generation: int
    verified_at_ms: int
    expires_at_ms: int
    account_set_digest: str
    account_count: int


@dataclass(frozen=True, slots=True)
class CurrentAdapterAccountProof:
    proof: AdapterAccountProof
    current_account_set_digest: str
    current_proof_generation: int


class AdapterAccountProofProvider(Protocol):
    def current(self, platform_id: str) -> CurrentAdapterAccountProof | None: ...


class NoAdapterAccountProofProvider:
    def current(self, platform_id: str) -> None:
        return None


def resolve_proven_single_account(
    proof: AdapterAccountProof | None,
    *,
    platform_id: str,
    current_account_set_digest: str,
    current_proof_generation: int,
    now_ms: int,
) -> BotRef | None:
    if proof is None:
        return None
    if proof.platform_id != platform_id:
        return None
    if proof.account_count != 1:
        return None
    if proof.proof_generation != current_proof_generation:
        return None
    if proof.account_set_digest != current_account_set_digest:
        return None
    if proof.verified_at_ms > now_ms or now_ms >= proof.expires_at_ms:
        return None
    return proof.bot_ref
```

`NoAdapterAccountProofProvider` is the production default. AstrBot 4.26.7 exposes no general public API for enumerating the current account set, so only a separately tested adapter integration may register a provider. That provider must obtain the live account set from the adapter, advance its proof generation whenever the set changes, and start unproven after process restart until it has re-observed the live set. Only an adapter-supplied current proof may call `resolve_proven_single_account`; a catalog containing one historically observed account is not a proof and never enters this function.

Add identity tests proving `NoAdapterAccountProofProvider().current("adapter") is None`, a changed account-set digest/generation rejects a previously valid proof, and a newly constructed provider after restart cannot reuse the old in-memory proof.

- [ ] **Step 7: Keep V3 identity shadow-only**

Add a type-level guard to `sylanne_alpha/v3bridge/session_identity.py`:

```python
SCOPE_V1_AUTHORITY = False
```

Add an assertion to `tests/test_scope_identity.py`:

```python
from sylanne_alpha.v3bridge import session_identity


def test_v3_session_identity_is_not_scope_authority() -> None:
    assert session_identity.SCOPE_V1_AUTHORITY is False
```

- [ ] **Step 8: Run identity and existing V3 identity tests**

Run:

```powershell
python -m pytest tests/test_scope_contracts.py tests/test_scope_identity.py tests/test_v3_session_identity.py -q
```

Expected: all selected tests pass.

- [ ] **Step 9: Commit identity contracts**

```powershell
git add sylanne_alpha/scope_contracts.py sylanne_alpha/scope_identity.py sylanne_alpha/v3bridge/session_identity.py tests/test_scope_contracts.py tests/test_scope_identity.py
git commit -m "feat: add opaque multibot scope identities"
```

### Task 3: Build the authoritative scope repository

**Files:**
- Create: `sylanne_alpha/scope_repository.py`
- Create: `sylanne_alpha/session_catalog.py`
- Create: `tests/test_scope_repository.py`
- Create: `tests/test_session_catalog.py`
- Modify: `sylanne_alpha/scope_identity.py`
- Modify: `sylanne_alpha/infra.py`
- Modify: `sylanne_alpha/v3bridge/session_identity.py`
- Reference only: `sylanne_alpha/v3bridge/_state_repository.py`

- [ ] **Step 1: Write failing atomicity, CAS, and quarantine tests**

```python
import json
from dataclasses import replace

import pytest

from sylanne_alpha.scope_identity import load_or_create_scope_identity_key
from sylanne_alpha.scope_repository import (
    ScopeRepository,
    StaleScopeWrite,
)
from sylanne_alpha.session_catalog import SessionCatalog


def test_scope_repository_rejects_stale_generation(tmp_path) -> None:
    repo = ScopeRepository(tmp_path)
    token = ("bot_v1_A", "persona_v1_P", "session_v1_S")
    first = repo.write_session(token, expected_generation=0, payload={"value": "A"})

    assert first == 1
    with pytest.raises(StaleScopeWrite):
        repo.write_session(token, expected_generation=0, payload={"value": "B"})
    assert repo.read_session(token).payload == {"value": "A"}


def test_corrupt_snapshot_is_quarantined_inside_its_scope(tmp_path) -> None:
    repo = ScopeRepository(tmp_path)
    token = ("bot_v1_A", "persona_v1_P", "session_v1_S")
    path = repo.session_path(token)
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")

    assert repo.read_session(token) is None
    quarantined = list((path.parent / "quarantine").glob("snapshot.*.corrupt.json"))
    assert len(quarantined) == 1
    assert json.loads(repo.catalog_path.read_text(encoding="utf-8"))["generation"] == 1


def test_scope_identity_secret_is_stable_and_corruption_fails_closed(tmp_path) -> None:
    first = load_or_create_scope_identity_key(tmp_path / "identity.key")
    second = load_or_create_scope_identity_key(tmp_path / "identity.key")
    assert first.key_id == second.key_id

    (tmp_path / "identity.key").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="scope identity key"):
        load_or_create_scope_identity_key(tmp_path / "identity.key")


def test_scope_lifecycle_generation_has_one_authoritative_record(
    tmp_path,
    scope,
) -> None:
    repo = ScopeRepository(tmp_path)
    active = repo.create_scope(scope, expected_absent=True)
    repo.write_component(
        active,
        "memory",
        expected_generation=0,
        payload={"items": []},
    )
    unchanged = repo.resolve_scope(active.storage_token)
    invalidated = repo.invalidate_scope(
        active,
        expected_scope_generation=active.scope_generation,
        reason="reset",
    )

    assert unchanged.scope_generation == active.scope_generation
    assert invalidated.scope_generation == active.scope_generation + 1
    with pytest.raises(StaleScopeWrite):
        repo.invalidate_scope(
            active,
            expected_scope_generation=active.scope_generation,
            reason="purge",
        )


def test_persona_retire_and_reactivate_preserve_identity_and_fence_stale_writes(
    tmp_path,
    scope,
) -> None:
    repo = ScopeRepository(tmp_path)
    active = repo.activate_persona_revision(scope.persona_ref)
    retired = repo.retire_persona_revision(
        active,
        expected_lifecycle_generation=active.lifecycle_generation,
        reason="purge",
    )
    recreated = repo.activate_persona_revision(scope.persona_ref)

    assert retired.token == active.token == recreated.token
    assert recreated.lifecycle_generation == active.lifecycle_generation + 1
    with pytest.raises(StaleScopeWrite):
        repo.write_genesis(
            active,
            expected_lifecycle_generation=active.lifecycle_generation,
            payload={"traits_prior": {}},
        )


def test_transport_catalog_persists_monotonic_turn_and_blocks_unfrozen_restart(
    tmp_path,
    transport_scope,
    scope,
    protected_delivery_binding,
) -> None:
    repo = ScopeRepository(tmp_path)
    catalog = SessionCatalog(repo)
    first = catalog.begin_turn(transport_scope, protected_delivery_binding)
    frozen = catalog.freeze_persona(first, scope)

    restarted = SessionCatalog(ScopeRepository(tmp_path))
    restored = restarted.current(transport_scope.session_ref.token)
    assert restored.turn_generation == frozen.turn_generation
    assert restored.turn_state == "frozen"
    assert restored.active_persona_ref == scope.persona_ref.token

    second = restarted.begin_turn(transport_scope, protected_delivery_binding)
    restarted_again = SessionCatalog(ScopeRepository(tmp_path))
    unresolved = restarted_again.current(transport_scope.session_ref.token)
    assert second.turn_generation == frozen.turn_generation + 1
    assert unresolved.turn_state == "resolving"
    assert restarted_again.can_issue_proactive(unresolved) is False


def test_same_transport_a_to_b_to_a_never_reuses_a_turn_generation(
    tmp_path,
    transport_scope,
    scopes,
    protected_delivery_binding,
) -> None:
    catalog = SessionCatalog(ScopeRepository(tmp_path))
    generations = []
    for scope in (
        scopes.bot_a_persona_a,
        scopes.bot_a_persona_b,
        scopes.bot_a_persona_a,
    ):
        turn = catalog.begin_turn(transport_scope, protected_delivery_binding)
        generations.append(catalog.freeze_persona(turn, scope).turn_generation)

    assert generations == sorted(set(generations))
```

- [ ] **Step 2: Run the repository tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_scope_repository.py -q
```

Expected: FAIL because `ScopeRepository` is not defined.

- [ ] **Step 3: Add the only permitted `scope-v1` root adapter**

In `sylanne_alpha/infra.py`, add:

```python
from pathlib import Path


def resolve_scope_v1_root() -> Path:
    from astrbot.api.star import StarTools

    root = StarTools.get_data_dir("astrbot_plugin_sylanne") / "scope-v1"
    root.mkdir(parents=True, exist_ok=True)
    return root
```

This function must not call `resolve_data_root()` and must not move, rename, or import an old directory.

- [ ] **Step 4: Create a stable owner-only scope secret**

Move the audited owner-only secret-file primitive from `v3bridge/session_identity.py` into `infra.py` without changing its Windows ACL, POSIX mode, exclusive-create, fsync, corruption, or size checks. Keep the V3 loader calling the shared primitive so its existing tests remain valid.

`scope_identity.py` uses a distinct magic and key-ID domain:

```python
_SCOPE_KEY_MAGIC = b"SYLANNE-SCOPE-IDENTITY\x01\x00"


def load_or_create_scope_identity_key(path: Path) -> ScopeIdentityKey:
    secret = load_or_create_owner_only_secret(
        path,
        magic=_SCOPE_KEY_MAGIC,
        secret_bytes=32,
        error_label="scope identity key",
    )
    digest = hashlib.sha256(b"sylanne.scope.key-id.v1\x00" + secret).hexdigest()
    return ScopeIdentityKey(key_id=f"scope-key-v1-{digest[:32]}", secret=secret)
```

A malformed existing key fails closed and is never silently replaced. The binding catalog stores only an HMAC binding digest and generation. A newly observed `(platform_id, self_id)` gets its own generation-0 entry; a changed `self_id` creates a second binding rather than updating the first. Rebind/transfer requires an explicit audited admin transaction.

- [ ] **Step 5: Implement the repository transaction**

The repository must serialize:

```json
{
  "schema_version": "sylanne.scope.snapshot.v1",
  "generation": 1,
  "payload": {"value": "A"}
}
```

Use this write order in `ScopeRepository.write_session`:

```python
def write_session(
    self,
    components: tuple[str, str, str],
    *,
    expected_generation: int,
    payload: dict[str, object],
) -> int:
    path = self.session_path(components)
    current = self.read_session(components)
    actual = 0 if current is None else current.generation
    if actual != expected_generation:
        raise StaleScopeWrite(expected_generation, actual)
    next_generation = actual + 1
    document = {
        "schema_version": "sylanne.scope.snapshot.v1",
        "generation": next_generation,
        "payload": payload,
    }
    self._atomic_json_replace(path, document)
    self._commit_catalog_generation()
    return next_generation
```

`_atomic_json_replace` writes a same-directory unique temporary file with `open(..., "x")`, flushes and `os.fsync()`s it, uses `os.replace()`, then fsyncs the parent directory when supported. Mutating methods hold the existing repository-compatible interprocess lock pattern from `v3bridge/_state_repository.py`; do not share V3 manifests or pointers.

Required layout:

```text
scope-v1/
  identity.key
  catalog.json
  bots/<bot_token>/
    manifest.json
    transport-sessions/<session_token>/
      catalog.json
      delivery-binding.json
    personas/<persona_token>/
      manifest.json
      genesis.json
      runtime.json
      sessions/<session_token>/
        scope-meta.json
        snapshot.json
      relations/<relation_token>/snapshot.json
      relations/<relation_token>/relation-meta.json
      delivery/outbox.json
  observation/
    manifest.json
    scopes/<scope_storage_token>/
      active.jsonl
      segment-<opaque_sequence>.jsonl
```

Only opaque tokens may appear in these paths. A damaged snapshot moves to `quarantine/` beneath its own session, persona, or bot directory; the reader returns `None` and records a diagnostic rather than loading a sibling scope.

`SessionCatalog` is Bot-owned and persisted under `bots/<bot_token>/transport-sessions/<session_token>/`; it is not stored below a Persona. `catalog.json` contains only opaque refs and generations:

```json
{
  "schema_version": "sylanne.transport.session.v1",
  "bot_ref": "bot_v1_...",
  "session_ref": "session_v1_...",
  "session_generation": 2,
  "turn_generation": 19,
  "turn_state": "frozen",
  "active_persona_ref": "persona_v1_...",
  "persona_lifecycle_generation": 4,
  "active_scope_token": "scope_v1_...",
  "scope_generation": 7,
  "binding_digest": "opaque-hmac",
  "identity_quality": "event_self_id",
  "updated_at_ms": 1785260000000
}
```

The sibling owner-only `delivery-binding.json` contains the exact platform ID, self ID, canonical AstrBot `MessageSession`/target address, adapter capability, current account-proof digest/generation/expiry, and binding generation. Its filename and ordinary diagnostics remain opaque; raw fields are never returned by APIs or logged. It uses the same restrictive ACL/mode primitive as the scope identity key.

`SessionCatalog.begin_turn(ResolvedTransportScope, ProtectedDeliveryBinding)` holds the repository lock, verifies the active Bot binding and Session generation, increments the persisted `turn_generation`, writes the current protected address/proof, sets `turn_state="resolving"`, and clears the prior active Persona/scope fields before returning a frozen turn record. `freeze_persona(turn, SessionScope)` under the same lock verifies the exact current turn plus active Persona/scope parent generations, then records `turn_state="frozen"` and the effective Persona/scope. `current(session_ref_token: str)` accepts only an opaque `session_v1_` token and revalidates its Bot-owned catalog parent before returning a record; the same signature is used by reactive and proactive validators. A restart reloads the monotonic counter; a persisted `resolving` turn stays fail-closed and cannot send proactively until a later turn is fully frozen. No in-memory counter is authoritative.

Each `personas/<persona_token>/manifest.json` is the sole authority for `PersonaRevisionRef.lifecycle_generation` and its `active`/`retired` state. `activate_persona_revision(candidate)` validates the candidate's Bot, Persona token, Persona ID digest, and source fingerprint, then returns the persisted generation; it never resets an existing Persona to generation 0. Retirement/purge CAS-increments this generation before cancelling Persona tasks, invalidating child scopes, and deleting or rebuilding any Persona-owned state. Reactivation of the same source keeps the same opaque Persona token and the incremented generation.

`scope-meta.json` is the sole authority for `SessionScope.scope_generation`:

```json
{
  "schema_version": "sylanne.scope.meta.v1",
  "storage_token": "scope_v1_...",
  "scope_generation": 3,
  "state": "active",
  "bot_ref": "bot_v1_...",
  "persona_ref": "persona_v1_...",
  "session_ref": "session_v1_...",
  "updated_at_ms": 1785260000000,
  "last_transition": "reset"
}
```

Ordinary component writes use their own snapshot generations and do not change `scope_generation`. Reset, purge, meltdown, explicit Session invalidation, Bot binding invalidation, PersonaRevision retirement, and delete/recreate first CAS-increment the scope lifecycle generation and invalidate in-memory tasks/leases/streams before clearing or rebuilding state. A content change creates a new PersonaRevision/storage token and invalidates the old scope; a restart alone does not bump it. Recreate never resets an existing token to generation 0.

`ScopeRepository.resolve_scope(storage_token)` reads the parent catalog and `scope-meta.json` under one lock and returns the complete `SessionScope`. `ScopeResolver`, `SessionCatalog`, `ScopeApiService`, `ReactiveDeliveryCoordinator`, background writers, SSE/WS, and the frontend catalog all consume this same persisted generation reader; none infer it from a component generation.

`ScopeRepository.write_genesis()` and every Persona-level commit require the frozen `PersonaRevisionRef.lifecycle_generation` and compare it against the Persona manifest under the same lock. A stale background task may record a bounded diagnostic, but it cannot recreate `genesis.json`, `runtime.json`, a child scope, or an in-memory Persona runtime after retirement.

- [ ] **Step 6: Run repository unit and multiprocess regression tests**

Run:

```powershell
python -m pytest tests/test_scope_repository.py tests/test_session_catalog.py tests/test_v3_repository_cas.py tests/test_v3_repository_multiprocess.py -q
```

Expected: all selected tests pass; V3 regressions remain unchanged.

- [ ] **Step 7: Commit the authoritative repository**

```powershell
git add sylanne_alpha/infra.py sylanne_alpha/scope_identity.py sylanne_alpha/scope_repository.py sylanne_alpha/session_catalog.py sylanne_alpha/v3bridge/session_identity.py tests/test_scope_repository.py tests/test_session_catalog.py
git commit -m "feat: add atomic scoped state repository"
```

### Task 4: Resolve and freeze the effective AstrBot Persona

**Files:**
- Create: `tests/test_scope_persona_resolution.py`
- Create: `tests/integration/test_scope_astrbot_hook_order.py`
- Modify: `sylanne_alpha/scope_identity.py`
- Modify: `sylanne_alpha/scope_contracts.py`
- Modify: `sylanne_alpha/session_catalog.py`
- Modify: `main.py`
- Modify: `sylanne_alpha/protocols.py`

- [ ] **Step 1: Write failing resolver tests**

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from sylanne_alpha.scope_identity import ScopeResolver


class _Session:
    platform_id = "adapter"

    def __str__(self) -> str:
        return "adapter:FriendMessage:42"


@pytest.mark.asyncio
async def test_resolver_uses_astrbot_effective_persona_and_freezes_it() -> None:
    manager = SimpleNamespace(
        resolve_selected_persona=AsyncMock(
            return_value=(
                "narrator",
                {
                    "name": "narrator",
                    "prompt": "calm observer",
                    "begin_dialogs": ["hello"],
                    "tools": None,
                    "skills": [],
                },
                None,
                False,
            )
        )
    )
    context = SimpleNamespace(
        persona_manager=manager,
        get_config=lambda *, umo: {"provider_settings": {"default_personality": "narrator"}},
    )
    event = SimpleNamespace(
        session=_Session(),
        unified_msg_origin="adapter:FriendMessage:42",
        get_platform_id=lambda: "adapter",
        get_platform_name=lambda: "aiocqhttp",
        get_self_id=lambda: "10001",
        get_extra=lambda key, default=None: default,
        set_extra=lambda key, value: setattr(event, key, value),
    )
    request = SimpleNamespace(conversation=SimpleNamespace(persona_id=None))

    resolved = await ScopeResolver.for_test(context).resolve(event, request)

    assert resolved.persona_source.persona_id == "narrator"
    assert resolved.persona_source.prompt == "calm observer"
    assert resolved.scope.bot_ref.token.startswith("bot_v1_")
    assert resolved.scope.persona_ref.token.startswith("persona_v1_")
    manager.resolve_selected_persona.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolver_fails_closed_for_missing_bot_or_managed_persona() -> None:
    resolver = ScopeResolver.for_test(None)

    missing_bot = await resolver.resolve_test_values(
        platform_id="adapter",
        self_id="",
        umo="adapter:FriendMessage:42",
        persona_id="narrator",
    )
    managed = await resolver.resolve_test_values(
        platform_id="adapter",
        self_id="10001",
        umo="adapter:FriendMessage:42",
        persona_id="sylanne_embodiment_42",
    )

    assert missing_bot.private_scope_enabled is False
    assert managed.private_scope_enabled is False


@pytest.mark.asyncio
async def test_missing_self_uses_only_a_current_single_account_proof(
    resolver,
    account_proof,
) -> None:
    resolved = await resolver.resolve_test_values(
        platform_id="adapter",
        self_id="",
        umo="adapter:FriendMessage:42",
        persona_id="narrator",
        proof=account_proof.with_values(
            account_count=1,
            expires_at_ms=2_000,
            account_set_digest="current",
        ),
        current_account_set_digest="current",
        current_proof_generation=account_proof.proof_generation,
        now_ms=1_000,
    )
    expired = await resolver.resolve_test_values(
        platform_id="adapter",
        self_id="",
        umo="adapter:FriendMessage:42",
        persona_id="narrator",
        proof=account_proof.with_values(
            account_count=1,
            expires_at_ms=999,
            account_set_digest="current",
        ),
        current_account_set_digest="current",
        current_proof_generation=account_proof.proof_generation,
        now_ms=1_000,
    )

    assert resolved.private_scope_enabled is True
    assert resolved.identity_quality == "single_account_proven"
    assert expired.private_scope_enabled is False
    assert expired.disabled_reason == "bot_identity_unverified"


@pytest.mark.asyncio
async def test_empty_or_wrong_platform_umo_fails_closed(resolver) -> None:
    empty = await resolver.resolve_test_values(
        platform_id="adapter",
        self_id="10001",
        umo="",
        persona_id="narrator",
    )
    conflict = await resolver.resolve_test_values(
        platform_id="adapter",
        self_id="10001",
        umo="other:FriendMessage:42",
        persona_id="narrator",
    )

    assert empty.disabled_reason == "transport_session_unverified"
    assert conflict.disabled_reason == "umo_platform_conflict"


@pytest.mark.asyncio
async def test_third_party_request_without_conversation_is_not_given_private_overlay(
    resolver,
) -> None:
    result = await resolver.resolve_test_request(conversation=None)

    assert result.private_scope_enabled is False
    assert result.disabled_reason == "persona_application_unverified"
```

Use `unittest.mock.AsyncMock` in the actual import; do not add a pytest-specific mock dependency.

- [ ] **Step 2: Run the resolver tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_scope_persona_resolution.py -q
```

Expected: FAIL because `ScopeResolver` does not exist.

- [ ] **Step 3: Implement the verified resolver call**

`ScopeResolver.resolve()` must use exactly this AstrBot call:

```python
cfg = self._context.get_config(umo=event.unified_msg_origin)
selected_id, personality, forced_id, is_webchat_special = (
    await self._context.persona_manager.resolve_selected_persona(
        umo=event.unified_msg_origin,
        conversation_persona_id=(
            request.conversation.persona_id if request.conversation else None
        ),
        platform_name=event.get_platform_name(),
        provider_settings=cfg.get("provider_settings", {}),
    )
)
```

Before treating the resolver result as an applied base Persona, require `request.conversation is not None`. AstrBot 4.26.7's third-party Agent branch fires the hook with a bare `ProviderRequest` and does not run the main Agent Persona decoration; that branch returns `ResolvedScope.disabled("persona_application_unverified", resolved_at_ms=now_ms)` and receives no Sylanne private overlay or state write.

Then enforce:

```python
now_ms = self._clock_ms()
self_id = str(event.get_self_id() or "")
platform_id = str(event.get_platform_id() or "")
session = getattr(event, "session", None)
canonical_umo = str(session) if session is not None else ""
session_platform_id = str(getattr(session, "platform_id", "") or "")
if not platform_id or not canonical_umo:
    return ResolvedScope.disabled(
        "transport_session_unverified",
        resolved_at_ms=now_ms,
    )
if session_platform_id != platform_id:
    return ResolvedScope.disabled(
        "umo_platform_conflict",
        resolved_at_ms=now_ms,
    )
if self_id:
    bot_ref = self._identity.bot_ref(
        BotBinding(platform_id, self_id),
        generation=self._catalog.binding_generation(platform_id, self_id),
    )
    identity_quality = "event_self_id"
else:
    current_proof = self._account_proofs.current(platform_id)
    if current_proof is None:
        return ResolvedScope.disabled(
            "bot_identity_unverified",
            resolved_at_ms=now_ms,
        )
    bot_ref = resolve_proven_single_account(
        current_proof.proof,
        platform_id=platform_id,
        current_account_set_digest=current_proof.current_account_set_digest,
        current_proof_generation=current_proof.current_proof_generation,
        now_ms=now_ms,
    )
    if bot_ref is None:
        return ResolvedScope.disabled(
            "bot_identity_unverified",
            resolved_at_ms=now_ms,
        )
    identity_quality = "single_account_proven"
if selected_id in (None, "[%None]", "_chatui_default_") or personality is None:
    return ResolvedScope.disabled("persona_unavailable", resolved_at_ms=now_ms)
if selected_id.startswith("sylanne_embodiment_"):
    return ResolvedScope.disabled(
        "managed_persona_forbidden",
        resolved_at_ms=now_ms,
    )
```

Construct `ScopeResolver` with `NoAdapterAccountProofProvider` unless an explicitly supported adapter module supplies a live provider. The resolver and proactive outbox call `current(platform_id)` on every resolution/send attempt; neither caches a positive result across a turn, account-set change, or restart.

Build `PersonaSource` from `personality["prompt"]`, `["begin_dialogs"]`, `["tools"]`, and `["skills"]`; never fingerprint `request.system_prompt` or `request.contexts`. Derive a generation-0 Persona candidate only to calculate its stable opaque token, then replace it with `self._repository.activate_persona_revision(candidate)`, which supplies the authoritative lifecycle generation. Resolve/create the Session scope beneath that exact returned Persona revision, then call `self._session_catalog.freeze_persona(transport_turn, scope)` and store its persisted `turn_generation` in `ResolvedScope`. Save the immutable result with `event.set_extra("_sylanne_resolved_scope_v1", resolved)`. Every later hook reads that exact object and never asks PersonaManager or the current catalog selection again for the same turn.

The successful `ResolvedScope` stores the `identity_quality` chosen above, the persisted full `SessionScope`, the static `PersonaSource`, AstrBot resolution source, and `now_ms`. The resolver records `forced_id`/conversation/default as safe resolution metadata but does not expose the raw prompt through the API.

- [ ] **Step 4: Split transport freeze from Persona freeze in `main.py`**

At the start of `on_message`, resolve `ResolvedTransportScope`, build a `ProtectedDeliveryBinding` only from the current original event/adapter boundary, call `SessionCatalog.begin_turn()`, and attach both transport records:

```python
platform_id = str(event.get_platform_id() or "")
self_id = str(event.get_self_id() or "")
session = getattr(event, "session", None)
canonical_umo = str(session) if session is not None else ""
```

```python
event.set_extra("_sylanne_transport_scope_v1", transport_scope)
event.set_extra("_sylanne_transport_turn_v1", transport_turn)
```

`ProtectedDeliveryBinding` contains the exact original `MessageSession`, platform/self IDs, target address, current adapter capability, and current account proof; it is never reconstructed from a raw UMO or historical catalog entry. At the start of `on_llm_request`, resolve the effective Persona and use only the attached transport turn. `freeze_persona()` must succeed before attaching `ResolvedScope`, constructing a runtime, creating a reactive lease, or issuing a proactive intent.

Temporary transport-safety exception until Task 9 replaces the legacy segmented-delivery fence: after `begin_turn()` has published exact transport extras and the attached resolving turn, binding authority, canonical event session, and durable catalog record have been revalidated, `on_message` may (a) set the event-local `enable_streaming=False` takeover flag and (b) interrupt/fence an already active legacy segmented delivery. The compatibility locator must be independently reconstructed from the same non-empty canonical event, must equal the legacy `SessionContext` locator, and must reject `"default"`, empty, or mismatched values. This exception may touch only the legacy delivery epoch/active-turn registries; it is not an identity source and must not read or write host, memory, relationship, scheduler, life, rhythm, authenticated-sender, Persona, or other private runtime state. Task 9 removes this bridge in favor of the opaque transport-keyed reactive lease.

Add an integration assertion to `tests/integration/test_scope_astrbot_hook_order.py`: `begin_turn` occurs once in `on_message`, `freeze_persona` occurs once after AstrBot Persona resolution in `on_llm_request`, and no runtime/lease/outbox call occurs before the frozen record exists. When either step is disabled or mismatched, leave the turn `resolving`/invalid, return control to AstrBot without reading, writing, scheduling, or delivering Sylanne private state. Do not use `"default"`, the first session, or `_most_recent_host_key()` as a scope fallback.

- [ ] **Step 5: Run resolver, hook-order, and AstrBot compatibility tests**

Run:

```powershell
python -m pytest tests/test_scope_persona_resolution.py tests/integration/test_scope_astrbot_hook_order.py tests/integration/test_scope_astrbot_v4267_contract.py -q
```

Expected: all selected tests pass. Task 7 updates the old manager integration assertion in the same commit that removes the obsolete PersonaManager-write path, so no intermediate commit knowingly leaves a regression red.

- [ ] **Step 6: Commit frozen scope resolution**

```powershell
git add main.py sylanne_alpha/protocols.py sylanne_alpha/scope_contracts.py sylanne_alpha/scope_identity.py sylanne_alpha/session_catalog.py tests/test_scope_persona_resolution.py tests/integration/test_scope_astrbot_hook_order.py
git commit -m "feat: freeze effective persona scope per turn"
```

### Task 5: Give each Bot and Persona its own mutable runtime

**Files:**
- Create: `sylanne_alpha/scope_runtime.py`
- Create: `tests/test_scope_runtime.py`
- Modify: `main.py`
- Modify: `sylanne_alpha/session_state_store.py`
- Modify: `sylanne_alpha/session_context.py`
- Modify: `sylanne_alpha/background_queue.py`
- Modify: `sylanne_alpha/protocols.py`
- Modify: `sylanne_alpha/v2core/integration.py`

- [ ] **Step 1: Write failing A → B → A and sibling-release tests**

```python
from sylanne_alpha.scope_runtime import ScopeRuntimeRegistry


def test_persona_switch_restores_exact_runtime_without_cross_bot_aliasing(scopes) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    a1, b1, a2 = scopes.bot_a_persona_a, scopes.bot_a_persona_b, scopes.bot_b_persona_a

    registry.for_scope(a1).store.last_user_texts.set(a1.storage_token, "A")
    registry.for_scope(b1).store.last_user_texts.set(b1.storage_token, "B")
    registry.for_scope(a2).store.last_user_texts.set(a2.storage_token, "other bot")

    assert registry.for_scope(a1).store.last_user_texts.get(a1.storage_token) == "A"
    assert registry.for_scope(b1).store.last_user_texts.get(b1.storage_token) == "B"
    assert registry.for_scope(a2).store.last_user_texts.get(a2.storage_token) == "other bot"


def test_releasing_one_scope_does_not_mutate_siblings(scopes) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    left = registry.for_scope(scopes.bot_a_persona_a)
    right = registry.for_scope(scopes.bot_b_persona_a)
    right.store.last_bot_texts.set(scopes.bot_b_persona_a.storage_token, "safe")

    registry.release_session(scopes.bot_a_persona_a)

    assert right.store.last_bot_texts.get(scopes.bot_b_persona_a.storage_token) == "safe"


def test_runtime_never_selects_a_sibling_session(scopes) -> None:
    registry = ScopeRuntimeRegistry.for_test()
    first = scopes.bot_a_persona_a
    second = scopes.bot_a_persona_a_second_session
    registry.for_scope(second).store.last_user_texts.set(
        second.storage_token,
        "sibling",
    )

    assert registry.exact_session(first).storage_token == first.storage_token
    assert registry.exact_session_or_none(None) is None
    assert (
        registry.for_scope(first).store.last_user_texts.get(first.storage_token)
        is None
    )
```

Put reusable deterministic scope fixtures in `tests/scope_fixtures.py`; they use only opaque tokens and never raw production secrets.

- [ ] **Step 2: Run the runtime tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_scope_runtime.py -q
```

Expected: FAIL because `ScopeRuntimeRegistry` does not exist.

- [ ] **Step 3: Implement nested runtime ownership**

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from sylanne_alpha.scope_contracts import PersonaRevisionRef, SessionScope
from sylanne_alpha.session_state_store import SessionStateStore


class ScopeMismatch(RuntimeError):
    pass


@dataclass(slots=True)
class PersonaRuntime:
    persona_ref: PersonaRevisionRef
    store: SessionStateStore = field(default_factory=SessionStateStore)
    memory_factory: Callable[[SessionScope], object] = field(
        default=lambda _scope: object(),
        repr=False,
    )
    memory_systems: dict[str, object] = field(default_factory=dict)
    life_simulator: object | None = None
    rhythm_learner: object | None = None
    social_field: object | None = None
    proactive_scheduler: object | None = None
    generation: int = 0

    def memory_system_for(self, scope: SessionScope) -> object:
        if scope.persona_ref != self.persona_ref:
            raise ScopeMismatch("memory scope does not belong to runtime")
        memory = self.memory_systems.get(scope.storage_token)
        if memory is None:
            memory = self.memory_factory(scope)
            self.memory_systems[scope.storage_token] = memory
        return memory


@dataclass(frozen=True, slots=True)
class ScopedSessionRuntime:
    scope: SessionScope
    store: SessionStateStore

    @property
    def storage_token(self) -> str:
        return self.scope.storage_token


class ScopeRuntimeRegistry:
    def __init__(self, runtime_factory) -> None:
        self._runtime_factory = runtime_factory
        self._personas: dict[tuple[str, str, int], PersonaRuntime] = {}
        self._sessions: dict[
            tuple[str, str, int, str, int],
            ScopedSessionRuntime,
        ] = {}

    def for_scope(self, scope) -> PersonaRuntime:
        key = (
            scope.bot_ref.token,
            scope.persona_ref.token,
            scope.persona_ref.lifecycle_generation,
        )
        runtime = self._personas.get(key)
        if runtime is None:
            runtime = self._runtime_factory(scope)
            self._personas[key] = runtime
        return runtime

    def exact_session(self, scope: SessionScope) -> ScopedSessionRuntime:
        key = (
            scope.bot_ref.token,
            scope.persona_ref.token,
            scope.persona_ref.lifecycle_generation,
            scope.storage_token,
            scope.scope_generation,
        )
        session = self._sessions.get(key)
        if session is None:
            session = ScopedSessionRuntime(scope=scope, store=self.for_scope(scope).store)
            self._sessions[key] = session
        return session

    def exact_session_or_none(
        self,
        scope: SessionScope | None,
    ) -> ScopedSessionRuntime | None:
        return None if scope is None else self.exact_session(scope)

    def release_session(self, scope) -> None:
        runtime = self.for_scope(scope)
        runtime.store.release_session(scope.storage_token)
        self._sessions.pop(
            (
                scope.bot_ref.token,
                scope.persona_ref.token,
                scope.persona_ref.lifecycle_generation,
                scope.storage_token,
                scope.scope_generation,
            ),
            None,
        )
```

`retire_persona()` first advances the repository Persona lifecycle generation, removes the old `(bot token, persona token, lifecycle generation)` entry, and cancels its tasks. A later request may construct only the new generation. Registry lookup never aliases an old runtime to the same-token recreated Persona.

`ResolvedScope.storage_token` is derived by `ScopeIdentityKey` from all three opaque parents. It replaces raw `session_key` in every `SessionMap`, lock, host, V2 runtime, pending turn, metric, and background-task key.

- [ ] **Step 4: Move mutable global owners behind the registry**

In `main.py`, replace construction of global mutable owners:

```python
self._store = SessionStateStore()
self._life_simulator = LifeSimulator(...)
self._rhythm_learner = RhythmLearner(...)
self._social_field = SocialFieldCollector(...)
```

with:

```python
self._scope_runtime_registry = ScopeRuntimeRegistry(self._create_persona_runtime)
```

`_create_persona_runtime(resolved_scope)` constructs a new `SessionStateStore`, `LifeSimulator`, `RhythmLearner`, `SocialFieldCollector`, and `ProactiveScheduler` for that Bot + Persona revision. Shared read-only configuration, provider handles, model weights, authentication, and the WebUI server remain on the plugin.

It also owns the `BackgroundPostQueue` service for that Persona. Queue/worker/checkpoint maps and device-context state are Session-owned and keyed by the frozen `scope.storage_token`; relation age, first impression, and ritual state are Relation-owned beneath the Persona runtime. The process-wide worker budget may count opaque active workers, but it cannot own queue contents, select a Session, or persist state. There is no plugin-global `RitualRegistry`.

Add:

```python
def _runtime_for_event(self, event):
    resolved = event.get_extra("_sylanne_resolved_scope_v1")
    if resolved is None or not resolved.private_scope_enabled:
        raise ScopeUnavailable("resolved private scope is unavailable")
    return self._scope_runtime_registry.for_scope(resolved.scope)
```

Pipelines receive a request-bound runtime view containing the frozen scope and these owners. They must not read plugin-global `_store`, `_life_simulator`, `_rhythm_learner`, `_social_field`, or `_proactive_scheduler`.

Move `SessionContext._first_interaction_times`, `_first_impressions`, and `_ritual_registry` into the owning `RelationRuntime`; move `_device_fingerprints` into `ScopedSessionRuntime`. If no authenticated `RelationScope` exists, relation age/impression/ritual observation is skipped rather than written to a Session/default/global bucket.

- [ ] **Step 5: Cut raw-key helpers out of the active path**

Keep `session_context.session_key()`, `safe_session_key()`, and `resolve_public_session_key()` only inside explicitly named legacy readers. Active hook and pipeline signatures use `ResolvedScope` and `scope.storage_token`.

Replace:

```python
self._memory_system_for_session("default")
self._llm_request_pipeline._most_recent_host_key()
```

with:

```python
persona_runtime = self._scope_runtime_registry.for_scope(scope)
memory_system = persona_runtime.memory_system_for(scope)
session_runtime = self._scope_runtime_registry.exact_session(scope)
```

Delete `_most_recent_host_key()` and every “most recent”, first, or default session fallback from active code. An operation with a frozen scope uses only that exact `scope.storage_token`; an operation without it returns unavailable/fail-closed. Proactive work is addressed by Task 10's durable `BotDeliveryRef`, never by selecting a recent Session.

- [ ] **Step 6: Move V2 runtime and pending state to the frozen storage token**

In `sylanne_alpha/v2core/integration.py`, require `ResolvedScope` and index `_v2core_runtimes`, pending decisions, and Session persistence callbacks by `scope.storage_token`. Relationship registers are not Session-owned: Task 6 moves them behind `RelationScope.relation_ref.token`, the owning Persona lifecycle generation, and a RelationRuntime lock so the same authenticated user shares the intended relationship across Sessions without crossing Bot or Persona boundaries. Add this regression:

```python
def test_v2core_same_raw_session_isolated_by_full_scope(scopes, integration) -> None:
    left = integration.runtime_for(scopes.bot_a_persona_a)
    right = integration.runtime_for(scopes.bot_b_persona_a)

    assert left is not right
    assert left.storage_token != right.storage_token
```

- [ ] **Step 7: Run runtime, store, context, and V2 tests**

Run:

```powershell
python -m pytest tests/test_scope_runtime.py tests/test_final_full_architecture.py tests/test_issue43_reset_ghost_cleanup.py tests/test_v2core_bridge.py tests/test_v2core_full_turn.py -q
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit runtime ownership**

```powershell
git add main.py sylanne_alpha/protocols.py sylanne_alpha/scope_runtime.py sylanne_alpha/session_state_store.py sylanne_alpha/session_context.py sylanne_alpha/background_queue.py sylanne_alpha/v2core/integration.py tests/scope_fixtures.py tests/test_scope_runtime.py
git commit -m "refactor: isolate mutable runtime by bot persona scope"
```

### Task 6: Cut every active state path over to the scoped repository

**Files:**
- Create: `tests/test_scope_persistence_isolation.py`
- Create: `tests/test_scope_background_queue.py`
- Modify: `tests/integration/test_scope_astrbot_hook_order.py`
- Modify: `tests/test_wave_l2_t2_05_t2_06_followup_ritual.py`
- Modify: `tests/test_scope_runtime.py`
- Create: `sylanne_alpha/scoped_host_runtime.py`
- Modify: `sylanne_alpha/scope_contracts.py`
- Modify: `sylanne_alpha/scope_identity.py`
- Modify: `sylanne_alpha/scope_repository.py`
- Modify: `sylanne_alpha/scope_runtime.py`
- Modify: `sylanne_alpha/state_persistence.py`
- Modify: `sylanne_alpha/background_queue.py`
- Modify: `sylanne_alpha/session_context.py`
- Modify: `sylanne_alpha/memory_system.py`
- Modify: `sylanne_alpha/memory_facade.py`
- Modify: `sylanne_alpha/memory_write_throat.py`
- Modify: `sylanne_alpha/diagnostics_surface.py`
- Modify: `sylanne_alpha/person_profile.py`
- Modify: `sylanne_alpha/person_shelf.py`
- Modify: `sylanne_alpha/relationship_layer.py`
- Modify: `sylanne_alpha/social_field.py`
- Modify: `sylanne_alpha/life_simulation.py`
- Modify: `sylanne_alpha/rhythm_learner.py`
- Modify: `sylanne_alpha/proactive_scheduler.py`
- Modify: `sylanne_alpha/public_api.py`
- Modify: `sylanne_alpha/v2core/integration.py`
- Modify: `sylanne_alpha/v3bridge/integration.py`
- Modify: `sylanne_alpha/host.py`
- Modify: `sylanne_alpha/_engine/sylanne_core/compute/host.py`
- Modify: `sylanne_alpha/_engine/sylanne_core/compute/runtime.py`
- Modify: `main.py`

- [ ] **Step 1: Write failing cross-scope persistence tests**

```python
import json

import pytest

from sylanne_alpha.scope_repository import ScopeRepository


def test_identical_transport_values_never_share_state(tmp_path, scopes) -> None:
    repo = ScopeRepository(tmp_path)
    left = scopes.bot_a_persona_a
    right = scopes.bot_b_persona_a

    repo.write_component(
        left,
        component="runtime",
        expected_generation=0,
        payload={"memory": ["left"], "life": {"phase": "awake"}},
    )
    repo.write_component(
        right,
        component="runtime",
        expected_generation=0,
        payload={"memory": ["right"], "life": {"phase": "sleep"}},
    )

    assert repo.read_component(left, "runtime").payload["memory"] == ["left"]
    assert repo.read_component(right, "runtime").payload["memory"] == ["right"]
    assert repo.component_path(left, "runtime") != repo.component_path(right, "runtime")


def test_reset_and_meltdown_touch_only_the_requested_scope(tmp_path, scopes) -> None:
    repo = ScopeRepository(tmp_path)
    left = scopes.bot_a_persona_a
    right = scopes.bot_b_persona_a
    repo.write_component(left, "runtime", expected_generation=0, payload={"v": "left"})
    repo.write_component(right, "runtime", expected_generation=0, payload={"v": "right"})

    repo.purge_session(left)

    assert repo.read_component(left, "runtime") is None
    assert repo.read_component(right, "runtime").payload == {"v": "right"}


def test_scoped_host_never_writes_legacy_files_or_kv(
    tmp_path,
    scopes,
    fake_kv,
) -> None:
    legacy_root = tmp_path / "legacy"
    host = build_scoped_host(
        scopes.bot_a_persona_a,
        repository=ScopeRepository(tmp_path / "scope-v1"),
        legacy_root=legacy_root,
        kv=fake_kv,
    )

    host.on_request({"text": "hello"})
    host.flush()

    assert list(legacy_root.rglob("*.alpha.json")) == []
    assert list(legacy_root.rglob("*.buffer.json")) == []
    assert fake_kv.put_calls == []


def test_scoped_host_restart_reads_only_scope_v1(tmp_path, scopes) -> None:
    repository = ScopeRepository(tmp_path / "scope-v1")
    first = build_scoped_host(scopes.bot_a_persona_a, repository=repository)
    first.on_request({"text": "hello"})
    first.flush()
    expected = first.kernel.snapshot()

    restored = build_scoped_host(scopes.bot_a_persona_a, repository=repository)

    assert restored.kernel.snapshot() == expected


def test_stale_session_writer_cannot_recreate_state_after_reset(tmp_path, scopes) -> None:
    repo = ScopeRepository(tmp_path)
    stale = repo.create_scope(scopes.bot_a_persona_a, expected_absent=True)
    repo.write_component(stale, "memory", expected_generation=0, payload={"v": 1})
    current = repo.invalidate_scope(
        stale,
        expected_scope_generation=stale.scope_generation,
        reason="reset",
    )
    path = repo.component_path(current, "memory")
    before = path.read_bytes() if path.exists() else None

    with pytest.raises(StaleScopeWrite) as exc:
        repo.write_component(stale, "memory", expected_generation=0, payload={"v": 2})

    assert exc.value.code == "scope_generation_stale"
    assert (path.read_bytes() if path.exists() else None) == before


def test_stale_relation_writer_is_fenced_by_relation_and_persona_generation(
    tmp_path,
    relation_scope,
) -> None:
    repo = ScopeRepository(tmp_path)
    active = repo.create_relation_scope(relation_scope)
    repo.write_relation_component(
        active,
        "relationship",
        expected_generation=0,
        payload={"trust": 0.5},
    )
    retired = repo.invalidate_relation(
        active,
        expected_relation_generation=active.relation_generation,
        reason="purge",
    )
    path = repo.relation_component_path(retired, "relationship")
    before = path.read_bytes() if path.exists() else None

    with pytest.raises(StaleScopeWrite) as relation_exc:
        repo.write_relation_component(
            active,
            "relationship",
            expected_generation=0,
            payload={"trust": 1.0},
        )
    assert relation_exc.value.code == "relation_generation_stale"
    assert (path.read_bytes() if path.exists() else None) == before

    repo.retire_persona_revision(
        active.persona_ref,
        expected_lifecycle_generation=active.persona_ref.lifecycle_generation,
        reason="retire",
    )
    with pytest.raises(StaleScopeWrite) as persona_exc:
        repo.read_relation_component(retired, "relationship")
    assert persona_exc.value.code == "persona_lifecycle_stale"


def test_runtime_activates_one_relation_across_sessions_and_restores_it(
    tmp_path,
    scopes,
    identity_key,
    authenticated_subject,
    runtime_registry_factory,
) -> None:
    repo = ScopeRepository(tmp_path / "scope-v1")
    registry = runtime_registry_factory(repo, identity_key)
    first = registry.relation_for(
        scopes.bot_a_persona_a,
        authenticated_subject,
    )
    second = registry.relation_for(
        scopes.bot_a_persona_a_session_2,
        authenticated_subject,
    )

    assert first is second
    assert first.scope.relation_ref == second.scope.relation_ref
    assert first.scope.relation_generation == second.scope.relation_generation
    first.persistence.save(
        "relationship",
        expected_generation=0,
        payload={"trust": 0.75},
    )

    restarted = runtime_registry_factory(repo, identity_key)
    restored = restarted.relation_for(
        scopes.bot_a_persona_a_session_2,
        authenticated_subject,
    )
    assert restored.scope == first.scope
    assert restored.persistence.load("relationship").payload == {"trust": 0.75}


def test_relation_activation_fails_closed_without_authenticated_subject(
    tmp_path,
    scopes,
    identity_key,
    runtime_registry_factory,
) -> None:
    repo = ScopeRepository(tmp_path / "scope-v1")
    registry = runtime_registry_factory(repo, identity_key)

    assert (
        registry.relation_for(
            scopes.bot_a_persona_a,
            None,
        )
        is None
    )
    assert list((tmp_path / "scope-v1").rglob("relation-meta.json")) == []


def test_reactivated_relation_fences_the_old_runtime(
    tmp_path,
    scopes,
    identity_key,
    authenticated_subject,
    runtime_registry_factory,
) -> None:
    repo = ScopeRepository(tmp_path / "scope-v1")
    registry = runtime_registry_factory(repo, identity_key)
    old = registry.relation_for(scopes.bot_a_persona_a, authenticated_subject)
    repo.invalidate_relation(
        old.scope,
        expected_relation_generation=old.scope.relation_generation,
        reason="purge",
    )
    fresh = registry.relation_for(
        scopes.bot_a_persona_a_session_2,
        authenticated_subject,
    )

    assert fresh.scope.relation_generation == old.scope.relation_generation + 1
    with pytest.raises(StaleScopeWrite, match="relation_generation_stale"):
        old.persistence.save(
            "relationship",
            expected_generation=0,
            payload={"trust": 1.0},
        )


@pytest.mark.asyncio
async def test_hooks_carry_one_opaque_turn_bound_subject_without_rereading_sender(
    hook_harness,
    fake_event,
    provider_request,
) -> None:
    fake_event.set_authenticated_sender("42")
    await hook_harness.on_message(fake_event)
    proof = fake_event.get_extra("_sylanne_turn_subject_v1")

    assert proof.transport_session_token.startswith("session_v1_")
    assert proof.subject.relation_ref.token.startswith("relation_v1_")
    assert "42" not in repr(proof)
    assert fake_event.get_sender_id_calls == 1

    fake_event.set_authenticated_sender("attacker-after-on-message")
    await hook_harness.on_llm_request(fake_event, provider_request)
    view = fake_event.get_extra("_sylanne_runtime_view_v1")

    assert fake_event.get_sender_id_calls == 1
    assert view.relation_runtime.scope.relation_ref == proof.subject.relation_ref
    assert fake_event.get_extra("_sylanne_turn_subject_v1") is None


@pytest.mark.asyncio
async def test_mismatched_turn_subject_proof_disables_private_runtime(
    hook_harness,
    fake_event,
    provider_request,
) -> None:
    await hook_harness.on_message(fake_event)
    proof = fake_event.get_extra("_sylanne_turn_subject_v1")
    fake_event.set_extra(
        "_sylanne_turn_subject_v1",
        replace(proof, turn_generation=proof.turn_generation + 1),
    )

    await hook_harness.on_llm_request(fake_event, provider_request)

    resolved = fake_event.get_extra("_sylanne_resolved_scope_v1")
    assert resolved.private_scope_enabled is False
    assert resolved.disabled_reason == "turn_subject_proof_mismatch"
    assert hook_harness.private_runtime_calls == 0
    assert hook_harness.relation_meta_writes == 0


@pytest.mark.asyncio
async def test_bound_missing_subject_skips_only_relation_runtime(
    hook_harness,
    fake_event,
    provider_request,
) -> None:
    fake_event.set_authenticated_sender(None)
    await hook_harness.on_message(fake_event)
    proof = fake_event.get_extra("_sylanne_turn_subject_v1")
    assert proof.subject is None

    await hook_harness.on_llm_request(fake_event, provider_request)
    view = fake_event.get_extra("_sylanne_runtime_view_v1")

    assert view.session_runtime is not None
    assert view.relation_runtime is None
    assert hook_harness.relation_meta_writes == 0


@pytest.mark.asyncio
async def test_background_queue_checkpoint_is_full_scope_and_restart_safe(
    tmp_path,
    scopes,
    fake_kv,
    scoped_background_queue_factory,
) -> None:
    repo = ScopeRepository(tmp_path / "scope-v1")
    left_scope = scopes.bot_a_persona_a
    right_scope = scopes.bot_b_persona_a
    left = scoped_background_queue_factory(repo, left_scope, fake_kv=fake_kv)
    right = scoped_background_queue_factory(repo, right_scope, fake_kv=fake_kv)
    left.enqueue_text("left")
    right.enqueue_text("right")

    await left.save_checkpoint()
    await right.save_checkpoint()

    restarted = scoped_background_queue_factory(repo, left_scope, fake_kv=fake_kv)
    assert await restarted.recover_queue() is True
    assert restarted.pending_texts() == ["left"]
    assert repo.component_path(left_scope, "background-queue") != repo.component_path(
        right_scope,
        "background-queue",
    )
    assert fake_kv.get_calls == []
    assert fake_kv.put_calls == []
    assert fake_kv.delete_calls == []


def test_relation_age_impression_and_ritual_are_relation_owned_and_restart_safe(
    tmp_path,
    relation_scopes,
    relation_runtime_factory,
    fake_kv,
) -> None:
    repo = ScopeRepository(tmp_path / "scope-v1")
    owner = relation_runtime_factory(repo, relation_scopes.bot_a_persona_a)
    other_bot = relation_runtime_factory(repo, relation_scopes.bot_b_persona_a)
    other_persona = relation_runtime_factory(repo, relation_scopes.bot_a_persona_b)
    owner.record_first_interaction(100.0)
    owner.record_first_impression(
        valence=0.8,
        topic_type="deep",
        user_style="brief",
        quality=0.9,
    )
    for _ in range(3):
        owner.observe_ritual(hour=22, pattern="goodnight")
    owner.flush()

    assert other_bot.first_interaction_time() is None
    assert other_persona.first_impression() is None
    assert other_bot.ritual("goodnight") is None

    restarted = relation_runtime_factory(repo, relation_scopes.bot_a_persona_a)
    assert restarted.first_interaction_time() == 100.0
    assert restarted.first_impression().topic_type == "deep"
    assert restarted.ritual("goodnight")["pattern"] == "goodnight"
    assert fake_kv.put_calls == []


def test_device_context_is_session_owned_and_never_persists_raw_user_agent(
    tmp_path,
    scopes,
    session_context_factory,
) -> None:
    repo = ScopeRepository(tmp_path / "scope-v1")
    left = session_context_factory(repo, scopes.bot_a_persona_a)
    right = session_context_factory(repo, scopes.bot_a_persona_a_session_2)
    raw_ua = "Browser/123 secret-device-string"

    assert left.detect_device_change(raw_ua) is None
    left.flush()

    assert right.last_device_category() is None
    payload = repo.read_component(
        scopes.bot_a_persona_a,
        "device-context",
    ).payload
    assert raw_ua not in json.dumps(payload, ensure_ascii=False)
```

The three hook-carrier tests live in `tests/integration/test_scope_astrbot_hook_order.py`; `hook_harness` invokes the actual decorated plugin methods in framework order and only instruments calls. The remaining test-local factories construct the production queue/context/runtime with frozen scope gateways and expose only harmless inspection helpers; do not add `enqueue_text`, `pending_texts`, or other test-only methods to production classes.

- [ ] **Step 2: Run the isolation tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_scope_persistence_isolation.py -q
```

Expected: FAIL because the component repository API is not implemented.

- [ ] **Step 3: Add one scoped persistence gateway**

In `scope_repository.py`, expose only complete-scope methods:

```python
_SESSION_COMPONENTS = frozenset(
    {
        "runtime",
        "host",
        "memory",
        "conversation",
        "life",
        "rhythm",
        "social",
        "scheduler",
        "background-queue",
        "device-context",
        "v2",
        "v3-shadow",
    }
)

_RELATION_COMPONENTS = frozenset(
    {
        "profile",
        "shelf",
        "relationship",
        "relationship-age",
        "first-impression",
        "ritual",
    }
)


def component_path(self, scope: SessionScope, component: str) -> Path:
    if component not in _SESSION_COMPONENTS:
        raise ValueError(f"unsupported scoped component: {component}")
    bot, persona, session = scope.storage_components()
    return (
        self.root
        / "bots"
        / bot
        / "personas"
        / persona
        / "sessions"
        / session
        / f"{component}.json"
    )


def relation_component_path(
    self,
    scope: RelationScope,
    component: str,
) -> Path:
    if component not in _RELATION_COMPONENTS:
        raise ValueError(f"unsupported relation component: {component}")
    return (
        self.root
        / "bots"
        / scope.bot_ref.token
        / "personas"
        / scope.persona_ref.token
        / "relations"
        / scope.relation_ref.token
        / f"{component}.json"
    )
```

`ScopeRepository.activate_relation_scope()` is the only production creator/reattacher of a RelationScope. It accepts the already-active `PersonaRevisionRef` and an opaque HMAC-derived `RelationRef`; callers cannot supply a relation generation:

```python
def activate_relation_scope(
    self,
    persona_ref: PersonaRevisionRef,
    relation_ref: RelationRef,
) -> RelationScope:
    if relation_ref.bot_ref != persona_ref.bot_ref:
        raise ScopeParentMismatch("relation does not belong to persona Bot")
    with self._lock:
        self._validate_bot_ref_locked(persona_ref.bot_ref)
        self._validate_persona_ref_locked(persona_ref)
        meta = self._read_relation_meta_locked(persona_ref, relation_ref)
        if meta is None:
            generation = 0
        elif meta.parent_tuple != (
            persona_ref.bot_ref.token,
            persona_ref.token,
            persona_ref.lifecycle_generation,
            relation_ref.token,
        ):
            raise ScopeParentMismatch("relation metadata parent mismatch")
        elif meta.state == "active":
            generation = meta.relation_generation
        elif meta.state == "retired":
            generation = meta.relation_generation + 1
        else:
            raise ScopeCorrupt("relation metadata state is invalid")
        self._atomic_write_relation_meta_locked(
            persona_ref,
            relation_ref,
            state="active",
            relation_generation=generation,
        )
        return RelationScope(
            bot_ref=persona_ref.bot_ref,
            persona_ref=persona_ref,
            relation_ref=relation_ref,
            relation_generation=generation,
        )
```

The `relation-meta.json` parent tuple and generation are authoritative across restart. It stores only opaque refs and generations—never the raw authenticated subject. Retired metadata is advanced exactly once under the repository lock when the subject next reappears; concurrent activation returns that same new active generation.

Every scoped gateway operation acquires the repository lock and performs its parent fence before reading component generation or bytes:

```python
def _validate_session_scope_locked(self, scope: SessionScope) -> None:
    persona = self._read_persona_manifest_locked(scope.persona_ref.token)
    if (
        persona is None
        or persona.state != "active"
        or persona.lifecycle_generation
        != scope.persona_ref.lifecycle_generation
    ):
        raise StaleScopeWrite(code="persona_lifecycle_stale")
    meta = self._read_scope_meta_locked(scope.storage_token)
    if (
        meta is None
        or meta.state != "active"
        or meta.scope_generation != scope.scope_generation
    ):
        raise StaleScopeWrite(code="scope_generation_stale")
    if (
        meta.bot_ref != scope.bot_ref.token
        or meta.persona_ref != scope.persona_ref.token
        or meta.session_ref != scope.session_ref.token
    ):
        raise StaleScopeWrite(code="scope_parent_stale")
```

`_validate_relation_scope_locked()` applies the same active Bot + Persona lifecycle checks and compares `RelationScope.relation_generation` with `relation-meta.json`. `read_component`, `write_component`, `append_component`, `purge_session`, scoped history append/read, scoped host commits, `read_relation_component`, `write_relation_component`, and relation purge all call the matching validator under the same lock. Only after that fence passes may they inspect or CAS a component generation. Component files may be absent or generation zero after cleanup; that never weakens the parent fence.

These methods accept a full `SessionScope` or `RelationScope`, never a raw string. `purge_session` and relation purge resolve and verify the exact opaque directory before using native `Path` operations; they cannot delete a bot, persona, repository root, or sibling state.

- [ ] **Step 4: Make `StatePersistence` legacy-read-only**

Rename its active write entry points to explicit legacy readers and reject new writes:

```python
class LegacyWriteForbidden(RuntimeError):
    pass


class StatePersistence:
    def save_session_state(self, *args, **kwargs) -> None:
        raise LegacyWriteForbidden("legacy-unscoped state is read-only")

    def load_legacy_session_state(self, legacy_session_key: str) -> dict[str, object] | None:
        return self._load_existing_legacy_payload(legacy_session_key)
```

Remove the new-runtime call sites for raw KV names such as `sylanne_kernel_{safe}`, `personality_drift:{safe}`, global life keys, relation keys, and raw filenames. Do not delete the legacy readers; Task 12 consumes them.

- [ ] **Step 5: Change stateful modules to require a scope gateway**

Construct memory, person profile/shelf, relationship, social field, life, rhythm, scheduler, V2, and V3 shadow objects with:

```python
@dataclass(frozen=True, slots=True)
class ScopedPersistence:
    repository: ScopeRepository
    scope: SessionScope

    def load(self, component: str):
        return self.repository.read_component(self.scope, component)

    def save(
        self,
        component: str,
        *,
        expected_generation: int,
        payload: dict[str, object],
    ) -> int:
        return self.repository.write_component(
            self.scope,
            component,
            expected_generation=expected_generation,
            payload=payload,
        )


@dataclass(frozen=True, slots=True)
class RelationScopedPersistence:
    repository: ScopeRepository
    scope: RelationScope

    def load(self, component: str):
        return self.repository.read_relation_component(self.scope, component)

    def save(
        self,
        component: str,
        *,
        expected_generation: int,
        payload: dict[str, object],
    ) -> int:
        return self.repository.write_relation_component(
            self.scope,
            component,
            expected_generation=expected_generation,
            payload=payload,
        )
```

At the event boundary, `SessionContext.resolve_authenticated_identity(event)` returns verified raw fields only to the immediate caller. `ScopeIdentityKey.authenticated_subject()` HMAC-derives the RelationRef immediately and returns this opaque process-memory proof:

```python
@dataclass(frozen=True, slots=True)
class VerifiedSubjectInput:
    platform_realm: str
    subject_kind: Literal["user"]
    subject_id: str = field(repr=False)
    identity_quality: Literal["event_get_sender_id"] = "event_get_sender_id"


@dataclass(frozen=True, slots=True)
class AuthenticatedSubject:
    relation_ref: RelationRef
    identity_quality: Literal["event_get_sender_id"]


@dataclass(frozen=True, slots=True)
class TurnSubjectProof:
    transport_session_token: str
    turn_generation: int
    subject: AuthenticatedSubject | None

    def __post_init__(self) -> None:
        _require_token(self.transport_session_token, "session_v1_")
        if type(self.turn_generation) is not int or self.turn_generation < 0:
            raise ValueError("invalid turn generation")


def authenticated_subject(
    self,
    bot_ref: BotRef,
    *,
    platform_realm: str,
    subject_kind: str,
    authenticated_subject_id: str,
    identity_quality: str,
) -> AuthenticatedSubject:
    if identity_quality != "event_get_sender_id":
        raise UnauthenticatedSubject("subject identity is not authenticated")
    return AuthenticatedSubject(
        relation_ref=self.relation_ref(
            bot_ref,
            platform_realm=platform_realm,
            subject_kind=subject_kind,
            authenticated_subject_id=authenticated_subject_id,
        ),
        identity_quality="event_get_sender_id",
    )
```

The raw authenticated subject is used only as HMAC input in the `on_message` stack frame and is then discarded; neither event extras nor logs contain it. `ScopeRuntimeRegistry` owns the activation path:

```python
def relation_for(
    self,
    session_scope: SessionScope,
    subject: AuthenticatedSubject | None,
) -> RelationRuntime | None:
    self._repository.validate_session_scope(session_scope)
    if subject is None:
        return None
    relation_ref = subject.relation_ref
    if relation_ref.bot_ref != session_scope.bot_ref:
        raise ScopeParentMismatch("subject proof belongs to another Bot")
    relation_scope = self._repository.activate_relation_scope(
        session_scope.persona_ref,
        relation_ref,
    )
    key = (
        relation_scope.bot_ref.token,
        relation_scope.persona_ref.token,
        relation_scope.persona_ref.lifecycle_generation,
        relation_scope.relation_ref.token,
        relation_scope.relation_generation,
    )
    runtime = self._relations.get(key)
    if runtime is None:
        runtime = self._relation_runtime_factory(
            relation_scope,
            RelationScopedPersistence(self._repository, relation_scope),
        )
        self._relations[key] = runtime
    return runtime
```

`on_message` resolves the authenticated subject exactly once, immediately converts it to the opaque `AuthenticatedSubject`, discards the raw fields, and attaches one `TurnSubjectProof` under `_sylanne_turn_subject_v1`. The carrier binds that proof to the `transport_scope.session_ref.token` and the exact `transport_turn.turn_generation` already returned by `SessionCatalog.begin_turn()`.

At `on_llm_request`, before Persona resolution or any private-state access, require the attached transport scope, transport turn, and subject carrier to agree on SessionRef and turn generation. Missing/mismatched carriers disable the whole turn with `turn_subject_proof_mismatch`; they do not silently rebuild a subject from the event. After AstrBot Persona resolution, freeze the `SessionScope`, call `relation_for()` once with `turn_subject_proof.subject`, carry the returned runtime in the request-bound runtime view, and overwrite `_sylanne_turn_subject_v1` with `None`. A legitimately missing/untrusted subject is represented by a correctly bound carrier whose `subject is None`; Session-owned work may continue, but all relation reads and writes are skipped. No downstream module re-reads sender fields, derives a RelationRef, or activates relation metadata independently.

The production hook wiring is explicit:

```python
# on_message, immediately after SessionCatalog.begin_turn()
raw_subject = self._session_context.resolve_authenticated_identity(event)
subject = (
    None
    if raw_subject is None
    else self._identity_key.authenticated_subject(
        transport_scope.bot_ref,
        platform_realm=raw_subject.platform_realm,
        subject_kind=raw_subject.subject_kind,
        authenticated_subject_id=raw_subject.subject_id,
        identity_quality=raw_subject.identity_quality,
    )
)
del raw_subject
event.set_extra(
    "_sylanne_turn_subject_v1",
    TurnSubjectProof(
        transport_session_token=transport_scope.session_ref.token,
        turn_generation=transport_turn.turn_generation,
        subject=subject,
    ),
)

# on_llm_request, before resolving Persona
now_ms = int(self._observed_now() * 1000)
subject_proof = event.get_extra("_sylanne_turn_subject_v1")
if (
    not isinstance(subject_proof, TurnSubjectProof)
    or subject_proof.transport_session_token
    != transport_scope.session_ref.token
    or subject_proof.turn_generation != transport_turn.turn_generation
):
    event.set_extra(
        "_sylanne_resolved_scope_v1",
        ResolvedScope.disabled(
            "turn_subject_proof_mismatch",
            resolved_at_ms=now_ms,
        ),
    )
    return

# after freeze_persona() succeeds
relation_runtime = self._scope_runtime_registry.relation_for(
    resolved.scope,
    subject_proof.subject,
)
runtime_view = RequestRuntimeView(
    resolved=resolved,
    persona_runtime=self._scope_runtime_registry.for_scope(resolved.scope),
    session_runtime=self._scope_runtime_registry.exact_session(resolved.scope),
    relation_runtime=relation_runtime,
)
event.set_extra("_sylanne_runtime_view_v1", runtime_view)
event.set_extra("_sylanne_turn_subject_v1", None)
```

`RequestRuntimeView` is an immutable `scope_runtime.py` dataclass. Every later hook requires `_sylanne_runtime_view_v1`; it never reconstructs a runtime view from current registry selection or event sender fields.

Every async save captures the frozen `ScopedPersistence` object when it is scheduled. On commit it uses the captured generation; `StaleScopeWrite` is recorded and discarded, never redirected to the currently selected Persona.

Person profile, shelf, relationship layer, and V2 relationship registers receive `RelationScope` plus `RelationScopedPersistence`; they never index by `(platform_id, sender_id)` or Session alone. `PersonaRuntime` owns `RelationRuntime` objects and locks by `RelationRef.token`. The same authenticated user across two Sessions of one Bot + Persona reaches the same RelationRuntime; another Bot or Persona reaches a different parent path and object. Releasing/purging a Session never deletes a RelationRuntime—only an explicit full-parent relation purge can do so. Social-field group state remains Session-scoped; identical group and sender IDs under another Bot or Persona produce different objects and paths.

Refactor `BackgroundPostQueue` so every public queue, worker, lease, checkpoint, recovery, and drain method is bound to one frozen `SessionScope` at construction and therefore accepts no raw `session_key`. Its in-memory maps are keyed by `(scope.storage_token, scope.scope_generation)` and its checkpoint is CAS-written only through `ScopedPersistence` component `background-queue`. A delayed task captures that persistence object; a stale generation raises `StaleScopeWrite` and the job is discarded rather than redirected. A recovered job has `event=None` and may resume private assessment/state work for the same scope, but it cannot perform reactive delivery or infer a current Session. Scoped mode contains no `checkpoint_kv_key()`, `get_kv_data()`, `put_kv_data()`, or `delete_kv_data()` branch.

Move relationship age, first interaction, first impression, and ritual state out of `SessionContext` into `RelationRuntime`. The runtime restores and CAS-writes `relationship-age`, `first-impression`, and `ritual` through `RelationScopedPersistence`. Each `RelationRuntime` owns one `RitualRegistry`; registry keys are pattern names only because the enclosing RelationScope is already the namespace. It registers timing hints only with the owning PersonaRuntime scheduler. There is no plugin-global ritual registry, global ritual scheduler, concatenated `session_key:pattern` key, or `_RITUAL_REGISTRY_KV_KEY` persistence.

Keep device-change context Session-owned. Persist only a keyed digest and coarse device category through `ScopedPersistence` component `device-context`; never persist the raw User-Agent. If an authenticated RelationScope cannot be resolved, skip relation age/impression/ritual reads and writes rather than creating an anonymous or Session-keyed relation.

Add:

```python
def test_relation_shared_across_sessions_but_not_across_bot_or_persona(
    registry,
    relation_scopes,
    authenticated_subject,
) -> None:
    same_person_first = registry.relation_for(
        relation_scopes.a_session_1,
        authenticated_subject,
    )
    same_person_second = registry.relation_for(
        relation_scopes.a_session_2,
        authenticated_subject,
    )
    other_persona = registry.relation_for(
        relation_scopes.persona_b,
        authenticated_subject,
    )
    other_bot = registry.relation_for(
        relation_scopes.bot_b,
        authenticated_subject,
    )

    assert same_person_first is same_person_second
    assert same_person_first is not other_persona
    assert same_person_first is not other_bot
    assert registry.relation_for(relation_scopes.a_session_1, None) is None
```

- [ ] **Step 6: Replace AlphaRuntime file/KV persistence in scoped mode**

Implement `ScopedAlphaRuntime`:

```python
class ScopedAlphaRuntime:
    def __init__(self, persistence: ScopedPersistence, profile, pel_enabled: bool) -> None:
        self._persistence = persistence
        self._profile = profile
        self._pel_enabled = pel_enabled
        self._generation = 0
        self._buffer_generation = 0
        self._observation_sink = None

    def load(self, session_key: str) -> AlphaKernel:
        if session_key != self._persistence.scope.storage_token:
            raise ValueError("host session token does not match frozen scope")
        snapshot = self._persistence.load("host")
        if snapshot is None:
            return AlphaKernel.boot(
                session_key=session_key,
                profile=self._profile,
                pel_enabled=self._pel_enabled,
            )
        self._generation = snapshot.generation
        return AlphaKernel.restore(
            snapshot.payload,
            profile=self._profile,
            pel_enabled=self._pel_enabled,
        )

    def save(self, kernel: AlphaKernel) -> None:
        self.save_snapshot(kernel.session_key, kernel.snapshot())

    def save_snapshot(self, session_key: str, snapshot: dict[str, object]) -> None:
        if session_key != self._persistence.scope.storage_token:
            raise ValueError("host session token does not match frozen scope")
        self._generation = self._persistence.save(
            "host",
            expected_generation=self._generation,
            payload=snapshot,
        )
        if self._observation_sink is not None:
            self._observation_sink(session_key, snapshot)

    def load_buffer(self, session_key: str) -> dict[str, object] | None:
        if session_key != self._persistence.scope.storage_token:
            raise ValueError("buffer session token does not match frozen scope")
        snapshot = self._persistence.load("conversation")
        if snapshot is None:
            return None
        self._buffer_generation = snapshot.generation
        return snapshot.payload

    def save_buffer(
        self,
        session_key: str,
        buffer_data: dict[str, object],
    ) -> None:
        if session_key != self._persistence.scope.storage_token:
            raise ValueError("buffer session token does not match frozen scope")
        self._buffer_generation = self._persistence.save(
            "conversation",
            expected_generation=self._buffer_generation,
            payload=buffer_data,
        )

    def set_observation_sink(self, sink) -> None:
        self._observation_sink = sink
```

Add an optional runtime factory to the vendored `compute.host.SylanneAlphaHost`; scoped construction always injects `ScopedAlphaRuntime`, while legacy readers retain `AlphaRuntime`. `state_persistence.persist_kernel()` detects scoped runtime, skips every raw KV/backup/file branch, and flushes only through the scoped adapter. `AlphaRuntime` remains available only for read-only legacy inventory/export and tests. No scoped turn calls its `.save()`, `.save_snapshot()`, `.save_buffer()`, or legacy KV key functions.

- [ ] **Step 7: Add an enforcement test for raw-key and global fallback regressions**

Add to `tests/test_scope_persistence_isolation.py`:

```python
import ast
from pathlib import Path


def test_active_entrypoints_have_no_default_or_raw_session_persistence() -> None:
    root = Path(__file__).parents[1]
    checked = [
        root / "main.py",
        root / "sylanne_alpha" / "background_queue.py",
        root / "sylanne_alpha" / "session_context.py",
        root / "sylanne_alpha" / "memory_system.py",
        root / "sylanne_alpha" / "person_profile.py",
        root / "sylanne_alpha" / "person_shelf.py",
        root / "sylanne_alpha" / "life_simulation.py",
        root / "sylanne_alpha" / "social_field.py",
        root / "sylanne_alpha" / "proactive_scheduler.py",
        root / "sylanne_alpha" / "v2core" / "integration.py",
    ]
    forbidden_calls: list[tuple[str, int, str]] = []
    for path in checked:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            rendered = ast.unparse(node)
            if '"default"' in rendered and (
                "memory_system_for_session" in rendered
                or "session_key" in rendered
                or "most_recent_host_key" in rendered
            ):
                forbidden_calls.append((path.name, node.lineno, rendered))
    assert forbidden_calls == []

    background_source = (root / "sylanne_alpha" / "background_queue.py").read_text(
        encoding="utf-8",
    )
    for forbidden in (
        "checkpoint_kv_key",
        "get_kv_data",
        "put_kv_data",
        "delete_kv_data",
    ):
        assert forbidden not in background_source

    session_context_source = (
        root / "sylanne_alpha" / "session_context.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "_first_interaction_times",
        "_device_fingerprints",
        "_first_impressions",
        "_ritual_registry",
        "_RITUAL_REGISTRY_KV_KEY",
    ):
        assert forbidden not in session_context_source

    main_tree = ast.parse((root / "main.py").read_text(encoding="utf-8"))
    hook_functions = {
        node.name: node
        for node in ast.walk(main_tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name
        in {
            "on_message",
            "on_llm_request",
            "_on_llm_request_inner",
            "_process_llm_request_final",
        }
    }
    on_message_calls = [
        ast.unparse(node)
        for node in ast.walk(hook_functions["on_message"])
        if isinstance(node, ast.Call)
        and "resolve_authenticated_identity" in ast.unparse(node.func)
    ]
    assert len(on_message_calls) == 1
    for name in (
        "on_llm_request",
        "_on_llm_request_inner",
        "_process_llm_request_final",
    ):
        forbidden_sender_reads = [
            ast.unparse(node)
            for node in ast.walk(hook_functions[name])
            if isinstance(node, ast.Call)
            and (
                "get_sender_id" in ast.unparse(node.func)
                or "resolve_authenticated_identity" in ast.unparse(node.func)
            )
        ]
        assert forbidden_sender_reads == []
```

- [ ] **Step 8: Run state, memory, relation, life, and shadow regressions**

Run:

```powershell
$v3Tests = @(
    Get-ChildItem -LiteralPath 'tests' -Filter 'test_v3_*.py' -File |
        Select-Object -ExpandProperty FullName
)
if ($v3Tests.Count -eq 0) {
    throw 'No test_v3_*.py regression files found'
}
python -m pytest tests/test_scope_persistence_isolation.py tests/test_scope_background_queue.py tests/test_scope_runtime.py tests/integration/test_scope_astrbot_hook_order.py tests/test_wave_l2_t2_05_t2_06_followup_ritual.py tests/test_memory_contract_prd.py tests/test_v250_profile_crossgroup.py tests/test_v250_shelf_recall.py tests/test_v250_shelf_write.py tests/test_fixlist_p0_5_outreach.py @v3Tests -q
```

Expected: all selected tests pass.

- [ ] **Step 9: Commit the state cutover**

```powershell
git add main.py sylanne_alpha/scoped_host_runtime.py sylanne_alpha/scope_contracts.py sylanne_alpha/scope_identity.py sylanne_alpha/scope_repository.py sylanne_alpha/scope_runtime.py sylanne_alpha/state_persistence.py sylanne_alpha/background_queue.py sylanne_alpha/session_context.py sylanne_alpha/memory_system.py sylanne_alpha/memory_facade.py sylanne_alpha/memory_write_throat.py sylanne_alpha/diagnostics_surface.py sylanne_alpha/person_profile.py sylanne_alpha/person_shelf.py sylanne_alpha/relationship_layer.py sylanne_alpha/social_field.py sylanne_alpha/life_simulation.py sylanne_alpha/rhythm_learner.py sylanne_alpha/proactive_scheduler.py sylanne_alpha/public_api.py sylanne_alpha/v2core/integration.py sylanne_alpha/v3bridge/integration.py sylanne_alpha/host.py sylanne_alpha/_engine/sylanne_core/compute/host.py sylanne_alpha/_engine/sylanne_core/compute/runtime.py tests/integration/test_scope_astrbot_hook_order.py tests/test_scope_persistence_isolation.py tests/test_scope_background_queue.py tests/test_scope_runtime.py tests/test_wave_l2_t2_05_t2_06_followup_ritual.py
git commit -m "refactor: cut mutable state over to full scope"
```

### Task 7: Replace all dynamic prompt mutation with one temporary context sink

**Files:**
- Create: `sylanne_alpha/transient_context.py`
- Create: `tests/test_transient_context.py`
- Modify: `sylanne_alpha/llm_request_pipeline.py`
- Modify: `sylanne_alpha/llm_response_pipeline.py`
- Modify: `sylanne_alpha/deliverable_mode.py`
- Modify: `sylanne_alpha/realtime_dispatch.py`
- Modify: `sylanne_alpha/v2core/integration.py`
- Modify: `sylanne_alpha/state_persistence.py`
- Modify: `sylanne_alpha/public_api.py`
- Modify: `main.py`
- Modify: `tests/test_context_history_isolation.py`
- Modify: `tests/test_astrbot_manager_integration.py`

- [ ] **Step 1: Write failing sink and history-isolation tests**

```python
from types import SimpleNamespace

import pytest

from sylanne_alpha.transient_context import ScopeMismatch, TransientContextSink


def test_sink_commits_exactly_one_sylanne_temporary_text_part(scope) -> None:
    existing = SimpleNamespace(text="framework part", _no_save=True)
    request = SimpleNamespace(
        extra_user_content_parts=[existing],
        system_prompt="astrbot persona",
        contexts=[{"role": "user", "content": "history"}],
    )
    sink = TransientContextSink(
        scope,
        max_chars=512,
        scope_generation_reader=lambda token: (
            scope.scope_generation if token == scope.storage_token else None
        ),
    )
    sink.add(scope, "state", "quietly attentive", source="runtime")
    sink.add(scope, "state", "quietly attentive", source="runtime")
    sink.add(scope, "memory", "keep a measured distance", source="memory")

    sink.commit(request)

    assert request.system_prompt == "astrbot persona"
    assert request.contexts == [{"role": "user", "content": "history"}]
    sylanne_parts = [
        part
        for part in request.extra_user_content_parts
        if getattr(part, "text", "").startswith("[sylanne_runtime_overlay]")
    ]
    assert request.extra_user_content_parts[0] is existing
    assert len(sylanne_parts) == 1
    part = sylanne_parts[0]
    assert part._no_save is True
    assert part.text == (
        "[sylanne_runtime_overlay]\n"
        "[state source=runtime lifecycle=turn]\nquietly attentive\n"
        "[memory source=memory lifecycle=turn]\nkeep a measured distance"
    )
    with pytest.raises(RuntimeError, match="already committed"):
        sink.commit(request)


def test_sink_rejects_wrong_or_stale_scope_without_mutating_request(
    scope,
    other_scope,
) -> None:
    request = SimpleNamespace(
        extra_user_content_parts=[],
        system_prompt="base",
        contexts=[],
    )
    current_generation = {scope.storage_token: scope.scope_generation}
    sink = TransientContextSink(
        scope,
        max_chars=512,
        scope_generation_reader=current_generation.get,
    )

    with pytest.raises(ScopeMismatch):
        sink.add(other_scope, "state", "wrong", source="runtime")
    current_generation[scope.storage_token] += 1

    assert sink.commit(request) is False
    assert request.extra_user_content_parts == []
    assert request.system_prompt == "base"


def test_text_part_failure_safely_omits_overlay(scope) -> None:
    request = SimpleNamespace(
        extra_user_content_parts=[],
        system_prompt="base",
        contexts=[],
    )
    sink = TransientContextSink(
        scope,
        max_chars=512,
        scope_generation_reader=lambda _token: scope.scope_generation,
        part_factory=lambda _text: (_ for _ in ()).throw(RuntimeError("no API")),
    )
    sink.add(scope, "state", "quiet", source="runtime")

    assert sink.commit(request) is False
    assert request.extra_user_content_parts == []
    assert request.system_prompt == "base"
```

- [ ] **Step 2: Run the sink tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_transient_context.py -q
```

Expected: FAIL because `TransientContextSink` does not exist.

- [ ] **Step 3: Implement the single sink**

```python
from __future__ import annotations

from astrbot.core.agent.message import TextPart


class TransientContextSink:
    _CHANNEL_ORDER = {
        "time": 10,
        "state": 20,
        "semantic": 30,
        "amnesia": 40,
        "outreach": 50,
        "unfinished": 60,
        "memory": 70,
        "deliverable": 80,
        "realtime": 90,
        "v2": 100,
        "genesis": 110,
    }

    def __init__(
        self,
        scope: SessionScope,
        *,
        max_chars: int,
        scope_generation_reader,
        part_factory=None,
    ) -> None:
        if max_chars < 128:
            raise ValueError("transient context budget is too small")
        self._scope = scope
        self._max_chars = max_chars
        self._scope_generation_reader = scope_generation_reader
        self._part_factory = part_factory or (
            lambda text: TextPart(text=text).mark_as_temp()
        )
        self._fragments: dict[tuple[str, str, str], tuple[int, str]] = {}
        self._committed = False

    def add(
        self,
        scope: SessionScope,
        channel: str,
        text: str,
        *,
        source: str,
        priority: int = 0,
        lifecycle: str = "turn",
    ) -> None:
        if self._committed:
            raise RuntimeError("transient context already committed")
        if scope != self._scope:
            raise ScopeMismatch("transient fragment scope mismatch")
        clean_channel = channel.strip().lower()
        clean_text = text.strip()
        clean_source = source.strip().lower()
        if clean_channel not in self._CHANNEL_ORDER:
            raise ValueError("unknown transient context channel")
        if lifecycle != "turn":
            raise ValueError("transient context lifecycle must be turn")
        if clean_text:
            key = (clean_channel, clean_source, clean_text)
            current = self._fragments.get(key)
            if current is None or priority > current[0]:
                self._fragments[key] = (priority, lifecycle)

    def commit(self, request) -> bool:
        if self._committed:
            raise RuntimeError("transient context already committed")
        self._committed = True
        if (
            self._scope_generation_reader(self._scope.storage_token)
            != self._scope.scope_generation
        ):
            return False
        if not self._fragments:
            return False
        header = "[sylanne_runtime_overlay]\n"
        remaining = self._max_chars - len(header)
        blocks: list[str] = []
        ordered = sorted(
            self._fragments.items(),
            key=lambda item: (
                self._CHANNEL_ORDER[item[0][0]],
                -item[1][0],
                item[0][1],
                item[0][2],
            ),
        )
        for (channel, source, text), (_priority, lifecycle) in ordered:
            block = f"[{channel} source={source} lifecycle={lifecycle}]\n{text}"
            separator = 1 if blocks else 0
            if len(block) + separator > remaining:
                continue
            blocks.append(block)
            remaining -= len(block) + separator
        if not blocks:
            return False
        try:
            part = self._part_factory(header + "\n".join(blocks))
            request.extra_user_content_parts.append(part)
        except Exception:
            return False
        return True
```

- [ ] **Step 4: Route every dynamic producer into the sink**

`LLMRequestPipeline._process_llm_request_final()` creates one sink bound to the frozen `resolved.scope`, the repository scope-generation reader, and the existing request injection budget. It passes the same sink to all producers and calls `sink.commit(request)` once after state, time, semantic beat, amnesia, outreach, unfinished reply, memory, deliverable-mode, realtime, and V2 fragments have been added.

Replace direct mutation:

```python
request.system_prompt = f"{request.system_prompt}\n{fragment}"
```

with:

```python
sink.add(
    resolved.scope,
    "state",
    fragment,
    source="llm_request_pipeline",
)
```

Use stable channels: `time`, `state`, `semantic`, `amnesia`, `outreach`, `unfinished`, `memory`, `deliverable`, `realtime`, and `v2`. Producers return text or call `sink.add`; they never write `request.prompt`, `request.contexts`, `request.system_prompt`, or `extra_user_content_parts` directly.

- [ ] **Step 5: Remove PersonaManager reverse synchronization**

Delete the `sync_personality_to_persona_mgr` implementation and its call sites in `state_persistence.py`, `llm_request_pipeline.py`, `public_api.py`, and `main.py`. Replace the old positive assertions in `tests/test_astrbot_manager_integration.py` with:

```python
@pytest.mark.asyncio
async def test_runtime_never_creates_or_updates_astrbot_persona(plugin) -> None:
    await plugin.initialize()
    await plugin.on_llm_request(plugin.test_event, plugin.test_request)

    plugin.context.persona_manager.create_persona.assert_not_awaited()
    plugin.context.persona_manager.update_persona.assert_not_awaited()
```

- [ ] **Step 6: Add an AST enforcement test**

In `tests/test_context_history_isolation.py`, scan these active files:

```python
ACTIVE_CONTEXT_FILES = (
    "sylanne_alpha/llm_request_pipeline.py",
    "sylanne_alpha/llm_response_pipeline.py",
    "sylanne_alpha/deliverable_mode.py",
    "sylanne_alpha/realtime_dispatch.py",
    "sylanne_alpha/v2core/integration.py",
)
```

Assert there are zero assignments to `request.system_prompt`, `request.contexts`, and `request.prompt`, and that `extra_user_content_parts.append` occurs only in `transient_context.py`.

- [ ] **Step 7: Run context, semantic, and manager regressions**

Run:

```powershell
python -m pytest tests/test_transient_context.py tests/test_context_history_isolation.py tests/test_context_integrity_silent_history.py tests/test_semantic_segmentation_pipeline.py tests/test_grey4_third_party_history_fallback.py tests/test_astrbot_manager_integration.py -q
```

Expected: all selected tests pass; there is exactly one Sylanne-tagged temporary `TextPart` in the positive request path, unrelated framework parts remain untouched, and there are zero Sylanne PersonaManager writes.

- [ ] **Step 8: Commit the transient overlay boundary**

```powershell
git add main.py sylanne_alpha/transient_context.py sylanne_alpha/llm_request_pipeline.py sylanne_alpha/llm_response_pipeline.py sylanne_alpha/deliverable_mode.py sylanne_alpha/realtime_dispatch.py sylanne_alpha/v2core/integration.py sylanne_alpha/state_persistence.py sylanne_alpha/public_api.py tests/test_transient_context.py tests/test_context_history_isolation.py tests/test_astrbot_manager_integration.py
git commit -m "refactor: inject runtime context as one temporary part"
```

### Task 8: Infer Persona Genesis safely in the background

**Files:**
- Create: `sylanne_alpha/persona_genesis.py`
- Create: `tests/test_persona_genesis.py`
- Modify: `sylanne_alpha/scope_runtime.py`
- Modify: `sylanne_alpha/scope_repository.py`
- Modify: `sylanne_alpha/llm_request_pipeline.py`
- Modify: `main.py`

- [ ] **Step 1: Write failing non-blocking, schema, and single-flight tests**

```python
import asyncio
import json

import pytest

from sylanne_alpha.persona_genesis import (
    GenesisProviderBudget,
    GenesisProviderRetryable,
    GenesisService,
)


@pytest.mark.asyncio
async def test_genesis_is_single_flight_and_does_not_block_first_reply(
    repo,
    scope,
    source,
) -> None:
    gate = asyncio.Event()
    calls = 0

    async def model_call(prompt: str) -> str:
        nonlocal calls
        calls += 1
        await gate.wait()
        return json.dumps(
            {
                "traits_prior": {"curiosity": 0.7},
                "voice_prior": {"pace": "measured"},
                "boundary_prior": {"firmness": 0.6},
                "proactivity_prior": {"initiative": 0.4},
                "circadian_prior": {"phase": "diurnal"},
            }
        )

    service = GenesisService.for_test(repository=repo, model_call=model_call)
    first = service.schedule(scope.persona_ref, source)
    second = service.schedule(scope.persona_ref, source)

    assert first is second
    assert service.snapshot(scope.persona_ref) is None
    gate.set()
    await first
    assert calls == 1


@pytest.mark.asyncio
async def test_genesis_rejects_memory_or_relationship_fields(
    repo,
    scope,
    source,
) -> None:
    async def model_call(prompt: str) -> str:
        return '{"traits_prior":{},"memory":["met user"],"relationship":"friend"}'

    service = GenesisService.for_test(repository=repo, model_call=model_call)
    await service.schedule(scope.persona_ref, source)

    assert service.snapshot(scope.persona_ref) is None
    assert service.diagnostic(scope.persona_ref).code == "genesis_schema_rejected"


@pytest.mark.asyncio
async def test_growth_and_dynamic_overlay_stay_disabled_until_genesis_is_ready(
    plugin,
    scope,
) -> None:
    plugin.genesis_model.block()

    await plugin.handle_first_turn(scope, text="hello")

    assert plugin.sent_base_reply is True
    assert plugin.runtime(scope).growth_write_count == 0
    assert plugin.runtime(scope).memory_write_count == 0
    assert plugin.runtime(scope).relation_write_count == 0
    assert plugin.runtime(scope).outbox_write_count == 0
    assert plugin.last_request.extra_user_content_parts == []


@pytest.mark.asyncio
async def test_stale_genesis_completion_cannot_resurrect_a_retired_persona(
    repo,
    scope,
    source,
) -> None:
    gate = asyncio.Event()

    async def model_call(prompt: str) -> str:
        await gate.wait()
        return json.dumps(
            {
                "traits_prior": {},
                "voice_prior": {},
                "boundary_prior": {},
                "proactivity_prior": {},
                "circadian_prior": {},
            }
        )

    active = repo.activate_persona_revision(scope.persona_ref)
    service = GenesisService.for_test(repository=repo, model_call=model_call)
    stale_task = service.schedule(active, source)
    repo.retire_persona_revision(
        active,
        expected_lifecycle_generation=active.lifecycle_generation,
        reason="purge",
    )
    recreated = repo.activate_persona_revision(scope.persona_ref)

    gate.set()
    await stale_task

    assert recreated.lifecycle_generation == active.lifecycle_generation + 1
    assert service.snapshot(active) is None
    assert service.snapshot(recreated) is None
    assert repo.read_genesis(recreated) is None


@pytest.mark.asyncio
async def test_genesis_provider_budget_caps_concurrency_across_personas(
    repo,
    persona_cases,
    valid_genesis_json,
) -> None:
    release = asyncio.Event()
    two_started = asyncio.Event()
    active = 0
    max_active = 0
    calls = 0

    async def model_call(prompt: str) -> str:
        nonlocal active, max_active, calls
        calls += 1
        active += 1
        max_active = max(max_active, active)
        if active == 2:
            two_started.set()
        try:
            await release.wait()
            return valid_genesis_json
        finally:
            active -= 1

    budget = GenesisProviderBudget.for_test(
        repository=repo,
        max_concurrency=2,
        burst_tokens=4,
        refill_tokens_per_second=4.0,
    )
    service = GenesisService.for_test(
        repository=repo,
        model_call=model_call,
        provider_budget=budget,
    )
    tasks = [service.schedule(ref, source) for ref, source in persona_cases[:4]]

    await asyncio.wait_for(two_started.wait(), timeout=1)
    assert calls == 2
    assert max_active == 2
    release.set()
    await asyncio.gather(*tasks)
    assert calls == 4
    assert max_active == 2
    assert budget.snapshot().leased == 0


@pytest.mark.asyncio
async def test_global_provider_backoff_survives_restart_and_blocks_other_personas(
    repo,
    persona_cases,
    valid_genesis_json,
    manual_clock,
) -> None:
    calls = 0

    async def rate_limited(_prompt: str) -> str:
        nonlocal calls
        calls += 1
        raise GenesisProviderRetryable("rate limited", retry_after_ms=5_000)

    first_budget = GenesisProviderBudget.for_test(
        repository=repo,
        clock=manual_clock,
        max_concurrency=1,
        burst_tokens=2,
        refill_tokens_per_second=1.0,
    )
    first_service = GenesisService.for_test(
        repository=repo,
        model_call=rate_limited,
        provider_budget=first_budget,
    )
    await first_service.schedule(*persona_cases[0])
    blocked_until = first_budget.snapshot().next_allowed_at_ms
    assert blocked_until == manual_clock.now_ms() + 5_000

    async def succeeds(_prompt: str) -> str:
        nonlocal calls
        calls += 1
        return valid_genesis_json

    restarted_budget = GenesisProviderBudget.for_test(
        repository=repo,
        clock=manual_clock,
        max_concurrency=1,
        burst_tokens=2,
        refill_tokens_per_second=1.0,
    )
    restarted = GenesisService.for_test(
        repository=repo,
        model_call=succeeds,
        provider_budget=restarted_budget,
    )
    pending = restarted.schedule(*persona_cases[1])
    await asyncio.sleep(0)
    assert calls == 1
    assert pending.done() is False

    manual_clock.advance_ms(4_999)
    await asyncio.sleep(0)
    assert calls == 1
    manual_clock.advance_ms(1)
    await pending
    assert calls == 2
    assert restarted_budget.snapshot().leased == 0


@pytest.mark.asyncio
async def test_cancelled_genesis_releases_global_provider_permit(
    repo,
    persona_cases,
    valid_genesis_json,
) -> None:
    first_started = asyncio.Event()
    second_started = asyncio.Event()

    async def model_call(prompt: str) -> str:
        if not first_started.is_set():
            first_started.set()
            await asyncio.Future()
        second_started.set()
        return valid_genesis_json

    budget = GenesisProviderBudget.for_test(
        repository=repo,
        max_concurrency=1,
        burst_tokens=2,
        refill_tokens_per_second=2.0,
    )
    service = GenesisService.for_test(
        repository=repo,
        model_call=model_call,
        provider_budget=budget,
    )
    first = service.schedule(*persona_cases[0])
    await first_started.wait()
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first

    second = service.schedule(*persona_cases[1])
    await asyncio.wait_for(second_started.wait(), timeout=1)
    await second
    assert budget.snapshot().leased == 0
```

- [ ] **Step 2: Run Genesis tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_persona_genesis.py -q
```

Expected: FAIL because `GenesisService` does not exist.

- [ ] **Step 3: Define the exact allowed schema and prompt**

`GenesisProfile` contains only:

```python
ALLOWED_GENESIS_FIELDS = frozenset(
    {
        "traits_prior",
        "voice_prior",
        "boundary_prior",
        "proactivity_prior",
        "circadian_prior",
    }
)
```

The model prompt includes the canonical Persona prompt and begin dialogs, followed by:

```text
Return one JSON object with exactly five keys:
traits_prior, voice_prior, boundary_prior, proactivity_prior, circadian_prior.
Infer tendencies only. Do not invent memories, relationships, conversation history,
life events, projects, user facts, names, or events that have already happened.
Numeric priors must be within [0, 1]. Use only short enums or finite numeric maps.
```

Validate exact keys, recursive JSON scalar/map/list limits, numeric bounds, maximum serialized size, and forbidden semantic keys. A failed response is not persisted.

- [ ] **Step 4: Implement background single-flight behind one global Provider budget**

```python
def schedule(self, persona_ref, source):
    key = (persona_ref.token, persona_ref.lifecycle_generation)
    existing = self._tasks.get(key)
    if existing is not None and not existing.done():
        return existing
    task = asyncio.create_task(
        self._infer_and_commit(
            persona_ref,
            source,
            expected_lifecycle_generation=persona_ref.lifecycle_generation,
        ),
        name=f"sylanne-genesis-{persona_ref.token[-12:]}",
    )
    self._tasks[key] = task
    return task
```

Construct exactly one plugin-level `GenesisProviderBudget` and inject that same object into every Genesis task across every Bot and Persona. It is shared infrastructure only: it may contain counters and timestamps, but no scope, prompt, source, Persona, or user data. Use conservative defaults `max_concurrency=2`, `burst_tokens=4`, `refill_tokens_per_second=1.0`, and `max_backoff_ms=900_000`.

The repository persists this global, generation-CAS metadata at `scope-v1/system/genesis-provider-budget.json`:

```python
@dataclass(frozen=True, slots=True)
class GenesisProviderBudgetState:
    schema_version: Literal["sylanne.genesis-provider-budget.v1"]
    generation: int
    tokens_micros: int
    last_refill_at_ms: int
    next_allowed_at_ms: int
    failure_streak: int
```

The in-flight permit count and FIFO waiter queue stay process-local because all old calls cease on process death; restart reloads the durable token level, refill timestamp, global failure streak, and `next_allowed_at_ms`, so it cannot erase a Provider cooldown or create a restart retry storm.

`GenesisProviderBudget.acquire()` waits in FIFO order until all three conditions hold: the process-local concurrency permit is available, the durable token bucket can atomically consume one token, and the durable global `next_allowed_at_ms` has passed. Only then may `_infer_and_commit()` construct the Provider request or call the model. It returns an async lease whose `finally` path always releases the in-memory permit. Cancellation releases the permit without increasing the failure streak; the already-consumed rate token stays consumed. A successful Provider call atomically clears the global failure streak. A retryable Provider failure atomically advances global `next_allowed_at_ms` to the maximum of Provider `Retry-After` and capped exponential backoff, then records the same Persona-specific retry metadata. Schema rejection after a successful Provider response affects only the Persona attempt and does not trip the shared Provider cooldown.

The request path calls `schedule()` without awaiting it. Until a valid profile exists, the Genesis fragment is omitted; no neutral fake snapshot is written. Persist per-Persona `attempt_count`, `next_retry_at_ms`, `prompt_version`, provider/model metadata, source fingerprint, lifecycle generation, and hashes of the source fields. `schedule()` consults that durable Persona retry time before creating or reusing the single-flight task; `_infer_and_commit()` then awaits the shared Provider budget before building a model call. It catches and records retryable failures so background tasks do not leak unhandled exceptions. `_infer_and_commit()` must call the repository with the captured expected lifecycle generation; retirement/purge invalidates and cancels all matching old-generation tasks before state removal.

- [ ] **Step 5: Atomically unlock growth only after a valid Genesis commit**

Each Persona runtime begins in `awaiting_genesis`. While in that mode, hooks schedule/retry Genesis and let AstrBot produce its base-Persona reply, but they do not construct/tick a Host, write runtime/memory/relation/life/history, start schedulers, enqueue delivery, or commit a transient overlay.

`_infer_and_commit()` CAS-writes the immutable Genesis profile, then creates the initial `PersonaRuntimeSnapshot` from exactly those five priors and flips `growth_enabled=true` in the same Persona-generation transaction. A stale concurrent result loses the CAS and reloads the winner. There is no neutral PersonaRuntime snapshot before this commit. The next turn—not the already-running first turn—may create Session/Relation runtimes and begin growth.

- [ ] **Step 6: Make the overlay consume only an accepted profile**

In `llm_request_pipeline.py`:

```python
profile = runtime.genesis.snapshot(resolved.scope.persona_ref)
if profile is not None and runtime.growth_enabled:
    sink.add(
        resolved.scope,
        "genesis",
        render_genesis_priors(profile),
        source="persona_genesis",
    )
```

The renderer may express only the five priors. It cannot render source prompt text, raw begin dialogs, memories, relationship claims, user facts, or a fabricated life history.

- [ ] **Step 7: Run Genesis and repository tests**

Run:

```powershell
python -m pytest tests/test_persona_genesis.py tests/test_scope_repository.py tests/test_transient_context.py -q
```

Expected: all selected tests pass; the first reply remains unblocked, same-Persona discovery performs one model call, cross-Persona discovery never exceeds the shared Provider budget, cancellation releases permits, and durable global cooldown survives restart.

- [ ] **Step 8: Commit Genesis**

```powershell
git add main.py sylanne_alpha/persona_genesis.py sylanne_alpha/scope_runtime.py sylanne_alpha/scope_repository.py sylanne_alpha/llm_request_pipeline.py tests/test_persona_genesis.py
git commit -m "feat: infer scoped persona genesis in background"
```

### Task 9: Protect reactive delivery with a turn lease and the original event

**Files:**
- Create: `tests/test_scope_delivery.py`
- Create: `sylanne_alpha/scope_delivery.py`
- Modify: `sylanne_alpha/scope_contracts.py`
- Modify: `sylanne_alpha/delivery_ledger.py`
- Modify: `sylanne_alpha/llm_response_pipeline.py`
- Modify: `sylanne_alpha/realtime_dispatch.py`
- Modify: `main.py`
- Modify: `tests/test_v250_realtime_send_save_decoupling.py`

- [ ] **Step 1: Write failing late-response and original-event tests**

```python
import asyncio

import pytest

from sylanne_alpha.scope_contracts import ResolvedTransportScope
from sylanne_alpha.scope_delivery import ReactiveDeliveryCoordinator


def freeze_turn(catalog, scope, protected_delivery_binding):
    transport = ResolvedTransportScope(
        bot_ref=scope.bot_ref,
        session_ref=scope.session_ref,
        identity_quality="event_self_id",
        private_scope_enabled=True,
        disabled_reason=None,
    )
    turn = catalog.begin_turn(
        transport,
        protected_delivery_binding.for_scope(scope),
    )
    return catalog.freeze_persona(turn, scope)


@pytest.mark.asyncio
async def test_new_persona_turn_on_same_transport_invalidates_old_delivery(
    scopes,
    fake_event,
    session_catalog,
    protected_delivery_binding,
) -> None:
    coordinator = ReactiveDeliveryCoordinator(
        lambda text: text,
        session_catalog.current,
        session_catalog.scope_generation,
    )
    old_turn = freeze_turn(
        session_catalog,
        scopes.bot_a_persona_a,
        protected_delivery_binding,
    )
    old = coordinator.begin_turn(
        scopes.bot_a_persona_a,
        fake_event,
        turn_generation=old_turn.turn_generation,
    )
    new_turn = freeze_turn(
        session_catalog,
        scopes.bot_a_persona_b,
        protected_delivery_binding,
    )
    coordinator.begin_turn(
        scopes.bot_a_persona_b,
        fake_event,
        turn_generation=new_turn.turn_generation,
    )

    sent = await coordinator.send_if_current(old, "late A")

    assert sent is False
    assert fake_event.sent == []


@pytest.mark.asyncio
async def test_a_to_b_to_a_leaves_only_latest_turn_current(
    scopes,
    fake_event,
    session_catalog,
    protected_delivery_binding,
) -> None:
    coordinator = ReactiveDeliveryCoordinator(
        lambda text: text,
        session_catalog.current,
        session_catalog.scope_generation,
    )
    leases = []
    for scope in (
        scopes.bot_a_persona_a,
        scopes.bot_a_persona_b,
        scopes.bot_a_persona_a,
    ):
        turn = freeze_turn(session_catalog, scope, protected_delivery_binding)
        leases.append(
            coordinator.begin_turn(
                scope,
                fake_event,
                turn_generation=turn.turn_generation,
            )
        )
    first_a, turn_b, second_a = leases

    assert coordinator.is_current(first_a) is False
    assert coordinator.is_current(turn_b) is False
    assert coordinator.is_current(second_a) is True


@pytest.mark.asyncio
async def test_other_bot_same_umo_does_not_invalidate_delivery(
    scopes,
    fake_event,
    session_catalog,
    protected_delivery_binding,
) -> None:
    coordinator = ReactiveDeliveryCoordinator(
        lambda text: text,
        session_catalog.current,
        session_catalog.scope_generation,
    )
    turn_a = freeze_turn(
        session_catalog,
        scopes.bot_a_persona_a,
        protected_delivery_binding,
    )
    bot_a = coordinator.begin_turn(
        scopes.bot_a_persona_a,
        fake_event,
        turn_generation=turn_a.turn_generation,
    )
    turn_b = freeze_turn(
        session_catalog,
        scopes.bot_b_persona_a,
        protected_delivery_binding,
    )
    coordinator.begin_turn(
        scopes.bot_b_persona_a,
        fake_event,
        turn_generation=turn_b.turn_generation,
    )

    assert coordinator.is_current(bot_a) is True


@pytest.mark.asyncio
async def test_each_reactive_segment_uses_original_event(
    scope,
    fake_event,
    session_catalog,
    protected_delivery_binding,
) -> None:
    coordinator = ReactiveDeliveryCoordinator(
        lambda text: text,
        session_catalog.current,
        session_catalog.scope_generation,
    )
    turn = freeze_turn(session_catalog, scope, protected_delivery_binding)
    lease = coordinator.begin_turn(
        scope,
        fake_event,
        turn_generation=turn.turn_generation,
    )

    assert await coordinator.send_if_current(lease, "first") is True
    assert await coordinator.send_if_current(lease, "second") is True
    assert fake_event.sent == ["first", "second"]
```

- [ ] **Step 2: Run delivery tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_scope_delivery.py -q
```

Expected: FAIL because the coordinator does not exist.

- [ ] **Step 3: Implement in-memory reactive leases**

```python
class ReactiveDeliveryCoordinator:
    def __init__(
        self,
        message_factory,
        turn_reader,
        scope_generation_reader,
    ) -> None:
        self._message_factory = message_factory
        self._turn_reader = turn_reader
        self._scope_generation_reader = scope_generation_reader
        self._current: dict[str, tuple[str, int, int, int]] = {}
        self._events: dict[tuple[str, int], object] = {}

    def begin_turn(self, scope, event, *, turn_generation: int):
        transport = scope.session_ref.token
        current_turn = self._turn_reader(scope.session_ref.token)
        if (
            current_turn is None
            or current_turn.turn_state != "frozen"
            or current_turn.turn_generation != turn_generation
            or current_turn.active_scope_token != scope.storage_token
            or current_turn.active_persona_ref != scope.persona_ref.token
        ):
            raise ScopeUnavailable("persisted frozen turn is unavailable")
        self._current[transport] = (
            scope.storage_token,
            scope.session_ref.generation,
            scope.scope_generation,
            turn_generation,
        )
        self._events[(transport, turn_generation)] = event
        return TurnDeliveryLease(
            transport_session_token=transport,
            resolved_scope_token=scope.storage_token,
            session_generation=scope.session_ref.generation,
            scope_generation=scope.scope_generation,
            turn_generation=turn_generation,
        )

    def is_current(self, lease) -> bool:
        persisted = self._turn_reader(lease.transport_session_token)
        return (
            self._current.get(lease.transport_session_token)
            == (
                lease.resolved_scope_token,
                lease.session_generation,
                lease.scope_generation,
                lease.turn_generation,
            )
            and self._scope_generation_reader(lease.resolved_scope_token)
            == lease.scope_generation
            and persisted is not None
            and persisted.turn_state == "frozen"
            and persisted.turn_generation == lease.turn_generation
            and persisted.active_scope_token == lease.resolved_scope_token
            and (
                lease.transport_session_token,
                lease.turn_generation,
            )
            in self._events
        )

    async def send_if_current(self, lease, text: str) -> bool:
        if not self.is_current(lease):
            return False
        event = self._events[
            (lease.transport_session_token, lease.turn_generation)
        ]
        await event.send(self._message_factory(text))
        return True
```

Production constructs the coordinator with the existing `_astrbot_message` helper, the persisted `SessionCatalog.current` reader, and the repository-backed current-scope-generation reader. It passes only `resolved.turn_generation` returned by Task 4's successful `freeze_persona`; the coordinator never invents or increments a turn generation. The send target is always the captured original event. Event objects remain in-memory and are invalidated on restart, while the monotonic transport turn generation remains persisted for proactive validation.

- [ ] **Step 4: Carry the lease through segmented response and history settlement**

Replace `SegmentedDeliveryTurn(session_key, input_epoch, origin)` with a record containing the frozen `ResolvedScope`, `TurnDeliveryLease`, delivered prefix, and terminal reason. Validate the lease:

1. before every segment send;
2. after the awaited send returns;
3. before rewriting AstrBot assistant history;
4. before conversation-buffer or memory commit.

If the lease becomes stale, set terminal reason `superseded_by_new_turn`, suppress remaining segments, and commit only the prefix that was confirmed before invalidation.

- [ ] **Step 5: Remove reactive `Context.send_message(origin, ...)` paths**

In `llm_response_pipeline.py` and `realtime_dispatch.py`, reactive segmented and first-sentence paths call the coordinator with the original event. `Context.send_message` remains eligible only for Task 10's capability-checked proactive outbox.

- [ ] **Step 6: Run realtime and segmented-delivery regressions**

Run:

```powershell
python -m pytest tests/test_scope_delivery.py tests/test_v250_realtime_send_save_decoupling.py tests/test_semantic_segmentation_pipeline.py tests/test_context_history_isolation.py -q
```

Expected: all selected tests pass; a late A completion cannot send after B begins, and history contains only confirmed segments.

- [ ] **Step 7: Commit reactive lease protection**

```powershell
git add main.py sylanne_alpha/scope_delivery.py sylanne_alpha/scope_contracts.py sylanne_alpha/session_catalog.py sylanne_alpha/delivery_ledger.py sylanne_alpha/llm_response_pipeline.py sylanne_alpha/realtime_dispatch.py tests/test_scope_delivery.py tests/test_v250_realtime_send_save_decoupling.py
git commit -m "fix: fence reactive delivery by scoped turn lease"
```

### Task 10: Add the account-aware durable proactive outbox

**Files:**
- Create: `tests/test_scope_outbox.py`
- Modify: `sylanne_alpha/scope_delivery.py`
- Modify: `sylanne_alpha/scope_repository.py`
- Modify: `sylanne_alpha/session_catalog.py`
- Modify: `sylanne_alpha/proactive_scheduler.py`
- Modify: `sylanne_alpha/proactive_bridge.py`
- Modify: `sylanne_alpha/life_simulation.py`
- Modify: `main.py`
- Modify: `tests/test_proactive_bridge.py`
- Modify: `tests/test_issue43_bridge_residual.py`
- Modify: `tests/test_lifesim_routing_pri.py`
- Modify: `tests/test_wave_l2_t2_05_t2_06_followup_ritual.py`

- [ ] **Step 1: Write failing crash-state, idempotency, and suppression tests**

```python
import pytest

from sylanne_alpha.scope_delivery import (
    DeliveryOutbox,
    DeliveryStatus,
    UnverifiedDeliveryIntent,
)


@pytest.mark.asyncio
async def test_non_idempotent_dispatching_crash_becomes_outcome_unknown(
    repo,
    catalog,
    scope,
    issued_draft,
) -> None:
    outbox = DeliveryOutbox(repo, catalog)
    item = outbox.enqueue(
        issued_draft(scope, text="hello", idempotent=False)
    )
    claimed = outbox.claim(item.delivery_ref, worker_id="w1")
    outbox.mark_dispatching(claimed, worker_id="w1")

    recovered = outbox.recover_after_restart()

    assert recovered[item.delivery_ref].status is DeliveryStatus.OUTCOME_UNKNOWN


def test_crash_before_send_returns_claimed_item_to_pending(
    repo,
    catalog,
    scope,
    issued_draft,
) -> None:
    outbox = DeliveryOutbox(repo, catalog)
    item = outbox.enqueue(
        issued_draft(scope, text="hello", idempotent=False)
    )
    outbox.claim(item.delivery_ref, worker_id="w1")

    recovered = outbox.recover_after_restart()

    assert recovered[item.delivery_ref].status is DeliveryStatus.PENDING


def test_idempotent_dispatching_crash_retries_with_same_delivery_id(
    repo,
    catalog,
    scope,
    issued_draft,
) -> None:
    outbox = DeliveryOutbox(repo, catalog)
    item = outbox.enqueue(
        issued_draft(scope, text="hello", idempotent=True)
    )
    claimed = outbox.claim(item.delivery_ref, worker_id="w1")
    outbox.mark_dispatching(claimed, worker_id="w1")

    recovered = outbox.recover_after_restart()[item.delivery_ref]
    retried = outbox.claim(item.delivery_ref, worker_id="w2")

    assert recovered.status is DeliveryStatus.FAILED_RETRYABLE
    assert retried.delivery_id == item.delivery_id


@pytest.mark.asyncio
async def test_receipt_loss_after_non_idempotent_send_is_never_retried(
    repo,
    catalog,
    scope,
    transport,
    issued_draft,
) -> None:
    transport.behavior = "send_then_lose_receipt"
    outbox = DeliveryOutbox(repo, catalog)
    item = outbox.enqueue(
        issued_draft(scope, text="hello", idempotent=False)
    )

    await outbox.dispatch_one(transport)
    await outbox.dispatch_one(transport)

    assert outbox.get(item.delivery_ref).status is DeliveryStatus.OUTCOME_UNKNOWN
    assert transport.calls == [item.delivery_id]


@pytest.mark.asyncio
async def test_account_proof_change_is_suppressed_without_send(
    repo,
    catalog,
    scope,
    transport,
    issued_draft,
) -> None:
    outbox = DeliveryOutbox(repo, catalog)
    item = outbox.enqueue(
        issued_draft(scope, text="hello", idempotent=True)
    )
    transport.account_addressable = False
    transport.platform_account_count = 2

    await outbox.dispatch_one(transport)

    assert outbox.get(item.delivery_ref).status is DeliveryStatus.SUPPRESSED
    assert transport.calls == []


@pytest.mark.asyncio
async def test_persona_switch_suppresses_old_intent_and_return_requires_fresh_lease(
    repo,
    catalog,
    scopes,
    transport,
    freeze_scope,
    issued_draft,
) -> None:
    scope_a = scopes.bot_a_persona_a
    scope_b = scopes.bot_a_persona_b
    freeze_scope(scope_a)
    outbox = DeliveryOutbox(repo, catalog)
    old = outbox.enqueue(
        issued_draft(scope_a, text="from A", idempotent=True)
    )

    freeze_scope(scope_b)
    await outbox.dispatch_one(transport)
    freeze_scope(scope_a)
    await outbox.dispatch_one(transport)

    assert outbox.get(old.delivery_ref).status is DeliveryStatus.SUPPRESSED
    assert transport.calls == []

    fresh = outbox.enqueue(
        issued_draft(scope_a, text="fresh A", idempotent=True)
    )
    await outbox.dispatch_one(transport)
    assert outbox.get(fresh.delivery_ref).status is DeliveryStatus.SENT_CONFIRMED
    assert transport.calls == [fresh.delivery_id]


def test_scope_alone_cannot_enqueue_a_proactive_delivery(repo, catalog, scope) -> None:
    outbox = DeliveryOutbox(repo, catalog)

    with pytest.raises(UnverifiedDeliveryIntent):
        outbox.enqueue(scope)
```

`freeze_scope` uses the production `begin_turn` + `freeze_persona` calls with a protected binding fixture. `issued_draft` calls only `SessionCatalog.issue_proactive_intent()` with the current adapter proof; it never instantiates `BotDeliveryRef`, `ProactiveDeliveryLease`, or `issuer_mac` in test code.

- [ ] **Step 2: Run outbox tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_scope_outbox.py -q
```

Expected: FAIL because the durable outbox is absent.

- [ ] **Step 3: Implement the approved state machine**

Use these exact primary states:

```python
class DeliveryStatus(str, Enum):
    PENDING = "pending"
    CLAIMED = "claimed"
    DISPATCHING = "dispatching"
    SENT_CONFIRMED = "sent_confirmed"
    FAILED_RETRYABLE = "failed_retryable"
    OUTCOME_UNKNOWN = "outcome_unknown"
    SUPPRESSED = "suppressed"
    EXPIRED = "expired"
```

Persist each transition through repository CAS:

```text
pending -> claimed -> dispatching -> sent_confirmed
              |              |-> failed_retryable only when the adapter proves no
              |              |   send occurred, or idempotent retry is safe
              |              |-> outcome_unknown after a non-idempotent crash,
              |                  post-send exception, or lost receipt
              +-> pending on recovery only when dispatch never began
failed_retryable -> claimed
pending/claimed -> suppressed when Bot account addressing is unavailable
pending/claimed -> expired after expires_at_ms
```

`sent_confirmed`, `outcome_unknown`, `suppressed`, and `expired` are terminal for automatic workers. In particular, `sent_confirmed` never transitions to `failed_retryable`. The owner-only `DeliveryEnvelope` contains the complete serializable `BotDeliveryRef`, its `ProactiveDeliveryLease`, unique `delivery_id`, idempotency key, text, and issuer MAC. The lease freezes the transport SessionRef, expected Persona token and lifecycle generation, Session and scope generations, current transport turn generation, and expiry. Raw platform/self/target values exist only inside this ACL/mode-protected outbox document; filenames, WebUI payloads, diagnostics, metrics, and ordinary logs expose only opaque digests and safe state/reason fields.

The only issuer is:

```python
draft = session_catalog.issue_proactive_intent(
    scope,
    text=text,
    idempotent=idempotent,
    expires_at_ms=expires_at_ms,
    current_account_proof=account_proof_provider.current(platform_id),
)
item = outbox.enqueue(draft)
```

`issue_proactive_intent()` holds the SessionCatalog/repository lock and requires a currently `frozen` record whose BotRef, SessionRef/session generation, effective Persona token/lifecycle generation, scope token/generation, and turn generation exactly match the supplied frozen `SessionScope`. It reloads the owner-only delivery binding, validates its binding digest and the just-fetched current account proof/capability, creates the `BotDeliveryRef` and `ProactiveDeliveryLease`, and HMAC-seals the canonical draft with the scope identity secret. `DeliveryOutbox.enqueue()` accepts only `ProactiveIntentDraft`, verifies the issuer MAC and lease again in the same transaction, then persists it. A plain Scope, raw UMO, client-supplied address, or manually constructed draft raises `UnverifiedDeliveryIntent` and performs zero writes.

`SessionCatalog.validate_proactive_lease()` atomically reads the current transport-session owner, protected binding digest, effective Persona, Persona lifecycle generation, Session generation, scope generation, and turn generation. Claim, immediately-before-send, post-send bookkeeping, and every retry call it under the repository/catalog lock. A Persona switch or newer turn makes the old lease stale: the item becomes `suppressed` with safe reason `persona_or_turn_superseded` and is never redirected into the newly active Persona. Returning A after A → B does not revive A's old item; the A scheduler must request a newly issued draft with a fresh lease.

- [ ] **Step 4: Define the capability boundary**

```python
class AccountAwareTransport(Protocol):
    def can_address(self, delivery_ref: BotDeliveryRef) -> bool:
        return False

    async def send(self, delivery_ref: BotDeliveryRef, text: str) -> str:
        raise RuntimeError("account-aware delivery is unavailable")
```

The AstrBot public fallback may use `Context.send_message(saved_session, chain)` only when the current adapter proof demonstrates that the `platform_id` addresses exactly one current Bot account. When one adapter instance has multiple `self_id` values, the fallback returns unavailable and the item becomes `suppressed`; it never chooses the default account. Every automatic retry revalidates the full `ProactiveDeliveryLease`, cooldown, expiry, and current account proof. An `outcome_unknown` item can continue only after receipt reconciliation or an administrator uses a full-scope nonce to create a new intent while explicitly accepting duplicate risk.

- [ ] **Step 5: Route scheduler and life intents only through the outbox**

`ProactiveScheduler.request_dispatch()` and life-simulation outreach enqueue an immutable intent. `ProactiveBridge.check_and_chat(origin)` and its session override sidecar remain legacy-only and cannot run in scoped mode. Add a mode assertion so a scope outbox and the legacy bridge can never dispatch the same intent.

- [ ] **Step 6: Implement ordered initialize and shutdown recovery**

Initialize:

1. open repository and verify identity key;
2. recover `dispatching` items;
3. expire old items;
4. start one outbox worker per Bot runtime.

Shutdown:

1. stop accepting new proactive intents;
2. cancel claim loops;
3. release `claimed` items back to `pending` only when no send began;
4. leave `dispatching` items durable for restart classification;
5. fsync manifests;
6. release runtimes.

- [ ] **Step 7: Run outbox and proactive regressions**

Run:

```powershell
python -m pytest tests/test_scope_outbox.py tests/test_proactive_bridge.py tests/test_issue43_bridge_residual.py tests/test_lifesim_routing_pri.py tests/test_wave_l2_t2_05_t2_06_followup_ritual.py -q
```

Expected: all selected tests pass; scoped mode has one delivery owner and ambiguous account routing deterministically suppresses.

- [ ] **Step 8: Commit durable proactive delivery**

```powershell
git add main.py sylanne_alpha/scope_delivery.py sylanne_alpha/scope_repository.py sylanne_alpha/session_catalog.py sylanne_alpha/proactive_scheduler.py sylanne_alpha/proactive_bridge.py sylanne_alpha/life_simulation.py tests/test_scope_outbox.py tests/test_proactive_bridge.py tests/test_issue43_bridge_residual.py tests/test_lifesim_routing_pri.py tests/test_wave_l2_t2_05_t2_06_followup_ritual.py
git commit -m "feat: add account-aware proactive delivery outbox"
```

### Task 11: Scope observation history and make cleanup fair and durable

**Files:**
- Modify: `sylanne_alpha/observation_history.py`
- Modify: `sylanne_alpha/scope_repository.py`
- Modify: `sylanne_alpha/session_context.py`
- Modify: `_conf_schema.json`
- Modify: `tests/test_observation_history.py`

- [ ] **Step 1: Write failing multi-scope cleanup tests**

```python
def test_cleanup_rotates_persistently_between_over_share_scopes(history_factory, scopes) -> None:
    store = history_factory(limit_bytes=1_000, target_ratio=0.9)
    store.seed_closed(scopes.bot_a_persona_a, sizes=[400, 300])
    store.seed_closed(scopes.bot_b_persona_a, sizes=[400, 300])

    first = store.cleanup_once()
    cursor_after_first = store.manifest.cleanup_cursor
    restarted = history_factory(limit_bytes=1_000, target_ratio=0.9)
    second = restarted.cleanup_once()

    assert first.deleted_scope != second.deleted_scope
    assert restarted.manifest.cleanup_cursor != cursor_after_first


def test_cleanup_protects_active_and_latest_and_reports_unsatisfiable(
    history_factory,
    scopes,
) -> None:
    store = history_factory(limit_bytes=100, target_ratio=0.9)
    store.seed_active(scopes.bot_a_persona_a, size=80)
    store.seed_closed(scopes.bot_a_persona_a, sizes=[30], mark_latest=True)

    result = store.cleanup_once()

    assert result.deleted_segment is None
    assert result.budget_unsatisfiable is True


def test_unlimited_history_never_deletes(history_factory, scopes) -> None:
    store = history_factory(limit_bytes=0, target_ratio=0.9)
    store.seed_closed(scopes.bot_a_persona_a, sizes=[1_000_000])

    assert store.cleanup_once().deleted_segment is None


def test_empty_or_corrupt_manifest_over_budget_does_not_divide_by_zero(
    history_factory,
) -> None:
    store = history_factory(limit_bytes=100, target_ratio=0.9)
    store.seed_orphaned_bytes(size=200)
    store.corrupt_manifest()

    result = store.cleanup_once()

    assert result.deleted_segment is None
    assert result.budget_unsatisfiable is True


def test_scoped_history_restart_uses_repository_root_and_never_legacy_root(
    tmp_path,
    scope,
) -> None:
    repo = ScopeRepository(tmp_path / "scope-v1")
    legacy_root = tmp_path / "observation-history"
    store = ObservationHistoryStore.from_scope_repository(repo, limit_bytes=10_000)
    store.append(scope, {"kind": "state", "value": 0.5})

    restarted = ObservationHistoryStore.from_scope_repository(repo, limit_bytes=10_000)

    assert restarted.read(scope)
    assert repo.observation_scope_dir(scope).is_dir()
    assert not legacy_root.exists()
```

- [ ] **Step 2: Run the history tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_observation_history.py -q
```

Expected: new fairness, cursor, and `budget_unsatisfiable` assertions fail against the global-oldest implementation.

- [ ] **Step 3: Change history inputs and manifests to opaque scope**

Replace raw `session` arguments and manifest keys with `scope.storage_token`. `ScopeRepository.observation_root` is exactly `scope-v1/observation`; its one global `manifest.json` owns the fair cleanup cursor, while segment bytes live only in `scope-v1/observation/scopes/<scope_storage_token>/`. `observation_scope_dir(scope)` verifies the full parent chain and current scope generation before returning that opaque directory. Manifest schema:

```json
{
  "schema_version": "sylanne.observation.history.v2",
  "generation": 12,
  "cleanup_active": false,
  "cleanup_cursor": "scope_v1_opaque",
  "budget_unsatisfiable": false,
  "scopes": {
    "scope_v1_opaque": {
      "used_bytes": 512,
      "active_segment": "active.jsonl",
      "latest_closed_segment": "segment-0004.jsonl",
      "segments": []
    }
  }
}
```

Write the global manifest through repository lock + expected generation CAS. A stale cleanup cycle reloads and retries candidate selection; it does not delete based on an obsolete manifest.

`SessionContext` no longer constructs `ObservationHistoryStore(Path(resolve_data_root(cfg)) / "observation-history", ...)` in scoped mode. `ScopeRuntimeRegistry` injects the single repository-owned store and every append/read supplies the frozen `SessionScope`. The old root is available only to `legacy_scope_claim.py` as a read-only source; scoped execution never creates, updates, deletes, or falls back to it.

- [ ] **Step 4: Implement one-segment fair cleanup**

For each cleanup cycle:

1. return immediately when `limit_bytes == 0` or usage is at/below the limit;
2. calculate `soft_share = limit_bytes / max(1, retained_scope_count)`, where the count includes only scopes with at least one retained segment;
3. build over-share scopes that own a deletable closed segment;
4. sort opaque scope tokens, start after persisted `cleanup_cursor`, and choose the next over-share scope;
5. within that scope choose its oldest deletable segment;
6. if there is no over-share candidate, choose the global oldest deletable segment;
7. delete exactly one segment, update cursor/generation, and stop;
8. repeat only on a later append or maintenance cycle until usage reaches 90%;
9. if no candidate exists while over budget, set `budget_unsatisfiable=true`.

Always protect every active segment and each scope's latest closed segment. Never delete Genesis, runtime, memory, relationship, life, or delivery records.
Each cleanup decision appends an opaque `ScopeDiagnosticEcho`, manifest generation, segment ID, before/after sizes, cursor, trigger, and unfinished reason to bounded diagnostics; it never records raw IDs or observed text.

- [ ] **Step 5: Preserve the configured retention semantics**

Keep `_conf_schema.json` at:

```json
{
  "sylanne_webui_history_storage_limit_mb": {
    "type": "int",
    "default": 128,
    "description": "全局观测历史容量上限（MB）；0 表示无限制，不按天过期。"
  }
}
```

Preserve this existing key exactly; do not introduce a renamed alias that would silently reset an operator's configured limit. There is no day-based expiry field.

- [ ] **Step 6: Run history, CAS, and restart tests**

Run:

```powershell
python -m pytest tests/test_observation_history.py tests/test_scope_repository.py tests/test_v3_repository_multiprocess.py -q
```

Expected: all selected tests pass; every cycle removes at most one closed segment and restart retains the fair cursor.

- [ ] **Step 7: Commit scoped history**

```powershell
git add _conf_schema.json sylanne_alpha/observation_history.py sylanne_alpha/scope_repository.py sylanne_alpha/session_context.py tests/test_observation_history.py
git commit -m "feat: scope and fairly prune observation history"
```

### Task 12: Quarantine legacy data and support explicit copy-claim

**Files:**
- Create: `sylanne_alpha/legacy_scope_claim.py`
- Create: `tests/test_legacy_scope_claim.py`
- Modify: `sylanne_alpha/state_persistence.py`
- Modify: `sylanne_alpha/scope_repository.py`
- Modify: `main.py`

- [ ] **Step 1: Write failing no-fallback and crash-recovery tests**

```python
import pytest

from sylanne_alpha.legacy_scope_claim import LegacyScopeClaimService


def test_legacy_record_never_appears_in_live_scope_without_claim(service, legacy, scope) -> None:
    record = legacy.write_record({"memory": ["mixed"]})

    assert service.list_legacy()[0].record_id == record.record_id
    assert service.repository.read_component(scope, "memory") is None


def test_claim_copies_with_checksum_and_is_idempotent(service, legacy, scope) -> None:
    record = legacy.write_record({"memory": ["chosen"]})

    first = service.claim(record.record_id, scope, actor="admin")
    second = service.claim(record.record_id, scope, actor="admin")

    assert first.migration_id == second.migration_id
    assert first.source_checksum == record.checksum
    assert service.repository.read_component(scope, "memory").payload == {
        "memory": ["chosen"]
    }
    assert legacy.read_record(record.record_id) == {"memory": ["chosen"]}


def test_interrupted_claim_does_not_publish_partial_state(service, legacy, scope) -> None:
    record = legacy.write_record({"memory": ["chosen"]})
    service.fail_after_staging = True

    with pytest.raises(RuntimeError, match="injected staging failure"):
        service.claim(record.record_id, scope, actor="admin")

    assert service.repository.read_component(scope, "memory") is None
```

- [ ] **Step 2: Run legacy tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_legacy_scope_claim.py -q
```

Expected: FAIL because the claim service does not exist.

- [ ] **Step 3: Implement a read-only legacy inventory**

`LegacyScopeClaimService.scan()` reads existing unscoped files and KV exports through `StatePersistence.load_legacy_*` methods. Each record exposes:

```python
@dataclass(frozen=True, slots=True)
class LegacyRecord:
    record_id: str
    source_kind: str
    checksum: str
    byte_size: int
    contaminated: bool
    discovered_at_ms: int
```

`record_id` is a content-derived opaque digest. The inventory may show safe metadata and export bytes to an authenticated administrator, but live runtimes never read it. Session names, display names, `"default"`, platform IDs, and UMO similarity never assign a record automatically.

- [ ] **Step 4: Implement the staged claim transaction**

Claim order:

1. verify the destination Bot → Persona → Session parent path;
2. read source and verify checksum;
3. create `scope-v1/staging/<migration_id>/payload.json` with exclusive creation;
4. fsync payload and a manifest containing source checksum, destination scope echo, actor, and timestamp;
5. validate the staged payload against the destination component schema;
6. CAS-copy it into the destination namespace;
7. write and fsync `claim-complete.json`;
8. leave the legacy source unchanged.

On restart, an incomplete staging directory is either resumed from its verified manifest or quarantined. A completed migration ID returns the existing result. New state is never written back to legacy and active writes never dual-write.

- [ ] **Step 5: Expose authenticated inventory and claim service methods**

Add service operations consumed by Task 13:

```python
def list_legacy(self) -> tuple[LegacyRecord, ...]:
    return tuple(self._inventory())

def claim(
    self,
    record_id: str,
    destination: SessionScope,
    *,
    actor: str,
) -> ClaimManifest:
    return self._claim_transaction(record_id, destination, actor=actor)
```

Claim requires a full-scope, action-bound one-time nonce. The API cannot accept a raw destination key.

- [ ] **Step 6: Run legacy, persistence, and purge tests**

Run:

```powershell
python -m pytest tests/test_legacy_scope_claim.py tests/test_scope_persistence_isolation.py tests/test_scope_repository.py -q
```

Expected: all selected tests pass; interrupted claims publish no partial state and sources remain readable.

- [ ] **Step 7: Commit legacy quarantine and claim**

```powershell
git add main.py sylanne_alpha/legacy_scope_claim.py sylanne_alpha/state_persistence.py sylanne_alpha/scope_repository.py tests/test_legacy_scope_claim.py
git commit -m "feat: quarantine and explicitly claim legacy state"
```

### Task 13: Freeze one scoped API contract for both WebUI hosts

**Files:**
- Create: `sylanne_alpha/scope_api.py`
- Create: `tests/test_scope_api.py`
- Modify: `sylanne_alpha/webui_routes.py`
- Modify: `sylanne_alpha/webui_server.py`
- Modify: `sylanne_alpha/public_api.py`
- Modify: `main.py`
- Modify: `tests/test_astrbot_web_api_migration_contract.py`
- Modify: `tests/test_webui_contract.py`
- Modify: `tests/test_webui_life_api.py`

- [ ] **Step 1: Write failing parentage and status-code tests**

```python
import pytest

from sylanne_alpha.scope_api import ScopeApiError, ScopeApiService


def test_scope_api_distinguishes_missing_and_wrong_parent(catalog, scopes) -> None:
    api = ScopeApiService(catalog)

    with pytest.raises(ScopeApiError) as missing:
        api.resolve("bot_v1_missing", "persona_v1_P", "session_v1_S")
    assert (missing.value.status, missing.value.code) == (404, "scope_bot_not_found")

    with pytest.raises(ScopeApiError) as wrong_parent:
        api.resolve(
            scopes.bot_a_persona_a.bot_ref.token,
            scopes.bot_b_persona_a.persona_ref.token,
            scopes.bot_a_persona_a.session_ref.token,
        )
    assert (wrong_parent.value.status, wrong_parent.value.code) == (
        403,
        "scope_persona_not_owned",
    )

    persona_scope = api.resolve_persona(
        scopes.bot_a_persona_a.bot_ref.token,
        scopes.bot_a_persona_a.persona_ref.token,
    )
    assert persona_scope.persona_ref == scopes.bot_a_persona_a.persona_ref


def test_persona_snapshot_is_bot_persona_scoped_on_both_hosts(
    pages_client,
    standalone_client,
    scopes,
) -> None:
    path = (
        f"/api/bots/{scopes.bot_a_persona_a.bot_ref.token}"
        f"/personas/{scopes.bot_a_persona_a.persona_ref.token}/snapshot"
    )

    pages = pages_client.get(path)
    standalone = standalone_client.get(path)

    assert pages.status_code == standalone.status_code == 200
    assert pages.json()["scope"] == standalone.json()["scope"] == {
        "bot_ref": scopes.bot_a_persona_a.bot_ref.token,
        "persona_ref": scopes.bot_a_persona_a.persona_ref.token,
    }
    assert pages.json()["scope_generation"] == (
        scopes.bot_a_persona_a.persona_ref.lifecycle_generation
    )

def test_scope_less_private_endpoint_is_gone(api_client) -> None:
    response = api_client.get("/api/state?session=shared")
    assert response.status_code == 410
    assert response.json()["code"] == "scope_required"


def test_pages_sse_emits_invalidation_and_closes(
    pages_client,
    scope_path,
    catalog,
) -> None:
    stream = pages_client.open_sse(scope_path + "/events")
    scope = catalog.scope_for_path(scope_path)
    catalog.invalidate_scope(
        scope,
        expected_scope_generation=scope.scope_generation,
        reason="reset",
    )

    assert stream.next_json()["event"] == "scope_invalidated"
    assert stream.closed is True


def test_standalone_websocket_emits_invalidation_and_closes(
    standalone_client,
    scope_path,
    catalog,
) -> None:
    socket = standalone_client.open_websocket(
        scope_path.replace("/api/", "/ws/") + "/state"
    )
    scope = catalog.scope_for_path(scope_path)
    catalog.invalidate_scope(
        scope,
        expected_scope_generation=scope.scope_generation,
        reason="reset",
    )

    assert socket.next_json()["event"] == "scope_invalidated"
    assert socket.closed is True
```

- [ ] **Step 2: Run API tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_scope_api.py tests/test_webui_contract.py -q
```

Expected: new API assertions fail because the current handler selects the most active, `"default"`, or first session.

- [ ] **Step 3: Implement shared resolution and response echo**

```python
class ScopeApiError(RuntimeError):
    def __init__(self, status: int, code: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code


def resolve_persona(self, bot_ref: str, persona_ref: str) -> PersonaScope:
    bot = self._catalog.bot(bot_ref)
    if bot is None:
        raise ScopeApiError(404, "scope_bot_not_found")
    persona = self._catalog.persona(bot_ref, persona_ref)
    if persona is None and self._catalog.persona_exists(persona_ref):
        raise ScopeApiError(403, "scope_persona_not_owned")
    if persona is None:
        raise ScopeApiError(404, "scope_persona_not_found")
    return PersonaScope(bot_ref=bot, persona_ref=persona)


def resolve(self, bot_ref: str, persona_ref: str, session_ref: str) -> SessionScope:
    self.resolve_persona(bot_ref, persona_ref)
    scope = self._catalog.session_scope(bot_ref, persona_ref, session_ref)
    if scope is None and self._catalog.session_exists(session_ref):
        raise ScopeApiError(403, "scope_session_not_owned")
    if scope is None:
        raise ScopeApiError(404, "scope_session_not_found")
    return scope
```

`catalog.session_scope()` returns the persisted, already parent-verified `SessionScope` including its HMAC `storage_token` and current `scope_generation`; the API never recomputes either value and never supplies generation 0 as a fallback.

Every successful private response merges:

```python
ScopeApiEcho(
    scope=ScopeApiPathEcho(
        bot_ref=scope.bot_ref.token,
        persona_ref=scope.persona_ref.token,
        session_ref=scope.session_ref.token,
    ),
    scope_generation=scope.scope_generation,
    resolved_at_ms=resolved_at_ms,
)
```

The service serializes this dataclass to the documented nested JSON shape through one explicit serializer. Persona-level snapshot responses use `PersonaApiEcho(scope={bot_ref, persona_ref}, scope_generation=persona_ref.lifecycle_generation, resolved_at_ms=...)`. It exposes no raw-session resolver. A scope-less route returns 410 before any catalog lookup, so raw `session=` input can never select, inspect, or mutate private state.

No handler chooses the first or most-active item. `/api/scopes` may auto-label safe display metadata but returns only opaque refs and counts.
Bot labels use configured platform label plus administrator-defined account alias, Persona labels use the AstrBot display name plus an 8–12 character revision short code, and Session labels use safe display metadata. The catalog never returns raw `self_id`, UMO, full source fingerprint, prompt text, or delivery address; duplicate labels remain distinguishable by their safe parent labels and revision short code.

- [ ] **Step 4: Freeze the route table**

Shared resources:

```text
GET  /api/scopes
GET  /api/bots/{bot}/personas/{persona}/snapshot
GET  /api/bots/{bot}/personas/{persona}/sessions/{session}/state
GET  /api/bots/{bot}/personas/{persona}/sessions/{session}/observation-history
GET  /api/bots/{bot}/personas/{persona}/sessions/{session}/memory
GET  /api/bots/{bot}/personas/{persona}/sessions/{session}/life/status
POST /api/bots/{bot}/personas/{persona}/sessions/{session}/nonce/{action}
POST /api/bots/{bot}/personas/{persona}/sessions/{session}/actions/{action}
GET  /api/bots/{bot}/personas/{persona}/sessions/{session}/events
WS   /ws/bots/{bot}/personas/{persona}/sessions/{session}/state  [standalone only]
GET  /api/legacy/records
POST /api/bots/{bot}/personas/{persona}/sessions/{session}/legacy-claims
```

The Persona snapshot is deliberately Bot → Persona scoped and does not require or infer a Session. Its resolver still validates the Bot/Persona parent relation, lifecycle generation, and principal. Export, reset, purge, meltdown, scheduler controls, logs, and every Session-owned private/stateful route follow the complete Session parent prefix. Old scope-less private endpoints return `410 scope_required`; a thin forwarder is allowed only when it validates an already complete scope and never performs selection.

Transport capability is explicit rather than inferred:

- AstrBot Pages registers scoped HTTP and SSE through `Context.register_web_api`; AstrBot 4.26.7 exposes no plugin WebSocket registration contract.
- The standalone aiohttp host exposes the same scoped HTTP/SSE resources plus the scoped WebSocket route.
- Both transports resolve the same persisted `SessionScope`, echo the same `scope_generation`, and terminate on the same generation reader. There is no Pages WebSocket placeholder or unregistered route.

- [ ] **Step 5: Bind destructive nonces to the full authority tuple**

Nonce payload:

```python
NonceBinding(
    principal=principal,
    bot_ref=scope.bot_ref.token,
    persona_ref=scope.persona_ref.token,
    session_ref=scope.session_ref.token,
    scope_generation=generation,
    action=action,
    expires_at_ms=expires_at_ms,
    one_time_token=token,
)
```

A principal without permission for the target scope receives 403. A nonce binding mismatch, cross-scope/cross-action replay, consumed token, expiry, or stale scope generation receives 409; 404 is reserved for a missing parent. A valid nonce is consumed exactly once.

- [ ] **Step 6: Adapt AstrBot Pages with verified route syntax**

Register Flask-style paths:

```python
self.context.register_web_api(
    f"/{PLUGIN_NAME}/api/bots/<bot_ref>/personas/<persona_ref>/sessions/<session_ref>/state",
    self._scope_pages_state,
    ["GET"],
    "Sylanne scoped state",
)
```

Register the Persona snapshot separately as:

```python
self.context.register_web_api(
    f"/{PLUGIN_NAME}/api/bots/<bot_ref>/personas/<persona_ref>/snapshot",
    self._scope_pages_persona_snapshot,
    ["GET"],
    "Sylanne Persona snapshot",
)
```

Use `from astrbot.api.web import request, stream_response`. Capture all `request.path_params`, query, and authorization data inside the handler before returning an SSE `StreamingResponse`; the generator must not read module-level `request` after the handler returns.

SSE frames use:

```python
yield "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"
```

The Pages registration root is always `f"/{PLUGIN_NAME}/..."`, matching the repository's existing `_register_web_apis` convention. The embedded frontend bridge continues to call the unprefixed, no-leading-slash endpoint `api/bots/...`; AstrBot adds the plugin root. Contract tests assert both sides so neither a literal `"sylanne"` prefix nor a double prefix can ship.

The Pages SSE stream is bound to the resolved scope generation. On generation change it emits one `scope_invalidated` event and closes. Capture every request value before constructing the generator.

- [ ] **Step 7: Adapt standalone aiohttp and stdlib fallback to the same service**

`webui_server.py` parses aiohttp `{bot_ref}` path parameters, calls `ScopeApiService`, and serializes the same payload/error object as Pages. The stdlib fallback also delegates to the service. Remove duplicated most-active/default selection logic from `webui_routes.py` and `_build_state`.
The standalone WebSocket performs the same parent validation before upgrade, freezes the current scope generation in the connection, and closes with one `scope_invalidated` frame when that generation changes. Legacy `/ws/state` returns `410 scope_required` before upgrade.

- [ ] **Step 8: Run API, Pages, life, and stream regressions**

Run:

```powershell
python -m pytest tests/test_scope_api.py tests/test_astrbot_web_api_migration_contract.py tests/test_webui_contract.py tests/test_webui_life_api.py -q
```

Expected: all selected tests pass; both hosts return identical Persona snapshot and Session-state status/code/echo schemas; the Pages SSE and standalone WebSocket each close on scope invalidation.

- [ ] **Step 9: Commit the scoped API**

```powershell
git add main.py sylanne_alpha/scope_api.py sylanne_alpha/webui_routes.py sylanne_alpha/webui_server.py sylanne_alpha/public_api.py tests/test_scope_api.py tests/test_astrbot_web_api_migration_contract.py tests/test_webui_contract.py tests/test_webui_life_api.py
git commit -m "feat: expose one full-scope WebUI API"
```

### Task 14: Replace the frontend session fallback with Bot → Persona → Session

**Files:**
- Create: `webui-src/src/stores/scope.ts`
- Create: `webui-src/src/stores/scope.test.ts`
- Modify: `webui-src/src/api/types.ts`
- Modify: `webui-src/src/api/client.ts`
- Modify: `webui-src/src/api/client.test.ts`
- Delete: `webui-src/src/stores/session.ts`
- Delete: `webui-src/src/stores/session.test.ts`
- Modify: `webui-src/src/stores/live.ts`
- Modify: `webui-src/src/stores/live.test.ts`
- Modify: `webui-src/src/components/shell/TopBar.vue`
- Modify: `webui-src/src/views/AdminView.vue`
- Modify: `webui-src/src/views/CognitionView.vue`
- Modify: `webui-src/src/views/LifeView.vue`
- Modify: `webui-src/src/views/LogsView.vue`
- Modify: `webui-src/src/views/MemoryView.vue`
- Modify: `webui-src/src/views/MonitorView.vue`
- Modify: `webui-src/src/components/monitor/ObservationChamber.vue`

- [ ] **Step 1: Write failing cascade and unique-only selection tests**

```typescript
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useScopeStore } from './scope'

describe('scope selection', () => {
  beforeEach(() => {
    const values = new Map<string, string>()
    vi.stubGlobal('localStorage', {
      getItem: vi.fn((key: string) => values.get(key) ?? null),
      setItem: vi.fn((key: string, value: string) => values.set(key, value)),
      removeItem: vi.fn((key: string) => values.delete(key)),
    })
    setActivePinia(createPinia())
  })

  afterEach(() => vi.unstubAllGlobals())

  it('auto-selects only a unique item at each tier', () => {
    const store = useScopeStore()
    store.setCatalog({
      schema_version: 'sylanne.scope.catalog.v1',
      generation: 4,
      bots: [
        {
          ref: 'bot_v1_A',
          label: 'A',
          personas: [
            {
              ref: 'persona_v1_P',
              label: 'P',
              revisionShort: 'a1b2c3d4',
              generation: 0,
              sessions: [
                { ref: 'session_v1_S1', label: 'S1', generation: 4 },
                { ref: 'session_v1_S2', label: 'S2', generation: 5 },
              ],
            },
          ],
        },
      ],
    })

    expect(store.selection.botRef).toBe('bot_v1_A')
    expect(store.selection.personaRef).toBe('persona_v1_P')
    expect(store.selection.sessionRef).toBe('')
  })

  it('clears all children and live data when the bot changes', () => {
    const store = useScopeStore()
    store.selection = {
      botRef: 'bot_v1_A',
      personaRef: 'persona_v1_P',
      sessionRef: 'session_v1_S',
    }
    const before = store.selectionEpoch

    store.selectBot('bot_v1_B')

    expect(store.selection).toEqual({
      botRef: 'bot_v1_B',
      personaRef: '',
      sessionRef: '',
    })
    expect(store.selectionEpoch).toBe(before + 1)
  })
})
```

- [ ] **Step 2: Run frontend store tests and verify they fail**

Run:

```powershell
Set-Location 'G:\Sylanne-next\webui-src'
pnpm test -- src/stores/scope.test.ts
```

Expected: FAIL because `useScopeStore` does not exist and the old store selects the first session.

- [ ] **Step 3: Define the exact frontend types**

```typescript
export interface ScopeSelection {
  botRef: string
  personaRef: string
  sessionRef: string
}

export interface ScopeSessionItem {
  ref: string
  label: string
  generation: number
}

export interface ScopePersonaItem {
  ref: string
  label: string
  revisionShort: string
  generation: number
  sessions: ScopeSessionItem[]
}

export interface ScopeBotItem {
  ref: string
  label: string
  personas: ScopePersonaItem[]
}

export interface ScopeCatalog {
  schema_version: 'sylanne.scope.catalog.v1'
  generation: number
  bots: ScopeBotItem[]
}

export interface ScopeApiEcho {
  scope: {
    bot_ref: string
    persona_ref: string
    session_ref: string
  }
  scope_generation: number
  resolved_at_ms: number
}

export interface PersonaApiEcho {
  scope: {
    bot_ref: string
    persona_ref: string
  }
  scope_generation: number
  resolved_at_ms: number
}
```

Remove `SessionInfo`, `current_session`, and raw `session_id` from active response types. Legacy export types may keep explicit `legacy_*` fields.

- [ ] **Step 4: Implement the scope store**

Use storage key `sylanne_scope_selection_v1` with:

```typescript
interface PersistedSelectionV1 {
  schema: 1
  selection: ScopeSelection
}
```

Do not import the old `sylanne_session` value. On catalog load:

1. restore the complete selection only when all three parent links remain valid;
2. otherwise clear the first invalid tier and all descendants;
3. auto-select a tier only when its current parent exposes exactly one item;
4. stop at the first tier with zero or multiple items.

Every selection mutation increments `selectionEpoch`.
Replacing the catalog also increments `selectionEpoch` when the selected Persona or Session `generation` changes, even if the opaque refs stay the same. The store exposes `selectedPersonaGeneration` as soon as Bot + Persona are valid and `selectedScopeGeneration` when all three tiers are valid.

- [ ] **Step 5: Build URLs only from complete selections**

Add:

```typescript
export function scopedApiPath(
  selection: ScopeSelection,
  resource: string,
): string {
  if (!selection.botRef || !selection.personaRef || !selection.sessionRef) {
    throw new Error('complete scope required')
  }
  const bot = encodeURIComponent(selection.botRef)
  const persona = encodeURIComponent(selection.personaRef)
  const session = encodeURIComponent(selection.sessionRef)
  return `/api/bots/${bot}/personas/${persona}/sessions/${session}/${resource}`
}

export function personaApiPath(
  selection: Pick<ScopeSelection, 'botRef' | 'personaRef'>,
  resource: string,
): string {
  if (!selection.botRef || !selection.personaRef) {
    throw new Error('bot and persona scope required')
  }
  const bot = encodeURIComponent(selection.botRef)
  const persona = encodeURIComponent(selection.personaRef)
  return `/api/bots/${bot}/personas/${persona}/${resource}`
}
```

Session-owned API calls use `scopedApiPath`; the Persona dossier uses `personaApiPath(selection, "snapshot")`. There is no `?session=` fallback and the Persona helper never guesses a Session.

Define the live transport selector against verified host capabilities:

```typescript
export type LiveTransportMode =
  | 'standalone-websocket'
  | 'pages-bridge-polling'
  | 'standalone-polling'

export function chooseLiveTransport(
  astrBotBridgeAvailable: boolean,
  websocketAvailable: boolean,
): LiveTransportMode {
  if (astrBotBridgeAvailable) return 'pages-bridge-polling'
  if (websocketAvailable) return 'standalone-websocket'
  return 'standalone-polling'
}
```

The bundled AstrBot Pages client uses authenticated `apiGet` bridge polling because the existing `astrBotBridge.ts` supports GET/POST but cannot carry `AbortSignal`, SSE, or WebSocket. It runs at most one scoped poll at a time and relies on the epoch + scope-echo guard to discard a late bridge result. It never constructs `EventSource` or `WebSocket`. Standalone prefers the scoped WebSocket and falls back to scoped HTTP polling after a connection failure. The backend Pages SSE remains available to capable authenticated consumers, but the bundled Pages UI does not pretend the bridge can stream.

- [ ] **Step 6: Guard every response by epoch and scope echo**

In `live.ts`, capture:

```typescript
const requestedEpoch = scopeStore.selectionEpoch
const requested = { ...scopeStore.selection }
const requestedScopeGeneration = scopeStore.selectedScopeGeneration
```

Abort the prior request, clear `state` immediately, and accept the response only when:

```typescript
requestedEpoch === scopeStore.selectionEpoch &&
requested.botRef === data.scope.bot_ref &&
requested.personaRef === data.scope.persona_ref &&
requested.sessionRef === data.scope.session_ref &&
requestedScopeGeneration !== null &&
data.scope_generation === requestedScopeGeneration
```

Apply the same guard to observation history, life, memory, logs, cognition, modal detail fetches, polling, SSE, and WebSocket updates.

Generation mismatch is an invalidation signal, not a permanent silent discard. When the path still matches but `data.scope_generation` differs:

1. discard that resource payload;
2. coalesce concurrent mismatches into one `/api/scopes` reload;
3. reconcile the complete selection against the returned catalog;
4. if any parent disappeared, clear that tier and descendants;
5. if the same full path remains with the new generation, retry the resource exactly once under the new `selectionEpoch`;
6. if the retry mismatches again, show the existing quiet unavailable state and wait for the next user/poll cycle—never loop.

Standalone WebSocket `scope_invalidated` closes the socket and enters the same catalog reconciliation path before reconnecting. Pages bridge polling and standalone polling share this handler.

Add client regressions in `client.test.ts` and `live.test.ts`:

```typescript
it('uses scoped bridge polling in Pages mode and rejects a late old-scope result', async () => {
  vi.stubGlobal('WebSocket', vi.fn())
  vi.stubGlobal('EventSource', vi.fn())
  const oldRequest = deferred<ScopeApiEcho & { state: object }>()
  bridge.apiGet.mockReturnValueOnce(oldRequest.promise)
  const store = useLiveStore()

  const pending = store.refresh()
  scopeStore.selectBot('bot_v1_B')
  oldRequest.resolve(responseFor('bot_v1_A', 'persona_v1_A', 'session_v1_A', 3))
  await pending

  expect(bridge.apiGet).toHaveBeenCalledWith(
    'api/bots/bot_v1_A/personas/persona_v1_A/sessions/session_v1_A/state',
    {},
  )
  expect(globalThis.WebSocket).not.toHaveBeenCalled()
  expect(globalThis.EventSource).not.toHaveBeenCalled()
  expect(store.state).toBeNull()
})

it.each(['pages-bridge-polling', 'standalone-polling'] as const)(
  'reloads the catalog once and retries after a same-path generation bump in %s',
  async (mode) => {
    seedSelectedScope({ generation: 3 })
    mockStateOnce(responseForSelected({ generation: 4, state: { stale: true } }))
    mockCatalogOnce(catalogForSelected({ generation: 4 }))
    mockStateOnce(responseForSelected({ generation: 4, state: { ready: true } }))

    await useLiveStore().refreshForTest(mode)

    expect(api.getScopes).toHaveBeenCalledTimes(1)
    expect(api.getState).toHaveBeenCalledTimes(2)
    expect(useScopeStore().selectedScopeGeneration).toBe(4)
    expect(useLiveStore().state).toEqual({ ready: true })
  },
)
```

- [ ] **Step 7: Upgrade the TopBar without changing the design language**

Render three existing-style compact selects in order: Bot, Persona, Session. Disable Persona until Bot is selected; disable Session until Persona is selected. Multiple candidates show the existing quiet waiting text “等待选择”. Keep the current monochrome/rose tokens, typography, spacing, borders, and control shapes; do not introduce a new admin visual system.

- [ ] **Step 8: Surface retention, delivery, and legacy controls in existing views**

Extend `ObservationHistoryStorage` with:

```typescript
export interface ObservationHistoryStorage {
  used_bytes: number
  limit_bytes: number | null
  oldest_ms: number | null
  segment_count: number
  cleanup_active: boolean
  budget_unsatisfiable: boolean
}
```

ObservationChamber displays used capacity, `无限` when `limit_bytes` is null, oldest record, cleanup state, and the protected-data warning when the budget is unsatisfiable. It contains no day-retention wording.

Extend scoped state with safe delivery diagnostics:

```typescript
export interface DeliveryDiagnostics {
  pending: number
  failed_retryable: number
  outcome_unknown: number
  suppressed: number
  last_reason?: 'account_route_unavailable' | 'delivery_outcome_unknown'
}
```

AdminView/LogsView render existing-style badges for “账号级路由不可用” and “投递结果未知”; they never show platform ID, self ID, destination, Persona prompt, or UMO.

Reuse the existing Admin/Settings view for `legacy-unscoped`: list opaque record ID short code, size, checksum short code, and contamination warning. The copy-claim control remains disabled until a complete current Scope is selected; activation first requests an action-bound nonce, then posts to that Scope's `/legacy-claims` path. It does not create a new route or mutate/delete the source record.

- [ ] **Step 9: Run frontend unit tests**

Run:

```powershell
Set-Location 'G:\Sylanne-next\webui-src'
pnpm test
```

Expected: all Vitest tests pass, including stale-response rejection and unique-only auto-selection.

- [ ] **Step 10: Commit the frontend scope selector**

```powershell
Set-Location 'G:\Sylanne-next'
git add webui-src/src/api/types.ts webui-src/src/api/client.ts webui-src/src/api/client.test.ts webui-src/src/stores/scope.ts webui-src/src/stores/scope.test.ts webui-src/src/stores/session.ts webui-src/src/stores/session.test.ts webui-src/src/stores/live.ts webui-src/src/stores/live.test.ts webui-src/src/components/shell/TopBar.vue webui-src/src/views/AdminView.vue webui-src/src/views/CognitionView.vue webui-src/src/views/LifeView.vue webui-src/src/views/LogsView.vue webui-src/src/views/MemoryView.vue webui-src/src/views/MonitorView.vue webui-src/src/components/monitor/ObservationChamber.vue
git commit -m "feat: select WebUI state by bot persona session"
```

### Task 15: Add the read-only Persona dossier and whole-card interaction

**Files:**
- Modify: `webui-src/src/api/types.ts`
- Modify: `webui-src/src/api/client.ts`
- Modify: `webui-src/src/views/PersonalityView.vue`
- Create: `webui-src/src/components/persona/PersonaDossier.vue`
- Reference only: `webui-src/src/components/ui/Card.vue`
- Reference only: `webui-src/src/components/ui/Modal.vue`
- Reference only: `webui-src/src/components/monitor/ObservationChamber.vue`
- Create: `webui-src/src/views/personaDossier.test.ts`
- Modify: `webui-src/src/views/monitorObservation.test.ts`
- Modify: `sylanne_alpha/scope_api.py`
- Modify: `tests/test_scope_api.py`

- [ ] **Step 1: Write failing dossier and interaction contract tests**

Without adding `@vue/test-utils`, use the repository's existing source-contract test style:

```typescript
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const source = readFileSync(
  new URL('./PersonalityView.vue', import.meta.url),
  'utf8',
)

describe('persona dossier interaction', () => {
  it('opens from the card and has no observation badge', () => {
    expect(source).toContain('<Card')
    expect(source).toContain('interactive')
    expect(source).toContain('@activate="openPersonaDossier(')
    expect(source).not.toContain('观察')
  })

  it('keeps the approved dossier sections read only', () => {
    expect(source).toContain('基础人格')
    expect(source).toContain('出生推断')
    expect(source).toContain('当前成长')
    expect(source).toContain('更新时间')
    expect(source).not.toContain('<input')
    expect(source).not.toContain('<textarea')
  })
})
```

- [ ] **Step 2: Run the dossier tests and verify they fail**

Run:

```powershell
Set-Location 'G:\Sylanne-next\webui-src'
pnpm test -- src/views/personaDossier.test.ts
```

Expected: FAIL because the Persona card does not open the new read-only dossier.

- [ ] **Step 3: Freeze the safe dossier payload**

Backend response:

```typescript
export interface PersonaDossierResponse extends PersonaApiEcho {
  schema_version: 'sylanne.persona.dossier.v1'
  base: {
    display_name: string
    persona_ref: string
    source_fingerprint_short: string
    resolution_source: string
  }
  genesis: {
    status: 'pending' | 'ready' | 'rejected' | 'backoff'
    traits_prior?: Record<string, number>
    voice_prior?: Record<string, string | number>
    boundary_prior?: Record<string, number>
    proactivity_prior?: Record<string, number>
    circadian_prior?: Record<string, string | number>
  }
  growth: Record<string, string | number>
  updated_at_ms: number
}
```

Do not return the raw Persona prompt, begin dialogs, user text, memories, relationship details, raw IDs, provider secrets, or delivery addresses.

- [ ] **Step 4: Reuse the current chamber and card language**

Make all three existing PersonalityView cards focusable triggers through `Card interactive`: radar opens the dossier focused on 基础人格, six-axis opens it focused on 出生推断, and drift opens it focused on 当前成长. Create `PersonaDossier.vue` around the existing `Modal.vue` and copy only the ObservationChamber layout tokens/motion already present in the product. The dossier contains four read-only groups: 基础人格, 出生推断, 当前成长, 更新时间.

Hover/focus may use only the current rose outline, slight lift, and existing top-edge light. Do not add an “观察” corner badge, extra button, new route, new palette, new icon family, or different radii.

- [ ] **Step 5: Preserve scope and stale-response guards**

Opening the dossier requires only the selected Bot + Persona, captures `selectionEpoch`, those two opaque refs, and `selectedPersonaGeneration`, then requests `personaApiPath(selection, "snapshot")`. It never requires or infers a Session. Closing, changing Bot/Persona, or changing the selected Persona lifecycle generation aborts the fetch and clears the modal payload. A response is displayed only when its two-level scope echo, Persona lifecycle generation, and epoch still match; a Session-only selection change may close the modal by product choice but cannot alter the requested Persona identity.

- [ ] **Step 6: Run dossier, card, and monitor tests**

Run:

```powershell
Set-Location 'G:\Sylanne-next\webui-src'
pnpm test -- src/views/personaDossier.test.ts src/components/ui/cardInteraction.test.ts src/views/monitorObservation.test.ts
```

Expected: all selected tests pass; cards respond to click, Enter, and Space with no observation badge, and the dossier fetch uses the Bot → Persona snapshot route without a Session.

- [ ] **Step 7: Commit the dossier**

```powershell
Set-Location 'G:\Sylanne-next'
git add sylanne_alpha/scope_api.py tests/test_scope_api.py webui-src/src/api/types.ts webui-src/src/api/client.ts webui-src/src/views/PersonalityView.vue webui-src/src/components/persona/PersonaDossier.vue webui-src/src/views/personaDossier.test.ts webui-src/src/views/monitorObservation.test.ts
git commit -m "feat: open read-only persona dossier from cards"
```

### Task 16: Run the complete isolation, packaging, build, and browser acceptance gate

**Files:**
- Modify: `tests/integration/test_scope_astrbot_hook_order.py`
- Modify: `tests/test_package_plugin.py`
- Generated: `UI/index.html`
- Generated: `pages/dashboard/index.html`
- Evidence only: `D:\bun\tmp\codex\Sylanne-next\evidence\`

- [ ] **Step 1: Add the two-Bot concurrent integration test**

The fake AstrBot harness creates two events with the same platform ID, UMO, sender, and Persona ID but different `get_self_id()` values. Barrier the requests so both are in flight, then assert:

```python
assert bot_a.resolved.scope.bot_ref != bot_b.resolved.scope.bot_ref
assert bot_a.resolved.scope.session_ref != bot_b.resolved.scope.session_ref
assert bot_a.runtime.store is not bot_b.runtime.store
assert bot_a.repository_path != bot_b.repository_path
assert bot_a.reactive_event.sent == ["reply A"]
assert bot_b.reactive_event.sent == ["reply B"]
assert bot_a.api_state["scope"]["bot_ref"] != bot_b.api_state["scope"]["bot_ref"]
```

The same test switches Bot A from Persona A → B → A and asserts exact restoration of A's kernel, memory, relationship, life, background queue checkpoint, Session-owned device context, Relation-owned relationship age/first impression/ritual state, Genesis, observation manifest, and generation. It also asserts that Bot B's concurrent queue/checkpoint and relation state remain byte-for-byte unchanged.

A companion integration case concurrently discovers at least four fresh Persona revisions across both Bots, uses an instrumented Provider, and proves only the plugin-wide `GenesisProviderBudget` allowance enters the model at once. It then simulates a retryable Provider failure plus restart and proves the persisted global `next_allowed_at_ms` blocks every Persona until the shared cooldown expires.

- [ ] **Step 2: Add fail-closed and destructive-action integration cases**

Cover:

```python
assert ambiguous_missing_self.private_writes == 0
assert ambiguous_missing_self.proactive_sends == 0
assert awaiting_genesis.private_growth_writes == 0
assert awaiting_genesis.extra_user_content_parts == []
assert wrong_parent_api.status == 403
assert cross_bot_nonce_replay.status == 409
assert stale_scope_write.code == "scope_generation_stale"
assert sibling_bytes_before == sibling_bytes_after_reset
assert non_idempotent_restart.status == "outcome_unknown"
assert ambiguous_proactive.status == "suppressed"
```

Parameterize reset, purge, meltdown, Session invalidation, Bot binding invalidation, PersonaRevision retirement, and delete/recreate. For each transition assert the lifecycle generation increments once and the prior background write, reactive lease, API nonce, frontend response, SSE event, and WebSocket event are rejected; a plain restart keeps the generation stable.

- [ ] **Step 3: Run targeted backend gates**

Run:

```powershell
python -m pytest tests/test_scope_contracts.py tests/test_scope_identity.py tests/test_scope_persona_resolution.py tests/test_scope_repository.py tests/test_scope_runtime.py tests/test_scope_persistence_isolation.py tests/test_transient_context.py tests/test_persona_genesis.py tests/test_scope_delivery.py tests/test_scope_outbox.py tests/test_observation_history.py tests/test_legacy_scope_claim.py tests/test_scope_api.py tests/integration/test_scope_astrbot_hook_order.py -q
```

Expected: all selected tests pass with no skip in the scope contract tests.

- [ ] **Step 4: Run the complete backend suite**

Run:

```powershell
python -m pytest tests/ -v --no-header -p no:cacheprovider
```

Expected: all tests pass. AstrBot-version-specific tests may skip only when their documented external version predicate is not met; the 4.26.7 acceptance environment must not skip Task 1 or Task 16 integration tests.

- [ ] **Step 5: Run lint, type, and plugin validation**

Run:

```powershell
python -m ruff check .
python -m pyright
python 'C:\Users\pidan\.codex\plugins\cache\pidan-local-plugins\2718lab-devkit\0.2.0+codex.20260725190515\skills\astrbot-plugin-dev\scripts\validate_plugin.py' 'G:\Sylanne-next'
```

Expected: all commands exit 0. If the validator script path changed with the installed plugin cache, resolve the current `2718lab-devkit:astrbot-plugin-dev` skill root and run its `scripts/validate_plugin.py`; do not substitute an unrelated validator.

- [ ] **Step 6: Run frontend tests and build**

Run:

```powershell
Set-Location 'G:\Sylanne-next\webui-src'
pnpm test
pnpm build
Set-Location 'G:\Sylanne-next'
git diff -- UI/index.html pages/dashboard/index.html
```

Expected: Vitest and build exit 0; generated diffs contain the scoped frontend and no unrelated asset or design-system replacement.

- [ ] **Step 7: Start both local hosts with scoped test fixtures**

Use two Bot bindings, two Persona revisions, and at least two Sessions under one Persona. Keep logs and fixture state under:

```text
D:\bun\tmp\codex\Sylanne-next\evidence\runtime\
```

The standalone host remains `http://127.0.0.1:2718/`. For AstrBot Pages, copy the actual URL from the running AstrBot plugin page after registration; do not guess a route.

- [ ] **Step 8: Verify the standalone WebUI in the user's installed Browser**

Run:

```powershell
agent-browser --session sylanne-scope-qa open http://127.0.0.1:2718/#/monitor
agent-browser --session sylanne-scope-qa snapshot -i
```

Then use role/name or snapshot refs to verify:

1. Bot → Persona → Session order;
2. multiple candidates stop at “等待选择”;
3. A → B → A restores A without a flash of B;
4. rapid switching cannot apply an old response;
5. card click, Enter, and Space open detail;
6. no “观察” badge exists;
7. Persona dossier is read-only and uses existing chamber styling;
8. history shows used capacity, 128 MB or unlimited, oldest record, cleanup state, and no seven-day wording;
9. suppressed/outcome-unknown delivery states are visible without exposing addresses.

Save screenshots with:

```powershell
agent-browser --session sylanne-scope-qa screenshot 'D:\bun\tmp\codex\Sylanne-next\evidence\standalone-monitor.png'
```

- [ ] **Step 9: Verify AstrBot Pages with the same browser session**

Open the actual registered Pages URL, repeat the same scope selections, and compare payload/status behavior with standalone. Save:

```text
D:\bun\tmp\codex\Sylanne-next\evidence\astrbot-pages-monitor.png
```

Do not use Playwright or another browser. Close the Browser session:

```powershell
agent-browser --session sylanne-scope-qa close
```

- [ ] **Step 10: Inspect secrets, raw IDs, and staged diff**

Run:

```powershell
git diff --check
git status --short
git diff --name-only
Select-String -Path 'sylanne_alpha\*.py','sylanne_alpha\v2core\*.py' -Pattern 'sylanne_embodiment_|create_persona\(|update_persona\(|request\.system_prompt\s*='
```

Expected:

- no whitespace errors;
- only task-owned source, tests, and generated WebUI files changed;
- no active runtime PersonaManager writes;
- no dynamic `request.system_prompt` assignment;
- no raw Bot/self/UMO values in filenames, API scope refs, or normal logs;
- unrelated untracked files remain untouched.

- [ ] **Step 11: Commit generated assets and final integration coverage**

```powershell
git add tests/integration/test_scope_astrbot_hook_order.py tests/test_package_plugin.py UI/index.html pages/dashboard/index.html
git commit -m "test: verify multibot persona isolation end to end"
```

- [ ] **Step 12: Final acceptance**

Main Sol reviews every commit and verifies the approved spec section by section:

- identity and immutable Persona revision;
- full mutable runtime and persistence isolation, including queue checkpoints, device context, relationship age, first impression, and ritual state;
- background Genesis boundaries and the restart-safe global Provider budget;
- at most one Sylanne-tagged temporary request overlay and zero PersonaManager writes;
- reactive lease and durable proactive state machine;
- scoped/fair history and explicit legacy claim;
- 403/404/409/410 API semantics and nonce binding;
- both WebUI hosts, unique-only auto-selection, stale-response rejection, whole-card interaction, no observation badge, and unchanged design language.

Acceptance is denied if any private/stateful path still accepts a raw session key, any ambiguous account can write or send, either host uses a different API contract, or the backend suite cannot be run in a real Python environment.

## Commit sequence

```text
test: lock scoped runtime AstrBot contracts
feat: add opaque multibot scope identities
feat: add atomic scoped state repository
feat: freeze effective persona scope per turn
refactor: isolate mutable runtime by bot persona scope
refactor: cut mutable state over to full scope
refactor: inject runtime context as one temporary part
feat: infer scoped persona genesis in background
fix: fence reactive delivery by scoped turn lease
feat: add account-aware proactive delivery outbox
feat: scope and fairly prune observation history
feat: quarantine and explicitly claim legacy state
feat: expose one full-scope WebUI API
feat: select WebUI state by bot persona session
feat: open read-only persona dossier from cards
test: verify multibot persona isolation end to end
```

Do not squash these commits during implementation. Each is a review and rollback boundary; final publication policy can decide history shape later.
