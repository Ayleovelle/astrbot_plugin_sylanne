import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { SessionInfo } from '../api/types'

export function sessionId(s: SessionInfo): string {
  return String(s.id || s.session_id || '')
}
export function sessionLabel(s: SessionInfo): string {
  return String(s.name || s.id || s.session_id || '')
}

export const useSessionStore = defineStore('session', () => {
  const sessions = ref<SessionInfo[]>([])
  const current = ref<string>(readStored())

  function readStored(): string {
    try {
      return localStorage.getItem('sylanne_session') || ''
    } catch {
      return ''
    }
  }
  function setCurrent(id: string): void {
    current.value = id
    try {
      localStorage.setItem('sylanne_session', id)
    } catch {
      /* ignore */
    }
  }
  function setSessions(s: SessionInfo[]): void {
    sessions.value = s || []
    if (!current.value && s && s.length) setCurrent(sessionId(s[0]))
  }

  return { sessions, current, setCurrent, setSessions }
})
