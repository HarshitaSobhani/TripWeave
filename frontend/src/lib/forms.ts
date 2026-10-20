import type { Hours } from '../types'

export function buildHours(days: string[], open: string, close: string, source: string): { hours?: Hours; error?: string } {
  if (days.length === 0) return { error: 'Choose at least one open day.' }
  if (!open || !close || open >= close) return { error: 'Opening time must be before closing time.' }
  if (!source.trim()) return { error: 'Say where these hours come from (source is required).' }
  const hours: Hours = {}
  for (const d of days) hours[d] = [[open, close]]
  return { hours }
}

const optInt = (v: string) => (v.trim() === '' ? null : Number(v))

export function buildTripBody(f: Record<string, string | boolean>): { body?: Record<string, unknown>; error?: string } {
  const start = String(f.start_date), end = String(f.end_date)
  if (!f.name || !String(f.name).trim()) return { error: 'Give the trip a name.' }
  if (!Number(f.destination_id)) return { error: 'Choose a destination.' }
  if (!start || !end) return { error: 'Choose travel dates.' }
  if (end < start) return { error: 'The end date cannot be before the start date.' }
  const ds = String(f.day_start), de = String(f.day_end)
  if (ds >= de) return { error: 'Daily start must be before daily end.' }
  const budget = String(f.budget).trim()
  if (budget !== '' && !/^\d+(\.\d{1,2})?$/.test(budget)) return { error: 'Budget must be a positive amount with at most 2 decimals.' }
  const ccy = String(f.currency).toUpperCase()
  if (!/^[A-Z]{3}$/.test(ccy)) return { error: 'Currency must be a 3-letter code such as EUR.' }
  const pt = (p: string) => {
    const lat = String(f[`${p}_lat`]).trim(), lon = String(f[`${p}_lon`]).trim()
    if (!lat && !lon) return null
    const la = Number(lat), lo = Number(lon)
    if (!lat || !lon || Number.isNaN(la) || Number.isNaN(lo) || Math.abs(la) > 90 || Math.abs(lo) > 180) return undefined
    return { lat: la, lon: lo, label: String(f[`${p}_label`]) }
  }
  const sp = pt('start'), ep = pt('end')
  if (sp === undefined) return { error: 'Start point needs a valid latitude (-90..90) and longitude (-180..180).' }
  if (ep === undefined) return { error: 'End point needs a valid latitude (-90..90) and longitude (-180..180).' }
  const maxDaily = optInt(String(f.max_daily_minutes)), maxTravel = optInt(String(f.max_travel_minutes))
  if (maxDaily && maxTravel && maxTravel > maxDaily) return { error: 'Maximum travel per day cannot exceed the maximum daily workload.' }
  return {
    body: {
      name: String(f.name).trim(), destination_id: Number(f.destination_id), start_date: start, end_date: end,
      travelers: Number(f.travelers), day_start: ds.length === 5 ? `${ds}:00` : ds, day_end: de.length === 5 ? `${de}:00` : de,
      currency: ccy, budget: budget === '' ? null : budget, travel_mode: f.travel_mode,
      transit_buffer_minutes: Number(f.transit_buffer_minutes),
      max_daily_minutes: maxDaily, max_travel_minutes: maxTravel, max_walk_minutes: optInt(String(f.max_walk_minutes)),
      accessibility: f.step_free || String(f.access_notes).trim() ? { step_free: !!f.step_free, notes: String(f.access_notes).trim() || null } : null,
      interests: String(f.interests).split(',').map((s) => s.trim().toLowerCase()).filter(Boolean),
      start_point: sp, end_point: ep,
    },
  }
}
