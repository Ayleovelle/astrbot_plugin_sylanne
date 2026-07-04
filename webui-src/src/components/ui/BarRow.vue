<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    label: string
    value: number
    max?: number
    color?: string
    display?: string
  }>(),
  { max: 1 },
)

const pct = computed(() => {
  const m = props.max || 1
  return Math.max(0, Math.min(100, (props.value / m) * 100))
})

const shown = computed(() => {
  if (props.display !== undefined) return props.display
  const v = props.value
  return v <= 1 && v >= -1 ? v.toFixed(2) : String(Math.round(v))
})
</script>

<template>
  <div class="bar-row">
    <span class="bar-label mono">{{ label }}</span>
    <span class="bar-track">
      <span
        class="bar-fill"
        :style="{ width: pct + '%', background: color || 'var(--accent)' }"
      />
    </span>
    <span class="bar-value mono">{{ shown }}</span>
  </div>
</template>

<style scoped>
.bar-row {
  display: flex;
  align-items: center;
  margin-bottom: var(--space-4);
  gap: var(--space-4);
}
.bar-label {
  font-size: var(--font-sm);
  width: 120px;
  flex: none;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bar-track {
  flex: 1;
  height: 10px;
  background: var(--track);
  border-radius: 5px;
  overflow: hidden;
}
.bar-fill {
  display: block;
  height: 100%;
  border-radius: 5px;
  transition: width var(--dur-slow) ease;
  box-shadow: var(--glow-accent);
}
.bar-value {
  font-size: var(--font-sm);
  width: 44px;
  flex: none;
  text-align: right;
}
</style>
