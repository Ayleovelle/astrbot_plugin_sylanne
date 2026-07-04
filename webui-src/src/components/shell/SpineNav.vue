<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { useI18n } from '../../composables/useI18n'

const { t } = useI18n()

// Evolved "spine": the old centered draggable rail becomes a left sidebar that
// keeps the accent-line + node identity but is a real, keyboard-accessible nav.
const items = [
  { to: '/monitor', key: 'nav.monitor' },
  { to: '/cognition', key: 'nav.cognition' },
  { to: '/config', key: 'nav.config' },
  { to: '/logs', key: 'nav.logs' },
  { to: '/memory', key: 'nav.memory' },
  { to: '/personality', key: 'nav.personality' },
  { to: '/life', key: 'nav.life' },
  { to: '/admin', key: 'nav.admin' },
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
      <span class="dot" aria-hidden="true" />
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
  background: linear-gradient(
    180deg,
    rgba(184, 138, 158, 0.04),
    transparent 40%
  );
}
.spine-line {
  position: absolute;
  top: 12%;
  bottom: 12%;
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
  opacity: 0.35;
  pointer-events: none;
}
.node {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  text-decoration: none;
  color: var(--text-muted);
  transition: color var(--dur-fast) ease;
  outline: none;
}
.dot {
  width: 11px;
  height: 11px;
  border-radius: 50%;
  border: 2px solid var(--accent);
  background: var(--bg);
  opacity: 0.5;
  transition:
    transform var(--dur-fast) ease,
    box-shadow var(--dur-fast) ease,
    opacity var(--dur-fast) ease,
    background var(--dur-fast) ease;
}
.label {
  font-size: 10px;
  letter-spacing: 1px;
  text-transform: uppercase;
}
.node:hover {
  color: var(--text);
}
.node:hover .dot {
  transform: scale(1.25);
  opacity: 0.85;
}
.node:focus-visible .dot {
  box-shadow: var(--ring-focus);
  opacity: 1;
}
.node.active {
  color: var(--accent);
}
.node.active .dot {
  opacity: 1;
  background: var(--accent);
  box-shadow: 0 0 10px rgba(184, 138, 158, 0.5);
}
</style>
