import { useState, type FormEvent } from 'react'
import { buildTripBody } from '../lib/forms'
import type { Destination, Trip } from '../types'
import { ErrorBanner, Field } from './ui'

interface Props {
  destinations: Destination[]
  initial?: Trip
  submitLabel: string
  onSubmit: (body: Record<string, unknown>) => Promise<void>
}

export default function TripSetupForm({ destinations, initial, submitLabel, onSubmit }: Props) {
  const t = initial
  const [f, setF] = useState<Record<string, string | boolean>>({
    name: t?.name ?? '', destination_id: String(t?.destination.id ?? destinations[0]?.id ?? ''),
    start_date: t?.start_date ?? '', end_date: t?.end_date ?? '', travelers: String(t?.travelers ?? 1),
    day_start: t?.day_start.slice(0, 5) ?? '09:00', day_end: t?.day_end.slice(0, 5) ?? '18:00',
    currency: t?.currency ?? 'EUR', budget: t?.budget ?? '', travel_mode: t?.travel_mode ?? 'walking',
    transit_buffer_minutes: String(t?.transit_buffer_minutes ?? 15),
    max_daily_minutes: t?.max_daily_minutes?.toString() ?? '', max_travel_minutes: t?.max_travel_minutes?.toString() ?? '',
    max_walk_minutes: t?.max_walk_minutes?.toString() ?? '',
    step_free: t?.accessibility?.step_free ?? false, access_notes: t?.accessibility?.notes ?? '',
    interests: (t?.interests ?? []).join(', '),
    start_lat: t?.start_point?.lat.toString() ?? '', start_lon: t?.start_point?.lon.toString() ?? '', start_label: t?.start_point?.label ?? '',
    end_lat: t?.end_point?.lat.toString() ?? '', end_lon: t?.end_point?.lon.toString() ?? '', end_label: t?.end_point?.label ?? '',
  })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const set = (k: string) => (e: { target: { value: string; type?: string; checked?: boolean } }) =>
    setF({ ...f, [k]: e.target.type === 'checkbox' ? !!e.target.checked : e.target.value })

  async function submit(e: FormEvent) {
    e.preventDefault()
    const { body, error: err } = buildTripBody(f)
    if (err || !body) { setError(err ?? 'Invalid form'); return }
    setError(null); setBusy(true)
    try { await onSubmit(body) } catch (x) { setError(x instanceof Error ? x.message : 'Could not save') } finally { setBusy(false) }
  }

  return (
    <form onSubmit={submit} className="space-y-5" noValidate>
      <ErrorBanner message={error} />
      <fieldset className="card grid gap-3 p-4 sm:grid-cols-2">
        <legend className="px-1 text-sm font-bold">Trip</legend>
        <Field label="Trip name" htmlFor="name"><input id="name" className="input" required value={String(f.name)} onChange={set('name')} /></Field>
        <Field label="Destination" htmlFor="dest">
          <select id="dest" className="input" value={String(f.destination_id)} onChange={set('destination_id')}>
            {destinations.map((d) => <option key={d.id} value={d.id}>{d.name}{d.country ? `, ${d.country}` : ''}</option>)}
          </select>
        </Field>
        <Field label="Start date" htmlFor="sd"><input id="sd" className="input" type="date" required value={String(f.start_date)} onChange={set('start_date')} /></Field>
        <Field label="End date" htmlFor="ed"><input id="ed" className="input" type="date" required value={String(f.end_date)} onChange={set('end_date')} /></Field>
        <Field label="Travellers" htmlFor="tv"><input id="tv" className="input" type="number" min={1} max={50} value={String(f.travelers)} onChange={set('travelers')} /></Field>
        <Field label="Interests" htmlFor="int" hint="Comma separated place categories, e.g. museum, park. Matching places start at interest 4.">
          <input id="int" className="input" value={String(f.interests)} onChange={set('interests')} />
        </Field>
      </fieldset>

      <fieldset className="card grid gap-3 p-4 sm:grid-cols-2">
        <legend className="px-1 text-sm font-bold">Daily schedule</legend>
        <Field label="Day starts" htmlFor="ds"><input id="ds" className="input" type="time" value={String(f.day_start)} onChange={set('day_start')} /></Field>
        <Field label="Day ends" htmlFor="de"><input id="de" className="input" type="time" value={String(f.day_end)} onChange={set('day_end')} /></Field>
        <Field label="Travel mode" htmlFor="tm">
          <select id="tm" className="input" value={String(f.travel_mode)} onChange={set('travel_mode')}>
            <option value="walking">Walking</option><option value="driving">Driving</option><option value="cycling">Cycling</option>
          </select>
        </Field>
        <Field label="Transit buffer between stops (min)" htmlFor="buf" hint="Your own assumption, used when no routing data exists. It is not an estimate of travel time.">
          <input id="buf" className="input" type="number" min={0} max={240} value={String(f.transit_buffer_minutes)} onChange={set('transit_buffer_minutes')} />
        </Field>
        <Field label="Max daily workload (min)" htmlFor="mdw" hint="Visits plus travel, excluding waiting. Blank = whole day window.">
          <input id="mdw" className="input" type="number" min={30} value={String(f.max_daily_minutes)} onChange={set('max_daily_minutes')} />
        </Field>
        <Field label="Max travel per day (min)" htmlFor="mtd" hint="Enforced only with real routing data.">
          <input id="mtd" className="input" type="number" min={5} value={String(f.max_travel_minutes)} onChange={set('max_travel_minutes')} />
        </Field>
        <Field label="Max single leg (min)" htmlFor="mwl" hint="Longest walk/drive between two stops. Enforced only with routing data.">
          <input id="mwl" className="input" type="number" min={5} value={String(f.max_walk_minutes)} onChange={set('max_walk_minutes')} />
        </Field>
      </fieldset>

      <fieldset className="card grid gap-3 p-4 sm:grid-cols-2">
        <legend className="px-1 text-sm font-bold">Budget</legend>
        <Field label="Currency" htmlFor="cur"><input id="cur" className="input" maxLength={3} value={String(f.currency)} onChange={set('currency')} /></Field>
        <Field label="Total budget (optional)" htmlFor="bud"><input id="bud" className="input" inputMode="decimal" value={String(f.budget)} onChange={set('budget')} /></Field>
      </fieldset>

      <fieldset className="card grid gap-3 p-4 sm:grid-cols-3">
        <legend className="px-1 text-sm font-bold">Start and end points (optional, e.g. your hotel)</legend>
        <Field label="Start latitude" htmlFor="slat"><input id="slat" className="input" inputMode="decimal" value={String(f.start_lat)} onChange={set('start_lat')} /></Field>
        <Field label="Start longitude" htmlFor="slon"><input id="slon" className="input" inputMode="decimal" value={String(f.start_lon)} onChange={set('start_lon')} /></Field>
        <Field label="Start label" htmlFor="slab"><input id="slab" className="input" value={String(f.start_label)} onChange={set('start_label')} /></Field>
        <Field label="End latitude" htmlFor="elat"><input id="elat" className="input" inputMode="decimal" value={String(f.end_lat)} onChange={set('end_lat')} /></Field>
        <Field label="End longitude" htmlFor="elon"><input id="elon" className="input" inputMode="decimal" value={String(f.end_lon)} onChange={set('end_lon')} /></Field>
        <Field label="End label" htmlFor="elab"><input id="elab" className="input" value={String(f.end_label)} onChange={set('end_label')} /></Field>
      </fieldset>

      <fieldset className="card space-y-2 p-4">
        <legend className="px-1 text-sm font-bold">Accessibility (optional)</legend>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!f.step_free} onChange={set('step_free')} /> Step-free access needed</label>
        <Field label="Notes" htmlFor="acc" hint="The catalog has no verified accessibility data, so TripWeave will warn you to check each stop instead of filtering.">
          <input id="acc" className="input" value={String(f.access_notes)} onChange={set('access_notes')} />
        </Field>
      </fieldset>

      <button className="btn btn-primary" disabled={busy}>{busy ? 'Saving…' : submitLabel}</button>
    </form>
  )
}
