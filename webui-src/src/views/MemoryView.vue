<script setup lang="ts">
// Memory pools page. Owns its own 10s poll of /api/memory_pools (mirrors the
// old dashboard's adaptMemoryPools()) plus two action flows:
//   - consolidation: POST /api/memory_consolidate -> countdown -> GET /api/memory_sink
//   - meltdown: nonce fetch -> type-to-arm -> abortable countdown -> POST /api/memory_meltdown
// Both are destructive-adjacent (meltdown genuinely irreversible), so the
// meltdown flow is deliberately defensive: a `cancelled` flag is checked
// right before the POST fires, so dismissing the Modal mid-countdown (Esc /
// backdrop) can never let the network call slip through afterward.
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { apiFetch } from '../api/client'
import { num } from '../composables/useAdapt'
import { useI18n } from '../composables/useI18n'
import { useSessionStore } from '../stores/session'
import { useAuthStore } from '../stores/auth'
import type { MemoryPoolItem, MemoryPoolsResponse } from '../api/types'
import Card from '../components/ui/Card.vue'
import StatGrid from '../components/ui/StatGrid.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import ErrorState from '../components/ui/ErrorState.vue'
import Button from '../components/ui/Button.vue'
import Modal from '../components/ui/Modal.vue'
import TextInput from '../components/ui/TextInput.vue'

const { t } = useI18n()
const session = useSessionStore()
const auth = useAuthStore()

// ---- data: own poll of /api/memory_pools ----

const pools = ref<MemoryPoolsResponse | null>(null)
const poolsError = ref('')
let timer: number | null = null
let inflight = false

function query(): string {
  return session.current ? '?session=' + encodeURIComponent(session.current) : ''
}

async function fetchPools(): Promise<void> {
  if (inflight) return
  inflight = true
  try {
    const data = await apiFetch<MemoryPoolsResponse>('/api/memory_pools' + query())
    pools.value = data
    poolsError.value = ''
  } catch (e) {
    poolsError.value = e instanceof Error ? e.message : 'fetch failed'
  } finally {
    inflight = false
  }
}

onMounted(() => {
  void fetchPools()
  timer = window.setInterval(() => void fetchPools(), 10000)
})
onUnmounted(() => {
  if (timer !== null) {
    clearInterval(timer)
    timer = null
  }
})
watch(
  () => session.current,
  () => void fetchPools(),
)

// ---- adapt: mirrors old adaptMemoryPools() — prefer layers.*, fallback flat ----

function itemText(it: MemoryPoolItem): string {
  return String(it.content ?? it.text ?? it.summary ?? '')
}
function itemMeta(it: MemoryPoolItem): string {
  const parts: string[] = []
  const w = num(it, ['weight'], NaN)
  if (!Number.isNaN(w)) parts.push(t('mem.weight') + ' ' + w.toFixed(2))
  const age = num(it, ['age'], NaN)
  if (!Number.isNaN(age)) parts.push(t('mem.age') + ' ' + age)
  else if (it.created_at) parts.push(String(it.created_at))
  return parts.join(' · ')
}

const l1Items = computed<MemoryPoolItem[]>(() => {
  const p = pools.value
  return p?.layers?.l1_hot?.items ?? p?.hot ?? []
})
const l2Items = computed<MemoryPoolItem[]>(() => {
  const p = pools.value
  return p?.layers?.l2_warm?.items ?? p?.warm ?? []
})
const l3Items = computed<MemoryPoolItem[]>(() => {
  const p = pools.value
  return p?.layers?.l3_cold?.nodes ?? p?.cold ?? []
})

const summaryItems = computed(() => {
  const s = pools.value?.summary
  return [
    { label: 'total', value: num(s, ['total'], 0) },
    { label: 'l1_count', value: num(s, ['l1_count'], 0) },
    { label: 'l2_count', value: num(s, ['l2_count'], 0) },
    { label: 'l3_node_count', value: num(s, ['l3_node_count'], 0) },
    { label: 'avg_weight', value: num(s, ['avg_weight'], 0).toFixed(2) },
    { label: 'avg_temperature', value: num(s, ['avg_temperature'], 0).toFixed(2) },
  ]
})

// ---- consolidation ----

const consolidating = ref(false)
const consolidateCountdown = ref(0)
const sinkResult = ref<number | null>(null)
let consolidateTimer: number | null = null
// Guards against a duplicate finishConsolidate() call — the ===0 branch and
// the interval-completion branch could otherwise both fire and the second,
// stale GET /api/memory_sink would clobber the real sunk result.
let consolidateFinished = false

function clearConsolidateTimer(): void {
  if (consolidateTimer !== null) {
    clearInterval(consolidateTimer)
    consolidateTimer = null
  }
}

async function startConsolidate(): Promise<void> {
  if (consolidating.value) return
  consolidating.value = true
  consolidateFinished = false
  sinkResult.value = null
  try {
    const resp = await apiFetch<{ estimated_seconds?: number }>('/api/memory_consolidate', {
      method: 'POST',
      body: { session: session.current },
    })
    const seconds = num(resp as Record<string, unknown>, ['estimated_seconds'], 3)
    consolidateCountdown.value = Math.max(0, Math.ceil(seconds))
    clearConsolidateTimer()
    if (consolidateCountdown.value === 0) {
      // Nothing to wait on (e.g. empty L1) — finish immediately and never
      // schedule the interval, so it can't also fire finishConsolidate().
      await finishConsolidate()
      return
    }
    consolidateTimer = window.setInterval(() => {
      consolidateCountdown.value -= 1
      if (consolidateCountdown.value <= 0) {
        clearConsolidateTimer()
        void finishConsolidate()
      }
    }, 1000)
  } catch {
    consolidating.value = false
  }
}

async function finishConsolidate(): Promise<void> {
  if (consolidateFinished) return
  consolidateFinished = true
  try {
    const resp = await apiFetch<{ sunk?: number }>('/api/memory_sink' + query())
    sinkResult.value = num(resp as Record<string, unknown>, ['sunk'], 0)
    void fetchPools()
  } catch {
    sinkResult.value = null
  } finally {
    consolidating.value = false
  }
}

onUnmounted(() => {
  clearConsolidateTimer()
})

// ---- meltdown ----

type MeltdownStage = 'idle' | 'confirm' | 'counting'

const meltdownOpen = ref(false)
const meltdownStage = ref<MeltdownStage>('idle')
const meltdownNonce = ref('')
const meltdownInput = ref('')
const meltdownCountdown = ref(0)
const meltdownError = ref('')
let meltdownTimer: number | null = null
// Guards the one truly dangerous race: Modal dismissed (Esc/backdrop) while
// the countdown is running must NEVER let the queued POST fire afterward.
let meltdownCancelled = false

function clearMeltdownTimer(): void {
  if (meltdownTimer !== null) {
    clearInterval(meltdownTimer)
    meltdownTimer = null
  }
}

function resetMeltdownState(): void {
  clearMeltdownTimer()
  meltdownStage.value = 'idle'
  meltdownNonce.value = ''
  meltdownInput.value = ''
  meltdownCountdown.value = 0
  meltdownError.value = ''
}

async function openMeltdown(): Promise<void> {
  meltdownCancelled = false
  meltdownOpen.value = true
  meltdownStage.value = 'confirm'
  meltdownInput.value = ''
  meltdownError.value = ''
  try {
    const resp = await apiFetch<{ nonce?: string }>('/api/meltdown_nonce' + query())
    meltdownNonce.value = String(resp.nonce ?? '')
  } catch {
    meltdownNonce.value = ''
    meltdownError.value = 'nonce fetch failed'
  }
}

const meltdownMatch = computed(
  () => meltdownNonce.value !== '' && meltdownInput.value === meltdownNonce.value,
)

function armMeltdown(): void {
  if (!meltdownMatch.value) return
  meltdownStage.value = 'counting'
  meltdownCountdown.value = 10
  clearMeltdownTimer()
  meltdownTimer = window.setInterval(() => {
    meltdownCountdown.value -= 1
    if (meltdownCountdown.value <= 0) {
      clearMeltdownTimer()
      void fireMeltdown()
    }
  }, 1000)
}

function abortMeltdown(): void {
  meltdownCancelled = true
  clearMeltdownTimer()
  meltdownOpen.value = false
  resetMeltdownState()
}

// Watches the Modal's own open state — covers Esc/backdrop dismissal, which
// bypasses abortMeltdown() and only ever fires 'update:open'.
watch(meltdownOpen, (isOpen) => {
  if (!isOpen) {
    meltdownCancelled = true
    clearMeltdownTimer()
    resetMeltdownState()
  }
})

async function fireMeltdown(): Promise<void> {
  if (meltdownCancelled) return
  try {
    const resp = await apiFetch<{ ok?: boolean }>('/api/memory_meltdown', {
      method: 'POST',
      body: { session: session.current, nonce: meltdownNonce.value },
    })
    if (meltdownCancelled) return
    if (resp.ok) {
      // Reuse the auth store's logout path exactly (clears token + status),
      // then hard-redirect so no stale in-memory state (pools, session)
      // survives the meltdown.
      auth.logout()
      window.location.hash = '#/login'
      window.location.reload()
    }
  } catch {
    if (!meltdownCancelled) meltdownError.value = 'meltdown failed'
  }
}

onUnmounted(() => {
  meltdownCancelled = true
  clearMeltdownTimer()
})
</script>

<template>
  <ErrorState v-if="!pools && poolsError" :message="poolsError" class="page-error" />

  <div v-else-if="!pools" class="loading-state">
    <span class="mono">{{ t('common.loading') }}</span>
  </div>

  <div v-else class="page">
    <Card :title="t('mem.l1')" class="pool-card">
      <div v-if="l1Items.length" class="pool-list">
        <div v-for="(it, i) in l1Items" :key="i" class="pool-item">
          <div class="pool-text mono">{{ itemText(it) }}</div>
          <div class="pool-meta mono">{{ itemMeta(it) }}</div>
        </div>
      </div>
      <EmptyState v-else />
    </Card>

    <Card :title="t('mem.l2')" class="pool-card">
      <div v-if="l2Items.length" class="pool-list">
        <div v-for="(it, i) in l2Items" :key="i" class="pool-item">
          <div class="pool-text mono">{{ itemText(it) }}</div>
          <div class="pool-meta mono">{{ itemMeta(it) }}</div>
        </div>
      </div>
      <EmptyState v-else />
    </Card>

    <Card :title="t('mem.l3')" class="pool-card">
      <div v-if="l3Items.length" class="pool-list">
        <div v-for="(it, i) in l3Items" :key="i" class="pool-item">
          <div class="pool-text mono">{{ itemText(it) }}</div>
          <div class="pool-meta mono">{{ itemMeta(it) }}</div>
        </div>
      </div>
      <EmptyState v-else />
    </Card>

    <Card class="stat-card">
      <StatGrid :items="summaryItems" :cols="3" />
    </Card>

    <Card :title="t('mem.consolidate')" class="consolidate-card">
      <div class="consolidate-row">
        <Button
          variant="primary"
          :loading="consolidating"
          :disabled="consolidating"
          @click="startConsolidate"
        >
          {{ t('mem.sink') }}
        </Button>
        <span v-if="consolidating && consolidateCountdown > 0" class="countdown mono">
          {{ consolidateCountdown }}s
        </span>
        <span v-if="sinkResult !== null" class="sink-result mono">sunk: {{ sinkResult }}</span>
      </div>
    </Card>

    <Card :title="t('mem.meltdown')" class="meltdown-card">
      <p class="meltdown-desc">{{ t('mem.meltdown_desc') }}</p>
      <Button variant="danger" @click="openMeltdown">{{ t('mem.meltdown_btn') }}</Button>
    </Card>

    <Modal v-model:open="meltdownOpen" :title="t('mem.meltdown_btn')" size="sm">
      <div v-if="meltdownStage === 'confirm'" class="meltdown-confirm">
        <p class="meltdown-confirm-desc">{{ t('mem.meltdown_confirm') }}</p>
        <p v-if="meltdownNonce" class="meltdown-nonce mono">{{ meltdownNonce }}</p>
        <p v-else-if="meltdownError" class="meltdown-error mono">{{ meltdownError }}</p>
        <TextInput
          v-model="meltdownInput"
          placeholder="..."
          :invalid="meltdownInput.length > 0 && !meltdownMatch"
        />
      </div>
      <div v-else-if="meltdownStage === 'counting'" class="meltdown-counting">
        <p class="countdown-big mono">{{ meltdownCountdown }}</p>
        <p v-if="meltdownError" class="meltdown-error mono">{{ meltdownError }}</p>
      </div>

      <template #footer>
        <Button variant="secondary" @click="abortMeltdown">{{ t('mem.meltdown_abort') }}</Button>
        <Button
          v-if="meltdownStage === 'confirm'"
          variant="danger"
          :disabled="!meltdownMatch"
          @click="armMeltdown"
        >
          {{ t('mem.meltdown_btn') }}
        </Button>
      </template>
    </Modal>
  </div>
</template>

<style scoped>
.page {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-8);
  align-items: start;
}

.stat-card,
.consolidate-card,
.meltdown-card {
  grid-column: 1 / -1;
}

.pool-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  max-height: 280px;
  overflow-y: auto;
}

.pool-item {
  padding: var(--space-4) var(--space-5);
  background: var(--stat-bg);
  border: 1px solid var(--stat-border);
  border-radius: var(--r-md);
}

.pool-text {
  font-size: var(--font-sm);
  color: var(--text);
  white-space: pre-wrap;
  word-break: break-word;
}

.pool-meta {
  margin-top: var(--space-2);
  font-size: var(--font-xs);
  color: var(--text-muted);
}

.consolidate-row {
  display: flex;
  align-items: center;
  gap: var(--space-6);
}

.countdown {
  font-size: var(--font-sm);
  color: var(--accent);
}

.sink-result {
  font-size: var(--font-sm);
  color: var(--text-muted);
}

.meltdown-card {
  border-color: rgba(255, 68, 68, 0.25);
  background: rgba(255, 68, 68, 0.04);
}

.meltdown-desc {
  margin: 0 0 var(--space-6);
  font-size: var(--font-sm);
  color: var(--text-muted);
}

.meltdown-confirm,
.meltdown-counting {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  align-items: center;
  text-align: center;
}

.meltdown-confirm-desc {
  margin: 0;
  font-size: var(--font-sm);
  color: var(--text-muted);
}

.meltdown-nonce {
  font-size: var(--font-lg);
  font-weight: 700;
  letter-spacing: 4px;
  color: var(--red);
}

.meltdown-error {
  font-size: var(--font-xs);
  color: var(--red);
}

.countdown-big {
  font-size: var(--font-xl);
  font-weight: 700;
  color: var(--red);
  text-shadow: 0 0 12px rgba(255, 68, 68, 0.45);
}

.loading-state {
  height: 100%;
  min-height: 200px;
  display: grid;
  place-items: center;
  color: var(--text-muted);
  font-size: var(--font-sm);
  letter-spacing: 1px;
  opacity: 0.7;
}

@media (max-width: 900px) {
  .page {
    grid-template-columns: 1fr;
  }
}
</style>
