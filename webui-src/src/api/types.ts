// Permissive types for the frozen backend responses. The backend has minor
// shape variance across engine variants (the old UI's adaptState() normalized
// several forms), so fields are optional and adapters read defensively.

export interface SessionInfo {
  id?: string
  session_id?: string
  name?: string
  ticks?: number
  tick_count?: number
  [k: string]: unknown
}

export interface EmotionState {
  warmth?: number
  arousal?: number
  valence?: number
  tension?: number
  curiosity?: number
  repair_pressure?: number
  expression_drive?: number
  boundary_firmness?: number
  [k: string]: number | undefined
}

export interface RouteDistribution {
  FAST?: number
  NORMAL?: number
  FULL?: number
  SKIP?: number
  [k: string]: number | undefined
}

export interface BoundaryState {
  integrity?: number
  entropy?: number
  stability?: number
  rotation?: number
  repair_rate?: number
  phase_transitions?: number
  [k: string]: number | undefined
}

export interface ExpressionState {
  pressure?: number
  drive?: number
  threshold?: number
  ratio?: number
  mode?: string
  count?: number
  [k: string]: unknown
}

export interface GateState {
  precision?: number
  mean_surprise?: number
  surprise?: number
  threshold?: number
  route?: string
  history_len?: number
  history?: number[]
  [k: string]: unknown
}

export interface FeedbackState {
  accepted?: number
  ignored?: number
  rejected?: number
  positive?: number
  negative?: number
  neutral?: number
  [k: string]: number | undefined
}

export interface TimingLayer {
  avg?: number
  avg_ms?: number
  p95?: number
  p95_ms?: number
  count?: number
}

export interface StateResponse {
  schema_version?: number
  runtime?: string
  current_session?: string
  session_id?: string
  emotion?: EmotionState
  gate?: GateState
  route_stats?: Record<string, number>
  route_distribution?: RouteDistribution
  boundary?: BoundaryState
  expression?: ExpressionState
  timing?: Record<string, number>
  layers?: Record<string, TimingLayer>
  personality?: Record<string, unknown>
  feedback?: FeedbackState
  sessions?: SessionInfo[]
  theme?: string
  life_simulation?: Record<string, unknown>
  [k: string]: unknown
}
