<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { fetchObservationHistory } from '../../api/client'
import type { ObservationHistoryResponse, StateResponse } from '../../api/types'
import { useI18n } from '../../composables/useI18n'
import Modal from '../ui/Modal.vue'
import ObservationTrendChart from './ObservationTrendChart.vue'
import { buildCurrentReadings, createObservationRequestGuard, formatObservationBytes, formatObservationOldest, normalizeHistoryBuckets, type ObservationGroup } from '../../views/monitorObservation'

const props = defineProps<{ open: boolean; group: ObservationGroup | null; session: string; state: StateResponse | null; originRect: DOMRect | null }>()
const emit = defineEmits<{ 'update:open': [value: boolean] }>()
const { t } = useI18n()
const guard = createObservationRequestGuard()
const history = ref<ObservationHistoryResponse | null>(null)
const historyKey = ref('')
const loading = ref(false)
const error = ref('')
let controller: AbortController | null = null
const readings = computed(() => props.group && props.state ? buildCurrentReadings(props.state, props.group) : [])
const requestKey = computed(() => props.group ? `${props.session}:${props.group}` : '')
const visibleHistory = computed(() => historyKey.value === requestKey.value ? history.value : null)
const buckets = computed(() => normalizeHistoryBuckets(visibleHistory.value?.points || []))
const trendState = computed<'loading' | 'error' | 'chart' | 'empty'>(() => {
  if (!visibleHistory.value) return loading.value ? 'loading' : error.value ? 'error' : 'empty'
  if (visibleHistory.value.points.length) return 'chart'
  return 'empty'
})
const title = computed(() => props.group ? t(`monitor.${props.group}`) : '')
function close(): void { guard.invalidate(); controller?.abort(); controller = null; emit('update:open', false) }
async function load(): Promise<void> {
  if (!props.open || !props.group || !props.session) return
  controller?.abort(); controller = new AbortController(); const local = controller; const group = props.group; const session = props.session; const token = guard.begin(session, group)
  loading.value = true; error.value = ''
  try { const result = await fetchObservationHistory({ session, group, max_points: 240 }, local.signal); if (guard.isCurrent(token, session, group)) { history.value = result; historyKey.value = `${session}:${group}`; error.value = '' } }
  catch (cause) { if (guard.isCurrent(token, session, group) && !(cause instanceof Error && cause.name === 'AbortError')) error.value = cause instanceof Error ? cause.message : String(cause) }
  finally { if (guard.isCurrent(token, session, group)) loading.value = false }
}
watch(() => [props.open, props.group, props.session] as const, ([open]) => { if (open) void load(); else { guard.invalidate(); controller?.abort(); controller = null } }, { immediate: true, flush: 'sync' })
onBeforeUnmount(() => { guard.invalidate(); controller?.abort() })
const storage = computed(() => visibleHistory.value?.storage)
const latest = computed(() => buckets.value.at(-1))
const latestValues = computed(() => latest.value ? Object.entries(latest.value.metrics).flatMap(([key, value]) => value.last === undefined ? [] : [{ key, value: value.last }]) : [])
const latestTime = computed(() => latest.value ? new Date(latest.value.toMs).toLocaleString() : t('observation.no_record'))
const description = computed(() => props.group ? t(`observation.${props.group}_description`) : '')
const related = computed(() => {
  const state = props.state; const none = t('common.empty'); if (!state || !props.group) return [none]
  const value = (label: string, item: unknown) => `${label}: ${item ?? none}`
  if (props.group === 'emotion') return [value(t('expr.mode'), state.expression?.mode), value(t('bound.integrity'), state.boundary?.integrity)]
  if (props.group === 'boundary') return [value(t('emo.repair_pressure'), state.emotion?.repair_pressure), value(t('expr.drive'), state.expression?.drive ?? state.expression?.pressure)]
  if (props.group === 'timing') return [value(t('gate.route'), state.gate?.route), value(t('monitor.routing'), Object.values(state.route_stats || state.route_distribution || {}).reduce<number>((sum, item) => sum + Number(item || 0), 0))]
  if (props.group === 'routing') { const entries = Object.entries(state.route_stats || state.route_distribution || {}); return entries.length ? entries.map(([key, value]) => `${key}: ${value}`) : [none] }
  if (props.group === 'gate') return [value(t('gate.route'), state.gate?.route), value(t('expr.mode'), state.expression?.mode)]
  if (props.group === 'expression') return [value(t('gate.route'), state.gate?.route), value(t('emo.warmth'), state.emotion?.warmth)]
  return [value(t('emo.repair_pressure'), state.emotion?.repair_pressure), value(t('expr.mode'), state.expression?.mode)]
})
const readingLabel = (key: string): string => ({ warmth: t('emo.warmth'), arousal: t('emo.arousal'), valence: t('emo.valence'), tension: t('emo.tension'), curiosity: t('emo.curiosity'), repair_pressure: t('emo.repair_pressure'), expression_drive: t('emo.expression_drive'), boundary_firmness: t('emo.boundary_firmness'), integrity: t('bound.integrity'), entropy: t('bound.entropy'), rotation: t('bound.rotation'), repair_rate: t('bound.repair_rate'), surprise: t('gate.surprise'), threshold: t('gate.threshold'), route: t('gate.route'), mode: t('expr.mode'), drive: t('expr.drive'), positive: t('fb.positive'), negative: t('fb.negative'), neutral: t('fb.neutral') }[key] || key)
const storageLimit = computed(() => storage.value?.limit_bytes == null || storage.value.limit_bytes === 0 ? t('observation.unlimited') : formatObservationBytes(storage.value.limit_bytes))
const oldestLabel = computed(() => formatObservationOldest(storage.value?.oldest_ms, t('observation.no_record')))
</script>

<template>
  <Modal :open="open" :title="title" size="lg" variant="observation" :origin-rect="originRect" @update:open="close">
    <section id="observation-chamber" class="chamber" aria-live="polite">
      <div class="primary-grid"><div><h3>{{ t('observation.current') }}</h3><div class="readings"><span v-for="reading in readings" :key="reading.key"><b>{{ readingLabel(reading.key) }}</b> {{ reading.value }}</span></div></div><div><h3>{{ t('observation.trend') }}</h3><p v-if="trendState === 'loading'">{{ t('common.loading') }}</p><p v-else-if="trendState === 'error'">{{ error }} <button type="button" @click="load">{{ t('common.retry') }}</button></p><template v-else-if="trendState === 'chart'"><ObservationTrendChart :buckets="buckets" :label="title" /><p v-if="loading">{{ t('common.loading') }}</p><p v-if="error" class="warning">{{ t('observation.refresh_failed') }} <button type="button" @click="load">{{ t('common.retry') }}</button></p></template><template v-else><p>{{ t('observation.empty') }}</p><p v-if="trendState === 'empty' && loading">{{ t('common.loading') }}</p><p v-if="trendState === 'empty' && error" class="warning">{{ t('observation.refresh_failed') }} <button type="button" @click="load">{{ t('common.retry') }}</button></p></template></div></div>
      <p v-if="visibleHistory?.partial" class="warning">{{ t('observation.partial_warning') }}</p>
      <div class="detail-grid"><p class="description">{{ description }}</p><p><b>{{ t('observation.related') }}</b> {{ related.join(' · ') }}</p><div v-if="visibleHistory" class="metadata"><span>{{ t('observation.latest') }}: {{ latestTime }}</span><span>{{ latestValues.length ? latestValues.map(item => `${readingLabel(item.key)}: ${item.value}`).join(' · ') : t('common.empty') }}</span><span>{{ t('observation.samples') }}: {{ visibleHistory.sample_count }}</span><span>{{ t('observation.storage') }}: {{ formatObservationBytes(storage?.used_bytes) }} / {{ storageLimit }}</span><span>{{ t('observation.oldest') }}: {{ oldestLabel }}</span></div></div>
    </section>
  </Modal>
</template>

<style scoped>
.chamber { display: grid; gap: var(--space-5); }
.primary-grid, .detail-grid { display: grid; grid-template-columns: minmax(0, .8fr) minmax(0, 1.2fr); gap: var(--space-6); }
.primary-grid h3 { margin: 0 0 var(--space-4); font-size: var(--font-sm); }
.description, .metadata { color: var(--text-muted); font-size: var(--font-sm); }
.readings, .metadata { display: flex; flex-wrap: wrap; gap: var(--space-4); }
.readings span { padding: var(--space-3) var(--space-4); border-left: 2px solid var(--accent); background: color-mix(in srgb, var(--card) 88%, var(--accent)); }
.warning { color: var(--accent); }
@media (max-width: 620px) { .primary-grid, .detail-grid { grid-template-columns: 1fr; } }
</style>
