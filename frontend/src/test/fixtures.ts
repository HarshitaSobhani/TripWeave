import type { Day, LatestRun, Metrics, Place, Stop, Trip } from '../types'

export const place = (id: number, name: string, extra: Partial<Place> = {}): Place => ({
  id, destination_id: 1, owner_id: null, name, category: 'landmark', lat: 48.85 + id / 100, lon: 2.35 + id / 100,
  description: null, source: null, opening_hours: null, opening_hours_source: null, opening_hours_verified_at: null,
  cost: null, cost_currency: null, cost_recorded_at: null, visit_minutes: null, ...extra,
})

export const stop = (id: number, placeId: number, name: string, position: number, extra: Partial<Stop> = {}): Stop => ({
  id, place_id: placeId, position, visit_minutes: 60, notes: null, origin: 'optimized', locked: false,
  arrive_min: 540, start_min: 540, end_min: 600, wait_min: 0, leg_minutes: null, leg_basis: null,
  leg_distance_m: null, leg_distance_kind: null, warnings: null, place: place(placeId, name), ...extra,
})

export const day = (idx: number, stops: Stop[]): Day => ({ id: idx + 100, day_index: idx, date: `2030-01-0${7 + idx}`, stops })

export const metrics = (extra: Partial<Metrics> = {}): Metrics => ({
  stops: 3, interest_total: 9, visit_minutes: 180, travel_minutes: null, buffer_minutes: 30, wait_minutes: 0,
  distance_m: 2500, distance_kind: 'straight_line_estimate',
  distance_note: 'Straight-line (great-circle) estimate. Not a route and not a travel time.', ...extra,
})

export const run = (extra: Partial<LatestRun> = {}): LatestRun => ({
  id: 1, kind: 'optimize', created_at: '2030-01-01T00:00:00Z', status: 'feasible', matrix_kind: 'straight_line_estimate',
  matrix_provider: 'straight_line', issues: [], metrics: metrics(), last_optimization: null, ...extra,
})

export const trip = (extra: Partial<Trip> = {}): Trip => ({
  id: 1, name: 'Paris', destination: { id: 1, name: 'Paris', country: 'France', lat: 48.85, lon: 2.35 },
  start_date: '2030-01-07', end_date: '2030-01-08', travelers: 2, day_start: '09:00:00', day_end: '18:00:00',
  currency: 'EUR', budget: '500.00', travel_mode: 'walking', transit_buffer_minutes: 15, max_daily_minutes: null,
  max_travel_minutes: null, max_walk_minutes: null, accessibility: null, interests: null, start_point: null,
  end_point: null, days: [day(0, []), day(1, [])], candidates: [], pins: [], latest_run: null, ...extra,
})
