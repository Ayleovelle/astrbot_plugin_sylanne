import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  apiFetch,
  setToken,
  clearToken,
  getToken,
  ApiError,
  usesHostAuthentication,
} from '../api/client'

export type AuthStatus = 'anon' | 'authing' | 'ok' | 'error'

export const useAuthStore = defineStore('auth', () => {
  const status = ref<AuthStatus>(usesHostAuthentication() || getToken() ? 'ok' : 'anon')
  const error = ref('')

  // Validate a token by hitting the authenticated /api/state (matches old verifyToken).
  async function login(token: string): Promise<boolean> {
    if (usesHostAuthentication()) return verifyExisting()
    status.value = 'authing'
    error.value = ''
    setToken(token)
    try {
      await apiFetch('/api/state')
      status.value = 'ok'
      return true
    } catch (e) {
      clearToken()
      status.value = 'error'
      error.value = e instanceof ApiError ? e.message : 'auth failed'
      return false
    }
  }

  // On app load, verify a persisted token before admitting to the dashboard.
  // Only a real 401 invalidates the token; a transient network/5xx failure
  // must NOT log the user out (the dashboard surfaces its own offline state).
  async function verifyExisting(): Promise<boolean> {
    const hostAuth = usesHostAuthentication()
    if (!hostAuth && !getToken()) {
      status.value = 'anon'
      return false
    }
    try {
      await apiFetch('/api/state')
      status.value = 'ok'
      return true
    } catch (e) {
      if (hostAuth) {
        status.value = 'error'
        error.value = e instanceof Error ? e.message : 'host auth failed'
        return false
      }
      if (e instanceof ApiError && e.status === 401) {
        // apiFetch already cleared the token on 401; mirror the state here.
        clearToken()
        status.value = 'anon'
        return false
      }
      status.value = 'ok'
      return true
    }
  }

  function logout(): void {
    if (usesHostAuthentication()) {
      status.value = 'ok'
      error.value = ''
      return
    }
    clearToken()
    status.value = 'anon'
    error.value = ''
  }

  return { status, error, login, verifyExisting, logout }
})
