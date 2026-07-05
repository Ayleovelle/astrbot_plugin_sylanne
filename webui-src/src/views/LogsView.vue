<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { apiFetch } from '../api/client'
import { useLiveStore } from '../stores/live'
import { useSessionStore } from '../stores/session'
import { useI18n } from '../composables/useI18n'
import { num } from '../composables/useAdapt'
import Card from '../components/ui/Card.vue'
import Toggle from '../components/ui/Toggle.vue'
import Button from '../components/ui/Button.vue'
import LogTerminal, { type LogLine, type LogLevel } from '../components/ui/LogTerminal.vue'
import RouteBar from '../components/ui/RouteBar.vue'
import StatGrid from '../components/ui/StatGrid.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import type { ComputationLogEntry, ComputationLogsResponse, RouteDistribution } from '../api/types'

const live = useLiveStore()
const session = useSessionStore()
const { t } = useI18n()

const logs = ref<ComputationLogEntry[]>([])
const autoScroll = ref(true)
let timer: number | null = null
let inflight = false

// Old formatLogTime (UI/index.html, pre-rebuild — see git history at
// 1f8a21f): a string containing ':' is already human-formatted and passes
// through untouched; a number is unix seconds -> localized HH:MM:SS.mmm.
function formatLogTime(ts: unknown): string {
  if (typeof ts === 'string' && ts.indexOf(':') !== -1) return ts
  if (typeof ts === 'number') {
    const d = new Date(ts * 1000)
    return (
      d.toLocaleTimeString('en-GB', { hour12: false }) +
      '.' +
      String(d.getMilliseconds()).padStart(3, '0')
    )
  }
  return String(ts ?? '')
}

function logLevel(route: string, text: string): LogLevel {
  const t2 = text.toLowerCase()
  if (t2.includes('error') || t2.includes('fail') || t2.includes('exception')) return 'error'
  if (route.toUpperCase() === 'FULL' || t2.includes('spike') || t2.includes('warn')) return 'warn'
  return 'info'
}

async function fetchLogs(): Promise<void> {
  if (inflight) return
  inflight = true
  const q =
    '?limit=100' + (session.current ? '&session=' + encodeURIComponent(session.current) : '')
  try {
    const data = await apiFetch<ComputationLogsResponse | ComputationLogEntry[]>(
      '/api/computation_logs' + q,
    )
    logs.value = Array.isArray(data) ? data : data.logs || []
  } catch {
    // keep last-known logs on transient failure, matching the old dashboard
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

watch(() => session.current, () => void fetchLogs())

const logLines = computed<LogLine[]>(() =>
  logs.value.map((l) => {
    const route = String(l.route || 'NORMAL').toUpperCase()
    let text = String(l.msg ?? l.text ?? l.message ?? '')
    if (l.layers && typeof l.layers === 'object') {
      text += ' [' + Object.keys(l.layers).join(' ') + ']'
    }
    return {
      time: formatLogTime(l.time ?? l.ts),
      route,
      text,
      level: logLevel(route, text),
    }
  }),
)

const routeDist = computed<RouteDistribution>(() => {
  const rd = live.state?.route_distribution
  if (rd) return rd
  return { FAST: 0, NORMAL: 0, FULL: 0, SKIP: 0 }
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
  <div class="page">
    <Card :title="t('logs.title')" class="card-terminal">
      <template #action>
        <div class="terminal-actions">
          <Toggle v-model="autoScroll">{{ t('logs.autoscroll') }}</Toggle>
          <Button size="sm" @click="refresh">{{ t('logs.refresh') }}</Button>
        </div>
      </template>
      <LogTerminal v-if="logLines.length" :lines="logLines" :auto-scroll="autoScroll" />
      <EmptyState v-else message-key="common.empty" />
    </Card>

    <Card :title="t('logs.stats')">
      <RouteBar :dist="routeDist" />
      <StatGrid :items="statItems" :cols="4" />
    </Card>
  </div>
</template>

<style scoped>
/* 2-col grid so the terminal (left) and route stats (right) part around the
 * center rail — same split the old dashboard's page-left/page-right had. A
 * flex column here left --page-col-gap inert and the fixed spine sat on top
 * of the terminal text at >=900px. */
.page {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--page-row-gap, var(--space-8)) var(--page-col-gap, var(--space-8));
  align-items: start;
}

@media (max-width: 900px) {
  .page {
    grid-template-columns: 1fr;
  }
}

.terminal-actions {
  display: flex;
  align-items: center;
  gap: var(--space-6);
}

.card-terminal :deep(.log-terminal) {
  margin-top: var(--space-2);
}

.page > .card + .card :deep(.stat-grid) {
  margin-top: var(--space-6);
}
</style>
