<script setup lang="ts">
// 认知核 / Cognition page — the old dashboard's "spine"/CORE view, rebuilt.
// Own 5s poll of /api/v2core_state (independent of useLiveStore's /api/state
// poll), scoped to the active session like live.ts does for /api/state.
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { apiFetch } from '../api/client'
import { useSessionStore } from '../stores/session'
import { useI18n } from '../composables/useI18n'
import { num } from '../composables/useAdapt'
import type { V2CoreStateResponse } from '../api/types'
import Card from '../components/ui/Card.vue'
import Badge from '../components/ui/Badge.vue'
import BarRow from '../components/ui/BarRow.vue'
import StatGrid from '../components/ui/StatGrid.vue'
import EmptyState from '../components/ui/EmptyState.vue'

const { t } = useI18n()
const session = useSessionStore()

const resp = ref<V2CoreStateResponse | null>(null)
let timer: number | null = null
let inflight = false

async function fetchOnce(): Promise<void> {
  if (inflight) return
  inflight = true
  const s = session.current
  const q = s ? '?session=' + encodeURIComponent(s) : ''
  try {
    resp.value = await apiFetch<V2CoreStateResponse>('/api/v2core_state' + q)
  } catch {
    resp.value = null
  } finally {
    inflight = false
  }
}

function start(): void {
  stop()
  void fetchOnce()
  timer = window.setInterval(() => void fetchOnce(), 5000)
}
function stop(): void {
  if (timer !== null) {
    clearInterval(timer)
    timer = null
  }
}

onMounted(start)
onUnmounted(stop)
watch(() => session.current, () => void fetchOnce())

// enabled:false whenever v2core never ran for this session — normal, not an error.
const disabled = computed(() => !resp.value || resp.value.enabled === false)

// --- 1) decision ---
const decision = computed(() => resp.value?.decision)
const decisionAction = computed(() => decision.value?.action || 'N/A')
const decisionOutcome = computed(() => decision.value?.outcome)
const silentReason = computed(() => decision.value?.silent_reason)

const decisionBars = computed(() => {
  const d = decision.value as Record<string, unknown> | undefined
  const keys = ['g_speak', 'g_hold', 'g_reach', 'eff_drive'] as const
  return keys.map((field) => {
    const v = num(d, [field], 0)
    return { key: field, label: field, value: v, display: v.toFixed(2) }
  })
})

const decisionStats = computed(() => {
  const d = decision.value as Record<string, unknown> | undefined
  return [
    { label: 'express_at', value: num(d, ['express_at'], 0).toFixed(2) },
    { label: 'quality', value: num(d, ['quality'], 0).toFixed(2) },
  ]
})

// --- 2) fragment ---
const fragment = computed(() => resp.value?.fragment || '')

// --- 3) emotion domain ---
const emotionDomain = computed(() => resp.value?.domains?.emotion)
const emotionBars = computed(() => {
  const e = emotionDomain.value as Record<string, unknown> | undefined
  const keys = ['warmth', 'tension', 'volatility', 'unexpressed'] as const
  const rows: Array<{ key: string; label: string; value: number; display: string }> = keys.map((k) => {
    const v = num(e, [k], 0)
    return { key: k, label: k, value: Math.abs(v), display: v.toFixed(2) }
  })
  const extra: typeof rows = []
  if (e && (e.valence !== undefined && e.valence !== null && e.valence !== '')) {
    const v = num(e, ['valence'], 0)
    extra.push({ key: 'valence', label: 'valence', value: Math.abs(v), display: v.toFixed(2) })
  }
  if (e && (e.arousal !== undefined && e.arousal !== null && e.arousal !== '')) {
    const v = num(e, ['arousal'], 0)
    extra.push({ key: 'arousal', label: 'arousal', value: Math.abs(v), display: v.toFixed(2) })
  }
  return [...rows, ...extra]
})
const emotionLine = computed(() => emotionDomain.value?.line)
const emotionTrend = computed(() => emotionDomain.value?.trend)
// Signed 2dp when it parses as a finite number (e.g. -0.12 -> '-0.12', 0.5 ->
// '+0.50'); otherwise show whatever string the backend sent as-is.
const emotionTrendDisplay = computed(() => {
  const v = emotionTrend.value
  const n = Number(v)
  if (v !== undefined && v !== null && Number.isFinite(n)) {
    return (n >= 0 ? '+' : '') + n.toFixed(2)
  }
  return String(v ?? '')
})

// --- 4) usermodel domain ---
const usermodelDomain = computed(() => resp.value?.domains?.usermodel)
const usermodelBars = computed(() => {
  const u = usermodelDomain.value
  const rows: Array<{ key: string; label: string; value: number; display: string }> = []
  const core: Record<string, unknown> | undefined = u as Record<string, unknown> | undefined
  for (const k of ['synchrony', 'grip', 'rhythm_ema'] as const) {
    const v = num(core, [k], 0)
    rows.push({ key: k, label: k, value: v, display: v.toFixed(2) })
  }
  const disp = u?.disposition as Record<string, unknown> | undefined
  for (const k of ['warmth', 'engagement', 'defensiveness', 'distress'] as const) {
    const v = num(disp, [k], 0)
    // Bare label (not 'disposition.' + k) — the 150px BarRow label column
    // truncates the prefixed form, and context (对Ta的后验 card) already
    // makes clear these are disposition fields. Row `key` keeps the prefix
    // for uniqueness against the core synchrony/grip/rhythm_ema keys above.
    rows.push({ key: 'disposition.' + k, label: k, value: v, display: v.toFixed(2) })
  }
  return rows
})
const usermodelLine = computed(() => usermodelDomain.value?.line)

// --- 5) narrative domain ---
const narrativeDomain = computed(() => resp.value?.domains?.narrative)
const narrativeStats = computed(() => {
  const n = narrativeDomain.value as Record<string, unknown> | undefined
  const items = [
    { label: 'epoch', value: num(n, ['epoch'], 0).toFixed(0) },
    { label: 'anchor_total', value: num(n, ['anchor_total', 'anchor_count'], 0).toFixed(0) },
    { label: 'rigidity', value: num(n, ['rigidity'], 0).toFixed(2) },
  ]
  if (n && n.ossification !== undefined && n.ossification !== null && n.ossification !== '') {
    items.push({ label: 'ossification', value: num(n, ['ossification'], 0).toFixed(2) })
  }
  return items
})
const narrativeLine = computed(() => narrativeDomain.value?.line)

// --- 6) distill domain ---
const distillDomain = computed(() => resp.value?.domains?.distill)
const distillStats = computed(() => {
  const d = distillDomain.value as Record<string, unknown> | undefined
  return [
    { label: 'fidelity', value: num(d, ['fidelity'], 0).toFixed(2) },
    { label: 'samples', value: num(d, ['samples'], 0).toFixed(0) },
    { label: 'mean_error', value: num(d, ['mean_error'], 0).toFixed(3) },
  ]
})
</script>

<template>
  <div v-if="disabled" class="page">
    <Card :title="t('cog.cycle')">
      <EmptyState message-key="cog.disabled" />
    </Card>
  </div>

  <div v-else class="page">
    <Card :title="t('cog.decision')">
      <div class="badge-row">
        <Badge variant="accent">{{ decisionAction }}</Badge>
        <Badge v-if="decisionOutcome" variant="neutral">{{ decisionOutcome }}</Badge>
      </div>
      <div v-if="silentReason" class="silent-reason mono">{{ silentReason }}</div>
      <BarRow
        v-for="row in decisionBars"
        :key="row.key"
        :label="row.label"
        :value="row.value"
        :display="row.display"
      />
      <StatGrid :items="decisionStats" :cols="2" />
    </Card>

    <Card :title="t('cog.fragment')">
      <pre v-if="fragment" class="fragment mono">{{ fragment }}</pre>
      <EmptyState v-else />
    </Card>

    <Card :title="t('cog.emotion')">
      <BarRow
        v-for="row in emotionBars"
        :key="row.key"
        :label="row.label"
        :value="row.value"
        :display="row.display"
      />
      <div class="caption-row">
        <span v-if="emotionLine" class="line-caption mono">{{ emotionLine }}</span>
        <Badge v-if="emotionTrend !== undefined && emotionTrend !== null" variant="neutral">
          {{ emotionTrendDisplay }}
        </Badge>
      </div>
    </Card>

    <Card :title="t('cog.usermodel')">
      <BarRow
        v-for="row in usermodelBars"
        :key="row.key"
        :label="row.label"
        :value="row.value"
        :display="row.display"
      />
      <div v-if="usermodelLine" class="line-caption mono">{{ usermodelLine }}</div>
    </Card>

    <Card :title="t('cog.narrative')">
      <StatGrid :items="narrativeStats" :cols="narrativeStats.length > 3 ? 4 : 3" />
      <div v-if="narrativeLine" class="line-caption mono">{{ narrativeLine }}</div>
    </Card>

    <Card :title="t('cog.distill')">
      <StatGrid :items="distillStats" :cols="3" />
    </Card>
  </div>
</template>

<style scoped>
.page {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-8);
  align-items: start;
}

.badge-row {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  margin-bottom: var(--space-5);
}

.silent-reason {
  color: var(--text-muted);
  font-size: var(--font-xs);
  margin-bottom: var(--space-5);
}

.fragment {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: var(--font-sm);
  line-height: 1.6;
  color: var(--text);
  margin: 0;
  max-height: 320px;
  overflow-y: auto;
}

.caption-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  margin-top: var(--space-4);
}

.line-caption {
  color: var(--text-muted);
  font-size: var(--font-xs);
  margin-top: var(--space-4);
  display: block;
}

@media (max-width: 900px) {
  .page {
    grid-template-columns: 1fr;
  }
}
</style>
