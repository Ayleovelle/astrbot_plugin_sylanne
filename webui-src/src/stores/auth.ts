import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiFetch, setToken, clearToken, getToken, ApiError } from '../api/client'

export type AuthStatus = 'anon' | 'authing' | 'ok' | 'error'

export const useAuthStore = defineStore('auth', () => {
  const status = ref<AuthStatus>(getToken() ? 'ok' : 'anon')
  const error = ref('')

  // Validate a token by hitting the authenticated /api/state (matches old verifyToken).
  async function login(token: string): Promise<boolean> {
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
  async function verifyExisting(): Promise<boolean> {
    if (!getToken()) {
      status.value = 'anon'
      return false
    }
    try {
      await apiFetch('/api/state')
      status.value = 'ok'
      return true
    } catch {
      clearToken()
      status.value = 'anon'
      return false
    }
  }

  function logout(): void {
    clearToken()
    status.value = 'anon'
    error.value = ''
  }

  return { status, error, login, verifyExisting, logout }
})
