import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useSessionStore } from './session'

function stubStorage(stored: string): {
  setItem: ReturnType<typeof vi.fn>
} {
  const setItem = vi.fn()
  vi.stubGlobal('localStorage', {
    getItem: vi.fn((key: string) =>
      key === 'sylanne_session' ? stored : null,
    ),
    setItem,
  })
  return { setItem }
}

describe('session selection reconciliation', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('preserves the current id while it remains in the session list', () => {
    const { setItem } = stubStorage('B')
    const session = useSessionStore()

    session.setSessions([{ id: 'A' }, { session_id: 'B' }])

    expect(session.current).toBe('B')
    expect(setItem).not.toHaveBeenCalled()
  })

  it('falls back to the first session when the current id disappears', () => {
    const { setItem } = stubStorage('missing')
    const session = useSessionStore()

    session.setSessions([{ id: 'A' }, { id: 'B' }])

    expect(session.current).toBe('A')
    expect(setItem).toHaveBeenLastCalledWith('sylanne_session', 'A')
  })

  it('clears the current id when the session list is empty', () => {
    const { setItem } = stubStorage('B')
    const session = useSessionStore()

    session.setSessions([])

    expect(session.current).toBe('')
    expect(setItem).toHaveBeenLastCalledWith('sylanne_session', '')
  })
})
