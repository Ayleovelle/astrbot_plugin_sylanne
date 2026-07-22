# LLM Provider Configuration Consolidation Design

**Date:** 2026-07-22
**Status:** Approved direction; implementation pending
**Scope:** Sylanne WebUI settings, provider resolution, and backward-compatible configuration

## 1. Problem and audit evidence

The current `_conf_schema.json` exposes all 64 settings. `ConfigView.vue` groups them only by key prefix and has no basic/advanced hierarchy. Seven separate provider selectors are distributed across memory, life simulation, and advanced cards, while blank values do not clearly communicate inheritance or automatic selection.

The runtime audit found configuration drift as well as visual overload:

- `sylanne_alpha_fast_assessor_provider_id` has no LLM-call consumer; the real path reads hidden legacy keys.
- `sylanne_alpha_fast_assessor_enabled` and `sylanne_alpha_main_assessor_enabled` do not control their advertised production paths. The real foreground assessor gate is the currently hidden `sylanne_alpha_assessor_llm_enabled`; background/main-assessor calls are gated by their owning memory or scheduler features rather than a global main-assessor switch.
- life simulation hard-requires its own provider today and silently stops when blank.
- transcription already supports automatic multimodal discovery, so its default-visible override is unnecessary.
- relationship classification and Qzone already have partial, inconsistent fallback chains.
- relationship classification currently looks for `_generic_llm_call` on the response pipeline even though that method exists only on the request pipeline, so its advertised provider selector can degrade to a silent no-op.
- embedding providers are a distinct AstrBot provider type and cannot be treated as ordinary chat providers.

The page must be simplified by fixing provider ownership, not by merely hiding the same broken topology.

## 2. Product outcome

The normal setup requires zero provider selections. A cost-conscious user may choose one shared auxiliary text model. An embedding provider appears only when embedding memory is enabled and automatic selection is ambiguous.

The existing two-pane settings page, `Card`, `Select`, `Toggle`, `Badge`, `Button`, and project design tokens remain the visual system. This is a focused change inside the existing UI; it does not introduce a new visual language or page route.

## 3. Model Strategy card

A single **Model Strategy** card replaces default-visible per-feature provider rows. It appears at the top of the right settings pane and contains:

1. **Chat model** — read-only status: “Follows the current AstrBot conversation”.
2. **Auxiliary model** — one optional provider selector whose first option is “Follow chat model (recommended)”. It is shared by text-only assessment, memory organization, life simulation, relationship classification, and Qzone generation.
3. **Image understanding** — read-only status: “Automatic multimodal detection”.
4. **Embedding model** — hidden until embedding memory is enabled. If exactly one embedding provider exists, show it as automatically selected. If multiple exist, show a selector and validation state.
5. **Advanced overrides** — a local, non-persisted “Show per-capability overrides” toggle. When expanded, it shows only overrides that can materially differ from the shared policy.

A badge reports `Automatic`, `Shared auxiliary model`, or `N advanced overrides active`. Existing nonblank specialized values count as active overrides and are never silently discarded.

## 4. Canonical configuration model

Add one canonical optional provider setting:

```text
sylanne_alpha_aux_provider_id
```

Blank means “follow the current/default AstrBot chat provider”. It is not required.

Expose `sylanne_alpha_assessor_llm_enabled` as the canonical foreground-assessor switch with its existing fail-closed default (`false`). This is a control switch, not another model choice.

Keep existing specialized keys readable for backward compatibility:

- `sylanne_alpha_main_assessor_provider_id`
- `sylanne_alpha_life_simulation_provider_id`
- `sylanne_alpha_rel_register_provider_id`
- `sylanne_alpha_qzone_provider_id`
- `sylanne_alpha_transcription_provider_id`
- `sylanne_alpha_embedding_memory_provider_id`
- legacy assessor/emotion aliases already present in deployed configs

These keys move to the advanced UI tier. `sylanne_alpha_fast_assessor_provider_id` becomes the backward-compatible foreground-assessor override there; it no longer appears as an independent normal setting, but an existing value remains visible and editable after the user opens Advanced overrides.

The two dead advertised enable switches are removed from the default schema surface and remain tolerated on load. They are not reinterpreted as active gates, because doing so would unexpectedly enable paid LLM work for installations that merely inherited the old schema defaults. The public settings status reports the real foreground gate; background/main work keeps its existing owner-feature gates.

## 5. Central provider router

Provider fallback logic moves into one small bridge module instead of remaining duplicated across request, life, relationship, transcription, Qzone, and public API code.

Resolution is fail-closed and preserves old explicit behavior:

1. nonblank feature-specific override;
2. nonblank deployed legacy aliases/fallbacks in their existing priority order;
3. nonblank shared auxiliary provider;
4. current conversation provider for event-bound foreground work;
5. AstrBot global/default chat provider for background work;
6. unavailable result with a structured reason.

Feature details:

- **Semantic segmentation:** same-call contract on the current chat model; it never invokes the auxiliary provider.
- **Fast/deep assessment and memory organization:** explicit/legacy assessor override, then auxiliary, then current/default chat provider. Consolidation must not automatically enable an assessor that was actually disabled in the old runtime.
- **Life simulation:** explicit life override, then auxiliary, then global/default chat provider.
- **Relationship classification:** call the central router directly (rather than reaching through either request/response pipeline), then resolve explicit relationship override, legacy assessor chain, auxiliary, and current/default provider.
- **Qzone:** preserve existing explicit `qzone -> life -> main assessor -> legacy assessor` order before auxiliary/default fallback.
- **Transcription:** explicit override, otherwise capability-aware multimodal discovery. The auxiliary provider is used only if AstrBot identifies it as compatible.
- **Embedding:** explicit embedding override, otherwise auto-select only when exactly one embedding provider exists. Multiple or zero matches return an actionable state; never pass a chat provider to `get_embedding(s)`.

All AstrBot calls use locally verified v4.26.5 APIs: `get_current_chat_provider_id(umo)`, `get_using_provider(umo=None)`, `get_all_providers()`, and `get_all_embedding_providers()`.

## 6. Backend settings payload

`/api/settings` continues returning schema, values, and provider inventory. It adds derived, non-secret routing metadata:

```json
{
  "model_routing": {
    "chat": {"mode": "current_conversation"},
    "auxiliary": {"mode": "inherit|explicit", "provider_id": ""},
    "transcription": {"mode": "auto|override"},
    "embedding": {"mode": "disabled|auto|selection_required|explicit"},
    "advanced_override_count": 0
  }
}
```

The payload never exposes masked secrets. Saving remains dirty-key only. Selecting an inheritance option writes the empty string to the canonical/override key; it does not copy a provider ID into every feature key.

## 7. WebUI behavior

`ConfigView.vue` receives explicit UI-tier metadata rather than guessing all behavior from key prefixes. Provider-specific rows owned by the Model Strategy card are excluded from their old groups to avoid duplicates.

Interactions:

- inheritance and automatic choices are visible options, not unexplained blanks;
- manual provider ID entry remains available from the existing selector pattern;
- advanced overrides use existing `Toggle` and row styles;
- disabling a feature hides its dependent override as today;
- keyboard focus, labels, error states, dirty tracking, save feedback, responsive two-pane collapse, and existing typography/tokens remain intact;
- no new route, decorative art, icon family, or card-grid pattern is introduced.

## 8. Migration and compatibility

Migration is read-compatible first:

- never rewrite an old config merely because the page was opened;
- old nonblank feature-specific IDs retain highest priority;
- the UI displays their active override count;
- the dead fast-assessor **provider** page key is honored as a legacy fast-assessor override only when the real foreground assessor gate is enabled;
- the two dead boolean page keys never enable work by themselves;
- unknown/manual provider IDs remain editable and fail closed at runtime;
- a missing or deleted provider produces a bounded warning and falls through only when doing so does not violate an explicit user override.

An explicit invalid override should be visible as invalid rather than silently replaced, while background work may fail closed. This prevents cost or privacy surprises from quietly switching models.

## 9. Test and acceptance matrix

- Audit contract: normal view contains one auxiliary selector, no duplicate specialized selectors.
- Zero-config text features resolve to current/default AstrBot chat provider without requiring setup.
- Legacy explicit IDs retain precedence.
- Fast-assessor schema/runtime key mismatch is covered by a migration regression test.
- Disabled assessors remain disabled after migration.
- Life, relationship, Qzone, and memory fallback order is deterministic.
- Transcription automatic discovery and explicit override both work.
- Embedding never resolves to a chat provider; zero/one/many embedding-provider states are covered.
- Settings GET emits correct derived routing metadata without secrets.
- Settings POST remains dirty-key only and accepts inheritance as an empty value.
- Existing manual-provider behavior, mask behavior, dependent visibility, language switching, save feedback, and responsive layout remain functional.
- Vue type-check/build passes; backend provider-routing tests and AstrBot 4.26.5 integration tests pass.
- Browser verification covers default, one shared auxiliary, active legacy overrides, embedding selection-required, manual provider, save success/error, and mobile-width states.

## 10. Rollout and rollback

Ship the centralized resolver and compatibility tests before hiding old rows. Grey telemetry records only resolution mode/reason, never prompts or provider credentials. Rollback can restore the old row visibility while retaining the router because feature-specific keys remain supported. No configuration value is deleted during the grey release.
