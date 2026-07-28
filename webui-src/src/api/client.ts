// Single API client for the frozen backend contract.
// - Bearer token (localStorage 'sylanne_token')
// - CSRF double-submit: capture csrf_token from any JSON body, echo as
//   X-CSRF-Token on non-GET (the backend hands it back inside /api/state).
// - 401 anywhere -> clear token + notify (hard logout), matching the old UI.
// - Resolves /api/* under BOTH serving contexts: standalone (port 2718, '/')
//   and AstrBot-native (served under '/astrbot_plugin_sylanne/...').

import { devMock } from './devMock'
import { bridgeFetch, getAstrBotBridge } from './astrBotBridge'
import type {
  ObservationHistoryParams,
  ObservationHistoryResponse,
} from './types'

const TOKEN_KEY = 'sylanne_token'
let csrfToken = ''

export function apiBase(): string {
  const p = typeof location !== 'undefined' ? location.pathname : ''
  const pluginName = 'astrbot_plugin_sylanne'
  const segments = p.split('/')
  const pluginIndex = segments.indexOf(pluginName)
  return pluginIndex >= 0 ? segments.slice(0, pluginIndex + 1).join('/') : ''
}

export function usesHostAuthentication(): boolean {
  return getAstrBotBridge() !== null || apiBase() !== ''
}

export function getToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) || ''
  } catch {
    return ''
  }
}
export function setToken(t: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, t)
  } catch {
    /* ignore */
  }
}
export function clearToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* ignore */
  }
}

type Handler = () => void
let onUnauthorized: Handler | null = null
export function setUnauthorizedHandler(h: Handler): void {
  onUnauthorized = h
}

export class ApiError extends Error {
  status: number
  data?: unknown
  constructor(status: number, message: string, data?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.data = data
  }
}

export function fetchObservationHistory(
  params: ObservationHistoryParams,
  signal?: AbortSignal,
): Promise<ObservationHistoryResponse> {
  const query = new URLSearchParams()
  query.set('session', params.session)
  query.set('group', params.group)
  if (params.from_ms !== undefined) {
    query.set('from_ms', String(params.from_ms))
  }
  if (params.to_ms !== undefined) {
    query.set('to_ms', String(params.to_ms))
  }
  if (params.max_points !== undefined) {
    query.set('max_points', String(params.max_points))
  }
  const path = `/api/observation_history?${query.toString()}`
  if (getAstrBotBridge()) {
    return apiFetch<ObservationHistoryResponse>(path)
  }
  return apiFetch<ObservationHistoryResponse>(path, { signal })
}

export interface ApiOptions {
  method?: string
  body?: unknown
  signal?: AbortSignal
  auth?: boolean
  /** internal — set on the one allowed retry to prevent recursion */
  _retried?: boolean
}

export async function apiFetch<T = unknown>(path: string, opts: ApiOptions = {}): Promise<T> {
  const bridge = getAstrBotBridge()
  if (bridge) {
    try {
      return await bridgeFetch<T>(bridge, path, opts)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error || 'bridge failed')
      throw new ApiError(0, message)
    }
  }

  const method = (opts.method || 'GET').toUpperCase()
  const standaloneAuth = !usesHostAuthentication()
  const headers: Record<string, string> = {}
  const token = getToken()
  if (standaloneAuth && opts.auth !== false && token) {
    headers['Authorization'] = 'Bearer ' + token
  }

  let body: BodyInit | undefined
  if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(opts.body)
  }
  // Remember whether csrfToken was empty when THIS request was built — a
  // hard-load straight into a page that immediately POSTs (e.g. #/config)
  // can race /api/state's csrf_token capture, so a 403 in that specific
  // case is worth one recovery retry (below), not just a hard failure.
  const hadNoCsrfAtSend = standaloneAuth && method !== 'GET' && !csrfToken
  if (standaloneAuth && method !== 'GET' && csrfToken) {
    headers['X-CSRF-Token'] = csrfToken
  }

  // DEV-only mock (dead-code-stripped from production: import.meta.env.DEV is a
  // build-time constant). Used ONLY as a fallback when a mockable path yields no
  // usable response — a real backend (via the dev proxy) always wins.
  const mockable = import.meta.env.DEV ? devMock(path, method) : undefined
  const returnMock = (m: unknown): T => {
    if (m && typeof m === 'object') {
      const c = (m as Record<string, unknown>).csrf_token
      if (typeof c === 'string' && c) csrfToken = c
    }
    return m as T
  }

  let res: Response
  try {
    res = await fetch(apiBase() + path, { method, headers, body, signal: opts.signal })
  } catch (err) {
    if (mockable !== undefined) return returnMock(mockable)
    throw err
  }

  if (res.status === 401) {
    if (standaloneAuth) {
      clearToken()
      if (onUnauthorized) onUnauthorized()
    }
    throw new ApiError(401, 'unauthorized')
  }

  // CSRF race recovery: a non-GET sent before /api/state ever populated
  // csrfToken can get rejected with 403. Fetch /api/state once (it carries
  // csrf_token in its body) and retry the original request exactly once.
  // _retried guards against ever looping — the retry cannot retry again.
  if (res.status === 403 && !opts._retried && hadNoCsrfAtSend) {
    try {
      await apiFetch('/api/state')
    } catch {
      /* fall through to normal 403 handling below */
    }
    if (csrfToken) {
      return apiFetch<T>(path, { ...opts, _retried: true })
    }
  }

  const text = await res.text()
  let data: unknown = undefined
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }
  // DEV: no usable JSON object (proxy error / SPA index.html fallback / non-ok)
  // for a mockable path -> use the mock.
  if (mockable !== undefined && (!res.ok || data === null || typeof data !== 'object')) {
    return returnMock(mockable)
  }

  if (data && typeof data === 'object') {
    const c = (data as Record<string, unknown>).csrf_token
    if (typeof c === 'string' && c) csrfToken = c
  }
  if (!res.ok) {
    const msg =
      (data && typeof data === 'object' && typeof (data as Record<string, unknown>).error === 'string'
        ? ((data as Record<string, unknown>).error as string)
        : '') || res.statusText
    throw new ApiError(res.status, msg, data)
  }
  return data as T
}
