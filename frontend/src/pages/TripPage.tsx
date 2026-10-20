import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ApiError, api, downloadExport } from '../api'
import BudgetPanel from '../components/BudgetPanel'
import ItineraryEditor, { type EditorActions } from '../components/ItineraryEditor'
import MapView from '../components/MapView'
import { OptimizeControls, PlanSummary, type OptimizeOptions } from '../components/OptimizePanel'
import PlacesPanel from '../components/PlacesPanel'
import TripSetupForm from '../components/TripSetupForm'
import { ErrorBanner, Spinner } from '../components/ui'
import { itineraryMarkers, type MarkerModel } from '../lib/itinerary'
import { fmtDate } from '../lib/time'
import type { AppConfig, Destination, Issue, Metrics, Stop, Trip } from '../types'
import { Shell } from './TripsPage'

type Tab = 'itinerary' | 'places' | 'budget' | 'setup'
const TABS: [Tab, string][] = [['itinerary', 'Itinerary'], ['places', 'Places'], ['budget', 'Budget'], ['setup', 'Trip setup']]
const FALLBACK_CFG: AppConfig = {
  routing_provider: 'none', fx_provider: 'none', tile_url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  tile_attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}

export default function TripPage() {
  const { id } = useParams()
  const tripId = Number(id)
  const nav = useNavigate()
  const [trip, setTrip] = useState<Trip | null>(null)
  const [dests, setDests] = useState<Destination[]>([])
  const [cfg, setCfg] = useState<AppConfig>(FALLBACK_CFG)
  const [tab, setTab] = useState<Tab>('itinerary')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [selected, setSelected] = useState<number | null>(null)
  const [dayFilter, setDayFilter] = useState<number | null>(null)
  const [pendingReplace, setPendingReplace] = useState<string[] | null>(null)
  const [preview, setPreview] = useState<{ metrics: Metrics; issues: Issue[] } | null>(null)
  const [budgetKey, setBudgetKey] = useState(0)
  const [mobileMap, setMobileMap] = useState(false)

  const load = useCallback(async () => {
    try {
      const [t, d, c] = await Promise.all([api.trip(tripId), api.destinations(), api.config().catch(() => FALLBACK_CFG)])
      setTrip(t); setDests(d); setCfg(c); setError(null)
    } catch (e) { setError(e instanceof Error ? e.message : 'Failed to load trip') }
  }, [tripId])
  useEffect(() => { void load() }, [load])

  const apply = (t: Trip, msg: string) => { setTrip(t); setNotice(msg); setBudgetKey((k) => k + 1) }
  const guard = async (fn: () => Promise<void>) => {
    setBusy(true); setError(null)
    try { await fn() } catch (e) { setError(e instanceof Error ? e.message : 'Something went wrong') } finally { setBusy(false) }
  }
  const reload = useCallback(async () => { const t = await api.trip(tripId); setTrip(t); setBudgetKey((k) => k + 1) }, [tripId])

  const optimize = (o: OptimizeOptions) => guard(async () => {
    try {
      const r = await api.optimize(tripId, o)
      setPendingReplace(null)
      if (r.persisted && r.trip) { setPreview(null); apply(r.trip, `Itinerary ${r.result.status === 'feasible' ? 'optimized' : 'generated with problems'}.`) }
      else setPreview({ metrics: r.result.metrics, issues: r.result.issues })
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        const d = e.detail as { manual_stops?: string[] }
        setPendingReplace(d.manual_stops ?? [])
      } else throw e
    }
  })

  const actions: EditorActions = useMemo(() => ({
    move: (s: Stop, day, pos) => void guard(async () => apply(await api.patchStop(tripId, s.id, { day_index: day, position: pos }), `Moved ${s.place.name}.`)),
    patch: (s, body) => void guard(async () => apply(await api.patchStop(tripId, s.id, body), `Updated ${s.place.name}.`)),
    remove: (s) => void guard(async () => apply(await api.deleteStop(tripId, s.id), `Removed ${s.place.name}.`)),
    add: (placeId, day) => void guard(async () => apply(await api.addStop(tripId, { place_id: placeId, day_index: day }), 'Stop added.')),

  }), [tripId])

  const markers: MarkerModel[] = useMemo(() => {
    if (!trip) return []
    if (tab === 'places') {
      return trip.candidates.filter((c) => c.status !== 'excluded').map((c) => ({ id: c.place_id, lat: c.place.lat, lon: c.place.lon, label: c.place.name, color: '#475569' }))
    }
    const m = itineraryMarkers(trip.days, dayFilter)
    const scheduled = new Set(m.map((x) => x.id))
    const rest = trip.candidates.filter((c) => c.status !== 'excluded' && !trip.days.some((d) => d.stops.some((s) => s.place_id === c.place_id)) && !scheduled.has(c.place_id))
      .map((c) => ({ id: c.place_id, lat: c.place.lat, lon: c.place.lon, label: `${c.place.name} (not scheduled)`, color: '#94a3b8' }))
    return dayFilter === null ? [...m, ...rest] : m
  }, [trip, tab, dayFilter])

  const select = (placeId: number) => {
    setSelected(placeId)
    document.getElementById(`stop-${trip?.days.flatMap((d) => d.stops).find((s) => s.place_id === placeId)?.id}`)?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' })
  }

  if (!trip) return <Shell>{error ? <ErrorBanner message={error} onRetry={load} /> : <Spinner label="Loading trip…" />}</Shell>
  const showMap = tab === 'itinerary' || tab === 'places'

  return (
    <Shell>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold">{trip.name}</h1>
          <p className="text-sm text-slate-600">{trip.destination.name} · {fmtDate(trip.start_date)} → {fmtDate(trip.end_date)} · {trip.travelers} traveller{trip.travelers > 1 ? 's' : ''}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-slate-500">All changes save automatically.</span>
          {(['json', 'csv', 'ics'] as const).map((f) => (
            <button key={f} className="btn btn-sm" onClick={() => guard(() => downloadExport(tripId, f))}>Export {f.toUpperCase()}</button>
          ))}
          <button className="btn btn-sm btn-danger" onClick={() => { if (window.confirm('Delete this trip permanently?')) void guard(async () => { await api.deleteTrip(tripId); nav('/') }) }}>Delete trip</button>
        </div>
      </div>
      <output aria-live="polite" className="sr-only">{notice}</output>
      <ErrorBanner message={error} />
      <div role="tablist" aria-label="Trip sections" className="mb-4 flex gap-1 border-b border-slate-200">
        {TABS.map(([t, label]) => (
          <button key={t} role="tab" id={`tab-${t}`} aria-selected={tab === t} aria-controls={`panel-${t}`} tabIndex={tab === t ? 0 : -1}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${tab === t ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-600 hover:text-slate-900'}`}
            onClick={() => setTab(t)}
            onKeyDown={(e) => {
              const i = TABS.findIndex(([x]) => x === tab)
              if (e.key === 'ArrowRight') setTab(TABS[(i + 1) % TABS.length][0])
              if (e.key === 'ArrowLeft') setTab(TABS[(i + TABS.length - 1) % TABS.length][0])
            }}>
            {label}
          </button>
        ))}
      </div>

      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {showMap && (
          <div className="mb-3 flex items-center gap-2 lg:hidden">
            <button className="btn btn-sm" aria-pressed={mobileMap} onClick={() => setMobileMap(!mobileMap)}>{mobileMap ? 'Show list' : 'Show map'}</button>
          </div>
        )}
        {showMap ? (
          <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <div className={`space-y-4 ${mobileMap ? 'hidden lg:block' : ''}`}>
              {tab === 'itinerary' ? (
                <>
                  <OptimizeControls trip={trip} busy={busy} onOptimize={optimize} pendingReplace={pendingReplace}
                    onCancelReplace={() => setPendingReplace(null)} previewMetrics={preview} onClearPreview={() => setPreview(null)} />
                  <div className="flex items-center gap-2 text-sm">
                    <label htmlFor="dayf" className="font-medium">Map shows</label>
                    <select id="dayf" className="input !w-auto" value={dayFilter ?? ''} onChange={(e) => setDayFilter(e.target.value === '' ? null : Number(e.target.value))}>
                      <option value="">All days</option>
                      {trip.days.map((d) => <option key={d.id} value={d.day_index}>Day {d.day_index + 1}</option>)}
                    </select>
                    <button className="btn btn-sm" disabled={busy} onClick={() => guard(async () => apply(await api.reschedule(tripId), 'Times recomputed.'))}>Recompute times</button>
                  </div>
                  <ItineraryEditor days={trip.days} candidates={trip.candidates} selectedId={selected} onSelect={select} actions={actions} busy={busy} bufferMinutes={trip.transit_buffer_minutes} />
                  <PlanSummary trip={trip} />
                </>
              ) : (
                <PlacesPanel trip={trip} selectedId={selected} onSelect={setSelected} onChanged={reload} onError={setError} />
              )}
            </div>
            <div className={`${mobileMap ? '' : 'hidden lg:block'} h-[70vh] lg:sticky lg:top-4`}>
              <MapView markers={markers} selectedId={selected} onSelect={select} tileUrl={cfg.tile_url} attribution={cfg.tile_attribution} showOrderLines={tab === 'itinerary'} />
            </div>
          </div>
        ) : tab === 'budget' ? (
          <BudgetPanel trip={trip} refreshKey={budgetKey} />
        ) : (
          <div className="max-w-3xl">
            <TripSetupForm destinations={dests} initial={trip} submitLabel="Save changes"
              onSubmit={async (body) => { const t = await api.updateTrip(tripId, body); apply(t, 'Trip saved. Re-optimize to apply changed constraints.') }} />
          </div>
        )}
      </div>
    </Shell>
  )
}
