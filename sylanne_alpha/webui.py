"""Embedded Sylanne WebUI HTML fallback."""

WEBUI_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Soulful Sylanne-Embodiment Dashboard Preview</title>
  <style>
  :root {
    /* Dark Theme */
    --bg-primary: #080a0f;
    --bg-secondary: #0f131a;
    --card-bg: rgba(20, 25, 35, 0.65);
    --card-border: rgba(255, 255, 255, 0.06);
    --text-primary: #f1f5f9;
    --text-muted: #94a3b8;
    --text-inverse: #080a0f;
    --primary: #f3a7c8;
    --primary-strong: #f3a7c8;
    --primary-glow: rgba(243, 167, 200, 0.28);
    --mood-primary: #f3a7c8;
    --mood-secondary: #a7d8f3;
    --mood-tertiary: #c8f3a7;
    --mood-glow: rgba(243, 167, 200, 0.28);
    --mood-wash: rgba(243, 167, 200, 0.12);
    --mood-border: rgba(243, 167, 200, 0.34);
    --shadow: rgba(0, 0, 0, 0.6);
    --input-bg: rgba(10, 12, 18, 0.7);
    --panel-blur: blur(20px);

    /* Layer Theme Colors */
    --l1-color: #22d3ee;
    --l2-color: #fbbf24;
    --l3-color: #f87171;
    --l4-color: #c084fc;
    --l5-color: #60a5fa;
    --l6-color: #34d399;
    --l7-color: #f472b6;

    --green: #34d399;
    --red: #f87171;
    --amber: #fbbf24;
    --blue: #60a5fa;
    --purple: #c084fc;
  }

  [data-theme="light"] {
    /* Light Theme */
    --bg-primary: #f8fafc;
    --bg-secondary: #f1f5f9;
    --card-bg: rgba(255, 255, 255, 0.75);
    --card-border: rgba(15, 23, 42, 0.08);
    --text-primary: #0f172a;
    --text-muted: #64748b;
    --text-inverse: #ffffff;
    --primary: #b83276;
    --primary-strong: #9f1f61;
    --primary-glow: rgba(243, 167, 200, 0.22);
    --mood-primary: #f3a7c8;
    --mood-secondary: #93cfe9;
    --mood-tertiary: #b8e6a4;
    --mood-glow: rgba(243, 167, 200, 0.24);
    --mood-wash: rgba(243, 167, 200, 0.16);
    --mood-border: rgba(184, 50, 118, 0.26);
    --shadow: rgba(15, 23, 42, 0.05);
    --input-bg: rgba(255, 255, 255, 0.85);

    /* Brightened layer colors for light mode */
    --l1-color: #0891b2;
    --l2-color: #d97706;
    --l3-color: #dc2626;
    --l4-color: #9333ea;
    --l5-color: #2563eb;
    --l6-color: #059669;
    --l7-color: #db2777;
  }

  * {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    transition: background-color 0.3s ease, border-color 0.3s ease, color 0.3s ease, box-shadow 0.3s ease;
  }

  body {
    background:
      radial-gradient(circle at 76% 8%, var(--mood-wash), transparent 34%),
      radial-gradient(circle at 8% 92%, rgba(167, 216, 243, 0.10), transparent 30%),
      radial-gradient(circle at 80% 10%, var(--bg-secondary), var(--bg-primary));
    color: var(--text-primary);
    min-height: 100vh;
    display: flex;
    overflow: hidden;
  }

  /* Sidebar navigation */
  .sidebar {
    width: 280px;
    background: var(--card-bg);
    backdrop-filter: var(--panel-blur);
    -webkit-backdrop-filter: var(--panel-blur);
    border-right: 1px solid var(--card-border);
    display: flex;
    flex-direction: column;
    height: 100vh;
    z-index: 10;
    flex-shrink: 0;
    box-shadow: 4px 0 24px rgba(0, 0, 0, 0.15);
  }

  .logo-area {
    padding: 28px 24px;
    border-bottom: 1px solid var(--card-border);
    display: flex;
    align-items: center;
    gap: 14px;
  }

  .logo-icon {
    width: 38px;
    height: 38px;
    background: linear-gradient(135deg, var(--mood-primary), var(--mood-secondary));
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #fff;
    font-weight: 800;
    font-size: 1.3rem;
    box-shadow: 0 8px 22px var(--mood-glow);
    text-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
    overflow: hidden;
    flex: 0 0 38px;
  }

  .logo-icon img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }

  .logo-title-group {
    display: flex;
    flex-direction: column;
  }

  .logo-text {
    font-weight: 800;
    font-size: 1.15rem;
    letter-spacing: 0.5px;
    background: linear-gradient(to right, var(--text-primary), var(--mood-primary), var(--mood-secondary));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }

  .logo-subtext {
    font-size: 0.65rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-top: 1px;
  }

  .nav-links {
    list-style: none;
    padding: 24px 16px;
    flex-grow: 1;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .nav-item button {
    width: 100%;
    padding: 14px 18px;
    background: transparent;
    border: none;
    color: var(--text-muted);
    border-radius: 10px;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 14px;
    font-size: 0.95rem;
    font-weight: 600;
    text-align: left;
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  }

  .nav-item button:hover {
    background: rgba(255, 255, 255, 0.04);
    color: var(--text-primary);
    transform: translateX(4px);
  }

  .nav-item.active button {
    background: var(--mood-wash);
    color: var(--primary);
    box-shadow: inset 0 0 0 1px var(--mood-border);
  }

  .nav-item button svg {
    width: 20px;
    height: 20px;
    fill: currentColor;
  }

  .sidebar-footer {
    padding: 20px 24px;
    border-top: 1px solid var(--card-border);
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .theme-toggle-btn {
    width: 46px;
    height: 46px;
    --theme-button-bg: #fff3f8;
    --theme-cover-bg: var(--theme-button-bg);
    background: var(--theme-button-bg);
    border: 1px solid rgba(243, 167, 200, 0.22);
    color: var(--text-muted);
    cursor: pointer;
    padding: 0;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    overflow: hidden;
    transition: border-color 0.2s ease, background 0.2s ease, transform 0.2s ease;
  }

  .theme-toggle-btn:hover {
    --theme-button-bg: #fdeaf3;
    --theme-cover-bg: var(--theme-button-bg);
    border-color: var(--mood-border);
    background: var(--theme-button-bg);
    transform: translateY(-1px);
  }

  [data-theme="dark"] .theme-toggle-btn {
    --theme-button-bg: #2d2a3c;
    --theme-cover-bg: var(--theme-button-bg);
    border-color: rgba(167, 216, 243, 0.18);
  }

  .theme-toggle-stage {
    --toggle-sky: transparent;
    position: relative;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: transparent;
    border: none;
    overflow: hidden;
    isolation: isolate;
    transition: background 0.28s ease, border-color 0.28s ease, transform 0.45s cubic-bezier(0.16, 1, 0.3, 1);
  }

  [data-theme="dark"] .theme-toggle-stage {
    --toggle-sky: transparent;
  }

  .theme-sky-wash {
    display: none;
  }

  .theme-celestial {
    position: absolute;
    inset: 0;
    transform-origin: center;
    transition: transform 0.58s cubic-bezier(0.16, 1, 0.3, 1);
  }

  .theme-core {
    position: absolute;
    left: 50%;
    top: 50%;
    width: 13px;
    height: 13px;
    border-radius: 50%;
    background: #ffd36e;
    box-shadow: inset 0 0 0 0 var(--theme-button-bg);
    transform: translate(-50%, -50%);
    overflow: visible;
    transition: background 0.28s ease, width 0.42s ease, height 0.42s ease, box-shadow 0.58s cubic-bezier(0.16, 1, 0.3, 1), transform 0.58s cubic-bezier(0.16, 1, 0.3, 1);
    z-index: 2;
  }

  .theme-core::after {
    content: "";
    position: absolute;
    left: 22px;
    top: -2.5px;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    background: var(--theme-cover-bg);
    opacity: 0;
    transform: scale(0.9);
    transform-origin: center;
    transition: left 0.58s cubic-bezier(0.16, 1, 0.3, 1), top 0.58s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.22s ease, transform 0.58s cubic-bezier(0.16, 1, 0.3, 1), background 0.2s ease;
    pointer-events: none;
    z-index: 3;
  }

  [data-theme="dark"] .theme-core {
    background: #dbeafe;
    width: 18px;
    height: 18px;
    box-shadow: inset 0 0 0 0 var(--theme-button-bg);
    transform: translate(-50%, -50%);
  }

  [data-theme="dark"] .theme-core::after {
    left: 7px;
    top: 0;
    opacity: 1;
    transform: scale(1);
  }

  .theme-ray {
    position: absolute;
    left: 50%;
    top: 50%;
    width: 2px;
    height: 5px;
    border-radius: 999px;
    background: #ffd36e;
    opacity: 1;
    transform-origin: center;
    transition: opacity 0.24s ease, transform 0.58s cubic-bezier(0.16, 1, 0.3, 1);
    z-index: 1;
  }

  .theme-ray:nth-child(1) { --ray-angle: 0deg; transform: translate(-50%, -50%) rotate(var(--ray-angle)) translateY(-11px); }
  .theme-ray:nth-child(2) { --ray-angle: 45deg; transform: translate(-50%, -50%) rotate(var(--ray-angle)) translateY(-11px); }
  .theme-ray:nth-child(3) { --ray-angle: 90deg; transform: translate(-50%, -50%) rotate(var(--ray-angle)) translateY(-11px); }
  .theme-ray:nth-child(4) { --ray-angle: 135deg; transform: translate(-50%, -50%) rotate(var(--ray-angle)) translateY(-11px); }
  .theme-ray:nth-child(5) { --ray-angle: 180deg; transform: translate(-50%, -50%) rotate(var(--ray-angle)) translateY(-11px); }
  .theme-ray:nth-child(6) { --ray-angle: 225deg; transform: translate(-50%, -50%) rotate(var(--ray-angle)) translateY(-11px); }
  .theme-ray:nth-child(7) { --ray-angle: 270deg; transform: translate(-50%, -50%) rotate(var(--ray-angle)) translateY(-11px); }
  .theme-ray:nth-child(8) { --ray-angle: 315deg; transform: translate(-50%, -50%) rotate(var(--ray-angle)) translateY(-11px); }

  [data-theme="dark"] .theme-ray {
    opacity: 0;
  }

  [data-theme="dark"] .theme-ray {
    transform: translate(-50%, -50%) rotate(var(--ray-angle)) translateY(-5px) scaleY(0.2);
  }

  .theme-star {
    display: none;
  }

  .theme-toggle-btn.switching.to-light .theme-celestial {
    animation: flatSunIn 0.68s cubic-bezier(0.16, 1, 0.3, 1);
  }

  .theme-toggle-btn.switching.to-dark .theme-celestial {
    animation: flatMoonIn 0.68s cubic-bezier(0.16, 1, 0.3, 1);
  }

  .theme-toggle-btn.switching.to-light .theme-toggle-stage,
  .theme-toggle-btn.switching.to-dark .theme-toggle-stage {
    animation: flatTogglePop 0.68s cubic-bezier(0.16, 1, 0.3, 1);
  }

  .theme-toggle-btn.switching.to-light .theme-core {
    animation: flatCoreSun 0.68s cubic-bezier(0.16, 1, 0.3, 1);
  }

  .theme-toggle-btn.switching.to-dark .theme-core {
    animation: flatCoreMoon 0.68s cubic-bezier(0.16, 1, 0.3, 1);
  }

  .theme-toggle-btn.switching.to-light .theme-core::after {
    animation: flatMaskOut 0.68s cubic-bezier(0.16, 1, 0.3, 1);
  }

  .theme-toggle-btn.switching.to-dark .theme-core::after {
    animation: flatMaskIn 0.68s cubic-bezier(0.16, 1, 0.3, 1);
  }

  .theme-toggle-btn.switching.to-light .theme-ray {
    animation: flatRayBloom 0.68s cubic-bezier(0.16, 1, 0.3, 1);
  }

  .theme-toggle-btn.switching.to-dark .theme-ray {
    animation: flatRayFold 0.68s cubic-bezier(0.16, 1, 0.3, 1);
  }

  .theme-toggle-btn.switching .theme-ray:nth-child(2) { animation-delay: 0.02s; }
  .theme-toggle-btn.switching .theme-ray:nth-child(3) { animation-delay: 0.04s; }
  .theme-toggle-btn.switching .theme-ray:nth-child(4) { animation-delay: 0.06s; }
  .theme-toggle-btn.switching .theme-ray:nth-child(5) { animation-delay: 0.08s; }
  .theme-toggle-btn.switching .theme-ray:nth-child(6) { animation-delay: 0.10s; }
  .theme-toggle-btn.switching .theme-ray:nth-child(7) { animation-delay: 0.12s; }
  .theme-toggle-btn.switching .theme-ray:nth-child(8) { animation-delay: 0.14s; }

  @keyframes flatSunIn {
    0% { transform: rotate(-90deg) scale(0.72); }
    48% { transform: rotate(22deg) scale(0.86); }
    76% { transform: rotate(-8deg) scale(1.12); }
    100% { transform: rotate(0deg) scale(1); }
  }

  @keyframes flatMoonIn {
    0% { transform: rotate(70deg) scale(0.76); }
    52% { transform: rotate(-20deg) scale(0.88); }
    78% { transform: rotate(7deg) scale(1.08); }
    100% { transform: rotate(0deg) scale(1); }
  }

  @keyframes flatTogglePop {
    0% { transform: scale(1); }
    42% { transform: scale(0.84); }
    72% { transform: scale(1.08); }
    100% { transform: scale(1); }
  }

  @keyframes flatRingPulse {
    0% { transform: translate(-50%, -50%) scale(0.84); opacity: 0.45; }
    54% { transform: translate(-50%, -50%) scale(1.32); opacity: 1; }
    100% { transform: translate(-50%, -50%) scale(1); opacity: 0.9; }
  }

  @keyframes flatCoreSun {
    0% { transform: translate(-50%, -50%) scale(0.9); background: #dbeafe; width: 18px; height: 18px; box-shadow: inset 0 0 0 0 var(--theme-button-bg); }
    48% { transform: translate(-50%, -50%) scale(0.76); background: #eef4fb; width: 17px; height: 17px; box-shadow: inset 0 0 0 0 var(--theme-button-bg); }
    76% { transform: translate(-50%, -50%) scale(1.12); background: #ffd36e; width: 13px; height: 13px; box-shadow: inset 0 0 0 0 var(--theme-button-bg); }
    100% { transform: translate(-50%, -50%) scale(1); background: #ffd36e; width: 13px; height: 13px; box-shadow: inset 0 0 0 0 var(--theme-button-bg); }
  }

  @keyframes flatCoreMoon {
    0% { transform: translate(-50%, -50%) scale(0.92); background: #ffd36e; width: 13px; height: 13px; box-shadow: inset 0 0 0 0 var(--theme-button-bg); }
    46% { transform: translate(-50%, -50%) scale(0.76); background: #f5dca0; width: 16px; height: 16px; box-shadow: inset 0 0 0 0 var(--theme-button-bg); }
    76% { transform: translate(-50%, -50%) scale(1.08); background: #dbeafe; width: 18px; height: 18px; box-shadow: inset 0 0 0 0 var(--theme-button-bg); }
    100% { transform: translate(-50%, -50%) scale(1); background: #dbeafe; width: 18px; height: 18px; box-shadow: inset 0 0 0 0 var(--theme-button-bg); }
  }

  @keyframes flatMaskOut {
    0% { left: 7px; top: 0; opacity: 1; transform: scale(1); background: var(--theme-cover-bg); }
    58% { left: -4px; top: 1px; opacity: 1; transform: scale(1.04); background: var(--theme-cover-bg); }
    100% { left: -17px; top: 2.5px; opacity: 0; transform: scale(0.9); background: var(--theme-cover-bg); }
  }

  @keyframes flatMaskIn {
    0% { left: 22px; top: -2.5px; opacity: 0; transform: scale(0.9); background: var(--theme-cover-bg); }
    22% { opacity: 1; background: var(--theme-cover-bg); }
    58% { left: 5px; top: 0; opacity: 1; transform: scale(1.04); background: var(--theme-cover-bg); }
    100% { left: 7px; top: 0; opacity: 1; transform: scale(1); background: var(--theme-cover-bg); }
  }

  @keyframes flatRayBloom {
    0% { opacity: 0; transform: translate(-50%, -50%) rotate(var(--ray-angle)) translateY(-5px) scaleY(0.15); }
    54% { opacity: 0; transform: translate(-50%, -50%) rotate(var(--ray-angle)) translateY(-6px) scaleY(0.25); }
    78% { opacity: 1; transform: translate(-50%, -50%) rotate(var(--ray-angle)) translateY(-12px) scaleY(1.18); }
    100% { opacity: 1; transform: translate(-50%, -50%) rotate(var(--ray-angle)) translateY(-11px) scaleY(1); }
  }

  @keyframes flatRayFold {
    0% { opacity: 1; transform: translate(-50%, -50%) rotate(var(--ray-angle)) translateY(-11px) scaleY(1); }
    38% { opacity: 1; transform: translate(-50%, -50%) rotate(var(--ray-angle)) translateY(-12px) scaleY(1.12); }
    100% { opacity: 0; transform: translate(-50%, -50%) rotate(var(--ray-angle)) translateY(-5px) scaleY(0.2); }
  }

  @media (prefers-reduced-motion: reduce) {
    .theme-toggle-btn.switching.to-light .theme-celestial,
    .theme-toggle-btn.switching.to-dark .theme-celestial,
    .theme-toggle-btn.switching.to-light .theme-toggle-stage,
    .theme-toggle-btn.switching.to-dark .theme-toggle-stage,
    .theme-toggle-btn.switching.to-light .theme-sky-wash,
    .theme-toggle-btn.switching.to-dark .theme-sky-wash,
    .theme-toggle-btn.switching.to-light .theme-core,
    .theme-toggle-btn.switching.to-dark .theme-core,
    .theme-toggle-btn.switching.to-light .theme-core::after,
    .theme-toggle-btn.switching.to-dark .theme-core::after,
    .theme-toggle-btn.switching.to-light .theme-ray,
    .theme-toggle-btn.switching.to-dark .theme-ray,
    .theme-toggle-btn.switching.to-light .theme-star,
    .theme-toggle-btn.switching.to-dark .theme-star {
      animation: none;
    }
  }

  /* Main Content Area */
  .main-wrapper {
    flex-grow: 1;
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
  }

  .top-bar {
    height: 76px;
    border-bottom: 1px solid var(--card-border);
    background: var(--card-bg);
    backdrop-filter: var(--panel-blur);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 32px;
    z-index: 5;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  }

  .top-bar-title h2 {
    font-size: 1.25rem;
    font-weight: 700;
    letter-spacing: -0.2px;
  }

  .top-bar-status {
    display: flex;
    align-items: center;
    gap: 20px;
    font-size: 0.85rem;
  }

  .status-wrapper {
    display: flex;
    align-items: center;
    gap: 8px;
    background: rgba(0, 0, 0, 0.15);
    padding: 6px 12px;
    border-radius: 20px;
    border: 1px solid var(--card-border);
  }

  .session-select-shell {
    display: flex;
    align-items: center;
    gap: 8px;
    position: relative;
  }

  .session-label {
    font-size: 0.8rem;
    color: var(--text-muted);
    font-weight: 700;
    white-space: nowrap;
  }

  .session-native-select {
    min-width: 168px;
    max-width: min(320px, 38vw);
    height: 36px;
    border: 1px solid var(--card-border);
    border-radius: 10px;
    background:
      linear-gradient(135deg, rgba(243, 167, 200, 0.08), rgba(243, 167, 200, 0.02)),
      var(--bg-primary);
    color: var(--text-primary);
    padding: 0 12px;
    font-size: 0.82rem;
    font-weight: 800;
    cursor: pointer;
    outline: none;
    transition: border-color 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
  }

  .enhanced-session-picker .session-native-select {
    position: absolute;
    width: 1px;
    height: 1px;
    min-width: 1px;
    opacity: 0;
    pointer-events: none;
  }

  .session-native-select:focus-visible {
    border-color: var(--mood-border);
    box-shadow: 0 0 0 3px var(--mood-wash);
  }

  .session-picker {
    display: none;
    position: relative;
    width: min(330px, 38vw);
    min-width: 190px;
  }

  .enhanced-session-picker .session-picker {
    display: block;
  }

  .session-picker-button {
    width: 100%;
    height: 34px;
    border: 1px solid var(--card-border);
    border-radius: 10px;
    background:
      linear-gradient(135deg, rgba(243, 167, 200, 0.08), rgba(167, 216, 243, 0.04)),
      var(--bg-primary);
    color: var(--text-primary);
    padding: 0 32px 0 12px;
    font-size: 0.82rem;
    font-weight: 800;
    text-align: left;
    cursor: pointer;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
    position: relative;
    transition: border-color 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
  }

  .session-picker-button::after {
    content: "";
    position: absolute;
    right: 12px;
    top: 50%;
    width: 7px;
    height: 7px;
    border-right: 2px solid var(--text-muted);
    border-bottom: 2px solid var(--text-muted);
    transform: translateY(-65%) rotate(45deg);
    transition: transform 0.18s ease, border-color 0.18s ease;
  }

  .session-picker.open .session-picker-button,
  .session-picker-button:focus-visible {
    border-color: var(--mood-border);
    box-shadow: 0 0 0 3px var(--mood-wash);
    outline: none;
  }

  .session-picker.open .session-picker-button::after {
    border-color: var(--primary);
    transform: translateY(-35%) rotate(225deg);
  }

  .session-picker-menu {
    position: absolute;
    z-index: 70;
    top: calc(100% + 8px);
    left: 0;
    right: 0;
    max-height: 220px;
    overflow-y: auto;
    padding: 6px;
    border-radius: 12px;
    border: 1px solid var(--mood-border);
    background: color-mix(in srgb, var(--bg-primary) 90%, var(--card-bg));
    box-shadow: 0 18px 46px rgba(15, 23, 42, 0.22);
    opacity: 0;
    pointer-events: none;
    transform: translateY(-6px) scale(0.98);
    transform-origin: top center;
    transition: opacity 0.22s ease, transform 0.22s cubic-bezier(0.16, 1, 0.3, 1);
  }

  .session-picker.open .session-picker-menu {
    opacity: 1;
    pointer-events: auto;
    transform: translateY(0) scale(1);
  }

  .session-picker-option {
    width: 100%;
    border: none;
    background: transparent;
    color: var(--text-primary);
    border-radius: 8px;
    padding: 8px 10px;
    text-align: left;
    cursor: pointer;
    font-size: 0.82rem;
    font-weight: 800;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
    transition: background 0.16s ease, color 0.16s ease;
  }

  .session-picker-option small {
    display: block;
    margin-top: 2px;
    color: var(--text-muted);
    font-size: 0.68rem;
    font-weight: 700;
  }

  .session-picker-option:hover,
  .session-picker-option.active {
    background: var(--mood-wash);
    color: var(--primary);
  }

  .status-dot {
    width: 10px;
    height: 10px;
    background-color: var(--green);
    border-radius: 50%;
    display: inline-block;
    box-shadow: 0 0 10px var(--green);
    animation: pulseGlow 2s infinite;
  }

  .status-dot.preview {
    background-color: var(--primary);
    box-shadow: 0 0 10px color-mix(in srgb, var(--primary) 58%, transparent);
  }

  .status-dot.bridge {
    background-color: var(--amber);
    box-shadow: 0 0 10px rgba(251, 191, 36, 0.55);
  }

  .status-dot.offline {
    background-color: var(--text-muted);
    box-shadow: none;
    animation: none;
  }

  @keyframes pulseGlow {
    0% { transform: scale(1); opacity: 0.8; }
    50% { transform: scale(1.2); opacity: 1; box-shadow: 0 0 14px var(--green); }
    100% { transform: scale(1); opacity: 0.8; }
  }

  .content-pane {
    flex-grow: 1;
    overflow-y: auto;
    padding: 32px;
  }

  .content-pane.is-switching {
    animation: paneSwitch 0.32s cubic-bezier(0.16, 1, 0.3, 1);
  }

  .tab-pane {
    display: none !important;
  }

  .tab-pane.active {
    display: block !important;
    animation: fadeSlideIn 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards;
  }

  @keyframes fadeSlideIn {
    from {
      opacity: 0;
      transform: translateY(12px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  /* Glassmorphic Grid and Cards */
  .card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 20px;
    margin-bottom: 28px;
  }

  .glass-card {
    background: var(--card-bg);
    backdrop-filter: var(--panel-blur);
    -webkit-backdrop-filter: var(--panel-blur);
    border: 1px solid var(--card-border);
    border-radius: 16px;
    padding: 24px;
    box-shadow: 0 12px 40px var(--shadow);
    position: relative;
    overflow: hidden;
  }

  .glass-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.15), transparent);
  }

  .card-title {
    font-size: 0.9rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 1.2px;
    margin-bottom: 20px;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  /* Emo-metric bars */
  .emo-bar {
    margin-bottom: 16px;
  }

  .emo-bar:last-child {
    margin-bottom: 0;
  }

  .emo-header {
    display: flex;
    justify-content: space-between;
    font-size: 0.85rem;
    margin-bottom: 6px;
  }

  .emo-name {
    font-weight: 600;
  }

  .emo-val {
    font-family: 'Courier New', Courier, monospace;
    font-weight: 700;
  }

  .emo-track {
    height: 9px;
    background: rgba(255, 255, 255, 0.05);
    border-radius: 999px;
    overflow: hidden;
    position: relative;
    box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.2);
    contain: paint;
  }

  @keyframes paneSwitch {
    from {
      opacity: 0.72;
      transform: translateY(6px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .emo-fill {
    height: 100%;
    max-width: 100%;
    border-radius: inherit;
    overflow: hidden;
    transition: width 1.15s cubic-bezier(0.22, 1, 0.36, 1), background-color 0.55s ease;
    position: relative;
    transform-origin: left center;
    will-change: width;
  }

  .emo-fill::after {
    content: none;
  }

  /* Pie stats container */
  .route-pie-wrapper {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 24px;
    padding: 10px 0;
  }

  .route-pie {
    width: 120px;
    height: 120px;
    border-radius: 50%;
    position: relative;
    flex-shrink: 0;
    background: conic-gradient(from -90deg, var(--green) 0% 25%, var(--blue) 25% 50%, var(--purple) 50% 75%, var(--text-muted) 75% 100%);
    -webkit-mask: radial-gradient(circle, transparent 0 51%, #000 52% 100%);
    mask: radial-gradient(circle, transparent 0 51%, #000 52% 100%);
    filter: drop-shadow(0 12px 18px rgba(15, 23, 42, 0.18));
    transition: background 0.5s ease;
  }

  .route-pie::after {
    content: none;
  }

  .route-legend {
    flex-grow: 1;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .legend-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.85rem;
  }

  .legend-label {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--text-muted);
  }

  .legend-color {
    width: 12px;
    height: 12px;
    border-radius: 4px;
  }

  .legend-val {
    font-family: 'Courier New', Courier, monospace;
    font-weight: 700;
  }

  /* Simple stats key-value rows */
  .stats-list {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .stats-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 10px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
    font-size: 0.9rem;
  }

  .stats-row:last-child {
    border-bottom: none;
    padding-bottom: 0;
  }

  .stats-label {
    color: var(--text-muted);
  }

  .stats-value {
    font-weight: 700;
  }

  /* Diagnostic badges */
  .badge {
    display: inline-block;
    padding: 6px 12px;
    border-radius: 8px;
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .badge-green { background: rgba(52, 211, 153, 0.12); color: var(--green); border: 1px solid rgba(52, 211, 153, 0.2); }
  .badge-blue { background: rgba(96, 165, 250, 0.12); color: var(--blue); border: 1px solid rgba(96, 165, 250, 0.2); }
  .badge-purple { background: rgba(192, 132, 252, 0.12); color: var(--purple); border: 1px solid rgba(192, 132, 252, 0.2); }
  .badge-amber { background: rgba(251, 191, 36, 0.12); color: var(--amber); border: 1px solid rgba(251, 191, 36, 0.2); }

  /* Settings items styled beautifully */
  .settings-group {
    margin-bottom: 32px;
  }

  .settings-group-title {
    font-size: 1.05rem;
    font-weight: 700;
    color: var(--primary);
    margin-bottom: 18px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--card-border);
  }

  .setting-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 20px;
    background: var(--input-bg);
    border: 1px solid var(--card-border);
    border-radius: 12px;
    margin-bottom: 12px;
    transition: all 0.2s;
  }

  .setting-row:hover {
    border-color: rgba(59, 130, 246, 0.25);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  }

  .setting-info {
    max-width: 70%;
  }

  .setting-label {
    font-size: 0.95rem;
    font-weight: 600;
    display: block;
  }

  .setting-desc {
    font-size: 0.8rem;
    color: var(--text-muted);
    margin-top: 4px;
    line-height: 1.4;
  }

  /* Beautiful Switch Toggle */
  .switch {
    position: relative;
    display: inline-block;
    width: 52px;
    height: 28px;
  }

  .switch input {
    opacity: 0;
    width: 0;
    height: 0;
  }

  .slider {
    position: absolute;
    cursor: pointer;
    top: 0; left: 0; right: 0; bottom: 0;
    background-color: rgba(255, 255, 255, 0.12);
    transition: .3s cubic-bezier(0.4, 0, 0.2, 1);
    border-radius: 34px;
    border: 1px solid rgba(255,255,255,0.05);
  }

  .slider:before {
    position: absolute;
    content: "";
    height: 20px;
    width: 20px;
    left: 3px;
    bottom: 3px;
    background-color: white;
    transition: .3s cubic-bezier(0.4, 0, 0.2, 1);
    border-radius: 50%;
    box-shadow: 0 2px 5px rgba(0,0,0,0.3);
  }

  input:checked + .slider {
    background-color: var(--green);
  }

  input:checked + .slider:before {
    transform: translateX(24px);
  }

  /* Modern inputs */
  .text-input, .num-input, .select-input {
    background: var(--bg-primary);
    border: 1px solid var(--card-border);
    color: var(--text-primary);
    padding: 10px 14px;
    border-radius: 8px;
    outline: none;
    font-size: 0.9rem;
    min-width: 140px;
    max-width: 220px;
    transition: all 0.2s;
  }

  .text-input:focus, .num-input:focus, .select-input:focus {
    border-color: var(--primary);
    box-shadow: 0 0 0 2px var(--primary-glow);
  }

  .num-input::-webkit-outer-spin-button,
  .num-input::-webkit-inner-spin-button {
    -webkit-appearance: none;
    margin: 0;
  }

  .num-input {
    appearance: textfield;
    -moz-appearance: textfield;
  }

  .number-stepper {
    width: 206px;
    max-width: 30vw;
    min-height: 42px;
    display: grid;
    grid-template-columns: 36px minmax(72px, 1fr) 36px;
    align-items: center;
    gap: 4px;
    padding: 3px;
    border: 1px solid var(--card-border);
    border-radius: 12px;
    background:
      linear-gradient(135deg, rgba(243, 167, 200, 0.09), rgba(167, 216, 243, 0.05)),
      var(--bg-primary);
    transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
  }

  .number-stepper:focus-within,
  .number-stepper:hover {
    border-color: var(--mood-border);
    box-shadow: 0 0 0 3px var(--mood-wash);
  }

  .number-stepper .num-input {
    width: 100%;
    min-width: 0;
    max-width: none;
    height: 34px;
    padding: 0 8px;
    border: none;
    border-radius: 8px;
    background: transparent;
    text-align: center;
    font-family: "Courier New", monospace;
    font-weight: 800;
    color: var(--text-primary);
    box-shadow: none;
  }

  .number-stepper .num-input:focus {
    box-shadow: none;
    border-color: transparent;
  }

  .number-stepper-btn {
    height: 34px;
    width: 34px;
    border: none;
    border-radius: 9px;
    background: rgba(255, 255, 255, 0.06);
    color: var(--text-muted);
    cursor: pointer;
    font-size: 1rem;
    font-weight: 900;
    line-height: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: color 0.18s ease, background 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease;
  }

  .number-stepper-btn:hover {
    color: var(--primary);
    background: var(--mood-wash);
    box-shadow: inset 0 0 0 1px var(--mood-border);
  }

  .number-stepper-btn:active {
    transform: scale(0.92);
  }

  .number-stepper-btn:disabled {
    opacity: 0.35;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
  }

  .provider-input-stack {
    position: relative;
    width: 280px;
    max-width: min(340px, 34vw);
  }

  .provider-picker-button {
    width: 100%;
    min-height: 42px;
    background:
      linear-gradient(135deg, rgba(243, 167, 200, 0.08), rgba(167, 216, 243, 0.06)),
      var(--bg-primary);
    border: 1px solid var(--card-border);
    border-radius: 10px;
    color: var(--text-primary);
    padding: 10px 38px 10px 14px;
    text-align: left;
    cursor: pointer;
    position: relative;
    font-size: 0.9rem;
    font-weight: 700;
    line-height: 1.35;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
    transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
  }

  .provider-picker-button::after {
    content: '';
    position: absolute;
    right: 14px;
    top: 50%;
    width: 8px;
    height: 8px;
    border-right: 2px solid var(--text-muted);
    border-bottom: 2px solid var(--text-muted);
    transform: translateY(-65%) rotate(45deg);
    transition: transform 0.2s ease, border-color 0.2s ease;
  }

  .provider-input-stack.open .provider-picker-button,
  .provider-picker-button:focus-visible {
    border-color: var(--mood-border);
    box-shadow: 0 0 0 3px var(--mood-wash);
    outline: none;
  }

  .provider-input-stack.open .provider-picker-button::after {
    transform: translateY(-35%) rotate(225deg);
    border-color: var(--primary);
  }

  .provider-picker-menu {
    position: absolute;
    z-index: 40;
    left: 0;
    right: 0;
    top: calc(100% + 8px);
    background: color-mix(in srgb, var(--bg-primary) 86%, var(--card-bg));
    border: 1px solid var(--mood-border);
    border-radius: 12px;
    box-shadow: 0 18px 46px rgba(15, 23, 42, 0.20);
    padding: 6px;
    opacity: 0;
    transform: translateY(-6px) scale(0.98);
    pointer-events: none;
    transition: opacity 0.18s ease, transform 0.18s ease;
  }

  .provider-input-stack.open .provider-picker-menu {
    opacity: 1;
    transform: translateY(0) scale(1);
    pointer-events: auto;
  }

  .provider-picker-option {
    width: 100%;
    border: none;
    background: transparent;
    color: var(--text-primary);
    border-radius: 8px;
    padding: 9px 10px;
    text-align: left;
    cursor: pointer;
    font-size: 0.86rem;
    line-height: 1.35;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .provider-picker-option:hover,
  .provider-picker-option.active {
    background: var(--mood-wash);
    color: var(--primary);
  }

  .provider-picker-option small {
    color: var(--text-muted);
    font-family: "Courier New", monospace;
    font-size: 0.72rem;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .provider-manual-wrap {
    max-height: 0;
    opacity: 0;
    transform: translateY(-4px);
    overflow: hidden;
    transition: max-height 0.24s ease, opacity 0.2s ease, transform 0.2s ease, margin-top 0.2s ease;
  }

  .provider-input-stack.manual-active .provider-manual-wrap {
    max-height: 58px;
    opacity: 1;
    transform: translateY(0);
    margin-top: 8px;
  }

  .provider-input-stack .text-input {
    width: 100%;
    max-width: none;
  }

  /* Buttons */
  .btn {
    padding: 12px 24px;
    border-radius: 10px;
    font-size: 0.9rem;
    font-weight: 700;
    cursor: pointer;
    border: none;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  }

  .btn:active {
    transform: scale(0.96);
  }

  .btn-primary {
    background:
      linear-gradient(135deg, rgba(255, 255, 255, 0.30), transparent 42%),
      linear-gradient(135deg, #F3A7C8 0%, #E777AE 58%, #CC4E8D 100%);
    color: #fff;
    box-shadow: 0 8px 20px rgba(243, 167, 200, 0.34);
  }

  .btn-primary:hover {
    filter: saturate(1.03) brightness(1.01);
    box-shadow: 0 10px 24px rgba(243, 167, 200, 0.42);
  }

  .btn-secondary {
    background: rgba(255, 255, 255, 0.05);
    color: var(--text-primary);
    border: 1px solid var(--card-border);
  }

  .btn-secondary:hover {
    background: rgba(255, 255, 255, 0.08);
  }

  /* 7-Layer Spine Evolution */
  .spine-panel {
    display: flex;
    gap: 22px;
    height: calc(100vh - 140px);
  }

  .spine-steps {
    width: 340px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    overflow-y: auto;
    padding: 2px 10px 14px 2px;
  }

  .spine-step-card {
    padding: 14px 16px;
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 10px;
    cursor: pointer;
    position: relative;
    overflow: hidden;
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  }

  .spine-step-card:hover {
    transform: translateY(-2px);
    border-color: rgba(255,255,255,0.15);
  }

  .spine-step-card.active {
    border-color: var(--layer-color);
    background: rgba(255, 255, 255, 0.03);
    box-shadow: 0 6px 20px rgba(0,0,0,0.15);
  }

  .spine-step-card.active::before {
    content: '';
    position: absolute;
    left: 0; top: 0; bottom: 0;
    width: 3px;
    background: var(--layer-color);
  }

  .spine-step-num {
    font-size: 0.72rem;
    font-weight: 800;
    color: var(--layer-color);
    text-transform: uppercase;
    letter-spacing: 0.3px;
  }

  .spine-step-title {
    font-size: 0.95rem;
    font-weight: 800;
    margin-top: 8px;
    line-height: 1.25;
  }

  .spine-step-desc {
    font-size: 0.76rem;
    color: var(--text-muted);
    margin-top: 7px;
    line-height: 1.5;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .spine-visualizer {
    flex-grow: 1;
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 16px;
    padding: 28px;
    display: flex;
    flex-direction: column;
    position: relative;
    box-shadow: 0 12px 40px var(--shadow);
  }

  .visualizer-header {
    margin-bottom: 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .visualizer-title h3 {
    font-size: 1.25rem;
    font-weight: 700;
  }

  .visualizer-title p {
    font-size: 0.85rem;
    color: var(--text-muted);
    margin-top: 4px;
  }

  .visualizer-canvas-container {
    flex-grow: 1;
    position: relative;
    background: var(--input-bg);
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid var(--card-border);
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .canvas-element {
    position: absolute;
    top: 0; left: 0; width: 100%; height: 100%;
  }

  .visualizer-controls {
    margin-top: 20px;
    display: flex;
    gap: 16px;
    align-items: center;
    flex-wrap: wrap;
  }

  /* HGT Templates overlay style inside visualizer controls */
  .template-controls {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  .gate-status-strip {
    width: 100%;
    display: grid;
    grid-template-columns: repeat(3, minmax(92px, 1fr)) minmax(190px, 1.3fr);
    gap: 10px;
    align-items: stretch;
  }

  .gate-metric-card,
  .gate-live-readout,
  .persona-chip {
    background: var(--input-bg);
    border: 1px solid var(--card-border);
    border-radius: 12px;
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
  }

  .gate-metric-card {
    padding: 10px 12px;
    min-height: 58px;
  }

  .gate-metric-card.active {
    border-color: var(--mood-border);
    box-shadow: 0 10px 26px var(--mood-glow);
  }

  .gate-label {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.72rem;
    font-weight: 800;
    letter-spacing: 0.5px;
    color: var(--text-muted);
  }

  .gate-dot {
    width: 8px;
    height: 8px;
    border-radius: 999px;
    background: var(--green);
    box-shadow: 0 0 10px currentColor;
  }

  .gate-value {
    margin-top: 6px;
    font-family: "Courier New", monospace;
    font-size: 1rem;
    font-weight: 800;
    color: var(--text-primary);
  }

  .gate-live-readout {
    padding: 10px 14px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 4px;
    border-color: var(--mood-border);
  }

  .gate-live-title {
    font-size: 0.72rem;
    font-weight: 800;
    color: var(--primary);
    letter-spacing: 0.7px;
  }

  .gate-live-main {
    font-family: "Courier New", monospace;
    font-size: 1rem;
    font-weight: 800;
  }

  .gate-live-hint {
    font-size: 0.76rem;
    color: var(--text-muted);
    line-height: 1.45;
  }

  .persona-control-panel {
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .persona-heading {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
  }

  .persona-heading strong {
    font-size: 0.9rem;
  }

  .persona-heading small {
    color: var(--text-muted);
    font-size: 0.76rem;
  }

  .persona-chip-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 10px;
    width: 100%;
  }

  .persona-chip {
    padding: 10px 12px;
    min-height: 68px;
  }

  .persona-chip-label {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    font-size: 0.78rem;
    font-weight: 800;
  }

  .persona-chip-value {
    font-family: "Courier New", monospace;
    color: var(--primary);
  }

  .persona-meter {
    height: 5px;
    margin-top: 10px;
    border-radius: 999px;
    background: rgba(148, 163, 184, 0.16);
    overflow: hidden;
  }

  .persona-meter-fill {
    height: 100%;
    border-radius: inherit;
    background: linear-gradient(90deg, rgba(243, 167, 200, 0.42), #F3A7C8 78%, #f7c4dc);
  }

  /* Chat simulator styles */
  .simulator-panel {
    display: flex;
    flex-direction: column;
    height: calc(100vh - 140px);
    gap: 20px;
  }

  .terminal-box {
    background: #030508;
    border: 1px solid var(--card-border);
    border-radius: 14px;
    padding: 20px;
    flex-grow: 1;
    overflow-y: auto;
    font-family: 'Courier New', Courier, monospace;
    font-size: 0.85rem;
    color: #34d399;
    box-shadow: inset 0 4px 16px rgba(0, 0, 0, 0.8);
  }

  .terminal-line {
    margin-bottom: 8px;
    line-height: 1.5;
  }

  .terminal-info { color: #60a5fa; }
  .terminal-warn { color: #fbbf24; }
  .terminal-err { color: #f87171; }
  .terminal-user { color: #f472b6; }
  .terminal-system { color: #8e95a5; }

  .memory-pool-card {
    max-height: calc(100vh - 180px);
    min-height: 420px;
    display: flex;
    flex-direction: column;
  }

  .memory-pool-desc {
    font-size: 0.8rem;
    color: var(--text-muted);
    margin-bottom: 12px;
    line-height: 1.65;
    flex-shrink: 0;
  }

  .memory-sort-hint {
    font-size: 0.72rem;
    color: var(--primary);
    margin-bottom: 12px;
    font-weight: 800;
    letter-spacing: 0.2px;
    flex-shrink: 0;
  }

  .memory-list {
    min-height: 0;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding-right: 6px;
  }

  .memory-list::-webkit-scrollbar {
    width: 8px;
  }

  .memory-list::-webkit-scrollbar-track {
    background: rgba(148, 163, 184, 0.10);
    border-radius: 999px;
  }

  .memory-list::-webkit-scrollbar-thumb {
    background: rgba(243, 167, 200, 0.45);
    border-radius: 999px;
  }

  .memory-list::-webkit-scrollbar-thumb:hover {
    background: rgba(243, 167, 200, 0.72);
  }

  .memory-item {
    background: rgba(255, 255, 255, 0.035);
    border: 1px solid var(--card-border);
    border-radius: 12px;
    padding: 12px 14px;
  }

  [data-theme="light"] .memory-item {
    background: rgba(15, 23, 42, 0.035);
  }

  .memory-item-title {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 8px;
  }

  .memory-item-text {
    color: var(--text-primary);
    font-size: 0.86rem;
    line-height: 1.55;
  }

  .memory-item-meta {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 10px;
    color: var(--text-muted);
    font-size: 0.72rem;
  }

  .memory-meter {
    height: 5px;
    border-radius: 999px;
    background: rgba(148, 163, 184, 0.18);
    overflow: hidden;
    margin-top: 10px;
  }

  .memory-meter-fill {
    height: 100%;
    border-radius: inherit;
    background: linear-gradient(90deg, rgba(243, 167, 200, 0.42), #F3A7C8 78%, #f7c4dc);
  }

  .input-bar-container {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .input-bar {
    display: flex;
    gap: 14px;
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    padding: 14px;
    border-radius: 14px;
    box-shadow: 0 8px 30px var(--shadow);
  }

  .input-bar input {
    flex-grow: 1;
    background: var(--input-bg);
    border: 1px solid var(--card-border);
    border-radius: 8px;
    color: var(--text-primary);
    padding: 12px 18px;
    font-size: 0.95rem;
    outline: none;
    transition: all 0.2s;
  }

  .input-bar input:focus {
    border-color: var(--primary);
    box-shadow: 0 0 0 2px var(--primary-glow);
  }

  .quick-inputs {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    padding: 4px;
  }

  .quick-tag {
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid var(--card-border);
    padding: 6px 14px;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 600;
    cursor: pointer;
    color: var(--text-muted);
    transition: all 0.2s;
  }

  .quick-tag:hover {
    background: var(--primary-glow);
    color: var(--primary);
    border-color: rgba(59, 130, 246, 0.3);
    transform: translateY(-1px);
  }

  /* Fluid responsive layout utilities */
  @media (max-width: 992px) {
    body {
      flex-direction: column;
      overflow: auto;
    }
    .sidebar {
      width: 100%;
      height: auto;
      border-right: none;
      border-bottom: 1px solid var(--card-border);
    }
    .main-wrapper {
      height: auto;
      overflow: visible;
    }
    .spine-panel {
      flex-direction: column;
      height: auto;
    }
    .spine-steps {
      width: 100%;
      flex-direction: row;
      overflow-x: auto;
      padding-bottom: 10px;
    }
    .spine-step-card {
      min-width: 220px;
      flex-shrink: 0;
    }
    .spine-visualizer {
      height: 480px;
    }
    .gate-status-strip {
      grid-template-columns: repeat(2, minmax(120px, 1fr));
    }
    .gate-live-readout {
      grid-column: 1 / -1;
    }
    .simulator-panel {
      height: auto;
    }
    .terminal-box {
      height: 400px;
    }
  }

  @media (max-width: 640px) {
    .top-bar {
      height: auto;
      min-height: 88px;
      align-items: flex-start;
      flex-direction: column;
      gap: 12px;
      padding: 14px 18px;
    }
    .top-bar-status {
      width: 100%;
      flex-wrap: wrap;
      gap: 10px;
    }
    .status-wrapper,
    .session-select-shell {
      max-width: 100%;
    }
    .session-select-shell {
      width: 100%;
      justify-content: space-between;
    }
    .session-native-select {
      flex: 1;
      min-width: 0;
      max-width: none;
    }
    .card-title {
      align-items: flex-start;
      gap: 10px;
      flex-wrap: wrap;
    }
    .memory-pool-card {
      min-height: 360px;
      max-height: 70vh;
    }
  }
  </style>
</head>
<body>

  <!-- Left Sidebar Navigation -->
  <div class="sidebar">
    <div class="logo-area">
      <div class="logo-icon">
        <img src="logo.png" alt="Sylanne" onerror="this.remove(); this.parentElement.textContent='S';">
      </div>
      <div class="logo-title-group">
        <div class="logo-text">Sylanne Core</div>
        <div class="logo-subtext">Soulful Embodiment</div>
      </div>
    </div>

    <ul class="nav-links">
      <li class="nav-item active" data-target="monitor">
        <button>
          <svg viewBox="0 0 24 24"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-2 10H7v-2h10v2zm0-4H7V7h10v2zm0 8H7v-2h10v2z"/></svg>
          <span>系统状态监控</span>
        </button>
      </li>
      <li class="nav-item" data-target="spine">
        <button>
          <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 17h-2v-2h2v2zm2.07-7.75l-.9.92C13.45 12.9 13 13.5 13 15h-2v-.5c0-1.1.45-2.1 1.17-2.83l1.24-1.26c.37-.36.59-.86.59-1.41 0-1.1-.9-2-2-2s-2 .9-2 2H7c0-2.76 2.24-5 5-5s5 2.24 5 5c0 1.04-.42 1.99-1.07 2.75z"/></svg>
          <span>七层计算神经脊</span>
        </button>
      </li>
      <li class="nav-item" data-target="settings">
        <button>
          <svg viewBox="0 0 24 24"><path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/></svg>
          <span>参数配置面板</span>
        </button>
      </li>
      <li class="nav-item" data-target="simulator">
        <button>
          <svg viewBox="0 0 24 24"><path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm-9 12H5v-2h6v2zm4-4H5v-2h10v2zm4-4H5V6h14v2z"/></svg>
          <span>计算日志</span>
        </button>
      </li>
      <li class="nav-item" data-target="memory">
        <button>
          <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>
          <span>记忆池</span>
        </button>
      </li>
    </ul>

    <div class="sidebar-footer">
      <button class="theme-toggle-btn" id="theme-toggle" title="切换深浅主题">
        <span class="theme-toggle-stage" aria-hidden="true">
          <span class="theme-sky-wash"></span>
          <span class="theme-celestial">
            <span class="theme-ray"></span>
            <span class="theme-ray"></span>
            <span class="theme-ray"></span>
            <span class="theme-ray"></span>
            <span class="theme-ray"></span>
            <span class="theme-ray"></span>
            <span class="theme-ray"></span>
            <span class="theme-ray"></span>
            <span class="theme-core"></span>
          </span>
          <span class="theme-star"></span>
          <span class="theme-star"></span>
          <span class="theme-star"></span>
        </span>
      </button>
      <div style="font-size:0.75rem;font-weight:700;color:var(--text-muted);">Sylanne-embodiment</div>
    </div>
  </div>

  <!-- Main Wrapper -->
  <div class="main-wrapper">
    <div class="top-bar">
      <div class="top-bar-title">
        <h2 id="top-title">系统状态监控</h2>
      </div>
      <div class="top-bar-status">
        <div class="status-wrapper">
          <span class="status-dot" id="server-status-dot"></span>
          <span id="server-status-text">正在连接真实后端...</span>
        </div>
        <div class="session-select-shell">
          <span class="session-label">会话选择:</span>
          <select id="session-selector" class="session-native-select" aria-label="会话选择">
            <option value="default">总览</option>
          </select>
          <div class="session-picker" id="session-picker">
            <button type="button" class="session-picker-button" id="session-picker-button" aria-haspopup="listbox" aria-expanded="false">总览</button>
            <div class="session-picker-menu" id="session-picker-menu" role="listbox" aria-label="会话选择"></div>
          </div>
        </div>
      </div>
    </div>

    <div class="content-pane">

      <!-- TAB 1: Monitor -->
      <div class="tab-pane active" id="pane-monitor">
        <div class="card-grid">

          <!-- Emotion States -->
          <div class="glass-card" style="grid-column: span 2;">
            <div class="card-title">
              <span>八项表象状态</span>
              <span class="badge badge-blue">实时体征</span>
            </div>
            <div id="emo-container">
              <!-- Dynamic emo bars -->
            </div>
          </div>

          <!-- Route and Surprise -->
          <div class="glass-card">
            <div class="card-title">
              <span>计算路由分配统计 (Predictive Coding)</span>
              <span class="badge badge-amber">Gate Routing</span>
            </div>
            <div class="route-pie-wrapper">
              <div class="route-pie" id="route-pie-chart"></div>
              <div class="route-legend" id="route-legend">
                <!-- legend items -->
              </div>
            </div>
          </div>

          <!-- Autopoietic Boundary -->
          <div class="glass-card">
            <div class="card-title">
              <span>自创生身份边界 (L6 Autopoiesis)</span>
              <span class="badge badge-green">L6 Core</span>
            </div>
            <div class="stats-list">
              <div class="stats-row">
                <span class="stats-label">边界完整性 (Integrity)</span>
                <span class="stats-value" id="monitor-boundary-integrity" style="color:var(--green)">1.000</span>
              </div>
              <div class="stats-row">
                <span class="stats-label">内部系统熵 (Entropy)</span>
                <span class="stats-value" id="monitor-boundary-entropy">0.245</span>
              </div>
              <div class="stats-row">
                <span class="stats-label">身份轴心倾角 (Core Rotation)</span>
                <span class="stats-value" id="monitor-boundary-rotation">0.00°</span>
              </div>
              <div class="stats-row">
                <span class="stats-label">边界自愈率 (Self-Repair)</span>
                <span class="stats-value">0.05 / tick</span>
              </div>
            </div>
          </div>

          <!-- Expression stats -->
          <div class="glass-card">
            <div class="card-title">
              <span>表达相变与表达欲望 (L7 Expression)</span>
              <span class="badge badge-purple">L7 Phase</span>
            </div>
            <div class="stats-list">
              <div class="stats-row">
                <span class="stats-label">相变表达阈值</span>
                <span class="stats-value" id="monitor-express-threshold">0.600</span>
              </div>
              <div class="stats-row">
                <span class="stats-label">当前表达积累驱动</span>
                <span class="stats-value" id="monitor-express-drive" style="color:var(--purple)">0.210</span>
              </div>
              <div class="stats-row">
                <span class="stats-label">上一次表达模态</span>
                <span class="stats-value"><span class="badge badge-blue" id="monitor-express-mode">NORMAL</span></span>
              </div>
              <div class="stats-row">
                <span class="stats-label">沉默衰减阈值加速</span>
                <span class="stats-value">已启用</span>
              </div>
            </div>
          </div>

          <!-- Performance and Timing -->
          <div class="glass-card" style="grid-column: span 2;">
            <div class="card-title">
              <span>神经计算管道延迟 (Timing stats)</span>
              <span class="badge badge-purple">Performance</span>
            </div>
            <table style="width:100%; border-collapse:collapse; text-align:left; font-size:0.9rem;">
              <thead>
                <tr style="border-bottom:1px solid var(--card-border); color:var(--text-muted)">
                  <th style="padding:12px 0">计算层级 (Layer)</th>
                  <th>平均耗时 (p50)</th>
                  <th>最差耗时 (p99)</th>
                  <th>耗时占比</th>
                </tr>
              </thead>
              <tbody id="timing-rows">
                <!-- Timing rows dynamically generated -->
              </tbody>
            </table>
          </div>

        </div>
      </div>

      <!-- TAB 2: Spine -->
      <div class="tab-pane" id="pane-spine">
        <div class="spine-panel">

          <!-- Left Spine Layers List -->
          <div class="spine-steps">
            <div class="spine-step-card active" data-step="1" style="--layer-color: var(--l1-color);">
              <div class="spine-step-num">Layer 1</div>
              <div class="spine-step-title">HDC 感知编码</div>
              <div class="spine-step-desc">把输入转成 HDC 向量，用于快速相似检索。</div>
            </div>

            <div class="spine-step-card" data-step="2" style="--layer-color: var(--l2-color);">
              <div class="spine-step-num">Layer 2</div>
              <div class="spine-step-title">预测编码门控</div>
              <div class="spine-step-desc">读取惊讶度采样，决定 Fast / Normal / Full。</div>
            </div>

            <div class="spine-step-card" data-step="3" style="--layer-color: var(--l3-color);">
              <div class="spine-step-num">Layer 3</div>
              <div class="spine-step-title">Void-Scar 伤痕引擎</div>
              <div class="spine-step-desc">记录缺席、伤痕与修复压力的变化。</div>
            </div>

            <div class="spine-step-card" data-step="4" style="--layer-color: var(--l4-color);">
              <div class="spine-step-num">Layer 4</div>
              <div class="spine-step-title">关系分次剪切</div>
              <div class="spine-step-desc">整理关系信号，标出冲突与连接强度。</div>
            </div>

            <div class="spine-step-card" data-step="5" style="--layer-color: var(--l5-color);">
              <div class="spine-step-num">Layer 5</div>
              <div class="spine-step-title">异构图 Transformer</div>
              <div class="spine-step-desc">整合人格、关系、记忆等符号节点。</div>
            </div>

            <div class="spine-step-card" data-step="6" style="--layer-color: var(--l6-color);">
              <div class="spine-step-num">Layer 6</div>
              <div class="spine-step-title">自创生身份边界</div>
              <div class="spine-step-desc">显示身份边界的稳定、吸收与抵抗。</div>
            </div>

            <div class="spine-step-card" data-step="7" style="--layer-color: var(--l7-color);">
              <div class="spine-step-num">Layer 7</div>
              <div class="spine-step-title">表达相变跳变</div>
              <div class="spine-step-desc">根据表达压力选择沉默、提示或主动表达。</div>
            </div>
          </div>

          <!-- Right Focused Visualizer Pane -->
          <div class="spine-visualizer">
            <div class="visualizer-header">
              <div class="visualizer-title">
                <h3 id="vis-title">HDC 感知层超空间投影</h3>
                <p id="vis-desc">2048-bit 二进制超向量分布，感知叠加状态演变</p>
              </div>
              <span class="badge" id="vis-badge" style="background: rgba(34, 211, 238, 0.15); color: var(--l1-color); border: 1px solid var(--l1-color);">PERCEPTION</span>
            </div>

            <div class="visualizer-canvas-container">
              <canvas id="vis-canvas" class="canvas-element"></canvas>
            </div>

            <div class="visualizer-controls" id="vis-controls-panel">
              <button class="btn btn-secondary" id="vis-action-btn">激活动画</button>
              <span style="font-size:0.8rem; color:var(--text-muted)" id="vis-status">运行流畅: 60 FPS</span>
            </div>
          </div>

        </div>
      </div>

      <!-- TAB 3: Settings -->
      <div class="tab-pane" id="pane-settings">
        <div class="glass-card" style="max-width: 900px; margin: 0 auto;">
          <div class="card-title">
            <span>Sylanne-Embodiment 插件系统配置</span>
            <button class="btn btn-primary" id="save-settings-btn">保存全部修改</button>
          </div>

          <div id="settings-container">
            <!-- settings groups dynamically loaded -->
          </div>
        </div>
      </div>

      <!-- TAB 4: Computation Logs -->
      <div class="tab-pane" id="pane-simulator">
        <div class="simulator-panel">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
            <div>
              <h3 style="font-size:1.1rem; font-weight:700;">实时计算日志</h3>
              <p style="font-size:0.8rem; color:var(--text-muted); margin-top:4px;">每条消息经过 7 层计算栈的完整过程记录</p>
            </div>
            <div style="display:flex; gap:10px; align-items:center;">
              <label class="switch"><input type="checkbox" id="log-auto-scroll" checked><span class="slider"></span></label>
              <span style="font-size:0.8rem; color:var(--text-muted);">自动滚动</span>
              <button class="btn btn-secondary" id="log-clear-btn" style="padding:8px 16px;">清空</button>
            </div>
          </div>
          <div class="terminal-box" id="term-box" style="font-size:0.82rem;">
            <div class="terminal-line terminal-info">[System] 等待插件计算日志...</div>
            <div class="terminal-line terminal-system">[System] 连接到 /api/computation_logs 端点后将实时展示每条消息的 7 层计算过程。</div>
            <div class="terminal-line terminal-system">[System] file:// 预览才会展示本地示例；生产页面不会用示例数据冒充真实日志。</div>
          </div>

          <div style="display:flex; gap:12px; margin-top:16px; flex-wrap:wrap;">
            <div class="glass-card" style="flex:1; min-width:200px; padding:16px;">
              <div style="font-size:0.75rem; color:var(--text-muted); text-transform:uppercase; letter-spacing:1px; margin-bottom:8px;">最近路由分布</div>
              <div style="display:flex; gap:12px; align-items:center;">
                <span class="badge badge-green" id="log-route-fast">Fast: 0</span>
                <span class="badge badge-blue" id="log-route-normal">Normal: 0</span>
                <span class="badge badge-purple" id="log-route-full">Full: 0</span>
              </div>
            </div>
            <div class="glass-card" style="flex:1; min-width:200px; padding:16px;">
              <div style="font-size:0.75rem; color:var(--text-muted); text-transform:uppercase; letter-spacing:1px; margin-bottom:8px;">平均计算耗时</div>
              <div style="font-size:1.4rem; font-weight:800; color:var(--primary);" id="log-avg-time">--ms</div>
            </div>
            <div class="glass-card" style="flex:1; min-width:200px; padding:16px;">
              <div style="font-size:0.75rem; color:var(--text-muted); text-transform:uppercase; letter-spacing:1px; margin-bottom:8px;">日志条目</div>
              <div style="font-size:1.4rem; font-weight:800;" id="log-entry-count">0</div>
            </div>
          </div>
        </div>
      </div>

      <!-- TAB 5: Memory Pools -->
      <div class="tab-pane" id="pane-memory">
        <div class="card-grid" style="grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));">

          <!-- L1 Hot Memory Pool -->
          <div class="glass-card memory-pool-card">
            <div class="card-title">
              <span>L1 Hot Pool 工作记忆</span>
              <span class="badge badge-amber">deque / 50</span>
            </div>
            <div class="memory-pool-desc">
              最近消息驻留层，负责即时上下文与刚发生的对话片段；满 50 条后带 embedding 的条目下沉到 L2。
            </div>
            <div class="memory-sort-hint">按印象深度从高到低排序</div>
            <div id="memory-hot-list" class="memory-list">
              <!-- Dynamic memory items -->
            </div>
          </div>

          <!-- L2 Warm Memory Pool -->
          <div class="glass-card memory-pool-card">
            <div class="card-title">
              <span>L2 Warm Pool 召回记忆</span>
              <span class="badge badge-blue">vector recall</span>
            </div>
            <div class="memory-pool-desc">
              从 L1 下沉的可召回记忆，按权重、相似度、情绪温度参与检索，并持续衰减与再巩固。
            </div>
            <div class="memory-sort-hint">按印象深度从高到低排序</div>
            <div id="memory-warm-list" class="memory-list">
              <!-- Dynamic memory items -->
            </div>
          </div>

          <!-- L3 Cold Graph Memory -->
          <div class="glass-card memory-pool-card">
            <div class="card-title">
              <span>L3 Cold Graph 结构记忆</span>
              <span class="badge badge-purple">entity graph</span>
            </div>
            <div class="memory-pool-desc">
              由压缩后的实体、关系和边界事实组成，使用 clarity 衰减；适合展示长期关系图节点。
            </div>
            <div class="memory-sort-hint">按印象深度从高到低排序</div>
            <div id="memory-cold-list" class="memory-list">
              <!-- Dynamic memory items -->
            </div>
          </div>

        </div>

        <!-- Memory Stats -->
        <div class="card-grid" style="margin-top:20px;">
          <div class="glass-card" style="padding:16px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <div>
                <div style="font-size:0.75rem; color:var(--text-muted); text-transform:uppercase; letter-spacing:1px;">总记忆条目</div>
                <div style="font-size:1.6rem; font-weight:800; margin-top:4px;" id="mem-total-count">0</div>
              </div>
              <div>
                <div style="font-size:0.75rem; color:var(--text-muted); text-transform:uppercase; letter-spacing:1px;">有 Embedding 的</div>
                <div style="font-size:1.6rem; font-weight:800; margin-top:4px; color:var(--green);" id="mem-embed-count">0</div>
              </div>
              <div>
                <div style="font-size:0.75rem; color:var(--text-muted); text-transform:uppercase; letter-spacing:1px;">平均权重</div>
                <div style="font-size:1.6rem; font-weight:800; margin-top:4px; color:var(--blue);" id="mem-avg-weight">0.00</div>
              </div>
              <div>
                <div style="font-size:0.75rem; color:var(--text-muted); text-transform:uppercase; letter-spacing:1px;">平均温度</div>
                <div style="font-size:1.6rem; font-weight:800; margin-top:4px; color:var(--amber);" id="mem-avg-temp">0.50</div>
              </div>
            </div>
          </div>
        </div>
      </div>

    </div>
  </div>

  <script src="/api/plugin/page/bridge-sdk.js"></script>
  <script>
  const FALLBACK_CONFIG_SCHEMA = {
    "sylanne_alpha_root": {
      "description": "Sylanne 4.0 alpha body 状态目录",
      "type": "string",
      "default": ".sylanne_alpha_state",
      "hint": "每个会话会保存为独立的 .alpha.json；覆盖安装前请备份旧 Sylanne 数据，再通过 4.0 导入入口迁入。"
    },
    "sylanne_alpha_realtime_chat_enabled": {
      "description": "启用 Sylanne 4.0 即时聊天调度",
      "type": "bool",
      "default": false,
      "hint": "默认关闭；开启后仍受用户主权、风险、冷却和预算边界限制。"
    },
    "sylanne_alpha_stream_first_sentence_enabled": {
      "description": "启用首句抢发（流式）",
      "type": "bool",
      "default": false,
      "hint": "默认关闭。开启后在 LLM 流式生成过程中检测到第一个完整句子就提前发给用户，降低感知延迟。需要 LLM Provider 开启流式输出。"
    },
    "sylanne_alpha_realtime_intercept_llm_response": {
      "description": "允许即时聊天接管 LLM 响应分段",
      "type": "bool",
      "default": false,
      "hint": "默认关闭；用于 4.0 对话分段和打断识别，不恢复旧 realtime engine。"
    },
    "sylanne_alpha_proactive_dispatch_enabled": {
      "description": "启用 Sylanne 4.0 主动发起派发",
      "type": "bool",
      "default": false,
      "hint": "默认关闭；开启后 guard 不允许时仍不会派发。"
    },
    "sylanne_alpha_proactive_scheduler_enabled": {
      "description": "启用主动检查后台调度",
      "type": "bool",
      "default": false,
      "hint": "默认关闭；用于低频检查，不执行高频循环。"
    },
    "sylanne_alpha_embedding_memory_enabled": {
      "description": "启用 embedding 记忆辅助召回",
      "type": "bool",
      "default": false,
      "hint": "默认关闭；开启后需要配置 embedding provider。"
    },
    "sylanne_alpha_embedding_memory_provider_id": {
      "description": "Embedding 记忆使用的 Provider ID",
      "type": "string",
      "default": "",
      "hint": "填写 AstrBot 中配置的 embedding provider ID；留空则不启用向量召回。"
    },
    "sylanne_alpha_embedding_memory_top_k": {
      "description": "Embedding 召回 top-K 条数",
      "type": "int",
      "default": 3,
      "hint": "每次召回最多返回的相似记忆条数。"
    },
    "sylanne_alpha_assessor_llm_enabled": {
      "description": "启用独立判断 LLM 通道",
      "type": "bool",
      "default": false,
      "hint": "默认关闭；开启后情绪估计使用独立 provider，不占用主聊天模型。"
    },
    "sylanne_alpha_assessor_provider_id": {
      "description": "深度判断 LLM Provider（后台异步）",
      "type": "string",
      "default": "",
      "_special": "select_provider",
      "hint": "后台深度语义分析，结果喂给长期状态引擎。不阻塞回复，可用强模型。推荐设置：温度 0，top-p 0.1。"
    },
    "sylanne_alpha_fast_assessor_enabled": {
      "description": "启用即时判断 LLM",
      "type": "bool",
      "default": true,
      "hint": "默认开启；前台同步等待（2s），即时情绪直接注入当前轮回复。"
    },
    "sylanne_alpha_fast_assessor_provider_id": {
      "description": "即时判断 LLM Provider（前台同步）",
      "type": "string",
      "default": "",
      "_special": "select_provider",
      "hint": "前台同步等待 2s，需要响应快的小模型。即时情绪直接影响当前轮回复语气。推荐设置：温度 0，top-p 0.1，Max Tokens 无需设置（插件已接管）。"
    },
    "sylanne_alpha_background_workers_enabled": {
      "description": "启用后台工作队列",
      "type": "bool",
      "default": true,
      "hint": "默认开启；用于异步持久化和后台任务。"
    },
    "sylanne_alpha_background_max_workers": {
      "description": "后台最大并发工作数",
      "type": "int",
      "default": 2,
      "hint": "1c1g 环境建议保持 1-2。"
    },
    "sylanne_alpha_life_simulation_enabled": {
      "description": "启用 Sylanne 生活模拟",
      "type": "bool",
      "default": false,
      "hint": "默认关闭；开启后 Sylanne 会用外部 LLM 模拟自己的生活，某些时刻会因为她那边发生的事主动找用户。"
    },
    "sylanne_alpha_life_simulation_provider_id": {
      "description": "生活模拟 LLM Provider",
      "type": "string",
      "default": "",
      "_special": "select_provider",
      "hint": "用于模拟 Sylanne 生活的 LLM；建议用便宜的小模型。"
    },
    "sylanne_alpha_life_simulation_interval_seconds": {
      "description": "生活模拟间隔（秒）",
      "type": "float",
      "default": 1800,
      "hint": "每隔多久模拟一次 Sylanne 的生活状态。默认 30 分钟。"
    },
    "sylanne_alpha_life_simulation_outreach_cooldown_seconds": {
      "description": "生活模拟主动找用户冷却（秒）",
      "type": "float",
      "default": 3600,
      "hint": "因为生活事件主动找用户的最短间隔。默认 1 小时。"
    }
  };

  let runtimeConfigSchema = FALLBACK_CONFIG_SCHEMA;
  let runtimeConfigValues = Object.fromEntries(
    Object.entries(FALLBACK_CONFIG_SCHEMA).map(([key, meta]) => [key, meta.default])
  );
  let runtimeProviders = [];
  let hasLiveState = false;
  document.documentElement.classList.add('enhanced-session-picker');
  const WEBUI_STATE_CONTRACT = Object.freeze({
    schema_version: "sylanne.webui.state.v1",
    required: ["current_session", "emotion", "gate", "route_stats", "boundary", "expression", "timing", "spine", "persona", "theme"],
    timing_unit: "ms",
    theme_base: "#F3A7C8"
  });

  const IS_FILE_PREVIEW = window.location.protocol === "file:";

  function createEmptySysState() {
    return {
      emotion: {},
      route_stats: { fast: 0, normal: 0, full: 0, skip: 0 },
      gate: { mean_surprise: 0, surprise_history: [], history: [] },
      spine: { route: "", surprise: 0, last_text: "" },
      layers: {},
      persona: {
        profile: { name: "Sylanne", version: "4.0" },
        traits: {},
        voice: {},
        drift: {}
      },
      theme: { base: "#F3A7C8", mode: "soft" },
      boundary: { integrity: 0, entropy: 0, stability: 0, rotation: 0, history: [] },
      expression: { threshold: 0, pressure: 0, ratio: 0, mode: "", count: 0 },
      timing: {},
      scars: [],
      voids: [],
      sheaf_nodes: [],
      sheaf_edges: [],
      hgt_attention: Array.from({length: 7}, () => Array.from({length: 7}, () => 0))
    };
  }

  function createPreviewSysState() {
    return {
    emotion: {
      warmth: 0.65,
      arousal: 0.38,
      valence: 0.52,
      tension: 0.18,
      curiosity: 0.72,
      repair_pressure: 0.05,
      expression_drive: 0.21,
      boundary_firmness: 0.85
    },
    route_stats: {
      fast: 142,
      normal: 38,
      full: 12,
      skip: 4
    },
    gate: {
      mean_surprise: 0.165,
      surprise_history: [
        0.06, 0.07, 0.08, 0.07, 0.09, 0.10, 0.08, 0.11,
        0.34, 0.22, 0.14, 0.10, 0.08, 0.09, 0.12, 0.10,
        0.07, 0.08, 0.09, 0.11, 0.48, 0.30, 0.18, 0.12,
        0.09, 0.08, 0.10, 0.13, 0.16, 0.12, 0.09, 0.08,
        0.07, 0.09, 0.10, 0.26, 0.19, 0.13, 0.10, 0.09
      ]
    },
    spine: {
      route: "fast",
      surprise: 0.165
    },
    layers: {},
    persona: {
      profile: { name: "Sylanne", version: "4.0" },
      traits: {
        warmth_bias: 0.62,
        edge: 0.44,
        curiosity: 0.68,
        patience: 0.58,
        intimacy_gravity: 0.52,
        sovereignty_guard: 0.72
      },
      voice: { cadence: "slow_burn", boundary: "strong" },
      drift: { mode: "slow_plasticity", events: 0, plasticity: 0.0 }
    },
    theme: {
      base: "#F3A7C8",
      mode: "soft"
    },
    boundary: {
      integrity: 0.98,
      entropy: 0.245,
      stability: 0.92,
      rotation: 0.0,
      history: Array.from({length: 30}, () => 0.95 + Math.random() * 0.05)
    },
    expression: {
      threshold: 0.60,
      pressure: 0.126,
      ratio: 0.21,
      mode: "hint",
      count: 24
    },
    timing: {
      perception: { p50_ns: 120000, p99_ns: 250000 },
      gate: { p50_ns: 24000, p99_ns: 85000 },
      ssm: { p50_ns: 850000, p99_ns: 3200000 },
      memory: { p50_ns: 2100000, p99_ns: 8600000 },
      boundary: { p50_ns: 95000, p99_ns: 340000 },
      expression: { p50_ns: 12000, p99_ns: 45000 }
    },
    scars: [
      { id: 1, type: "avoidance", weight: 0.45, dimension: "warmth", healing: "scarred" },
      { id: 2, type: "shock", weight: 0.75, dimension: "tension", healing: "closing" }
    ],
    voids: [
      { id: 1, concept: "silent_absence", pressure: 0.38, depth: 0.52, age: 14 },
      { id: 2, concept: "self_doubt", pressure: 0.12, depth: 0.22, age: 3 }
    ],
    sheaf_nodes: [
      { id: "A", rel: "user", val: 0.62 },
      { id: "B", rel: "self", val: 0.78 },
      { id: "C", rel: "environment", val: 0.45 }
    ],
    sheaf_edges: [
      { from: "A", to: "B", weight: 0.8 },
      { from: "B", to: "C", weight: 0.5 }
    ],
      hgt_attention: Array.from({length: 7}, () => Array.from({length: 7}, () => Math.random()))
    };
  }

  // Local Spine calculations state representation. Production starts empty and waits for real API state.
  let sysState = IS_FILE_PREVIEW ? createPreviewSysState() : createEmptySysState();

  // Local simulator calculations
  class LocalSimulator {
    static generateSurprise(text) {
      if (text.includes("说话") || text.includes("沉默")) return 0.58;
      if (text.includes("难过") || text.includes("痛苦") || text.includes("伤心")) return 0.72;
      if (text.includes("懦弱") || text.includes("投射") || text.includes("尊严")) return 0.86;
      return 0.1 + Math.random() * 0.25;
    }

    static runStep(text) {
      const surprise = this.generateSurprise(text);

      // L2 Gate Routing
      let route = "fast";
      if (surprise > 0.45) route = "full";
      else if (surprise > 0.18) route = "normal";

      sysState.route_stats[route]++;
      sysState.gate.mean_surprise = sysState.gate.mean_surprise * 0.9 + surprise * 0.1;
      sysState.gate.surprise_history.push(surprise);
      if (sysState.gate.surprise_history.length > 30) sysState.gate.surprise_history.shift();

      // L3 Void-Scar dynamics and L6 Boundary perturbation
      if (route === "full") {
        sysState.emotion.tension = Math.min(1.0, sysState.emotion.tension + surprise * 0.55);
        sysState.emotion.arousal = Math.min(1.0, sysState.emotion.arousal + surprise * 0.45);
        sysState.emotion.valence = Math.max(-1.0, sysState.emotion.valence - surprise * 0.65);
        sysState.emotion.repair_pressure = Math.min(1.0, sysState.emotion.repair_pressure + 0.25);

        const boundaryPerturbation = surprise * 0.9;
        if (boundaryPerturbation > 0.7) {
          // Deep penetration and rotation
          sysState.boundary.integrity = Math.max(0.3, sysState.boundary.integrity - boundaryPerturbation * 0.45);
          sysState.boundary.rotation = Math.min(6.0, 2.0 + Math.random() * 4.0);
          sysState.boundary.entropy = Math.min(1.0, sysState.boundary.entropy + 0.35);

          // Trigger particle hits on L6 Boundary visualizer if selected
          if (activeSpineStep === 6 && typeof triggerL6Perturbation === 'function') {
            triggerL6Perturbation(boundaryPerturbation, true);
          }
        } else if (boundaryPerturbation > 0.35) {
          // Resistance
          sysState.boundary.integrity = Math.max(0.6, sysState.boundary.integrity - boundaryPerturbation * 0.2);
          sysState.boundary.rotation = Math.min(2.0, Math.random() * 2.0);
          if (activeSpineStep === 6 && typeof triggerL6Perturbation === 'function') {
            triggerL6Perturbation(boundaryPerturbation, false);
          }
        }
      } else {
        // Fast/Normal pathway
        sysState.emotion.tension = Math.max(0.05, sysState.emotion.tension * 0.82);
        sysState.emotion.arousal = sysState.emotion.arousal * 0.88 + Math.random() * 0.12;
        sysState.emotion.valence = Math.min(1.0, sysState.emotion.valence * 0.9 + 0.1);

        // Heal boundary
        sysState.boundary.integrity = Math.min(1.0, sysState.boundary.integrity + 0.05);
        sysState.boundary.rotation = Math.max(0.0, sysState.boundary.rotation - 0.6);
        sysState.boundary.entropy = Math.max(0.1, sysState.boundary.entropy - 0.03);
      }

      // Add Void or Scar nodes based on text
      if (text.includes("说话") || text.includes("沉默")) {
        sysState.voids.push({
          id: Date.now(),
          concept: "unspoken_abyss_" + Math.floor(Math.random() * 100),
          pressure: 0.6 + Math.random() * 0.3,
          depth: 0.5 + Math.random() * 0.4,
          age: 1
        });
        if (sysState.voids.length > 5) sysState.voids.shift();
      }

      if (text.includes("难过") || text.includes("痛苦") || text.includes("伤口")) {
        sysState.scars.push({
          id: Date.now(),
          type: "rupture",
          weight: 0.55 + Math.random() * 0.35,
          dimension: "tension",
          healing: "raw"
        });
        if (sysState.scars.length > 5) sysState.scars.shift();
      }

      // Accumulate L7 expression drive
      const baseDrive = 0.12 + sysState.emotion.tension * 0.5 + sysState.emotion.repair_pressure * 0.35;
      sysState.emotion.expression_drive = Math.min(1.0, sysState.emotion.expression_drive + baseDrive);

      sysState.expression.pressure = sysState.emotion.expression_drive;
      sysState.expression.ratio = sysState.expression.pressure / sysState.expression.threshold;

      let exprTriggered = false;
      let exprMode = "silent";
      if (sysState.expression.ratio >= 1.0) {
        exprTriggered = true;
        sysState.expression.count++;
        if (sysState.expression.pressure > 0.95) {
          exprMode = "urgent";
        } else if (sysState.expression.pressure > 0.7) {
          exprMode = "normal";
        } else {
          exprMode = "hint";
        }
        sysState.expression.mode = exprMode;
        sysState.emotion.expression_drive = 0.05; // Reset to minimal base
      }

      // Slightly vary timing stats
      sysState.timing.perception.p50_ns = Math.floor(110000 + Math.random() * 30000);
      sysState.timing.gate.p50_ns = Math.floor(22000 + Math.random() * 6000);
      sysState.timing.ssm.p50_ns = Math.floor(820000 + Math.random() * 150000);

      // Morph HGT attention mapping
      sysState.hgt_attention = Array.from({length: 7}, () => Array.from({length: 7}, () => Math.random()));

      return {
        surprise,
        route,
        exprTriggered,
        exprMode
      };
    }
  }

  // Global UI state
  let activeTab = "monitor";
  let activeSpineStep = 1;
  let animationFrameId = null;

  // Unified API transport:
  // - AstrBot plugin pages use window.AstrBotPluginPage bridge.
  // - Standalone WebUI and /webui fallback use ordinary fetch.
  const PLUGIN_NAME = "astrbot_plugin_sylanne";
  let pluginBridge = null;
  let pluginBridgeReady = null;
  let lastTransportMode = window.location.protocol === "file:" ? "preview" : "http";

  function setConnectionStatus(mode, text) {
    const dot = document.getElementById('server-status-dot');
    const label = document.getElementById('server-status-text');
    if (!dot || !label) return;
    const classes = ["status-dot"];
    if (mode && mode !== "live") classes.push(mode);
    dot.className = classes.join(" ");
    label.textContent = text;
  }

  function apiPath(path) {
    const pathname = window.location.pathname.replace(/\/+$/, '');
    const plugMatch = pathname.match(/^\/api\/plug\/([^/]+)\/(?:webui|dashboard)$/);
    if (plugMatch) return `/api/plug/${plugMatch[1]}${path}`;
    if (pathname.startsWith('/api/plugin/page/')) return `/api/plug/${PLUGIN_NAME}${path}`;
    const pageMatch = pathname.match(/^(\/[^/]+)\/pages\//);
    if (pageMatch) return `/api/plug/${pageMatch[1].replace(/^\/+/, '')}${path}`;
    const routeMatch = pathname.match(/^(\/[^/]+)\/(?:webui|dashboard)$/);
    const base = routeMatch ? `/api/plug/${routeMatch[1].replace(/^\/+/, '')}` : '';
    return `${base}${path}`;
  }

  function splitApiPath(path) {
    const [rawEndpoint, rawQuery = ""] = String(path || "").split("?");
    const endpoint = rawEndpoint.replace(/^\/+/, "");
    const params = {};
    new URLSearchParams(rawQuery).forEach((value, key) => { params[key] = value; });
    return { endpoint, params };
  }

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  function withTimeout(promise, ms) {
    return Promise.race([
      promise,
      new Promise(resolve => setTimeout(() => resolve(null), ms))
    ]);
  }

  async function waitForPluginBridge(timeoutMs = 1500) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const bridge = window.AstrBotPluginPage;
      if (bridge && typeof bridge.apiGet === "function" && typeof bridge.apiPost === "function") {
        return bridge;
      }
      await sleep(50);
    }
    return null;
  }

  async function getPluginBridge() {
    const bridge = pluginBridge || await waitForPluginBridge();
    if (!bridge) return null;
    if (pluginBridge !== bridge) {
      pluginBridge = bridge;
      pluginBridgeReady = null;
    }
    if (typeof pluginBridge.ready === "function") {
      pluginBridgeReady = pluginBridgeReady || withTimeout(pluginBridge.ready().catch(() => null), 1500);
      const context = await pluginBridgeReady;
      if (!context) return null;
    }
    return pluginBridge;
  }

  async function apiFetch(path, options = {}) {
    const bridge = await getPluginBridge();
    if (bridge && typeof bridge.apiGet === "function" && typeof bridge.apiPost === "function") {
      const { endpoint, params } = splitApiPath(path);
      try {
        const method = String(options.method || "GET").toUpperCase();
        const payload = options.body ? JSON.parse(options.body) : {};
        const data = method === "POST"
          ? await bridge.apiPost(endpoint, payload)
          : await bridge.apiGet(endpoint, params);
        lastTransportMode = "bridge";
        return { ok: true, status: 200, json: async () => data };
      } catch (error) {
        console.warn("Sylanne WebUI bridge request failed:", endpoint, error);
        return { ok: false, status: 0, json: async () => ({ error: String(error) }) };
      }
    }
    lastTransportMode = window.location.protocol === "file:" ? "preview" : "http";
    return fetch(apiPath(path), options);
  }

  function resolveAssetPath(path) {
    if (window.location.protocol === "file:") return path.replace(/^\/+/, "");
    return apiPath(path);
  }

  // DOM elements wireup
  const navItems = document.querySelectorAll('.nav-item');
  const tabPanes = document.querySelectorAll('.tab-pane');
  const themeToggle = document.getElementById('theme-toggle');
  const topTitle = document.getElementById('top-title');
  const contentPane = document.querySelector('.content-pane');
  const logoImg = document.querySelector('.logo-icon img');
  if (logoImg) logoImg.src = resolveAssetPath('/logo.png');
  if (window.location.protocol === "file:") {
    setConnectionStatus("preview", "本地预览 (等待后端)");
  }

  // Tab switching
  navItems.forEach(item => {
    item.addEventListener('click', () => {
      navItems.forEach(i => i.classList.remove('active'));
      tabPanes.forEach(p => p.classList.remove('active'));

      item.classList.add('active');
      const target = item.dataset.target;
      document.getElementById('pane-' + target).classList.add('active');
      activeTab = target;
      if (contentPane) {
        contentPane.classList.remove('is-switching');
        void contentPane.offsetWidth;
        contentPane.classList.add('is-switching');
      }

      const titles = {
        monitor: "系统状态监控",
        spine: "七层计算神经脊演化",
        settings: "参数配置面板",
        simulator: "实时计算日志",
        memory: "记忆池观测"
      };
      topTitle.textContent = titles[target] || "Sylanne Core";

      if (target === "spine") {
        initSpineCanvas();
      } else {
        cancelAnimationFrame(animationFrameId);
      }
    });
  });

  // Dark/Light theme toggle
  themeToggle.addEventListener('click', () => {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    themeToggle.classList.remove('switching', 'to-light', 'to-dark');
    void themeToggle.offsetWidth;
    themeToggle.classList.add('switching', newTheme === 'light' ? 'to-light' : 'to-dark');
    document.documentElement.setAttribute('data-theme', newTheme);
    setTimeout(() => themeToggle.classList.remove('switching', 'to-light', 'to-dark'), 900);

    if (activeTab === "spine") {
      initSpineCanvas();
    }
  });

  function buildEmotionDisplayMetrics(emotion = {}) {
    const getNumber = (key) => {
      const value = Number(emotion?.[key]);
      return Number.isFinite(value) ? value : null;
    };
    const firstNumber = (...values) => {
      for (const value of values) {
        const number = Number(value);
        if (Number.isFinite(number)) return number;
      }
      return null;
    };
    const clamp01Value = (value) => Math.max(0, Math.min(1, Number(value) || 0));
    const valencePercent = (value) => {
      const number = Number(value);
      if (!Number.isFinite(number)) return 0.5;
      return number < 0 ? (number + 1) / 2 : number;
    };
    const surfaceMetrics = [
      { key: "arousal", label: "活跃度", color: "var(--amber)" },
      { key: "valence", label: "正负价", color: "var(--blue)", percent: valencePercent },
      { key: "tension", label: "紧张度", color: "var(--red)" },
      { key: "curiosity", label: "好奇度", color: "var(--primary)" },
      { key: "repair_pressure", label: "自愈压力", color: "var(--purple)" },
      {
        key: "expression_drive",
        label: "表达驱动",
        color: "var(--l7-color)",
        value: () => firstNumber(getNumber("expression_drive"), sysState.expression?.pressure)
      },
      {
        key: "boundary_firmness",
        label: "身份边界",
        color: "var(--l6-color)",
        value: () => firstNumber(getNumber("boundary_firmness"), sysState.boundary?.integrity, sysState.boundary?.stability)
      },
      { key: "coherence", label: "内部和平度", color: "var(--green)" }
    ];
    const metrics = surfaceMetrics
      .map((metric) => {
        const value = typeof metric.value === "function" ? metric.value() : getNumber(metric.key);
        if (value === null || value === undefined || !Number.isFinite(Number(value))) return null;
        const percentValue = typeof metric.percent === "function" ? metric.percent(value) : value;
        return {
          key: metric.key,
          label: metric.label,
          value: Number(value),
          display: Number(value).toFixed(4),
          percent: clamp01Value(percentValue) * 100,
          color: metric.color
        };
      })
      .filter(Boolean);

    if (!metrics.length) {
      metrics.push({
        key: "unavailable",
        label: "状态指标暂未返回",
        value: 0,
        display: "0",
        percent: 0,
        color: "var(--text-muted)"
      });
    }
    return metrics.slice(0, 8);
  }

  // Render Monitor values
  function renderMonitor() {
    const isRealOrPreview = hasLiveState || IS_FILE_PREVIEW;
    applyMoodTheme(sysState.emotion, sysState.theme);
    // 1. Emotion bars
    const emoContainer = document.getElementById('emo-container');
    const displayMetrics = buildEmotionDisplayMetrics(sysState.emotion);

    for (const metric of displayMetrics) {
      const { key, label, display, percent, color } = metric;
      let bar = emoContainer.querySelector(`[data-emo-key="${key}"]`);
      if (!bar) {
        const wrapper = document.createElement('div');
        wrapper.className = 'emo-bar';
        wrapper.dataset.emoKey = key;
        wrapper.innerHTML = `
          <div class="emo-header">
            <span class="emo-name">${escapeHtml(label)}</span>
            <span class="emo-val">0.0000</span>
          </div>
          <div class="emo-track">
            <div class="emo-fill"></div>
          </div>
        `;
        emoContainer.appendChild(wrapper);
        bar = wrapper;
      }
      const valueNode = bar.querySelector('.emo-val');
      const fillNode = bar.querySelector('.emo-fill');
      if (valueNode) valueNode.textContent = display;
      if (fillNode) {
        fillNode.style.backgroundColor = color;
        requestAnimationFrame(() => {
          fillNode.style.width = `${percent}%`;
        });
      }
    }
    Array.from(emoContainer.querySelectorAll('.emo-bar')).forEach(bar => {
      if (!displayMetrics.some(metric => metric.key === bar.dataset.emoKey)) {
        bar.remove();
      }
    });

    // 2. Conic Pie Chart
    const totalRoutes = Math.max(1, sysState.route_stats.fast + sysState.route_stats.normal + sysState.route_stats.full + sysState.route_stats.skip);
    const fastPct = ((sysState.route_stats.fast / totalRoutes) * 100).toFixed(1);
    const normalPct = ((sysState.route_stats.normal / totalRoutes) * 100).toFixed(1);
    const fullPct = ((sysState.route_stats.full / totalRoutes) * 100).toFixed(1);
    const skipPct = ((sysState.route_stats.skip / totalRoutes) * 100).toFixed(1);

    const pieChart = document.getElementById('route-pie-chart');
    const fVal = parseFloat(fastPct);
    const nVal = parseFloat(normalPct);
    const fuVal = parseFloat(fullPct);
    pieChart.style.background = `conic-gradient(from -90deg,
      var(--green) 0% ${fastPct}%,
      var(--blue) ${fastPct}% ${(fVal + nVal)}%,
      var(--purple) ${(fVal + nVal)}% ${(fVal + nVal + fuVal)}%,
      var(--text-muted) ${(fVal + nVal + fuVal)}% 100%
    )`;

    const legendContainer = document.getElementById('route-legend');
    legendContainer.innerHTML = `
      <div class="legend-item">
        <span class="legend-label"><span class="legend-color" style="background:var(--green)"></span>Fast (快速旁路)</span>
        <span class="legend-val">${sysState.route_stats.fast} (${fastPct}%)</span>
      </div>
      <div class="legend-item">
        <span class="legend-label"><span class="legend-color" style="background:var(--blue)"></span>Normal (标准响应)</span>
        <span class="legend-val">${sysState.route_stats.normal} (${normalPct}%)</span>
      </div>
      <div class="legend-item">
        <span class="legend-label"><span class="legend-color" style="background:var(--purple)"></span>Full (全深度评估)</span>
        <span class="legend-val">${sysState.route_stats.full} (${fullPct}%)</span>
      </div>
      <div class="legend-item">
        <span class="legend-label"><span class="legend-color" style="background:var(--text-muted)"></span>Skip (空事件跳过)</span>
        <span class="legend-val">${sysState.route_stats.skip} (${skipPct}%)</span>
      </div>
      <div class="legend-item" style="border-top:1px solid var(--card-border); margin-top:6px; padding-top:6px">
        <span class="legend-label">平均惊讶度 (Hamming)</span>
        <span class="legend-val" style="color:var(--amber)">${sysState.gate.mean_surprise.toFixed(4)}</span>
      </div>
    `;

    // 3. L6 Boundary Stats
    document.getElementById('monitor-boundary-integrity').textContent = isRealOrPreview ? Number(sysState.boundary.integrity || 0).toFixed(4) : '--';
    document.getElementById('monitor-boundary-entropy').textContent = isRealOrPreview ? Number(sysState.boundary.entropy || 0).toFixed(4) : '--';
    document.getElementById('monitor-boundary-rotation').textContent = isRealOrPreview ? `${Number(sysState.boundary.rotation || 0).toFixed(2)}°` : '--';

    // 4. L7 Expression Stats
    document.getElementById('monitor-express-threshold').textContent = isRealOrPreview ? Number(sysState.expression.threshold || 0).toFixed(4) : '--';
    document.getElementById('monitor-express-drive').textContent = isRealOrPreview ? Number(sysState.expression.pressure || 0).toFixed(4) : '--';
    document.getElementById('monitor-express-mode').textContent = isRealOrPreview ? String(sysState.expression.mode || 'silent').toUpperCase() : 'WAITING';

    // 5. Timing Stats Table
    const timingBody = document.getElementById('timing-rows');
    let timingHtml = "";
    const layerLabels = {
      perception: "L1 HDC 空间二进制感知编码",
      gate: "L2 Hamming 惊喜度分级门控",
      ssm: "L3 Void-Scar 伤痕耦合代数空间",
      memory: "L4-L5 Relational Sheaf 与 HGT 异构注意力网",
      boundary: "L6 Autopoietic 32维身份自创生流形",
      expression: "L7 Thermodynamic 相变表达决策器"
    };
    const timingEntries = Object.entries(sysState.timing || {})
      .filter(([layer]) => layer !== "total_ms")
      .map(([layer, times]) => {
        if (typeof times === "number") {
          return { layer: layer.replace(/_ms$/, ""), p50Ms: Number(times) || 0, p99Ms: Number(times) || 0 };
        }
        if (layer.endsWith("_ms")) {
          return { layer: layer.replace(/_ms$/, ""), p50Ms: Number(times) || 0, p99Ms: Number(times) || 0 };
        }
        const p50Ns = Number(times?.p50_ns ?? times?.p50 ?? 0);
        const p99Ns = Number(times?.p99_ns ?? times?.p99 ?? p50Ns);
        return { layer, p50Ms: p50Ns / 1000000, p99Ms: p99Ns / 1000000 };
      })
      .filter(item => Number.isFinite(item.p50Ms));
    const totalMs = Number(sysState.timing?.total_ms) || timingEntries.reduce((sum, item) => sum + item.p50Ms, 0);

    if (!timingEntries.length) {
      timingBody.innerHTML = `
        <tr>
          <td colspan="4" style="padding:18px 0;color:var(--text-muted);font-weight:700;">暂无真实耗时数据，等待插件后端返回 timing。</td>
        </tr>
      `;
    }

    for (const { layer, p50Ms, p99Ms } of timingEntries) {
      const ratio = totalMs > 0 ? ((p50Ms / totalMs) * 100).toFixed(1) : "0.0";
      timingHtml += `
        <tr style="border-bottom:1px solid rgba(255, 255, 255, 0.03)">
          <td style="padding:14px 0; font-weight:600">${layerLabels[layer] || layer}</td>
          <td style="font-family:monospace;font-weight:700">${p50Ms.toFixed(4)} ms</td>
          <td style="font-family:monospace;color:var(--text-muted)">${p99Ms.toFixed(4)} ms</td>
          <td style="font-family:monospace;font-weight:700;color:var(--primary)">${ratio}%</td>
        </tr>
      `;
    }
    if (timingEntries.length) timingBody.innerHTML = timingHtml;
    if (activeTab === "spine" && (activeSpineStep === 2 || activeSpineStep === 5)) {
      updateSpineControls();
    }
  }

  function configGroupsFromSchema(schema) {
    const keys = Object.keys(schema || {});
    const groups = [
      { title: "Sylanne 4.0 Alpha 核心目录", match: key => key === "sylanne_alpha_root" },
      { title: "即时聊天与流式分段", match: key => key.includes("realtime") || key.includes("stream_first") },
      { title: "主动发起与后台调度", match: key => key.includes("proactive") },
      { title: "Embedding 记忆召回", match: key => key.includes("embedding_memory") },
      { title: "判断 LLM 通道", match: key => key.includes("assessor") },
      { title: "后台工作队列", match: key => key.includes("background") },
      { title: "生活模拟", match: key => key.includes("life_simulation") }
    ];
    const used = new Set();
    return groups.map(group => {
      const groupKeys = keys.filter(key => group.match(key));
      groupKeys.forEach(key => used.add(key));
      return { title: group.title, keys: groupKeys };
    }).filter(group => group.keys.length > 0).concat(
      keys.filter(key => !used.has(key)).length
        ? [{ title: "其他包体配置", keys: keys.filter(key => !used.has(key)) }]
        : []
    );
  }

  function valueForConfigKey(key, meta) {
    if (Object.prototype.hasOwnProperty.call(runtimeConfigValues, key)) {
      return runtimeConfigValues[key];
    }
    return meta?.default ?? "";
  }

  function renderConfigInput(key, meta, val) {
    const type = meta.type || "string";
    if (type === "bool") {
      return `
        <label class="switch">
          <input type="checkbox" id="set-${key}" ${val ? 'checked' : ''}>
          <span class="slider"></span>
        </label>
      `;
    }
    if (type === "int") {
      const minAttr = meta.min !== undefined || meta.minimum !== undefined ? ` min="${escapeHtml(meta.min ?? meta.minimum)}"` : "";
      const maxAttr = meta.max !== undefined || meta.maximum !== undefined ? ` max="${escapeHtml(meta.max ?? meta.maximum)}"` : "";
      return `
        <div class="number-stepper" data-step="1">
          <button type="button" class="number-stepper-btn" data-delta="-1" aria-label="减少">-</button>
          <input type="number" step="1"${minAttr}${maxAttr} class="num-input" id="set-${key}" value="${escapeHtml(val)}">
          <button type="button" class="number-stepper-btn" data-delta="1" aria-label="增加">+</button>
        </div>
      `;
    }
    if (type === "float") {
      const step = meta.step ?? meta.multipleOf ?? 0.05;
      const minAttr = meta.min !== undefined || meta.minimum !== undefined ? ` min="${escapeHtml(meta.min ?? meta.minimum)}"` : "";
      const maxAttr = meta.max !== undefined || meta.maximum !== undefined ? ` max="${escapeHtml(meta.max ?? meta.maximum)}"` : "";
      return `
        <div class="number-stepper" data-step="${escapeHtml(step)}">
          <button type="button" class="number-stepper-btn" data-delta="-1" aria-label="减少">-</button>
          <input type="number" step="${escapeHtml(step)}"${minAttr}${maxAttr} class="num-input" id="set-${key}" value="${escapeHtml(val)}">
          <button type="button" class="number-stepper-btn" data-delta="1" aria-label="增加">+</button>
        </div>
      `;
    }
    if (Array.isArray(meta.options) && meta.options.length) {
      return `
        <select class="select-input" id="set-${key}">
          ${meta.options.map(option => `<option value="${escapeHtml(option)}" ${String(val) === String(option) ? 'selected' : ''}>${escapeHtml(option)}</option>`).join('')}
        </select>
      `;
    }
    if (meta._special === "select_provider" || key.endsWith("provider_id")) {
      const manualId = `set-${key}-manual`;
      const selectedKnown = runtimeProviders.some(provider => String(provider.id || provider.provider_id || "") === String(val || ""));
      const options = runtimeProviders.map(provider => {
        const id = provider.id || provider.provider_id || "";
        const label = provider.name && provider.name !== id ? `${provider.name} (${id})` : id;
        return id ? `<button type="button" class="provider-picker-option ${String(val) === String(id) ? 'active' : ''}" data-value="${escapeHtml(id)}"><span>${escapeHtml(provider.name || id)}</span><small>${escapeHtml(id)}</small></button>` : "";
      }).join('');
      const useManual = val && !selectedKnown;
      const currentLabel = useManual ? '手动填写 Provider ID...' : (val ? (runtimeProviders.find(provider => String(provider.id || provider.provider_id || "") === String(val))?.name || val) : '不启用 / 留空');
      return `
        <div class="provider-input-stack ${useManual ? 'manual-active' : ''}" data-provider-key="${escapeHtml(key)}">
          <input type="hidden" id="set-${key}" class="provider-value" value="${useManual ? '__manual__' : escapeHtml(val || '')}">
          <button type="button" class="provider-picker-button" data-manual-input="${manualId}">${escapeHtml(currentLabel)}</button>
          <div class="provider-picker-menu">
            <button type="button" class="provider-picker-option ${!val ? 'active' : ''}" data-value=""><span>不启用 / 留空</span><small>empty</small></button>
            ${options}
            <button type="button" class="provider-picker-option ${useManual ? 'active' : ''}" data-value="__manual__"><span>手动填写 Provider ID...</span><small>custom AstrBot provider id</small></button>
          </div>
          <div class="provider-manual-wrap">
            <input type="text" class="text-input provider-manual-input" id="${manualId}" value="${useManual ? escapeHtml(val) : ''}" placeholder="手动 Provider ID">
          </div>
        </div>
      `;
    }
    return `<input type="text" class="text-input" id="set-${key}" value="${escapeHtml(val)}">`;
  }

  function collectSettingsPayload() {
    const payload = {};
    for (const [key, meta] of Object.entries(runtimeConfigSchema)) {
      const el = document.getElementById(`set-${key}`);
      if (!el) continue;
      if (meta.type === "bool") payload[key] = el.checked;
      else if (meta.type === "int") payload[key] = parseInt(el.value || meta.default || 0, 10);
      else if (meta.type === "float") payload[key] = parseFloat(el.value || meta.default || 0);
      else if (meta._special === "select_provider" || key.endsWith("provider_id")) {
        payload[key] = el.value === "__manual__" ? (document.getElementById(`set-${key}-manual`)?.value || "") : el.value;
      } else payload[key] = el.value;
    }
    return payload;
  }

  // Render Settings Panel dynamically from the actual package schema.
  function renderSettings() {
    const container = document.getElementById('settings-container');
    let html = "";
    const groups = configGroupsFromSchema(runtimeConfigSchema);

    for (const group of groups) {
      html += `
        <div class="settings-group">
          <div class="settings-group-title">${escapeHtml(group.title)}</div>
      `;

      for (const key of group.keys) {
        const meta = runtimeConfigSchema[key];
        if (!meta) continue;
        const val = valueForConfigKey(key, meta);
        const inputHtml = renderConfigInput(key, meta, val);

        html += `
          <div class="setting-row">
            <div class="setting-info">
              <span class="setting-label">${escapeHtml(meta.description || key)}</span>
              <span class="setting-desc">${escapeHtml(meta.hint || key)}</span>
            </div>
            <div>
              ${inputHtml}
            </div>
          </div>
        `;
      }

      html += `</div>`;
    }

    container.innerHTML = html;

    container.querySelectorAll('.provider-input-stack').forEach(stack => {
      const button = stack.querySelector('.provider-picker-button');
      const hidden = stack.querySelector('.provider-value');
      const manual = document.getElementById(button?.dataset.manualInput || '');
      const options = stack.querySelectorAll('.provider-picker-option');
      const close = () => stack.classList.remove('open');
      const open = () => stack.classList.add('open');
      const syncManual = () => stack.classList.toggle('manual-active', hidden?.value === "__manual__");
      button?.addEventListener('click', (event) => {
        event.stopPropagation();
        stack.classList.contains('open') ? close() : open();
      });
      options.forEach(option => {
        option.addEventListener('click', (event) => {
          event.stopPropagation();
          options.forEach(item => item.classList.remove('active'));
          option.classList.add('active');
          if (hidden) hidden.value = option.dataset.value || '';
          if (button) button.textContent = option.querySelector('span')?.textContent || '不启用 / 留空';
          syncManual();
          close();
          if (hidden?.value === "__manual__") setTimeout(() => manual?.focus(), 180);
        });
      });
      document.addEventListener('click', close);
      syncManual();
    });

    container.querySelectorAll('.number-stepper').forEach(stepper => {
      const input = stepper.querySelector('.num-input');
      const buttons = stepper.querySelectorAll('.number-stepper-btn');
      if (!input) return;
      const stepValue = Number(stepper.dataset.step || input.step || 1) || 1;
      const decimals = String(stepValue).includes('.') ? String(stepValue).split('.')[1].length : 0;
      const clampNumber = value => {
        let next = value;
        if (input.min !== "") next = Math.max(Number(input.min), next);
        if (input.max !== "") next = Math.min(Number(input.max), next);
        return next;
      };
      const applyDelta = delta => {
        const current = Number(input.value || input.defaultValue || 0) || 0;
        const next = clampNumber(current + stepValue * delta);
        input.value = decimals ? next.toFixed(decimals) : String(Math.round(next));
        input.dispatchEvent(new Event('input', { bubbles: true }));
      };
      buttons.forEach(button => {
        button.addEventListener('click', () => applyDelta(Number(button.dataset.delta || 0)));
      });
      input.addEventListener('blur', () => {
        const parsed = Number(input.value);
        if (Number.isFinite(parsed)) {
          const next = clampNumber(parsed);
          input.value = decimals ? next.toFixed(decimals) : String(Math.round(next));
        }
      });
    });

    // Save action bind
    document.getElementById('save-settings-btn').onclick = () => {
      const payload = collectSettingsPayload();
      runtimeConfigValues = { ...runtimeConfigValues, ...payload };

      apiFetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }).then(res => res.json())
        .then(data => alert(`已保存 ${data.updated?.length ?? Object.keys(payload).length} 个包体配置项。`))
        .catch(err => {
          console.log("Offline mode settings saved locally:", payload);
          alert("本地配置已更新 (当前处于离线仿真调试模式)");
        });
    };
  }

  async function syncSettings() {
    try {
      const res = await apiFetch('/api/settings', { cache: 'no-store' });
      if (!res.ok) throw new Error("settings offline");
      const data = await res.json();
      if (data.schema && Object.keys(data.schema).length) {
        runtimeConfigSchema = data.schema;
      }
      runtimeProviders = data.providers || data.llm_providers || data.embedding_providers || [];
      runtimeConfigValues = {
        ...Object.fromEntries(Object.entries(runtimeConfigSchema).map(([key, meta]) => [key, meta.default])),
        ...(data.values || {})
      };
      renderSettings();
    } catch (e) {
      runtimeConfigSchema = FALLBACK_CONFIG_SCHEMA;
      runtimeConfigValues = Object.fromEntries(
        Object.entries(FALLBACK_CONFIG_SCHEMA).map(([key, meta]) => [key, meta.default])
      );
      renderSettings();
    }
  }

  // Interactive 7-Layer Canvas Animations
  let visCanvas, ctx;
  const stepCards = document.querySelectorAll('.spine-step-card');
  let triggerL6Perturbation = null; // Local L6 perturbation callback

  function clamp01(value) {
    const n = Number(value);
    return Number.isFinite(n) ? Math.max(0, Math.min(1, n)) : 0;
  }

  function normalizeValence(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return 0.5;
    return n < 0 ? clamp01((n + 1) / 2) : clamp01(n);
  }

  function wrapCanvasText(canvasCtx, text, x, y, maxWidth, lineHeight, maxLines = 3) {
    const words = String(text || '').split('');
    let line = '';
    let lines = 0;
    for (const ch of words) {
      const test = line + ch;
      if (canvasCtx.measureText(test).width > maxWidth && line) {
        canvasCtx.fillText(line, x, y + lines * lineHeight);
        line = ch;
        lines++;
        if (lines >= maxLines) return;
      } else {
        line = test;
      }
    }
    if (line && lines < maxLines) canvasCtx.fillText(line, x, y + lines * lineHeight);
  }

  function layerPayload(name) {
    const live = sysState.layers?.[name];
    if (live && typeof live === 'object' && Object.keys(live).length) return { mode: 'live', data: live };
    const latest = visibleComputationLogs?.[visibleComputationLogs.length - 1]?.layers?.[name];
    if (latest && typeof latest === 'object' && Object.keys(latest).length) return { mode: 'live-summary', data: latest };
    if (hasLiveState) return { mode: 'derived', data: {} };
    if (window.location.protocol === 'file:') return { mode: 'offline-preview', data: {} };
    return { mode: 'unavailable', data: {} };
  }

  function drawDataModeBadge(canvasCtx, mode, x, y) {
    const labels = {
      live: '真实层数据',
      'live-summary': '日志摘要',
      derived: '派生视图',
      'offline-preview': '本地预览',
      unavailable: '暂无数据'
    };
    const styles = getComputedStyle(document.documentElement);
    const colors = {
      live: styles.getPropertyValue('--green').trim() || '#34d399',
      'live-summary': styles.getPropertyValue('--blue').trim() || '#60a5fa',
      derived: styles.getPropertyValue('--amber').trim() || '#fbbf24',
      'offline-preview': styles.getPropertyValue('--primary').trim() || '#F3A7C8',
      unavailable: styles.getPropertyValue('--text-muted').trim() || '#64748b'
    };
    canvasCtx.save();
    canvasCtx.font = '800 11px sans-serif';
    const text = labels[mode] || mode;
    const w = canvasCtx.measureText(text).width + 22;
    canvasCtx.fillStyle = document.documentElement.getAttribute('data-theme') !== 'light'
      ? 'rgba(15,23,42,0.72)'
      : 'rgba(255,255,255,0.78)';
    canvasCtx.strokeStyle = colors[mode] || 'var(--card-border)';
    canvasCtx.lineWidth = 1;
    canvasCtx.beginPath();
    canvasCtx.roundRect(x, y - 16, w, 24, 12);
    canvasCtx.fill();
    canvasCtx.stroke();
    canvasCtx.fillStyle = colors[mode] || 'var(--text-muted)';
    canvasCtx.fillText(text, x + 11, y);
    canvasCtx.restore();
  }

  function drawProgressBar(canvasCtx, x, y, w, value, color, bg) {
    canvasCtx.fillStyle = bg;
    canvasCtx.beginPath();
    canvasCtx.roundRect(x, y, w, 6, 3);
    canvasCtx.fill();
    canvasCtx.fillStyle = color;
    canvasCtx.beginPath();
    canvasCtx.roundRect(x, y, w * clamp01(value), 6, 3);
    canvasCtx.fill();
  }

  function drawL1Visualizer(ctx, rect, frame, isDark) {
    const payload = layerPayload('L1_HDC');
    const data = payload.data || {};
    const hasBits = Array.isArray(data.sample_bits) && data.sample_bits.length > 0;
    const bits = hasBits ? data.sample_bits : [];
    const density = Number.isFinite(Number(data.density)) ? clamp01(data.density) : null;
    const flipRate = Number.isFinite(Number(data.flip_ratio)) ? clamp01(data.flip_ratio) : null;
    const similarity = Number.isFinite(Number(data.prediction_similarity))
      ? clamp01(data.prediction_similarity)
      : Math.max(0.12, 1 - clamp01(sysState.gate?.mean_surprise || 0.1));
    const displayDensity = density ?? 0;
    const displayFlip = flipRate ?? 0;
    const inputText = String(data.input_text || visibleComputationLogs[visibleComputationLogs.length - 1]?.text || sysState.spine?.last_text || '等待下一条消息进入感知层').slice(0, 36);
    const styles = getComputedStyle(document.documentElement);
    const l1Color = styles.getPropertyValue('--l1-color').trim() || '#22d3ee';
    const primary = styles.getPropertyValue('--primary').trim() || '#F3A7C8';
    const green = styles.getPropertyValue('--green').trim() || '#34d399';
    const muted = isDark ? 'rgba(203,213,225,0.72)' : 'rgba(51,65,85,0.72)';
    const text = isDark ? '#f8fafc' : '#0f172a';
    const cardFill = isDark ? 'rgba(15,23,42,0.70)' : 'rgba(255,255,255,0.78)';
    const cardStroke = isDark ? 'rgba(148,163,184,0.15)' : 'rgba(15,23,42,0.10)';

    ctx.fillStyle = text;
    ctx.font = '800 13px sans-serif';
    ctx.fillText('L1 HDC 编码流', 20, 30);
    ctx.fillStyle = muted;
    ctx.font = '700 11px sans-serif';
    ctx.fillText('编码带来自后端 sample_bits；缺失时只显示数据占位，不伪装成真实向量。', 20, 48);
    drawDataModeBadge(ctx, payload.mode, rect.width - 130, 32);

    const panelY = 64;
    const panelH = Math.max(190, rect.height - 112);
    const compact = rect.width < 820;
    const leftW = compact ? 0 : Math.min(210, Math.max(160, rect.width * 0.22));
    const rightW = compact ? 0 : Math.min(190, Math.max(150, rect.width * 0.20));
    const midX = compact ? 28 : 36 + leftW + 22;
    const midW = compact ? rect.width - 56 : Math.max(260, rect.width - midX - rightW - 58);
    const rightX = midX + midW + 22;
    const cards = compact
      ? [{ x: midX, w: midW, title: hasBits ? 'HDC sample bits' : '等待 HDC sample_bits', hint: `${data.vector_dim || 2048}-bit / ${hasBits ? '真实采样' : '后端暂未提供采样'}` }]
      : [
          { x: 36, w: leftW, title: '最近输入', hint: '后端 text -> encoder.encode_text' },
          { x: midX, w: midW, title: hasBits ? 'HDC sample bits' : '等待 HDC sample_bits', hint: `${data.vector_dim || 2048}-bit / ${hasBits ? '真实采样' : '后端暂未提供采样'}` },
          { x: rightX, w: rightW, title: '编码指标', hint: '真实字段优先，缺字段标派生' }
        ];
    cards.forEach(card => {
      ctx.fillStyle = cardFill;
      ctx.strokeStyle = cardStroke;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.roundRect(card.x, panelY, card.w, panelH, 14);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = text;
      ctx.font = '800 13px sans-serif';
      ctx.fillText(card.title, card.x + 16, panelY + 28);
      ctx.fillStyle = muted;
      ctx.font = '700 11px sans-serif';
      ctx.fillText(card.hint, card.x + 16, panelY + 48);
    });

    if (!compact) {
      ctx.fillStyle = isDark ? 'rgba(34,211,238,0.10)' : 'rgba(8,145,178,0.08)';
      ctx.strokeStyle = l1Color;
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.roundRect(52, panelY + 78, leftW - 32, 82, 12);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = isDark ? '#dff9ff' : '#0e7490';
      ctx.font = '800 12px monospace';
      ctx.fillText('TEXT IN', 66, panelY + 104);
      ctx.fillStyle = text;
      ctx.font = '700 12px sans-serif';
      wrapCanvasText(ctx, `"${inputText}"`, 66, panelY + 128, leftW - 58, 18, 2);
    }

    const rows = Number(data.sample_rows) || 16;
    const cols = Number(data.sample_cols) || 64;
    const maxRows = compact ? 10 : Math.min(16, rows);
    const maxCols = Math.min(64, cols);
    const gridX = midX + 18;
    const gridY = panelY + 78;
    const cellW = Math.max(3, (midW - 36) / maxCols);
    const cellH = Math.max(4, Math.min(13, (panelH - (compact ? 162 : 120)) / maxRows));
    for (let r = 0; r < maxRows; r++) {
      for (let c = 0; c < maxCols; c++) {
        const idx = r * cols + c;
        const liveBit = hasBits ? Number(bits[idx]) === 1 : false;
        const pulse = !hasBits && ((idx + Math.floor(frame / 22)) % 41 === 0);
        ctx.fillStyle = liveBit
          ? l1Color
          : (pulse ? 'rgba(148,163,184,0.16)' : (isDark ? 'rgba(255,255,255,0.035)' : 'rgba(15,23,42,0.035)'));
        ctx.fillRect(gridX + c * cellW + 1, gridY + r * cellH + 1, Math.max(2, cellW - 2), Math.max(2, cellH - 2));
      }
    }

    if (!hasBits) {
      ctx.fillStyle = muted;
      ctx.font = '800 12px sans-serif';
      ctx.fillText('后端暂未提供 sample_bits，当前不显示真实编码带。', gridX, gridY + maxRows * cellH + 26);
    }

    const metrics = [
      { label: '激活密度', value: displayDensity, text: density === null ? '--' : density.toFixed(3), color: l1Color },
      { label: '本帧翻转率', value: displayFlip, text: flipRate === null ? '--' : `${(flipRate * 100).toFixed(1)}%`, color: primary },
      { label: '预测相似度', value: similarity, text: similarity.toFixed(3), color: green }
    ];
    const metricBaseY = compact ? Math.min(rect.height - 58, gridY + maxRows * cellH + 50) : panelY + 82;
    if (compact) {
      const boxW = (midW - 24) / 3;
      metrics.forEach((item, idx) => {
        const x = midX + 12 + idx * boxW;
        ctx.fillStyle = muted;
        ctx.font = '700 11px sans-serif';
        ctx.fillText(item.label, x, metricBaseY);
        ctx.fillStyle = item.color;
        ctx.font = '900 14px monospace';
        ctx.fillText(item.text, x, metricBaseY + 21);
        drawProgressBar(ctx, x, metricBaseY + 31, boxW - 16, item.value, item.color, isDark ? 'rgba(148,163,184,0.16)' : 'rgba(15,23,42,0.10)');
      });
    } else {
      metrics.forEach((item, idx) => {
        const y = metricBaseY + idx * 58;
        ctx.fillStyle = muted;
        ctx.font = '700 12px sans-serif';
        ctx.fillText(item.label, rightX + 16, y);
        ctx.fillStyle = item.color;
        ctx.font = '900 16px monospace';
        ctx.fillText(item.text, rightX + 16, y + 22);
        drawProgressBar(ctx, rightX + 16, y + 34, rightW - 32, item.value, item.color, isDark ? 'rgba(148,163,184,0.16)' : 'rgba(15,23,42,0.10)');
      });
      ctx.fillStyle = muted;
      ctx.font = '700 10px sans-serif';
      ctx.fillText(`source: ${data.source || payload.mode}`, rightX + 16, panelY + panelH - 18);
    }
  }

  function drawL3Visualizer(ctx, rect, frame, isDark) {
    const payload = layerPayload('L3_VoidScar');
    const data = payload.data || {};
    const styles = getComputedStyle(document.documentElement);
    const primary = styles.getPropertyValue('--primary').trim() || '#F3A7C8';
    const purple = styles.getPropertyValue('--purple').trim() || '#c084fc';
    const red = styles.getPropertyValue('--red').trim() || '#f87171';
    const green = styles.getPropertyValue('--green').trim() || '#34d399';
    const text = isDark ? '#f8fafc' : '#0f172a';
    const muted = isDark ? 'rgba(203,213,225,0.72)' : 'rgba(51,65,85,0.72)';
    const grid = isDark ? 'rgba(148,163,184,0.12)' : 'rgba(15,23,42,0.08)';
    const voids = Array.isArray(data.voids) && data.voids.length ? data.voids : (payload.mode === 'derived' || payload.mode === 'offline-preview' ? sysState.voids : []);
    const scars = Array.isArray(data.scars) && data.scars.length ? data.scars : (payload.mode === 'derived' || payload.mode === 'offline-preview' ? sysState.scars : []);
    const coherence = Number.isFinite(Number(data.coherence)) ? clamp01(data.coherence) : clamp01(sysState.boundary?.stability ?? sysState.boundary?.integrity ?? 0.8);
    const surprise = clamp01(sysState.spine?.surprise ?? sysState.gate?.mean_surprise ?? 0.08);
    const tension = clamp01(sysState.emotion?.tension ?? 0.2);
    const repair = clamp01(sysState.emotion?.repair_pressure ?? 0.2);

    ctx.fillStyle = text;
    ctx.font = '800 13px sans-serif';
    ctx.fillText('L3 Void-Scar 伤痕/空洞诊断', 20, 30);
    ctx.fillStyle = muted;
    ctx.font = '700 11px sans-serif';
    ctx.fillText('波形=当前扰动；空心圆=Void 缺席；尖峰=Scar 伤痕；相干度越低代表内部冲突越强。', 20, 48);
    drawDataModeBadge(ctx, payload.mode, rect.width - 130, 32);

    const plot = { x: 42, y: 74, w: Math.max(300, rect.width - 278), h: Math.max(190, rect.height - 142) };
    const panel = { x: rect.width - 206, y: 74, w: 164, h: plot.h };
    const midY = plot.y + plot.h * 0.52;
    ctx.strokeStyle = grid;
    ctx.lineWidth = 1;
    for (let i = 0; i <= 5; i++) {
      const y = plot.y + (plot.h / 5) * i;
      ctx.beginPath();
      ctx.moveTo(plot.x, y);
      ctx.lineTo(plot.x + plot.w, y);
      ctx.stroke();
    }
    for (let i = 0; i <= 8; i++) {
      const x = plot.x + (plot.w / 8) * i;
      ctx.beginPath();
      ctx.moveTo(x, plot.y);
      ctx.lineTo(x, plot.y + plot.h);
      ctx.stroke();
    }

    const samples = 110;
    const amp = 15 + tension * 42 + surprise * 30;
    ctx.strokeStyle = primary;
    ctx.lineWidth = 3;
    ctx.beginPath();
    for (let i = 0; i < samples; i++) {
      const t = i / (samples - 1);
      const x = plot.x + t * plot.w;
      const wave = Math.sin(t * Math.PI * 8 + frame * 0.045) * 0.62 + Math.sin(t * Math.PI * 23 + frame * 0.022) * 0.18;
      const y = midY + wave * amp * (0.5 + repair * 0.5);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();

    ctx.strokeStyle = isDark ? 'rgba(226,232,240,0.26)' : 'rgba(15,23,42,0.16)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(plot.x, midY);
    ctx.lineTo(plot.x + plot.w, midY);
    ctx.stroke();

    voids.slice(0, 5).forEach((v, idx) => {
      const depth = clamp01(v.depth ?? v.pressure ?? 0.35);
      const x = plot.x + plot.w * ((idx + 1) / (Math.min(voids.length, 5) + 1));
      const y = midY + Math.sin(frame * 0.035 + idx) * 10;
      const r = 10 + depth * 20;
      ctx.strokeStyle = purple;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.stroke();
      ctx.fillStyle = isDark ? 'rgba(192,132,252,0.10)' : 'rgba(192,132,252,0.14)';
      ctx.beginPath();
      ctx.arc(x, y, Math.max(3, r - 5), 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = text;
      ctx.font = '800 10px sans-serif';
      ctx.fillText('Void', x - 12, y - r - 8);
      ctx.fillStyle = muted;
      ctx.font = '700 9px sans-serif';
      ctx.fillText(String(v.concept || '缺席').slice(0, 12), x - 24, y + r + 14);
    });

    scars.slice(0, 5).forEach((s, idx) => {
      const weight = clamp01(s.weight ?? 0.45);
      const x = plot.x + plot.w * ((idx + 0.75) / (Math.min(scars.length, 5) + 0.7));
      const base = plot.y + plot.h - 22;
      const h = 28 + weight * 70;
      ctx.strokeStyle = red;
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      ctx.moveTo(x - 16, base);
      ctx.lineTo(x, base - h - Math.sin(frame * 0.08 + idx) * 4);
      ctx.lineTo(x + 16, base);
      ctx.stroke();
      ctx.fillStyle = 'rgba(248,113,113,0.16)';
      ctx.beginPath();
      ctx.moveTo(x - 16, base);
      ctx.lineTo(x, base - h);
      ctx.lineTo(x + 16, base);
      ctx.closePath();
      ctx.fill();
      ctx.fillStyle = red;
      ctx.font = '800 10px sans-serif';
      ctx.fillText('Scar', x - 12, base + 16);
    });

    ctx.fillStyle = isDark ? 'rgba(15,23,42,0.72)' : 'rgba(255,255,255,0.78)';
    ctx.strokeStyle = isDark ? 'rgba(148,163,184,0.18)' : 'rgba(15,23,42,0.10)';
    ctx.beginPath();
    ctx.roundRect(panel.x, panel.y, panel.w, panel.h, 14);
    ctx.fill();
    ctx.stroke();
    [
      ['Void 空洞', Number(data.void_count ?? voids.length), purple, clamp01((data.void_count ?? voids.length) / 8)],
      ['Scar 伤痕', Number(data.scar_count ?? scars.length), red, clamp01((data.scar_count ?? scars.length) / 8)],
      ['系统相干', coherence.toFixed(2), green, coherence],
      ['Ghost 残影', Number(data.ghost_count ?? 0), primary, clamp01((data.ghost_count ?? 0) / 8)]
    ].forEach((row, idx) => {
      const y = panel.y + 34 + idx * 48;
      ctx.fillStyle = muted;
      ctx.font = '700 11px sans-serif';
      ctx.fillText(row[0], panel.x + 16, y);
      ctx.fillStyle = row[2];
      ctx.font = '900 19px monospace';
      ctx.fillText(String(row[1]), panel.x + 16, y + 22);
      drawProgressBar(ctx, panel.x + 16, y + 30, panel.w - 32, row[3], row[2], isDark ? 'rgba(148,163,184,0.16)' : 'rgba(15,23,42,0.10)');
    });
  }

  function drawL4Visualizer(ctx, rect, frame, isDark) {
    const payload = layerPayload('L4_Sheaf');
    const data = payload.data || {};
    const prop = data.propagation && typeof data.propagation === 'object' ? data.propagation : data;
    const styles = getComputedStyle(document.documentElement);
    const l4Color = styles.getPropertyValue('--l4-color').trim() || '#a78bfa';
    const primary = styles.getPropertyValue('--primary').trim() || '#F3A7C8';
    const amber = styles.getPropertyValue('--amber').trim() || '#fbbf24';
    const green = styles.getPropertyValue('--green').trim() || '#34d399';
    const red = styles.getPropertyValue('--red').trim() || '#f87171';
    const text = isDark ? '#f8fafc' : '#0f172a';
    const muted = isDark ? 'rgba(203,213,225,0.72)' : 'rgba(51,65,85,0.72)';
    const cardFill = isDark ? 'rgba(15,23,42,0.72)' : 'rgba(255,255,255,0.78)';
    const cardStroke = isDark ? 'rgba(148,163,184,0.18)' : 'rgba(15,23,42,0.10)';
    const propagated = Boolean(prop.propagated);
    const energy = clamp01(data.energy ?? prop.energy_remaining ?? 0);
    const dissociation = clamp01(data.dissociation_pressure ?? 0);
    const decay = clamp01(data.decay_factor ?? prop.decay_factor ?? 0);
    const affected = Array.isArray(data.affected_dims) ? data.affected_dims : (Array.isArray(prop.affected_dims) ? prop.affected_dims : []);
    const targets = Array.isArray(data.propagated_to) ? data.propagated_to : (Array.isArray(prop.propagated_to) ? prop.propagated_to : []);
    const reason = String(data.reason || prop.reason || '');

    ctx.fillStyle = text;
    ctx.font = '800 13px sans-serif';
    ctx.fillText('L4 Sheaf 关系传播诊断', 20, 30);
    ctx.fillStyle = muted;
    ctx.font = '700 11px sans-serif';
    ctx.fillText('输入关系进入 Sheaf 后，观察传播是否发生、影响哪些维度、能量是否被耗散。', 20, 48);
    drawDataModeBadge(ctx, payload.mode, rect.width - 130, 32);

    const left = { x: 42, y: 80, w: Math.max(260, rect.width * 0.42), h: rect.height - 148 };
    const mid = { x: left.x + left.w + 24, y: 80, w: Math.max(210, rect.width * 0.24), h: left.h };
    const right = { x: mid.x + mid.w + 24, y: 80, w: rect.width - (mid.x + mid.w + 66), h: left.h };
    [left, mid, right].forEach(box => {
      ctx.fillStyle = cardFill;
      ctx.strokeStyle = cardStroke;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.roundRect(box.x, box.y, box.w, box.h, 14);
      ctx.fill();
      ctx.stroke();
    });

    const pipeline = [
      ['输入关系', propagated ? `edge ${data.source_relationship ?? prop.source ?? 0}` : '等待有效边'],
      ['传播', propagated ? '已发生' : '未传播'],
      ['受影响维度', affected.length ? `${affected.length} 个` : '--'],
      ['耗散', decay ? decay.toFixed(2) : '--']
    ];
    pipeline.forEach((item, idx) => {
      const x = left.x + 28 + idx * ((left.w - 56) / 4);
      const y = left.y + left.h * 0.45 + Math.sin(frame * 0.035 + idx) * 3;
      ctx.fillStyle = idx === 1 && !propagated ? amber : l4Color;
      ctx.beginPath();
      ctx.arc(x, y, 16, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = isDark ? '#0f172a' : '#ffffff';
      ctx.font = '900 12px monospace';
      ctx.fillText(String(idx + 1), x - 4, y + 4);
      if (idx < pipeline.length - 1) {
        ctx.strokeStyle = propagated ? l4Color : 'rgba(148,163,184,0.30)';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(x + 22, y);
        ctx.lineTo(x + ((left.w - 56) / 4) - 22, y);
        ctx.stroke();
      }
      ctx.fillStyle = text;
      ctx.font = '800 12px sans-serif';
      ctx.fillText(item[0], x - 28, y + 42);
      ctx.fillStyle = muted;
      ctx.font = '700 11px sans-serif';
      ctx.fillText(item[1], x - 28, y + 60);
    });
    if (!propagated) {
      ctx.fillStyle = muted;
      ctx.font = '800 12px sans-serif';
      ctx.fillText(reason === 'invalid_source' ? '本帧没有有效关系边，Sheaf 未传播。' : '本帧没有传播事件。', left.x + 20, left.y + left.h - 24);
    }

    ctx.fillStyle = text;
    ctx.font = '800 13px sans-serif';
    ctx.fillText('受影响维度', mid.x + 16, mid.y + 30);
    const dims = affected.length ? affected.slice(0, 8) : [0, 1, 2, 3, 4, 5, 6, 7];
    dims.forEach((dim, idx) => {
      const y = mid.y + 58 + idx * 24;
      const value = affected.length ? clamp01(0.32 + ((Number(dim) % 8) / 10)) : 0;
      ctx.fillStyle = muted;
      ctx.font = '700 11px monospace';
      ctx.fillText(`dim ${dim}`, mid.x + 16, y);
      drawProgressBar(ctx, mid.x + 72, y - 8, mid.w - 96, value, affected.length ? primary : 'rgba(148,163,184,0.35)', isDark ? 'rgba(148,163,184,0.16)' : 'rgba(15,23,42,0.10)');
    });

    const cards = [
      ['关系能量', energy.toFixed(2), energy, green],
      ['解离压力', dissociation.toFixed(2), dissociation, red],
      ['传播衰减', decay ? decay.toFixed(2) : '--', decay, l4Color],
      ['传播状态', propagated ? 'ON' : 'IDLE', propagated ? 1 : 0, propagated ? green : amber],
      ['目标边数', String(targets.length), clamp01(targets.length / 8), primary]
    ];
    cards.forEach((item, idx) => {
      const y = right.y + 34 + idx * 48;
      ctx.fillStyle = muted;
      ctx.font = '700 11px sans-serif';
      ctx.fillText(item[0], right.x + 16, y);
      ctx.fillStyle = item[3];
      ctx.font = '900 18px monospace';
      ctx.fillText(item[1], right.x + 16, y + 22);
      drawProgressBar(ctx, right.x + 16, y + 30, right.w - 32, item[2], item[3], isDark ? 'rgba(148,163,184,0.16)' : 'rgba(15,23,42,0.10)');
    });
  }

  function drawL7Visualizer(ctx, rect, frame, isDark) {
    const styles = getComputedStyle(document.documentElement);
    const l7Color = styles.getPropertyValue('--l7-color').trim() || '#f472b6';
    const primary = styles.getPropertyValue('--primary').trim() || '#F3A7C8';
    const amber = styles.getPropertyValue('--amber').trim() || '#fbbf24';
    const green = styles.getPropertyValue('--green').trim() || '#34d399';
    const text = isDark ? '#f8fafc' : '#0f172a';
    const muted = isDark ? 'rgba(203,213,225,0.72)' : 'rgba(51,65,85,0.72)';
    const grid = isDark ? 'rgba(148,163,184,0.12)' : 'rgba(15,23,42,0.08)';
    const pressure = clamp01(sysState.expression?.pressure ?? sysState.emotion?.expression_drive ?? 0);
    const threshold = Math.max(0.05, Math.min(1, Number(sysState.expression?.threshold ?? 0.6)));
    const ratio = pressure / threshold;
    const mode = String(sysState.expression?.mode || (ratio >= 1 ? 'ready' : 'accumulating')).toUpperCase();
    const displayLevel = Math.max(0.06, pressure);

    ctx.fillStyle = text;
    ctx.font = '800 13px sans-serif';
    ctx.fillText('L7 表达压力累积', 20, 30);
    ctx.fillStyle = muted;
    ctx.font = '700 11px sans-serif';
    ctx.fillText('液面=表达驱动累计；虚线=触发阈值；超过阈值后进入相变表达，然后缓慢回落。', 20, 48);
    drawDataModeBadge(ctx, hasLiveState ? 'derived' : (window.location.protocol === 'file:' ? 'offline-preview' : 'unavailable'), rect.width - 130, 32);

    const plot = { x: 42, y: 74, w: Math.max(300, rect.width - 278), h: Math.max(210, rect.height - 142) };
    const panel = { x: rect.width - 206, y: 74, w: 164, h: plot.h };
    ctx.strokeStyle = grid;
    ctx.lineWidth = 1;
    for (let i = 0; i <= 5; i++) {
      const y = plot.y + (plot.h / 5) * i;
      ctx.beginPath();
      ctx.moveTo(plot.x, y);
      ctx.lineTo(plot.x + plot.w, y);
      ctx.stroke();
    }

    const vessel = {
      x: plot.x + plot.w * 0.36,
      y: plot.y + 26,
      w: Math.min(148, plot.w * 0.26),
      h: plot.h - 66
    };
    ctx.strokeStyle = isDark ? 'rgba(226,232,240,0.34)' : 'rgba(15,23,42,0.18)';
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.roundRect(vessel.x, vessel.y, vessel.w, vessel.h, 18);
    ctx.stroke();

    const fluidH = vessel.h * displayLevel;
    const fluidY = vessel.y + vessel.h - fluidH;
    const wave = Math.sin(frame * 0.05) * 3;
    const grad = ctx.createLinearGradient(vessel.x, fluidY, vessel.x, vessel.y + vessel.h);
    grad.addColorStop(0, '#F3A7C8');
    grad.addColorStop(0.72, l7Color);
    grad.addColorStop(1, '#CC4E8D');
    ctx.save();
    ctx.beginPath();
    ctx.roundRect(vessel.x + 4, vessel.y + 4, vessel.w - 8, vessel.h - 8, 14);
    ctx.clip();
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.moveTo(vessel.x + 4, fluidY + wave);
    for (let i = 0; i <= 28; i++) {
      const x = vessel.x + 4 + (i / 28) * (vessel.w - 8);
      const y = fluidY + Math.sin(frame * 0.06 + i * 0.55) * (2 + pressure * 4);
      ctx.lineTo(x, y);
    }
    ctx.lineTo(vessel.x + vessel.w - 4, vessel.y + vessel.h - 4);
    ctx.lineTo(vessel.x + 4, vessel.y + vessel.h - 4);
    ctx.closePath();
    ctx.fill();
    ctx.restore();

    const thresholdY = vessel.y + vessel.h - threshold * vessel.h;
    ctx.strokeStyle = amber;
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 5]);
    ctx.beginPath();
    ctx.moveTo(vessel.x - 26, thresholdY);
    ctx.lineTo(vessel.x + vessel.w + 26, thresholdY);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = amber;
    ctx.font = '800 11px sans-serif';
    ctx.fillText('触发阈值', vessel.x + vessel.w + 32, thresholdY + 4);

    const phasePulse = ratio >= 1 ? 0.5 + Math.sin(frame * 0.12) * 0.5 : 0;
    if (phasePulse > 0) {
      ctx.strokeStyle = `rgba(244,114,182,${0.25 + phasePulse * 0.35})`;
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.arc(vessel.x + vessel.w / 2, vessel.y + vessel.h / 2, vessel.w * (0.7 + phasePulse * 0.22), 0, Math.PI * 2);
      ctx.stroke();
    }

    ctx.fillStyle = muted;
    ctx.font = '800 12px sans-serif';
    ctx.fillText(ratio >= 1 ? '状态：已跨过阈值，等待/执行表达相变。' : '状态：持续累积中，还没有跨过表达阈值。', plot.x, plot.y + plot.h - 12);

    ctx.fillStyle = isDark ? 'rgba(15,23,42,0.72)' : 'rgba(255,255,255,0.78)';
    ctx.strokeStyle = isDark ? 'rgba(148,163,184,0.18)' : 'rgba(15,23,42,0.10)';
    ctx.beginPath();
    ctx.roundRect(panel.x, panel.y, panel.w, panel.h, 14);
    ctx.fill();
    ctx.stroke();
    [
      ['当前压力', pressure.toFixed(3), pressure, l7Color],
      ['表达阈值', threshold.toFixed(3), threshold, amber],
      ['累计比例', `${Math.round(ratio * 100)}%`, Math.min(1, ratio), ratio >= 1 ? green : primary],
      ['当前模式', mode, ratio >= 1 ? 1 : 0.45, ratio >= 1 ? green : primary]
    ].forEach((row, idx) => {
      const y = panel.y + 34 + idx * 54;
      ctx.fillStyle = muted;
      ctx.font = '700 11px sans-serif';
      ctx.fillText(row[0], panel.x + 16, y);
      ctx.fillStyle = row[3];
      ctx.font = '900 18px monospace';
      ctx.fillText(row[1], panel.x + 16, y + 22);
      drawProgressBar(ctx, panel.x + 16, y + 30, panel.w - 32, row[2], row[3], isDark ? 'rgba(148,163,184,0.16)' : 'rgba(15,23,42,0.10)');
    });
  }

  function applyMoodTheme(emotion = sysState.emotion, theme = sysState.theme) {
    const root = document.documentElement;
    const base = theme?.base || WEBUI_STATE_CONTRACT.theme_base;
    const arousal = clamp01(emotion?.arousal ?? 0.3);
    const tension = clamp01(emotion?.tension ?? 0.1);
    const warmth = clamp01(emotion?.warmth ?? 0.55);
    const curiosity = clamp01(emotion?.curiosity ?? 0.45);
    const valence = normalizeValence(emotion?.valence ?? 0.5);
    let secondary = '#A7D8F3';
    let tertiary = '#BEE7A5';
    if (tension > 0.58) {
      secondary = '#F87171';
      tertiary = '#F6C177';
    } else if (arousal > 0.62) {
      secondary = '#F6C177';
      tertiary = '#A7D8F3';
    } else if (curiosity > 0.62) {
      secondary = '#8BD3FF';
      tertiary = '#C7B8FF';
    } else if (valence > 0.64 || warmth > 0.64) {
      secondary = '#BEE7A5';
      tertiary = '#A7D8F3';
    }
    const glowAlpha = Math.min(0.40, 0.18 + arousal * 0.10 + tension * 0.12 + warmth * 0.05);
    root.style.setProperty('--mood-primary', base);
    root.style.setProperty('--mood-secondary', secondary);
    root.style.setProperty('--mood-tertiary', tertiary);
    root.style.setProperty('--mood-glow', `rgba(243, 167, 200, ${glowAlpha.toFixed(2)})`);
    root.style.setProperty('--mood-wash', `rgba(243, 167, 200, ${(0.08 + warmth * 0.08).toFixed(2)})`);
    root.style.setProperty('--mood-border', `rgba(243, 167, 200, ${(0.22 + arousal * 0.16).toFixed(2)})`);
  }

  function currentGateSnapshot() {
    const raw = Array.isArray(sysState.gate?.surprise_history) ? sysState.gate.surprise_history : [];
    const lastRaw = raw.length ? raw[raw.length - 1] : (sysState.spine?.surprise ?? sysState.gate?.mean_surprise ?? 0);
    const surprise = clamp01(lastRaw);
    const route = String(sysState.spine?.route || (surprise > 0.45 ? 'full' : (surprise > 0.18 ? 'normal' : 'fast'))).toLowerCase();
    return { surprise, route };
  }

  function gateRouteLabel(route) {
    const map = { fast: "FAST 快速通道", normal: "NORMAL 标准通道", full: "FULL 深度通道", skip: "SKIP 空事件" };
    return map[route] || String(route || "?").toUpperCase();
  }

  function renderGateStatusStrip() {
    const snapshot = currentGateSnapshot();
    const cards = [
      { key: 'fast', label: 'FAST', color: 'var(--green)' },
      { key: 'normal', label: 'NORMAL', color: 'var(--blue)' },
      { key: 'full', label: 'FULL', color: 'var(--red)' }
    ];
    const total = Math.max(1, cards.reduce((sum, item) => sum + Number(sysState.route_stats?.[item.key] || 0), 0));
    return `
      <div class="gate-status-strip">
        ${cards.map(item => {
          const value = Number(sysState.route_stats?.[item.key] || 0);
          const pct = ((value / total) * 100).toFixed(1);
          return `
            <div class="gate-metric-card ${snapshot.route === item.key ? 'active' : ''}">
              <div class="gate-label"><span class="gate-dot" style="background:${item.color};color:${item.color}"></span>${item.label}</div>
              <div class="gate-value">${pct}%</div>
            </div>
          `;
        }).join('')}
        <div class="gate-live-readout">
          <div class="gate-live-title">LIVE GATE</div>
          <div class="gate-live-main">${gateRouteLabel(snapshot.route)} · surprise=${snapshot.surprise.toFixed(3)}</div>
          <div class="gate-live-hint">读法：曲线是惊讶度采样记录；低于 0.18 走 FAST，超过 0.18 走 NORMAL，超过 0.45 走 FULL。</div>
        </div>
      </div>
    `;
  }

  const personaTraitLabels = {
    warmth_bias: "温度基准",
    edge: "锐度",
    curiosity: "好奇",
    patience: "耐心",
    intimacy_gravity: "亲近引力",
    sovereignty_guard: "边界守护",
    extraversion: "外倾",
    neuroticism: "防备",
    agreeableness: "亲和",
    openness: "开放",
    conscientiousness: "自律"
  };

  function renderPersonaPanel() {
    const persona = sysState.persona || {};
    const profile = persona.profile || {};
    const traits = persona.traits || persona.personality?.traits || {};
    const traitEntries = Object.entries(traits).filter(([, value]) => Number.isFinite(Number(value))).slice(0, 6);
    const name = profile.name || persona.name || "Sylanne";
    const version = profile.version || persona.version || "4.0";
    const chips = traitEntries.length ? traitEntries.map(([key, value]) => {
      const pct = clamp01(value);
      return `
        <div class="persona-chip">
          <div class="persona-chip-label">
            <span>${escapeHtml(personaTraitLabels[key] || key)}</span>
            <span class="persona-chip-value">${pct.toFixed(2)}</span>
          </div>
          <div class="persona-meter"><div class="persona-meter-fill" style="width:${(pct * 100).toFixed(1)}%"></div></div>
        </div>
      `;
    }).join('') : `
      <div class="persona-chip">
        <div class="persona-chip-label"><span>等待后端人格画像</span><span class="persona-chip-value">--</span></div>
        <div class="persona-meter"><div class="persona-meter-fill" style="width:42%"></div></div>
      </div>
    `;
    return `
      <div class="persona-control-panel">
        <div class="persona-heading">
          <strong>当前 Bot 人格画像：${escapeHtml(name)} ${escapeHtml(version)}</strong>
          <small>来源：/api/state.persona · HGT 只展示载体状态，不在前端写死人格模板</small>
        </div>
        <div class="persona-chip-grid">${chips}</div>
      </div>
    `;
  }

  function updateSpineControls() {
    const controlsPanel = document.getElementById('vis-controls-panel');
    if (!controlsPanel) return;
    if (activeSpineStep === 2) {
      controlsPanel.innerHTML = renderGateStatusStrip();
      return;
    }
    if (activeSpineStep === 5) {
      controlsPanel.innerHTML = renderPersonaPanel();
      return;
    }
    controlsPanel.innerHTML = `
      <button class="btn btn-secondary" id="vis-action-btn">激活动画</button>
      <span style="font-size:0.8rem; color:var(--text-muted)" id="vis-status">运行流畅: 60 FPS</span>
    `;
    document.getElementById('vis-action-btn').onclick = () => {
      if (activeSpineStep === 6 && typeof triggerL6Perturbation === 'function') triggerL6Perturbation(0.85, true);
      else if (activeSpineStep === 7) sysState.emotion.expression_drive = 0.99;
      else alert("动画正在读取后端实时状态");
    };
  }

  // Custom step click
  stepCards.forEach(card => {
    card.addEventListener('click', () => {
      stepCards.forEach(c => c.classList.remove('active'));
      card.classList.add('active');
      activeSpineStep = parseInt(card.dataset.step);

      // Visual title mappings
      const stepTitles = {
        1: "L1 感知超空间编码网格 (HDC)",
        2: "L2 Predictive Coding 惊讶度门控",
        3: "L3 Void-Scar 耦合伤痕引擎",
        4: "L4 剪切波信号波幅演化 (Sheaf)",
        5: "L5 HGT 异构注意力矩阵",
        6: "L6 自创生身份形变流形",
        7: "L7 相变表达驱动压力"
      };
      const stepDescs = {
        1: "2048-bit 超二进制映射网格。收到消息时点位剧烈翻转并高亮共存区。",
        2: "根据信息 Hamming 惊喜度将计算分流至 Fast, Normal 或 Full 物理信道。",
        3: "不可逆代数（Scar）与心理学缺席漏洞（Void）重力牵拉演化图谱。",
        4: "在多维人际关系上同调剪切格子上，波幅能量随时间衰减的波动状况。",
        5: "异构注意力在 Layer-7 节点上的加权分布，可以通过模板改变人格倾向。",
        6: "32维刚性包络面受到大能量冲击时的波动、旋转角度（最高6°）及防御状态。",
        7: "相变容器热运动。表达欲跨越界限时触发跳变并发射模式代码（HINT/NORMAL/URGENT）。"
      };
      const badges = {
        1: "PERCEPTION", 2: "GATE ROUTE", 3: "VOID-SCAR ENGINE", 4: "RELATIONAL SHEAF", 5: "HGT ATTENTION", 6: "IDENTITY CORE", 7: "EXPRESSION MODE"
      };
      const colors = {
        1: "var(--l1-color)", 2: "var(--l2-color)", 3: "var(--l3-color)", 4: "var(--l4-color)", 5: "var(--l5-color)", 6: "var(--l6-color)", 7: "var(--l7-color)"
      };

      document.getElementById('vis-title').textContent = stepTitles[activeSpineStep];
      document.getElementById('vis-desc').textContent = stepDescs[activeSpineStep];

      const badge = document.getElementById('vis-badge');
      badge.textContent = badges[activeSpineStep];
      badge.style.color = colors[activeSpineStep];
      badge.style.borderColor = colors[activeSpineStep];
      badge.style.backgroundColor = colors[activeSpineStep].replace("var(", "rgba(").replace(")", ", 0.12)");

      updateSpineControls();

      initSpineCanvas();
    });
  });

  // HGT Easing templates
  let hgtTargetTemplate = null;
  window.setHGTTemplate = function(type) {
    const templates = {
      extrovert: [
        [0.85, 0.25, 0.35, 0.45, 0.25, 0.88, 0.75],
        [0.22, 0.92, 0.15, 0.35, 0.22, 0.48, 0.65],
        [0.34, 0.15, 0.88, 0.25, 0.42, 0.72, 0.32],
        [0.45, 0.35, 0.22, 0.95, 0.18, 0.68, 0.55],
        [0.25, 0.22, 0.45, 0.18, 0.82, 0.52, 0.88],
        [0.82, 0.45, 0.78, 0.65, 0.55, 0.95, 0.45],
        [0.68, 0.58, 0.32, 0.48, 0.75, 0.45, 0.85]
      ],
      neurotic: [
        [0.98, 0.78, 0.88, 0.12, 0.92, 0.35, 0.25],
        [0.82, 0.99, 0.75, 0.22, 0.85, 0.18, 0.32],
        [0.88, 0.72, 0.98, 0.15, 0.78, 0.25, 0.45],
        [0.18, 0.25, 0.15, 0.98, 0.32, 0.85, 0.88],
        [0.92, 0.85, 0.78, 0.32, 0.99, 0.45, 0.12],
        [0.35, 0.18, 0.25, 0.85, 0.45, 0.98, 0.78],
        [0.25, 0.32, 0.45, 0.88, 0.12, 0.78, 0.99]
      ],
      agreeable: [
        [0.45, 0.12, 0.22, 0.92, 0.15, 0.75, 0.82],
        [0.12, 0.42, 0.18, 0.88, 0.25, 0.65, 0.78],
        [0.25, 0.15, 0.55, 0.82, 0.32, 0.58, 0.68],
        [0.92, 0.85, 0.88, 0.99, 0.75, 0.95, 0.92],
        [0.15, 0.22, 0.32, 0.75, 0.45, 0.62, 0.85],
        [0.68, 0.58, 0.62, 0.92, 0.58, 0.88, 0.75],
        [0.82, 0.75, 0.68, 0.95, 0.85, 0.78, 0.92]
      ],
      void: [
        [0.95, 0.92, 0.75, 0.15, 0.82, 0.18, 0.22],
        [0.92, 0.99, 0.85, 0.22, 0.95, 0.25, 0.15],
        [0.78, 0.88, 0.92, 0.32, 0.75, 0.35, 0.42],
        [0.15, 0.25, 0.32, 0.45, 0.18, 0.52, 0.65],
        [0.85, 0.92, 0.78, 0.18, 0.99, 0.22, 0.35],
        [0.18, 0.25, 0.35, 0.52, 0.22, 0.45, 0.72],
        [0.22, 0.15, 0.42, 0.65, 0.35, 0.72, 0.68]
      ]
    };
    hgtTargetTemplate = templates[type];
  };

  function initSpineCanvas() {
    visCanvas = document.getElementById('vis-canvas');
    if (!visCanvas) return;

    ctx = visCanvas.getContext('2d');
    const rect = visCanvas.getBoundingClientRect();
    visCanvas.width = rect.width * window.devicePixelRatio;
    visCanvas.height = rect.height * window.devicePixelRatio;
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio);

    cancelAnimationFrame(animationFrameId);
    let frame = 0;

    // L6 Membrane Points State setup
    const numL6Points = 32;
    const l6Points = Array.from({length: numL6Points}, (_, i) => {
      const theta = (i * Math.PI * 2) / numL6Points;
      return {
        theta,
        baseR: 90,
        currentR: 90,
        targetR: 90,
        velocity: 0
      };
    });

    let l6Rotation = 0;
    let l6RotationVel = 0;

    // Physics perturbation for L6 Boundary
    triggerL6Perturbation = function(power, rotate) {
      const targetIdx = Math.floor(Math.random() * numL6Points);
      // Dent inward
      for (let i = -4; i <= 4; i++) {
        const idx = (targetIdx + i + numL6Points) % numL6Points;
        const dist = 1 - Math.abs(i) / 5;
        l6Points[idx].velocity -= power * 24 * dist;
      }
      if (rotate) {
        l6RotationVel += (Math.random() > 0.5 ? 1 : -1) * power * 8;
      }
    };

    // L3 Particle equations
    const mathParticles = [];

    // L7 Bubble particles
    const L7Bubbles = Array.from({length: 45}, () => {
      const vialW = 100;
      const vx = (rect.width - vialW) / 2;
      return {
        x: vx + 4 + Math.random() * (vialW - 8),
        y: rect.height + Math.random() * 40,
        r: 1 + Math.random() * 4,
        vy: 0.8 + Math.random() * 1.5,
        alpha: 0.1 + Math.random() * 0.5
      };
    });

    function draw() {
      if (activeTab !== "spine") return;

      const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
      ctx.clearRect(0, 0, rect.width, rect.height);

      // Backdrop Grid
      ctx.strokeStyle = isDark ? 'rgba(255,255,255,0.035)' : 'rgba(15,23,42,0.03)';
      ctx.lineWidth = 1;
      const gridSz = 40;
      for (let x = 0; x < rect.width; x += gridSz) {
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, rect.height); ctx.stroke();
      }
      for (let y = 0; y < rect.height; y += gridSz) {
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(rect.width, y); ctx.stroke();
      }

      frame++;

      if (activeSpineStep === 1) {
        drawL1Visualizer(ctx, rect, frame, isDark);
      }      else if (activeSpineStep === 2) {
        // L2 shows surprise samples only. Quiet turns stay near baseline; spikes mark routing events.
        const styles = getComputedStyle(document.documentElement);
        const l2Color = styles.getPropertyValue('--l2-color').trim() || '#fbbf24';
        const normalColor = styles.getPropertyValue('--blue').trim() || '#60a5fa';
        const fullColor = styles.getPropertyValue('--red').trim() || '#f87171';
        ctx.fillStyle = isDark ? '#ffffff' : '#0f172a';
        ctx.font = '700 12px monospace';
        ctx.fillText("L2 SURPRISE SAMPLES / ROUTE GATE", 20, 30);

        const plot = { x: 52, y: 58, w: rect.width - 104, h: rect.height - 112 };
        const fallbackPoints = [
          0.06, 0.07, 0.08, 0.07, 0.09, 0.10, 0.08, 0.11,
          0.34, 0.22, 0.14, 0.10, 0.08, 0.09, 0.12, 0.10,
          0.07, 0.08, 0.09, 0.11, 0.48, 0.30, 0.18, 0.12,
          0.09, 0.08, 0.10, 0.13, 0.16, 0.12, 0.09, 0.08,
          0.07, 0.09, 0.10, 0.26, 0.19, 0.13, 0.10, 0.09
        ];
        const rawPoints = Array.isArray(sysState.gate.surprise_history) ? sysState.gate.surprise_history : [];
        const sourcePoints = (rawPoints.length > 4 ? rawPoints : fallbackPoints)
          .slice(-56)
          .map(p => Math.max(0.02, Math.min(0.95, Number(p) || 0.02)));
        let ema = sourcePoints[0] || 0.08;
        const points = sourcePoints.map((p, idx) => {
          ema = idx === 0 ? p : ema * 0.58 + p * 0.42;
          return Math.max(0.02, Math.min(0.95, ema));
        });
        const xFor = idx => plot.x + (idx / Math.max(1, points.length - 1)) * plot.w;
        const yFor = value => plot.y + plot.h - value * plot.h;
        const latestRaw = sourcePoints[sourcePoints.length - 1] || points[points.length - 1] || 0.1;
        const latestSmoothed = points[points.length - 1] || latestRaw;
        const currentRoute = latestRaw > 0.45 ? 'FULL' : (latestRaw > 0.18 ? 'NORMAL' : 'FAST');

        // Minimal grid.
        ctx.strokeStyle = isDark ? 'rgba(148,163,184,0.12)' : 'rgba(15,23,42,0.08)';
        ctx.lineWidth = 1;
        for (let i = 0; i <= 6; i++) {
          const x = plot.x + (plot.w / 6) * i;
          ctx.beginPath();
          ctx.moveTo(x, plot.y);
          ctx.lineTo(x, plot.y + plot.h);
          ctx.stroke();
        }
        for (let i = 0; i <= 4; i++) {
          const y = plot.y + (plot.h / 4) * i;
          ctx.beginPath();
          ctx.moveTo(plot.x, y);
          ctx.lineTo(plot.x + plot.w, y);
          ctx.stroke();
        }

        // Threshold rules with clear labels.
        const fullY = yFor(0.45);
        const normY = yFor(0.18);
        [
          { y: fullY, color: fullColor, text: 'FULL 0.45' },
          { y: normY, color: normalColor, text: 'NORMAL 0.18' }
        ].forEach(rule => {
          ctx.strokeStyle = rule.color;
          ctx.globalAlpha = 0.58;
          ctx.lineWidth = 1;
          ctx.setLineDash([5, 8]);
          ctx.beginPath();
          ctx.moveTo(plot.x, rule.y);
          ctx.lineTo(plot.x + plot.w, rule.y);
          ctx.stroke();
          ctx.setLineDash([]);
          ctx.globalAlpha = 1;
          ctx.fillStyle = rule.color;
          ctx.font = '700 10px monospace';
          ctx.fillText(rule.text, plot.x + plot.w - 74, rule.y - 7);
        });

        // Subtle baseline fill. No scanning glow band: the thin cursor below marks the current sample.
        ctx.beginPath();
        points.forEach((p, idx) => {
          const x = xFor(idx);
          const y = yFor(p);
          if (idx === 0) ctx.moveTo(x, y);
          else {
            const prevX = xFor(idx - 1);
            const prevY = yFor(points[idx - 1]);
            ctx.quadraticCurveTo((prevX + x) / 2, prevY, x, y);
          }
        });
        ctx.lineTo(plot.x + plot.w, plot.y + plot.h);
        ctx.lineTo(plot.x, plot.y + plot.h);
        ctx.closePath();
        ctx.fillStyle = isDark ? 'rgba(251, 191, 36, 0.07)' : 'rgba(243, 167, 200, 0.10)';
        ctx.fill();

        // Main surprise sample line: deliberately calm, with spikes only where route thresholds are crossed.
        ctx.strokeStyle = l2Color;
        ctx.lineWidth = 2;
        ctx.lineJoin = 'round';
        ctx.lineCap = 'round';
        ctx.beginPath();
        points.forEach((p, idx) => {
          const x = xFor(idx);
          const y = yFor(p);
          if (idx === 0) ctx.moveTo(x, y);
          else {
            const prevX = xFor(idx - 1);
            const prevY = yFor(points[idx - 1]);
            ctx.quadraticCurveTo((prevX + x) / 2, prevY, x, y);
          }
        });
        ctx.stroke();

        // Mark meaningful spikes so it does not read as "everything is surprise".
        sourcePoints.forEach((p, idx) => {
          if (p < 0.18 && idx !== sourcePoints.length - 1) return;
          const x = xFor(idx);
          const y = yFor(points[idx]);
          ctx.fillStyle = p > 0.45 ? fullColor : (p > 0.18 ? normalColor : l2Color);
          ctx.beginPath();
          ctx.arc(x, y, p > 0.45 ? 4.2 : 3.2, 0, Math.PI * 2);
          ctx.fill();
        });

        const headX = xFor(points.length - 1);
        const headY = yFor(latestSmoothed);
        ctx.strokeStyle = l2Color;
        ctx.globalAlpha = 0.78;
        ctx.lineWidth = 1.5;
        ctx.setLineDash([3, 6]);
        ctx.beginPath();
        ctx.moveTo(headX, plot.y);
        ctx.lineTo(headX, plot.y + plot.h);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.globalAlpha = 1;

        ctx.fillStyle = l2Color;
        ctx.beginPath();
        ctx.arc(headX, headY, 5 + Math.sin(frame * 0.1) * 1.2, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = isDark ? '#cbd5e1' : '#334155';
        ctx.font = '800 12px monospace';
        ctx.fillText(`CURRENT SAMPLE ${currentRoute} / surprise=${latestRaw.toFixed(3)}`, plot.x, plot.y + plot.h + 30);
        ctx.font = '700 10px sans-serif';
        ctx.fillStyle = isDark ? 'rgba(203,213,225,0.72)' : 'rgba(51,65,85,0.72)';
        ctx.fillText("低位=预测稳定；尖峰=消息造成偏差，才会升级路由。竖线是当前采样点。", plot.x, plot.y + plot.h + 48);
      }
      else if (activeSpineStep === 3) {
        drawL3Visualizer(ctx, rect, frame, isDark);
      }
      else if (activeSpineStep === 4) {
        drawL4Visualizer(ctx, rect, frame, isDark);
      }      else if (activeSpineStep === 5) {
        // L5 HGT attention matrix heatmap
        ctx.fillStyle = isDark ? '#ffffff' : '#0f172a';
        ctx.font = '700 12px monospace';
        ctx.fillText("HETEROGENEOUS GRAPH TRANSFORMER MULTI-HEAD ATTENTION (7x7)", 20, 30);

        const matSize = 7;
        const cellW = Math.min(42, (rect.height - 100) / matSize);
        const startX = (rect.width - matSize * cellW) / 2;
        const startY = (rect.height - matSize * cellW) / 2 + 10;
        const labels = ["scar", "void", "bound", "pers", "surp", "expr", "ctx"];

        // Apply template interpolations if selected
        if (hgtTargetTemplate) {
          for (let i = 0; i < matSize; i++) {
            for (let j = 0; j < matSize; j++) {
              const diff = hgtTargetTemplate[i][j] - sysState.hgt_attention[i][j];
              sysState.hgt_attention[i][j] += diff * 0.08; // Smooth transition
            }
          }
        }

        for (let i = 0; i < matSize; i++) {
          // Axis tags
          ctx.fillStyle = isDark ? '#94a3b8' : '#64748b';
          ctx.font = 'bold 10px monospace';
          ctx.fillText(labels[i], startX - 44, startY + i * cellW + cellW/2 + 4);
          ctx.fillText(labels[i], startX + i * cellW + cellW/2 - 12, startY - 12);

          for (let j = 0; j < matSize; j++) {
            const w = sysState.hgt_attention[i][j];
            const noise = Math.sin(frame * 0.04 + i * 2 + j) * 0.05;
            const cellVal = Math.max(0, Math.min(1.0, w + noise));

            // Radiant blue/violet heatmap color
            ctx.fillStyle = `rgba(59, 130, 246, ${cellVal})`;
            ctx.fillRect(startX + i * cellW + 1, startY + j * cellW + 1, cellW - 2, cellW - 2);

            // Draw numbers
            ctx.fillStyle = cellVal > 0.55 ? '#000000' : (isDark ? '#ffffff' : '#0f172a');
            ctx.font = '8px monospace';
            ctx.fillText(cellVal.toFixed(2), startX + i * cellW + cellW/2 - 10, startY + j * cellW + cellW/2 + 4);
          }
        }
      }
      else if (activeSpineStep === 6) {
        // L6 Autopoietic Boundary Soft body physical simulator
        ctx.fillStyle = isDark ? '#ffffff' : '#0f172a';
        ctx.font = '700 12px monospace';
        ctx.fillText("32-DIMENSIONAL IDENTITY AUTOPOIETICS AND ROTATIONAL DRIFT", 20, 30);

        const cx = rect.width / 2;
        const cy = rect.height / 2;

        // Apply rotation velocity and spring forces to L6 Points
        l6Rotation += l6RotationVel;
        l6RotationVel *= 0.95; // Dampen rotation
        const currentRotationDrift = sysState.boundary.rotation * 0.8 + Math.sin(frame * 0.02) * 0.5;

        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate((l6Rotation + currentRotationDrift) * Math.PI / 180);

        // Soft body spring update
        l6Points.forEach((pt, i) => {
          const targetDist = pt.baseR * sysState.boundary.integrity;
          const force = (targetDist - pt.currentR) * 0.08; // Hooke's law
          pt.velocity += force;
          pt.velocity *= 0.92; // Dampen physics
          pt.currentR += pt.velocity;
        });

        // Draw glowing inner core
        const coreGrad = ctx.createRadialGradient(0, 0, 5, 0, 0, 35);
        coreGrad.addColorStop(0, 'rgba(52, 211, 153, 0.45)');
        coreGrad.addColorStop(0.7, 'rgba(52, 211, 153, 0.1)');
        coreGrad.addColorStop(1, 'rgba(52, 211, 153, 0)');
        ctx.fillStyle = coreGrad;
        ctx.beginPath();
        ctx.arc(0, 0, 40, 0, Math.PI * 2);
        ctx.fill();

        ctx.strokeStyle = 'var(--l6-color)';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(0, 0, 20, 0, Math.PI * 2);
        ctx.stroke();

        // Draw soft-body boundary envelope
        ctx.strokeStyle = 'var(--l6-color)';
        ctx.lineWidth = 3.5;
        ctx.fillStyle = isDark ? 'rgba(52, 211, 153, 0.04)' : 'rgba(5, 150, 105, 0.03)';
        ctx.beginPath();

        l6Points.forEach((pt, i) => {
          const x = Math.cos(pt.theta) * pt.currentR;
          const y = Math.sin(pt.theta) * pt.currentR;
          if (i === 0) ctx.moveTo(x, y);
          else {
            // Draw smooth bezier curves
            const prevPt = l6Points[i - 1];
            const xc = (Math.cos(prevPt.theta) * prevPt.currentR + x) / 2;
            const yc = (Math.sin(prevPt.theta) * prevPt.currentR + y) / 2;
            ctx.quadraticCurveTo(Math.cos(prevPt.theta) * prevPt.currentR, Math.sin(prevPt.theta) * prevPt.currentR, xc, yc);
          }
        });

        ctx.closePath();
        ctx.fill();
        ctx.stroke();

        // Draw diagnostic ticks on boundary ring
        ctx.strokeStyle = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.05)';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(0, 0, 120, 0, Math.PI * 2);
        ctx.stroke();

        ctx.restore();

        // Live telemetry panel from real boundary state.
        const telemetryX = 34;
        const telemetryY = rect.height - 104;
        const integrity = Number(sysState.boundary.integrity || 0);
        const entropy = Number(sysState.boundary.entropy || 0);
        const stability = Number(sysState.boundary.stability || integrity || 0);
        [
          ["完整性", integrity, "var(--green)"],
          ["稳定性", stability, "var(--l6-color)"],
          ["熵/扰动", entropy, "var(--red)"]
        ].forEach(([label, value, color], idx) => {
          const y = telemetryY + idx * 26;
          ctx.fillStyle = isDark ? 'rgba(15,23,42,0.72)' : 'rgba(255,255,255,0.72)';
          ctx.fillRect(telemetryX, y - 13, 210, 18);
          ctx.fillStyle = isDark ? '#94a3b8' : '#475569';
          ctx.font = '700 10px monospace';
          ctx.fillText(label.toUpperCase(), telemetryX + 8, y);
          ctx.fillStyle = color;
          ctx.fillRect(telemetryX + 82, y - 9, 96 * Math.max(0, Math.min(1, value)), 6);
          ctx.fillStyle = isDark ? '#e2e8f0' : '#0f172a';
          ctx.fillText(value.toFixed(3), telemetryX + 184, y);
        });

        ctx.fillStyle = isDark ? '#cbd5e1' : '#334155';
        ctx.font = '700 12px sans-serif';
        ctx.fillText('读法：绿色边界越圆越稳；红色熵升高代表外部冲击或身份边界扰动。', telemetryX, telemetryY + 90);

        const driftPulse = 0.5 + Math.sin(frame * 0.06) * 0.5;
        ctx.strokeStyle = `rgba(52, 211, 153, ${0.16 + driftPulse * 0.22})`;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(cx, cy, 140 + Math.sin(frame * 0.04) * 10 + entropy * 28, 0, Math.PI * 2);
        ctx.stroke();
      }
      else if (activeSpineStep === 7) {
        drawL7Visualizer(ctx, rect, frame, isDark);
      }      animationFrameId = requestAnimationFrame(draw);
    }

    draw();
  }

  // Real-time computation logs and memory pool renderers
  const termBox = document.getElementById('term-box');
  const logAutoScroll = document.getElementById('log-auto-scroll');
  const logClearBtn = document.getElementById('log-clear-btn');
  let visibleComputationLogs = [];

  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  function logTerminal(message, type = 'info', withTime = true) {
    if (!termBox) return;
    const line = document.createElement('div');
    line.className = `terminal-line terminal-${type}`;
    line.textContent = withTime ? `[${new Date().toLocaleTimeString()}] ${message}` : message;
    termBox.appendChild(line);
    if (!logAutoScroll || logAutoScroll.checked) {
      termBox.scrollTop = termBox.scrollHeight;
    }
  }

  function compactValue(value) {
    if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(3);
    if (typeof value === 'boolean') return value ? 'true' : 'false';
    if (Array.isArray(value)) return `[${value.map(compactValue).join(', ')}]`;
    if (value && typeof value === 'object') {
      return Object.entries(value).slice(0, 5).map(([k, v]) => `${k}=${compactValue(v)}`).join(', ') || '{}';
    }
    return String(value ?? '-');
  }

  function totalTimingMs(entry) {
    const timing = entry?.timing_ns || entry?.timing || {};
    const totalNs = Object.values(timing).reduce((sum, value) => {
      const n = Array.isArray(value) ? value[value.length - 1] : value;
      return sum + (Number(n) || 0);
    }, 0);
    return totalNs > 0 ? totalNs / 1e6 : 0;
  }

  function renderComputationLogs(entries, source = 'live') {
    visibleComputationLogs = Array.isArray(entries) ? entries.slice(-50) : [];
    const latestLayers = visibleComputationLogs[visibleComputationLogs.length - 1]?.layers;
    if (latestLayers && typeof latestLayers === 'object') {
      sysState.layers = { ...(sysState.layers || {}), ...latestLayers };
    }
    if (!termBox) return;
    termBox.innerHTML = '';

    if (visibleComputationLogs.length === 0) {
      logTerminal('[System] 等待插件计算日志...', 'info', false);
      logTerminal('[System] 每条新消息会按 L1-L7、assessor、memory、timing 展开。', 'system', false);
      logTerminal(source === 'offline'
        ? '[System] 当前是离线预览，后端连上后会自动切换为真实日志。'
        : '[System] 已连接日志端点，尚未捕获到计算条目。', 'system', false);
      setText('log-entry-count', '0');
      setText('log-avg-time', '--ms');
      setText('log-route-fast', 'Fast: 0');
      setText('log-route-normal', 'Normal: 0');
      setText('log-route-full', 'Full: 0');
      return;
    }

    const routeCounts = { fast: 0, normal: 0, full: 0 };
    let timingSum = 0;
    let timedCount = 0;
    const layerLabels = {
      L1_HDC: 'L1 HDC',
      L2_Gate: 'L2 Gate',
      L3_VoidScar: 'L3 Void-Scar',
      L4_Sheaf: 'L4 Sheaf',
      L5_HGT: 'L5 HGT',
      L6_Boundary: 'L6 Boundary',
      L7_Expression: 'L7 Expression'
    };

    visibleComputationLogs.forEach((entry, index) => {
      const ts = entry.ts ? new Date(entry.ts * 1000).toLocaleTimeString() : new Date().toLocaleTimeString();
      const route = String(entry.route || entry.layers?.L2_Gate?.route || '?').toLowerCase();
      if (routeCounts[route] !== undefined) routeCounts[route]++;
      const surprise = Number(entry.surprise ?? entry.layers?.L2_Gate?.surprise ?? 0);
      if (Number.isFinite(surprise) && surprise > 0) {
        sysState.gate.mean_surprise = sysState.gate.mean_surprise * 0.85 + surprise * 0.15;
        sysState.gate.surprise_history.push(surprise);
        sysState.gate.surprise_history = sysState.gate.surprise_history.slice(-60);
      }
      if (routeCounts[route] !== undefined) sysState.route_stats[route] = Math.max(sysState.route_stats[route] || 0, routeCounts[route]);
      if (entry.layers?.L6_Boundary?.stability !== undefined) {
        sysState.boundary.stability = Number(entry.layers.L6_Boundary.stability) || sysState.boundary.stability;
      }
      if (entry.layers?.L7_Expression?.drive !== undefined) {
        sysState.expression.pressure = Number(entry.layers.L7_Expression.drive) || sysState.expression.pressure;
        sysState.emotion.expression_drive = sysState.expression.pressure;
      }
      const ms = totalTimingMs(entry);
      if (ms > 0) {
        timingSum += ms;
        timedCount++;
      }

      logTerminal(`[#${index + 1} ${ts}] session=${entry.session || currentSession} route=${route.toUpperCase()} surprise=${compactValue(entry.surprise)} text="${entry.text || ''}"`, 'user', false);
      const layers = entry.layers || {};
      Object.keys(layerLabels).forEach(key => {
        const payload = layers[key] || {};
        const type = key === 'L2_Gate' || key === 'L7_Expression' ? 'warn' : 'system';
        logTerminal(`  ${layerLabels[key]} -> ${compactValue(payload)}`, type, false);
      });
      if (entry.assessor) {
        logTerminal(`  Assessor -> ${compactValue(entry.assessor)}`, 'info', false);
      }
      if (ms > 0) {
        logTerminal(`  Total -> ${ms.toFixed(3)} ms`, 'info', false);
      }
    });

    setText('log-entry-count', String(visibleComputationLogs.length));
    setText('log-avg-time', timedCount ? `${(timingSum / timedCount).toFixed(3)}ms` : '--ms');
    setText('log-route-fast', `Fast: ${routeCounts.fast}`);
    setText('log-route-normal', `Normal: ${routeCounts.normal}`);
    setText('log-route-full', `Full: ${routeCounts.full}`);
  }

  function buildOfflineComputationLogs() {
    const now = Date.now() / 1000;
    return [
      {
        ts: now - 16,
        session: currentSession,
        text: '离线预览：普通问候',
        route: 'fast',
        surprise: sysState.gate.mean_surprise,
        layers: {
          L1_HDC: { density: 0.514 },
          L2_Gate: { surprise: sysState.gate.mean_surprise, route: 'fast' },
          L3_VoidScar: { scars: sysState.scars.length, voids: sysState.voids.length, coherence: 0.72 },
          L4_Sheaf: { relation_nodes: sysState.sheaf_nodes.length, transfer: 0.31 },
          L5_HGT: { decision: [0.12, 0.03, 0.01, 0.08] },
          L6_Boundary: { stability: sysState.boundary.stability },
          L7_Expression: { drive: sysState.emotion.expression_drive, should_express: false }
        },
        assessor: { valence: 0.31, arousal: 0.12, intent: '闲聊' },
        timing_ns: { perception: 122000, gate: 26000, ssm: 840000, memory: 2120000, boundary: 91000, expression: 16000 }
      },
      {
        ts: now - 5,
        session: currentSession,
        text: '离线预览：情绪强输入',
        route: 'full',
        surprise: 0.68,
        layers: {
          L1_HDC: { density: 0.537 },
          L2_Gate: { surprise: 0.68, route: 'full' },
          L3_VoidScar: { scars: sysState.scars.length + 1, voids: sysState.voids.length, coherence: 0.66 },
          L4_Sheaf: { relation_nodes: 3, conflict_gradient: 0.44 },
          L5_HGT: { decision: [0.22, 0.15, 0.19, 0.41] },
          L6_Boundary: { stability: Math.max(0, sysState.boundary.stability - 0.08) },
          L7_Expression: { drive: 0.82, should_express: true }
        },
        assessor: { valence: -0.24, arousal: 0.56, intent: '安抚/澄清' },
        timing_ns: { perception: 131000, gate: 31000, ssm: 1180000, memory: 4120000, boundary: 142000, expression: 21000 }
      }
    ];
  }

  async function syncComputationLogs() {
    try {
      const res = await apiFetch(`/api/computation_logs?limit=50&session=${encodeURIComponent(currentSession)}`, { cache: 'no-store' });
      if (!res.ok) throw new Error('logs offline');
      const data = await res.json();
      renderComputationLogs(data.logs || [], 'live');
    } catch (e) {
      if (useOfflinePreviewData()) {
        renderComputationLogs(buildOfflineComputationLogs(), 'offline');
      } else {
        renderComputationLogs([], 'unavailable');
      }
    }
  }

  function memoryScore(record) {
    if (record.clarity !== undefined) return Math.max(0, Math.min(1, Number(record.clarity) || 0));
    const depth = Number(record.depth ?? record.weight ?? 0) || 0;
    const confidence = Number(record.confidence ?? 0.35) || 0;
    const recalls = Math.min(1, (Number(record.recall_count ?? record.recalls ?? 0) || 0) / 5);
    const evidence = Math.min(1, (Number(record.evidence_count ?? 1) || 1) / 4);
    const interference = Number(record.interference ?? 0) || 0;
    return Math.max(0, Math.min(1, depth * 0.45 + confidence * 0.25 + recalls * 0.2 + evidence * 0.1 - interference * 0.15));
  }

  function memoryImpressionDepth(record) {
    const raw = record.impression_depth ?? record.depth ?? record.weight ?? record.clarity ?? record.strength ?? record.score ?? memoryScore(record);
    return Math.max(0, Math.min(1, Number(raw) || 0));
  }

  function sortMemoriesByDepth(items) {
    return (Array.isArray(items) ? items.slice() : []).sort((a, b) => {
      const byDepth = memoryImpressionDepth(b) - memoryImpressionDepth(a);
      if (Math.abs(byDepth) > 0.0001) return byDepth;
      return memoryScore(b) - memoryScore(a);
    });
  }

  function memoryTemperature(record) {
    if (record.emotion_weight !== undefined) return Math.max(0, Math.min(1, (Number(record.emotion_weight) + 1) / 2));
    const sig = record.emotional_signature || record.emotion || {};
    const arousal = Math.abs(Number(sig.arousal ?? sig.tension ?? 0.35) || 0.35);
    const warmth = Math.abs(Number(sig.warmth ?? sig.valence ?? 0.45) || 0.45);
    return Math.max(0, Math.min(1, (arousal + warmth) / 2));
  }

  function renderMemoryItem(record, pool) {
    const depthScore = memoryImpressionDepth(record);
    const score = Math.max(depthScore, Math.max(0, Math.min(1, Number(record.weight ?? memoryScore(record)) || 0)));
    const temp = Number(record.temperature ?? memoryTemperature(record));
    const title = record.summary || record.label || record.text || '未命名记忆片段';
    const body = record.text && record.text !== title ? record.text : (record.summary || '');
    const embedding = record.has_embedding ?? Boolean(record.semantic_embedding?.length || record.embedding?.length || record.embedding_provider_id);
    const recallCount = Number(record.recall_count ?? record.recalls ?? 0) || 0;
    const created = record.event_local_time || (record.created_at ? new Date(record.created_at * 1000).toLocaleString() : '本地预览');
    const badgeClass = pool === 'cold' ? 'badge-purple' : (pool === 'warm' ? 'badge-blue' : 'badge-amber');
    const poolLabel = pool === 'cold' ? 'L3' : (pool === 'warm' ? 'L2' : 'L1');
    return `
      <div class="memory-item">
        <div class="memory-item-title">
          <span class="badge ${badgeClass}">${poolLabel} ${depthScore.toFixed(2)}</span>
          <span style="font-size:0.72rem;color:var(--text-muted);">${escapeHtml(created)}</span>
        </div>
        <div class="memory-item-text">${escapeHtml(title)}</div>
        ${body && body !== title ? `<div style="font-size:0.78rem;color:var(--text-muted);line-height:1.5;margin-top:6px;">${escapeHtml(body).slice(0, 220)}</div>` : ''}
        <div class="memory-meter"><div class="memory-meter-fill" style="width:${Math.round(depthScore * 100)}%; opacity:${0.55 + temp * 0.45};"></div></div>
        <div class="memory-item-meta">
          <span>印象深度 ${depthScore.toFixed(2)}</span>
          <span>召回 ${recallCount}</span>
          <span>情绪温度 ${temp.toFixed(2)}</span>
          ${embedding ? '<span>已向量化</span>' : ''}
        </div>
      </div>
    `;
  }

  function buildOfflineMemoryPools() {
    const records = [
      { summary: '用户希望 WebUI 显示插件内部计算日志，而不是本地仿真输入框。', text: '实时日志需要展示 L1-L7、assessor、memory 与 timing。', depth: 0.62, confidence: 0.88, recall_count: 2, evidence_count: 3, session_key: currentSession, emotional_signature: { arousal: 0.32, warmth: 0.54 }, semantic_embedding: [0.1] },
      { summary: '记忆栏目需要拆成两个池：短时热池和长期沉淀池。', text: '热池看最近消息，长期池看高权重/多次召回的记忆。', depth: 0.68, confidence: 0.9, recall_count: 3, evidence_count: 4, session_key: currentSession, emotional_signature: { arousal: 0.28, warmth: 0.58 }, semantic_embedding: [0.2] },
      { summary: '配置页曾因 tab-pane 属性引号异常被误判为消失。', text: '实际问题是弯引号导致 CSS/JS 无法正确识别新增页签。', depth: 0.44, confidence: 0.82, recall_count: 1, evidence_count: 2, session_key: currentSession, emotional_signature: { tension: 0.46, warmth: 0.22 } }
    ];
    return {
      hot: sortMemoriesByDepth(records),
      long_term: sortMemoriesByDepth(records.filter(r => memoryScore(r) >= 0.5)),
      summary: {
        total: records.length,
        embedded: records.filter(r => r.semantic_embedding?.length).length,
        avg_weight: records.reduce((s, r) => s + memoryScore(r), 0) / records.length,
        avg_temperature: records.reduce((s, r) => s + memoryTemperature(r), 0) / records.length
      }
    };
  }

  function buildEmptyMemoryPools() {
    return {
      hot: [],
      warm: [],
      long_term: [],
      cold: [],
      summary: {
        total: 0,
        l1_count: 0,
        l2_count: 0,
        l3_node_count: 0,
        l3_edge_count: 0,
        embedded: 0,
        avg_weight: 0,
        avg_temperature: 0.5
      }
    };
  }

  function useOfflinePreviewData() {
    return IS_FILE_PREVIEW;
  }

  function memoryFallbackPayload() {
    return useOfflinePreviewData() ? buildOfflineMemoryPools() : buildEmptyMemoryPools();
  }

  function offlineColdGraphNodes() {
    return [
      { id: 'node-webui-observe', label: 'WebUI 实时可观测性', type: 'topic', temporal_type: 'evolving', emotion_weight: 0.56, clarity: 0.82, recall_count: 3, text: '动画、日志、耗时和人格色彩都要读取实时状态。', session_key: currentSession },
      { id: 'node-memory-system', label: '三层记忆架构', type: 'topic', temporal_type: 'permanent', emotion_weight: 0.48, clarity: 0.76, recall_count: 1, text: 'L1 Hot、L2 Warm、L3 Cold Graph。', session_key: currentSession }
    ];
  }

  function normalizeMemoryPayload(data) {
    const fallback = memoryFallbackPayload();
    const layers = data?.layers || {};
    const hotRaw = Array.isArray(layers.l1_hot?.items) ? layers.l1_hot.items : (Array.isArray(data?.hot) ? data.hot : fallback.hot);
    const warmRaw = Array.isArray(layers.l2_warm?.items) ? layers.l2_warm.items : (Array.isArray(data?.warm) ? data.warm : (Array.isArray(data?.long_term) ? data.long_term : fallback.long_term));
    const coldRaw = Array.isArray(layers.l3_cold?.nodes) ? layers.l3_cold.nodes : (Array.isArray(data?.cold) ? data.cold : (useOfflinePreviewData() ? offlineColdGraphNodes() : (fallback.cold || [])));
    const hot = sortMemoriesByDepth(hotRaw);
    const warm = sortMemoriesByDepth(warmRaw);
    const cold = sortMemoriesByDepth(coldRaw);
    const summary = {
      ...(fallback.summary || {}),
      ...(data?.summary || {}),
      total: data?.summary?.total ?? hot.length + warm.length + cold.length,
      l1_count: data?.summary?.l1_count ?? hot.length,
      l2_count: data?.summary?.l2_count ?? warm.length,
      l3_node_count: data?.summary?.l3_node_count ?? cold.length,
      l3_edge_count: data?.summary?.l3_edge_count ?? layers.l3_cold?.edge_count ?? 0
    };
    return { hot, warm, cold, summary };
  }

  function renderMemoryPools(data) {
    const { hot, warm, cold, summary } = normalizeMemoryPayload(data);
    const hotList = document.getElementById('memory-hot-list');
    const warmList = document.getElementById('memory-warm-list');
    const coldList = document.getElementById('memory-cold-list');
    if (hotList) hotList.innerHTML = hot.length ? hot.map(item => renderMemoryItem(item, 'hot')).join('') : '<div class="terminal-system">暂无 L1 工作记忆。</div>';
    if (warmList) warmList.innerHTML = warm.length ? warm.map(item => renderMemoryItem(item, 'warm')).join('') : '<div class="terminal-system">暂无 L2 召回记忆。</div>';
    if (coldList) coldList.innerHTML = cold.length ? cold.map(item => renderMemoryItem(item, 'cold')).join('') : '<div class="terminal-system">暂无 L3 图记忆节点。</div>';
    setText('mem-total-count', String(summary.total ?? hot.length + warm.length + cold.length));
    setText('mem-embed-count', String(summary.embedded ?? 0));
    setText('mem-avg-weight', Number(summary.avg_weight ?? 0).toFixed(2));
    setText('mem-avg-temp', Number(summary.avg_temperature ?? 0.5).toFixed(2));
  }

  async function syncMemoryPools() {
    try {
      const res = await apiFetch(`/api/memory_pools?limit=50&session=${encodeURIComponent(currentSession)}`, { cache: 'no-store' });
      if (!res.ok) throw new Error('memory offline');
      const data = await res.json();
      renderMemoryPools(data);
    } catch (e) {
      renderMemoryPools(memoryFallbackPayload());
    }
  }

  if (logClearBtn) {
    logClearBtn.addEventListener('click', () => {
      if (termBox) termBox.innerHTML = '';
      setText('log-entry-count', '0');
      logTerminal('[System] 当前视图已清空，下一次轮询会重新拉取最近日志。', 'system', false);
    });
  }

  // Background slow ticker to make visualizer grids pulse/feel alive
  setInterval(() => {
    if (hasLiveState) {
      renderMonitor();
      return;
    }
    if (!IS_FILE_PREVIEW) {
      renderMonitor();
      return;
    }
    // Decay values slowly
    sysState.gate.mean_surprise = sysState.gate.mean_surprise * 0.94 + Math.random() * 0.05 * 0.06;
    sysState.boundary.integrity = Math.min(1.0, sysState.boundary.integrity + 0.006);
    sysState.boundary.rotation = Math.max(0.0, sysState.boundary.rotation - 0.08);
    sysState.boundary.entropy = Math.max(0.1, sysState.boundary.entropy * 0.97);

    sysState.emotion.arousal = Math.max(0.1, sysState.emotion.arousal * 0.97);
    sysState.emotion.tension = Math.max(0.04, sysState.emotion.tension * 0.94);
    sysState.emotion.expression_drive = Math.max(0.04, sysState.emotion.expression_drive * 0.97);
    sysState.expression.pressure = sysState.emotion.expression_drive;
    sysState.expression.ratio = sysState.expression.pressure / sysState.expression.threshold;

    if (sysState.expression.ratio < 1.0) {
      sysState.expression.mode = "silent";
    }

    renderMonitor();
  }, 2500);

  let currentSession = "default";

  // Bind session selector events. Native select remains as compatibility fallback.
  const sessionSelector = document.getElementById('session-selector');
  const sessionPicker = document.getElementById('session-picker');
  const sessionPickerButton = document.getElementById('session-picker-button');
  const sessionPickerMenu = document.getElementById('session-picker-menu');

  function sessionLabel(session) {
    return session === "default" ? "总览" : session;
  }

  function sessionHint(session) {
    return session === "default" ? "汇总入口" : "跟踪会话";
  }

  function closeSessionPicker() {
    if (!sessionPicker || !sessionPickerButton) return;
    sessionPicker.classList.remove('open');
    sessionPickerButton.setAttribute('aria-expanded', 'false');
  }

  function openSessionPicker() {
    if (!sessionPicker || !sessionPickerButton) return;
    sessionPicker.classList.add('open');
    sessionPickerButton.setAttribute('aria-expanded', 'true');
  }

  function applySessionChange(nextSession) {
    if (!nextSession || nextSession === currentSession) {
      closeSessionPicker();
      return;
    }
    currentSession = nextSession;
    renderSessionPicker(Array.from(sessionSelector?.options || []).map(o => o.value), currentSession);
    closeSessionPicker();
    if (contentPane) {
      contentPane.classList.remove('is-switching');
      void contentPane.offsetWidth;
      contentPane.classList.add('is-switching');
    }
    syncServerState();
    syncComputationLogs();
    syncMemoryPools();
  }

  function renderSessionPicker(values = [], selected = currentSession) {
    const sessions = Array.from(new Set((values.length ? values : [selected || "default"]).filter(Boolean)));
    const chosen = sessions.includes(selected) ? selected : (sessions[0] || "default");
    currentSession = chosen;
    if (sessionSelector) {
      const currentOpts = Array.from(sessionSelector.options).map(o => o.value);
      const matches = currentOpts.length === sessions.length && currentOpts.every(v => sessions.includes(v));
      if (!matches) {
        sessionSelector.innerHTML = sessions.map(session => `
          <option value="${escapeHtml(session)}">${escapeHtml(sessionLabel(session))}</option>
        `).join('');
      }
      sessionSelector.value = chosen;
    }
    if (sessionPickerButton) {
      sessionPickerButton.textContent = sessionLabel(chosen);
      sessionPickerButton.title = chosen === "default" ? "总览" : chosen;
    }
    if (sessionPickerMenu) {
      sessionPickerMenu.innerHTML = sessions.map(session => `
        <button type="button" class="session-picker-option ${session === chosen ? 'active' : ''}" data-session="${escapeHtml(session)}" role="option" aria-selected="${session === chosen ? 'true' : 'false'}">
          <span>${escapeHtml(sessionLabel(session))}</span>
          <small>${escapeHtml(sessionHint(session))}</small>
        </button>
      `).join('');
    }
  }

  renderSessionPicker(["default"], "default");

  sessionSelector?.addEventListener('change', (e) => {
    applySessionChange(e.target.value);
  });

  sessionPickerButton?.addEventListener('click', () => {
    if (sessionPicker?.classList.contains('open')) closeSessionPicker();
    else openSessionPicker();
  });

  sessionPickerMenu?.addEventListener('click', (event) => {
    const option = event.target.closest('.session-picker-option');
    if (!option) return;
    applySessionChange(option.dataset.session || "default");
  });

  document.addEventListener('click', (event) => {
    if (!sessionPicker || sessionPicker.contains(event.target)) return;
    closeSessionPicker();
  });

  // Sync state with server API fallbacks
  async function syncServerState() {
    try {
      const res = await apiFetch(`/api/state?session=${encodeURIComponent(currentSession)}`, { cache: 'no-store' });
      if (!res.ok) throw new Error("Offline");
      const data = await res.json();
      hasLiveState = true;

      sysState.emotion = { ...sysState.emotion, ...(data.emotion || {}) };
      sysState.gate = { ...sysState.gate, ...(data.gate || {}) };
      sysState.spine = { ...sysState.spine, ...(data.spine || {}) };
      sysState.layers = {
        ...(sysState.layers || {}),
        ...(data.layers || {}),
        ...(data.spine?.layers || {})
      };
      sysState.persona = { ...sysState.persona, ...(data.persona || {}) };
      sysState.theme = { ...sysState.theme, ...(data.theme || {}) };
      const history = Array.isArray(data.gate?.history) ? data.gate.history : [];
      if (history.length) {
        sysState.gate.surprise_history = history.map(item => {
          if (typeof item === "number") return item;
          return Number(item.surprise ?? item.value ?? item.mean_surprise ?? 0);
        }).filter(value => Number.isFinite(value)).slice(-60);
      } else if (data.spine?.surprise !== undefined) {
        const surprise = Number(data.spine.surprise);
        if (Number.isFinite(surprise)) {
          sysState.gate.surprise_history.push(surprise);
          sysState.gate.surprise_history = sysState.gate.surprise_history.slice(-60);
        }
      }
      sysState.route_stats = data.route_stats || sysState.route_stats;
      sysState.boundary = data.boundary || sysState.boundary;
      sysState.expression = { ...sysState.expression, ...(data.expression || {}) };
      if (sysState.expression.pressure === undefined && data.expression?.drive !== undefined) {
        sysState.expression.pressure = data.expression.drive;
      }
      sysState.expression.ratio = sysState.expression.pressure / Math.max(0.01, sysState.expression.threshold || 0.6);
      sysState.timing = data.timing || sysState.timing;
      if (data.spine?.hgt_decision && Array.isArray(data.spine.hgt_decision)) {
        const row = data.spine.hgt_decision.map(value => Math.max(0, Math.min(1, Number(value) || 0)));
        if (row.length) {
          sysState.hgt_attention[0] = sysState.hgt_attention[0].map((value, idx) => row[idx % row.length] ?? value);
        }
      }
      if (data.memory?.layers || data.memory?.records || data.memory?.hot || data.memory?.warm || data.memory?.cold || data.memory?.long_term) {
        renderMemoryPools(data.memory);
      }

      setConnectionStatus("live", lastTransportMode === "bridge" ? "实时后端 (插件桥)" : "实时后端已连接");

      if (data.sessions && data.sessions.length > 0) {
        const currentOpts = Array.from(sessionSelector.options).map(o => o.value);
        const matches = currentOpts.length === data.sessions.length && currentOpts.every(v => data.sessions.includes(v));
        if (!matches) {
          sessionSelector.innerHTML = data.sessions.map(s => `<option value="${escapeHtml(s)}" ${s === data.current_session ? 'selected' : ''}>${escapeHtml(sessionLabel(s))}</option>`).join('');
        }
        if (data.current_session) {
          currentSession = data.current_session;
          sessionSelector.value = data.current_session;
        }
        renderSessionPicker(data.sessions, currentSession);
      }

      renderMonitor();
    } catch (e) {
      hasLiveState = false;
      if (window.location.protocol === "file:") {
        setConnectionStatus("preview", "本地预览 (等待后端)");
      } else if (lastTransportMode === "bridge") {
        setConnectionStatus("bridge", "插件桥在线 (状态未返回)");
      } else {
        setConnectionStatus("offline", "后端未响应");
      }
    }
  }

  // Initial runs
  renderMonitor();
  syncSettings();
  renderComputationLogs([], useOfflinePreviewData() ? 'offline' : 'unavailable');
  renderMemoryPools(memoryFallbackPayload());
  syncServerState();
  syncComputationLogs();
  syncMemoryPools();
  setInterval(syncServerState, 3000);
  setInterval(syncComputationLogs, 3000);
  setInterval(syncMemoryPools, 5000);

  </script>
</body>
</html>


"""

