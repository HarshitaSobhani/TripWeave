import { useState } from 'react'
import { buildHours } from '../lib/forms'
import type { Hours } from '../types'

const DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'] as const

export default function HoursEditor({ idPrefix, onApply, label = 'Apply hours' }: {
  idPrefix: string
  onApply: (hours: Hours, source: string) => void
  label?: string
}) {
  const [days, setDays] = useState<string[]>([])
  const [open, setOpen] = useState('09:00')
  const [close, setClose] = useState('17:00')
  const [source, setSource] = useState('')
  const [error, setError] = useState<string | null>(null)
  return (
    <fieldset className="space-y-2 rounded-md border border-slate-200 p-2">
      <legend className="px-1 text-xs font-semibold uppercase text-slate-600">Verified opening hours (optional)</legend>
      <div className="flex flex-wrap gap-2" aria-label="Open days">
        {DAYS.map((d) => (
          <label key={d} className="flex items-center gap-1 text-xs capitalize">
            <input type="checkbox" checked={days.includes(d)} onChange={(e) => setDays(e.target.checked ? [...days, d] : days.filter((x) => x !== d))} />{d}
          </label>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div><label htmlFor={`${idPrefix}-o`} className="label">Opens</label><input id={`${idPrefix}-o`} type="time" className="input" value={open} onChange={(e) => setOpen(e.target.value)} /></div>
        <div><label htmlFor={`${idPrefix}-c`} className="label">Closes</label><input id={`${idPrefix}-c`} type="time" className="input" value={close} onChange={(e) => setClose(e.target.value)} /></div>
      </div>
      <div>
        <label htmlFor={`${idPrefix}-s`} className="label">Source</label>
        <input id={`${idPrefix}-s`} className="input" placeholder="e.g. official website, checked 2030-01-02" value={source} onChange={(e) => setSource(e.target.value)} />
      </div>
      {error && <p role="alert" className="text-xs text-red-700">{error}</p>}
      <button type="button" className="btn btn-sm" onClick={() => {
        const r = buildHours(days, open, close, source)
        if (r.error || !r.hours) { setError(r.error ?? 'Invalid'); return }
        setError(null); onApply(r.hours, source.trim())
      }}>{label}</button>
    </fieldset>
  )
}
