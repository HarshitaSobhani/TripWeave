import type { Day, Metrics, Stop } from '../types'
import { fmtDistance, fmtDuration } from './time'

export const DAY_COLORS = ['#1f5bd6', '#d9480f', '#2b8a3e', '#862e9c', '#c2255c', '#0b7285', '#a16207']
export const dayColor = (dayIndex: number) => DAY_COLORS[dayIndex % DAY_COLORS.length]

export interface MarkerModel {
  id: number
  lat: number
  lon: number
  label: string
  number?: number
  color: string
  dayIndex?: number
}

/** Numbered markers: numbering restarts each day, in visit order. */
export function itineraryMarkers(days: Day[], onlyDay: number | null): MarkerModel[] {
  const out: MarkerModel[] = []
  for (const d of days) {
    if (onlyDay !== null && d.day_index !== onlyDay) continue
    ;[...d.stops].sort((a, b) => a.position - b.position).forEach((s, i) => {
      out.push({
        id: s.place_id, lat: s.place.lat, lon: s.place.lon, label: s.place.name,
        number: i + 1, color: dayColor(d.day_index), dayIndex: d.day_index,
      })
    })
  }
  return out
}

/** The only honest wording for a leg between two stops. */
export function describeLeg(s: Stop, bufferMinutes = 0): string | null {
  if (s.leg_distance_kind == null && s.leg_minutes == null) return null
  const parts: string[] = []
  if (s.leg_basis === 'routed' && s.leg_minutes != null) {
    const routed = Math.max(0, s.leg_minutes - bufferMinutes)
    const buffer = bufferMinutes > 0 ? ` + ${fmtDuration(bufferMinutes)} buffer (your assumption)` : ''
    parts.push(`${fmtDuration(routed)} travel (routed)${buffer}`)
    if (s.leg_distance_m != null) parts.push(`${fmtDistance(s.leg_distance_m)} by route`)
  } else {
    if (s.leg_distance_m != null) parts.push(`≈ ${fmtDistance(s.leg_distance_m)} straight line (estimate, not a route or travel time)`)
    if (s.leg_minutes != null) parts.push(`${fmtDuration(s.leg_minutes)} transit buffer (your assumption)`)
  }
  return parts.join(' · ')
}

export function distanceLabel(m: Metrics): string {
  return m.distance_kind === 'routed'
    ? `${fmtDistance(m.distance_m)} (routed)`
    : `≈ ${fmtDistance(m.distance_m)} straight-line estimate`
}

export function travelLabel(m: Metrics): string {
  if (m.travel_minutes != null) return `${fmtDuration(m.travel_minutes)} (routed)`
  return `Unknown, no routing data (${fmtDuration(m.buffer_minutes)} of your buffers scheduled)`
}
