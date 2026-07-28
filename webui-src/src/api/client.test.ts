import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  apiBase,
  apiFetch,
  fetchObservationHistory,
  usesHostAuthentication,
} from './client'

function stubToken(token = 'standalone-secret'): void {
  vi.stubGlobal('localStorage', {
    getItem: vi.fn((key: string) => (key === 'sylanne_token' ? token : null)),
    setItem: vi.fn(),
    removeItem: vi.fn(),
  })
}

function jsonResponse(data: unknown): Response {
  return {
    ok: true,
    status: 200,
    statusText: 'OK',
    text: vi.fn().mockResolvedValue(JSON.stringify(data)),
  } as unknown as Response
}

describe('apiBase', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it.each([
    [
      '/api/plug/astrbot_plugin_sylanne/dashboard',
      '/api/plug/astrbot_plugin_sylanne',
    ],
    [
      '/api/v1/plugins/extensions/astrbot_plugin_sylanne/dashboard',
      '/api/v1/plugins/extensions/astrbot_plugin_sylanne',
    ],
    ['/dashboard', ''],
  ])('preserves the host route prefix for %s', (pathname, expected) => {
    vi.stubGlobal('location', { pathname })

    expect(apiBase()).toBe(expected)
  })

  it('does not treat a plugin-name substring in a standalone path as host routing', () => {
    vi.stubGlobal('window', {})
    vi.stubGlobal('location', {
      pathname: '/dashboard/astrbot_plugin_sylanne-preview',
    })

    expect(apiBase()).toBe('')
    expect(usesHostAuthentication()).toBe(false)
  })

  it('uses the AstrBot bridge and converts query strings into GET params', async () => {
    const apiGet = vi.fn().mockResolvedValue({ tick_count: 7 })
    const apiPost = vi.fn()
    const fetchMock = vi.fn()
    vi.stubGlobal('window', { AstrBotPluginPage: { apiGet, apiPost } })
    vi.stubGlobal('location', {
      pathname: '/api/plugin/page/content/astrbot_plugin_sylanne/dashboard/index.html',
    })
    vi.stubGlobal('fetch', fetchMock)
    stubToken()

    await expect(apiFetch('/api/state?session=friend%3A42')).resolves.toEqual({ tick_count: 7 })
    expect(apiGet).toHaveBeenCalledWith('api/state', { session: 'friend:42' })
    expect(fetchMock).not.toHaveBeenCalled()
    expect(usesHostAuthentication()).toBe(true)
  })

  it('uses the AstrBot bridge for observation history without passing its signal', async () => {
    const apiGet = vi.fn().mockResolvedValue({
      schema_version: 'sylanne.observation.history.v1',
      session: 'friend:42',
      group: 'timing',
      points: [],
      sample_count: 0,
      downsampled: false,
      partial: false,
      storage: {
        used_bytes: 0,
        limit_bytes: null,
        oldest_ms: null,
        segment_count: 0,
        cleanup_active: false,
      },
    })
    vi.stubGlobal('window', {
      AstrBotPluginPage: { apiGet, apiPost: vi.fn() },
    })
    vi.stubGlobal('location', {
      pathname: '/api/plugin/page/content/astrbot_plugin_sylanne/dashboard/index.html',
    })
    vi.stubGlobal('fetch', vi.fn())
    const signal = new AbortController().signal

    await fetchObservationHistory(
      {
        session: 'friend:42',
        group: 'timing',
        from_ms: 10,
        max_points: 12,
      },
      signal,
    )

    expect(apiGet).toHaveBeenCalledWith('api/observation_history', {
      session: 'friend:42',
      group: 'timing',
      from_ms: '10',
      max_points: '12',
    })
  })

  it('uses the AstrBot bridge for POST without leaking standalone auth', async () => {
    const apiGet = vi.fn()
    const apiPost = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal('window', { AstrBotPluginPage: { apiGet, apiPost } })
    vi.stubGlobal('location', {
      pathname: '/api/plugin/page/content/astrbot_plugin_sylanne/dashboard/index.html',
    })
    vi.stubGlobal('fetch', vi.fn())
    stubToken()

    await expect(
      apiFetch('/api/settings', { method: 'POST', body: { enabled: true } }),
    ).resolves.toEqual({ ok: true })
    expect(apiPost).toHaveBeenCalledWith('api/settings', { enabled: true })
  })

  it.each([
    ['/api/settings?session=a', { method: 'POST', body: {} }, 'POST does not support query'],
    ['/api/state', { method: 'DELETE' }, 'does not support DELETE'],
    [
      '/api/state',
      { signal: new AbortController().signal },
      'does not support request cancellation',
    ],
  ])('rejects bridge requests whose semantics cannot be preserved', async (path, opts, message) => {
    const apiGet = vi.fn()
    const apiPost = vi.fn()
    vi.stubGlobal('window', { AstrBotPluginPage: { apiGet, apiPost } })
    vi.stubGlobal('location', {
      pathname: '/api/plugin/page/content/astrbot_plugin_sylanne/dashboard/index.html',
    })
    vi.stubGlobal('fetch', vi.fn())

    const error = await apiFetch(path, opts).catch((caught: unknown) => caught)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 0 })
    expect((error as Error).message).toContain(message)
    expect(apiGet).not.toHaveBeenCalled()
    expect(apiPost).not.toHaveBeenCalled()
  })

  it('uses AstrBot host auth on the legacy wrapper without a Sylanne bearer', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ tick_count: 9 }))
    vi.stubGlobal('window', {})
    vi.stubGlobal('location', {
      pathname: '/api/plug/astrbot_plugin_sylanne/dashboard',
    })
    vi.stubGlobal('fetch', fetchMock)
    stubToken()

    await expect(apiFetch('/api/state')).resolves.toEqual({ tick_count: 9 })
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(fetchMock.mock.calls[0][0]).toBe(
      '/api/plug/astrbot_plugin_sylanne/api/state',
    )
    expect(fetchMock.mock.calls[0][1].headers).not.toHaveProperty('Authorization')
    expect(usesHostAuthentication()).toBe(true)
  })

  it('keeps bearer authentication for the standalone 2718 server', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ tick_count: 11 }))
    vi.stubGlobal('window', {})
    vi.stubGlobal('location', { pathname: '/dashboard' })
    vi.stubGlobal('fetch', fetchMock)
    stubToken()

    await expect(apiFetch('/api/state')).resolves.toEqual({ tick_count: 11 })
    expect(fetchMock.mock.calls[0][1].headers).toMatchObject({
      Authorization: 'Bearer standalone-secret',
    })
    expect(usesHostAuthentication()).toBe(false)
  })

  it('fetches standalone observation history with a relative URL, bearer, and signal', async () => {
    const payload = {
      schema_version: 'sylanne.observation.history.v1',
      session: 'standalone',
      group: 'emotion',
      points: [],
      sample_count: 0,
      downsampled: false,
      partial: false,
      storage: {
        used_bytes: 0,
        limit_bytes: null,
        oldest_ms: null,
        segment_count: 0,
        cleanup_active: false,
      },
    }
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(payload))
    vi.stubGlobal('window', {})
    vi.stubGlobal('location', { pathname: '/dashboard' })
    vi.stubGlobal('fetch', fetchMock)
    stubToken()
    const signal = new AbortController().signal

    await expect(
      fetchObservationHistory(
        {
          session: 'standalone',
          group: 'emotion',
          from_ms: 10,
          to_ms: 20,
          max_points: 5,
        },
        signal,
      ),
    ).resolves.toEqual(payload)

    expect(fetchMock.mock.calls[0][0]).toBe(
      '/api/observation_history?session=standalone&group=emotion&from_ms=10&to_ms=20&max_points=5',
    )
    expect(fetchMock.mock.calls[0][1]).toMatchObject({
      signal,
      headers: { Authorization: 'Bearer standalone-secret' },
    })
  })
})
