# WebUI Design-System Reference (extracted from current UI/index.html)

> Purpose: faithful port reference for the Vue 3 + Vite + TS rebuild (task #11).
> The user likes the current visual identity and wants it **evolved, not replaced**.
> Source of truth for the *old* look: `UI/index.html` (4158-line single-file dashboard).
> This doc captures its design tokens, component styles, the specimen canvas engine,
> and a refinement punch-list so the rebuild keeps the identity while closing gaps.

## 1. Design tokens

### 1.1 `:root` (dark — default)
```css
:root {
  --bg: #1a1a1b;
  --card: rgba(30,30,30,0.8);
  --card-border: rgba(255,255,255,0.06);
  --text: #f0ece4;
  --text-muted: #888;
  --accent: #B88A9E;              /* signature dusty rose/mauve — the ONE color */
  --glow: rgba(184,138,158,0.15); /* = accent @ 15% */
  --cyan: #00b4d8;
  --red: #ff4444;
  --amber: #ffaa00;
  --void-fill: rgba(0,0,0,0.45);  /* specimen fill, normal */
  --void-solid: 26,26,27;         /* raw rgb triplet = bg, for JS rgba() building */
  --font-head: 'Rajdhani', sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
  --font-body: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --font-xs: 11px; --font-sm: 13px; --font-base: 14px; --font-md: 15px;
}
```

### 1.2 `[data-theme="light"]`
```css
[data-theme="light"] {
  --bg: #f5f4f2; --card: rgba(255,255,255,0.7); --card-border: rgba(0,0,0,0.1);
  --text: #1a1a1a; --text-muted: #666;
  --void-fill: rgba(0,0,0,0.12); --void-solid: 245,244,242;
}
```
`--accent/--glow/--cyan/--red/--amber` and fonts are theme-invariant. There are ~11
per-component light overrides (submit/save buttons → solid `--accent` fill, inputs →
white bg, etc.); the rebuild should promote these into semantic tokens
(e.g. `--btn-primary-bg`) instead of a growing override list.

### 1.3 Radii / shadows / easing / z-index
- Radii in use: 3, 4, 6, 8, 10, 12, 20, 24px; 50% (circles); 100px (full pills).
- Shadows/glows: all built from `rgba(184,138,158,α)` (accent) except status-green/red.
  Key ones: focus ring `0 0 0 2px var(--glow)`; bar-fill glow `0 0 6px rgba(184,138,158,.4)`;
  active spine-node `0 0 10px rgba(184,138,158,.5)`; toast `0 8px 32px rgba(0,0,0,.3)`.
- Easing vocabulary: **snap** `cubic-bezier(0.4,0,0.2,1)` (chrome/slider/menus);
  **organic overshoot** `cubic-bezier(0.25,1,0.2,1)` (entrances). Durations 0.2s hover →
  0.4–0.6s entrances → 1.6s void transition. Global theme cross-fade `.4s ease` on `html,body`.
- Z-index: canvas 1 · phases 10 · header/footer/deco 50 · session-menu 100 · spine-handle 110 ·
  login 200 · fixed-spine 300 · scanline 9999 · meltdown/toast 30000 · loading-screen 50000.
- **No spacing-scale tokens** today (literal 4/6/8/10/12/14/16/20/24/32/36/44px). Introduce
  `--space-1..9` in the rebuild.

## 2. Typography
```html
<link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;700&family=JetBrains+Mono:wght@400;700&display=block" rel="stylesheet">
```
- **Rajdhani** (500/700) = the voice font: body default, all headers, labels, badges, buttons, nav.
- **JetBrains Mono** (400/700) = data only: token input, timing tables, logs, bar values,
  numeric config, session pill, provider text, drift timestamps.
- `display=block` deliberately blocks paint until fonts load (pairs with the loading-screen gate).

## 3. Core component styles (essentials)
- **App shell**: `grid-template-rows: 52px 1fr 36px` (header/content/footer). Content is a
  translateY-driven vertical slider of `.page-section`s, each a 2-col grid with independently
  scrolling left/right columns (scrollbar hidden, top/bottom mask fade). Header/footer start
  off-screen (`translateY(±100%)`) and slide in.
- **Card**: `background:var(--card); border:1px solid var(--card-border); border-radius:12px;
  padding:20px; margin-bottom:16px`. Hover → accent border tint. Entrance: `cardFromLeft/Right`
  slide *toward the center spine* (left col from +40px, right col from −40px), staggered by
  `nth-child` (+0.07s each), `backwards` fill. Container `.awaiting-entrance` keeps cards
  `opacity:0` until backend data resolves.
- **bar-row**: mono label (140px) + `.bar-track` (10px, `rgba(255,255,255,.12)`, radius 5) +
  `.bar-fill` (`var(--accent)`, `width .6s ease`, glow) + mono value (40px right). Reused at 4px
  (mem-weight) and 8px (six-bar) heights.
- **stat-grid**: 2-col; `.stat-box` centered, bg `rgba(255,255,255,.03)`, mono 18px accent value +
  xs muted label. **gate-grid**: 3-col, no box bg. **route-bar**: flex of width-animated segments,
  `.tight` hides text at narrow widths.
- **Badges/pills**: `.mode-badge` (pill, `--glow` bg, accent text); `.log-badge` (radius 4, 4
  route-speed color variants fast=rose/normal=cyan/full=amber/skip=neutral).
  **BUG**: `.badge`/`.switch`/`.slider` (Life page) are used but **never defined** → render as bare
  text / native checkbox. Fix by reusing `.mode-badge` + the toggle component.
- **Buttons**: `.submit-btn` (login) inverted pill (`bg:var(--text)/color:var(--bg)`), hover lift;
  `.save-btn` accent-fill pill; chip buttons (theme/lang/refresh) `1px card-border` pill, hover
  accent border.
- **Spine nav**: fixed centered 40px vertical rail (z 300). `.spine-line` 3px accent gradient
  revealed via `clip-path` wipe (1.6s). `.spine-node` 12px accent circle, `.active` full-opacity +
  glow, hover 1.5× + `::after` tooltip label. `.spine-handle` 16px draggable accent circle → maps
  drag position to nearest page. 7 nodes at top% 18/28/38/48/58/68/78.
- **Toggle**: `.config-toggle` = 36×20 rounded track, off neutral / on accent, `::after` 14px knob
  translateX(16). It's a **div+ARIA fake checkbox** (`role=switch`, onclick) — no keyboard activation
  today (a11y bug). Standardize the rebuild on ONE real-checkbox-backed toggle used everywhere.
- **Meltdown modal**: full-screen overlay (z 30000), backdrop blur fade-in; card box with red border;
  4-char random nonce challenge → exact match enables confirm → swaps to a countdown mode with a big
  pulsing digit + single "abort" button before firing.
- **Form inputs**: `#tokenInput` borderless w/ 2px bottom border, mono 18px, focus → accent; shake on
  invalid. `.config-input/.config-select` radius-6 fields, mono, number spinners removed. Conditional
  `.config-row[data-depends]` accordion reveal.
- **Provider picker**: custom combobox (not native select) — `.provider-btn` + rotating chevron +
  accordion `.provider-menu` of `.provider-opt` (name + mono sub-label), plus a `.manual-opt` that
  reveals an inline text input for a custom provider id. Closes others on open + on outside click.

## 4. Keyframes
`scanDrift` (body::after scanline, 10s), `spin` (0.8s loader / 1.1s verify ring), `fadeUp`
(boot entrance), `cardFromLeft/Right` (card stagger), `shake` (login error, 0.3s), `dotBreath`
(status-dot breathing glow, 3.2s — cadence tied to specimen breathing), `meltdown-pulse`
(countdown heartbeat, 1s). Plus SVG stroke-dasharray wipe for the login verify check/cross, and
the spine-line clip-path wipe.

## 5. Specimen canvas engine (`initNetworkCanvas`/`stopNetworkCanvas`)
Full-viewport `<canvas>` (z 1) behind login — the single most distinctive asset. Reproduce faithfully.

**Specimen blob**: 14 control points, each oscillating via 3 stacked sines (breathing ~5s / secondary /
tremor) with independent random phases; Catmull-Rom→Bézier smoothed closed outline; base radius
`min(W,H)*0.12`. **Pseudopods**: one random point periodically bulges (amp 0.25–0.6·R over ~2s). Fill =
`--void-fill` (→ opaque `rgba(--void-solid,α)` during transition); stroke `rgba(184,138,158,.3)`.

**Scars** (max 12, spawn every 7.5–15s): lens/spindle shape with a 0.6s directional "cut" wipe; color
lifecycle bright pink `rgb(200,140,165)` → dark `rgb(100,50,70)` @ residual α 0.4 forever; positioned by
sampling the *live breathing* radius so they ride the surface. **Agitation** = scars/12 drives pseudopod
frequency (8s→2s) and strength — more wounds = visibly more distressed.

**Gravity particle field** (70 particles): spawn at edges with tangential-dominant velocity (spiral/accretion
look); inverse-square pull `gravityG/(d²+100)`, `gravityG = base(500, or 4000 while expanding)·(1−scars/12)`
— gravity itself decays with wounds; damped ×0.998; brighten with speed/proximity; absorbed inside radius
(80% annihilate, 20% tunnel) then respawn (closed loop). Static overlay: crosshair + edge ticks (microscope
framing), blinking REC dot, 7s scanline sweep.

**Void-transition contract (critical)** — 4 module globals:
```js
voidTransitionState = null;        // null | 'expanding' | 'shrinking'
voidTransitionStart = 0;           // performance.now()
voidTransitionDuration = 1600;     // ms
voidTransitionCallback = null;     // fired exactly once at progress>=1, then state reset
```
Caller sets state/start/duration/callback; the `draw()` loop eases progress (expanding=ease-in-out-quad,
shrinking=ease-out-cubic), interpolates baseRadius between normal and `hypot(W,H)` (screen diagonal → full
coverage), fires callback once and nulls state. Two call sites: **login→dashboard** `transitionToDashboard()`
(expand: reveal spine in sync, callback hides login + `stopNetworkCanvas()` + shows dashboard + `startDashboard()`);
**logout** (a longer CSS choreography first, THEN shrink + `initNetworkCanvas(true)` with skipFadeIn so frame 1
is already full-screen).

**Vue port**: model as a `useVoidTransition()` composable exposing `start(direction, ms): Promise<void>`
(replace raw callback with a resolvable Promise) + reactive `state`/`progress`; a `<SpecimenCanvas>` reads them
each frame. Read colors from CSS tokens (via getComputedStyle/props), not hardcoded rgba, so accent changes
propagate. Also gate canvas motion behind `prefers-reduced-motion` (today it ignores it).

## 6. Responsive + a11y
- `@media (max-width:768px)`: 2-col page-section → single stacked column with natural scroll (an explicit
  fix replacing a prior `.page-right{display:none}` that used to delete right-column functionality on mobile);
  hides spine tooltip on touch.
- `@media (prefers-reduced-motion:reduce)`: global `animation/transition-duration:0.01ms !important` — but does
  NOT reach the canvas RAF loop (rebuild should).
- **Pre-paint theme bootstrap** (inline `<head>` script, must survive migration verbatim — Vue-mounted code
  runs too late and would flash):
```js
(function(){var t=localStorage.getItem('sylanne_theme')||(matchMedia('(prefers-color-scheme:light)').matches?'light':'dark');
document.documentElement.setAttribute('data-theme',t);
var l=localStorage.getItem('sylanne_lang'); if(l)document.documentElement.setAttribute('data-lang',l);})();
```

## 7. Refinement punch-list (fix while porting)
1. Define/replace the undefined `.badge`/`.switch`/`.slider` (Life page) — reuse `.mode-badge` + the toggle.
2. Drop dead `.layer-card` family (old v1 Spine design, zero references).
3. Standardize on ONE toggle component (real checkbox under the hood, styled like `.config-toggle`, keyboard-operable).
4. Introduce `--space-1..9` spacing tokens.
5. Decide `--font-body` usage (currently declared-but-dead; Rajdhani is used everywhere).
6. Collapse per-component light overrides into semantic theme-aware tokens.
7. Canvas engine should read colors from CSS tokens, not duplicated hardcoded rgba.
8. `prefers-reduced-motion` should also throttle/freeze the canvas engine.

## Key line references in the old UI/index.html
- Tokens/theme 21–59 · component CSS 60–563 · responsive/a11y 566–594 · pre-paint script 6–15
- Canvas engine 770–1315 · void-transition globals 773–776 (consumed 960–994, 1074–1085, 1210)
- Transition call sites: `logout()` 1837–1947 (shrink), `transitionToDashboard()` 2010–2060+ (expand)
- Undefined `.badge/.switch/.slider`: 3369, 3408, 3499–3500 · dead `.layer-card`: 436–444
