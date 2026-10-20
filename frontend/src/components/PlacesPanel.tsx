import { useEffect, useState, type FormEvent } from 'react'
import { api } from '../api'
import type { Candidate, Place, Trip } from '../types'
import HoursEditor from './HoursEditor'
import { Empty, ErrorBanner, Field } from './ui'

interface Props {
  trip: Trip
  selectedId: number | null
  onSelect: (placeId: number) => void
  onChanged: () => Promise<void>
  onError: (m: string) => void
}

function CandidateRow({ trip, c, selected, onSelect, onChanged, onError }: { trip: Trip; c: Candidate; selected: boolean } & Pick<Props, 'onSelect' | 'onChanged' | 'onError'>) {
  const [minutes, setMinutes] = useState(c.visit_minutes?.toString() ?? '')
  const [showHours, setShowHours] = useState(false)
  const pin = trip.pins.find((p) => p.place_id === c.place_id)
  const run = async (fn: () => Promise<unknown>) => {
    try { await fn(); await onChanged() } catch (e) { onError(e instanceof Error ? e.message : 'Failed') }
  }
  const id = `cand-${c.place_id}`
  return (
    <li className={`card space-y-2 p-3 ${selected ? 'ring-2 ring-slate-900' : ''} ${c.status === 'excluded' ? 'opacity-60' : ''}`}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <button className="text-left font-semibold hover:underline" onClick={() => onSelect(c.place_id)}>{c.place.name}</button>
          <p className="text-xs text-slate-500">{c.place.category}
            {c.place.cost ? ` · ${c.place.cost} ${c.place.cost_currency} per person` : ' · cost unknown'}
            {c.place.opening_hours || c.hours_override ? ' · hours set' : ' · hours unknown (assumed open)'}
          </p>
        </div>
        <button className="btn btn-sm btn-danger" aria-label={`Remove ${c.place.name} from trip`} onClick={() => run(() => api.deleteCandidate(trip.id, c.place_id))}>Remove</button>
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <div>
          <label htmlFor={`${id}-st`} className="label">Status</label>
          <select id={`${id}-st`} className="input" value={c.status} onChange={(e) => run(() => api.patchCandidate(trip.id, c.place_id, { status: e.target.value }))}>
            <option value="mandatory">Must visit</option><option value="optional">Optional</option><option value="excluded">Excluded</option>
          </select>
        </div>
        <div>
          <label htmlFor={`${id}-in`} className="label">Interest (1-5)</label>
          <select id={`${id}-in`} className="input" value={c.interest} onChange={(e) => run(() => api.patchCandidate(trip.id, c.place_id, { interest: Number(e.target.value) }))}>
            {[1, 2, 3, 4, 5].map((n) => <option key={n}>{n}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor={`${id}-min`} className="label">Visit (min)</label>
          <input id={`${id}-min`} className="input" type="number" min={5} max={1440} step={5} placeholder="60 default" value={minutes}
            onChange={(e) => setMinutes(e.target.value)}
            onBlur={() => { const v = Number(minutes); if (minutes !== '' && Number.isInteger(v) && v > 0 && v !== c.visit_minutes) run(() => api.patchCandidate(trip.id, c.place_id, { visit_minutes: v })) }} />
        </div>
        <div>
          <label htmlFor={`${id}-pin`} className="label">Pin to day</label>
          <select id={`${id}-pin`} className="input" value={pin?.day_index ?? ''}
            onChange={(e) => run(() => (e.target.value === '' ? api.clearPin(trip.id, c.place_id) : api.setPin(trip.id, c.place_id, Number(e.target.value))))}>
            <option value="">Any day</option>
            {trip.days.map((d) => <option key={d.id} value={d.day_index}>Day {d.day_index + 1}</option>)}
          </select>
        </div>
      </div>
      {c.hours_override && <p className="text-xs text-slate-600">Hours override: {Object.entries(c.hours_override).map(([d, w]) => `${d} ${w.map((x) => x.join('–')).join(', ')}`).join('; ')} (source: {c.hours_override_source})</p>}
      <button className="text-xs text-brand-700 underline" onClick={() => setShowHours(!showHours)} aria-expanded={showHours}>{showHours ? 'Hide hours' : 'Set opening hours'}</button>
      {showHours && <HoursEditor idPrefix={id} onApply={(h, s) => run(() => api.patchCandidate(trip.id, c.place_id, { hours_override: h, hours_override_source: s }))} />}
    </li>
  )
}

function CustomPlaceForm({ trip, onDone, onError }: { trip: Trip; onDone: () => Promise<void>; onError: (m: string) => void }) {
  const [f, setF] = useState({ name: '', category: '', lat: '', lon: '', cost: '', cost_currency: trip.currency, minutes: '' })
  const [hours, setHours] = useState<{ hours: unknown; source: string } | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const set = (k: string) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })
  async function submit(e: FormEvent) {
    e.preventDefault()
    const lat = Number(f.lat), lon = Number(f.lon)
    if (!f.name.trim() || !f.category.trim()) return setErr('Name and category are required.')
    if (f.lat === '' || f.lon === '' || Number.isNaN(lat) || Number.isNaN(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) return setErr('Enter valid coordinates (lat -90..90, lon -180..180).')
    if (f.cost !== '' && !/^\d+(\.\d{1,2})?$/.test(f.cost)) return setErr('Cost must be a positive amount with at most 2 decimals.')
    if (f.cost !== '' && !/^[A-Z]{3}$/.test(f.cost_currency.toUpperCase())) return setErr('Cost currency must be 3 letters.')
    setErr(null)
    try {
      const place = await api.createPlace({
        destination_id: trip.destination.id, name: f.name.trim(), category: f.category.trim().toLowerCase(), lat, lon,
        visit_minutes: f.minutes === '' ? null : Number(f.minutes),
        cost: f.cost === '' ? null : f.cost, cost_currency: f.cost === '' ? null : f.cost_currency.toUpperCase(),
        opening_hours: hours?.hours ?? null, opening_hours_source: hours?.source ?? null,
      })
      await api.upsertCandidate(trip.id, { place_id: place.id })
      setF({ ...f, name: '', lat: '', lon: '', cost: '', minutes: '' }); setHours(null)
      await onDone()
    } catch (x) { onError(x instanceof Error ? x.message : 'Failed') }
  }
  return (
    <form onSubmit={submit} className="card space-y-2 p-3" noValidate>
      <h3 className="text-sm font-bold">Add your own place (private to you)</h3>
      {err && <ErrorBanner message={err} />}
      <div className="grid grid-cols-2 gap-2">
        <Field label="Name" htmlFor="cp-name"><input id="cp-name" className="input" value={f.name} onChange={set('name')} /></Field>
        <Field label="Category" htmlFor="cp-cat"><input id="cp-cat" className="input" value={f.category} onChange={set('category')} /></Field>
        <Field label="Latitude" htmlFor="cp-lat"><input id="cp-lat" className="input" inputMode="decimal" value={f.lat} onChange={set('lat')} /></Field>
        <Field label="Longitude" htmlFor="cp-lon"><input id="cp-lon" className="input" inputMode="decimal" value={f.lon} onChange={set('lon')} /></Field>
        <Field label="Cost per person (optional)" htmlFor="cp-cost"><input id="cp-cost" className="input" inputMode="decimal" value={f.cost} onChange={set('cost')} /></Field>
        <Field label="Cost currency" htmlFor="cp-ccy"><input id="cp-ccy" className="input" maxLength={3} value={f.cost_currency} onChange={set('cost_currency')} /></Field>
        <Field label="Visit minutes (optional)" htmlFor="cp-min"><input id="cp-min" className="input" type="number" min={5} value={f.minutes} onChange={set('minutes')} /></Field>
      </div>
      <HoursEditor idPrefix="cp" label={hours ? 'Hours saved ✓ (re-apply to change)' : 'Use these hours'} onApply={(h, s) => setHours({ hours: h, source: s })} />
      <button className="btn btn-primary">Create and add to trip</button>
    </form>
  )
}

export default function PlacesPanel({ trip, selectedId, onSelect, onChanged, onError }: Props) {
  const [q, setQ] = useState('')
  const [catalog, setCatalog] = useState<Place[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const inTrip = new Set(trip.candidates.map((c) => c.place_id))

  useEffect(() => {
    let live = true
    const t = setTimeout(() => {
      api.places(trip.destination.id, q).then((p) => { if (live) { setCatalog(p); setErr(null) } })
        .catch((e) => { if (live) setErr(e instanceof Error ? e.message : 'Failed to load places') })
    }, 200)
    return () => { live = false; clearTimeout(t) }
  }, [q, trip.destination.id, trip.candidates.length])

  const add = async (p: Place) => {
    try {
      await api.upsertCandidate(trip.id, { place_id: p.id }); await onChanged()
    } catch (e) { onError(e instanceof Error ? e.message : 'Failed') }
  }

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <section aria-labelledby="cat-h" className="space-y-3">
        <h2 id="cat-h" className="text-lg font-bold">Find places in {trip.destination.name}</h2>
        <label htmlFor="q" className="sr-only">Search places</label>
        <input id="q" className="input" type="search" placeholder="Search by name…" value={q} onChange={(e) => setQ(e.target.value)} />
        <ErrorBanner message={err} />
        {catalog === null ? <output className="text-sm text-slate-600">Loading places…</output> : catalog.length === 0 ? (
          <Empty title="No places match">Try a different search, or add your own place below.</Empty>
        ) : (
          <ul className="max-h-[28rem] space-y-1.5 overflow-auto pr-1">
            {catalog.map((p) => (
              <li key={p.id} className="card flex items-center justify-between gap-2 p-2.5">
                <div className="min-w-0">
                  <button className="truncate text-left text-sm font-semibold hover:underline" onClick={() => onSelect(p.id)}>{p.name}</button>
                  <p className="truncate text-xs text-slate-500">{p.category}{p.source ? ` · source: ${p.source.name}` : ' · your place'}</p>
                </div>
                <button className="btn btn-sm" disabled={inTrip.has(p.id)} onClick={() => add(p)} aria-label={`Add ${p.name} to trip`}>{inTrip.has(p.id) ? 'Added' : 'Add'}</button>
              </li>
            ))}
          </ul>
        )}
        <CustomPlaceForm trip={trip} onDone={onChanged} onError={onError} />
      </section>
      <section aria-labelledby="sel-h" className="space-y-3">
        <h2 id="sel-h" className="text-lg font-bold">Your places ({trip.candidates.length})</h2>
        {trip.candidates.length === 0 ? (
          <Empty title="No places yet">Add places from the catalog. Mark must-see places as “Must visit”.</Empty>
        ) : (
          <ul className="space-y-2">
            {trip.candidates.map((c) => <CandidateRow key={`${c.id}-${c.status}-${c.interest}-${c.visit_minutes}-${trip.pins.find((p) => p.place_id === c.place_id)?.day_index ?? 'x'}`}
              trip={trip} c={c} selected={selectedId === c.place_id} onSelect={onSelect} onChanged={onChanged} onError={onError} />)}
          </ul>
        )}
      </section>
    </div>
  )
}
