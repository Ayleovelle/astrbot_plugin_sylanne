<script setup lang="ts">
import { computed } from 'vue'
import { useLiveStore } from '../../stores/live'

const live = useLiveStore()

const runtime = computed(() => (live.state?.runtime as string) || '—')
const schema = computed(() =>
  live.state?.schema_version !== undefined ? 'v' + live.state.schema_version : '',
)
const sessionCount = computed(() => live.state?.sessions?.length ?? 0)
</script>

<template>
  <footer class="foot mono">
    <span>runtime: {{ runtime }}</span>
    <span v-if="schema">schema {{ schema }}</span>
    <span>sessions: {{ sessionCount }}</span>
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
}
.err {
  color: var(--red);
}
</style>
