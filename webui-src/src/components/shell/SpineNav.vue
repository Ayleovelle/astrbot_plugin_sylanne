<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { useI18n } from '../../composables/useI18n'

const { t } = useI18n()

// Evolved "spine": left rail that keeps the accent-line + node identity but is a
// real, keyboard-accessible nav. Each node now carries a line-icon (scannable)
// plus a legible label, and the active node truly glows (bioluminescent).
const items: { to: string; key: string; icon: string }[] = [
  { to: '/monitor', key: 'nav.monitor', icon: '<path d="M2 10h3l2-5 3 10 2-5h6"/>' },
  {
    to: '/cognition',
    key: 'nav.cognition',
    icon: '<circle cx="10" cy="10" r="6.5"/><circle cx="10" cy="10" r="1.6" fill="currentColor" stroke="none"/>',
  },
  {
    to: '/config',
    key: 'nav.config',
    icon: '<path d="M4 6h12M4 10h12M4 14h12"/><circle cx="8" cy="6" r="1.9" fill="currentColor" stroke="none"/><circle cx="13" cy="10" r="1.9" fill="currentColor" stroke="none"/><circle cx="7" cy="14" r="1.9" fill="currentColor" stroke="none"/>',
  },
  { to: '/logs', key: 'nav.logs', icon: '<path d="M4 6l3 2-3 2M10 10h6M4 14h12"/>' },
  {
    to: '/memory',
    key: 'nav.memory',
    icon: '<path d="M10 3l7 3.5-7 3.5-7-3.5z"/><path d="M3 10l7 3.5 7-3.5M3 13.5l7 3.5 7-3.5"/>',
  },
  { to: '/personality', key: 'nav.personality', icon: '<path d="M10 2l6.9 4v8L10 18l-6.9-4V6z"/>' },
  {
    to: '/life',
    key: 'nav.life',
    icon: '<path d="M10 2c3 3.5 5 5 5 8a5 5 0 11-10 0c0-3 2-4.5 5-8z"/>',
  },
  {
    to: '/admin',
    key: 'nav.admin',
    icon: '<path d="M10 2l6 2.2v5.3c0 4-2.7 6.2-6 7.3-3.3-1.1-6-3.3-6-7.3V4.2z"/>',
  },
]
</script>

<template>
  <nav class="spine" aria-label="primary">
    <div class="spine-line" aria-hidden="true" />
    <RouterLink
      v-for="it in items"
      :key="it.to"
      :to="it.to"
      class="node"
      active-class="active"
    >
      <span class="node-mark">
        <!-- eslint-disable-next-line vue/no-v-html -- static, trusted icon markup -->
        <svg
          class="icon"
          viewBox="0 0 20 20"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
          v-html="it.icon"
        />
      </span>
      <span class="label">{{ t(it.key) }}</span>
    </RouterLink>
  </nav>
</template>

<style scoped>
.spine {
  position: relative;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: space-around;
  align-items: center;
  padding: var(--space-9) 0;
  border-right: 1px solid var(--card-border);
  background: linear-gradient(180deg, rgba(184, 138, 158, 0.05), transparent 40%);
}
.spine-line {
  position: absolute;
  top: 10%;
  bottom: 10%;
  left: 50%;
  width: 2px;
  transform: translateX(-50%);
  background: linear-gradient(
    180deg,
    transparent 2%,
    var(--accent) 14%,
    var(--accent) 86%,
    transparent 98%
  );
  opacity: 0.28;
  pointer-events: none;
}
.node {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  text-decoration: none;
  color: var(--text-muted);
  transition: color var(--dur-fast) ease;
  outline: none;
}
.node-mark {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  border: 1px solid transparent;
  background: var(--bg);
  transition:
    transform var(--dur-fast) ease,
    border-color var(--dur-fast) ease,
    box-shadow var(--dur-fast) ease;
}
.icon {
  width: 19px;
  height: 19px;
  opacity: 0.75;
  transition: opacity var(--dur-fast) ease, filter var(--dur-fast) ease;
}
.label {
  font-size: 11px;
  letter-spacing: 1px;
  text-transform: uppercase;
  opacity: 0.7;
  transition: opacity var(--dur-fast) ease;
}
.node:hover {
  color: var(--text);
}
.node:hover .node-mark {
  transform: translateY(-1px);
  border-color: rgba(184, 138, 158, 0.35);
}
.node:hover .icon,
.node:hover .label {
  opacity: 1;
}
.node:focus-visible .node-mark {
  box-shadow: var(--ring-focus);
}
.node.active {
  color: var(--accent);
}
.node.active .node-mark {
  border-color: var(--accent);
  background: var(--glow);
  box-shadow: var(--glow-strong);
}
.node.active .icon {
  opacity: 1;
  filter: drop-shadow(0 0 5px rgba(184, 138, 158, 0.7));
}
.node.active .label {
  opacity: 1;
}
</style>
