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
  transition: border-color var(--dur-mid) ease;
  animation: fadeUp 0.5s var(--ease-snap) both;
}
.card:hover {
  border-color: rgba(184, 138, 158, 0.22);
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-6);
}
.card-title {
  font-size: var(--font-xs);
  letter-spacing: 2px;
  text-transform: uppercase;
  color: var(--text-muted);
}
</style>
