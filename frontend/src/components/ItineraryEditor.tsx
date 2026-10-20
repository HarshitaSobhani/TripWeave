import { useState } from 'react'
import { dayColor, describeLeg } from '../lib/itinerary'
import { fmtClock, fmtDate, fmtDuration } from '../lib/time'
import type { Candidate, Day, Stop } from '../types'

export interface EditorActions {
  move: (stop: Stop, dayIndex: number, position: number) => void
  patch: (stop: Stop, body: { visit_minutes?: number; notes?: string | null; locked?: boolean }) => void
  remove: (stop: Stop) => void
  add: (placeId: number, dayIndex: number) => void
}

interface Props {
  days: Day[]
  candidates: Candidate[]
  selectedId: number | null
  onSelect: (placeId: number) => void
  actions: EditorActions
  busy: boolean
  bufferMinutes?: number
}

function StopCard({
  stop, index, count, day, days, selected, onSelect, actions, busy, bufferMinutes,
}: {
  stop: Stop; index: number; count: number; day: Day; days: Day[]; selected: boolean
  onSelect: () => void; actions: EditorActions; busy: boolean; bufferMinutes: number
}) {
  const [minutes, setMinutes] = useState(String(stop.visit_minutes))
  const [notes, setNotes] = useState(stop.notes ?? '')
  const leg = index > 0 || stop.leg_minutes != null || stop.leg_distance_m != null ? describeLeg(stop, bufferMinutes) : null
  const id = `stop-${stop.id}`
  const unscheduledTime = stop.start_min == null
  return (
    <li id={id} className={`card p-3 ${selected ? 'ring-2 ring-slate-900' : ''}`} aria-current={selected ? 'true' : undefined}>
      {leg && <p className="-mt-1 mb-2 text-xs text-slate-500">↓ {leg}</p>}
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-sm font-bold text-white" style={{ background: dayColor(day.day_index) }} aria-label={`Stop ${index + 1}`}>
          {index + 1}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <button className="text-left font-semibold hover:underline" onClick={onSelect}>{stop.place.name}</button>
            <span className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${stop.origin === 'manual' ? 'bg-violet-100 text-violet-800' : 'bg-slate-100 text-slate-700'}`}>
              {stop.origin === 'manual' ? 'Manual' : 'Optimized'}
            </span>
            {stop.locked && <span className="rounded bg-violet-50 px-1.5 py-0.5 text-[11px] text-violet-800">Kept on re-optimize</span>}
          </div>
          <p className="text-sm text-slate-700">
            {unscheduledTime ? 'No time assigned' : `${fmtClock(stop.start_min)}–${fmtClock(stop.end_min)}`}
            {' · '}{fmtDuration(stop.visit_minutes)}
            {!!stop.wait_min && <span className="text-amber-700"> · waits {fmtDuration(stop.wait_min)} for opening</span>}
          </p>
          {stop.warnings?.map((w) => (
            <p key={w} className="mt-1 rounded bg-amber-50 px-2 py-1 text-xs text-amber-900" role="note">⚠ {w}</p>
          ))}
          <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-[7rem_1fr]">
            <div>
              <label htmlFor={`${id}-min`} className="label">Minutes</label>
              <input id={`${id}-min`} className="input" type="number" min={5} max={1440} step={5} value={minutes}
                onChange={(e) => setMinutes(e.target.value)}
                onBlur={() => {
                  const v = Number(minutes)
                  if (Number.isInteger(v) && v > 0 && v !== stop.visit_minutes) actions.patch(stop, { visit_minutes: v })
                  else setMinutes(String(stop.visit_minutes))
                }} />
            </div>
            <div>
              <label htmlFor={`${id}-notes`} className="label">Notes</label>
              <input id={`${id}-notes`} className="input" value={notes} maxLength={2000}
                onChange={(e) => setNotes(e.target.value)}
                onBlur={() => { if (notes !== (stop.notes ?? '')) actions.patch(stop, { notes: notes || null }) }} />
            </div>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <button className="btn btn-sm" disabled={busy || index === 0} aria-label={`Move ${stop.place.name} earlier`}
              onClick={() => actions.move(stop, day.day_index, index - 1)}>↑ Earlier</button>
            <button className="btn btn-sm" disabled={busy || index === count - 1} aria-label={`Move ${stop.place.name} later`}
              onClick={() => actions.move(stop, day.day_index, index + 1)}>↓ Later</button>
            <label className="sr-only" htmlFor={`${id}-day`}>Move {stop.place.name} to day</label>
            <select id={`${id}-day`} className="input !w-auto py-1 text-xs" value={day.day_index} disabled={busy}
              onChange={(e) => actions.move(stop, Number(e.target.value), 9999)}>
              {days.map((d) => <option key={d.id} value={d.day_index}>Day {d.day_index + 1}</option>)}
            </select>
            <label className="flex items-center gap-1 text-xs text-slate-700">
              <input type="checkbox" checked={stop.locked} disabled={busy} onChange={(e) => actions.patch(stop, { locked: e.target.checked })} />
              Keep here
            </label>
            <button className="btn btn-sm btn-danger" disabled={busy} onClick={() => actions.remove(stop)}
              aria-label={`Remove ${stop.place.name}`}>Remove</button>
          </div>
        </div>
      </div>
    </li>
  )
}

export default function ItineraryEditor({ days, candidates, selectedId, onSelect, actions, busy, bufferMinutes = 0 }: Props) {
  const scheduled = new Set(days.flatMap((d) => d.stops.map((s) => s.place_id)))
  const available = candidates.filter((c) => !scheduled.has(c.place_id))
  const [addPick, setAddPick] = useState<Record<number, string>>({})

  return (
    <div className="space-y-5">
      {days.map((day) => {
        const stops = [...day.stops].sort((a, b) => a.position - b.position)
        return (
          <section key={day.id} aria-labelledby={`day-${day.id}`}>
            <h3 id={`day-${day.id}`} className="mb-2 flex items-center gap-2 text-base font-bold">
              <span className="inline-block h-3 w-3 rounded-full" style={{ background: dayColor(day.day_index) }} aria-hidden />
              Day {day.day_index + 1} <span className="text-sm font-normal text-slate-500">{fmtDate(day.date)}</span>
            </h3>
            {stops.length === 0 ? (
              <p className="rounded-md border border-dashed border-slate-300 p-3 text-sm text-slate-500">No stops on this day.</p>
            ) : (
              <ol className="space-y-2">
                {stops.map((s, i) => (
                  <StopCard key={`${s.id}-${s.visit_minutes}-${s.notes ?? ''}`} stop={s} index={i} count={stops.length} day={day} days={days}
                    selected={selectedId === s.place_id} onSelect={() => onSelect(s.place_id)} actions={actions} busy={busy} bufferMinutes={bufferMinutes} />
                ))}
              </ol>
            )}
            {available.length > 0 && (
              <div className="mt-2 flex items-center gap-2">
                <label className="sr-only" htmlFor={`add-${day.id}`}>Add a place to day {day.day_index + 1}</label>
                <select id={`add-${day.id}`} className="input !w-auto text-xs" value={addPick[day.day_index] ?? ''}
                  onChange={(e) => setAddPick({ ...addPick, [day.day_index]: e.target.value })}>
                  <option value="">Add a place…</option>
                  {available.map((c) => <option key={c.place_id} value={c.place_id}>{c.place.name}{c.status === 'excluded' ? ' (removed)' : ''}</option>)}
                </select>
                <button className="btn btn-sm" disabled={busy || !addPick[day.day_index]}
                  onClick={() => { actions.add(Number(addPick[day.day_index]), day.day_index); setAddPick({ ...addPick, [day.day_index]: '' }) }}>
                  Add to day {day.day_index + 1}
                </button>
              </div>
            )}
          </section>
        )
      })}
    </div>
  )
}
