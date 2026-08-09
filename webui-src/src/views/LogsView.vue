<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { scopedApiFetch } from '../api/client'
import { useScopeStore } from '../stores/scope'
import { useI18n } from '../composables/useI18n'
import { num } from '../composables/useAdapt'
import Card from '../components/ui/Card.vue'
import Button from '../components/ui/Button.vue'
import RouteBar from '../components/ui/RouteBar.vue'
import StatGrid from '../components/ui/StatGrid.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import type { RouteDistribution, ScopedDiagnosticsResponse } from '../api/types'

const scope = useScopeStore()
const { t } = useI18n()

const routeDistribution = ref<RouteDistribution>({})
let timer: number | null = null
let inflight = false

async function fetchLogs(): Promise<void> {
  if (inflight) return
  inflight = true
  const snapshot = scope.snapshot()
  if (!snapshot) {
    routeDistribution.value = {}
    inflight = false
    return
  }
  try {
    const data = await scopedApiFetch<ScopedDiagnosticsResponse>(snapshot, 'diagnostics')
    if (!scope.isCurrent(snapshot, data)) return
    routeDistribution.value = data.diagnostics?.route_counts || {}
  } catch {
    // Keep last-known route statistics on transient failure.
  } finally {
    inflight = false
  }
}

function start(): void {
  stop()
  void fetchLogs()
  timer = window.setInterval(() => void fetchLogs(), 5000)
}
function stop(): void {
  if (timer !== null) {
    clearInterval(timer)
    timer = null
  }
}

onMounted(start)
onUnmounted(stop)

watch(() => scope.selectionEpoch, () => void fetchLogs())

const routeDist = computed<RouteDistribution>(() => {
  return routeDistribution.value
})

const statItems = computed(() => {
  const rd = routeDist.value
  return [
    { label: 'FAST', value: num(rd, ['FAST'], 0) },
    { label: 'NORMAL', value: num(rd, ['NORMAL'], 0) },
    { label: 'FULL', value: num(rd, ['FULL'], 0) },
    { label: 'SKIP', value: num(rd, ['SKIP'], 0) },
  ]
})

function refresh(): void {
  void fetchLogs()
}
</script>

<template>
  <div class="page-split">
    <div class="pane-left">
      <Card :title="t('logs.title')" class="card-terminal">
        <template #action>
          <Button size="sm" @click="refresh">{{ t('logs.refresh') }}</Button>
        </template>
        <EmptyState message-key="common.empty" />
      </Card>
    </div>

    <div class="pane-right">
      <Card :title="t('logs.stats')">
        <RouteBar :dist="routeDist" />
        <StatGrid :items="statItems" :cols="4" />
      </Card>
    </div>
  </div>
</template>

<style scoped>
.pane-right :deep(.stat-grid) {
  margin-top: var(--space-6);
}
</style>
