import { useState } from 'react'
import { distanceLabel, travelLabel } from '../lib/itinerary'
import { fmtDuration } from '../lib/time'
import type { Issue, LastOptimization, LatestRun, Metrics, Trip } from '../types'
import { IssueList } from './ui'

export interface OptimizeOptions {
  solver: 'auto' | 'ortools' | 'fallback'
  interest_weight?: number
  preview?: boolean
  replace_manual?: boolean
  confirm_replace_manual?: boolean
}

interface Props {
  trip: Trip
  busy: boolean
  onOptimize: (o: OptimizeOptions) => void
  pendingReplace: string[] | null
  onCancelReplace: () => void
  previewMetrics: { metrics: Metrics; issues: Issue[] } | null
  onClearPreview: () => void
}

export function Comparison({ before, after }: { before: Metrics; after: Metrics }) {
  const rows: [string, string, string][] = [
    ['Stops', String(before.stops), String(after.stops)],
    [after.distance_kind === 'routed' ? 'Route distance' : 'Straight-line distance (estimate)', distanceLabel(before), distanceLabel(after)],
    ['Travel time', travelLabel(before), travelLabel(after)],
    ['Time at stops', fmtDuration(before.visit_minutes), fmtDuration(after.visit_minutes)],
    ['Interest score', String(before.interest_total), String(after.interest_total)],
  ]
  return (
    <table className="w-full text-left text-sm">
      <caption className="sr-only">Before and after optimization</caption>
      <thead>
        <tr className="text-xs uppercase text-slate-500"><th scope="col" className="py-1">Measure</th><th scope="col">Before</th><th scope="col">After</th></tr>
      </thead>
      <tbody>
        {rows.map(([k, b, a]) => (
          <tr key={k} className="border-t border-slate-100"><th scope="row" className="py-1 pr-2 font-medium">{k}</th><td className="pr-2">{b}</td><td>{a}</td></tr>
        ))}
      </tbody>
    </table>
  )
}

function Summary({ run, opt }: { run: LatestRun; opt: LastOptimization | null }) {
  const m = run.metrics
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className={`rounded px-2 py-0.5 text-xs font-semibold ${run.status === 'feasible' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}>
          {run.status === 'feasible' ? 'Feasible plan' : run.status === 'infeasible' ? 'Constraints cannot all be met' : 'No stops scheduled'}
        </span>
        <span className="text-slate-600">
          {run.kind === 'optimize' ? `Optimized (${opt?.solver})` : 'Times recomputed after manual edit'}
          {' · '}{run.matrix_kind === 'routed' ? `routing: ${run.matrix_provider}` : 'no routing data'}
        </span>
      </div>
      {m && m.stops != null && (
        <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
          <dt className="text-slate-500">Distance</dt><dd>{distanceLabel(m)}</dd>
          <dt className="text-slate-500">Travel time</dt><dd>{travelLabel(m)}</dd>
          <dt className="text-slate-500">Time at stops</dt><dd>{fmtDuration(m.visit_minutes)}</dd>
          <dt className="text-slate-500">Waiting</dt><dd>{fmtDuration(m.wait_minutes)}</dd>
        </dl>
      )}
      {m?.distance_kind === 'straight_line_estimate' && (
        <p className="rounded bg-sky-50 px-2 py-1 text-xs text-sky-900">{m.distance_note}</p>
      )}
    </div>
  )
}

export function OptimizeControls({ trip, busy, onOptimize, pendingReplace, onCancelReplace, previewMetrics, onClearPreview }: Props) {
  const hasStops = trip.days.some((d) => d.stops.length > 0)
  const [solver, setSolver] = useState<OptimizeOptions['solver']>('auto')
  const [weight, setWeight] = useState('')
  const manualCount = trip.days.flatMap((d) => d.stops).filter((s) => s.locked).length
  const base = (extra: Partial<OptimizeOptions> = {}): OptimizeOptions => ({
    solver, interest_weight: weight === '' ? undefined : Number(weight), ...extra,
  })
  const noCandidates = trip.candidates.filter((c) => c.status !== 'excluded').length === 0

  return (
    <section className="card space-y-3 p-4" aria-labelledby="opt-h">
      <h2 id="opt-h" className="text-lg font-bold">Optimize</h2>
      <div className="flex flex-wrap gap-2">
        <button className="btn btn-primary" disabled={busy || noCandidates} onClick={() => onOptimize(base())}>
          {hasStops ? 'Re-optimize' : 'Optimize itinerary'}
        </button>
        <button className="btn" disabled={busy || noCandidates} onClick={() => onOptimize(base({ preview: true }))}>Preview only</button>
        {manualCount > 0 && (
          <button className="btn btn-danger" disabled={busy} onClick={() => onOptimize(base({ replace_manual: true }))}>
            Replace {manualCount} manual edit{manualCount > 1 ? 's' : ''}…
          </button>
        )}
      </div>
      {noCandidates && <p className="text-sm text-slate-600">Add places to the trip first (Places tab).</p>}
      {manualCount > 0 && (
        <p className="text-xs text-slate-600">Re-optimizing keeps the {manualCount} stop{manualCount > 1 ? 's' : ''} you placed manually on their day and order. Only “Replace” can change them, after confirmation.</p>
      )}
      <details className="text-sm">
        <summary className="cursor-pointer text-slate-700">Advanced</summary>
        <div className="mt-2 grid grid-cols-2 gap-2">
          <div>
            <label htmlFor="solver" className="label">Solver</label>
            <select id="solver" className="input" value={solver} onChange={(e) => setSolver(e.target.value as OptimizeOptions['solver'])}>
              <option value="auto">Automatic (OR-Tools, heuristic fallback)</option>
              <option value="ortools">OR-Tools only</option>
              <option value="fallback">Heuristic fallback</option>
            </select>
          </div>
          <div>
            <label htmlFor="iw" className="label">Interest weight</label>
            <input id="iw" className="input" type="number" min={0} step={1} placeholder="default" value={weight} onChange={(e) => setWeight(e.target.value)} />
            <p className="mt-1 text-xs text-slate-500">Cost units a stop of interest 1 is worth. Lower = more compact, may drop far-off stops.</p>
          </div>
        </div>
      </details>

      {pendingReplace && (
        <div role="alertdialog" aria-labelledby="rep-h" className="space-y-2 rounded-md border border-red-300 bg-red-50 p-3 text-sm">
          <p id="rep-h" className="font-semibold text-red-900">Replace your manual edits?</p>
          <p>These stops were placed by you and will be re-planned: {pendingReplace.join(', ')}.</p>
          <div className="flex gap-2">
            <button className="btn btn-danger" onClick={() => onOptimize(base({ replace_manual: true, confirm_replace_manual: true }))}>Yes, replace them</button>
            <button className="btn" onClick={onCancelReplace}>Keep my edits</button>
          </div>
        </div>
      )}

      {previewMetrics && (
        <div className="space-y-2 rounded-md border border-brand-100 bg-brand-50 p-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold">Preview (nothing saved)</p>
            <button className="btn btn-sm" onClick={onClearPreview}>Dismiss</button>
          </div>
          {previewMetrics.metrics.before && <Comparison before={previewMetrics.metrics.before} after={previewMetrics.metrics} />}
          <IssueList issues={previewMetrics.issues} />
          <button className="btn btn-primary btn-sm" disabled={busy} onClick={() => onOptimize(base())}>Apply this plan</button>
        </div>
      )}

    </section>
  )
}

export function PlanSummary({ trip }: { trip: Trip }) {
  const run = trip.latest_run
  const opt = run?.last_optimization ?? null
  return (
    <section className="card space-y-3 p-4" aria-labelledby="sum-h">
      <h2 id="sum-h" className="text-lg font-bold">Plan summary</h2>
      {run && <Summary run={run} opt={opt} />}
      {opt?.metrics.before && (
        <div>
          <h3 className="mb-1 text-sm font-semibold">Before vs after (last optimization)</h3>
          <Comparison before={opt.metrics.before} after={opt.metrics} />
        </div>
      )}
      {run && <IssueList issues={run.issues} />}
      {opt && opt.unscheduled.length > 0 && (
        <div>
          <h3 className="mb-1 text-sm font-semibold">Not scheduled</h3>
          <ul className="list-disc space-y-0.5 pl-5 text-sm">
            {opt.unscheduled.map((u) => <li key={u.key}><strong>{u.name ?? u.key}</strong> ({u.code.replace('_', ' ')}): {u.detail}</li>)}
          </ul>
        </div>
      )}
      {opt && opt.explanation.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer font-semibold">Why this order?</summary>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-slate-700">{opt.explanation.map((e, i) => <li key={i}>{e}</li>)}</ul>
          <p className="mt-2 break-all text-xs text-slate-500">Run input fingerprint: {opt.input_hash.slice(0, 16)}…</p>
        </details>
      )}
      {!run && <p className="text-sm text-slate-600">No plan yet. Optimize to generate one, or add stops by hand.</p>}
    </section>
  )
}

export default function OptimizePanel(props: Props) {
  return (
    <div className="space-y-4">
      <OptimizeControls {...props} />
      <PlanSummary trip={props.trip} />
    </div>
  )
}
