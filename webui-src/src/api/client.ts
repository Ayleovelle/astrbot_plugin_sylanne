// Single API client for the frozen backend contract.
// - Bearer token (localStorage 'sylanne_token')
// - CSRF double-submit: capture csrf_token from any JSON body, echo as
//   X-CSRF-Token on non-GET (the backend hands it back inside /api/state).
// - 401 anywhere -> clear token + notify (hard logout), matching the old UI.
// - Resolves /api/* under BOTH serving contexts: standalone (port 2718, '/')
//   and AstrBot-native (served under '/astrbot_plugin_sylanne/...').

import { devMock } from './devMock'

const TOKEN_KEY = 'sylanne_token'
let csrfToken = ''

export function apiBase(): string {
  const p = typeof location !== 'undefined' ? location.pathname : ''
  return p.indexOf('/astrbot_plugin_sylanne') >= 0 ? '/astrbot_plugin_sylanne' : ''
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

export interface ApiOptions {
  method?: string
  body?: unknown
  signal?: AbortSignal
  auth?: boolean
}

export async function apiFetch<T = unknown>(path: string, opts: ApiOptions = {}): Promise<T> {
  const method = opts.method || 'GET'
  const headers: Record<string, string> = {}
  const token = getToken()
  if (opts.auth !== false && token) headers['Authorization'] = 'Bearer ' + token

  let body: BodyInit | undefined
  if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(opts.body)
  }
  if (method !== 'GET' && csrfToken) headers['X-CSRF-Token'] = csrfToken

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
    clearToken()
    if (onUnauthorized) onUnauthorized()
    throw new ApiError(401, 'unauthorized')
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
