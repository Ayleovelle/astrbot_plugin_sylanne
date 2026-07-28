import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiFetch } from '../api/client'
import { isAstrBotPage } from '../api/astrBotBridge'
import type { StateResponse } from '../api/types'
import { useSessionStore } from './session'

// Live /api/state poll. Wave 1 uses HTTP polling; a /ws/state WebSocket upgrade
// (the backend already exposes it) is a Wave-2 enhancement.
export const useLiveStore = defineStore('live', () => {
  const state = ref<StateResponse | null>(null)
  const loading = ref(false)
  const error = ref('')
  let timer: number | null = null
  let generation = 0
  let controller: AbortController | null = null

  function isAbortError(cause: unknown): boolean {
    return cause instanceof Error && cause.name === 'AbortError'
  }

  async function fetchOnce(): Promise<boolean> {
    const requestGeneration = ++generation
    controller?.abort()
    const requestController = new AbortController()
    controller = requestController
    const sessionStore = useSessionStore()
    const requestedSession = sessionStore.current
    const q = requestedSession
      ? '?session=' + encodeURIComponent(requestedSession)
      : ''

    try {
      loading.value = true
      const data = isAstrBotPage()
        ? await apiFetch<StateResponse>('/api/state' + q)
        : await apiFetch<StateResponse>('/api/state' + q, {
            signal: requestController.signal,
          })
      if (
        requestGeneration !== generation ||
        requestController.signal.aborted ||
        requestedSession !== sessionStore.current
      ) {
        return false
      }

      if (data.sessions) sessionStore.setSessions(data.sessions)
      state.value = data
      error.value = ''
      return true
    } catch (cause) {
      if (
        requestGeneration !== generation ||
        requestController.signal.aborted ||
        requestedSession !== sessionStore.current ||
        isAbortError(cause)
      ) {
        return false
      }
      error.value = cause instanceof Error ? cause.message : 'fetch failed'
      return false
    } finally {
      if (requestGeneration === generation) {
        loading.value = false
        if (controller === requestController) controller = null
      }
    }
  }

  function start(intervalMs = 5000): void {
    stop()
    void fetchOnce()
    timer = window.setInterval(() => void fetchOnce(), intervalMs)
  }
  function stop(): void {
    generation += 1
    controller?.abort()
    controller = null
    if (timer !== null) {
      clearInterval(timer)
      timer = null
    }
    loading.value = false
  }

  return { state, loading, error, fetchOnce, start, stop }
})
