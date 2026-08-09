<script setup lang="ts">
// Admin diagnostics page. Read-only anatomy table over three new backend
// admin endpoints (session KV/epoch inspection, quarantine view, pending
// deletes). Own fetch on mount + manual Refresh + a gentle 15s poll — this is
// diagnostic data, not a hot loop, so no aggressive polling (mirrors
// MemoryView/MonitorView's inflight-guarded interval pattern).
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { apiFetch } from '../api/client'
import { num } from '../composables/useAdapt'
import { useI18n } from '../composables/useI18n'
import { useSessionStore } from '../stores/session'
import type {
  AdminInspectResponse,
  AdminKvSlot,
  AdminPendingDeletesResponse,
  AdminQuarantineResponse,
} from '../api/types'
import Card from '../components/ui/Card.vue'
import StatGrid from '../components/ui/StatGrid.vue'
import Badge from '../components/ui/Badge.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import ErrorState from '../components/ui/ErrorState.vue'
import Timeline, { type TimelineItem } from '../components/ui/Timeline.vue'
import Button from '../components/ui/Button.vue'

const { t } = useI18n()
const session = useSessionStore()

// ---- data: own fetch of the 3 admin endpoints ----

const inspect = ref<AdminInspectResponse | null>(null)
const quarantine = ref<AdminQuarantineResponse | null>(null)
const pendingDeletes = ref<AdminPendingDeletesResponse | null>(null)

const inspectError = ref('')
const quarantineError = ref('')
const pendingError = ref('')

let timer: number | null = null
let inflight = false

function sessionQuery(): string {
  return session.current ? '?session=' + encodeURIComponent(session.current) : ''
}

async function fetchInspect(): Promise<void> {
  try {
    inspect.value = await apiFetch<AdminInspectResponse>('/api/admin/inspect' + sessionQuery())
    inspectError.value = ''
  } catch (e) {
    inspectError.value = e instanceof Error ? e.message : 'fetch failed'
  }
}

async function fetchQuarantine(): Promise<void> {
  try {
    quarantine.value = await apiFetch<AdminQuarantineResponse>(
      '/api/admin/quarantine_view' + sessionQuery(),
    )
    quarantineError.value = ''
  } catch (e) {
    quarantineError.value = e instanceof Error ? e.message : 'fetch failed'
  }
}

async function fetchPendingDeletes(): Promise<void> {
  try {
    pendingDeletes.value = await apiFetch<AdminPendingDeletesResponse>('/api/admin/pending_deletes')
    pendingError.value = ''
  } catch (e) {
    pendingError.value = e instanceof Error ? e.message : 'fetch failed'
  }
}

async function fetchAll(): Promise<void> {
  if (inflight) return
  inflight = true
  try {
    await Promise.all([fetchInspect(), fetchQuarantine(), fetchPendingDeletes()])
  } finally {
    inflight = false
  }
}

onMounted(() => {
  void fetchAll()
  timer = window.setInterval(() => void fetchAll(), 15000)
})
onUnmounted(() => {
  if (timer !== null) {
    clearInterval(timer)
    timer = null
  }
})
watch(
  () => session.current,
  () => {
    void fetchInspect()
    void fetchQuarantine()
  },
)

function refresh(): void {
  void fetchAll()
}

// ---- formatting helpers ----

function yn(v: boolean | null | undefined): string {
  if (v === null || v === undefined) return t('admin.unknown')
  return v ? t('admin.yes') : t('admin.no')
}

function fmtBytes(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  if (v < 1024) return v + ' B'
  return (v / 1024).toFixed(1) + ' KB'
}

function fmtTs(ts: number | undefined): string {
  if (ts === undefined || Number.isNaN(ts)) return '—'
  const d = new Date(ts * 1000)
  return d.toLocaleString()
}

// ---- inspect: pane-left ----

const inspectStats = computed(() => {
  const i = inspect.value ?? undefined
  if (!i) return []
  return [
    { label: t('admin.hydrated'), value: yn(i.hydrated) },
    { label: t('admin.incarnation_epoch'), value: num(i, ['incarnation_epoch'], NaN) },
    { label: t('admin.current_epoch'), value: num(i, ['current_epoch'], NaN) },
    { label: t('admin.queue_depth'), value: num(i, ['queue_depth'], NaN) },
    { label: t('admin.has_pending_delete'), value: yn(i.has_pending_delete) },
  ]
})

const epochMatches = computed<boolean | null>(() => inspect.value?.epoch_matches ?? null)

interface KvRow {
  key: string
  label: string
  slot: AdminKvSlot | null | undefined
}

const kvRows = computed<KvRow[]>(() => {
  const kv = inspect.value?.kv_keys
  if (!kv) return []
  return [
    { key: 'primary', label: t('admin.kv_primary'), slot: kv.primary },
    { key: 'v2_backup', label: t('admin.kv_v2_backup'), slot: kv.v2_backup },
    { key: 'quarantine', label: t('admin.kv_quarantine'), slot: kv.quarantine },
  ]
})

const throatStats = computed(() => {
  const th = inspect.value?.throat_stats ?? undefined
  return [
    { label: 'reject_count', value: num(th, ['reject_count'], 0) },
    { label: 'rebuild_count', value: num(th, ['rebuild_count'], 0) },
    { label: 'dropped_no_loop_count', value: num(th, ['dropped_no_loop_count'], 0) },
    { label: 'active_sessions', value: num(th, ['active_sessions'], 0) },
    { label: 'tracked_epochs', value: num(th, ['tracked_epochs'], 0) },
  ]
})

// ---- pending deletes: pane-right ----

const pendingItems = computed<TimelineItem[]>(() => {
  const entries = pendingDeletes.value?.entries
  if (!entries) return []
  return Object.entries(entries).map(([key, v]) => ({
    time: fmtTs(v.ts),
    text: key + ' · epoch ' + (v.epoch ?? '—'),
  }))
})

const pendingCount = computed(() => num(pendingDeletes.value ?? undefined, ['count'], 0))

// ---- quarantine: pane-right ----

const quarantineRows = computed(() => {
  const s = quarantine.value?.sessions
  if (!s) return []
  return Object.entries(s).map(([key, v]) => ({
    key,
    count: v.count ?? 0,
    itemsLen: Array.isArray(v.items) ? v.items.length : 0,
    error: v.error ?? false,
  }))
})

const totalEntries = computed(() => num(quarantine.value ?? undefined, ['total_entries'], 0))
</script>

<template>
  <div class="page-split">
    <div class="pane-left">
      <ErrorState v-if="!inspect && inspectError" :message="inspectError" class="page-error">
        <template #action>
          <Button variant="primary" @click="fetchInspect">{{ t('common.retry') }}</Button>
        </template>
      </ErrorState>

      <template v-else>
        <Card :title="t('admin.inspect')">
          <EmptyState v-if="!inspect" />
          <template v-else>
            <StatGrid :items="inspectStats" :cols="2" />
            <div class="epoch-match-row">
              <span class="epoch-match-lbl">{{ t('admin.epoch_matches') }}</span>
              <Badge :variant="epochMatches === null ? 'neutral' : epochMatches ? 'green' : 'red'">
                {{ yn(epochMatches) }}
              </Badge>
            </div>

            <div class="kv-section">
              <div class="kv-section-title">{{ t('admin.kv_keys') }}</div>
              <div v-if="kvRows.length" class="kv-rows">
                <div v-for="row in kvRows" :key="row.key" class="kv-row">
                  <div class="kv-row-head">
                    <span class="kv-row-label mono">{{ row.label }}</span>
                    <Badge
                      v-if="row.slot && row.slot.error"
                      variant="red"
                    >err</Badge>
                    <Badge
                      v-else
                      :variant="row.slot?.exists ? 'green' : 'neutral'"
                    >
                      {{ yn(row.slot?.exists) }}
                    </Badge>
                  </div>
                  <div v-if="row.slot && row.slot.exists" class="kv-row-detail mono">
                    <span>{{ t('admin.kv_bytes') }}: {{ fmtBytes(row.slot.bytes) }}</span>
                    <span>{{ t('admin.kv_version') }}: {{ row.slot.version ?? '—' }}</span>
                    <span v-if="row.slot.crc_valid !== undefined && row.slot.crc_valid !== null">
                      {{ t('admin.kv_crc_valid') }}: {{ yn(row.slot.crc_valid) }}
                    </span>
                  </div>
                </div>
              </div>
              <EmptyState v-else />
            </div>
          </template>
        </Card>

        <Card :title="t('admin.throat')">
          <EmptyState v-if="!inspect?.throat_stats" />
          <StatGrid v-else :items="throatStats" :cols="2" />
        </Card>
      </template>
    </div>

    <div class="pane-right">
      <Card :title="t('admin.pending')">
        <template #action>
          <Button size="sm" @click="refresh">{{ t('admin.refresh') }}</Button>
        </template>

        <ErrorState v-if="!pendingDeletes && pendingError" :message="pendingError">
          <template #action>
            <Button variant="primary" @click="fetchPendingDeletes">{{ t('common.retry') }}</Button>
          </template>
        </ErrorState>

        <template v-else-if="pendingDeletes">
          <div class="pending-head">
            <span class="pending-head-lbl">{{ t('admin.scan_done') }}</span>
            <Badge :variant="pendingDeletes.scan_done ? 'green' : 'neutral'">
              {{ yn(pendingDeletes.scan_done) }}
            </Badge>
          </div>
          <EmptyState v-if="pendingCount === 0" />
          <Timeline v-else :items="pendingItems" />
        </template>

        <EmptyState v-else />
      </Card>

      <Card :title="t('admin.quarantine')">
        <ErrorState v-if="!quarantine && quarantineError" :message="quarantineError">
          <template #action>
            <Button variant="primary" @click="fetchQuarantine">{{ t('common.retry') }}</Button>
          </template>
        </ErrorState>

        <template v-else-if="quarantine">
          <div class="quarantine-head">
            <span class="quarantine-head-lbl">{{ t('admin.total_entries') }}</span>
            <span class="quarantine-head-val mono">{{ totalEntries }}</span>
          </div>

          <EmptyState v-if="totalEntries === 0" />
          <template v-else>
            <div class="quarantine-rows">
              <div v-for="row in quarantineRows" :key="row.key" class="quarantine-row">
                <span class="quarantine-row-key mono">{{ row.key }}</span>
                <Badge v-if="row.error" variant="red">err</Badge>
                <span v-else class="quarantine-row-count mono">
                  {{ row.count }} / {{ row.itemsLen }}
                </span>
              </div>
            </div>
            <p v-if="quarantine.note" class="quarantine-note">{{ quarantine.note }}</p>
          </template>
        </template>

        <EmptyState v-else />
      </Card>
    </div>
  </div>
</template>

<style scoped>
.pane-left > .card + .card,
.pane-right > .card + .card {
  margin-top: var(--space-8);
}

.epoch-match-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: var(--space-6);
  padding: var(--space-4) var(--space-5);
  background: var(--stat-bg);
  border: 1px solid var(--stat-border);
  border-radius: var(--r-md);
}
.epoch-match-lbl {
  font-size: var(--font-xs);
  color: var(--text-muted);
  letter-spacing: 0.5px;
}

.kv-section {
  margin-top: var(--space-7);
}
.kv-section-title {
  font-size: var(--font-xs);
  letter-spacing: 1px;
  text-transform: uppercase;
  color: var(--text-muted);
  margin-bottom: var(--space-4);
}
.kv-rows {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
.kv-row {
  padding: var(--space-4) var(--space-5);
  background: var(--stat-bg);
  border: 1px solid var(--stat-border);
  border-radius: var(--r-md);
}
.kv-row-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.kv-row-label {
  font-size: var(--font-sm);
  color: var(--text);
}
.kv-row-detail {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-5);
  margin-top: var(--space-3);
  font-size: var(--font-xs);
  color: var(--text-muted);
}

.pending-head,
.quarantine-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-6);
}
.pending-head-lbl,
.quarantine-head-lbl {
  font-size: var(--font-xs);
  color: var(--text-muted);
  letter-spacing: 0.5px;
}
.quarantine-head-val {
  font-size: var(--font-lg);
  font-weight: 700;
  color: var(--accent);
  text-shadow: var(--glow-text);
}

.quarantine-rows {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.quarantine-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-5);
  background: var(--stat-bg);
  border: 1px solid var(--stat-border);
  border-radius: var(--r-md);
}
.quarantine-row-key {
  font-size: var(--font-sm);
  color: var(--text);
}
.quarantine-row-count {
  font-size: var(--font-sm);
  color: var(--text-muted);
}
.quarantine-note {
  margin: var(--space-6) 0 0;
  font-size: var(--font-xs);
  color: var(--text-muted);
  opacity: 0.8;
  line-height: 1.5;
}

.page-error {
  height: 100%;
}
</style>
