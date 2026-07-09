import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiFetch } from '../api/client'
import type { StateResponse } from '../api/types'
import { useSessionStore } from './session'

// Live /api/state poll. Wave 1 uses HTTP polling; a /ws/state WebSocket upgrade
// (the backend already exposes it) is a Wave-2 enhancement.
export const useLiveStore = defineStore('live', () => {
  const state = ref<StateResponse | null>(null)
  const loading = ref(false)
  const error = ref('')
  let timer: number | null = null
  let inflight = false

  async function fetchOnce(): Promise<void> {
    if (inflight) return
    inflight = true
    const session = useSessionStore().current
    const q = session ? '?session=' + encodeURIComponent(session) : ''
    try {
      loading.value = true
      const data = await apiFetch<StateResponse>('/api/state' + q)
      state.value = data
      error.value = ''
      if (data.sessions) useSessionStore().setSessions(data.sessions)
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'fetch failed'
    } finally {
      loading.value = false
      inflight = false
    }
  }

  function start(intervalMs = 5000): void {
    stop()
    void fetchOnce()
    timer = window.setInterval(() => void fetchOnce(), intervalMs)
  }
  function stop(): void {
    if (timer !== null) {
      clearInterval(timer)
      timer = null
    }
  }

  return { state, loading, error, fetchOnce, start, stop }
})
