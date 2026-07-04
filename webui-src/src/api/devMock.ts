// DEV-ONLY mock. Gated by `import.meta.env.DEV`, so Vite dead-code-eliminates
// this whole path from the production singlefile build (import.meta.env.DEV
// === false at build time). It exists purely so `pnpm dev` can show the full
// dashboard with plausible data when no real backend is running — and it only
// kicks in as a FALLBACK after a real fetch fails, so a live backend (via the
// dev proxy) always wins. This is NOT the old shipped mock-fallback anti-pattern.

function jitter(base: number, amp = 0.04): number {
  return Math.max(0, Math.min(1, base + (Math.random() - 0.5) * amp))
}

function mockState(): Record<string, unknown> {
  const layers: Record<string, unknown> = {}
  for (let i = 1; i <= 7; i++) {
    layers['L' + i] = {
      avg: 1.5 + Math.random() * 5,
      p95: 4 + Math.random() * 8,
      count: 40 + Math.floor(Math.random() * 200),
    }
  }
  return {
    schema_version: 3,
    runtime: 'dev-mock',
    current_session: 'qq:private:2300184498',
    session_id: 'qq:private:2300184498',
    emotion: {
      warmth: jitter(0.62),
      arousal: jitter(0.41),
      valence: jitter(0.35),
      tension: jitter(0.28),
      curiosity: jitter(0.55),
      repair_pressure: jitter(0.18),
      expression_drive: jitter(0.71),
      boundary_firmness: jitter(0.66),
    },
    boundary: {
      integrity: jitter(0.9, 0.02),
      entropy: jitter(0.12),
      rotation: jitter(0.34),
      repair_rate: jitter(0.8, 0.02),
    },
    route_distribution: {
      FAST: 120 + Math.floor(Math.random() * 10),
      NORMAL: 44 + Math.floor(Math.random() * 8),
      FULL: 190 + Math.floor(Math.random() * 12),
      SKIP: 22 + Math.floor(Math.random() * 5),
    },
    gate: {
      surprise: jitter(0.33),
      threshold: 0.4,
      route: ['FAST', 'NORMAL', 'FULL'][Math.floor(Math.random() * 3)],
    },
    expression: {
      mode: ['speak', 'hold', 'reach'][Math.floor(Math.random() * 3)],
      pressure: jitter(0.71),
      threshold: 0.4,
    },
    feedback: { positive: 14, negative: 2, neutral: 5 },
    layers,
    sessions: [
      { id: 'qq:private:2300184498', name: 'qq:private:2300184498', ticks: 412 },
      { id: 'qq:group:10086', name: 'qq:group:10086', ticks: 88 },
    ],
    csrf_token: 'dev-mock-csrf',
  }
}

// Return a mock payload for a known GET path, or undefined to signal "no mock".
export function devMock(path: string, method: string): unknown {
  const clean = path.split('?')[0]
  if (method === 'GET' && clean.endsWith('/api/state')) return mockState()
  return undefined
}
