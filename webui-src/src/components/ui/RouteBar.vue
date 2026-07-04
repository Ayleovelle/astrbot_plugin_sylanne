<script setup lang="ts">
import { computed } from 'vue'
import type { RouteDistribution } from '../../api/types'

const props = defineProps<{ dist: RouteDistribution }>()

const ORDER = ['FAST', 'NORMAL', 'FULL', 'SKIP'] as const
const COLORS: Record<string, string> = {
  FAST: 'var(--accent)',
  NORMAL: 'var(--cyan)',
  FULL: 'var(--amber)',
  SKIP: 'rgba(255,255,255,0.2)',
}

const total = computed(() =>
  ORDER.reduce((s, k) => s + (props.dist[k] || 0), 0),
)
const segs = computed(() =>
  ORDER.map((k) => {
    const count = props.dist[k] || 0
    return {
      key: k,
      count,
      pct: total.value ? (count / total.value) * 100 : 0,
      color: COLORS[k],
    }
  }),
)
</script>

<template>
  <div>
    <div class="route-bar">
      <div
        v-for="s in segs"
        :key="s.key"
        class="route-seg"
        :style="{ width: s.pct + '%', background: s.color }"
      />
    </div>
    <div class="route-legend">
      <span v-for="s in segs" :key="s.key" class="leg mono">
        <i class="dot" :style="{ background: s.color }" />{{ s.key }}
        <b>{{ s.count }}</b>
      </span>
    </div>
  </div>
</template>

<style scoped>
.route-bar {
  display: flex;
  height: 16px;
  border-radius: var(--r-xs);
  overflow: hidden;
  background: var(--track);
}
.route-seg {
  height: 100%;
  transition: width var(--dur-slow) ease;
}
.route-legend {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-5);
  margin-top: var(--space-5);
  font-size: var(--font-xs);
  color: var(--text-muted);
}
.leg {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
}
.leg b {
  color: var(--text);
  font-weight: 700;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}
</style>
