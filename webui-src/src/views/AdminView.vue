<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { apiFetch, scopedApiFetch } from '../api/client'
import type {
  LegacyInventoryRecord,
  LegacyInventoryResponse,
  ScopedApiResponse,
} from '../api/types'
import { useI18n } from '../composables/useI18n'
import { useLiveStore } from '../stores/live'
import { useScopeStore } from '../stores/scope'
import Badge from '../components/ui/Badge.vue'
import Button from '../components/ui/Button.vue'
import Card from '../components/ui/Card.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import ErrorState from '../components/ui/ErrorState.vue'

const { t } = useI18n()
const live = useLiveStore()
const scope = useScopeStore()

const records = ref<LegacyInventoryRecord[]>([])
const inventoryError = ref('')
const copyingId = ref('')
const claimMessage = ref('')
let inventoryRequest = 0
let claimRequest = 0
let timer: number | null = null

const delivery = computed(() => live.state?.delivery)
const hasCompleteScope = computed(() => scope.snapshot() !== null)

function deliveryReason(): string {
  if (delivery.value?.last_reason === 'account_route_unavailable') {
    return t('delivery.account_route_unavailable')
  }
  if (delivery.value?.last_reason === 'delivery_outcome_unknown') {
    return t('delivery.delivery_outcome_unknown')
  }
  return ''
}

function shortValue(value: string): string {
  return value.length > 12 ? `${value.slice(0, 12)}…` : value
}

function formatBytes(value: number): string {
  if (!Number.isFinite(value) || value < 0) return '—'
  if (value < 1024) return `${value} B`
  return `${(value / 1024).toFixed(1)} KiB`
}

function clearScopeData(): void {
  inventoryRequest += 1
  claimRequest += 1
  records.value = []
  inventoryError.value = ''
  copyingId.value = ''
  claimMessage.value = ''
}

async function fetchInventory(): Promise<void> {
  const request = ++inventoryRequest
  const selectionEpoch = scope.selectionEpoch
  inventoryError.value = ''
  try {
    const response = await apiFetch<LegacyInventoryResponse>('/api/v1/legacy/inventory')
    if (request !== inventoryRequest || selectionEpoch !== scope.selectionEpoch) return
    records.value = Array.isArray(response.records) ? response.records : []
  } catch (cause) {
    if (request !== inventoryRequest || selectionEpoch !== scope.selectionEpoch) return
    records.value = []
    inventoryError.value = cause instanceof Error ? cause.message : String(cause)
  }
}

async function copyClaim(record: LegacyInventoryRecord): Promise<void> {
  const snapshot = scope.snapshot()
  if (!snapshot) return
  const request = ++claimRequest
  const selectionEpoch = scope.selectionEpoch
  copyingId.value = record.record_id
  claimMessage.value = ''
  try {
    const response = await scopedApiFetch(snapshot, 'legacy-claim', {
      method: 'POST',
      body: { record_id: record.record_id },
    }) as ScopedApiResponse
    if (
      request !== claimRequest ||
      selectionEpoch !== scope.selectionEpoch ||
      !scope.isCurrent(snapshot, response)
    ) return
    claimMessage.value = t('admin.legacy_copy_ok')
  } catch (cause) {
    if (request !== claimRequest || selectionEpoch !== scope.selectionEpoch) return
    claimMessage.value = `${t('admin.legacy_copy_failed')}: ${cause instanceof Error ? cause.message : String(cause)}`
  } finally {
    if (request === claimRequest && selectionEpoch === scope.selectionEpoch) copyingId.value = ''
  }
}

function refresh(): void {
  void fetchInventory()
}

watch(
  () => scope.selectionEpoch,
  () => {
    clearScopeData()
    void fetchInventory()
  },
)

onMounted(() => {
  void fetchInventory()
  timer = window.setInterval(refresh, 15000)
})

onUnmounted(() => {
  clearScopeData()
  if (timer !== null) clearInterval(timer)
})
</script>

<template>
  <div class="page-split">
    <div class="pane-left">
      <Card :title="t('admin.delivery')">
        <EmptyState v-if="!delivery" />
        <div v-else class="delivery-grid">
          <div class="delivery-row">
            <span>{{ t('delivery.pending') }}</span>
            <Badge variant="neutral">{{ delivery.pending }}</Badge>
          </div>
          <div class="delivery-row">
            <span>{{ t('delivery.failed_retryable') }}</span>
            <Badge :variant="delivery.failed_retryable ? 'red' : 'neutral'">{{ delivery.failed_retryable }}</Badge>
          </div>
          <div class="delivery-row">
            <span>{{ t('delivery.outcome_unknown') }}</span>
            <Badge :variant="delivery.outcome_unknown ? 'red' : 'neutral'">{{ delivery.outcome_unknown }}</Badge>
          </div>
          <div class="delivery-row">
            <span>{{ t('delivery.suppressed') }}</span>
            <Badge variant="neutral">{{ delivery.suppressed }}</Badge>
          </div>
          <Badge v-if="deliveryReason()" variant="red">{{ deliveryReason() }}</Badge>
        </div>
      </Card>
    </div>

    <div class="pane-right">
      <Card :title="t('admin.legacy')">
        <template #action>
          <Button size="sm" @click="refresh">{{ t('admin.refresh') }}</Button>
        </template>
        <p class="legacy-warning">{{ t('admin.legacy_warning') }}</p>
        <ErrorState v-if="inventoryError" :message="inventoryError">
          <template #action><Button variant="primary" @click="refresh">{{ t('common.retry') }}</Button></template>
        </ErrorState>
        <EmptyState v-else-if="records.length === 0" />
        <div v-else class="legacy-list">
          <article v-for="record in records" :key="record.record_id" class="legacy-record">
            <div class="legacy-meta mono">
              <span>{{ t('admin.legacy_record') }}: {{ shortValue(record.record_id) }}</span>
              <span>{{ t('admin.legacy_checksum') }}: {{ shortValue(record.checksum) }}</span>
              <span>{{ t('admin.legacy_size') }}: {{ formatBytes(record.byte_size) }}</span>
            </div>
            <Button
              size="sm"
              variant="primary"
              :disabled="!hasCompleteScope || copyingId !== ''"
              :loading="copyingId === record.record_id"
              @click="copyClaim(record)"
            >{{ t('admin.legacy_copy') }}</Button>
          </article>
        </div>
        <p v-if="claimMessage" class="claim-message">{{ claimMessage }}</p>
      </Card>
    </div>
  </div>
</template>

<style scoped>
.delivery-grid, .legacy-list, .legacy-meta { display: grid; gap: var(--space-3); }
.delivery-row, .legacy-record { display: flex; align-items: center; justify-content: space-between; gap: var(--space-4); }
.delivery-row { padding: var(--space-3) var(--space-4); border: 1px solid var(--stat-border); border-radius: var(--r-md); background: var(--stat-bg); }
.legacy-warning { margin: 0 0 var(--space-5); color: var(--red); font-size: var(--font-sm); line-height: 1.6; }
.legacy-record { padding: var(--space-4); border: 1px solid var(--card-border); border-radius: var(--r-md); background: var(--stat-bg); }
.legacy-meta { min-width: 0; color: var(--text-muted); font-size: var(--font-xs); }
.claim-message { margin: var(--space-4) 0 0; color: var(--accent); font-size: var(--font-sm); }
@media (max-width: 760px) { .legacy-record { align-items: stretch; flex-direction: column; } }
</style>
