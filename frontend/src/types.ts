export interface Source { id: number; name: string; url: string | null; license: string | null; attribution: string | null }
export interface Destination { id: number; name: string; country: string | null; lat: number; lon: number }
export type Hours = Record<string, [string, string][]>
export interface Place {
  id: number
  destination_id: number
  owner_id: number | null
  name: string
  category: string
  lat: number
  lon: number
  description: string | null
  source: Source | null
  opening_hours: Hours | null
  opening_hours_source: string | null
  opening_hours_verified_at: string | null
  cost: string | null
  cost_currency: string | null
  cost_recorded_at: string | null
  visit_minutes: number | null
}
export interface Stop {
  id: number
  place_id: number
  position: number
  visit_minutes: number
  notes: string | null
  origin: 'optimized' | 'manual'
  locked: boolean
  arrive_min: number | null
  start_min: number | null
  end_min: number | null
  wait_min: number | null
  leg_minutes: number | null
  leg_basis: 'routed' | 'user_buffer' | 'none' | null
  leg_distance_m: number | null
  leg_distance_kind: 'routed' | 'straight_line_estimate' | null
  warnings: string[] | null
  place: Place
}
export interface Day { id: number; day_index: number; date: string; stops: Stop[] }
export interface Candidate {
  id: number
  place_id: number
  status: 'mandatory' | 'optional' | 'excluded'
  interest: number
  visit_minutes: number | null
  hours_override: Hours | null
  hours_override_source: string | null
  place: Place
}
export interface Issue { severity: 'error' | 'warning' | 'info'; code: string; message: string; place_key: number | null; day_index: number | null }
export interface Metrics {
  stops: number
  interest_total: number
  visit_minutes: number
  travel_minutes: number | null
  buffer_minutes: number | null
  wait_minutes: number
  distance_m: number
  distance_kind: 'routed' | 'straight_line_estimate'
  distance_note: string
  spend?: string
  before?: Metrics
}
export interface Unscheduled { key: number; code: string; detail: string; name?: string }
export interface LastOptimization {
  id: number
  created_at: string
  solver: string
  explanation: string[]
  unscheduled: Unscheduled[]
  metrics: Metrics
  params: Record<string, unknown>
  input_hash: string
}
export interface LatestRun {
  id: number
  kind: 'optimize' | 'reschedule'
  created_at: string
  status: 'feasible' | 'infeasible' | 'empty'
  matrix_kind: string
  matrix_provider: string
  issues: Issue[]
  metrics: Metrics
  last_optimization: LastOptimization | null
}
export interface Point { lat: number; lon: number; label?: string }
export interface Trip {
  id: number
  name: string
  destination: Destination
  start_date: string
  end_date: string
  travelers: number
  day_start: string
  day_end: string
  currency: string
  budget: string | null
  travel_mode: 'walking' | 'driving' | 'cycling'
  transit_buffer_minutes: number
  max_daily_minutes: number | null
  max_travel_minutes: number | null
  max_walk_minutes: number | null
  accessibility: { step_free: boolean; notes: string | null } | null
  interests: string[] | null
  start_point: Point | null
  end_point: Point | null
  days: Day[]
  candidates: Candidate[]
  pins: { place_id: number; day_index: number }[]
  latest_run: LatestRun | null
}
export interface TripSummary { id: number; name: string; start_date: string; end_date: string; destination: Destination }
export interface OptimizeResult {
  result: { status: string; issues: Issue[]; unscheduled: Unscheduled[]; explanation: string[]; metrics: Metrics; matrix_kind: string; days: unknown[] }
  persisted: boolean
  run_id: number | null
  trip: Trip | null
}
export interface Expense { id: number; category: string; description: string | null; amount: string; currency: string; day_index: number | null }
export interface Budget {
  currency: string
  travelers: number
  planned_admission: Record<string, string>
  stops_without_known_cost: number
  expenses_by_category: Record<string, Record<string, string>>
  totals_by_currency: Record<string, string>
  budget: string | null
  in_trip_currency: string
  remaining_in_trip_currency: string | null
  over_budget: boolean | null
  conversion: { provider: string; converted_total: string | null; rates: { from: string; to: string; rate: string; as_of: string; provider: string }[]; note: string | null }
  notes: string[]
}
export interface AppConfig { routing_provider: string; fx_provider: string; tile_url: string; tile_attribution: string }
