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

export interface PersonalitySixItem {
  name?: string
  value?: number
  color?: string
}

export interface PersonalityDriftItem {
  time?: string
  text?: string
}

export interface PersonalityState {
  five?: Record<string, number>
  six?: PersonalitySixItem[]
  drift?: PersonalityDriftItem[]
  [k: string]: unknown
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
  personality?: PersonalityState
  feedback?: FeedbackState
  sessions?: SessionInfo[]
  theme?: string
  life_simulation?: Record<string, unknown>
  [k: string]: unknown
}

// --- v2core cognition (Wave: cognitive-cycle page) ---
// Same defensive philosophy as StateResponse: the backend's v2core payload
// shape varies by engine build, so every field is optional and read with
// fallbacks by the adapters.

export interface V2CoreDecision {
  action?: string
  g_speak?: number
  g_hold?: number
  g_reach?: number
  eff_drive?: number
  express_at?: number
  outcome?: string
  silent_reason?: string
  quality?: number
}

export interface V2CoreDomains {
  emotion?: {
    warmth?: number
    valence?: number
    arousal?: number
    tension?: number
    volatility?: number
    trend?: number
    unexpressed?: number
    line?: string
  }
  usermodel?: {
    synchrony?: number
    grip?: number
    rhythm_ema?: number
    disposition?: {
      warmth?: number
      engagement?: number
      defensiveness?: number
      distress?: number
    }
    line?: string
  }
  narrative?: {
    epoch?: number
    rigidity?: number
    ossification?: number
    anchor_count?: number
    anchor_total?: number
    line?: string
  }
  distill?: {
    fidelity?: number
    samples?: number
    mean_error?: number
  }
}

export interface V2CoreStateResponse {
  enabled?: boolean
  session?: string
  sessions?: SessionInfo[]
  fragment?: string
  decision?: V2CoreDecision
  body?: Record<string, unknown>
  domains?: V2CoreDomains
  [k: string]: unknown
}

// --- settings / config (Wave: config page) ---

export interface SettingsSchemaEntry {
  description?: string
  type?: string
  default?: unknown
  invisible?: boolean
  options?: string[]
}

export interface ProviderInfo {
  id?: string
  name?: string
  type?: string
}

export interface SettingsResponse {
  schema?: Record<string, SettingsSchemaEntry>
  values?: Record<string, unknown>
  providers?: ProviderInfo[]
  [k: string]: unknown
}

// --- computation logs (Wave: logs page) ---

export interface ComputationLogEntry {
  route?: string
  time?: string
  ts?: number
  msg?: string
  text?: string
  message?: string
  layers?: Record<string, unknown>
  [k: string]: unknown
}

export interface ComputationLogsResponse {
  logs?: ComputationLogEntry[]
  total?: number
  total_for_session?: number
  session?: string
  [k: string]: unknown
}

// --- memory pools (Wave: memory page) ---

export interface MemoryPoolItem {
  content?: string
  text?: string
  summary?: string
  weight?: number
  age?: number
  created_at?: string
  [k: string]: unknown
}

export interface MemoryPoolsResponse {
  layers?: {
    l1_hot?: {
      label?: string
      count?: number
      items?: MemoryPoolItem[]
    }
    l2_warm?: {
      label?: string
      count?: number
      items?: MemoryPoolItem[]
    }
    l3_cold?: {
      nodes?: MemoryPoolItem[]
      edges?: MemoryPoolItem[]
    }
  }
  hot?: MemoryPoolItem[]
  warm?: MemoryPoolItem[]
  cold?: MemoryPoolItem[]
  summary?: {
    total?: number
    l1_count?: number
    l2_count?: number
    l3_node_count?: number
    l3_edge_count?: number
    embedded?: number
    avg_weight?: number
    avg_temperature?: number
  }
  sessions?: SessionInfo[]
  session?: string
  mode?: string
  [k: string]: unknown
}

// --- life simulation (Wave: life page) ---

export interface LifeWorld {
  phase?: string
  local_date?: string
  energy?: number
  focus?: number
  current_activity_id?: string
  last_tick_at?: string
  seconds_since_tick?: number
}

export interface LifeStatusResponse {
  available?: boolean
  enabled?: boolean
  world?: LifeWorld
  current_activity?: Record<string, unknown>
  counts?: {
    simulation_count?: number
    outreach_count?: number
    events_total?: number
  }
  timing?: Record<string, unknown>
  recent_events?: unknown[]
  distribution?: Record<string, unknown>
  prompt_fragment_preview?: string
  [k: string]: unknown
}

export interface LifeEvent {
  event_id?: string
  text?: string
  event_type?: string
  timestamp?: number
  source?: string
  importance?: number
  wants_to_share?: boolean
  shared?: boolean
  project_id?: string
  origin_session?: string
  privacy_level?: string
  [k: string]: unknown
}

export interface LifeEventsResponse {
  events?: LifeEvent[]
  available?: boolean
  [k: string]: unknown
}

export interface LifeProject {
  title?: string
  kind?: string
  state?: string
  progress?: number
  share_policy?: string
  effectiveness?: number
  [k: string]: unknown
}

export interface LifeSkill {
  name?: string
  effectiveness?: number
  success_count?: number
  failure_count?: number
  [k: string]: unknown
}

export interface LifeProjectsResponse {
  projects?: LifeProject[]
  skills?: LifeSkill[]
  available?: boolean
  [k: string]: unknown
}

export interface LifeAuditEntry {
  kind?: string
  intent_id?: string
  ts?: number
  feedback_status?: string
  [k: string]: unknown
}

export interface LifeAuditResponse {
  audit?: Record<string, LifeAuditEntry[]>
  available?: boolean
  [k: string]: unknown
}

// --- admin diagnostics (Wave: admin page) ---
// Three new read-only endpoints exposing internal KV/epoch/quarantine state
// for debugging the session persistence pipeline. Same permissive-optional
// philosophy as the rest of this file — every field may be absent or null
// depending on backend state (e.g. inspect before any session has hydrated).

export interface AdminKvSlot {
  exists?: boolean | null
  bytes?: number | null
  version?: string | null
  crc_valid?: boolean | null
  error?: boolean
  [k: string]: unknown
}

export interface AdminThroatStats {
  reject_count?: number
  rebuild_count?: number
  dropped_no_loop_count?: number
  active_sessions?: number
  tracked_epochs?: number
  [k: string]: unknown
}

export interface AdminInspectResponse {
  session?: string
  kv_keys?: {
    primary?: AdminKvSlot | null
    v2_backup?: AdminKvSlot | null
    quarantine?: AdminKvSlot | null
    [k: string]: AdminKvSlot | null | undefined
  } | null
  hydrated?: boolean | null
  incarnation_epoch?: number | null
  current_epoch?: number | null
  epoch_matches?: boolean | null
  queue_depth?: number | null
  throat_stats?: AdminThroatStats | null
  has_pending_delete?: boolean | null
  [k: string]: unknown
}

export interface AdminQuarantineSession {
  count?: number
  items?: unknown[]
  error?: boolean
  [k: string]: unknown
}

export interface AdminQuarantineResponse {
  session?: string
  sessions?: Record<string, AdminQuarantineSession>
  total_entries?: number
  note?: string
  [k: string]: unknown
}

export interface AdminPendingDeleteEntry {
  epoch?: number
  ts?: number
  [k: string]: unknown
}

export interface AdminPendingDeletesResponse {
  scan_done?: boolean | null
  entries?: Record<string, AdminPendingDeleteEntry>
  count?: number
  [k: string]: unknown
}
