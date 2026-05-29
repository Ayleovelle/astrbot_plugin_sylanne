# Sylanne WebUI backend integration handoff

## Status

Backend integration is working through AstrBot's plugin API bridge.

- AstrBot panel: `http://154.36.178.25:15356`
- Plugin: `astrbot_plugin_sylanne`
- Version: `Embodiment-1.1.5`
- Latest local fix round: `2026-05-23 session-memory-sync`

The plugin's internal standalone listener also starts successfully.

- Diagnostic endpoint: `/api/plug/astrbot_plugin_sylanne/api/webui_probe`
- Result: `local.ok=true`
- Internal URL: `http://127.0.0.1:2718/api/state`
- Internal schema: `sylanne.webui.state.v1`

The public standalone URL verified in the previous round is:

- `http://154.36.178.32:2718/`

`154.36.178.27:2718` is not the working mapped IP and may still timeout/refuse. Use `.32` for standalone WebUI checks unless the server mapping changes.

## Known UI Truthfulness Gaps

- L1 canvas previously visualized HDC-like activity but did not receive actual 2048-bit samples from the backend.
- L1 log density was previously derived from emotion averages, not true HDC bit density.
- L3 canvas previously used frontend scar/void fallback state unless backend layer diagnostics were present.
- L4 canvas previously used a decorative lattice unless backend sheaf diagnostics were present.
- Production UI must label any non-raw visualization as `derived`, `live-summary`, `offline-preview`, or `unavailable`.
- Current frontend now has these display modes wired, but backend `layers.L1_HDC`, `layers.L3_VoidScar`, and `layers.L4_Sheaf` must be provided for fully truthful live visuals.

## Official AstrBot contract

AstrBot plugin pages are discovered from:

```text
pages/<page_name>/index.html
```

The WebUI page is:

```text
pages/dashboard/index.html
```

Inside plugin pages, use the bridge:

```js
const bridge = window.AstrBotPluginPage;
await bridge.ready();
const state = await bridge.apiGet("api/state", { session: "default" });
```

AstrBot forwards bridge calls to:

```text
/api/plug/<plugin_name>/<endpoint>
```

For Sylanne:

```text
/api/plug/astrbot_plugin_sylanne/api/state
```

Do not call `/<plugin_name>/api/state` from the browser. That route shape is only what the plugin registers internally with `context.register_web_api`; AstrBot exposes it under `/api/plug/...`.

## Backend endpoints

All endpoints below are authenticated through the AstrBot panel.

### State

```http
GET /api/plug/astrbot_plugin_sylanne/api/state?session=default
```

Returns `schema_version: "sylanne.webui.state.v1"`.

Use this as the source for live animation state, emotion-driven theme color, timing display, session selector, HGT/Sheaf/Boundary/Expression panels, and route stats. The deployed server returned timing keys:

```text
perception_ms, gate_ms, void_scar_ms, sheaf_ms, hgt_ms,
boundary_ms, expression_ms, total_ms
```

### Settings

```http
GET /api/plug/astrbot_plugin_sylanne/api/settings
```

Returns:

```json
{
  "schema": {},
  "values": {},
  "providers": []
}
```

The WebUI settings page must render according to `_conf_schema.json`. Do not hard-code old config keys.

Save:

```http
POST /api/plug/astrbot_plugin_sylanne/api/settings
Content-Type: application/json

{
  "sylanne_webui_enabled": true,
  "sylanne_webui_host": "0.0.0.0",
  "sylanne_webui_port": 2718
}
```

Returns:

```json
{ "ok": true, "updated": ["sylanne_webui_enabled"] }
```

### Computation logs

```http
GET /api/plug/astrbot_plugin_sylanne/api/computation_logs?limit=50
```

Returns:

```json
{
  "logs": [],
  "total": 0
}
```

Empty `logs` is valid when no new message has run through `_background_observe_request` since plugin startup. Do not replace it with fake demo logs in production.

### Memory pools

```http
GET /api/plug/astrbot_plugin_sylanne/api/memory_pools?limit=50&session=default
```

Returns:

```json
{
  "schema_version": "sylanne.webui.memory.v1",
  "architecture": "sylanne_alpha.memory_system.three_layer",
  "session": "default",
  "layers": {
    "l1_hot": { "items": [] },
    "l2_warm": { "items": [] },
    "l3_cold": { "nodes": [], "edges": [] }
  },
  "summary": {
    "total": 0,
    "l1_count": 0,
    "l2_count": 0,
    "l3_node_count": 0,
    "l3_edge_count": 0,
    "embedded": 0,
    "avg_weight": 0,
    "avg_temperature": 0.5
  }
}
```

Memory items should be sorted by impression depth/weight on the frontend. The backend already sorts L2/L3 by weight; the frontend also sorts defensively.

### Standalone WebUI probe

```http
GET /api/plug/astrbot_plugin_sylanne/api/webui_probe
```

Returns:

```json
{
  "schema_version": "sylanne.webui.probe.v1",
  "enabled": true,
  "host": "0.0.0.0",
  "port": 2718,
  "local": {
    "ok": true,
    "url": "http://127.0.0.1:2718/api/state",
    "status": 200,
    "schema_version": "sylanne.webui.state.v1",
    "error": ""
  }
}
```

Use this only for diagnostics. If `local.ok=true` but public `154.36.178.27:2718` fails, the remaining problem is server networking, not plugin code.

## Frontend transport rules

Use one `apiFetch()` abstraction:

1. If `window.AstrBotPluginPage` exists, call `bridge.apiGet` / `bridge.apiPost`.
2. If running from an AstrBot `/api/plug/.../dashboard` fallback page, fetch `/api/plug/astrbot_plugin_sylanne/...`.
3. If running from standalone `http://host:2718/`, fetch `/api/...`.
4. If running from `file://` preview, local demo data is allowed only for preview.

Production remote pages must not silently use fake memory/log data when backend fetch fails.

## Session and memory contract

The WebUI session selector is a native `<select>` for compatibility. It is populated from `/api/state.sessions`.

The backend must build `sessions` from more than `_hosts.keys()`:

- live host keys,
- session-scoped three-layer memory systems,
- `_sylanne_memory_cache`,
- persisted alpha runtime snapshots,
- the requested `session` query value.

Three-layer memory is now session-scoped:

- `main.py::_memory_system_for_session(session_key)` returns the L1/L2/L3 `MemorySystem` for that session.
- `_background_observe_request()` writes to the session memory system, saves it into `host.kernel.body.memory["_memory_system"]`, and periodically writes the same object to the plugin KV memory state.
- `_load_sylanne_memory_state()` recognizes the `MemorySystem.to_dict()` shape: `l1`, `l2`, `l3_nodes`, `l3_edges`.

Standalone `webui_server.py` must not close over an old plugin object after hot upload. It now keeps `_active_plugin`; every handler resolves the current plugin at request time. `stop_webui_server()` is called from plugin `terminate()` so old listeners do not keep serving stale data after reinstall.

## Frontend display rules added in this round

- Monitor cards no longer render raw `dim_0` / `sensitivity_0` fields.
- `dim_0..dim_7` are summarized as 8D baseline offset average/peak.
- `sensitivity_0..7` are summarized as sensitivity average/floor.
- Memory cards no longer show `depth=`, `temp=`, `embedding=`, or `session=` machine labels.
- Timing table accepts both legacy `{p50_ns,p99_ns}` timing objects and the current `*_ms` numeric timing fields from `/api/state`.
- The visible session picker is now the native select; the old custom double-layer button UI was removed from HTML.

## Deployment checklist

Before every upload:

```powershell
$env:ASTRBOT_REMOTE_CLEAN_FORMAL='1'
$env:ASTRBOT_REMOTE_CLEAN_FAILED_UPLOAD='1'
$env:ASTRBOT_REMOTE_CLEAN_CONFIRM='astrbot_plugin_sylanne'
node scripts\remote_cleanup_plugin_playwright.js
```

Then upload:

```powershell
$env:ASTRBOT_REMOTE_INSTALL_CONFIRM='1'
$env:ASTRBOT_REMOTE_INSTALL_ZIP='G:\Sylanne_for_astr\.claude\worktrees\sylanne-kernel-x-body\dist\astrbot_plugin_sylanne.zip'
node scripts\remote_install_upload_playwright.js
```

Then verify:

```powershell
node scripts\remote_smoke_playwright.js
```

Finally call:

```http
GET /api/plug/astrbot_plugin_sylanne/api/webui_probe
```

## Key implementation files

- `G:\Sylanne_for_astr\.claude\worktrees\sylanne-kernel-x-body\main.py`
- `G:\Sylanne_for_astr\.claude\worktrees\sylanne-kernel-x-body\sylanne_alpha\webui_server.py`
- `G:\Sylanne_for_astr\.claude\worktrees\sylanne-kernel-x-body\pages\dashboard\index.html`
- `G:\Sylanne_for_astr\.claude\worktrees\sylanne-kernel-x-body\sylanne_alpha\webui.py`
- `G:\Sylanne_for_astr\webui_preview.html`

## Changes made in this handoff

- Added computation log API and ring buffer.
- Added three-layer memory pool API for `sylanne_alpha/memory_system.py`.
- Added standalone WebUI startup helper and config keys:
  - `sylanne_webui_enabled`
  - `sylanne_webui_host`
  - `sylanne_webui_port`
- Fixed standalone startup self-short-circuit in `start_webui_server()`.
- Added no-`aiohttp` stdlib HTTP fallback.
- Added internal standalone listener probe.
- Forced reload of `sylanne_alpha.webui_server` on hot upload.
- Fixed raw AstrBot API path to `/api/plug/astrbot_plugin_sylanne/...`.
- Stopped production remote pages from using offline demo memory when backend fetch fails.
- Added `_active_plugin` to the standalone server so external `2718` and internal AstrBot page read the same live plugin object after hot reinstall.
- Added session-scoped three-layer memory systems and persistence/restore support for `MemorySystem.to_dict()`.
- Expanded WebUI session discovery beyond `_hosts.keys()`.
- Switched session selection UI back to a native dropdown.
- Replaced raw Void-Scar machine fields with readable aggregate metrics.
- Fixed `/api/webui_probe` so it reads the full standalone `/api/state` response instead of truncating at 4096 bytes.

## Current verification target

After the next package upload, verify both internal and standalone endpoints:

```powershell
curl.exe --noproxy "*" -sS -m 20 http://154.36.178.32:2718/api/state
curl.exe --noproxy "*" -sS -m 20 "http://154.36.178.32:2718/api/memory_pools?session=default&limit=50"
```

Inside AstrBot, compare the same session through:

```text
/api/plug/astrbot_plugin_sylanne/api/state?session=default
/api/plug/astrbot_plugin_sylanne/api/memory_pools?session=default&limit=50
```

The two paths should return the same `current_session`, the same `sessions` list, and matching memory `summary`.
