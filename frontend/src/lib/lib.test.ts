import { describe, expect, it } from 'vitest'
import { buildHours, buildTripBody } from './forms'
import { describeLeg, distanceLabel, itineraryMarkers, travelLabel } from './itinerary'
import { fmtClock, fmtDistance, fmtDuration } from './time'
import { day, metrics, stop } from '../test/fixtures'

describe('time formatting', () => {
  it('formats clock, duration, distance', () => {
    expect(fmtClock(9 * 60 + 5)).toBe('09:05')
    expect(fmtClock(null)).toBe('--:--')
    expect(fmtDuration(90)).toBe('1 h 30 min')
    expect(fmtDuration(120)).toBe('2 h')
    expect(fmtDistance(850)).toBe('850 m')
    expect(fmtDistance(1250)).toBe('1.3 km')
  })
})

describe('honest travel labelling', () => {
  it('never calls a straight line a route or travel time', () => {
    const s = stop(1, 1, 'A', 1, { leg_minutes: 15, leg_basis: 'user_buffer', leg_distance_m: 1200, leg_distance_kind: 'straight_line_estimate' })
    const text = describeLeg(s)!
    expect(text).toMatch(/straight line \(estimate, not a route or travel time\)/)
    expect(text).toMatch(/transit buffer \(your assumption\)/)
    expect(text).not.toMatch(/by route|\(routed\)/)
  })
  it('labels routed legs as routed', () => {
    const s = stop(1, 1, 'A', 1, { leg_minutes: 20, leg_basis: 'routed', leg_distance_m: 1500, leg_distance_kind: 'routed' })
    expect(describeLeg(s)).toBe('20 min travel (routed) · 1.5 km by route')
    expect(describeLeg(s, 5)).toBe('15 min travel (routed) + 5 min buffer (your assumption) · 1.5 km by route')
  })
  it('summaries distinguish estimate from routed', () => {
    expect(distanceLabel(metrics())).toMatch(/straight-line estimate/)
    expect(travelLabel(metrics())).toMatch(/Unknown, no routing data/)
    expect(travelLabel(metrics({ travel_minutes: 45, distance_kind: 'routed' }))).toBe('45 min (routed)')
  })
  it('returns null when a stop has no leg data', () => {
    expect(describeLeg(stop(1, 1, 'A', 0))).toBeNull()
  })
})

describe('itinerary markers', () => {
  it('numbers by visit order per day and can filter a day', () => {
    const days = [day(0, [stop(1, 11, 'B', 1), stop(2, 10, 'A', 0)]), day(1, [stop(3, 12, 'C', 0)])]
    const all = itineraryMarkers(days, null)
    expect(all.map((m) => [m.label, m.number, m.dayIndex])).toEqual([['A', 1, 0], ['B', 2, 0], ['C', 1, 1]])
    expect(itineraryMarkers(days, 1).map((m) => m.label)).toEqual(['C'])
  })
})

const goodTrip = {
  name: 'T', destination_id: '1', start_date: '2030-01-07', end_date: '2030-01-08', travelers: '2', day_start: '09:00',
  day_end: '18:00', currency: 'eur', budget: '100.50', travel_mode: 'walking', transit_buffer_minutes: '10',
  max_daily_minutes: '', max_travel_minutes: '', max_walk_minutes: '', step_free: false, access_notes: '', interests: 'Museum, park',
  start_lat: '', start_lon: '', start_label: '', end_lat: '', end_lon: '', end_label: '',
}

describe('trip form validation', () => {
  it('builds a valid body', () => {
    const { body, error } = buildTripBody(goodTrip)
    expect(error).toBeUndefined()
    expect(body).toMatchObject({ currency: 'EUR', budget: '100.50', day_start: '09:00:00', interests: ['museum', 'park'], accessibility: null })
  })
  it.each([
    [{ end_date: '2030-01-01' }, /end date/i],
    [{ day_start: '19:00' }, /start must be before/i],
    [{ budget: '-5' }, /budget/i],
    [{ budget: '1.234' }, /budget/i],
    [{ currency: 'EU' }, /currency/i],
    [{ start_lat: '95', start_lon: '2' }, /start point/i],
    [{ end_lat: '48' }, /end point/i],
    [{ max_daily_minutes: '60', max_travel_minutes: '90' }, /cannot exceed/i],
    [{ name: '  ' }, /name/i],
    [{ destination_id: '' }, /destination/i],
  ])('rejects %j', (over, msg) => {
    expect(buildTripBody({ ...goodTrip, ...over }).error).toMatch(msg)
  })
})

describe('hours validation', () => {
  it('requires days, ordered times and a source', () => {
    expect(buildHours([], '09:00', '17:00', 's').error).toMatch(/at least one/)
    expect(buildHours(['mon'], '17:00', '09:00', 's').error).toMatch(/before closing/)
    expect(buildHours(['mon'], '09:00', '17:00', ' ').error).toMatch(/source/)
    expect(buildHours(['mon', 'tue'], '09:00', '17:00', 'sign').hours).toEqual({ mon: [['09:00', '17:00']], tue: [['09:00', '17:00']] })
  })
})
