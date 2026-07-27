<script setup lang="ts">
import { useSlots } from 'vue'
defineProps<{ title?: string }>()
const slots = useSlots()
</script>

<template>
  <div class="card">
    <div v-if="title || slots.header" class="card-head">
      <slot name="header"><span class="card-title">{{ title }}</span></slot>
      <slot name="action" />
    </div>
    <slot />
  </div>
</template>

<style scoped>
.card {
  background: var(--card);
  border: 1px solid var(--card-border);
  border-radius: var(--r-lg);
  padding: var(--space-8);
  position: relative;
  overflow: hidden;
  box-shadow: 0 2px 20px rgba(0, 0, 0, 0.22);
  transition: border-color var(--dur-mid) ease, box-shadow var(--dur-mid) ease;
  animation: fadeUp 0.5s var(--ease-snap) both;
  min-width: 0;
}
/* glowing "tissue slice" top edge — a constant faint version of the hover tint */
.card::before {
  content: '';
  position: absolute;
  top: 0;
  left: var(--space-7);
  right: var(--space-7);
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--card-tick), transparent);
  opacity: 0.4;
}
.card:hover {
  border-color: rgba(184, 138, 158, 0.28);
  box-shadow: 0 2px 24px rgba(0, 0, 0, 0.28), 0 0 20px rgba(184, 138, 158, 0.06);
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-6);
}
.card-title {
  display: inline-flex;
  align-items: center;
  gap: var(--space-3);
  font-size: var(--font-xs);
  letter-spacing: 2px;
  text-transform: uppercase;
  color: var(--text);
  opacity: 0.85;
}
/* glowing rose anchor tick — gives each card title an identity, not just a label */
.card-title::before {
  content: '';
  width: 3px;
  height: 12px;
  border-radius: 1px;
  background: var(--accent);
  box-shadow: var(--glow-accent);
}

@media (max-width: 620px) {
  .card {
    padding: var(--space-7);
  }
}
</style>
