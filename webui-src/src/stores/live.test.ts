import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { StateResponse } from '../api/types'
import { useLiveStore } from './live'
import { useSessionStore } from './session'

const { apiFetchMock } = vi.hoisted(() => ({
  apiFetchMock: vi.fn(),
}))

vi.mock('../api/client', () => ({
  apiFetch: apiFetchMock,
}))

interface Deferred<T> {
  promise: Promise<T>
  resolve: (value: T) => void
  reject: (reason: unknown) => void
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function stateFor(session: string): StateResponse {
  return { session_id: session, current_session: session }
}

function requestSignal(index: number): AbortSignal | undefined {
  const options = apiFetchMock.mock.calls[index]?.[1] as
    | { signal?: AbortSignal }
    | undefined
  return options?.signal
}

function makeAbortError(): Error {
  const error = new Error('aborted')
  error.name = 'AbortError'
  return error
}

describe('live state request isolation', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiFetchMock.mockReset()
  })

  afterEach(() => {
    useLiveStore().stop()
  })

  it('starts session B immediately and ignores a late session A response', async () => {
    const requestA = deferred<StateResponse>()
    const requestB = deferred<StateResponse>()
    apiFetchMock
      .mockImplementationOnce(() => requestA.promise)
      .mockImplementationOnce(() => requestB.promise)

    const session = useSessionStore()
    const live = useLiveStore()
    session.setCurrent('A')
    const resultA = live.fetchOnce()
    session.setCurrent('B')
    const resultB = live.fetchOnce()

    requestB.resolve(stateFor('B'))
    const appliedB = await resultB
    requestA.resolve(stateFor('A'))
    const appliedA = await resultA

    expect(apiFetchMock).toHaveBeenCalledTimes(2)
    expect(apiFetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/state?session=A',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    )
    expect(apiFetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/state?session=B',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    )
    expect(requestSignal(0)?.aborted).toBe(true)
    expect(requestSignal(1)?.aborted).toBe(false)
    expect(appliedB).toBe(true)
    expect(appliedA).toBe(false)
    expect(live.state).toEqual(stateFor('B'))
  })

  it('keeps a stale session A rejection silent while B is loading', async () => {
    const requestA = deferred<StateResponse>()
    const requestB = deferred<StateResponse>()
    apiFetchMock
      .mockImplementationOnce(() => requestA.promise)
      .mockImplementationOnce(() => requestB.promise)

    const session = useSessionStore()
    const live = useLiveStore()
    session.setCurrent('A')
    const resultA = live.fetchOnce()
    session.setCurrent('B')
    const resultB = live.fetchOnce()

    requestA.reject(new Error('stale A failed'))
    expect(await resultA).toBe(false)
    expect(live.error).toBe('')
    expect(live.loading).toBe(true)

    requestB.resolve(stateFor('B'))
    expect(await resultB).toBe(true)
    expect(live.error).toBe('')
    expect(live.loading).toBe(false)
    expect(live.state).toEqual(stateFor('B'))
  })

  it('rejects a response when the requested session is no longer selected', async () => {
    const requestA = deferred<StateResponse>()
    apiFetchMock.mockImplementationOnce(() => requestA.promise)

    const session = useSessionStore()
    const live = useLiveStore()
    session.setCurrent('A')
    const resultA = live.fetchOnce()
    session.setCurrent('B')

    requestA.resolve(stateFor('A'))

    expect(await resultA).toBe(false)
    expect(live.state).toBeNull()
    expect(live.error).toBe('')
  })

  it('applies the initial default response while selecting its first session', async () => {
    const response = {
      ...stateFor('A'),
      sessions: [{ id: 'A' }, { id: 'B' }],
    }
    apiFetchMock.mockResolvedValueOnce(response)

    const session = useSessionStore()
    const live = useLiveStore()

    expect(session.current).toBe('')
    expect(await live.fetchOnce()).toBe(true)
    expect(session.current).toBe('A')
    expect(live.state).toEqual(response)
  })

  it('invalidates a late response and resets loading when stopped', async () => {
    const requestA = deferred<StateResponse>()
    apiFetchMock.mockImplementationOnce(() => requestA.promise)

    useSessionStore().setCurrent('A')
    const live = useLiveStore()
    const resultA = live.fetchOnce()
    const signal = requestSignal(0)

    live.stop()
    const loadingAfterStop = live.loading
    const abortedAfterStop = signal?.aborted
    requestA.resolve(stateFor('A'))

    expect(await resultA).toBe(false)
    expect(abortedAfterStop).toBe(true)
    expect(loadingAfterStop).toBe(false)
    expect(live.state).toBeNull()
    expect(live.error).toBe('')
  })

  it('does not report an aborted current request as an error', async () => {
    apiFetchMock.mockImplementation(
      (_path: string, options?: { signal?: AbortSignal }) =>
        new Promise<StateResponse>((_resolve, reject) => {
          if (!options?.signal) {
            reject(new Error('missing abort signal'))
            return
          }
          options.signal.addEventListener(
            'abort',
            () => reject(makeAbortError()),
            { once: true },
          )
        }),
    )

    const live = useLiveStore()
    const result = live.fetchOnce()
    live.stop()

    expect(await result).toBe(false)
    expect(live.error).toBe('')
    expect(live.loading).toBe(false)
  })
})
