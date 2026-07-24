<script setup lang="ts">
import { computed } from 'vue'
import { useLiveStore } from '../../stores/live'

const live = useLiveStore()

const runtime = computed(() => {
  const value = live.state?.runtime
  if (typeof value === 'string') return value || '—'
  if (value && typeof value === 'object') {
    const info = value as Record<string, unknown>
    return String(info.runtime_id || info.instance_id || info.plugin_name || '—')
  }
  return '—'
})
const schema = computed(() => {
  const value = live.state?.schema_version
  return value === undefined ? '' : String(value).replace(/^sylanne\.webui\./, '')
})
const sessionCount = computed(() => live.state?.sessions?.length ?? 0)
</script>

<template>
  <footer class="foot mono">
    <span class="runtime">runtime: {{ runtime }}</span>
    <span v-if="schema" class="meta">schema {{ schema }}</span>
    <span class="meta">sessions: {{ sessionCount }}</span>
    <span v-if="live.error" class="err">· {{ live.error }}</span>
  </footer>
</template>

<style scoped>
.foot {
  display: flex;
  align-items: center;
  gap: var(--space-7);
  padding: 0 var(--space-8);
  border-top: 1px solid var(--card-border);
  font-size: var(--font-xs);
  color: var(--text-muted);
  letter-spacing: 0.5px;
  min-width: 0;
  overflow: hidden;
}
.runtime {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.meta {
  flex: none;
  white-space: nowrap;
}
.err {
  color: var(--red);
}

@media (max-width: 620px) {
  .foot {
    gap: var(--space-4);
    padding: 0 var(--space-3);
  }
}
</style>
